# Lấy thông tin theo chế độ pull với danh tính khởi tạo

## 1. Mục tiêu và bối cảnh

Trong chương **Xác thực AppRole** của **SPRING_VAULT**, bài này giải thích cách một ứng dụng Java sử dụng **danh tính khởi tạo** (*bootstrap identity*) để tự lấy RoleID và SecretID của HashiCorp Vault trước khi đăng nhập bằng AppRole. Đây là **full pull mode** của Spring Vault:

~~~java
VaultToken initialToken = VaultToken.of(bootstrapToken);

AppRoleAuthenticationOptions options = AppRoleAuthenticationOptions.builder()
        .appRole("payment-reconciler")
        .roleId(RoleId.pull(initialToken))
        .secretId(SecretId.pull(initialToken))
        .build();
~~~

Ở ví dụ trên, `initialToken` là **Vault token đã được cấp sẵn** cho thành phần khởi tạo; nó có quyền đọc RoleID và tạo SecretID theo policy riêng. `AppRoleAuthentication` dùng hai credential vừa lấy để yêu cầu một **AppRole client token** khác. Token thứ hai mới được `VaultTemplate` sử dụng để đọc KV secrets hoặc gọi Transit, PKI trong phạm vi policy của workload.

Sau bài học, bạn có thể:

- Phân biệt danh tính khởi tạo, bootstrap Vault token, RoleID, SecretID và AppRole client token.
- Mô tả đúng ba giai đoạn **pull RoleID → pull SecretID → AppRole login** và các HTTP endpoint liên quan.
- Cấu hình ACL tối thiểu cho token khởi tạo, khác biệt rõ với ACL cấp cho token ứng dụng.
- Xây dựng cấu hình Java với `RoleId.pull(...)`, `SecretId.pull(...)`, `AppRoleAuthentication` và `VaultTemplate`.
- Xử lý giới hạn TTL, số lần dùng của bootstrap token, SecretID và client token.
- Thiết kế kiểm thử tích hợp và giám sát phân biệt lỗi ở bước pull, login và đọc secret.

**Giả định lab:** Vault đã được khởi tạo và unseal; có một danh tính quản trị đủ quyền để bật auth method, tạo policy và role. Những lệnh dùng `http://127.0.0.1:8200` chỉ áp dụng cho lab local. Production phải sử dụng HTTPS/TLS được xác minh và không cung cấp root token cho JVM.

## 2. “Danh tính khởi tạo” là gì?

### 2.1. Vấn đề con gà và quả trứng

Trong chế độ `provided`, ứng dụng nhận RoleID và SecretID qua biến môi trường, secret mount hoặc provisioner. Ngược lại, trong **pull mode**, ứng dụng muốn lấy chúng bằng Vault API:

- Đọc `role_id` qua `GET /v1/auth/approle/role/<role-name>/role-id`.
- Yêu cầu phát một `secret_id` qua `POST /v1/auth/approle/role/<role-name>/secret-id`.

Hai endpoint này cần **xác thực và phân quyền**. Nếu ứng dụng chưa có AppRole token thì phải có một danh tính tin cậy khác để được phép gọi chúng. Danh tính đó là *bootstrap identity*; trong Spring Vault full pull mode, thứ truyền vào hai factory method là một **Vault token khởi tạo** (`VaultToken initialToken`).

Danh tính khởi tạo có thể xuất phát từ một quy trình cấp token được kiểm soát, một secret broker, Vault Agent hoặc một phương thức xác thực nền tảng phù hợp với môi trường. Điểm cốt lõi: **phải có điểm xuất phát tin cậy**. Full pull không làm biến mất nhu cầu bảo vệ credential; nó chuyển yêu cầu bảo vệ sang bootstrap token cùng quyền mà token này có.

### 2.2. Hai token phục vụ hai mục đích

| Đối tượng | Được cấp lúc nào? | Quyền cần thiết | Được dùng để làm gì? |
| --- | --- | --- | --- |
| **Bootstrap Vault token** | Trước khi Spring Vault thực hiện pull | `read` trên role-id, `update` trên secret-id của **đúng role** | Lấy thông tin để đăng nhập AppRole |
| **RoleID** | Khi role được tạo; ứng dụng đọc bằng bootstrap token | Không phải token ACL | Xác định AppRole khi login |
| **SecretID** | Khi được Vault sinh cho role thông qua bootstrap token | Không phải token ACL | Chứng minh quyền login AppRole; chịu TTL/số lượt dùng |
| **AppRole client token** | Sau `auth/approle/login` thành công | Policy nghiệp vụ được gắn vào role | Đọc KV, gọi Transit/PKI hoặc secret engine được cấp quyền |

**Không tráo vai trò token:** `VaultToken.of(bootstrapToken)` chỉ bọc chuỗi token khởi tạo để API Spring Vault sử dụng trong quá trình pull. Nó không biến token này thành RoleID, SecretID hay token dùng đọc KV. Dù đều là `VaultToken` ở phía Java, hai token có **chính sách và vòng đời riêng**.

### 2.3. Luồng request thực tế

~~~mermaid
sequenceDiagram
    autonumber
    participant Deploy as Provisioner / Runtime
    participant App as Spring Vault AppRoleAuthentication
    participant Vault as Vault AppRole auth mount
    participant Session as SessionManager
    participant KV as KV v2 secrets engine
    Deploy-->>App: Bootstrap token có ACL hạn chế
    App->>Vault: GET auth/approle/role/payment-reconciler/role-id
    Note over App,Vault: Header X-Vault-Token là bootstrap token
    Vault-->>App: data.role_id
    App->>Vault: POST auth/approle/role/payment-reconciler/secret-id
    Note over App,Vault: Header X-Vault-Token là bootstrap token
    Vault-->>App: data.secret_id
    App->>Vault: POST auth/approle/login (role_id, secret_id)
    Vault-->>App: auth.client_token + TTL + policies
    App-->>Session: AppRole client token
    Session->>KV: Đọc secret bằng AppRole client token
    KV-->>Session: Secret hoặc lỗi phân quyền
~~~

Hai lần gọi đầu **có bootstrap token trong header**; lần AppRole login gửi RoleID/SecretID và không cần dùng bootstrap token làm header xác thực. Sau đó `VaultTemplate` dùng **AppRole client token**. Đây là lý do tách policy của bootstrap token và policy của workload rất quan trọng.

## 3. Spring Vault full pull mode hoạt động thế nào?

### 3.1. Ý nghĩa chính xác của builder

~~~java
import org.springframework.vault.authentication.AppRoleAuthenticationOptions;
import org.springframework.vault.authentication.AppRoleAuthenticationOptions.RoleId;
import org.springframework.vault.authentication.AppRoleAuthenticationOptions.SecretId;
import org.springframework.vault.authentication.VaultToken;

VaultToken initialToken = VaultToken.of(initialTokenValue);

AppRoleAuthenticationOptions options = AppRoleAuthenticationOptions.builder()
        .path("approle")
        .appRole("payment-reconciler")
        .roleId(RoleId.pull(initialToken))
        .secretId(SecretId.pull(initialToken))
        .build();
~~~

| Cấu hình | Chức năng | Lỗi thường gặp |
| --- | --- | --- |
| `path("approle")` | Mount path của AppRole auth method; mặc định `approle` | Ghi nhầm `auth/approle` hoặc URL đầy đủ |
| `appRole("payment-reconciler")` | Tên role dùng để xây đường dẫn **đọc RoleID/phát SecretID** | Bỏ quên `appRole` khi dùng pull |
| `RoleId.pull(initialToken)` | Đọc `role_id` qua endpoint của role, dùng bootstrap token | Bootstrap policy không có `read` |
| `SecretId.pull(initialToken)` | Xin Vault tạo `secret_id` mới, dùng bootstrap token | Bootstrap policy không có `update` |
| `build()` | Tạo options bất biến | Tưởng builder đã tự login |
| `new AppRoleAuthentication(options, vaultClient())` | Tạo implementation của `ClientAuthentication` | Tưởng object mới tạo đã có client token |

`appRole` là **tên role**, còn `role_id` là **giá trị định danh** của role đó. Đừng dùng chuỗi `"payment-reconciler"` để thay cho RoleID nếu Vault tạo RoleID ngẫu nhiên.

### 3.2. Ba chế độ lấy credential dễ nhầm

| Cách lấy | RoleID | SecretID | Thứ runtime cần bảo vệ |
| --- | --- | --- | --- |
| **Provided** | `RoleId.provided(roleId)` | `SecretId.provided(secretId)` | RoleID/SecretID đã được cấp |
| **Full pull** | `RoleId.pull(initialToken)` | `SecretId.pull(initialToken)` | Bootstrap token đủ quyền lấy hai credential |
| **Mixed pull** | `RoleId.provided(roleId)` | `SecretId.pull(initialToken)` | RoleID và bootstrap token có quyền phát SecretID |
| **Wrapped** | `RoleId.provided(roleId)` hoặc wrapped tương ứng | `SecretId.wrapped(wrappingToken)` | Wrapping token có TTL ngắn và chỉ unwrap một lần |

Theo cách gọi của Spring Vault, **full pull** là ứng dụng tự lấy cả RoleID và SecretID từ Vault bằng initial token. `SecretId.wrapped(...)` là **response wrapping**, khác với `pull(...)`: wrapping token không cần quyền `update` để tạo SecretID, mà chỉ được unwrap một response đã được provisioner tạo trước đó.

**Giới hạn đáng nhớ:** mặc dù full pull có thể tự tạo SecretID mới khi cần, bản thân bootstrap token có thể hết TTL, hết số lượt sử dụng hoặc bị thu hồi. Spring Vault không tự tạo ra một danh tính khởi tạo mới chỉ nhờ cấu hình `pull(...)`.

## 4. Thực hành Vault: cấu hình quyền tách biệt

Bài tập dùng role tên `payment-reconciler` để đọc đúng một secret của KV v2. Có **hai policy**: policy phát credential cho bootstrap token và policy đọc dữ liệu nghiệp vụ cho AppRole client token.

### 4.1. Chuẩn bị AppRole và KV v2 trong lab

Chạy từ shell của quản trị viên Vault:

~~~bash
export VAULT_ADDR="http://127.0.0.1:8200"

# Bỏ qua nếu AppRole đã được mount ở auth/approle.
vault auth enable approle

# Bỏ qua nếu mount secret/ đã là KV v2.
vault secrets enable -path=secret -version=2 kv

# Dữ liệu giả, chỉ phục vụ kiểm thử:
vault kv put secret/apps/payment-reconciler flag="enabled"
~~~

Nếu gặp lỗi mount đã tồn tại, hãy kiểm tra mount hiện hữu thay vì bật trùng. Trong production, không đặt bí mật thật trực tiếp trong shell history.

### 4.2. Policy nghiệp vụ cho token sau login

Tạo tệp `payment-reconciler-read.hcl`:

~~~hcl
path "secret/data/apps/payment-reconciler" {
  capabilities = ["read"]
}
~~~

Cài policy:

~~~bash
vault policy write payment-reconciler-read payment-reconciler-read.hcl
~~~

Tệp trên chỉ cấp quyền đọc **một** đường dẫn. Với KV v2, đường dẫn Vault API có thành phần `data/`, còn logical path của Java sẽ là `apps/payment-reconciler` trong mount `secret`.

### 4.3. Tạo AppRole phát token chỉ đọc

~~~bash
vault write auth/approle/role/payment-reconciler \
    bind_secret_id=true \
    token_policies="payment-reconciler-read" \
    secret_id_ttl=10m \
    secret_id_num_uses=1 \
    token_ttl=20m \
    token_max_ttl=2h \
    token_type=service \
    token_num_uses=0

vault read auth/approle/role/payment-reconciler
~~~

Với `secret_id_num_uses=1`, mỗi SecretID chỉ được dùng login thành công một lần. **Đây có thể là lựa chọn phù hợp cho full pull** vì bước `SecretId.pull(...)` xin Vault cấp SecretID mới. Nếu ứng dụng cần đăng nhập lại, nó phải có **bootstrap token còn hiệu lực** để xin SecretID khác.

`token_ttl` và `token_max_ttl` ràng buộc client token theo giới hạn hệ thống. Chúng **không tự gia hạn bootstrap token**. Trong lab, không cấu hình CIDR để giữ luồng cơ bản dễ quan sát; production có thể bổ sung `secret_id_bound_cidrs` và `token_bound_cidrs` sau khi xác định đúng IP egress mà Vault nhìn thấy.

### 4.4. Policy tối thiểu của bootstrap token

Tạo tệp `payment-reconciler-bootstrap.hcl`:

~~~hcl
# Cho phép đọc RoleID của đúng AppRole.
path "auth/approle/role/payment-reconciler/role-id" {
  capabilities = ["read"]
}

# Cho phép tạo SecretID mới của đúng AppRole.
path "auth/approle/role/payment-reconciler/secret-id" {
  capabilities = ["update"]
}
~~~

Đăng ký:

~~~bash
vault policy write payment-reconciler-bootstrap payment-reconciler-bootstrap.hcl
~~~

Hai ACL tương ứng chính xác với HTTP GET và POST mà Spring Vault cần. Bootstrap token không cần quyền `sudo`, không cần `list` toàn bộ roles, không cần quyền sửa role và **không cần `read` trên KV data**. AppRole client token cũng không cần quyền đọc RoleID hoặc tạo SecretID.

Sự phân tách này giúp giới hạn phạm vi truy cập dữ liệu nếu bootstrap token bị lộ. Tuy nhiên, **không được xem bootstrap token là vô hại**: ai chiếm được token còn hiệu lực có thể phát SecretID cho role và login để nhận token ứng dụng. Vì thế policy hẹp, TTL ngắn, giới hạn mạng và audit vẫn cần thiết.

### 4.5. Cấp bootstrap token cho lab

Chỉ dùng danh tính quản trị **bên ngoài ứng dụng** để tạo token cho bootstrap:

~~~bash
vault token create \
    -policy="payment-reconciler-bootstrap" \
    -no-default-policy \
    -ttl=45m \
    -explicit-max-ttl=45m \
    -renewable=false
~~~

Lệnh trả về token cần được chuyển vào runtime qua kênh bí mật được bảo vệ. Trong lab, người thực hành có thể ghi nhận giá trị để inject cho một instance. Trong production, **không in token vào CI log**, không commit vào Git, không nhúng trong JAR/Docker image và không truyền root token vào `VaultToken.of(...)`.

Tại đây, `-ttl=45m` được chọn để dễ quan sát giới hạn của bootstrap token; đó **không phải giá trị khuyến nghị chung**. Bootstrap token hết hạn thì bước pull mới sẽ thất bại dù AppRole vẫn tồn tại. Ứng dụng cần quy trình cấp lại token khởi tạo hoặc sử dụng một cơ chế bootstrap bền vững hơn có kiểm soát.

### 4.6. Kiểm chứng quyền của bootstrap token

Trong một terminal thử nghiệm được bảo vệ, giả sử đã có biến `BOOTSTRAP_TOKEN` do hệ thống lab cung cấp:

~~~bash
# Được phép: đọc RoleID.
VAULT_TOKEN="$BOOTSTRAP_TOKEN" vault read -field=role_id \
    auth/approle/role/payment-reconciler/role-id

# Được phép: xin cấp một SecretID mới.
VAULT_TOKEN="$BOOTSTRAP_TOKEN" vault write -f -field=secret_id \
    auth/approle/role/payment-reconciler/secret-id

# Kỳ vọng bị từ chối: bootstrap policy không cho đọc dữ liệu nghiệp vụ.
VAULT_TOKEN="$BOOTSTRAP_TOKEN" vault kv get \
    secret/apps/payment-reconciler
~~~

Hai lệnh thành công minh họa đúng quyền cần cho pull. Chúng có thể in RoleID/SecretID ra terminal nên chỉ dùng với **credential giả trong lab**. CLI tạo SecretID ở đây chỉ để kiểm tra ACL; khi chạy Java full pull, Spring Vault sẽ tự gọi endpoint phát SecretID, không cần người dùng copy SecretID từ CLI vào ứng dụng.

**Lưu ý về số lượt dùng bootstrap token:** một lần full pull cần ít nhất hai yêu cầu tới Vault bằng initial token (đọc RoleID và tạo SecretID); giới hạn `token_num_uses` quá thấp có thể làm bước thứ hai thất bại. Các lần login lại, thử lại hoặc lời gọi phát credential bổ sung sẽ tiêu thụ thêm lượt. Không chọn quota dựa trên giả định toàn bộ vòng đời chỉ cần đúng hai request.

## 5. Viết Java: sử dụng `RoleId.pull` và `SecretId.pull`

### 5.1. Cấu hình với Spring Vault Core

Ứng dụng sử dụng Spring Framework và Spring Vault Core. Ví dụ tham chiếu **Spring Vault 4.1.x**; tại đây constructor `AppRoleAuthentication(options, vaultClient())` được hỗ trợ. Một số phiên bản cũ dùng constructor với `RestOperations`.

~~~java
package example.vault;

import java.net.URI;

import org.springframework.context.annotation.Configuration;
import org.springframework.vault.authentication.AppRoleAuthentication;
import org.springframework.vault.authentication.AppRoleAuthenticationOptions;
import org.springframework.vault.authentication.AppRoleAuthenticationOptions.RoleId;
import org.springframework.vault.authentication.AppRoleAuthenticationOptions.SecretId;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.authentication.VaultToken;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.config.AbstractVaultConfiguration;

@Configuration
public class PullAppRoleVaultConfiguration extends AbstractVaultConfiguration {

    @Override
    public VaultEndpoint vaultEndpoint() {
        // Production dùng HTTPS và trust CA đúng với cụm Vault.
        return VaultEndpoint.from(URI.create(requiredEnv("VAULT_ADDR")));
    }

    @Override
    public ClientAuthentication clientAuthentication() {
        // Token này chỉ dùng cho bước bootstrap, KHÔNG phải token đọc KV.
        VaultToken initialToken = VaultToken.of(
                requiredEnv("VAULT_APPROLE_BOOTSTRAP_TOKEN"));

        AppRoleAuthenticationOptions options =
                AppRoleAuthenticationOptions.builder()
                        .path("approle")
                        .appRole("payment-reconciler")
                        .roleId(RoleId.pull(initialToken))
                        .secretId(SecretId.pull(initialToken))
                        .build();

        return new AppRoleAuthentication(options, vaultClient());
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                    "Missing required configuration: " + name);
        }
        return value;
    }
}
~~~

Ứng dụng cần được inject `VAULT_ADDR` và `VAULT_APPROLE_BOOTSTRAP_TOKEN`. **Không cần inject `VAULT_ROLE_ID` hoặc `VAULT_SECRET_ID`** khi dùng full pull. Không log token khởi tạo và không đặt giá trị thật làm chuỗi literal trong file Java.

Giải thích từng phần:

1. `vaultEndpoint()` trỏ tới Vault. Spring Vault sẽ tạo các request dựa trên endpoint này và mount path đã cấu hình.
2. `VaultToken.of(...)` chuyển chuỗi token khởi tạo thành đối tượng cho `RoleId.pull` và `SecretId.pull`.
3. `path("approle")` là tên mount. Nếu AppRole nằm ở `auth/team-approle` thì dùng `path("team-approle")` và sửa các ACL bootstrap tương ứng.
4. `appRole("payment-reconciler")` bắt buộc về mặt logic vì endpoint pull RoleID/SecretID cần **tên role**. Đừng nhầm với trường `role_id` dùng khi login.
5. `new AppRoleAuthentication(options, vaultClient())` tạo implementation của `ClientAuthentication`. Việc xây dựng object chưa đồng nghĩa đã lấy token.
6. `AbstractVaultConfiguration` cung cấp những thành phần như `VaultTemplate` và `SessionManager`; tùy cấu hình và phiên bản, session manager có thể quản lý việc sử dụng/gia hạn token.

Khi ứng dụng cần sử dụng `VaultTemplate` lần đầu, quá trình tạo phiên sẽ kích hoạt xác thực. Nếu muốn chủ động kiểm tra đăng nhập trước khi phục vụ request, có thể thiết kế một **startup health check** riêng, nhưng tránh gọi `login()` lặp lại vô ích ở mỗi request hoặc vô tình phát nhiều SecretID.

### 5.2. Đọc KV v2 bằng token AppRole

~~~java
package example.vault;

import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.VaultResponse;

@Service
public class PaymentReconcilerSecrets {

    private final VaultTemplate vaultTemplate;

    public PaymentReconcilerSecrets(VaultTemplate vaultTemplate) {
        this.vaultTemplate = vaultTemplate;
    }

    public String featureFlag() {
        VaultResponse response = vaultTemplate
                .opsForKeyValue("secret", KeyValueBackend.KV_2)
                .get("apps/payment-reconciler");

        if (response == null) {
            throw new IllegalStateException("Vault secret not found");
        }

        Map<String, Object> data = response.getRequiredData();
        Object flag = data.get("flag");
        if (!(flag instanceof String)) {
            throw new IllegalStateException("Invalid secret value");
        }
        return (String) flag;
    }
}
~~~

Nếu đã ghi dữ liệu lab trong bước chuẩn bị, `featureFlag()` phải trả `enabled`. Client token được cấp cho AppRole có `read` trên `secret/data/apps/payment-reconciler`. Token khởi tạo **không cần và không nên có** quyền đọc path này.

`opsForKeyValue("secret", KV_2)` sử dụng logical path `apps/payment-reconciler`; khi viết ACL cho Vault phải dùng HTTP path KV v2 `secret/data/apps/payment-reconciler`.

### 5.3. Nếu role được mount ở đường dẫn khác

Giả sử quản trị viên bật AppRole tại `team-approle`:

~~~bash
vault auth enable -path=team-approle approle
~~~

Tùy chọn Java phải đổi thành:

~~~java
AppRoleAuthenticationOptions options = AppRoleAuthenticationOptions.builder()
        .path("team-approle")
        .appRole("payment-reconciler")
        .roleId(RoleId.pull(initialToken))
        .secretId(SecretId.pull(initialToken))
        .build();
~~~

Khi đó ba endpoint tương ứng là:

| Mục đích | Path Vault |
| --- | --- |
| Đọc RoleID | `auth/team-approle/role/payment-reconciler/role-id` |
| Tạo SecretID | `auth/team-approle/role/payment-reconciler/secret-id` |
| Login | `auth/team-approle/login` |

Đồng thời **hai path trong bootstrap policy cũng phải đổi**. Việc sửa `path(...)` mà giữ nguyên ACL tại `auth/approle/...` sẽ khiến pull bị từ chối hoặc trỏ sai endpoint.

## 6. Bảo vệ và cấp mới danh tính khởi tạo

### 6.1. Bootstrap token vẫn là một credential mạnh

Token khởi tạo đủ quyền phát SecretID của role tương đương khả năng **khởi tạo một phiên AppRole hợp lệ** nếu người sở hữu token biết tên role và có thể gọi Vault. Mặc dù nó không thể tự đọc KV bằng chính token bootstrap, một bên tấn công có thể tận dụng quyền phát SecretID để đăng nhập nhận client token với policy của AppRole.

Các biện pháp cơ bản:

- Giới hạn ACL theo **đúng một role**, chỉ cấp `read` cho role-id và `update` cho secret-id.
- Cấp bootstrap token qua kênh tin cậy; dùng TTL ngắn, kiểm soát số lượt dùng/nguồn mạng khi hạ tầng cho phép và có phương án cấp lại.
- Không dùng root token, không dùng token người vận hành dài hạn và không đưa bootstrap token vào Git, Docker image, log, trace hay tham số command line của service.
- Giữ thông tin đầu vào trong bộ nhớ hoặc secret mount có ACL hệ điều hành/orchestrator phù hợp; audit việc phát credential và login.
- Nếu có nhiều replica, ưu tiên **bootstrap token riêng cho instance/job** hoặc một broker cấp phát có thể thu hồi theo từng instance. Dùng chung token giữa nhiều replica có thể gây tranh chấp số lượt dùng và mở rộng phạm vi ảnh hưởng khi lộ.

### 6.2. Danh tính khởi tạo đến từ đâu?

Có một số mô hình tùy nền tảng:

| Mô hình | Cách lấy initial token | Điều kiện cần kiểm soát |
| --- | --- | --- |
| Provisioner/secret broker | Cấp token policy hẹp và inject khi job/instance bắt đầu | TTL, audit, hạn mức tạo SecretID, phạm vi role |
| Vault Agent hoặc môi trường đã xác thực | Dùng token hợp lệ được agent/sidecar cấp bằng phương thức tin cậy | Cách đồng bộ token với JVM và gia hạn/refresh |
| Workload identity có sẵn (Kubernetes/cloud IAM/OIDC) | Xác thực với Vault trước để nhận token khởi tạo, nếu kiến trúc đòi hỏi AppRole | Thiết kế nhiều bước, đánh giá có nên dùng auth method nền tảng trực tiếp |

**Quyết định kiến trúc:** nếu môi trường đã xác thực workload bằng Kubernetes Auth, AWS IAM, GCP hoặc Azure Auth, có thể dùng luôn token của cơ chế đó để truy cập KV theo policy phù hợp. Thêm một vòng AppRole pull chỉ thực sự có ích khi có yêu cầu quản lý role/credential riêng. Full pull không tự động an toàn hơn mọi phương thức khác.

### 6.3. Kịch bản bootstrap token hết hạn

Giả sử:

- Bootstrap token có TTL 45 phút và không renewable.
- Mỗi SecretID được cấp có TTL 10 phút, dùng login 1 lần.
- AppRole client token có TTL khởi tạo 20 phút và giới hạn gia hạn theo role.

Diễn tiến:

1. Ứng dụng lúc đầu có bootstrap token hợp lệ, pull RoleID và SecretID, login thành công.
2. Trong khi client token còn hợp lệ, `VaultTemplate` đọc KV bằng **client token**, không cần bootstrap token ở từng request.
3. Bootstrap token hết TTL sau đó **không thu hồi tự động** client token đã phát hành.
4. Khi client token cần login lại, quá trình pull có thể thất bại vì bootstrap token đã hết hạn hoặc bị revoke.
5. Phải có quy trình phân phối **bootstrap token mới**, hoặc ứng dụng được thiết kế dùng một danh tính nền tảng có thể lấy token mới khi cần.

Đặc biệt, cách sử dụng `requiredEnv(...)` trong ví dụ Java nạp chuỗi token khởi tạo khi tạo bean. Thay biến môi trường bên ngoài **không tự cập nhật** một `VaultToken` đã được lưu vào options. Muốn xoay vòng token lúc JVM đang chạy, cần thiết kế lại việc cấp credential, khả năng reload/recreate cấu hình hoặc cơ chế session tương ứng; khởi động lại có điều phối là một lựa chọn khi phù hợp.

## 7. Token, TTL, lease và thao tác đọc bí mật

Cần theo dõi **ba vòng đời** tách biệt:

| Vòng đời | Giới hạn bởi | Khi hết hạn/hết lượt |
| --- | --- | --- |
| **Bootstrap token** | TTL, số lượt token, revoke, policy, mạng | Không thể đọc RoleID/tạo SecretID qua pull |
| **SecretID** | `secret_id_ttl`, `secret_id_num_uses`, CIDR, hủy qua accessor | Không thể dùng SecretID đó login AppRole mới |
| **AppRole client token** | `token_ttl`, `token_max_ttl`, loại token, renewal, revoke, CIDR, policy | `VaultTemplate` cần phiên mới hoặc request bị từ chối |

Nếu dùng `LifecycleAwareSessionManager`, Spring Vault có thể gia hạn **client token** khi token có khả năng renewal. Điều này không làm gia hạn bootstrap token, cũng không biến một SecretID đã dùng thành có thêm lượt. Full pull có thể cấp SecretID mới ở lần xác thực kế tiếp **chỉ khi bootstrap token còn quyền và còn hiệu lực**.

Một **KV v2 secret tĩnh** như `secret/apps/payment-reconciler` không tự sinh lease cần renew theo cơ chế dynamic secret. Khi dùng dynamic credentials (ví dụ database engine) hoặc PKI certificates, vòng đời lease/certificate là một vấn đề riêng nữa. Không nhầm **lease dữ liệu động** với TTL của credential AppRole.

### Số lần sử dụng của bootstrap token

Nếu bạn giới hạn số lần dùng bootstrap token, đừng nhầm:

- `secret_id_num_uses=1`: SecretID chỉ đăng nhập được một lần. Full pull có thể tạo SecretID mới cho lần khác.
- `token_num_uses` **của bootstrap token**: giới hạn số **HTTP request** dùng bootstrap token; ít nhất hai lần cho quy trình lấy RoleID và SecretID trong full pull.
- `token_num_uses` của **AppRole client token**: giới hạn những request tiếp theo như đọc KV, gọi Transit và có thể cả hoạt động quản lý phiên.

Một bootstrap token giới hạn lượt quá thấp có thể khiến quá trình pull thất bại ở bước lấy SecretID; một client token giới hạn lượt quá thấp có thể khiến Java đọc được một lần rồi thất bại. Cả hai tình huống có thể trông giống lỗi xác thực nếu không tách được giai đoạn thực tế.

## 8. Phương án giảm quyền: chỉ pull SecretID

Nếu provisioner có thể cấp RoleID ổn định theo cơ chế riêng, ứng dụng có thể dùng `RoleId.provided(...)` và chỉ xin SecretID bằng bootstrap token:

~~~java
VaultToken initialToken = VaultToken.of(
        requiredEnv("VAULT_APPROLE_BOOTSTRAP_TOKEN"));

AppRoleAuthenticationOptions options = AppRoleAuthenticationOptions.builder()
        .path("approle")
        .appRole("payment-reconciler")
        .roleId(RoleId.provided(requiredEnv("VAULT_ROLE_ID")))
        .secretId(SecretId.pull(initialToken))
        .build();
~~~

Khi đó bootstrap policy chỉ cần `update` trên `auth/approle/role/payment-reconciler/secret-id`; không cần `read` ở `role-id` nếu ứng dụng không dùng API đó. Mô hình hỗn hợp cho phép giảm quyền đọc role-id và có thể giảm một request trên mỗi chu trình xác thực. Tuy nhiên, bootstrap token vẫn có quyền phát SecretID; cần bảo vệ chặt chẽ.

Ngược lại, `RoleId.pull(initialToken)` kết hợp với `SecretId.provided(secretId)` cũng khả thi trong trường hợp provisioner chỉ cấp SecretID trước. Vì SecretID là credential bí mật, hãy đánh giá luồng phân phối và cách restart trước khi chọn tổ hợp này.

## 9. Chẩn đoán lỗi theo đúng giai đoạn

| Triệu chứng | Giai đoạn | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- | --- |
| Java không khởi tạo được bean do thiếu `VAULT_APPROLE_BOOTSTRAP_TOKEN` | Cấu hình Java | Runtime chưa inject initial token | Kiểm tra tên biến/cơ chế injection, không in giá trị |
| HTTP 403 khi đọc `role-id` | Pull RoleID | Bootstrap token không có `read`, đã hết TTL/lượt, sai role path | Kiểm tra bootstrap policy, token TTL, `appRole` và mount path |
| HTTP 403 khi POST `secret-id` | Pull SecretID | Thiếu `update`, token bị revoke, quota token cạn, role không tồn tại | Kiểm tra đúng quyền tạo SecretID và trạng thái token |
| HTTP 404 trong bước pull | Pull RoleID/SecretID | Mount path sai, tên role sai | So sánh `path(...)` và `appRole(...)` với Vault |
| Pull thành công nhưng login 400/403 | AppRole login | SecretID bị chặn bởi CIDR, lỗi ràng buộc role, RoleID/SecretID không thuộc cùng role | Kiểm tra role constraints và IP egress mà Vault nhìn thấy |
| AppRole login thành công nhưng KV trả 403 | Đọc dữ liệu | Token AppRole thiếu policy, sai KV v2 ACL path, token-bound CIDR hoặc token không hợp lệ | Kiểm tra policy của client token và logical/API path |
| Service chạy một thời gian rồi không lấy được phiên mới | Vòng đời token | Bootstrap token hết hạn hoặc hết lượt; session token không renew được | Thiết kế cấp lại bootstrap token và reauthentication |
| Chỉ một vài replica gặp lỗi | Phân phối / mạng | Dùng chung bootstrap token có quota, khác IP egress hoặc sai secret injection | Cấp credential theo instance, kiểm tra mạng và quota |

**Cách điều tra thực tế:**

1. Xác định operation nào lỗi: `GET role-id`, `POST secret-id`, `POST login` hay `GET KV`.
2. Kiểm tra mount path, tên AppRole, URL Vault và TLS; phân biệt lỗi mạng với lỗi ACL.
3. Với hai endpoint pull, kiểm tra **bootstrap token** và chính sách của nó. Với login, kiểm tra RoleID/SecretID và role constraints. Với KV, kiểm tra **client token** và policy nghiệp vụ.
4. Đối chiếu Vault audit logs và metric ứng dụng đã che thông tin nhạy cảm: mã lỗi, loại operation, thời điểm, correlation ID. Không ghi token, RoleID, SecretID hoặc dữ liệu bí mật.

Không dùng quyền root để “chữa” lỗi HTTP 403 trong thử nghiệm: cách đó che mất sự khác nhau giữa policy bootstrap và policy workload.

## 10. Kiểm thử tích hợp có ý nghĩa

Có thể dùng một Vault dev/test instance riêng hoặc Testcontainers Vault để chạy các trường hợp sau. Bắt đầu bằng policy/role và secret giả từ bài thực hành, rồi tạo bootstrap token theo từng test.

| Kịch bản | Chuẩn bị | Kỳ vọng |
| --- | --- | --- |
| **Happy path: full pull** | Bootstrap có `read role-id` và `update secret-id`; AppRole có `read KV` | Spring Vault pull, login, `VaultTemplate` đọc được `enabled` |
| **Thiếu quyền đọc RoleID** | Bỏ `read` trong bootstrap policy | Thất bại trước login ở bước pull RoleID |
| **Thiếu quyền phát SecretID** | Bỏ `update` trong bootstrap policy | Thất bại trước login ở bước pull SecretID |
| **Sai tên role** | Đặt `appRole("wrong-role")` | Pull thất bại, không nhận được token workload |
| **Sai mount** | Đặt `path("wrong-mount")` | Endpoint pull không tồn tại/không đúng |
| **Bootstrap token hết hạn** | Token TTL ngắn, đợi quá hạn rồi tạo phiên mới | Pull bị từ chối; cần cấp initial token mới |
| **Bootstrap token hết lượt** | Giới hạn lượt dưới nhu cầu pull | Một trong các request pull bị từ chối |
| **AppRole policy quá hẹp** | Login thành công nhưng bỏ `read KV` | KV trả 403 dù bootstrap và login thành công |
| **SecretID một lần dùng** | Role `secret_id_num_uses=1`, full pull mỗi lần đăng nhập | Mỗi SecretID chỉ dùng được 1 lần; pull lại chỉ khả thi nếu bootstrap token còn hợp lệ |
| **Dùng token bootstrap đọc KV** | Chạy `vault kv get` với bootstrap token | Bị từ chối; chứng minh tách biệt quyền |

Ví dụ test xác minh logic ở tầng nghiệp vụ:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

// Chỉ chạy khi môi trường integration test đã cấp bootstrap token,
// Vault test đã có AppRole, policy và KV secret giả.
@SpringBootTest
class PaymentReconcilerSecretsIT {

    @Autowired
    PaymentReconcilerSecrets secrets;

    @Test
    void readsOnlyAuthorizedKvValue() {
        assertEquals("enabled", secrets.featureFlag());
    }
}
~~~

Đoạn test có chủ đích thể hiện **hành vi tích hợp** với Vault; không đủ để chạy độc lập nếu chưa cấu hình Spring Boot, Vault test instance và provisioning. Đặt nó trong một module test phù hợp hoặc điều chỉnh cho Spring Test thuần nếu dự án không dùng Spring Boot. Kiểm thử âm (thiếu ACL, sai role, token hết hạn) nên dùng các bootstrap token riêng để tránh ảnh hưởng lẫn nhau.

Không cần gọi `clientAuthentication.login()` liên tục để kiểm tra builder: phép thử hữu ích cần xác minh rằng Vault **thật sự phân quyền** đúng ở cả hai giai đoạn.

## 11. Khuyến nghị triển khai và bài tập cuối

Một thiết kế production điển hình có thể phân trách nhiệm như sau:

- **Vault administrator/IaC** tạo mount, role, bootstrap policy và policy nghiệp vụ; cấu hình TTL, CIDR và auditing.
- **Provisioner hoặc nền tảng workload identity** cấp bootstrap token đủ quyền với đúng AppRole, TTL ngắn và phạm vi instance/job.
- **Spring Vault application** nhận bootstrap token tại runtime, gọi pull khi cần, login AppRole và sử dụng `VaultTemplate` qua session manager.
- **Monitoring/rotation** phát hiện login thất bại, bootstrap token sắp hết hạn/hết lượt và lỗi renewal; cấp lại danh tính khởi tạo trước khi lần đăng nhập mới cần đến nó.

**Bài tập 1.** Viết và áp dụng hai policy phân tách bootstrap với nghiệp vụ. Chứng minh bootstrap token không đọc được KV nhưng AppRole token đọc được.

**Bài tập 2.** Cấu hình full pull trong `PullAppRoleVaultConfiguration`, giải thích chính xác những request nào dùng bootstrap token và request nào tạo client token.

**Bài tập 3.** Bỏ quyền `update` ở endpoint `secret-id`, chạy lại và xác định lỗi phát sinh **trước hay sau AppRole login**. Sau đó khôi phục policy tối thiểu.

**Bài tập 4.** Đặt bootstrap token chỉ có một lượt sử dụng. Giải thích tại sao full pull không thể hoàn tất cả hai bước với token đó. Thử một token có nhiều lượt hơn trong lab.

**Bài tập 5.** Thiết kế cách cấp lại bootstrap token cho service dài hạn hoặc replica autoscale khi token hiện tại hết TTL. Nêu vì sao thay biến môi trường sau khi `AppRoleAuthenticationOptions` đã được khởi tạo không tự cập nhật bean.

**Tiêu chí đạt:** người học có thể mô tả đúng luồng **initial token → RoleID/SecretID → AppRole client token → VaultTemplate**, tự cấu hình full pull mode và ACL tối thiểu, chạy đọc KV v2 bằng client token được cấp, phân biệt lỗi từng giai đoạn và nêu được kế hoạch cấp lại danh tính khởi tạo.

## Tài liệu tham khảo

- [Spring Vault Reference — Authentication Methods, mục AppRole](https://docs.spring.io/spring-vault/reference/vault/authentication.html)
- [Spring Vault API — AppRoleAuthenticationOptions](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AppRoleAuthenticationOptions.html)
- [Spring Vault API — AppRoleAuthenticationOptions.RoleId](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AppRoleAuthenticationOptions.RoleId.html)
- [Spring Vault API — AppRoleAuthenticationOptions.SecretId](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AppRoleAuthenticationOptions.SecretId.html)
- [Spring Vault API — AppRoleAuthentication](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AppRoleAuthentication.html)
- [HashiCorp Vault — AppRole Authentication](https://developer.hashicorp.com/vault/docs/auth/approle)
- [HashiCorp Vault — AppRole HTTP API](https://developer.hashicorp.com/vault/api-docs/auth/approle)
- [HashiCorp Vault — Tokens and TTL](https://developer.hashicorp.com/vault/docs/concepts/tokens)

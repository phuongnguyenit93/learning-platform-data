# Kết hợp chế độ push, pull và wrapped theo nhu cầu

## Mục tiêu bài học

Trong chương **Xác thực AppRole** của **SPRING_VAULT**, ứng dụng Java cần có RoleID và, theo cấu hình AppRole thông thường, SecretID để đăng nhập HashiCorp Vault. Spring Vault cung cấp các chiến lược lấy **từng credential** thông qua `AppRoleAuthenticationOptions.RoleId` và `AppRoleAuthenticationOptions.SecretId`. Vì thế, người triển khai có thể **kết hợp nhiều chiến lược** thay vì buộc cả RoleID và SecretID đi qua cùng một kênh phân phối.

Bài này giải quyết câu hỏi thực tế: **khi nào nên nhận trực tiếp credential (provided/push), khi nào nên tự lấy bằng bootstrap token (pull), và khi nào nên nhận response wrapping token để unwrap (wrapped)?** Chúng ta sẽ chọn thiết kế theo mức độ tin cậy của provisioner, vòng đời workload, khả năng rotation, điều kiện kết nối và policy Vault.

Sau khi học, bạn có thể:

- Phân biệt tên gọi **push/pull trong HashiCorp Vault** với **provided/pull/wrapped trong Spring Vault**.
- Thiết kế tổ hợp `RoleId.provided/pull/wrapped` và `SecretId.provided/pull/wrapped` theo nhu cầu workload.
- Cấu hình `AppRoleAuthenticationOptions` và `AppRoleAuthentication` trong Java, tích hợp `VaultTemplate` để đọc KV v2.
- Xây policy tách biệt cho **provisioner**, **bootstrap token** và **AppRole client token**.
- Dự kiến ảnh hưởng của TTL, số lần dùng, response wrapping một lần và token renewal tới restart, autoscaling, lỗi mạng.
- Lập ma trận kiểm thử tích hợp chứng minh login thành công nhưng yêu cầu ngoài quyền vẫn bị Vault từ chối.

Ví dụ tham chiếu sử dụng **Spring Vault Core 4.1.x**, Java 17+ và HashiCorp Vault có AppRole/KV v2. Các URL HTTP và token ở phần lab chỉ dành cho môi trường thử nghiệm; production cần HTTPS/TLS và kênh cấp phát bí mật phù hợp.

## 1. Hai lớp thuật ngữ “push”, “pull” và “wrapped”

### 1.1. Ở phía HashiCorp Vault

Theo cách gọi của Vault đối với **SecretID**:

- **Pull mode:** Vault **tự sinh** SecretID ngẫu nhiên qua `POST auth/approle/role/<role>/secret-id`. Thành phần có quyền có thể yêu cầu response wrapping khi phát SecretID.
- **Push mode:** thành phần có quyền **đăng ký giá trị SecretID tự chọn** qua `POST auth/approle/role/<role>/custom-secret-id`. Giá trị do bên ngoài tạo phải đủ mạnh và được bảo vệ trong quá trình chuyển giao.
- **Response wrapping:** là một cơ chế **bọc response** cho endpoint phát credential, không phải một auth method khác. Có thể áp dụng wrapping cho response sinh SecretID hoặc response đọc RoleID.

Vault gọi “push” và “pull” theo **nguồn tạo SecretID**. Cả SecretID sinh ngẫu nhiên và SecretID tùy chỉnh đều có thể được đưa cho ứng dụng Java dưới dạng chuỗi đã có.

### 1.2. Ở phía Spring Vault

`AppRoleAuthenticationOptions` cho phép mô tả **ứng dụng lấy giá trị RoleID/SecretID bằng cách nào**:

| Spring Vault API | Dữ liệu ứng dụng nhận ban đầu | Lệnh Vault trước khi AppRole login |
| --- | --- | --- |
| `RoleId.provided(roleId)` | Chuỗi RoleID thật | Không cần gọi endpoint đọc RoleID |
| `RoleId.pull(initialToken)` | Bootstrap Vault token | `GET auth/<mount>/role/<role>/role-id` |
| `RoleId.wrapped(wrappingToken)` | Wrapping token cho response chứa RoleID | `POST sys/wrapping/unwrap` |
| `SecretId.provided(secretId)` | Chuỗi SecretID thật | Không cần gọi endpoint phát SecretID |
| `SecretId.pull(initialToken)` | Bootstrap Vault token | `POST auth/<mount>/role/<role>/secret-id` |
| `SecretId.wrapped(wrappingToken)` | Wrapping token cho response chứa SecretID | `POST sys/wrapping/unwrap` |
| `SecretId.absent()` | Không có SecretID | Không gửi `secret_id`; chỉ hợp lệ nếu role cho phép |

**Điểm phân biệt quan trọng:** `SecretId.provided(...)` **không tự chứng minh** SecretID được tạo theo Vault push mode. Nó có thể là SecretID ngẫu nhiên từ endpoint pull nhưng **được provisioner chuyển sẵn cho Java**. Không gọi `custom-secret-id` chỉ vì dự án sử dụng `SecretId.provided(...)`.

`RoleId` bắt buộc trong mọi lần AppRole login. `SecretId.absent()` chỉ dùng khi role được cấu hình `bind_secret_id=false` với các ràng buộc thích hợp; đây không phải lựa chọn mặc định an toàn.

### 1.3. Tất cả chiến lược hội tụ về cùng một lần đăng nhập

~~~mermaid
flowchart LR
    R1["RoleID đã cấp trực tiếp"] --> R["RoleID"]
    R2["Pull RoleID bằng bootstrap token"] --> R
    R3["Unwrap response chứa RoleID"] --> R
    S1["SecretID đã cấp trực tiếp"] --> S["SecretID"]
    S2["Pull SecretID bằng bootstrap token"] --> S
    S3["Unwrap response chứa SecretID"] --> S
    R --> L["POST auth/approle/login"]
    S --> L
    L --> T["AppRole client token"]
    T --> KV["VaultTemplate: KV, Transit, PKI theo policy"]
~~~

Khác biệt nằm ở **quá trình chuẩn bị credential trước login**. Vault vẫn kiểm tra RoleID, SecretID (nếu `bind_secret_id=true`), giới hạn số lần dùng, TTL, CIDR và các ràng buộc role. Sau khi đăng nhập thành công, `VaultTemplate` dùng **client token** được cấp, không dùng RoleID/SecretID trong mỗi request.

## 2. Chọn tổ hợp dựa trên mô hình triển khai

Một tổ hợp có thể tạo được bằng API Java nhưng vẫn không phù hợp với vòng đời ứng dụng. Bảng sau là các lựa chọn có ích nhất:

| RoleID | SecretID | Nguồn ứng dụng cần lúc bắt đầu | Phù hợp khi | Điểm cần quản lý |
| --- | --- | --- | --- | --- |
| `provided` | `provided` | RoleID + SecretID thô | Lab, môi trường có secret injection đáng tin cậy | Bảo vệ SecretID, rotation, TTL/số lượt khi restart |
| `provided` | `wrapped` | RoleID + wrapping token SecretID | CI/CD, job ngắn, container được cấp credential khi khởi động | Token bọc dùng một lần, TTL ngắn, cấp lại mỗi instance |
| `provided` | `pull` | RoleID + bootstrap token | RoleID ổn định, Java được phép xin SecretID mới | Bootstrap token phải có quyền tạo SecretID; bảo vệ token đó |
| `pull` | `pull` | Bootstrap token + tên role | Runtime cần tự lấy cả hai credential | Ít nhất hai request pull; token khởi tạo có đủ ACL, TTL/lượt dùng |
| `wrapped` | `provided` | Wrapping token RoleID + SecretID | Kênh phát RoleID yêu cầu wrapping, SecretID được cấp riêng | Vai trò của hai credential và TTL không đồng đều |
| `wrapped` | `wrapped` | **Hai wrapping token khác nhau** | Provisioner muốn bọc riêng cả hai giá trị | Hai lần unwrap độc lập; kiểm tra chính xác creation path mỗi token |
| `pull` | `provided` | Bootstrap token + SecretID | Chỉ RoleID được phép đọc từ Vault lúc runtime | Bootstrap có quyền đọc RoleID; SecretID vẫn cần phân phối an toàn |

Tổ hợp `provided/absent` dành cho AppRole cố ý tắt yêu cầu SecretID; không nên chọn chỉ để tránh quản lý credential. Các cách phối ghép ít phổ biến cần được thử với **chính phiên bản Spring Vault và cách khởi tạo phiên** đang sử dụng.

**Khuyến nghị chọn ban đầu:** với workload có provisioner đáng tin cậy, `RoleId.provided(...)` + `SecretId.wrapped(...)` là mô hình thực tế phổ biến: RoleID có thể cấp trước, SecretID được phát đúng lúc và chỉ mở ở bên nhận. Với service phải tự lấy SecretID nhiều lần trong vòng đời, cân nhắc `provided + pull` hoặc một phương thức workload authentication khác phù hợp hơn.

### 2.1. Câu hỏi quyết định trước khi chọn

1. Ai có quyền cấp SecretID? Có thể tách provisioner ra khỏi JVM không?
2. Runtime có được phép giữ **bootstrap Vault token có quyền phát SecretID** không?
3. Instance khởi động trong bao lâu? Wrapping TTL có đủ qua hàng đợi CI, scheduling và network delay?
4. Service cần login lại sau khi token hết hạn, khi restart, hoặc khi autoscale không?
5. Có cách cấp **credential mới** sau lần unwrap/SecretID một lần dùng không?
6. Vault nhìn thấy IP egress nào; cần giới hạn `secret_id_bound_cidrs` hoặc `token_bound_cidrs` ra sao?
7. Ứng dụng có thể dùng Kubernetes Auth, AWS/GCP/Azure Auth hoặc phương thức danh tính nền tảng trực tiếp thay cho một chuỗi bootstrap phức tạp không?

Không tối ưu một chiều vào việc “ít secret trong biến môi trường”. Pull giúp tránh đưa SecretID thô vào runtime ban đầu, nhưng **bootstrap token có quyền phát SecretID cũng là credential nhạy cảm**. Wrapped hạn chế rủi ro chuyển giao nhưng cần giải quyết khả năng đăng nhập lại.

## 3. Chuẩn bị môi trường Vault lab với quyền tối thiểu

Ví dụ dùng AppRole `order-sync` để đọc đúng `secret/data/apps/order-sync` (KV v2). Giả định người quản trị có quyền tạo mount/policy/role. Không dùng dữ liệu hoặc token production.

### 3.1. Bật auth và KV v2

~~~bash
export VAULT_ADDR="http://127.0.0.1:8200"

# Bỏ qua nếu auth/approle đã được bật:
vault auth enable approle

# Bỏ qua nếu secret/ đã tồn tại là KV v2:
vault secrets enable -path=secret -version=2 kv

# Dữ liệu giả:
vault kv put secret/apps/order-sync enabled="true"
~~~

Chỉ bật mount khi chưa tồn tại. Các ví dụ local dùng HTTP cho lab; môi trường thực cần HTTPS và xác minh CA/TLS.

### 3.2. Policy nghiệp vụ cho client token

Tạo file `order-sync-read.hcl`:

~~~hcl
path "secret/data/apps/order-sync" {
  capabilities = ["read"]
}
~~~

Áp dụng policy và role:

~~~bash
vault policy write order-sync-read order-sync-read.hcl

vault write auth/approle/role/order-sync \
    bind_secret_id=true \
    token_policies="order-sync-read" \
    secret_id_ttl=15m \
    secret_id_num_uses=1 \
    token_ttl=30m \
    token_max_ttl=2h \
    token_type=service \
    token_num_uses=0

vault read auth/approle/role/order-sync
~~~

`secret_id_num_uses=1` minh họa một SecretID cho một lần login; với mode `provided` dùng lại SecretID khi restart sẽ thất bại nếu chưa được cấp lại. Với `pull`, lần login sau có thể xin SecretID mới **chỉ khi bootstrap token còn hiệu lực/quyền**. Với `wrapped`, lần login lại cần token bọc mới do provisioner cung cấp. Các TTL này là giá trị lab; phải đánh giá cùng chính sách auth mount và global token TTL của Vault.

### 3.3. Tách quyền provisioner và bootstrap

Policy `order-sync-provisioner.hcl` cho thành phần **phát credential và chuyển cho workload**:

~~~hcl
path "auth/approle/role/order-sync/role-id" {
  capabilities = ["read"]
}

path "auth/approle/role/order-sync/secret-id" {
  capabilities = ["update"]
}
~~~

Policy dành cho **bootstrap token** nếu Java tự pull RoleID và SecretID cũng có thể dùng đúng hai quyền này; với `provided RoleID + pull SecretID` chỉ cần quyền `update` ở path thứ hai. Cần có **identity riêng** và token TTL phù hợp cho từng trường hợp; không mặc định đưa token của provisioner vào Java.

~~~bash
vault policy write order-sync-provisioner order-sync-provisioner.hcl

# Chỉ dùng cho lab: tạo token bootstrap policy hẹp.
vault token create \
    -policy="order-sync-provisioner" \
    -no-default-policy \
    -ttl=30m \
    -explicit-max-ttl=30m \
    -renewable=false
~~~

Lệnh cuối chỉ chạy ở môi trường quản trị; token được cấp phải truyền qua kênh bảo vệ. Trong production không hiển thị token thực trên CI log và không sử dụng root/operator token như `initialToken`.

**Ranh giới quan trọng:** token bootstrap **có thể tạo SecretID của role**, từ đó tạo AppRole token có quyền đọc dữ liệu. Dù token bootstrap không trực tiếp có ACL đọc KV, nó vẫn đủ mạnh để bị lợi dụng. Cần TTL ngắn, network boundary, audit và giới hạn theo role.

## 4. Các cách cấp RoleID/SecretID cho từng tổ hợp

### 4.1. Provisioner cung cấp trực tiếp cả hai giá trị

Lệnh dưới đây tạo credential trong lab:

~~~bash
vault read -field=role_id auth/approle/role/order-sync/role-id
vault write -f -field=secret_id auth/approle/role/order-sync/secret-id
~~~

Provisioner chuyển RoleID và SecretID thực bằng secret injection hoặc kênh riêng. Java nhận chúng qua `RoleId.provided(...)` và `SecretId.provided(...)`. Đó là **cung cấp trực tiếp từ góc nhìn Spring Vault**, mặc dù SecretID được Vault **sinh ngẫu nhiên theo pull mode**.

Nếu có yêu cầu nghiệp vụ phải dùng SecretID bên ngoài tự sinh, Vault có endpoint `auth/approle/role/order-sync/custom-secret-id`. Giá trị cần đủ ngẫu nhiên và được quản lý chặt; lựa chọn này **không cần thiết** cho use case thông thường. Không nhầm endpoint tạo custom SecretID với factory `SecretId.provided`.

### 4.2. Provisioner đưa RoleID trực tiếp, SecretID được response-wrap

~~~bash
# RoleID có thể được phân phối trước theo một kênh riêng.
vault read -field=role_id auth/approle/role/order-sync/role-id

# Vault sinh SecretID và chỉ trả wrapping token có TTL 90 giây.
vault write -wrap-ttl=90s -f \
    auth/approle/role/order-sync/secret-id
~~~

Provisioner chuyển **RoleID thật** và **wrapping token chưa unwrap** cho đúng một instance. Spring Vault cấu hình `RoleId.provided(...)` + `SecretId.wrapped(...)` để tự unwrap trước AppRole login.

Nếu người vận hành đã dùng `vault unwrap` thủ công, wrapping token đó không còn dùng được trong Java. Khi chuẩn bị cho một instance mới hoặc lần login mới, cần cấp **SecretID mới + wrapping token mới**. Không chia sẻ một token bọc cho hai replica.

### 4.3. Java tự pull SecretID bằng bootstrap token

Runtime nhận RoleID và một bootstrap token có quyền `update` trên `auth/approle/role/order-sync/secret-id`. Khi login, `SecretId.pull(initialToken)` xin Vault phát SecretID mới. Java không cần nhận SecretID thô qua hệ thống triển khai và không cần token bọc.

Đổi lại, runtime **phải bảo vệ token có quyền phát SecretID** và xử lý TTL/số lượt dùng của token đó. Pull không tự làm bootstrap token sống mãi hoặc tự gia hạn bootstrap token.

### 4.4. Java tự pull cả RoleID và SecretID

Full pull nhận `appRole("order-sync")` và một bootstrap token đủ cả hai ACL: `read` role-id, `update` secret-id. Spring Vault thực hiện hai yêu cầu trước login. Đây là lý do không nên đặt `token_num_uses=1` cho bootstrap token nếu nó phải thực hiện **hai** API request pull.

### 4.5. Wrapped RoleID cùng Wrapped SecretID

Muốn bọc cả hai giá trị, provisioner phát **hai wrapping token độc lập**:

~~~bash
# W_ROLE: response bọc trường role_id.
vault read -wrap-ttl=90s \
    auth/approle/role/order-sync/role-id

# W_SECRET: response bọc trường secret_id mới.
vault write -wrap-ttl=90s -f \
    auth/approle/role/order-sync/secret-id
~~~

Tại Java:

~~~java
AppRoleAuthenticationOptions options =
        AppRoleAuthenticationOptions.builder()
                .path("approle")
                .roleId(RoleId.wrapped(
                        VaultToken.of(requiredEnv("VAULT_WRAPPED_ROLE_ID"))))
                .secretId(SecretId.wrapped(
                        VaultToken.of(requiredEnv("VAULT_WRAPPED_SECRET_ID"))))
                .build();
~~~

**Không sử dụng cùng wrapping token cho cả hai factory method.** Mỗi token chỉ unwrap một lần và phải chứa **đúng response** mà phương thức cần (`role_id` hoặc `secret_id`). Với môi trường yêu cầu xác thực provenance trước khi unwrap, cần kiểm tra metadata `creation_path` của từng token qua `sys/wrapping/lookup`:

- RoleID wrapper: `auth/approle/role/order-sync/role-id`.
- SecretID wrapper: `auth/approle/role/order-sync/secret-id`.

Kiểm tra với Vault đáng tin cậy qua TLS. Trường `creation_path` sai thì từ chối token, thay vì tùy tiện lấy dữ liệu trong payload làm credential.

## 5. Java/Spring Vault: từ lựa chọn chiến lược tới VaultTemplate

### 5.1. Cấu hình mặc định: provided RoleID + wrapped SecretID

Đây là mô hình được minh họa chính trong bài vì tách được RoleID ổn định và SecretID có vòng đời ngắn. Ví dụ sử dụng **Spring Vault Core**, không đòi hỏi auto-configuration của Spring Cloud Vault.

~~~java
package example.vault;

import java.net.URI;

import org.springframework.context.annotation.Configuration;
import org.springframework.vault.authentication.AppRoleAuthentication;
import org.springframework.vault.authentication.AppRoleAuthenticationOptions;
import org.springframework.vault.authentication.AppRoleAuthenticationOptions.RoleId;
import org.springframework.vault.authentication.AppRoleAuthenticationOptions.SecretId;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.authentication.UnwrappingEndpoints;
import org.springframework.vault.authentication.VaultToken;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.config.AbstractVaultConfiguration;

@Configuration
public class OrderSyncVaultConfiguration extends AbstractVaultConfiguration {

    @Override
    public VaultEndpoint vaultEndpoint() {
        return VaultEndpoint.from(URI.create(requiredEnv("VAULT_ADDR")));
    }

    @Override
    public ClientAuthentication clientAuthentication() {
        AppRoleAuthenticationOptions options =
                AppRoleAuthenticationOptions.builder()
                        .path("approle")
                        .roleId(RoleId.provided(requiredEnv("VAULT_ROLE_ID")))
                        .secretId(SecretId.wrapped(
                                VaultToken.of(requiredEnv("VAULT_WRAPPED_SECRET_ID"))))
                        .unwrappingEndpoints(UnwrappingEndpoints.SysWrapping)
                        .build();

        return new AppRoleAuthentication(options, vaultClient());
    }

    private static String requiredEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing required env: " + key);
        }
        return value;
    }
}
~~~

`UnwrappingEndpoints.SysWrapping` dùng API `sys/wrapping/unwrap` hiện đại; có thể bỏ khai báo khi mặc định phiên bản Spring Vault đang dùng đã phù hợp. `path("approle")` là mount AppRole cho login; không phải endpoint unwrap. Nếu Vault mount ở `auth/team-approle`, sử dụng `path("team-approle")` và sửa ACL path cho provisioner/bootstrap tương ứng.

Trong Java, ba biến `VAULT_ADDR`, `VAULT_ROLE_ID`, `VAULT_WRAPPED_SECRET_ID` phải được inject bằng cơ chế bảo vệ phù hợp. Không gắn chúng làm literal vào mã nguồn hoặc file cấu hình được commit. Chỉ cung cấp token bọc **chưa từng unwrap**.

### 5.2. Thay đúng phần options để dùng provided + provided

Khi provisioner đã cấp cả RoleID và SecretID, dùng:

~~~java
AppRoleAuthenticationOptions options =
        AppRoleAuthenticationOptions.builder()
                .path("approle")
                .roleId(RoleId.provided(requiredEnv("VAULT_ROLE_ID")))
                .secretId(SecretId.provided(requiredEnv("VAULT_SECRET_ID")))
                .build();
~~~

Với chế độ này không cần `appRole("order-sync")` để login, vì RoleID được cung cấp sẵn. `AppRoleAuthentication` không cần gọi endpoint đọc RoleID hoặc phát SecretID. Nhưng phải cấp SecretID mới nếu TTL/lượt dùng đã hết.

### 5.3. Thay options để dùng provided + pull

~~~java
VaultToken bootstrapToken = VaultToken.of(
        requiredEnv("VAULT_APPROLE_BOOTSTRAP_TOKEN"));

AppRoleAuthenticationOptions options =
        AppRoleAuthenticationOptions.builder()
                .path("approle")
                .appRole("order-sync")
                .roleId(RoleId.provided(requiredEnv("VAULT_ROLE_ID")))
                .secretId(SecretId.pull(bootstrapToken))
                .build();
~~~

Trong trường hợp này, `appRole("order-sync")` cần để Spring Vault xây endpoint `auth/approle/role/order-sync/secret-id`. Bootstrap token phải có `update` trên endpoint đó. Không cần tự cấp quyền đọc KV cho bootstrap token. RoleID đã có nên không cần cấp bootstrap `read` role-id.

### 5.4. Thay options để dùng full pull

~~~java
VaultToken bootstrapToken = VaultToken.of(
        requiredEnv("VAULT_APPROLE_BOOTSTRAP_TOKEN"));

AppRoleAuthenticationOptions options =
        AppRoleAuthenticationOptions.builder()
                .path("approle")
                .appRole("order-sync")
                .roleId(RoleId.pull(bootstrapToken))
                .secretId(SecretId.pull(bootstrapToken))
                .build();
~~~

Bootstrap token cần `read` role-id và `update` secret-id. Spring Vault sử dụng token để lấy từng credential, sau đó login AppRole. Dù không chứa RoleID/SecretID lúc startup, ứng dụng vẫn phải bảo vệ initial token và có phương án cấp lại khi nó hết hạn.

### 5.5. Đọc secret bằng VaultTemplate

Các đoạn options ở trên là **các phương án thay thế nhau** cho một `ClientAuthentication`, không phải nhiều bean chạy cùng lúc. Dù chọn phương án nào, khi AppRole login thành công thì một Spring service vẫn có thể dùng `VaultTemplate` bình thường:

~~~java
package example.vault;

import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.VaultResponse;

@Service
public class OrderSyncSecrets {

    private final VaultTemplate vaultTemplate;

    public OrderSyncSecrets(VaultTemplate vaultTemplate) {
        this.vaultTemplate = vaultTemplate;
    }

    public boolean isEnabled() {
        VaultResponse response = vaultTemplate
                .opsForKeyValue("secret", KeyValueBackend.KV_2)
                .get("apps/order-sync");

        if (response == null) {
            throw new IllegalStateException("Vault secret not found");
        }
        Map<String, Object> data = response.getRequiredData();
        Object raw = data.get("enabled");
        if (!(raw instanceof String)) {
            throw new IllegalStateException("Invalid enabled field");
        }
        return Boolean.parseBoolean((String) raw);
    }
}
~~~

Nếu Vault lab đã ghi `enabled="true"` và role mang policy `order-sync-read`, `isEnabled()` trả `true`. Quyền `read` của token AppRole được kiểm tra trên `secret/data/apps/order-sync` (KV v2 API path); logical path Java là `apps/order-sync`. Đăng nhập thành công không cấp quyền `update` hoặc `delete` trên secret đó.

### 5.6. Lưu ý khi dùng Spring Cloud Vault

Spring Cloud Vault có các thuộc tính `spring.cloud.vault.authentication=APPROLE` và `spring.cloud.vault.app-role.*` để tự cấu hình nhiều kiểu AppRole. Tuy nhiên, **không phải mọi tổ hợp có thể được suy ra từ YAML properties**; một số tổ hợp đòi hỏi cung cấp bean `AppRoleAuthentication` đã cấu hình. Đặc biệt, cách tích hợp reactive có các giới hạn riêng về full pull.

Nếu ứng dụng đang dùng `AbstractVaultConfiguration` như ví dụ này, đó là cấu hình **Spring Vault Core**. Tránh vừa khai báo bean thủ công vừa bật auto-configuration khác vô tình tạo nhiều client/session với credential khác nhau. Kiểm tra phiên bản Spring Cloud Vault và ma trận mode được hỗ trợ trước khi chuyển đoạn mã builder thành YAML.

## 6. Vòng đời và khả năng phục hồi quyết định phương án

### 6.1. Bốn vòng đời độc lập

| Credential/token | Điều kiện hết hiệu lực | Hệ quả đối với ứng dụng |
| --- | --- | --- |
| **Wrapping token** | TTL ngắn, đã unwrap, bị revoke | Không thể lấy response bọc lần nữa; cần token bọc mới |
| **SecretID** | `secret_id_ttl`, `secret_id_num_uses`, CIDR, revoke | Không thể dùng SecretID đó để login mới |
| **Bootstrap token** | TTL, token use limit, revoke, ACL/CIDR | Không thể pull credential mới nếu token hết hiệu lực |
| **AppRole client token** | TTL, renewal limit, revoke, bound CIDR, policy | `VaultTemplate` mất khả năng gọi API nếu không có token hợp lệ |

`LifecycleAwareSessionManager` có thể gia hạn client token khi được Vault cho phép; nó **không tự quay vòng bootstrap token hay wrapping token**. SecretID đã được unwrap một lần vẫn có thể còn TTL nhưng không nhất thiết còn lượt login. Khi token AppRole cần tạo lại, `ClientAuthentication` phải có một đường lấy credential còn hoạt động.

### 6.2. Minh họa service dài hạn và autoscaling

Giả sử role đặt `secret_id_num_uses=1`, token AppRole có `token_ttl=30m`. Một instance đang chạy đã login và có client token hợp lệ:

- **provided + provided:** login lại bằng cùng SecretID sau lần đầu có thể thất bại; phải cấp SecretID mới và nạp lại cấu hình.
- **provided + wrapped:** wrapping token đã được dùng để unwrap; lần dùng lại có thể thất bại; phải cấp SecretID mới cùng token bọc mới.
- **provided + pull:** có thể xin SecretID mới nếu bootstrap token còn hiệu lực, còn quyền và không vượt hạn mức.
- **pull + pull:** có thể lấy cả hai giá trị nếu bootstrap token còn hiệu lực; cần ít nhất hai request bootstrap cho mỗi chu trình full pull.

Token AppRole **đã được cấp** vẫn có thể sử dụng trong thời hạn cho phép dù SecretID vừa hết lượt hay wrapping token đã bị tiêu thụ. **Thu hồi SecretID không tự động thu hồi mọi client token đã cấp**; ứng phó sự cố cần đánh giá token/session riêng.

### 6.3. Một lần unwrap và timeout mạng

Nếu client timeout sau khi gửi `sys/wrapping/unwrap`, Vault có thể đã tiêu thụ token trong khi client chưa nhận được SecretID. Retry vô điều kiện bằng chính wrapping token sẽ gây lỗi khó giải thích. Quy trình an toàn là kiểm tra audit/lookup trong giới hạn quyền, xác minh trạng thái rồi **cấp một response wrapping mới** nếu không thể xác định hoặc khôi phục dữ liệu cũ.

### 6.4. Dữ liệu config được đọc lúc tạo bean

Đoạn Java `requiredEnv(...)` lấy credential khi `AppRoleAuthenticationOptions` được tạo. Sửa biến môi trường hoặc file secret mount sau đó **không tự thay** các chuỗi đã nằm trong options. Nếu muốn rotation không restart, cần một thiết kế provider/refresh hoặc tái tạo client/session có kiểm soát. Với CI job ngắn có thể khởi tạo instance mới cùng credential mới; với service dài hạn cần quy trình renewal và re-authentication được kiểm thử.

## 7. Các mẫu triển khai theo workload

| Workload | Phương án nên cân nhắc | Tại sao | Điều kiện trước khi chọn |
| --- | --- | --- | --- |
| **Job CI/CD ngắn** | `provided RoleID + wrapped SecretID` | SecretID chỉ xuất hiện sau unwrap ở job runner | Provisioner phát token bọc sát lúc khởi động; TTL đủ cho queue |
| **Service có broker cấp SecretID khi deploy** | `provided + provided` hoặc `provided + wrapped` | JVM không giữ token có quyền phát SecretID | Broker hỗ trợ cấp mới khi restart và rotation |
| **Service được phép tự phát SecretID** | `provided RoleID + pull SecretID` | Tự xin SecretID mới theo yêu cầu | Token bootstrap ACL hẹp, TTL/renewal và cấp lại được quản lý |
| **Nền tảng bootstrap bằng Vault token ngắn hạn** | `pull + pull` | Không cần inject sẵn RoleID/SecretID | Bootstrap token có 2 ACL, đủ TTL/lượt và khả năng cấp lại |
| **Hai kênh cấp credential độc lập** | `wrapped + wrapped` | Hai credential có thể chuyển theo các kênh riêng | Cấp hai token bọc khác nhau, xác minh creation path và TTL |
| **Service Kubernetes/cloud có workload identity sẵn** | Cân nhắc auth method nền tảng | Giảm tầng phân phối credential tự quản | Policy nền tảng cấp được quyền KV/Transit/PKI mong muốn |

Đây là gợi ý theo điều kiện vận hành, không phải một bảng xếp hạng bảo mật tuyệt đối. Một phương án ổn cho job chỉ sống hai phút có thể gây gián đoạn cho service cần chạy liên tục hàng tháng.

## 8. Xử lý lỗi theo từng giai đoạn

| Hiện tượng | Vị trí có khả năng lỗi | Cách kiểm tra |
| --- | --- | --- |
| `RoleId.provided` hoặc `SecretId.provided` bị thiếu | Cấu hình runtime | Biến môi trường/secret file chưa inject; không in giá trị |
| Pull RoleID trả 403 | `GET role-id` | Bootstrap token thiếu `read`, hết TTL/lượt hoặc sai auth mount |
| Pull SecretID trả 403 | `POST secret-id` | Bootstrap token thiếu `update`, đã revoke, role hoặc token quota sai |
| Unwrap trả 400/403 | `sys/wrapping/unwrap` | Wrapping token hết TTL, đã unwrap, sai Vault namespace hoặc payload |
| Unwrap thành công nhưng login thất bại | `auth/approle/login` | SecretID hết TTL/lượt, không thuộc role, sai CIDR, RoleID không khớp |
| Login được nhưng KV trả 403 | `secret/data/...` | Token thiếu policy, sai path KV v2, token-bound CIDR hoặc token không hợp lệ |
| Instance mới thất bại, instance cũ vẫn chạy | Bootstrap hoặc cấp phát | Chia sẻ SecretID/wrapping token ít lượt, sai thứ tự deploy, TTL quá ngắn |
| Sau nhiều giờ không thể login lại | Token lifecycle | Client token không renew được, bootstrap/wrapper cũ không còn dùng được |
| Đã đổi auth mount nhưng pull không hoạt động | Mount/ACL | `path("new-mount")` cần khớp ACL bootstrap ở `auth/new-mount/...` |

Để tìm nguyên nhân, hãy xác định **request nào thất bại** trước khi sửa policy:

1. `GET role-id` hoặc `POST secret-id`: xác minh bootstrap token và tên role.
2. `POST sys/wrapping/unwrap`: xác minh wrapping token, TTL, đã dùng chưa, `creation_path`.
3. `POST auth/approle/login`: xác minh RoleID/SecretID và role constraints.
4. `GET secret/data/apps/order-sync`: xác minh **AppRole client token**, KV v2 mount/path và ACL.

Không ghi RoleID, SecretID, wrapping token, bootstrap token hoặc client token trong log/trace/metrics. Theo dõi mã lỗi, loại request, latency, correlation ID và sự kiện audit Vault đã được kiểm soát truy cập.

## 9. Kiểm thử tích hợp: xác minh từng lựa chọn

Nên dùng Vault dev/test riêng hoặc Testcontainers để tạo AppRole, policy, bootstrap token và secret giả. Mỗi test cần tự cấp credential mới; đặc biệt **không dùng lại wrapping token từ test khác**.

| Ca kiểm thử | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Cả hai provided | RoleID/SecretID hợp lệ, policy KV read | Login và đọc `enabled=true` |
| Provided + wrapped | Wrapping token SecretID còn TTL và chưa unwrap | Spring Vault unwrap rồi login, đọc KV thành công |
| Wrapped token đã tiêu thụ | Gọi unwrap thủ công trước khi Java dùng | Login không thể hoàn tất từ token cũ |
| Provided + pull | Bootstrap token chỉ `update secret-id` | Login thành công, bootstrap token không tự đọc KV được |
| Full pull | Bootstrap có `read role-id` và `update secret-id` | Hai request pull thành công rồi login |
| Bootstrap thiếu `read` | Full pull với policy chỉ có `update secret-id` | Dừng ở giai đoạn pull RoleID |
| Bootstrap thiếu `update` | Provided + pull với policy không có quyền phát SecretID | Dừng ở giai đoạn pull SecretID |
| SecretID hết lượt | `secret_id_num_uses=1`, thử login lại với cùng SecretID | Login thứ hai thất bại; token đã cấp lần đầu có vòng đời riêng |
| Policy đọc KV bị bỏ | Login vẫn thành công | `VaultTemplate` bị `403` khi gọi secret |
| Wrapped + wrapped | Hai wrapping token độc lập, đúng creation paths | Hai lần unwrap rồi login thành công |
| Sai nguồn wrapped | Wrapper cho response path khác | Bước kiểm tra provenance từ chối trước khi login |
| Restart/autoscale | Hai replica dùng chung wrapper | Chỉ một replica unwrap được; cấp riêng từng replica để sửa |

Mỗi ca thử phải xét **chức năng thật của Vault**, không chỉ kiểm tra builder trả object khác null. Việc test TTL/CIDR cần môi trường có đồng hồ/địa chỉ IP nguồn có thể tái hiện; không giả định IP của container chính là IP mà Vault nhìn thấy.

### Bài tập chọn kiến trúc

**Tình huống A.** CI runner được tạo mới vài phút một lần. Provisioner có quyền tạo SecretID, runner không được giữ token quản trị. Hãy cấu hình `provided RoleID + wrapped SecretID`; giải thích vì sao mỗi runner phải có token bọc riêng và `wrap-ttl` cần tính đến độ trễ scheduling.

**Tình huống B.** Java service chạy nhiều tuần, được cấp bootstrap token từ broker có cơ chế refresh. Chọn `provided RoleID + pull SecretID`, viết ACL bootstrap chỉ `update` đúng SecretID path và trình bày cách lấy lại bootstrap token khi quá TTL.

**Tình huống C.** Một tổ chức yêu cầu RoleID và SecretID đi qua hai kênh độc lập, cả hai đều bọc. Hãy phát hai wrapping token, kiểm tra hai `creation_path` và giải thích vì sao một token không thể unwrap hai lần.

**Tình huống D.** Workload có Kubernetes service account và Vault Kubernetes Auth sẵn. Đánh giá liệu thêm AppRole pull có lợi ích cụ thể nào so với dùng trực tiếp token từ Kubernetes Auth; ghi rõ ảnh hưởng của việc duy trì bootstrap token thêm một tầng.

**Tiêu chí hoàn thành:** người học phân biệt đúng push/pull theo Vault và provided/pull/wrapped theo Spring Vault; chọn được tổ hợp hợp lý, cấu hình Java và policy phù hợp; xác minh được đọc KV v2 bằng `VaultTemplate`; mô tả được rotation/restart và chẩn đoán đúng giai đoạn lỗi.

## Tài liệu tham khảo

- [Spring Vault — Authentication Methods, AppRole](https://docs.spring.io/spring-vault/reference/vault/authentication.html)
- [Spring Vault — AppRoleAuthenticationOptions (API)](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AppRoleAuthenticationOptions.html)
- [Spring Vault — AppRoleAuthenticationOptions.Builder (API)](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AppRoleAuthenticationOptions.AppRoleAuthenticationOptionsBuilder.html)
- [Spring Vault — AppRoleAuthenticationOptions.RoleId (API)](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AppRoleAuthenticationOptions.RoleId.html)
- [Spring Vault — AppRoleAuthenticationOptions.SecretId (API)](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AppRoleAuthenticationOptions.SecretId.html)
- [Spring Vault — AppRoleAuthentication (API)](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AppRoleAuthentication.html)
- [HashiCorp Vault — AppRole auth method](https://developer.hashicorp.com/vault/docs/auth/approle)
- [HashiCorp Vault — AppRole API, SecretID pull/push và login](https://developer.hashicorp.com/vault/api-docs/auth/approle)
- [HashiCorp Vault — AppRole best practices / response wrapping](https://developer.hashicorp.com/vault/docs/auth/approle/approle-pattern)
- [HashiCorp Vault — Response wrapping](https://developer.hashicorp.com/vault/docs/concepts/response-wrapping)
- [Spring Cloud Vault — Authentication Methods và ma trận AppRole](https://docs.spring.io/spring-cloud-vault/reference/authentication.html)

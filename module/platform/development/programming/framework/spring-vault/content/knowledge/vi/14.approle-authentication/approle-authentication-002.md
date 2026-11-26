# AppRoleAuthentication và AppRoleAuthenticationOptions

## Mục tiêu bài học

Trong chương **Xác thực AppRole** của **SPRING_VAULT**, hai API quan trọng nhất để ứng dụng Java đăng nhập HashiCorp Vault bằng AppRole là:

- `AppRoleAuthenticationOptions`: mô tả **lấy RoleID và SecretID bằng cách nào**, sử dụng auth mount nào và tên AppRole nào khi cần lấy credential từ Vault.
- `AppRoleAuthentication`: thực hiện quy trình xác thực dựa trên cấu hình đó và trả về **Vault token** để các thành phần như `VaultTemplate` gửi yêu cầu đọc KV secrets, gọi Transit, PKI và những API khác theo policy.

Mục tiêu thực hành là tự cấu hình AppRole trong Spring Vault, đọc một secret KV v2 bằng token nhận được, nhận biết lỗi xác thực và lựa chọn phương thức cấp credential phù hợp với workload. Bài sử dụng Spring Vault **4.1.x** làm phiên bản tham chiếu cho ví dụ Java; với phiên bản 3.x/4.0 có lưu ý tương thích riêng.

Sau khi hoàn thành, bạn có thể giải thích quy trình đăng nhập; sử dụng `provided`, `wrapped`, `pull` và `absent` đúng điều kiện; tùy chỉnh mount path; phân biệt AppRole credential với phiên token; và xây dựng kịch bản kiểm thử, giám sát an toàn.

## 1. Vị trí của hai API trong Spring Vault

AppRole là cơ chế xác thực cho **workload** (dịch vụ Java, CI job hoặc worker) do Vault cung cấp. Thông thường ứng dụng gửi `role_id` và `secret_id` tới `POST /v1/auth/approle/login`. Vault kiểm tra các điều kiện gắn với role rồi trả về token. Token này chịu policy và TTL riêng; nó mới là thứ ứng dụng sử dụng ở những lệnh gọi secret sau đó.

~~~mermaid
sequenceDiagram
    autonumber
    participant Init as Cấu hình ứng dụng
    participant Auth as AppRoleAuthentication
    participant Vault as Vault /auth/approle
    participant Session as SessionManager
    participant Template as VaultTemplate
    participant KV as KV v2
    Init->>Auth: AppRoleAuthenticationOptions
    Session->>Auth: Yêu cầu VaultToken khi cần phiên
    Auth->>Vault: Lấy RoleID/SecretID nếu dùng pull hoặc wrapped
    Vault-->>Auth: Credential cần để login
    Auth->>Vault: POST /v1/auth/approle/login
    Vault-->>Auth: Vault token (TTL, policies)
    Auth-->>Session: VaultToken
    Template->>Session: Lấy token cho request
    Session-->>Template: Token hợp lệ
    Template->>KV: GET /v1/secret/data/apps/order-api
    KV-->>Template: Secret hoặc lỗi phân quyền
~~~

Lưu ý: thành phần khởi tạo `AppRoleAuthentication` **chưa chắc đã gửi request login ngay**. Phiên có thể được tạo khi `SessionManager` cần token lần đầu. `ClientAuthentication.login()` là hành động yêu cầu token; ứng dụng bình thường sử dụng `VaultTemplate` cùng session manager thay vì tự gọi `login()` trước mỗi lệnh đọc.

| API | Vai trò | Đầu vào | Đầu ra / đối tượng liên quan |
| --- | --- | --- | --- |
| `ClientAuthentication` | Giao diện trừu tượng cho thao tác xác thực | Cấu hình xác thực tương ứng | `VaultToken` khi gọi `login()` |
| `AppRoleAuthenticationOptions` | Mô tả cách lấy credential AppRole và đường dẫn auth mount | RoleID, SecretID, mount path, tên role, tùy chọn unwrap | Đối tượng cấu hình bất biến |
| `AppRoleAuthentication` | Cài đặt `ClientAuthentication` cho AppRole | `AppRoleAuthenticationOptions`, `VaultClient` | Token từ Vault AppRole login |
| `SessionManager` | Cấp token cho các request sử dụng Vault; quản lý vòng đời token tùy implementation | `ClientAuthentication`, scheduler/khả năng gia hạn | Token đang dùng trong phiên |
| `VaultTemplate` | Thao tác với Vault API, như KV v2 | `VaultClient` và `SessionManager` | Kết quả đọc/ghi tùy policy |

**Ranh giới trách nhiệm:** `AppRoleAuthentication` không quyết định role được cấp policy gì, không sinh SecretID trừ khi được cấu hình chế độ pull với bootstrap token phù hợp, không tự cấp quyền trên KV và không thay thế chức năng quản lý phiên token của `SessionManager`.

## 2. Hiểu `AppRoleAuthenticationOptions`

### 2.1. Các thuộc tính cấu hình

`AppRoleAuthenticationOptions` sử dụng kiểu builder:

~~~java
AppRoleAuthenticationOptions options = AppRoleAuthenticationOptions.builder()
        .path("approle")
        .roleId(RoleId.provided(roleId))
        .secretId(SecretId.provided(secretId))
        .build();
~~~

Bảng sau giải thích các thành phần:

| Builder method | Ý nghĩa | Khi cần |
| --- | --- | --- |
| `path(String)` | **Mount path** của AppRole auth method; mặc định là `approle` | Đổi khi Vault mount tại đường dẫn khác, ví dụ `team-approle` |
| `roleId(RoleId)` | Nguồn RoleID hoặc cách lấy RoleID | Mọi chế độ xác thực AppRole đều cần RoleID cuối cùng |
| `secretId(SecretId)` | Nguồn SecretID hoặc đánh dấu không gửi SecretID | Bắt buộc có SecretID nếu role bật `bind_secret_id=true` |
| `appRole(String)` | **Tên role** tại Vault, chẳng hạn `order-api` | Cần khi `RoleId.pull` hoặc `SecretId.pull` phải gọi endpoint theo tên role |
| `unwrappingEndpoints(UnwrappingEndpoints)` | Tùy biến cơ chế/endpoint unwrap | Chỉ khi hệ thống dùng response wrapping với yêu cầu tương thích đặc biệt |
| `build()` | Tạo đối tượng options sau khi kiểm tra cấu hình | Sau khi thiết lập các trường |

Đối tượng options là **immutable** sau `build()`. Muốn đổi nguồn credential hay mount path cần tạo cấu hình mới; `build()` không cấp token và không gửi request login.

### 2.2. `path` khác `appRole` như thế nào?

Giả sử quản trị viên đã chạy:

~~~bash
vault auth enable -path=team-approle approle
vault write auth/team-approle/role/order-api \
    bind_secret_id=true \
    token_policies="order-api-read"
~~~

Khi đó:

- `path("team-approle")` xác định nơi mount auth method. Endpoint login sẽ là `/v1/auth/team-approle/login`.
- `appRole("order-api")` là **tên role** dùng để lấy RoleID hoặc SecretID theo pull mode, ví dụ `/v1/auth/team-approle/role/order-api/secret-id`.
- `RoleId.provided(roleId)` là **giá trị** RoleID đã được cấp; nó không nhất thiết trùng tên role.
- Không đưa `auth/` vào `path()`: với ví dụ này là `team-approle`, không phải `auth/team-approle` hay URL đầy đủ.

Nếu ứng dụng đã được cấp RoleID và SecretID (provided mode), `appRole()` không bắt buộc chỉ để login. Nếu bạn dùng pull mode thì tên role là dữ liệu cần thiết để Spring Vault tìm endpoint phát credential.

## 3. Các phương án lấy RoleID và SecretID

Spring Vault biểu diễn **cách thu nhận credential** qua hai kiểu lồng trong `AppRoleAuthenticationOptions`: `RoleId` và `SecretId`. Chúng không phải là `VaultToken` được cấp sau login.

### 3.1. Các cách lấy RoleID

| Factory method | Spring Vault sẽ làm gì? | Điều kiện trước |
| --- | --- | --- |
| `RoleId.provided(String)` | Dùng RoleID đã có | Ứng dụng nhận giá trị từ môi trường triển khai/broker |
| `RoleId.pull(VaultToken)` | Gọi endpoint role-id để đọc RoleID | Có `appRole` và **bootstrap token** đủ quyền đọc endpoint |
| `RoleId.wrapped(VaultToken)` | Unwrap response chứa RoleID | Có wrapping token hợp lệ, chưa sử dụng và còn TTL |

### 3.2. Các cách lấy SecretID

| Factory method | Spring Vault sẽ làm gì? | Điều kiện trước |
| --- | --- | --- |
| `SecretId.provided(String)` | Dùng SecretID đã được cấp sẵn | SecretID còn TTL/lượt dùng và đúng role |
| `SecretId.pull(VaultToken)` | Gọi endpoint phát SecretID cho role | Có `appRole` và bootstrap token đủ quyền **tạo SecretID** |
| `SecretId.wrapped(VaultToken)` | Unwrap response chứa SecretID | Wrapping token còn hiệu lực, chưa được unwrap |
| `SecretId.absent()` | Không gửi trường `secret_id` khi login | Chỉ hợp lệ khi AppRole phía Vault **không** yêu cầu SecretID |

`RoleId` không có `absent()`: AppRole vẫn cần `role_id` để Vault xác định role. `SecretId.absent()` là cơ chế thể hiện rõ cấu hình không dùng SecretID, không phải một cách vượt qua `bind_secret_id=true`.

### 3.3. Push, pull và wrapped khác nhau ở đâu?

**Provided (push credentials):** provisioner sinh và phân phối RoleID/SecretID trước, Java nhận chuỗi và login. Ứng dụng không cần token có quyền quản trị AppRole. Dễ hiểu và dễ triển khai nhưng phải bảo vệ credential trên kênh phân phối, trong bộ nhớ runtime và khi restart.

**Pull:** Java được cấp một **initial/bootstrapping Vault token**; nó dùng token đó để đọc RoleID và/hoặc xin SecretID. Cách này tự động hóa việc lấy credential nhưng đặt thêm trách nhiệm bảo vệ một token có quyền trên endpoint phát credential vào workload. Không nên dùng token quản trị hoặc root token làm bootstrap token.

**Wrapped:** provisioner gọi Vault với `-wrap-ttl` để nhận wrapping token một lần; Java unwrap rồi dùng credential bên trong để login. Cách này có thể giảm phơi lộ SecretID trong khâu chuyển giao, nhưng cần xử lý nghiêm túc thời hạn và tính **dùng một lần** của wrapping token.

Tương ứng, **AppRole login** vẫn chỉ gửi JSON chứa `role_id` và (khi cần) `secret_id`; `AppRoleAuthenticationOptions` thay đổi **cách chuẩn bị** hai giá trị đó trước khi login.

## 4. Ví dụ chạy được: Spring Vault với provided RoleID và SecretID

### 4.1. Chuẩn bị policy và AppRole trên Vault lab

Ví dụ này chạy trên Vault dev/lab đã khởi tạo và có token quản trị đủ quyền cấu hình. Thay địa chỉ/mount cho môi trường của bạn. Không chạy với credential thật hoặc đặt root token vào ứng dụng.

~~~bash
export VAULT_ADDR="http://127.0.0.1:8200"

# Nếu chưa có AppRole auth mount:
vault auth enable approle

# Nếu chưa có mount KV v2 tên "secret":
vault secrets enable -path=secret -version=2 kv

# Dữ liệu mô phỏng; không dùng mật khẩu thật trong terminal.
vault kv put secret/apps/order-api greeting="hello-from-vault"
~~~

Tạo file `order-api-read.hcl`:

~~~hcl
path "secret/data/apps/order-api" {
  capabilities = ["read"]
}
~~~

Ghi policy và tạo role:

~~~bash
vault policy write order-api-read order-api-read.hcl

vault write auth/approle/role/order-api \
    bind_secret_id=true \
    secret_id_ttl=30m \
    secret_id_num_uses=5 \
    token_policies="order-api-read" \
    token_ttl=20m \
    token_max_ttl=2h \
    token_type=service

vault read auth/approle/role/order-api
~~~

Nếu mount đã tồn tại, bỏ qua lệnh `auth enable`/`secrets enable` tương ứng. Khi chọn TTL, số lần dùng, policy và mạng cho production, phải điều chỉnh theo luồng cấp phát và khởi động lại của workload. Ví dụ cho phép SecretID dùng 5 lần là để dễ thực hành; môi trường thật có thể cấp SecretID riêng cho từng instance với giới hạn chặt hơn.

Bên cấp phát (không phải JVM production) lấy giá trị:

~~~bash
vault read -field=role_id auth/approle/role/order-api/role-id
vault write -f -field=secret_id auth/approle/role/order-api/secret-id
~~~

Đưa hai giá trị này đến runtime qua cơ chế secret injection tin cậy. Tránh lưu vào Git, file cấu hình công khai, CI logs hoặc Docker image.

### 4.2. Cấu hình Java bằng `AbstractVaultConfiguration`

Đối với Spring Vault 4.1.x, đoạn dưới là cấu hình tối giản. Phần triển khai phải cung cấp `VAULT_ADDR`, `VAULT_ROLE_ID` và `VAULT_SECRET_ID`. Có thể thay hàm đọc biến môi trường bằng nhà cung cấp credential phù hợp.

~~~java
package example.vault;

import java.net.URI;

import org.springframework.context.annotation.Configuration;
import org.springframework.vault.authentication.AppRoleAuthentication;
import org.springframework.vault.authentication.AppRoleAuthenticationOptions;
import org.springframework.vault.authentication.AppRoleAuthenticationOptions.RoleId;
import org.springframework.vault.authentication.AppRoleAuthenticationOptions.SecretId;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.config.AbstractVaultConfiguration;

@Configuration
public class OrderVaultConfig extends AbstractVaultConfiguration {

    @Override
    public VaultEndpoint vaultEndpoint() {
        return VaultEndpoint.from(
                URI.create(requiredEnv("VAULT_ADDR")));
    }

    @Override
    public ClientAuthentication clientAuthentication() {
        AppRoleAuthenticationOptions options =
                AppRoleAuthenticationOptions.builder()
                        .path("approle")
                        .roleId(RoleId.provided(requiredEnv("VAULT_ROLE_ID")))
                        .secretId(SecretId.provided(requiredEnv("VAULT_SECRET_ID")))
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

**Các điểm quan trọng:**

1. `vaultEndpoint()` xác định URL của Vault; trong sản xuất dùng HTTPS và cấu hình trust CA/TLS đúng chuẩn.
2. `AppRoleAuthenticationOptions.builder()` quyết định cách lấy RoleID, SecretID và mount path.
3. `new AppRoleAuthentication(options, vaultClient())` khởi tạo triển khai `ClientAuthentication`. Lời gọi tạo object không mặc nhiên tạo token.
4. `AbstractVaultConfiguration` cung cấp các bean nền tảng như `VaultTemplate` và `SessionManager`, nên service có thể inject `VaultTemplate`. Với Spring Vault 4.1.x, `vaultClient()` là cách dùng mới; một số phiên bản cũ dùng constructor nhận `restOperations()`.
5. `VAULT_SECRET_ID` là credential bootstrap để đăng nhập, **không phải** Vault client token; tránh tự đưa nó vào HTTP header `X-Vault-Token`.

Không thêm cơ chế `spring.cloud.vault.*` vào cấu hình trên nếu dự án chỉ dùng **Spring Vault Core**. Những property đó thuộc **Spring Cloud Vault** và có luồng auto-configuration riêng.

### 4.3. Dùng `VaultTemplate` đọc KV v2

~~~java
package example.vault;

import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.support.VaultResponse;

@Service
public class OrderConfigService {

    private final VaultTemplate vaultTemplate;

    public OrderConfigService(VaultTemplate vaultTemplate) {
        this.vaultTemplate = vaultTemplate;
    }

    public String loadGreeting() {
        VaultResponse result = vaultTemplate
                .opsForKeyValue("secret", KeyValueBackend.KV_2)
                .get("apps/order-api");

        if (result == null) {
            throw new IllegalStateException("Vault secret does not exist");
        }

        Map<String, Object> data = result.getRequiredData();
        Object greeting = data.get("greeting");
        if (!(greeting instanceof String)) {
            throw new IllegalStateException("Invalid greeting secret");
        }
        return (String) greeting;
    }
}
~~~

Trong trường hợp này:

- `VaultTemplate` nhờ session manager cung cấp token; token được sử dụng trong request tới Vault.
- `opsForKeyValue("secret", KV_2)` hiểu đường dẫn KV v2. Logic path trong Java là `apps/order-api`, còn policy phải cấp `read` cho `secret/data/apps/order-api`.
- Nếu ứng dụng cố ghi `secret/apps/order-api` với policy chỉ có `read`, Vault trả lỗi phân quyền. Đây là lỗi **authorization**, không phải lỗi RoleID/SecretID.

Nên xác minh `loadGreeting()` trả `hello-from-vault` từ dữ liệu lab. Tuy nhiên không đưa secret thực vào response HTTP hoặc log trong ứng dụng production.

## 5. Ví dụ: wrapped SecretID, RoleID provided

Tình huống thường gặp: provisioner chuyển một **wrapping token** thay cho SecretID thô. CLI phía provisioner:

~~~bash
vault write -wrap-ttl=60s -f \
    auth/approle/role/order-api/secret-id
~~~

Kết quả chứa `wrapping_token` có TTL ngắn. Broker chuyển token này riêng cho **một instance** qua kênh tin cậy. Tại Java, thay phần options của ví dụ trước:

~~~java
import org.springframework.vault.authentication.AppRoleAuthenticationOptions;
import org.springframework.vault.authentication.AppRoleAuthenticationOptions.RoleId;
import org.springframework.vault.authentication.AppRoleAuthenticationOptions.SecretId;
import org.springframework.vault.authentication.VaultToken;

AppRoleAuthenticationOptions options =
        AppRoleAuthenticationOptions.builder()
                .path("approle")
                .roleId(RoleId.provided(requiredEnv("VAULT_ROLE_ID")))
                .secretId(SecretId.wrapped(
                        VaultToken.of(requiredEnv("VAULT_WRAPPED_SECRET_ID_TOKEN"))))
                .build();
~~~

**Luồng request thực tế:** Spring Vault dùng wrapping token gọi API unwrap, đọc trường `secret_id` từ payload, sau đó gửi login AppRole. Wrapping token không phải token chính được gắn vào `VaultTemplate` để đọc KV.

Các hệ quả cần thiết kế:

- Wrapping token chỉ unwrap được **một lần** trong khoảng TTL. Một lần login/khởi tạo lại dùng chính wrapping token đã unwrap có thể thất bại; chỉ retry an toàn khi có cơ chế cấp credential mới.
- Nếu SecretID được cấu hình `secret_id_num_uses=1`, nó chỉ cho phép một lần login. Token đang hoạt động có thể tiếp tục dùng đến khi hết hạn, nhưng các lần login mới đòi hỏi credential mới.
- Unwrap bị từ chối không thể giải quyết bằng cách tăng TTL của Vault client token. Đó là hai credential khác nhau.
- Không log payload unwrap và không truyền wrapping token dưới dạng tham số dòng lệnh trên môi trường có người khác quan sát tiến trình.

`RoleId.wrapped(VaultToken)` cũng được hỗ trợ, nhưng nếu muốn wrap cả RoleID lẫn SecretID thì phải thiết kế phân phối và unwrap phù hợp. Không đưa **một wrapping token dùng một lần** vào hai lệnh unwrap độc lập với kỳ vọng cả hai đều thành công.

## 6. Ví dụ: full pull mode dùng bootstrap token

Spring Vault cho phép dùng một **initial token** để chủ động lấy RoleID và tạo SecretID từ Vault, rồi mới gọi AppRole login.

~~~java
import org.springframework.vault.authentication.AppRoleAuthenticationOptions;
import org.springframework.vault.authentication.AppRoleAuthenticationOptions.RoleId;
import org.springframework.vault.authentication.AppRoleAuthenticationOptions.SecretId;
import org.springframework.vault.authentication.VaultToken;

VaultToken initialToken = VaultToken.of(
        requiredEnv("VAULT_APPROLE_BOOTSTRAP_TOKEN"));

AppRoleAuthenticationOptions options =
        AppRoleAuthenticationOptions.builder()
                .path("approle")
                .appRole("order-api")
                .roleId(RoleId.pull(initialToken))
                .secretId(SecretId.pull(initialToken))
                .build();
~~~

Khi `AppRoleAuthentication.login()` chạy, quá trình bao gồm:

1. `GET /v1/auth/approle/role/order-api/role-id` với bootstrap token để lấy `role_id`.
2. `POST /v1/auth/approle/role/order-api/secret-id` với bootstrap token để xin SecretID mới.
3. `POST /v1/auth/approle/login` bằng RoleID/SecretID vừa lấy để nhận token **của workload**.
4. Session manager dùng token workload cho KV/Transit/PKI theo policy được cấp.

Về ACL, bootstrap token cần những quyền tương đương sau (đường dẫn phụ thuộc auth mount):

~~~hcl
# Policy dành cho bootstrap, KHÔNG phải policy đọc KV.
path "auth/approle/role/order-api/role-id" {
  capabilities = ["read"]
}

path "auth/approle/role/order-api/secret-id" {
  capabilities = ["update"]
}
~~~

Tách token bootstrap với token workload. Token dùng lấy RoleID/SecretID **được quyền tạo credential đăng nhập** và vì vậy phải được kiểm soát mạnh: TTL ngắn, giới hạn theo role, phân phối tin cậy và audit đầy đủ. Nhiều hệ thống sẽ thích cấp SecretID sẵn qua broker/wrapped mode hơn là đưa quyền tạo SecretID vào ứng dụng.

Có thể dùng hỗn hợp, ví dụ `RoleId.provided(...)` cùng `SecretId.pull(initialToken)`. Khi pull một trong hai giá trị, vẫn cần `appRole("order-api")` để xây dựng endpoint tương ứng. `AppRoleAuthenticationOptions` là nơi diễn đạt tổ hợp này.

## 7. Ví dụ đặc biệt: không gửi SecretID

`SecretId.absent()` yêu cầu Spring Vault bỏ trường `secret_id` khỏi JSON login:

~~~java
AppRoleAuthenticationOptions options =
        AppRoleAuthenticationOptions.builder()
                .path("approle")
                .roleId(RoleId.provided(requiredEnv("VAULT_ROLE_ID")))
                .secretId(SecretId.absent())
                .build();
~~~

Chỉ cấu hình này khi Vault role đặt `bind_secret_id=false` và có các biện pháp ràng buộc thích hợp (như CIDR và kiểm soát network). Trong AppRole điển hình, **giữ `bind_secret_id=true`**. Không có SecretID làm giảm một lớp bảo vệ; RoleID không nên được coi là đủ an toàn cho mọi môi trường.

Không dùng `SecretId.absent()` chỉ để “sửa” lỗi `permission denied`. Nếu Vault đang yêu cầu SecretID, đăng nhập như vậy sẽ thất bại. Tương tự, provided SecretID bị hết TTL hoặc vượt số lượt cũng phải được cấp lại; options không sửa được trạng thái đó trên Vault.

## 8. SessionManager, vòng đời token và hệ quả của credential một lần

### 8.1. Hai vòng đời tách biệt

Hãy phân biệt:

| Đối tượng | Sinh ra khi nào? | Hết hạn do đâu? | Ai quản lý? |
| --- | --- | --- | --- |
| **RoleID** | Khi Vault tạo/cập nhật định danh của role | Đổi hoặc hủy role, thay RoleID | Vault/provisioner |
| **SecretID** | Khi được Vault phát hoặc push | `secret_id_ttl`, `secret_id_num_uses`, bị hủy, sai CIDR | Vault/provisioner và cơ chế phân phối |
| **Wrapping token** | Khi response được wrap | TTL ngắn hoặc đã unwrap một lần | Vault và bên nhận |
| **Client token** | Khi AppRole login thành công | TTL, explicit max TTL, giới hạn lượt dùng, thu hồi hoặc điều kiện khác | Vault và `SessionManager` |

Ví dụ SecretID cho phép **một lần login** nhưng token workload có `token_ttl=20m` và `renewable=true`. Ứng dụng có thể tiếp tục sử dụng/renew token đó trong thời hạn được Vault cho phép mà không cần mỗi lần đọc KV lại sử dụng SecretID. Khi token không còn renew được, phiên phải được tạo lại qua login. Nếu SecretID đã dùng hết và không có credential mới, login lại sẽ thất bại.

### 8.2. `LifecycleAwareSessionManager` giúp gì?

Cấu hình `AbstractVaultConfiguration` tiêu chuẩn tạo `SessionManager` phù hợp, thông thường là `LifecycleAwareSessionManager`. Thành phần này có thể lên lịch gia hạn token khi Vault cho phép và quản lý session trong quá trình ứng dụng hoạt động.

Tuy nhiên, nó **không tự quay vòng SecretID** và **không tạo mới wrapping token**. `AppRoleAuthenticationOptions` chứa các thông số cần thiết cho lần login tiếp theo; nếu đó là giá trị `SecretId.provided` đã hết lượt hoặc `SecretId.wrapped` với token đã unwrap thì lần đăng nhập mới có thể thất bại.

Với service dài hạn, cần thiết kế đường đi thay credential trước khi làm mất khả năng đăng nhập lại. Không giả định token renewal chạy mãi: TTL, token type, explicit max TTL, policy và vận hành thực tế của Vault đều có thể ngăn gia hạn.

### 8.3. Không gọi `login()` ở mọi request

Một cách cài đặt không nên dùng:

~~~java
// Ví dụ phản diện: gọi login liên tục khi đọc mỗi secret.
VaultToken token = clientAuthentication.login();
// Gọi lại login() ở request kế tiếp có thể tiêu hao lượt dùng SecretID.
~~~

Thay vì tự đăng nhập mỗi lần, dùng `VaultTemplate`/`SessionManager` do Spring Vault quản lý, và kiểm tra login/renew bằng quan sát an toàn. Số lượt dùng của SecretID không đồng nghĩa số lượt gọi KV bằng token đã được cấp.

## 9. Tích hợp với Spring Cloud Vault: phân biệt rõ API

Nếu ứng dụng dùng **Spring Cloud Vault** thì có thể khai báo AppRole qua cấu hình framework, chẳng hạn:

~~~yaml
spring:
  cloud:
    vault:
      uri: https://vault.example.internal:8200
      authentication: APPROLE
      app-role:
        app-role-path: approle
        role-id: ${VAULT_ROLE_ID}
        secret-id: ${VAULT_SECRET_ID}
~~~

Trong cấu hình này, giá trị được lấy từ biến môi trường khi Spring xử lý placeholder; hệ thống triển khai phải cung cấp hai biến một cách an toàn. Đây là **đường tích hợp Spring Cloud Vault**; các property trên không tự hoạt động nếu classpath chỉ có `spring-vault-core`. Tùy phiên bản và cách bootstrap của Spring Cloud Vault, cơ chế tải cấu hình và thời điểm đăng nhập cũng khác.

Khi chọn **Spring Vault Core với `AbstractVaultConfiguration`**, bạn chủ động tạo `AppRoleAuthenticationOptions` như các ví dụ Java. Khi chọn **Spring Cloud Vault**, nên tuân theo property và cơ chế auto-configuration đúng phiên bản đang dùng, tránh khai báo chồng hai `ClientAuthentication` không mong muốn.

## 10. Lỗi thường gặp và cách xác định đúng tầng

| Hiện tượng | Tầng lỗi có khả năng | Nên kiểm tra |
| --- | --- | --- |
| Lỗi khi `build()` options hoặc khi tạo bean | Cấu hình ứng dụng | Thiếu RoleID, sai tổ hợp pull/`appRole`, biến môi trường rỗng, sai URL |
| `404` hoặc lỗi mount khi login | Đường dẫn Vault auth | `path("approle")` có đúng mount không? Có viết thừa `auth/` không? |
| `400`/`403` khi login | RoleID, SecretID hoặc role constraints | `bind_secret_id`, TTL/số lượt SecretID, CIDR, role đã tồn tại |
| Không lấy được RoleID ở pull mode | Bootstrap token/role path | Có `appRole` đúng tên? Bootstrap policy có quyền `read` role-id? |
| Không lấy được SecretID ở pull mode | Bootstrap token/role path | Bootstrap policy có `update` trên role secret-id endpoint? |
| Unwrap lỗi hoặc payload thiếu `secret_id` | Response wrapping | Wrapping token đã dùng/hết TTL? Có wrap đúng response sinh SecretID không? |
| Login được nhưng đọc KV `403` | Policy/CIDR của **token** | `token_policies`, mount KV2 và path `secret/data/...`, token bound CIDR |
| Chạy được lúc đầu, restart thì lỗi | Vòng đời credential | SecretID đã hết lượt; token bọc đã unwrap; phải cấp mới |
| Đang chạy thì đọc secret thất bại | Phiên token / kết nối | Token hết TTL/không renew, token type, policy thay đổi, TLS hoặc mạng |

Cách xác định nguyên nhân theo thứ tự:

1. Kiểm tra **một cách an toàn** URL, TLS, mount auth và endpoint: `/v1/auth/<path>/login`.
2. Xác định options đang là `provided`, `pull`, `wrapped` hay `absent`; nếu pull kiểm tra `appRole` và policy của bootstrap token.
3. Xác định lỗi phát sinh **trước login (pull/unwrap)** hay **tại login**.
4. Khi đã login thành công, phân tích token TTL/policies/CIDR và endpoint mà `VaultTemplate` đang gọi. Với KV v2, URL API khác với logical path.
5. Dùng audit logs/metric Vault và trace của ứng dụng đã loại bỏ bí mật. Chỉ ghi mã lỗi, loại thao tác, endpoint ở mức phù hợp và correlation ID; không log SecretID, wrapping token, client token hoặc dữ liệu bí mật.

Không suy đoán `permission denied` của lệnh đọc KV đồng nghĩa SecretID sai. Nếu đã có token, khả năng cao cần kiểm tra **authorization** hoặc token validity.

## 11. Thiết kế kiểm thử tích hợp

Một bài kiểm chứng tối thiểu có thể chuẩn bị Vault dev/test riêng hoặc Testcontainers với Vault, tạo role, policy và secret giả trước khi chạy test. Cần xác nhận cả đường đi thành công và giới hạn lỗi.

| Tình huống | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| **Provided thành công** | RoleID/SecretID hợp lệ, policy `read` đúng KV path | `VaultTemplate` đọc đúng `greeting` |
| **SecretID sai** | Đổi một ký tự trong SecretID | Không cấp được token |
| **Mount path sai** | `path("other-approle")` không tồn tại | Login lỗi endpoint, không đọc được KV |
| **Policy thiếu** | Token chỉ có policy không cho phép đọc secret đó | Login được nhưng KV trả `403` |
| **SecretID một lần dùng** | `secret_id_num_uses=1`, gọi login hai lần độc lập | Lần đầu thành công, lần sau thất bại |
| **Wrapping token đã dùng** | Unwrap trước khi Java dùng, hoặc thử unwrap hai lần | Lần dùng sau không lấy được SecretID |
| **Pull thiếu ACL** | Bootstrap token thiếu `update` trên secret-id endpoint | Lỗi ở bước phát SecretID trước login |
| **TTL/restart** | Credential ngắn hạn, restart khi SecretID hết hạn | Yêu cầu cấp credential mới được kích hoạt |

Đừng viết test kiểu chỉ assert builder không null; test hữu ích phải kiểm chứng request thực hoặc hành vi thực của Vault. Khi test CIDR cần môi trường mạng tái hiện được **địa chỉ nguồn mà Vault nhìn thấy**; cùng một container network/localhost có thể không kiểm chứng đúng giả định production.

### Quan sát an toàn trong vận hành

Theo dõi tỷ lệ login thành công/thất bại, lỗi phát SecretID, lỗi unwrap, token renewal failure và độ trễ gọi Vault. Giữ metric/tag ở mức không chứa credential. Hạn chế quyền đọc audit logs và xoay vòng credential nếu nghi bị tiết lộ.

Đối với service dùng Transit encryption hay PKI thay vì KV, cấu hình AppRole client ở đây vẫn có thể dùng lại. Chỉ thay đổi **policy Vault và thao tác `VaultTemplate`** cho secrets engine tương ứng; không cần phát triển phương thức xác thực mới.

## 12. Bài tập củng cố và tiêu chí đạt

1. Tạo AppRole `order-api` với policy chỉ đọc `secret/data/apps/order-api`, cung cấp RoleID/SecretID cho `OrderVaultConfig` và kiểm chứng `loadGreeting()`.
2. Đổi mount auth method thành `team-approle`, điều chỉnh `path(...)` và giải thích vì sao `appRole("order-api")` không thay thế được `path`.
3. Chuyển từ `SecretId.provided(...)` sang `SecretId.wrapped(...)`; chạy lại với wrapping token cũ, ghi nhận và giải thích lỗi.
4. Thử full pull mode bằng bootstrap token policy tối thiểu; bỏ quyền `update` trên endpoint secret-id để xác minh lý do fail.
5. Đặt `secret_id_num_uses=1`; giải thích vì sao app đọc KV nhiều lần bằng session token có thể vẫn hoạt động, nhưng lần AppRole login mới thất bại.

**Hoàn thành khi:** người học phân biệt được options và authentication, cấu hình được ba cơ chế provided/wrapped/pull, dùng `VaultTemplate` đọc một KV secret với quyền tối thiểu, phân loại lỗi auth với authorization, và giải thích vòng đời độc lập của SecretID với Vault token. Không lưu hoặc ghi log credential thật.

## Tài liệu tham khảo

- [Spring Vault 4.1 — Authentication Methods / AppRole](https://docs.spring.io/spring-vault/reference/vault/authentication.html)
- [Spring Vault API — AppRoleAuthentication](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AppRoleAuthentication.html)
- [Spring Vault API — AppRoleAuthenticationOptions](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AppRoleAuthenticationOptions.html)
- [Spring Vault API — AppRoleAuthenticationOptions.Builder](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AppRoleAuthenticationOptions.AppRoleAuthenticationOptionsBuilder.html)
- [Spring Vault API — AbstractVaultConfiguration](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/config/AbstractVaultConfiguration.html)
- [HashiCorp Vault — AppRole authentication](https://developer.hashicorp.com/vault/docs/auth/approle)
- [HashiCorp Vault — AppRole API](https://developer.hashicorp.com/vault/api-docs/auth/approle)
- [HashiCorp Vault — Response wrapping](https://developer.hashicorp.com/vault/docs/concepts/response-wrapping)
- [Spring Cloud Vault — Authentication (phân biệt cách tích hợp)](https://docs.spring.io/spring-cloud-vault/reference/authentication.html)

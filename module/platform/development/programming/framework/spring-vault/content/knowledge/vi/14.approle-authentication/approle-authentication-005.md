# SecretId được response-wrap và bước unwrap

## 1. Mục tiêu và tình huống sử dụng

Trong chương **Xác thực AppRole** của **SPRING_VAULT**, ứng dụng Java thường cần hai thông tin để đăng nhập HashiCorp Vault: `RoleID` và `SecretID`. Chuyển SecretID thô qua CI/CD, hệ thống triển khai hoặc secret broker làm tăng nguy cơ vô tình để lộ credential trong log, output, backup và các tầng trung gian. **Response wrapping** là cơ chế Vault cho phép bên cấp phát chuyển **wrapping token** có thời hạn ngắn và dùng một lần thay cho chuyển trực tiếp SecretID.

Bài này tập trung vào việc tạo một **SecretID response-wrap**, kiểm tra và **unwrap** đúng cách, rồi dùng Spring Vault để tự unwrap khi xác thực:

~~~java
AppRoleAuthenticationOptions options = AppRoleAuthenticationOptions.builder()
        .roleId(RoleId.provided(roleId))
        .secretId(SecretId.wrapped(VaultToken.of(wrappingToken)))
        .build();
~~~

Mục tiêu học tập:

- Phân biệt **RoleID**, **SecretID**, **wrapping token** và **AppRole client token**.
- Giải thích thứ tự: provisioner xin SecretID có response wrapping → workload nhận token bọc → kiểm tra nguồn gốc → unwrap → AppRole login → dùng `VaultTemplate`.
- Biết cách tạo wrapping token bằng Vault CLI hoặc yêu cầu HTTP với header `X-Vault-Wrap-TTL`.
- Biết kiểm tra `creation_path`, TTL, trạng thái token rồi unwrap qua `sys/wrapping/unwrap`.
- Cấu hình đúng `SecretId.wrapped(VaultToken)`, phân biệt với `SecretId.provided(String)` và `SecretId.pull(VaultToken)`.
- Hiểu vì sao wrapping token **không thể tái sử dụng**, cách cấp token mới cho restart/re-authentication và chẩn đoán lỗi.
- Thực hành đọc KV v2 qua `VaultTemplate` bằng token mang policy tối thiểu.

**Phạm vi:** Spring Vault Core phiên bản 4.1.x là tham chiếu cho ví dụ Java. Các lệnh Vault sử dụng môi trường **lab** được quản trị riêng. Production cần TLS được xác minh, kênh phân phối bảo vệ và chính sách riêng cho provisioner.

## 2. Response wrapping giải quyết vấn đề gì?

### 2.1. Không đưa SecretID thô qua các tầng trung gian

AppRole thường sử dụng `role_id` và `secret_id` ở endpoint `POST /v1/auth/approle/login`. RoleID là định danh role; SecretID là credential cần được bảo vệ. Khi provisioner xin SecretID theo cách thông thường, Vault trả `secret_id` trực tiếp trong response. Nếu provisioner chép dữ liệu đó vào CI output, biến môi trường dùng chung hoặc file build, một người ngoài ý muốn có thể nhìn thấy SecretID.

Với response wrapping, provisioner yêu cầu Vault **đóng gói response**. Vault lưu response ban đầu ở vùng riêng gắn với một token dùng một lần, rồi chỉ trả về **wrapping token** cùng metadata. Người nhận token có thể gọi unwrap để lấy response thật. Nhờ vậy, các tầng trung gian chỉ mang một credential có thời hạn ngắn và có thể phát hiện việc token bị tiêu thụ trước khi tới tay người nhận.

~~~mermaid
sequenceDiagram
    autonumber
    participant P as Provisioner
    participant V as Vault
    participant D as Kênh triển khai
    participant J as Java Spring Vault
    participant K as KV v2
    P->>V: POST auth/approle/role/billing-worker/secret-id
    Note over P,V: X-Vault-Wrap-TTL: 60s
    V-->>P: wrap_info.token, ttl, creation_path
    P->>D: Chuyển wrapping token
    D-->>J: Wrapping token + RoleID
    J->>V: POST sys/wrapping/unwrap
    Note over J,V: X-Vault-Token: wrapping token
    V-->>J: data.secret_id (token bọc bị tiêu thụ)
    J->>V: POST auth/approle/login (role_id, secret_id)
    V-->>J: AppRole client token + TTL + policies
    J->>K: Đọc secret bằng client token
    K-->>J: Dữ liệu nếu policy cho phép
~~~

Spring Vault có thể tự thực hiện bước unwrap khi bạn cấu hình `SecretId.wrapped(...)`. Nếu hệ thống cần **kiểm tra nguồn gốc trước khi unwrap**, nên kiểm tra wrapping token ở một lớp bootstrap/provisioning riêng, vì `SecretId.wrapped(...)` trực tiếp không thay thế toàn bộ quy trình kiểm chứng chính sách phát credential.

### 2.2. Bốn loại thông tin khác nhau

| Thứ được cấp | Ai nhận? | Được dùng làm gì? | Điều kiện hết hiệu lực |
| --- | --- | --- | --- |
| **RoleID** | Workload | Chọn AppRole khi login | Khi role/RoleID bị đổi hoặc xóa |
| **SecretID** | Workload sau unwrap | Đăng nhập AppRole cùng RoleID | TTL SecretID, số lần dùng, revoke, CIDR |
| **Wrapping token** | Workload trước unwrap | Đọc **một response** đã được Vault bọc | TTL wrapping token, unwrap một lần, revoke |
| **AppRole client token** | Workload sau login thành công | Đọc KV hoặc thao tác Transit/PKI theo policy | TTL token, giới hạn renewal, revoke, ACL/CIDR |

**Wrapping token không phải SecretID.** Truyền wrapping token vào `SecretId.provided(...)` sẽ khiến Vault coi nó là một SecretID sai khi login. Ngược lại, `SecretId.wrapped(...)` trông đợi một **wrapping token**, không phải chuỗi SecretID thô.

**Wrapping token cũng không phải client token của workload.** Sau unwrap, Spring Vault còn phải gọi AppRole login để nhận token riêng cho `VaultTemplate`.

### 2.3. Response wrapping không thay thế những gì?

Response wrapping **không** thay thế:

- TLS giữa client và Vault; nếu kết nối bị chuyển tới Vault giả, kiểm tra token cũng có thể bị đánh lừa.
- Policy cho quyền tạo SecretID: provisioner vẫn cần quyền `update` đúng endpoint AppRole.
- Policy cho token sau login: đọc KV v2 cần ACL trên đường dẫn dữ liệu.
- TTL, số lần dùng và rotation của chính SecretID: thời hạn wrapping token hoàn toàn độc lập.
- Kiểm soát đầu cuối về **ai nhận token bọc**: bất kỳ bên nào chiếm token còn hợp lệ có thể thử unwrap trước người nhận.

Cơ chế wrapping giúp hạn chế thời gian/phạm vi lộ credential và hỗ trợ **phát hiện dấu hiệu token bị dùng trước**, nhưng một lỗi unwrap không tự chứng minh rằng đã có hành vi tấn công; cũng có thể do TTL hết, mạng lỗi hoặc hệ thống khởi động chậm.

## 3. Bên trong wrapping token: TTL, Cubbyhole và creation_path

Khi request có header `X-Vault-Wrap-TTL`, Vault thực hiện về mặt logic:

1. Tạo response gốc (ở đây chứa `secret_id`).
2. Lưu response gốc trong Cubbyhole của một wrapping token mới có quyền dùng một lần.
3. Trả về metadata `wrap_info` chứa wrapping token, TTL, thời điểm phát và `creation_path`.
4. Khi người nhận unwrap, Vault đọc response được bọc, trả về dữ liệu gốc và khiến wrapping token không thể sử dụng lại.

Ví dụ metadata minh họa (không phải credential thật):

~~~json
{
  "wrap_info": {
    "token": "<WRAPPING_TOKEN>",
    "ttl": 60,
    "creation_time": "2026-11-25T08:00:00Z",
    "creation_path": "auth/approle/role/billing-worker/secret-id"
  }
}
~~~

Giải thích:

| Trường | Ý nghĩa thực tế |
| --- | --- |
| `wrap_info.token` | Token phải chuyển đến **duy nhất bên nhận**; cần bảo mật như credential ngắn hạn |
| `wrap_info.ttl` | Số giây token bọc còn hiệu lực tính từ lúc tạo |
| `wrap_info.creation_time` | Thời điểm phát wrapping token |
| `wrap_info.creation_path` | Endpoint gốc đã phát **response được bọc**, có thể dùng để xác minh nguồn |
| `wrapping_accessor` (CLI, nếu có) | Accessor của wrapping token, **không phải** SecretID accessor |
| `data.secret_id_accessor` (sau unwrap) | Accessor của SecretID thật, phục vụ các thao tác quản trị/thu hồi theo quyền |

**Điểm bảo mật quan trọng:** cần xác minh `creation_path` **khớp chính xác** `auth/approle/role/billing-worker/secret-id`. Nếu nhận wrapping token bọc dữ liệu từ `sys/wrapping/wrap` hay role khác, không coi đó là SecretID đúng chỉ vì token còn hiệu lực.

Vault không phát một chữ ký độc lập lên wrapping token để bạn xác minh offline. Tính xác thực của metadata đến từ việc trao đổi với **đúng Vault server qua TLS tin cậy**.

## 4. Ba TTL không được nhầm

Ví dụ AppRole được cấu hình:

~~~text
wrap-ttl                = 60s    # yêu cầu riêng của request phát SecretID
secret_id_ttl           = 10m    # giới hạn trên AppRole
secret_id_num_uses      = 1      # mỗi SecretID chỉ login được một lần
token_ttl               = 30m    # TTL khởi tạo client token
token_max_ttl           = 2h     # giới hạn gia hạn tùy cấu hình Vault
~~~

| Thời hạn | Bắt đầu từ đâu? | Hết hạn sẽ gây lỗi gì? |
| --- | --- | --- |
| **Wrapping TTL (60 giây)** | Khi response được wrap | Không thể unwrap response sau thời hạn/đã dùng |
| **SecretID TTL (10 phút)** | Khi Vault **tạo SecretID**, không chờ unwrap | Dù đã unwrap thành công, SecretID hết hạn vẫn không login được |
| **Client token TTL (30 phút)** | Khi AppRole login thành công | Request đọc KV thất bại nếu token hết hạn và không được gia hạn/tạo phiên mới |

Hai tình huống đáng nhớ:

- Wrapping token có thể hết hạn **trước khi** ứng dụng nhận được nó. SecretID phía Vault vẫn có thể đang tồn tại, nhưng người nhận không thể mở response đã bị mất quyền truy cập. Hãy **cấp mới một SecretID và bọc lại response mới**, không kéo dài hoặc tái sử dụng token bọc hết hạn.
- Wrapping token có thể được unwrap thành công nhưng SecretID đã bị thu hồi hoặc quá TTL. Unwrap chỉ chứng minh bạn truy xuất response được bọc; **không bảo đảm AppRole login thành công**.

Cũng có thể wrapping token còn TTL nhưng đã bị unwrap một lần; nó không hợp lệ ngay sau khi bị tiêu thụ. Đừng tăng `wrap-ttl` để giải quyết lỗi `secret_id_num_uses`: đây là hai giới hạn riêng.

## 5. Thực hành Vault: cấp SecretID có response wrapping

### 5.1. Chuẩn bị Vault và KV v2 trong môi trường lab

Giả sử có token quản trị đủ quyền cấu hình Vault, CLI được đăng nhập và Vault chạy local.

~~~bash
export VAULT_ADDR="http://127.0.0.1:8200"

# Chỉ chạy nếu auth method chưa có ở mount auth/approle.
vault auth enable approle

# Chỉ chạy nếu mount secret/ chưa tồn tại.
vault secrets enable -path=secret -version=2 kv

# Dữ liệu giả cho bài tập.
vault kv put secret/apps/billing-worker feature="ready"
~~~

Nếu mount đã tồn tại, bỏ qua lệnh enable tương ứng; không tạo thêm mount trùng hoặc ghi đè cấu hình đang dùng. HTTP chỉ dành cho lab local; production dùng HTTPS/TLS với CA tin cậy.

### 5.2. Policy nghiệp vụ và AppRole

Tạo file `billing-worker-read.hcl` trên máy quản trị:

~~~hcl
path "secret/data/apps/billing-worker" {
  capabilities = ["read"]
}
~~~

Cấu hình:

~~~bash
vault policy write billing-worker-read billing-worker-read.hcl

vault write auth/approle/role/billing-worker \
    bind_secret_id=true \
    secret_id_ttl=10m \
    secret_id_num_uses=1 \
    token_policies="billing-worker-read" \
    token_ttl=30m \
    token_max_ttl=2h \
    token_type=service \
    token_num_uses=0

vault read auth/approle/role/billing-worker
~~~

`secret_id_num_uses=1` phù hợp cho minh họa cấp một credential theo từng lần login. Với service cần tự login lại, bên triển khai phải cấp **SecretID mới và wrapping token mới**, bởi SecretID cũ không còn lượt đăng nhập.

`token_num_uses=0` là số lượt của **client token** được cấp sau login; không đồng nghĩa SecretID không giới hạn lượt.

### 5.3. Policy riêng cho provisioner

Một thành phần cấp credential chỉ cần quyền tạo SecretID ở đúng AppRole; nếu cũng phải chuyển RoleID thì thêm quyền đọc RoleID:

~~~hcl
# billing-worker-provisioner.hcl
path "auth/approle/role/billing-worker/secret-id" {
  capabilities = ["update"]
}

path "auth/approle/role/billing-worker/role-id" {
  capabilities = ["read"]
}
~~~

Nạp policy:

~~~bash
vault policy write billing-worker-provisioner \
    billing-worker-provisioner.hcl
~~~

**Workload Java không cần các quyền trên.** Nó nhận RoleID và wrapping token rồi unwrap, login. Provisioner nên có token chỉ mang policy này và không đọc KV nghiệp vụ.

Ở môi trường có yêu cầu kiểm soát chặt việc wrapping, quản trị viên có thể dùng ràng buộc `min_wrapping_ttl`/`max_wrapping_ttl` của Vault policy để buộc hoặc giới hạn TTL wrapping trên endpoint cấp SecretID. Việc áp dụng tùy vào chính sách tổ chức; không đặt các giới hạn không tương thích với thời gian triển khai.

### 5.4. Sinh SecretID và yêu cầu Vault wrap response

Trong phiên của provisioner:

~~~bash
# Vault trả về wrapping token, không in SecretID trực tiếp.
vault write -wrap-ttl=60s -f \
    auth/approle/role/billing-worker/secret-id
~~~

CLI sẽ hiển thị các trường tương tự:

~~~text
wrapping_token:               <WRAPPING_TOKEN>
wrapping_accessor:            <WRAPPING_ACCESSOR>
wrapping_token_ttl:           1m
wrapping_token_creation_path: auth/approle/role/billing-worker/secret-id
~~~

Provisioner **chuyển `wrapping_token`**, không chuyển `wrapping_accessor`, cho một instance của ứng dụng. Vai trò của accessor là hỗ trợ quản trị wrapper, không phải để unwrap.

Để hiểu cơ chế HTTP, yêu cầu tương đương về ý tưởng:

~~~http
POST /v1/auth/approle/role/billing-worker/secret-id HTTP/1.1
X-Vault-Token: <PROVISIONER_TOKEN>
X-Vault-Wrap-TTL: 60s
Content-Type: application/json

{}
~~~

Phía provisioner phải gọi đúng auth mount và đúng role; wrapping token mới tồn tại từ **thời điểm Vault xử lý request**, không tính từ lúc CI bắt đầu triển khai ứng dụng.

**Không ghi wrapping token thật vào CI console, artifact, ticket hoặc command line**. Ví dụ terminal ở đây chỉ để quan sát luồng trong môi trường lab được kiểm soát; trong production, hệ thống triển khai nên truyền credential qua secret injection hoặc một kênh bảo vệ khác.

### 5.5. RoleID được lấy và phân phối riêng

RoleID có thể được provisioner đọc từ endpoint:

~~~bash
vault read -field=role_id \
    auth/approle/role/billing-worker/role-id
~~~

Ứng dụng cần **RoleID** và **wrapping token cho SecretID**. RoleID thường tồn tại ổn định cho role, nhưng vẫn cần được kiểm soát truy cập. Không nhầm RoleID, tên role `billing-worker` và wrapping token. Trong cách cấu hình này, Java không cần `appRole("billing-worker")` chỉ để login vì RoleID đã có và SecretID được unwrap trực tiếp từ token bọc.

## 6. Kiểm tra token trước khi unwrap

HashiCorp khuyến nghị người nhận xác thực nguồn gốc response bọc, nhất là trong luồng có nhiều bên trung gian.

### 6.1. Tra cứu metadata mà không làm mất lượt unwrap

Vault có endpoint `POST /v1/sys/wrapping/lookup`. Ví dụ request logic:

~~~http
POST /v1/sys/wrapping/lookup HTTP/1.1
Content-Type: application/json

{
  "token": "<WRAPPING_TOKEN>"
}
~~~

Theo đặc tả HTTP API, trường `token` trong request body xác định wrapping token cần tra cứu; endpoint trả metadata của token mà không trả SecretID. Đây là một request minh họa, không đưa token thật vào tài liệu/log. Khi kiểm tra cần:

1. Metadata lookup **còn hợp lệ**; không bị báo không tìm thấy, đã hết TTL hay đã bị tiêu thụ.
2. `creation_path` bằng chính xác `auth/approle/role/billing-worker/secret-id`.
3. TTL còn đủ cho thao tác unwrap ngay sau đó.
4. Vault server và TLS certificate đúng endpoint mà workload tin cậy.

`lookup` tự nó **không tiêu thụ** wrapping token. Đây là bước thích hợp để kiểm tra đường dẫn và tuổi token trước khi giao việc unwrap cho Spring Vault.

Nếu có thể, provisioner/ứng dụng cũng kiểm tra **token đã được phát như dự kiến vào thời điểm phù hợp**. Token còn hợp lệ không tự chứng minh nó đến từ bên triển khai đúng: kiểm tra `creation_path` và kênh trao đổi vẫn là yêu cầu quan trọng.

### 6.2. Khi lookup không hợp lệ

Token không tìm thấy có thể do TTL đã hết, token bị revoke, token đã được unwrap bởi tiến trình khác hoặc do nhầm Vault namespace/server. Không thử bỏ kiểm tra rồi gọi login bằng chuỗi wrapping token như SecretID. Nên **dừng bootstrap, cảnh báo và điều tra audit logs**. Bên phát có thể thu hồi credential liên quan nếu có dấu hiệu lộ và cấp mới credential cho lần triển khai khác.

Lỗi lookup **không đủ** để kết luận có kẻ tấn công; cần xem lại latency của pipeline, thời điểm tạo token, mạng, Vault namespace và audit events.

## 7. Unwrap: lấy response gốc đúng một lần

### 7.1. Endpoint `sys/wrapping/unwrap`

Sau khi xác minh metadata, người nhận gọi:

~~~http
POST /v1/sys/wrapping/unwrap HTTP/1.1
X-Vault-Token: <WRAPPING_TOKEN>
Content-Type: application/json

{}
~~~

Đây là cách dùng **wrapping token làm token xác thực của request**. Vault còn hỗ trợ trường hợp client dùng một token khác có quyền unwrap và cung cấp wrapping token trong body. **Không đặt cùng một wrapping token ở cả header và body**: điều đó có thể khiến token bị tính là dùng hai lần, không lấy được response.

Response thành công có cấu trúc chứa SecretID, ví dụ:

~~~json
{
  "data": {
    "secret_id": "<SECRET_ID_THAT>",
    "secret_id_accessor": "<SECRET_ID_ACCESSOR>",
    "secret_id_ttl": 600,
    "secret_id_num_uses": 1
  }
}
~~~

Dữ liệu SecretID thô chỉ xuất hiện ở **bên nhận** sau khi unwrap. Không ghi response thật vào log. Lưu ý `secret_id_accessor` khác hoàn toàn `wrapping_accessor`.

Endpoint `sys/wrapping/unwrap` là cách làm hiện đại được Vault khuyến nghị; cách đọc trực tiếp `cubbyhole/response` là legacy và không cung cấp cùng mức kiểm tra, audit như endpoint unwrap mới.

### 7.2. Thử unwrap bằng Vault CLI trong lab

Chỉ dùng token thử nghiệm trong một phiên shell kín:

~~~bash
# Dùng wrapping token được provisioner phát trong lab.
# Người thực hành thiết lập VAULT_TOKEN trong session bảo vệ trước khi chạy.
vault unwrap
~~~

Nếu CLI đang dùng `VAULT_TOKEN` là wrapping token, `vault unwrap` sẽ lấy dữ liệu và tiêu thụ token đó. Một lần `vault unwrap` nữa với chính token ấy **phải thất bại**; muốn thử lại phải **tạo SecretID mới kèm wrapping token mới**.

> **Quan trọng:** bài này có hai cách thực hành loại trừ nhau trên cùng wrapping token:
>
> - **Thử CLI thủ công:** người học unwrap và quan sát phản hồi trong lab. Token đó **không được đưa lại cho Spring Vault**.
> - **Thử Java tự động:** người học đưa wrapping token còn nguyên vẹn vào `SecretId.wrapped(...)`, để **Spring Vault unwrap lần đầu**. Không chạy CLI unwrap trước khi Java khởi động.

Dùng chung một wrapping token cho cả bài test CLI và Java sẽ khiến một trong hai phía thất bại do token đã được dùng.

### 7.3. Unwrap khác với AppRole login

Sau khi unwrap, Spring Vault phải gửi:

~~~http
POST /v1/auth/approle/login HTTP/1.1
Content-Type: application/json

{
  "role_id": "<ROLE_ID>",
  "secret_id": "<SECRET_ID_THAT>"
}
~~~

Vault kiểm tra SecretID còn TTL/lượt dùng, có thuộc đúng RoleID/role, và các ràng buộc role (ví dụ CIDR). Chỉ sau khi login thành công Vault mới trả `auth.client_token`. Token này có policy/TTL dành cho các lệnh đọc KV hoặc gọi Transit/PKI.

Do đó **unwrap thành công ≠ AppRole login thành công ≠ đọc KV được phép**. Đây là ba lần kiểm tra khác nhau.

## 8. Spring Vault: tự unwrap bằng `SecretId.wrapped`

### 8.1. Cấu hình `ClientAuthentication`

Ví dụ với **Spring Vault 4.1.x** dùng `AbstractVaultConfiguration`. Runtime cần cung cấp `VAULT_ADDR`, `VAULT_ROLE_ID` và `VAULT_SECRET_ID_WRAPPING_TOKEN` trước khi Spring tạo bean.

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
public class WrappedSecretIdVaultConfiguration
        extends AbstractVaultConfiguration {

    @Override
    public VaultEndpoint vaultEndpoint() {
        return VaultEndpoint.from(URI.create(requiredEnv("VAULT_ADDR")));
    }

    @Override
    public ClientAuthentication clientAuthentication() {
        String roleId = requiredEnv("VAULT_ROLE_ID");
        String wrappingToken = requiredEnv("VAULT_SECRET_ID_WRAPPING_TOKEN");

        AppRoleAuthenticationOptions options =
                AppRoleAuthenticationOptions.builder()
                        .path("approle")
                        .roleId(RoleId.provided(roleId))
                        .secretId(SecretId.wrapped(
                                VaultToken.of(wrappingToken)))
                        .unwrappingEndpoints(UnwrappingEndpoints.SysWrapping)
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

Các điểm cần hiểu:

- `RoleId.provided(roleId)` dùng RoleID đã được provisioner cấp, không có request pull RoleID.
- `SecretId.wrapped(VaultToken.of(wrappingToken))` chỉ định **nguồn SecretID là một response đang được wrap**. Spring Vault dùng wrapping token để gọi endpoint unwrap, trích `data.secret_id` rồi login AppRole.
- `UnwrappingEndpoints.SysWrapping` sử dụng `sys/wrapping/unwrap` của Vault hiện đại. Không cần tùy chỉnh nếu cấu hình phiên bản Spring Vault đã chọn sẵn endpoint phù hợp, nhưng khai báo tường minh giúp minh họa cơ chế. `UnwrappingEndpoints.Cubbyhole` chỉ dành cho tương thích rất cũ.
- `path("approle")` là auth **mount path** cho AppRole login, không phải đường dẫn endpoint unwrap. Nếu auth mount khác, sửa mount path; endpoint unwrap vẫn là `sys/wrapping/unwrap`.
- `AppRoleAuthentication` implement `ClientAuthentication`. Spring Vault `SessionManager` quản lý token cho các lệnh gọi của `VaultTemplate`.
- Trong bản tham chiếu 4.1.x, constructor nhận `vaultClient()`. Với một số phiên bản cũ, `AppRoleAuthentication` có constructor nhận `RestOperations`; cần kiểm tra API dự án.

**Đừng truyền SecretID thô vào `VaultToken.of(...)` ở cấu hình này.** Nó phải là wrapping token được Vault phát cho response của SecretID. Nếu đã unwrap thủ công thì phải chuyển sang `SecretId.provided(secretId)`, đồng thời chịu trách nhiệm bảo vệ chuỗi SecretID thô.

### 8.2. Điều gì xảy ra ở lần đăng nhập?

Phần xử lý của Spring Vault về mặt ý tưởng:

~~~mermaid
flowchart TD
    A["VaultTemplate cần token"] --> B["SessionManager gọi ClientAuthentication"]
    B --> C["Spring Vault POST sys/wrapping/unwrap"]
    C --> D{"Wrapping token hợp lệ?"}
    D -- "Không" --> E["VaultLoginException / lỗi unwrap"]
    D -- "Có" --> F["Lấy SecretID từ response"]
    F --> G["POST auth/approle/login"]
    G --> H{"RoleID + SecretID hợp lệ?"}
    H -- "Không" --> I["Lỗi AppRole login"]
    H -- "Có" --> J["Nhận client token và policy"]
    J --> K["VaultTemplate dùng token để đọc KV"]
~~~

Bước unwrap là thao tác thật tới Vault, **không diễn ra tại thời điểm `.build()` chỉ tạo options**. Tùy phiên bản/cách khởi tạo session manager, nó có thể diễn ra lúc lấy token lần đầu. Nếu mạng mất kết nối ở giai đoạn bất kỳ, cần xác định token bọc đã được Vault tiêu thụ hay chưa **trước khi retry**.

### 8.3. Dùng `VaultTemplate` truy cập KV v2

~~~java
package example.vault;

import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.VaultResponse;

@Service
public class BillingWorkerSecrets {

    private final VaultTemplate vaultTemplate;

    public BillingWorkerSecrets(VaultTemplate vaultTemplate) {
        this.vaultTemplate = vaultTemplate;
    }

    public String feature() {
        VaultResponse result = vaultTemplate
                .opsForKeyValue("secret", KeyValueBackend.KV_2)
                .get("apps/billing-worker");

        if (result == null) {
            throw new IllegalStateException("Vault secret not found");
        }

        Map<String, Object> data = result.getRequiredData();
        Object value = data.get("feature");

        if (!(value instanceof String)) {
            throw new IllegalStateException("Invalid feature field");
        }

        return (String) value;
    }
}
~~~

Dữ liệu lab `feature="ready"` sẽ trả `ready` nếu token mới có quyền đọc `secret/data/apps/billing-worker`. Không đưa secret thật vào log hoặc HTTP response của service production.

**Chú ý KV v2:** logical path của `VaultTemplate` là `apps/billing-worker` dưới mount `secret`; ACL thực phải cấp `read` trên `secret/data/apps/billing-worker`.

## 9. Vòng đời token và vấn đề restart/re-authentication

### 9.1. Wrapping token đã unwrap không dùng lại được

Giả sử wrapping token `W1` có TTL 60 giây, chứa SecretID `S1` có TTL 10 phút, số lượt dùng 1. Một quy trình hợp lệ:

1. Provisioner tạo `S1` và nhận wrapping token `W1`.
2. Workload nhận `W1` trước khi hết hạn.
3. Spring Vault unwrap `W1`, nhận `S1`; ngay lúc này `W1` **không còn hợp lệ**.
4. Spring Vault login bằng `S1`, Vault cấp client token `T1`. `S1` cũng hết lượt login nếu `secret_id_num_uses=1`.
5. `T1` vẫn có thể đọc KV khi còn hiệu lực và đủ policy; việc `W1`/`S1` hết lượt **không làm `T1` hết hạn ngay**.
6. Khi `T1` không thể gia hạn và cần login lại, Spring Vault sẽ không thể unwrap lại `W1`. Instance cần **credential bootstrap mới**, thường là một `S2` được response-wrap thành `W2`.

Vì vậy cách cấu hình tĩnh `SecretId.wrapped(VaultToken.of(requiredEnv(...)))` rất phù hợp cho **bootstrap lần đầu**, nhưng **không tự giải quyết toàn bộ bài toán re-authentication dài hạn**.

### 9.2. SessionManager gia hạn cái gì?

`LifecycleAwareSessionManager` của Spring Vault có thể quản lý gia hạn **client token** nếu Vault phát token renewable và còn nằm trong giới hạn. Nó không gia hạn wrapping token và không tạo SecretID mới. Token không renewable hoặc vượt trần TTL cần một phiên xác thực mới.

Thay biến môi trường bên ngoài sau khi Spring đã tạo `AppRoleAuthenticationOptions` cũng **không tự đổi** wrapping token đã lưu trong object. Muốn cấp lại token bọc tại runtime phải thiết kế quy trình mới: khởi tạo lại client/session với credential mới, dùng một provider có cơ chế refresh, hoặc cho instance restart theo cách có điều phối. Không ép gọi `login()` mỗi request vì sẽ tiêu thụ wrapping token ở lần đầu rồi thất bại ngay sau đó.

### 9.3. Quy trình rotation phù hợp cho autoscaling

Với CI job hoặc instance container ngắn hạn:

- Provisioner phát **một SecretID mới** cho mỗi instance/job.
- Mỗi SecretID được wrap thành **một wrapping token mới** với TTL đủ cho độ trễ startup có kiểm soát.
- Inject RoleID và wrapping token vào đúng instance; không chia sẻ wrapping token cho nhiều replica.
- Workload kiểm tra nguồn gốc token trước khi unwrap, sau đó login và thực hiện công việc.
- Khi instance bị thay thế hoặc cần re-login, provisioner cấp cặp credential mới; token cũ được thu hồi/đánh giá theo chính sách sự cố.

Với service dài hạn, nên thiết kế vòng đời client token và quy trình bổ sung credential **trước khi** chọn TTL quá ngắn. Nếu nền tảng có Kubernetes Auth hoặc cloud IAM Auth đáng tin cậy, cân nhắc dùng trực tiếp danh tính workload thay vì tự tạo vòng phân phối wrapping token cho AppRole.

## 10. Bảng lỗi thường gặp

| Triệu chứng | Tầng phát sinh | Nguyên nhân có khả năng | Cách xử lý |
| --- | --- | --- | --- |
| Provisioner không lấy được wrapping token | Phát SecretID | Sai auth mount, thiếu ACL `update`, policy TTL wrapping không phù hợp | Kiểm tra đúng role/path và quyền provisioner |
| Wrapping token không đến được instance trước TTL | Phân phối | CI queue lâu, orchestration delay, lỗi mạng | Giảm độ trễ hoặc phát token mới đúng thời điểm triển khai |
| `sys/wrapping/lookup` báo invalid | Kiểm tra trước unwrap | Hết TTL, đã unwrap, đã revoke, khác Vault namespace | Dừng bootstrap, xem audit logs, cấp credential mới khi phù hợp |
| `creation_path` không trùng endpoint SecretID dự kiến | Kiểm tra nguồn gốc | Sai role hoặc response bị thay bằng dữ liệu bọc từ path khác | Từ chối token, báo sự cố nguồn cung cấp |
| `sys/wrapping/unwrap` thất bại ở lần gọi thứ hai | Unwrap | Token bọc đã dùng một lần | Cấp SecretID + wrapping token mới; không retry cùng token |
| Spring Vault báo không thấy `secret_id` trong data | Unwrap response | Bọc nhầm payload, sai endpoint hoặc format dữ liệu | Đảm bảo wrap **response của endpoint phát SecretID** |
| Unwrap được nhưng login trả 400/403 | AppRole login | SecretID không thuộc role, hết TTL/lượt dùng hoặc sai CIDR | Kiểm tra role constraints và vòng đời SecretID |
| Login thành công nhưng KV trả 403 | Authorization | Client token thiếu policy/path, hết hạn hoặc bound CIDR sai | Kiểm tra `token_policies` và KV v2 ACL path |
| Ứng dụng restart rồi không login được | Re-authentication | JVM nhận lại wrapping token cũ đã dùng | Mỗi restart phải có token bọc mới hoặc cơ chế cấp credential tương ứng |
| Nhiều replica, một replica thành công và phần còn lại thất bại | Phân phối | Các replica dùng chung một wrapping token | Phát token bọc riêng cho mỗi replica |
| Unwrap trả lỗi nhưng không rõ đã dùng token chưa | Mạng/timeout | Vault có thể đã xử lý request trước khi client timeout | Kiểm tra lookup/audit; không tự động unwrap lần nữa với cùng token |

Đừng nhầm lỗi `VaultLoginException` tại bước unwrap với lỗi phân quyền khi `VaultTemplate` truy cập KV. Mã `403` có thể xuất hiện ở cả hai tầng; cần xem request nào bị từ chối.

## 11. Giám sát và ứng phó khi nghi token bị lấy cắp

### 11.1. Chỉ ghi metadata vận hành

Một hệ thống production có thể theo dõi:

- Số wrapping token được phát, số token được unwrap thành công/thất bại, và độ trễ phát → unwrap.
- Tần suất token hết TTL trước khi đến ứng dụng; cảnh báo nếu vượt ngưỡng.
- `creation_path` không đúng kỳ vọng hoặc token không hợp lệ khi vừa giao cho instance.
- Số lần AppRole login thất bại theo role/môi trường, lỗi gia hạn client token và lỗi ACL đọc KV.
- Vault audit events cho endpoint `secret-id`, `sys/wrapping/lookup`, `sys/wrapping/unwrap` và `auth/approle/login`.

Không gắn `wrapping_token`, `secret_id`, `role_id` hoặc `client_token` vào metric label, exception, log payload hay trace attributes. Dùng request ID hoặc correlation ID không nhạy cảm để liên kết sự kiện. Audit log cũng cần giới hạn quyền truy cập và chính sách lưu giữ.

### 11.2. Nếu unwrap nghi có người thực hiện trước

Một quy trình phản ứng phù hợp:

1. **Dừng** instance dùng token đang nghi ngờ; tránh thử lại bằng cùng token.
2. Kiểm tra Vault audit logs, thời gian tạo wrapping token, `creation_path` và sự kiện unwrap thực tế.
3. Thu hồi SecretID tương ứng qua accessor nếu có khả năng truy vết/đã thu thập ở kênh cấp phát; hoặc áp dụng quy trình hủy/rotation role khi cần.
4. Xem xét **AppRole client token đã được cấp**, vì thu hồi SecretID **không tự thu hồi token** phát hành trước đó. Nếu có nguy cơ lộ token đã login, cần thu hồi phiên liên quan theo quy trình sự cố.
5. Phát **SecretID mới và wrapping token mới**, xác minh kênh phân phối rồi mới cho triển khai lại.

Bản thân wrapping token bị dùng trước là tín hiệu đáng điều tra, không đủ để khẳng định đã có truy cập dữ liệu nghiệp vụ. Cần phân biệt response đã bị unwrap với bước AppRole login và quyền mà token sau login thực sự có.

## 12. Kiểm thử tích hợp

Thực hành trên Vault dev/test cô lập với dữ liệu giả. Có thể dùng Testcontainers Vault hoặc một Vault instance test riêng để khởi tạo auth mount, policy và AppRole trước mỗi nhóm test.

| Tình huống | Cách chuẩn bị | Kỳ vọng kiểm chứng |
| --- | --- | --- |
| **Happy path** | Provisioner tạo SecretID có `-wrap-ttl=60s`, Java nhận RoleID + token bọc | Spring Vault unwrap, login, đọc KV giá trị `ready` |
| **Lookup hợp lệ** | Tra cứu wrapping token chưa dùng | `creation_path` đúng, token còn TTL; tra cứu không làm mất lượt |
| **Creation path sai** | Bọc response từ endpoint khác | Phần kiểm tra nguồn gốc từ chối, chưa unwrap |
| **Token hết TTL** | Đặt TTL ngắn và chờ quá hạn trong test cô lập | Unwrap bị từ chối; phải cấp token mới |
| **Token đã unwrap** | Unwrap thủ công trước khi Java sử dụng | `SecretId.wrapped` không thể unwrap lần nữa |
| **SecretID sai/hết lượt** | Cấp SecretID bị hủy hoặc giới hạn lượt cạn | Unwrap response thành công nếu còn, nhưng login thất bại |
| **Đọc KV thiếu ACL** | Bỏ `read` trên `secret/data/apps/billing-worker` | Login thành công, KV bị `403` |
| **Replica dùng chung wrapper** | Hai instance cùng nhận một token bọc | Chỉ một instance có thể unwrap thành công |
| **Re-authentication** | Login lần đầu rồi yêu cầu login mới bằng options giữ token bọc cũ | Lần sau thất bại; cấp token bọc mới để khôi phục |
| **Mất response unwrap** | Tạo timeout sau khi Vault có thể đã xử lý unwrap | Không retry vô điều kiện; kiểm tra audit và cấp lại nếu cần |

Có thể dùng lớp service `BillingWorkerSecrets` để kiểm tra kết quả đọc KV v2. Trọng tâm của test **không phải** việc `AppRoleAuthenticationOptions.builder().build()` trả object khác null, mà là **tích hợp thật với Vault** và phân loại đúng lỗi tại từng giai đoạn.

Trong bài lab, **không sử dụng wrapping token của test này cho test khác**. Mỗi case phải được provisioner cấp token mới để kết quả không phụ thuộc thứ tự chạy test.

## 13. Câu hỏi ôn tập và nhiệm vụ thực hành

**Câu hỏi 1.** Provisioner phát token bọc 60 giây chứa SecretID TTL 10 phút. 70 giây sau, ứng dụng chưa unwrap lần nào. Nó có thể đăng nhập bằng SecretID bên trong không? Vì sao?

**Câu hỏi 2.** Bạn đã chạy `vault unwrap` để kiểm chứng token, sau đó chạy Java với `SecretId.wrapped(VaultToken.of(sameToken))`. Tại sao Java thất bại?

**Câu hỏi 3.** `sys/wrapping/lookup` báo token hợp lệ nhưng `creation_path=sys/wrapping/wrap`. Vì sao ứng dụng nên từ chối token nếu đang chờ SecretID được phát từ `auth/approle/role/billing-worker/secret-id`?

**Câu hỏi 4.** Spring Vault unwrap được SecretID và login thành công. Tại sao request đọc KV vẫn có thể nhận `403`?

**Câu hỏi 5.** Một service có client token renewable chạy lâu hơn TTL wrapping token. Điều này có bắt buộc service phải unwrap lại liên tục không? Chuyện gì xảy ra khi cần AppRole login lại?

**Bài tập cuối:** tạo AppRole `billing-worker`, policy chỉ đọc một KV v2 secret, phát SecretID dưới dạng response-wrap và inject **một wrapping token mới** cho một instance Spring Vault. Thực hiện lookup kiểm tra `creation_path`, để Spring Vault tự unwrap và login, sau đó gọi `VaultTemplate` đọc dữ liệu. Chứng minh token bọc cũ không thể tái sử dụng và policy chặn thao tác ghi.

**Tiêu chí đạt:** người học phân biệt rõ bốn loại credential/token; hiểu TTL của mỗi loại; kiểm tra được nguồn gốc response qua metadata; cấu hình đúng `SecretId.wrapped`; xác định được lỗi unwrap, login hoặc authorization; và mô tả được quy trình cấp lại credential khi restart.

## Tài liệu tham khảo

- [Spring Vault — Authentication Methods, mục AppRole](https://docs.spring.io/spring-vault/reference/vault/authentication.html)
- [Spring Vault — AppRoleAuthenticationOptions.SecretId](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AppRoleAuthenticationOptions.SecretId.html)
- [Spring Vault — AppRoleAuthenticationOptions.Builder](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AppRoleAuthenticationOptions.AppRoleAuthenticationOptionsBuilder.html)
- [Spring Vault — UnwrappingEndpoints](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/UnwrappingEndpoints.html)
- [Spring Vault — AppRoleAuthentication](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AppRoleAuthentication.html)
- [HashiCorp Vault — Response wrapping](https://developer.hashicorp.com/vault/docs/concepts/response-wrapping)
- [HashiCorp Vault — AppRole best practices](https://developer.hashicorp.com/vault/docs/auth/approle/approle-pattern)
- [HashiCorp Vault — Wrapping lookup API](https://developer.hashicorp.com/vault/api-docs/system/wrapping-lookup)
- [HashiCorp Vault — Wrapping unwrap API](https://developer.hashicorp.com/vault/api-docs/system/wrapping-unwrap)
- [HashiCorp Vault — AppRole HTTP API](https://developer.hashicorp.com/vault/api-docs/auth/approle)

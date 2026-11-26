# RoleID, SecretID và cấu hình ràng buộc của role

## Mục tiêu và bối cảnh

Trong chương **Xác thực AppRole** của **SPRING_VAULT**, chúng ta tìm hiểu cách ứng dụng Java xác thực với HashiCorp Vault để sử dụng `VaultTemplate` và các API quản lý secret. Bài này tập trung vào ba thành phần quyết định sự an toàn của AppRole: **RoleID**, **SecretID** và **các ràng buộc cấu hình trên role**.

Sau khi học, bạn có thể:

- Giải thích vai trò của RoleID, SecretID và Vault token; phân biệt thông tin dùng để **đăng nhập** với quyền dùng token **sau khi đăng nhập**.
- Cấu hình giới hạn số lần dùng, thời hạn, dải IP và policy cho một AppRole.
- Cấp và phân phối SecretID an toàn; hiểu khi nào nên dùng response wrapping.
- Kết nối Java/Spring Vault bằng AppRole, đọc secret KV v2 với quyền tối thiểu.
- Chẩn đoán trường hợp đăng nhập thất bại, token hết hạn và lỗi do ràng buộc không khớp.

**Giả định:** Vault đã được khởi tạo, người quản trị có token đủ quyền cấu hình auth method, policy và KV secrets engine. Các ví dụ CLI dùng Bash và môi trường lab; giá trị địa chỉ IP, TTL và chính sách phải được điều chỉnh theo hạ tầng thực tế. Trong sản xuất, sử dụng HTTPS và không cung cấp operator/root token cho ứng dụng.

## 1. AppRole xác thực workload như thế nào?

AppRole là phương thức xác thực dành cho **máy hoặc ứng dụng**. Một AppRole được đặt tên, chẳng hạn `order-service`, chứa cấu hình xác thực và các điều kiện cấp token. Ứng dụng gửi thông tin tới endpoint `auth/approle/login`; nếu hợp lệ, Vault trả về **client token**. Các yêu cầu đọc KV, thao tác Transit hay PKI sau đó dùng token này. AppRole tự nó không trao quyền đọc mọi secret.

~~~mermaid
sequenceDiagram
    autonumber
    participant Broker as Provisioner / Secret broker
    participant App as Java service
    participant Vault as Vault AppRole
    participant KV as KV v2
    Broker->>Vault: Đọc RoleID, tạo SecretID
    Vault-->>Broker: RoleID, SecretID hoặc wrapping token
    Broker-->>App: Phân phối credential qua kênh an toàn
    App->>Vault: POST auth/approle/login (role_id, secret_id)
    Vault->>Vault: Kiểm tra role, SecretID, TTL, số lần dùng, CIDR
    Vault-->>App: client_token và thời hạn token
    App->>KV: Đọc secret bằng client_token
    KV-->>App: Dữ liệu hoặc 403 theo token policy
~~~

| Thành phần | Mục đích | Đặc tính bảo mật | Thời điểm dùng |
| --- | --- | --- | --- |
| **RoleID** | Xác định AppRole cần kiểm tra | Thường ổn định theo role; luôn bắt buộc khi login; không phải token truy cập secret | Khi gọi `auth/approle/login` |
| **SecretID** | Chứng minh ứng dụng được cấp quyền dùng role | Phải giữ bí mật; mặc định bắt buộc; có TTL, số lần dùng, CIDR | Khi login, nếu `bind_secret_id=true` |
| **Vault client token** | Mang danh sách policy và ràng buộc của phiên đã đăng nhập | Có TTL, có thể có giới hạn dùng/IP và khả năng gia hạn tùy loại | Trong từng yêu cầu tới secrets engine |
| **Policy** | Mô tả action được phép trên path | Ví dụ chỉ `read` một KV v2 path | Khi Vault kiểm tra quyền của token |

Cần nhớ ba lần kiểm tra khác nhau: **credential có đúng không → đăng nhập từ nguồn hợp lệ không → token được cấp có quyền trên endpoint đang gọi không**. Đăng nhập thành công không có nghĩa thao tác đọc hoặc ghi secret đều được cho phép.

## 2. RoleID: định danh role, không phải giấy phép truy cập

### 2.1. RoleID được sử dụng ra sao?

RoleID thường được Vault sinh dưới dạng UUID khó đoán. Nó chọn AppRole tương ứng tại thời điểm đăng nhập; tên role (`order-service`) chủ yếu phục vụ quản trị và cấp SecretID, còn ứng dụng dùng giá trị `role_id`. Vault cho phép đặt RoleID tùy chỉnh trong trường hợp chuyên biệt, nhưng mặc định tự sinh thường dễ quản lý và giảm nguy cơ trùng lặp.

Dù có thể hình dung RoleID như **tên tài khoản** và SecretID như **mật khẩu**, không nên xem RoleID là dữ liệu công khai không cần bảo vệ. Không gắn RoleID vào URL công khai, log hoặc hệ thống telemetry không được kiểm soát; đồng thời **không dựa riêng vào tính bí mật của RoleID** để bảo vệ ứng dụng.

Quản trị viên có thể xem RoleID của role:

~~~bash
vault read auth/approle/role/order-service/role-id
# Hoặc chỉ lấy trường cần thiết (đừng đưa kết quả vào log):
vault read -field=role_id auth/approle/role/order-service/role-id
~~~

Token dùng để đọc endpoint này phải có ACL phù hợp. Token của ứng dụng chỉ được cấp quyền đọc secrets của ứng dụng; thông thường **không cần quyền đọc RoleID hoặc tạo SecretID**.

### 2.2. Điều gì xảy ra khi RoleID bị lộ?

Lộ RoleID **không đủ** để đăng nhập khi `bind_secret_id=true` và SecretID còn được bảo vệ. Tuy nhiên, việc kết hợp RoleID với SecretID bị lộ, hoặc cấu hình role bỏ yêu cầu SecretID, có thể dẫn đến phát hành token trái phép.

Nếu nghi RoleID bị lộ: kiểm tra SecretID, nguồn IP và audit trail; thu hồi SecretID liên quan khi cần; cân nhắc đổi RoleID, điều phối cập nhật cho workload. Thay RoleID có thể làm các lần **đăng nhập mới** bằng thông tin cũ thất bại; token đã phát hành cần được đánh giá và thu hồi riêng khi ứng phó sự cố.

## 3. SecretID: thông tin xác thực có vòng đời riêng

### 3.1. Sinh, phân phối và quản lý SecretID

Mỗi SecretID thuộc về **một AppRole**, có thể giới hạn theo thời gian, số lần dùng và dải IP. Có hai mô hình:

- **Pull:** thành phần có quyền (provisioner/CI/broker) yêu cầu Vault sinh SecretID ngẫu nhiên qua `auth/approle/role/<role>/secret-id`. Đây là cách thường gặp.
- **Push:** thành phần có quyền đăng ký một giá trị SecretID tự chọn qua `auth/approle/role/<role>/custom-secret-id`. Chỉ dùng khi có yêu cầu cụ thể và cơ chế sinh giá trị đủ mạnh; tránh SecretID dễ đoán.

Ví dụ, người cấp phát có thể sinh SecretID như sau (lệnh làm lộ giá trị trên terminal, chỉ dùng trong lab đã kiểm soát):

~~~bash
vault write -f auth/approle/role/order-service/secret-id
~~~

Kết quả có thể chứa `secret_id`, `secret_id_accessor`, `secret_id_ttl`, `secret_id_num_uses`. **SecretID accessor không phải SecretID**: nó cho phép tra cứu thông tin hoặc hủy SecretID thông qua endpoint quản trị tương ứng mà không cần tiết lộ SecretID thô. Accessor vẫn là thông tin quản trị cần quản lý đúng quyền.

Trong production, tạo SecretID **theo instance/job** và phân phối qua kênh tin cậy. Không commit vào Git, đóng gói vào JAR/Docker image, ghi trong file `application.yml` công khai hoặc lưu vào log/trace. Việc inject từ secret manager, file được bảo vệ quyền truy cập hoặc một broker cấp phát giúp quản lý tốt hơn hard-code.

### 3.2. Phân biệt TTL và số lần dùng

Giả sử AppRole cấu hình:

~~~text
secret_id_ttl      = 15m
secret_id_num_uses = 2
token_ttl          = 30m
token_max_ttl      = 2h
~~~

Ý nghĩa:

1. **SecretID** còn hợp lệ tối đa 15 phút kể từ khi được cấp; sau khoảng này, không thể dùng nó để tạo phiên đăng nhập mới.
2. SecretID đó có thể được dùng để đăng nhập tối đa 2 lần. Mỗi lần đăng nhập thành công tiêu thụ một lượt; lượt thứ ba thất bại ngay cả khi chưa hết 15 phút.
3. Một **token đã cấp thành công** có thời hạn độc lập: TTL ban đầu là 30 phút (còn phụ thuộc cấu hình mount và giới hạn hệ thống) và nếu token có khả năng gia hạn thì việc gia hạn vẫn chịu mức tối đa tương ứng.
4. SecretID hết hạn hoặc hết lượt **không có nghĩa** token đã phát hành bị vô hiệu hóa ngay lập tức. Ngược lại, token hết hạn không tự làm mới được SecretID. Đây là hai vòng đời khác nhau.

Giá trị `0` của `secret_id_ttl` hay `secret_id_num_uses` có nghĩa **không giới hạn tương ứng**. Đây không phải mặc định an toàn cho workload thông thường. Thời hạn và số lượt càng ngắn thì càng cần có cơ chế cấp SecretID mới đáng tin cậy để ứng dụng khởi động lại và đăng nhập lại.

### 3.3. Response wrapping khi chuyển giao SecretID

Thay vì đưa SecretID thuần vào CI output hoặc runtime environment, bên cấp phát có thể yêu cầu Vault **response-wrap** kết quả. Vault trả về một **wrapping token có TTL ngắn, dùng một lần**; thành phần nhận dùng nó để unwrap và lấy SecretID.

~~~bash
# Provisioner yêu cầu Vault đóng gói kết quả trong một wrapping token 60 giây.
vault write -wrap-ttl=60s -f auth/approle/role/order-service/secret-id

# Chỉ phía nhận token mới thực hiện unwrap trong khoảng TTL cho phép:
vault unwrap <WRAPPING_TOKEN>
~~~

Wrapping token **không phải** SecretID và cũng **không phải** client token của ứng dụng. Một lần unwrap hợp lệ sẽ tiêu thụ wrapping token; việc unwrap thất bại do token đã dùng có thể cho thấy lỗi phân phối hoặc nguy cơ bị lấy cắp. Cần giảm rủi ro lộ token từ tham số dòng lệnh, biến môi trường, CI logs và process inspection; ví dụ trên chỉ minh họa cơ chế.

**Khi dùng Spring Vault:** `SecretId.provided(...)` nhận SecretID đã được cấp; `SecretId.wrapped(VaultToken.of(...))` nhận wrapping token để Spring Vault unwrap. Nếu credential bọc đã bị tiêu thụ, lần xác thực lại sau đó không thể cứ dùng lại wrapping token cũ; cần có cơ chế cấp lại/đổi credential trước khi token hoạt động hết hạn.

## 4. Các ràng buộc cấu hình trên AppRole

Một AppRole không chỉ lưu credential. Nó xác định **khi nào Vault cho phép login** và **token được cấp hoạt động trong phạm vi nào**.

### 4.1. Ràng buộc giai đoạn đăng nhập

| Field | Mặc định phổ biến | Tác dụng | Lưu ý |
| --- | --- | --- | --- |
| `bind_secret_id` | `true` | Bắt buộc gửi SecretID khi login | Nên giữ `true`. Nếu tắt, phải đánh giá các ràng buộc khác; RoleID là bắt buộc trong mọi trường hợp. |
| `secret_id_bound_cidrs` | danh sách rỗng | Chỉ cho phép login bằng SecretID từ các CIDR được chỉ định | Đánh giá theo **IP mà Vault quan sát**; lưu ý NAT, proxy, egress gateway. |
| `secret_id_ttl` | `0` | Giới hạn tuổi thọ SecretID | Giới hạn khả năng tái sử dụng credential cũ. |
| `secret_id_num_uses` | `0` | Giới hạn số lần SecretID tạo token | Không phải số lần token được gọi đến Vault. |
| `local_secret_ids` | `false` | SecretID của role chỉ có tính local đối với cluster nếu bật | Tùy chọn gắn với mô hình replication; chỉ thiết lập lúc tạo role và không đổi lại được. |

Vault yêu cầu role có **ít nhất một ràng buộc** khi tạo hoặc cập nhật. Mặc định `bind_secret_id=true` đáp ứng yêu cầu này; đừng tắt một cách tùy tiện và mặc nhiên xem RoleID như mật khẩu duy nhất.

Khi **sinh riêng một SecretID**, người cấp phát có thể thêm các tham số `cidr_list`, `ttl`, `num_uses`, `token_bound_cidrs` để thu hẹp phạm vi cho **credential cụ thể đó**. Các hạn chế cấp trên role tiếp tục được áp dụng; các giá trị theo từng SecretID không được vượt quá phạm vi hoặc giới hạn của role.

### 4.2. Ràng buộc của token đã cấp

| Field | Tác dụng | Ví dụ lựa chọn |
| --- | --- | --- |
| `token_policies` | Các policy gắn với token mới | `order-service-read` với quyền đọc đúng KV path |
| `token_bound_cidrs` | Giới hạn IP dùng token; đồng thời tác động tới khả năng login tương ứng | CIDR egress ổn định của workload |
| `token_ttl` | TTL ban đầu/yêu cầu gia hạn theo giới hạn của Vault | `30m` |
| `token_max_ttl` | Mức TTL tối đa theo cấu hình thông thường | `2h` |
| `token_explicit_max_ttl` | Mức trần cứng, áp dụng cả khi có gia hạn | Chỉ đặt khi có yêu cầu cụ thể |
| `token_period` | Cấp token periodic, cần gia hạn định kỳ để tiếp tục hợp lệ | Phù hợp service dài hạn và có cơ chế renewal |
| `token_num_uses` | Số yêu cầu mà token được phép thực hiện; `0` là không giới hạn | Thường `0` nếu service gọi Vault liên tục |
| `token_type` | Loại token, chẳng hạn `service`, `batch` hoặc `default` | `service` nếu cần gia hạn; `batch` không renewable |
| `token_no_default_policy` | Có tự gắn policy `default` hay không | Xem xét theo nhu cầu token lookup/renewal và policy nội bộ |

Cấu hình role **không thay thế Vault policy**. Nếu `token_policies` chỉ gắn policy có `read` trên `secret/data/apps/order-service` thì token sẽ không thể `update` path đó, dù login bằng RoleID/SecretID hợp lệ.

Hai trường CIDR dễ bị nhầm:

- `secret_id_bound_cidrs`: hạn chế **nguồn IP có thể dùng SecretID để đăng nhập**.
- `token_bound_cidrs`: hạn chế **nguồn IP của yêu cầu dùng token sau khi đăng nhập**; theo AppRole, nó cũng được xét khi login.

Ví dụ: service đăng nhập từ máy A (đúng CIDR), sau đó gọi KV từ máy B (ngoài `token_bound_cidrs`). Login có thể đã thành công nhưng yêu cầu KV từ máy B vẫn bị Vault từ chối. Đặc biệt cẩn thận với hệ thống có nhiều IP egress hoặc thay đổi tuyến mạng.

### 4.3. Nguyên tắc chọn giới hạn

Các giá trị dưới đây là **minh họa để cân nhắc**, không phải cấu hình mặc định dùng chung:

| Kiểu workload | SecretID | Token | Điều cần chuẩn bị |
| --- | --- | --- | --- |
| CI job tồn tại vài phút | TTL rất ngắn, thường 1 lần dùng; ưu tiên response wrapping | TTL đủ cho job, policy hẹp | Broker cấp một SecretID mới cho mỗi job |
| Service có thể restart/autoscale | SecretID theo instance và TTL/số lượt được tính đến retry, restart | Service token có renewal hoặc có quy trình login lại | Kênh cấp mới credential khi instance khởi động |
| Batch job quy mô lớn, ngắn hạn | SecretID cấp đúng lúc chạy | Cân nhắc batch token nếu không cần renewal | Token hết hạn cố định, không có cơ chế gia hạn |
| Service liên tục nhiều ngày | Cấp phát và rotation riêng; tránh giữ SecretID bất biến | Service token hoặc periodic token có renewal được giám sát | Renewal phải xảy ra trước khi TTL hết; xử lý trường hợp mất kết nối |

Mức độ chặt của giới hạn phải đi cùng **khả năng phục hồi**. SecretID một lần dùng là lựa chọn tốt cho job một lần, nhưng service cần login lại khi restart sẽ bị khóa nếu không được cấp SecretID mới. `token_num_uses=1` cũng hiếm khi phù hợp với ứng dụng đọc nhiều secret hoặc cần renewal.

## 5. Thực hành: tạo AppRole chỉ được đọc một KV secret

Ví dụ dùng Vault ở `http://127.0.0.1:8200` cho **môi trường local lab**. Bạn cần quyền quản trị để bật auth method, mount KV, tạo policy và role. Đảm bảo Vault CLI đã đăng nhập bằng token quản trị trong terminal cấu hình. Không dùng token này trong JVM của ứng dụng.

### Bước 1. Bật AppRole và tạo KV v2 path

~~~bash
export VAULT_ADDR="http://127.0.0.1:8200"

# Chạy một lần nếu auth method chưa được bật ở mount này:
vault auth enable approle

# Chạy một lần nếu mount "secret/" chưa tồn tại:
vault secrets enable -path=secret -version=2 kv

# Chỉ là dữ liệu giả cho lab; tránh nhập secret thực vào shell history.
vault kv put secret/apps/order-service db_password="lab-demo-only"
~~~

Nếu Vault đã có mount `approle/` hoặc `secret/`, việc bật lại sẽ báo lỗi trùng mount: kiểm tra các mount có sẵn và **bỏ qua bước bật lặp lại**. Với KV v2, CLI `vault kv put secret/apps/order-service` tương ứng HTTP path `secret/data/apps/order-service`.

### Bước 2. Viết policy tối thiểu

Tạo file `order-service-read.hcl` trong máy lab với nội dung:

~~~hcl
path "secret/data/apps/order-service" {
  capabilities = ["read"]
}
~~~

Đăng ký policy:

~~~bash
vault policy write order-service-read order-service-read.hcl
~~~

Policy chỉ cho phép **đọc** đúng secret này. Không cấp `list` hay `update` nếu ứng dụng không cần. Quyền cấu hình role và phát SecretID nên thuộc một **provisioner** riêng, không nằm trong policy `order-service-read`.

### Bước 3. Tạo AppRole với ràng buộc có thể kiểm chứng

~~~bash
vault write auth/approle/role/order-service \
  bind_secret_id=true \
  secret_id_ttl=15m \
  secret_id_num_uses=2 \
  secret_id_bound_cidrs="127.0.0.1/32" \
  token_bound_cidrs="127.0.0.1/32" \
  token_policies="order-service-read" \
  token_ttl=30m \
  token_max_ttl=2h \
  token_num_uses=0 \
  token_type=service

vault read auth/approle/role/order-service
~~~

Các giá trị IP `127.0.0.1/32` chỉ dùng khi **Vault nhìn thấy nguồn yêu cầu là loopback**. Nếu chạy Vault trong container/VM, hoặc ứng dụng truy cập qua NAT, cân nhắc CIDR ứng dụng thật và egress path; không sửa bừa thành `0.0.0.0/0` để vượt qua kiểm tra. Các giới hạn TTL còn phụ thuộc cấu hình của Vault server/auth mount.

Điểm cần quan sát:

- `bind_secret_id=true` yêu cầu cả RoleID lẫn SecretID.
- SecretID tồn tại tối đa 15 phút và login được tối đa 2 lần.
- Token gắn policy `order-service-read`, được phép dùng từ nguồn IP đã chỉ định.
- `token_num_uses=0` tránh cạn lượt gọi khi Java đọc nhiều lần hoặc token cần được gia hạn.

### Bước 4. Lấy credential và thử login

Chỉ thực hiện trong phiên shell bảo mật của lab. Không đưa các biến sau vào CI log, screenshot hoặc output theo dõi. Ví dụ dùng `jq` để trích token từ kết quả login:

~~~bash
ROLE_ID="$(vault read -field=role_id auth/approle/role/order-service/role-id)"
SECRET_ID="$(vault write -f -field=secret_id auth/approle/role/order-service/secret-id)"

# Một login thành công sẽ tiêu thụ một lượt sử dụng SecretID.
APP_TOKEN="$(vault write -format=json auth/approle/login \
  role_id="$ROLE_ID" \
  secret_id="$SECRET_ID" | jq -r '.auth.client_token')"

# Chỉ dùng token ứng dụng cho yêu cầu đọc:
VAULT_TOKEN="$APP_TOKEN" vault kv get secret/apps/order-service

# Dự kiến 403: policy của token ứng dụng không có quyền ghi.
VAULT_TOKEN="$APP_TOKEN" vault kv put secret/apps/order-service db_password="blocked"
~~~

Trong môi trường thực, tránh giữ cả SecretID và token trong biến shell lâu hơn cần thiết; hủy session/credential thử nghiệm sau lab. Nếu muốn thử độc lập giới hạn `secret_id_num_uses=2`, hãy dùng lại chính SecretID đó: lần login thứ ba sẽ bị từ chối. Khi SecretID hết lượt/hết hạn, **sinh SecretID mới bằng danh tính provisioner**, không cấp quyền tạo SecretID cho ứng dụng chỉ để sửa lỗi.

### Bước 5. API JSON để hiểu request

Spring Vault thực hiện ý tưởng tương đương HTTP request sau:

~~~http
POST /v1/auth/approle/login HTTP/1.1
Content-Type: application/json

{
  "role_id": "<ROLE_ID_DA_CAP>",
  "secret_id": "<SECRET_ID_DA_CAP>"
}
~~~

Phần thành công thường có `auth.client_token`, `auth.lease_duration`, `auth.renewable` và `auth.token_policies`. Không log toàn bộ response vì chứa client token; chỉ ghi những metadata an toàn cần thiết cho vận hành.

## 6. Dùng AppRole trong Spring Vault và VaultTemplate

### 6.1. Cấu hình `ClientAuthentication`

Ví dụ sử dụng **Spring Vault thuần** với `AbstractVaultConfiguration`. Các credential đến từ môi trường do hệ thống triển khai cấp phát, không phải chuỗi hard-code trong mã nguồn.

~~~java
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
public class VaultAppRoleConfig extends AbstractVaultConfiguration {

    @Override
    public VaultEndpoint vaultEndpoint() {
        return VaultEndpoint.from(URI.create(requiredEnv("VAULT_ADDR")));
    }

    @Override
    public ClientAuthentication clientAuthentication() {
        AppRoleAuthenticationOptions options = AppRoleAuthenticationOptions.builder()
                .roleId(RoleId.provided(requiredEnv("VAULT_ROLE_ID")))
                .secretId(SecretId.provided(requiredEnv("VAULT_SECRET_ID")))
                .build();

        return new AppRoleAuthentication(options, vaultClient());
    }

    private static String requiredEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing environment variable: " + key);
        }
        return value;
    }
}
~~~

Khi ứng dụng bắt đầu, runtime cần có `VAULT_ADDR`, `VAULT_ROLE_ID` và `VAULT_SECRET_ID`. Ví dụ `VAULT_ADDR=https://vault.example.internal:8200` trong production; cấu hình CA/TLS trust và network phải phù hợp với môi trường. Không chuyển operator token dùng để thiết lập role thành `VAULT_TOKEN` của JVM.

Spring Vault dùng `ClientAuthentication` để có token và `SessionManager` để tái sử dụng token cho các lệnh gọi sau. `LifecycleAwareSessionManager` có thể lên lịch gia hạn token **nếu token hỗ trợ renewal**; việc này không gia hạn SecretID. Nếu token hết hạn và cần login lại, credential AppRole phải còn hợp lệ hoặc có cơ chế cung cấp credential mới.

> Lưu ý tương thích: ví dụ sử dụng API `vaultClient()` trong tài liệu Spring Vault hiện hành. Với một số phiên bản Spring Vault cũ hơn, constructor của `AppRoleAuthentication` nhận `RestOperations` từ `restOperations()`. Kiểm tra phiên bản thư viện trước khi sao chép mã.

### 6.2. Đọc KV v2 bằng `VaultTemplate`

~~~java
import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.support.VaultResponse;

@Service
public class OrderServiceSecrets {

    private final VaultTemplate vaultTemplate;

    public OrderServiceSecrets(VaultTemplate vaultTemplate) {
        this.vaultTemplate = vaultTemplate;
    }

    public String databasePassword() {
        VaultResponse response = vaultTemplate
                .opsForKeyValue("secret", KeyValueBackend.KV_2)
                .get("apps/order-service");

        if (response == null) {
            throw new IllegalStateException("Vault secret is missing");
        }
        Object password = response.getRequiredData().get("db_password");
        if (!(password instanceof String)) {
            throw new IllegalStateException("Vault secret has invalid db_password");
        }
        return (String) password;
    }
}
~~~

`opsForKeyValue("secret", KV_2)` xử lý khác biệt đường dẫn KV v2 cho Java. Tại tầng ACL, quyền đọc vẫn phải cấp trên **`secret/data/apps/order-service`**. Ví dụ trả mật khẩu cho lớp gọi để minh họa; ứng dụng thực nên tránh ghi mật khẩu vào log, HTTP response hoặc exception.

Nếu hệ thống dùng **Spring Cloud Vault**, có cơ chế cấu hình `spring.cloud.vault.authentication=APPROLE` và các property `spring.cloud.vault.app-role.*` riêng. Chúng thuộc cách tích hợp Spring Cloud Vault, không tự xuất hiện chỉ vì có dependency Spring Vault thuần.

### 6.3. Dùng SecretID đã response-wrap

Đối với provisioning an toàn hơn, thay dòng cung cấp SecretID bằng:

~~~java
.secretId(SecretId.wrapped(
        org.springframework.vault.authentication.VaultToken.of(
                requiredEnv("VAULT_WRAPPED_SECRET_ID_TOKEN"))))
~~~

Lúc này ứng dụng cần nhận **wrapping token** do broker cung cấp; không nhận SecretID thô. Token bọc hết hạn nhanh và chỉ unwrap một lần, nên luồng retry/restart phải phát wrapping token mới khi cần. Đây là bước **bootstrap credential**; token đọc KV vẫn được quản lý bởi Spring Vault sau khi login thành công.

## 7. Sai lầm thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân nên kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Login trả `400`/`403`, báo credential không hợp lệ | Sai `role_id`, sai SecretID, SecretID hết TTL/hết lượt, `bind_secret_id` yêu cầu SecretID | Đối chiếu đúng role; tra cứu accessor bằng quyền provisioner; cấp SecretID mới nếu cần |
| Login bị từ chối chỉ tại một môi trường | `secret_id_bound_cidrs` hoặc `token_bound_cidrs` không khớp IP mà Vault nhìn thấy | Kiểm tra IP egress, NAT/proxy; chỉnh đúng CIDR của workload |
| Login thành công nhưng đọc KV bị `403 permission denied` | Policy chưa gắn vào token, sai KV v2 ACL path, token không hợp lệ hoặc IP sử dụng token bị chặn | Xem policy của token và mount/path thực tế; phân biệt lỗi authentication và authorization |
| Đọc KV trả dữ liệu rỗng/`404` | Không tồn tại key hoặc dùng nhầm `secret/data/...` với `opsForKeyValue`, sai version KV | Kiểm tra mount KV và logical path `apps/order-service` |
| Service chạy ban đầu, restart sau đó không login được | SecretID một lần dùng, TTL ngắn, wrapping token đã unwrap | Cấp credential mới theo instance; kiểm tra luồng deploy/retry |
| Service lỗi sau khi hoạt động một thời gian | Token hết TTL, hết số lượt token, token `batch` không renewable, renewal thất bại | Xem `auth.renewable`, lifecycle của token, giới hạn `token_*` và cơ chế login lại |

### Gợi ý quy trình điều tra

1. Kiểm tra **đường đi request**: đúng URL Vault, auth mount `approle/`, TLS và IP egress của workload.
2. Kiểm tra **AppRole trên máy quản trị** bằng `vault read auth/approle/role/order-service`; xác nhận `bind_secret_id`, CIDR, TTL, số lượt và policy.
3. Kiểm tra **SecretID** theo accessor nếu có; tuyệt đối không in SecretID hoặc token vào ticket/log để debug.
4. Nếu login thành công, xác định **token** đang được dùng: thời hạn còn lại, khả năng renewal, CIDR và danh sách policy.
5. Kiểm tra **đường dẫn KV v2 và policy**: `vault kv get secret/apps/order-service` là logical path trong CLI, còn policy cần `secret/data/apps/order-service`.
6. Đối chiếu audit log Vault và metric ứng dụng để biết lỗi xảy ra **lúc login**, **khi renew** hay **khi thao tác secrets engine**. Tạo cảnh báo cho số login thất bại bất thường, token renewal thất bại và wrapping token bị dùng trước khi bên nhận unwrap.

Lưu ý: thông báo `permission denied` có thể xuất hiện ở nhiều tầng; không suy đoán rằng RoleID/SecretID sai chỉ vì một yêu cầu đọc KV nhận `403`.

## 8. Mẫu vận hành an toàn cho workload

### Phân tách danh tính triển khai và danh tính ứng dụng

- **Vault administrator/IaC**: tạo policy, cấu hình role và ràng buộc.
- **Provisioner hoặc broker**: được phép đọc RoleID/tạo SecretID cho role mục tiêu, nhưng không mặc nhiên được đọc dữ liệu nghiệp vụ của ứng dụng.
- **Workload Java**: chỉ nhận thông tin đủ để đăng nhập và token được cấp với policy đọc đúng secret cần thiết.

Khi CI/CD hoặc Kubernetes triển khai nhiều replica, lý tưởng là mỗi replica nhận credential riêng; việc hủy một SecretID không làm gián đoạn tất cả replica. Giới hạn CIDR nên phản ánh IP egress mà Vault thực sự nhìn thấy. Nếu môi trường có phương thức danh tính nền tảng mạnh hơn (ví dụ Kubernetes Auth hoặc cloud IAM Auth), đánh giá phương thức đó trước khi quyết định dùng AppRole và tự phân phối SecretID.

### Quy trình xoay vòng và thu hồi

1. Cấp **SecretID mới** cho replica/job mới qua kênh tin cậy (có thể response-wrap).
2. Cho workload đăng nhập, đọc secret và kiểm tra health với token mới.
3. Ngừng phân phối SecretID cũ; dùng **accessor** để hủy SecretID nếu cần ngăn các lần login mới.
4. Đánh giá các **token đã cấp**: hủy SecretID không tự động thu hồi những token này. Thu hồi token/token accessor hoặc thay đổi policy theo quy trình ứng phó nếu đã có nguy cơ lộ.
5. Theo dõi thời hạn, kết quả renewal, lỗi authorization và audit events mà không ghi lộ dữ liệu nhạy cảm.

Giữ `metadata` của SecretID ở mức thông tin không nhạy cảm, chẳng hạn mã môi trường hoặc ID triển khai: Vault có thể ghi metadata vào audit log **dưới dạng plaintext**.

## 9. Bài tập kiểm chứng

Thực hành trên môi trường lab, không dùng credential thật:

1. Tạo AppRole với `secret_id_ttl=5m`, `secret_id_num_uses=1`, policy chỉ `read` một KV v2 path. Đăng nhập một lần, rồi thử lần thứ hai bằng SecretID cũ. Giải thích vì sao token lần đầu vẫn có thể hoạt động.
2. Thử dùng token đã cấp để **ghi** lên KV path chỉ có quyền `read`. Phân biệt phản hồi này với lỗi login do SecretID sai.
3. Thêm `token_bound_cidrs` và kiểm tra từ một nguồn IP khác khi hạ tầng lab cho phép. Quan sát vì sao login hoặc lệnh dùng token có thể bị từ chối.
4. Chuyển sang cấp SecretID bằng response wrapping và xác minh lần unwrap thứ hai không còn hợp lệ. Thiết kế cách cấp lại credential khi ứng dụng restart.

**Tiêu chí hoàn thành:** ứng dụng Java có thể đăng nhập qua AppRole và đọc đúng một secret bằng `VaultTemplate`; không thể ghi secret đó; kiểm tra giới hạn SecretID và token cho kết quả đúng; không có RoleID/SecretID/client token được hard-code hoặc ghi vào log.

## Tài liệu tham khảo

- [HashiCorp Vault — AppRole auth method](https://developer.hashicorp.com/vault/docs/auth/approle)
- [HashiCorp Vault — AppRole HTTP API và các field cấu hình](https://developer.hashicorp.com/vault/api-docs/auth/approle)
- [HashiCorp Vault — Best practices for AppRole authentication](https://developer.hashicorp.com/vault/docs/auth/approle/approle-pattern)
- [HashiCorp Vault — Response wrapping](https://developer.hashicorp.com/vault/docs/concepts/response-wrapping)
- [HashiCorp Vault — Token TTL, periodic token và token types](https://developer.hashicorp.com/vault/docs/concepts/tokens)
- [Spring Vault — Authentication methods](https://docs.spring.io/spring-vault/reference/vault/authentication.html)
- [Spring Vault — Session management và VaultTemplate](https://docs.spring.io/spring-vault/reference/vault/imperative-template.html)
- [Spring Vault — KV secrets engine](https://docs.spring.io/spring-vault/reference/vault/vault-secret-engines.html)

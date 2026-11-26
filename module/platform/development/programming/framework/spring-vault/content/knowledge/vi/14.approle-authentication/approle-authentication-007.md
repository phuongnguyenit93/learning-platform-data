# TTL, giới hạn số lần dùng và vòng đời SecretId

## 1. Mục tiêu bài học

Trong chương **Xác thực AppRole** của **SPRING_VAULT**, SecretID là một credential được HashiCorp Vault phát cho một AppRole và thường được dùng cùng RoleID để ứng dụng Java đăng nhập. Hai tham số **`secret_id_ttl`** và **`secret_id_num_uses`** quyết định SecretID có thể tiếp tục tạo phiên đăng nhập trong bao lâu và bao nhiêu lần. Chúng ảnh hưởng trực tiếp tới triển khai, khởi động lại, autoscaling và khả năng ứng dụng phục hồi khi Vault token hết hạn.

Bài học này giúp bạn:

- Phân biệt **SecretID**, **SecretID accessor**, **wrapping token** và **AppRole client token**.
- Cấu hình `secret_id_ttl` và `secret_id_num_uses` trên role; cấp một SecretID với `ttl`/`num_uses` riêng theo giới hạn cho phép.
- Giải thích khi nào SecretID còn hợp lệ, đã hết TTL, hết lượt hoặc bị thu hồi.
- Thực hành cấp phát, xem metadata qua accessor, hủy SecretID và quan sát tác động tới những lần đăng nhập tiếp theo.
- Chọn chiến lược `SecretId.provided(...)`, `SecretId.pull(...)` hoặc `SecretId.wrapped(...)` trong Spring Vault cho từng kiểu workload.
- Thiết kế việc làm mới credential, quản lý client token qua `SessionManager`, phân loại lỗi và thực hiện kiểm thử tích hợp.

Phần minh họa sử dụng Spring Vault Core (API 4.1.x), `VaultTemplate` và KV v2. Các giá trị thời gian, chính sách, IP và token đều dành cho **lab**. Môi trường production phải dùng HTTPS/TLS, phân quyền tối thiểu và cơ chế phân phối bí mật được bảo vệ.

## 2. Tại sao SecretID cần vòng đời riêng?

Một AppRole có tên, ví dụ `audit-consumer`, sở hữu RoleID cùng cấu hình xác thực. Khi `bind_secret_id=true` (cấu hình thường dùng), ứng dụng phải gửi cả `role_id` và `secret_id` đến `POST /v1/auth/approle/login`. Vault sẽ kiểm tra credential và các ràng buộc liên quan trước khi cấp **client token**.

~~~mermaid
sequenceDiagram
    autonumber
    participant Provisioner as Provisioner
    participant Vault as Vault AppRole
    participant Java as Java / Spring Vault
    participant KV as KV v2
    Provisioner->>Vault: POST auth/approle/role/audit-consumer/secret-id
    Vault-->>Provisioner: SecretID + accessor + thông tin giới hạn
    Provisioner-->>Java: Cấp RoleID/SecretID an toàn
    Java->>Vault: POST auth/approle/login (role_id, secret_id)
    Vault->>Vault: Kiểm tra SecretID, TTL, lượt dùng, CIDR
    Vault-->>Java: Client token + TTL + policies
    Java->>KV: GET secret/data/apps/audit-consumer bằng client token
    KV-->>Java: Dữ liệu hoặc lỗi ACL
~~~

Nếu SecretID bị lộ và vẫn còn hợp lệ, một bên ngoài ý muốn có thể dùng nó cùng RoleID để xin client token. **TTL ngắn** giảm thời gian credential có thể bị lợi dụng. **Số lượt dùng nhỏ** giảm khả năng tái sử dụng. **Thu hồi có chủ đích** giúp dừng các lần login mới mà không phải chờ TTL hết.

Giới hạn càng chặt càng đòi hỏi cơ chế cấp mới đáng tin cậy. SecretID chỉ dùng một lần rất phù hợp cho một CI job được provisioner cấp credential đúng lúc, nhưng có thể làm một service tự restart bị khóa nếu service chỉ có chuỗi SecretID ban đầu.

### 2.1. Bốn đối tượng không được nhầm

| Đối tượng | Nguồn tạo | Mục đích | Điểm hết hiệu lực |
| --- | --- | --- | --- |
| **RoleID** | Vault gắn cho AppRole | Xác định role tại bước login | Role bị xóa hoặc RoleID được thay |
| **SecretID** | Vault phát hoặc tiếp nhận qua custom-secret-id | Cho phép đăng nhập AppRole cùng RoleID | TTL, số lượt, hủy, ràng buộc IP |
| **Wrapping token** | Vault tạo khi response được wrap | Unwrap response chứa SecretID | TTL wrapping, dùng một lần, hủy |
| **AppRole client token** | Vault cấp sau login | Truy cập KV, Transit, PKI theo ACL | Token TTL, giới hạn renew, revoke, bound CIDR |

**Một SecretID hết hạn hoặc bị hủy không có nghĩa mọi client token đã được cấp trước đó cũng lập tức hết hiệu lực.** Nếu phải xử lý sự cố lộ credential, cần đánh giá và thu hồi client token liên quan riêng.

## 3. Hai giới hạn quan trọng: TTL và số lần dùng

### 3.1. `secret_id_ttl`: thời hạn tồn tại của SecretID

Giả sử role có:

~~~hcl
secret_id_ttl = "5m"
~~~

Khi Vault phát SecretID lúc 09:00, SecretID này thường không còn dùng login được sau 09:05, kể cả chưa từng đăng nhập. TTL được tính từ **thời điểm phát SecretID**, không đợi ứng dụng nhận được hoặc lần đầu dùng nó.

Theo Vault AppRole HTTP API:

- `secret_id_ttl=0` là **không giới hạn TTL** của SecretID theo tùy chọn này.
- Có thể cấu hình khoảng thời gian dưới dạng `30s`, `5m`, `1h` hoặc số giây.
- Giá trị giới hạn ở **role** áp dụng mặc định khi phát các SecretID của role đó.
- Khi phát một SecretID riêng lẻ, có thể gửi `ttl` để thu hẹp thời hạn; không được yêu cầu TTL dài hơn trần đã đặt trên role.
- Một SecretID có TTL vẫn có thể hết hiệu lực **sớm hơn** do hết lượt dùng, bị hủy hoặc role/ràng buộc thay đổi.

`secret_id_ttl=0` không nên được hiểu là an toàn chỉ vì token nghiệp vụ có TTL ngắn. SecretID không hết hạn có thể tiếp tục xin **token mới** trong tương lai nếu còn lượt và role còn hợp lệ.

### 3.2. `secret_id_num_uses`: số lần SecretID được dùng để login

Ví dụ:

~~~hcl
secret_id_num_uses = 2
~~~

SecretID có thể được dùng tối đa **hai lần để lấy AppRole client token**. Khi số lượt hợp lệ đã tiêu thụ hết, SecretID đó không thể tiếp tục tạo phiên mới, dù chưa đến thời điểm hết TTL.

Các quy tắc cần nhớ:

- `secret_id_num_uses=0` có nghĩa **không giới hạn số lượt dùng** theo tham số này.
- Một lần login thành công phát token sẽ tiêu thụ một lượt của SecretID. Với một SecretID hữu hạn lượt, các lần login sau khi hết lượt sẽ bị từ chối.
- **Mỗi yêu cầu đọc KV bằng client token đã cấp không trừ thêm lượt của SecretID.**
- Nếu role đặt giới hạn, một SecretID cụ thể có thể được phát với `num_uses` nhỏ hơn; không được nâng trần bằng tham số `num_uses`.
- Khi role đặt giới hạn hữu hạn, đừng sử dụng `num_uses=0` để hy vọng biến SecretID thành vô hạn lượt; Vault áp dụng quy tắc giới hạn của role.

Một lỗi phổ biến là nhầm `secret_id_num_uses` với `token_num_uses`. Đây là hai điều kiện hoàn toàn khác:

| Tham số | Áp dụng cho | Giới hạn thứ gì? |
| --- | --- | --- |
| `secret_id_num_uses` | **SecretID** | Số lần dùng SecretID để đăng nhập và lấy token |
| `num_uses` khi phát SecretID | **SecretID riêng lẻ** | Số lần login cho credential được phát |
| `token_num_uses` | **Client token** do AppRole cấp | Số request được phép dùng chính client token |
| `token_ttl`, `token_max_ttl` | **Client token** | Thời gian sử dụng/gia hạn client token theo cấu hình và giới hạn Vault |

Ví dụ `secret_id_num_uses=1`, `token_num_uses=0`: ứng dụng đăng nhập được **một lần** với SecretID đó, nhưng client token nhận được vẫn có thể dùng để đọc KV nhiều lần khi còn hạn và đủ policy.

### 3.3. TTL và số lượt là hai điều kiện đồng thời

Một SecretID chỉ có thể sử dụng khi **chưa hết TTL, chưa hết lượt và chưa bị vô hiệu vì lý do khác**. Không phải chọn một trong hai điều kiện.

~~~mermaid
flowchart TD
    A["AppRole login bằng SecretID"] --> B{"SecretID tồn tại và thuộc role?"}
    B -- "Không" --> X["Từ chối login"]
    B -- "Có" --> C{"Còn TTL nếu được giới hạn?"}
    C -- "Không" --> X
    C -- "Có" --> D{"Còn lượt dùng nếu được giới hạn?"}
    D -- "Không" --> X
    D -- "Có" --> E{"Ràng buộc CIDR / role hợp lệ?"}
    E -- "Không" --> X
    E -- "Có" --> F["Vault cấp client token"]
    F --> G["Trừ lượt SecretID theo kết quả login"]
    G --> H["Client token có vòng đời độc lập"]
~~~

| Thời điểm minh họa | Sự kiện | SecretID TTL 4 phút, tối đa 2 lượt | Client token |
| --- | --- | --- | --- |
| 09:00 | Phát SecretID `S1` | Còn 4 phút, 2 lượt | Chưa có |
| 09:01 | Login bằng `S1` lần 1 | Còn ~3 phút, 1 lượt | Phát `T1` |
| 09:02 | Login bằng `S1` lần 2 | Đã dùng hết 2 lượt | Phát `T2` |
| 09:02:30 | Login bằng `S1` lần 3 | **Không còn lượt** | Không phát token mới |
| 09:03 | Dùng `T1` đọc KV | Không cần dùng lại `S1` | Có thể thành công nếu `T1` còn hợp lệ |
| 09:04 | TTL SecretID kết thúc | `S1` cũng đã hết TTL | `T1`/`T2` có TTL riêng |

Thời điểm và kết quả token trong bảng chỉ minh họa. TTL client token thực tế phụ thuộc giới hạn auth mount, loại token, policy và các yếu tố Vault khác.

## 4. Vòng đời SecretID từ cấp phát đến thu hồi

Có thể mô tả một credential theo các trạng thái logic:

~~~mermaid
stateDiagram-v2
    [*] --> Issued: Vault phát SecretID
    Issued --> Usable: Chuyển giao cho workload
    Usable --> Usable: Login thành công, còn lượt và TTL
    Usable --> Expired: TTL hết
    Usable --> Exhausted: Số lượt dùng về 0
    Usable --> Revoked: Destroy qua SecretID/accessor
    Issued --> Expired: Hết TTL trước khi tới workload
    Issued --> Revoked: Provisioner hủy
    Expired --> [*]
    Exhausted --> [*]
    Revoked --> [*]
~~~

Các tên trạng thái ở sơ đồ chỉ nhằm giúp học, **không phải một trường `status` chính thức** mà Vault luôn trả về. Muốn biết một SecretID còn hợp lệ phải kết hợp metadata, thời gian, giới hạn dùng và tình trạng role.

### 4.1. Cấp phát (issue)

Provisioner có quyền `update` endpoint `auth/approle/role/<role>/secret-id` để tạo SecretID ngẫu nhiên; nếu cần một SecretID do bên ngoài sinh, Vault có endpoint `custom-secret-id`. Phân phối từng SecretID qua một kênh tin cậy cho đúng workload.

### 4.2. Sử dụng (login)

Khi có RoleID và SecretID, Java/Spring Vault gọi `auth/approle/login`. Vault kiểm tra SecretID, TTL, số lượt dùng và các ràng buộc khác, rồi cấp client token theo cấu hình role.

### 4.3. Hết TTL hoặc hết lượt

Hết TTL không đợi ứng dụng khởi động lại. Hết lượt có thể xảy ra sớm hơn dự tính nếu nhiều instance dùng chung credential hoặc ứng dụng tự gọi `login()` quá nhiều lần. Khi SecretID không còn hợp lệ, **không thể tự khôi phục số lượt**; cần cấp SecretID khác.

### 4.4. Thu hồi (destroy)

Quản trị viên/provisioner có thể hủy SecretID trực tiếp hoặc thông qua **SecretID accessor**. Hủy chặn việc dùng credential đó cho **các lần login mới**. Token đã phát hành trước đó phải được đánh giá và thu hồi riêng khi cần ứng phó sự cố.

### 4.5. Xoay vòng (rotate)

Rotation thường là **cấp mới trước, chuyển giao, kiểm tra login, sau đó hủy credential cũ**. Với instance có SecretID một lần dùng, mỗi lần triển khai mới nên được cấp SecretID mới; không nên cố đặt số lượt quá cao để né việc thiết kế cấp phát.

## 5. Thực hành Vault CLI: role có TTL và use-count

### 5.1. Chuẩn bị lab với KV v2

Giả sử Vault đã khởi tạo và có token quản trị trong shell lab. HTTP chỉ dùng với Vault local/dev; production cần HTTPS và xác minh CA/TLS.

~~~bash
export VAULT_ADDR="http://127.0.0.1:8200"

# Chỉ bật AppRole nếu auth/approle chưa tồn tại.
vault auth enable approle

# Chỉ bật KV v2 nếu secret/ chưa tồn tại.
vault secrets enable -path=secret -version=2 kv

# Secret giả để kiểm thử, không dùng dữ liệu nhạy cảm thật.
vault kv put secret/apps/audit-consumer greeting="hello-vault"
~~~

Nếu mount đã tồn tại, bỏ qua lệnh bật trùng. Kiểm tra đúng mount và phiên bản KV trước khi viết thêm dữ liệu.

### 5.2. Tạo policy tối thiểu

Tạo file `audit-consumer-read.hcl` trên máy lab:

~~~hcl
path "secret/data/apps/audit-consumer" {
  capabilities = ["read"]
}
~~~

Áp dụng:

~~~bash
vault policy write audit-consumer-read audit-consumer-read.hcl
~~~

Đây là ACL của **AppRole client token** sau login, chỉ đọc một path KV v2. Token của provisioner cấp phát SecretID cần policy **khác**, không được mặc nhiên dùng chính policy này để quản lý AppRole.

### 5.3. Tạo AppRole

~~~bash
vault write auth/approle/role/audit-consumer \
    bind_secret_id=true \
    secret_id_ttl=5m \
    secret_id_num_uses=3 \
    token_ttl=15m \
    token_max_ttl=1h \
    token_type=service \
    token_num_uses=0 \
    token_policies="audit-consumer-read"

vault read auth/approle/role/audit-consumer
~~~

Ý nghĩa của cấu hình:

- SecretID mặc định của role có TTL 5 phút, tối đa 3 lần login.
- Client token có TTL cấu hình ban đầu 15 phút, mức tối đa 1 giờ (còn phụ thuộc giới hạn hệ thống), loại `service`.
- `token_num_uses=0` cho phép client token thực hiện nhiều request trong TTL.
- Token chỉ có quyền đọc `secret/data/apps/audit-consumer` theo policy đã gắn.

Đừng lấy các giá trị này làm chuẩn production chung; mỗi workload cần đánh giá startup delay, tần suất restart, retry, mức độ phân tán, nhu cầu token renewal và đường cấp phát credential.

### 5.4. Cấp một SecretID với giới hạn chặt hơn role

Role cho phép 3 lượt và TTL 5 phút; provisioner có thể yêu cầu một SecretID riêng chỉ 2 lượt, TTL 2 phút:

~~~bash
vault write auth/approle/role/audit-consumer/secret-id \
    ttl=2m \
    num_uses=2
~~~

Phản hồi chứa các trường như:

~~~text
secret_id                <SECRET_ID_LAB>
secret_id_accessor       <ACCESSOR_LAB>
secret_id_ttl            2m
secret_id_num_uses       2
~~~

Chỉ dùng placeholder ở đây; đừng ghi lại SecretID thật trong tài liệu, issue, log hoặc CI output. Accessor là **tay nắm quản trị**, không dùng thay `secret_id` khi login. Accessor vẫn phải được quản lý với ACL đúng quyền vì có thể dùng để tra cứu/hủy credential nếu kết hợp với một token quản trị có quyền.

**Trường `ttl` và `num_uses` khi phát SecretID** là giới hạn của **credential cụ thể**, trong khi `secret_id_ttl` và `secret_id_num_uses` trên role là cấu hình mặc định/trần. Vault không cho vượt mức giới hạn hữu hạn mà role đặt ra.

### 5.5. Thử login hai lần, lần thứ ba bị từ chối

Trong terminal lab được bảo vệ, hãy cấp RoleID và SecretID thử nghiệm. Để minh họa, sử dụng biến shell chỉ tồn tại trong phiên lab:

~~~bash
ROLE_ID="$(vault read -field=role_id \
    auth/approle/role/audit-consumer/role-id)"

# Tạo riêng một SecretID để thử. Mỗi lần chạy là một credential mới.
SECRET_ID="$(vault write -field=secret_id \
    auth/approle/role/audit-consumer/secret-id ttl=2m num_uses=2)"

# Chạy lệnh login này hai lần trong khoảng TTL.
# Cần jq để chỉ hiện metadata, tránh in client token:
vault write -format=json auth/approle/login \
    role_id="$ROLE_ID" secret_id="$SECRET_ID" \
    | jq '{ttl: .auth.lease_duration, renewable: .auth.renewable, errors: .errors}'

# Chạy lại lần thứ ba với đúng SECRET_ID trên:
# Kỳ vọng Vault từ chối vì SecretID đã hết lượt.
vault write auth/approle/login \
    role_id="$ROLE_ID" secret_id="$SECRET_ID"
~~~

Các lệnh trên chỉ dành cho **lab**: shell variable có thể bị người có quyền trên host quan sát, và lệnh cuối có thể in token nếu số lượt thử trước đó chưa đủ. Trong production, cấp phát/giao credential bằng API và kênh bảo vệ, không đưa SecretID lên command line.

Khi gặp lỗi, cần chắc rằng hai lần login thành công trước đó thật sự đã tiêu thụ lượt; nếu lần đầu bị từ chối do CIDR/sai role, không nên suy diễn rằng lần thứ ba là lỗi hết lượt.

### 5.6. Thử TTL hết trước khi hết lượt

Tạo một SecretID mới với TTL ngắn và 3 lượt:

~~~bash
vault write auth/approle/role/audit-consumer/secret-id \
    ttl=30s \
    num_uses=3
~~~

Nếu đợi qua thời điểm hết hạn trước **lần login đầu tiên**, SecretID phải bị từ chối dù chưa dùng lượt nào. Trong test automation, có thể tạo thông số TTL ngắn và kiểm tra bằng đồng hồ/test container riêng; không cần chạy script chờ lâu trong bài.

## 6. Tra cứu SecretID an toàn bằng accessor

Vault trả `secret_id_accessor` cùng SecretID khi phát credential. Accessor rất hữu ích để theo dõi và hủy credential mà không cần giữ SecretID thô ở nơi điều hành.

### 6.1. Policy dành cho provisioner

Ví dụ policy cấp phát và quản lý **chính AppRole `audit-consumer`**:

~~~hcl
# Tạo SecretID mới.
path "auth/approle/role/audit-consumer/secret-id" {
  capabilities = ["update"]
}

# Đọc RoleID để phân phối khi cần.
path "auth/approle/role/audit-consumer/role-id" {
  capabilities = ["read"]
}

# Tra cứu một SecretID qua accessor.
path "auth/approle/role/audit-consumer/secret-id-accessor/lookup" {
  capabilities = ["update"]
}

# Hủy SecretID qua accessor.
path "auth/approle/role/audit-consumer/secret-id-accessor/destroy" {
  capabilities = ["update"]
}
~~~

Hãy lưu policy này trong file `audit-consumer-provisioner.hcl` ở môi trường quản trị và nạp bằng `vault policy write` nếu thực hành. **Không gắn policy provisioner vào token của ứng dụng**; workload chỉ cần RoleID/SecretID để đăng nhập và token đọc secret theo policy `audit-consumer-read`.

### 6.2. Lookup theo accessor

Với `<ACCESSOR_LAB>` đã được lưu an toàn khi provisioner phát SecretID:

~~~bash
vault write auth/approle/role/audit-consumer/secret-id-accessor/lookup \
    secret_id_accessor="<ACCESSOR_LAB>"
~~~

Vault có thể trả các trường `creation_time`, `expiration_time`, `secret_id_ttl`, `secret_id_num_uses`, `cidr_list`, `token_bound_cidrs` và `metadata`. Đây là **thông tin mô tả** credential, không trả lại giá trị SecretID.

Không suy diễn rằng field `secret_id_num_uses` trong mọi bản Vault là một bộ đếm thời gian thực cho số lượt còn lại; điều cần xác minh chắc chắn là kết quả login và trạng thái credential tại thời điểm thử. Một accessor của SecretID đã hết hạn/hết lượt có thể không còn lookup được.

### 6.3. Destroy theo accessor

Khi cần chặn các lần login tiếp theo:

~~~bash
vault write auth/approle/role/audit-consumer/secret-id-accessor/destroy \
    secret_id_accessor="<ACCESSOR_LAB>"
~~~

Vault cũng có endpoint hủy trực tiếp bằng `secret_id`, nhưng việc hủy qua accessor có lợi là **provisioner không phải đưa SecretID thô vào công cụ quản trị để thu hồi**. Accessor cũng cần được bảo vệ theo quyền truy cập vì ai có accessor cùng token đủ quyền có thể tác động tới credential đó.

**Sau khi hủy:** login mới bằng SecretID này không hợp lệ. Nếu một client token đã được cấp trước khi hủy, nó vẫn có **TTL, policy và điều kiện thu hồi riêng**. Đối với sự cố bị lộ, rà soát client token, audit log và policy theo quy trình ứng phó.

### 6.4. Metadata và dữ liệu nhạy cảm

Khi phát SecretID, provisioner có thể gửi metadata liên quan đến job, deploy hoặc môi trường. **Không ghi mật khẩu, token, bí mật nghiệp vụ vào metadata**: Vault có thể ghi metadata SecretID ra audit logs dưới dạng plaintext. Chỉ ghi identifier không nhạy cảm phục vụ điều tra và truy vết.

## 7. TTL có tương tác với CIDR, wrapping và role như thế nào?

### 7.1. CIDR giới hạn nơi SecretID được dùng

AppRole có `secret_id_bound_cidrs` để giới hạn địa chỉ nguồn được phép login; khi phát SecretID riêng lẻ cũng có thể đặt `cidr_list` hẹp hơn. Ngoài ra `token_bound_cidrs` ràng buộc địa chỉ nguồn được phép dùng client token sau khi cấp.

Ví dụ role dành cho workload chạy trong mạng riêng:

~~~bash
vault write auth/approle/role/audit-consumer \
    bind_secret_id=true \
    secret_id_bound_cidrs="10.30.0.0/16" \
    token_bound_cidrs="10.30.0.0/16" \
    secret_id_ttl=5m \
    secret_id_num_uses=2 \
    token_policies="audit-consumer-read"
~~~

**Đây là cấu hình minh họa, không áp dụng nguyên trạng cho lab localhost.** Vault kiểm tra địa chỉ IP nguồn mà server thực sự nhìn thấy; NAT, proxy và egress gateway có thể khiến IP khác với IP nội bộ của container. Một SecretID còn TTL và còn lượt vẫn có thể không login được nếu vi phạm CIDR.

### 7.2. Wrapping TTL không phải SecretID TTL

Provisioner có thể yêu cầu Vault **response-wrap** kết quả phát SecretID:

~~~bash
vault write -wrap-ttl=60s -f \
    auth/approle/role/audit-consumer/secret-id
~~~

Khi đó provisioner nhận **wrapping token** thay vì SecretID thô. Wrapping token thường chỉ unwrap **một lần**, trong 60 giây ở ví dụ này. SecretID bên trong vẫn mang TTL và số lượt riêng do role và yêu cầu phát credential quyết định.

Nếu một wrapping token hết TTL trước khi workload mở được, người nhận không thể dựa vào việc SecretID phía Vault còn thời hạn để khôi phục response bị bọc. Cần **phát một SecretID mới, wrap response mới** rồi chuyển token mới. Spring Vault dùng `SecretId.wrapped(...)` để unwrap.

### 7.3. Thay đổi role không “hồi sinh” SecretID cũ

Điều chỉnh `secret_id_ttl` hoặc `secret_id_num_uses` trên role là cách thay đổi chính sách cấp SecretID. Không xem thao tác này như phương pháp kéo dài một SecretID đã hết TTL, hết lượt hoặc bị destroy. Khi cần rotation, hãy **tạo SecretID mới** và chuyển cho workload.

## 8. Spring Vault: một SecretID, nhiều chiến lược nhận credential

Spring Vault cấu hình AppRole qua `AppRoleAuthenticationOptions`. Các chiến lược khác nhau sẽ có ảnh hưởng khác nhau khi cần tạo phiên mới.

| Chiến lược | Ví dụ Spring Vault | Hệ quả khi cần login lần nữa |
| --- | --- | --- |
| **Provided** | `SecretId.provided(secretId)` | Có thể dùng lại cùng chuỗi **chỉ nếu** SecretID còn TTL/lượt và đúng ràng buộc |
| **Pull** | `SecretId.pull(initialToken)` | Có thể xin SecretID mới nếu bootstrap token còn hiệu lực và có quyền tạo |
| **Wrapped** | `SecretId.wrapped(wrappingToken)` | Wrapping token cũ đã unwrap là **một lần dùng**; cần wrapper/credential mới khi login mới |
| **Absent** | `SecretId.absent()` | Chỉ dùng nếu AppRole đặt `bind_secret_id=false`; không phù hợp với ví dụ bài này |

`RoleId` vẫn phải được cung cấp hoặc lấy từ Vault. Khi dùng pull SecretID, Java phải biết tên role (`appRole`) để gọi đúng endpoint phát SecretID và có bootstrap token được cấp quyền.

### 8.1. Cấu hình Java với SecretID provided

Ví dụ Spring Vault Core với `AbstractVaultConfiguration`:

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
public class AuditVaultConfig extends AbstractVaultConfiguration {

    @Override
    public VaultEndpoint vaultEndpoint() {
        return VaultEndpoint.from(URI.create(requiredEnv("VAULT_ADDR")));
    }

    @Override
    public ClientAuthentication clientAuthentication() {
        String roleId = requiredEnv("VAULT_ROLE_ID");
        String secretId = requiredEnv("VAULT_SECRET_ID");

        AppRoleAuthenticationOptions options = AppRoleAuthenticationOptions.builder()
                .path("approle")
                .roleId(RoleId.provided(roleId))
                .secretId(SecretId.provided(secretId))
                .build();

        return new AppRoleAuthentication(options, vaultClient());
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing configuration: " + name);
        }
        return value;
    }
}
~~~

Trong lab, runtime cần có `VAULT_ADDR`, `VAULT_ROLE_ID` và `VAULT_SECRET_ID`. Ở production, inject qua cơ chế secret management của orchestrator; không hard-code SecretID trong Java hoặc file cấu hình đưa vào Git.

Đây là cấu hình tối giản tham chiếu API Spring Vault 4.1.x. Với bản cũ, constructor `AppRoleAuthentication` có thể nhận `RestOperations` thay cho `vaultClient()`; kiểm tra dependency thật của dự án trước khi sử dụng nguyên mã.

**Cần nhớ:** `SecretId.provided(secretId)` giữ chuỗi được nạp khi tạo object; thay biến môi trường hoặc file mount sau đó **không tự cập nhật** một options đã được xây dựng. Nếu SecretID hết TTL/lượt, phải cấp mới và có cơ chế tạo lại configuration/auth client hoặc khởi động lại có điều phối.

### 8.2. Dùng VaultTemplate đọc KV v2

~~~java
package example.vault;

import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.VaultResponse;

@Service
public class AuditConsumerSecrets {

    private final VaultTemplate vaultTemplate;

    public AuditConsumerSecrets(VaultTemplate vaultTemplate) {
        this.vaultTemplate = vaultTemplate;
    }

    public String greeting() {
        VaultResponse response = vaultTemplate
                .opsForKeyValue("secret", KeyValueBackend.KV_2)
                .get("apps/audit-consumer");

        if (response == null) {
            throw new IllegalStateException("Vault secret does not exist");
        }

        Map<String, Object> data = response.getRequiredData();
        Object greeting = data.get("greeting");

        if (!(greeting instanceof String)) {
            throw new IllegalStateException("Vault field 'greeting' is missing");
        }
        return (String) greeting;
    }
}
~~~

Khi AppRole token có policy `audit-consumer-read`, phương thức trả `hello-vault` từ dữ liệu lab. Spring Vault dùng token đã cấp qua `SessionManager` để gọi KV; **không tiêu thụ SecretID trong mỗi lần `greeting()` được gọi**.

### 8.3. Chuyển sang pull SecretID để chủ động xin credential mới

Một workload có danh tính khởi tạo được quản lý có thể chọn `SecretId.pull(...)`:

~~~java
import org.springframework.vault.authentication.AppRoleAuthenticationOptions;
import org.springframework.vault.authentication.AppRoleAuthenticationOptions.RoleId;
import org.springframework.vault.authentication.AppRoleAuthenticationOptions.SecretId;
import org.springframework.vault.authentication.VaultToken;

VaultToken initialToken = VaultToken.of(
        requiredEnv("VAULT_APPROLE_BOOTSTRAP_TOKEN"));

AppRoleAuthenticationOptions options = AppRoleAuthenticationOptions.builder()
        .path("approle")
        .appRole("audit-consumer")
        .roleId(RoleId.provided(requiredEnv("VAULT_ROLE_ID")))
        .secretId(SecretId.pull(initialToken))
        .build();
~~~

Bootstrap token cần `update` trên `auth/approle/role/audit-consumer/secret-id`. Nó **không cần quyền đọc KV** chỉ để phát SecretID. Tuy nhiên token có khả năng tạo credential đăng nhập là thông tin nhạy cảm và phải giới hạn TTL, policy, đối tượng nhận và audit.

Khi cần xác thực mới, pull mode **có thể xin SecretID mới** nếu bootstrap token vẫn còn hiệu lực và quyền. Nó không tự tạo lại bootstrap token đã hết TTL hoặc hết lượt.

### 8.4. Chuyển sang response-wrapped SecretID

Nếu provisioner sinh SecretID và chỉ cấp wrapping token:

~~~java
import org.springframework.vault.authentication.AppRoleAuthenticationOptions;
import org.springframework.vault.authentication.AppRoleAuthenticationOptions.RoleId;
import org.springframework.vault.authentication.AppRoleAuthenticationOptions.SecretId;
import org.springframework.vault.authentication.VaultToken;

AppRoleAuthenticationOptions options = AppRoleAuthenticationOptions.builder()
        .path("approle")
        .roleId(RoleId.provided(requiredEnv("VAULT_ROLE_ID")))
        .secretId(SecretId.wrapped(VaultToken.of(
                requiredEnv("VAULT_WRAPPED_SECRET_ID_TOKEN"))))
        .build();
~~~

Spring Vault unwrap wrapper để lấy SecretID rồi login AppRole. **Wrapping token dùng một lần**: nếu ứng dụng restart hoặc cần login khác bằng cấu hình giữ wrapper cũ, việc unwrap lại có thể thất bại. Provisioner phải cấp **SecretID mới + wrapper mới** cho mỗi lần bootstrap/instance theo thiết kế này.

Không đưa wrapping token vào `SecretId.provided(...)`; phương thức đó yêu cầu **chuỗi SecretID thô**. Cũng không dùng cùng một wrapping token cho nhiều replica.

## 9. Vòng đời client token và ý nghĩa của renewal

### 9.1. SecretID không phải phiên truy cập API

AppRole login thành công trả client token với TTL, danh sách policy và thuộc tính renewable theo cấu hình. `VaultTemplate` cần token này cho request đọc KV, mã hóa Transit hoặc gọi PKI. Vòng đời token do Vault quyết định theo loại token, TTL, giới hạn maximum/explicit maximum, khả năng renewal, thu hồi và bound CIDR.

~~~mermaid
flowchart TD
    A["SecretID còn TTL/lượt"] --> B["AppRole login"]
    B --> C["Client token T1"]
    C --> D["VaultTemplate sử dụng T1"]
    D --> E{"T1 còn hợp lệ?"}
    E -- "Có" --> D
    E -- "Sắp hết TTL và renewable" --> F["SessionManager thử renew T1"]
    F --> D
    E -- "Hết hạn/không renew được" --> G["Cần tạo phiên mới"]
    G --> H{"Có credential AppRole hợp lệ?"}
    H -- "Có" --> B
    H -- "Không" --> I["Cấp SecretID/bootstrap credential mới"]
    I --> B
~~~

Sơ đồ diễn tả nguyên tắc vận hành, không bảo đảm mọi implementation tự làm đủ các bước mà không cấu hình. `LifecycleAwareSessionManager` có thể hỗ trợ gia hạn token nếu Vault cho phép; nó **không gia hạn `secret_id_ttl`** và không phục hồi số lượt `secret_id_num_uses`.

### 9.2. Token hết hạn, SecretID còn lượt

Nếu client token hết hạn nhưng SecretID vẫn còn TTL/lượt, một lần AppRole login mới có thể cấp token khác. Với mode `provided`, điều này chỉ thành công nếu credential cũ thực sự còn hợp lệ.

### 9.3. SecretID hết hạn, client token còn hạn

Nếu SecretID hết hạn lúc client token `T1` vẫn còn TTL, `T1` có thể tiếp tục dùng theo policy và điều kiện của chính token. Chỉ khi ứng dụng phải login lại mới gặp trở ngại từ SecretID.

### 9.4. Thu hồi SecretID sau khi token đã phát

Hủy SecretID ngăn các lần login mới bằng credential đó; không tự làm token `T1` đã cấp biến mất. Nếu nguyên nhân là nghi lộ SecretID, quy trình ứng phó cần tìm những token đã được cấp đáng ngờ và cân nhắc revoke những token đó riêng.

**Ngoài phạm vi SecretID:** dynamic secret lease của Vault (ví dụ database credentials) và chứng chỉ PKI có lịch sống/hủy riêng, không được đồng nhất với `secret_id_ttl` hay `token_ttl`.

## 10. Chọn TTL và số lượt theo workload

Không có một con số phù hợp cho mọi service. Bảng sau là các **kịch bản tham khảo**, không phải cấu hình production cố định.

| Kiểu workload | TTL SecretID cần cân nhắc | Số lượt dùng | Yêu cầu bổ sung |
| --- | --- | --- | --- |
| CI/CD job cấp credential sát giờ chạy | Ngắn hơn vòng đời job nếu login diễn ra ngay | Thường 1 | Provisioner cấp SecretID riêng/job và theo dõi độ trễ queue |
| Worker chạy một lần, có retry login | Đủ cho thời gian retry dự kiến | 1 nếu broker cấp lại nhanh, hoặc vài lượt có kiểm soát | Không dùng một SecretID chung cho nhiều job |
| Service có autoscaling nhiều replica | TTL tính theo startup delay | 1 cho từng replica nếu phát riêng | Cấp credential mới cho mỗi instance |
| Service dài hạn, tự restart | Chỉ TTL ngắn khi có broker/rotation | Phụ thuộc cơ chế phát lại | Có đường nhận SecretID mới khi restart/login lại |
| Service tự pull SecretID bằng bootstrap token | TTL ngắn có thể phù hợp | 1 nếu pull luôn cấp mới | Quản lý TTL/ACL của **bootstrap token** riêng |
| Lab học cách kiểm tra TTL/use-count | 1–5 phút | 2–3 | Dùng dữ liệu giả, không dùng token production |

Tư duy chọn tham số:

1. Đo **độ trễ cấp → nhận → login** ở percentile cao của CI, orchestrator và mạng để đặt TTL đủ cho startup.
2. Đếm số lần login cần trong vòng đời credential, kể cả retry, restart và replica. Đừng nhầm với số request đọc secrets.
3. Xác định ai có thể **phát SecretID mới** và cơ chế cung cấp lại khi hỏng mạng hoặc token hết hạn.
4. Áp dụng **CIDR và policy tối thiểu** cho cả giai đoạn login lẫn client token khi hạ tầng cho phép.
5. Theo dõi lỗi phân biệt TTL, hết lượt, credential sai, CIDR và token expired; tránh log SecretID.
6. Thử tình huống secret đã dùng hết trước khi chọn số lượt 1 cho service không có kênh cấp phát lại.

Nếu một ứng dụng đã có Kubernetes Auth hoặc cloud workload identity phù hợp, đánh giá sử dụng phương thức xác thực gốc thay vì quản lý SecretID dài hạn không có rotation.

## 11. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân đáng kiểm tra | Cách xác định |
| --- | --- | --- |
| AppRole login thành công ban đầu, restart sau vài phút lỗi | SecretID hết TTL hoặc hết lượt | Tra cứu credential qua accessor bởi provisioner; kiểm tra timeline deploy/login |
| Một replica login được, replica khác lỗi | Nhiều replica dùng chung SecretID ít lượt | Xem nơi phân phối credential, cấp SecretID riêng theo instance |
| Login bị từ chối ngay dù SecretID mới phát | RoleID/SecretID không thuộc cùng role, sai mount, CIDR chặn, hoặc payload sai | Kiểm tra role, endpoint, IP Vault nhìn thấy và thông tin phát credential |
| Đã tăng `secret_id_num_uses` nhưng credential cũ vẫn lỗi | SecretID cũ đã hết lượt/hết hạn | Phát credential mới; không xem cập nhật role là hồi sinh SecretID |
| Đăng nhập được nhưng `VaultTemplate` trả 403 | Client token thiếu policy, sai ACL path KV v2, token-bound CIDR hoặc token hết hiệu lực | Tách lỗi login khỏi lỗi yêu cầu KV, xem policy/path và token metadata |
| Client token dùng được vài lần rồi lỗi | `token_num_uses` quá thấp hoặc token hết TTL | Kiểm tra token config và `SessionManager`, không vội tăng use-count SecretID |
| `SecretId.wrapped(...)` lỗi khi restart | Wrapping token cũ đã unwrap | Phát SecretID và wrapper mới cho instance |
| `SecretId.pull(...)` không phát được SecretID mới | Bootstrap token hết TTL/lượt hoặc thiếu `update` | Kiểm tra bootstrap ACL trên `secret-id` endpoint |
| Accessor lookup không thấy credential | SecretID đã hết TTL, hết lượt, bị destroy hoặc sai role/accessor | Kiểm tra sự kiện cấp/hủy và audit logs; không lộ SecretID thô để debug |
| Client token vẫn truy cập được sau khi destroy SecretID | Hai vòng đời độc lập | Thu hồi token đã cấp riêng nếu yêu cầu ứng phó sự cố |

Cách điều tra theo **thứ tự request**:

1. `POST .../secret-id`: provisioner có tạo được credential mới không?
2. Nếu response-wrap: `POST sys/wrapping/unwrap` có nhận được SecretID và wrapper còn TTL không?
3. `POST auth/approle/login`: SecretID đúng role, còn TTL/lượt, đáp ứng CIDR không?
4. `GET secret/data/...`: client token có policy và còn TTL hợp lệ không?
5. Nếu lỗi xuất hiện sau thời gian dài: kiểm tra token renewal và lộ trình re-authentication.

Vault audit logs giúp nhận biết giai đoạn lỗi, nhưng không ghi trực tiếp SecretID, RoleID, client token, wrapping token hay dữ liệu secret vào log/trace/metric labels của ứng dụng.

## 12. Kiểm thử tích hợp có ý nghĩa

Một môi trường Vault dev/test riêng hoặc Testcontainers có thể dùng để tạo role, policy và SecretID giả cho từng test. Không chia sẻ SecretID giữa các test có quota lượt dùng, vì thứ tự chạy sẽ ảnh hưởng kết quả.

| Ca kiểm thử | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| **Login thành công** | SecretID mới phát, TTL/lượt đủ dùng | AppRole cấp client token và `VaultTemplate` đọc KV |
| **Hết lượt trước TTL** | `num_uses=2`, login thành công hai lần | Lần login thứ ba với cùng SecretID bị từ chối |
| **Hết TTL trước lần dùng đầu** | `ttl=30s`, để credential hết hạn trước login | Login bị từ chối dù chưa tiêu thụ lượt |
| **Giới hạn riêng nhỏ hơn role** | Role TTL 5m/3 lượt; phát TTL 2m/1 lượt | Credential được phát với giới hạn riêng và login tối đa 1 lần |
| **Yêu cầu vượt giới hạn role** | Role TTL 5m/3 lượt; cố phát TTL 10m/4 lượt | Vault từ chối giới hạn không hợp lệ |
| **Destroy qua accessor** | Tạo SecretID, lưu accessor, destroy trước login | Login bằng SecretID đó thất bại |
| **Token đã cấp trước destroy** | Login thành công, sau đó destroy SecretID | Token cũ vẫn chịu TTL/policy riêng; đọc KV nếu còn hợp lệ |
| **Policy chỉ read KV** | AppRole token đọc được secret | Thao tác update KV bị 403 |
| **Client token quota quá thấp** | `token_num_uses` hữu hạn nhỏ | Đọc KV liên tục có thể hết quota token dù SecretID còn TTL |
| **Provided khi restart** | `SecretId.provided` đã hết lượt | Khởi động lại thất bại nếu chưa cấp credential mới |
| **Pull khi restart** | Bootstrap token còn hiệu lực, ACL đủ | Có thể xin SecretID mới và đăng nhập lại |
| **Wrapped khi restart** | Dùng lại wrapping token đã unwrap | Unwrap lần sau thất bại; cần wrapper mới |
| **CIDR không khớp** | Workload tới Vault từ egress IP ngoài dải | Đăng nhập hoặc dùng client token bị chặn theo loại ràng buộc |

Để test hành vi thật của Spring Vault, tạo Spring Context với `AuditVaultConfig` và gọi `AuditConsumerSecrets.greeting()`. Kiểm tra kết quả đọc được `hello-vault` bằng token ứng dụng, rồi thay credential/ACL theo từng case. Test chỉ kiểm tra builder khác null sẽ **không chứng minh** TTL, số lượt và ACL của Vault hoạt động đúng.

### Bộ câu hỏi tự kiểm tra

**Câu 1.** SecretID có TTL 5 phút và `num_uses=1`. Sau một lần login thành công ở phút thứ nhất, ứng dụng gọi KV 20 lần qua cùng client token. Những request KV có nhất thiết tiêu hao thêm lượt SecretID không?

**Câu 2.** SecretID được phát lúc 09:00, TTL 2 phút, chưa từng dùng. Đến 09:03, ứng dụng lần đầu gọi login. Vì sao đăng nhập có thể thất bại?

**Câu 3.** Người vận hành destroy SecretID qua accessor sau khi service đã login. Vì sao việc destroy này chưa đủ để đảm bảo một client token nghi bị lộ sẽ không đọc dữ liệu nữa?

**Câu 4.** Hai replica cùng nhận một SecretID có `num_uses=1`. Replica thứ hai bị từ chối. Giải pháp nào phù hợp hơn việc tắt giới hạn lượt dùng cho toàn bộ role?

**Câu 5.** Service dùng `SecretId.pull(initialToken)` và mỗi SecretID chỉ login một lần. Tại sao service vẫn có thể gặp lỗi khi re-authentication dù Vault có thể sinh SecretID mới?

**Tiêu chí hoàn thành:** người học tính đúng giới hạn TTL/lượt, giải thích ba vòng đời SecretID/wrapping token/client token, tự tạo và tra cứu/hủy SecretID qua accessor, cấu hình Spring Vault đọc KV v2 theo policy tối thiểu, và xây được quy trình cấp credential mới khi restart/rotation.

## Tài liệu tham khảo

- [HashiCorp Vault — AppRole auth method](https://developer.hashicorp.com/vault/docs/auth/approle)
- [HashiCorp Vault — AppRole HTTP API: role options, SecretID issuance và accessor](https://developer.hashicorp.com/vault/api-docs/auth/approle)
- [HashiCorp Vault — Best practices for AppRole authentication](https://developer.hashicorp.com/vault/docs/auth/approle/approle-pattern)
- [HashiCorp Vault — Tokens, TTL và renewal](https://developer.hashicorp.com/vault/docs/concepts/tokens)
- [HashiCorp Vault — Response wrapping](https://developer.hashicorp.com/vault/docs/concepts/response-wrapping)
- [Spring Vault — Authentication Methods / AppRole](https://docs.spring.io/spring-vault/reference/vault/authentication.html)
- [Spring Vault — Imperative VaultTemplate](https://docs.spring.io/spring-vault/reference/vault/imperative-template.html)
- [Spring Vault — AppRoleAuthenticationOptions.SecretId API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AppRoleAuthenticationOptions.SecretId.html)
- [Spring Vault — AppRoleAuthentication API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AppRoleAuthentication.html)

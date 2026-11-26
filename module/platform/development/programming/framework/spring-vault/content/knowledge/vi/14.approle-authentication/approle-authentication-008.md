# Ràng buộc địa chỉ mạng và các điều kiện ở phía Vault

## 1. Mục tiêu và bối cảnh

Trong chương **Xác thực AppRole** của **SPRING_VAULT**, có RoleID và SecretID đúng **chưa đủ** để ứng dụng Java đăng nhập HashiCorp Vault. Vault còn kiểm tra những ràng buộc được cấu hình ở **phía server**, trong đó quan trọng nhất là dải IP nguồn (CIDR), thời hạn/số lượt dùng của SecretID, chính sách cấp token và các giới hạn của chính token.

Bài học này tập trung vào ba lớp kiểm soát:

1. **Điều kiện đăng nhập AppRole:** Vault có cho phép client từ địa chỉ mạng hiện tại gửi RoleID và SecretID để lấy token hay không?
2. **Điều kiện dùng token sau đăng nhập:** token được phát có thể được sử dụng từ địa chỉ mạng nào, trong bao lâu và với quyền gì?
3. **Điều kiện gắn với từng SecretID:** SecretID riêng cho instance có thể bị giới hạn chặt hơn role như thế nào?

Sau bài học, bạn sẽ có thể:

- Phân biệt `secret_id_bound_cidrs`, `cidr_list` lúc cấp SecretID và `token_bound_cidrs` ở cấp role/token riêng.
- Hiểu Vault lấy **IP nguồn nào** để kiểm tra CIDR trong hệ thống có NAT, reverse proxy, Kubernetes hoặc load balancer.
- Thiết kế AppRole có `bind_secret_id`, TTL, use count và token policy phù hợp với workload.
- Cấu hình AppRole ở Vault và dùng `AppRoleAuthentication`, `AppRoleAuthenticationOptions` cùng `VaultTemplate` để đọc KV v2.
- Chẩn đoán đúng lỗi đăng nhập so với lỗi dùng token, lỗi policy, lỗi TLS/mạng.
- Thiết kế các kiểm thử âm/dương với IP nguồn khác nhau mà **không giả mạo header IP**.

Ví dụ dùng **Vault local lab** và **Spring Vault Core 4.1.x** với Java 17+. Ở production cần TLS được xác minh, credential được cấp qua kênh tin cậy, policy tối thiểu và quan sát đúng mạng egress. Các dải `127.0.0.1/32` và `10.50.0.0/16` trong bài là **ví dụ**, không phải giá trị nên sao chép nguyên vào mọi môi trường.

## 2. Từ RoleID/SecretID đến token: Vault kiểm tra tại đâu?

Ở cấu hình AppRole thông dụng, phía Java sử dụng:

~~~java
AppRoleAuthenticationOptions options = AppRoleAuthenticationOptions.builder()
        .path("approle")
        .roleId(RoleId.provided(roleId))
        .secretId(SecretId.provided(secretId))
        .build();
~~~

Spring Vault gửi RoleID và SecretID tới endpoint `POST /v1/auth/approle/login`. Vault kiểm tra các điều kiện gắn với role và SecretID, rồi cấp **AppRole client token** nếu đăng nhập hợp lệ. Sau đó `VaultTemplate` dùng token này để đọc KV hoặc gọi Transit/PKI theo policy.

~~~mermaid
sequenceDiagram
    autonumber
    participant Java as Java / Spring Vault
    participant LB as NAT / LB / Proxy
    participant Auth as Vault AppRole auth
    participant Token as Vault token store
    participant KV as KV v2
    Java->>LB: POST auth/approle/login
    LB->>Auth: RoleID + SecretID, IP nguồn quan sát được
    Auth->>Auth: Kiểm tra role, TTL, uses, CIDR
    alt Không thỏa điều kiện
        Auth-->>Java: Login thất bại (400/403 tùy tình huống)
    else Đủ điều kiện
        Auth->>Token: Tạo client token, policies, bound CIDRs
        Auth-->>Java: Client token + TTL + policies
        Java->>LB: GET secret/data/apps/ledger (X-Vault-Token)
        LB->>KV: Request và IP nguồn quan sát được
        KV->>Token: Kiểm tra token, bound CIDRs, policy
        KV-->>Java: Dữ liệu hoặc lỗi token/ACL
    end
~~~

**Hai thời điểm kiểm tra khác nhau:**

- **Trước khi có token:** Vault có thể từ chối `auth/approle/login` dù RoleID và SecretID đúng vì IP nguồn không thuộc dải được chấp nhận, SecretID quá TTL/hết lượt, hoặc một điều kiện role khác không thỏa.
- **Sau khi có token:** request `GET secret/data/...` vẫn có thể bị từ chối do `token_bound_cidrs`, token hết hạn/revoke, policy không có `read` hoặc path sai.

Không gộp mọi lỗi `permission denied` thành lỗi SecretID; cần biết **endpoint nào trả lỗi**.

## 3. CIDR là gì và Vault so khớp ra sao?

**CIDR** (Classless Inter-Domain Routing) mô tả một dải địa chỉ IP bằng tiền tố mạng. Ví dụ:

| CIDR | Phạm vi minh họa | Ý nghĩa thực tế |
| --- | --- | --- |
| `127.0.0.1/32` | Đúng địa chỉ IPv4 loopback `127.0.0.1` | Dùng khi Vault và client tương tác local bằng IPv4 |
| `10.50.0.0/16` | Các địa chỉ từ `10.50.0.0` đến `10.50.255.255` | Ví dụ dải mạng private rộng của workload |
| `10.50.12.0/24` | Các địa chỉ `10.50.12.x` | Ví dụ mạng con chỉ dành cho một nhóm worker |
| `10.50.12.37/32` | Chỉ `10.50.12.37` | Ví dụ một egress gateway có IP ổn định |
| `2001:db8::/32` | Dải IPv6 dành cho tài liệu minh họa | Phải xem Vault thực sự quan sát kết nối IPv6 nào |

Ở production, **không nên chọn dải chỉ dựa vào IP của pod hoặc máy ảo**. Điều kiện Vault đánh giá địa chỉ phía client mà Vault thực sự nhìn thấy, có thể là địa chỉ sau NAT, SNAT, load balancer, service mesh hoặc một reverse proxy được tin cậy. Ngoài ra, địa chỉ dùng ở giai đoạn **login** và **request KV sau đó** có thể khác nhau nếu hệ thống định tuyến các request qua nhiều đường đi.

### 3.1. CIDR là giới hạn mạng, không phải danh tính workload

Một CIDR có thể bao gồm nhiều pod, node hoặc khách hàng đứng sau cùng egress gateway. Do đó:

- IP đúng **không thay thế** RoleID/SecretID, token hoặc policy.
- CIDR không bảo đảm request đến từ đúng ứng dụng nếu nhiều workload chia sẻ cùng IP egress.
- Cho phép `0.0.0.0/0` hoặc `::/0` về thực chất không thu hẹp nguồn truy cập theo họ IP tương ứng.
- CIDR quá hẹp có thể khóa ứng dụng khi đổi vùng, node, NAT gateway hoặc đường failover.
- Chỉ nên dùng CIDR sau khi đã quan sát được egress thực và có cơ chế kiểm thử, thay đổi, rollback.

CIDR là một lớp **defense in depth** bên cạnh credential, TLS và quyền truy cập. Không dùng nó để bù đắp việc quản lý SecretID kém.

## 4. Phân biệt chính xác ba loại CIDR AppRole

### 4.1. `secret_id_bound_cidrs`: ràng buộc **login** ở cấp role

Ví dụ cấu hình role:

~~~bash
vault write auth/approle/role/ledger-worker \
    bind_secret_id=true \
    secret_id_bound_cidrs="10.50.0.0/16"
~~~

`secret_id_bound_cidrs` giới hạn IP nguồn được phép **thực hiện AppRole login**. Nếu nguồn nằm ngoài dải, Vault từ chối đăng nhập dù credential đúng. Đây là điều kiện ở **phía Vault**, Spring Vault không thể bỏ qua bằng cách đổi builder.

Ở role có `bind_secret_id=true`, bạn vẫn phải có SecretID hợp lệ. Nếu SecretID riêng cũng có `cidr_list`, cả giới hạn cấp role và cấp SecretID phải phù hợp.

### 4.2. `cidr_list`: thu hẹp nơi sử dụng **SecretID riêng**

Khi provisioner tạo SecretID, có thể đặt một danh sách CIDR hẹp hơn cho credential đó:

~~~bash
vault write auth/approle/role/ledger-worker/secret-id \
    cidr_list="10.50.12.0/24" \
    ttl=10m \
    num_uses=1
~~~

Nếu role cho phép `10.50.0.0/16`, SecretID vừa phát chỉ được dùng login từ `10.50.12.0/24`. Nếu provisioner cố yêu cầu `cidr_list` vượt ra ngoài dải cấp role, Vault phải từ chối cấu hình không hợp lệ.

Ví dụ:

| Role `secret_id_bound_cidrs` | SecretID `cidr_list` | Kết quả |
| --- | --- | --- |
| `10.50.0.0/16` | `10.50.12.0/24` | Hợp lệ: SecretID được giới hạn hẹp hơn |
| `10.50.0.0/16` | `10.51.0.0/16` | Không hợp lệ: vượt phạm vi role |
| `10.50.12.0/24` | `10.50.12.37/32` | Hợp lệ: một IP cụ thể |
| Không đặt ràng buộc ở role | `10.50.12.0/24` | Có thể giới hạn SecretID riêng bằng CIDR này |

**Không nhầm tham số:** `secret_id_bound_cidrs` là **thuộc tính role**, còn `cidr_list` là **thuộc tính của SecretID khi cấp phát**. Đặt `cidr_list` ở phía Java `AppRoleAuthenticationOptions` không có tác dụng: đây không phải một phương thức builder của client.

### 4.3. `token_bound_cidrs`: ràng buộc **token sau login**

Role có thể cấu hình:

~~~bash
vault write auth/approle/role/ledger-worker \
    bind_secret_id=true \
    token_bound_cidrs="10.50.0.0/16"
~~~

Theo tài liệu Vault AppRole API, `token_bound_cidrs` ở cấp role xác định các dải IP được phép xác thực thành công và gắn dải đó vào **client token được cấp**. Token về sau bị giới hạn nơi có thể sử dụng. Vì vậy không nên diễn giải nó chỉ như một bộ lọc cho request KV sau login: ở cấp role, **quá trình login cũng có thể chịu ràng buộc này**.

Khi phát SecretID, provisioner còn có thể đặt `token_bound_cidrs` riêng:

~~~bash
vault write auth/approle/role/ledger-worker/secret-id \
    cidr_list="10.50.12.0/24" \
    token_bound_cidrs="10.50.12.0/24"
~~~

Theo AppRole API, `token_bound_cidrs` ở SecretID ghi đè giá trị cấp role khi phát token, nhưng nếu role đã đặt giới hạn thì dải riêng phải **nằm trong phạm vi cấp role**. Nó làm token sinh từ SecretID này chặt hơn, không được mở rộng quyền vượt giới hạn role.

### 4.4. Đừng coi ba giá trị là một

| Tên cấu hình | Đặt ở đâu? | Kiểm soát chính | Ai cần cấu hình? |
| --- | --- | --- | --- |
| `secret_id_bound_cidrs` | AppRole role | IP nguồn được phép login AppRole | Vault admin/IaC |
| `cidr_list` | Lệnh phát SecretID | IP nguồn được phép dùng **SecretID cụ thể** để login | Provisioner có quyền phát SecretID |
| `token_bound_cidrs` trên role | AppRole role | Giới hạn IP xác thực và giới hạn dùng token được cấp | Vault admin/IaC |
| `token_bound_cidrs` lúc phát SecretID | Lệnh phát SecretID | Dải IP áp dụng cho token sinh từ **SecretID này**, thu hẹp role | Provisioner có quyền phát SecretID |

Trong các dải ràng buộc đó, **giá trị rỗng** thường có nghĩa không áp đặt hạn chế CIDR bằng cấu hình tương ứng. Nó không có nghĩa token không bị giới hạn bởi TTL, policy, token type hay các control khác.

### 4.5. Ví dụ tổ hợp mạng có chủ đích

Giả sử một nhóm worker có egress ổn định:

~~~text
Mạng công ty / Vault cho login AppRole:   10.50.0.0/16
Một nhóm worker cần login:              10.50.12.0/24
Egress dùng client token của nhóm đó:   10.50.12.37/32
~~~

Một thiết kế có thể là:

~~~text
Role:
    secret_id_bound_cidrs = "10.50.0.0/16"
    token_bound_cidrs     = "10.50.0.0/16"

SecretID cấp riêng cho nhóm:
    cidr_list             = "10.50.12.0/24"
    token_bound_cidrs     = "10.50.12.37/32"
~~~

Ví dụ này có ý nghĩa **chỉ nếu** request từ worker đi tới Vault bằng các IP tương ứng và thực tế login/token use tuân theo các dải trên. Nếu login đi qua một egress IP khác với request KV, cần thiết kế lại path/tập CIDR cho phù hợp; đừng mặc định cấu hình trên sẽ hoạt động ở mọi Kubernetes cluster.

## 5. Các điều kiện khác được Vault kiểm tra ở cấp role

### 5.1. `bind_secret_id` và yêu cầu ít nhất một constraint

AppRole thông thường có `bind_secret_id=true`, nghĩa là login bắt buộc trình `secret_id` bên cạnh `role_id`.

~~~bash
vault write auth/approle/role/ledger-worker \
    bind_secret_id=true \
    secret_id_bound_cidrs="10.50.0.0/16"
~~~

Một AppRole cần có **ít nhất một ràng buộc** hợp lệ khi tạo hoặc cập nhật. Nếu tắt `bind_secret_id`, không nên tạo một role chỉ có RoleID rồi cấp quyền dữ liệu rộng mà không có điều kiện bảo vệ phù hợp. Với role không dùng SecretID, Spring Vault có `SecretId.absent()`, nhưng cấu hình phải khớp chính sách phía Vault và được đánh giá rủi ro.

**Không tắt `bind_secret_id` chỉ để chữa lỗi `permission denied`.** Trong phần lớn workload, giữ SecretID cùng policy và CIDR tối thiểu an toàn hơn.

### 5.2. TTL và số lần dùng của SecretID

| Field | Ý nghĩa | Tác động đến đăng nhập |
| --- | --- | --- |
| `secret_id_ttl` | Thời hạn SecretID | Hết TTL thì không dùng SecretID đó để login mới |
| `secret_id_num_uses` | Số lần SecretID có thể dùng để lấy token | Hết lượt thì login mới bị từ chối |
| `ttl`/`num_uses` lúc phát | Giá trị cho SecretID riêng, trong giới hạn role | Có thể làm credential hết hiệu lực sớm hơn |
| `local_secret_ids` | SecretID chỉ có phạm vi cluster local khi bật | Liên quan topology/replication, **không phải** giới hạn IP CIDR |

**Lưu ý `local_secret_ids`:** cờ này chỉ đặt được khi tạo role và không thể bật/tắt tùy ý sau đó. Đừng dùng nó thay cho `secret_id_bound_cidrs`; “local” ở đây không đồng nghĩa “chỉ được kết nối từ localhost”.

Các giới hạn TTL và số lượt kiểm tra ở **thời điểm login mới**. Client token đã được phát trước đó có vòng đời riêng.

### 5.3. Các thuộc tính ràng buộc token

| Field | Vai trò | Lưu ý vận hành |
| --- | --- | --- |
| `token_policies` | Policy được mã hóa trong token cấp qua AppRole | Chỉ cấp capability/path cần thiết cho workload |
| `token_no_default_policy` | Nếu bật, không tự gắn policy `default` | Phải hiểu tác động tới các API self-service cần thiết |
| `token_ttl` | TTL khởi tạo token | Còn chịu giới hạn mount/system |
| `token_max_ttl` | Trần TTL gia hạn theo cấu hình | Không hứa hẹn token renewable vô hạn |
| `token_explicit_max_ttl` | Trần TTL cứng có thể chặn renewal ngay cả khi token có thể gia hạn | Đặc biệt quan trọng cho service dài hạn |
| `token_num_uses` | Giới hạn số lần client token có thể được dùng | **Khác** `secret_id_num_uses` |
| `token_type` | Loại token như `service` hoặc `batch` | Batch token không có cùng tính năng gia hạn như service token |
| `token_period` | Thiết lập cho periodic token | Chỉ dùng sau khi hiểu token renewal và trần TTL liên quan |
| `token_bound_cidrs` | Gắn dải IP vào token / điều kiện login cấp role | Có thể làm request fail khi mạng egress đổi |

Policy Vault là cơ chế authorization ở tầng **path/capability**; CIDR kiểm soát nguồn request, không cấp thêm quyền dữ liệu. Một token hợp lệ từ mạng đúng **vẫn nhận 403** nếu gọi path ngoài policy.

### 5.4. Điều kiện tạo SecretID và metadata

Provisioner có thể cấp SecretID với `cidr_list`, `token_bound_cidrs`, `ttl`, `num_uses` và `metadata`. Nếu role đã định các ràng buộc hữu hạn, giá trị riêng phải phù hợp với role. Phía Vault sẽ đánh giá cả hai lớp.

Metadata có thể được đưa vào audit logs dưới dạng plaintext; **không đặt token, password hoặc dữ liệu nhạy cảm vào metadata**. Chỉ nên đặt nhận dạng môi trường/instance không bí mật và tuân thủ quy định lưu trữ log.

## 6. IP nguồn thực tế: NAT, Kubernetes, load balancer và proxy

### 6.1. IP trong container không nhất thiết là IP Vault nhìn thấy

Ví dụ Java worker có:

~~~text
Pod IP:             10.244.1.42
Node IP:            10.50.12.18
Egress Gateway IP:  10.50.12.37
Vault IP:           10.90.0.20
~~~

Nếu traffic đi qua SNAT/egress gateway, Vault có thể nhìn thấy **10.50.12.37**. Khi đó:

- `secret_id_bound_cidrs="10.244.0.0/16"` có thể **không** khớp tại login.
- `token_bound_cidrs="10.50.12.37/32"` có thể phù hợp nếu mọi request dùng token đều đi qua gateway đó.
- Nếu Vault thực ra nhìn thấy IP của load balancer hoặc proxy, phải xem cấu hình listener/trust để biết IP nào được dùng trong việc kiểm tra.

Không suy ra IP nguồn chỉ từ lệnh `ip addr` trong container. Hãy đối chiếu kiến trúc mạng và Vault audit record `remote_address` trong môi trường đã bảo vệ quyền truy cập.

### 6.2. Trường hợp reverse proxy gửi `X-Forwarded-For`

Vault có hỗ trợ các cấu hình listener liên quan đến IP gốc, trong đó có:

- `x_forwarded_for_authorized_addrs`: các địa chỉ proxy/load balancer **được Vault tin cậy** để cung cấp header `X-Forwarded-For`.
- `x_forwarded_for_hop_skips`: lựa chọn hop từ chuỗi proxy khi cần xử lý nhiều tầng.
- `x_forwarded_for_reject_not_authorized` và `x_forwarded_for_reject_not_present`: hành vi khi header/nguồn không thỏa điều kiện.

Các cài đặt này thuộc **cấu hình Vault listener** do đội vận hành hạ tầng quản lý, không phải tham số `AppRoleAuthenticationOptions`. Phải chỉ tin cậy proxy được kiểm soát, bảo đảm proxy xử lý header gốc đúng cách và test toàn bộ topology.

**Không giải quyết lỗi CIDR bằng cách tự thêm header `X-Forwarded-For` ở Java.** Nếu server tin các header do client không tin cậy tự khai, một bên tấn công có thể giả mạo IP nguồn. Chỉ triển khai cơ chế này qua proxy nằm trong miền tin cậy với `authorized_addrs` hẹp và cách chọn hop đúng.

### 6.3. Các kịch bản mạng cần thử

| Kịch bản | Rủi ro CIDR | Điều nên kiểm tra |
| --- | --- | --- |
| Vault chạy local, Java nối qua localhost | `127.0.0.1/32` khớp IPv4 loopback, nhưng `::1` khác | Client dùng IPv4 hay IPv6? |
| Pod đi qua NAT gateway cố định | Vault thấy IP gateway thay cho IP pod | Gateway/IP egress có ổn định không? |
| Mở rộng nhiều vùng/zone | Mỗi vùng có một hoặc nhiều IP egress | Tập CIDR có bao phủ các nguồn hợp lệ? |
| Load balancer trước Vault | Vault có thể thấy IP của LB hoặc IP gốc được forwarding | Listener/trusted proxy cấu hình thế nào? |
| VPN thay đổi/luân chuyển egress | Login tốt nhưng request KV từ tuyến mới bị chặn | Lộ trình token-bound CIDR và failover |
| Vault cluster/namespace khác | Mount/policy/role và đường kết nối có thể khác | Đúng Vault address, namespace, auth mount không? |

Đừng mở rộng CIDR thành `0.0.0.0/0` chỉ vì chưa xác định được IP nguồn. Hãy đo và kiểm tra trước, rồi cấu hình chính xác theo mạng được phê duyệt.

## 7. Lab A: cấu hình AppRole có CIDR dùng được từ localhost

Phần này cố ý dùng **`127.0.0.1/32`** để người học có thể thực hành trên Vault dev và Java cùng máy qua IPv4. Nếu chạy trong Docker/Kubernetes với network bridge, cần thay CIDR bằng IP nguồn **mà Vault thực sự nhìn thấy**, không sao chép `127.0.0.1/32` rồi kỳ vọng thành công.

### 7.1. Chuẩn bị auth method và KV v2

Với một Vault local/dev đã init/unseal, shell quản trị có token đủ quyền:

~~~bash
export VAULT_ADDR="http://127.0.0.1:8200"

# Chỉ chạy khi mount auth/approle chưa tồn tại:
vault auth enable approle

# Chỉ chạy khi secret/ chưa tồn tại là KV v2:
vault secrets enable -path=secret -version=2 kv

# Secret giả cho bài tập, không phải dữ liệu production.
vault kv put secret/apps/ledger message="cidr-ok"
~~~

Nếu mount đã tồn tại, bỏ qua lệnh enable tương ứng. Không đổi mount đang sử dụng của hệ thống khác để chạy bài thử.

### 7.2. Policy chỉ cho đọc một secret KV v2

Tạo file `ledger-read.hcl` trên máy lab:

~~~hcl
path "secret/data/apps/ledger" {
  capabilities = ["read"]
}
~~~

Nạp policy:

~~~bash
vault policy write ledger-read ledger-read.hcl
~~~

Với KV v2, logical path của CLI là `secret/apps/ledger`, nhưng ACL sử dụng đường dẫn API có thành phần `data/`: `secret/data/apps/ledger`.

### 7.3. Tạo role ràng buộc CIDR cho login và token

~~~bash
vault write auth/approle/role/ledger-worker \
    bind_secret_id=true \
    secret_id_bound_cidrs="127.0.0.1/32" \
    token_bound_cidrs="127.0.0.1/32" \
    secret_id_ttl=15m \
    secret_id_num_uses=3 \
    token_policies="ledger-read" \
    token_ttl=20m \
    token_max_ttl=1h \
    token_type=service \
    token_num_uses=0

vault read auth/approle/role/ledger-worker
~~~

Ở đây:

- AppRole login cần RoleID và SecretID.
- Request login phải có IP nguồn hợp lệ với ràng buộc role.
- Token sau login cũng bị giới hạn bởi `token_bound_cidrs`.
- SecretID có TTL và số lượt; token có TTL và use-count riêng.
- Token chỉ đọc KV path được cấp.

**Không dùng root token trong ứng dụng.** Token quản trị chỉ nên dùng khi tạo role, policy và phát credential trong môi trường lab/provisioner.

### 7.4. Cấp SecretID riêng, thu hẹp điều kiện

Provisioner tạo một SecretID với TTL/lượt hạn chế hơn:

~~~bash
vault write auth/approle/role/ledger-worker/secret-id \
    cidr_list="127.0.0.1/32" \
    token_bound_cidrs="127.0.0.1/32" \
    ttl=5m \
    num_uses=2
~~~

Vault trả `secret_id` và `secret_id_accessor`. Hãy truyền SecretID thật cho ứng dụng lab qua kênh tin cậy; không ghi vào repo. `secret_id_accessor` có thể dùng để tra cứu hoặc hủy SecretID theo policy provisioner, **không** dùng thay SecretID lúc login.

Với CIDR `127.0.0.1/32`, client **phải thực sự truy cập từ IPv4 loopback**. Nếu ở máy/VM/container khác, sẽ gặp lỗi dù dữ liệu role và SecretID hoàn toàn đúng.

### 7.5. Thử đăng nhập tại máy local

Provisioner đọc RoleID:

~~~bash
vault read -field=role_id \
    auth/approle/role/ledger-worker/role-id
~~~

Trong lab cô lập, có thể kiểm tra login với placeholder:

~~~bash
vault write auth/approle/login \
    role_id="<ROLE_ID_LAB>" \
    secret_id="<SECRET_ID_LAB>"
~~~

Ví dụ sẽ in client token khi thành công. **Chỉ thực hiện với credential giả trong môi trường lab**; CLI args và output có thể xuất hiện trong history, process inspection hoặc log shell. Trong production hãy dùng kênh cấp phát/authentication của ứng dụng và không đưa secret vào command line.

Nếu login thành công, token mang policy `ledger-read` và ràng buộc CIDR. Nếu client IPv6 kết nối tới `::1` hoặc network bridge làm Vault quan sát IP khác, lỗi CIDR là kết quả đúng của cấu hình này.

## 8. Lab B: kiểm chứng dải con và ràng buộc token ở môi trường có egress ổn định

Phần này **chỉ là kịch bản staging**; không chạy nguyên lệnh trên Vault local đang dùng trong Lab A trừ khi bạn có mạng như ví dụ.

Giả sử egress IP của client thuộc `10.50.12.0/24`, mạng rộng được admin chấp thuận là `10.50.0.0/16`.

~~~bash
# Chỉ cho staging có egress thực thuộc 10.50.0.0/16.
vault write auth/approle/role/ledger-worker \
    bind_secret_id=true \
    secret_id_bound_cidrs="10.50.0.0/16" \
    token_bound_cidrs="10.50.0.0/16" \
    secret_id_ttl=10m \
    secret_id_num_uses=1 \
    token_policies="ledger-read" \
    token_ttl=20m \
    token_type=service
~~~

Provisioner phát SecretID riêng cho nhóm worker:

~~~bash
vault write auth/approle/role/ledger-worker/secret-id \
    cidr_list="10.50.12.0/24" \
    token_bound_cidrs="10.50.12.0/24" \
    ttl=5m \
    num_uses=1
~~~

**Kỳ vọng** nếu topology đúng:

| Request | IP nguồn Vault quan sát | Kết quả mong đợi |
| --- | --- | --- |
| AppRole login bằng SecretID riêng | `10.50.12.37` | Được phép nếu các điều kiện khác hợp lệ |
| AppRole login bằng SecretID riêng | `10.50.13.42` | Bị từ chối bởi `cidr_list` của SecretID |
| AppRole login bằng SecretID riêng | `10.51.0.10` | Bị từ chối bởi ràng buộc CIDR ở role |
| Đọc KV bằng client token đã cấp | `10.50.12.37` | Có thể thành công nếu token còn hạn, đủ policy |
| Đọc KV bằng cùng token | `10.50.13.42` | Bị từ chối bởi giới hạn `token_bound_cidrs` của token |

**Quan trọng:** không dùng **cùng SecretID `num_uses=1`** để chạy nhiều lần login dương/âm rồi suy luận về CIDR; credential có thể đã hết lượt. Mỗi ca test nên cấp **SecretID riêng** với cùng các điều kiện, hoặc kiểm soát chính xác số lượt còn lại. Đối với thử token từ IP khác, phải có khả năng gửi request từ **một client/network thực** khác, không giả mạo header tự khai.

### 8.1. Cố phát SecretID ngoài dải role

Một ca kiểm thử âm:

~~~bash
# Role chỉ cho phép 10.50.0.0/16; SecretID đề nghị ở ngoài dải.
vault write auth/approle/role/ledger-worker/secret-id \
    cidr_list="10.51.0.0/16"
~~~

Vault phải từ chối yêu cầu không phù hợp vì dải `cidr_list` vượt `secret_id_bound_cidrs`. Tương tự, per-SecretID `token_bound_cidrs` phải nằm trong phạm vi token-bound CIDR mà role giới hạn.

## 9. Tích hợp với Spring Vault và VaultTemplate

### 9.1. Điều kiện CIDR nằm ở Vault, không phải ở Java builder

Trong Spring Vault, `AppRoleAuthenticationOptions` mô tả **cách lấy RoleID/SecretID** và mount path; nó không có trách nhiệm tự đặt `secret_id_bound_cidrs` hay `token_bound_cidrs`. Những ràng buộc này thuộc quản trị AppRole và lệnh cấp SecretID phía Vault.

Khi Java có credential hợp lệ, có thể dùng provided mode:

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
public class LedgerVaultConfig extends AbstractVaultConfiguration {

    @Override
    public VaultEndpoint vaultEndpoint() {
        // Production: HTTPS và CA/truststore hợp lệ.
        return VaultEndpoint.from(URI.create(requiredEnv("VAULT_ADDR")));
    }

    @Override
    public ClientAuthentication clientAuthentication() {
        String roleId = requiredEnv("VAULT_ROLE_ID");
        String secretId = requiredEnv("VAULT_SECRET_ID");

        AppRoleAuthenticationOptions options =
                AppRoleAuthenticationOptions.builder()
                        .path("approle")
                        .roleId(RoleId.provided(roleId))
                        .secretId(SecretId.provided(secretId))
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

Ví dụ sử dụng Spring Vault Core 4.1.x, nơi `AppRoleAuthentication` có constructor nhận `vaultClient()`. Một số phiên bản cũ có constructor khác, nên kiểm tra Javadoc/version đang sử dụng. Hệ thống triển khai phải inject `VAULT_ADDR`, `VAULT_ROLE_ID` và `VAULT_SECRET_ID`, không hard-code secret.

**Quan sát quan trọng:** nếu ứng dụng chạy ngoài địa chỉ nguồn CIDR mà Vault chấp thuận, mã Java trên vẫn bị từ chối login. Thay `RestClient`, dùng lại RoleID hoặc tăng timeout **không giải quyết** sai lệch mạng.

### 9.2. Đọc KV v2 để kiểm tra cả token policy lẫn token-bound CIDR

~~~java
package example.vault;

import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.VaultResponse;

@Service
public class LedgerSecrets {

    private final VaultTemplate vaultTemplate;

    public LedgerSecrets(VaultTemplate vaultTemplate) {
        this.vaultTemplate = vaultTemplate;
    }

    public String loadMessage() {
        VaultResponse response = vaultTemplate
                .opsForKeyValue("secret", KeyValueBackend.KV_2)
                .get("apps/ledger");

        if (response == null) {
            throw new IllegalStateException("KV secret not found");
        }

        Map<String, Object> data = response.getRequiredData();
        Object message = data.get("message");

        if (!(message instanceof String)) {
            throw new IllegalStateException("KV value has invalid type");
        }
        return (String) message;
    }
}
~~~

Kết quả mong đợi từ Lab A là `cidr-ok` khi Java đi qua `127.0.0.1` và token có `read` trên `secret/data/apps/ledger`. Nếu Java chạy ở máy khác và kết nối Vault qua một dải ngoài CIDR được phép, bạn cần thay lab config để phù hợp với topology test đã biết.

**Phân biệt path:** trong Java dùng `opsForKeyValue("secret", KV_2).get("apps/ledger")`, còn Vault policy phải cấp `read` trên `secret/data/apps/ledger`. Lỗi 403 sau login có thể do **policy** dù CIDR của token hoàn toàn hợp lệ.

### 9.3. Provided, pull và wrapped đều chịu giới hạn phía Vault

| Kiểu lấy SecretID ở Spring Vault | Đầu vào | CIDR có được Spring Vault bỏ qua không? |
| --- | --- | --- |
| `SecretId.provided(secretId)` | SecretID được cấp sẵn | Không. Vault vẫn kiểm tra role/SecretID CIDR ở login |
| `SecretId.pull(initialToken)` | Bootstrap token có quyền phát SecretID | Không. Bước pull đòi quyền ACL riêng, sau đó login vẫn chịu CIDR |
| `SecretId.wrapped(wrappingToken)` | Token bọc có TTL ngắn và dùng một lần | Không. Unwrap thành công chưa có nghĩa login từ IP hiện tại hợp lệ |
| `SecretId.absent()` | Không có SecretID | Chỉ hợp lệ với role có `bind_secret_id=false` và ràng buộc tương ứng |

Với `pull`, bootstrap token còn có ACL/TTL/use limits riêng và có thể bị ràng buộc mạng. Với `wrapped`, wrapping token chỉ unwrap một lần; nếu unwrap thành công nhưng AppRole login bị chặn bởi CIDR, bạn có thể đã tiêu thụ wrapper mà vẫn chưa có client token. Cần thiết kế kênh cấp lại credential thay vì retry bằng wrapper cũ.

## 10. Vòng đời token khi egress IP thay đổi

Hãy xét một service login thành công từ IP `10.50.12.37`. Token được cấp bị ràng buộc vào `10.50.12.0/24`. Sau đó service chuyển node hoặc route failover khiến request đi từ IP `10.50.14.9`.

- **SecretID không được gửi** trong mỗi request KV. Do đó lỗi truy cập lúc này chưa chắc liên quan đến SecretID.
- Vault kiểm tra token và `token_bound_cidrs` ở request tiếp theo; ngoài dải thì có thể bị từ chối.
- Dù token chưa hết TTL và token policy vẫn cho `read`, ràng buộc network vẫn có hiệu lực.
- Việc `SessionManager` cố renew token cũng có thể bị ảnh hưởng nếu request renewal đi từ IP không được phép.
- AppRole login mới có thể bị từ chối bởi `secret_id_bound_cidrs` hoặc `cidr_list` nếu egress mới không hợp lệ.

`LifecycleAwareSessionManager` có thể hỗ trợ gia hạn **client token** khi Vault cho phép, nhưng không sửa chính sách CIDR, không kéo dài SecretID TTL và không tự tìm đúng đường egress.

Một kế hoạch vận hành cần quyết định: giới hạn CIDR vào **egress gateway ổn định**, dùng dải bao phủ có kiểm soát, hay cấp token/SecretID mới cho vùng mới. Không vô hiệu hóa toàn bộ IP restriction chỉ để tránh thiết kế đường mạng.

## 11. Bảo mật, quyền quản trị và thay đổi cấu hình

### 11.1. Tách các danh tính/role vận hành

| Thành phần | Quyền nên có | Không nên có nếu không cần |
| --- | --- | --- |
| **Vault admin/IaC** | Tạo auth mount, role, cập nhật CIDR, TTL, policy | Dùng root token trong JVM |
| **Provisioner** | `update` trên SecretID endpoint đúng role, `read` role-id khi cần | Policy đọc toàn bộ KV nghiệp vụ |
| **Workload Java** | Credential AppRole được phân phối và token chỉ cho phép API nghiệp vụ cần thiết | Quyền tạo SecretID, sửa role hoặc policy |
| **Operator/auditor** | Tra cứu cấu hình và audit phù hợp trách nhiệm | Truy cập SecretID/client token thô không cần thiết |

Vault có endpoint riêng cho cập nhật `secret-id-bound-cidrs` và `token-bound-cidrs` của role, giúp phân quyền quản trị chi tiết thay vì cấp `sudo` hoặc root trên mọi auth method. Khi thay đổi CIDR, cần theo quy trình change management, kiểm thử canary và rollback.

### 11.2. Đừng khóa tất cả instance bằng một thay đổi thiếu kiểm chứng

Một kế hoạch đổi CIDR:

1. Xác định danh sách egress IP thực (login và request API) của từng vùng/cluster, kể cả DR/failover.
2. Xác nhận nguồn nào Vault nhìn thấy qua audit record/mạng và cấu hình proxy tin cậy.
3. Tạo role/staging test với dải mới và credential test riêng; xác minh login cùng request KV.
4. Thử từ một nguồn nằm **ngoài** dải để xác minh ràng buộc thực sự có hiệu lực.
5. Triển khai theo canary, giám sát tỷ lệ login/token failure; chuẩn bị rollback.
6. Đánh giá token đang lưu và SecretID đã phát: thay đổi cấu hình role không nhất thiết viết lại mọi thuộc tính của token/SecretID cũ. Cấp mới và revoke có chủ đích theo chính sách thay đổi/sự cố.

Không đặt `0.0.0.0/0` tạm thời mà quên rollback. Nếu cần khôi phục dịch vụ, hãy dùng quy trình truy cập khẩn cấp được phê duyệt và giới hạn thời gian.

### 11.3. CIDR không thay TLS, policy hay bảo vệ credential

Ngay cả khi IP thuộc dải, Vault vẫn cần xác thực credential và policy. Bảo vệ RoleID/SecretID, bootstrap token, wrapping token và client token khỏi log/trace/backup; dùng response wrapping hoặc secret injection khi phù hợp; giới hạn thời hạn/lượt dùng; không đưa secret thật vào tham số lệnh trên môi trường chia sẻ.

Các giá trị `token_policies`, `token_no_default_policy` và `token_num_uses` có thể tác động mạnh đến tính sẵn sàng và quyền; hãy hiểu chúng trước khi đổi để “sửa” lỗi IP.

## 12. Bảng chẩn đoán lỗi theo tầng

| Triệu chứng | Tầng xảy ra | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- | --- |
| Login 403 dù RoleID/SecretID đúng | AppRole login | IP nguồn ngoài `secret_id_bound_cidrs` hoặc `cidr_list`; cũng có thể `token_bound_cidrs` role | Đối chiếu IP Vault nhìn thấy, role config và SecretID metadata |
| Login thành công tại máy A, bị từ chối tại máy B | AppRole login | CIDR không bao gồm máy B hoặc B đi qua NAT khác | Kiểm tra egress thực thay vì IP gán trong pod |
| Login từ IPv4 thành công nhưng IPv6 thất bại | AppRole login | Chỉ cho `127.0.0.1/32`, chưa có `::1/128` | Kiểm tra DNS, IP family của kết nối và cấu hình CIDR |
| Provisioner không phát SecretID với dải rộng hơn role | Issue SecretID | `cidr_list` hoặc per-secret `token_bound_cidrs` vượt phạm vi role | Kiểm tra tính bao hàm CIDR |
| Đã có token nhưng đọc KV 403 sau đổi tuyến | Token use | `token_bound_cidrs` chặn egress mới | Xem bound CIDRs của token và IP nguồn request |
| Đã có token nhưng đọc KV 403 dù IP đúng | Authorization | `token_policies` thiếu `read`, path KV v2 sai, token hết hạn | Kiểm tra policies, `secret/data/...` và TTL |
| Đọc KV 404 hoặc `null` | Secret engine/path | Sai mount, backend KV1/KV2, dữ liệu chưa tồn tại | Xác minh logical path và KV v2 |
| Một replica login được, replica khác không | Deployment | IP egress khác, SecretID hết lượt, SecretID khác role | Kiểm tra từng điều kiện riêng, cấp credential theo replica |
| Sau vài giờ có lỗi token renew | SessionManager/token | Token hết TTL/trần renewal hoặc request renew từ IP không hợp lệ | Kiểm tra token type/TTL/renewable và network path |
| `SecretId.wrapped(...)` unwrap được rồi login lỗi | Unwrap → login | Wrapper hợp lệ nhưng CIDR AppRole hoặc SecretID không khớp | Cấp wrapper/SecretID mới sau khi sửa điều kiện mạng |
| Đổi `path("approle")` sang mount khác rồi lỗi | Auth path | Sai mount, namespace hoặc role ID/SecretID của mount khác | So sánh `path`, auth mount và role |
| IP ghi trong audit không như dự tính | Network listener | NAT, LB, proxy forwarding hoặc trust config | Kiểm tra Vault listener và proxy; không tin header client tùy tiện |

Cách điều tra đúng thứ tự:

1. Xác định request thất bại: **phát SecretID**, **unwrap**, **AppRole login** hay **VaultTemplate đọc KV**.
2. Đối chiếu `VAULT_ADDR`, TLS, auth mount, role, TTL và số lượt trước.
3. Đối chiếu **IP nguồn mà Vault quan sát**, không chỉ IP trong container.
4. Xem `secret_id_bound_cidrs` ở role và `cidr_list` của SecretID cho lỗi login.
5. Xem `token_bound_cidrs` và policies/TTL của **client token** cho lỗi request sau login.
6. Dùng Vault audit/metrics đã bảo vệ; không log RoleID, SecretID, wrapping token hay client token.

## 13. Kiểm thử tích hợp với nguồn mạng xác định

Một môi trường Vault dev/staging hoặc Testcontainers có thể tạo role và credential để kiểm tra policy/TTL. Tuy nhiên, **một test chạy từ đúng một IP nguồn không thể chứng minh ràng buộc CIDR với nhiều nguồn mạng**. Nên tổ chức hai lớp test:

- **Test logic/API:** tạo role, phát SecretID, xác minh cấu hình CIDR subset, login và đọc KV từ nguồn được phép.
- **Test network end-to-end:** gửi login và request token từ hai workload/egress **thực sự khác nhau** mà Vault thấy được, có network setup tái hiện được.

| Ca kiểm thử | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Local happy path | Cả role và SecretID cho `127.0.0.1/32` | Java local login và đọc `cidr-ok` |
| Sai IP khi login | Client thực từ IP ngoài `secret_id_bound_cidrs` | AppRole login bị từ chối |
| SecretID CIDR hẹp hơn role | Role `10.50.0.0/16`; SecretID `10.50.12.0/24` | Login ngoài `10.50.12.0/24` thất bại |
| Cấp SecretID vượt role | Role `10.50.0.0/16`; xin `cidr_list=10.51.0.0/16` | Vault từ chối yêu cầu cấp credential |
| Token-bound CIDR | Client token gắn `10.50.12.0/24`, sử dụng từ mạng khác | Request dùng token bị từ chối |
| Token đúng IP, policy thiếu | AppRole token không có `read` KV path | Login được nhưng `VaultTemplate` trả 403 |
| SecretID hết lượt | `num_uses=1`, login hai lần độc lập với cùng SecretID | Login lần sau bị từ chối |
| SecretID hết TTL | `ttl=30s`, chờ quá hạn | Login bị từ chối dù IP đúng |
| Source IP đổi do failover | Cùng token, hai egress thực khác nhau | Thấy rõ token-bound effect |
| Token renewable nhưng network đổi | Yêu cầu renew từ mạng ngoài token-bound CIDR | Renewal có thể bị Vault từ chối |
| Wrapped SecretID, login sai CIDR | Unwrap hợp lệ, request login ngoài dải | Unwrap xong vẫn không có AppRole token |
| CIDR và token policy đồng thời | Nguồn đúng dải, nhưng KV operation không được phép | Vault vẫn từ chối yêu cầu ngoài quyền |

Không tự thêm header `X-Forwarded-For` để mô phỏng IP ngoài dải: điều đó **không phải phép kiểm thử có giá trị** trừ khi bạn đang kiểm thử chính xác một proxy được Vault tin cậy và cách proxy xử lý header. Test nên có network namespace, worker node hoặc egress gateway khác nhau thật.

### 13.1. Ví dụ Spring integration test cho đường đi hợp lệ

~~~java
package example.vault;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

// Vault test đã được provision AppRole/KV, credential qua env, mạng hợp CIDR.
// Chỉ dành cho integration test, không chạy với Vault production.
@SpringBootTest
class LedgerSecretsIT {

    @Autowired
    LedgerSecrets secrets;

    @Test
    void readsKvWhenRoleTokenAndNetworkConstraintsAreSatisfied() {
        assertEquals("cidr-ok", secrets.loadMessage());
    }
}
~~~

Ví dụ giả định dự án dùng Spring Boot Test và môi trường integration đã provision Vault/secret đúng. Nếu ứng dụng chỉ dùng Spring Framework thuần thì có thể thay bằng Spring Test với `@ContextConfiguration`. **Không chỉ assert builder khác null**; cần kiểm chứng request thật và kết quả Vault trả.

### 13.2. Bài tập tư duy

**Bài tập 1 — IP nguồn.** Worker có Pod IP `10.244.2.9` nhưng Vault audit thấy `10.50.12.37`. Bạn nên kiểm chứng dải CIDR nào cho login và token use? Vì sao không thể chỉ dựa vào Pod IP?

**Bài tập 2 — giới hạn hai lớp.** Role `secret_id_bound_cidrs=10.50.0.0/16` và một SecretID có `cidr_list=10.50.12.0/24`. Client từ `10.50.13.9` có RoleID/SecretID đúng. Vault nên cho login không?

**Bài tập 3 — token sau login.** Service login tại `10.50.12.37` và nhận token chỉ sử dụng được từ `10.50.12.0/24`. Sau khi failover, request KV tới Vault từ `10.50.14.2`. Vì sao request có thể bị từ chối dù token chưa hết TTL và policy đúng?

**Bài tập 4 — quyền dữ liệu.** AppRole client token có CIDR hợp lệ, nhưng `token_policies` không có `read` trên `secret/data/apps/ledger`. Bạn cần thay đổi CIDR hay ACL? Vì sao?

**Bài tập 5 — thay đổi an toàn.** Lập kế hoạch chuyển egress gateway từ `10.50.12.37` sang `10.50.14.2` mà không dừng mọi replica; nêu cách kiểm tra trước, canary, audit và rollback.

**Tiêu chí hoàn thành:** bạn giải thích đúng vai trò các CIDR tại login và token use, kiểm tra được constraint role/SecretID, cấu hình Java Spring Vault đọc KV v2 bằng token có policy tối thiểu, phân biệt được lỗi network với lỗi auth/authorization và thiết kế được bài test có **IP nguồn thực**.

## Tài liệu tham khảo

- [HashiCorp Vault — AppRole HTTP API: role settings, SecretID fields, CIDR](https://developer.hashicorp.com/vault/api-docs/auth/approle)
- [HashiCorp Vault — AppRole auth method: Credentials and Constraints](https://developer.hashicorp.com/vault/docs/auth/approle)
- [HashiCorp Vault — Best practices for AppRole authentication](https://developer.hashicorp.com/vault/docs/auth/approle/approle-pattern)
- [HashiCorp Vault — TCP listener: X-Forwarded-For và trusted proxy](https://developer.hashicorp.com/vault/docs/configuration/listener/tcp)
- [HashiCorp Vault — Token concepts và TTL](https://developer.hashicorp.com/vault/docs/concepts/tokens)
- [Spring Vault — Authentication Methods, AppRole](https://docs.spring.io/spring-vault/reference/vault/authentication.html)
- [Spring Vault — AppRoleAuthentication API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AppRoleAuthentication.html)
- [Spring Vault — AppRoleAuthenticationOptions API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AppRoleAuthenticationOptions.html)
- [Spring Vault — VaultTemplate imperative API](https://docs.spring.io/spring-vault/reference/vault/imperative-template.html)

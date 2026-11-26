# Secret tĩnh, secret động và vòng đời sử dụng

> **Chương:** Bản đồ Spring Vault  
> **Bối cảnh:** Một ứng dụng Java dùng Spring Vault có thể đọc API key lưu trong KV, nhận tài khoản cơ sở dữ liệu được tạo theo yêu cầu, sử dụng token đăng nhập Vault, gọi Transit và xin chứng chỉ PKI. Các giá trị này không cùng cách phát hành, thời hạn hoặc cách thu hồi.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **secret tĩnh (static secret)** và **secret động (dynamic secret)** bằng nguồn phát hành, phạm vi quyền, TTL và cơ chế thu hồi.
2. Giải thích vì sao **phiên bản KV v2**, **TTL của Vault token** và **lease TTL** là ba khái niệm khác nhau.
3. Mô tả vòng đời đầy đủ: tạo/cấp phát, xác thực để lấy secret, sử dụng, gia hạn/cấp mới, luân chuyển, thu hồi và kiểm toán.
4. Chọn cách dùng KV v2 và Database secrets engine từ `VaultOperations`/`VaultTemplate`; hiểu giới hạn của việc tự làm mới credential trong ứng dụng Spring.
5. Phân tích tác động của việc hết hạn secret đến connection pool, API client, Transit encryption và certificate PKI.
6. Đề xuất policy tối thiểu, kịch bản xử lý lỗi, giám sát và bài kiểm thử tích hợp cho từng vòng đời.

## 1. Cùng là bí mật, nhưng không cùng vòng đời

Giả sử `orders-service` của một hệ thống bán hàng cần hai credential:

- **API key của cổng thanh toán:** đối tác cấp một chuỗi key có giá trị cho đến khi đối tác thay hoặc thu hồi nó. Nhóm vận hành lưu key trong Vault KV v2 để `orders-service` đọc lúc cần.
- **Username/password để đọc PostgreSQL:** Vault Database secrets engine có thể tạo một tài khoản riêng từ một role cấu hình trước và cấp credential có TTL cho mỗi lần yêu cầu.

Cả hai đều giúp ứng dụng chứng minh quyền với hệ thống đích, nhưng cách giảm rủi ro khác nhau:

| Tiêu chí | Secret tĩnh | Secret động |
|---|---|---|
| Nguồn tạo | Được tạo/cấp từ trước, rồi nhập vào kho | Engine/hệ thống phát hành tạo theo yêu cầu hoặc theo phiên |
| Ví dụ | API key bên thứ ba, OAuth client secret, shared password | Tài khoản DB động, credential cloud cấp theo role, certificate cấp mới theo yêu cầu |
| Thời gian có hiệu lực | Theo hệ thống phát hành và quy trình rotation | Thường có TTL, thời hạn hiệu lực hoặc lease do engine phát hành |
| Độ dài sử dụng | Có thể được nhiều phiên bản ứng dụng tái sử dụng | Thường có thể giới hạn theo workload, phiên hoặc thời gian |
| Gia hạn | Thường phải phát hành/thay giá trị qua hệ thống gốc | Có thể gia hạn **nếu** engine, role và lease cho phép; nếu không, phải cấp mới |
| Thu hồi | Thực hiện tại hệ thống phát hành và cập nhật kho | Có thể thu hồi bằng cơ chế của engine/lease, tùy backend |
| Vault thường dùng | KV v1/v2 | Database, cloud secrets engines, PKI và các engine hỗ trợ cấp phát |
| Điều dễ nhầm | KV v2 có version ≠ tự đổi key | Có lease ID ≠ chắc chắn gia hạn được vô thời hạn |

**Định nghĩa thực hành:** secret tĩnh có giá trị được lưu/đọc và thường không tự hết hiệu lực chỉ vì người dùng đọc từ Vault; secret động được backend tạo/cấp phát có ràng buộc thời gian hoặc khả năng thu hồi theo một yêu cầu phát hành.

Phân loại này không phải hai nhãn tuyệt đối. Một certificate X.509 được cấp bởi PKI có thời hạn hiệu lực và có thể được tạo theo yêu cầu, nhưng không phải lúc nào cũng có semantics gia hạn lease giống credential Database. Một token Vault có TTL nhưng là **token xác thực với Vault**, không phải dữ liệu KV hay credential của PostgreSQL. Một secret trong KV vẫn có thể chứa access token hết hạn theo quy tắc của bên phát hành: **Vault KV không tự gia hạn token đó**.

## 2. Bản đồ bốn khái niệm dễ bị lẫn

| Khái niệm | Bản chất | Ví dụ | Điều quyết định hết hiệu lực |
|---|---|---|---|
| **KV secret value** | Dữ liệu lưu tại một key logic | `secret/prod/orders/payment` chứa `api-key` | Nhà phát hành key, rotation/revoke bên ngoài; thao tác xóa/hủy KV chỉ ảnh hưởng bản sao Vault |
| **KV v2 version** | Phiên bản lịch sử của tài liệu tại một key | Version 7 của `prod/orders/payment` | Quy tắc lưu trữ/soft-delete/destroy/retention của KV v2 |
| **Vault login token** | Thông tin xác thực để client gọi Vault API | Token cấp sau Kubernetes/AppRole login | TTL, max TTL, chính sách renew/revoke và trạng thái token |
| **Secret lease** | Quyền sử dụng một secret được engine cấp có vòng đời | Credential Database với `lease_id` và TTL | Lease TTL, khả năng renew/revoke và backend thực thi thu hồi |

Ví dụ: quản trị viên ghi version 8 của API key vào KV v2. Điều đó **không** có nghĩa version 7 của API key đã bị vô hiệu hóa ở cổng thanh toán; nó chỉ thay đổi dữ liệu tại Vault. Tương tự, gia hạn Vault token không nhất thiết gia hạn lease của username/password động mà client đã lấy trước đó.

Một số secret động có thể bị thu hồi như hệ quả của việc thu hồi token dùng để cấp secret, tùy quan hệ lease/token và backend. Tuy nhiên, vẫn phải **quản lý riêng** thời hạn và vòng đời của credential; không giả định rằng chỉ theo dõi Vault token đã đủ.

## 3. Luồng sử dụng trong một ứng dụng Spring

~~~mermaid
sequenceDiagram
    autonumber
    participant A as orders-service (Spring Boot)
    participant S as Spring Vault Client/Session
    participant V as Vault Auth + Policy
    participant K as KV v2
    participant G as Database secrets engine
    participant D as PostgreSQL

    A->>S: Yêu cầu secret
    S->>V: Login bằng danh tính workload nếu cần
    V-->>S: Vault token + TTL + policies
    S->>V: GET /v1/secret/data/prod/orders/payment
    V->>K: Kiểm tra read, tải dữ liệu
    K-->>S: API key tĩnh + KV metadata
    S-->>A: API key

    A->>S: Xin credential DB mới
    S->>V: GET /v1/database/creds/orders-reader
    V->>G: Kiểm tra policy, phát hành credential
    G->>D: Tạo user/quyền theo DB role
    G-->>S: username/password + lease_id + TTL
    S-->>A: Credential DB và thông tin vòng đời
    A->>D: Dùng credential để mở kết nối
    Note over A,V: Token có TTL riêng; lease DB có TTL riêng
    Note over A,D: Đến hạn phải renew hợp lệ hoặc đổi credential/kết nối
~~~

Spring Vault nằm trong JVM, chuyển lệnh Java thành lời gọi HTTPS đến Vault. Máy chủ Vault xác thực và kiểm tra policy; Database engine có thể thao tác trực tiếp với DB để cấp tài khoản. Sau khi nhận secret, `orders-service` phải bảo vệ nó trong bộ nhớ và trong những yêu cầu gửi tới hệ thống đích.

Để tránh bài toán “bí mật để lấy bí mật”, ứng dụng nên **xác thực theo workload**: Kubernetes ServiceAccount/JWT, IAM phù hợp hoặc AppRole được quản lý đúng, thay vì đặt root token vào source hoặc image. Token được phát hành nên có TTL hợp lý và policy quyền tối thiểu.

## 4. Vòng đời chung: từ cấp phát đến thu hồi

Một secret có thể trải qua các bước sau, dù cách thực hiện ở từng engine khác nhau:

~~~mermaid
flowchart LR
    P["1. Phát hành / tạo"] --> S["2. Lưu trữ<br/>hoặc cấp động"]
    S --> A["3. Xác thực workload<br/>+ kiểm tra policy"]
    A --> U["4. Ứng dụng sử dụng"]
    U --> D{"5. Còn hiệu lực?"}
    D -->|"Có"| U
    D -->|"Renew được"| R["Gia hạn theo TTL/giới hạn"]
    R --> U
    D -->|"Không renew / rotate"| N["Cấp mới, thay client<br/>hoặc credential"]
    N --> U
    D -->|"Không còn cần"| X["6. Revoke / expire<br/>dọn bản sao"]
    X --> O["7. Audit và kiểm chứng"]
~~~

Trong thực tế, các sự kiện chồng lấp nhau. Một API key có thể đang được sử dụng khi key mới đã phát hành; kết nối DB có thể còn hoạt động sau khi lease chuyển trạng thái; certificate cũ có thể còn được nạp trong TLS context dù certificate mới đã được cấp. Vì vậy, **thay secret ở Vault** và **thay secret mà service đang dùng** là hai bước phải phối hợp.

### 4.1. Chuẩn bị trước khi cấp secret

Trước khi viết Java code, xác định:

1. **Chủ sở hữu:** ai được phép tạo/rotate/revoke secret và xử lý sự cố?
2. **Workload nhận quyền:** service account/role nào, ở môi trường `dev`, `test` hay `prod`?
3. **Phạm vi sử dụng:** secret dùng cho một service, một instance, một hệ thống đích hay một nhóm workload?
4. **Giới hạn:** TTL bao nhiêu, có renewable không, tối đa được renew tới đâu, có khoảng chồng lấp giá trị cũ/mới không?
5. **Ảnh hưởng khi hết hạn:** request nào bị từ chối, connection pool nào cần thay, có được retry hay phải fail closed?
6. **Bằng chứng kiểm toán:** làm sao biết ai đã đọc/cấp/renew/revoke mà không ghi plaintext hoặc token vào log?

### 4.2. Mốc thời gian minh họa

Giả sử tại `t0` ứng dụng nhận Vault token có TTL 30 phút và credential DB có lease 10 phút (số liệu chỉ dùng để minh họa):

~~~text
t0          t0+8m       t0+10m              t0+30m
|-------------|------------|--------------------|
Token Vault:  còn hiệu lực -----------------> hạn token
Lease DB:     còn hiệu lực --> hạn lease ban đầu
                            ^
             Ứng dụng phải renew (nếu được phép)
             hoặc xin credential mới trước điểm rủi ro

API key KV:   không có TTL tự động do lần đọc KV này
              (vẫn có thể bị bên thanh toán revoke bất kỳ lúc nào)
~~~

Nếu service đã renew DB lease hợp lệ, đường thời gian thực tế của lease sẽ thay đổi; nếu không renewable thì phải cấp credential mới. Không nên lên lịch chính xác vào giây cuối: thời gian mạng, độ trễ Vault, CPU và hệ thống đích đều có thể làm thao tác đến muộn.

## 5. Secret tĩnh với KV v2: version không thay cho rotation

KV phù hợp khi một hệ thống khác là nguồn phát hành secret, ví dụ API key của đối tác. Tại Vault, quản trị viên mount KV v2 tại `secret/` và lưu key logic `prod/orders/payment`:

~~~text
Vault mount:   secret/                      (KV v2)
Key logic:     prod/orders/payment
Fields:        api-key, key-id
HTTP read:     GET /v1/secret/data/prod/orders/payment
Policy path:   secret/data/prod/orders/payment
~~~

Ví dụ ACL cho một workload chỉ cần đọc:

~~~hcl
path "secret/data/prod/orders/payment" {
  capabilities = ["read"]
}
~~~

Đây là quyền ở cấp **API path**, không phải quyền riêng từng field JSON. Nếu KV key chứa cả `api-key` và `refresh-token`, token được cấp quyền đọc key sẽ nhận cả hai field. Hãy tách key theo quyền đọc và mục đích sử dụng.

### 5.1. KV v1 và KV v2 khác nhau ở điểm nào?

- **KV v1:** lưu giá trị hiện tại; không có cơ chế version history như KV v2.
- **KV v2:** hỗ trợ version dữ liệu, metadata, thao tác xóa mềm/khôi phục phiên bản trong điều kiện cho phép và hủy vĩnh viễn version khi được phép.
- **Cả hai:** bản thân giá trị KV không có lease động mà Vault tự thu hồi tại nhà phát hành credential. TTL của Vault token dùng để đọc KV cũng không quyết định thời hạn của API key ở hệ thống đích.

Với KV v2, `delete` và `destroy` có ý nghĩa khác nhau: xóa mềm có thể cho phép khôi phục phiên bản; destroy hủy nội dung một version theo API/quyền tương ứng. Đây là **vòng đời bản sao dữ liệu trong Vault**, không đồng nghĩa thu hồi quyền của key tại cổng thanh toán.

### 5.2. Quy trình rotate một API key tĩnh

Một lần rotation có kiểm soát khi đối tác hỗ trợ hai key tồn tại song song:

1. **Cấp key mới** tại cổng thanh toán, giữ phạm vi quyền tối thiểu; key cũ vẫn hoạt động tạm thời.
2. **Ghi version KV v2 mới**, ví dụ thay giá trị `api-key` ở `prod/orders/payment`.
3. **Làm mới ứng dụng:** cho instance đọc key mới theo refresh strategy, cập nhật HTTP client/cache hoặc triển khai lại phần dùng key tùy thiết kế.
4. **Xác minh:** quan sát lỗi xác thực từ đối tác, xác nhận các instance không còn phát request bằng key cũ.
5. **Thu hồi key cũ tại đối tác** và dọn những bản sao không cần thiết trong cache, pipeline, log, backup/versions theo retention policy.
6. **Ghi nhận kiểm toán** thời điểm thay, người thực hiện và kết quả, không ghi giá trị secret.

Nếu đối tác chỉ hỗ trợ một key hoạt động, quy trình phải xử lý khả năng gián đoạn khi chuyển đổi; không suy diễn rằng KV v2 tự giải quyết vấn đề tương thích giữa key cũ và key mới.

### 5.3. Caching secret tĩnh: giảm tải nhưng tăng độ trễ thu hồi

Một service gọi Vault ở mọi HTTP request có thể gây độ trễ và tăng phụ thuộc vào Vault. Ngược lại, cache một API key vô thời hạn khiến rotation/revocation không có hiệu lực ở ứng dụng cho tới khi restart. Chọn chiến lược phù hợp: cache có TTL, chủ động invalidate, refresh theo sự kiện hoặc cập nhật tại deploy. Nếu Vault tạm thời không truy cập được, việc dùng giá trị cache cũ chỉ được phép khi chính sách nghiệp vụ chấp nhận và secret chưa bị thu hồi.

Không ghi secret vào cache chia sẻ hoặc metric labels có quyền đọc rộng chỉ để thuận tiện. Giá trị đã lấy về vẫn là plaintext trong bộ nhớ ứng dụng.

## 6. Secret động: Database engine và lease

Database secrets engine có thể được cấu hình với một kết nối quản trị phù hợp và role xác định cách tạo account/quyền trên database. Khi ứng dụng đọc:

~~~text
GET /v1/database/creds/orders-reader
~~~

Vault có thể tạo credential theo role `orders-reader` và trả về dữ liệu chứa `username`, `password` cùng metadata như `lease_id`, `lease_duration` và `renewable`. Lease là **đối tượng vòng đời** của credential được cấp; không phải phiên bản KV.

Ví dụ response HTTP được rút gọn, với giá trị hoàn toàn giả:

~~~json
{
  "lease_id": "database/creds/orders-reader/illustrative-lease",
  "lease_duration": 600,
  "renewable": true,
  "data": {
    "username": "v_orders_reader_example",
    "password": "example-only-never-use"
  }
}
~~~

Số `600` minh họa TTL ban đầu tính bằng giây. Trường `renewable: true` chỉ cho biết lease hỗ trợ gia hạn theo chính sách tại thời điểm trả lời, **không** bảo đảm có thể gia hạn không giới hạn; role, max TTL, engine và trạng thái hạ tầng vẫn quyết định kết quả.

### 6.1. Phân biệt cấp phát, renew, reissue và revoke

| Thao tác | Ý nghĩa | Cần chú ý |
|---|---|---|
| **Issue (cấp phát)** | Vault tạo/nhận credential mới theo role | Một lần gọi có thể tạo tài khoản mới ở hệ đích |
| **Renew lease (gia hạn)** | Xin kéo dài TTL cho lease hiện có khi được phép | Có thể thất bại nếu đến giới hạn TTL, lease bị revoke hoặc backend không hỗ trợ |
| **Reissue (cấp lại)** | Xin credential mới khi không thể/không muốn renew | Username/password mới đòi hỏi đổi cấu hình client/pool |
| **Revoke (thu hồi)** | Yêu cầu Vault/backend vô hiệu hóa secret/credential theo lease | Hiệu quả phụ thuộc loại engine và hệ đích; không mặc nhiên đóng mọi socket đã mở |
| **Expire (hết hạn)** | Lease tới hạn và được hệ thống xử lý theo cơ chế tương ứng | Không nên chờ đúng hạn mới bắt đầu tạo credential mới |

Vault HTTP API có các endpoint quản lý lease như `sys/leases/renew` và `sys/leases/revoke`, được bảo vệ theo quyền tương ứng. Spring Vault có các API hỗ trợ và thành phần quản lý lease; ứng dụng không nhất thiết phải tự thực hiện REST thô. Việc renew/revoke có yêu cầu quyền và ràng buộc theo token/lease; cần kiểm tra cách xác thực và khả năng engine của phiên bản triển khai.

### 6.2. Connection pool là một phần của vòng đời

Giả sử Spring Data JDBC/JPA sử dụng HikariCP với credential từ Vault. Sau khi Vault cấp account mới:

- **Kết nối mới** phải sử dụng username/password mới.
- **Kết nối đã mở** có thể vẫn tồn tại hoặc bị đóng tùy database, plugin, quy trình revoke và trạng thái kết nối.
- **Connection pool** không biết tự đổi credential chỉ vì Vault có lease mới; có thể cần cấu hình lại datasource, tạo pool thay thế, drain/evict connection cũ và xử lý transaction đang chạy.
- **Role DB** phải thật sự chỉ có quyền đọc/ghi cần thiết. Vault policy giới hạn ai được *xin* credential; quyền SQL của account do role và database quản lý.

~~~mermaid
flowchart TB
    I["Credential thế hệ A<br/>lease sắp hết"] --> P1["Connection pool A"]
    N["Xin credential thế hệ B<br/>trước thời điểm hết hạn"] --> P2["Connection pool B"]
    P1 --> O["Transaction đang chạy"]
    P2 --> R["Kết nối / request mới"]
    O --> X["Drain / đóng pool A<br/>theo kế hoạch"]
    X --> V["Revoke/expire lease A<br/>khi phù hợp"]
~~~

Sơ đồ mô tả một chiến lược chuyển đổi, không phải chức năng tự động có sẵn trong mọi cấu hình Spring Boot. Để giảm downtime, hệ thống cần chọn thời gian chồng lấp credential, cách ứng dụng cập nhật pool và hành vi khi Vault không sẵn sàng.

### 6.3. TTL “ngắn hơn” không tự động “an toàn hơn”

TTL ngắn giảm cửa sổ sử dụng của credential bị lộ nhưng làm số lần gia hạn/cấp lại tăng lên, nâng độ phụ thuộc vào Vault và hệ đích. Một TTL quá ngắn so với thời gian startup, batch job, transaction hoặc điều kiện mạng có thể gây lỗi vận hành. Hãy cân bằng quyền tối thiểu, giới hạn thời gian, khả năng renew, khối lượng cấp phát và quy trình failover dựa trên dữ liệu sử dụng thực tế.

## 7. Token Vault và lease secret: hai đồng hồ khác nhau

Khi kết nối Vault, Spring Vault cần một Vault token hợp lệ. `ClientAuthentication` cung cấp chiến lược lấy token (ví dụ xác thực Kubernetes hay AppRole). `SessionManager` cấp token cho các request của `VaultTemplate`:

- `SimpleSessionManager` thích hợp cho cơ chế lấy token đơn giản, không tự triển khai lịch renewal/revocation theo vòng đời.
- `LifecycleAwareSessionManager` có cơ chế lên lịch gia hạn token nếu hợp lệ và xử lý vòng đời của token đăng nhập theo cấu hình.
- Nếu loại token không renewable hoặc bị revoke, client phải xử lý khả năng đăng nhập lại/lỗi; không có token bất tử.

**Gia hạn Vault token chỉ giúp tiếp tục gọi Vault API** khi được phép; nó không bắt buộc làm lease Database trước đó kéo dài. Ngược lại, một credential DB động có thể sắp hết hạn dù Vault token vẫn còn thời gian. Khi token bị thu hồi, các lease liên quan có thể bị tác động tùy quan hệ giữa token, lease và backend.

### 7.1. Thành phần hỗ trợ lease của Spring Vault

Spring Vault cung cấp `SecretLeaseContainer` để quản lý một số vòng đời của leased/rotating secrets khi được cấu hình với các secret cần theo dõi. Thành phần này có thể hỗ trợ renewal/rotation và phát sự kiện về secret/lease. Tuy nhiên:

1. Phải **khai báo những secret/path cần quản lý** cùng lifecycle phù hợp; không phải mọi lần gọi `vault.read(...)` đều tự động được theo dõi.
2. **Event nhận credential mới không tự thay mọi client ứng dụng.** Code sử dụng event phải cập nhật datasource, HTTP client, pool hoặc TLS context.
3. Cần kiểm tra engine có thực sự renewable hay chỉ hỗ trợ phát hành mới.
4. Token session và secret lease là hai phần, phải cấu hình và kiểm thử cả hai.

Nếu dùng Spring Cloud Vault để đưa secret vào `Environment`, chiến lược refresh bean/datasource cũng cần được xác định riêng; giá trị trong môi trường Spring không đồng nghĩa connection pool tự thay tài khoản đang sử dụng.

## 8. Ví dụ Spring Vault: đọc KV tĩnh và xin credential DB động

Giả định hạ tầng đã có:

- Vault server qua HTTPS và client Java tin cậy CA/hostname.
- `VaultOperations` bean đã cấu hình authentication theo workload và session manager thích hợp.
- Mount KV v2 tên `secret` và key `prod/orders/payment`.
- Database secrets engine mount `database` với role `orders-reader`, cùng policy cho phép workload đọc đúng hai path tương ứng.

Mã minh họa cách *lấy* hai kiểu secret, chưa phải một chiến lược quản lý lease/rotation hoàn chỉnh:

~~~java
import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Service
public class OrdersSecrets {

    private final VaultOperations vault;
    private final VaultKeyValueOperations kv;

    public OrdersSecrets(VaultOperations vault) {
        this.vault = vault;
        this.kv = vault.opsForKeyValue("secret", KeyValueBackend.KV_2);
    }

    // KV v2: secret do bên ngoài phát hành và Vault lưu lại.
    public String paymentApiKey() {
        VaultResponse response = kv.get("prod/orders/payment");
        if (response == null) {
            throw new IllegalStateException("Required payment secret not found");
        }
        return requiredString(response.getRequiredData(), "api-key");
    }

    // Database engine: mỗi lần đọc role có thể cấp credential/lease mới.
    // Trong hệ thống thật, cần gắn thông tin lease với vòng đời datasource.
    public DatabaseLogin issueDatabaseLogin() {
        VaultResponse response = vault.read("database/creds/orders-reader");
        if (response == null) {
            throw new IllegalStateException("No database credential returned");
        }

        Map<String, Object> data = response.getRequiredData();
        return new DatabaseLogin(
            requiredString(data, "username"),
            requiredString(data, "password")
        );
    }

    private static String requiredString(Map<String, Object> data, String name) {
        Object value = data.get(name);
        if (!(value instanceof String text) || text.isBlank()) {
            throw new IllegalStateException("Missing required Vault field: " + name);
        }
        return text;
    }

    public record DatabaseLogin(String username, String password) { }
}
~~~

`VaultResponse` của dynamic secrets cũng có thông tin lease bên ngoài map `data`; phần quản lý vòng đời cần sử dụng metadata lease và API sự kiện/quản lý lease tương ứng của Spring Vault. **Không** lấy credential trong `issueDatabaseLogin()` rồi cache vô thời hạn hoặc tạo pool cố định mà bỏ qua TTL.

API `opsForKeyValue("secret", KV_2).get("prod/orders/payment")` dùng **key logic**; API KV v2 thật đọc ở `secret/data/prod/orders/payment`. Khi gọi `vault.read("database/creds/orders-reader")`, path thuộc Database engine, không cần thêm `data/` của KV v2.

### 8.1. Chính sách minh họa cho hai loại secret

~~~hcl
# Chỉ đọc KV v2 key của orders-service.
path "secret/data/prod/orders/payment" {
  capabilities = ["read"]
}

# Chỉ được xin credential theo DB role orders-reader.
path "database/creds/orders-reader" {
  capabilities = ["read"]
}
~~~

Quyền này không cho ứng dụng đọc key KV của service khác hoặc tự thay policy/role của Database engine. Phía Vault, role `orders-reader` vẫn phải gắn với quyền SQL tối thiểu và cấu hình TTL phù hợp; policy của Vault không thay cho phân quyền database.

### 8.2. Những phần phải bổ sung trước production

Mã trên cố ý ngắn để làm rõ API. Trong ứng dụng thật cần có quản lý token/session, renewal hoặc cấp mới lease, đồng bộ cập nhật connection pool, timeout, retry giới hạn, metrics và xử lý lỗi theo chính sách. Không log `DatabaseLogin`, `VaultResponse` hoặc `X-Vault-Token`; cũng không trả credential từ REST controller ra người dùng cuối.

Nếu ứng dụng dùng Spring Cloud Vault cho property nguồn cấu hình thay vì gọi `VaultOperations` trực tiếp, vẫn phải bảo đảm cùng một quy trình dùng secret mới, thay client và ngừng dùng credential hết hạn.

## 9. Transit và PKI nằm ở đâu trong bức tranh vòng đời?

Tư duy static/dynamic hữu ích nhưng không mô tả hết chức năng Vault:

| Chức năng | Vault làm gì? | Vòng đời cần nghĩ tới |
|---|---|---|
| **KV** | Lưu secret tĩnh, có thể theo version | Rotation tại nguồn phát hành, KV version, xóa/retention, cache |
| **Database** | Cấp credential có lease theo role | Issue, TTL, renew/revoke hoặc cấp mới, thay connection pool |
| **Transit** | Giữ key material để mã hóa/giải mã/ký qua API | Key versions, quyền encrypt/decrypt, rewrap/re-encrypt ciphertext; không có “lease credential” cho mỗi ciphertext |
| **PKI** | Cấp certificate X.509 theo role và thời hạn | Hạn certificate, cấp lại/thu hồi, private key, thay TLS context |
| **Vault auth/token** | Xác thực workload và cấp token để gọi API | Token TTL, renewability, re-login, revoke |

### 9.1. Transit encryption

Với Transit, ứng dụng gửi dữ liệu cần mã hóa qua HTTPS đến `transit/encrypt/<key>` theo format API, nhận ciphertext rồi lưu ciphertext trong database nghiệp vụ. Khóa được quản lý phía Vault. Khi rotate key Transit, phiên bản khóa mới có thể được dùng cho hoạt động mới, nhưng ciphertext đã lưu **không tự được ghi lại**; có thể cần `rewrap` hoặc quy trình mã hóa lại theo chính sách cho phép.

Quyền chỉ mã hóa có thể tách khỏi quyền giải mã:

~~~hcl
path "transit/encrypt/orders-pii" {
  capabilities = ["update"]
}
~~~

Chính sách trên chưa cấp quyền `transit/decrypt/orders-pii`. TTL của Vault token vẫn ảnh hưởng khả năng gọi Transit API, nhưng ciphertext không phải credential động được cấp lease giống tài khoản Database.

### 9.2. PKI certificates

PKI có thể phát hành certificate thời hạn ngắn. Certificate công khai thường không cần giữ bí mật; **private key** mới là dữ liệu cần bảo vệ. Nếu gọi `pki/issue/<role>` để Vault tạo private key, response có thể chứa private key. Với `pki/sign/<role>`, workload có thể tạo key cục bộ và gửi CSR để Vault ký, giúp private key không phải gửi lên Vault.

Khi certificate hết hạn, chỉ lấy certificate mới chưa đủ: client TLS và keystore/trust context cần được cập nhật, các kết nối cũ cần chiến lược thay thế. Không đồng nhất thời hạn certificate với lease Database, và không mặc định mọi certificate có thể được “renew” như một token.

## 10. Xử lý lỗi và giám sát theo vòng đời

| Dấu hiệu | Nhóm nguyên nhân | Phản ứng phù hợp |
|---|---|---|
| `403 permission denied` khi đọc KV | Policy thiếu `read` trên `secret/data/...` hoặc token sai role | Kiểm tra role, path và capability; không thử lại bằng root token |
| `404` hoặc field KV thiếu | Key không tồn tại, sai mount/path hoặc version đã bị xóa | Phân biệt không tồn tại với bị từ chối; fail closed nếu secret bắt buộc |
| Token expired/revoked | Hết TTL, không thể renew, auth method/role thay đổi | Xử lý đăng nhập lại khi đủ điều kiện, quan sát token lifecycle |
| Lease renew thất bại | Lease không renewable, max TTL, bị revoke, backend lỗi | Cấp credential mới nếu hợp lệ, thay pool an toàn |
| DB trả authentication failed | Credential cũ hết hạn hoặc revoke, client chưa cập nhật | Kiểm tra lease lẫn kết nối, tránh retry vô hạn bằng password cũ |
| Cổng thanh toán trả 401 | API key bị rotate/revoke bên đối tác, cache cũ | Xác minh key hiện hành và thực hiện quy trình làm mới |
| TLS handshake thất bại | CA/hostname/certificate/truststore | Sửa cấu hình chứng chỉ và trust, không bỏ qua xác minh TLS |
| Vault timeout, 429 hoặc 5xx | Mạng, giới hạn lưu lượng, engine hoặc cluster | Timeout, backoff + jitter và giới hạn retry theo hành động; không retry mù quáng thao tác có thể tạo mới credential |

### 10.1. Những chỉ số nên theo dõi

- **Vault client:** độ trễ đọc/cấp phát, số lỗi theo HTTP status, tần suất login thất bại, lỗi renew/revoke và số lượng request bất thường.
- **Credential động:** TTL còn lại/điểm cần chuyển đổi, tỷ lệ cấp lại thành công, sự kiện hết lease, số kết nối trong pool cũ và mới.
- **Secret tĩnh:** thời điểm rotation gần nhất, số instance đã nhận phiên bản mới, lỗi xác thực với hệ thống phát hành key.
- **PKI/Transit:** thời gian đến hạn certificate, lỗi phát hành/chuyển certificate, lỗi thao tác encrypt/decrypt và tác động đến luồng nghiệp vụ.
- **Vault server:** sức khỏe/HA, audit devices và lỗi auth/policy, giới hạn tài nguyên theo cách triển khai thực tế.

Metrics và log chỉ nên dùng metadata an toàn; không dùng API key, password, Vault token, private key, plaintext hay ciphertext có ngữ cảnh nhạy cảm làm nhãn. Audit phía Vault cho biết hoạt động API theo cấu hình audit, không có nghĩa ứng dụng được quyền in dữ liệu secret ra log.

### 10.2. Failure mode cần quyết định trước

Khi Vault không truy cập được, ứng dụng có thể đã có một API key trong cache nhưng không thể xin credential Database mới hoặc gọi Transit để mã hóa. Việc tiếp tục sử dụng cache chỉ phù hợp nếu giá trị vẫn hợp lệ và chính sách chấp nhận; không có cơ chế “tự kéo dài” một lease hết hạn. Nếu dữ liệu bắt buộc phải được mã hóa trước khi lưu, thao tác cần thất bại có kiểm soát khi Transit không sẵn sàng, **không** âm thầm lưu plaintext.

Với các lệnh cấp credential mới hoặc ghi dữ liệu, nếu response bị mất sau khi server đã xử lý, retry mù quáng có thể phát hành trùng hoặc tạo trạng thái khó kiểm soát. Thiết kế retry phải hiểu tính idempotent và tác động của từng Vault API.

## 11. Kiểm thử tích hợp: xác minh cả quyền và thời hạn

Một môi trường Vault thật nhưng cô lập cho test (ví dụ container/test-only dev Vault) giúp kiểm tra những điều mock Java không chứng minh được: policy path, khả năng phát hành credential ở database, TTL, renew/revoke và lỗi mạng. Không đưa credential sản xuất vào fixture hoặc pipeline test.

| Bài kiểm thử | Thiết lập | Kết quả mong đợi |
|---|---|---|
| Đọc KV v2 thành công | Mount `secret`, key `prod/orders/payment`, token có `read` | `paymentApiKey()` nhận đúng field |
| Thiếu quyền | Token không có policy đọc KV key | Server trả 403; ứng dụng không trả giá trị rỗng giả thành công |
| KV version/rotation | Ghi hai version với key giả, thay chiến lược refresh | Client nhận key mới đúng thời điểm; version KV cũ không mặc nhiên “đã revoke” ở nguồn |
| Cấp DB credential | Database engine test + role `orders-reader` | Mỗi lần phát hành theo role và lease hợp lệ; quyền DB đúng giới hạn |
| Renew/reissue | Dùng TTL ngắn hợp lý và giới hạn renew | Credential được renew nếu cho phép hoặc cấp mới trước hạn; pool được đổi theo chiến lược |
| Revoke/hết lease | Chủ động revoke lease thử nghiệm | Kết nối mới với credential hết hiệu lực bị xử lý đúng; không khẳng định mọi session cũ bị ngắt ngay |
| Token hết hạn | Revoke token hoặc dùng thời hạn test | Session/auth xử lý lỗi hoặc đăng nhập lại phù hợp; không retry vô hạn |
| Transit/PKI | Key/cert test và role quyền tối thiểu | Encrypt được mà decrypt bị từ chối nếu thiếu quyền; cert thay được khi hết hạn |
| Vault gián đoạn | Timeout, lỗi TLS, 5xx hoặc mạng không tới | Không rò secret, retry hữu hạn và fail closed khi cần |

Trong unit test, mock `VaultOperations` để kiểm tra logic chọn path, phân loại lỗi và xử lý field thiếu. Trong integration test, kiểm tra **server thực và thời gian hiệu lực**, không chỉ assert dữ liệu response giả.

## 12. Bài tập tình huống

### Tình huống A: đã ghi KV version mới mà request vẫn bị từ chối

`orders-service` đọc KV v2 version mới thành công, nhưng API thanh toán trả 401. Nguyên nhân có thể nằm tại nhà cung cấp (key chưa kích hoạt), ứng dụng đang cache key cũ, hoặc header gọi đối tác sai. KV version mới không làm key cũ/new key tự hoạt động ở hệ đích. Hãy kiểm tra toàn bộ quá trình phát hành, phân phối, cập nhật client và thu hồi.

### Tình huống B: Vault token còn hạn nhưng PostgreSQL từ chối đăng nhập

Vault token còn 20 phút, DB credential có TTL ban đầu 10 phút và vừa hết hạn. Gia hạn Vault token không giải quyết credential DB cũ. Nếu lease không thể renew, ứng dụng cần xin credential mới và thay pool/kết nối theo cơ chế đã kiểm thử.

### Tình huống C: certificate đã cấp lại nhưng mTLS vẫn thất bại

PKI cấp certificate mới đúng role. Tuy nhiên, client TLS vẫn nạp keystore cũ hoặc peer không tin chain CA, nên handshake thất bại. Vòng đời chứng chỉ bao gồm **cấp phát, phân phối, nạp vào TLS context và thay kết nối**; Vault cấp cert thành công chỉ là một bước.

### Tình huống D: cần lưu dữ liệu đã mã hóa, Vault Transit tạm thời không sẵn sàng

Hệ thống không có bản mã để lưu và không được phép lưu plaintext. Cách xử lý phù hợp là trì hoãn/từ chối thao tác với thông báo lỗi nghiệp vụ thích hợp, áp timeout/retry hữu hạn; chỉ dùng fallback mã hóa cục bộ khi đây là **thiết kế mật mã đã được phê duyệt riêng** với quản lý khóa tương đương, không phải fallback ngẫu nhiên trong exception handler.

### Câu hỏi tự kiểm tra

1. Vì sao KV v2 có version 5 không có nghĩa API key ở version 4 đã bị nhà cung cấp thu hồi?
2. Vault login token, KV v2 version và DB credential lease khác nhau ở điểm nào?
3. Thế nào là `renew`, `reissue` và `revoke`; khi nào cần cấp credential mới?
4. Tại sao `SecretLeaseContainer` không tự bảo đảm HikariCP đã chuyển sang tài khoản mới?
5. Với Vault token còn hạn nhưng DB lease hết hạn, hệ thống nên xử lý theo chuỗi bước nào?
6. Vì sao Transit ciphertext và certificate PKI không nên được quản lý như một API key tĩnh thông thường?
7. Nếu Vault tạm thời không sẵn sàng, ranh giới giữa cache hợp lệ và việc dùng credential hết hạn nằm ở đâu?

## Tài liệu tham khảo chính thức

- [Spring Vault — Reference Documentation](https://docs.spring.io/spring-vault/reference/)
- [Spring Vault — VaultTemplate](https://docs.spring.io/spring-vault/reference/vault/imperative-template.html)
- [Spring Vault — Authentication and Sessions](https://docs.spring.io/spring-vault/reference/vault/authentication.html)
- [Spring Vault — Secret Lease Container](https://docs.spring.io/spring-vault/reference/vault/secret-lease-container.html)
- [HashiCorp Vault — KV v2 Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/kv/kv-v2)
- [HashiCorp Vault — Database Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/databases)
- [HashiCorp Vault — Lease Concepts](https://developer.hashicorp.com/vault/docs/concepts/lease)
- [HashiCorp Vault — Token Concepts](https://developer.hashicorp.com/vault/docs/concepts/tokens)
- [HashiCorp Vault — Transit Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/transit)
- [HashiCorp Vault — PKI Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/pki)

> **Ghi chú triển khai:** Các path và TTL là ví dụ dành cho học tập. API Spring Vault, tính năng lease/token và hành vi engine phụ thuộc phiên bản cùng cấu hình Vault thực tế. Trước khi triển khai, đối chiếu tài liệu phù hợp với phiên bản đang chạy và kiểm thử đường cấp phát, làm mới, thu hồi trên hệ thống test.

# Read-after-write và độ trễ khi đọc từ replica

## 1. Ghi thành công nhưng đọc ngay lại thấy dữ liệu cũ

Người dùng tạo đơn hàng, REST API trả **201 Created** với `Location: /v1/orders/o-42`. Trình duyệt lập tức gọi `GET /v1/orders/o-42` để hiển thị chi tiết nhưng nhận **404 Not Found**. Vài trăm mili giây sau, gọi lại thì đơn xuất hiện. Không nhất thiết có lỗi ở transaction ghi: ứng dụng có thể **ghi vào primary nhưng đọc từ read replica chưa kịp nhận thay đổi**.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as REST API
    participant P as Primary DB
    participant R as Read replica
    C->>A: POST /v1/orders
    A->>P: INSERT order o-42
    P-->>A: COMMIT thành công
    A-->>C: 201 Created + Location
    Note over P,R: Sao chép bất đồng bộ đang trễ
    C->>A: GET /v1/orders/o-42
    A->>R: SELECT order o-42
    R-->>A: Chưa có hàng
    A-->>C: 404 (thấy như không tồn tại)
    P-->>R: WAL/changes được áp dụng
    C->>A: GET /v1/orders/o-42
    A->>R: SELECT order o-42
    R-->>A: Có order o-42
    A-->>C: 200 + JSON mới
~~~

Bài thuộc chương **Nhất quán nghiệp vụ** của module **INTEGRATION_API_REST**: thiết kế REST theo resource, URI, HTTP method/status và hợp đồng dữ liệu; học phân trang, cache, idempotency, OpenAPI, xác thực, phân quyền, xử lý lỗi và kiểm thử với Java/Spring hoặc công nghệ tương đương. Ở đây, vấn đề cần giải quyết là **hợp đồng quan sát sau khi ghi** chứ không đơn thuần tối ưu truy vấn.

Mục tiêu sau bài: giải thích vì sao read replica có thể trễ, phân biệt read-your-writes với strong/eventual consistency, chọn cách đọc primary hoặc chờ replica hợp lý, thiết kế HTTP contract rõ ràng, triển khai Java/Spring an toàn, quan sát replica lag và kiểm thử trường hợp ghi xong nhưng replica chưa theo kịp.

## 2. Ba khái niệm phải phân biệt

### 2.1. Commit, replication và khả năng quan sát

Trong kiến trúc primary–replica dùng sao chép bất đồng bộ:

1. **Primary commit:** thay đổi đã được commit theo bảo đảm durability/transaction của primary.
2. **Replication delivery:** log hoặc thay đổi được chuyển đến replica.
3. **Replica apply/visibility:** replica áp dụng thay đổi và query sau đó nhìn thấy phiên bản mới.

Ba mốc không nhất thiết xảy ra cùng lúc. Một HTTP `201` trả sau **primary commit** không tự cam kết rằng **mọi replica** đã áp dụng thay đổi. Nếu failover hoặc sự cố xảy ra, dữ liệu đã ACK ở primary nhưng chưa sao chép có thể còn thêm rủi ro mất/rollback tùy cấu hình durability và failover; không nên đồng nhất “primary trả commit” với “đã bền vững trên toàn vùng”.

~~~text
t0 primary: order.status = CREATED, version = 1
t1 primary COMMIT UPDATE status = PAID, version = 2
t2 API trả 200 cho PATCH
t3 replica SELECT -> CREATED, version = 1  (stale)
t4 replica replay commit -> PAID, version = 2
t5 replica SELECT -> PAID, version = 2
~~~

Độ trễ phụ thuộc tải ghi, network, I/O, replay, transaction dài, topology, cross-region và khả năng replica tạm dừng. **Không thiết kế với giả định “replica luôn chậm đúng 100 ms”**; phân phối độ trễ có đuôi dài và có thể thay đổi khi incident.

### 2.2. Những mức nhất quán có liên quan

| Mô hình | Điều được bảo đảm về quan sát | Ví dụ |
|---|---|---|
| **Eventual consistency** | Nếu không có ghi mới và hệ thống tiếp tục hoạt động, replica có thể hội tụ về phiên bản mới | GET ngay sau PATCH có thể thấy trạng thái cũ |
| **Read-your-writes (RYW)** | Trong phạm vi session/actor được quy ước, các đọc sau ghi của chính actor phải thấy ghi ấy hoặc phiên bản mới hơn | Người vừa đổi địa chỉ thấy địa chỉ mới |
| **Monotonic reads** | Cùng một session không đi lùi về phiên bản cũ hơn đã thấy | Sau khi thấy v7, không thấy lại v6 |
| **Causal consistency** | Quan sát các thao tác theo phụ thuộc nhân quả, bao gồm nhưng rộng hơn RYW | B thấy phản hồi cho thông điệp A sau khi thấy A |
| **Linearizability** | Mỗi thao tác như xảy ra tại một thời điểm duy nhất giữa invocation và response, tôn trọng thứ tự thực | Đọc sau một ghi đã hoàn tất trên đối tượng thấy hiệu ứng của ghi đó, kể cả giữa các client |

**RYW không phải linearizability:** đọc primary trong một hệ thống primary đơn có thể đáp ứng nhiều trường hợp, nhưng việc chuyển leader/failover, cache, giao dịch khác và các nguồn dữ liệu ngoài DB quyết định bảo đảm toàn hệ thống. **RYW cũng không đồng nghĩa “mọi client nhìn thấy ngay”**: nó thường là lời hứa với chính session vừa ghi.

### 2.3. “Đọc mới nhất” có thể có nhiều nghĩa

Với order `o-42`, client có thể cần một trong ba hợp đồng:

- **Ngay sau POST:** nhìn thấy *ít nhất* order vừa tạo, tránh 404 giả do replica trễ.
- **Ngay sau PATCH:** thấy *tối thiểu version 8* mà chính mình vừa ghi; nếu user khác đã cập nhật version 9, v9 cũng có thể chấp nhận.
- **Dashboard tổng hợp:** chấp nhận dữ liệu trễ vài giây để giảm tải primary, nhưng cần ghi rõ độ mới và không dùng cho quyết định tài chính tức thời.

Định nghĩa “mới nhất” chỉ theo đồng hồ server hoặc `updatedAt` có thể không đủ: clock giữa các node lệch, nhiều update trong cùng milli-giây và một bản đọc có thể thuộc snapshot cũ. **Version đơn điệu, commit position hoặc đọc primary** thường là công cụ tin cậy hơn khi cần ràng buộc freshness.

## 3. Vì sao hệ thống có read replica?

Replica có ích để **phân tải đọc**, tăng locality ở nhiều region, phục vụ reporting hoặc tách query nặng khỏi primary. Đổi lại:

| Lợi ích | Giá phải trả |
|---|---|
| Scale nhiều truy vấn GET | Phát sinh cửa sổ stale reads |
| Đọc gần vị trí người dùng | Cross-region replication latency khó đoán |
| Reporting/search không đè primary | Độ mới phụ thuộc pipeline áp dụng thay đổi |
| Khả năng failover tùy kiến trúc | Cần kiểm tra RPO/RTO, fencing và nguy cơ mất commit chưa replicate |

Một replica có thể **đã nhận log nhưng chưa apply**; chỉ nhìn network latency hoặc số byte nhận được không đủ kết luận câu lệnh SELECT sẽ thấy version mới. Với PostgreSQL, các tín hiệu như WAL receive/replay position và `pg_last_xact_replay_timestamp()` giúp quan sát, nhưng một con số “lag = 0” không bảo đảm mọi request đã gặp đúng commit hoặc read transaction dùng snapshot mới. Với MySQL/GTID, nguyên tắc tương tự nhưng cách chờ/applied position phụ thuộc engine/cấu hình.

Đặc biệt, **replica lag khác cache staleness**. Một GET có thể vẫn cũ vì CDN, application cache hoặc client cache **ngay cả khi replica đã bắt kịp primary**. Cần xác định tất cả tầng đọc, không chỉ nhìn dashboard DB.

## 4. Hợp đồng HTTP sau POST, PUT và PATCH

HTTP không định nghĩa rằng `201 Created` hoặc `204 No Content` bắt mọi read replica đồng bộ tức thời. REST API phải **nêu rõ khả năng đọc lại kết quả** và cung cấp cách lấy dữ liệu mới phù hợp với nghiệp vụ.

### 4.1. POST đồng bộ: trả representation vừa ghi

~~~http
POST /v1/orders HTTP/1.1
Authorization: Bearer <redacted>
Content-Type: application/json
Idempotency-Key: "6f0f4f80-8ac7-4aa7-b403-92aa914edce2"

{"productId":"sku-7","quantity":2}

HTTP/1.1 201 Created
Location: /v1/orders/o-42
Content-Type: application/json
ETag: "order-v1"
Cache-Control: no-store

{"id":"o-42","status":"CREATED","version":1}
~~~

Response body có thể được **lắp từ dữ liệu đã commit trên primary**, nên UI có thể hiển thị đơn mới mà **chưa phải GET lần nữa**. `Location` vẫn là URI chuẩn cho các request sau, nhưng nếu GET tại URI đó được route tới replica bất kỳ thì **vẫn có cửa sổ 404 giả**. Giải pháp trả body giảm một round-trip, **không tự tạo cam kết RYW** cho các GET kế tiếp.

`Idempotency-Key` ở đây là hợp đồng do server công bố: nếu request POST timeout rồi retry cùng ý định, service phải chống tạo trùng bằng ledger/transaction/unique constraint phù hợp. RYW không thay idempotency; chúng giải quyết hai nguy cơ khác nhau: **ghi hai lần** và **đọc phiên bản cũ**.

### 4.2. PUT/PATCH thành công: body hoặc version tối thiểu

~~~http
PATCH /v1/orders/o-42 HTTP/1.1
Authorization: Bearer <redacted>
If-Match: "order-v6"
Content-Type: application/merge-patch+json

{"deliveryNote":"Gọi trước khi giao"}

HTTP/1.1 200 OK
Content-Type: application/json
ETag: "order-v7"
Cache-Control: no-store

{"id":"o-42","status":"CREATED","version":7,
 "deliveryNote":"Gọi trước khi giao"}
~~~

Hoặc API có thể trả `204 No Content` với validator đúng hợp đồng và không gửi body. **`If-Match`/`412 Precondition Failed` ngăn lost update**, nhưng **không bảo đảm** GET kế tiếp qua replica đã thấy version v7. Đây là hai trục độc lập: *an toàn khi ghi* và *độ mới khi đọc*.

Nếu client có `ETag: "order-v7"` từ response PATCH rồi gửi `If-None-Match: "order-v7"` tới replica đang ở v6, replica có thể trả **200 với v6**, khiến giao diện đi lùi. Ngược lại, nếu client đang giữ v6 và gửi `If-None-Match: "order-v6"`, replica v6 có thể trả **304**, mặc dù primary đã ở v7. **Conditional GET cũng cần đi qua đường đọc đáp ứng freshness contract**; `ETag` không tự sửa replica lag.

### 4.3. 202 Accepted là chuyện khác

~~~http
POST /v1/reports HTTP/1.1
Content-Type: application/json

{"period":"2026-10"}

HTTP/1.1 202 Accepted
Location: /v1/operations/op-71
Retry-After: 3
Content-Type: application/json

{"id":"op-71","status":"QUEUED"}
~~~

Với `202`, server mới **chấp nhận yêu cầu**, chưa hứa công việc đã hoàn tất. Client theo dõi operation resource; không tự diễn giải GET resource kết quả trả 404 là replica lag khi job còn QUEUED. Trang thái `SUCCEEDED` chỉ nên được công bố khi hiệu ứng nghiệp vụ tương ứng đã commit và có đường đọc phù hợp; nếu operation status nằm trong store khác, cần thiết kế chuyển trạng thái/đối soát để tránh “đã xong” giả.

### 4.4. Khi nào 404 là “không tồn tại”, khi nào chỉ “chưa thấy”?

Một replica trả không có hàng không thể tự phân biệt **resource chưa tạo**, **đã bị xóa** hay **đã tạo nhưng chưa replicate**. Nếu endpoint hứa RYW thì trả ngay 404 từ replica khi caller vừa tạo là **vi phạm hợp đồng**, không phải một cách dùng 404 “hợp lệ” vì replica chưa thấy.

API có thể:

- đọc primary cho những GET cần RYW;
- nhận một consistency token/version tối thiểu và chờ hoặc fallback;
- công bố rõ endpoint chỉ eventual consistency, kèm trạng thái “đang đồng bộ” ở tầng UX khi cần.

Không biến mọi 404 thành 202/503 tùy tiện: khi **không có bằng chứng đang chờ replication**, 404 vẫn có ý nghĩa resource không tồn tại/không nhìn thấy theo policy. Đặc biệt, **404 trung tính do authorization** không được phân biệt bằng thông điệp “replica chưa đồng bộ” để lộ sự tồn tại order của tenant khác.

## 5. Năm chiến lược đọc sau ghi

| Chiến lược | Ưu điểm | Đánh đổi / khi dùng |
|---|---|---|
| **Trả DTO trong response ghi** | Không cần GET để vẽ ngay UI | GET sau đó vẫn có thể stale; body tăng kích thước |
| **Đọc primary cho critical GET** | Dễ hiểu, đường đọc nhất quán với commit của primary | Tăng tải primary; failover/cache vẫn cần xem xét |
| **Session read affinity trong một khoảng** | RYW cho user vừa ghi, tận dụng replica ở các request khác | Phải quản lý session across instances, TTL và identity |
| **Version/commit-position gating** | Chờ đến khi replica đạt version cần thiết | Tốn round-trip, timeout; cần token an toàn, version đúng |
| **Bounded wait + fallback primary** | Cân bằng tải replica và độ mới | Complexity/cost; fallback có thể tăng tải primary lúc replication incident |

### 5.1. Đọc primary là lựa chọn mặc định an toàn cho thao tác nhạy cảm

Các endpoint như xác nhận thanh toán, chuyển khoản, điều chỉnh tồn kho hay trạng thái đơn ngay sau checkout thường cần **freshness mạnh**. Đọc primary theo transaction/snapshot phù hợp dễ vận hành hơn một hệ token phiên bản phức tạp.

Không vì tất cả request GET có tính “safe” theo HTTP mà mặc định chúng đều có thể đọc replica. **HTTP safe/idempotent mô tả tác dụng của method**, không nói gì về mô hình nhất quán backend. Cũng không nhầm `@Transactional(readOnly=true)` của Spring với “sẽ route sang replica”: annotation này **không tự quyết định datasource**.

### 5.2. Sticky read sau ghi theo actor/session

Sau khi actor A ghi order, hệ thống có thể đặt **“read primary until”** trong session server-side hoặc một context được ký/giới hạn TTL. Các GET của A đến resource liên quan sẽ route primary trong khoảng nhất định; actor B vẫn đọc replica nếu hợp đồng cho phép.

**Không dùng một thời gian chờ cố định như bảo đảm tuyệt đối**: replica có thể trễ hơn TTL. Nếu sau TTL muốn vẫn hứa RYW, phải lưu và kiểm **version đã quan sát** chứ không chỉ chờ 2 giây. Sticky session của load balancer chỉ gắn với **application instance**, không nhất thiết gắn với primary database; muốn có hiệu lực phải có logic read routing thực sự.

### 5.3. Consistency token hoặc minimum version

Server có thể trả một **token opaque đã ký**, gắn với `actor/tenant/resource/version/expiry`; client gửi lại token khi GET. Service chỉ trả từ replica nếu thấy version **lớn hơn hoặc bằng** minimum version. Token phải được xác minh trước khi dùng, không tin client tự khai `version=999999` để buộc primary nhận tải vô hạn.

~~~http
HTTP/1.1 201 Created
Location: /v1/orders/o-42
Content-Type: application/json
X-Read-After-Write: <opaque-signed-consistency-token>

{"id":"o-42","status":"CREATED","version":1}

GET /v1/orders/o-42 HTTP/1.1
Authorization: Bearer <redacted>
X-Read-After-Write: <same-opaque-token>
~~~

**`X-Read-After-Write` là header minh họa do API tự định nghĩa, không phải header HTTP tiêu chuẩn.** Nếu triển khai phải document trong OpenAPI, giới hạn độ dài, tính phí/quota read strong và kiểm tra token thuộc actor/resource hiện tại. Token đọc **không phải quyền truy cập**: kiểm object-level authorization vẫn bắt buộc. Đối với cache, cân nhắc không lưu (`no-store`) hoặc có cache key/`Vary` an toàn theo consistency mode; proxy thường không hiểu tự động token này.

Token version đơn điệu theo resource chỉ giúp nếu dữ liệu có **version tăng đúng cho mọi ghi**, và khi đọc lại có thể kiểm version. Khi **DELETE**, hàng biến mất nên không thể kiểm version từ hàng: cần tombstone/high-watermark hoặc route primary để phân biệt delete đã thấy với replica còn hàng cũ. Với nhiều resource liên quan, version của một order **không chứng minh** aggregate/search index đã cập nhật; cần checkpoint ở cấp dataset/pipeline hoặc chấp nhận stale view rõ ràng.

### 5.4. Chờ replica có giới hạn rồi fallback

~~~text
GET resource với minimumVersion=7
  -> authenticate + authorize actor/tenant
  -> đọc replica (scoped query)
  -> nếu version >= 7: trả DTO
  -> nếu version < 7 hoặc chưa có: chờ ngắn/đọc lại có giới hạn
  -> nếu hết deadline: đọc primary để bảo đảm RYW, hoặc trả lỗi rõ
  -> nếu primary cũng không bảo đảm: không trả dữ liệu cũ như "đã mới"
~~~

**Không chờ vô hạn trên HTTP worker/event loop**: đặt deadline, giới hạn số polling, jitter, concurrency cap cho số request đang chờ và chống retry storm. Nếu fallback primary ngay lập tức cho mọi request trong giờ cao điểm, replica không còn giúp scale; đo tỷ lệ fallback và điều chỉnh policy. Với request chi phí cao, có thể trả 503 + `Retry-After` **nếu hợp đồng cho phép và không thể đáp ứng freshness**, thay vì giả vờ 200 với dữ liệu cũ.

### 5.5. Chờ commit position của database

Thay vì version business, hạ tầng có thể dùng **vị trí log đã commit** (ví dụ PostgreSQL WAL LSN hoặc MySQL GTID) để chứng minh replica đã replay đủ xa. Hệ thống cần **capture position gắn đúng với commit**: lấy LSN **trong** transaction và xem là commit token là sai vì transaction có thể chưa commit. Một LSN lấy trên primary **sau khi commit được xác nhận** có thể là *upper bound bảo thủ* (chờ lâu hơn cần thiết), chứ không tự nhiên là “LSN đúng của order”.

Các cơ chế chờ theo database có khác biệt về replication mode, timeline/failover, topology và thời gian timeout. Nếu replica được promote sau sự cố, **token vị trí cũ có thể không còn so sánh trực tiếp trên timeline mới**. Không xây cơ chế vị trí log chỉ từ chuỗi `pg_last_wal_replay_lsn()` mà bỏ qua transaction boundaries và failover.

## 6. Chọn freshness contract theo nghiệp vụ, không theo “GET là đọc nhẹ”

| Use case | Hợp đồng tối thiểu phù hợp | Đường đọc gợi ý |
|---|---|---|
| Sau tạo order, hiển thị chi tiết của chính user | **RYW**: thấy order đã commit | DTO ngay trong 201; GET detail qua primary hoặc version gate |
| Sau đổi địa chỉ giao hàng | **RYW/monotonic** cho actor | PATCH trả DTO/version; GET không xuống dưới version đó |
| Kiểm tra trạng thái trước trừ tiền/giao hàng | **Strong/current authoritative state** tại transaction thực thi | Kiểm trên primary/owner của state, khóa/version phù hợp |
| Danh sách lịch sử nhiều năm | Có thể **eventual** với độ trễ được ghi rõ | Read replica + pagination nhất quán |
| Dashboard analytics | Thường chấp nhận stale có giới hạn | Replica/read model, hiển thị `dataAsOf` hoặc watermark |
| Tra cứu quyền truy cập/token đã thu hồi | Cần chính sách freshness **nghiêm ngặt** | Không dựa hoàn toàn replica chậm hoặc cache quyền cũ |
| Search index/eventual projection | Có thể nhất quán trễ độc lập với DB replica | Checkpoint riêng + UX “đang cập nhật” |

**Cách quyết định:** trước tiên nêu việc gì sẽ sai nếu đọc bản cũ. Nếu chỉ hiển thị dashboard ít quan trọng, latency thấp có thể đáng đổi. Nếu dữ liệu cũ khiến thanh toán lại, giao trùng hoặc cho phép user đã bị thu hồi quyền xem dữ liệu, chọn đường authoritative và kiểm transaction boundary. Đừng biến vấn đề **an toàn lệnh ghi** thành bài toán “đọc vài lần xem đã mới chưa”.

### 6.1. Độ mới là thuộc tính của response, không chỉ DB

Hệ thống có thể định nghĩa SLO như “99,9% GET danh sách nhìn thấy commit sau tối đa 2 giây”, nhưng **SLO thống kê không phải bảo đảm RYW tuyệt đối**. Nếu API công bố bounded staleness, cần quy định cách đo, khoảng thời gian, hành vi khi vượt ngưỡng và ngoại lệ lúc failover. Không ghi trong OpenAPI “strongly consistent” chỉ vì bình thường replica chậm ít.

Một thuộc tính `dataAsOf`/`replicaCheckpoint` có thể hữu ích cho reporting, nhưng **thời điểm replay cuối cùng không chứng minh snapshot có đủ mọi thay đổi của một resource** nếu đọc qua nhiều nguồn hoặc cache. Nếu yêu cầu cụ thể “tôi vừa ghi v8”, dùng floor version v8 hoặc primary.

### 6.2. UI và client cần hành vi rõ ràng

Client sau `201` nên sử dụng representation trả về nếu có và điều hướng tới `Location` khi cần, không lập tức tự coi 404 từ đường eventual là “tạo thất bại”. Với endpoint công bố eventual consistency, có thể hiển thị **đang đồng bộ** và refresh bằng backoff có deadline; không poll từng 10 ms hoặc retry vô hạn. Nếu server hứa RYW nhưng trả 404 giả, đó là lỗi server/API contract cần sửa **tại đường đọc**, không chỉ che bằng spinner phía client.

Nếu POST timeout và không rõ đã commit, client dùng **Idempotency-Key** hoặc operation ID để đối soát; không tạo lần nữa với key mới. Một read replica chưa thấy bản ghi **không phải bằng chứng transaction ghi thất bại**.

## 7. Spring Boot: tách command path và hai read paths có chủ đích

Ví dụ minh họa **Java 17+, Spring Boot 3.x, Spring MVC, Spring Data/JDBC hoặc JPA phía sau adapter**. Ứng dụng có hai datasource được cấu hình ngoài ví dụ: `primary` và `readReplica`. Không tự route bằng cách đoán annotation.

### 7.1. Ports có tên rõ ràng

~~~java
record CreateOrderRequest(
    @NotBlank String productId,
    @Min(1) @Max(100) int quantity) {}
record OrderView(UUID id, String status, long version) {}
record Actor(UUID tenantId, UUID customerId) {}

interface OrderCommandPort {
    // Ghi trên primary trong transaction đúng.
    OrderView insert(Actor actor, CreateOrderRequest request);
}

interface OrderReadPort {
    // Tất cả truy vấn đều có scope tenant/customer từ Actor đáng tin.
    Optional<OrderView> findVisible(Actor actor, UUID id);
    List<OrderView> listVisible(Actor actor, int limit);
}
~~~

Để tránh đưa cùng bean vào cả hai vai trò, lớp adapter thực có thể đặt `@Qualifier("primaryOrderReader")` và `@Qualifier("replicaOrderReader")` hoặc dùng kiểu interface riêng. Hai adapter phải **thực sự chọn datasource đúng**; `@Transactional(readOnly=true)` không tự tạo split primary/replica. Với JPA, EntityManager/transaction manager tương ứng datasource phải được cấu hình nhất quán; với JDBC dùng `JdbcTemplate` trên datasource cụ thể sẽ rõ hơn.

### 7.2. Ghi vào primary, trả DTO đã được xác nhận commit

~~~java
@Service
class OrderCommandService {
    private final OrderCommandPort primaryWriter;

    OrderCommandService(OrderCommandPort primaryWriter) {
        this.primaryWriter = primaryWriter;
    }

    @Transactional(transactionManager = "primaryTransactionManager")
    public OrderView create(Actor actor, CreateOrderRequest body) {
        if (body.quantity() < 1 || body.quantity() > 100) {
            throw new IllegalArgumentException("Invalid quantity");
        }
        return primaryWriter.insert(actor, body);
    }
}
~~~

Khi controller gọi service qua Spring transactional proxy, transaction **commit trước khi lời gọi service trả kết quả cho controller** (nếu commit thành công). Nếu commit lỗi, không được gửi `201`. `OrderCommandPort.insert` phải dùng **cùng primary transaction manager/connection**; nếu port tự ghi qua connection khác, giả định atomicity bị phá vỡ. Response DTO nên được tạo từ dữ liệu transaction đã ghi, không yêu cầu một GET mới từ replica trước khi trả.

### 7.3. GET detail qua primary, GET danh sách qua replica

~~~java
@Service
class OrderQueryService {
    private final OrderReadPort primaryReader;
    private final OrderReadPort replicaReader;

    OrderQueryService(
            @Qualifier("primaryOrderReader") OrderReadPort primaryReader,
            @Qualifier("replicaOrderReader") OrderReadPort replicaReader) {
        this.primaryReader = primaryReader;
        this.replicaReader = replicaReader;
    }

    public OrderView getFresh(Actor actor, UUID id) {
        return primaryReader.findVisible(actor, id)
            .orElseThrow(ResourceNotVisibleException::new);
    }

    public List<OrderView> listEventually(Actor actor, int limit) {
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("Invalid limit");
        }
        return replicaReader.listVisible(actor, limit);
    }
}
~~~

Trong ví dụ, `GET detail` được chọn **authoritative** để user vừa tạo order thấy bản ghi; `GET collection` chọn **eventual** cho tải lớn. Đây là **quyết định riêng của API mẫu**; nếu UI cần order mới **xuất hiện ngay trong collection**, cũng phải route list qua primary, dùng consistency floor ở cấp collection hoặc thể hiện trạng thái đang đồng bộ. Không hứa RYW trên collection rồi đọc replica vô điều kiện.

### 7.4. HTTP controller không “tự đồng bộ” bằng sleep

~~~java
@RestController
@RequestMapping("/v1/orders")
class OrderController {
    private final OrderCommandService commands;
    private final OrderQueryService queries;
    private final ActorFactory actors;

    OrderController(OrderCommandService commands,
                    OrderQueryService queries, ActorFactory actors) {
        this.commands = commands;
        this.queries = queries;
        this.actors = actors;
    }

    @PostMapping
    ResponseEntity<OrderView> create(
            @AuthenticationPrincipal Jwt jwt,
            @Valid @RequestBody CreateOrderRequest input) {
        Actor actor = actors.fromVerifiedJwt(jwt);
        OrderView created = commands.create(actor, input);
        URI uri = URI.create("/v1/orders/" + created.id());
        return ResponseEntity.created(uri)
            .cacheControl(CacheControl.noStore())
            .body(created);
    }

    @GetMapping("/{id}")
    ResponseEntity<OrderView> get(
            @AuthenticationPrincipal Jwt jwt, @PathVariable UUID id) {
        Actor actor = actors.fromVerifiedJwt(jwt);
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(queries.getFresh(actor, id));
    }
}
~~~

Đoạn code là **khung tích hợp**, cần import từ Spring Web/Security/Jakarta Validation và hiện thực `ActorFactory`/`ResourceNotVisibleException`/adapter. `@Valid` chỉ kiểm constraint nếu DTO có annotation và provider Bean Validation được cấu hình; demo kiểm quantity ở service. `ActorFactory` phải chỉ lấy tenant/customer sau khi JWT đã xác thực chữ ký, issuer, audience, expiry và membership; **không tin `tenantId` từ query hay body**. Route `POST` phải có authorization theo scope, idempotency nếu hợp đồng hỗ trợ, và kiểm tra nghiệp vụ trong transaction.

**Không dùng `Thread.sleep(500)` sau POST để “đợi replica”**: nó không có ngưỡng bảo đảm, chặn worker và tăng latency. Code không tự chuyển read-only transaction qua replica; lựa chọn reader là quyết định hiển thị bằng dependency injection. Một GET strong có thể tăng tải primary, nên cần capacity planning/rate limits riêng.

## 8. Khi cần read replica nhưng không muốn trả phiên bản thấp hơn

Một ứng dụng lớn có thể tránh dồn **mọi GET** vào primary bằng cách mang một *minimum version* đã được server xác minh. Đoạn service dưới đây tập trung vào **quy tắc chọn nơi đọc**, không mô tả ký/giải mã token:

~~~java
// Chỉ được tạo sau khi verify chữ ký/expiry/scope của token.
record VerifiedReadFloor(
    UUID tenantId, UUID orderId, long minVersion) {}

class VersionAwareOrderReader {
    private final OrderReadPort primary;
    private final OrderReadPort replica;

    VersionAwareOrderReader(OrderReadPort primary, OrderReadPort replica) {
        this.primary = primary;
        this.replica = replica;
    }

    OrderView readAtLeast(Actor actor, UUID id, VerifiedReadFloor floor) {
        if (!floor.tenantId().equals(actor.tenantId())
                || !floor.orderId().equals(id)
                || floor.minVersion() < 1) {
            throw new AccessDeniedException("Invalid consistency scope");
        }

        Optional<OrderView> candidate = replica.findVisible(actor, id);
        if (candidate.isPresent()
                && candidate.get().version() >= floor.minVersion()) {
            return candidate.get();
        }

        // Replica absent/stale; primary vẫn truy vấn scoped.
        OrderView fresh = primary.findVisible(actor, id)
            .orElseThrow(ResourceNotVisibleException::new);
        if (fresh.version() < floor.minVersion()) {
            throw new ConsistencyUnavailableException();
        }
        return fresh;
    }
}
~~~

`AccessDeniedException`, `ConsistencyUnavailableException` và `ResourceNotVisibleException` cần được ánh xạ HTTP phù hợp. `floor` phải đến từ token đã **xác thực bằng khóa server-side**, có hạn sử dụng, không cho client tự đặt version cực lớn để gây DoS. Nếu scope còn phụ thuộc customer/subject, cũng phải kiểm tra **actor identity và quyền đọc**; chỉ kiểm tenant ID như minh họa không đủ cho hệ hỗ trợ nhiều customer cùng tenant. `OrderReadPort.findVisible` luôn có predicate quyền, cả primary lẫn replica.

**Giới hạn của cách này:**

- Nó bảo đảm **không trả thấp hơn version tối thiểu** nếu version tăng đơn điệu và primary hiện tại còn bảo toàn commit.
- Nó **không bảo đảm** replica không chậm cho các read **không mang floor**, cũng không biến projection `/orders/search` thành strongly consistent.
- Nếu order đã bị xóa, cần tombstone/version của lệnh xóa hoặc primary để tránh replica trả lại hàng cũ.
- Nếu primary sau failover có version thấp hơn floor, **không được lặng lẽ trả bản thấp hơn**; kích hoạt chính sách error/reconciliation thay vì tuyên bố RYW đã được đáp ứng.

### 8.1. Bounded wait trên replica cần kiểm soát tài nguyên

Thay vì fallback ngay, có thể poll replica với deadline ngắn. Nhưng mỗi request chờ giữ tài nguyên; ví dụ 1.000 requests chờ 2 giây có thể tự tạo overload khi replica lag. Nên có **concurrency cap, timeout toàn yêu cầu, retry có jitter, metrics** và chính sách khi hết thời gian. Với Spring MVC/JDBC, chờ đồng bộ tiêu servlet worker; WebFlux/R2DBC có thể sử dụng non-blocking delay, nhưng cũng phải giới hạn số subscription.

## 9. Transaction isolation, cache và multi-region: những đường vòng làm mất RYW

### 9.1. Một read transaction cũ có thể tiếp tục nhìn snapshot cũ

Ngay cả khi replica đã apply commit, một transaction đọc với **repeatable-read snapshot được mở trước đó** có thể vẫn thấy trạng thái cũ tùy database. “Chờ WAL replay đủ xa” không tự thay snapshot của transaction đang mở. Hãy bắt đầu **query/transaction mới** sau khi đạt checkpoint; không giữ transaction/EntityManager dài và kỳ vọng nó refresh tự động.

Với Spring, `@Transactional(readOnly=true)` chủ yếu là **hint/transaction mode**, không phải bảo đảm freshness; một transaction read đã dùng replica có thể kéo mọi repository call sau đó vào cùng datasource/snapshot. Cấu hình routing dựa vào `TransactionSynchronizationManager.isCurrentTransactionReadOnly()` cần được review thứ tự acquisition connection và proxy/self-invocation; ví dụ trên chủ động chọn adapter để giảm sự mơ hồ.

### 9.2. CDN và application cache có thể phá hợp đồng

~~~http
GET /v1/orders/o-42 HTTP/1.1
If-None-Match: "order-v6"
Authorization: Bearer <redacted>

HTTP/1.1 200 OK
ETag: "order-v7"
Cache-Control: private, no-store
Content-Type: application/json

{"id":"o-42","status":"PAID","version":7}
~~~

Ngay cả GET đi primary vẫn có thể bị trả dữ liệu cũ nếu gateway, Redis cache, ứng dụng hoặc browser dùng stale entry. Dữ liệu đơn có quyền truy cập nhạy cảm thường chọn `Cache-Control: no-store`. Nếu cần cache để scale, key phải gồm tenant/actor hoặc policy visibility, phiên bản representation/`Vary` tương ứng; invalidate đúng lúc sau ghi và đánh giá RYW trên cả **đường cache hit lẫn miss**.

Một `304 Not Modified` do cache/replica trả theo ETag v6 có thể gây “không cập nhật” giả khi primary đã ở v7; cần đánh giá freshness trước khi áp conditional request. **Không dùng `ETag` như authentication token hoặc expose version nội bộ nhạy cảm** nếu policy không cho phép.

### 9.3. Phân quyền có thể stale hơn chính bản ghi

User vừa bị thu hồi quyền truy cập, nhưng read replica chứa bảng ACL/tenant membership cũ: query scoped theo **quyền cũ** có thể vẫn trả dữ liệu. Vì thế “query theo tenant” là điều kiện cần, chưa đủ nếu **nguồn quyền** cũng eventual. Với thao tác nhạy cảm, phân quyền dùng nguồn đủ mới, token TTL/revocation policy phù hợp và tái kiểm quyền tại điểm thực thi. Không nhận `X-Tenant-Id` do caller tự khai để chọn primary hay mở rộng scope.

### 9.4. Failover và cross-region cần định nghĩa lại bảo đảm

Nếu primary A đã ACK ghi nhưng replica B chưa nhận commit rồi B được promote, ứng dụng có thể thấy commit “biến mất” tùy chế độ replication/failover. Không dùng RYW token cũ để giả vờ dữ liệu chắc chắn còn ở B: cần RPO được công bố, kiểm soát promotion/fencing, event/reconciliation và phát hiện divergence. **Synchronous replication có thể giảm một loại rủi ro**, nhưng đổi lấy latency/availability và vẫn phải thiết kế query/caches.

Nếu một actor ghi ở region X rồi GET ở region Y, session affinity tới **app region** không bảo đảm data region Y đã catch up. Policy có thể route RYW về leader region, chờ checkpoint hoặc dùng tối thiểu version đã ký. Cần đặt timeout/circuit breaker để tránh thác lỗi khi leader không truy cập được.

## 10. Quan sát replica lag và tỷ lệ vi phạm hợp đồng

Chỉ đo replica lag ở database là chưa đủ để kết luận API có RYW. Một **dashboard vận hành** nên kết hợp:

| Tín hiệu | Ý nghĩa | Cẩn trọng |
|---|---|---|
| WAL/GTID receive/replay position, apply delay | Replica đang ở đâu so với primary | Không luôn đo trực tiếp freshness của từng resource |
| `replica_read_stale_total` | Số lần đọc replica trả version thấp hơn floor | Phải có floor/version quan sát được |
| `ryw_fallback_primary_total` | Số lần fallback từ replica sang primary | Tăng đột biến báo replica chậm hoặc policy quá gắt |
| `ryw_wait_duration` p50/p95/p99 | Thời gian chờ replica đạt checkpoint | Theo dõi đuôi dài, timeout và concurrency |
| `read_source` primary/replica/cache | Phân bổ tải và nơi stale phát sinh | Label theo nhóm route, không user ID/token |
| `post_then_get_not_found` | Tỷ lệ 404 sau tạo thành công có căn cứ correlation | Phân biệt 404 visibility thật và 404 giả |
| Primary CPU/IO/connections, replica replay lag | Chi phí fallback và tải query | Tránh fallback storm làm primary sụp |

Metrics/log không được chứa JWT, raw consistency token, địa chỉ khách hàng hoặc Redis key có PII. Dùng **route template**, outcome category, region/replica ID đã cho phép và correlation ID. Với tracing, ghi span: `write_commit` → `read_source` → `freshness_floor_met`, không serialise toàn bộ order vào span attributes.

Đặt alert dựa trên **SLO người dùng**: ví dụ số GET strong không đạt minimum version sau deadline, tỷ lệ fallback hoặc 404 giả trong session; replica lag kỹ thuật là **leading indicator**, không thay kiểm thử API từ bên ngoài. Khi lag tăng, có thể tạm route những endpoint critical qua primary và giảm lưu lượng export/reporting theo kế hoạch năng lực.

## 11. Kiểm thử: giả lập replica trễ và xác minh response thực

### 11.1. Ma trận các tình huống

| Ca | Điều kiện | Kỳ vọng |
|---|---|---|
| C01 | POST tạo order, primary commit | **201 + Location + DTO** đúng, không đọc replica trong đường trả response |
| C02 | Replica chưa có order, GET detail critical | **200 từ primary**, không 404 giả |
| C03 | Replica v6, primary v7, floor v7 | Không trả v6; primary fallback hoặc chờ đến v7 |
| C04 | Replica v8, floor v7 | Có thể trả v8 nếu visibility/policy cho phép |
| C05 | Không có floor, GET list eventual | Có thể vắng order mới nếu contract đã công bố |
| C06 | `If-None-Match: "order-v6"`, primary v7 | Không trả 304 giả từ replica v6 trên đường RYW |
| C07 | Floor/token tenant B gửi cho order tenant A | Từ chối/404 theo policy; không tiết lộ row A |
| C08 | User bị thu hồi quyền, ACL replica cũ | Không trả dữ liệu nếu contract yêu cầu revocation freshness |
| C09 | Replica không bắt kịp trước deadline | Fallback/error đúng, không treo worker vô hạn |
| C10 | Failover khiến version primary mới thấp hơn floor | Không khẳng định RYW thành công; cảnh báo/reconcile |
| C11 | Order đã DELETE nhưng replica còn bản cũ | Không “hồi sinh” ở đường strong |
| C12 | Cache giữ ETag/DTO v6 sau PATCH v7 | Cache bị bypass/invalidate/validate đúng contract |
| C13 | POST mất response rồi retry | Idempotency ngăn tạo thêm order, không dựa vào 404 replica |
| C14 | Nhiều request strong khi replica lag | Fallback bounded, primary không bị bão tải |

### 11.2. JUnit/Mockito: chứng minh chọn đúng nguồn đọc

~~~java
@ExtendWith(MockitoExtension.class)
class OrderConsistencyTest {
    @Mock OrderReadPort primary;
    @Mock OrderReadPort replica;

    @Test
    void getFreshUsesPrimaryEvenWhenReplicaIsBehind() {
        var actor = new Actor(UUID.randomUUID(), UUID.randomUUID());
        UUID id = UUID.randomUUID();
        var expected = new OrderView(id, "PAID", 7);
        when(primary.findVisible(actor, id))
            .thenReturn(Optional.of(expected));

        var queries = new OrderQueryService(primary, replica);
        assertEquals(expected, queries.getFresh(actor, id));
        verify(primary).findVisible(actor, id);
        verifyNoInteractions(replica);
    }

    @Test
    void versionFloorRejectsStaleReplicaAndFallsBack() {
        var actor = new Actor(UUID.randomUUID(), UUID.randomUUID());
        UUID id = UUID.randomUUID();
        var old = new OrderView(id, "CREATED", 6);
        var current = new OrderView(id, "PAID", 7);
        when(replica.findVisible(actor, id)).thenReturn(Optional.of(old));
        when(primary.findVisible(actor, id)).thenReturn(Optional.of(current));

        var reader = new VersionAwareOrderReader(primary, replica);
        var floor = new VerifiedReadFloor(actor.tenantId(), id, 7);
        assertEquals(current, reader.readAtLeast(actor, id, floor));
        verify(replica).findVisible(actor, id);
        verify(primary).findVisible(actor, id);
    }
}
~~~

Ví dụ cần imports JUnit 5/Mockito và các kiểu minh họa ở Mục 7–8. `VerifiedReadFloor` trong unit test là **giá trị đã xác minh giả định**; hãy kiểm chữ ký/expiry/actor scope thực ở test token verifier. Đừng biến floor do client tự truyền thành input tin cậy ở production.

### 11.3. HTTP integration test quan trọng hơn unit test routing

Với Spring MVC, test qua `MockMvc` nên khẳng định POST trả `201`/`Location`/DTO và GET detail **cùng actor** thấy version vừa ghi, dù replica stub cố ý trả rỗng. Dùng `@SpringBootTest` + `@AutoConfigureMockMvc`, `@MockitoBean` đúng boundary và Spring Security Test `jwt()` cho các test contract. **`jwt()` chỉ mô phỏng principal**, không thay kiểm tra signature/issuer/audience trên resource-server integration test.

Với database thật, dùng môi trường primary–replica có thể **tạm dừng replay có kiểm soát** (ví dụ test infrastructure/containers hoặc network fault injection phù hợp engine), tạo commit, gọi HTTP ngay rồi cho replica bắt kịp. Test cả failover, replica outage, snapshot cũ, cache hit và thao tác DELETE. Không giả lập replica lag bằng `Thread.sleep(200)` rồi coi test deterministic: dùng synchronization/checkpoint có timeout và đo **version quan sát được**.

### 11.4. Chứng minh consistency không che lỗi bảo mật

Tạo order của tenant A; tenant B gọi cùng ID khi primary có order nhưng replica chưa có. B **không** được nhận “replica đang chờ order A” hoặc `409` với trạng thái A. Test 404 trung tính, không body/header/ETag khác biệt có thể dùng để dò. Cùng lúc kiểm tra user A đọc được order vừa ghi. Truy vấn primary **vẫn phải scoped**, không cho consistency token đóng vai trò authorization.

## 12. Bài tập áp dụng và checklist

**Tình huống:** hệ thống checkout có primary ở region A, replica ở region B. `POST /v1/orders` commit thành công, trả `201 Location`, sau đó mobile app tại B gọi `GET /v1/orders/{id}` và thấy 404 trong 800 ms. Một số user thử lại POST vì tưởng đơn không tạo, gây trùng.

**Yêu cầu:** xác định nguyên nhân có thể, chọn hợp đồng RYW cho GET detail, xử lý retry POST, thiết kế test và metric để xác minh giải pháp.

**Lời giải tham khảo:**

1. Phân biệt primary commit, replica replay và cache; đo lag/correlation, không kết luận chắc chắn do replica trước khi kiểm router, transaction và cache.
2. Trả DTO/id/version trong `201`; định tuyến **GET detail critical đến primary** hoặc dùng version gate có token đã ký, bounded wait và primary fallback. Nếu GET collection vẫn eventual, document riêng và UX có trạng thái pending.
3. POST dùng `Idempotency-Key` scoped và outcome durable; retry **cùng key** cho cùng ý định, không dựa vào GET replica để quyết định tạo mới.
4. Test replica cố ý trễ, GET detail của actor tạo vẫn 200 với version đã commit, tenant khác vẫn 404 trung tính; test duplicate POST, ETag v6/v7, timeout/failover.
5. Theo dõi lag p95/p99, fallback ratio, 404-after-201, primary load và hợp đồng RYW; ngăn fallback storm.

**Câu hỏi nâng cao:** PATCH trả `204` với ETag v8; client lập tức GET qua replica và nhận body v7. Hệ thống đã giải quyết lost update nếu dùng `If-Match` đúng chưa? **Có thể đã ngăn lost update tại thời điểm ghi**, nhưng vẫn **vi phạm RYW** nếu client được hứa nhìn thấy v8. Cần sửa read routing/freshness; thêm `If-None-Match` không đủ.

**Checklist trước production:**

- [ ] Chỉ rõ endpoint nào **eventual**, endpoint nào hứa RYW/strong; không đồng nhất HTTP 201 với replica đã catch up.
- [ ] Có response DTO/`Location`/version sau ghi, đồng thời contract GET sau đó phù hợp.
- [ ] Không dùng `@Transactional(readOnly=true)` để suy luận datasource; reader primary/replica được chọn và test rõ.
- [ ] Nếu dùng floor token: ký, TTL, scope actor/tenant/resource, kiểm minimum version; xử lý DELETE/failover.
- [ ] Chờ replica có deadline, concurrency cap và fallback/error policy; không sleep cố định.
- [ ] ETag/304, app cache, CDN, session và permission source không phá RYW hay tenant isolation.
- [ ] Ghi qua transaction đúng, có idempotency/reconciliation để xử lý POST timeout; precondition bảo vệ lost update.
- [ ] Test lag thực, stale 404/200/304, quyền, cache, failover, nhiều region; có metric quan sát SLO.

**Đọc thêm:** [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110), [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111), [PostgreSQL — Monitoring Streaming Replication](https://www.postgresql.org/docs/current/monitoring-stats.html), [PostgreSQL — Warm Standby](https://www.postgresql.org/docs/current/warm-standby.html), [Spring — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html), [Spring — Testing](https://docs.spring.io/spring-framework/reference/testing.html).

**Kết luận:** read replica giúp scale nhưng **thời điểm commit trên primary và thời điểm dữ liệu quan sát được ở replica là hai mốc khác nhau**. Một REST API đáng tin phải nêu rõ freshness contract, dùng primary hoặc version-aware read khi cần RYW, giữ HTTP/ETag/cache nhất quán với lời hứa đó và kiểm thử cả replica lag lẫn bảo mật đa tenant. Không thể chữa stale read chỉ bằng “retry vài lần” mà bỏ qua đường dữ liệu và điều kiện nghiệp vụ.

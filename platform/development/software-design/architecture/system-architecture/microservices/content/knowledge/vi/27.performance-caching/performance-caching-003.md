# Giảm số lần trao đổi mạng và tránh API quá vụn

**Nhóm kiến thức:** Hiệu năng và bộ nhớ đệm trong thiết kế hệ thống, kiến trúc microservices và ứng dụng phân tán.

Một microservice có thể phản hồi trong vài mili giây khi được thử riêng nhưng toàn bộ trang ứng dụng vẫn tải trong nhiều giây. Nguyên nhân đôi khi không phải CPU hoặc thuật toán mà là **quá nhiều lời gọi mạng nhỏ, phụ thuộc nối tiếp và trao đổi dữ liệu không theo nhu cầu sử dụng**. Một trang đơn hàng gọi API lấy danh sách, sau đó gọi thêm API lấy tên sản phẩm, giá, kho hàng và trạng thái thanh toán cho từng đơn có thể tạo hàng chục hoặc hàng trăm request. Mỗi request đều có chi phí mạng, xếp hàng, xác thực, xử lý, serialization và ghi log.

Thiết kế API quá vụn (chatty API) là tình trạng một thao tác nghiệp vụ cần nhiều cuộc trao đổi mạng hơn mức hợp lý. Giải pháp không phải đơn giản gộp mọi dữ liệu thành một API khổng lồ, mà là **đặt ranh giới gọi mạng theo nhu cầu nghiệp vụ, giữ phạm vi dữ liệu vừa đủ, đo đường đi tới hạn và kiểm soát tải lên các dịch vụ phía sau**.

Bài học này hướng dẫn nhận diện N+1 call, lựa chọn batch/bulk API, API composition, backend-for-frontend, đọc theo nhu cầu, caching, truyền đồng bộ hoặc bất đồng bộ, tối ưu giao thức, thiết kế lỗi một phần, kiểm thử hiệu năng và cách chuyển đổi API mà vẫn giữ hợp đồng hệ thống.

## 1. Vấn đề cốt lõi: một thao tác nghiệp vụ có bao nhiêu lần vượt qua mạng?

Giả sử ứng dụng hiển thị 30 đơn hàng. API danh sách chỉ trả về orderId. Client sau đó gọi thêm 30 request lấy người mua, 30 request lấy tình trạng thanh toán và 30 request lấy tồn kho. Từ một thao tác hiển thị có thể phát sinh:

~~~text
GET /orders?limit=30                      1 request

30 × GET /customers/{customerId}         30 requests
30 × GET /payments/by-order/{orderId}     30 requests
30 × GET /inventory/for-order/{orderId}   30 requests

Tổng cộng: 91 request ở phía client
(chưa tính các lời gọi phát sinh bên trong từng service)
~~~

Nếu BFF/API Gateway cũng tiếp tục fan-out từng phần tử qua nhiều tầng, số cuộc trao đổi thực tế còn lớn hơn. Những lời gọi lặp lại dễ bị che khuất trong SDK, ORM, resolver GraphQL hoặc mapper đối tượng.

Một cách tiếp cận có chủ đích hơn:

~~~text
Client
  |
  | 1 request theo màn hình / nghiệp vụ
  v
Orders View API / BFF
  |
  +--> Orders Service: lấy 30 đơn
  +--> Customer Service: batch theo danh sách customerId
  +--> Payment Service: batch theo danh sách orderId
  +--> Inventory Service: batch theo danh sách SKU nếu thật sự cần
  |
  v
Trả một response đã tổng hợp, được phân trang và chọn trường
~~~

Số round trip phía client giảm đáng kể; phía server vẫn phải gọi các nguồn dữ liệu cần thiết, nhưng có thể **batch, thực thi có giới hạn và cache** thay vì lặp theo từng phần tử.

Cần phân biệt ba đại lượng:

- **Số request từ client đến hệ thống:** ảnh hưởng trải nghiệm thiết bị, kết nối và tiêu thụ tài nguyên edge.
- **Số RPC/HTTP giữa các dịch vụ:** ảnh hưởng latency tổng, tải mạng nội bộ, downstream và độ phức tạp chuỗi phụ thuộc.
- **Số truy vấn DB/cache/broker ở phía sau:** ảnh hưởng hiệu năng dữ liệu và tính ổn định khi scale.

Tối ưu một tầng mà tăng mạnh chi phí ở tầng khác chưa chắc đem lại lợi ích.

## 2. Chattiness, N+1 và fan-out: các khái niệm cần phân biệt

| Hiện tượng | Bản chất | Dấu hiệu |
|---|---|---|
| **Chatty API** | Một thao tác cần nhiều tương tác nhỏ qua mạng | Timeline có nhiều span cùng kiểu, payload nhỏ, nhiều RTT |
| **N+1 HTTP/RPC** | Sau một lời gọi lấy N phần tử, phát sinh thêm một lời gọi cho mỗi phần tử | GET list rồi N × GET detail |
| **N+1 database query** | Sau một truy vấn lấy N record, ORM hoặc code gọi thêm N truy vấn | ORM lazy loading từng quan hệ |
| **Fan-out** | Một request đầu vào gọi đồng thời/nối tiếp nhiều dependency | Một API gateway gọi hàng chục service |
| **Under-fetching** | Response chưa chứa dữ liệu cần thiết, client phải gọi bổ sung | Client tải danh sách rồi tải từng thuộc tính |
| **Over-fetching** | Response chứa nhiều dữ liệu không cần | Một endpoint trả cả cây đối tượng rất lớn |
| **Waterfall** | Các lời gọi tuần tự, mỗi lời gọi chờ kết quả của lời trước | A → B → C → D trên critical path |
| **Request amplification** | Một request đầu vào tạo rất nhiều việc hoặc retry phía sau | 100 RPS ngoài tạo 3.000 RPC/s trong |

**N+1 database query và N+1 HTTP** có nguyên nhân bề ngoài tương tự nhưng cần giải ở vị trí khác. Với ORM, có thể sử dụng projection, join hoặc batch loading. Với RPC, cần cân nhắc hợp đồng bulk, composition hoặc cache. Đưa toàn bộ dữ liệu vào một microservice để tránh network call không phải lúc nào cũng chấp nhận được: điều đó có thể phá ranh giới sở hữu dữ liệu.

Nhiều request chưa chắc là sai nếu chúng độc lập, cần streaming hoặc phục vụ các tác vụ khác nhau. Vấn đề là **số lần trao đổi không tương xứng với giá trị và làm xấu SLO hoặc năng lực chịu tải**.

## 3. Vì sao mỗi request có chi phí?

Một lời gọi dịch vụ có thể đi qua:

~~~text
Caller
  -> DNS / chọn kết nối từ pool
  -> TCP/TLS hoặc kênh truyền đang có
  -> network routing / proxy / service mesh
  -> xếp hàng ở server
  -> xác thực/ủy quyền
  -> deserialize request
  -> business logic + DB/downstream
  -> serialize response
  -> network về caller
  -> parse kết quả và cập nhật state
~~~

Không phải lúc nào request cũng tạo kết nối mới: connection pooling, HTTP keep-alive, HTTP/2 multiplex và HTTP/3 có thể tiết kiệm đáng kể chi phí thiết lập kết nối. Nhưng ngay cả trên một kết nối đã được tái sử dụng, request vẫn có **overhead xử lý, header, scheduling, latency lan truyền và khả năng thất bại**.

Vì vậy, đổi từ HTTP/1.1 sang HTTP/2 không tự giải quyết một hệ thống gọi 100 lần để dựng một màn hình. Transport tối ưu có thể làm chi phí từng request nhỏ hơn nhưng **không sửa ranh giới API bị phân mảnh**.

### 3.1. Độ trễ nối tiếp cộng dồn

Giả sử một lời gọi phụ thuộc trung bình mất 30 ms và một trang phải chờ 20 lời gọi **nối tiếp**. Phần độ trễ do chuỗi đó có thể gần:

~~~text
20 × 30 ms = 600 ms
~~~

Thời gian còn cộng thêm thao tác ban đầu, render, DB và client. Đây là ví dụ minh họa, không phải ước tính cố định cho mọi mạng.

Với lời gọi độc lập chạy **song song**, thời gian lý tưởng của nhóm gần với lời gọi chậm nhất, nhưng thực tế còn có queue, pool, CPU, giới hạn concurrency và phần phụ thuộc chung. Công thức tư duy:

~~~text
T_sequential ≈ tổng các thời gian trên đường nối tiếp

T_parallel ≈ max(thời gian các nhánh độc lập)
             + overhead điều phối
             + thời gian chờ tài nguyên

T_request ≈ thời gian trên critical path
            + các đoạn xử lý trước/sau
~~~

Đưa 20 cuộc gọi sang chạy song song có thể giảm latency nhưng **không giảm tổng số request**. Khi nhiều người dùng cùng thực hiện, lượng kết nối và công việc downstream có thể tăng đột biến. Nên giải bài toán ở hai lớp: giảm các lời gọi không cần, rồi tối ưu lịch thực thi những lời gọi còn lại.

### 3.2. Kích thước dữ liệu cũng quan trọng

Một batch quá lớn có thể giảm RTT nhưng tạo payload vài chục MB, tốn CPU serialize, RAM, băng thông, GC và thời gian chờ. Tối ưu hiệu năng là cân bằng giữa:

~~~text
Chi phí tổng ≈ số round trip × overhead mỗi request
               + số byte truyền × chi phí truyền/xử lý
               + chi phí phía server
               + chi phí hàng đợi và lỗi
~~~

Công thức là mô hình tư duy, không phải phương trình dự đoán latency chính xác. Không thể chọn batch size chỉ bằng số RTT nếu không đo kích thước message và tài nguyên.

## 4. Bước đầu tiên: đo trước khi đổi API

Tối ưu mà không đo có thể vô tình chuyển tải sang DB, tăng response size hoặc làm cache kém hiệu quả hơn.

Các chỉ số tối thiểu:

| Chỉ số | Mục đích | Câu hỏi |
|---|---|---|
| Client requests per user action | Số lần trao đổi ngoài | Một thao tác tạo bao nhiêu request? |
| Internal RPC calls per inbound request | Fan-out thực tế | Một API call tạo bao nhiêu call downstream? |
| Span count / trace depth | Độ sâu chuỗi gọi | Có N+1 hoặc waterfall không? |
| p50/p95/p99 latency | Độ trễ cảm nhận và đuôi | Người dùng chậm nhất chịu tác động gì? |
| Payload bytes in/out | Khối lượng truyền | Batch có làm dữ liệu quá lớn không? |
| DB query count per request | N+1 phía dữ liệu | Mỗi đơn hàng có thêm truy vấn riêng không? |
| Connections active / wait | Áp lực pool | Tăng parallelism có nghẽn pool không? |
| Timeout/retry rate | Hiệu ứng lỗi dây chuyền | Có retry amplification không? |
| CPU, heap, GC, network | Chi phí xử lý | Giảm RPC có tăng CPU/heap không? |
| Cache hit/miss và dữ liệu stale | Hiệu quả cache | Có giảm truy vấn thật không? |
| Downstream saturation | Điểm nghẽn chung | API nhanh hơn nhưng DB yếu đi? |

Dùng distributed tracing để xem cả cây lời gọi. Một trace giả định:

~~~text
GET /order-summary                     820 ms
  ├─ GET /orders/123                    45 ms
  ├─ GET /items?order=123               70 ms
  ├─ GET /catalog/items/a               36 ms
  ├─ GET /catalog/items/b               34 ms
  ├─ GET /catalog/items/c               41 ms
  ├─ ...
  ├─ GET /inventory/a                   39 ms
  ├─ GET /inventory/b                   42 ms
  └─ GET /inventory/c                   40 ms
~~~

Nếu timeline thể hiện các span lặp nối tiếp, ứng viên tối ưu là bulk lookup hoặc projection. Nếu các span có thời gian rất dài do database chậm, chỉ gộp request không giải quyết được nút cổ chai.

**Lưu ý khi quan sát:** span nên có service, operation và trạng thái; không đưa orderId/customerId hoặc nội dung nhạy cảm vào nhãn metric có cardinality cao. Trace sampling có thể bỏ lỡ các trường hợp hiếm; kết hợp với metric đếm và log có kiểm soát.

## 5. Nguyên tắc chính: thiết kế API theo công việc của người gọi

API quá vụn thường xuất hiện khi endpoint phản ánh máy móc từng bảng hoặc từng field:

~~~text
GET /orders/{id}
GET /orders/{id}/customer-id
GET /customers/{id}/name
GET /customers/{id}/tier
GET /orders/{id}/status
GET /orders/{id}/line-items
GET /items/{sku}/price
GET /items/{sku}/image
~~~

Với màn hình danh sách đơn, người dùng cần **một tác vụ đọc có ngữ nghĩa rõ ràng**: lấy thông tin vừa đủ để hiển thị 20 đơn. Endpoint nên phản ánh use case như:

~~~http
GET /orders?view=summary&limit=20&cursor=...
~~~

Response có thể là:

~~~json
{
  "items": [
    {
      "orderId": "ord-101",
      "createdAt": "2026-11-12T02:00:00Z",
      "status": "PAID",
      "customerDisplayName": "Khách hàng A",
      "amountMinor": 125000,
      "currency": "VND",
      "lineItemCount": 3
    }
  ],
  "nextCursor": "opaque-next-page-token"
}
~~~

Tuy nhiên, trường **customerDisplayName** có thể thuộc Customer Service, còn status thanh toán thuộc Payment Service. Việc trả response tổng hợp không đồng nghĩa Orders Service được trực tiếp truy cập bảng DB của các service khác. Cần chọn **composition, projection hoặc read model** phù hợp quyền sở hữu dữ liệu và nhu cầu nhất quán.

### 5.1. Ranh giới API đủ thô nhưng không quá thô

**Quá vụn:** một lời gọi lấy một thuộc tính hoặc một record, client tự ghép hàng chục lượt.

**Vừa đủ:** một API phản ánh một thao tác có ý nghĩa, cho phép chọn phạm vi và trả số lượng mục được giới hạn.

**Quá thô:** endpoint trả tất cả lịch sử đơn, hồ sơ khách hàng, chi tiết giao vận, hóa đơn, trạng thái thanh toán và hàng nghìn item dù màn hình chỉ cần tiêu đề.

Điểm cân bằng phụ thuộc use case, network, UI, thiết bị, độ nhạy dữ liệu và khả năng mở rộng. Không nên biến mọi API thành một endpoint “getEverything” không có giới hạn vì sợ nhiều round trip.

## 6. Batch read: gộp nhiều tra cứu cùng loại

Đây là một biện pháp đơn giản và hiệu quả khi có N lời gọi **cùng resource, cùng logic và không phụ thuộc nối tiếp**.

Trước tối ưu:

~~~http
GET /inventory/availability/SKU-001
GET /inventory/availability/SKU-002
GET /inventory/availability/SKU-003
GET /inventory/availability/SKU-004
...
~~~

Sau tối ưu, một endpoint batch:

~~~http
POST /internal/inventory/availability:batchGet
Content-Type: application/json

{
  "skus": ["SKU-001", "SKU-002", "SKU-003", "SKU-004"]
}
~~~

Response:

~~~json
{
  "results": [
    {"sku": "SKU-001", "status": "FOUND", "available": 12},
    {"sku": "SKU-002", "status": "FOUND", "available": 0},
    {"sku": "SKU-003", "status": "NOT_FOUND"},
    {"sku": "SKU-004", "status": "FOUND", "available": 8}
  ]
}
~~~

**Điểm quan trọng trong hợp đồng:**

1. Giới hạn **maxItems** theo request, ví dụ 100 hoặc mức đo được.
2. Dedupe key nếu caller có nhiều line item cùng SKU; ghi rõ kết quả có giữ thứ tự input không.
3. Thiết kế lỗi từng phần tử: SKU không tồn tại không làm cả batch thất bại nếu use case chấp nhận.
4. Phân biệt lỗi từng record với lỗi toàn request như chưa xác thực, body quá lớn hoặc service lỗi hạ tầng.
5. Có deadline và limit concurrent batch; một batch không được giữ worker vô hạn.
6. Trả dữ liệu tối thiểu; không trả toàn bộ record inventory khi chỉ cần số lượng sẵn có.
7. Áp phân quyền **theo từng đối tượng** nếu dữ liệu phân vùng theo tenant hoặc quyền riêng.
8. Hỗ trợ metrics theo số mục và bytes; kiểm tra batch có thực sự giảm số truy vấn DB/RPC phía sau hay chỉ chuyển vòng lặp vào server.
9. Định nghĩa consistency: các phần tử được đọc trong cùng snapshot hay có thể khác thời điểm?
10. Nếu có cache, cân nhắc cache theo key và chiến lược invalidate.

**POST cho batch read** có thể hợp lý khi danh sách khóa dài, tránh trần URL và cho request body có cấu trúc. Đây là thao tác đọc về ngữ nghĩa nhưng POST mặc định không có khả năng cache tự động giống GET ở nhiều client/proxy. Nếu cần HTTP cache, có thể dùng GET với tham số giới hạn hoặc cấu hình rõ cơ chế cache ở ứng dụng.

### 6.1. Phân biệt batch và bulk

Trong tài liệu/API của nhiều hệ thống, **batch** chỉ gộp nhiều thao tác, **bulk** có thể nhấn mạnh xử lý lượng lớn; tên không có nghĩa chuẩn duy nhất. Điều cốt lõi là hợp đồng: giới hạn kích thước, tính nguyên tử, thứ tự, lỗi từng phần, idempotency và khả năng retry.

Một API cho 50 key không nhất thiết phù hợp với 1 triệu key. Với dữ liệu cực lớn, dùng pagination, export job, streaming hoặc batch worker thay vì cho phép một HTTP request không giới hạn.

## 7. Batch write: cần quyết định atomicity và idempotency

Batch đọc thường dễ hơn batch ghi. Với lệnh cập nhật 100 sản phẩm, phải trả lời:

- **All-or-nothing:** toàn batch commit hoặc rollback khi bất kỳ mục nào lỗi?
- **Partial success:** mục hợp lệ được xử lý, mục lỗi được báo riêng?
- **Ordering:** thứ tự thao tác trong batch có ảnh hưởng kết quả không?
- **Duplicate:** caller retry cả batch khi một vài mục đã thành công, có ghi trùng không?
- **Transaction boundary:** các mục có cùng database hay phải gọi nhiều service?
- **Authorization:** caller được sửa mọi item trong batch hay chỉ một phần?
- **Size/deadline:** nếu batch quá lớn, có cần async job thay vì giữ HTTP kết nối?

Một response cho partial success nên mang kết quả đủ để client quyết định retry chính xác phần thất bại:

~~~json
{
  "batchId": "batch-2104",
  "results": [
    {"itemId": "p-1", "status": "UPDATED", "version": 7},
    {"itemId": "p-2", "status": "REJECTED", "code": "FORBIDDEN"},
    {"itemId": "p-3", "status": "RETRYABLE", "code": "DEPENDENCY_UNAVAILABLE"}
  ]
}
~~~

HTTP status của toàn request phải được thiết kế theo hợp đồng API; có thể có 200 với danh sách kết quả từng mục hoặc một mã tổng hợp phù hợp, nhưng đừng chỉ dựa vào status 200 để tuyên bố mọi mục đã hoàn thành. Mã **207 Multi-Status** thuộc WebDAV và không bắt buộc cho mọi batch API.

**Idempotency key:** với thao tác có tác dụng phụ, dùng idempotency key theo request hoặc từng item, lưu trạng thái xử lý với phạm vi và thời hạn rõ. Nếu có partial success và caller retry, server cần tránh làm lại những thao tác đã commit. Gửi một batch nhiều lần không được tự nhiên hiểu là an toàn.

Nếu cần giao dịch phân tán giữa nhiều service, không nên hứa “atomic batch” chỉ nhờ một endpoint tổng hợp. Cân nhắc saga/compensation, transactional outbox, workflow bền vững hoặc thay đổi cách phân chia trách nhiệm nghiệp vụ.

## 8. API composition và Backend-for-Frontend (BFF)

**API composition** là tổng hợp dữ liệu từ nhiều nguồn để đáp ứng một yêu cầu đọc. **BFF** là backend được thiết kế theo nhu cầu của từng loại client, ví dụ web và mobile, để tránh client tự orchestrate nhiều service.

~~~mermaid
flowchart LR
    WEB["Web / Mobile"] --> BFF["Order Summary BFF"]
    BFF --> O["Orders Service"]
    BFF --> C["Customer Service"]
    BFF --> P["Payment Service"]
    BFF --> I["Inventory Service"]
    O --> ODB[("Orders DB")]
    C --> CDB[("Customers DB")]
    P --> PDB[("Payments DB")]
    I --> IDB[("Inventory DB")]
~~~

BFF có thể giảm round trip của client và đưa logic tổng hợp về phía server gần các service. Tuy vậy, BFF trở thành một **điểm fan-out và phụ thuộc** cần thiết kế vận hành cẩn thận.

### 8.1. BFF nên chịu trách nhiệm gì?

Phù hợp:
- Lấy dữ liệu cần thiết cho màn hình cụ thể.
- Gộp nhiều lookup cùng loại.
- Chuẩn hóa response DTO, chọn fields và phân trang.
- Áp deadline, giới hạn concurrency, cache và fallback cho phần tùy chọn.
- Chuyển lỗi dependency thành thông tin đủ cho client hiển thị.
- Thực thi phân quyền ở biên và truyền danh tính/ủy quyền đúng cách đến service sở hữu dữ liệu.

Không phù hợp:
- BFF thay thế mọi nghiệp vụ của Orders, Payment hoặc Inventory.
- Ghi trực tiếp sang DB của service khác để “giảm một RPC”.
- Giữ bản sao dữ liệu nhạy cảm không có owner, retention và quyền phù hợp.
- Tạo endpoint tổng hợp không giới hạn độ sâu, số record hoặc số service.
- Cố che mọi lỗi bằng response 200 nhưng trả dữ liệu giả như thể chính xác.

Nếu cùng một read model được nhiều client cần, có thể đặt ở **query service** hay một projection chuyên dụng thay vì nhân bản logic cho từng BFF.

### 8.2. Khi nào không nên dùng BFF?

Nếu ứng dụng rất nhỏ, chỉ có hai endpoint và không có N+1 rõ ràng, thêm BFF có thể tạo thêm một network hop, một deployment và điểm lỗi. Chỉ thêm tầng composition khi dữ liệu đo được hoặc hợp đồng client cho thấy lợi ích vượt chi phí.

## 9. Gọi song song có kiểm soát thay vì waterfall

Sau khi giảm N+1, vẫn có thể còn ba dependency độc lập: Orders, Payment và Customer. Nếu không phụ thuộc dữ liệu của nhau, có thể gọi song song để rút ngắn critical path.

~~~text
TUẦN TỰ
Order 40ms -> Payment 60ms -> Customer 50ms
Tổng phụ thuộc ~150ms + overhead

SONG SONG
Order 40ms ----+
Payment 60ms --+-> tổng hợp
Customer 50ms -+
Đường nhánh chậm nhất ~60ms + overhead
~~~

Các số chỉ minh họa. Trường hợp Payment cần orderId từ Orders, phần đó không thể bắt đầu trước khi có orderId, trừ khi dữ liệu đã được cung cấp theo cách khác. Đừng ép song song các thao tác phụ thuộc rồi tạo tính không nhất quán.

### 9.1. Giới hạn fan-out và concurrency

Nếu một request tạo 10 RPC đồng thời, ở 100 request đang xử lý có thể có tới khoảng 1.000 RPC đang chờ downstream. Nếu không giới hạn connection pool và concurrency, quá trình “tăng tốc” từng request có thể làm hệ thống chung chậm hơn.

Các biện pháp:
- Giới hạn số nhánh đồng thời theo request.
- Giới hạn concurrency **toàn instance** cho từng dependency bằng semaphore/bulkhead.
- Dùng deadline theo request và chia ngân sách thời gian cho từng nhánh.
- Hủy hoặc dừng chờ các tác vụ không còn cần khi request hết deadline.
- Có rate limit hoặc admission control để chặn tải trước khi làm nghẽn backend.
- Tránh retry đồng thời trên mọi nhánh gây khuếch đại.
- Điều chỉnh pool và số replica dựa trên năng lực thực của downstream.

**Không nhầm concurrency với throughput.** Tăng concurrency khi service đang queue dài không bảo đảm tăng số request hoàn thành mỗi giây.

### 9.2. Độ trễ đuôi khi fan-out

Nếu một màn hình cần kết quả từ 12 dependency và phải chờ **tất cả**, xác suất ít nhất một nhánh chậm tăng theo số nhánh, ngay cả khi mỗi service thường khá nhanh. Kết quả tổng hợp có thể bị chi phối bởi nhánh chậm nhất.

Do vậy, giảm số dependency trên đường tới hạn đôi khi quan trọng hơn tối ưu vài mili giây ở từng service. Với thông tin tùy chọn, trả kết quả một phần có đánh dấu có thể giúp đạt SLO mà không báo sai nghiệp vụ.

## 10. Deadline, timeout và retry budget

Một API tổng hợp nên nhận **deadline tổng**, rồi phân phối ngân sách cho các bước thay vì cho mỗi service timeout rất dài.

Ví dụ:

~~~text
Tổng ngân sách request: 900 ms

Phân tích đầu vào và auth:        tối đa 80 ms
Gọi Orders:                       tối đa 200 ms
Batch Payment + Customer:         tối đa 350 ms
Tổng hợp và gửi response:         ngân sách còn lại
Dự phòng queue/network:           phần còn lại
~~~

Đây là mô hình minh họa; ngân sách thực cần dựa trên latency distribution và SLO. Nếu hai nhánh chạy song song, không nhất thiết cộng timeout như các bước nối tiếp. Tuy nhiên, mỗi nhánh vẫn phải nhận thời hạn không vượt deadline cha.

**Retry không miễn phí.** Nếu 100 request ban đầu gặp lỗi tạm thời và mỗi tầng tự retry ba lần, số call phía sau có thể nhân lên rất lớn khi nhiều tầng retry. Nên:
- Retry ở một lớp có trách nhiệm rõ.
- Chỉ retry lỗi thực sự có khả năng phục hồi, với backoff và jitter.
- Bảo đảm idempotency cho thao tác ghi.
- Không retry sau khi deadline tổng đã hết.
- Dùng retry budget và circuit breaker phù hợp.
- Đo retry attempts/initial requests và saturation, không chỉ success cuối.

Khi dependency optional không đáp ứng, có thể dùng fallback/cache và đánh dấu dữ liệu bị thiếu. Khi dependency quyết định an toàn thanh toán, không được trả “thanh toán thành công” chỉ vì muốn tối ưu latency.

## 11. CQRS và materialized read model: giảm fan-out lặp lại

Với màn hình đọc thường xuyên tổng hợp 5–10 service, mỗi lần gọi BFF vẫn tạo nhiều RPC. Một phương án khác là xây **read model** được cập nhật từ sự kiện, tối ưu theo truy vấn.

~~~mermaid
flowchart TB
    O["Orders Service"] --> OE["Order events"]
    P["Payment Service"] --> PE["Payment events"]
    C["Customer Service"] --> CE["Customer events"]
    OE --> PROJ["Order Summary Projector"]
    PE --> PROJ
    CE --> PROJ
    PROJ --> READ[("Order Summary Read DB")]
    UI["Web / Mobile"] --> API["Order Summary Query API"]
    API --> READ
~~~

Ưu điểm:
- Một truy vấn đọc có thể lấy các trường màn hình cần mà không phải fan-out nhiều RPC tại request time.
- Dễ tạo index, pagination, filter và sort theo nhu cầu hiển thị.
- Phù hợp tải đọc cao, dashboard và danh sách tổng hợp.

Đánh đổi:
- **Eventual consistency:** dữ liệu projection có thể trễ so với nguồn.
- Cần xử lý event trùng, lệch thứ tự, phiên bản schema và replay.
- Phải kiểm soát quyền xem dữ liệu gộp, retention, xóa dữ liệu và tính riêng tư.
- Projection có thể sai hoặc bị lag; cần khả năng rebuild và kiểm tra reconciliation.
- Không thích hợp để thay dữ liệu giao dịch có yêu cầu consistency nghiêm ngặt nếu chưa thiết kế bù.

**Chọn BFF composition hay read model?** Nếu màn hình ít truy cập, yêu cầu dữ liệu rất mới và chỉ có vài dependency, composition có thể đủ. Nếu truy vấn đọc nhiều, phức tạp, cùng fan-out lặp đi lặp lại và chấp nhận trễ cập nhật, read model thường đáng đánh giá.

Không phá quyền sở hữu dữ liệu bằng cách để BFF đọc thẳng database của các service. Nếu cần dữ liệu cục bộ, dùng read model với hợp đồng đồng bộ riêng và owner rõ ràng.

## 12. DataLoader và GraphQL: giải quyết N+1 ở resolver

GraphQL cho client chọn field, nhưng tự nó **không giải quyết N+1**. Một query lấy 50 orders và trường customer có thể khiến resolver gọi Customer Service 50 lần.

~~~text
orders resolver -> lấy 50 orders
customer resolver(order 1) -> RPC
customer resolver(order 2) -> RPC
...
customer resolver(order 50) -> RPC
~~~

**DataLoader** là mẫu gom các key phát sinh trong cùng một khoảng điều phối rồi gọi batch endpoint. Nó có thể cache kết quả theo key trong phạm vi request để tránh cùng một customerId được tải nhiều lần.

~~~text
50 order resolvers
    |
    v
Customer DataLoader
    |
    v
customers.batchGet([id1, id2, ..., idN])
    |
    v
Map kết quả trở lại từng resolver
~~~

Điểm phải kiểm tra:
- Batch function xử lý key trùng và giữ mapping đúng; không nhầm thứ tự khi backend trả theo thứ tự khác.
- Cache per-request không trở thành cache xuyên tenant vô tình rò dữ liệu.
- Có max batch size, giới hạn độ sâu và độ phức tạp query.
- Resolver vẫn xác minh quyền trên từng order/customer.
- Không biến một GraphQL query tùy ý thành fan-out vô hạn tới nhiều service.
- Test query depth, số database query/RPC và latency theo fixture lớn.

GraphQL có thể giảm over-fetching/under-fetching nếu triển khai tốt, nhưng cũng có thể che fan-out đắt đỏ bên trong. Điều quyết định là **cách resolver và backend tải dữ liệu**.

## 13. Chọn trường và projection: tránh gửi dữ liệu không cần

Một API list thường chỉ cần một tập trường nhỏ. Nếu trả đối tượng đầy đủ chứa mô tả dài, danh sách line item, lịch sử thanh toán và metadata, tổng bytes lớn dù chỉ có một request.

Các lựa chọn:
- **DTO theo use case:** OrderSummary, OrderDetail, PaymentStatus.
- **Field selection:** tham số fields được định nghĩa chặt, ví dụ fields=id,status,total.
- **Projection DB:** chỉ select cột cần cho response, tránh load cả entity graph.
- **GraphQL selection set:** client chọn trường; server đặt giới hạn complexity/depth.
- **Pagination:** giới hạn số record của mỗi lần lấy.
- **Conditional request/ETag:** nếu dữ liệu không đổi, không chuyển body lớn nhiều lần.

Không cung cấp field selection vô hạn nếu nó làm cache key bùng nổ hoặc tạo quá nhiều nhánh backend. DTO cố định theo các use case có lưu lượng cao thường đơn giản hơn.

### 13.1. N+1 ở ORM vẫn quan trọng

Một endpoint duy nhất ở tầng HTTP có thể tạo 500 câu SQL vì quan hệ lazy:

~~~text
GET /orders/summary
  -> SELECT * FROM orders LIMIT 50        (1)
  -> SELECT * FROM order_items WHERE ...   (50)
  -> SELECT * FROM customers WHERE ...     (50)
  -> ...
~~~

Khi đó, giảm HTTP request đã xong nhưng DB N+1 vẫn còn. Có thể sử dụng batch fetching, joins, projection hoặc truy vấn bulk tùy mô hình dữ liệu. Không dùng một giant join thiếu kiểm soát khiến row duplication và bộ nhớ tăng theo tích Descartes.

Phải đo cả **SQL query count** và **data volume** trước/sau; không kết luận một endpoint = một truy vấn.

## 14. Pagination và giới hạn kích thước batch

Một endpoint trả tất cả 200.000 records trong một lần có ít round trip nhưng tiêu tốn RAM, network và thời gian serialize, dễ timeout.

Cách tiếp cận an toàn:

~~~http
GET /orders?limit=50&cursor=eyJ...
~~~

Response:

~~~json
{
  "items": [
    {"orderId": "ord-601", "status": "PAID"},
    {"orderId": "ord-602", "status": "PENDING"}
  ],
  "nextCursor": "opaque-cursor",
  "hasMore": true
}
~~~

**Cursor pagination** hữu ích khi danh sách thay đổi nhanh và cần duyệt tuần tự, miễn là key sắp xếp ổn định và cursor được thiết kế đúng. Offset pagination đơn giản nhưng có thể chậm hoặc bỏ/trùng record dưới thay đổi dữ liệu tùy query và cơ sở dữ liệu.

Giới hạn cần xác định:
- maxPageSize và giá trị mặc định.
- maxBatchItems, maxRequestBytes, maxResponseBytes.
- Timeout và tổng ngân sách tải.
- Filter/sort được phép và index tương ứng.
- Điều kiện trả cursor hết hạn hoặc không hợp lệ.
- Quy tắc nhất quán khi dữ liệu bị sửa trong lúc phân trang.
- Quyền theo tenant và người dùng trên mỗi trang.
- Hành vi khi caller muốn export toàn bộ dữ liệu.

Với export rất lớn, tạo **asynchronous export job** và đưa kết quả vào object storage có quyền, thời hạn lưu và link hết hạn có thể phù hợp hơn giữ một kết nối HTTP lâu. Cần kiểm soát dữ liệu nhạy cảm và tránh phát link tải công khai.

## 15. Caching: giảm cả lời gọi và công việc phía sau

Cache là cách tránh gọi lại nguồn dữ liệu nếu dữ liệu đã có và phù hợp yêu cầu về độ mới.

Các vị trí cache thường gặp:

| Vị trí | Ví dụ | Lợi ích | Rủi ro |
|---|---|---|---|
| Trình duyệt/mobile | HTTP cache, local store | Tránh request ra mạng | Dữ liệu stale, quyền thay đổi, thiết bị chia sẻ |
| CDN/edge | Ảnh, dữ liệu public | Giảm latency và tải origin | Cache key và invalidation sai |
| BFF | Cache response tổng hợp | Giảm nhiều RPC phía sau | Dữ liệu từ nhiều nguồn có TTL khác nhau |
| Service | Cache Customer/Profile theo ID | Tránh lookup lặp | Cross-tenant leak, memory pressure |
| Redis/distributed cache | Read-through key-value | Dùng lại giữa replica | Cache stampede và stale |
| DB query/materialized view | Read model/index | Giảm truy vấn phức tạp | Chi phí cập nhật, eventual consistency |

Một chiến lược cache phải có:
- **Key:** gắn đủ tenant, danh tính/phạm vi quyền, schema/version và tham số filter cần thiết.
- **TTL/staleness:** dữ liệu được phép cũ bao lâu.
- **Invalidation:** khi dữ liệu thay đổi thì xóa hay cập nhật thế nào.
- **Fallthrough:** cache miss làm gì; có giới hạn tải lên nguồn không.
- **Failure behavior:** cache lỗi thì dùng DB trực tiếp, stale hoặc fail theo mức độ nhạy cảm.
- **Observability:** hit rate, miss rate, eviction, stale reads, error và stampede.

### 15.1. Cache kết quả tổng hợp cần thận trọng

Ví dụ OrderSummary có thông tin đơn hàng ít đổi, tên khách hàng có thể đổi và PaymentStatus cần cập nhật nhanh. Cache tất cả trong 10 phút có thể tạo trạng thái sai với màn hình xử lý thanh toán.

Có thể:
- Tách phần ổn định khỏi trường trạng thái thay đổi nhanh.
- Dùng TTL khác nhau cho những thành phần cụ thể.
- Cập nhật/invalidate theo sự kiện; chấp nhận eventual consistency có ghi rõ.
- Với yêu cầu xác thực trạng thái cuối cùng, đọc lại nguồn có thẩm quyền tại bước quyết định.

**Cache không phải nguồn sự thật cho hành động quan trọng nếu hợp đồng yêu cầu xác minh mới nhất.** Ví dụ hiển thị “Còn hàng” từ cache không bảo đảm checkout được phép trừ kho; bước giữ hàng cần kiểm tra/ghi tại Inventory Service.

### 15.2. Chống cache stampede

Khi một key phổ biến hết hạn, hàng nghìn request cùng miss có thể gây bão request đến DB. Các biện pháp:
- Single-flight: chỉ một tác vụ tải lại cho cùng key ở mỗi phạm vi phù hợp.
- TTL jitter để các key không hết hạn đồng loạt.
- Stale-while-revalidate khi độ mới cho phép.
- Giới hạn concurrency đi tới nguồn.
- Cache warm-up có kiểm soát cho dữ liệu phổ biến.
- Negative caching rất ngắn khi phù hợp, nhưng phải xét quyền và dữ liệu có thể mới được tạo.

Mục tiêu là giảm số lần trao đổi thật, không chỉ thay hình thức N+1 thành một đợt miss đồng loạt.

## 16. HTTP keep-alive, HTTP/2, HTTP/3 và connection pooling

Sau khi thiết kế API đúng ranh giới, tối ưu transport có thể giảm thêm chi phí.

**HTTP/1.1 keep-alive:** tái sử dụng kết nối TCP/TLS cho nhiều request khi client/server/proxy hỗ trợ. Không tạo kết nối mới cho từng request nếu không cần.

**HTTP/2:** hỗ trợ multiplex nhiều stream trên cùng một kết nối, header compression và cơ chế flow control; có thể làm giảm chi phí khi cần nhiều request. Tuy nhiên, một kết nối TCP có thể chịu tác động từ mất gói ở tầng transport, và HTTP/2 không xóa chi phí logic của fan-out.

**HTTP/3:** dùng QUIC và có đặc tính xử lý stream ở tầng transport khác TCP; lợi ích tùy mạng/client/server/proxy. Không giả định HTTP/3 luôn nhanh hơn trong mạng nội bộ latency thấp.

**gRPC:** thường dùng HTTP/2 với Protocol Buffers, hỗ trợ unary và streaming; phù hợp một số kết nối nội bộ có hợp đồng chặt. gRPC không tự ngăn service gọi N lần unary RPC; vẫn cần batch hoặc streaming khi hợp lý.

**Connection pooling:** giới hạn max connections, idle lifetime, TLS verification, timeout và cơ chế circuit breaker. Một pool quá lớn có thể đè DB/downstream; một pool quá nhỏ làm request chờ connection.

### 16.1. Khi nào streaming tốt hơn batch response?

Streaming phù hợp khi:
- Dữ liệu có thể trả dần, không cần giữ toàn bộ trong RAM.
- Client có thể tiêu thụ từng phần và chịu được partial progress.
- Tác vụ kéo dài, có flow control, hủy và backpressure.
- Kết quả có thứ tự hoặc subscription cần thiết.

Một stream dài không tự tốt hơn batch: cần thiết kế reconnect, resume token, duplicate handling, phân quyền và thời hạn kết nối. Trong mạng di động hoặc qua proxy có idle timeout, streaming có thể phức tạp hơn phân trang thông thường.

## 17. Compression và serialization: tối ưu bytes có điều kiện

Một response JSON lặp nhiều field name có thể nén khá tốt. Khi payload lớn, compression như gzip hoặc Brotli ở môi trường hỗ trợ có thể giảm network bytes, nhưng tốn CPU và tăng latency encode/decode ở payload nhỏ.

Các điểm cần đo:
- Kích thước payload trước và sau nén.
- CPU và memory của server/client khi nén/giải nén.
- Ngưỡng tối thiểu áp compression.
- Trường hợp đã nén sẵn (ảnh, video, dữ liệu nhị phân) có thể không được lợi.
- Khả năng serialization format (JSON, Protobuf, Avro...) của các client.
- Rủi ro lộ dữ liệu khi nén trộn dữ liệu bí mật với dữ liệu attacker-controlled trong cùng ngữ cảnh phản hồi nếu threat model liên quan.

**Serialization nhỏ hơn không đồng nghĩa hệ thống tốt hơn.** Nếu format chặt khiến tiến hóa schema khó, chi phí phát hành có thể tăng. Chọn format theo hợp đồng, năng lực đội, hiệu năng và compatibility.

## 18. Java/Spring Boot: tránh N+1 giữa các service

Giả sử Order Service trả danh sách order items, mỗi item có SKU. Checkout cần kiểm tra tồn kho để dựng response. Cách chưa tốt:

~~~java
for (OrderItem item : order.items()) {
    Availability availability =
        inventoryClient.getOne(item.sku()); // 1 network call / item

    result.add(toView(item, availability));
}
~~~

Với 50 items, đoạn này có thể tạo 50 HTTP calls, kể cả khi chỉ có 20 SKU khác nhau.

Một cách hợp lý hơn:

~~~java
List<String> skus = order.items().stream()
    .map(OrderItem::sku)
    .distinct()
    .toList();

Map<String, Availability> availabilityBySku =
    inventoryClient.getBatch(skus); // 1 batch request, trong giới hạn maxItems

List<OrderItemView> views = order.items().stream()
    .map(item -> toView(
        item,
        availabilityBySku.get(item.sku())))
    .toList();
~~~

Dedupe key giúp giảm khối lượng thêm. Tuy nhiên, **getBatch** phải thật sự thực hiện batch ở server; nếu nó bí mật lặp gọi getOne cho mỗi SKU, mới chỉ chuyển N+1 từ caller sang thư viện.

Nếu danh sách vượt giới hạn batch, chia thành các chunk có kích thước được duyệt. Chunk có thể chạy tuần tự hoặc song song **có giới hạn**, chứ không tạo hàng nghìn request cùng lúc.

### 18.1. API DTO cho batch availability

Một ví dụ Spring Boot đơn giản với Java record:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

record AvailabilityBatchRequest(List<String> skus) {}

record AvailabilityItem(
        String sku,
        String status,
        Integer available) {}

record AvailabilityBatchResponse(List<AvailabilityItem> results) {}

interface InventoryQueryService {
    // Truy vấn bulk theo tập SKU đã xác thực,
    // không gọi tiếp một RPC/SQL query cho mỗi SKU.
    Map<String, Integer> findAvailableQuantities(List<String> skus);
}

@RestController
@RequestMapping("/internal/inventory")
final class InventoryQueryController {
    private final InventoryQueryService queryService;

    InventoryQueryController(InventoryQueryService queryService) {
        this.queryService = queryService;
    }

    @PostMapping("/availability:batchGet")
    AvailabilityBatchResponse getBatch(
            @RequestBody AvailabilityBatchRequest request) {

        if (request == null || request.skus() == null
                || request.skus().isEmpty()
                || request.skus().size() > 100) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "1..100 SKUs required");
        }

        List<String> skus = request.skus().stream()
            .filter(Objects::nonNull)
            .map(String::trim)
            .distinct()
            .toList();

        if (skus.isEmpty()
                || skus.stream().anyMatch(s -> s.isEmpty() || s.length() > 64)) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid SKU");
        }

        Map<String, Integer> quantities =
            queryService.findAvailableQuantities(skus);

        List<AvailabilityItem> items = skus.stream()
            .map(sku -> quantities.containsKey(sku)
                ? new AvailabilityItem(sku, "FOUND", quantities.get(sku))
                : new AvailabilityItem(sku, "NOT_FOUND", null))
            .toList();

        return new AvailabilityBatchResponse(items);
    }
}
~~~

Đây là ví dụ cấu trúc API, không phải một dịch vụ hoàn chỉnh. Production còn cần xác thực, phân quyền theo tenant/SKU, validation kích thước body, quan sát, timeout, giới hạn concurrency, mapping lỗi DB và không để lộ thông tin hàng hóa ngoài phạm vi được phép. Hàm **findAvailableQuantities** có hợp đồng bulk; cách hiện thực phải được test để tránh N+1 SQL.

### 18.2. Cẩn thận với thứ tự và dữ liệu thiếu

Batch response không bắt buộc có thứ tự giống request. Caller nên map theo key. Nếu key xuất hiện nhiều lần trong input, dedupe khi gọi mạng nhưng vẫn tái dựng đúng số item của đơn. Nếu service trả thiếu key, không được mặc định available=0 nếu ý nghĩa nghiệp vụ phân biệt **không tồn tại**, **không được phép** và **lỗi tạm thời**.

Cân nhắc DTO trạng thái rõ:

~~~text
FOUND          -> có thông tin xác thực về tồn kho
NOT_FOUND      -> SKU không tồn tại theo nguồn dữ liệu
FORBIDDEN      -> caller không có quyền xem
UNAVAILABLE    -> nguồn dữ liệu tạm chưa trả lời
~~~

Khi đáp ứng màn hình mua hàng, trạng thái **UNAVAILABLE** không được tự biến thành **FOUND với số lượng 0** nếu điều đó làm thay đổi hành vi nghiệp vụ.

## 19. Ví dụ Java: xử lý batch theo chunk và concurrency hữu hạn

Nếu API Inventory cho tối đa 100 SKU nhưng đơn tổng hợp có 700 SKU, cần chia thành tối đa 7 batch. Không nên gửi 700 GET hoặc 700 RPC song song.

Mẫu ý tưởng:

~~~java
int maxBatchSize = 100;
int maxConcurrentBatches = 3;

List<List<String>> chunks = partition(distinctSkus, maxBatchSize);

// Dùng executor bounded hoặc bulkhead của hệ thống.
// Chỉ có tối đa maxConcurrentBatches batch thực thi đồng thời.
// Các batch phải chịu deadline chung của request.
List<BatchResult> results =
    boundedBatchExecutor.execute(chunks, maxConcurrentBatches,
        chunk -> inventoryClient.getBatch(chunk, requestDeadline));

Map<String, Availability> merged = mergeBySku(results);
~~~

Các hàm **partition**, **boundedBatchExecutor** và **mergeBySku** là pseudocode cho thành phần ứng dụng, không phải API Java chuẩn. Mục tiêu của ví dụ là **đặt giới hạn concurrency, deadline và xác định cách gộp lỗi một phần**.

Nếu 7 batch đều thất bại do Inventory đã quá tải, retry đồng loạt có thể làm tình hình xấu hơn. Nên có timeout, circuit breaker, retry budget và fallback phù hợp. Với giao dịch có yêu cầu nhất quán, việc chia batch có thể dẫn đến snapshot từ những thời điểm khác nhau; cần ghi rõ điều này trong hợp đồng.

## 20. Khi nào dùng caching thay vì batch?

Batch và cache giải quyết hai vấn đề khác nhau:

- **Batch** giảm số request khi nhiều key cần tải **trong cùng một thao tác**.
- **Cache** giảm số request khi **cùng key được dùng lặp lại theo thời gian**.

Ví dụ trang 50 sản phẩm:
- Dùng batch để lấy giá và tồn kho cho 50 SKU.
- Cache những trường catalog ít đổi như tên/ảnh theo SKU.
- Không cache tình trạng thanh toán cuối cùng như kết quả giao dịch đáng tin tuyệt đối khi nghiệp vụ yêu cầu xác nhận trực tiếp.

Có thể kết hợp:
1. Lấy dữ liệu từ cache bằng multi-get.
2. Xác định những key còn miss.
3. Batch fetch các key miss từ service sở hữu.
4. Điền cache theo TTL/permission policy.
5. Tái dựng response theo thứ tự của client.

Quá trình này phải giới hạn số lượng key và áp **single-flight** nếu cùng lúc có nhiều request miss cùng key. Caching không thay quyền đọc dữ liệu và cũng không cho phép bỏ qua phân quyền theo tenant.

## 21. Nhiều lời gọi mạng trong microservices: đừng tự ý dùng chung database

Một ý tưởng thường gặp là “bỏ Customer API, Orders đọc thẳng DB Customer sẽ nhanh hơn”. Điều này có thể giảm một RPC trước mắt nhưng tạo **tight coupling**:

- Orders phụ thuộc trực tiếp schema DB thuộc Customer.
- Customer không thể đổi bảng, migrate hoặc scale độc lập.
- Quyền truy cập dữ liệu và dữ liệu nhạy cảm bị mở rộng.
- Query từ Orders có thể làm quá tải DB Customer.
- Đường transaction và ownership trở nên khó xác định.

Các phương án phù hợp hơn:
- Batch API có version của Customer.
- Query service/BFF composition.
- Event-driven replication/read model với hợp đồng eventual consistency.
- Cache theo TTL hoặc sự kiện invalidate.
- Đánh giá lại ranh giới service nếu chúng vốn tách quá vụn và thực chất cùng một nghiệp vụ, nhưng đó là quyết định thiết kế lớn cần bằng chứng.

Nguyên tắc: **tối ưu network không được làm mất trách nhiệm sở hữu dữ liệu và ranh giới an ninh**.

## 22. Đồng bộ hay bất đồng bộ: chọn theo nhu cầu nhận kết quả

Không phải mọi công việc đều cần kết quả ngay trong một HTTP request.

**Đồng bộ phù hợp** khi caller cần quyết định ngay, ví dụ kiểm tra quyền hoặc tính tổng tiền trước khi xác nhận checkout. Dù vậy, cần deadline, cache/batch và xử lý dependency lỗi.

**Bất đồng bộ phù hợp** với công việc có thể hoàn tất sau:
- Gửi email/xuất báo cáo.
- Tạo thumbnail hoặc chuyển mã media.
- Cập nhật search index hoặc projection.
- Đồng bộ dữ liệu phân tích.
- Xử lý batch lớn với checkpoint.

Ví dụ:

~~~text
Client
  |
  | POST /exports
  v
Export API -> lưu Job (status=PENDING)
  |
  +--> Queue -> Export Worker -> Object Storage
  |
  v
202 Accepted + jobId

Client
  |
  +--> GET /exports/{jobId}
       hoặc nhận callback/notification
~~~

Chuyển một request dài sang job giúp không giữ HTTP connection quá lâu và xử lý tải theo queue. Nhưng nó làm xuất hiện vấn đề khác: **at-least-once delivery, idempotency, retry, DLQ, trạng thái job, quyền truy cập kết quả và kết thúc khi người dùng hủy**. Không dùng async chỉ để che một thao tác phải nhất quán ngay lập tức.

## 23. Sự cố một phần trong API tổng hợp

Giả sử API OrderSummary cần ba nguồn:

- Orders: thông tin bắt buộc.
- Payment: trạng thái thanh toán bắt buộc để quyết định nghiệp vụ.
- Recommendations: gợi ý sản phẩm tùy chọn.

Nếu Recommendations lỗi, UI có thể hiển thị đơn hàng và bỏ phần gợi ý. Nếu Orders lỗi, không có dữ liệu gốc; phải trả lỗi phù hợp. Nếu Payment lỗi, không nên tự báo “PAID” hoặc “NOT_PAID” khi trạng thái thực là unknown.

Một response tổng hợp có thể biểu diễn trạng thái từng phần một cách rõ ràng:

~~~json
{
  "order": {
    "orderId": "ord-123",
    "status": "CREATED"
  },
  "payment": {
    "status": "UNAVAILABLE",
    "lastVerifiedAt": null
  },
  "recommendations": [],
  "partial": true,
  "warnings": [
    {
      "component": "payment",
      "code": "DEPENDENCY_TIMEOUT"
    }
  ]
}
~~~

Mã HTTP và response schema cần tuân theo hợp đồng ứng dụng. Không trả 200 “thành công toàn phần” trong khi client tưởng dữ liệu thanh toán đã được xác minh. Đồng thời không phải mọi lỗi ở phần tùy chọn đều buộc toàn bộ thao tác đọc thất bại; lựa chọn phải dựa trên mức quan trọng.

**Một batch có nhiều kết quả** và **một API composition có nhiều dependency** đều cần kế hoạch partial failure. Đừng giả định vì gộp request nên mọi thao tác trở thành giao dịch nguyên tử.

## 24. Bảo mật khi gộp dữ liệu: nguy cơ BOLA và lộ dữ liệu chéo

Một endpoint batch có thể cho phép caller gửi 100 ID tùy ý. Nếu server chỉ kiểm tra quyền gọi endpoint một lần mà không kiểm tra quyền **trên từng object**, người dùng có thể đọc dữ liệu của khách hàng khác.

Ví dụ nguy hiểm:

~~~http
POST /orders:batchGet
{
  "orderIds": [
    "order-my-account",
    "order-other-tenant",
    "order-confidential"
  ]
}
~~~

Cần thực hiện:
- Authentication và authorization theo người dùng/workload gọi.
- Object-level/tenant-level authorization cho từng ID.
- Cơ chế trả lỗi không tiết lộ quá nhiều thông tin về sự tồn tại của đối tượng nhạy cảm.
- Giới hạn batch size, response size và rate limit theo caller.
- Cache key có tenant và quyền thích hợp.
- Kiểm soát PII/secret khi BFF tổng hợp nhiều nguồn.
- Không log toàn bộ danh sách ID nếu có dữ liệu nhạy cảm; metrics dùng bucket batch size thay vì label cho từng ID.
- Nếu response có các nguồn khác thời điểm, ghi rõ độ mới và quyền đối với từng trường.

**Gộp API làm tăng mức dữ liệu trả trong một phản hồi**, nên đánh giá lại threat model: mỗi trường có thực sự cần tới client hay không? Tối ưu hiệu năng không thể lấy lý do để cấp quyền đọc rộng hơn.

## 25. Thiết kế giới hạn để chống lạm dụng bulk endpoint

Một API bulk có thể trở thành phương tiện DoS nếu người dùng yêu cầu quá nhiều mục, quá nhiều trường hoặc liên tục gửi batch lớn.

Thiết kế giới hạn nhiều tầng:

| Tầng | Biện pháp | Mục đích |
|---|---|---|
| Request | maxItems, maxBytes, schema validation | Không nhận payload quá lớn |
| Authentication | principal, tenant, scopes | Chỉ người hợp lệ được truy cập |
| Authorization | kiểm tra từng object | Không lộ dữ liệu chéo |
| Concurrency | semaphore/bulkhead | Giới hạn số batch đang chạy |
| Rate | quota theo caller/tenant | Chặn request amplification |
| DB | số tham số IN, query plan, index | Tránh truy vấn nặng |
| Cache | TTL, single-flight, size limit | Giảm miss storm |
| Output | maxResponseBytes, pagination/streaming | Tránh giữ response khổng lồ |
| Timeout | deadline toàn request | Không giữ worker quá lâu |
| Observability | batch size, p99, rejected count | Phát hiện lạm dụng và hỏng hiệu năng |

Nếu dữ liệu lấy từ nhiều tenant, không nên để một tenant chiếm toàn bộ pool của backend qua các batch kích thước lớn. Quota và công bằng tài nguyên quan trọng không kém việc giảm số request.

## 26. Tình huống 1: danh sách sản phẩm của thương mại điện tử

**Bối cảnh:** Client hiển thị trang 40 sản phẩm, mỗi sản phẩm cần tên, ảnh, giá hiển thị và trạng thái còn hàng.

**Thiết kế chưa tốt:**

~~~text
GET /products?page=1       -> 1 request
40 × GET /product/{id}     -> 40 requests
40 × GET /prices/{id}      -> 40 requests
40 × GET /stocks/{id}      -> 40 requests

Tổng: 121 request phía client
~~~

Một phương án:
1. Product list endpoint trả **summary** có trường catalog cần cho danh sách.
2. Price Service hỗ trợ **batchGet** theo product IDs, có giới hạn.
3. Inventory Service hỗ trợ **batch availability** theo SKU.
4. BFF gộp dữ liệu; cache ảnh/catalog theo TTL phù hợp.
5. List có pagination/cursor, response không chứa lịch sử giá và metadata không dùng.
6. Client thực hiện một request theo trang, không tự gọi thêm từng item.
7. Phân quyền và chính sách giá theo khách hàng/tenant được áp ở đúng service.
8. Đo số RPC nội bộ, bytes, p95, p99, CPU, cache hit và độ mới dữ liệu.

**Đánh đổi:** số round trip giảm, nhưng BFF phải chờ nhiều nguồn; Price có thể áp chính sách theo nhóm khách hàng, Stock biến động nhanh và có thể khác thời điểm. UI phải thể hiện thông tin chưa xác nhận nếu một nguồn lỗi.

### 26.1. Tối ưu thêm với read model

Nếu trang sản phẩm có traffic rất cao và chấp nhận dữ liệu tồn kho chỉ mang tính gợi ý, có thể dựng ProductListingProjection từ sự kiện Catalog, Price và Inventory. Lúc checkout vẫn phải xác minh giá/quyền/tồn kho theo hợp đồng giao dịch.

Không dùng thông tin projection đã stale để tự động trừ kho hay tính phí mà không có bước đảm bảo nghiệp vụ.

## 27. Tình huống 2: trang quản trị đơn hàng có fan-out nhiều tầng

Một operator mở danh sách 100 đơn. Gateway gọi Orders; Orders gọi Customer cho từng đơn; BFF lại gọi Payment cho từng đơn. Với mỗi lời gọi ở tầng trên có thể có nhiều lời gọi tầng dưới, tạo amplification.

**Giải pháp theo tầng:**
- Orders trả OrderSummary hàng loạt với pagination và projection DB.
- Customer có batch profile lookup theo các customerId distinct và phạm vi được phép.
- Payment có batch status lookup hoặc projection thanh toán theo đơn.
- BFF giới hạn concurrency giữa nhóm nguồn, không làm N+1.
- Chỉ lấy order detail khi operator mở một đơn cụ thể.
- Cache danh mục ít đổi, không cache mù trạng thái thanh toán quan trọng.
- Theo dõi queue, DB connection và downstream timeout khi 100 operator cùng xem trang.

**Một cách đo:** đếm RPC nội bộ **trên mỗi lần mở trang**, không chỉ đếm request từ browser. Nếu trang từ 301 request client giảm xuống 1, nhưng BFF vẫn tạo 300 RPC, lợi ích network ngoài có thể có nhưng bottleneck phía server chưa được giải quyết.

## 28. Tình huống 3: service mesh nhiều hop

Giả sử mỗi lời gọi microservice đi qua sidecar proxy, áp mTLS và telemetry. Một truy vấn phải qua năm service nối tiếp, mỗi service gọi thêm hai nguồn khác.

Service mesh có ích cho identity, mTLS, routing và observability, nhưng **không làm mất các phụ thuộc nối tiếp**. Những lời gọi không cần thiết vẫn gây:
- Thêm hop và queue ở proxy.
- Thêm header/trace/telemetry.
- Thêm điểm timeout, retry và circuit breaker.
- Tăng fan-out theo số user cùng lúc.

**Không đề xuất tắt mTLS hoặc xác thực để lấy vài mili giây.** Thay vào đó đo trace, gộp những lookup lặp, lựa chọn read model/batch, giữ deadline và tối ưu cấu hình transport trong ranh giới bảo mật đã được chấp nhận.

Nếu request routing qua nhiều gateway do thiết kế quá phân tầng, xem lại đường đi của request nhưng giữ nguyên các kiểm soát bắt buộc.

## 29. Tình huống 4: mobile network và API chậm

Trên mạng di động, RTT có thể biến động lớn. Một màn hình phải gọi 30 lần nối tiếp thường nhạy với packet loss, chuyển mạng và sự kiện reconnect hơn một response tổng hợp có kích thước vừa phải.

Các biện pháp:
- BFF theo màn hình: một response đủ dữ liệu để render lần đầu.
- Trả trước phần chính, tải phần ít quan trọng sau nếu UX cho phép.
- Cache có ETag/TTL phù hợp; không tải lại data bất biến.
- Hạn dữ liệu ảnh, dùng kích thước ảnh tương ứng thiết bị, lazy load.
- Batch các ID cần thiết và tối ưu pagination.
- Dùng connection reuse, HTTP/2/HTTP/3 khi client và server hỗ trợ.
- Đo **time to useful content** và p95 trải nghiệm thực tế, không chỉ latency API nội bộ.

Đừng gộp mọi màn hình vào một payload 20 MB; over-fetching có thể làm người dùng mobile chịu chi phí dữ liệu và chờ lâu hơn dù request count thấp.

## 30. Kiểm thử hiệu năng: so trước và sau bằng cùng workload

Một phép thử có ý nghĩa nên so:

- Cùng số record hiển thị và cùng dữ liệu thực tế.
- Cùng tỷ lệ cache warm/cold hoặc báo rõ từng kịch bản.
- Cùng concurrency, network profile và cấu hình downstream.
- Có cả tốc độ bình thường và đợt burst.
- Có tính đến payload size và chi phí serialize.
- Có cả lỗi dependency, timeout và retry.
- Có đo query count, RPC count, DB pool wait và p95/p99.
- Có baseline và ngưỡng chấp nhận đã thống nhất.

Ví dụ bảng thí nghiệm giả định:

| Chỉ số | Trước cải tiến | Sau batch + BFF | Điều cần xem xét |
|---|---:|---:|---|
| Request từ browser/trang | 91 | 1 | Giảm round trip phía client |
| RPC nội bộ/trang | 90 | 3 | Giảm fan-out |
| SQL query/trang | 95 | 8 | Batch DB hiệu quả hơn |
| p95 trang | 1.600 ms | 380 ms | Cải thiện đáng kể |
| Response size | 70 KB | 115 KB | Payload tăng nhưng còn hợp lý |
| p99 DB latency | 120 ms | 140 ms | Phải kiểm tra áp lực thêm |
| Lỗi partial/trang | Không rõ | Được đo riêng | Quan sát minh bạch hơn |

Các con số minh họa; không được dùng làm cam kết thực tế. Nếu batch cải thiện p50 nhưng p99 DB xấu mạnh hoặc rate limit bắt đầu từ chối hàng loạt, thiết kế có thể cần giới hạn batch/concurrency khác.

### 30.1. Phân biệt cold và warm cache

Một phép thử sau tối ưu với cache 100% warm so với baseline cold không công bằng. Nên có ít nhất:
- Cache cold, dữ liệu đa dạng.
- Cache warm, nhiều key lặp.
- Cache invalidation và stampede khi TTL hết.
- Một dependency thất bại hoặc chậm.
- Peak concurrency trong giới hạn production.

Phải xem cả CPU/RAM/GC của BFF vì gộp response có thể tăng cấp phát bộ nhớ.

## 31. Unit, contract và integration tests cho batch API

### 31.1. Unit test

- Input rỗng, null, trùng key, key không hợp lệ và vượt maxItems.
- Dedupe đúng mà vẫn giữ số item UI cần.
- Kết quả trả khác thứ tự input vẫn được map đúng.
- Missing key không bị diễn giải sai thành số lượng 0.
- Quy tắc tính giá/đơn vị tiền không đổi khi lấy bulk.
- Timeout và fallback không tạo trạng thái “thành công” giả.
- Lỗi từng phần tử được biểu diễn ổn định.
- Mỗi object được kiểm tra quyền theo user/tenant.

### 31.2. Contract test

- API cũ và mới có semantics nhất quán đối với cùng fixture.
- Field status, currency, amountMinor giữ cùng ý nghĩa.
- Tên endpoint, JSON schema, mã lỗi, maxItems và ordering được công bố.
- Old client còn đọc được format theo chính sách hỗ trợ.
- Batch response không tiết lộ dữ liệu mà single-item API từng từ chối.
- Nếu gộp nhiều nguồn, consistency/staleness được mô tả đúng.

### 31.3. Integration test

- Dùng serializer, HTTP client, auth, database và service mock/realistic.
- Gửi batch 1, 10, 100 và 101 item để kiểm giới hạn.
- Dùng fixture N items và assert số SQL query/RPC thực không tăng tuyến tính một cách bất ngờ.
- Thử lỗi một item, lỗi toàn downstream, timeout, retry và circuit breaker.
- Thử user tenant A yêu cầu ID tenant B phải bị chặn đúng.
- Thử thay đổi dữ liệu khi request đang xử lý, đánh giá consistency.
- Đo body size, memory, GC và thời gian serialize ở kích thước gần ngưỡng.

Nếu endpoint mới trả đúng giá trị nhưng vẫn gọi N lần getOne nội bộ, test chỉ so kết quả JSON sẽ không phát hiện; cần **đếm calls và queries** như một thuộc tính phi chức năng.

## 32. Kiểm thử độ tin cậy dưới tải

Giảm lời gọi là một phần của thiết kế chịu lỗi. Cần thử:
1. Một dependency chậm hơn bình thường 10 lần.
2. Một dependency không phản hồi và timeout.
3. Một dependency trả lỗi 429/503 theo đợt.
4. BFF có nhiều request cùng lúc, tổng concurrency tiến sát max.
5. Cache bị xóa hoặc cluster cache không truy cập được.
6. DB chỉ cho số connection hữu hạn khi tăng replica.
7. Payload vượt maxBatchItems hoặc maxResponseBytes.
8. Client hủy request giữa lúc các nhánh đang chạy.
9. Một endpoint gộp trả dữ liệu từ nhiều phiên bản schema.
10. Rolling deployment trộn client và server phiên bản cũ/mới.

**Kỳ vọng:** hệ thống từ chối quá tải có kiểm soát, không chuyển một request thành hàng trăm retry, không giữ connection vô hạn và không báo sai kết quả nghiệp vụ.

Với đọc dữ liệu tùy chọn, graceful degradation có thể chấp nhận. Với lệnh ghi tài chính hoặc tồn kho, thất bại phải được thể hiện rõ và có cơ chế idempotency/đối soát.

## 33. Rollout: thay API vụn bằng batch mà không phá client cũ

Một lộ trình chuyển đổi thường gồm:

### Giai đoạn 1 — Đo và chốt hợp đồng

- Đo request/RPC/query count, latency và tải.
- Xác định trường nào cần trong mỗi use case.
- Ghi contract của API cũ và API mới, maxItems, lỗi partial, auth và staleness.
- Kiểm tra những client nào đang phụ thuộc endpoint đơn lẻ.

### Giai đoạn 2 — Thêm batch API ở service sở hữu dữ liệu

- Giữ endpoint cũ trong thời gian chuyển đổi.
- Triển khai bulk query thật sự ở DB/cache.
- Thêm giới hạn request bytes/items và phân quyền mỗi item.
- Test positive/negative cases và hiệu năng.

### Giai đoạn 3 — Chuyển BFF hoặc client theo cohort

- Chọn một trang/tenant nhỏ, đo kết quả so với baseline.
- Phát phiên bản client/BFF dùng batch; giữ đường cũ nếu cần rollback.
- Giới hạn concurrency và retry budget cho các dependency.
- Theo dõi p95/p99, query count, payload bytes, DB pool và lỗi từng phần.

### Giai đoạn 4 — Mở rộng và khôi phục khi cần

- Tăng lưu lượng nếu guardrail đạt yêu cầu.
- Nếu p99 DB xấu hoặc lỗi nghiệp vụ tăng, dừng rollout và chuyển traffic trở về đường ổn định.
- Không xóa endpoint cũ khi còn client chưa nâng hoặc data flow chưa được kiểm chứng.

### Giai đoạn 5 — Loại bỏ legacy có kế hoạch

- Công bố chính sách deprecation và thời điểm kết thúc hỗ trợ.
- Đo traffic thực đến endpoint cũ.
- Dọn client code và test không còn dùng endpoint vụn.
- Giữ metric hiệu năng làm bằng chứng cải tiến dài hạn.

Không coi batch response là giao dịch nguyên tử nếu các phần tử vốn lấy từ nhiều hệ thống độc lập. Nếu contract thay đổi semantics, phải có version hoặc migration tương ứng.

## 34. Decision matrix: nên dùng giải pháp nào?

| Triệu chứng | Hướng thử đầu tiên | Đánh đổi chính |
|---|---|---|
| N × GET cùng resource | BatchGet/multi-get | Giới hạn kích thước và lỗi từng item |
| 50 RPC để dựng một màn hình | BFF/API composition | Fan-out chuyển sang BFF |
| N+1 SQL trong một API | Projection/batch DB query | Query plan, join explosion |
| Nhiều màn hình cần cùng dữ liệu gộp | Materialized read model | Eventual consistency và rebuild |
| Cùng key được đọc lặp lại | Cache có TTL/invalidation | Staleness và cache stampede |
| Nhiều nhánh độc lập nối tiếp | Parallelism có giới hạn | Downstream concurrency, tail latency |
| Nhiều request HTTP nhỏ | Keep-alive/HTTP2/gRPC phù hợp | Không chữa N+1 nghiệp vụ |
| Danh sách quá lớn | Pagination/streaming | Nhiều lượt tải có kiểm soát |
| Export hàng triệu record | Async job + object storage | Quản lý job, quyền và retry |
| Payload lớn hơn cần thiết | Summary DTO/field selection | Nhiều view/schema cần quản lý |
| Dependency optional hay chậm | Fallback, cache, deadline | Tính đầy đủ/độ mới response |
| Mỗi trang gọi dữ liệu nhạy cảm chéo service | BFF + authz từng object | Tăng trách nhiệm bảo mật tầng tổng hợp |

Một hệ thống có thể cần nhiều biện pháp phối hợp; **không có một kỹ thuật tối ưu thay thế việc xác định critical path và ranh giới dữ liệu**.

## 35. Phân tích sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Gộp mọi thứ vào một endpoint khổng lồ | Response lớn, khó cache, dữ liệu lộ quá phạm vi | DTO theo use case, chọn trường, pagination |
| Chỉ giảm số request browser | BFF vẫn N+1 phía trong | Đếm cả internal RPC và SQL |
| Đưa toàn bộ N call chạy song song | Downstream quá tải và p99 tăng | Batch và bounded concurrency |
| HTTP/2 được xem là thuốc chữa N+1 | Logic fan-out vẫn còn | Đổi API granularity |
| Batch endpoint tự lặp getOne | Không giảm workload phía sau | Bulk DB/cache query thực sự |
| Không giới hạn batch size | DoS qua body và truy vấn khổng lồ | maxItems, bytes, deadline và quota |
| Cache dữ liệu theo ID nhưng thiếu tenant | Rò dữ liệu chéo người dùng | Key và quyền truy cập theo phạm vi |
| Gộp dữ liệu mà không đánh dấu lỗi partial | Client tưởng mọi phần đều đáng tin | Status theo thành phần hoặc item |
| Tăng retry ở nhiều tầng | Request amplification | Retry budget, backoff, trách nhiệm rõ |
| Bỏ qua serializer và response size | GC, CPU, mạng tăng | Đo bytes, RSS, p99 |
| Bulk write không idempotent | Retry tạo thao tác lặp | Idempotency key, result per item |
| Đọc trực tiếp DB service khác | Tight coupling và quyền mở rộng | Contract API/read model |
| Materialized view dùng làm nguồn giao dịch tức thời | Sai do eventual consistency | Xác minh tại owner khi commit |
| Không đo SQL N+1 | Một endpoint vẫn chậm | Query-count tests và tracing |
| Không xử lý dữ liệu thiếu/không có quyền | Tính sai hoặc lộ object | Trạng thái kết quả phân biệt |
| Chỉ benchmark cache warm | Đánh giá quá lạc quan | Cold/warm/failure scenarios |
| Không có rollback cho API mới | Lỗi production khó phục hồi | Progressive rollout, giữ đường cũ có thời hạn |

## 36. Bài tập thực hành

**Bài A — nhận diện N+1:** Một trang hiển thị 60 đơn. Endpoint /orders trả danh sách; client gọi thêm /payments/order/{id} và /customers/{id} cho mỗi đơn. Hãy tính tổng request client, vẽ critical path nếu gọi tuần tự, và đề xuất batch API cũng như response summary hợp lý.

**Bài B — thiết kế batch:** Inventory API nhận tối đa 100 SKU. Hãy định nghĩa JSON request/response, semantics khi có SKU không tồn tại, SKU bị cấm xem, lỗi DB và input trùng. Nêu hành vi nếu caller gửi 101 SKU.

**Bài C — idempotency:** Một endpoint bulk cập nhật 50 sản phẩm; 45 thành công, 5 timeout. Caller retry cả batch. Hãy thiết kế idempotency key, lưu trạng thái xử lý, response từng item và cách không cập nhật trùng.

**Bài D — fan-out:** BFF có 8 dependency, mỗi dependency p95 khoảng 80 ms. Hãy mô tả tại sao gọi song song có thể nhanh hơn nối tiếp nhưng khiến tail latency và concurrency downstream xấu hơn; chọn deadline và bulkhead.

**Bài E — GraphQL:** Một query lấy 100 articles và author của mỗi article. Thiết kế DataLoader batch authors, cache per-request, mapping kết quả, auth theo tenant và giới hạn complexity.

**Bài F — CQRS:** Một trang quản trị phải gộp Order, Payment và Delivery, đọc 10.000 lần/phút và chấp nhận dữ liệu trễ tối đa vài giây. Hãy thiết kế projection, event version, idempotency, replay và cách quan sát lag. Chỉ rõ bước nào vẫn phải đọc trực tiếp nguồn.

**Bài G — caching:** Một cache ProductSummary vừa hết TTL, 2.000 người cùng mở trang. Xác định nguy cơ cache stampede và đề xuất single-flight, TTL jitter, giới hạn concurrency và stale-while-revalidate phù hợp.

**Bài H — mạng mobile:** So sánh phương án 20 request nhỏ với một response tổng hợp 3 MB dưới mạng RTT cao. Phân tích over-fetching và đề xuất API theo màn hình, lazy loading và compression có điều kiện.

**Bài I — đo lường:** Hãy định nghĩa trace, metric và benchmark trước/sau cho hành vi N+1. Chỉ số nào chứng minh nội bộ giảm RPC, chỉ số nào đảm bảo DB không bị nghẽn, chỉ số nào phản ánh trải nghiệm người dùng?

**Bài J — rollout:** Thiết kế quá trình chuyển từ 30 × GET /inventory/{sku} sang POST /availability:batchGet. Ghi các bước feature flag, canary, guardrail, rollback, deprecation và contract test khi consumer/client cũ vẫn còn.

## 37. Checklist áp dụng trong dự án

Khi phát hiện một API có độ trễ cao hoặc mạng bị gọi quá nhiều, có thể đi theo trình tự:

1. **Xác định use case thật:** màn hình/tác vụ cần dữ liệu nào, cần tươi bao lâu?
2. **Đo request graph:** số request ngoài, số RPC trong, SQL query count, bytes và critical path.
3. **Tìm N+1:** cùng một lời gọi lặp theo từng phần tử ở HTTP, RPC, resolver hoặc ORM.
4. **Loại bỏ dữ liệu không cần:** summary DTO, field selection và pagination.
5. **Batch những lookup độc lập:** xác định maxItems, error per item, auth và ordering.
6. **Chọn composition/read model:** theo lưu lượng, nhu cầu nhất quán và trách nhiệm dữ liệu.
7. **Giữ concurrency hữu hạn:** deadline, pool, semaphore, backpressure và retry budget.
8. **Dùng cache có hợp đồng:** key, tenant, TTL, invalidation và fail behavior.
9. **Kiểm thử lỗi/biên:** missing data, partial, duplicate, overload, cache miss, downstream timeout.
10. **Rollout có quan sát:** so cùng workload ở p95/p99, error, DB saturation và chi phí.
11. **Giữ đường phục hồi:** client/API cũ hoặc adapter còn hoạt động trong thời kỳ chuyển đổi.
12. **Dọn thiết kế cũ:** deprecate sau khi chứng minh không còn người dùng và không giảm tính đúng.

## 38. Ghi nhớ

- **Một request có chi phí**, ngay cả khi kết nối HTTP/TLS đã được tái sử dụng; nhiều lời gọi nối tiếp thường làm tăng latency trên critical path.
- **N+1 tồn tại cả ở HTTP/RPC lẫn database/GraphQL resolver**. Cần đo request, RPC và query count thay vì chỉ nhìn endpoint ngoài.
- **BatchGet và bulk query** giảm số round trip của các lookup cùng loại; phải có maxItems, validation, kết quả từng key, phân quyền và giới hạn tài nguyên.
- **BFF/API composition** có thể giảm chattiness phía client nhưng phải tránh chuyển N+1 vào server hoặc làm tăng fan-out không kiểm soát.
- **Materialized read model/CQRS** phù hợp luồng đọc gộp lặp lại với điều kiện chấp nhận eventual consistency và có cơ chế reconciliation.
- **Parallelism giảm waterfall nhưng không giảm số lời gọi**; fan-out lớn có thể làm tăng p99 và quá tải downstream.
- **Cache, field selection, pagination và compression** xử lý những nguyên nhân khác nhau; tối ưu số request không được đánh đổi thành payload quá lớn hoặc dữ liệu stale nguy hiểm.
- **Timeout, retry budget, idempotency và partial failure** quyết định sự an toàn khi API gộp hoặc batch gặp lỗi.
- **Giữ ranh giới sở hữu dữ liệu và object-level authorization** khi tổng hợp nhiều nguồn hoặc nhiều ID.
- **Chỉ kết luận cải tiến sau khi benchmark có cùng workload** và quan sát latency, error, bytes, RPC/SQL count, saturation và trải nghiệm người dùng.

Thiết kế API tốt không đồng nghĩa một endpoint cho tất cả, cũng không phải một endpoint cho mỗi trường dữ liệu. Đó là thiết kế **mỗi cuộc trao đổi mạng phục vụ một nhu cầu đủ rõ, chuyển đúng lượng dữ liệu, có giới hạn tải và giữ được hợp đồng khi hệ thống lớn lên**. Khi đo được fan-out và chọn được ranh giới hợp lý, hệ thống vừa phản hồi nhanh hơn vừa giảm áp lực và phạm vi lỗi cho những dịch vụ phía sau.

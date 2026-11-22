# Thay giao tiếp nội bộ bằng hợp đồng và cơ chế phục hồi trong Microservices

Khi một hệ thống chuyển từ kiến trúc đơn khối sang microservices, hoặc khi các thành phần nội bộ được tách thành những dịch vụ triển khai độc lập, cách các thành phần gọi nhau cần thay đổi. Một lời gọi hàm trong cùng process có thể được thực hiện ngay lập tức và chia sẻ bộ nhớ; một lời gọi qua mạng có thể chậm, mất kết nối, bị thực hiện nhiều lần, trả kết quả không rõ ràng hoặc gặp phiên bản service không tương thích.

**Thay giao tiếp nội bộ bằng hợp đồng và cơ chế phục hồi** là quá trình chuyển các phụ thuộc ngầm giữa module/service thành những hợp đồng giao tiếp được định nghĩa rõ, có versioning, validation, quyền truy cập, timeout, retry policy, idempotency, quan sát và hành vi khi dependency gặp lỗi.

Mục tiêu không chỉ là đổi một lời gọi nội bộ thành HTTP hoặc message. Mục tiêu là làm cho mỗi thành phần có thể phát triển và triển khai độc lập trong khi vẫn giữ đúng nghiệp vụ, giới hạn ảnh hưởng của lỗi và cung cấp hành vi có thể dự đoán cho consumer.

Bài học tập trung vào:

- Xác định ranh giới giao tiếp và trách nhiệm của provider/consumer.
- Chọn API đồng bộ hay event/message bất đồng bộ.
- Thiết kế contract, schema, versioning và compatibility.
- Xử lý timeout, retry, circuit breaker, bulkhead và fallback.
- Bảo đảm idempotency, ordering và consistency.
- Chuyển đổi dần từ giao tiếp cũ sang contract mới.
- Kiểm thử lỗi mạng, lỗi dependency và các phiên bản triển khai khác nhau.
- Theo dõi latency, lỗi, saturation và chất lượng phục hồi.

## 1. Vì sao giao tiếp nội bộ cần được thay đổi?

Trong một ứng dụng đơn khối, các module có thể gọi trực tiếp nhau:

    OrderController
        -> OrderService
            -> CustomerRepository
            -> InventoryService
            -> PaymentService

Các lời gọi thường chạy trong cùng process hoặc cùng database. Một module có thể truy cập class, object, transaction và cấu trúc dữ liệu nội bộ của module khác. Cách này đơn giản lúc đầu, nhưng tạo coupling khi các thành phần cần được tách thành service độc lập.

Sau khi tách:

    Order Service
        -> Customer Profile API
        -> Inventory API
        -> Payment API
        -> Event Broker

Các phụ thuộc trở thành network boundaries. Một lời gọi có thể:

- Không kết nối được do DNS, routing, TLS hoặc service restart.
- Chờ quá lâu vì provider bị nghẽn.
- Timeout sau khi provider đã thực hiện side effect nhưng response bị mất.
- Trả 429/503 vì quota hoặc overload.
- Trả schema mới mà consumer cũ không hiểu.
- Được retry và thực hiện nhiều lần.
- Đến sai thứ tự khi đi qua nhiều queue/partition.
- Thành công ở một service nhưng thất bại ở service tiếp theo.

Nếu chỉ thay direct method call bằng HTTP call mà không thay đổi cách xử lý lỗi, hệ thống có thể trở nên mong manh hơn. Mỗi network dependency bổ sung một failure mode và một phần latency.

## 2. Phân biệt implementation detail với contract

Một service không nên yêu cầu consumer biết cách provider lưu dữ liệu hoặc tổ chức code nội bộ.

**Implementation detail** có thể thay đổi mà không báo trước: tên bảng, ORM entity, package Java, class nội bộ, cache key, cấu trúc thread pool, index hoặc cách provider phân vùng dữ liệu.

**Contract** là phần provider cam kết với consumer: endpoint hoặc event type, schema, semantics, validation, authorization, lỗi có thể trả, timeout expectation, consistency, ordering và các quy tắc tương thích.

Ví dụ không nên để Order Service truy vấn trực tiếp:

    SELECT id, name, phone
      FROM customer_profiles
     WHERE customer_id = ?

Một hợp đồng rõ hơn:

    GET /customers/{customerId}/checkout-profile

Response có thể chứa những trường consumer được phép sử dụng:

    {
      "customerId": "customer-123",
      "displayName": "Nguyen Van A",
      "phone": "+84...",
      "profileVersion": 42
    }

Ví dụ JSON trên chỉ minh họa payload; không phải yêu cầu lưu dữ liệu hoặc định danh thật. Consumer phụ thuộc vào semantics của contract, không phụ thuộc bảng customer_profiles.

**Contract phải thể hiện ý nghĩa nghiệp vụ, không chỉ kiểu dữ liệu.** Ví dụ field status có giá trị ACTIVE có nghĩa gì? phone có thể null không? profileVersion tăng khi thay đổi nào? response có phải dữ liệu mới nhất hay một projection có thể trễ?

## 3. Xác định provider, consumer và trách nhiệm

Trong giao tiếp service-to-service:

- **Provider** sở hữu dữ liệu/quy tắc và cung cấp operation hoặc event.
- **Consumer** sử dụng contract và chịu trách nhiệm xử lý kết quả, lỗi và version compatibility.
- **Gateway/adapter** có thể xác thực, định tuyến hoặc chuyển đổi giao thức, nhưng không nên âm thầm sở hữu logic nghiệp vụ của cả hai bên.
- **Broker** vận chuyển message; nó không thay thế trách nhiệm của producer/consumer đối với schema, retry, idempotency và business semantics.

Một ma trận ownership:

| Nội dung | Provider chịu trách nhiệm | Consumer chịu trách nhiệm |
| --- | --- | --- |
| Schema/semantics | Công bố và giữ tương thích | Deserialize và hiểu đúng |
| Authentication | Xác minh caller | Gửi credential hợp lệ |
| Authorization | Kiểm tra quyền trên tài nguyên | Không giả định quyền từ ID |
| Validation | Kiểm tra invariant của domain | Gửi dữ liệu đúng contract |
| Timeout | Công bố đặc tính/giới hạn | Đặt deadline phù hợp |
| Retry | Trả lỗi có semantics rõ | Retry có giới hạn và an toàn |
| Idempotency | Hỗ trợ key nếu operation cần | Gửi và giữ key ổn định |
| Observability | Trace/metrics phía provider | Trace context và outcome phía consumer |
| Versioning | Quản lý thay đổi contract | Nâng cấp consumer theo compatibility |
| Data consistency | Công bố mức nhất quán | Chấp nhận/đối soát đúng mức |

Không để consumer bypass provider bằng cách đọc database trực tiếp khi gặp API chậm. Điều đó tạo một contract thứ hai không được quản lý.

## 4. Chọn giao tiếp đồng bộ hay bất đồng bộ

Không phải mọi tương tác đều nên dùng REST hoặc message broker.

### 4.1. API đồng bộ

Dùng khi caller cần câu trả lời ngay để tiếp tục quyết định:

- Kiểm tra địa chỉ có thể sử dụng lúc checkout.
- Lấy báo giá hiện tại.
- Xác minh quyền hoặc trạng thái cần thiết.
- Yêu cầu provider thực hiện một command và nhận kết quả theo contract.

Ưu điểm: luồng điều khiển rõ, response trực tiếp, dễ hiểu với thao tác ngắn.

Đánh đổi: caller phụ thuộc availability và latency của provider; lỗi có thể lan truyền; chuỗi nhiều API call làm tăng tail latency.

### 4.2. Event/message bất đồng bộ

Dùng khi producer thông báo một sự kiện đã xảy ra hoặc yêu cầu xử lý có thể hoàn thành sau:

- OrderPlaced.
- PaymentAuthorized.
- InventoryReserved.
- ReportRequested.
- CustomerProfileChanged.
- EmailDeliveryRequested.

Ưu điểm: giảm phụ thuộc trực tiếp về thời điểm hoạt động, hấp thụ burst bằng queue và cho phép consumer scale độc lập.

Đánh đổi: eventual consistency, duplicate delivery, ordering, backlog, schema evolution, DLQ và khả năng quan sát workflow phức tạp hơn.

### 4.3. Command và event không giống nhau

**Command** yêu cầu một hành động: ReserveInventory, AuthorizePayment.

**Event** thông báo điều đã xảy ra: InventoryReserved, PaymentAuthorized.

Command có thể bị từ chối; event mô tả sự kiện đã được xác nhận theo semantics của producer. Đặt tên và thiết kế payload lẫn lộn có thể khiến consumer hiểu nhầm một yêu cầu chưa hoàn thành thành kết quả thành công.

| Nhu cầu | Cơ chế thường phù hợp |
| --- | --- |
| Cần kết quả ngay | Request/response API |
| Thông báo sự kiện đã xảy ra | Event |
| Xử lý lâu, có thể chờ | Durable queue/job |
| Broadcast thay đổi cho nhiều consumer | Event topic |
| Đảm bảo một thao tác nghiệp vụ do owner thực hiện | Command API hoặc command message có trạng thái |
| Query đọc lớn, chấp nhận trễ | Read model/projection |

## 5. Thiết kế contract API

Một API contract cần định nghĩa tối thiểu:

1. Method, path và operation semantics.
2. Request/response schema và content type.
3. Required/optional fields, constraints và default behavior.
4. Authentication, authorization và tenant context.
5. HTTP status/error model.
6. Idempotency và concurrency behavior.
7. Pagination/filter/sort nếu có.
8. Timeout/deadline expectation.
9. Rate/concurrency limit.
10. Consistency và freshness.
11. Deprecation/versioning policy.
12. Observability và correlation/trace context.

Ví dụ contract cho lệnh tạo reservation:

    POST /inventory/reservations

    Request:
      {
        "orderId": "order-123",
        "tenantId": "tenant-7",
        "items": [
          { "sku": "sku-1", "quantity": 2 }
        ],
        "idempotencyKey": "stable-operation-key"
      }

    Success:
      201 Created
      {
        "reservationId": "reservation-456",
        "status": "RESERVED",
        "expiresAt": "..."
      }

    Business rejection:
      409 Conflict
      {
        "code": "INSUFFICIENT_STOCK",
        "message": "Requested quantity is unavailable"
      }

Payload chỉ là ví dụ. Không nên để client tự quyết định tenantId nếu danh tính đã xác thực cung cấp tenant context đáng tin cậy. Provider phải kiểm tra caller được phép thao tác với order/tenant tương ứng.

### 5.1. Error model ổn định

Không trả stack trace hoặc tên class Java nội bộ cho consumer. Dùng error code có semantics ổn định:

| Status | Ý nghĩa thường gặp | Hành vi consumer |
| --- | --- | --- |
| 400 | Request không hợp lệ | Sửa request, không retry y nguyên |
| 401 | Chưa xác thực | Làm mới credential theo policy |
| 403 | Không có quyền | Không retry tự động |
| 404 | Tài nguyên không tồn tại hoặc không được tiết lộ | Xử lý theo nghiệp vụ |
| 409 | Xung đột trạng thái/version | Đọc lại hoặc xử lý conflict |
| 422 | Vi phạm quy tắc nghiệp vụ | Không retry nếu input không đổi |
| 429 | Vượt quota/rate limit | Backoff, tôn trọng Retry-After |
| 500 | Lỗi provider không xác định | Retry có giới hạn nếu operation an toàn |
| 502/503/504 | Gateway/dependency/availability issue | Retry có điều kiện và deadline |

Không dùng status code một cách máy móc. Contract phải định nghĩa mã lỗi và semantics cụ thể, vì 409 có thể là xung đột version, duplicate idempotency key hoặc một trạng thái domain khác nhau.

### 5.2. Không rò rỉ implementation detail

Một error response an toàn có thể có:

    {
      "code": "INVENTORY_UNAVAILABLE",
      "message": "Inventory could not be reserved",
      "correlationId": "trace-reference"
    }

Không trả SQL, host nội bộ, credential, stack trace hoặc dữ liệu của tenant khác. Correlation ID nên giúp tìm log/trace nhưng không được dùng làm bí mật xác thực.

## 6. Versioning và compatibility

Consumer và provider không được triển khai đồng thời trong mọi hệ thống. Có lúc provider v2 chạy trong khi một số consumer vẫn ở v1.

### 6.1. Expand-contract

Một quy trình an toàn:

1. Thêm field mới theo hướng optional hoặc có default tương thích.
2. Provider phát hành schema/API hỗ trợ cả consumer cũ và mới.
3. Consumer nâng cấp để đọc field mới.
4. Chuyển dần producer sang semantics mới.
5. Theo dõi usage của field cũ.
6. Chỉ loại bỏ field cũ sau thời gian deprecation và xác nhận không còn consumer.

Tránh đổi tên hoặc đổi kiểu field bắt buộc ngay trong một lần deploy nếu có consumer cũ.

### 6.2. Backward, forward và full compatibility

- **Backward compatibility:** consumer mới đọc được dữ liệu/contract cũ.
- **Forward compatibility:** consumer cũ vẫn xử lý được dữ liệu mới trong phạm vi thiết kế.
- **Full compatibility:** hai chiều đáp ứng theo chính sách schema registry/công nghệ.

Thêm một field optional thường dễ tương thích hơn xóa field hoặc đổi kiểu. Tuy vậy enum mới, thay semantics của field cũ hoặc đổi default có thể phá consumer dù schema vẫn parse được.

### 6.3. URL version hay schema version?

API có thể dùng path version như /v1 và /v2, hoặc quản lý thay đổi compatible trong cùng major version. Event thường cần schema version/registry và chính sách compatibility. Không cần tạo version mới cho mọi field; nhưng thay đổi breaking phải có lộ trình rõ.

**Version số không tự giải quyết compatibility.** Contract tests và rollout order mới chứng minh các phiên bản có thể hoạt động cùng nhau.

## 7. Contract-first và schema governance

Contract-first nghĩa là định nghĩa interface trước khi triển khai provider/consumer:

- OpenAPI cho HTTP API.
- AsyncAPI hoặc schema registry cho message/event.
- Protobuf/gRPC IDL cho RPC.
- JSON Schema/Avro/Protobuf schema cho payload.
- Error catalog và semantics trong tài liệu API.

Một contract tốt nên được review cùng domain owner, security và consumer đại diện. Cần kiểm tra naming, nullability, units, timezone, identifier, tenant scope, error cases, pagination, ordering và data retention.

Không biến contract thành bản sao của database entity. Một API public không nên lộ hết các cột chỉ vì entity đang có chúng. Payload nên tối thiểu theo use case và có semantics ổn định.

### 7.1. Consumer-driven contract tests

Consumer có thể khai báo kỳ vọng thực tế của mình, ví dụ:

- Field orderId luôn có.
- Reservation status có tập giá trị được hỗ trợ.
- Provider trả 409 khi version không khớp.
- Một response thành công có reservationId hợp lệ.

Provider chạy các contract tests trước release. Cách này giảm rủi ro provider thay đổi mà consumer không biết. Tuy nhiên không thay thế integration tests, security tests và load tests; contract test thường không chứng minh latency hay khả năng chịu lỗi.

## 8. Timeout và deadline: không chờ vô hạn

Một network call cần timeout. Nếu không, thread, connection và request context có thể bị giữ vô hạn, gây cạn tài nguyên.

Có thể phân biệt:

- **Connection timeout:** thời gian thiết lập kết nối.
- **TLS/handshake timeout:** thời gian thương lượng bảo mật.
- **Response/read timeout:** thời gian chờ dữ liệu phản hồi.
- **Request deadline:** tổng thời gian caller cho phép operation hoàn tất, bao gồm các bước con và retry.

Ví dụ request có tổng deadline 800 ms:

    Gateway budget:       800 ms
    Order local work:     100 ms
    Inventory API:        250 ms
    Payment API:          300 ms
    Response reserve:     100 ms
    Safety margin:         50 ms

Đây là phân bổ minh họa. Các budget phải được đo theo p95/p99 và SLO thực. Nếu mỗi service tự đặt timeout 2 giây, tổng chuỗi có thể vượt deadline gateway rất nhiều.

**Propagate deadline** qua downstream khi giao thức hỗ trợ; nếu không, truyền một deadline/correlation context phù hợp và tính thời gian còn lại. Không khởi động lại full timeout cho mỗi bước con.

### 8.1. Timeout không chứng minh operation thất bại

Một trường hợp quan trọng:

    Client gửi AuthorizePayment.
    Provider đã gọi payment gateway và charge thành công.
    Response bị mất trên mạng.
    Caller timeout.

Caller không biết chắc payment đã thành công hay chưa. Nếu retry bằng key mới, có thể charge hai lần.

Đối với command có side effect, trạng thái sau timeout có thể là **UNKNOWN/PENDING**. Dùng idempotency key ổn định, query trạng thái hoặc reconciliation trước khi gửi command mới.

## 9. Retry có giới hạn và có hiểu biết về nghiệp vụ

Retry giúp vượt qua lỗi tạm thời, nhưng retry sai có thể khuếch đại overload hoặc lặp side effect.

### 9.1. Chỉ retry khi phù hợp

Thường có thể retry có điều kiện:

- Lỗi kết nối trước khi gửi request.
- 503/504 tạm thời nếu operation an toàn.
- 429 theo Retry-After.
- Lỗi transient được contract phân loại rõ.

Không retry mù:

- 400/401/403/422.
- Vi phạm nghiệp vụ không thay đổi khi gửi lại.
- Timeout của command không idempotent.
- 409 cần đọc lại version/trạng thái.
- Lỗi do quota toàn hệ thống khi chưa có capacity.

### 9.2. Exponential backoff và jitter

Một công thức minh họa:

    delay = random(0, min(cap, base * 2^attempt))

Ví dụ base 100 ms, cap 2 giây, số lần retry tối đa 3. Jitter phân tán thời điểm retry, tránh hàng nghìn client cùng gọi lại một lúc.

Không retry vô hạn. Mỗi request có deadline, retry budget và số lần tối đa. Retry ở gateway, client, service và broker có thể nhân lên: ba lớp, mỗi lớp ba lần, có thể tạo nhiều request hơn dự tính.

### 9.3. Retry budget

Có thể giới hạn retry theo tỷ lệ so với traffic gốc hoặc theo thời gian. Khi dependency lỗi diện rộng, ngừng retry thêm và chuyển sang fallback/503 hoặc trạng thái pending theo nghiệp vụ.

Retry nên có metric riêng: attempts, exhausted, duplicate, retry delay và kết quả cuối cùng.

## 10. Circuit breaker: ngừng gọi dependency đang lỗi

Circuit breaker theo dõi kết quả lời gọi và chuyển trạng thái:

- **Closed:** cho phép request đi qua, ghi nhận failure/latency.
- **Open:** từ chối nhanh hoặc dùng fallback khi tỷ lệ lỗi vượt điều kiện.
- **Half-open:** cho một số probe giới hạn thử lại; nếu phục hồi thì đóng circuit, nếu còn lỗi thì mở lại.

    Closed
      | failure threshold reached
      v
    Open
      | wait duration elapsed
      v
    Half-open
      | probe success -> Closed
      | probe failure -> Open

Circuit breaker tránh giữ thread chờ một provider đang lỗi và giảm áp lực khi provider hồi phục. Nhưng cấu hình sai có thể:

- Mở circuit do một số lỗi nghiệp vụ không phải dependency failure.
- Đóng/mở liên tục (flapping).
- Tạo burst probe khi provider vừa hồi phục.
- Che giấu lỗi lâu nếu fallback trả kết quả sai.

Chỉ tính các failure phù hợp: network, timeout, 5xx/transient; không coi 400/validation error là lỗi availability của provider. Ngưỡng, sliding window, minimum calls và open duration cần dựa trên traffic và SLO.

**Circuit breaker không phải retry và không phải rate limiter.** Mỗi pattern xử lý một vấn đề khác.

## 11. Bulkhead: giới hạn blast radius

Bulkhead tách tài nguyên theo dependency hoặc nhóm nghiệp vụ để một nhóm lời gọi chậm không chiếm mọi worker.

Ví dụ:

    Order Service
      |
      +--> Inventory executor (max 30 in-flight)
      |
      +--> Payment executor (max 15 in-flight)
      |
      +--> Profile executor (max 20 in-flight)

Nếu Inventory chậm, các worker của Payment vẫn có cơ hội xử lý. Có thể dùng semaphore hoặc thread pool riêng, bounded queue và rejection policy.

Cần lưu ý:

- Semaphore phải được release khi operation thực sự hoàn tất.
- Async task không được trả permit ngay sau khi tạo Future.
- Queue phải có giới hạn; queue vô hạn chỉ chuyển lỗi thành memory pressure.
- Tổng concurrency vẫn phải phù hợp DB/API provider.
- Bulkhead trong một JVM không phải quota toàn cluster.
- Pool quá nhỏ làm throughput thấp; quá lớn có thể làm dependency quá tải.

Bulkhead phải đặt gần tài nguyên cần bảo vệ, không chỉ ở controller.

## 12. Fallback và graceful degradation

Fallback là hành vi thay thế khi dependency không sẵn sàng hoặc kết quả không thể lấy đúng hạn.

Ví dụ phù hợp:

- Recommendation lỗi thì bỏ phần gợi ý, vẫn hiển thị sản phẩm.
- Catalog search lỗi thì dùng cache gần nhất nếu policy cho phép.
- Report service lỗi thì trả trạng thái đang chờ hoặc cho người dùng tải sau.
- Profile display có thể dùng read projection đã đánh dấu freshness nếu use case chấp nhận.

Ví dụ nguy hiểm:

- Payment timeout thì tự đánh dấu thanh toán thất bại hoặc thành công khi chưa xác định.
- Inventory không trả lời thì mặc định còn hàng.
- Authorization lỗi thì cho phép truy cập.
- Dữ liệu giá cũ được dùng cho giao dịch nếu nghiệp vụ yêu cầu giá mới.

Fallback cần có **staleness policy**: dữ liệu cũ bao lâu thì còn dùng được, hiển thị thế nào và use case nào không được phép dùng. Không dùng fallback để che một lỗi làm sai invariant.

## 13. Idempotency cho command có side effect

Một request có thể được gửi nhiều lần do client retry, gateway retry, message redelivery hoặc response mất.

**Idempotent operation** bảo đảm nhiều lần thực hiện cùng một logical command không tạo nhiều tác động nghiệp vụ hơn một lần.

Ví dụ API:

    POST /payments/authorizations
    Idempotency-Key: order-123-payment-attempt-1

Provider có thể lưu:

- Idempotency key.
- Caller/tenant scope.
- Request hash để phát hiện cùng key nhưng payload khác.
- Trạng thái processing/succeeded/failed/unknown.
- Kết quả cuối và external reference.
- Thời gian retention phù hợp.

Nếu nhận lại cùng key và payload, trả kết quả đã biết hoặc trạng thái đang xử lý. Nếu cùng key nhưng payload khác, trả lỗi conflict theo contract.

Không dùng key ngẫu nhiên mới mỗi lần retry. Key phải ổn định cho cùng một logical operation, nhưng khác nhau cho lần thử nghiệp vụ mới được phép.

### 13.1. Exactly-once và giới hạn thực tế

Trong hệ phân tán, thường khó đảm bảo exactly-once side effect xuyên database, broker và API ngoài. Mục tiêu thực tế là:

- Delivery có thể at-least-once.
- Consumer idempotent.
- Event ID ổn định.
- Inbox/outbox hoặc deduplication có transaction boundary rõ.
- External API dùng idempotency nếu hỗ trợ.
- Có reconciliation cho trạng thái không rõ.

Không tuyên bố exactly-once chỉ vì broker có một chế độ producer transaction; business side effect còn nằm ngoài broker.

## 14. Ordering, concurrency và consistency

Nếu các event cùng aggregate cần giữ thứ tự, phải xác định ordering key và phạm vi đảm bảo.

Kafka bảo đảm thứ tự trong một partition; key theo aggregate có thể đưa các event liên quan về cùng partition nếu partitioner được cấu hình phù hợp. Điều đó không bảo đảm thứ tự toàn topic hoặc giữa nhiều topic.

RabbitMQ có ordering semantics phụ thuộc queue, consumer concurrency, redelivery và topology; không giả định nhiều consumer vẫn xử lý xong theo thứ tự gửi.

Các biện pháp:

- Event có aggregate ID và sequence/version.
- Consumer kiểm tra version, phát hiện gap và stale event.
- Partition/queue key theo đơn vị cần ordering.
- Chỉ dùng serial processing khi invariant yêu cầu; nó giảm concurrency.
- Dùng idempotency cho redelivery.
- Có replay và reconciliation khi phát hiện gap.

Eventual consistency cần được phản ánh trong UI và API: có thể trả PENDING hoặc version/lastUpdated, không hiển thị một projection stale như dữ liệu canonical mới nhất.

## 15. Giao tiếp bất đồng bộ: durable messaging

Một message broker giúp producer không cần biết consumer đang online ngay lúc publish, nhưng phải xác định:

- Message có được lưu bền vững trước khi producer nhận acknowledgment không?
- Producer retry có thể tạo duplicate không?
- Consumer ack ở thời điểm nào?
- Poison message được xử lý ra sao?
- Retry queue/DLQ có retention và alert không?
- Ordering cần ở mức nào?
- Consumer scale có làm downstream quá tải không?
- Schema version và replay compatibility thế nào?

### 15.1. Transactional outbox

Nếu business record được ghi vào DB và event phải publish, ghi cả hai trong cùng transaction:

    BEGIN
      UPDATE orders SET status = 'CONFIRMED' WHERE id = ...;
      INSERT INTO outbox(event_id, aggregate_id, event_type, payload);
    COMMIT

Publisher đọc outbox và gửi broker. Nếu publisher crash sau publish nhưng trước mark sent, event có thể được gửi lại. Consumer phải idempotent.

Outbox giải quyết khoảng trống giữa commit database và publish event; nó không đảm bảo consumer đã hoàn tất mọi side effect.

### 15.2. Inbox/deduplication

Consumer có thể ghi event ID đã xử lý trong cùng transaction với business update. Nếu event được giao lại, unique constraint ngăn xử lý business lần hai.

Nếu consumer gọi external provider, inbox transaction không bao phủ side effect ngoài; cần idempotency key và trạng thái đối soát.

### 15.3. Dead-letter queue

Poison message không được retry vô hạn. DLQ cần:

- Alert khi message vào.
- Lưu reason/code và metadata cần thiết.
- Bảo vệ PII.
- Quy trình inspect, sửa dữ liệu/schema và replay có kiểm soát.
- Giới hạn quyền replay để tránh duplicate side effect.
- Metric về oldest message và backlog.

DLQ không phải thùng rác có thể bỏ quên; message quan trọng bị chuyển vào DLQ vẫn là công việc chưa hoàn tất.

## 16. Propagate trace context và correlation ID

Một request có thể đi qua Gateway, Order, Inventory, Payment và Broker. Nếu mỗi service tạo log riêng mà không giữ trace context, khó tìm nguyên nhân latency hoặc duplicate.

Cần:

- Distributed tracing theo chuẩn được tổ chức chọn (ví dụ W3C Trace Context).
- Propagate traceparent/tracestate qua HTTP hoặc message headers.
- Correlation ID cho business workflow nếu cần.
- Business IDs như orderId/paymentId được log theo policy.
- Không dùng PII hoặc credential làm trace baggage.
- Đo span của network call, queue wait và xử lý consumer.
- Giữ trace context khi publish event và khi consumer xử lý.

Correlation ID không thay authentication và không phải idempotency key. Mỗi khái niệm có mục đích riêng.

## 17. Java/Spring Boot: HTTP client với timeout

Ví dụ sử dụng Spring WebClient; cấu hình chính xác phụ thuộc phiên bản Spring Boot/Reactor Netty:

    @Configuration
    public class InventoryClientConfig {

        @Bean
        WebClient inventoryWebClient(
                WebClient.Builder builder) {
            HttpClient httpClient = HttpClient.create()
                .option(
                    ChannelOption.CONNECT_TIMEOUT_MILLIS,
                    300
                )
                .responseTimeout(Duration.ofMillis(500));

            return builder
                .baseUrl("http://inventory-service")
                .clientConnector(
                    new ReactorClientHttpConnector(httpClient)
                )
                .build();
        }
    }

Cần thêm imports và dependency phù hợp trong dự án thực. Connect timeout và response timeout không nhất thiết bao phủ toàn bộ thời gian của business operation; caller vẫn cần tổng deadline.

Không đặt timeout tùy tiện theo một con số cho mọi service. Dùng latency distribution, SLO và phần thời gian dành cho các bước còn lại để phân bổ.

## 18. Java/Spring Boot: gọi API có deadline và error mapping

Một service có thể dùng WebClient:

    public Mono<InventoryResult> reserve(
            ReservationRequest request) {
        return inventoryWebClient.post()
            .uri("/inventory/reservations")
            .bodyValue(request)
            .retrieve()
            .onStatus(
                status -> status.value() == 409,
                response -> response.bodyToMono(String.class)
                    .map(body -> new InsufficientStockException(body))
            )
            .onStatus(
                status -> status.is5xxServerError(),
                response -> response.createException()
            )
            .bodyToMono(InventoryResult.class)
            .timeout(Duration.ofMillis(700));
    }

Đoạn code minh họa, cần bổ sung import, exception mapping, tracing, authentication và retry policy phù hợp. Timeout ở đây không chứng minh provider chưa thực hiện reservation. Với command có side effect, request cần idempotency key và khả năng tra trạng thái.

Không bắt mọi exception rồi trả empty result: điều đó có thể biến lỗi dependency thành dữ liệu nghiệp vụ sai.

## 19. Java: retry có giới hạn

Có thể dùng Resilience4j Retry hoặc cơ chế tương đương. Policy phải phân loại lỗi transient và loại trừ business rejection.

Pseudo-configuration minh họa:

    maxAttempts: 3
    waitDuration: 100ms
    exponentialBackoffMultiplier: 2
    randomJitter: enabled
    retryOn:
      - connect failure before request delivery
      - selected 502/503/504
    doNotRetry:
      - 400
      - 401
      - 403
      - 422
      - business validation rejection

Với HTTP command, chỉ retry khi operation idempotent hoặc có key. Nếu timeout xảy ra sau khi request có thể đã được gửi, cần coi outcome là uncertain và dùng cùng key.

Kết hợp tổng retry deadline để không giữ request lâu hơn SLO. Không cấu hình retry ở nhiều tầng mà không tính tổng số lần gọi.

## 20. Java: circuit breaker và bulkhead

Resilience4j có thể cung cấp các pattern:

    CircuitBreaker:
      slidingWindowSize: 20
      failureRateThreshold: 50
      waitDurationInOpenState: 5s
      permittedCallsInHalfOpenState: 3

    Bulkhead:
      maxConcurrentCalls: 20
      maxWaitDuration: 50ms

Các số chỉ là ví dụ. Cần đánh giá traffic volume, minimum number of calls, latency, failure types và provider capacity. Nếu một dependency có traffic thấp, cửa sổ quá nhỏ có thể mở circuit do vài lỗi ngẫu nhiên.

Circuit breaker có thể kết hợp bulkhead và timeout, nhưng phải tránh retry bên trong circuit tạo vòng lặp. Chọn một lớp sở hữu retry chính và đo toàn bộ downstream attempts.

## 21. Fallback theo từng loại nghiệp vụ

Ví dụ:

| Dependency | Fallback có thể phù hợp | Fallback nguy hiểm |
| --- | --- | --- |
| Recommendation | Ẩn khu vực gợi ý | Hiển thị dữ liệu sai như mới |
| Catalog search | Cache có giới hạn freshness | Dùng giá cũ để xác nhận giao dịch |
| Profile display | Projection cũ có nhãn stale nếu được phép | Dùng địa chỉ cũ cho giao dịch bắt buộc xác nhận mới |
| Reporting | Trả job pending | Trả báo cáo chưa hoàn chỉnh như đầy đủ |
| Payment | Giữ trạng thái UNKNOWN/PENDING và đối soát | Tự đánh dấu paid/failed sau timeout |
| Inventory | Tạm từ chối hoặc chờ xác minh | Mặc định còn hàng |
| Authorization | Fail closed | Cho phép khi auth service lỗi |

Fallback phải gắn với business invariant, freshness và mức rủi ro. Không dùng một fallback chung cho mọi endpoint.

## 22. Chống cascading failure trong call chain

Một request có thể đi qua nhiều dependency:

    Client
      -> Gateway
      -> Order
      -> Inventory
      -> Pricing
      -> Payment
      -> Notification

Nếu mỗi tầng giữ worker và retry khi downstream chậm, lượng công việc chờ có thể tăng nhanh.

Các biện pháp:

- Tổng deadline xuyên chuỗi.
- Timeout ngắn phù hợp ở từng hop.
- Concurrency cap/bulkhead theo dependency.
- Retry budget và jitter.
- Circuit breaker cho lỗi availability.
- Bounded queue và load shedding.
- Không gọi service không thiết yếu trong critical path.
- Idempotency cho command.
- Graceful degradation có policy.
- Capacity budget tổng thể cho downstream.

Một service có thể khỏe về CPU nhưng vẫn cạn thread do chờ network. Cần theo dõi thread pool queue, connection pool wait và in-flight requests.

## 23. Security của service-to-service contract

Giao tiếp nội bộ không mặc nhiên đáng tin. Cần:

- Authentication service identity (OAuth2 client credentials, mTLS hoặc cơ chế phù hợp).
- Authorization theo action/resource/tenant.
- Least privilege cho service account.
- Credential rotation và secret management.
- TLS cho traffic nội bộ khi policy yêu cầu.
- Kiểm tra payload, size limit và schema.
- Chống replay nếu operation hoặc protocol cần.
- Audit cho các lệnh nhạy cảm.
- Không tin X-Tenant-ID hoặc user identity từ header chưa được xác thực.
- Phân loại PII/secrets trong event, log và trace.

Một service được phép gọi Inventory API không có nghĩa nó được phép reserve hàng cho mọi tenant hoặc mọi order. Provider vẫn phải kiểm tra quyền và ownership.

## 24. Rate limit và admission control

Rate limit giới hạn tốc độ; concurrency limit giới hạn số operation đang chạy. Cần kết hợp khi một request giữ tài nguyên lâu.

Các lớp:

- Per-client/per-tenant quota.
- Global emergency cap.
- Per-route weighted cost.
- Concurrency cap trước DB/provider.
- Queue capacity hữu hạn cho async work.
- Retry budget riêng.

Nếu mỗi Pod có local rate limit, quota có thể bị nhân theo số replicas. Muốn quota toàn cluster cần shared state hoặc phân chia budget có chủ đích.

429 thường phù hợp khi consumer vượt quota của mình; 503 có thể phù hợp khi nền tảng thiếu capacity. Contract phải phân biệt để caller không retry sai cách.

## 25. Migration từ direct call sang contract

Không nên đổi tất cả consumer cùng một lúc. Một lộ trình:

1. **Inventory:** tìm mọi direct dependency, shared table và class import.
2. **Define contract:** API/event schema, error model, auth, consistency và SLO.
3. **Implement provider:** service đích sở hữu logic và dữ liệu, contract tests.
4. **Adapter/facade:** tạo một interface rõ để thay đổi consumer từng bước.
5. **Shadow/read comparison:** nếu phù hợp, gọi đường mới ở chế độ read-only và so kết quả.
6. **Canary consumer:** chuyển một nhóm nhỏ traffic hoặc tenant.
7. **Observe:** latency, errors, mismatches, retry, downstream saturation.
8. **Expand:** chuyển thêm consumers sau khi đạt tiêu chí.
9. **Fence old path:** ngừng direct DB access hoặc legacy call.
10. **Contract:** xóa adapter/old schema sau khi hết consumer và hết thời gian deprecation.

Không để compatibility adapter tồn tại vĩnh viễn mà không có owner, metrics và ngày kết thúc. Nếu adapter chứa nhiều business logic, nó có thể trở thành service trung gian khó bảo trì.

### 25.1. Strangler pattern

Có thể định tuyến dần:

    Client
      |
      v
    API Facade / Router
      |             |
      v             v
    Old module     New service
       \             /
        \-- controlled migration

Router cần routing rule versioned, audit và fallback an toàn. Với command có side effect, không gửi đồng thời sang old và new chỉ để so sánh. Shadow chỉ nên áp dụng với read không side effect hoặc môi trường test.

## 26. Kiểm thử contract và khả năng phục hồi

Một bộ kiểm thử đầy đủ gồm:

**Schema/contract tests**
- Required/optional field.
- Enum và unknown field.
- Version cũ/mới.
- Error code và status.
- Tenant/auth context.

**Consumer-driven contract**
- Consumer mô tả kỳ vọng thật.
- Provider xác minh contract trước release.
- Kiểm tra rollout khi consumer/provider khác phiên bản.

**Integration tests**
- HTTP client, TLS/auth, serialization.
- Broker publish/consume, ack/retry/DLQ.
- Transactional outbox/inbox.
- Idempotency và duplicate message.

**Resilience tests**
- Provider timeout.
- Connection refused.
- DNS/TLS failure.
- 429/503.
- Response mất sau side effect.
- Circuit open/half-open.
- Bulkhead đầy.
- Queue full.
- Dependency hồi phục sau outage.

**Performance tests**
- p95/p99 latency dưới tải.
- Retry amplification.
- Thread/connection pool saturation.
- Throughput khi một dependency chậm.
- Backlog drain rate sau phục hồi.

**Business tests**
- Payment timeout không tạo double charge.
- Inventory unavailable không xác nhận order sai.
- Fallback không vi phạm invariant.
- Event replay không gửi side effect trùng.

Không chỉ mock mọi network call. Mock hữu ích cho unit test, nhưng contract/integration/resilience cần môi trường provider hoặc broker thực tương ứng.

## 27. Chaos engineering và failure injection

Có thể mô phỏng:

- Tăng latency của Inventory API.
- Drop một tỷ lệ response.
- Restart một consumer.
- Tạm dừng broker hoặc làm tăng consumer lag.
- Làm DNS lookup thất bại trong môi trường test.
- Trả 429/503 theo burst.
- Làm database connection pool cạn.
- Đưa event duplicate/out-of-order.
- Cho provider hồi phục sau thời gian circuit open.

Mục tiêu không phải tạo lỗi để chứng minh hệ thống “không bao giờ hỏng”. Mục tiêu là xác nhận failure mode đã dự đoán, blast radius, alert, fallback và recovery đúng như thiết kế.

Chỉ thực hiện trên môi trường và phạm vi đã được kiểm soát; bắt đầu từ test/staging hoặc game day có kế hoạch, có stop conditions và rollback.

## 28. Observability cho contract và resilience

Các metric quan trọng:

| Metric | Ý nghĩa |
| --- | --- |
| client_request_duration_seconds | Latency của lời gọi downstream |
| client_requests_total | Số lời gọi theo dependency/status |
| client_timeouts_total | Số timeout |
| client_retries_total | Số retry |
| circuit_breaker_state | Trạng thái breaker |
| circuit_breaker_rejections_total | Số call bị từ chối nhanh |
| bulkhead_in_flight | Số call đang chiếm permit |
| bulkhead_rejections_total | Số call không lấy được slot |
| connection_pool_pending | Request chờ connection |
| queue_oldest_message_age | Tuổi message lâu nhất |
| consumer_lag | Độ trễ consumer |
| idempotency_replays_total | Request/message lặp được nhận diện |
| fallback_total | Số lần fallback |
| contract_version_usage | Consumer/provider version đang dùng |

Tên metric chỉ là ví dụ. Dùng labels có cardinality giới hạn như service, operation, status class, region, version major; tránh user ID/order ID/trace ID làm metric label.

Trace nên cho biết span nào chiếm thời gian, có retry bao nhiêu lần, queue wait bao lâu và dependency nào gây lỗi. Log có correlation ID nhưng không chứa credential hoặc PII ngoài policy.

### 28.1. Alert theo SLO

- p95/p99 dependency latency vượt budget.
- Timeout/error rate tăng.
- Circuit breaker mở kéo dài.
- Bulkhead rejection tăng.
- Retry rate cao hơn baseline.
- Queue oldest age hoặc consumer lag vượt deadline.
- DLQ tăng.
- Idempotency conflict hoặc unknown payment state tăng.
- Consumer version cũ sắp hết deprecation window.

Một service có thể vẫn trả 200 nhờ fallback nhưng business success rate đang giảm. Cần đo kết quả nghiệp vụ, không chỉ HTTP success.

## 29. SLO và ngân sách latency xuyên service

Ví dụ checkout có SLO p95 800 ms:

| Thành phần | Budget minh họa |
| --- | ---: |
| Gateway/auth | 80 ms |
| Order local validation | 70 ms |
| Inventory API | 180 ms |
| Pricing API | 120 ms |
| Payment authorization | 250 ms |
| Serialization/network reserve | 100 ms |
| **Tổng** | **800 ms** |

Đây là phân bổ giả định. Tổng p95 của từng span không nhất thiết bằng p95 của end-to-end do tương quan và phân phối latency. Cần đo transaction thật.

Nếu một dependency chiếm phần lớn budget, cân nhắc cache/projection, parallelism an toàn, giảm số network hops hoặc chuyển bước không thiết yếu sang async. Không song song hóa các operation có phụ thuộc thứ tự hoặc side effect nếu không có protocol đúng.

## 30. Khi nào nên dùng event thay cho chain API?

Một chuỗi đồng bộ:

    Order -> Inventory -> Payment -> Notification

có thể tạo latency và failure propagation. Một workflow event-driven:

    Order Service
       -> OrderPlaced event
            -> Inventory consumer
            -> Payment workflow
            -> Notification consumer

giảm coupling thời điểm nhưng cần state machine và saga/workflow orchestration nếu nhiều bước phải phối hợp.

Không phải mọi API call đều nên đổi thành event. Nếu caller cần biết ngay inventory reservation thành công để chốt order, một command/response có thể phù hợp. Nếu notification chỉ cần gửi sau khi order confirmed, event async phù hợp hơn.

Chọn theo business semantics, deadline, consistency và khả năng xử lý pending/compensation.

## 31. Saga và compensation trong giao tiếp phân tán

Một workflow có nhiều side effects:

    Create Order
       -> Reserve Inventory
       -> Authorize Payment
       -> Confirm Order

Nếu payment bị từ chối sau khi inventory đã reserve, cần hành động bù trừ ReleaseInventory. Đây là ví dụ saga.

Một saga có thể dùng orchestration (một coordinator quản lý state) hoặc choreography (các service phản ứng với events). Dù chọn cách nào, cần:

- Workflow ID và correlation.
- Trạng thái bền vững cho từng bước.
- Timeout/deadline cho bước.
- Retry và idempotency.
- Compensation semantics.
- Reconciliation khi kết quả không rõ.
- Quan sát workflow đang pending/stuck.

Compensation không phải rollback database transaction. Một payment đã authorize có thể cần void/refund theo API provider; không thể giả định đảo ngược hoàn toàn như chưa từng xảy ra.

## 32. Java/Spring Boot: xử lý trạng thái UNKNOWN

Ví dụ domain state:

    enum PaymentStatus {
        REQUESTED,
        PROCESSING,
        AUTHORIZED,
        DECLINED,
        UNKNOWN,
        RECONCILIATION_REQUIRED
    }

Khi timeout sau khi gửi lệnh, có thể lưu UNKNOWN hoặc PROCESSING tùy contract, rồi truy vấn trạng thái theo idempotency key/external reference. Không đổi thành DECLINED chỉ vì client không nhận được response.

Một endpoint tra cứu:

    GET /payments/operations/{idempotencyKey}

có thể trả PROCESSING, AUTHORIZED, DECLINED hoặc UNKNOWN theo semantics. Client phải hiểu UNKNOWN là chưa thể kết luận, không phải thất bại cuối cùng.

## 33. Contract deprecation và consumer inventory

Trước khi xóa field/endpoint cũ:

- Xác định toàn bộ consumers theo access logs, registry và team ownership.
- Thông báo deprecation với ngày sunset và migration guide.
- Phát hành provider hỗ trợ cả old/new contract trong thời gian chuyển.
- Theo dõi usage theo version/consumer.
- Có consumer contract tests và cảnh báo consumer cũ.
- Chỉ xóa khi hết usage hoặc có ngoại lệ được owner chấp thuận.
- Giữ tài liệu và cách xử lý nếu client không thể nâng cấp đúng hạn.

Không suy ra “không còn consumer” từ việc một tuần không thấy request nếu batch job chạy theo tháng/quý. Cần biết lịch và các consumer offline.

## 34. Bài tập thực hành: thay direct calls bằng contract

Một Order Service đang gọi class InventoryService trực tiếp trong cùng codebase và đọc bảng inventory bằng shared repository. Hệ thống được tách Inventory thành deployment riêng. Các thông tin giả định:

- Checkout cần xác nhận reservation trước khi order được confirmed.
- Inventory API có p95 120 ms bình thường nhưng có thể chậm 2 giây khi peak.
- Client có thể retry khi gateway timeout.
- Message broker giao event at-least-once.
- Một số consumer cũ vẫn đọc bảng inventory trong giai đoạn rollout.
- Order/Payment có side effect và không được lặp.

**Yêu cầu:**

1. Xác định Inventory là provider và Order là consumer; mô tả owner của stock.
2. Định nghĩa API command ReserveInventory, response và error codes.
3. Chọn timeout/deadline phù hợp với checkout SLO.
4. Thiết kế idempotency key cho một lần reserve theo order.
5. Phân biệt timeout với business rejection và trạng thái UNKNOWN.
6. Thiết kế retry/backoff và circuit breaker không retry mọi lỗi.
7. Chọn bulkhead/concurrency limit để bảo vệ Inventory.
8. Xác định phần nào chuyển sang event async và phần nào cần response đồng bộ.
9. Lập kế hoạch chuyển direct DB read sang API/projection.
10. Thiết kế version compatibility khi provider và consumer deploy lệch thời điểm.
11. Kiểm thử duplicate command, response mất sau side effect, broker redelivery và Inventory outage.
12. Định nghĩa metrics/alerts để biết khi contract đang vi phạm SLO.
13. Mô tả saga/compensation nếu Payment bị decline sau khi reserve.
14. Nêu điều kiện an toàn để ngừng quyền truy cập shared table.

**Hướng giải:** Inventory giữ single writer cho stock/reservation; Order gửi command với key ổn định; provider trả reservation result theo contract; timeout tạo trạng thái chưa rõ và cần query/reconcile; retry giới hạn và dùng cùng key; circuit breaker/bulkhead bảo vệ dependency; chuyển consumers theo cohort, dùng adapter/projection; chỉ thu hồi shared DB access sau khi inventory reader/writer cũ đã được chuyển.

## 35. Những sai lầm thường gặp

**“Đổi method call thành HTTP là đã tách service.”** Nếu vẫn dùng shared database và phụ thuộc implementation, coupling chưa biến mất.

**“Timeout nghĩa là provider chưa xử lý.”** Response có thể mất sau khi side effect đã xảy ra.

**“Retry mọi lỗi 5xx và timeout.”** Có thể nhân tải hoặc tạo duplicate side effect.

**“Circuit breaker thay được retry.”** Breaker ngăn gọi dependency đang lỗi; retry xử lý transient failures trong budget.

**“Queue làm hệ thống không mất message.”** Còn durability, acknowledgment, retention, DLQ và consumer idempotency.

**“HTTP 200 nghĩa nghiệp vụ thành công.”** Có thể response là fallback/stale hoặc workflow vẫn pending.

**“API versioning giải quyết mọi breaking change.”** Consumer cũ, semantics và rollout order vẫn cần compatibility tests.

**“Internal network đáng tin nên không cần auth.”** Service-to-service vẫn cần identity, authorization và tenant boundary.

**“Mỗi service tự đặt timeout 5 giây.”** Tổng call chain có thể vượt deadline người dùng.

**“Một semaphore trong JVM là global limit.”** Replica tăng thì tổng concurrency có thể tăng theo.

**“Fallback luôn tốt hơn lỗi.”** Fallback sai có thể vi phạm tiền, tồn kho hoặc quyền truy cập.

**“Exactly-once của broker bảo đảm exactly-once business.”** Side effect nằm ngoài broker và cần idempotency/reconciliation.

**“DLQ là nơi có thể bỏ quên message lỗi.”** Message quan trọng vẫn là công việc chưa hoàn thành và cần alert/replay policy.

## 36. Checklist triển khai

### Contract

- Provider và consumer ownership rõ?
- API/event schema có semantics, error model và version?
- Authn/authz và tenant context được kiểm tra?
- Nullability, enum, timezone, ID và consistency được định nghĩa?
- Có deprecation và compatibility policy?

### Resilience

- Timeout/deadline tổng và từng hop?
- Retry có giới hạn, backoff, jitter và budget?
- Command có side effect dùng idempotency?
- Circuit breaker phân loại đúng lỗi?
- Bulkhead và bounded queue bảo vệ resource?
- Fallback có staleness và business policy?
- DLQ/replay và reconciliation được quản trị?

### Operations

- Trace context và correlation được propagate?
- Metrics latency, error, retry, circuit, queue và business outcome?
- Alert theo SLO và backlog?
- Contract tests/provider-consumer integration tests?
- Failure injection/chaos test có kiểm soát?
- Legacy callers và direct database access đã được kiểm kê?
- Có rollout/canary/rollback plan?
- Có owner chịu trách nhiệm contract và sunset?

---

**Điểm cốt lõi:** Thay giao tiếp nội bộ bằng hợp đồng và cơ chế phục hồi nghĩa là chuyển phụ thuộc ngầm thành **contract rõ ràng, có version và có hành vi xác định khi lỗi**. API/event cần semantics, security và compatibility; network calls cần deadline, timeout, retry có giới hạn, circuit breaker, bulkhead và idempotency; workflow phân tán cần ordering, trạng thái pending, reconciliation và quan sát. Một kiến trúc chỉ thực sự độc lập khi provider và consumer có thể triển khai lệch thời điểm, chịu được dependency failure và vẫn bảo vệ đúng các bất biến nghiệp vụ.

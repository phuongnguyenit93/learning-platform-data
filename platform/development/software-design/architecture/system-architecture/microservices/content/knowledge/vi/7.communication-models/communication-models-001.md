# Phân biệt tương tác yêu cầu–phản hồi, lệnh và sự kiện

Trong kiến trúc microservices, ba thuật ngữ **yêu cầu–phản hồi (request–response)**, **lệnh (command)** và **sự kiện (event)** thường xuất hiện cùng nhau nhưng không thuộc cùng một trục phân loại. Nếu phân biệt theo công nghệ như “HTTP là request”, “queue là command”, “Kafka là event”, thiết kế dễ sai ngữ nghĩa, khó xử lý lỗi và vô tình ghép chặt các service.

Cách hiểu chính xác:

- **Request–response** là **mẫu tương tác**: một bên gửi yêu cầu và nhận câu trả lời gắn với yêu cầu đó.
- **Command** là **ý định**: yêu cầu một thành phần có thẩm quyền thực hiện hành động, sau khi kiểm tra điều kiện và bất biến nghiệp vụ.
- **Event** là **sự thật đã xảy ra**: thành phần sở hữu công bố một thay đổi hoặc kết quả đã được ghi nhận.

Một HTTP POST có thể vận chuyển command và trả response. Một command có thể đi qua message queue. Một event có thể được gửi bằng webhook HTTP. Vì vậy, khi thiết kế cần trả lời đồng thời hai câu hỏi: **Thông điệp có ý nghĩa gì?** và **Hai bên trao đổi thông điệp theo kiểu nào?**

Bài học sử dụng hệ thống đặt hàng với Ordering, Inventory, Payments, Shipping và Notifications làm ví dụ, trình bày các lựa chọn về thời gian, ownership, transaction, lỗi và vận hành.

## 1. So sánh trực tiếp

| Tiêu chí | Request–response | Command | Event |
| --- | --- | --- | --- |
| Bản chất | Cơ chế trao đổi có phản hồi | Yêu cầu thực hiện một hành động | Thông báo sự thật đã xảy ra |
| Câu hỏi | “Tôi nhận được câu trả lời nào?” | “Hãy làm việc X” | “X đã xảy ra” |
| Ví dụ | GET /orders/100 → 200 | PlaceOrder, ReserveStock | OrderPlaced, StockReserved |
| Vai trò người nhận | Endpoint/server trả lời request | Owner thực thi hoặc từ chối | Một hoặc nhiều subscriber tùy nhu cầu |
| Tính hoàn tất | Response có thể là dữ liệu, ACK hoặc kết quả | Có thể accepted, rejected, completed | Fact phải đã xảy ra ở producer; consumer có thể chưa xử lý |
| Thời gian | Thường đồng bộ nhưng có thể async reply | Đồng bộ hoặc bất đồng bộ | Thường bất đồng bộ nhưng không bị ràng buộc |
| Xử lý trùng | Phụ thuộc ngữ nghĩa request | Idempotency đặc biệt quan trọng nếu có side effect | Consumer cần dedup/idempotency khi redelivery |
| Coupling | Caller cần contract và khả năng sẵn sàng để có kết quả | Caller biết năng lực/owner được yêu cầu | Subscriber biết contract event; publisher không cần biết từng subscriber |

**Điểm phân biệt quan trọng nhất:** request–response giải thích *hình thức tương tác*, còn command/event giải thích *ý nghĩa và trách nhiệm trong nghiệp vụ*. Do đó không nên xem chúng như ba lựa chọn loại trừ nhau.

## 2. Hai trục: cơ chế giao tiếp và ngữ nghĩa

~~~text
                             NGỮ NGHĨA
                    Query       Command           Event
CƠ CHẾ
HTTP request/reply   GET price   POST order        Webhook OrderPlaced + ACK
gRPC request/reply   GetPrice    ConfirmOrder      Event callback / stream
Queue async          Query/reply ReserveStock      StockReserved published
Broker pub/sub       ít gặp     không thích hợp   OrderPlaced to subscribers
~~~

Một query (truy vấn) hỏi dữ liệu mà không có ý định thay đổi trạng thái nghiệp vụ. Một command yêu cầu thay đổi hay hành động. Một event thông báo kết quả. Tên giao thức và method không tự tạo ra tính chất này.

Ví dụ: HTTP POST /orders thường là một **request–response mang command PlaceOrder**. Server có thể trả 201 Created khi đã tạo đơn hoặc 202 Accepted khi mới lưu yêu cầu xử lý. Sau khi commit Order, Ordering có thể phát **event OrderPlaced**. Các event này lại được vận chuyển qua broker, nhưng cũng có thể được đẩy bằng HTTP webhook.

Không nên suy đoán chỉ từ tên công nghệ rằng một thông điệp đã có được semantic, nhất quán hay durability nào.

## 3. Request–response: cần một câu trả lời tương ứng

Mẫu cơ bản:

~~~text
Client                    Server
  | ------ request ------> |
  |                        | xử lý / truy vấn
  | <----- response ------ |
~~~

Người gọi xác định nơi nhận và kỳ vọng phản hồi trong một thời gian nhất định. HTTP và gRPC unary biểu diễn tự nhiên. Trên broker vẫn có thể cài request/reply bằng correlationId, replyTo và xử lý timeout riêng.

Phù hợp khi:

- Cần dữ liệu ngay để hiển thị, như giá, trạng thái đơn, thông tin tài khoản.
- Một command ngắn được hoàn tất bằng transaction cục bộ, có thể trả kết quả tức thì.
- Người dùng cần biết validation hoặc conflict tại thời điểm thao tác.
- Độ trễ và availability downstream nằm trong ngân sách cho phép.

Ví dụ truy vấn:

~~~http
GET /api/products/sku-42/quote?currency=VND
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "sku-42",
  "priceMinor": 159900,
  "currency": "VND",
  "quoteVersion": "v218",
  "expiresAt": "2026-11-11T14:00:00Z"
}
~~~

Response là dữ liệu báo giá; nó không đồng nghĩa với việc đã giữ tồn hoặc chốt giá cho một Order. Ordering cần policy riêng để xác định lúc nào giá được xác nhận và snapshot nào được lưu.

### Các mức thành công cần phân biệt

- **Transport success:** request tới đích, response truyền về được.
- **Accepted:** service đã nhận yêu cầu xử lý, có thể còn pending.
- **Business completed:** hành động nghiệp vụ đã thực sự hoàn tất theo hợp đồng.
- **Business rejected:** command không hợp lệ ở trạng thái hiện tại, ví dụ tồn không đủ.
- **Technical failure:** timeout, mạng lỗi, database không sẵn sàng, broker lỗi.

HTTP 200 không tự bảo đảm business completed; HTTP 202 Accepted càng không có nghĩa xử lý đã hoàn tất. Một operation ID hoặc endpoint tra cứu trạng thái thường cần thiết cho công việc dài.

Ví dụ tạo báo cáo:

~~~http
POST /reports
Content-Type: application/json

{ "dateFrom": "2026-11-01", "dateTo": "2026-11-10" }

HTTP/1.1 202 Accepted
Location: /operations/op-987

{ "operationId": "op-987", "status": "ACCEPTED" }
~~~

Client có thể GET /operations/op-987 để theo dõi. Nếu xử lý kéo dài vài phút, giữ một kết nối HTTP đồng bộ xuyên nhiều service thường không cần thiết.

### Rủi ro đặc trưng của request–response

Một chuỗi Checkout → Ordering → Pricing → Inventory → Payments có thể tăng latency và khuếch đại outage. Mỗi caller cần timeout, retry giới hạn, circuit breaker/bulkhead phù hợp và cách xử lý khi kết quả không rõ.

Điều nguy hiểm nhất là **timeout sau khi side effect đã commit**. Payment API có thể đã capture tiền nhưng response bị mất; retry bằng một payment mới có thể gây thu tiền hai lần. Bắt buộc thiết kế idempotency và cách kiểm tra kết quả theo operation ID.

## 4. Command: một chủ thể có quyền quyết định

Command mô tả ý định tác động vào nghiệp vụ: PlaceOrder, ConfirmOrder, ReserveStock, AuthorizePayment, CancelShipment, SendReceipt.

~~~text
Ordering              Inventory
   | --- ReserveStock --> |
   |                      | kiểm tra quyền và số lượng khả dụng
   |                      | cập nhật trạng thái trong local transaction
   | <--- kết quả -------- | (response hoặc event)
~~~

Command có một **owner logic**. Nhiều worker instance có thể chia tải nhận command, nhưng hành động phải do service có quyền và có dữ liệu authoritative quyết định. Sender không tự khẳng định kết quả.

Đặc tính nên có:

1. **Tên diễn đạt ý định:** ReserveStock thay vì StockReserved.
2. **Người nhận xác định:** Inventory chịu trách nhiệm quyết định giữ hàng.
3. **Precondition rõ ràng:** số lượng dương, đơn hợp lệ, phiên bản dữ liệu còn đúng, quyền thao tác hợp lệ.
4. **Kết quả rõ ràng:** accepted, rejected, completed, failed, expired theo hợp đồng.
5. **Idempotency:** xử lý command lặp không nhân đôi hiệu ứng.
6. **Điều kiện đồng thời:** optimistic/pessimistic lock, conditional update hoặc unique constraint phù hợp.
7. **Thời hạn và retry:** nếu command đến sau deadline thì cách xử lý phải được quy định.
8. **Khả năng quan sát:** command ID, correlation ID, operation state, lỗi và metric.

Ví dụ command payload:

~~~json
{
  "commandId": "cmd-reserve-771",
  "commandType": "ReserveStock",
  "schemaVersion": 1,
  "orderId": "ord-1001",
  "warehouseId": "wh-hcm",
  "items": [
    { "sku": "sku-42", "quantity": 2 }
  ],
  "requestedAt": "2026-11-11T09:00:00Z",
  "expiresAt": "2026-11-11T09:05:00Z",
  "correlationId": "checkout-1001"
}
~~~

Command này **không** chứng minh kho đã giữ hàng. Inventory cần kiểm tra invariant, race condition và tình trạng khả dụng.

### Command có thể đồng bộ

~~~text
POST /orders {PlaceOrder}
  -> validate
  -> Order.create()
  -> commit Order + outbox
  <- 201 Created {orderId}
~~~

Nếu việc tạo đơn đã được commit trong local transaction thì có thể trả 201 Created. Luồng giữ tồn, thanh toán và giao hàng phía sau vẫn chưa hoàn tất; trạng thái Order cần phản ánh đúng.

### Command cũng có thể bất đồng bộ

~~~text
POST /orders {PlaceOrder}
  -> persist durable operation
  <- 202 Accepted {operationId}

Worker nhận PlaceOrder:
  -> commit Order
  -> ghi OrderPlaced
  -> trạng thái operation = COMPLETED
~~~

Một queue broker ACK chỉ xác nhận ở mức vận chuyển, không thể tự được diễn giải là “đã thực thi command”. Cần hợp đồng riêng để gửi kết quả hoặc truy vấn trạng thái.

## 5. Event: sự thật sau khi xảy ra

Event thường có tên quá khứ: OrderPlaced, StockReserved, PaymentCaptured, ShipmentDispatched, CustomerEmailChanged.

~~~text
Ordering
  | -- OrderPlaced --> Broker
                           |--> Inventory workflow
                           |--> Loyalty projection
                           |--> Analytics
                           |--> Notifications
~~~

Event thông báo **một fact trong miền do producer sở hữu**, không yêu cầu mọi consumer thực thi một hành động bắt buộc. Consumer có thể phản ứng độc lập hoặc không đăng ký. Publisher không nên cần biết toàn bộ subscriber để hoàn tất transaction tạo fact.

Đặc tính của event:

- **Đã xảy ra:** event phản ánh trạng thái đã được xác nhận trong ranh giới sở hữu.
- **Không mang ý định bắt buộc:** khác ReserveStock command.
- **Có nguồn có thẩm quyền:** Inventory phát StockReserved, Payments phát PaymentCaptured.
- **Có định danh và thời điểm:** eventId, occurredAt, aggregateId, version khi thích hợp.
- **Có lifecycle schema:** consumer cần hỗ trợ thay đổi tương thích và event đến muộn.
- **Có khả năng redelivery:** consumer phải xử lý trùng/idempotency và tiến trình hồi phục.

Ví dụ:

~~~json
{
  "eventId": "evt-stock-771",
  "eventType": "StockReserved",
  "schemaVersion": 1,
  "occurredAt": "2026-11-11T09:00:15Z",
  "producer": "inventory",
  "aggregateId": "reservation-771",
  "aggregateVersion": 3,
  "correlationId": "checkout-1001",
  "causationId": "cmd-reserve-771",
  "payload": {
    "reservationId": "reservation-771",
    "orderId": "ord-1001",
    "items": [{ "sku": "sku-42", "quantity": 2 }]
  }
}
~~~

Trong thiết kế chuẩn, Inventory chỉ phát StockReserved sau khi transaction giữ tồn thành công; nó không được phát “để yêu cầu listener giữ hàng”.

### Sự kiện miền và sự kiện tích hợp

**Domain event** dùng để mô tả thay đổi trong bounded context, có thể chỉ cần nội bộ service. **Integration event** là contract công bố cho service khác, đòi hỏi schema và semantics ổn định hơn. Một domain event có thể được chuyển thành integration event, nhưng không nên public nguyên object ORM cùng trường nhạy cảm.

Việc publish event lên broker **không đồng nghĩa event sourcing**. Event sourcing là mô hình lưu các sự kiện làm nguồn sự thật để tái dựng state; hệ thống sử dụng outbox và integration events có thể vẫn lưu trạng thái chuẩn trong bảng quan hệ.

## 6. Command và event nhìn gần giống nhưng khác trách nhiệm

| Tình huống | Command | Event |
| --- | --- | --- |
| Khách nhấn đặt hàng | PlaceOrder | OrderPlaced |
| Cần giữ hàng | ReserveStock | StockReserved / ReservationRejected |
| Cần thu tiền | CapturePayment | PaymentCaptured / PaymentDeclined |
| Cần hoàn tiền | RefundPayment | PaymentRefunded |
| Cần gửi email | SendConfirmationEmail | ConfirmationEmailDispatched |
| Cần tạo vận đơn | CreateShipment | ShipmentCreated |
| Cần hủy đơn | CancelOrder | OrderCancelled |

**ReserveStock** nghĩa là “hãy thử giữ hàng” và có thể bị từ chối. **StockReserved** nghĩa là “đã giữ hàng”; một consumer không có quyền sửa lại sự thật đó bằng cách từ chối command.

**SendEmail** yêu cầu thực hiện; **EmailDispatched** nói hệ thống đã giao message ra kênh gửi theo mức xác nhận đã định. Dispatched không nhất thiết có nghĩa người nhận đã nhận hoặc đọc; tên event phải khớp đúng mức business fact có thể chứng minh.

Một event có thể kích hoạt command mới. Ví dụ khi nhận OrderPlaced, một workflow phát ReserveStock. Sự kiện OrderPlaced không phải command ReserveStock trá hình; workflow chịu trách nhiệm quyết định cần làm gì sau fact đó.

## 7. Luồng đặt hàng kết hợp ba kiểu

~~~text
Browser             Ordering         Inventory        Payments
  |                    |                 |                |
  |-- GET quote ------>|                 |                |
  |<--- Quote ---------|                 |                |
  |-- POST PlaceOrder ->|                |                |
  |<-- 202 + orderId ---|                |                |
  |                    |-- OrderPlaced event --> Broker   |
  |                    |                                |
  |           OrderSaga receives event                   |
  |                    |-- ReserveStock command --------> Inventory
  |                    |<-- StockReserved event ---------|
  |                    |-- AuthorizePayment command ----------------> Payments
  |                    |<-- PaymentAuthorized event -----------------|
  |                    |-- ConfirmOrder command -------> Ordering
  |                    |-- OrderConfirmed event -------> Broker
  |-- GET order ------->|
  |<-- CONFIRMED -------|
~~~

Sơ đồ chỉ là dòng logic, không phải mô tả một broker/API bắt buộc. Các bước có thể dùng HTTP, gRPC hoặc queue, tùy yêu cầu latency, tải, độ tin cậy và sự phục hồi. Các lựa chọn giữ hàng trước thanh toán hay ngược lại cần được quyết định theo nghiệp vụ và rủi ro.

Trong cùng luồng:

- GET quote, GET order là query qua **request–response**.
- POST PlaceOrder là **command được vận chuyển bằng request–response**.
- ReserveStock và AuthorizePayment là **command** với owner cụ thể.
- OrderPlaced, StockReserved, PaymentAuthorized là **event** phản ánh kết quả.
- Saga là nơi theo dõi tiến trình nhiều bước, không phải một aggregate có quyền ghi trực tiếp dữ liệu của mọi service.

## 8. Phân biệt phối hợp bằng choreography và orchestration

**Choreography**: mỗi service đăng ký event mà mình cần và phản ứng theo trách nhiệm:

~~~text
OrderPlaced
   -> Inventory giữ hàng -> StockReserved
   -> Payments xử lý thanh toán -> PaymentAuthorized
   -> Shipping tạo vận đơn -> ShipmentCreated
~~~

Ưu điểm là giảm nhu cầu có một bộ điều phối trung tâm cho luồng đơn giản, giúp các service phản ứng linh hoạt với fact. Rủi ro là logic tổng thể phân tán, khó theo dõi khi timeout, cần bù trừ và có nhiều biến thể nghiệp vụ.

**Orchestration**: một process manager/saga lưu state và gửi các command theo tiến trình:

~~~text
on OrderPlaced:
    send ReserveStock
on StockReserved:
    send AuthorizePayment
on PaymentAuthorized:
    send ConfirmOrder
on ReservationRejected:
    send CancelOrder
on PaymentDeclined:
    send ReleaseReservation
    send CancelOrder
~~~

Ưu điểm là trách nhiệm kết thúc workflow, timeout và compensation tập trung hơn. Rủi ro là orchestrator có thể trở thành thành phần phức tạp và ghép nối cao nếu ôm cả logic nội bộ của các domain.

**Event không tự động nghĩa là choreography; command không tự động nghĩa là orchestration.** Cả hai mẫu đều có thể kết hợp với cả command và event. Chọn theo mức phức tạp, yêu cầu quan sát, recovery và ownership.

## 9. Bảo toàn bất biến và ranh giới giao dịch

Một command được owner thực thi trong phạm vi transaction mà nó kiểm soát. Ví dụ, để giữ tồn, Inventory phải bảo đảm số đã giữ không vượt số khả dụng của đơn vị tồn phù hợp khi có request đồng thời.

~~~text
ReserveStock(orderId, sku, quantity)
  -> Inventory tải trạng thái do mình sở hữu
  -> kiểm tra invariant
  -> cập nhật reservation / available quantity
  -> ghi StockReserved vào outbox
  -> commit local transaction
~~~

Không nên để Ordering tự ghi bảng tồn của Inventory, dù mọi service dùng chung database. Cũng không nên dùng một event “StockMustBeReserved” thay cho một command nhưng lại coi kết quả đã chắc chắn.

Eventual consistency nghĩa là các service đọc/nhìn trạng thái ở thời điểm khác nhau, **không đồng nghĩa được phép bỏ qua invariant**. Mỗi owner phải bảo vệ quy tắc cục bộ của mình. Workflow liên service cần trạng thái trung gian, deadline, retry, compensation và giám sát.

Ví dụ Order có thể ở PENDING_FULFILLMENT trong khi Inventory đang giữ hàng. Khi payment thất bại, saga ra lệnh ReleaseReservation và CancelOrder. Không phải mọi bước đảo ngược transaction trước; đây là các hành động nghiệp vụ bù trừ có logic riêng và có thể thất bại cần reconciliation.

## 10. Ghi state và phát event đáng tin cậy bằng outbox

Phản ví dụ:

~~~text
1. UPDATE orders SET status = CONFIRMED
2. COMMIT
3. publish OrderConfirmed
4. Crash giữa bước 2 và 3 => event bị mất
~~~

Nếu dùng hai hệ thống lưu trữ độc lập mà không có cơ chế phối hợp, database commit thành công không bảo đảm broker publish thành công. **Transactional outbox** giải quyết bằng cách ghi event record và state vào cùng local transaction:

~~~text
BEGIN
  UPDATE orders ...
  INSERT INTO outbox(eventId, eventType, payload)
COMMIT

Publisher đọc outbox:
  -> publish event
  -> đánh dấu đã publish
  -> retry khi kết quả chưa rõ
~~~

Outbox worker có thể gửi event trùng (ví dụ publish xong nhưng chết trước khi ghi nhận đã gửi). Subscriber phải idempotent. Outbox không bảo đảm mọi consumer đã xử lý xong; nó đảm bảo khả năng phát sự kiện từ trạng thái đã commit khi triển khai đúng.

Đối với command nhận từ queue, có thể dùng inbox/processed_messages và lưu side effect trong cùng transaction:

~~~text
Receive ReserveStock(commandId)
BEGIN
  nếu commandId đã xử lý -> đọc trạng thái cũ, không tạo thêm side effect
  nếu chưa:
     kiểm tra invariant
     lưu kết quả xử lý và processed commandId
     ghi event kết quả vào outbox
COMMIT
ACK broker
~~~

Cần kết hợp unique constraint, isolation và kiểm soát tranh chấp. Một thao tác find rồi insert không nguyên tử khi hai worker cùng xử lý command; database phải bảo đảm khóa định danh không trùng.

## 11. Thất bại của request, command và event khác nhau thế nào?

### Request timeout

Timeout chỉ cho biết client chưa nhận được response đúng hạn. Server có thể chưa nhận, đang xử lý, đã reject, hoặc đã commit và mất response. Vì vậy, đặc biệt với payment, không retry bằng khóa nghiệp vụ mới nếu kết quả cũ chưa rõ.

### Command bị từ chối

ReserveStock bị từ chối vì số lượng tồn không đủ là **business outcome**, không phải lỗi hạ tầng. Tùy hợp đồng có thể trả HTTP 409/422 hoặc phát ReservationRejected. Tự retry vô hạn khi không có thay đổi điều kiện chỉ gây quá tải.

### Broker redelivery

Một command hoặc event có thể được nhận nhiều lần nếu consumer crash sau commit nhưng trước ACK. Hệ thống cần thiết kế theo khả năng at-least-once delivery và xử lý trùng an toàn tại điểm gây side effect.

### Event đến muộn hoặc sai thứ tự

StockReleased có thể được nhận trước StockReserved nếu có nhiều luồng/partition hoặc replay. Consumer cần xét aggregateVersion, ordering key, state machine và cơ chế xác minh owner khi nhận event cũ, trùng hoặc ngoài trình tự.

### Consumer vắng mặt

Producer không nên chờ Analytics online mới được commit OrderPlaced. Broker retention, outbox và consumer lag cho phép subscriber bắt kịp sau, trong phạm vi chính sách lưu trữ. Nếu queue có dữ liệu ngoài thời hạn thì cần bootstrap/rebuild projection từ nguồn tin cậy.

Bảng phân loại:

| Kết quả | Hành động phù hợp |
| --- | --- |
| Validation lỗi | Từ chối có cấu trúc, không tự retry |
| Business rejection | Trả status/reason, workflow quyết định bước sau |
| Version conflict | Đọc state mới, retry có giới hạn nếu hợp lệ |
| 429/503, lỗi DB tạm thời | Backoff, jitter, retry budget |
| Timeout sau side effect có thể đã xảy ra | Tra operation ID, idempotency, reconciliation |
| Duplicate command/event | Dedup hoặc idempotent handler |
| Event schema không đọc được | DLQ/quarantine, cảnh báo, sửa hợp đồng và replay |
| Event đến trễ | So version/trạng thái, bỏ hoặc xử lý lại theo quy tắc |
| Saga thất bại giữa chừng | Retry/bù trừ/manual recovery có state |
| Publish event không rõ kết quả | Outbox publisher gửi lại, consumer dedup |

## 12. Idempotency và định danh thao tác

Một business command cần một **operation identity** ổn định khi có thể retry. Với PlaceOrder, idempotency key có thể là mã phiên checkout do client gửi và được scope theo tenant/customer. Với CapturePayment, cần payment operation key để gateway và service cùng nhận diện yêu cầu lặp.

Ví dụ request:

~~~http
POST /payments/capture
Idempotency-Key: pay-order-1001-attempt-1

{
  "paymentId": "pay-1001",
  "amountMinor": 159900,
  "currency": "VND"
}
~~~

Khi nhận lại cùng key và cùng nội dung nghiệp vụ, service có thể trả trạng thái đã lưu. Nếu key trùng mà payload nghiệp vụ khác, cần từ chối conflict; không âm thầm xử lý lần thứ hai.

Một messageId không luôn đồng nhất với business operation ID. Một business operation có thể phát nhiều event trạng thái, và một event có thể được publish lại nhưng giữ eventId. Xác định rõ scope, thời hạn lưu khóa và cách xử lý khi hết hạn.

**Exactly-once end-to-end** không tự xuất hiện chỉ vì broker hỗ trợ transaction hoặc chính sách giao hàng đặc biệt. Khi xử lý còn gọi external payment gateway, cập nhật database hoặc gửi email, phải thiết kế idempotency tại điểm tạo tác dụng nghiệp vụ.

## 13. Thiết kế schema và metadata

Một integration event có thể có envelope:

~~~json
{
  "messageId": "evt-order-1001",
  "messageType": "OrderPlaced",
  "schemaVersion": 2,
  "producer": "ordering",
  "occurredAt": "2026-11-11T09:21:15Z",
  "publishedAt": "2026-11-11T09:21:16Z",
  "aggregateId": "ord-1001",
  "aggregateVersion": 7,
  "correlationId": "checkout-888",
  "causationId": "cmd-place-1001",
  "payload": {
    "orderId": "ord-1001",
    "customerId": "cust-71",
    "total": { "amountMinor": 159900, "currency": "VND" }
  }
}
~~~

Các trường cần được hiểu chính xác:

- **messageId/eventId:** định danh thông điệp để dedup và điều tra.
- **messageType:** tên có ý nghĩa nghiệp vụ, không dùng EventUpdated chung chung.
- **schemaVersion:** phiên bản hợp đồng mà consumer cần hỗ trợ.
- **occurredAt:** thời điểm fact được owner ghi nhận.
- **publishedAt:** thời điểm thông điệp ra broker; có thể muộn hơn.
- **aggregateId/version:** hỗ trợ xử lý đúng thứ tự thay đổi trong cùng aggregate.
- **correlationId:** liên kết các bước trong cùng yêu cầu/workflow.
- **causationId:** định danh lệnh hoặc sự kiện trực tiếp dẫn đến thông điệp.
- **payload:** dữ liệu đủ cho consumer, hạn chế lộ dữ liệu riêng tư hoặc domain object nội bộ.

Một timestamp không đủ chứng minh thứ tự nhân quả vì clock giữa service có thể lệch. Các bản ghi cần version/sequence và quy tắc xử lý riêng khi yêu cầu ordering nghiêm ngặt.

## 14. Tương thích ngược giữa các phiên bản

Event hay API đều là hợp đồng, dù vận chuyển bằng broker hay HTTP.

Ví dụ event v1:

~~~json
{
  "eventType": "OrderPlaced",
  "schemaVersion": 1,
  "orderId": "ord-1001",
  "totalMinor": 159900,
  "currency": "VND"
}
~~~

Nếu producer bổ sung trường discountBreakdown tùy chọn, consumer cũ có thể tiếp tục hoạt động nếu parser cho phép trường mới. Nhưng nếu đổi kiểu totalMinor thành object hoặc đổi nghĩa từ “đã giảm giá” sang “trước giảm giá”, consumer cũ có thể đọc sai tiền dù không crash.

Nguyên tắc:

1. Ưu tiên thêm trường một cách tương thích, xác định giá trị mặc định.
2. Không âm thầm đổi semantics của field/eventType đã công bố.
3. Thử các tổ hợp consumer cũ với producer mới và ngược lại trong cửa sổ rolling update.
4. Chọn chiến lược version hoặc dual-publish/dual-read khi có breaking change.
5. Nếu dual-publish hai format của cùng một fact, dùng identity chung để không xử lý side effect hai lần.
6. Tính đến message còn tồn trong queue, retry và DLQ khi bỏ version cũ.
7. Public integration contract ổn định hơn model ORM/private enum, cần tách mapping rõ.

**Giảm coupling thời gian không xóa coupling hợp đồng.** Event broker giúp publisher không phải chờ subscriber xử lý, nhưng schema và ý nghĩa phải có chính sách evolution để giữ khả năng triển khai độc lập.

## 15. Quy tắc ownership và phát thông điệp

Ví dụ trách nhiệm:

| Owner | Command nhận | Event có quyền công bố |
| --- | --- | --- |
| Ordering | PlaceOrder, ConfirmOrder, CancelOrder | OrderPlaced, OrderConfirmed, OrderCancelled |
| Inventory | ReserveStock, ReleaseReservation | StockReserved, ReservationReleased |
| Payments | AuthorizePayment, CapturePayment, RefundPayment | PaymentAuthorized, PaymentCaptured, PaymentRefunded |
| Shipping | CreateShipment, DispatchShipment | ShipmentCreated, ShipmentDispatched |
| Notifications | SendReceiptEmail | ReceiptEmailDispatched |

Service Analytics có thể nhận event OrderPlaced và cập nhật báo cáo của mình; nó không nên tự phát một event OrderConfirmed vì đơn thuộc Ordering.

Nếu một subscriber muốn kích hoạt thay đổi trong service khác, subscriber gửi **command đến owner** thay vì chỉnh trực tiếp database của owner. Khi một service xử lý event rồi sinh command, chỉ nên làm những việc thuộc trách nhiệm của nó; ràng buộc nghiệp vụ của owner vẫn phải được kiểm tra ở owner.

## 16. Đoạn mã Java minh họa ngữ nghĩa

Các record sau phân biệt command và event, không gắn cố định vào công nghệ transport:

~~~java
import java.time.Instant;
import java.util.List;
import java.util.UUID;

public record OrderItem(String sku, int quantity) {}

public record PlaceOrder(
    UUID commandId,
    UUID orderId,
    UUID customerId,
    List<OrderItem> items
) {}

public record OrderPlaced(
    UUID eventId,
    UUID orderId,
    UUID customerId,
    Instant occurredAt,
    long orderVersion
) {}

public record PlaceOrderResult(
    UUID orderId,
    String status
) {}
~~~

Application service minh họa:

~~~java
public final class PlaceOrderHandler {
    private final OrderRepository orders;
    private final Outbox outbox;

    public PlaceOrderHandler(OrderRepository orders, Outbox outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    // Tất cả thao tác persistence chạy trong một local transaction.
    public PlaceOrderResult handle(PlaceOrder command) {
        // Xác thực quyền, validation và idempotency được thực hiện
        // trong application/persistence theo hợp đồng đã thiết kế.
        Order order = Order.create(
            command.orderId(), command.customerId(), command.items());

        orders.save(order);
        outbox.add(new OrderPlaced(
            UUID.randomUUID(), order.id(), order.customerId(),
            Instant.now(), order.version()));

        return new PlaceOrderResult(order.id(), order.status().name());
    }
}
~~~

Các interface và class Order, OrderRepository, Outbox chỉ là ví dụ; mã không phải ứng dụng đầy đủ độc lập. Triển khai thực tế phải có transaction boundary, unique constraints/idempotency, kiểm tra optimistic lock, serialization, handler từ transport và test.

Điểm chủ chốt: command đi vào handler của owner; handler áp dụng luật miền và lưu state; integration event được ghi trong cùng transaction để phát sau khi thành công. Không cho consumer tự sửa Order chỉ vì nó nhận OrderPlaced.

## 17. Quan sát một workflow phân tán

Một thao tác checkout có thể sinh nhiều bản tin:

~~~text
traceId: trace-checkout-88
  HTTP POST /orders
    commandId: cmd-place-10
      eventId: evt-order-10
        commandId: cmd-reserve-11
          eventId: evt-stock-11
        commandId: cmd-payment-12
          eventId: evt-payment-12
~~~

Sử dụng distributed tracing, message headers và log có cấu trúc khi hạ tầng hỗ trợ. Thông tin hữu ích gồm service name, command/event ID, correlation/causation ID, aggregate ID, outcome, latency, retry count, schema version, consumer lag và outbox age.

Không log toàn bộ payment credentials, token hoặc dữ liệu cá nhân nhạy cảm. Quan sát **business completion time** từ accepted đến completed, ngoài HTTP response latency. Khi một bước bị kẹt, cần tra được operation/saga state và bước retry hoặc compensation đã làm.

Các chỉ số vận hành có thể gồm tỷ lệ business rejection, lỗi kỹ thuật, số event ở DLQ, thời gian consumer lag, số message duplicate được loại bỏ, số saga quá hạn và tỷ lệ command hoàn tất.

## 18. Phản ví dụ thường gặp

**Dùng event làm command trá hình.** Ordering phát NeedToChargeCustomer rồi giả định Payment sẽ thu tiền, không định nghĩa ai xử lý, idempotency hoặc kết quả. Nếu muốn một owner thực thi nhiệm vụ, hãy mô hình CapturePayment command với hợp đồng rõ.

**Dùng command làm broadcast event.** CRM gửi UpdateCustomerStatus cho năm service để tất cả tự sửa bản sao “status”. Nếu CRM đã đổi trạng thái và công bố fact, event CustomerStatusChanged với owner rõ ràng phù hợp hơn; từng consumer quyết định hành vi của mình.

**Nhầm HTTP 202 với completed.** Client thấy 202 và hiển thị “thanh toán thành công”. Đúng hơn cần status ACCEPTED/PENDING, endpoint tra cứu và event hoàn tất thực sự.

**Tin rằng không có response tức không cần theo dõi kết quả.** Fire-and-forget một command quan trọng có thể bị mất, hết hạn hoặc từ chối. Thiết kế durability, trạng thái operation và chính sách retry.

**Publish event trước khi commit.** Consumer thấy OrderConfirmed dù Order rollback. Phát event theo trạng thái đã cam kết, sử dụng outbox khi cần.

**Nhầm schema hợp lệ với semantics đúng.** Consumer parse field PAID nhưng owner đã đổi nghĩa từ captured sang authorized. Thay đổi này có thể dẫn đến giao hàng khi tiền chưa thực sự thu.

**Đẩy toàn bộ entity lên event.** Thay đổi cột ORM làm các consumer phụ thuộc cấu trúc nội bộ và có thể lộ dữ liệu. Dùng integration schema ổn định với dữ liệu tối thiểu.

**Đặt mọi hành động trên hàng đợi dù cần trả dữ liệu ngay.** Request/reply trên broker làm tăng correlation, timeout và vận hành nếu không có nhu cầu tải/độ bền cụ thể.

**Lấy event làm bằng chứng consumer đã xử lý.** Event OrderPlaced chỉ xác nhận Ordering đã ghi nhận đơn; nó không chứng minh Notifications đã gửi email, Inventory đã giữ hàng hay Payments đã thanh toán.

**Không nghĩ tới replay.** Consumer cập nhật doanh thu từ PaymentCaptured rồi khi replay message cộng thêm lần nữa. Idempotency/projection rebuild cần là trách nhiệm tường minh.

## 19. Bảng lựa chọn trong thực tế

| Nhu cầu | Mẫu phù hợp | Lưu ý |
| --- | --- | --- |
| Tra cứu chi tiết sản phẩm | Query qua request–response | Latency, freshness và cache |
| Tạo đơn nhanh bằng local transaction | Command qua HTTP request–response | Idempotency, 201 sau commit |
| Tạo báo cáo dài | Async command qua queue | Job ID và trạng thái hoàn tất |
| Ghi nhận thanh toán ở service chủ sở hữu | Command CapturePayment | Transaction, gateway idempotency |
| Thông báo đã thu tiền | Event PaymentCaptured | Chỉ phát từ Payments sau fact được xác nhận |
| Giữ hàng với tranh chấp tồn kho | ReserveStock command | Lock/conditional update bảo vệ invariant |
| Đồng bộ dashboard | Event-driven projection | Eventual consistency và replay |
| Gửi email cho một đơn đã tạo | Command SendEmail trong Notifications | Chống gửi trùng theo business key |
| Thông báo khách đã đăng ký | Event CustomerRegistered | Subscriber chọn hành vi riêng |
| Điều phối thanh toán và vận đơn | Saga dùng command + event | Timeout, compensation, reconcile |
| Kiểm tra trạng thái authoritative | Query trực tiếp owner | Không ép read model hội tụ tức thì |
| Public webhook nhận payment event | Event qua HTTP + ACK | Verify signature, replay protection |

Đây là gợi ý thiết kế, không phải lệnh buộc chọn một công nghệ. Một command ngắn có thể chạy qua queue vì tải; một event cũng có thể được phân phối bằng HTTP.

## 20. Kiểm thử theo ngữ nghĩa

### Unit tests

- Command bị từ chối khi invariant vi phạm, không ghi trạng thái mới.
- Cùng commandId lặp lại không nhân đôi side effect.
- Cùng idempotency key nhưng payload khác bị từ chối.
- Event handler bỏ qua event đã xử lý.
- Event version cũ hơn state hiện tại không ghi đè kết quả mới theo chính sách.
- Command thành công phát đúng một **logical event** với dữ liệu đúng; publish vật lý có thể lặp.

### Contract tests

- Query response và command response giữ schema/semantics đã cam kết.
- Producer event mới vẫn được consumer cũ đọc trong rollout nếu contract hứa hỗ trợ.
- Consumer mới nhận được event còn tồn trong queue theo schema cũ.
- HTTP 201, 202, 409, 422 có ý nghĩa rõ ràng theo từng API.
- Các message có ID và version cần thiết để dedup, trace, migration.

### Integration tests

- Transaction rollback thì outbox record cũng rollback.
- Crash sau DB commit nhưng trước broker ACK không gây double effect.
- Hai command đồng thời tranh cùng aggregate không phá invariant.
- Payment gateway timeout sau capture được reconcile mà không thu lại lần hai.
- Event sai thứ tự hoặc đến trễ có đường xử lý được kiểm chứng.
- Saga có thể bù trừ khi một bước hoàn tất nhưng bước sau thất bại.

### End-to-end tests

Người dùng tạo Order và UI hiển thị PENDING khi mới accepted; chỉ hiển thị CONFIRMED khi nghiệp vụ có đủ điều kiện. Khi hết tồn hoặc payment bị từ chối, trạng thái và thông báo phải phù hợp, không có đơn ảo hoặc khoản thanh toán trùng. Với xử lý async, test cả đường phục hồi sau outage và khả năng truy vết theo operationId.

## 21. Mẫu tài liệu hóa cho từng thông điệp

Trước khi xây một endpoint/topic, nhóm phát triển có thể ghi:

~~~text
Name: ReserveStock
Semantic: COMMAND
Owner: Inventory
Sender: OrderWorkflow
Transport: queue (competing consumers)
Business key: orderId + reservationAttempt
Command ID: cmd-reserve-771
Preconditions: quantity > 0, chưa hết hạn, slot tồn còn khả dụng
Success: StockReserved (integration event)
Rejection: ReservationRejected (business outcome)
Retryable errors: temporary database/broker error
Idempotency: unique business operation key
Timeout: reservation deadline
Consistency: local Inventory transaction + outbox
Observability: correlationId, causationId, commandId, lag
Schema version: 1
~~~

Và event tương ứng:

~~~text
Name: StockReserved
Semantic: INTEGRATION EVENT
Owner/producer: Inventory
Fact: reservation đã commit
Consumers: OrderWorkflow, Analytics nếu cần
Identity: eventId, reservationId
OccurredAt: do Inventory ghi nhận
Ordering: xử lý theo reservation version nếu cần
Delivery: có thể trùng, đến muộn
Schema: version 1, có chính sách evolution
Outbox: được ghi cùng local transaction giữ tồn
Consumer responsibility: idempotency, workflow state, retry
~~~

Bảng mô tả command/event phải có **owner, ngữ nghĩa, trạng thái hoàn tất, error contract và bảo đảm khi nhận lại**. Không dừng ở tên topic hoặc loại broker.

## 22. Bài tập áp dụng: đặt lịch có thanh toán

Một nền tảng cho phép đặt lịch tư vấn. Scheduling quản lý slot, Payments thu tiền, Notifications gửi xác nhận. Yêu cầu:

1. Khách cần tra slot trống trong vòng hai giây.
2. Khi bấm xác nhận, hệ thống giữ slot tối đa mười phút.
3. Không được double-booking cùng slot.
4. Hết hạn thanh toán thì giải phóng slot.
5. Tiền đã thu nhưng giữ slot thất bại phải có bù trừ/hoàn tiền theo chính sách.
6. Email xác nhận được gửi một lần theo nghiệp vụ.

Phân loại các thông điệp:

| Tương tác | Ý nghĩa | Cơ chế gợi ý |
| --- | --- | --- |
| GetAvailableSlots | Query | Request–response tới Scheduling |
| HoldSlot | Command | HTTP hoặc queue tới Scheduling |
| SlotHeld | Event | Publish từ Scheduling |
| CapturePayment | Command | Payments xử lý, có idempotency |
| PaymentCaptured | Event | Publish từ Payments |
| ReleaseSlot | Command | Scheduling xử lý |
| HoldExpired | Event | Fact do Scheduling công bố |
| SendBookingConfirmation | Command | Notifications xử lý qua queue |
| ConfirmationDispatched | Event | Fact do Notifications công bố |

Bài mở rộng: Nếu HoldSlot được gửi hai lần cùng business key, scheduling có tạo hai reservation không? Nếu PaymentCaptured đến sau HoldExpired thì process manager phải làm gì? Nếu Notifications xử lý xong nhưng crash trước ACK, email có bị gửi hai lần không? Những câu hỏi này đòi hỏi xác định owner, transaction, ID, state, retry và compensation, chứ không thể trả lời chỉ bằng câu “dùng Kafka”.

## 23. Checklist ra quyết định

1. Đây là một yêu cầu thông tin, một ý định hành động hay một thông báo sự thật?
2. Service nào sở hữu dữ liệu và bất biến có liên quan?
3. Người gửi cần câu trả lời ngay hay chỉ cần theo dõi việc xử lý về sau?
4. Mức thành công nào đang được hứa: transport ACK, accepted hay completed?
5. Hành động có thể hoàn tất trong một local transaction không?
6. Có nguy cơ gửi trùng, retry sau timeout hoặc xử lý concurrent không?
7. Idempotency key được scope và lưu bao lâu?
8. Nếu producer commit nhưng publish thất bại, cơ chế outbox có bảo vệ không?
9. Event consumer có chịu được duplicate, delay, out-of-order và replay không?
10. Schema và semantics của API/message có tương thích khi deploy lệch version?
11. Có cần state machine/saga để theo dõi workflow liên service không?
12. Nếu một bước thất bại, command bù trừ, deadline và owner xử lý là ai?
13. Có operationId, trace/correlation ID, logs, metrics và cảnh báo không?
14. Dữ liệu nhạy cảm trong request/event được kiểm soát như thế nào?
15. Có kiểm thử lỗi, rollback và recovery bên cạnh happy path không?

---

**Nguyên tắc cần nhớ:** **Request–response** mô tả việc hỏi và nhận lời đáp; **command** yêu cầu owner thực hiện hành động; **event** công bố điều đã xảy ra. Chúng là những khái niệm có thể kết hợp trong một workflow microservices. Thiết kế đúng phải bắt đầu từ nghĩa vụ nghiệp vụ, quyền sở hữu trạng thái, yêu cầu thời gian và cơ chế phục hồi, rồi mới quyết định dùng HTTP, gRPC hay message broker.
# Giao dịch xuyên ranh giới

## Giao dịch xuyên ranh giới trong tích hợp ứng dụng là gì?

Một DSL (domain-specific language) thường được nhúng vào một ứng dụng host để mô tả rule, workflow, truy vấn, hành động hoặc quy trình nghiệp vụ. Khi DSL thực thi, nó có thể tương tác với nhiều thành phần: dữ liệu trong bộ nhớ, database của host, message broker, API bên ngoài, filesystem, dịch vụ thanh toán hoặc hệ thống triển khai.

Một **giao dịch xuyên ranh giới (cross-boundary transaction)** là một đơn vị công việc có các bước tác động đến nhiều thành phần hoặc nhiều phạm vi quản lý giao dịch khác nhau. Ví dụ, một workflow được mô tả bằng DSL có thể cập nhật đơn hàng trong database, giữ chỗ tồn kho ở service khác, yêu cầu thanh toán qua cổng bên ngoài rồi phát event cho hệ thống giao hàng.

Vấn đề cốt lõi là các thành phần này không nhất thiết dùng chung một transaction manager hoặc cùng một cơ chế rollback. Database có thể hỗ trợ ACID transaction, nhưng HTTP API của một nhà cung cấp thanh toán không thể tự động tham gia transaction đó. Message broker có thể nhận event sau khi database commit, nhưng hai thao tác này thường không nằm trong cùng một transaction nếu hệ thống không có cơ chế tích hợp phù hợp.

Ví dụ, một DSL mô tả việc xác nhận đơn hàng:

~~~text
WORKFLOW confirmOrder(orderId) {
  order = orders.load(orderId)
  inventory.reserve(order.items)
  payment.capture(order.paymentIntent)
  orders.markConfirmed(orderId)
  events.publish("order.confirmed", orderId)
}
~~~

Nếu inventory reservation thành công nhưng payment capture thất bại, hệ thống cần biết phải làm gì với reservation. Nếu payment capture thành công nhưng database commit thất bại, khách hàng có thể bị trừ tiền trong khi đơn hàng vẫn ở trạng thái chưa xác nhận. Nếu database commit thành công nhưng event publish thất bại, hệ thống giao hàng có thể không nhận được thông tin đơn hàng.

Một transaction xuyên ranh giới cần trả lời các câu hỏi:

- Những thao tác nào thuộc cùng một đơn vị nghiệp vụ?
- Ranh giới nào có thể commit hoặc rollback nguyên tử?
- Thành phần nào sở hữu transaction?
- Khi một bước thành công và bước sau thất bại, có thể hoàn tác hay cần compensation?
- Retry có thể chạy lại một action đã thành công hay không?
- Làm sao tránh xử lý event hoặc command trùng lặp?
- Khi process hoặc network bị gián đoạn, trạng thái được phục hồi thế nào?
- Người vận hành có thể biết transaction đang ở bước nào và vì sao thất bại không?

Trong DSL tích hợp ứng dụng, các câu hỏi này phải được phản ánh trong semantics của action, transaction scope, retry, compensation và persistence. Không thể chỉ bao toàn bộ workflow trong một khối TRANSACTION rồi giả định mọi side effect bên ngoài đều rollback được.

## Vì sao ranh giới giao dịch quan trọng?

Một ranh giới giao dịch xác định phạm vi mà hệ thống có thể bảo đảm một tập thay đổi được commit hoặc hủy theo một quy tắc nhất quán. Khi một workflow đi qua nhiều ranh giới, bảo đảm đó có thể thay đổi.

Các ranh giới phổ biến gồm:

- **Ranh giới bộ nhớ:** một biểu thức hoặc một lần đánh giá DSL.
- **Ranh giới runtime:** một invocation của interpreter hoặc workflow engine.
- **Ranh giới ứng dụng:** một request hoặc một use case của host.
- **Ranh giới database:** một transaction trên một database connection.
- **Ranh giới dịch vụ:** một API call đến service độc lập.
- **Ranh giới message:** publish hoặc consume message qua broker.
- **Ranh giới tài nguyên:** ghi file, upload object, tạo cloud resource hoặc gọi command.
- **Ranh giới thời gian:** một workflow kéo dài qua nhiều request, process restart hoặc nhiều ngày.

Một thao tác có thể đi qua nhiều ranh giới cùng lúc. Ví dụ, một request HTTP gọi host application, host mở database transaction, DSL gọi một function, function gọi service ngoài, rồi workflow phát event qua broker.

### Ranh giới kỹ thuật và ranh giới nghiệp vụ

Ranh giới kỹ thuật mô tả thành phần nào quản lý commit. Ranh giới nghiệp vụ mô tả các hành động nào cần được xem là một mục tiêu có ý nghĩa.

Ví dụ, đặt hàng có thể gồm:
1. Tạo order record.
2. Reserve inventory.
3. Capture payment.
4. Tạo shipment.
5. Gửi confirmation.

Về kỹ thuật, mỗi bước có thể thuộc một hệ thống khác nhau. Về nghiệp vụ, chúng cùng phục vụ một mục tiêu: xác nhận đơn hàng. Một giao dịch nghiệp vụ dài như vậy thường cần orchestration và compensation thay vì một database transaction duy nhất.

### Vì sao không thể rollback mọi thứ?

Rollback database có thể hủy các thay đổi chưa commit trên database đó. Nó không thể tự động:
- Thu hồi email đã gửi.
- Xóa message đã được consumer xử lý.
- Hoàn tác payment đã capture.
- Thu hồi một HTTP request đã được service khác thực hiện.
- Xóa file đã được tải về máy khác.
- Đảo ngược hành động của một người dùng.
- Khôi phục trạng thái cloud resource nếu thao tác ngoài hệ thống đã hoàn tất.

Với side effect bên ngoài, hệ thống thường cần một hành động bù trừ (compensation), hoặc cần thiết kế bước thực thi sao cho có thể retry an toàn.

## ACID và giới hạn của transaction cục bộ

ACID mô tả các thuộc tính quan trọng của transaction database:

- **Atomicity:** các thay đổi trong transaction được commit cùng nhau hoặc bị rollback.
- **Consistency:** transaction giữ các constraint và invariant đã định nghĩa.
- **Isolation:** các transaction đồng thời không nhìn thấy trạng thái trung gian theo isolation level.
- **Durability:** dữ liệu đã commit được lưu bền vững theo bảo đảm của database.

Ví dụ:

~~~text
BEGIN TRANSACTION

UPDATE accounts
SET balance = balance - 100
WHERE id = "A"

UPDATE accounts
SET balance = balance + 100
WHERE id = "B"

COMMIT
~~~

Nếu một câu lệnh thất bại trước commit, database có thể rollback cả hai thay đổi. Đây là transaction cục bộ trên cùng một transaction manager.

### Local transaction

Local transaction thường thuộc một database hoặc một resource manager. Host application có thể mở transaction, thực hiện nhiều repository operation rồi commit hoặc rollback.

DSL có thể tham gia transaction hiện tại bằng cách gọi host service sử dụng cùng connection hoặc transaction context. Điều đó chỉ đúng nếu host bindings được thiết kế để chia sẻ transaction một cách rõ ràng.

### Transaction boundary không đồng nghĩa với function boundary

Một function DSL có thể gọi nhiều host API. Một API có thể mở transaction riêng. Nếu không định nghĩa rõ, người viết DSL có thể nghĩ các action trong cùng một block là atomic dù thực tế mỗi action commit riêng.

Ngược lại, nhiều function có thể cùng tham gia transaction do host quản lý. Khi đó, transaction scope cần được truyền qua context và được giữ nhất quán.

### Consistency là gì?

Consistency không có nghĩa mọi hệ thống bên ngoài luôn cập nhật cùng một thời điểm. Nó có nghĩa các invariant được bảo đảm theo contract của hệ thống.

Với workflow phân tán, có thể tồn tại khoảng thời gian order đã được tạo nhưng payment chưa capture. Trạng thái trung gian này phải được mô hình hóa hợp lệ, ví dụ OrderPendingPayment. Nếu hệ thống không cho phép trạng thái trung gian, nó cần một cơ chế commit mạnh hơn hoặc một thiết kế khác.

## Phân loại transaction theo phạm vi

Có thể phân loại giao dịch theo số resource manager và thời gian tồn tại.

| Loại | Phạm vi | Cách xử lý thường gặp |
|---|---|---|
| In-memory transaction | Một lần đánh giá hoặc state snapshot | Copy-on-write, undo log |
| Local database transaction | Một database | ACID, commit/rollback |
| Multi-resource transaction | Nhiều resource manager hỗ trợ phối hợp | Two-phase commit hoặc XA |
| Distributed business transaction | Nhiều service độc lập | Saga, compensation, outbox |
| Long-running transaction | Nhiều bước và kéo dài theo thời gian | Durable workflow, state machine |
| File/resource transaction | Database kết hợp file hoặc object store | Staging, atomic rename, manifest |
| Event-driven transaction | Database và message broker | Transactional outbox/inbox, CDC |

Không nên chọn cơ chế chỉ dựa vào tên gọi. Cần xem resource có hỗ trợ transaction protocol chung hay không, thời gian thực thi, yêu cầu consistency và khả năng compensation.

## Transaction context trong DSL và host application

Để DSL tham gia transaction của host, runtime cần một cách biểu diễn transaction context.

Ví dụ:

~~~text
ExecutionContext
  principal
  tenant
  requestId
  transaction
  cancellationToken
  clock
  services
~~~

Transaction context có thể chứa handle hoặc abstraction cho transaction hiện tại. DSL thường không cần thao tác trực tiếp với connection; nó cần gọi các host API đã được cấu hình để tham gia transaction.

### Ai sở hữu transaction?

Cần xác định một thành phần có trách nhiệm bắt đầu, commit và rollback:

- Host request handler.
- Application service.
- Workflow engine.
- Transaction coordinator.
- Một resource adapter chuyên biệt.

Nếu DSL tự mở transaction trong khi host cũng đang quản lý transaction, có thể xảy ra nested transaction hoặc commit ngoài dự kiến. Một contract rõ cần nói ai là owner và ai chỉ tham gia.

### Propagation

Transaction propagation quy định một function hoặc action xử lý transaction hiện có thế nào khi được gọi.

Các chế độ thường gặp:

| Chế độ | Hành vi khái niệm |
|---|---|
| REQUIRED | Tham gia transaction hiện tại; nếu chưa có thì tạo mới |
| REQUIRES_NEW | Tạm treo transaction hiện tại và tạo transaction mới |
| SUPPORTS | Tham gia nếu có; nếu không thì chạy không transaction |
| MANDATORY | Yêu cầu phải có transaction hiện tại |
| NEVER | Từ chối nếu đang có transaction |
| NOT_SUPPORTED | Tạm treo transaction và chạy ngoài transaction |
| NESTED | Dùng nested scope hoặc savepoint nếu resource hỗ trợ |

Tên và semantics phụ thuộc framework. DSL cần dùng một vocabulary thống nhất hoặc ẩn chi tiết propagation sau host API.

### REQUIRES_NEW và dữ liệu chưa commit

Một transaction mới thường không nhìn thấy thay đổi chưa commit của transaction bên ngoài. Nếu DSL gọi action REQUIRES_NEW để ghi audit trước khi transaction cha commit, audit có thể tồn tại ngay cả khi transaction cha rollback. Điều đó có thể đúng với audit attempt, nhưng không đúng nếu audit mô tả một nghiệp vụ đã hoàn tất.

### Context propagation qua async boundary

Transaction thường gắn với thread hoặc execution context cụ thể. Khi DSL tạo task bất đồng bộ, transaction context có thể không được truyền hoặc không còn hợp lệ.

Không nên mặc định mang database connection đang mở sang thread khác. Có thể:
- Hoàn tất transaction cục bộ trước khi enqueue task.
- Truyền dữ liệu cần thiết thay vì connection.
- Mở transaction mới trong worker.
- Dùng workflow state bền vững để điều phối bước tiếp theo.

### Transaction timeout

Transaction context cần có timeout hoặc deadline. Một DSL script chạy lâu có thể giữ lock và connection quá lâu. Host nên giới hạn thời gian và hủy hoặc rollback khi vượt ngưỡng, đồng thời đảm bảo cancellation được truyền xuống các operation có thể hủy.

## DSL syntax cho transaction scope

Một DSL có thể cung cấp cú pháp tường minh:

~~~text
TRANSACTION {
  orderRepository.insert(order)
  inventoryRepository.reserve(order.items)
  orderRepository.markReserved(order.id)
}
~~~

Cú pháp này chỉ nên được hỗ trợ nếu các operation bên trong thực sự tham gia cùng transaction manager. Nếu inventoryRepository là service từ xa, khối trên không tự biến HTTP call thành thao tác rollback được.

### Transaction declaration

Một khai báo có thể mô tả phạm vi và policy:

~~~text
TRANSACTION orderCreation {
  SCOPE LOCAL
  PROPAGATION REQUIRED
  ISOLATION READ_COMMITTED
  TIMEOUT 5 SECONDS

  DO {
    orderRepository.insert(order)
    auditRepository.recordCreation(order.id)
  }
}
~~~

Các trường như isolation và timeout cần được map sang khả năng của host database. Nếu backend không hỗ trợ yêu cầu, compiler hoặc runtime phải báo lỗi thay vì âm thầm bỏ qua.

### Action metadata

Mỗi host action nên khai báo metadata:

~~~text
HOST_ACTION orderRepository.insert(order) {
  TRANSACTIONAL
  IDEMPOTENT
  RESOURCE database.orders
}

HOST_ACTION payment.capture(intentId) {
  NON_TRANSACTIONAL
  IDEMPOTENCY_KEY REQUIRED
  COMPENSATION payment.refund
}
~~~

Metadata giúp planner biết action nào tham gia transaction, action nào có side effect không thể rollback trực tiếp và action nào cần idempotency key.

### Static validation

Compiler hoặc analyzer có thể cảnh báo:
- Transaction block chứa action non-transactional.
- Action yêu cầu transaction nhưng được gọi ngoài scope.
- Async boundary làm mất transaction context.
- Action có side effect nhưng thiếu retry/compensation policy.
- Transaction scope quá rộng hoặc timeout không hợp lý.
- Có nested scope không được host hỗ trợ.

Static analysis không thể biết mọi behavior của plugin động, vì vậy runtime vẫn phải enforce contract.

## Nhiều resource manager và Two-Phase Commit

Nếu nhiều resource manager hỗ trợ cùng một distributed transaction protocol, có thể phối hợp commit bằng Two-Phase Commit (2PC).

Các vai trò chính:
- Coordinator: điều phối transaction.
- Participants: các resource manager tham gia.
- Transaction ID: định danh transaction xuyên các participant.

### Phase 1: Prepare

Coordinator yêu cầu mọi participant chuẩn bị commit. Mỗi participant kiểm tra có thể commit và giữ đủ trạng thái cần thiết để hoàn tất sau đó.

~~~text
Coordinator -> Participant A: PREPARE
Coordinator -> Participant B: PREPARE
Participant A -> Coordinator: READY
Participant B -> Coordinator: READY
~~~

Nếu tất cả participant trả READY, coordinator có thể quyết định commit. Nếu có participant từ chối hoặc gặp lỗi theo protocol, coordinator quyết định rollback.

### Phase 2: Commit hoặc rollback

~~~text
Coordinator -> Participant A: COMMIT
Coordinator -> Participant B: COMMIT
~~~

Nếu prepare không thành công:

~~~text
Coordinator -> Participant A: ROLLBACK
Coordinator -> Participant B: ROLLBACK
~~~

Participant phải lưu trạng thái prepared bền vững để có thể hoàn tất sau khi coordinator phục hồi.

### Ưu điểm

- Có thể đạt atomic commit giữa các resource manager tương thích.
- Ứng dụng có mô hình commit/rollback gần với transaction cục bộ.
- Phù hợp một số môi trường enterprise có transaction manager hỗ trợ XA.

### Hạn chế

- Participant phải hỗ trợ protocol phù hợp.
- Transaction có thể giữ lock hoặc resource trong thời gian dài.
- Coordinator trở thành thành phần quan trọng cần phục hồi.
- Participant có thể ở trạng thái prepared và chờ quyết định.
- Network partition có thể làm transaction bị block.
- Nhiều HTTP API hoặc SaaS service không hỗ trợ XA.
- Vận hành và troubleshooting phức tạp.

### Khi nào nên dùng 2PC?

2PC có thể phù hợp khi tất cả resource manager hỗ trợ cùng transaction protocol, yêu cầu atomicity mạnh là bắt buộc và tổ chức chấp nhận chi phí vận hành. Nó thường không phải lựa chọn mặc định cho workflow đi qua nhiều microservice độc lập.

### XA và transaction manager

XA là một chuẩn giao tiếp cho distributed transaction giữa transaction manager và resource manager. Host có thể dùng JTA hoặc transaction manager tương ứng để điều phối resource hỗ trợ XA.

DSL không nên tự triển khai XA protocol. Nó chỉ nên khai báo transaction scope theo abstraction của host. Việc enlist resource, prepare, commit và recovery thuộc transaction infrastructure.

## Saga cho giao dịch nghiệp vụ phân tán

Khi các service không hỗ trợ distributed transaction chung, Saga là một mẫu phổ biến. Một saga chia nghiệp vụ thành nhiều local transaction. Mỗi bước commit độc lập và có thể có một compensation tương ứng.

Ví dụ đặt hàng:

~~~text
CreateOrder
    |
    v
ReserveInventory
    |
    v
CapturePayment
    |
    v
CreateShipment
    |
    v
ConfirmOrder
~~~

Nếu CreateShipment thất bại sau khi payment đã capture, saga có thể:
1. RefundPayment.
2. ReleaseInventory.
3. MarkOrderFailed hoặc ManualReview.

### Local transaction và compensation

Mỗi bước saga nên thực hiện một local transaction có ranh giới rõ. Compensation là hành động nghiệp vụ bù trừ, không phải rollback kỹ thuật.

Ví dụ:
- ReserveInventory được bù bằng ReleaseInventory.
- CapturePayment được bù bằng RefundPayment.
- CreateShipment được bù bằng CancelShipment nếu hãng vận chuyển còn cho phép.

Compensation có thể thất bại, có thể cần retry và có thể không khôi phục chính xác trạng thái ban đầu. Vì vậy, saga cần state để theo dõi bước đã hoàn thành và compensation đang chờ.

### Orchestration

Trong orchestration, một coordinator hoặc workflow engine quyết định bước tiếp theo:

~~~text
SAGA checkout {
  STEP reserveInventory {
    DO inventory.reserve(order.items)
    COMPENSATE inventory.release(order.items)
  }

  STEP capturePayment {
    DO payment.capture(order.paymentIntent)
    COMPENSATE payment.refund(order.paymentId)
  }

  STEP createShipment {
    DO shipping.create(order)
    COMPENSATE shipping.cancel(order.shipmentId)
  }
}
~~~

Orchestrator lưu trạng thái saga và phát command đến service. Nó phù hợp khi luồng nghiệp vụ có nhiều nhánh, timeout và recovery cần được quản lý tập trung.

### Choreography

Trong choreography, mỗi service phản ứng với event từ service trước rồi phát event tiếp theo. Không có một coordinator điều khiển toàn bộ luồng.

Ví dụ:
- OrderCreated kích hoạt inventory service.
- InventoryReserved kích hoạt payment service.
- PaymentCaptured kích hoạt shipping service.
- ShipmentCreated kích hoạt order service để xác nhận.

Choreography giảm sự phụ thuộc vào coordinator nhưng luồng tổng thể khó quan sát hơn khi có nhiều event và nhánh. Cần correlation, event schema, idempotency và tracing xuyên service.

### Chọn orchestration hay choreography

| Tiêu chí | Orchestration | Choreography |
|---|---|---|
| Điều khiển flow | Tập trung tại coordinator | Phân tán theo event |
| Quan sát toàn luồng | Thường dễ hơn | Cần tracing và event correlation |
| Coupling | Service biết coordinator | Service phụ thuộc event contract |
| Nhánh và compensation | Dễ mô hình hóa tập trung | Có thể phức tạp khi flow lớn |
| Failure recovery | Coordinator quản lý state | Mỗi participant và event flow tự xử lý |
| Phù hợp | Quy trình dài, nhiều bước, cần audit | Luồng event đơn giản, loosely coupled |

Không có lựa chọn phù hợp cho mọi hệ thống. Một DSL workflow thường hỗ trợ orchestration tốt; một event DSL hoặc integration DSL có thể mô tả choreography.

## Transactional Outbox

Một lỗi phổ biến là cập nhật database rồi publish event trong hai thao tác độc lập:

~~~text
BEGIN
  UPDATE orders SET status = "CONFIRMED"
COMMIT

PUBLISH "order.confirmed"
~~~

Nếu database commit thành công nhưng publish thất bại, dữ liệu và message bị lệch. Nếu publish thành công nhưng database rollback, consumer có thể nhận một event cho nghiệp vụ chưa commit.

Transactional Outbox giải quyết vấn đề bằng cách ghi business data và event record vào cùng database transaction.

~~~text
BEGIN TRANSACTION
  UPDATE orders SET status = "CONFIRMED"
  INSERT INTO outbox(event_id, event_type, payload, status)
COMMIT
~~~

Một publisher nền đọc outbox và gửi event đến broker. Sau khi gửi, nó đánh dấu record đã publish hoặc lưu trạng thái tương ứng.

### Ưu điểm

- Business update và ý định phát event được commit nguyên tử trong cùng database.
- Nếu process crash sau commit, outbox record vẫn còn để publisher xử lý.
- Có thể retry publish khi broker tạm thời không khả dụng.
- Không cần database và broker tham gia 2PC.

### Delivery semantics

Outbox publisher thường có thể gửi lặp nếu crash sau khi broker nhận message nhưng trước khi outbox được đánh dấu published. Vì vậy, consumer cần idempotent processing hoặc inbox deduplication.

Outbox không tự bảo đảm exactly-once delivery. Nó bảo đảm event intent được lưu bền vững cùng business change; delivery thường là at-least-once.

### Polling và Change Data Capture

Publisher có thể polling bảng outbox hoặc dùng CDC đọc transaction log. Polling dễ triển khai nhưng cần quản lý query load và locking. CDC giảm polling nhưng phụ thuộc connector và vận hành log stream.

### Ordering

Nếu thứ tự event quan trọng, outbox cần sequence hoặc aggregate version. Publisher và broker phải giữ ordering theo key phù hợp. Không nên giả định thứ tự toàn cục nếu hệ thống dùng nhiều partition.

## Transactional Inbox và idempotent consumer

Consumer nhận message từ broker có thể xử lý message rồi crash trước khi acknowledge. Broker có thể gửi lại message. Consumer cần tránh áp dụng side effect nhiều lần.

Transactional Inbox lưu message ID đã xử lý cùng business update trong một local transaction:

~~~text
BEGIN TRANSACTION
  INSERT INTO inbox(message_id)
  UPDATE account SET balance = balance + amount
COMMIT
ACK MESSAGE
~~~

Nếu message ID đã tồn tại, consumer nhận ra message duplicate và không lặp business update.

### Inbox key

Inbox key cần định danh ổn định một message trong phạm vi phù hợp. Có thể gồm:
- Producer hoặc source.
- Message ID.
- Consumer hoặc handler.
- Tenant nếu namespace được phân vùng.

Không nên dùng payload hash làm ID duy nhất nếu hai message giống payload vẫn là hai sự kiện nghiệp vụ riêng.

### Idempotent handler

Một handler idempotent có thể được gọi nhiều lần nhưng tạo cùng hiệu ứng cuối cùng. Ví dụ, đặt trạng thái order thành Confirmed có thể idempotent nếu update có điều kiện theo version. Trừ balance một số tiền thường không idempotent nếu không có deduplication.

### Acknowledge timing

Acknowledge trước khi commit business transaction có thể làm mất message nếu process crash sau ack. Acknowledge sau commit có thể tạo duplicate nhưng inbox xử lý được. Vì vậy, thường ưu tiên commit inbox và business state trước rồi mới ack.

## Idempotency cho action xuyên ranh giới

Idempotency là khả năng xử lý cùng một yêu cầu nhiều lần mà không tạo thêm hiệu ứng nghiệp vụ ngoài ý muốn.

Ví dụ, payment.capture được gọi lần đầu thành công nhưng response bị mất do network timeout. Client không biết payment đã capture hay chưa. Nếu retry với một operation mới, khách hàng có thể bị trừ tiền hai lần.

Một idempotency key ổn định giúp service nhận diện retry của cùng một logical operation:

~~~text
payment.capture(
  intentId = "pi-123",
  idempotencyKey = "order-456-capture-v1"
)
~~~

### Quy tắc tạo key

Key nên:
- Gắn với một logical operation.
- Ổn định qua retry.
- Không tái sử dụng cho operation khác.
- Có scope phù hợp theo tenant và service.
- Không chứa secret hoặc dữ liệu nhạy cảm.
- Được lưu đủ lâu theo thời gian retry/reconciliation.

Không nên tạo key mới mỗi lần retry, vì như vậy service sẽ xem mỗi lần là một operation khác.

### Idempotency ở host action

DSL host binding có thể nhận execution ID và step ID để tạo operation key. Nhưng key cần ổn định khi workflow được resume hoặc retry trên worker khác.

### Idempotency và concurrency

Hai request đồng thời cùng dùng một key cần được serialize hoặc xử lý bằng unique constraint. Nếu cả hai cùng thấy key chưa tồn tại rồi thực hiện side effect, deduplication không có tác dụng.

### Kết quả của request lặp

Service cần định nghĩa response khi nhận lại key đã xử lý:
- Trả kết quả ban đầu.
- Trả trạng thái đang xử lý.
- Từ chối nếu payload khác với request ban đầu.
- Cho phép query operation status.

Không nên dùng cùng key cho payload khác nhau mà không phát hiện conflict.

## Consistency model và trạng thái trung gian

Một giao dịch xuyên ranh giới thường không thể làm mọi service cập nhật cùng một thời điểm. Hệ thống cần mô hình hóa consistency và trạng thái trung gian.

### Strong consistency trong một resource

Trong một database transaction, các thay đổi có thể được commit nguyên tử theo isolation level. Các request đọc sau commit thấy trạng thái đã commit theo consistency guarantee của database.

### Eventual consistency

Trong hệ thống event-driven, service khác có thể cập nhật sau khi nhận event. Trong khoảng thời gian đó, hai service có thể nhìn thấy trạng thái khác nhau.

Ví dụ:
- Order đã Confirmed.
- Shipping service chưa nhận OrderConfirmed.
- Shipment chưa được tạo.

Đây có thể là trạng thái hợp lệ tạm thời nếu workflow theo eventual consistency. UI và API cần thể hiện trạng thái ProcessingShipment thay vì giả định mọi service đã đồng bộ.

### Read-your-writes

Một caller có thể cần nhìn thấy thay đổi vừa thực hiện. Nếu đọc từ replica hoặc service downstream chưa nhận event, kết quả có thể cũ. Có thể trả version hoặc operation status để caller theo dõi.

### Monotonic state progression

Workflow nên tránh state quay lùi ngoài ý muốn. Có thể dùng version, transition precondition và state machine để đảm bảo một event cũ không ghi đè trạng thái mới.

### Reconciliation

Vì saga và event delivery có thể gặp lỗi lâu dài, hệ thống cần tiến trình reconciliation:
- Tìm outbox event chưa publish.
- Tìm operation ở trạng thái pending quá lâu.
- So sánh payment provider với order state.
- Tìm reservation chưa release.
- Retry hoặc đưa vào manual review.

Reconciliation là một phần của thiết kế giao dịch, không chỉ là công cụ vận hành bổ sung.

## Isolation, concurrency và optimistic locking

Giao dịch xuyên ranh giới thường kéo dài lâu hơn một database transaction. Giữ lock database trong suốt một workflow kéo dài nhiều phút hoặc nhiều ngày thường không phù hợp.

Thay vào đó, workflow có thể dùng optimistic concurrency.

### Versioned update

Một record có version:

~~~text
Order
  id
  status
  version
~~~

Khi cập nhật:

~~~text
UPDATE orders
SET status = "CONFIRMED",
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion
~~~

Nếu số hàng được cập nhật bằng 0, record đã thay đổi bởi một transaction khác. Workflow cần reload và quyết định tiếp tục, retry hoặc conflict.

### Lost update

Hai process cùng đọc balance 100. Process A trừ 10 và process B trừ 20. Nếu cả hai ghi giá trị tính từ snapshot cũ mà không có concurrency control, một thay đổi có thể bị mất.

Optimistic lock, atomic update hoặc isolation phù hợp giúp ngăn lỗi này.

### Pessimistic locking

Lock có thể phù hợp cho transaction ngắn trên database. Với workflow dài, giữ lock qua network call làm tăng contention và nguy cơ deadlock. Nên ưu tiên reservation hoặc state transition có version thay vì giữ database lock lâu.

### Duplicate command và competing event

Hai event có thể cùng cố chuyển OrderPendingPayment sang OrderPaid hoặc OrderCancelled. Transition cần có precondition trên state/version để chỉ một kết quả được commit. Event thua cuộc cần được xử lý theo policy, không tự động retry vô hạn.

## Retry, timeout và lỗi không xác định

Retry rất cần thiết khi service hoặc network tạm thời lỗi, nhưng retry sai có thể nhân đôi side effect.

### Phân loại lỗi

Có thể phân loại:
- Transient: timeout, connection reset, throttling.
- Permanent: invalid input, permission denied, unsupported operation.
- Conflict: version mismatch hoặc state đã thay đổi.
- Unknown outcome: request có thể đã được xử lý nhưng response bị mất.
- Dependency unavailable: service không thể truy cập trong thời gian hiện tại.

Transient error có thể retry với backoff. Permanent error thường cần sửa dữ liệu hoặc policy. Conflict cần reload và đánh giá lại. Unknown outcome cần query operation status hoặc retry với cùng idempotency key.

### Exponential backoff và jitter

Retry có thể dùng exponential backoff:

~~~text
delay = min(initialDelay * 2^attempt, maxDelay)
delay = applyJitter(delay)
~~~

Jitter giúp tránh nhiều worker retry cùng lúc tạo thêm tải. Cần có maximum attempts, total retry deadline và retry budget.

### Không retry mọi exception

Nếu action đã thực hiện side effect nhưng lỗi xảy ra khi ghi nhận kết quả, retry có thể lặp side effect. Cần biết action idempotent không và outcome có xác định không.

### Timeout không có nghĩa operation thất bại

Client timeout chỉ nói caller không nhận response trong thời gian giới hạn. Service có thể đã hoàn tất operation. Với payment, deployment hoặc provisioning, cần operation ID để query trạng thái trước khi quyết định retry.

### Circuit breaker

Nếu dependency liên tục lỗi, circuit breaker có thể tạm ngừng gửi request để bảo vệ hệ thống. Workflow có thể chuyển sang WaitingForDependency hoặc RetryPending. Circuit breaker không thay thế retry và không quyết định business outcome.

### Cancellation

Hủy request từ client không nhất thiết có thể hủy operation đã commit ở service ngoài. Runtime cần phân biệt:
- Cancel trước khi action bắt đầu.
- Cancel khi request đang gửi.
- Cancel sau khi service đã nhận.
- Cancel sau khi side effect đã commit.
- Cancel workflow nhưng vẫn cần compensation.

## Compensation và rollback

Rollback và compensation đều nhằm xử lý thất bại nhưng hoạt động khác nhau.

| Đặc điểm | Rollback | Compensation |
|---|---|---|
| Phạm vi | Transaction chưa commit | Side effect đã commit |
| Cơ chế | Hủy thay đổi trong resource manager | Thực hiện hành động nghiệp vụ mới |
| Tính nguyên tử | Theo transaction manager | Thường không nguyên tử toàn cục |
| Ví dụ | Rollback update order | Refund payment |
| Có thể thất bại? | Có, tùy resource/recovery | Có |
| Lưu lịch sử? | Thường không giữ thay đổi bị rollback | Có, vì compensation là một sự kiện mới |

### Compensation không xóa lịch sử

Nếu payment đã capture rồi refund, lịch sử phải thể hiện cả capture và refund. Không nên giả vờ payment chưa từng xảy ra bằng cách xóa record capture.

### Compensation có thể không hoàn toàn

Một shipment đã được gửi có thể không hủy được. Compensation có thể là tạo return request hoặc yêu cầu nhân viên xử lý. DSL nên cho phép compensation thất bại và chuyển sang state cần can thiệp.

### Compensation order

Thông thường, compensation chạy theo thứ tự ngược với các bước đã commit:

~~~text
Forward:
  ReserveInventory
  CapturePayment
  CreateShipment

Compensate:
  CancelShipment
  RefundPayment
  ReleaseInventory
~~~

Thứ tự cụ thể phụ thuộc dependency và business rule. Không phải mọi bước đều có compensation hoặc có thể bù trừ ngay.

### Compensation idempotency

Compensation cũng có thể bị retry. Refund cần idempotency key riêng, gắn với capture operation và compensation attempt. Nếu không, retry compensation có thể hoàn tiền nhiều lần.

## Transaction với filesystem, object storage và artifact

Không phải mọi resource đều là database hoặc service API. DSL tích hợp có thể ghi file, tạo artifact, upload object hoặc cập nhật registry.

### Ghi file nguyên tử

Một pattern là ghi vào file tạm, flush nội dung, sau đó atomic rename nếu filesystem hỗ trợ:

~~~text
write temporary file
validate content
flush and close
rename temporary -> final
~~~

Cần xác định atomic rename có bảo đảm trong cùng filesystem hay không. Rename qua volume khác có thể không atomic.

### Staging object

Với object storage, có thể upload vào staging key, kiểm tra checksum và metadata rồi cập nhật manifest hoặc pointer để công bố artifact. Nếu publish thất bại, staging object có thể được dọn dẹp sau.

### Manifest commit

Một release có thể gồm nhiều artifact. Thay vì giả định upload từng file là một transaction, có thể upload tất cả rồi ghi manifest release cuối cùng. Consumer chỉ coi release hợp lệ khi manifest đã commit và signature hợp lệ.

### Cleanup và orphan resource

Nếu workflow thất bại giữa chừng, staging file, temporary object hoặc cloud resource có thể còn sót. Cần cleanup task có thể retry, TTL hoặc reconciliation job.

### Không xóa resource không rõ chủ sở hữu

Cleanup cần gắn resource với execution ID hoặc ownership metadata. Không nên xóa theo pattern tên rộng có thể chạm resource của một workflow khác.

## Giao dịch với message broker

Message broker là một boundary phổ biến trong ứng dụng tích hợp.

### Publish và consume

Publish message và commit database là hai hành động riêng nếu broker không tham gia cùng transaction. Outbox giúp ghi ý định publish trong database transaction.

Consume message và cập nhật database cũng cần coordination. Inbox hoặc transaction integration với broker giúp tránh mất hoặc lặp tác động.

### Ordering

Ordering có thể được bảo đảm trong một partition hoặc theo key, nhưng không nhất thiết trên toàn topic. Nếu workflow cần thứ tự theo order ID, hãy dùng key tương ứng và kiểm tra sequence/version trong consumer.

### Poison message

Một message luôn gây lỗi có thể được retry vô hạn. Cần retry limit, dead-letter queue và cách đưa process về ManualReview. Dead-letter không có nghĩa nghiệp vụ đã được giải quyết; cần theo dõi và xử lý.

### Message schema evolution

Producer và consumer có thể deploy ở thời điểm khác nhau. Event schema cần versioning và compatibility policy. Một consumer cũ không nên crash khi gặp field mới nếu contract cho phép unknown field.

### Transactional messaging

Một số broker hỗ trợ transaction trong phạm vi broker, chẳng hạn gửi và consume message trong cùng broker transaction. Điều đó không tự động làm database transaction và broker transaction trở thành một transaction toàn cục.

## DSL abstraction cho giao dịch xuyên ranh giới

DSL nên biểu diễn ý định nghiệp vụ và contract thực thi mà không buộc tác giả phải quản lý connection hoặc protocol ở mức thấp.

Một model có thể gồm:

~~~text
WorkflowTransaction
  id
  scope
  participants
  consistencyMode
  timeout
  retryPolicy
  compensationPlan
  idempotencyPolicy
  recoveryPolicy
~~~

### Local transaction block

~~~text
TRANSACTION localOrderUpdate {
  SCOPE LOCAL
  DO {
    orders.updateStatus(orderId, "PENDING_PAYMENT")
    audit.record(orderId, "payment-requested")
  }
}
~~~

### Saga block

~~~text
SAGA placeOrder {
  STEP reserveStock {
    DO inventory.reserve(orderId)
    COMPENSATE inventory.release(orderId)
  }

  STEP charge {
    DO payment.capture(orderId)
    COMPENSATE payment.refund(orderId)
  }

  STEP notify {
    DO notifications.sendConfirmation(orderId)
  }
}
~~~

### Outbox declaration

~~~text
PUBLISH AFTER COMMIT "order.created" {
  orderId = order.id
  version = order.version
}
~~~

### Retry and idempotency declaration

~~~text
ACTION payment.capture(orderId) {
  IDEMPOTENCY_KEY orderId + ":capture"
  RETRY ON TRANSIENT_ERROR
    MAX_ATTEMPTS 4
    BACKOFF EXPONENTIAL
}
~~~

Các ví dụ là cú pháp minh họa. DSL cần định nghĩa semantics cụ thể, đặc biệt với side effect, transaction propagation, timeout và recovery.

### Compile-time checks

Compiler có thể:
- Phân loại action theo transaction capability.
- Phát hiện action non-transactional trong local transaction.
- Yêu cầu compensation cho bước saga theo policy.
- Kiểm tra idempotency key khi retry.
- Kiểm tra transaction scope không vượt giới hạn host.
- Phát hiện nested transaction không được hỗ trợ.
- Cảnh báo async task dùng transaction context đã hết hạn.

### Runtime enforcement

Runtime cần:
- Bắt đầu và kết thúc local transaction theo owner.
- Truyền context cho host adapter.
- Ghi workflow state bền vững.
- Áp dụng retry và timeout.
- Ghi outbox/inbox.
- Thực hiện compensation.
- Hỗ trợ cancellation và recovery.
- Không cho action vượt capability.

## Host API contract và transaction participation

Mỗi host binding cần công bố cách nó tham gia transaction.

Một contract có thể nêu:
- Có tham gia transaction hiện tại không?
- Tạo transaction riêng hay yêu cầu transaction có sẵn?
- Có side effect ngoài database không?
- Có idempotent không?
- Có compensation không?
- Có hỗ trợ cancellation không?
- Timeout tối đa là bao lâu?
- Có thể retry không?
- Kết quả có durable không?
- Error nào là transient, permanent hoặc unknown outcome?

Ví dụ:

~~~text
HostActionContract
  name: payment.capture
  transactionMode: NON_TRANSACTIONAL
  idempotent: true
  idempotencyKeyRequired: true
  compensation: payment.refund
  supportsCancellation: false
  timeout: 10s
  retryableErrors:
    - TEMPORARY_UNAVAILABLE
    - RATE_LIMITED
~~~

Contract này có thể được đăng ký cùng function registry để compiler và runtime hiểu capability.

### Không che giấu side effect trong function thuần

Một function tên calculateTotal có thể được xem là pure. Nếu nó đồng thời ghi audit hoặc gọi service, optimizer hoặc runtime có thể gọi nó nhiều lần ngoài ý muốn. Side effect cần được khai báo như action riêng.

### Adapter boundary

Host adapter chịu trách nhiệm map DSL value sang request của service và map response/error trở lại DSL. Nó cũng cần thực thi authorization, timeout, tracing và idempotency. Không nên để DSL tự tạo HTTP client tùy ý nếu muốn quản lý transaction và security nhất quán.

## Security và tenant isolation trong giao dịch xuyên ranh giới

Transaction context có thể mang identity và tenant. Khi workflow gọi nhiều service, các thuộc tính này cần được truyền đúng và không mở rộng quyền ngoài ý muốn.

### Principal propagation

Host cần truyền principal đã xác thực hoặc workload identity phù hợp. Không tin user ID do DSL source hoặc event payload tự khai báo.

### Tenant boundary

Mỗi repository và service call phải áp dụng tenant scope. Transaction ID hoặc saga ID không phải bằng chứng người gọi có quyền truy cập tenant tương ứng.

### Delegation và service identity

Một workflow có thể chạy sau khi request ban đầu đã kết thúc. Khi đó, không nên giữ access token người dùng vô thời hạn. Có thể dùng workload identity và delegation record có scope, audience và expiration.

### Secret và credential

Secret cần được cấp cho đúng action, không ghi vào workflow history hoặc event payload. Log và trace cần redaction. Idempotency key không nên chứa secret.

### Authorization tại mỗi bước

Quyền có thể bị thu hồi trong lúc saga đang chạy. Trước mỗi action nhạy cảm, runtime có thể cần đánh giá lại policy. Nếu bị từ chối, workflow phải đi vào trạng thái an toàn và có recovery path rõ.

## Observability và audit cho transaction xuyên ranh giới

Một workflow nhiều bước cần có khả năng trả lời: transaction đang ở đâu, bước nào đã commit, bước nào đang retry, action nào đã compensation và resource nào còn pending.

### Correlation identifiers

Các ID thường dùng:
- Workflow instance ID.
- Saga ID.
- Step ID.
- Transaction ID.
- Event ID.
- Idempotency key.
- Trace ID.
- Resource version.

Không nên dùng một ID cho mọi mục đích. Ví dụ, trace ID có vòng đời theo request, còn saga ID có thể tồn tại nhiều ngày.

### Transaction timeline

Một timeline có thể ghi:

~~~text
10:00:00 OrderCreated committed
10:00:01 InventoryReserved committed
10:00:03 PaymentCapture requested
10:00:13 PaymentCapture outcome unknown
10:00:14 Payment status reconciled as captured
10:00:15 ShipmentCreated committed
10:00:16 OrderConfirmed committed
~~~

Timeline giúp người vận hành hiểu khoảng thời gian giữa các boundary và phát hiện operation bị treo.

### Metrics

Có thể theo dõi:
- Số workflow đang hoạt động.
- Saga duration.
- Step success/failure.
- Compensation count và failure.
- Retry count.
- Outbox backlog.
- Inbox duplicate count.
- Message delivery lag.
- Transaction timeout.
- Unknown outcome count.
- Reconciliation backlog.
- Workflow stuck duration.

Metric labels nên có tập giá trị hữu hạn như workflow type, step name, outcome và service class. Không đưa raw customer ID hoặc order ID vào label.

### Logs và traces

Logs nên ghi transition, operation ID, reason code và policy version. Trace có thể nối host request, DSL evaluation, database call, external API và message publish.

Với workflow dài, không nhất thiết giữ một trace mở trong nhiều ngày. Có thể tạo trace riêng cho mỗi execution segment và liên kết chúng bằng saga ID hoặc trace link.

### Audit

Audit record cần lưu những thay đổi có ý nghĩa nghiệp vụ:
- Ai khởi tạo workflow.
- Definition version nào được chạy.
- Resource nào bị thay đổi.
- Action nào đã commit.
- Compensation nào đã chạy.
- Approval và authorization decision.
- Kết quả cuối cùng.

Không ghi secret hoặc toàn bộ payload nhạy cảm vào audit.

## Kiểm thử giao dịch xuyên ranh giới

Kiểm thử cần bao phủ cả thành công, thất bại một phần, duplicate, timeout và recovery.

### Local transaction test

Kiểm tra:
- Tất cả database changes commit khi thành công.
- Một lỗi giữa các thao tác làm rollback theo contract.
- Nested/propagation behavior đúng.
- Isolation và optimistic lock được áp dụng.
- Event chỉ được phát theo commit semantics.

### Distributed workflow test

Mô phỏng từng điểm thất bại:
- Inventory reserve thành công, payment thất bại.
- Payment thành công nhưng response timeout.
- Database commit thất bại sau external action.
- Outbox publisher crash sau broker publish.
- Consumer xử lý xong nhưng crash trước acknowledge.
- Compensation thất bại.
- Workflow restart khi đang chờ timer hoặc service.
- Policy bị thu hồi trước bước tiếp theo.

### Idempotency test

Gửi cùng operation nhiều lần và xác nhận:
- Chỉ một business effect được tạo.
- Retry nhận lại kết quả phù hợp.
- Cùng key với payload khác bị phát hiện.
- Hai request đồng thời không cùng thực hiện side effect.
- Compensation không bị chạy lặp gây hoàn tiền nhiều lần.

### Outbox/inbox test

Kiểm tra business update và outbox record commit cùng nhau. Giả lập publisher gửi thành công rồi crash trước khi đánh dấu published. Consumer cần xử lý duplicate mà không lặp side effect.

### Saga test

Kiểm tra:
- Forward path hoàn tất.
- Compensation chạy đúng thứ tự.
- Compensation failure được lưu và retry.
- Process đi vào manual intervention khi không thể tự phục hồi.
- Restart không làm mất step state.
- Một event cũ không làm state tiến lùi.

### Fault injection

Có thể tiêm:
- Network timeout.
- Connection reset.
- Database deadlock.
- Broker unavailable.
- HTTP 429 hoặc 503.
- Response malformed.
- Process crash.
- Disk full.
- Credential expired.

Fault injection nên chạy trong môi trường test được cô lập. Không tạo lỗi có chủ đích trên production resource.

### Deterministic test

Dùng fake clock, deterministic scheduler, controllable message broker và stable IDs để test timeout, ordering và retry mà không dựa vào sleep. Mỗi test cần namespace riêng để chạy song song.

## Vận hành và phục hồi

Một thiết kế giao dịch chỉ hoàn chỉnh khi có quy trình vận hành các operation bị treo hoặc thất bại.

### Durable workflow state

Workflow dài cần lưu:
- Current state.
- Completed steps.
- Pending steps.
- Attempt count.
- Last error category.
- Compensation status.
- Next retry time.
- Deadline.
- Definition version.
- Correlation IDs.

Nếu state chỉ nằm trong memory, process restart có thể làm mất tiến độ và không biết side effect nào đã xảy ra.

### Recovery worker

Recovery worker có thể tìm:
- Saga ở trạng thái pending quá lâu.
- Outbox record chưa publish.
- Compensation chưa hoàn tất.
- Operation outcome chưa xác định.
- Inbox record bị kẹt.
- Timer đã đến hạn nhưng chưa xử lý.

Worker cần idempotent và dùng concurrency control để nhiều instance không cùng xử lý một recovery task.

### Manual intervention

Không phải lỗi nào cũng có thể tự động giải quyết. Workflow có thể chuyển sang ManualReview với:
- Trạng thái hiện tại.
- Các bước đã hoàn tất.
- Side effect đã xảy ra.
- Compensation còn thiếu.
- Bằng chứng từ external service.
- Hành động được phép cho operator.

Operator action cũng cần authorization và audit.

### Reconciliation

Đối chiếu định kỳ với hệ thống nguồn có thể phát hiện chênh lệch, ví dụ payment provider đã capture nhưng order còn PendingPayment. Reconciliation cần có quy tắc sửa trạng thái hoặc đưa vào manual review, không tự suy đoán khi dữ liệu mâu thuẫn.

### Retention

Workflow history, outbox/inbox và idempotency records cần retention đủ dài để hỗ trợ retry và audit. Xóa record quá sớm có thể làm một retry cũ được xử lý như operation mới.

## Những lỗi thiết kế thường gặp

### Bao toàn bộ workflow trong một transaction tưởng tượng

Một transaction block không thể rollback HTTP call, email hoặc payment nếu các hệ thống đó không tham gia protocol chung. Phân biệt local transaction và distributed workflow.

### Giữ database transaction mở qua network call dài

Điều này giữ lock và connection, làm tăng contention và timeout. Commit local state trước rồi điều phối bước ngoài transaction khi phù hợp.

### Publish event sau commit mà không có outbox

Nếu process crash giữa database commit và publish, event có thể bị mất. Dùng transactional outbox hoặc cơ chế tương đương.

### Retry action không idempotent

Retry payment hoặc create shipment có thể tạo side effect lặp. Dùng idempotency key và operation status.

### Coi timeout là thất bại chắc chắn

Service có thể đã commit nhưng response bị mất. Query status hoặc retry cùng key thay vì tạo operation mới.

### Compensation không được mô hình hóa

Nếu workflow có nhiều local commit mà không có compensation hoặc manual recovery, lỗi giữa chừng có thể để lại trạng thái nghiệp vụ không thể giải quyết.

### Không lưu durable state

Process restart có thể khiến engine không biết bước nào đã chạy. Lưu state và event history bền vững.

### Nhầm exactly-once với bảo đảm mặc định

Broker hoặc network thường có thể giao message lặp. Dùng at-least-once kết hợp inbox, deduplication và idempotent action.

### Không kiểm soát version và concurrency

Event cũ có thể ghi đè state mới. Dùng process version, expected state và optimistic locking.

### Bỏ qua reconciliation

Retry hữu hạn không xử lý mọi trường hợp. Cần job tìm operation bị treo và đối chiếu trạng thái với hệ thống ngoài.

### Gộp transaction và authorization

Có quyền gọi action không có nghĩa action có thể tham gia transaction hiện tại. Cần kiểm tra riêng permission, resource scope và transaction capability.

## Quy trình thiết kế giao dịch xuyên ranh giới cho DSL

Một quy trình thực tế có thể đi theo các bước:

1. **Vẽ workflow nghiệp vụ:** liệt kê các bước, dữ liệu và side effect.
2. **Đánh dấu ranh giới:** xác định database, service, broker, filesystem và resource manager của từng bước.
3. **Chọn transaction owner:** chỉ rõ host, workflow engine hay transaction manager chịu trách nhiệm commit.
4. **Phân loại action:** local transactional, distributed protocol participant, idempotent external action hoặc non-idempotent action.
5. **Định nghĩa consistency:** xác định invariant, trạng thái trung gian và mức eventual/strong consistency.
6. **Chọn coordination pattern:** local ACID, 2PC/XA, saga, outbox/inbox hoặc kết hợp.
7. **Định nghĩa compensation:** mô tả hành động bù trừ, retry và manual recovery cho từng bước đã commit.
8. **Thiết kế idempotency:** operation key, deduplication, inbox và response cho request lặp.
9. **Thiết kế concurrency:** version, locking, ordering và conflict handling.
10. **Đặt timeout và retry budget:** phân loại lỗi, backoff, jitter và unknown outcome.
11. **Thiết kế DSL contract:** transaction scope, propagation, action metadata và static validation.
12. **Bảo vệ context:** principal, tenant, capability, secret và authorization tại từng boundary.
13. **Lưu durable state:** saga state, outbox/inbox, timer và definition version.
14. **Bổ sung observability:** correlation ID, timeline, metrics, trace và audit.
15. **Kiểm thử failure path:** duplicate, crash, timeout, partial commit, compensation và recovery.
16. **Chuẩn bị vận hành:** dashboard, reconciliation, manual intervention và retention.

Với mỗi action, nên có một contract mô tả transaction mode, idempotency, retryable errors, timeout, cancellation, compensation và resource được tác động. Đây là thông tin giúp compiler, runtime và operator hiểu giới hạn của hành động.

## Kết luận

Giao dịch xuyên ranh giới xuất hiện khi một quy trình DSL tương tác với nhiều thành phần có transaction scope hoặc cơ chế commit khác nhau. Local database transaction có thể cung cấp ACID trong phạm vi resource manager, nhưng không tự rollback được side effect ở service, broker, filesystem hoặc cloud API.

Một thiết kế đáng tin cậy cần xác định transaction owner, propagation và consistency model; chọn 2PC/XA khi các resource hỗ trợ và atomic commit thực sự cần thiết; hoặc dùng saga, compensation, transactional outbox/inbox và idempotency cho workflow phân tán. Durable state, versioning, timeout, retry, cancellation, reconciliation và manual intervention giúp xử lý các trạng thái thất bại một phần.

DSL nên khai báo rõ transaction capability của từng host action để compiler và runtime không tạo ra kỳ vọng atomicity sai. Host adapter chịu trách nhiệm truyền context, enforce policy, quản lý transaction cục bộ và kết nối các cơ chế recovery. Khi các ranh giới, side effect và failure path được mô hình hóa tường minh, workflow có thể hoạt động nhất quán qua nhiều service mà vẫn có khả năng quan sát, phục hồi và kiểm soát.

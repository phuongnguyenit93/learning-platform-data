# Sự kiện quy trình

Trong một DSL quy trình (workflow DSL), các bước thường không chạy liên tục từ đầu đến cuối. Một quy trình có thể phải chờ khách hàng xác nhận, đợi hệ thống thanh toán phản hồi, nhận thông báo từ kho hàng hoặc tiếp tục khi đến một thời điểm nhất định. **Sự kiện quy trình (workflow event)** là tín hiệu cho biết một điều gì đó đã xảy ra và có thể làm quy trình bắt đầu, tiếp tục, chuyển trạng thái hoặc thực hiện hành động tiếp theo.

Ví dụ, một workflow xử lý đơn hàng có thể chờ `PaymentSucceeded`, nhận `InventoryReserved`, hoặc dừng khi `PaymentFailed`. Những sự kiện này có thể đến từ chính workflow, một dịch vụ bên ngoài, người dùng, bộ lập lịch hoặc message broker.

Để hỗ trợ sự kiện một cách đáng tin cậy, DSL cần mô tả loại sự kiện, dữ liệu đi kèm, điều kiện kích hoạt, cách tương quan với instance quy trình, thứ tự xử lý, bảo đảm giao nhận, retry, timeout, versioning và bảo mật. Runtime cần tiếp nhận event, tìm đúng workflow đang chờ, kiểm tra điều kiện, cập nhật trạng thái và ghi nhận kết quả xử lý.

## 1. Sự kiện quy trình là gì?

Sự kiện là một bản ghi hoặc thông điệp biểu diễn một điều đã xảy ra tại một thời điểm. Trong workflow, event thường kích hoạt hoặc cung cấp dữ liệu cho một transition.

Ví dụ:

```text
PaymentAuthorized {
    orderId: OrderId
    paymentId: PaymentId
    amount: Money
    occurredAt: Instant
}
```

Event `PaymentAuthorized` biểu thị việc thanh toán đã được chấp thuận. Workflow có thể nhận event này rồi chuyển từ trạng thái `AwaitingPayment` sang `PreparingShipment`.

### 1.1. Event mô tả sự thật đã xảy ra

Event thường được đặt tên theo dạng quá khứ hoặc một trạng thái đã xảy ra: `OrderSubmitted`, `PaymentCaptured`, `ShipmentDispatched`, `CustomerConfirmed`. Cách đặt tên này nhấn mạnh rằng event mô tả một sự kiện đã xảy ra, không phải yêu cầu một hành động trong tương lai.

### 1.2. Event khác với state

State mô tả tình trạng hiện tại của một đối tượng hoặc workflow. Event mô tả một thay đổi hoặc điều đã xảy ra.

| Khái niệm | Ví dụ | Ý nghĩa |
|---|---|---|
| State | `order.status = PAID` | Đơn hàng hiện đang ở trạng thái đã thanh toán |
| Event | `PaymentCaptured` | Thanh toán vừa được ghi nhận thành công |
| Command | `CapturePayment` | Yêu cầu hệ thống thực hiện thao tác thu tiền |
| Query | `GetPaymentStatus` | Yêu cầu đọc trạng thái thanh toán |

### 1.3. Event khác với command

Command yêu cầu một hành động; event thông báo một kết quả hoặc sự kiện đã xảy ra. Command có thể bị từ chối hoặc thất bại. Event được phát ra khi điều đã mô tả thực sự xảy ra theo hợp đồng của hệ thống.

Ví dụ:

```text
command CapturePayment(orderId)
event PaymentCaptured(orderId, paymentId, amount)
```

Không nên dùng tên event như `DoPayment` nếu nó thực chất là yêu cầu thực thi. Tách command và event giúp workflow thể hiện rõ yêu cầu, kết quả và lỗi.

## 2. Vai trò của event trong workflow

Event có thể tham gia vào nhiều điểm của vòng đời quy trình:

- Khởi tạo một workflow mới khi nhận yêu cầu hoặc thông báo.
- Đánh thức một instance đang chờ sự kiện.
- Chọn nhánh tiếp theo dựa trên loại event hoặc payload.
- Cập nhật dữ liệu và biến của workflow.
- Hoàn tất, hủy hoặc chuyển workflow sang trạng thái lỗi.
- Phát thông báo cho workflow khác hoặc hệ thống bên ngoài.
- Kích hoạt timer, retry hoặc escalation.

Ví dụ workflow đơn hàng:

```text
OrderSubmitted
      |
      v
ValidateOrder
      |
      v
RequestPayment
      |
      v
Wait for PaymentCaptured or PaymentFailed
      |                         |
      v                         v
ReserveInventory             CancelOrder
      |
      v
Wait for InventoryReserved
      |
      v
CreateShipment
```

Event giúp quy trình phối hợp các hệ thống độc lập mà không cần giữ một lời gọi đồng bộ mở trong suốt thời gian chờ.

## 3. Các nguồn phát sinh sự kiện

Event có thể đến từ nhiều nguồn. DSL nên phân biệt nguồn phát sinh nếu điều đó ảnh hưởng đến xác thực, routing hoặc semantics.

| Nguồn | Ví dụ |
|---|---|
| Người dùng | `CustomerApproved`, `DocumentUploaded` |
| Ứng dụng nghiệp vụ | `OrderSubmitted`, `InvoiceIssued` |
| Dịch vụ bên ngoài | `PaymentCaptured`, `CarrierDelivered` |
| Database/CDC | `CustomerRecordChanged` |
| Message broker | Message được publish từ topic hoặc queue |
| Timer/scheduler | `ReviewDeadlineReached`, `DailySettlementDue` |
| Workflow khác | `ApprovalCompleted`, `SubprocessFailed` |
| Hệ thống vận hành | `ServiceUnavailable`, `ManualInterventionRequested` |

### 3.1. External events

External event đến từ ngoài runtime workflow, ví dụ webhook từ cổng thanh toán. Runtime cần xác thực nguồn, kiểm tra schema và chống xử lý lặp.

### 3.2. Internal events

Internal event được phát ra bởi một bước hoặc một service trong cùng ứng dụng. Runtime có thể xử lý chúng ngay hoặc đưa vào hàng đợi để duy trì thứ tự và tách biệt giữa các bước.

### 3.3. Timer events

Timer event xuất hiện khi đạt một thời điểm hoặc khoảng thời gian. Ví dụ `PaymentTimeout` sau 15 phút nếu chưa nhận được `PaymentCaptured`. Timer cần gắn với workflow instance và được hủy hoặc vô hiệu hóa khi điều kiện chờ đã kết thúc.

### 3.4. Error events

Error event biểu diễn lỗi hoặc ngoại lệ có thể được workflow bắt và xử lý. Cần phân biệt lỗi nghiệp vụ như `PaymentDeclined` với lỗi kỹ thuật như timeout hoặc dịch vụ không khả dụng.

## 4. Định nghĩa kiểu sự kiện

Một DSL có thể cho phép khai báo event type cùng payload có kiểu:

```text
event PaymentCaptured {
    orderId: OrderId
    paymentId: PaymentId
    amount: Money
    occurredAt: Instant
}

event PaymentDeclined {
    orderId: OrderId
    paymentId: PaymentId
    reason: DeclineReason
    occurredAt: Instant
}
```

Khai báo event type giúp compiler kiểm tra tên trường, kiểu dữ liệu, required fields và tương thích giữa producer với consumer.

### 4.1. Event name

Tên event nên mô tả điều đã xảy ra và có nghĩa ổn định trong domain. Nên tránh tên quá chung như `Update`, `Message` hoặc `StatusChanged` nếu không có thêm loại hoặc ngữ cảnh.

### 4.2. Payload

Payload chứa dữ liệu cần để consumer xử lý. Nên chỉ mang thông tin cần thiết, tránh gửi toàn bộ object lớn nếu consumer chỉ cần ID và một vài thuộc tính.

### 4.3. Required và optional fields

Event schema cần chỉ rõ trường bắt buộc và tùy chọn. Consumer phải có hành vi xác định khi trường optional không có mặt.

### 4.4. Immutable event

Event thường được xem là immutable sau khi phát hành. Nếu thông tin sai, hệ thống có thể phát event điều chỉnh hoặc event bù trừ thay vì sửa âm thầm event đã được consumer xử lý.

### 4.5. Event không phải snapshot tùy ý

Payload có thể chứa dữ liệu tại thời điểm event xảy ra. Nếu consumer cần trạng thái mới nhất, nó có thể truy vấn hệ thống sở hữu dữ liệu. Cần phân biệt snapshot payload với ID tham chiếu để tránh hiểu nhầm rằng event luôn chứa trạng thái hiện tại.

## 5. Event envelope và metadata

Ngoài payload nghiệp vụ, message thường có một envelope chứa metadata phục vụ định tuyến, tương quan, deduplication và audit.

Ví dụ cấu trúc khái niệm:

```json
{
  "id": "evt-8f31",
  "type": "PaymentCaptured",
  "schemaVersion": 2,
  "source": "payment-service",
  "subject": "orders/order-42",
  "occurredAt": "2026-11-15T03:00:00Z",
  "correlationId": "wf-order-42",
  "causationId": "cmd-capture-19",
  "payload": {
    "orderId": "order-42",
    "paymentId": "pay-19",
    "amount": 125000
  }
}
```

Các trường thường gặp:

| Metadata | Mục đích |
|---|---|
| `id` | ID duy nhất để nhận diện event và chống xử lý lặp |
| `type` | Loại event |
| `schemaVersion` | Phiên bản schema payload |
| `source` | Hệ thống phát event |
| `subject` | Đối tượng hoặc tài nguyên liên quan |
| `occurredAt` | Thời điểm sự kiện xảy ra |
| `publishedAt` | Thời điểm event được gửi đi |
| `correlationId` | Liên kết các message trong cùng luồng nghiệp vụ |
| `causationId` | Message hoặc command trực tiếp gây ra event |
| `tenantId` | Phạm vi tenant nếu hệ thống multi-tenant |
| `traceId` | Liên kết telemetry và distributed trace |

### 5.1. Event ID và deduplication

Producer có thể gửi lại cùng event sau timeout hoặc retry. Event ID ổn định giúp consumer nhận biết bản sao và tránh áp dụng cùng thay đổi nhiều lần.

### 5.2. Correlation ID

Correlation ID liên kết các event, command và bước thuộc cùng một workflow hoặc business transaction. Ví dụ tất cả message liên quan đến đơn `order-42` có thể mang cùng `correlationId`.

### 5.3. Causation ID

Causation ID chỉ ra message nào trực tiếp gây ra event hiện tại. Nó giúp lần theo chuỗi nhân quả, ví dụ command `CapturePayment` dẫn đến event `PaymentCaptured`.

### 5.4. Timestamp

`occurredAt` và `publishedAt` có ý nghĩa khác nhau. Event có thể xảy ra trước nhưng được publish trễ. Không nên dùng timestamp nhận message làm đại diện tuyệt đối cho thứ tự nghiệp vụ.

## 6. Khai báo event trong workflow DSL

Một DSL có thể biểu diễn điểm chờ và transition bằng cú pháp tường minh:

```text
workflow fulfillOrder(orderId: OrderId) {
    let order = loadOrder(orderId)
    requestPayment(order)

    wait for PaymentCaptured where event.orderId == orderId
        as payment

    reserveInventory(order, payment)
}
```

Ở đây workflow phát command hoặc gọi service thanh toán, sau đó tạm dừng đến khi nhận event `PaymentCaptured` có `orderId` khớp. Khi event đến, payload được bind vào biến `payment` để bước tiếp theo sử dụng.

### 6.1. Wait for event

`wait for` biểu diễn điểm chờ. Runtime cần lưu trạng thái chờ bền vững để instance có thể tiếp tục sau khi process hoặc server khởi động lại.

### 6.2. Event filter

Điều kiện `where` lọc event phù hợp. Filter có thể dựa trên payload, metadata, tenant, correlation ID hoặc trạng thái workflow.

### 6.3. Binding payload

`as payment` gắn payload hoặc event object vào biến trong workflow scope. DSL cần quy định biến này chứa envelope đầy đủ hay chỉ payload nghiệp vụ.

### 6.4. Nhiều loại event

Một điểm chờ có thể nhận nhiều loại event:

```text
wait for PaymentCaptured or PaymentDeclined
    where event.orderId == orderId
```

Workflow cần định nghĩa nhánh xử lý riêng cho từng loại event và hành vi khi nhiều event cạnh tranh đến gần như đồng thời.

## 7. Event trigger và subscription

Workflow runtime cần biết những event nào có thể đánh thức một workflow instance. Có thể khai báo subscription:

```text
on PaymentCaptured as payment
    where payment.orderId == context.orderId
    resume fulfillOrder
```

Subscription thường có:

- Event type hoặc topic được lắng nghe.
- Predicate lọc event.
- Phạm vi instance hoặc correlation.
- Quy tắc authorization.
- Handler hoặc transition đích.
- Chính sách acknowledgement và retry.

### 7.1. Event type subscription

Subscription theo type nhận tất cả event của một loại rồi lọc thêm theo payload. Đây là cách phổ biến khi broker route theo topic hoặc event type.

### 7.2. Content-based routing

Event có thể được route theo nội dung, ví dụ `region == "EU"` hoặc `amount > threshold`. Routing predicate cần có kiểu và chi phí thực thi phù hợp; không nên cho phép expression tùy ý có tác dụng phụ trong broker filter.

### 7.3. Subscription scope

Subscription có thể ở cấp workflow definition, workflow instance, tenant hoặc toàn hệ thống. Subscription cấp instance cần được đăng ký và hủy theo vòng đời instance để tránh rò rỉ và xử lý nhầm.

### 7.4. Correlation

Khi nhiều workflow instance cùng chờ `PaymentCaptured`, event phải được gắn đúng instance. Thường dùng `correlationId`, `orderId` hoặc một khóa business đã xác thực. Không nên chỉ chọn instance đầu tiên đang chờ cùng event type.

## 8. Correlation và causation

Trong hệ thống event-driven, một event type có thể được phát sinh bởi nhiều luồng. Correlation giúp gom các message thuộc cùng một quy trình; causation giúp xác định message trước đó gây ra message hiện tại.

Ví dụ:

```text
OrderSubmitted
    correlationId = wf-42
        |
        v
CapturePayment command
    causationId = evt-order-submitted
        |
        v
PaymentCaptured
    correlationId = wf-42
    causationId = cmd-capture-payment
        |
        v
ReserveInventory command
    correlationId = wf-42
```

### 8.1. Business key và workflow ID

Business key như `orderId` giúp liên kết message với thực thể nghiệp vụ. Workflow ID nhận diện một lần thực thi cụ thể. Hai khái niệm không luôn giống nhau: một đơn hàng có thể có nhiều workflow instance qua các lần xử lý hoặc bù trừ.

### 8.2. Không tin correlation từ bên ngoài

Correlation ID do client gửi có thể bị giả mạo hoặc trùng. Runtime cần kiểm tra tenant, quyền và quan hệ giữa event với workflow instance trước khi resume.

### 8.3. Distributed tracing

`traceId` liên kết log, span và telemetry qua nhiều dịch vụ. Nó phục vụ quan sát kỹ thuật; correlation ID phục vụ liên kết nghiệp vụ. Có thể truyền cả hai nhưng không nên dùng thay thế lẫn nhau.

## 9. Thứ tự sự kiện

Event có thể đến không theo thứ tự xảy ra, đặc biệt khi có nhiều producer, partition hoặc retry.

Ví dụ workflow nhận:

```text
1. ShipmentDelivered
2. ShipmentDispatched
```

Nếu `ShipmentDelivered` đến trước `ShipmentDispatched`, runtime cần biết có nên giữ event chờ, xử lý ngay, từ chối hay yêu cầu đồng bộ lại trạng thái.

### 9.1. Ordering theo partition

Message broker thường chỉ bảo đảm thứ tự trong một partition hoặc một key cụ thể. Nếu cần thứ tự theo `orderId`, producer có thể dùng `orderId` làm partition key.

### 9.2. Sequence number

Event có thể chứa sequence number theo aggregate hoặc workflow instance. Consumer kiểm tra sequence để phát hiện event thiếu, trùng hoặc đến sai thứ tự.

### 9.3. Event time và processing time

Event time là thời điểm sự kiện xảy ra; processing time là thời điểm runtime xử lý nó. Chênh lệch giữa hai thời điểm có thể lớn do mạng, broker hoặc consumer bị gián đoạn.

### 9.4. Late events

Event đến muộn có thể không còn phù hợp với trạng thái hiện tại. Workflow cần định nghĩa late event được bỏ qua, lưu để audit, áp dụng compensation hay đưa vào manual review.

### 9.5. Không giả định thứ tự toàn cục

Trong hệ thống phân tán, thứ tự toàn cục giữa mọi event thường không có hoặc rất tốn kém. Nên xác định thứ tự cần bảo đảm theo aggregate, workflow instance hoặc partition.

## 10. Delivery semantics: at-most-once, at-least-once và exactly-once

Giao nhận event có thể gặp mất message, gửi lại hoặc consumer xử lý xong nhưng chưa kịp acknowledgement.

| Semantics | Đặc điểm | Hệ quả |
|---|---|---|
| At-most-once | Message được giao tối đa một lần | Có thể mất message |
| At-least-once | Message được giao một hoặc nhiều lần | Consumer phải chịu được duplicate |
| Exactly-once | Mỗi hiệu ứng logic được tính đúng một lần trong phạm vi bảo đảm cụ thể | Cần transaction/protocol và giới hạn rõ |

### 10.1. At-most-once

Phù hợp với tín hiệu có thể bỏ qua hoặc dữ liệu telemetry không yêu cầu xử lý lại. Không phù hợp nếu mất event khiến workflow bị treo hoặc mất giao dịch.

### 10.2. At-least-once

Đây là mô hình phổ biến vì producer hoặc broker có thể retry cho đến khi acknowledgement. Consumer cần idempotency hoặc deduplication.

### 10.3. Exactly-once không phải lời hứa tuyệt đối

Exactly-once thường chỉ áp dụng trong phạm vi transaction hoặc hệ thống cụ thể. Khi event đi qua nhiều dịch vụ và database, việc bảo đảm một hiệu ứng duy nhất đòi hỏi phối hợp các thành phần. Thiết kế thực tế thường dùng at-least-once cùng xử lý idempotent.

## 11. Idempotency và chống xử lý trùng

Một handler idempotent có thể được gọi nhiều lần với cùng event mà kết quả nghiệp vụ không bị nhân đôi.

Ví dụ:

```text
on PaymentCaptured as event {
    if not processed(event.id) {
        markOrderPaid(event.orderId)
        recordProcessed(event.id)
    }
}
```

Đoạn mã minh họa cần được thực hiện nguyên tử: ghi nhận event đã xử lý và cập nhật trạng thái nghiệp vụ phải nằm trong cùng transaction hoặc một cơ chế tương đương.

### 11.1. Deduplication key

Event ID là khóa dedup phổ biến. Với event được tạo lại bởi producer, có thể cần business operation ID ổn định để nhận diện cùng một thao tác dù message ID khác nhau.

### 11.2. Inbox pattern

Consumer có thể lưu event ID đã nhận vào bảng inbox cùng transaction với cập nhật trạng thái. Nếu event ID đã tồn tại, consumer bỏ qua phần xử lý nghiệp vụ và acknowledgement message.

### 11.3. Idempotent operations

Ngoài dedup, API nghiệp vụ có thể nhận idempotency key. Ví dụ yêu cầu tạo shipment mang cùng operation ID sẽ không tạo hai shipment nếu client retry.

### 11.4. Không deduplicate quá rộng

Hai event cùng payload nhưng khác event ID có thể đại diện cho hai sự kiện thực sự khác nhau. Không nên dùng hash payload làm khóa dedup nếu domain không bảo đảm hai payload giống nhau luôn là cùng một event.

## 12. Retry, timeout và dead-letter

Event handler có thể thất bại vì lỗi mạng, database tạm thời không khả dụng hoặc payload không hợp lệ.

### 12.1. Retry transient errors

Với lỗi tạm thời, runtime có thể thử lại sau một khoảng thời gian. Exponential backoff và jitter giúp tránh nhiều consumer cùng retry đồng loạt.

Ví dụ policy:

```text
retry {
    maxAttempts = 5
    initialDelay = 1s
    multiplier = 2
    maxDelay = 1m
    jitter = true
}
```

### 12.2. Phân loại lỗi

Không phải lỗi nào cũng nên retry:

- Transient: timeout, network reset, service unavailable.
- Permanent: schema không hợp lệ, thiếu field bắt buộc, event type không hỗ trợ.
- Business rejection: trạng thái hiện tại không cho phép thao tác.
- Unknown: cần log và có thể đưa vào dead-letter hoặc manual review.

### 12.3. Timeout khi chờ event

Workflow có thể chờ event trong một khoảng thời gian:

```text
wait for PaymentCaptured
    timeout 15m
    on timeout -> cancelPayment
```

Khi timeout, runtime cần hủy hoặc vô hiệu hóa subscription cũ để event đến muộn không kích hoạt nhầm transition.

### 12.4. Dead-letter queue

Event không thể xử lý sau số lần retry cho phép có thể được đưa vào dead-letter queue (DLQ). DLQ hỗ trợ điều tra, sửa dữ liệu hoặc replay có kiểm soát.

### 12.5. Replay

Replaying event có thể khôi phục xử lý sau sự cố, nhưng cần biết handler có idempotent không và trạng thái workflow hiện tại có còn phù hợp không. Replay không nên tự động tạo lại tác dụng phụ bên ngoài nếu chưa có chính sách.

## 13. Transactional outbox và inbox

Một lỗi thường gặp là cập nhật database thành công nhưng publish event thất bại, hoặc publish event thành công trong khi transaction database bị rollback.

### 13.1. Transactional outbox

Outbox ghi thay đổi nghiệp vụ và event cần publish vào cùng database transaction. Một dispatcher đọc outbox rồi gửi event đến broker. Nếu dispatcher gửi lại, consumer xử lý idempotent.

```text
Application transaction
    |
    +--> Update business data
    |
    +--> Insert outbox event
             |
             v
         Commit
             |
             v
       Outbox dispatcher
             |
             v
          Message broker
```

### 13.2. Inbox

Inbox lưu message ID đã xử lý để tránh duplicate. Việc lưu inbox marker và cập nhật domain state nên nằm trong cùng transaction.

### 13.3. Outbox không tự tạo exactly-once

Dispatcher vẫn có thể gửi cùng event nhiều lần nếu crash sau khi broker nhận message nhưng trước khi đánh dấu outbox đã gửi. Vì vậy consumer vẫn cần deduplication.

### 13.4. Workflow runtime persistence

Runtime có thể lưu trạng thái workflow, subscription và event receipt trong cùng transaction để tránh tình trạng event đã được acknowledge nhưng workflow chưa được cập nhật.

## 14. Event-driven workflow và state machine

Workflow thường có trạng thái và transition được kích hoạt bởi event.

Ví dụ state machine:

```text
Draft
  | OrderSubmitted
  v
AwaitingPayment
  | PaymentCaptured
  v
PreparingShipment
  | ShipmentDispatched
  v
InTransit
  | ShipmentDelivered
  v
Completed
```

Event không hợp lệ với state hiện tại cần có policy: bỏ qua, lưu lại, báo lỗi, hoặc kích hoạt compensation.

### 14.1. Guard condition

Transition có thể có điều kiện:

```text
on PaymentCaptured
    when event.amount == context.expectedAmount
    -> PreparingShipment
```

Guard nên thuần và xác định. Nếu guard cần truy vấn dịch vụ ngoài, nên mô hình hóa thành bước workflow riêng để tránh kết quả thay đổi giữa các lần đánh giá.

### 14.2. Event có thể kích hoạt nhiều transition?

Một event có thể phù hợp với nhiều handler. DSL cần quy định fan-out hay chỉ một transition được chọn. Nếu có nhiều handler, thứ tự và tính nguyên tử của các cập nhật cần được xác định.

### 14.3. Event không phù hợp state

Ví dụ `ShipmentDelivered` đến khi workflow vẫn ở `AwaitingPayment`. Có thể đây là event sai, event đến sai thứ tự hoặc trạng thái workflow bị mất đồng bộ. Nên có diagnostic/audit và quy tắc xử lý thay vì âm thầm chuyển state.

## 15. Event choreography và orchestration

Có hai cách phổ biến để phối hợp nhiều dịch vụ.

### 15.1. Choreography

Mỗi dịch vụ phát và tiêu thụ event theo hợp đồng. Không có một coordinator trung tâm điều khiển toàn bộ luồng.

```text
Order Service
    | OrderSubmitted
    v
Payment Service
    | PaymentCaptured
    v
Inventory Service
    | InventoryReserved
    v
Shipping Service
```

Ưu điểm là các dịch vụ ít phụ thuộc trực tiếp vào nhau. Nhược điểm là luồng tổng thể có thể khó quan sát khi có nhiều event và nhánh.

### 15.2. Orchestration

Một workflow engine điều phối các bước, phát command, chờ event và quyết định bước tiếp theo.

```text
             Workflow Engine
             /      |      \\
            v       v       v
        Payment  Inventory Shipping
```

Orchestration giúp nhìn rõ trạng thái quy trình và timeout/compensation, nhưng engine trở thành thành phần quan trọng cần vận hành tin cậy.

### 15.3. Kết hợp hai mô hình

Một workflow có thể orchestration các bước lớn trong khi từng service vẫn dùng event choreography nội bộ. DSL cần xác định ranh giới trách nhiệm và hợp đồng event giữa các service.

## 16. Event sourcing và workflow events

Event sourcing lưu chuỗi event như nguồn dữ liệu chính để tái dựng state. Workflow events là những event kích hoạt hoặc cập nhật tiến trình. Hai khái niệm liên quan nhưng không đồng nghĩa.

### 16.1. Event sourcing

Ví dụ aggregate đơn hàng có event log:

```text
OrderCreated
ItemAdded
PaymentCaptured
ShipmentDispatched
```

State hiện tại được dựng bằng cách áp dụng lần lượt các event.

### 16.2. Workflow event

Workflow có thể nhận `PaymentCaptured` từ aggregate nhưng chỉ lưu trạng thái tiến trình của chính nó. Nó không nhất thiết lưu toàn bộ event log nghiệp vụ.

### 16.3. Replay và side effects

Khi replay event để dựng state, không nên thực hiện lại email, thanh toán hoặc gọi dịch vụ ngoài. Có thể tách pure state reducer khỏi side-effect handlers hoặc dùng chế độ replay chuyên biệt.

### 16.4. Snapshot

Event stream dài có thể dùng snapshot để giảm thời gian khôi phục. Snapshot cần gắn version và có thể tái dựng từ event log nếu cần.

## 17. Event schema và versioning

Event thường được tiêu thụ bởi nhiều service có vòng đời triển khai độc lập. Schema vì vậy cần được quản lý version và tương thích.

### 17.1. Additive changes

Thêm trường optional thường dễ tương thích hơn thay đổi kiểu hoặc xóa trường. Consumer cũ có thể bỏ qua trường mới nếu format và contract cho phép.

### 17.2. Breaking changes

Đổi tên field, đổi kiểu, thay ý nghĩa hoặc đổi requiredness có thể làm consumer cũ lỗi. Có thể phát event type/version mới hoặc dùng schema registry và migration adapter.

### 17.3. Upcasting

Consumer có thể chuyển event phiên bản cũ thành mô hình nội bộ mới trước khi xử lý. Upcaster cần xác định default hoặc cách suy ra trường mới mà không bịa dữ liệu.

### 17.4. Consumer-driven compatibility

Producer cần biết các consumer đang hỗ trợ phiên bản nào. Contract tests hoặc schema compatibility checks giúp phát hiện thay đổi phá vỡ consumer trước khi publish.

### 17.5. Event type naming

Event type nên có namespace hoặc domain prefix để tránh trùng tên giữa các bounded context, ví dụ `sales.OrderSubmitted` và `billing.InvoiceIssued`.

## 18. Event routing và filtering

Event routing quyết định event được chuyển đến handler, workflow hoặc queue nào.

### 18.1. Routing theo type

Định tuyến theo event type là cách cơ bản nhất. Ví dụ topic `payments.captured` chỉ chứa event thanh toán đã thu tiền.

### 18.2. Routing theo payload

Có thể lọc theo tenant, region, amount hoặc resource ID. Predicate cần được giới hạn và có thể index để tránh scan toàn bộ message.

### 18.3. Fan-out

Một event có thể được gửi đến nhiều consumer độc lập: workflow fulfillment, analytics và notification. Mỗi consumer cần subscription riêng và không nên phụ thuộc thứ tự xử lý của consumer khác.

### 18.4. Competing consumers

Nhiều worker cùng tiêu thụ một queue để chia tải. Mỗi message thường được giao cho một worker tại một thời điểm, nhưng có thể được giao lại sau lỗi. Idempotency vẫn cần thiết.

### 18.5. Tenant routing

Trong hệ thống multi-tenant, event cần được gắn tenant context và được lọc/ủy quyền đúng. Không nên cho phép payload tự do chỉ định tenant đích mà không kiểm tra quyền.

## 19. Event time, timers và deadline

Workflow thường chờ một event đến trước deadline. Timer có thể được mô hình hóa như một event hệ thống.

Ví dụ:

```text
wait for CustomerConfirmed
    timeout 48h
    on timeout -> ExpireReservation
```

### 19.1. Durable timer

Với workflow chạy lâu, timer cần được lưu bền vững để không mất khi runtime restart. Khi đến hạn, scheduler phát timer event hoặc đánh dấu subscription hết hạn.

### 19.2. Race giữa event và timeout

Event có thể đến đúng lúc timer hết hạn. Runtime cần một quy tắc xác định: event được ghi nhận trước deadline theo event time, hay theo thời điểm runtime nhận; hoặc dựa vào thứ tự commit. Quy tắc phải nhất quán.

### 19.3. Hủy timer

Khi event hợp lệ đến và workflow tiếp tục, timer tương ứng cần được hủy hoặc đánh dấu inactive. Nếu timer vẫn phát sau đó, handler phải nhận biết subscription đã kết thúc.

### 19.4. Business calendar

Một số deadline tính theo ngày làm việc hoặc múi giờ nghiệp vụ. DSL có thể hỗ trợ calendar/time zone thay vì cộng thời lượng đơn giản. Cần phân biệt duration 24 giờ với một ngày lịch.

## 20. Compensation và sự kiện lỗi

Workflow dài có thể đã thực hiện một số hành động trước khi nhận event lỗi. Khi đó, có thể cần compensation để đưa hệ thống về trạng thái nghiệp vụ phù hợp.

Ví dụ:

```text
ReserveInventory
    | InventoryReserved
    v
CapturePayment
    | PaymentDeclined
    v
ReleaseInventory
    | InventoryReleased
    v
CancelOrder
```

### 20.1. Compensation không phải rollback database

Rollback transaction chỉ đảo thay đổi trong một transaction database. Compensation là hành động nghiệp vụ mới, ví dụ hoàn tiền hoặc giải phóng tồn kho, có thể thất bại và cần retry.

### 20.2. Error event

Có thể phát event như `PaymentServiceUnavailable` hoặc `InventoryReservationFailed`. Workflow phân loại lỗi để retry, compensation hoặc yêu cầu người vận hành can thiệp.

### 20.3. Escalation

Nếu event không đến hoặc retry vượt ngưỡng, workflow có thể phát `ManualReviewRequired` hoặc tạo task cho người vận hành.

### 20.4. Audit lỗi

Cần lưu loại lỗi, bước xảy ra, attempt count, event ID liên quan và hành động compensation. Không ghi dữ liệu nhạy cảm hoặc payload đầy đủ nếu không cần.

## 21. Bảo mật event

Event có thể chứa thông tin cá nhân, dữ liệu tài chính hoặc chỉ thị nghiệp vụ. Hệ thống cần xác thực producer, phân quyền consumer và bảo vệ payload.

### 21.1. Authentication và producer identity

Runtime cần biết ai phát event. Có thể dùng mutual TLS, chữ ký message, broker ACL hoặc token service-to-service. Chỉ kiểm tra trường `source` trong payload là không đủ vì trường đó có thể bị giả mạo.

### 21.2. Authorization theo event và workflow

Không phải producer nào cũng được phát mọi event. Ví dụ chỉ payment service được phát `PaymentCaptured`; người dùng cuối có thể gửi `CustomerConfirmed` cho đơn thuộc quyền của họ.

### 21.3. Payload minimization

Chỉ gửi dữ liệu cần thiết cho consumer. Nếu event chỉ cần `customerId`, không nên đính kèm toàn bộ hồ sơ khách hàng.

### 21.4. Encryption

Bảo vệ dữ liệu khi truyền và khi lưu trong broker hoặc event store. Secret và credential nên được tham chiếu qua secret manager thay vì nhúng vào event.

### 21.5. Replay protection

Kẻ tấn công có thể phát lại event hợp lệ đã bắt được. Event ID, timestamp/nonce, signature và deduplication window giúp hạn chế replay. Consumer vẫn cần kiểm tra state transition và authorization.

### 21.6. Tenant isolation

Correlation ID và business key phải được kiểm tra trong tenant scope. Không được resume workflow của tenant khác chỉ vì event gửi một ID trùng hoặc biết được.

## 22. Quan sát và vận hành event workflow

Workflow event-driven khó theo dõi nếu chỉ xem log từng service. Cần telemetry liên kết event, workflow instance và handler.

Các metric hữu ích:

- Số event nhận, xử lý, retry và dead-letter.
- Thời gian từ `occurredAt` đến processing time.
- Độ trễ từ event đến workflow resume.
- Số workflow đang chờ theo event type.
- Số subscription hết hạn hoặc timer quá hạn.
- Tỷ lệ handler lỗi và duplicate.
- Số event bị từ chối do schema hoặc authorization.

### 22.1. Correlated logs

Log nên mang `eventId`, `correlationId`, `workflowId`, `stepId` và `traceId` để truy vết một luồng qua nhiều service.

### 22.2. Event trace

Có thể hiển thị timeline:

```text
10:00:00 OrderSubmitted
10:00:01 CapturePayment requested
10:00:04 PaymentCaptured received
10:00:04 Workflow resumed
10:00:06 InventoryReserved received
10:00:07 Shipment created
```

Timeline giúp phát hiện event đến muộn, retry kéo dài hoặc workflow bị kẹt ở trạng thái chờ.

### 22.3. PII và log redaction

Không nên ghi toàn bộ payload vào log mặc định. Có thể ghi metadata, event type và ID; trường nhạy cảm phải được redact hoặc loại bỏ.

## 23. Kiểm thử event-driven workflow

Kiểm thử cần bao phủ luồng bình thường và các trường hợp giao nhận không lý tưởng.

Các trường hợp quan trọng:

1. Event hợp lệ resume đúng workflow instance.
2. Event không khớp correlation không làm thay đổi instance khác.
3. Event sai schema bị từ chối với diagnostic rõ.
4. Duplicate event không tạo duplicate side effect.
5. Event đến sai thứ tự được xử lý theo policy.
6. Event đến sau timeout không kích hoạt transition đã hết hạn.
7. Retry transient error theo backoff đã cấu hình.
8. Permanent error không retry vô hạn.
9. DLQ giữ được message và metadata cần điều tra.
10. Workflow persistence khôi phục đúng sau restart.
11. Outbox/inbox tránh mất hoặc xử lý lặp ngoài ý muốn.
12. Schema version cũ được upcast hoặc xử lý tương thích.
13. Authorization chặn producer/consumer không hợp lệ.
14. Tenant isolation không bị phá qua correlation ID.
15. Compensation được kích hoạt khi bước sau thất bại.
16. Replay không lặp tác dụng phụ ngoài ý muốn.
17. Timer/event race có kết quả xác định.
18. Trace và audit liên kết được toàn bộ luồng.

### 23.1. Contract tests

Producer và consumer cần thống nhất event schema. Contract test xác nhận producer phát đúng cấu trúc và consumer có thể đọc các version được hỗ trợ.

### 23.2. Integration tests với broker

Kiểm tra acknowledgement, retry, redelivery, partition ordering và dead-letter trên broker hoặc test harness tương thích.

### 23.3. Deterministic workflow tests

Có thể dùng fake clock, event fixture và scheduler giả để kiểm tra timer mà không phải chờ thời gian thật. Event input và expected transitions nên được cố định để test có thể lặp lại.

### 23.4. Chaos/failure tests

Mô phỏng broker unavailable, consumer crash sau commit, duplicate delivery, event delay và network partition để xác nhận workflow phục hồi đúng.

## 24. Ví dụ tổng hợp: workflow xử lý đơn hàng

Giả sử một DSL mô tả quy trình:

```text
event OrderSubmitted {
    orderId: OrderId
    customerId: CustomerId
    occurredAt: Instant
}

event PaymentCaptured {
    orderId: OrderId
    paymentId: PaymentId
    amount: Money
}

event PaymentDeclined {
    orderId: OrderId
    reason: String
}

event InventoryReserved {
    orderId: OrderId
    reservationId: ReservationId
}

event ShipmentDispatched {
    orderId: OrderId
    trackingCode: String
}

workflow fulfillOrder(orderId: OrderId) {
    let order = loadOrder(orderId)
    requestPayment(order)

    wait for PaymentCaptured
        where event.orderId == orderId
        timeout 15m
        as payment

    reserveInventory(order)

    wait for InventoryReserved
        where event.orderId == orderId
        timeout 30m
        as reservation

    createShipment(order, reservation)

    wait for ShipmentDispatched
        where event.orderId == orderId
        as shipment

    markOrderShipped(order, shipment.trackingCode)
}
```

### 24.1. Luồng thành công

1. `OrderSubmitted` tạo workflow instance hoặc kích hoạt workflow.
2. Workflow gọi `requestPayment` và lưu trạng thái chờ `PaymentCaptured`.
3. Payment service phát `PaymentCaptured` với `orderId` tương ứng.
4. Runtime xác thực event, kiểm tra correlation, deduplicate và resume workflow.
5. Workflow yêu cầu giữ hàng, chờ `InventoryReserved` rồi tạo shipment.
6. `ShipmentDispatched` đến và workflow cập nhật đơn hàng thành đã gửi.

### 24.2. Luồng thanh toán thất bại

Nếu nhận `PaymentDeclined`, workflow có thể chuyển sang `PaymentRejected`, thông báo khách hàng và kết thúc. Nó không nên chờ `PaymentCaptured` vô hạn.

### 24.3. Timeout

Nếu không có `PaymentCaptured` trong 15 phút, timer event kích hoạt `cancelPayment` hoặc chuyển đơn sang trạng thái cần kiểm tra. Subscription chờ thanh toán phải được vô hiệu hóa để event đến muộn không thực hiện bước tiếp theo.

### 24.4. Duplicate delivery

Nếu broker giao lại `PaymentCaptured`, event ID và inbox record giúp runtime nhận ra message đã xử lý. `reserveInventory` không được thực hiện lần thứ hai chỉ vì event bị gửi lại.

### 24.5. Trace

Tất cả event và command nên mang `correlationId` của workflow instance và `causationId` phù hợp để người vận hành dựng lại timeline.

## 25. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng command và event như nhau | Không rõ yêu cầu hay kết quả đã xảy ra | Tách command, event và query |
| Event payload không có identity/correlation | Không biết workflow instance nào cần resume | Dùng event ID và correlation/business key |
| Giả định event chỉ đến một lần | Side effect bị lặp khi broker redeliver | Idempotency và inbox/dedup |
| Giả định thứ tự toàn cục | Workflow chuyển state sai khi event đến lệch thứ tự | Sequence/version và ordering scope rõ |
| Chờ event không có timeout | Instance có thể bị treo vô hạn | Durable timer và timeout policy |
| Không hủy subscription sau timeout | Event muộn kích hoạt transition cũ | Quản lý lifecycle subscription |
| Publish sau database commit không có outbox | Database cập nhật nhưng event bị mất | Transactional outbox |
| Retry mọi lỗi | Lỗi vĩnh viễn tạo tải và duplicate vô hạn | Phân loại transient/permanent/business errors |
| Tin source/correlation trong payload | Có thể giả mạo producer hoặc workflow | Authentication, authorization và tenant checks |
| Thay đổi event schema phá consumer | Dịch vụ triển khai độc lập bị lỗi | Versioning và contract tests |
| Replay chạy lại side effects | Thu tiền/gửi email/đặt hàng nhiều lần | Tách state replay và side-effect handling |
| Không quan sát workflow timeline | Khó tìm điểm kẹt hoặc event bị mất | Correlated logs, metrics và trace |

## 26. Nguyên tắc thiết kế sự kiện quy trình

Khi xây dựng event model và workflow runtime, có thể áp dụng các nguyên tắc sau:

1. **Đặt tên event theo sự kiện đã xảy ra.** Phân biệt event với command và query.
2. **Định nghĩa schema có kiểu.** Payload, required fields và version phải rõ.
3. **Dùng event envelope.** Có ID, type, source, timestamp, correlation và causation khi cần.
4. **Tương quan đúng instance.** Không resume workflow chỉ dựa vào event type.
5. **Xác định ordering scope.** Theo aggregate, workflow hoặc partition; không giả định thứ tự toàn cục.
6. **Chọn delivery semantics thực tế.** Thường dùng at-least-once cùng consumer idempotent.
7. **Thiết kế deduplication.** Event ID hoặc operation ID phải ổn định.
8. **Có retry và timeout hữu hạn.** Phân loại lỗi, dùng backoff và DLQ.
9. **Dùng outbox/inbox khi cần tính nhất quán.** Gắn publish/consume với transaction dữ liệu.
10. **Quản lý subscription lifecycle.** Đăng ký, resume, timeout, cancel và cleanup rõ ràng.
11. **Version event contract.** Kiểm tra compatibility giữa producer và consumer.
12. **Bảo vệ event.** Xác thực producer, phân quyền consumer, giảm payload và cô lập tenant.
13. **Tách replay khỏi side effects.** Không lặp hành động bên ngoài khi dựng lại state.
14. **Quan sát được toàn bộ luồng.** Dùng correlation, trace, metrics và audit.
15. **Kiểm thử lỗi phân tán.** Duplicate, delay, out-of-order, crash, retry và restart phải có test.

## 27. Kết luận

Sự kiện quy trình là tín hiệu cho biết một điều đã xảy ra và có thể làm workflow bắt đầu, tiếp tục hoặc chuyển trạng thái. Event khác command và state: command yêu cầu hành động, state mô tả tình trạng hiện tại, còn event ghi nhận sự kiện đã xảy ra. Trong DSL, event type và payload có kiểu giúp compiler kiểm tra hợp đồng giữa producer, consumer và workflow.

Một workflow event-driven đáng tin cậy cần correlation để tìm đúng instance, ordering policy để xử lý message đến lệch thứ tự, idempotency để chịu được duplicate, retry/timeout để phục hồi và outbox/inbox để phối hợp với transaction. Schema versioning, authorization, tenant isolation và telemetry giúp hệ thống an toàn và có thể vận hành.

Khi DSL mô tả rõ event, subscription, guard, timeout và hành vi lỗi, runtime có thể điều phối quy trình dài hạn mà không cần giữ một lời gọi đồng bộ liên tục. Điều đó giúp kết nối các dịch vụ độc lập, phản ứng với thay đổi nghiệp vụ và theo dõi toàn bộ tiến trình một cách có kiểm soát.

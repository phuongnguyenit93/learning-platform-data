# Saga với điều phối tập trung và phối hợp qua sự kiện

Một giao dịch nghiệp vụ thường đi qua nhiều dịch vụ. Khi khách hàng đặt lịch, hệ thống có thể phải giữ khung giờ, tạo booking, ghi nhận thanh toán, phát sự kiện và gửi thông báo. Mỗi dịch vụ sở hữu dữ liệu riêng và commit transaction trong database của mình. Không có một transaction ACID duy nhất bao trùm mọi database và API bên ngoài. Nếu bước thanh toán thành công nhưng bước xác nhận lịch thất bại, hệ thống phải làm gì?

**Saga** là mẫu thiết kế để thực hiện một giao dịch nghiệp vụ dài qua nhiều dịch vụ bằng chuỗi **local transaction**. Mỗi bước commit trong ranh giới dữ liệu của dịch vụ sở hữu nó. Nếu một bước không thể tiếp tục, workflow chạy các hành động **compensation** đã định nghĩa để đưa nghiệp vụ về trạng thái chấp nhận được. Saga thường có hai cách tổ chức: **orchestration** (điều phối tập trung) và **choreography** (các dịch vụ phối hợp qua sự kiện).

Hai cách đều hướng tới xử lý workflow phân tán mà không giữ transaction database mở xuyên nhiều dịch vụ. Chúng có đánh đổi khác nhau về mức độ tập trung logic, coupling, khả năng quan sát, vận hành, độ phức tạp event và phục hồi. Saga không biến hệ thống thành một transaction ACID toàn cục, và compensation không bảo đảm đảo ngược hoàn toàn một hành động đã xảy ra bên ngoài.

Bài học thuộc phần **Tính nhất quán** của học phần thiết kế kiến trúc đám mây. Trọng tâm là lựa chọn ranh giới dịch vụ và mô hình triển khai để cân bằng tính đúng đắn nghiệp vụ, độ tin cậy, bảo mật, khả năng mở rộng, chi phí và khả năng vận hành theo tư duy Well-Architected.

Sau bài học, bạn có thể:

- Giải thích Saga và lý do cần local transaction cùng compensation trong workflow nhiều dịch vụ.
- Phân biệt điều phối tập trung với phối hợp qua sự kiện.
- Thiết kế trạng thái, transition, timeout, retry và xử lý lỗi cho một Saga.
- Áp dụng transactional outbox/inbox, idempotency và xử lý event trùng hoặc sai thứ tự.
- Xác định điểm không thể hoàn tác, hành động bù và quy trình reconciliation.
- Chọn orchestration, choreography hoặc kết hợp dựa trên độ phức tạp và ranh giới sở hữu dịch vụ.
- Kiểm thử và quan sát workflow phân tán, đồng thời đánh giá các đánh đổi Well-Architected.

## 1. Vì sao cần Saga?

Xét quy trình đặt lịch gồm các bước:

1. Booking Service xác nhận khung giờ còn trống và giữ lịch.
2. Payment Service thực hiện thanh toán hoặc giữ tiền.
3. Booking Service xác nhận lịch hẹn.
4. Notification Service gửi email/SMS.

Mỗi service có database và transaction riêng. Nếu ứng dụng giữ một transaction database mở trong lúc gọi network đến ba service khác, nó có thể giữ lock quá lâu, tăng connection usage, dễ timeout và không thể tự động rollback một giao dịch đã commit ở database khác hoặc một khoản tiền đã charge tại payment provider.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant B as Booking Service
    participant P as Payment Service
    participant N as Notification Service
    C->>B: Tạo booking
    B->>B: Local transaction: giữ slot
    B->>P: Yêu cầu thanh toán
    P->>P: Local transaction/provider call
    P-->>B: Thanh toán thành công
    B->>B: Local transaction: xác nhận booking
    B->>N: Phát yêu cầu thông báo
    N-->>B: Đã nhận yêu cầu
    B-->>C: Trả kết quả
~~~

Đường đi thành công có vẻ đơn giản. Nhưng nếu service chết sau khi payment thành công, response bị mất, event bị phát trùng hoặc notification provider tạm ngừng, hệ thống cần biết nghiệp vụ đang ở bước nào và cách tiếp tục.

Saga chia workflow thành các **bước cục bộ có kết quả bền vững**. Mỗi bước được thực hiện idempotent; coordinator hoặc event handler theo dõi tiến trình. Khi thất bại, Saga gọi compensation cho những bước đã hoàn thành và có thể bù.

### Saga không phải distributed transaction

| Cách tiếp cận | Cơ chế | Đánh đổi chính |
| --- | --- | --- |
| Một database transaction | ACID trong một ranh giới database | Đơn giản về atomicity, nhưng không bao trùm nhiều service/database |
| Distributed transaction/2PC | Coordinator yêu cầu participant prepare rồi commit/abort | Participant phải hỗ trợ; có thể giữ resource và tăng coupling |
| Saga | Nhiều local transaction và compensation | Tính nhất quán đạt dần; cần state, retry, compensation và vận hành |

Saga phù hợp khi workflow kéo dài, nhiều service sở hữu dữ liệu riêng hoặc có bước gọi hệ thống ngoài. Nếu toàn bộ nghiệp vụ nằm trong một database và có thể giải quyết bằng transaction ngắn, thêm Saga sẽ làm hệ thống phức tạp không cần thiết.

## 2. Local transaction, compensation và trạng thái nghiệp vụ

Một Saga gồm các bước nghiệp vụ. Mỗi bước:

- Thực hiện thay đổi trong phạm vi sở hữu dữ liệu của service.
- Commit local transaction trước khi thông báo kết quả.
- Có operation ID hoặc Saga ID để truy vết.
- Có thể retry an toàn bằng idempotency/deduplication.
- Khi thất bại, phát kết quả để workflow quyết định tiếp tục, retry hoặc compensation.

**Compensation** là hành động nghiệp vụ mới nhằm bù đắp tác động của một bước trước đó. Nó không nhất thiết xóa dấu vết cũ hoặc khôi phục chính xác trạng thái vật lý như chưa từng xảy ra.

| Bước đã hoàn tất | Compensation có thể dùng | Giới hạn |
| --- | --- | --- |
| Giữ khung giờ | Giải phóng hold | Nếu hold đã hết hạn hoặc slot đã được phân bổ lại, cần kiểm tra owner/version |
| Tạo đơn hàng | Đánh dấu cancelled | Giữ lịch sử để audit; không xóa dấu vết |
| Giữ tiền (authorization) | Void/release authorization | Phụ thuộc trạng thái và thời hạn của provider |
| Charge tiền | Refund | Refund là giao dịch mới, có thể chậm, tốn phí hoặc cần xử lý thủ công |
| Gửi email | Gửi thông báo sửa/đính chính | Không thể thu hồi email người nhận đã đọc |
| Cấp quyền | Thu hồi quyền | Token đã cấp có thể còn hiệu lực tới khi hết hạn hoặc bị revoke |

Không nên mô tả compensation như câu lệnh ROLLBACK toàn hệ thống. Ví dụ đã gửi email “Đặt lịch thành công” thì không thể xóa email khỏi hộp thư khách hàng. Hệ thống có thể gửi thông báo sửa đổi hoặc hủy lịch, nhưng đó là một sự kiện mới.

### Forward recovery và backward recovery

Khi lỗi xảy ra, có hai hướng:

- **Forward recovery:** tiếp tục hoàn thành workflow sau khi khắc phục nguyên nhân, ví dụ retry một service tạm thời không khả dụng.
- **Backward recovery/compensation:** bù các bước đã thực hiện để kết thúc Saga ở trạng thái thất bại hoặc hủy.

Không phải lỗi nào cũng nên compensation ngay. Nếu Payment Service timeout và chưa biết giao dịch đã charge hay chưa, refund mù quáng hoặc charge lại có thể tạo sai lệch. Trước tiên cần tra cứu trạng thái giao dịch bằng operation ID/provider reference.

### Thiết kế trạng thái rõ ràng

~~~text
PENDING
  -> SLOT_HELD
  -> PAYMENT_PENDING
  -> PAYMENT_AUTHORIZED
  -> CONFIRMED
  -> COMPLETED

Các nhánh lỗi:
  PAYMENT_FAILED
  PAYMENT_UNKNOWN
  CANCEL_PENDING
  COMPENSATING
  CANCELLED
  MANUAL_REVIEW
~~~

Tên trạng thái chỉ là ví dụ. Nên phản ánh điều đã biết, không kết luận quá sớm. PAYMENT_UNKNOWN hữu ích hơn PAYMENT_FAILED khi request tới provider timeout và kết quả chưa rõ.

## 3. Hai kiểu tổ chức Saga

### 3.1. Orchestration — điều phối tập trung

Trong orchestration, một **Saga orchestrator/coordinator** sở hữu định nghĩa workflow và quyết định bước kế tiếp dựa trên trạng thái cùng kết quả nhận được. Nó gửi command tới service tham gia, nhận response/event, lưu tiến trình và điều khiển retry hoặc compensation.

~~~mermaid
flowchart TD
    CLIENT["Client"] --> ORCH["Booking Saga Orchestrator<br/>State + transition"]
    ORCH -->|"ReserveSlot command"| BOOK["Booking Service"]
    BOOK -->|"SlotHeld / SlotRejected"| ORCH
    ORCH -->|"AuthorizePayment command"| PAY["Payment Service"]
    PAY -->|"PaymentAuthorized / PaymentDeclined"| ORCH
    ORCH -->|"ConfirmBooking command"| BOOK
    BOOK -->|"BookingConfirmed"| ORCH
    ORCH -->|"SendNotification command"| NOTIFY["Notification Service"]
    NOTIFY -->|"Accepted / Failed"| ORCH
    ORCH --> RESULT["Saga result / status"]
~~~

Orchestrator có thể là state machine managed, workflow engine, service riêng hoặc thư viện trong ứng dụng. Nó cần lưu state bền vững, không chỉ dựa vào RAM của một process.

**Ưu điểm:**

- Workflow và thứ tự bước được nhìn thấy tại một nơi.
- Timeout, retry, deadline, compensation và manual review có thể được định nghĩa tường minh.
- Dễ xem trạng thái toàn Saga và xác định bước đang chờ.
- Có thể quản lý workflow dài với timer, human approval và nhánh điều kiện.

**Đánh đổi:**

- Orchestrator là thành phần quan trọng cần HA, backup/restore, access control và giám sát.
- Participant phụ thuộc command contract và semantics do coordinator định nghĩa.
- Workflow trung tâm có thể phình lớn, chứa logic nghiệp vụ thuộc service khác.
- Nếu coordinator phát command nhưng không lưu checkpoint đúng, duplicate hoặc state divergence có thể xảy ra.

Orchestrator nên điều phối **tiến trình**, không chiếm quyền sở hữu dữ liệu participant. Booking Service vẫn quyết định slot có thể giữ hay không; Payment Service vẫn quyết định trạng thái thanh toán theo dữ liệu của mình.

### 3.2. Choreography — phối hợp qua sự kiện

Trong choreography, không có một coordinator quyết định mọi bước. Mỗi service nhận event liên quan, thực hiện local transaction và phát event kết quả. Workflow hình thành từ chuỗi sự kiện và quy tắc phản ứng của các service.

~~~mermaid
flowchart LR
    B["Booking Service"] -->|"BookingRequested"| E1[("Event Bus")]
    E1 --> P["Payment Service"]
    P -->|"PaymentAuthorized"| E2[("Event Bus")]
    E2 --> B
    B -->|"BookingConfirmed"| E3[("Event Bus")]
    E3 --> N["Notification Service"]
    P -->|"PaymentDeclined"| E4[("Event Bus")]
    E4 --> B
    B -->|"BookingCancelled"| E5[("Event Bus")]
    E5 --> N
~~~

Booking Service phát BookingRequested; Payment Service phản ứng và phát PaymentAuthorized hoặc PaymentDeclined; Booking Service lại cập nhật trạng thái và phát event tiếp theo.

**Ưu điểm:**

- Các service có thể độc lập phản ứng và mở rộng theo lượng event.
- Producer không nhất thiết biết mọi consumer.
- Phù hợp với workflow đơn giản, event là ranh giới tích hợp tự nhiên.
- Giảm sự phụ thuộc đồng bộ vào một coordinator trung tâm.

**Đánh đổi:**

- Toàn bộ trình tự nghiệp vụ khó nhìn thấy hơn khi logic nằm rải trong nhiều event handler.
- Quan hệ phụ thuộc ẩn có thể tăng khi một event có nhiều consumer.
- Debug, replay và xác định Saga mắc ở đâu phức tạp hơn.
- Khó quản lý timeout tổng thể, compensation nhiều bước và human intervention nếu thiếu cơ chế theo dõi.

Choreography không có nghĩa không cần quản lý workflow. Vẫn cần Saga ID, correlation, event schema, trạng thái bền vững, timeout, dead-letter handling và công cụ quan sát tiến trình.

### 3.3. So sánh trực tiếp

| Tiêu chí | Orchestration | Choreography |
| --- | --- | --- |
| Nơi định nghĩa luồng | Tập trung ở coordinator | Phân tán qua event handler và contract |
| Điều khiển bước kế tiếp | Coordinator ra lệnh | Service phản ứng với event |
| Quan sát end-to-end | Thường dễ hơn nếu state machine lưu đầy đủ | Cần correlation và công cụ tổng hợp |
| Coupling | Participant phụ thuộc command/contract | Producer/consumer phụ thuộc event schema và semantics |
| Timeout/compensation | Có thể khai báo rõ trong workflow | Phải phân tán hoặc dùng công cụ phụ trợ |
| Workflow nhiều nhánh | Dễ thể hiện tường minh hơn | Khó theo dõi khi nhiều service tham gia |
| Tự chủ service | Coordinator điều phối; domain vẫn sở hữu local data | Service tự quyết định phản ứng trong domain |
| Vận hành | Tập trung vận hành coordinator và participant | Vận hành nhiều consumer, event flow và correlation |
| Phù hợp | Quy trình quan trọng, nhiều bước/nhánh, cần audit | Luồng event đơn giản, consumer độc lập |

Không có lựa chọn luôn tốt hơn. Hệ thống có thể kết hợp: orchestrator quản lý các bước cốt lõi, trong khi notification, analytics hoặc audit được phát qua event và hoạt động độc lập.

## 4. Thiết kế Saga orchestration

Một orchestration Saga thường có:

- **Saga ID:** định danh duy nhất cho một lần chạy workflow.
- **State store:** trạng thái hiện tại, dữ liệu cần thiết và checkpoint.
- **Command dispatcher:** gửi lệnh đến participant.
- **Result/event handler:** nhận kết quả, xác thực correlation và cập nhật state.
- **Timer/deadline:** kiểm soát timeout tổng hoặc từng bước.
- **Retry policy:** lỗi nào có thể thử lại, số lần và khoảng cách.
- **Compensation handler:** chạy hành động bù theo thứ tự phù hợp.
- **Operational controls:** cancellation, pause, resume, manual review và audit.

### Ví dụ state machine đặt lịch

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> SLOT_HELD: ReserveSlotSucceeded
    PENDING --> FAILED: ReserveSlotRejected
    SLOT_HELD --> PAYMENT_PENDING: AuthorizePayment
    PAYMENT_PENDING --> PAYMENT_AUTHORIZED: PaymentAuthorized
    PAYMENT_PENDING --> PAYMENT_UNKNOWN: ProviderTimeout
    PAYMENT_PENDING --> COMPENSATING: PaymentDeclined
    PAYMENT_UNKNOWN --> PAYMENT_AUTHORIZED: ReconcileAuthorized
    PAYMENT_UNKNOWN --> COMPENSATING: ReconcileNotAuthorized
    PAYMENT_AUTHORIZED --> CONFIRMING: ConfirmBooking
    CONFIRMING --> CONFIRMED: BookingConfirmed
    CONFIRMING --> COMPENSATING: ConfirmFailed
    COMPENSATING --> CANCELLED: CompensationCompleted
    COMPENSATING --> MANUAL_REVIEW: CompensationFailed
    CONFIRMED --> [*]
    CANCELLED --> [*]
    FAILED --> [*]
~~~

State machine có PAYMENT_UNKNOWN vì timeout không đủ thông tin kết luận payment thất bại. Orchestrator phải tra cứu hoặc nhận event xác nhận trước khi chọn compensation.

### Command và event là hai loại thông điệp khác nhau

- **Command:** yêu cầu một service thực hiện hành động, ví dụ AuthorizePayment hoặc ReserveSlot.
- **Event:** sự kiện đã xảy ra, ví dụ PaymentAuthorized hoặc SlotHeld.

Command có thể bị từ chối hoặc timeout; event mô tả sự kiện đã phát sinh. Không đặt tên event như mệnh lệnh còn chưa thực hiện.

### State persistence và checkpoint

Mỗi lần nhận kết quả, orchestrator nên cập nhật state và kế hoạch bước kế tiếp nhất quán. Nếu dùng database riêng:

1. Đọc version hiện tại của Saga.
2. Kiểm tra message có thuộc Saga và đúng bước/version không.
3. Cập nhật state bằng optimistic concurrency hoặc transaction.
4. Lưu command tiếp theo trong outbox.
5. Commit rồi dispatcher gửi command.

Nếu dispatcher gửi command trước khi commit checkpoint, orchestrator có thể chết và phát lại lệnh không có dấu vết. Nếu commit checkpoint trước rồi chết trước khi gửi command, workflow mắc kẹt. Outbox giúp xử lý khoảng trống giữa cập nhật state và phát thông điệp.

## 5. Thiết kế Saga choreography

Mỗi consumer trong choreography cần:

- Validate event schema và nguồn phát.
- Kiểm tra Saga ID, event ID và loại event.
- Thực hiện local transaction.
- Ghi event đã xử lý/inbox để tránh lặp.
- Ghi event tiếp theo vào outbox cùng local transaction.
- ACK message sau khi xử lý bền vững theo semantics broker.
- Có retry, DLQ và quy trình replay.

### Ví dụ event flow

~~~text
BookingRequested (sagaId, bookingId)
    -> Payment Service:
         authorize payment
         emit PaymentAuthorized or PaymentDeclined

PaymentAuthorized
    -> Booking Service:
         confirm booking
         emit BookingConfirmed

PaymentDeclined
    -> Booking Service:
         release slot
         emit BookingCancelled

BookingConfirmed
    -> Notification Service:
         send confirmation notification
~~~

Đây là bản tóm tắt luồng, không thay thế schema và transition thực tế. Cần định nghĩa rõ điều gì xảy ra nếu PaymentAuthorized đến hai lần, BookingRequested bị phát trễ hoặc event đến sau khi booking đã hủy.

### Khi một event có nhiều consumer

Ví dụ BookingConfirmed được Booking Service phát; Notification Service gửi email, Analytics cập nhật báo cáo, Audit Service ghi log. Producer không cần biết tất cả consumer, nhưng từng consumer có trạng thái xử lý riêng. Notification lỗi không nên buộc booking quay về PENDING nếu nghiệp vụ đã xác nhận và thông báo chỉ là tác vụ phụ.

Phải phân biệt **core transaction** và **side effect phụ**. Không để lỗi của một consumer phụ đảo ngược giao dịch cốt lõi nếu hợp đồng nghiệp vụ không yêu cầu.

## 6. Transactional outbox và inbox

Một lỗi phổ biến trong event-driven Saga:

1. Service commit thay đổi database.
2. Service gửi message đến broker.
3. Process chết giữa hai bước.

Nếu gửi message trước commit, consumer có thể nhận event cho dữ liệu chưa commit. Nếu commit trước rồi chết, event không được gửi. **Transactional outbox** giải quyết bằng cách ghi dữ liệu nghiệp vụ và event record trong cùng local transaction.

~~~mermaid
flowchart TD
    S["Service command/event handler"] --> TX["Local database transaction"]
    TX --> DATA["Business data update"]
    TX --> OUT["Outbox event record"]
    OUT --> RELAY["Outbox relay / CDC"]
    RELAY --> BROKER["Message broker"]
    BROKER --> CONSUMER["Consumer"]
    CONSUMER --> ITX["Consumer local transaction"]
    ITX --> INBOX["Inbox / processed message"]
    ITX --> NEXT["Business update + next outbox event"]
~~~

Outbox relay có thể phát cùng event nhiều hơn một lần nếu đã publish nhưng chưa ghi nhận trạng thái sent. Vì vậy consumer cần **inbox/deduplication** theo event ID hoặc cơ chế idempotent tương đương.

### Cấu trúc event tối thiểu

~~~json
{
  "eventId": "evt-01J9X...",
  "eventType": "PaymentAuthorized",
  "eventVersion": 1,
  "occurredAt": "2026-11-18T04:30:00Z",
  "sagaId": "saga-8a31",
  "correlationId": "req-71f2",
  "causationId": "cmd-229a",
  "aggregateId": "booking-9281",
  "producer": "payment-service",
  "data": {
    "paymentReference": "pay-5512",
    "amountMinor": 250000,
    "currency": "VND"
  }
}
~~~

Schema là minh họa. Event nên chứa reference và dữ liệu vừa đủ cho consumer, tránh gửi thông tin thẻ, secret hoặc payload cá nhân không cần thiết. Cần versioning, backward compatibility, validation và quyền publish/subscribe theo domain.

### Inbox xử lý trùng

Consumer có thể lưu eventId vào bảng inbox với unique constraint. Nếu event ID đã có và transaction trước đã commit, consumer bỏ qua side effect nghiệp vụ và ACK. Nếu cùng message được xử lý song song, unique claim bảo đảm chỉ một consumer có quyền thực hiện.

Inbox và thay đổi nghiệp vụ nên được commit cùng transaction khi nằm trong một database. Nếu side effect là gọi external provider, cần provider idempotency key hoặc reconciliation.

## 7. Retry, timeout và backoff

Không phải mọi lỗi đều cần compensation ngay. Phân loại lỗi giúp chọn đúng hướng:

| Loại lỗi | Ví dụ | Hành vi phù hợp |
| --- | --- | --- |
| Transient | 503, network reset, rate limit tạm thời | Retry có giới hạn, backoff và jitter |
| Permanent/business | Không còn slot, thẻ bị từ chối rõ ràng, không đủ quyền | Đánh dấu business failure và compensation nếu bước trước đã commit |
| Ambiguous | Timeout sau khi gửi payment command; không biết provider đã xử lý chưa | Query/reconcile bằng operation reference |
| Poison message/schema | Payload sai, version không hỗ trợ | DLQ, cảnh báo, sửa dữ liệu/consumer rồi replay |
| Resource exhaustion | DB connection pool cạn, quota hết | Backpressure, giảm concurrency, khắc phục capacity/quota |

### Exponential backoff có jitter

Một chính sách minh họa:

~~~text
delay(n) = random(0, min(maxDelay, baseDelay * 2^n))
~~~

Jitter giúp nhiều Saga không retry đồng loạt sau outage. Cần giới hạn cả số lần thử và deadline tổng; không retry vô hạn một dịch vụ đang hỏng.

### Timeout từng bước và toàn workflow

Saga nên có:

- **Step timeout:** tối đa một bước được phép chờ phản hồi.
- **Retry deadline:** thời gian tối đa thử lại lỗi transient.
- **Saga deadline:** thời hạn nghiệp vụ hoàn tất, ví dụ giữ slot không quá 10 phút.
- **Compensation deadline:** khoảng thời gian để hoàn tất hành động bù.
- **Manual review SLA:** thời hạn con người xử lý trường hợp không tự động xác định được.

Các con số phải xuất phát từ nghiệp vụ. Timeout quá ngắn làm workflow thất bại giả; timeout quá dài làm tài nguyên giữ chỗ và trải nghiệm khách hàng suy giảm.

## 8. Compensation và các trường hợp không thể đảo ngược

Thiết kế compensation trước khi production. Mỗi bước cần biết:

1. Side effect đã xảy ra ở đâu?
2. Có thể bù bằng hành động nào?
3. Hành động bù có idempotent không?
4. Có thể thất bại hoặc timeout không?
5. Nếu kết quả không rõ thì tra cứu thế nào?
6. Nếu compensation thất bại kéo dài thì ai xử lý?

| Local action | Compensation | Cách xác minh |
| --- | --- | --- |
| Hold slot | Release hold theo booking/Saga ID | Slot thuộc về ai và hold còn hiệu lực không |
| Authorize payment | Void authorization | Provider status và reference |
| Capture payment | Refund theo payment operation ID | Đối soát refund state, số tiền và currency |
| Confirm booking | Cancel booking nếu policy cho phép | Kiểm tra trạng thái, thông báo và chính sách hủy |
| Gửi email | Gửi correction/cancellation notice | Delivery status; không thể thu hồi email đã nhận |
| Gửi webhook đối tác | Gửi event điều chỉnh hoặc cancellation | Event reference và acknowledgement |

### Compensation có thể có thứ tự ngược

Nếu workflow gồm A → B → C, compensation thường thực hiện theo C → B → A vì bước sau có thể phụ thuộc tài nguyên bước trước. Nhưng đây không phải quy tắc tuyệt đối. Nghiệp vụ có thể yêu cầu chạy song song hoặc ưu tiên một hành động bù để giảm thiệt hại.

Ví dụ refund có thể cần khởi chạy sớm, trong khi giải phóng slot chỉ thực hiện sau khi provider xác nhận không còn giữ tiền. Phải ghi thứ tự theo dependency thực tế.

### Compensation thất bại

Không nên đánh dấu Saga CANCELLED nếu một compensation quan trọng chưa hoàn tất. Có thể chuyển sang COMPENSATION_PENDING, RECONCILIATION_REQUIRED hoặc MANUAL_REVIEW. Lưu bước compensation đã thử, lần thử, lỗi, thời điểm, provider reference, tài nguyên còn bị giữ, chủ sở hữu xử lý và deadline.

Một workflow được đánh dấu hoàn tất nhưng còn tiền chưa refund hoặc slot chưa release tạo ra trạng thái sai lệch khó điều tra.

## 9. Event ordering, concurrency và stale message

Saga có thể nhận event trùng, đến trễ hoặc sai thứ tự. Broker ordering thường chỉ có trong một phạm vi (partition, key, session hoặc group) và không tự đồng bộ mọi service.

Những trường hợp cần xử lý:

- PaymentAuthorized đến sau khi Saga đã chuyển sang CANCELLED.
- BookingRequested được phát lại sau khi booking đã được xác nhận.
- PaymentDeclined và PaymentAuthorized xuất hiện gần như đồng thời do retry/timeout ở provider.
- Consumer xử lý event version cũ sau khi aggregate đã cập nhật version mới.
- Hai command cùng thao tác trên một booking hoặc payment reference.

Cơ chế bảo vệ:

- Dùng **Saga ID**, **event ID**, **correlation ID**, **causation ID** để truy vết.
- Dùng **aggregate version/sequence** hoặc optimistic concurrency để phát hiện event stale.
- Kiểm tra transition hợp lệ trước khi cập nhật trạng thái.
- Dùng inbox/unique constraint để chống duplicate.
- Dùng lock/lease có fencing token nếu cần tuần tự hóa thao tác cùng aggregate.
- Thiết kế handler idempotent và event replay an toàn.
- Có dead-letter và quarantine cho event không thể xử lý tự động.

Không nên bỏ event chỉ vì đến sai thứ tự mà không lưu dấu vết. Có thể cần giữ chờ, đọc lại trạng thái nguồn hoặc chuyển sang reconciliation.

## 10. Workflow dài, user interaction và cancellation

Một Saga có thể mất vài giây, vài phút hoặc vài ngày. Ví dụ đặt dịch vụ cần chờ người dùng xác nhận thanh toán, nhân viên duyệt hoặc bên thứ ba phản hồi. Không nên giữ HTTP request mở trong toàn bộ thời gian workflow.

API thường trả một operation resource:

~~~http
HTTP/1.1 202 Accepted
Location: /v1/operations/saga-8a31
Retry-After: 2
Content-Type: application/json

{
  "sagaId": "saga-8a31",
  "status": "PAYMENT_PENDING"
}
~~~

Client có thể poll status endpoint, nhận webhook/callback hoặc dùng notification channel phù hợp. Status endpoint phải xác thực và kiểm tra quyền theo tenant.

Hủy workflow cũng là một command có điều kiện:

- Nếu chưa có side effect, có thể chuyển sang CANCELLED.
- Nếu slot đang hold, release theo booking ID/version.
- Nếu payment đang xử lý, tra cứu và quyết định void/refund khi có kết quả.
- Nếu booking đã xác nhận, áp dụng cancellation policy, phí và thông báo.
- Nếu dịch vụ đã hoàn tất, có thể cần quy trình hoàn tiền/khiếu nại riêng.

Không cho cancellation ghi đè trạng thái vô điều kiện. Cần version/transition rule để tránh cancellation đến đồng thời với confirmation.

## 11. Khi nào chọn orchestration và khi nào chọn choreography?

### Chọn orchestration khi:

- Workflow có nhiều bước tuần tự, điều kiện, nhánh và compensation.
- Có timeout tổng, lịch chờ, phê duyệt hoặc human intervention.
- Cần audit dễ hiểu về trạng thái của một lần giao dịch.
- Nghiệp vụ cần một nơi thể hiện rõ luồng từ đầu đến cuối.
- Có thể vận hành coordinator/state machine như một năng lực nền tảng tin cậy.

### Chọn choreography khi:

- Luồng event tương đối đơn giản và các service có quyền tự quyết theo domain.
- Một event có nhiều consumer độc lập như analytics, notification và audit.
- Cần giảm sự phụ thuộc vào coordinator trung tâm.
- Các team có năng lực quản lý schema, consumer, replay và observability.
- Không cần điều phối phức tạp qua nhiều nhánh và compensation.

### Kết hợp hai mô hình

Một mô hình phổ biến là orchestrator quản lý **core business transaction**, còn các tác vụ hậu xử lý phát event. Ví dụ orchestrator điều phối hold slot, authorize payment và confirm booking; sau BookingConfirmed, các consumer độc lập cập nhật search index, analytics, gửi email và thông báo đối tác.

Cách kết hợp tránh để notification failure làm rollback booking, đồng thời vẫn giữ core workflow có trạng thái rõ ràng.

## 12. Saga và eventual consistency

Vì các local transaction commit theo thời gian, có một khoảng mà các dịch vụ nhìn thấy trạng thái chưa đồng bộ. Đây là **eventual consistency** ở cấp workflow.

Ví dụ Payment Service đã authorize tiền nhưng Booking Service chưa xác nhận lịch. Trong vài giây, người dùng có thể thấy trạng thái PAYMENT_PENDING hoặc CONFIRMING. API không nên trả “đã đặt thành công” trước khi nghiệp vụ đạt state CONFIRMED.

Không phải mọi dữ liệu cần strong consistency toàn hệ thống:

- Booking status là nguồn chuẩn trong Booking Service.
- Payment status là nguồn chuẩn trong Payment Service.
- Search projection cập nhật bất đồng bộ và có độ trễ chấp nhận được.
- Notification history là lịch sử gửi, không quyết định booking có hiệu lực.

Một màn hình có thể hiển thị trạng thái gần nhất cùng timestamp hoặc trạng thái “đang xử lý” để tránh biểu diễn sai.

Nếu Saga giữ slot trong khi chờ payment, hold cần TTL và cơ chế gia hạn có giới hạn. Nếu người dùng bỏ đi, timeout phải kích hoạt compensation hoặc reconciliation. TTL của hold và deadline của Saga cần phối hợp; xóa hold trong khi payment vẫn đang xử lý có thể tạo thanh toán cho lịch không còn chỗ.

### Chỉ số nghiệp vụ cần theo dõi

- Tỷ lệ Saga hoàn tất trước deadline.
- Thời gian p50/p95/p99 từ request đến CONFIRMED.
- Số Saga ở PAYMENT_UNKNOWN hoặc MANUAL_REVIEW.
- Tuổi của hold slot và số hold quá hạn.
- Tỷ lệ compensation thành công và số lần retry.
- Số payment/booking mismatch được phát hiện qua reconciliation.
- Số event trễ, trùng, vào DLQ và backlog lâu.

## 13. Bảo mật và dữ liệu trong Saga

Saga thường kéo nhiều service và broker tham gia, làm tăng bề mặt truy cập:

- Mỗi service dùng service identity riêng và chỉ có quyền publish/subscribe đúng topic/queue.
- Command phải xác thực producer, tenant và quyền trong domain sở hữu.
- Không tin tenantId, amount, ownerId hoặc trạng thái thanh toán chỉ vì chúng xuất hiện trong event.
- Payment Service tự đọc/kiểm tra dữ liệu và áp dụng quy tắc của mình; consumer khác không thể tự kết luận payment hợp lệ.
- Event chỉ chứa dữ liệu tối thiểu; secret, token và card data không được phát rộng.
- Log/tracing phải che dữ liệu cá nhân và có access control/retention.
- State store của orchestrator chứa thông tin nhạy cảm cũng cần mã hóa và audit.
- Compensation endpoint cần authorization, chống replay ngoài ý muốn và ghi dấu vết.

Một lỗi thường gặp là orchestrator được cấp quyền quá rộng vào database của mọi service. Điều đó làm mất ranh giới sở hữu. Coordinator nên gửi command và nhận kết quả qua contract được kiểm soát, không truy vấn hoặc sửa trực tiếp database participant.

## 14. Observability, vận hành và reconciliation

Một Saga thành công không chỉ là message đã gửi hoặc handler trả 200. Cần nhìn thấy **một giao dịch từ đầu đến cuối**, kể cả khi nó chạy qua nhiều service và hàng đợi.

Mỗi command/event nên mang các định danh phù hợp:

- Saga ID: định danh lần chạy workflow.
- Correlation ID: nối các request/sự kiện cùng luồng.
- Causation ID: chỉ ra command/event nào gây ra thông điệp hiện tại.
- Event ID/command ID: chống lặp và truy vết từng thông điệp.
- Aggregate ID và version: xác định đối tượng và thứ tự cập nhật.
- Trace context: nối distributed trace qua các service.

| Tín hiệu | Ý nghĩa vận hành |
| --- | --- |
| Saga count theo state | Tìm workflow mắc hoặc tăng bất thường ở một bước |
| Saga age/deadline overdue | Xác định thao tác vượt thời hạn nghiệp vụ |
| Retry count theo dependency | Phát hiện downstream không ổn định |
| Compensation success/failure | Đo khả năng phục hồi và rủi ro còn lại |
| Outbox lag/publish failure | Phát hiện event chưa được phát |
| Inbox duplicate count | Quan sát redelivery và hoạt động dedup |
| DLQ depth/oldest age | Xác định poison message và công việc cần xử lý |
| Payment/booking mismatch | Phát hiện sai lệch nghiệp vụ quan trọng |
| Orchestrator execution error | Giám sát coordinator hoặc workflow runtime |

### Reconciliation là phần quan trọng của workflow

Ngay cả Saga được thiết kế tốt vẫn có thể gặp trạng thái không rõ do timeout, outage hoặc lỗi tích hợp. Reconciliation định kỳ so sánh trạng thái giữa các hệ thống:

1. Lấy các booking quá thời hạn PAYMENT_PENDING hoặc PAYMENT_UNKNOWN.
2. Tra cứu Payment Service/provider bằng payment reference.
3. So sánh payment state với booking state và hold state.
4. Thực hiện bước tiếp theo an toàn: confirm, void, refund, release hoặc manual review.
5. Ghi audit và kết quả reconciliation.

Reconciliation cần policy và quyền được duyệt; không phải quyền sửa dữ liệu trực tiếp tùy ý. Đây là cơ chế phát hiện và giải quyết sai lệch mà retry tự động không thể xác định.

## 15. Ví dụ đối chiếu hai mô hình cho đặt lịch

### Phương án A — Orchestration

Booking Saga Orchestrator lưu state. Nó gửi ReserveSlot, chờ SlotHeld, gửi AuthorizePayment, chờ kết quả, rồi gửi ConfirmBooking. Nếu payment declined, nó gửi ReleaseSlot. Nếu payment timeout, nó tra cứu trạng thái trước khi quyết định.

Khi notification service lỗi sau khi booking đã confirmed, orchestrator có thể ghi tác vụ notification pending hoặc phát event riêng. Nó không nhất thiết đảo ngược booking.

### Phương án B — Choreography

Booking Service phát BookingRequested. Payment Service nhận và thực hiện authorization, rồi phát PaymentAuthorized. Booking Service nhận event và xác nhận lịch. Notification Service nhận BookingConfirmed và gửi thông báo. Nếu PaymentDeclined, Booking Service giải phóng slot và phát BookingCancelled.

Các service dùng outbox/inbox, Saga ID, event ID và state riêng. Một dashboard hoặc workflow tracker cần tổng hợp tiến trình để nhân viên biết một booking đang chờ ở đâu.

| Tình huống | Orchestration | Choreography |
| --- | --- | --- |
| Payment timeout | Coordinator ghi PAYMENT_UNKNOWN, tra cứu và quyết định | Payment handler/reconciliation phát trạng thái; Booking phản ứng theo event |
| Booking confirm thất bại sau payment | Coordinator điều khiển void/refund và giải phóng slot | Payment/Booking event flow phối hợp compensation |
| Notification lỗi | Coordinator ghi tác vụ phụ hoặc event riêng | Notification consumer retry/DLQ độc lập |
| Một event đến lặp | Coordinator dedup command/result; participant vẫn idempotent | Mỗi consumer dùng inbox/dedup |
| Nhân viên cần xem một Saga | State machine có thể hiển thị step và deadline | Cần tổng hợp event/state từ nhiều service |

Choreography không nhất thiết ít thành phần hơn: nó có thể cần event bus, inbox/outbox, tracker, reconciliation và công cụ vận hành. Orchestration cũng không nhất thiết là điểm lỗi đơn nếu coordinator dùng state store và runtime có HA phù hợp.

## 16. Những sai lầm thường gặp

**Giữ một database transaction mở khi gọi nhiều service.** Network chậm làm lock và connection bị giữ lâu; transaction không bao trùm side effect ngoài database.

**Coi compensation là rollback chính xác.** Refund, gửi thông báo sửa hoặc hủy đơn là giao dịch mới; không thể xóa lịch sử một cách trung thực.

**Retry mù một payment command sau timeout.** Provider có thể đã charge; cần cùng idempotency key và reconciliation.

**Không có Saga ID hoặc correlation.** Khó nối log, event, command và trạng thái từ đầu tới cuối.

**Để workflow state chỉ nằm trong memory orchestrator.** Process restart có thể làm mất tiến trình; cần checkpoint bền vững.

**Phát event và commit database như hai thao tác không liên kết.** Crash giữa hai bước gây event mất hoặc event phát cho dữ liệu chưa commit; dùng outbox.

**Chỉ có outbox mà consumer không dedup.** Relay có thể phát lại; consumer cần inbox hoặc xử lý idempotent.

**Cho notification failure hủy booking không cần thiết.** Tách core transaction và side effect phụ theo yêu cầu nghiệp vụ.

**Không xử lý event đến trễ/sai thứ tự.** Dùng state transition, version/sequence, fencing hoặc reconciliation.

**Đánh dấu CANCELLED khi compensation còn dang dở.** Trạng thái nghiệp vụ phải phản ánh phần chưa hoàn tất và người chịu trách nhiệm.

**Chọn choreography vì tưởng không cần coordinator hoặc giám sát.** Luồng phân tán vẫn cần ownership, correlation, timeout và dashboard.

**Đưa logic domain participant vào orchestrator.** Coordinator nên điều khiển tiến trình; mỗi service vẫn sở hữu quyết định và dữ liệu của mình.

## 17. Bài thực hành: thiết kế Saga cho đặt lịch và thanh toán

**Bối cảnh giả định:** Một nền tảng đặt lịch có Booking Service, Payment Service và Notification Service. Mỗi service có database riêng. Người dùng chọn một slot, thanh toán, sau đó nhận thông báo. Payment provider có thể trả kết quả chậm hoặc timeout. Event broker giao message theo semantics at-least-once và có thể redeliver. Booking hold có TTL 10 phút. SLO mục tiêu là 99,9% booking hợp lệ được hoàn tất hoặc báo trạng thái xử lý rõ trong 30 ngày.

Các con số chỉ để luyện tập. Cần xác minh khả năng provider, broker và datastore khi triển khai thực tế.

### Nhiệm vụ

1. **Vẽ hai kiến trúc:** một sơ đồ orchestration và một sơ đồ choreography cho cùng workflow; đánh dấu service sở hữu dữ liệu, nơi quyết định bước kế tiếp, command/event, Saga ID và state store.
2. **Thiết kế state machine:** dùng các trạng thái như PENDING, SLOT_HELD, PAYMENT_PENDING, PAYMENT_UNKNOWN, PAYMENT_AUTHORIZED, CONFIRMED, COMPENSATING, CANCELLED và MANUAL_REVIEW. Với từng transition, xác định event/command hợp lệ, timeout và điều kiện.
3. **Thiết kế compensation:** định nghĩa hành động bù cho hold slot, authorize/capture payment, confirm booking và notification. Chỉ rõ hành động nào không thể đảo ngược hoàn toàn.
4. **Thiết kế outbox/inbox và idempotency:** tạo schema/pseudocode cho outbox, inbox và Saga state. Đảm bảo local transaction cập nhật business state cùng outbox/inbox khi phù hợp.
5. **Phân loại failure:** xử lý payment decline, timeout nhưng provider đã capture, booking confirmation lỗi tạm thời, hold hết hạn khi payment đang chờ, notification redelivery, refund thất bại và event đến trễ sau khi Saga đã hủy.
6. **Quan sát và vận hành:** đề xuất dashboard theo Saga state/age, timeout, retry, outbox lag, DLQ, compensation và payment mismatch. Viết quy trình reconciliation cho PAYMENT_UNKNOWN và MANUAL_REVIEW.
7. **Chọn mô hình:** chọn orchestration, choreography hoặc kết hợp; nêu lý do, rủi ro, chi phí vận hành, năng lực cần có và điều kiện review.

### Tiêu chí nghiệm thu

| Mục tiêu | Bằng chứng |
| --- | --- |
| Không có payment bị charge lặp vì retry | Provider operation ID/idempotency key và đối soát giao dịch |
| Booking state không mâu thuẫn với payment state | Concurrent/failure test và reconciliation report |
| Event redelivery không tạo side effect trùng | Inbox/unique event ID và test phát lại |
| Crash giữa DB commit và publish không làm mất sự kiện | Outbox relay recovery test |
| Compensation phản ánh trạng thái thật | Test refund/release lỗi và manual review |
| Workflow quá hạn được phát hiện | Alert theo Saga age/deadline và runbook |
| Có thể truy vết end-to-end | Trace/log nối Saga ID, correlation ID và event ID |
| Client hiểu trạng thái bất đồng bộ | API operation/status endpoint và contract rõ |

## 18. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi cho Saga |
| --- | --- |
| **Operational Excellence** | Có state dashboard, runbook, DLQ replay, reconciliation, audit và owner cho từng bước không? |
| **Security** | Command/event có identity, least privilege, tenant validation, data minimization và bảo vệ state store không? |
| **Reliability** | Timeout, retry, duplicate, out-of-order, crash, compensation và provider ambiguity đã được xử lý? |
| **Performance Efficiency** | Thời gian chờ từng bước, lock/queue, orchestration overhead và event fan-out có phù hợp SLO? |
| **Cost Optimization** | Workflow chạy lâu, state retention, message storage, retry và reconciliation có được dự toán? |
| **Sustainability** | Có tránh polling liên tục, retry storm, event dư thừa và lưu payload không cần thiết không? |

## 19. Checklist trước khi đưa Saga vào production

- [ ] Workflow thực sự cần nhiều local transaction; một transaction đơn giản không đủ.
- [ ] Saga ID, operation ID, command/event ID và correlation được định nghĩa.
- [ ] Mỗi participant sở hữu dữ liệu và transaction của mình; không service khác sửa trực tiếp database.
- [ ] Orchestration/choreography được chọn dựa trên độ phức tạp, ownership và năng lực vận hành.
- [ ] State machine có transition hợp lệ, trạng thái unknown và trạng thái manual review.
- [ ] Mỗi local transaction commit bền vững và xử lý duplicate an toàn.
- [ ] Outbox/inbox hoặc cơ chế tương đương xử lý khoảng trống commit/publish và redelivery.
- [ ] Timeout từng bước, deadline toàn Saga và retry/backoff có giới hạn.
- [ ] Compensation được định nghĩa cho từng side effect; các hành động không thể đảo ngược được nêu rõ.
- [ ] Payment/external provider có idempotency key và reconciliation khi kết quả không rõ.
- [ ] Event schema có version, producer, event ID, Saga ID và quyền publish/subscribe.
- [ ] Event trễ, sai thứ tự, duplicate và stale version được kiểm tra.
- [ ] Hold/resource có TTL phối hợp với workflow deadline và cancellation.
- [ ] Dashboard có Saga age/state, retry, compensation, outbox lag, DLQ và mismatch.
- [ ] Có quy trình manual review/reconciliation và người chịu trách nhiệm.
- [ ] Đã thử crash tại các ranh giới commit, publish, provider call và compensation.
- [ ] Security, retention, data minimization, cost và quyền truy cập được review.

Saga giúp nhiều dịch vụ cùng hoàn thành một mục tiêu nghiệp vụ mà không cần giữ distributed transaction kéo dài. **Orchestration** đặt tiến trình tại coordinator để điều khiển bước, timeout và compensation; **choreography** để service phối hợp qua event theo ranh giới domain. Dù chọn cách nào, độ tin cậy phụ thuộc vào local transaction, trạng thái bền vững, idempotency, outbox/inbox, xử lý kết quả không rõ, compensation thực tế và reconciliation. Một Saga chỉ đáng tin khi hệ thống có thể trả lời chính xác: giao dịch đang ở bước nào, side effect nào đã xảy ra, còn việc gì cần bù và ai chịu trách nhiệm khi tự động phục hồi không đủ.

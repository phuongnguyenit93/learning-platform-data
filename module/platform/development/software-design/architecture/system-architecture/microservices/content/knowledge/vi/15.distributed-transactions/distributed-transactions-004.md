# Saga điều phối và Saga phối hợp qua sự kiện trong giao dịch phân tán

## 1. Bài toán: một quy trình nghiệp vụ đi qua nhiều dịch vụ

Trong hệ thống thương mại điện tử, một yêu cầu đặt hàng có thể cần nhiều quyết định độc lập:

1. **Ordering** ghi nhận đơn ORD-1001.
2. **Inventory** kiểm tra và giữ sản phẩm.
3. **Payments** xác nhận một phương án thanh toán và thực hiện ủy quyền/thu tiền theo chính sách.
4. **Fulfillment** tạo yêu cầu xử lý hoặc vận chuyển.
5. **Notifications** gửi thông báo xác nhận.

Nếu mỗi khả năng nghiệp vụ nằm trong một Microservice sở hữu database riêng, chúng không còn cùng một transaction của một database. Mỗi dịch vụ có thể commit thay đổi của mình rồi mất kết nối, crash, hoặc mất khả năng liên hệ với dịch vụ tiếp theo.

Ví dụ Inventory đã giữ được 2 cuốn sách, nhưng Payments từ chối thanh toán. Hệ thống không được để hàng bị giữ vô thời hạn. Ngược lại, nếu khoản tiền đã được thu nhưng dịch vụ tạo vận đơn thất bại, việc hoàn tiền hoặc tiếp tục xử lý phải tuân thủ chính sách nghiệp vụ, không thể đơn giản chạy lệnh ROLLBACK SQL trên tất cả database.

**Saga** là một mẫu tổ chức quy trình nghiệp vụ phân tán dưới dạng chuỗi **giao dịch cục bộ** và những **hành động bù (compensating actions)** khi cần. Có hai cách điều phối phổ biến:

- **Saga điều phối tập trung (orchestration):** một Saga Orchestrator/Process Manager giữ tiến trình và phát lệnh đến các dịch vụ; nó quyết định bước tiếp theo dựa trên kết quả nhận được.
- **Saga phối hợp qua sự kiện (choreography):** các dịch vụ phát sự kiện nghiệp vụ, những dịch vụ quan tâm tự phản ứng và thực hiện giao dịch cục bộ tiếp theo theo một hợp đồng đã thống nhất; không nhất thiết có bộ điều phối trung tâm.

Cả hai là **lựa chọn tổ chức workflow**, không phải cơ chế biến nhiều database thành một transaction ACID toàn cục. Bài học này giúp xác định khi nào dùng mỗi cách, xử lý lỗi thế nào và tránh những nhầm lẫn thường gặp.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao transaction cục bộ không tự bảo đảm toàn bộ checkout là nguyên tử.
2. Nhận diện các thành phần của Saga: bước tiến, kết quả, trạng thái chờ, hành động bù và điểm kết thúc.
3. Vẽ cùng một luồng đặt hàng bằng **orchestration** và **choreography**.
4. Phân biệt **command**, **domain event**, **reply/event kết quả** và **compensation command**.
5. Thiết kế idempotency, outbox/inbox, timeout, retry, reconciliation và lưu trạng thái Saga bền vững.
6. Nhận biết giới hạn của compensation: có hành động bù không phải hoàn tác hoàn toàn.
7. So sánh khả năng quan sát, coupling, ownership và độ phức tạp của hai chiến lược.
8. Mô tả triển khai Java/Spring và cách kiểm thử các nhánh lỗi khó.
9. Nhận biết các tình huống cần kết hợp orchestration với choreography hoặc chọn kiến trúc đơn giản hơn.

## 2. Vì sao giao dịch phân tán là một bài toán riêng?

### 2.1. Một transaction cục bộ không trải rộng qua tất cả dịch vụ

Một Order Service có thể dùng transaction PostgreSQL:

~~~sql
BEGIN;
INSERT INTO orders (order_id, status)
VALUES ('ORD-1001', 'PENDING');
COMMIT;
~~~

Inventory Service cũng có transaction giữ hàng:

~~~sql
BEGIN;
UPDATE stock
SET available_qty = available_qty - 2,
    reserved_qty = reserved_qty + 2
WHERE sku = 'BOOK-01'
  AND available_qty >= 2;
INSERT INTO reservations (...) VALUES (...);
COMMIT;
~~~

Payments có database riêng và có thể gọi một cổng thanh toán ngoài tổ chức. Không có một câu lệnh SQL ROLLBACK duy nhất nào tự động hoàn tác cả ba hệ thống và cả thao tác đã gửi ra nhà cung cấp thanh toán.

Khi Inventory đã commit reservation, Ordering không thể dùng transaction local để trả hàng về kho. Nó phải yêu cầu Inventory thực hiện một thao tác nghiệp vụ mới, ví dụ **ReleaseReservation**, do Inventory kiểm tra và commit.

### 2.2. ACID cục bộ khác tính nhất quán nghiệp vụ của toàn workflow

Một transaction cục bộ có thể bảo đảm những invariant trong database mình sở hữu:

- Inventory không giữ số lượng vượt tồn theo mô hình tồn kho đã thống nhất.
- Payments không ghi hai lần cùng provider transaction ID.
- Ordering không chuyển từ CANCELLED sang DELIVERED trái state machine.

Nhưng toàn quy trình có thể tồn tại các trạng thái trung gian:

~~~text
Order    = PENDING_PAYMENT
Stock    = RESERVED
Payment  = PROCESSING
Shipment = NOT_CREATED
~~~

Đây không nhất thiết là dữ liệu sai. Nó có thể là **trạng thái hợp lệ đang tiến triển**. Thiết kế Saga cần định nghĩa trạng thái tạm, hạn xử lý, cách quan sát và hành động tiếp theo để những trạng thái đó không tồn tại mãi ngoài ý muốn.

### 2.3. Saga không giống 2-Phase Commit

**Two-Phase Commit (2PC)** cố điều phối một quyết định commit/abort qua các participant có hỗ trợ transaction protocol phù hợp. Trong Microservices, việc dùng 2PC xuyên nhiều công nghệ hoặc cổng thanh toán thường không khả thi hoặc tạo coupling/sẵn sàng không phù hợp.

**Saga** cho phép từng giao dịch local hoàn tất rồi dùng hành động nghiệp vụ bù khi một bước sau không đạt điều kiện. Trade-off là phải chấp nhận khoảng thời gian trạng thái các service chưa nhất quán với nhau và chủ động xử lý những trường hợp không thể hoàn tác hoàn toàn.

Không khẳng định 2PC luôn sai hay Saga luôn đúng: bài toán và hệ thống tham gia quyết định lựa chọn. Saga đặc biệt hữu ích khi nhiều participant không chia sẻ transaction manager và cần tiến trình có khả năng phục hồi.

## 3. Saga gồm những thành phần nào?

Một Saga có thể được mô tả bằng bảng:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Saga ID | Nhận diện một lần chạy workflow | saga-checkout-1001 |
| Correlation ID | Nối những message liên quan | checkout-1001 |
| Business entity ID | Đối tượng nghiệp vụ được xử lý | ORD-1001 |
| Local transaction | Thay đổi do một context sở hữu | Inventory ghi reservation |
| Forward action | Hành động tiến workflow | ReserveStock, AuthorizePayment |
| Reply/business event | Thông báo kết quả đã được xác nhận | StockReserved, PaymentAuthorized |
| Compensating action | Bước xử lý bù khi cần | ReleaseStock, VoidAuthorization |
| Saga state | Bước hiện tại và tình trạng workflow | WAITING_FOR_PAYMENT |
| Deadline/timer | Giới hạn chờ và phát hiện bị kẹt | reservation expiration |
| Idempotency key | Định danh một thao tác tránh thực thi trùng | reserve-ORD-1001 |
| Recovery metadata | Dữ liệu để chạy lại/đối soát | attemptId, version, lastError |

**Saga ID** không nhất thiết giống Order ID. Một Order có thể có checkout Saga, cancel Saga và refund Saga khác nhau. Correlation ID dùng để quan sát hoặc liên kết; không dùng correlation ID một cách máy móc làm khóa idempotency cho mọi lệnh có semantics khác nhau.

## 4. Chọn một workflow để so sánh công bằng

Ta sử dụng cùng một quy trình minh họa:

~~~text
1. Tạo Order trạng thái PENDING
2. ReserveStock
3. AuthorizePayment
4. ConfirmOrder
5. RequestFulfillment
6. Hoàn tất checkout workflow
~~~

Các **bước bù** có thể gồm:

~~~text
ReserveStock thành công, Payment bị từ chối:
  -> ReleaseStock
  -> CancelOrder

Payment authorized, bước tiếp theo thất bại:
  -> VoidPaymentAuthorization (nếu còn được phép)
  -> ReleaseStock
  -> CancelOrder

Payment đã captured:
  -> RefundPayment (nếu chính sách yêu cầu)
  -> theo dõi RefundSucceeded và các nghĩa vụ liên quan
~~~

**Authorize, capture, void và refund là các thao tác tài chính khác nhau.** Không thể giả định mọi cổng thanh toán hỗ trợ void sau capture hoặc refund hoàn tất tức thì. Phải chọn luồng phù hợp business policy và hợp đồng nhà cung cấp.

Trong ví dụ, **Notifications không phải bước bảo đảm thành công checkout**: gửi email lỗi không nên tự động hủy đơn đã trả tiền. Nó là hiệu ứng phụ có thể retry và quan sát riêng. Đây là ranh giới quan trọng khi vẽ Saga.

## 5. Saga điều phối tập trung — Orchestration

### 5.1. Mô hình tư duy

Một thành phần **Saga Orchestrator** lưu trạng thái workflow và ra quyết định bước tiếp theo:

~~~mermaid
flowchart TB
    U[Client] --> O[Ordering API]
    O --> SG[Saga Orchestrator / Process Manager]
    SG -->|ReserveStock command| I[Inventory]
    I -->|StockReserved / StockRejected| SG
    SG -->|AuthorizePayment command| P[Payments]
    P -->|PaymentAuthorized / PaymentRejected| SG
    SG -->|ConfirmOrder command| O
    SG -->|RequestFulfillment command| F[Fulfillment]
    F -->|FulfillmentAccepted / Rejected| SG
~~~

Từng service vẫn có quyền quyết định giao dịch cục bộ của mình. Orchestrator **không được** tự ghi vào database riêng của Inventory/Payments chỉ vì nó là “trung tâm”.

Orchestrator quản lý **trình tự và chính sách workflow xuyên context**. Inventory quản lý invariant tồn kho; Payments quản lý tình trạng giao dịch tài chính; Ordering quản lý vòng đời Order; Fulfillment quản lý shipment.

### 5.2. Luồng thành công

~~~mermaid
sequenceDiagram
    autonumber
    participant S as Checkout Saga Orchestrator
    participant I as Inventory
    participant P as Payments
    participant O as Ordering
    participant F as Fulfillment

    S->>I: ReserveStock(orderId, operationId)
    I-->>S: StockReserved(reservationId)
    S->>P: AuthorizePayment(orderId, paymentOperationId)
    P-->>S: PaymentAuthorized(paymentId)
    S->>O: ConfirmOrder(orderId)
    O-->>S: OrderConfirmed
    S->>F: RequestFulfillment(orderId)
    F-->>S: FulfillmentAccepted
    S->>S: Mark Saga COMPLETED
~~~

**Sự kiện tên “StockReserved” phải mang nghĩa xác nhận business transaction đã commit**, không phải “đã nhận message yêu cầu”. Nếu chỉ mới enqueue request, kết quả phải có trạng thái khác để Orchestrator không chuyển sang bước tiếp quá sớm.

### 5.3. Luồng thất bại và bù

Giả sử Inventory đã giữ được hàng nhưng Payments từ chối:

~~~mermaid
sequenceDiagram
    autonumber
    participant S as Checkout Saga
    participant I as Inventory
    participant P as Payments
    participant O as Ordering

    S->>I: ReserveStock
    I-->>S: StockReserved(RES-1)
    S->>P: AuthorizePayment
    P-->>S: PaymentRejected
    S->>S: Enter COMPENSATING
    S->>I: ReleaseStock(RES-1)
    I-->>S: StockReleased
    S->>O: CancelOrder(reason=PAYMENT_REJECTED)
    O-->>S: OrderCancelled
    S->>S: Mark Saga COMPENSATED
~~~

Orchestrator quản lý trình tự bù và trạng thái của từng nhiệm vụ. Nếu ReleaseStock timeout, nó **không được ghi ngay StockReleased**. Phải kiểm tra tình trạng reservation, retry an toàn theo cùng operation ID, hoặc đưa vào luồng đối soát.

### 5.4. Những trạng thái của Orchestrator

Một thiết kế có thể dùng:

~~~text
CREATED
  -> RESERVING_STOCK
  -> STOCK_RESERVED
  -> AUTHORIZING_PAYMENT
  -> PAYMENT_AUTHORIZED
  -> CONFIRMING_ORDER
  -> REQUESTING_FULFILLMENT
  -> COMPLETED

Bất kỳ bước hợp lệ có lỗi nghiệp vụ:
  -> COMPENSATING
  -> WAITING_FOR_COMPENSATION
  -> COMPENSATED / MANUAL_REVIEW

Bất kỳ bước chưa rõ kết quả:
  -> WAITING_FOR_RECONCILIATION
  -> tiếp tục hoặc bù theo sự thật đã xác minh
~~~

Tên status chỉ minh họa. Với nhiều điểm thất bại và tài nguyên khác nhau, nên lưu thêm **step status**, operation IDs, thời hạn, phiên bản Saga và kết quả đã nhận, không chỉ một enum duy nhất.

### 5.5. Ưu điểm của orchestration

- **Luồng điều khiển dễ nhìn:** một state machine biểu diễn toàn bộ tiến trình.
- **Quản lý timeout/timer tập trung:** dễ biết Saga nào chờ quá lâu.
- **Compensation rõ ràng:** Orchestrator biết bước nào đã hoàn tất và cần bù.
- **Quan sát và quản trị workflow:** có thể tra cứu Saga ID, current step, retry, last error.
- **Dễ kiểm thử nhánh rẽ:** decision logic và failure handling tập trung.
- **Phù hợp quy trình nhiều bước/điều kiện:** đặc biệt khi có wait for event, human approval, deadline và bù phức tạp.

### 5.6. Nhược điểm và rủi ro

- Orchestrator có thể trở thành **điểm tập trung logic**, cần ownership rõ và vận hành bền vững.
- Các thay đổi quy trình có thể phải cập nhật workflow definition.
- Nếu Orchestrator chứa cả validation tồn kho, quyết định khoản tiền và nghiệp vụ kho, nó đang **lấn quyền context**.
- Hệ thống có thể lệ thuộc vào khả năng sẵn sàng của Orchestrator; phải có persistence, HA và recovery.
- Đặt quá nhiều gọi đồng bộ trong một orchestrator handler khiến request bị giữ lâu, không bảo đảm durability của trạng thái chờ.

Một Orchestrator tốt điều phối **chính sách trình tự**, không biến thành “super service” với quyền sửa tất cả database.

## 6. Saga phối hợp qua sự kiện — Choreography

### 6.1. Mô hình tư duy

Trong choreography, các context lắng nghe những sự kiện quan trọng rồi tự thực hiện bước nghiệp vụ của mình. Không nhất thiết có một service chuyên ra lệnh cho mọi bước.

~~~mermaid
flowchart LR
    O[Ordering] -->|OrderPlaced| B[(Event Broker)]
    B -->|OrderPlaced| I[Inventory]
    I -->|StockReserved| B
    B -->|StockReserved| P[Payments]
    P -->|PaymentAuthorized| B
    B -->|PaymentAuthorized| O
    O -->|OrderConfirmed| B
    B -->|OrderConfirmed| F[Fulfillment]
    F -->|FulfillmentAccepted| B
~~~

Sơ đồ có các cạnh qua broker để nhấn mạnh publisher không gọi trực tiếp một handler khác. Broker **không quyết định business workflow**: mỗi subscriber có logic phản ứng theo contract.

### 6.2. Luồng thành công

~~~mermaid
sequenceDiagram
    autonumber
    participant O as Ordering
    participant B as Broker
    participant I as Inventory
    participant P as Payments
    participant F as Fulfillment

    O->>O: Persist Order PENDING
    O->>B: Publish OrderPlaced
    B-->>I: OrderPlaced
    I->>I: Reserve stock locally
    I->>B: Publish StockReserved
    B-->>P: StockReserved
    P->>P: Authorize payment locally
    P->>B: Publish PaymentAuthorized
    B-->>O: PaymentAuthorized
    O->>O: Confirm order locally
    O->>B: Publish OrderConfirmed
    B-->>F: OrderConfirmed
    F->>F: Accept fulfillment locally
    F->>B: Publish FulfillmentAccepted
~~~

Event contract phải làm rõ điều kiện phát: một OrderPlaced có nghĩa đơn đã được ghi, chứ chưa chắc đã thanh toán; một PaymentAuthorized có nghĩa provider đã xác nhận một authorization hợp lệ, không nhất thiết tiền đã settled.

### 6.3. Luồng từ chối và bù

Giả sử Payments từ chối:

~~~mermaid
sequenceDiagram
    autonumber
    participant I as Inventory
    participant B as Broker
    participant P as Payments
    participant O as Ordering

    I->>B: StockReserved(orderId, reservationId)
    B-->>P: StockReserved
    P->>P: Authorization rejected
    P->>B: PaymentRejected(orderId)
    B-->>I: PaymentRejected
    I->>I: Release reservation
    I->>B: StockReleased(orderId, reservationId)
    B-->>O: PaymentRejected + StockReleased
    O->>O: Cancel order when required conditions met
    O->>B: OrderCancelled
~~~

Tình huống này cần xác định rõ **ai chịu trách nhiệm tổng hợp trạng thái của workflow**. Ordering có thể sở hữu trạng thái checkout/order và biết khi nào đủ điều kiện Cancelled. Choreography không đồng nghĩa rằng không có bất kỳ service nào giữ state hoặc timer.

### 6.4. Ưu điểm của choreography

- Các context phát **domain events** và tự phản ứng theo nhu cầu của mình.
- Producer không cần biết tất cả consumer và không nhất thiết phát lệnh trực tiếp cho từng bước.
- Phù hợp các luồng ngắn, tuyến tính hoặc nhiều side effects độc lập.
- Dễ bổ sung một consumer mới như Analytics hoặc Notifications mà không sửa producer nếu event contract đủ ổn định.
- Mỗi nhóm có thể quản logic phản ứng của context mình.

### 6.5. Nhược điểm và rủi ro

- **Luồng workflow phân tán qua nhiều codebase:** khó biết ai quyết định bước cuối.
- **Coupling ẩn qua events:** đổi ý nghĩa event có thể ảnh hưởng nhiều consumer.
- **Event storm và vòng lặp:** sự kiện A kích hoạt B, B phát C, C kích hoạt A.
- **Khó xác định khi nào workflow kết thúc:** mỗi context có state cục bộ khác nhau.
- **Timeout và compensation phân tán:** có thể không rõ ai phát hiện bước bị kẹt, ai retry và ai escalates.
- **Khó kiểm thử end-to-end:** phải có integration tests cho nhiều listener và contract.
- **Khó tái hiện diễn biến:** cần correlation IDs, event catalog, tracing và logging có cấu trúc.

Choreography có thể phù hợp cho “OrderPlaced → gửi email” vì phản ứng ít phụ thuộc; nhưng một Saga nhiều bước có thu tiền, hoàn tiền, dự trữ kho và điều kiện bù chéo có thể nhanh chóng trở nên khó quan sát nếu mọi điều kiện bị rải trong các event handlers.

## 7. So sánh orchestration và choreography

| Tiêu chí | Orchestration | Choreography |
| --- | --- | --- |
| Ai quyết định bước tiếp? | Orchestrator/Process Manager | Từng subscriber phản ứng theo event |
| Nơi lưu trạng thái workflow | Thường có Saga state rõ ràng ở Orchestrator | Có thể phân tán; cần owner tổng hợp hoặc process tracking khi cần |
| Loại giao tiếp chính | Commands + replies/events | Domain events và event handlers |
| Khả năng hiểu quy trình | Tập trung ở workflow definition | Cần ghép nhiều subscriptions/contract |
| Compensation | Có thể được điều phối theo một kế hoạch | Các context phản ứng bằng sự kiện, phải tránh vòng lặp/đợi vô hạn |
| Coupling | Orchestrator biết participant và capabilities | Consumer biết event semantics; coupling thường ẩn |
| Onboarding consumer mới | Side-effect listener có thể bổ sung độc lập | Dễ thêm consumer mới nếu published event ổn định |
| Workflow nhiều nhánh | Thường dễ quản lý hơn | Có thể khó kiểm soát khi số bước tăng |
| Theo dõi timeout | Tập trung hơn | Cần thiết kế timer/monitor rõ |
| Team ownership | Có team sở hữu workflow | Ownership các phản ứng phân tán, cần governance |
| Triển khai | Tạo thêm thành phần điều phối | Có thể ít thành phần điều phối, nhưng tăng event coupling |
| Failure recovery | Saga state bền vững hỗ trợ resume | Phụ thuộc vào inbox, events, state máy và tracking phân tán |
| Test | State machine + participant contract tests | Event sequence/integration/contract tests |
| Phù hợp | Checkout, thanh toán, booking, flow có bù | Sự kiện lan tỏa, workflow ngắn, side effects tương đối độc lập |

Không có lựa chọn nào tốt hơn trong mọi tình huống. Khi quy trình phức tạp, **choreography thuần** có thể thành một workflow điều phối ẩn; khi mọi event đều bị một Orchestrator gọi lệnh chi li, **orchestration quá mức** có thể làm service mất autonomy.

## 8. Commands và events: phân biệt bản chất

Một **command** thể hiện ý định muốn một bên thực hiện hành động:

~~~json
{
  "commandId": "cmd-reserve-1001",
  "commandType": "ReserveStock",
  "orderId": "ORD-1001",
  "items": [{"sku": "BOOK-01", "quantity": 2}]
}
~~~

Một **event** công bố một sự thật đã xảy ra:

~~~json
{
  "eventId": "evt-reserved-1001",
  "eventType": "StockReserved",
  "orderId": "ORD-1001",
  "reservationId": "RES-200",
  "occurredAt": "2026-11-11T10:00:01Z"
}
~~~

Nếu Orchestrator gửi ReserveStock, Inventory vẫn có thể từ chối; command không chứng minh reservation đã tạo. Nếu Inventory phát StockReserved, event phải phản ánh một kết quả đã được commit và phù hợp semantics.

### Sự kiện mang tên command là dấu hiệu cần xem xét

Một “event” OrderPleaseChargeCreditCard gửi vào topic để Payments hành động thực chất có thể là command được đặt tên sai. Điều đó không tự làm hệ thống hỏng, nhưng gây nhầm quyền sở hữu và trách nhiệm xử lý.

Trong choreography, các subscriber thường phản ứng với **sự thật nghiệp vụ** hơn là producer chỉ định đích trực tiếp. Trong orchestration, Orchestrator thường gửi **mệnh lệnh rõ ràng** đến participant.

### Reply và completion event

Orchestrator cần biết command hoàn thành hay chưa. Có thể nhận response đồng bộ, command reply qua queue hoặc domain event có correlation/operation ID.

~~~text
ReserveStock(commandId=cmd-1)
  -> StockReserved(causationId=cmd-1, reservationId=RES-200)

AuthorizePayment(commandId=cmd-2)
  -> PaymentAuthorized(causationId=cmd-2, paymentId=PAY-100)
~~~

Không sử dụng một event từ lần Saga cũ làm phản hồi cho lần Saga mới chỉ vì orderId trùng. Cần xác nhận **operation identity**, version, trạng thái hiện tại và nguồn đáng tin.

## 9. Không có rollback vật lý: hiểu đúng compensation

Một **compensating transaction** là một giao dịch nghiệp vụ mới làm giảm hoặc xử lý tác động của một bước trước đó. Nó **không phải** phép đảo bit hoặc rollback SQL trên hệ thống khác.

| Bước đã thành công | Hành động bù có thể có | Giới hạn cần hiểu |
| --- | --- | --- |
| ReserveStock | ReleaseStock | Hàng có thể đã được pick/ship; không phải lúc nào release được |
| AuthorizePayment | VoidAuthorization | Có thể hết hạn void hoặc đã capture |
| CapturePayment | RefundPayment | Hoàn tiền có thể chậm, có phí, chịu quy định provider |
| CreateShipment | CancelShipment | Nếu đã bàn giao carrier, cancel có thể thất bại |
| SendEmail | Gửi thông báo đính chính | Không thể “thu hồi” email đã được người nhận đọc |
| PublishEvent | Publish corrective event | Consumer cũ có thể đã thực hiện side effects |
| CreateBooking | CancelBooking | Có thể bị phí hủy hoặc không thể hoàn toàn |

Trong thực tế, quy trình bù có thể tạo **trạng thái mới** như REFUND_PENDING, REFUNDED, CANCEL_REQUESTED. “Đã bù” không đồng nghĩa thế giới quay lại chính xác như trước khi Saga bắt đầu.

### Pivot transaction và điểm không thể bù đơn giản

Một số Saga có **bước pivot**: sau đó quy trình không thể dùng hành động bù thông thường hoặc chi phí bù tăng mạnh. Ví dụ khi gói hàng đã giao cho carrier hoặc tiền đã settled. Các bước sau pivot cần chính sách retry/forward recovery thay vì giả định luôn có inverse operation.

Nên thiết kế workflow giảm rủi ro bằng cách đặt các bước dễ đảo trước, các bước không thể đảo sau, nhưng thứ tự phải do nhu cầu business quyết định.

### Hành động bù cũng có thể thất bại

ReleaseStock có thể timeout. RefundPayment có thể bị nhà cung cấp tạm lỗi. Vì vậy Saga cần:

- Operation ID cho compensation.
- Retry có giới hạn, backoff, jitter.
- Trạng thái compensation đang chờ.
- Deadline và cơ chế escalation.
- Dashboard/alert cho các Saga chưa thể hoàn tất.
- Manual intervention có kiểm soát nếu không thể tự động khôi phục.
- Reconciliation đối chiếu nguồn thực tế trước khi lặp lại thao tác.

## 10. Timeout không phải kết quả thất bại

Một trong những lỗi nguy hiểm nhất:

~~~text
Orchestrator -> Payments: AuthorizePayment
Payments thực hiện với PSP và commit thành công
Response bị mất trên mạng
Orchestrator nhận timeout
Orchestrator kết luận PaymentRejected
Orchestrator bắt đầu refund sai hoặc gửi charge lần nữa
~~~

**Timeout = không biết chắc kết quả ở phía bên kia.** Có thể request chưa đến, đã đến nhưng chưa xử lý, hoặc xử lý thành công nhưng không có response.

Một cách xử lý:

1. Mỗi command có operationId/idempotency key ổn định.
2. Participant ghi nhận operation và kết quả bền vững.
3. Sau timeout, Orchestrator tra cứu trạng thái theo operationId hoặc chờ event được xác nhận.
4. Nếu kết quả vẫn chưa rõ, vào WAITING_FOR_RECONCILIATION thay vì đoán.
5. Chỉ quyết định tiếp tục/bù khi có đủ chứng cứ nghiệp vụ.
6. Nếu retry, dùng **cùng identity của thao tác** và bảo đảm participant xử lý idempotent.

Trong choreography, nguyên tắc tương tự áp dụng cho event handlers: thiếu một event phản hồi không chứng minh hành động chưa xảy ra; cần timer, reconciliation hoặc query nguồn.

## 11. Idempotency là nền móng của Saga

Message broker và network có thể giao lại command/event. Một Saga phải giả định cùng message có thể được xử lý hơn một lần.

### 11.1. Idempotent command handler

Inventory nhận hai lần ReserveStock với operationId=reserve-ORD-1001. Nếu cả hai lần đều trừ tồn thì hệ thống oversell hoặc giữ hàng trùng.

Một quy tắc:

~~~text
Same (tenant, operationType, operationId) + same payload:
    return/replay same business result

Same key + different payload:
    reject conflict / investigate

New operationId:
    apply new command according to business invariants
~~~

Thực thi nên dùng nguồn dữ liệu bền vững và unique constraint/atomic operation, không dùng ConcurrentHashMap local của một process.

### 11.2. Idempotent event consumer

Event PaymentAuthorized có eventId=evt-101 bị giao lại. Ordering không được “xác nhận đơn” hai lần nếu việc đó tạo thêm side effect; projector không được cộng tiền hai lần.

Có thể lưu inbox:

~~~sql
CREATE TABLE processed_messages (
    consumer_name VARCHAR(100) NOT NULL,
    message_id VARCHAR(128) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, message_id)
);
~~~

Trong cùng transaction local, consumer insert message ID và cập nhật state. Nếu duplicate key đã có, bỏ qua tác dụng trùng hoặc trả lại kết quả trước đó theo contract.

### 11.3. Khác nhau giữa message ID và operation ID

- **messageId/eventId:** định danh một message/entry cụ thể để dedupe delivery.
- **operationId/idempotencyKey:** định danh cùng một hành động nghiệp vụ dù có nhiều message attempt.
- **sagaId:** định danh workflow.
- **correlationId:** liên kết observability và trao đổi liên quan.
- **aggregateVersion:** hỗ trợ xét tiến trình thay đổi của một đối tượng nguồn.

Một Saga có thể có nhiều operationId; một operation có thể có nhiều delivery messages. Dùng sai ID có thể khiến bù nhầm reservation hoặc gộp hai payment attempts độc lập.

## 12. Transactional Outbox: DB commit và phát sự kiện

Cả orchestration và choreography đều cần một cách phát thông điệp đáng tin cậy sau thay đổi cục bộ. Nếu dùng cách:

~~~text
BEGIN transaction;
UPDATE orders;
COMMIT;

publish OrderPlaced;
~~~

Process có thể chết sau COMMIT trước publish, khiến các participant không biết Order đã được tạo.

Với **Transactional Outbox**:

~~~sql
BEGIN;

UPDATE orders
SET status = 'PENDING'
WHERE order_id = 'ORD-1001';

INSERT INTO outbox_events
    (event_id, aggregate_id, event_type, payload, created_at)
VALUES
    ('evt-1001', 'ORD-1001', 'OrderPlaced',
     '{"orderId":"ORD-1001"}', CURRENT_TIMESTAMP);

COMMIT;
~~~

Outbox publisher/CDC đọc bản ghi và phát lên broker. Nếu publisher crash sau khi phát nhưng trước khi đánh dấu xong, event có thể được gửi lại. Vì vậy inbox/idempotency vẫn cần thiết.

### Outbox không biến toàn hệ thống thành một transaction

Outbox giải quyết việc **ghi state và lưu ý định phát event trong cùng transaction local**. Nó không bao trùm Inventory DB, Payment DB và provider API vào một ACID transaction chung.

### Outbox và command trong orchestration

Orchestrator cũng có thể ghi **Saga state mới + outbound command** vào cùng transaction DB của Orchestrator:

~~~text
BEGIN
  UPDATE checkout_saga SET step = WAITING_FOR_STOCK
  INSERT outbox command ReserveStock(operationId=reserve-1001)
COMMIT
~~~

Khi restart, publisher phát lại command từ outbox; participant phải xử lý trùng an toàn. Phía nhận có thể trả reply/event qua broker để Orchestrator cập nhật trạng thái.

## 13. Inbound processing và xử lý trùng

Một participant có thể nhận ReserveStock(commandId=cmd-1). Quy trình tốt:

~~~text
receive message
  -> authenticate/validate caller and schema
  -> check dedupe / operation state
  -> apply domain transaction
  -> save result/outbox event atomically when possible
  -> commit
  -> acknowledge broker after durable update
~~~

Nếu broker ack trước khi transaction commit, crash có thể làm mất command. Nếu DB commit rồi crash trước ack, message có thể đến lại; dedupe bảo vệ kết quả.

### Consumer offset và "exactly once"

Một số broker/stream framework có cơ chế exactly-once ở phạm vi xử lý được định nghĩa; nhưng điều đó **không tự bao gồm** transaction ở một database ngoài hoặc payment provider. Khi có external side effect, vẫn cần idempotency và reconciliation.

Trong Kafka consumer group, offset/partition, rebalance và retry cần được quản lý để không xử lý một Saga cũ như mới. Trong RabbitMQ, ack/nack/requeue và dead-letter chính sách cũng ảnh hưởng delivery. Tên công nghệ không thay cho thiết kế contract.

## 14. State machine của Orchestrator

Một Saga Orchestrator không nên chỉ giữ biến state trong RAM. Nó cần **durable workflow state** để sống sót qua restart, retry, rolling deployment và delayed replies.

Ví dụ mô hình:

~~~sql
CREATE TABLE checkout_sagas (
    saga_id VARCHAR(128) PRIMARY KEY,
    order_id VARCHAR(128) NOT NULL,
    status VARCHAR(48) NOT NULL,
    current_step VARCHAR(48) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    reservation_id VARCHAR(128),
    payment_id VARCHAR(128),
    last_operation_id VARCHAR(128),
    deadline_at TIMESTAMPTZ,
    next_retry_at TIMESTAMPTZ,
    last_error_code VARCHAR(100),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Một bảng phụ có thể lưu step history, attempts, incoming message IDs và các compensation outcomes.

### Ví dụ chuyển trạng thái

| Saga state hiện tại | Tín hiệu | Điều kiện | Saga state tiếp |
| --- | --- | --- | --- |
| WAITING_FOR_STOCK | StockReserved | operationId khớp, reservation hợp lệ | WAITING_FOR_PAYMENT |
| WAITING_FOR_STOCK | StockRejected | Rejection có thẩm quyền | CANCELING_ORDER |
| WAITING_FOR_PAYMENT | PaymentAuthorized | paymentId và operationId khớp | CONFIRMING_ORDER |
| WAITING_FOR_PAYMENT | PaymentRejected | Kết quả bị từ chối cuối cùng | RELEASING_STOCK |
| WAITING_FOR_PAYMENT | DeadlineExceeded | Kết quả chưa rõ | RECONCILING_PAYMENT |
| RELEASING_STOCK | StockReleased | reservation khớp | CANCELING_ORDER |
| CONFIRMING_ORDER | OrderConfirmed | orderId và version hợp lệ | REQUESTING_FULFILLMENT |
| REQUESTING_FULFILLMENT | FulfillmentAccepted | Quy trình đã được nhận | COMPLETED |

**Một sự kiện không được áp trong mọi trạng thái.** Nếu PaymentAuthorized từ lần thử cũ đến sau khi Saga đã Cancelled, handler phải xét operation identity, phiên bản và chính sách đối soát, không tự chuyển đơn thành Confirmed.

### Optimistic locking cho Saga state

Khi hai reply gần như đồng thời đến, cần tránh lost update:

~~~sql
UPDATE checkout_sagas
SET status = 'WAITING_FOR_PAYMENT',
    current_step = 'AUTHORIZE_PAYMENT',
    version = version + 1
WHERE saga_id = 'saga-checkout-1001'
  AND status = 'WAITING_FOR_STOCK'
  AND version = 3;
~~~

Nếu UPDATE ảnh hưởng 0 dòng, handler phải đọc lại trạng thái, quyết định duplicate/stale/conflict và xử lý tương ứng. Có thể dùng database locks hoặc cơ chế concurrency control khác; điều quan trọng là state transition được bảo vệ nguyên tử.

## 15. Java/Spring: kiến trúc Orchestrator minh họa

Một cách tổ chức code:

~~~text
CheckoutSagaMessageListener
  -> Validate event/message envelope
  -> CheckoutSagaApplicationService
  -> SagaStateRepository + Inbox
  -> Domain decision (next command / compensation)
  -> OutboxRepository
  -> Transaction COMMIT
  -> Outbox publisher sends command

Inventory command listener
  -> Inventory domain + repository
  -> local transaction + outbox event
~~~

Pseudo-Java tập trung vào ý tưởng:

~~~java
public enum CheckoutState {
    WAITING_FOR_STOCK,
    WAITING_FOR_PAYMENT,
    RECONCILING_PAYMENT,
    RELEASING_STOCK,
    CANCELING_ORDER,
    COMPLETED,
    COMPENSATED,
    MANUAL_REVIEW
}

public record StockReserved(
    String eventId,
    String sagaId,
    String orderId,
    String operationId,
    String reservationId
) {}

@Service
public final class CheckoutSagaHandler {
    private final SagaRepository sagas;
    private final InboxRepository inbox;
    private final OutboxRepository outbox;

    public CheckoutSagaHandler(
        SagaRepository sagas,
        InboxRepository inbox,
        OutboxRepository outbox
    ) {
        this.sagas = sagas;
        this.inbox = inbox;
        this.outbox = outbox;
    }

    @Transactional
    public void onStockReserved(StockReserved event) {
        if (!inbox.tryRegister("checkout-saga", event.eventId())) {
            return;
        }

        CheckoutSaga saga = sagas.lockById(event.sagaId());

        if (saga.state() != CheckoutState.WAITING_FOR_STOCK) {
            saga.recordUnexpectedEvent(event.eventId());
            return;
        }

        saga.assertExpectedOperation(event.operationId());
        saga.recordReservation(event.reservationId());
        saga.moveTo(CheckoutState.WAITING_FOR_PAYMENT);

        outbox.saveCommand(
            "AuthorizePayment",
            saga.sagaId(),
            saga.paymentOperationId(),
            saga.paymentCommandPayload()
        );
        sagas.save(saga);
    }
}
~~~

Các lớp Repository, CheckoutSaga và phương thức domain cần được hiện thực trong dự án. Đây là **khung kiến trúc minh họa**, không phải code chạy độc lập hoàn chỉnh.

Cần chú ý:

- Inbox registration và Saga state update nằm trong cùng transaction local.
- Lock/version bảo vệ nhiều worker xử lý cùng Saga.
- Reply có operationId phải khớp bước đang chờ.
- Ghi outbound command vào Outbox trong cùng transaction.
- Broker ack/offset commit diễn ra sau durable commit theo cấu hình consumer.
- Khi event unexpected/stale xuất hiện, phải có chính sách lưu/đối soát hoặc bỏ qua có kiểm soát; không được “nuốt” một PaymentAuthorized quan trọng mà không biết khoản tiền thực tế.

### Những bước nghiệp vụ không chạy trong một transaction của Orchestrator

Handler không trực tiếp mở transaction tới Inventory DB/Payment DB. Nó tạo **intent** để participant xử lý giao dịch cục bộ. Nếu Orchestrator gọi HTTP đồng bộ, vẫn cần persist state trước/sau lời gọi phù hợp và có recovery khi response mất; không giữ transaction DB mở quá lâu trong lúc chờ network.

## 16. Java/Spring: choreography bằng event handlers

Trong choreography, Order Service công bố OrderPlaced; Inventory tiêu thụ:

~~~java
public record OrderPlacedEvent(
    String eventId,
    String orderId,
    String correlationId,
    List<OrderLine> items
) {}

@Service
public final class InventoryEventHandler {
    private final InventoryApplicationService inventory;
    private final InboxRepository inbox;
    private final OutboxRepository outbox;

    public InventoryEventHandler(
        InventoryApplicationService inventory,
        InboxRepository inbox,
        OutboxRepository outbox
    ) {
        this.inventory = inventory;
        this.inbox = inbox;
        this.outbox = outbox;
    }

    @Transactional
    public void onOrderPlaced(OrderPlacedEvent event) {
        if (!inbox.tryRegister("inventory-order-events", event.eventId())) {
            return;
        }

        ReserveOutcome result = inventory.reserveForOrder(
            event.orderId(), event.items()
        );

        if (result.reserved()) {
            outbox.saveEvent("StockReserved", event.orderId(),
                result.reservationId(), event.correlationId());
        } else {
            outbox.saveEvent("StockRejected", event.orderId(),
                result.reasonCode(), event.correlationId());
        }
    }
}
~~~

Trong đoạn này, Inventory **tự quyết định** có giữ hàng được hay không. Nó không cập nhật Order DB. Payments lắng nghe StockReserved và đưa ra kết quả thanh toán theo chính sách; Ordering lắng nghe các kết quả liên quan để cập nhật Order.

Các type và repository là ví dụ, không phải thư viện có sẵn. Thiết kế thật cần transactional boundary đúng, command identity phù hợp, kiểm tra version, handling event đến trễ và nghiệp vụ nhiều lần retry.

### Mối nguy coupling ẩn

Nếu Payments chỉ biết lắng nghe event StockReserved do Inventory phát mà không hiểu vì sao event đó được phát, việc thay đổi quy trình checkout có thể ảnh hưởng Payments dù không đổi API trực tiếp. Cần event catalog và hợp đồng semantics, consumer map, versioning và governance.

## 17. Choreography vẫn cần trạng thái, timer và người chịu trách nhiệm

Một quan niệm sai: choreography nghĩa là **không có state machine**. Thực tế từng service có state machine riêng:

- Ordering: Order PENDING, CONFIRMED, CANCEL_PENDING, CANCELLED.
- Inventory: Reservation RESERVED, EXPIRED, RELEASED.
- Payments: Payment CREATED, AUTHORIZED, VOIDED, CAPTURED, REFUNDED.
- Fulfillment: Shipment REQUESTED, ACCEPTED, SHIPPED, CANCELLED.

Nếu các trạng thái phụ thuộc nhau, cần một **owner của kết quả nghiệp vụ tổng thể**, ví dụ Ordering chịu trách nhiệm vòng đời đơn. Một service theo dõi tiến trình có thể nhận events để hiển thị saga status hoặc phát hiện workflow kẹt mà không nhất thiết quyết định mọi bước; khi nó bắt đầu phát command điều phối, thiết kế đã dịch chuyển về một dạng hybrid/orchestration.

### Ai phát hiện bước không xảy ra?

Giả sử StockReserved đã phát nhưng Payments không bao giờ phát PaymentAuthorized hay PaymentRejected. Choreography cần:

- Một timer/timeout có owner.
- Cơ chế truy vấn hoặc xác minh Payments.
- Quy tắc có được release stock chưa.
- Operation ID/correlation để tránh bù nhầm.
- Alert/manual intervention nếu không xác định được kết quả.
- Quy tắc tiến tiếp khi nhận event sau deadline.

Không thể chỉ nói “broker sẽ tự xử lý”. Broker giao message; **quyết định business timeout** thuộc hệ thống nghiệp vụ.

## 18. Một Saga có thể kết hợp cả hai kiểu

Sự phân đôi orchestration/choreography không hoàn toàn tuyệt đối.

Ví dụ:

- **Checkout Saga Orchestrator** điều khiển ReserveStock → AuthorizePayment → ConfirmOrder và các bù trừ tài chính/kho.
- **Ordering** công bố OrderConfirmed.
- **Notifications** và **Analytics** phản ứng choreography một cách độc lập.
- **Fulfillment** có thể sử dụng riêng một workflow dài xử lý đóng gói, xuất kho, giao vận với Orchestrator riêng hoặc event choreography tùy độ phức tạp.

~~~mermaid
flowchart TB
    CO[Checkout Orchestrator] -->|commands| I[Inventory]
    CO -->|commands| P[Payments]
    CO -->|commands| O[Ordering]
    O -->|OrderConfirmed event| B[(Broker)]
    B --> N[Notifications]
    B --> A[Analytics]
    B --> F[Fulfillment workflow]
~~~

Đây thường là cách tổ chức thực tế: **điều phối tập trung ở những bước có nghĩa vụ bù quan trọng**, sự kiện lan tỏa cho những tác dụng phụ độc lập.

Không cần tạo Orchestrator cho mọi event. Gửi thông báo sản phẩm mới thường chỉ cần listener và retry/observability phù hợp.

## 19. Chọn Saga boundaries theo business capability

Không phải mọi bước của một request phải thuộc cùng Saga. Bắt đầu bằng business invariants và nghĩa vụ cần bảo đảm.

### Trong checkout

- Reservation phải được giải phóng khi đơn bị từ chối.
- Payment authorization phải gắn với đúng order/amount.
- Nếu Order Confirmed, các nghĩa vụ còn lại được theo dõi.
- Fulfillment có thể là một workflow riêng sau khi checkout thành công.
- Notifications không quyết định tính hợp lệ tài chính của đơn.

### Tránh Saga quá rộng

Một Mega Saga bao gồm đặt hàng, đóng gói, vận chuyển, giao thành công, đánh giá sản phẩm, gửi email marketing kéo dài nhiều tuần sẽ rất khó bù và khó định nghĩa completion.

Hãy chia theo những ranh giới nghiệp vụ có kết quả rõ. Ví dụ Checkout Saga kết thúc ở “đơn được xác nhận và đủ điều kiện xử lý”; Fulfillment Saga sau đó quản vận đơn và các bước giao. Hai workflow liên kết qua events, không nhất thiết tạo một transaction phân tán khổng lồ.

### Tránh Saga quá nhỏ

Nếu mọi bước chỉ cần cập nhật trong một database của cùng context, dùng local ACID transaction thường đơn giản và nhất quán hơn. Không cần Saga chỉ vì hệ thống có Kafka.

## 20. Phân loại bước: có thể bù, pivot, retry

Một cách thiết kế hữu ích là phân loại các transaction của Saga:

**Compensatable:** có hành động nghiệp vụ giảm/hoàn tác hiệu ứng nếu cần. Ví dụ ReserveStock có ReleaseStock.

**Pivot:** bước cam kết quan trọng sau đó việc đảo lại có thể không còn đơn giản hoặc có hậu quả bên ngoài lớn. Ví dụ CapturePayment hoặc bàn giao hàng cho carrier tùy mô hình.

**Retryable:** bước sau pivot cần tiếp tục đến kết quả hợp lệ bằng retry/recovery có kiểm soát, không mặc định rollback.

Phân loại không phải một quy tắc cứng dựa vào tên method. Một authorized payment có thể void trong khoảng thời gian nhất định; một reservation có thể không release được sau khi pick/ship. Hãy xác nhận với domain expert và provider contract.

### Ví dụ chiến lược

~~~text
ReserveStock        -> compensatable
AuthorizePayment    -> may be voidable
ConfirmOrder        -> local state transition
CapturePayment      -> potentially pivot / requires refund, not simple rollback
RequestFulfillment  -> retryable or compensatable by current fulfillment stage
SendNotification    -> independent side effect
~~~

Mỗi bước có thể đổi loại tùy trạng thái và thời điểm. Saga state cần phản ánh điều kiện thực tế, không chỉ danh sách tĩnh.

## 21. Một Saga có nhiều participant hoặc nhiều bản sao

Nếu một Order có 3 dòng hàng ở 2 kho, Inventory có thể tạo nhiều reservations. Nếu payment chia thành 2 đợt, Payments có nhiều attempts. Nếu Fulfillment tách 2 shipments, quy trình còn phức tạp hơn.

**Không đơn giản lưu một reservationId và một paymentId nếu nghiệp vụ hỗ trợ nhiều bản ghi.**

Ví dụ trạng thái:

~~~json
{
  "sagaId": "checkout-ORD-1001",
  "orderId": "ORD-1001",
  "status": "WAITING_FOR_PAYMENT",
  "reservations": [
    {"reservationId": "RES-A", "warehouse": "WH-1", "status": "RESERVED"},
    {"reservationId": "RES-B", "warehouse": "WH-2", "status": "RESERVED"}
  ],
  "paymentAttempts": [
    {"paymentId": "PAY-1", "status": "AUTHORIZATION_PENDING"}
  ]
}
~~~

Khi bù, cần release **đúng tập reservations thực sự đã commit**. Nếu một reservation release thất bại, không được đánh dấu mọi reservation đã giải phóng. Có thể cần compensation fan-out và tổng hợp trạng thái.

Orchestrator có thể dễ quản lý tập bước này hơn; choreography vẫn làm được nếu contract và owner tiến trình được thiết kế chặt.

## 22. Sự kiện đến trùng, đến muộn và sai thứ tự

### 22.1. Giao trùng

~~~text
StockReserved(evt-1) tới hai lần
PaymentAuthorized(evt-2) tới hai lần
~~~

Handler phải dedupe eventId hoặc bảo vệ state transition idempotent. Một email notification lặp có thể gây khó chịu; một payment command lặp không có idempotency có thể gây tổn thất tài chính.

### 22.2. Đến muộn

Saga đã CANCELLED và sau đó PaymentAuthorized từ một attempt cũ mới đến. Không được coi đó chỉ là event “không hợp lệ” để bỏ qua vô điều kiện. Cần đối soát: có tồn tại authorization/charge thực tế cần void/refund không?

### 22.3. Sai thứ tự

~~~text
OrderCancelled(version=5)
OrderConfirmed(version=4)
~~~

Consumer không được đưa order trở lại CONFIRMED nếu event cũ đến sau. Version/sequence theo aggregate và state machine giúp kiểm soát stale updates.

### 22.4. Event từ nhiều context

Payment version=3 không thể so sánh trực tiếp với Order version=3 để kết luận cái nào “mới hơn”. Mỗi context có trật tự riêng; cần correlation/causation/operation IDs và quy tắc domain.

### 22.5. Chọn partition key

Với Kafka, đặt các events cùng aggregate vào một partition có thể giữ thứ tự log trong phạm vi đó, nhưng không bảo đảm **total ordering giữa các topic/context**. Consumer concurrency, retry, rebalance và key strategy vẫn phải được kiểm soát.

## 23. Schema, version và hợp đồng liên dịch vụ

Saga có thể chạy trong vài phút, giờ hoặc lâu hơn; trong lúc đó producer/consumer được rolling deploy. Một Saga v1 có thể nhận một message do service v2 phát.

Các contract cần ghi:

- Message type: command hay event.
- Schema format: JSON Schema, Protobuf, Avro hoặc loại khác.
- Contract owner và các consumer.
- Versioning/compatibility policy.
- Ý nghĩa chính xác của kết quả.
- operationId, sagaId, eventId, aggregateId, correlationId.
- Error codes của business rejection và retryable failures.
- Giá trị default/unknown, enum mới, data privacy.
- Điều kiện phát và chính sách giao trùng/thứ tự.
- Cách xử lý message từ Saga version cũ sau deploy.

**Schema compatibility không đồng nghĩa semantic compatibility.** Đổi nghĩa PaymentAuthorized thành “đã captured” mà giữ cùng trường dữ liệu có thể phá logic bù rất nghiêm trọng.

### Version workflow

Orchestrator có thể cần giữ workflow definition version tại Saga creation, để một Saga đang chạy không bị thay đổi logic giữa chừng khi deploy phiên bản mới. Những hệ thống dùng workflow engine có thể cung cấp cơ chế versioning riêng; cần làm theo contract của engine cụ thể.

Choreography cũng cần hỗ trợ event versions và bảo đảm các subscriber cũ/mới hoạt động trong giai đoạn chuyển tiếp.

## 24. Quan sát Saga end-to-end

Chỉ nhìn HTTP 200 hoặc broker ack không đủ xác nhận checkout hoàn tất. Cần business-level observability.

| Tín hiệu | Ý nghĩa |
| --- | --- |
| Saga started / completed / compensated | Tỷ lệ workflow kết thúc |
| Saga age by state | Bao nhiêu Saga đang chờ quá lâu |
| Step latency | ReserveStock, AuthorizePayment, ConfirmOrder mất bao lâu |
| Compensation started/succeeded/failed | Khả năng khôi phục nghiệp vụ |
| Unknown payment result | Số giao dịch cần reconciliation |
| Retry count/backoff | Lỗi tạm và nguy cơ retry storm |
| Inbox duplicates | Mức độ redelivery và hoạt động dedupe |
| Outbox pending age | Message đã commit nhưng chưa phát |
| Consumer lag/DLQ | Bị kẹt ở broker/consumer |
| Cross-service trace | Xác định hop chậm hoặc lỗi |
| Financial/stock reconciliation | Kiểm tra dữ liệu và nghĩa vụ thực tế |

### Ví dụ log có cấu trúc

~~~text
sagaId=checkout-1001 orderId=ORD-1001
step=RESERVE_STOCK state=WAITING retry=0
operationId=reserve-ORD-1001
traceId=t-1001

sagaId=checkout-1001 orderId=ORD-1001
eventType=StockReserved reservationId=RES-200
step=AUTHORIZE_PAYMENT state=WAITING retry=0

sagaId=checkout-1001 orderId=ORD-1001
eventType=PaymentRejected
step=RELEASE_STOCK state=COMPENSATING
~~~

Không ghi access token, payment credential, số thẻ hay dữ liệu nhạy cảm vào log. orderId/sagaId có thể xuất hiện trong log có kiểm soát, nhưng tránh làm metric label cardinality rất cao.

### Correlation và distributed tracing

Sử dụng traceId/spanId để quan sát những request kỹ thuật; sagaId/correlationId để liên kết workflow lâu dài qua nhiều trace. Một Saga kéo dài ba ngày không bắt buộc phải nằm trong một trace đơn duy nhất.

## 25. Kiểm thử Saga: chỉ có happy path là không đủ

Một bộ kiểm thử nên bao gồm:

### 25.1. State machine unit tests

Với Orchestrator:

- StockReserved trong WAITING_FOR_STOCK → sang WAITING_FOR_PAYMENT.
- PaymentRejected trong WAITING_FOR_PAYMENT → phát ReleaseStock.
- StockReleased trong RELEASING_STOCK → tiếp tục CancelOrder.
- Reply sai operationId → không áp nhầm.
- Event duplicate → không phát command hai lần ngoài ý muốn.
- Event stale → không đưa state lùi.
- Timeout → RECONCILING thay vì kết luận thành công/thất bại.

### 25.2. Participant contract tests

- Inventory chỉ trả StockReserved sau khi reservation commit.
- Payments không đánh đồng HTTP timeout với PaymentRejected.
- Compensation command có idempotency key ổn định.
- Schema/event version cũ vẫn được đọc trong rolling deployment.
- Business rejection khác lỗi transport.

### 25.3. Integration tests

- Event broker gửi trùng command/event.
- Consumer crash trước và sau DB commit.
- Outbox publisher crash sau gửi trước checkpoint.
- Orchestrator crash khi đang chờ payment.
- Database participant unavailable.
- Message đến sai thứ tự.
- Network chập chờn làm reply đến rất muộn.
- Saga chạy khi producer/consumer ở phiên bản khác nhau.

### 25.4. End-to-end failure injection

- ReserveStock thành công, AuthorizePayment bị từ chối.
- AuthorizePayment thành công nhưng response mất.
- ReleaseStock timeout sau khi Inventory đã giải phóng.
- PaymentCaptured nhưng Fulfillment không nhận shipment.
- Refund được yêu cầu nhưng provider tạm không trả lời.
- Hai request checkout cùng order và idempotency key.
- Một Saga bị kẹt sau restart/redeploy.
- Notifications fail nhưng Order không bị hủy sai.

Thử những tình huống này trên môi trường test có dữ liệu giả và provider sandbox phù hợp; không gây lỗi trên giao dịch thật khi chưa có quyền.

## 26. Những anti-pattern phổ biến

### Anti-pattern 1 — Gọi nhiều RPC rồi tưởng có một transaction toàn cục

~~~text
Order.create()
Inventory.reserve()
Payments.charge()
Fulfillment.ship()
return success
~~~

Nếu Payments timeout, không thể chỉ bắt exception và rollback Order DB. Phải có trạng thái trung gian, operation identities, compensation và reconciliation.

### Anti-pattern 2 — Compensation là thao tác đảo SQL trực tiếp

Ordering tự UPDATE inventory.stock để trả hàng. Điều này phá quyền sở hữu domain, bỏ qua invariant và audit. Bên sở hữu Inventory phải thực hiện ReleaseReservation theo contract.

### Anti-pattern 3 — Orchestrator giữ trạng thái chỉ trong RAM

Khi process restart, Saga mất bước hiện tại và không biết đã gửi ChargePayment chưa. Cần durable state, inbox/outbox, timeout recovery.

### Anti-pattern 4 — Event choreography không có người sở hữu tiến trình

PaymentRejected được phát, không rõ Inventory hay Ordering phải release stock, không ai phát hiện reservation bị kẹt. Cần rõ responsibility và state/timer owner.

### Anti-pattern 5 — Phát event trước DB commit

Consumer nhận OrderPlaced trong khi Order transaction rollback. Dùng outbox hoặc cơ chế commit/publish đáng tin cậy.

### Anti-pattern 6 — Ack message trước khi commit

Consumer ack command rồi crash trước khi ghi reservation. Message không được giao lại nhưng workflow kẹt. Thiết kế ack sau durable commit, có idempotency.

### Anti-pattern 7 — Retry command với identity mới

Sau timeout, client tạo paymentOperationId mới và gửi ChargePayment lại, có thể thu tiền hai lần. Giữ identity ổn định và tra cứu kết quả.

### Anti-pattern 8 — Một event làm thay đổi mọi context theo schema private

Producer gửi nguyên DB entity gồm nhiều field nội bộ; consumer phụ thuộc tên cột và logic chưa công bố. Dùng published contracts có semantics rõ và data minimization.

### Anti-pattern 9 — Xóa message lỗi để giảm lag

Poison message gây lỗi, operator skip offset mà không lưu DLQ/đối soát. Saga có thể vĩnh viễn mắc trạng thái chờ. Cần quarantine, investigation và replay an toàn.

### Anti-pattern 10 — Xem refund là rollback tức thì

Refund có thể mất nhiều ngày, có phí, bị từ chối hoặc đảo ngược. Saga phải theo dõi REFUND_PENDING/FAILED, reconciliation và trách nhiệm hỗ trợ.

### Anti-pattern 11 — Choreography với quá nhiều vòng sự kiện

A phát event làm B phát event, B kích C, C quay lại kích A và tạo vòng lặp. Cần state machine, causation IDs, idempotency, thiết kế event types hoặc chuyển sang điều phối tường minh.

### Anti-pattern 12 — Orchestrator là God Service

Orchestrator chứa toàn bộ quy tắc tồn kho, giá, hoàn tiền và shipping. Nó trở thành monolith phân tán. Giữ business rules trong Bounded Context, Orchestrator chỉ tổ chức tiến trình.

## 27. Khi nào ưu tiên orchestration?

Orchestration thường đáng cân nhắc khi:

- Workflow gồm nhiều bước phụ thuộc và nhiều nhánh điều kiện.
- Compensation phức tạp, có nguy cơ tài chính hoặc dữ liệu quan trọng.
- Cần SLA cho từng bước, timeout/long-running timer, human approval.
- Cần biết rõ tiến trình tổng thể của mỗi Saga và theo dõi manual escalation.
- Thay đổi workflow cần nhìn được tại một nơi.
- Nhiều participant phải dùng chung một chính sách sequencing.
- Dự án đã có workflow/process engine được vận hành tốt.

Ví dụ đặt vé du lịch gồm Flight, Hotel, Payment, Refund và các bước bù với chính sách khác nhau. Một Orchestrator với state bền vững thường giúp thiết kế rõ tiến trình hơn so với việc rải logic trong nhiều event listeners.

Tuy nhiên Orchestrator là một thành phần cần vận hành: HA, persistence, versioning, metrics, authorization và ownership. Nếu chỉ có “OrderPlaced → send email” thì lợi ích có thể không bù chi phí.

## 28. Khi nào choreography phù hợp?

Choreography thường hợp lý khi:

- Nhiều consumer phản ứng độc lập với một domain event.
- Quy trình ngắn, ít nhánh và ít nghĩa vụ bù liên kết.
- Các context muốn mở rộng subscriber mà producer không cần biết.
- Mỗi sự kiện có semantics rõ, ownership và versioning tốt.
- Hạ tầng event broker, schema registry/contract tests, tracing và DLQ đã được vận hành ổn định.
- Có cơ chế theo dõi business state/timer đủ cho quy mô workflow.

Ví dụ OrderConfirmed phát một event và Notifications, Analytics, Loyalty tự cập nhật phần của mình. Nếu Notifications lỗi, hệ thống retry/alert riêng mà không hủy Order; đây là mô hình phù hợp với choreography.

Nhưng nếu việc cộng loyalty points trở thành điều kiện bắt buộc để xác nhận thanh toán hoặc phải bù nhiều bước liên quan, cần xem lại ranh giới workflow và cách điều phối.

## 29. Một quyết định kiến trúc có thể thay đổi theo thời gian

Một dự án khởi đầu có hai service:

~~~text
OrderPlaced -> Inventory reserves stock
StockReserved -> Payments authorizes payment
PaymentAuthorized -> Ordering confirms order
~~~

Choreography có thể đủ. Sau một năm, hệ thống có thêm:

- Đặt trước/giữ hàng theo kho.
- Thanh toán nhiều phương thức, partial capture, voucher.
- Hủy một phần đơn, nhiều shipments.
- Đối soát tiền khi webhook đến muộn.
- SLA xử lý checkout trong 10 phút, nếu trễ phải escalates.
- Xử lý thủ công khi provider không trả kết quả.
- Các quy tắc retry, timeout, compensation chồng chéo.

Lúc đó chuyển phần **quy trình quan trọng** sang Checkout Orchestrator có thể giảm sự phân tán của business workflow. Các event thông báo/analytics vẫn giữ choreography.

Ngược lại, nếu Orchestrator quá lớn vì mỗi feature phụ chỉ gửi một event, nên tách các side effects độc lập thành subscribers. Kiến trúc cần tiến hóa theo complexity thực, không gắn nhãn bất biến cho toàn hệ thống.

## 30. Tổ chức team ownership và hợp đồng

Dùng bảng:

| Khả năng | Team sở hữu ví dụ | Quyền quyết định |
| --- | --- | --- |
| Order aggregate | Team Commerce | Vòng đời đơn và điều kiện xác nhận/hủy |
| Checkout Saga policy | Team Commerce / Workflow Team | Bước tiến, deadline, compensation decisions |
| Stock reservation | Team Inventory | Giữ/giải phóng hàng, khả dụng tồn kho |
| Payment operations | Team Payments | Authorization/capture/refund/reconciliation |
| Fulfillment | Team Logistics | Tạo shipment, xử lý giao/huỷ |
| Event platform | Platform Team | Broker, delivery, schema tooling, monitoring nền tảng |
| Notifications | Team Engagement | Gửi thông báo, templates, retry |

Trong orchestration, owning team của Saga cần làm rõ interface của các participant và không được tự viết business rules của nhóm khác.

Trong choreography, từng team sở hữu events mình công bố và listeners của mình. Phải có ít nhất một đầu mối chịu trách nhiệm cho việc **workflow tổng thể đạt trạng thái hợp lệ**, nhất là khi có tiền và hàng.

### Contract cho một bước

~~~yaml
capability: ReserveStock
owner: Team Inventory
caller: Checkout Saga Orchestrator
command:
  name: ReserveStock
  operationId: reserve-ORD-1001
  orderId: ORD-1001
  items: [BOOK-01 x 2]
outcomes:
  - StockReserved
  - StockRejected
idempotencyScope: tenant-plus-operationId
timeoutHandling: unknown-until-verified
compensation:
  command: ReleaseStock
  requires: reservationId
observability:
  correlationId: checkout-1001
  sagaId: saga-1001
~~~

Đây là tài liệu minh họa, không phải schema chuẩn hay cấu hình chạy trực tiếp.

## 31. Bảo mật và dữ liệu trong Saga

Mỗi message có thể đi qua broker, log, DLQ và những service khác nhau. Cần coi message như một **hợp đồng truy cập dữ liệu**:

- Caller/workload identity phải được xác minh theo service-to-service policy.
- Command có quyền cao như RefundPayment phải được authorization nghiêm ngặt.
- Không tin một field userId/orderId tự điền là bằng chứng quyền.
- Không đưa raw payment credentials, mật khẩu, token hay dữ liệu cá nhân không cần vào events.
- Broker topic/queue ACL giới hạn producer và consumer.
- Dữ liệu trên wire và at rest được bảo vệ phù hợp.
- DLQ/logs cũng cần redaction, retention và quyền truy cập.
- Manual compensation có approval/audit để tránh gian lận.
- Correlation IDs không thay thế security principal.
- Một process worker bị compromise không được có quyền vô điều kiện với mọi participant.

Saga chạy lâu nên phải xét **quyền thay đổi theo thời gian**: user có thể logout hoặc bị thu hồi quyền trong khi workflow vẫn cần hoàn thành nghĩa vụ đã hợp lệ trước đó. Quyết định nào cần xác minh lại quyền, quyết định nào dựa trên cam kết đã được chấp nhận phải có policy nghiệp vụ rõ; không phụ thuộc sự sống của browser session.

## 32. DLQ, retry và xử lý sự cố thủ công

Khi một command/event không xử lý được:

1. Phân biệt lỗi **transient** (DB unavailable, broker reset) và lỗi **permanent** (payload sai schema, thiếu field bắt buộc).
2. Retry có giới hạn và backoff cho lỗi transient, tôn trọng deadline.
3. Không retry nóng một message sai dữ liệu vô hạn.
4. Đưa message cần điều tra vào DLQ/quarantine có source metadata, correlation và error reason.
5. Cảnh báo khi Saga age vượt ngưỡng hoặc compensation bị kẹt.
6. Bảo toàn khả năng replay, không xóa message chỉ để dashboard lag về 0.
7. Có hướng dẫn manual action với approval và audit nếu cần.
8. Sau khi sửa, replay bằng handler idempotent và đối chiếu kết quả nguồn.

### Một trường hợp nhiều lỗi chồng nhau

~~~text
PaymentAuthorized event đến trễ
  -> Saga đã trong COMPENSATING
  -> Orchestrator phát VoidAuthorization
  -> PSP timeout
  -> Worker restart
  -> VoidAuthorization reply tới hai lần
~~~

Thiết kế đúng cần operation ID cho cả authorization và void, state bền vững, cùng semantics khi retry, inbox dedupe và reconciliation. Một hệ thống chỉ dựa vào “đã gọi void thành công ở API” mà không lưu kết quả có thể không biết trạng thái cuối.

## 33. Saga và tính nhất quán dữ liệu

Các trạng thái trung gian là bình thường nhưng **không tùy tiện để trạng thái sai sống vô hạn**.

Ví dụ:

~~~text
Ordering:    Order=PAYMENT_PENDING
Inventory:   Reservation=RESERVED
Payments:    Payment=AUTHORIZED
Fulfillment: NOT_REQUESTED
~~~

Một thời gian ngắn sau event, Ordering có thể chưa cập nhật; đó là eventual consistency. Hệ thống nên có:

- Trạng thái chờ có deadline.
- Reconciliation job tìm những Saga/event không tiến.
- Quy tắc release reservation khi workflow bỏ dở.
- Query từ source authority khi cần xác nhận tiền.
- Read model/projection thể hiện dữ liệu còn đồng bộ hay chưa.
- UX không đẩy khách thanh toán lại chỉ vì màn hình chưa nhận event.

**Các invariant mạnh vẫn nằm trong local transactions của từng context.** Saga phối hợp giữa chúng bằng thông điệp và compensation, không thay thế atomic update bên trong Inventory hay Payment.

## 34. Bài thực hành: thiết kế hai Saga cho một đơn

### Bài 1 — Vẽ orchestration

Cho các service Ordering, Inventory, Payments, Fulfillment. Vẽ Checkout Orchestrator gửi ReserveStock và AuthorizePayment rồi ConfirmOrder. Thêm nhánh PaymentRejected: ReleaseStock → CancelOrder. Ghi rõ Saga ID, operation ID và trạng thái WAITING ở từng bước.

### Bài 2 — Vẽ choreography

Với cùng bài toán, thiết kế chuỗi OrderPlaced → StockReserved → PaymentAuthorized → OrderConfirmed. Thêm StockRejected và PaymentRejected. Nêu rõ team nào nghe event, ai phát event và ai chịu trách nhiệm phát hiện trường hợp không có phản hồi.

### Bài 3 — Mất response sau commit

Payments đã authorize thành công nhưng Orchestrator chỉ nhận DEADLINE_EXCEEDED. Có được phát AuthorizePayment lần nữa với ID mới không? Trình bày cách tra cứu payment attempt, đối soát và retry theo identity ổn định.

### Bài 4 — Compensation không thực hiện được

Shipping đã bàn giao hàng cho carrier; Saga yêu cầu CancelShipment nhưng carrier từ chối. Hãy thiết kế trạng thái exception, quy trình vận hành và nghĩa vụ hoàn tiền/đổi hàng nếu có. Giải thích vì sao SQL ROLLBACK không giải quyết được.

### Bài 5 — Replay event

Broker giao PaymentAuthorized hai lần. Thiết kế inbox và transition guard để không ConfirmOrder hai lần và không tạo shipment trùng. Phân biệt eventId và operationId.

### Bài 6 — Event đến sau khi Saga hoàn tất

Một StockReserved từ lần thử cũ tới sau khi đơn đã Cancelled. Hệ thống cần làm gì để bảo đảm không còn reservation bị giữ trái ý muốn? Nêu cách kiểm tra operationId/reservationId và reconciliation.

### Bài 7 — Nhiều kho

Một Order đặt sản phẩm ở WH-1 và WH-2. WH-1 giữ được hàng, WH-2 từ chối. Thiết kế compensation release đúng reservation đã commit, không release nhầm lần đặt khác.

### Bài 8 — Outbox publisher crash

Order DB đã commit OrderPlaced trong Outbox, publisher gửi Kafka thành công rồi crash trước checkpoint. Hãy mô tả vì sao event có thể đến hai lần và cách consumer bảo đảm một reservation.

### Bài 9 — Saga State DB mất kết nối

Orchestrator đã phát ReserveStock rồi không lưu được bước tiếp theo. Thiết kế transaction/outbox và bước phục hồi an toàn. Vì sao giữ Saga state trong Java static Map không đủ?

### Bài 10 — Chuyển dần từ choreography sang orchestration

Một hệ thống có ba event handlers và thêm nhiều nhánh refund/compensation. Đề xuất lộ trình phân tách workflow controller, giữ domain events công khai, từng bước chuyển quyền quyết định thứ tự mà không tạo hai orchestrators cùng điều khiển một Saga.

## 35. Câu hỏi tự kiểm tra

1. Saga khác local database transaction và 2PC như thế nào?
2. Orchestration có nghĩa Orchestrator sở hữu database của mọi participant không?
3. Choreography có bắt buộc hoàn toàn không có state hay timer không?
4. Command khác event ở điều kiện nào?
5. StockReserved có nên được phát trước khi Inventory commit reservation không?
6. Vì sao timeout không thể tự đồng nghĩa PaymentRejected?
7. Idempotency key nào cần ổn định khi retry AuthorizePayment?
8. Message ID, operation ID và Saga ID khác nhau thế nào?
9. Tại sao Outbox không thay thế Inbox hoặc idempotent consumer?
10. Khi nào nên bù bằng RefundPayment thay vì VoidAuthorization?
11. Compensation có thể thất bại không? Khi đó ai xử lý?
12. Choreography có nguy cơ coupling ẩn như thế nào?
13. Vì sao Notifications fail không nên mặc định hủy Order đã thanh toán?
14. Một Saga kéo dài nhiều ngày có thể giữ trạng thái chỉ trong memory không?
15. Một reply mang orderId đúng nhưng operationId sai có được áp vào Saga hiện tại không?
16. Tại sao cần kiểm tra event versions trong rolling deployment?
17. Các sự kiện từ Payments và Inventory có total order chung mặc định không?
18. Manual review nên có những thông tin và quyền nào?
19. Những tín hiệu quan sát nào giúp phát hiện Saga bị kẹt?
20. Một quy trình chỉ cần ghi hai bảng cùng database có nhất thiết phải dùng Saga không?

## 36. Checklist trước khi triển khai Saga

| Hạng mục | Câu hỏi quyết định |
| --- | --- |
| Business outcome | Khi nào xem workflow thành công, thất bại hoặc đang chờ? |
| Saga boundary | Những bước nào thực sự thuộc cùng một nghĩa vụ nghiệp vụ? |
| Coordination model | Orchestration, choreography hay kết hợp? |
| Owner | Team nào quyết định trình tự, timeout và escalation? |
| Participant ownership | Service nào sở hữu từng local transaction? |
| Commands/events | Hợp đồng, semantics, producer và consumer? |
| State persistence | Saga progress được lưu bền vững ở đâu? |
| Local invariants | Constraint/version/transaction nào bảo vệ mỗi context? |
| Compensation | Bước nào có thể bù, bù thế nào, có hoàn toàn không? |
| Pivot | Khi nào không còn khả năng hủy đơn giản? |
| Idempotency | Operation IDs, message IDs, key scope và retention? |
| Reliability | Outbox, inbox, ack/offset, retry, backoff, DLQ? |
| Timeout | Trạng thái chưa rõ được đối soát bằng nguồn nào? |
| Ordering | Per-aggregate sequence/version và xử lý event đến muộn? |
| Security | Workload authn/authz, PII, secrets, manual approval? |
| Versioning | Events và workflow definitions có chạy song song an toàn? |
| Observability | Saga age, step latency, compensation failures, tracing? |
| Recovery | Restart/replay/reconciliation và tình huống provider timeout? |
| Testing | Happy path, lỗi ở mọi bước, duplicate, out-of-order, crash? |
| Operations | Dashboard, alerts, runbook và owner xử lý thủ công? |

## 37. Kết luận

**Saga** là mẫu điều phối những giao dịch cục bộ thành một quy trình nghiệp vụ có kết quả hợp lệ, có thể dùng **các hành động bù** khi một bước sau thất bại. Saga **không** đem lại tính nguyên tử toàn cục và không miễn nhu cầu xử lý trạng thái trung gian.

Trong **orchestration**, một Orchestrator/Process Manager giữ tiến trình, gửi commands và quản lý compensation/timers; đổi lại phải vận hành một thành phần điều phối bền vững và tránh biến nó thành God Service.

Trong **choreography**, các services công bố events và tự phản ứng; producer ít biết trực tiếp consumer hơn, nhưng workflow dễ phân tán, có coupling ẩn, cần ownership, observability, timeout và policy bù rõ ràng.

Dù dùng cách nào, nền tảng chung vẫn là **transaction cục bộ, nguồn sự thật theo Bounded Context, idempotency, outbox/inbox, xử lý duplicate/out-of-order, đối soát khi timeout, bù có thể thất bại và trạng thái được lưu bền vững**. Một thiết kế Saga tốt không chỉ chỉ ra đường thành công, mà còn trả lời được câu hỏi quan trọng nhất: **khi tiền, hàng và đơn đã thay đổi một phần rồi hệ thống gặp lỗi, ai chịu trách nhiệm đưa nghiệp vụ về một kết quả đúng và có thể kiểm chứng?**

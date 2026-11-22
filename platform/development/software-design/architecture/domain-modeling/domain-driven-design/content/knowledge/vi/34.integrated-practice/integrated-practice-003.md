# Đề xuất Bounded Context và Context Map cho đặt hàng, kho và thanh toán

Một quy trình đặt hàng thường đi qua nhiều năng lực nghiệp vụ: tiếp nhận đơn, kiểm tra và giữ tồn kho, ủy quyền thanh toán, rồi xác nhận đơn. Nếu gom tất cả vào một mô hình Order lớn, mô hình đó sẽ phải hiểu cả cách quản lý số lượng kho, vòng đời giao dịch thanh toán và chính sách đặt hàng. Nếu tách theo bảng hoặc theo service một cách máy móc, các ranh giới mới có thể chỉ sao chép sự phụ thuộc của hệ thống cũ.

Domain-Driven Design (DDD) giúp tìm ranh giới dựa trên ngôn ngữ, trách nhiệm và invariant nghiệp vụ. Bài thực hành này đề xuất ba Bounded Context: Ordering, Inventory và Payment; mô tả Context Map giữa chúng; xác định Aggregate, Value Object, Repository và Domain Event; sau đó ghép chúng thành một quy trình đặt hàng có thể phục hồi khi một bước thất bại.

Đây là một mô hình tham khảo cho hệ thống bán hàng trực tuyến. Chính sách cụ thể như thời hạn giữ hàng, thời điểm thu tiền, cho phép backorder hay xử lý giao hàng từng phần cần được xác nhận với chuyên gia nghiệp vụ trước khi triển khai.

## 1. Bài toán và phạm vi

Một khách hàng đặt một đơn có một hoặc nhiều sản phẩm. Hệ thống cần:

1. Tiếp nhận thông tin đơn và chốt giá tại thời điểm đặt.
2. Kiểm tra và giữ đủ số lượng hàng.
3. Yêu cầu nhà cung cấp thanh toán ủy quyền khoản tiền cần thiết.
4. Xác nhận đơn khi các điều kiện nghiệp vụ đã hoàn tất.
5. Xử lý khi kho từ chối, thanh toán bị từ chối, timeout hoặc một hệ thống tạm thời không khả dụng.

Mỗi năng lực có dữ liệu và quy tắc riêng. Ví dụ:

- Ordering quyết định đơn có hợp lệ để đặt hay không, đơn đang ở trạng thái nào và khách đã chấp nhận điều khoản nào.
- Inventory quyết định số lượng nào có thể được giữ, reservation nào còn hiệu lực và có thể giải phóng hay không.
- Payment quyết định một yêu cầu ủy quyền/thanh toán có hợp lệ, đã được xử lý hay đã bị từ chối.

Mục tiêu là đề xuất ranh giới có thể bảo vệ các quy tắc đó và hợp đồng để phối hợp giữa chúng.

### 1.1. Giả định làm việc

Để ví dụ nhất quán, bài thực hành dùng các giả định sau:

- Một đơn được xác nhận khi kho đã giữ đủ hàng và thanh toán đã được ủy quyền.
- Mỗi yêu cầu giữ hàng có một reservation ID ổn định.
- Mỗi yêu cầu thanh toán có một payment request ID/idempotency key ổn định.
- Quy trình có thể hoàn tất bất đồng bộ; trạng thái chờ được hiển thị cho người dùng.
- Mỗi Bounded Context sở hữu dữ liệu và invariant của mình.
- Các context giao tiếp qua command/API và event contract, không ghi trực tiếp database của nhau.

Đây là giả định cho bài tập, không phải quy tắc phổ quát. Một số doanh nghiệp thu tiền sau khi giao, cho phép giao từng phần hoặc cho phép đặt trước khi chưa có hàng. Những lựa chọn đó sẽ thay đổi trạng thái và quy trình nhưng không làm mất nguyên tắc phân định quyền sở hữu.

## 2. Khám phá ngôn ngữ và trách nhiệm nghiệp vụ

Trước khi đặt tên service, hãy làm rõ các thuật ngữ với chuyên gia:

| Thuật ngữ | Ý nghĩa trong ví dụ | Câu hỏi cần xác nhận |
|---|---|---|
| Order | Cam kết mua hàng do khách tạo | Khi nào đơn được coi là đã đặt? |
| Order Line | Một mặt hàng và số lượng khách muốn mua | SKU có thể xuất hiện nhiều dòng không? |
| Unit Price Snapshot | Giá được chốt cho dòng hàng | Giá chốt tại lúc thêm giỏ hay lúc đặt? |
| Reservation | Lượng hàng được giữ cho một đơn | Giữ hàng trong bao lâu? |
| Available Quantity | Lượng có thể cấp phát | Có trừ hàng lỗi, hàng đang kiểm kê và reservation hết hạn không? |
| Payment Authorization | Xác nhận khả năng thanh toán/giữ hạn mức | Khi nào capture/thu tiền? |
| Payment Capture | Ghi nhận khoản tiền đã thu | Có thể capture nhiều lần hoặc theo từng phần không? |
| Order Confirmation | Đơn đã thỏa điều kiện xác nhận | Có cần thêm điều kiện giao hàng hoặc chống gian lận không? |

Các thuật ngữ gần nhau cần được phân biệt. “Giữ hàng” không có nghĩa hàng đã được xuất kho. “Ủy quyền thanh toán” không nhất thiết có nghĩa tiền đã được thu. “Đặt đơn” cũng không đồng nghĩa “xác nhận đơn” nếu quy trình cần chờ kho và payment.

### 2.1. Tìm invariant của từng năng lực

Invariant là điều kiện phải luôn đúng trong phạm vi nhất quán mà một mô hình có thể bảo vệ.

| Năng lực | Invariant ứng viên |
|---|---|
| Ordering | Đơn phải có ít nhất một dòng hợp lệ khi được đặt; đơn đã xác nhận không thể sửa dòng hàng; tổng tiền và tiền tệ nhất quán |
| Inventory | Không giữ vượt số lượng có thể cấp phát; một reservation ID không tạo ra hai lần giữ hàng; chỉ reservation hợp lệ mới được giải phóng |
| Payment | Một payment request ID không được tạo hai lần ủy quyền; số tiền và tiền tệ phải khớp yêu cầu; giao dịch chỉ chuyển theo trạng thái hợp lệ |

Mỗi invariant phải có một context chịu trách nhiệm. Không nên để Ordering tự cập nhật số lượng kho hoặc tự đặt trạng thái giao dịch Payment để “giữ cho dữ liệu đồng bộ”.

## 3. Đề xuất ba Bounded Context

### 3.1. Ordering Context

**Mục tiêu:** quản lý ý định mua hàng và vòng đời đơn hàng.

Ordering sở hữu:

- Order và Order Line.
- Giá, thuế, chiết khấu hoặc phí được chốt theo chính sách của đơn.
- Trạng thái nghiệp vụ của đơn.
- Thông tin tham chiếu tới khách hàng, SKU, reservation và payment.
- Quyết định xác nhận, từ chối hoặc hủy đơn theo điều kiện mà Ordering chịu trách nhiệm.

Ordering không sở hữu:

- Số lượng vật lý, số lượng khả dụng và reservation của kho.
- Trạng thái giao dịch thanh toán thực tế.
- Chi tiết giao tiếp với nhà cung cấp payment.

Ordering có thể lưu ReservationId và PaymentId như reference. Reference không có nghĩa Ordering được quyền thay đổi Aggregate thuộc context kia.

### 3.2. Inventory Context

**Mục tiêu:** bảo vệ tính đúng đắn của tồn kho và cấp phát hàng.

Inventory sở hữu:

- Stock Item theo SKU, warehouse hoặc location.
- Số lượng hiện có, đã giữ và có thể cấp phát.
- Reservation và thời hạn reservation.
- Quy tắc giữ, giải phóng, xác nhận xuất kho và điều chỉnh tồn kho.

Inventory không cần biết toàn bộ cấu trúc Order, chính sách khách hàng hay cách tính chiết khấu. Nó nhận yêu cầu giữ hàng với SKU, số lượng và tham chiếu nghiệp vụ cần thiết.

### 3.3. Payment Context

**Mục tiêu:** quản lý vòng đời giao dịch thanh toán.

Payment sở hữu:

- Payment Intent/Transaction.
- Authorization, capture, void và refund.
- Idempotency key và tham chiếu nhà cung cấp.
- Trạng thái, số tiền, tiền tệ và lịch sử giao dịch.
- Mapping lỗi từ cổng thanh toán thành kết quả có ý nghĩa trong Payment.

Payment không sở hữu trạng thái Order. Nó có thể phát PaymentAuthorized hoặc PaymentDeclined; Ordering quyết định trạng thái đơn dựa trên kết quả đó và các điều kiện còn lại.

### 3.4. Bảng quyền sở hữu

| Khái niệm | Context sở hữu | Context khác được phép làm gì? |
|---|---|---|
| Order | Ordering | Gửi command hoặc nhận event về kết quả đơn |
| Order Line | Ordering | Tham chiếu SKU và dữ liệu giá đã chốt |
| Stock Item | Inventory | Gửi yêu cầu giữ/giải phóng; đọc thông tin được công bố |
| Reservation | Inventory | Lưu ReservationId để theo dõi |
| Payment Intent | Payment | Gửi yêu cầu authorize/capture/void/refund |
| Payment Transaction | Payment | Lưu PaymentId và xử lý event kết quả |
| Order Summary projection | Read Model/Reporting | Đọc để hiển thị, không dùng làm nguồn quyết định invariant |

## 4. Context Map và quan hệ giữa các context

Trong đề xuất này, Inventory và Payment là upstream supplier đối với Ordering ở các hợp đồng dữ liệu/dịch vụ mà chúng cung cấp. Ordering là downstream customer vì nó phụ thuộc kết quả giữ hàng và thanh toán để hoàn tất đơn.

Context Map cần phân biệt hai chiều:

- **Supplier contract/event:** dữ liệu và kết quả mà context upstream công bố cho downstream.
- **Command/API request:** lệnh mà Ordering gửi tới Inventory hoặc Payment để yêu cầu hành động.

Hai chiều có thể đi ngược nhau trong cùng một quan hệ. Upstream/downstream mô tả ảnh hưởng của mô hình và hợp đồng, không có nghĩa mọi message đều đi một chiều.

~~~mermaid
flowchart LR
    I[Inventory Context<br/>Upstream Supplier]
    P[Payment Context<br/>Upstream Supplier]
    O[Ordering Context<br/>Downstream Customer]
    R[Reporting / Read Model]

    I -->|Published Language:<br/>InventoryReserved / Rejected| O
    P -->|Published Language:<br/>PaymentAuthorized / Declined| O
    O -->|Order events| R
    I -->|Inventory events| R
    P -->|Payment events| R

    O -.->|Reserve / Release command| I
    O -.->|Authorize / Void command| P
~~~

Mũi tên liền biểu diễn hướng công bố event/dữ liệu trong sơ đồ; mũi tên nét đứt biểu diễn command từ Ordering tới provider. Khi vẽ Context Map cho tổ chức thực tế, cần ghi thêm team ownership, khả năng thay đổi contract và mức độ phối hợp giữa các nhóm.

### 4.1. Customer–Supplier

Ordering cần Inventory và Payment cung cấp các kết quả có hợp đồng ổn định. Nếu các nhóm phối hợp roadmap và thống nhất thay đổi contract, quan hệ Customer–Supplier có thể phù hợp.

Supplier cần:

- Công bố semantics của command/event.
- Quản lý version và tương thích ngược.
- Thông báo thay đổi phá vỡ contract.
- Cung cấp SLA và chính sách lỗi.

Customer cần:

- Nêu rõ dữ liệu và hành vi cần dùng.
- Không phụ thuộc schema nội bộ của supplier.
- Có kiểm thử contract và xử lý version.
- Không giả định response luôn đến tức thời.

### 4.2. Open Host Service và Published Language

Inventory có thể cung cấp API/command endpoint chuẩn để giữ hàng; Payment cung cấp API để authorize. Event được công bố theo Published Language như InventoryReserved, PaymentAuthorized.

Published Language là hợp đồng tích hợp, không phải toàn bộ domain model nội bộ. Event không nên chứa ORM entity hoặc object graph nội bộ của Aggregate.

### 4.3. Anti-Corruption Layer

Nếu Payment tích hợp với nhà cung cấp bên ngoài hoặc Inventory còn nằm trong legacy, ACL đặt ở ranh giới đó để dịch mô hình provider/legacy sang mô hình nội bộ.

Ordering cũng có thể có ACL nếu phải tiêu thụ contract legacy. Khi ba context mới giao tiếp qua hợp đồng đã thiết kế cho nhau, không nhất thiết mỗi quan hệ đều cần một ACL đầy đủ; một adapter/translator nhỏ có thể đủ. ACL đặc biệt hữu ích khi mô hình upstream có semantics khác biệt hoặc không do nhóm kiểm soát.

### 4.4. Reporting là consumer, không phải owner

Reporting có thể subscribe event từ ba context để xây Order Summary, doanh thu hoặc trạng thái fulfillment. Read model có thể trễ và được xây lại. Nó không được dùng để quyết định giữ hàng hoặc xác nhận thanh toán.

## 5. Tactical Design: Aggregate và Value Object

Aggregate được chọn theo invariant cần bảo vệ, không phải theo quan hệ object hoặc việc muốn gom mọi dữ liệu vào một graph.

### 5.1. Ordering Aggregate

Aggregate Root: Order.

Các thành phần có thể gồm:

- OrderId
- CustomerId
- OrderLine (SKU, quantity, unit price snapshot)
- Money (subtotal, discount, tax, total)
- OrderStatus
- ReservationId và PaymentId sau khi có kết quả tương ứng

Invariant:

- Chỉ đơn nháp mới được sửa dòng hàng.
- Không thể đặt đơn rỗng.
- Mọi dòng hàng phải có quantity hợp lệ và giá cùng currency.
- Khi đặt đơn, giá và chính sách được chốt theo thời điểm nghiệp vụ đã xác định.
- Chỉ xác nhận khi điều kiện kho và thanh toán đã được thỏa.

Không đưa danh sách stock item hoặc toàn bộ payment transaction vào Order Aggregate. Chúng thuộc Aggregate của context khác.

### 5.2. Inventory Aggregate

Aggregate Root ứng viên: StockItem theo SKU và warehouse, hoặc một Aggregate reservation riêng nếu quy mô và invariant yêu cầu.

Invariant:

- Available quantity không âm.
- Reserved quantity không vượt quá lượng có thể cấp phát.
- Cùng một reservation ID không giữ hàng hai lần.
- Chỉ reservation ở trạng thái hợp lệ mới được release/commit.
- Các thao tác đồng thời không được làm vượt tồn kho.

Nếu một đơn có nhiều SKU ở nhiều kho, Inventory có thể thực hiện phân bổ theo policy và quản lý reservation ở cấp use case. Không nên gom toàn bộ kho vào một Aggregate chỉ để có một transaction khổng lồ.

### 5.3. Payment Aggregate

Aggregate Root ứng viên: PaymentIntent hoặc PaymentTransaction.

Invariant:

- Payment request ID là duy nhất trong phạm vi xác định.
- Amount và currency không thay đổi tùy tiện sau authorization.
- Một intent không được authorize lặp thành nhiều giao dịch ngoài ý muốn.
- Capture không vượt quá số tiền được authorize theo chính sách.
- Void/refund chỉ được thực hiện ở trạng thái cho phép.

Payment Aggregate lưu trạng thái nghiệp vụ và tham chiếu provider. Không để Ordering gọi trực tiếp SDK provider rồi tự cập nhật payment status.

### 5.4. Value Object dùng trong từng context

| Value Object | Ý nghĩa |
|---|---|
| Sku | Mã sản phẩm theo quy tắc nội bộ |
| Quantity | Số lượng và đơn vị có ý nghĩa |
| Money | Amount đi cùng currency và phép toán hợp lệ |
| OrderId | Định danh đơn |
| ReservationId | Định danh yêu cầu giữ hàng |
| PaymentRequestId | Định danh yêu cầu thanh toán/idempotency |
| WarehouseId | Định danh kho |
| TimeWindow | Khoảng thời gian reservation có hiệu lực |

Tên và kiểu có thể giống nhau giữa các context, nhưng không bắt buộc chia sẻ cùng một class/package. Mỗi context có thể định nghĩa Value Object phù hợp với semantics của nó; contract integration dùng kiểu dữ liệu ổn định và được dịch ở biên.

## 6. Repository và quyền truy cập dữ liệu

Mỗi Repository làm việc với Aggregate Root thuộc context sở hữu:

| Repository | Context | Trách nhiệm |
|---|---|---|
| OrderRepository | Ordering | Load/save Order |
| StockItemRepository | Inventory | Load/save StockItem |
| ReservationRepository | Inventory | Tra cứu reservation theo ID khi reservation là Aggregate riêng |
| PaymentIntentRepository | Payment | Load/save PaymentIntent |

Không tạo OrderRepository có method cập nhật trực tiếp tồn kho hoặc trạng thái Payment. Không để một transaction repository xuyên ba database giả vờ rằng cả ba Aggregate có cùng consistency boundary.

Các truy vấn cho màn hình có thể dùng Query Service/read model riêng. Repository tập trung vào Aggregate; read model tối ưu theo câu hỏi cần trả lời.

## 7. Command và Domain Event giữa các context

Command là yêu cầu thực hiện hành động; event là sự thật đã xảy ra. Đặt tên và contract cần phân biệt hai loại này.

| Context nhận | Command | Event kết quả |
|---|---|---|
| Ordering | PlaceOrder | OrderSubmitted |
| Inventory | ReserveInventory | InventoryReserved hoặc InventoryReservationRejected |
| Inventory | ReleaseReservation | InventoryReleased hoặc ReservationReleaseFailed |
| Payment | AuthorizePayment | PaymentAuthorized hoặc PaymentDeclined |
| Payment | VoidAuthorization | PaymentAuthorizationVoided |
| Ordering | ConfirmOrder | OrderConfirmed |
| Ordering | RejectOrder | OrderRejected |

Event nên chứa dữ liệu đủ để consumer hiểu sự kiện mà không phải truy vấn schema nội bộ của producer. Ví dụ:

~~~json
{
  "eventId": "evt-901",
  "eventType": "InventoryReserved",
  "schemaVersion": 1,
  "occurredAt": "2026-11-18T10:15:30Z",
  "correlationId": "checkout-781",
  "causationId": "cmd-reserve-55",
  "reservationId": "res-440",
  "orderId": "ord-1001",
  "warehouseId": "wh-01",
  "lines": [
    {"sku": "SKU-01", "quantity": 2}
  ],
  "expiresAt": "2026-11-18T10:30:30Z"
}
~~~

Payload chỉ là ví dụ. Cần xác định timezone, precision, currency, đơn vị, schema compatibility, thông tin nhạy cảm và quyền truy cập trước khi công bố contract.

### 7.1. Correlation và causation

correlationId liên kết các message thuộc cùng quy trình đặt hàng. causationId chỉ ra command/event nào gây ra message hiện tại. Các ID này giúp theo dõi một quy trình qua Ordering, Inventory và Payment.

Không nên dùng timestamp làm thứ tự duy nhất giữa các context vì clock có thể lệch. Dùng stream revision, sequence hoặc version theo Aggregate khi cần phát hiện event cũ.

## 8. Quy trình tổng thể: Saga do Ordering điều phối

Đặt hàng qua ba context là một quy trình nhiều local transaction. Không có một transaction database chung bao trùm Order, StockItem và PaymentIntent.

Một Process Manager/Saga trong Ordering có thể theo dõi quy trình:

1. Ordering nhận PlaceOrder, kiểm tra Order và lưu trạng thái PENDING.
2. Ordering phát ReserveInventory.
3. Inventory kiểm tra và giữ hàng trong transaction của Inventory.
4. Inventory phát InventoryReserved hoặc InventoryReservationRejected.
5. Nếu giữ hàng thành công, Ordering phát AuthorizePayment.
6. Payment thực hiện authorization và phát PaymentAuthorized hoặc PaymentDeclined.
7. Khi payment được authorize, Ordering xác nhận đơn.
8. Nếu payment bị từ chối, Ordering yêu cầu Inventory giải phóng reservation rồi chuyển đơn sang trạng thái thất bại/hủy theo chính sách.

~~~mermaid
sequenceDiagram
    participant C as Customer
    participant O as Ordering / Saga
    participant I as Inventory
    participant P as Payment

    C->>O: PlaceOrder
    O->>O: Save Order PENDING
    O->>I: ReserveInventory
    I->>I: Check invariant and commit reservation
    I-->>O: InventoryReserved
    O->>P: AuthorizePayment
    P->>P: Authorize and commit result
    P-->>O: PaymentAuthorized
    O->>O: ConfirmOrder
    O-->>C: OrderConfirmed
~~~

### 8.1. Nhánh giữ hàng thất bại

Nếu Inventory từ chối vì không đủ hàng, Ordering không gửi yêu cầu authorization. Saga chuyển đơn sang REJECTED hoặc trạng thái chờ xử lý khác theo chính sách backorder.

~~~mermaid
sequenceDiagram
    participant O as Ordering / Saga
    participant I as Inventory
    O->>I: ReserveInventory
    I-->>O: InventoryReservationRejected
    O->>O: RejectOrder
~~~

### 8.2. Nhánh thanh toán bị từ chối

Nếu hàng đã được giữ nhưng Payment từ chối authorization, Ordering phải giải phóng reservation. Việc giải phóng là một command mới trong Inventory, không phải rollback transaction đã commit ở Inventory.

~~~mermaid
sequenceDiagram
    participant O as Ordering / Saga
    participant I as Inventory
    participant P as Payment
    O->>I: ReserveInventory
    I-->>O: InventoryReserved
    O->>P: AuthorizePayment
    P-->>O: PaymentDeclined
    O->>I: ReleaseReservation
    I-->>O: InventoryReleased
    O->>O: Mark Order payment failed
~~~

Nếu release thất bại, saga cần trạng thái COMPENSATION_PENDING hoặc MANUAL_REVIEW, retry có giới hạn và cảnh báo vận hành. Không được đánh dấu hoàn tất hủy trong khi reservation vẫn còn hiệu lực mà không thể hiện sự thật đó.

### 8.3. Timeout và kết quả chưa xác định

Timeout không chứng minh thao tác thất bại. Payment có thể đã authorize nhưng response bị mất. Ordering cần gửi lại cùng paymentRequestId hoặc truy vấn trạng thái theo ID đó. Không tạo một request ID mới cho mỗi lần retry, nếu không có thể phát sinh hai authorization.

Tương tự, lệnh giữ hàng cần reservationId ổn định. Consumer phải xử lý lặp idempotent và trả lại kết quả trước đó nếu cùng yêu cầu đã được xử lý.

### 8.4. Orchestration và choreography

Trong ví dụ, Ordering orchestration vì quy trình có nhiều bước, timeout và compensation. Process Manager lưu trạng thái saga và phát command tiếp theo dựa trên event nhận được.

Choreography có thể phù hợp với luồng ngắn, ít nhánh, trong đó các context phản ứng với event. Nhưng khi quy trình có nhiều nhánh lỗi và cần một nơi theo dõi tiến độ, orchestration thường dễ quan sát hơn.

### 8.5. Ví dụ Inventory Aggregate giữ hàng

Đoạn mã sau minh họa cách Inventory bảo vệ invariant tại Aggregate Root. Các kiểu phụ trợ được rút gọn để tập trung vào hành vi:

~~~java
record ReservationId(String value) {}
record OrderId(String value) {}

record Quantity(int value) {
    Quantity {
        if (value <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
    }
}

enum ReservationStatus {
    ACTIVE, RELEASED, COMMITTED
}

record Reservation(
    ReservationId id,
    OrderId orderId,
    Quantity quantity,
    ReservationStatus status
) {
    boolean matches(OrderId order, Quantity requested) {
        return orderId.equals(order) && quantity.equals(requested);
    }
}

record InventoryReserved(
    ReservationId reservationId,
    OrderId orderId,
    Quantity quantity
) {}

final class StockItem {
    private final Sku sku;
    private int onHand;
    private int reserved;
    private final Map<ReservationId, Reservation> reservations =
        new HashMap<>();

    InventoryReserved reserve(
            ReservationId reservationId,
            OrderId orderId,
            Quantity quantity) {
        Reservation previous = reservations.get(reservationId);
        if (previous != null) {
            if (!previous.matches(orderId, quantity)) {
                throw new IdempotencyKeyConflict();
            }
            if (previous.status() != ReservationStatus.ACTIVE) {
                throw new ReservationAlreadyFinalized();
            }
            return new InventoryReserved(reservationId, orderId, quantity);
        }

        int available = onHand - reserved;
        if (quantity.value() > available) {
            throw new InsufficientStock(sku);
        }

        reserved += quantity.value();
        reservations.put(
            reservationId,
            new Reservation(
                reservationId, orderId, quantity, ReservationStatus.ACTIVE
            )
        );
        return new InventoryReserved(reservationId, orderId, quantity);
    }
}
~~~

Đây là mã minh họa, cần bổ sung constructor, getter, release/commit và kiểu lỗi theo domain thực tế. Trong ứng dụng thật, việc kiểm tra revision và lưu StockItem phải diễn ra nguyên tử bằng optimistic locking hoặc cơ chế concurrency phù hợp. Event chỉ được publish sau khi transaction commit, thường thông qua outbox.

Ví dụ cũng cho thấy idempotency cần kiểm tra cả nội dung request. Nếu cùng reservation ID nhưng order hoặc quantity khác, đó là xung đột khóa idempotency, không được trả kết quả thành công giả.

### 8.6. Ví dụ Process Manager điều phối

Process Manager lưu tiến độ saga và phát command tiếp theo. Pseudocode:

~~~java
final class OrderProcessManager {
    private final SagaRepository sagas;
    private final CommandOutbox commands;

    void on(OrderSubmitted event) {
        sagas.startIfAbsent(
            event.orderId(),
            event.correlationId(),
            SagaStage.WAITING_FOR_INVENTORY
        );
        commands.enqueueOnce(
            "reserve-" + event.orderId(),
            new ReserveInventory(
                event.orderId(),
                event.reservationId(),
                event.lines()
            )
        );
    }

    void on(InventoryReserved event) {
        OrderSaga saga = sagas.load(event.orderId());
        if (!saga.isWaitingForInventory()) {
            return;
        }
        saga.recordReservation(event.reservationId());
        saga.moveTo(SagaStage.WAITING_FOR_PAYMENT);
        sagas.save(saga);
        commands.enqueueOnce(
            "authorize-" + event.orderId(),
            new AuthorizePayment(
                event.orderId(),
                saga.paymentRequestId(),
                saga.amount()
            )
        );
    }

    void on(PaymentAuthorized event) {
        OrderSaga saga = sagas.load(event.orderId());
        if (!saga.isWaitingForPayment()) {
            return;
        }
        saga.recordPayment(event.paymentId());
        saga.moveTo(SagaStage.CONFIRMING_ORDER);
        sagas.save(saga);
        commands.enqueueOnce(
            "confirm-" + event.orderId(),
            new ConfirmOrder(event.orderId(), event.paymentId())
        );
    }

    void on(PaymentDeclined event) {
        OrderSaga saga = sagas.load(event.orderId());
        if (!saga.canCompensateReservation()) {
            return;
        }
        saga.moveTo(SagaStage.RELEASING_INVENTORY);
        sagas.save(saga);
        commands.enqueueOnce(
            "release-" + event.orderId(),
            new ReleaseReservation(event.orderId(), saga.reservationId())
        );
    }
}
~~~

Pseudocode chưa mô tả đầy đủ các handler timeout, reservation release result, payment void, retry và manual review. Trong triển khai, cập nhật saga state và ghi command vào outbox cần cùng transaction. Consumer cần Inbox/deduplication theo event ID; command ID phải ổn định để retry không tạo side effect trùng.

Không nhất thiết lưu toàn bộ saga state bên trong Order Aggregate. Order sở hữu vòng đời đơn; Process Manager sở hữu tiến độ phối hợp nhiều context. Hai trạng thái liên quan nhưng có mục đích và vòng đời khác nhau.

## 9. Consistency boundary và eventual consistency

Mỗi context có local transaction bảo vệ invariant của nó:

- Ordering transaction cập nhật Order và trạng thái saga.
- Inventory transaction cập nhật StockItem/Reservation.
- Payment transaction cập nhật PaymentIntent/Transaction.

Các context hội tụ qua event và command. Vì vậy, người dùng có thể thấy đơn PENDING trong lúc Inventory hoặc Payment đang xử lý. Đây là trạng thái trung gian hợp lệ nếu được mô hình hóa và truyền đạt rõ.

### 9.1. Không dùng read model để bảo vệ invariant

Read model có thể trễ. Ordering không nên nhìn vào dashboard tồn kho rồi tự quyết định số lượng còn đủ; Inventory phải kiểm tra lại trong transaction của nó. Tương tự, Order Summary không thể chứng minh payment đã authorize.

### 9.2. Transactional Outbox

Nếu Ordering lưu Order rồi publish OrderSubmitted, hai thao tác độc lập có thể lệch nhau. Transactional Outbox ghi thay đổi Aggregate và outbox message trong cùng transaction. Publisher gửi message sau commit và retry khi cần.

Consumer dùng Inbox/deduplication hoặc idempotent handler để tránh xử lý trùng. Cần theo dõi outbox backlog, message tuổi cao và dead-letter.

### 9.3. Không dùng distributed transaction mặc định

Distributed transaction có thể phù hợp trong môi trường có resource manager hỗ trợ và yêu cầu nguyên tử thực sự. Tuy nhiên, API nhà cung cấp payment hoặc hệ thống kho độc lập thường không tham gia transaction chung. Saga với local transaction, trạng thái trung gian và compensation thường thực tế hơn.

## 10. Read Model cho trải nghiệm người dùng

Ordering có thể cung cấp query model cho trang chi tiết đơn:

| Field | Nguồn |
|---|---|
| Order ID, line items, total | Ordering |
| Order status | Ordering |
| Reservation status/expiry | Event từ Inventory |
| Payment status | Event từ Payment |
| Last updated/version | Projection processor |

Read model có thể tổng hợp event từ ba context để hiển thị tiến độ. Nó không được phép cập nhật ngược các Aggregate nguồn. Nếu projection chậm, giao diện có thể hiển thị “Đang xử lý” và timestamp cập nhật gần nhất.

Với yêu cầu read-your-writes, Ordering có thể trả về trạng thái PENDING ngay sau command. UI không cần đợi mọi projection hoàn tất mới phản hồi.

## 11. Thiết kế API và hợp đồng ở mức khái niệm

API command nên phản ánh ý định, không phơi bày cấu trúc bảng:

~~~http
POST /orders
Idempotency-Key: checkout-781
Content-Type: application/json

{
  "customerId": "cus-17",
  "currency": "VND",
  "lines": [
    {"sku": "SKU-01", "quantity": 2}
  ]
}
~~~

Response ban đầu có thể là:

~~~json
{
  "orderId": "ord-1001",
  "status": "PENDING",
  "message": "Đơn hàng đang được xử lý"
}
~~~

API này không nên giả vờ rằng order đã confirmed nếu saga chưa hoàn tất. Có thể cung cấp query:

~~~http
GET /orders/ord-1001
~~~

Các API nội bộ:

- Inventory: POST /reservations, POST /reservations/{id}/release, GET /reservations/{id}.
- Payment: POST /payment-authorizations, POST /payment-authorizations/{id}/void, GET /payment-intents/{id}.

Đây là ví dụ thiết kế hợp đồng, không phải bắt buộc dùng REST. Message command/event cũng phù hợp nếu use case bất đồng bộ.

## 12. Phân chia module và triển khai

Bounded Context là ranh giới mô hình và ngôn ngữ; nó không tự động bắt buộc phải là một microservice. Có thể triển khai nhiều context trong một modular monolith ở giai đoạn đầu, miễn là giữ được ownership và không truy cập trực tiếp dữ liệu nội bộ của nhau.

Một cấu trúc module minh họa:

~~~text
ordering/
  domain/
    Order
    OrderLine
    Money
    OrderPolicy
    OrderSubmitted
  application/
    PlaceOrderHandler
    OrderProcessManager
    InventoryPort
    PaymentPort
  infrastructure/
    OrderRepositoryAdapter
    OutboxPublisher
  api/
    OrderController

inventory/
  domain/
    StockItem
    Reservation
    Quantity
    InventoryReserved
  application/
    ReserveInventoryHandler
    ReleaseReservationHandler
  infrastructure/
    StockRepositoryAdapter

payment/
  domain/
    PaymentIntent
    PaymentTransaction
    Money
    PaymentAuthorized
  application/
    AuthorizePaymentHandler
    VoidAuthorizationHandler
  infrastructure/
    PaymentProviderAdapter
~~~

Các module có thể nằm trong cùng repository nhưng không chia sẻ Aggregate hoặc truy cập bảng của nhau. Contract giữa context nên được công bố rõ, version hóa và kiểm thử.

### 12.1. Khi nào tách deployment?

Chỉ nên tách thành service độc lập khi có lý do vận hành hoặc tổ chức đủ rõ:

- Nhu cầu scale khác nhau.
- Yêu cầu bảo mật/compliance khác nhau.
- Nhóm sở hữu và nhịp phát hành độc lập.
- Failure isolation có giá trị.
- Hợp đồng tích hợp đủ ổn định.

Nếu tách quá sớm, chi phí network, retry, observability, deployment và consistency có thể lớn hơn lợi ích. Giữ modular monolith với ranh giới rõ có thể là bước đầu hợp lý.

## 13. Chiến lược kiểm thử cho toàn bộ thiết kế

Kiểm thử cần đi từ quy tắc cục bộ đến quy trình xuyên context.

| Mức kiểm thử | Context/phạm vi | Ví dụ |
|---|---|---|
| Unit test | Ordering | Không đặt đơn rỗng; giá và total nhất quán |
| Unit test | Inventory | Không giữ vượt tồn kho; reservation ID idempotent |
| Unit test | Payment | Không authorize trùng; currency và amount hợp lệ |
| Application test | Ordering saga | Gửi ReserveInventory trước AuthorizePayment |
| Contract test | Inventory/Payment | Schema, version, error mapping |
| Integration test | Mỗi context | Repository, transaction, outbox/inbox |
| Saga test | Quy trình tổng | Payment declined thì release reservation |
| Concurrency test | Inventory/Payment | Hai lệnh đồng thời không vượt invariant |
| End-to-end | Toàn hành trình | Đặt đơn tới OrderConfirmed |

### 13.1. Scenario thành công

- Khách gửi đơn hợp lệ.
- Inventory giữ đủ số lượng.
- Payment authorize thành công.
- Ordering xác nhận đơn.
- Read model hiển thị trạng thái cuối.

### 13.2. Scenario thất bại

- Không đủ hàng.
- Payment bị từ chối.
- Payment timeout nhưng thực tế đã authorize.
- Reservation hết hạn trước khi payment hoàn tất.
- Event bị giao lặp.
- Event đến sai thứ tự.
- Consumer dừng sau khi xử lý dữ liệu nhưng trước khi checkpoint.
- Compensation release reservation thất bại.

Test cần xác nhận không chỉ kết quả cuối mà cả trạng thái trung gian và khả năng phục hồi.

## 14. Các quyết định cần làm rõ với chuyên gia

Trước khi biến đề xuất thành thiết kế production, cần trả lời:

1. Khi nào Order được xem là placed, confirmed và fulfilled?
2. Có cho phép đơn có nhiều warehouse hoặc giao từng phần không?
3. Reservation có thời hạn bao lâu và ai gia hạn?
4. Nếu reservation hết hạn trong lúc Payment đang authorize thì xử lý thế nào?
5. Payment chỉ authorize hay capture ngay? Capture ở thời điểm nào?
6. Khi Payment timeout, có API truy vấn trạng thái theo idempotency key không?
7. Nếu Payment đã authorize nhưng Order không thể confirm, có void tự động không?
8. Có cho phép backorder hoặc đặt trước khi hết hàng không?
9. Có giới hạn số lượng theo khách, SKU hoặc chiến dịch không?
10. Currency, thuế, phí vận chuyển và rounding được chốt ở đâu?
11. Ai được quyền hủy đơn sau khi đã xác nhận hoặc đã giao?
12. Reporting cần độ trễ tối đa bao lâu?

Các câu hỏi này ảnh hưởng trực tiếp tới Aggregate Boundary, trạng thái, event contract và Saga. Không nên đóng đinh câu trả lời bằng code trước khi nghiệp vụ xác nhận.

## 15. Những lựa chọn sai thường gặp

- **Một Order Aggregate chứa cả kho và thanh toán:** tạo ranh giới nhất quán giả, phụ thuộc nhiều owner.
- **Một database chung với mọi context ghi tự do:** không còn quyền sở hữu dữ liệu rõ ràng.
- **Tách microservice theo bảng:** ranh giới kỹ thuật không phản ánh invariant và ngôn ngữ.
- **Ordering tự quyết định tồn kho:** dùng dữ liệu trễ hoặc không có concurrency control để bảo vệ stock.
- **Ordering tự cập nhật Payment status:** làm sai quyền sở hữu giao dịch.
- **Gọi Payment rồi mới lưu Order mà không có idempotency:** timeout có thể tạo giao dịch trùng hoặc mất liên kết.
- **Coi authorize là capture:** nhầm giữ hạn mức với thu tiền thực tế.
- **Không có trạng thái PENDING:** UI báo thành công trước khi quy trình hoàn tất.
- **Không có Saga/process state:** khó phục hồi khi bước giữa thất bại.
- **Compensation bị coi là rollback:** reservation/payment đã commit không tự biến mất.
- **Không có outbox/inbox:** event có thể mất hoặc gây tác động lặp.
- **Read model dùng để quyết định giữ hàng:** projection có thể trễ.
- **Event contract phơi bày ORM model:** consumer phụ thuộc implementation nội bộ.
- **Không xác định upstream/downstream:** không biết ai chịu trách nhiệm version và tương thích contract.

## 16. Lộ trình triển khai đề xuất

Một lộ trình an toàn có thể gồm:

1. **Discovery:** Event Storming luồng đặt hàng, xác định thuật ngữ, actor, command, event và ngoại lệ.
2. **Context mapping:** chốt trách nhiệm Ordering, Inventory, Payment và các quan hệ supplier/customer.
3. **Domain modeling:** thiết kế Aggregate, Value Object, invariant và Domain Event cho từng context.
4. **Contract design:** định nghĩa command/event, ID, version, idempotency, error và timeout.
5. **Local implementation:** triển khai từng context và Repository trong modular monolith hoặc service phù hợp.
6. **Process orchestration:** xây saga/process manager và compensation.
7. **Consistency plumbing:** transactional outbox, inbox, retry, dead-letter và reconciliation.
8. **Read model:** xây Order Summary projection và theo dõi checkpoint.
9. **Testing:** unit, contract, integration, concurrency, saga và end-to-end.
10. **Operational readiness:** metric, trace, alert, runbook và diễn tập lỗi.
11. **Incremental rollout:** canary theo cohort, quan sát và mở rộng khi đạt tiêu chí.

~~~mermaid
flowchart TD
    A[Event Storming và Ubiquitous Language] --> B[Bounded Context và Context Map]
    B --> C[Aggregate / Value Object / Invariant]
    C --> D[Command và Event Contracts]
    D --> E[Ordering / Inventory / Payment]
    E --> F[Saga + Outbox / Inbox]
    F --> G[Read Model + Observability]
    G --> H[Contract / Integration / E2E tests]
    H --> I[Canary và vận hành]
~~~

## 17. Checklist thiết kế

- [ ] Ordering, Inventory và Payment có trách nhiệm và ngôn ngữ riêng.
- [ ] Mỗi invariant có một context sở hữu rõ ràng.
- [ ] Context Map phân biệt upstream/downstream và chiều command/event.
- [ ] Quan hệ Customer–Supplier và Published Language có hợp đồng cụ thể.
- [ ] Aggregate Boundary dựa trên invariant, không dựa vào object graph.
- [ ] Repository chỉ truy cập Aggregate thuộc context của nó.
- [ ] Value Object biểu diễn tiền, số lượng, ID và thời gian có ý nghĩa.
- [ ] Domain Event mô tả sự thật đã xảy ra.
- [ ] Command và event được phân biệt rõ.
- [ ] Saga có trạng thái trung gian, timeout và compensation.
- [ ] Mỗi context dùng local transaction để bảo vệ invariant của nó.
- [ ] Outbox/inbox hoặc cơ chế tương đương xử lý message an toàn.
- [ ] Idempotency key ổn định cho reservation và payment request.
- [ ] Read model không được dùng thay nguồn có thẩm quyền.
- [ ] Contract có version và xử lý unknown/error.
- [ ] Có test cho success, failure, timeout, duplicate, out-of-order và concurrency.
- [ ] Có observability, reconciliation và runbook vận hành.
- [ ] Các chính sách chưa rõ được xác nhận với chuyên gia trước khi production.

## 18. Bài tập thực hành

Hãy dùng mô hình đề xuất để hoàn thiện một thiết kế cụ thể:

1. Vẽ Context Map cho Ordering, Inventory, Payment và Reporting.
2. Ghi rõ upstream/downstream, command direction và event direction.
3. Viết ba invariant cho mỗi context.
4. Chọn một Aggregate Root và ít nhất ba Value Object cho mỗi context.
5. Định nghĩa command/event contract cho luồng đặt hàng.
6. Vẽ Saga thành công và hai nhánh thất bại.
7. Mô tả timeout Payment có kết quả chưa xác định.
8. Đề xuất outbox/inbox và idempotency key.
9. Xác định read model cho trang chi tiết đơn.
10. Viết test case cho biên số lượng, currency, reservation expiry và duplicate command.

## 19. Câu hỏi tự kiểm tra

1. Vì sao Ordering, Inventory và Payment nên có mô hình và quyền sở hữu riêng?
2. Context Map khác sơ đồ microservice ở điểm nào?
3. Upstream/downstream khác chiều gửi command như thế nào?
4. Vì sao Ordering chỉ lưu ReservationId/PaymentId thay vì sở hữu Aggregate của context khác?
5. Những invariant nào cần được bảo vệ trong Inventory và Payment?
6. Vì sao authorize không đồng nghĩa capture?
7. Saga điều phối luồng thành công và compensation khi Payment bị từ chối ra sao?
8. Timeout tạo ra trạng thái chưa xác định như thế nào và idempotency giúp gì?
9. Vì sao mỗi context cần local transaction riêng?
10. Outbox/inbox giải quyết rủi ro nào khi publish/consume event?
11. Khi nào nên dùng modular monolith trước khi tách microservice?
12. Read model tổng hợp từ ba context có thể trễ; điều đó ảnh hưởng gì tới quyết định nghiệp vụ?
13. Những chính sách nào cần chuyên gia xác nhận trước khi triển khai?

## Kết luận

Đề xuất cho bài toán là ba Bounded Context có quyền sở hữu riêng: Ordering quản lý đơn và quyết định xác nhận; Inventory bảo vệ tồn kho và reservation; Payment quản lý authorization, capture, void và refund. Context Map thể hiện Inventory và Payment cung cấp hợp đồng cho Ordering; Ordering gửi command và nhận kết quả qua event. Reporting chỉ tổng hợp dữ liệu để truy vấn.

Aggregate và Repository giữ invariant trong từng context. Saga phối hợp local transaction qua command/event, còn outbox, inbox, idempotency, timeout và compensation giúp quy trình phục hồi khi có lỗi. Có thể bắt đầu bằng modular monolith với ranh giới module rõ trước khi tách deployment. Thiết kế chỉ nên được chốt sau khi chuyên gia xác nhận các chính sách còn mở như reservation expiry, payment capture, backorder và giao hàng từng phần.

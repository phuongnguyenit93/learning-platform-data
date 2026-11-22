# Khám phá một miền bán hàng từ tình huống và quy tắc nghiệp vụ

Domain-Driven Design (DDD) bắt đầu bằng việc hiểu sâu vấn đề kinh doanh rồi
chuyển hiểu biết đó thành mô hình và ngôn ngữ chung giữa chuyên gia nghiệp vụ
với đội phát triển. Bài thực hành này đi xuyên qua một miền bán hàng giả định:
từ câu chuyện khách đặt hàng, khám phá sự kiện và quy tắc, xác định subdomain
và bounded context, đến thiết kế entity, value object, aggregate, repository,
domain event và các luồng tích hợp.

Mục tiêu là luyện cách suy nghĩ có căn cứ. Mỗi thành phần trong mô hình phải
giải thích được nó đại diện cho khái niệm nào, bảo vệ quy tắc nào và thuộc
trách nhiệm của context nào. Các con số, chính sách và ranh giới trong ví dụ
là giả định để thực hành; một doanh nghiệp thật cần xác nhận chúng với domain
expert trước khi dùng làm business rule.

## 1. Bối cảnh kinh doanh

Giả sử một nhà bán lẻ trực tuyến bán đồ gia dụng qua website và ứng dụng.
Khách hàng chọn sản phẩm, áp dụng ưu đãi, đặt hàng, thanh toán và nhận hàng.
Đội vận hành có thể xử lý một số ngoại lệ như hết hàng, thanh toán thất bại,
khách yêu cầu hủy hoặc địa chỉ giao hàng không hợp lệ.

Doanh nghiệp muốn cải thiện ba kết quả:

1. Khách có thể đặt hàng với giá và điều kiện rõ ràng.
2. Hệ thống không xác nhận đơn khi chưa giữ được hàng hoặc chưa có thanh toán
   được chấp thuận.
3. Nhân viên có thể giải thích vì sao đơn được xác nhận, từ chối hoặc hủy.

Phạm vi bài tập tập trung vào lát cắt: khách gửi yêu cầu đặt hàng, hệ thống
ghi nhận đơn, giữ hàng, xin phép thanh toán và xác nhận đơn khi các điều kiện
đều đạt. Hoàn tiền, đổi trả và tối ưu vận chuyển được nhận diện như các luồng
liên quan nhưng không triển khai sâu trong lát cắt đầu tiên.

### 1.1. Giả định ban đầu cần được xác nhận

| Giả định | Vì sao cần xác nhận |
|---|---|
| Giá được giữ trong một khoảng thời gian khi khách xem báo giá | Ảnh hưởng thời điểm chốt giá |
| Một đơn chỉ dùng một loại tiền | Ảnh hưởng Money và tổng tiền |
| Mỗi dòng đơn có số lượng nguyên dương | Ảnh hưởng Quantity và validation |
| Đơn chỉ được xác nhận khi hàng đã được giữ và thanh toán được authorize | Ảnh hưởng state transition |
| Authorize chưa đồng nghĩa với capture | Ảnh hưởng quy trình thanh toán |
| Hết hàng hoặc thanh toán thất bại khiến quy trình xác nhận dừng | Ảnh hưởng compensation |

Đây chưa phải sự thật của doanh nghiệp. Hãy đánh dấu là giả định cho tới khi
domain expert xác nhận, đưa ra ngoại lệ hoặc sửa lại.

## 2. Bắt đầu bằng tình huống, không bắt đầu bằng class

Một câu chuyện ban đầu có thể được kể như sau:

> Lan chọn một chiếc máy lọc không khí và hai bộ lọc thay thế. Website hiển
> thị giá, phí giao hàng và ưu đãi hiện có. Lan xác nhận địa chỉ, gửi yêu cầu
> đặt hàng và chọn thanh toán bằng thẻ. Hệ thống ghi nhận đơn, yêu cầu kho
> giữ hàng và yêu cầu cổng thanh toán authorize số tiền cần thu. Khi cả hai
> bước thành công, đơn được xác nhận và chuyển sang quy trình giao hàng.

Đừng vội chuyển câu chuyện thành một Order class. Trước hết hãy hỏi những
người tham gia nghiệp vụ:

- Giá hiển thị được giữ trong bao lâu?
- Khi giá thay đổi giữa lúc xem và lúc đặt, giá nào được áp dụng?
- Khuyến mãi có thể kết hợp với nhau không?
- Kho giữ hàng ở thời điểm khách bấm đặt hay sau khi thanh toán?
- Nếu kho giữ được hàng nhưng thanh toán thất bại thì chuyện gì xảy ra?
- Nếu thanh toán authorize thành công nhưng phản hồi đến chậm thì sao?
- Khi nào đơn được xem là đã xác nhận?
- Ai có quyền hủy đơn và hủy được tới giai đoạn nào?
- Khách cần thấy lý do gì khi đơn không thể tiếp tục?

Những câu hỏi này mở ra quy tắc, ngoại lệ và ranh giới trách nhiệm. Chúng là
đầu vào để khám phá mô hình.

## 3. Thu thập nhiều kịch bản

Một happy path không đủ để hiểu domain. Hãy thu thập cả tình huống bình
thường, thất bại, biên và ngoại lệ vận hành.

| Kịch bản | Tình huống | Điều cần khám phá |
|---|---|---|
| S1 — Đặt hàng thành công | Hàng được giữ và thanh toán được authorize | Điều kiện xác nhận đơn |
| S2 — Hết hàng | Một dòng không đủ số lượng | Có giữ một phần không? |
| S3 — Thanh toán thất bại | Ngân hàng từ chối authorize | Giải phóng hàng thế nào? |
| S4 — Phản hồi chậm | Payment đã xử lý nhưng callback đến trễ | Có thể nhận event lặp không? |
| S5 — Giá hết hạn | Khách gửi đơn với quote đã hết hiệu lực | Có yêu cầu khách xác nhận giá mới? |
| S6 — Yêu cầu đặt lặp | Client gửi lại cùng yêu cầu do timeout | Có tạo hai đơn không? |
| S7 — Hủy sau xác nhận | Khách yêu cầu hủy trước khi giao cho hãng vận chuyển | Hủy giữ hàng và xử lý authorization ra sao? |
| S8 — Hủy sau khi giao | Kiện hàng đã được bàn giao cho hãng vận chuyển | Đây là hủy đơn hay yêu cầu trả hàng? |

Với mỗi kịch bản, ghi rõ actor, điều kiện ban đầu, hành động, kết quả mong
đợi, ngoại lệ và bằng chứng. Nếu hai bộ phận đưa ra câu trả lời khác nhau,
giữ bất đồng đó thành câu hỏi mở thay vì tự chọn một cách hiểu.

## 4. Xác định người cần tham gia discovery

Một miền bán hàng thường có nhiều góc nhìn:

| Vai trò | Hiểu biết cần khai thác |
|---|---|
| Sales/Product Owner | Chính sách đặt hàng và trải nghiệm khách |
| Pricing/Merchandising | Giá, khuyến mãi, thời hạn báo giá |
| Warehouse/Inventory | Tồn kho khả dụng, giữ hàng, giải phóng |
| Finance/Payment Operations | Authorize, capture, void, refund, đối soát |
| Fulfillment | Đóng gói, bàn giao, giao hàng |
| Customer Support | Ngoại lệ, tra cứu và giải thích cho khách |
| Developer/Architect | Chuyển quy tắc thành model, contract và test |

Không nhất thiết mời tất cả vào mọi buổi. Hãy mời người hiểu rõ quyết định
đang được khám phá và người chịu trách nhiệm xác nhận chính sách đó.

## 5. Event Storming cho luồng đặt hàng

Hãy viết các sự kiện đã xảy ra bằng dạng quá khứ. Sau đó tìm command, actor,
policy và hệ thống tham gia.

| Thứ tự | Command/Trigger | Domain Event có thể xuất hiện | Bên quan tâm |
|---:|---|---|---|
| 1 | SubmitOrder | OrderPlaced | Sales Order |
| 2 | ReserveStock | StockReserved hoặc StockReservationRejected | Inventory |
| 3 | AuthorizePayment | PaymentAuthorized hoặc PaymentAuthorizationFailed | Payment |
| 4 | ConfirmOrder | OrderConfirmed | Sales Order |
| 5 | CreateShipment | ShipmentRequested | Fulfillment |
| 6 | DispatchShipment | ShipmentDispatched | Fulfillment, Sales, Support |

Bảng này là một giả thuyết về chuỗi sự kiện. Trong workshop, thứ tự có thể
khác tùy chính sách thực tế. Ví dụ doanh nghiệp có thể authorize thanh toán
trước rồi mới reserve stock, hoặc thực hiện hai bước song song.

### 5.1. Sơ đồ dòng sự kiện

~~~mermaid
flowchart TD
    A[Khách gửi yêu cầu đặt hàng] --> B[OrderPlaced]
    B --> C[Process Manager gửi ReserveStock]
    B --> D[Process Manager gửi AuthorizePayment]
    C --> E[Lưu kết quả giữ hàng]
    D --> E
    E --> F{Có nhánh thất bại?}
    F -->|Không| G{Cả hai đã thành công?}
    G -->|Chưa| E
    G -->|Rồi| H[ConfirmOrder]
    H --> I[OrderConfirmed]
    F -->|Có| J{Kết quả nhánh còn lại đã rõ?}
    J -->|Chưa| K[Chờ kết quả hoặc timeout]
    K --> J
    J -->|Rồi| L[Compensate nhánh đã thành công]
    L --> M[OrderRejected]
~~~

Sơ đồ nhấn mạnh rằng hai kết quả có thể đến không đồng thời. Đội cần xác định
cách xử lý khi một kết quả đến trước, đến sau, bị lặp hoặc không bao giờ đến.

### 5.2. Tìm hotspot

Các điểm cần đào sâu có thể là:

- “Tồn kho khả dụng” có bao gồm hàng đã giữ cho đơn khác không?
- Một reservation hết hạn thì đơn đang chờ thanh toán ra sao?
- Payment timeout có nghĩa là thất bại hay chưa biết kết quả?
- Một callback có thể đến nhiều lần không?
- Có thể xác nhận một phần đơn không?
- Giá quote được khóa tại thời điểm nào?

Hotspot là nơi nhóm cần thêm ví dụ hoặc quyết định, không phải nơi cần thêm
class ngay lập tức.

## 6. Chuyển câu chuyện thành quy tắc nghiệp vụ

Sau discovery, tách các quy tắc thành nhóm để biết chúng thuộc đâu.

### 6.1. Quy tắc về đơn hàng

| Mã | Quy tắc giả định | Loại |
|---|---|---|
| ORD-01 | Đơn phải có ít nhất một dòng hàng | Invariant của Order |
| ORD-02 | Số lượng mỗi dòng phải lớn hơn 0 | Invariant của OrderLine/Quantity |
| ORD-03 | Các dòng trong một đơn dùng cùng currency | Invariant của Order |
| ORD-04 | Giá dòng hàng là snapshot từ quote đã chấp nhận | Quy tắc tạo Order |
| ORD-05 | Không sửa dòng hàng sau khi đơn đã được đặt | State transition |
| ORD-06 | Chỉ xác nhận đơn đang chờ xác nhận | Invariant của Order |
| ORD-07 | Xác nhận cần bằng chứng giữ hàng và authorize thanh toán | Invariant của Order |

### 6.2. Quy tắc về phối hợp

| Mã | Quy tắc giả định | Nơi có thể thực thi |
|---|---|---|
| FLOW-01 | Chỉ tiếp tục khi cả Inventory và Payment thành công | Process Manager |
| FLOW-02 | Nếu giữ hàng thất bại, không xác nhận đơn | Process Manager |
| FLOW-03 | Nếu payment thất bại sau khi giữ hàng, phải yêu cầu giải phóng hàng | Compensation flow |
| FLOW-04 | Nếu giữ hàng thất bại sau khi payment authorize, phải void authorization | Compensation flow |
| FLOW-05 | Một kết quả nhận lặp không được tạo side effect lặp | Consumer idempotency |
| FLOW-06 | Timeout chưa chắc là thất bại nghiệp vụ | Integration policy |

### 6.3. Quy tắc về quote

- Quote có thời hạn hiệu lực.
- Giá và ưu đãi trong quote được xác định tại thời điểm phát hành.
- Khi khách chấp nhận quote còn hiệu lực, Order lưu snapshot thương mại.
- Nếu quote hết hạn trước khi đặt, khách cần nhận quote mới theo chính sách.

Không nên đặt mọi quy tắc vào một Order Aggregate. Quy tắc nội tại của đơn
thuộc Order; chính sách tính giá thuộc Pricing; tồn kho thuộc Inventory;
phối hợp nhiều context thuộc process manager hoặc application workflow.

## 7. Phân biệt invariant, policy và quy trình

Các loại quy tắc có vị trí thực thi khác nhau:

| Loại | Ví dụ | Nơi phù hợp |
|---|---|---|
| Invariant | Order không có dòng hàng rỗng | Aggregate |
| Value constraint | Quantity phải dương | Value Object |
| Domain policy | Mức giảm tối đa theo chương trình | Pricing Model/Policy |
| Process policy | Chờ cả stock reservation và payment authorization | Process Manager |
| Authorization | Nhân viên nào được duyệt ngoại lệ | Application/Security Policy |
| Integration policy | Retry hoặc chuyển message vào DLQ | Adapter/Infrastructure |

Đây là bước quan trọng để tránh một service khổng lồ chứa tất cả điều kiện
hoặc một Aggregate phải biết trạng thái nội bộ của mọi context.

## 8. Xây Ubiquitous Language

Một glossary nhỏ cho lát cắt này có thể là:

| Thuật ngữ | Ý nghĩa trong ví dụ |
|---|---|
| Cart | Tập sản phẩm khách đang cân nhắc, chưa phải đơn |
| Quote | Báo giá có thời hạn và điều kiện |
| Order | Cam kết thương mại được ghi nhận sau khi khách đặt |
| Order Line | Một loại sản phẩm và số lượng trong đơn |
| Reservation | Lượng tồn kho được giữ cho một mục đích trong thời hạn |
| Available Stock | Tồn kho có thể được cấp sau khi trừ lượng đã giữ |
| Authorization | Ngân hàng/nhà cung cấp thanh toán chấp thuận khả năng thu tiền |
| Capture | Thực sự yêu cầu thu khoản tiền đã authorize |
| Void | Hủy một authorization chưa capture |
| Refund | Hoàn lại khoản tiền đã capture |
| Fulfillment | Quy trình chuẩn bị và bàn giao hàng |
| Dispatch | Kiện hàng đã được bàn giao cho đơn vị vận chuyển |

Các thuật ngữ này có thể khác giữa doanh nghiệp. Đặc biệt, không đồng nhất
authorize với capture, void với refund, hoặc OrderConfirmed với
ShipmentDispatched.

### 8.1. Ghi cả từ không nên dùng

Ví dụ, nếu nhóm thường gọi cả authorization và capture là “payment success”,
hãy ghi rõ vì sao cách gọi này gây mơ hồ. Một glossary hữu ích không chỉ định
nghĩa từ được chọn mà còn chỉ ra cách gọi dễ dẫn đến hiểu nhầm.

## 9. Phân loại Subdomain

Subdomain là cách chia domain theo năng lực nghiệp vụ. Với nhà bán lẻ giả
định, một phân loại ban đầu có thể là:

| Subdomain | Vai trò | Phân loại giả thuyết |
|---|---|---|
| Order Management | Ghi nhận và quản lý cam kết mua bán | Core |
| Pricing & Promotion | Tính giá và áp dụng ưu đãi | Core hoặc Supporting |
| Inventory Management | Quản lý tồn kho và giữ hàng | Supporting hoặc Core |
| Payment Processing | Tích hợp và quản lý thanh toán | Generic hoặc Supporting |
| Fulfillment | Chuẩn bị và bàn giao hàng | Supporting |
| Customer Identity | Xác thực và quản lý tài khoản | Generic |

Không thể kết luận loại subdomain chỉ từ tên. Nếu lợi thế cạnh tranh của
doanh nghiệp là tối ưu giá, Pricing có thể là Core. Nếu lợi thế là giao hàng
nhanh với tồn kho chính xác, Inventory/Fulfillment có thể là Core.

Phân loại cần được xác nhận bằng chiến lược, khả năng khác biệt và cách doanh
nghiệp tạo giá trị.

## 10. Đề xuất Bounded Context

Subdomain và Bounded Context không phải hai khái niệm thay thế nhau. Một
subdomain có thể được triển khai bằng một hoặc nhiều bounded context; một
bounded context có thể hỗ trợ một phần năng lực cụ thể.

Với lát cắt bán hàng, có thể khảo sát các context:

| Bounded Context | Trách nhiệm | Model chính |
|---|---|---|
| Catalog | Mô tả sản phẩm được bán | Product, ProductReference |
| Pricing | Tính quote và ưu đãi | Quote, Price, Promotion |
| Sales Order | Ghi nhận cam kết mua bán | Order, OrderLine |
| Inventory | Tồn kho và reservation | StockItem, Reservation |
| Payment | Authorization, capture, void, refund | Payment, Authorization |
| Fulfillment | Đóng gói và giao hàng | Shipment, Dispatch |

Ranh giới này là phương án ban đầu để kiểm chứng. Nếu một tổ chức nhỏ có
thể giữ nhiều model trong một ứng dụng modular monolith, không cần tách
microservice chỉ để có bounded context.

## 11. Vẽ Context Map

Context Map thể hiện quan hệ và luồng contract giữa các model:

~~~mermaid
flowchart LR
    C[Catalog] -->|Product facts| P[Pricing]
    P -->|Quote| S[Sales Order]
    subgraph Sales["Sales Order Context"]
        S[Order Aggregate]
        PM[Order Process Manager]
        S -->|OrderPlaced| PM
        PM -->|ConfirmOrder| S
    end
    PM -->|ReserveStock| I[Inventory]
    PM -->|AuthorizePayment| Pay[Payment]
    I -->|StockReserved / Rejected| PM
    Pay -->|PaymentAuthorized / Failed| PM
    S -->|OrderConfirmed| F[Fulfillment]
~~~

Order Aggregate và Order Process Manager cùng nằm trong Sales Order Context.
Aggregate bảo vệ invariant của đơn; Process Manager điều phối workflow dài
hạn. Inventory và Payment sở hữu quy tắc và trạng thái riêng. Fulfillment
chỉ nhận yêu cầu khi đơn đã được xác nhận theo điều kiện đã thống nhất.

### 11.1. Quan hệ upstream/downstream

Trong ví dụ:

- Catalog là upstream cung cấp thông tin sản phẩm cho Pricing.
- Pricing cung cấp quote cho Sales Order.
- Sales Order gửi yêu cầu xuống Inventory và Payment.
- Inventory và Payment trả kết quả qua event.
- Sales Order thông báo OrderConfirmed cho Fulfillment.

Các quan hệ này cần xác định contract, ownership và cách xử lý thay đổi.
Không nên chia sẻ trực tiếp Entity hoặc bảng dữ liệu của context upstream.

### 11.2. Dùng Anti-Corruption Layer

Sales Order có thể nhận event từ Inventory và Payment qua adapter. Adapter
chuyển external contract thành kiểu nội bộ:

- External StockReservedV1 thành InventoryReservationConfirmed.
- External PaymentAuthorizedV1 thành PaymentAuthorizationConfirmed.

Tên nội bộ cần phản ánh ngôn ngữ Sales Order. ACL giúp Sales Order không bị
buộc phải dùng nguyên mô hình hoặc enum của context khác.

## 12. Chọn một Implementation Slice

Để tránh xây toàn bộ hệ thống cùng lúc, chọn use case:

> Khách gửi yêu cầu đặt một đơn có quote hợp lệ. Hệ thống chỉ xác nhận đơn
> khi Inventory đã giữ đủ hàng và Payment đã authorize đúng số tiền.

Slice này đủ để kiểm chứng:

- Quote và price snapshot.
- Order Aggregate.
- Reservation và authorization contracts.
- Process Manager.
- Domain Event và Integration Event.
- Eventual consistency và compensation.
- Repository và test.

Các chức năng như tìm kiếm sản phẩm, quản lý tài khoản, dashboard và tối ưu
giao hàng có thể được tích hợp sau bằng contract riêng.

## 13. Mô hình trạng thái của Order

Một state machine ban đầu:

~~~mermaid
stateDiagram-v2
    [*] --> PendingConfirmation
    PendingConfirmation --> Confirmed: stock reserved + payment authorized
    PendingConfirmation --> Rejected: prerequisite failed
    Confirmed --> CancellationPending: cancel accepted
    CancellationPending --> Cancelled: compensation completed
    Rejected --> [*]
    Cancelled --> [*]
~~~

Trong lát cắt đầu tiên, tập trung vào PendingConfirmation, Confirmed và
Rejected. CancellationPending/Cancelled được giữ để chỉ ra hướng mở rộng;
quy tắc hủy thực tế cần được domain expert xác nhận, nhất là khi shipment
đã được dispatch.

Một đơn không nên có các cờ boolean rời rạc như isConfirmed, isRejected,
isCancelled nếu chúng cho phép các tổ hợp trạng thái mâu thuẫn. Trạng thái
phải phản ánh một vòng đời có ý nghĩa.

## 14. Xác định Aggregate boundary

Aggregate là consistency boundary bảo vệ invariant. Trong lát cắt này:

### Sales Order Aggregate

Sở hữu:

- OrderId.
- CustomerId hoặc customer reference.
- Quote reference và snapshot giá được chấp nhận.
- Các OrderLine.
- Currency và tổng tiền.
- OrderStatus.
- Bằng chứng cần thiết để xác nhận đơn.

Không sở hữu:

- Toàn bộ Product Catalog.
- Số lượng tồn kho hiện tại.
- Payment transaction đầy đủ.
- Shipment và tracking history.

Order chỉ tham chiếu các Aggregate khác bằng ID hoặc dữ liệu snapshot cần
thiết. Mỗi context bảo vệ invariant của chính nó.

### 14.1. Vì sao không tạo một SalesTransaction Aggregate khổng lồ?

Nếu một Aggregate chứa Order, StockItem, Payment và Shipment, mọi cập nhật
đều có xu hướng phải đi qua một consistency boundary. Điều này không phù
hợp khi các context có database, vòng đời và khả năng thay đổi độc lập.

Quy trình nhiều context nên được phối hợp bằng event/command và eventual
consistency. Không ép một distributed workflow thành một transaction ACID
giả định.

## 15. Tạo Value Object cho dữ liệu có ý nghĩa

Một số giá trị cần ngữ nghĩa riêng:

- OrderId: định danh đơn.
- CustomerId: định danh khách.
- ProductReference: tham chiếu sản phẩm.
- Money: số tiền luôn đi cùng currency.
- Quantity: số lượng hợp lệ.
- QuoteId: tham chiếu báo giá.

Ví dụ Money:

~~~java
public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount);
        Objects.requireNonNull(currency);
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("Amount must not be negative");
        }
    }

    public Money add(Money other) {
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException("Currency mismatch");
        }
        return new Money(amount.add(other.amount), currency);
    }

    public Money multiply(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        return new Money(amount.multiply(BigDecimal.valueOf(quantity)), currency);
    }
}
~~~

Trong hệ thống thật, quy tắc scale, rounding, thuế và cách biểu diễn tiền
cần theo currency và chính sách kế toán. Không tự ý dùng double cho tiền.

### 15.1. Quantity

~~~java
public record Quantity(int value) {
    public Quantity {
        if (value <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
    }
}
~~~

Quantity làm cho quy tắc số lượng dương được kiểm tra tại nơi tạo giá trị.
Nếu ngành hàng cho phép cân theo trọng lượng hoặc số lượng thập phân, kiểu
và quy tắc phải thay đổi theo nghiệp vụ thực tế.

## 16. Thiết kế OrderLine và Order Aggregate

OrderLine là thành phần thuộc vòng đời của Order trong ví dụ. Giá đơn vị
được lưu thành snapshot để đơn không đổi giá khi Pricing cập nhật về sau.

~~~java
public record OrderLine(
        ProductReference product,
        String productNameSnapshot,
        Quantity quantity,
        Money unitPrice
) {
    public OrderLine {
        Objects.requireNonNull(product);
        Objects.requireNonNull(productNameSnapshot);
        Objects.requireNonNull(quantity);
        Objects.requireNonNull(unitPrice);
        if (productNameSnapshot.isBlank()) {
            throw new IllegalArgumentException("Product name snapshot is required");
        }
    }

    public Money subtotal() {
        return unitPrice.multiply(quantity.value());
    }
}
~~~

Aggregate:

~~~java
public final class Order {
    private final OrderId id;
    private final CustomerId customerId;
    private final QuoteId quoteId;
    private final List<OrderLine> lines;
    private final Money total;
    private OrderStatus status;
    private ConfirmationEvidence confirmationEvidence;
    private OrderRejectionReason rejectionReason;

    private Order(
            OrderId id,
            CustomerId customerId,
            QuoteId quoteId,
            List<OrderLine> lines,
            Money total
    ) {
        this.id = Objects.requireNonNull(id);
        this.customerId = Objects.requireNonNull(customerId);
        this.quoteId = Objects.requireNonNull(quoteId);
        this.lines = List.copyOf(lines);
        this.total = Objects.requireNonNull(total);
        this.status = OrderStatus.PENDING_CONFIRMATION;
    }

    public static Order place(
            OrderId id,
            CustomerId customerId,
            QuoteId quoteId,
            List<OrderLine> lines
    ) {
        if (lines == null || lines.isEmpty()) {
            throw new IllegalArgumentException("Order must contain a line");
        }

        Currency currency = lines.get(0).unitPrice().currency();
        Money total = new Money(BigDecimal.ZERO, currency);

        for (OrderLine line : lines) {
            if (!currency.equals(line.unitPrice().currency())) {
                throw new IllegalArgumentException("Mixed currencies are not allowed");
            }
            total = total.add(line.subtotal());
        }

        return new Order(id, customerId, quoteId, lines, total);
    }

    public void confirm(ConfirmationEvidence evidence) {
        requireStatus(OrderStatus.PENDING_CONFIRMATION);
        this.confirmationEvidence = Objects.requireNonNull(evidence);
        this.status = OrderStatus.CONFIRMED;
    }

    public void reject(OrderRejectionReason reason) {
        requireStatus(OrderStatus.PENDING_CONFIRMATION);
        this.rejectionReason = Objects.requireNonNull(reason);
        this.status = OrderStatus.REJECTED;
    }

    private void requireStatus(OrderStatus expected) {
        if (status != expected) {
            throw new InvalidOrderState(status, expected);
        }
    }

    public OrderId id() {
        return id;
    }

    public Money total() {
        return total;
    }

    public OrderStatus status() {
        return status;
    }
}
~~~

Đây là code minh họa rút gọn. Trong triển khai thật, factory cần kiểm tra
quote đã được xác thực và còn hiệu lực ở Application/Domain Policy phù hợp;
Aggregate ghi nhận OrderPlaced khi tạo và OrderConfirmed/OrderRejected sau
chuyển trạng thái để Unit of Work đưa event vào Outbox cùng transaction.
Danh sách dòng hàng và các giá trị phải được bảo vệ bất biến. Không nên để
client tự gửi total được tin cậy mà không tính lại từ snapshot đã được xác minh.

Ví dụ cộng total chỉ tính subtotal của các dòng. Nếu quote có chiết khấu,
thuế hoặc phí giao hàng, cần lưu các thành phần snapshot đó và áp dụng quy
tắc Pricing đã xác nhận thay vì coi tổng dòng hàng là tổng cuối cùng.

### 16.1. Bằng chứng xác nhận

~~~java
public record ConfirmationEvidence(
        ReservationId reservationId,
        PaymentAuthorizationId authorizationId
) {
    public ConfirmationEvidence {
        Objects.requireNonNull(reservationId);
        Objects.requireNonNull(authorizationId);
    }
}
~~~

Order chỉ được confirm khi application workflow đã nhận được cả hai bằng
chứng thành công. Aggregate không gọi Inventory hoặc Payment trực tiếp.

## 17. Quy tắc xác nhận thuộc Aggregate hay Process Manager?

Có hai cấp quy tắc:

- Order Aggregate bảo vệ trạng thái nội tại: chỉ đơn đang chờ mới được
  confirm; bằng chứng phải có đủ reservation và authorization.
- Process Manager theo dõi tiến trình liên context: đã nhận kết quả nào,
  còn chờ kết quả nào, khi nào cần confirm hoặc compensation.

Không nên đưa toàn bộ trạng thái của Inventory và Payment vào Order chỉ để
đơn có thể tự điều phối. Process Manager là nơi phù hợp cho trạng thái của
workflow dài hạn.

## 18. Thiết kế Process Manager

Process Manager theo dõi hai nhánh bất đồng bộ:

~~~mermaid
stateDiagram-v2
    [*] --> WaitingForResults
    WaitingForResults --> ReadyToConfirm: both prerequisites succeeded
    WaitingForResults --> FailureObserved: one prerequisite failed
    FailureObserved --> Compensating: other result known or timeout policy applied
    ReadyToConfirm --> Completed: OrderConfirmed
    Compensating --> Failed: compensation completed
~~~

Nó cần lưu:

- OrderId và correlationId.
- Kết quả reservation.
- Kết quả payment authorization.
- Các eventId đã xử lý.
- Trạng thái workflow.
- Thời điểm timeout và retry nếu cần.

Khi cả hai thành công, Process Manager gửi ConfirmOrder. Khi một nhánh thất
bại, nó không được giả định nhánh còn lại đã dừng. Nó ghi nhận thất bại, chờ
kết quả còn lại hoặc áp dụng timeout policy, rồi yêu cầu giải phóng reservation
hoặc void authorization nếu thao tác đó đã thành công.

### 18.1. Xử lý event đến không đúng thứ tự

PaymentAuthorized có thể đến trước StockReserved. Process Manager lưu kết
quả payment và chờ inventory. Khi StockReserved đến, nó kiểm tra cả hai
điều kiện rồi mới gửi ConfirmOrder.

Nếu cùng event được giao lại, eventId giúp phát hiện duplicate. Nếu hai
event khác nhau mâu thuẫn về cùng một reservation hoặc authorization, workflow
phải áp dụng policy xử lý xung đột thay vì ghi đè im lặng.

## 19. Domain Event và Integration Event

Domain Event mô tả sự kiện có ý nghĩa trong Sales Order Context. Integration
Event là contract được công bố cho context khác.

~~~java
public record OrderPlaced(
        OrderId orderId,
        CustomerId customerId,
        Money total,
        List<OrderLine> lines,
        Instant occurredAt
) {
    public OrderPlaced {
        lines = List.copyOf(lines);
    }
}
~~~

Integration Event có thể dùng kiểu dữ liệu độc lập với Java domain:

~~~java
public record OrderPlacedV1(
        String orderId,
        String customerReference,
        String totalAmount,
        String currency,
        Instant occurredAt,
        List<OrderLineV1> lines
) {}

public record OrderLineV1(
        String productReference,
        int quantity
) {}
~~~

Payload cần có các dòng hàng để Inventory biết sản phẩm và số lượng phải giữ.
Envelope có thể mang eventId, eventType, schemaVersion và correlationId; payload
là OrderPlacedV1. Mapper chuyển từng OrderLine sang OrderLineV1. Không serialize
trực tiếp Aggregate hoặc expose persistence entity ra message broker.

### 19.1. Event phải diễn đạt điều đã xảy ra

Tên event nên mô tả sự kiện đã xảy ra như OrderPlaced, OrderConfirmed,
StockReserved, PaymentAuthorized. Command như PlaceOrder hoặc ReserveStock
mô tả yêu cầu thực hiện hành động.

Không nên đặt event là ReserveStockRequested nếu ý nghĩa thực tế chỉ là một
command đang được gửi. Có thể có event OrderPlacementRequested nếu đó thật
sự là một fact đã được ghi nhận, nhưng phải định nghĩa rõ.

## 20. Repository theo Aggregate Root

Repository domain cung cấp cách truy xuất Aggregate mà không để Application
phụ thuộc vào chi tiết database:

~~~java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}
~~~

Repository không cần có method cho từng bảng hoặc từng OrderLine. Nếu cần
tìm danh sách cho màn hình, có thể dùng query service/read model riêng.

## 21. Application Service điều phối use case

Application Service nhận command, lấy quote đã xác minh, tạo Order và lưu
Aggregate. Các bước liên context được kích hoạt qua outbox/event hoặc
Process Manager.

~~~java
public record PlaceOrderCommand(
        QuoteId quoteId,
        String idempotencyKey
) {}

public final class PlaceOrderService {
    private final QuoteGateway quotes;
    private final OrderRepository orders;
    private final OrderIdGenerator ids;
    private final CurrentCustomer currentCustomer;

    public PlaceOrderService(
            QuoteGateway quotes,
            OrderRepository orders,
            OrderIdGenerator ids,
            CurrentCustomer currentCustomer
    ) {
        this.quotes = quotes;
        this.orders = orders;
        this.ids = ids;
        this.currentCustomer = currentCustomer;
    }

    public OrderId handle(PlaceOrderCommand command) {
        CustomerId customerId = currentCustomer.id();
        VerifiedQuote quote = quotes.getValidQuote(
                command.quoteId(),
                customerId
        );

        Order order = Order.place(
                ids.next(),
                customerId,
                quote.quoteId(),
                quote.toOrderLines()
        );

        orders.save(order);
        return order.id();
    }
}
~~~

CurrentCustomer lấy CustomerId từ danh tính đã xác thực; API không tin
customerId tùy ý do client gửi. Ví dụ lược bỏ transaction, outbox và xử lý
idempotency để làm rõ luồng.
Trong hệ thống thật, kiểm tra idempotency và ghi Order cùng Outbox Message
cần được bảo vệ bằng local transaction phù hợp. QuoteGateway là port; adapter
gọi Pricing contract và chuyển kết quả thành kiểu nội bộ.

## 22. Luồng tích hợp hoàn chỉnh

Một trình tự có thể là:

~~~mermaid
sequenceDiagram
    actor Customer
    participant API as Sales API
    participant Sales as Sales Order
    participant PM as Order Process Manager
    participant Inv as Inventory
    participant Pay as Payment
    participant Ful as Fulfillment

    Customer->>API: Submit order with QuoteId
    API->>Sales: PlaceOrder
    Sales->>Sales: Validate quote and create Order
    Sales-->>PM: OrderPlaced
    PM->>Inv: ReserveStock
    PM->>Pay: AuthorizePayment
    Inv-->>PM: StockReserved
    Pay-->>PM: PaymentAuthorized
    PM->>Sales: ConfirmOrder with evidence
    Sales->>Sales: Order.confirm()
    Sales-->>Ful: OrderConfirmed
~~~

Nếu Inventory hoặc Payment thất bại, Process Manager không gửi ConfirmOrder.
Nó gửi yêu cầu compensation phù hợp:

| Kết quả đã có | Kết quả thất bại | Compensation |
|---|---|---|
| StockReserved | PaymentAuthorizationFailed | Release reservation |
| PaymentAuthorized | StockReservationRejected | Void authorization |
| Cả hai thành công | ConfirmOrder thất bại do state conflict | Điều tra và compensation theo policy |

Đây là Saga/process workflow có các local transaction và hành động bù. Nó
không cung cấp rollback nguyên tử trên nhiều context.

## 23. Idempotency và consistency

Client có thể gửi lại PlaceOrder do timeout. Broker có thể giao lại event.
Payment provider có thể gửi callback nhiều lần. Hệ thống cần các khóa và
quy tắc chống side effect lặp:

- idempotencyKey cho yêu cầu đặt hàng từ client.
- eventId cho message deduplication.
- providerTransactionId cho callback thanh toán.
- reservationId cho thao tác giữ/giải phóng hàng.
- unique constraint phù hợp trong database.

Strong consistency được bảo vệ trong Aggregate transaction của từng context.
Giữa các context, hệ thống thường dùng eventual consistency và trạng thái
workflow có thể quan sát được.

Không nên trả lời “đã xác nhận đơn” ngay khi chỉ mới ghi OrderPlaced nếu
contract với khách hiểu xác nhận là cả hàng và thanh toán đã sẵn sàng. Có thể
trả trạng thái PendingConfirmation và cập nhật khi OrderConfirmed xuất hiện.

## 24. API phản ánh use case

API công khai có thể cung cấp:

~~~http
POST /orders
Idempotency-Key: checkout-2026-0001
Content-Type: application/json
~~~

~~~json
{
  "quoteId": "quote-456"
}
~~~

Response ban đầu:

~~~http
HTTP/1.1 202 Accepted
Location: /orders/order-789
~~~

~~~json
{
  "orderId": "order-789",
  "status": "PENDING_CONFIRMATION"
}
~~~

Nếu xử lý xác nhận đồng bộ và nhanh theo business requirement, response có
thể là 201 Created. Với workflow bất đồng bộ, 202 phù hợp khi tài nguyên đã
được tiếp nhận nhưng quy trình chưa hoàn tất.

Không để client gửi totalAmount rồi tin đó là giá phải thu. Client gửi
QuoteId; Sales xác minh quote với Pricing và tạo snapshot từ dữ liệu được
chấp nhận.

## 25. Persistence và Transactional Outbox

Trong Sales Order, việc lưu Order và ghi message OrderPlaced nên nằm trong
cùng local database transaction. Outbox Publisher đọc message sau commit và
gửi tới broker.

~~~mermaid
flowchart TD
    A[PlaceOrder use case] --> T[Sales DB transaction]
    T --> O[Save Order]
    T --> B[Insert Outbox OrderPlaced]
    O --> C[Commit]
    B --> C
    C --> P[Outbox Publisher]
    P --> M[(Message Broker)]
    M --> R[Process Manager]
~~~

Outbox tránh tình huống Order đã commit nhưng message bị mất vì ứng dụng
crash trước khi publish. Nó không bảo đảm message chỉ được giao đúng một lần.
Consumer vẫn cần idempotency.

## 26. Kiểm thử từ quy tắc đến tích hợp

Không nên chỉ viết một end-to-end test lớn. Hãy phân tầng kiểm thử theo
những điều cần chứng minh.

### 26.1. Unit test cho Value Object

~~~java
@Test
void moneyCannotBeAddedAcrossCurrencies() {
    Money vnd = new Money(
            new BigDecimal("10000"),
            Currency.getInstance("VND")
    );
    Money usd = new Money(
            new BigDecimal("10"),
            Currency.getInstance("USD")
    );

    assertThrows(IllegalArgumentException.class, () -> vnd.add(usd));
}
~~~

### 26.2. Unit test cho Aggregate

~~~java
@Test
void orderCannotBeConfirmedWithoutPendingState() {
    Order order = anOrderInPendingConfirmation();
    order.confirm(validConfirmationEvidence());

    assertThrows(
            InvalidOrderState.class,
            () -> order.confirm(validConfirmationEvidence())
    );
}
~~~

Test này bảo vệ việc một đơn đã Confirmed không được confirm lần nữa. Cần
thêm test cho đơn rỗng, currency khác nhau, quote không hợp lệ và reject
không đúng trạng thái.

### 26.3. Test Process Manager

Kiểm tra:

- StockReserved đến trước PaymentAuthorized: chưa confirm.
- PaymentAuthorized đến trước StockReserved: chưa confirm.
- Cả hai đến: gửi ConfirmOrder đúng một lần.
- Một bên thất bại: gửi compensation cho bên đã thành công.
- Event trùng: không gửi command lặp.
- Event đến trễ sau khi workflow đã kết thúc: xử lý theo policy.

### 26.4. Contract test

Producer kiểm tra Integration Event đúng schema và semantics. Consumer kiểm
tra có thể parse version đang hỗ trợ và map sang command nội bộ. Thay đổi
field, unit hoặc ý nghĩa phải được xác minh với các consumer.

### 26.5. Integration test

Dùng database và broker phù hợp để kiểm tra:

- Order và Outbox commit/rollback cùng nhau.
- Publisher phát message sau commit.
- Consumer nhận message và ghi Inbox.
- Retry hoặc redelivery không tạo side effect lặp.
- Routing key, topic, serializer và acknowledgement đúng cấu hình.

## 27. Acceptance examples cho lát cắt

Các ví dụ sau có thể được dùng trong workshop, specification hoặc
acceptance test:

~~~gherkin
Feature: Confirm an order

  Scenario: Confirm when stock and payment are ready
    Given a valid quote for the customer
    And all requested stock can be reserved
    And payment authorization succeeds
    When the customer places the order
    Then the order eventually becomes Confirmed

  Scenario: Reject when stock is unavailable
    Given a valid quote for the customer
    And at least one order line cannot be reserved
    When the customer places the order
    Then the order does not become Confirmed
    And any successful payment authorization is voided

  Scenario: Release stock when payment authorization fails
    Given a valid quote for the customer
    And all requested stock has been reserved
    When payment authorization fails
    Then the order does not become Confirmed
    And the reservation is released

  Scenario: Retry the same placement request
    Given a placement request with an idempotency key
    When the same request is submitted again
    Then the same order result is returned
    And no second order is created
~~~

Các scenario là đặc tả của giả định trong bài. Domain expert cần xác nhận
thứ tự, trạng thái và kết quả compensation trước khi dùng trong production.

## 28. Theo dõi tiến trình và vận hành

Một workflow bất đồng bộ cần được quan sát. Hãy ghi correlationId xuyên qua
command, event và log để điều tra một đơn cụ thể.

Các metric hữu ích:

- Số đơn đang PendingConfirmation.
- Thời gian từ OrderPlaced đến OrderConfirmed.
- Tỷ lệ reservation thất bại.
- Tỷ lệ payment authorization thất bại.
- Số workflow quá hạn.
- Số lần retry và duplicate event.
- Số compensation thất bại.
- Số message vào dead-letter queue.

Metric không thay thế business model. Nó cho thấy hệ thống đang thực hiện
quy trình đã mô hình hóa ra sao và giúp đội tìm ra tình huống mới cần khám
phá.

## 29. Ghi lại quyết định và câu hỏi còn mở

Sau workshop, không chỉ lưu sơ đồ. Hãy ghi lại:

~~~text
Decision:
  Order is confirmed only after stock reservation and payment authorization.

Evidence:
  Operations examples from successful and failed orders.

Model impact:
  Order has PendingConfirmation, Confirmed and Rejected states.
  A process manager coordinates Inventory and Payment.

Open questions:
  Does the business allow partial fulfillment?
  How long may a stock reservation remain active?
  When is payment captured?
  What is the cancellation cutoff?

Owner:
  Sales Operations / Finance / Warehouse, depending on question.
~~~

Quyết định nên có owner và bằng chứng. Câu hỏi mở nên có người chịu trách
nhiệm tìm câu trả lời; nếu không, giả định dễ tồn tại vô thời hạn trong code.

## 30. Kế hoạch discovery và implementation theo lát cắt

Một kế hoạch khả thi có thể chia như sau:

| Giai đoạn | Hoạt động | Đầu ra |
|---|---|---|
| 1. Discovery | Phỏng vấn, thu thập S1-S8, Event Storming | Scenario và hotspot |
| 2. Language | Thống nhất thuật ngữ, ghi từ mơ hồ | Ubiquitous Language |
| 3. Strategic design | Phân loại subdomain, đề xuất context | Context Map |
| 4. Rules | Tách invariant, policy và workflow | Rule catalogue |
| 5. Tactical model | Thiết kế Value Object, Order Aggregate | Domain model |
| 6. Application | PlaceOrder, Process Manager, repositories | Use case flow |
| 7. Integration | Contract, Outbox/Inbox, compensation | Integration design |
| 8. Verification | Unit, acceptance, contract, integration tests | Bằng chứng model |
| 9. Feedback | Quan sát vận hành, review ngoại lệ | Learning backlog mới |

Đây không phải chuỗi cứng. Nếu khi viết test đội phát hiện khái niệm
Reservation chưa rõ, hãy quay lại discovery thay vì cố hoàn tất code theo
mô hình sai.

## 31. Những câu hỏi cần mang lại cho domain expert

Trước khi xem mô hình là đủ tin cậy, hãy xác nhận:

1. Quote được giữ trong bao lâu và điều gì làm quote mất hiệu lực?
2. Giá có thể thay đổi sau khi khách gửi PlaceOrder không?
3. Có cho phép một đơn chứa nhiều currency không?
4. Có cho phép giữ một phần số lượng không?
5. Reservation hết hạn được xử lý thế nào?
6. Payment timeout có thể được truy vấn lại hay phải authorize lại?
7. Khi nào capture tiền?
8. Trường hợp nào được phép hủy đơn?
9. Sau dispatch, quy trình là cancel hay return?
10. Khách nhìn thấy trạng thái PendingConfirmation trong bao lâu?
11. Ai có quyền override một thất bại tự động?
12. Những quyết định nào cần lưu audit và lý do?

Đây là danh sách khám phá, không phải câu trả lời có sẵn. Một mô hình tốt
phải phản ánh câu trả lời đã được xác nhận của doanh nghiệp.

## 32. Các lỗi thiết kế thường gặp trong bài thực hành

### Bắt đầu từ database schema

Danh sách bảng không nói rõ sự kiện, hành động và invariant. Hãy bắt đầu từ
scenario và quy tắc.

### Một Order Aggregate chứa mọi context

Order không nên sở hữu tồn kho, giao dịch thanh toán và shipment. Hãy giữ
Aggregate boundary theo ownership và consistency.

### Xác nhận đơn ngay khi nhận request

OrderPlaced và OrderConfirmed là hai business fact khác nhau trong ví dụ.
Đừng gộp chúng nếu còn điều kiện bất đồng bộ.

### Dùng một trạng thái Payment chung chung

Authorize, capture, void và refund có ý nghĩa khác nhau. Dùng từ đúng để
tránh xử lý tiền sai.

### Đặt workflow vào Aggregate

Aggregate bảo vệ invariant nội tại. Process Manager theo dõi tiến trình qua
nhiều context.

### Gọi trực tiếp database của context khác

Giao tiếp qua contract và adapter. Không truy cập bảng nội bộ để rút ngắn
đường đi.

### Coi message broker là exactly-once

Thiết kế cho redelivery, retry và idempotency. Không dựa vào giả định message
chỉ đến một lần.

### Chia microservice quá sớm

Bounded Context là ranh giới model. Có thể triển khai nhiều context trong
modular monolith trước khi có lý do vận hành để tách service.

## 33. Bài tập thực hành

Hãy dùng case trên để tự hoàn thiện một vòng DDD:

### Bài tập A — Discovery

- Viết thêm ba kịch bản ngoại lệ.
- Phỏng vấn giả định ba vai trò: Sales, Warehouse và Finance.
- Ghi ít nhất năm câu hỏi chưa có bằng chứng.

### Bài tập B — Language

- Tạo glossary cho ít nhất mười thuật ngữ.
- Tìm ba từ có thể mang ý nghĩa khác nhau giữa hai context.
- Đề xuất cách đặt tên event và command.

### Bài tập C — Strategic Design

- Phân loại lại subdomain theo chiến lược của một nhà bán lẻ cụ thể.
- Vẽ Context Map và ghi upstream/downstream.
- Giải thích vì sao mỗi context sở hữu model riêng.

### Bài tập D — Tactical Design

- Xác định invariant của Order.
- Viết Money, Quantity và OrderLine.
- Chọn Aggregate boundary.
- Viết test cho confirm và reject.

### Bài tập E — Integration

- Thiết kế event contract cho OrderPlaced.
- Viết luồng Process Manager.
- Mô tả compensation khi một nhánh thất bại.
- Xác định idempotency key và eventId.

### Bài tập F — Review

- Chọn một giả định ban đầu và thay bằng bằng chứng mới.
- Mô tả model thay đổi ra sao.
- Cập nhật acceptance example và test tương ứng.

## 34. Checklist đánh giá mô hình tổng hợp

~~~text
Discovery
  [ ] Có business outcome và phạm vi rõ
  [ ] Có happy path, failure path và edge cases
  [ ] Có domain expert xác nhận quy tắc
  [ ] Giả định và câu hỏi mở được ghi riêng

Strategic design
  [ ] Subdomain được phân loại có căn cứ
  [ ] Bounded Context có model ownership rõ
  [ ] Context Map thể hiện contract và dependency
  [ ] Không suy ra microservice chỉ từ context boundary

Language
  [ ] Thuật ngữ có định nghĩa và ví dụ
  [ ] Command được phân biệt với event
  [ ] Authorize/capture/void/refund không bị nhập nhằng

Tactical design
  [ ] Entity có identity đúng nghĩa
  [ ] Value Object bảo vệ value constraint
  [ ] Aggregate bảo vệ invariant
  [ ] Repository làm việc theo Aggregate Root
  [ ] Domain Event phản ánh business fact

Integration
  [ ] Cross-context contract được version hóa
  [ ] Workflow bất đồng bộ có trạng thái bền vững
  [ ] Retry và duplicate được xử lý
  [ ] Compensation có quy tắc rõ
  [ ] Outbox/Inbox được xem xét

Verification
  [ ] Unit tests bảo vệ invariant
  [ ] Acceptance tests thể hiện scenario
  [ ] Contract tests bảo vệ integration
  [ ] Integration tests xác minh adapter

Continuous learning
  [ ] Quyết định có evidence và owner
  [ ] Production feedback quay lại learning backlog
  [ ] Model, code, tests và documentation được cập nhật cùng nhau
~~~

## 35. Kết luận

Khám phá một miền bán hàng theo DDD là quá trình đi từ tình huống thật đến
quy tắc, từ quy tắc đến ngôn ngữ chung, từ ngôn ngữ đến ranh giới model, rồi
từ model đến code và kiểm thử. Event Storming giúp nhóm nhìn thấy hành vi;
subdomain và bounded context giúp xác định trọng tâm và ownership; tactical
design giúp bảo vệ invariant; Integration Event và Process Manager giúp các
context phối hợp mà không phải chia sẻ một Aggregate khổng lồ.

Mô hình trong bài là một giả thuyết thực hành có thể kiểm chứng, không phải
blueprint áp dụng cho mọi nhà bán lẻ. Giá trị của DDD nằm ở việc đội cùng
domain expert liên tục xác nhận, sửa và làm sâu mô hình dựa trên bằng chứng
nghiệp vụ. Khi mỗi quyết định có ngôn ngữ, ví dụ, code và test tương ứng,
đội phát triển có thể thay đổi hệ thống mà vẫn giữ được ý nghĩa kinh doanh.

# Tách khái niệm phức tạp thành mô hình nhỏ có quan hệ rõ ràng

Trong Domain-Driven Design (DDD), mô hình miền là cách đội phát triển diễn đạt và thực thi hiểu biết nghiệp vụ. Khi hệ thống lớn dần, một khái niệm ban đầu đơn giản có thể tích lũy thêm trạng thái, quy tắc, điều kiện và quan hệ. Một lớp Order có thể vừa giữ thông tin khách hàng, dòng hàng, giá, khuyến mãi, vận chuyển, thanh toán, hóa đơn, hoàn tiền và trạng thái giao nhận. Khi mọi thứ bị gom vào một object hoặc một module, thay đổi nhỏ cũng trở nên khó dự đoán.

Thiết kế dễ thay đổi bắt đầu bằng việc **tách các khái niệm có trách nhiệm khác nhau thành những mô hình nhỏ, có tên và quan hệ rõ ràng**. Mỗi phần cần có ý nghĩa nghiệp vụ, invariant và quyền sở hữu được xác định. Các phần phối hợp qua hợp đồng tường minh, giúp người đọc biết dữ liệu thuộc về ai, ai được phép thay đổi, quan hệ có bắt buộc hay không và thay đổi được nhất quán ở phạm vi nào.

Tách nhỏ không có nghĩa là tạo thật nhiều class hoặc service. Một mô hình tốt làm cho quy tắc dễ tìm, trạng thái hợp lệ dễ diễn đạt và tác động của thay đổi dễ giới hạn. Mục tiêu là giảm sự phụ thuộc ngầm, không phải tăng số lượng thành phần.

## 1. Vì sao một mô hình lớn khó thay đổi?

### 1.1. Nhiều khái niệm bị trộn trong cùng một object

Giả sử một lớp Order có các field:

~~~java
public class Order {
    UUID id;
    UUID customerId;
    String customerName;
    String customerAddress;
    String shippingAddress;
    String billingAddress;
    List<OrderLine> lines;
    BigDecimal subtotal;
    BigDecimal discount;
    BigDecimal tax;
    BigDecimal shippingFee;
    BigDecimal total;
    String paymentStatus;
    String shipmentStatus;
    String invoiceStatus;
    boolean refundRequested;
    boolean priorityShipping;
    boolean giftWrapped;
    boolean manuallyApproved;
    // Rất nhiều field và phương thức khác.
}
~~~

Lớp này có vẻ tiện vì mọi thông tin đều nằm cùng nơi. Nhưng nó đang đại diện cho nhiều khái niệm khác nhau:

- Đơn hàng và các dòng hàng.
- Danh tính khách hàng.
- Địa chỉ giao hàng và địa chỉ thanh toán.
- Kết quả định giá, thuế và giảm giá.
- Thanh toán.
- Giao nhận.
- Hóa đơn.
- Hoàn tiền.

Mỗi khái niệm có vòng đời và quy tắc thay đổi riêng. Khi một lớp sở hữu tất cả, thay đổi ở thanh toán có thể ảnh hưởng đến xác nhận đơn; thay đổi cách tính thuế có thể tác động vào logic giao hàng; một cờ boolean mới có thể tạo thêm nhiều nhánh trong các phương thức không liên quan.

### 1.2. Quy tắc bị phân tán

Một số quy tắc nằm trong Order, một số nằm trong controller, một số trong repository, một số lại được viết lại ở màn hình. Ví dụ, kiểm tra đơn có thể hủy được ở ba nơi:

~~~java
if (order.status() != OrderStatus.SHIPPED) {
    // Cho phép hủy ở controller.
}
~~~

~~~java
if (!order.isPaid()) {
    // Cho phép hủy ở application service.
}
~~~

~~~java
if (order.status() == OrderStatus.CONFIRMED) {
    // Cho phép hủy ở giao diện.
}
~~~

Ba điều kiện không diễn đạt cùng một quy tắc. Khi chính sách thay đổi, đội phát triển không biết đâu là nguồn chân lý.

### 1.3. Quan hệ ngầm tạo ra coupling

Một field nullable có thể có nhiều cách hiểu:

- Chưa có địa chỉ.
- Chưa tải địa chỉ.
- Địa chỉ không áp dụng.
- Dữ liệu bị thiếu do lỗi mapping.

Một danh sách có thể là null hoặc rỗng; một ID có thể trỏ đến object đã bị xóa; một trạng thái có thể phụ thuộc vào một cờ boolean khác. Người đọc phải biết các quy ước ngầm mới hiểu được object.

Mô hình nhỏ với kiểu dữ liệu và quan hệ rõ ràng giúp loại bỏ nhiều trạng thái mơ hồ ngay từ thiết kế.

## 2. Phân rã theo ý nghĩa nghiệp vụ, không theo số lượng field

Trước khi tách class, hãy hỏi phần nào thực sự là một khái niệm riêng trong ngôn ngữ nghiệp vụ.

Hai tiêu chí hữu ích khi đánh giá kết quả phân rã là **cohesion** và **coupling**. Cohesion cho biết các phần bên trong một thành phần có cùng phục vụ một trách nhiệm nghiệp vụ hay không. Coupling cho biết một thành phần phụ thuộc vào những thành phần khác ở mức nào. Hướng tới cohesion cao và coupling thấp: các quy tắc liên quan được đặt gần nhau, còn quan hệ ra bên ngoài được giới hạn bằng hợp đồng rõ. Không cần loại bỏ mọi phụ thuộc; cần làm cho phụ thuộc cần thiết trở nên có chủ đích và dễ kiểm soát.

### 2.1. Tìm các khái niệm có tên riêng

Trong một quy trình bán hàng, chuyên gia nghiệp vụ có thể nói:

- Đơn hàng được tạo.
- Báo giá có hiệu lực trong 30 phút.
- Kho giữ chỗ số lượng hàng.
- Thanh toán được ủy quyền.
- Lô giao hàng được tạo.
- Hóa đơn được phát hành.

Các danh từ và động từ này gợi ý những khái niệm có identity, vòng đời hoặc quy tắc riêng. Chúng là điểm bắt đầu để khám phá mô hình.

Không phải danh từ nào cũng cần một Entity. “Tổng tiền”, “địa chỉ giao hàng” hoặc “khoảng hiệu lực” có thể phù hợp hơn với Value Object. “Có thể hoàn tiền không?” có thể là một Policy hoặc Specification.

### 2.2. Nhận diện invariant

Invariant là điều kiện phải luôn đúng đối với mô hình trong phạm vi mà domain cam kết bảo vệ.

Ví dụ:

- Tổng tiền đơn bằng tổng các dòng hàng sau khi áp dụng các điều chỉnh hợp lệ.
- Số lượng của một dòng hàng phải lớn hơn 0.
- Đơn đã giao không thể quay về trạng thái Draft.
- Một lần giữ chỗ không được làm số lượng tồn khả dụng âm.
- Một hợp đồng đã ký phải tham chiếu đúng phiên bản điều khoản đã chấp thuận.

Những quy tắc phải được bảo vệ cùng nhau thường gợi ý các thành phần nên ở gần nhau. Các quy tắc có thể thay đổi độc lập thường là tín hiệu để tách khái niệm hoặc ranh giới.

### 2.3. Dùng vòng đời và quyền sở hữu để tìm ranh giới

Một khái niệm đáng được mô hình hóa riêng khi có một hoặc nhiều đặc điểm:

- Có identity riêng và cần được tham chiếu.
- Có trạng thái hoặc vòng đời riêng.
- Có quy tắc thay đổi riêng.
- Được một vai trò hoặc bộ phận khác sở hữu.
- Có tần suất thay đổi khác các khái niệm lân cận.
- Có thể được dùng trong nhiều quy trình mà không cần phụ thuộc vào toàn bộ object cha.
- Cần được kiểm thử hoặc lưu trữ độc lập.

Ví dụ, Payment có vòng đời Pending, Authorized, Captured, Failed, Refunded. Nó có identity và lịch sử giao dịch riêng, nên không nên chỉ là vài field trong Order.

### 2.4. Không tách chỉ vì một lớp dài

Một lớp 200 dòng có thể vẫn là một aggregate root có trách nhiệm nhất quán rõ ràng. Ngược lại, một lớp 20 dòng có thể đang gom hai khái niệm không liên quan.

Độ dài file là tín hiệu để xem xét, không phải tiêu chí quyết định. Cần phân tích ngôn ngữ, invariant, vòng đời, quyền sở hữu và lý do thay đổi.

## 3. Chọn đúng loại mô hình: Entity, Value Object, Aggregate và Domain Service

### 3.1. Entity: khái niệm có identity

Entity có identity xuyên suốt các lần thay đổi trạng thái. Hai object có field giống nhau vẫn có thể là hai Entity khác nhau.

Ví dụ:

- Order.
- Customer.
- Payment.
- Shipment.
- Contract.

Identity nên được biểu diễn bằng kiểu riêng:

~~~java
public record OrderId(UUID value) {
    public OrderId {
        Objects.requireNonNull(value);
    }
}

public record PaymentId(UUID value) {
    public PaymentId {
        Objects.requireNonNull(value);
    }
}
~~~

Các kiểu ID riêng giúp tránh truyền nhầm CustomerId vào nơi cần OrderId, dù bên trong chúng cùng dùng UUID.

### 3.2. Value Object: mô tả giá trị và quy tắc

Value Object không có identity riêng; nó được xác định bởi giá trị và thường bất biến.

Ví dụ:

- Money.
- Quantity.
- Address.
- EffectivePeriod.
- Percentage.
- Dimensions.

~~~java
public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount);
        Objects.requireNonNull(currency);

        int fractionDigits = currency.getDefaultFractionDigits();
        if (fractionDigits >= 0
                && amount.stripTrailingZeros().scale() > fractionDigits) {
            throw new IllegalArgumentException(
                "Amount has too many fractional digits"
            );
        }
    }

    public Money add(Money other) {
        requireSameCurrency(other);
        return new Money(amount.add(other.amount), currency);
    }

    private void requireSameCurrency(Money other) {
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException(
                "Currency must match"
            );
        }
    }
}
~~~

Ví dụ này minh họa ý tưởng; quy tắc scale và rounding thực tế cần dựa trên currency, loại nghiệp vụ và chính sách làm tròn. Việc đóng gói trong Money giúp caller không tự cộng BigDecimal mà quên kiểm tra currency.

### 3.3. Aggregate: nhóm các object cần bảo vệ invariant cùng nhau

Aggregate xác định ranh giới nhất quán. Aggregate Root là điểm truy cập để thay đổi trạng thái bên trong.

Ví dụ Order có thể sở hữu OrderLine. Người gọi thay đổi dòng hàng thông qua Order để Order kiểm tra trạng thái, số lượng và tổng tiền.

Một Payment riêng không tự động trở thành thành phần bên trong Order chỉ vì nó có quan hệ với đơn hàng. Nếu Payment có vòng đời và invariant riêng, Order có thể giữ PaymentId hoặc tham chiếu đến kết quả thanh toán theo hợp đồng phù hợp.

### 3.4. Domain Service: quy tắc không thuộc tự nhiên về một Entity hay Value Object

Một quy tắc nghiệp vụ có thể cần phối hợp nhiều khái niệm nhưng không thuộc về riêng object nào.

Ví dụ:

- Định giá giỏ hàng theo một price list và chính sách chiết khấu.
- Tính điều kiện đủ tiêu chuẩn của một khách hàng cho chương trình.
- Phân bổ một khoản thanh toán vào nhiều nghĩa vụ.

Domain Service nên có tên diễn đạt hành vi nghiệp vụ, không phải tên kỹ thuật như `Helper` hoặc `Manager`. Nó không nên trở thành nơi chứa mọi logic bị đẩy ra khỏi Entity.

### 3.5. Policy và Specification

Policy biểu diễn một chính sách quyết định. Specification biểu diễn điều kiện có thể kiểm tra trên một candidate.

Ví dụ, điều kiện “đơn đủ điều kiện giao miễn phí” có thể được mô hình hóa thành một Specification. Chính sách chọn phương thức vận chuyển có thể là ShippingPolicy.

Khi một điều kiện thay đổi độc lập hoặc có nhiều biến thể, việc đặt tên riêng giúp hệ thống dễ mở rộng hơn một chuỗi if dài trong Order.

## 4. Quan hệ phải nói rõ nhiều hơn một field tham chiếu

Một quan hệ tốt cần trả lời các câu hỏi sau:

| Chiều quan hệ | Câu hỏi cần làm rõ |
|---|---|
| Identity | Hai phía được nhận diện bằng gì? |
| Cardinality | Một-một, một-nhiều hay nhiều-nhiều? |
| Optionality | Quan hệ bắt buộc hay tùy chọn? |
| Ownership | Bên nào sở hữu vòng đời của bên kia? |
| Direction | Bên nào được phép điều hướng hoặc truy cập bên kia? |
| Consistency | Thay đổi cần nguyên tử cùng nhau hay chấp nhận eventual consistency? |
| Time | Quan hệ đúng ở thời điểm nào? |
| Deletion | Khi xóa hoặc kết thúc vòng đời, quan hệ được xử lý ra sao? |

Nếu các câu hỏi này không có câu trả lời, quan hệ thường vẫn đang dựa vào giả định ngầm.

### 4.1. Cardinality

Cardinality mô tả số lượng phần tử ở hai đầu quan hệ:

- Một Order Draft có thể có 0..n OrderLine; trước khi Submit phải có ít nhất một dòng.
- Một Customer có thể có nhiều Order.
- Một Order có thể có nhiều PaymentAttempt.
- Một Shipment có thể gom hàng từ nhiều Order trong mô hình fulfillment phù hợp.

Không nên chọn một-một hoặc một-nhiều chỉ vì mapping database thuận tiện. Hãy hỏi nghiệp vụ cho phép bao nhiêu phần tử và điều kiện nào giới hạn số lượng.

### 4.2. Optionality

Optionality mô tả quan hệ có thể chưa tồn tại hay không.

Ví dụ:

- Draft Order có thể chưa có địa chỉ giao hàng.
- Order đã xác nhận giao hàng phải có địa chỉ hợp lệ.
- Payment có thể chưa được tạo ở bước đặt hàng.
- Invoice chỉ tồn tại sau khi đạt điều kiện phát hành.

Không phải cứ field nullable là đã mô hình hóa optionality đúng. Có thể cần phân biệt trạng thái trước và sau một hành vi.

### 4.3. Ownership và vòng đời

Nếu OrderLine không có ý nghĩa độc lập ngoài Order và vòng đời của nó được quản lý theo Order, nó có thể thuộc Order aggregate. Việc xóa vật lý, lưu trữ hoặc ẩn dòng hàng vẫn phải tuân theo retention và yêu cầu audit của nghiệp vụ.

Nếu Shipment được quản lý độc lập bởi bộ phận logistics, có trạng thái và lịch sử riêng, Order không nên sở hữu vòng đời Shipment. Nó chỉ cần biết shipment reference hoặc nhận các sự kiện liên quan.

Ownership trả lời ai chịu trách nhiệm bảo vệ và thay đổi dữ liệu. Nó không đồng nghĩa với việc object nào chứa field của object nào.

### 4.4. Hướng quan hệ và phụ thuộc

Không cần cả hai phía đều giữ reference đến nhau.

Ví dụ:

- Order giữ CustomerId để biết đơn thuộc khách hàng nào.
- Customer không nhất thiết giữ collection tất cả Order trong aggregate.
- Payment giữ OrderId nếu payment context cần liên kết giao dịch.
- Order có thể lưu PaymentReference hoặc trạng thái thanh toán được đồng bộ qua event.

Quan hệ một chiều thường giảm coupling và tránh phải tải một object graph lớn.

### 4.5. Quan hệ có thuộc tính riêng

Một quan hệ nhiều-nhiều đơn giản có thể được biểu diễn bằng tập hợp ID. Nhưng nếu chính quan hệ có dữ liệu hoặc vòng đời riêng, hãy mô hình hóa nó thành một khái niệm.

Ví dụ, một nhân viên tham gia một dự án có vai trò, ngày bắt đầu, ngày kết thúc và trạng thái phân công. Quan hệ Employee–Project lúc này không chỉ là hai ID:

~~~java
public record ProjectAssignment(
        EmployeeId employeeId,
        ProjectId projectId,
        ProjectRole role,
        LocalDate startsOn,
        LocalDate endsOn) {
}
~~~

Tương tự, một OrderLine có số lượng và giá tại thời điểm đặt hàng nên có ý nghĩa riêng trong mô hình Order. Chỉ tạo association Entity khi các thuộc tính hoặc vòng đời của quan hệ có ý nghĩa nghiệp vụ; không cần tạo class trung gian cho mọi quan hệ nhiều-nhiều.

### 4.6. Quan hệ theo thời gian

Một Contract có thể liên kết với Customer tại thời điểm ký, nhưng Customer profile hiện tại có thể đã thay đổi.

Nếu cần tái hiện hợp đồng, cần lưu snapshot các thông tin bên ký hoặc tham chiếu tới bản ghi/version bất biến. Chỉ lưu CustomerId rồi đọc tên và địa chỉ hiện tại có thể làm thay đổi cách hiểu tài liệu lịch sử.

Tương tự, OrderLine cần lưu PriceVersionId hoặc snapshot giá đã chốt, thay vì mỗi lần hiển thị lại tra giá hiện tại.

## 5. Phân biệt object composition với aggregate boundary

Một lỗi phổ biến là xem mọi object lồng nhau là cùng một aggregate.

### 5.1. Composition trong object model

Order có thể chứa Address, Money, OrderLine và DiscountSummary như các object con. Điều đó giúp cấu trúc code rõ ràng.

Tuy nhiên, composition không tự quyết định:

- Tất cả có cùng transaction boundary không?
- Các object có thể được lưu riêng không?
- Có được cập nhật độc lập không?
- Có vòng đời riêng không?

Đó là các câu hỏi của aggregate và persistence design.

### 5.2. Một aggregate có thể gồm nhiều class nhỏ

~~~java
public class Order {
    private final OrderId id;
    private final CustomerId customerId;
    private final List<OrderLine> lines = new ArrayList<>();
    private ShippingAddress shippingAddress;
    private OrderStatus status = OrderStatus.DRAFT;

    public void addLine(ProductId productId, Quantity quantity,
                        Money unitPrice) {
        requireDraft();
        if (quantity.isZeroOrNegative()) {
            throw new InvalidOrderQuantity();
        }
        lines.add(OrderLine.create(productId, quantity, unitPrice));
    }

    public void changeShippingAddress(ShippingAddress address) {
        requireDraft();
        this.shippingAddress = Objects.requireNonNull(address);
    }

    public void submit() {
        requireDraft();
        if (lines.isEmpty()) {
            throw new EmptyOrderCannotBeSubmitted();
        }
        if (shippingAddress == null) {
            throw new ShippingAddressRequired();
        }
        status = OrderStatus.SUBMITTED;
    }

    private void requireDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new OrderIsNotEditable();
        }
    }
}
~~~

Order vẫn là một aggregate, nhưng trách nhiệm được diễn đạt bằng các kiểu nhỏ và hành vi có tên. OrderLine có thể là Entity nội bộ nếu cần nhận diện dòng hàng trong vòng đời đơn; Quantity, Money và ShippingAddress là Value Object.

### 5.3. Hai aggregate có thể liên kết bằng ID

~~~java
public class Payment {
    private final PaymentId id;
    private final OrderId orderId;
    private PaymentStatus status;
}
~~~

Payment được quản lý trong aggregate riêng. Nó biết OrderId nhưng không cần giữ toàn bộ object Order. Hai aggregate có thể được điều phối qua application service, domain event hoặc một quy trình nhất quán phù hợp.

### 5.4. Không dùng aggregate để biểu diễn mọi quan hệ database

Foreign key trong database mô tả liên kết lưu trữ. Aggregate boundary mô tả invariant và quyền thay đổi. Một bảng có foreign key không chứng minh hai entity phải nằm cùng aggregate.

Ngược lại, một aggregate có thể được lưu qua nhiều bảng. Cấu trúc object và cấu trúc relational mapping không nhất thiết trùng nhau.

## 6. Ví dụ phân rã mô hình Order

Giả sử hệ thống bán hàng có các yêu cầu:

- Khách hàng tạo đơn với nhiều dòng hàng.
- Mỗi dòng lưu số lượng và giá đã chốt.
- Đơn cần địa chỉ giao hàng trước khi submit.
- Thanh toán được xử lý bởi Payment context.
- Shipment được tạo sau khi đơn đủ điều kiện fulfillment.
- Đơn đã submit không được chỉnh sửa dòng hàng.

### 6.1. Mô hình khái niệm

~~~mermaid
classDiagram
    class Order {
        OrderId id
        CustomerId customerId
        OrderStatus status
        addLine()
        changeShippingAddress()
        submit()
    }
    class OrderLine {
        OrderLineId id
        ProductId productId
        Quantity quantity
        Money unitPrice
    }
    class ShippingAddress {
        String recipient
        String street
        String city
        String postalCode
    }
    class Money {
        Decimal amount
        Currency currency
    }
    class Payment {
        PaymentId id
        OrderId orderId
        PaymentStatus status
    }
    class Shipment {
        ShipmentId id
        OrderId orderId
        ShipmentStatus status
    }
    Order "1" *-- "0..*" OrderLine
    Order "1" *-- "0..1" ShippingAddress
    OrderLine --> Money
    Payment --> OrderId
    Shipment --> OrderId
~~~

Sơ đồ là một mô hình khái niệm. Cardinality chính xác phải theo quy tắc của use case; ví dụ Order có thể có 0 dòng khi còn Draft nhưng phải có ít nhất 1 dòng khi submit.

### 6.2. Tách theo trách nhiệm

| Khái niệm | Trách nhiệm | Kiểu mô hình gợi ý |
|---|---|---|
| Order | Trạng thái và quy tắc của đơn | Aggregate Root |
| OrderLine | Sản phẩm, số lượng, giá đã chốt của dòng | Entity bên trong Order |
| Quantity | Giá trị số lượng hợp lệ | Value Object |
| Money | Số tiền và currency | Value Object |
| ShippingAddress | Địa chỉ giao hàng của đơn | Value Object |
| Payment | Trạng thái và giao dịch thanh toán | Aggregate riêng |
| Shipment | Vòng đời giao nhận | Aggregate riêng hoặc mô hình thuộc Fulfillment Context |
| PricingPolicy | Quy tắc chọn và tính giá | Policy/Domain Service |

### 6.3. Hành vi thay vì cờ trạng thái rời rạc

Thay vì lưu:

~~~java
boolean isSubmitted;
boolean isCancelled;
boolean isShipped;
boolean isRefunded;
~~~

Hãy dùng một trạng thái có ý nghĩa và hành vi chuyển trạng thái:

~~~java
public enum OrderStatus {
    DRAFT,
    SUBMITTED,
    CONFIRMED,
    SHIPPED,
    CANCELLED,
    COMPLETED
}
~~~

Một enum đơn giản vẫn có thể chưa đủ nếu mỗi trạng thái cho phép các hành vi khác nhau theo policy. Có thể dùng state transition method hoặc state machine để bảo vệ các chuyển đổi hợp lệ.

Không nên để các boolean độc lập tạo ra tổ hợp vô nghĩa như isCancelled = true và isShipped = true nếu nghiệp vụ không cho phép.

### 6.4. Quy tắc chuyển trạng thái tập trung ở aggregate

~~~java
public void cancel(CancellationReason reason) {
    if (status == OrderStatus.COMPLETED
            || status == OrderStatus.CANCELLED) {
        throw new OrderCannotBeCancelled(status);
    }
    if (status == OrderStatus.CONFIRMED
            && fulfillmentHasStarted()) {
        throw new CancellationRequiresReview();
    }

    status = OrderStatus.CANCELLED;
    domainEvents.add(new OrderCancelled(id, reason));
}
~~~

Đây là ví dụ minh họa; nếu fulfillment được sở hữu bởi context khác, Order không nên tự truy cập object Shipment để kiểm tra. Application service có thể cung cấp một quyết định/giá trị đã được xác minh hoặc use case phối hợp qua hợp đồng phù hợp. Không đưa dependency xuyên context vào aggregate chỉ để tiện gọi.

## 7. Tách theo invariant và consistency boundary

### 7.1. Câu hỏi quan trọng: điều gì phải đúng ngay lập tức?

Nếu OrderLine thay đổi thì tổng tiền Order phải được tính nhất quán theo quy tắc đơn. Đây có thể là invariant nội bộ của Order.

Nhưng khi Order được submit, Inventory cần giữ chỗ hàng. Order và Inventory có thể thuộc hai aggregate hoặc hai Bounded Context khác nhau. Việc giữ chỗ có thể diễn ra sau đó qua một quy trình bất đồng bộ.

Hãy phân biệt:

- Invariant cần được bảo vệ đồng bộ trong một aggregate.
- Quy tắc phối hợp giữa các aggregate trong một transaction cục bộ.
- Quy trình xuyên Bounded Context cần eventual consistency, retry hoặc compensation.

### 7.2. Aggregate quá lớn

Nếu một aggregate chứa Customer, Order, Payment, Inventory, Shipment và Invoice chỉ để có thể cập nhật trong một transaction, nó sẽ:

- Tải object graph lớn.
- Tăng contention khi nhiều người cập nhật.
- Kéo nhiều quy tắc không liên quan vào cùng nơi.
- Khó triển khai song song theo team hoặc service.
- Khiến thay đổi một phần ảnh hưởng đến phần còn lại.

Hãy tách theo invariant và quyền sở hữu. Dùng ID, domain event hoặc application workflow để phối hợp các aggregate độc lập.

### 7.3. Aggregate quá nhỏ

Tách mỗi field hoặc mỗi bảng thành một aggregate cũng gây vấn đề:

- Một hành vi nghiệp vụ cần nhiều lần tải/lưu.
- Invariant bị chia ra và khó bảo vệ.
- Nhiều transaction hoặc event không cần thiết.
- Application service phải điều phối quá nhiều chi tiết.

Ranh giới tốt giữ các phần cần thay đổi cùng nhau ở gần nhau và cho phép các phần độc lập thay đổi riêng.

### 7.4. Transaction không phải tiêu chí duy nhất

Một database transaction có thể cập nhật nhiều aggregate nếu nghiệp vụ cần và cùng một database hỗ trợ. Nhưng nếu nhiều aggregate thường xuyên cần thay đổi cùng nhau để giữ một invariant, cần xem lại mô hình. Ngược lại, không phải mọi thay đổi phải cùng transaction chỉ vì chúng diễn ra trong một use case.

Chọn consistency boundary theo cam kết nghiệp vụ; sau đó mới chọn cách thực thi bằng transaction, locking, event hoặc Saga.

## 8. Quan hệ giữa các Bounded Context

### 8.1. Không chia sẻ một mô hình chung cho mọi context

Một từ như Customer có thể mang ý nghĩa khác nhau:

- Sales quan tâm hồ sơ mua hàng và phân khúc.
- Billing quan tâm thông tin xuất hóa đơn và nghĩa vụ thanh toán.
- Support quan tâm lịch sử yêu cầu hỗ trợ.

Các context có thể dùng chung Customer ID hoặc một số dữ liệu tham chiếu, nhưng không nhất thiết chia sẻ cùng một Customer class hay cùng một aggregate.

### 8.2. Dùng contract rõ ràng giữa context

Ordering có thể phát OrderSubmitted với order ID, buyer reference, các dòng hàng đã chốt và thông tin cần cho Inventory. Inventory không cần nhận toàn bộ object graph của Order.

Hợp đồng nên xác định:

- Event/command name.
- Identity của đối tượng.
- Field bắt buộc và tùy chọn.
- Đơn vị đo, currency và timezone.
- Version schema.
- Ngữ nghĩa thời điểm.
- Chính sách retry và duplicate.

### 8.3. Anti-Corruption Layer

Khi một context tích hợp với mô hình ngoài có ngôn ngữ hoặc semantics khác, Anti-Corruption Layer chuyển đổi contract đó thành mô hình nội bộ.

Ví dụ, hệ thống vận chuyển bên ngoài dùng mã trạng thái IN_TRANSIT, DELIVERED, EXCEPTION. Fulfillment Context có thể ánh xạ chúng sang các trạng thái và thuật ngữ nội bộ phù hợp.

Không để tên field, enum và semantics của nhà cung cấp lan vào domain model chỉ vì API mapping tiện lợi.

### 8.4. Reference bằng ID qua ranh giới

Một aggregate thường chỉ giữ ID của aggregate khác thay vì object reference trực tiếp. Điều này:

- Tránh tải graph xuyên nhiều ranh giới.
- Làm rõ quyền sở hữu.
- Giảm coupling về vòng đời.
- Giúp thay đổi persistence hoặc service boundary dễ hơn.

Nếu cần dữ liệu từ context khác, dùng read model, local projection hoặc contract/API phù hợp. Không truy cập trực tiếp database của context khác.

## 9. Thiết kế module và package theo khái niệm

### 9.1. Nhóm code theo năng lực nghiệp vụ

Thay vì gom tất cả Entity vào một package toàn cục:

~~~text
domain/
  entities/
  valueobjects/
  services/
  repositories/
~~~

Có thể nhóm theo khái niệm hoặc subdomain:

~~~text
ordering/
  order/
    Order.java
    OrderLine.java
    OrderStatus.java
    OrderRepository.java
  pricing/
    PriceVersion.java
    Money.java
    PricingPolicy.java
  fulfillment/
    Shipment.java
    ShipmentStatus.java
~~~

Cấu trúc cụ thể phụ thuộc module và bounded context. Điều quan trọng là code liên quan đến một khái niệm có thể được tìm thấy cùng nhau, trong khi phụ thuộc giữa các module có hướng rõ ràng.

### 9.2. Giữ hướng phụ thuộc có chủ đích

Domain model không nên phụ thuộc vào controller, ORM repository implementation, HTTP client hoặc message broker.

Một hướng phụ thuộc thường gặp:

~~~mermaid
flowchart TD
    A["Inbound Adapter: REST / Message"] --> B["Application Use Case"]
    B --> C["Domain Model"]
    B --> D["Ports"]
    E["Infrastructure Adapters: JPA / Broker / HTTP"] --> D
~~~

Application layer điều phối use case. Domain model diễn đạt quy tắc. Infrastructure implement các port để lưu trữ hoặc giao tiếp bên ngoài.

### 9.3. Repository theo aggregate root

Repository thường cung cấp cách tải và lưu aggregate root. Không cần tạo repository cho mọi Value Object hoặc mọi bảng con nếu chúng không có vòng đời độc lập.

Ví dụ, OrderLine được truy cập qua OrderRepository nếu nó thuộc Order aggregate. Một Payment aggregate độc lập có thể có PaymentRepository riêng.

### 9.4. Không để ORM mapping quyết định mô hình

JPA có thể cần field, constructor hoặc annotation để mapping. Những yêu cầu đó không nên quyết định khái niệm nghiệp vụ.

Có thể dùng persistence entity riêng và mapper nếu domain model cần giữ sự độc lập cao. Với hệ thống đơn giản, có thể dùng chung class nếu mapping không làm méo domain behavior. Quyết định dựa trên độ phức tạp và nhu cầu thay đổi, không phải quy tắc tuyệt đối.

## 10. Tách policy và quy tắc biến thiên

### 10.1. Tránh nhánh điều kiện tích lũy

Một phương thức tính phí vận chuyển có thể dần trở thành:

~~~java
if (customer.isVip() && order.total() > threshold) {
    // Miễn phí.
} else if (order.isInternational() && order.weight() > limit) {
    // Phí đặc biệt.
} else if (campaignEnabled && ...) {
    // Quy tắc khuyến mãi.
}
~~~

Nếu các quy tắc thuộc những chính sách khác nhau và thay đổi độc lập, hãy tách chúng thành policy có tên.

### 10.2. Strategy cho các biến thể thuật toán

~~~java
public interface ShippingFeePolicy {
    Money calculate(ShippingRequest request);
}

public final class DomesticShippingFeePolicy
        implements ShippingFeePolicy {
    @Override
    public Money calculate(ShippingRequest request) {
        // Quy tắc tính phí nội địa.
        return request.baseFee();
    }
}
~~~

Strategy phù hợp khi có nhiều thuật toán thay thế cùng một hợp đồng. Không nên tạo interface cho một phương thức không có biến thể hoặc nhu cầu thay thế thực tế.

### 10.3. Specification cho điều kiện có thể kết hợp

~~~java
public interface Specification<T> {
    boolean isSatisfiedBy(T candidate);
}
~~~

Các Specification có thể kết hợp bằng AND, OR hoặc NOT nếu nghiệp vụ cần. Nếu caller cần giải thích lý do không đạt, có thể dùng kết quả đánh giá có reason code thay vì chỉ boolean.

### 10.4. Tránh truyền một túi tham số mơ hồ

Không nên dùng Map<String, Object> hoặc một request object có hàng chục field nullable để đại diện mọi biến thể policy. Hãy tạo kiểu đầu vào rõ theo use case hoặc dùng sealed type khi các trường hợp khác nhau về cấu trúc.

## 11. Làm cho trạng thái hợp lệ dễ biểu diễn

### 11.1. Tránh boolean soup

Nhiều boolean độc lập có thể tạo ra rất nhiều tổ hợp trạng thái, trong đó phần lớn không hợp lệ.

Ví dụ, bốn boolean tạo ra 16 tổ hợp. Nếu domain chỉ cho phép 5 trạng thái, phần còn lại cần bị loại bỏ.

Thay vào đó, dùng enum, sealed interface hoặc state machine để chỉ biểu diễn các trạng thái hợp lệ.

### 11.2. Dùng kiểu riêng cho trường bắt buộc

Nếu một hành vi chỉ được thực hiện sau khi có địa chỉ hợp lệ, có thể tạo một type biểu diễn địa chỉ đã xác thực hoặc dùng state transition method để bảo đảm điều kiện trước khi chuyển trạng thái.

Không cần tạo type mới cho mọi field; chỉ làm vậy khi nó giúp loại bỏ một trạng thái sai có ý nghĩa.

### 11.3. Phân biệt chưa biết, không áp dụng và không có

Một null không giải thích được lý do thiếu dữ liệu. Tùy ngữ nghĩa, có thể dùng:

- Optional<T> cho giá trị có thể không tồn tại trong kết quả truy vấn.
- Một trạng thái rõ như NotApplicable.
- Sealed result cho các nhánh Known, Unknown, NotProvided.
- Một hành vi yêu cầu bổ sung dữ liệu trước khi chuyển trạng thái.

Không dùng Optional như field mặc định cho mọi thuộc tính Entity. Nó phù hợp hơn ở ranh giới API hoặc kết quả truy vấn; domain model nên diễn đạt rõ ý nghĩa của việc thiếu dữ liệu.

## 12. Ví dụ refactor từng bước

Giả sử lớp Order hiện có:

- Customer name và address.
- Các dòng hàng.
- Trạng thái payment.
- Trạng thái shipment.
- Các boolean điều khiển khuyến mãi và giao hàng.
- Một phương thức calculateTotal() dài.

Có thể refactor theo từng bước nhỏ.

### Bước 1: Đặt tên cho các giá trị

Thay BigDecimal total bằng Money, int quantity bằng Quantity, các chuỗi trạng thái bằng enum hoặc kiểu riêng. Điều này làm rõ đơn vị và invariant.

### Bước 2: Tách Value Object

Tạo ShippingAddress, BillingAddress, Money, Quantity và PriceSnapshot. Chuyển validation vào constructor hoặc factory phù hợp.

### Bước 3: Tách Entity có identity và vòng đời riêng

Nếu Payment có nhiều lần thử, trạng thái và đối soát riêng, tạo Payment aggregate. Nếu Shipment có nhiều lần giao và lịch sử tracking, tạo Shipment aggregate.

### Bước 4: Xác định Aggregate Root

Order quản lý OrderLine và các quy tắc submit/cancel. Payment và Shipment được truy cập qua repository hoặc ID riêng.

### Bước 5: Tách quy tắc biến thiên

Đưa logic định giá hoặc vận chuyển thành PricingPolicy/ShippingFeePolicy khi chúng có quy tắc riêng hoặc nhiều biến thể.

### Bước 6: Định nghĩa quan hệ

Ghi rõ:

- Order có 0..n OrderLine khi Draft, tối thiểu 1 khi Submit.
- Order giữ CustomerId, không sở hữu vòng đời Customer.
- Order giữ snapshot ShippingAddress sau khi xác nhận.
- Payment tham chiếu OrderId.
- Shipment tham chiếu OrderId và được Fulfillment Context sở hữu.

### Bước 7: Tách workflow xuyên ranh giới

Application service điều phối submit Order, lưu trạng thái và phát event. Inventory/Payment/Fulfillment xử lý trong context riêng. Nếu cần độ tin cậy giữa database và broker, dùng Outbox.

### Bước 8: Bảo vệ hành vi bằng test

Viết test cho invariant của Order trước khi tách. Sau refactor, giữ nguyên hành vi đã cam kết và bổ sung test cho ranh giới mới.

~~~mermaid
flowchart TD
    A["Order lớn, nhiều trách nhiệm"] --> B["Tìm khái niệm và invariant"]
    B --> C["Tách Value Object"]
    C --> D["Tách Entity có vòng đời riêng"]
    D --> E["Xác định Aggregate Boundary"]
    E --> F["Định nghĩa quan hệ và contract"]
    F --> G["Tách policy/workflow biến thiên"]
    G --> H["Kiểm thử và triển khai từng bước"]
~~~

Không cần thực hiện toàn bộ trong một lần. Refactor theo lát cắt có thể kiểm chứng giúp giảm rủi ro và giữ được khả năng phát hành liên tục.

## 13. Làm rõ quan hệ trong API và persistence

### 13.1. API không nên vô tình phơi bày object graph

Trả trực tiếp một Entity có thể làm API phụ thuộc vào:

- Cấu trúc nội bộ của domain.
- Lazy loading và proxy của ORM.
- Quan hệ vòng tròn.
- Field không dành cho consumer.
- Thay đổi persistence mapping.

Hãy thiết kế DTO theo nhu cầu của use case. DTO có thể chứa ID reference, summary hoặc snapshot thay vì toàn bộ object liên quan.

### 13.2. Phân biệt command và query

Command diễn đạt ý định thay đổi:

- SubmitOrder.
- ChangeShippingAddress.
- CancelOrder.

Query lấy dữ liệu:

- GetOrderDetails.
- ListOrders.
- FindApplicablePrice.

Command nên gọi hành vi domain để bảo vệ invariant. Query có thể dùng projection tối ưu cho màn hình mà không cần tải toàn bộ aggregate.

### 13.3. Relationship mapping không thay thế ownership

JPA OneToMany, ManyToOne hoặc cascade chỉ mô tả mapping và hành vi persistence. Chúng không tự xác định:

- Ai sở hữu nghiệp vụ.
- Ai được phép thay đổi.
- Có nên xóa cascade không.
- Hai object có cùng aggregate không.
- Có thể cập nhật độc lập không.

Chỉ cấu hình cascade remove khi vòng đời của object con thực sự phụ thuộc vào object cha theo quy tắc nghiệp vụ và retention.

### 13.4. Dùng ID reference để tránh graph quá rộng

Nếu một Order cần biết CustomerId, lưu ID thường đủ. Khi hiển thị tên khách hàng, application query có thể lấy CustomerSummary qua một port hoặc read model.

Đừng tải Customer cùng tất cả Order, Payment và Shipment chỉ để hiển thị một trang chi tiết. Fetch plan và DTO cần phục vụ use case cụ thể.

## 14. Phân rã module nhưng tránh overengineering

### 14.1. Một class mới phải giải quyết một vấn đề có thật

Tạo một class chỉ để chuyển tiếp một lời gọi mà không thêm ngữ nghĩa, invariant hoặc điểm thay đổi có thể làm code khó điều hướng hơn.

Trước khi tách, hãy xác định:

- Tên khái niệm mới có xuất hiện trong ngôn ngữ nghiệp vụ không?
- Nó có trách nhiệm hoặc lý do thay đổi riêng không?
- Có invariant cần bảo vệ riêng không?
- Có thể kiểm thử độc lập có ý nghĩa không?
- Nó có làm giảm coupling hay chỉ chuyển coupling sang interface khác?

### 14.2. Tránh micro-class và interface không cần thiết

Không cần tạo interface cho mọi class, factory cho mọi constructor hoặc service cho mọi hành vi. Dùng abstraction khi có ranh giới, biến thể, dependency bên ngoài hoặc nhu cầu thay thế.

Một Value Object nhỏ có thể là record. Một hành vi thuộc Entity có thể là method trực tiếp. Một port có ích khi domain/application cần tách khỏi implementation hạ tầng.

### 14.3. Tránh shared kernel quá rộng

Một package `common` hoặc `shared` chứa mọi kiểu dữ liệu của nhiều context dễ trở thành nơi phụ thuộc vòng và thay đổi lan truyền.

Chỉ chia sẻ những khái niệm thực sự ổn định và có cùng ngữ nghĩa. Nếu hai context dùng cùng một từ nhưng khác semantics, hãy giữ mô hình riêng và chuyển đổi qua contract.

### 14.4. Tách theo khả năng thay đổi

Một phần thường thay đổi vì:

- Chính sách pháp lý.
- Cách tính giá.
- Nhà cung cấp tích hợp.
- Quy trình vận hành.
- Kênh giao tiếp.
- Cách lưu trữ hoặc truy vấn.

Nếu các phần có lý do thay đổi khác nhau, chúng nên có ranh giới phù hợp. Nhưng đừng tách một quy tắc chỉ vì dự đoán mơ hồ rằng tương lai có thể thay đổi.

## 15. Dấu hiệu mô hình đã có quan hệ rõ ràng

Một người mới đọc code có thể trả lời được:

- Object này đại diện cho khái niệm nghiệp vụ nào?
- Identity của nó là gì?
- Nó sở hữu những object nào?
- Những object nào chỉ được tham chiếu?
- Trạng thái nào hợp lệ?
- Hành vi nào làm thay đổi trạng thái?
- Invariant nào được bảo vệ tại đây?
- Quy tắc nào thuộc policy hoặc service khác?
- Thay đổi cần transaction đồng bộ hay event bất đồng bộ?
- Khi xóa, hết hạn hoặc thay version thì quan hệ được xử lý ra sao?

Nếu câu trả lời chỉ nằm trong đầu người viết hoặc một tài liệu ngoài code, mô hình chưa diễn đạt đủ rõ.

## 16. Những sai lầm thường gặp

**Tách class theo số field.** Một class nhỏ chưa chắc có cohesion. Hãy tách theo khái niệm, invariant, vòng đời và quyền sở hữu.

**Tạo một God Object.** Một object quản lý quá nhiều quy trình làm thay đổi lan rộng. Tách các khái niệm có vòng đời và quy tắc riêng.

**Tách mọi bảng thành một aggregate.** Aggregate boundary dựa trên invariant, không phải số bảng hoặc foreign key.

**Đưa mọi object liên quan vào cùng aggregate.** Quan hệ không đồng nghĩa ownership. Dùng ID reference khi object có vòng đời riêng.

**Chỉ đổi field thành class wrapper.** Wrapper không tạo giá trị nếu không có ngữ nghĩa, invariant hoặc hành vi rõ ràng.

**Dùng boolean cho nhiều trạng thái.** Các cờ độc lập tạo ra tổ hợp mâu thuẫn. Dùng trạng thái có ý nghĩa và transition hợp lệ.

**Để controller kiểm tra invariant.** Controller là adapter. Hành vi domain phải bảo vệ trạng thái dù được gọi từ API, job hay message consumer.

**Đưa mọi logic vào Domain Service.** Service không phải nơi chứa logic không biết đặt đâu. Hãy đặt hành vi vào Entity/Value Object khi nó thuộc về khái niệm đó.

**Chia sẻ Entity giữa Bounded Context.** Context có thể cùng tham chiếu identity nhưng cần giữ mô hình và ngôn ngữ riêng.

**Để ORM cascade quyết định vòng đời.** Mapping persistence không thay thế quy tắc ownership của domain.

**Tạo interface và factory hàng loạt.** Abstraction không có lý do cụ thể làm tăng indirection. Chỉ tạo khi cần ranh giới hoặc biến thể.

**Tách module nhưng vẫn phụ thuộc vòng.** Package mới không có ích nếu các module vẫn gọi ngược nhau tùy tiện. Đặt hướng phụ thuộc và contract rõ.

## 17. Quy trình phân rã mô hình

1. Thu thập thuật ngữ và hành vi từ chuyên gia nghiệp vụ.
2. Xác định khái niệm, identity, giá trị và vòng đời.
3. Liệt kê invariant và nơi cần bảo vệ chúng.
4. Nhóm các object cần thay đổi cùng nhau.
5. Tách Value Object để đóng gói giá trị và quy tắc.
6. Tách Entity khi có identity và lifecycle riêng.
7. Xác định Aggregate Root và consistency boundary.
8. Làm rõ cardinality, optionality, ownership, direction và deletion semantics.
9. Dùng ID reference qua aggregate hoặc Bounded Context khi phù hợp.
10. Tách policy/specification/domain service cho quy tắc có trách nhiệm riêng.
11. Định nghĩa command, query và integration contract.
12. Tổ chức module/package theo khái niệm và hướng phụ thuộc.
13. Refactor từng lát cắt, giữ hành vi bằng test.
14. Đánh giá lại khi invariant, quyền sở hữu hoặc ngôn ngữ nghiệp vụ thay đổi.

## 18. Checklist đánh giá mô hình

**Khái niệm**

- Mỗi class/module có tên diễn đạt khái niệm nghiệp vụ không?
- Entity và Value Object đã được phân biệt theo identity chưa?
- Các thuật ngữ có nhất quán với ngôn ngữ của Bounded Context không?
- Có object nào đang gom nhiều lý do thay đổi không?

**Invariant và vòng đời**

- Invariant quan trọng được bảo vệ ở đâu?
- Các trạng thái không hợp lệ có thể biểu diễn được không?
- Hành vi thay đổi trạng thái có tên rõ ràng không?
- Vòng đời của object con có phụ thuộc object cha không?

**Quan hệ**

- Cardinality và optionality có rõ không?
- Ownership và hướng truy cập có rõ không?
- Quan hệ dùng object reference hay ID, và vì sao?
- Thời điểm hiệu lực và snapshot có được giữ khi cần không?
- Delete/cascade có đúng với vòng đời nghiệp vụ không?

**Ranh giới và thay đổi**

- Aggregate có bảo vệ đúng consistency boundary không?
- Có aggregate nào quá lớn hoặc quá nhỏ không?
- Quy tắc biến thiên có policy riêng khi cần không?
- Các Bounded Context có giữ mô hình riêng không?
- Module có hướng phụ thuộc rõ và không có vòng không?

**Khả năng kiểm thử**

- Có thể kiểm thử invariant mà không cần khởi động toàn bộ ứng dụng không?
- Có thể kiểm thử các transition hợp lệ và không hợp lệ không?
- Có test cho quan hệ bắt buộc, tùy chọn và giới hạn số lượng không?
- Có test cho duplicate event hoặc cập nhật đồng thời khi liên quan không?
- Refactor có giữ nguyên hành vi đã cam kết không?

Thiết kế dễ thay đổi không đến từ việc chia mọi thứ thành những class nhỏ nhất. Nó đến từ việc mỗi khái niệm có trách nhiệm và quyền sở hữu rõ ràng, các quan hệ được mô hình hóa bằng kiểu và hợp đồng tường minh, còn invariant được bảo vệ tại đúng ranh giới. Khi một quy tắc thay đổi, đội phát triển có thể tìm đúng phần cần sửa và dự đoán được những phần bị ảnh hưởng.

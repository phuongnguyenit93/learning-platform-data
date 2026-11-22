# Model nghiệp vụ trong thiết kế hướng miền

Trong ứng dụng MVC, phần Model thường được hiểu là dữ liệu và hành vi mà ứng dụng cần để phục vụ giao diện. Khi hệ thống có nhiều quy tắc nghiệp vụ, nhiều trạng thái và nhiều cách tương tác, việc gom mọi dữ liệu vào các lớp đơn giản rồi để Controller hoặc Service thao tác trực tiếp sẽ khiến quy tắc bị phân tán. Một thay đổi nhỏ có thể phải sửa ở nhiều endpoint, và rất khó biết đâu là nơi chịu trách nhiệm bảo vệ tính đúng đắn của nghiệp vụ.

Thiết kế hướng miền (Domain-Driven Design - DDD) khuyến khích xây dựng một mô hình nghiệp vụ thể hiện ngôn ngữ, khái niệm và quy tắc của lĩnh vực đang giải quyết. Domain Model không chỉ chứa dữ liệu; nó còn thể hiện hành vi và bảo vệ các bất biến của nghiệp vụ. Trong MVC, Controller tiếp nhận tương tác, Application điều phối ca sử dụng, Domain Model thực thi quy tắc, còn Repository và adapter đảm nhiệm lưu trữ.

Bài học này làm rõ ý nghĩa của Model trong MVC, phân biệt Domain Model với View Model và persistence model, giới thiệu các thành phần cốt lõi của DDD và minh họa cách tổ chức một mô hình đơn hàng có hành vi rõ ràng.

Các ví dụ Java dùng record và cú pháp của Java 17 trở lên. Import, một số kiểu command/query và cấu hình framework được lược bỏ để tập trung vào mô hình; trong dự án, mỗi public top-level type được đặt trong file phù hợp.

## 1. Mục tiêu

Sau bài học, bạn có thể:

- Giải thích Domain Model và vai trò của nó trong thiết kế hướng miền.
- Phân biệt MVC Model, Domain Model, View Model, DTO và ORM Entity.
- Sử dụng ubiquitous language và bounded context để xác định phạm vi mô hình.
- Nhận biết Entity, Value Object, Aggregate và Aggregate Root.
- Đặt bất biến và hành vi nghiệp vụ trong đúng đối tượng.
- Phân biệt Application Service với Domain Service.
- Sử dụng Repository và Domain Event mà không làm rò rỉ framework.
- Kết nối Domain Model với luồng request của MVC.
- Kiểm thử quy tắc nghiệp vụ độc lập với HTTP và database.

## 2. Model trong MVC và Domain Model trong DDD

Từ Model trong MVC có phạm vi khá rộng. Nó thường chỉ phần dữ liệu và trạng thái mà ứng dụng sử dụng để tạo View hoặc xử lý tương tác. Tùy framework, Model còn có thể là một object chứa các thuộc tính được Controller đưa sang template.

Domain Model có nghĩa cụ thể hơn: đó là mô hình khái niệm của một miền nghiệp vụ, bao gồm các đối tượng, quan hệ, hành vi, trạng thái và quy tắc. Domain Model là một phần quan trọng của Model theo nghĩa MVC khi ứng dụng có nghiệp vụ đáng kể, nhưng hai thuật ngữ không đồng nghĩa.

| Khái niệm | Mục đích | Ví dụ |
|---|---|---|
| MVC Model | Dữ liệu và trạng thái mà ứng dụng dùng để xử lý/hiển thị | Model attributes trong Spring MVC |
| Domain Model | Biểu diễn khái niệm và quy tắc nghiệp vụ | Order, Money, OrderLine |
| View Model | Cấu trúc dữ liệu tối ưu cho một màn hình | OrderDetailView |
| Request DTO / Form | Hợp đồng dữ liệu nhận từ client | CreateOrderRequest |
| ORM Entity | Cấu trúc được ORM ánh xạ với persistence | OrderJpaEntity |

Trong Spring MVC, tham số org.springframework.ui.Model là một vùng chứa thuộc tính để View sử dụng. Nó không phải Domain Model và không nên trở thành nơi lưu các quy tắc như tính giá, xác nhận đơn hoặc kiểm tra trạng thái.

Một ứng dụng nhỏ có thể dùng cùng một lớp cho Domain Entity và JPA Entity nếu mô hình đơn giản. Khi quy tắc nghiệp vụ phát triển, việc tách Domain Model khỏi cấu trúc persistence và presentation giúp mỗi mô hình thay đổi theo lý do riêng.

## 3. Vì sao cần mô hình hóa miền nghiệp vụ?

Hãy xem một chức năng tạo đơn hàng. Một cách triển khai đơn giản có thể là:

~~~java
@PostMapping("/orders")
public String create(CreateOrderForm form) {
    OrderEntity order = new OrderEntity();
    order.setCustomerId(form.getCustomerId());
    order.setQuantity(form.getQuantity());
    order.setStatus("NEW");
    order.setTotal(form.getPrice() * form.getQuantity());

    orderRepository.save(order);
    return "redirect:/orders";
}
~~~

Đoạn code có vẻ ngắn, nhưng nhiều quyết định nghiệp vụ đang nằm trong Controller:

- Số lượng có được phép bằng 0 hoặc âm không?
- Giá lấy từ biểu mẫu hay từ danh mục sản phẩm?
- Đơn có thể được tạo nếu sản phẩm ngừng bán không?
- Tổng tiền được làm tròn theo quy tắc nào?
- Đơn có thể xác nhận ngay sau khi tạo không?
- Khi hủy đơn, tồn kho và hoàn tiền được xử lý ra sao?

Nếu API, trang quản trị và tác vụ nền đều tự viết các quy tắc tương tự, chúng có thể dần không nhất quán. Domain Model đưa các quy tắc liên quan về gần dữ liệu mà chúng bảo vệ.

~~~mermaid
flowchart TD
    UI["HTML / REST / Mobile"]
    Controller["MVC Controller"]
    Application["Application Service"]
    Domain["Domain Model<br/>Entity / Value Object / Aggregate"]
    Repository["Repository Port"]
    Adapter["Persistence Adapter"]
    DB[("Database")]

    UI --> Controller
    Controller -->|"Command / Query"| Application
    Application --> Domain
    Application --> Repository
    Repository -. "implemented by" .-> Adapter
    Adapter --> DB
~~~

Domain Model giúp:

- Tập trung quy tắc nghiệp vụ vào nơi có ý nghĩa.
- Bảo vệ trạng thái hợp lệ của đối tượng.
- Dùng chung hành vi giữa nhiều giao diện và điểm vào.
- Giảm phụ thuộc vào HTTP, template, ORM và database.
- Làm cho kiểm thử nghiệp vụ nhanh và có mục tiêu.

Không phải ứng dụng nào cũng cần một mô hình Domain phức tạp. Với màn hình CRUD đơn giản, các DTO và thao tác persistence trực tiếp có thể đủ. DDD phát huy giá trị khi quy tắc và ngôn ngữ nghiệp vụ có độ phức tạp đáng kể.

## 4. Bắt đầu từ ngôn ngữ chung (Ubiquitous Language)

DDD khuyến khích nhóm phát triển và chuyên gia nghiệp vụ dùng cùng một ngôn ngữ để mô tả hệ thống. Tên lớp, phương thức, sự kiện, tài liệu và trao đổi nghiệp vụ nên phản ánh những khái niệm đã thống nhất.

Ví dụ trong một hệ thống bán hàng:

- Customer là người đặt hàng.
- Order là đơn hàng được tạo từ yêu cầu mua.
- OrderLine là một dòng hàng trong đơn.
- Product là mặt hàng được cung cấp.
- Reservation là việc giữ tồn kho.
- Confirmation là thao tác xác nhận đơn.

Tên gọi phải phản ánh cách miền nghiệp vụ hiểu sự việc. Nếu một từ như Account có nghĩa khác nhau giữa bộ phận kế toán và bộ phận khách hàng, không nên cố ép cả hai dùng một mô hình duy nhất mà không làm rõ ngữ cảnh.

### 4.1. Mô hình hóa động từ, không chỉ danh từ

Khi phân tích nghiệp vụ, hãy hỏi:

- Ai thực hiện hành động?
- Hành động tác động lên đối tượng nào?
- Điều kiện nào phải đúng trước khi hành động?
- Trạng thái nào thay đổi?
- Sự kiện nào được phát sinh sau hành động?
- Trường hợp nào phải bị từ chối?

Ví dụ, thay vì chỉ tạo lớp Order có các setter, hãy xác định các hành vi: addLine, removeLine, confirm, cancel và markPaid. Những động từ này giúp làm rõ nơi cần bảo vệ bất biến.

### 4.2. Quy tắc phải có ngôn ngữ rõ

Một quy tắc mơ hồ như "đơn hợp lệ" cần được chuyển thành điều kiện cụ thể:

- Đơn phải có ít nhất một dòng hàng.
- Mỗi dòng có số lượng dương.
- Mỗi sản phẩm phải được phép bán.
- Chỉ đơn ở trạng thái DRAFT mới được xác nhận.
- Tổng tiền phải được tính từ giá và số lượng theo quy tắc tiền tệ.

Khi quy tắc chưa rõ, cần trao đổi với người hiểu nghiệp vụ thay vì tự suy đoán rồi mã hóa thành điều kiện kỹ thuật.

## 5. Bounded Context và ranh giới của mô hình

Trong một tổ chức lớn, cùng một khái niệm có thể mang ý nghĩa khác nhau giữa các miền. Bounded Context xác định ranh giới mà trong đó một mô hình và ngôn ngữ có ý nghĩa nhất quán.

Ví dụ một hệ thống thương mại có thể có:

- Sales: quản lý giỏ hàng, đơn hàng và giá bán.
- Inventory: quản lý tồn kho và giữ hàng.
- Payment: quản lý giao dịch, hoàn tiền và phương thức thanh toán.
- Shipping: quản lý kiện hàng và vận chuyển.

Sales có thể cần Product với tên hiển thị và giá bán; Inventory cần SKU và số lượng khả dụng; Shipping cần kích thước, trọng lượng và địa chỉ giao hàng. Không nhất thiết dùng một lớp Product chung cho mọi context.

~~~mermaid
flowchart LR
    Sales["Sales Context<br/>Order / ProductOffer"]
    Inventory["Inventory Context<br/>StockItem / Reservation"]
    Payment["Payment Context<br/>Payment / Refund"]
    Shipping["Shipping Context<br/>Shipment / Address"]

    Sales -->|"Reserve request"| Inventory
    Sales -->|"Payment request"| Payment
    Sales -->|"Fulfillment request"| Shipping
~~~

Mỗi context sở hữu mô hình và quy tắc riêng. Chúng giao tiếp qua API, message hoặc hợp đồng tích hợp. Một context có thể dùng Anti-Corruption Layer để chuyển đổi mô hình bên ngoài sang ngôn ngữ nội bộ, tránh để khái niệm từ hệ thống khác làm biến dạng Domain Model của mình.

Không nên chia bounded context chỉ theo package hoặc team một cách máy móc. Ranh giới cần xuất phát từ ngôn ngữ, quy tắc và quyền sở hữu dữ liệu/nghiệp vụ.

## 6. Các thành phần cốt lõi của Domain Model

DDD chiến thuật cung cấp một số building block thường dùng:

| Thành phần | Đặc điểm | Câu hỏi cần trả lời |
|---|---|---|
| Entity | Có định danh và vòng đời | Đối tượng này là ai/cái nào theo thời gian? |
| Value Object | Được xác định bằng giá trị, thường bất biến | Giá trị này có ý nghĩa và ràng buộc gì? |
| Aggregate | Nhóm đối tượng được bảo vệ bởi một ranh giới nhất quán | Bất biến nào cần đúng cùng nhau? |
| Aggregate Root | Cửa vào duy nhất để thao tác aggregate từ bên ngoài | Ai kiểm soát thay đổi bên trong? |
| Domain Service | Quy tắc nghiệp vụ không tự nhiên thuộc về một Entity/Value Object | Hành vi này cần phối hợp khái niệm nào? |
| Domain Event | Sự kiện có ý nghĩa nghiệp vụ đã xảy ra | Điều gì đã xảy ra trong miền? |
| Repository | Hợp đồng truy xuất và lưu aggregate | Làm sao tải/lưu đối tượng nghiệp vụ? |
| Factory | Đóng gói cách tạo đối tượng phức tạp | Điều kiện tạo hợp lệ là gì? |

Không phải domain nào cũng cần đủ mọi thành phần. Hãy dùng một building block khi nó giúp diễn đạt quy tắc rõ hơn.

## 7. Entity: đối tượng có định danh và vòng đời

Entity được nhận diện bằng identity thay vì chỉ bằng các thuộc tính hiện tại. Hai đối tượng có cùng dữ liệu vẫn có thể là hai Entity khác nhau nếu định danh khác nhau.

Ví dụ, hai đơn hàng cùng khách hàng, cùng ngày và cùng tổng tiền vẫn là hai đơn khác nhau. Order ID xác định từng đơn.

~~~java
public final class OrderId {
    private final UUID value;

    public OrderId(UUID value) {
        this.value = Objects.requireNonNull(value);
    }

    public UUID value() {
        return value;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof OrderId id && value.equals(id.value);
    }

    @Override
    public int hashCode() {
        return value.hashCode();
    }
}
~~~

Các kiểu định danh và mã miền đơn giản khác có thể được biểu diễn bằng Value Object:

~~~java
public record CustomerId(String value) {
    public CustomerId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Customer ID is required");
        }
    }
}

public record ProductCode(String value) {
    public ProductCode {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Product code is required");
        }
    }
}
~~~

Một Entity thường:

- Có identity ổn định.
- Có vòng đời và trạng thái.
- Có hành vi thay đổi trạng thái theo quy tắc.
- Kiểm soát cách thay đổi các thuộc tính quan trọng.
- Không để bên ngoài tùy ý đưa nó vào trạng thái bất hợp lệ.

Không nên tạo Entity chỉ vì một bảng database tồn tại. Entity là khái niệm nghiệp vụ; bảng là chi tiết lưu trữ.

## 8. Value Object: mô hình hóa giá trị và ràng buộc

Value Object không có identity riêng; hai instance được xem là bằng nhau khi các giá trị cấu thành bằng nhau. Value Object thường bất biến, giúp tránh thay đổi ngoài ý muốn.

Ví dụ Money:

~~~java
public record Money(BigDecimal amount, Currency currency)
        implements Comparable<Money> {
    public Money {
        Objects.requireNonNull(amount);
        Objects.requireNonNull(currency);

        if (amount.signum() < 0) {
            throw new IllegalArgumentException(
                "Amount must not be negative"
            );
        }

        amount = amount.setScale(
            currency.getDefaultFractionDigits(),
            RoundingMode.HALF_EVEN
        );
    }

    public Money add(Money other) {
        requireSameCurrency(other);
        return new Money(amount.add(other.amount), currency);
    }

    public static Money zero(Currency currency) {
        return new Money(BigDecimal.ZERO, currency);
    }

    public static Money of(long amount, Currency currency) {
        return new Money(BigDecimal.valueOf(amount), currency);
    }

    @Override
    public int compareTo(Money other) {
        requireSameCurrency(other);
        return amount.compareTo(other.amount);
    }

    public Money multiply(int quantity) {
        if (quantity < 0) {
            throw new IllegalArgumentException(
                "Quantity must not be negative"
            );
        }
        return new Money(amount.multiply(BigDecimal.valueOf(quantity)), currency);
    }

    private void requireSameCurrency(Money other) {
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException(
                "Currencies must match"
            );
        }
    }
}
~~~

Money bảo vệ các quy tắc như số tiền không âm, độ chính xác thập phân và không cộng hai loại tiền khác nhau. Nếu dùng BigDecimal trực tiếp ở khắp nơi, mỗi lớp có thể tự chọn cách làm tròn hoặc so sánh không nhất quán.

Các phương thức zero, of và compareTo trong ví dụ giúp những đoạn code sau dùng cùng quy tắc tạo, so sánh Money. Một hệ thống thực tế cần quyết định chính sách scale và rounding theo loại tiền hoặc nghiệp vụ; không nên mặc định mọi loại tiền đều có cùng số chữ số thập phân.

Value Object phù hợp với:

- Money.
- Address.
- DateRange.
- EmailAddress.
- ProductCode.
- Quantity.
- Percentage.

Không nên biến mọi kiểu dữ liệu thành Value Object nếu chúng không có quy tắc hoặc ý nghĩa riêng. Mục tiêu là diễn đạt ngữ nghĩa và bảo vệ ràng buộc, không phải tạo lớp bọc cho mọi String.

### 8.1. So sánh Entity và Value Object

| Tiêu chí | Entity | Value Object |
|---|---|---|
| Định danh | Có identity | Không có identity riêng |
| So sánh | Theo identity | Theo giá trị |
| Vòng đời | Có thể thay đổi theo thời gian | Thường bất biến |
| Ví dụ | Order, Customer | Money, Address |
| Thay đổi | Qua hành vi được kiểm soát | Thường tạo instance mới |

## 9. Aggregate và Aggregate Root

Aggregate là một ranh giới nhất quán gồm một hoặc nhiều đối tượng domain. Aggregate Root là đối tượng gốc mà bên ngoài dùng để đọc và thay đổi aggregate.

Ví dụ:

~~~text
Order (Aggregate Root)
├── OrderLine
├── OrderLine
└── OrderLine
~~~

Nếu OrderLine chỉ có ý nghĩa trong một đơn hàng, bên ngoài không nên tải và thay đổi nó độc lập. Thay đổi dòng hàng cần đi qua Order để tổng tiền, số lượng và trạng thái được cập nhật nhất quán.

~~~java
public final class Order {
    private final OrderId id;
    private final CustomerId customerId;
    private final List<OrderLine> lines = new ArrayList<>();
    private final List<DomainEvent> domainEvents = new ArrayList<>();
    private OrderStatus status;
    private Money total;

    private Order(OrderId id, CustomerId customerId) {
        this.id = Objects.requireNonNull(id);
        this.customerId = Objects.requireNonNull(customerId);
        this.status = OrderStatus.DRAFT;
        this.total = Money.zero(Currency.getInstance("VND"));
    }

    public static Order create(OrderId id, CustomerId customerId) {
        return new Order(id, customerId);
    }

    public void addLine(
            ProductCode productCode,
            int quantity,
            Money unitPrice) {
        requireDraft();
        Objects.requireNonNull(unitPrice);

        if (!unitPrice.currency().equals(total.currency())) {
            throw new OrderRuleViolation(
                "All order lines must use the order currency"
            );
        }

        if (quantity <= 0) {
            throw new OrderRuleViolation("Quantity must be positive");
        }

        OrderLine line = new OrderLine(
            productCode,
            quantity,
            unitPrice
        );

        lines.add(line);
        recalculateTotal();
    }

    public void removeLine(ProductCode productCode) {
        requireDraft();

        boolean removed = lines.removeIf(
            line -> line.productCode().equals(productCode)
        );

        if (!removed) {
            throw new OrderRuleViolation("Order line does not exist");
        }

        recalculateTotal();
    }

    public void confirm(Instant now) {
        Objects.requireNonNull(now);
        requireDraft();

        if (lines.isEmpty()) {
            throw new OrderRuleViolation(
                "An order must contain at least one line"
            );
        }

        status = OrderStatus.CONFIRMED;
        domainEvents.add(new OrderConfirmed(id, customerId, now));
    }

    public void cancel() {
        if (status != OrderStatus.DRAFT
                && status != OrderStatus.CONFIRMED) {
            throw new OrderRuleViolation(
                "Order cannot be cancelled in this state"
            );
        }

        status = OrderStatus.CANCELLED;
    }

    private void requireDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new OrderRuleViolation(
                "Only a draft order can be changed"
            );
        }
    }

    private void recalculateTotal() {
        Currency currency = total.currency();
        total = lines.stream()
            .map(OrderLine::subtotal)
            .reduce(
                Money.zero(currency),
                Money::add
            );
    }

    public OrderId id() {
        return id;
    }

    public CustomerId customerId() {
        return customerId;
    }

    public List<OrderLine> lines() {
        return List.copyOf(lines);
    }

    public OrderStatus status() {
        return status;
    }

    public Money total() {
        return total;
    }

    public List<DomainEvent> domainEvents() {
        return List.copyOf(domainEvents);
    }

    public void clearDomainEvents() {
        domainEvents.clear();
    }
}
~~~

Ví dụ rút gọn giả định các dòng hàng dùng cùng currency và các kiểu Money, ProductCode, CustomerId, OrderLine, OrderRuleViolation được định nghĩa phù hợp. Hệ thống thực tế cần quy định rõ tiền tệ, chính sách giá, thuế, giảm giá và làm tròn.

Constructor minh họa chọn VND làm tiền tệ của đơn. Nếu miền hỗ trợ nhiều tiền tệ, hãy đưa Currency vào factory/constructor của Order và bảo vệ bất biến thống nhất tiền tệ ngay tại aggregate.

Các kiểu phụ trợ dùng trong ví dụ có thể được khai báo như sau:

~~~java
public enum OrderStatus {
    DRAFT, CONFIRMED, CANCELLED
}

public record OrderLine(
        ProductCode productCode,
        int quantity,
        Money unitPrice) {

    public OrderLine {
        Objects.requireNonNull(productCode);
        Objects.requireNonNull(unitPrice);
        if (quantity <= 0) {
            throw new OrderRuleViolation("Quantity must be positive");
        }
    }

    public Money subtotal() {
        return unitPrice.multiply(quantity);
    }
}

public final class OrderRuleViolation extends RuntimeException {
    public OrderRuleViolation(String message) {
        super(message);
    }
}
~~~

### 9.1. Bất biến của aggregate

Bất biến là điều kiện phải luôn đúng ở mọi trạng thái hợp lệ của aggregate. Trong ví dụ Order:

- Mỗi dòng hàng có số lượng dương.
- Đơn ở trạng thái DRAFT mới được thêm hoặc xóa dòng.
- Đơn chỉ được xác nhận khi có ít nhất một dòng.
- Tổng tiền bằng tổng subtotal của các dòng.
- Đơn chỉ được hủy ở các trạng thái được cho phép.

Bất biến nên được bảo vệ bởi Aggregate Root. Không để code bên ngoài gọi setter tùy ý lên các trường quan trọng.

### 9.2. Aggregate nên nhỏ và nhất quán

Không nên đưa toàn bộ đối tượng có liên quan vào một aggregate lớn. Một aggregate quá lớn làm tăng chi phí tải, khóa và cập nhật đồng thời.

Một số nguyên tắc:

- Đặt cùng aggregate khi các đối tượng cần duy trì bất biến tức thời cùng nhau.
- Tham chiếu aggregate khác bằng ID thay vì giữ toàn bộ object graph.
- Dùng domain event hoặc quy trình application để phối hợp thay đổi giữa các aggregate.
- Chấp nhận eventual consistency khi nghiệp vụ cho phép.
- Tải dữ liệu cần thiết cho hành vi, tránh nạp mọi quan hệ.

Ví dụ Order có thể lưu CustomerId thay vì nhúng toàn bộ Customer. Việc đổi địa chỉ khách hàng không nhất thiết phải tải và lưu lại mọi đơn hàng đã tạo.

## 10. Domain Service: quy tắc không thuộc tự nhiên một Entity

Một số quy tắc nghiệp vụ không phù hợp để đặt vào một Entity cụ thể. Domain Service biểu diễn hành vi đó mà không biến nó thành tiện ích kỹ thuật chung.

Ví dụ, chính sách định giá có thể phụ thuộc khách hàng, sản phẩm và thời điểm:

~~~java
public interface PricingPolicy {
    Money calculatePrice(
        CustomerCategory customerCategory,
        Product product,
        Instant effectiveAt
    );
}
~~~

Hoặc một dịch vụ domain có thể kiểm tra việc phân bổ hạn mức giữa nhiều đối tượng:

~~~java
public class CreditAllocationService {
    public boolean canAllocate(
            Money creditLimit,
            Money currentExposure,
            Money requestedAmount) {
        Money projected = currentExposure.add(requestedAmount);
        return projected.compareTo(creditLimit) <= 0;
    }
}
~~~

Domain Service nên:

- Có tên diễn đạt quy tắc nghiệp vụ.
- Không giữ trạng thái tùy tiện giữa các lần gọi.
- Làm việc với các kiểu domain thay vì Servlet Request hoặc JPA Entity.
- Không trở thành nơi gom tất cả logic mà Entity chưa được thiết kế tốt.

Nếu hành vi chỉ liên quan đến một Order, hãy ưu tiên đặt nó trong Order. Chỉ tách Domain Service khi quy tắc thực sự liên quan nhiều đối tượng hoặc không có chủ thể tự nhiên.

## 11. Application Service và Domain Service khác nhau

Hai loại service thường bị nhầm lẫn.

| Application Service | Domain Service |
|---|---|
| Điều phối một ca sử dụng | Thực hiện quy tắc nghiệp vụ |
| Xác định transaction và phối hợp port | Không điều khiển giao thức hoặc transaction hạ tầng |
| Tải aggregate, gọi hành vi, lưu kết quả | Làm việc với khái niệm domain |
| Có thể gọi email, repository, message port | Không trực tiếp gửi HTTP hoặc thao tác Servlet |
| Ví dụ: PlaceOrderService | Ví dụ: PricingPolicy |

Application Service thường không nên chứa nhiều phép tính hoặc quy tắc trạng thái. Nó điều phối: lấy actor, tải dữ liệu cần thiết, gọi Domain Model, lưu thay đổi và phát các kết quả phù hợp.

Domain Service không nên biết request đến từ form HTML hay REST API. Cùng một quy tắc có thể được gọi từ nhiều ca sử dụng.

## 12. Domain Event: mô tả điều đã xảy ra

Domain Event biểu diễn một sự kiện có ý nghĩa trong miền và thường được đặt ở thì quá khứ:

- OrderPlaced.
- OrderConfirmed.
- PaymentCaptured.
- StockReserved.
- CustomerAddressChanged.

Domain Event khác command:

- Command yêu cầu một hành động: ConfirmOrder.
- Event mô tả điều đã xảy ra: OrderConfirmed.

Ví dụ:

~~~java
public interface DomainEvent {
    Instant occurredAt();
}

public record OrderConfirmed(
    OrderId orderId,
    CustomerId customerId,
    Instant occurredAt
) implements DomainEvent {}
~~~

Aggregate có thể ghi nhận event sau khi hành vi thành công. Application hoặc infrastructure sẽ thu thập và phát event theo cơ chế phù hợp.

~~~java
private final List<DomainEvent> domainEvents = new ArrayList<>();

public void confirm(Instant now) {
    Objects.requireNonNull(now);
    requireDraft();
    if (lines.isEmpty()) {
        throw new OrderRuleViolation("Order cannot be empty");
    }

    status = OrderStatus.CONFIRMED;
    domainEvents.add(new OrderConfirmed(id, customerId, now));
}

public List<DomainEvent> domainEvents() {
    return List.copyOf(domainEvents);
}

public void clearDomainEvents() {
    domainEvents.clear();
}
~~~

Đây là phần cài đặt bổ sung cho Order ở ví dụ Aggregate. Cần xác định thời điểm xóa event và bảo đảm event chỉ được phát sau khi thay đổi dữ liệu được commit.

### 12.1. Phát event sau khi commit

Nếu gửi message ra broker trước khi transaction database commit, consumer có thể nhận event về một thay đổi sau đó bị rollback. Một giải pháp phổ biến là transactional outbox: ghi dữ liệu nghiệp vụ và outbox record trong cùng transaction; một publisher riêng đọc outbox rồi gửi message.

Không phải mọi domain event đều cần đi ra message broker. Một event nội bộ có thể chỉ dùng để điều phối trong cùng process. Chọn cơ chế theo yêu cầu độ bền và tích hợp.

### 12.2. Event không phải log

Domain Event là dữ liệu có ngữ nghĩa nghiệp vụ và có thể kích hoạt hành vi tiếp theo. Log là tín hiệu quan sát phục vụ vận hành. Một event có thể được log, lưu audit hoặc publish, nhưng ba việc này có mục đích và chính sách lưu trữ khác nhau.

## 13. Repository và cách lưu aggregate

Repository cung cấp hợp đồng để tải và lưu aggregate. Interface nên phản ánh nhu cầu của domain hoặc application, không nên phơi bày API của ORM.

~~~java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}
~~~

Application dùng hợp đồng này:

~~~java
public class ConfirmOrderService {
    private final OrderRepository orders;
    private final Clock clock;

    public ConfirmOrderService(OrderRepository orders, Clock clock) {
        this.orders = orders;
        this.clock = clock;
    }

    public void handle(ConfirmOrderCommand command) {
        Order order = orders.findById(command.orderId())
            .orElseThrow(OrderNotFoundException::new);

        order.confirm(clock.instant());
        orders.save(order);
    }
}
~~~

Implementation có thể dùng Spring Data JPA, JDBC hoặc một nguồn dữ liệu khác. Nếu Domain Model tách khỏi ORM Entity, adapter sẽ ánh xạ hai mô hình.

Không cần tạo Repository cho mọi bảng hoặc mọi Value Object. Thường một Repository quản lý Aggregate Root; đối tượng con được lưu qua root để bảo vệ tính nhất quán.

## 14. Domain Model trong luồng request MVC

Một luồng tạo đơn có thể được tổ chức như sau:

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant Browser as Trình duyệt
    participant Controller as MVC Controller
    participant App as Application Service
    participant Domain as Order Aggregate
    participant Repo as Order Repository

    User->>Browser: Gửi form
    Browser->>Controller: POST /orders
    Controller->>Controller: Bind và kiểm tra request DTO
    Controller->>App: PlaceOrderCommand
    App->>Repo: Tải dữ liệu cần thiết
    Repo-->>App: Domain objects
    App->>Domain: Gọi hành vi nghiệp vụ
    Domain-->>App: Trạng thái hợp lệ hoặc domain error
    App->>Repo: Lưu aggregate
    App-->>Controller: OrderId / Result
    Controller-->>Browser: Redirect hoặc response
~~~

Mỗi tầng có nhiệm vụ rõ ràng:

- Controller xử lý HTTP, binding, status code và điều hướng View.
- Request DTO biểu diễn dữ liệu client gửi.
- Application Service điều phối use case.
- Domain Model bảo vệ bất biến và quy tắc.
- Repository lưu và tải aggregate.
- View Model/Response DTO chuẩn bị dữ liệu phù hợp cho giao diện.

Controller không nên tự tính tổng tiền hoặc tự gán trạng thái nghiệp vụ. Application không nên trả Model của Spring MVC hoặc HttpServletResponse cho Domain.

## 15. Tách Request DTO, Domain Model và View Model

Không nên mặc định dùng cùng một object cho request, domain và response. Mỗi mô hình có mục tiêu riêng.

~~~java
public record CreateOrderRequest(
    UUID customerId,
    List<CreateOrderLineRequest> lines
) {}

public record CreateOrderLineRequest(
    String productCode,
    int quantity
) {}

public record PlaceOrderCommand(
    CustomerId customerId,
    List<PlaceOrderLine> lines
) {}

public record OrderDetailView(
    String orderNumber,
    String customerName,
    String statusLabel,
    String formattedTotal,
    List<OrderLineView> lines
) {}
~~~

Luồng ánh xạ:

1. Request DTO nhận và kiểm tra cấu trúc dữ liệu từ HTTP.
2. Controller hoặc mapper chuyển DTO thành command có kiểu domain.
3. Application Service gọi Domain Model.
4. Query service hoặc presenter chuyển kết quả thành View Model.
5. Controller đưa View Model vào template hoặc serialize response.

Request DTO có thể chứa String, UUID và kiểu dữ liệu thuận tiện cho giao thức. Domain Model nên dùng các kiểu diễn đạt ý nghĩa như OrderId, ProductCode, Money và OrderStatus.

Trong ví dụ, customerId được đưa vào request để minh họa ánh xạ kiểu. Với chức năng tạo đơn thực tế, danh tính khách hàng thường phải lấy từ actor đã xác thực ở application layer thay vì tin customerId do client tự gửi.

View Model có thể chứa formattedTotal hoặc statusLabel vì đó là dữ liệu phục vụ hiển thị. Không đưa các chuỗi định dạng này trở lại Domain Model.

## 16. Validation ở boundary và bất biến trong Domain

Không phải mọi kiểm tra đều thuộc cùng một tầng.

| Loại kiểm tra | Ví dụ | Vị trí phù hợp |
|---|---|---|
| Cấu trúc request | Trường bắt buộc, JSON đúng kiểu | Binding / DTO validation |
| Định dạng đầu vào | Email hợp lệ, ngày parse được | Boundary / Value Object |
| Quy tắc nghiệp vụ | Đơn phải có ít nhất một dòng | Domain Model |
| Quyền truy cập | Actor có được hủy đơn không | Application policy / security |
| Trạng thái chuyển đổi | Chỉ đơn nháp được xác nhận | Domain Model |
| Tồn tại dữ liệu | Sản phẩm có tồn tại không | Application qua Repository/port |

DTO validation giúp trả lỗi đầu vào rõ ràng trước khi gọi use case. Domain vẫn cần bảo vệ bất biến vì có thể được gọi từ job, message hoặc test không đi qua HTTP.

Không lặp mọi constraint ở tất cả các tầng. Hãy đặt kiểm tra tại nơi có đủ ngữ nghĩa để quyết định. Ví dụ, quantity phải là số nguyên dương có thể được kiểm tra trong Value Object hoặc hành vi Domain; quantity bị thiếu trong JSON là lỗi hợp đồng request.

## 17. Anemic Domain Model và Rich Domain Model

Anemic Domain Model là mô hình trong đó Entity chủ yếu chứa field và getter/setter, còn hầu hết quy tắc được đặt trong Service.

Ví dụ:

~~~java
public class Order {
    private OrderStatus status;
    private BigDecimal total;

    public void setStatus(OrderStatus status) {
        this.status = status;
    }

    public void setTotal(BigDecimal total) {
        this.total = total;
    }
}
~~~

Service phải tự nhớ điều kiện:

~~~java
if (order.getStatus() == OrderStatus.DRAFT) {
    order.setStatus(OrderStatus.CONFIRMED);
}
~~~

Nếu nhiều service làm điều này, một service có thể quên kiểm tra trạng thái hoặc cập nhật tổng tiền sai cách.

Rich Domain Model đặt hành vi và bất biến gần đối tượng:

~~~java
order.confirm();
~~~

Phương thức confirm tự bảo vệ điều kiện cần thiết. Bên ngoài không cần biết cách chuyển trạng thái.

Tuy nhiên, không phải mọi ứng dụng đều cần Rich Domain Model. Một hệ thống chủ yếu CRUD, ít quy tắc và không có trạng thái phức tạp có thể dùng transaction script hoặc service-oriented design đơn giản. Không nên tạo nhiều lớp domain chỉ để làm code có vẻ giống DDD.

## 18. Persistence và ánh xạ Domain Model

Domain Model không nên bị thiết kế chỉ theo cấu trúc bảng. Database có thể có bảng phụ, cột kỹ thuật, quan hệ join hoặc kiểu dữ liệu đặc thù. Những chi tiết đó thuộc persistence model.

Có hai cách thường gặp:

### 18.1. Dùng cùng lớp cho Domain và JPA

Phù hợp khi mô hình đơn giản, quy tắc ít và annotation ORM không làm ảnh hưởng đáng kể đến domain.

Ưu điểm:
- Ít lớp và ít mapping.
- CRUD nhanh.
- Ít mã chuyển đổi.

Hạn chế:
- Domain phụ thuộc JPA annotation.
- Quan hệ lazy/eager có thể ảnh hưởng cách sử dụng.
- Constructor và setter có thể bị chi phối bởi ORM.
- Schema persistence có thể làm méo mô hình nghiệp vụ.

### 18.2. Tách Domain Entity và JPA Entity

Phù hợp khi domain có hành vi, aggregate phức tạp hoặc cần độc lập với ORM.

~~~java
@Entity
@Table(name = "orders")
public class OrderJpaEntity {
    @Id
    private UUID id;

    private UUID customerId;
    private String status;
    private BigDecimal total;
    private long version;
}
~~~

Adapter dùng mapper để tái tạo domain object. Mapper cần bảo đảm invariant, identity, version và quan hệ aggregate được giữ đúng.

Không nên tách chỉ vì nguyên tắc trừu tượng. Cân nhắc chi phí mapping, độ phức tạp ORM, nhu cầu kiểm thử và khả năng thay đổi công nghệ lưu trữ.

## 19. Kiểm thử Domain Model

Domain Model có thể được kiểm thử mà không cần Spring MVC, HTTP server hoặc database.

Ví dụ:

~~~java
class OrderTest {

    @Test
    void cannotConfirmAnEmptyOrder() {
        Order order = Order.create(
            new OrderId(UUID.randomUUID()),
            new CustomerId("customer-1")
        );

        assertThrows(
            OrderRuleViolation.class,
            () -> order.confirm(Instant.EPOCH)
        );
    }

    @Test
    void cannotChangeLinesAfterConfirmation() {
        Order order = anOrderWithOneLine();
        order.confirm(Instant.EPOCH);

        assertThrows(
            OrderRuleViolation.class,
            () -> order.addLine(
                new ProductCode("BOOK-02"),
                1,
                Money.of(100, Currency.getInstance("VND"))
            )
        );
    }
}
~~~

Ngoài các ví dụ trên, nên kiểm thử:

- Tổng tiền sau khi thêm hoặc xóa dòng.
- Không trộn tiền tệ nếu quy tắc cấm.
- Chuyển trạng thái chỉ theo các cạnh hợp lệ.
- Hủy đơn ở trạng thái không được phép.
- Equality của Entity theo identity.
- Equality của Value Object theo giá trị.
- Domain Event chỉ được tạo khi hành vi thành công.

### 19.1. Unit test và integration test có mục tiêu khác nhau

- Unit test Domain xác nhận quy tắc và bất biến.
- Application test dùng fake Repository để xác nhận điều phối use case.
- Repository integration test xác nhận mapping và persistence.
- MVC test xác nhận binding, response và điều hướng.
- End-to-end test xác nhận các thành phần phối hợp đúng.

Không cần khởi động database cho một test chỉ muốn xác nhận Order không thể xác nhận khi rỗng. Ngược lại, unit test không chứng minh mapper JPA hoặc transaction hoạt động đúng.

## 20. Những lỗi thiết kế thường gặp

### Nhầm MVC Model với Domain Model

org.springframework.ui.Model chỉ là vùng chứa thuộc tính cho View. Đưa quy tắc nghiệp vụ vào đó làm ranh giới trách nhiệm bị mờ.

### Dùng Entity làm Request DTO

Client có thể gửi những trường không được phép thay đổi như status, ownerId hoặc approvalState. Dùng DTO riêng để xác định hợp đồng đầu vào.

### Để Controller chứa quy tắc nghiệp vụ

Nhiều Controller có thể lặp lại hoặc thực thi quy tắc khác nhau. Chuyển hành vi quan trọng vào Domain Model và use case.

### Entity chỉ có getter/setter

Nếu mọi thay đổi đều đi qua setter, bất biến dễ bị phá vỡ. Tạo phương thức hành vi có tên nghiệp vụ và giới hạn quyền sửa trường.

### Aggregate quá lớn

Một aggregate chứa quá nhiều đối tượng làm tăng chi phí tải, khóa và cập nhật đồng thời. Chỉ gom các đối tượng cần cùng bảo vệ bất biến tức thời.

### Tạo Domain Service cho mọi thao tác

Một service cho từng CRUD method không làm mô hình giàu hơn. Đặt hành vi vào Entity khi nó thuộc về Entity; chỉ dùng Domain Service khi không có chủ thể tự nhiên.

### Domain Model phụ thuộc framework

Không để Domain Model phụ thuộc Servlet API, Spring MVC Model hoặc kiểu request của controller. Giữ framework ở adapter và infrastructure khi cần độc lập.

### Dùng một mô hình cho nhiều bounded context

Cùng một danh từ có thể có ý nghĩa khác nhau. Tách mô hình theo ngữ cảnh nghiệp vụ thay vì tạo một lớp dùng chung quá rộng.

### Tách lớp quá mức

Không phải mọi String đều cần Value Object và không phải mọi bảng đều cần một aggregate. Chỉ tạo abstraction khi nó diễn đạt ý nghĩa, quy tắc hoặc ranh giới thực sự.

## 21. Quy trình xây dựng Domain Model

Khi bắt đầu một chức năng, hãy làm theo trình tự:

1. **Hiểu miền nghiệp vụ.** Trao đổi với người hiểu nghiệp vụ và thống nhất thuật ngữ.
2. **Xác định bounded context.** Làm rõ phạm vi mô hình và các hệ thống liên quan.
3. **Tìm Entity và Value Object.** Xác định identity, giá trị và ràng buộc.
4. **Tìm hành vi và bất biến.** Ghi rõ điều kiện trước/sau mỗi hành động.
5. **Xác định aggregate root.** Gom các đối tượng cần bảo vệ nhất quán cùng nhau.
6. **Đặt quy tắc đúng nơi.** Entity, Value Object, Domain Service hoặc Application Service.
7. **Xác định Repository và event.** Chỉ tạo hợp đồng cần thiết cho use case.
8. **Kết nối MVC.** Map request DTO thành command; trả View Model hoặc response DTO.
9. **Tách persistence khi có lý do.** Ánh xạ Domain Model với ORM Entity ở adapter.
10. **Kiểm thử bất biến.** Bắt đầu bằng unit test Domain, sau đó kiểm thử application và tích hợp.

Trước khi hoàn thành, hãy tự hỏi:

- Tên lớp và phương thức có dùng đúng ngôn ngữ nghiệp vụ không?
- Đối tượng nào có identity và đối tượng nào chỉ là giá trị?
- Bất biến nào phải luôn đúng?
- Có một aggregate root rõ ràng kiểm soát thay đổi không?
- Quy tắc đang nằm trong Domain hay bị rải ở Controller?
- Application Service đang điều phối hay đang chứa quá nhiều nghiệp vụ?
- Domain Model có phụ thuộc HTTP, template hoặc ORM không cần thiết không?
- Các bounded context có đang dùng chung một mô hình dù ngữ nghĩa khác nhau không?
- Unit test có thể xác nhận quy tắc mà không cần database không?

## 22. Kết luận

Domain Model biểu diễn khái niệm, hành vi và quy tắc của một miền nghiệp vụ. Trong MVC, nó là phần nghiệp vụ của Model theo nghĩa rộng; nó khác với Model attribute của Spring MVC, View Model, Request DTO và ORM Entity.

Thiết kế hướng miền bắt đầu từ ngôn ngữ chung và ranh giới bounded context, sau đó mô hình hóa Entity, Value Object, Aggregate, Domain Service và Domain Event khi cần. Aggregate Root bảo vệ bất biến; Application Service điều phối ca sử dụng; Repository cung cấp hợp đồng lưu trữ; Controller chỉ chuyển đổi tương tác HTTP thành lời gọi ứng dụng. Khi các ranh giới này rõ ràng, quy tắc nghiệp vụ có thể được tái sử dụng giữa nhiều giao diện, kiểm thử độc lập và phát triển mà không bị chi phối bởi cấu trúc View hoặc database.


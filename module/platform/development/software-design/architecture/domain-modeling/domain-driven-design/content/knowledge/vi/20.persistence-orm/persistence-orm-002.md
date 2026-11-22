# Ánh xạ aggregate với JPA và Hibernate trong Java

## Vì sao ánh xạ Aggregate cần được thiết kế cẩn thận?

Trong Domain-Driven Design (DDD), Aggregate là ranh giới nhất quán của một nhóm đối tượng miền. Aggregate Root chịu trách nhiệm bảo vệ các bất biến và là điểm truy cập từ bên ngoài. Khi dùng JPA và Hibernate để lưu aggregate, nhóm cần giữ được ranh giới đó trong mô hình đối tượng, quan hệ ORM và transaction.

Một ánh xạ thiếu kiểm soát có thể làm mất ý nghĩa của aggregate: caller sửa trực tiếp entity con, cascade xóa lan sang aggregate khác, lazy loading kéo theo một đồ thị đối tượng lớn, hoặc một thay đổi ở dòng hàng không được bảo vệ bởi cơ chế đồng thời của root. Ngược lại, nếu hiểu rõ trách nhiệm của từng quan hệ, JPA có thể giúp lưu và khôi phục aggregate mà không buộc domain model trở thành một tập getter/setter thuần dữ liệu.

Bài học này tập trung vào cách ánh xạ aggregate bằng Java Persistence API (JPA) và Hibernate. JPA định nghĩa các annotation và hợp đồng persistence; Hibernate là một implementation phổ biến, đồng thời cung cấp một số tính năng mở rộng riêng. Các ví dụ dùng namespace `jakarta.persistence` thường gặp trong ứng dụng Jakarta EE hoặc Spring Boot 3 trở lên. Với dự án cũ dùng JPA 2 và Spring Boot 2, package có thể là `javax.persistence`; không trộn hai namespace trong cùng một ứng dụng.

Sau bài học, người học có thể:

- Ánh xạ Aggregate Root và entity con bằng `@Entity`, `@OneToMany` và `@ManyToOne`.
- Biểu diễn Value Object bằng `@Embeddable`, `@Embedded` hoặc `@ElementCollection`.
- Giữ aggregate reference qua định danh thay vì liên kết ORM xuyên aggregate.
- Chọn cascade, orphan removal và fetch strategy theo vòng đời nghiệp vụ.
- Dùng repository và transaction để tải, thay đổi, lưu aggregate qua root.
- Bảo vệ cập nhật đồng thời bằng `@Version` và hiểu giới hạn của version ở aggregate có entity con.
- Tránh các lỗi thường gặp khi kết hợp domain model với JPA/Hibernate.

## Nguyên tắc ánh xạ Aggregate

### Aggregate Root là điểm truy cập và lưu trữ

Một aggregate có một root. Repository miền nên tải và lưu root; các entity con được tải cùng hoặc theo cách mà persistence mapping cần để bảo vệ hành vi của root. Thành phần bên ngoài không nên lấy entity con rồi sửa độc lập.

Ví dụ, `Order` có thể là root và chứa `OrderLine`. Bên ngoài gọi `order.addLine(...)`, `order.removeLine(...)` hoặc `order.place()`. Root kiểm tra trạng thái và bất biến trước khi thay đổi collection. Repository có thể lưu cả root và các dòng hàng trong một transaction.

### Chỉ ánh xạ quan hệ thuộc cùng ranh giới Aggregate

Trong cùng aggregate, JPA relationship có thể diễn tả quan hệ sở hữu vòng đời. `Order` và `OrderLine` thường được ánh xạ bằng `@OneToMany`/`@ManyToOne` vì dòng hàng không có vòng đời độc lập với đơn.

Giữa hai aggregate, ưu tiên lưu ID của root được tham chiếu. Ví dụ, `Order` giữ `customerId`, `OrderLine` giữ `productId`; không cần ánh xạ `@ManyToOne Customer` hoặc `@ManyToOne Product` chỉ để nối các aggregate. Cách này giữ quyền sở hữu và tránh một lần tải đơn hàng kéo theo nhiều aggregate khác.

### Persistence mapping không quyết định mô hình miền

JPA mô tả cách lưu và khôi phục đối tượng. Nó không nên quyết định entity nào tồn tại, aggregate có ranh giới ở đâu hoặc quy tắc nghiệp vụ được đặt ở đâu. Hãy xác định danh tính, vòng đời, bất biến và quan hệ trước, sau đó mới chọn annotation phù hợp.

## Ánh xạ Aggregate Root bằng `@Entity`

### Một Aggregate Root đơn giản

Ví dụ sau mô tả `Order` là Aggregate Root. Đơn hàng giữ `customerId` như một định danh, trạng thái và collection các dòng hàng thuộc cùng aggregate.

```java
import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

@Entity
@Table(name = "orders")
@Access(AccessType.FIELD)
public class Order {
    @Id
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    // Tham chiếu aggregate Customer bằng ID, không giữ Customer entity.
    @Column(name = "customer_id", nullable = false, updatable = false)
    private UUID customerId;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 24)
    private OrderStatus status;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    @OneToMany(mappedBy = "order",
            cascade = CascadeType.ALL,
            orphanRemoval = true)
    private List<OrderLine> lines = new ArrayList<>();

    // JPA cần constructor không tham số với visibility public/protected.
    protected Order() {
    }

    private Order(UUID id, UUID customerId) {
        this.id = Objects.requireNonNull(id, "id");
        this.customerId = Objects.requireNonNull(customerId, "customerId");
        this.status = OrderStatus.DRAFT;
    }

    public static Order draft(UUID customerId) {
        return new Order(UUID.randomUUID(), customerId);
    }

    public void addLine(UUID productId, Quantity quantity, Money unitPrice) {
        requireDraft();
        OrderLine line = new OrderLine(this, productId, quantity, unitPrice);
        lines.add(line);
    }

    public void place() {
        requireDraft();
        if (lines.isEmpty()) {
            throw new IllegalStateException("An order needs at least one line");
        }
        status = OrderStatus.PLACED;
    }

    private void requireDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Only a draft order can be changed");
        }
    }

    public UUID id() {
        return id;
    }

    public UUID customerId() {
        return customerId;
    }

    public OrderStatus status() {
        return status;
    }

    public List<OrderLine> lines() {
        return List.copyOf(lines);
    }
}
```

Đây là ví dụ minh họa, giả định `OrderStatus`, `OrderLine`, `Quantity` và `Money` được định nghĩa trong cùng mô hình. ID được sinh ở application/domain khi tạo đơn nên không cần `@GeneratedValue`. Với dự án dùng ID do database hoặc Hibernate cấp, có thể cấu hình generator tương ứng; lựa chọn đó không làm thay đổi vai trò của ID trong domain.

Enum trạng thái được lưu bằng tên để tránh phụ thuộc vào thứ tự khai báo:

```java
public enum OrderStatus {
    DRAFT,
    PLACED,
    CANCELLED
}
```

`@Access(AccessType.FIELD)` cho biết JPA truy cập các field trực tiếp. Vì `@Id` đặt trên field, các annotation mapping khác cũng được đặt trên field để tránh trộn field access và property access ngoài ý muốn. Không cần public setter chỉ để ORM có thể ghi dữ liệu khi field access được dùng.

### Vì sao entity JPA không nên là `final`?

JPA yêu cầu entity class, các phương thức persistent và persistent instance fields không bị `final` theo quy tắc portability; Hibernate cũng thường cần proxy hoặc enhancement để hỗ trợ lazy loading. Entity thường cần constructor không tham số `public` hoặc `protected`. Vì vậy, domain entity được ánh xạ trực tiếp bằng JPA thường không thể được thiết kế giống hệt một immutable value object thuần.

Có thể giảm rò rỉ persistence bằng cách:

- Dùng constructor không tham số `protected` dành cho JPA.
- Giữ constructor tạo mới và hành vi miền có tên, không công khai setter tổng quát.
- Dùng field access và chỉ cung cấp các phương thức đọc cần thiết.
- Không dùng Lombok `@Data` cho entity vì nó thường sinh setter và `equals`/`hashCode` dựa trên toàn bộ field.
- Không trả entity trực tiếp qua REST hoặc serialize toàn bộ object graph.

Nếu các ràng buộc của JPA làm domain model bị biến dạng đáng kể, có thể dùng persistence model riêng và mapper để chuyển đổi. Đó là một lựa chọn kiến trúc có chi phí; không phải ứng dụng nào cũng cần tách hai mô hình.

## Ánh xạ Entity con thuộc Aggregate

### `@OneToMany` và `@ManyToOne`

Trong quan hệ một đơn có nhiều dòng hàng, cột khóa ngoại `order_id` nằm ở bảng `order_lines`. Vì vậy, phía `OrderLine` là phía sở hữu quan hệ trong JPA và dùng `@ManyToOne`; collection `Order.lines` dùng `mappedBy = "order"` để chỉ ra field sở hữu ở phía con.

```java
import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.AttributeOverride;
import jakarta.persistence.AttributeOverrides;
import jakarta.persistence.Column;
import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.util.Objects;
import java.util.UUID;

@Entity
@Table(name = "order_lines")
@Access(AccessType.FIELD)
public class OrderLine {
    @Id
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false, updatable = false)
    private Order order;

    // Product là aggregate khác: chỉ lưu định danh của nó.
    @Column(name = "product_id", nullable = false, updatable = false)
    private UUID productId;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(name = "amount",
            column = @Column(name = "quantity_amount", nullable = false,
                    precision = 19, scale = 4)),
        @AttributeOverride(name = "unitCode",
            column = @Column(name = "quantity_unit", nullable = false, length = 12))
    })
    private Quantity quantity;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(name = "amount",
            column = @Column(name = "unit_price_amount", nullable = false,
                    precision = 19, scale = 4)),
        @AttributeOverride(name = "currency",
            column = @Column(name = "unit_price_currency", nullable = false, length = 3))
    })
    private Money agreedUnitPrice;

    protected OrderLine() {
    }

    OrderLine(Order order, UUID productId,
              Quantity quantity, Money agreedUnitPrice) {
        this.id = UUID.randomUUID();
        this.order = Objects.requireNonNull(order, "order");
        this.productId = Objects.requireNonNull(productId, "productId");
        this.quantity = Objects.requireNonNull(quantity, "quantity");
        this.agreedUnitPrice = Objects.requireNonNull(agreedUnitPrice,
                "agreedUnitPrice");
    }

    public UUID id() {
        return id;
    }

    public UUID productId() {
        return productId;
    }

    public Quantity quantity() {
        return quantity;
    }

    public Money agreedUnitPrice() {
        return agreedUnitPrice;
    }
}
```

`OrderLine` không có API công khai để tự chuyển sang đơn hàng khác. Constructor tạo dòng hàng chỉ được gọi từ package/domain root; root quản lý việc thêm dòng và bảo vệ trạng thái đơn. Trong dự án thật, có thể đặt các entity này trong package nội bộ của aggregate để hạn chế nơi sử dụng.

JPA coi `OrderLine.order` là phía sở hữu vì field đó chứa khóa ngoại. Khi thêm một dòng, cần thiết lập cả hai phía trong bộ nhớ: tạo `OrderLine` với `this` làm order rồi thêm vào collection. Chỉ thêm vào `Order.lines` mà không đặt `OrderLine.order` sẽ làm quan hệ không được lưu như mong đợi.

### `cascade` và `orphanRemoval`

Trong ví dụ, `cascade = CascadeType.ALL` cho phép thao tác persistence trên root lan đến các dòng hàng thuộc vòng đời của nó. `orphanRemoval = true` có nghĩa khi một dòng bị loại khỏi quan hệ sở hữu, provider sẽ xóa bản ghi con khi flush.

Chỉ dùng các tùy chọn này khi entity con thực sự thuộc quyền sở hữu vòng đời của root. Chúng thường phù hợp với `OrderLine` vì dòng hàng không tồn tại độc lập sau khi bị loại khỏi đơn. Chúng không phù hợp để xóa `Customer` hoặc `Product` khi một đơn hàng bị xóa.

| Tùy chọn | Ý nghĩa | Khi nên dùng |
|---|---|---|
| `CascadeType.PERSIST` | Persist root kéo theo persist entity con | Entity con mới thuộc aggregate |
| `CascadeType.MERGE` | Merge root kéo theo merge entity con | Khi thực sự dùng merge trên graph detached |
| `CascadeType.REMOVE` | Xóa root kéo theo xóa entity con | Vòng đời con phụ thuộc root |
| `CascadeType.ALL` | Bao gồm các thao tác cascade phổ biến | Quan hệ sở hữu chặt, đã hiểu rõ tác động |
| `orphanRemoval = true` | Xóa bản ghi con khi bị loại khỏi quan hệ | Con không có vòng đời độc lập |

Không nên chọn `ALL` theo thói quen cho mọi quan hệ. Đặc biệt, tránh cascade remove qua ranh giới aggregate. Một khách hàng có thể có hàng trăm đơn hàng; xóa hoặc đóng hồ sơ khách hàng không đồng nghĩa với việc xóa lịch sử đơn hàng.

### Không dùng `@ManyToMany` để che giấu mô hình nghiệp vụ

Quan hệ nhiều-nhiều trực tiếp có thể tiện cho bảng liên kết đơn giản, nhưng nếu mối quan hệ có thuộc tính hoặc vòng đời riêng, hãy mô hình hóa nó thành entity/aggregate phù hợp. Ví dụ, việc nhân viên tham gia dự án có ngày bắt đầu, vai trò và tỷ lệ phân bổ nên được biểu diễn bằng `ProjectAssignment` thay vì một collection `@ManyToMany` không thể chứa quy tắc.

Giữa hai aggregate, cũng không nên tạo `@ManyToMany` chỉ để ORM tự quản lý bảng nối. Hãy xác định context nào sở hữu mối liên hệ và dùng ID hoặc một mô hình liên kết có trách nhiệm rõ ràng.

## Ánh xạ Value Object

### `@Embeddable` và `@Embedded`

Value Object được xác định bằng giá trị và không có danh tính độc lập. Với JPA, một value object có thể được ánh xạ bằng `@Embeddable` và nhúng vào entity bằng `@Embedded`. Các field của nó được lưu thành các cột trong bảng của entity sở hữu.

Ví dụ `Money`:

```java
import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.math.BigDecimal;
import java.util.Objects;

@Embeddable
@Access(AccessType.FIELD)
public class Money {
    @Column(name = "amount", precision = 19, scale = 4, nullable = false)
    private BigDecimal amount;

    @Column(name = "currency", length = 3, nullable = false)
    private String currency;

    protected Money() {
    }

    public Money(BigDecimal amount, String currency) {
        this.amount = Objects.requireNonNull(amount, "amount");
        String normalizedCurrency = Objects.requireNonNull(currency, "currency")
                .trim().toUpperCase(java.util.Locale.ROOT);
        if (normalizedCurrency.length() != 3) {
            throw new IllegalArgumentException("Invalid money value");
        }
        this.currency = normalizedCurrency;
    }

    public BigDecimal amount() {
        return amount;
    }

    public String currency() {
        return currency;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof Money money
                && currency.equals(money.currency)
                && amount.compareTo(money.amount) == 0;
    }

    @Override
    public int hashCode() {
        return Objects.hash(amount.stripTrailingZeros(), currency);
    }
}
```

Đây là value object rút gọn; mô hình thật cần xác định mã tiền tệ hợp lệ, số chữ số thập phân và chính sách cho phép số âm. Ví dụ này cho phép số âm vì `Money` có thể biểu diễn khoản điều chỉnh; nếu một khái niệm như đơn giá không được âm, hãy bảo vệ điều kiện đó ở `UnitPrice` hoặc hành vi miền tương ứng. `equals` dùng `compareTo` để coi `10.0` và `10.00` là cùng giá trị, còn `hashCode` chuẩn hóa scale tương ứng. Để giữ ví dụ tương thích với cách ánh xạ JPA phổ biến, class có constructor không tham số `protected` và field không `final`. Không cung cấp setter công khai; domain code thay toàn bộ value object bằng một instance hợp lệ khi cần thay đổi.

Khi một entity chứa nhiều `Money`, dùng `@AttributeOverrides` để đặt tên cột riêng cho từng instance. Ví dụ `OrderLine` ở trên ánh xạ `agreedUnitPrice.amount` thành `unit_price_amount` và `agreedUnitPrice.currency` thành `unit_price_currency`.

### Quantity được nhúng vào OrderLine

`OrderLine` ở ví dụ trước dùng `Quantity` với hai field `amount` và `unitCode`. Một ánh xạ tương ứng có thể như sau:

```java
import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.math.BigDecimal;
import java.util.Objects;

@Embeddable
@Access(AccessType.FIELD)
public class Quantity {
    @Column(name = "amount", precision = 19, scale = 4, nullable = false)
    private BigDecimal amount;

    @Column(name = "unit_code", length = 12, nullable = false)
    private String unitCode;

    protected Quantity() {
    }

    public Quantity(BigDecimal amount, String unitCode) {
        this.amount = Objects.requireNonNull(amount, "amount");
        this.unitCode = Objects.requireNonNull(unitCode, "unitCode").trim();
        if (amount.signum() <= 0 || this.unitCode.isEmpty()) {
            throw new IllegalArgumentException("Invalid quantity");
        }
    }

    public BigDecimal amount() {
        return amount;
    }

    public String unitCode() {
        return unitCode;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof Quantity quantity
                && unitCode.equals(quantity.unitCode)
                && amount.compareTo(quantity.amount) == 0;
    }

    @Override
    public int hashCode() {
        return Objects.hash(amount.stripTrailingZeros(), unitCode);
    }
}
```

Quy tắc `amount > 0` phù hợp với số lượng của một dòng đơn hàng; một `StockBalance` hoặc `StockAdjustment` có thể cần quy tắc khác. `unitCode` cần được kiểm tra với danh mục đơn vị và dimension phù hợp trong miền. Như với mọi Value Object, cần định nghĩa `equals`/`hashCode` theo số lượng và đơn vị; đoạn mã tập trung vào các field mà JPA ánh xạ.

### `@ElementCollection` cho tập hợp Value Object

Nếu aggregate chứa một tập value object không có danh tính độc lập, có thể dùng `@ElementCollection`. Ví dụ, một hồ sơ có nhiều số điện thoại liên hệ hoặc một sản phẩm có nhiều kích thước đóng gói được mô hình như các value object.

```java
@ElementCollection
@CollectionTable(name = "product_dimensions",
        joinColumns = @JoinColumn(name = "product_id"))
private Set<Dimensions> dimensions = new HashSet<>();
```

`Dimensions` cần được ánh xạ bằng `@Embeddable`. Các phần tử được lưu trong bảng collection với khóa ngoại về entity sở hữu. Không có repository riêng cho từng `Dimensions`; việc thêm/xóa giá trị được quản lý qua aggregate root.

Ví dụ một embeddable đơn giản:

```java
import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.math.BigDecimal;
import java.util.Objects;

@Embeddable
@Access(AccessType.FIELD)
public class Dimensions {
    @Column(name = "length_value", precision = 12, scale = 3, nullable = false)
    private BigDecimal length;

    @Column(name = "width_value", precision = 12, scale = 3, nullable = false)
    private BigDecimal width;

    @Column(name = "height_value", precision = 12, scale = 3, nullable = false)
    private BigDecimal height;

    protected Dimensions() {
    }

    public Dimensions(BigDecimal length, BigDecimal width, BigDecimal height) {
        this.length = positive(length, "length");
        this.width = positive(width, "width");
        this.height = positive(height, "height");
    }

    private static BigDecimal positive(BigDecimal value, String name) {
        Objects.requireNonNull(value, name);
        if (value.signum() <= 0) {
            throw new IllegalArgumentException(name + " must be positive");
        }
        return value;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof Dimensions dimensions
                && length.compareTo(dimensions.length) == 0
                && width.compareTo(dimensions.width) == 0
                && height.compareTo(dimensions.height) == 0;
    }

    @Override
    public int hashCode() {
        return Objects.hash(length.stripTrailingZeros(),
                width.stripTrailingZeros(), height.stripTrailingZeros());
    }
}
```

Ví dụ lược bỏ đơn vị đo để tập trung vào cách ánh xạ. Mô hình thật nên gắn đơn vị hoặc quy ước đơn vị rõ ràng; nếu không, ba số đo có thể bị hiểu nhầm giữa centimet, milimet hoặc inch. Value Object cũng cần `equals`/`hashCode` theo các thành phần có ý nghĩa để collection hoạt động đúng theo giá trị.

Nếu phần tử cần định danh riêng, được tham chiếu độc lập, có trạng thái hoặc vòng đời riêng, hãy cân nhắc entity con thay vì `@ElementCollection`. Không nên dùng `@ElementCollection` cho một khái niệm thực chất là entity chỉ vì nó dễ ánh xạ hơn.

### Chọn giữa `@Embedded`, `@ElementCollection` và entity con

| Mô hình miền | Mapping thường phù hợp | Dấu hiệu nhận biết |
|---|---|---|
| Một Value Object đơn lẻ | `@Embedded` | Được xác định bằng các giá trị và thuộc về entity sở hữu |
| Tập hợp Value Object | `@ElementCollection` | Phần tử không có danh tính/vòng đời độc lập |
| Entity con trong cùng Aggregate | `@OneToMany`/`@ManyToOne` | Có danh tính trong aggregate và được root quản lý |
| Aggregate khác | Lưu ID hoặc kiểu ID nhúng | Có root và bất biến riêng, không thuộc vòng đời của aggregate hiện tại |

## Tham chiếu Aggregate khác bằng định danh

### Tránh liên kết ORM xuyên Aggregate

Giả sử `Order` cần biết khách hàng đặt đơn. Có thể viết:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
```

Nhưng cách này tạo một object relationship trực tiếp giữa hai aggregate. Nó có thể khiến `Order` tải `Customer`, cho phép code đi qua quan hệ để truy cập dữ liệu ngoài ranh giới, và khuyến khích cascade hoặc thao tác graph không phù hợp.

Thông thường, nên lưu ID:

```java
@Column(name = "customer_id", nullable = false, updatable = false)
private UUID customerId;
```

Khi use case cần thông tin khách hàng, application service hoặc query service truy vấn theo ID. `Order` không sở hữu vòng đời của `Customer` và không cần biết cấu trúc nội bộ của aggregate đó.

### Khi nào foreign key vật lý vẫn phù hợp?

Lưu ID không có nghĩa phải bỏ mọi foreign key trong database. Nếu hai bảng nằm trong cùng database và việc tham chiếu phải luôn trỏ đến bản ghi tồn tại, có thể tạo foreign key ở schema mà không ánh xạ thành object association trong domain model. Đây là quyết định ở tầng lưu trữ; nó không buộc domain code phải giữ object của aggregate khác.

Nếu hai bounded context có database độc lập hoặc vòng đời triển khai riêng, foreign key xuyên context thường không phù hợp. Khi đó, định danh được trao đổi qua hợp đồng tích hợp và tính hợp lệ của tham chiếu được xử lý theo chính sách đồng bộ của các context.

## Fetch Strategy: tải đúng dữ liệu cần thiết

### Lazy và Eager

Fetch strategy quyết định khi nào quan hệ được tải. JPA có mặc định khác nhau: `@ManyToOne` và `@OneToOne` mặc định `EAGER`; `@OneToMany` và `@ManyToMany` mặc định `LAZY`. Để tránh tải không chủ đích, thường nên khai báo `fetch = FetchType.LAZY` rõ ràng cho các quan hệ entity, đặc biệt là `@ManyToOne`.

`LAZY` có nghĩa dữ liệu quan hệ có thể được tải khi truy cập trong phạm vi persistence context còn hoạt động. Nếu truy cập sau khi session/entity manager đã đóng, có thể gặp `LazyInitializationException` trong Hibernate. Không nên giải quyết bằng cách bật EAGER cho mọi quan hệ; hãy xác định dữ liệu cần cho use case và tải rõ ràng.

### N+1 query

Giả sử màn hình danh sách tải 50 đơn hàng rồi đọc `order.customer` hoặc collection của từng đơn. Nếu mỗi lần truy cập kích hoạt một truy vấn riêng, hệ thống có thể thực hiện một truy vấn lấy danh sách và thêm nhiều truy vấn cho từng hàng — vấn đề thường gọi là N+1.

Các cách xử lý thường gặp:

- Dùng projection/DTO query lấy đúng trường cần hiển thị.
- Dùng `JOIN FETCH` cho quan hệ cần thiết trong một use case cụ thể.
- Dùng `@EntityGraph` để mô tả graph cần tải cho một phương thức repository.
- Chia truy vấn theo batch hoặc cấu hình batch fetching của Hibernate khi phù hợp.
- Tránh serialize entity trực tiếp, vì serializer có thể vô tình truy cập lazy association.

Không nên fetch join nhiều collection to-many cùng lúc mà không kiểm tra kết quả. Join có thể nhân số dòng, gây dữ liệu lặp, làm pagination sai hoặc tạo truy vấn rất lớn. Với màn hình đọc, projection thường đơn giản và hiệu quả hơn việc tải toàn bộ aggregate.

### Query Model không cần là Aggregate

DDD không yêu cầu mọi truy vấn đọc phải tải aggregate root. Với danh sách, dashboard hoặc báo cáo, query service có thể trả về projection được tối ưu theo nhu cầu đọc. Repository miền tập trung vào tải/lưu aggregate cho hành vi ghi; query model phục vụ đọc có thể dùng SQL, JPQL, Criteria API hoặc công cụ tìm kiếm phù hợp.

## Repository và transaction với JPA

### Repository nên làm việc ở cấp Aggregate Root

Một repository miền thường có các thao tác như tìm root theo ID và thêm root mới. Không nên tạo repository công khai cho mọi entity con nếu chúng chỉ có ý nghĩa trong aggregate.

```java
import java.util.Optional;
import java.util.UUID;

public interface OrderRepository {
    Optional<Order> findById(UUID orderId);
    void add(Order order);
}
```

JPA adapter triển khai interface này:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import java.util.Optional;
import java.util.UUID;

public class JpaOrderRepository implements OrderRepository {
    @PersistenceContext
    private EntityManager entityManager;

    @Override
    public Optional<Order> findById(UUID orderId) {
        return Optional.ofNullable(entityManager.find(Order.class, orderId));
    }

    @Override
    public void add(Order order) {
        entityManager.persist(order);
    }
}
```

Adapter này giả định `add` chỉ dùng cho aggregate mới và `findById` được gọi trong transaction. Khi một aggregate đã được load và đang managed, các thay đổi qua hành vi miền được Hibernate theo dõi (dirty checking); không cần gọi `persist` lại. Nếu dùng `merge` với entity detached, phải sử dụng instance được trả về bởi `merge`, vì `merge` sao chép trạng thái sang một managed instance khác.

### Transaction nằm ở Application Service

Application Service điều phối use case và đặt transaction boundary:

```java
import jakarta.transaction.Transactional;
import java.util.UUID;

public class PlaceOrderHandler {
    private final OrderRepository orders;

    public PlaceOrderHandler(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public void place(UUID orderId) {
        Order order = orders.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException("Order not found"));
        order.place();
        // Hibernate dirty checking ghi trạng thái và các thay đổi liên quan khi flush.
    }
}
```

Annotation trong ví dụ dùng `jakarta.transaction.Transactional`; dự án Spring cũng có thể dùng `org.springframework.transaction.annotation.Transactional`. Hãy dùng một cách nhất quán với transaction manager của ứng dụng. Transaction phải bao quanh thời gian aggregate được load, hành vi được gọi và thay đổi được flush/commit.

Không nên mở transaction trong từng phương thức nhỏ của entity. Entity không biết về EntityManager hoặc transaction manager. Cũng không nên giữ aggregate managed lâu qua nhiều request; persistence context và transaction nên có phạm vi rõ, thường là một use case ghi.

## Optimistic Locking với `@Version`

### Ngăn ghi đè thay đổi đồng thời

Khi hai transaction cùng tải một đơn hàng, cả hai có thể thấy version 4. Transaction đầu tiên cập nhật và commit, version tăng lên 5. Transaction thứ hai cố ghi với version 4 sẽ không cập nhật được và nhận lỗi optimistic locking. Ứng dụng cần tải lại trạng thái và quyết định trả lỗi xung đột hoặc thử lại theo chính sách.

```java
@Version
@Column(name = "version", nullable = false)
private long version;
```

`@Version` có thể dùng với các kiểu được JPA hỗ trợ như số nguyên hoặc timestamp tùy provider. Trường version do provider quản lý; không cho domain code tự đặt giá trị version.

### Lưu ý quan trọng với Aggregate có Entity con

Đặt `@Version` trên root là bước cần thiết nhưng không nên mặc định rằng mọi thay đổi trên mọi entity con đều tự động làm tăng version của root. Trong quan hệ hai chiều `@OneToMany(mappedBy = ...)`, phía collection của root là inverse side; việc cập nhật một entity con có thể chỉ làm thay đổi hàng của entity con và không buộc root version tăng theo cách nhóm mong muốn.

Nếu bất biến yêu cầu mọi thay đổi trong aggregate phải cạnh tranh trên cùng một version của root, cần chọn mapping và chiến lược khóa bảo đảm điều đó. Có thể dùng `EntityManager.lock(root, LockModeType.OPTIMISTIC_FORCE_INCREMENT)` để yêu cầu tăng version của root, hoặc dùng khóa pessimistic/thiết kế cập nhật phù hợp. Hãy kiểm thử hành vi với mapping và Hibernate version thực tế; không suy luận chỉ từ việc có annotation `@Version`.

Ví dụ yêu cầu force increment:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.LockModeType;

public void addLineWithAggregateVersion(Order order,
                                        UUID productId,
                                        Quantity quantity,
                                        Money price) {
    entityManager.lock(order, LockModeType.OPTIMISTIC_FORCE_INCREMENT);
    order.addLine(productId, quantity, price);
}
```

Đoạn mã là minh họa cho persistence/application adapter; `order` cần là entity đang managed và lời gọi phải nằm trong transaction. Không đặt `EntityManager` bên trong domain entity. Dùng force increment khi cần kiểm soát cạnh tranh ở cấp aggregate, không bật một cách máy móc cho mọi thao tác đọc.

### Xử lý lỗi optimistic locking

Khi version không khớp, transaction thường phải rollback. Ứng dụng có thể chuyển lỗi persistence thành kết quả như `ConcurrentModification` hoặc yêu cầu người dùng tải lại dữ liệu. Chỉ retry tự động khi thao tác có thể lặp an toàn, không tạo side effect trùng và có giới hạn số lần thử.

Với các thao tác như trừ tồn kho, giữ chỗ hoặc chuyển trạng thái, có thể cần thêm constraint hoặc conditional update ở database. Optimistic locking không thay thế mọi ràng buộc toàn vẹn.

## Ràng buộc Database và mapping

JPA annotation có thể mô tả một phần schema như `nullable = false`, `unique = true` và `@UniqueConstraint`. Hibernate còn cung cấp annotation mở rộng như `@Check`, nhưng đây không phải annotation chuẩn của JPA. Schema migration nên là nguồn kiểm soát chính trong môi trường triển khai thực tế.

Ví dụ DDL minh họa:

```sql
CREATE TABLE orders (
    id UUID PRIMARY KEY,
    customer_id UUID NOT NULL,
    status VARCHAR(24) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE order_lines (
    id UUID PRIMARY KEY,
    order_id UUID NOT NULL REFERENCES orders(id),
    product_id UUID NOT NULL,
    quantity_amount NUMERIC(19, 4) NOT NULL CHECK (quantity_amount > 0),
    quantity_unit VARCHAR(12) NOT NULL,
    unit_price_amount NUMERIC(19, 4) NOT NULL CHECK (unit_price_amount >= 0),
    unit_price_currency CHAR(3) NOT NULL
);
```

Ví dụ không tạo foreign key tới `customer` hoặc `product` vì chúng được mô hình như aggregate khác và có thể thuộc context/kho dữ liệu khác. Nếu các bảng cùng một database và chính sách lưu trữ yêu cầu bảo đảm tham chiếu, có thể thêm FK vật lý mà vẫn giữ scalar ID trong domain model.

Các constraint bảo vệ dữ liệu ở tầng database; aggregate vẫn phải kiểm tra quy tắc nghiệp vụ để đưa ra hành vi và lỗi có ý nghĩa. Không phải mọi bất biến đều có thể biểu diễn bằng `CHECK` trên một hàng. Ví dụ “đơn đã đặt phải có ít nhất một dòng” cần logic ở root hoặc cơ chế lưu trữ bổ sung phù hợp.

Trong production, nên dùng migration có phiên bản để thay đổi schema có kiểm soát. Hibernate schema generation hữu ích khi phát triển hoặc kiểm tra, nhưng không nên để `ddl-auto=update` tự thay đổi schema production mà không qua review. Nhiều ứng dụng đặt Hibernate ở chế độ `validate` để kiểm tra mapping so với schema do migration quản lý.

## JPA Lifecycle Callback không thay thế Domain Behavior

JPA cung cấp callback như `@PrePersist`, `@PreUpdate`, `@PostLoad` và `@PostPersist`. Chúng phù hợp với một số việc kỹ thuật như gán timestamp lưu trữ hoặc chuẩn bị dữ liệu persistence đơn giản. Không nên đặt chính sách miền quan trọng vào callback.

Ví dụ, không nên dựa vào `@PreUpdate` để quyết định đơn hàng có được hủy hay không. Callback có thể chạy trong ngữ cảnh flush, không diễn đạt rõ ý định nghiệp vụ và không thay thế hành vi `order.cancel(reason)`. Tương tự, không nên publish domain event trực tiếp từ `@PostPersist`: callback không tự bảo đảm message được gửi cùng transaction một cách bền vững.

Nếu aggregate phát sinh Domain Event, có thể thu thập sự kiện sau khi hành vi miền thành công và ghi outbox record trong cùng transaction với aggregate. Một relay riêng gửi integration event sau commit. Cách này tránh việc database commit thành công nhưng message bị mất hoặc message được gửi cho một thay đổi sau đó rollback.

## Những lỗi thường gặp khi ánh xạ Aggregate

| Sai lầm | Hệ quả | Cách điều chỉnh |
|---|---|---|
| Tạo repository cho từng entity con | Bỏ qua Aggregate Root và bất biến | Repository công khai ở cấp root; root quản lý entity con |
| Cho phép setter công khai trên mọi field | Caller có thể tạo trạng thái không hợp lệ | Dùng hành vi miền có tên và field access |
| Dùng `@ManyToOne` tới aggregate khác theo thói quen | Tạo liên kết object và tải dữ liệu xuyên ranh giới | Lưu ID của aggregate root được tham chiếu |
| Cascade `REMOVE` sang Customer/Product | Xóa nhầm dữ liệu thuộc aggregate khác | Cascade chỉ trong phạm vi sở hữu vòng đời |
| Bật `orphanRemoval` cho mọi collection | Xóa dữ liệu khi chỉ bỏ tham chiếu | Chỉ bật khi entity con thực sự không tồn tại độc lập |
| Không cập nhật phía sở hữu quan hệ | Hibernate không lưu quan hệ như mong muốn | Root cập nhật collection và field owning side |
| Dùng EAGER cho mọi quan hệ | Tải đồ thị lớn, truy vấn khó kiểm soát | Mặc định rõ LAZY và fetch theo use case |
| Trả entity trực tiếp qua API | Lazy loading, vòng tham chiếu và lộ cấu trúc nội bộ | Dùng DTO/projection |
| Dùng `@Data` cho entity | Setter, equals/hashCode và toString có thể kéo cả graph | Viết API và equality có chủ đích |
| Nghĩ `@Version` ở root tự bao phủ mọi thay đổi child | Có thể bỏ sót xung đột ở cấp aggregate | Kiểm tra mapping; force increment hoặc khóa phù hợp |
| Đặt domain logic trong callback ORM | Quy tắc khó nhìn thấy và khó kiểm thử | Đặt hành vi trong entity/aggregate/domain policy |
| Để Hibernate tự sửa schema production | Thay đổi schema khó review và rollback | Dùng migration có phiên bản, Hibernate validate |

## Quy trình ánh xạ một Aggregate

1. **Xác định ranh giới miền:** liệt kê root, entity con, value object và aggregate reference trước khi viết annotation.
2. **Xác định vòng đời:** quyết định đối tượng nào được tạo/xóa cùng root và đối tượng nào có vòng đời độc lập.
3. **Chọn mapping:** `@Entity` cho entity, `@Embeddable` cho value object, `@ElementCollection` cho tập value object, quan hệ entity cho thành phần sở hữu trong aggregate.
4. **Chỉ định owning side:** xác định field chứa khóa ngoại và viết helper để cập nhật cả hai phía trong bộ nhớ.
5. **Giữ root làm cổng truy cập:** repository tải root; entity con không được sửa độc lập từ bên ngoài.
6. **Chọn cascade và fetch:** cascade theo vòng đời, orphan removal theo quyền sở hữu; tải quan hệ theo use case.
7. **Thiết kế transaction và concurrency:** transaction bao trùm một use case ghi; version/lock bảo vệ các thay đổi cạnh tranh.
8. **Bổ sung constraint và migration:** bảo vệ tính toàn vẹn dữ liệu ở DB và kiểm thử schema thực tế.
9. **Kiểm thử hành vi và mapping:** kiểm tra bất biến miền, cascade, orphan removal, lazy loading, optimistic lock và rollback.

## Checklist rà soát

- [ ] Aggregate Root được ánh xạ thành entity và có định danh ổn định.
- [ ] Repository làm việc ở cấp Aggregate Root.
- [ ] Entity con chỉ được thay đổi qua hành vi của root.
- [ ] Quan hệ ORM chỉ mô tả ownership trong aggregate khi phù hợp.
- [ ] Aggregate khác được tham chiếu bằng ID, không cần object graph trực tiếp.
- [ ] Value Object dùng `@Embedded`, `@Embeddable` hoặc `@ElementCollection` phù hợp.
- [ ] Owning side và inverse side được cập nhật nhất quán.
- [ ] Cascade và orphan removal phản ánh đúng vòng đời nghiệp vụ.
- [ ] Không cascade xóa qua ranh giới aggregate.
- [ ] Fetch strategy được chọn rõ; đã xem xét N+1 và projection cho read use case.
- [ ] Entity tuân thủ yêu cầu constructor và proxy của JPA/Hibernate.
- [ ] Không dùng setter tổng quát hoặc Lombok `@Data` làm suy yếu bất biến.
- [ ] `@Version` và chiến lược khóa phù hợp với mapping thực tế, kể cả entity con.
- [ ] Transaction bao quanh việc tải, thay đổi và lưu aggregate.
- [ ] Domain Event được công bố sau commit hoặc qua outbox đáng tin cậy.
- [ ] Database constraints và migration bảo vệ tính toàn vẹn dữ liệu.
- [ ] Mapping được kiểm thử với phiên bản JPA/Hibernate và database thực tế.

## Kết luận

Ánh xạ Aggregate với JPA và Hibernate cần giữ rõ quyền sở hữu và ranh giới nhất quán của mô hình miền. Aggregate Root là điểm truy cập và lưu trữ; entity con thuộc vòng đời của root có thể dùng quan hệ ORM cùng cascade phù hợp; Value Object được nhúng hoặc lưu như collection giá trị; aggregate khác thường được tham chiếu bằng ID. Khi kết hợp fetch strategy có chủ đích, repository ở cấp root, transaction rõ ràng, optimistic locking và database constraints, persistence layer có thể hỗ trợ mô hình DDD mà không làm mất ý nghĩa nghiệp vụ.

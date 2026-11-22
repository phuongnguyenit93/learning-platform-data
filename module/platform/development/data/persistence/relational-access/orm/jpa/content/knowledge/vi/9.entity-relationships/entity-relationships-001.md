# Chuyển quan hệ nghiệp vụ thành liên kết giữa các entity trong JPA

Một mô hình nghiệp vụ thường bắt đầu bằng những câu như: **“Một khách hàng có nhiều đơn hàng”**, **“Mỗi đơn hàng gồm nhiều dòng hàng”**, **“Một sản phẩm có thể xuất hiện trong nhiều đơn hàng”**. Từ các câu này, lập trình viên phải xác định đối tượng nào là entity, quan hệ có lực lượng (*cardinality*) thế nào, khóa ngoại nên nằm ở bảng nào, và liên kết Java Persistence API (JPA) nào phù hợp.

Điều quan trọng là **quan hệ nghiệp vụ không tự động tương ứng với một annotation JPA duy nhất**. Cùng một mô tả “có nhiều” có thể được hiện thực bằng `@OneToMany`, `@ManyToMany`, một entity trung gian hoặc chỉ một truy vấn theo khóa ngoại. Lựa chọn đúng phụ thuộc vào quy tắc nghiệp vụ, vòng đời dữ liệu và cách hệ thống cần truy vấn/cập nhật.

Bài học này đi từ **ngôn ngữ nghiệp vụ → mô hình entity → quan hệ dữ liệu → annotation JPA → thao tác giao dịch**, với một ví dụ nhất quán về khách hàng, đơn hàng, dòng hàng và sản phẩm.

## 1. Bắt đầu từ câu chuyện nghiệp vụ, không bắt đầu từ annotation

Giả sử hệ thống bán hàng có yêu cầu:

1. Một **Customer** có thể tạo nhiều **PurchaseOrder**.
2. Mỗi **PurchaseOrder** phải thuộc đúng một **Customer**.
3. Một **PurchaseOrder** gồm ít nhất một **OrderLine** khi xác nhận đặt hàng.
4. Mỗi **OrderLine** tham chiếu đúng một **Product** và có số lượng, đơn giá tại thời điểm đặt.
5. Một **Product** có thể được tham chiếu bởi nhiều **OrderLine**.
6. Khi hủy một dòng hàng khỏi đơn hàng đang chỉnh sửa, dòng đó không còn tồn tại độc lập.
7. Không xóa lịch sử sản phẩm chỉ vì một đơn hàng bị xóa.

Từ những câu này, ta chưa vội viết `@OneToMany` hay `@ManyToMany`. Trước tiên phải xác định:

- **Entity nào có định danh và vòng đời riêng?**
- **Lực lượng mỗi phía:** một, nhiều, có thể bằng không hay bắt buộc phải có?
- **Có chiều tham chiếu nào thực sự cần trong code?**
- **Dòng nào sở hữu khóa ngoại hoặc bảng nối?**
- **Entity con có phụ thuộc vòng đời vào entity cha không?**
- **Có dữ liệu nghiệp vụ gắn với chính quan hệ không?**
- **Xóa/đổi liên kết có được phép không, và được thực hiện trong transaction nào?**

Ví dụ các câu trả lời ban đầu:

| Quan hệ nghiệp vụ | Bản chất dữ liệu | Cách ánh xạ thường phù hợp |
|---|---|---|
| Customer tạo PurchaseOrder | Một khách có 0..n đơn; mỗi đơn thuộc 1 khách | `PurchaseOrder → Customer` bằng `@ManyToOne` |
| PurchaseOrder gồm OrderLine | Một đơn có 0..n dòng trong giai đoạn soạn; dòng thuộc 1 đơn | `@OneToMany` + `@ManyToOne`, cân nhắc `orphanRemoval` |
| OrderLine nói tới Product | Nhiều dòng có thể tham chiếu một sản phẩm | `@ManyToOne` từ OrderLine tới Product |
| OrderLine có quantity và unitPrice | Dữ liệu thuộc bản thân dòng đơn | `OrderLine` là entity riêng thay vì quan hệ Many-to-Many trần |
| Customer có địa chỉ giao hàng | Có thể là dữ liệu snapshot gắn vào đơn | `@Embeddable` hoặc entity riêng tùy nhu cầu |
| Nhân viên được gán nhiều vai trò | Nhiều-nhiều nếu liên kết không có dữ liệu riêng | `@ManyToMany` hoặc entity gán quyền nếu có metadata |

Các quyết định thiết kế phải dựa trên những câu hỏi đó, không chỉ trên số nhiều trong tên thuộc tính Java.

## 2. Phân biệt entity, value object và một thuộc tính đơn giản

Trước khi ánh xạ quan hệ, cần xác định đối tượng có phải entity không.

### 2.1. Entity có danh tính bền vững

`Customer`, `PurchaseOrder` và `Product` thường có khóa chính, vòng đời, quy tắc cập nhật và được tham chiếu độc lập. Chúng phù hợp để khai báo `@Entity`.

Ví dụ:

~~~java
@Entity
@Table(name = "product")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", nullable = false, unique = true, length = 40)
    private String sku;

    @Column(name = "name", nullable = false, length = 200)
    private String name;

    protected Product() {}

    public Product(String sku, String name) {
        this.sku = sku;
        this.name = name;
    }

    public Long getId() {
        return id;
    }
}
~~~

`Product` có định danh riêng. Một đơn hàng tham chiếu sản phẩm không có nghĩa là đơn hàng sở hữu vòng đời của sản phẩm đó.

### 2.2. Value object thường được nhúng

Ví dụ địa chỉ giao hàng là ảnh chụp (*snapshot*) của thông tin khách nhập lúc đặt đơn:

~~~java
@Embeddable
public class ShippingAddress {

    @Column(name = "ship_street", nullable = false)
    private String street;

    @Column(name = "ship_city", nullable = false)
    private String city;

    protected ShippingAddress() {}

    public ShippingAddress(String street, String city) {
        this.street = street;
        this.city = city;
    }
}
~~~

Trong entity đơn hàng:

~~~java
@Embedded
private ShippingAddress shippingAddress;
~~~

Nếu địa chỉ chỉ là tập hợp thuộc tính không có định danh độc lập, `@Embedded` thường rõ hơn tạo entity `Address` và thêm một quan hệ `@ManyToOne` không cần thiết. Ngược lại, nếu doanh nghiệp quản lý **sổ địa chỉ** với ID, quyền chia sẻ và vòng đời riêng, `Address` có thể là entity.

**Quy tắc:** có hai object xuất hiện trong sơ đồ nghiệp vụ chưa đủ để kết luận chúng phải liên kết bằng foreign key. Cần xem chúng có identity riêng hay một object chỉ là giá trị của object khác.

## 3. Từ mô tả nghiệp vụ đến cardinality

*Cardinality* mô tả số lượng instance bên này có thể liên kết với bên kia.

| Mô tả | Cardinality thường dùng | Quan hệ JPA ứng viên |
|---|---|---|
| Một tài khoản có tối đa một hồ sơ | 1 ↔ 0..1 hoặc 1 ↔ 1 | `@OneToOne` |
| Một khách hàng có nhiều đơn hàng | 1 ↔ 0..n | `@ManyToOne` / `@OneToMany` |
| Một đơn hàng có nhiều dòng hàng | 1 ↔ 1..n ở mức quy tắc đặt hàng | `@OneToMany` / `@ManyToOne` |
| Mỗi dòng hàng tham chiếu một sản phẩm | n ↔ 1 | `@ManyToOne` |
| Mỗi học viên học nhiều khóa, mỗi khóa có nhiều học viên | n ↔ n | `@ManyToMany` hoặc entity liên kết |
| Một nhân viên có thể chưa có quản lý | n ↔ 0..1, tự liên kết | `@ManyToOne` tới chính loại entity |

**Cardinality không đồng nghĩa với optionality.** Ví dụ một khách có 0 đơn hàng là hợp lệ, nhưng mỗi đơn hàng phải có đúng 1 khách. Ở phía `PurchaseOrder.customer`, thuộc tính không được phép `null`; ở phía danh sách đơn của `Customer`, danh sách rỗng lại hoàn toàn bình thường.

Đồng thời, yêu cầu “một đơn hàng phải có ít nhất một dòng khi xác nhận” thường cần được kiểm tra ở **service/domain**; chỉ dùng `@OneToMany` không tự tạo constraint “ít nhất một phần tử” trong DB.

## 4. Quan hệ nhiều-một: Mỗi đơn hàng thuộc một khách hàng

Đây là liên kết trọng tâm để biểu diễn “nhiều đơn hàng thuộc cùng một khách”.

### 4.1. Sơ đồ dữ liệu

~~~text
customer                       purchase_order
-----------------------        ---------------------------
id (PK)  <-------------------- customer_id (FK, NOT NULL)
email                           id (PK)
name                            order_status
                                created_at

1 Customer  <----------  N PurchaseOrder
~~~

Khóa ngoại `purchase_order.customer_id` trỏ tới `customer.id`. Vì khóa ngoại được lưu trong bảng đơn hàng, quan hệ từ `PurchaseOrder` sang `Customer` là phía thuận tiện để cấu hình và cập nhật.

### 4.2. Entity Customer

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "email", nullable = false, unique = true, length = 254)
    private String email;

    @Column(name = "full_name", nullable = false, length = 150)
    private String fullName;

    protected Customer() {}

    public Customer(String email, String fullName) {
        this.email = email;
        this.fullName = fullName;
    }

    public Long getId() {
        return id;
    }
}
~~~

Chưa cần khai báo `List<PurchaseOrder>` trên Customer. Nếu nghiệp vụ chỉ cần từ đơn hàng truy cập khách hàng, **quan hệ một chiều** từ `PurchaseOrder` sang `Customer` đã đủ.

### 4.3. Entity PurchaseOrder

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    protected PurchaseOrder() {}

    public PurchaseOrder(Customer customer) {
        if (customer == null) {
            throw new IllegalArgumentException("Customer is required");
        }
        this.customer = customer;
    }

    public Long getId() {
        return id;
    }

    public Customer getCustomer() {
        return customer;
    }
}
~~~

Ý nghĩa:

- `@ManyToOne`: nhiều đơn hàng có thể tham chiếu cùng một `Customer`.
- `@JoinColumn(name = "customer_id")`: cột foreign key nằm trong bảng `purchase_order`.
- `optional = false`: liên kết entity được yêu cầu tồn tại theo metadata JPA.
- `nullable = false`: cột khóa ngoại được mô tả không cho phép `NULL` khi sinh schema.
- `fetch = LAZY`: đề nghị provider chỉ tải khách hàng khi thực sự cần. Việc trì hoãn tải to-one còn phụ thuộc khả năng triển khai/provider.
- Không đặt `cascade = CascadeType.REMOVE` cho customer: xóa một đơn hàng không nên xóa khách hàng có thể còn đơn khác.

Cấu hình mapping hỗ trợ ràng buộc; **foreign key thực tế trong DB** mới trực tiếp bảo vệ tính toàn vẹn tham chiếu khi có nhiều đường ghi dữ liệu.

### 4.4. SQL tương ứng

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(254) NOT NULL UNIQUE,
    full_name VARCHAR(150) NOT NULL
);

CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer(id)
);
~~~

`@JoinColumn` cho JPA biết cách liên kết; constraint `FOREIGN KEY` và `NOT NULL` trong DB đảm bảo dữ liệu không thể tham chiếu khóa khách hàng không tồn tại theo quy tắc DB.

## 5. Có nên thêm chiều ngược lại trên Customer?

Nếu một màn hình cần duyệt các đơn của khách, có thể thêm:

~~~java
@OneToMany(mappedBy = "customer")
private List<PurchaseOrder> orders = new ArrayList<>();
~~~

Trong `Customer`:

~~~java
public List<PurchaseOrder> getOrders() {
    return Collections.unmodifiableList(orders);
}
~~~

Ở đây `mappedBy = "customer"` là **tên thuộc tính Java** `customer` trong entity `PurchaseOrder`. Nó không phải tên bảng `customer` hay tên cột `customer_id`.

### 5.1. Phía sở hữu quan hệ (*owning side*)

Trong quan hệ hai chiều:

~~~text
Customer.orders
    @OneToMany(mappedBy = "customer")
         |
         | inverse side
         v
PurchaseOrder.customer
    @ManyToOne
    @JoinColumn(name = "customer_id")
         |
         | owning side
         v
purchase_order.customer_id
~~~

`PurchaseOrder.customer` là **owning side** trong ánh xạ này, vì nó điều khiển cột khóa ngoại. `Customer.orders` là phía đối ứng (*inverse side*) cho phép duyệt chiều ngược.

**Thêm một order vào `customer.orders` mà không cập nhật `order.customer` là chưa đủ để JPA ghi đúng FK.** Với liên kết hai chiều, code ứng dụng có trách nhiệm giữ hai phía nhất quán trong bộ nhớ.

### 5.2. Helper duy trì cả hai phía

Một thiết kế có thể cung cấp phương thức nghiệp vụ để gán khách cho đơn, thay vì công khai setter và list cho bất kỳ caller nào sửa:

~~~java
// Trong Customer (ví dụ bổ sung cho bản entity hai chiều)
void registerOrder(PurchaseOrder order) {
    if (!orders.contains(order)) {
        orders.add(order);
    }
}

void unregisterOrder(PurchaseOrder order) {
    orders.remove(order);
}

// Trong PurchaseOrder
public void assignCustomer(Customer newCustomer) {
    if (newCustomer == null) {
        throw new IllegalArgumentException("Customer is required");
    }
    if (this.customer == newCustomer) {
        return;
    }

    Customer oldCustomer = this.customer;
    this.customer = newCustomer; // owning side
    if (oldCustomer != null) {
        oldCustomer.unregisterOrder(this);
    }
    newCustomer.registerOrder(this);
}
~~~

Đoạn code là minh họa cách đồng bộ hai phía, giả định lớp đã khai báo `Customer.orders` và các helper cùng package để truy cập được. Nếu nghiệp vụ không cho phép đổi chủ đơn, constructor có thể gán customer một lần và hệ thống không cần cung cấp chức năng `assignCustomer`.

Giữ quan hệ một chiều thường đơn giản và ít rủi ro hơn nếu không có use case cần duyệt chiều ngược. Khi màn hình cần danh sách đơn của khách, một repository query theo `customer.id` cũng có thể là lựa chọn tốt mà không cần mở rộng entity bằng collection.

## 6. Quan hệ một-nhiều: PurchaseOrder sở hữu các dòng hàng

Đơn hàng gồm những dòng hàng; mỗi dòng có số lượng và đơn giá lúc đặt. Đây là trường hợp vòng đời con phụ thuộc cha rất điển hình.

### 6.1. Vì sao OrderLine nên là entity?

Một quan hệ `PurchaseOrder ↔ Product` “nhiều-nhiều” chỉ nói đơn hàng chứa sản phẩm, nhưng chưa mô tả:

- Số lượng của mỗi sản phẩm trong đơn.
- Đơn giá tại thời điểm mua (khác giá hiện tại của Product).
- Khuyến mại, ghi chú hoặc thuế của từng dòng.
- Quy tắc sửa/xóa từng dòng.
- Khả năng cùng sản phẩm xuất hiện ở nhiều dòng có mục đích khác nhau.

Vì có dữ liệu và vòng đời riêng của từng dòng, tạo entity `OrderLine` là cách mô hình hóa giàu ý nghĩa hơn `@ManyToMany` trực tiếp giữa `PurchaseOrder` và `Product`.

Sơ đồ:

~~~text
purchase_order 1 ---- N order_line N ---- 1 product

order_line:
    id (PK)
    order_id (FK)
    product_id (FK)
    quantity
    unit_price_at_order
~~~

### 6.2. Entity OrderLine

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.math.BigDecimal;

@Entity
@Table(name = "order_line")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "product_id", nullable = false)
    private Product product;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    @Column(
        name = "unit_price_at_order",
        nullable = false,
        precision = 14,
        scale = 2
    )
    private BigDecimal unitPriceAtOrder;

    protected OrderLine() {}

    OrderLine(
        PurchaseOrder order,
        Product product,
        int quantity,
        BigDecimal unitPriceAtOrder
    ) {
        if (order == null || product == null || unitPriceAtOrder == null) {
            throw new IllegalArgumentException("Required order line data");
        }
        if (quantity <= 0 || unitPriceAtOrder.signum() < 0) {
            throw new IllegalArgumentException("Invalid quantity or price");
        }
        this.order = order;
        this.product = product;
        this.quantity = quantity;
        this.unitPriceAtOrder = unitPriceAtOrder;
    }

    void detachFromOrder() {
        this.order = null;
    }

    public PurchaseOrder getOrder() {
        return order;
    }

    public BigDecimal getLineTotal() {
        return unitPriceAtOrder.multiply(BigDecimal.valueOf(quantity));
    }
}
~~~

Đoạn code giả định `PurchaseOrder` và `OrderLine` có quyền truy cập package-private đến nhau khi cùng package.

`OrderLine.product` **chỉ là tham chiếu tới Product**. Không có lý do để xóa Product khi xóa OrderLine; cũng không nên cascade `PERSIST` bừa bãi sang Product nếu sản phẩm phải được tạo trong quy trình riêng.

### 6.3. Bổ sung collection trong PurchaseOrder

~~~java
import jakarta.persistence.CascadeType;
import jakarta.persistence.OneToMany;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines = new ArrayList<>();

public List<OrderLine> getLines() {
    return Collections.unmodifiableList(lines);
}

public void addLine(
    Product product,
    int quantity,
    BigDecimal unitPrice
) {
    OrderLine line = new OrderLine(this, product, quantity, unitPrice);
    lines.add(line);
}

public void removeLine(OrderLine line) {
    if (lines.remove(line)) {
        line.detachFromOrder();
    }
}
~~~

Ý nghĩa:

- `mappedBy = "order"` trỏ tới field `OrderLine.order`, tức owning side của FK.
- `cascade = ALL` chuyển tiếp các thao tác persistence liên quan từ đơn hàng sang dòng hàng. Đây là lựa chọn phù hợp **khi vòng đời dòng hàng thuộc đơn hàng**.
- `orphanRemoval = true` đánh dấu xóa một dòng hàng được tách khỏi quan hệ chứa nó theo ngữ nghĩa JPA, phù hợp khi dòng không còn ý nghĩa nếu không nằm trong đơn.
- Helper `addLine` tạo line với `order = this` để giữ hai phía đồng bộ.
- Helper `removeLine` xóa khỏi collection và cập nhật field `order` trong bộ nhớ.

Không trực tiếp thay `lines` bằng một list khác khi muốn thêm hoặc xóa từng dòng; với entity managed và `orphanRemoval`, giữ collection do JPA quản lý và thao tác thông qua helper thường an toàn hơn.

### 6.4. Schema tương ứng

~~~sql
CREATE TABLE product (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(40) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL
);

CREATE TABLE order_line (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price_at_order DECIMAL(14, 2) NOT NULL,

    CONSTRAINT fk_line_order
        FOREIGN KEY (order_id) REFERENCES purchase_order(id),
    CONSTRAINT fk_line_product
        FOREIGN KEY (product_id) REFERENCES product(id),
    CONSTRAINT ck_line_quantity CHECK (quantity > 0),
    CONSTRAINT ck_line_price CHECK (unit_price_at_order >= 0)
);
~~~

`OrderLine` là một entity dù nó phụ thuộc nghiệp vụ vào đơn hàng. Định danh riêng của dòng giúp cập nhật, xóa và truy xuất chính xác từng dòng; có thể chọn khóa tổng hợp khi mô hình thật cần, nhưng đó là quyết định khác với cardinality.

### 6.5. Quy tắc tối thiểu một dòng hàng

`@OneToMany` cho phép collection rỗng. Nếu một đơn hàng chỉ được xác nhận khi có ít nhất một dòng, kiểm tra ở operation nghiệp vụ:

~~~java
public void confirm() {
    if (lines.isEmpty()) {
        throw new IllegalStateException(
            "Cannot confirm an order without lines"
        );
    }

    this.status = OrderStatus.CONFIRMED;
}
~~~

`OrderStatus` và field `status` là thành phần bổ sung tùy mô hình. Quy tắc “ít nhất một dòng” không xuất hiện tự động chỉ vì collection là `@OneToMany`.

**Kết luận nghiệp vụ:** mapping nói các bản ghi được nối bằng gì; domain/service nói **khi nào một tổ hợp dữ liệu là hợp lệ**.

## 7. Phân biệt owning side và chiều điều hướng

Hai câu hỏi rất dễ bị lẫn:

1. **Từ class nào code có thể đi sang class nào?** → Chiều điều hướng (unidirectional/bidirectional).
2. **Field nào làm thay đổi quan hệ trong database?** → Owning side của liên kết.

Ví dụ:

~~~java
// PurchaseOrder
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id")
private Customer customer;

// Customer
@OneToMany(mappedBy = "customer")
private List<PurchaseOrder> orders;
~~~

Code có thể điều hướng **hai chiều**; nhưng FK vẫn nằm trên bảng `purchase_order`, với `PurchaseOrder.customer` là owning side.

| Thuật ngữ | Nội dung | Cách nhận diện |
|---|---|---|
| Unidirectional | Chỉ một phía có thuộc tính tham chiếu phía kia | Một field quan hệ |
| Bidirectional | Hai phía cùng khai báo thuộc tính phản chiếu quan hệ | Hai field có mapping khớp nhau |
| Owning side | Phía JPA dùng để điều khiển liên kết khi ghi DB | Với Many-to-One/One-to-Many hai chiều, thường phía `@ManyToOne` |
| Inverse side | Phía khai báo `mappedBy` | Không tự quyết định FK |
| `@JoinColumn` | Cột khóa ngoại để nối tới bản ghi đích | Đặt trên phía phù hợp với mapping |
| `mappedBy` | Tên field/property Java ở phía owning | Không phải tên cột SQL |

Đừng đặt `mappedBy = "customer_id"` khi field bên kia là `customer`; đúng là `mappedBy = "customer"`.

### 7.1. Quan hệ một chiều One-to-Many không có mappedBy

JPA cũng hỗ trợ một `@OneToMany` không có chiều `@ManyToOne` tương ứng. Tùy cấu hình, provider có thể sử dụng join table mặc định; nếu chỉ định thêm `@JoinColumn` có thể sử dụng FK tại bảng con theo mapping được hỗ trợ.

Nếu database có FK `order_line.order_id` và domain cũng cần từ `OrderLine` biết đơn cha, quan hệ hai chiều với `mappedBy` thường rõ ràng. Không nên thêm chiều hai chỉ để thỏa một quy tắc hình thức khi code không cần nó.

## 8. `@OneToOne`: Khi mỗi phía có tối đa một đối tượng

Một yêu cầu: “Mỗi tài khoản có tối đa một hồ sơ cá nhân, và mỗi hồ sơ thuộc đúng một tài khoản.”

Sơ đồ database:

~~~text
account                          account_profile
------------------------         -------------------------------
id (PK)  <---------------------  account_id (FK, UNIQUE, NOT NULL)
email                            id (PK)
                                 bio
~~~

Việc đặt **UNIQUE** trên `account_profile.account_id` giúp thực thi “một account có tối đa một profile” ở database.

Entity profile:

~~~java
@Entity
@Table(name = "account_profile")
public class AccountProfile {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(
        name = "account_id",
        nullable = false,
        unique = true
    )
    private Account account;

    @Column(name = "bio")
    private String bio;

    protected AccountProfile() {}

    public AccountProfile(Account account, String bio) {
        this.account = account;
        this.bio = bio;
    }
}
~~~

Nếu cần điều hướng từ account sang profile, trong `Account` có thể thêm:

~~~java
@OneToOne(mappedBy = "account", fetch = FetchType.LAZY)
private AccountProfile profile;
~~~

`mappedBy = "account"` trỏ tới field Java `AccountProfile.account`. Phía `AccountProfile` giữ FK và là owning side. Trong JPA, `@OneToOne` mặc định có fetch `EAGER`; chỉ định `LAZY` là một yêu cầu/lựa chọn cần kiểm tra hỗ trợ của provider, đặc biệt ở phía inverse.

### 8.1. Cấu trúc khóa ngoại chia sẻ khóa chính

Nếu vòng đời hồ sơ hoàn toàn gắn với tài khoản, một giải pháp khác là dùng `@MapsId` để `AccountProfile` chia sẻ khóa chính với `Account`:

~~~java
@Entity
public class AccountProfile {

    @Id
    private Long id;

    @MapsId
    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "account_id")
    private Account account;

    protected AccountProfile() {}
}
~~~

Trong cách này `account_profile.account_id` vừa là primary key vừa là FK tới `account.id`. Đây là ánh xạ phù hợp cho quan hệ một-một phụ thuộc định danh; không cần thiết với mọi trường hợp One-to-One.

### 8.2. Có nhất thiết One-to-One phải có hai collection/field?

Không. Nhiều trường hợp chỉ cần `AccountProfile.account`. Nếu màn hình hồ sơ luôn được tìm theo account ID, repository query cũng có thể đáp ứng. Chọn chiều điều hướng theo các use case, tránh tạo đồ thị object quá rộng.

## 9. `@ManyToMany`: Khi một liên kết không có dữ liệu nghiệp vụ riêng

Tình huống học viên tham gia khóa học:

- Một học viên học nhiều khóa.
- Một khóa có nhiều học viên.
- Ban đầu chỉ cần biết “đã tham gia” mà không có thêm thuộc tính riêng của lần tham gia.

Có thể dùng bảng nối `student_course`:

~~~text
student 1 -- N student_course N -- 1 course

student_course:
    student_id (FK)
    course_id  (FK)
    PRIMARY KEY (student_id, course_id)
~~~

Mapping đơn giản:

~~~java
@Entity
public class Student {

    @Id
    private Long id;

    @ManyToMany
    @JoinTable(
        name = "student_course",
        joinColumns = @JoinColumn(name = "student_id"),
        inverseJoinColumns = @JoinColumn(name = "course_id")
    )
    private Set<Course> courses = new HashSet<>();
}
~~~

Chiều ngược, nếu cần:

~~~java
@Entity
public class Course {

    @Id
    private Long id;

    @ManyToMany(mappedBy = "courses")
    private Set<Student> students = new HashSet<>();
}
~~~

`Student.courses` là owning side của join table trong ví dụ. Với quan hệ hai chiều, cần giữ collection hai phía đồng bộ bằng helper nếu cập nhật trong bộ nhớ.

**Không cấu hình `CascadeType.REMOVE` mặc định cho Many-to-Many giữa các entity độc lập.** Xóa một học viên không được kéo theo xóa khóa học mà nhiều người khác đang tham gia.

### 9.1. Khi quan hệ có thuộc tính: Dùng entity trung gian

Nghiệp vụ bổ sung: “Mỗi lần học viên ghi danh có thời điểm ghi danh, trạng thái và điểm cuối khóa.”

Lúc này quan hệ trở thành một khái niệm nghiệp vụ riêng: `Enrollment`.

~~~text
Student 1 ---- N Enrollment N ---- 1 Course
                       |
                       +-- enrolledAt
                       +-- status
                       +-- finalGrade
~~~

Định nghĩa:

~~~java
@Entity
@Table(
    name = "enrollment",
    uniqueConstraints = @UniqueConstraint(
        columnNames = {"student_id", "course_id"}
    )
)
public class Enrollment {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "student_id", nullable = false)
    private Student student;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "course_id", nullable = false)
    private Course course;

    @Column(name = "enrolled_at", nullable = false)
    private Instant enrolledAt;

    protected Enrollment() {}

    public Enrollment(Student student, Course course, Instant enrolledAt) {
        this.student = student;
        this.course = course;
        this.enrolledAt = enrolledAt;
    }
}
~~~

`Instant` đến từ `java.time.Instant`. Mỗi enrollment có identity và dữ liệu riêng; các khóa ngoại cùng UNIQUE constraint đảm bảo một cặp học viên–khóa học có tối đa một dòng theo quy tắc này.

Nếu nghiệp vụ cho phép học lại cùng khóa ở nhiều kỳ, UNIQUE trên cặp `(student_id, course_id)` sẽ không còn phù hợp; có thể bổ sung `term_id` hoặc thay đổi mô hình. Đây là ví dụ rõ ràng về việc **quy tắc nghiệp vụ quyết định database constraint**, còn annotation chỉ thể hiện quyết định đó.

## 10. Quan hệ tự tham chiếu: Cấp quản lý của nhân viên

Trong sơ đồ tổ chức:

- Một nhân viên có thể có một quản lý hoặc không.
- Một quản lý có thể có nhiều nhân viên dưới quyền.

Một entity tham chiếu chính nó:

~~~java
@Entity
@Table(name = "employee")
public class Employee {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "manager_id")
    private Employee manager;

    @OneToMany(mappedBy = "manager")
    private List<Employee> directReports = new ArrayList<>();
}
~~~

SQL:

~~~sql
CREATE TABLE employee (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    manager_id BIGINT NULL,
    CONSTRAINT fk_employee_manager
        FOREIGN KEY (manager_id) REFERENCES employee(id)
);
~~~

`manager_id` nullable vì nhân viên cấp cao nhất có thể không có quản lý. Mapping không tự ngăn vòng lặp như A quản lý B, B lại quản lý A, hoặc một người là quản lý chính họ. Nếu hệ thống cấm vòng lặp, cần validation/logic nghiệp vụ và quy tắc xử lý concurrency tương ứng.

Không nên cấu hình cascade REMOVE trên `Employee.manager`: xóa một nhân viên không có nghĩa xóa toàn bộ quản lý cấp trên.

## 11. Optionality, uniqueness và các constraint vật lý

Quan hệ JPA mô tả cấu trúc object; SQL constraint kiểm soát tính toàn vẹn ngay cả khi có nhiều ứng dụng cùng ghi DB.

| Quy tắc nghiệp vụ | Mapping JPA thường dùng | Constraint DB tương ứng |
|---|---|---|
| Mỗi order bắt buộc có customer | `@ManyToOne(optional = false)` | `customer_id NOT NULL` và `FOREIGN KEY` |
| Mỗi profile thuộc một account | `@OneToOne(optional = false)` | FK `NOT NULL` |
| Mỗi account có tối đa một profile | `@OneToOne` + `unique = true` theo FK | `UNIQUE(account_id)` |
| Một order có thể chưa có line khi đang draft | `@OneToMany` collection có thể rỗng | Thường không có FK constraint nào tự bảo đảm min-count |
| Không ghi trùng một enrollment cho một kỳ | Entity trung gian + unique constraint | `UNIQUE(student_id, course_id, term_id)` nếu phù hợp |
| OrderLine.quantity phải lớn hơn 0 | Kiểm tra domain/Bean Validation | `CHECK(quantity > 0)` |
| Xóa customer phải có chính sách đối với orders | Cascade/restrict theo nghiệp vụ | FK `ON DELETE` theo schema, hoặc thao tác service rõ ràng |

`optional = false` và `nullable = false` giải quyết các tầng liên quan nhưng không thay thế hoàn toàn nhau. `optional` là metadata của liên kết JPA; `nullable` giúp mô tả cột. Ràng buộc DB phải được tạo và duy trì thực tế bằng migration/DDL.

Với quy tắc “mỗi đơn có ít nhất một dòng”, chỉ có FK từ OrderLine sang PurchaseOrder là chưa đủ. Đó là invariant liên quan **tập nhiều bản ghi** và thời điểm chuyển trạng thái, thường phải được thực thi ở logic nghiệp vụ trong transaction.

## 12. Cascade không phải là “liên kết”, và xóa liên kết không luôn là xóa entity

Khi một entity có tham chiếu đến entity khác, không mặc định mọi thao tác với entity thứ nhất phải lan sang entity thứ hai.

### 12.1. Các cascade JPA phổ biến

| CascadeType | Tác động khi gọi thao tác ở entity nguồn |
|---|---|
| `PERSIST` | Chuyển tiếp thao tác persist tới entity liên kết |
| `MERGE` | Chuyển tiếp thao tác merge |
| `REMOVE` | Chuyển tiếp thao tác remove |
| `REFRESH` | Chuyển tiếp refresh |
| `DETACH` | Chuyển tiếp detach |
| `ALL` | Kết hợp các loại trên |

**Cascade thể hiện quyền sở hữu vòng đời thao tác persistence, không phải cardinality.**

Ví dụ:

- `PurchaseOrder → OrderLine`: một dòng phụ thuộc hoàn toàn vào đơn, có thể dùng `cascade = ALL`.
- `OrderLine → Product`: sản phẩm là dữ liệu danh mục dùng chung, thường **không cascade REMOVE**.
- `PurchaseOrder → Customer`: khách hàng tồn tại độc lập, thường không cascade REMOVE.
- `Student ↔ Course`: hai phía độc lập, không cascade REMOVE chỉ vì họ có liên kết.

Nếu không có cascade PERSIST và tham chiếu tới entity target còn transient, provider có thể báo lỗi khi flush; cách xử lý là persist entity đích theo nghiệp vụ hoặc sử dụng target managed sẵn có, không tùy tiện bật cascade ALL.

### 12.2. `orphanRemoval = true` khác `CascadeType.REMOVE`

Giả sử `PurchaseOrder.lines` dùng:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines = new ArrayList<>();
~~~

- `CascadeType.REMOVE`: khi remove đơn hàng, thao tác remove có thể chuyển đến những dòng được liên kết.
- `orphanRemoval = true`: khi một dòng bị tách khỏi mối quan hệ bao chứa của đơn theo quy tắc JPA, dòng đó có thể được xóa ở thời điểm flush.

Trong mô hình độc lập như `Customer ↔ PurchaseOrder`, **không nên cấu hình orphanRemoval một cách máy móc** nếu chỉ muốn chuyển đơn hàng từ khách này sang khách khác hoặc giữ lịch sử đơn khi khách ngừng hoạt động.

### 12.3. Database `ON DELETE CASCADE` là cơ chế khác

`ON DELETE CASCADE` là hành vi của FK tại database; cascade JPA là hành vi do ORM điều phối. Hai cơ chế có thể cùng tồn tại nhưng không tương đương về callback entity, persistence context hoặc SQL mà provider phát ra.

Nếu có xóa dữ liệu bằng native SQL hoặc hệ thống khác, DB-level constraint mới trực tiếp áp dụng cho luồng đó. Khi thiết kế quan hệ, cần quyết định rõ cách xóa ở cả tầng domain, JPA và database.

## 13. Fetching: Có liên kết trong Java không nghĩa là lúc nào cũng tải tất cả

Mặc định JPA có chính sách fetching khác nhau:

| Annotation | Mặc định JPA | Lưu ý |
|---|---|---|
| `@ManyToOne` | `EAGER` | Thường nên cân nhắc `LAZY` và chọn truy vấn phù hợp |
| `@OneToOne` | `EAGER` | LAZY to-one có thể chịu hạn chế triển khai |
| `@OneToMany` | `LAZY` | Collection có thể được tải khi truy cập |
| `@ManyToMany` | `LAZY` | Duyệt collection có thể phát sinh SQL bổ sung |

`FetchType.LAZY` là yêu cầu/hint theo đặc tả đối với provider trong một số ngữ cảnh, còn `EAGER` thể hiện yêu cầu nạp trước theo hợp đồng. Cần quan sát SQL thực tế để biết provider xử lý fetching ra sao.

### 13.1. Vấn đề N+1 queries

Ví dụ lấy 100 đơn hàng rồi đọc tên khách:

~~~java
List<PurchaseOrder> orders = entityManager.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
).getResultList();

for (PurchaseOrder order : orders) {
    System.out.println(order.getCustomer().getId());
}
~~~

Nếu truy cập dữ liệu customer chưa được tải, ORM có thể phải thực hiện nhiều truy vấn phụ. Trong ví dụ trên chỉ đọc ID; provider có thể xử lý ID proxy mà không cần load đầy đủ, nên để minh họa N+1 rõ hơn, thao tác đọc thuộc tính khác như `getFullName()` mới là tình huống quan sát thích hợp.

Khi màn hình cần cả đơn và tên khách, có thể chủ động dùng fetch join:

~~~java
List<PurchaseOrder> orders = entityManager.createQuery(
    "SELECT o FROM PurchaseOrder o " +
    "JOIN FETCH o.customer",
    PurchaseOrder.class
).getResultList();
~~~

Hoặc sử dụng EntityGraph/projection để chọn dữ liệu cần cho use case. Không cấu hình mọi quan hệ thành EAGER chỉ để tránh một truy vấn N+1: việc tải quá nhiều đồ thị cũng có thể làm giảm hiệu năng.

### 13.2. Pagination và collection fetch

Fetch join một collection `@OneToMany` trong truy vấn phân trang có thể nhân bản dòng SQL, khiến kết quả trang khó dự đoán và tùy provider có thể phải phân trang trong bộ nhớ.

Các cách tiếp cận thường dùng là:

1. Phân trang danh sách entity gốc bằng truy vấn chỉ lấy ID hoặc dữ liệu tóm tắt.
2. Tải chi tiết/collection cho tập ID của trang hiện tại bằng truy vấn bổ sung thích hợp.
3. Dùng DTO projection nếu giao diện chỉ cần các trường tổng hợp.
4. Kiểm tra SQL và hiệu năng theo dữ liệu thật.

**Quan hệ entity dùng để mô hình hóa domain; chiến lược load nên được thiết kế theo từng nhu cầu đọc.**

### 13.3. LazyInitializationException

Với Hibernate, truy cập collection LAZY ngoài persistence context/session còn hiệu lực có thể dẫn tới `LazyInitializationException`. Ví dụ trả thẳng entity qua REST controller sau khi transaction đã kết thúc rồi serializer cố đọc `order.lines`.

Giải pháp thường là chuẩn bị DTO trong service có transaction phù hợp hoặc tải trước những phần cần thiết; không nên trông đợi serializer tự truy cập mọi association mà không có kế hoạch.

## 14. Đặt liên kết trong domain nhưng không để entity vượt quá ranh giới hệ thống

Một quyết định quan trọng hơn annotation là **hai đối tượng có thuộc cùng một mô hình persistence hay không**.

Ví dụ:

- `PurchaseOrder` và `Customer` nằm trong cùng database và persistence unit, cần truy cập qua ORM → `@ManyToOne` có thể phù hợp.
- `PurchaseOrder` cần tham chiếu một khách hàng ở dịch vụ CRM độc lập, DB riêng → lưu `customerExternalId` hoặc một định danh tham chiếu, gọi API/qua sự kiện để lấy dữ liệu. Không cố tạo JPA `@ManyToOne` xuyên qua hai database/service như thể chúng cùng persistence context.
- Product thay đổi tên/giá theo thời gian → OrderLine có thể tham chiếu Product để biết sản phẩm hiện tại, **đồng thời lưu snapshot** giá/tên tại thời điểm đặt nếu nghiệp vụ yêu cầu lịch sử không đổi.
- Các domain aggregate khác nhau cần được cập nhật độc lập → có thể tham chiếu bằng ID thay vì giữ object association sâu nếu điều đó giúp rõ ranh giới và hạn chế tải dữ liệu.

JPA association mạnh ở những quan hệ được xử lý trong một mô hình ORM thống nhất, nhưng không thay thế quy tắc nhất quán của hệ thống phân tán hoặc lựa chọn aggregate của domain.

### 14.1. Tham chiếu bằng entity hay chỉ lưu foreign key?

Có hai cách biểu diễn cùng một FK:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id")
private Customer customer;
~~~

hoặc:

~~~java
@Column(name = "customer_id")
private Long customerId;
~~~

Cách thứ nhất cho khả năng điều hướng object và tận dụng mapping JPA. Cách thứ hai lưu trực tiếp giá trị ID, hữu ích khi không muốn phụ thuộc entity của domain khác hoặc chỉ cần một tham chiếu đơn giản.

Nếu dùng **cả hai field ánh xạ cùng một cột**, cần tránh hai mapping đều cùng ghi vào FK. Một lựa chọn là làm field ID chỉ đọc bằng `insertable = false, updatable = false`, nhưng phải hiểu việc đồng bộ trạng thái và lý do cần hai đại diện. Thường tốt hơn là chọn một nguồn sự thật rõ ràng theo use case.

## 15. Ví dụ transaction tạo đơn hàng đúng liên kết

Giả sử ứng dụng có:

- Customer và Product đã tồn tại.
- PurchaseOrder mới.
- OrderLine là thành phần phụ thuộc của PurchaseOrder.
- PurchaseOrder có `@OneToMany(mappedBy = "order", cascade = ALL, orphanRemoval = true)` như đã nêu.

Service Spring có thể thực hiện:

~~~java
import jakarta.persistence.EntityManager;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;

@Service
public class OrderService {

    private final EntityManager entityManager;

    public OrderService(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Transactional
    public Long createOrder(
        Long customerId,
        Long productId,
        int quantity
    ) {
        Customer customer =
            entityManager.find(Customer.class, customerId);

        Product product =
            entityManager.find(Product.class, productId);

        if (customer == null || product == null) {
            throw new IllegalArgumentException(
                "Customer or product does not exist"
            );
        }

        PurchaseOrder order = new PurchaseOrder(customer);

        // Ví dụ giá đã được xác định theo chính sách nghiệp vụ.
        BigDecimal unitPrice = new BigDecimal("125000.00");
        order.addLine(product, quantity, unitPrice);

        entityManager.persist(order);

        // Cascade PERSIST lưu OrderLine cùng unit of work.
        // Thao tác thật vẫn cần transaction commit thành công.
        return order.getId();
    }
}
~~~

Code mẫu minh họa liên kết, không phải quy trình tính giá hoàn chỉnh; ứng dụng thực phải xác nhận giá theo catalog/khuyến mại, tính thuế, tồn kho và bảo vệ cạnh tranh theo yêu cầu.

Nếu IDENTITY được dùng, thời điểm ID xuất hiện có thể gắn với việc provider thực thi INSERT; nếu dùng SEQUENCE/UUID, ID có thể có sớm hơn. `@Transactional` trong Spring điều phối commit ở ranh giới transaction phù hợp. Nếu method tham gia transaction đã có, caller của method con vẫn có thể nhận ID trước khi transaction ngoài cùng commit.

### 15.1. Vì sao không `persist(customer)` và `persist(product)` lại?

Customer và Product là các entity đã tồn tại. Chúng được `find` trong persistence context hiện tại và có identity do DB xác nhận. Cascade từ OrderLine sang Product không được bật, nên JPA chỉ lưu/order line mới và dùng FK trỏ tới Product.

Không tùy tiện tạo một `new Product()` rồi chỉ điền ID như thể đó là một entity managed hợp lệ. Nếu muốn tham chiếu entity đích đã tồn tại mà không cần tải toàn bộ thuộc tính, `EntityManager.getReference(Product.class, productId)` có thể được cân nhắc khi hợp đồng nghiệp vụ và việc kiểm tra tồn tại phù hợp; provider có thể trì hoãn truy cập DB nên lỗi không tồn tại có thể phát hiện muộn.

### 15.2. Nên kiểm tra ràng buộc ở đâu?

- **Trước khi persist:** kiểm tra input và quy tắc domain (quantity > 0, đơn có dòng, giá hợp lệ).
- **Trong transaction:** lấy entity cần liên kết, kiểm tra trạng thái và áp dụng thay đổi nhất quán.
- **Ở database:** FK, NOT NULL, UNIQUE, CHECK bảo vệ tính toàn vẹn khi có truy cập đồng thời.
- **Khi commit:** xử lý exception và rollback; không coi ID đã cấp là bằng chứng lưu thành công.

Quan hệ đúng về cú pháp nhưng cập nhật ngoài transaction hoặc bỏ qua constraint vẫn có thể tạo ra lỗi dữ liệu nghiệp vụ.

## 16. Vấn đề equality, collection và vòng lặp serialization

### 16.1. `equals()`/`hashCode()` trên entity

JPA entity có identity gắn với khóa chính, nhưng khóa sinh tự động có thể chưa có trước persist. Nếu đưa entity mới vào `HashSet` rồi `hashCode()` thay đổi khi ID được cấp, collection có thể hoạt động bất ngờ.

Không mặc định sinh `equals()`/`hashCode()` dựa trên **toàn bộ trường và toàn bộ quan hệ**, đặc biệt với association hai chiều. Điều đó có thể gây vòng lặp vô hạn hoặc tải LAZY không chủ ý. Hãy chọn chính sách equality theo domain và vòng đời ID; với các ví dụ tập `Set`, cần xét chính sách đó trước khi dùng thật.

### 16.2. JSON có thể tuần hoàn

Một đồ thị hai chiều:

~~~text
Customer.orders -> PurchaseOrder.customer -> Customer.orders -> ...
~~~

Nếu trả trực tiếp entity từ REST API, serializer có thể đi theo vòng lặp hoặc kích hoạt nhiều lazy loads. Thay vì lạm dụng annotation để che tất cả liên kết, thường nên dùng DTO xác định dữ liệu API cần trả:

~~~java
public record OrderSummaryDto(
    Long orderId,
    Long customerId,
    int lineCount
) {}
~~~

Service có thể truy vấn/projection và tạo DTO trong ranh giới transaction phù hợp. Dữ liệu gửi cho client không cần phản ánh toàn bộ đồ thị object trong persistence context.

### 16.3. `toString()` và logging

Không đưa collection quan hệ hoặc giá trị nhạy cảm vào `toString()` một cách tự động. Việc log entity có thể kích hoạt lazy loading, xuất lộ dữ liệu không cần thiết hoặc đệ quy vô hạn.

## 17. Lỗi thường gặp khi chuyển quan hệ nghiệp vụ thành JPA

| Triệu chứng | Nguyên nhân thường gặp | Hướng xác định |
|---|---|---|
| Thêm vào `customer.orders` nhưng FK không đổi | Chỉ sửa inverse side, chưa sửa `order.customer` | Cập nhật owning side và đồng bộ helper |
| `mappedBy` không hợp lệ | Dùng tên cột SQL thay vì field Java | `mappedBy = "customer"` nếu field là `customer` |
| Quan hệ 1-1 có nhiều profile cho cùng account | Thiếu UNIQUE constraint trên FK | Thiết kế FK UNIQUE ở DB |
| Xóa OrderLine nhưng vẫn còn trong DB | Chỉ xóa phần tử ở inverse collection, hoặc chưa có `orphanRemoval`/thao tác xóa phù hợp | Kiểm tra lifecycle, owning side và transaction |
| Xóa đơn kéo theo xóa Product | Cascade REMOVE đặt trên quan hệ dùng chung | Chỉ cascade theo quyền sở hữu vòng đời |
| JPA cố tạo bảng nối không mong muốn | Cấu hình One-to-Many một chiều không chỉ rõ mapping kỳ vọng | Xem `mappedBy`/`@JoinColumn`/`@JoinTable` và DDL |
| Đơn có hai dòng cùng Product nhưng mapping không phù hợp | Dùng Many-to-Many trần và mất metadata của từng dòng | Tạo OrderLine là entity liên kết |
| N+1 queries khi duyệt dữ liệu | Đường truy cập LAZY/EAGER không được thiết kế theo use case | Dùng fetch join, EntityGraph hoặc projection phù hợp |
| LazyInitializationException trong REST | Serializer truy cập association sau khi context đóng | Tạo DTO và tải dữ liệu trong transaction phù hợp |
| SQL báo FK violation | Entity tham chiếu không tồn tại, hoặc chưa persist theo đúng thứ tự/cascade | Xác nhận target managed/tồn tại và transaction |
| Trùng enrollment cho cùng kỳ | Không có ràng buộc UNIQUE đúng với nghiệp vụ | Thiết kế unique key theo kỳ học |
| Hai chiều tham chiếu tạo recursion | Serializer/equality/toString đi qua cả hai phía | DTO và chính sách equality/logging rõ ràng |
| Xóa khách hàng làm mất đơn hàng lịch sử | Cascade/DB deletion policy không phù hợp | Quy định giữ lịch sử, soft delete hoặc hạn chế xóa |
| Collection “ít nhất 1 dòng” vẫn rỗng | ORM cardinality không tự diễn tả min-count | Kiểm tra invariant khi xác nhận trong transaction |

Khi có lỗi, nên tìm ngược từ yêu cầu nghiệp vụ: **quan hệ có được hiểu đúng không, khóa ngoại đúng phía không, và thao tác nào phải thay đổi dữ liệu thật?** Sau đó mới xem SQL provider phát ra.

## 18. Quy trình quyết định ánh xạ cho một quan hệ mới

Có thể dùng quy trình sau khi nhận một user story mới.

### Bước 1: Viết rõ câu nghiệp vụ theo hai chiều

Ví dụ:

> “Một đơn hàng có nhiều dòng; mỗi dòng phải thuộc đúng một đơn hàng.”

Ghi nhận riêng:

- Từ đơn sang dòng: 0..n trong giai đoạn tạo.
- Từ dòng sang đơn: đúng 1.
- Khi xác nhận đơn: số dòng phải ít nhất 1.
- Dòng không có ý nghĩa tồn tại ngoài đơn.

### Bước 2: Chọn entity hay value object

Nếu đối tượng có identity và được cập nhật/xóa độc lập hoặc được tham chiếu bởi nhiều nơi, cân nhắc entity. Nếu chỉ là một tập thuộc tính của entity khác và không cần identity độc lập, cân nhắc embeddable.

### Bước 3: Chọn cấu trúc quan hệ vật lý

Đặt FK trên bảng con ở quan hệ nhiều-một; đặt UNIQUE nếu là một-một; dùng join table cho nhiều-nhiều thuần; tạo entity trung gian khi liên kết có thuộc tính hoặc vòng đời riêng.

### Bước 4: Chọn hướng điều hướng cần thiết

Bắt đầu với chiều đủ đáp ứng use case. Chỉ bổ sung chiều ngược nếu có lợi cho logic domain hoặc cách truy vấn. Việc điều hướng dữ liệu có thể được thực hiện bằng repository query mà không nhất thiết giữ collection trong entity.

### Bước 5: Chọn owning side và chỉ định mapping

Dùng `@JoinColumn`/`@JoinTable` để thể hiện nơi lưu quan hệ, và `mappedBy` cho phía inverse nếu có ánh xạ hai chiều. Xác minh tên cột, tên bảng và tên field Java không bị nhầm lẫn.

### Bước 6: Quyết định lifecycle

Liên kết có nghĩa là cùng tồn tại hay chỉ tham chiếu? Chỉ bật cascade PERSIST/REMOVE hoặc orphanRemoval khi quan hệ nghiệp vụ thực sự cần lan truyền thao tác. Entity dùng chung thường không nên bị xóa theo entity tham chiếu.

### Bước 7: Thiết kế fetching cho use case

Chọn LAZY khi phù hợp và chủ động fetch dữ liệu cần cho trang/list/report. Kiểm tra query plan với nhiều bản ghi; tránh N+1 và tránh fetch collection bừa bãi khi phân trang.

### Bước 8: Bảo vệ invariant và transaction

Kiểm tra số lượng, điều kiện trạng thái, quyền sửa và tính toàn vẹn trong service/domain. Đặt constraint DB tương ứng. Không trả tín hiệu nghiệp vụ thành công trước khi transaction thực sự được xác nhận.

## 19. Bài tập áp dụng

### Bài 1: Khách hàng và đơn hàng

Yêu cầu: một khách có thể có nhiều đơn, mỗi đơn bắt buộc có khách. Màn hình chính chỉ mở từ đơn hàng tới khách; không cần duyệt `customer.orders`.

**Câu hỏi:** Có bắt buộc tạo `@OneToMany` trên Customer không?

**Đáp án:** Không. Có thể chỉ dùng `@ManyToOne(optional = false)` trên `PurchaseOrder.customer`, kèm FK `customer_id NOT NULL`. Nếu cần danh sách đơn, repository query theo customer ID là đủ.

### Bài 2: Enrollment có thêm điểm số

Yêu cầu: học viên học nhiều khóa; một khóa có nhiều học viên; mỗi lần ghi danh có ngày đăng ký và điểm.

**Câu hỏi:** Nên dùng `@ManyToMany` thuần hay entity `Enrollment`?

**Đáp án:** `Enrollment` là entity liên kết phù hợp hơn vì ngày đăng ký và điểm thuộc về lần ghi danh, không phải riêng Student hoặc Course. Entity đó có hai `@ManyToOne`. UNIQUE constraint cần được thiết kế theo quy tắc một lần/mỗi kỳ.

### Bài 3: Thêm vào inverse collection

~~~java
customer.getOrders().add(order);
entityManager.flush();
~~~

Đã khai báo `Customer.orders` bằng `@OneToMany(mappedBy = "customer")`, nhưng `order.customer` vẫn `null`.

**Câu hỏi:** Vì sao FK có thể không được ghi đúng?

**Đáp án:** `PurchaseOrder.customer` là owning side. Chỉ sửa collection inverse không đồng bộ liên kết. Cần gán owning side và giữ hai phía nhất quán bằng helper.

### Bài 4: Cascade REMOVE trên quan hệ Product

~~~java
@ManyToOne(cascade = CascadeType.REMOVE)
private Product product;
~~~

Một OrderLine bị xóa, trong khi Product đang được các đơn hàng khác tham chiếu.

**Câu hỏi:** Rủi ro là gì?

**Đáp án:** Cascade REMOVE có thể yêu cầu xóa Product được dùng chung, dẫn đến FK violation hoặc mất danh mục. Không cascade xóa đối tượng độc lập chỉ vì association được khai báo.

### Bài 5: Một tài khoản có tối đa một hồ sơ

Cơ sở dữ liệu có bảng `account_profile(account_id, bio)` và `account_id` là FK nhưng không UNIQUE.

**Câu hỏi:** Chỉ thêm `@OneToOne` đã đủ bảo vệ quy tắc chưa?

**Đáp án:** Chưa. Cần thiết lập uniqueness thực tế tại database (chẳng hạn UNIQUE hoặc dùng shared primary key) và đồng bộ mapping/schema.

### Bài 6: Lịch sử giá sản phẩm

Product hiện tại có giá 150.000 đồng, nhưng người dùng đã đặt hàng khi giá là 120.000 đồng.

**Câu hỏi:** OrderLine chỉ chứa `@ManyToOne Product` rồi đọc `product.currentPrice` có đúng yêu cầu lịch sử không?

**Đáp án:** Không nếu hóa đơn cần giữ giá lúc đặt. OrderLine phải lưu snapshot đơn giá tại thời điểm tạo dòng. Quan hệ Product giúp tham chiếu danh mục hiện tại, không thay thế dữ liệu lịch sử.

## 20. Ghi nhớ cốt lõi

~~~text
Câu nghiệp vụ
    |
    v
Xác định entity và value object
    |
    v
Xác định cardinality + optionality
    |
    v
Chọn FK / UNIQUE / join table / entity trung gian
    |
    v
Chọn chiều điều hướng và owning side
    |
    v
Cấu hình @ManyToOne / @OneToMany / @OneToOne / @ManyToMany
    |
    v
Định nghĩa cascade, orphanRemoval, fetch
    |
    v
Đặt constraint DB + quy tắc domain + transaction
~~~

Những nguyên tắc cần nhớ:

1. **Chuyển câu nghiệp vụ thành mô hình dữ liệu trước khi chọn annotation.**
2. **Cardinality, optionality và vòng đời** là ba quyết định riêng; một quan hệ nhiều-một không tự cho biết có được xóa liên đới hay không.
3. **`@ManyToOne` thường nằm tại entity chứa FK**; `mappedBy` đặt ở phía inverse và trỏ tới **tên field Java** của owning side.
4. **Quan hệ hai chiều phải đồng bộ trong bộ nhớ ở cả hai phía**; chỉ sửa collection inverse có thể không làm thay đổi khóa ngoại.
5. **Many-to-Many có dữ liệu riêng thường nên được mô hình hóa bằng entity trung gian**, ví dụ `OrderLine` hoặc `Enrollment`.
6. **Cascade và orphanRemoval phải phản ánh quyền sở hữu vòng đời**, tránh xóa entity dùng chung như Customer, Product, Course.
7. **JPA metadata không thay thế constraint DB** và không tự thực thi các quy tắc như “ít nhất một dòng”.
8. **Loading và transaction là quyết định riêng:** thiết kế fetch theo use case, tránh N+1, và giữ tính nhất quán khi cập nhật nhiều entity.
9. **Không phải mọi mối liên hệ giữa hai khái niệm đều cần association JPA**; có trường hợp dùng embeddable, khóa ID hoặc tham chiếu dịch vụ bên ngoài hợp lý hơn.

Khi mô hình hóa theo hướng này, các liên kết entity trở thành biểu hiện chính xác của quy tắc nghiệp vụ và cấu trúc dữ liệu, thay vì chỉ là một tập annotation được thêm vào cho đủ quan hệ.

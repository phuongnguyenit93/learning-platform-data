# Áp dụng `CascadeType.PERSIST` cho đồ thị có entity mới

## 1. Bài toán: lưu cả một đồ thị object bằng một thao tác

Trong Jakarta Persistence (JPA), dữ liệu nghiệp vụ thường không được tạo thành từng object độc lập. Khi tiếp nhận một đơn hàng, ứng dụng có thể đồng thời tạo **đơn hàng**, **các dòng hàng** và **các ghi chú của dòng hàng**, rồi liên kết chúng với **khách hàng** và **sản phẩm** đã có trong cơ sở dữ liệu.

Ví dụ:

```text
                         PurchaseOrder mới
                               |
                   +-----------+-----------+
                   |                       |
                   v                       v
              OrderLine mới            OrderLine mới
                   |                       |
                   v                       v
              Product #7                Product #9
              (đã có)                  (đã có)

PurchaseOrder ---------> Customer #12 (đã có)
```

Ta muốn chỉ cần:

```java
em.persist(order);
```

để **Order và các OrderLine mới được lưu**, trong khi **Customer và Product hiện có được tham chiếu chứ không bị tạo trùng**.

Đó là một tình huống điển hình để áp dụng **`CascadeType.PERSIST`**: khi thực hiện `persist` trên một entity, JPA có thể **lan truyền thao tác persist theo những association có khai báo cascade PERSIST**, qua các tầng của object graph.

Tuy nhiên, cascade **không tự động áp dụng cho mọi object được tham chiếu**. Nó còn khác với việc thiết lập foreign key, khác `orphanRemoval`, và không nên dùng bừa bãi trên entity có vòng đời độc lập. Bài học này giải thích cách thiết kế graph, chọn đúng hướng cascade, tạo dữ liệu mới và kiểm soát kết quả trong database.

## 2. Những khái niệm cần phân biệt

### 2.1. Entity mới, managed và detached

Một object có annotation `@Entity` chưa chắc đã được lưu:

```java
OrderLine line = new OrderLine("KEYBOARD", 2);

System.out.println(em.contains(line)); // false: new/transient.
```

Sau khi gọi `persist` trên entity mới hợp lệ:

```java
em.persist(line);
System.out.println(em.contains(line)); // true: managed.
```

Các trạng thái chính:

| Trạng thái | Ý nghĩa | Tình huống |
|---|---|---|
| **New/transient** | Object Java chưa được persistence context quản lý; chưa được JPA đưa vào quy trình persist | `new OrderLine(...)` |
| **Managed** | Instance đang được một persistence context theo dõi | `em.persist(newLine)` hoặc `em.find(...)` |
| **Detached** | Instance từng managed nhưng không còn thuộc context hiện tại | Object từ request/context cũ, sau `detach`, `clear` hoặc `close` |
| **Removed** | Entity được đánh dấu xóa trong context | `em.remove(managedLine)` |

`CascadeType.PERSIST` nhằm **lan truyền thao tác đưa entity mới vào quản lý**. Nó không phải cơ chế để đồng bộ tùy ý một entity detached, cũng không phải phép kiểm tra object đã tồn tại trong database hay chưa.

### 2.2. Object graph là gì?

*Đồ thị object* gồm các entity như nút và các reference/collection như cạnh:

```text
Order
  |
  +---- customer ------> Customer
  |
  +---- lines ---------> Line A
  |                       |
  |                       +---- product ---> Product
  |
  +---- lines ---------> Line B
                          |
                          +---- product ---> Product
```

Cạnh có thể được ánh xạ bằng `@OneToOne`, `@OneToMany`, `@ManyToOne` hoặc `@ManyToMany`.

JPA **không đơn giản đi theo mọi cạnh của Java graph để tự INSERT tất cả nút**. Việc lan truyền phụ thuộc cấu hình cascade **trên chính association và thao tác đang thực hiện**.

### 2.3. Cascade PERSIST là gì?

Ví dụ:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.PERSIST
)
private List<OrderLine> lines = new ArrayList<>();
```

Khi `em.persist(order)` được gọi, thao tác `PERSIST` có thể lan truyền đến từng `OrderLine` trong `order.lines`. Nếu các dòng hàng là **new**, chúng được đưa vào quy trình persistence cùng Order.

Nếu cần dùng nhiều loại cascade:

```java
@OneToMany(
    mappedBy = "order",
    cascade = {
        CascadeType.PERSIST,
        CascadeType.MERGE
    }
)
private List<OrderLine> lines = new ArrayList<>();
```

`CascadeType.ALL` bao gồm cả `REMOVE`, `REFRESH`, `DETACH` và `MERGE`, không chỉ `PERSIST`. Vì vậy **không cần thêm `ALL` chỉ để lưu con mới**.

## 3. Hai trách nhiệm độc lập: lưu entity và ghi liên kết

Một lỗi phổ biến là tưởng rằng “có cascade là foreign key tự đúng”. Thực tế phải giải quyết **hai vấn đề riêng**:

1. **Vòng đời:** entity con mới có được persist hay không?
2. **Quan hệ:** phía sở hữu association có được gán đúng để JPA ghi khóa ngoại/bảng nối hay không?

Với quan hệ Order–OrderLine hai chiều:

```java
@OneToMany(mappedBy = "order", cascade = CascadeType.PERSIST)
private List<OrderLine> lines = new ArrayList<>();
```

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "order_id", nullable = false)
private PurchaseOrder order;
```

`OrderLine.order` là **owning side** vì chứa `@JoinColumn` chỉ tới `order_lines.order_id`. `PurchaseOrder.lines` là inverse side vì có `mappedBy = "order"`.

Nếu chỉ gọi:

```java
order.getLines().add(line);
```

thì OrderLine có thể được persist nhờ cascade, **nhưng field `line.order` có thể vẫn null**. Khi flush, cột `order_id NOT NULL` có thể vi phạm constraint.

Cách đúng là dùng helper để đồng bộ cả hai phía:

```java
public void addLine(OrderLine line) {
    if (line == null) {
        throw new IllegalArgumentException("Line không được null");
    }

    lines.add(line);
    line.setOrder(this); // Owning side được thiết lập.
}
```

**Cascade điều khiển thao tác persist lan truyền; owning side điều khiển association được ghi vào database.** Cần cả hai nếu muốn persist graph nhiều entity với foreign key đúng.

## 4. Ví dụ hoàn chỉnh: Order mới, Line mới, Customer và Product đã có

Để nhìn rõ ranh giới cascade, ta xây dựng các entity:

- `Customer`: đã tồn tại, được nhiều Order tham chiếu.
- `Product`: đã tồn tại, được nhiều OrderLine tham chiếu.
- `PurchaseOrder`: entity nguồn vừa tạo.
- `OrderLine`: các entity mới phụ thuộc về vòng đời vào PurchaseOrder.

Mỗi OrderLine giữ số lượng và đơn giá đã chốt; giá trị này **không đặt trên Product** vì cùng Product có thể xuất hiện với số lượng/giá khác nhau ở nhiều đơn.

### 4.1. Schema minh họa

Ví dụ PostgreSQL:

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    display_name VARCHAR(120) NOT NULL
);

CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE,
    name VARCHAR(160) NOT NULL
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    order_code VARCHAR(40) NOT NULL UNIQUE,
    CONSTRAINT fk_purchase_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(14, 2) NOT NULL
        CHECK (unit_price >= 0),
    CONSTRAINT fk_lines_order
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id),
    CONSTRAINT fk_lines_product
        FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE INDEX ix_lines_order_id ON order_lines(order_id);
CREATE INDEX ix_lines_product_id ON order_lines(product_id);
```

Một Order có nhiều Line; một Product có thể được nhiều Line tham chiếu. Database đảm bảo các khóa ngoại trỏ tới bản ghi hợp lệ.

### 4.2. Customer và Product là entity dùng chung

**`Customer.java`**

```java
package com.example.shop.domain;

import jakarta.persistence.*;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "display_name", nullable = false, length = 120)
    private String displayName;

    protected Customer() {
    }

    public Customer(String displayName) {
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }
}
```

**`Product.java`**

```java
package com.example.shop.domain;

import jakarta.persistence.*;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", nullable = false, unique = true, length = 80)
    private String sku;

    @Column(name = "name", nullable = false, length = 160)
    private String name;

    protected Product() {
    }

    public Product(String sku, String name) {
        this.sku = sku;
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }
}
```

Trong use case tạo Order, **không có lý do tự persist lại những Customer/Product đã tồn tại**. Service sẽ tải các entity đó từ `EntityManager` hiện tại hoặc dùng managed reference theo chính sách kiểm tra tồn tại thích hợp.

### 4.3. PurchaseOrder sở hữu vòng đời của các OrderLine

**`PurchaseOrder.java`**

```java
package com.example.shop.domain;

import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_code", nullable = false,
            unique = true, length = 40)
    private String orderCode;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.PERSIST
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String orderCode, Customer customer) {
        if (orderCode == null || orderCode.isBlank()) {
            throw new IllegalArgumentException("Mã đơn không hợp lệ");
        }
        this.orderCode = orderCode;
        this.customer = Objects.requireNonNull(customer);
    }

    public void addLine(OrderLine line) {
        Objects.requireNonNull(line, "line");
        lines.add(line);
        line.setOrder(this);
    }

    public Long getId() {
        return id;
    }

    public Customer getCustomer() {
        return customer;
    }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }
}
```

Những quyết định quan trọng:

- `PurchaseOrder.lines` có **`cascade=PERSIST`** vì các dòng được tạo cùng đơn.
- `PurchaseOrder.customer` **không có cascade PERSIST** vì Customer có vòng đời độc lập.
- `mappedBy="order"` trỏ tới thuộc tính Java trong `OrderLine`.
- Helper `addLine` bắt buộc thiết lập owning side `OrderLine.order`.

Ta cố ý **chưa thêm `orphanRemoval`** để tập trung vào cách tạo graph. Khi thiết kế thao tác xóa line về sau, cần quyết định riêng line có bị xóa khi rời khỏi Order hay không.

### 4.4. OrderLine chứa hai quan hệ ManyToOne

**`OrderLine.java`**

```java
package com.example.shop.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(name = "order_lines")
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

    @Column(name = "unit_price", nullable = false,
            precision = 14, scale = 2)
    private BigDecimal unitPrice;

    protected OrderLine() {
    }

    public OrderLine(
            Product product, int quantity, BigDecimal unitPrice) {
        this.product = Objects.requireNonNull(product);

        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity phải dương");
        }
        if (unitPrice == null || unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Price không được âm");
        }

        this.quantity = quantity;
        this.unitPrice = unitPrice;
    }

    void setOrder(PurchaseOrder order) {
        this.order = order;
    }

    public Long getId() {
        return id;
    }

    public Product getProduct() {
        return product;
    }

    public PurchaseOrder getOrder() {
        return order;
    }
}
```

Ở `OrderLine`:

- `order` là foreign key tới Order mới, sẽ trở thành managed trong cùng graph.
- `product` là foreign key tới Product đã tồn tại, **không cascade persist sang Product**.
- `quantity` và `unitPrice` là thuộc tính của chính dòng hàng.
- `setOrder` có phạm vi package để helper của Order thiết lập quan hệ; production có thể áp dụng cách đóng gói khác.

### 4.5. Tạo graph rồi persist Order một lần

Giả sử Customer #12 cùng Product #7 và #9 đã có trong database:

```java
EntityTransaction tx = em.getTransaction();
tx.begin();

try {
    Customer customer = em.find(Customer.class, 12L);
    Product keyboard = em.find(Product.class, 7L);
    Product mouse = em.find(Product.class, 9L);

    if (customer == null || keyboard == null || mouse == null) {
        throw new IllegalArgumentException(
            "Customer hoặc Product không tồn tại");
    }

    PurchaseOrder order =
        new PurchaseOrder("PO-2026-001", customer);

    OrderLine first = new OrderLine(
        keyboard, 2, new BigDecimal("890000.00"));

    OrderLine second = new OrderLine(
        mouse, 1, new BigDecimal("240000.00"));

    order.addLine(first);
    order.addLine(second);

    // Chỉ persist root mới; PERSIST cascade tới lines.
    em.persist(order);

    em.flush(); // Không bắt buộc cho mọi use case,
                // nhưng giúp phát hiện lỗi DB trước commit.

    System.out.println(em.contains(order));  // true.
    System.out.println(em.contains(first));  // true.
    System.out.println(em.contains(second)); // true.

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
```

Đoạn mã dùng `jakarta.persistence.EntityTransaction`, `java.math.BigDecimal` và một `EntityManager em` đã mở. Với Spring/Jakarta EE, transaction thường do framework/container quản lý.

**Kết quả mong muốn:**

1. Một hàng mới trong `purchase_orders` có `customer_id = 12`.
2. Hai hàng mới trong `order_lines` có `order_id` là ID của Order vừa tạo.
3. Hai hàng đó lần lượt có `product_id = 7` và `product_id = 9`.
4. Không có Customer hay Product bị tạo trùng.

Về mặt logic, SQL tương đương:

```sql
INSERT INTO purchase_orders (order_code, customer_id)
VALUES ('PO-2026-001', 12);

-- Giả sử ID Order mới là 100.
INSERT INTO order_lines
    (order_id, product_id, quantity, unit_price)
VALUES
    (100, 7, 2, 890000.00),
    (100, 9, 1, 240000.00);
```

SQL thực tế có thể gồm từng lệnh INSERT riêng, câu lấy generated ID, statement batching hoặc thứ tự khác tùy provider, dialect và chiến lược sinh khóa. **Không dựa vào chuỗi SQL minh họa như một bảo đảm về tối ưu hay ordering**.

### 4.6. Không cần gọi `persist` từng Line khi cascade đã đúng

Với graph và mapping trên:

```java
em.persist(order);
```

đã thể hiện ý định persist root và lan truyền PERSIST tới children. Việc viết thêm:

```java
em.persist(first);
em.persist(second);
```

không cần thiết để đạt mục tiêu; dù `persist` trên managed entity thường không yêu cầu thêm INSERT, thêm các lời gọi dư thừa sẽ khiến ranh giới ownership khó đọc. Nếu chọn convention **persist từng child tường minh**, có thể bỏ cascade và thiết kế service phù hợp; nên nhất quán.

## 5. Dòng thời gian: lúc nào entity mới được persist?

Giả sử ta đã tạo graph:

```java
PurchaseOrder order = new PurchaseOrder("PO-1", managedCustomer);
OrderLine line = new OrderLine(managedProduct, 2, price);
order.addLine(line);
```

Trước persist:

```java
em.contains(order); // false.
em.contains(line);  // false.
```

Sau:

```java
em.persist(order);
```

JPA đưa Order và các child trong quan hệ có PERSIST cascade vào quá trình persistence. Sau khi cascade đã được thực hiện, chúng là managed:

```java
em.contains(order); // true.
em.contains(line);  // true.
```

Nhưng **managed không đồng nghĩa INSERT đã commit**. Với `GenerationType.IDENTITY`, provider có thể cần gửi INSERT sớm để lấy ID; với `SEQUENCE`, provider có thể cấp ID trước khi ghi hàng. Các câu SQL pending khác có thể chờ đến `flush`.

Mô hình quan sát:

```text
Java new Order + new Lines
               |
               | em.persist(Order)
               v
PERSIST cascade tới các Lines
               |
               v
Order / Lines đang managed trong context
               |
               | em.flush()
               v
ORM gửi INSERT và kiểm tra ràng buộc DB
               |
               | commit
               v
Giao dịch thành công: thay đổi được xác nhận
```

Không dùng `id != null` hoặc `em.contains(entity) == true` làm bằng chứng duy nhất rằng transaction đã commit.

## 6. Cascade qua nhiều tầng của đồ thị

Một graph có thể gồm nhiều cấp:

```text
PurchaseOrder (new)
   |
   | cascade PERSIST
   v
OrderLine (new)
   |
   | cascade PERSIST
   v
LineAdjustment (new)
```

`OrderLine` có thể sở hữu các `LineAdjustment` như khoản chiết khấu hoặc điều chỉnh riêng của dòng hàng:

```java
@Entity
@Table(name = "line_adjustments")
public class LineAdjustment {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "line_id", nullable = false)
    private OrderLine line;

    @Column(name = "amount", nullable = false,
            precision = 14, scale = 2)
    private BigDecimal amount;

    protected LineAdjustment() {
    }

    public LineAdjustment(BigDecimal amount) {
        this.amount = Objects.requireNonNull(amount);
    }

    void setLine(OrderLine line) {
        this.line = line;
    }
}
```

Thêm vào `OrderLine`:

```java
@OneToMany(
    mappedBy = "line",
    cascade = CascadeType.PERSIST
)
private List<LineAdjustment> adjustments = new ArrayList<>();

public void addAdjustment(LineAdjustment adjustment) {
    Objects.requireNonNull(adjustment);
    adjustments.add(adjustment);
    adjustment.setLine(this);
}
```

Trong ví dụ này, `OrderLine` cần thêm import `java.util.ArrayList`, `List`; `LineAdjustment` cần import JPA, `BigDecimal` và `Objects`.

Khi tạo:

```java
OrderLine line = new OrderLine(product, 2, price);
line.addAdjustment(new LineAdjustment(
    new BigDecimal("-10000.00")));

order.addLine(line);
em.persist(order);
```

JPA có thể cascade qua chuỗi:

```text
persist(Order)
    |
    +--> persist(Line)
               |
               +--> persist(LineAdjustment)
```

Điều kiện quan trọng: **mỗi cạnh cần lan truyền PERSIST phải được khai báo cascade phù hợp**. Nếu Order → Line có cascade nhưng Line → Adjustment không có, JPA không tự suy ra cần persist Adjustment chỉ vì object nằm trong graph Java.

Ngoài ra, mỗi tầng vẫn phải thiết lập **owning side** của các association để foreign key đúng. Khi metadata hoặc vòng đời ở một tầng không hợp lệ, flush/commit có thể thất bại, và cả transaction cần rollback.

## 7. Thêm entity mới vào parent đã managed

Không phải mọi graph đều được tạo cùng lúc. Một Order đã lưu có thể được tải lên rồi bổ sung Line mới:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
Product product = em.find(Product.class, productId);

OrderLine line = new OrderLine(
    product, 1, new BigDecimal("120000.00"));

order.addLine(line);
```

Ở thời điểm vừa gọi `addLine`:

- Order đang managed nếu `find` thành công.
- Line vừa tạo vẫn là object new ban đầu.
- Thao tác thêm collection **không phải một lệnh `EntityManager.persist(line)` ngay tại dòng đó**.

Với quan hệ có `cascade=PERSIST`, JPA áp dụng quy tắc lan truyền PERSIST từ managed parent khi thao tác phù hợp diễn ra (trong đó có xử lý cascade tại flush theo semantics JPA). Vì vậy **không giả định** `em.contains(line)` đã là true ngay sau `order.addLine(line)`.

Nếu yêu cầu service muốn rõ thời điểm đưa child vào quản lý, có thể dùng:

```java
order.addLine(line);
em.persist(line); // Rõ ràng khi thêm con vào parent đã managed.
```

Cách khác là duy trì convention cascade từ aggregate root và để provider xử lý theo metadata khi flush:

```java
order.addLine(line);
em.flush(); // Cascade PERSIST qua managed parent theo semantics JPA.
```

Trong cả hai phương án, `line.order` phải được thiết lập qua helper. Khi cần kiểm soát chính xác trạng thái child ở một thời điểm, **persist tường minh** thường dễ lập luận hơn. Không nên dùng `contains` ngay sau `List.add` để kết luận cascade không hoạt động.

## 8. Các loại quan hệ và chiến lược cascade PERSIST

### 8.1. `@OneToMany`: cha tạo các con

Đây là tình huống tự nhiên nhất:

```java
@OneToMany(
    mappedBy = "invoice",
    cascade = CascadeType.PERSIST
)
private List<InvoiceLine> lines = new ArrayList<>();
```

Một Invoice mới được tạo với nhiều InvoiceLine mới; line thuộc vòng đời của invoice. Cần lưu Invoice và các line trong cùng transaction. Khi mapping hai chiều, phải thiết lập `InvoiceLine.invoice` là owning side.

### 8.2. `@OneToOne`: profile mới phụ thuộc account

Ví dụ một UserAccount mới có Profile mới, và Profile chỉ tồn tại cùng Account:

```java
@Entity
public class UserAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToOne(
        cascade = CascadeType.PERSIST,
        optional = false
    )
    @JoinColumn(name = "profile_id", unique = true, nullable = false)
    private UserProfile profile;

    protected UserAccount() {}

    public UserAccount(UserProfile profile) {
        this.profile = Objects.requireNonNull(profile);
    }
}
```

```java
@Entity
public class UserProfile {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String displayName;

    protected UserProfile() {}

    public UserProfile(String displayName) {
        this.displayName = displayName;
    }
}
```

Ví dụ sử dụng import JPA và `java.util.Objects` tương ứng.

```java
UserProfile profile = new UserProfile("An");
UserAccount account = new UserAccount(profile);

em.persist(account); // Có thể cascade PERSIST tới profile.
```

Do Account chứa FK tới Profile, ORM phải tạo một thứ tự ghi cho phép `profile_id` hợp lệ. Với identity generation và ràng buộc not-null, phải quan sát SQL thực tế khi sử dụng provider cụ thể; đây là thiết kế hợp lệ về mặt mục đích cascade nhưng schema và DDL cần tương thích.

### 8.3. `@ManyToOne`: target dùng chung thường không nên cascade

```java
@Entity
public class Booking {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "venue_id", nullable = false)
    private Venue venue;
}
```

Venue có thể được nhiều Booking sử dụng. Khi tạo Booking mới, thường nên tìm Venue đã tồn tại:

```java
Venue venue = em.find(Venue.class, venueId);

if (venue == null) {
    throw new IllegalArgumentException("Venue không tồn tại");
}

Booking booking = new Booking(venue);
em.persist(booking);
```

Nếu Venue thật sự mới trong một use case tạo venue, service có thể gọi `em.persist(venue)` tường minh rồi tạo Booking. Việc thêm `cascade=ALL` từ Booking tới Venue chỉ để tránh lỗi transient sẽ khiến xóa Booking có thể lan truyền REMOVE tới Venue, thường sai domain.

**Cascade PERSIST về mặt kỹ thuật có thể đặt trên `@ManyToOne`**, nhưng nên dùng khi đúng quyền sở hữu vòng đời, không phải vì chiều mũi tên tham chiếu.

### 8.4. `@ManyToMany`: entity chia sẻ cần được giải quyết riêng

Ví dụ BlogPost–Tag:

```java
@ManyToMany
@JoinTable(
    name = "post_tags",
    joinColumns = @JoinColumn(name = "post_id"),
    inverseJoinColumns = @JoinColumn(name = "tag_id")
)
private Set<Tag> tags = new HashSet<>();
```

Một Tag có thể được nhiều bài viết sử dụng. Nếu Tag đã tồn tại, hãy tìm hoặc lấy reference managed phù hợp trước khi gắn vào bài viết. Nếu Tag mới phải được tạo, có thể persist Tag một cách có chủ đích.

`CascadeType.REMOVE` hoặc `ALL` trên quan hệ nhiều-nhiều chia sẻ thường rất nguy hiểm. `CascadeType.PERSIST` đơn lẻ có thể hợp lệ khi nghiệp vụ cho phép tạo các Tag mới cùng bài viết, nhưng vẫn cần xử lý Tag đã tồn tại/detached, uniqueness và quy tắc dùng chung. **Cascade không phải cơ chế find-or-create/upsert**.

### 8.5. Bảng tổng hợp

| Quan hệ | Đồ thị mới thường gặp | Dùng PERSIST cascade thế nào? | Lưu ý |
|---|---|---|---|
| `OneToMany` | Order mới → Lines mới | Thường phù hợp từ root → children | Đồng bộ owning side ở child khi hai chiều |
| `OneToOne` | Account mới → Profile mới | Phù hợp nếu vòng đời phụ thuộc | Kiểm tra FK/unique/shared key |
| `ManyToOne` | Order mới → Customer mới/cũ | Thường persist/find Customer riêng | Đích có thể dùng chung |
| `ManyToMany` | Post mới → Tags | Cần cân nhắc kỹ; không dùng `ALL` mặc định | Tag có thể đã tồn tại và được chia sẻ |
| Nhiều tầng | Order → Lines → Adjustments | Mỗi cạnh cần cascade phù hợp | Một mắt xích thiếu cascade làm graph không được lưu đủ |

## 9. Không nhầm `CascadeType.PERSIST` với các loại cascade khác

### 9.1. Các loại cascade

| CascadeType | Khi thao tác gì được lan truyền? | Khi thường dùng |
|---|---|---|
| `PERSIST` | `persist` | Tạo root cùng entity con mới |
| `MERGE` | `merge` | Sao chép trạng thái graph detached/new qua merge theo mapping |
| `REMOVE` | `remove` | Xóa entity con thuộc vòng đời root |
| `REFRESH` | `refresh` | Đọc lại trạng thái entity liên quan |
| `DETACH` | `detach` | Tách entity liên quan khỏi context |
| `ALL` | Tất cả những thao tác trên | Chỉ khi đúng toàn bộ chính sách vòng đời |

Một annotation:

```java
@OneToMany(cascade = CascadeType.PERSIST)
private List<OrderLine> lines;
```

**Không** có nghĩa các Line sẽ tự bị xóa khi xóa Order, tự merge khi merge Order, hoặc tự detach khi detach Order. Những thao tác đó cần semantics/cấu hình khác.

### 9.2. `PERSIST` khác `MERGE`

`persist(newEntity)` biểu thị ý định đưa **entity mới** vào managed state. `merge(detachedEntity)` sao chép trạng thái của một entity detached/new sang một **managed instance trả về**; đối số ban đầu vẫn có thể detached.

```java
OrderLine detachedLine = ...;

OrderLine managedCopy = em.merge(detachedLine);

System.out.println(em.contains(detachedLine)); // false với detached input.
System.out.println(em.contains(managedCopy));  // true.
```

Nếu graph chứa detached Product đã lưu mà OrderLine có cascade `PERSIST` tới Product, luồng persist Order mới có thể bị lỗi do cố cascade persist một entity detached. Không khắc phục bằng việc bật thêm `MERGE` rồi tin rằng mọi trường hợp được JPA “đoán đúng”.

Trong một use case tạo Order mới, hãy **lấy Product managed hiện có theo ID** rồi gắn vào OrderLine mới. Khi cần xử lý một detached graph toàn diện, chọn `merge` có mục đích rõ và kiểm soát trạng thái dữ liệu, cascade và concurrency.

### 9.3. `PERSIST` khác `orphanRemoval`

`orphanRemoval=true` dùng cho `@OneToOne` hoặc `@OneToMany` khi một con bị gỡ khỏi association và **không còn được phép tồn tại riêng**:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.PERSIST,
    orphanRemoval = true
)
private List<OrderLine> lines = new ArrayList<>();
```

Trong mapping này:

- `cascade=PERSIST`: persist Order có thể tạo các Line mới.
- `orphanRemoval=true`: gỡ một Line thuộc vòng đời Order có thể dẫn tới xóa Line.
- Hai cơ chế phục vụ **hai thao tác khác nhau**.

Không nên mặc định bật orphanRemoval chỉ vì có cascade PERSIST. Nếu Line được phép chuyển sang Order khác hoặc tồn tại tạm thời không có Order, chính sách xóa orphan có thể không phù hợp. JPA cũng có quy tắc giới hạn đối với orphan ở trạng thái new/detached/removed; không được dựa vào việc “thêm rồi gỡ một object transient” để suy ra ORM chắc chắn DELETE một hàng.

### 9.4. Cascade của JPA khác database `ON DELETE CASCADE`

SQL có thể khai báo:

```sql
FOREIGN KEY (order_id)
REFERENCES purchase_orders(id)
ON DELETE CASCADE
```

Đây là referential action của **database khi xóa hàng cha**, khác `CascadeType.PERSIST` của JPA. DB cascade xóa không tạo entity con mới; JPA cascade persist không tự thay ràng buộc FK của schema.

Phải phân biệt:

- **JPA cascade PERSIST:** lan truyền thao tác lưu trong persistence context.
- **JPA cascade REMOVE:** lan truyền thao tác xóa entity theo ORM lifecycle.
- **DB ON DELETE CASCADE:** database tự xóa hàng phụ thuộc khi parent row bị xóa.
- **orphanRemoval:** JPA xóa child bị gỡ khỏi association sở hữu vòng đời.

## 10. Những lỗi phổ biến khi persist đồ thị mới

### 10.1. Thiếu cascade: tham chiếu transient chưa được lưu

```java
PurchaseOrder order = new PurchaseOrder("PO-2", managedCustomer);
OrderLine line = new OrderLine(managedProduct, 2, price);
order.addLine(line);

// Nếu @OneToMany không có cascade=PERSIST:
em.persist(order);
em.flush();
```

Order được yêu cầu persist nhưng Line mới chưa nhất thiết được lưu. Với quan hệ hai chiều, Line có thể chưa được ORM quản lý và bảng `order_lines` không có hàng mong đợi; với mapping khác, provider có thể ném exception vì tham chiếu transient.

Cách sửa: thêm cascade PERSIST đúng chỗ khi các Line thật sự thuộc graph cần tạo, **hoặc** persist Line tường minh trong service.

### 10.2. Có cascade nhưng không gán owning side

```java
@OneToMany(mappedBy = "order", cascade = CascadeType.PERSIST)
private List<OrderLine> lines = new ArrayList<>();

// Chỉ thay inverse collection:
lines.add(line);
```

Nếu `OrderLine.order` vẫn null, ORM không có owning-side value để điền `order_id`. Với FK `NOT NULL`, flush có thể thất bại; với nullable FK, Line có thể được lưu nhưng **không thuộc Order** theo database.

Cách sửa: helper thực hiện đồng thời `lines.add(line)` và `line.setOrder(this)`.

### 10.3. Cascade nhầm sang entity shared

```java
@ManyToOne(cascade = CascadeType.PERSIST)
private Product product;
```

Nếu Product là đối tượng độc lập đã tồn tại/detached, việc cascade `PERSIST` có thể gây lỗi hoặc xung đột khóa, thay vì “sử dụng lại Product”. Một Product new cùng SKU tồn tại cũng có thể vi phạm unique constraint.

Cách sửa: phân biệt create Product và select existing Product, lấy managed Product khi gắn vào Line. Chỉ cascade khi thật sự có quyền tạo entity đích trong cùng vòng đời.

### 10.4. Lỗi `detached entity passed to persist`

Một graph nhận từ client có thể chứa Product đã có `id=7` nhưng không managed. Nếu cascade PERSIST từ OrderLine sang Product, provider có thể từ chối thao tác persist detached Product.

Ví dụ:

```java
Product detachedProduct = ...; // Từ một EntityManager khác.
OrderLine line = new OrderLine(detachedProduct, 1, price);
order.addLine(line);
em.persist(order);
```

Khi sửa, không dùng nguyên Product detached để làm nguồn cập nhật nếu chỉ muốn tham chiếu Product. Thay bằng:

```java
Product managedProduct =
    em.find(Product.class, detachedProduct.getId());

if (managedProduct == null) {
    throw new IllegalArgumentException("Product không tồn tại");
}

OrderLine line = new OrderLine(managedProduct, 1, price);
```

Ở use case chỉ cập nhật FK, không cần merge toàn bộ trạng thái Product từ object cũ. Nếu Product có thay đổi cần lưu, đó phải là use case được kiểm soát riêng.

### 10.5. Có ID không đồng nghĩa đã persist

```java
@Entity
public class ExternalIdentity {

    @Id
    private UUID id;

    protected ExternalIdentity() {}

    public ExternalIdentity(UUID id) {
        this.id = Objects.requireNonNull(id);
    }
}
```

Một object vừa `new ExternalIdentity(UUID.randomUUID())` đã có ID nhưng vẫn là transient. Ngược lại, một detached entity cũng có ID. Dùng `em.contains(entity)` để hỏi trạng thái managed hiện tại, nhưng nếu false thì chưa đủ phân biệt new/detached.

Đừng áp dụng `if (id != null) merge else persist` cho mọi entity như một quy tắc chung; cần xét chiến lược ID, `@Version`, vòng đời và dữ liệu thực.

### 10.6. Quan hệ nhiều tầng bị thiếu cascade ở một cạnh

```text
Order --PERSIST--> Line --(không PERSIST)--> Adjustment
```

Persist Order không bảo đảm Adjustment new được persist. Cần chọn rõ cascade từ Line tới Adjustment hoặc persist Adjustment tường minh. Cascade không “nhảy qua” những association không khai báo.

### 10.7. Xử lý vòng lặp object graph

Một quan hệ hai chiều tự nhiên có vòng tham chiếu:

```text
Order.lines -> Line
Line.order  -> Order
```

Đó **không phải** lý do tránh mapping hai chiều hoặc thêm cascade hai phía một cách bừa bãi. JPA quản lý identity/state của các entity nên có cơ chế xử lý graph có chu kỳ khi mapping hợp lệ.

Tuy nhiên, không nên đặt cascade `ALL` hai chiều một cách cơ học, vì có thể lan truyền các thao tác ngoài ý định. Với Order–Line, PERSIST từ root xuống child thường đã đủ; chiều `Line.order` không cần cascade PERSIST ngược lên root.

### 10.8. `HashSet` và khóa sinh sau persist

Nếu collection children là `HashSet<OrderLine>` và entity triển khai `hashCode()` dựa trên ID được sinh sau persist, hash có thể thay đổi khi entity đang nằm trong Set. Điều này dẫn tới `remove`/`contains` của Set hoạt động sai ở Java và khó chẩn đoán.

Dùng `List` khi thứ tự/danh sách phù hợp hoặc thiết kế equality/hashCode ổn định theo vòng đời định danh. **Đừng để lỗi collection Java bị hiểu nhầm thành lỗi cascade JPA**.

## 11. Graph lớn, hiệu năng và giới hạn cascade

### 11.1. Một lần `persist(root)` không có nghĩa một câu SQL

Nếu Order có 500 Line mới, `cascade=PERSIST` yêu cầu ORM quản lý 500 child mới, nhưng database vẫn cần các thao tác INSERT tương ứng. Tùy mapping, provider và JDBC batching, chúng có thể được gửi thành nhiều statement hoặc batch; `GenerationType.IDENTITY` có thể ảnh hưởng khả năng batching ở một số provider.

```text
persist(Order)
    |
    +--- 500 OrderLine trở thành managed
                 |
                 v
           INSERT 500 dòng
           (cách gộp batch tùy provider)
```

**Cascade giúp giảm mã boilerplate quản lý vòng đời**, không loại bỏ chi phí database.

### 11.2. Batching và generated ID

Khi tạo nhiều entity con, có thể xem xét:

- Cấu hình JDBC batch size của provider.
- Chiến lược ID như `SEQUENCE` và allocation phù hợp hệ quản trị.
- Kích thước transaction để không giữ graph khổng lồ trong bộ nhớ.
- Quan sát số statement và round-trip thực tế.
- Tối ưu thứ tự ghi/insert ordering khi provider hỗ trợ.

Đừng tự ý đổi `GenerationType.IDENTITY` sang `SEQUENCE` chỉ để nhanh hơn nếu database hoặc quy ước khóa không hỗ trợ. Tính tương thích schema quan trọng hơn một giả định tối ưu.

### 11.3. Flush/clear trong batch

Với batch xử lý hàng nghìn graph:

```java
for (PurchaseOrder order : orders) {
    em.persist(order);

    // Tại các mốc phù hợp:
    // em.flush();
    // em.clear();
}
```

`flush` đồng bộ pending changes; `clear` detach tất cả managed entities. Nếu clear quá sớm khi graph còn cần tiếp tục cập nhật, các object cũ trở thành detached và sửa sau đó không tự được ghi. Hãy thiết kế batch theo từng chunk có ranh giới transaction và không dùng lại những reference detached như managed entity.

### 11.4. Cascade không thay thế fetch plan

PERSIST cascade giải quyết **việc tạo entity mới**. Nó không quyết định cách tối ưu đọc graph về sau. Nếu màn hình gọi `order.getLines()` cho hàng trăm Order, vấn đề N+1 và fetch strategy vẫn cần giải quyết bằng truy vấn/DTO/batch fetch phù hợp.

Đừng bật `FetchType.EAGER` ở mọi association chỉ vì muốn cascade PERSIST hoạt động; fetch và cascade là hai trục khác nhau.

## 12. Thiết kế API và service để tránh graph không rõ trạng thái

### 12.1. Phân biệt ID của entity cũ với dữ liệu tạo entity mới

Ví dụ request:

```json
{
  "orderCode": "PO-2026-001",
  "customerId": 12,
  "lines": [
    {
      "productId": 7,
      "quantity": 2,
      "unitPrice": "890000.00"
    },
    {
      "productId": 9,
      "quantity": 1,
      "unitPrice": "240000.00"
    }
  ]
}
```

Request này truyền **ID của Customer/Product đã có** và **dữ liệu mới cho Order/OrderLine**. Service tự quyết định entity nào cần tạo, entity nào cần tìm.

Nếu deserialize JSON thành các JPA entity rồi gọi `save` lên graph, ứng dụng có thể vô tình tạo Customer/Product mới hoặc merge field không mong muốn. DTO/command rõ nghĩa giúp tránh nhầm transient, detached và managed.

### 12.2. Ví dụ service Spring

Giả sử dùng repository hoặc `EntityManager` trong một service transaction:

```java
@Service
public class OrderService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public Long createOrder(CreateOrderCommand command) {
        Customer customer = em.find(
            Customer.class, command.customerId());

        if (customer == null) {
            throw new IllegalArgumentException("Customer không tồn tại");
        }

        PurchaseOrder order =
            new PurchaseOrder(command.orderCode(), customer);

        for (CreateLineCommand input : command.lines()) {
            Product product = em.find(
                Product.class, input.productId());

            if (product == null) {
                throw new IllegalArgumentException(
                    "Product không tồn tại: " + input.productId());
            }

            order.addLine(new OrderLine(
                product, input.quantity(), input.unitPrice()));
        }

        em.persist(order);
        em.flush(); // Ví dụ lấy ID/kiểm tra lỗi đồng bộ sớm.
        return order.getId();
    }
}
```

Ví dụ giả định `CreateOrderCommand` là DTO/record gồm `orderCode()`, `customerId()` và `lines()`; `CreateLineCommand` gồm `productId()`, `quantity()` và `unitPrice()`. Cần cấu hình Spring `@Service`, `@Transactional`, `@PersistenceContext` và imports tương ứng.

**Phạm vi cascade trong service này:**

```text
New Order
   |
   +--- PERSIST ---> New Line A
   |
   +--- PERSIST ---> New Line B

Existing Customer / Product: được tìm bằng ID, không persist lại.
```

Ngoài mapping, service thực tế cần kiểm tra quyền sử dụng Customer/Product, trạng thái catalog, tính hợp lệ của giá, tổng tiền, trùng order code và những quy tắc domain khác.

### 12.3. `save()` của Spring Data JPA vẫn phụ thuộc cascade

```java
orderRepository.save(order);
```

không đồng nghĩa “tất cả object trong graph chắc chắn được lưu”. Spring Data JPA chọn persist/merge dựa trên cách nhận diện entity mới theo cấu hình, còn việc lan truyền tới các relation vẫn theo metadata JPA.

Nếu root mới nhưng graph chứa entity detached hoặc các relation thiếu cascade, `save` vẫn có thể dẫn đến lỗi khi flush. `saveAndFlush` chỉ yêu cầu flush sớm hơn; nó không tự sửa owning side hoặc biến shared entities thành managed đúng cách.

## 13. Transaction, constraint và kiểm chứng kết quả

### 13.1. Luôn tạo graph trong transaction có phạm vi phù hợp

Với các entity mới phụ thuộc nhau, một transaction giúp đảm bảo tính nguyên tử:

```text
Begin transaction
  |
  +--- persist Order
  +--- cascade persist Lines
  +--- flush SQL / validate constraints
  |
  +--- commit thành công ---> Order và Lines được lưu cùng nhau
  |
  +--- lỗi / rollback -----> Không có graph mới được commit một phần
```

Nếu flush thất bại do FK/unique/not-null hoặc lỗi persistence khác, cần rollback transaction và xử lý lại trong context phù hợp. Không cố tiếp tục commit một transaction đã gặp lỗi như thể chưa xảy ra gì.

### 13.2. Các ràng buộc cần thiết

`@ManyToOne(optional=false)` và `@JoinColumn(nullable=false)` diễn tả quan hệ bắt buộc ở mapping, nhưng schema vẫn cần `NOT NULL`/`FOREIGN KEY` thực. Với các business keys như `order_code` hoặc `product.sku` cần uniqueness, đặt unique constraint trong database.

Cascade không bỏ qua được các constraint đó; mọi child mới vẫn phải tạo row hợp lệ.

### 13.3. Dùng `contains` để quan sát vòng đời, không thay cho xác minh DB

```java
OrderLine line = new OrderLine(product, 2, price);
order.addLine(line);

System.out.println(em.contains(line)); // false khi còn new.

em.persist(order);

System.out.println(em.contains(line)); // true sau cascade PERSIST.
```

Kết quả true chỉ chứng minh Line đang managed trong context hiện tại. Nó **không** chứng minh SQL đã commit.

Sau commit thành công, nếu cần kiểm chứng dữ liệu đã ghi, mở `EntityManager` mới rồi tìm Order/Line hoặc dùng truy vấn SQL/JDBC trên nguồn dữ liệu phù hợp. Chỉ gọi `find` trong cùng context cũ có thể đọc lại managed instance từ L1 cache.

### 13.4. Ví dụ integration test theo ranh giới commit

Một phép kiểm tra độc lập có thể tổ chức như sau:

```java
EntityManager writer = emf.createEntityManager();
Long orderId;

try {
    writer.getTransaction().begin();

    Customer customer = writer.find(Customer.class, 12L);
    Product product = writer.find(Product.class, 7L);

    PurchaseOrder order =
        new PurchaseOrder("PO-INTEGRATION-1", customer);
    order.addLine(new OrderLine(
        product, 2, new BigDecimal("100000.00")));

    writer.persist(order);
    writer.flush();

    orderId = order.getId();
    writer.getTransaction().commit();
} catch (RuntimeException ex) {
    if (writer.getTransaction().isActive()) {
        writer.getTransaction().rollback();
    }
    throw ex;
} finally {
    writer.close();
}

EntityManager reader = emf.createEntityManager();
try {
    reader.getTransaction().begin();

    PurchaseOrder actual =
        reader.find(PurchaseOrder.class, orderId);

    if (actual == null || actual.getLines().size() != 1) {
        throw new AssertionError("Graph không được lưu như mong đợi");
    }

    reader.getTransaction().commit();
} finally {
    reader.close();
}
```

Ví dụ dùng `RESOURCE_LOCAL` và giả định Customer/Product test data đã tồn tại. Trong môi trường bật L2 cache, việc dùng reader mới tránh L1 cũ nhưng chưa chắc buộc SELECT từ bảng; khi cần kiểm chứng SQL vật lý, dùng bypass cache hoặc scalar SQL/JDBC.

Đoạn test chỉ minh họa ranh giới transaction và lifecycle của graph; ứng dụng có thể bổ sung rollback cho reader nếu xảy ra exception và tạo dữ liệu test độc lập.

## 14. Các tình huống đặc biệt

### 14.1. Graph có khóa ghép và `@MapsId`

Đôi khi entity con có primary key phụ thuộc parent, ví dụ `OrderLine` được định danh bởi `(orderId, lineNumber)`. Khi dùng `@EmbeddedId` và `@MapsId`, relationship đến Order tham gia vào identity của Line.

Cascade PERSIST vẫn có thể đưa graph mới vào persistence context, nhưng ID cần được xác lập đúng theo derived identity. Một line không thể có khóa hợp lệ nếu không xác định parent và thành phần khóa còn lại.

Không nên cố gán ID null/không đồng bộ rồi nghĩ cascade sẽ tự tìm ra lineNumber hoặc tạo một natural key không được khai báo. Derived identity và cascade là hai cơ chế hợp tác, không thay thế nhau.

### 14.2. Entity mới được tham chiếu từ nhiều node

Giả sử hai Line cùng tham chiếu một `Product` mới được tạo. Nếu Product thật sự được phép tạo cùng đơn, service có thể persist Product **một lần** rồi dùng cùng managed instance cho cả hai Line.

Nếu Product được cascade persist qua nhiều nhánh graph, provider quản lý identity của cùng instance, nhưng application vẫn phải tránh tạo **hai object Product khác nhau cùng business key** và đặt unique constraint tương ứng. Cascade không hợp nhất những object khác instance chỉ vì `sku` bằng nhau.

### 14.3. Đồ thị có nhiều root

Có thể một transaction tạo hai Order cùng chung một Customer mới. Nếu Customer thực sự mới và dùng chung, service nên persist Customer tường minh, rồi tạo cả hai Order tham chiếu đến cùng managed Customer:

```java
Customer customer = new Customer("Khách mới");
em.persist(customer);

PurchaseOrder first = new PurchaseOrder("PO-A", customer);
PurchaseOrder second = new PurchaseOrder("PO-B", customer);

first.addLine(new OrderLine(product, 1, price));
second.addLine(new OrderLine(product, 3, price));

em.persist(first);
em.persist(second);
```

PERSIST cascade từ mỗi Order tới các Line. Customer được quản lý riêng đúng với vòng đời độc lập của nó. Không phải cứ có nhiều graph mới thì cần một root cascade chung cho mọi entity.

### 14.4. Điều gì xảy ra nếu entity target bị removed?

Nếu một association từ graph mới tham chiếu tới entity đang ở trạng thái removed, đó không phải target hợp lệ để coi là “đã tồn tại có thể dùng lại”. Tùy cascade, flush, constraint và provider, ORM có thể ném lỗi hoặc tạo thao tác vòng đời khó dự đoán.

Không dùng cascade PERSIST để “hồi sinh” đối tượng vừa bị xóa mà không có quy trình domain rõ ràng. Hãy quyết định liệu entity bị xóa có được phép khôi phục hay phải tạo một entity mới với identity phù hợp.

### 14.5. Cascade validation không phải cascade persistence

Trong một DTO/entity graph có thể có:

```java
@Valid
private List<LineInput> lines;
```

`@Valid` của Bean Validation lan truyền **kiểm tra dữ liệu**, không lan truyền `EntityManager.persist`. Tương tự, `@NotNull` trên field association không làm target transient trở thành managed.

Có thể cần đồng thời Bean Validation, cascade PERSIST và schema constraints, nhưng chúng giải quyết những trách nhiệm khác nhau.

## 15. Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Order lưu được, Line không có hàng | Không cascade PERSIST tới Line và không persist tường minh | Chọn một chiến lược lưu con |
| Line được INSERT nhưng `order_id` null | Không thiết lập owning side `Line.order` | Dùng helper gán cả hai phía |
| Lỗi transient association khi flush | Target mới chưa được persist; thiếu cascade hoặc đường persist | Persist target đúng lifecycle |
| Lỗi detached entity passed to persist | Cascade PERSIST tới object đã lưu ở context khác | Dùng managed instance theo ID hoặc xử lý merge có chủ đích |
| Product bị tạo trùng | Client tạo Product mới thay vì tham chiếu Product cũ | Dùng ID/business key, query managed Product và unique constraint |
| Xóa Order vô tình xóa Customer/Product | Dùng cascade REMOVE/ALL trên quan hệ shared | Giới hạn cascade theo ownership thực |
| Chỉ dòng đầu được lưu, các Adjustment mất | Thiếu cascade ở tầng Line → Adjustment | Cấu hình PERSIST ở đúng cạnh hoặc persist explicit |
| Flush vi phạm NOT NULL dù đã cascade | Owning-side field null hoặc SQL/mapping không đáp ứng schema | Kiểm tra relation, FK, nullability và SQL ordering |
| `contains(line)` vẫn false ngay sau `addLine` | Chỉ đổi Java collection, chưa thực hiện cascade/persist | Phân biệt add với persist/flush |
| Có ID nhưng INSERT không xảy ra | Object có assigned ID nhưng vẫn transient, hoặc luồng detached | Xác minh lifecycle và transaction |
| Test đọc cùng object thấy đúng nhưng DB không có | Chỉ assert trên managed object hoặc transaction rollback | Commit và kiểm chứng bằng context/SQL mới |
| INSERT hàng loạt quá chậm | Graph lớn, nhiều statement, generator/batch chưa phù hợp | Đo SQL/round-trip, batching, chunk, ID strategy |
| Vi phạm unique khi tạo Tag/Product | Có đối tượng trùng business key hoặc race condition | Lookup/create có kiểm soát và constraint DB |
| `orphanRemoval` xóa Line khi muốn chuyển chủ | Lifecycle ownership không khớp nghiệp vụ | Đánh giá lại orphanRemoval, không chuyển orphan tùy tiện |

## 16. Bài thực hành

### Bài 1 — Lưu Order mới với hai Line mới

Tạo `PurchaseOrder` và `OrderLine` như mục 4, cấu hình `cascade=PERSIST` ở `PurchaseOrder.lines`. Tải Customer/Product có sẵn bằng `find`, tạo Order/Lines, gọi `order.addLine` rồi `em.persist(order)`.

Quan sát các entity nào được managed và các câu `INSERT` thực tế. Sau commit, dùng context mới kiểm tra FK trong `order_lines` và đảm bảo Customer/Product không bị INSERT thêm.

### Bài 2 — Cố ý bỏ owning side

Thử thay `addLine` bằng đoạn chỉ thêm vào collection:

```java
order.getLines().add(line); // Minh họa ý tưởng bỏ setOrder.
```

Nếu API trả collection read-only như ví dụ, hãy viết một helper thử nghiệm riêng để tái hiện thay đổi inverse side mà không set owning side. Quan sát SQL và lỗi FK. Giải thích vì sao cascade PERSIST có thể hoạt động nhưng relationship vẫn sai.

### Bài 3 — Bỏ cascade PERSIST

Giữ helper thiết lập `line.order` nhưng bỏ `cascade=PERSIST` khỏi `@OneToMany`. Persist Order, flush và kiểm tra Line. Sau đó thử gọi `em.persist(line)` tường minh và so sánh kết quả.

Phân biệt **lưu entity** với **thiết lập foreign key**.

### Bài 4 — Cascade nhiều tầng

Thêm `LineAdjustment` phụ thuộc `OrderLine`. Bật PERSIST ở cả Order → Line và Line → Adjustment, rồi tạo cả ba tầng trước khi `em.persist(order)`.

Bỏ cascade ở tầng thứ hai để quan sát graph không được lưu đủ. Đối chiếu lý do với sơ đồ đường cascade.

### Bài 5 — Customer mới và Customer cũ

Tạo hai use case:

1. Tạo Customer mới rồi Order mới trong cùng transaction bằng persist tường minh cho Customer.
2. Tạo Order mới cho Customer đã có bằng `em.find`.

Giải thích vì sao không nên thêm `CascadeType.ALL` vào `Order.customer` chỉ để gộp hai use case.

### Bài 6 — ManyToMany với Tag dùng chung

Tạo hai bài viết cùng một Tag đã tồn tại. Lưu các bài viết và bảng nối. Thử bật cascade PERSIST rồi truyền một Tag detached vào một Post mới.

Quan sát lỗi, phân tích vì sao cần tìm managed Tag và bảo vệ uniqueness. Không sử dụng cascade REMOVE cho entity được chia sẻ.

### Bài 7 — Thêm con vào parent đã managed

Tải Order đã có trong database, thêm một Line mới. Kiểm tra `em.contains(line)` ngay sau Java `addLine`, sau `em.persist(line)` tường minh và sau flush ở phương án dùng cascade.

Giải thích khi nào JPA thực hiện PERSIST cascade và vì sao một lời gọi collection không phải lệnh EntityManager.

### Bài 8 — Flush khác commit

Tạo Order và Line, gọi `em.persist(order)` rồi `em.flush()`. Kiểm tra trạng thái managed; sau đó rollback. Mở EntityManager mới để truy vấn.

Giải thích vì sao `contains=true` và ID đã được cấp không bảo đảm dữ liệu đã commit.

### Bài 9 — Gỡ child và orphanRemoval

Lưu Order và Line, sau đó gỡ Line khỏi Order với hai mapping:

- `cascade=PERSIST`, `orphanRemoval=false`.
- `cascade=PERSIST`, `orphanRemoval=true`.

Quan sát khác nhau khi child đang managed và relation được thay đổi hợp lệ. Giải thích vì sao cascade PERSIST chỉ liên quan việc **tạo mới**, không phải quy tắc **xóa**.

### Bài 10 — Kiểm tra graph lớn

Tạo 500 OrderLine mới dưới một Order. Theo dõi số INSERT, số round-trip, ID generation và thời gian flush. Thử cấu hình batch phù hợp với provider/database; so sánh dựa trên log/metric thực thay vì giả định rằng “persist một lần” tương đương “SQL một lần”.

## 17. Ghi nhớ cốt lõi

**`CascadeType.PERSIST` cho phép lan truyền thao tác persist qua các association được cấu hình, đặc biệt hữu ích khi tạo một aggregate gồm root và nhiều entity con mới.** Với `PurchaseOrder → OrderLine`, chỉ cần persist Order nếu các Line thuộc quyền sở hữu vòng đời của Order và mapping đã khai báo cascade PERSIST phù hợp.

Tuy nhiên, **cascade không tự thiết lập foreign key**: trong quan hệ hai chiều, phải đồng bộ owning side như `OrderLine.order`. Nó cũng **không tự tìm entity đã tồn tại**, **không upsert**, **không biến detached thành managed bằng cách persist**, và **không thay thế transaction/constraint**.

Khi thiết kế một đồ thị mới, hãy chia đối tượng thành **entity mới cần lưu cùng root** và **entity độc lập đã có cần tham chiếu**. Cascade PERSIST theo những cạnh sở hữu vòng đời; dùng `find`/managed reference hoặc persist tường minh cho target dùng chung; tránh cascade REMOVE/ALL theo thói quen. Sau cùng, flush và commit trong transaction hợp lệ, rồi kiểm tra dữ liệu đã ghi qua một lượt đọc phù hợp để xác nhận cả entity lẫn association.

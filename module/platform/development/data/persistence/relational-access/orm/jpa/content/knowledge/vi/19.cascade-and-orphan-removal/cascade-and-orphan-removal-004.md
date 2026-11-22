# Áp dụng REMOVE theo ranh giới sở hữu dữ liệu trong JPA

Trong **Jakarta Persistence (JPA)**, thao tác `EntityManager.remove()` xóa một entity khỏi cơ sở dữ liệu theo quy tắc vòng đời entity. Khi entity có quan hệ đến những entity khác, ta còn có thể yêu cầu **lan truyền thao tác xóa** bằng `CascadeType.REMOVE` hoặc `CascadeType.ALL`.

Nhưng việc một entity **có tham chiếu** tới entity khác không đồng nghĩa nó **sở hữu vòng đời** của entity kia. Một đơn hàng có các dòng hàng riêng thuộc về nó, đồng thời tham chiếu tới một khách hàng và nhiều sản phẩm. Xóa đơn hàng nháp có thể hợp lý khi xóa các dòng hàng đi kèm, nhưng không bao giờ nên vì thế mà xóa khách hàng hoặc danh mục sản phẩm dùng chung.

Đây là nguyên tắc của bài học:

> **Chỉ lan truyền REMOVE khi entity nguồn thực sự có quyền kết thúc vòng đời của entity đích.** Quyền này phải xuất phát từ ranh giới sở hữu dữ liệu và quy tắc nghiệp vụ, không phải chỉ vì trong Java có field liên kết hay trong SQL có khóa ngoại.

Ví dụ cấu hình có chủ đích:

```java
// Một PurchaseOrder thực sự sở hữu vòng đời của các OrderLine.
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.REMOVE
)
private List<OrderLine> lines = new ArrayList<>();

// PurchaseOrder chỉ THAM CHIẾU Customer; không sở hữu Customer.
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
```

Cấu hình đầu tiên cho phép xóa dòng hàng cùng đơn hàng khi phù hợp domain. Cấu hình thứ hai **không** xóa khách hàng khi xóa đơn. Bài viết giải thích cách xác định ranh giới sở hữu, viết mapping chính xác, xử lý `orphanRemoval`, foreign key, database cascade, transaction, hiệu năng, dữ liệu lịch sử và các tình huống nguy hiểm.

## 1. Thế nào là ranh giới sở hữu dữ liệu?

Trong mô hình nghiệp vụ, một entity có thể:

- **Sở hữu vòng đời một entity khác:** nếu entity cha không tồn tại nữa, entity con không còn ý nghĩa hoặc không được phép tồn tại độc lập.
- **Chỉ giữ liên kết đến một entity độc lập:** entity được liên kết có danh tính và vòng đời riêng, có thể được nhiều nơi tham chiếu.
- **Có quan hệ nghiệp vụ cần lưu lịch sử:** dù một đối tượng được tạo ra trong quy trình của đối tượng khác, pháp lý hoặc audit có thể yêu cầu dữ liệu tiếp tục tồn tại.

Ví dụ hệ thống thương mại điện tử:

```text
                        Customer#10
                            ^
                            | tham chiếu, KHÔNG xóa theo
                            |
                      PurchaseOrder#100
                            |
              +-------------+------------------+
              |                                |
      SỞ HỮU vòng đời                    Quan hệ khác
              |                                |
        +-----+------+                  PaymentRecord#501
        |            |                   (lịch sử giao dịch)
    OrderLine#1  OrderLine#2             không tự động xóa
        |            |
        v            v
     Product#8     Product#9
       (chia sẻ, KHÔNG xóa theo)
```

Khi xóa một **đơn hàng nháp**:

1. Hai dòng `OrderLine#1` và `OrderLine#2` có thể được xóa theo nếu chúng thực sự thuộc riêng đơn hàng đó.
2. `Customer#10` tiếp tục tồn tại.
3. `Product#8` và `Product#9` tiếp tục tồn tại vì nhiều đơn hàng khác có thể tham chiếu chúng.
4. Nếu đã có `PaymentRecord#501`, nghiệp vụ có thể **không cho phép xóa vật lý đơn hàng**. Tùy yêu cầu lưu trữ, có thể hủy trạng thái đơn hoặc lưu lịch sử thay vì xóa.

**Ranh giới sở hữu không nhất thiết trùng với quan hệ `@OneToMany`.** Một người dùng có thể có nhiều bài viết nhưng chưa chắc việc xóa tài khoản người dùng được phép xóa toàn bộ bài viết đã được công bố. Quy tắc đó phụ thuộc domain, không phụ thuộc một annotation JPA đơn lẻ.

### 1.1. Aggregate và vòng đời phụ thuộc

Trong Domain-Driven Design, một *aggregate* thường có *aggregate root* chịu trách nhiệm giữ các bất biến nghiệp vụ. Các entity con nằm trong aggregate có thể có ID riêng, nhưng những thao tác tạo/sửa/xóa chúng được điều phối qua root.

Ví dụ `Cart` và `CartLine`:

```text
Cart (aggregate root)
    |
    +-- CartLine (thuộc riêng cart)
    +-- CartLine (thuộc riêng cart)
```

Xóa cart có thể xóa toàn bộ cart line. Nhưng `CartLine.product` trỏ tới `Product` trong catalog là quan hệ **tham chiếu qua ranh giới aggregate**: catalog product phải sống độc lập.

Tư duy aggregate hữu ích để thiết kế cascade, nhưng không cần biến mọi quan hệ JPA thành aggregate. Hãy hỏi **ai được phép xóa ai**, không phải chỉ hỏi **ai chứa collection nào**.

### 1.2. Sở hữu dữ liệu khác owning side của JPA

Có hai khái niệm dùng chữ “sở hữu” nhưng ý nghĩa khác nhau:

| Khái niệm | Câu hỏi nó trả lời |
| --- | --- |
| **Sở hữu vòng đời theo domain** (*lifecycle ownership*) | Khi xóa A, có được phép hoặc cần xóa B không? |
| **Owning side trong mapping JPA** | Phía nào của association chịu trách nhiệm ánh xạ khóa ngoại hoặc bảng liên kết? |

Trong quan hệ hai chiều:

```java
// Ở cha:
@OneToMany(mappedBy = "order")
private List<OrderLine> lines;

// Ở con:
@ManyToOne
@JoinColumn(name = "order_id")
private PurchaseOrder order;
```

`OrderLine.order` là **owning side JPA** vì nó quản lý `order_id`. Tuy nhiên, về **vòng đời nghiệp vụ**, `PurchaseOrder` có thể sở hữu `OrderLine` và được quyền xóa con. Không có mâu thuẫn: mỗi khái niệm áp dụng ở một tầng khác nhau.

**Không đặt cascade REMOVE từ con về cha chỉ vì `@ManyToOne` là owning side.**

## 2. CascadeType.REMOVE hoạt động như thế nào?

Khi gọi:

```java
entityManager.remove(parent);
```

JPA chuyển một **managed parent entity** sang trạng thái `removed`. Nếu association từ parent đến children khai báo `cascade = CascadeType.REMOVE`, thao tác remove được lan truyền tới các entity đích phù hợp.

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.REMOVE
)
private List<OrderLine> lines = new ArrayList<>();
```

Về mặt logic:

```text
entityManager.remove(order)
             |
             +-- remove(OrderLine#1)
             |
             +-- remove(OrderLine#2)
             |
             +-- remove(PurchaseOrder#100)
```

Thứ tự minh họa cho ý nghĩa vòng đời, **không phải bảo đảm provider gọi Java method hoặc phát SQL theo đúng sơ đồ này**. Provider sẽ đồng bộ những thay đổi phù hợp với transaction, khóa ngoại và mapping.

### 2.1. REMOVE là lan truyền thao tác, không phải tự tải dữ liệu

`CascadeType.REMOVE` chỉ quy định loại thao tác lifecycle được truyền. Nó không tương đương:

- `FetchType.EAGER`: yêu cầu tải liên kết chủ động.
- `orphanRemoval = true`: xử lý con bị tách khỏi quan hệ.
- `ON DELETE CASCADE`: quy tắc xóa ở database.
- `@JoinColumn`: cấu hình khóa ngoại.
- `@Version`: cơ chế optimistic locking.

Một collection `LAZY` vẫn có thể cascade REMOVE. Provider có thể cần truy vấn để tìm các child phải xóa; **LAZY không chặn việc xóa lan truyền**.

### 2.2. Cascade REMOVE có mặc định bật không?

Không. Với các relationship annotations, khi không khai báo `cascade`, mặc định là **không có cascade JPA**.

```java
@OneToMany(mappedBy = "order")
private List<OrderLine> lines;
```

Đoạn trên không yêu cầu `remove(order)` lan truyền đến từng OrderLine.

Nếu child có khóa ngoại `NOT NULL` đến order, xóa order có thể bị database từ chối do FK nếu không có chính sách xử lý children phù hợp.

### 2.3. CascadeType.ALL bao gồm những gì?

`CascadeType.ALL` bao gồm các thao tác JPA tiêu chuẩn:

- `PERSIST`
- `MERGE`
- `REMOVE`
- `REFRESH`
- `DETACH`

Ví dụ:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL
)
private List<OrderLine> lines;
```

Cấu hình này **không chỉ tiện cho persist**: nó cũng cho phép xóa, refresh và detach lan truyền. Nếu chỉ cần tạo và cập nhật con, nên dùng:

```java
cascade = {CascadeType.PERSIST, CascadeType.MERGE}
```

thay vì bật `ALL` theo thói quen. Thêm `REMOVE` là một **quyết định nghiệp vụ riêng**, không phải hệ quả tất yếu của việc entity liên quan.

## 3. Phạm vi REMOVE portable trong JPA

Theo các quy tắc chuẩn của Jakarta Persistence, việc sử dụng `cascade = REMOVE` được thiết kế cho các association như **`@OneToOne` và `@OneToMany`**. Áp dụng cascade REMOVE qua những association chia sẻ như `@ManyToMany` hoặc chiều `@ManyToOne` không nên được coi là hành vi portable an toàn; các provider có thể có cách xử lý riêng, nhưng **nghiệp vụ xóa có thể sai ngay cả khi code chạy được**.

Bảng định hướng:

| Quan hệ | Có thể hợp lý để cascade REMOVE? | Điều kiện nghiệp vụ |
| --- | --- | --- |
| `@OneToOne` | Có | Entity đích là đối tượng phụ thuộc riêng, không chia sẻ và không có nghĩa vụ lưu độc lập. |
| `@OneToMany` | Có | Các con thuộc vòng đời cha, không được chuyển sang chủ khác và được phép xóa cùng cha. |
| `@ManyToOne` | Thường không | Parent đích thường được nhiều entity tham chiếu; xóa một child không được xóa parent. |
| `@ManyToMany` | Tránh cascade REMOVE | Entity hai phía thường độc lập; xóa association không đồng nghĩa xóa entity được chia sẻ. |

**Không dùng bảng này như một quy tắc chỉ nhìn multiplicity.** Có quan hệ `@OneToMany` nhưng entity con vẫn độc lập về quyền sở hữu, luật lưu trữ hoặc audit. Ngược lại, một `@OneToOne` có thể chỉ là một liên kết giữa hai entity độc lập. Hãy đánh giá chính sách vòng đời trước khi bật cascade.

## 4. Ví dụ nhất quán: PurchaseOrder và OrderLine

Giả sử hệ thống có những entity:

- `Customer`: khách hàng tồn tại độc lập, có nhiều đơn hàng.
- `Product`: sản phẩm thuộc catalog, được nhiều dòng đơn tham chiếu.
- `PurchaseOrder`: đơn hàng do khách hàng tạo.
- `OrderLine`: dòng chi tiết của một đơn hàng, lưu snapshot số lượng/giá tại thời điểm đặt.

Giả sử nghiệp vụ cho phép **xóa vật lý đơn hàng DRAFT chưa phát sinh thanh toán**, đồng thời xóa các dòng của đơn. Khi đơn hàng đã thanh toán/xuất hóa đơn, hệ thống có chính sách lưu lịch sử khác.

### 4.1. Schema SQL minh họa

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    display_name VARCHAR(120) NOT NULL
);

CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    order_state VARCHAR(20) NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(15, 2) NOT NULL CHECK (unit_price >= 0),
    CONSTRAINT fk_lines_order
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id),
    CONSTRAINT fk_lines_product
        FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE payment_records (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    provider_reference VARCHAR(100) NOT NULL,
    CONSTRAINT fk_payments_order
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id)
);
```

Trong schema này:

- `order_lines.order_id` là FK đến bảng đơn hàng.
- `order_lines.product_id` là FK đến product; xóa OrderLine **không xóa Product**.
- `purchase_orders.customer_id` là FK đến customer; xóa Order **không xóa Customer**.
- `payment_records.order_id` là FK giữ lịch sử thanh toán. Nếu đã có record, FK có thể chặn xóa order; đó có thể là điều mong muốn.

Quan hệ *bảng nào chứa khóa ngoại* **không quyết định hướng cascade REMOVE**. Dù `OrderLine` giữ FK đến `Product`, nó không được phép xóa product.

### 4.2. Entity Customer và Product

Hai entity này có vòng đời độc lập:

```java
package com.example.shop;

import jakarta.persistence.*;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "display_name", nullable = false, length = 120)
    private String displayName;

    protected Customer() {}

    public Customer(String displayName) {
        this.displayName = displayName;
    }

    public Long getId() { return id; }
}
```

```java
package com.example.shop;

import jakarta.persistence.*;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 80)
    private String sku;

    protected Product() {}

    public Product(String sku) {
        this.sku = sku;
    }

    public Long getId() { return id; }
}
```

Các entity này được tạo bởi quy trình quản lý khách hàng/catalog riêng. Đơn hàng chỉ **tham chiếu** chúng. Vì vậy trong `PurchaseOrder` hoặc `OrderLine` không khai báo `CascadeType.REMOVE` trên các association tới `Customer`, `Product`.

### 4.3. Entity PurchaseOrder

```java
package com.example.shop;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import jakarta.persistence.*;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    public enum State { DRAFT, CONFIRMED, CANCELLED }

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Enumerated(EnumType.STRING)
    @Column(name = "order_state", nullable = false, length = 20)
    private State state = State.DRAFT;

    @Version
    @Column(nullable = false)
    private Long version;

    @OneToMany(
        mappedBy = "order",
        fetch = FetchType.LAZY,
        cascade = {
            CascadeType.PERSIST,
            CascadeType.MERGE,
            CascadeType.REMOVE
        }
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public PurchaseOrder(Customer customer) {
        this.customer = Objects.requireNonNull(customer);
    }

    public void addLine(
            Product product,
            int quantity,
            BigDecimal unitPrice) {
        if (state != State.DRAFT) {
            throw new IllegalStateException("Order is not a draft");
        }
        OrderLine line = new OrderLine(product, quantity, unitPrice);
        line.assignOrder(this);
        lines.add(line);
    }

    public Long getId() { return id; }
    public State getState() { return state; }
    public List<OrderLine> getLines() { return lines; }

    public void confirm() {
        if (state != State.DRAFT) {
            throw new IllegalStateException("Only drafts can be confirmed");
        }
        state = State.CONFIRMED;
    }
}
```

Ở đây:

- `@ManyToOne customer` **không có cascade**: đơn hàng không sở hữu vòng đời khách hàng.
- `@OneToMany lines` có `CascadeType.REMOVE` vì ví dụ giả định dòng đơn thuộc riêng đơn hàng.
- `PERSIST` và `MERGE` được khai báo bổ sung vì nghiệp vụ cũng muốn tạo/cập nhật dòng qua đơn hàng.
- **Không dùng `CascadeType.ALL`** chỉ vì muốn ba thao tác đó; cách liệt kê giúp thấy rõ chính sách.
- Ví dụ này **không bật `orphanRemoval`** để tách biệt việc xóa cả đơn với việc gỡ một dòng trong các phần tiếp theo.

### 4.4. Entity OrderLine

```java
package com.example.shop;

import java.math.BigDecimal;
import java.util.Objects;
import jakarta.persistence.*;

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

    @Column(nullable = false)
    private int quantity;

    @Column(
        name = "unit_price",
        nullable = false,
        precision = 15,
        scale = 2
    )
    private BigDecimal unitPrice;

    protected OrderLine() {}

    OrderLine(Product product, int quantity, BigDecimal unitPrice) {
        this.product = Objects.requireNonNull(product);
        this.unitPrice = Objects.requireNonNull(unitPrice);

        if (quantity <= 0 || unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Invalid order line");
        }
        this.quantity = quantity;
    }

    void assignOrder(PurchaseOrder order) {
        this.order = order;
    }

    public Long getId() { return id; }
    public Product getProduct() { return product; }
    public PurchaseOrder getOrder() { return order; }
}
```

`OrderLine.order` là owning side của association và điều khiển khóa ngoại `order_id`. Nhưng **cascade REMOVE từ PurchaseOrder tới OrderLine** được khai báo trên phía cha `@OneToMany`. Hai hướng này hoàn toàn hợp lệ và có mục đích khác nhau.

Đặc biệt:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
private Product product;
```

không có `cascade = REMOVE`. Nếu thêm cascade REMOVE tại đây, khi xóa dòng đơn, provider có thể lan truyền xóa sản phẩm catalog được nhiều đơn khác sử dụng — một lỗi nghiệp vụ nghiêm trọng.

## 5. Luồng xóa đơn nháp trong transaction

Với các entity đã tồn tại, một service Java SE sử dụng `EntityManager` có thể:

```java
package com.example.shop;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;

public final class DraftOrderDeletionService {
    private final EntityManagerFactory factory;

    public DraftOrderDeletionService(EntityManagerFactory factory) {
        this.factory = factory;
    }

    public boolean deleteDraft(long orderId) {
        EntityManager em = factory.createEntityManager();

        try {
            EntityTransaction tx = em.getTransaction();

            try {
                tx.begin();

                PurchaseOrder order =
                    em.find(PurchaseOrder.class, orderId);

                if (order == null) {
                    tx.commit();
                    return false;
                }

                if (order.getState() != PurchaseOrder.State.DRAFT) {
                    throw new IllegalStateException(
                        "Only draft orders can be deleted"
                    );
                }

                Long paymentCount = em.createQuery(
                        "SELECT COUNT(p) FROM PaymentRecord p " +
                        "WHERE p.order.id = :orderId",
                        Long.class
                    )
                    .setParameter("orderId", orderId)
                    .getSingleResult();

                if (paymentCount > 0) {
                    throw new IllegalStateException(
                        "Order has payment history"
                    );
                }

                em.remove(order); // Cascade REMOVE đến OrderLine.

                tx.commit();
                return true;
            } catch (RuntimeException error) {
                if (tx.isActive()) {
                    tx.rollback();
                }
                throw error;
            }
        } finally {
            em.close();
        }
    }
}
```

Trong đoạn này, `PaymentRecord` là entity lưu ở bảng `payment_records`; một mapping tối thiểu của nó:

```java
package com.example.shop;

import jakarta.persistence.*;

@Entity
@Table(name = "payment_records")
public class PaymentRecord {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "provider_reference", nullable = false)
    private String providerReference;

    protected PaymentRecord() {}
}
```

Các class minh họa sử dụng cùng package và một persistence unit có đủ entity. Ví dụ giả định resource-local transaction đã được cấu hình; với Spring/JTA, transaction boundary sẽ khác.

### 5.1. Các bước nghiệp vụ

```text
BEGIN TRANSACTION
        |
        +-- find(PurchaseOrder, id)
        |         |
        |         +-- null -> kết quả "không tồn tại"
        |
        +-- Kiểm tra trạng thái DRAFT
        |
        +-- Kiểm tra không có payment history
        |
        +-- remove(order)
        |         |
        |         +-- cascade REMOVE đến OrderLine thuộc order
        |
        +-- FLUSH / COMMIT
                  |
                  +-- DB ghi các DELETE đúng constraint
                  +-- Customer và Product còn nguyên
                  +-- Transaction thành công hoặc rollback
```

Việc kiểm tra payment giúp code thể hiện quy tắc domain. **Database FK tiếp tục là lớp bảo vệ cuối cùng** nếu có giao dịch khác tạo payment hoặc còn tham chiếu không được xử lý. Để bảo đảm một invariant dưới cạnh tranh, cần locking/isolation hoặc các cơ chế đồng bộ nghiệp vụ tương ứng; một câu `COUNT` trước delete không ngăn race condition.

### 5.2. SQL có thể có dạng nào?

Provider có thể phát các lệnh logic tương đương:

```sql
-- Có thể phải SELECT các child để xử lý cascade:
SELECT id, order_id, product_id, quantity, unit_price
FROM order_lines
WHERE order_id = ?;

-- Xóa child trước khi xóa parent để thỏa mãn FK:
DELETE FROM order_lines WHERE id = ?;
DELETE FROM order_lines WHERE id = ?;

DELETE FROM purchase_orders WHERE id = ?;
```

Đây là **SQL minh họa**, không phải cam kết số câu SQL và thứ tự tuyệt đối trong mọi provider. Có thể có batching, truy vấn/kiểm tra version, tối ưu database hoặc xử lý khác.

Điều cần xác nhận là **hàng của OrderLine và PurchaseOrder được xóa theo chính sách**, còn `Customer`, `Product` và dữ liệu lịch sử không có quyền bị xóa sẽ được giữ lại.

### 5.3. remove() chưa đồng nghĩa đã commit

```java
em.remove(order);
```

đánh dấu entity ở trạng thái removed. SQL `DELETE` có thể chỉ được thực hiện khi flush hoặc commit. Nếu một FK, constraint hoặc optimistic locking không thỏa mãn, lỗi có thể xuất hiện muộn. Transaction phải rollback khi thất bại.

Một service không nên tuyên bố “đã xóa bền vững” chỉ vì `remove()` không ném exception ngay lập tức.

## 6. Vì sao không cascade REMOVE từ OrderLine đến Product?

Cùng xem quan hệ:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Product product;
```

`Product` đại diện bản ghi catalog; nó có thể được hàng nghìn OrderLine tham chiếu. Nếu vô tình viết:

```java
@ManyToOne(
    fetch = FetchType.LAZY,
    cascade = CascadeType.REMOVE
)
private Product product;
```

khi xóa một OrderLine, thao tác remove có thể lan đến `Product`. Hậu quả:

- Xóa nhầm sản phẩm còn dùng trong nhiều đơn hàng.
- Lỗi foreign key do những đơn hàng khác vẫn tham chiếu product.
- Dữ liệu báo cáo hoặc danh mục không còn nhất quán.
- Hiệu ứng lan truyền sâu nếu Product còn quan hệ được cấu hình cascade khác.

**Quy tắc:** Từ **child tới parent độc lập** hoặc **từ entity tham chiếu tới entity chia sẻ** không được mặc định lan truyền REMOVE.

Điều này vẫn đúng khi quan hệ là một-một: một trường `User.account` có vẻ chỉ trỏ một account, nhưng nếu `Account` có vòng đời bảo mật riêng, phải xác định rõ quyền sở hữu trước khi xóa theo.

## 7. Vì sao nguy hiểm khi cascade REMOVE trên @ManyToMany?

Giả sử học viên tham gia nhiều khóa học:

```java
@Entity
public class Student {
    @Id
    private Long id;

    @ManyToMany
    private Set<Course> courses = new HashSet<>();
}
```

`Course` là entity độc lập và có nhiều học viên. Khi xóa một Student, hệ thống thường chỉ muốn:

1. Xóa liên kết của Student khỏi join table.
2. Xóa hàng Student.
3. **Giữ toàn bộ Course** vì những học viên khác vẫn học.

Nếu dùng:

```java
@ManyToMany(cascade = CascadeType.REMOVE)
private Set<Course> courses;
```

ta đã yêu cầu lan truyền **xóa Course entity**, không chỉ các hàng trong join table. Đây là rủi ro mất dữ liệu. Hơn nữa, cascade remove trên association kiểu này không phải lựa chọn portable theo các giới hạn JPA.

### 7.1. Xóa liên kết không phải xóa entity đích

Giả sử join table:

```sql
CREATE TABLE student_courses (
    student_id BIGINT NOT NULL REFERENCES students(id),
    course_id BIGINT NOT NULL REFERENCES courses(id),
    PRIMARY KEY (student_id, course_id)
);
```

Xóa Student#10 có thể yêu cầu loại các hàng:

```sql
DELETE FROM student_courses
WHERE student_id = 10;
```

rồi xóa Student#10. **Không cần**:

```sql
DELETE FROM courses
WHERE id IN (...);
```

Vì thế, khi review mapping nhiều-nhiều, cần tách câu hỏi **“có xóa liên kết không?”** và **“có xóa entity Course không?”**. Cascade REMOVE trả lời câu hỏi thứ hai; nó không phải công cụ dọn join table chung.

Nếu liên kết có thuộc tính riêng như ngày đăng ký hoặc điểm, có thể dùng một `Enrollment` entity làm bảng nối có vòng đời của chính nó, rồi thiết kế quyền xóa theo nghiệp vụ.

## 8. Cascade REMOVE khác orphanRemoval

Đây là cặp khái niệm dễ bị dùng thay nhau.

**`CascadeType.REMOVE`** phát huy tác dụng khi thao tác `remove()` được áp dụng lên entity nguồn và cần lan truyền xuống entity đích.

**`orphanRemoval = true`** đánh dấu rằng entity con không còn được liên kết với parent sở hữu thì nó phải được xử lý như một orphan, thường bằng thao tác xóa khi flush. Annotation này dùng với `@OneToOne` và `@OneToMany` phù hợp.

### 8.1. Hai thao tác khác nhau

Giả sử:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.REMOVE
)
private List<OrderLine> lines;
```

Khi gọi:

```java
em.remove(order);
```

JPA lan truyền remove đến OrderLine. Nhưng nếu chỉ làm:

```java
order.getLines().remove(line);
```

thì **CascadeType.REMOVE đơn thuần không phải lệnh xóa entity line**. Nó không được kích hoạt chỉ bởi `Collection.remove()`.

Với:

```java
@OneToMany(
    mappedBy = "order",
    orphanRemoval = true
)
private List<OrderLine> lines;
```

khi một dòng đã được quản lý bị loại khỏi association sở hữu theo mapping, JPA có thể xóa dòng đó khi flush.

### 8.2. So sánh hành vi

| Hành động nghiệp vụ | `cascade = REMOVE` | `orphanRemoval = true` |
| --- | --- | --- |
| Xóa parent bằng `em.remove(parent)` | Lan truyền remove đến children. | Theo quy tắc JPA, remove parent cũng dẫn đến remove targets trong association được sở hữu theo orphan removal. |
| Gỡ một child khỏi collection nhưng giữ parent | Không tự động phát lệnh remove(child) chỉ vì CascadeType.REMOVE. | Gỡ child khỏi quan hệ sở hữu có thể lên lịch xóa child. |
| Thay child của `@OneToOne` | Không nhất thiết xóa child cũ. | Child cũ có thể được xử lý như orphan. |
| Chuyển child đã managed sang parent khác | Cascade REMOVE không tự xóa child chỉ vì đổi owner, nếu không có cơ chế khác. | **Không nên dựa vào việc tái gán orphan**: hành vi orphan rồi gán lại không được bảo đảm portable. |

Điểm quan trọng: **Không nhất thiết phải đặt cả `cascade = REMOVE` và `orphanRemoval = true` để đạt mục tiêu xóa con khi xóa cha.** Khi `orphanRemoval = true` có ý nghĩa sở hữu phù hợp, JPA cũng yêu cầu xử lý remove entity đích khi parent bị removed. Tuy vậy, nhiều dự án cấu hình cả hai để diễn đạt chủ ý; hãy hiểu chúng khác điều kiện kích hoạt.

### 8.3. Khi nào nên dùng cả hai?

Nếu `PurchaseOrder` sở hữu độc quyền các `OrderLine`, và nghiệp vụ cho phép:

- Xóa toàn bộ đơn nháp và tất cả dòng.
- Gỡ một dòng trong đơn nháp và xóa bản ghi dòng đó.

có thể dùng:

```java
@OneToMany(
    mappedBy = "order",
    cascade = {
        CascadeType.PERSIST,
        CascadeType.MERGE,
        CascadeType.REMOVE
    },
    orphanRemoval = true
)
private List<OrderLine> lines = new ArrayList<>();
```

Đây là một cấu hình phù hợp **khi OrderLine không được chuyển nguyên entity giữa các đơn và không có vòng đời độc lập**.

Nhưng khi có `orphanRemoval = true`, nếu ứng dụng chỉ muốn chuyển OrderLine từ đơn A sang đơn B, thao tác remove khỏi A có thể khiến nó bị xóa. Hãy chọn mô hình **di chuyển association** hoặc **xóa và tạo một entity mới** theo domain; không cố dùng reparent orphan như một thao tác JPA portable.

### 8.4. Helper để xóa một dòng nháp

Một phương thức trong `PurchaseOrder` có thể:

```java
public void removeLine(OrderLine line) {
    if (state != State.DRAFT) {
        throw new IllegalStateException("Order is not a draft");
    }
    if (lines.remove(line)) {
        line.assignOrder(null);
    }
}
```

Ví dụ này giả định quan hệ sử dụng `orphanRemoval = true` và cột `order_id` không cho `NULL`. JPA phải xử lý orphan theo quy tắc xóa; **không được gỡ association rồi flush như một phép UPDATE `order_id = NULL` nếu nghiệp vụ thật sự cần xóa child**. Với mapping không có orphanRemoval, thay `line.order = null` có thể vi phạm khóa ngoại.

Để một ví dụ dùng được, phương thức và mapping phải được bổ sung vào cùng phiên bản `PurchaseOrder` ở mục 4; không tạo hai entity trùng tên trong dự án.

## 9. Chuyển child giữa các parent: tín hiệu xem lại ranh giới sở hữu

Giả sử một hệ thống quản lý nhân sự:

```text
Department A ----> Employee#101
Department B ----> Employee#102
```

Một nhân viên có thể được chuyển từ Department A sang Department B **vẫn giữ nguyên ID**. Khi đó nhân viên có vòng đời riêng, không biến mất chỉ vì phòng ban cũ bị xóa.

Mapping thích hợp thường là:

```java
@OneToMany(mappedBy = "department")
private List<Employee> employees;
```

và:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Department department;
```

**Không mặc định CascadeType.REMOVE hoặc orphanRemoval** từ Department đến Employee.

Nếu hệ thống cần xóa phòng ban:

1. Kiểm tra còn nhân viên không.
2. Chuyển nhân viên sang phòng ban phù hợp, hoặc từ chối xóa.
3. Xóa phòng ban khi FK/ràng buộc đã được xử lý.

Đừng cấu hình cascade REMOVE chỉ để làm database “tự dọn nhân viên” trong khi domain thực sự cần giữ dữ liệu nhân sự.

### 9.1. Child có khóa chính phụ thuộc parent

Với một `OrderLine` có khóa chính ghép `(order_id, line_number)`, chuyển dòng sang order khác đồng nghĩa **thay đổi thành phần khóa chính**. JPA không bảo đảm sửa primary key của entity đã persist một cách portable.

Trong trường hợp đó, nghiệp vụ thường cần **xóa dòng ở đơn cũ và tạo dòng mới ở đơn đích**, hoặc thiết kế khóa thay thế độc lập nếu cần di chuyển giữ danh tính. Đây cũng là dấu hiệu rõ rằng dòng hàng mang vòng đời phụ thuộc đơn hàng.

## 10. @OneToOne: xóa entity phụ thuộc và tránh xóa nhầm

Một ví dụ có thể xóa theo là `UserAccount` với `PrivatePreferences`, nếu preferences thuộc riêng user và không có ý nghĩa độc lập:

```java
@Entity
public class UserAccount {
    @Id
    private Long id;

    @OneToOne(
        mappedBy = "user",
        cascade = CascadeType.REMOVE,
        orphanRemoval = true
    )
    private PrivatePreferences preferences;
}
```

```java
@Entity
public class PrivatePreferences {
    @Id
    private Long id;

    @OneToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "user_id", unique = true)
    private UserAccount user;
}
```

Đây là **một biến thể minh họa tối giản**, không thay thế các class domain của ứng dụng thật. Nếu bản ghi preferences chỉ tồn tại cùng user, cascade remove có thể hợp lý; có thể cần cấu hình thêm cascade PERSIST/MERGE tùy quy trình tạo/sửa.

Nhưng nếu quan hệ một-một là `Employee ↔ IdentityDocument` và tài liệu cần lưu theo quy định pháp lý, xóa Employee **không được mặc nhiên xóa tài liệu**. Multiplicity một-một không phải giấy phép xóa.

### 10.1. Một-một không tự động bảo đảm dữ liệu chỉ có một owner

`@OneToOne` diễn đạt multiplicity theo mapping, nhưng thiết kế schema cần unique constraint/FK phù hợp để bảo vệ quy tắc tại database. Ngoài ra, “unique hiện tại” không đủ chứng minh entity đích không có giá trị pháp lý hoặc lịch sử độc lập.

Luôn kiểm tra đồng thời **mô hình quan hệ**, **vòng đời** và **nghĩa vụ lưu trữ**.

## 11. Cascade REMOVE và ON DELETE CASCADE ở database

Một cách dọn các hàng con là để database thực hiện:

```sql
ALTER TABLE order_lines
DROP CONSTRAINT fk_lines_order;

ALTER TABLE order_lines
ADD CONSTRAINT fk_lines_order
FOREIGN KEY (order_id)
REFERENCES purchase_orders(id)
ON DELETE CASCADE;
```

Khi thực thi SQL xóa một hàng `purchase_orders`, database tự xóa các hàng `order_lines` tham chiếu.

Điều này **khác** với `CascadeType.REMOVE`:

| Tiêu chí | CascadeType.REMOVE (JPA) | ON DELETE CASCADE (database) |
| --- | --- | --- |
| Tầng xử lý | JPA provider và entity lifecycle | Database foreign-key constraint |
| Khi nào hoạt động? | Khi remove được áp dụng và cascade lan truyền | Khi SQL DELETE parent chạy |
| Cần tạo managed entity con không? | Provider thực hiện theo mapping; có thể cần load/resolve child | Database không cần Java entity |
| JPA lifecycle callbacks của con | Có thể tham gia theo quy tắc remove entity | Không tự kích hoạt `@PreRemove`/`@PostRemove` của JPA |
| Tác động tới persistence context | Provider có thể theo dõi các entity removed | Java managed entities có thể trở nên lỗi thời nếu DB tự xóa ngoài nhận biết |
| Có phải tự động tạo khi dùng CascadeType.REMOVE? | Không | Chỉ có khi schema có constraint được định nghĩa |
| Phụ thuộc JPA provider hay DB? | Theo JPA mapping và provider | Theo DBMS, DDL và khả năng khóa ngoại |

**Không suy luận rằng `cascade = REMOVE` tự tạo `ON DELETE CASCADE`.** Tương tự, có database cascade cũng không có nghĩa JPA tự gọi mọi callback/xử lý entity con.

### 11.1. Có nên dùng cả hai?

Chỉ sau khi đã hiểu cơ chế provider và schema. Một số provider có tính năng riêng giúp tận dụng database cascade để giảm số câu SQL, nhưng cần cân nhắc:

- Entity con đã được tải trong persistence context sẽ được xử lý ra sao?
- Second-level cache có thể giữ dữ liệu đã bị database xóa không?
- Lifecycle callback/audit nào phải chạy?
- Version của con có được kiểm tra theo ý định không?
- Có cần phát domain event cho từng con không?

Nếu hệ thống phụ thuộc vào các callback JPA trên từng child, **database cascade thuần túy không thay thế được những callback đó**. Nếu yêu cầu xóa hàng loạt với hiệu năng cao và không cần lifecycle per-child, database cascade có thể là một công cụ, nhưng phải được thiết kế rõ với cơ chế quản lý cache và transaction.

## 12. Vì sao foreign key là lớp bảo vệ quan trọng?

Một association `@ManyToOne` ở Java không thể thay thế hoàn toàn tính toàn vẹn của database. Khi xóa:

```java
em.remove(order);
```

nếu còn một `payment_records.order_id` tham chiếu đơn hàng và database không cho phép xóa, FK sẽ từ chối.

**Điều đó thường là thông điệp rằng ranh giới xóa của nghiệp vụ chưa được thỏa mãn**, không phải lý do để:

- Bỏ foreign key.
- Thêm `ON DELETE CASCADE` lên toàn bộ bảng.
- Bật `CascadeType.ALL` lên mọi quan hệ.
- Bắt exception rồi báo “đã xóa thành công”.

Thay vào đó, cần quyết định liệu:

1. Phải từ chối xóa vì dữ liệu lịch sử quan trọng.
2. Có chính sách archive/soft delete.
3. Có đối tượng phụ thuộc thực sự được phép xóa.
4. Có quy trình chuyển tham chiếu hoặc vô hiệu hóa dữ liệu.
5. Có ngoại lệ pháp lý/quy trình kế toán cần xử lý.

**Ràng buộc database là hàng rào cuối cùng**, nhưng phải kết hợp với quy tắc service để trả về lỗi nghiệp vụ có nghĩa, thay vì chỉ cho người dùng thấy lỗi SQL thô.

## 13. Xóa mềm (soft delete) khác xóa vật lý theo cascade

Trong những hệ thống cần audit hoặc retention, “xóa đơn hàng” có thể có nghĩa đổi trạng thái:

```java
order.cancel();
```

hoặc đặt một dấu thời gian:

```java
order.setDeletedAt(Instant.now());
```

Khi đó provider thường thực thi một câu `UPDATE`, **không phải `EntityManager.remove(order)`**. `CascadeType.REMOVE` **không tự được kích hoạt** chỉ bởi thao tác soft delete một field.

Ví dụ database:

```sql
ALTER TABLE purchase_orders
ADD COLUMN deleted_at TIMESTAMP NULL;
```

Nếu chỉ update `deleted_at`, hàng Order vẫn tồn tại. Các OrderLine có thể được giữ lại để phục vụ audit, báo cáo và phục hồi. Đừng mặc định rằng mọi soft delete phải xóa hoặc soft delete tất cả quan hệ.

### 13.1. Soft delete cần chính sách truy vấn và liên kết

Một hệ thống soft delete cần xác định:

- Query bình thường có lọc `deleted_at IS NULL` không?
- `find()` theo ID có hiển thị bản ghi soft-deleted không?
- Các liên kết từ Payment/Invoice tới order còn hợp lệ không?
- Có cho phép restore không, và điều gì xảy ra với những dòng đã bị xóa?
- Unique constraint cần áp dụng cho cả hàng soft-deleted hay chỉ hàng active?
- Dữ liệu nào phải được purge vật lý sau thời hạn retention?

Một số JPA provider có hỗ trợ soft-delete riêng, nhưng đó là tính năng khác với **`CascadeType.REMOVE` tiêu chuẩn**. Không nên giả định JPA tự soft-delete con khi parent được gắn dấu xóa.

### 13.2. Chính sách domain quan trọng hơn tiện ích cascade

Đơn hàng đã xác nhận, hóa đơn đã phát hành hoặc giao dịch thanh toán có thể phải tồn tại để đối soát. Trong tình huống này, thay vì chọn:

```java
cascade = CascadeType.ALL
```

trên mọi quan hệ, nên thiết kế trạng thái nghiệp vụ rõ ràng và chỉ cho phép xóa vật lý những dữ liệu phụ trợ thật sự không cần giữ.

## 14. Bulk delete không giống cascading remove từng entity

JPA hỗ trợ JPQL bulk delete:

```java
int affected = em.createQuery(
        "DELETE FROM OrderLine l WHERE l.order.id = :orderId"
    )
    .setParameter("orderId", orderId)
    .executeUpdate();
```

Bulk JPQL delete thường **thực thi trực tiếp trên database**, bỏ qua nhiều quy tắc lifecycle của thao tác `EntityManager.remove()` trên từng managed entity:

- Không tự gọi `@PreRemove`/`@PostRemove` cho từng child như entity remove thông thường.
- Không tự áp dụng cascade JPA trên các association từ từng entity bị xóa.
- Không tự đồng bộ các managed entities đã được tải trong persistence context.
- Không mặc nhiên kiểm tra `@Version` từng entity theo mô hình remove managed instance.

Vì vậy, nếu cần lifecycle callback và ranh giới cascade chính xác, **không thay thế một cách cơ học `em.remove(order)` bằng bulk DELETE**.

### 14.1. Thứ tự bulk delete với foreign key

Nếu cần xóa dữ liệu theo thứ tự:

```text
1. DELETE order_lines WHERE order_id = ?
2. DELETE purchase_orders WHERE id = ?
```

có thể thực hiện bằng hai câu bulk SQL/JPQL trong cùng transaction **khi nghiệp vụ và ràng buộc cho phép**. Nhưng cần nhận thức rằng:

- Bulk delete có thể bỏ qua orphanRemoval/callbacks.
- Managed OrderLine/Order đã tải có thể trở nên stale.
- Nếu còn PaymentRecord tham chiếu Order, xóa Order vẫn có thể bị FK từ chối.
- Tính nhất quán cache, locking và audit cần xử lý rõ.

Không dùng bulk delete để “xóa sạch mọi thứ” chỉ vì có số lượng child lớn. Cần quyết định trước **đối tượng nào thực sự thuộc ranh giới được phép xóa**.

### 14.2. Bulk delete khi không tồn tại

`executeUpdate()` trả số lượng entity bị ảnh hưởng theo hợp đồng bulk operation, không phải danh sách callback. Với điều kiện đơn giản theo khóa chính, kết quả 0 thường phản ánh không có dữ liệu tương ứng được xóa. Đừng coi tất cả giá trị 0 là thành công nếu hợp đồng nghiệp vụ cần biết ID tồn tại hoặc trạng thái bị đổi đồng thời.

## 15. Lifecycle callbacks, audit và sự kiện xóa

Một entity có thể khai báo:

```java
@PreRemove
void beforeRemove() {
    // Logic callback thuộc vòng đời JPA.
}

@PostRemove
void afterRemove() {
    // Callback sau thao tác remove theo JPA.
}
```

Nếu CascadeType.REMOVE lan truyền remove đến các entity con, các callback lifecycle của con có thể tham gia theo quy tắc JPA. Nhưng có những giới hạn quan trọng:

- Callback không phải bằng chứng transaction đã commit thành công.
- Callback không phải nơi an toàn để gửi email hoặc message bên ngoài không thể rollback.
- Bulk JPQL/native SQL và database `ON DELETE CASCADE` không tự tạo đầy đủ callback JPA cho từng child.
- Một hành động xóa lớn có thể kích hoạt nhiều callback; chúng cần được thiết kế có kiểm soát và tuân thủ giới hạn JPA.

Nếu nghiệp vụ cần ghi lại mỗi dòng đã xóa, một số lựa chọn:

1. Ghi audit record trong cùng transaction thông qua lớp service/hệ thống audit phù hợp.
2. Dùng cơ chế auditing của provider theo hiểu biết rõ về trường hợp delete.
3. Dùng database audit/trigger với giới hạn và chính sách riêng.
4. Dùng **transactional outbox** nếu phải phát sự kiện sau commit tới hệ thống ngoài.

**Không dùng cascade REMOVE thay thế thiết kế audit.** Mục đích của cascade là lan truyền thao tác lifecycle, không quy định dữ liệu lịch sử nào cần giữ hoặc sự kiện nào phải phát.

## 16. @Version và xung đột khi xóa

Ví dụ `PurchaseOrder` có:

```java
@Version
private Long version;
```

Nếu hai transaction cùng thao tác trên một order:

```text
Transaction A                    Transaction B
-------------                    -------------
Đọc Order#100 version=2
                                 Đọc Order#100 version=2
                                 Xác nhận/đổi trạng thái order
                                 Commit version=3
A cố xóa Order#100 version=2
Có thể phát hiện optimistic conflict
```

Provider có thể dùng version trong câu SQL delete hoặc kiểm tra tương ứng và ném `OptimisticLockException` khi trạng thái stale.

### 16.1. @Version của root không tự khóa mọi child

Version trên PurchaseOrder giúp phát hiện xung đột **trên order**, nhưng không tự bảo vệ mọi nghiệp vụ liên quan tới từng OrderLine, PaymentRecord hoặc các writer ngoài JPA trong mọi tình huống.

Một giao dịch khác có thể:

- Thêm PaymentRecord ngay sau khi ta kiểm tra `COUNT = 0`.
- Thay đổi hoặc xóa một child qua SQL trực tiếp.
- Tạo tham chiếu mới đến order trong khi ta định xóa.

Các ràng buộc FK có thể khiến delete thất bại, và các isolation/locking strategy có thể cần bổ sung. **Không nên giả định `@Version` trên cha là đủ để làm nguyên tử mọi điều kiện liên quan tới toàn bộ graph.**

### 16.2. Xử lý lỗi đúng transaction

Nếu flush hoặc commit phát sinh `OptimisticLockException`, `PersistenceException` hay lỗi FK:

1. Rollback transaction còn hoạt động nếu runtime yêu cầu.
2. Kết thúc/đóng EntityManager của đơn vị công việc lỗi khi phù hợp.
3. Phân loại kết quả: không tìm thấy, dữ liệu đã thay đổi, có tham chiếu phụ thuộc, lỗi hệ thống.
4. Chỉ retry bằng transaction mới khi thao tác idempotent/an toàn và chính sách cho phép.

Không bắt mọi exception rồi trả “đã xóa” hoặc tự động thử lại vô hạn. Điều đó có thể che một quy tắc bảo vệ dữ liệu đã hoạt động đúng.

## 17. Xóa số lượng lớn và chi phí hiệu năng

Cascade REMOVE có thể tiện và đúng với một aggregate nhỏ; nhưng với parent có **hàng chục nghìn children**, thao tác xóa có thể tốn:

- Truy vấn nạp hoặc xác định các child phải xóa.
- Nhiều lệnh `DELETE`.
- Lock và thời gian transaction kéo dài.
- Memory cho entity được materialize/cascade.
- Callback, version check và xử lý cache theo từng entity.

`FetchType.LAZY` không phải công tắc ngăn provider đọc dữ liệu khi phải thực hiện cascade REMOVE. Nếu nghiệp vụ xóa một aggregate lớn, cần **đo SQL và giải thích kế hoạch thực thi** trước khi chọn chiến lược.

Những phương án có thể cân nhắc:

| Lựa chọn | Điểm mạnh | Đánh đổi |
| --- | --- | --- |
| JPA `remove(parent)` + cascade REMOVE | Tương thích vòng đời entity/callback/cascade theo mapping. | Có thể tốn nhiều SELECT/DELETE khi graph lớn. |
| Database `ON DELETE CASCADE` | DB có thể xử lý xóa phụ thuộc hiệu quả theo constraint. | Không chạy callback JPA trên từng child, có thể gây stale cache/context. |
| Bulk JPQL/native delete theo thứ tự | Chủ động xóa nhiều hàng qua ít câu lệnh hơn. | Bỏ qua lifecycle per-entity, cần quản lý FK/context/audit/version. |
| Soft delete/archive rồi purge sau | Giảm tác động tức thời và giữ lịch sử theo chính sách. | Phức tạp hóa truy vấn, retention, index, khôi phục. |

Không có một lựa chọn “luôn tối ưu”. Với aggregate 5-20 children, cascade JPA thường rõ và đủ. Với hàng triệu record lịch sử, delete trực tiếp cùng aggregate trong request người dùng có thể không phù hợp; quy trình archive/purge riêng có thể tốt hơn. Số lượng cụ thể phải dựa vào workload, không có ngưỡng chuẩn bắt buộc trong JPA.

## 18. Vòng đời children trong cùng persistence context

Một hệ quả dễ bị bỏ qua khi xóa parent:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, 100L);
List<OrderLine> lines = order.getLines();

em.remove(order);
```

Sau khi yêu cầu remove:

- Parent được đánh dấu removed.
- Các OrderLine được lan truyền remove theo mapping.
- Các object Java `order` và `lines` vẫn có thể được các biến hiện tại tham chiếu trong bộ nhớ.
- Một lần đọc getter của object cũ không chứng minh hàng database còn tồn tại.
- SQL DELETE có thể chạy tại flush/commit.

Không nên tiếp tục sử dụng graph đã removed như dữ liệu đơn hàng còn hoạt động. Nếu cần trả API response, có thể **trích những thông tin cần thiết trước khi xóa** thành DTO, sau đó commit và trả response phù hợp.

### 18.1. Không tái sử dụng entity removed như entity mới

Nếu đã gọi `remove(child)` hoặc child bị cascade REMOVE, không nên chỉ thêm lại cùng instance vào collection khác rồi kỳ vọng JPA tự phục hồi identity/row.

Một removed entity không tương đương một transient entity vừa `new`. Tùy thao tác, lifecycle JPA có thể có những quy tắc phục hồi riêng, nhưng **không nên thiết kế nghiệp vụ xóa/đổi chủ dựa trên việc tái sử dụng object đang removed**.

### 18.2. Rollback không phục hồi object graph sạch trong bộ nhớ

Nếu transaction đã flush DELETE rồi rollback, database có thể khôi phục hàng, nhưng các Java object đã bị sửa/removed không nên được coi là tự trở lại trạng thái managed sạch.

Với EntityManager application-managed, cách thực hành an toàn là kết thúc persistence context lỗi rồi tải lại dữ liệu trong transaction mới khi cần.

## 19. Một ranh giới xóa có thể phụ thuộc trạng thái nghiệp vụ

Cùng một quan hệ `PurchaseOrder → OrderLine`, có thể tồn tại hai chính sách:

- **Order DRAFT:** có thể xóa vật lý, cùng các OrderLine.
- **Order CONFIRMED:** không xóa vật lý vì cần audit, thanh toán, hàng đã xuất hoặc hóa đơn.
- **Order CANCELLED:** giữ bản ghi nhưng đổi trạng thái; sau thời hạn retention mới purge theo chính sách.

`CascadeType.REMOVE` không biết những quy tắc trạng thái này. Nó chỉ có nghĩa **nếu** JPA được yêu cầu xóa order và cascade áp dụng, thì thao tác remove lan tới dòng hàng.

Vì vậy, policy phải được kiểm tra trước:

```java
if (order.getState() != PurchaseOrder.State.DRAFT) {
    throw new IllegalStateException(
        "Confirmed or cancelled orders cannot be hard deleted"
    );
}

em.remove(order);
```

**Không đặt toàn bộ quyết định xóa vào annotation.** Annotation mô tả cơ chế propagation; service/domain quyết định khi nào được phép gọi remove.

## 20. Thiết kế trong Spring Data JPA

Trong Spring Boot, có thể dùng một service transactional:

```java
package com.example.shop;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderDeletionApplicationService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void deleteDraft(Long orderId) {
        PurchaseOrder order =
            entityManager.find(PurchaseOrder.class, orderId);

        if (order == null) {
            throw new IllegalArgumentException("Order not found");
        }

        if (order.getState() != PurchaseOrder.State.DRAFT) {
            throw new IllegalStateException("Cannot delete this order");
        }

        Long payments = entityManager.createQuery(
                "SELECT COUNT(p) FROM PaymentRecord p " +
                "WHERE p.order.id = :id",
                Long.class
            )
            .setParameter("id", orderId)
            .getSingleResult();

        if (payments > 0) {
            throw new IllegalStateException("Payment history exists");
        }

        entityManager.remove(order);
    }
}
```

Giả định entity và transaction manager đã được cấu hình trong Spring. Vì `order` là managed, `entityManager.remove(order)` là lựa chọn trực tiếp. `@Transactional` yêu cầu Spring quản lý commit/rollback khi lời gọi đi qua transaction interceptor; **không gọi thủ công `entityManager.getTransaction().begin()`** trên EntityManager do Spring/container quản lý.

Trong Spring Data JPA, `repository.delete(order)` thường cuối cùng cũng sử dụng cơ chế xóa entity tương ứng; nhưng không nên đồng nhất nó với mọi biến thể `deleteAllInBatch` hay custom bulk delete. Các bulk method có thể bỏ qua cascade/lifecycle per-entity; phải chọn theo mục đích thực tế và phiên bản thư viện.

### 20.1. Phân loại kết quả API

Một REST endpoint:

```text
DELETE /api/orders/100
```

có thể trả:

| Kết quả nghiệp vụ | HTTP thường cân nhắc |
| --- | --- |
| Xóa đơn nháp thành công | `204 No Content` |
| ID không tồn tại theo quyền truy cập/tenant | `404 Not Found` |
| Đơn đã xác nhận hoặc có payment, không được hard-delete | `409 Conflict` |
| Caller không có quyền xóa | `403 Forbidden` hoặc chính sách che sự tồn tại |
| ETag/version không khớp theo hợp đồng conditional request | `412 Precondition Failed` |
| Lỗi DB/transaction ngoài dự kiến | Không trả 204; xử lý lỗi hệ thống phù hợp |

Chọn mã HTTP theo hợp đồng API, không phải một-một theo tên JPA exception. Đặc biệt **không trả thành công trước khi transaction được cam kết**; lỗi FK hay optimistic locking có thể xuất hiện tại flush/commit.

## 21. Hướng dẫn đánh giá ranh giới xóa trước khi mapping

Trước khi thêm `CascadeType.REMOVE`, trả lời các câu hỏi:

1. **Entity đích có thể tồn tại khi entity nguồn không còn không?** Nếu có, không nên tự động xóa theo.
2. **Entity đích có được nhiều nguồn tham chiếu hoặc sử dụng chung không?** Nếu có, tránh xóa nó qua một source đơn lẻ.
3. **Entity đích có cần giữ ID, lịch sử, audit hoặc giá trị pháp lý không?** Nếu có, cân nhắc giữ/archiving.
4. **Xóa source có thực sự có nghĩa xóa target trong domain?** Nếu chỉ gỡ liên kết, xử lý association thay vì remove target.
5. **Có cần gỡ riêng một target khi source vẫn tồn tại không?** Nếu có và target phụ thuộc độc quyền, cân nhắc `orphanRemoval`.
6. **Target có được chuyển từ owner này sang owner khác không?** Nếu có, không nên mặc định orphanRemoval và cần xét quyền xóa theo từng tình huống.
7. **Các target có thể rất nhiều hoặc rất sâu không?** Nếu có, xem chi phí cascade và chiến lược xóa.
8. **Có quan hệ gián tiếp đến entity chia sẻ không?** Đảm bảo cascade không vượt ranh giới ở một cấp khác.
9. **Có khóa ngoại giữ dữ liệu lịch sử không?** Hãy coi đó là ràng buộc domain và vận hành cần giải quyết, không tự động gỡ constraint.
10. **Ai có quyền yêu cầu xóa, và trạng thái nào được phép xóa?** Annotation JPA không thay quyền kiểm tra authorization và business state.

Ví dụ quyết định:

| Quan hệ | Khuyến nghị suy luận | Vì sao |
| --- | --- | --- |
| `Cart → CartLine` | Thường cân nhắc REMOVE/orphanRemoval | CartLine chỉ mang ý nghĩa trong cart. |
| `PurchaseOrder → OrderLine` | Có thể REMOVE với order được phép xóa | Dòng thuộc đơn, nhưng việc xóa cả đơn phải kiểm tra trạng thái và retention. |
| `PurchaseOrder → Customer` | Không cascade REMOVE | Customer độc lập, có thể có nhiều orders. |
| `OrderLine → Product` | Không cascade REMOVE | Product dùng chung trong catalog. |
| `Student ↔ Course` | Không cascade REMOVE | Hai entity độc lập; chỉ xóa liên kết khi cần. |
| `User → PrivatePreferences` | Có thể REMOVE nếu sở hữu riêng | Preferences phụ thuộc vòng đời User trong domain tương ứng. |
| `Department → Employee` | Thường không cascade REMOVE | Nhân viên có thể chuyển phòng ban và cần giữ danh tính. |
| `Invoice → PaymentTransaction` | Thường không tự xóa | Thông tin tài chính có vòng đời và yêu cầu lưu trữ riêng. |
| `Project → Task` | Tùy domain | Task có thể là thành phần aggregate hoặc entity độc lập/được chuyển dự án. |
| `BlogPost → Comment` | Tùy chính sách | Bình luận có thể cần kiểm duyệt/audit độc lập, không phải lúc nào cũng xóa theo. |

Các dòng trên là ví dụ phân tích, không phải luật cứng. Một mô hình khác có thể chọn chính sách khác, miễn được xác định **có chủ đích**.

## 22. Những hiểu lầm cần tránh

### “Owning side của JPA phải đặt cascade REMOVE”

Sai. Owning side quyết định mapping khóa ngoại; domain ownership quyết định quyền xóa entity khác. `OrderLine.product` có thể là owning side của FK nhưng **không được xóa Product**.

### “@OneToMany luôn nên cascade ALL”

Sai. Một-to-nhiều chỉ là cardinality. Con có thể sống độc lập hoặc cần lưu lịch sử. `ALL` bao gồm REMOVE, REFRESH, DETACH; chỉ bật khi mọi thao tác đó phù hợp.

### “Cascade REMOVE nghĩa là remove khỏi collection sẽ xóa con”

Sai. Cascade REMOVE được lan truyền từ **thao tác remove trên entity nguồn**. Gỡ child khỏi quan hệ mà giữ parent là bài toán khác; có thể cần `orphanRemoval = true`.

### “orphanRemoval luôn là lựa chọn tốt cho mọi OneToMany”

Sai. Nếu con được phép đổi chủ và giữ nguyên ID, orphan removal có thể đánh dấu xóa khi rời parent cũ. Không giả định thao tác reparent orphan được provider bảo đảm.

### “FetchType.LAZY sẽ ngăn xóa con vì chưa tải collection”

Sai. LAZY điều chỉnh cách tải, không hủy yêu cầu cascade. Provider vẫn xử lý những child thuộc phạm vi xóa.

### “Xóa Order sẽ tự xóa Product vì OrderLine tham chiếu Product”

Không, nếu mapping không có cascade REMOVE từ OrderLine tới Product. Chỉ tham chiếu qua nhiều cấp không tạo quyền xóa; đó là điều cần bảo vệ.

### “Xóa một Student nên xóa luôn Course để dọn join table”

Sai. Xóa liên kết trong join table khác xóa entity Course; nhiều-to-nhiều không phải nơi mặc định cascade REMOVE.

### “ON DELETE CASCADE và CascadeType.REMOVE là một”

Sai. Database cascade hoạt động ở tầng SQL, không tự chạy JPA callbacks cho từng con và có thể khiến persistence context lỗi thời.

### “Có CascadeType.REMOVE thì không cần foreign key”

Sai. FK bảo vệ dữ liệu khi có writer ngoài JPA, lỗi ứng dụng hoặc điều kiện cạnh tranh. Cascade JPA không thay thế constraint database.

### “Một entity nằm trong collection tức là nó được phép xóa theo”

Sai. Collection có thể biểu diễn dữ liệu được chia sẻ, danh sách tham chiếu, bảng liên kết hoặc một tập đối tượng độc lập. Phải xem lifecycle, không nhìn getter.

### “Bulk DELETE và em.remove(parent) luôn có cùng tác dụng”

Sai. Bulk operation bỏ qua một số quy tắc lifecycle/cascade/callback và không tự làm mới managed state. Chỉ thay thế nếu đã thiết kế các hiệu ứng khác.

### “Xóa parent đã hoàn tất ngay khi remove() trả về”

Sai. Lỗi FK, lock hoặc constraint có thể xảy ra khi flush/commit. Cần transaction boundary và rollback khi thất bại.

### “Soft delete field sẽ kích hoạt CascadeType.REMOVE”

Sai. Update một cột `deletedAt` không phải `EntityManager.remove()`. Quy tắc soft delete cho child phải được định nghĩa riêng.

### “@Version ở parent tự khóa toàn bộ graph”

Không hẳn. Cạnh tranh trên những entity khác, FK mới tạo và writers ngoài JPA cần chiến lược riêng. Version hỗ trợ optimistic locking theo trạng thái entity/mapping, không tạo transaction phân tán cho cả graph.

## 23. Bài tập thực hành có hướng dẫn

### Bài tập 1 — Giỏ hàng và sản phẩm

Giả sử:

```text
Cart#10
  +-- CartLine#1 -> Product#100
  +-- CartLine#2 -> Product#101
```

**Câu hỏi:** Xóa Cart#10 nên cascade REMOVE đến đâu?

**Giải thích:** Có thể cascade REMOVE tới CartLine#1 và CartLine#2 nếu dòng giỏ hàng thuộc riêng giỏ. **Không** cascade REMOVE từ CartLine sang Product vì Product thuộc catalog và có vòng đời độc lập.

### Bài tập 2 — Student và Course

```java
@ManyToMany(cascade = CascadeType.ALL)
private Set<Course> courses;
```

**Câu hỏi:** Khi xóa Student, cấu hình này có nguy cơ gì?

**Giải thích:** `ALL` bao gồm REMOVE. Xóa Student có thể lan truyền xóa Course, gây mất dữ liệu dùng chung hoặc lỗi FK. Nên bỏ REMOVE/ALL và quản lý liên kết, không xóa Course.

### Bài tập 3 — Gỡ dòng đơn nhưng không xóa đơn

```java
order.getLines().remove(line);
```

**Câu hỏi:** Chỉ có `cascade = REMOVE` thì lệnh trên chắc chắn xóa OrderLine không?

**Giải thích:** Không. Cascade REMOVE không được kích hoạt chỉ bởi việc sửa Java collection. Nếu muốn child bị xóa khi rời owner, cần orphanRemoval và mapping/đồng bộ hai phía phù hợp, hoặc gọi `em.remove(line)` rõ ràng khi domain cho phép.

### Bài tập 4 — Chuyển Employee giữa hai Department

Department A quản lý Employee#101. Employee được chuyển sang Department B.

**Câu hỏi:** Có nên dùng `orphanRemoval = true` trên Department.employees?

**Giải thích:** Thông thường không. Employee được chuyển chứ không bị kết thúc vòng đời. Việc gỡ khỏi A không được có nghĩa tự xóa Employee.

### Bài tập 5 — Xóa Order đã có PaymentRecord

Order#100 là DRAFT nhưng đã có payment record. `PaymentRecord.order` có FK tới Order và không có database cascade.

**Câu hỏi:** Khi `em.remove(order)`, điều gì có thể xảy ra?

**Giải thích:** JPA có thể xóa các OrderLine theo cascade, nhưng delete Order có thể bị FK từ PaymentRecord từ chối tại flush/commit. Transaction phải rollback; ứng dụng nên kiểm tra business rule và giữ payment history. Không bật cascade REMOVE qua PaymentRecord để né constraint.

### Bài tập 6 — Xóa parent với 50.000 children

Một aggregate chứa 50.000 child và có callback audit từng child.

**Câu hỏi:** Có nên thay ngay bằng database ON DELETE CASCADE để nhanh hơn?

**Giải thích:** Không thể thay thế máy móc. Database cascade không tự chạy callback JPA của từng child. Cần quyết định yêu cầu audit và cách thực thi tương ứng, thử nghiệm kế hoạch SQL/khóa, cân nhắc purge nền hoặc một cơ chế audit database/outbox phù hợp.

### Bài tập 7 — Soft delete đơn hàng

Service làm:

```java
order.cancel();
```

và commit, không gọi remove.

**Câu hỏi:** CascadeType.REMOVE có tự xóa lines không?

**Giải thích:** Không. Đây là cập nhật trạng thái. Đơn và dòng thường nên giữ nguyên để phản ánh lịch sử; nếu muốn xử lý dữ liệu phụ thuộc theo trạng thái, cần logic nghiệp vụ riêng.

### Bài tập 8 — Cascade ở nhiều cấp

```text
Order -> OrderLine -> Product -> Supplier
```

Đoạn mapping Order→OrderLine có REMOVE, còn Line→Product và Product→Supplier không có REMOVE.

**Câu hỏi:** Xóa Order có yêu cầu xóa Product hoặc Supplier không?

**Giải thích:** Không. Cascade đi theo những association có cấu hình lan truyền phù hợp; ranh giới dừng ở OrderLine, giữ Product/Supplier độc lập.

### Bài tập 9 — Entity đã detached

Ứng dụng nhận một `PurchaseOrder` detached từ một request cũ và muốn xóa.

**Câu hỏi:** Có nên gọi `em.remove(detachedOrder)` không?

**Giải thích:** Không. `remove()` yêu cầu managed entity. Cách dễ kiểm soát là tải lại Order theo ID trong transaction, kiểm tra trạng thái/quyền/dữ liệu liên quan rồi mới remove.

### Bài tập 10 — Hai giao dịch cạnh tranh

A kiểm tra Order#100 chưa có Payment. B tạo PaymentRecord và commit ngay trước khi A flush delete.

**Câu hỏi:** Kiểm tra `COUNT = 0` của A có đủ không?

**Giải thích:** Không. Có race condition. FK có thể chặn việc xóa và transaction A phải rollback; để bảo đảm đúng chính sách có thể cần locking/isolation/điều phối quy trình tạo payment và xóa order.

## 24. Câu hỏi tự kiểm tra

**1. Điều kiện chính để bật `CascadeType.REMOVE` là gì?**

Entity nguồn thực sự có quyền kết thúc vòng đời entity đích theo domain, và cách dùng phù hợp với quan hệ/mapping.

**2. Một `@OneToMany` có tự chứng minh rằng cha sở hữu vòng đời con không?**

Không. Cardinality của quan hệ không tự quy định quyền xóa. Cần xét dữ liệu có được chia sẻ, di chuyển hoặc lưu lịch sử không.

**3. Owning side JPA khác domain ownership như thế nào?**

Owning side điều khiển ánh xạ association/khóa ngoại. Domain ownership quyết định lifecycle và quyền xóa dữ liệu.

**4. `CascadeType.ALL` có những loại cascade nào?**

`PERSIST`, `MERGE`, `REMOVE`, `REFRESH`, `DETACH`.

**5. Xóa một Product có nên làm theo xóa OrderLine chỉ vì OrderLine.product là `@ManyToOne` không?**

Không. Product thường có vòng đời độc lập và được tham chiếu ở nhiều nơi.

**6. Vì sao nên tránh REMOVE trên `@ManyToMany`?**

Vì xóa một entity nguồn không có nghĩa entity phía còn lại, vốn có thể được chia sẻ, cũng phải bị xóa; cách dùng này còn không phải lựa chọn portable an toàn.

**7. `CascadeType.REMOVE` và `orphanRemoval = true` khác nhau ở trigger nào?**

REMOVE lan truyền khi entity nguồn bị remove; orphanRemoval xử lý con bị loại khỏi quan hệ sở hữu.

**8. Database `ON DELETE CASCADE` có thực thi `@PreRemove` JPA của mọi child không?**

Không. DB cascade hoạt động ở SQL, không tự gọi callback JPA của entity con.

**9. Xóa order đã có payment history nên làm gì?**

Thường cần từ chối hard delete, archive hoặc thay đổi trạng thái theo chính sách. Không tự xóa payment chỉ để vượt FK.

**10. `FetchType.LAZY` có ngăn cascade REMOVE không?**

Không. Fetching và cascading là hai cơ chế độc lập. Provider vẫn phải xử lý thao tác remove theo mapping.

**11. Bulk JPQL DELETE có tương đương gọi remove trên từng managed entity không?**

Không. Bulk delete có giới hạn với cascade, callbacks, version và persistence context.

**12. Tại sao không trả thành công ngay sau `em.remove()`?**

Vì thao tác xóa có thể chỉ thực thi SQL ở flush/commit và thất bại do FK, constraint hoặc concurrency.

## 25. Ghi nhớ cốt lõi

**`CascadeType.REMOVE` là một công cụ lan truyền thao tác xóa, không phải chỉ thị “xóa tất cả thứ gì có liên kết”.** Khi áp dụng trong JPA, phải căn cứ **ranh giới sở hữu vòng đời của dữ liệu**: entity con thực sự phụ thuộc chủ và được phép bị xóa cùng chủ; entity tham chiếu/chia sẻ như Customer, Product, Course hoặc PaymentTransaction không được xóa chỉ vì xuất hiện trong object graph.

Trong quan hệ **`@OneToMany` hoặc `@OneToOne` có sở hữu độc quyền**, REMOVE có thể phù hợp. Với quan hệ **`@ManyToOne` và `@ManyToMany` chia sẻ**, không nên cascade REMOVE theo thói quen. **Owning side của JPA** chỉ nói về quản lý FK, khác với **lifecycle ownership** của nghiệp vụ.

Đồng thời cần phân biệt **CascadeType.REMOVE** khi xóa entity nguồn, **orphanRemoval** khi gỡ một child khỏi quan hệ sở hữu, **ON DELETE CASCADE** của database, và **soft delete** cập nhật trạng thái nghiệp vụ. Cả transaction, foreign key, optimistic locking, audit và yêu cầu giữ lịch sử đều có thể giới hạn quyền xóa, dù mapping JPA về mặt cú pháp là hợp lệ.

Một thiết kế an toàn bắt đầu bằng câu hỏi: **Nếu entity A biến mất, entity B có thật sự phải biến mất vĩnh viễn theo không?** Chỉ sau khi xác định rõ đáp án và ranh giới sở hữu, hãy đặt `CascadeType.REMOVE` trên association thích hợp, kiểm tra tác động xuyên graph và điều phối thao tác xóa trong transaction đúng.

# Thực thể liên kết khi quan hệ có thuộc tính hoặc quy tắc riêng trong Hibernate ORM

## 1. Bài toán: quan hệ nhiều-nhiều không chỉ là hai khóa ngoại

Giả sử một hệ thống bán hàng có hai thực thể độc lập:

- **PurchaseOrder**: đơn hàng, có mã đơn, khách đặt, thời gian và trạng thái.
- **Product**: sản phẩm, có SKU, tên, giá hiện tại và tồn kho.

Một đơn chứa nhiều sản phẩm; một sản phẩm xuất hiện trong nhiều đơn. Nếu nhìn **chỉ** vào lực lượng quan hệ, ta có quan hệ nhiều-nhiều (many-to-many):

~~~mermaid
erDiagram
    PURCHASE_ORDERS }o--o{ PRODUCTS : contains
~~~

Ban đầu, một bảng nối đơn giản có thể trông như sau:

~~~sql
CREATE TABLE order_products (
    order_id   BIGINT NOT NULL REFERENCES purchase_orders(id),
    product_id BIGINT NOT NULL REFERENCES products(id),
    PRIMARY KEY (order_id, product_id)
);
~~~

Nhưng nghiệp vụ đặt hàng thực tế cần trả lời những câu hỏi khác:

- Đặt **bao nhiêu** sản phẩm?
- **Đơn giá tại thời điểm mua** là bao nhiêu, kể cả sau khi bảng giá sản phẩm thay đổi?
- Mỗi dòng có giảm giá, thuế, trạng thái hoàn trả, ghi chú riêng hay không?
- Có được thêm một sản phẩm hai lần vào cùng đơn không?
- Khi xóa đơn, dòng hàng có bị xóa không? Khi xóa dòng hàng, có được xóa sản phẩm không?
- Có được sửa số lượng sau khi đơn được xác nhận không?

Các dữ liệu **quantity**, **unitPrice** và những quy tắc trên thuộc **mối quan hệ giữa đơn và sản phẩm**, không thuộc riêng bảng sản phẩm hoặc bảng đơn.

Đó là lúc ta chuyển từ quan hệ many-to-many trực tiếp sang **thực thể liên kết** (*association entity*, còn gọi là *join entity*): **OrderItem**, hay dòng hàng.

~~~mermaid
erDiagram
    PURCHASE_ORDERS ||--|{ ORDER_ITEMS : contains
    PRODUCTS ||--o{ ORDER_ITEMS : appears_in
    PURCHASE_ORDERS {
        bigint id PK
        bigint customer_id FK
        varchar status
        timestamp placed_at
    }
    ORDER_ITEMS {
        bigint id PK
        bigint order_id FK
        bigint product_id FK
        integer quantity
        decimal unit_price
    }
    PRODUCTS {
        bigint id PK
        varchar sku
        decimal current_price
    }
~~~

Thực thể liên kết không phải một mẹo để né khó khăn của annotation. Nó là quyết định mô hình hóa: **bản thân việc một sản phẩm thuộc một đơn hàng đã trở thành một đối tượng có dữ liệu và quy tắc riêng**.

### Mục tiêu

Sau bài học, bạn có thể:

1. Nhận biết khi nào một bảng nối nên trở thành entity độc lập.
2. Chuyển một quan hệ many-to-many thành hai quan hệ many-to-one và ánh xạ one-to-many tương ứng bằng Jakarta Persistence/Hibernate.
3. Chọn khóa chính tự sinh hoặc khóa ghép cho thực thể liên kết, giữ ràng buộc duy nhất ở database.
4. Thiết kế constructor, helper method, cascade và orphan removal đúng vòng đời.
5. Lưu giá trị nghiệp vụ theo thời điểm phát sinh, thay đổi association an toàn trong transaction.
6. Truy vấn, phân trang, kiểm soát lazy loading và xử lý cập nhật đồng thời.
7. Kiểm thử những quy tắc riêng của quan hệ bằng database thật.

Ví dụ sử dụng Java 17+, Jakarta Persistence API (package **jakarta.persistence**) với Hibernate ORM 6.x và Spring Data JPA. Phần lớn khái niệm cũng áp dụng với Hibernate trực tiếp; hành vi SQL cụ thể tùy phiên bản, dialect và mapping.

## 2. Phân biệt ba cách biểu diễn một liên kết

| Cách ánh xạ | Dữ liệu của quan hệ | Khi thích hợp | Điểm cần lưu ý |
|---|---|---|---|
| **@ManyToMany** trực tiếp | Thường chỉ cặp khóa ngoại | Hai thực thể độc lập, liên kết rất đơn giản, không có nghiệp vụ riêng | Không có entity đại diện cho từng hàng nối; khó mở rộng khi quan hệ có thuộc tính |
| **@OneToMany / @ManyToOne** qua association entity | Khóa ngoại + thuộc tính như số lượng, ngày bắt đầu, trạng thái | Liên kết có dữ liệu, quy tắc, lịch sử hoặc vòng đời riêng | Có entity và transaction boundary rõ ràng; cần chọn cascade, identity |
| **@ElementCollection** với embeddable/value | Giá trị thuộc vòng đời chủ sở hữu, không có danh tính entity độc lập | Tập giá trị nhỏ như nhãn hoặc địa chỉ đơn giản | Không phù hợp khi hàng liên kết cần tham chiếu hai entity độc lập và có identity/nghiệp vụ riêng |

Một ví dụ khác dễ nhận biết là quan hệ giữa **Student** và **Course**. Nếu chỉ cần biết sinh viên đăng ký khóa học nào, nhiều-nhiều trực tiếp có thể đủ. Khi phải lưu **enrolledAt**, **progress**, **grade**, **status**, và quy tắc “chỉ được đăng ký lại khi lần trước đã hủy”, mối liên kết đã có nghiệp vụ riêng: một entity **Enrollment** là lựa chọn tự nhiên.

Tương tự, với hai đối tượng **User** và **Team**, entity **Membership** có thể lưu vai trò, ngày tham gia, người mời, trạng thái chờ duyệt và thời điểm rời nhóm.

**Tín hiệu cần tạo entity liên kết:** bạn bắt đầu nói về *một lần tham gia*, *một dòng đặt hàng*, *một quyền thành viên* hoặc *một phiên đăng ký* như một thực thể trong câu chuyện nghiệp vụ.

## 3. Mô hình quan hệ cho ví dụ đơn hàng

Ta thống nhất một quy tắc đơn giản để học:

> Trong một đơn hàng, cùng một sản phẩm chỉ xuất hiện **một dòng**. Khi khách mua thêm sản phẩm đó, ứng dụng tăng quantity trên dòng hiện có.

Với quy tắc này, **(order_id, product_id)** là duy nhất. Mỗi dòng có **id** riêng để tiện sửa/xóa, tham chiếu qua API và thêm các nghiệp vụ về sau.

### 3.1. Lược đồ SQL đề xuất

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    full_name VARCHAR(150) NOT NULL
);

CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    current_price NUMERIC(19, 2) NOT NULL CHECK (current_price >= 0),
    stock_quantity INTEGER NOT NULL CHECK (stock_quantity >= 0),
    version BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(id),
    status VARCHAR(24) NOT NULL,
    placed_at TIMESTAMPTZ NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE order_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_orders(id),
    product_id BIGINT NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(19, 2) NOT NULL CHECK (unit_price >= 0),
    CONSTRAINT uq_order_item_product UNIQUE (order_id, product_id)
);

CREATE INDEX idx_orders_customer_date
    ON purchase_orders(customer_id, placed_at);
CREATE INDEX idx_order_items_order
    ON order_items(order_id);
CREATE INDEX idx_order_items_product
    ON order_items(product_id);
~~~

Trong hệ thống thật, DDL được quản lý bằng migration có phiên bản (Flyway hoặc Liquibase). Ví dụ trên dành cho PostgreSQL; cú pháp identity, timestamp có timezone và check constraint tùy hệ quản trị. Không chạy lặp DDL này lên schema đã có bảng tương ứng.

Một vài ý nghĩa quan trọng:

- **order_items.order_id** là foreign key bắt buộc: một dòng không thể tồn tại nếu không thuộc một đơn.
- **order_items.product_id** tham chiếu một Product tồn tại độc lập: xóa dòng **không được xóa Product**.
- **order_items.unit_price** là **giá đã chốt của dòng hàng**, không đọc từ current_price khi hiển thị đơn lịch sử.
- **UNIQUE(order_id, product_id)** hiện thực quy tắc “một sản phẩm một dòng trong mỗi đơn” tại database, kể cả khi hai request đua nhau.
- **CHECK(quantity > 0)** và **CHECK(unit_price >= 0)** bảo vệ tính đúng đắn dù người ghi không phải Hibernate.
- **order_items.id** là khóa nhận diện ổn định cho một dòng trong đời sống nghiệp vụ.

Giả sử ban đầu giá sản phẩm KB-01 là 250.000 VND, khách đặt hai chiếc. Sau đó cửa hàng đổi giá thành 300.000 VND. Dòng hàng cũ phải còn **quantity = 2, unit_price = 250000** và tổng dòng vẫn là **500.000 VND**.

### 3.2. Một dòng hàng có phải entity riêng hay chỉ là giá trị?

Trong một đơn hàng, dòng hàng thường có:

- Identity dùng để thay đổi số lượng, hoàn trả một phần hoặc lưu audit.
- Quan hệ đến Product độc lập.
- Quy tắc trạng thái/giá chốt riêng.
- Ràng buộc tổ hợp với order và product.

Đó là lý do dùng **@Entity OrderItem** thay vì nhét một danh sách mã sản phẩm hoặc một **@ElementCollection** các số lượng. **OrderItem** có thể vẫn là *entity con nằm trong aggregate của PurchaseOrder*: có ID riêng **không đồng nghĩa** nó phải tồn tại độc lập sau khi đơn bị xóa.

## 4. Tránh ánh xạ many-to-many trực tiếp khi bảng nối có thuộc tính

Một ánh xạ đơn giản:

~~~java
@ManyToMany
@JoinTable(
    name = "order_products",
    joinColumns = @JoinColumn(name = "order_id"),
    inverseJoinColumns = @JoinColumn(name = "product_id")
)
private Set<Product> products = new HashSet<>();
~~~

Thông thường nó biểu diễn tập Product liên kết với order. Nó không có nơi trực tiếp để đặt quantity, unitPrice hoặc trạng thái hoàn trả của **từng cặp** (order, product). Nếu bổ sung cột **quantity** vào bảng nối nhưng vẫn chỉ ánh xạ quan hệ trên, Hibernate không tự biến cột đó thành thuộc tính của Product và cũng không tự quản lý nó.

Cách đúng là chuyển bảng nối thành entity:

~~~text
PurchaseOrder (1) ---- (N) OrderItem (N) ---- (1) Product
~~~

Trong Java, mỗi OrderItem có **hai @ManyToOne**:

~~~java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "order_id", nullable = false)
private PurchaseOrder order;

@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "product_id", nullable = false)
private Product product;
~~~

Đồng thời PurchaseOrder có thể có **@OneToMany(mappedBy = "order")** để duyệt các dòng. Nhìn theo database, nhiều dòng thuộc cùng một order và nhiều dòng khác nhau có thể tham chiếu cùng một product. Tổng thể vẫn mô tả quan hệ nhiều-nhiều về mặt nghiệp vụ, nhưng không dùng annotation **@ManyToMany** trực tiếp.

## 5. Ánh xạ bốn entity với JPA/Hibernate

Các class dưới đây thuộc cùng package ví dụ **com.example.shop.domain**; các import có thể đặt tại đầu file tương ứng. Dùng field access (annotation **@Id** đặt trên field), constructor không tham số **protected**, field **private** và business method rõ nghĩa.

### 5.1. Customer: khách hàng

~~~java
package com.example.shop.domain;

import jakarta.persistence.*;
import java.util.Objects;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 255)
    private String email;

    @Column(name = "full_name", nullable = false, length = 150)
    private String fullName;

    protected Customer() {}

    public Customer(String email, String fullName) {
        this.email = Objects.requireNonNull(email);
        this.fullName = Objects.requireNonNull(fullName);
        if (email.isBlank() || fullName.isBlank()) {
            throw new IllegalArgumentException("Thông tin khách hàng không hợp lệ");
        }
    }

    public Long getId() { return id; }
    public String getEmail() { return email; }
    public String getFullName() { return fullName; }
}
~~~

Trong ví dụ này không thêm collection ngược **Customer.orders** nếu use case chưa cần. Mọi quan hệ hai chiều đều làm tăng phần state cần đồng bộ trong Java; chỉ ánh xạ chiều thật sự hữu ích.

### 5.2. Product: danh mục sản phẩm độc lập

~~~java
package com.example.shop.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 64)
    private String sku;

    @Column(nullable = false, length = 200)
    private String name;

    @Column(name = "current_price", nullable = false, precision = 19, scale = 2)
    private BigDecimal currentPrice;

    @Column(name = "stock_quantity", nullable = false)
    private int stockQuantity;

    @Version
    private long version;

    protected Product() {}

    public Product(String sku, String name, BigDecimal currentPrice,
                   int stockQuantity) {
        this.sku = Objects.requireNonNull(sku);
        this.name = Objects.requireNonNull(name);
        changePrice(currentPrice);
        if (stockQuantity < 0) {
            throw new IllegalArgumentException("Tồn kho không hợp lệ");
        }
        this.stockQuantity = stockQuantity;
    }

    public void changePrice(BigDecimal newPrice) {
        if (newPrice == null || newPrice.signum() < 0) {
            throw new IllegalArgumentException("Giá không hợp lệ");
        }
        this.currentPrice = newPrice;
    }

    public void decreaseStock(int quantity) {
        if (quantity <= 0 || quantity > stockQuantity) {
            throw new IllegalStateException("Không đủ tồn kho hoặc sai số lượng");
        }
        stockQuantity -= quantity;
    }

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public String getName() { return name; }
    public BigDecimal getCurrentPrice() { return currentPrice; }
    public int getStockQuantity() { return stockQuantity; }
}
~~~

**Product có vòng đời độc lập** với các đơn hàng. Không đặt CascadeType.REMOVE từ OrderItem đến Product. Giá hiện tại chỉ được chép vào dòng hàng ở thời điểm tạo dòng, sau đó dòng lưu riêng giá lịch sử của nó.

### 5.3. PurchaseOrder: aggregate root chứa dòng hàng

~~~java
package com.example.shop.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
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

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderItem> items = new ArrayList<>();

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 24)
    private OrderStatus status = OrderStatus.DRAFT;

    @Column(name = "placed_at", nullable = false)
    private Instant placedAt;

    @Version
    private long version;

    protected PurchaseOrder() {}

    public PurchaseOrder(Customer customer, Instant placedAt) {
        this.customer = Objects.requireNonNull(customer);
        this.placedAt = Objects.requireNonNull(placedAt);
    }

    public void addItem(Product product, int quantity) {
        requireDraft();
        Objects.requireNonNull(product);
        if (product.getId() == null) {
            throw new IllegalArgumentException("Sản phẩm phải đã tồn tại");
        }
        boolean exists = items.stream().anyMatch(item ->
            item.getProduct().getId().equals(product.getId()));
        if (exists) {
            throw new IllegalArgumentException("Sản phẩm đã có trong đơn");
        }
        items.add(new OrderItem(this, product, quantity,
                                product.getCurrentPrice()));
    }

    public void removeItem(OrderItem item) {
        requireDraft();
        if (items.remove(item)) {
            item.detachFromOrder();
        }
    }

    public void confirm() {
        requireDraft();
        if (items.isEmpty()) {
            throw new IllegalStateException("Không thể xác nhận đơn rỗng");
        }
        status = OrderStatus.CONFIRMED;
    }

    void requireDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Đơn không còn ở trạng thái nháp");
        }
    }

    public BigDecimal getTotal() {
        return items.stream()
            .map(OrderItem::getLineTotal)
            .reduce(BigDecimal.ZERO, BigDecimal::add);
    }

    public Long getId() { return id; }
    public Customer getCustomer() { return customer; }
    public OrderStatus getStatus() { return status; }
    public Instant getPlacedAt() { return placedAt; }
    public List<OrderItem> getItems() {
        return Collections.unmodifiableList(items);
    }
}
~~~

~~~java
package com.example.shop.domain;

public enum OrderStatus {
    DRAFT, CONFIRMED, CANCELLED
}
~~~

Ở đây **PurchaseOrder** điều khiển vòng đời OrderItem:

- **cascade = ALL**: khi persist/remove đơn theo entity lifecycle, các dòng có thể nhận cascade tương ứng.
- **orphanRemoval = true**: khi một dòng không còn thuộc collection của đơn, Hibernate xóa chính OrderItem tại flush.
- **mappedBy = "order"**: khóa ngoại **order_items.order_id** do **OrderItem.order** quản lý.
- Không cascade từ PurchaseOrder đến Customer hay Product, vì các entity đó độc lập và có thể được nhiều đơn tham chiếu.

Việc cung cấp danh sách chỉ đọc bằng **Collections.unmodifiableList** giúp code bên ngoài không tùy tiện chỉnh collection, nhưng Hibernate vẫn giữ và quản lý collection bên trong field **items**. Helper method thực hiện thay đổi trên collection hiện có.

### 5.4. OrderItem: thực thể liên kết có quy tắc riêng

~~~java
package com.example.shop.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(name = "order_items",
       uniqueConstraints = @UniqueConstraint(
           name = "uq_order_item_product",
           columnNames = {"order_id", "product_id"}
       ))
public class OrderItem {
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

    @Column(name = "unit_price", nullable = false, precision = 19, scale = 2)
    private BigDecimal unitPrice;

    protected OrderItem() {}

    OrderItem(PurchaseOrder order, Product product,
              int quantity, BigDecimal unitPrice) {
        this.order = Objects.requireNonNull(order);
        this.product = Objects.requireNonNull(product);
        if (quantity <= 0 || unitPrice == null || unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Dòng hàng không hợp lệ");
        }
        this.quantity = quantity;
        this.unitPrice = unitPrice;
    }

    public void changeQuantity(int newQuantity) {
        order.requireDraft();
        if (newQuantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải dương");
        }
        this.quantity = newQuantity;
    }

    void detachFromOrder() {
        this.order = null;
    }

    public BigDecimal getLineTotal() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }

    public Long getId() { return id; }
    public PurchaseOrder getOrder() { return order; }
    public Product getProduct() { return product; }
    public int getQuantity() { return quantity; }
    public BigDecimal getUnitPrice() { return unitPrice; }
}
~~~

**OrderItem** có:

- ID và hai khóa ngoại, thể hiện nó là **một hàng có danh tính**, không chỉ một collection reference.
- Thuộc tính của liên kết: quantity và unitPrice.
- Quy tắc kiểm tra quantity > 0 và unitPrice >= 0.
- Quy tắc nghiệp vụ: chỉ thay đổi quantity khi đơn đang là **DRAFT**.
- Phương thức getLineTotal tính từ **giá chốt**.

Phương thức **detachFromOrder()** chỉ được gọi trong bối cảnh **orphanRemoval = true**, khi dòng đã bị loại khỏi parent collection và sẽ bị xóa. Mặc dù field **order** tạm thời nhận null trong object graph, mục tiêu là **DELETE dòng**, không phải lưu một dòng có **order_id = NULL**. Nếu thay đổi thiết kế để OrderItem tồn tại độc lập, phải bỏ cách làm này và định nghĩa lại ownership, nullability, cascade.

## 6. Phía sở hữu quan hệ và helper method hai chiều

Ở JPA, chỉ một phía điều khiển foreign key của một quan hệ hai chiều.

~~~text
PurchaseOrder.items  @OneToMany(mappedBy = "order")  -> phía nghịch đảo
OrderItem.order       @ManyToOne + @JoinColumn       -> phía sở hữu FK
~~~

Vì vậy thao tác sau dễ khiến object graph mất nhất quán:

~~~java
// Tránh công khai mutation kiểu này:
order.getItems().add(item);
// Nếu item.order chưa được gán -> quan hệ phía sở hữu sai.
~~~

Helper method **addItem()** trong ví dụ đã tạo OrderItem với **order = this** rồi mới thêm vào collection. Khi xóa, helper loại khỏi collection và đánh dấu không còn thuộc owner.

Trường hợp **thay đổi sản phẩm trên một dòng**, không nên tùy tiện viết **item.product = anotherProduct**. Đó là thay danh tính của liên kết và có thể vi phạm unique constraint. Trong nhiều domain, cách rõ ràng hơn là xóa dòng cũ và thêm một dòng mới, hoặc dành riêng một business method với kiểm tra trạng thái/giá chốt.

Với **quan hệ một chiều**, bạn cũng có thể chỉ giữ OrderItem.order mà không giữ PurchaseOrder.items, sau đó query OrderItem theo orderId. Chọn cách này khi collection có thể rất lớn hoặc không cần thao tác trên aggregate graph; các quy tắc vòng đời sẽ chuyển sang service/repository thay vì phụ thuộc orphanRemoval trên collection.

## 7. SQL được sinh khi tạo, sửa và xóa liên kết

Giả sử một đơn mới có hai dòng: bàn phím **2 × 250.000** và chuột **1 × 120.000**.

### 7.1. Tạo mới

Các câu SQL có thể có hình dạng:

~~~sql
INSERT INTO purchase_orders
    (customer_id, placed_at, status, version)
VALUES (?, ?, 'DRAFT', 0);

INSERT INTO order_items
    (order_id, product_id, quantity, unit_price)
VALUES (?, ?, 2, 250000.00);

INSERT INTO order_items
    (order_id, product_id, quantity, unit_price)
VALUES (?, ?, 1, 120000.00);
~~~

Với IDENTITY, Hibernate có thể phải thực hiện insert để lấy ID order trước khi chèn các dòng. Thứ tự chính xác chịu ảnh hưởng cơ chế cấp ID và action queue; minh họa trên diễn đạt phụ thuộc FK, không phải cam kết SQL literal của mọi dialect.

### 7.2. Sửa số lượng của một dòng

~~~java
item.changeQuantity(3);
~~~

Trong transaction với entity managed, dirty checking có thể phát sinh:

~~~sql
UPDATE order_items
SET quantity = ?
WHERE id = ?;
~~~

Không cần xóa dòng cũ hay cập nhật Product chỉ vì số lượng đặt thay đổi. Tổng dòng được tính lại từ quantity và unitPrice. Nếu bổ sung **@Version** cho OrderItem, SQL UPDATE còn kiểm tra version và tăng version theo cơ chế optimistic locking.

### 7.3. Xóa một dòng với orphan removal

~~~java
order.removeItem(item);
~~~

Hibernate có thể sinh:

~~~sql
DELETE FROM order_items WHERE id = ?;
~~~

**Không có** lý do để sinh:

~~~sql
DELETE FROM products WHERE id = ?;
~~~

Product vẫn tồn tại, có thể được tham chiếu trong nhiều đơn khác.

### 7.4. Xóa cả đơn

Khi ứng dụng xóa đơn có cascade remove đến OrderItem, Hibernate có thể xóa các dòng liên quan rồi xóa parent, đảm bảo ràng buộc foreign key:

~~~sql
DELETE FROM order_items WHERE id = ?;
DELETE FROM order_items WHERE id = ?;
DELETE FROM purchase_orders WHERE id = ?;
~~~

Cơ chế **ON DELETE CASCADE** tại database có thể thay đổi SQL ORM cần gửi nếu được cấu hình phù hợp, nhưng callback/cache/chiến lược xóa là vấn đề riêng. Với đơn đã xác nhận, ứng dụng thật thường **không xóa vật lý** để giữ lịch sử, thay vào đó đổi trạng thái và xử lý hoàn tiền/hoàn kho theo quy tắc.

### 7.5. Khi không có orphanRemoval

Nếu bạn chỉ xóa phần tử khỏi **@OneToMany(mappedBy = "order")** mà không thay OrderItem.order, Hibernate có thể không cập nhật FK vì bạn mới sửa phía nghịch đảo. Nếu chủ động đặt **order = null** và cột order_id cho phép NULL, ORM có thể sinh **UPDATE order_items SET order_id = NULL** chứ không xóa entity.

Vì mô hình đơn hàng của chúng ta không cho dòng đứng riêng và khóa ngoại là **NOT NULL**, orphan removal có ngữ nghĩa phù hợp hơn. Đừng dùng orphanRemoval nếu child có thể chuyển sang parent khác hoặc sống độc lập.

## 8. Khóa chính của thực thể liên kết: ID tự sinh hay khóa ghép?

Có hai cách thiết kế phổ biến; cả hai đều hợp lệ khi phù hợp nghiệp vụ.

### 8.1. Khóa thay thế (surrogate key): OrderItem.id

~~~text
order_items
  id          PK
  order_id    FK
  product_id  FK
  quantity
  unit_price
  UNIQUE(order_id, product_id)
~~~

Ưu điểm:

- API, log/audit, refund và các bảng khác có thể tham chiếu dòng bằng một ID ổn định.
- Có thể mở rộng thêm thuộc tính và lịch sử trên entity.
- Không cần đưa hai khóa ngoại vào **@EmbeddedId**.
- Mã Java với **@GeneratedValue** và **@ManyToOne** tương đối dễ đọc.

Hạn chế:

- Cần thêm cột ID.
- ID tự sinh **không thay thế UNIQUE(order_id, product_id)**; nếu quên unique constraint, ứng dụng có thể lưu nhiều dòng trùng sản phẩm trong một đơn.

Đây là lựa chọn được dùng xuyên suốt bài.

### 8.2. Khóa ghép: (order_id, product_id)

Nếu bản sắc của mỗi liên kết thật sự chỉ là cặp (order, product), có thể dùng **@EmbeddedId** và **@MapsId**.

~~~java
package com.example.shop.domain;

import jakarta.persistence.*;
import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class OrderItemId implements Serializable {
    @Column(name = "order_id")
    private Long orderId;

    @Column(name = "product_id")
    private Long productId;

    protected OrderItemId() {}

    public OrderItemId(Long orderId, Long productId) {
        this.orderId = Objects.requireNonNull(orderId);
        this.productId = Objects.requireNonNull(productId);
    }

    public Long getOrderId() { return orderId; }
    public Long getProductId() { return productId; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof OrderItemId that)) return false;
        return Objects.equals(orderId, that.orderId)
            && Objects.equals(productId, that.productId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(orderId, productId);
    }
}
~~~

~~~java
package com.example.shop.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(name = "order_items")
public class OrderItemWithCompositeId {
    @EmbeddedId
    private OrderItemId id;

    @MapsId("orderId")
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @MapsId("productId")
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "product_id", nullable = false)
    private Product product;

    @Column(nullable = false)
    private int quantity;

    @Column(name = "unit_price", nullable = false, precision = 19, scale = 2)
    private BigDecimal unitPrice;

    protected OrderItemWithCompositeId() {}

    public OrderItemWithCompositeId(PurchaseOrder order, Product product,
                                    int quantity, BigDecimal unitPrice) {
        this.order = Objects.requireNonNull(order);
        this.product = Objects.requireNonNull(product);
        if (order.getId() == null || product.getId() == null) {
            throw new IllegalArgumentException("Cần ID của order và product");
        }
        if (quantity <= 0 || unitPrice == null || unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Dữ liệu dòng hàng không hợp lệ");
        }
        this.id = new OrderItemId(order.getId(), product.getId());
        this.quantity = quantity;
        this.unitPrice = unitPrice;
    }
}
~~~

Đoạn này minh họa **một phương án thay thế** cho class OrderItem dùng khóa ID tự sinh ở phần trước, **không** ánh xạ đồng thời cả hai class vào cùng bảng trong một ứng dụng. Nếu chọn khóa ghép, thay thế mapping và schema nhất quán.

**@MapsId("orderId")** nghĩa là khóa ngoại từ trường order đồng thời cung cấp phần **orderId** trong embedded ID; tương tự với productId. Trong ví dụ constructor cần order và product **đã có ID**, nên không dùng nguyên xi constructor này để cascade persist một đơn mới chưa có ID. Nếu muốn cascade với ID được tạo sau, cần thiết kế trình tự persist/mapping derived identifier phù hợp và kiểm tra trên phiên bản Hibernate thực tế.

**Khi nào khóa ghép bất tiện?**

- Quan hệ cần nhiều phiên bản giữa cùng hai bên (ví dụ cùng sản phẩm được đặt thành nhiều dòng có khuyến mại khác nhau): cặp (order, product) không còn duy nhất.
- Một đầu của cặp có thể thay đổi về nghiệp vụ: thay khóa chính tương đương thay identity.
- Entity liên kết cần tham chiếu từ bảng khác qua một ID đơn giản.

Ngược lại, với một bảng Membership chỉ có **một** thành viên cho mỗi cặp (team, user) tại một thời điểm và không cần ID độc lập, khóa ghép có thể rất tự nhiên. Dù dùng cách nào, **equals/hashCode của khóa ghép** cần dựa trên những thành phần khóa ổn định.

## 9. Identity, equals/hashCode và collection Java

Khi dùng ID tự sinh, OrderItem chưa có ID lúc mới tạo. Nếu **equals/hashCode** chỉ dựa vào ID nhưng hash code đổi từ null sang một số sau persist, một đối tượng đã đặt trong **HashSet** có thể trở nên khó tìm/xóa.

Do đó trong ví dụ chúng ta dùng **List<OrderItem>** và không tự viết equality của entity chỉ bằng ID. Phần tử được thêm và xóa qua object reference trong một persistence context hoặc được tìm bằng ID rồi xóa bằng helper.

Một vài quy tắc thực hành:

- Nếu dùng **Set<OrderItem>**, thiết kế equality theo identity ổn định, cân nhắc proxy Hibernate, transient entity và thời điểm ID được sinh.
- Không dùng Lombok **@Data** tùy tiện trên entity có quan hệ hai chiều: phương thức sinh **equals**, **hashCode**, **toString** có thể duyệt quan hệ lazy, tạo vòng lặp hoặc phát sinh SQL.
- Không cho **equals/hashCode** dựa trên quantity hoặc unitPrice, vì chúng là dữ liệu có thể thay đổi mà không làm entity trở thành một dòng khác.
- Với **@EmbeddedId**, equals/hashCode được xây theo các thành phần khóa bất biến.
- Không dùng ID database chưa được cấp làm giả định trong constructor/factory đối với entity mới.

Việc chọn List thay vì Set trong ví dụ còn giữ được thứ tự trong Java tại thời điểm thao tác, nhưng **không tự tạo thứ tự bền vững trong SQL**. Nếu nghiệp vụ cần reorder có lưu index, cần thiết kế **@OrderColumn** hoặc cột thứ tự riêng, đồng thời hiểu các UPDATE phát sinh.

## 10. Service tạo đơn: transaction và cascade đúng mục đích

Một repository đơn giản:

~~~java
package com.example.shop.application;

import com.example.shop.domain.*;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository extends JpaRepository<Customer, Long> {}
public interface ProductRepository extends JpaRepository<Product, Long> {}
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {}
~~~

Đặt mỗi interface **public** ở file Java riêng trong project thật; đoạn trên gộp lại để dễ quan sát chữ ký. DTO tạo đơn:

~~~java
package com.example.shop.application;

import java.util.List;

public record OrderLineInput(Long productId, int quantity) {}
public record CreateOrderInput(Long customerId, List<OrderLineInput> lines) {}
~~~

Service:

~~~java
package com.example.shop.application;

import com.example.shop.domain.*;
import java.time.Instant;
import java.util.HashSet;
import java.util.Set;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {
    private final CustomerRepository customers;
    private final ProductRepository products;
    private final PurchaseOrderRepository orders;

    public OrderApplicationService(CustomerRepository customers,
                                   ProductRepository products,
                                   PurchaseOrderRepository orders) {
        this.customers = customers;
        this.products = products;
        this.orders = orders;
    }

    @Transactional
    public Long createDraft(CreateOrderInput input) {
        if (input == null || input.customerId() == null
                || input.lines() == null || input.lines().isEmpty()) {
            throw new IllegalArgumentException("Đơn hàng phải có dòng hàng");
        }

        Customer customer = customers.findById(input.customerId())
            .orElseThrow(() -> new IllegalArgumentException("Không có khách"));

        PurchaseOrder order = new PurchaseOrder(customer, Instant.now());
        Set<Long> seenProductIds = new HashSet<>();

        for (OrderLineInput line : input.lines()) {
            if (line == null || line.productId() == null
                    || line.quantity() <= 0
                    || !seenProductIds.add(line.productId())) {
                throw new IllegalArgumentException("Dòng hàng không hợp lệ/trùng");
            }
            Product product = products.findById(line.productId())
                .orElseThrow(() -> new IllegalArgumentException("Không có sản phẩm"));
            order.addItem(product, line.quantity());
        }

        return orders.save(order).getId();
    }
}
~~~

**@Transactional** bao toàn bộ use case: tìm khách, kiểm tra từng sản phẩm, chốt giá, tạo order và các OrderItem. Nếu một dòng không hợp lệ, exception runtime làm transaction rollback theo quy tắc mặc định của Spring; không tồn tại đơn được ghi một phần.

**orders.save(order)** lưu aggregate và các OrderItem mới qua **cascade = ALL**. Customer và Product đã được truy vấn trong transaction, không cần cascade persist chúng.

Trong ví dụ này, **createDraft chưa trừ tồn kho**. Có thể giữ giá chốt tại thời điểm tạo nháp, rồi trừ kho khi xác nhận. Ứng dụng khác có thể chỉ chốt giá khi thanh toán; đó là quyết định nghiệp vụ cần làm rõ. Nếu giá cần được làm mới trước xác nhận, phải có một phương thức nghiệp vụ tường minh và lưu được dấu vết quyết định ấy.

### 10.1. Vì sao cần cả validation Java lẫn ràng buộc DB?

Service kiểm tra trùng productId để trả lỗi dễ hiểu. Tuy nhiên hai request đồng thời vẫn có thể tạo dữ liệu trùng nếu không có constraint. **UNIQUE(order_id, product_id)** là lớp bảo vệ cuối tại DB, còn Java validation giúp diễn đạt quy tắc và thông báo lỗi phù hợp.

Không coi **@Column(nullable=false)** là thay thế cho validation hay constraint được triển khai bằng migration. Tương tự, **@UniqueConstraint** là metadata mapping; schema thực tế phải có unique constraint.

## 11. Thay đổi số lượng và xóa một dòng theo ID

Khi API nhận lệnh sửa quantity, không nên merge trực tiếp một OrderItem detached chỉ gồm ID và quantity, vì các field order/product/unitPrice còn thiếu có thể gây sao chép null ngoài ý muốn.

Thay vào đó, load **PurchaseOrder managed** và tìm đúng dòng nằm trong aggregate:

~~~java
@Transactional
public void changeQuantity(Long orderId, Long itemId, int newQuantity) {
    PurchaseOrder order = orders.findById(orderId)
        .orElseThrow(() -> new IllegalArgumentException("Không có đơn"));

    OrderItem item = order.getItems().stream()
        .filter(i -> i.getId().equals(itemId))
        .findFirst()
        .orElseThrow(() -> new IllegalArgumentException("Dòng không thuộc đơn"));

    item.changeQuantity(newQuantity);
    // Dirty checking cập nhật row order_items ở flush/commit.
}
~~~

Đây là **phương thức bổ sung** của OrderApplicationService, dùng cùng field **orders** đã khai báo trước đó. Phương thức sửa quantity nằm trên OrderItem nhưng tự kiểm tra trạng thái của order. Vì truy cập **order.getItems()** trong transaction, collection LAZY có thể được load an toàn.

Để xóa:

~~~java
@Transactional
public void removeLine(Long orderId, Long itemId) {
    PurchaseOrder order = orders.findById(orderId)
        .orElseThrow(() -> new IllegalArgumentException("Không có đơn"));

    OrderItem item = order.getItems().stream()
        .filter(i -> i.getId().equals(itemId))
        .findFirst()
        .orElseThrow(() -> new IllegalArgumentException("Dòng không thuộc đơn"));

    order.removeItem(item);
    // orphanRemoval = true -> xóa OrderItem khi flush.
}
~~~

**Lợi ích của việc kiểm tra membership:** một khách không thể yêu cầu sửa/xóa dòng hàng của đơn khác chỉ bằng cách đoán itemId. Ở ứng dụng thật, service còn cần kiểm tra user hiện tại có quyền sửa order hay không.

Nếu collection có rất nhiều dòng, tải toàn bộ để tìm một item có thể tốn kém. Khi đó cân nhắc repository query **findByIdAndOrderId**, vẫn xác minh ranh giới aggregate và xử lý orphan/cascade/persistence context nhất quán. Đây là tối ưu riêng, không nên làm bằng native DELETE bừa bãi vì bulk DML bỏ qua một số entity callbacks và state managed.

## 12. Giá lịch sử và tính tổng: thuộc tính của quan hệ

Giả sử:

| Product | Giá hiện tại lúc đặt | Quantity | Unit price được lưu | Line total |
|---|---:|---:|---:|---:|
| KB-01 | 250.000 | 2 | 250.000 | 500.000 |
| MS-02 | 120.000 | 1 | 120.000 | 120.000 |
| **Tổng đơn** | | | | **620.000** |

Sau khi Product KB-01 tăng giá lên 300.000, **OrderItem.unitPrice vẫn là 250.000**. Nếu hiển thị hóa đơn bằng Product.currentPrice, tổng đơn sẽ đổi thành 720.000 dù khách không mua thêm hàng nào.

Chính nhu cầu **giá thuộc về một lần giao dịch** là ví dụ mạnh nhất cho association entity.

Nếu bài toán có giảm giá, thuế hoặc loại tiền tệ, cần quyết định chỗ lưu phù hợp:

- **discountAmount** trên OrderItem khi giảm giá được áp dụng cho từng dòng.
- **taxRate/taxAmount** trên dòng khi cần lưu thuế đã xác định tại thời điểm giao dịch, thay vì đọc thuế suất hiện tại.
- **currency** trên order hoặc line tùy việc một đơn có cho nhiều loại tiền hay không. Nếu đa tiền tệ, không cộng BigDecimal khác currency trực tiếp.
- **refundQuantity** và lịch sử hoàn trả có thể cần entity riêng **ReturnLine** trỏ về OrderItem, thay vì ghi đè quantity của giao dịch gốc.

Với tiền, dùng **BigDecimal** và kiểu SQL **NUMERIC/DECIMAL**, không dùng float/double để đại diện số tiền. Thể hiện phép tính và quy tắc rounding bằng một API nghiệp vụ rõ ràng.

## 13. Khi nào thuộc tính nằm trên Product, Order hay OrderItem?

Một phép thử hữu ích: **Nếu cùng một sản phẩm xuất hiện trong hai đơn khác nhau, thuộc tính này có thể khác nhau không?**

| Thuộc tính | Entity phù hợp | Lý do |
|---|---|---|
| SKU, tên danh mục, giá hiện hành | Product | Thuộc tính của sản phẩm đang được bán |
| Khách đặt, thời điểm tạo, trạng thái chung | PurchaseOrder | Thuộc tính của toàn bộ đơn |
| Quantity của sản phẩm trong đơn | OrderItem | Thuộc tính của cặp order-product |
| Unit price đã chốt | OrderItem | Có thể khác giữa hai đơn dù cùng Product |
| Giảm giá riêng của dòng | OrderItem | Phụ thuộc chương trình/điều kiện tại lần đặt |
| Tổng tiền đơn | PurchaseOrder (tính từ items hoặc snapshot theo domain) | Là kết quả tổng hợp các dòng |
| Hạn bảo hành của đơn vị hàng cụ thể | Có thể entity SerialNumber/ShipmentItem | Nếu cần theo dõi từng chiếc, một OrderItem gộp quantity có thể chưa đủ |

Không nhất thiết đẩy mọi thuộc tính lên association entity. Nếu **tên sản phẩm lúc mua** cần giữ nguyên cho hóa đơn pháp lý, có thể lưu snapshot tên sản phẩm trên OrderItem hoặc snapshot hóa đơn riêng. Nếu không có yêu cầu đó, tên có thể đọc qua Product; chính sách phải được quyết định nhất quán.

## 14. Chọn ranh giới vòng đời và cascade

Đặt câu hỏi: **nếu bỏ liên kết, điều gì phải còn tồn tại?**

| Quan hệ | Khi bỏ liên kết | Cascade/orphan phù hợp |
|---|---|---|
| PurchaseOrder → OrderItem | Dòng hàng thuộc đơn không còn hợp lệ | Có thể dùng cascade persist/remove và orphanRemoval |
| OrderItem → Product | Sản phẩm vẫn tồn tại trong catalog | Không cascade remove Product |
| PurchaseOrder → Customer | Khách vẫn tồn tại | Không cascade remove Customer |
| Team → Membership | Membership hết hiệu lực hoặc bị xóa theo policy | Tùy chính sách audit/soft delete |
| Membership → User | User vẫn tồn tại | Không cascade remove User |
| Course → Enrollment | Enrollment có thể cần lưu lịch sử điểm | Có thể dùng status/soft delete thay vì xóa vật lý |

**orphanRemoval** phù hợp với child có vòng đời phụ thuộc owner và **thật sự phải xóa** khi bị gỡ. Nếu lịch sử đơn hàng, thanh toán, chiết khấu hoặc thành viên cần lưu vết, có thể đánh dấu trạng thái **CANCELLED**, **INACTIVE**, **REVOKED** thay vì xóa hàng. Trong trường hợp đó không dùng orphanRemoval như một thao tác hủy nghiệp vụ.

Mặt khác, **CascadeType.REMOVE** và **orphanRemoval** không đồng nghĩa:

- CascadeType.REMOVE lan truyền thao tác xóa parent đến child được cascade.
- orphanRemoval có thể xóa child bị loại khỏi quan hệ của parent ngay cả khi parent không bị xóa.
- Foreign key **ON DELETE CASCADE** là cơ chế của DB, không mặc nhiên chạy JPA lifecycle callbacks cho mọi hàng do DB xóa.

Với entity dùng chung như Product, việc cấu hình **CascadeType.ALL** trên OrderItem.product là nguy hiểm vì nó bao gồm cả REMOVE. Không nên dùng cascade theo thói quen chỉ để giảm số lần gọi repository.

## 15. Truy vấn association entity bằng JPQL

### 15.1. Đọc chi tiết một đơn

Trong PurchaseOrderRepository, ta có thể thêm query:

~~~java
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import java.util.Optional;

@Query("""
    select distinct o
    from PurchaseOrder o
    join fetch o.customer
    left join fetch o.items item
    left join fetch item.product
    where o.id = :id
    """)
Optional<PurchaseOrder> findDetailById(@Param("id") Long id);
~~~

Trong use case **một đơn cụ thể**, fetch join collection có thể phù hợp để nạp order, customer, items và product mà màn hình cần. Sau đó chuyển entity thành DTO **bên trong service transaction**:

~~~java
public record OrderLineView(
    Long itemId,
    String sku,
    String productName,
    int quantity,
    BigDecimal unitPrice,
    BigDecimal lineTotal
) {}

public record OrderDetailView(
    Long orderId,
    String customerName,
    BigDecimal total,
    List<OrderLineView> lines
) {}
~~~

~~~java
@Transactional(readOnly = true)
public OrderDetailView getDetail(Long orderId) {
    PurchaseOrder order = orders.findDetailById(orderId)
        .orElseThrow(() -> new IllegalArgumentException("Không có đơn"));

    List<OrderLineView> lines = order.getItems().stream()
        .map(item -> new OrderLineView(
            item.getId(),
            item.getProduct().getSku(),
            item.getProduct().getName(),
            item.getQuantity(),
            item.getUnitPrice(),
            item.getLineTotal()
        ))
        .toList();

    return new OrderDetailView(
        order.getId(),
        order.getCustomer().getFullName(),
        order.getTotal(),
        lines
    );
}
~~~

Hai record đặt trong package phù hợp và import BigDecimal/List; phương thức getDetail là **phương thức bổ sung trong OrderApplicationService**. Không trả entity graph trực tiếp ra JSON vì dễ gặp lazy loading, tham chiếu vòng và tiết lộ dữ liệu không cần thiết.

### 15.2. Tìm đơn nào có một sản phẩm

~~~java
@Query("""
    select distinct i.order
    from OrderItem i
    where i.product.sku = :sku
    """)
List<PurchaseOrder> findOrdersContainingSku(@Param("sku") String sku);
~~~

Truy vấn dựa trên **OrderItem** vì chính liên kết chứa Product. Nếu có thêm điều kiện quantity, giá chốt hoặc trạng thái hoàn trả, ta chỉ cần mở rộng điều kiện trên OrderItem, không phải thao tác với collection ManyToMany ẩn.

### 15.3. Thống kê số lượng và doanh thu

~~~java
@Query("""
    select sum(i.quantity)
    from OrderItem i
    where i.product.id = :productId
      and i.order.status = :status
    """)
Long sumSoldQuantity(@Param("productId") Long productId,
                     @Param("status") OrderStatus status);
~~~

~~~java
@Query("""
    select sum(i.quantity * i.unitPrice)
    from OrderItem i
    where i.order.status = :status
    """)
BigDecimal sumOrderValue(@Param("status") OrderStatus status);
~~~

SQL aggregate có thể trả null khi không có hàng phù hợp; service cần định nghĩa null thành 0 nếu phù hợp nghiệp vụ. Ở ví dụ này “doanh thu” chỉ được xem như tổng giá dòng của các đơn CONFIRMED, chưa tính hoàn tiền, phí, giảm giá hoặc thuế.

### 15.4. Vì sao cần cẩn thận với phân trang?

Một PurchaseOrder có nhiều OrderItem, vì vậy join sẽ tạo **nhiều hàng SQL cho cùng một đơn**. Không dùng collection **JOIN FETCH** trực tiếp với pageable và giả định LIMIT/OFFSET của DB vẫn biểu diễn đúng số đơn. Hibernate có thể phải xử lý phân trang trong bộ nhớ hoặc từ chối theo cấu hình.

Với màn hình danh sách, ưu tiên projection/DTO chỉ lấy dữ liệu đơn và khách; nếu cần tải nhiều items của một trang, có thể truy vấn hai bước: trang ID đơn trước, rồi lấy chi tiết theo tập ID và giữ lại thứ tự của trang.

## 16. Lazy loading, N+1 và chiều truy cập

**@ManyToOne** theo JPA có mặc định eager; trong các entity trên, ta đã ghi **fetch = LAZY** cho quan hệ từ OrderItem tới Order/Product và từ PurchaseOrder tới Customer. **@OneToMany** thường lazy. Khi code gọi **order.getItems()**, Hibernate có thể truy vấn để nạp collection; khi gọi **item.getProduct().getName()**, có thể phát sinh thêm SELECT.

Ví dụ N+1:

~~~java
List<PurchaseOrder> orders = findRecentOrders();
for (PurchaseOrder order : orders) {
    System.out.println(order.getItems().size());
}
~~~

Nếu mỗi collection được load riêng, hệ thống có thể có một query lấy danh sách cộng thêm nhiều query lấy items. Trên danh sách nhiều đơn, chi phí này tăng rất nhanh.

Các hướng xử lý:

- **Chi tiết một đơn:** fetch join các quan hệ cần hiển thị hoặc dùng DTO query.
- **Danh sách phân trang:** projection cho cột cần dùng; tải items bằng batch hoặc truy vấn riêng cho các order ID trong trang.
- **Báo cáo:** aggregate JPQL/SQL trên OrderItem thay vì tải hàng nghìn entity rồi tính trong Java.
- **Quan sát:** bật SQL log và đo số statement trước khi chọn chiến lược tối ưu.

Không chuyển tất cả quan hệ thành **EAGER** vì có thể làm những use case đơn giản tải nhiều dữ liệu thừa. Với **spring.jpa.open-in-view=false**, hãy tạo DTO trong service transaction để tránh truy cập collection lazy sau khi persistence context đã đóng.

## 17. Cập nhật đồng thời và quy tắc nghiệp vụ riêng của liên kết

Chính vì một OrderItem có quantity, giá chốt và trạng thái nên phải có chính sách cập nhật đồng thời, thay vì coi nó chỉ là một phần tử trong List.

### 17.1. Hai request cùng sửa số lượng

Giả sử OrderItem có quantity = 1. Request A đổi thành 2, request B đổi thành 3 dựa trên cùng dữ liệu cũ. Nếu không có cơ chế kiểm tra cạnh tranh, cập nhật cuối có thể ghi đè cập nhật đầu.

Có thể thêm:

~~~java
@Version
private long version;
~~~

vào OrderItem nếu muốn optimistic locking **theo từng dòng**. Khi Hibernate cập nhật một entity có version, statement có thể kiểm tra phiên bản cũ, ví dụ:

~~~sql
UPDATE order_items
SET quantity = ?, version = ?
WHERE id = ? AND version = ?;
~~~

Nếu không update được hàng nào do version đã đổi, Hibernate báo optimistic-lock conflict. Caller phải xử lý bằng cách tải lại, thông báo xung đột hoặc retry **toàn bộ transaction** theo chính sách. **@Version trên PurchaseOrder** trong ví dụ có thể bảo vệ một số thay đổi lên aggregate, nhưng không nên mặc định nó phát hiện mọi thay đổi trực tiếp vào field của OrderItem nếu OrderItem không có version; hãy xác định ranh giới cạnh tranh cần bảo vệ.

### 17.2. Hai đơn cùng mua sản phẩm cuối cùng

Giả sử còn một sản phẩm trong kho, hai đơn khác nhau cùng được xác nhận. Đây là tranh chấp ở **Product.stockQuantity**, không chỉ ở OrderItem. Cần transaction và chiến lược lock hoặc cập nhật điều kiện ở DB.

Một phương án minh họa là khóa các Product khi xác nhận:

~~~java
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("select p from Product p where p.id = :id")
Optional<Product> findByIdForUpdate(@Param("id") Long id);
~~~

Đặt phương thức này trong **ProductRepository**. Đồng thời có thể khóa một đơn khi đổi trạng thái:

~~~java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("select o from PurchaseOrder o where o.id = :id")
Optional<PurchaseOrder> findByIdForUpdate(@Param("id") Long id);
~~~

Đặt phương thức thứ hai trong **PurchaseOrderRepository**. Trong service:

~~~java
@Transactional
public void confirmOrder(Long orderId) {
    PurchaseOrder order = orders.findByIdForUpdate(orderId)
        .orElseThrow(() -> new IllegalArgumentException("Không có đơn"));

    if (order.getStatus() != OrderStatus.DRAFT) {
        throw new IllegalStateException("Đơn đã được xử lý");
    }

    var lines = order.getItems().stream()
        .sorted(java.util.Comparator.comparing(
            line -> line.getProduct().getId()))
        .toList();

    for (OrderItem item : lines) {
        Product product = products.findByIdForUpdate(
            item.getProduct().getId())
            .orElseThrow(() ->
                new IllegalArgumentException("Sản phẩm không tồn tại"));
        product.decreaseStock(item.getQuantity());
    }

    order.confirm();
    // Dirty checking ghi thay đổi khi flush/commit.
}
~~~

Khóa **PurchaseOrder** giúp không xác nhận hai lần cùng đơn theo đường service này. Khóa **Product** theo thứ tự ID giảm nguy cơ deadlock khi nhiều đơn chứa các sản phẩm giống nhau. Nếu thiếu kho ở bất kỳ dòng nào, exception runtime làm rollback các thay đổi trong transaction.

Đây là **một chiến lược mẫu**, không phải giải pháp duy nhất: optimistic locking của Product, atomic SQL **UPDATE ... SET stock_quantity = stock_quantity - ? WHERE stock_quantity >= ?**, hoặc mô hình reservation có thể thích hợp hơn ở quy mô khác. Hành vi lock, isolation và deadlock phải được kiểm thử trên DB thực tế; H2 không đại diện đầy đủ cho PostgreSQL/MySQL.

### 17.3. Không thay identity liên kết để “sửa” nghiệp vụ

Một yêu cầu thay productId trên một OrderItem sau khi xác nhận có thể phá dữ liệu lịch sử. Nếu đổi hàng, hoàn hàng hoặc thay thế sản phẩm, hãy diễn đạt thành hành động có lưu dấu vết riêng. Việc thay khóa ngoại không nhất thiết tương đương việc đổi một field thông thường.

## 18. Một ứng dụng khác: Membership với vai trò và thời hạn

Xét hai entity **User** và **Team**. Một người có thể thuộc nhiều team; một team có nhiều thành viên. Nếu chỉ dùng:

~~~java
@ManyToMany
private Set<User> members;
~~~

ta không thể quản lý trực tiếp vai trò trong từng team hoặc ngày hết hạn thành viên. Tạo một entity:

~~~java
@Entity
@Table(
    name = "team_memberships",
    uniqueConstraints = @UniqueConstraint(
        columnNames = {"team_id", "user_id"}
    )
)
public class Membership {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "team_id", nullable = false)
    private Team team;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private MembershipRole role;

    @Column(name = "joined_at", nullable = false)
    private Instant joinedAt;

    @Column(name = "expires_at")
    private Instant expiresAt;

    protected Membership() {}

    public boolean isActiveAt(Instant time) {
        return joinedAt.compareTo(time) <= 0
            && (expiresAt == null || time.isBefore(expiresAt));
    }
}
~~~

Đây là code khung: cần định nghĩa **Team**, **User**, **MembershipRole**, import Java/JPA và constructor nghiệp vụ phù hợp trước khi đưa vào dự án hoàn chỉnh. Điểm chính là Membership trở thành nơi kiểm tra **thành viên có quyền gì**, **đã tham gia chưa** và **còn hiệu lực tại thời điểm nào**.

Với lịch sử vào/ra nhiều lần, unique (team_id, user_id) **không còn phù hợp** nếu cho phép nhiều bản ghi theo thời gian. Có thể chuyển sang ID tự sinh cho từng lượt và thêm ràng buộc “tối đa một membership đang active” bằng partial unique index (nếu database hỗ trợ), hoặc đưa các lần tham gia vào bảng lịch sử riêng.

Như vậy **quy tắc nghiệp vụ của liên kết phải quyết định khóa và constraint**, không phải ngược lại.

## 19. API và DTO: bảo vệ thực thể liên kết khỏi sửa bừa

Một API thực tế có thể tổ chức:

| Hành động | Ý nghĩa nghiệp vụ |
|---|---|
| POST /orders | Tạo đơn nháp với danh sách productId và quantity |
| GET /orders/{id} | Trả DTO gồm các dòng, giá chốt và tổng tiền |
| PATCH /orders/{id}/items/{itemId} | Đổi quantity nếu đơn còn nháp |
| DELETE /orders/{id}/items/{itemId} | Bỏ dòng khỏi đơn nháp |
| POST /orders/{id}/confirm | Kiểm tra tồn kho và xác nhận một lần |

Không nhận nguyên một entity OrderItem từ JSON rồi **merge** trực tiếp. Client không được tự chỉ định:

- orderId của người khác,
- productId để thay mối liên kết lịch sử,
- unitPrice hoặc discount đã chốt nếu không được phép,
- trạng thái vượt qua workflow của order.

Ví dụ request DTO:

~~~java
public record ChangeQuantityRequest(int quantity) {}
~~~

Service lấy entity managed theo orderId/itemId đã kiểm quyền và gọi **changeQuantity()**. Với thao tác xóa, dùng business method **removeItem()** thay vì để client xóa cả graph bằng cách gửi một danh sách items bị thiếu phần tử.

Với request cập nhật danh sách, phải định nghĩa rõ:

1. **Replace toàn bộ:** phần tử vắng mặt trong payload sẽ bị xóa hoặc bỏ liên kết.
2. **Patch một phần:** phần tử vắng mặt giữ nguyên; chỉ những item được chỉ định mới thay đổi.

Nếu không phân biệt, code **clear() rồi addAll()** có thể xóa/tạo lại hàng loạt dòng, gây mất lịch sử hoặc vi phạm constraint. Association entity với ID riêng giúp thực hiện diff theo itemId và giữ lại các dòng chưa thay đổi.

## 20. Migration từ @ManyToMany sang association entity

Một hệ thống đang chạy có thể bắt đầu với bảng nối chỉ gồm **(order_id, product_id)** rồi mới phát sinh yêu cầu quantity và unitPrice. Việc chuyển đổi cần migration dữ liệu chứ không chỉ đổi annotation.

Ví dụ quy trình:

1. **Thêm cấu trúc mới**: tạo bảng order_items có id, hai FK, quantity, unit_price và unique constraint.
2. **Backfill** từng liên kết cũ thành OrderItem. Cần xác định quantity mặc định hợp lệ (ví dụ 1) và **nguồn giá lịch sử**. Nếu trước đây chưa lưu giá tại thời điểm mua, không thể khôi phục chính xác chỉ từ giá Product hiện tại; cần đánh dấu/đối chiếu nguồn khác thay vì bịa dữ liệu.
3. **Đọc song song/đối chiếu** số liên kết và kết quả query giữa cấu trúc cũ/mới trong giai đoạn chuyển tiếp nếu cần.
4. **Chuyển đường ghi** của ứng dụng sang OrderItem; cần cơ chế đồng bộ/backfill lần cuối nếu hệ thống vẫn nhận traffic trong thời gian chuyển đổi.
5. **Xóa mapping và bảng nối cũ** chỉ sau khi xác nhận dữ liệu và các caller đều dùng mô hình mới.

Với PostgreSQL, một minh họa backfill:

~~~sql
INSERT INTO order_items (order_id, product_id, quantity, unit_price)
SELECT op.order_id,
       op.product_id,
       1,
       p.current_price
FROM order_products op
JOIN products p ON p.id = op.product_id;
~~~

**Chỉ dùng dạng này nếu nghiệp vụ có cơ sở chấp nhận quantity = 1 và current_price làm giá tại thời điểm chuyển đổi.** Đối với hóa đơn lịch sử, việc dùng current_price rất có thể sai; cần giá chốt từ dữ liệu giao dịch hoặc đối soát thủ công. Trước khi chạy trên dữ liệu thật còn phải xét duplicate, NULL, foreign key, kích thước bảng, lock và khả năng rollback migration.

Trong production, Hibernate **ddl-auto=update** không phải chiến lược migration dữ liệu an toàn. Dùng Flyway/Liquibase và để Hibernate kiểm tra mapping khi phù hợp (**ddl-auto=validate**).

## 21. Kiểm thử association entity bằng database thực

Các test có giá trị nhất là **integration tests** trên cùng loại DB triển khai (ví dụ PostgreSQL qua Testcontainers) để chứng minh cascade, constraint, lazy loading và transaction.

### 21.1. Các tình huống cần chứng minh

| Tình huống | Kết quả mong muốn |
|---|---|
| Đơn mới có hai sản phẩm | 1 PurchaseOrder và 2 OrderItem; giá chốt đúng, tổng đúng |
| Một request có productId trùng | Service từ chối hoặc gộp theo rule đã chọn; ví dụ này từ chối |
| Hai request cố tạo dòng trùng trong cùng đơn | Unique constraint ở DB từ chối trạng thái trùng |
| Thay Product.currentPrice sau khi đặt | Giá trên OrderItem cũ và tổng đơn không đổi |
| Sửa quantity trên đơn nháp | Một dòng được UPDATE, tổng thay đổi tương ứng |
| Sửa/xóa dòng trên đơn đã xác nhận | Business method từ chối |
| Xóa một OrderItem bằng orphanRemoval | OrderItem biến mất; Product vẫn tồn tại |
| Một dòng lỗi giữa createDraft | Transaction rollback trọn vẹn |
| Tải chi tiết đơn | DTO đầy đủ và không phụ thuộc persistence context đã đóng |
| Hai đơn tranh sản phẩm cuối cùng | Không bán vượt tồn kho |
| Hai request xác nhận cùng một đơn | Không trừ kho hai lần |

### 21.2. Test mẫu: giá snapshot và vòng đời liên kết

~~~java
@SpringBootTest
class OrderItemIntegrationTest {
    @Autowired EntityManager em;
    @Autowired OrderApplicationService orderService;

    @Test
    void keepsHistoricalPriceAfterProductPriceChanges() {
        // Arrange: dùng fixture transaction riêng để tạo Customer, Product,
        // sau đó gọi createDraft với productId hợp lệ.
        // Act: đổi Product.currentPrice trong transaction khác.
        // Assert: OrderItem.unitPrice và tổng OrderDetailView không đổi.
    }

    @Test
    void removingLineDoesNotDeleteProduct() {
        // Arrange: tạo order nháp có một OrderItem.
        // Act: gọi removeLine(orderId, itemId), commit transaction.
        // Assert: OrderItem bị xóa, Product vẫn tồn tại.
    }
}
~~~

Đây là skeleton để định hướng bài test; cần import và setup fixture/test transactions trước khi chạy. Việc chỉ assert trên collection trong memory là chưa đủ: hãy **flush/commit, clear persistence context và truy vấn lại DB** để chứng minh dữ liệu thật đã thay đổi.

### 21.3. Quan sát SQL từ Hibernate

Với Spring Boot/Hibernate 6, ở môi trường local:

~~~yaml
spring:
  jpa:
    open-in-view: false
    show-sql: false
    properties:
      hibernate:
        format_sql: true
        generate_statistics: true

logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
~~~

Theo dõi SQL:

- Tạo đơn: INSERT order và các OrderItem, **không INSERT lại Product**.
- Sửa quantity: UPDATE đúng dòng cần thay đổi.
- Xóa dòng: DELETE OrderItem, không DELETE Product.
- Fetch một đơn: quan sát join và số hàng SQL.

Logger bind ở mức TRACE có thể ghi dữ liệu nhạy cảm, nên chỉ bật khi chẩn đoán tại môi trường phù hợp. SQL log là nguồn sự thật về DML phát sinh; không suy luận chỉ dựa trên số lần gọi **save()**.

## 22. Những lỗi thường gặp khi mô hình hóa entity liên kết

| Triệu chứng | Nguyên nhân có thể | Cách khắc phục |
|---|---|---|
| Muốn thêm quantity nhưng vẫn dùng @ManyToMany | Bảng nối bị giấu sau collection Product | Tạo association entity chứa quantity và hai @ManyToOne |
| Cùng sản phẩm xuất hiện nhiều dòng trong một đơn | Không có kiểm tra trùng hoặc unique constraint | Thêm UNIQUE(order_id, product_id) nếu nghiệp vụ yêu cầu |
| Giá hóa đơn cũ đổi khi thay giá catalog | Tính tổng dựa vào Product.currentPrice | Lưu snapshot unitPrice trên OrderItem |
| Thêm item vào List nhưng FK order_id null | Chỉ sửa phía mappedBy, chưa gán owning side | Helper method thiết lập OrderItem.order |
| Bỏ item khỏi List nhưng DB vẫn giữ item | Không có orphanRemoval hoặc chưa sửa owning side | Chọn đúng vòng đời child và thiết kế remove method |
| Xóa dòng làm mất Product | Cascade REMOVE/ALL sai hướng từ link sang entity độc lập | Không cascade xóa Product |
| Merge request DTO làm mất giá chốt/association | Merge detached graph với field null/thiếu | Load entity managed và gọi business method có chọn lọc |
| Set không xóa được item sau persist | equals/hashCode phụ thuộc ID chưa ổn định | Thiết kế identity nhất quán hoặc dùng List/helper theo ID |
| Truy vấn danh sách đơn quá nhiều SQL | Lazy N+1 trên items hoặc product | Projection, fetch plan/batch hợp lý và đo SQL |
| Collection JOIN FETCH kèm phân trang sai/chậm | Join nhân bản hàng của parent | Trang ID/projection trước, fetch chi tiết sau |
| Entity liên kết không lưu được sau create | Thiếu cascade persist hoặc thiếu persist rõ ràng | Xem lifecycle, owning side, transaction và SQL |
| Hai thao tác cùng sửa quantity ghi đè nhau | Thiếu optimistic/pessimistic concurrency policy | @Version trên entity phù hợp hoặc lock/use-case check |
| Không thể tạo lịch sử nhiều lần đăng ký | Khóa/unique chỉ cho một cặp user-course | Thiết kế identity theo từng lượt, thay đổi constraint |
| Schema Hibernate và production khác nhau | Chỉ đổi annotation mà không migration | Migration có phiên bản và kiểm thử trên database thật |

## 23. Bài thực hành tổng hợp

Hãy xây dựng một ứng dụng nhỏ với các bước sau, tập trung vào vòng đời và SQL của entity liên kết:

1. Tạo Customer, hai Product và một PurchaseOrder nháp.
2. Thêm hai OrderItem: bàn phím quantity 2 với giá chốt 250.000; chuột quantity 1 với giá chốt 120.000. Xác nhận tổng **620.000**.
3. Tăng giá bàn phím lên 300.000 rồi đọc đơn cũ. Giải thích vì sao tổng vẫn **620.000**.
4. Sửa quantity bàn phím trong đơn nháp thành 3, đọc log SQL và tính tổng mới **870.000** (3 × 250.000 + 120.000).
5. Thử thêm bàn phím lần thứ hai: service phải từ chối, database phải có unique constraint.
6. Xóa dòng chuột: kiểm tra DELETE trên order_items và đảm bảo Product chuột còn tồn tại.
7. Xác nhận đơn: khóa dữ liệu cần thiết, trừ tồn kho theo quantity, đổi status. Thử xác nhận lại và sửa dòng sau xác nhận; cả hai phải bị từ chối.
8. Tạo hai request cùng mua sản phẩm tồn kho 1; kiểm tra không có hai đơn đồng thời xác nhận thành công.
9. Viết JPQL tìm đơn chứa SKU, thống kê số lượng bán và tổng giá dòng; so sánh số SQL với cách duyệt entity trong Java.
10. Chọn lại khóa ghép cho một phiên bản thực nghiệm, thử **@EmbeddedId + @MapsId**, phân tích điều gì sẽ thay đổi ở API, unique constraint và trình tự persist.

Một kết quả hoàn chỉnh phải giải thích được **vì sao OrderItem có danh tính/thuộc tính/quy tắc riêng**, khóa ngoại nào sở hữu liên kết, khi nào Hibernate INSERT/UPDATE/DELETE OrderItem, và vì sao Product/Customer vẫn độc lập.

## 24. Các nguyên tắc mang sang những domain khác

Khi gặp quan hệ đa trị, hãy đặt các câu hỏi:

1. **Mối quan hệ có thuộc tính không?** Nếu cần quantity, role, enrolledAt, effectiveFrom, grade, status, unitPrice, association entity thường là một lựa chọn tốt.
2. **Mối quan hệ có quy tắc riêng không?** Nếu có quyền chuyển trạng thái, thay đổi, gia hạn, hoàn trả hoặc audit, hãy diễn đạt bằng business method trên association entity hoặc aggregate sở hữu.
3. **Identity của một liên kết là gì?** Cặp FK có thật sự duy nhất trong mọi thời điểm hay quan hệ có nhiều lần/phân đoạn lịch sử? Chọn surrogate ID hoặc composite ID tương ứng.
4. **Nếu bỏ liên kết, entity nào cần còn sống?** Tách rõ xóa association với xóa một entity dùng chung. Cascade và orphanRemoval phải phản ánh vòng đời nghiệp vụ.
5. **Giá trị nào phải được chốt theo giao dịch?** Không đọc lại giá hay quy tắc hiện hành để tính dữ liệu lịch sử nếu nghiệp vụ yêu cầu bất biến.
6. **Ai được quyền thay đổi?** Đặt transaction và validation ở use case, dùng helper method đồng bộ hai phía quan hệ, để DB constraint bảo vệ cuộc đua giữa nhiều giao dịch.
7. **Truy vấn này cần bao nhiêu dữ liệu?** Association entity tạo khả năng query/projection tốt, nhưng vẫn phải kiểm soát LAZY, N+1 và phân trang.

**Một bảng nối trở thành thực thể liên kết khi chính mối quan hệ có ý nghĩa nghiệp vụ.** Việc thay @ManyToMany bằng OrderItem, Enrollment hoặc Membership làm rõ dữ liệu cần lưu, quy tắc cần giữ và vòng đời cần quản lý. Hibernate ánh xạ mô hình ấy sang relational database; tính đúng đắn vẫn phụ thuộc thiết kế aggregate, khóa/constraint, transaction và cách ứng dụng sử dụng entity.

# Thiết kế một persistence unit cho một mô hình dữ liệu

Một ứng dụng Java dùng JPA cần một nơi xác định **những entity nào thuộc cùng một vùng quản lý**, **provider nào thực thi ánh xạ**, **kết nối dữ liệu được lấy ở đâu** và **transaction được quản lý theo cách nào**. Tập hợp cấu hình logic đó được gọi là **persistence unit** (đơn vị persistence).

Bài này thiết kế một persistence unit hoàn chỉnh cho mô hình đặt hàng đơn giản, từ ranh giới nghiệp vụ, quan hệ giữa các entity và cấu trúc bảng cho đến cấu hình `persistence.xml`, khởi tạo `EntityManagerFactory`, thực hiện transaction và các quyết định khi đưa vào ứng dụng Spring.

## 1. Persistence unit là gì?

Trong Jakarta Persistence (thường vẫn gọi là JPA), **persistence unit** là một tập các lớp có thể được quản lý theo mô hình persistence và cấu hình liên quan để provider tạo ra một `EntityManagerFactory`. Mỗi persistence unit được nhận diện bằng một tên, ví dụ `shopPU`.

Có thể hình dung mối liên hệ:

~~~text
Một ứng dụng Java
    |
    +-- Persistence unit: shopPU
           |
           +-- Entity: Customer
           +-- Entity: Product
           +-- Entity: PurchaseOrder
           +-- Entity: OrderLine
           |
           +-- JPA provider: Hibernate ORM
           +-- Cấu hình database / DataSource
           +-- Kiểu transaction: RESOURCE_LOCAL hoặc JTA
           |
           +-- EntityManagerFactory (dùng chung)
                  |
                  +-- EntityManager #1 -> persistence context #1
                  +-- EntityManager #2 -> persistence context #2
                  +-- ...
~~~

Bốn khái niệm dễ nhầm có nhiệm vụ khác nhau:

| Khái niệm | Nhiệm vụ |
|---|---|
| **Persistence unit** | Định nghĩa tập entity được quản lý và cấu hình persistence thống nhất |
| **EntityManagerFactory** | Được tạo cho một persistence unit; là đối tượng tương đối tốn chi phí khởi tạo, có thể dùng chung giữa nhiều luồng |
| **EntityManager** | Điểm vào để `find`, `persist`, `remove`, tạo truy vấn; **không dùng chung đồng thời giữa nhiều luồng** |
| **Persistence context** | Theo dõi tập entity managed, danh tính đối tượng và các thay đổi cần đồng bộ trong phạm vi của nó |

Persistence unit **không đồng nghĩa với một bảng**: một đơn vị thường quản lý nhiều entity có quan hệ với nhau. Nó cũng **không nhất thiết tương ứng một database vật lý**; cấu hình có thể trỏ đến một schema hoặc nguồn dữ liệu thích hợp. Ngược lại, việc khai báo nhiều persistence unit không tự động tạo transaction thống nhất hoặc quan hệ JPA xuyên qua các đơn vị đó.

### Kết quả cần đạt khi thiết kế

Sau khi thiết kế xong, phải trả lời được:

1. Bài toán nghiệp vụ và phạm vi entity nào cùng thuộc một persistence unit?
2. Các quan hệ một-nhiều, nhiều-một, khóa và ràng buộc được biểu diễn thế nào?
3. Ai quản lý transaction, JPA provider nào được dùng, kết nối database cấu hình ra sao?
4. Khi ứng dụng chạy, một thao tác nghiệp vụ tạo ra những entity managed nào, và khi nào dữ liệu được lưu?
5. Nếu mô hình thay đổi, quản lý migration và phạm vi persistence context như thế nào?

## 2. Bài toán mẫu: quản lý đơn đặt hàng

Giả sử cần xây dựng một phần của hệ thống bán hàng với các yêu cầu:

- Khách hàng có thể đặt nhiều đơn hàng.
- Mỗi đơn hàng thuộc về đúng một khách hàng.
- Một đơn hàng có nhiều dòng hàng; mỗi dòng ghi một sản phẩm, số lượng và **đơn giá tại thời điểm đặt hàng**.
- Một sản phẩm có thể xuất hiện trong nhiều đơn hàng.
- Giá sản phẩm có thể thay đổi trong danh mục, nhưng tổng tiền của đơn đã đặt phải được tính từ giá được chốt ở các dòng hàng.
- Trong ví dụ này, khách hàng và sản phẩm đã tồn tại trước khi tạo đơn; chức năng tồn kho, thanh toán và giao hàng nằm ngoài phạm vi.

Từ yêu cầu đó, chọn bốn entity:

| Entity Java | Bảng database | Ý nghĩa | Thuộc tính cốt lõi |
|---|---|---|---|
| `Customer` | `customers` | Khách mua hàng | `id`, `email`, `fullName` |
| `Product` | `products` | Danh mục sản phẩm | `id`, `sku`, `name`, `unitPrice` |
| `PurchaseOrder` | `purchase_orders` | Thông tin một đơn đặt hàng | `id`, `customer`, `orderedAt` |
| `OrderLine` | `order_lines` | Một dòng trong đơn hàng | `id`, `order`, `product`, `quantity`, `unitPriceAtPurchase` |

Chọn tên `PurchaseOrder` và bảng `purchase_orders` để tránh xung đột với từ khóa SQL `ORDER`.

### 2.1. Mối quan hệ dữ liệu

~~~mermaid
erDiagram
    CUSTOMER ||--o{ PURCHASE_ORDER : "dat"
    PURCHASE_ORDER ||--|{ ORDER_LINE : "gom"
    PRODUCT ||--o{ ORDER_LINE : "duoc-mua-trong"

    CUSTOMER {
        bigint id PK
        varchar email UK
        varchar full_name
    }
    PRODUCT {
        bigint id PK
        varchar sku UK
        varchar name
        decimal unit_price
    }
    PURCHASE_ORDER {
        bigint id PK
        bigint customer_id FK
        timestamp ordered_at
    }
    ORDER_LINE {
        bigint id PK
        bigint order_id FK
        bigint product_id FK
        int quantity
        decimal unit_price_at_purchase
    }
~~~

Ở mức thiết kế nghiệp vụ, mỗi đơn được tạo cùng ít nhất một dòng hàng. Sơ đồ biểu diễn ràng buộc đó; để cưỡng chế quy tắc “ít nhất một dòng” thường cần logic nghiệp vụ hoặc ràng buộc nâng cao vì một khóa ngoại thông thường không tự bảo đảm bảng cha có ít nhất một bản ghi con.

Cần phân biệt hai quan hệ:

- `PurchaseOrder → OrderLine` là quan hệ **sở hữu vòng đời**: một dòng hàng tồn tại để mô tả một đơn cụ thể. Khi xóa dòng khỏi đơn, có thể xóa hẳn dòng tương ứng.
- `OrderLine → Product` là quan hệ **tham chiếu**: xóa dòng hàng không được xóa sản phẩm trong danh mục.

Đây là căn cứ quan trọng để quyết định cascade và orphan removal ở bước ánh xạ JPA.

### 2.2. Chọn ranh giới persistence unit

Bốn entity cùng phục vụ một luồng nghiệp vụ: tạo đơn, đọc đơn và xem giá đã chốt. Ta gom chúng vào **một persistence unit tên `shopPU`** vì:

- Một thao tác tạo đơn cần truy cập `Customer`, `Product`, `PurchaseOrder` và `OrderLine` trong cùng transaction.
- Các quan hệ dùng khóa ngoại nằm trong cùng cơ sở dữ liệu quan hệ.
- Các entity có thể được quản lý trong cùng một persistence context, cho phép provider duy trì tính nhất quán của đối tượng managed.
- Mô hình đủ gắn kết để có thể triển khai và tiến hóa schema thống nhất.

Không tạo một persistence unit riêng cho mỗi entity. Nếu sau này tách một hệ thống billing dùng database khác, quyết định tách persistence unit phải xét ranh giới transaction, quyền sở hữu dữ liệu và cách giao tiếp giữa các hệ thống; không chỉ vì muốn chia package Java.

## 3. Thiết kế ánh xạ các entity

Ví dụ dùng **Jakarta Persistence 3.x**, import từ `jakarta.persistence.*`, Java có hỗ trợ `BigDecimal` và `Instant`, và một JPA provider như Hibernate ORM. Đặt các lớp trong package `com.example.shop.domain`.

### 3.1. Customer: entity độc lập

~~~java
package com.example.shop.domain;

import jakarta.persistence.*;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 255)
    private String email;

    @Column(name = "full_name", nullable = false, length = 160)
    private String fullName;

    protected Customer() {
        // JPA cần constructor không tham số (public hoặc protected).
    }

    public Customer(String email, String fullName) {
        this.email = email;
        this.fullName = fullName;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getFullName() {
        return fullName;
    }
}
~~~

Các quyết định:

- `@Entity` xác định đây là một entity do provider quản lý.
- `@Table` đặt tên bảng rõ ràng.
- `@Id` xác định danh tính entity; `IDENTITY` yêu cầu cơ chế sinh khóa tương ứng của database.
- Email có ràng buộc duy nhất ở mức ánh xạ; cần tạo ràng buộc **UNIQUE thực sự** trong schema để ngăn dữ liệu trùng khi có concurrent transactions.

Ở ví dụ này, `Customer` không cần giữ một `List<PurchaseOrder>`. Chỉ khai báo quan hệ một chiều từ đơn hàng đến khách hàng sẽ đơn giản hơn nếu không có nhu cầu điều hướng từ khách hàng sang các đơn.

### 3.2. Product: giá hiện tại trong danh mục

~~~java
package com.example.shop.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 50)
    private String sku;

    @Column(nullable = false, length = 200)
    private String name;

    @Column(name = "unit_price", nullable = false, precision = 12, scale = 2)
    private BigDecimal unitPrice;

    protected Product() {}

    public Product(String sku, String name, BigDecimal unitPrice) {
        this.sku = sku;
        this.name = name;
        this.unitPrice = unitPrice;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }
}
~~~

Dùng `BigDecimal` và kiểu SQL `NUMERIC/DECIMAL` cho tiền, tránh sai số biểu diễn nhị phân thường gặp với `float`/`double`. Mô hình dùng một đơn vị tiền tệ thống nhất để giữ ví dụ gọn; nếu hỗ trợ nhiều loại tiền tệ, phải thêm mã tiền tệ và quy tắc làm tròn rõ ràng.

Không đặt cascade từ `OrderLine` sang `Product`: sản phẩm là dữ liệu danh mục tồn tại độc lập với đơn.

### 3.3. PurchaseOrder: gốc quản lý các dòng hàng

~~~java
package com.example.shop.domain;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Column(name = "ordered_at", nullable = false)
    private Instant orderedAt;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public PurchaseOrder(Customer customer, Instant orderedAt) {
        this.customer = customer;
        this.orderedAt = orderedAt;
    }

    public void addLine(Product product, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải dương");
        }

        OrderLine line = new OrderLine(
            this,
            product,
            quantity,
            product.getUnitPrice()
        );
        lines.add(line);
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
~~~

Ý nghĩa các annotation quan hệ:

- `@ManyToOne` biểu thị nhiều đơn hàng tham chiếu đến một khách hàng.
- `@JoinColumn(name = "customer_id")` ánh xạ thuộc tính Java sang cột khóa ngoại.
- `@OneToMany(mappedBy = "order")` nói rằng phía `OrderLine.order` nắm cột khóa ngoại; phía `PurchaseOrder.lines` là phía nghịch đảo của quan hệ.
- `cascade = CascadeType.ALL` cho phép thao tác persistence/lifecycle từ đơn hàng lan sang **dòng hàng** của nó. Trong ứng dụng cụ thể có thể giới hạn cascade vào những thao tác cần thiết.
- `orphanRemoval = true` cho phép xóa entity con khi nó bị loại khỏi quan hệ sở hữu. Ví dụ chỉ cung cấp thao tác thêm dòng; nếu bổ sung thao tác xóa dòng, cần giữ hai phía của quan hệ đồng bộ.

Dùng `FetchType.LAZY` cho quan hệ many-to-one để tránh tải khách hàng không cần thiết khi đọc một đơn. Trong JPA, lazy loading ở quan hệ đơn là một gợi ý theo khả năng provider; nên kiểm tra hành vi thực tế.

Trong mô hình này, `PurchaseOrder` quản lý tập `OrderLine` như một aggregate ở tầng nghiệp vụ. Khái niệm aggregate thuộc thiết kế domain; annotation JPA chỉ cung cấp các cơ chế giúp biểu diễn quan hệ và vòng đời.

### 3.4. OrderLine: entity con với giá chốt

~~~java
package com.example.shop.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;

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
        name = "unit_price_at_purchase",
        nullable = false,
        precision = 12,
        scale = 2
    )
    private BigDecimal unitPriceAtPurchase;

    protected OrderLine() {}

    OrderLine(
        PurchaseOrder order,
        Product product,
        int quantity,
        BigDecimal unitPriceAtPurchase
    ) {
        this.order = order;
        this.product = product;
        this.quantity = quantity;
        this.unitPriceAtPurchase = unitPriceAtPurchase;
    }

    public BigDecimal lineTotal() {
        return unitPriceAtPurchase.multiply(BigDecimal.valueOf(quantity));
    }

    public Product getProduct() {
        return product;
    }

    public int getQuantity() {
        return quantity;
    }
}
~~~

Khi thêm dòng hàng, `OrderLine` giữ tham chiếu đến cả đơn và sản phẩm. **Phía `OrderLine.order` là phía sở hữu quan hệ trong JPA**, vì chính bảng `order_lines` có cột `order_id`; việc thêm đối tượng vào `PurchaseOrder.lines` đồng thời với thiết lập `order` giúp hai phía nhất quán.

Giá mua được sao chép tại thời điểm tạo dòng. Nếu giá danh mục sau này đổi từ 100.000 thành 120.000, giá trên đơn cũ không tự đổi theo. Đây là một quyết định nghiệp vụ độc lập với chuyện đơn và sản phẩm cùng thuộc persistence unit.

> Mã mẫu tập trung vào ánh xạ và vòng đời JPA. Hệ thống thật thường cần bổ sung xác thực dữ liệu đầu vào, quy tắc giá/thuế, tính đồng thời, và quyết định khi khách hàng hay sản phẩm bị vô hiệu hóa.

## 4. Thiết kế schema vật lý

Annotation mô tả ánh xạ giữa Java và database; schema thực tế cần có bảng, khóa, ràng buộc và chỉ mục tương thích. Ví dụ sau dùng **PostgreSQL** và cú pháp identity column của PostgreSQL:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    full_name VARCHAR(160) NOT NULL
);

CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL,
    CONSTRAINT ck_products_price_nonnegative CHECK (unit_price >= 0)
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(id),
    ordered_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_orders(id),
    product_id BIGINT NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL,
    unit_price_at_purchase NUMERIC(12, 2) NOT NULL,
    CONSTRAINT ck_order_lines_quantity_positive CHECK (quantity > 0),
    CONSTRAINT ck_order_lines_price_nonnegative
        CHECK (unit_price_at_purchase >= 0)
);

CREATE INDEX idx_orders_customer ON purchase_orders(customer_id);
CREATE INDEX idx_lines_order ON order_lines(order_id);
CREATE INDEX idx_lines_product ON order_lines(product_id);
~~~

Thiết kế này cần hai mức bảo vệ:

1. **Ở domain/service**, không tạo đơn rỗng, số lượng âm hoặc giá không hợp lệ. Ví dụ `addLine` đã từ chối số lượng không dương.
2. **Ở database**, ràng buộc `NOT NULL`, `UNIQUE`, `FOREIGN KEY` và `CHECK` bảo vệ dữ liệu ngay cả khi có nhiều chương trình cùng ghi.

Không phải mọi ràng buộc ở database đều biểu diễn được bằng annotation JPA chuẩn. Ví dụ `CHECK` và chỉ mục có thể được quản lý trực tiếp bằng migration. Các cột thời gian như `Instant` cần được kiểm tra tương thích giữa provider, JDBC driver và kiểu cột; với PostgreSQL, `TIMESTAMP WITH TIME ZONE` phù hợp với nhu cầu lưu mốc thời gian tuyệt đối trong ví dụ này.

**Thực hành triển khai:** dùng Flyway, Liquibase hoặc cơ chế migration tương đương để áp dụng schema theo phiên bản. Tránh mặc định tự động cập nhật bảng từ entity khi vận hành production; một migration có thể được kiểm soát, review và phục hồi rõ hơn.

## 5. Tạo persistence unit bằng persistence.xml

Với ứng dụng Java SE dùng JPA trực tiếp, có thể đặt file cấu hình tại:

~~~text
shop-app/
├── src/main/java/
│   └── com/example/shop/
│       ├── domain/
│       │   ├── Customer.java
│       │   ├── Product.java
│       │   ├── PurchaseOrder.java
│       │   └── OrderLine.java
│       └── App.java
└── src/main/resources/
    └── META-INF/
        └── persistence.xml
~~~

Khi build, `META-INF/persistence.xml` phải nằm trên **runtime classpath** để JPA tìm thấy persistence unit.

### 5.1. Cấu hình mẫu cho Java SE và Hibernate

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/persistence
        https://jakarta.ee/xml/ns/persistence/persistence_3_1.xsd"
    version="3.1">

    <persistence-unit name="shopPU" transaction-type="RESOURCE_LOCAL">
        <provider>org.hibernate.jpa.HibernatePersistenceProvider</provider>

        <class>com.example.shop.domain.Customer</class>
        <class>com.example.shop.domain.Product</class>
        <class>com.example.shop.domain.PurchaseOrder</class>
        <class>com.example.shop.domain.OrderLine</class>

        <exclude-unlisted-classes>true</exclude-unlisted-classes>

        <properties>
            <property
                name="jakarta.persistence.jdbc.driver"
                value="org.postgresql.Driver" />
            <property
                name="jakarta.persistence.jdbc.url"
                value="jdbc:postgresql://localhost:5432/shopdb" />
            <property
                name="jakarta.persistence.jdbc.user"
                value="shop_app" />

            <property name="hibernate.hbm2ddl.auto" value="validate" />
        </properties>
    </persistence-unit>
</persistence>
~~~

Cấu hình này cố ý không để mật khẩu trong XML: ứng dụng sẽ lấy từ biến môi trường và đưa vào lúc tạo factory. Với production, thường ưu tiên DataSource có connection pool và secret manager của môi trường chạy.

| Thành phần cấu hình | Ý nghĩa thiết kế |
|---|---|
| `name="shopPU"` | Định danh duy nhất để mã Java chọn persistence unit cần khởi tạo |
| `transaction-type="RESOURCE_LOCAL"` | Ứng dụng tự quản lý transaction qua `EntityTransaction` |
| `provider` | Chỉ định Hibernate làm JPA provider thực thi |
| Các thẻ `class` | Liệt kê chính xác những entity thuộc persistence unit |
| `exclude-unlisted-classes=true` | Không dựa vào quét tự động những entity chưa liệt kê |
| `jakarta.persistence.jdbc.*` | Thông tin JDBC cơ bản cho kết nối |
| `hibernate.hbm2ddl.auto=validate` | Tùy chọn **riêng của Hibernate** để kiểm tra schema lúc khởi động, không tự tạo/cập nhật bảng |

Để ví dụ chạy được, cần khai báo dependencies tương thích với thế hệ API đang dùng, tối thiểu là **JPA provider (Hibernate ORM)** và **JDBC driver PostgreSQL**. Trong Maven/Gradle, nên quản lý các phiên bản theo dependency management hoặc BOM phù hợp; nếu dùng Jakarta Persistence 3.x, tránh vô tình trộn các thư viện dùng `javax.persistence.*` cũ.

**Không suy ra rằng `persistence.xml` luôn bắt buộc**: trong Spring Boot, persistence unit và EntityManagerFactory thường được Spring Boot tự cấu hình từ datasource, entity scanning và properties. Phần này chủ động dùng XML để thấy đầy đủ một persistence unit chứa những gì.

### 5.2. RESOURCE_LOCAL hay JTA?

Trong ví dụ Java SE này, chọn `RESOURCE_LOCAL` vì thao tác đơn hàng diễn ra trên một nguồn dữ liệu quan hệ và ứng dụng tự điều khiển transaction:

~~~text
EntityManager.getTransaction()
        |
       begin
        |
   persist / query
        |
  commit / rollback
~~~

Khi chạy trong container hoặc môi trường có transaction manager hỗ trợ JTA, persistence unit có thể dùng `transaction-type="JTA"` và một `jta-data-source` do môi trường cấp. Khi đó transaction manager kiểm soát transaction; không viết code `em.getTransaction().begin()` theo ví dụ RESOURCE_LOCAL.

| Khía cạnh | RESOURCE_LOCAL | JTA |
|---|---|---|
| Ai điều khiển transaction? | Ứng dụng/JPA qua `EntityTransaction` | Transaction manager của môi trường |
| Nguồn dữ liệu điển hình | Một DB và một transaction tại một thời điểm | Nguồn dữ liệu được quản lý, có thể tham gia transaction phân tán nếu được cấu hình hỗ trợ |
| Cách bắt đầu/commit | `begin()`/`commit()` | Cơ chế quản lý transaction của framework/container |
| Phù hợp bài này? | Có, khi chạy Java SE đơn giản | Chỉ khi đã có hạ tầng JTA thích hợp |

**JTA không tự động bảo đảm hai hệ thống bất kỳ sẽ cùng commit**. Transaction phân tán cần sự tham gia của resource và cấu hình transaction manager tương ứng. Với dịch vụ tách database và giao tiếp qua mạng, thường còn phải xem xét outbox, saga hoặc mô hình nhất quán khác thay vì giả định JPA tự giải quyết.

## 6. Khởi tạo EntityManagerFactory và thực hiện một transaction

### 6.1. Tạo factory cho đúng persistence unit

Trong ứng dụng Java SE, có thể khởi tạo factory như sau:

~~~java
package com.example.shop;

import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.Persistence;
import java.util.Map;
import java.util.Objects;

public final class App {
    public static void main(String[] args) {
        String password = Objects.requireNonNull(
            System.getenv("SHOP_DB_PASSWORD"),
            "Cần đặt biến môi trường SHOP_DB_PASSWORD"
        );

        EntityManagerFactory emf = Persistence.createEntityManagerFactory(
            "shopPU",
            Map.of("jakarta.persistence.jdbc.password", password)
        );

        try {
            Long orderId = new OrderService(emf).placeOrder(1L, 10L, 2);
            System.out.println("Đã tạo đơn #" + orderId);
        } finally {
            emf.close();
        }
    }
}
~~~

Tên `shopPU` trong lời gọi factory **phải khớp** với thuộc tính `name` trong XML. Hãy tạo một `EntityManagerFactory` cho persistence unit khi ứng dụng khởi động và đóng khi ứng dụng dừng; không tạo một factory mới cho mỗi request.

Đoạn code giả định database đã có một khách hàng `id = 1` và một sản phẩm `id = 10`. Các ID này chỉ phục vụ ví dụ, không phải giá trị có sẵn ở mọi cơ sở dữ liệu.

### 6.2. Viết use case tạo đơn

~~~java
package com.example.shop;

import com.example.shop.domain.Customer;
import com.example.shop.domain.Product;
import com.example.shop.domain.PurchaseOrder;
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;
import java.time.Instant;

public class OrderService {
    private final EntityManagerFactory emf;

    public OrderService(EntityManagerFactory emf) {
        this.emf = emf;
    }

    public Long placeOrder(
        Long customerId,
        Long productId,
        int quantity
    ) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải dương");
        }

        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        try {
            tx.begin();

            Customer customer = em.find(Customer.class, customerId);
            Product product = em.find(Product.class, productId);

            if (customer == null || product == null) {
                throw new IllegalArgumentException(
                    "Không tìm thấy khách hàng hoặc sản phẩm"
                );
            }

            PurchaseOrder order = new PurchaseOrder(
                customer,
                Instant.now()
            );
            order.addLine(product, quantity);

            em.persist(order); // Cascade PERSIST xuống các OrderLine.
            tx.commit();

            return order.getId();
        } catch (RuntimeException ex) {
            if (tx.isActive()) {
                tx.rollback();
            }
            throw ex;
        } finally {
            em.close();
        }
    }
}
~~~

Phân tích theo thứ tự dữ liệu thay đổi:

1. `createEntityManager()` tạo một context làm việc; `begin()` mở transaction.
2. `em.find(Customer.class, ...)` và `em.find(Product.class, ...)` tìm entity. Nếu tồn tại, chúng trở thành managed trong persistence context của `em`.
3. `new PurchaseOrder(...)` và `new OrderLine(...)` ban đầu chỉ là đối tượng Java mới.
4. `em.persist(order)` yêu cầu quản lý đơn hàng mới; cascade `PERSIST` kéo các dòng hàng vào context. Quan hệ tới `Customer` và `Product` chỉ được tham chiếu, không cascade persist tới chúng.
5. Provider đồng bộ entity mới thành các câu `INSERT`. Thời điểm SQL được thực thi có thể trước lúc commit, đặc biệt với `GenerationType.IDENTITY` khi cần nhận ID.
6. `tx.commit()` xác nhận transaction. Nếu thao tác lỗi, `rollback()` hủy các thay đổi thuộc transaction đó.
7. `em.close()` giải phóng context; `EntityManagerFactory` vẫn dùng được cho các lần gọi sau.

**Không dùng cùng một `EntityManager` đồng thời cho nhiều request/thread.** Factory có thể dùng chung; mỗi transaction hoặc đơn vị công việc nên có phạm vi `EntityManager` phù hợp. Entity đã detached sau khi context đóng không còn tự động được theo dõi thay đổi bởi context cũ.

### 6.3. Khi nào dữ liệu được ghi?

Phân biệt ba mốc:

- **`persist()`**: đưa entity mới vào trạng thái managed và lên lịch thao tác chèn, với những ngoại lệ có thể thực hiện SQL sớm.
- **`flush()`**: đồng bộ trạng thái persistence context thành SQL; **không đồng nghĩa** với transaction đã commit.
- **`commit()`**: xác nhận transaction sau khi các thao tác cần thiết hoàn tất; lỗi có thể dẫn đến rollback.

Nếu dùng khóa `IDENTITY`, provider có thể chèn hàng sớm để lấy khóa sinh từ database. Không nên suy luận rằng mọi câu `INSERT` chỉ xuất hiện ở dòng `tx.commit()`.

## 7. Đọc dữ liệu và thiết kế chiến lược fetch

Một persistence unit giúp provider biết cách quản lý các mối quan hệ, nhưng **không bảo đảm cách tải dữ liệu luôn tối ưu**.

Ví dụ chỉ đọc thông tin đơn:

~~~java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
~~~

Vì `PurchaseOrder.customer` được khai báo LAZY và `PurchaseOrder.lines` là quan hệ to-many, việc đọc thêm khách hàng hoặc dòng hàng có thể tạo các truy vấn tiếp theo. Với Hibernate, truy cập quan hệ lazy sau khi `EntityManager` đóng có thể gây `LazyInitializationException`.

Nếu màn hình chi tiết đơn cần thông tin khách hàng và toàn bộ dòng hàng, có thể chủ động fetch trong transaction:

~~~java
PurchaseOrder order = em.createQuery(
        """
        SELECT DISTINCT o
        FROM PurchaseOrder o
        JOIN FETCH o.customer
        LEFT JOIN FETCH o.lines
        WHERE o.id = :id
        """,
        PurchaseOrder.class
    )
    .setParameter("id", orderId)
    .getResultStream()
    .findFirst()
    .orElseThrow(() ->
        new IllegalArgumentException("Không tìm thấy đơn hàng")
    );
~~~

Ở đây JPQL dùng **tên entity Java**, không phải bảng `purchase_orders`. `JOIN FETCH` và `LEFT JOIN FETCH` yêu cầu tải các quan hệ ngay trong truy vấn. Sản phẩm của từng dòng vẫn có thể cần truy vấn riêng khi truy cập vì `OrderLine.product` đang LAZY; nếu cần các thông tin sản phẩm, phải thiết kế truy vấn/projection phù hợp.

Không áp dụng fetch join collection một cách máy móc cho trang danh sách đơn có phân trang: tập kết quả SQL có thể bị nhân số hàng, dẫn đến phân trang không hiệu quả hoặc hành vi phụ thuộc provider. Với API danh sách lớn, projection/DTO hoặc truy vấn nhiều bước thường dễ kiểm soát hơn.

### 7.1. Transaction, danh tính entity và dirty checking

Trong cùng persistence context, nếu hai lần `find` cùng khóa entity đều trả về một bản ghi managed, JPA đảm bảo tính nhất quán của danh tính entity trong context đó. Điều này giúp xử lý quan hệ không tạo nhiều bản sao managed khác nhau cho cùng một ID.

Nếu thay đổi thuộc tính trên entity managed trong transaction, provider theo dõi và đồng bộ thay đổi tương ứng khi flush (*dirty checking*). Tuy nhiên, khi object đã detached, thay đổi trong Java không tự biến thành SQL; cần tải lại managed entity hoặc xử lý merge một cách có chủ đích.

### 7.2. Tính đồng thời

Khi nhiều request có thể thay đổi cùng một bản ghi, nên cân nhắc **optimistic locking** với `@Version` hoặc cơ chế khóa khác. Ví dụ entity sản phẩm có số lượng tồn kho sẽ cần quy tắc cập nhật đồng thời chặt chẽ hơn dữ liệu danh mục chỉ để đọc.

Ví dụ bài này **không** mô hình hóa trừ tồn kho, nên không đưa ra cam kết rằng chỉ nhờ một persistence unit thì hệ thống đã xử lý được mọi race condition. Persistence unit tập hợp cấu hình persistence; ràng buộc nghiệp vụ và chiến lược đồng thời vẫn phải thiết kế riêng.

## 8. Tổ chức persistence unit trong ứng dụng Spring Boot

Trong Spring Boot, cách thường gặp là khai báo datasource và để framework tạo `EntityManagerFactory`, persistence unit và transaction manager thích hợp. Với Hibernate làm provider, có thể cấu hình:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/shopdb
    username: ${SHOP_DB_USER}
    password: ${SHOP_DB_PASSWORD}
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Các entity vẫn dùng annotation JPA như ở trên. Khi đặt chúng trong vùng package được Spring Boot quét, ứng dụng thường không cần thêm `META-INF/persistence.xml`. Nếu entity ở package khác, cần cấu hình entity scanning (ví dụ `@EntityScan`). Đây là **cách cấu hình thay thế** cho ví dụ Java SE ở mục 5–6; không nên mặc định chép cả hai cấu hình vào một ứng dụng mà không hiểu cơ chế tạo factory.

Với Spring Data JPA, có thể khai báo:

~~~java
package com.example.shop.repository;

import com.example.shop.domain.PurchaseOrder;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
}
~~~

Hoặc nếu muốn trực tiếp dùng `EntityManager` mà vẫn để Spring quản lý transaction:

~~~java
@Service
public class SpringOrderService {
    @PersistenceContext
    private EntityManager em;

    @Transactional
    public Long placeOrder(Long customerId, Long productId, int quantity) {
        Customer customer = em.find(Customer.class, customerId);
        Product product = em.find(Product.class, productId);

        if (customer == null || product == null) {
            throw new IllegalArgumentException("Thiếu dữ liệu tham chiếu");
        }

        PurchaseOrder order = new PurchaseOrder(customer, Instant.now());
        order.addLine(product, quantity);
        em.persist(order);
        return order.getId();
    }
}
~~~

Ví dụ Spring phía trên giả định đã import các kiểu liên quan, dùng `@Service` của Spring, `@PersistenceContext` của Jakarta Persistence và `@Transactional` của Spring. Transaction được Spring mở/commit qua proxy gọi service, vì vậy **không tự gọi `em.getTransaction()`** trong phương thức này. Cần gọi thông qua bean Spring đúng cách để transaction advice được áp dụng.

Dù dùng cách cấu hình nào, mô hình vẫn là:

~~~text
Business service
    |
    +-- EntityManager (API JPA) hoặc Repository (Spring Data JPA)
          |
          +-- EntityManagerFactory / Persistence unit
                |
                +-- Provider: Hibernate
                      |
                      +-- JDBC -> PostgreSQL
~~~

Trong ứng dụng Spring có nhiều datasource hoặc nhiều persistence unit, phải khai báo rõ entity package, factory, transaction manager và repository thuộc đơn vị nào. Không giả định rằng `@Transactional` sẽ tự kết hợp transaction của tất cả các database.

## 9. Khi nào cần một hay nhiều persistence unit?

**Một persistence unit** thường phù hợp khi các entity dùng cùng provider/cấu hình persistence, chung một vùng transaction và một nguồn dữ liệu quan hệ. Ví dụ `Customer`, `PurchaseOrder`, `OrderLine` và `Product` ở bài này.

**Nhiều persistence unit** có thể hợp lý khi:

- Ứng dụng thực sự dùng hai database với thông tin kết nối và chu kỳ vận hành độc lập, ví dụ `salesPU` và `reportingPU`.
- Hai nhóm entity cần thiết lập provider hoặc quyền truy cập khác nhau.
- Một hệ thống legacy cần tách bối cảnh persistence của các module trong giai đoạn chuyển đổi.

Tuy nhiên, cần chú ý:

| Lựa chọn | Hệ quả |
|---|---|
| Một persistence unit với nhiều entity | Dễ điều hướng quan hệ JPA, quản lý entity cùng một context/transaction khi dùng cùng `EntityManager` |
| Hai persistence unit trên hai datasource | Mỗi unit có factory/context riêng; không tạo quan hệ JPA trực tiếp xuyên unit |
| Hai persistence unit cùng một database | Vẫn là hai phạm vi quản lý entity độc lập; không vì dùng chung DB mà context tự hòa làm một |
| Transaction cần cập nhật nhiều nguồn dữ liệu | Cần chiến lược transaction và nhất quán riêng; JTA chỉ khả thi khi toàn bộ hạ tầng tham gia hỗ trợ đúng |

Khi chia persistence unit, tránh đặt cùng một kiểu entity vào nhiều context rồi giả định các đối tượng cùng định danh sẽ là một Java object thống nhất. Mỗi persistence context quản lý danh tính và thay đổi theo phạm vi của chính nó.

## 10. Các lỗi thiết kế thường gặp và cách nhận biết

### 10.1. Không tìm thấy persistence unit

Triệu chứng: provider không tìm thấy `shopPU` khi gọi `Persistence.createEntityManagerFactory("shopPU")`.

Nguyên nhân cần xem:

- Tên gọi không khớp `persistence-unit name="shopPU"`.
- `META-INF/persistence.xml` không được đưa lên runtime classpath.
- Thiếu JPA provider hoặc không tương thích phiên bản API với provider.
- XML sai namespace/version/schema.

### 10.2. “Not a managed type” hoặc “Unknown entity”

Thường xảy ra khi một class được dùng trong repository/query nhưng không thuộc tập entity được factory quản lý. Kiểm tra `@Entity`, danh sách `<class>`, `exclude-unlisted-classes` và cấu hình entity scanning.

**Cùng package Java không có nghĩa tự động được nhận diện** nếu persistence unit đang bật cơ chế liệt kê tường minh và loại trừ unlisted classes.

### 10.3. Trùng lặp hoặc mất đồng bộ quan hệ hai chiều

Nếu chỉ sửa `order.getLines()` mà quên thiết lập `line.order`, phía sở hữu khóa ngoại không đúng như mong muốn. Dùng phương thức domain như `addLine(...)` để cập nhật cả collection và thuộc tính `order`. Không đặt `CascadeType.REMOVE` từ `OrderLine` sang `Product`, vì một dòng hàng bị xóa không được làm mất dữ liệu danh mục.

### 10.4. Không có transaction hoặc lạm dụng EntityManager

Trong ứng dụng Java SE với `RESOURCE_LOCAL`, thao tác ghi cần transaction phù hợp. Lỗi `TransactionRequiredException` có thể xuất hiện khi gọi một thao tác yêu cầu transaction mà transaction chưa hoạt động. Dùng chung một `EntityManager` cho nhiều request cũng có thể gây lỗi trạng thái và vấn đề an toàn luồng.

### 10.5. Cấu hình schema không tương thích

`@GeneratedValue(strategy = IDENTITY)` phải phù hợp cách database sinh khóa. Kiểu `BigDecimal`/`NUMERIC` cần đồng bộ precision và scale. `Instant` và kiểu timestamp cần cách lưu timezone nhất quán. Lỗi kiểm tra schema lúc khởi động có thể là dấu hiệu migration chưa chạy hoặc mapping/schema không đồng bộ.

### 10.6. Quan hệ LAZY bị truy cập quá muộn

Khi `EntityManager` đã đóng, việc mở thêm một quan hệ lazy chưa được tải có thể không thực hiện được. Tránh trả trực tiếp entity ra bên ngoài rồi dựa vào việc JSON serializer tự lấy mọi quan hệ. Hãy chủ động chọn fetch plan và chuyển thành DTO trong transaction.

### 10.7. Chạy SQL quá nhiều dù chỉ gọi một repository

Một câu lệnh JPA không đồng nghĩa với một câu SQL. Chẳng hạn truy cập 100 đơn hàng rồi lần lượt lấy dòng hàng của từng đơn có thể tạo dạng truy vấn N+1. Cần quan sát SQL log, execution plan và số lượt DB round-trip trước khi chọn fetch join, entity graph, batch fetching hoặc DTO.

## 11. Quy trình thực hiện khi thiết kế một persistence unit mới

Có thể áp dụng quy trình sau cho một dự án thực tế:

1. **Xác định use case và transaction boundary.** Những thông tin nào phải được đọc/ghi cùng nhau? Ví dụ tạo đơn cần khách hàng, sản phẩm, đơn và các dòng hàng.
2. **Chọn ranh giới mô hình entity.** Xác định entity nào có vòng đời độc lập, entity nào phụ thuộc entity cha, entity nào chỉ là tham chiếu.
3. **Vẽ lược đồ quan hệ.** Định nghĩa khóa chính, khóa ngoại, unique, nullable, kiểu tiền tệ/thời gian, chỉ mục và ràng buộc nghiệp vụ.
4. **Ánh xạ JPA.** Chọn `@Entity`, `@Id`, `@ManyToOne`, `@OneToMany`, `mappedBy`, `cascade`, `orphanRemoval` và chiến lược fetch có chủ đích.
5. **Chọn cấu hình persistence unit.** Đặt tên, chọn provider, liệt kê/quét entity, chọn DataSource và RESOURCE_LOCAL/JTA dựa trên môi trường chạy.
6. **Triển khai schema migration.** Đảm bảo database thật tương thích với mapping, không phụ thuộc vào thao tác cập nhật schema không kiểm soát.
7. **Thiết kế phạm vi context và transaction.** Sử dụng factory dài hạn, context theo đơn vị công việc, commit/rollback rõ ràng.
8. **Thiết kế cách đọc dữ liệu.** Mỗi use case xác định fetch plan, DTO/projection và giới hạn phân trang phù hợp.
9. **Chuẩn bị cho thay đổi.** Quy hoạch versioning/migration, đồng thời, logging truy vấn và tách persistence unit nếu ranh giới dữ liệu thực sự thay đổi.

### Bài tập mở rộng

Với mô hình ở trên, thử bổ sung ba yêu cầu:

- **Một đơn có nhiều sản phẩm:** dùng `PurchaseOrder.addLine(...)` nhiều lần, rồi kiểm tra cách `cascade` lưu các dòng hàng trong cùng transaction.
- **Lấy lịch sử đơn của khách hàng:** viết JPQL truy vấn `PurchaseOrder` theo `customer.id`, có sắp xếp theo `orderedAt` và phân trang; không bắt buộc thêm `List<PurchaseOrder>` vào entity khách hàng.
- **Đơn đã đặt không được sửa giá:** tiếp tục lưu `unitPriceAtPurchase`, đồng thời quyết định trường hợp chỉnh sửa dòng, hủy đơn, giảm giá hoặc áp mã khuyến mãi trong domain mà không dựa vào giá hiện tại của `Product`.

Một persistence unit tốt là một ranh giới cấu hình phù hợp với **mô hình dữ liệu và transaction thực tế**: nó gom những entity cần được provider quản lý thống nhất, chỉ rõ kết nối/transaction, và giúp mã Java làm việc thông qua `EntityManager` hoặc repository mà vẫn giữ nguyên các ràng buộc của cơ sở dữ liệu.

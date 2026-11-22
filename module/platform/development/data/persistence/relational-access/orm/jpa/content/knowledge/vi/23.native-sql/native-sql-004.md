# Ánh xạ native query về entity với đủ thông tin cần thiết trong JPA

**Native SQL** cho phép ứng dụng JPA viết câu lệnh SQL theo bảng, cột và cú pháp của database thay vì biểu diễn truy vấn bằng JPQL hoặc Criteria API. Điều này rất hữu ích khi cần dùng tính năng đặc thù của cơ sở dữ liệu, tối ưu truy vấn phức tạp hoặc đọc từ những cấu trúc khó diễn đạt bằng JPQL. Nhưng một câu SQL trả về dữ liệu **chưa tự động trở thành một entity hợp lệ trong JPA**.

Muốn JPA dựng một entity từ kết quả native query, ResultSet phải chứa **đầy đủ thông tin mà mapping của entity cần**, đặc biệt là **định danh**, các cột persistent và những cột dùng để giải quyết quan hệ hoặc cơ chế kế thừa/phiên bản. Khi các cột SQL được đổi alias, hoặc query trả nhiều loại kết quả, cần chỉ định ánh xạ phù hợp, chẳng hạn `@SqlResultSetMapping`, `@EntityResult`, `@FieldResult` hoặc DTO projection.

Ví dụ đơn giản:

```java
List<Product> products = entityManager
    .createNativeQuery(
        """
        SELECT
            p.id,
            p.sku,
            p.display_name,
            p.unit_price,
            p.product_status,
            p.version,
            p.created_at
        FROM catalog_product p
        WHERE p.product_status = ?1
        """,
        Product.class
    )
    .setParameter(1, "ACTIVE")
    .getResultList();
```

Ở đây `Product.class` yêu cầu JPA ánh xạ mỗi dòng kết quả thành entity `Product`. Điều kiện quan trọng là những cột ResultSet cung cấp phải tương thích với các cột được mapping trong `Product`. Việc thêm `Product.class` **không thể tự bù các cột đã bị bỏ khỏi SELECT**.

Bài học thuộc chương **Native SQL** của module *Data Persistence Relational Access ORM JPA*. Nội dung tập trung vào nhận diện thế nào là “đủ thông tin để dựng entity”, cách dùng `createNativeQuery` và `@SqlResultSetMapping`, xử lý alias/join/inheritance/composite key, trạng thái managed entity và các lỗi thực tế.

---

## 1. Native query khác JPQL ở cấp độ nào?

Giả sử có entity:

```java
@Entity
@Table(name = "catalog_product")
public class Product {

    @Id
    private Long id;

    @Column(name = "display_name")
    private String name;
}
```

**JPQL** sử dụng entity name và thuộc tính Java:

```jpql
select p
from Product p
where p.name = :name
```

**Native SQL** sử dụng table name và column name:

```sql
SELECT p.id, p.display_name
FROM catalog_product p
WHERE p.display_name = ?;
```

So sánh:

| Vấn đề | JPQL | Native SQL |
|---|---|---|
| Nguồn trong `FROM` | Entity `Product` | Bảng `catalog_product` |
| Thuộc tính cần lọc | `p.name` | `p.display_name` |
| Provider tạo SQL? | Có, dựa vào mapping | SQL cơ bản do ứng dụng viết |
| Có thể trả entity managed? | Có | Có, **khi cấu hình ánh xạ kết quả đúng** |
| Tính độc lập database | Cao hơn trong phạm vi JPQL chuẩn | Phụ thuộc dialect, driver và schema |
| SQL-specific syntax | Bị giới hạn bởi JPQL/provider | Sử dụng được theo database hỗ trợ |
| Cần biết tên cột vật lý? | Thường không | Có |
| Vấn đề thiếu cột mapped | Provider quản lý cách SELECT | **Ứng dụng phải đặc biệt chú ý** |

JPA provider vẫn quản lý persistence context, entity identity và lifecycle đối với native query trả entity. Vì vậy một entity do native query trả về **không phải một POJO tùy ý được tạo bằng constructor rồi điền field**, mà phải tuân theo mapping JPA.

## 2. Mô hình dùng xuyên suốt bài học

Giả sử hệ thống bán hàng có ba entity:

- `Product` — sản phẩm trong danh mục.
- `Customer` — khách hàng.
- `SalesOrder` — đơn hàng, có quan hệ nhiều-một tới Customer.

Một bảng `order_line` còn liên kết đơn hàng với sản phẩm, giúp minh họa JOIN và aggregate.

### 2.1. Schema SQL minh họa

```sql
CREATE TABLE catalog_product (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(64) NOT NULL UNIQUE,
    display_name VARCHAR(200) NOT NULL,
    unit_price DECIMAL(18,2) NOT NULL,
    product_status VARCHAR(20) NOT NULL,
    version BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE crm_customer (
    id BIGINT PRIMARY KEY,
    email_address VARCHAR(254) NOT NULL UNIQUE,
    display_name VARCHAR(200) NOT NULL
);

CREATE TABLE sales_order (
    id BIGINT PRIMARY KEY,
    order_no VARCHAR(64) NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL,
    order_status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(18,2) NOT NULL,
    version BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id)
        REFERENCES crm_customer(id)
);

CREATE TABLE order_line (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_line_order
        FOREIGN KEY (order_id) REFERENCES sales_order(id),
    CONSTRAINT fk_line_product
        FOREIGN KEY (product_id) REFERENCES catalog_product(id)
);
```

DDL trên mang tính giáo dục. Cú pháp identity/sequence, kiểu `TIMESTAMP` và giới hạn số liệu có thể khác giữa PostgreSQL, MySQL, Oracle, SQL Server và các database khác. Với dự án thực tế, mapping phải khớp schema được migration quản lý.

Sơ đồ:

```text
        crm_customer                  catalog_product
        +-----------------+           +------------------+
        | id (PK)         |           | id (PK)          |
        | email_address   |           | sku              |
        | display_name    |           | display_name     |
        +--------+--------+           | unit_price       |
                 |                    | product_status   |
                 | 1:N                | version          |
                 v                    | created_at       |
           sales_order                +--------+---------+
           +-----------------+                 |
           | id (PK)         |                 | 1:N
           | order_no        |                 |
           | customer_id FK  |                 |
           | order_status    |                 |
           | total_amount    |                 |
           | version         |                 |
           | created_at      |                 |
           +--------+--------+                 |
                    |                          |
                    | 1:N                      |
                    v                          v
                  order_line ------------------+
                  +---------------------+
                  | id (PK)             |
                  | order_id (FK)       |
                  | product_id (FK)     |
                  | quantity            |
                  +---------------------+
```

### 2.2. Entity Product

```java
package com.example.shop.persistence;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(name = "catalog_product")
public class Product {

    @Id
    private Long id;

    @Column(nullable = false, unique = true, length = 64)
    private String sku;

    @Column(name = "display_name", nullable = false)
    private String name;

    @Column(name = "unit_price", nullable = false)
    private BigDecimal price;

    @Enumerated(EnumType.STRING)
    @Column(name = "product_status", nullable = false)
    private ProductStatus status;

    @Version
    private Long version;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected Product() {
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public ProductStatus getStatus() {
        return status;
    }

    public Long getVersion() {
        return version;
    }
}
```

Với enum:

```java
package com.example.shop.persistence;

public enum ProductStatus {
    ACTIVE,
    INACTIVE,
    DISCONTINUED
}
```

Để tập trung vào **đọc từ native query**, ví dụ không trình bày constructor tạo mới và chiến lược sinh ID. Một ứng dụng tạo Product bằng `persist` có thể bổ sung constructor nghiệp vụ, ID strategy và validation phù hợp.

Bảy cột persistent cần đặc biệt chú ý trong entity mẫu là:

| Java attribute | Database column | Vai trò |
|---|---|---|
| `id` | `id` | Primary key, xác định entity identity |
| `sku` | `sku` | Business key |
| `name` | `display_name` | Thuộc tính String |
| `price` | `unit_price` | Thuộc tính BigDecimal |
| `status` | `product_status` | Enum ánh xạ dưới dạng String |
| `version` | `version` | Optimistic locking metadata |
| `createdAt` | `created_at` | Thời điểm tạo |

### 2.3. Entity Customer và SalesOrder

```java
@Entity
@Table(name = "crm_customer")
public class Customer {

    @Id
    private Long id;

    @Column(name = "email_address", nullable = false)
    private String email;

    @Column(name = "display_name", nullable = false)
    private String name;

    protected Customer() {
    }
}
```

```java
@Entity(name = "SalesOrder")
@Table(name = "sales_order")
public class SalesOrder {

    @Id
    private Long id;

    @Column(name = "order_no", nullable = false)
    private String orderNumber;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Enumerated(EnumType.STRING)
    @Column(name = "order_status", nullable = false)
    private OrderStatus status;

    @Column(name = "total_amount", nullable = false)
    private BigDecimal totalAmount;

    @Version
    private Long version;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected SalesOrder() {
    }
}
```

`SalesOrder.customer` là association; trong SQL, nó được biểu diễn bằng cột khóa ngoại `sales_order.customer_id`. Để JPA dựng đúng SalesOrder từ native SQL, không được tùy tiện bỏ cột khóa ngoại này chỉ vì Java không khai báo một field riêng tên `customerId`.

## 3. Cách đơn giản nhất: createNativeQuery(sql, Entity.class)

JPA hỗ trợ:

```java
Query query = em.createNativeQuery(sql, Product.class);
```

Với câu SELECT có đủ các cột của Product:

```java
String sql = """
    SELECT
        p.id,
        p.sku,
        p.display_name,
        p.unit_price,
        p.product_status,
        p.version,
        p.created_at
    FROM catalog_product p
    WHERE p.product_status = ?1
    ORDER BY p.id
    """;

@SuppressWarnings("unchecked")
List<Product> products = em
    .createNativeQuery(sql, Product.class)
    .setParameter(1, "ACTIVE")
    .getResultList();
```

Phân tích:

1. `createNativeQuery(...)` nhận **SQL thật**: bảng `catalog_product`, cột `display_name`.
2. `Product.class` yêu cầu kết quả được dựng theo metadata của entity Product.
3. `?1` là tham số vị trí được bind bằng `setParameter(1, ...)`.
4. `getResultList()` trả danh sách kết quả.
5. Khi entity được load trong persistence context đang hoạt động, nó tham gia cơ chế **managed identity** của JPA.

### 3.1. Vì sao có @SuppressWarnings("unchecked")?

Ở các API JPA truyền thống, `EntityManager.createNativeQuery` trả `Query` chứ không luôn trả một `TypedQuery<Product>` theo generic signature giống `createQuery(JPQL, Product.class)`. Do đó compiler có thể cảnh báo unchecked conversion khi gán vào `List<Product>`.

`@SuppressWarnings("unchecked")` không có chức năng kiểm tra mapping. Nó chỉ triệt cảnh báo compile trong đoạn code mà lập trình viên đã chọn đúng `resultClass` và kiểm soát kết quả.

### 3.2. Entity được tạo bằng phản chiếu hay constructor nghiệp vụ?

Provider dùng cơ chế instantiation và hydration phù hợp với JPA mapping, chứ không gọi constructor nghiệp vụ của Product để đảm bảo rằng mọi field được gán qua setter công khai. Entity cần constructor không tham số public/protected theo quy tắc entity thông thường và mapping hợp lệ.

Không nên nhầm việc ResultSet có các cột với “JPA chắc chắn gọi setter tương ứng”: điều đó phụ thuộc **field access hoặc property access** của entity.

### 3.3. Có thể SELECT p.* không?

Ví dụ:

```java
List<?> products = em.createNativeQuery(
    "SELECT p.* FROM catalog_product p",
    Product.class
).getResultList();
```

Với bảng đơn và ánh xạ trực tiếp, `p.*` thường là cách thực dụng để lấy mọi cột hiện có. Nhưng:

- Khi thêm `JOIN` hoặc truy vấn nhiều bảng, `*` có thể gây trùng tên cột.
- Khi mapping dùng `@SecondaryTable` hoặc inheritance, `p.*` có thể không đủ thông tin.
- Khi schema thêm cột mới, query có thể trả dữ liệu không cần thiết.
- Nếu mapping yêu cầu alias hoặc cột đặc biệt, `SELECT *` không tự giải quyết.
- Với các truy vấn cần API ổn định, danh sách cột rõ ràng giúp kiểm soát chi phí và contract tốt hơn.

**Định hướng:** Query trả entity hãy ưu tiên **đúng và đủ các cột mà mapping cần**, rồi tối ưu có đo đạc; không coi `SELECT *` là bảo đảm portable trong mọi mô hình.

## 4. “Đủ thông tin cần thiết” nghĩa là những gì?

Khi `resultClass` là entity, không chỉ primary key cần được chọn. Cần xét toàn bộ mapping có ảnh hưởng đến việc provider dựng entity và quản lý state.

| Nhóm dữ liệu | Vì sao cần chú ý |
|---|---|
| Primary key `@Id` / `@EmbeddedId` | Xác định entity identity; phân biệt row và quản lý first-level cache |
| Thuộc tính persistent cơ bản | Provider cần dữ liệu tương ứng để hydrate state theo mapping |
| Thuộc tính `@Version` | Hỗ trợ optimistic locking/phiên bản |
| Cột FK thuộc association | Cho provider xác định reference/relationship theo mapping |
| Các cột thuộc embedded component | Đảm bảo giá trị nhúng được dựng đúng |
| Discriminator cho entity inheritance | Có thể cần xác định subclass cụ thể |
| Cột ánh xạ ở secondary table | Có thể cần nếu mapping/phương thức hydrate phụ thuộc những field đó |
| Formula/converter/provider-specific mappings | Cần thỏa hợp đồng mapping mà provider thực sự hỗ trợ |
| Tên/alias cột ResultSet | Phải khớp mapping mặc định hoặc ánh xạ tường minh `@FieldResult` |

Một tiêu chí thực dụng:

> **Nếu bạn yêu cầu native query trả một entity đầy đủ, hãy chọn các cột mà entity mapping cần để hydrate entity ấy đúng cách.** Không sử dụng một SELECT “chỉ vài cột hiển thị trên màn hình” rồi gắn `Entity.class` và kỳ vọng provider tự hiểu các field bị thiếu.

Tùy provider, việc bỏ cột bắt buộc có thể gây exception, trả state không được xác định portable, hoặc tạo tác dụng phụ khi load sau đó. Vì vậy **không dựa vào hành vi thành công tình cờ của một phiên bản Hibernate/EclipseLink** để xem partial entity loading là đúng chuẩn.

## 5. Thiếu primary key: lỗi cơ bản nhất

Sai về ý định ánh xạ:

```java
String sql = """
    SELECT
        sku,
        display_name,
        unit_price
    FROM catalog_product
    """;

em.createNativeQuery(sql, Product.class)
    .getResultList();
```

Dù dữ liệu đủ để hiển thị một ô sản phẩm trên UI, query **không trả `id`**. Provider thiếu thông tin nhận diện một Product duy nhất trong persistence context.

Hậu quả có thể là lỗi “column id not found”, lỗi hydrate entity, hoặc hành vi không portable khác. Không nên chờ provider tự suy ra ID từ SKU, dù SKU có unique constraint.

### 5.1. Business key không thay @Id

`sku` có thể unique trong database, nhưng JPA mapping đã chọn:

```java
@Id
private Long id;
```

Vì vậy ID của entity vẫn là `id`; không thể bỏ cột này chỉ vì `sku` là khóa nghiệp vụ.

### 5.2. Chọn đúng primary key

```sql
SELECT
    id,
    sku,
    display_name,
    unit_price,
    product_status,
    version,
    created_at
FROM catalog_product;
```

Đây là hướng đúng cho ví dụ Product: mỗi row cung cấp ID và các cột persistent mà mapping cần.

### 5.3. Không cố gán ID giả

Không dùng:

```sql
SELECT
    0 AS id,
    sku,
    display_name,
    ...
FROM catalog_product;
```

để “lấp chỗ thiếu”. Nếu mọi row có ID bằng 0, JPA có thể xem nhiều dòng là cùng một persistent identity. Điều đó làm sai entity identity và có thể gây kết quả kỳ lạ ngay cả khi SQL trả nhiều rows.

## 6. Thiếu thuộc tính bình thường cũng là vấn đề

Một trường hợp dễ bỏ qua:

```java
String sql = """
    SELECT
        id,
        sku,
        display_name
    FROM catalog_product
    """;

em.createNativeQuery(sql, Product.class).getResultList();
```

Mặc dù có ID, query vẫn thiếu:

- `unit_price`.
- `product_status`.
- `version`.
- `created_at`.

Nếu mục tiêu chỉ là danh sách ID/SKU/tên, bạn **không cần entity Product đầy đủ**; nên chọn projection DTO hoặc scalar query.

### 6.1. Không dùng “default Java value” để che thiếu cột

Giả sử entity có primitive:

```java
private int quantity;
```

Nếu SELECT không trả cột quantity, không được giả định JPA sẽ hiểu quantity = 0 là dữ liệu thật. Đó có thể là default value do Java instance chưa được điền đúng, không phải giá trị database.

Tương tự, String null có thể là “không có thông tin trong ResultSet”, không nhất thiết là DB column thực sự NULL.

### 6.2. Không dùng @Transient để né trách nhiệm mapping

Nếu một field chỉ dành cho UI, không nên bắt nó làm persistent attribute:

```java
@Transient
private String displayBadge;
```

`@Transient` nói JPA không ánh xạ field này. Nhưng không thêm `@Transient` vào những field thật sự cần lưu chỉ để native SELECT ít cột hơn. Quyết định persistent model phải theo domain, không theo một truy vấn báo cáo.

## 7. @Version: vì sao không nên bỏ qua?

Product có:

```java
@Version
private Long version;
```

Khi JPA quản lý entity, `version` là một phần cơ chế optimistic locking. Câu native query trả Product nên chứa cột `version` được ánh xạ:

```sql
SELECT
    id,
    sku,
    display_name,
    unit_price,
    product_status,
    version,
    created_at
FROM catalog_product;
```

Nếu bỏ version, provider có thể không đủ dữ liệu quản lý snapshot/version đúng cách. Không nên kỳ vọng entity với version bị thiếu vẫn cập nhật an toàn.

### 7.1. Không dùng số version cố định

```sql
SELECT
    id,
    sku,
    display_name,
    unit_price,
    product_status,
    0 AS version,
    created_at
FROM catalog_product;
```

Đây không phải cách thay thế version thật. Nếu version trong database đã tăng lên 7, một entity được hydrate với version giả 0 không phản ánh trạng thái thực và có thể gây lỗi đồng bộ về sau.

### 7.2. Kết quả managed có thể đã nằm trong persistence context

Ngay cả khi native SELECT trả đúng version, nếu entity cùng ID đang managed trong persistence context, JPA có thể trả lại managed instance đó với state hiện có. Native query **không tự là lệnh refresh** toàn bộ state đã được quản lý.

Muốn đảm bảo đọc lại dữ liệu mới nhất theo ngữ nghĩa thích hợp, cần xem `EntityManager.refresh`, `clear` hoặc mở context/transaction mới, đồng thời hiểu database isolation và concurrent updates.

## 8. Enum, converter và dữ liệu SQL phải khớp mapping

`Product.status` được khai báo:

```java
@Enumerated(EnumType.STRING)
@Column(name = "product_status")
private ProductStatus status;
```

Database lưu `ACTIVE`, `INACTIVE` hoặc `DISCONTINUED`. Native SELECT phải trả giá trị database tương ứng với enum mapping đó.

```sql
SELECT
    id,
    sku,
    display_name,
    unit_price,
    product_status,
    version,
    created_at
FROM catalog_product
WHERE product_status = ?;
```

Khi bind một tham số của **native SQL**, một giá trị String tương ứng cột SQL thường dễ kiểm soát:

```java
query.setParameter(1, "ACTIVE");
```

Đừng tự giả định native SQL parameter binding luôn có cùng type inference như JPQL khi truyền `ProductStatus.ACTIVE`. Khả năng provider chuyển enum trong native parameter có thể khác theo implementation; dùng kiểu SQL column hoặc mapping rõ ràng theo môi trường.

### 8.1. AttributeConverter

Nếu entity có:

```java
@Convert(converter = MoneyCodeConverter.class)
private MoneyCode moneyCode;
```

thì khi entity được hydrate đúng theo mapping, provider áp converter tương ứng. Nhưng native SQL trả scalar `money_code` không nhất thiết áp dụng toàn bộ entity converter như khi trả managed entity.

Cần phân biệt:

- **Native result mapped to entity**: JPA mapping điều khiển hydration.
- **Native scalar projection**: kiểu dữ liệu thường phụ thuộc JDBC/`@ColumnResult`/provider, không tự là domain value object.

### 8.2. SQL expression có thể phá kiểu dữ liệu

```sql
SELECT
    id,
    sku,
    display_name,
    CAST(unit_price AS VARCHAR) AS unit_price,
    product_status,
    version,
    created_at
FROM catalog_product;
```

Nếu `unit_price` bị ép sang String, trong khi entity mapping kỳ vọng `BigDecimal`, quá trình hydrate có thể lỗi hoặc phụ thuộc chuyển kiểu của JDBC/provider.

Chỉ đổi biểu thức/kiểu dữ liệu khi bạn biết rõ mục đích và đã có mapping kết quả phù hợp.

## 9. Association @ManyToOne: không bỏ cột khóa ngoại

SalesOrder có:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "customer_id", nullable = false)
private Customer customer;
```

Một câu native SQL trả SalesOrder đầy đủ nên cung cấp `customer_id`:

```java
String sql = """
    SELECT
        o.id,
        o.order_no,
        o.customer_id,
        o.order_status,
        o.total_amount,
        o.version,
        o.created_at
    FROM sales_order o
    WHERE o.order_status = ?1
    """;

@SuppressWarnings("unchecked")
List<SalesOrder> orders = em
    .createNativeQuery(sql, SalesOrder.class)
    .setParameter(1, "PAID")
    .getResultList();
```

`customer_id` là thông tin để provider xác định Customer reference. Không cần tải toàn bộ cột Customer chỉ để ánh xạ association tới Customer.

### 9.1. Không có Java field customerId thì sao?

Entity chỉ khai báo:

```java
private Customer customer;
```

chứ không khai báo:

```java
private Long customerId;
```

Điều đó **không có nghĩa native query có thể bỏ customer_id**. Cột FK vẫn được mapping bởi `@JoinColumn`.

### 9.2. LAZY không có nghĩa không cần FK

`FetchType.LAZY` điều chỉnh việc tải association khi thực sự cần. Nó không biến dữ liệu nhận diện relationship thành tùy chọn khi hydrate entity owner theo mapping.

Provider có thể tạo reference hoặc proxy cho Customer dựa vào FK, rồi tải thêm dữ liệu khi truy cập association trong context phù hợp.

### 9.3. Nếu SELECT chỉ có customer_id nhưng không có Order columns?

```sql
SELECT customer_id FROM sales_order;
```

Đây là query scalar hợp lệ, nhưng **không phải** query trả một `SalesOrder` managed hoàn chỉnh. Khi chỉ cần ID khách hàng, nhận scalar result hoặc DTO thay vì `SalesOrder.class`.

## 10. JOIN nhiều bảng và lỗi tên cột trùng nhau

Trường hợp nguy hiểm:

```sql
SELECT o.*, c.*
FROM sales_order o
JOIN crm_customer c
  ON c.id = o.customer_id;
```

Cả `sales_order` và `crm_customer` đều có cột tên `id`. ResultSet có thể chứa hai cột cùng label `id`, làm ánh xạ mặc định trở nên mơ hồ. Những cột khác như `display_name` hoặc `created_at` cũng có thể trùng trong schema lớn.

Không nên viết:

```java
em.createNativeQuery(
    "SELECT o.*, c.* FROM sales_order o JOIN crm_customer c ON ...",
    SalesOrder.class
);
```

rồi mặc định JPA sẽ chọn đúng cột ID và mọi FK mà không có alias rõ ràng.

### 10.1. Nếu chỉ muốn SalesOrder, chọn cột của SalesOrder

```sql
SELECT
    o.id,
    o.order_no,
    o.customer_id,
    o.order_status,
    o.total_amount,
    o.version,
    o.created_at
FROM sales_order o
JOIN crm_customer c
  ON c.id = o.customer_id
WHERE c.email_address = ?;
```

Query JOIN Customer chỉ để **lọc** Order theo email. ResultSet chỉ có các cột mapped của SalesOrder, nên mapping về `SalesOrder.class` rõ ràng hơn.

### 10.2. JOIN không tự fetch Customer thành managed entity trong result

Vì SQL có:

```sql
JOIN crm_customer c ON ...
```

không có nghĩa JPA tự tạo cả `SalesOrder` và `Customer` managed nếu `resultClass` chỉ là `SalesOrder.class`. Những gì được trả và hydrate phụ thuộc result mapping.

Nếu muốn hai entity từ cùng một SQL row, cần kết quả mapping nhiều entity và alias cột không xung đột, hoặc dùng phương án fetch phù hợp hơn (JPQL `JOIN FETCH`, EntityGraph, query riêng).

### 10.3. Tại sao SELECT o.* thường an toàn hơn SELECT * ở đây?

`o.*` chỉ chọn các cột của bảng Order, giảm xung đột tên với Customer. Nhưng vẫn cần đánh giá:

- `o.*` có cung cấp tất cả cột mapping của SalesOrder không?
- Có `@SecondaryTable` hay inheritance không?
- Có provider-specific fields/formulas/discriminators không?
- Các tên cột và kiểu có đúng với mapping không?

`SELECT o.*` là một công cụ hữu ích, **không phải phép đảm bảo tuyệt đối**.

## 11. Alias SQL: khi nào ánh xạ mặc định đủ và khi nào không?

Giả sử SQL trả alias:

```sql
SELECT
    p.id AS product_id,
    p.sku AS product_sku,
    p.display_name AS product_title,
    p.unit_price AS product_price,
    p.product_status AS product_state,
    p.version AS product_version,
    p.created_at AS product_created
FROM catalog_product p;
```

Các label trong ResultSet giờ là:

```text
product_id
product_sku
product_title
product_price
product_state
product_version
product_created
```

Chúng **không còn trùng với tên cột** mà Product mapping mặc định chờ nhận, chẳng hạn `id`, `display_name` hoặc `unit_price`. Nếu chỉ truyền `Product.class`, cách provider đối chiếu label có thể thất bại.

**Giải pháp:** Dùng `@SqlResultSetMapping` và `@FieldResult` để mô tả alias nào cấp dữ liệu cho thuộc tính nào.

### 11.1. Đặt alias rõ để tránh xung đột

Viết:

```sql
p.id AS product_id
```

giúp tránh nhầm với:

```sql
c.id AS customer_id
```

khi query có nhiều entity. Nhưng **chỉ đổi alias trong SQL vẫn chưa ánh xạ tự động alias ấy sang field Java** nếu chúng khác column mapping. Phải có result mapping hoặc query shape tương thích.

### 11.2. Không trộn ba loại tên

| Loại tên | Ví dụ | Vai trò |
|---|---|---|
| Java attribute | `name` | Thuộc tính entity Product |
| Mapped database column | `display_name` | Cột trong bảng catalog_product |
| SQL result alias | `product_title` | Label của giá trị trả về trong ResultSet |

`@FieldResult(name = "name", column = "product_title")` dùng **attribute name** ở `name` và **SQL result alias** ở `column`. Đây là chỗ dễ nhầm nhất khi viết custom mapping.

## 12. @SqlResultSetMapping và @EntityResult: ánh xạ alias về entity

JPA cung cấp annotation:

- `@SqlResultSetMapping` — đặt tên cho cấu hình ánh xạ ResultSet.
- `@EntityResult` — chỉ định entity class được tạo từ row.
- `@FieldResult` — ánh xạ một thuộc tính persistent tới một cột/alias ResultSet.
- `@ColumnResult` — ánh xạ giá trị scalar.
- `@ConstructorResult` — dựng DTO bằng constructor.

Với SQL dùng alias `product_id`, `product_title`..., ta thêm mapping **trên một entity phù hợp**:

```java
@SqlResultSetMapping(
    name = "ProductAliasMapping",
    entities = @EntityResult(
        entityClass = Product.class,
        fields = {
            @FieldResult(name = "id", column = "product_id"),
            @FieldResult(name = "sku", column = "product_sku"),
            @FieldResult(name = "name", column = "product_title"),
            @FieldResult(name = "price", column = "product_price"),
            @FieldResult(name = "status", column = "product_state"),
            @FieldResult(name = "version", column = "product_version"),
            @FieldResult(name = "createdAt", column = "product_created")
        }
    )
)
@Entity
@Table(name = "catalog_product")
public class Product {
    // Giữ nguyên các @Id/@Column/@Version field ở phần trên.
}
```

Chú ý mapping ở ví dụ:

- `@FieldResult(name="name", ...)` chỉ **Java field name** `name`.
- `column="product_title"` chỉ **result-set alias**, không phải `@Column(name="display_name")`.
- ID, version và mọi basic persistent attributes của Product được đưa vào.
- Khi alias bị đổi trong SQL, phải đồng bộ `@FieldResult(column=...)`.
- Mẫu này minh họa annotation đặt trên entity; trong file nguồn thực tế, đừng tạo một lớp Product trùng tên — hãy gắn annotation vào lớp Product đã có.

Thực thi:

```java
String sql = """
    SELECT
        p.id AS product_id,
        p.sku AS product_sku,
        p.display_name AS product_title,
        p.unit_price AS product_price,
        p.product_status AS product_state,
        p.version AS product_version,
        p.created_at AS product_created
    FROM catalog_product p
    WHERE p.sku = ?1
    """;

@SuppressWarnings("unchecked")
List<Product> results = em
    .createNativeQuery(sql, "ProductAliasMapping")
    .setParameter(1, "BOOK-001")
    .getResultList();
```

Đối số thứ hai giờ là **tên SQL result set mapping**, không phải `Product.class`.

### 12.1. Khi nào @FieldResult không cần thiết?

Nếu các column labels của SELECT đã trùng tên mapped columns được provider kỳ vọng và không có ambiguity, có thể chỉ cần:

```java
em.createNativeQuery(sql, Product.class)
```

hoặc một entity mapping mặc định đơn giản mà không khai báo từng field alias.

Đừng tạo hàng chục `@FieldResult` khi một câu SELECT đơn bảng có thể đáp ứng mapping mặc định rõ ràng. Mục đích của explicit mapping là giải quyết **khác biệt alias/kết quả phức tạp**, không phải một nghi thức bắt buộc cho mọi native query.

### 12.2. Những gì FieldResult không làm

`@FieldResult` không:

- Tự đổi schema database.
- Tạo thuộc tính Java mới.
- Biến một scalar thiếu ID thành entity hợp lệ.
- Bảo đảm SQL join/fetch đúng ngữ nghĩa.
- Tự sửa sai lệch enum hoặc numeric type.
- Tự áp business validation/authorization.

Nó chỉ mô tả **cột ResultSet nào dùng để hydrate thuộc tính persistent nào**.

## 13. @EntityResult nhiều entity: tránh xung đột alias

Một native query có thể trả cả Order và Customer:

```sql
SELECT
    o.id AS o_id,
    o.order_no AS o_number,
    o.customer_id AS o_customer_fk,
    o.order_status AS o_status,
    o.total_amount AS o_total,
    o.version AS o_version,
    o.created_at AS o_created,
    c.id AS c_id,
    c.email_address AS c_email,
    c.display_name AS c_name
FROM sales_order o
JOIN crm_customer c
  ON c.id = o.customer_id;
```

Để hydrate **hai entity** từ một row, mapping có thể dùng hai `@EntityResult`. Ở ví dụ này, entity SalesOrder có association Customer sử dụng một cột FK; tùy provider/mapping phức tạp, relationship field mapping có thể cần cấu hình chuyên biệt.

Ví dụ theo ý tưởng chuẩn với association khóa ngoại một cột:

```java
@SqlResultSetMapping(
    name = "OrderAndCustomer",
    entities = {
        @EntityResult(
            entityClass = SalesOrder.class,
            fields = {
                @FieldResult(name = "id", column = "o_id"),
                @FieldResult(name = "orderNumber", column = "o_number"),
                @FieldResult(name = "customer", column = "o_customer_fk"),
                @FieldResult(name = "status", column = "o_status"),
                @FieldResult(name = "totalAmount", column = "o_total"),
                @FieldResult(name = "version", column = "o_version"),
                @FieldResult(name = "createdAt", column = "o_created")
            }
        ),
        @EntityResult(
            entityClass = Customer.class,
            fields = {
                @FieldResult(name = "id", column = "c_id"),
                @FieldResult(name = "email", column = "c_email"),
                @FieldResult(name = "name", column = "c_name")
            }
        )
    }
)
```

**Lưu ý về quan hệ:** `@FieldResult` dành cho relationship field một-cột FK có thể phải tương thích với mapping owning side và cách provider giải quyết relationship; trường hợp composite FK, inheritance hoặc alias đặc biệt cần đọc hợp đồng provider và kiểm chứng bằng integration test. Nếu không thật sự cần hydrate hai entity, **SELECT riêng các cột Order với `SalesOrder.class` thường đơn giản và portable hơn**.

Kết quả nhiều entity thường gồm nhiều phần tử cho mỗi row:

```java
List<?> rows = em.createNativeQuery(
    sql,
    "OrderAndCustomer"
).getResultList();

for (Object row : rows) {
    Object[] tuple = (Object[]) row;
    SalesOrder order = (SalesOrder) tuple[0];
    Customer customer = (Customer) tuple[1];
}
```

Đây là minh họa hình dạng kết quả khi mapping gồm hai entity. Các entity được quản lý theo persistence context tương ứng, không chỉ là DTO.

### 13.1. Lưu ý về số row và duplicate

Một Customer có thể xuất hiện ở nhiều SQL rows vì nhiều Order tham chiếu Customer ấy. Provider phải tôn trọng entity identity trong persistence context, nhưng **danh sách kết quả query vẫn có thể có nhiều row tham chiếu cùng Customer object**.

Đừng nhầm:

- Có **một Java instance managed** cho mỗi identity trong context.
- Có **một lần xuất hiện trong ResultSet/query result**.

Đó là hai vấn đề khác nhau.

## 14. Entity + scalar trong cùng native query

Một dashboard cần hiển thị Product kèm số lần sản phẩm xuất hiện trong `order_line`.

SQL:

```sql
SELECT
    p.id AS product_id,
    p.sku AS product_sku,
    p.display_name AS product_title,
    p.unit_price AS product_price,
    p.product_status AS product_state,
    p.version AS product_version,
    p.created_at AS product_created,
    (
        SELECT COUNT(*)
        FROM order_line l
        WHERE l.product_id = p.id
    ) AS usage_count
FROM catalog_product p
ORDER BY p.id;
```

Có thể khai báo mapping với **entity + scalar**:

```java
@SqlResultSetMapping(
    name = "ProductAndUsageCount",
    entities = @EntityResult(
        entityClass = Product.class,
        fields = {
            @FieldResult(name = "id", column = "product_id"),
            @FieldResult(name = "sku", column = "product_sku"),
            @FieldResult(name = "name", column = "product_title"),
            @FieldResult(name = "price", column = "product_price"),
            @FieldResult(name = "status", column = "product_state"),
            @FieldResult(name = "version", column = "product_version"),
            @FieldResult(name = "createdAt", column = "product_created")
        }
    ),
    columns = @ColumnResult(
        name = "usage_count",
        type = Long.class
    )
)
```

Thực thi:

```java
List<?> rows = em.createNativeQuery(
    sql,
    "ProductAndUsageCount"
).getResultList();

for (Object item : rows) {
    Object[] row = (Object[]) item;

    Product product = (Product) row[0];
    Long usageCount = (Long) row[1];

    System.out.println(
        product.getSku() + ": " + usageCount
    );
}
```

Ở đây:

- Phần tử đầu là entity Product có ID và state được hydrate.
- Phần tử sau là scalar `usageCount`.
- `usageCount` **không tự trở thành thuộc tính persistent của Product**.
- `@ColumnResult(type=Long.class)` giúp yêu cầu chuyển đổi kiểu theo ánh xạ được hỗ trợ; kiểu kết quả count của SQL thuần vẫn cần kiểm chứng theo DB/driver/provider.
- Nếu query trả nhiều scalar hoặc entity, thứ tự các phần tử trong `Object[]` cần được đọc theo hợp đồng result mapping.

### 14.1. Không gắn aggregate tùy ý vào entity field

Tránh thêm:

```java
@Column(name = "usage_count")
private Long usageCount;
```

chỉ để nhận kết quả từ một query tính toán, nếu bảng Product không có cột `usage_count` thực. Cách này làm sai mapping schema của entity.

Nếu thống kê là dữ liệu chỉ-đọc của response, hãy dùng **scalar projection hoặc DTO**.

## 15. Nếu chỉ cần một vài cột, dùng DTO thay vì entity

Giả sử một API cần:

- ID sản phẩm.
- SKU.
- Giá niêm yết.

Query:

```sql
SELECT
    p.id AS product_id,
    p.sku AS product_sku,
    p.unit_price AS product_price
FROM catalog_product p
WHERE p.product_status = ?1;
```

**Không nên** map truy vấn này bằng `Product.class`, bởi nó không trả đủ cột `name`, `status`, `version`, `createdAt`.

Tạo DTO:

```java
package com.example.shop.readmodel;

import java.math.BigDecimal;

public record ProductBrief(
    Long id,
    String sku,
    BigDecimal price
) { }
```

Và result mapping bằng `@ConstructorResult`:

```java
@SqlResultSetMapping(
    name = "ProductBriefMapping",
    classes = @ConstructorResult(
        targetClass = ProductBrief.class,
        columns = {
            @ColumnResult(name = "product_id", type = Long.class),
            @ColumnResult(name = "product_sku", type = String.class),
            @ColumnResult(
                name = "product_price",
                type = BigDecimal.class
            )
        }
    )
)
```

Thực thi:

```java
List<?> rows = em.createNativeQuery(
    """
    SELECT
        p.id AS product_id,
        p.sku AS product_sku,
        p.unit_price AS product_price
    FROM catalog_product p
    WHERE p.product_status = ?1
    """,
    "ProductBriefMapping"
)
.setParameter(1, "ACTIVE")
.getResultList();

for (Object row : rows) {
    ProductBrief dto = (ProductBrief) row;
    System.out.println(dto.sku());
}
```

### 15.1. Thứ tự @ColumnResult rất quan trọng

`@ConstructorResult` ánh xạ các cột theo thứ tự đối số constructor. Với record `ProductBrief(Long, String, BigDecimal)`, danh sách columns phải có:

1. ID kiểu Long.
2. SKU kiểu String.
3. Price kiểu BigDecimal.

Đổi thứ tự mà không đổi constructor có thể gây lỗi khởi tạo hoặc đưa dữ liệu sai vị trí nếu kiểu trùng nhau.

### 15.2. DTO không phải managed entity

`ProductBrief` không có `@Entity`. Kể cả có `id`, nó không được `EntityManager.contains(...)` nhận là một entity managed. Thay đổi field trong DTO không kích hoạt dirty checking hoặc UPDATE.

Đây là lợi ích cho nhiều truy vấn báo cáo: **kết quả đủ dùng, không làm phình persistence context, không vô tình mang theo entity lifecycle**.

### 15.3. Entity class làm DTO không phải thiết kế tốt

Không dùng một entity thiếu dữ liệu làm “DTO tạm” chỉ vì muốn tái sử dụng lớp Java. Một entity partial có thể gây hiểu nhầm về identity, trạng thái managed, lazy loading và dirty checking. Tách DTO giúp API thể hiện ý định rõ.

## 16. Native scalar query: không cần entity mapping

Chỉ muốn lấy số lượng Product:

```java
Object result = em
    .createNativeQuery(
        "SELECT COUNT(*) FROM catalog_product"
    )
    .getSingleResult();
```

Kết quả là scalar từ JDBC/provider, không phải Product entity.

Một cách xử lý thực dụng nếu provider trả numeric:

```java
Number countValue = (Number) result;
long count = countValue.longValue();
```

Không khẳng định mọi native SQL `COUNT(*)` đều trả `Long`. Tùy database, JDBC driver và JPA provider, kiểu cụ thể có thể là `Long`, `BigInteger` hoặc kiểu numeric khác. Nếu cần hợp đồng cố định, dùng mapping `@ColumnResult(type=...)` hoặc xử lý `Number` phù hợp.

### 16.1. Nhiều cột scalar

```sql
SELECT id, sku, unit_price
FROM catalog_product
ORDER BY id;
```

Với native query không truyền `resultClass` hoặc result-set mapping:

```java
List<?> rows = em.createNativeQuery(sql).getResultList();

for (Object item : rows) {
    Object[] columns = (Object[]) item;
    // Giải mã theo thứ tự SELECT và kiểu JDBC được trả về.
}
```

Mẫu scalar `Object[]` có ích cho truy vấn nhỏ, nhưng khi result phức tạp hơn nên dùng `@ConstructorResult` hoặc công cụ mapping rõ kiểu để giảm cast lỗi.

### 16.2. Chỉ một cột không nhất thiết có Object[]

Với native query SELECT một scalar column, mỗi phần tử của list thường chính là giá trị scalar thay vì `Object[]` một phần tử. Khi chuyển từ SELECT một cột sang nhiều cột, hình dạng kết quả có thể thay đổi. Không copy xử lý `Object[]` mà không kiểm tra query shape.

## 17. @NamedNativeQuery: đặt tên truy vấn và chọn mapping

Thay vì rải SQL ở nhiều service, có thể khai báo named native query trên entity:

```java
@NamedNativeQuery(
    name = "Product.findActiveNative",
    query = """
        SELECT
            p.id,
            p.sku,
            p.display_name,
            p.unit_price,
            p.product_status,
            p.version,
            p.created_at
        FROM catalog_product p
        WHERE p.product_status = ?1
        ORDER BY p.id
        """,
    resultClass = Product.class
)
@Entity
@Table(name = "catalog_product")
public class Product {
    // Mapping entity Product.
}
```

Sử dụng:

```java
List<?> results = em
    .createNamedQuery("Product.findActiveNative")
    .setParameter(1, "ACTIVE")
    .getResultList();

for (Object result : results) {
    Product product = (Product) result;
}
```

Một named native query cũng có thể chỉ định `resultSetMapping`:

```java
@NamedNativeQuery(
    name = "Product.findAliased",
    query = """
        SELECT
            p.id AS product_id,
            p.sku AS product_sku,
            p.display_name AS product_title,
            p.unit_price AS product_price,
            p.product_status AS product_state,
            p.version AS product_version,
            p.created_at AS product_created
        FROM catalog_product p
        """,
    resultSetMapping = "ProductAliasMapping"
)
```

Các ví dụ annotation ở nhiều phần là **những cấu hình thay thế hoặc bổ sung đặt trên entity**. Khi áp dụng thực tế, gộp annotation hợp lệ trong cùng file entity hoặc dùng dạng lặp/container annotation tương ứng; không khai báo nhiều class Product trùng tên.

### 17.1. Lợi ích của named native query

- Gắn tên truy vấn với một use case rõ ràng.
- Có thể tái sử dụng qua nhiều service.
- Tách một phần SQL khỏi logic nghiệp vụ.
- Chỉ định mapping ngay cạnh query.
- Dễ tìm kiếm khi thay schema hoặc đổi alias.

Nhưng việc câu SQL được khai báo bằng annotation **không chứng minh nó hợp lệ với mọi database**. Nó vẫn phụ thuộc schema, dialect, mapping và test.

## 18. Composite primary key: cần đủ mọi thành phần định danh

Một entity có khóa tổng hợp:

```java
@Embeddable
public class OrderLineId implements java.io.Serializable {

    private Long orderId;
    private Integer lineNumber;

    protected OrderLineId() {
    }

    // equals/hashCode theo giá trị khóa.
}
```

```java
@Entity
@Table(name = "sales_order_line")
public class SalesOrderLine {

    @EmbeddedId
    private OrderLineId id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @MapsId("orderId")
    @JoinColumn(name = "order_id")
    private SalesOrder order;

    @Column(name = "sku", nullable = false)
    private String sku;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    protected SalesOrderLine() {
    }
}
```

Giả sử `OrderLineId.orderId` và `OrderLineId.lineNumber` được ánh xạ sang cột `order_id` và `line_number` đúng bằng metadata/`@AttributeOverride` thích hợp.

Native query trả entity này phải cung cấp **cả hai phần** khóa:

```sql
SELECT
    l.order_id,
    l.line_number,
    l.sku,
    l.quantity
FROM sales_order_line l;
```

Không thể chỉ trả:

```sql
SELECT l.order_id, l.sku, l.quantity
FROM sales_order_line l;
```

và hy vọng JPA tự suy ra `lineNumber`.

### 18.1. Aliased composite key với FieldResult

Với trường hợp custom aliases:

```sql
SELECT
    l.order_id AS key_order,
    l.line_number AS key_line,
    l.sku AS line_sku,
    l.quantity AS line_quantity
FROM sales_order_line l;
```

`@FieldResult` cho nested fields có thể sử dụng **đường dẫn tên thuộc tính**, ví dụ `id.orderId` và `id.lineNumber` theo cơ chế nested field mapping mà JPA/provider hỗ trợ:

```java
@SqlResultSetMapping(
    name = "SalesOrderLineAliases",
    entities = @EntityResult(
        entityClass = SalesOrderLine.class,
        fields = {
            @FieldResult(name = "id.orderId", column = "key_order"),
            @FieldResult(name = "id.lineNumber", column = "key_line"),
            @FieldResult(name = "sku", column = "line_sku"),
            @FieldResult(name = "quantity", column = "line_quantity")
        }
    )
)
```

Phần relationship `@MapsId` cũng có yêu cầu FK tương ứng. Với nhiều cột FK, embedded IDs lồng nhau hoặc provider cụ thể, cần mapping đầy đủ theo hợp đồng JPA/provider và kiểm chứng kết quả hydrate. Ví dụ nhằm minh họa rằng **khóa tổng hợp không thể bị cắt bớt**.

### 18.2. @IdClass cũng có yêu cầu tương tự

Nếu dùng nhiều field `@Id` với `@IdClass`, tất cả cột ID cần có trong ResultSet. Việc khóa được biểu diễn bằng `@EmbeddedId` hay `@IdClass` không thay nguyên tắc: **entity identity phải đầy đủ và chính xác**.

## 19. Inheritance: discriminator và subclass fields

JPA hỗ trợ các chiến lược kế thừa như:

- `SINGLE_TABLE`.
- `JOINED`.
- `TABLE_PER_CLASS`.

Với `SINGLE_TABLE`:

```java
@Entity
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(name = "payment_kind")
public abstract class Payment {

    @Id
    private Long id;

    private BigDecimal amount;
}
```

```java
@Entity
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {

    private String cardLastFour;
}
```

Một native query trả `Payment.class` có thể cần **discriminator `payment_kind`** để provider xác định mỗi row phải được hydrate thành `CardPayment` hay subtype khác. Các cột của subtype cũng phải được xử lý đầy đủ theo mapping.

Ví dụ SQL minh họa:

```sql
SELECT
    id,
    amount,
    payment_kind,
    card_last_four
    -- và các cột persistent khác của hierarchy
FROM payment;
```

### 19.1. EntityResult có discriminatorColumn

Khi custom alias:

```java
@EntityResult(
    entityClass = Payment.class,
    discriminatorColumn = "payment_type_alias",
    fields = {
        @FieldResult(name = "id", column = "payment_id_alias"),
        @FieldResult(name = "amount", column = "amount_alias")
        // Mapping field của subtype nếu cần.
    }
)
```

`discriminatorColumn` trong `@EntityResult` là alias/cột được dùng để xác định discriminator trong ResultSet theo cấu hình đó.

Không tự tạo một giá trị discriminator giống nhau cho mọi row nếu bảng chứa nhiều subtype. Nếu SELECT bỏ discriminator hoặc cột subtype cần thiết, provider có thể không thể dựng đối tượng đúng type.

### 19.2. Với JOINED inheritance

Một hierarchy JOINED có thể lưu thuộc tính base và subtype ở **nhiều bảng**. Câu `SELECT base_table.*` có thể không đủ để dựng subtype đầy đủ. Cần SQL JOIN/cột bổ sung hoặc cơ chế mapping/provider được thiết kế rõ.

### 19.3. Không dùng ví dụ Product đơn bảng làm quy tắc cho mọi hierarchy

Khi entity mapping phức tạp, độ đầy đủ của ResultSet phải được xác định theo **toàn bộ mapping inheritance**, không chỉ những field hiển thị trong một class.

## 20. @Embedded, @SecondaryTable và thuộc tính phức tạp

### 20.1. @Embedded

Nếu entity có:

```java
@Embedded
private ShippingAddress shippingAddress;
```

và `ShippingAddress` chứa `city`, `postalCode` được ánh xạ vào các cột của entity, native query trả entity đầy đủ phải cung cấp các cột này theo mapping.

Với alias tùy chỉnh, field result cho embeddable có thể cần dotted attribute paths như `shippingAddress.city` tùy cấu trúc mapping. Phần này cần kiểm tra đặc tả/provider khi nhiều tầng embedded hoặc `@AttributeOverride`.

### 20.2. @SecondaryTable

Giả sử:

```java
@Entity
@Table(name = "customer")
@SecondaryTable(name = "customer_profile")
public class CustomerProfile {

    @Id
    private Long id;

    private String name;

    @Column(
        table = "customer_profile",
        name = "biography"
    )
    private String biography;
}
```

Một câu:

```sql
SELECT id, name FROM customer;
```

không tự chứa `biography` ở secondary table. Để hydrate entity hoàn chỉnh bằng native SQL, có thể phải JOIN bảng `customer_profile` và chọn alias phù hợp, hoặc dựa vào một cơ chế riêng của provider được chứng minh hoạt động.

Không giả định provider tự query secondary table để bù thiếu dữ liệu cho mọi trường hợp native resultClass.

### 20.3. @Basic(fetch=LAZY) không tự cho phép bỏ cột

Một số basic attribute như LOB có thể khai báo `@Basic(fetch = FetchType.LAZY)`. Nhưng khả năng trì hoãn tải basic fields có thể cần bytecode enhancement hoặc hỗ trợ riêng của provider.

Không lấy việc field được đánh dấu LAZY làm lý do mặc định bỏ cột khỏi native entity SELECT. Nếu muốn tránh tải LOB lớn, DTO projection hoặc entity thiết kế riêng theo use case thường an toàn hơn.

### 20.4. Provider-specific formula/computed columns

Các mapping đặc thù như calculated/formula fields có thể đòi hỏi alias/expression tương ứng để hydrate kết quả native. Đây không phải phần portable của mọi JPA provider; cần tham khảo hợp đồng implementation đã chọn khi viết câu SQL trả entity.

## 21. Native query trả entity có phải managed không?

Khi ánh xạ native query thành entity trong một persistence context đang hoạt động, entity nhận được được quản lý theo JPA như các entity khác cùng context.

Ví dụ:

```java
EntityManager em = emf.createEntityManager();

try {
    List<?> rows = em.createNativeQuery(
        """
        SELECT
            id, sku, display_name, unit_price,
            product_status, version, created_at
        FROM catalog_product
        WHERE id = ?1
        """,
        Product.class
    )
    .setParameter(1, 100L)
    .getResultList();

    if (!rows.isEmpty()) {
        Product product = (Product) rows.get(0);

        boolean managed = em.contains(product);
        System.out.println(managed); // Thường true trong context này.
    }
} finally {
    em.close();
}
```

Vì entity mang identity được quản lý:

- `EntityManager.contains(product)` có thể trả true khi context vẫn đang quản lý.
- `em.find(Product.class, product.getId())` trong cùng context thường trả cùng Java instance theo identity map.
- Sửa persistent state của managed entity trong transaction phù hợp có thể được dirty-check.
- Khi context bị đóng, instance không còn managed bởi context ấy.

### 21.1. Native resultClass không tạo một detached snapshot tự động

Nếu bạn muốn một kết quả chỉ đọc dùng cho API, cần cân nhắc DTO. Entity managed có thể mang theo:

- Association LAZY.
- Dirty checking.
- First-level cache.
- Vòng đời transaction/persistence context.
- Nguy cơ thay đổi state ngoài ý định trong transaction ghi.

Native SQL không tự vô hiệu những khía cạnh đó.

### 21.2. Một persistent identity tương ứng một managed instance trong context

Giả sử Product#100 đã được `em.find` tải trước:

```java
Product first = em.find(Product.class, 100L);

// Native query cũng trả Product#100.
Product second = (Product) em.createNativeQuery(
    """
    SELECT
        id, sku, display_name, unit_price,
        product_status, version, created_at
    FROM catalog_product
    WHERE id = ?1
    """,
    Product.class
)
.setParameter(1, 100L)
.getSingleResult();

System.out.println(first == second); // Cùng identity trong context.
```

JPA duy trì **identity map**. Không xem native query là cách chắc chắn ép provider tạo một bản Java entity độc lập mỗi lần SELECT.

### 21.3. Không dùng native query thay refresh một cách vô điều kiện

Nếu một Product đã managed và một transaction khác cập nhật row Product#100, native query mới không nhất thiết ghi đè state đã có của managed instance. Transaction isolation và first-level cache ảnh hưởng quan sát dữ liệu.

Muốn làm mới object có chủ đích, cân nhắc:

```java
em.refresh(product);
```

nhưng `refresh` có thể ghi đè thay đổi cục bộ chưa flush. Cần hiểu use case trước khi gọi.

## 22. Đồng bộ trước native SELECT và transaction context

Trong một transaction ghi, có thể có pending changes trong persistence context:

```java
tx.begin();

Product product = em.find(Product.class, 100L);
// Giả sử domain method đổi giá thành 250.00.
product.changePrice(new BigDecimal("250.00"));

List<?> rows = em.createNativeQuery(
    """
    SELECT
        id, sku, display_name, unit_price,
        product_status, version, created_at
    FROM catalog_product
    WHERE id = ?1
    """,
    Product.class
)
.setParameter(1, 100L)
.getResultList();

tx.commit();
```

Provider có thể quyết định flush trước query theo flush mode, transaction và loại native query. Không suy ra native SQL luôn nhìn thấy pending Java changes mà chưa flush, và cũng không suy ra query không bao giờ gây auto-flush.

Khi **cần** SQL/JDBC thực thi trên trạng thái mới của entity trong cùng transaction, có thể đặt:

```java
em.flush();
```

trước native query, với transaction phù hợp. Nhưng:

- Flush đồng bộ pending state **chưa phải commit**.
- Lỗi FK/UNIQUE/optimistic lock có thể xuất hiện ở flush.
- Nếu entity đã managed, việc đọc kết quả native có thể tái dùng instance hiện tại.
- Một flush không khiến transaction khác mặc định nhìn thấy dữ liệu chưa commit.

### 22.1. Không tạo side effect ngoài DB chỉ vì native SELECT thấy dữ liệu

Một row được đọc trong cùng transaction chưa commit vẫn có thể rollback. Nếu cần phát event/payment/email sau khi tạo entity, dùng after-commit/outbox theo yêu cầu, không căn cứ vào một native SELECT hoặc explicit flush như bằng chứng commit.

## 23. SQL JOIN và N+1: việc map đủ cột chưa giải quyết fetch plan

SalesOrder có Customer LAZY. Query:

```sql
SELECT
    o.id,
    o.order_no,
    o.customer_id,
    o.order_status,
    o.total_amount,
    o.version,
    o.created_at
FROM sales_order o;
```

có thể hydrate SalesOrder managed mà chưa tải toàn bộ Customer. Sau đó:

```java
for (SalesOrder o : orders) {
    System.out.println(o.getCustomer().getEmail());
}
```

có thể kích hoạt nhiều SELECT bổ sung. Đây là nguy cơ **N+1**.

### 23.1. SQL JOIN dùng để lọc không tự giải quyết fetch

```sql
SELECT o.id, o.order_no, o.customer_id, ...
FROM sales_order o
JOIN crm_customer c ON c.id = o.customer_id
WHERE c.email_address = ?;
```

Vẫn chỉ có các cột Order trong ResultSet. Join chỉ phục vụ predicate, không tự thay đổi fetch plan của SalesOrder.customer.

### 23.2. Nếu cần DTO, chọn luôn các cột mong muốn

```sql
SELECT
    o.id AS order_id,
    o.order_no AS order_number,
    c.display_name AS customer_name,
    o.total_amount AS total_amount
FROM sales_order o
JOIN crm_customer c
  ON c.id = o.customer_id;
```

Đây là query tốt cho DTO gồm Order ID, Order Number, Customer Name và Total Amount. Không nên map nó sang SalesOrder managed vì thiếu các cột khác và có alias không tương thích.

### 23.3. Khi nào dùng JPQL JOIN FETCH hoặc EntityGraph?

Nếu mục tiêu chính là tải entity graph thông thường theo association JPA, JPQL `JOIN FETCH` hoặc entity graph thường dễ biểu đạt fetch semantics hơn. Native SQL phù hợp khi query logic thực sự cần SQL-specific syntax hoặc bạn muốn kiểm soát SQL và result mapping.

**Đừng chọn native SQL chỉ vì nghĩ rằng SQL JOIN luôn tự biến thành loaded JPA association.**

## 24. Row multiplication và duplicate entities khi JOIN collection

Giả sử Product#100 xuất hiện trong ba OrderLine. Query:

```sql
SELECT
    p.id,
    p.sku,
    p.display_name,
    p.unit_price,
    p.product_status,
    p.version,
    p.created_at
FROM catalog_product p
JOIN order_line l
  ON l.product_id = p.id
WHERE p.id = ?;
```

SQL có thể trả **ba rows** ứng với cùng Product#100.

Provider vẫn phải tôn trọng identity của Product trong persistence context, nhưng result list có thể có ba lần xuất hiện của cùng managed Product. Không được suy luận:

> Có một Product entity trong persistence context nên query list chắc chắn chỉ có một phần tử.

### 24.1. DISTINCT ở SQL

Nếu chỉ cần Product duy nhất:

```sql
SELECT DISTINCT
    p.id,
    p.sku,
    p.display_name,
    p.unit_price,
    p.product_status,
    p.version,
    p.created_at
FROM catalog_product p
JOIN order_line l
  ON l.product_id = p.id;
```

Có thể giúp loại duplicate rows khi tất cả selected Product columns giống nhau. Tuy nhiên DISTINCT có thể tốn chi phí, nhất là khi SELECT nhiều cột lớn.

### 24.2. EXISTS tránh nhân bản khi chỉ cần điều kiện tồn tại

```sql
SELECT
    p.id,
    p.sku,
    p.display_name,
    p.unit_price,
    p.product_status,
    p.version,
    p.created_at
FROM catalog_product p
WHERE EXISTS (
    SELECT 1
    FROM order_line l
    WHERE l.product_id = p.id
);
```

Mỗi Product chỉ nằm ở outer source một lần. Đây thường là cách rõ nghĩa nếu câu hỏi là “sản phẩm có ít nhất một dòng hàng không?”.

### 24.3. Không tính tổng sai sau JOIN

Nếu muốn tính tổng giá `unit_price` cho các Product khác nhau, JOIN order_line có thể làm Product bị lặp; `SUM(p.unit_price)` sẽ cộng một lần **trên mỗi joined row**, không phải mỗi Product. Entity result mapping đúng không tự sửa lỗi aggregate logic này.

Khi aggregate, xác định grain và dùng EXISTS/subquery hoặc thiết kế query đúng mức dữ liệu.

## 25. Pagination với native entity query

JPA `Query` hỗ trợ:

```java
List<?> page = em.createNativeQuery(
    """
    SELECT
        p.id,
        p.sku,
        p.display_name,
        p.unit_price,
        p.product_status,
        p.version,
        p.created_at
    FROM catalog_product p
    ORDER BY p.created_at DESC, p.id DESC
    """,
    Product.class
)
.setFirstResult(20)
.setMaxResults(10)
.getResultList();
```

`setFirstResult(20)` bỏ qua 20 result rows đầu; `setMaxResults(10)` lấy tối đa 10 rows theo thứ tự đã xác định.

### 25.1. Cần ORDER BY ổn định

Nếu không có `ORDER BY`, database không cam kết thứ tự rows. Để phân trang ổn định, thêm tie-breaker như `id` khi nhiều Product có cùng `created_at`.

### 25.2. JOIN collection có thể làm pagination theo row, không theo entity

Nếu SQL trả nhiều joined rows cho cùng Product, `setMaxResults(10)` có thể chỉ lấy 10 SQL/result rows, không phải 10 Product identity khác nhau. Kết quả pagination có thể thiếu hoặc lặp parent theo mục tiêu nghiệp vụ.

Một hướng:

1. Query trang **Product ID** duy nhất theo sort.
2. Query thứ hai lấy đầy đủ Product columns cho các ID đó.
3. Khôi phục thứ tự mong muốn ở application nếu SQL `IN` không giữ thứ tự đầu vào.

### 25.3. Không nối LIMIT/OFFSET tùy ý khi đã dùng JPA pagination

Database có cú pháp khác nhau như `LIMIT/OFFSET`, `FETCH FIRST`, `ROWNUM`, `TOP`. Với query dùng JPA Query API, `setFirstResult`/`setMaxResults` cho provider cơ hội áp dụng dialect phù hợp.

Khi cố ý viết native SQL có pagination chuyên biệt, cần xem tương tác với các giới hạn đặt thêm từ JPA Query để tránh phân trang hai lần ngoài ý muốn.

## 26. Parameter binding và SQL injection

Native SQL có nhiều tính năng mạnh, nên càng cần bảo vệ việc lắp chuỗi query.

### 26.1. Bind giá trị bằng tham số

```java
String sql = """
    SELECT
        id, sku, display_name, unit_price,
        product_status, version, created_at
    FROM catalog_product
    WHERE sku = ?1
    """;

List<?> rows = em.createNativeQuery(sql, Product.class)
    .setParameter(1, skuFromRequest)
    .getResultList();
```

Dùng `?1` / `setParameter(1, ...)` theo kiểu binding được môi trường JPA hỗ trợ.

Các provider có thể hỗ trợ named parameters trong native SQL như `:sku`, nhưng không nên giả định mọi syntax/kiểu binding provider-specific được portable trên mọi JPA implementation. Collection parameter expansion cho `IN (...)` trong native SQL cũng có điểm khác biệt; cần kiểm chứng.

### 26.2. Đừng nối input vào SQL

Không nên:

```java
String sql = "SELECT * FROM catalog_product WHERE sku = '" +
    userInput +
    "'";
```

Giá trị người dùng có thể thay đổi cú pháp SQL, gây SQL injection hoặc sai quoting. Luôn bind giá trị lọc khi API hỗ trợ.

### 26.3. Không bind tên bảng hoặc tên cột

Câu SQL như:

```sql
SELECT * FROM ?1 WHERE sku = ?2
```

không cho phép `?1` hoạt động như tên bảng động theo cách parameter binding thông thường. Tên identifier thuộc **cấu trúc SQL**, không phải giá trị dữ liệu.

Nếu cần chọn trường sort:

```java
String orderBy = switch (sortKey) {
    case "sku" -> "p.sku";
    case "created" -> "p.created_at";
    case "price" -> "p.unit_price";
    default -> throw new IllegalArgumentException(
        "Trường sắp xếp không được phép"
    );
};

String sql = """
    SELECT
        p.id, p.sku, p.display_name, p.unit_price,
        p.product_status, p.version, p.created_at
    FROM catalog_product p
    ORDER BY
    """ + orderBy;
```

Chỉ nối các **literal đáng tin từ whitelist**, không nối trực tiếp nội dung tùy ý do client nhập.

### 26.4. Bảo mật multi-tenant và soft delete

Native query có thể không tự chịu tác động của một số provider-level filters hoặc logic query được ứng dụng thiết kế riêng cho JPQL/repository. Nếu bảng có `tenant_id` hoặc `deleted_at`, cần bảo đảm truy vấn native áp dụng điều kiện chính xác, trừ khi cơ chế bảo vệ ở DB như row-level security đã được cấu hình và kiểm chứng.

**Không có chuyện native resultClass tự sinh authorization predicate** chỉ vì entity có annotation/logic ở tầng service.

Ví dụ dữ liệu nhiều tenant:

```sql
SELECT
    p.id, p.sku, p.display_name, p.unit_price,
    p.product_status, p.version, p.created_at
FROM catalog_product p
WHERE p.tenant_id = ?1;
```

Đây là ví dụ giả định bảng đã có `tenant_id` và entity/mapping tương thích; phải lấy tenant ID từ security context đáng tin, không từ yêu cầu chưa xác thực.

## 27. Những lỗi phổ biến khi ánh xạ native SQL về entity

### 27.1. Dùng JPQL trong createNativeQuery

```java
em.createNativeQuery("select p from Product p", Product.class);
```

`Product` ở đây là entity name, `p` là JPQL alias. SQL engine không hiểu cú pháp `select p from Product p` theo nghĩa JPA nếu không có bảng/identifier tương ứng.

Dùng `createQuery` cho JPQL hoặc viết SQL thật cho `createNativeQuery`.

### 27.2. Dùng tên bảng SQL trong createQuery

```java
em.createQuery("select p from catalog_product p");
```

`createQuery` nhận JPQL nên `catalog_product` không phải entity name trừ khi được khai báo cố ý như vậy. Không trộn hai loại ngôn ngữ.

### 27.3. SELECT thiếu ID

`SELECT sku, display_name FROM catalog_product` không đủ để tạo Product managed theo @Id Long id.

### 27.4. SELECT thiếu version

Entity có @Version nhưng SQL không trả version thực; optimistic locking state có thể không đúng.

### 27.5. SELECT thiếu cột FK

SalesOrder có `@ManyToOne customer` nhưng SQL bỏ `customer_id`, khiến provider thiếu thông tin relationship.

### 27.6. SELECT * khi JOIN nhiều bảng

`SELECT o.*, c.*` có nhiều cột `id` và tên trùng; cần chọn đúng columns hoặc dùng aliases + explicit result mapping.

### 27.7. Alias khác mapped column nhưng không có FieldResult

SQL trả `product_title` nhưng entity @Column là `display_name`. Nếu mapping mặc định cần `display_name`, query có thể thất bại vì không tìm thấy label phù hợp.

### 27.8. FieldResult.name dùng tên cột DB

```java
@FieldResult(
    name = "display_name",
    column = "product_title"
)
```

Sai nếu Product persistent attribute là `name`, không phải `display_name`.

Đúng:

```java
@FieldResult(
    name = "name",
    column = "product_title"
)
```

### 27.9. FieldResult.column trỏ đến cột không được SELECT

Nếu mapping nói `column = "product_title"` mà SQL chỉ trả alias `title`, ResultSet không cung cấp tên mapping mong muốn.

### 27.10. Trả DTO query nhưng dùng Entity.class

SQL chỉ có `id`, `sku`, `unit_price`; nhưng `resultClass` = Product.class. Dùng `@ConstructorResult` hoặc scalar projection.

### 27.11. Entity hydration thành công nên tưởng mọi field đều đúng

Provider có thể cho phép một số extension/partial loading hoặc deferred load; hành vi đó không trở thành contract portable. Cần thiết kế query đúng theo mapping và kiểm chứng trong môi trường thực tế.

### 27.12. Trả nhiều entity nhưng chỉ map một

`SELECT o.*, c.*` không tự nói JPA cần dựng cả SalesOrder và Customer. Sử dụng hai `@EntityResult` hoặc DTO tùy mục tiêu.

### 27.13. Đếm native COUNT với cast Long cứng

`(Long) query.getSingleResult()` có thể fail nếu driver/provider trả BigInteger hoặc kiểu Number khác. Cân nhắc `Number`/ColumnResult typed.

### 27.14. Cho rằng native query trả detached POJO

Native entity result được quản lý theo persistence context khi query hydrate entity hợp lệ. Sửa entity trong transaction có thể tạo UPDATE.

### 27.15. Cho rằng native query luôn refresh entity đã managed

First-level cache/identity map vẫn có hiệu lực. Muốn làm mới có chủ đích cần hiểu `refresh`, `clear` và isolation.

### 27.16. Nhầm JOIN với JOIN FETCH của JPQL

Một SQL JOIN phục vụ predicate không tự đảm bảo hydrated LAZY association.

### 27.17. Không kiểm soát duplicate rows khi JOIN collection

ResultList có thể chứa nhiều lần cùng entity identity do row multiplication; DISTINCT/EXISTS hoặc query hai bước khi cần.

### 27.18. Dùng alias trùng nhau giữa hai entity

`p.id AS id` và `c.id AS id` gây ambiguity nếu cần hydrate hai entity. Dùng `product_id`/`customer_id` và result mapping tường minh.

### 27.19. Composite ID thiếu thành phần

@EmbeddedId có hai cột nhưng SELECT chỉ trả một. Entity identity không đầy đủ.

### 27.20. Inheritance thiếu discriminator

SINGLE_TABLE polymorphic query không có discriminator cần thiết có thể khiến provider không xác định subclass.

### 27.21. @SecondaryTable không được đưa vào SQL

Entity có field ở bảng phụ nhưng SELECT chỉ từ bảng chính, khiến ResultSet thiếu dữ liệu mapping yêu cầu.

### 27.22. Tự gán ID hoặc version giả

Thay cột thiếu bằng literal SQL không phản ánh dữ liệu thực, gây lỗi identity/optimistic state.

### 27.23. Không kiểm tra provider và database dialect

Cú pháp `WITH`, `RETURNING`, window functions, JSON operators, quoted aliases và kiểu số khác nhau theo database/provider. Native SQL không tự portable hoàn toàn.

### 27.24. Nghĩ @SqlResultSetMapping làm SQL hợp lệ

Mapping chỉ mô tả kết quả, không sửa sai cú pháp SQL, quyền DB hoặc missing table/column.

### 27.25. Bỏ qua tenant và soft-delete

Native query có thể vô tình trả dữ liệu của tenant khác hoặc record đã soft-delete nếu thiếu các predicate bắt buộc.

## 28. Quy trình điều tra lỗi khi native entity mapping thất bại

Nếu gặp lỗi kiểu “column not found”, “could not extract ResultSet”, “could not resolve column position/name”, “invalid identifier”, hoặc hydrated entity sai state, hãy tách vấn đề theo từng lớp.

### 28.1. Kiểm tra SQL có chạy độc lập không

Chạy SQL tương ứng trong môi trường phát triển với database/dialect thật và cùng schema. Kiểm tra:

- Table và column names đúng.
- Điều kiện WHERE và parameter hợp lệ.
- Alias đúng ký tự hoa/thường, dấu nháy.
- JOIN không nhân bản rows ngoài dự kiến.
- SQL trả số cột và giá trị như mong muốn.

Đây là bước chẩn đoán khi phát triển, không phải yêu cầu luôn log dữ liệu production nhạy cảm.

### 28.2. Đối chiếu ResultSet với entity mapping

Lập bảng:

| Entity field | Mapping column | SQL result label | Có trong SELECT? |
|---|---|---|---|
| `id` | `id` | `product_id` | Có |
| `sku` | `sku` | `product_sku` | Có |
| `name` | `display_name` | `product_title` | Có |
| `price` | `unit_price` | `product_price` | Có |
| `status` | `product_status` | `product_state` | Có |
| `version` | `version` | `product_version` | Có |
| `createdAt` | `created_at` | `product_created` | Có |

Nếu labels khác mapped column names, cần result set mapping tường minh như `ProductAliasMapping`.

### 28.3. Kiểm tra identity và quan hệ

- Đủ tất cả `@Id`/`@EmbeddedId` components?
- Có version/discriminator đúng không?
- FK cho association mapped có trong query không?
- Cột của embedded/secondary tables đã có chưa?
- JOIN có tạo nhiều rows cho một identity không?

### 28.4. Kiểm tra mapping và Java type

- `@Enumerated` khớp giá trị cột?
- `@Convert` được áp đúng trong entity hydration?
- BigDecimal, Date/Time, UUID, Boolean mapping khớp dialect?
- Field access/property access có đúng metadata?
- Entity được quét vào persistence unit chưa?
- Result mapping name đúng và annotation đặt ở phạm vi được JPA nhận diện chưa?

### 28.5. Kiểm tra persistence context

Nếu SQL trả giá trị mới nhưng entity kết quả vẫn giữ field cũ:

- Instance cùng ID đã managed trước query?
- Có dirty changes chưa flush?
- Có transaction isolation che thay đổi từ transaction khác?
- Đã dùng `refresh`/context mới khi cần chưa?

### 28.6. Quan sát log đúng mức

Ghi SQL, query name, mapping name và thời gian thực thi. Khi bật bind parameter logging, cẩn thận email, payment token, thông tin cá nhân, khóa API và dữ liệu nhạy cảm. Không bật log toàn bộ params ở production một cách mặc định.

## 29. Kiểm thử ánh xạ bằng integration test

Một unit test chỉ mock `EntityManager` không chứng minh provider hydrate entity từ JDBC ResultSet đúng. Để kiểm tra vấn đề này, cần integration test với database/schema thực tế hoặc môi trường tương thích.

### 29.1. Setup dữ liệu có ID ổn định

Tạo Product với:

```text
id            = 100
sku           = BOOK-001
display_name  = Java Persistence Guide
unit_price    = 125000.00
product_status= ACTIVE
version       = 3
created_at    = ...
```

Sử dụng transaction setup đã commit, rồi mở `EntityManager` mới cho test đọc.

### 29.2. Kiểm tra direct native mapping

```java
EntityManager em = emf.createEntityManager();

try {
    Product product = (Product) em.createNativeQuery(
        """
        SELECT
            id, sku, display_name, unit_price,
            product_status, version, created_at
        FROM catalog_product
        WHERE id = ?1
        """,
        Product.class
    )
    .setParameter(1, 100L)
    .getSingleResult();

    assertEquals(100L, product.getId());
    assertEquals("BOOK-001", product.getSku());
    assertEquals(ProductStatus.ACTIVE, product.getStatus());
    assertEquals(
        0,
        product.getPrice().compareTo(
            new BigDecimal("125000.00")
        )
    );
    assertTrue(em.contains(product));
} finally {
    em.close();
}
```

Đây là đoạn minh họa trong phong cách JUnit; các import như `assertEquals`/`assertTrue` từ framework test và setup transaction/fixture cần được bổ sung khi áp dụng.

### 29.3. Kiểm tra custom alias mapping

Dùng SQL trả `product_id`, `product_title`... và mapping `ProductAliasMapping`; kiểm tra ID, các field cơ bản, enum và version sau hydration.

### 29.4. Kiểm tra association FK

Tạo Customer#10 và SalesOrder#20 trỏ tới Customer#10. Dùng native SELECT Order có `customer_id`; trong persistence context hợp lệ, kiểm tra reference tới Customer mang đúng ID, rồi kiểm tra dữ liệu Customer theo fetch/lazy behavior của provider.

Không chỉ assert `orders.size()` mà bỏ qua relationship mapping.

### 29.5. Kiểm tra JOIN có nhiều rows

Tạo Product với ba OrderLine, thực thi query JOIN order_line; xác định result list có duplicate rows hay không và xác minh query DISTINCT/EXISTS tương ứng thực sự đáp ứng mục đích.

### 29.6. Kiểm tra composite ID/inheritance

Nếu project có `@EmbeddedId` hoặc hierarchy, thêm fixture có hai entity cùng một phần khóa nhưng khác phần còn lại, và nhiều subclass/discriminator values. Đây là nơi thiếu cột thường gây lỗi khó phát hiện.

### 29.7. Kiểm tra query report dùng DTO

Với ProductBrief, assert DTO chỉ có ID/SKU/price và không thể được coi là Product managed. Không dùng `em.contains(dto)` để kiểm tra DTO như entity; DTO không phải một JPA entity.

### 29.8. Kiểm tra trên provider/database đích

Một test chạy với H2 có thể không bắt được mọi khác biệt alias case, numeric JDBC type, pagination và SQL dialect của PostgreSQL/Oracle/MySQL. Với native SQL quan trọng, nên có integration test với database tương thích production, có thể qua Testcontainers hoặc môi trường test đã thiết lập.

## 30. Chọn result mapping theo mục tiêu

| Mục tiêu | Cách ánh xạ thường phù hợp | Lưu ý |
|---|---|---|
| Trả Product đầy đủ từ một bảng | `createNativeQuery(sql, Product.class)` | SELECT phải đủ mapped columns |
| Query có alias tùy chỉnh | `@SqlResultSetMapping` + `@EntityResult`/`@FieldResult` | Đồng bộ aliases và field names |
| Trả cả Order và Customer | Nhiều `@EntityResult` | Phân biệt aliases; quan hệ/FK có thể phức tạp |
| Trả Product + số lượng | `@EntityResult` + `@ColumnResult` | Kết quả nhiều phần tử, scalar không thành entity field |
| Chỉ trả ID/SKU/price | `@ConstructorResult`/DTO | Tránh partial entity |
| Chỉ COUNT hoặc SUM | Scalar `createNativeQuery(sql)` | Kiểu numeric phụ thuộc JDBC/provider |
| Nhiều cột scalar ngắn | `Object[]` hoặc DTO mapping | Thứ tự và kiểu phải rõ |
| Một query native dùng lại nhiều nơi | `@NamedNativeQuery` | Không tự làm SQL portable |
| Entity có composite ID | Entity mapping đầy đủ key parts | Không bỏ bất kỳ thành phần ID nào |
| Entity inheritance | Discriminator/subclass-aware mapping | Phụ thuộc strategy/provider |
| Entity có @SecondaryTable | SQL/mapping bao phủ dữ liệu cần thiết | SELECT main table.* có thể không đủ |

**Cách quyết định nhanh:**

```text
                  Cần native SQL?
                         |
                         v
              Kết quả muốn nhận là gì?
               /          |           \
          Entity đầy đủ  Entity+scalar  Chỉ vài cột
               |          |             |
               v          v             v
          SELECT đủ   @EntityResult   DTO /
          mapped      + @ColumnResult @ConstructorResult
          columns         |
               |          |
               v          v
          Alias có khác/khả năng trùng không?
               /                 \
             Không               Có
               |                  |
               v                  v
         resultClass         @SqlResultSetMapping
               |                  |
               +--------+---------+
                        |
                        v
             Kiểm tra ID, version,
             FK, embedded/inheritance
                        |
                        v
              Kiểm tra ResultSet,
              persistence context
                        |
                        v
               Integration test
```

## 31. Bài tập thực hành có gợi ý

### Bài 1: SELECT thiếu ID

```sql
SELECT sku, display_name, unit_price
FROM catalog_product;
```

**Yêu cầu:** Query này có phù hợp với `createNativeQuery(sql, Product.class)` không?

**Gợi ý:** Không. Thiếu `id` và các mapped columns khác. Dùng DTO nếu chỉ cần vài cột, hoặc SELECT đầy đủ Product columns.

### Bài 2: Tên attribute và tên column

Product có `@Column(name="display_name") private String name`.

**Yêu cầu:** Trong native SQL chọn cột nào? Trong `@FieldResult(name=...)` điền gì?

**Gợi ý:** SQL chọn `display_name`; `FieldResult.name` điền `name`.

### Bài 3: Direct entity mapping

**Yêu cầu:** Viết query lấy Product ACTIVE với đủ dữ liệu.

**Gợi ý:**

```sql
SELECT id, sku, display_name, unit_price,
       product_status, version, created_at
FROM catalog_product
WHERE product_status = ?;
```

Dùng `createNativeQuery(sql, Product.class)` và bind giá trị phù hợp kiểu DB.

### Bài 4: SQL alias

```sql
SELECT id AS pid, sku AS psku, ...
FROM catalog_product;
```

**Câu hỏi:** Vì sao `Product.class` có thể không đủ để map tự động?

**Gợi ý:** ResultSet label `pid` khác mapped column `id`. Cần alias khớp mapping hoặc `@SqlResultSetMapping` với `@FieldResult`.

### Bài 5: Version

**Yêu cầu:** Entity có `@Version Long version` nhưng SELECT không trả `version`.

**Gợi ý:** Không an toàn/không portable cho managed entity đầy đủ. Bổ sung giá trị version thật từ DB.

### Bài 6: ManyToOne

SalesOrder có `Customer customer` qua `customer_id`.

**Câu hỏi:** Không có field `customerId` thì có được bỏ cột `customer_id` khỏi native SELECT không?

**Gợi ý:** Không. Association FK vẫn là một phần dữ liệu cần cho mapping SalesOrder.

### Bài 7: JOIN hai bảng

```sql
SELECT o.*, c.*
FROM sales_order o
JOIN crm_customer c ON c.id = o.customer_id;
```

**Câu hỏi:** Rủi ro khi map `SalesOrder.class` là gì?

**Gợi ý:** Trùng label `id` và các cột khác. Nếu chỉ cần Order, SELECT các cột Order. Nếu cần hai entity, alias rõ và result mapping.

### Bài 8: Scalar COUNT

**Yêu cầu:** Nhận `SELECT COUNT(*) FROM catalog_product`.

**Gợi ý:** Không dùng Product.class; nhận scalar kiểu `Number` hoặc mapping có type được xác định.

### Bài 9: DTO ba cột

**Yêu cầu:** API chỉ cần Product id, sku, price.

**Gợi ý:** `@ConstructorResult(targetClass=ProductBrief.class, columns=...)` hoặc manual DTO; không hydrate partial Product managed.

### Bài 10: @FieldResult.name

```java
@FieldResult(name = "unit_price", column = "price_alias")
```

**Câu hỏi:** Sai ở đâu nếu Product field là `price`?

**Gợi ý:** `name` phải là persistent Java attribute `price`, không phải SQL column `unit_price`.

### Bài 11: ID tổng hợp

OrderLineId có `orderId` và `lineNumber`.

**Câu hỏi:** Query chỉ trả `order_id` mà không trả `line_number` có được xem là đủ không?

**Gợi ý:** Không; thiếu một phần primary key nên không xác định được entity identity.

### Bài 12: Inheritance discriminator

Một bảng SINGLE_TABLE có Payment, CardPayment và BankTransferPayment.

**Câu hỏi:** Native query trả Payment base có thể cần thêm gì?

**Gợi ý:** Cột discriminator và các cột subtype cần thiết theo mapping.

### Bài 13: Entity và scalar

SQL trả Product đầy đủ + `usage_count`.

**Yêu cầu:** Mapping nên dùng gì?

**Gợi ý:** `@SqlResultSetMapping` với `@EntityResult` cho Product và `@ColumnResult` cho count. Khi đọc, kết quả thường là `Object[]`.

### Bài 14: Entity identity

Product#100 đã managed. Native query trả Product#100 lần nữa.

**Câu hỏi:** Có mặc định là một object Java thứ hai không?

**Gợi ý:** Không. Persistence context quản lý identity, có thể trả chính instance đã managed.

### Bài 15: Refresh

Native SQL trong một context trả row mới cập nhật từ transaction khác, nhưng Product managed còn field cũ.

**Gợi ý:** Đọc lại bằng native query không nhất thiết refresh state hiện có. Phải xem isolation, `refresh` hoặc context mới.

### Bài 16: N+1

Native SELECT SalesOrder có đủ FK, rồi duyệt `order.getCustomer().getEmail()`.

**Câu hỏi:** Vì sao vẫn có thể N+1?

**Gợi ý:** FK đủ để map association nhưng không đồng nghĩa Customer entity đã được fetch.

### Bài 17: Duplicate rows

Một Product có 5 OrderLine. SQL JOIN line trả Product columns.

**Câu hỏi:** Kết quả có thể có bao nhiêu SQL rows?

**Gợi ý:** 5 rows cho cùng Product. Cần DISTINCT/EXISTS hoặc query ở grain phù hợp.

### Bài 18: Pagination

**Yêu cầu:** Lấy 20 Product theo created_at mới nhất, tie-breaker ID.

**Gợi ý:** `ORDER BY p.created_at DESC, p.id DESC` và `setMaxResults(20)`. Tránh pagination theo joined rows của collection khi muốn 20 Product duy nhất.

### Bài 19: Multi-tenant

Bảng catalog_product có tenant_id, một native query không có tenant predicate.

**Câu hỏi:** Vì sao nguy hiểm?

**Gợi ý:** Native mapping về Product không tự bảo đảm filter tenant/authorization. Cần điều kiện và security policy phù hợp.

### Bài 20: Secondary table

Entity có `biography` ở `customer_profile`, nhưng SQL chỉ SELECT bảng `customer`.

**Gợi ý:** Có thể thiếu dữ liệu mapped. Cân nhắc SQL JOIN/alias hoặc DTO tùy yêu cầu.

### Bài 21: Kiểu enum

Database lưu ProductStatus dưới dạng VARCHAR, ứng dụng bind `ProductStatus.ACTIVE` trực tiếp vào native `?1`.

**Câu hỏi:** Có portable không?

**Gợi ý:** Không giả định mọi provider áp enum binding native giống JPQL. Dùng kiểu SQL column hoặc mapping được provider hỗ trợ và test thật.

### Bài 22: @NamedNativeQuery

**Đề:** Định nghĩa query native tái sử dụng với alias khác mapping.

**Gợi ý:** `@NamedNativeQuery(resultSetMapping="ProductAliasMapping")` và cấu hình `@SqlResultSetMapping` cho alias tương ứng.

### Bài 23: Không nhầm DTO với entity

ProductBrief nhận từ `@ConstructorResult` có Long id.

**Câu hỏi:** ProductBrief có tự được JPA quản lý chỉ vì chứa id không?

**Gợi ý:** Không. Nó là DTO thường, không phải entity managed.

### Bài 24: Test resultClass với DB thật

**Đề:** Viết integration test kiểm tra native Product mapping.

**Gợi ý:** Tạo fixture có id/status/version/createdAt đầy đủ, commit setup, mở EntityManager mới, chạy SQL, assert các field và identity. Kiểm tra thêm alias mapping và FK relation.

## 32. Bảng ghi nhớ cuối bài

| Câu hỏi | Câu trả lời trọng tâm |
|---|---|
| Native SQL viết theo entity hay bảng? | Theo **bảng/cột SQL** |
| JPQL viết theo entity hay bảng? | Theo **entity/thuộc tính Java** |
| Dùng API nào để trả entity từ native SQL? | `EntityManager.createNativeQuery(sql, Entity.class)` |
| ResultClass tự điền cột thiếu không? | **Không có bảo đảm portable** |
| Cột quan trọng nhất là gì? | **Primary key đầy đủ** |
| Chỉ ID đã đủ chưa? | Không; còn mapped fields, version, FK và metadata liên quan |
| @Version có cần chú ý không? | Có, vì optimistic locking |
| @ManyToOne LAZY có cần cột FK không? | Có, theo mapping association |
| Có thể SELECT * khi JOIN nhiều bảng? | Dễ xung đột tên; nên chọn cột/alias rõ |
| Alias khác mapped column xử lý thế nào? | `@SqlResultSetMapping` + `@FieldResult` |
| FieldResult.name là tên gì? | **Tên persistent attribute Java** |
| FieldResult.column là tên gì? | **Label/alias ResultSet** |
| Cần nhiều entity trong một row? | Nhiều `@EntityResult`, mapping rõ |
| Cần entity + scalar? | `@EntityResult` + `@ColumnResult` |
| Chỉ cần vài cột? | DTO/`@ConstructorResult` hoặc scalar |
| @ConstructorResult tạo managed entity không? | Không nếu target là DTO thường |
| Composite ID có thể thiếu một phần khóa không? | Không |
| Inheritance có thể cần discriminator không? | Có |
| Native entity results có managed không? | Có trong persistence context phù hợp |
| Native query luôn refresh managed instance? | Không |
| SQL JOIN tự preload association? | Không mặc định |
| COUNT native trả Long chắc chắn không? | Không; phụ thuộc driver/provider hoặc mapping type |
| Pagination khi JOIN collection có thể lệch không? | Có, do nhiều rows trên một entity |
| Native SQL tự bảo vệ tenant/soft-delete không? | Không nên mặc định |
| Cần kiểm thử ở tầng nào? | Integration test với provider/schema/database phù hợp |

**Kết luận:** Khi ánh xạ **native query về entity**, điểm quan trọng nhất không phải là câu SQL chạy được, mà là ResultSet có **đủ và đúng thông tin để JPA dựng một entity theo mapping**. Hãy chọn đầy đủ ID, các cột persistent, version, FK và metadata về embedded/inheritance khi cần; dùng alias có kiểm soát; sử dụng `@SqlResultSetMapping`/`@EntityResult`/`@FieldResult` khi ResultSet phức tạp; và chuyển sang DTO nếu chỉ cần một tập cột rút gọn. Khi đó bạn tận dụng được sức mạnh native SQL mà vẫn giữ rõ ràng ranh giới giữa **SQL row**, **managed entity** và **projection** trong JPA.

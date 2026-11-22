# Thay annotation JPA bằng metadata Spring Data JDBC

Chuyển một ứng dụng từ JPA sang Spring Data JDBC không phải là thay import annotation theo tên tương tự. Hai framework có mô hình persistence khác nhau: JPA quản lý entity qua persistence context, quan hệ object và dirty checking; Spring Data JDBC tập trung vào aggregate, repository và các thao tác SQL tường minh hơn.

Khi chuyển đổi, cần ánh xạ lại ý nghĩa của domain model và schema database. Một số annotation có tên gần giống nhau như `@Table`, `@Column`, `@Id` và `@Version` nhưng thuộc package khác. Một số annotation JPA không có tương đương trực tiếp vì Spring Data JDBC không cung cấp lazy loading, persistence context, cascade graph hoặc association mapping kiểu ORM.

Bài học này hướng dẫn thay metadata JPA bằng metadata Spring Data JDBC, chuyển các quan hệ entity sang aggregate/collection phù hợp, cấu hình ID, embedded value object, auditing và converter, đồng thời chỉ ra những trường hợp phải thiết kế lại thay vì thay annotation máy móc.

## 1. Bắt đầu từ khác biệt mô hình persistence

### 1.1. JPA quản lý entity trong persistence context

Trong JPA, entity thường được quản lý bởi `EntityManager`. Khi entity đã được load vào persistence context, thay đổi field có thể được ghi xuống database khi flush/commit mà không cần gọi repository save cho từng thay đổi.

JPA cũng hỗ trợ:

- Association giữa entity qua `@OneToOne`, `@OneToMany`, `@ManyToOne` và `@ManyToMany`.
- Fetch strategy như LAZY/EAGER.
- Cascade operation và orphan removal.
- Dirty checking.
- Entity lifecycle callback.
- Inheritance mapping và nhiều chiến lược ORM khác.

### 1.2. Spring Data JDBC quản lý aggregate

Spring Data JDBC không duy trì persistence context và không theo dõi mọi thay đổi object trong một session dài hạn. Ứng dụng tải aggregate, thay đổi state rồi gọi repository save để lưu.

Mô hình được tổ chức theo aggregate root:

- Aggregate root là entry point để load/save một nhóm object được sở hữu.
- Object con trong aggregate được lưu cùng aggregate root theo mapping.
- Aggregate khác được tham chiếu bằng identifier; không tạo object association tự động giữa các aggregate.
- Không có lazy loading proxy kiểu JPA.
- Không có dirty checking tự động; cần gọi repository save.
- Schema database cần được quản lý bằng migration hoặc quy trình riêng.

Ví dụ:

```text
JPA:
Order --@OneToMany--> OrderLine
  |
  +-- EntityManager theo dõi entity graph

Spring Data JDBC:
PurchaseOrder (aggregate root)
  |
  +-- @MappedCollection --> OrderLine
  |
  +-- repository.save(purchaseOrder)

Customer (aggregate khác)
  ^
  |
  +-- customerId (identifier reference)
```

Trước khi sửa annotation, hãy quyết định object nào thuộc cùng aggregate và object nào là aggregate độc lập. Quyết định này ảnh hưởng cách lưu, transaction, concurrency và hiệu năng.

## 2. Các annotation cơ bản: Table, Id và Column

Một số annotation có tên giống JPA nhưng phải dùng annotation của Spring Data.

| Ý nghĩa | JPA | Spring Data JDBC |
| --- | --- | --- |
| Đánh dấu entity/table | `jakarta.persistence.Entity`, `Table` | `org.springframework.data.relational.core.mapping.Table` |
| Đánh dấu ID | `jakarta.persistence.Id` | `org.springframework.data.annotation.Id` |
| Ánh xạ tên cột | `jakarta.persistence.Column` | `org.springframework.data.relational.core.mapping.Column` |
| Bỏ qua property | `jakarta.persistence.Transient` | `org.springframework.data.annotation.Transient` |
| Optimistic version | `jakarta.persistence.Version` | `org.springframework.data.annotation.Version` |

Không dùng đồng thời hai loại annotation chỉ vì chúng có cùng tên đơn giản. IDE có thể tự import nhầm package khi cả JPA và Spring Data cùng có dependency trong giai đoạn chuyển tiếp.

### 2.1. @Table

JPA:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    // ...
}
```

Spring Data JDBC:

```java
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {
    // ...
}
```

`@Table` của Spring Data Relational xác định tên table cho aggregate/entity được mapping. Không cần `@Entity` của JPA; Spring Data JDBC không sử dụng annotation đó để quản lý mapping.

Nếu không khai báo `@Table`, Spring Data có thể suy ra tên table từ tên class theo naming strategy. Với schema hiện hữu hoặc quy ước tên cụ thể, nên khai báo tường minh để tránh sai khác giữa môi trường.

### 2.2. @Id

JPA:

```java
import jakarta.persistence.Id;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;

@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

Spring Data JDBC:

```java
import org.springframework.data.annotation.Id;

@Id
private Long id;
```

Spring Data JDBC không dùng `@GeneratedValue`. Với khóa identity do database sinh, cấu hình cột ID trong schema để database tạo giá trị khi insert. Khi entity mới có ID null, Spring Data JDBC có thể nhận biết trạng thái mới và lấy generated key theo khả năng của database/driver.

Ví dụ DDL minh họa:

```sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE
);
```

Không copy `GenerationType.IDENTITY`, `SEQUENCE` hoặc `TABLE` sang Spring Data JDBC. Nếu hệ thống dùng sequence hoặc cơ chế sinh ID đặc thù, hãy xác định rõ cơ chế database/driver và cách cung cấp ID trong ứng dụng; có thể cần custom ID generation trước khi save.

Nếu ứng dụng tự gán UUID hoặc ID khác trước khi gọi save, cần xem xét cách Spring Data JDBC xác định entity mới. Với ID khác null, framework có thể xem entity là đã tồn tại tùy chiến lược newness. Có thể dùng version property hoặc triển khai `Persistable` với `isNew()` nếu cần biểu diễn chính xác trạng thái insert/update.

### 2.3. @Column

JPA:

```java
import jakarta.persistence.Column;

@Column(name = "order_number", nullable = false, length = 40)
private String orderNumber;
```

Spring Data JDBC:

```java
import org.springframework.data.relational.core.mapping.Column;

@Column("order_number")
private String orderNumber;
```

`@Column` của Spring Data JDBC dùng để ánh xạ property sang tên cột. Các thuộc tính như `nullable`, `length` và `unique` trong JPA không được chuyển thành cùng loại schema-generation metadata ở đây.

Nullability, độ dài, unique constraint và kiểu dữ liệu cần được định nghĩa trong schema/migration:

```sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE
);
```

Spring Data JDBC tập trung mapping object với schema hiện có. Hãy quản lý DDL bằng Flyway, Liquibase hoặc công cụ schema provisioning của dự án.

## 3. Chuyển một entity JPA đơn giản

Ví dụ JPA:

```java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "full_name", nullable = false)
    private String fullName;

    @Column(nullable = false, unique = true)
    private String email;

    @Version
    private Long version;

    // Constructor, getters, setters.
}
```

Spring Data JDBC:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {

    @Id
    private Long id;

    @Column("full_name")
    private String fullName;

    private String email;

    @Version
    private Long version;

    // Constructor, getters và domain behavior.
}
```

Repository:

```java
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
```

Các điểm chuyển đổi:

- Bỏ `@Entity`.
- Dùng `@Table` của Spring Data Relational.
- Dùng `@Id` và `@Version` của Spring Data Commons.
- Dùng `@Column` của Spring Data Relational.
- Bỏ `@GeneratedValue` và chuyển ID generation sang schema/database hoặc cơ chế riêng.
- Chuyển constraint sang DDL/migration.
- Thay `JpaRepository` bằng repository abstraction phù hợp như `CrudRepository` hoặc `ListCrudRepository`.

Nếu cần phân trang/sort, dùng repository interface và query support phù hợp với Spring Data JDBC version đang sử dụng. Không giả định toàn bộ method của `JpaRepository` có mặt giống hệt trong repository JDBC.

## 4. Chuyển @OneToMany sang @MappedCollection

JPA thường biểu diễn quan hệ một-nhiều bằng association annotation:

```java
@OneToMany(
    mappedBy = "purchaseOrder",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines;
```

Trong Spring Data JDBC, nếu `OrderLine` thuộc quyền sở hữu của `PurchaseOrder`, biểu diễn collection trong aggregate bằng `@MappedCollection`.

```java
import org.springframework.data.relational.core.mapping.MappedCollection;

@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;

    @MappedCollection(
        idColumn = "purchase_order_id",
        keyColumn = "line_number"
    )
    private List<OrderLine> lines = new ArrayList<>();
}
```

Child entity:

```java
@Table("order_lines")
public class OrderLine {

    private String productCode;
    private Integer quantity;
    private BigDecimal unitPrice;

    // Constructor và accessor.
}
```

Schema minh họa:

```sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE
);

CREATE TABLE order_lines (
    purchase_order_id BIGINT NOT NULL,
    line_number INTEGER NOT NULL,
    product_code VARCHAR(50) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (purchase_order_id, line_number),
    CONSTRAINT fk_order_lines_order
        FOREIGN KEY (purchase_order_id)
        REFERENCES purchase_orders(id)
);
```

`idColumn` là cột trên bảng child chứa ID của aggregate root. `keyColumn` lưu key/index của collection khi cần phân biệt phần tử, ví dụ vị trí của phần tử trong List hoặc key của Map. Tên cột phải khớp schema thực tế.

### 4.1. @MappedCollection thể hiện ownership

Khi một collection được ánh xạ trong aggregate:

- Aggregate root là điểm truy cập để load và save collection.
- Child object được lưu cùng aggregate root theo persistence model.
- Không cần property back-reference tới root như `OrderLine.purchaseOrder` chỉ để JPA quản lý quan hệ.
- Foreign key nằm ở bảng child và trỏ về aggregate root.
- Việc thêm/xóa child nên đi qua domain method của aggregate.

Ví dụ:

```java
public void addLine(
        String productCode,
        int quantity,
        BigDecimal unitPrice) {
    if (quantity <= 0) {
        throw new IllegalArgumentException(
            "Quantity phải lớn hơn 0"
        );
    }

    lines.add(new OrderLine(
        productCode,
        quantity,
        unitPrice
    ));
}

public void removeLine(String productCode) {
    lines.removeIf(line ->
        line.getProductCode().equals(productCode)
    );
}
```

Sau khi thay đổi collection, gọi `repository.save(order)` để lưu aggregate. Spring Data JDBC không có dirty checking tự động như JPA.

### 4.2. @MappedCollection với Set, List và Map

`@MappedCollection` có thể tùy chỉnh tên cột tham chiếu aggregate và cột key/index:

```java
@MappedCollection(idColumn = "order_id")
private Set<OrderTag> tags = new LinkedHashSet<>();
```

Với Map:

```java
@MappedCollection(
    idColumn = "order_id",
    keyColumn = "attribute_name"
)
private Map<String, OrderAttribute> attributes =
    new LinkedHashMap<>();
```

Với List, key column có thể lưu vị trí phần tử. Hãy thiết kế kiểu dữ liệu và constraint của cột key phù hợp với collection semantics.

Không nên giả định thứ tự row trong database tự ổn định nếu không có key/index hoặc ORDER BY phù hợp. Nếu thứ tự là một phần của domain, cần lưu và truy xuất nó một cách tường minh.

## 5. Chuyển @ManyToOne và @ManyToMany

Không có cách thay trực tiếp mọi association JPA bằng một annotation Spring Data JDBC tương đương. Cần xem aggregate boundary.

### 5.1. @ManyToOne tới aggregate khác

JPA:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id")
private Customer customer;
```

Trong Spring Data JDBC, nếu `Customer` là aggregate riêng, thường lưu ID tham chiếu:

```java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("customer_id")
    private Long customerId;
}
```

Bảng `purchase_orders` giữ foreign key `customer_id`. Khi cần thông tin Customer, application service tải qua `CustomerRepository` hoặc query projection phù hợp.

```java
@Transactional(readOnly = true)
public OrderDetails getDetails(Long orderId) {
    PurchaseOrder order = orders.findById(orderId)
        .orElseThrow();

    Customer customer = customers.findById(order.getCustomerId())
        .orElseThrow();

    return new OrderDetails(order, customer);
}
```

Đây là hai aggregate được tải riêng. Không có lazy proxy tự động thay thế property `customer`.

### 5.2. @ManyToMany

JPA:

```java
@ManyToMany
@JoinTable(
    name = "product_categories",
    joinColumns = @JoinColumn(name = "product_id"),
    inverseJoinColumns = @JoinColumn(name = "category_id")
)
private Set<Category> categories;
```

Với Spring Data JDBC, cân nhắc mô hình hóa bảng liên kết thành association entity/aggregate riêng:

```java
@Table("product_category_links")
public class ProductCategoryLink {

    @Id
    private Long id;

    @Column("product_id")
    private Long productId;

    @Column("category_id")
    private Long categoryId;
}
```

Nếu quan hệ có thuộc tính như thứ tự, thời điểm gán, người gán hoặc trạng thái, association entity giúp biểu diễn nghiệp vụ rõ hơn.

Nếu bảng link thuộc quyền sở hữu của một aggregate root, có thể mô hình hóa nó như child trong aggregate bằng `@MappedCollection`. Nếu hai phía đều là aggregate độc lập, lưu ID tham chiếu và quản lý liên kết bằng một repository/service chuyên biệt.

### 5.3. @JoinColumn

`@JoinColumn` của JPA không có annotation tương đương một-một cho mọi quan hệ trong Spring Data JDBC.

- Với child collection, dùng `@MappedCollection(idColumn = "...")` trên property của aggregate root để chỉ tên FK ở bảng child.
- Với reference tới aggregate khác, ánh xạ cột ID bằng `@Column` hoặc naming convention.
- Với bảng link, mô hình hóa association row và khai báo FK bằng migration.

Không đặt `@JoinColumn` của JPA lên property Spring Data JDBC rồi mong framework tự tạo association mapping.
## 6. Chuyển @Embeddable và @Embedded

JPA dùng `@Embeddable` để định nghĩa value object và `@Embedded` để lưu thuộc tính của nó trong cùng bảng với entity sở hữu. Trong Spring Data JDBC, chỉ cần đánh dấu property bằng `@Embedded`; value type không cần `@Embeddable`.

Ví dụ Spring Data JDBC:

```java
import org.springframework.data.relational.core.mapping.Embedded;

public class Address {
    private String street;
    private String city;
    private String postalCode;
}

@Table("customers")
public class Customer {

    @Id
    private Long id;

    private String name;

    @Embedded(prefix = "shipping_")
    private Address shippingAddress;
}
```

Các cột được ánh xạ thành `shipping_street`, `shipping_city` và `shipping_postal_code`. Prefix giúp tránh trùng tên cột nếu aggregate có nhiều value object cùng kiểu, ví dụ địa chỉ giao hàng và địa chỉ thanh toán.

### 6.1. Xử lý value object rỗng

`@Embedded` hỗ trợ cấu hình hành vi khi tất cả cột của embedded object đều null:

```java
@Embedded(
    prefix = "shipping_",
    onEmpty = Embedded.OnEmpty.USE_NULL
)
private Address shippingAddress;
```

Với `USE_NULL`, nếu toàn bộ cột được prefix đều null, property được ánh xạ thành null. Với `USE_EMPTY`, framework tạo embedded object ngay cả khi các giá trị bên trong đều null. Chọn semantics phù hợp với domain và schema hiện có.

Nếu domain yêu cầu Address luôn tồn tại, hãy đảm bảo schema và validation giữ invariant đó. Annotation mapping không thay thế constraint NOT NULL hoặc kiểm tra nghiệp vụ.

## 7. Chuyển @ElementCollection và collection value

JPA có thể lưu collection value bằng `@ElementCollection` cùng `@CollectionTable`. Trong Spring Data JDBC, cần mô hình hóa collection theo cách phù hợp với relational mapping và aggregate ownership. Với collection phần tử có cấu trúc riêng hoặc cần key/index, tạo value type/child type và dùng `@MappedCollection`:

```java
@Table("customers")
public class Customer {

    @Id
    private Long id;

    @MappedCollection(
        idColumn = "customer_id",
        keyColumn = "phone_position"
    )
    private List<PhoneNumber> phoneNumbers =
        new ArrayList<>();
}

public class PhoneNumber {
    @Column("phone_number")
    private String value;
}
```

Schema có thể dùng khóa ghép gồm `customer_id` và `phone_position`. Cách thiết kế này làm rõ collection thuộc aggregate Customer và cho phép giữ thứ tự nếu đó là yêu cầu domain.

Với collection đơn giản, kiểm tra khả năng mapping type và converter của phiên bản Spring Data JDBC đang dùng. Nếu cần lưu thêm metadata cho mỗi phần tử, child class thường rõ ràng hơn một collection scalar.

## 8. Chuyển @Version và optimistic locking

JPA:

```java
@Version
private Long version;
```

Spring Data JDBC cũng hỗ trợ optimistic locking bằng annotation cùng tên nhưng package khác:

```java
import org.springframework.data.annotation.Version;

@Version
private Long version;
```

Khi save aggregate, Spring Data JDBC sử dụng version để phát hiện cập nhật cạnh tranh. Nếu version trong database không còn khớp với version mà aggregate đã đọc, thao tác có thể thất bại bằng `OptimisticLockingFailureException`.

Cột version phải tồn tại trong schema:

```sql
ALTER TABLE purchase_orders
ADD COLUMN version BIGINT NOT NULL DEFAULT 0;
```

Không dùng `jakarta.persistence.Version` cho entity Spring Data JDBC. Cũng không tự tăng version trong domain method nếu framework đang quản lý version cho repository save.

Nếu có custom SQL UPDATE trực tiếp, câu SQL đó phải tự thực hiện điều kiện version cũ và tăng version đúng cách. Custom SQL không tự chạy optimistic locking metadata của repository.

## 9. Chuyển auditing metadata

JPA có thể dùng entity listener và callback để điền created/modified fields. Spring Data JDBC có auditing support riêng.

```java
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;

public class Customer {

    @CreatedBy
    private String createdBy;

    @CreatedDate
    private Instant createdDate;

    @LastModifiedBy
    private String lastModifiedBy;

    @LastModifiedDate
    private Instant lastModifiedDate;
}
```

Bật auditing bằng cấu hình:

```java
@Configuration
@EnableJdbcAuditing
public class JdbcAuditingConfiguration {
}
```

Nếu cần actor hiện tại, cung cấp `AuditorAware`:

```java
@Bean
AuditorAware<String> auditorAware() {
    return () -> Optional.of("system");
}
```

Trong ứng dụng thực tế, lấy actor từ security context hoặc execution context phù hợp. Nếu cần thời gian có thể kiểm soát trong test, cấu hình `DateTimeProvider`.

Auditing chỉ chạy trên các lifecycle operation mà Spring Data JDBC quản lý. Một câu SQL trực tiếp qua JdbcTemplate hoặc custom statement không tự kích hoạt auditing callback. Nếu có direct SQL write, cần tự cập nhật audit columns hoặc dùng database trigger theo thiết kế thống nhất.

## 10. Chuyển converter và enum mapping

JPA thường dùng `@Convert`/`AttributeConverter` để chuyển Java type thành database type. Spring Data JDBC dùng Spring Data custom conversions.

Ví dụ domain enum được lưu dưới mã ngắn:

```java
public enum OrderStatus {
    PENDING,
    CONFIRMED,
    CANCELLED
}
```

Writing converter:

```java
@WritingConverter
public class OrderStatusWritingConverter
        implements Converter<OrderStatus, String> {

    @Override
    public String convert(OrderStatus source) {
        return switch (source) {
            case PENDING -> "P";
            case CONFIRMED -> "C";
            case CANCELLED -> "X";
        };
    }
}
```

Reading converter:

```java
@ReadingConverter
public class OrderStatusReadingConverter
        implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        return switch (source) {
            case "P" -> OrderStatus.PENDING;
            case "C" -> OrderStatus.CONFIRMED;
            case "X" -> OrderStatus.CANCELLED;
            default -> throw new IllegalArgumentException(
                "Unknown order status: " + source
            );
        };
    }
}
```

Đăng ký converter trong cấu hình Spring Data JDBC, ví dụ thông qua `AbstractJdbcConfiguration.userConverters()`:

```java
@Configuration
public class JdbcConversionConfiguration
        extends AbstractJdbcConfiguration {

    @Override
    protected List<?> userConverters() {
        return List.of(
            new OrderStatusWritingConverter(),
            new OrderStatusReadingConverter()
        );
    }
}
```

Tên hook/cấu hình cụ thể cần khớp phiên bản Spring Data Relational đang dùng. Trong Spring Boot, tránh tạo thêm nhiều conversion bean trùng nhau; hãy tích hợp converter theo cơ chế configuration mà ứng dụng đang sử dụng.

Không giả định converter JPA cũ tự được Spring Data JDBC gọi. Hãy kiểm tra cả hai chiều đọc/ghi và dữ liệu hiện hữu trong database.

## 11. @Transient và property không được lưu

JPA:

```java
@Transient
private BigDecimal calculatedTotal;
```

Spring Data JDBC:

```java
import org.springframework.data.annotation.Transient;

@Transient
private BigDecimal calculatedTotal;
```

Property đánh dấu transient không được ánh xạ vào cột. Có thể dùng cho giá trị dẫn xuất trong domain object hoặc dữ liệu chỉ tồn tại trong memory.

Không nhầm `@Transient` của Spring Data với `transient` keyword của Java. Khi chuyển đổi, hãy kiểm tra import và xác nhận property không xuất hiện trong generated SQL/mapping.

## 12. Các annotation JPA không có tương đương trực tiếp

| Annotation/capability JPA | Cách xử lý trong Spring Data JDBC |
| --- | --- |
| `@Entity` | Bỏ; dùng `@Table` nếu cần tên table rõ ràng. |
| `@GeneratedValue` | Dùng cơ chế ID do database hỗ trợ hoặc sinh ID trong application/custom code. |
| `@OneToMany` | Nếu child thuộc aggregate, dùng `@MappedCollection`. |
| `@ManyToOne` | Thường lưu foreign key dưới dạng ID; load aggregate khác riêng. |
| `@OneToOne` | Xác định value object, owned child hoặc aggregate riêng; không có thay thế annotation tổng quát. |
| `@ManyToMany` | Mô hình hóa association row/link entity và ownership rõ ràng. |
| `@JoinColumn` | Dùng `@MappedCollection(idColumn=...)` cho child hoặc `@Column` cho ID reference. |
| `@JoinTable` | Thiết kế association table và mapping child/aggregate riêng. |
| `fetch = LAZY/EAGER` | Không có lazy-loading proxy kiểu JPA; thiết kế query/load boundary tường minh. |
| `cascade` / `orphanRemoval` | Quản lý object thuộc aggregate qua root và gọi save; xác định lại ownership. |
| `@Embeddable` / `@AttributeOverride` | Dùng value type cùng `@Embedded(prefix=...)`. |
| `@ElementCollection` | Mô hình hóa collection thuộc aggregate bằng mapping phù hợp, thường là `@MappedCollection`. |
| `@EntityListeners` | Dùng Spring Data entity callbacks/auditing hoặc application service. |
| `@Convert` | Dùng Spring Data custom converters. |
| `@OrderColumn` | Dùng key/index column của `@MappedCollection` nếu thứ tự là dữ liệu domain. |
| `@Inheritance` / discriminator mapping | Thiết kế bảng và mapping cụ thể; không có ORM inheritance mapping tương đương tổng quát. |
| `@Formula` | Dùng query/projection/custom SQL để tính giá trị. |
| `@Temporal` | Ưu tiên kiểu Java Time và mapping JDBC tương ứng. |
| `@Lob` | Chọn SQL type và Java type phù hợp với database/driver; kiểm tra mapping thực tế. |

Không nên cố giữ nguyên toàn bộ object graph JPA rồi chỉ đổi annotation. Nếu domain phụ thuộc lazy association, cascade xuyên aggregate hoặc dirty checking, cần refactor application service và transaction boundary.

## 13. Repository và query metadata cũng cần đổi

JPA repository thường kế thừa `JpaRepository` và có thể dùng JPQL hoặc native query. Spring Data JDBC repository thường kế thừa `CrudRepository` hoặc `ListCrudRepository`:

```java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByStatus(OrderStatus status);
}
```

Với custom SQL, dùng `@Query` của Spring Data JDBC:

```java
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    @Query("""
        SELECT id, order_number, status, version
        FROM purchase_orders
        WHERE status = :status
        ORDER BY id
        """)
    List<PurchaseOrder> findByStatus(@Param("status") String status);
}
```

Query Spring Data JDBC là SQL làm việc với schema database. Nó không phải JPQL; không thể lấy câu JPQL dùng tên entity/property rồi chỉ đổi import annotation.

Nếu query trả DTO/projection, cần kiểm tra cách mapping cột sang constructor/property. Với join phức tạp, aggregate root hoặc báo cáo, có thể dùng custom repository/JdbcTemplate hoặc MyBatis tùy nhu cầu.

## 14. Ví dụ chuyển aggregate hoàn chỉnh

Giả sử JPA model hiện tại có PurchaseOrder, OrderLine và Customer:

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;

    @OneToMany(
        mappedBy = "purchaseOrder",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    @Version
    private Long version;
}
```

Trước khi chuyển, quyết định:

- PurchaseOrder là aggregate root.
- OrderLine thuộc quyền sở hữu của PurchaseOrder.
- Customer là aggregate riêng.
- PurchaseOrder giữ customer ID.
- ShippingAddress (nếu có) là value object có thể embedded.
- Các invariant của order được kiểm tra trong domain method.

Model Spring Data JDBC:

```java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("customer_id")
    private Long customerId;

    @MappedCollection(
        idColumn = "purchase_order_id",
        keyColumn = "line_number"
    )
    private List<OrderLine> lines = new ArrayList<>();

    @Version
    private Long version;

    public void addLine(OrderLine line) {
        lines.add(line);
    }

    public void removeLine(int index) {
        lines.remove(index);
    }
}
```

Child:

```java
public class OrderLine {

    @Column("product_code")
    private String productCode;

    private Integer quantity;

    @Column("unit_price")
    private BigDecimal unitPrice;
}
```

Application service:

```java
@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository orders;

    public PurchaseOrderService(
            PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public PurchaseOrder addLine(
            Long orderId,
            OrderLine line) {
        PurchaseOrder order = orders.findById(orderId)
            .orElseThrow();

        order.addLine(line);
        return orders.save(order);
    }
}
```

Đường ghi thể hiện rõ thao tác load, thay đổi aggregate và save. Nếu một use case cần thông tin Customer, service tải Customer riêng hoặc query một DTO kết hợp hai bảng.

## 15. Schema migration khi thay metadata

Annotation mapping và schema database phải đồng bộ. Spring Data JDBC không tự thay đổi schema chỉ vì code chuyển từ JPA annotation sang Spring Data annotation.

Một quy trình an toàn:

1. Kiểm kê table, column, foreign key, index và constraint hiện có.
2. Xác định aggregate root và ownership của từng child table.
3. Ghi lại ID generation, version, auditing và converter đang dùng.
4. Chuyển annotation và import theo từng aggregate.
5. Viết migration nếu tên table/column, key column hoặc constraint thay đổi.
6. Cập nhật query SQL, repository method và custom mapper.
7. Kiểm tra dữ liệu cũ tương thích với converter mới.
8. Chạy integration test trên database tương ứng production.
9. Chuyển application service từ dirty checking sang explicit save.
10. Triển khai theo giai đoạn tương thích nếu code cũ và mới cùng chạy trong rolling deployment.

Không đổi tên cột chỉ để khớp naming convention mới nếu không có nhu cầu. Giữ schema hiện tại và dùng `@Column`/`@MappedCollection` để ánh xạ đúng thường giảm rủi ro migration.

## 16. Kiểm thử sau khi chuyển đổi

### 16.1. Kiểm thử mapping cơ bản

Dùng `@DataJdbcTest` để xác nhận aggregate có thể insert, load và update:

```java
@DataJdbcTest
class PurchaseOrderRepositoryTest {

    @Autowired
    PurchaseOrderRepository orders;

    @Test
    void savesAndLoadsAggregate() {
        PurchaseOrder order = PurchaseOrder.create(42L);
        order.addLine(
            new OrderLine("SKU-1", 2, new BigDecimal("12.50"))
        );

        PurchaseOrder saved = orders.save(order);

        PurchaseOrder loaded =
            orders.findById(saved.getId()).orElseThrow();

        assertThat(loaded.getCustomerId()).isEqualTo(42L);
        assertThat(loaded.getLines()).hasSize(1);
    }
}
```

Schema test phải có table, foreign key và key column đúng như mapping. Nếu dùng migration tool trong production, cân nhắc chạy migration trong test để tránh test schema tự viết bị lệch.

### 16.2. Kiểm thử embedded value object

Xác nhận prefix column được đọc đúng, hai embedded object cùng kiểu không bị trùng cột, semantics khi tất cả embedded columns null đúng với `onEmpty` và value object được ghi đúng khi thay đổi.

### 16.3. Kiểm thử generated ID và assigned ID

Kiểm tra database sinh ID cho entity mới có ID null. Nếu dùng UUID/ID tự gán, kiểm tra chiến lược newness để repository insert thay vì update nhầm.

### 16.4. Kiểm thử optimistic locking và auditing

Tạo hai bản đọc cùng version, save một bản, xác nhận bản cũ bị conflict. Nếu auditing bật, kiểm tra created/modified fields được điền theo actor và clock đã cấu hình.

### 16.5. Kiểm thử query và transaction

Đảm bảo custom SQL dùng đúng tên cột sau chuyển đổi, các operation cần atomicity nằm trong cùng transaction, direct SQL không vô tình bỏ qua version/audit behavior, aggregate child được lưu/xóa theo ownership đã chọn và không còn code phụ thuộc lazy loading hoặc EntityManager.

## 17. Checklist chuyển đổi JPA sang Spring Data JDBC

| Hạng mục | Câu hỏi cần trả lời |
| --- | --- |
| Aggregate boundary | Object nào là root, object nào là child, object nào là aggregate khác? |
| Table/column | Đã đổi sang Spring Data Relational `@Table`/`@Column` đúng package chưa? |
| ID | Database hay application sinh ID? Entity mới được nhận diện thế nào? |
| Version | Đã dùng `org.springframework.data.annotation.Version` và có cột version chưa? |
| One-to-many | Collection child đã chuyển sang `@MappedCollection` với FK/key column đúng chưa? |
| Many-to-one | Có chuyển object association thành identifier reference khi cần không? |
| Many-to-many | Association table có ownership và mapping rõ ràng chưa? |
| Embedded | Value object đã dùng `@Embedded` và prefix phù hợp chưa? |
| Converter | Reading/writing conversion đã được đăng ký và test hai chiều chưa? |
| Auditing | Đã bật `@EnableJdbcAuditing` và cung cấp auditor/time provider chưa? |
| Repository | Đã bỏ JpaRepository/JPQL và chuyển sang repository/query JDBC chưa? |
| Lifecycle | Đã thay dirty checking/cascade/lazy behavior bằng service và aggregate method chưa? |
| Schema | Migration có giữ constraint, index, foreign key và dữ liệu cũ không? |
| Test | Integration test chạy trên database/driver tương ứng production chưa? |

## 18. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Entity không được mapping | Còn dùng `@Entity` hoặc annotation JPA. | Dùng Spring Data `@Table`, `@Id`, `@Column`. |
| Import `@Id` sai package | IDE chọn `jakarta.persistence.Id`. | Chọn `org.springframework.data.annotation.Id`. |
| ID không được sinh | Chờ `@GeneratedValue` hoạt động trong Spring Data JDBC. | Cấu hình identity/default ở database hoặc ID generator riêng. |
| Repository update thay vì insert | ID tự gán khiến entity bị xem là đã tồn tại. | Xem version/newness và triển khai `Persistable` khi cần. |
| Child table không được lưu | Thiếu `@MappedCollection` hoặc sai FK column. | Kiểm tra aggregate ownership, `idColumn`, `keyColumn` và schema. |
| Customer object không tự load | Kỳ vọng `@ManyToOne`/lazy proxy. | Lưu customer ID và load/query riêng. |
| Thay đổi field không được ghi | Kỳ vọng dirty checking JPA. | Gọi repository `save` trong transaction phù hợp. |
| Xóa child không như mong đợi | Kỳ vọng cascade/orphanRemoval của JPA. | Thay đổi collection qua aggregate root rồi save; kiểm tra mapping. |
| Embedded columns bị trùng | Nhiều value object cùng tên property. | Dùng `@Embedded(prefix = "...")`. |
| Constraint không được tạo | Dùng thuộc tính nullable/unique của JPA Column. | Định nghĩa constraint trong migration. |
| JPQL không chạy | Dùng lại query JPA trong repository JDBC. | Viết SQL theo tên table/column thật. |
| Auditing không cập nhật | Chưa bật auditing hoặc đang ghi bằng direct SQL. | Cấu hình auditing và xử lý direct SQL riêng. |
| Enum đọc sai | Converter JPA không được Spring Data JDBC sử dụng. | Đăng ký reading/writing converters và test dữ liệu cũ. |

> **Chuyển JPA sang Spring Data JDBC là chuyển mô hình persistence, không chỉ đổi annotation.** Dùng `@Table`, `@Column`, `@Id`, `@Version` của Spring Data; dùng `@MappedCollection` cho child thuộc aggregate và `@Embedded` cho value object. Tham chiếu aggregate khác bằng ID, quản lý schema bằng migration và thay dirty checking/cascade/lazy loading bằng domain method, repository save và query tường minh.

### Tài liệu tham khảo

- [Spring Data Relational — Mapping](https://docs.spring.io/spring-data/relational/reference/mapping.html): metadata mapping và quy ước ánh xạ object-relational.
- [Spring Data JDBC — Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): aggregate, embedded objects và mapped collections.
- [Spring Data JDBC — Entity Persistence](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): insert/update, ID và optimistic locking.
- [Spring Data JDBC — Custom Conversions](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): chuyển đổi Java type và JDBC type.
- [Spring Data JDBC — Auditing](https://docs.spring.io/spring-data/relational/reference/jdbc/auditing.html): auditing annotations và cấu hình auditor.
- [Spring Data JDBC — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): repository query và custom SQL.
- [Spring Data Commons — Persistable API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Persistable.html): tùy chỉnh xác định entity mới.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/): semantics của entity, relationship, lifecycle và mapping JPA.

# @Entity, @Table và quan hệ giữa tên Entity với tên bảng

Trong JPA, **tên Entity và tên bảng database là hai định danh khác nhau**. Entity name được dùng trong JPQL và các API JPA; table name xác định bảng vật lý được ánh xạ trong database. Một lớp Java có thể giữ tên `PurchaseOrder`, được khai báo entity name là `OrderRecord`, đồng thời ánh xạ tới bảng `purchase_orders`.

Hiểu đúng hai lớp tên này giúp tránh lỗi truy vấn, lỗi mapping, xung đột tên bảng và sai lệch giữa code với schema. Bài học sử dụng Spring Data JPA với Jakarta Persistence trong Spring Boot 3.x.

## 1. Phân biệt class name, entity name và table name

Có ba khái niệm cần tách biệt:

| Khái niệm | Ví dụ | Được dùng ở đâu |
|---|---|---|
| Java class name | `PurchaseOrder` | Java type, constructor, generic của repository |
| JPA entity name | `OrderRecord` | JPQL, tên entity trong metadata JPA và một số API truy vấn |
| Database table name | `purchase_orders` | SQL, schema database, migration và công cụ quản trị DB |

Nếu không khai báo tên riêng, entity name mặc định là tên lớp không kèm package. Ví dụ lớp `com.example.orders.PurchaseOrder` có entity name mặc định là `PurchaseOrder`.

Annotation `@Entity(name = "...")` cho phép đổi entity name. Annotation `@Table(name = "...")` chỉ định bảng database mà entity ánh xạ tới.

Ví dụ:

```java
@Entity(name = "OrderRecord")
@Table(name = "purchase_orders")
public class PurchaseOrder {
    // ...
}
```

Trong ví dụ này:

- Java code vẫn khai báo kiểu `PurchaseOrder`.
- JPQL tham chiếu entity bằng tên `OrderRecord`.
- SQL truy cập bảng `purchase_orders`.
- Spring Data repository vẫn khai báo generic bằng kiểu Java `PurchaseOrder`.

Đổi entity name không đổi tên class Java và cũng không đổi tên bảng. Đổi table name không tự đổi entity name.

## 2. @Entity khai báo một persistent entity

Một class được JPA quản lý phải được đánh dấu bằng `@Entity`. Annotation thuộc package `jakarta.persistence` trong Jakarta Persistence, được dùng với Spring Boot 3.x.

```java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Customer() {
    }
}
```

Các quy tắc cơ bản của entity:

1. Class phải là một class độc lập hoặc class static phù hợp; không khai báo entity là `final`.
2. Entity phải có constructor không tham số `public` hoặc `protected`, để provider có thể khởi tạo entity.
3. Entity phải có primary key được đánh dấu bằng `@Id` hoặc `@EmbeddedId`.
4. Các thuộc tính persistent phải tuân theo quy tắc truy cập JPA. Nếu dùng field access, provider đọc/ghi field; nếu dùng property access, provider sử dụng getter/setter.
5. Không nên dùng `final` cho persistent fields hoặc methods cần provider quản lý/proxy.
6. Không nên đánh dấu mọi thuộc tính là persistent một cách vô thức. Dùng `@Transient` cho trạng thái chỉ phục vụ xử lý trong bộ nhớ và không lưu vào database.

Entity là đối tượng có identity và vòng đời persistence. Nó khác DTO, request model hoặc class tiện ích chỉ chứa dữ liệu. Không đánh dấu mọi class Java bằng `@Entity`; chỉ các đối tượng thuộc mô hình dữ liệu cần được JPA quản lý mới nên là entity.

### 2.1. Tên entity mặc định

Nếu không truyền thuộc tính `name`, tên entity mặc định là tên đơn giản của class:

```java
@Entity
public class PurchaseOrder {
    @Id
    private Long id;
}
```

Entity name mặc định là `PurchaseOrder`, không phải `com.example.orders.PurchaseOrder`. Vì entity name được dùng trong JPQL, hai entity trong cùng persistence unit không nên có entity name trùng nhau. Nếu hai module có class cùng tên, hãy cân nhắc đặt entity name rõ ràng hoặc tách persistence unit theo ranh giới dữ liệu phù hợp.

### 2.2. Đặt entity name tường minh

```java
@Entity(name = "OrderRecord")
public class PurchaseOrder {
    @Id
    private Long id;
}
```

Tên trong `@Entity(name = "OrderRecord")` là tên logic trong JPA. Nó không phải tên table và không phải tên Spring bean. Tên này cần duy nhất trong persistence unit để JPQL có thể phân biệt entity.

Không nên đổi entity name tùy tiện khi ứng dụng có JPQL string, named query, native mapping hoặc code dùng metadata JPA tham chiếu tên cũ. Nếu đổi, cần tìm và cập nhật toàn bộ nơi sử dụng.

## 3. @Table ánh xạ entity tới bảng vật lý

`@Table` chỉ định table mà entity được lưu. Nếu bỏ qua, JPA dùng quy tắc tên bảng mặc định dựa trên entity name; kết quả vật lý còn có thể chịu ảnh hưởng của implicit/physical naming strategy do provider hoặc Spring Boot cấu hình.

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;
}
```

Khi khai báo `name = "purchase_orders"`, ta thể hiện rõ hợp đồng giữa entity và database. Cách này hữu ích khi tên class theo quy ước Java camelCase nhưng tên bảng theo quy ước SQL snake_case, hoặc khi database đã có schema được quản lý độc lập.

### 3.1. Các thuộc tính thường dùng của @Table

| Thuộc tính | Ý nghĩa | Ví dụ |
|---|---|---|
| `name` | Tên bảng | `purchase_orders` |
| `schema` | Schema chứa bảng | `sales` |
| `catalog` | Catalog chứa bảng, tùy database | `shop_catalog` |
| `uniqueConstraints` | Khai báo unique constraint ở cấp bảng | `order_number` không trùng |
| `indexes` | Khai báo index ở cấp bảng | Index trên `created_at` |

Ví dụ đầy đủ hơn:

```java
@Entity
@Table(
    name = "purchase_orders",
    schema = "sales",
    uniqueConstraints = {
        @UniqueConstraint(
            name = "uk_purchase_orders_order_number",
            columnNames = "order_number"
        )
    },
    indexes = {
        @Index(
            name = "idx_purchase_orders_created_at",
            columnList = "created_at"
        )
    }
)
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_number", nullable = false, length = 40)
    private String orderNumber;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected PurchaseOrder() {
    }
}
```

Trong ví dụ, `schema = "sales"` yêu cầu bảng nằm trong schema sales của database. Schema phải tồn tại hoặc được quản lý bởi migration/cấu hình triển khai. Không phải mọi database đều có cách tổ chức schema/catalog giống nhau.

`uniqueConstraints` và `indexes` là metadata mapping để provider có thể sử dụng khi tạo schema. Chúng không tự bảo đảm rằng migration production đã tạo constraint/index. Nếu Flyway hoặc Liquibase là nguồn quản lý schema, migration vẫn phải khai báo unique constraint và index tương ứng.

### 3.2. @Table và @Column làm hai việc khác nhau

`@Table` ánh xạ entity tới bảng. `@Column` ánh xạ một thuộc tính persistent tới cột trong bảng đó.

```java
@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "product_code", nullable = false, unique = true, length = 30)
    private String code;

    @Column(name = "display_name", nullable = false, length = 160)
    private String name;

    @Column(name = "current_price", nullable = false, precision = 19, scale = 2)
    private BigDecimal currentPrice;
}
```

Ở đây `products` là table; `product_code`, `display_name` và `current_price` là column. Tên column trong `@Column` cũng là tên database, không phải tên thuộc tính Java.

Một unique constraint đơn cột có thể khai báo bằng `@Column(unique = true)`. Nếu cần constraint nhiều cột hoặc muốn đặt tên constraint, dùng `@Table(uniqueConstraints = ...)`. Tránh khai báo trùng lặp cùng một constraint ở nhiều chỗ mà không có lý do.

## 4. Tên mặc định và naming strategy

Nếu không khai báo `@Table(name = ...)`, provider cần suy ra tên bảng từ mapping. Spring Boot/Hibernate có thể áp dụng hai lớp quy tắc:

- **Implicit naming strategy:** quyết định tên logic khi mapping không chỉ định tên rõ ràng.
- **Physical naming strategy:** biến tên logic thành tên vật lý phù hợp với quy ước database.

Ví dụ tên Java `purchaseOrder` có thể được chuyển thành tên vật lý `purchase_order` theo naming strategy camelCase sang snake_case. Tên thuộc tính `createdAt` có thể thành `created_at`.

Không nên giả định mọi dự án hoặc provider đều dùng cùng một quy tắc. Naming strategy có thể được tùy chỉnh bằng cấu hình Hibernate. Một entity chạy được ở môi trường local có thể lỗi khi sang môi trường khác nếu schema và naming strategy không thống nhất.

Để kiểm soát mapping:

1. Kiểm tra cấu hình implicit và physical naming strategy của ứng dụng.
2. Xem SQL Hibernate sinh ra hoặc metadata database.
3. Đối chiếu tên table/column với migration.
4. Với bảng có tên legacy, tên viết tắt, tên chứa từ khóa hoặc quy tắc đặc biệt, khai báo `@Table(name = ...)` và `@Column(name = ...)` tường minh.

Ví dụ cấu hình Hibernate có thể đặt physical naming strategy riêng:

```yaml
spring:
  jpa:
    hibernate:
      naming:
        physical-strategy: org.hibernate.boot.model.naming.CamelCaseToUnderscoresNamingStrategy
```

Đây là class của Hibernate. Chỉ cấu hình khi muốn chọn rõ quy tắc đó và đã kiểm tra ảnh hưởng lên toàn bộ mapping. Không đổi naming strategy giữa một hệ thống đã có schema mà chưa kiểm tra migration, vì thay đổi có thể làm provider tìm bảng/cột theo tên khác.

## 5. JPQL dùng entity name, SQL dùng table name

Đây là khác biệt dễ gây lỗi nhất khi dùng `@Entity(name)` và `@Table(name)`.

Giả sử mapping:

```java
@Entity(name = "OrderRecord")
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    @Column(name = "order_number")
    private String orderNumber;
}
```

JPQL tham chiếu entity name và thuộc tính Java:

```java
@Query("""
    select o
    from OrderRecord o
    where o.orderNumber = :orderNumber
    """)
Optional<PurchaseOrder> findByOrderNumber(
    @Param("orderNumber") String orderNumber
);
```

Trong JPQL:

- `OrderRecord` là entity name.
- `orderNumber` là thuộc tính Java.
- Không dùng `purchase_orders` hoặc `order_number` trong câu JPQL trên.

Native SQL tham chiếu tên bảng và cột:

```java
@Query(
    value = """
        select *
        from purchase_orders
        where order_number = :orderNumber
        """,
    nativeQuery = true
)
Optional<PurchaseOrder> findNativeByOrderNumber(
    @Param("orderNumber") String orderNumber
);
```

Trong native SQL:

- `purchase_orders` là table name.
- `order_number` là column name.
- Cú pháp và hàm SQL phụ thuộc database.

Spring Data derived query dựa trên tên thuộc tính Java, không dựa trên tên bảng:

```java
Optional<PurchaseOrder> findByOrderNumber(String orderNumber);
```

Spring Data phân tích method name theo property của entity rồi tạo query phù hợp với JPA provider. Vì vậy, đổi `@Table(name = ...)` thường không cần đổi derived method, còn đổi tên thuộc tính Java có thể ảnh hưởng method name và JPQL.

## 6. Quan hệ entity sử dụng tên bảng và cột ở đâu?

Khi ánh xạ quan hệ, các annotation tham chiếu tới thuộc tính Java hoặc tên database tùy annotation:

- `mappedBy` nhận tên thuộc tính Java ở owning side.
- `@JoinColumn(name = ...)` nhận tên cột khóa ngoại trong database.
- `@JoinTable(name = ...)` nhận tên bảng trung gian trong database.
- JPQL path expression sử dụng tên thuộc tính Java.

Ví dụ quan hệ đơn hàng - khách hàng:

```java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToMany(mappedBy = "customer")
    private List<PurchaseOrder> orders = new ArrayList<>();
}

@Entity(name = "OrderRecord")
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;
}
```

Ở đây:

- `mappedBy = "customer"` trỏ đến field `customer` trong PurchaseOrder.
- `@JoinColumn(name = "customer_id")` chỉ định cột khóa ngoại ở bảng `purchase_orders`.
- `Customer` và `OrderRecord` là entity name trong JPQL nếu không đổi tên Customer.
- `customers` và `purchase_orders` là tên bảng vật lý.

JPQL lấy đơn theo khách hàng:

```java
select o
from OrderRecord o
where o.customer.id = :customerId
```

Câu SQL tương ứng có thể truy cập `purchase_orders.customer_id`, nhưng JPQL không cần biết tên cột đó. Provider dịch mapping thành SQL.

## 7. Tên bảng đặc biệt, từ khóa và chữ hoa/chữ thường

Tránh đặt table hoặc column name trùng từ khóa SQL như `order`, `user`, `group`, `select`. Một số database chấp nhận khi quote identifier, nhưng quy tắc quote và phân biệt hoa/thường khác nhau theo hệ quản trị.

Ví dụ, nếu bảng hiện hữu có tên `order`, có thể phải dùng quoting theo dialect hoặc cấu hình mapping tương ứng. Tuy nhiên, tên như `purchase_orders` thường dễ dùng và ít phụ thuộc database hơn.

Các identifier được quote có thể bị phân biệt chữ hoa/chữ thường tùy database. PostgreSQL, chẳng hạn, xử lý identifier không quote theo quy tắc chuyển chữ thường; identifier có quote giữ nguyên chữ hoa/thường. Vì vậy, không tùy tiện trộn `PurchaseOrders`, `purchase_orders` và `"PurchaseOrders"`.

Với schema legacy:

1. Xác nhận chính xác tên bảng/cột từ database hoặc migration.
2. Xác nhận schema/catalog và quyền của user kết nối.
3. Khai báo tên mapping khớp chính xác.
4. Chạy kiểm thử khởi tạo EntityManagerFactory và repository query trên database cùng loại.
5. Không đổi tên bảng trong annotation nếu chưa có migration hoặc kế hoạch tương thích schema.

## 8. @Table không phải annotation dành cho mọi class

Chỉ entity mới ánh xạ tới bảng thông qua `@Table`. Một số loại mapping khác có hành vi riêng:

| Annotation / loại class | Có entity identity riêng? | Có bảng riêng mặc định? |
|---|---:|---:|
| `@Entity` | Có | Có bảng mapping |
| `@MappedSuperclass` | Không | Không |
| `@Embeddable` | Không | Không; các field được nhúng vào entity sở hữu |
| `@Embedded` | Không tạo entity mới | Dùng các cột của bảng entity sở hữu |

Ví dụ một mapped superclass chứa field dùng chung:

```java
@MappedSuperclass
public abstract class AuditableEntity {

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at")
    private Instant updatedAt;
}

@Entity
@Table(name = "products")
public class Product extends AuditableEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
}
```

`AuditableEntity` không có bảng riêng. Các thuộc tính persistent của nó được đưa vào mapping của entity con Product. `@Table(name = "products")` thuộc về Product.

Với inheritance giữa các entity, chiến lược `@Inheritance` quyết định cách hierarchy được lưu: SINGLE_TABLE, JOINED hoặc TABLE_PER_CLASS. Không thể kết luận mỗi class con luôn có một bảng độc lập; cần đọc chiến lược inheritance và mapping cụ thể.

## 9. Named query và các vị trí tham chiếu entity name

Ngoài JPQL viết trong `@Query`, entity name còn xuất hiện trong named query:

```java
@Entity(name = "OrderRecord")
@Table(name = "purchase_orders")
@NamedQuery(
    name = "OrderRecord.findByStatus",
    query = """
        select o
        from OrderRecord o
        where o.status = :status
        """
)
public class PurchaseOrder {

    @Id
    private Long id;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;
}
```

Named query được đăng ký với tên truy vấn riêng `OrderRecord.findByStatus`, còn phần JPQL vẫn dùng entity name `OrderRecord`. Tên named query là định danh truy vấn, không phải tên bảng.

Khi đổi entity name, cần rà soát:

- JPQL trong `@Query`.
- `@NamedQuery` và `@NamedQueries`.
- `@NamedEntityGraph` nếu có tham chiếu entity/attribute metadata liên quan.
- JPQL trong code dùng EntityManager.
- Các cấu hình hoặc thư viện truy vấn động tham chiếu tên entity.

Native query và migration cần rà soát table/column name thay vì entity name.

## 10. Đồng bộ mapping với schema migration

Trong dự án có Flyway hoặc Liquibase, migration là nơi mô tả schema thực tế. Annotation JPA mô tả cách entity ánh xạ vào schema đó. Hai nguồn phải thống nhất.

Ví dụ migration SQL:

```sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL,
    customer_id BIGINT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uk_purchase_orders_order_number UNIQUE (order_number)
);

CREATE INDEX idx_purchase_orders_created_at
    ON purchase_orders (created_at);
```

Mapping tương ứng cần dùng đúng tên:

```java
@Entity
@Table(
    name = "purchase_orders",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_purchase_orders_order_number",
        columnNames = "order_number"
    ),
    indexes = @Index(
        name = "idx_purchase_orders_created_at",
        columnList = "created_at"
    )
)
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_number", nullable = false, length = 40)
    private String orderNumber;

    @Column(name = "customer_id", nullable = false)
    private Long customerId;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;
}
```

Đây là ví dụ mapping tối giản để minh họa tên; nếu customer_id là quan hệ tới Customer thì nên dùng association `@ManyToOne` và `@JoinColumn` thay cho field Long trong mô hình nghiệp vụ thực tế. Migration cũng cần tạo foreign key tới bảng customers nếu quy tắc dữ liệu yêu cầu.

Không dựa vào việc `@Table` hoặc `@Column` tự tạo bảng khi production đang dùng `ddl-auto=validate`. Validate chỉ kiểm tra tương thích; nó không tạo hoặc sửa schema. Các thay đổi cần được đưa vào migration và triển khai theo thứ tự.

## 11. Kiểm tra mapping khi ứng dụng khởi động

Lỗi sai table name hoặc column name thường được phát hiện khi Hibernate khởi tạo EntityManagerFactory, khi validate schema hoặc khi query thực thi. Có thể xác minh theo các bước:

1. Kiểm tra entity package có được scan bởi đúng persistence unit không.
2. Kiểm tra entity name và table name riêng biệt.
3. Kiểm tra physical naming strategy có biến đổi tên logic không.
4. Kiểm tra schema/catalog và quyền database user.
5. Kiểm tra migration đã tạo đúng table, column, constraint và index.
6. Chạy repository test để xác nhận JPQL, derived query và native query.

Một repository test đơn giản:

```java
@DataJpaTest
class PurchaseOrderRepositoryTest {

    @Autowired
    private PurchaseOrderRepository repository;

    @Test
    void findsOrderByOrderNumber() {
        PurchaseOrder order = new PurchaseOrder();
        order.setOrderNumber("PO-1001");
        repository.saveAndFlush(order);

        Optional<PurchaseOrder> result =
                repository.findByOrderNumber("PO-1001");

        assertThat(result).isPresent();
    }
}
```

Đây là khung minh họa; entity thực tế có thể yêu cầu thêm các field bắt buộc như customer, status hoặc createdAt. Bài kiểm thử cần khởi tạo đầy đủ dữ liệu hợp lệ theo invariant của entity. `saveAndFlush` giúp đẩy SQL xuống database trong test để nhiều lỗi mapping xuất hiện ngay tại điểm kiểm tra.

Với native query, nên kiểm thử trên cùng loại database với production. H2 có thể khác về reserved word, identifier case, kiểu dữ liệu, function và dialect nên không đủ để xác nhận mọi native SQL.

## 12. Những nhầm lẫn phổ biến

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| @Entity(name) là tên bảng | Đây là entity name dùng trong JPA/JPQL |
| @Table(name) là tên entity | Đây là tên bảng database |
| JPQL dùng table và column name | JPQL dùng entity name và property name |
| Native SQL dùng entity name | Native SQL dùng table và column của database |
| Repository generic phải dùng entity name | Generic repository dùng Java class, ví dụ JpaRepository<PurchaseOrder, Long> |
| mappedBy nhận tên cột khóa ngoại | mappedBy nhận tên field/property ở owning side |
| @JoinColumn nhận tên field Java | name là tên cột database |
| @Table tự tạo schema production | Việc tạo schema phụ thuộc DDL generation hoặc migration |
| Đổi table name thì phải đổi JPQL entity name | Hai định danh độc lập; chỉ sửa nơi tham chiếu tương ứng |
| Mọi class có @MappedSuperclass đều có bảng | Mapped superclass không có bảng riêng |

## 13. Bài tập thực hành

1. Tạo entity `PurchaseOrder` với entity name mặc định và table name `purchase_orders`.
2. Viết JPQL truy vấn theo entity name mặc định và property `orderNumber`.
3. Đổi entity name thành `OrderRecord`; cập nhật JPQL và named query, giữ nguyên tên class và table.
4. Viết native query truy cập `purchase_orders.order_number`; so sánh với JPQL.
5. Khai báo `@Table(schema = "sales")` và kiểm tra SQL được sinh ra trên database có schema sales.
6. Tạo unique constraint cho `order_number` và index cho `created_at`; đối chiếu annotation với migration.
7. Dùng `@MappedSuperclass` cho auditing fields và xác nhận bảng entity con chứa các cột được kế thừa.
8. Cấu hình `ddl-auto=validate`, cố ý đổi một tên column trong mapping rồi quan sát lỗi khởi động hoặc truy vấn.
9. Thử một derived query sau khi đổi entity name; xác nhận method vẫn dựa trên property Java.
10. Chạy integration test trên database cùng loại với môi trường triển khai.

**Nguyên tắc xuyên suốt:** class name là kiểu Java; entity name là định danh JPA được JPQL sử dụng; table name là định danh vật lý trong database. `@Entity` khai báo entity, `@Table` ánh xạ entity tới bảng, `@Column` ánh xạ thuộc tính tới cột. Khi viết query, hãy chọn đúng hệ tên: JPQL dùng entity/property; native SQL dùng table/column.

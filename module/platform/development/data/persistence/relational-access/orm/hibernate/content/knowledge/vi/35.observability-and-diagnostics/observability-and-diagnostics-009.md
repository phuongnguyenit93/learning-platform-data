# Chẩn đoán lỗi ánh xạ, ràng buộc, kiểu dữ liệu hoặc tham chiếu không tồn tại

## 1. Bắt đầu từ triệu chứng và thời điểm lỗi xuất hiện

Khi Hibernate báo lỗi trong lúc đọc hoặc ghi dữ liệu, thông báo ngoài cùng thường chỉ nói rằng một thao tác persistence thất bại. Nguyên nhân thật có thể nằm ở mapping entity, schema database, kiểu JDBC, ràng buộc quan hệ, transaction hoặc dữ liệu đã có từ trước.

Ví dụ, một lệnh `save()` có thể chạy qua mà không thấy exception, nhưng đến lúc transaction flush/commit mới xuất hiện lỗi `constraint violation`. Một association có thể được gán ID mà không kiểm tra bản ghi đích tồn tại; lỗi chỉ xuất hiện khi Hibernate cần khởi tạo proxy. Một entity có annotation `@Entity` vẫn có thể không được quản lý bởi `EntityManagerFactory` mà repository đang sử dụng.

Trước khi sửa, hãy xác định **lỗi xảy ra ở giai đoạn nào**:

| Giai đoạn | Triệu chứng thường gặp | Khu vực cần xem |
|---|---|---|
| Application startup | `Not a managed type`, lỗi mapping, không tạo được EntityManagerFactory | Entity scanning, annotation, mapping metadata, dialect |
| Tạo query | Không nhận ra entity/property, SQL grammar error | JPQL/HQL, tên property, table/column mapping |
| Load entity | Không tìm thấy hàng, lỗi convert type, lazy proxy | ID, FK, schema, converter, association |
| Persist/update | Transient reference, duplicate key, not-null, type mismatch | Cascade, identifier, constraints, JDBC type |
| Flush/commit | Lỗi xuất hiện muộn, transaction rollback-only | SQL thực thi, constraint, optimistic locking |
| Truy cập association | EntityNotFoundException, LazyInitializationException | FK stale, proxy, fetch plan, persistence context |
| Concurrent writes | Optimistic lock, deadlock, lock timeout | @Version, transaction order, indexes, isolation |

Đừng bắt đầu bằng cách đổi `ddl-auto` sang `update`, tắt constraint hoặc bắt exception rồi tiếp tục. Trước tiên cần tìm ra **câu SQL và điều kiện dữ liệu cụ thể** gây lỗi.

## 2. Đọc exception chain, không chỉ dòng log đầu tiên

Spring và Hibernate thường bọc exception từ tầng thấp lên tầng cao:

```text
Service method
  |
  v
Spring Data repository / @Repository
  |
  v
Spring DataAccessException
  |
  v
JPA PersistenceException / Hibernate exception
  |
  v
JDBC SQLException
  |
  +-- SQLState
  +-- vendor error code
  +-- database message
```

Một log có thể bắt đầu bằng:

```text
org.springframework.dao.DataIntegrityViolationException:
could not execute statement
```

Nhưng nguyên nhân có ích hơn có thể nằm sâu bên dưới:

```text
Caused by: org.hibernate.exception.ConstraintViolationException:
could not execute statement

Caused by: org.postgresql.util.PSQLException:
ERROR: duplicate key value violates unique constraint
```

Khi điều tra, ghi lại:

- Toàn bộ exception chain và stack trace có liên quan.
- Tên constraint/table/column nếu database cung cấp.
- SQLState và vendor error code.
- SQL statement đã thực thi, với các giá trị nhạy cảm được redaction.
- Tenant, database/schema và transaction boundary liên quan.
- Phiên bản Hibernate, JDBC driver và DBMS.

Thông báo `could not execute statement` tự nó chưa cho biết lỗi là unique constraint, FK, sai kiểu dữ liệu hay mất kết nối. Cần đi đến `SQLException` hoặc thông tin tương đương của provider.

## 3. Phân biệt các loại exception có tên gần giống nhau

Tên exception có thể gây nhầm:

| Exception | Nguồn | Ý nghĩa |
|---|---|---|
| `org.hibernate.exception.ConstraintViolationException` | Hibernate JDBC exception conversion | Database từ chối statement do constraint |
| `jakarta.validation.ConstraintViolationException` | Jakarta Bean Validation | Object vi phạm validation constraint như @NotNull, @Size |
| `jakarta.persistence.PersistenceException` | Jakarta Persistence | Lỗi persistence tổng quát |
| `org.springframework.dao.DataIntegrityViolationException` | Spring DAO abstraction | Lỗi integrity được dịch từ persistence/JDBC |
| `org.hibernate.StaleObjectStateException` | Hibernate | State/row count không còn như Hibernate kỳ vọng |
| `jakarta.persistence.OptimisticLockException` | JPA | Optimistic lock thất bại |
| `org.springframework.orm.ObjectOptimisticLockingFailureException` | Spring ORM | Spring translation cho optimistic locking failure |

Đặc biệt, `ConstraintViolationException` của Bean Validation và của Hibernate JDBC là **hai class khác nhau**. Hãy kiểm tra fully qualified class name/import trong log, không suy luận từ tên rút gọn.

## 4. Dùng SQLState để phân nhóm lỗi JDBC

SQLState là mã phân loại lỗi theo chuẩn SQL/JDBC, dù chi tiết và vendor code vẫn phụ thuộc DBMS.

| SQLState class | Ý nghĩa khái quát | Ví dụ |
|---|---|---|
| `08` | Connection exception | Connection mất, lỗi thiết lập kết nối |
| `22` | Data exception | Giá trị không phù hợp kiểu, vượt precision/length |
| `23` | Integrity constraint violation | Unique, FK, NOT NULL, CHECK |
| `40` | Transaction rollback | Deadlock, serialization failure |
| `42` | Syntax/access rule | Sai SQL, table/column không tồn tại hoặc quyền truy cập |

Ví dụ PostgreSQL thường dùng:

| SQLState | Ý nghĩa thường gặp trên PostgreSQL |
|---|---|
| `23502` | Not-null violation |
| `23503` | Foreign-key violation |
| `23505` | Unique violation |
| `23514` | Check constraint violation |
| `22P02` | Invalid text representation |
| `42P01` | Undefined table |
| `42703` | Undefined column |
| `40001` | Serialization failure |
| `40P01` | Deadlock detected |

Các mã cụ thể trong bảng này là **PostgreSQL-specific**; không dùng chúng như danh mục vendor-neutral. Với MySQL, SQL Server, Oracle hoặc DBMS khác, tra SQLState/vendor code của driver và tài liệu database tương ứng.

## 5. Lỗi Not a managed type

Triệu chứng:

```text
Not a managed type: class com.example.Product
```

Spring Data JPA repository hoặc code gọi metamodel/EntityManager đang sử dụng một class không thuộc persistence unit hiện tại.

Kiểm tra theo thứ tự:

1. Class có annotation `jakarta.persistence.Entity` đúng namespace không?
2. Package của entity có nằm trong vùng entity scanning không?
3. Repository có đang gắn đúng `EntityManagerFactory` không?
4. Nếu có nhiều persistence units, entity đã được đăng ký vào đúng factory chưa?
5. Có vô tình import `javax.persistence.Entity` trong stack Jakarta không?

Ví dụ:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class Product {
    @Id
    private Long id;
}
```

Nếu main class ở `com.example.app`, Boot convention thường quét các package con. Nếu entity nằm ở `com.example.shared.domain`, có thể cần:

```java
@SpringBootApplication
@EntityScan(basePackages = {
    "com.example.app.domain",
    "com.example.shared.domain"
})
public class Application {}
```

Với multi-datasource, kiểm tra `@EnableJpaRepositories` có đúng `entityManagerFactoryRef` và `transactionManagerRef`. Thêm `@EntityScan` toàn cục không tự đảm bảo một entity được đăng ký vào mọi custom persistence unit.

## 6. Lỗi Unknown entity hoặc Association targets an unknown entity

Những lỗi này thường có nghĩa Hibernate không có mapping metadata cho entity được yêu cầu hoặc entity đích của association.

Ví dụ:

```java
@Entity
public class PurchaseOrder {
    @Id
    private Long id;

    @ManyToOne
    private Customer customer;
}
```

Nếu `Customer` không được đăng ký trong cùng persistence unit, Hibernate không thể xây dựng association mapping hợp lệ.

Kiểm tra:

- `Customer` có phải entity thật hay chỉ là DTO/value object?
- `Customer` có nằm trong entity packages của đúng EMF không?
- `@ManyToOne` có trỏ tới class đúng không, hay import nhầm class trùng tên từ module khác?
- Có nhiều persistence units nhưng hai entity ở hai factory khác nhau không?
- Annotation `@Entity` có đúng namespace/provider không?

Một association JPA thông thường không thể tự động tham chiếu entity do một `EntityManagerFactory` độc lập quản lý. Nếu dữ liệu ở database khác, thường cần lưu external ID và kết hợp ở service/read model.

## 7. Lỗi entity không có identifier

Một JPA entity cần có identifier mapping:

```java
@Entity
public class Customer {
    @Id
    private Long id;
}
```

Nếu quên `@Id`/`@EmbeddedId`, hoặc annotation đặt nhầm trên getter/field so với access strategy, Hibernate có thể báo entity không có identifier hoặc không xây dựng được mapping.

Ví dụ với composite key:

```java
@Embeddable
public class MembershipId implements Serializable {
    private Long userId;
    private Long groupId;

    protected MembershipId() {}

    // equals() và hashCode() dựa trên cả hai thành phần.
}

@Entity
public class Membership {
    @EmbeddedId
    private MembershipId id;
}
```

Composite key cần tuân thủ quy tắc JPA về kiểu ID, equality và mapping. Nếu `equals()`/`hashCode()` sai, collection, persistence context hoặc thao tác merge có thể có hành vi khó hiểu dù schema vẫn có primary key.

### 7.1. Field access và property access

JPA xác định access strategy dựa trên vị trí annotation mapping như `@Id` hoặc cấu hình `@Access`. Nếu `@Id` đặt trên field, Hibernate thường đọc field; nếu đặt trên getter, Hibernate thường dùng property access. Trộn annotations trên field và getter không có chủ đích có thể khiến mapping không như mong muốn.

Giữ annotations nhất quán, hoặc chỉ định `@Access(AccessType.FIELD)`/`PROPERTY` khi cần.

## 8. Lỗi duplicate column mapping

Một lỗi mapping phổ biến xảy ra khi cùng một cột được ánh xạ writable qua hai thuộc tính:

```java
@Entity
public class PurchaseOrder {
    @Id
    private Long id;

    @Column(name = "customer_id")
    private Long customerId;

    @ManyToOne
    @JoinColumn(name = "customer_id")
    private Customer customer;
}
```

Hibernate có thể báo column mapped more than once. Một cột đang được cả scalar property và association cùng ghi.

Nếu cần giữ cả ID scalar để đọc và association để điều hướng, chỉ một mapping nên writable:

```java
@Column(name = "customer_id", insertable = false, updatable = false)
private Long customerId;

@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id")
private Customer customer;
```

Hoặc thiết kế chỉ dùng association và lấy `customer.getId()` khi cần. Với derived/composite identifiers, xem `@MapsId` thay vì tạo hai mapping cạnh tranh.

## 9. JPQL/HQL không tìm thấy entity hoặc property

JPQL/HQL thường dùng **tên entity và thuộc tính Java**, không mặc định dùng tên bảng/cột vật lý.

Entity:

```java
@Entity(name = "PurchaseOrder")
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    @Column(name = "order_status")
    private String status;
}
```

Query đúng theo entity/property:

```hql
select o
from PurchaseOrder o
where o.status = :status
```

Query sai nếu coi `purchase_orders` là entity name hoặc `order_status` là property:

```hql
select o
from purchase_orders o
where o.order_status = :status
```

Native SQL mới dùng tên table/column vật lý:

```sql
SELECT *
FROM purchase_orders
WHERE order_status = ?;
```

Khi gặp `Could not resolve attribute`, `UnknownPathException` hoặc lỗi tương tự, kiểm tra entity name, Java property, embedded path, inheritance mapping và query alias trước khi sửa schema.

## 10. Lỗi table/column không tồn tại

Các thông báo:

```text
relation "purchase_orders" does not exist
column "order_status" does not exist
invalid object name 'purchase_orders'
```

có thể đến từ:

- Migration chưa chạy trên database/schema mà ứng dụng đang kết nối.
- Hibernate dùng sai `DataSource` hoặc schema.
- `@Table`/`@Column` không khớp DDL.
- Physical naming strategy chuyển tên khác dự kiến.
- Chữ hoa/chữ thường và quoted identifiers khác nhau.
- PostgreSQL `search_path` hoặc default schema khác.
- User database không có quyền nhìn thấy object.

Đừng chỉ nhìn tên JDBC URL. Hãy xác minh connection đang dùng đúng database, catalog và schema bằng chính user của ứng dụng.

### 10.1. Naming strategy

Ví dụ Java:

```java
private String orderStatus;
```

có thể được chuyển thành `order_status` bởi physical naming strategy mặc định của cấu hình Spring Boot/Hibernate. Nếu DDL tạo `orderStatus`, SQL generated có thể không tìm thấy cột.

Khi cần tên rõ ràng:

```java
@Column(name = "order_status")
private String orderStatus;
```

Đừng đổi naming strategy toàn ứng dụng chỉ để sửa một cột mà chưa xem ảnh hưởng tới mọi entities và migrations.

## 11. Kiểm tra schema thực tế bằng JDBC metadata

Khi nghi ngờ table/column không khớp, có thể kiểm tra metadata qua JDBC trong môi trường debug:

```java
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData metadata = connection.getMetaData();

    System.out.println(metadata.getDatabaseProductName());
    System.out.println(metadata.getDatabaseProductVersion());
    System.out.println(metadata.getDriverName());
    System.out.println(metadata.getDriverVersion());

    try (ResultSet columns = metadata.getColumns(
            connection.getCatalog(),
            connection.getSchema(),
            "purchase_orders",
            null)) {
        while (columns.next()) {
            System.out.println(
                columns.getString("COLUMN_NAME") + " : " +
                columns.getString("TYPE_NAME"));
        }
    }
}
```

Đây là ví dụ JDBC chẩn đoán; kết quả metadata phụ thuộc driver và schema naming. Không log connection URL chứa credentials hoặc các thông tin nhạy cảm.

Nếu dùng Hibernate schema validation, lỗi validate có thể phát hiện một số mismatch lúc startup. Nhưng validation không thay thế migration review và không bảo đảm mọi native query/constraint nghiệp vụ đều đúng.

## 12. Kiểu dữ liệu Java và kiểu cột SQL không tương thích

Ví dụ:

```java
@Column(name = "total_amount")
private BigDecimal totalAmount;
```

Schema:

```sql
total_amount INTEGER
```

Nếu nghiệp vụ cần tiền với phần thập phân, mapping/schema này không phù hợp. Khi ghi giá trị, DBMS có thể từ chối, làm tròn hoặc cắt theo quy tắc của nó.

Các cặp kiểu thường cần kiểm tra:

| Java | SQL thường gặp | Vấn đề cần để ý |
|---|---|---|
| `String` | VARCHAR, CHAR, TEXT | Độ dài, collation, Unicode |
| `Long` | BIGINT | Range, identity/sequence |
| `Integer` | INTEGER | Range overflow |
| `BigDecimal` | DECIMAL/NUMERIC(p,s) | Precision và scale |
| `Boolean` | BOOLEAN, BIT, NUMBER(1) | Biểu diễn theo DBMS/converter |
| `UUID` | UUID, BINARY(16), CHAR(36) | JDBC type và representation |
| `LocalDate` | DATE | Không có giờ/múi giờ |
| `LocalDateTime` | TIMESTAMP | Semantics timezone phải rõ |
| `Instant` | Timestamp type phù hợp | UTC/DB timezone/precision |
| Enum | VARCHAR hoặc ordinal integer | Đổi tên/thứ tự enum |

Đừng chỉ sửa Java field type; cần kiểm tra migration, dữ liệu cũ và SQL generated.

## 13. Lỗi precision/scale và giá trị số

Ví dụ:

```java
@Column(precision = 12, scale = 2)
private BigDecimal amount;
```

Schema:

```sql
amount NUMERIC(12, 2)
```

Với precision 12 và scale 2, số chữ số tổng cộng tối đa là 12, trong đó 2 chữ số phần thập phân. Một giá trị có phần nguyên quá lớn có thể bị từ chối.

Khi gặp numeric overflow/truncation:

1. Kiểm tra giá trị thực được bind.
2. Kiểm tra precision/scale trong annotation và DDL.
3. Kiểm tra calculation trung gian có vượt giới hạn không.
4. Kiểm tra rounding policy nghiệp vụ.
5. Migrate schema và validate dữ liệu cũ trước khi mở rộng precision.

Không tự động tăng precision vô hạn; database storage, index và business limits vẫn cần được cân nhắc.

## 14. Enum mapping bị lệch

Nếu không chỉ định rõ, enum có thể được lưu theo ordinal trong một số mapping conventions:

```java
enum OrderStatus {
    DRAFT, CONFIRMED, PAID
}
```

Ordinal mapping có rủi ro: đổi thứ tự enum có thể khiến giá trị cũ được diễn giải thành trạng thái khác.

Thông thường nên dùng:

```java
@Enumerated(EnumType.STRING)
@Column(name = "status", nullable = false)
private OrderStatus status;
```

Schema:

```sql
status VARCHAR(32) NOT NULL
```

Nhưng STRING vẫn cần tương thích với enum values cũ. Nếu đổi `CONFIRMED` thành `APPROVED`, cần migration dữ liệu hoặc converter giữ backward compatibility. Đừng đổi tên enum rồi mong Hibernate tự suy ra giá trị lịch sử.

## 15. Converter và kiểu dữ liệu tùy biến

Một `AttributeConverter`:

```java
@Converter
public class YesNoConverter
        implements AttributeConverter<Boolean, String> {

    @Override
    public String convertToDatabaseColumn(Boolean value) {
        return Boolean.TRUE.equals(value) ? "Y" : "N";
    }

    @Override
    public Boolean convertToEntityAttribute(String value) {
        if (value == null) {
            return null;
        }
        return switch (value) {
            case "Y" -> true;
            case "N" -> false;
            default -> throw new IllegalArgumentException(
                "Unexpected database value");
        };
    }
}
```

Mapping:

```java
@Convert(converter = YesNoConverter.class)
@Column(name = "enabled", length = 1)
private Boolean enabled;
```

Khi gặp lỗi convert:

- Xác định giá trị database thực tế.
- Xác định domain type và relational type của converter.
- Kiểm tra legacy values, NULL và giá trị ngoài miền.
- Kiểm tra converter có bị áp dụng nhầm sang field không mong muốn.
- Đảm bảo migration đổi representation đồng bộ với code.

Không để converter âm thầm biến dữ liệu lỗi thành một default hợp lệ nếu việc đó che giấu corruption.

## 16. Lỗi JDBC type không xác định

Hibernate có thể báo lỗi dạng:

```text
Could not determine recommended JdbcType for Java type ...
UnknownBasicJavaType ...
Could not resolve JDBC type ...
```

Nguyên nhân thường là một thuộc tính Java có kiểu mà Hibernate không biết cách map thành SQL type trong context hiện tại.

Ví dụ:

```java
@Entity
public class ImportJob {
    @Id
    private Long id;

    private Map<String, Object> options;
}
```

`Map<String,Object>` không tự động có một biểu diễn portable trong cột quan hệ thông thường. Có thể cần:

- Một `@Embeddable`/entity model hóa rõ dữ liệu.
- `AttributeConverter` sang JSON/text/binary representation phù hợp.
- Hibernate-specific JSON type support đúng dialect/version.
- Bảng con cho collection/value objects.

Không đánh dấu mọi kiểu phức tạp thành `@Lob` để ép qua lỗi; đó có thể chỉ chuyển lỗi mapping thành dữ liệu khó truy vấn và khó migrate.

## 17. Date, time và timezone mismatch

Các kiểu:

| Java type | Ý nghĩa |
|---|---|
| `LocalDate` | Ngày lịch, không có giờ |
| `LocalTime` | Giờ trong ngày, không có ngày |
| `LocalDateTime` | Ngày + giờ địa phương, không mang offset/zone |
| `OffsetDateTime` | Ngày + giờ với UTC offset |
| `Instant` | Một thời điểm trên timeline UTC |

Lỗi thường gặp không chỉ là JDBC type mà còn là **semantics**: database lưu `timestamp without time zone` trong khi ứng dụng nghĩ đó là UTC instant.

Khi điều tra:

- Xem DDL thực tế: DATE, TIMESTAMP, TIMESTAMP WITH TIME ZONE hay kiểu vendor-specific.
- Kiểm tra JDBC driver/version và Hibernate dialect.
- Kiểm tra `hibernate.jdbc.time_zone` nếu cấu hình phù hợp.
- Xác định timezone của DB/session/application.
- Kiểm tra precision (milliseconds/microseconds).
- Không chuyển LocalDateTime thành UTC bằng suy đoán khi không biết zone gốc.

Test với giờ gần nửa đêm, DST boundary (nếu zone áp dụng), và timestamp có precision khác nhau khi hệ thống cần độ chính xác cao.

## 18. Lỗi TransientPropertyValueException

Ví dụ:

```java
PurchaseOrder order = new PurchaseOrder();
Customer customer = new Customer(); // transient, chưa persist

order.setCustomer(customer);
entityManager.persist(order);
```

Nếu association không có cascade persist và Customer chưa được lưu, Hibernate có thể báo:

```text
TransientPropertyValueException:
object references an unsaved transient instance
```

Có hai ý định khác nhau:

**A. Customer là object mới và phải được tạo cùng Order.**

```java
@ManyToOne(cascade = CascadeType.PERSIST)
private Customer customer;
```

hoặc persist Customer rõ ràng trước Order, nếu lifecycle cho phép.

**B. Customer đã tồn tại và Order chỉ cần tham chiếu.**

Tải một managed instance:

```java
Customer customer = entityManager.find(
    Customer.class, customerId);

if (customer == null) {
    throw new IllegalArgumentException("Customer not found");
}

order.setCustomer(customer);
```

Không thêm `CascadeType.PERSIST` theo phản xạ cho mọi `@ManyToOne`; có thể khiến Hibernate cố tạo mới một đối tượng tham chiếu vốn phải tồn tại.

## 19. Lỗi detached entity passed to persist

Một entity detached là object đã từng được quản lý nhưng hiện không còn thuộc persistence context hiện tại.

Ví dụ:

```java
Customer detached = loadInAnotherTransaction();
entityManager.persist(detached); // Sai ý định phổ biến.
```

`persist()` dành cho instance mới. Nếu instance có identity đã tồn tại/detached, Hibernate có thể từ chối.

Giải pháp thường là tải managed instance trong transaction hiện tại rồi áp dụng thay đổi:

```java
Customer managed = entityManager.find(
    Customer.class, detached.getId());

if (managed == null) {
    throw new EntityNotFoundException();
}

managed.changeName(detached.getName());
```

`merge()` có thể sao chép state từ detached object vào managed instance và trả về instance managed khác. Đừng bỏ qua giá trị trả về:

```java
Customer managed = entityManager.merge(detached);
```

Không dùng `merge()` như một cách “làm mọi object thành managed” mà không kiểm tra stale fields, association graph, authorization và optimistic version.

## 20. Tham chiếu ID không tồn tại: getReference() và find()

Hai API có semantics khác nhau:

```java
Customer found = entityManager.find(
    Customer.class, customerId);
```

`find()` thường tải entity và trả `null` nếu không tìm thấy (trừ trường hợp entity đã có trong persistence context).

```java
Customer reference = entityManager.getReference(
    Customer.class, customerId);
```

`getReference()` có thể trả một proxy/reference mà không truy vấn database ngay. Nếu row không tồn tại, lỗi có thể xuất hiện muộn khi proxy cần được khởi tạo hoặc khi database kiểm tra foreign key.

### 20.1. Khi nào dùng getReference?

Nếu ứng dụng đã xác thực ID và chỉ cần gắn association mà không cần đọc field:

```java
Customer customer = em.getReference(
    Customer.class, customerId);
order.setCustomer(customer);
```

đây có thể là cách giảm một SELECT. Nhưng nếu cần thông báo domain rõ “Customer không tồn tại” ngay trong service, `find()` thường dễ kiểm soát hơn.

Dù dùng `getReference()`, database FK vẫn là lớp bảo vệ cuối cùng khi insert/update. Không biến `getReference()` thành cơ chế validate tồn tại mà không kiểm tra behavior thực tế.

## 21. Lỗi EntityNotFoundException hoặc ObjectNotFoundException

Một proxy có thể đại diện cho identifier mà database không còn row tương ứng.

Nguyên nhân:

- FK không được khai báo hoặc dữ liệu legacy bị orphan.
- Row đích bị xóa vật lý bởi SQL ngoài Hibernate.
- Database khác schema/tenant so với dự kiến.
- Một import/job đã xóa target nhưng không cập nhật references.
- `getReference()` được gọi với ID không tồn tại.
- Cache/proxy giữ state cũ trong tình huống ngoài ORM.

Ví dụ:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
Customer customer = order.getCustomer();

// Lỗi có thể chỉ xuất hiện khi:
String name = customer.getName();
```

Kiểm tra bằng SQL trên đúng database/schema/user:

```sql
SELECT id
FROM customers
WHERE id = :customerId;
```

Sau đó kiểm tra bảng tham chiếu và foreign key. Nếu target thực sự không tồn tại, quyết định sửa dữ liệu, tạo target hợp lệ hoặc xử lý domain exception; không chỉ catch exception rồi trả một object rỗng.

## 22. Foreign-key violation khi ghi

Một lỗi:

```text
insert or update on table "purchase_orders"
violates foreign key constraint "fk_order_customer"
```

thường nghĩa là giá trị FK không tham chiếu tới row đích hợp lệ trong database.

Ví dụ:

```sql
INSERT INTO purchase_orders (id, customer_id)
VALUES (10, 999999);
```

nếu `customers.id=999999` không tồn tại thì DB từ chối.

Kiểm tra:

1. Customer ID được lấy từ nguồn nào?
2. Có đang tham chiếu nhầm tenant/database/schema không?
3. Customer đã được persist/commit chưa?
4. Transaction order và flush timing có đúng không?
5. Association join columns có khớp FK thật không?
6. FK có composite tenant columns nhưng mapping chỉ gửi một phần không?

Không tắt foreign key để lệnh INSERT chạy qua. Constraint đang bảo vệ tính toàn vẹn quan hệ; hãy sửa dữ liệu hoặc luồng ghi.

## 23. FK và transaction ordering

Ví dụ:

```java
@Transactional
public void createOrder(CreateCommand command) {
    Customer customer = new Customer(command.customerName());
    PurchaseOrder order = new PurchaseOrder();
    order.setCustomer(customer);

    entityManager.persist(order);
    entityManager.persist(customer);
}
```

Hibernate có thể sắp xếp action queue theo dependency và mapping, nhưng không nên dựa vào thứ tự code như một cam kết SQL statement order cho mọi mapping. Nếu mapping không có cascade và dependency không được provider xử lý như mong đợi, flush có thể thất bại.

Cách rõ ràng:

```java
entityManager.persist(customer);
entityManager.persist(order);
```

hoặc cấu hình cascade phù hợp với aggregate lifecycle. Với dữ liệu đã tồn tại, lấy managed reference thay vì tạo một Customer object mới chỉ có ID.

Nếu cần kiểm soát ordering của nhiều writes, dùng mapping/cascade đúng và kiểm tra SQL/constraint bằng integration test.

## 24. Unique constraint violation

Ví dụ:

```text
duplicate key value violates unique constraint "uq_customer_email"
```

Có thể xảy ra khi:

- Email đã tồn tại.
- Hai requests đồng thời cùng đăng ký một email.
- Code kiểm tra `existsByEmail()` rồi insert nhưng race xảy ra giữa check và insert.
- Unique index bao gồm tenant scope khác với business rule.
- Soft-deleted rows vẫn chiếm unique key.

### 24.1. existsBy... không thay thế unique constraint

```java
if (repository.existsByEmail(email)) {
    throw new DuplicateEmailException();
}
repository.save(new Customer(email));
```

Đoạn code cải thiện thông báo thân thiện nhưng không đảm bảo concurrency. Hai transactions có thể cùng thấy “chưa tồn tại” rồi cùng insert. Unique constraint của DB phải là lớp bảo vệ cuối.

Bắt và translate đúng constraint violation thành domain error; đừng xóa constraint để tránh exception.

## 25. NOT NULL và CHECK constraint

Ví dụ not-null:

```text
null value in column "order_number"
violates not-null constraint
```

Kiểm tra cả:

- Field Java có null không?
- DTO mapping có bỏ sót property?
- Constructor/builder có gán default?
- `@Column(nullable=false)` có khớp DDL không?
- Native SQL/batch writer có gửi NULL không?

Ví dụ check:

```sql
ALTER TABLE purchase_orders
ADD CONSTRAINT ck_order_total_nonnegative
CHECK (total_amount >= 0);
```

Nếu database báo CHECK violation, xem giá trị thực được bind và business invariant. Bean Validation như `@PositiveOrZero` có thể cải thiện lỗi sớm, nhưng DB constraint vẫn bảo vệ dữ liệu từ các writer khác.

## 26. Optimistic locking failure

Entity:

```java
@Entity
public class InventoryItem {
    @Id
    private Long id;

    private int quantity;

    @Version
    private long version;
}
```

Hai transactions cùng đọc version 4:

```text
Transaction A: read version=4
Transaction B: read version=4

A UPDATE ... WHERE id=7 AND version=4
  -> row updated, version becomes 5

B UPDATE ... WHERE id=7 AND version=4
  -> affected rows = 0
  -> optimistic locking failure
```

Đây không phải lỗi mapping FK hay sai JDBC type. Một transaction đang dùng state cũ.

Hướng xử lý:

- Xác định business có cho phép retry không.
- Tải state mới và áp dụng lại business operation nếu có thể.
- Không retry một lệnh không idempotent mà không kiểm tra tác dụng phụ.
- Kiểm tra native SQL/bulk updates có cập nhật version đúng không.
- Xem transaction duration và concurrent writers.

Không xóa `@Version` chỉ để hết exception; làm vậy có thể biến lost update thành lỗi dữ liệu âm thầm.

## 27. Deadlock và lock timeout

Hai transactions có thể lấy locks theo thứ tự ngược:

```text
Transaction A:
  lock Order #1
  waits for Customer #5

Transaction B:
  lock Customer #5
  waits for Order #1

Database detects deadlock
  -> abort one transaction
```

Deadlock thường là lỗi runtime/concurrency, không phải lỗi entity mapping. Kiểm tra:

- Database deadlock report/transaction graph.
- SQL statements và thứ tự lock.
- Indexes có khiến query khóa nhiều rows hơn cần thiết không.
- Transaction có giữ lock khi gọi network/slow code không.
- Isolation level và lock hints.

Retry transaction bị deadlock có thể hợp lý nếu thao tác idempotent và giới hạn số lần retry/backoff; không retry vô hạn hoặc nuốt lỗi.

## 28. Lỗi SQLGrammarException và cú pháp SQL

Hibernate có thể bọc lỗi cú pháp/access rule trong `SQLGrammarException` dù SQL có thể đúng cú pháp ở một DBMS khác.

Nguyên nhân:

- Hibernate dialect không đúng DBMS/version.
- Table/column name sai.
- Reserved keyword dùng làm identifier không quote đúng.
- Native query viết theo cú pháp vendor khác.
- Function/type/sequence không được hỗ trợ.
- Schema/search path không đúng.

Lấy SQL generated đầy đủ, chạy thử trên cùng DBMS/user/schema, sau đó đọc vendor message. Không sửa bằng cách quote mọi identifier một cách tùy tiện vì có thể làm thay đổi case-sensitive semantics.

## 29. Dialect và JDBC metadata

Hibernate cần biết đặc điểm DBMS để sinh SQL và chọn kiểu JDBC/DDL phù hợp. Trong nhiều cấu hình hiện đại, dialect có thể được xác định qua JDBC metadata.

Nếu gặp:

```text
Unable to determine Dialect without JDBC metadata
```

đừng vội thêm một dialect class để che lỗi. Kiểm tra:

1. JDBC URL có đúng không?
2. Driver có trên runtime classpath không?
3. Database có sẵn sàng và reachable không?
4. Credentials/schema permissions có đúng không?
5. Connection pool có mở được connection không?

Chỉ cấu hình dialect tường minh khi có lý do và class phù hợp với Hibernate version. Không dùng dialect của một major version khác hoặc database khác.

## 30. Lỗi column type khi dùng UUID, JSON hoặc ARRAY

Một Java field phức tạp không luôn map tự nhiên thành một SQL type portable:

```java
@Entity
public class EventPayload {
    @Id
    private Long id;

    private Map<String, Object> payload;
}
```

Nếu muốn lưu JSON, cần chọn:

- Converter serialize JSON thành VARCHAR/TEXT/CLOB.
- Hibernate JSON type mapping phù hợp dialect/version.
- Một bảng con lưu key/value.

Nếu muốn dùng DB-native JSON, kiểm tra DDL, JDBC driver, Hibernate type mapping và query operators. Không giả định `Map` sẽ tự biến thành JSON column.

Tương tự UUID: PostgreSQL có type `uuid`, một số DBMS dùng binary/char. Representation và parameter binding phải thống nhất giữa Java mapping, DDL, migrations và native SQL.

## 31. Lỗi sai độ dài chuỗi hoặc encoding

Ví dụ:

```text
value too long for type character varying(50)
```

Kiểm tra:

- Dữ liệu thực có vượt độ dài không?
- Schema có cột cũ ngắn hơn mapping?
- Unicode code points và độ dài byte có bị nhầm?
- Có trimming/normalization policy?
- API có giới hạn độ dài trước khi persistence không?

`@Column(length=255)` là mapping/DDL metadata; nó không đảm bảo một schema production cũ đã được migrate lên 255.

Không cắt chuỗi tự động nếu việc đó làm thay đổi email, identifier hoặc dữ liệu pháp lý.

## 32. Phân biệt Bean Validation với database constraint

Entity:

```java
@Entity
public class Customer {
    @Id
    private Long id;

    @NotBlank
    @Size(max = 100)
    @Column(nullable = false, length = 100)
    private String displayName;
}
```

Hai lớp bảo vệ:

- Bean Validation có thể phát hiện dữ liệu không hợp lệ trước khi SQL được thực thi, tùy validation integration và lifecycle.
- Database NOT NULL/VARCHAR(100) bảo vệ cả JDBC, SQL scripts và ứng dụng khác.

Nếu validation exception xuất hiện trước SQL, xem object input và validator. Nếu DB exception xuất hiện lúc flush, kiểm tra DDL, actual value và writers ngoài ứng dụng.

Đừng chỉ dựa vào Bean Validation để bảo vệ constraint liên quan uniqueness hoặc concurrent writes; DB unique index vẫn cần thiết.

## 33. Flush khiến lỗi xuất hiện muộn

Hibernate thường trì hoãn SQL cho tới lúc flush. Những điểm có thể kích hoạt flush gồm:

- Explicit `entityManager.flush()`/`session.flush()`.
- Transaction commit.
- Một số query theo flush mode cần đồng bộ pending changes.

Ví dụ:

```java
@Transactional
public void createCustomer(String email) {
    Customer customer = new Customer(email);
    entityManager.persist(customer);

    // Không thấy lỗi tại persist() không có nghĩa
    // INSERT đã thành công.

    entityManager.flush();
}
```

Nếu email vi phạm unique constraint, exception có thể chỉ xuất hiện ở `flush()` hoặc khi transaction commit.

### 33.1. Flush không phải commit

```text
persist()
   |
   v
Entity managed, SQL có thể đang pending
   |
   v
flush()
   |
   v
SQL gửi tới DB trong transaction
   |
   +-- rollback -> thay đổi chưa commit bị hoàn tác
   |
   +-- commit -> thay đổi trở nên durable theo DB semantics
```

Đừng ghi log “đã lưu thành công” ngay sau `persist()` nếu chưa biết transaction sẽ commit hay rollback.

## 34. Transaction rollback-only và lỗi thứ cấp

Một lỗi persistence có thể đánh dấu transaction rollback-only. Code sau đó catch exception và tiếp tục chạy, nhưng lúc commit Spring có thể báo:

```text
UnexpectedRollbackException:
Transaction rolled back because it has been marked as rollback-only
```

Exception này đôi khi là **hậu quả** của lỗi xảy ra trước đó, không phải root cause.

Hãy tìm exception đầu tiên trong transaction và xem:

- Có repository call nào đã ném exception nhưng bị catch?
- Transaction propagation có tham gia transaction cha?
- Một inner method đã đánh dấu rollback-only?
- Exception type có kích hoạt rollback rule?
- Code có nuốt lỗi và trả kết quả thành công giả không?

Không bắt `DataAccessException` rồi bỏ qua chỉ để API trả HTTP 200. Transaction đã rollback thì response phải phản ánh trạng thái thất bại hoặc trạng thái nghiệp vụ có thể tiếp tục.

## 35. SQL logging trong Hibernate

Để xem SQL do Hibernate phát, cấu hình logger phù hợp với version. Với Hibernate 6.x, một cấu hình thường dùng:

```properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Trong một số version, logger bind/extract khác nhau; Hibernate 5.x thường dùng category cũ như `org.hibernate.type.descriptor.sql.BasicBinder` cho bind parameters. Tra logging guide của đúng version.

SQL logging giúp thấy:

- Statement thật sự được thực thi.
- Cột/table names sau naming strategy.
- Join và predicate.
- Số lần query/N+1.

Bind logging có thể tiết lộ email, token, PII, thông tin tài chính và payload. Chỉ bật tạm ở môi trường phát triển/test với dữ liệu giả hoặc được redaction; không bật TRACE bind parameters rộng rãi trong production.

## 36. Kiểm tra JDBC bind types và values

Một statement:

```sql
INSERT INTO purchase_orders (id, total_amount, created_at)
VALUES (?, ?, ?);
```

có thể sai do:

- Bind String vào cột numeric.
- Bind timestamp với timezone semantics không đúng.
- Gửi null nhưng Hibernate không có type metadata cần thiết.
- Dùng UUID representation không khớp DB column.
- Converter trả value không hợp lệ.

Khi debug, cần biết cả **giá trị đã redaction** và **JDBC type**. Chỉ nhìn SQL placeholders không đủ.

Không copy nguyên dữ liệu nhạy cảm từ bind logs vào ticket/chat. Dùng giá trị giả giữ nguyên kiểu/độ dài/biên lỗi để tái hiện.

## 37. Thống kê Hibernate giúp tìm query bất thường

Khi bật statistics:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
```

Có thể đọc một số counters:

```java
SessionFactory sf =
    entityManagerFactory.unwrap(SessionFactory.class);
Statistics statistics = sf.getStatistics();

long preparedStatements =
    statistics.getPrepareStatementCount();
long entityLoads =
    statistics.getEntityLoadCount();
long entityFetches =
    statistics.getEntityFetchCount();
long collectionFetches =
    statistics.getCollectionFetchCount();
long queryExecutions =
    statistics.getQueryExecutionCount();
```

Statistics giúp xác định workload, query counts và entity/collection fetch behavior. Chúng không tự cung cấp root cause cho mọi constraint failure và thường là counters tích lũy ở phạm vi SessionFactory.

Trong production, nếu lấy delta giữa hai thời điểm, hoạt động đồng thời của requests khác có thể nằm trong cùng delta. Hãy kết hợp tracing, datasource metrics và DB monitoring thay vì gán aggregate counter cho một request.

## 38. Dùng schema validation để phát hiện mismatch sớm

Với schema do migration quản lý:

```properties
spring.jpa.hibernate.ddl-auto=validate
```

Hibernate có thể kiểm tra một phần sự tương thích giữa mapping và schema khi khởi tạo. Điều này giúp phát hiện thiếu bảng/cột hoặc một số kiểu không phù hợp trước khi traffic đến.

Nhưng `validate`:

- Không chứng minh mọi constraint nghiệp vụ đã tồn tại.
- Không kiểm tra mọi native query.
- Không thay migration review.
- Không sửa schema.
- Không đảm bảo hai databases trong multi-datasource đều được migrate đúng.

Không chuyển sang `update` trên production để né validation failure. Hãy sửa migration/schema hoặc mapping có chủ đích.

## 39. Kiểm tra DB/schema mà ứng dụng thực sự đang dùng

Một ứng dụng có nhiều profiles/DataSources có thể kết nối khác với bạn nghĩ.

Ví dụ:

```properties
spring.datasource.url=jdbc:postgresql://db-prod:5432/orders
spring.datasource.username=orders_app
```

Nhưng test/local profile có thể override URL. Hãy xác minh runtime:

- Active Spring profiles.
- DataSource bean được inject vào EntityManagerFactory.
- Database product/version và current schema.
- Database username/role.
- Tenant routing key nếu có.
- Migration version table.

Không gửi password hoặc URL chứa secret vào logs. Có thể log database product, schema và một định danh môi trường đã được redaction.

## 40. Dùng DB console để kiểm tra constraint và dữ liệu

Khi Hibernate báo unique/FK failure, hãy kiểm tra database trực tiếp trên đúng môi trường và schema.

Ví dụ PostgreSQL tìm constraints:

```sql
SELECT
    conname,
    contype,
    conrelid::regclass AS table_name
FROM pg_constraint
WHERE conrelid = 'purchase_orders'::regclass;
```

Kiểm tra duplicate:

```sql
SELECT email, COUNT(*)
FROM customers
GROUP BY email
HAVING COUNT(*) > 1;
```

Kiểm tra orphan references:

```sql
SELECT o.id, o.customer_id
FROM purchase_orders o
LEFT JOIN customers c ON c.id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.id IS NULL;
```

Các câu lệnh trên dành cho PostgreSQL hoặc SQL phổ biến tùy cú pháp. Trước khi chạy query điều tra trên production, kiểm tra chi phí scan và quyền truy cập; dùng read-only role khi phù hợp.

## 41. getReference() có thể trì hoãn phát hiện dữ liệu thiếu

Ví dụ:

```java
PurchaseOrder order = new PurchaseOrder();
Customer customer = em.getReference(
    Customer.class, command.customerId());

order.setCustomer(customer);
em.persist(order);
```

Nếu ID không tồn tại:

- Proxy có thể chưa được khởi tạo khi được gán.
- Hibernate có thể chỉ bind ID vào FK.
- DB FK có thể phát hiện ở INSERT/flush.
- Nếu không có FK, lỗi có thể xuất hiện muộn hơn khi dereference proxy.

Nếu API cần lỗi domain rõ ràng ngay tại thời điểm xử lý:

```java
Customer customer = em.find(
    Customer.class, command.customerId());

if (customer == null) {
    throw new CustomerNotFoundException(
        command.customerId());
}
```

Với nhiều request đồng thời, row vẫn có thể bị xóa sau lần `find()`. Database FK và transaction/isolation là lớp cuối cùng; kiểm tra tồn tại ở application không thay thế constraint.

## 42. Composite foreign key và tenant mismatch

Trong shared-schema multi-tenancy, một FK có thể phải bao gồm tenant ID:

```sql
FOREIGN KEY (tenant_id, customer_id)
REFERENCES customers (tenant_id, id)
```

Nếu Hibernate mapping chỉ khai báo `customer_id`, SQL có thể không cung cấp đủ khóa quan hệ hoặc model không phản ánh constraint thật.

Kiểm tra:

- Primary/unique key của bảng đích.
- `@JoinColumns` và tên cột chính xác.
- Insertable/updatable flags.
- `@EmbeddedId`/`@MapsId` nếu có composite identity.
- Tenant context và SQL generated.

Đừng sửa lỗi FK bằng cách chỉ tìm row có cùng customer_id mà bỏ qua tenant_id; như vậy có thể che một lỗi truy cập chéo tổ chức.

## 43. Sai schema hoặc search_path

Một query có thể chạy trên máy dev nhưng thất bại trên môi trường khác vì schema resolution.

PostgreSQL ví dụ:

```sql
SHOW search_path;
SELECT current_database(), current_schema(), current_user;
```

Nếu bảng ở schema `sales` nhưng connection tìm trong `public`, `purchase_orders` có thể không được tìm thấy hoặc có thể trỏ tới một bảng khác cùng tên.

Giải pháp:

- Cấu hình default schema phù hợp khi cần.
- Dùng `@Table(schema=...)` nếu schema là cố định.
- Dùng tenant schema routing nếu schema thay đổi theo tenant.
- Quản lý `search_path`/connection state trong pool.
- Migration và application phải thống nhất schema.

Không hard-code schema tenant Alpha vào entity mapping nếu Session phải chạy cho nhiều tenants.

## 44. Phân biệt lỗi mapping với lỗi dữ liệu legacy

Một mapping có thể đúng cho dữ liệu mới nhưng thất bại khi đọc hàng cũ:

- Enum DB chứa giá trị đã bị xóa khỏi code.
- Cột mới NOT NULL nhưng legacy rows chưa backfill.
- Numeric cũ có precision vượt giới hạn mới.
- Timestamp chứa giá trị bất hợp lệ hoặc timezone assumption khác.
- FK legacy bị orphan.
- JSON/text có payload không parse được.

Khi lỗi chỉ xảy ra với một số IDs, hãy lấy sample row đã redaction và so sánh với rows đọc thành công. Đừng mặc định mapping sai chỉ vì một dữ liệu cũ không hợp lệ.

Quy trình sửa thường là:

1. Xác định phạm vi rows bị ảnh hưởng.
2. Xác định dữ liệu nào đúng theo business contract.
3. Viết migration/backfill có thể kiểm tra và chạy lại an toàn.
4. Cập nhật mapping/validation để ngăn lỗi mới.
5. Kiểm tra dữ liệu sau migration.

Không tự sửa dữ liệu production trực tiếp bằng câu UPDATE không có backup/review.

## 45. Lỗi duplicate entity trong một Session

Hibernate có thể báo `NonUniqueObjectException` khi cùng một Session chứa hai Java instances khác nhau với cùng entity type/identifier.

Ví dụ:

```java
Customer a = new Customer();
a.setId(10L);

Customer b = new Customer();
b.setId(10L);

session.update(a);
session.update(b); // Conflict trong cùng Session.
```

Persistence context cần một managed identity duy nhất cho cùng entity key. Hướng xử lý:

- Tải managed instance một lần và cập nhật nó.
- Không tạo nhiều detached copies cùng ID rồi attach đồng thời.
- Dùng `merge()` đúng semantics nếu thật sự cần merge detached state; sử dụng instance được trả về.
- Clear/close Session ở boundary phù hợp, không dùng để che xung đột logic.

Với multi-tenancy, kiểm tra tenant identity của Session và key. Không tự giả định hai instances cùng ID nhưng khác tenant có thể dùng chung Session.

## 46. Lỗi LazyInitializationException

Ví dụ:

```java
PurchaseOrder order;
try (Session session = sessionFactory.openSession()) {
    order = session.find(PurchaseOrder.class, id);
}

String customerName = order.getCustomer().getName();
```

Association lazy cần Session để tải, nhưng Session đã đóng. Hibernate có thể báo:

```text
LazyInitializationException:
could not initialize proxy - no Session
```

Giải pháp:

- Load dữ liệu cần thiết trong transaction bằng fetch join/entity graph.
- Dùng DTO projection.
- Chuyển entity thành DTO trước khi service transaction kết thúc.
- Xác định rõ OSIV policy nếu ứng dụng web dùng.

Không chuyển tất cả associations sang `FetchType.EAGER` để dập lỗi; điều đó có thể tạo query quá lớn hoặc N+1 ở nơi khác.

## 47. NoResultException và NonUniqueResultException

Một query được mong đợi trả đúng một kết quả:

```java
Customer customer = em.createQuery("""
    select c
    from Customer c
    where c.email = :email
    """, Customer.class)
    .setParameter("email", email)
    .getSingleResult();
```

Hai tình huống:

- Không có row: có thể ném `NoResultException`.
- Có nhiều hơn một row: có thể ném `NonUniqueResultException`.

Nếu nghiệp vụ yêu cầu email unique, hãy có database unique constraint. Nếu query vốn có thể trả nhiều rows, dùng `getResultList()` hoặc định nghĩa ordering/limit rõ thay vì mong `getSingleResult()` chọn ngẫu nhiên.

Spring Data method trả `Optional<T>` và derived query cũng có semantics riêng; kiểm tra method return type so với cardinality thực tế.

## 48. Dùng EXPLAIN để tách lỗi cú pháp khỏi lỗi query plan

Một query có thể chạy đúng nhưng chậm do:

- Index thiếu hoặc không được dùng.
- Predicate/cast khiến index không thể sử dụng.
- Join cardinality lớn.
- Statistics database cũ.
- Parameter distribution skew.

Với PostgreSQL:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, order_number
FROM purchase_orders
WHERE customer_id = 42
ORDER BY created_at DESC;
```

`ANALYZE` thực sự chạy query. Tránh chạy `EXPLAIN ANALYZE` với câu lệnh có tác dụng phụ hoặc trên workload production mà chưa đánh giá; dùng read-only query và môi trường phù hợp.

Nếu query không chạy do type mismatch/column missing, sửa mapping/schema trước; EXPLAIN không thay thế điều tra exception.

## 49. Không dùng log SQL để lộ dữ liệu nhạy cảm

Trong lúc debug, một bind value có thể chứa:

- Password, access token, refresh token.
- Email, số điện thoại, địa chỉ.
- Thông tin thanh toán.
- Nội dung cá nhân.

Quy tắc:

- Dùng fixture giả trong dev/test.
- Bật bind logging trong khoảng thời gian giới hạn.
- Redact trước khi chia sẻ logs.
- Không đưa nguyên dump production vào ticket/chat.
- Thu thập đủ SQLState/vendor code và kiểu dữ liệu mà không cần lộ secret.

Thông tin kỹ thuật hữu ích nhất thường là table, column, constraint name, type, length, SQLState và giá trị đã thay bằng placeholder an toàn.

## 50. Exception translation của Spring

Trong Spring, `@Repository` và persistence exception translation có thể chuyển exception JDBC/Hibernate sang hệ `DataAccessException`.

Ví dụ:

```java
@Repository
public class CustomerRepositoryAdapter {
    @PersistenceContext
    private EntityManager em;

    public void persist(Customer customer) {
        em.persist(customer);
    }
}
```

Service có thể bắt exception ở boundary phù hợp:

```java
try {
    customerService.register(command);
} catch (DataIntegrityViolationException ex) {
    // Phân loại lỗi theo constraint/SQLState nếu cần.
    throw new DuplicateCustomerDataException();
}
```

Không map mọi `DataIntegrityViolationException` thành “email đã tồn tại”; nó có thể là FK, NOT NULL hoặc CHECK failure. Hãy phân biệt constraint name/vendor code hoặc validate dữ liệu theo business rule.

Không trả stack trace hay SQL nội bộ cho client. Ghi log correlation ID và error classification, trả response phù hợp.

## 51. Thiết kế thông báo lỗi ở API boundary

Một response hữu ích cho client:

```json
{
  "code": "CUSTOMER_EMAIL_ALREADY_EXISTS",
  "message": "Email đã được sử dụng.",
  "correlationId": "req-8f2a"
}
```

Không trả:

```json
{
  "message": "duplicate key value violates unique constraint uq_customer_email",
  "sql": "INSERT INTO customers ...",
  "databaseHost": "..."
}
```

Response thứ hai có thể tiết lộ cấu trúc database, tên nội bộ và dữ liệu. Error translation nên:

- Giữ lỗi gốc trong server logs đã được bảo vệ.
- Phân loại lỗi domain mà client có thể xử lý.
- Không làm mất correlation ID.
- Không che các lỗi không xác định thành một thông báo nghiệp vụ sai.

## 52. Quy trình điều tra có thể lặp lại

Một workflow thực tế:

**Bước 1 — Reproduce.** Ghi lại endpoint/command, entity ID giả lập, tenant, input shape và thời điểm lỗi.

**Bước 2 — Đọc root cause.** Đi từ exception ngoài cùng tới JDBC/vendor exception.

**Bước 3 — Lấy SQL.** Bật SQL logging phù hợp trong dev/test; lấy bind types/values đã redaction.

**Bước 4 — Xác định resource.** Đúng DataSource, database, schema, user, tenant và Hibernate version chưa?

**Bước 5 — So mapping với DDL.** Entity annotations, converters, identifiers, joins, constraints, migration version.

**Bước 6 — Kiểm tra dữ liệu.** Row đích có tồn tại? Unique value có trùng? Legacy values có nằm ngoài domain?

**Bước 7 — Kiểm tra transaction/flush.** Lỗi phát sinh lúc persist, flush, commit hay lazy access? Có exception trước đó đã đánh dấu rollback-only không?

**Bước 8 — Sửa nguyên nhân gốc.** Mapping, migration, data, domain validation, transaction order hoặc concurrency strategy.

**Bước 9 — Viết integration test.** Dùng DBMS đích, migrations thật và dữ liệu tái hiện failure.

**Bước 10 — Xác nhận regression.** Kiểm tra các tenant/association/query paths liên quan và quan sát metrics sau triển khai.

## 53. Bảng tra cứu nhanh triệu chứng và nguyên nhân

| Triệu chứng/log | Nhóm lỗi có thể có | Kiểm tra đầu tiên |
|---|---|---|
| `Not a managed type` | Entity scan/EMF mismatch | Entity annotation/package/factory |
| `Unknown entity` | Entity không được map | Persistence unit và class imports |
| `Association targets an unknown entity` | Target relation không managed | Target entity scan |
| `has no identifier` | Thiếu/mapping sai ID | @Id, access strategy, composite ID |
| `Repeated column in mapping` | Hai property cùng ghi một cột | Join column, insertable=false/updatable=false |
| `Could not resolve attribute` | HQL property path sai | Java property/entity name |
| `relation/table does not exist` | Schema/migration/naming | Database/schema/search path |
| `column does not exist` | Mapping/DDL mismatch | @Column, naming strategy |
| `Could not determine recommended JdbcType` | Java type không map được | Converter/type mapping |
| `DataException` / SQLState 22 | Giá trị không hợp lệ | Length, precision, type, format |
| `ConstraintViolationException` | DB constraint | Root SQLException và constraint name |
| `TransientPropertyValueException` | Association tới object mới chưa persist | Cascade/lifecycle |
| `detached entity passed to persist` | Dùng persist cho detached object | Load managed/merge semantics |
| `EntityNotFoundException` | Proxy target không còn row | FK, getReference, schema/tenant |
| `LazyInitializationException` | Lazy load ngoài Session | Fetch plan/transaction boundary |
| `NonUniqueObjectException` | Hai instances cùng identity trong Session | Persistence context lifecycle |
| `OptimisticLockException` | Concurrent state changed | @Version, retries |
| Deadlock/lock timeout | Concurrent lock order/contention | DB deadlock report, transaction duration |
| `UnexpectedRollbackException` | Transaction đã bị đánh dấu rollback-only | Exception đầu tiên trong transaction |
| `NoResultException` | Query không có row | Cardinality/optional result |
| `NonUniqueResultException` | Query trả nhiều rows | Unique constraint/query semantics |

Các dòng trên là hướng định vị, không phải mapping một-một. Luôn xem full exception chain và vendor diagnostics.

## 54. Ví dụ hoàn chỉnh: chẩn đoán FK reference không tồn tại

Giả sử code:

```java
@Transactional
public Long placeOrder(CreateOrderCommand command) {
    PurchaseOrder order = new PurchaseOrder();
    order.setOrderNumber(command.orderNumber());

    Customer customer = em.getReference(
        Customer.class, command.customerId());
    order.setCustomer(customer);

    em.persist(order);
    return order.getId();
}
```

Log:

```text
DataIntegrityViolationException
  caused by ConstraintViolationException
    caused by SQLException:
      foreign key constraint fk_order_customer violated
```

Điều tra:

1. SQL INSERT có customer_id bằng ID từ command.
2. Query trực tiếp đúng database/schema xác nhận customer ID đó không tồn tại.
3. Request đang thuộc tenant Alpha; ID được client gửi có thể thuộc Beta hoặc đã bị xóa.
4. API trước đây dùng getReference() nên không validate existence sớm.
5. FK database ngăn ghi orphan như thiết kế.

Sửa:

```java
Customer customer = em.find(
    Customer.class, command.customerId());

if (customer == null) {
    throw new CustomerNotFoundException(
        command.customerId());
}

order.setCustomer(customer);
```

Nếu có multi-tenancy, `find()` phải chạy trong Session tenant Alpha và FK phải tenant-aware khi schema dùng shared tables. Test thêm ID của tenant Beta để xác nhận không thể tham chiếu chéo.

## 55. Ví dụ hoàn chỉnh: chẩn đoán sai kiểu dữ liệu

Entity:

```java
@Column(name = "total_amount")
private BigDecimal totalAmount;
```

DDL cũ:

```sql
total_amount NUMERIC(8, 2)
```

Giá trị gửi:

```text
123456789.99
```

Số chữ số cần thiết vượt precision 8, nên DB có thể báo numeric overflow.

Sửa không chỉ là đổi Java field. Cần:

1. Xác định giới hạn tiền nghiệp vụ.
2. Chọn precision/scale mới phù hợp.
3. Kiểm tra dữ liệu hiện tại có chuyển đổi an toàn không.
4. Viết migration tăng precision.
5. Cập nhật mapping/validation.
6. Test boundary values: min, max, scale, overflow.

Ví dụ migration:

```sql
ALTER TABLE purchase_orders
ALTER COLUMN total_amount TYPE NUMERIC(19, 2);
```

Đây là cú pháp PostgreSQL. DBMS khác cần syntax phù hợp; kiểm tra lock/rewrite impact trên bảng lớn trước khi triển khai.

## 56. Ví dụ hoàn chỉnh: chẩn đoán mapping association trùng cột

Mapping lỗi:

```java
@Column(name = "customer_id")
private Long customerId;

@ManyToOne
@JoinColumn(name = "customer_id")
private Customer customer;
```

Nếu code cần cả scalar ID và object association:

```java
@Column(name = "customer_id",
        insertable = false,
        updatable = false)
private Long customerId;

@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id")
private Customer customer;
```

Chỉ association ghi FK; scalar property đọc cùng cột. Cần kiểm tra:

- Khi đổi `customer`, scalar `customerId` có thể chưa phản ánh ngay như field Java nếu mapping/provider synchronization không được thiết kế.
- Khi đọc ID, có thể dùng `customer.getId()` hoặc một projection rõ.
- Không tự sửa `customerId` writable đồng thời với association.

Một thiết kế đơn giản hơn thường chỉ giữ association và dùng DTO projection khi cần scalar ID.

## 57. Integration tests phải dùng database gần production

H2 có ích cho một số unit tests nhưng không chứng minh:

- PostgreSQL enum/JSON/UUID types hoạt động đúng.
- MySQL collation/unsigned semantics đúng.
- SQL Server identity/locking đúng.
- Oracle sequence/precision đúng.
- Unique filtered/partial index đúng.
- FK, schema và isolation behavior đúng.

Nếu production dùng PostgreSQL, hãy chạy migration và Hibernate tests trên PostgreSQL thật hoặc Testcontainers PostgreSQL cùng major version phù hợp.

Một test skeleton:

```java
@Testcontainers
@SpringBootTest
class PurchaseOrderPersistenceIT {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("orders_test");

    @DynamicPropertySource
    static void datasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
```

Đây là khung cần dependencies/imports/test methods và migrations thực tế. Nếu production dùng DBMS khác, dùng đúng engine; không ép mọi database thành PostgreSQL chỉ vì tiện.

## 58. Test mapping và schema validation

Một nhóm integration tests nên kiểm tra:

1. Application context khởi tạo với `ddl-auto=validate`.
2. Tất cả entities/repositories thuộc đúng persistence unit.
3. Các association join columns khớp FK thật.
4. Insert/load/update/delete với representative values.
5. Enum/converter/date/UUID/JSON mapping.
6. Unique, NOT NULL, CHECK và FK constraints.
7. Composite keys/tenant-scoped constraints.
8. Bulk HQL/native SQL paths được kiểm soát.
9. Flush/commit/rollback behavior.
10. Concurrent update/optimistic locking.

Không viết test chỉ để lặp lại đúng implementation của converter hoặc repository. Test nên chứng minh hợp đồng với database và business invariants.

## 59. Migration và dữ liệu cũ phải được kiểm tra cùng nhau

Một mapping mới:

```java
@Column(nullable = false)
private String currencyCode;
```

không thể áp dụng an toàn nếu bảng hiện tại có hàng cũ với `currency_code IS NULL`.

Một migration có thể cần:

1. Thêm cột nullable.
2. Backfill dữ liệu từ nguồn đáng tin.
3. Kiểm tra rows còn null/bất hợp lệ.
4. Đặt default nếu có ý nghĩa nghiệp vụ.
5. Thêm NOT NULL constraint.
6. Deploy code đọc/ghi mapping mới theo chiến lược tương thích.

Không thêm NOT NULL trực tiếp vào bảng lớn rồi kỳ vọng DB tự đoán giá trị đúng cho các rows cũ.

## 60. Không chữa lỗi bằng cách tắt constraint

Khi FK/unique/check constraint gây lỗi, nó thường chỉ ra một invariant đang bị vi phạm. Tắt constraint có thể khiến:

- Orphan rows tích lũy.
- Hai records cùng một business identity.
- Dữ liệu âm hoặc status không hợp lệ.
- Một tenant tham chiếu entity tenant khác.
- Lỗi chỉ xuất hiện về sau trong báo cáo hoặc thanh toán.

Chỉ thay đổi constraint khi business rule thực sự thay đổi, có migration dữ liệu, kế hoạch rollback và test đầy đủ. Không tắt constraint như workaround để production “chạy qua”.

## 61. Khi nào cần sửa mapping, khi nào sửa dữ liệu?

| Bằng chứng | Hướng sửa thường phù hợp |
|---|---|
| Nhiều rows mới đều sai cùng một column mapping | Sửa mapping/DDL |
| Chỉ một số legacy rows có giá trị ngoài domain | Data cleanup/backfill có kiểm soát |
| SQL sai schema ở mọi requests | DataSource/schema/naming configuration |
| FK target thiếu do transaction order | Sửa unit-of-work/cascade/reference flow |
| Duplicate xảy ra dưới concurrent requests | Giữ unique constraint, xử lý race/idempotency |
| Optimistic lock ở concurrent update hợp lệ | Business retry/merge policy |
| Native SQL bỏ tenant predicate | Sửa query và kiểm thử isolation |
| Converter lỗi ở một số values cũ | Migrate representation hoặc hỗ trợ backward compatibility |

Không sửa code để chấp nhận dữ liệu sai nếu invariant vẫn phải được bảo vệ. Cũng không sửa dữ liệu để bù cho một mapping sai đang tiếp tục tạo rows lỗi.

## 62. Checklist trước khi đóng một incident persistence

- [ ] Root cause đã được xác định từ exception chain/vendor diagnostics.
- [ ] SQL statement và bind types đã được xem với dữ liệu đã redaction.
- [ ] Đúng DBMS/database/schema/tenant/transaction đã được xác minh.
- [ ] Mapping entity/association/ID đã được đối chiếu với DDL.
- [ ] Constraint/index có semantics phù hợp business rule.
- [ ] Legacy data và migration đã được kiểm tra.
- [ ] Flush/commit/rollback và concurrent behavior đã được xác nhận.
- [ ] Native SQL/bulk paths liên quan đã được rà soát.
- [ ] Có integration test tái hiện lỗi trên DBMS đích.
- [ ] API không lộ SQL, schema hoặc dữ liệu nhạy cảm.
- [ ] Metrics/logging đủ để nhận biết nếu lỗi tái diễn.

## 63. Sơ đồ quyết định chẩn đoán

```text
                 Hibernate/JPA persistence error
                              |
                              v
                  Error occurs at which stage?
                  /          |             \
                 /           |              \
                v            v               v
             Startup        Read            Write
                |            |               |
                v            v               v
          Entity scan,   Entity/ID,      Flush/commit SQL,
          mapping, EMF   association,    constraint, type,
          dialect        proxy/lazy      concurrency
                |            |               |
                +------------+---------------+
                             |
                             v
                Read full root exception chain
                             |
                             v
                 SQLState/vendor code available?
                       /             \
                     YES              NO
                      |                |
                      v                v
              Classify DB error   Inspect mapping/provider
                      \                /
                       \              /
                        v            v
                 Verify DB/schema/data/tenant
                             |
                             v
                   Compare mapping and DDL
                             |
                             v
                   Fix root cause, preserve
                   required constraints
                             |
                             v
                 Integration test on target DB
                             |
                             v
                    Deploy and observe
```

## 64. Tổng kết

Chẩn đoán Hibernate hiệu quả bắt đầu bằng việc xác định lỗi xuất hiện ở **startup, query, load, persist, flush/commit hay lazy access**. Sau đó đọc toàn bộ exception chain đến JDBC `SQLException`, SQLState và vendor error code. Các lỗi mapping như `Not a managed type`, `Unknown entity`, thiếu identifier hoặc duplicate column cần xem entity scanning, persistence unit và annotation access. Các lỗi constraint cần kiểm tra giá trị thực, FK/unique/NOT NULL/CHECK và transaction order. Các lỗi type cần đối chiếu Java type, Hibernate mapping, JDBC bind type, DDL và dữ liệu legacy.

Những lỗi tham chiếu không tồn tại thường liên quan `getReference()`, proxy chưa được khởi tạo, FK thiếu hoặc tenant/schema không đúng. `find()` có thể phát hiện thiếu dữ liệu sớm hơn, nhưng database constraint vẫn cần bảo vệ race conditions. Flush có thể trì hoãn lỗi đến cuối transaction; exception thứ cấp như `UnexpectedRollbackException` không nhất thiết là nguyên nhân đầu tiên.

Khi debug, hãy xem SQL generated và bind types có redaction, xác minh đúng database/schema/tenant, so mapping với migrations và kiểm tra DB metadata/constraints. Dùng integration tests trên DBMS đích để tái hiện unique/FK/type/locking failures. Giữ các constraint bảo vệ dữ liệu; sửa đúng mapping, migration, dữ liệu hoặc workflow tạo ra vi phạm.

**Nguyên tắc cần nhớ:** một thông báo Hibernate thường là tín hiệu ở tầng trên. Muốn sửa bền vững, phải tìm được statement, dữ liệu, mapping và invariant database thực sự gây ra lỗi.

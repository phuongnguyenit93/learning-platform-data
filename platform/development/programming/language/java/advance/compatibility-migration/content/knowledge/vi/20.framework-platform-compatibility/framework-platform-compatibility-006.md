# Hibernate, JPA và thay đổi truy vấn hoặc ánh xạ dữ liệu

Trong một đợt **Java Advance Compatibility Migration**, ứng dụng có Hibernate/JPA có thể biên dịch và khởi động thành công nhưng vẫn truy vấn sai, ghi dữ liệu khác trước, sinh SQL không tối ưu hoặc chỉ thất bại khi xử lý những bản ghi được tạo từ nhiều năm trước. Đổi JDK, đổi phiên bản Hibernate ORM, đổi Spring Data JPA, đổi JDBC driver và nâng database đều có thể làm lộ các khác biệt này.

Ví dụ: một entity dùng `@GeneratedValue(strategy = AUTO)` được provider mới ánh xạ tới sequence khác; một enum lưu bằng ordinal bị đổi thứ tự; một truy vấn HQL trước đây dựa vào ép kiểu ngầm nay bị parser mới từ chối; hoặc một câu fetch join gây tăng số hàng trung gian và ảnh hưởng phân trang. Những lỗi này khác nhau về bản chất, nên không thể giải quyết bằng cách chỉ sửa import hoặc nâng một dependency.

Bài học hướng dẫn cách phân biệt các tầng **JDK – JPA/Jakarta Persistence – Hibernate – framework – JDBC – database**, kiểm tra entity mapping và HQL/JPQL, bảo vệ dữ liệu hiện có, thiết kế integration tests và triển khai có khả năng rollback.

## 1. Xác định Hibernate và JPA là những tầng khác nhau

Một hệ thống Java persistence thường có kiến trúc:

~~~text
Service / Business Logic
            |
            v
Repository (Spring Data JPA hoặc code riêng)
            |
            v
JPA / Jakarta Persistence API
            |
            v
Hibernate ORM provider
            |
            v
JDBC Driver + Connection Pool
            |
            v
Database Engine + Schema + Persisted Data
~~~

**JPA/Jakarta Persistence** là đặc tả API và hợp đồng hành vi. **Hibernate ORM** là một provider triển khai đặc tả và còn có HQL, caching, bytecode enhancement, custom types và extensions. Spring Data JPA lại là một tầng repository framework phía trên.

Các mức thay đổi:

| Tầng | Ví dụ | Rủi ro migration |
|---|---|---|
| JDK | Java 8 → Java 17/21 | Reflection, class loading, JVM flags, security, bytecode |
| Persistence API | `javax.persistence` → `jakarta.persistence` | Namespace, annotations, binary API |
| Hibernate ORM | Major cũ → major mới | Mapping, query parser, SQL generation, type SPI |
| Spring Data JPA | Repository framework mới | Derived queries, projection, pagination |
| JDBC driver | Driver mới | Parameter binding, SQL types, timezone |
| Database | Engine/dialect/schema | Constraints, functions, collation, locking |
| Migration tool | Flyway/Liquibase | DDL, data backfill và rollback |

Không nên kết luận “JDK mới làm Hibernate sinh SQL khác” nếu cùng lúc framework BOM đã thay Hibernate, driver hoặc dialect. Cần ghi **artifact version được resolve thực tế**, thay vì chỉ nhìn property version trong POM.

## 2. Xác định ma trận hỗ trợ trước khi đổi

Những thông tin cần lưu:

- JDK vendor, feature/update và OS/CPU.
- Hibernate ORM version chính xác.
- JPA API version và namespace được dùng.
- Spring Boot, Spring Data, Jakarta EE container hoặc framework khác.
- JDBC driver, database engine và version.
- Hibernate Validator, Envers, Search, custom type libraries, cache provider.
- Maven/Gradle Wrapper, compiler target, annotation processors.
- Hibernate bytecode enhancer, agent, proxy framework.
- Schema migration tool và trạng thái schema đã triển khai.

Một bảng baseline/target:

| Thành phần | Hiện tại | Mục tiêu | Bằng chứng |
|---|---|---|---|
| JDK | JDK X | JDK Y | Ma trận vendor/framework |
| Persistence API | `javax` hoặc `jakarta` | API target | Dependency tree |
| Hibernate | Version H1 | Version H2 | Migration guide đúng phiên bản |
| Spring Data | Release train R1 | R2 | BOM và support matrix |
| JDBC | Driver D1 | D2 | Compatibility với database |
| Database | Engine E | Có thể giữ nguyên | Schema, SQL, query plans |
| Cache | Provider C1 | C2 hoặc giữ | Binary/cache-entry compatibility |

Nếu có thể, nên tách nâng JDK và nâng major ORM/framework để khoanh vùng nguyên nhân. Nếu không tồn tại tổ hợp trung gian được hỗ trợ, phải nâng phối hợp có kiểm soát chứ không cố chạy framework cũ trên runtime mới bằng những cờ JVM không được bảo đảm.

## 3. Chốt baseline bằng dữ liệu thật, không chỉ code

Trước migration, chọn các luồng nghiệp vụ quan trọng và ghi lại:

1. Query đầu vào và kết quả dự kiến.
2. Entity classes, table/column mappings, relationships.
3. SQL được Hibernate sinh và số statement mỗi request.
4. Schema thực tế, indexes, constraints, sequences, triggers.
5. Dữ liệu lịch sử có `NULL`, enum cũ, timezone, giá trị lớn.
6. Transaction boundaries, lock modes và flush behavior.
7. Hiệu năng p95/p99, query plans và connection pool metrics.
8. Binary/version của driver và ORM thực sự được nạp.

~~~text
App v1 + Hibernate v1 + Schema S1
                  |
                  +--> Golden fixtures
                  +--> Expected business results
                  +--> SQL count / execution plans
                  +--> Transaction/locking behavior
                  |
                  v
App v2 + Hibernate v2 + Schema S1/S2
                  |
                  v
So sánh giá trị, cardinality, constraints, hiệu năng
~~~

Một bài test tạo database trống bằng entity mới có thể xanh trong khi hàng triệu rows cũ không tương thích. Vì vậy cần **kiểm thử reader mới trên dữ liệu do writer cũ tạo ra**.

## 4. Chuyển namespace javax.persistence sang jakarta.persistence

Đổi từ Java Persistence API các thế hệ `javax.persistence` sang Jakarta Persistence các thế hệ `jakarta.persistence` ảnh hưởng source và binary API.

Ví dụ:

~~~java
// Thế hệ API cũ
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.Table;

@Entity
@Table(name = "orders")
public class OrderEntity {
    @Id
    private Long id;
}
~~~

Đối với provider/framework dùng Jakarta Persistence:

~~~java
// Thế hệ Jakarta Persistence
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "orders")
public class OrderEntity {
    @Id
    private Long id;
}
~~~

**Đổi namespace không phải thay đổi tự động do nâng JDK.** JDK không tự chuyển `javax.persistence.Entity` thành `jakarta.persistence.Entity`. Thay đổi do các thế hệ Jakarta Persistence và framework/provider liên quan.

Kiểm tra:

- Entity annotations, lifecycle callbacks và `EntityManager`.
- Query API, Criteria API và static metamodel classes.
- Các annotation trong generated code.
- Hibernate Validator / Jakarta Validation nếu có.
- Spring Data repository, converters và query DSL.
- Third-party starters/extensions còn dùng namespace cũ.
- Test entities và test configuration.

Một application có thể vô tình chứa cả `javax.persistence-api` lẫn `jakarta.persistence-api`, nhưng provider target có thể không nhận diện annotation từ namespace khác. Lỗi có thể xuất hiện dưới dạng “not a managed type”, “unknown entity” hoặc thiếu metadata.

**Lưu ý version:** một số artifact/chế độ chuyển tiếp tồn tại trong các dòng Hibernate cũ; không nên suy luận chỉ từ số major mà bỏ qua namespace thực tế của artifact và migration guide.

## 5. Entity mapping: tên bảng, cột và naming strategy

Mapping phụ thuộc khai báo tường minh lẫn chiến lược đặt tên ngầm định.

~~~java
@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @Column(name = "order_id")
    private Long id;

    @Column(name = "created_at")
    private Instant createdAt;
}
~~~

Những yếu tố có thể thay đổi khi nâng provider/framework:

- Implicit naming strategy.
- Physical naming strategy.
- Quoting/case folding của database identifiers.
- Reserved words trong dialect mới.
- Naming của join tables, foreign keys và indexes.
- Attribute access bằng field hoặc getter.
- Inheritance/discriminator mapping.

Nếu provider mới tìm `purchase_order` trong khi schema có `PurchaseOrder` hoặc `purchase_orders`, có thể phát sinh table not found; nguy hiểm hơn, một chế độ tự tạo schema có thể **tạo bảng trống mới** và khiến dữ liệu cũ như bị biến mất.

Không bật DDL auto-update ở production chỉ để “chữa” mismatch. Cần xác nhận schema thật và quyết định rõ liệu mapping hay database phải thay đổi.

### 5.1. JPQL dùng tên entity/property, không phải table/column

Truy vấn JPQL:

~~~java
select o
from PurchaseOrder o
where o.createdAt >= :from
order by o.id
~~~

Trong đó `PurchaseOrder` là entity name và `createdAt` là Java persistent property. Nếu đổi field `createdAt` thành `createdOn` nhưng giữ column `created_at`, JPQL vẫn cần sửa theo tên property; native SQL dùng tên column thật có thể không cần đổi.

Không trộn quy tắc của HQL/JPQL và native SQL khi xử lý lỗi query parser.

## 6. Field access, property access và inheritance

Với JPA, vị trí annotation `@Id` và metadata khác thường tham gia xác định **field access** hoặc **property access**.

Field access:

~~~java
@Entity
public class Customer {
    @Id
    private Long id;

    private String displayName;

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Property access:

~~~java
@Entity
public class Customer {
    private Long id;

    @Id
    public Long getId() {
        return id;
    }
}
~~~

Nếu refactor đưa annotation từ field lên getter mà không chủ đích thay access type, provider có thể thấy tập persistent properties khác. Những vấn đề liên quan:

- Getter chứa business logic hoặc side effects.
- `@Transient` nằm sai vị trí.
- Lombok/generated getters tạo behavior không mong muốn.
- Embedded types hoặc mapped superclass có access rules khác.
- Inheritance strategy và discriminator fields thay đổi.

Khi nâng Hibernate, hạn chế trộn refactor entity access strategy với thay đổi provider. Nếu buộc đổi, test read/write với dữ liệu cũ và xem SQL thật.

## 7. Sinh khóa chính: SEQUENCE, IDENTITY và AUTO

Các annotation thường gặp:

~~~java
@Id
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "order_id_generator"
)
@SequenceGenerator(
    name = "order_id_generator",
    sequenceName = "order_id_seq",
    allocationSize = 50
)
private Long id;
~~~

Các thuộc tính quan trọng:

- `sequenceName` là tên sequence ở database.
- `allocationSize` có thể ảnh hưởng cách provider tối ưu cấp ID.
- Database sequence increment/start value phải phù hợp giả định của generator.
- IDENTITY có semantics khác SEQUENCE và ảnh hưởng batching/insert.
- `AUTO` trao quyền lựa chọn cho provider/dialect, vì vậy default có thể thay qua version.

Khi nâng major ORM, cần kiểm tra implicit sequence naming và generator behavior theo migration guide đúng phiên bản. Không mặc định `@GeneratedValue(AUTO)` sẽ dùng cùng sequence/table trong mọi Hibernate version.

### 7.1. Các lỗi điển hình

- Hibernate tìm sequence tên mới không tồn tại.
- Sequence increment không phù hợp cấu hình ORM.
- ID được cấp trùng trong rolling deploy do hai phiên bản dùng strategy khác nhau.
- Dữ liệu mới được ghi bằng sequence khác nhưng cùng bảng.
- Schema tool đề xuất tạo sequence mà nhóm vận hành không mong đợi.

**Không reset sequence thủ công trên production** khi chưa biết ID hiện có và các writer đang hoạt động. Thử insert đồng thời trên schema có dữ liệu lịch sử trước khi rollout.

## 8. Kiểu dữ liệu Java ↔ JDBC ↔ SQL

ORM chuyển đổi giữa Java type và database type. Khi Hibernate hoặc JDBC driver đổi, cùng một field có thể được bind/đọc bằng một JDBC type khác.

| Java type | Vấn đề cần xét |
|---|---|
| `BigDecimal` | Precision, scale, rounding, overflow |
| `Boolean` | BOOLEAN, BIT, SMALLINT, CHAR representation |
| `UUID` | Native UUID, CHAR, BINARY |
| `Instant` | Timestamp, UTC normalization, precision |
| `LocalDateTime` | Timezone-less semantics |
| `OffsetDateTime` | Offset storage và normalization |
| `Enum` | STRING, ORDINAL, SQL enum |
| `byte[]` | VARBINARY, BLOB, LOB streaming |
| JSON/array | Dialect và custom JDBC types |
| Custom value object | AttributeConverter, UserType, provider SPI |

Một mapping trước đây dùng `CHAR(36)` để lưu UUID có thể không khớp với default type target. Nếu schema validation báo expected type khác actual type, phải xác định:

1. Dữ liệu thực tế đang được lưu ra sao?
2. Provider target mong đợi JDBC/SQL type gì?
3. Có converter/dialect custom nào tham gia?
4. Có service khác cũng đọc cùng cột không?
5. Thay ORM mapping hay thay database schema là lựa chọn ít rủi ro hơn?

Không tự sửa DDL trước khi xem migration guide và các consumers khác.

## 9. Converter và custom Hibernate type

Một `AttributeConverter` có thể tách Java representation khỏi database representation:

~~~java
@Converter(autoApply = false)
public class CurrencyCodeConverter
        implements AttributeConverter<CurrencyCode, String> {

    @Override
    public String convertToDatabaseColumn(CurrencyCode code) {
        return code == null ? null : code.name();
    }

    @Override
    public CurrencyCode convertToEntityAttribute(String stored) {
        return stored == null
                ? null
                : CurrencyCode.valueOf(stored);
    }
}
~~~

Nhưng converter không tự giải quyết mọi vấn đề:

- Dữ liệu cũ có giá trị enum/code không còn tồn tại.
- Query parameters có thể dùng đường binding khác khi provider nhận custom type.
- Native query projections có thể không đi qua converter theo cùng cách.
- JSON/array/UUID custom types có thể phụ thuộc Hibernate SPI đã thay.
- `autoApply` có thể áp dụng rộng hơn dự kiến.
- Một null hoặc invalid string có thể tạo lỗi khi materialize entity.

Nếu dùng `UserType`, `BasicType`, `CompositeUserType`, custom dialect hoặc thư viện kiểu Hibernate bên thứ ba, cần xác nhận API extension của major mới. **Chỉ đổi import để compile không chứng minh type descriptor và SQL binding vẫn đúng.**

## 10. Enum mapping và dữ liệu cũ

Entity có thể khai báo:

~~~java
@Enumerated(EnumType.STRING)
private OrderStatus status;
~~~

hoặc:

~~~java
@Enumerated(EnumType.ORDINAL)
private OrderStatus status;
~~~

### 10.1. ORDINAL có nguy cơ đổi ý nghĩa

Ban đầu:

~~~java
enum OrderStatus {
    CREATED, PAID, CANCELLED
}
~~~

Nếu database lưu ordinal, giá trị `1` nghĩa là `PAID`. Sau khi chèn một giá trị mới vào giữa enum, cùng giá trị `1` có thể bị hiểu thành trạng thái khác. Đây là **semantic data corruption** dù Hibernate không ném exception.

### 10.2. STRING cũng cần migration khi rename

Nếu database có `PAID` nhưng enum mới đổi thành `COMPLETED`, reader có thể không nhận ra giá trị cũ. Hướng giảm rủi ro:

- Giữ storage code ổn định.
- Có converter hỗ trợ mã legacy khi cần.
- Backfill dữ liệu bằng migration có kiểm soát.
- Không xóa parser cũ khi backup/replay còn chứa mã cũ.
- Test unknown values thay vì silently gán default sai.

Với một số dialect/version, mapping enum dạng string có thể tương tác SQL enum native hoặc DDL khác. Cần kiểm tra bản provider cụ thể.

## 11. Timestamp và timezone không được thay đổi âm thầm

Phân biệt:

- `Instant`: một thời điểm trên trục UTC.
- `LocalDateTime`: ngày-giờ không gắn timezone.
- `OffsetDateTime`: có offset.
- `LocalDate`: ngày không có thời gian.
- `Timestamp`/`Date` legacy: semantics khác các kiểu `java.time`.

Khi migration, kiểm tra:

- SQL type `TIMESTAMP` hay `TIMESTAMP WITH TIME ZONE`.
- JDBC timezone configuration.
- Default JVM timezone.
- Database session timezone.
- Precision và rounding.
- Các bản ghi gần mốc ngày, cuối tháng, DST.
- Điều kiện truy vấn range.

Ví dụ lọc nửa khoảng thời gian:

~~~java
List<OrderEntity> result = entityManager
        .createQuery(
            "select o from OrderEntity o " +
            "where o.createdAt >= :start " +
            "and o.createdAt < :end",
            OrderEntity.class)
        .setParameter("start", startInstant)
        .setParameter("end", endInstant)
        .getResultList();
~~~

Phải bind `startInstant` và `endInstant` theo cùng kiểu dữ liệu mà mapping hỗ trợ. Đổi từ `LocalDateTime` sang `Instant` cần xác định ý nghĩa dữ liệu cũ, không chỉ đổi tên class.

## 12. Relationships: owning side, cascade và orphanRemoval

Ví dụ:

~~~java
@Entity
public class Customer {

    @Id
    private Long id;

    @OneToMany(mappedBy = "customer")
    private List<OrderEntity> orders;
}

@Entity
public class OrderEntity {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;
}
~~~

`mappedBy = "customer"` trỏ tới tên Java persistent attribute trên entity phía kia, không phải tên cột `customer_id`.

Các yếu tố cần kiểm tra:

- Owning side của association.
- Join column, nullable và FK constraints.
- `CascadeType.PERSIST`, `MERGE`, `REMOVE`.
- `orphanRemoval`, đặc biệt với collections.
- Bidirectional consistency trong Java object graph.
- Quan hệ nullable, orphaned rows và dữ liệu cũ.
- Fetch type và bytecode enhancement.
- Behavior `equals/hashCode` với proxy hoặc generated ID.

Một thay đổi cascade hoặc orphan-removal có thể xóa rows thật dù source vẫn compile. Cần test thêm/xóa liên kết trên dữ liệu đã tồn tại, quan sát SQL `DELETE` và foreign-key behavior.

## 13. Lazy loading, proxy và N+1 queries

Hibernate có thể lazy-load associations qua proxies hoặc bytecode enhancement. Sau migration, cùng lời gọi repository có thể tạo số SQL khác do fetch plan, framework defaults hoặc cách xử lý query thay đổi.

Ví dụ N+1:

~~~java
List<OrderEntity> orders = entityManager
        .createQuery(
            "select o from OrderEntity o",
            OrderEntity.class)
        .getResultList();

for (OrderEntity order : orders) {
    System.out.println(order.getCustomer().getName());
}
~~~

Nếu `customer` chưa được fetch và các customer khác nhau, vòng lặp có thể tạo thêm nhiều truy vấn. Đây là vấn đề performance, không nhất thiết có exception.

### 13.1. Fetch join

~~~java
List<OrderEntity> orders = entityManager
        .createQuery(
            "select o from OrderEntity o " +
            "join fetch o.customer " +
            "where o.status = :status",
            OrderEntity.class)
        .setParameter("status", OrderStatus.PAID)
        .getResultList();
~~~

Fetch join hữu ích nhưng không phải giải pháp mặc định cho mọi query:

- Join trên to-many có thể nhân số SQL rows.
- Pagination với collection fetch join có thể bị hạn chế hoặc dẫn đến in-memory pagination tùy provider/cấu hình.
- Fetch nhiều collection/bag có thể gây lỗi hoặc tạo rất nhiều row.
- `inner join fetch` có thể loại bản ghi không có association; khi cần có thể phải dùng `left join fetch`.

### 13.2. EntityGraph

Khi muốn điều khiển fetch theo use case:

~~~java
EntityGraph<OrderEntity> graph =
        entityManager.createEntityGraph(OrderEntity.class);
graph.addAttributeNodes("customer");

List<OrderEntity> orders = entityManager
        .createQuery(
            "select o from OrderEntity o where o.status = :status",
            OrderEntity.class)
        .setParameter("status", OrderStatus.PAID)
        .setHint("jakarta.persistence.fetchgraph", graph)
        .getResultList();
~~~

Ví dụ dùng Jakarta namespace; với các thế hệ API `javax`, hint namespace tương ứng có thể khác. Đọc đúng tài liệu phiên bản provider trước khi copy.

### 13.3. LazyInitializationException

Nếu truy cập lazy association ngoài persistence context phù hợp, có thể gặp `LazyInitializationException`. Đừng chỉ bật Open Session in View hoặc đổi mọi association sang `EAGER` để che lỗi. Hãy xác định transaction boundary, fetch plan và DTO/projection theo từng use case.

## 14. HQL/JPQL: parser và semantic validation

Hibernate HQL mở rộng so với JPQL chuẩn. Khi nâng major, parser và semantic query model có thể thay đổi, khiến query cũ không còn hợp lệ.

JPQL:

~~~java
select o
from OrderEntity o
where o.customer.id = :customerId
order by o.createdAt desc
~~~

Native SQL:

~~~sql
SELECT *
FROM purchase_order
WHERE customer_id = ?
ORDER BY created_at DESC;
~~~

**JPQL dùng entity names và Java persistent properties.** Native SQL dùng database table/column names.

### 14.1. Implicit type coercion

Ví dụ query lỗi:

~~~java
select o from OrderEntity o
where o.createdAt = :dateAsText
~~~

Nếu `createdAt` là `Instant` nhưng parameter là `String`, provider cũ/database có thể thực hiện conversion ngầm; provider mới có thể từ chối sớm. Thay vì dùng cast tùy tiện, bind đúng kiểu:

~~~java
Instant time = Instant.parse("2026-11-12T08:00:00Z");

List<OrderEntity> results = entityManager
        .createQuery(
            "select o from OrderEntity o where o.createdAt = :time",
            OrderEntity.class)
        .setParameter("time", time)
        .getResultList();
~~~

Nếu dữ liệu cũ không thật sự ở UTC, đây chưa phải toàn bộ giải pháp; phải xử lý semantic time zone đúng.

### 14.2. HQL-specific functions

Một số query dùng cú pháp hoặc function riêng của Hibernate/database:

~~~java
select function('normalize_name', c.displayName)
from Customer c
~~~

Khả năng suy luận kiểu và cách đăng ký function có thể khác qua Hibernate major. Các custom dialect/functions cần được chuyển sang extension API được phiên bản target hỗ trợ, không chỉ sửa tên class.

### 14.3. Named và dynamic queries

Các truy vấn được lưu ở:

- `@NamedQuery` / `@NamedNativeQuery`.
- `@Query` của Spring Data.
- Query strings dựng trong service.
- Criteria API/Specifications.
- Reporting/batch queries.
- Stored procedure calls.

Một named query có thể được kiểm tra khi bootstrap, còn dynamic query chỉ gây lỗi khi đường code được gọi. Vì vậy chạy startup test không đủ để xác nhận parser migration.

## 15. Joins, DISTINCT, ORDER BY và pagination

### 15.1. Join semantics

JPQL:

~~~java
select o
from OrderEntity o
join o.customer c
where c.enabled = true
~~~

là inner join. Nếu dùng `left join` nhưng vẫn đặt điều kiện `c.enabled = true` trong `where`, những hàng không có customer không còn thỏa, dù cú pháp dùng left join.

Khi đổi ORM, đừng nhầm thay đổi SQL rendering với lỗi logic đã tồn tại. Test với dữ liệu có association `null` để biết hợp đồng kỳ vọng.

### 15.2. Duplicate rows và DISTINCT

Fetch join trên to-many có thể tạo nhiều SQL rows cho một entity. Cách Hibernate xử lý duplicate entity references có thể thay đổi theo version/query shape.

Phân biệt:

- SQL rows trùng.
- Java entity references trùng trong result list.
- `distinct` trên scalar projection.
- Thứ tự/pagination sau join.

Không tự thêm hoặc xóa `distinct` chỉ vì SQL text khác; xác nhận cardinality và kết quả trên fixture.

### 15.3. Pagination ổn định

~~~java
List<OrderEntity> page = entityManager
        .createQuery(
            "select o from OrderEntity o " +
            "order by o.createdAt desc, o.id desc",
            OrderEntity.class)
        .setFirstResult(offset)
        .setMaxResults(limit)
        .getResultList();
~~~

Cần `ORDER BY` có tie-breaker ổn định như ID để tránh bản ghi nhảy trang khi nhiều rows có cùng timestamp. Dialect/provider target có thể sinh pagination SQL khác; kiểm tra trên engine thật với dữ liệu đủ lớn.

## 16. Projection, aggregate và kiểu trả về

Trong JPQL, `count` thường có result type `Long`:

~~~java
Long count = entityManager
        .createQuery(
            "select count(o) from OrderEntity o",
            Long.class)
        .getSingleResult();
~~~

Không mặc định mọi phép `count` native SQL sẽ trả `Integer` hoặc `BigInteger` giống nhau trên mọi JDBC driver/dialect. DTO constructor projections cũng cần khớp kiểu:

~~~java
select new com.acme.report.OrderSummary(
    o.status, count(o)
)
from OrderEntity o
group by o.status
~~~

Khi nâng Hibernate, nếu type inference thay đổi hoặc constructor không còn khớp, có thể gặp lỗi query validation hoặc materialization.

Với `sum`, `avg` và phép tính số, cần đặc biệt chú ý precision/scale và nguy cơ overflow. Không giải quyết bằng cách gọi `intValue()` ở mọi kết quả.

## 17. Criteria API và static metamodel

Ví dụ dùng Jakarta Persistence Criteria:

~~~java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();

CriteriaQuery<OrderEntity> query =
        cb.createQuery(OrderEntity.class);

Root<OrderEntity> root = query.from(OrderEntity.class);

ParameterExpression<OrderStatus> status =
        cb.parameter(OrderStatus.class, "status");

query.select(root)
     .where(cb.equal(root.get("status"), status));

List<OrderEntity> results = entityManager
        .createQuery(query)
        .setParameter("status", OrderStatus.PAID)
        .getResultList();
~~~

Nếu dùng generated static metamodel:

~~~java
root.get(OrderEntity_.status)
~~~

cần nâng annotation processor cùng namespace `jakarta.persistence` target. Clean rebuild quan trọng để không nhặt lại generated sources/classfiles từ `javax` cũ.

Kiểm tra thêm Spring Data `Specification`, QueryDSL, criteria joins và dynamic sorting vì các query này không luôn xuất hiện dưới dạng chuỗi tìm kiếm dễ nhận biết.

## 18. Native SQL và result mapping

Native query ít phụ thuộc JPQL parser nhưng phụ thuộc chặt vào database, JDBC và mapping kết quả.

~~~java
List<?> rows = entityManager
        .createNativeQuery(
            "select order_id, total_amount " +
            "from purchase_order where status = :status")
        .setParameter("status", "PAID")
        .getResultList();
~~~

Các điểm cần kiểm tra:

- Column names và aliases.
- Kiểu scalar trả về như `Long`, `BigInteger`, `BigDecimal`.
- Thứ tự cột và duplicate column labels.
- `@SqlResultSetMapping`.
- JSON/array/UUID bindings.
- SQL functions, casts và vendor syntax.
- `IN` parameters, bao gồm empty collections.
- Native pagination, locks và stored procedures.

Nếu code ép mỗi row thành `Object[]` nhưng provider mới trả một scalar hoặc mapping khác, có thể xuất hiện `ClassCastException`. Dùng result mapping tường minh khi thích hợp.

Không chuyển tất cả native SQL sang JPQL trong cùng đợt migration chỉ vì “nên dùng ORM”; đó là một thay đổi semantics/performance riêng cần test.

## 19. Database dialect quyết định nhiều thứ hơn cú pháp

Hibernate dialect có thể ảnh hưởng:

| Tính năng | SQL behavior có thể thay đổi |
|---|---|
| ID generator | SEQUENCE, IDENTITY, `RETURNING` |
| Pagination | `LIMIT/OFFSET` hoặc cú pháp vendor |
| Locking | `FOR UPDATE`, lock timeout/hints |
| Boolean/UUID/enum | JDBC/SQL type và literal |
| Timestamp | Cast, timezone normalization |
| Aggregate/functions | SQL rendering và result type |
| JSON/array | Native operators và bindings |
| DDL | Index, constraint, column type |

Một provider mới có thể đổi dialect class names hoặc chiến lược suy ra dialect dựa trên JDBC metadata. Đừng giữ nguyên tên một dialect class cũ đã không còn phù hợp mà chưa kiểm tra migration guide.

Quan trọng là phân biệt lỗi do **Hibernate sinh SQL khác** với lỗi do **JDBC driver/database version khác**. So SQL, bind types, execution plans và actual database error code, không chỉ nhìn exception wrapper.

## 20. Schema validate khác với schema migration

Một số dự án Spring Boot dùng:

~~~properties
spring.jpa.hibernate.ddl-auto=validate
~~~

Validate kiểm tra mapping và schema theo khả năng provider nhưng không kiểm chứng toàn bộ dữ liệu/query/transaction semantics. Các chế độ tạo hoặc cập nhật schema tự động không phải công cụ migration dữ liệu production đáng tin cậy.

Ưu tiên Flyway/Liquibase hoặc quy trình SQL migrations được kiểm soát:

~~~text
schema S1
   |
   | Expand: thêm cấu trúc tương thích
   v
schema S1+ (v1 và v2 cùng đọc được)
   |
   | Backfill và chuyển writer
   v
schema S2-compatible
   |
   | Chờ hết phiên bản cũ và cửa sổ rollback
   v
Contract: bỏ cột/hợp đồng cũ
~~~

Ví dụ thêm cột `status_code` mới:

1. Thêm cột nullable mà không xóa `status` cũ.
2. Cho reader v2 hỗ trợ cả hai representation.
3. Backfill dữ liệu cũ theo mapping có kiểm soát.
4. Chuyển writer sau khi những reader liên quan sẵn sàng.
5. Chỉ bỏ cột cũ khi không còn v1 và backup/replay policy cho phép.

Không dùng `hibernate.hbm2ddl.auto=update` ở production để “tự sửa” khác biệt mapping sau major migration.

## 21. Transactions, flush và dirty checking

Một managed entity có thể được đồng bộ xuống DB nhờ dirty checking khi flush/commit:

~~~java
@Transactional
public void markPaid(Long orderId) {
    OrderEntity order = entityManager.find(
            OrderEntity.class, orderId);

    order.setStatus(OrderStatus.PAID);
}
~~~

Điều kiện là transaction và persistence context được quản lý đúng; detached object không tự được cập nhật chỉ vì setter đã gọi.

Cần test:

- Flush mode và thời điểm SQL được gửi.
- Transaction propagation/isolation.
- `persist`, `merge`, `remove` behavior.
- Bulk JPQL update/delete.
- Constraint violations xảy ra ở flush hay commit.
- Batch insert ordering.
- Exception translation và rollback rules.

### 21.1. Bulk update và stale state

~~~java
int changed = entityManager
        .createQuery(
            "update OrderEntity o " +
            "set o.status = :newStatus " +
            "where o.status = :oldStatus")
        .setParameter("newStatus", OrderStatus.PAID)
        .setParameter("oldStatus", OrderStatus.CREATED)
        .executeUpdate();
~~~

Bulk JPQL updates thường không đồng bộ mọi managed entity đã nằm trong persistence context giống cách setter + dirty checking hoạt động. Trong một transaction dài, có thể cần refresh/clear phù hợp để tránh dùng state cũ.

Thành công của câu update không chứng minh mọi object sau đó đã phản ánh trạng thái mới.

## 22. Optimistic và pessimistic locking

Optimistic locking:

~~~java
@Entity
public class Inventory {
    @Id
    private Long id;

    @Version
    private long version;

    private int quantity;
}
~~~

Thử hai transaction cùng cập nhật một row, xác minh version increments và exception/retry policy. Bulk updates hoặc direct SQL có thể bypass cơ chế version nếu không được thiết kế cẩn thận.

Pessimistic locking:

~~~java
Inventory item = entityManager.find(
        Inventory.class,
        id,
        LockModeType.PESSIMISTIC_WRITE);
~~~

SQL lock được sinh phụ thuộc database dialect và provider. Khi nâng Hibernate, kiểm tra transaction timeout, deadlock, `NOWAIT`/`SKIP LOCKED` nếu ứng dụng sử dụng và thứ tự lock trong concurrent flows.

Không dùng H2 mock như bằng chứng cuối cho locking behavior của PostgreSQL/Oracle/MySQL.

## 23. Cache của Hibernate có thể lưu trạng thái cũ

Hibernate first-level cache nằm trong persistence context. Second-level cache/query cache có thể lưu qua nhiều Session và thậm chí qua deployments tùy backend.

Rủi ro:

- Format cache entry thay đổi giữa Hibernate major.
- Region name hoặc key strategy đổi.
- Serializer không đọc được entry do version trước ghi.
- Invalidation không đồng bộ trong rolling deploy.
- Query cache mang result shape cũ.

Chiến lược có thể gồm:

- Version cache namespace/regions.
- Cho phép cache rebuild nếu nguồn DB chịu được.
- Vô hiệu hóa cache trong một giai đoạn đã đo tác động.
- Tách region giữa v1/v2 nếu chúng không có compatibility.
- Xác minh cache provider/integration version theo Hibernate target.

Không xóa toàn bộ Redis một cách mù quáng nếu cùng kho đang chứa sessions, locks hoặc idempotency keys.

## 24. Spring Data JPA và derived queries

Với Spring Data JPA:

~~~java
public interface OrderRepository
        extends JpaRepository<OrderEntity, Long> {

    List<OrderEntity> findByStatusOrderByCreatedAtDesc(
            OrderStatus status);

    Page<OrderEntity> findByCustomerId(
            Long customerId, Pageable pageable);
}
~~~

Những method này có thể được framework chuyển thành queries dựa trên entity properties. Nâng major có thể ảnh hưởng:

- Derived query name parsing.
- Nested properties và join traversal.
- Count queries sinh cho `Page`.
- Sorting, pagination và projections.
- `@Query`, `@EntityGraph` và native queries.
- Repository transaction defaults.
- Entity scanning và persistence unit configuration.

Không chỉ test CRUD `save/findById`. Các named queries và reporting queries có thể chỉ chạy ở những nghiệp vụ hiếm.

## 25. SQL logs và hiệu năng phải được kiểm soát

Các công cụ quan sát:

- Hibernate SQL logging.
- JDBC data source proxy trong test.
- Hibernate statistics.
- Database slow query logs và explain plans.
- APM/tracing đã bảo vệ thông tin nhạy cảm.
- Query count per request và p95/p99.

Ví dụ một số cấu hình Spring:

~~~properties
spring.jpa.show-sql=false
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Tên log category bind values có thể khác theo Hibernate major. Bind logging có thể lộ PII, token hoặc thông tin khách hàng, nên chỉ bật ở môi trường được phép và có kiểm soát.

Đừng chỉ diff chuỗi SQL. So thêm:

1. Kết quả nghiệp vụ và số hàng.
2. Number of statements/round trips.
3. Query plan/index usage.
4. Bytes transferred và row multiplication.
5. Locking/transaction behavior.
6. Response latency và DB CPU.

Một SQL khác về cú pháp có thể vẫn đúng và nhanh; một SQL rất giống có thể có plan kém do parameter type hoặc missing index.

## 26. Kiểm thử bằng database gần production

H2 hữu ích cho test nhẹ nhưng không đại diện đầy đủ cho database thực. Các khác biệt thường gặp:

- SQL types `BOOLEAN`, `UUID`, `JSON`, `ARRAY`.
- Quoting, case sensitivity và collation.
- Timezone/precision.
- Sequence và identity.
- Locking/isolation/deadlocks.
- Vendor functions và casts.
- Pagination syntax và execution plan.
- Foreign-key, trigger, generated columns.

Dùng database engine/version gần production cho persistence integration tests, có thể qua Testcontainers hoặc môi trường test được vận hành riêng.

Một golden-test matrix:

| Test | Dữ liệu | Điều xác minh |
|---|---|---|
| Load legacy entity | Rows v1 | Mapping, null và enum |
| Insert v2 | Schema thật | ID/sequence, constraints |
| Update relation | Associations cũ | Cascade, FK, orphanRemoval |
| JPQL/HQL | Fixture có joins | Cardinality, sorting, result type |
| Native SQL | Driver/database thật | Scalar mapping và functions |
| Timestamp | Boundary values | Timezone, precision |
| Pagination | Nhiều rows trùng sort key | Không trùng/mất bản ghi |
| Concurrency | Hai transactions | Version/locking |
| Cache | Entry do v1 ghi | Readability và isolation |
| Rollback | Rows v2 trên reader v1 | Hai chiều nếu deployment yêu cầu |

### 26.1. Fixture nên bảo vệ dữ liệu nhạy cảm

Có thể tổ chức:

~~~text
fixtures/
  schema/baseline.sql
  data/legacy-order-status.sql
  data/null-and-foreign-key.sql
  data/timezone-boundary.sql
  expected/report-summary.json
~~~

Không sao chép dữ liệu nhận diện khách hàng hoặc secrets thẳng từ production vào repository. Dữ liệu giả lập/anonymized vẫn phải giữ được các trường hợp biên cần test.

## 27. Rolling deployment và backward data compatibility

Trong rolling deploy, bản cũ và mới có thể cùng truy cập database:

~~~text
App v1 + Hibernate H1 ----+
                          +---- Schema S ---- Persisted data
App v2 + Hibernate H2 ----+
~~~

Nếu v2 yêu cầu cột bị rename ngay, v1 sẽ lỗi khi còn hoạt động. Nếu v2 ghi enum/format mới, v1 có thể không đọc được dù schema chưa thay.

Cần thử cả:

- **V1 writer → V2 reader:** phiên bản mới đọc dữ liệu cũ.
- **V2 writer → V1 reader:** cần khi rollback hoặc mixed-version deployment.
- V1/V2 cùng insert/update một bảng.
- Sequence/identity generation không tạo ID conflict.
- Cache/session liên quan không có format xung đột.
- Transaction/locking giữ được invariant.

Nếu không có hai chiều compatibility, phải điều chỉnh rollout, dùng bridge release hoặc maintenance window được phê duyệt; không mặc định rolling luôn an toàn.

## 28. Rollback không chỉ hạ dependency Hibernate

Sau khi v2 chạy, có thể đã có:

- Column/type/sequence mới.
- Enum values mới.
- Timestamps được chuẩn hóa khác.
- Query result/cache format mới.
- Backfill dữ liệu không thể đảo ngược.
- Constraint/index khác.
- Dữ liệu do framework mới serialize.

Chỉ đổi `hibernate-core` về version cũ không khôi phục database cũ. Rollback phải gồm app artifact, ORM provider, schema state, dữ liệu và các consumer vẫn đang hoạt động.

Phải xác định **point of no return** trước khi drop cột, rotate khóa không thể phục hồi hoặc phát data format mà phiên bản cũ không biết đọc.

## 29. Một ví dụ tổng hợp về migration đơn hàng

Giả sử entity hiện tại có:

~~~text
OrderEntity
  id              @GeneratedValue(AUTO)
  status          EnumType.ORDINAL
  createdAt       LocalDateTime
  customer        @ManyToOne(LAZY)
  total           BigDecimal
~~~

Các lỗi có thể lộ khi nâng Hibernate:

1. Provider target chọn tên sequence hoặc cách allocate ID khác.
2. Enum ordinal đổi semantic sau khi thêm status.
3. Timestamp đọc theo timezone khác.
4. HQL report cũ dùng phép so sánh type không hợp lệ.
5. DTO projection kỳ vọng `Integer` nhưng query count trả `Long`.
6. Pagination join fetch làm số SQL rows tăng.
7. Spring Data generated count query không đúng với custom join.
8. Schema auto-update muốn đổi column type.
9. Old/new nodes cùng ghi nhưng assumptions về ID/schema khác.

Lộ trình:

- **Bước 1:** Giữ bản database đã ẩn danh có dữ liệu cũ và baseline SQL/kết quả.
- **Bước 2:** Liệt kê provider, framework, driver, dialect thực tế.
- **Bước 3:** Xác định ID generator và schema sequence metadata.
- **Bước 4:** Kiểm tra enum, timestamp và converter semantics trên rows cũ.
- **Bước 5:** Nâng dependency trong branch riêng, không thay toàn bộ business features.
- **Bước 6:** Chạy schema validate, rồi mọi named/dynamic/Criteria/native queries trọng yếu.
- **Bước 7:** So query counts, plans, transaction/locking.
- **Bước 8:** Thiết kế expand–migrate–contract cho DDL cần đổi.
- **Bước 9:** Test mixed-version nếu rollout thực tế dùng rolling deploy.
- **Bước 10:** Canary, theo dõi DB/errors/p99, kiểm chứng rollback thực tế.

Dự án chỉ có thể tuyên bố bước migration thành công khi **kết quả truy vấn, dữ liệu persist và ràng buộc nghiệp vụ** được bảo toàn, không chỉ khi `EntityManagerFactory` khởi tạo được.

## 30. Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân khả dĩ | Bắt đầu kiểm tra |
|---|---|---|
| `Not a managed type` | Entity scan/namespace/provider mismatch | `javax`/`jakarta`, dependency tree |
| Missing table/column | Naming strategy hoặc schema drift | Mapping và database metadata |
| Sequence not found | Generator implicit name đổi | `@GeneratedValue`, sequence SQL |
| `SemanticException` / invalid HQL | Query parser và type mismatch | JPQL/HQL source, bound parameter types |
| `ClassCastException` khi lấy result | Projection/scalar JDBC type khác | Result mapping và JDBC driver |
| `LazyInitializationException` | Persistence context/fetch plan | Transaction và lazy access |
| N+1 / DB load tăng | Fetch plan/query shape | SQL count và EntityGraph/fetch joins |
| `ConstraintViolationException` | FK, unique, nullable hoặc DDL | Database constraint và SQL root cause |
| `OptimisticLockException` | Version conflict | Concurrency và `@Version` |
| Time/enum đọc sai mà không lỗi | Semantic data compatibility | Golden fixtures |
| Rollback không hoạt động | V2 đã ghi schema/data không đọc ngược | Expand–contract và rollback test |
| Query pass H2 nhưng fail production DB | Dialect/driver behavior | Integration test với engine thật |

Thông báo exception thay đổi theo provider/framework version. Luôn xem root cause, SQL được sinh và dữ liệu cụ thể thay vì chỉ tên exception ngoài cùng.

## 31. Checklist trước khi chốt migration

- [ ] Đã ghi phiên bản JDK, Hibernate, JPA, Spring Data, JDBC và database thật.
- [ ] Đã xác nhận support matrix các thành phần đó.
- [ ] Đã phân biệt nâng JDK và nâng major ORM/framework.
- [ ] Đã xử lý namespace `javax.persistence` / `jakarta.persistence` đúng target.
- [ ] Đã rebuild generated metamodel/query sources tương ứng.
- [ ] Đã kiểm tra entity scanning, annotations và access type.
- [ ] Đã xác minh naming strategy, table/column/foreign-key names.
- [ ] Đã xác minh sequence/identity/UUID generator và concurrency.
- [ ] Đã kiểm tra numeric precision, Boolean, UUID, JSON/array type mappings.
- [ ] Đã kiểm tra converter/custom type SPI và dữ liệu lịch sử.
- [ ] Đã kiểm tra enum ordinal/string, values không còn dùng.
- [ ] Đã kiểm tra timezone/precision với timestamps cũ.
- [ ] Đã kiểm tra association owning side, cascade và orphanRemoval.
- [ ] Đã so SQL count, N+1, proxies, fetch joins và entity graphs.
- [ ] Đã chạy named queries, HQL/JPQL, Criteria, Spring Data và native SQL.
- [ ] Đã xác minh projection, count/sum types, pagination và ordering.
- [ ] Đã kiểm tra transaction, flush, bulk updates và optimistic/pessimistic locks.
- [ ] Đã kiểm tra caching behavior khi nhiều versions cùng chạy.
- [ ] Đã chạy migrations trên fixture có schema và dữ liệu cũ.
- [ ] Đã dùng database gần production, không chỉ H2.
- [ ] Đã có golden fixtures, SQL metrics và performance baseline.
- [ ] Đã kiểm tra V1→V2 và V2→V1 nếu rolling/rollback cần.
- [ ] Đã xác định điểm không thể rollback và backup/restore plan.
- [ ] Đã bảo vệ PII/secrets khi thu SQL và bind logs.

## 32. Kết luận

Hibernate/JPA migration là sự thay đổi hợp đồng giữa **Java object model, API persistence, SQL do provider sinh ra, database schema và dữ liệu đang tồn tại**. Một query hợp lệ về cú pháp không bảo đảm kết quả đúng; một entity có thể persist mà vẫn sai enum/timezone; một ứng dụng khởi động thành công nhưng N+1 hoặc locking regression có thể làm production chậm hoặc sai nghiệp vụ.

Cách làm có cơ sở là chốt baseline bằng SQL và dữ liệu cũ, nâng đúng tổ hợp JDK/framework/provider/JDBC được hỗ trợ, kiểm thử mapping và từng loại truy vấn, quản lý schema bằng migration có kiểm soát, rồi triển khai với khả năng đọc dữ liệu hai chiều nếu cần rolling/rollback.

**Mục tiêu cuối cùng không phải chỉ là “chạy được Hibernate mới”, mà là “đọc, ghi, truy vấn và bảo vệ đúng cùng một hợp đồng dữ liệu trên phiên bản mới”.**

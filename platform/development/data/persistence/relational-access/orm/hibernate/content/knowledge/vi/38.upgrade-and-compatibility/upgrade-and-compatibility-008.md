# Đánh giá cấu hình cũ bị đổi nghĩa, ngừng hỗ trợ hoặc thay mặc định

Một ứng dụng Hibernate có thể nâng version thành công, compile không lỗi và vẫn chạy sai vì **cấu hình cũ không còn mang cùng ý nghĩa**. Có property đã bị thay tên, property chỉ còn được chấp nhận để tương thích nhưng không còn tác dụng, API bị xóa, default thay đổi, hoặc cùng một giá trị cấu hình được diễn giải khác sau khi nâng Hibernate, Jakarta Persistence, Spring Boot, JDBC driver hay database.

Ví dụ, một cấu hình từng ép Hibernate dùng một Dialect cụ thể có thể trở nên dư thừa khi Hibernate mới tự nhận diện database; một mapping type cũ có thể không còn tương thích với type system mới; một query từng chấp nhận cú pháp lỏng có thể bị parser mới từ chối; một tên property vẫn nằm trong `application.yml` nhưng không còn được đọc do namespace hoặc framework version thay đổi.

Vì vậy, nâng cấp không nên chỉ là tìm và thay các property có tên cũ. Cần **đánh giá từng cấu hình theo hành vi quan sát được**:

1. Cấu hình đó đang được đọc bởi thành phần nào?
2. Giá trị cũ có còn được hỗ trợ ở version đích không?
3. Ý nghĩa hoặc default có thay đổi không?
4. Nếu bỏ cấu hình, hành vi mới là gì?
5. Hành vi đó có phù hợp với yêu cầu ứng dụng không?
6. Có test chứng minh trước và sau nâng cấp không?
7. Có thể phát hiện lỗi và rollback an toàn không?

Bài học trình bày phương pháp kiểm kê cấu hình Hibernate/JPA, phân loại cấu hình còn hiệu lực, deprecated, removed, ignored hoặc đổi default; các vùng thường bị ảnh hưởng khi chuyển Hibernate 5 sang 6/7; cách xử lý `javax` sang `jakarta`, Dialect, type system, identifier generation, schema generation, query semantics, flush, batching, cache, transaction, multi-tenancy, Envers và logging; cuối cùng là quy trình kiểm chứng và triển khai nâng cấp.

---

## 1. Phân biệt đổi tên, deprecated, removed, ignored và đổi default

Năm trạng thái này có hậu quả khác nhau:

| Trạng thái | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| Renamed | Cấu hình có tên mới | Đổi tên, xác nhận giá trị và semantics |
| Deprecated | Vẫn có thể chạy nhưng không còn được khuyến nghị | Lập kế hoạch thay thế; không mặc định sẽ tồn tại mãi |
| Removed | API/property không còn trong version đích | Thay bằng API/cơ chế được hỗ trợ |
| Ignored/unknown | Runtime không tiêu thụ cấu hình hoặc framework không truyền xuống | Tìm nguồn cấu hình đúng và kiểm tra startup |
| Default changed | Không khai báo vẫn chạy, nhưng hành vi mặc định khác | Quyết định giữ default mới hay khai báo tường minh |

Một property không báo lỗi khi startup **không chứng minh nó còn hiệu lực**. Một số framework bỏ qua property không nhận diện; một số thư viện giữ alias tương thích; một số cấu hình chỉ được đọc khi một feature cụ thể khởi chạy.

### 1.1. Một giá trị vẫn tồn tại chưa chắc còn đúng nghĩa

Giả sử file có:

```properties
hibernate.jdbc.batch_size=50
hibernate.order_inserts=true
```

Các key có thể vẫn hợp lệ, nhưng hiệu quả thực tế còn phụ thuộc:
- ID generator có cho phép batching không.
- JDBC driver hỗ trợ batching ra sao.
- Transaction boundaries.
- Entity insert ordering và FK dependencies.
- Dialect/DBMS behavior.
- Batch failure handling.

Không thể chỉ thấy property trong file rồi kết luận ứng dụng đang batch 50 inserts.

### 1.2. Default mới có thể làm thay đổi ứng dụng dù không sửa file

Nếu trước đây ứng dụng không khai báo một property, nó dùng default của version cũ. Sau khi nâng version, cùng file cấu hình có thể dùng default mới. Đây là một thay đổi cấu hình thực sự dù Git diff không có dòng nào.

Vì thế, cần so sánh **effective configuration** và hành vi runtime, không chỉ so sánh text files.

## 2. Phân biệt cấu hình Hibernate, JPA, Spring Boot và database

Một ứng dụng Spring Boot thường có nhiều lớp property:

```text
application.yml
    |
    v
Spring Boot configuration binding
    |
    +--> spring.jpa.*
    |       |
    |       +--> Hibernate properties
    |
    +--> spring.datasource.*
    |       |
    |       +--> DataSource / JDBC pool
    |
    +--> spring.flyway.* / spring.liquibase.*
    |
    v
Hibernate bootstrap
    |
    +--> jakarta.persistence.*
    +--> hibernate.*
    +--> Dialect / JDBC driver
```

Các namespace không thể thay thế nhau tùy ý.

Ví dụ:

```yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
    properties:
      hibernate:
        format_sql: true
        jdbc:
          batch_size: 25
```

Trong Spring Boot:
- `spring.jpa.hibernate.ddl-auto` là property Spring Boot dùng để cấu hình schema action.
- `spring.jpa.properties.hibernate.*` truyền property xuống Hibernate.
- `spring.datasource.*` cấu hình datasource/pool, không phải Hibernate.
- `spring.flyway.*` cấu hình Flyway, không phải schema generator của Hibernate.

Nếu đặt:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        ddl-auto: validate
```

thì đó là một key Hibernate khác với `spring.jpa.hibernate.ddl-auto`; không nên tự giả định Hibernate có property `hibernate.ddl-auto` tương ứng. Kiểm tra tên setting theo đúng component tiêu thụ nó.

### 2.1. JPA standard property và Hibernate-specific property

Ví dụ:

```properties
jakarta.persistence.schema-generation.database.action=validate
```

thuộc namespace Jakarta Persistence schema generation.

Còn:

```properties
hibernate.hbm2ddl.auto=validate
```

là property Hibernate-specific được dùng trong các cấu hình Hibernate truyền thống.

Spring Boot còn có abstraction riêng:

```properties
spring.jpa.hibernate.ddl-auto=validate
```

Khi nâng cấp, hãy xác định property nào thực sự được framework truyền xuống, property nào được chuẩn hóa bởi JPA và property nào là extension của Hibernate.

## 3. Bắt đầu bằng kiểm kê toàn bộ cấu hình

Không chỉ tìm `hibernate.*` trong `application.yml`. Cấu hình có thể nằm trong:

- `application-*.yml` và `.properties`.
- Environment variables và Kubernetes ConfigMaps/Secrets.
- JVM system properties.
- Command-line arguments.
- Spring profiles.
- `persistence.xml`.
- `hibernate.cfg.xml`.
- `META-INF/orm.xml`.
- Java bootstrap code và `Map<String, Object>`.
- Custom `HibernatePropertiesCustomizer`.
- `LocalContainerEntityManagerFactoryBean`.
- Test configuration.
- Build dependency constraints/BOM.
- Database migration scripts.
- Runtime flags của connection pool/JDBC driver.

Một kiểm kê nên ghi cả nguồn và giá trị hiệu lực:

| Field | Ví dụ |
| --- | --- |
| Property key | `hibernate.jdbc.batch_size` |
| Giá trị | `25` |
| Nguồn | `application-prod.yml` |
| Thành phần tiêu thụ | Hibernate ORM |
| Version nguồn | Hibernate 5.6 |
| Version đích | Hibernate 6.6 |
| Trạng thái | Còn hỗ trợ / deprecated / removed / đổi default |
| Hành vi cần giữ | Batch DML trong transaction |
| Bằng chứng | Startup log, SQL/JDBC metric, integration test |
| Quyết định | Giữ / thay / bỏ / cấu hình rõ |
| Owner | Team/service phụ trách |

### 3.1. Tìm property bằng repository search

Có thể dùng các truy vấn tìm kiếm trong quá trình nâng cấp:

```shell
rg -n -i "hibernate\.|javax\.persistence|jakarta\.persistence" .
rg -n "hibernate\.dialect|hbm2ddl|generator_mappings" .
rg -n "hibernate\.cache|hibernate\.jdbc|hibernate\.query" .
rg -n "@Type|UserType|BasicType|Dialect|Integrator" .
```

Đây là cách tìm điểm xuất hiện, không phải bằng chứng đầy đủ. Property có thể được tạo động từ environment variables hoặc Java code.

### 3.2. Tìm cả API cũ trong source

Các property đã đổi có thể chỉ là một phần của vấn đề. Hãy tìm:
- `javax.persistence.*`.
- `org.hibernate.Criteria`.
- Hibernate-specific query APIs cũ.
- `TypeDef`, `@Type` và custom `UserType`.
- Dialect class cũ.
- Generator classes cũ.
- SPI interfaces đã thay đổi.
- Integrator/event listener implementations.
- Custom SQL functions và type registrations.

Không xóa một API chỉ vì IDE gạch deprecated; trước tiên phải hiểu nơi gọi và contract hiện tại.

## 4. Pin version trước khi đánh giá cấu hình

Một cấu hình chỉ có thể được đánh giá khi biết chính xác:
- Hibernate ORM version.
- Hibernate Envers version.
- Jakarta Persistence API version.
- Spring Boot/Spring Framework/Spring Data version.
- JDBC driver version.
- Database server product/version.
- Connection pool version.
- Migration tool version.
- Java runtime version.

Không có một khái niệm “Hibernate 6” duy nhất. Minor versions có thể bổ sung setting, thay đổi behavior hoặc sửa bug. Một property có thể hợp lệ ở một minor version nhưng chưa có ở version khác.

### 4.1. Giữ ORM và Envers đồng bộ

Nếu dùng Envers, dependency `hibernate-envers` cần cùng dòng version tương thích với `hibernate-core`. Quản lý bằng BOM/dependency management thay vì nâng một module độc lập.

### 4.2. Phân biệt thay đổi Hibernate với thay đổi Spring Boot

Một lần nâng Spring Boot major có thể đồng thời thay:
- Hibernate version.
- Jakarta Persistence API.
- Spring Data JPA.
- Default datasource/connection pool.
- Logging stack.
- Transaction manager integration.

Nếu behavior thay đổi, không tự quy toàn bộ nguyên nhân cho Hibernate. Hãy cô lập từng lớp bằng dependency graph và cấu hình hiệu lực.

## 5. Hibernate 5 sang Hibernate 6: namespace `javax` thành `jakarta`

Đây là thay đổi lớn về binary/package compatibility.

Code cũ:

```java
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.ManyToOne;
```

Code mới:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.ManyToOne;
```

Không thể trộn annotation `javax.persistence` và `jakarta.persistence` trên cùng một persistence model rồi mong Hibernate 6 nhận diện như nhau.

### 5.1. Dependency cũng phải chuyển namespace

Các thư viện tích hợp JPA, validation, transaction và persistence annotations cần tương thích Jakarta. Một dependency cũ vẫn compile trong project nhưng không có nghĩa runtime Hibernate 6 nhận annotation cũ.

Kiểm tra:
- Entity annotations.
- Attribute converters.
- Lifecycle listeners.
- Persistence provider bootstrap.
- `persistence.xml`.
- Validation integration.
- Test fixtures và mocks.
- Các thư viện third-party có nhận `jakarta.persistence` không.

### 5.2. XML descriptors và service providers

Nếu dùng `persistence.xml`, `orm.xml` hoặc custom provider bootstrap, kiểm tra namespace/schema version và provider class. Đừng chỉ thay imports Java mà bỏ quên XML metadata.

## 6. Hibernate 6: query và Criteria API cũ cần được chuyển đổi

Hibernate 5 có legacy Criteria API:

```java
Criteria criteria =
    session.createCriteria(PurchaseOrder.class);
```

Legacy `org.hibernate.Criteria` API đã bị loại khỏi Hibernate 6. Với query động, dùng JPA Criteria API:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<PurchaseOrder> query =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> root =
    query.from(PurchaseOrder.class);

query.select(root)
    .where(cb.equal(root.get("status"), OrderStatus.PAID));

List<PurchaseOrder> result =
    em.createQuery(query).getResultList();
```

Hoặc dùng HQL/JPQL, repository queries và query builder phù hợp.

### 6.1. Không chuyển máy móc mọi Criteria cũ thành chuỗi JPQL

Legacy Criteria có thể dùng:
- Projections.
- Result transformers.
- Aliases.
- Detached criteria.
- Restrictions.
- Custom SQL projections.

Mỗi use case cần được ánh xạ sang JPA Criteria, HQL, DTO projection hoặc native SQL có kiểm soát. Test result shape, null handling, joins, ordering và pagination.

### 6.2. Result transformers cũ

Các API transformer legacy đã thay đổi qua các Hibernate versions. Nếu code dùng `setResultTransformer`, kiểm tra API thay thế như tuple/list transformers trong version đích hoặc chuyển sang DTO constructor projections.

Đừng chỉ suppress deprecation warning rồi để API cũ trở thành blocker khi nâng major tiếp theo.

## 7. Hibernate 6: HQL parser và query semantics chặt chẽ hơn

Hibernate 6 có query engine/HQL implementation mới so với các thế hệ trước. Một số query trước đây được chấp nhận nhờ parser hoặc behavior permissive có thể cần viết lại rõ ràng.

Những vùng cần kiểm tra:
- Implicit joins.
- Path expressions.
- Type compatibility trong comparisons.
- Enum/string/numeric literal handling.
- Group by và aggregate expressions.
- Subqueries.
- Collection functions.
- Native query result mapping.
- Pagination và fetch joins.
- Parameter binding.
- Function registration.

Ví dụ query mơ hồ:

```java
select o
from PurchaseOrder o
where o.customer = :customerId
```

Nếu `customer` là association, parameter nên có đúng entity type hoặc query nên so sánh identifier một cách tường minh:

```java
where o.customer.id = :customerId
```

Không dựa vào implicit conversion của provider cũ.

### 7.1. Test query result, không chỉ test query parse

Một query có thể chạy nhưng trả số rows khác do join cardinality, null semantics hoặc duplicate elimination. Mỗi query quan trọng cần fixtures có:
- Không có association.
- Một association.
- Nhiều child rows.
- Null values.
- Duplicate-looking data.
- Tenant boundaries.
- Sorting và paging.

## 8. `DISTINCT` và fetch join: xem lại kỳ vọng giữa các version

Trong Hibernate 6, entity results từ fetch joins được khử trùng lặp theo entity identity trong nhiều trường hợp; code cũ thường thêm `DISTINCT` để loại duplicate root references.

Điều này không có nghĩa `DISTINCT` luôn vô dụng:
- SQL `DISTINCT` vẫn có semantics ở query/database layer.
- Projection/scalar results có thể khác entity results.
- Query shape và provider version vẫn quan trọng.
- Không nên dùng DISTINCT như một biện pháp chữa row multiplication khi phân trang collection.

Khi nâng cấp, hãy kiểm tra:
- Số root entities trả về.
- Số SQL rows.
- Collection completeness.
- Count query.
- Pagination với collection fetch.
- Query plan và in-memory pagination warnings.

### 8.1. Phân trang collection fetch

Cấu hình guardrail có thể dùng ở các version hỗ trợ:

```properties
hibernate.query.fail_on_pagination_over_collection_fetch=true
```

Với Spring Boot:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        query:
          fail_on_pagination_over_collection_fetch: true
```

Setting này giúp phát hiện query kết hợp pagination và collection fetch có thể phải paginate trong memory. Kiểm tra tên property và behavior trên version đích.

## 9. Hibernate 6: type system và custom types

Hibernate 6 thay đổi đáng kể nội bộ type system. Code cũ có thể sử dụng:
- `BasicType`.
- `SqlTypeDescriptor`.
- `JavaTypeDescriptor`.
- `@Type(type = "...")
`.
- `@TypeDef`.
- Custom `UserType`.
- `TypeContributor`.

Các extension points có thể đã đổi signature hoặc cách đăng ký. Không nên copy custom type Hibernate 5 vào Hibernate 6 rồi chỉ sửa import cho compile.

### 9.1. Phân biệt Java type và JDBC type

Khi debug mapping, cần xác định:
- Java representation.
- JDBC type.
- SQL type được Dialect chọn.
- Converter có tham gia không.
- Column definition trong migration.
- Cách Envers ghi và đọc cùng type đó.

Ví dụ `UUID` có thể lưu native UUID, binary hoặc character representation tùy DBMS/configuration. Cùng Java type nhưng SQL representation không nhất thiết giống giữa hai Dialects.

### 9.2. `AttributeConverter` hay custom Hibernate type?

Nếu chỉ cần chuyển một Java value sang một basic database value, `AttributeConverter<X,Y>` theo Jakarta Persistence thường dễ portable hơn.

Nếu cần JDBC type-specific behavior, multi-column mapping hoặc database-specific operations, custom Hibernate type có thể cần thiết. Chọn abstraction theo yêu cầu, không theo thói quen cũ.

### 9.3. `@Type` API thay đổi

Các version Hibernate mới có API `@Type` khác với cú pháp cũ dựa trên tên type string. Mapping cũ như:

```java
@Type(type = "json")
private Map<String, Object> metadata;
```

không nên được coi là portable sang version mới. Tùy version/dialect, có thể dùng `@JdbcTypeCode(SqlTypes.JSON)` hoặc custom type phù hợp.

Test cả live persistence và Envers historical read.

## 10. `@TypeDef` và custom type registration

Nếu code cũ dùng `@TypeDef`/`@TypeDefs`, kiểm tra:
- Annotation còn tồn tại trong version đích không.
- Type registration được thực hiện ở đâu.
- `@Type` mới yêu cầu class hay annotation parameters nào.
- Custom type có hỗ trợ deep copy/mutability đúng không.
- Query parameter binding có tương thích không.
- Envers có thể serialize/restore type đó không.

Không thay mọi custom type bằng JSON chỉ để giảm code. Cần giữ schema, index/query semantics và data compatibility.

## 11. Dialect: cấu hình thủ công có thể đã dư thừa hoặc không còn phù hợp

Cấu hình cũ:

```properties
hibernate.dialect=org.hibernate.dialect.PostgreSQL10Dialect
```

Trong Hibernate hiện đại, Hibernate thường có thể suy ra Dialect từ JDBC metadata. Việc cấu hình class cụ thể có thể không cần thiết, và một số dialect class cũ đã được hợp nhất, deprecated hoặc chuyển module tùy version.

### 11.1. Không xóa `hibernate.dialect` một cách mù quáng

Trước khi bỏ:
- Xác nhận JDBC metadata được truy cập ở bootstrap.
- Xác nhận DB product/version nhận diện đúng.
- Kiểm tra custom dialect overrides.
- Kiểm tra test environment và production dùng cùng database family.
- Kiểm tra startup khi database proxy/driver trả metadata khác thường.

Nếu dùng custom Dialect hoặc database compatibility layer, có thể vẫn cần cấu hình cụ thể.

### 11.2. Một số dialect-specific classes có thể nằm trong module khác

Với một số database ít phổ biến hoặc legacy, dialect không còn nằm trong core artifact ở version mới và có thể cần `hibernate-community-dialects` hoặc module tương ứng.

Kiểm tra dependency và classpath thực tế; không đoán tên class mới từ tên class cũ.

### 11.3. Dialect không phải công tắc tương thích server

Ép một Dialect class không cài thêm feature vào database. Server version, JDBC driver và extension vẫn quyết định database thực thi được SQL hay không.

## 12. `hibernate.id.new_generator_mappings` và identifier migration

Hibernate 5 có setting lịch sử:

```properties
hibernate.id.new_generator_mappings=true
```

Setting này liên quan cách Hibernate sử dụng các identifier generators mới so với legacy mappings trong những thế hệ cũ. Ở các version hiện đại, không nên coi đây là công tắc còn có thể tùy ý bật/tắt để giữ nguyên mọi behavior cũ; cần kiểm tra version đích và migration guide.

### 12.1. Kiểm tra SEQUENCE allocation

Mapping:

```java
@SequenceGenerator(
    name = "orderSeq",
    sequenceName = "purchase_order_seq",
    allocationSize = 50
)
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "orderSeq"
)
```

phải khớp với sequence và optimizer behavior của Hibernate/DBMS. Nếu legacy app dùng allocation size khác hoặc sequence increment không tương thích, nâng cấp có thể tạo warning, lỗi hoặc hành vi cấp ID khác.

Test:
- Nhiều inserts.
- Restart application.
- Nhiều instances.
- Rollback và sequence gaps.
- IDs không trùng.
- Generator schema validation.
- Existing data có ID lớn hơn sequence hiện tại.

Không assert ID liên tục; hãy xác nhận uniqueness và không va chạm dữ liệu cũ.

### 12.2. `AUTO` không phải cam kết cùng một generator giữa mọi Dialect

`GenerationType.AUTO` cho provider quyền chọn chiến lược theo database/provider. Khi đổi DBMS hoặc Hibernate version, strategy được chọn có thể khác.

Nếu ứng dụng phụ thuộc behavior cụ thể về batching, ID availability hoặc schema, dùng strategy tường minh và test trên production DBMS.

## 13. Schema generation: `hbm2ddl.auto` và JPA schema-generation properties

Cấu hình Hibernate truyền thống:

```properties
hibernate.hbm2ddl.auto=validate
```

Các giá trị thường gặp gồm `none`, `validate`, `update`, `create`, `create-drop`. Spring Boot có property riêng:

```properties
spring.jpa.hibernate.ddl-auto=validate
```

Jakarta Persistence có nhóm properties schema-generation:

```properties
jakarta.persistence.schema-generation.database.action=none
```

Các property thuộc các abstraction khác nhau; đừng đặt đồng thời nhiều nguồn với giá trị mâu thuẫn rồi đoán cái nào thắng.

### 13.1. Default phụ thuộc environment và framework

Spring Boot có thể chọn default DDL action khác nhau tùy embedded database, datasource và framework version. Vì vậy, bỏ `ddl-auto` khi nâng Spring Boot có thể thay đổi behavior dù Hibernate property không đổi.

Đối với production schema do Flyway/Liquibase quản lý, thường khai báo rõ `validate` hoặc policy phù hợp thay vì phụ thuộc default.

### 13.2. `update` không phải migration engine

Hibernate schema update không thay thế migrations có version:
- Không diễn đạt đầy đủ data backfill.
- Không quản lý rollout tương thích nhiều app versions.
- Không cung cấp rollback có kiểm soát như migration plan.
- Có thể không xử lý mọi DDL/constraint/index theo ý định.
- Không tự đảm bảo audit history được migrate đúng.

## 14. Naming strategies và schema naming drift

Hibernate có implicit và physical naming strategies. Spring Boot cũng có thể cung cấp naming defaults.

Một field:

```java
private String createdAt;
```

có thể được map thành `created_at` theo naming strategy hiện tại. Khi đổi Spring Boot/Hibernate hoặc custom naming strategy, tên bảng/cột có thể thay đổi.

Kiểm tra:
- `hibernate.implicit_naming_strategy`.
- `hibernate.physical_naming_strategy`.
- Spring Boot naming strategy defaults.
- `@Table`, `@Column`, `@JoinColumn`.
- Audit table naming.
- Sequence/table generator names.
- Quoted identifiers.
- Schema/catalog.

### 14.1. Không đổi naming strategy mà thiếu migration

Nếu version mới sinh tên cột khác nhưng migration giữ tên cũ, Hibernate có thể báo thiếu column hoặc tạo query sai. Với Envers, naming drift còn ảnh hưởng `_AUD` tables và join tables.

Nếu cần giữ schema hiện tại, có thể cấu hình strategy tường minh hoặc khai báo column/table names cụ thể. Chọn một contract và test bằng schema do migrations tạo.

## 15. SQL types và default mapping có thể đổi

Những loại cần kiểm tra khi nâng:
- Boolean.
- UUID.
- Enum.
- JSON/JSONB.
- ARRAY.
- `BigDecimal`.
- `Instant`, `LocalDateTime`, `OffsetDateTime`.
- LOB/BLOB/CLOB.
- Nationalized strings.
- Binary data.
- Custom database types.

Hibernate 6 type system và Dialect có thể chọn SQL types khác so với version cũ. Điều đó ảnh hưởng DDL validation, bind parameters, indexes, query operators và Envers audit columns.

### 15.1. Enum mapping

`@Enumerated(EnumType.ORDINAL)` lưu số thứ tự enum; thêm/reorder constants có thể đổi ý nghĩa dữ liệu. `STRING` lưu tên enum; rename constant có thể làm dữ liệu cũ không parse được.

Khi nâng version, đừng tự đổi ORDINAL thành STRING nếu không có data migration. Nếu domain cần code ổn định, cân nhắc `AttributeConverter` map enum sang value nghiệp vụ tường minh.

### 15.2. Decimal precision/scale

So sánh `precision`/`scale` của live và audit columns. Một Dialect có thể chọn numeric type hoặc precision limits khác nhau. Test giá trị biên và round-trip historical data.

### 15.3. Timestamp/time zone

Xác định semantics của từng Java temporal type. Không đổi `LocalDateTime` thành `Instant` chỉ vì database có `TIMESTAMP WITH TIME ZONE`; đó là thay đổi meaning, cần migration dữ liệu và API.

## 16. JDBC timezone và temporal behavior

Cấu hình:

```properties
hibernate.jdbc.time_zone=UTC
```

có thể ảnh hưởng cách Hibernate bind/extract JDBC timestamp values trong các mappings phù hợp.

Khi nâng version:
- Xác nhận property vẫn được hỗ trợ.
- Kiểm tra JDBC driver.
- Kiểm tra column type.
- Kiểm tra JVM default timezone.
- Kiểm tra DB session timezone.
- Test DST boundaries và offsets.
- So sánh instant thay vì chuỗi hiển thị nếu domain là absolute time.

Đừng dùng `hibernate.jdbc.time_zone` để che một schema lưu local wall-clock time nhưng ứng dụng lại hiểu đó là UTC.

## 17. Query plan và default query behavior

Một số query settings có thể đã đổi hoặc được bổ sung qua version:
- IN-clause parameter padding.
- Query plan cache sizing.
- Collection fetch pagination behavior.
- Batch fetching.
- Query timeout handling.
- SQL comments.
- HQL parser strictness.
- Null precedence.
- Function registration.

Không sao chép một file `hibernate.properties` cũ sang version mới rồi giả định mọi key có tác dụng. Xác minh bằng query behavior, logs và API docs của version đích.

### 17.1. `hibernate.query.in_clause_parameter_padding`

Nếu setting này được dùng, nó có thể thay đổi số placeholder JDBC bằng cách pad danh sách IN nhằm cải thiện statement plan/cache reuse trên một số DBMS. Nó không thay đổi logical membership mong muốn, nhưng có thể thay SQL shape và parameter count.

Test:
- Danh sách rỗng.
- Một phần tử.
- Số phần tử gần ngưỡng pad.
- Số phần tử lớn.
- DBMS parameter limits.
- Query plan/cache metrics.

Không bật chỉ vì một benchmark khác DBMS cho thấy có lợi.

## 18. Flush mode và auto-flush

Các flush modes JPA/Hibernate ảnh hưởng thời điểm SQL được phát:
- `AUTO`.
- `COMMIT`.
- Hibernate-specific `ALWAYS`.
- Hibernate-specific `MANUAL`.

Nâng Hibernate hoặc thay query engine có thể làm một số query trigger flush khác trước. Hãy test:
- Persist rồi query cùng entity type.
- Persist rồi query entity type khác.
- Native query.
- Bulk update/delete.
- `saveAndFlush`.
- Transaction commit/rollback.

Không dùng `MANUAL` như cách giảm SQL logs nếu code không quản lý flush rõ ràng. Một thay đổi flush timing có thể làm lỗi constraint xuất hiện ở method khác với trước.

## 19. JDBC batching và defaults

Cấu hình thường gặp:

```properties
hibernate.jdbc.batch_size=25
hibernate.order_inserts=true
hibernate.order_updates=true
```

Những settings này cần được đánh giá theo:
- Version Hibernate.
- JDBC driver batch support.
- ID generation strategy.
- Versioned entities.
- SQL shape.
- FK ordering.
- Transaction size.
- DBMS parameter/packet limits.

### 19.1. Không suy batching từ số dòng SQL log

SQL log có thể ghi nhiều statements dù JDBC driver gom thành batch. Dùng batch logger/metrics hoặc datasource instrumentation để xác nhận.

### 19.2. IDENTITY và batching

Với identity-generated IDs, Hibernate thường cần INSERT sớm để lấy generated keys; khả năng batch entity inserts có thể bị hạn chế so với sequence strategy. Đừng nâng version rồi kỳ vọng `batch_size` tự tăng throughput nếu generator không phù hợp.

### 19.3. Batch ordering có thể đổi thứ tự SQL

Bật `order_inserts`/`order_updates` có thể sắp xếp các actions để batching hiệu quả hơn. Nếu application phụ thuộc vào thứ tự side effects ở database triggers, hãy xem xét lại giả định. Referential integrity phải được bảo vệ bằng mapping/constraints, không bằng thứ tự Java setter.

## 20. Connection handling và transaction defaults

Hibernate có các connection handling modes và integration với JTA/resource-local transaction. Spring Boot có thể quản lý DataSource và transaction manager thay cho Hibernate tự tạo connection provider.

Khi nâng:
- Kiểm tra ai sở hữu DataSource.
- Kiểm tra auto-commit.
- Kiểm tra isolation.
- Kiểm tra connection release timing.
- Kiểm tra JTA vs local transaction.
- Kiểm tra connection pool defaults.
- Kiểm tra transaction timeout.
- Kiểm tra multi-datasource routing.

Không thay connection handling property chỉ vì thấy nó trong file cũ. Trước tiên xác định property đó còn được hỗ trợ và transaction manager nào thực sự quản lý connection.

### 20.1. Không gọi JDBC connection trực tiếp ngoài transaction-aware path

Một `DataSource.getConnection()` độc lập có thể không tham gia cùng transaction với EntityManager. Khi kết hợp Hibernate và JDBC, dùng Spring transaction-aware APIs hoặc resource binding đúng cấu hình.

Test bằng cách ghi qua ORM, ghi qua JDBC, rồi rollback một transaction để chứng minh hai writes thực sự atomic khi đó là yêu cầu.

## 21. Second-level cache và query cache

Các cấu hình:
- `hibernate.cache.use_second_level_cache`.
- `hibernate.cache.use_query_cache`.
- Region factory/provider.
- Cache concurrency strategy.
- Query cache layout.
- Minimal puts.
- Region prefixes.

cần được kiểm tra cùng cache provider và Hibernate version.

Đừng suy từ việc cache provider dependency vẫn có trong classpath rằng integration còn hoạt động. SPI/region factory có thể thay đổi; cache provider phải tương thích version mới.

### 21.1. Default cache có thể vẫn disabled

Second-level cache và query cache thường cần cấu hình rõ; không giả định nâng version tự bật cache hoặc tự tắt cache. Kiểm tra effective settings và runtime statistics.

### 21.2. Cache invalidation sau native SQL

Native/JDBC writes có thể không đồng bộ cache như managed entity updates. Nếu code dựa vào cache consistency, test:
- ORM update.
- Bulk HQL update.
- Native SQL.
- External writer.
- Multi-node invalidation.
- Query cache results.

Không chỉ so sánh response trong cùng Persistence Context.

## 22. Bytecode enhancement và lazy loading

Hibernate bytecode enhancement có thể phục vụ:
- Lazy attribute loading.
- Dirty tracking.
- Association management.
- Inline dirty checking.

Build plugin và enhancement options thay đổi qua Hibernate major versions. Một cấu hình Maven/Gradle cũ có thể không còn đúng plugin goal/extension hoặc enhancer option.

Kiểm tra:
- Build plugin version.
- Entity class enhancement thực sự được áp dụng.
- Runtime classpath.
- Lazy basic fields.
- Dirty tracking correctness.
- Tests chạy trên class đã enhance.
- Dev/test/prod build có cùng enhancement pipeline không.

Không bật enhancement option mà không hiểu entity instrumentation và test behavior. Một test IDE chạy từ source có thể khác artifact đã được enhancer xử lý.

## 23. Logging categories thay đổi qua Hibernate versions

Cấu hình cũ có thể dùng logger cho binder/extractor của Hibernate 5. Hibernate 6/7 có logging categories mới cho SQL và JDBC bind/extract.

Ví dụ thường gặp trên Hibernate 6/7:

```properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
logging.level.org.hibernate.orm.jdbc.extract=TRACE
```

Kiểm tra version đích và logging backend. Nếu không thấy bind values, có thể category cũ không còn đúng hoặc log level/filter không cho phép.

### 23.1. Logging không phải audit

Bind logs có thể chứa PII, credentials hoặc dữ liệu tài chính. Không bật TRACE lâu dài chỉ để kiểm tra migration. Dùng môi trường test, redaction, access control và thời gian bật giới hạn.

## 24. Envers: kiểm tra setting và schema cùng lúc

Nếu dùng Envers, cấu hình có thể gồm:
- `audit_table_suffix`/prefix.
- `revision_field_name`.
- `revision_type_field_name`.
- `revision_on_collection_change`.
- `store_data_at_delete`.
- `audit_strategy`.
- `withModifiedFlag`.
- Custom revision entity/listener.

Nâng Hibernate/Envers cần:
1. Đồng bộ core và Envers versions.
2. Kiểm tra property keys còn hiệu lực.
3. Kiểm tra revision table/cột.
4. Kiểm tra mọi `_AUD`/collection audit tables.
5. Kiểm tra historical queries.
6. Kiểm tra rollback và bulk DML.
7. Kiểm tra target audit mode và behavior version-specific.

### 24.1. DefaultAuditStrategy và ValidityAuditStrategy

Nếu đổi strategy, cần migration/backfill audit schema. Không chỉ đổi property:
- Validity strategy thường cần `REVEND`.
- Có thể cần revision-end timestamp column.
- Historical queries và indexes khác.
- Write path cập nhật audit row trước đó.
- Concurrency/locking cần kiểm thử.

### 24.2. Revision entity custom

Nếu custom revision entity có actor/tenant/request ID, hãy kiểm tra:
- Generator và revision ID type.
- Column lengths/types.
- Listener hoạt động trong background jobs.
- Thread/request context không null.
- Migration tương thích audit tables.
- PII retention trong revision metadata.

## 25. Soft delete là tính năng theo version

Hibernate cung cấp `@SoftDelete` từ các phiên bản hiện đại (bắt đầu ở dòng 6.4). Một ứng dụng cũ có thể dùng:
- `@SQLDelete`.
- `@Where` hoặc `@SQLRestriction`.
- `@Filter`.
- Cờ `deleted` tự quản lý.

Khi nâng lên version hỗ trợ `@SoftDelete`, không nên đổi annotation chỉ vì có API mới. Đánh giá:
- Query visibility.
- To-one associations.
- Collection tables.
- Restore path.
- Native SQL.
- Envers integration.
- Cache invalidation.
- Missing target.
- Unique indexes và FK.

### 25.1. Không trộn hai cơ chế delete cho cùng entity

Nếu `@SoftDelete` đã quản lý delete indicator, không đồng thời dùng custom `@SQLDelete`/static restriction cùng cột mà chưa xác định rõ semantics. Một entity có thể bị double predicate hoặc SQL update mâu thuẫn.

## 26. Multi-tenancy SPI và tenant resolution

Hibernate có các cách multi-tenancy:
- Database per tenant.
- Schema per tenant.
- Shared tables với tenant discriminator.

Các SPI như `MultiTenantConnectionProvider` và `CurrentTenantIdentifierResolver` có thể thay đổi qua Hibernate major versions. Kiểm tra:
- Method signatures.
- Tenant identifier lifecycle.
- Connection acquisition/release.
- Schema switching.
- Tenant-specific caches.
- Envers revision/audit isolation.
- Native SQL tenant predicates.
- Background jobs.

### 26.1. Test không chỉ tenant resolution

Tạo hai tenants có cùng logical IDs rồi kiểm tra:
- Load entity.
- Insert/update.
- Association joins.
- Composite FK.
- AuditReader history.
- Cache keys.
- Schema routing.
- Transaction rollback.
- Native queries.

Một resolver trả tenant ID đúng ở startup không chứng minh mọi query/audit path được cô lập.

## 27. Custom Dialect, SQL functions và Integrator

Code cũ có thể extend Dialect để:
- Đăng ký SQL functions.
- Định nghĩa column types.
- Chỉnh identity/sequence support.
- Tùy chỉnh limit/offset.
- Đăng ký JDBC types.

Hibernate 6 thay đổi nhiều điểm trong type system và function registration. Một custom Dialect cũ có thể không compile hoặc override method không còn đúng.

Ưu tiên extension point được tài liệu version đích hỗ trợ:
- Function contributor/registration APIs phù hợp.
- Type contributor hoặc custom JDBC mapping.
- Integrator/service registration theo SPI mới.
- `MetadataBuilderContributor`/bootstrap customization nếu còn phù hợp version.

Không copy override của Dialect cũ vào version mới chỉ để compile; kiểm tra generated SQL và DDL trên database thật.

## 28. Custom SQL, `@SQLInsert`, `@SQLUpdate`, `@SQLDelete`

Custom SQL annotation phụ thuộc:
- Số và thứ tự bind parameters.
- Identifier columns.
- Version columns.
- Generated columns.
- Result check style.
- Dialect syntax.
- Table/secondary table mappings.

Một SQL custom vẫn compile vì annotation là string, nhưng runtime có thể lỗi bind index hoặc update count.

Test:
1. Insert entity.
2. Update entity.
3. Optimistic locking conflict.
4. Delete/soft delete.
5. Composite ID.
6. Secondary table.
7. Envers audit row.
8. Rollback.
9. DBMS-specific syntax.

Không coi `@SQLDelete` cũ còn đúng chỉ vì annotation vẫn tồn tại.

## 29. Stored procedures, functions và native query result mappings

Nâng cấp query engine/JDBC driver có thể ảnh hưởng:
- Procedure parameter registration.
- REF_CURSOR support.
- Named parameters trong native SQL.
- Scalar result type inference.
- Entity result mapping.
- Tuple/constructor mappings.
- SQL function registration.
- Callable statement behavior.

Nếu application dùng stored procedures, tạo integration tests với đúng DBMS và driver. Một H2 stored procedure substitute không chứng minh behavior production.

## 30. Property cũ bị bỏ qua: làm sao phát hiện?

Các dấu hiệu:
- Startup log có warning về unrecognized/deprecated setting.
- Effective configuration không chứa key.
- SQL/DDL behavior không đổi dù thay giá trị.
- API getter hoặc metadata cho thấy default vẫn được dùng.
- Runtime metrics không phản ánh tính năng kỳ vọng.
- Test hành vi không phân biệt được hai giá trị.

Cách xác minh:
1. Tìm property trong documentation/Javadocs của version đích.
2. Tìm migration guide giữa source và target versions.
3. Kiểm tra namespace/precedence.
4. Bật logging startup phù hợp.
5. Tạo một test thay giá trị cấu hình theo hai hướng đối lập.
6. Quan sát hành vi runtime/SQL/metadata.
7. Ghi quyết định: còn hiệu lực, ignored hay không thể quan sát.

Không kết luận property bị ignored chỉ vì không có log warning; nhiều setting không log khi unknown.

## 31. Effective configuration và precedence

Một giá trị cuối cùng có thể đến từ:
- Default thư viện.
- `persistence.xml`.
- `hibernate.cfg.xml`.
- Spring Boot auto-configuration.
- `application.yml`.
- Profile-specific file.
- Environment variable.
- JVM `-D`.
- Command-line argument.
- Programmatic overrides.

Khi nâng cấp, tạo báo cáo effective configuration cho từng môi trường (dev/test/staging/prod) và che secrets.

Không ghi ra log:
- Password.
- JDBC URL chứa credentials.
- Tokens.
- Encryption keys.
- Sensitive connection properties.

### 31.1. Hai property cùng tên nhưng khác prefix

Ví dụ:

```properties
spring.jpa.hibernate.ddl-auto=validate
spring.jpa.properties.hibernate.hbm2ddl.auto=update
```

Có thể tạo xung đột giữa Spring Boot schema action và Hibernate property. Không để hai nguồn điều khiển cùng feature mà không hiểu precedence. Chọn một cấu hình có chủ sở hữu rõ.

## 32. Cấu hình đã deprecated: lập kế hoạch thay thế

Một property/API deprecated không nhất thiết cần xóa ngay trong cùng commit nâng cấp, nhưng cần:
- Xác định version giới thiệu deprecation.
- Xác định replacement.
- Kiểm tra replacement có cùng semantics không.
- Tạo test bảo vệ behavior.
- Thay code/config.
- Bỏ legacy setting.
- Kiểm tra warning biến mất.
- Đặt thời hạn loại bỏ trước major upgrade tiếp theo.

Không suppress warning toàn cục. Một warning có thể chỉ ra API sẽ bị xóa hoặc behavior đang chuyển sang mặc định mới.

## 33. Cấu hình đã removed: chuyển đổi theo capability

Khi một setting bị removed:
1. Không giữ property cũ với hy vọng runtime bỏ qua an toàn.
2. Tìm replacement chính thức.
3. Nếu replacement không có, xem lại feature design.
4. Nếu cần giữ behavior, implement qua supported extension point.
5. Viết test chứng minh behavior tương đương.
6. Đánh giá tác động performance/security.
7. Cập nhật runbook và configuration docs.

Ví dụ, nếu legacy Criteria API bị removed, không tìm property để bật lại API đó. Chuyển query sang JPA Criteria/HQL/DTO/native query phù hợp.

## 34. Default changed: vì sao phải khai báo tường minh có chọn lọc?

Một số default quan trọng thường cần xem xét:
- Schema action của Spring Boot theo môi trường.
- Naming strategy.
- Identifier generator behavior.
- Query parser/strictness.
- Fetch behavior.
- Batch/fetch sizes.
- Cache enablement.
- Connection handling.
- SQL logging.
- JDBC timezone.
- Envers audit strategy/settings.

Không nên khai báo mọi property để “khóa chặt” Hibernate; điều đó tạo configuration debt và có thể chặn cải tiến an toàn trong version mới.

Chỉ pin tường minh những default ảnh hưởng contract nghiệp vụ, schema, consistency, security hoặc performance có ý nghĩa. Với các tối ưu nội bộ không phải contract, có thể chấp nhận default mới sau khi đo.

## 35. Bảng đánh giá cấu hình thường gặp

| Cấu hình/API cũ | Vùng cần kiểm tra khi nâng | Câu hỏi quyết định |
| --- | --- | --- |
| `hibernate.dialect` | Dialect auto-detection/class changes | Có custom Dialect hoặc metadata bất thường không? |
| `hibernate.id.new_generator_mappings` | Identifier generators | Version đích còn hỗ trợ không; ID allocation có đổi không? |
| `hibernate.hbm2ddl.auto` | Schema generation | Có bị Spring Boot/JPA property khác override không? |
| Legacy `javax.persistence.*` | Jakarta migration | Tất cả dependencies đã chuyển namespace chưa? |
| `org.hibernate.Criteria` | Query API | Đã chuyển JPA Criteria/HQL chưa? |
| `@Type(type="...")` | Type system | Custom type có API mới và audit support không? |
| `@TypeDef` | Type registration | Registration point còn hợp lệ không? |
| Custom `Dialect` overrides | Dialect SPI | Method/type/function API còn đúng không? |
| `@Where` | Static restriction | Có thay bằng `@SQLRestriction`/`@SoftDelete` phù hợp không? |
| `@SQLDelete` | Custom delete SQL | Parameter/version semantics còn đúng không? |
| Legacy logging categories | Logging | Bind/extract logger category còn đúng không? |
| Legacy cache provider | L2 cache SPI | RegionFactory/provider tương thích không? |
| `@Fetch`/`@BatchSize` | Fetching | SQL/query count có thay đổi không? |
| Envers strategy setting | Audit schema | Audit tables có columns/indexes tương ứng không? |
| `hibernate.jdbc.time_zone` | Temporal binding | Instant/offset semantics có giữ không? |
| `hibernate.jdbc.batch_size` | JDBC batching | Driver/generator có thực sự batch không? |
| `hibernate.order_inserts` | Action ordering | Có ảnh hưởng trigger/side-effect assumptions không? |
| `hibernate.query.*` | HQL/query engine | Parser, pagination và plan cache behavior có đổi không? |
| Connection handling settings | Transactions/pool | Spring/JTA có đang quản lý connection không? |
| Bytecode enhancement options | Build/runtime | Entity artifacts thực sự được enhance không? |

Bảng này là danh sách kiểm tra, không phải tuyên bố mọi property trong đó đã bị removed hoặc đổi default ở cùng một version. Trạng thái chính xác phải đối chiếu version nguồn và đích.

## 36. Lập compatibility matrix theo version

Một bảng version matrix giúp tránh nói chung chung “Hibernate mới”:

| Thành phần | Version nguồn | Version đích | Điều phải xác nhận |
| --- | --- | --- | --- |
| Java | Runtime hiện tại | Runtime mục tiêu | Bytecode/API compatibility |
| Spring Boot | Major/minor cũ | Major/minor mới | Auto-config và property binding |
| Hibernate ORM | Version cũ | Version mới | API, defaults, SQL behavior |
| Envers | Version cũ | Cùng dòng tương thích | Audit schema và revision queries |
| Jakarta Persistence | `javax`/Jakarta API cũ | Jakarta API mới | Namespace và spec behavior |
| JDBC driver | Driver cũ | Driver mới | Type/transaction/batching |
| DBMS | Server version cũ | Server version mới | Dialect capabilities |
| Migration tool | Flyway/Liquibase cũ | Version mới | DDL/transaction behavior |

Không nâng tất cả thành phần cùng lúc nếu không thể cô lập nguyên nhân regression. Nếu bắt buộc nâng đồng thời theo Spring Boot BOM, dùng test matrix và release checkpoints để xác định thay đổi.

## 37. So sánh hành vi trước và sau bằng golden tests

Chọn các use cases quan trọng:
- Persist entity với mỗi ID strategy.
- Update entity có `@Version`.
- Cascade persist/remove.
- Orphan removal.
- Composite IDs/FKs.
- Lazy/eager loading.
- Pagination + collection.
- Native queries.
- Custom types.
- Envers add/modify/delete.
- Soft delete/restore nếu có.
- Transaction rollback.
- Batch inserts.
- Multi-tenancy.

Chạy cùng fixtures trên version cũ và version mới, so sánh:
- Kết quả business/API.
- Row counts và values.
- SQL types/constraints.
- Historical revisions.
- Transaction outcomes.
- Query counts/performance envelopes.

Không snapshot mọi SQL string như golden file cứng vì alias/format/statement order có thể đổi mà semantics vẫn đúng. Chỉ assert SQL details khi đó là contract cần giữ.

## 38. Kiểm thử startup và bootstrap riêng

Một smoke test khởi tạo EntityManagerFactory/Spring context có thể bắt:
- Missing Dialect class.
- Removed SPI.
- Invalid property.
- Type registration errors.
- Mapping metadata errors.
- Revision entity errors.
- Missing audit table khi validate.
- Incompatible dependencies.

Nhưng startup pass chưa đủ. Nhiều lỗi chỉ xuất hiện ở query cụ thể, collection initialization, commit hoặc historical read.

Tách:
1. Bootstrap test.
2. Mapping CRUD tests.
3. Query behavior tests.
4. Transaction tests.
5. Envers history tests.
6. Performance/observability tests.

## 39. Kiểm tra schema bằng migrations thật

Một test nâng cấp nên có hai luồng:

```text
Fresh install:
  empty database
      |
      v
  Flyway/Liquibase migrations
      |
      v
  Hibernate ddl-auto=validate
      |
      v
  ORM + Envers tests

Upgrade:
  schema version N + representative data
      |
      v
  migration N -> N+1
      |
      v
  Hibernate bootstrap
      |
      v
  read old audit revisions
      |
      v
  write new revision
      |
      v
  verify history and constraints
```

Không để Hibernate `create-drop` tạo schema mới trong test rồi kết luận migration production đúng.

### 39.1. Upgrade fixture phải có dữ liệu đại diện

Bao gồm:
- Entity chưa từng update.
- Entity có nhiều revisions.
- Entity đã delete.
- Composite IDs.
- Collections.
- Null/large values.
- Legacy enum/type values.
- Historical rows trước khi thêm field.
- Data có thể gây unique/FK conflicts.

## 40. Testcontainers và đúng DBMS

Nếu production dùng PostgreSQL, dùng PostgreSQL container; nếu production dùng Oracle, MySQL hoặc SQL Server, dùng container/image phù hợp với license và CI policy của DBMS đó.

Một skeleton PostgreSQL:

```java
@Testcontainers
@SpringBootTest
class HibernateUpgradeIT {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(
            DynamicPropertyRegistry registry
    ) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
        registry.add("spring.jpa.hibernate.ddl-auto", () -> "validate");
        registry.add("spring.flyway.enabled", () -> "true");
    }
}
```

Đây là skeleton; cần dependencies/imports, migrations và cấu hình ứng dụng thực tế. Pin DB image version thay vì `latest` để kết quả reproducible.

### 40.1. Compatibility mode không thay thế DBMS thật

H2 ở PostgreSQL mode vẫn là H2. Nó không chứng minh:
- Partial indexes.
- JSONB operators.
- Deferred constraints.
- Locking semantics.
- Sequence behavior.
- DDL transaction behavior.
- JDBC driver binding.

Dùng đúng DBMS cho những capabilities ứng dụng dựa vào.

## 41. Kiểm tra property có hiệu lực bằng hành vi

Một test cấu hình tốt nên tạo khác biệt có thể quan sát.

Ví dụ muốn xác nhận batch size:
- Chạy cùng một fixture với batch size 0 và 25.
- Dùng JDBC/datasource instrumentation ghi nhận `addBatch`/`executeBatch`.
- So sánh round trips hoặc batch metrics.
- Giữ transaction và generator tương đương.

Muốn xác nhận timezone:
- Persist timestamp có offset khác UTC.
- Đọc bằng context mới.
- Kiểm tra instant và DB column semantics.

Muốn xác nhận query fetch behavior:
- Đếm SELECT statements.
- Kiểm tra collection completeness.
- Kiểm tra memory/query rows nếu pagination.

Không test property bằng cách assert nó tồn tại trong `Environment`; điều đó chỉ chứng minh Spring biết key, không chứng minh Hibernate đã tiêu thụ nó.

## 42. Differential testing cho defaults

Khi nghi default thay đổi:
1. Tạo một test profile không khai báo property.
2. Ghi lại behavior trên version nguồn.
3. Chạy cùng test trên version đích.
4. Tạo profile đích pin giá trị cũ (nếu property còn hỗ trợ).
5. So sánh behavior.
6. Quyết định chấp nhận default mới hay cấu hình tường minh.
7. Ghi lý do vào migration notes.

Ví dụ:
- Query count trước/sau.
- Generated ID patterns.
- Naming strategy output.
- Fetch SQL.
- Timestamp conversion.
- Cache statistics.
- DDL validation.
- Envers revision reads.

Đừng mặc định pin mọi default cũ là lựa chọn tốt. Một default mới có thể sửa bug hoặc cải thiện an toàn.

## 43. Performance regression không nhất thiết là config regression

Sau nâng cấp, SQL có thể khác nhưng không nhất thiết sai. Một số thay đổi:
- SQL alias/format.
- Join order.
- Batch grouping.
- Fetch plan.
- Type casts.
- Query plan do JDBC bind type khác.
- Number of prepared statements.
- Cache hit/miss.

Đánh giá theo:
- Result correctness.
- Rows scanned.
- Execution plan.
- Latency percentile.
- DB CPU/IO.
- Network round trips.
- Lock waits.
- Heap/GC.
- Query count.

Không revert một feature chỉ vì SQL text không giống version cũ.

## 44. Triển khai nâng cấp theo expand-contract

Nếu schema và application cần thay đổi cùng nhau:
1. Thêm schema objects mới tương thích code cũ.
2. Deploy application version mới có thể đọc schema cũ/mới theo thiết kế.
3. Bật write path mới.
4. Backfill dữ liệu.
5. Xác nhận metrics và historical reads.
6. Chuyển reads.
7. Đợi mọi instances cũ dừng.
8. Loại bỏ schema/API cũ ở release sau.

Với Envers, đừng drop audit columns/tables khi old binaries còn ghi hoặc đọc chúng.

### 44.1. Config rollout có thể cần feature flags

Một behavior mới như query fetch strategy, cache provider hoặc generator có thể được bật theo profile/feature flag nếu ứng dụng thiết kế cho phép. Nhưng tránh giữ hai nguồn cấu hình mâu thuẫn lâu dài.

## 45. Rollback application không tự rollback schema

Nếu app version mới đã migrate audit tables, rollback binary về app cũ không nhất thiết an toàn:
- App cũ có thể không hiểu schema mới.
- Revision entity columns mới có thể bắt buộc.
- Type mapping cũ không đọc được SQL type mới.
- Old code có thể ghi dữ liệu không còn tương thích.

Phải định nghĩa:
- Schema backward compatibility.
- Binary compatibility.
- Data migration reversibility.
- Backup/restore.
- Forward-fix path.
- Conditions cho phép rollback.

Không chạy down migration xóa dữ liệu chỉ để khớp code cũ nếu đã có dữ liệu mới không thể biểu diễn trong schema cũ.

## 46. Logging deprecation và startup warnings

Trong môi trường staging:
- Bật log cho Hibernate bootstrap và deprecation warnings phù hợp.
- Thu thập warnings từ custom code và dependency.
- Xác định warning nào do cấu hình cũ.
- Kiểm tra warning có được phát một lần hay chỉ khi code path chạy.
- Không tắt logger để làm sạch output trước khi hiểu warning.

Một warning không nhất thiết là lỗi ngay lập tức, nhưng có thể là dấu hiệu API sẽ bị xóa hoặc behavior thay đổi ở major tiếp theo.

### 46.1. Không coi absence of warning là proof

Property unknown có thể bị bỏ qua mà không warning. Cần documentation lookup và behavior tests.

## 47. Troubleshooting: cấu hình cũ không còn tác dụng

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Hibernate dùng Dialect khác | Auto-detection hoặc class cũ | Kiểm tra JDBC metadata và version đích |
| Class Dialect không tìm thấy | Class chuyển module/removed | Thêm module đúng hoặc thay Dialect |
| `javax` annotations bị bỏ qua | Hibernate 6 dùng Jakarta namespace | Chuyển imports/dependencies/XML |
| Legacy Criteria không compile | API đã removed | Chuyển JPA Criteria/HQL/DTO |
| Custom type không compile | Type SPI đổi | Port theo type system mới |
| `@Type(type=...)` lỗi | Annotation API thay đổi | Dùng supported mapping/type registration |
| Schema validation fail | Naming/type/default mapping đổi | So sánh metadata và migration |
| ID allocation khác | Generator mapping/default khác | Kiểm tra sequence, allocation size, optimizer |
| Sequence collision sau deploy | Sequence state không theo dữ liệu hiện tại | Migration sequence value và test nhiều instances |
| Query trước chạy nay lỗi | HQL parser/type checking chặt hơn | Viết query tường minh, test parameters |
| Page query đọc quá nhiều rows | Fetch join collection + pagination | Two-phase IDs hoặc batch fetching |
| Batch size có nhưng không batch | Generator/driver/transaction không phù hợp | JDBC instrumentation và ID strategy |
| SQL logs không có bind values | Logger category cũ hoặc level sai | Dùng category đúng version |
| L2 cache không hoạt động | RegionFactory/provider incompatibility | Kiểm tra provider SPI/version |
| Timestamp lệch | JDBC timezone/column semantics | Round-trip Instant/offset trên DB thật |
| Envers insert lỗi | `_AUD` schema không khớp | Migration audit tables và revision entity |
| Historical query lỗi sau đổi strategy | Thiếu `REVEND`/backfill | Migrate Validity schema đúng |
| Modified flag column thiếu | Mapping bật flags nhưng migration quên | Thêm columns và test AuditReader |
| `ddl-auto` chạy ngoài ý muốn | Spring Boot default/profile khác | Pin schema action rõ ràng |
| Property có trong YAML nhưng không đổi behavior | Sai namespace/unknown/overridden | Trace property precedence và test hiệu lực |
| H2 pass, production fail | Dialect/DBMS behavior khác | Testcontainers đúng DBMS |
| Upgrade app rollback không chạy | Schema đã thay đổi phá binary cũ | Expand-contract và compatibility plan |
| Warning deprecation biến mất nhưng behavior sai | Logger bị tắt hoặc code path chưa chạy | Runtime tests và startup tracing |
| Native SQL bỏ qua cache/audit semantics | Bypass ORM lifecycle | Invalidate cache/audit path riêng |
| Boot upgrade làm tên cột đổi | Naming strategy default đổi | Pin strategy hoặc migrate schema |

## 48. Checklist đánh giá một cấu hình cũ

Với mỗi property/API, trả lời:

1. Cấu hình được khai báo ở file, environment hay Java code nào?
2. Thành phần nào tiêu thụ nó: Spring, JPA, Hibernate, driver, pool hay DBMS?
3. Version nguồn có hỗ trợ không?
4. Version đích còn hỗ trợ không?
5. Có deprecated/removal notice không?
6. Default của version đích là gì?
7. Có property alias/replacement chính thức không?
8. Namespace/prefix có đổi không?
9. Có source cấu hình khác override không?
10. Cấu hình có ảnh hưởng schema không?
11. Có ảnh hưởng dữ liệu hiện hữu không?
12. Có ảnh hưởng transaction/consistency không?
13. Có ảnh hưởng security/tenant isolation không?
14. Có ảnh hưởng performance/SQL shape không?
15. Có test chứng minh behavior không?
16. Có DBMS-specific capability không?
17. Có Envers/audit schema liên quan không?
18. Có thể rollout và rollback an toàn không?
19. Có owner và deadline loại bỏ legacy setting không?
20. Có tài liệu ghi quyết định và version áp dụng không?

## 49. Mẫu bảng quyết định migration

| Property/API | Version cũ | Version đích | Phân loại | Hành vi cần giữ | Hành động | Test |
| --- | --- | --- | --- | --- | --- | --- |
| `hibernate.dialect` | Dialect class cũ | Auto-detect/custom | Review | SQL phù hợp DB | Giữ hoặc bỏ có căn cứ | Bootstrap + SQL |
| `hibernate.id.new_generator_mappings` | Legacy setting | Version-dependent | Review/removal | ID uniqueness | Thay generator mapping | Restart/concurrency |
| `hibernate.hbm2ddl.auto` | Hibernate schema action | Boot/JPA config | Review | Không tự sửa prod schema | Pin `validate` | Migration test |
| `javax.persistence.*` | javax namespace | jakarta namespace | Removed compatibility | Entity metadata | Port imports/deps | Bootstrap |
| Legacy Criteria | Hibernate Criteria | JPA Criteria/HQL | Removed | Query result | Rewrite | Query fixture |
| Custom `UserType` | Old SPI | New type system | API change | Type round-trip | Port | Live + audit |
| `hibernate.jdbc.batch_size` | Configured value | Same/new runtime | Verify | Batch writes | Keep/tune | JDBC metrics |
| Envers strategy | Default | Default/Validity | Explicit decision | Historical reads | Schema migration if changed | AuditReader |
| Naming strategy | Old default | New default/custom | Default drift | Column names | Pin or migrate | Schema validate |
| SQL logging | Old categories | New categories | Renamed/changed | Diagnostic visibility | Update logger | Capture bind logs |

Các nhãn `Review`/`version-dependent` có chủ ý: không có một bảng chung có thể xác định trạng thái mọi property cho mọi version. Ghi rõ version nguồn/đích trong quyết định thực tế.

## 50. Quy trình nâng cấp theo từng vòng

**Vòng 1 — Inventory.** Thu thập dependencies, property files, XML descriptors, environment variables, Java bootstrap code, custom types và Dialects.

**Vòng 2 — Classify.** Với từng property/API, phân loại supported, renamed, deprecated, removed, ignored hoặc default-changed. Ghi nguồn tài liệu và version áp dụng.

**Vòng 3 — Freeze behavior baseline.** Chạy test trên version cũ và lưu kết quả nghiệp vụ, schema, query count, ID generation, transaction và Envers history.

**Vòng 4 — Port compile-time APIs.** Chuyển Jakarta namespace, Criteria, custom types, Dialect/SPI và event/listener code.

**Vòng 5 — Migrate schema.** Cập nhật live tables, sequences, constraints, audit tables, revision entity, indexes và data backfill.

**Vòng 6 — Pin critical configuration.** Khai báo tường minh những defaults có ảnh hưởng tới schema, correctness, security hoặc performance contract.

**Vòng 7 — Run DBMS-specific tests.** Dùng migrations thật, `ddl-auto=validate`, Testcontainers/DBMS tương đương production.

**Vòng 8 — Differential behavior tests.** So sánh output và transaction semantics giữa version cũ/mới; không yêu cầu SQL text giống tuyệt đối.

**Vòng 9 — Observe staging.** Theo dõi warnings, SQL, JDBC batches, latency, DB load, cache và audit revision behavior.

**Vòng 10 — Rollout.** Dùng expand-contract nếu schema thay đổi; xác định điều kiện rollback binary/schema.

**Vòng 11 — Remove obsolete configuration.** Sau khi replacement được xác nhận, bỏ legacy properties, dependencies và compatibility code.

**Vòng 12 — Record support matrix.** Ghi version Hibernate, Envers, Spring, driver và DBMS được hỗ trợ để lần nâng cấp sau có baseline rõ ràng.

## 51. Bài tập tình huống

### Bài 1 — Property còn trong file

`hibernate.jdbc.batch_size=50` vẫn còn trong YAML sau nâng cấp. Có thể kết luận batching đang chạy không?

**Đáp án:** Không. Phải xác nhận property được truyền tới Hibernate, ID strategy và driver cho phép batching, rồi đo JDBC `executeBatch`.

### Bài 2 — Dialect cũ

Ứng dụng khai báo `PostgreSQL10Dialect` nhưng class không còn trong artifact mới. Làm gì?

**Đáp án:** Xác nhận Hibernate version và DB server; dùng Dialect được hỗ trợ/auto-detection hoặc module tương ứng, rồi test SQL capabilities thực tế.

### Bài 3 — `javax` và `jakarta`

Hibernate 6 chạy nhưng entity không được nhận diện. Source vẫn import `javax.persistence.Entity`. Vì sao?

**Đáp án:** Hibernate 6 dùng Jakarta Persistence namespace; phải chuyển annotation và dependency tương thích sang `jakarta.persistence`.

### Bài 4 — Legacy Criteria

`Session.createCriteria()` không compile sau nâng cấp. Có property nào bật lại không?

**Đáp án:** Không. Legacy Criteria API đã bị loại; chuyển sang JPA Criteria, HQL hoặc query/projection phù hợp.

### Bài 5 — Type cũ

Custom `@Type(type="json")` không còn compile. Có nên thay bằng `String` không?

**Đáp án:** Không tự động. Xác định SQL type/JSON query needs và port sang mapping được hỗ trợ, sau đó test live + Envers round-trip.

### Bài 6 — Default schema action

Sau Spring Boot upgrade, app test tự tạo schema ngoài ý muốn. Nguyên nhân có thể?

**Đáp án:** Spring Boot schema action default/profile khác. Pin `spring.jpa.hibernate.ddl-auto` theo môi trường và để migration tool quản lý schema production.

### Bài 7 — Sequence collision

Nâng generator, hai app instances cấp ID có nguy cơ trùng. Kiểm tra gì?

**Đáp án:** Sequence increment, allocationSize, optimizer, current sequence value, generator schema và concurrent multi-instance test.

### Bài 8 — Query parser

HQL cũ so association object với Long ID và giờ lỗi. Cách viết rõ?

**Đáp án:** So sánh `o.customer.id = :customerId` hoặc bind entity đúng type.

### Bài 9 — Fetch join

Page query trả ít roots và đọc rất nhiều rows. `DISTINCT` có chắc sửa không?

**Đáp án:** Không. Phân trang root IDs trước, sau đó fetch collection graph riêng hoặc dùng batch/DTO.

### Bài 10 — Bind logging

Hibernate SQL category vẫn log SQL nhưng không có bind values. Có thể do đâu?

**Đáp án:** Logger category thay đổi theo Hibernate version; cấu hình `org.hibernate.orm.jdbc.bind` ở TRACE cho version phù hợp và bảo vệ PII.

### Bài 11 — Cache provider

Sau nâng Hibernate, cache dependency còn nhưng không thấy L2 hits. Kiểm tra gì?

**Đáp án:** RegionFactory/provider SPI compatibility, effective cache settings, region config và runtime statistics.

### Bài 12 — Envers Validity

Bật `ValidityAuditStrategy` nhưng commit lỗi thiếu `REVEND`. Vì sao?

**Đáp án:** Audit schema chưa migrate thêm revision-end metadata và backfill phù hợp.

### Bài 13 — Bỏ `@NotAudited`

Thêm `@NotAudited` hôm nay có xóa field khỏi audit rows cũ không?

**Đáp án:** Không. Historical data cũ vẫn có thể tồn tại; cần retention/remediation migration riêng.

### Bài 14 — H2 test

Test pass H2 nhưng PostgreSQL fail do deferred FK. Có thể đổi Dialect trên H2 không?

**Đáp án:** Không đủ. Chạy test trên PostgreSQL thật bằng Testcontainers vì server/driver semantics khác.

### Bài 15 — Default timezone

Timestamp lệch sau nâng driver. Chỉ cần ép `hibernate.jdbc.time_zone=UTC`?

**Đáp án:** Chưa chắc. Kiểm tra Java type, column type, JDBC driver, DB session timezone và round-trip instant semantics.

### Bài 16 — Deprecated API

Một method bị deprecated nhưng test vẫn pass. Có thể bỏ qua mãi không?

**Đáp án:** Không. Xác định replacement, version removal risk, tạo test rồi lập kế hoạch loại bỏ trước major upgrade tiếp theo.

### Bài 17 — Property ignored

Không có warning nhưng thay property từ true sang false không đổi behavior. Kết luận gì?

**Đáp án:** Cần kiểm tra namespace, precedence, consumer và runtime code path; absence of warning không chứng minh property có hiệu lực.

### Bài 18 — SQL text thay đổi

Hibernate mới sinh SQL khác alias và join order nhưng kết quả đúng, performance tốt hơn. Có cần rollback?

**Đáp án:** Không chỉ vì SQL text khác. Đánh giá result semantics, query plan, latency và DB resource usage.

### Bài 19 — Rollback binary

App mới đã migrate audit schema rồi rollback binary cũ. Có chắc chạy được?

**Đáp án:** Không. Schema mới có thể phá compatibility với binary cũ; cần expand-contract và rollback plan đã test.

### Bài 20 — Configuration freeze

Có nên copy toàn bộ defaults Hibernate cũ thành properties tường minh để giữ nguyên behavior?

**Đáp án:** Không mặc định. Chỉ pin defaults ảnh hưởng contract quan trọng sau khi xác minh; tránh tạo configuration debt và khóa mất cải tiến an toàn.

## 52. Tài liệu tham khảo chính thức

- [Hibernate ORM Migration Guides](https://hibernate.org/orm/releases/): migration notes theo từng release, API removals, deprecations và behavioral changes.
- [Hibernate ORM User Guide](https://docs.hibernate.org/orm/): configuration, identifiers, types, fetching, transactions, caching và SQL behavior theo version.
- [Hibernate ORM Javadocs](https://docs.hibernate.org/orm/current/javadocs/): API signatures, deprecation và replacement documentation.
- [Hibernate ORM Logging](https://docs.hibernate.org/orm/current/logging/logging.html): logging categories và SQL/JDBC diagnostics.
- [Hibernate Envers](https://hibernate.org/orm/envers/): audit module, revision model và compatibility.
- [Jakarta Persistence Specifications](https://jakarta.ee/specifications/persistence/): namespace, entity mappings, query, transaction và schema-generation contracts.
- [Spring Boot Reference Documentation](https://docs.spring.io/spring-boot/reference/): property binding, JPA auto-configuration, datasource và schema initialization.
- [Spring Data JPA Reference](https://docs.spring.io/spring-data/jpa/reference/): repository, query methods, paging và persistence integration.
- [Flyway Documentation](https://documentation.red-gate.com/flyway): versioned migrations, validation, repair và execution behavior.
- [Liquibase Documentation](https://docs.liquibase.com/): changelogs, changesets, rollback và database support.
- [Testcontainers Documentation](https://java.testcontainers.org/): integration tests với DBMS thật.
- [PostgreSQL Documentation](https://www.postgresql.org/docs/current/): SQL types, constraints, indexes, transactions và server-specific capabilities.
- [MySQL Reference Manual](https://dev.mysql.com/doc/refman/): SQL dialect, types, indexes, transactions và server version behavior.
- [Oracle Database Documentation](https://docs.oracle.com/en/database/): data types, sequences, constraints, transactions và SQL capabilities.
- [Microsoft SQL Server Documentation](https://learn.microsoft.com/sql/): data types, identity, indexes, constraints và transaction semantics.

**Ghi chú phiên bản:** Không có danh sách property “cũ” áp dụng đồng nhất cho mọi ứng dụng. Trạng thái chính xác của một setting/API phụ thuộc version nguồn, version đích, Spring Boot BOM, driver, Dialect và DBMS server. Các ví dụ trong bài là điểm cần điều tra; khi ra quyết định, đối chiếu migration guide/Javadocs đúng hai version và xác nhận bằng behavior tests.

## Kết luận

Đánh giá cấu hình cũ là quá trình xác định **hành vi thực tế** của ứng dụng sau nâng cấp. Một property có thể đổi tên, deprecated, removed, bị bỏ qua hoặc vẫn hợp lệ nhưng không còn tạo ra hiệu quả như trước. Một default mới có thể làm thay đổi schema, identifier generation, query, fetch plan, timezone, cache hoặc audit behavior dù không có dòng cấu hình nào được sửa.

Hãy kiểm kê cấu hình từ mọi nguồn, pin rõ version của Hibernate/Envers/Spring/driver/DBMS, đối chiếu migration guide của version nguồn và đích, rồi phân loại từng setting theo consumer và semantics. Với những thay đổi ảnh hưởng dữ liệu, schema, transaction, security hoặc performance, hãy có migrations và integration tests trên DBMS thật; với API deprecated/removed, chuyển sang extension point được hỗ trợ thay vì giữ compatibility bằng suy đoán.

Một lần nâng cấp đáng tin cậy không phải là lần nâng cấp có ít compile errors nhất. Đó là lần mà các cấu hình quan trọng đã được giải thích, hành vi cần giữ đã được kiểm chứng, default mới được chấp nhận có chủ đích, và đường triển khai/rollback không làm mất dữ liệu hay lịch sử.

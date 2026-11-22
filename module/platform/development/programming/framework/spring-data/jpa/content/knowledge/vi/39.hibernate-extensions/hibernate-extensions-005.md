# Ánh xạ JSON và kiểu cơ sở dữ liệu đặc thù trong Hibernate

Hibernate mở rộng khả năng mapping của JPA để làm việc với các kiểu dữ liệu database không được biểu diễn trực tiếp bằng kiểu Java cơ bản, trong đó có JSON, SQL ARRAY, UUID, enum native và các kiểu riêng của từng hệ quản trị. Với JSON, Hibernate 6 cung cấp mapping qua `@JdbcTypeCode(SqlTypes.JSON)`, cho phép ánh xạ một thuộc tính Java như POJO, `Map` hoặc cấu trúc JSON tree vào cột JSON của database.

Cần tách biệt ba việc:

- **Java type:** kiểu object mà ứng dụng sử dụng, ví dụ `Map<String, Object>`, record hoặc `JsonNode`.
- **JDBC/Hibernate type:** cách Hibernate serialize, bind parameter và đọc dữ liệu qua JDBC.
- **Database column type:** kiểu cột thực tế như PostgreSQL `jsonb`, PostgreSQL `json`, MySQL `JSON` hoặc kiểu lưu trữ JSON-specific của database khác.

Annotation `@JdbcTypeCode` định hướng Hibernate chọn JDBC type. `columnDefinition` chủ yếu mô tả fragment DDL khi Hibernate tạo schema; nó không tự cung cấp serializer, JDBC binding hoặc JSON query support. Migration và schema thật phải khớp với mapping.

Tài liệu dùng Hibernate ORM 6+ và Jakarta Persistence (`jakarta.persistence`) trong Spring Boot 3 trở lên. Các extension như JSON mapping, custom UserType và database-specific JDBC types phụ thuộc phiên bản Hibernate và dialect; luôn đối chiếu với phiên bản ORM mà Spring Boot BOM quản lý.

## 1. Vì sao cần kiểu Hibernate đặc thù?

JPA chuẩn cung cấp các kiểu mapping phổ biến như String, numeric, date/time, enum, relationship và converter. Nhưng database hiện đại còn có các kiểu phong phú hơn:

- JSON/JSONB để lưu document có cấu trúc linh hoạt.
- SQL ARRAY để lưu một tập giá trị trong một cột.
- UUID native.
- Enum type do database định nghĩa.
- Network type như PostgreSQL INET/CIDR.
- Spatial type như geometry/geography.
- Vendor-specific binary, range, vector hoặc kiểu mở rộng khác.

Nếu dùng String cho mọi kiểu đặc thù, ứng dụng có thể mất khả năng binding, validation, query operator hoặc index chuyên biệt của database. Hibernate type system cho phép ánh xạ kiểu Java sang JDBC/database type phù hợp hơn.

Không phải mọi database hỗ trợ cùng kiểu dữ liệu. Một mapping chạy trên PostgreSQL có thể không chạy trên MySQL hoặc H2 nếu dialect, DDL và JDBC driver khác nhau.

## 2. Mapping JSON trong Hibernate 6

Hibernate 6 cung cấp JSON mapping qua:

```java
@JdbcTypeCode(SqlTypes.JSON)
```

Import:

```java
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;
```

Ví dụ entity:

```java
@Entity
@Table(name = "event")
public class Event {

    @Id
    @GeneratedValue
    private Long id;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private Map<String, Object> payload;

    protected Event() {
    }

    public Map<String, Object> getPayload() {
        return payload;
    }

    public void setPayload(Map<String, Object> payload) {
        this.payload = payload;
    }
}
```

Ở đây:

- `Map<String, Object>` là Java representation.
- `@JdbcTypeCode(SqlTypes.JSON)` yêu cầu Hibernate dùng JSON JDBC mapping.
- `columnDefinition = "jsonb"` là DDL fragment cụ thể cho PostgreSQL khi Hibernate tạo schema.
- Migration phải tạo cột có kiểu tương thích với mapping.

`columnDefinition` không phải điều kiện duy nhất để bật JSON serializer. Nếu chỉ viết `@Column(columnDefinition = "jsonb")` mà không cấu hình JSON JDBC mapping, Hibernate có thể vẫn xử lý thuộc tính theo kiểu Java/JDBC mặc định và phát sinh lỗi.

Với schema do Flyway/Liquibase quản lý, DDL migration là nguồn sự thật. Không dựa vào `columnDefinition` để tự tạo hoặc thay đổi cột ở production.

## 3. Các Java representation có thể dùng

Hibernate JSON mapping có thể serialize/deserialize các cấu trúc Java phù hợp với JSON format mapper được cấu hình.

### 3.1. Map

```java
@JdbcTypeCode(SqlTypes.JSON)
@Column(columnDefinition = "jsonb")
private Map<String, Object> metadata;
```

Ưu điểm:

- Linh hoạt khi cấu trúc document thay đổi.
- Dễ thêm/bỏ key.
- Hữu ích cho metadata, settings hoặc payload không có schema cố định.

Nhược điểm:

- Ít type safety.
- Dễ sai tên key hoặc kiểu value khi đọc.
- Nested object thường phải cast hoặc kiểm tra kiểu.
- Refactor cấu trúc JSON khó được compiler hỗ trợ.

Nếu dùng Map, hãy xác định rõ quy ước key, kiểu dữ liệu và schema version của document.

### 3.2. POJO hoặc record

Với cấu trúc ổn định, dùng class/record:

```java
public record DeliveryAddress(
    String city,
    String postalCode,
    String countryCode
) {
}
```

Entity:

```java
@Entity
public class Shipment {

    @Id
    @GeneratedValue
    private Long id;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private DeliveryAddress destination;
}
```

Cách này tăng type safety, dễ refactor và dễ validate ở application layer. Record bất biến có thể giúp thay toàn bộ value object rõ ràng khi cập nhật document.

Hibernate cần JSON format mapper có thể serialize/deserialize kiểu Java đó. Jackson hoặc JSON-B thường được dùng tùy classpath/cấu hình; hãy xác nhận dependency và mapper thực tế của ứng dụng. Nếu có constructor, record component, polymorphic type hoặc custom serializer, cần integration test cho round trip.

### 3.3. JSON tree như JsonNode

Nếu ứng dụng dùng Jackson:

```java
import com.fasterxml.jackson.databind.JsonNode;

@Entity
public class AuditEvent {

    @Id
    @GeneratedValue
    private Long id;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private JsonNode document;
}
```

JsonNode phù hợp khi cần thao tác JSON tree mà không muốn tạo POJO cho mọi cấu trúc. Nó phụ thuộc Jackson và không phải kiểu JSON của Jakarta Persistence.

Chỉ chọn một Java representation phù hợp với domain. Tránh chuyển Map sang String rồi lưu JSON string trong cột JSON nếu mục tiêu là để Hibernate quản lý JSON binding trực tiếp; điều đó có thể dẫn tới lưu JSON bị double-encode như một chuỗi thay vì document.

## 4. JSON format mapper và cấu hình serialization

Hibernate cần một JSON format mapper để chuyển Java object thành JSON và ngược lại. Hibernate 6 có thể chọn mapper dựa trên thư viện có trên classpath, thường là Jackson hoặc JSON-B, và có thể cấu hình rõ bằng setting tương ứng của Hibernate.

Các yếu tố ảnh hưởng kết quả:

- Jackson module cho Java Time, records hoặc kiểu custom.
- Naming strategy và annotation serialization.
- Custom serializer/deserializer.
- Cách xử lý unknown property và null.
- Polymorphic type metadata.
- Version schema của JSON document.

Không mặc định mọi cấu hình ObjectMapper của Spring Boot đều tự động được Hibernate JSON mapper sử dụng. Cấu hình Hibernate JSON format mapper và Jackson HTTP serialization có thể là hai đường riêng; nếu cần cùng behavior, hãy cấu hình và kiểm thử rõ ràng theo phiên bản Hibernate.

Đối với document đã lưu lâu dài, thay đổi serializer hoặc tên property có thể làm dữ liệu cũ không deserialize được. Nên có chiến lược versioning/migration cho JSON schema, đặc biệt khi document được dùng như một phần dữ liệu nghiệp vụ.

## 5. PostgreSQL: json và jsonb

PostgreSQL cung cấp hai kiểu chính:

| Kiểu | Đặc điểm |
|---|---|
| `json` | Lưu văn bản JSON đầu vào; giữ whitespace và thứ tự key theo văn bản đã nhận, kiểm tra cú pháp JSON |
| `jsonb` | Lưu dạng binary đã phân tích; không giữ whitespace/thứ tự key nguyên bản, hỗ trợ operator/index phong phú hơn |

Thông thường `jsonb` phù hợp hơn cho document cần query/index thường xuyên. `json` có thể phù hợp khi cần giữ nguyên representation văn bản hoặc workload chỉ ghi/đọc toàn document.

Migration ví dụ:

```sql
create table event (
    id bigserial primary key,
    payload jsonb not null
);
```

Entity:

```java
@JdbcTypeCode(SqlTypes.JSON)
@Column(columnDefinition = "jsonb", nullable = false)
private Map<String, Object> payload;
```

Column type phải thống nhất giữa migration và mapping. Nếu schema đã có cột `json`, không khai báo `jsonb` trong entity như thể hai kiểu hoàn toàn giống nhau; chọn đúng kiểu database đang sử dụng.

## 6. MySQL và các database khác

MySQL có kiểu cột `JSON`, có validation JSON ở database và cung cấp các function như `JSON_EXTRACT`, `JSON_SET`, `JSON_CONTAINS`.

DDL minh họa:

```sql
create table event (
    id bigint primary key auto_increment,
    payload json not null
);
```

Mapping Hibernate:

```java
@JdbcTypeCode(SqlTypes.JSON)
@Column(columnDefinition = "json")
private Map<String, Object> payload;
```

Không copy DDL PostgreSQL `jsonb` sang MySQL. Tên type, operator, index và cách query JSON khác nhau theo database.

Một số database lưu JSON trong kiểu text/binary hoặc có native JSON type theo phiên bản. Oracle, SQL Server, MariaDB và các database khác có thể khác nhau về DDL, constraint, function và index. Hãy kiểm tra documentation của đúng phiên bản database và dialect Hibernate đang chạy.

## 7. Truy vấn thuộc tính JSON bằng native SQL

Hibernate JSON mapping giúp lưu/đọc document, nhưng cú pháp truy vấn JSON thường phụ thuộc database.

PostgreSQL:

```sql
select id, payload ->> 'status' as status
from event
where payload ->> 'status' = :status;
```

MySQL:

```sql
select id,
       json_unquote(json_extract(payload, '$.status')) as status
from event
where json_unquote(json_extract(payload, '$.status')) = :status;
```

Có thể chạy qua Spring Data native query hoặc EntityManager:

```java
@Query(
    value = """
        select *
        from event
        where payload ->> 'status' = :status
        """,
    nativeQuery = true
)
List<Event> findByPayloadStatus(
    @Param("status") String status
);
```

Ví dụ query trên dành cho PostgreSQL. Không dùng nguyên SQL đó trên MySQL; cần function/operator tương ứng.

Bind giá trị bằng parameter. JSON path hoặc identifier động không phải lúc nào cũng bind như value parameter theo cùng cách giữa các database; nếu cần path động, whitelist path được phép và xây query theo chiến lược an toàn. Không nối raw input thành SQL.

JPQL không có một cú pháp JSON operator portable cho mọi database. Có thể gọi database function qua Hibernate HQL/Criteria function hoặc native SQL, nhưng function name và semantics phụ thuộc dialect.

## 8. Index cho JSON

Không có một index JSON chung áp dụng giống nhau cho mọi database.

PostgreSQL:

```sql
create index ix_event_payload_gin
on event using gin (payload);
```

GIN index hỗ trợ nhiều JSONB containment/key-existence query. Có thể tạo expression index cho một path cụ thể:

```sql
create index ix_event_payload_status
on event ((payload ->> 'status'));
```

MySQL thường cần generated column hoặc functional index phù hợp với JSON expression:

```sql
alter table event
add column payload_status varchar(40)
    generated always as (
        json_unquote(json_extract(payload, '$.status'))
    ) stored;

create index ix_event_payload_status
on event(payload_status);
```

Ví dụ index phụ thuộc engine/version và expression phải khớp query. Kiểm tra EXPLAIN/EXPLAIN ANALYZE để xác nhận optimizer dùng index.

Không tạo GIN hoặc index cho mọi JSON column theo mặc định. Index làm tăng storage và chi phí INSERT/UPDATE; hãy index path/operator thực sự xuất hiện trong workload.

## 9. Cập nhật một phần document hay thay toàn bộ JSON?

Khi ứng dụng sửa một thuộc tính trong Map/POJO, Hibernate có thể serialize và ghi lại toàn bộ giá trị JSON của cột. Đây không mặc nhiên là JSON path update tại database.

Ví dụ:

```java
@Transactional
public void changeStatus(Long id, String status) {
    Event event = repository.findById(id).orElseThrow();

    Map<String, Object> payload =
        new HashMap<>(event.getPayload());

    payload.put("status", status);
    event.setPayload(payload);
}
```

Thay object Map mới làm thay đổi reference rõ ràng và giúp semantics dirty checking dễ hiểu. Với kiểu mutable, cần kiểm tra mutability plan và equality của Java type/mapper mà Hibernate sử dụng; đừng giả định mọi thay đổi sâu bên trong object đều được phát hiện giống nhau ở mọi kiểu.

Nếu cần cập nhật đúng một path mà không ghi lại toàn document, có thể dùng native function như PostgreSQL `jsonb_set` hoặc MySQL `JSON_SET`. Đây là database-specific DML và cần đồng bộ PersistenceContext nếu entity đang managed.

Ví dụ PostgreSQL:

```sql
update event
set payload = jsonb_set(
    payload,
    '{status}',
    to_jsonb(cast(:status as text)),
    true
)
where id = :id;
```

Sau native bulk update, entity Event đang managed có thể giữ payload cũ. Cần refresh entity hoặc clear PersistenceContext theo phạm vi phù hợp. Bulk/native DML không tự chạy lifecycle callback, cascade hoặc dirty checking cho từng entity.

## 10. SQL NULL, JSON null và key không tồn tại

Ba trạng thái này không giống nhau:

1. **SQL NULL:** cả cột payload không có giá trị database.
2. **JSON null:** document có giá trị JSON literal `null`, hoặc một property có giá trị null.
3. **Missing key:** object JSON không chứa key được hỏi.

Ví dụ document:

```json
{
  "status": null
}
```

Khác với:

```json
{}
```

Và khác với cột SQL có payload = NULL.

Các database JSON function có thể trả SQL NULL, JSON null hoặc kết quả khác nhau tùy function/path/operator. Ví dụ PostgreSQL operator `->>` trả text và có semantics riêng cho missing key/JSON null. MySQL JSON_EXTRACT có thể trả JSON value và JSON null; JSON_UNQUOTE có behavior tương ứng.

Hãy định nghĩa rõ semantics nghiệp vụ: “không có status”, “status null” và “payload không tồn tại” có ý nghĩa khác nhau hay không. Viết integration test cho cả ba trường hợp, không chỉ test JSON object thông thường.

## 11. AttributeConverter so với @JdbcTypeCode(JSON)

JPA `AttributeConverter<X, Y>` chuyển kiểu domain X thành kiểu basic Y và ngược lại:

```java
@Converter
public class SettingsConverter
        implements AttributeConverter<Settings, String> {

    @Override
    public String convertToDatabaseColumn(Settings value) {
        // Serialize Settings to JSON text.
        return value == null ? null : serialize(value);
    }

    @Override
    public Settings convertToEntityAttribute(String value) {
        // Deserialize JSON text to Settings.
        return value == null ? null : deserialize(value);
    }
}
```

Ví dụ này là skeleton; `serialize`/`deserialize` phải được triển khai bằng mapper thực tế và xử lý exception/null phù hợp.

So sánh:

| Tiêu chí | AttributeConverter sang String | Hibernate JSON JDBC mapping |
|---|---|---|
| Java type | Domain object | Map/POJO/JSON tree |
| JDBC representation | Thường là VARCHAR/CLOB | JSON JDBC type theo Hibernate/dialect |
| Database JSON operator/index | Có thể bị hạn chế nếu cột/driver xem là text | Phù hợp hơn với native JSON type |
| Portability | Converter JPA chuẩn, nhưng storage/query phụ thuộc DB | Hibernate-specific và database-dependent |
| Serialization | Do ứng dụng quản lý converter | Qua Hibernate JSON format mapper |

Nếu cột database thực sự là JSON/JSONB và cần JSON operator/index, ưu tiên mapping JSON của Hibernate khi dialect/driver hỗ trợ. Converter sang String có thể phù hợp nếu schema lưu text hoặc cần mapping portable ở tầng Java, nhưng phải xác nhận kiểu cột và binding thực tế.

Không áp dụng đồng thời converter và `@JdbcTypeCode(SqlTypes.JSON)` lên cùng thuộc tính nếu chưa hiểu precedence và mapping composition của Hibernate; cấu hình chồng chéo có thể làm kiểu JDBC không như mong muốn.

## 12. @JavaType, @JdbcTypeCode và custom type

Hibernate tách Java-side type handling và JDBC-side type handling:

- `@JavaType` chọn cách Hibernate hiểu, so sánh, copy và quản lý Java value.
- `@JdbcTypeCode` chọn JDBC type code dùng để bind/read.
- `@JdbcType` có thể chỉ định một JdbcType implementation cụ thể.
- `@Type` gắn custom Hibernate UserType.

Ví dụ dùng type code:

```java
@JdbcTypeCode(SqlTypes.JSON)
private Map<String, Object> payload;
```

Đây thường là lựa chọn đơn giản nhất cho JSON trong Hibernate 6.

Khi cần hành vi đặc biệt như serialization riêng, conversion tùy chỉnh, mutability plan hoặc JDBC binding riêng, có thể dùng custom JavaType/JdbcType hoặc UserType. Đừng viết custom type nếu built-in JSON support đáp ứng yêu cầu; custom type làm tăng trách nhiệm tương thích với Hibernate version, JDBC driver và schema.

## 13. Custom UserType trong Hibernate

Hibernate cung cấp extension point `UserType` để định nghĩa cách một Java value được đọc/ghi qua JDBC, so sánh, copy và cache. API đã thay đổi giữa Hibernate 5 và Hibernate 6.

Hibernate 6 dùng generic UserType và annotation `@Type` theo class:

```java
@Type(MyCustomType.class)
private CustomValue value;
```

Đây chỉ là cách gắn type; implementation `MyCustomType` phải thực hiện contract Hibernate 6 tương ứng, gồm JDBC mapping, equality/hash code, deep copy/mutability và null handling.

Hibernate 5 có API UserType khác và thường gặp cú pháp annotation cũ:

```java
@Type(type = "com.example.MyCustomType")
private CustomValue value;
```

Không copy code custom type Hibernate 5 vào Hibernate 6 mà không port API. Đọc đúng Javadoc/source của phiên bản Hibernate ORM trong dự án. Custom type phải được integration test trên provider/database thật, đặc biệt với bind null, dirty checking, second-level cache và schema validation.

## 14. Các kiểu đặc thù khác

### 14.1. UUID

UUID có thể được lưu bằng native UUID, binary hoặc character tùy database/dialect và cấu hình Hibernate.

```java
@Id
@GeneratedValue
@JdbcTypeCode(SqlTypes.UUID)
private UUID id;
```

Hibernate thường có hỗ trợ UUID mapping tích hợp; chỉ chỉ định type code khi cần làm rõ mapping hoặc phù hợp với schema. Xác nhận DDL thực tế và representation trong database. Nếu schema cũ lưu UUID dạng CHAR(36) hoặc BINARY(16), mapping phải tương thích với dữ liệu hiện hữu.

### 14.2. SQL ARRAY

Với database hỗ trợ ARRAY, Hibernate có thể map kiểu Java array hoặc collection phù hợp:

```java
@JdbcTypeCode(SqlTypes.ARRAY)
@Column(columnDefinition = "text[]")
private String[] tags;
```

Ví dụ này hướng tới database hỗ trợ SQL ARRAY như PostgreSQL. MySQL không có cùng native ARRAY column semantics. Không dùng DDL `text[]` trên database không hỗ trợ kiểu này.

### 14.3. Native enum

JPA chuẩn hỗ trợ:

```java
@Enumerated(EnumType.STRING)
private OrderStatus status;
```

Đây thường là VARCHAR/string representation, không nhất thiết là native enum type của database.

Hibernate có extension cho named/native enum theo dialect và version. Với PostgreSQL, mapping native enum có thể cần `SqlTypes.NAMED_ENUM` hoặc PostgreSQL enum JdbcType phù hợp phiên bản Hibernate, cùng `columnDefinition` khớp tên enum type trong schema. Hãy xác nhận hỗ trợ trong version cụ thể; `@Enumerated(EnumType.STRING)` không tự tạo PostgreSQL enum type.

### 14.4. Network và spatial types

Các kiểu như INET/CIDR hoặc GEOMETRY/GEOGRAPHY thường cần JDBC type/dialect hoặc thư viện chuyên dụng. Hibernate Spatial hỗ trợ một số spatial type/function; mapping chính xác phụ thuộc database và extension.

Không ép các kiểu này thành String nếu ứng dụng cần operator/index chuyên biệt của database. Ngược lại, nếu chỉ hiển thị giá trị và không query theo semantics đặc thù, kiểu đơn giản có thể đủ. Cân nhắc dependency và portability trước khi thêm extension.

## 15. Khi nào cần custom Dialect hoặc function registration?

Dialect mô tả khác biệt SQL, type và function của database cho Hibernate. Trong đa số trường hợp, built-in dialect hiện đại đã hỗ trợ các kiểu phổ biến; không nên tạo custom Dialect chỉ để đổi một column definition đơn lẻ.

Có thể cần extension khi:

- Database vendor/version có type hoặc function chưa được Hibernate nhận diện.
- Cần đăng ký SQL function để gọi qua HQL/Criteria.
- JDBC driver trả type code/vendor object cần binding riêng.
- Cần custom type registration dùng chung cho nhiều entity.

Tùy Hibernate version, extension API và cách đăng ký type/function thay đổi. Ưu tiên API được tài liệu phiên bản hiện tại hỗ trợ; không dựa vào internal class hoặc API deprecated. Giữ custom Dialect nhỏ và có test SQL generation.

## 16. Schema migration và validation

Với JSON và kiểu đặc thù, schema migration phải khớp mapping.

PostgreSQL migration:

```sql
alter table event
add column payload jsonb;

create index ix_event_payload_gin
on event using gin (payload);
```

Entity:

```java
@JdbcTypeCode(SqlTypes.JSON)
@Column(columnDefinition = "jsonb")
private Map<String, Object> payload;
```

Trong production, dùng Flyway/Liquibase để quản lý DDL. `spring.jpa.hibernate.ddl-auto=validate` có thể phát hiện một số khác biệt schema, nhưng không thay thế migration review hoặc xác nhận toàn bộ index/function/constraint.

Không dùng `ddl-auto=update` như công cụ migration production cho custom type, JSON index hoặc database-specific DDL. DDL generated bởi Hibernate có thể không tạo đúng mọi index/operator class hoặc constraint mà ứng dụng cần.

Khi thay kiểu `json` sang `jsonb`, hoặc đổi cấu trúc JSON, cần migration dữ liệu và kiểm tra các document cũ trước khi deploy code mới.

## 17. Query, dirty checking và PersistenceContext

JSON property là state của entity. Khi entity managed và JSON value thay đổi, Hibernate có thể đánh dấu entity dirty và ghi lại cột JSON trong flush. Với custom mutable object, behavior phụ thuộc JavaType/mutability plan và cách equality/copy được triển khai.

Nguyên tắc an toàn:

- Dùng immutable value object/record khi phù hợp.
- Thay object mới thay vì sửa sâu nested map nếu dirty detection không rõ.
- Viết integration test cho nested mutation và update.
- Kiểm tra SQL UPDATE để xem Hibernate có ghi lại toàn bộ JSON column không.
- Nếu dùng native JSON update, refresh/clear entity managed để tránh stale state.
- Không kỳ vọng JSON path update tự động chỉ vì property là Map hoặc POJO.

Second-level cache, optimistic locking và audit/version column cũng cần được xem xét nếu JSON là dữ liệu thay đổi thường xuyên.

## 18. Security và validation cho JSON

JSON là dữ liệu có cấu trúc nhưng vẫn là input không tin cậy nếu đến từ client hoặc hệ thống ngoài.

- Validate schema/domain rules trước khi persist.
- Giới hạn kích thước document và độ sâu lồng nhau.
- Không deserialize polymorphic class tùy ý từ type metadata không tin cậy.
- Không lưu secret/token nếu không có encryption/access control phù hợp.
- Tránh log toàn bộ JSON payload có dữ liệu cá nhân hoặc credential.
- Dùng parameter binding cho value; whitelist JSON path và SQL identifier động.
- Xác định rõ unknown field/version behavior khi schema thay đổi.

Nếu JSON document có cấu trúc nghiệp vụ ổn định, cân nhắc tách các field thường filter/join/sort thành cột quan hệ bình thường. JSON không nên trở thành nơi giấu toàn bộ dữ liệu quan hệ khiến constraint, indexing và query khó kiểm soát.

## 19. Kiểm thử trên database thật

H2 hoặc mock không thể bảo đảm mô phỏng đúng JSON type, operator, index, enum native hoặc driver behavior của PostgreSQL/MySQL.

Dùng Testcontainers hoặc database test cùng engine/version gần production để xác minh:

1. Schema có cột JSON/JSONB đúng kiểu.
2. Persist POJO/Map/JsonNode tạo document đúng, không double-encode.
3. Read lại document giữ đúng kiểu, null và nested value.
4. SQL NULL khác JSON null và missing key theo mong đợi.
5. JSON operator/function trả đúng kết quả.
6. Index được dùng theo execution plan cho query quan trọng.
7. Nested mutation được dirty checking đúng.
8. Native JSON update đồng bộ PersistenceContext.
9. Custom UserType xử lý null, equality, deep copy và cache.
10. Migration nâng cấp document cũ chạy an toàn.

Testcontainers không tự đảm bảo production tương đương nếu version image/driver khác. Ghi rõ database image, driver và Hibernate version trong build/test setup.

## 20. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Hibernate bind JSON như VARCHAR | Chỉ khai báo columnDefinition hoặc thiếu JSON JDBC mapping | Dùng `@JdbcTypeCode(SqlTypes.JSON)` và kiểm tra dialect |
| Schema có JSONB nhưng app lỗi type | DDL và Hibernate/driver type không khớp | Đồng bộ column type, dialect và migration |
| JSON bị double-encode | Lưu JSON string như một JSON string value | Map POJO/Map/JsonNode trực tiếp bằng JSON mapping |
| Không deserialize được record/POJO | JSON mapper/dependency/constructor config không phù hợp | Kiểm tra Jackson/JSON-B mapper và round-trip test |
| JSON operator không chạy trên DB khác | Native function/operator vendor-specific | Viết query theo database hoặc dùng abstraction riêng |
| Query JSON chậm | Thiếu GIN/expression/generated-column index | Thiết kế index theo operator/path và EXPLAIN |
| Thay nested Map nhưng không UPDATE | Mutability/equality/dirty checking không như giả định | Thay object mới và test SQL UPDATE |
| JPA đọc JSON cũ sau native update | PersistenceContext stale | Refresh entity hoặc clear phù hợp |
| SQL NULL và JSON null bị nhầm | Khác semantics của column/path/function | Test riêng missing key, JSON null và SQL NULL |
| Enum native lỗi binding | Hibernate type/dialect không khớp enum database | Dùng mapping native enum đúng version hoặc STRING |
| Custom UserType không compile sau upgrade | API Hibernate 5/6 khác nhau | Port theo UserType API của version hiện tại |
| H2 test pass nhưng production fail | Khác JSON type, function, driver hoặc dialect | Integration test bằng Testcontainers/engine thật |

## 21. Quy trình chọn mapping

1. Xác định database engine/version và JDBC driver.
2. Kiểm tra database có native JSON/ARRAY/UUID/enum type không.
3. Chọn Java representation: POJO/record, Map hoặc JSON tree.
4. Dùng Hibernate built-in type như `@JdbcTypeCode(SqlTypes.JSON)` khi được hỗ trợ.
5. Khai báo DDL đúng trong migration; chỉ dùng `columnDefinition` như DDL hint khi phù hợp.
6. Xác định nhu cầu query JSON, function và index.
7. Chọn native SQL/dialect function cho query vendor-specific.
8. Chỉ viết AttributeConverter/UserType/custom JdbcType khi built-in mapping không đáp ứng.
9. Xác định dirty checking, mutability, cache và update semantics.
10. Test round-trip, NULL, nested mutation, native DML và migration trên database mục tiêu.

## 22. Checklist trước khi đưa JSON/custom type vào production

- [ ] Hibernate version và dialect có hỗ trợ type code cần dùng?
- [ ] Java type có thể serialize/deserialize bằng JSON format mapper?
- [ ] Đã dùng `@JdbcTypeCode(SqlTypes.JSON)` cho Hibernate JSON mapping?
- [ ] `columnDefinition` có khớp kiểu cột thật và migration?
- [ ] Đã phân biệt PostgreSQL json/jsonb và MySQL JSON?
- [ ] Có query JSON vendor-specific nào cần tách riêng?
- [ ] Index JSON có dựa trên workload và EXPLAIN?
- [ ] SQL NULL, JSON null và missing key đã có semantics?
- [ ] Nested mutation được dirty checking đúng?
- [ ] Native DML có refresh/clear PersistenceContext?
- [ ] Custom type có tương thích đúng Hibernate major version?
- [ ] Có kiểm thử bằng đúng database/driver gần production?
- [ ] JSON payload có validation, size limit và security policy?

## 23. Kết luận

Hibernate 6 cung cấp JSON mapping tích hợp qua `@JdbcTypeCode(SqlTypes.JSON)`, giúp ánh xạ Map, POJO/record hoặc JSON tree sang kiểu JSON mà dialect/database hỗ trợ. `columnDefinition` mô tả DDL, còn JDBC type và JSON format mapper quyết định cách bind/serialize; hai trách nhiệm này không thể thay thế lẫn nhau.

Kiểu database đặc thù như UUID, ARRAY, native enum, network hoặc spatial cần mapping đúng dialect/driver và có thể cần Hibernate extension. Chỉ viết custom UserType/JdbcType hoặc Dialect khi built-in support không đủ, vì extension gắn chặt với Hibernate version.

Cuối cùng, JSON query/index, SQL NULL versus JSON null, dirty checking và native DML đều phụ thuộc database/provider. Quản lý schema bằng migration, kiểm thử trên đúng engine, đo execution plan và giữ PersistenceContext đồng bộ khi chạy native update. Cách đó giúp tận dụng JSON/custom types mà vẫn kiểm soát được tính đúng đắn và khả năng vận hành.

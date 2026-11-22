# @JdbcTypeCode cùng cơ chế chỉ định cách biểu diễn JDBC

Trong Hibernate ORM, một thuộc tính Java không nhất thiết được lưu xuống cơ sở dữ liệu bằng một kiểu SQL trùng với tên kiểu Java. Ví dụ, `UUID` có thể đi qua JDBC ở dạng native UUID hoặc dạng ký tự; một `Map<String, Object>` có thể được biểu diễn bằng JSON; một mảng Java có thể dùng SQL ARRAY trên những hệ quản trị hỗ trợ.

Từ Hibernate 6, annotation **`@JdbcTypeCode`** là một công cụ để chỉ rõ **loại biểu diễn JDBC** mà Hibernate nên dùng khi ghi và đọc một thuộc tính. Annotation này không đứng riêng lẻ: Hibernate còn phải biết kiểu Java, cách chuyển đổi giá trị, dialect và kiểu cột thực tế trong database.

Bài học giải thích cơ chế lựa chọn JDBC representation, cách dùng `@JdbcTypeCode`, các ví dụ với JSON, UUID, ARRAY và kiểu ký tự, cũng như cách phân biệt annotation này với các cơ chế ánh xạ khác.

## 1. Tại sao cần chỉ định biểu diễn JDBC?

Xét một entity có field:

~~~java
private UUID externalId;
~~~

Trong code nghiệp vụ, `externalId` là `java.util.UUID`. Khi Hibernate lưu entity, nó cần làm nhiều việc:

1. Hiểu kiểu Java và giá trị của field.
2. Xác định cách bind giá trị vào tham số SQL của `PreparedStatement`.
3. Xác định cách đọc giá trị từ `ResultSet` khi tải entity.
4. Dùng thông tin về dialect và metadata ánh xạ để chọn kiểu cột phù hợp nếu Hibernate sinh DDL.
5. Bảo đảm cách bind/extract JDBC tương thích schema database đã có.

Có thể hình dung như sau:

~~~mermaid
flowchart TD
    A["Entity field<br/>UUID / String / Map / byte[]"] --> B["Hibernate JavaType"]
    B --> C["Hibernate JdbcType"]
    C --> D["JDBC PreparedStatement / ResultSet"]
    D --> E["Database column"]
    F["Dialect + mapping metadata"] -.-> C
    F -.-> E
~~~

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Kiểu Java | Giá trị mà ứng dụng thao tác | `UUID`, `String`, `Map<String, Object>` |
| Hibernate `JavaType` | Mô tả semantics của giá trị Java, hỗ trợ chuyển đổi, so sánh và xử lý tính khả biến | Descriptor cho `String` hoặc `UUID` |
| Hibernate `JdbcType` | Quy định cách bind/extract giá trị qua JDBC | VARCHAR, CHAR, JSON, UUID |
| `SqlTypes` | Tập mã kiểu dùng để tham chiếu các loại JDBC/SQL trong Hibernate | `SqlTypes.JSON`, `SqlTypes.CHAR` |
| `Dialect` | Đóng gói khác biệt giữa hệ quản trị database | PostgreSQL, MySQL, Oracle… |
| SQL column type | Kiểu vật lý của cột trong schema | `jsonb`, `uuid`, `varchar(36)` |

**Điểm quan trọng:** kiểu Java, JDBC type và kiểu cột SQL là những khái niệm liên quan nhưng khác nhau. `@JdbcTypeCode` giúp định hướng tầng JDBC; nó không tự quyết định mọi phần còn lại.

## 2. Cú pháp @JdbcTypeCode trong Hibernate 6

Import:

~~~java
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;
~~~

Ví dụ:

~~~java
@JdbcTypeCode(SqlTypes.JSON)
private Map<String, Object> settings;
~~~

`@JdbcTypeCode` nhận một mã số nguyên chỉ định JDBC type, thông thường truyền bằng một hằng số trong `org.hibernate.type.SqlTypes` để dễ đọc.

Hibernate sẽ sử dụng mã này để tìm `JdbcType` phù hợp trong hệ thống type registry. Từ đó, cách bind tham số, đọc kết quả và một phần lựa chọn SQL type của dialect được điều chỉnh theo mapping.

`SqlTypes` chứa mã kiểu tương ứng với nhiều hằng số trong `java.sql.Types` và một số mã mở rộng của Hibernate như `JSON` hay `UUID`. Vì thế, `SqlTypes.JSON` là **mã kiểu dùng trong hệ thống Hibernate**, không phải lời khẳng định rằng mọi JDBC driver đều có cùng một loại SQL JSON native.

### 2.1. Khi nào nên khai báo?

Thường nên khai báo khi có một yêu cầu cụ thể:

- Một thuộc tính cần được lưu thành JSON thay vì ánh xạ theo cách mặc định.
- UUID phải lưu bằng CHAR để khớp schema đã tồn tại.
- Muốn chỉ định kiểu JDBC ARRAY cho một thuộc tính phù hợp.
- Cần định hướng việc lưu text hoặc binary ở một dạng JDBC cụ thể.
- Mapping mặc định của Hibernate không khớp với kiểu cột hiện có.

Nếu một `String`, `Integer` hoặc `LocalDate` đang được Hibernate ánh xạ đúng và không có yêu cầu đặc biệt, **không cần thêm `@JdbcTypeCode` cho mọi field**.

### 2.2. Giới hạn của annotation

`@JdbcTypeCode`:

- Không tự thêm hoặc xóa cột trong một database đã tồn tại.
- Không tự chạy migration dữ liệu.
- Không đảm bảo bất kỳ object Java nào cũng có thể chuyển sang loại JDBC được chọn.
- Không thay thế `AttributeConverter` khi domain object cần một phép biến đổi riêng.
- Không tự tạo index, foreign key hoặc quan hệ ORM.
- Là annotation riêng của Hibernate, không thuộc JPA chuẩn.

Chọn mã JDBC chỉ là một quyết định trong toàn bộ quá trình mapping.

## 3. Ví dụ JSON: lưu cấu hình động vào một cột

Một trường hợp điển hình là cột chứa cấu hình linh hoạt:

~~~json
{
  "theme": "dark",
  "notifications": true,
  "maxItems": 25
}
~~~

Nếu giá trị này được sử dụng như một tài liệu nhỏ đi cùng entity, JSON có thể thuận tiện hơn tạo nhiều cột riêng.

### 3.1. Entity Hibernate 6

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.util.LinkedHashMap;
import java.util.Map;

@Entity
@Table(name = "document_records")
public class DocumentRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "attributes", nullable = false)
    private Map<String, Object> attributes = new LinkedHashMap<>();

    protected DocumentRecord() {
        // Constructor dành cho JPA.
    }

    public DocumentRecord(Map<String, Object> attributes) {
        this.attributes = new LinkedHashMap<>(attributes);
    }

    public Long getId() {
        return id;
    }

    public Map<String, Object> getAttributes() {
        return attributes;
    }

    public void setAttributes(Map<String, Object> attributes) {
        this.attributes = new LinkedHashMap<>(attributes);
    }
}
~~~

`@Id` đặt trên field nên entity dùng **field access** theo mặc định; `@JdbcTypeCode` cũng được đặt trên field cần ánh xạ.

Với PostgreSQL và dialect tương thích, schema có thể tạo bằng migration như sau:

~~~sql
CREATE TABLE document_records (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    attributes JSONB NOT NULL
);
~~~

Kiểu `JSONB` là kiểu của PostgreSQL. Database khác có thể dùng kiểu cột khác hoặc cần cấu hình khác. `@JdbcTypeCode(SqlTypes.JSON)` không có nghĩa mọi database đều đặt tên cột là `jsonb`.

### 3.2. Persist và load JSON

Trong một transaction hợp lệ:

~~~java
DocumentRecord record = new DocumentRecord(Map.of(
    "theme", "dark",
    "notifications", true,
    "maxItems", 25
));

em.persist(record);
em.flush();

Long id = record.getId();

em.clear(); // Lần tìm tiếp theo phải nạp lại từ database.
DocumentRecord loaded = em.find(DocumentRecord.class, id);

System.out.println(loaded.getAttributes().get("theme")); // dark
~~~

Ứng dụng nhìn thấy `Map`, trong khi Hibernate sử dụng JSON mapper và `JdbcType` tương ứng để chuyển sang/from JDBC representation.

Hibernate **không tạo một cột riêng cho mỗi key** trong Map, cũng không tự biến các phần tử JSON thành entity có quan hệ ORM.

### 3.3. Các điều kiện cần có

Để JSON mapping hoạt động ổn định, cần bảo đảm:

1. Hibernate đủ phiên bản hỗ trợ `@JdbcTypeCode(SqlTypes.JSON)`, thường là Hibernate 6.
2. Có thư viện JSON tương thích để Hibernate serialize/deserialize, chẳng hạn Jackson hoặc JSON-B implementation phù hợp.
3. Dialect được cấu hình đúng với database.
4. Cột SQL thực tế có kiểu tương thích.
5. Kiểu Java được dùng (`Map` hoặc POJO) có thể chuyển đổi qua JSON mapper.

Trong ứng dụng Spring Boot, Jackson có thể đã có trên classpath nhờ một starter khác, nhưng **không nên mặc định rằng starter JPA tự cung cấp đầy đủ JSON mapper cần thiết**.

### 3.4. JSON không tự hỗ trợ mọi truy vấn JPQL

Ví dụ PostgreSQL có cú pháp truy vấn key JSON:

~~~sql
SELECT id
FROM document_records
WHERE attributes ->> 'theme' = 'dark';
~~~

Đây là **native SQL riêng của PostgreSQL**. `@JdbcTypeCode(SqlTypes.JSON)` không tự làm Hibernate hiểu tất cả toán tử JSON của mọi database ở cấp JPQL. Có thể cần native query, hàm SQL/dialect hỗ trợ hoặc phương án mapping/query khác.

Nếu cần lọc, join và đặt constraint độc lập cho các phần tử JSON, hãy cân nhắc mô hình quan hệ thay vì lưu tất cả trong một cột.

### 3.5. JSON khả biến và dirty checking

Với cấu trúc `Map` hoặc POJO khả biến, cần quan tâm cách Hibernate nhận diện thay đổi và sao chép snapshot. Hành vi có thể phụ thuộc JavaType, mutability plan, JSON mapper và cách gán giá trị.

Ví dụ:

~~~java
DocumentRecord record = em.find(DocumentRecord.class, id);
record.getAttributes().put("theme", "light");
~~~

Không nên giả định mọi thay đổi sâu trong một Map hoặc List lồng nhau đều được phát hiện nhất quán trên mọi mapping. Với dữ liệu quan trọng, có thể tạo giá trị mới rồi gán qua setter:

~~~java
DocumentRecord record = em.find(DocumentRecord.class, id);

Map<String, Object> updated =
    new LinkedHashMap<>(record.getAttributes());

updated.put("theme", "light");
record.setAttributes(updated);
~~~

Cần kiểm tra hành vi lưu thực tế của mapping và cơ chế khóa phiên bản khi nhiều transaction có thể cùng sửa một tài liệu JSON. `@Version` có thể hữu ích để tránh ghi đè không mong muốn.

## 4. UUID: giữ Java UUID nhưng chọn biểu diễn JDBC

UUID cho thấy rõ sự khác nhau giữa kiểu Java và kiểu lưu.

### 4.1. Để Hibernate tự lựa chọn

~~~java
@Id
private UUID id;
~~~

Hibernate có thể sử dụng mapping UUID phù hợp với dialect. Ví dụ PostgreSQL có kiểu cột `uuid` native. Khi thiết kế schema mới và database hỗ trợ tốt loại này, mặc định thường đã hợp lý.

### 4.2. UUID lưu dạng CHAR

Giả sử schema cũ có cột `external_id CHAR(36)`. Có thể chỉ định:

~~~java
@JdbcTypeCode(SqlTypes.CHAR)
@Column(name = "external_id", length = 36)
private UUID externalId;
~~~

Code Java vẫn nhận và gán `UUID`:

~~~java
UUID value = entity.getExternalId();
~~~

Nhưng Hibernate được hướng về cách bind/extract phù hợp với biểu diễn ký tự. Cần kiểm tra khả năng chuyển đổi của Hibernate, JDBC driver, dữ liệu cũ, độ dài cột và DDL cuối cùng trước khi áp dụng.

Không nên giả định một cột chứa bất kỳ chuỗi UUID tùy ý nào đều được đọc thành `UUID` hợp lệ.

### 4.3. UUID native

Hibernate có mã kiểu riêng:

~~~java
@JdbcTypeCode(SqlTypes.UUID)
private UUID trackingId;
~~~

Mã này thể hiện chủ đích dùng JDBC representation UUID. Kiểu SQL thực tế vẫn phụ thuộc dialect: **không phải mọi database đều có kiểu cột tên `UUID`**.

### 4.4. UUID ở dạng binary

Một số hệ thống dùng biểu diễn binary 16 byte nhằm tiết kiệm dung lượng so với CHAR(36). Đó là một quyết định thiết kế khác, yêu cầu mapping/driver/schema và migration nhất quán. Không nên chỉ đổi mã JDBC mà không kiểm tra thứ tự byte, giá trị lịch sử và những service khác đang dùng dữ liệu.

## 5. ARRAY: ánh xạ mảng Java qua JDBC

Một số hệ quản trị hỗ trợ SQL ARRAY. Ví dụ với PostgreSQL và kiểu phần tử phù hợp:

~~~java
@JdbcTypeCode(SqlTypes.ARRAY)
@Column(name = "tags")
private String[] tags;
~~~

Một schema có thể sử dụng:

~~~sql
CREATE TABLE article_tags (
    id BIGINT PRIMARY KEY,
    tags TEXT[]
);
~~~

`SqlTypes.ARRAY` chỉ định loại biểu diễn JDBC mong muốn. Tuy nhiên, khả năng map `String[]`, cách driver tạo SQL array và hành vi trên database khác phụ thuộc **Hibernate version, JDBC driver, dialect và loại phần tử**. Đừng coi ví dụ này là bảo đảm portability cho mọi hệ quản trị.

### ARRAY, JSON hay bảng quan hệ?

| Dạng dữ liệu | Lựa chọn cần cân nhắc | Đánh đổi |
| --- | --- | --- |
| Một nhóm giá trị cơ bản, nhỏ, đi cùng record | ARRAY nếu DB hỗ trợ tốt | Phụ thuộc DB/dialect; khả năng query mảng có đặc thù |
| Cấu trúc linh hoạt, có đối tượng lồng nhau | JSON | Index, truy vấn và cập nhật theo key tùy database |
| Phần tử có ID, vòng đời, quan hệ hoặc cập nhật độc lập | Bảng quan hệ | Schema nhiều thành phần hơn nhưng ràng buộc rõ hơn |

`@JdbcTypeCode` không thay thế mô hình quan hệ `@OneToMany` hoặc bảng liên kết khi các phần tử có nghiệp vụ độc lập.

## 6. String và dữ liệu binary: điều chỉnh JDBC type

### 6.1. VARCHAR

Với thuộc tính chuỗi thông dụng:

~~~java
@JdbcTypeCode(SqlTypes.VARCHAR)
@Column(name = "title", length = 200)
private String title;
~~~

`SqlTypes.VARCHAR` nói về JDBC representation; `@Column(length = 200)` cung cấp metadata chiều dài cho schema và quá trình sinh DDL. Chúng không có cùng vai trò.

Khi Hibernate đã tự map `String` thành VARCHAR phù hợp, annotation `@JdbcTypeCode(SqlTypes.VARCHAR)` có thể không mang thêm giá trị.

### 6.2. LONGVARCHAR

~~~java
@JdbcTypeCode(SqlTypes.LONGVARCHAR)
@Column(name = "description")
private String description;
~~~

Đây là cách định hướng JDBC type cho chuỗi dài. Dialect quyết định SQL type vật lý tương ứng, ví dụ kiểu text dài của database. `LONGVARCHAR` không nhất thiết có cùng ngữ nghĩa với CLOB; nếu muốn lưu large object, phải hiểu thêm `@Lob` và cách driver/database xử lý LOB.

### 6.3. VARBINARY

~~~java
@JdbcTypeCode(SqlTypes.VARBINARY)
@Column(name = "checksum_bytes")
private byte[] checksum;
~~~

Field Java là `byte[]`, còn representation JDBC là binary. Nếu lưu tệp lớn hoặc dữ liệu cần streaming, hãy cân nhắc BLOB hoặc lưu trữ đối tượng chuyên dụng; đừng mặc định VARBINARY phù hợp mọi kích thước.

## 7. So sánh với các cơ chế ánh xạ liên quan

| Cơ chế | Mục tiêu chính | Khi nào dùng |
| --- | --- | --- |
| `@JdbcTypeCode(SqlTypes.X)` | Chọn một JDBC type bằng mã đăng ký | JSON, UUID, CHAR, ARRAY, binary… |
| `@JdbcType(SomeJdbcType.class)` | Chỉ rõ lớp implementation `JdbcType` | Cần một JDBC type chuyên biệt |
| `@JavaType(SomeJavaType.class)` | Chỉ rõ descriptor biểu diễn Java | Cần thay đổi semantics/behavior xử lý giá trị Java |
| `@Type(SomeUserType.class)` | Dùng custom Hibernate type | Mapping đặc thù mà mapping thường chưa hỗ trợ |
| `@Convert(converter = ...)` | Biến đổi domain Java value sang relational Java value | Value object cần chuyển đổi |
| `@Column(columnDefinition = "...")` | Chỉ rõ khai báo cột khi tạo DDL | SQL column definition phụ thuộc DB |
| `@Enumerated` | Chỉ cách lưu enum theo tên hoặc ordinal | Entity có enum |
| `@Lob` | Mô tả large object trong JPA | BLOB/CLOB theo nhu cầu |

### 7.1. @JdbcTypeCode và @JdbcType

Với:

~~~java
@JdbcTypeCode(SqlTypes.JSON)
private Map<String, Object> settings;
~~~

bạn nói: *hãy chọn JdbcType đã đăng ký cho mã JSON*. Ngược lại, `@JdbcType` cho phép tham chiếu trực tiếp tới một implementation `JdbcType` cụ thể.

Thông thường, nếu chỉ muốn lưu JSON trong một database mà Hibernate hỗ trợ, hãy bắt đầu bằng `@JdbcTypeCode(SqlTypes.JSON)`, chưa cần xây custom `JdbcType`.

### 7.2. @JavaType giải quyết một phần khác

`JavaType` liên quan việc Hibernate hiểu và xử lý giá trị Java, chẳng hạn chuyển đổi, so sánh hay mutability. Nếu một custom domain value không có descriptor thích hợp hoặc quá trình so sánh/dirty checking không đúng, chỉ chọn JDBC type có thể chưa đủ.

### 7.3. AttributeConverter biến đổi giá trị domain

Ví dụ value object:

~~~java
public record ProductCode(String value) {}
~~~

Có thể dùng JPA `AttributeConverter<ProductCode, String>`:

~~~java
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter
public class ProductCodeConverter
        implements AttributeConverter<ProductCode, String> {

    @Override
    public String convertToDatabaseColumn(ProductCode code) {
        return code == null ? null : code.value();
    }

    @Override
    public ProductCode convertToEntityAttribute(String value) {
        return value == null ? null : new ProductCode(value);
    }
}
~~~

Entity:

~~~java
@Convert(converter = ProductCodeConverter.class)
@Column(name = "product_code", length = 30)
private ProductCode code;
~~~

Ở đây `@Convert` quy định phép biến đổi từ `ProductCode` sang `String`. `@JdbcTypeCode` thì định hướng cách biểu diễn JDBC của giá trị quan hệ. Hai cơ chế có thể tương tác, nhưng không nên gắn đồng thời nhiều annotation tùy ý mà không xác định type mapping cuối cùng.

### 7.4. @Column(columnDefinition) chỉ định SQL DDL, không tự làm JSON serialization

Một cấu hình dễ gây nhầm:

~~~java
@Column(columnDefinition = "jsonb")
private Map<String, Object> attributes;
~~~

`columnDefinition` giúp chỉ rõ SQL column declaration cho quá trình sinh DDL. Nó **không bảo đảm Hibernate biết serialize Map, chọn JdbcType JSON và bind tham số phù hợp**.

Với Hibernate 6, cách thể hiện rõ ý định mapping JSON thường là:

~~~java
@JdbcTypeCode(SqlTypes.JSON)
@Column(name = "attributes")
private Map<String, Object> attributes;
~~~

Nếu migration database cần cột PostgreSQL `jsonb`, hãy tạo cột bằng migration thích hợp. Dùng `columnDefinition` khi cần, đồng thời biết rằng nó làm mapping phụ thuộc vào cú pháp database.

### 7.5. Enum cần xác định semantics, không chỉ JDBC type

Ví dụ:

~~~java
@Enumerated(EnumType.STRING)
private OrderStatus status;
~~~

`@Enumerated(EnumType.STRING)` nói rằng enum được ánh xạ theo tên thay vì ordinal. Hibernate và dialect có thể tiếp tục chọn loại JDBC/SQL phù hợp, kể cả các kiểu enum riêng trong một số trường hợp.

Việc tự gắn `@JdbcTypeCode(SqlTypes.VARCHAR)` **không thay thế ý nghĩa nghiệp vụ** của `@Enumerated`.

## 8. Đặt @JdbcTypeCode đúng theo access strategy

Hibernate/JPA hỗ trợ FIELD access và PROPERTY access:

- **FIELD:** provider đọc/ghi trực tiếp field; annotation mapping thường nằm trên field.
- **PROPERTY:** provider đọc/ghi bằng getter/setter; annotation mapping thường nằm trên getter.

Vị trí `@Id` hoặc `@EmbeddedId` thường quyết định access mặc định, trừ khi có `@Access` rõ ràng.

### 8.1. Field access

~~~java
@Entity
public class UserPreferences {

    @Id
    private Long id;

    @JdbcTypeCode(SqlTypes.JSON)
    private Map<String, Object> preferences;
}
~~~

`@Id` trên field nên `@JdbcTypeCode` cũng được gắn với field cần ánh xạ.

### 8.2. Property access

~~~java
@Entity
public class UserPreferences {

    private Long id;
    private Map<String, Object> preferences;

    @Id
    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    @JdbcTypeCode(SqlTypes.JSON)
    public Map<String, Object> getPreferences() {
        return preferences;
    }

    public void setPreferences(Map<String, Object> preferences) {
        this.preferences = preferences;
    }
}
~~~

Khi `@Id` trên getter, nên đặt `@JdbcTypeCode` trên getter tương ứng. Nếu trộn annotation field/getter mà không hiểu access strategy, Hibernate có thể không áp dụng override như mong muốn.

## 9. Dialect và SQL type thực tế

Cùng một `SqlTypes` code có thể ứng với nhiều kiểu SQL vật lý khác nhau.

| Ý định | Java type | JDBC code thường dùng | SQL column type có thể gặp |
| --- | --- | --- | --- |
| Chuỗi thông thường | `String` | `SqlTypes.VARCHAR` | `varchar(n)` hoặc kiểu tương đương |
| Chuỗi dài | `String` | `SqlTypes.LONGVARCHAR` | `text` hoặc kiểu chuỗi dài |
| UUID native | `UUID` | `SqlTypes.UUID` | PostgreSQL `uuid` hoặc biểu diễn khác |
| UUID ký tự | `UUID` | `SqlTypes.CHAR` | `char(36)` hoặc kiểu tương thích |
| JSON | `Map` hoặc POJO phù hợp | `SqlTypes.JSON` | PostgreSQL `jsonb`, kiểu JSON khác |
| SQL mảng | `String[]` | `SqlTypes.ARRAY` | ARRAY nếu DB và driver hỗ trợ |
| Binary | `byte[]` | `SqlTypes.VARBINARY` | `varbinary`, `bytea` hoặc tương đương |

Cột cuối là ví dụ minh họa, **không phải cam kết DDL chính xác trên mọi hệ quản trị**.

### 9.1. Kiểu cột đang tồn tại vẫn có ý nghĩa quyết định

Nếu database đã có cột `VARCHAR` nhưng Hibernate định bind giá trị như JSON native, câu SQL có thể lỗi kiểu. Ngược lại, nếu database có cột `jsonb` nhưng Hibernate chỉ bind như chuỗi thông thường, driver/database cũng có thể từ chối hoặc cần cast.

Vì vậy hãy xác nhận cùng lúc:

1. Java field type và annotation.
2. JDBC type được Hibernate sử dụng.
3. SQL column type đang có.
4. Dialect và JDBC driver thực tế.
5. Kiểu dữ liệu lịch sử trong bảng.

### 9.2. Migration và validation

Trong dự án dùng migration, schema cần được thay đổi độc lập với entity. Với Spring Boot, có thể bật kiểm tra:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
~~~

`validate` đối chiếu mapping với schema theo khả năng của Hibernate/dialect/driver; nó không tạo hoặc thay đổi cột. Đổi từ VARCHAR sang JSON cần migration dữ liệu tương thích, không chỉ sửa annotation Java.

Việc validate thành công cũng không tự chứng minh dữ liệu cũ đáp ứng mọi quy tắc nghiệp vụ hoặc các câu query đều hoạt động như mong muốn.

## 10. Cấu hình ứng dụng Spring Boot dùng JSON mapping

Ví dụ dependencies Gradle trong dự án dùng Hibernate 6 qua Spring Boot phiên bản tương thích:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'com.fasterxml.jackson.core:jackson-databind'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

Trong dự án dùng dependency management đúng cách, phiên bản thư viện được quản lý đồng bộ. Ví dụ cấu hình kết nối:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/shop
    username: shop_app
    password: ${APP_DB_PASSWORD}
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Thông tin này chỉ minh họa môi trường phát triển. Mật khẩu thực tế nên được quản lý qua secret của hạ tầng, không commit trực tiếp vào mã nguồn.

Ví dụ repository và service dùng lại entity `DocumentRecord` ở phần trước:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface DocumentRecordRepository
        extends JpaRepository<DocumentRecord, Long> {
}
~~~

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.Map;

@Service
public class DocumentService {
    private final DocumentRecordRepository repository;

    public DocumentService(DocumentRecordRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Long create() {
        DocumentRecord record = new DocumentRecord(Map.of(
            "theme", "dark",
            "maxItems", 25
        ));

        return repository.save(record).getId();
    }
}
~~~

Business code không phải tự tạo JSON string. Khi persistence mapping, JSON mapper, dialect và cột SQL tương thích, Hibernate xử lý chuyển đổi qua JDBC. Ví dụ vẫn cần schema, transaction và dependency thực tế được cấu hình đầy đủ.

## 11. Cách chẩn đoán lỗi JDBC type mapping

Lỗi có thể phát sinh ở một trong nhiều tầng:

| Dấu hiệu | Hướng kiểm tra |
| --- | --- |
| Hibernate không biết map một Java class | JavaType, converter, custom type hoặc annotation cần thiết |
| Không serialize được object sang JSON | JSON library, kiểu object, cấu trúc dữ liệu, JSON mapper |
| Insert/update bị database từ chối kiểu | JdbcType binding, SQL column type, dialect, driver |
| Load entity thất bại khi đọc giá trị | JDBC extraction, dữ liệu cũ không đúng định dạng, conversion |
| Không nhận ra thay đổi Map/POJO | Dirty checking, mutability, cách cập nhật giá trị |
| Hệ thống chạy trên DB khác thì lỗi | Cú pháp SQL, type support và dialect portability |
| Hibernate validate báo mismatch | Schema vật lý khác mapping entity hoặc metadata driver |

### 11.1. Quan sát SQL và binding

Trong Hibernate 6, log cấu hình minh họa với Spring Boot:

~~~yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
~~~

`org.hibernate.SQL` có thể hiển thị SQL, còn logger bind có thể cung cấp thông tin về JDBC parameter binding. Chỉ bật logging chi tiết khi cần, trong môi trường phù hợp, vì tham số bind có thể chứa dữ liệu nhạy cảm.

Các bước xác định nguồn lỗi:

1. Xác minh annotation nằm đúng vị trí FIELD/PROPERTY.
2. Kiểm tra phiên bản Hibernate và dialect đang chạy.
3. Quan sát kiểu cột thực tế trong database.
4. Xác nhận driver và thư viện chuyển đổi JSON hoặc các loại dữ liệu đặc biệt đã có.
5. Xác định lỗi xảy ra khi serialize, bind, SQL execute hay extract.
6. Đọc lại entity trong persistence context mới để phân biệt dữ liệu trong RAM với giá trị được lưu.

### 11.2. Null và dữ liệu đặc biệt

Với các kiểu JSON/ARRAY/binary, cần phân biệt:

- SQL `NULL` và nội dung JSON có giá trị `null`.
- JSON object rỗng `{}` và giá trị không tồn tại.
- SQL ARRAY rỗng và SQL `NULL`.
- Chuỗi UUID hợp lệ và dữ liệu cũ sai định dạng.
- Chuỗi dài hoặc binary vượt khả năng cột.

`@JdbcTypeCode` giúp chỉ định cách biểu diễn, nhưng không thay thế validation và các quy tắc dữ liệu ở tầng nghiệp vụ/database.

## 12. Những nhầm lẫn thường gặp

| Nhận định | Cách hiểu chính xác |
| --- | --- |
| “`@JdbcTypeCode` tự tạo kiểu cột giống hệt mã SqlTypes.” | Nó định hướng JDBC type; dialect/DDL/schema có vai trò riêng. |
| “Chỉ `@Column(columnDefinition = "jsonb")` là đủ để lưu Map.” | DDL declaration không tự thiết lập JSON serialization/JDBC binding. |
| “Có JSON mapping thì key JSON tự trở thành thuộc tính JPQL.” | JSON là một giá trị; query theo key phụ thuộc khả năng SQL/dialect. |
| “Bất kỳ Java type nào cũng dùng được với mọi `SqlTypes`.” | Cần khả năng chuyển đổi giữa JavaType và JdbcType. |
| “`SqlTypes.UUID` luôn tạo cột UUID native.” | Kiểu cột phụ thuộc database/dialect. |
| “Sửa trực tiếp Map lồng nhau chắc chắn được dirty-check.” | Hành vi phụ thuộc mapping/mutability; cần thiết kế cập nhật có chủ đích. |
| “`@JdbcTypeCode` là annotation JPA chuẩn.” | Đây là extension của Hibernate 6. |
| “`@JdbcTypeCode` và `@Convert` giống nhau.” | Converter biến đổi domain value; JdbcType chọn cách bind/extract JDBC. |
| “Đổi annotation đồng nghĩa database đã migration.” | Schema và dữ liệu lịch sử phải được migration riêng. |
| “Cột JSON có quan hệ ORM giống `@OneToMany`.” | JSON không tự tạo foreign key, cascade hay entity identity cho phần tử. |

## 13. Quy trình lựa chọn cách biểu diễn JDBC

Khi gặp một field cần mapping, hãy đi theo thứ tự:

1. **Xác định kiểu Java theo nghiệp vụ.** Giá trị cần là `UUID`, `Map`, `String` hay value object?
2. **Xác định schema đang có hoặc định thiết kế.** Cột SQL cần là JSON, CHAR, UUID native, ARRAY, v.v.?
3. **Thử mapping mặc định trước.** Nếu Hibernate đã bind/extract đúng và schema tương thích, không cần override.
4. **Chỉ định JDBC representation khi cần.** Dùng `@JdbcTypeCode(SqlTypes.X)` cho trường hợp có mã kiểu phù hợp.
5. **Xác định có cần conversion riêng.** Nếu giá trị domain phải chuyển sang relational Java type khác, cân nhắc `AttributeConverter` hoặc custom type.
6. **Xác định ràng buộc dialect/driver.** Đặc biệt với JSON, ARRAY và UUID native.
7. **Thiết kế migration dữ liệu.** Đảm bảo dữ liệu cũ phù hợp trước khi đổi mapping.
8. **Xét mutable value và concurrency.** Với JSON/array, xác định cách cập nhật và phát hiện thay đổi.
9. **Xem xét portability.** Nếu chạy trên nhiều database, tránh phụ thuộc cú pháp kiểu SQL riêng khi không cần thiết.

## 14. Bài tập vận dụng

### Bài tập 1: Phân biệt tầng kiểu

Cho mapping:

~~~java
@JdbcTypeCode(SqlTypes.JSON)
private Map<String, Object> preferences;
~~~

Hãy xác định Java type, JdbcType code, vai trò của dialect và vì sao `@Column(columnDefinition = "jsonb")` không tự thay thế annotation trên.

### Bài tập 2: UUID với schema cũ

Database có cột `external_id CHAR(36)`, nhưng code nghiệp vụ muốn dùng `UUID`. Hãy đề xuất mapping và nêu những rủi ro cần xử lý nếu dữ liệu cũ có giá trị UUID không hợp lệ.

### Bài tập 3: ARRAY hay bảng quan hệ?

Một hệ thống quản lý bài viết có danh sách tag. Khi nào có thể lưu bằng `String[]` và `SqlTypes.ARRAY`? Khi nào nên tách bảng `tags` cùng bảng liên kết?

### Bài tập 4: JSON insert thất bại

Một entity đã khai báo `@JdbcTypeCode(SqlTypes.JSON)` nhưng khi insert xuất hiện lỗi database từ chối kiểu dữ liệu. Hãy liệt kê các tầng cần kiểm tra, từ kiểu Java đến JDBC binding và SQL column type.

### Gợi ý

- **Bài 1:** Java là `Map`; JDBC code là JSON; dialect và schema quyết định kiểu cột. `columnDefinition` chủ yếu phục vụ DDL.
- **Bài 2:** Có thể cân nhắc `@JdbcTypeCode(SqlTypes.CHAR)` trên `UUID`, xác minh driver/chuyển đổi và chuẩn hóa dữ liệu cũ.
- **Bài 3:** ARRAY có thể phù hợp tập giá trị nhỏ gắn chặt với một record; bảng quan hệ thích hợp khi tag có identity và quan hệ riêng.
- **Bài 4:** Kiểm tra JSON mapper/classpath, Java value, Hibernate type mapping, dialect, JDBC driver, dữ liệu và loại cột SQL thực tế.

---

**Ghi nhớ:** `@JdbcTypeCode` trong Hibernate 6 cho phép **chỉ định cách biểu diễn JDBC** thông qua mã `SqlTypes`. Chọn một mã JDBC đúng là bước quan trọng, nhưng tính đúng đắn còn phụ thuộc JavaType, converter/serializer, dialect, JDBC driver, schema và dữ liệu đã lưu.

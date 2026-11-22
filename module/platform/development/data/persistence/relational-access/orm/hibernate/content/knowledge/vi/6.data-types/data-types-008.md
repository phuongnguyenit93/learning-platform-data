# Ánh xạ JSON, mảng và kiểu dữ liệu đặc thù theo phiên bản Hibernate và `Dialect`

Một ứng dụng Hibernate thường ánh xạ `String`, `Long`, `BigDecimal` hoặc `LocalDateTime` mà không cần quan tâm nhiều đến chi tiết JDBC. Tuy nhiên, khi thuộc tính chứa tài liệu JSON, mảng, UUID, enum native, dữ liệu không gian hay kiểu do cơ sở dữ liệu (DBMS) tự định nghĩa, câu hỏi trở nên phức tạp: **giá trị Java được biểu diễn bằng kiểu JDBC nào, kiểu cột SQL nào sẽ được tạo và câu truy vấn có chạy được ở DBMS đang dùng không?**

Bài này giải thích cách đưa ra quyết định ấy trong **Hibernate ORM 6.x**, lấy Hibernate 6.6 làm mốc minh họa. Các tính năng dạng JSON, SQL array, enum và aggregate có thay đổi qua các phiên bản Hibernate; tên kiểu SQL và mức hỗ trợ còn phụ thuộc **`Dialect`, phiên bản DBMS và JDBC driver**. Ví dụ dùng Jakarta Persistence (`jakarta.persistence.*`) cùng annotation riêng của Hibernate (`org.hibernate.annotations.*`). Với Hibernate 5.x hoặc một phiên bản 6.x khác, cần đối chiếu hướng dẫn chính thức của đúng phiên bản trước khi áp dụng.

## 1. Ba lớp quyết định của ánh xạ một giá trị

Đối với một basic attribute như `profile.settings`, Hibernate phải phối hợp ba khía cạnh:

| Khía cạnh | Câu hỏi cần trả lời | Thành phần thường tham gia |
| --- | --- | --- |
| **Kiểu và ngữ nghĩa Java** | Đây là `Map`, `String[]`, `UUID` hay một value object? Khi nào hai giá trị bằng nhau; chúng có mutable không? | `JavaType`, `MutabilityPlan`, converter, mapping annotation |
| **Biểu diễn JDBC** | Giá trị được bind/extract như `VARCHAR`, `ARRAY`, `JSON`, `UUID` hay một kiểu khác? | `JdbcType`, `BasicType`, `@JdbcTypeCode`, JDBC driver |
| **Biểu diễn SQL của DBMS** | DB có kiểu native không? DDL và cú pháp truy vấn phải viết thế nào? | `Dialect`, DBMS/version, schema migration |

```mermaid
flowchart LR
    A[Giá trị Java: Map, String[], UUID...] --> B[Mapping / converter]
    B --> C[JavaType + JdbcType]
    C --> D[Bind/extract JDBC]
    D --> E[(Kiểu cột trên DBMS)]
    F[Dialect + phiên bản DBMS] --> C
    F --> G[DDL và SQL phù hợp]
    G --> E
```

Ví dụ, `@JdbcTypeCode(SqlTypes.JSON)` yêu cầu Hibernate dùng cơ chế ánh xạ JDBC cho JSON. Nhưng từ đây **không thể suy ra mọi database có một kiểu cột tên `jsonb`**. PostgreSQL, MySQL, Oracle và các DBMS khác có kiểu native, cú pháp khai báo, hàm và toán tử JSON khác nhau. `Dialect` là lớp Hibernate dùng để điều chỉnh nhiều khác biệt đó; **nó không biến một tính năng không được database hỗ trợ thành tính năng được hỗ trợ**.

### 1.1. `SqlTypes` và `java.sql.Types` khác nhau thế nào?

`java.sql.Types` định nghĩa các mã JDBC chuẩn như `VARCHAR`, `BINARY`, `ARRAY`, `TIMESTAMP`. Hibernate bổ sung **`org.hibernate.type.SqlTypes`** với các mã và khái niệm đặc thù như `JSON`, `UUID`, `NAMED_ENUM`, `GEOMETRY`, `STRUCT`… để mô tả nhu cầu mapping rộng hơn JDBC chuẩn. Annotation sau chọn một mã kiểu cho thuộc tính:

```java
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@JdbcTypeCode(SqlTypes.JSON)
private Map<String, String> preferences;
```

`@JdbcTypeCode` tác động đến cách Hibernate xác định **JDBC type descriptor** cho mapping. Nó **không** thay thế việc định nghĩa entity, định nghĩa column, quản lý converter hoặc migration schema. Ngoài ra, phạm vi áp dụng annotation trên thuộc tính collection/`Map` phụ thuộc loại mapping (basic value hay plural attribute); cần biết thuộc tính đang được ánh xạ là một giá trị hay một tập phần tử quan hệ.

## 2. Ánh xạ JSON: từ đối tượng Java đến cột JSON

JSON phù hợp với dữ liệu có cấu trúc lồng nhau nhưng không cần thiết kế một bảng quan hệ riêng cho từng thuộc tính: tùy chọn hiển thị, các cờ cấu hình, metadata tích hợp bên ngoài hoặc payload chỉ được truy xuất cùng entity cha. Trong Hibernate 6, có thể kích hoạt JSON mapping tường minh bằng `@JdbcTypeCode(SqlTypes.JSON)`.

### 2.1. Ví dụ JSON cơ bản bằng `Map`

```java
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
@Table(name = "customer_profiles")
public class CustomerProfile {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "preferences")
    private Map<String, String> preferences = new LinkedHashMap<>();

    protected CustomerProfile() { }

    public Map<String, String> getPreferences() {
        return preferences;
    }

    public void setPreferences(Map<String, String> preferences) {
        this.preferences = preferences;
    }
}
```

Giả sử ứng dụng gán:

```java
profile.setPreferences(Map.of(
        "theme", "dark",
        "locale", "vi-VN"
));
entityManager.persist(profile);
```

Biểu diễn logic trong cột có thể là:

```json
{"theme":"dark","locale":"vi-VN"}
```

Đó là nội dung JSON minh họa, **không phải cam kết về thứ tự khóa, định dạng byte, khoảng trắng hoặc biểu diễn nội bộ của DBMS**. Hibernate sử dụng một **JSON format mapper** để serialize/deserialize giá trị; cần có thư viện JSON phù hợp trên classpath, chẳng hạn tích hợp Jackson hoặc JSON-B được phiên bản Hibernate lựa chọn hỗ trợ. Thư viện có thể được tự phát hiện và cũng có thể được cấu hình bằng thuộc tính `hibernate.type.json_format_mapper`.

```properties
# Ví dụ tùy chọn cấu hình format mapper khi dự án cần chỉ định rõ.
# Kiểm tra tên triển khai/hành vi với phiên bản Hibernate đang chạy.
hibernate.type.json_format_mapper=jackson
```

Ở cấu hình bình thường, nếu format mapper được tự phát hiện đúng, không cần thêm thuộc tính này. Dependency cụ thể phụ thuộc cách ứng dụng quản lý Jakarta Persistence, Hibernate và thư viện JSON; hãy dùng một bộ phiên bản tương thích.

### 2.2. JSON bằng một POJO thay cho `Map`

Khi JSON có cấu trúc ổn định, một lớp dữ liệu tường minh thường dễ kiểm soát hơn `Map<String, Object>`:

```java
public class NotificationSettings {
    private boolean emailEnabled;
    private String timezone;

    public NotificationSettings() { }

    public boolean isEmailEnabled() { return emailEnabled; }
    public void setEmailEnabled(boolean value) { emailEnabled = value; }

    public String getTimezone() { return timezone; }
    public void setTimezone(String value) { timezone = value; }
}

// Trong lớp @Entity:
@JdbcTypeCode(SqlTypes.JSON)
@Column(name = "notification_settings")
private NotificationSettings notificationSettings;
```

Đoạn code minh họa một POJO có constructor mặc định và thuộc tính truy cập được bởi JSON mapper. Cách JSON mapper xử lý record, enum, generic, ngày giờ, constructor bất biến và trường không công khai **tùy thư viện và cấu hình**, không phải Hibernate tự bảo đảm mọi lớp Java đều serialize được. Giá trị có cấu trúc phức tạp cần thiết kế khả năng đọc lại tương thích với dữ liệu cũ và có quy tắc `equals`/mutability rõ ràng.

Trong những phiên bản Hibernate 6 hỗ trợ **JSON aggregate mapping**, một `@Embeddable` cũng có thể được ánh xạ như một giá trị JSON bằng `@JdbcTypeCode(SqlTypes.JSON)` trên thuộc tính persistent. Đây là khả năng riêng của Hibernate; quy tắc về association/collection lồng trong aggregate và DDL phát sinh có giới hạn theo phiên bản. Đừng coi một `@Embeddable` lưu thành nhiều cột quan hệ mặc định là tương đương với một aggregate JSON lưu trong một cột.

### 2.3. SQL type thực tế do `Dialect` và schema quyết định

Trong PostgreSQL, một migration có thể chọn `jsonb`:

```sql
create table customer_profiles (
    id bigint generated by default as identity primary key,
    preferences jsonb
);
```

Đây là **DDL chỉ minh họa cho PostgreSQL và những phiên bản có hỗ trợ cú pháp tương ứng**. Một database khác có thể dùng `JSON`, cách lưu qua chuỗi/binary hoặc cơ chế riêng; kiểu mà Hibernate tự xuất DDL không nhất thiết trùng đúng ví dụ. Để ép một tên kiểu vendor-specific, Hibernate cho phép:

```java
@JdbcTypeCode(SqlTypes.JSON)
@Column(name = "preferences", columnDefinition = "jsonb")
private Map<String, String> preferences;
```

Nhưng `columnDefinition = "jsonb"` cố định DDL cho những DBMS có kiểu tương ứng. **Chỉ đặt nó khi schema/migration yêu cầu**, không dùng như công thức mặc định cho mọi database. Nếu cột đã tồn tại, Hibernate không tự chuyển đổi an toàn dữ liệu từ `VARCHAR` sang `jsonb` chỉ nhờ thay annotation.

### 2.4. Truy vấn dữ liệu nằm bên trong JSON

Các thao tác ORM thông thường như tải entity theo ID hoặc cập nhật trường JSON có thể được Hibernate điều phối. Trái lại, **truy vấn sâu vào cấu trúc JSON** rất dễ phụ thuộc tính năng SQL của DBMS.

Ví dụ PostgreSQL:

```sql
select id
from customer_profiles
where preferences ->> 'theme' = 'dark';
```

Toán tử `->>` là cú pháp PostgreSQL để lấy giá trị JSON dưới dạng text; không phải cú pháp SQL portable. MySQL, Oracle và các DBMS khác có những hàm/truy vấn JSON riêng. Hibernate HQL có khả năng mở rộng hàm SQL và các tính năng JSON phát triển theo phiên bản, nhưng **không nên giả định mọi phép toán JSON có cùng biểu thức HQL trên mọi dialect**. Khi dùng native SQL, cần tách phần SQL theo DBMS nếu ứng dụng thực sự hỗ trợ đa database.

Với giá trị do người dùng cung cấp, luôn bind parameter thay vì nối chuỗi vào SQL. Nếu JSON được truy vấn theo trường con thường xuyên, cân nhắc index tương ứng (chẳng hạn expression index hoặc GIN trong PostgreSQL, theo câu truy vấn thực tế) và đánh giá lại liệu trường đó có nên thành cột quan hệ chính thức hay không.

### 2.5. Những giới hạn cần hiểu của JSON

- **SQL `NULL` khác JSON `null`:** một cột không có giá trị và một tài liệu JSON chứa literal `null` không nhất thiết có cùng nghĩa/truy vấn. Hãy định nghĩa rõ hợp đồng dữ liệu và trường hợp null.
- **Dữ liệu mutable:** sửa nội dung của một `Map`/POJO đã managed có thể đặt ra yêu cầu về snapshot, equality và deep copy. Hành vi dirty checking phụ thuộc descriptor/mutability plan và phiên bản. Khi không chắc, hãy kiểm soát cập nhật rõ ràng, ví dụ gán giá trị mới, và xác định ngữ nghĩa của custom type.
- **Schema ứng dụng khác schema DB:** JSON cho phép thêm khóa linh hoạt nhưng không tự bảo đảm kiểu dữ liệu, trường bắt buộc hay tương thích phiên bản payload. Cần validation và chiến lược migration dữ liệu JSON.
- **Chi phí cập nhật:** nếu thay đổi một thuộc tính nhỏ trong JSON, ORM có thể phải ghi lại toàn bộ giá trị cột; DBMS có thể có các tối ưu riêng. Đừng giả định Hibernate sẽ phát SQL cập nhật từng đường dẫn JSON.
- **Bảo mật và dữ liệu nhạy cảm:** không serialize bừa entity, bí mật hoặc đối tượng có vòng tham chiếu vào JSON. JSON mapper phải được cấu hình cho những kiểu dữ liệu có chủ đích.

## 3. SQL ARRAY: ánh xạ mảng và basic collection

SQL array là **một giá trị cột chứa tập phần tử theo kiểu mà database hỗ trợ**, khác với một quan hệ nhiều hàng trong bảng phụ. Ví dụ PostgreSQL có kiểu `text[]`, `integer[]` và các toán tử truy vấn mảng. Hibernate 6.x cung cấp cơ chế basic array mapping nhưng chi tiết mặc định thay đổi theo phiên bản.

### 3.1. Ánh xạ `String[]` thành basic array

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@Entity
@Table(name = "articles")
public class Article {
    @Id
    private Long id;

    @JdbcTypeCode(SqlTypes.ARRAY)
    @Column(name = "tags")
    private String[] tags;

    protected Article() { }

    public String[] getTags() { return tags; }
    public void setTags(String[] tags) { this.tags = tags; }
}
```

`@JdbcTypeCode(SqlTypes.ARRAY)` làm ý định JDBC type rõ hơn. Trong Hibernate 6.6, các mảng basic thông dụng như `String[]`, `Short[]` hoặc `short[]` **được ánh xạ theo mã `SqlTypes.ARRAY` mặc định**, miễn là chúng không rơi vào các quy tắc đặc biệt. Với DBMS có hỗ trợ SQL array chuẩn/native, dialect có thể sinh cột array thích hợp.

DDL PostgreSQL để minh họa schema tương ứng:

```sql
create table articles (
    id bigint primary key,
    tags text[]
);
```

Việc cột được tạo tên `text[]`, `varchar(...)[]` hay một dạng khác tùy Hibernate, dialect, độ dài phần tử, cấu hình schema và DBMS. **`@JdbcTypeCode(SqlTypes.ARRAY)` không cam kết DDL luôn là `text[]`.** Hibernate/driver còn phải hỗ trợ binding và extraction của array cho kiểu phần tử cụ thể.

### 3.2. Nếu database không có SQL ARRAY native?

Trong Hibernate 6.6, dialect có thể sử dụng **kiểu dự phòng như JSON, XML hoặc VARBINARY** khi database không hỗ trợ SQL array như mong đợi. Lựa chọn liên quan đến `Dialect.getPreferredSqlTypeCodeForArray()` và hỗ trợ của DBMS; không nên gắn cứng một fallback duy nhất cho tất cả dialect.

Điều này có các hệ quả:

1. Cùng một thuộc tính Java, **kiểu cột và biểu diễn lưu trữ có thể khác** giữa hai DBMS.
2. Thao tác truy vấn `array_contains`, unnest hoặc dùng index array đặc thù **không tự trở nên portable** nhờ mapping cơ bản.
3. Khi nâng cấp Hibernate, đổi dialect hoặc chuyển hệ quản trị, cần kiểm tra DDL và khả năng đọc dữ liệu đã ghi trước đó.
4. Một fallback dạng JSON/BINARY có thể khiến thao tác tìm phần tử và index khác hẳn SQL array native.

Nếu ứng dụng **bắt buộc** sử dụng array native của một DBMS, hãy xem native array support như một yêu cầu kỹ thuật cần kiểm chứng, kèm schema migration và phép truy vấn đặc thù. Nếu ứng dụng phải hỗ trợ nhiều DBMS, có thể cân nhắc mô hình quan hệ bằng bảng phụ.

### 3.3. Basic collection khác `@ElementCollection`

Hibernate 6.6 cho phép ánh xạ một số `List<String>`/`Set<Short>` **không gắn `@ElementCollection`** như basic collection, dùng cùng hướng xử lý SQL array khi phù hợp:

```java
// Thuộc tính basic collection trong Hibernate 6.x:
@JdbcTypeCode(SqlTypes.ARRAY)
private java.util.List<String> tags;
```

Trái lại, nếu biểu diễn mỗi phần tử bằng một dòng trong bảng riêng, hãy khai báo quan hệ element collection:

```java
@ElementCollection
@CollectionTable(
        name = "article_tags",
        joinColumns = @JoinColumn(name = "article_id")
)
@Column(name = "tag", nullable = false)
private Set<String> tags = new HashSet<>();
```

Với ví dụ thứ hai, database có bảng `article_tags(article_id, tag, ...)`, chứ không phải một cột SQL ARRAY chứa toàn bộ tag. Cả hai ví dụ là **hai phương án thay thế**, không khai báo đồng thời trên cùng một field. Các import tương ứng: `jakarta.persistence.ElementCollection`, `CollectionTable`, `JoinColumn`, `Column`, và `java.util.Set`, `HashSet`.

| Câu hỏi thiết kế | SQL ARRAY / basic collection | `@ElementCollection` / bảng phụ |
| --- | --- | --- |
| Một owner lưu nhiều giá trị? | Một cột giữ cả tập phần tử. | Một bảng giữ nhiều dòng liên kết owner. |
| Tìm, lọc, join từng phần tử? | Thường dùng toán tử/hàm array vendor-specific. | SQL quan hệ, index và join phổ biến hơn. |
| Ràng buộc từng phần tử? | Phụ thuộc khả năng array/JSON và DBMS. | Có thể dùng constraint/index trên từng dòng. |
| Cập nhật một phần tử? | Có thể cần ghi lại giá trị cột hoặc dùng SQL đặc thù. | Có thể thao tác mức dòng, tùy mapping/collection semantics. |
| Tính di động giữa DBMS? | Phụ thuộc nhiều vào dialect/fallback. | Thường cao hơn do dùng mô hình bảng quan hệ chuẩn. |

**Không phải mọi `List`/`Map` đều nên biến thành JSON hoặc SQL ARRAY.** Nếu dữ liệu có quan hệ nghiệp vụ riêng, cần truy vấn/join thường xuyên, cần khóa ngoại hoặc constraint từng phần tử, bảng riêng thường là lựa chọn phù hợp.

### 3.4. Nhầm lẫn đặc biệt: `byte[]`, `Byte[]`, `char[]`

Không thể suy ra từ từ “array” trong Java rằng Hibernate sẽ dùng SQL ARRAY:

- `byte[]` truyền thống được Hibernate ánh xạ như **dữ liệu nhị phân** (`VARBINARY` hoặc dạng binary/LOB tùy annotation và dialect), không mặc nhiên thành SQL `ARRAY` gồm nhiều số byte.
- Theo hướng dẫn Hibernate 6.6, `Byte[]` có quy tắc khác `byte[]` vì phần tử wrapper có thể nhận `null`: từ **Hibernate 6.2**, `Byte[]` mặc định thuộc nhóm basic array thay vì luôn theo mapping `VARBINARY` cũ.
- `char[]`/`Character[]` cũng có quy tắc xử lý riêng, không được xem giống mọi kiểu mảng số/chữ tùy ý.
- `@Lob` dùng cho yêu cầu lưu trữ LOB, không phải cách mặc định để yêu cầu SQL ARRAY hoặc JSON.

Khi nâng cấp từ Hibernate cũ, thay đổi mapping của `Byte[]` có thể dẫn tới khác biệt schema và dữ liệu đã có; cần kiểm tra migration guide đúng phiên bản. Nếu muốn giữ biểu diễn binary cũ cho một thuộc tính đặc biệt, các giải pháp như `@JavaType(ByteArrayJavaType.class)` phải được cân nhắc theo khuyến cáo và API của phiên bản đang chạy.

### 3.5. Các truy vấn mảng đặc thù DBMS

Ví dụ PostgreSQL tìm bài viết có tag `urgent`:

```sql
select id
from articles
where 'urgent' = any(tags);
```

Đây là **native PostgreSQL SQL**, không phải truy vấn JPQL portable. Những DBMS dùng fallback JSON, XML hoặc binary không nhất thiết hỗ trợ cùng biểu thức. Nếu cần tìm kiếm thường xuyên, cần cân nhắc index thích hợp, ví dụ GIN index với những toán tử mảng phù hợp của PostgreSQL; index hữu ích hay không còn tùy câu query và số liệu thực tế.

Ngoài ra, phải định nghĩa rõ ý nghĩa của **mảng null**, **mảng rỗng** và **phần tử null**. JDBC driver, DBMS và mapping có thể phân biệt chúng theo những cách khác nhau. Mảng mutable cần được xử lý cẩn thận về việc thay phần tử tại chỗ, dirty checking và detached entity.

## 4. Kiểu đặc thù: UUID, native enum, XML, spatial, structured types

### 4.1. UUID: cùng kiểu Java nhưng có thể là `UUID`, binary hoặc chuỗi

```java
import java.util.UUID;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

// Cách ánh xạ mặc định (tùy Dialect):
private UUID externalId;

// Nếu schema bắt buộc lưu UUID theo dạng văn bản:
@JdbcTypeCode(SqlTypes.VARCHAR)
private UUID externalIdAsText;
```

Hibernate có `JavaType` cho `java.util.UUID`, nhưng JDBC type được chọn có thể phụ thuộc dialect và cấu hình như `hibernate.type.preferred_uuid_jdbc_type`. PostgreSQL có kiểu `uuid` native, trong khi ở DBMS khác có thể dùng `BINARY`, `CHAR` hoặc `VARCHAR`. Khi schema có sẵn, ưu tiên phù hợp với **kiểu cột thực** và cách JDBC driver biểu diễn tham số, không mặc định mọi `UUID` đều dài 36 ký tự trong DB.

Chuyển `UUID` từ binary sang text hoặc sang native UUID trong một schema đang vận hành là **migration dữ liệu và index/constraint**, không chỉ thay annotation. Cần phân biệt ID được sinh (`@GeneratedValue`) với cách ID đó được lưu qua JDBC.

### 4.2. Enum: `EnumType.STRING` và enum native

```java
enum PaymentStatus { NEW, PAID, FAILED }

@Enumerated(EnumType.STRING)
@Column(name = "status", nullable = false)
private PaymentStatus status;
```

`EnumType.STRING` mô tả cách ánh xạ enum theo tên hằng. **Nó không bảo đảm cột là `VARCHAR` ở mọi Hibernate version và dialect**: DBMS có kiểu enum native có thể được Hibernate chọn hoặc cần cấu hình tường minh.

Với PostgreSQL, một thiết kế có thể dùng một kiểu enum do migration tạo:

```sql
create type payment_status as enum ('NEW', 'PAID', 'FAILED');
```

Trong những phiên bản Hibernate hỗ trợ kiểu này, có thể chỉ định mapping theo hướng `NAMED_ENUM`, ví dụ:

```java
@Enumerated(EnumType.STRING)
@JdbcTypeCode(SqlTypes.NAMED_ENUM)
@Column(name = "status")
private PaymentStatus status;
```

`NAMED_ENUM` là khả năng Hibernate-specific và **cách xác định tên SQL enum type cũng như DDL phù hợp phải được đối chiếu với Hibernate/dialect và migration thực tế**. Không mặc nhiên suy ra chú thích sẽ tạo đúng SQL type có tên `payment_status` trong ví dụ. Một số dòng phiên bản Hibernate có hành vi mặc định hoặc API khác; nếu mục tiêu chỉ là lưu mã enum ổn định, `AttributeConverter` sang `String` cũng là phương án cần xem xét.

Enum native có lợi về constraint/type safety ở database nhưng thêm chi phí khi thay danh sách giá trị, đổi tên hằng hoặc di chuyển DBMS. Cần migration trước khi phần mềm bắt đầu ghi giá trị enum mới.

### 4.3. SQL XML và aggregate structured type

Hibernate 6.x có mã `SqlTypes.SQLXML` cho một số mapping XML và hỗ trợ format mapper XML tương ứng:

```java
@JdbcTypeCode(SqlTypes.SQLXML)
@Column(name = "document_data")
private Map<String, String> documentData;
```

Khả năng ánh xạ XML, thư viện cần thiết và tên cột SQL đều phụ thuộc phiên bản/dialect. Đừng dùng XML chỉ vì cơ sở dữ liệu có chức năng XML: yêu cầu query, validate và migration cần được đặt trước.

Một số DBMS cũng có **SQL object/structured types** (`STRUCT`) và Hibernate cung cấp khả năng aggregate mapping/`@Struct` cho `@Embeddable` theo những phiên bản nhất định. Đây là tính năng chuyên biệt: tên SQL type, thuộc tính được phép lồng, thứ tự field, driver và quy trình tạo type đều cần khớp schema. Nó không tương đương với `@Embedded` thông thường trải thuộc tính ra nhiều cột bảng.

### 4.4. Spatial, network, vector và kiểu mở rộng khác

| Nhóm | Ví dụ nhu cầu | Phụ thuộc cần kiểm tra |
| --- | --- | --- |
| Spatial/geometry | Điểm tọa độ, đường, vùng, truy vấn khoảng cách/giao nhau | Tích hợp spatial tương thích, kiểu Java (ví dụ JTS), database extension, dialect và hàm SQL. |
| Network address | `InetAddress`, cột `inet` ở PostgreSQL | Driver, hỗ trợ dialect, cách fallback khi DBMS không có kiểu native. |
| Vector/embedding | Tìm hàng xóm gần nhất theo vector | Phiên bản Hibernate/addon, extension DBMS, kích thước vector, distance operator/index. |
| Range/interval | Khoảng thời gian hoặc khoảng giá trị | Mức hỗ trợ của driver/dialect, semantics biên và biểu diễn SQL. |
| Vendor-defined type | Domain type, enum type, object type do doanh nghiệp định nghĩa | Tên SQL type, đăng ký `JdbcType`/`JavaType`, schema và binding chuyên dụng. |

Không thể gọi `@JdbcTypeCode` với một mã tùy ý rồi chờ Hibernate hiểu toàn bộ cấu trúc, toán tử và index của DBMS. Khi type chưa được Hibernate tích hợp, có thể cần addon hoặc **custom type descriptor** và logic query/schema đặc thù. Tên class API cụ thể phải được tra theo đúng phiên bản Hibernate vì các SPI nội bộ thay đổi nhiều giữa Hibernate 5 và 6.

## 5. `AttributeConverter` hay `@JdbcTypeCode` hay custom type?

Ba cơ chế giải quyết các vấn đề khác nhau:

| Cơ chế | Tác động | Trường hợp nên dùng | Hạn chế |
| --- | --- | --- | --- |
| **`AttributeConverter<X, Y>`** | Chuyển domain Java type `X` thành relational Java type `Y` và ngược lại | Một value object đổi thành `String`, `Integer`, `BigDecimal`… đã được JDBC hỗ trợ | Không tự định nghĩa tất cả chi tiết SQL/JDBC type, SQL operator, DDL hoặc query JSON sâu. |
| **`@JdbcTypeCode(SqlTypes.…)`** | Chọn JDBC type descriptor/mã kiểu cho basic attribute | JSON, ARRAY, UUID, SQLXML, ENUM native khi phiên bản hỗ trợ | Phụ thuộc dialect/driver/serializer; không tự chuyển mô hình quan hệ hay nâng cấp schema. |
| **`JavaType`/`JdbcType`/`BasicType` tùy chỉnh** | Kiểm soát ngữ nghĩa Java, binding/extraction, mutability và/hoặc ánh xạ JDBC | Proprietary SQL type, driver bất thường, domain semantics phức tạp | Chi phí triển khai và bảo trì cao; phụ thuộc SPI và phiên bản Hibernate. |
| **`@Embeddable` / entity / `@ElementCollection`** | Thay đổi **cấu trúc mô hình** lưu trữ | Cần nhiều cột, khóa ngoại, bảng phụ, truy vấn quan hệ | Không phải lựa chọn thay thế cho custom JDBC binder khi cần kiểu native. |

Ví dụ, một `Money` gồm `amount` và `currency` thường hợp lý dưới dạng `@Embeddable` với hai cột. Nếu hệ thống cố lưu nó trong **một cột JSON**, phải chấp nhận những đánh đổi về index, constraint, query và update. Nếu cần ánh xạ một Java value object đơn giản thành một `VARCHAR`, `AttributeConverter` thường đủ, không cần custom `JdbcType`.

### 5.1. Minh họa `AttributeConverter` cho mã trạng thái bên ngoài

```java
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

enum ShipmentState { CREATED, IN_TRANSIT, DELIVERED }

@Converter
public class ShipmentStateConverter
        implements AttributeConverter<ShipmentState, String> {

    @Override
    public String convertToDatabaseColumn(ShipmentState value) {
        if (value == null) return null;
        return switch (value) {
            case CREATED -> "C";
            case IN_TRANSIT -> "T";
            case DELIVERED -> "D";
        };
    }

    @Override
    public ShipmentState convertToEntityAttribute(String value) {
        if (value == null) return null;
        return switch (value) {
            case "C" -> ShipmentState.CREATED;
            case "T" -> ShipmentState.IN_TRANSIT;
            case "D" -> ShipmentState.DELIVERED;
            default -> throw new IllegalArgumentException("Unknown state: " + value);
        };
    }
}

// Trong entity:
@Convert(converter = ShipmentStateConverter.class)
private ShipmentState state;
```

Với `@Convert`, giá trị lưu ở dạng `String` đã chuyển đổi; converter không bảo đảm cột native enum. Không gắn `@Enumerated` cùng lúc nếu hai cách xác định mapping cho enum mâu thuẫn. Các giá trị cũ không hợp lệ sẽ làm converter ném exception khi đọc, vì vậy cần chiến lược migration/validation dữ liệu thật.

### 5.2. Khi phải viết type riêng, cần kiểm soát cả hai chiều

Một custom `JdbcType` không thể chỉ có logic ghi qua `PreparedStatement`. Cần có logic đọc qua JDBC, xử lý SQL `NULL`, kiểu Java trung gian, equality, snapshot/dirty checking, second-level cache và ngoại lệ của driver. Với giá trị mutable, cần đảm bảo `MutabilityPlan` phản ánh đúng việc deep copy và so sánh. Đặc biệt, một bộ chuyển đổi JSON tự viết bằng chuỗi nếu thiếu quy tắc đồng nhất hóa dữ liệu có thể làm Hibernate phát SQL update không cần thiết hoặc bỏ sót thay đổi.

Ưu tiên dùng mapping đã có và annotation công khai trước khi viết SPI. Việc nâng cấp từ Hibernate 5 sang Hibernate 6 chuyển nhiều API type cũ sang **compositional basic mapping** (`JavaType` + `JdbcType` + converter), nên hướng dẫn triển khai `UserType`/`BasicType` từ Hibernate 5 có thể không còn phù hợp nguyên dạng.

## 6. Phiên bản Hibernate có thể thay đổi mapping mặc định

Một quyết định quan trọng là **không coi hành vi mặc định của một phiên bản là hợp đồng vĩnh viễn**.

| Nhóm | Mốc/hành vi cần chú ý | Hệ quả triển khai |
| --- | --- | --- |
| JSON | Trong Hibernate 6, JSON mapping tường minh dùng `@JdbcTypeCode(SqlTypes.JSON)` và format mapper; hỗ trợ aggregate/hàm tiếp tục tiến hóa theo các bản phát hành | Không chuyển mã Hibernate 5 sang 6 bằng cách chỉ đổi package import; soát mapping và thư viện JSON. |
| Basic array | Từ Hibernate 6.1, nhiều array/collection có xu hướng tận dụng SQL ARRAY theo khả năng dialect thay cho biểu diễn binary cũ | Schema cũ và schema mới có thể khác; cần xét migration trước khi nâng cấp. |
| `Byte[]` | Hibernate 6.2 phân biệt `Byte[]` với `byte[]` rõ hơn trong mapping mặc định vì phần tử `Byte` có thể null | Không giả định wrapper byte array vẫn được lưu giống `VARBINARY` như trước. |
| Named enum | Mức hỗ trợ và cách chọn native enum có biến đổi theo Hibernate và DBMS | Soát `EnumType.STRING`, `SqlTypes.NAMED_ENUM`, tên DB type và migration. |
| Định danh DBMS / dialect | Danh sách DBMS/version được hỗ trợ thay đổi theo từng dòng Hibernate | Cần cập nhật driver/dialect/version đồng bộ; không chỉ sửa JDBC URL. |
| SPI type custom | Tổ chức descriptor và registration khác đáng kể giữa Hibernate 5 và 6 | Không copy nguyên giải pháp custom `Type`/`UserType` cũ mà không đối chiếu API. |

Theo tài liệu Hibernate 6.6, các basic array ngoài những trường hợp đặc biệt được ánh xạ theo `SqlTypes.ARRAY`; nếu DBMS thiếu SQL array native, dialect có thể quyết định fallback JSON/XML/VARBINARY. Nhưng **đây là thông tin của Hibernate 6.6**, không phải cam kết với mọi bản Hibernate 6/7 hay mọi driver.

Một ví dụ có thể gây lỗi khi nâng cấp: ứng dụng Hibernate cũ từng lưu danh sách số ở cột binary; phiên bản mới suy ra SQL ARRAY. Việc chỉ chạy `ddl-auto=update` có thể không chuyển toàn bộ bản ghi sang định dạng mới an toàn. Phải thiết kế migration rõ ràng, kiểm tra kiểu hiện tại và kiểm chứng đọc/ghi dữ liệu trước khi cutover.

## 7. `Dialect` không chỉ là tên lớp trong cấu hình

`Dialect` đại diện nhiều khả năng của một DBMS/phiên bản: tên kiểu DDL, sự hiện diện của SQL ARRAY/JSON, kiểu enum, cú pháp hàm, khóa, identity, pagination, expression và chiến lược SQL generator. Hibernate hiện đại thường tự nhận diện dialect qua JDBC metadata; có thể chỉ định thủ công khi thật sự cần và khi phiên bản hỗ trợ DBMS tương ứng:

```properties
# Ví dụ dành cho PostgreSQL, chỉ cần khi thực sự muốn chỉ định tường minh:
hibernate.dialect=org.hibernate.dialect.PostgreSQLDialect
```

Đặt property này **không** tự tạo database, không thay JDBC driver, không tạo extension và không biến schema MySQL thành PostgreSQL. Ngoài `Dialect`, còn phải kiểm tra:

1. **Database product và version:** có hỗ trợ JSON/array/enum native không; tính năng đó xuất hiện ở phiên bản nào?
2. **JDBC driver và version:** driver bind/extract được SQL type này không; có phụ thuộc wrapper/vendor object không?
3. **Hibernate ORM và addon version:** API và dialect nào còn được hỗ trợ; có thay đổi default mapping hay không?
4. **Schema thực:** tên type, `NULL`/`NOT NULL`, index, constraint và các giá trị đã lưu có đúng với mapping không?
5. **Truy vấn thực:** JSON path, array operator, custom function, cast và các index có được DBMS hiểu không?

### 7.1. So sánh nhanh theo năng lực, không theo tên kiểu

| Nhu cầu | PostgreSQL (minh họa) | DBMS khác |
| --- | --- | --- |
| JSON | `json`/`jsonb`, toán tử và index chuyên biệt | Tên kiểu, hàm JSON và index phụ thuộc sản phẩm/phiên bản. |
| Mảng basic | SQL array native như `text[]`, `integer[]` | Có thể có SQL ARRAY hoặc phải dùng fallback theo dialect. |
| UUID | SQL type `uuid` native | Có thể dùng binary/char/varchar hoặc native type khác. |
| Named enum | SQL enum type do DB định nghĩa | Có thể có enum native với quy tắc riêng hoặc không có. |
| Spatial/vector | Có thể cần extension như PostGIS/pgvector | Cần thư viện, extension hoặc kiểu SQL khác tùy hệ thống. |

Nếu một công ty triển khai nhiều DBMS, cần một **danh sách năng lực được hỗ trợ thực tế theo phiên bản**, thay vì hứa rằng mọi thuộc tính ánh xạ được bằng Hibernate đều truy vấn giống nhau trên tất cả các DBMS.

## 8. Quan sát SQL, schema và dữ liệu thực

Khi kiểu thực tế khác kỳ vọng, hãy phân biệt ba câu hỏi:

**(A) Hibernate đã xây dựng mapping nào?** Kiểm tra annotation trên field/getter, `@Convert`, `@JdbcTypeCode`, loại basic hay collection relationship, cách cấu hình Hibernate và phiên bản. Một `Map` được ánh xạ như basic JSON khác `@ElementCollection` hoặc association table.

**(B) Database đang có cột kiểu gì?** Đối chiếu schema do migration tạo với DDL mà Hibernate dự đoán. Chế độ `validate` chỉ kiểm tra những khía cạnh Hibernate có thể xác minh; nó không xác nhận toàn bộ ý nghĩa JSON schema, phần tử mảng, index, constraint hoặc dữ liệu lịch sử.

**(C) SQL thực tế và JDBC bind như thế nào?** Bật log có kiểm soát trong môi trường phát triển:

```properties
# Ví dụ khi dùng hệ thống logging có cấu hình logger tương ứng:
# org.hibernate.SQL = DEBUG
# org.hibernate.orm.jdbc.bind = TRACE
```

Tên logger và cấu hình cụ thể tùy framework/version. Log bind parameters có thể chứa dữ liệu cá nhân hoặc dữ liệu bí mật trong JSON, vì vậy không bật chi tiết này tùy tiện ở production.

Các dấu hiệu thường gặp:

| Hiện tượng | Nguyên nhân cần xem xét |
| --- | --- |
| Lỗi mapping khi khởi động với `SqlTypes.JSON` | Thư viện JSON mapper thiếu/không tương thích; loại Java chưa serialize được; thuộc tính có annotation chồng chéo. |
| `column ... is of type jsonb but expression is of type character varying` | Cột và JDBC parameter không được bind/cast theo kiểu DB mong đợi; converter hoặc mapping cũ có thể đang áp dụng. |
| Array được tạo thành JSON/BINARY | Dialect/DBMS không dùng SQL array native cho mapping đó; thiếu hỗ trợ phần tử/driver. |
| Query `ANY` hoặc toán tử JSON chạy PostgreSQL nhưng lỗi ở DB khác | Native SQL vendor-specific, dialect không biên dịch lại câu SQL do ứng dụng tự viết. |
| Sau nâng cấp, schema validation báo lệch kiểu | Default SQL type thay đổi giữa các phiên bản; migration chưa cập nhật kiểu cột hoặc annotation đang ép kiểu cũ. |
| Sửa map/list/array trong entity nhưng không có `UPDATE` như mong đợi | Ngữ nghĩa mutability/snapshot/dirty checking của mapping chưa phù hợp; cần kiểm tra thay đổi in-place và custom type. |
| Dữ liệu JSON cũ không deserialize được | Schema payload đổi, class Java đổi, format mapper đổi, null/generic/enum mapping không còn tương thích. |

## 9. Quy trình triển khai một kiểu dữ liệu không chuẩn

**Bước 1 — Xác định nhu cầu nghiệp vụ.** Thuộc tính cần lọc/join/index theo phần tử hay chỉ lưu và trả lại toàn bộ? Có cần constraint quan hệ? Nếu dữ liệu có đời sống riêng hoặc cần foreign key, hãy ưu tiên mô hình bảng quan hệ. JSON/array chỉ có lợi khi cấu trúc lưu trữ khớp mô hình truy cập.

**Bước 2 — Chốt hợp đồng Java.** Chọn `Map`, POJO bất biến, `String[]`, `List<String>`, `UUID` hay value object; định nghĩa `null`, empty, phần tử `null`, equality, thứ tự và cách đổi phiên bản payload. Đối với kiểu mutable, xác định cách thay đổi được Hibernate theo dõi.

**Bước 3 — Chọn mapping tối thiểu cần thiết.** Thử basic type có sẵn trước. Dùng `@JdbcTypeCode(SqlTypes.JSON)` khi cần JSON; `SqlTypes.ARRAY` khi cần array; `AttributeConverter` nếu chỉ đổi domain type sang relational Java type. Chỉ viết custom descriptor nếu việc bind/extract/mutability thực sự vượt khả năng tích hợp sẵn.

**Bước 4 — Khóa ma trận hỗ trợ.** Ghi rõ phiên bản Hibernate, driver, DBMS và dialect. Kiểm tra native support/fallback cho JSON, array, enum hoặc type đặc biệt. Nếu hỗ trợ nhiều DBMS, phân định những API nào portable và những phép truy vấn cần nhánh riêng.

**Bước 5 — Thiết kế migration và index.** Tạo schema đúng tên SQL type, constraint, index và cách chuyển dữ liệu cũ. Tránh phụ thuộc vào `hbm2ddl.auto=update` để tự xử lý chuyển đổi cột phức tạp. Có thể dùng công cụ migration có quản lý phiên bản như Flyway hoặc Liquibase.

**Bước 6 — Xác nhận chiều đọc/ghi trên database đích.** Với môi trường phát triển/tích hợp, quan sát `INSERT`/`UPDATE`/`SELECT`, JDBC bind, trạng thái `null`/empty, JSON payload cũ, dữ liệu unicode, và các biểu thức truy vấn thực sự dùng. Phần kiểm chứng này thuộc quy trình triển khai sản phẩm, không phải tính năng Hibernate tự đảm bảo.

**Bước 7 — Quản lý nâng cấp.** Khi đổi Hibernate/dialect/driver, soát migration guide và SQL DDL phát sinh cho các nhóm kiểu dễ đổi mặc định như array, wrapper byte array, enum, JSON aggregate. Thay đổi một annotation có thể đồng thời đòi hỏi đổi cột, dữ liệu, index và code query.

## 10. Ba tình huống thiết kế để áp dụng

### Tình huống A — Hồ sơ có bộ tùy chọn linh hoạt

Một hệ thống có nhiều tùy chọn nhỏ (`theme`, `locale`, thông báo…) luôn được đọc cùng hồ sơ và hiếm khi truy vấn từng khóa. **Một cột JSON** có thể giảm nhu cầu tạo thêm cột khi thay đổi cấu trúc. Dùng POJO/`Map` phù hợp, `@JdbcTypeCode(SqlTypes.JSON)`, JSON format mapper và định nghĩa version payload. Nếu sản phẩm bắt đầu tìm kiếm hàng triệu hồ sơ theo `locale`, cần cân nhắc index chuyên biệt hoặc đưa trường truy vấn quan trọng ra cột riêng.

### Tình huống B — Danh sách tag cần tìm kiếm qua nhiều DBMS

`String[]`/SQL ARRAY có thể ngắn gọn trên PostgreSQL, nhưng các truy vấn như `= ANY(tags)` không portable. Nếu hệ thống phải hỗ trợ nhiều DBMS và truy vấn tag thường xuyên, **`@ElementCollection` với bảng `article_tags`** có thể có mô hình index/join nhất quán hơn. Nếu chỉ lưu một tập nhỏ và đọc toàn bộ cùng entity, SQL ARRAY hoặc JSON vẫn có thể hợp lý, sau khi kiểm chứng dialect/driver.

### Tình huống C — Enum trạng thái thanh toán và schema cũ

Ứng dụng đang lưu `PaymentStatus` trong `VARCHAR` với dữ liệu `NEW`, `PAID`. Chuyển sang PostgreSQL native enum là quyết định về **schema và vận hành**, không chỉ chọn `SqlTypes.NAMED_ENUM`. Cần tạo type SQL, chuyển cột, kiểm tra giá trị hiện hữu, constraint, tên type trong Hibernate và chiến lược thêm trạng thái mới. Nếu tính di động và thay đổi enum thường xuyên quan trọng hơn ràng buộc native, có thể tiếp tục dùng chuỗi hoặc converter với mã ổn định.

## 11. Tài liệu tham khảo theo phiên bản

- **Hibernate ORM 6.6 User Guide:** [Basic values, JSON mapping, basic arrays, basic collections, aggregate mappings](https://docs.jboss.org/hibernate/orm/6.6/userguide/html_single/Hibernate_User_Guide.html). Nội dung về JSON, `Byte[]`, array fallback và `Dialect` trong bài lấy hành vi Hibernate 6.6 làm mốc.
- **Hibernate `@JdbcTypeCode` Javadoc:** [Annotation contract](https://docs.jboss.org/hibernate/orm/6.6/javadocs/org/hibernate/annotations/JdbcTypeCode.html). Xem ý nghĩa của annotation trên field/method và lưu ý với mapping collection/`Map`.
- **Hibernate migration guides:** tham khảo mục migration tương ứng trong [tài liệu Hibernate ORM](https://hibernate.org/orm/documentation/) khi nâng cấp minor/major version; API và mặc định của kiểu đặc thù có thể thay đổi.

Ý tưởng quan trọng nhất là **một kiểu Java không quyết định một kiểu SQL duy nhất**. Với JSON, array hoặc kiểu vendor-specific, phải hiểu cả cấu trúc Java, cơ chế JDBC do Hibernate chọn, khả năng `Dialect`, schema vật lý và truy vấn nghiệp vụ. Chọn mapping theo nhu cầu dữ liệu trước, rồi khóa phiên bản/khả năng hỗ trợ và thiết kế migration tương ứng để tránh những lỗi chỉ xuất hiện khi đổi DBMS hoặc nâng cấp Hibernate.

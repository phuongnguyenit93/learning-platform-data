# BeanPropertySqlParameterSource: lấy giá trị tham số SQL từ đối tượng Java

## 1. Mục tiêu bài học

Trong ứng dụng Java sử dụng Spring JDBC, các câu SQL thường cần nhận dữ liệu từ DTO, command hoặc đối tượng chứa điều kiện tìm kiếm: mã khách hàng, tên hiển thị, số điểm, trạng thái, thời gian cập nhật... Với `JdbcTemplate` thông thường, bạn có thể bind các giá trị theo vị trí `?`. Với `NamedParameterJdbcTemplate`, bạn có thể viết tham số có tên như `:customerId` và `:displayName`. Lúc đó, `BeanPropertySqlParameterSource` giúp **lấy giá trị của các tham số từ thuộc tính có thể đọc của một đối tượng Java**, tránh tự tạo từng cặp tên–giá trị.

Bài học thuộc nhóm **Tham số có tên** của Spring Framework Data Access và tập trung vào chính cơ chế này, không thay thế nội dung tổng quan về JDBC hay ORM.

Sau bài, bạn cần có khả năng:

1. Giải thích quan hệ giữa `NamedParameterJdbcTemplate`, `SqlParameterSource` và `BeanPropertySqlParameterSource`.
2. Viết JavaBean có getter đúng chuẩn và truyền object vào một lệnh `INSERT`, `UPDATE` hoặc `SELECT` dùng `:parameterName`.
3. Phân biệt **tên property Java** (`displayName`) với **tên cột SQL** (`display_name`); biết trường hợp cần `MapSqlParameterSource` thay thế.
4. Hiểu `hasValue`, `getValue`, `getParameterNames`, `getSqlType`, `registerSqlType` và ý nghĩa của `null`.
5. Dùng một danh sách object cho `batchUpdate` thông qua `SqlParameterSourceUtils.createBatch`.
6. Tránh các lỗi: chỉ có field mà không có accessor thích hợp, sai tên parameter, giả định đối tượng được copy/snapshot, trộn named parameter với identifier, xử lý null/enum/SQL type tùy tiện.
7. Chạy project **Java 17 + Spring Framework + H2** để quan sát đúng giá trị bind, kết quả cập nhật và truy vấn.

## 2. Từ tham số vị trí sang tham số có tên

### 2.1. JdbcTemplate dùng dấu hỏi chấm

Ví dụ:

```java
jdbcTemplate.update(
        "UPDATE customers SET display_name = ?, age = ? WHERE id = ?",
        input.getDisplayName(),
        input.getAge(),
        input.getId());
```

Nếu SQL đổi thứ tự placeholder, lời gọi Java phải đổi tương ứng. Với statement có nhiều cột kiểu tương tự nhau, việc vô tình đảo hai giá trị có thể chạy thành công nhưng ghi sai dữ liệu.

### 2.2. NamedParameterJdbcTemplate dùng :name

Vẫn là thao tác trên:

```java
String sql = """
        UPDATE customers
        SET display_name = :displayName,
            age = :age
        WHERE id = :id
        """;

SqlParameterSource params = new BeanPropertySqlParameterSource(input);
int changed = namedParameterJdbcTemplate.update(sql, params);
```

Ý nghĩa:

- `:displayName`, `:age` và `:id` là **named parameters** trong câu SQL.
- `BeanPropertySqlParameterSource(input)` cung cấp giá trị cho các tên này qua thuộc tính có thể đọc của `input`.
- `NamedParameterJdbcTemplate` phân tích SQL, chuyển named parameters thành binding JDBC thích hợp và chuyển giá trị đến driver bằng prepared-statement infrastructure.
- **Tên property** phải tương ứng với **tên named parameter**; tên bảng/cột trong SQL hoàn toàn có thể dùng quy ước khác.
- `update(...)` trả về số hàng bị tác động, không phải giá trị trả về của SQL.

Đây là snippet trong một phương thức đã có `input`, `namedParameterJdbcTemplate` và các import thích hợp. Phần 8 cung cấp ứng dụng hoàn chỉnh chạy độc lập.

### 2.3. Sơ đồ luồng dữ liệu

```text
Java object input
 ├─ getId()           → 101L
 ├─ getDisplayName()  → "Lan"
 └─ getAge()          → 25
         │
         ▼
BeanPropertySqlParameterSource
         │ implements SqlParameterSource
         ▼
NamedParameterJdbcTemplate
         │ SQL: INSERT ... VALUES (:id, :displayName, :age)
         │ binding value/type to prepared statement
         ▼
JDBC driver → relational database
```

**Không phải ORM:** `BeanPropertySqlParameterSource` không thực hiện entity tracking, SQL generation, schema migration, lazy loading hoặc tự lưu một bean xuống bảng. Nó chỉ là **nguồn cung cấp giá trị/thông tin kiểu cho những parameter mà câu SQL bạn đã tự viết yêu cầu**.

## 3. Các API và hợp đồng quan trọng

Package Spring Framework:

```java
import org.springframework.jdbc.core.namedparam.BeanPropertySqlParameterSource;
import org.springframework.jdbc.core.namedparam.SqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
```

Lớp `BeanPropertySqlParameterSource` implements `SqlParameterSource` và kế thừa `AbstractSqlParameterSource`. Nó sử dụng cơ chế property access (Spring `BeanWrapper`) để đọc một đối tượng được cung cấp cho constructor.

### 3.1. Tạo nguồn tham số

```java
CustomerInput input = new CustomerInput(101L, "Lan", null, true);
BeanPropertySqlParameterSource source =
        new BeanPropertySqlParameterSource(input);
```

Object nguồn không cần implement interface riêng. Thông thường, bạn viết getter chuẩn JavaBeans (`getId()`, `getDisplayName()`, `getAge()`, `isActive()`). Spring Framework 6.2 còn hỗ trợ thành phần của record với accessor phù hợp; vẫn nên kiểm tra hành vi ở phiên bản đang dùng, nhất là khi dùng DTO sinh mã hoặc công cụ proxy.

### 3.2. hasValue(String paramName)

`hasValue("displayName")` cho biết object cung cấp property đọc được mang tên đó hay không. **Có property nhưng giá trị null vẫn là “có giá trị được định nghĩa” theo hợp đồng nguồn tham số**:

```java
source.hasValue("id");           // true
source.hasValue("age");          // true, dù getAge() trả null
source.hasValue("display_name"); // false, vì getter là getDisplayName()
```

`hasValue` không phải phép kiểm tra “non-null” hay “hợp lệ nghiệp vụ”. Hãy dùng validation cho các trường bắt buộc; không dựa vào `hasValue` để xác thực input.

### 3.3. getValue(String paramName)

`getValue` đọc giá trị của property:

```java
Object id = source.getValue("id");                 // 101L
Object name = source.getValue("displayName");      // "Lan"
Object age = source.getValue("age");               // null
```

Nếu tên property không tồn tại/không đọc được, lời gọi có thể ném `IllegalArgumentException` hoặc dẫn đến lỗi parameter khi thực thi câu SQL. **Đừng bắt lỗi này rồi tự bind null**, bởi sai tên `:display_name` khác hoàn toàn với giá trị `age=null` hợp lệ.

### 3.4. getSqlType(String paramName) và kiểu SQL

`BeanPropertySqlParameterSource` có thể suy ra SQL type mặc định từ kiểu khai báo của property; ví dụ `Integer` thường tương ứng `java.sql.Types.INTEGER`. Nếu kiểu đặc thù hoặc database driver xử lý null không rõ ràng, có thể đăng ký rõ:

```java
BeanPropertySqlParameterSource source =
        new BeanPropertySqlParameterSource(input);
source.registerSqlType("age", java.sql.Types.INTEGER);
```

`registerSqlType` đến từ `AbstractSqlParameterSource`. Bạn cũng có thể dùng `registerTypeName` khi database yêu cầu type name riêng. Không mặc định suy luận kiểu Java sẽ xử lý hoàn hảo enum, JSON, UUID, array, proprietary type hoặc SQL NULL trên mọi driver.

### 3.5. getParameterNames()

`getParameterNames()` trả tên các thuộc tính nguồn tham số có thể liệt kê; hữu ích khi kiểm tra hoặc tích hợp `SimpleJdbcInsert`/`SimpleJdbcCall` trong một số tình huống. Không nên in toàn bộ tên–giá trị (`source.toString()`) vào log production vì object có thể chứa token, email, thông tin cá nhân hoặc secret.

**Tóm tắt contract:**

| Phương thức | Trả về / chức năng | Lưu ý |
| --- | --- | --- |
| `hasValue("name")` | Property có thể đọc theo tên hay không | Null vẫn có thể là true |
| `getValue("name")` | Giá trị hiện tại từ object | Sai tên không được coi là null hợp lệ |
| `getSqlType("name")` | SQL type dựa vào khai báo hoặc đăng ký | Có thể là `TYPE_UNKNOWN` |
| `getTypeName("name")` | Tên kiểu SQL nếu có đăng ký | Không phải tên class Java |
| `getParameterNames()` | Danh sách tên parameter có thể cung cấp | Không đồng nghĩa tất cả đều được dùng trong câu SQL |
| `registerSqlType(name, type)` | Gắn JDBC SQL type tường minh | Cần khi driver/null/type đặc biệt |
| `registerTypeName(name, typeName)` | Tên kiểu theo cơ sở dữ liệu | Chỉ khi DB/driver yêu cầu |

## 4. Property JavaBean khác với field Java và cột SQL

Ví dụ class đơn giản:

```java
public class CustomerInput {
    private long id;
    private String displayName;
    private Integer age;
    private boolean active;

    public long getId() { return id; }
    public String getDisplayName() { return displayName; }
    public Integer getAge() { return age; }
    public boolean isActive() { return active; }
}
```

Các tên có thể đọc theo quy ước JavaBean là `id`, `displayName`, `age`, `active`. Chúng **không phải** `getId`, `getDisplayName` hoặc `display_name`.

### 4.1. Đặt SQL column name và parameter name độc lập

```sql
INSERT INTO customers (id, display_name, age, active)
VALUES (:id, :displayName, :age, :active);
```

| Thành phần | Tên thực tế | Ý nghĩa |
| --- | --- | --- |
| Cột database | `display_name` | Tên cột trong schema |
| Property Java | `displayName` | Được truy cập bởi `getDisplayName()` |
| Named parameter trong SQL | `:displayName` | Lookup `source.getValue("displayName")` |
| `ResultSet` khi query | `getString("display_name")` | Đọc label cột SELECT, **không liên quan** BeanPropertySqlParameterSource |

**Sai thường gặp:**

```sql
-- SAI nếu đối tượng chỉ có property displayName:
INSERT INTO customers (display_name) VALUES (:display_name);
```

`BeanPropertySqlParameterSource` không áp dụng việc đổi `snake_case` của **`BeanPropertyRowMapper`** một cách mặc định cho named parameter. Chọn `:displayName` hoặc dùng `MapSqlParameterSource("display_name", input.getDisplayName())` nếu SQL bắt buộc giữ tên đó.

### 4.2. Chỉ có field mà không có getter?

Một class có `private String displayName` nhưng không có accessor phù hợp có thể không cung cấp `displayName` như một JavaBean property đọc được. Ngay cả khi field tồn tại, `BeanPropertySqlParameterSource` không phải công cụ đọc mọi private field tùy ý.

Nếu muốn truy cập raw field/record/bean theo cơ chế khác, Spring 6.2 có `SimplePropertySqlParameterSource` với phạm vi hỗ trợ riêng. Không chuyển sang nó chỉ vì muốn bỏ validation hay che một DTO thiết kế không đúng; trước tiên cân nhắc getter chuẩn, record hoặc nguồn Map thích hợp.

### 4.3. Bean không nhất thiết phải có setter

Để **đọc** tham số, JavaBean có getter là đủ; một input bất biến với trường `final` và public getter vẫn hoạt động. Điều này khác với mapper ánh xạ **kết quả** vào JavaBean, nơi việc ghi qua setter/constructor có thể quan trọng.

### 4.4. Boolean, acronym, nested property

- `isActive()` thường tạo property `active` với kiểu `boolean`.
- `getEnabled()` tạo `enabled` nếu đúng kiểu getter.
- Tên có chữ viết tắt như `getURL()` có thể dẫn đến JavaBeans property name không đúng `url` như người viết kỳ vọng; hãy kiểm tra tên theo quy tắc JavaBeans và `getParameterNames()`.
- Với object lồng nhau, truy cập dạng `customer.address.city` chỉ nên dùng khi hạ tầng property accessor và SQL parser xử lý đúng, đồng thời mọi tầng trung gian không null; trong bài tập cơ bản, **ưu tiên DTO phẳng** với tên parameter rõ ràng.

## 5. So sánh BeanPropertySqlParameterSource, MapSqlParameterSource và map trực tiếp

### 5.1. Từ object: BeanPropertySqlParameterSource

```java
SqlParameterSource args =
        new BeanPropertySqlParameterSource(customerInput);
namedParameterJdbcTemplate.update("""
        UPDATE customers SET display_name = :displayName
        WHERE id = :id
        """, args);
```

Thích hợp khi SQL dùng nhiều tên trùng với các readable properties của object; ít boilerplate và tiện với batch object.

### 5.2. Từ tập giá trị tường minh: MapSqlParameterSource

```java
SqlParameterSource args = new MapSqlParameterSource()
        .addValue("customer_id", customerInput.getId())
        .addValue("display_name", customerInput.getDisplayName());

namedParameterJdbcTemplate.update("""
        UPDATE customers SET display_name = :display_name
        WHERE id = :customer_id
        """, args);
```

Thích hợp khi:

- Tên SQL cố tình khác tên property Java;
- Chỉ muốn bind một subset được chọn rõ;
- Cần giá trị tính toán hoặc default có chủ đích;
- Có parameter động/các kiểu cần đăng ký tường minh.

`MapSqlParameterSource.addValue` cũng có overload nhận SQL type, giúp bind `NULL` với kiểu cụ thể ngay tại nơi tạo tham số. Với dữ liệu chỉ có một-hai parameter, `MapSqlParameterSource` có thể rõ ràng hơn tạo một bean tạm.

### 5.3. Dùng Map<String, ?> trực tiếp

Nhiều overload của `NamedParameterJdbcTemplate` nhận `Map<String, ?>`:

```java
Map<String, Object> values = Map.of(
        "id", customerInput.getId(),
        "displayName", customerInput.getDisplayName());

namedParameterJdbcTemplate.update(
        "UPDATE customers SET display_name = :displayName WHERE id = :id",
        values);
```

Lưu ý **`Map.of` không nhận null key/value**; khi cần bind `null`, dùng `MapSqlParameterSource` hoặc một implementation Map cho phép null. Với kiểu SQL đặc thù, `SqlParameterSource` có khả năng đăng ký metadata kiểu rõ hơn.

### 5.4. Không nhầm với BeanPropertyRowMapper

| Công cụ | Chiều dữ liệu | Input | Output |
| --- | --- | --- | --- |
| `BeanPropertySqlParameterSource` | Java object → SQL parameter | JavaBean/record property | `SqlParameterSource` giá trị để bind |
| `MapSqlParameterSource` | Map/giá trị tường minh → SQL parameter | Named key/value | `SqlParameterSource` |
| `BeanPropertyRowMapper<T>` | JDBC ResultSet → Java object | ResultSet column label | JavaBean properties |
| `DataClassRowMapper<T>` | JDBC ResultSet → class/record | Row + column label | Object với constructor/record support |
| `NamedParameterJdbcTemplate` | SQL+parameter source → JDBC statement | Named SQL + nguồn tham số | Count/row/object kết quả |

`BeanPropertySqlParameterSource` **không tự tạo `RowMapper` và không quyết định cách đọc kết quả**. Trong một method bạn có thể dùng nó để bind điều kiện `WHERE` và dùng một `RowMapper` khác để ánh xạ cột trả về.

## 6. Các mẫu SQL thực tế

### 6.1. INSERT từ một input object

```java
String sql = """
        INSERT INTO customers (id, display_name, age, active)
        VALUES (:id, :displayName, :age, :active)
        """;
int affected = named.update(
        sql, new BeanPropertySqlParameterSource(input));
```

Cần kiểm soát ràng buộc schema, id và dữ liệu đầu vào; việc bind thành công không có nghĩa là dữ liệu đã hợp lệ theo nghiệp vụ.

### 6.2. UPDATE từ command object

```java
String sql = """
        UPDATE customers
        SET display_name = :displayName, age = :age
        WHERE id = :id
        """;
int changed = named.update(
        sql, new BeanPropertySqlParameterSource(change));
```

**Phải kiểm tra `changed`** khi nghiệp vụ yêu cầu đúng một bản ghi. Nếu bằng 0, có thể không tìm thấy id; nếu lớn hơn 1, điều kiện `WHERE` hoặc schema có thể sai. Tên parameter lặp lại trong SQL được bind từ cùng tên property, không cần copy giá trị thành nhiều phần tử của array.

### 6.3. SELECT có điều kiện từ object

```java
String sql = """
        SELECT id, display_name, age, active
        FROM customers
        WHERE active = :active
          AND age >= :minimumAge
        ORDER BY id
        """;

List<CustomerView> result = named.query(
        sql,
        new BeanPropertySqlParameterSource(filter),
        (rs, rowNum) -> new CustomerView(
                rs.getLong("id"),
                rs.getString("display_name"),
                rs.getObject("age", Integer.class),
                rs.getBoolean("active")));
```

Đây là snippet minh họa, cần class/record `CustomerView` và `filter` với getter `isActive()`, `getMinimumAge()`. SQL `display_name` là **column label** cho output mapper, còn `:minimumAge` là **input property name**. Hai chiều ánh xạ độc lập nhau.

### 6.4. Cùng một parameter xuất hiện nhiều lần

```sql
SELECT id, display_name
FROM customers
WHERE display_name = :keyword
   OR nickname = :keyword;
```

Đối tượng chỉ cần một getter `getKeyword()`. `NamedParameterJdbcTemplate` phân tích cả hai lần xuất hiện và bind cùng giá trị tương ứng. Đừng viết nối chuỗi `"WHERE name = '" + keyword + "'"` vì nguy cơ SQL injection và sai escaping.

### 6.5. IN (:ids) và danh sách

Ví dụ:

```java
String sql = "SELECT id, display_name FROM customers WHERE id IN (:ids)";
SqlParameterSource parameters =
        new MapSqlParameterSource("ids", List.of(1L, 2L, 3L));
List<Long> ids = named.query(
        sql, parameters,
        (rs, rowNum) -> rs.getLong("id"));
```

`NamedParameterJdbcTemplate` hỗ trợ mở rộng một danh sách giá trị cho `IN` theo các trường hợp được document; chính input JavaBean cũng có thể cung cấp readable property chứa collection. Tuy nhiên:

- **Danh sách rỗng** có thể tạo SQL `IN ()` không hợp lệ hoặc phụ thuộc database. Chủ động xử lý empty list trong service/DAO, ví dụ trả list rỗng trước khi query nếu nghiệp vụ cho phép.
- Với danh sách quá lớn, database có thể giới hạn số bind variable, độ dài SQL hoặc khả năng tối ưu; cân nhắc chia lô, temp table hoặc truy vấn khác.
- **`?`/`:name` chỉ bind giá trị**, không bind tên bảng, tên cột, SQL keyword, `ORDER BY` hoặc alias. Nếu identifier động, phải dùng allowlist hợp lệ.

## 7. NULL, SQL type và vòng đời của object

### 7.1. Property tồn tại nhưng giá trị null

Một JavaBean:

```java
public Integer getAge() {
    return null;
}
```

vẫn có property `age`; `BeanPropertySqlParameterSource.hasValue("age")` là true. Nếu SQL cho phép `age=NULL`, driver có thể bind null; nếu cột `NOT NULL`, database sẽ từ chối. **Đừng nhầm missing property và null property**:

| Trường hợp | `hasValue("age")` | `getValue("age")` | Kết luận |
| --- | --- | --- | --- |
| Có getter `getAge()`, trả 25 | true | 25 | Bind giá trị bình thường |
| Có getter `getAge()`, trả null | true | null | Bind SQL NULL nếu driver/type/schema cho phép |
| Không có readable property `age` | false | Lỗi truy cập | Sai hợp đồng tên SQL ↔ object |

### 7.2. SQL type của NULL

Một số driver/database cần biết SQL type tường minh khi bind giá trị null. `BeanPropertySqlParameterSource` có thể suy luận từ kiểu khai báo, nhưng bạn có thể đăng ký:

```java
BeanPropertySqlParameterSource params =
        new BeanPropertySqlParameterSource(input);
params.registerSqlType("age", java.sql.Types.INTEGER);

named.update("""
        UPDATE customers SET age = :age WHERE id = :id
        """, params);
```

Không tự chọn `Types.VARCHAR` cho một cột `INTEGER` chỉ để query “chạy được trên H2”. Với `UUID`, JSON, SQL ARRAY, enum do driver quy định, bạn có thể cần SQL type/typeName hoặc conversion riêng. Integration test cần chạy trên database/driver gần production để kiểm tra.

### 7.3. Object không phải immutable snapshot

`BeanPropertySqlParameterSource` **bọc object** và đọc property qua accessor khi được yêu cầu. Nó không phải một bản copy immutable của tất cả field tại thời điểm constructor. Nếu object bị thay đổi giữa lúc tạo nguồn tham số và lúc thực thi SQL (hoặc bị thread khác thay đổi), các getter có thể trả giá trị không nhất quán.

Thực hành tốt:

- DTO immutable hoặc không mutate trong suốt một thao tác database.
- Mỗi operation/batch item dùng input riêng rõ phạm vi, không tái dùng mutable object cho nhiều request.
- Không đưa cùng một input bean mutable vào nhiều thread rồi bind đồng thời.
- Không thực hiện network/API call hoặc business logic có side effect trong getter; getter nên nhanh, ổn định, không ném lỗi bất ngờ.

### 7.4. Tránh bind các object phức tạp trực tiếp

`getValue("address")` có thể trả một Java object `Address`, nhưng JDBC driver không biết tự động lưu nó thành nhiều cột. Nếu database có các cột `street`, `city`, hãy flatten input thành readable properties `getStreet()`/`getCity()` hoặc dùng `MapSqlParameterSource` để chọn giá trị cần bind. Đừng nhầm **đọc giá trị property** với **serialize object tùy ý sang SQL**.

## 8. Project độc lập Java 17: chứng minh binding và batch

Dùng **Java 17+**, **Spring Framework 6.2.14**, **H2 2.3.232** và Gradle. Ví dụ chạy bằng Spring IoC container đơn giản, **không cần Spring Boot, HTTP server hoặc database cài riêng**.

### 8.1. Cấu trúc file

```text
bean-property-params-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── demo/
                └── BeanPropertyParamsDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'bean-property-params-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.14'
    implementation 'org.springframework:spring-jdbc:6.2.14'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'demo.BeanPropertyParamsDemo'
}
```

`src/main/java/demo/BeanPropertyParamsDemo.java`:

```java
package demo;

import java.sql.Types;
import java.util.Arrays;
import java.util.List;
import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.BeanPropertySqlParameterSource;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.core.namedparam.SqlParameterSource;
import org.springframework.jdbc.core.namedparam.SqlParameterSourceUtils;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class BeanPropertyParamsDemo {

    // Input bất biến, có public getter: không cần public setter.
    public static class CustomerInput {
        private final long id;
        private final String displayName;
        private final Integer age;
        private final boolean active;

        public CustomerInput(long id, String displayName,
                             Integer age, boolean active) {
            this.id = id;
            this.displayName = displayName;
            this.age = age;
            this.active = active;
        }

        public long getId() {
            return id;
        }

        public String getDisplayName() {
            return displayName;
        }

        public Integer getAge() {
            return age;
        }

        public boolean isActive() {
            return active;
        }
    }

    @Configuration
    static class Config {
        @Bean
        DataSource dataSource() {
            return new DriverManagerDataSource(
                    "jdbc:h2:mem:bean_params;DB_CLOSE_DELAY=-1",
                    "sa", "");
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        NamedParameterJdbcTemplate namedParameterJdbcTemplate(
                DataSource dataSource) {
            return new NamedParameterJdbcTemplate(dataSource);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            NamedParameterJdbcTemplate named =
                    context.getBean(NamedParameterJdbcTemplate.class);

            jdbc.execute("""
                    CREATE TABLE customers (
                        id BIGINT PRIMARY KEY,
                        display_name VARCHAR(100) NOT NULL,
                        age INTEGER NULL,
                        active BOOLEAN NOT NULL
                    )
                    """);

            CustomerInput lan = new CustomerInput(
                    1L, "Lan", null, true);
            CustomerInput minh = new CustomerInput(
                    2L, "Minh", 23, false);

            BeanPropertySqlParameterSource source =
                    new BeanPropertySqlParameterSource(lan);

            // Đọc property theo tên JavaBean, không theo tên cột SQL.
            System.out.println("name=" +
                    source.getValue("displayName"));
            System.out.println("hasAge=" +
                    source.hasValue("age"));
            System.out.println("hasSnakeCase=" +
                    source.hasValue("display_name"));
            System.out.println("ageType=" +
                    (source.getSqlType("age") == Types.INTEGER));

            // Bind hai đối tượng bằng cùng một câu SQL.
            String insertSql = """
                    INSERT INTO customers (id, display_name, age, active)
                    VALUES (:id, :displayName, :age, :active)
                    """;
            SqlParameterSource[] batch =
                    SqlParameterSourceUtils.createBatch(List.of(lan, minh));
            int[] inserted = named.batchUpdate(insertSql, batch);
            System.out.println("batch=" + Arrays.toString(inserted));

            // Getter age của Lan trả null => SQL NULL, không phải
            // thiếu tên parameter age.
            Integer ageBefore = named.queryForObject(
                    "SELECT age FROM customers WHERE id = :id",
                    new MapSqlParameterSource("id", 1L),
                    Integer.class);
            System.out.println("initialAgeNull=" + (ageBefore == null));

            // Dùng object thay đổi để UPDATE: id, displayName, age.
            CustomerInput edited = new CustomerInput(
                    1L, "Lan Anh", 25, true);
            int updated = named.update("""
                    UPDATE customers
                    SET display_name = :displayName, age = :age
                    WHERE id = :id
                    """, new BeanPropertySqlParameterSource(edited));
            System.out.println("updated=" + updated);

            String nameAfter = named.queryForObject(
                    "SELECT display_name FROM customers WHERE id = :id",
                    new MapSqlParameterSource("id", 1L),
                    String.class);
            Integer ageAfter = named.queryForObject(
                    "SELECT age FROM customers WHERE id = :id",
                    new MapSqlParameterSource("id", 1L),
                    Integer.class);
            System.out.println("after=" + nameAfter + ":" + ageAfter);

            // Named parameter dùng trong SELECT. Mọi cột đã đổi
            // sang Java object bởi RowMapper trước khi trả kết quả.
            List<String> adults = named.query("""
                    SELECT display_name FROM customers
                    WHERE age >= :minimumAge
                    ORDER BY id
                    """, new MapSqlParameterSource("minimumAge", 18),
                    (rs, rowNum) -> rs.getString("display_name"));
            System.out.println("adults=" + adults);

            int activeAdults = named.queryForObject("""
                    SELECT COUNT(*) FROM customers
                    WHERE age >= :minimumAge AND active = :active
                    """,
                    new MapSqlParameterSource()
                            .addValue("minimumAge", 18)
                            .addValue("active", true),
                    Integer.class);
            System.out.println("activeAdults=" + activeAdults);
        }
    }
}
```

### 8.2. Chạy ứng dụng

Đứng tại thư mục có `build.gradle`, với Gradle tương thích Java 17:

```bash
gradle run
```

Nếu dự án đã có Gradle Wrapper: Linux/macOS dùng `./gradlew run`; Windows dùng `gradlew.bat run`. Các dòng do `System.out.println` của chương trình tạo ra (không tính log Gradle) là:

```text
name=Lan
hasAge=true
hasSnakeCase=false
ageType=true
batch=[1, 1]
initialAgeNull=true
updated=1
after=Lan Anh:25
adults=[Lan Anh, Minh]
activeAdults=1
```

### 8.3. Đối chiếu từng dòng output

1. `name=Lan`: `getValue("displayName")` gọi accessor tương ứng trên `lan`, trả `"Lan"`.
2. `hasAge=true`: bean có getter `getAge()`, dù giá trị của Lan là null.
3. `hasSnakeCase=false`: không tồn tại readable property `display_name`; SQL cột `display_name` không tạo ra Java property mới.
4. `ageType=true`: property `Integer age` được suy ra `Types.INTEGER`.
5. `batch=[1, 1]`: H2 trả một hàng bị ảnh hưởng cho mỗi lần insert. JDBC nói chung có thể trả các mã đặc biệt như `Statement.SUCCESS_NO_INFO` trong batch; đây là đầu ra dự kiến trên môi trường demo H2.
6. `initialAgeNull=true`: hàng đầu tiên giữ `age = NULL`, vì input `getAge()` trả null.
7. `updated=1`: UPDATE trúng `id = 1` và thay tên thành `Lan Anh`, tuổi thành 25.
8. `after=Lan Anh:25`: query đọc lại dữ liệu để xác minh giá trị vừa được bind.
9. `adults=[Lan Anh, Minh]`: cả hai có tuổi từ 18 sau UPDATE; query sắp theo `id`.
10. `activeAdults=1`: Lan Anh active=true; Minh active=false.

**Điều demo chứng minh:** một object Java có getter có thể làm nguồn bind cho nhiều named parameters, kể cả giá trị null và batch; `JdbcTemplate`/`NamedParameterJdbcTemplate` vẫn chịu trách nhiệm cấp/giải phóng JDBC resources. Trong ví dụ `DriverManagerDataSource` không pooling chỉ phục vụ học tập. Production nên cấu hình một pool phù hợp, giữ credentials ngoài mã nguồn, và dùng transaction nếu một nghiệp vụ gồm nhiều bước ghi phải cùng commit/rollback.

### 8.4. Thay đổi có kiểm soát để học sâu

- Đổi `:displayName` trong SQL thành `:display_name` nhưng giữ JavaBean: hãy quan sát lỗi vì property không khớp; sửa lại SQL hoặc đổi sang `MapSqlParameterSource`.
- Bỏ `getAge()`: `hasValue("age")` không còn hợp đồng phù hợp; named SQL `:age` không thể nhận giá trị từ property ấy.
- Thử sửa `age` của Lan thành null ở UPDATE: với cột nullable, H2 lưu NULL; kiểm tra `getSqlType` hoặc gọi `registerSqlType("age", Types.INTEGER)` trước khi update.
- Thử truyền list rỗng vào `IN (:ids)` và giải quyết tại DAO trước khi để driver xử lý câu SQL không hợp lệ.
- Đặt hai record trùng khóa `id` trong batch và quan sát constraint violation; để có rollback nguyên tử cho nhiều thay đổi, sử dụng Spring transaction và kiểm thử trên database thực.

## 9. Batch object: cơ chế và giới hạn

Một đoạn production-friendly cho batch:

```java
// inputs là Collection<CustomerInput> đã validate.
SqlParameterSource[] batch =
        SqlParameterSourceUtils.createBatch(inputs);
int[] rowCounts = namedParameterJdbcTemplate.batchUpdate("""
        INSERT INTO customers (id, display_name, age, active)
        VALUES (:id, :displayName, :age, :active)
        """, batch);
```

`SqlParameterSourceUtils.createBatch(Collection<?>)` tạo một `SqlParameterSource` cho từng phần tử; với bean object, nó dùng cơ chế nguồn property, với Map sử dụng nguồn Map tương ứng. Cách này tiện cho một tập input có cùng property contract.

Điều cần nhớ:

- Mỗi item phải cung cấp đủ các tham số mà SQL yêu cầu; một item thiếu property có thể khiến cả batch thất bại.
- `batchUpdate` trả `int[]` theo từng execution. JDBC cho phép mã đặc biệt như `SUCCESS_NO_INFO`/`EXECUTE_FAILED` tùy driver; không suy luận mọi phần tử luôn là số dương.
- Batch JDBC không mặc định có nghĩa là một transaction nguyên tử do ứng dụng định nghĩa. Nếu yêu cầu all-or-nothing, bao thao tác trong `@Transactional`/`TransactionTemplate` và test rollback.
- Đừng dùng một JavaBean mutable rồi thay field trong vòng lặp và tạo nhiều nguồn tham số đều trỏ tới **cùng một instance**. Khi batch bind, các phần tử có thể cùng đọc trạng thái cuối của object. Tạo object riêng hoặc snapshot hợp lệ cho mỗi item.
- Nếu dữ liệu rất lớn, cân nhắc kích thước batch, giới hạn driver/database, thời gian transaction và memory thay vì gửi hàng triệu input trong một mẻ.

Một API có ích: `SqlParameterSourceUtils.createBatch(Object...)` cũng nhận array/varargs, còn overload Collection nhận collection. Không cần tự viết vòng lặp tạo `BeanPropertySqlParameterSource` từng phần tử nếu helper đáp ứng đúng hợp đồng.

## 10. Sử dụng trong Repository và giao dịch Spring

Đặt nguồn tham số ở tầng data access hoặc adapter của repository:

```java
@Repository
public class CustomerRepository {
    private final NamedParameterJdbcTemplate named;

    public CustomerRepository(NamedParameterJdbcTemplate named) {
        this.named = named;
    }

    public int update(CustomerChange change) {
        return named.update("""
                UPDATE customers
                SET display_name = :displayName, age = :age
                WHERE id = :id
                """, new BeanPropertySqlParameterSource(change));
    }
}
```

Đây là snippet mô tả một repository, cần định nghĩa `CustomerChange` có readable properties, import `@Repository` và kích hoạt component scan/đăng ký bean; không phải phần của chương trình demo chạy ở mục 8. Với Spring Boot, `NamedParameterJdbcTemplate` thường có thể được auto-configured khi các điều kiện phù hợp; với Spring Framework thuần, tạo bean rõ ràng như demo.

**Transaction ở service:** nếu một thao tác nghiệp vụ cần cập nhật nhiều bảng, transaction manager phải dùng cùng `DataSource` mà template sử dụng. `BeanPropertySqlParameterSource` chỉ cung cấp bind values, không bắt đầu, commit hoặc rollback transaction. Đừng nhầm nó với một entity manager.

**Validation ở boundary:** trước khi gọi DAO, kiểm tra id hợp lệ, `displayName` không trống/không quá dài, `age` trong miền nghiệp vụ, quyền sửa dữ liệu... Việc object có getter không bảo đảm database có thể chấp nhận giá trị.

## 11. Các lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Không tìm được parameter `display_name` | SQL dùng `:display_name`, bean chỉ có `displayName` | Đổi thành `:displayName` hoặc dùng `MapSqlParameterSource` với key SQL muốn dùng |
| `hasValue("age")` false | Không có getter/accessor đọc được | Viết getter chuẩn, dùng record phù hợp hoặc nguồn tham số khác |
| `hasValue("age")` true nhưng DB lỗi NOT NULL | Getter trả null | Validate input hoặc thay schema/logic nếu null hợp lệ |
| Query ghi sai giá trị | Getter trả giá trị đã bị mutate hoặc mapper nhầm field | Dùng input immutable, kiểm tra property SQL và test |
| Cột SQL `display_name` bị hiểu là property | Nhầm schema column với `:namedParameter` | Đặt tên param JavaBean rõ ràng |
| Lỗi bind enum/UUID/JSON/ARRAY | Driver không hiểu object hoặc SQL type | Convert/đăng ký SQL type/typeName, test trên driver thật |
| `Map.of` ném exception | Giá trị null không được phép trong Map.of | Dùng `MapSqlParameterSource` hoặc Map hỗ trợ null |
| Nhiều batch item cập nhật cùng giá trị cuối | Tái dùng một bean mutable cho các nguồn tham số | Tạo object riêng cho từng item |
| Batch có kết quả không như dự kiến | Driver trả special count hoặc constraint failure | Kiểm tra `int[]`, exception và transaction |
| Spring báo thiếu bean `NamedParameterJdbcTemplate` | Chưa cấu hình hoặc auto-config không chạy | Khai báo bean đúng, kiểm tra DataSource và dependency |
| SQL injection dù đã dùng param cho WHERE | Ghép identifier, ORDER BY hoặc SQL fragment từ input | Parameter chỉ bind value; dùng allowlist cho identifier |
| Query trả không đủ dòng | Điều kiện WHERE sai hoặc input property sai | Kiểm tra giá trị bind, SQL, affected row count, test bằng DB |

### Phân biệt ba loại lỗi quan trọng

1. **Sai tên property**: `:display_name` khi object chỉ có `displayName`; phát hiện ngay ở tầng named parameter/property access.
2. **Property null hợp lệ**: `:age` tồn tại nhưng giá trị null; quyết định tiếp theo thuộc schema và kiểu JDBC.
3. **Tên property đúng nhưng giá trị nghiệp vụ sai**: `age=-10` hay `displayName=" "`; đây là validation/domain rule, không phải lỗi của `BeanPropertySqlParameterSource`.

## 12. Kiểm thử đề xuất

Đừng chỉ test `getValue` độc lập; test phải chứng minh SQL thực sự nhận đúng property.

### 12.1. Test mức đơn vị cho tên property

```java
CustomerInput sample = new CustomerInput(1L, "Lan", null, true);
BeanPropertySqlParameterSource source =
        new BeanPropertySqlParameterSource(sample);

assert source.hasValue("displayName");
assert !source.hasValue("display_name");
assert source.hasValue("age");
assert source.getValue("age") == null;
```

Đoạn này minh họa assertion logic. Java `assert` có thể bị tắt khi không dùng `-ea`; trong dự án test thực tế nên dùng JUnit/AssertJ và kiểm tra code theo cấu hình test.

### 12.2. Test tích hợp INSERT/UPDATE

- Tạo bảng với cột SQL `display_name`, input có `getDisplayName()`; chạy `INSERT ... :displayName` rồi `SELECT` kiểm tra.
- Test `Integer age=null` trên cột nullable; xác minh database lưu `NULL` chứ không lưu 0.
- Test `UPDATE ... WHERE id=:id` trả đúng 1; id không có phải trả 0 và được xử lý theo contract repository.
- Test nhiều item batch, xác minh từng item thực sự có giá trị riêng, không dùng chung một mutable object.
- Test rollback khi hai cập nhật trong một service transaction và thao tác thứ hai lỗi.
- Test trên database/driver gần production nếu có enum/UUID/JSON/ARRAY hoặc SQL NULL đặc biệt.

### 12.3. Kiểm tra đúng SQL type

Nếu driver hỗ trợ, kiểm tra `getSqlType("age")` trả kiểu mong đợi; với property đặc biệt, gọi `registerSqlType` và integration test với cột thực. Không giả định Java `String` hay `Object` luôn là kiểu SQL chính xác cho mọi dữ liệu.

### 12.4. Test fail-fast khi thiếu parameter

Tạo input không có getter `getDisplayName()` hoặc cố tình đặt SQL `:missingProperty`. Test cần **thất bại có thông điệp rõ**, không được tự bind null rồi ghi dữ liệu thiếu. Nếu dùng catch exception, chỉ bắt tại boundary phù hợp để đưa lỗi lên logging/monitoring không lộ dữ liệu cá nhân.

## 13. Bài tập thực hành

**Bài 1 — Chuyển positional parameter sang named parameter.** Cho:

```java
jdbcTemplate.update(
        "UPDATE customers SET display_name=?, active=? WHERE id=?",
        input.getDisplayName(), input.isActive(), input.getId());
```

Viết lại bằng `NamedParameterJdbcTemplate` và một `BeanPropertySqlParameterSource(input)`. SQL đề xuất:

```sql
UPDATE customers
SET display_name = :displayName,
    active = :active
WHERE id = :id;
```

**Bài 2 — Sai tên property.** SQL có `:display_name` nhưng object có `getDisplayName()`. Hãy đưa ra hai cách sửa: đổi param thành `:displayName` hoặc cung cấp `MapSqlParameterSource.addValue("display_name", ...)`.

**Bài 3 — Phân biệt null và missing.** Với `getAge()` trả null, giải thích vì sao `hasValue("age")` là true, còn `hasValue("unknown")` là false. Hãy bind SQL NULL vào cột INTEGER nullable và kiểm chứng bằng query.

**Bài 4 — Batch đúng với hai đối tượng.** Viết `createBatch(List.of(item1, item2))` rồi `batchUpdate` cho SQL có `:id, :displayName, :age, :active`. Mỗi item phải có dữ liệu riêng; kiểm tra affected counts và số hàng trong DB.

**Bài 5 — Tránh object mutable dùng chung.** Tạo một object bean mutable, lần lượt đổi tên rồi xây hai `BeanPropertySqlParameterSource` cùng trỏ tới nó. Giải thích vì sao hai source có thể đọc cùng trạng thái cuối và sửa bằng object riêng.

**Bài 6 — Khi nào dùng Map?** Một stored procedure hoặc SQL cần tên param `:p_customer_id` trong khi Java object chỉ có `getId()`. Hãy chọn nguồn Map có key phù hợp hoặc tạo adapter DTO, thay vì ép `BeanPropertySqlParameterSource` tự đoán quy ước tên.

## 14. Checklist khi review code

1. SQL đang dùng `:name` hay `?`; template được gọi có hỗ trợ tên không?
2. Mọi `:name` đều khớp **readable JavaBean property/record component**, không chỉ khớp field/private variable?
3. Có đang nhầm `display_name` (SQL column) và `displayName` (Java property)?
4. Null có ý nghĩa nghiệp vụ không; cột/driver có nhận SQL type đúng không?
5. Object đầu vào có bất biến hoặc ít nhất không bị sửa trong quá trình binding?
6. SQL có tự ghép dữ liệu/identifier không tin cậy thay vì bind value?
7. Batch tạo nguồn riêng cho từng input và được đặt trong transaction phù hợp?
8. Getter có side effect, chậm hoặc ném lỗi không mong muốn không?
9. Số hàng `update` ảnh hưởng đã được kiểm tra trong nơi nghiệp vụ cần đúng một hàng?
10. Test có chạy trên DB thực/driver phù hợp chứ không chỉ mock `SqlParameterSource`?
11. Dữ liệu bí mật có bị in qua `toString()` hoặc logging parameter không?
12. Mapping dữ liệu đầu ra có dùng `RowMapper` đúng vai trò, không lẫn với nguồn tham số đầu vào?

## 15. Tóm tắt

- `BeanPropertySqlParameterSource` biến **các property có thể đọc của đối tượng Java** thành nguồn giá trị cho **named SQL parameters**.
- Dùng cùng `NamedParameterJdbcTemplate`; SQL vẫn phải được viết rõ và tên `:propertyName` phải khớp property.
- `display_name` là tên cột, `displayName` là Java property, `:displayName` là named parameter: ba vai trò khác nhau.
- Property null **không có nghĩa là property không tồn tại**. Kiểm tra SQL type và ràng buộc DB khi bind NULL.
- Dùng `SqlParameterSourceUtils.createBatch` để tạo nhiều nguồn từ danh sách input; cẩn thận với mutable object và giới hạn transaction.
- Dùng `MapSqlParameterSource` khi tên/giá trị cần được điều khiển thủ công; không cưỡng ép bean property mapping cho mọi SQL.
- Đây là **binding dữ liệu vào SQL**, không phải ORM, không tự thực hiện validation, transaction hay ánh xạ ResultSet thành entity.

## 16. Tài liệu tham khảo

- Spring Framework 6.2 — NamedParameterJdbcTemplate và SqlParameterSource: https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html
- Spring Framework 6.2 — BeanPropertySqlParameterSource API: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/core/namedparam/BeanPropertySqlParameterSource.html
- Spring Framework 6.2 — NamedParameterJdbcOperations API: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcOperations.html
- Spring Framework 6.2 — SqlParameterSource và AbstractSqlParameterSource: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/core/namedparam/SqlParameterSource.html
- Spring Framework 6.2 — SqlParameterSourceUtils: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/core/namedparam/SqlParameterSourceUtils.html
- Spring Framework — Cấp thông tin SQL type cho parameter: https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html

**Kết luận thực hành:** nếu ứng dụng có một input object rõ property và SQL dùng named parameters trùng tên đó, hãy truyền `new BeanPropertySqlParameterSource(input)` cho `NamedParameterJdbcTemplate`. Nếu cần đổi tên, chuyển đổi hoặc quản lý giá trị đặc biệt, chọn adapter/Map rõ ràng; không giả định nguồn bean tự hiểu schema database.
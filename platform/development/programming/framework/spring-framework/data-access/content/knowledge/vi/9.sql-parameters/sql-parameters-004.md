# Chỉ rõ kiểu SQL khi giá trị null không đủ thông tin suy luận

> **Mô-đun:** Spring Framework – Data Access  
> **Nhóm kiến thức:** Tham số SQL  
> **Trọng tâm:** SQL type của `null` trong JDBC, `JdbcTemplate` và `NamedParameterJdbcTemplate`

## 1. Tại sao Java null gây khó khăn cho JDBC?

Khi một đối tượng Java khác null, Spring/JDBC thường có thể suy ra cách bind từ kiểu runtime. Ví dụ `String` gợi ý kiểu chuỗi, `Long` gợi ý số nguyên lớn, `BigDecimal` gợi ý số thập phân. Ngược lại, giá trị `null` **không có class runtime** để nhận diện: cùng một Java `null` có thể đại diện cho SQL NULL kiểu `VARCHAR`, `DATE`, `DECIMAL`, `BIGINT` hoặc một kiểu đặc thù của database.

Ví dụ bảng:

~~~sql
CREATE TABLE task_note (
    id BIGINT PRIMARY KEY,
    note_text VARCHAR(120) NULL,
    estimate DECIMAL(8,2) NULL,
    due_on DATE NULL
);
~~~

Câu lệnh:

~~~java
jdbcTemplate.update(
    "INSERT INTO task_note(id, note_text, estimate, due_on) VALUES (?, ?, ?, ?)",
    1L, null, null, null
);
~~~

*có thể* chạy thành công nếu database/driver suy được kiểu từ ngữ cảnh cột `INSERT`, hoặc Spring/JDBC có cơ chế metadata/fallback phù hợp. Nhưng không phải driver và SQL expression nào cũng cung cấp metadata đủ tin cậy. Một số tổ hợp có thể từ chối bind NULL không rõ SQL type hoặc khiến ứng dụng tốn thời gian hỏi metadata.

Vấn đề cần giải quyết là **nói rõ kiểu SQL mong muốn ở vị trí tham số**. Các cách thông dụng:

1. JDBC thuần: `PreparedStatement.setNull(index, Types.DATE)`.
2. `JdbcTemplate`: dãy `Object[] args` song song với `int[] argTypes`.
3. `JdbcTemplate`: bọc một tham số bằng `SqlParameterValue`.
4. `NamedParameterJdbcTemplate`: dùng `MapSqlParameterSource` hoặc một `SqlParameterSource` đăng ký SQL type.

Hãy cung cấp SQL type đúng từ hợp đồng SQL/schema. Không chọn một kiểu tùy ý chỉ để làm mất lỗi tại một driver.

## 2. Phân biệt Java type, SQL type và SQL NULL

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Kiểu Java | `String`, `Long`, `LocalDate`, `BigDecimal` | Kiểu dữ liệu trên JVM |
| Giá trị Java `null` | `String description = null;` | Không có object tại runtime |
| SQL type của cột | `VARCHAR(120)`, `DATE`, `DECIMAL(8,2)` | Hợp đồng dữ liệu trong database |
| Mã JDBC SQL type | `Types.VARCHAR`, `Types.DATE`, `Types.DECIMAL` | Mã truyền cho driver để bind |
| SQL `NULL` | `note_text IS NULL` | Một marker SQL, không phải chuỗi `"null"` |
| SQL type chưa biết | `SqlParameterSource.TYPE_UNKNOWN` | Sentinel của Spring, không mô tả loại cột đích |

Ba hành động rất khác nhau:

- **Bỏ cột trong INSERT hoặc dùng DEFAULT:** có thể kích hoạt giá trị mặc định của schema.
- **Bind SQL NULL:** yêu cầu ghi giá trị NULL nếu constraint cho phép; không tự động kích hoạt DEFAULT.
- **Bind chuỗi `"null"` hoặc `""`:** đây là dữ liệu chuỗi, thường không tương đương SQL NULL.

`NULL` cũng không đồng nghĩa `0` cho số hoặc `false` cho boolean. Nếu “chưa biết số tiền”, thay NULL bằng số 0 là thay đổi quy tắc nghiệp vụ.

### SQL type không phải kiểu của biến Java

Dù một biến được khai báo:

~~~java
String note = null;
~~~

runtime không còn object `String` để Spring tra class. DAO biết cột `note_text` có kiểu `VARCHAR` qua schema; vậy `Types.VARCHAR` là metadata thích hợp khi cần truyền NULL. Đây là kiến thức **từ SQL**, không phải “đoán” từ object null.

## 3. Những tình huống thiếu thông tin suy luận kiểu

### 3.1. PreparedStatement không biết parameter type

Trong JDBC, câu SQL có thể chứa `?` ở vị trí chưa rõ kiểu. Một số driver hỗ trợ `PreparedStatement.getParameterMetaData()` tốt; số khác có giới hạn hoặc trả thông tin không đầy đủ. Với `null`, gọi API bind kiểu không xác định có thể dẫn tới lỗi khác nhau tùy driver.

**Không khẳng định** rằng mọi câu `INSERT ... VALUES (?, ?)` với null đều lỗi; kết quả phụ thuộc driver, biểu thức và metadata mà database cung cấp.

### 3.2. Biểu thức SQL mơ hồ

Ví dụ:

~~~sql
SELECT ? IS NULL
~~~

hoặc:

~~~sql
SELECT COALESCE(?, ?)
~~~

có thể không cho database/driver biết nên coi mỗi dấu `?` là kiểu nào khi tất cả giá trị đều null. Một số database hỗ trợ suy luận, một số từ chối, nhất là khi expression không đi kèm cột được định kiểu.

Các lựa chọn xử lý: cung cấp `Types` tường minh từ JDBC; hoặc dùng `CAST(? AS VARCHAR(...))` với cú pháp đúng dialect khi có ý nghĩa về SQL. `CAST` không phải thay thế portable cho việc bind đúng kiểu trong mọi driver.

### 3.3. Kiểu của stored procedure, JSON, UUID, ARRAY

Kiểu của input procedure, enum, JSON, UUID, mảng SQL hay kiểu tự định nghĩa có thể không khớp trực tiếp một primitive Java class. Có lúc cần `Types.OTHER`, `Types.ARRAY`, type name hoặc API driver riêng. Không coi `Types.OTHER` là “đũa thần” cho tất cả kiểu chưa biết.

### 3.4. Metadata chậm hoặc driver lỗi

Spring JDBC có thể hỏi `PreparedStatement.getParameterMetaData().getParameterType(index)` trong một số trường hợp null chưa có kiểu, rồi fallback tùy driver. Việc hỏi này có thể tốn chi phí hoặc không tin cậy. Khi bạn đã biết kiểu SQL từ schema, truyền type tường minh giúp giảm sự phụ thuộc vào suy luận runtime. Tuy nhiên hiệu quả hiệu năng phải đo trên driver thật, không suy đoán.

## 4. JDBC thuần: `PreparedStatement.setNull`

Đây là cơ sở để hiểu những abstraction phía trên:

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "UPDATE task_note SET due_on = ? WHERE id = ?")) {
    ps.setNull(1, Types.DATE);
    ps.setLong(2, 1L);
    int affected = ps.executeUpdate();
}
~~~

*Đoạn này là minh họa trong method đã có `connection`, bảng và imports, không phải chương trình độc lập.*

- `setNull(1, Types.DATE)` truyền một SQL NULL kiểu DATE vào dấu `?` thứ nhất.
- `setLong(2, 1L)` bind ID ở dấu `?` thứ hai.
- Chỉ số JDBC parameter **bắt đầu từ 1**, không bắt đầu từ 0.
- `try-with-resources` đóng `PreparedStatement`. Connection cần được đóng/trả theo cơ chế của nơi sở hữu nó, đặc biệt nếu đang tham gia Spring transaction.

Dòng sau không diễn đạt type rõ bằng:

~~~java
ps.setObject(1, null);
~~~

JDBC cũng hỗ trợ những overload `setObject` có kiểu đích, nhưng khi chính xác cần bind NULL, `setNull(index, sqlType)` là ví dụ dễ đọc. Không thay `Types.DATE` bằng `Types.NULL` nếu biết rõ cột thuộc DATE.

Một số loại SQL cần `setNull(index, sqlType, typeName)`. Tên kiểu phụ thuộc database và driver; chỉ dùng sau khi tra hợp đồng provider.

## 5. `JdbcTemplate`: truyền `Object[]` cùng `int[] argTypes`

`JdbcTemplate` cung cấp overload update với hai dãy tương ứng:

~~~java
int affected = jdbcTemplate.update(
    "INSERT INTO task_note(id, note_text, estimate, due_on) " +
    "VALUES (?, ?, ?, ?)",
    new Object[] {1L, null, null, null},
    new int[] {Types.BIGINT, Types.VARCHAR, Types.DECIMAL, Types.DATE}
);
~~~

*Đây là mã minh họa có sẵn `jdbcTemplate` và schema mục 1.*

| Thứ tự dấu `?` | Giá trị Java | SQL type | Cột đích |
| --- | --- | --- | --- |
| 1 | `1L` | `Types.BIGINT` | `id` |
| 2 | `null` | `Types.VARCHAR` | `note_text` |
| 3 | `null` | `Types.DECIMAL` | `estimate` |
| 4 | `null` | `Types.DATE` | `due_on` |

Mỗi giá trị `args[i]` phải khớp `argTypes[i]`. Dấu `?` của SQL đếm từ 1, còn mảng Java đếm từ 0. Chèn hoặc xóa một placeholder mà quên cập nhật mảng type có thể gây lỗi khó thấy. Với câu SQL dài, named parameters thường giảm rủi ro lệch vị trí.

### Trường hợp dùng tốt

- SQL có số placeholder cố định.
- Có vài cột nullable mà driver cần SQL type rõ ràng.
- Muốn khai báo toàn bộ parameter contract cạnh câu lệnh.
- Code đang sử dụng `JdbcTemplate` và không muốn chuyển sang named parameters.

Mảng kiểu cần mô tả **loại SQL thực tế**, kể cả khi giá trị runtime là null. Ví dụ `estimate DECIMAL(8,2)` cần mã `Types.DECIMAL`; đừng chọn `Types.INTEGER` chỉ vì tính năng đang hiển thị số không có phần thập phân.

## 6. `SqlParameterValue`: gắn type trực tiếp vào giá trị

Nếu chỉ một hoặc vài parameter cần SQL type rõ, `org.springframework.jdbc.core.SqlParameterValue` là cách gọn hơn:

~~~java
jdbcTemplate.update(
    "INSERT INTO task_note(id, note_text, estimate, due_on) " +
    "VALUES (?, ?, ?, ?)",
    2L,
    new SqlParameterValue(Types.VARCHAR, null),
    new SqlParameterValue(Types.DECIMAL, new BigDecimal("12.50")),
    new SqlParameterValue(Types.DATE, null)
);
~~~

Mỗi `SqlParameterValue` chứa SQL type cùng value. Dù value là null, metadata vẫn còn. Những overload của `JdbcTemplate` nhận dãy argument bình thường có thể nhận wrapper này, thay vì chỉ suy từ value Java.

Cách này hữu ích khi:

- SQL có nhiều tham số nhưng chỉ hai giá trị nullable cần chỉ rõ kiểu.
- Adapter muốn tạo một giá trị đã mang metadata và truyền đi.
- Muốn tránh mảng `int[] argTypes` với hai dãy số lượng lớn.

`SqlParameterValue` còn hỗ trợ metadata bổ sung như scale cho decimal hoặc type name cho kiểu riêng khi cần. Đừng trộn metadata mâu thuẫn giữa wrapper và overload đã khai báo một `argTypes` khác ở cùng vị trí.

### Với kiểu riêng của database

Ví dụ dạng API:

~~~java
new SqlParameterValue(Types.OTHER, "vendor_type_name", null)
~~~

Đây là **minh họa không portable**, không phải code chạy được ở mọi DB. Tên kiểu phải là tên được driver/database hỗ trợ; JSONB, UUID, enum và array có thể cần những binding khác nhau.

### `Types.NULL` không phải loại thích hợp cho mọi cột nullable

Nếu biết cột là `DECIMAL` thì `Types.DECIMAL` có nghĩa rõ ràng hơn `Types.NULL`. `Types.NULL` là một mã JDBC chung dùng trong một số tình huống, không thay thế contract cột. Hãy ưu tiên type cụ thể từ schema.

## 7. Named parameters: `MapSqlParameterSource` và `registerSqlType`

`NamedParameterJdbcTemplate` hỗ trợ SQL theo tên:

~~~sql
INSERT INTO task_note(id, note_text, estimate, due_on)
VALUES (:id, :noteText, :estimate, :dueOn)
~~~

Đăng ký giá trị và type cùng lúc:

~~~java
MapSqlParameterSource source = new MapSqlParameterSource()
        .addValue("id", 3L, Types.BIGINT)
        .addValue("noteText", null, Types.VARCHAR)
        .addValue("estimate", null, Types.DECIMAL)
        .addValue("dueOn", null, Types.DATE);

namedParameterJdbcTemplate.update(
    "INSERT INTO task_note(id, note_text, estimate, due_on) " +
    "VALUES (:id, :noteText, :estimate, :dueOn)",
    source
);
~~~

*Đây là mẫu trong method có `namedParameterJdbcTemplate`, chưa phải class độc lập.* Spring tự ánh xạ tên tham số vào thứ tự JDBC placeholder, còn `MapSqlParameterSource` lưu value và SQL type cho từng tên.

Có thể cung cấp metadata theo hai bước:

~~~java
MapSqlParameterSource source = new MapSqlParameterSource();
source.addValue("dueOn", null);
source.registerSqlType("dueOn", Types.DATE);
~~~

Kết quả về ý tưởng giống cách `addValue("dueOn", null, Types.DATE)`: SQL type đã được đăng ký với tên cụ thể.

### Với `BeanPropertySqlParameterSource`

Nếu parameter đến từ bean có property:

~~~java
BeanPropertySqlParameterSource source =
        new BeanPropertySqlParameterSource(command);
source.registerSqlType("dueOn", Types.DATE);
~~~

*Ví dụ chỉ minh họa API với biến `command` đã tồn tại.* `BeanPropertySqlParameterSource` có thể xem metadata property và suy type phù hợp cho một số loại Java; song khi gặp nullable field và driver/kiểu SQL đặc thù, việc đăng ký type tường minh vẫn có ích.

### Không dùng `Map.of` với value null

Sai ngay ở Java:

~~~java
Map<String, Object> params = Map.of("dueOn", null);
~~~

`Map.of` không chấp nhận key hoặc value null nên tạo map sẽ ném `NullPointerException` **trước khi gọi SQL**. `MapSqlParameterSource` chấp nhận null và còn hỗ trợ SQL type metadata, vì thế phù hợp hơn cho named parameter nullable.

Không phải cứ truyền một `Map<String, Object>` thông thường là Spring tự biết loại SQL của mọi null; map chứa value không chứa metadata tương đương `SqlParameterSource`.

## 8. Đối chiếu SQL type phổ biến

| Cột/biểu thức SQL | JDBC type thường dùng cho NULL | Java value không null thường gặp |
| --- | --- | --- |
| `VARCHAR` | `Types.VARCHAR` | `String` |
| `CHAR` | `Types.CHAR` | `String` |
| `INTEGER` | `Types.INTEGER` | `Integer` |
| `BIGINT` | `Types.BIGINT` | `Long` |
| `SMALLINT` | `Types.SMALLINT` | `Short` |
| `DECIMAL(p,s)` | `Types.DECIMAL` | `BigDecimal` |
| `NUMERIC(p,s)` | `Types.NUMERIC` | `BigDecimal` |
| `DATE` | `Types.DATE` | `LocalDate` / `java.sql.Date` tùy driver |
| `TIMESTAMP` | `Types.TIMESTAMP` | `LocalDateTime` / `Timestamp` tùy driver |
| `TIMESTAMP WITH TIME ZONE` | `Types.TIMESTAMP_WITH_TIMEZONE` khi hỗ trợ | `OffsetDateTime` hoặc kiểu tương thích |
| `BOOLEAN` | `Types.BOOLEAN` | `Boolean` |
| `VARBINARY` | `Types.VARBINARY` | `byte[]` |
| Vendor-specific JSON/UUID/enum | Có thể là `Types.OTHER` kèm type name/adapter | Phụ thuộc DB và driver |

Bảng mang tính định hướng; kiểu cụ thể phải hợp đồng với schema và driver thật. `null` của cột DATE không nên thay bằng chuỗi rỗng, còn `null` của DECIMAL không nên bị đổi thành số 0 nếu nghiệp vụ phân biệt hai trạng thái.

### Scale và precision

SQL `DECIMAL(8,2)` có precision 8, scale 2. Bind NULL với `Types.DECIMAL` cho biết loại, nhưng không tự tạo chính sách làm tròn cho giá trị **khác null**. Đối với tiền tệ, dùng `BigDecimal` và quy tắc làm tròn cụ thể. Không dùng `double` chỉ vì nó thuận tiện khi in số.

### SQL DATE/TIMESTAMP khác chuỗi

Khai báo `Types.DATE` cho null không có nghĩa Spring sẽ tự parse mọi `String` thành ngày chính xác khi non-null. Đối với giá trị có dữ liệu, chọn Java date/time type được JDBC driver hỗ trợ; tránh phụ thuộc locale hoặc chuỗi ngày không chuẩn.

## 9. Demo Java 17+ chạy được: bốn cách bind NULL có kiểu

Ví dụ dùng **JDK 17+**, **Maven 3.9+**, **Spring JDBC 6.1.14**, **H2 2.2.224**. H2 in-memory giữ dữ liệu trong tiến trình khi `DB_CLOSE_DELAY=-1`. Mục tiêu: insert bốn hàng bằng bốn cách binding và đọc lại trạng thái NULL một cách xác định.

### 9.1. Cấu trúc tệp

~~~text
typed-null-parameters/
├── pom.xml
└── src/main/java/demo/
    └── TypedNullDemo.java
~~~

### 9.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>typed-null-parameters</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.1.14</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.2.224</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 9.3. `src/main/java/demo/TypedNullDemo.java`

~~~java
package demo;

import java.math.BigDecimal;
import java.sql.Types;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.SqlParameterValue;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class TypedNullDemo {

    private static final String INSERT_SQL =
            "INSERT INTO task_note(id, note_text, estimate, due_on) " +
            "VALUES (?, ?, ?, ?)";

    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl("jdbc:h2:mem:typed_null_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        NamedParameterJdbcTemplate named =
                new NamedParameterJdbcTemplate(dataSource);

        jdbc.execute("CREATE TABLE task_note (" +
                "id BIGINT PRIMARY KEY, " +
                "note_text VARCHAR(120) NULL, " +
                "estimate DECIMAL(8,2) NULL, " +
                "due_on DATE NULL)");

        // A: Object[] cùng int[] SQL types.
        jdbc.update(
                INSERT_SQL,
                new Object[] {1L, null, null, null},
                new int[] {
                        Types.BIGINT, Types.VARCHAR,
                        Types.DECIMAL, Types.DATE
                });

        // B: SqlParameterValue gắn type vào từng argument.
        jdbc.update(
                INSERT_SQL,
                2L,
                new SqlParameterValue(Types.VARCHAR, null),
                new SqlParameterValue(
                        Types.DECIMAL, new BigDecimal("12.50")),
                new SqlParameterValue(Types.DATE, null));

        // C: Named parameters với SQL type theo tên.
        MapSqlParameterSource source = new MapSqlParameterSource()
                .addValue("id", 3L, Types.BIGINT)
                .addValue("noteText", null, Types.VARCHAR)
                .addValue("estimate", null, Types.DECIMAL)
                .addValue("dueOn", null, Types.DATE);
        named.update(
                "INSERT INTO task_note(id, note_text, estimate, due_on) " +
                "VALUES (:id, :noteText, :estimate, :dueOn)",
                source);

        // D: PreparedStatementSetter dùng JDBC setNull.
        jdbc.update(INSERT_SQL, ps -> {
            ps.setLong(1, 4L);
            ps.setNull(2, Types.VARCHAR);
            ps.setNull(3, Types.DECIMAL);
            ps.setNull(4, Types.DATE);
        });

        Integer total = jdbc.queryForObject(
                "SELECT COUNT(*) FROM task_note", Integer.class);

        Integer allNull = jdbc.queryForObject(
                "SELECT COUNT(*) FROM task_note " +
                "WHERE note_text IS NULL " +
                "AND estimate IS NULL AND due_on IS NULL",
                Integer.class);

        Integer nullNotes = jdbc.queryForObject(
                "SELECT COUNT(*) FROM task_note WHERE note_text IS NULL",
                Integer.class);

        BigDecimal estimate2 = jdbc.queryForObject(
                "SELECT estimate FROM task_note WHERE id = ?",
                BigDecimal.class, 2L);

        System.out.println("Total rows: " + total);
        System.out.println("All nullable columns NULL: " + allNull);
        System.out.println("NULL notes: " + nullNotes);
        System.out.println("Estimate of id=2: " + estimate2);
    }
}
~~~

Chạy ở thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.TypedNullDemo
~~~

**Những dòng chương trình in ra (không kể Maven log):**

~~~text
Total rows: 4
All nullable columns NULL: 3
NULL notes: 4
Estimate of id=2: 12.50
~~~

### 9.4. Giải thích kết quả

Hàng **1** có ba cột nullable được bind bằng SQL type array. Hàng **2** nhận `estimate = 12.50` và hai cột nullable còn lại là NULL thông qua `SqlParameterValue`. Hàng **3** dùng named parameters có metadata type; hàng **4** dùng JDBC setter trong `JdbcTemplate`.

Tất cả bốn hàng đều có `note_text IS NULL`. Chỉ hàng 1, 3, 4 có **cả ba cột nullable đều NULL**. Với H2, `DECIMAL(8,2)` giữ scale 2, nên giá trị ước lượng của hàng 2 in `12.50`.

Ví dụ **không cố tình ném lỗi bằng một NULL không có type**, vì chuyện đó có thể thành công hoặc thất bại phụ thuộc driver. Điều ta kiểm chứng là cả bốn chiến lược **truyền NULL có type rõ ràng** đều tạo đúng dữ liệu trong database demo.

Mẫu `DriverManagerDataSource` chỉ để học, không phải pool dùng trong production. Demo không mở transaction nhiều bước và không minh họa stored procedures hoặc custom JSON types.

## 10. SQL NULL vẫn tuân theo logic ba giá trị

Bind NULL đúng kiểu giải quyết chuyện **driver chấp nhận tham số**; nó không thay đổi ngữ nghĩa của SQL.

Nếu muốn tìm hàng `note_text` là NULL, câu sau **không đúng ý định**:

~~~sql
SELECT id FROM task_note WHERE note_text = ?
~~~

Dù bind `?` bằng SQL NULL kiểu VARCHAR, phép so sánh với NULL cho kết quả `UNKNOWN` theo logic ba giá trị, không cho TRUE như so sánh hai chuỗi bình thường.

Đúng khi muốn tìm cột NULL:

~~~sql
SELECT id FROM task_note WHERE note_text IS NULL
~~~

### Bộ lọc tùy chọn và placeholder null

Một mẫu:

~~~sql
WHERE (? IS NULL OR note_text = ?)
~~~

có thể không cho driver suy ra kiểu của placeholder trong `? IS NULL`, và còn có hai vị trí cần bind dù chúng biểu diễn cùng một bộ lọc.

Khai báo type ở cả hai vị trí:

~~~java
List<Long> ids = jdbcTemplate.queryForList(
    "SELECT id FROM task_note " +
    "WHERE (? IS NULL OR note_text = ?) ORDER BY id",
    Long.class,
    new SqlParameterValue(Types.VARCHAR, filter),
    new SqlParameterValue(Types.VARCHAR, filter)
);
~~~

*Đây là minh họa trong method có `filter` kiểu String/nullable, giả định SQL dialect hỗ trợ expression này.* Truy vấn dạng OR có thể ảnh hưởng query plan/index; nếu có nhiều điều kiện tùy chọn, việc xây điều kiện SQL theo nhánh rõ ràng có thể hợp lý hơn.

### Tránh nhầm default với NULL

~~~sql
INSERT INTO task_note(id) VALUES (5)
~~~

và

~~~sql
INSERT INTO task_note(id, due_on) VALUES (5, NULL)
~~~

không nhất thiết cùng ý nghĩa khi schema có `DEFAULT` cho `due_on`. Câu đầu có thể sử dụng DEFAULT, câu sau yêu cầu NULL và còn phải thỏa `NOT NULL` constraint. Đừng bind SQL NULL để mong database tự thay bằng default trừ khi schema có cơ chế được chỉ định rõ.

## 11. Những lưu ý khi dùng với driver khác nhau

### 11.1. `Types.OTHER` và type name

Kiểu như PostgreSQL JSONB, UUID hay enum và kiểu Oracle đặc thù có thể cần API riêng. Mẫu:

~~~java
new SqlParameterValue(Types.OTHER, "vendor_type_name", null)
~~~

chỉ cho thấy Spring có thể mang type name; tên kia là **minh họa**, không chạy được trên một database bất kỳ. Hãy dùng type/driver metadata được tài liệu nhà cung cấp xác nhận.

### 11.2. Không suy luận production từ H2

Một câu bind null tự động có thể chạy ở H2 nhưng không chạy với Oracle/PostgreSQL hoặc ngược lại. SQL dialect, statement metadata và driver version đều ảnh hưởng. Với các câu JDBC quan trọng, hãy chạy integration test trên database/driver mục tiêu, bao gồm cả nhánh null và non-null.

### 11.3. Property kiểm soát việc hỏi `ParameterMetaData`

Spring JDBC có property:

~~~text
spring.jdbc.getParameterType.ignore
~~~

Đây là cấu hình liên quan đến việc `StatementCreatorUtils` có bỏ qua thao tác tra cứu `PreparedStatement.getParameterMetaData().getParameterType(...)` khi xử lý null type unknown hay không. Có các fallback tùy driver. Không nên đổi property toàn ứng dụng chỉ vì một query lỗi; hãy ưu tiên khai báo type chính xác ở đúng tham số, đo và kiểm chứng nguyên nhân trước.

### 11.4. SQL type đúng không sửa được dữ liệu sai kiểu

Khi non-null, truyền chuỗi `"2026-10-30"` với `Types.DATE` không mặc định khiến mọi JDBC driver parse ngày đúng. Hãy dùng Java date/time type phù hợp. SQL type metadata không tự thay thế validation, conversion, ràng buộc `CHECK`, `NOT NULL` hoặc chính sách làm tròn.

## 12. Batch update và stored procedures

Batch có thể trộn hàng null và non-null. Dù hàng đầu có thể suy type, hàng khác vẫn cần bind null đúng loại. Với `BatchPreparedStatementSetter`, viết rõ nhánh:

~~~java
if (noteText == null) {
    ps.setNull(2, Types.VARCHAR);
} else {
    ps.setString(2, noteText);
}
~~~

*Đây là snippet trong callback có `ps` và `noteText`, không phải method hoàn chỉnh.* Với named batches, `SqlParameterSource` cho mỗi phần tử có thể mang metadata. Đừng dựa vào thứ tự hoặc kiểu của một hàng batch để thay cho contract của mọi hàng.

Stored procedures có hợp đồng `IN`/`OUT` riêng, có thể cần `SqlParameter`, `SimpleJdbcCall` và type name cụ thể. `ARRAY`, `STRUCT`, `CLOB` hay `BLOB` có thể cần `SqlTypeValue` hoặc API driver. Việc bind NULL của một VARCHAR không tự cung cấp đầy đủ cách bind những loại này.

## 13. Bảng lỗi và hướng khắc phục

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Driver báo không xác định SQL type của NULL | Không có metadata đủ rõ cho `?` | Chỉ rõ type ở placeholder bằng `Types` hoặc `SqlParameterValue` |
| Binding thành công với value nhưng lỗi khi null | Kiểu của object non-null giúp suy luận, null không mang kiểu | Test và khai báo SQL type cho nhánh null |
| Hai mảng args/argTypes lệch | Dấu `?`, giá trị và type không cùng thứ tự | Đối chiếu placeholder từ trái sang phải |
| SQL có nhiều tham số, khó đọc | Dùng positional parameters dài | `NamedParameterJdbcTemplate` và `MapSqlParameterSource` |
| `Map.of(..., null)` lỗi | Java `Map.of` không chấp nhận null | Dùng `MapSqlParameterSource` |
| `Types.INTEGER` được dùng cho cột DATE | Kiểu đã chỉ định sai schema | Sửa `java.sql.Types` và test trên DB đích |
| `WHERE field = ?` không tìm hàng NULL | Logic ba giá trị của SQL | Dùng `IS NULL` theo mục đích |
| Insert NULL mà mong cột dùng DEFAULT | NULL khác bỏ cột/DEFAULT | Sửa cách viết INSERT và hiểu schema |
| Typed null trên H2 tốt nhưng driver thật lỗi | Vendor-specific type hoặc metadata khác nhau | Integration test với driver/database thật |
| Typed NULL không khắc phục lỗi `NOT NULL` | Constraint không cho lưu NULL | Sửa dữ liệu hoặc nghiệp vụ, không sửa bằng type giả |
| Performance giảm khi bind unknown NULL | Hỏi parameter metadata hoặc query plan | Đo, xác định nguyên nhân, chỉ rõ SQL type và xem execution plan |

### Quy trình chẩn đoán

1. **Xác định SQL gốc và từng dấu `?`.** Placeholder thứ mấy tương ứng cột/biểu thức kiểu gì?
2. **Kiểm tra Java value.** Đây là null thật, chuỗi rỗng, chuỗi `"null"` hay object?
3. **Kiểm tra API bind.** `PreparedStatement.setNull`, `JdbcTemplate` array types, `SqlParameterValue` hay named source?
4. **Đối chiếu schema.** Chọn `Types` đúng, cả SQL type và scale/type name khi cần.
5. **Đọc nguyên nhân ngoại lệ.** Phân biệt lỗi metadata, cú pháp SQL, ràng buộc, conversion và logic SQL NULL.
6. **Tái hiện trên database thật.** Chạy nhánh null/non-null cùng driver và schema production-like.
7. **Đo trước khi cấu hình toàn cục.** Chỉ chỉnh property metadata nếu có bằng chứng về lỗi hoặc độ trễ.

Không cần log các giá trị dữ liệu nhạy cảm để điều tra. Ghi loại tham số, chỉ số, SQL type và stack trace phù hợp thường đủ giúp lần ra vị trí.

## 14. Câu hỏi tự kiểm tra

**1. Tại sao `String value = null` có thể vẫn gây khó khăn khi bind?**  
Vì runtime không có String object, và SQL/driver không phải lúc nào cũng suy được type của placeholder.

**2. JDBC dùng gì để bind NULL kiểu DATE?**  
`ps.setNull(position, Types.DATE)`, với chỉ số parameter bắt đầu từ 1.

**3. Trong `update(sql, Object[], int[])`, SQL type gắn với cái gì?**  
Gắn với placeholder tại vị trí tương ứng trong dãy args; hai mảng phải cùng thứ tự và số lượng.

**4. Chỉ một tham số cần metadata, chọn gì?**  
`new SqlParameterValue(Types.VARCHAR, null)` là cách ngắn gọn với overload nhận arguments thông thường.

**5. Với named parameters, khai báo SQL type ở đâu?**  
`MapSqlParameterSource.addValue(name, null, Types.DATE)` hoặc `registerSqlType(name, Types.DATE)`.

**6. Dùng `Map.of("x", null)` có an toàn không?**  
Không. Java factory này ném `NullPointerException` với null key/value.

**7. `Types.NULL` có phù hợp cho mọi cột nullable không?**  
Không. Nếu cột thuộc DATE, DECIMAL hoặc VARCHAR, nên chọn đúng loại cụ thể khi biết schema.

**8. Bind NULL kiểu VARCHAR có khiến `col = ?` tìm các giá trị SQL NULL không?**  
Không. Dùng `IS NULL`; SQL NULL tuân theo logic ba giá trị.

**9. Vì sao phải test trên DB đích dù demo H2 thành công?**  
Vì JDBC driver, vendor types và parameter metadata có khác biệt.

**10. Việc khai báo SQL type thay thế transaction hoặc validation không?**  
Không. Nó mô tả cách bind; transaction, constraint, validation và logic SQL thuộc các cơ chế riêng.

## 15. Nguồn đọc chính thức

- [Spring Framework – Parameter and Data Value Handling](https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html): ba hướng khai báo SQL type và xử lý NULL.
- [Spring Framework – JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): cách dùng `JdbcTemplate` và SQL arguments.
- [Spring 6.1 Javadoc – SqlParameterValue](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/SqlParameterValue.html).
- [Spring 6.1 Javadoc – MapSqlParameterSource](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/namedparam/MapSqlParameterSource.html).
- [Spring 6.1 Javadoc – StatementCreatorUtils](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/StatementCreatorUtils.html).
- [Java SE 17 – java.sql.Types](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Types.html).

**Ghi nhớ:** Java `null` không nói được SQL type của placeholder. Khi driver hoặc SQL expression không suy đủ, hãy khai báo **loại SQL thật từ schema** qua `setNull`, `argTypes`, `SqlParameterValue` hoặc `SqlParameterSource`. Khai báo đúng kiểu giúp JDBC bind rõ ràng, nhưng không thay đổi ý nghĩa SQL NULL hay quy tắc transaction.

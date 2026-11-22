# Toán tử LIKE, ký tự đại diện và chính sách tìm kiếm trong Spring JDBC

## 1. Vấn đề: người dùng nhập chữ, còn SQL hiểu mẫu

Giả sử ô tìm kiếm khách hàng nhận `Lan`, `Lan_Pro`, `50%` hoặc `O'Reilly`. Một hệ thống có thể yêu cầu khớp chính xác, khớp tiền tố, chứa chuỗi hoặc cho phép mẫu nâng cao. Mỗi chính sách dẫn đến một câu query có ngữ nghĩa và hiệu năng khác nhau.

Toán tử `LIKE` của SQL dùng một **pattern**; ký tự `%` và `_` là wildcard. Vì vậy, từ khóa `50%` người dùng nhập với ý định tìm đúng dấu phần trăm có thể làm query khớp cả `50 Percent` nếu ứng dụng không xử lý đúng.

Bài này phân biệt:

1. **Cú pháp SQL:** `LIKE`, hai wildcard, `ESCAPE`, `NULL`, collation.
2. **Cách truyền giá trị:** `JdbcTemplate` hoặc `NamedParameterJdbcTemplate` dùng tham số để chống SQL injection.
3. **Chính sách sản phẩm:** exact/prefix/contains, từ khóa literal hay pattern, chữ hoa/chữ thường, dấu tiếng Việt, input rỗng, giới hạn kết quả và hiệu năng.

**Quy tắc an toàn, dễ dự đoán:** mặc định coi nội dung người dùng nhập là **literal**. Ứng dụng chủ động thêm wildcard cho chức năng cụ thể; không ngầm cho phép người dùng điều khiển wildcard chỉ vì họ gõ dấu `%` hoặc `_`.

## 2. `LIKE`, `%` và `_` khác nhau như thế nào?

```sql
SELECT id, display_name
FROM customers
WHERE display_name LIKE 'Lan%'
ORDER BY id;
```

| Ký hiệu | Nghĩa trong LIKE | Ví dụ |
| --- | --- | --- |
| `%` | Không hoặc nhiều ký tự | `'Lan%'` khớp `Lan` và `Lan Anh` |
| `_` | Đúng một ký tự theo cách DB định nghĩa | `'Lan_'` khớp `Lany`, không khớp `Lan Anh` |
| Chữ khác | Chữ thông thường, chịu ảnh hưởng collation | `'Lan'` là mẫu không có wildcard |
| `ESCAPE` | Chỉ định cách dùng wildcard theo nghĩa đen | `'50!%' ESCAPE '!'` khớp chữ `50%` |

Các dạng thường gặp:

```sql
-- Khớp chính xác (theo quy tắc so sánh của DB):
WHERE display_name = 'Lan'

-- Tên bắt đầu bằng "Lan":
WHERE display_name LIKE 'Lan%'

-- Tên kết thúc bằng "Lan":
WHERE display_name LIKE '%Lan'

-- Tên chứa "Lan":
WHERE display_name LIKE '%Lan%'

-- Tên gồm "Lan" rồi đúng một ký tự:
WHERE display_name LIKE 'Lan_'
```

`%` có thể đại diện **0 ký tự**, vì vậy `'Lan%'` khớp cả tên `Lan`. `_` yêu cầu đúng một ký tự theo quy tắc DB, vì vậy `'Lan_'` không khớp `Lan`. Với chuỗi Unicode nhiều code point, một ký tự người dùng nhìn thấy có thể không tương ứng một đơn vị đếm của DB; hãy kiểm thử theo dialect/collation thực tế.

`LIKE` không phải regex. `*` và `?` không phải hai wildcard chuẩn của `LIKE`; cú pháp regex/`SIMILAR TO`/full-text search là tính năng khác. Đừng áp dụng quy tắc Java regex cho SQL `LIKE`.

### 2.1. Collation quyết định cách so chữ

Một số hệ quản trị hoặc collation xem `Lan` và `lan` như nhau; cấu hình khác phân biệt. Ngay cả `=` và `LIKE` cũng có thể bị ảnh hưởng bởi collation, kiểu `CHAR`, ký tự Unicode và khoảng trắng cuối. Không mặc định kết quả ở H2 giống hệt PostgreSQL/MySQL/SQL Server.

## 3. Dùng `ESCAPE '!'` để tìm ký tự wildcard thật

Ví dụ người dùng muốn tìm **dấu phần trăm** trong `50%`, không phải tìm “mọi chuỗi bắt đầu bằng 50”:

```sql
SELECT display_name
FROM customers
WHERE display_name LIKE '%50!%%' ESCAPE '!';
```

Giải thích pattern `%50!%%`:

- `%` đầu: bất kỳ tiền tố nào;
- `50`: chữ số `5`, `0`;
- `!%`: dấu phần trăm **literal**;
- `%` cuối: bất kỳ hậu tố nào.

Khi đó `50% Sale` khớp, còn `50 Percent` không khớp. Tương tự:

```sql
-- Chuỗi chứa đúng "Lan_" (có dấu gạch dưới thật):
WHERE display_name LIKE '%Lan!_%' ESCAPE '!'

-- Chuỗi chứa đúng "Lan!" (có dấu chấm than thật):
WHERE display_name LIKE '%Lan!!%' ESCAPE '!'
```

Nếu chọn `!` làm escape character, phải escape **cả `!`** trong input. Bảng sau mô tả chuỗi **giá trị cần bind vào SQL**, không phải đoạn SQL nối bằng chuỗi:

| Từ khóa người dùng | Sau khi escape | Pattern chứa literal |
| --- | --- | --- |
| `Lan` | `Lan` | `%Lan%` |
| `50%` | `50!%` | `%50!%%` |
| `Lan_` | `Lan!_` | `%Lan!_%` |
| `Lan!` | `Lan!!` | `%Lan!!%` |
| `50%_!` | `50!%!_!!` | `%50!%!_!!%` |
| `O'Reilly` | `O'Reilly` | `%O'Reilly%` |

Java helper:

```java
static String escapeLikeLiteral(String input) {
    return input
            .replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_");
}
```

**Thứ tự là một phần của thuật toán.** Phải nhân đôi `!` trước khi thêm `!` cho `%` và `_`. Nếu nhân đôi `!` cuối cùng, các marker vừa được thêm sẽ bị thay đổi, gây pattern sai.

Sử dụng escape character được chỉ định tường minh giúp tránh phụ thuộc vào backslash mặc định, vì backslash có thể tương tác với quy tắc escape chuỗi của Java/SQL và khác giữa DB. Cú pháp `ESCAPE '!'` được H2 hỗ trợ, nhưng khi đổi RDBMS vẫn cần kiểm tra cú pháp, collation và unit test/integration test riêng.

## 4. Vì sao bind tham số vẫn chưa đủ cho literal LIKE?

Câu sau dùng bind tham số:

```java
String pattern = "%" + userInput + "%";
List<String> names = jdbc.query(
        "SELECT display_name FROM customers " +
        "WHERE display_name LIKE ? ORDER BY id",
        (rs, rowNum) -> rs.getString(1),
        pattern);
```

Nó có khả năng chống SQL injection do không chèn input thành cú pháp SQL. Nhưng nếu `userInput = "%"`, pattern thành `"%%%"`: wildcard khớp gần như mọi giá trị chuỗi khác `NULL`. Người dùng đã điều khiển **phạm vi khớp**, dù chưa can thiệp được parser SQL.

Hãy tách hai lớp:

- **Bind parameter:** truyền `?`/`:name` dưới dạng dữ liệu; dấu `'` trong `O'Reilly` không đóng literal SQL; chuỗi `' OR 1=1 --` không trở thành logic SQL.
- **Escape LIKE:** biến ký tự đặc biệt do người dùng nhập thành literal. Với policy chứa literal, chỉ ứng dụng được chủ động thêm `%` đầu/cuối.

Mẫu an toàn:

```java
String pattern = "%" + escapeLikeLiteral(userInput) + "%";
List<String> names = jdbc.query(
        "SELECT display_name FROM customers " +
        "WHERE display_name LIKE ? ESCAPE '!' ORDER BY id",
        (rs, rowNum) -> rs.getString(1),
        pattern);
```

Hai đoạn trên giả định đã có `jdbc` và input được validate, **chưa phải file Java chạy độc lập**. Dùng trực tiếp `userInput` để ghép SQL sẽ nguy hiểm:

```java
// SAI: dữ liệu người dùng trở thành cú pháp SQL.
String sql = "SELECT * FROM customers WHERE display_name LIKE '%"
        + userInput + "%'";
jdbc.queryForList(sql);
```

Nếu người dùng nhập dấu nháy đơn hoặc mã SQL có chủ đích xấu, query có thể hỏng hoặc bị SQL injection. Đừng tự thay dấu `'` thành `''` trong Java nếu đã bind giá trị; đó là cách xử lý literal trong SQL text, không phải trách nhiệm của dữ liệu đã bind.

## 5. Chính sách tìm kiếm: EXACT, PREFIX, SUFFIX, CONTAINS

Thiết kế API nên nêu rõ ý định thay vì để service tự diễn giải pattern của client:

| Chế độ | SQL | Tham số |
| --- | --- | --- |
| EXACT | `column = ?` | Chuỗi literal (không cần LIKE) |
| PREFIX | `column LIKE ? ESCAPE '!'` | `escaped + "%"` |
| SUFFIX | `column LIKE ? ESCAPE '!'` | `"%" + escaped` |
| CONTAINS | `column LIKE ? ESCAPE '!'` | `"%" + escaped + "%"` |
| ADVANCED | `column LIKE ? ESCAPE '!'` | Pattern theo ngôn ngữ đã công bố rõ |

Với ô tìm kiếm chung, người dùng nên chọn **bắt đầu bằng** hoặc **chứa** qua UI. Server nhận enum được validate và tự tạo pattern. Tránh “người dùng gõ `%` nghĩa là wildcard” nếu giao diện không hề giải thích.

### 5.1. Chính sách `null`, rỗng, khoảng trắng

Ứng dụng phải quyết định khi input `null`, `""` hoặc chỉ có khoảng trắng:

1. Trả lỗi validation nếu ô tìm kiếm bắt buộc có nội dung.
2. Trả danh sách rỗng và không gọi DB.
3. Chuyển sang chế độ duyệt dữ liệu có phân trang, sort và phân quyền.

Không âm thầm biến thành `LIKE '%%'`. Trong phần lớn DB, pattern đó khớp rất rộng với các chuỗi khác SQL `NULL`, khiến query chậm và có thể trả dữ liệu không đúng ý định.

Quy tắc trim cũng phải rõ: `"  Lan  "` thành `"Lan"` với Java `strip()`, nhưng với mã hàng mà dấu cách đầu/cuối có nghĩa thì không nên trim. Độ dài tối đa/tối thiểu phụ thuộc UI và quy mô dữ liệu, không có một hằng số đúng cho mọi hệ thống.

### 5.2. Không cho client chèn tên cột hoặc ORDER BY

`?` chỉ bind **giá trị**, không bind tên cột/bảng hay keyword `ASC`/`DESC`. Nếu người dùng chọn “Tìm theo tên hoặc email”, server phải dùng allowlist:

```java
// Đoạn minh họa: field là enum server đã validate.
String column = switch (field) {
    case NAME -> "display_name";
    case EMAIL -> "email";
};

String sql = "SELECT id FROM customers WHERE " +
        column + " LIKE ? ESCAPE '!' ORDER BY id";
```

Đây là lựa chọn giữa **hai chuỗi SQL cố định của ứng dụng**, không phải nối bất kỳ nội dung client nào thành identifier.

## 6. Chương trình hoàn chỉnh Java 17+: Spring JDBC với H2

Ví dụ sau cố định Java 17+, Spring Framework 6.2.12 và H2 2.3.232, để tái hiện hành vi. Không cần Spring Boot hay cài database server.

Nó tạo một DAO dùng `JdbcTemplate` và một `RowMapper<String>` không giữ state; sử dụng H2 `LIKE ? ESCAPE '!'` và các mẫu do server xây.

### 6.1. Cấu trúc tệp và Maven

```text
like-policy-demo/
├── pom.xml
└── src/main/java/example/LikePolicyDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>like-policy-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/example/LikePolicyDemo.java`:

```java
package example;

import java.util.List;
import java.util.Locale;
import java.util.Objects;
import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class LikePolicyDemo {
    enum Mode { EXACT, PREFIX, CONTAINS }

    static final class SearchDao {
        private static final RowMapper<String> NAME_MAPPER =
                (rs, rowNum) -> rs.getString("display_name");

        private final JdbcTemplate jdbc;

        SearchDao(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        private static String validate(String input) {
            if (input == null) {
                throw new IllegalArgumentException("Search input is null");
            }
            String text = input.strip();
            if (text.isBlank() || text.length() > 60) {
                throw new IllegalArgumentException("Invalid search length");
            }
            return text;
        }

        private static String escapeLike(String literal) {
            return literal
                    .replace("!", "!!")
                    .replace("%", "!%")
                    .replace("_", "!_");
        }

        List<String> search(String input, Mode mode) {
            Objects.requireNonNull(mode, "mode");
            String text = validate(input);
            String escaped = escapeLike(text);
            String operator = mode == Mode.EXACT
                    ? "= ?" : "LIKE ? ESCAPE '!'";

            String parameter = switch (mode) {
                case EXACT -> text;
                case PREFIX -> escaped + "%";
                case CONTAINS -> "%" + escaped + "%";
            };

            return jdbc.query(
                    "SELECT display_name FROM customers WHERE display_name " +
                    operator + " ORDER BY id",
                    NAME_MAPPER,
                    parameter);
        }

        List<String> containsIgnoreCase(String input) {
            String text = validate(input);
            String pattern = "%" +
                    escapeLike(text.toLowerCase(Locale.ROOT)) + "%";

            return jdbc.query(
                    "SELECT display_name FROM customers " +
                    "WHERE LOWER(display_name) LIKE ? ESCAPE '!' ORDER BY id",
                    NAME_MAPPER,
                    pattern);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {
        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:likepolicy;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource source) {
            return new JdbcTemplate(source);
        }

        @Bean
        SearchDao searchDao(JdbcTemplate jdbc) {
            return new SearchDao(jdbc);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            SearchDao dao = context.getBean(SearchDao.class);

            jdbc.execute(
                    "CREATE TABLE customers (" +
                    "id BIGINT PRIMARY KEY, display_name VARCHAR(100) NOT NULL)");

            String insert =
                    "INSERT INTO customers (id, display_name) VALUES (?, ?)";
            jdbc.update(insert, 1L, "Lan Anh");
            jdbc.update(insert, 2L, "Lan_Pro");
            jdbc.update(insert, 3L, "Nam");
            jdbc.update(insert, 4L, "50% Sale");
            jdbc.update(insert, 5L, "50 Percent");
            jdbc.update(insert, 6L, "ALAN");
            jdbc.update(insert, 7L, "Lan! VIP");
            jdbc.update(insert, 8L, "Lan% VIP");
            jdbc.update(insert, 9L, "Lany");
            jdbc.update(insert, 10L, "lan junior");
            jdbc.update(insert, 11L, "O'Reilly");

            System.out.println("Exact: " +
                    dao.search("Lan Anh", Mode.EXACT));
            System.out.println("Prefix: " +
                    dao.search("Lan", Mode.PREFIX));
            System.out.println("Literal underscore: " +
                    dao.search("Lan_", Mode.CONTAINS));
            System.out.println("Literal percent: " +
                    dao.search("50%", Mode.CONTAINS));
            System.out.println("Literal escape: " +
                    dao.search("Lan!", Mode.CONTAINS));
            System.out.println("Apostrophe: " +
                    dao.search("O'Reilly", Mode.CONTAINS));
            System.out.println("Case insensitive: " +
                    dao.containsIgnoreCase("lan"));
        }
    }
}
```

Chạy từ thư mục có `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.LikePolicyDemo
```

Các dòng do chương trình in ra với H2 đã cấu hình (bỏ qua log Maven có thể xuất hiện tùy môi trường):

```text
Exact: [Lan Anh]
Prefix: [Lan Anh, Lan_Pro, Lan! VIP, Lan% VIP, Lany]
Literal underscore: [Lan_Pro]
Literal percent: [50% Sale]
Literal escape: [Lan! VIP]
Apostrophe: [O'Reilly]
Case insensitive: [Lan Anh, Lan_Pro, ALAN, Lan! VIP, Lan% VIP, Lany, lan junior]
```

### 6.2. Vì sao các dòng output khác nhau?

- `Exact` dùng `= ?` với `Lan Anh`, không dùng wildcard.
- `Prefix` dùng pattern `Lan%`, nên lấy các tên bắt đầu bằng `Lan` trong database H2 case-sensitive của ví dụ.
- `Literal underscore` từ `Lan_` thành `%Lan!_%`, chỉ tên có ký tự gạch dưới thật khớp.
- `Literal percent` từ `50%` thành `%50!%%`, không trả tên `50 Percent`.
- `Literal escape` từ `Lan!` thành `%Lan!!%`, giữ đúng ký tự `!`.
- `Apostrophe` dùng bind parameter, nên tên `O'Reilly` không làm hỏng SQL.
- `Case insensitive` kết hợp `LOWER(display_name)` và `Locale.ROOT` cho chuỗi Latin không dấu trong dữ liệu demo. Nó **không** tự giải quyết tìm không dấu hoặc Unicode case folding phức tạp trong production.

`strip()` và giới hạn 60 ký tự là policy minh họa, không phải mặc định của Spring. `DriverManagerDataSource` được dùng cho bài học, không có connection pool; ứng dụng thực thường cần HikariCP hoặc pool khác. Tùy chọn H2 `DB_CLOSE_DELAY=-1` giữ database trong bộ nhớ qua các connection của demo.

### 6.3. Các công cụ chưa tự kiểm tra nội dung người dùng

`JdbcTemplate` giúp chuẩn bị statement và quản lý JDBC resources. `RowMapper` tạo Java object từ từng hàng. Cả hai **không tự biết** người dùng muốn tìm literal, prefix hay wildcard nâng cao. Chính DAO/service phải làm rõ search policy và biến đổi pattern.

## 7. Với NamedParameterJdbcTemplate thì sao?

`NamedParameterJdbcTemplate` cho phép tham số tên như `:pattern`, dễ đọc khi có nhiều điều kiện, nhưng **không thay** ý nghĩa `LIKE`:

```java
// Đoạn trích: cần namedJdbc, Map, validate và escapeLike đã định nghĩa.
String pattern = "%" + escapeLike(userText) + "%";
List<String> results = namedJdbc.query(
        "SELECT display_name FROM customers " +
        "WHERE display_name LIKE :pattern ESCAPE '!' ORDER BY id",
        Map.of("pattern", pattern),
        (rs, rowNum) -> rs.getString("display_name"));
```

Tên `:pattern` là cơ chế bind tham số của Spring; dấu `%` trong giá trị vẫn là wildcard của SQL nếu chưa escape. Các giá trị khác như `:tenantId` hoặc `:status` cũng được bind; tên bảng/column/sort phải được chọn từ allowlist của ứng dụng, không ghép từ request.

## 8. Trường hợp khó: chữ hoa, dấu tiếng Việt và Unicode

Với sản phẩm cho người Việt, yêu cầu “không phân biệt chữ hoa và dấu” cần được viết thành quy tắc:

- `Lan` và `lan` có tương đương không?
- `Hoa` và `Hòa` có tương đương không?
- `đ` và `d` có tương đương không?
- Hai cách biểu diễn Unicode composed/decomposed có khớp nhau không?
- Có bỏ khoảng trắng đầu/cuối, chuẩn hóa khoảng trắng giữa các từ không?

`LOWER(name) LIKE ?` có thể phục vụ case-insensitive đơn giản nhưng **không** đương nhiên bỏ dấu tiếng Việt. Java `toLowerCase(Locale.ROOT)` cũng không cam kết hoàn toàn trùng thuật toán so sánh của database. Cần chọn collation phù hợp, normalization nhất quán hoặc cột tìm kiếm được chuẩn hóa có kiểm soát.

Một số DB có `ILIKE` (như PostgreSQL, H2), nhưng đó không phải SQL portable cho mọi RDBMS. `ILIKE` cũng vẫn có wildcard `%` và `_`, nên vẫn cần escape input literal. Đừng dùng `ILIKE` mà quên quy tắc tìm kiếm của người dùng.

### 8.1. Cột nullable và logic ba giá trị

`NULL` không giống chuỗi rỗng. Trong SQL:

```sql
SELECT id FROM customers
WHERE display_name LIKE '%Lan%';

SELECT id FROM customers
WHERE display_name NOT LIKE '%Lan%';
```

Nếu `display_name IS NULL`, cả hai điều kiện `LIKE` và `NOT LIKE` đều cho kết quả UNKNOWN chứ không TRUE. `WHERE` không trả hàng NULL. Nếu policy yêu cầu xem NULL là “không khớp”, phải viết tường minh:

```sql
SELECT id FROM customers
WHERE display_name IS NULL
   OR display_name NOT LIKE '%Lan%';
```

Đừng tùy tiện dùng `COALESCE(display_name, '')` vì thay đổi semantics và có thể ảnh hưởng index. Bảng demo không có NULL để tập trung vào wildcard, nhưng query production phải xét schema và kết quả `LEFT JOIN`.

## 9. Hiệu năng của `'prefix%'` và `'%contains%'`

Cùng một chuỗi literal nhưng chế độ tìm kiếm ảnh hưởng lớn tới khả năng dùng index B-tree.

| Mẫu | Mục đích | Khả năng dùng index thường |
| --- | --- | --- |
| `column = ?` | Exact | Thường thuận lợi |
| `column LIKE 'Lan%'` | Prefix | Có thể tối ưu bằng range scan, tùy collation/operator |
| `column LIKE '%Lan'` | Suffix | Wildcard đầu thường làm prefix scan khó |
| `column LIKE '%Lan%'` | Contains | Dễ quét nhiều hàng nếu thiếu index chuyên biệt |
| `LOWER(column) LIKE 'lan%'` | Case-insensitive | Có thể cần expression index hoặc collation index |

Đây là **xu hướng**, không phải cam kết planner: H2, PostgreSQL, MySQL/SQL Server có engine, collation, statistics và index strategy khác nhau. Nên xem `EXPLAIN` hoặc execution plan trên dữ liệu có kích thước thực tế.

Nếu UI là autocomplete, tìm prefix có thể vừa phù hợp UX vừa giảm tải. Nếu sản phẩm thực sự cần tìm substring trên hàng triệu dòng, cân nhắc chức năng `pg_trgm` (PostgreSQL), full-text index hoặc search engine chuyên dụng, cùng benchmark và test semantics. Đừng dùng `'%term%'` cho mọi màn hình chỉ vì nó “dễ tìm ra nhiều kết quả”.

### 9.1. Giới hạn kết quả và quyền truy cập

- Dùng limit/pagination do **server** áp đặt, không chỉ giới hạn số item hiển thị ở client.
- `ORDER BY` ổn định với khóa `id` làm tie-breaker khi paging.
- Lọc tenant/ownership/role; escaping không thay authorization.
- Có query timeout/rate limiting/debounce cho request tìm khi người dùng gõ liên tiếp.
- Tránh `SELECT *`, chỉ lấy cột cần hiển thị.
- Kiểm thử với database production; đo số dòng scan, thời gian query, sử dụng connection pool.

Câu SQL sau phù hợp H2/PostgreSQL, nhưng limit/offset **không portable cho mọi dialect**:

```sql
SELECT id, display_name
FROM customers
WHERE tenant_id = ?
  AND display_name LIKE ? ESCAPE '!'
ORDER BY display_name, id
LIMIT ? OFFSET ?;
```

Các `?` cần bind theo thứ tự tenant, pattern, limit, offset; tất cả phải validate. Với SQL Server/Oracle hoặc các dialect khác, dùng cú pháp phân trang riêng. Truy vấn bắt đầu bằng wildcard có thể vẫn tốn kém dù giới hạn số dòng trả về.

## 10. Khi nào cho phép người dùng gõ wildcard?

Có một số công cụ nội bộ dùng “tìm theo mẫu” có chủ đích. Nên thiết kế thành chế độ rõ:

1. Hiển thị hướng dẫn `%` khớp không hoặc nhiều ký tự, `_` khớp một ký tự.
2. Nêu rõ cách viết literal `%` và `_`, cách escape `!`; hoặc cung cấp UI tách wildcard/literal.
3. Validate độ dài, số wildcard, mẫu quá rộng và quyền truy cập.
4. Bind nguyên pattern được phép bằng tham số; **không bao giờ** nối user SQL syntax.
5. Giới hạn số kết quả, thời gian query và log an toàn, không ghi dữ liệu nhạy cảm tùy tiện.
6. Test với mẫu kết thúc bằng ký tự escape và nhiều chuỗi Unicode.

Với phần lớn sản phẩm, dropdown `Khớp chính xác / Bắt đầu bằng / Chứa` thân thiện và dễ kiểm soát hơn đưa hẳn cú pháp SQL vào giao diện.

## 11. Kiểm thử: đừng chỉ assert query trả một kết quả

Bộ dữ liệu phải có **positive và negative** cases cho từng ký tự đặc biệt:

| Từ khóa và chế độ | Kết quả phải có | Kết quả không được có |
| --- | --- | --- |
| `50%` CONTAINS literal | `50% Sale` | `50 Percent` |
| `Lan_` CONTAINS literal | `Lan_Pro` | `Lany` |
| `Lan!` CONTAINS literal | `Lan! VIP` | `Lan Anh` |
| `%` CONTAINS literal | Tên thực sự có dấu `%` | Mọi tên không chứa `%` |
| `O'Reilly` CONTAINS literal | `O'Reilly` | SQL syntax error |
| `Lan` PREFIX | Tên bắt đầu bằng `Lan` | `ALAN` trong cấu hình phân biệt hoa/thường |
| `null`, `""`, whitespace | Hành vi validation theo policy | Tự biến thành `LIKE '%%'` |

Nên test cả chuỗi chứa `!!`, `!%`, `!_`, ký tự Unicode có dấu, case/accent theo yêu cầu, cột SQL NULL, input quá dài và đồng thời nhiều request.

Test JUnit 5 minh họa cho hàm escape (đoạn test cần dependency/import tương ứng, **không nằm trong project Maven của mục 6**):

```java
@Test
void escapesWildcardAndEscapeCharacter() {
    assertEquals("50!%!_!!", escapeLikeLiteral("50%_!"));
    assertEquals("!!", escapeLikeLiteral("!"));
    assertEquals("!_", escapeLikeLiteral("_"));
}
```

Test chuỗi chỉ chứng minh thuật toán Java. **Integration test** với JDBC driver/DB phù hợp mới xác nhận `ESCAPE '!'`, collation, Unicode và query results. Khi production dùng PostgreSQL/MySQL/SQL Server, hãy test trên database đó, không chỉ dựa vào H2.

## 12. Lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nối `userInput` trực tiếp vào SQL | SQL injection, lỗi dấu apostrophe | Bind bằng `?`/`:name` |
| Bind `LIKE ?` nhưng không escape literal | Input `%`/`_` thay đổi phạm vi khớp | Escape cả wildcard và marker |
| Escape `!` sau cùng | Nhân đôi marker mới thêm làm sai mẫu | Escape `!` trước `%` và `_` |
| Quên `ESCAPE '!'` | DB có thể diễn giải `!%` sai | SQL/hàm escape cùng quy ước |
| Input rỗng thành `LIKE '%%'` | Kết quả quá rộng, truy vấn đắt | Quy định reject/empty/browse |
| Coi `LOWER` là tìm không dấu | Sai ngữ nghĩa tiếng Việt | Collation/normalization và test |
| Dùng contains cho autocomplete khổng lồ | Index thường khó tối ưu | Prefix hoặc index text search |
| Tin `NOT LIKE` tự nhận SQL NULL | Kết quả mất bản ghi NULL | Có `IS NULL` nếu policy yêu cầu |
| Không sort mà phân trang | Trùng/thiếu kết quả | `ORDER BY` ổn định |
| Không giới hạn kết quả | DB, mạng và heap quá tải | Limit, paging, timeout, rate limit |
| Ghép tên cột/sort từ request | Injection ở identifier | Enum/allowlist |
| Giả định mọi DB đều như H2 | Sai collation/escape/index behavior | Integration test trên dialect thật |

## 13. Quy trình thiết kế một API tìm kiếm thực tế

1. **Xác định search contract:** EXACT/PREFIX/CONTAINS, literal hay pattern, case/accent.
2. **Validate server-side:** blank, null, độ dài, whitespace, giới hạn và quyền truy cập.
3. **Escape literal:** `!` rồi `%` và `_`; thêm wildcard đúng chế độ.
4. **Bind tham số:** dùng `JdbcTemplate` hoặc `NamedParameterJdbcTemplate`, không nối input vào SQL.
5. **Giữ SQL có cấu trúc cố định:** tên cột/sort từ allowlist, không nhận expression tùy ý.
6. **Đặt ESCAPE tường minh:** thống nhất với hàm Java và test ký tự đặc biệt.
7. **Đặt limit/ORDER BY/paging:** tránh truy vấn không giới hạn.
8. **Kiểm thử end-to-end:** positive/negative wildcard, apostrophe, null, Unicode, dialect.
9. **Đo chi phí:** index, EXPLAIN, thời gian query, pool và khả năng chịu tải.

### Câu hỏi tự kiểm tra

1. Vì sao `'Lan%'` khớp `Lan`, còn `'Lan_'` thì không?
2. Nếu `LIKE ?` nhận pattern `"%"`, truy vấn có SQL injection không? Có thể trả quá nhiều dữ liệu không?
3. Cần truyền pattern nào để tìm chứa literal `50%_!` với `ESCAPE '!'`?
4. Vì sao phải escape marker `!` trước khi xử lý `%` và `_`?
5. Tại sao bind `O'Reilly` bằng `?` không cần tự xử lý dấu nháy đơn?
6. `NULL NOT LIKE '%Lan%'` có đưa hàng NULL vào `WHERE` không?
7. Tại sao `'%Lan%'` thường tốn kém hơn `'Lan%'` với B-tree?
8. `LOWER(name)` đã đủ để tìm không dấu tiếng Việt chưa?
9. Có thể bind tên cột `ORDER BY` bằng `?` không?
10. Ngoài escaping, cần các chính sách nào để tránh trả dữ liệu quá rộng hoặc trái quyền?

**Kết luận:** `LIKE` dùng `%` và `_` làm wildcard. Với ô tìm kiếm thông thường, input phải được xem là **literal theo mặc định**; escape `%`, `_` và escape marker bằng `ESCAPE` tường minh, rồi chỉ thêm wildcard theo chế độ mà ứng dụng quyết định. Spring `JdbcTemplate` bảo vệ cú pháp SQL qua binding, nhưng correctness còn phụ thuộc chính sách search, collation/Unicode, SQL NULL, pagination, authorization và đo hiệu năng.

### Tài liệu tham khảo chính thức

- Spring Framework — JDBC Core: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — JdbcTemplate JavaDoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Spring Framework — Named Parameters: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- H2 Database — LIKE and ESCAPE: https://h2database.github.io/html/grammar.html
- PostgreSQL — Pattern Matching: https://www.postgresql.org/docs/current/functions-matching.html

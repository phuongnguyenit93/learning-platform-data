# Tái sử dụng RowMapper giữa JdbcTemplate và NamedParameterJdbcTemplate

> **Mục tiêu:** Khi cùng một bảng hoặc tập cột SQL được truy vấn theo tham số vị trí (`?`) và tham số có tên (`:name`), viết **một `RowMapper<T>` duy nhất** để ánh xạ hàng kết quả thành đối tượng Java; dùng lại mapper đó với cả `JdbcTemplate` (template cổ điển) và `NamedParameterJdbcTemplate` (template có tên). Hiểu ranh giới giữa **ràng buộc tham số**, **thực thi SQL** và **ánh xạ ResultSet**, cách kiểm thử tính tương đương và các tình huống không nên tái sử dụng máy móc.

**Ngữ cảnh:** Spring Framework → Data Access → *Tham số có tên*. Đây là bài về **tái sử dụng logic đọc dữ liệu** khi chuyển giữa hai phong cách truy vấn JDBC của Spring, không phải bài tạo JPA entity, cấu hình ORM hay thay toàn bộ DAO bằng một framework khác.

## 1. Trả lời ngắn gọn: có thể dùng chung RowMapper không?

**Có.** Cả `JdbcTemplate` lẫn `NamedParameterJdbcTemplate` đều có overload `query(...)` và `queryForObject(...)` nhận một đối tượng `org.springframework.jdbc.core.RowMapper<T>`. Cùng một mapper có thể được truyền cho cả hai API, miễn là kết quả SQL của hai câu truy vấn có **các cột, alias, kiểu dữ liệu và ý nghĩa** phù hợp với mapper.

```text
JdbcTemplate                                 NamedParameterJdbcTemplate
SQL ... WHERE category = ?                   SQL ... WHERE category = :category
               |                                         |
       Java values theo vị trí                    Map / SqlParameterSource
               |                                         |
               +---------- Spring JDBC ------------------+
                                     |
                      PreparedStatement / ResultSet
                                     |
                             RowMapper<Book>
                                     |
                          mapRow(ResultSet, rowNum)
                                     |
                              Book / DTO Java
```

**Khác nhau ở đầu vào SQL:** template cổ điển dùng placeholder `?` và danh sách tham số **theo vị trí**; template có tên dùng `:name` và `Map`/`SqlParameterSource` để Spring chuyển thành JDBC placeholders tương ứng. **Giống nhau ở đầu ra:** sau khi câu SQL chạy và có `ResultSet`, mapper được gọi cho từng hàng theo cùng hợp đồng `RowMapper<T>`.

Hai template không cần hai kiểu mapper khác nhau. **Không viết `ClassicBookMapper` và `NamedBookMapper` với logic giống hệt chỉ vì cách bind tham số khác.**

## 2. Ba trách nhiệm tách biệt: SQL, bind và map

Giả sử muốn lấy sách thuộc nhóm "Java".

**Câu SQL tham số vị trí:**

```sql
SELECT id, title, category, price, in_stock
FROM books
WHERE category = ?
ORDER BY id;
```

**Câu SQL tham số có tên:**

```sql
SELECT id, title, category, price, in_stock
FROM books
WHERE category = :category
ORDER BY id;
```

Cả hai truy vấn đều yêu cầu tập cột như nhau và cùng thứ tự kết quả. Chỉ cách đưa giá trị `"Java"` vào điều kiện WHERE là khác.

| Phần trách nhiệm | Template cổ điển | Template có tên | RowMapper có liên quan không? |
| --- | --- | --- | --- |
| Tạo SQL | `WHERE category = ?` | `WHERE category = :category` | Không cần biết placeholder |
| Bind tham số | `"Java"` tại vị trí `1` | `category → "Java"` | Không bind input |
| Thực thi | `JdbcTemplate`/JDBC | `NamedParameterJdbcTemplate` chuyển named SQL rồi dùng JDBC | Không tự mở connection/query |
| Duyệt ResultSet | Spring JDBC | Spring JDBC | Nhận **một hàng hiện tại** |
| Đọc cột | `rs.getLong("id")`… | Như hệt | **Có** |
| Tạo DTO | `new Book(...)` | Như hệt | **Có** |
| Đóng tài nguyên | Spring JDBC | Spring JDBC | Không tự đóng `ResultSet` |

`RowMapper` **không** chứa logic quyết định WHERE, ORDER BY, pagination hay tham số truyền vào. Hợp đồng của nó là **biến hàng hiện tại của ResultSet thành một đối tượng Java**.

## 3. Hợp đồng chính thức của RowMapper<T>

`RowMapper<T>` là một functional interface có phương thức cốt lõi:

```java
@FunctionalInterface
public interface RowMapper<T> {
    T mapRow(ResultSet rs, int rowNum) throws SQLException;
}
```

Đây là **mô tả chữ ký để học**, không phải file interface mà bạn phải tự tạo: interface thực tế đã nằm trong Spring JDBC.

- `rs` là `ResultSet` **đang trỏ tới hàng cần đọc**. Framework đã thực hiện `rs.next()` trước khi gọi `mapRow`.
- `rowNum` là chỉ số hàng của kết quả đang duyệt, **bắt đầu từ 0**. Nó không phải id của bản ghi trong DB.
- `T` là kiểu đối tượng được tạo cho mỗi hàng: record, DTO, JavaBean hay kiểu đơn giản.
- Hàm có thể ném `SQLException`. Spring JDBC sẽ xử lý/dịch exception theo cơ chế data access; không cần catch và nuốt mọi lỗi trong mapper.
- `mapRow` có thể trả `null` theo hợp đồng API, nhưng ứng dụng thường nên map thành object có nghĩa và quy định null semantics rõ ràng.
- **Không gọi `rs.next()`, `rs.close()`, `statement.close()` hoặc `connection.close()` trong `mapRow`**. Template điều khiển vòng đời cursor và tài nguyên.
- **Không cache `ResultSet` rồi dùng sau**: mapper được gọi trong thời gian result set còn mở; hãy trích dữ liệu và trả về object Java độc lập.

Một mapper tốt thường **stateless**: không giữ dữ liệu mutable giữa các lần gọi, không tăng counter để quyết định nội dung, không lưu trạng thái của hàng trước. Theo Javadoc, `RowMapper` stateless thường có thể tái sử dụng hiệu quả.

### Ví dụ mapper thủ công cho Java record

Giả sử database có cột `id` (BIGINT), `title` (VARCHAR), `category` (VARCHAR), `price` (DECIMAL) và `in_stock` (BOOLEAN), đều `NOT NULL`:

```java
public record Book(
        long id,
        String title,
        String category,
        BigDecimal price,
        boolean inStock) {}

public static final RowMapper<Book> BOOK_MAPPER =
        (rs, rowNum) -> new Book(
                rs.getLong("id"),
                rs.getString("title"),
                rs.getString("category"),
                rs.getBigDecimal("price"),
                rs.getBoolean("in_stock"));
```

Đây là **snippet**, cần import `BigDecimal` và `RowMapper`, đồng thời đặt record/field vào class Java hợp lệ; project chạy đầy đủ ở mục 7.

Mapper này không biết truy vấn sử dụng `?` hay `:category`. Nó chỉ cần `ResultSet` có đúng năm cột (hoặc alias tương ứng). Vì mapper không giữ state riêng cho mỗi query nên **cùng instance `BOOK_MAPPER`** có thể truyền vào nhiều lời gọi khác nhau.

## 4. Cùng một mapper: cách gọi JdbcTemplate và NamedParameterJdbcTemplate

### 4.1. JdbcTemplate: tham số theo vị trí

```java
List<Book> classics = jdbcTemplate.query(
        "SELECT id, title, category, price, in_stock " +
        "FROM books WHERE category = ? ORDER BY id",
        BOOK_MAPPER,
        "Java");
```

Đây là overload `query(String sql, RowMapper<T> rowMapper, Object... args)`: giá trị `"Java"` được bind vào dấu `?` đầu tiên. Nếu có nhiều `?`, thứ tự `args` phải khớp thứ tự dấu hỏi. Trường hợp code cũ có overload dạng `query(sql, Object[] args, mapper)`, hãy đọc chữ ký; nhiều overload cũ hiện đã bị deprecate, không nên sao chép máy móc sang code mới.

### 4.2. NamedParameterJdbcTemplate: Map hoặc SqlParameterSource

```java
List<Book> named = namedJdbcTemplate.query(
        "SELECT id, title, category, price, in_stock " +
        "FROM books WHERE category = :category ORDER BY id",
        Map.of("category", "Java"),
        BOOK_MAPPER);
```

`NamedParameterJdbcTemplate` nhận giá trị theo key `category`, phân tích câu SQL có `:category` và chuyển thành JDBC statement với bind parameter tương ứng. **Mapper truyền vào hoàn toàn giống dòng trên**.

Khi muốn khai báo JDBC type (đặc biệt SQL NULL) hoặc nhiều giá trị, dùng `MapSqlParameterSource`:

```java
SqlParameterSource params = new MapSqlParameterSource()
        .addValue("category", "Java", Types.VARCHAR);

List<Book> named = namedJdbcTemplate.query(
        "SELECT id, title, category, price, in_stock " +
        "FROM books WHERE category = :category ORDER BY id",
        params,
        BOOK_MAPPER);
```

Lưu ý cần import `org.springframework.jdbc.core.namedparam.MapSqlParameterSource` và `SqlParameterSource`, cùng `java.sql.Types`. `SqlParameterSource` **chỉ phụ trách cung cấp input values**, còn `RowMapper` vẫn phụ trách **output result rows**.

### 4.3. Hai API thực ra cùng dùng hạ tầng Spring JDBC

`NamedParameterJdbcTemplate` **bọc/delegate** một classic `JdbcTemplate`, không phải subclass của nó. Nó triển khai `NamedParameterJdbcOperations`, còn template cổ điển triển khai `JdbcOperations`. Tạo wrapper trên instance có sẵn là hợp lệ:

```java
JdbcTemplate classic = new JdbcTemplate(dataSource);
NamedParameterJdbcTemplate named =
        new NamedParameterJdbcTemplate(classic);
```

Nếu đã inject `NamedParameterJdbcTemplate` mà cần một method chỉ có ở template cổ điển, có thể dùng `named.getJdbcOperations()` để truy cập giao diện `JdbcOperations`; `named.getJdbcTemplate()` cung cấp implementation cụ thể khi cần. **Không cần hai mapper hoặc hai data source** chỉ để dùng hai loại placeholder.

Với Spring Boot, có thể inject cả hai template đã cấu hình; ví dụ trong mục 7 cố ý tạo `NamedParameterJdbcTemplate` từ chính `JdbcTemplate` đang inject để thấy rõ cùng nền tảng.

## 5. Điều kiện để tái sử dụng thật sự an toàn

Sử dụng cùng mapper là đúng khi **result contract** giống nhau, không nhất thiết SQL giống hệt từng ký tự. Bạn có thể thay đổi điều kiện lọc, thứ tự sắp xếp, JOIN hoặc paging, miễn là cột cần cho mapper vẫn tồn tại với kiểu/ngữ nghĩa mong đợi.

**Điều kiện quan trọng:**

1. **Column names/aliases:** Mapper gọi `rs.getString("title")` thì SQL phải SELECT cột tên/alias `title`. `SELECT title AS name` không còn đáp ứng contract trừ khi sửa mapper hoặc alias lại.
2. **Data types:** `rs.getLong("id")` cần dữ liệu có thể chuyển sang long; `rs.getBigDecimal("price")` cần số thập phân phù hợp.
3. **NULL semantics:** `getBoolean`/`getLong` trả primitive mặc định khi gặp SQL NULL; nếu SQL cột nullable, cần dùng `rs.wasNull()` hoặc wrapper/nullable mapping thay vì giả định không có null.
4. **Projection đầy đủ:** Query `SELECT id, title` không thể dùng một mapper vẫn truy cập `category`, `price` và `in_stock`. Hãy mở rộng projection hoặc dùng một mapper dành riêng cho DTO rút gọn.
5. **JOIN trùng tên cột:** `SELECT b.id, a.id` gây cột `id` mơ hồ. Chỉ định alias rõ như `b.id AS book_id`, `a.id AS author_id` và mapper tương ứng.
6. **Loại domain object:** `RowMapper<Book>` phải trả `Book`; không reuse bằng cast sang `RowMapper<Order>` chỉ vì các cột có tên gần giống.
7. **Tính thuần/ít state:** Tránh shared mutable counters, xử lý network hoặc giữ `ResultSet` ngoài callback. Nếu mapper phụ thuộc timezone/locale, hãy giữ dependency đó immutable và được cấu hình rõ.
8. **Chính sách chuyển đổi:** `BigDecimal` scale, timestamp timezone, enum và vendor types cần nhất quán qua các query.

Ví dụ hai câu SQL **khác filter nhưng cùng projection**:

```sql
-- Dùng với JdbcTemplate:
SELECT id, title, category, price, in_stock
FROM books WHERE category = ?
ORDER BY id;

-- Dùng với NamedParameterJdbcTemplate:
SELECT id, title, category, price, in_stock
FROM books WHERE id IN (:ids)
ORDER BY id;
```

Dù điều kiện khác nhau, cả hai có thể dùng `BOOK_MAPPER` vì cột kết quả cùng contract.

### Contract rõ hơn bằng constant projection

Ở DAO có nhiều truy vấn, một cách tránh sai tên cột là định nghĩa projection thống nhất:

```java
private static final String BOOK_COLUMNS =
        "id, title, category, price, in_stock";

private static final RowMapper<Book> BOOK_MAPPER = (rs, n) ->
        new Book(rs.getLong("id"), rs.getString("title"),
                rs.getString("category"), rs.getBigDecimal("price"),
                rs.getBoolean("in_stock"));
```

Khi query có JOIN, không ghép projection vào SQL thiếu alias; hãy tạo projection phù hợp thực tế. Một constant tránh lặp cột nhưng **không thay thế kiểm tra truy vấn/mapper bằng test**.

## 6. Cách tổ chức RowMapper cho mã có thể bảo trì

Có ba lựa chọn thông dụng, tất cả dùng được với classic và named template:

| Cách tổ chức | Ví dụ | Nên dùng khi |
| --- | --- | --- |
| `private static final RowMapper<Book>` lambda | `(rs,n) -> new Book(...)` | Mapping ngắn, không state, tập trung trong DAO hoặc config |
| Class mapper riêng | `public final class BookRowMapper implements RowMapper<Book>` | Mapping dài, nhiều DAO dùng chung hoặc cần unit test riêng |
| Spring mapper tích hợp | `BeanPropertyRowMapper` / `DataClassRowMapper` | Mapping dựa tên cột/property phù hợp và không cần logic domain đặc biệt |

### 6.1. Một mapper class riêng, không phụ thuộc template

```java
package com.example.library;

import java.sql.ResultSet;
import java.sql.SQLException;
import org.springframework.jdbc.core.RowMapper;

public final class BookRowMapper implements RowMapper<Book> {
    @Override
    public Book mapRow(ResultSet rs, int rowNum) throws SQLException {
        return new Book(
                rs.getLong("id"),
                rs.getString("title"),
                rs.getString("category"),
                rs.getBigDecimal("price"),
                rs.getBoolean("in_stock"));
    }
}
```

Đây là **snippet về tổ chức mã**, yêu cầu `Book` là type có thể truy cập trong cùng package/import. Class không lưu `JdbcTemplate`, `DataSource` hay query string. Cả `JdbcTemplate.query(..., mapper, args)` và `NamedParameterJdbcTemplate.query(..., params, mapper)` đều dùng được `new BookRowMapper()`; bạn cũng có thể tạo một instance singleton để tránh lập lại allocation. Không cần thêm `@Component` chỉ để truyền mapper cho API.

### 6.2. BeanPropertyRowMapper: JavaBean mutable

`BeanPropertyRowMapper<BookBean>` có thể map cột `in_stock` sang property JavaBean `inStock` nếu tên khớp convention và bean có constructor không tham số/setters thích hợp.

```java
RowMapper<BookBean> beanMapper =
        BeanPropertyRowMapper.newInstance(BookBean.class);
```

Nó không yêu cầu bạn viết từng `rs.getXxx` nhưng cần kiểm tra setter, alias, conversion và nullability; không phải giải pháp cho mọi DTO phức tạp. Nếu object là **Java record immutable**, hãy dùng mapper lambda/constructor hoặc loại hỗ trợ data class.

### 6.3. DataClassRowMapper: Java record và constructor binding

`DataClassRowMapper` hỗ trợ Java records và kiểu có constructor với tên tham số tương ứng cột:

```java
RowMapper<Book> mapperForRecord =
        DataClassRowMapper.newInstance(Book.class);
```

Với `Book(long id, String title, String category, BigDecimal price, boolean inStock)` và alias/cột `in_stock` tương ứng `inStock`, mapper có thể bind qua record canonical constructor. Tuy nhiên để dùng auto-mapper phải kiểm thử column aliases, constructor parameter names, Java/SQL nullable types và conversion trên version Spring thực tế. **Trong ví dụ chạy ở mục 7, mapper thủ công được chọn** để hành vi rõ ràng, không phụ thuộc quy ước auto-mapping.

### 6.4. Khi nào không nên “dùng chung mọi thứ”?

Đừng ép một `RowMapper<Book>` dùng cho báo cáo chỉ trả `COUNT(*)` hoặc DTO tổng hợp có tên/kiểu khác. Chọn `SingleColumnRowMapper` hoặc `queryForObject(sql, Integer.class, ...)` cho giá trị đơn, và mapper riêng cho projection của báo cáo.

**Nguyên tắc:** Tái sử dụng *contract ánh xạ kết quả*, không phải tái sử dụng tên class bằng mọi giá.

## 7. Bài thực hành chạy được: cùng một RowMapper, hai phong cách parameter

Project dùng **Java 17+, Maven, Spring Boot 3.5.16, Spring JDBC, H2 in-memory**. Spring Boot 3.5.16 được phát hành ngày 25/06/2026 và là bản OSS cuối của nhánh 3.5.x; nó được chọn để demo có phiên bản cố định. **Dự án mới nên chọn dòng Spring Boot còn được hỗ trợ**, thay vì sao chép version chỉ vì ví dụ này.

Bài thực hành dùng một bảng `books`. Hai truy vấn đầu **cùng projection, cùng filter và cùng thứ tự** để có thể so sánh hai `List<Book>`; truy vấn thứ ba dùng named list parameter `:ids` nhưng vẫn dùng mapper đó.

### 7.1. Cấu trúc thư mục

```text
rowmapper-reuse/
├── pom.xml
└── src/main/
    ├── java/com/example/rowmapping/RowMapperReuseApplication.java
    └── resources/
        ├── application.properties
        ├── schema.sql
        └── data.sql
```

### 7.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>rowmapper-reuse</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.3. src/main/resources/schema.sql

```sql
CREATE TABLE books (
    id BIGINT PRIMARY KEY,
    title VARCHAR(120) NOT NULL,
    category VARCHAR(60) NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    in_stock BOOLEAN NOT NULL
);
```

### 7.4. src/main/resources/data.sql

```sql
INSERT INTO books (id, title, category, price, in_stock)
VALUES (1, 'Java Basics', 'Java', 12.50, TRUE);

INSERT INTO books (id, title, category, price, in_stock)
VALUES (2, 'Spring JDBC', 'Java', 29.90, TRUE);

INSERT INTO books (id, title, category, price, in_stock)
VALUES (3, 'SQL 101', 'Database', 17.00, FALSE);

INSERT INTO books (id, title, category, price, in_stock)
VALUES (4, 'Index Tuning', 'Database', 35.00, TRUE);
```

### 7.5. src/main/resources/application.properties

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=ERROR
spring.datasource.url=jdbc:h2:mem:rowmapperdemo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
```

### 7.6. src/main/java/com/example/rowmapping/RowMapperReuseApplication.java

```java
package com.example.rowmapping;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

@SpringBootApplication
public class RowMapperReuseApplication {

    public record Book(
            long id,
            String title,
            String category,
            BigDecimal price,
            boolean inStock) {}

    // Một instance dùng chung cho mọi query có đúng projection.
    private static final RowMapper<Book> BOOK_MAPPER =
            (rs, rowNum) -> new Book(
                    rs.getLong("id"),
                    rs.getString("title"),
                    rs.getString("category"),
                    rs.getBigDecimal("price"),
                    rs.getBoolean("in_stock"));

    private static final String COLUMNS =
            "SELECT id, title, category, price, in_stock FROM books ";

    public static void main(String[] args) {
        SpringApplication.run(RowMapperReuseApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc) {
        return args -> {
            // Wrapper có tên dùng chính classic JdbcTemplate đã inject.
            NamedParameterJdbcTemplate named =
                    new NamedParameterJdbcTemplate(jdbc);

            // A. Classic: WHERE category = ?.
            List<Book> classics = jdbc.query(
                    COLUMNS + "WHERE category = ? ORDER BY id",
                    BOOK_MAPPER,
                    "Java");

            // B. Named: WHERE category = :category.
            List<Book> byNames = named.query(
                    COLUMNS + "WHERE category = :category ORDER BY id",
                    Map.of("category", "Java"),
                    BOOK_MAPPER);

            System.out.println("classicIds=" + ids(classics));
            System.out.println("namedIds=" + ids(byNames));
            System.out.println("sameRows=" + classics.equals(byNames));

            // C. Named :ids được expand theo danh sách đầu vào.
            List<Book> selected = named.query(
                    COLUMNS + "WHERE id IN (:ids) ORDER BY id",
                    new MapSqlParameterSource(
                            "ids", List.of(1L, 3L)),
                    BOOK_MAPPER);
            System.out.println("selectedIds=" + ids(selected));

            // D. Hai cách queryForObject với cùng mapper.
            Book singleClassic = jdbc.queryForObject(
                    COLUMNS + "WHERE id = ?",
                    BOOK_MAPPER,
                    3L);
            Book singleNamed = named.queryForObject(
                    COLUMNS + "WHERE id = :id",
                    Map.of("id", 3L),
                    BOOK_MAPPER);
            System.out.println("singleTitle=" + singleClassic.title());
            System.out.println(
                    "sameSingle=" + singleClassic.equals(singleNamed));

            // E. query nhiều hàng không tìm thấy trả danh sách rỗng.
            List<Book> missing = named.query(
                    COLUMNS + "WHERE category = :category",
                    Map.of("category", "Missing"),
                    BOOK_MAPPER);
            System.out.println("emptyCount=" + missing.size());
        };
    }

    private static List<Long> ids(List<Book> books) {
        return books.stream().map(Book::id).toList();
    }
}
```

**Chạy** trong thư mục chứa `pom.xml`, với JDK 17+ và Maven:

```bash
mvn spring-boot:run
```

**Bảy dòng do ứng dụng tự in**, không tính log khởi động Maven/Spring:

```text
classicIds=[1, 2]
namedIds=[1, 2]
sameRows=true
selectedIds=[1, 3]
singleTitle=SQL 101
sameSingle=true
emptyCount=0
```

**Tại sao output này đáng tin?**

1. `schema.sql` tạo bảng trong H2; `data.sql` thêm bốn sách có ID 1–4.
2. Query classic và named đều filter `category='Java'`, và `ORDER BY id` để kết quả cố định: cùng hai bản ghi id 1 và 2.
3. Java `record` có `equals` dựa trên thành phần; cùng projection và giá trị được map bằng một `BOOK_MAPPER` nên hai `List<Book>` tương đương từng phần tử. `sameRows=true` kiểm chứng cả **nội dung**, không chỉ số hàng.
4. `IN (:ids)` nhận danh sách `1,3`; Spring chuyển thành danh sách placeholders JDBC tương ứng. Kết quả được sắp id tăng dần.
5. Hai `queryForObject` đều nhận ID 3 và map thành sách `SQL 101`; record equality xác nhận cùng ý nghĩa dữ liệu.
6. Query category `Missing` không có hàng; `query(...)` trả `List` rỗng, `emptyCount=0`.
7. **Không có một lần nào phải viết lại mapper**. `BOOK_MAPPER` giữ nguyên, chỉ SQL template và cách bind thay đổi.

*Giới hạn demo:* H2 đủ cho ví dụ nền tảng, nhưng production phải kiểm thử với driver/DB thật. Đây là project Maven multi-file; không chạy riêng file Java bằng `javac` nếu chưa có dependency Spring/H2. Toàn bộ khối code demo được thiết kế chạy với các API Spring 6.x trong Boot 3.5.16; phần lệnh và stdout là mô tả kỳ vọng, không thay cho integration test trên môi trường của bạn.

## 8. Khi dùng queryForObject, query và Stream: mapper vẫn giống, cardinality khác

Cả hai template đều cung cấp:

- `query(...)` + `RowMapper<T>`: trả `List<T>`; không có hàng → list rỗng; nhiều hàng → một đối tượng mapped cho mỗi hàng.
- `queryForObject(...)` + `RowMapper<T>`: **mong chính xác một hàng**; 0 hàng thường ném `EmptyResultDataAccessException`, nhiều hàng ném `IncorrectResultSizeDataAccessException`. Một mapper có thể trả `null` cho chính hàng được map, nên kiểu trả có thể nullable.
- API dạng streaming như `queryForStream(...)`: vẫn dùng mapper nhưng **Stream phải được đóng** bằng `try-with-resources`, vì còn tài nguyên JDBC đang mở. Không trả stream lười qua biên transaction mà không quy định ai sở hữu và đóng.

Ví dụ một bản ghi (snippet với mapper và template đã khai báo):

```java
Book byId = jdbcTemplate.queryForObject(
        "SELECT id, title, category, price, in_stock " +
        "FROM books WHERE id = ?",
        BOOK_MAPPER,
        1L);

Book sameBook = namedJdbcTemplate.queryForObject(
        "SELECT id, title, category, price, in_stock " +
        "FROM books WHERE id = :id",
        Map.of("id", 1L),
        BOOK_MAPPER);
```

**Sai lầm:** `queryForObject` không phải `findObject` của một vài API `SqlQuery` trong gói khác. Không áp mặc định “không thấy thì trả null” cho `JdbcTemplate.queryForObject`. Nếu nghiệp vụ cho phép thiếu, dùng `query(...)` rồi áp dụng chính sách `Optional` hoặc bắt đúng exception có chủ đích.

### Stream cùng mapper và trách nhiệm đóng

```java
// Snippet: Stream phải tồn tại trong thời gian resources còn mở.
try (Stream<Book> rows = namedJdbcTemplate.queryForStream(
        "SELECT id, title, category, price, in_stock " +
        "FROM books WHERE category = :category",
        Map.of("category", "Java"),
        BOOK_MAPPER)) {
    rows.forEach(book -> System.out.println(book.title()));
}
```

Cần `import java.util.stream.Stream`. Đây là snippet minh họa, không được dùng để tạo output cố định của mục 7. **RowMapper không đóng stream**; caller của `queryForStream` có trách nhiệm đóng. Kết quả stream còn có thể phụ thuộc transaction/fetch size/driver.

## 9. Tái sử dụng mapper khi named SQL có danh sách IN hoặc điều kiện thay đổi

`NamedParameterJdbcTemplate` hỗ trợ một collection cho `IN (:ids)`, tự tạo số `?` tương ứng rồi bind từng giá trị:

```java
List<Long> ids = List.of(10L, 20L, 30L);
List<Book> books = namedJdbcTemplate.query(
        "SELECT id, title, category, price, in_stock " +
        "FROM books WHERE id IN (:ids) ORDER BY id",
        new MapSqlParameterSource("ids", ids),
        BOOK_MAPPER);
```

**Khác phần input; mapper không đổi.** Tuy nhiên:

- **Danh sách rỗng:** `IN ()` có thể là cú pháp không hợp lệ theo database. Nếu yêu cầu "không chọn ID nào", trả `List.of()` trước query hoặc chọn nhánh SQL có ngữ nghĩa rõ, thay vì đoán driver xử lý.
- **Giới hạn số phần tử:** DB có giới hạn bind parameters và `IN` expressions. Với nhiều ID, cân nhắc bảng tạm, join, chunking hoặc chiến lược DB phù hợp; vẫn có thể giữ mapper.
- **Không bind identifier:** `:columnName` không thể thay tên cột/`ORDER BY`. Phần SQL động cần allowlist tên cột/tables đã tin cậy.
- **Không đánh đồng mapper với tham số có tên:** Mapper hoạt động sau khi SQL chạy, không cần biết `:ids` ban đầu có bao nhiêu giá trị.

### Pagination và sort

Cùng mapper dùng được cho SQL có `LIMIT/OFFSET` (nếu DB hỗ trợ), miễn projection thống nhất. Cần thống nhất `ORDER BY` ổn định, tránh phân trang cho kết quả không deterministic. Named SQL nhiều filter đôi khi dễ bảo trì hơn positional, nhưng đó là lợi ích về **input binding**, không làm `RowMapper` map tốt hơn.

## 10. Tham số NULL và xử lý NULL của cột kết quả là hai vấn đề độc lập

**NULL đầu vào (WHERE/bind):** Với `NamedParameterJdbcTemplate` có thể khai báo SQL type qua `MapSqlParameterSource`:

```java
SqlParameterSource params = new MapSqlParameterSource()
        .addValue("name", null, Types.VARCHAR);
```

Ví dụ trên chỉ là cách cung cấp typed NULL. **Cảnh báo:** SQL `WHERE title = NULL` không so khớp hàng như `WHERE title IS NULL` trong SQL ba giá trị. Nếu filter tùy chọn, hãy chọn câu SQL/điều kiện `IS NULL` phù hợp nghiệp vụ, không nghĩ bind null sẽ tự viết lại toán tử so sánh.

**NULL đầu ra (ResultSet):** Cả hai template gửi cùng cột đến cùng mapper; nếu cột nullable, mapper phải bảo toàn đúng ý nghĩa:

```java
RowMapper<BookStatus> statusMapper = (rs, rowNum) -> {
    long id = rs.getLong("id");

    boolean raw = rs.getBoolean("available");
    Boolean available = rs.wasNull() ? null : raw;

    return new BookStatus(id, available);
};
```

Cần `record BookStatus(long id, Boolean available) {}` và tên cột `available`; snippet minh họa. Nếu dùng `rs.getBoolean` trả `false` rồi bỏ qua `wasNull()`, SQL NULL có thể bị hiểu là false. Với kiểu số nguyên `getInt/getLong` cũng có bẫy tương tự.

**Định dạng số:** `BigDecimal` giữ precision/scale thập phân tốt hơn `double` đối với tiền. Hai query có thể map BigDecimal mang scale khác nếu DB hoặc SQL cast khác; record equality của `BigDecimal` còn xét scale. Vì vậy so sánh output giữa hai template chỉ hợp lý khi cả truy vấn có cùng phép biến đổi và cột.

**Ngày giờ:** Nếu mapper đọc `LocalDateTime` hoặc `Timestamp`, lựa chọn kiểu SQL/driver và chính sách timezone vẫn quan trọng, nhưng không bị quyết định bởi việc SQL bind theo vị trí hay có tên.

## 11. Tách phần mapping khỏi DAO và service như thế nào?

Khi một DAO có hai đường tìm kiếm — tìm theo ID bằng `JdbcTemplate` và tìm theo nhóm bằng `NamedParameterJdbcTemplate` — tổ chức kiểu sau giúp tránh duplicate mapping:

```text
BookService
    |
    v
BookDao
   |-- JdbcOperations classic
   |-- NamedParameterJdbcOperations named
   |
   +-- RowMapper<Book> BOOK_MAPPER (một nơi)
   |
   |-- findById(id): classic queryForObject
   |-- findByCategories(categories): named query IN (:categories)
   '-- findInStock(): query dùng một trong hai template
```

Service không cần biết `ResultSet`; DAO trả về record/DTO hoặc list đã được map. Nếu cùng mapper dùng qua nhiều DAO, đặt class `BookRowMapper` trong package data access dùng chung; tránh đặt ở controller hay domain object vì đó là chi tiết JDBC.

**Không nhất thiết tạo mapper làm Spring bean:** một stateless `private static final RowMapper<Book>` trong DAO đủ tốt. Còn khi mapping phức tạp cần inject converter (ví dụ money, timezone policy) bạn có thể tạo một mapper class với dependency bất biến và inject như bean. Dù cách nào, đừng đặt mutable state theo request vào singleton mapper.

### Ví dụ chống duplicated code

**Trước** (không mong muốn):

```java
List<Book> a = jdbc.query(sqlA, (rs, i) ->
        new Book(rs.getLong("id"), rs.getString("title"),
                 rs.getString("category"), rs.getBigDecimal("price"),
                 rs.getBoolean("in_stock")), "Java");

List<Book> b = named.query(sqlB, params, (rs, i) ->
        new Book(rs.getLong("id"), rs.getString("title"),
                 rs.getString("category"), rs.getBigDecimal("price"),
                 rs.getBoolean("in_stock")));
```

**Sau** (chỉ thay duplication mapping, không đổi nghiệp vụ):

```java
RowMapper<Book> bookMapper = (rs, i) ->
        new Book(rs.getLong("id"), rs.getString("title"),
                 rs.getString("category"), rs.getBigDecimal("price"),
                 rs.getBoolean("in_stock"));

List<Book> a = jdbc.query(sqlA, bookMapper, "Java");
List<Book> b = named.query(sqlB, params, bookMapper);
```

Các đoạn trên là **snippet với sqlA/sqlB/jdbc/named/params đã có**, không phải chương trình độc lập. Lợi ích là sửa logic mapping ở một nơi; nhưng cần test hai query trả đúng các cột đã hứa.

## 12. Đặt cạnh JdbcClient, RowCallbackHandler và ResultSetExtractor

Trong Spring Framework 6.1+, `JdbcClient` cung cấp fluent API kết hợp positional/named binding trong cùng facade; nó cũng chấp nhận `RowMapper<T>`:

```java
// Snippet: JdbcClient client đã được tạo từ datasource/template.
List<Book> books = client.sql(
        "SELECT id, title, category, price, in_stock " +
        "FROM books WHERE category = :category")
        .param("category", "Java")
        .query(BOOK_MAPPER)
        .list();
```

`JdbcClient` không làm `RowMapper` trở nên không cần thiết. Bạn có thể giữ mapper khi nâng cấp từ classic/named templates sang fluent API, rồi đổi từng call site có regression test. Advanced cases như batch hoặc stored procedure có thể vẫn dùng template trực tiếp.

**Phân biệt callback:**

| Callback | Trách nhiệm | Tái sử dụng qua classic/named? |
| --- | --- | --- |
| `RowMapper<T>` | Map **mỗi hàng** thành một `T`, template gom list hoặc lấy single | **Có**, chủ đề bài này |
| `RowCallbackHandler` | Xử lý từng hàng bằng side effect/callback, không tự trả một `T` | Một số overload của cả hai template chấp nhận; API/hợp đồng khác |
| `ResultSetExtractor<T>` | Được quyền xử lý **toàn bộ ResultSet** và trả một kết quả tùy ý | Dùng overload tương ứng, không thay trực tiếp cho RowMapper |
| `PreparedStatementSetter` | Bind input và tùy chọn statement | Không phải mapper, không map kết quả |
| `SqlParameterSource` | Cung cấp named input values/type | Không phải mapper, không đọc ResultSet |

Một `RowMapper` không nên tự lặp `while (rs.next())` hay tính tổng nhiều hàng, vì mỗi callback đã có một row hiện hành. Nếu cần map cấu trúc parent-child có nhiều hàng cho một object, hoặc aggregate toàn ResultSet, cân nhắc `ResultSetExtractor` hoặc query khác với thiết kế phù hợp.

## 13. Transaction và tài nguyên: dùng chung mapper không quyết định giao dịch

`JdbcTemplate` và `NamedParameterJdbcTemplate` đều dùng Spring JDBC và quản lý tạo/đóng `PreparedStatement`/`ResultSet` cho query thông thường. `NamedParameterJdbcTemplate` delegate xuống classic operations, nên bản thân việc đổi dạng placeholder không làm một `RowMapper` sở hữu connection.

**Nếu cùng datasource và transaction manager,** các lời gọi từ service `@Transactional` có thể tham gia cùng database transaction. Nhưng reuse mapper **không tự tạo transaction**:

```java
// Ví dụ minh họa, giả định DAO có hai query method.
@Service
public class BookReportService {
    private final BookDao dao;

    public BookReportService(BookDao dao) {
        this.dao = dao;
    }

    @Transactional(readOnly = true)
    public List<Book> report() {
        List<Book> a = dao.findClassic();
        List<Book> b = dao.findNamed();
        return a.size() >= b.size() ? a : b;
    }
}
```

Đây là snippet kiến trúc cần imports và `BookDao` thực tế. `@Transactional(readOnly=true)` là hint/hướng dẫn cho hạ tầng, **không đảm bảo mọi driver ngăn ghi**; mức isolation và việc hai query thấy cùng snapshot tùy cấu hình DB/transaction. Đừng mở transaction kéo dài chỉ để reuse mapper.

Cũng không đóng `ResultSet`, `Statement` hoặc `Connection` bên trong mapper. Sau khi `query(...)` hoàn tất, dữ liệu đã map thành record/DTO có thể được sử dụng độc lập với JDBC resources.

## 14. Bẫy thường gặp khi tái sử dụng RowMapper

1. **Viết hai mapper y hệt chỉ vì `?` khác `:name`.** Hai template dùng chung `RowMapper<T>`; tái sử dụng logic output, không nhân bản code.
2. **Tưởng RowMapper bind input.** Binding nằm ở template/`SqlParameterSource`; `mapRow` chạy sau query.
3. **Gọi `rs.next()` trong mapper.** Template đã di chuyển cursor; mapper gọi thêm sẽ bỏ qua hàng hoặc làm kết quả sai.
4. **Đóng `ResultSet` trong mapper.** Làm hỏng xử lý các hàng tiếp theo; template quản lý resource.
5. **Giữ `ResultSet` trong object để đọc sau.** Cursor có thể đã đóng khi query trả về.
6. **SQL projection không trùng:** query thứ hai thiếu `price` hay đổi alias `title` → `name`, khiến cùng mapper thất bại.
7. **JOIN có hai cột `id`:** mapper có thể đọc nhầm; alias rõ ràng trước khi tái sử dụng.
8. **Sử dụng `rowNum` như ID nghiệp vụ.** Nó là chỉ số dòng kết quả, bắt đầu 0.
9. **Đưa dữ liệu request vào field mutable của mapper singleton.** Dễ race giữa các thread; truyền filter qua SQL parameter, không qua mapper.
10. **Bỏ qua nullable SQL:** primitive getter có thể che `NULL` thành 0/false; dùng nullable type/`wasNull()`.
11. **Nhầm `query` rỗng với `queryForObject` rỗng.** `query` trả list rỗng; `queryForObject` yêu cầu đúng một hàng và có thể ném exception.
12. **Giả định SQL tương đương chỉ vì mapper giống.** WHERE/ORDER BY/JOIN/pagination có thể đổi tập dữ liệu.
13. **Sử dụng `BeanPropertyRowMapper` cho record không có setters.** Chọn `DataClassRowMapper` hoặc constructor-based manual mapper.
14. **Dùng named params để bind tên bảng/cột.** `:column` bind giá trị, không thay SQL identifier. Dùng allowlist nếu cần SQL động.
15. **Dùng `IN (:ids)` với list rỗng tùy tiện.** Kết quả/cú pháp phụ thuộc DB; xử lý empty list có chủ đích.
16. **Quên đóng queryForStream.** Stream còn nắm JDBC resource; dùng try-with-resources.
17. **Refactor mà không test cardinality/null/precision.** Code mới có thể compile nhưng thay nghĩa nghiệp vụ.
18. **Coi reuse mapper là cache kết quả.** Mapper chỉ là hàm ánh xạ; hai query vẫn chạy SQL riêng, không tự cache rows.

## 15. Kiểm thử tính tương đương của hai template

Một bài test tin cậy phải xác minh **kết quả và mapping**, không chỉ số lượng object. Nên chuẩn bị database fixture cố định, dùng cùng mapper và query tương đương về projection/filter/sort.

### Test cases tối thiểu

| Test | Kỳ vọng |
| --- | --- |
| Category có 2 bản ghi, classic vs named | Hai `List<Book>` bằng nhau khi thứ tự được bảo đảm |
| Category không có bản ghi | Cả hai `query(...)` trả list rỗng |
| Query bằng ID có đúng 1 bản ghi | Hai `queryForObject` trả record bằng nhau |
| ID không tồn tại với `queryForObject` | Cả hai theo contract ném `EmptyResultDataAccessException` |
| SQL trả >1 hàng cho `queryForObject` | Lỗi cardinality thay vì lấy phần tử đầu |
| Cột nullable | Mapper giữ null đúng, không ép thành 0/false tùy tiện |
| JOIN/alias | Mapper đọc đúng bảng/cột, không mơ hồ |
| `IN (:ids)` với 1, nhiều, rỗng | List expansion đúng; empty case xử lý rõ |
| SQL lỗi/schema thay đổi | Cả hai báo lỗi `DataAccessException` phù hợp |
| Transaction có nhiều query | Cùng datasource/manager, đọc được theo isolation mong muốn |

Có thể dùng Spring Boot `@JdbcTest`/integration test với H2 cho logic cơ bản; cần DB giống production khi hành vi phụ thuộc dialect, encoding, query plan, timezone hoặc isolation.

**Đừng bỏ `ORDER BY` rồi kiểm tra `List.equals` một cách mặc định:** SQL không đảm bảo thứ tự hàng khi không có ORDER BY. Nếu nghiệp vụ chỉ quan tâm tập ID, sort để so sánh hoặc so theo `Set` khi các phần tử không trùng theo contract.

### Một assert minh họa

```java
List<Book> classic = jdbc.query(sqlClassic, BOOK_MAPPER, "Java");
List<Book> named = namedJdbc.query(
        sqlNamed, Map.of("category", "Java"), BOOK_MAPPER);

if (!classic.equals(named)) {
    throw new AssertionError("Classic and named mappings differ");
}
```

Snippet trên cần cùng projection, điều kiện/sort tương đương và dữ liệu test cố định; trong dự án thực hãy dùng JUnit/AssertJ tương ứng. Cùng instance mapper là điều kiện **giảm duplication**, không bảo đảm hai câu SQL trả cùng bản ghi.

## 16. Một lộ trình refactor an toàn từ code cũ

Nếu DAO đang chứa hai anonymous mapper giống nhau:

1. **Ghi nhận hành vi hiện tại:** SQL, tất cả alias, kiểu dữ liệu, cách xử lý NULL, chính sách cardinality, thứ tự rows và exception.
2. **Tách một `RowMapper<Book>` stateless** khỏi hai call site; lúc này chưa đổi SQL hay tham số.
3. **Cho cả `JdbcTemplate` và `NamedParameterJdbcTemplate` dùng cùng instance mapper**; chạy test đối chiếu.
4. **Nếu muốn chuyển positional sang named**, đổi từng SQL `?` → `:name` và chuyển args sang `Map`/`SqlParameterSource`, **giữ mapper** không đổi.
5. **Kiểm tra những khác biệt ngầm:** `queryForObject` vs `query`, nulls, alias, required columns, order, vendor conversion, transactions.
6. **Đo và kiểm thử sau thay đổi:** repository integration test, số câu SQL, thời gian/connection pool, tải đồng thời và phân quyền DB.
7. Nếu tương lai đổi qua `JdbcClient`, **có thể tiếp tục dùng mapper**; không cần viết lại mapping chỉ vì fluent API.

*Không nhất thiết migration bằng mọi giá.* DAO đang hoạt động và dễ hiểu có thể giữ nguyên hai API nếu nghiệp vụ cần. Mục tiêu ưu tiên là **tập trung mapping logic**, để sửa một chỗ, kiểm thử đúng và không thay đổi hành vi.

## 17. Tự kiểm tra có đáp án

**Câu 1:** `JdbcTemplate` dùng `?`, còn `NamedParameterJdbcTemplate` dùng `:category`. Có cần hai `RowMapper<Book>` khác nhau?  
**Đáp án:** Không. Cùng mapper nếu kết quả SQL có cột/alias/type phù hợp. Khác biệt placeholder chỉ ảnh hưởng input binding.

**Câu 2:** Một mapper thực thi `rs.next()` trước khi `getString("title")`. Có đúng contract không?  
**Đáp án:** Sai. Framework đã đặt `rs` ở hàng hiện tại; gọi `next()` trong mapper có thể bỏ hàng.

**Câu 3:** Query classic SELECT đủ `id,title,category,price,in_stock`. Query named chỉ SELECT `id,title`. Có dùng cùng mapper hiện tại được không?  
**Đáp án:** Không, vì mapper truy cập những cột query named không trả. Sửa projection/alias hoặc tạo mapper cho DTO rút gọn.

**Câu 4:** `MapSqlParameterSource` và `RowMapper` cùng làm gì?  
**Đáp án:** `MapSqlParameterSource` cung cấp **input named values và SQL types**; `RowMapper` ánh xạ **output rows**.

**Câu 5:** `queryForObject` không có hàng trả `null` hay exception?  
**Đáp án:** Với cả hai template Spring JDBC, query mong chính xác một hàng; 0 hàng thường ném `EmptyResultDataAccessException`. Có thể trả null khi có một hàng và mapper tự trả null.

**Câu 6:** Có nên đặt một `static final RowMapper<Book>` cho nhiều request?  
**Đáp án:** Có nếu nó stateless và dependencies an toàn; không nếu mapper lưu mutable request state/connection/ResultSet.

**Câu 7:** SQL `IN (:ids)` với list rỗng sẽ thế nào?  
**Đáp án:** Không tự giả định có kết quả rỗng hợp lệ; empty list có thể tạo SQL không hợp lệ. Xử lý trước khi gọi DB hoặc chọn chiến lược khác được kiểm thử.

**Câu 8:** `BeanPropertyRowMapper` có phải lựa chọn mặc định cho Java record?  
**Đáp án:** Không. Java record là immutable và không có JavaBean setters; ưu tiên `DataClassRowMapper` hoặc mapper constructor/lambda tường minh.

**Câu 9:** Named template query và classic query chạy trong cùng `@Transactional` có vì mapper chung?  
**Đáp án:** Không. Transaction phụ thuộc datasource/transaction manager và lời gọi qua Spring transaction advice; mapper không mở transaction.

**Câu 10:** Có thể dùng mapper đã tạo với `JdbcClient` không?  
**Đáp án:** Có. `JdbcClient` hỗ trợ truyền `RowMapper<T>` cho việc ánh xạ row; những API advanced khác có thể vẫn cần template.

## 18. Checklist khi review code

- [ ] Đã phân biệt `JdbcTemplate` (positional) và `NamedParameterJdbcTemplate` (named) ở phần SQL input.
- [ ] Có **một RowMapper<T> stateless** dùng chung nếu cùng result contract.
- [ ] Mapper chỉ đọc hàng hiện tại, **không gọi `next()`/`close()`**.
- [ ] SQL classic/named trả đủ các cột, alias và kiểu cần cho mapper.
- [ ] Không truyền dữ liệu request hay connection vào mutable field của mapper.
- [ ] Mỗi method dùng đúng overload `query`/`queryForObject` và cardinality mong muốn.
- [ ] Named parameter map có đủ key và type; positional arguments đúng thứ tự.
- [ ] SQL có thể khác WHERE nhưng mapper vẫn phù hợp khi projection giống nhau.
- [ ] `IN (:ids)` có handling list rỗng và giới hạn của DB.
- [ ] Nullable SQL, `BigDecimal`, timestamp và boolean có chính sách mapping cụ thể.
- [ ] Không đóng resource Spring sở hữu; stream được đóng khi sử dụng.
- [ ] Cả hai đường query có integration tests kiểm chứng mapping/exception/transaction.

## Tài liệu tham khảo chính thức

- Spring Framework — Using the JDBC Core Classes / JdbcTemplate / NamedParameterJdbcTemplate: https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html
- Spring Javadoc — `RowMapper<T>`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/RowMapper.html
- Spring Javadoc — `JdbcTemplate`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Spring Javadoc — `NamedParameterJdbcTemplate`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcTemplate.html
- Spring Javadoc — `MapSqlParameterSource`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/namedparam/MapSqlParameterSource.html
- Spring Javadoc — `BeanPropertyRowMapper`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/BeanPropertyRowMapper.html
- Spring Javadoc — `DataClassRowMapper`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/DataClassRowMapper.html
- Spring Framework — Parameter Handling / IN expression list: https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/parameter-handling.html
- Spring Boot 3.5.16 release: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/

**Ghi nhớ:** **`RowMapper` là hợp đồng ánh xạ *đầu ra*, độc lập với cú pháp tham số *đầu vào*.** Khi kết quả SQL có cùng cột/alias/type, cùng một `RowMapper<Book>` hoạt động cho `JdbcTemplate.query(sql, mapper, args)` và `NamedParameterJdbcTemplate.query(sql, params, mapper)`. Đây là cách giảm lặp, giữ mapping thống nhất và giúp chuyển từ `?` sang `:name` mà không phải viết lại logic đọc từng hàng.
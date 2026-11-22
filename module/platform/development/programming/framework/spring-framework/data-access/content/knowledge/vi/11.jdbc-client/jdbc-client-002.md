# Tạo client từ DataSource hoặc template phù hợp

> **Ý chính:** Từ **Spring Framework 6.1**, `org.springframework.jdbc.core.simple.JdbcClient` cung cấp API fluent thống nhất cho truy vấn và cập nhật JDBC, hỗ trợ cả tham số theo vị trí `?` và tham số có tên `:name`. Có ba factory method thông dụng: **`JdbcClient.create(DataSource)`**, **`JdbcClient.create(JdbcOperations)`** và **`JdbcClient.create(NamedParameterJdbcOperations)`**. Hãy chọn theo tài nguyên đã được cấu hình: nếu chỉ có `DataSource`, tạo từ nguồn kết nối; nếu đã có `JdbcTemplate` hoặc `NamedParameterJdbcTemplate` được cấu hình riêng, **ưu tiên tái sử dụng template tương ứng** để giữ các tùy chỉnh của nó.

Nội dung này tập trung vào **cách tạo, chọn, khai báo bean và sử dụng `JdbcClient` đúng với kiến trúc Spring Data Access**. Một `JdbcClient` không phải kết nối vật lý, không tự tạo thêm database và không thay thế mọi tính năng chuyên sâu của `JdbcTemplate`.

## 1. Đặt JdbcClient đúng tầng trừu tượng

Các kiểu liên quan:

```java
import javax.sql.DataSource;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcOperations;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.core.simple.JdbcClient;
```

- **`DataSource`** (`javax.sql.DataSource`): nguồn cung cấp `java.sql.Connection`. Nó có thể kết nối trực tiếp hoặc đi qua connection pool như HikariCP.
- **`JdbcOperations`**: interface chứa các thao tác JDBC cấp cao dùng tham số theo vị trí, được `JdbcTemplate` hiện thực.
- **`JdbcTemplate`**: implementation Spring JDBC dùng `DataSource`, quản lý connection, statement, result set, callback và chuyển nhiều `SQLException` thành `DataAccessException`.
- **`NamedParameterJdbcOperations`**: interface cho thao tác SQL có named parameters, được `NamedParameterJdbcTemplate` hiện thực.
- **`NamedParameterJdbcTemplate`**: cung cấp `:id`, `:name` và các nguồn tham số `SqlParameterSource`; nó dùng `JdbcTemplate` ở tầng dưới.
- **`JdbcClient`**: interface fluent bao ngoài các operations/template nói trên, thống nhất cách viết các truy vấn và cập nhật thông dụng.

Sơ đồ:

```text
Service / Repository
       |
       v
    JdbcClient
       |
       +---- tham số ? ----------> JdbcOperations / JdbcTemplate
       |
       +---- tham số :name ------> NamedParameterJdbcOperations
       |                             / NamedParameterJdbcTemplate
       |                                       |
       +---------------------------------------+
                                               |
                                               v
                                          JdbcTemplate
                                               |
                                               v
                                           DataSource
                                               |
                                               v
                                            Connection
                                               |
                                               v
                                           Database
```

Đây là **sơ đồ trách nhiệm**; khi tạo client từ `JdbcOperations`, Spring có thể tạo wrapper named-parameter phù hợp dùng chung delegate đó. Không diễn giải sơ đồ thành quy tắc "mỗi `JdbcClient` mở một connection mới". Vòng đời của connection tiếp tục do `DataSource`, pool và transaction manager quyết định.

### JdbcClient là API nào?

`JdbcClient` là **interface**, không gọi `new JdbcClient()`. Dùng factory tĩnh `JdbcClient.create(...)` để nhận implementation, hoặc inject bean do Spring Boot/Spring configuration đã cung cấp.

```java
JdbcClient client = JdbcClient.create(dataSource);
```

Đây là **một câu lệnh minh họa trong method**, có biến `DataSource dataSource` đã được cấu hình. Đầu ra của `create(...)` là object fluent dùng lặp lại; nó không phải JDBC `Connection` và **không cần gọi `close()` sau mỗi query**.

Một truy vấn đơn giản:

```java
Long count = client.sql("SELECT COUNT(*) FROM books WHERE price >= ?")
    .param(new java.math.BigDecimal("100.00"))
    .query(Long.class)
    .single();
```

Các phần:

1. `sql(...)` mở đầu một mô tả statement.
2. `param(...)` bind một giá trị vào marker `?`.
3. `query(Long.class)` chỉ định kiểu ánh xạ kết quả.
4. `single()` yêu cầu kết quả đúng một hàng; `COUNT(*)` không `GROUP BY` phù hợp vì luôn cho ra một hàng, kể cả khi giá trị đếm là 0.

Câu lệnh chỉ chạy khi gọi terminal operation `single()`. `sql(...)` và `param(...)` xây cấu hình của request; không phải mỗi lần gọi chúng đều gửi query tới DB. Khi query kết thúc, JDBC resource được quản lý bởi các template bên dưới.

## 2. Ba factory method quan trọng

`JdbcClient` công bố ba cách tạo chính, mỗi cách có một đối tượng đầu vào khác nhau:

| Factory method | Cần có sẵn | Khi nào dùng | Điều nên nhớ |
| --- | --- | --- | --- |
| `JdbcClient.create(DataSource)` | `DataSource` | Spring Framework thuần, ví dụ nhỏ, hoặc chưa có template tùy chỉnh | Spring tạo các delegate JDBC cần thiết từ data source |
| `JdbcClient.create(JdbcOperations)` | `JdbcOperations`, thường là `JdbcTemplate` | Đã có `JdbcTemplate` được cấu hình; muốn giữ cài đặt của nó | Tái sử dụng delegate hiện có, bao gồm data source và cấu hình template |
| `JdbcClient.create(NamedParameterJdbcOperations)` | `NamedParameterJdbcOperations`, thường là `NamedParameterJdbcTemplate` | Đã có named-parameter template; muốn dùng lại cả cấu hình phía dưới | Tái sử dụng named-parameter delegate hiện có |

Các phương thức factory trên thuộc Spring Framework 6.1+. Không nên dùng một dự án Spring Framework 6.0 rồi mong import `JdbcClient` thành công: API chưa tồn tại ở nhánh đó.

Với cùng một `DataSource` và cấu hình template mặc định, ba lựa chọn có thể cho kết quả SQL tương đương. Khác biệt đáng lưu ý là **mức độ tái sử dụng cấu hình và object đã có**, không phải "DataSource chỉ hỗ trợ `?`, còn named template chỉ hỗ trợ `:name`". `JdbcClient` cung cấp cả hai kiểu tham số qua facade thống nhất.

## 3. Lựa chọn A: tạo từ DataSource

Nếu ứng dụng đã có một bean `DataSource` nhưng chưa có template cần tái sử dụng:

```java
import javax.sql.DataSource;
import org.springframework.jdbc.core.simple.JdbcClient;

public final class SimpleBookReader {
    private final JdbcClient client;

    public SimpleBookReader(DataSource dataSource) {
        this.client = JdbcClient.create(dataSource);
    }

    public long countBooks() {
        Long value = client.sql("SELECT COUNT(*) FROM books")
            .query(Long.class)
            .single();
        return java.util.Objects.requireNonNull(value);
    }
}
```

Đây là class Java 17+ **cần Spring JDBC trên classpath**, một `DataSource` được cấp vào constructor và bảng `books` đã tồn tại lúc chạy. Không có `main`, nên không phải chương trình chạy độc lập. `JdbcClient.create(dataSource)` là điểm khởi tạo; lần `countBooks()` sẽ dùng data source đó để thực thi SQL.

### Khai báo bean trong Spring Framework thuần

```java
package example;

import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.simple.JdbcClient;

@Configuration
public class JdbcClientConfig {
    @Bean
    JdbcClient jdbcClient(DataSource dataSource) {
        return JdbcClient.create(dataSource);
    }
}
```

Tệp nên là `src/main/java/example/JdbcClientConfig.java` trong dự án Spring có component scanning/`@Import` thích hợp. **Điều kiện tiên quyết:** trong context phải tồn tại đúng một `DataSource` phù hợp, hoặc phải thêm `@Qualifier` để chọn đúng bean khi có nhiều nguồn dữ liệu.

Khi có bean, repository chỉ cần constructor injection:

```java
public BookRepository(JdbcClient client) {
    this.client = client;
}
```

Đoạn trên là constructor nằm trong một class đã khai báo field `JdbcClient client` và cần import kiểu đó; không phải class độc lập.

### DataSource tạo từ đâu?

- Spring Boot có thể auto-configure `DataSource` dựa trên JDBC dependencies và `spring.datasource.*`.
- Ứng dụng Spring Framework thuần có thể tự tạo `@Bean DataSource` bằng pool, hoặc nhận từ JNDI/container.
- Dù nguồn dữ liệu có dùng connection pool hay không, `JdbcClient` chỉ cần hợp đồng `DataSource`.

**Không khởi tạo pool mới trong mỗi repository hoặc mỗi HTTP request.** `DataSource`/pool thường là tài nguyên dùng chung; tạo thêm các pool không cần thiết làm tăng connection tới database và khó kiểm soát transaction.

### Hạn chế khi chỉ dùng DataSource

Giả sử một `JdbcTemplate` hiện có đã được tùy chỉnh `setQueryTimeout(...)`, `setFetchSize(...)`, `setMaxRows(...)` hoặc `setExceptionTranslator(...)`. Nếu gọi `JdbcClient.create(dataSource)` để tạo một bộ delegate **mới**, bạn **không nên mặc định tin** rằng mọi cấu hình runtime của `JdbcTemplate` cũ sẽ được kế thừa. Trong trường hợp này, lựa chọn B/C ở các mục sau giúp giữ đúng template đã có.

## 4. Lựa chọn B: tạo từ JdbcOperations/JdbcTemplate hiện có

`JdbcTemplate implements JdbcOperations`, nên có thể tạo `JdbcClient` từ template đã cấu hình.

```java
import javax.sql.DataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.simple.JdbcClient;

JdbcTemplate template = new JdbcTemplate(dataSource);
template.setQueryTimeout(15);
template.setFetchSize(100);

JdbcClient client = JdbcClient.create(template);
```

Đây là **mảnh code trong phương thức cấu hình** có `DataSource dataSource` đã tồn tại. Nó không phải một tệp Java độc lập.

Khi `JdbcClient.create(template)` được gọi, Java chọn overload dành cho `JdbcOperations`. Template vẫn là delegate thực hiện công việc JDBC. Điều này đặc biệt có giá trị nếu template cũ đã có:
- `DataSource` đã được kiểm tra và định tuyến đúng;
- thời gian chờ câu lệnh (`query timeout`);
- kích cỡ fetch (`fetchSize`), giới hạn số hàng (`maxRows`);
- SQL exception translator hoặc một số cấu hình thực thi cụ thể.

Tùy driver, các gợi ý như `fetchSize` không nhất thiết có cùng tác động với mọi SQL. Nhưng về kiến trúc, **client dùng template hiện hữu**, không tạo một template hoàn toàn độc lập rồi làm mất thông số mà code đã thiết lập.

### Inject theo interface

Có thể không phụ thuộc trực tiếp vào class `JdbcTemplate`:

```java
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.jdbc.core.simple.JdbcClient;

public final class BookLookup {
    private final JdbcClient client;

    public BookLookup(JdbcOperations operations) {
        this.client = JdbcClient.create(operations);
    }
}
```

`BookLookup` là class có thể được Spring tạo nếu bean `JdbcOperations` đã tồn tại; thường bean thực tế là `JdbcTemplate`. Không biến `JdbcOperations` thành `DataSource`: đây là hai abstraction khác nhau.

Nếu tạo một bean `JdbcClient` thủ công:

```java
@Configuration
class ExistingTemplateClientConfig {
    @Bean
    JdbcClient jdbcClient(JdbcTemplate jdbcTemplate) {
        return JdbcClient.create(jdbcTemplate);
    }
}
```

Đoạn `@Configuration` cần các import `org.springframework.context.annotation.Configuration`, `Bean`, `org.springframework.jdbc.core.JdbcTemplate` và `org.springframework.jdbc.core.simple.JdbcClient`. Nó là **phương án cấu hình thay thế**, **không đặt đồng thời** với bean `JdbcClientConfig` ở mục 3 nếu cả hai đều tạo bean cùng ý nghĩa mà không có tên/`@Qualifier` rõ ràng.

**Không tự ý thay bean `JdbcTemplate` đã được cấu hình sang `new JdbcTemplate(dataSource)`** trong khi phần còn lại của ứng dụng vẫn dùng bean cũ. Dù cùng DB, khác biệt timeout, exception translation và policy thực thi có thể gây khó debug.

## 5. Lựa chọn C: tạo từ NamedParameterJdbcOperations

Một ứng dụng dùng `NamedParameterJdbcTemplate` thường có nhiều truy vấn với tham số tên `:id`, `:status`, `:minPrice`. Nếu template đó đã được cấu hình, có thể tạo client bằng overload nhận `NamedParameterJdbcOperations`:

```java
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.core.simple.JdbcClient;

JdbcClient client = JdbcClient.create(namedParameterJdbcTemplate);
```

`namedParameterJdbcTemplate` là một biến bean đã được cấu hình, thuộc kiểu `NamedParameterJdbcTemplate`. Đoạn trên thuộc một method/configuration chứ không phải class độc lập.

Ví dụ tạo template từ `JdbcTemplate` hiện có:

```java
JdbcTemplate classic = new JdbcTemplate(dataSource);
classic.setQueryTimeout(10);

NamedParameterJdbcTemplate named =
    new NamedParameterJdbcTemplate(classic);

JdbcClient client = JdbcClient.create(named);
```

`JdbcTemplate` và `NamedParameterJdbcTemplate` là các lớp Spring JDBC; `dataSource` phải được cung cấp trước. Khi lấy `JdbcClient` từ `named`, client tái sử dụng named delegate và `JdbcTemplate` phía dưới, bao gồm `DataSource` và các cài đặt liên quan.

### Tạo bean theo named template

```java
@Configuration
class NamedTemplateClientConfig {
    @Bean
    JdbcClient jdbcClient(
            NamedParameterJdbcTemplate namedParameterJdbcTemplate) {
        return JdbcClient.create(namedParameterJdbcTemplate);
    }
}
```

Đây là **phương án cấu hình độc lập với các phương án A/B**, chỉ áp dụng khi context đã có bean `NamedParameterJdbcTemplate` và các import tương ứng. Không tạo ba bean `JdbcClient` cùng kiểu chỉ để thử ba overload trong một context; nếu cần nhiều database/client thật, phải định danh bean rõ ràng.

### Một client vẫn hỗ trợ cả hai kiểu tham số

Dù tạo từ `DataSource`, `JdbcOperations` hay `NamedParameterJdbcOperations`, API facade `JdbcClient` có thể xử lý cả positional và named parameters trong những trường hợp phổ biến:

**Positional:**

```java
long id = 7L;
var result = client.sql("SELECT title FROM books WHERE id = ?")
    .param(id)
    .query(String.class)
    .optional();
```

**Named:**

```java
long id = 7L;
var result = client.sql("SELECT title FROM books WHERE id = :id")
    .param("id", id)
    .query(String.class)
    .optional();
```

Hai khối trên là **hai lựa chọn thay thế** cho cùng một method, không khai báo đồng thời biến `result` trong cùng phạm vi. Với 0 hàng, `optional()` trả `Optional.empty()`; với nhiều hơn một hàng, operation kỳ vọng tối đa một kết quả nên có thể ném lỗi kích thước kết quả. Với `SELECT title`, nếu giá trị SQL của cột là `NULL`, cần xét hợp đồng map nullable và ý nghĩa của `Optional`.

**Không trộn `?` và `:id` một cách tùy tiện trong cùng một câu SQL.** Chọn một kiểu nhất quán cho statement. Việc Spring phải parse và bind tên tham số không biến nó thành cơ chế thay tên bảng/cột; các placeholder chỉ đại diện cho **giá trị**.

## 6. Spring Boot: có thể inject JdbcClient mà không cần gọi create

Trong Spring Boot **3.2+**, khi Spring JDBC và các auto-configuration cần thiết khả dụng, Boot có thể tạo sẵn `JdbcTemplate`, `NamedParameterJdbcTemplate` và `JdbcClient`. Đặc biệt, `JdbcClientAutoConfiguration` phụ thuộc sự có mặt của một ứng viên `NamedParameterJdbcTemplate` phù hợp và không tạo bean mới khi đã có bean `JdbcClient` do người dùng định nghĩa.

Đường thông dụng:

```text
Spring Boot + spring-boot-starter-jdbc + JDBC driver
                       |
                       v
                Auto-config DataSource
                       |
                       v
                Auto-config JdbcTemplate
                       |
                       v
            Auto-config NamedParameterJdbcTemplate
                       |
                       v
                 Auto-config JdbcClient
                       |
                       v
             Inject vào repository/service
```

Repository có thể nhận thẳng client qua constructor:

```java
package example;

import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public final class BookStore {
    private final JdbcClient jdbc;

    public BookStore(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public long countBooks() {
        return java.util.Objects.requireNonNull(
            jdbc.sql("SELECT COUNT(*) FROM books")
                .query(Long.class)
                .single()
        );
    }
}
```

Đây là bean repository khi package `example` được Spring component scan, database có bảng `books` và context có bean `JdbcClient`. Không có `main` nên code không độc lập.

**Ưu tiên inject bean auto-configured** khi nó đáp ứng nhu cầu. Nếu Spring Boot đã có `JdbcClient`, gọi `JdbcClient.create(dataSource)` bên trong mọi repository không nhất thiết sai về chức năng nhưng dễ lặp cấu hình và làm bỏ qua các tùy chỉnh của `JdbcTemplate` mà Boot hoặc dự án đã áp dụng, ví dụ `spring.jdbc.template.*`.

### Khi nào vẫn cần khai báo @Bean JdbcClient thủ công trong Boot?

- Ứng dụng có nhiều `DataSource`/template và cần tạo client cho một nguồn cụ thể.
- Muốn cấu hình/đặt tên bean độc lập và không dựa vào auto-configuration mặc định.
- Có template đặc thù đã thiết lập các chính sách khác với template mặc định.

Khi khai báo bean thủ công, nên cân nhắc cơ chế `@ConditionalOnMissingBean` của Boot và số bean cùng kiểu thực tế. Một định nghĩa thủ công có thể làm auto-configuration của `JdbcClient` nhường chỗ; điều này là chủ đích nếu bạn thực sự muốn thay thế bean mặc định.

### Điều kiện lỗi thường gặp

Nếu project dùng **Spring Framework 6.0** hoặc **Spring Boot 3.1**, việc import `JdbcClient` sẽ không biên dịch vì phiên bản Spring Framework đi kèm chưa có API. Cần nâng cấp lên bản hỗ trợ (Spring 6.1+/Boot 3.2+) hoặc tiếp tục sử dụng `JdbcTemplate`/`NamedParameterJdbcTemplate`.

Nếu context không có `DataSource` hợp lệ, bean client cũng không tự sinh ra kết nối DB. Nếu có nhiều data sources/templates và không có ứng viên ưu tiên, auto-configuration có thể không tạo được một `JdbcClient` duy nhất; phải thiết kế bean rõ ràng.

## 7. Ví dụ chạy được: Spring Boot + JdbcClient lấy từ hạ tầng đã cấu hình

Ví dụ dùng **Java 17+, Spring Boot 3.3.x**, `spring-boot-starter-jdbc` và H2 in-memory. Mục đích: thấy Boot cung cấp bean `JdbcClient`, repository dùng fluent API cho cả `:name` và `?`, còn `JdbcTemplate` và `DataSource` bên dưới được dùng chung đúng cách.

Tạo một dự án Spring Boot Gradle 3.3.x có plugin Boot và dependency management như dự án Spring Boot thông thường. Trong phần `dependencies` của `build.gradle`, khai báo:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

Đây là **khối dependencies để ghép vào dự án Boot đã có build script**, không phải toàn bộ file Gradle. Spring Boot 3.3.x tương ứng với Spring Framework 6.1.x và Java 17.

### 7.1. Cấu hình DataSource

**`src/main/resources/application.yml`:**

```yaml
spring:
  datasource:
    url: "jdbc:h2:mem:jdbc_client_demo;DB_CLOSE_DELAY=-1"
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
```

H2 in-memory cho phép thử không cần server database độc lập. Nếu dùng PostgreSQL/MySQL trong môi trường thật, cần driver, JDBC URL và credential tương ứng. Không hard-code credential production trong repository.

### 7.2. Record dữ liệu

**`src/main/java/example/Book.java`:**

```java
package example;

import java.math.BigDecimal;

public record Book(long id, String code, String title, BigDecimal price) {}
```

`record` có từ Java 16, phù hợp với Java 17. `price` dùng `BigDecimal` để tránh sai số nhị phân của `double` khi lưu giá tiền kiểu SQL `DECIMAL`.

### 7.3. Repository chỉ phụ thuộc JdbcClient

**`src/main/java/example/BookCatalogRepository.java`:**

```java
package example;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public final class BookCatalogRepository {
    private static final RowMapper<Book> BOOK_MAPPER =
        (rs, rowNum) -> new Book(
            rs.getLong("id"),
            rs.getString("code"),
            rs.getString("title"),
            rs.getBigDecimal("price")
        );

    private final JdbcClient jdbc;

    public BookCatalogRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public int insert(Book book) {
        return jdbc.sql("""
                INSERT INTO book_catalog (id, code, title, price)
                VALUES (:id, :code, :title, :price)
                """)
            .param("id", book.id())
            .param("code", book.code())
            .param("title", book.title())
            .param("price", book.price())
            .update();
    }

    public Optional<Book> findById(long id) {
        return jdbc.sql("""
                SELECT id, code, title, price
                FROM book_catalog
                WHERE id = :id
                """)
            .param("id", id)
            .query(BOOK_MAPPER)
            .optional();
    }

    public List<Book> findAtLeast(BigDecimal minimum) {
        return jdbc.sql("""
                SELECT id, code, title, price
                FROM book_catalog
                WHERE price >= ?
                ORDER BY id
                """)
            .param(minimum)
            .query(BOOK_MAPPER)
            .list();
    }

    public int rename(long id, String newTitle) {
        return jdbc.sql("UPDATE book_catalog SET title = ? WHERE id = ?")
            .param(newTitle)
            .param(id)
            .update();
    }
}
```

Với mỗi method:
- `insert` dùng bốn named parameters; tên trong `:id`, `:code`, `:title`, `:price` phải khớp tên đã bind.
- `findById` trả `Optional<Book>`. `optional()` không yêu cầu ứng dụng phải bắt exception "zero rows"; nếu truy vấn có nhiều hơn một hàng, hợp đồng một kết quả vẫn được bảo vệ.
- `findAtLeast` dùng positional `?` và `param(minimum)`; `ORDER BY id` bảo đảm thứ tự kết quả thay vì dựa vào thứ tự lưu trữ.
- `rename` có hai marker, bind newTitle trước id; giá trị `update()` là số hàng tác động. Nếu ID không tồn tại, thường trả 0.
- `BOOK_MAPPER` chuyển `ResultSet` thành `Book`; lớp ở trên là repository Spring được component-scan, không tự quản lý connection.

Đáng lưu ý, **cùng một bean `JdbcClient` phục vụ cả hai phong cách tham số**; không cần tạo hai client hoặc hai `DataSource` chỉ vì một câu SQL dùng `:id` và câu khác dùng `?`.

### 7.4. Chạy và quan sát đầu ra

**`src/main/java/example/JdbcClientDemoApplication.java`:**

```java
package example;

import java.math.BigDecimal;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class JdbcClientDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(JdbcClientDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate template, BookCatalogRepository books) {
        return args -> {
            template.execute("""
                CREATE TABLE book_catalog (
                    id BIGINT PRIMARY KEY,
                    code VARCHAR(20) NOT NULL UNIQUE,
                    title VARCHAR(100) NOT NULL,
                    price DECIMAL(12, 2) NOT NULL
                )
                """);

            Book javaBook = new Book(
                1L, "JAVA-1", "Java Core",
                new BigDecimal("90.00")
            );
            Book springBook = new Book(
                2L, "SPR-2", "Spring JDBC",
                new BigDecimal("150.50")
            );

            System.out.println("insert1=" + books.insert(javaBook));
            System.out.println("insert2=" + books.insert(springBook));
            System.out.println("expensive=" +
                books.findAtLeast(new BigDecimal("100.00")));
            System.out.println("found=" + books.findById(1L));
            System.out.println("missing=" + books.findById(99L));
            System.out.println("renamed=" +
                books.rename(1L, "Java Core 17"));
            System.out.println("after=" + books.findById(1L));
        };
    }
}
```

Chạy từ thư mục gốc của dự án:

```bash
./gradlew bootRun
```

Trên Windows dùng `gradlew.bat bootRun`. Trong điều kiện H2 in-memory mới khởi tạo, không có script tạo bảng/dữ liệu khác và Boot đã cấu hình thành công `JdbcClient`, ngoài các log của Spring/Hikari, **chính chương trình in ra**:

```text
insert1=1
insert2=1
expensive=[Book[id=2, code=SPR-2, title=Spring JDBC, price=150.50]]
found=Optional[Book[id=1, code=JAVA-1, title=Java Core, price=90.00]]
missing=Optional.empty
renamed=1
after=Optional[Book[id=1, code=JAVA-1, title=Java Core 17, price=90.00]]
```

Giải thích:
1. `JdbcTemplate` được inject vào `CommandLineRunner` để chạy DDL. `JdbcClient` mà repository nhận cũng được Boot cấu hình dựa trên hạ tầng JDBC của ứng dụng; cả hai truy cập cùng `DataSource` phù hợp.
2. `insert` được gọi hai lần và trả số hàng tác động `1` cho mỗi câu `INSERT` thành công.
3. `findAtLeast(100.00)` lấy đúng cuốn có giá `150.50`; giá `90.00` không vượt ngưỡng.
4. `findById(1)` nhận một record; `findById(99)` không có hàng và trả `Optional.empty()`.
5. `rename` cập nhật tên một hàng qua hai positional parameters; truy vấn `after` phản ánh giá trị mới.
6. SQL `DECIMAL(12,2)` và `BigDecimal` làm phần in giá giữ dạng hai chữ số thập phân trong điều kiện đã mô tả.

Ba file Java trên là **một ứng dụng Spring Boot hoàn chỉnh khi được đặt trong dự án có build script đúng và dependency nêu trên**; không phải các tệp chỉ dùng lệnh `javac` của JDK thuần. Nếu ứng dụng có `JdbcClient` bean tùy chỉnh khác hoặc chọn sai `DataSource`, cần kiểm tra lại bean wiring thay vì mặc định mọi query đi đến H2 ví dụ.

## 8. Tạo trực tiếp từ DataSource và template: ba phiên bản cùng câu truy vấn

Có thể thấy ba overload đều cung cấp facade với cùng cấu trúc lệnh:

### Phương án 1: chỉ DataSource

```java
JdbcClient client = JdbcClient.create(dataSource);

Long total = client.sql("SELECT COUNT(*) FROM book_catalog")
    .query(Long.class)
    .single();
```

`dataSource` là một biến `DataSource` hiện hữu; đoạn code nằm trong method/configuration.

### Phương án 2: JdbcOperations đã cấu hình

```java
JdbcTemplate template = new JdbcTemplate(dataSource);
template.setQueryTimeout(12);

JdbcClient client = JdbcClient.create(template);

Long total = client.sql("SELECT COUNT(*) FROM book_catalog")
    .query(Long.class)
    .single();
```

Tùy chỉnh query timeout là cấu hình của template đang được tái sử dụng. Trong project thật, **nếu đã có bean `JdbcTemplate` cấu hình sẵn, inject nó**, đừng `new` lại chỉ để tạo client.

### Phương án 3: NamedParameterJdbcOperations

```java
NamedParameterJdbcTemplate named =
    new NamedParameterJdbcTemplate(template);

JdbcClient client = JdbcClient.create(named);

Long total = client.sql("SELECT COUNT(*) FROM book_catalog")
    .query(Long.class)
    .single();
```

Trong phương án này biến `template` đã được khởi tạo từ phần trước; đây là đoạn dùng trong cùng context, không phải code tự chứa độc lập. `NamedParameterJdbcTemplate` có delegate classic template, nên các cài đặt liên quan được giữ.

**Đừng khai báo cả ba biến `client` trong một block duy nhất**, vì đây là ba lựa chọn để so sánh. Trong ứng dụng có một nguồn dữ liệu chính, thường chỉ cần **một bean client được chia sẻ**.

## 9. Parameter binding: fluent không có nghĩa là bỏ qua JDBC

Với positional parameters, mỗi dấu `?` nhận một giá trị theo thứ tự:

```java
int changed = client.sql("""
        UPDATE book_catalog
        SET title = ?, price = ?
        WHERE id = ?
        """)
    .param("Spring Advanced")
    .param(new java.math.BigDecimal("199.90"))
    .param(2L)
    .update();
```

Có ba marker tương ứng title, price, id. Nếu đổi chỗ, câu lệnh có thể sai hoặc báo lỗi tùy kiểu dữ liệu; framework không suy ra vị trí dựa vào tên biến Java.

Với named parameters:

```java
int changed = client.sql("""
        UPDATE book_catalog
        SET title = :title, price = :price
        WHERE id = :id
        """)
    .param("id", 2L)
    .param("price", new java.math.BigDecimal("199.90"))
    .param("title", "Spring Advanced")
    .update();
```

Thứ tự các lời gọi `param("name", value)` không cần trùng thứ tự xuất hiện trong SQL vì Spring ghép theo tên; **tên phải khớp** và kiểu vẫn cần phù hợp SQL.

### Map và tham số NULL

Một câu SQL có cột nullable:

```java
var parameters =
    new org.springframework.jdbc.core.namedparam.MapSqlParameterSource()
        .addValue("note", null, java.sql.Types.VARCHAR)
        .addValue("id", 7L, java.sql.Types.BIGINT);

int changed = client.sql(
        "UPDATE book_catalog SET note = :note WHERE id = :id")
    .paramSource(parameters)
    .update();
```

**Đây là mảnh minh họa với schema đã có thêm cột `note VARCHAR`;** bảng demo ở mục 7 **không có cột note**, nên không chạy câu lệnh này nguyên xi trên bảng demo chưa sửa schema. `MapSqlParameterSource` truyền được null kèm SQL type rõ ràng; `Map.of("note", null)` không hợp lệ vì `Map.of` cấm null.

Ngoài tên/kiểu, hãy tách các giá trị đầu vào khỏi văn bản SQL: `JdbcClient` vẫn dựa trên `PreparedStatement` bên dưới và giúp tránh SQL injection ở **vị trí giá trị**. Các thành phần như tên bảng/cột/sort mode **không được dùng placeholder để thay tên identifier**; cần whitelist khi chúng là lựa chọn động.

### IN với nhiều giá trị

```java
var ids = java.util.List.of(1L, 2L, 3L);

var books = client.sql("""
        SELECT id, code, title, price
        FROM book_catalog
        WHERE id IN (:ids)
        ORDER BY id
        """)
    .param("ids", ids)
    .query(BOOK_MAPPER)
    .list();
```

Đây là đoạn trong class có `JdbcClient client` và `RowMapper<Book> BOOK_MAPPER`; nó yêu cầu bảng ví dụ. Với named parameters, Spring có thể mở rộng collection thành nhiều positional markers phù hợp. Danh sách rỗng cần chính sách rõ ràng (`IN ()` không portable); nếu không có ID nào cần tra cứu, thường trả `List.of()` mà không gửi SQL. Không dùng một `IN (?)` rồi kỳ vọng mọi driver tự hiểu một `List` Java là danh sách nhiều giá trị SQL.

## 10. Query result: single, optional, list và mapping

`JdbcClient` tách **cách thực thi SQL** khỏi **cách diễn giải kích thước kết quả**:

| API fluent | Kỳ vọng | Hành vi cần hiểu |
| --- | --- | --- |
| `query(MyType.class).single()` | Đúng một giá trị/hàng | Không có hàng gây lỗi kết quả rỗng; nhiều hàng gây lỗi kích thước |
| `query(rowMapper).single()` | Đúng một object/hàng | Thích hợp khi truy vấn theo khóa duy nhất và bắt buộc tồn tại |
| `query(rowMapper).optional()` | 0 hoặc 1 hàng | `Optional.empty()` khi không có hàng; nhiều hàng là vi phạm |
| `query(rowMapper).list()` | 0..N hàng | Danh sách rỗng khi 0 hàng |
| `sql(...).update()` | Lệnh ghi/DDL phù hợp | Trả số hàng tác động (`int`), tùy câu SQL và driver |

Nếu API repository là `findById` (có thể không tồn tại), `optional()` thường hợp lý; nếu là `getRequiredById`, `single()` cho contract rõ ràng.

Ví dụ sử dụng mapper:

```java
Book required = client.sql("""
        SELECT id, code, title, price
        FROM book_catalog WHERE id = :id
        """)
    .param("id", 7L)
    .query(BOOK_MAPPER)
    .single();
```

Mảnh này yêu cầu `BOOK_MAPPER` được định nghĩa như ở repository demo. Nếu `id=7` không tồn tại, Spring sẽ báo lỗi cho hợp đồng "đúng một hàng"; **không mặc định tự trả `null` chỉ vì không có hàng**. Với `query(Book.class)` Spring còn hỗ trợ mapping dựa trên property/record trong những điều kiện phù hợp, nhưng custom `RowMapper` thường minh bạch hơn khi tên cột và field khác nhau hoặc conversion có quy tắc nghiệp vụ.

### Resource management

`JdbcClient` không có `close()` cần gọi sau mỗi `sql(...)`. Các operation dưới facade sử dụng JDBC templates để mượn/trả connection, chuẩn bị statement, xử lý `ResultSet` và dịch lỗi. Không giữ `ResultSet` hay `Connection` ra khỏi callback mapper. Nếu dùng API trả `Stream` hoặc resource có vòng đời đặc biệt từ một tầng thấp hơn, cần tuân thủ hợp đồng đóng của API đó, không suy ra mọi luồng kết quả tự giải phóng ngay khi được tạo.

## 11. Transaction: chọn đúng DataSource hoặc template mới thực sự quan trọng

`JdbcClient` **không tự tạo một transaction bao trùm nhiều câu SQL** chỉ vì hai operation cùng chạy trên một object client. Transaction JDBC được quản lý thông qua `Connection` và transaction manager Spring gắn với **`DataSource`** tương ứng.

Ví dụ service gọi repository:

```java
package example;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public final class CatalogService {
    private final BookCatalogRepository books;

    public CatalogService(BookCatalogRepository books) {
        this.books = books;
    }

    @Transactional
    public void addTwo(Book first, Book second) {
        books.insert(first);
        books.insert(second);
    }
}
```

Đây là một component dùng trong Spring context đã có transaction manager tương thích. Khi `addTwo` được gọi **qua Spring transaction proxy**, và hai thao tác repository sử dụng client/template gắn với **cùng `DataSource`** mà transaction manager quản lý, chúng có thể tham gia một JDBC transaction chung. Nếu insert thứ hai gây `DuplicateKeyException` (runtime exception), chính sách rollback mặc định thường rollback cả insert thứ nhất.

- **Tạo `JdbcClient` từ đúng `DataSource`/template** là điều kiện quan trọng để transaction hoạt động như kỳ vọng.
- `JdbcClient.create(dataSource)` không tự mở transaction ở thời điểm tạo client.
- `JdbcClient.create(template)` tái sử dụng cấu hình template; transaction integration vẫn phụ thuộc vào data source/transaction manager.
- Nếu một service dùng hai `DataSource` trỏ tới hai DB khác nhau, một `@Transactional` JDBC thông thường **không tự thành transaction phân tán nguyên tử**.
- Spring AOP proxy thông thường không intercept lời gọi nội bộ `this.addTwo(...)` trong cùng bean; khi đó annotation có thể không được áp dụng.
- Không tự gọi `commit`/`rollback` trên connection mà Spring transaction manager đang sở hữu.

Điểm phân biệt lớn nhất của ba cách tạo client **không phải** "factory nào có hỗ trợ transaction"; tất cả đều dùng cơ chế JDBC/Spring phù hợp với delegate và nguồn dữ liệu được chọn.

## 12. Nhiều DataSource: tạo client theo đúng nguồn

Giả sử ứng dụng có `primaryDataSource` và `reportingDataSource`. Nếu chỉ inject `DataSource` theo kiểu mà không có định danh/ưu tiên, Spring có thể không chọn được bean; hoặc một client truy vấn nhầm database.

Một mẫu cấu hình khi **đã có sẵn bean tên `reportingDataSource`**:

```java
package example;

import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.simple.JdbcClient;

@Configuration
public class ReportingJdbcConfig {
    @Bean("reportingJdbcClient")
    JdbcClient reportingJdbcClient(
            @Qualifier("reportingDataSource") DataSource source) {
        return JdbcClient.create(source);
    }
}
```

Đây là **cấu hình một client cho nguồn báo cáo**, không định nghĩa data source gốc. Cần cung cấp bean `reportingDataSource` qua cấu hình khác. Ở repository, inject rõ bean:

```java
public ReportingRepository(
        @Qualifier("reportingJdbcClient") JdbcClient jdbc) {
    this.jdbc = jdbc;
}
```

Đoạn constructor này cần import `@Qualifier` và thuộc class có field `JdbcClient jdbc`. Nếu ứng dụng cũng có bean `JdbcClient` chính, hai bean cần tên/`@Primary`/`@Qualifier` rõ ràng; đừng tạo bean không định danh rồi chờ Spring đoán đúng DB.

### Nên tạo từ DataSource hay template cho nguồn thứ hai?

Nếu reporting DB đã có `JdbcTemplate` riêng với `queryTimeout` và `fetchSize` phục vụ query dài, nên tạo `JdbcClient.create(reportingJdbcTemplate)` để **tái sử dụng cấu hình đó**. Nếu chưa có template phù hợp và chỉ cần defaults, tạo từ `reportingDataSource` là hợp lý.

Với transaction của một nguồn khác, định danh transaction manager cũng cần khớp, ví dụ chọn đúng bean transaction manager trong `@Transactional("reportingTxManager")` nếu thật sự có bean đó và giao dịch ghi được phép. Không coi việc thêm `@Qualifier` cho client là đủ để biến hai data source thành một transaction.

## 13. Kiểm thử wiring: client nào đang dùng nguồn nào?

Có hai câu hỏi nên được kiểm tra riêng:

1. **Khởi tạo đúng?** Context có bean `JdbcClient` từ DataSource/template mong muốn, không gặp `NoSuchBeanDefinitionException` hoặc `NoUniqueBeanDefinitionException`.
2. **Thực thi đúng?** Câu SQL chạy trên database mong muốn, tham số được bind đúng, kết quả mapping đúng, transaction và tài nguyên được quản lý phù hợp.

Với project Spring Boot demo mục 7, có thể dùng JDBC slice test. Trong `build.gradle` bổ sung:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

**`src/test/java/example/BookCatalogRepositoryTest.java`:**

```java
package example;

import java.math.BigDecimal;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.*;

@JdbcTest
@Import(BookCatalogRepository.class)
class BookCatalogRepositoryTest {
    @Autowired
    JdbcTemplate template;

    @Autowired
    BookCatalogRepository books;

    @BeforeEach
    void setUp() {
        template.execute("""
            CREATE TABLE IF NOT EXISTS book_catalog (
                id BIGINT PRIMARY KEY,
                code VARCHAR(20) NOT NULL UNIQUE,
                title VARCHAR(100) NOT NULL,
                price DECIMAL(12, 2) NOT NULL
            )
            """);
        template.update("DELETE FROM book_catalog");
    }

    @Test
    void clientCreatedByBootSupportsNamedAndPositional() {
        Book item = new Book(
            7L, "BOOK-7", "Effective Java",
            new BigDecimal("120.00")
        );
        assertEquals(1, books.insert(item));
        assertEquals(item, books.findById(7L).orElseThrow());

        var expensive = books.findAtLeast(new BigDecimal("100.00"));
        assertEquals(1, expensive.size());
        assertEquals(7L, expensive.get(0).id());
        assertEquals(1, books.rename(7L, "Effective Java 3"));
        assertEquals(
            "Effective Java 3",
            books.findById(7L).orElseThrow().title()
        );
    }

    @Test
    void optionalIsEmptyWhenRowDoesNotExist() {
        assertTrue(books.findById(999L).isEmpty());
        assertEquals(0, books.rename(999L, "Absent"));
    }
}
```

Chạy:

```bash
./gradlew test
```

Với Spring Boot **3.3.x**, `@JdbcTest` auto-configure các thành phần JDBC cần thiết, trong đó có `JdbcClient` khi điều kiện phù hợp, và `@Import` cung cấp bean repository cho slice test. Dự kiến **2 bài test pass** khi H2 và schema phù hợp. `@JdbcTest` mặc định dùng embedded DB và transaction rollback cho mỗi test; ứng dụng không cần chạy toàn bộ `CommandLineRunner`.

**Vì sao test này hữu ích?** Nó chứng minh bean `JdbcClient` được inject thật, cả hai phong cách parameter cùng chạy, mapper trả record chính xác và truy vấn không có hàng trả `Optional.empty()`. Một unit test chỉ mock client không kiểm tra được SQL/driver hay cấu hình `DataSource` thực tế.

Trong ứng dụng có PostgreSQL/MySQL ở production, bổ sung integration test với đúng DB/driver (ví dụ Testcontainers); H2 không thay thế việc xác nhận dialect, schema, conversion và transaction trong môi trường thực.

### Test riêng khi có template tùy chỉnh

Nếu mục đích của bạn là "tạo client từ template đã cấu hình", nên có test cấu hình:

- Tạo hoặc inject `JdbcTemplate` mong muốn, cấu hình một giá trị có thể quan sát (`queryTimeout` chẳng hạn).
- Tạo client bằng `JdbcClient.create(existingTemplate)`, không tạo `new JdbcTemplate` khác.
- Kiểm tra data source tương ứng và behavior khi thực thi trong môi trường integration test.
- Khi nhiều DB, chèn dữ liệu phân biệt vào từng nguồn rồi xác minh client chỉ thấy dữ liệu của DB đúng.

Không chỉ test `client != null`: một client có thể tồn tại mà vẫn dùng sai data source hoặc sai template.

## 14. Các lỗi thiết kế thường gặp

| Sai lầm | Hậu quả / hướng sửa |
| --- | --- |
| Dùng Spring 6.0/Boot 3.1 nhưng import `JdbcClient` | API chưa được hỗ trợ; nâng lên Spring 6.1+/Boot 3.2+ hoặc dùng template cũ |
| Coi `JdbcClient` là một `Connection` | Sai tầng abstraction; `JdbcClient` là facade, còn connection lấy qua data source khi thực thi |
| Gọi `JdbcClient.create(dataSource)` liên tục trong mỗi request dù Boot đã có bean client | Tăng cấu hình trùng lặp, dễ bỏ qua template chung; inject bean dùng lại |
| Đã có `JdbcTemplate` cấu hình riêng nhưng tạo client từ data source | Có thể mất cấu hình template đã có; dùng `create(existingTemplate)` |
| Đã có `NamedParameterJdbcTemplate` nhưng tạo một template hoàn toàn mới | Bỏ qua delegate/cấu hình hiện hữu; tạo client từ named template đã inject |
| Tạo nhiều `@Bean JdbcClient` không có định danh rõ | Khó inject, lỗi nhiều bean hoặc truy vấn nhầm DB; dùng `@Qualifier`/`@Primary` |
| Tin rằng gọi `create(...)` là đã kiểm tra DB sống | Client có thể được tạo mà chưa chạy query; test connectivity/SQL thực tế |
| Trộn `:name` và `?` thiếu nhất quán trong một câu SQL | Dễ bind sai; chọn một kiểu placeholder nhất quán cho statement |
| Tham số cùng tên nhưng kiểu không phù hợp SQL | Lỗi conversion hoặc sai dữ liệu; xét SQL type, precision, nullability |
| Coi `optional()` là "lấy bản ghi đầu tiên" | Nó biểu diễn 0 hoặc 1, nhiều hàng là lỗi; dùng list hoặc query phù hợp |
| Coi client fluent là ORM hoặc JPA `EntityManager` | Không có persistence context/dirty checking của JPA; vẫn phải viết SQL |
| Coi các operation qua cùng client tự tạo transaction chung | Dùng transaction manager/`@Transactional` đúng DataSource |
| Dùng `JdbcClient` để ép mọi stored procedure/batch workflow | Với thao tác nâng cao, xem `JdbcTemplate`, `SimpleJdbcInsert`, `SimpleJdbcCall` |
| Giữ statement spec của một query rồi dùng chung giữa các thread | Chỉ nên chia sẻ client đã cấu hình; tạo chuỗi `sql(...).param(...)` riêng cho từng operation |
| Dùng `JdbcClient.create(new JdbcTemplate(dataSource))` thay vì bean template đã có | Có thể bypass cấu hình hạ tầng/observability; inject bean hiện tại |

### Không kỳ vọng JdbcClient thay thế mọi API SQL cao cấp

`JdbcClient` là facade **đơn giản hóa các truy vấn và cập nhật phổ biến**. Các công việc như batch update phức tạp, custom callback nâng cao, lấy generated keys theo nhiều chiến lược, stored procedure có metadata và nhiều result sets có thể cần API thấp hơn hoặc chuyên biệt:

- `JdbcTemplate` / `JdbcOperations`;
- `NamedParameterJdbcTemplate` / `NamedParameterJdbcOperations`;
- `SimpleJdbcInsert` và `SimpleJdbcCall`.

Không có lý do phải bỏ những template này khi thêm `JdbcClient`: client được xây trên chính chúng và có thể cùng tồn tại trong kiến trúc.

## 15. Checklist chọn cách tạo client

**Khi bắt đầu một repository Spring JDBC mới:**

1. Kiểm tra phiên bản: cần **Spring Framework 6.1+**; nếu dùng Boot thường cần **3.2+** để có auto-config `JdbcClient`.
2. Kiểm tra context có **bean `JdbcClient` đã cấu hình** không. Nếu có và đúng data source/template, **inject trực tiếp**.
3. Nếu chưa có client và chỉ có `DataSource`, dùng `JdbcClient.create(dataSource)` hoặc tạo một `@Bean` dùng chung.
4. Nếu đã có `JdbcTemplate`/`JdbcOperations` tùy chỉnh, dùng `JdbcClient.create(jdbcOperations)` để giữ cấu hình đó.
5. Nếu đã có `NamedParameterJdbcTemplate`/`NamedParameterJdbcOperations` tùy chỉnh, dùng `JdbcClient.create(namedOperations)`.
6. Nếu có nhiều data source, xác định bean bằng `@Qualifier` và gắn transaction manager phù hợp.
7. Sử dụng positional `?` hoặc named `:name` thống nhất trong từng câu; không ghép giá trị người dùng vào SQL raw.
8. Chọn `single()`, `optional()` hoặc `list()` theo **hợp đồng kích thước kết quả**.
9. Viết integration test để xác nhận schema, mapping, thứ tự kết quả, timeout/transaction và DB được chọn.
10. Khi có API nâng cao không phù hợp facade, tái dùng template đang có thay vì cố viết vòng tránh quanh `JdbcClient`.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Có bean `DataSource` nhưng chưa có JDBC template cần tùy chỉnh. Dùng cách tạo nào?

**Đáp án:** `JdbcClient.create(dataSource)` là lựa chọn trực tiếp; nếu dùng Spring Boot 3.2+ đã auto-config client từ hạ tầng phù hợp thì thường chỉ cần inject bean `JdbcClient`.

**Câu 2.** Có `JdbcTemplate` đã set query timeout, fetch size và exception translator. Nên tạo client từ đâu?

**Đáp án:** Từ chính `JdbcTemplate` đó qua `JdbcClient.create(jdbcTemplate)` (overload `JdbcOperations`), để giữ cấu hình và data source hiện hữu.

**Câu 3.** Có `NamedParameterJdbcTemplate` do ứng dụng tạo. `JdbcClient` có nhận làm delegate được không?

**Đáp án:** Có, qua `JdbcClient.create(namedParameterJdbcTemplate)` (overload `NamedParameterJdbcOperations`). Client dùng lại named template và classic template phía dưới.

**Câu 4.** Client được tạo từ `DataSource` có chạy query dùng `:id` được không?

**Đáp án:** Có. `JdbcClient` hỗ trợ cả named và positional parameters cho các statement phổ biến; không cần tạo từ named template chỉ để dùng `:id`.

**Câu 5.** Vì sao việc tạo client từ đúng `DataSource` quan trọng với `@Transactional`?

**Đáp án:** Transaction manager JDBC phối hợp connection trên data source tương ứng. Nếu client dùng data source khác, SQL của nó không tự tham gia cùng giao dịch chỉ vì service có annotation.

**Câu 6.** Gọi `JdbcClient.create(dataSource)` có tạo connection vật lý mới ngay cho mỗi instance không?

**Đáp án:** Không thể suy ra như vậy. Factory tạo facade/delegate JDBC; kết nối thực tế phụ thuộc data source/pool và thời điểm thực thi operation.

**Câu 7.** `JdbcClient` có tự sửa một câu SQL thiếu `ORDER BY` để kết quả ổn định không?

**Đáp án:** Không. Thứ tự truy vấn chỉ được bảo đảm khi SQL yêu cầu tương ứng; facade không thay ngữ nghĩa SQL.

**Câu 8.** Dùng `JdbcClient` có khiến `JdbcTemplate` lỗi thời hoặc phải xóa khỏi ứng dụng không?

**Đáp án:** Không. JdbcClient ủy quyền cho các template; những API phức tạp hoặc cần cấu hình sâu vẫn dùng template trực tiếp.

**Câu 9.** Có hai bean `JdbcClient`, một cho báo cáo và một cho giao dịch. Làm sao chọn?

**Đáp án:** Dùng `@Qualifier` hoặc `@Primary` rõ ràng trong cấu hình/injection; đảm bảo template, data source và transaction manager phù hợp.

## 17. Tài liệu tham khảo chính thức

- [Spring Framework — `JdbcClient` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.html): ba static factory `create`, overload nhận `DataSource`, `JdbcOperations` và `NamedParameterJdbcOperations`, hợp đồng của fluent client.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): giới thiệu `JdbcClient` từ 6.1, positional/named parameters, `RowMapper` và hoạt động query/update.
- [Spring Boot 3.3 — SQL Databases](https://docs.spring.io/spring-boot/3.3/reference/data/sql.html): auto-configuration `DataSource`, `JdbcTemplate`, `NamedParameterJdbcTemplate`, `JdbcClient`.
- [Spring Boot — `JdbcClientAutoConfiguration`](https://docs.spring.io/spring-boot/docs/3.2.1/api/org/springframework/boot/autoconfigure/jdbc/JdbcClientAutoConfiguration.html): điều kiện tạo bean `JdbcClient`, dựa trên named template khả dụng và thiếu bean client riêng.
- [Spring Framework — `JdbcTemplate` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html): cấu hình template và các thao tác cấp thấp dùng lại ở dưới client.
- [Spring Framework — Parameter Handling](https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html): SQL types và tham số null trong Spring JDBC.
- [Spring Boot 3.3 — JDBC Tests](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@JdbcTest` và các nguyên tắc JDBC slice testing.

**Ghi nhớ:** `JdbcClient` là **facade tạo từ `DataSource` hoặc các template JDBC đã cấu hình**, chứ không phải một kết nối riêng. **Có `DataSource` thì dùng `create(dataSource)`; có template tùy chỉnh thì dùng `create(template)` để tái sử dụng cấu hình; có bean `JdbcClient` do Spring Boot cung cấp thì thường chỉ cần inject nó.** Việc chọn đúng nguồn kết nối giúp query, exception translation, timeout và transaction nhất quán trong toàn bộ tầng truy cập dữ liệu.
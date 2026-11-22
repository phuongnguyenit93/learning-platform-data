# JdbcTemplate an toàn khi dùng chung sau cấu hình nhưng callback vẫn cần thiết kế đúng

## 1. Hai khái niệm an toàn khác nhau

Trong Spring JDBC, một `JdbcTemplate` có thể được tạo một lần, cấu hình đầy đủ, rồi inject vào nhiều repository/service và được nhiều request sử dụng đồng thời. Tài liệu API của Spring diễn đạt rõ: **một instance `JdbcTemplate` là thread-safe sau khi đã cấu hình xong** (*thread-safe once configured*).

Tuy nhiên, câu đó **không khẳng định** mọi đối tượng mà template sử dụng đều thread-safe. Đặc biệt, các callback mà bạn truyền vào `query`, `update` hoặc `execute` vẫn là **mã ứng dụng**. Nếu callback ghi vào cùng một `ArrayList`, `StringBuilder`, bộ đếm hoặc đối tượng trạng thái dùng chung giữa các request, vẫn có race condition, sai dữ liệu hoặc lộ kết quả từ request này sang request khác.

Cần tách ba câu hỏi:

1. **Template có dùng chung được không?** Có, sau khi cấu hình ổn định và công bố an toàn. Một bean singleton `JdbcTemplate` là mô hình phổ biến.
2. **Tài nguyên JDBC được dùng chung theo nghĩa nào?** `DataSource` là nguồn cung cấp connection; mỗi operation lấy tài nguyên theo cơ chế Spring, đóng/giải phóng đúng lúc. Không nên chia sẻ một `ResultSet` hay `PreparedStatement` tùy tiện giữa thread.
3. **Callback có an toàn không?** Tùy vào *state* nó đọc/ghi, đối tượng nó capture, vòng đời của state và việc có cho state/`ResultSet` thoát ra ngoài operation hay không.

Bài này tập trung vào sự khác biệt thứ ba, nhưng phải hiểu cả ba để tránh kết luận “có `JdbcTemplate` thì tự động hết lỗi concurrency”.

### 1.1. Thực tế JdbcTemplate giữ những gì?

`JdbcTemplate` giữ tham chiếu đến `DataSource` và một số cấu hình như cách dịch `SQLException`, `fetchSize`, `maxRows`, `queryTimeout`. Nó là thành phần điều phối các thao tác JDBC và gọi callback, **không phải** một `ResultSet` hay một `Connection` cố định để tất cả request cùng sửa.

Một cách sử dụng điển hình:

```java
@Configuration(proxyBeanMethods = false)
class JdbcConfiguration {
    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        JdbcTemplate template = new JdbcTemplate(dataSource);
        template.setQueryTimeout(10); // Cấu hình một lần khi tạo bean.
        return template;
    }
}
```

Đây là **đoạn minh họa**, cần import `@Configuration`, `@Bean`, `DataSource`, `JdbcTemplate` và một bean `DataSource` hiện hữu; chưa phải chương trình độc lập. Spring tạo bean rồi inject cùng instance vào nhiều DAO. Các setter cấu hình được gọi trước khi instance bắt đầu được dùng đồng thời.

**Không nên** gọi `template.setQueryTimeout(...)`, `setFetchSize(...)`, `setMaxRows(...)` hoặc `setDataSource(...)` theo từng request trên một singleton đang hoạt động. Đây là thay đổi cấu hình chia sẻ; request khác có thể quan sát giá trị mới ngoài ý muốn. Nếu cần cấu hình khác biệt, chọn API/statement tùy trường hợp hoặc tạo template đã cấu hình riêng; không biến setter toàn cục thành “request setting”.

### 1.2. Luồng chạy của một thao tác

```text
Request A                           Request B
   |                                   |
   v                                   v
BookRepository                     BookRepository
   |                                   |
   +-------------+---------------------+
                 |
          Cùng JdbcTemplate
           (cấu hình ổn định)
                 |
        +--------+--------+
        |                 |
   Query A            Query B
   tham số A          tham số B
   callback A         callback B
   ResultSet A        ResultSet B
        |                 |
        +--------+--------+
                 |
        DataSource / pool
                 |
        JDBC driver / database
```

Hai nhánh dùng chung **đối tượng template**; dữ liệu truy vấn và tài nguyên xử lý của từng operation vẫn phải được cô lập phù hợp. Với connection pool chuẩn, mỗi thao tác thường mượn và trả connection; khi có Spring-managed transaction, `JdbcTemplate` tham gia connection được gắn với transaction trên thread hiện tại. Không suy luận rằng mỗi operation *luôn* có physical connection mới: pool có thể tái sử dụng connection, và các lệnh trong cùng transaction có thể dùng cùng connection.

## 2. Vòng đời callback và ai sở hữu tài nguyên?

Một callback của Spring JDBC thường chạy **đồng bộ trong lời gọi JDBC**. Template điều phối tạo/chuẩn bị statement, thực thi, duyệt dữ liệu khi thích hợp và dọn dẹp tài nguyên nó quản lý. Callback chỉ làm nhiệm vụ được hợp đồng callback cho phép.

| Callback | Nhận gì? | Trách nhiệm chính | Lưu ý về trạng thái |
| --- | --- | --- | --- |
| `PreparedStatementCreator` | `Connection` | Tạo và trả `PreparedStatement` đúng SQL/tuỳ chọn cần dùng | Không giữ connection làm field để dùng về sau |
| `PreparedStatementSetter` | `PreparedStatement` | Bind tham số bằng `setXxx(...)` | Không tự execute/close statement; tránh capture dữ liệu mutable bị sửa đồng thời |
| `RowMapper<T>` | `ResultSet` ở **hàng hiện tại** và `rowNum` | Tạo một `T` từ **một hàng** | Tốt nhất stateless; **không gọi `rs.next()`** |
| `RowCallbackHandler` | `ResultSet` ở **hàng hiện tại** | Xử lý từng hàng, thường cập nhật một bộ tích lũy | Bộ tích lũy dùng chung cần cô lập theo **mỗi lời gọi**; **không gọi `rs.next()`** |
| `ResultSetExtractor<T>` | `ResultSet` để xử lý **toàn bộ tập kết quả** | Chủ động duyệt `while (rs.next())` rồi trả `T` | Trạng thái tổng hợp nên là biến local hoặc callback mới từng lần |
| `PreparedStatementCallback<T>` | `PreparedStatement` đã tạo | Thực thi thao tác statement tùy biến và lấy kết quả | Quản lý đúng tài nguyên tự mở trong callback; không đóng statement mà template sở hữu |

Trong `RowMapper` và `RowCallbackHandler`, **`JdbcTemplate` đã điều khiển vị trí con trỏ** trước khi gọi callback. Gọi thêm `rs.next()` ở đây sẽ làm mất hàng hoặc khiến hành vi khó đoán. Ngược lại, `ResultSetExtractor` chịu trách nhiệm duyệt tập kết quả; nếu không gọi `rs.next()` khi cần thì không có hàng nào được đọc.

`rowNum` của `RowMapper` bắt đầu từ 0 cho mỗi lần duyệt kết quả. Không sử dụng `rowNum` làm ID nghiệp vụ hay thứ tự bền vững của database. Thứ tự kết quả phụ thuộc `ORDER BY` trong SQL.

**Quy tắc tài nguyên:** không return hoặc lưu `ResultSet`, `PreparedStatement` hay `Connection` nhận được từ callback để sử dụng sau khi `JdbcTemplate` kết thúc. Template sẽ đóng/giải phóng các tài nguyên nó quản lý; tham chiếu thoát ra ngoài có thể đã không còn hợp lệ. Nếu callback tự tạo stream/file/network resource riêng, tự quản lý vòng đời các tài nguyên đó; template không biết mọi thứ bạn mở thêm.

## 3. RowMapper: chọn stateless để an toàn và tái sử dụng

`RowMapper<T>` nhận một hàng rồi trả một đối tượng Java. Một mapper tốt thường là hàm thuần với dữ liệu đọc từ hàng hiện tại, có thể dùng lại qua nhiều truy vấn và thread:

```java
// Đoạn minh họa, record và import cần có ở ứng dụng:
record Book(long id, String title) {}

RowMapper<Book> mapper = (rs, rowNum) ->
        new Book(rs.getLong("id"), rs.getString("title"));

List<Book> books = jdbc.query(
        "SELECT id, title FROM books ORDER BY id", mapper);
```

Trong ví dụ, `mapper` không giữ bộ đếm, danh sách đang tích lũy hay con trỏ ngoài. Hai lời gọi song song cùng dùng một mapper không chia sẻ kết quả tạm nào do mapper tạo ra. `JdbcTemplate` tạo một danh sách kết quả riêng cho từng lời gọi `query`.

Nếu cần dùng mapper thường xuyên, khai báo:

```java
private static final RowMapper<Book> BOOK_MAPPER =
        (rs, rowNum) -> new Book(
                rs.getLong("id"),
                rs.getString("title"));
```

Đây là một **đoạn khai báo field**, không phải class Java độc lập. Field `final` giúp giữ cố định tham chiếu tới mapper, nhưng **`final` không tự làm đối tượng được trỏ tới thành thread-safe**. Chính logic mapper không mutate state chia sẻ mới là lý do sử dụng lại an toàn.

### 3.1. Thiết kế sai: mapper tích lũy mutable state chia sẻ

```java
// Minh họa phản diện; KHÔNG dùng trong code nhiều request.
final class UnsafeBookMapper implements RowMapper<Book> {
    private int mappedRows = 0;
    private final List<String> recentTitles = new ArrayList<>();

    @Override
    public Book mapRow(ResultSet rs, int rowNum) throws SQLException {
        mappedRows++;
        recentTitles.add(rs.getString("title"));
        return new Book(rs.getLong("id"), rs.getString("title"));
    }
}
```

Nếu singleton repository dùng chung `UnsafeBookMapper`, các request có thể đồng thời `mappedRows++` (không atomic) hoặc `add` vào cùng một `ArrayList` (không thread-safe). Kết quả bị lẫn giữa các truy vấn, số lượng sai hoặc thậm chí lỗi cấu trúc collection. Dù có thêm `synchronized`, việc dùng chung `recentTitles` vẫn khiến ngữ nghĩa “kết quả của request nào?” không rõ.

Không cần lưu danh sách/đếm trong mapper nếu `JdbcTemplate.query(...)` đã trả `List<Book>`. Nếu muốn metrics dùng chung, thiết kế thành trách nhiệm riêng, có mô hình synchronization thích hợp và không coi đó là dữ liệu kết quả nghiệp vụ.

### 3.2. Đọc giá trị null và xử lý lỗi

Callback đúng còn phải ánh xạ đúng kiểu dữ liệu:

```java
// Đoạn RowMapper minh họa cho cột parent_id có thể NULL:
Long parentId = rs.getObject("parent_id", Long.class);
// Khác với rs.getLong(...): với SQL NULL, getLong trả 0 và phải dùng rs.wasNull().
```

`SQLException` phát sinh trong `mapRow` có thể được Spring JDBC bắt và dịch qua `SQLExceptionTranslator` thành phân cấp `DataAccessException` unchecked. Không nên nuốt `SQLException` rồi tự thay bằng một DTO “rỗng” như dữ liệu hợp lệ. Lỗi nghiệp vụ và lỗi hạ tầng cần được phân biệt.

## 4. RowCallbackHandler: callback thường stateful nhưng state phải thuộc từng invocation

`RowCallbackHandler` thích hợp khi muốn xử lý từng hàng mà không nhất thiết tạo `List<T>` qua `RowMapper`, chẳng hạn ghi thống kê, tính tổng, chuyển từng hàng sang một sink được kiểm soát. Handler thường có state để tích lũy, nhưng mỗi lời gọi nên sở hữu **một state độc lập**.

### 4.1. Cách đúng: bộ tích lũy local

```java
List<String> names = new ArrayList<>();
RowCallbackHandler handler = rs -> names.add(rs.getString("title"));
jdbc.query("SELECT title FROM books ORDER BY id", handler);

// names là kết quả riêng của lời gọi này, chỉ đọc sau khi query trả về.
```

Đây là **đoạn trích**, giả định `jdbc` và bảng `books` đã có, import `List`, `ArrayList`, `RowCallbackHandler`. Lambda capture danh sách mutable, nhưng ở cách dùng này danh sách **được tạo mới bên trong invocation** và callback chạy đồng bộ, không có thread khác cùng sửa nó; vì thế phù hợp.

Điểm quan trọng không phải “lambda luôn an toàn” hoặc “callback phải hoàn toàn immutable”. **Bộ tích lũy mutable vẫn hợp lệ nếu nó thuộc đúng một thao tác và không bị chia sẻ đồng thời.**

### 4.2. Cách sai: giữ RowCallbackHandler thành singleton với kết quả dùng chung

```java
// Đoạn minh họa lỗi trong singleton DAO, không phải ví dụ thực thi độc lập.
class UnsafeTitlesDao {
    private final JdbcTemplate jdbc;
    private final List<String> allTitles = new ArrayList<>();

    UnsafeTitlesDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    List<String> loadTitles() {
        allTitles.clear();
        jdbc.query("SELECT title FROM books", (RowCallbackHandler) rs ->
                allTitles.add(rs.getString("title")));
        return allTitles;
    }
}
```

Giả sử request A vừa thêm “Java” thì request B gọi `clear()`; A có thể mất dữ liệu. B lại thêm “Spring” vào cùng list; kết quả hai lời gọi bị trộn. Việc bean DAO và `JdbcTemplate` đều là singleton không bảo đảm tính đúng đắn của field `allTitles`.

**Sửa tốt hơn:** tạo `List<String> titles = new ArrayList<>()` bên trong `loadTitles()`, truyền handler dùng danh sách local và trả danh sách đó sau khi `query` kết thúc. Với nhu cầu chỉ chuyển một hàng thành một phần tử của danh sách, có thể viết thẳng:

```java
List<String> titles = jdbc.query(
        "SELECT title FROM books ORDER BY id",
        (rs, rowNum) -> rs.getString("title"));
```

Vì sao thường nên chọn `RowMapper` ở đây? Nó diễn tả rõ “mỗi hàng → một String”, và `JdbcTemplate` tự quản lý bộ sưu tập kết quả cho từng invocation; code ít phải duy trì state hơn.

### 4.3. Đừng điều khiển con trỏ trong RowCallbackHandler

```java
// Sai khi dùng RowCallbackHandler:
RowCallbackHandler wrong = rs -> {
    while (rs.next()) {          // Làm rối vòng lặp do JdbcTemplate quản lý.
        System.out.println(rs.getString("title"));
    }
};

// Đúng: chỉ đọc hàng hiện tại.
RowCallbackHandler right = rs ->
        System.out.println(rs.getString("title"));
```

Đây là các đoạn minh họa; `JdbcTemplate` tự duyệt `ResultSet` khi truyền `RowCallbackHandler`, nên `right` được gọi lần lượt cho các hàng.

## 5. ResultSetExtractor: duyệt toàn bộ result set một cách chủ động

`ResultSetExtractor<T>` phù hợp khi kết quả không phải đơn giản “mỗi hàng tạo một T” — ví dụ trả về tổng hợp, dựng cây từ dữ liệu JOIN, phân nhóm cha-con hoặc tính thống kê.

```java
ResultSetExtractor<Map<Long, List<String>>> extractor = rs -> {
    Map<Long, List<String>> childrenByParent = new LinkedHashMap<>();

    while (rs.next()) {
        long parentId = rs.getLong("parent_id");
        String child = rs.getString("child_name");
        childrenByParent
                .computeIfAbsent(parentId, id -> new ArrayList<>())
                .add(child);
    }
    return childrenByParent;
};

Map<Long, List<String>> groups = jdbc.query(
        "SELECT parent_id, child_name FROM child ORDER BY parent_id, child_name",
        extractor);
```

Đây là **đoạn trích** cần các import Java collections, interface extractor, bảng `child` và `jdbc`. Bản thân `extractor` không giữ dữ liệu qua nhiều query: `childrenByParent` được tạo **mỗi lần phương thức lambda được gọi**.

Ngược lại, nếu viết `Map` thành field của một singleton `ResultSetExtractor` rồi tái sử dụng cho nhiều query, vẫn có race và nhiễm state. Một extractor có thể được tái sử dụng an toàn nếu **nó stateless và mọi accumulator được tạo trong `extractData`**.

### 5.1. Không return ResultSet để dùng sau

```java
// Sai: kết quả trả về phụ thuộc tài nguyên sắp bị đóng.
ResultSet leaked = jdbc.query(
        "SELECT id, title FROM books",
        (ResultSetExtractor<ResultSet>) rs -> rs);

// Đúng: đọc và đóng gói dữ liệu ngay khi callback còn hiệu lực.
List<String> titles = jdbc.query(
        "SELECT title FROM books ORDER BY id",
        (rs, rowNum) -> rs.getString(1));
```

Trong ví dụ sai, `query` hoàn tất thì template đã có quyền đóng `ResultSet`. Phải biến dữ liệu thành DTO, collection, aggregate hoặc kết quả thuần Java **ngay trong thời gian callback thực thi**.

## 6. PreparedStatementSetter và các callback cấp thấp: quyền hạn đi kèm trách nhiệm

Khi cần tham số `?`, cách đơn giản nhất là dùng overload của `query`/`update`:

```java
List<Book> matching = jdbc.query(
        "SELECT id, title FROM books WHERE id >= ? ORDER BY id",
        BOOK_MAPPER,
        2L);
```

Nếu cần điều khiển binding, dùng `PreparedStatementSetter`:

```java
PreparedStatementSetter setter = ps -> ps.setLong(1, 2L);
List<Book> matching = jdbc.query(
        "SELECT id, title FROM books WHERE id >= ? ORDER BY id",
        setter,
        BOOK_MAPPER);
```

Các đoạn trên dùng `jdbc`/`BOOK_MAPPER` đã được khai báo ở DAO, không phải chương trình chạy riêng. `PreparedStatementSetter` chỉ **đặt tham số**; `JdbcTemplate` mới thực thi và đóng statement. Nếu callback sửa một `PreparedStatement` khác hoặc lưu nó vào field để gọi sau, nó vượt ra ngoài hợp đồng và thường không an toàn.

Với `PreparedStatementCreator` hoặc `PreparedStatementCallback`, quyền truy cập connection/statement trực tiếp nhiều hơn; vì vậy phải tôn trọng vòng đời và xử lý tài nguyên tạo thêm. Không đóng connection hoặc statement đang do template quản lý. Nếu callback tự mở `ResultSet` trong một API cấp thấp, đọc và đóng nó đúng phạm vi phù hợp; **tránh để API JDBC chưa đóng lọt ra ngoài**.

Lý do Spring cung cấp nhiều callback là để người viết chọn mức điều khiển vừa đủ. Không cần xuống API cấp thấp cho một truy vấn có hai tham số và một `RowMapper` đơn giản.

## 7. Ví dụ hoàn chỉnh Java 17+: một JdbcTemplate dùng bởi nhiều thao tác đồng thời

Chương trình dưới đây minh họa:

- Một `DataSource` được Spring cấu hình thành bean; một `JdbcTemplate` có cấu hình cố định.
- Một DAO nhận cùng bean template qua constructor.
- `RowMapper` stateless dùng lại nhiều lần.
- `RowCallbackHandler` tạo accumulator local cho một truy vấn.
- `ResultSetExtractor` tạo accumulator local và tự gọi `rs.next()`.
- `PreparedStatementSetter` bind tham số cho truy vấn.
- Nhiều task đọc dữ liệu cùng lúc qua **một `JdbcTemplate`**. Thứ tự hiển thị kết quả được cố định theo thứ tự nhận `Future`, không dựa vào lịch chạy thực tế.
- Một stream kết quả JDBC được đóng bằng `try-with-resources`.

Ví dụ dùng Java 17+, Spring Framework 6.2.12 và H2 2.3.232, **không yêu cầu Spring Boot**. Phiên bản được cố định để tái lập ví dụ, không nhằm khẳng định chúng là bản mới nhất.

### 7.1. Cấu trúc dự án

```text
shared-jdbc-demo/
├── pom.xml
└── src/main/java/example/SharedJdbcTemplateDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>shared-jdbc-demo</artifactId>
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

`src/main/java/example/SharedJdbcTemplateDemo.java`:

```java
package example;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.StringJoiner;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.stream.Stream;

import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.PreparedStatementSetter;
import org.springframework.jdbc.core.ResultSetExtractor;
import org.springframework.jdbc.core.RowCallbackHandler;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class SharedJdbcTemplateDemo {
    record Book(long id, String title) {}

    static class BookDao {
        private static final RowMapper<Book> BOOK_MAPPER =
                (rs, rowNum) -> new Book(
                        rs.getLong("id"),
                        rs.getString("title"));

        private final JdbcTemplate jdbc;

        BookDao(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        JdbcTemplate template() {
            return jdbc;
        }

        List<Book> findAll() {
            return jdbc.query(
                    "SELECT id, title FROM books ORDER BY id",
                    BOOK_MAPPER);
        }

        Optional<Book> findById(long id) {
            List<Book> results = jdbc.query(
                    "SELECT id, title FROM books WHERE id = ?",
                    BOOK_MAPPER,
                    id);
            return results.stream().findFirst();
        }

        List<String> titlesByCallback() {
            List<String> titles = new ArrayList<>();
            RowCallbackHandler handler =
                    rs -> titles.add(rs.getString("title"));

            jdbc.query(
                    "SELECT title FROM books ORDER BY id",
                    handler);
            return titles;
        }

        String titlesByExtractor() {
            ResultSetExtractor<String> extractor = rs -> {
                StringJoiner joiner = new StringJoiner(" | ");
                while (rs.next()) {
                    joiner.add(rs.getString("title"));
                }
                return joiner.toString();
            };

            return jdbc.query(
                    "SELECT title FROM books ORDER BY id",
                    extractor);
        }

        List<Book> findFrom(long minId) {
            PreparedStatementSetter setter =
                    ps -> ps.setLong(1, minId);

            return jdbc.query(
                    "SELECT id, title FROM books WHERE id >= ? ORDER BY id",
                    setter,
                    BOOK_MAPPER);
        }

        long streamedCount() {
            try (Stream<Book> stream = jdbc.queryForStream(
                    "SELECT id, title FROM books",
                    BOOK_MAPPER)) {
                return stream.count();
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class JdbcConfig {
        @Bean
        DataSource dataSource() {
            DriverManagerDataSource source = new DriverManagerDataSource();
            source.setDriverClassName("org.h2.Driver");
            source.setUrl("jdbc:h2:mem:sharedtemplate;DB_CLOSE_DELAY=-1");
            source.setUsername("sa");
            source.setPassword("");
            return source;
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            JdbcTemplate template = new JdbcTemplate(dataSource);
            template.setQueryTimeout(10); // Chỉ gọi lúc cấu hình.
            return template;
        }

        @Bean
        BookDao bookDao(JdbcTemplate template) {
            return new BookDao(template);
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(JdbcConfig.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            BookDao dao = context.getBean(BookDao.class);

            jdbc.execute(
                    "CREATE TABLE books (id BIGINT PRIMARY KEY, title VARCHAR(100))");
            jdbc.update("INSERT INTO books (id, title) VALUES (?, ?)", 1L, "Java");
            jdbc.update("INSERT INTO books (id, title) VALUES (?, ?)", 2L, "Spring");
            jdbc.update("INSERT INTO books (id, title) VALUES (?, ?)", 3L, "JDBC");

            System.out.println("Same bean: " + (jdbc == dao.template()));
            System.out.println("Rows: " + dao.findAll());
            System.out.println("RowCallbackHandler: " + dao.titlesByCallback());
            System.out.println("ResultSetExtractor: " + dao.titlesByExtractor());
            System.out.println("PreparedStatementSetter: " + dao.findFrom(2L));
            System.out.println("Stream count: " + dao.streamedCount());

            ExecutorService executor = Executors.newFixedThreadPool(3);
            try {
                List<Future<String>> futures = new ArrayList<>();
                for (long id = 1; id <= 3; id++) {
                    long requestedId = id;
                    futures.add(executor.submit(() ->
                            dao.findById(requestedId).orElseThrow().title()));
                }
                List<String> results = new ArrayList<>();
                for (Future<String> future : futures) {
                    results.add(future.get());
                }
                System.out.println("Parallel query results: " + results);
            } finally {
                executor.shutdown();
            }
        }
    }
}
```

Chạy trong thư mục có `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.SharedJdbcTemplateDemo
```

Các dòng `System.out.println` của chương trình (Maven/Spring có thể ghi thêm log riêng tùy môi trường):

```text
Same bean: true
Rows: [Book[id=1, title=Java], Book[id=2, title=Spring], Book[id=3, title=JDBC]]
RowCallbackHandler: [Java, Spring, JDBC]
ResultSetExtractor: Java | Spring | JDBC
PreparedStatementSetter: [Book[id=2, title=Spring], Book[id=3, title=JDBC]]
Stream count: 3
Parallel query results: [Java, Spring, JDBC]
```

### 7.2. Giải thích chính xác thí nghiệm

1. `JdbcConfig` tạo duy nhất một bean `JdbcTemplate` trong context. `dao.template() == jdbc` chứng minh DAO dùng đúng instance bean đó; `true` chỉ là phép so sánh tham chiếu, không phải tự nó chứng minh mọi callback an toàn.
2. `BOOK_MAPPER` là một field static final nhưng không có state biến đổi; mỗi `mapRow` tạo một record `Book`. Kết quả `findAll()` là một danh sách mới cho lời gọi.
3. `titlesByCallback` tạo `ArrayList` mới mỗi lần gọi; nó có mutable state nhưng không share giữa các invocation.
4. `titlesByExtractor` tự gọi `rs.next()`, dùng `StringJoiner` local và trả `String`. Template vẫn sở hữu lifecycle của `ResultSet`.
5. `findFrom` tạo `PreparedStatementSetter` dùng `minId` được chốt cho lần gọi, không sửa cấu hình template.
6. `streamedCount` dùng `try-with-resources` đóng `Stream` và tài nguyên JDBC đằng sau nó.
7. Ba `Callable` chạy qua cùng DAO/template; mỗi task có giá trị `requestedId` riêng. Chương trình đọc `Future` theo thứ tự 1, 2, 3 nên stdout xác định, mặc dù thứ tự các query thật sự chạy không được bảo đảm.
8. `DriverManagerDataSource` tạo connection JDBC mà không dùng pool. Nó được dùng để làm ví dụ ít dependency; **không phải cấu hình khuyến nghị cho lượng request đồng thời ở production**. Với tải thực tế dùng một `DataSource` có pool như HikariCP và giới hạn kết nối phù hợp.
9. H2 in-memory có `DB_CLOSE_DELAY=-1` để database không mất bảng giữa các connection trong cùng tiến trình. Đây là đặc tính H2 của demo; đừng suy ra từ đó rằng mọi database hay mọi driver có quy tắc tương tự.

Tái sử dụng template giúp tránh tạo/cấu hình wrapper lặp lại; nó **không bảo đảm** query đồng thời chạy với cùng tốc độ, không bảo đảm transaction của các request trộn làm một, cũng không tự giải quyết lock, contention và consistency của DB.

## 8. Spring transaction và ThreadLocal: phân biệt chia sẻ template với chia sẻ transaction

Trong Spring JDBC, `JdbcTemplate` có thể tham gia transaction bằng cách lấy connection qua `DataSourceUtils`. Một transaction thông thường do `PlatformTransactionManager` điều phối sử dụng ngữ cảnh gắn với thread, giúp các thao tác trên cùng `DataSource` và cùng thread tham gia transaction đang hoạt động.

Mô hình điển hình:

```text
Thread A: @Transactional service method
          -> Transaction manager
          -> Connection gắn với Thread A
          -> cùng JdbcTemplate gọi query/update
          -> commit/rollback khi service hoàn tất

Thread B: @Transactional service method
          -> Transaction manager
          -> Connection/transaction của Thread B
          -> cùng JdbcTemplate gọi query/update
          -> commit/rollback riêng của B
```

**Không** hiểu rằng singleton `JdbcTemplate` khiến hai thread mặc nhiên dùng chung một transaction. Cũng không nên dùng `Connection` từ Thread A đưa sang Thread B để “tham gia” transaction của A.

Nếu service gọi `CompletableFuture.supplyAsync(...)` hoặc `ExecutorService.submit(...)` khi đang ở một `@Transactional` thông thường, transaction context ràng buộc với thread **không tự lan sang worker thread**. Các JDBC operation trong worker có thể chạy ngoài transaction của caller nếu không có thiết kế propagation phù hợp. Cần xác định ranh giới transaction ở đúng nơi thực thi và kiểm thử kịch bản đồng thời.

Các lưu ý liên quan:

- Dùng cùng `DataSource` hoặc các proxy được Spring hỗ trợ đúng cách nếu muốn `JdbcTemplate` tham gia transaction đang hoạt động.
- `@Transactional` mặc định áp dụng qua proxy trong nhiều cấu hình; self-invocation của phương thức cùng bean không đi qua advice mặc định.
- Rollback và isolation là chính sách của transaction manager/DB; `JdbcTemplate` thread-safe không làm atomic một chuỗi câu lệnh riêng lẻ.
- JDBC `Connection`, `Statement`, `ResultSet` không phải tài nguyên để giữ làm singleton field trong DAO.
- Với database pool, một connection có thể được tái sử dụng *tuần tự* giữa các request sau khi được trả về pool; điều đó không có nghĩa chia sẻ đồng thời connection đang mượn.

## 9. Những cái bẫy khác khi callback chạy đúng cú pháp

### 9.1. Callback capture biến bên ngoài bị thay đổi

Một callback có thể không có field mà vẫn sai nếu capture một collection hoặc object mutable được chia sẻ:

```java
// Sai trong code nhiều request: danh sách tồn tại như field dùng chung.
private final List<Long> idsSeen = new ArrayList<>();

public void listIds() {
    jdbc.query(
            "SELECT id FROM books",
            (RowCallbackHandler) rs -> idsSeen.add(rs.getLong(1)));
}
```

Đây là đoạn trích trong DAO. `RowCallbackHandler` không có lỗi cú pháp; lỗi nằm ở **đối tượng mà lambda capture**. Để sửa, tạo `List<Long> idsSeen` bên trong mỗi method invocation hoặc dùng `RowMapper<Long>` rồi trả về danh sách.

Ngay cả với đối tượng “thread-safe” như `ConcurrentHashMap`, nếu mọi request cùng ghi vào một bảng kết quả dùng chung, vẫn có thể sai **ngữ nghĩa tách request**, dù không phát sinh lỗi cấu trúc bộ nhớ. Đồng bộ hóa dữ liệu và cô lập dữ liệu là hai yêu cầu khác nhau.

### 9.2. Callback chứa I/O, mạng hoặc thao tác tốn thời gian

`RowMapper` và `RowCallbackHandler` được gọi khi JDBC operation vẫn đang hoạt động; nếu mỗi hàng lại gọi HTTP API, ghi file chậm, chờ lock tùy ý hoặc thực hiện N+1 truy vấn, thời gian giữ statement/connection có thể kéo dài, giảm throughput của pool.

Nên map dữ liệu DB thành DTO càng rõ và ngắn càng tốt; xử lý tốn thời gian sau khi truy vấn kết thúc nếu ngữ nghĩa cho phép. Với dữ liệu rất lớn, cân nhắc streaming/fetch size/processing theo batch, nhưng luôn quản lý tài nguyên và transaction tương ứng.

### 9.3. Coi callback có thể dùng bất đồng bộ tùy ý

`JdbcTemplate.query(...)` gọi callback đồng bộ để xử lý `ResultSet` đang mở. Không dùng pattern:

```java
// Sai: đưa ResultSet đang sống sang task xử lý sau.
RowCallbackHandler wrongAsync = rs -> {
    executor.submit(() -> consumeResultSet(rs));
};
```

Đây là pseudocode minh họa lỗi, với `executor`/`consumeResultSet` chưa được định nghĩa. Khi task chạy, `ResultSet` có thể đã được đóng hoặc con trỏ đã di chuyển sang hàng khác; nhiều driver không cho dùng cursor giữa threads như vậy. **Đúng:** đọc và sao chép dữ liệu cần thiết thành DTO immutable ngay trong callback; sau đó mới chuyển DTO sang queue/executor với quy tắc backpressure phù hợp.

### 9.4. Nuốt lỗi SQL hoặc tự đóng tài nguyên không thuộc quyền sở hữu

`JdbcTemplate` chuyển nhiều lỗi JDBC thành `DataAccessException`; callback có thể để `SQLException` nổi lên theo chữ ký interface. Tự bắt `SQLException` rồi trả giá trị giả khiến lỗi hạ tầng giống dữ liệu hợp lệ và làm mất thông tin chẩn đoán.

Không tự gọi `rs.close()` trong `RowMapper` hoặc `RowCallbackHandler`; template có trách nhiệm xử lý `ResultSet` do nó tạo. Không đóng `PreparedStatement` trước khi template dùng xong. Với tài nguyên khác do callback tự mở, dùng `try-with-resources` theo quyền sở hữu thực tế.

### 9.5. Ngộ nhận mọi phương thức trả kết quả đều đóng tài nguyên ngay

Với các API dạng `query(...)` trả DTO/List sau khi xử lý hết, template thường hoàn tất việc dọn dẹp tài nguyên JDBC trước khi trả kết quả. Nhưng `queryForStream(...)` trả về stream lazy có thể **giữ tài nguyên JDBC còn mở đến khi stream được đóng**. Ví dụ đúng:

```java
try (Stream<Book> stream = jdbc.queryForStream(
        "SELECT id, title FROM books ORDER BY id",
        BOOK_MAPPER)) {
    stream.forEach(book -> process(book));
}
```

Đây là đoạn minh họa cần `Stream`, `Book`, `BOOK_MAPPER`, `process` và `jdbc` đã được định nghĩa. `Stream.close()` trong `try-with-resources` là điểm quyết định. Không đưa stream còn mở qua thread khác hoặc ra khỏi phạm vi có thể kiểm soát rồi bỏ mặc việc đóng.

### 9.6. Nhầm safety với tính đúng đắn khi cập nhật dữ liệu

Hai thread dùng cùng `JdbcTemplate` để:

```java
// Đoạn minh họa một câu SQL ở DAO:
int updated = jdbc.update(
        "UPDATE inventory SET quantity = quantity - 1 " +
        "WHERE id = ? AND quantity > 0",
        productId);
```

Câu update có thể an toàn về mức object `JdbcTemplate` nhưng **tính đúng đắn nghiệp vụ** còn phụ thuộc SQL và DB. Ví dụ kiểm tra `updated == 1`, isolation/locking và transaction nếu nhiều bước cập nhật cần commit cùng nhau. Tránh mô hình “SELECT quantity rồi Java trừ rồi UPDATE” mà không có cơ chế đồng thời thích hợp, dù tất cả đều dùng một template thread-safe.

## 10. Kiểm thử để xác nhận cả hai lớp an toàn

Một kiểm thử hữu ích không chỉ assert có cùng bean `JdbcTemplate`. Cần thử **hành vi của callback khi nhiều lời gọi xen kẽ**, đặc biệt là kết quả được cô lập.

### 10.1. Những gì nên xác minh

| Điều cần xác minh | Kiểm thử gợi ý |
| --- | --- |
| Singleton template đã cấu hình xong | Lấy bean từ context; các DAO dùng đúng tham chiếu được inject |
| Mapper stateless | Chạy nhiều query dùng cùng mapper; mỗi query có đúng danh sách riêng |
| Handler state cục bộ | Gọi `titlesByCallback()` lặp lại và đồng thời; không tích lũy dữ liệu từ lần trước |
| Extractor duyệt đủ hàng | Có 0, 1, nhiều hàng; kết quả đúng và không bị bỏ hàng đầu |
| Callback không nhảy con trỏ | Với dữ liệu cố định, `RowMapper`/`RowCallbackHandler` xử lý đúng từng hàng |
| Lỗi JDBC được xử lý đúng | SQL sai/duplicate key gây `DataAccessException` hợp lý, không tạo DTO giả |
| Tài nguyên JDBC được đóng | Pool active connections trở về mức mong đợi; stream được close |
| Transaction đúng | Hai cập nhật nhiều bước rollback theo kỳ vọng khi lỗi giữa chừng |
| DB concurrency đúng | Các cập nhật cạnh tranh không làm âm số lượng hoặc lost update |
| Nhiều request cùng truy vấn | Kiểm tra từng kết quả bằng ID, không đánh giá dựa vào thứ tự lập lịch |

Test có thể dùng `@JdbcTest` với JDBC thực, H2 hoặc Testcontainers khi SQL phụ thuộc dialect. Để phát hiện race, có thể dùng `CountDownLatch`/`CyclicBarrier` điều phối điểm bắt đầu và chạy nhiều lần; **một test chạy thành công không chứng minh không còn race**.

### 10.2. Test nhỏ kiểm tra kết quả tách biệt

Ví dụ với `BookDao` của chương trình ở trên:

```java
// Đoạn JUnit 5, không phải file test hoàn chỉnh.
@Test
void callbackResultsDoNotLeakAcrossCalls() {
    List<String> first = dao.titlesByCallback();
    List<String> second = dao.titlesByCallback();

    assertEquals(List.of("Java", "Spring", "JDBC"), first);
    assertEquals(List.of("Java", "Spring", "JDBC"), second);
    assertNotSame(first, second);
}
```

Cần JUnit Jupiter, static imports `assertEquals`/`assertNotSame` và `dao` được tạo từ fixture DB có ba hàng giống demo. Test này xác nhận method tạo danh sách kết quả riêng từng lần, nhưng cần thêm test đồng thời để phát hiện các lỗi chỉ bộc lộ khi nhiều thread thực thi.

### 10.3. Sử dụng connection pool khi kiểm thử tải

Demo dùng `DriverManagerDataSource` nhằm giảm dependency và cho thấy trách nhiệm template. Trong ứng dụng server nhiều request, `HikariDataSource` hoặc pool phù hợp giúp giới hạn connection, quản lý timeout và tài nguyên. Kiểm tra kết quả dưới tải với kích thước pool phù hợp, latency DB và connection lifetime thực tế; nếu pool có 5 connection, 100 tác vụ cùng dùng template sẽ không đồng nghĩa 100 query DB được thực thi cùng lúc.

## 11. Bảng đối chiếu quyết định thiết kế

| Tình huống | Có thể dùng chung? | Cách làm an toàn |
| --- | --- | --- |
| Một bean `JdbcTemplate` sau cấu hình | **Có** | Inject singleton, không thay đổi setter cấu hình khi request đang chạy |
| `RowMapper<Book>` chỉ đọc current row, tạo record mới | **Có** | Stateless; không gọi `rs.next()` |
| `RowCallbackHandler` ghi vào `ArrayList` mới mỗi method invocation | **Có, theo từng lời gọi** | Tạo list/callback tại call site; không chia sẻ list giữa request |
| `ResultSetExtractor` tạo local `Map` rồi duyệt `rs.next()` | **Có thể tái sử dụng** | Mọi accumulator local cho mỗi `extractData` |
| `PreparedStatementSetter` chỉ bind input riêng của call | **Có** | Tham số không thay đổi khi callback đang chạy |
| `RowMapper` giữ field `int count` và `ArrayList` | **Không an toàn nếu share** | Không giữ request state ở mapper |
| Một `ResultSet`/`PreparedStatement` được lưu trong singleton DAO | **Không** | Giữ tài nguyên trong phạm vi JDBC callback |
| `queryForStream` trả stream lazy | **Chỉ trong vòng đời kiểm soát** | `try-with-resources`, close trước khi kết thúc scope |
| Một singleton `JdbcTemplate` với nhiều transaction/thread | **Có, theo cấu hình đúng** | Transaction theo thread/resource; không tự chia sẻ Connection |
| Hai query cập nhật cùng bản ghi | **Template vẫn thread-safe** | Kiểm soát tính đúng đắn bằng SQL atomic, lock/isolation/transaction |

### Câu hỏi tự kiểm tra

1. “`JdbcTemplate` thread-safe once configured” bảo đảm điều gì, và không bảo đảm điều gì cho callback?
2. Tại sao `static final RowMapper<Book>` có thể dùng chung trong ví dụ, nhưng `static final UnsafeBookMapper` có field mutable vẫn nguy hiểm?
3. Khi nào dùng `RowMapper`, `RowCallbackHandler`, `ResultSetExtractor`? Ai được gọi `rs.next()`?
4. Vì sao handler chứa một `ArrayList` cục bộ vẫn an toàn trong một lần gọi, dù `ArrayList` vốn không thread-safe?
5. Vì sao không nên gọi `jdbcTemplate.setQueryTimeout(...)` theo từng request trên singleton?
6. Một `@Transactional` ở thread A có tự truyền transaction sang `ExecutorService` ở thread B không?
7. Vì sao stream trả về từ `queryForStream` cần đóng, trong khi `query` thông thường trả về `List` đã ánh xạ?
8. Nếu hai thread cùng dùng `JdbcTemplate` để trừ tồn kho, còn cần kiểm soát những điều gì?

**Điểm ghi nhớ:** `JdbcTemplate` được thiết kế để **chia sẻ sau khi cấu hình xong**. An toàn tổng thể phụ thuộc vào callback: dùng `RowMapper` stateless, tạo accumulator cho `RowCallbackHandler`/`ResultSetExtractor` theo từng lời gọi, không làm sai con trỏ, không để tài nguyên JDBC vượt khỏi vòng đời hợp lệ, không sửa cấu hình singleton theo request, và kiểm soát transaction/concurrency ở mức database.

### Tài liệu tham khảo chính thức

- Spring Framework — JDBC core: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — JdbcTemplate API (thread-safe once configured): https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Spring Framework — RowMapper API: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/core/RowMapper.html
- Spring Framework — RowCallbackHandler API: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/core/RowCallbackHandler.html
- Spring Framework — ResultSetExtractor API: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/core/ResultSetExtractor.html

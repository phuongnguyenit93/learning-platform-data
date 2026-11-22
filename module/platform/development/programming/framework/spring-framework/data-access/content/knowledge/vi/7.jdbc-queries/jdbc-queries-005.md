# query() để lấy danh sách đối tượng với Spring JDBC

Trong Spring JDBC, **`JdbcTemplate.query(...)`** là API chủ đạo để đọc **nhiều hàng** từ cơ sở dữ liệu quan hệ và biến mỗi hàng thành một đối tượng Java. Thay vì tự quản lý `Connection`, `PreparedStatement`, `ResultSet` và vòng lặp `while (rs.next())`, bạn đưa SQL và quy tắc ánh xạ cho `JdbcTemplate`. Spring thực thi truy vấn, đi qua từng hàng kết quả, gọi mapper và trả về `List<T>`.

Ví dụ: một câu SQL trả về ba hàng trong bảng `books` thì `query(...)` có thể trả về `List<Book>` gồm ba đối tượng `Book`. Nếu câu SQL không trả hàng nào, kết quả thông thường là **danh sách rỗng**, không phải ngoại lệ “không tìm thấy một bản ghi”.

Bài học thuộc phần **Truy vấn JDBC** và tập trung trực tiếp vào **`query()` để lấy danh sách đối tượng**: cú pháp overload, `RowMapper`, binding tham số, kết quả không có hàng, thiết kế DAO, phân trang và những lỗi thường gặp.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Đọc chữ ký `<T> List<T> query(String sql, RowMapper<T> rowMapper, Object... args)` và mô tả đường đi từ SQL đến từng phần tử `List<T>`.
2. Viết `RowMapper<Book>` bằng lambda, class hoặc constant tái sử dụng; không tự di chuyển con trỏ `ResultSet`.
3. Dùng dấu `?` hoặc named parameter để lọc dữ liệu an toàn, thay vì nối chuỗi từ người dùng.
4. Chọn đúng giữa `query`, `queryForObject`, `queryForList`, `queryForStream` và `RowCallbackHandler`.
5. Giải quyết `NULL`, tên cột, thứ tự kết quả, duplicate rows do `JOIN`, SQL dialect và hiệu năng khi truy vấn nhiều hàng.
6. Kiểm thử số lượng bản ghi, nội dung từng object, trường hợp rỗng, lỗi SQL và thứ tự phân trang.

## 2. Cơ chế hoạt động: một hàng thành một đối tượng

Giả sử truy vấn:

~~~sql
SELECT id, title, pages
FROM books
WHERE pages >= ?
ORDER BY id
~~~

Trả về:

| id | title | pages |
| ---: | --- | ---: |
| 1 | Java Basics | 320 |
| 2 | Spring JDBC | 240 |

Bạn định nghĩa kiểu dữ liệu:

~~~java
public record Book(long id, String title, int pages) { }
~~~

Và ánh xạ mỗi hàng thành một `Book`:

~~~java
RowMapper<Book> bookMapper = (rs, rowNum) ->
        new Book(
                rs.getLong("id"),
                rs.getString("title"),
                rs.getInt("pages")
        );
~~~

Sau đó gọi:

~~~java
List<Book> books = jdbcTemplate.query(
        """
        SELECT id, title, pages
        FROM books
        WHERE pages >= ?
        ORDER BY id
        """,
        bookMapper,
        240
);
~~~

Đây là **các đoạn mã tích hợp**: giả sử `jdbcTemplate` đã được Spring cung cấp, bảng `books` và dữ liệu ví dụ tồn tại; không phải chương trình standalone. Phần 4 sẽ có chương trình hoàn chỉnh.

Spring thực hiện về mặt khái niệm:

~~~text
DAO gọi JdbcTemplate.query(sql, mapper, args)
    |
    v
Lấy JDBC Connection phù hợp từ DataSource/transaction
    |
    v
Tạo PreparedStatement, bind tham số (pages >= 240)
    |
    v
Thực thi SQL -> ResultSet
    |
    +-- hàng 0 -> mapper.mapRow(rs, 0) -> Book(1, ...)
    |
    +-- hàng 1 -> mapper.mapRow(rs, 1) -> Book(2, ...)
    |
    +-- hết hàng
    |
    v
Đóng ResultSet/Statement, giải phóng Connection khi thích hợp
    |
    v
Trả về List<Book>
~~~

### Phân biệt vai trò các thành phần

| Thành phần | Nhiệm vụ |
| --- | --- |
| `JdbcTemplate` | Thực thi SQL, quản lý JDBC resources, dịch `SQLException` và tập hợp kết quả |
| `DataSource` | Cấp JDBC `Connection` hoặc kết nối từ pool |
| `PreparedStatement` | Thực thi SQL với các tham số đã bind |
| `ResultSet` | Con trỏ đọc các hàng truy vấn trả về |
| `RowMapper<T>` | Chuyển **một hàng đang được định vị** thành một `T` |
| `List<T>` | Chứa các object sau khi query hoàn thành; được giữ trong bộ nhớ ứng dụng |

**Điểm quan trọng nhất:** `JdbcTemplate` chịu trách nhiệm gọi `rs.next()` để đi qua từng hàng. `RowMapper.mapRow(rs, rowNum)` chỉ đọc **hàng hiện tại**, rồi trả một đối tượng. **Không gọi `rs.next()` bên trong `RowMapper`.** Nếu tự di chuyển con trỏ, bạn có thể bỏ qua hàng, trả sai dữ liệu hoặc phá cơ chế lặp của template.

Tham số `rowNum` là vị trí hàng kết quả bắt đầu từ **0**; không phải ID của bảng, cũng không phải số thứ tự ổn định giữa các lần chạy nếu SQL thiếu `ORDER BY`.

## 3. Các overload của query() và cách chọn

Các mẫu sau đều dùng Spring JDBC `JdbcTemplate`:

~~~java
// A. SQL cố định, không bind tham số: trả List<Book>.
List<Book> all = jdbcTemplate.query(
        "SELECT id, title, pages FROM books ORDER BY id",
        bookMapper);

// B. SQL có tham số vị trí: RowMapper trước, giá trị sau.
List<Book> filtered = jdbcTemplate.query(
        "SELECT id, title, pages FROM books WHERE pages >= ? ORDER BY id",
        bookMapper,
        240);

// C. Nhiều tham số: đúng thứ tự dấu ? trong SQL.
List<Book> range = jdbcTemplate.query(
        """
        SELECT id, title, pages FROM books
        WHERE pages >= ? AND pages <= ?
        ORDER BY pages, id
        """,
        bookMapper,
        150,
        350);
~~~

Tất cả là snippet cần biến `jdbcTemplate`, `bookMapper` và schema đã có. **Cú pháp hiện đại nên ưu tiên** là:

~~~java
jdbcTemplate.query(sql, rowMapper, arg1, arg2);
~~~

Một overload cũ nhận `Object[] args` trước `RowMapper` đã bị deprecated trong các nhánh Spring Framework hiện đại; tránh học theo ví dụ cũ chỉ vì có cú pháp `query(sql, new Object[]{...}, mapper)`.

### 3.1. Lambda RowMapper so với class riêng

Nếu chỉ dùng mapper một nơi và mapping ngắn, lambda đủ rõ:

~~~java
List<Book> books = jdbcTemplate.query(
        "SELECT id, title, pages FROM books ORDER BY id",
        (rs, rowNum) -> new Book(
                rs.getLong("id"),
                rs.getString("title"),
                rs.getInt("pages")));
~~~

Nếu nhiều DAO methods cùng dùng mapping, trích ra constant:

~~~java
private static final RowMapper<Book> BOOK_MAPPER =
        (rs, rowNum) -> new Book(
                rs.getLong("id"),
                rs.getString("title"),
                rs.getInt("pages"));
~~~

Nếu mapping dài, có nhiều conversion/domain validation hoặc được chia sẻ giữa nhiều class, triển khai class `BookRowMapper implements RowMapper<Book>`. Dù dùng cách nào, mapper nên **stateless**: không lưu `ResultSet` hoặc danh sách hiện tại vào field singleton, không mutate object dùng chung giữa request.

### 3.2. PreparedStatementSetter cho thao tác bind chuyên biệt

Khi cần điều khiển kiểu SQL hoặc cách bind vượt quá giá trị đơn giản, có overload nhận `PreparedStatementSetter`:

~~~java
List<Book> books = jdbcTemplate.query(
        """
        SELECT id, title, pages
        FROM books WHERE pages >= ? ORDER BY id
        """,
        ps -> ps.setInt(1, 240),
        BOOK_MAPPER);
~~~

Đây là đoạn mã trong DAO có `JdbcTemplate` và `BOOK_MAPPER`. JDBC dùng vị trí bind bắt đầu từ **1** (`ps.setInt(1, ...)`), khác `rowNum` của mapper bắt đầu từ 0. Không tự dùng `PreparedStatement` để nối input không an toàn. Với số lượng tham số bình thường, overload varargs đơn giản hơn.

### 3.3. Điều gì xảy ra nếu không có hàng?

~~~java
List<Book> none = jdbcTemplate.query(
        "SELECT id, title, pages FROM books WHERE pages > ?",
        BOOK_MAPPER,
        1_000_000);
System.out.println(none.isEmpty()); // true
~~~

Đây là ví dụ khi database không có `books.pages` lớn như điều kiện. `query` trả về một `List<Book>` rỗng; mapper **không được gọi** nếu `ResultSet` không có hàng. Không cần dùng `try/catch(EmptyResultDataAccessException)` chỉ để xử lý danh sách rỗng.

Ngược lại, SQL sai, mất kết nối, lỗi quyền hoặc binding không hợp lệ vẫn có thể ném một `DataAccessException` (hoặc lỗi runtime từ mã mapping). **Danh sách rỗng không đồng nghĩa truy vấn lỗi.**

## 4. Chương trình chạy được: Java 17+, Spring JDBC và H2

Ví dụ này tạo bảng H2, thêm ba cuốn sách và minh họa query toàn bộ, query theo điều kiện, query không có hàng và query bằng boolean. Nó **không cần Spring Boot**, nhưng dùng các API Spring JDBC thật.

Cấu trúc:

~~~text
jdbc-list-query/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/App.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jdbc-list-query'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.11'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.App'
}
~~~

`src/main/java/demo/App.java`:

~~~java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import javax.sql.DataSource;
import java.util.List;

public class App {

    public record Book(
            long id, String title, int pages, boolean available) {
    }

    public static class BookDao {
        private static final RowMapper<Book> BOOK_MAPPER =
                (rs, rowNum) -> new Book(
                        rs.getLong("id"),
                        rs.getString("title"),
                        rs.getInt("pages"),
                        rs.getBoolean("available"));

        private final JdbcTemplate jdbc;

        public BookDao(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        public List<Book> all() {
            return jdbc.query(
                    """
                    SELECT id, title, pages, available
                    FROM books ORDER BY id
                    """,
                    BOOK_MAPPER);
        }

        public List<Book> withAtLeastPages(int minPages) {
            return jdbc.query(
                    """
                    SELECT id, title, pages, available
                    FROM books
                    WHERE pages >= ?
                    ORDER BY id
                    """,
                    BOOK_MAPPER,
                    minPages);
        }

        public List<Book> available() {
            return jdbc.query(
                    """
                    SELECT id, title, pages, available
                    FROM books
                    WHERE available = ?
                    ORDER BY id
                    """,
                    BOOK_MAPPER,
                    true);
        }
    }

    public static void main(String[] args) {
        DataSource dataSource = new DriverManagerDataSource(
                "jdbc:h2:mem:library;DB_CLOSE_DELAY=-1", "sa", "");
        JdbcTemplate jdbc = new JdbcTemplate(dataSource);

        jdbc.execute("""
                CREATE TABLE books (
                    id BIGINT PRIMARY KEY,
                    title VARCHAR(100) NOT NULL,
                    pages INT NOT NULL,
                    available BOOLEAN NOT NULL
                )
                """);

        jdbc.update(
                "INSERT INTO books VALUES (?, ?, ?, ?)",
                1L, "Java Basics", 320, true);
        jdbc.update(
                "INSERT INTO books VALUES (?, ?, ?, ?)",
                2L, "Spring JDBC", 240, true);
        jdbc.update(
                "INSERT INTO books VALUES (?, ?, ?, ?)",
                3L, "SQL Primer", 180, false);

        BookDao dao = new BookDao(jdbc);

        System.out.println("Tất cả: " + dao.all());
        System.out.println("Từ 240 trang: " + dao.withAtLeastPages(240));
        System.out.println("Không tìm thấy: " + dao.withAtLeastPages(500));
        System.out.println("Có sẵn: " + dao.available());
    }
}
~~~

Chạy trong thư mục `jdbc-list-query`, với JDK 17+ và Gradle tương thích:

~~~bash
gradle run --quiet
~~~

**Stdout của chương trình** (không tính dòng log mà môi trường Gradle/driver có thể in thêm):

~~~text
Tất cả: [Book[id=1, title=Java Basics, pages=320, available=true], Book[id=2, title=Spring JDBC, pages=240, available=true], Book[id=3, title=SQL Primer, pages=180, available=false]]
Từ 240 trang: [Book[id=1, title=Java Basics, pages=320, available=true], Book[id=2, title=Spring JDBC, pages=240, available=true]]
Không tìm thấy: []
Có sẵn: [Book[id=1, title=Java Basics, pages=320, available=true], Book[id=2, title=Spring JDBC, pages=240, available=true]]
~~~

### 4.1. Đọc lại từng bước

1. `DriverManagerDataSource` tạo nguồn kết nối JDBC đến H2 in-memory. `DB_CLOSE_DELAY=-1` giữ database tồn tại trong vòng đời JVM dù kết nối cuối được đóng. Đây là cấu hình **demo**, không có pool.
2. `jdbc.execute(CREATE TABLE ...)` tạo bốn cột với `NOT NULL` để mapper có thể đọc `long`, `int` và `boolean` mà không phải xử lý SQL `NULL`.
3. Ba `jdbc.update` dùng `?` để bind dữ liệu riêng khỏi SQL. Việc bind giảm nguy cơ SQL injection qua **giá trị** đầu vào.
4. `BookDao` nhận `JdbcTemplate` qua constructor và dùng một `BOOK_MAPPER` stateless. Mỗi hàng biến thành một `Book` mới; record Java tự sinh `toString()` nên kết quả in có dạng `Book[id=..., title=..., ...]`.
5. `all()` trả ba phần tử; `withAtLeastPages(240)` trả hai; `withAtLeastPages(500)` trả danh sách rỗng; `available()` lọc cột `BOOLEAN`.
6. Tất cả SQL đều có `ORDER BY id` nên thứ tự phần tử trong `List` có thể dự đoán. Không có `ORDER BY`, database **không cam kết** thứ tự hàng.
7. Sau mỗi `query`, `JdbcTemplate` đóng JDBC statement/result set và giải phóng connection đúng phạm vi (hoặc tham gia transaction đang hoạt động). `List<Book>` chứa **object Java đã được mapping**, không còn giữ `ResultSet` mở.

Ví dụ không dùng `@Transactional` vì chỉ minh họa các truy vấn độc lập. Khi có service transaction, hãy để Spring quản lý manager và ranh giới transaction. Trong Spring Boot, thường inject `JdbcTemplate` bean tự cấu hình thay vì tự tạo `DriverManagerDataSource` trong mã nghiệp vụ.

## 5. Đặt query() trong DAO/Repository

Một tổ chức phổ biến:

~~~text
Controller / Scheduled job
          |
          v
       Service
          |
          v
    BookRepository
          |
          v
  JdbcTemplate.query(...)
          |
          v
       Database
~~~

Thay vì để controller viết SQL, DAO bao thao tác tìm kiếm thành phương thức biểu đạt ý nghĩa:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;
import java.util.List;

@Repository
public class BookRepository {
    private static final RowMapper<Book> MAPPER = (rs, n) ->
            new Book(
                    rs.getLong("id"),
                    rs.getString("title"),
                    rs.getInt("pages"));

    private final JdbcTemplate jdbc;

    public BookRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<Book> findByMinimumPages(int minPages) {
        return jdbc.query(
                """
                SELECT id, title, pages FROM books
                WHERE pages >= ? ORDER BY id
                """,
                MAPPER,
                minPages);
    }
}
~~~

Đây là snippet trong ứng dụng Spring đã có bean `JdbcTemplate` và kiểu `Book` ba trường đúng như mục 2; không phải class standalone độc lập. Constructor injection làm dependency rõ và dễ thay trong test. `@Repository` đánh dấu bean khi component scanning được bật; constructor đơn không nhất thiết phải có `@Autowired`.

Không lưu `List<Book>` kết quả ở field singleton chỉ để “tái sử dụng” nếu không có chiến lược caching/invalidation rõ: đó là dữ liệu thay đổi theo database, khác với việc tái sử dụng `JdbcTemplate` hay stateless `RowMapper`.

### 5.1. Thiết kế contract trả về

Một số lựa chọn:

- `List<Book> findAll()`: dùng `query`; không có hàng -> `List` rỗng.
- `List<Book> findByStatus(...)`: vẫn dùng `query` vì có thể có 0 đến N hàng.
- `Optional<Book> findById(...)`: thường query một danh sách nhỏ rồi kiểm tra 0/1 hoặc dùng API một hàng với xử lý cardinality thích hợp.
- `Book getRequiredById(...)`: nếu nghiệp vụ đòi chính xác một hàng, dùng `queryForObject` và chuyển “not found” thành lỗi domain phù hợp.
- `Page<Book> findPage(...)`: cần SQL phân trang và truy vấn tổng số bản ghi theo yêu cầu; `JdbcTemplate.query` tự nó chỉ tạo `List`, không tự thiết lập metadata `Page`.

Đừng ép mọi thao tác SELECT dùng `queryForObject`: tên phương thức đó nói rõ chỉ mong **một hàng**.

## 6. Những khác biệt dễ nhầm với các API truy vấn khác

| API | Kết quả / cơ chế | Nên dùng |
| --- | --- | --- |
| `query(sql, rowMapper, args...)` | `List<T>`, mỗi hàng thành một `T` | 0..N object với mapping tùy chỉnh |
| `queryForObject(sql, rowMapper, args...)` | Một `T`; lỗi nếu số hàng khác 1 | Truy vấn đòi chính xác một hàng |
| `queryForList(sql, String.class, args...)` | `List<String>` cho kết quả **một cột** | Danh sách scalar: tên, email, mã |
| `queryForList(sql, args...)` | `List<Map<String,Object>>` | Khảo sát dữ liệu động, không cần DTO cố định |
| `queryForStream(sql, rowMapper, args...)` | `Stream<T>` có tài nguyên cần đóng | Xử lý kết quả theo stream có kiểm soát |
| `query(sql, RowCallbackHandler)` | Callback xử lý từng hàng, không tạo `List<T>` | Tránh tích lũy toàn bộ dữ liệu khi xử lý |
| `query(sql, ResultSetExtractor<T>)` | Hàm nhận toàn bộ `ResultSet` và tự trích xuất `T` | Cần gộp nhiều hàng thành một object graph đặc biệt |
| `JdbcClient.sql(...).query(Book.class).list()` | Fluent API tạo danh sách qua mapper phù hợp | Code Spring Framework 6.1+ muốn cú pháp fluent |

### 6.1. queryForObject() có ngoại lệ khi không có hàng

~~~java
Book book = jdbcTemplate.queryForObject(
        "SELECT id, title, pages FROM books WHERE id = ?",
        BOOK_MAPPER,
        123L);
~~~

Nếu SQL không trả hàng, `queryForObject` sẽ ném `EmptyResultDataAccessException` (một nhánh `IncorrectResultSizeDataAccessException`). Nếu trả nhiều hơn một hàng, cũng ném lỗi kích thước kết quả không đúng. Khác với `query(...)` trả danh sách rỗng khi không có hàng.

Đây là snippet cần `BOOK_MAPPER` cho `Book` và database thực tế. Việc xử lý `not found` nên là quyết định của contract nghiệp vụ; không bắt mọi phương thức trả `null`.

### 6.2. queryForList() cho danh sách scalar

~~~java
List<String> titles = jdbcTemplate.queryForList(
        "SELECT title FROM books WHERE pages >= ? ORDER BY id",
        String.class,
        240);
~~~

Trả `List<String>`, không cần `RowMapper<Book>` vì query chỉ có một cột. Nếu query trả nhiều cột nhưng bạn yêu cầu `String.class`, sẽ phát sinh lỗi số cột không phù hợp. Với DTO nhiều trường, `query(...)` cùng `RowMapper` thường rõ hơn `List<Map<String,Object>>`.

### 6.3. ResultSetExtractor khác RowMapper

`RowMapper` chuyển **một hàng thành một object**. `ResultSetExtractor<T>` được gọi với toàn bộ `ResultSet` để tự điều khiển `rs.next()` và cách gộp dữ liệu. Nếu có `JOIN` làm một sách xuất hiện lặp cho mỗi tác giả, bạn có thể dùng `ResultSetExtractor` để tạo một `BookWithAuthors` từ nhiều hàng. Với các query đơn giản 1 hàng = 1 đối tượng, `RowMapper` ít lỗi và dễ test hơn.

## 7. Xử lý cột SQL NULL và ánh xạ kiểu dữ liệu

Mapper phải phản ánh schema. Ví dụ trên dùng `id BIGINT NOT NULL`, `pages INT NOT NULL`, `available BOOLEAN NOT NULL`. Nếu cột có thể `NULL`:

~~~java
int rawPages = rs.getInt("pages");
Integer pages = rs.wasNull() ? null : rawPages;
~~~

Lý do: các getter primitive như `getInt(...)`, `getLong(...)`, `getBoolean(...)` trả `0`/`false` cho SQL `NULL`; để phân biệt null cần gọi `rs.wasNull()` **ngay sau** getter của cột đó. Với `String`, `getString(...)` trả `null` khi SQL NULL.

Ví dụ mapper cho record nullable:

~~~java
record BookView(long id, String title, Integer pages) {}

RowMapper<BookView> mapper = (rs, rowNum) -> {
    int raw = rs.getInt("pages");
    Integer pages = rs.wasNull() ? null : raw;
    return new BookView(
            rs.getLong("id"),
            rs.getString("title"),
            pages);
};
~~~

Hai đoạn trên là snippet nằm trong mapper/method; không phải chương trình độc lập. Nếu `id` cũng nullable, phải chọn kiểu wrapper và cách đọc phù hợp.

### 7.1. Alias cột để mapper ổn định

Khi SQL có phép tính, join hoặc tên cột khác với DTO, dùng alias:

~~~sql
SELECT
    b.id AS book_id,
    b.title AS book_title,
    COUNT(r.id) AS review_count
FROM books b
LEFT JOIN reviews r ON r.book_id = b.id
GROUP BY b.id, b.title
ORDER BY b.id
~~~

Mapper tương ứng đọc `rs.getLong("book_id")`, `rs.getString("book_title")`, `rs.getLong("review_count")`. Đây là **SQL minh họa**, yêu cầu bảng `reviews` tồn tại. Alias giúp tránh lỗi khi hai bảng cùng có cột `id` và tạo contract rõ giữa query và mapper.

Hãy chỉ SELECT những cột thực sự cần; tránh `SELECT *` trong API có DTO cố định vì thay đổi schema hoặc JOIN dễ làm mapper nhập nhằng, tăng tải network và memory.

### 7.2. Mapping tự động bằng BeanPropertyRowMapper/DataClassRowMapper

Spring còn cung cấp:

- `BeanPropertyRowMapper<T>`: ánh xạ tên cột vào property của JavaBean có constructor không tham số và setter phù hợp; tiện cho DTO bean đơn giản.
- `DataClassRowMapper<T>`: hỗ trợ data-class-style constructor/record mapping, phụ thuộc metadata tên tham số/constructor; phù hợp khi tên cột khớp component của record.
- `ColumnMapRowMapper`, `SingleColumnRowMapper`: phục vụ kết quả map hoặc một cột đơn.

Ví dụ **minh họa tích hợp** cho record ba trường ở mục 2:

~~~java
import org.springframework.jdbc.core.DataClassRowMapper;

List<Book> books = jdbcTemplate.query(
        "SELECT id, title, pages FROM books ORDER BY id",
        DataClassRowMapper.newInstance(Book.class));
~~~

Không phải mọi SQL alias/type tự khớp. Mapper tự động dùng reflection/conversion, thuận tiện nhưng có thể phát hiện sai cột hoặc dữ liệu thiếu muộn hơn và có chi phí hơn mapper tường minh. Với phần quan trọng về hiệu năng, cần conversion đặc biệt hoặc hợp đồng schema chặt chẽ, `RowMapper` viết tay thường dễ kiểm soát.

## 8. Bind tham số và an toàn SQL

Với giá trị do người dùng nhập, **không ghép trực tiếp** vào SQL:

~~~java
// Sai: có thể bị SQL injection.
String sql = "SELECT id, title, pages FROM books WHERE title = '"
        + userInput + "'";
List<Book> unsafe = jdbcTemplate.query(sql, BOOK_MAPPER);
~~~

Thay bằng placeholder `?`:

~~~java
List<Book> safe = jdbcTemplate.query(
        """
        SELECT id, title, pages
        FROM books WHERE title = ?
        ORDER BY id
        """,
        BOOK_MAPPER,
        userInput);
~~~

Các đoạn này giả sử `userInput`, `BOOK_MAPPER` và repository đã được định nghĩa. JDBC driver bind tham số giá trị vào `PreparedStatement`, tránh diễn giải chúng là cấu trúc SQL.

**Caveat:** Placeholder thường chỉ thay thế **giá trị**, không thay thế identifier như tên bảng/cột hay hướng `ORDER BY ASC/DESC`. Nếu cho phép sort theo input, dùng **allowlist** các cột/hướng hợp lệ rồi ghép identifier đã kiểm soát. Không chấp nhận nguyên văn fragment SQL từ API.

### 8.1. NamedParameterJdbcTemplate cho điều kiện phức tạp

Khi có nhiều điều kiện tùy chọn, tên tham số dễ đọc hơn thứ tự dấu `?`:

~~~java
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

MapSqlParameterSource parameters =
        new MapSqlParameterSource()
                .addValue("minimum", 150)
                .addValue("maximum", 350);

List<Book> books = namedJdbc.query(
        """
        SELECT id, title, pages FROM books
        WHERE pages BETWEEN :minimum AND :maximum
        ORDER BY id
        """,
        parameters,
        BOOK_MAPPER);
~~~

`namedJdbc` là `NamedParameterJdbcTemplate` được inject vào DAO; đây là snippet tích hợp. Spring parse named parameter thành placeholder và bind an toàn. `IN (:ids)` cũng hỗ trợ collection phù hợp, nhưng phải xử lý tập `ids` rỗng chủ động: không phụ thuộc một chuỗi `IN ()` có thể không hợp lệ theo dialect. Với collection không có ID, thường trả `List.of()` ngay hoặc dùng chính sách truy vấn khác.

Trong repository có nhiều API, chọn `JdbcTemplate` hay `NamedParameterJdbcTemplate` theo độ rõ của SQL; cả hai có thể chia sẻ cùng `DataSource` và tham gia transaction phù hợp.

## 9. Thứ tự, JOIN, DISTINCT và đối tượng bị trùng

**`List` giữ thứ tự hàng mà query trả về.** Nhưng nếu SQL không có `ORDER BY`, database không đảm bảo thứ tự ổn định, kể cả khi bảng có primary key. Với API phân trang, luôn định nghĩa thứ tự quyết định được, ví dụ `ORDER BY created_at DESC, id DESC` để phá hòa.

`JOIN` có thể nhân hàng. Ví dụ một cuốn sách có ba tags, query JOIN `books`–`book_tags` tạo ba hàng cho cùng book. `query(..., BOOK_MAPPER)` sẽ tạo **ba object `Book`**, vì mapping cơ bản là **một hàng -> một phần tử**; template không tự loại bỏ trùng ID.

Cách xử lý tùy yêu cầu:

1. Chỉ cần sách không trùng: thay SQL dùng `EXISTS`, `SELECT DISTINCT` hoặc query lấy khóa sách trước, tùy dữ liệu/SQL dialect.
2. Cần object graph sách + nhiều tags: dùng `ResultSetExtractor` để gộp nhiều hàng vào một parent object, hoặc truy vấn cha/con riêng và gộp có kiểm soát.
3. Cần phân trang parent: phân trang trên khóa parent trước, tránh áp dụng `LIMIT/OFFSET` trực tiếp lên result join nhiều child gây thiếu parent.

Đừng tự dùng `stream().distinct()` sau khi đã tải hàng triệu bản ghi để “chữa cháy” một câu SQL JOIN sai; làm đúng ở tầng SQL thường hiệu quả hơn.

## 10. Phân trang danh sách: tránh tải vô hạn

`jdbcTemplate.query(...)` với `RowMapper` thông thường trả **toàn bộ `List<T>`** trước khi method kết thúc. Nếu query trả hàng triệu hàng, việc tạo và giữ toàn bộ object có thể tốn nhiều RAM và tạo GC pressure. Hãy phân trang từ database, giới hạn dữ liệu và chọn projection cần thiết.

Ví dụ SQL cho PostgreSQL, H2 hoặc một số dialect hỗ trợ `LIMIT/OFFSET` (snippet ứng dụng đã có mapper):

~~~java
public List<Book> findPage(int pageSize, long offset) {
    if (pageSize < 1 || pageSize > 100 || offset < 0) {
        throw new IllegalArgumentException("Invalid page request");
    }
    return jdbcTemplate.query(
            """
            SELECT id, title, pages FROM books
            ORDER BY id
            LIMIT ? OFFSET ?
            """,
            BOOK_MAPPER,
            pageSize,
            offset);
}
~~~

API `LIMIT/OFFSET` không phải SQL portable cho mọi database. SQL Server, Oracle và các dialect khác có cú pháp khác; bind/pagination phải được xác minh trên driver thực.

**Khuyến nghị:**

- Giới hạn page size ở service/API; không để client yêu cầu hàng trăm nghìn bản ghi một lần.
- Dùng `ORDER BY` ổn định, thêm cột unique như `id` để tránh hòa thứ tự.
- Cân nhắc **keyset pagination** cho danh sách rất sâu (lọc theo khóa cuối cùng đã trả) để tránh chi phí OFFSET lớn; cần SQL và index phù hợp.
- Nếu API cần tổng số hàng, chạy query `COUNT(*)` phù hợp qua `queryForObject(..., Long.class)`; `query` chỉ trả list dữ liệu, không tự tạo tổng số trang.
- Tránh `SELECT *` và lưu cả blob/text lớn khi list view chỉ cần vài trường.

### 10.1. Fetch size không phải page size

`JdbcTemplate.setFetchSize(500)` là **hint JDBC driver** về số hàng nên fetch một lần, không bảo đảm kết quả chỉ có 500 phần tử. `jdbcTemplate.query(...)` vẫn có thể tập hợp toàn bộ danh sách trong RAM. Hiệu quả fetch size phụ thuộc driver, DB, autocommit/transaction và cursor.

`setMaxRows` có thể giới hạn result set ở mức statement nhưng không thay cho semantics phân trang có `ORDER BY` và điều kiện SQL rõ. Nếu template được chia sẻ cho nhiều DAO, đặt max rows chung có thể âm thầm làm thiếu dữ liệu ở những query khác.

## 11. Xử lý dữ liệu lớn mà không tạo List khổng lồ

Khi cần xử lý từng hàng (xuất file, tổng hợp, chuyển sang pipeline) thay vì trả list cho API, cân nhắc `RowCallbackHandler` hoặc `queryForStream`.

### 11.1. RowCallbackHandler

~~~java
jdbcTemplate.query(
        "SELECT id, title, pages FROM books ORDER BY id",
        rs -> {
            long id = rs.getLong("id");
            String title = rs.getString("title");
            int pages = rs.getInt("pages");
            exportOneRow(id, title, pages);
        });
~~~

Đây là snippet giả sử `exportOneRow(...)` là phương thức ghi ra sink phù hợp. Spring đã di chuyển con trỏ; `RowCallbackHandler.processRow` **không gọi `rs.next()`**. Cách này không yêu cầu tự dựng `List<Book>`, nhưng SQL driver có thể vẫn buffer nhiều dữ liệu; xem cấu hình streaming/cursor theo DB và đừng thực hiện I/O chậm trong transaction dài mà chưa cân nhắc tác động.

### 11.2. queryForStream cần đóng stream

~~~java
import java.util.stream.Stream;

try (Stream<Book> stream = jdbcTemplate.queryForStream(
        "SELECT id, title, pages FROM books ORDER BY id",
        BOOK_MAPPER)) {
    stream.forEach(book -> processBook(book));
}
~~~

Đây là snippet cần `processBook` và mapper đã có. `queryForStream` trả một `Stream` giữ resource JDBC đến khi stream đóng; **dùng try-with-resources**, tiêu thụ trong phạm vi connection/transaction hợp lệ. Không trả stream gắn `ResultSet` đang mở ra khỏi service rồi quên đóng.

**Lưu ý:** JDBC vẫn là blocking I/O. Dùng Java `Stream` không biến `JdbcTemplate` thành R2DBC/reactive và không tự tạo backpressure xuyên driver. Với API trả một trang danh sách có giới hạn, `query(..., RowMapper)` vẫn là lựa chọn đơn giản.

## 12. Transaction, DataSource và thread safety

`JdbcTemplate` lấy connection qua hạ tầng Spring; trong một JDBC transaction do `DataSourceTransactionManager` hoặc `JdbcTransactionManager` điều phối, các template dùng cùng `DataSource` có thể tham gia connection được bind vào transaction hiện tại.

~~~text
Service @Transactional
    |
    +--> dao.findBooks() -> jdbcTemplate.query(...) -> transaction Connection
    |
    +--> dao.findTags()  -> jdbcTemplate.query(...) -> same transaction context
    |
    +--> commit or rollback
~~~

Điều kiện: các lời gọi phải đi qua transaction infrastructure phù hợp, cùng resource, và cách quản lý context đúng. Một `JdbcTemplate` được chia sẻ giữa hai DAO **không** tự tạo transaction; nếu không có `@Transactional` phù hợp, mỗi query có thể chạy theo autocommit/connection riêng.

`@Transactional(readOnly=true)` có thể là tối ưu/hint cho truy vấn đọc, nhưng không đảm bảo database sẽ chặn mọi lệnh ghi. Đừng giữ transaction đọc mở suốt lúc gọi API bên ngoài, chờ người dùng hoặc xuất file rất lâu khi không cần consistency snapshot.

**Đồng thời:** Bản thân `JdbcTemplate` đã cấu hình có thể dùng chung giữa nhiều thread. Nhưng nếu `RowMapper` hoặc DAO chứa field mutable làm bộ đệm cho danh sách đang đọc, race condition vẫn xảy ra. Mỗi lần `query` nên tạo object kết quả riêng; không mutate `jdbcTemplate.setFetchSize`/`setQueryTimeout` giữa nhiều request như thể đó là tùy chọn cục bộ.

## 13. Xử lý ngoại lệ: SQL lỗi khác với danh sách rỗng

Spring dịch nhiều lỗi JDBC thành hệ `DataAccessException` (runtime). Một số trường hợp cần phân biệt:

| Hiện tượng | Kết quả nên hiểu |
| --- | --- |
| Query hợp lệ nhưng không trả hàng | `query(...)` trả list rỗng |
| Query hợp lệ trả 10 hàng | List chứa 10 kết quả mapping (trừ khi mapper tự trả `null` cho một hàng) |
| SQL sai cú pháp | Thường có `BadSqlGrammarException`, một `DataAccessException` |
| Connection bị ngắt | Một loại `DataAccessException` tùy translator/driver |
| Mapper đọc cột không tồn tại | Có thể ném `SQLException` và được Spring dịch, hoặc lỗi runtime tương ứng |
| Mapper tự ném `IllegalArgumentException` | Lỗi runtime của logic mapping; không mặc định trở thành `DataAccessException` |
| `queryForObject` không có hàng | `EmptyResultDataAccessException` |
| `queryForObject` có nhiều hơn một hàng | `IncorrectResultSizeDataAccessException` |

Không bao toàn bộ truy vấn bằng `catch(Exception e) { return List.of(); }`: cách này biến outage/SQL bug thành một kết quả “không có dữ liệu”, làm che sự cố. Để lỗi lan tới tầng service/exception handler phù hợp; chỉ trả list rỗng khi query thật sự thành công nhưng không có bản ghi.

Trường hợp mapper trả `null` cho một hàng khác danh sách rỗng: list có thể chứa phần tử `null`. Với domain DTO, nên mapping hợp lệ hoặc ném lỗi rõ ràng thay vì lặng lẽ trả null per row.

## 14. Kiểm thử query() có ý nghĩa

Với integration test trên H2 hoặc database tương thích production, hãy chuẩn bị dữ liệu có thứ tự chủ động rồi kiểm tra:

1. **Nhiều hàng:** `query` trả đúng số phần tử, đúng id/title/pages, không chỉ kiểm tra `size()`.
2. **Không có hàng:** `query` trả `List` rỗng, không ném `EmptyResultDataAccessException`.
3. **Bind tham số:** Với minPages 240, SQL chọn đúng sách; thử input bất thường để khẳng định không nối SQL nguy hiểm.
4. **Thứ tự:** `ORDER BY id` trả hàng theo ID; với pagination cần kiểm tra khi có nhiều bản ghi cùng sort key.
5. **Mapping null/type:** Cho một cột nullable và xác nhận không đánh đồng NULL với `0`/`false`.
6. **JOIN/duplicate:** Nếu query join một-nhiều, kiểm tra API có trả đúng số parent hay tạo phần tử trùng như SQL result.
7. **Error path:** Cố ý dùng bảng/cột không tồn tại trong test riêng và xác minh lỗi không bị chuyển thành list rỗng.
8. **Giới hạn kết quả:** Query một tập đủ lớn để kiểm tra paging, memory, fetch/cursor trong driver thực.

Trong Spring Boot, `@JdbcTest` hỗ trợ JDBC test slice; với SQL dialect, locking, collation đặc thù, chỉ dùng H2 là chưa đủ. Hãy kiểm thử trên database tương thích production (có thể qua Testcontainers). Mock `JdbcTemplate` giúp test quyết định nghiệp vụ của service nhưng không chứng minh query SQL và mapper thực sự hoạt động.

### Bài tập thực hành

- **Bài 1:** Trong ví dụ mục 4, thêm `findByTitle(String title)` trả `List<Book>`, sử dụng `WHERE title = ?`. Kiểm tra một tiêu đề có dữ liệu và một tiêu đề không tồn tại.
- **Bài 2:** Đổi mapper sang record `BookSummary(long id, String title)` và SQL chỉ SELECT hai cột. So sánh dữ liệu truy xuất với việc dùng `SELECT *`.
- **Bài 3:** Thêm một trường `description` nullable và mapping đúng `String`; tiếp đó thử `pages` nullable với `getInt()/wasNull()`.
- **Bài 4:** Bổ sung query `LIMIT ? OFFSET ?` và kiểm tra hai trang liên tiếp với `ORDER BY id`; viết trường hợp page size không hợp lệ.
- **Bài 5:** Giả sử sách có nhiều tác giả, viết SQL JOIN khiến cùng book xuất hiện hai lần. Chọn `EXISTS`/`DISTINCT` hoặc `ResultSetExtractor` theo đúng yêu cầu API, giải thích vì sao.
- **Bài 6:** Viết test mô tả khác biệt “`query` không có hàng -> `[]`” và “`queryForObject` không có hàng -> exception”.

## 15. Checklist trước khi dùng query() trong production

- [ ] SQL chỉ SELECT những cột DTO cần; mapper đọc đúng tên cột/alias và kiểu dữ liệu.
- [ ] Đặt `ORDER BY` nếu kết quả cần thứ tự ổn định, đặc biệt khi phân trang.
- [ ] Dùng `?`/named binding cho giá trị; allowlist cho identifier/order động.
- [ ] `RowMapper` chỉ map hàng hiện tại, không tự gọi `rs.next()`, không dùng state request shared.
- [ ] Chọn `List<T>` cho kết quả 0..N hàng; nếu không có hàng, xử lý list rỗng theo contract.
- [ ] Chỉ dùng `queryForObject` khi mong đúng một hàng; `queryForList` khi chỉ cần scalar/maps.
- [ ] Xử lý nullable numeric/boolean đúng bằng wrapper và `rs.wasNull()`.
- [ ] Kiểm tra JOIN có nhân bản hàng, dùng projection/mapping phù hợp.
- [ ] Giới hạn page size và số hàng tải về; không mặc định đọc hàng triệu bản ghi vào list.
- [ ] Khi dùng `queryForStream`, luôn đóng stream; khi dùng callback, tránh lưu toàn bộ dữ liệu vô ý.
- [ ] Inject `JdbcTemplate` được cấu hình sẵn; dùng `DataSource`/transaction manager phù hợp.
- [ ] Không nuốt lỗi SQL rồi giả làm list rỗng; ghi nhận và xử lý `DataAccessException` hợp lý.
- [ ] Test kết quả, zero rows, SQL lỗi và dialect thực tế bằng integration test.

**Ghi nhớ:** `JdbcTemplate.query(sql, rowMapper, args...)` có nghĩa là **“chạy SQL trả nhiều hàng, biến mỗi hàng thành một đối tượng và trả danh sách”**. `RowMapper` là cầu nối từ một hàng `ResultSet` sang một `T`; `JdbcTemplate` lo vòng lặp và tài nguyên JDBC. Kết quả rỗng, sorting, binding an toàn và giới hạn số hàng là những phần quan trọng của contract repository.

## Tài liệu chính thức

- [Spring Framework — JdbcTemplate và cách query dữ liệu](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html)
- [Spring Framework — JDBC Data Access](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html)
- [Spring Framework — JdbcTemplate API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html)
- [Spring Framework — RowMapper API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/RowMapper.html)
- [Spring Framework — BeanPropertyRowMapper API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/BeanPropertyRowMapper.html)
- [Spring Framework — JDBC Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
- [Spring Boot — Working with SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html)

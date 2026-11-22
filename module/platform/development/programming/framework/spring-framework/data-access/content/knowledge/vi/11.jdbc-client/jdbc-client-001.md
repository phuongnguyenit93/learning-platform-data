# JdbcClient cung cấp API liền mạch từ Spring Framework 6.1

> **Chủ đề:** Spring Framework – data-access  
> **Nhóm kiến thức:** JdbcClient  
> **Phiên bản trọng tâm:** Spring Framework **6.1** trở lên, với ví dụ cụ thể trên Spring **6.1.14** và Java **17+**

## 1. Vấn đề mà JdbcClient giải quyết

Spring JDBC vốn đã có `JdbcTemplate` để thao tác SQL bằng tham số vị trí `?`, cùng `NamedParameterJdbcTemplate` để thao tác SQL bằng tham số có tên `:id`, `:status`. Hai API này ổn định và hữu ích, nhưng khi code truy vấn có nhiều tham số và nhiều lựa chọn ánh xạ, lời gọi có thể trở nên dài và phải chọn overload ngay từ đầu.

**Từ Spring Framework 6.1**, `org.springframework.jdbc.core.simple.JdbcClient` cung cấp một facade có **fluent API** thống nhất cho các thao tác JDBC query/update phổ biến. Lập trình viên viết chuỗi hành động theo trình tự tự nhiên:

~~~text
client
  .sql("SELECT ... WHERE id = :id")
  .param("id", wantedId)
  .query(Book.class)
  .optional()
~~~

Luồng đọc hiểu được ngay: tạo câu SQL → bind tham số → chọn cách ánh xạ → chọn hình dạng kết quả. Với ghi dữ liệu:

~~~text
client
  .sql("UPDATE ... SET ... WHERE ...")
  .param(...)
  .update()
~~~

**Điểm quan trọng:** `JdbcClient` **không phải một JDBC driver, ORM hay JPA repository mới**. Nó tổ chức lại cách gọi những chức năng JDBC cơ bản và **ủy quyền cho `JdbcTemplate` cùng `NamedParameterJdbcTemplate`** ở phía dưới. Vì vậy ứng dụng vẫn phải có `DataSource` và JDBC driver, vẫn cần viết SQL, quan tâm SQL injection, mapping, transaction, connection pool và exception handling.

Mục tiêu sau bài này: hiểu vị trí `JdbcClient` trong Spring JDBC, dùng cú pháp 6.1 chính xác, chọn positional/named parameters, ánh xạ scalar/map/record bằng nhiều cách, xử lý 0/1/n hàng, ghi dữ liệu, tích hợp bean và transaction, biết giới hạn của facade và chạy được demo Java 17.

## 2. JdbcClient ở đâu trong kiến trúc Spring Data Access?

~~~text
Application / Service
         |
         v
Repository tự viết SQL
         |
         v
JdbcClient  (fluent facade, từ Spring Framework 6.1)
         |
         +--> JdbcTemplate                (positional params)
         |
         +--> NamedParameterJdbcTemplate  (named params)
                  |
                  v
          DataSource / JDBC Connection
                  |
                  v
             JDBC Driver
                  |
                  v
               Database
~~~

`JdbcClient` nằm trong artifact `spring-jdbc`, package:

~~~java
import org.springframework.jdbc.core.simple.JdbcClient;
~~~

Với API cơ bản:

~~~java
JdbcClient client = JdbcClient.create(dataSource);
~~~

hoặc tái sử dụng một template đã cấu hình:

~~~java
JdbcTemplate template = new JdbcTemplate(dataSource);
JdbcClient client = JdbcClient.create(template);
~~~

Ngoài `DataSource` và `JdbcOperations`, Spring 6.1 còn có factory `create(NamedParameterJdbcOperations)`. Các factory này không tự thực hiện SQL; chúng tạo client để thực thi câu lệnh khi gọi terminal operation như `.update()`, `.single()`, `.list()`.

### 2.1. Facade không thay thế templates

`JdbcClient` phù hợp cho **query và update thông thường**. Với Spring **6.1**, các thao tác phức tạp như batch update hay stored procedure vẫn thường dùng `JdbcTemplate`, `NamedParameterJdbcTemplate`, `SimpleJdbcInsert` hoặc `SimpleJdbcCall`. Không dùng phương thức `batch()` nếu mục tiêu tương thích chính xác Spring 6.1: giao diện 6.1 không công bố fluent batch API đó; tính năng của các phiên bản mới hơn không nên được suy ngược vào 6.1.

Facade cũng không biến SQL thành query ngôn ngữ đối tượng, không tự tạo bảng và không tự quản lý entity/persistence context như JPA.

### 2.2. Tương thích với Spring Framework 6.1

`JdbcClient` được công bố với `@since 6.1`; không thể giả định một project Spring Framework 6.0 tự có cùng class/API. Cần kiểm tra **version `spring-jdbc` thực tế trên runtime classpath**, không chỉ nhìn phiên bản Spring Boot được ghi trong tài liệu. Nếu dùng Spring Boot, cần dùng dòng Boot quản lý một Spring Framework có `JdbcClient` (ví dụ Boot 3.2 tích hợp Spring Framework 6.1); khi tự ghi dependency, hãy bảo đảm các module Spring dùng phiên bản nhất quán.

## 3. Fluent API: hiểu từng bước trong một chuỗi gọi

Một câu SELECT theo tham số có tên:

~~~java
String title = client
        .sql("SELECT title FROM book WHERE id = :id")
        .param("id", 10L)
        .query(String.class)
        .single();
~~~

Đây là **đoạn minh họa** nằm trong method có `client`, bảng `book` và bản ghi ID 10. Không phải class độc lập.

Các phần:

1. `sql(String)` bắt đầu một `JdbcClient.StatementSpec` chứa câu SQL.
2. `param("id", 10L)` bind giá trị theo tên `:id`. Có thể thêm nhiều lần `.param(name, value)`.
3. `query(String.class)` yêu cầu mapper giá trị từ **một cột** sang `String`.
4. `single()` thực thi truy vấn và yêu cầu **đúng một kết quả**. Nếu không có hàng hoặc có nhiều hơn một hàng, kết quả không đạt cardinality yêu cầu và Spring ném ngoại lệ tương ứng.

Đối với UPDATE:

~~~java
int affected = client
        .sql("UPDATE book SET title = :title WHERE id = :id")
        .param("title", "Spring JDBC")
        .param("id", 10L)
        .update();
~~~

`update()` là terminal operation để chạy INSERT/UPDATE/DELETE, trả **số hàng bị ảnh hưởng** dưới dạng `int`. Một lệnh UPDATE không khớp hàng nào thông thường trả 0; đó không tự động là exception “not found”. Service cần kiểm tra `affected` nếu nghiệp vụ yêu cầu đúng một hàng được sửa.

### 3.1. `sql()` không phải tự thân là thực thi

Code chỉ xây `StatementSpec`:

~~~java
JdbcClient.StatementSpec spec =
        client.sql("SELECT title FROM book WHERE id = :id")
              .param("id", 10L);
~~~

chưa yêu cầu lấy kết quả. Truy vấn được thực thi khi sử dụng một terminal method thích hợp như `query(...).single()`, `query(...).list()` hoặc `update()`. Tránh lưu và chia sẻ một `StatementSpec` có tham số thay đổi giữa nhiều thread; hãy xây chuỗi mới mỗi lần gọi, còn `JdbcClient` được cấu hình trên `DataSource` có thể được sử dụng như dependency của repository.

### 3.2. Khả năng đọc code

Cách cũ của JDBC với named parameters:

~~~java
Integer count = namedParameterJdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM book WHERE pages >= :minPages",
        Map.of("minPages", 200),
        Integer.class);
~~~

Cách fluent:

~~~java
Integer count = client
        .sql("SELECT COUNT(*) FROM book WHERE pages >= :minPages")
        .param("minPages", 200)
        .query(Integer.class)
        .single();
~~~

Cả hai đều có thể đúng. `JdbcClient` khiến cách chỉ định tham số, mapper và cardinality **xuất hiện trên những bước riêng**, chứ không phải tự động nhanh hơn hoặc thay đổi SQL semantics.

## 4. Positional và named parameters trong cùng một facade

`JdbcClient` hỗ trợ **hai phong cách** cho từng SQL statement.

### 4.1. Positional `?`

~~~java
List<String> titles = client
        .sql("SELECT title FROM book WHERE pages >= ? AND pages <= ? ORDER BY id")
        .param(150)
        .param(350)
        .query(String.class)
        .list();
~~~

Hai lời gọi `param(value)` được đăng ký theo thứ tự xuất hiện của hai dấu `?`, tương ứng placeholder thứ nhất và thứ hai.

Khi đã có sẵn danh sách giá trị, có `params(Object... values)` hoặc `params(List<?> values)`:

~~~java
List<String> titles = client
        .sql("SELECT title FROM book WHERE pages BETWEEN ? AND ? ORDER BY id")
        .params(150, 350)
        .query(String.class)
        .list();
~~~

Hai mẫu này dùng cùng ý nghĩa SQL cho khoảng đóng khi cột không null. `params` dành cho **các giá trị đã được kiểm soát**; không ghép chuỗi SQL từ input người dùng.

### 4.2. Đặt chỉ số JDBC tường minh

Trong Spring 6.1 có overload:

~~~java
client.sql("SELECT title FROM book WHERE id = ?")
      .param(1, 10L)
      .query(String.class)
      .single();
~~~

`param(int jdbcIndex, Object value)` yêu cầu chỉ số JDBC bắt đầu từ **1**, không phải chỉ số mảng Java bắt đầu từ 0. Nó có thể hữu ích khi code xây binding có chủ đích, nhưng với ít tham số thì `.param(value)` thường dễ đọc hơn.

### 4.3. Named `:name`

~~~java
List<String> titles = client
        .sql("SELECT title FROM book " +
             "WHERE pages >= :minPages AND pages <= :maxPages ORDER BY id")
        .param("minPages", 150)
        .param("maxPages", 350)
        .query(String.class)
        .list();
~~~

Tên `minPages`/`maxPages` phải khớp placeholder trong SQL. Một tên xuất hiện nhiều lần trong SQL có thể lấy cùng giá trị theo cách xử lý named parameters của Spring.

Named parameters dễ bảo trì khi có nhiều điều kiện, vì không phụ thuộc người đọc đếm dấu `?`. Với 1–2 tham số đơn giản, positional cũng rất phù hợp.

### 4.4. `params(Map)` và `paramSource(...)`

Với dữ liệu đã tổ chức thành map:

~~~java
Map<String, Object> parameters = Map.of(
        "minPages", 150,
        "maxPages", 350);

List<String> titles = client
        .sql("SELECT title FROM book " +
             "WHERE pages BETWEEN :minPages AND :maxPages ORDER BY id")
        .params(parameters)
        .query(String.class)
        .list();
~~~

Nếu tham số đến từ record/bean có property trùng tên, Spring 6.1 hỗ trợ `paramSource(Object)`; và `paramSource(SqlParameterSource)` cho nguồn chuyên dụng:

~~~java
record Filter(int minPages, int maxPages) {}

Filter filter = new Filter(150, 350);

List<String> titles = client
        .sql("SELECT title FROM book " +
             "WHERE pages BETWEEN :minPages AND :maxPages ORDER BY id")
        .paramSource(filter)
        .query(String.class)
        .list();
~~~

Đây là snippet trong method; định nghĩa `Filter` đặt được ở nơi hợp lệ của Java 17. Với property có thể null hoặc cần loại SQL tường minh, dùng `MapSqlParameterSource` để mang metadata kiểu.

**Không trộn positional và named binding trong cùng một SQL statement** như cách hy vọng Spring tự kết hợp một `?` với `:id`. Hãy chọn một phong cách cho từng statement; nội bộ Spring chọn đường delegate tương ứng, và pha trộn có thể gây `InvalidDataAccessApiUsageException`.

## 5. Lấy kết quả: `query(mappedClass)`

Một API tiện lợi của JdbcClient 6.1 là:

~~~java
List<Book> books = client
        .sql("SELECT id, title, pages FROM book ORDER BY id")
        .query(Book.class)
        .list();
~~~

Nếu `Book` là Java record có components `id`, `title`, `pages` tương ứng column labels và kiểu chuyển đổi tương thích, Spring có thể ánh xạ một hàng sang record.

~~~java
public record Book(long id, String title, int pages) {}
~~~

Đối với `query(Class<T>)`, Spring 6.1 chọn mapper thích hợp giữa kiểu scalar một cột và class nhiều thuộc tính (JavaBean, record hoặc holder). **Đừng nhầm với** `JdbcTemplate.queryForList(sql, Book.class)`: overload cổ điển đó dành cho scalar một cột, không tự xây `Book` nhiều cột.

### 5.1. Scalar value

~~~java
long count = client
        .sql("SELECT COUNT(*) FROM book")
        .query(Long.class)
        .single();
~~~

`COUNT(*)` là một cột, một hàng. `Long.class` diễn tả giá trị kết quả mong muốn; nếu driver/SQL type khác, cần chọn type tương thích. Dùng SQL alias/mapper rõ ràng khi ánh xạ dữ liệu nhiều trường.

### 5.2. Record/DTO nhiều cột

~~~java
record BookSummary(long id, String title) {}

List<BookSummary> books = client
        .sql("SELECT id, title FROM book ORDER BY id")
        .query(BookSummary.class)
        .list();
~~~

Tên cột và kiểu phải khớp cách mapper tìm field, property hoặc constructor component. `query(BookSummary.class)` không tự xác minh invariant nghiệp vụ, không tự giải JOIN nhiều bảng thành object graph như ORM.

Các trường hợp mapping có conversion phức tạp, cột trùng tên sau JOIN, enum/date-time riêng của driver hoặc nhiều bảng gộp thành một object nên ưu tiên `RowMapper<T>` tự viết để tường minh.

## 6. Lấy kết quả: `query(RowMapper<T>)`

Khi muốn kiểm soát tuyệt đối cách đọc `ResultSet`:

~~~java
RowMapper<Book> mapper = (rs, rowNum) -> new Book(
        rs.getLong("id"),
        rs.getString("title"),
        rs.getInt("pages")
);

List<Book> books = client
        .sql("SELECT id, title, pages FROM book ORDER BY id")
        .query(mapper)
        .list();
~~~

*Đây là ví dụ Java nằm trong method có `client` và class/record `Book`.*

`RowMapper` phù hợp khi:

- SQL dùng alias đặc biệt hoặc tên cột không trùng component.
- Cần chuyển SQL NULL, enum, ngày giờ, JSON hay cấu trúc nested có chủ đích.
- Muốn giữ contract domain rõ, không phụ thuộc implicit property matching.
- Có cùng quy tắc mapping được tái sử dụng qua nhiều truy vấn.

`JdbcClient` không buộc phải chọn giữa “tự động map” và “tự viết mapper”. Cả hai xuất hiện qua overload `query(Class<T>)` và `query(RowMapper<T>)`.

### 6.1. `RowCallbackHandler` và `ResultSetExtractor`

Spring 6.1 còn có:

~~~java
client.sql("SELECT id, title FROM book ORDER BY id")
      .query(rs -> {
          // RowCallbackHandler: xử lý từng row trong ResultSet.
      });
~~~

Đây chỉ là đoạn **minh họa** một overload xử lý từng hàng; để tránh mơ hồ overload lambda, trong code thực tế khai báo callback có kiểu `RowCallbackHandler` hoặc dùng mapper cụ thể.

Với logic cần tổng hợp toàn bộ `ResultSet` theo cách không phải mỗi hàng = một object, dùng overload `query(ResultSetExtractor<T>)`. Những trường hợp này giúp giải quyết việc đọc dữ liệu phức tạp mà không phải rời khỏi facade, nhưng `JdbcTemplate` vẫn hữu ích khi cần kiểm soát JDBC thấp tầng nhiều hơn.

## 7. Chọn hình dạng kết quả: `list()`, `single()`, `optional()`

Ba terminal method thường gặp của `MappedQuerySpec<T>`:

| API | Kết quả | Không có hàng | Nhiều hàng |
| --- | --- | --- | --- |
| `.query(Book.class).list()` | `List<Book>` | List rỗng | List nhiều phần tử |
| `.query(Book.class).single()` | `Book` | `EmptyResultDataAccessException` | `IncorrectResultSizeDataAccessException` |
| `.query(Book.class).optional()` | `Optional<Book>` | `Optional.empty()` | `IncorrectResultSizeDataAccessException` |
| `.query(Book.class).set()` | `Set<Book>` | Set rỗng | Các phần tử duy nhất theo `equals/hashCode`, giữ thứ tự theo mapper/list |
| `.query(Book.class).stream()` | `Stream<Book>` cần đóng | Stream rỗng | Stream kết quả, không nạp trước như `list()` |

Ví dụ một ID có thể không tồn tại:

~~~java
Optional<Book> book = client
        .sql("SELECT id, title, pages FROM book WHERE id = :id")
        .param("id", requestedId)
        .query(Book.class)
        .optional();
~~~

Lúc này `Optional.empty()` là kết quả hợp lệ cho “không tìm thấy”. Nếu SQL trả nhiều hàng, `optional()` **không tự chọn hàng đầu**. Đó vẫn là vi phạm kỳ vọng tối đa một hàng.

Ngược lại, nếu ID bắt buộc phải có và việc thiếu dữ liệu là lỗi nghiệp vụ, `single()` làm yêu cầu đó rõ ràng, nhưng service nên chuyển `DataAccessException` thành lỗi nghiệp vụ thích hợp ở ranh giới ứng dụng nếu cần.

### 7.1. Stream cần đóng

~~~java
try (Stream<Book> stream = client
        .sql("SELECT id, title, pages FROM book ORDER BY id")
        .query(Book.class)
        .stream()) {
    stream.forEach(System.out::println);
}
~~~

*Đây là snippet có import `java.util.stream.Stream`.* Kết quả `stream()` có thể giữ JDBC resources cho đến khi stream được đóng. **Không** trả stream sống ra ngoài transaction/context đã kết thúc, không lưu trong field để xử lý ở thread khác. Dùng `list()` khi số hàng nhỏ và muốn một danh sách tách khỏi JDBC resources.

### 7.2. `set()` không phải SQL DISTINCT

`set()` thu danh sách thành `Set` giữ thứ tự encounter và loại trùng theo `equals/hashCode` của kiểu Java. Nó không thay thế ý định và chi phí của `SELECT DISTINCT` trong database. Với kết quả lớn, chọn phép lọc/phân nhóm ở nơi phù hợp.

## 8. Query không cần mapped class: `query()`

Không phải lúc nào kết quả cũng cần `Book`. Spring Framework 6.1 cung cấp `ResultQuerySpec` từ `query()` (không argument):

~~~java
List<Map<String, Object>> rows = client
        .sql("SELECT id, title, pages FROM book ORDER BY id")
        .query()
        .listOfRows();

Map<String, Object> row = client
        .sql("SELECT id, title FROM book WHERE id = ?")
        .param(1L)
        .query()
        .singleRow();
~~~

`listOfRows()` hữu ích cho bảng báo cáo với projection linh hoạt; mỗi hàng là map từ column label sang giá trị. `singleRow()` yêu cầu một hàng. Một map không có type-safety domain: code phải xử lý key, alias, SQL NULL, kiểu `Object` và khả năng trùng column label khi JOIN.

Các phương thức khác của `ResultQuerySpec` trong Spring **6.1**:

~~~java
List<Object> ids = client
        .sql("SELECT id FROM book ORDER BY id")
        .query()
        .singleColumn();

Object id = client
        .sql("SELECT id FROM book WHERE id = ?")
        .param(1L)
        .query()
        .singleValue();

SqlRowSet rowSet = client
        .sql("SELECT id, title FROM book ORDER BY id")
        .query()
        .rowSet();
~~~

*Đây là snippets minh họa; `SqlRowSet` có import `org.springframework.jdbc.support.rowset.SqlRowSet`.*

`singleColumn()` trả danh sách giá trị của **một cột** với phần tử kiểu `Object`, còn `singleValue()` yêu cầu kết quả đơn một ô. Với dữ liệu scalar bạn biết type, dạng `query(Long.class).single()` hoặc `query(String.class).list()` thường dễ bảo trì hơn.

**Quan trọng về phiên bản:** API `ResultQuerySpec.optionalValue()` xuất hiện ở những phiên bản sau 6.1, không nên dùng khi bài đang nhắm Spring 6.1. `query(Book.class).optional()` là phương thức phù hợp trong 6.1 để diễn đạt tùy chọn với mapper.

### 8.1. Cardinality không do SQL tự kiểm tra giúp bạn

Nếu chỉ muốn một bản ghi duy nhất, bảo đảm `WHERE` theo khóa/ràng buộc phù hợp. Nếu SQL trả hai hàng mà bạn gọi `singleRow()` hay `single()`, framework không âm thầm chọn hàng đầu. Cần sửa yêu cầu truy vấn chứ không tự động thêm `LIMIT 1` để che lỗi uniqueness.

### 8.2. Alias và mapping

~~~sql
SELECT b.id AS book_id, b.title AS book_title
FROM book b
~~~

Nếu kết quả map cần hai key `book_id` và `book_title`, dùng alias tường minh. Còn nếu dùng record `Book(long id, String title, ...)`, projection phải cung cấp các tên/kiểu phù hợp mapper. Sau JOIN, không chọn hai cột đều tên `id` mà mong map biểu diễn cả hai không mơ hồ.

## 9. Ghi dữ liệu: `update()` và generated keys

Dùng fluent update cho `INSERT`, `UPDATE` hoặc `DELETE`:

~~~java
int inserted = client
        .sql("INSERT INTO book(id, title, pages) VALUES (?, ?, ?)")
        .params(1L, "Clean Java", 320)
        .update();

int changed = client
        .sql("UPDATE book SET pages = :pages WHERE id = :id")
        .param("pages", 350)
        .param("id", 1L)
        .update();

int deleted = client
        .sql("DELETE FROM book WHERE id = ?")
        .param(1L)
        .update();
~~~

Trên bảng có `id` là primary key, INSERT trùng ID sẽ ném database exception được Spring dịch thành `DataAccessException` thích hợp. Giá trị trả về `int` biểu thị số hàng bị ảnh hưởng; nó không phải ID được generate.

### 9.1. Generated key trong Spring 6.1

`JdbcClient.StatementSpec` có overload `update(KeyHolder)` và `update(KeyHolder, String... keyColumnNames)`. Nếu schema có identity/generated column và driver hỗ trợ lấy khóa phát sinh:

~~~java
KeyHolder holder = new GeneratedKeyHolder();

int inserted = client
        .sql("INSERT INTO book(title, pages) VALUES (:title, :pages)")
        .param("title", "New Book")
        .param("pages", 240)
        .update(holder, "id");

Number key = holder.getKey();
~~~

**Đây là snippet minh họa chỉ khi bảng `book.id` được khai báo auto-generated**, khác với schema demo ở mục 11 nơi ID được nhập tường minh. `KeyHolder.getKey()` có thể không cung cấp một key nếu driver/DB không hỗ trợ hoặc metadata không như dự kiến; không khẳng định mọi database đều trả cùng kiểu `Number`. Hãy dùng SQL DDL và driver thực tế để test phần này.

### 9.2. Nhiều thao tác nghiệp vụ cần transaction

`update()` thực hiện một statement. Nó không tự đóng gói những statement khác thành một giao dịch nguyên tử cho cả use case. `@Transactional` hoặc `TransactionTemplate` cùng transaction manager tương thích vẫn quyết định begin/commit/rollback.

## 10. Tham số null, SQL type và an toàn SQL

`JdbcClient.StatementSpec` trong Spring 6.1 hỗ trợ overload có SQL type:

~~~java
client.sql("UPDATE book SET note = ? WHERE id = ?")
      .param(1, null, Types.VARCHAR)
      .param(2, 1L, Types.BIGINT)
      .update();
~~~

Và với named parameters:

~~~java
client.sql("UPDATE book SET note = :note WHERE id = :id")
      .param("note", null, Types.VARCHAR)
      .param("id", 1L)
      .update();
~~~

Hai đoạn này chỉ là **minh họa** với bảng có cột `note`, không dùng với schema demo `book(id, title, pages)` tại mục 11. Có thể dùng `paramSource(MapSqlParameterSource)` khi muốn truyền nhiều tham số kèm SQL type:

~~~java
MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("note", null, Types.VARCHAR)
        .addValue("id", 1L, Types.BIGINT);

client.sql("UPDATE book SET note = :note WHERE id = :id")
      .paramSource(params)
      .update();
~~~

*Trong trường hợp này `MapSqlParameterSource` chứa thông tin metadata, không chỉ map giá trị.* `Map.of("note", null)` sẽ ném `NullPointerException` ngay trong Java vì `Map.of` không chấp nhận null.

Tại sao cần SQL type cho null? Vì Java `null` không mang class runtime; một số JDBC driver/SQL expression không đủ thông tin để đoán loại SQL của parameter. Ghi rõ `Types.VARCHAR`, `Types.DATE`... theo schema giúp việc bind tường minh hơn.

### 10.1. Không ghép giá trị người dùng vào SQL

Đúng:

~~~java
client.sql("SELECT id, title, pages FROM book WHERE title = :title")
      .param("title", suppliedTitle)
      .query(Book.class)
      .list();
~~~

Sai:

~~~java
String unsafeSql =
        "SELECT id, title, pages FROM book WHERE title = '" +
        suppliedTitle + "'";
~~~

Tham số bind nhằm thay **giá trị**, không phải tên bảng/cột hoặc hướng `ORDER BY`. Nếu người dùng được chọn cột sắp xếp, phải đối chiếu whitelist các identifier được phép thay vì ghép chuỗi bất kỳ.

## 11. Demo đầy đủ chạy được: Java 17, Spring JDBC 6.1.14 và H2

Chương trình sử dụng **Maven 3.9+**, **JDK 17+**, `spring-jdbc:6.1.14` và `h2:2.2.224`. Đây là ứng dụng Java console **không cần Spring Boot**. Nó tạo `DataSource`, `JdbcTemplate` và `JdbcClient`, rồi minh họa cả positional/named parameters, mapping Java record, `list()`, `single()`, `optional()`, `update()` và số hàng ảnh hưởng.

### 11.1. Cấu trúc dự án

~~~text
jdbc-client-demo/
├── pom.xml
└── src/main/java/demo/
    └── JdbcClientDemo.java
~~~

### 11.2. Tệp `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>jdbc-client-demo</artifactId>
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

### 11.3. Tệp `src/main/java/demo/JdbcClientDemo.java`

~~~java
package demo;

import java.util.List;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class JdbcClientDemo {

    public record Book(long id, String title, int pages) {}

    public static void main(String[] args) {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:jdbc_client_demo;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");

        JdbcTemplate template = new JdbcTemplate(ds);
        JdbcClient client = JdbcClient.create(template);

        template.execute("CREATE TABLE book (" +
                "id BIGINT PRIMARY KEY, " +
                "title VARCHAR(100) NOT NULL, " +
                "pages INTEGER NOT NULL)");

        int a = client
                .sql("INSERT INTO book(id, title, pages) VALUES (?, ?, ?)")
                .params(1L, "Clean Java", 320)
                .update();

        int b = client
                .sql("INSERT INTO book(id, title, pages) " +
                     "VALUES (:id, :title, :pages)")
                .param("id", 2L)
                .param("title", "Spring JDBC")
                .param("pages", 200)
                .update();

        int c = client
                .sql("INSERT INTO book(id, title, pages) " +
                     "VALUES (:id, :title, :pages)")
                .param("id", 3L)
                .param("title", "Data Access")
                .param("pages", 260)
                .update();

        System.out.println("Inserted rows: " + (a + b + c));

        List<Book> initial = client
                .sql("SELECT id, title, pages FROM book ORDER BY id")
                .query(Book.class)
                .list();
        System.out.println("Books: " + initial.size());
        System.out.println("First title: " + initial.get(0).title());

        long count = client.sql("SELECT COUNT(*) FROM book")
                .query(Long.class)
                .single();
        System.out.println("Count before update: " + count);

        Optional<Book> missing = client
                .sql("SELECT id, title, pages FROM book WHERE id = :id")
                .param("id", 999L)
                .query(Book.class)
                .optional();
        System.out.println("Missing present: " + missing.isPresent());

        int changed = client
                .sql("UPDATE book SET pages = :pages WHERE id = :id")
                .param("pages", 350)
                .param("id", 1L)
                .update();
        System.out.println("Updated rows: " + changed);

        int pages = client
                .sql("SELECT pages FROM book WHERE id = ?")
                .param(1L)
                .query(Integer.class)
                .single();
        System.out.println("Pages for id=1: " + pages);

        int removed = client
                .sql("DELETE FROM book WHERE id = ?")
                .param(3L)
                .update();
        System.out.println("Deleted rows: " + removed);

        List<Book> remaining = client
                .sql("SELECT id, title, pages FROM book ORDER BY id")
                .query(Book.class)
                .list();
        System.out.println("Remaining ids: " +
                remaining.stream().map(Book::id).toList());

        long remainingCount = client.sql("SELECT COUNT(*) FROM book")
                .query(Long.class)
                .single();
        System.out.println("Count after delete: " + remainingCount);
    }
}
~~~

Chạy trong thư mục `jdbc-client-demo`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.JdbcClientDemo
~~~

**Các dòng do chương trình tự in** (không kể log Maven nếu có):

~~~text
Inserted rows: 3
Books: 3
First title: Clean Java
Count before update: 3
Missing present: false
Updated rows: 1
Pages for id=1: 350
Deleted rows: 1
Remaining ids: [1, 2]
Count after delete: 2
~~~

### 11.4. Giải thích vì sao output đúng

1. Chương trình tạo bảng `book` gồm `id BIGINT`, `title VARCHAR` và `pages INTEGER`. `DriverManagerDataSource` tạo các kết nối mới; `DB_CLOSE_DELAY=-1` giúp H2 in-memory còn tồn tại giữa những lần sử dụng kết nối trong cùng JVM.
2. Ba câu `INSERT` đều ghi một hàng. Câu đầu dùng `params(...)` positional; hai câu sau dùng `param(name, value)`. Do ID là unique primary key, ba hàng phân biệt được theo ID.
3. `SELECT ... ORDER BY id` trả ba dòng theo ID tăng dần. `query(Book.class)` ánh xạ các cột `id/title/pages` vào record components tương ứng. `list()` trả danh sách nên phần tử đầu là cuốn `Clean Java`.
4. `SELECT COUNT(*)` trả một số, qua `query(Long.class).single()` nhận 3.
5. Truy vấn ID 999 không có hàng; `optional()` trả `Optional.empty()` chứ không báo lỗi thiếu hàng.
6. Câu UPDATE cho ID 1 thay pages từ 320 thành 350; `update()` trả số hàng bị tác động là 1. SELECT scalar tương ứng in 350.
7. Câu DELETE cho ID 3 tác động đúng một hàng; `update()` trả 1. Kết quả SELECT cuối còn ID 1 và ID 2, theo `ORDER BY id` cho danh sách `[1, 2]`.
8. `COUNT(*)` sau khi xóa là 2. Không có transaction nhiều statement ở ví dụ này, vì mục tiêu là kiểm chứng fluent JDBC API; nếu nghiệp vụ yêu cầu atomicity xuyên nhiều thay đổi, cấu hình transaction riêng.

### 11.5. Những thử nghiệm nên làm trên demo

**Thử nghiệm A — empty result:** thay `.optional()` bằng `.single()` cho ID 999. Kết quả dự kiến là `EmptyResultDataAccessException`, thay vì `Optional.empty()`.

**Thử nghiệm B — duplicate result:** dùng `.single()` với SQL `SELECT id, title, pages FROM book` khi có hai hàng. Kết quả dự kiến là `IncorrectResultSizeDataAccessException`; cần WHERE theo unique key hoặc `list()` nếu nhiều hàng là hợp lệ.

**Thử nghiệm C — kiểm tra named parameter:** đổi tên `:pages` trong SQL nhưng không đổi `.param("pages", 350)`. Lỗi binding chỉ ra tên SQL và tên parameter phải đồng bộ.

**Thử nghiệm D — SQL mapping:** đổi alias `pages` thành `page_count` nhưng vẫn dựa vào automatic mapping của `Book.pages`. Hãy kiểm tra kết quả và dùng alias `AS pages` hoặc `RowMapper` phù hợp, thay vì tin mapper tự hiểu mọi alias.

**Thử nghiệm E — update không tìm thấy:** thay `WHERE id = :id` thành ID 999. `update()` thông thường trả 0; service phải tự coi đó là lỗi nghiệp vụ khi cần.

**Thử nghiệm F — conversion:** đổi SQL thành chỉ `SELECT title FROM book` và dùng `query(Book.class)`. Vì query không chứa đầy đủ components của record, mapping domain không thể coi là hợp lệ; dùng `query(String.class)` cho scalar một cột.

## 12. Sử dụng JdbcClient trong một Spring application

Trong ứng dụng dùng dependency injection, tạo bean từ `DataSource` sẵn có:

~~~java
@Configuration
public class JdbcConfig {
    @Bean
    JdbcClient jdbcClient(DataSource dataSource) {
        return JdbcClient.create(dataSource);
    }
}
~~~

Đây là **snippet cấu hình**, không phải chương trình độc lập. Cần imports `org.springframework.context.annotation.Configuration`, `Bean`, `javax.sql.DataSource` và `JdbcClient`. Nếu hệ sinh thái Boot đang dùng đã cung cấp một bean `JdbcClient` tương thích, không đăng ký trùng vô ý; hãy kiểm tra cấu hình thực tế của dự án.

Một repository dùng constructor injection:

~~~java
@Repository
public class BookRepository {

    private final JdbcClient client;

    public BookRepository(JdbcClient client) {
        this.client = client;
    }

    public Optional<Book> findById(long id) {
        return client.sql(
                "SELECT id, title, pages FROM book WHERE id = :id")
                .param("id", id)
                .query(Book.class)
                .optional();
    }

    public int updatePages(long id, int pages) {
        return client.sql(
                "UPDATE book SET pages = :pages WHERE id = :id")
                .param("pages", pages)
                .param("id", id)
                .update();
    }
}
~~~

Đây là **mã minh họa kiến trúc**; `Book` cần record/class hợp lệ trong ứng dụng. `@Repository` giúp Spring tìm class khi component scanning được cấu hình và thể hiện vai trò tầng dữ liệu. `JdbcClient` không tự biến repository thành bean; nó là dependency mà Spring inject qua constructor.

### 12.1. Transaction vẫn quản lý ở service

~~~java
@Service
public class BookService {
    private final BookRepository books;

    public BookService(BookRepository books) {
        this.books = books;
    }

    @Transactional
    public void revise(long id, int pages) {
        int affected = books.updatePages(id, pages);
        if (affected != 1) {
            throw new IllegalStateException("Book not found or not unique");
        }
        // Các thay đổi JDBC khác trong cùng transaction khi dùng đúng DataSource.
    }
}
~~~

Mã trên chỉ minh họa tổ chức lớp và cần Spring transaction manager phù hợp. `@Transactional` phải thực sự được kích hoạt, thường qua proxy/interceptor; self-invocation có thể bỏ qua proxy. Các hoạt động JDBC trên cùng `DataSource` với manager tương thích có thể tham gia transaction. `JdbcClient` không tự gọi commit/rollback cho một use case gồm nhiều statement.

Không đặt transaction chỉ vì muốn có cú pháp fluent: query list đơn giản có thể không cần một transaction nghiệp vụ dài; bài toán nhất quán sẽ quyết định transaction boundary.

## 13. Tái sử dụng cấu hình JdbcTemplate và DataSource

Nếu dự án đã có `JdbcTemplate` cấu hình `queryTimeout`, `fetchSize`, translator hoặc DataSource chuyên biệt, hãy cân nhắc:

~~~java
JdbcClient client = JdbcClient.create(existingJdbcTemplate);
~~~

Nó dùng `JdbcOperations` delegate đã tồn tại, giúp bảo toàn cấu hình thay vì tạo một template hoàn toàn khác. Tương tự có factory cho `NamedParameterJdbcOperations`.

**Không tự động suy luận** rằng hai `JdbcClient` tự tạo với hai `DataSource` khác nhau sẽ cùng một transaction. Với transaction JDBC địa phương, các lời gọi phải dùng đúng datasource/manager đang quản lý. Đặc biệt trong hệ thống đa database hoặc multi-tenant, xác định tenant, DataSource route và transaction manager thật trước khi dùng.

### So sánh API

| Tác vụ | `JdbcTemplate` / `NamedParameterJdbcTemplate` | `JdbcClient` 6.1 |
| --- | --- | --- |
| Query scalar một hàng | `queryForObject(sql, args, Long.class)` và overload tương ứng | `sql(...).param(...).query(Long.class).single()` |
| Query nhiều row mapped | `query(sql, rowMapper, args)` | `sql(...).param(...).query(rowMapper).list()` |
| Named parameter query | `namedTemplate.query(sql, params, rowMapper)` | `sql(...).param("name", value).query(rowMapper).list()` |
| Query list row map | `queryForList(sql, args)` | `sql(...).query().listOfRows()` |
| Update đơn | `update(sql, args...)` | `sql(...).params(...).update()` |
| Generated key | Các API `KeyHolder` trong templates | `sql(...).param(...).update(keyHolder)` |
| Batch update | Các overload `batchUpdate(...)` | Trong **6.1**, nên dùng templates |
| Stored procedure | `SimpleJdbcCall`, JDBC thấp tầng | Dùng API chuyên biệt/low-level |

Không phải mọi overload có cú pháp giống hệt nhau, nhưng những khả năng này giúp định vị tư duy. Việc đổi `JdbcTemplate` sang `JdbcClient` nên ưu tiên **đọc dễ hơn**, không mặc định tốc độ cao hơn hoặc behavior SQL khác.

## 14. Xử lý exception, không tìm thấy và kết quả sai kích thước

Các tình huống hay gặp:

| Tình huống | Hành vi thường gặp | Phương án |
| --- | --- | --- |
| `list()` query trả 0 hàng | List rỗng | Hợp lý với tìm kiếm/danh sách |
| `optional()` trả 0 hàng | `Optional.empty()` | Hợp lý với lookup có thể thiếu |
| `single()` trả 0 hàng | `EmptyResultDataAccessException` | Kiểm tra cardinality/use case |
| `single()` trả >1 hàng | `IncorrectResultSizeDataAccessException` | Kiểm tra WHERE và unique constraint |
| `optional()` trả >1 hàng | `IncorrectResultSizeDataAccessException` | Không tự lấy hàng đầu |
| `update()` tác động 0 hàng | Số nguyên 0 | Service kiểm tra nếu mong đúng một hàng |
| SQL syntax sai hoặc kết nối hỏng | `DataAccessException` phù hợp | Xem nguyên nhân gốc/SQL/driver |
| INSERT vi phạm unique key | `DataIntegrityViolationException` hoặc loại chuyên biệt, tùy translator | Không “bắt rồi bỏ qua” nếu nghiệp vụ cần rollback |

`JdbcClient` sử dụng hạ tầng Spring JDBC bên dưới, vì vậy những lỗi SQL/driver có thể được chuyển thành `DataAccessException`. Exception được dịch **không** đồng nghĩa transaction tự rollback trong mọi trường hợp: còn phụ thuộc ranh giới giao dịch, chính sách rollback và việc exception có bị catch hay không.

### Đừng catch mọi `DataAccessException` để trả list rỗng

Một lỗi SQL syntax, database offline hay timeout khác với “không có bản ghi”. Với `optional()`, trường hợp 0 hàng được biểu diễn bằng `Optional.empty()` mà không cần biến lỗi hệ thống thành kết quả bình thường.

## 15. Hiệu năng, phân trang và an toàn tài nguyên

### 15.1. Fluent API không tự phân trang

~~~java
List<Book> books = client
        .sql("SELECT id, title, pages FROM book ORDER BY id")
        .query(Book.class)
        .list();
~~~

`list()` vật hóa các phần tử trong bộ nhớ. Nếu bảng có hàng triệu bản ghi, không nên mặc định lấy tất cả. Dùng `WHERE`, `ORDER BY` và pagination thích hợp cho dialect; dùng projection chỉ lấy cột cần thiết.

### 15.2. Query stream và connection lifecycle

`stream()` hỗ trợ xử lý lazy, nhưng cần đóng stream để giải phóng JDBC resources. Không dùng như một lời hứa rằng mọi driver đều tải dữ liệu một dòng/lần; fetch size, transaction, cursor và driver ảnh hưởng memory/network behavior.

### 15.3. Không chia sẻ state giữa request qua StatementSpec

Repository singleton có thể giữ một field `final JdbcClient`. Nhưng `StatementSpec` chứa trạng thái SQL/parameters cho **một câu lệnh**. Hãy tạo lại spec theo mỗi method invocation. Không lưu một spec mutable trong singleton và thay param qua nhiều thread.

### 15.4. Parameter binding và SQL injection

`.param(value)` / `.param(name, value)` bind **giá trị**, tránh nối user input vào SQL string. Nhưng tên bảng/cột, ORDER BY field, hướng sort không thể biến thành một bound value tùy ý. Whitelist identifier và dùng những nhánh SQL được kiểm soát.

### 15.5. Không coi JdbcClient là ORM

Nếu cần dirty checking, entity relationship management, lazy loading hoặc JPQL, cần công nghệ ORM/JPA tương ứng. `JdbcClient` giữ lợi thế SQL tường minh, mapping linh hoạt và kiểm soát trực tiếp query; nó không tự tạo `@Entity`, session hoặc migration.

## 16. Những sai lầm thường gặp khi học JdbcClient 6.1

**Sai lầm 1 — “JdbcClient ra đời thay thế hoàn toàn JdbcTemplate”.** Không. `JdbcClient` là facade ủy quyền các query/update phổ biến; templates vẫn có vai trò cho batch/SQL nâng cao.

**Sai lầm 2 — “JdbcClient hỗ trợ mọi API mới nhất dù đang dùng 6.1”.** Không. Kiểm tra Javadoc 6.1. Ví dụ các fluent batch API được bổ sung sau đó không được coi là API cơ bản của 6.1.

**Sai lầm 3 — “Gọi `sql()` đã chạy query”.** Không. Phải gọi terminal method thích hợp.

**Sai lầm 4 — “Có thể trộn `?` và `:name` trong cùng statement tùy thích”.** Không nên; chọn một kiểu binding thống nhất cho mỗi SQL.

**Sai lầm 5 — “`optional()` lấy hàng đầu dù trả nhiều hàng”.** Không. Nó chỉ chấp nhận tối đa một kết quả.

**Sai lầm 6 — “`query(Book.class)` mapping tự động mọi loại JOIN/nested object”.** Không. Với cấu trúc phức tạp, dùng `RowMapper` và SQL alias có chủ đích.

**Sai lầm 7 — “`list()` không dùng bộ nhớ vì API fluent”.** Không. Danh sách được nạp trước; chọn phân trang hoặc stream có quản lý tài nguyên nếu dữ liệu lớn.

**Sai lầm 8 — “`update()` trả ID mới”.** Không. Nó trả số hàng bị tác động; generated keys cần `KeyHolder` và hỗ trợ của driver.

**Sai lầm 9 — “Có JdbcClient là tự có transaction”.** Không. Transaction manager và service boundary vẫn là phần cấu hình riêng.

**Sai lầm 10 — “`param("name", null)` luôn đủ cho mọi driver”.** Không. Có trường hợp cần overload truyền `sqlType` hoặc `SqlParameterSource` mang metadata.

**Sai lầm 11 — “Có thể dùng JdbcClient cho JPA query và để nó tự lưu entity”.** Không. Đây là Spring JDBC, không phải ORM.

## 17. Bài tập tự luyện

### Bài tập 1 — Đổi positional sang named

Cho SQL:

~~~sql
SELECT id, title, pages
FROM book
WHERE pages >= ? AND pages <= ?
ORDER BY id
~~~

Viết hai phiên bản `JdbcClient`: một dùng `params(min, max)`, một dùng `:min`/`:max` cùng `param(name, value)`. So sánh số lượng và thứ tự dòng trả về.

**Đáp án gợi ý:**

~~~java
List<Book> a = client
        .sql("SELECT id, title, pages FROM book " +
             "WHERE pages >= ? AND pages <= ? ORDER BY id")
        .params(150, 350)
        .query(Book.class)
        .list();

List<Book> b = client
        .sql("SELECT id, title, pages FROM book " +
             "WHERE pages >= :min AND pages <= :max ORDER BY id")
        .param("min", 150)
        .param("max", 350)
        .query(Book.class)
        .list();
~~~

### Bài tập 2 — Phân biệt `optional` và `single`

Với ID 999 không tồn tại, kiểm tra cả hai cách:

~~~java
Optional<Book> optional = client
        .sql("SELECT id, title, pages FROM book WHERE id = ?")
        .param(999L)
        .query(Book.class)
        .optional();
~~~

Kết quả `optional.isPresent()` bằng `false`. Nếu đổi terminal method sang `single()` trong cùng SQL, sẽ có lỗi thiếu hàng. Hãy chọn API dựa trên ý nghĩa nghiệp vụ của “không tìm thấy”.

### Bài tập 3 — Kiểm tra số hàng UPDATE

Cho ID không có trong bảng:

~~~java
int affected = client
        .sql("UPDATE book SET pages = :pages WHERE id = :id")
        .param("pages", 400)
        .param("id", 999L)
        .update();
~~~

Kiểm tra `affected == 0`. Trong service, quyết định xem đây là lỗi "not found", kết quả no-op hợp lệ hay một concurrency conflict. Không dựa vào `JdbcClient` để tự chọn quy tắc nghiệp vụ.

### Bài tập 4 — Null có SQL type

Giả sử bảng có thêm cột `note VARCHAR(120) NULL`. Ghi NULL bằng `.param("note", null, Types.VARCHAR)`. So sánh với `MapSqlParameterSource.addValue("note", null, Types.VARCHAR)` và `.paramSource(...)`. Kiểm tra trên driver mục tiêu, không tự suy đoán rằng giá trị null luôn gắn được type chính xác.

### Bài tập 5 — Stream an toàn

Thay `.list()` bằng `.stream()` để duyệt số lượng lớn. Dùng `try-with-resources` đóng stream. Nếu cần phân trang/throttle hoặc dùng transaction, kiểm tra driver và connection lifecycle trước khi kết luận stream là giải pháp tiết kiệm bộ nhớ trong mọi trường hợp.

## 18. Câu hỏi ôn tập nhanh

**1. `JdbcClient` có từ Spring Framework phiên bản nào?**  
Từ **6.1**; nó thuộc `spring-jdbc` và package `org.springframework.jdbc.core.simple`.

**2. `JdbcClient` thực thi SQL trực tiếp thay thế driver hay delegate?**  
Nó ủy quyền cho các template JDBC của Spring; vẫn dùng `DataSource` và JDBC driver thực.

**3. Làm sao trả nhiều đối tượng record?**  
`client.sql(sql).query(MyRecord.class).list()`, với cột/kiểu phù hợp.

**4. Khi 0 hàng là tình huống bình thường, dùng gì?**  
`optional()` cho lookup tối đa một hàng; `list()` cho danh sách có thể rỗng.

**5. `single()` có chọn hàng đầu khi SQL trả nhiều hàng không?**  
Không. Nó đòi đúng một kết quả và có thể ném `IncorrectResultSizeDataAccessException`.

**6. Làm sao bind theo tên trong SQL?**  
Dùng `:name` và `.param("name", value)`, `params(Map)` hoặc `paramSource(...)`.

**7. `update()` trả về gì?**  
Số hàng bị ảnh hưởng, không phải ID tự tăng.

**8. Khi Spring 6.1 cần batch updates, nên dùng gì?**  
Những API phù hợp ở `JdbcTemplate` hoặc `NamedParameterJdbcTemplate`; không giả định một fluent batch method mới hơn có trong 6.1.

**9. `stream()` có cần đóng?**  
Có. Đóng stream trong `try-with-resources` để giải phóng JDBC resources.

**10. Cần làm gì nếu muốn một transaction bao nhiều `update()`?**  
Đặt transaction boundary với transaction manager tương thích, thường bằng `@Transactional` ở service hoặc `TransactionTemplate`.

## 19. Tài liệu chính thức

- [Spring Framework 6.1 – JDBC Core](https://docs.spring.io/spring-framework/reference/6.1/data-access/jdbc/core.html): `JdbcClient` thống nhất positional/named query và update.
- [JdbcClient Javadoc – Spring Framework 6.1.14](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.html): factory methods và hợp đồng facade.
- [JdbcClient.StatementSpec Javadoc – 6.1.14](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.StatementSpec.html): `sql`, `param`, `params`, `paramSource`, `query`, `update`.
- [JdbcClient.MappedQuerySpec Javadoc – 6.1.14](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.MappedQuerySpec.html): `list`, `single`, `optional`, `set`, `stream`.
- [JdbcClient.ResultQuerySpec Javadoc – 6.1.14](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.ResultQuerySpec.html): `rowSet`, `listOfRows`, `singleRow`, `singleColumn`, `singleValue`.

**Kết luận:** `JdbcClient` từ Spring Framework 6.1 là một giao diện fluent tiện đọc cho các lệnh SQL JDBC thông dụng: `sql → param → query/mapping → list/single/optional` hoặc `sql → param → update`. Nó giữ lại hạ tầng JDBC/Spring JDBC hiện có, cho phép lựa chọn positional/named parameters và mapping linh hoạt, nhưng không tự thay thế transaction manager, JDBC templates nâng cao hoặc ORM.

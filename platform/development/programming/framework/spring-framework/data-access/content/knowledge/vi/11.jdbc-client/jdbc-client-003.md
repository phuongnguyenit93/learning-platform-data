# Bắt đầu thao tác bằng `sql()` trong Spring `JdbcClient`

`JdbcClient` là API fluent của **Spring JDBC từ Spring Framework 6.1**, hỗ trợ thực hiện những thao tác SQL thường gặp thông qua một chuỗi phương thức dễ đọc. Thay vì phải nhớ nhiều overload của `JdbcTemplate` hoặc `NamedParameterJdbcTemplate`, ta bắt đầu bằng một biểu thức chung:

```java
jdbcClient.sql("SELECT title FROM task WHERE id = :id")
          .param("id", 10L)
          .query(String.class)
          .single();
```

Lời gọi đầu tiên, **`sql(String)`**, là điểm khởi đầu: nó nhận câu SQL và trả về một đối tượng mô tả statement để bạn **khai báo các tham số và quyết định cách xử lý kết quả**. Nó **chưa phải lệnh thực thi SQL độc lập**. Ở ví dụ trên, quá trình thực thi diễn ra khi resolver `single()` lấy dữ liệu; với thao tác ghi, `update()` là điểm thực thi.

Bài học này tập trung vào ý nghĩa của `sql()`, kiểu `StatementSpec` mà nó trả về, các đường đi phổ biến sau `sql()`, các lỗi dễ nhầm và một chương trình Java 17+ có thể chạy để kiểm chứng. Ngữ cảnh là Spring Framework **data-access / JdbcClient**; những kiến thức về cơ sở dữ liệu, kết nối và giao dịch được giải thích ở mức cần thiết để sử dụng `sql()` đúng.

## 1. `JdbcClient` giải quyết vấn đề gì?

Spring JDBC đã có hai công cụ mạnh:

- `JdbcTemplate`: SQL với JDBC placeholder theo vị trí `?`, xử lý kết nối, statement, result set và chuyển đổi `SQLException`.
- `NamedParameterJdbcTemplate`: hỗ trợ placeholder đặt tên `:id`, `:status`, `:tenantId` rồi ủy quyền về cơ chế JDBC bên dưới.

`JdbcClient` tạo một lớp giao diện **thống nhất** cho các thao tác truy vấn và cập nhật thường gặp; bạn có thể chọn cú pháp `?` hoặc `:name` trong cùng một kiểu API mà không cần tự mở `Connection`/`PreparedStatement`. Nó vẫn ủy quyền cho các template của Spring JDBC, không phải ORM và không thay thế chúng trong mọi công việc nâng cao.

Đối chiếu cùng một truy vấn:

```java
// JdbcTemplate: tham số theo vị trí.
String a = jdbcTemplate.queryForObject(
    "SELECT title FROM task WHERE id = ?",
    String.class,
    10L
);

// NamedParameterJdbcTemplate: tham số có tên.
String b = namedJdbcTemplate.queryForObject(
    "SELECT title FROM task WHERE id = :id",
    java.util.Map.of("id", 10L),
    String.class
);

// JdbcClient: bắt đầu bằng sql(), bind, rồi chọn kết quả.
String c = jdbcClient
    .sql("SELECT title FROM task WHERE id = :id")
    .param("id", 10L)
    .query(String.class)
    .single();
```

Đây là **ba đoạn minh họa tích hợp**, cần những template đã được khởi tạo và bảng `task` có dữ liệu. Cả ba đặt SQL trong code; `JdbcClient` làm rõ trình tự bằng fluent chain.

**Đặc điểm quan trọng:** `JdbcClient` xử lý những thao tác JDBC đồng bộ. Nó không phải API reactive `DatabaseClient` của R2DBC, không tự sinh SQL từ entity như một ORM, và cũng không tự tạo transaction cho toàn bộ nghiệp vụ chỉ vì có một chuỗi phương thức.

## 2. Tạo một `JdbcClient` trước khi gọi `sql()`

Tên interface:

```java
import org.springframework.jdbc.core.simple.JdbcClient;
```

Các factory phổ biến:

```java
// 1. Từ DataSource đã có.
JdbcClient client = JdbcClient.create(dataSource);

// 2. Tái sử dụng JdbcTemplate/JdbcOperations đã cấu hình.
JdbcClient fromTemplate = JdbcClient.create(jdbcTemplate);

// 3. Tái sử dụng NamedParameterJdbcTemplate đã cấu hình.
JdbcClient fromNamed = JdbcClient.create(namedJdbcTemplate);
```

Đoạn trên là **mã minh họa**; các biến `dataSource`, `jdbcTemplate` và `namedJdbcTemplate` cần có trước. Factory `create` không mở một phiên làm việc JDBC bất biến cho mọi lời gọi. `JdbcClient` tham chiếu tới các thành phần vận hành tương ứng, còn việc lấy/trả connection xảy ra khi thao tác được thực thi.

Trong ứng dụng Spring quản lý bean, có thể cấu hình:

```java
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

Đây là class **tích hợp Spring**, cần `DataSource` được cấu hình riêng. Tùy phiên bản Spring Boot/autoconfiguration, ứng dụng có thể đã cung cấp bean `JdbcClient`; khi đó dùng bean hiện có, không khai báo trùng không cần thiết.

Một repository sử dụng constructor injection:

```java
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class TaskRepository {
    private final JdbcClient client;

    public TaskRepository(JdbcClient client) {
        this.client = client;
    }

    public long countAll() {
        return client.sql("SELECT COUNT(*) FROM task")
                     .query(Long.class)
                     .single();
    }
}
```

Đây là code tích hợp, yêu cầu bảng `task` và JDBC configuration. Sau khi khởi tạo, `JdbcClient` có thể dùng chung; mỗi lần bắt đầu thao tác nên gọi **`client.sql(...)` để nhận một statement specification riêng**. Không tạo rồi chia sẻ một `StatementSpec` mutable cho nhiều request như một template toàn cục.

### Yêu cầu phiên bản

`JdbcClient` xuất hiện từ **Spring Framework 6.1**. Nếu dự án dùng Spring 6.0 hoặc cũ hơn, package `org.springframework.jdbc.core.simple.JdbcClient` sẽ không có trong artifact tương ứng. Cần kiểm tra dependency `spring-jdbc` thực tế và sự đồng bộ phiên bản giữa các thư viện Spring; không chỉ thêm một import vào code rồi mong API tồn tại.

## 3. `sql(String)` nhận gì, trả gì và chưa làm gì?

Chữ ký API:

```java
JdbcClient.StatementSpec sql(String sql);
```

`String` đưa vào là **toàn bộ câu SQL** do ứng dụng định nghĩa, chẳng hạn:

```java
JdbcClient.StatementSpec spec = client.sql(
    "SELECT id, title FROM task WHERE tenant_id = :tenantId"
);
```

- Tham số `sql` là văn bản SQL, không phải tên entity hay đối tượng builder biểu diễn bảng.
- Đối tượng trả về `StatementSpec` mang các lựa chọn bind tham số, truy vấn hoặc cập nhật.
- Tại thời điểm gọi `sql(...)`, code mới **thiết lập mô tả thao tác**; chưa có một kết quả được nạp ra từ database.
- `sql()` không trả `List`, `Optional`, `ResultSet`, `Connection` hay số hàng cập nhật.
- `sql()` không tự biết muốn đọc hay ghi; bước tiếp theo quyết định cách xử lý.

Ví dụ chuỗi hành động:

```text
JdbcClient
    |
    | .sql("SELECT ... WHERE id = :id")
    v
StatementSpec
    |
    | .param("id", 7)
    v
StatementSpec với tham số đã đăng ký
    |
    | .query(TaskView.class)
    v
MappedQuerySpec<TaskView>
    |
    | .optional()
    v
Optional<TaskView>  <- thực thi truy vấn và phân giải cardinality
```

Đối với lệnh cập nhật:

```text
JdbcClient
    |
    | .sql("UPDATE task SET status = :newStatus WHERE id = :id")
    | .param("newStatus", "DONE")
    | .param("id", 7)
    | .update()
    v
int số hàng được tác động  <- thực thi JDBC update
```

Vì vậy, **`sql()` là điểm bắt đầu, không phải điểm kết thúc**. Viết:

```java
client.sql("DELETE FROM task WHERE id = 7");
```

**không phải cách đáng tin để xóa hàng**: bạn mới tạo `StatementSpec` rồi bỏ đi. Muốn thực thi câu DML có số hàng tác động, phải gọi terminal `update()`. Với `SELECT`, cần gọi đường dẫn truy vấn phù hợp rồi tiêu thụ kết quả (hoặc dùng callback/extractor thực thi trực tiếp).

## 4. Các bước có thể nối ngay sau `sql()`

Có ba nhóm hành động chính.

| Bước | Chữ ký điển hình | Ý nghĩa |
| --- | --- | --- |
| Đăng ký tham số vị trí | `.param(value)` | Bind lần lượt vào các dấu `?`. |
| Đăng ký tham số theo chỉ số JDBC | `.param(1, value)` | Chỉ rõ vị trí, **đánh số từ 1**, không từ 0. |
| Đăng ký tham số tên | `.param("id", id)` | Bind giá trị cho placeholder `:id`. |
| Đăng ký nhiều tham số | `.params(...)` | Danh sách positional hoặc `Map<String, ?>` cho named. |
| Đăng ký nguồn tham số | `.paramSource(beanOrRecord)` | Lấy named values từ JavaBean/record/field holder hoặc một `SqlParameterSource`. |
| Bước truy vấn có mapper | `.query(RowMapper<T>)` hoặc `.query(Class<T>)` | Chọn cách chuyển một hàng thành object, sau đó `list()`/`single()`/`optional()`/... |
| Bước truy vấn không mapper tường minh | `.query()` | Cho các dạng `singleRow()`, `listOfRows()`, `singleColumn()`, `rowSet()`, `singleValue()`. |
| Thao tác thay đổi dữ liệu | `.update()` | Thực thi SQL update/insert/delete và trả số hàng tác động. |
| Thao tác ghi có generated keys | `.update(keyHolder, "id")` | Thực thi và cố lấy generated key khi driver/database hỗ trợ. |

**Thứ tự đọc thông thường:** `sql(...) → param/params/paramSource → query(...).list()/single()/optional()` hoặc `update()`.

Một số overload của `query(...)` nhận `ResultSetExtractor<T>` hoặc `RowCallbackHandler` sẽ **thực thi ngay khi callback được gọi** và không trả tiếp `MappedQuerySpec`; cần phân biệt với `query(Class)`/`query(RowMapper)`. Không có một terminal chung tên `execute()` dành cho mọi kiểu thao tác `JdbcClient.StatementSpec` trong Spring 6.1.

## 5. Bắt đầu bằng `sql()` không có tham số

Không bắt buộc lời gọi `sql()` nào cũng có `param()`. Nếu SQL không cần bind value:

```java
long total = client
    .sql("SELECT COUNT(*) FROM task")
    .query(Long.class)
    .single();

List<TaskView> tasks = client
    .sql("SELECT id, title, status FROM task ORDER BY id")
    .query(TaskView.class)
    .list();
```

Đây là đoạn mã tích hợp; `TaskView` là kiểu dữ liệu của ứng dụng có property/constructor thích hợp. Đối với query không có `WHERE`, cần cân nhắc số hàng rất lớn trước khi gọi `list()`.

Không nên coi việc không có parameter là lý do để tự nối chuỗi người dùng vào SQL:

```java
// Không an toàn: input có thể làm thay đổi cú pháp truy vấn.
String sql = "SELECT id FROM task WHERE title = '" + userTitle + "'";
List<Long> ids = client.sql(sql).query(Long.class).list();
```

Đoạn trên là **phản ví dụ**, không chạy độc lập. Cách đúng là dùng `:title` hoặc `?` và bind dữ liệu:

```java
List<Long> ids = client
    .sql("SELECT id FROM task WHERE title = :title")
    .param("title", userTitle)
    .query(Long.class)
    .list();
```

Bên dưới, Spring JDBC dùng cơ chế `PreparedStatement`. Bind value tránh để giá trị trở thành một đoạn SQL do người dùng viết.

## 6. Từ `sql()` đến tham số theo vị trí `?`

Cách gần với JDBC truyền thống nhất:

```java
String title = client
    .sql("SELECT title FROM task WHERE tenant_id = ? AND id = ?")
    .param(10L)
    .param(7L)
    .query(String.class)
    .single();
```

Ở đây:

1. `.sql(...)` xác định câu truy vấn có **hai** dấu `?`.
2. `.param(10L)` đăng ký giá trị thứ nhất.
3. `.param(7L)` đăng ký giá trị thứ hai.
4. `.query(String.class).single()` thực thi và cần đúng một hàng một giá trị có thể ánh xạ thành String.

Một kiểu khác cho ít tham số:

```java
String title = client
    .sql("SELECT title FROM task WHERE tenant_id = ? AND id = ?")
    .params(10L, 7L)
    .query(String.class)
    .single();
```

`params(Object...)` và `params(List<?>)` đều đăng ký danh sách giá trị positional. Chúng **không tự đoán thứ tự thông qua tên cột**; nếu đổi vị trí `WHERE` trong SQL, hãy kiểm tra lại thứ tự bind. Với nhiều trường cùng kiểu (ví dụ `tenantId` và `accountId` cùng là long), nhầm thứ tự có thể trả dữ liệu sai mà không có lỗi type.

### Chỉ số JDBC bắt đầu từ 1

```java
String title = client
    .sql("SELECT title FROM task WHERE tenant_id = ? AND id = ?")
    .param(2, 7L)
    .param(1, 10L)
    .query(String.class)
    .single();
```

Ở overload `param(int jdbcIndex, Object value)`, `jdbcIndex` là **vị trí của placeholder trong PreparedStatement**, bắt đầu từ **1**, không phải index mảng Java. Cách gọi tường minh có thể giúp khi chuẩn bị query động, nhưng đòi hỏi bảo trì chỉ số chính xác.

Không viết `.param(0, ...)`; và không nhầm `.param(1L)` (một giá trị positional) với `.param(1, 7L)` (một vị trí cộng với giá trị).

## 7. Từ `sql()` đến tham số có tên `:name`

Một đặc điểm nổi bật của `JdbcClient` là cho phép cùng phương thức `sql(...)` bắt đầu câu SQL với **named placeholders**:

```java
String title = client
    .sql("""
         SELECT title
         FROM task
         WHERE tenant_id = :tenantId AND id = :id
         """)
    .param("tenantId", 10L)
    .param("id", 7L)
    .query(String.class)
    .single();
```

Trong SQL dùng `:tenantId` nhưng khi bind truyền tên **`"tenantId"` không có dấu hai chấm**. Spring sẽ phân tích và chuyển các named placeholders sang JDBC positional placeholders đúng thứ tự; ứng dụng không phải tự thay thế.

Ưu điểm là khi điều kiện SQL thay đổi vị trí, giá trị vẫn gắn với tên có nghĩa. Nếu `:tenantId` xuất hiện hai lần, nguồn tham số cùng tên được dùng ở cả hai vị trí; không cần tạo hai biến riêng.

Có thể truyền nhiều tên bằng `params(Map)`:

```java
Map<String, ?> values = Map.of(
    "tenantId", 10L,
    "status", "OPEN"
);

List<TaskView> rows = client
    .sql("SELECT id, title, status FROM task " +
         "WHERE tenant_id = :tenantId AND status = :status " +
         "ORDER BY id")
    .params(values)
    .query(TaskView.class)
    .list();
```

Đây là code tích hợp; `Map` cần import `java.util.Map`. `Map.of(...)` **không chấp nhận null**. Với giá trị null hoặc cần chỉ rõ SQL type, dùng `param("name", null, Types.XXX)` hoặc `paramSource(MapSqlParameterSource)`.

**Chọn một kiểu tham số nhất quán trong mỗi câu SQL.** Đừng chủ động phối hợp `?` và `:id` trong cùng statement; cách Spring lựa chọn cơ chế bind có thể gây lỗi hoặc khó hiểu. Dùng positional cho truy vấn ngắn; named cho truy vấn nhiều trường/điều kiện dài.

## 8. `paramSource(...)` tiếp tục chuỗi khởi đầu từ `sql()`

Nếu có một đối tượng đầu vào đại diện cho bộ giá trị, `paramSource(Object)` lấy named values từ JavaBean, record hoặc field holder:

```java
// Record Java 17: tên component trùng tên named parameter.
record NewTask(long id, long tenantId, String title, String status) {}

int changed = client
    .sql("""
         INSERT INTO task (id, tenant_id, title, status)
         VALUES (:id, :tenantId, :title, :status)
         """)
    .paramSource(new NewTask(1L, 10L, "Learn JDBC", "OPEN"))
    .update();
```

Đây là **đoạn minh họa**; file đầy đủ phía sau sử dụng record cùng ý tưởng nhưng có thêm cột. Trong Spring 6.1, `JdbcClient` hỗ trợ lấy tham số từ record/JavaBean/field holder thông qua chiến lược `SimplePropertySqlParameterSource`, không bắt buộc bạn tự đưa từng component vào `Map`.

Có overload nhận `SqlParameterSource` khi cần metadata JDBC type:

```java
import java.sql.Types;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

MapSqlParameterSource source = new MapSqlParameterSource()
    .addValue("id", 9L)
    .addValue("note", null, Types.VARCHAR);

int changed = client
    .sql("UPDATE task SET note = :note WHERE id = :id")
    .paramSource(source)
    .update();
```

Đoạn này là code tích hợp, cần bảng `task` có cột `note`. Đặt type cho `NULL` giúp driver biết kiểu SQL. Cũng có overload ngắn hơn:

```java
client.sql("UPDATE task SET note = :note WHERE id = :id")
      .param("note", null, java.sql.Types.VARCHAR)
      .param("id", 9L)
      .update();
```

`paramSource(Object)` và `paramSource(SqlParameterSource)` không có cùng ý nghĩa chính xác như `RowMapper`. Parameter source đọc **giá trị đầu vào**; `query(RowMapper)` đọc **ResultSet đầu ra**.

## 9. `sql()` đi với `query(Class<T>)`: kết quả đơn giản và object

Sau khi hoàn thành statement, `query(Class<T>)` tạo ra một `MappedQuerySpec<T>` để chọn hình dạng kết quả.

### Một giá trị một cột

```java
long count = client
    .sql("SELECT COUNT(*) FROM task WHERE status = :status")
    .param("status", "OPEN")
    .query(Long.class)
    .single();
```

`COUNT(*)` không có `GROUP BY` trả một hàng duy nhất, chứa số lượng (có thể là 0). `query(Long.class)` là ánh xạ một cột có thể chuyển sang `Long`; `single()` yêu cầu một object không-null theo contract của resolver.

### Một object nhiều cột

Spring 6.1 có chiến lược ánh xạ `SimplePropertyRowMapper` cho target JavaBean, record, constructor-based object hoặc field holder ở các trường hợp được hỗ trợ. Ví dụ:

```java
public record TaskView(long id, String title, String status) {}

TaskView task = client
    .sql("SELECT id, title, status FROM task WHERE id = :id")
    .param("id", 7L)
    .query(TaskView.class)
    .single();
```

Record nhận dữ liệu qua constructor theo tên component phù hợp với tên cột; không cần setter. Nếu tên cột khác tên property, dùng alias SQL, ví dụ `db_task_name AS title`. Với logic ánh xạ phức tạp hoặc type JDBC chuyên biệt, nên chọn `RowMapper` viết tay.

**Lưu ý:** `.query(TaskView.class)` không biến `TaskView` thành entity theo nghĩa JPA; nó chỉ xác định target để map các cột **mỗi hàng**. Nó cũng không sửa cardinality: nhiều hàng thì `single()` vẫn là lựa chọn sai.

## 10. `sql()` kết hợp `query(RowMapper<T>)`

Khi muốn kiểm soát chính xác cách ánh xạ:

```java
List<TaskView> tasks = client
    .sql("""
         SELECT id, title, status
         FROM task
         WHERE tenant_id = :tenantId
         ORDER BY id
         """)
    .param("tenantId", 10L)
    .query((rs, rowNum) -> new TaskView(
        rs.getLong("id"),
        rs.getString("title"),
        rs.getString("status")
    ))
    .list();
```

Đây là đoạn tích hợp, giả sử `TaskView` và `client` đã tồn tại. `RowMapper` chạy cho từng hàng; `list()` trả danh sách đã ánh xạ.

Để tránh nhầm khi overload `query(...)` nhận callback, cách dùng lambda hai tham số `(rs, rowNum) -> ...` phù hợp với `RowMapper`; một callback kiểu `RowCallbackHandler` có chữ ký khác, còn `ResultSetExtractor` làm việc với toàn `ResultSet`. Nếu type inference khó phân giải trong biểu thức phức tạp, có thể khai báo `RowMapper<TaskView> mapper` rồi gọi `query(mapper)`.

Không cần dùng `try-with-resources` cho một `Connection` do `JdbcClient`/Spring quản lý khi chỉ đọc dữ liệu bằng template. `JdbcClient` tiếp tục dùng cơ chế JDBC của Spring để đóng tài nguyên đúng phạm vi.

## 11. Chọn kết quả sau `query(...)`

Các resolver phổ biến của `MappedQuerySpec<T>`:

| Resolver | Kỳ vọng số hàng | Kết quả |
| --- | --- | --- |
| `list()` | 0 đến nhiều | `List<T>`, có thể rỗng; giữ thứ tự kết quả SQL. |
| `single()` | Chính xác 1 object không-null | Trả `T`; 0 hoặc trên 1 thường gây exception phù hợp. |
| `optional()` | 0 hoặc 1 | `Optional<T>`; nếu >1 là lỗi cardinality. |
| `set()` | 0 đến nhiều | `Set<T>` giữ thứ tự xuất hiện ở query khi loại trùng theo equality. |
| `stream()` | 0 đến nhiều, xử lý tuần tự/lazy | `Stream<T>` cần được đóng sau khi sử dụng. |

Ví dụ với id có thể vắng:

```java
Optional<TaskView> found = client
    .sql("SELECT id, title, status FROM task WHERE id = :id")
    .param("id", id)
    .query(TaskView.class)
    .optional();
```

Code cần import `java.util.Optional` và dữ liệu tồn tại. Nếu SQL trả **hai hàng** vì điều kiện không unique, `optional()` không có nghĩa “lấy một hàng bất kỳ”; trường hợp đó vẫn là sai kỳ vọng.

Ví dụ danh sách:

```java
List<TaskView> open = client
    .sql("SELECT id, title, status " +
         "FROM task WHERE status = :status ORDER BY id")
    .param("status", "OPEN")
    .query(TaskView.class)
    .list();
```

`list()` phù hợp cho kết quả 0/n hàng, nhưng với bảng lớn phải giới hạn hoặc phân trang có chủ đích. `ORDER BY` mang lại thứ tự xác định; không có `ORDER BY` thì database không cam kết một thứ tự hàng ổn định.

### Dùng `stream()` đúng vòng đời

```java
try (Stream<TaskView> stream = client
        .sql("SELECT id, title, status FROM task ORDER BY id")
        .query(TaskView.class)
        .stream()) {
    stream.forEach(task -> consume(task));
}
```

Đây là đoạn code **tích hợp**, cần import `Stream` và hàm `consume`. `stream()` trả resource-backed stream, vì vậy nên **tiêu thụ và đóng** trong cùng phạm vi giao dịch/kết nối thích hợp. Không trả stream giữ cursor ra khỏi phương thức `@Transactional` rồi để người gọi tiêu thụ sau khi transaction đã kết thúc.

## 12. `query()` không truyền mapper: các kiểu trả kết quả trực tiếp

Khác với `query(Class<T>)`, lời gọi `query()` không có tham số trả về `ResultQuerySpec` với những cách lấy giá trị sẵn có:

```java
// Danh sách map cho nhiều hàng.
List<Map<String, Object>> rows = client
    .sql("SELECT id, title FROM task ORDER BY id")
    .query()
    .listOfRows();

// Một map đại diện cho một hàng.
Map<String, Object> row = client
    .sql("SELECT id, title FROM task WHERE id = :id")
    .param("id", 7L)
    .query()
    .singleRow();

// Một giá trị (không ánh xạ thành DTO).
Object value = client
    .sql("SELECT COUNT(*) FROM task")
    .query()
    .singleValue();
```

Đây là minh họa tích hợp, cần import `List` và `Map`. Ngoài ra có `singleColumn()` trả danh sách các giá trị của một cột, và `rowSet()` trả `SqlRowSet` tách khỏi kết quả JDBC gốc.

Sự khác biệt quan trọng:

- `query(Class<T>).single()`: đường đi **mapped** và typed.
- `query().singleRow()`: một hàng biểu diễn bằng `Map<String,Object>`.
- `query().listOfRows()`: nhiều hàng là danh sách các map.
- `query().singleValue()`: một giá trị `Object` từ một hàng/một cột; không phải `String.class`/`Long.class` typed mapping.

Đừng viết `query().single()`: đó không phải tên resolver của `ResultQuerySpec` trong API 6.1. Ngược lại `query(String.class).single()` là hợp lệ.

## 13. Từ `sql()` đến `update()`: INSERT, UPDATE, DELETE

Mẫu fluent cho thao tác ghi:

```java
int inserted = client
    .sql("""
         INSERT INTO task(id, tenant_id, title, status)
         VALUES (:id, :tenantId, :title, :status)
         """)
    .param("id", 7L)
    .param("tenantId", 10L)
    .param("title", "Write tests")
    .param("status", "OPEN")
    .update();
```

`update()` là **terminal operation** trả số hàng tác động. Với một `INSERT` thông thường trả 1; với `UPDATE` hoặc `DELETE` có thể là 0, 1 hoặc nhiều tùy điều kiện `WHERE`, driver/database và quy tắc nghiệp vụ.

```java
int changed = client
    .sql("""
         UPDATE task
         SET status = :newStatus
         WHERE id = :id AND tenant_id = :tenantId
         """)
    .param("newStatus", "DONE")
    .param("id", taskId)
    .param("tenantId", tenantId)
    .update();

if (changed != 1) {
    throw new IllegalStateException(
        "Expected to update exactly one task, actual=" + changed
    );
}
```

Đoạn này tích hợp vào repository/service với các ID đã có. Nếu `changed==0`, SQL không nhất thiết lỗi; có thể không tìm thấy ID, sai tenant hoặc version không còn khớp. Nếu update điều kiện rộng trả `changed > 1`, đó có thể là hợp lệ hoặc là lỗi domain tùy hợp đồng.

Với `DELETE`:

```java
int removed = client
    .sql("DELETE FROM task WHERE tenant_id = :tenantId AND id = :id")
    .params(Map.of("tenantId", tenantId, "id", taskId))
    .update();
```

Ở đây `params(Map)` gắn tên với giá trị, không dựa vào thứ tự entry trong map. Luôn kiểm tra scope `tenant_id` và quyền truy cập; bind an toàn không tự thêm kiểm tra authorization.

### Generated keys

`StatementSpec` có overload `update(KeyHolder)` và `update(KeyHolder, String... keyColumnNames)` khi JDBC driver hỗ trợ lấy generated keys:

```java
GeneratedKeyHolder holder = new GeneratedKeyHolder();

int inserted = client
    .sql("INSERT INTO task(title, status) VALUES (:title, :status)")
    .param("title", "Example")
    .param("status", "OPEN")
    .update(holder, "id");
```

Đây là **minh họa**, cần bảng có khóa tự sinh và import `org.springframework.jdbc.support.GeneratedKeyHolder`. Không thể chạy nếu schema yêu cầu những cột NOT NULL không có default. Khả năng trả key, tên cột được hỗ trợ và cách đọc `holder.getKey()` phụ thuộc DB/driver; kiểm thử trên database thật.

## 14. Không nhầm `sql()` với tạo/chuẩn bị kết nối thủ công

Một chain `JdbcClient` thường có vòng đời:

```text
Repository gọi JdbcClient.sql(...)
         |
StatementSpec + param bindings
         |
terminal query/update
         |
Spring JDBC lấy Connection phù hợp với transaction
         |
PreparedStatement thực thi
         |
RowMapper/ResultSetExtractor hoặc update count
         |
Spring JDBC dọn statement/result set và release connection thích hợp
```

Bạn không cần:

```java
// Không làm thế này để "bổ sung" JdbcClient:
Connection connection = dataSource.getConnection();
// ... tự gọi commit/close cạnh một chuỗi JdbcClient độc lập ...
```

Code JDBC thủ công có thể lấy một connection **khác** với connection transaction-bound mà Spring sử dụng; vì thế nó không mặc nhiên tham gia cùng giao dịch với `JdbcClient`. Khi cần JDBC cấp thấp, sử dụng API Spring tương ứng như `JdbcTemplate.execute(...)`, `DataSourceUtils` hoặc transaction manager theo ownership đúng.

Đối với ứng dụng Spring có `@Transactional` hoạt động, nhiều lời gọi `client.sql(...).update()` trong cùng transaction cho cùng `DataSource` có thể dùng chung transaction-bound connection. `sql()` tự nó không commit/rollback; transaction kết thúc theo interceptor/`TransactionTemplate` và policy đã cấu hình.

## 15. Điều gì xảy ra khi SQL bị thiếu tham số hoặc kết quả sai số hàng?

### Thiếu bind cho placeholder

```java
// Thiếu .param("id", ...) cho :id.
client.sql("SELECT title FROM task WHERE id = :id")
      .query(String.class)
      .single();
```

Khi thực thi, Spring không có giá trị để bind `:id` nên thao tác thất bại, thường trong nhánh exception truy cập dữ liệu/tham số của Spring. `sql()` không tự phát minh giá trị cho placeholder, cũng không tự coi tham số chưa có là NULL.

### Bind sai kiểu hoặc sai chỉ số

```java
// Ở đây thiếu parameter thứ hai.
client.sql("SELECT title FROM task WHERE tenant_id = ? AND id = ?")
      .param(10L)
      .query(String.class)
      .single();
```

Một placeholder `?` chưa được gán thường dẫn tới lỗi lúc thực thi. Nếu dùng `.param(0, ...)`, chỉ số JDBC không hợp lệ vì đánh từ 1. Nếu dùng `.params("OPEN", 10L)` trong SQL đòi `tenant_id` trước rồi `status` sau, query có thể sai ngữ nghĩa dù kiểu đều chuyển đổi được.

### Kết quả có 0, 1 hoặc nhiều hàng

```java
TaskView one = client.sql("SELECT id, title, status FROM task WHERE id = :id")
                     .param("id", taskId)
                     .query(TaskView.class)
                     .single();
```

`single()` đòi đúng một object không-null. Nếu không có hàng, thường nhận `EmptyResultDataAccessException`; nếu nhiều hơn một hàng, nhận `IncorrectResultSizeDataAccessException`. Nếu nghiệp vụ cho phép không có hàng, dùng `optional()`; nếu nhiều hàng là bình thường, dùng `list()`.

Không nên chữa số hàng bằng `LIMIT 1` mù quáng: đó là hành vi **chọn một bản ghi** chứ không sửa sai invariant “phải duy nhất”. Nếu cần record mới nhất, chỉ định `ORDER BY created_at DESC, id DESC` và giới hạn theo dialect một cách có chủ đích.

### Câu SQL sai hoặc bảng không tồn tại

`JdbcClient` vẫn chạy qua JDBC driver và database. Nếu `task` không tồn tại, tên cột sai, query thiếu quyền hoặc SQL không hợp dialect, exception sẽ đi qua cơ chế chuyển dịch `SQLException` của Spring (thường là một `DataAccessException` thích hợp). Thay `JdbcTemplate` bằng `JdbcClient` không thể làm SQL sai trở nên đúng.

## 16. `sql()` bảo vệ giá trị, không phải cấu trúc SQL động

Vì `sql()` nhận **String SQL đã được xây dựng**, bạn phải biết rõ phần nào là cấu trúc cố định và phần nào cần bind.

**Đúng:**

```java
client.sql("SELECT id, title FROM task WHERE title = :title")
      .param("title", userInput)
      .query(TaskView.class)
      .list();
```

Trong đoạn này cần SQL projection có các cột phù hợp `TaskView`; nếu `TaskView` yêu cầu cả `status`, cần thêm cột trong `SELECT`. Đoạn là minh họa an toàn về bind, không phải chương trình chạy độc lập.

**Sai:**

```java
String sql = "SELECT id FROM task WHERE title = '" + userInput + "'";
client.sql(sql).query(Long.class).list();
```

Vì `userInput` đã được ghép vào SQL trước `sql()`, dấu quote và ký hiệu SQL bên trong input có thể làm thay đổi câu lệnh. Fluent API không tự sửa việc xây chuỗi trước đó.

Cũng không thể truyền **tên bảng/cột hoặc hướng `ORDER BY`** qua `:columnName` rồi mong DB hiểu đó là identifier. Bind placeholders biểu diễn giá trị, không phải cấu trúc SQL:

```java
String orderColumn = switch (sortKey) {
    case "id" -> "id";
    case "title" -> "title";
    default -> throw new IllegalArgumentException("Invalid sort field");
};

List<TaskView> tasks = client
    .sql("SELECT id, title, status FROM task " +
         "WHERE tenant_id = :tenantId ORDER BY " + orderColumn)
    .param("tenantId", tenantId)
    .query(TaskView.class)
    .list();
```

Đây là mã tích hợp với `sortKey`/`tenantId` được cung cấp; **chỉ hai literal đã được whitelist** được đưa vào SQL. Dữ liệu vẫn bind bằng `:tenantId`. Nếu cần sort chiều tăng/giảm động, hãy whitelist cả chiều thay vì dùng chuỗi người dùng trực tiếp.

## 17. Danh sách `IN` khi khởi đầu bằng `sql()`

Với named placeholders, Spring JDBC hỗ trợ mở rộng một collection thành nhiều dấu `?` cho SQL `IN` thông thường:

```java
List<Long> ids = List.of(1L, 3L, 5L);

List<TaskView> tasks = client
    .sql("SELECT id, title, status FROM task " +
         "WHERE id IN (:ids) ORDER BY id")
    .param("ids", ids)
    .query(TaskView.class)
    .list();
```

Câu SQL được chuẩn bị tương ứng với số phần tử; database vẫn nhận từng giá trị qua JDBC binding. Không cần ghép chuỗi `"1,3,5"` vào SQL.

Nếu `ids` trống, `IN ()` không phải cú pháp SQL di động và có thể gây lỗi. Ở tầng repository, hãy quyết định chính sách rõ:

```java
public List<TaskView> findByIds(List<Long> ids) {
    if (ids.isEmpty()) {
        return List.of();
    }
    return client.sql(
            "SELECT id, title, status FROM task " +
            "WHERE id IN (:ids) ORDER BY id")
        .param("ids", ids)
        .query(TaskView.class)
        .list();
}
```

Đây là một method minh họa cần field `client` và record `TaskView`; chính sách trả list rỗng phù hợp với tác vụ **tìm trong tập rỗng**. Với thao tác `DELETE` hoặc `UPDATE`, tuyệt đối không biến tập ID rỗng thành lệnh xóa/cập nhật **thiếu `WHERE`**.

Collection rất lớn có thể chạm giới hạn số placeholder hoặc điều kiện `IN` của DB; cân nhắc phân lô, temporary table hoặc khả năng chuyên biệt của database. `sql()` không tự bảo đảm hiệu năng và không cấp phép bind vô hạn.

## 18. Giao dịch: `sql()` không phải ranh giới commit

Ví dụ service gọi hai câu SQL:

```java
@Transactional
public void markAndAudit(long taskId) {
    client.sql("UPDATE task SET status = :status WHERE id = :id")
          .param("status", "DONE")
          .param("id", taskId)
          .update();

    client.sql(
          "INSERT INTO task_audit(task_id, action) VALUES (:id, :action)")
          .param("id", taskId)
          .param("action", "MARK_DONE")
          .update();
}
```

Đây là mã tích hợp cần `task_audit`, bean service do Spring quản lý và transaction manager đúng cấu hình. Mỗi `sql()` tạo một thao tác JDBC riêng; tính nguyên tử giữa hai thao tác phải đến từ **`@Transactional` thực sự được intercept** hoặc `TransactionTemplate` với cùng DataSource/transaction manager.

Nếu thao tác thứ hai ném unchecked exception ra ngoài boundary, Spring mặc định rollback transaction phù hợp. Nếu không có transaction, mỗi statement có thể auto-commit độc lập. `sql()` không tạo một transaction ngầm bao quanh mọi lệnh ở cùng Java method.

**Cẩn thận:** tự gọi method `@Transactional` trên cùng bean trong proxy mode có thể bypass interceptor; và nếu nhiều `DataSource` khác nhau, một local JDBC transaction manager không tự tạo distributed transaction cho tất cả chúng.

## 19. Ví dụ chạy được Java 17+: nhìn rõ điểm bắt đầu và điểm thực thi

Ví dụ sử dụng **Spring JDBC 6.1.14**, **H2 2.2.224** và JDK 17+. Không yêu cầu Spring Boot. Nó kiểm chứng:

1. `JdbcClient.create(DataSource)` được tạo một lần.
2. `sql(...)` + `paramSource(record)` + `update()` insert.
3. `sql(...)` + `param("name", value)` insert và bind `NULL` có SQL type.
4. `sql(...)` + positional `params(...)` + `query(Long.class).single()`.
5. `sql(...)` + named `param(...)` + `query(String.class).single()`.
6. `sql(...)` + named `params(Map)` + `query(TaskView.class).list()`.
7. `sql(...)` + `optional()` cho ID không tồn tại.
8. `sql(...)` + list parameter `IN (:ids)`.
9. `sql(...)` + `update()` trả số hàng cập nhật.
10. `TransactionTemplate` cho rollback một update trên cùng DataSource.

### 19.1. Tạo `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>learning</groupId>
    <artifactId>jdbcclient-sql-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <maven.compiler.parameters>true</maven.compiler.parameters>
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
```

### 19.2. Tạo `src/main/java/JdbcClientSqlDemo.java`

```java
import java.sql.Types;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;

public class JdbcClientSqlDemo {
    public record TaskInput(
            long id, long tenantId, String title,
            String status, Integer priority) {}

    public record TaskView(long id, String title, String status) {}

    public static void main(String[] args) {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:sql_start;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");

        // DDL được thực hiện riêng bằng JdbcTemplate.
        // JdbcClient tập trung vào các query/update nghiệp vụ.
        JdbcTemplate schema = new JdbcTemplate(ds);
        schema.execute(
            "CREATE TABLE task (" +
            "id BIGINT PRIMARY KEY, " +
            "tenant_id BIGINT NOT NULL, " +
            "title VARCHAR(100) NOT NULL, " +
            "status VARCHAR(20) NOT NULL, " +
            "priority INTEGER)"
        );

        JdbcClient client = JdbcClient.create(ds);

        // 1) sql() -> paramSource(record) -> update(): ghi hàng đầu.
        int inserted = client.sql(
                "INSERT INTO task(id, tenant_id, title, status, priority) " +
                "VALUES (:id, :tenantId, :title, :status, :priority)")
            .paramSource(new TaskInput(
                1L, 10L, "Learn JDBC", "OPEN", 1))
            .update();
        System.out.println("Inserted via record: " + inserted);

        // 2) Named parameters theo từng tên.
        client.sql(
                "INSERT INTO task(id, tenant_id, title, status, priority) " +
                "VALUES (:id, :tenantId, :title, :status, :priority)")
            .param("id", 2L)
            .param("tenantId", 10L)
            .param("title", "Review SQL")
            .param("status", "OPEN")
            .param("priority", 2)
            .update();

        // 3) Có thể bind NULL kèm JDBC SQL type.
        client.sql(
                "INSERT INTO task(id, tenant_id, title, status, priority) " +
                "VALUES (:id, :tenantId, :title, :status, :priority)")
            .param("id", 3L)
            .param("tenantId", 20L)
            .param("title", "Ship")
            .param("status", "DONE")
            .param("priority", null, Types.INTEGER)
            .update();

        // 4) Positional ? + params(...) + typed result.
        long count = client
            .sql("SELECT COUNT(*) FROM task WHERE tenant_id = ?")
            .params(10L)
            .query(Long.class)
            .single();
        System.out.println("Tenant 10 count: " + count);

        // 5) Named parameter + đúng một giá trị.
        String firstTitle = client
            .sql("SELECT title FROM task WHERE id = :id")
            .param("id", 1L)
            .query(String.class)
            .single();
        System.out.println("Title #1: " + firstTitle);

        // 6) Named params Map + record mapping cho nhiều hàng.
        List<TaskView> open = client
            .sql(
                "SELECT id, title, status FROM task " +
                "WHERE tenant_id = :tenantId AND status = :status " +
                "ORDER BY id")
            .params(Map.of("tenantId", 10L, "status", "OPEN"))
            .query(TaskView.class)
            .list();
        List<String> titles = open.stream()
            .map(TaskView::title)
            .toList();
        System.out.println("Open tasks: " + titles);

        // 7) Optional phân biệt vắng hàng.
        Optional<String> missing = client
            .sql("SELECT title FROM task WHERE id = :id")
            .param("id", 999L)
            .query(String.class)
            .optional();
        System.out.println("Missing is empty: " + missing.isEmpty());

        // 8) Collection được mở rộng trong IN.
        List<Long> matching = client
            .sql(
                "SELECT id FROM task " +
                "WHERE tenant_id = :tenantId AND id IN (:ids) " +
                "ORDER BY id")
            .param("tenantId", 10L)
            .param("ids", List.of(1L, 3L))
            .query(Long.class)
            .list();
        System.out.println("IN result: " + matching);

        // 9) update() trả số hàng bị tác động.
        int changed = client
            .sql("UPDATE task SET status = :status WHERE id = :id")
            .param("status", "DONE")
            .param("id", 2L)
            .update();
        System.out.println("Updated: " + changed);

        long stillOpen = client
            .sql("SELECT COUNT(*) FROM task WHERE status = :status")
            .param("status", "OPEN")
            .query(Long.class)
            .single();
        System.out.println("Still open: " + stillOpen);

        // 10) sql() không tự kiểm soát transaction.
        TransactionTemplate tx = new TransactionTemplate(
            new DataSourceTransactionManager(ds));
        try {
            tx.executeWithoutResult(status -> {
                client.sql(
                        "UPDATE task SET status = :status WHERE id = :id")
                    .param("status", "CANCELLED")
                    .param("id", 1L)
                    .update();

                throw new IllegalStateException("Business failure");
            });
        } catch (IllegalStateException expected) {
            System.out.println("Transaction rolled back");
        }

        String statusAfter = client
            .sql("SELECT status FROM task WHERE id = :id")
            .param("id", 1L)
            .query(String.class)
            .single();
        System.out.println("Task #1 after rollback: " + statusAfter);
    }
}
```

### 19.3. Chạy chương trình

Đặt hai file theo cấu trúc:

```text
jdbcclient-sql-demo/
├── pom.xml
└── src/main/java/JdbcClientSqlDemo.java
```

Cần JDK 17+ và Apache Maven. Tại thư mục chứa `pom.xml`, chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=JdbcClientSqlDemo
```

Các dòng do chính `System.out.println` trong ví dụ tạo ra:

```text
Inserted via record: 1
Tenant 10 count: 2
Title #1: Learn JDBC
Open tasks: [Learn JDBC, Review SQL]
Missing is empty: true
IN result: [1]
Updated: 1
Still open: 1
Transaction rolled back
Task #1 after rollback: OPEN
```

Các plugin, logger hoặc Maven có thể in thêm thông báo khác. Bảng stdout trên chỉ liệt kê những dòng do chương trình in.

### 19.4. Vì sao output có những giá trị đó?

- `Inserted via record: 1`: `sql(...)` nhận `INSERT`, `paramSource(TaskInput)` cung cấp đúng năm tên, `update()` thực thi một insert thành công.
- `Tenant 10 count: 2`: có hai task thuộc tenant 10, đếm bằng một placeholder `?` và `params(10L)`.
- `Title #1`: named placeholder `:id` nhận 1 và `query(String.class).single()` trả `Learn JDBC`.
- `Open tasks`: kết hợp `:tenantId`/`:status` lấy đúng hai task OPEN, sắp xếp theo id, ánh xạ thành record `TaskView`.
- `Missing is empty: true`: query ID 999 trả không có hàng, `optional()` biểu diễn việc vắng kết quả.
- `IN result: [1]`: tập ID `[1,3]` được bind, nhưng `tenant_id = 10` chỉ khớp ID 1.
- `Updated: 1`: thay status task 2 thành DONE, chỉ một hàng bị tác động.
- `Still open: 1`: trong ba task chỉ còn task 1 có status OPEN.
- `Transaction rolled back` và `Task #1 after rollback: OPEN`: `TransactionTemplate` rollback thao tác đổi task 1 thành CANCELLED vì unchecked exception. Dù từng lệnh bắt đầu bằng `sql()`, quyết định transaction là của Spring transaction manager.

`DriverManagerDataSource` ở demo là nguồn kết nối đơn giản **không có connection pool**. Ứng dụng production thường dùng DataSource/pool do Spring quản lý và cấu hình transaction phù hợp. Ví dụ minh họa chức năng Spring JDBC, không phải cấu hình vận hành production đầy đủ.

## 20. Những lỗi đặc trưng khi mới học `sql()`

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Viết `client.sql("UPDATE ...")` rồi bỏ kết quả | Chỉ tạo statement spec, không chạy lệnh ghi. | Kết thúc bằng `update()`. |
| Viết `client.sql("SELECT ...").list()` | `StatementSpec` chưa có `list()` trực tiếp. | Gọi `query(Class/RowMapper).list()`. |
| Viết `client.sql("SELECT ...").query().single()` | `ResultQuerySpec` không có resolver tên `single()`. | `query(Type.class).single()` hoặc `query().singleValue()/singleRow()`. |
| Dùng `.param(0, value)` | JDBC explicit index bắt đầu từ 1. | Dùng `.param(1, value)` hoặc positional `.param(value)`. |
| Đổi thứ tự SQL `?` nhưng không đổi thứ tự `params(...)` | Bind sai giá trị. | Giữ đúng thứ tự hoặc dùng `:name`. |
| Dùng `.param(":id", id)` | Tên bind được ghi không có dấu `:`; placeholder mới có `:`. | `.param("id", id)`. |
| Dùng `Map.of("note", null)` | `Map.of` ném `NullPointerException`. | `.param("note", null, Types.VARCHAR)` hoặc `MapSqlParameterSource`. |
| Truyền tên cột qua placeholder | Placeholder là **giá trị**, không phải SQL identifier. | Whitelist identifier rồi ghép literal an toàn. |
| Ghép raw user input vào String truyền cho `sql()` | Fluent API không chống injection cho SQL đã bị ghép nguy hiểm. | Dùng `:name` hoặc `?`; không ghép values vào SQL. |
| Dùng `single()` cho query nhiều hàng | Nhiều kết quả gây exception cardinality. | Dùng `list()` hoặc sửa SQL để duy nhất. |
| Dùng `optional()` để che duplicate | `optional()` chỉ chấp nhận 0 hoặc 1, không tự lấy hàng đầu. | Sửa SQL/invariant hoặc dùng danh sách. |
| Bỏ quên `close()` trên `stream()` | Có thể rò rỉ cursor/statement. | `try-with-resources` cho stream. |
| Nghĩ `JdbcClient` tự sinh repository/JPA entity | `JdbcClient` vẫn yêu cầu SQL và mapper phù hợp. | Viết rõ SQL, alias và kiểu result. |
| Nghĩ mọi `sql()` cùng method là transaction | Không có ranh giới transaction ngầm. | `@Transactional`/`TransactionTemplate` đã cấu hình. |
| Tái dùng `StatementSpec` cho nhiều request | Có trạng thái bind không thích hợp dùng chung. | Tạo chain mới từ `client.sql(...)` cho mỗi thao tác. |
| Dùng `JdbcClient` cho batch/stored procedure phức tạp | Fluent facade chỉ tập trung thao tác phổ biến. | Dùng `JdbcTemplate`, `NamedParameterJdbcTemplate`, `SimpleJdbcInsert/Call` khi cần. |

## 21. Checklist khi review một chuỗi bắt đầu bằng `sql()`

1. **Đã xác định loại SQL chưa?** `SELECT` sẽ đi qua query resolver, `INSERT/UPDATE/DELETE` qua `update()`.
2. **SQL String có cố định về cấu trúc không?** Mọi dữ liệu người dùng phải bind; identifier động phải whitelist.
3. **Kiểu tham số có nhất quán không?** Một query chọn positional `?` hay named `:name`; không trộn tùy tiện.
4. **Có đủ tham số không?** `?` đủ số vị trí, `:name` đủ key/getter tương ứng và đúng chữ hoa/thường.
5. **Chỉ số explicit của `param(index,value)` đã tính từ 1 chưa?**
6. **Có nullable input không?** `Map.of` không chấp nhận null; có cần `Types` rõ ràng?
7. **Có `IN (:ids)` không?** Xử lý tập rỗng và giới hạn số tham số theo database.
8. **Có chọn đúng cách ánh xạ không?** `query(String.class)` cho một cột, `query(TaskView.class)` hoặc `query(mapper)` cho nhiều cột.
9. **Có chọn đúng cardinality không?** `single()`, `optional()` và `list()` là những hợp đồng khác nhau.
10. **Có order/pagination nếu truy vấn nhiều hàng không?** Tránh kết quả không ổn định và tải quá nhiều record.
11. **Có gọi terminal phù hợp chưa?** `sql()` riêng không làm việc ghi; `query(Class)` mới chuẩn bị cách map, còn resolver lấy kết quả.
12. **Có kiểm tra số hàng tác động từ `update()` khi nghiệp vụ cần exactly one không?**
13. **Giao dịch có được thiết lập bên ngoài chain không?** Không nhầm fluent syntax với transaction boundary.
14. **Đã kiểm thử trên database dialect thực tế chưa?** Kiểu dữ liệu, generated keys, tên cột/alias và SQL syntax có thể khác.
15. **Có cần tính năng ngoài phạm vi facade không?** Dùng template JDBC thấp hơn cho các case batch/callback/procedure chuyên sâu.

### Các ý chính cần nhớ

- **`JdbcClient.sql(String)` là điểm bắt đầu mọi thao tác fluent JDBC** của client và trả `JdbcClient.StatementSpec`.
- `sql()` chỉ **khai báo câu SQL**, không tự trả dữ liệu hay thực thi lệnh ghi.
- Sau `sql()`, bind theo `.param(...)`, `.params(...)` hoặc `.paramSource(...)`, rồi chọn đường thực thi.
- `query(Class/RowMapper).single()/optional()/list()` dành cho các hợp đồng đọc; `query().singleRow()/singleValue()/listOfRows()` dành cho kết quả không map sẵn vào class.
- **`update()`** thực thi INSERT/UPDATE/DELETE và trả số hàng tác động; generated keys cần API/driver thích hợp.
- `JdbcClient` dùng cơ chế Spring JDBC phía dưới, **không thay thế SQL, transaction, kiểm tra quyền, quản lý cursor hay quy tắc kết quả**.
- Thiết kế chain mỗi lần từ `sql(...)` mới, không chia sẻ `StatementSpec` có trạng thái cho nhiều thao tác đồng thời.

### Tài liệu tham khảo

- Spring Framework 6.1.14 — `JdbcClient` (interface, `create`, `sql`): https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.html
- Spring Framework 6.1.14 — `JdbcClient.StatementSpec` (bind, query, update): https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.StatementSpec.html
- Spring Framework 6.1.14 — `JdbcClient.MappedQuerySpec` (`single`, `list`, `optional`, `stream`): https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.MappedQuerySpec.html
- Spring Framework 6.1.14 — `JdbcClient.ResultQuerySpec`: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.ResultQuerySpec.html
- Spring Framework Reference — Unified JDBC Query/Update Operations: `JdbcClient`: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html

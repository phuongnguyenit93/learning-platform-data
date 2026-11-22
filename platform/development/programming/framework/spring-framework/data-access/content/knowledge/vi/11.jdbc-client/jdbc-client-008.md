# JdbcClient dựa trên hạ tầng JdbcTemplate thay vì thay đổi bản chất JDBC

## 1. Mục tiêu: phân biệt API tiện dụng và cơ chế thực thi

Trong Spring Framework, `JdbcClient` giúp viết truy vấn SQL theo cú pháp *fluent* (gọi chuỗi phương thức) thay vì truyền nhiều đối số vào các overload của `JdbcTemplate`. Ví dụ:

```java
long count = jdbcClient
    .sql("SELECT COUNT(*) FROM customer WHERE active = ?")
    .param(true)
    .query(Long.class)
    .single();
```

Mã ngắn gọn hơn, nhưng không có nghĩa Spring đã thay JDBC bằng một cơ chế dữ liệu mới. Truy vấn vẫn được gửi tới cơ sở dữ liệu qua `DataSource`, `Connection`, `PreparedStatement`, JDBC driver, và những quy tắc transaction/SQL quen thuộc.

**Thông điệp trung tâm:** `JdbcClient` là **lớp API thống nhất, thuận tiện** ở phía trên `JdbcTemplate` và `NamedParameterJdbcTemplate`. Nó **ủy quyền thực thi** cho các template này, thay vì tự phát minh giao thức kết nối, cơ chế giao dịch, hệ thống ánh xạ quan hệ hay engine SQL riêng.

Bài này sẽ trả lời:

1. `JdbcClient` nằm ở đâu trong các lớp Spring JDBC và từ phiên bản nào có thể dùng?
2. Một chuỗi `sql().param().query().list()` hoặc `update()` thực sự làm gì phía dưới?
3. Các quy tắc về parameter binding, `RowMapper`, xử lý kết quả, transaction, pool và ngoại lệ có thay đổi không?
4. Khi nào nên chọn `JdbcClient`, khi nào vẫn dùng `JdbcTemplate`, `NamedParameterJdbcTemplate` hoặc công cụ khác?
5. Cách kiểm chứng bằng ví dụ Java/Spring và một chương trình Java 17 độc lập mô phỏng cơ chế ủy quyền.

## 2. Bản đồ các tầng: JdbcClient không phải JDBC driver

Xem sơ đồ trách nhiệm:

```text
Ứng dụng / Service / Repository
            |
            | Fluent API:
            | .sql(...).param(...).query(...).list()
            v
org.springframework.jdbc.core.simple.JdbcClient
            |
            | Ủy quyền các thao tác thông dụng
            +------------------------------+
            |                              |
            v                              v
      JdbcTemplate             NamedParameterJdbcTemplate
      (tham số "?")             (tham số ":name")
            |                              |
            |                         xử lý tên thành
            |                         vị trí JDBC
            |                              |
            +-------------+----------------+
                          |
                          v
                    Spring JDBC core
            (tài nguyên, callback, dịch lỗi)
                          |
                          v
                       DataSource
                          |
                          v
                 JDBC Connection / Driver
                          |
                          v
                    Database Server
```

Những điểm phải phân biệt:

- **`JdbcClient`**: API fluent cho truy vấn/cập nhật JDBC phổ biến; từ Spring Framework **6.1**.
- **`JdbcTemplate`**: thành phần Spring JDBC làm công việc chuẩn bị/giải phóng tài nguyên, thực thi SQL, ánh xạ kết quả và dịch ngoại lệ.
- **`NamedParameterJdbcTemplate`**: hỗ trợ tham số đặt tên, chuyển `:id` thành dấu `?` và vị trí bind tương ứng rồi làm việc với template JDBC bên dưới.
- **`DataSource`**: nơi lấy `Connection`, có thể dùng connection pool như HikariCP.
- **JDBC driver**: triển khai giao thức với DB cụ thể, xử lý I/O, loại SQL và dữ liệu.
- **Database**: thực sự phân tích SQL, kiểm tra khóa/ràng buộc, chạy query và quyết định giao dịch.

`JdbcClient` **không** thay thế `DataSource`, **không** chạy SQL bằng Java thay cho DB, **không** tạo kết nối “phi JDBC”, và **không** tự trở thành một ORM như JPA/Hibernate.

### Từ phiên bản nào?

`org.springframework.jdbc.core.simple.JdbcClient` được giới thiệu trong **Spring Framework 6.1**. Nếu một dự án Spring Framework 5.x hoặc 6.0 không thấy lớp này thì không phải do thiếu import ngẫu nhiên: thư viện hiện tại chưa hỗ trợ API. Spring Boot sử dụng Spring Framework theo phiên bản được quản lý trong dependency BOM; phải kiểm tra phiên bản Spring Framework **thực tế** của ứng dụng, không suy đoán chỉ từ cú pháp trong một bài hướng dẫn.

Những ví dụ nền tảng trong bài dùng các khả năng đã có từ Spring Framework 6.1. Một vài tùy chọn cấu hình *trên từng statement* được bổ sung ở phiên bản mới hơn; nếu cần gọi API như vậy, phải đối chiếu Javadoc theo đúng phiên bản, tránh sao chép phương thức Spring 7.x vào ứng dụng Spring 6.1.

## 3. Vì sao cần JdbcClient khi JdbcTemplate đã hoạt động tốt?

`JdbcTemplate` đã cung cấp hầu hết nhu cầu phổ biến: `query`, `queryForObject`, `update`, `batchUpdate`, v.v. `NamedParameterJdbcTemplate` giải quyết câu SQL có nhiều tham số bằng tên.

Trước `JdbcClient`, một dự án có thể viết hai phong cách:

```java
// Tham số theo vị trí:
Long count1 = jdbcTemplate.queryForObject(
    "SELECT COUNT(*) FROM customer WHERE active = ?",
    Long.class,
    true
);

// Tham số theo tên:
Long count2 = namedParameterJdbcTemplate.queryForObject(
    "SELECT COUNT(*) FROM customer WHERE active = :active",
    new MapSqlParameterSource("active", true),
    Long.class
);
```

Khi đọc code, người học cần nhớ đúng overload và đúng thứ tự tham số cho từng template. `JdbcClient` đưa ra một mặt API thống nhất:

```java
// Một API, tham số kiểu "?":
Long count1 = jdbcClient.sql(
        "SELECT COUNT(*) FROM customer WHERE active = ?"
    )
    .param(true)
    .query(Long.class)
    .single();

// Vẫn một API, tham số tên ":active":
Long count2 = jdbcClient.sql(
        "SELECT COUNT(*) FROM customer WHERE active = :active"
    )
    .param("active", true)
    .query(Long.class)
    .single();
```

Hai đoạn code diễn đạt **cùng một loại thao tác JDBC**. Sự khác biệt nằm ở cách biểu diễn yêu cầu, không phải việc đổi transaction manager, thay database driver hoặc chuyển sang reactive I/O.

### Những gì được cải thiện

- Chuỗi lời gọi đọc gần với quy trình: **chọn SQL → bind tham số → chọn kiểu kết quả → lấy kết quả**.
- Tham số theo vị trí và theo tên nằm trong cùng một abstraction, dễ thống nhất phong cách repository.
- Có các điểm kết thúc rõ ràng: `list()`, `single()`, `optional()`, `stream()` và `update()`.
- Hỗ trợ ánh xạ bằng `RowMapper` hoặc class đích cho các truy vấn phổ biến.
- Có thể dùng `JdbcClient.create(existingJdbcTemplate)` để tái sử dụng cấu hình delegate hiện có.

### Những gì KHÔNG được “tự động giải quyết”

- SQL vẫn phải đúng cú pháp của DB và có index/thiết kế truy vấn phù hợp.
- Vẫn phải bind tham số đúng kiểu, tránh SQL injection.
- Vẫn phải xác định transaction và quyền truy cập.
- Vẫn gặp lỗi mạng, mất kết nối, khóa, deadlock, constraint violation.
- `JOIN` 1–N vẫn có thể nhân hàng; `list()` không tự gom cha–con.
- Query trả rất nhiều hàng vẫn tốn mạng, bộ nhớ và thời gian.
- Không mặc nhiên có batch, stored procedure, ORM entity tracking, lazy loading hoặc non-blocking execution.

## 4. Từ chuỗi fluent đến JDBC: phần nào làm việc lúc nào?

Ví dụ:

```java
List<Customer> customers = jdbcClient
    .sql("""
         SELECT id, name
         FROM customer
         WHERE tenant_id = :tenantId
         ORDER BY id
         """)
    .param("tenantId", tenantId)
    .query(CUSTOMER_MAPPER)
    .list();
```

Đây là mã **trong một repository Spring đã có `jdbcClient`, `tenantId`, `Customer` và `CUSTOMER_MAPPER`**, chưa phải chương trình độc lập.

Hiểu luồng xử lý ở mức khái niệm:

1. `sql(String)` tạo/khởi đầu đặc tả của một statement với SQL do ứng dụng cung cấp.
2. `param("tenantId", tenantId)` đăng ký tham số có tên cần bind. Nó không phải cách tự sửa cấu trúc SQL.
3. `query(CUSTOMER_MAPPER)` chỉ định cách đọc một hàng thành `Customer`.
4. `list()` là một **terminal operation** lấy toàn bộ kết quả theo mapper. Khi query thực thi, delegate thực hiện công việc qua Spring JDBC.
5. Hạ tầng bên dưới lấy `Connection` phù hợp, chuẩn bị JDBC statement, chuyển tham số tên thành placeholder theo vị trí nếu cần, bind giá trị, thực thi SQL, duyệt `ResultSet`, ánh xạ các hàng, đóng tài nguyên và giải phóng connection theo transaction.

Không nên nói rằng mỗi lời gọi `sql()` lập tức mở socket hoặc gửi query. API xây đặc tả trước và thao tác được thực thi khi gọi phương thức kết thúc phù hợp. Cũng không suy luận rằng `JdbcClient` tối ưu SQL tốt hơn DB chỉ vì có cú pháp fluent.

Trong Spring JDBC truyền thống, các công việc tương tự được thực hiện bởi `JdbcTemplate` và callback. `JdbcClient` chủ yếu **giảm mức độ lặp và làm rõ ý định**, còn hành vi DB vẫn theo cơ chế JDBC.

## 5. Tạo JdbcClient: tái sử dụng hạ tầng đang có

Có các factory quan trọng:

```java
JdbcClient clientA = JdbcClient.create(dataSource);

JdbcClient clientB = JdbcClient.create(jdbcTemplate);

JdbcClient clientC = JdbcClient.create(namedParameterJdbcTemplate);
```

Giả sử `dataSource` là `javax.sql.DataSource`, hai template đã được tạo và đúng các kiểu Spring JDBC. Các overload nói lên điều gì?

| Cách tạo | Ý nghĩa | Khi nên chọn |
| --- | --- | --- |
| `JdbcClient.create(dataSource)` | Tạo client hoạt động với nguồn dữ liệu chỉ định | Ví dụ độc lập của Spring JDBC hoặc cấu hình gọn |
| `JdbcClient.create(jdbcTemplate)` | Sử dụng delegate `JdbcOperations` hiện có | Khi đã cấu hình template, `DataSource`, ngoại lệ, timeout hoặc tùy chỉnh |
| `JdbcClient.create(namedParameterJdbcTemplate)` | Dùng `NamedParameterJdbcOperations` hiện có | Khi đã có template đặt tên cần tái sử dụng cấu hình |

Để bảo đảm cùng nguồn dữ liệu/cấu hình với ứng dụng đang dùng, phương án **tạo từ bean `JdbcTemplate` đã được Spring quản lý** thường rõ hơn việc tự khởi tạo thêm DataSource không cùng cấu hình.

Một cấu hình Spring gọn:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.simple.JdbcClient;

@Configuration
public class JdbcClientConfig {
    @Bean
    JdbcClient jdbcClient(JdbcTemplate jdbcTemplate) {
        return JdbcClient.create(jdbcTemplate);
    }
}
```

Ứng dụng cần có bean `JdbcTemplate` được cấu hình sẵn. Trong các môi trường Spring Boot, bean `JdbcClient` có thể đã được auto-configure tùy phiên bản và cấu hình; **không khai báo trùng một bean chỉ vì ví dụ trên tồn tại**. Nếu có nhiều `DataSource`, phải xác định rõ client nào kết nối tới DB nào, chẳng hạn qua qualifier thay vì mặc định “chỉ có một nguồn”.

Lưu ý: nếu ứng dụng có tùy chỉnh sâu ở template (ví dụ exception translator hoặc thiết lập statement), tạo `JdbcClient` từ đúng delegate được cấu hình giúp giữ đường thực thi liên quan. Không tự tạo một bộ template mới từ cùng URL rồi cho rằng mọi cấu hình giống nhau.

## 6. SQL và kiểu dữ liệu mẫu

Xét DB thử nghiệm H2 hoặc PostgreSQL với bảng khách hàng:

```sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    name VARCHAR(80) NOT NULL,
    active BOOLEAN NOT NULL,
    balance DECIMAL(12, 2) NOT NULL
);

INSERT INTO customer (id, tenant_id, name, active, balance) VALUES
    (1, 10, 'Lan',  TRUE,  120.00),
    (2, 10, 'Minh', FALSE,  70.00),
    (3, 10, 'Vy',   TRUE,   90.00),
    (4, 20, 'An',   TRUE,  150.00);
```

Giả sử repository thực hiện các chức năng:

- Lấy khách hàng theo ID và tenant.
- Liệt kê khách hàng active của một tenant.
- Đếm khách hàng active.
- Đổi tên khách hàng thuộc tenant được phép.

Các cột `tenant_id`, `active`, `balance` không được Spring tự tạo hay tự phát hiện quan hệ theo kiểu ORM. **Chính SQL quyết định cột nào được đọc và điều kiện lọc nào được áp dụng.**

Khi truy vấn `WHERE tenant_id=10 AND active=TRUE ORDER BY id`, kết quả có Lan và Vy; Minh không active và An thuộc tenant 20.

## 7. Tham số theo vị trí và theo tên: cùng nguyên tắc bind JDBC

### 7.1. Positional binding

```java
Optional<Customer> found = jdbcClient.sql(
        "SELECT id, name FROM customer WHERE tenant_id = ? AND id = ?"
    )
    .param(10L)
    .param(3L)
    .query((rs, rowNum) ->
        new Customer(rs.getLong("id"), rs.getString("name"))
    )
    .optional();
```

Giả sử `Customer` là `record Customer(long id, String name)`; kết quả là `Optional` chứa Vy. `param(value)` đăng ký các giá trị theo **thứ tự xuất hiện của dấu `?`**; cặp trên dùng tenant trước, ID sau. Thứ tự nhầm có thể không ném lỗi nếu cả hai đều là số, mà chỉ trả kết quả sai.

JDBC cho phép đánh số tham số từ **1**, vì vậy với overload `param(int jdbcIndex, Object value)`, phải dùng đúng chỉ số JDBC bắt đầu từ 1, không phải chỉ số mảng Java bắt đầu từ 0.

### 7.2. Named binding

```java
Optional<Customer> found = jdbcClient.sql(
        "SELECT id, name FROM customer " +
        "WHERE tenant_id = :tenantId AND id = :id"
    )
    .param("tenantId", 10L)
    .param("id", 3L)
    .query((rs, rowNum) ->
        new Customer(rs.getLong("id"), rs.getString("name"))
    )
    .optional();
```

`:tenantId` và `:id` là tên ở phía Spring; lớp named parameter phải chuyển chúng thành các vị trí JDBC phù hợp. JDBC driver không cần hiểu cú pháp `:tenantId` để hoạt động.

Với số lượng tham số lớn, tên thường rõ nghĩa hơn thứ tự. Tuy nhiên vẫn phải kiểm tra đúng tên trong SQL và khi bind. Không trộn hai kiểu bind trong cùng statement theo kiểu tùy tiện; nên giữ một phong cách rõ ràng cho từng SQL.

### 7.3. Tách dữ liệu khỏi cấu trúc SQL

Ví dụ không an toàn:

```java
String unsafeSql =
    "SELECT id FROM customer WHERE name = '" + userInput + "'";
```

Nối giá trị do người dùng nhập thẳng vào câu SQL có nguy cơ SQL injection hoặc sai cú pháp. Cách đúng:

```java
List<Long> ids = jdbcClient
    .sql("SELECT id FROM customer WHERE name = :name")
    .param("name", userInput)
    .query(Long.class)
    .list();
```

Câu `:name` là một **giá trị** được bind, không phải chỗ trống cho tên bảng, tên cột hoặc `ORDER BY`. Nếu tên cột được chọn động, cần dùng danh sách cột cho phép trong code; không mong `.param("column", userInput)` biến chuỗi thành identifier SQL an toàn.

### 7.4. NULL và SQL type

Nếu cần bind null với loại cột rõ ràng, `JdbcClient` có overload `param("name", value, sqlType)` hoặc `param(index, value, sqlType)`, dùng các hằng của `java.sql.Types`.

```java
jdbcClient.sql(
        "UPDATE customer SET name = :name WHERE id = :id"
    )
    .param("name", nullableName, java.sql.Types.VARCHAR)
    .param("id", 1L)
    .update();
```

Đây chỉ là minh họa API; schema mẫu khai báo `name NOT NULL` nên truyền null sẽ vi phạm ràng buộc DB và ném ngoại lệ. **Đặt SQL type không làm mất đi quy tắc NOT NULL**. Ngoài ra biểu thức `WHERE name = NULL` không khớp hàng có name null; nếu cần so khớp SQL NULL thì dùng `IS NULL` theo ngữ nghĩa DB.

## 8. Ánh xạ kết quả vẫn là câu chuyện RowMapper hoặc kiểu đích

Một truy vấn trả về `ResultSet`. `JdbcClient` có thể tiếp nhận `RowMapper<T>`:

```java
RowMapper<Customer> mapper = (rs, rowNum) ->
    new Customer(
        rs.getLong("id"),
        rs.getString("name")
    );

List<Customer> customers = jdbcClient.sql(
        "SELECT id, name FROM customer WHERE tenant_id = :tenantId ORDER BY id"
    )
    .param("tenantId", 10L)
    .query(mapper)
    .list();
```

Mỗi lần `RowMapper` nhận một hàng, nó chuyển hàng đó thành một đối tượng Java. `rowNum` là số thứ tự ánh xạ tính từ 0, **không phải ID DB**; `rs.next()` do hạ tầng template thực hiện trước khi gọi mapper.

`JdbcClient` cũng có `query(Customer.class).list()`, cho phép Spring ánh xạ theo cấu trúc class/record và tên cột khi tương thích. Ví dụ nếu record có hai component `id`, `name` và query trả đúng hai cột tương ứng:

```java
List<Customer> customers = jdbcClient.sql(
        "SELECT id, name FROM customer WHERE tenant_id = :tenantId ORDER BY id"
    )
    .param("tenantId", 10L)
    .query(Customer.class)
    .list();
```

Điều đó **không biến `JdbcClient` thành Hibernate**. Spring ánh xạ dữ liệu từ kết quả truy vấn vào Java object; nó không duy trì persistence context, không tracking thay đổi entity, không tự thực hiện lazy loading hoặc flush như JPA.

Khi mapping phức tạp hoặc cần xử lý SQL NULL, enum, JSON hay cột alias không đơn giản, **RowMapper tường minh** giúp điều khiển chuyển đổi và kiểm soát lỗi tốt hơn. Nếu `LEFT JOIN` một cha nhiều con, phép JOIN vẫn có thể trả nhiều hàng cùng khóa cha; `.list()` không tự gom cấu trúc cha–con. Khi cần gom toàn tập, `JdbcClient.StatementSpec.query(ResultSetExtractor<T>)` hoặc `JdbcTemplate` trực tiếp là lựa chọn phù hợp.

## 9. Kết quả list, single, optional và stream

| Dạng lời gọi | Ý nghĩa | Trường hợp cần chú ý |
| --- | --- | --- |
| `.query(mapper).list()` | Trả danh sách các đối tượng được ánh xạ | Khi 0 hàng → danh sách rỗng; có thể tốn RAM với tập lớn |
| `.query(Target.class).single()` | Cần **đúng một** đối tượng kết quả | 0 hoặc nhiều hơn 1 hàng → ngoại lệ kích thước kết quả theo Spring |
| `.query(Target.class).optional()` | 0 hoặc 1 đối tượng theo `Optional` | >1 hàng vẫn là lỗi; không phải “lấy hàng đầu nếu nhiều” |
| `.query(mapper).stream()` | Trả một `Stream` có thể đọc lười | **Phải đóng stream** sau khi dùng; vẫn giữ tài nguyên JDBC trong quá trình tiêu thụ |
| `.query(ResultSetExtractor<T>)` | Callback xử lý cả `ResultSet` | Tự xử lý `rs.next()`, tài nguyên thuộc template |
| `.query(RowCallbackHandler)` | Xử lý từng hàng bằng callback | Callback không trả `List<T>` tự động |
| `.update()` | Thực hiện `INSERT`, `UPDATE` hoặc `DELETE` | Trả `int` số hàng bị tác động; không phải ID tự sinh |

Dạng `single()` khác với truy vấn SQL có `LIMIT 1`: `single()` kiểm tra kỳ vọng của kết quả sau khi DB trả hàng, còn `LIMIT 1` giới hạn số hàng ở DB. Nếu bảng có hai bản ghi cùng khóa nghiệp vụ không unique, thêm `LIMIT 1` có thể che dấu dữ liệu không nhất quán; phải dùng đúng khóa/ràng buộc nếu muốn bảo đảm một kết quả.

`optional()` mô tả tốt trường hợp một khóa có thể chưa tồn tại:

```java
Optional<Customer> found = jdbcClient
    .sql("SELECT id, name FROM customer WHERE id = :id")
    .param("id", 999L)
    .query(Customer.class)
    .optional();
// Khi không có id=999: Optional.empty().
```

Còn nếu dùng `single()` cho ID 999, Spring báo lỗi vì không có đối tượng bắt buộc. Với hai hàng trả về, cả `single()` lẫn `optional()` đều không nên lặng lẽ bỏ qua hàng thừa.

### 9.1. Stream cần đóng

```java
try (var stream = jdbcClient.sql(
        "SELECT id, name FROM customer ORDER BY id"
    )
    .query(Customer.class)
    .stream()) {
    long count = stream
        .filter(c -> c.name().startsWith("L"))
        .count();
}
```

`Stream` này không phải “list được tạo sẵn rồi trả”: nó có thể gắn với tài nguyên truy vấn còn mở và phải được đóng bằng `try-with-resources`. Nó cũng **không bảo đảm** DB driver stream từng hàng với RAM hằng số; fetch size, transaction, driver và cách client tiêu thụ stream quyết định nhiều yếu tố. Đừng trả một stream đang dùng JDBC ra ngoài transaction/request không kiểm soát được vòng đời.

## 10. UPDATE vẫn là JDBC update, không phải lưu tự động entity

Ví dụ đổi tên:

```java
int affected = jdbcClient
    .sql("""
         UPDATE customer
         SET name = :name
         WHERE tenant_id = :tenantId AND id = :id
         """)
    .param("name", "Lan Anh")
    .param("tenantId", 10L)
    .param("id", 1L)
    .update();
```

`affected` là số hàng DB báo bị ảnh hưởng theo JDBC. Nếu `affected == 0`, có thể không có hàng khớp tenant/ID; không nên tự kết luận “đã cập nhật một khách hàng” chỉ vì không có exception. Nếu `affected > 1` trong thao tác dự kiến theo khóa duy nhất, phải điều tra câu SQL/schema và hợp đồng nghiệp vụ.

`JdbcClient` không tự theo dõi một record được tạo từ `SELECT` rồi tự sinh `UPDATE` khi bạn đổi trường Java. Muốn ghi, ứng dụng vẫn phát hành SQL `UPDATE`/`INSERT`/`DELETE` hoặc dùng công nghệ có ORM nếu thật sự cần hành vi entity tracking.

Với khóa tự sinh, `JdbcClient.StatementSpec` có các overload `update(KeyHolder)` nếu driver và phiên bản Spring hỗ trợ; phải kiểm tra schema auto-generated key và cách DB trả khóa. Một giá trị `affected` không phải khóa được sinh. Khi cần API quản lý khóa hoặc batch nâng cao, `SimpleJdbcInsert`/`JdbcTemplate` cũng là phương án thích hợp.

## 11. Một repository thực tế dùng lại JdbcTemplate hiện có

Ví dụ dưới đây được viết cho **Java 17+ và ứng dụng Spring Framework 6.1+** đã có bean `JdbcTemplate`, `DataSource` và bảng `customer` ở mục 6. Đây là mã tích hợp Spring; cần dependencies `spring-jdbc`, `spring-context` và DB driver tương ứng. **Không thể biên dịch độc lập chỉ với JDK.**

Tệp `CustomerJdbcClientRepository.java`:

```java
import java.util.List;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public final class CustomerJdbcClientRepository {
    public record Customer(long id, String name, boolean active) {}

    private static final RowMapper<Customer> MAPPER =
        (rs, rowNum) -> new Customer(
            rs.getLong("id"),
            rs.getString("name"),
            rs.getBoolean("active")
        );

    private final JdbcClient client;

    public CustomerJdbcClientRepository(JdbcTemplate template) {
        // Tái sử dụng JdbcTemplate của ứng dụng.
        this.client = JdbcClient.create(template);
    }

    public List<Customer> listActive(long tenantId) {
        return client.sql("""
                SELECT id, name, active
                FROM customer
                WHERE tenant_id = :tenantId AND active = :active
                ORDER BY id
                """)
            .param("tenantId", tenantId)
            .param("active", true)
            .query(MAPPER)
            .list();
    }

    public Optional<Customer> findById(long tenantId, long id) {
        return client.sql("""
                SELECT id, name, active
                FROM customer
                WHERE tenant_id = :tenantId AND id = :id
                """)
            .param("tenantId", tenantId)
            .param("id", id)
            .query(MAPPER)
            .optional();
    }

    public long countActive(long tenantId) {
        Long count = client.sql("""
                SELECT COUNT(*)
                FROM customer
                WHERE tenant_id = :tenantId AND active = :active
                """)
            .param("tenantId", tenantId)
            .param("active", true)
            .query(Long.class)
            .single();
        return count;
    }

    public int rename(long tenantId, long id, String newName) {
        return client.sql("""
                UPDATE customer
                SET name = :newName
                WHERE tenant_id = :tenantId AND id = :id
                """)
            .param("newName", newName)
            .param("tenantId", tenantId)
            .param("id", id)
            .update();
    }
}
```

### Kết quả trên dữ liệu mẫu

- `listActive(10)` trả hai record: Lan (ID 1) và Vy (ID 3), theo `ORDER BY id`.
- `listActive(20)` trả An (ID 4).
- `findById(10, 2)` trả `Optional` chứa Minh dù `active=false`, vì SQL chỉ lọc theo tenant và ID.
- `findById(10, 4)` trả `Optional.empty()`: An thuộc tenant 20, không được phép xuất hiện ở truy vấn tenant 10.
- `countActive(10)` trả `2`.
- `rename(10, 1, "Lan Anh")` trả số hàng bị ảnh hưởng `1` khi dữ liệu và quyền DB cho phép; phương thức sẽ **thực sự ghi dữ liệu**, nên chỉ chạy với DB thử hoặc trong quy trình nghiệp vụ được phép.

Điểm quan trọng: biến `client` giữ instance `JdbcClient` được cấu hình chung, nhưng **mỗi chuỗi `sql(...).param(...)` mô tả statement của lời gọi riêng**. Không lưu một đối tượng `StatementSpec` mutable/chưa hoàn tất vào field của singleton repository rồi cho nhiều request gọi `param(...)` cùng lúc.

Nếu muốn tái sử dụng bean `JdbcClient` do container cung cấp, có thể inject trực tiếp bean đó, miễn là đúng `DataSource` và đúng cấu hình mong muốn. Bài chọn `JdbcClient.create(template)` vì thể hiện rõ **quan hệ ủy quyền** mà chủ đề yêu cầu.

## 12. Transaction: fluent API không tự tạo một transaction nghiệp vụ mới

Giả sử một yêu cầu phải thực hiện **hai cập nhật** rồi mới thành công. Hai lệnh `client.sql(...).update()` riêng biệt **không tự động trở thành một đơn vị nguyên tử chỉ vì dùng cùng biến `JdbcClient`**.

Trong Spring, giao dịch do transaction infrastructure và transaction manager điều phối. Ví dụ mã dịch vụ minh họa:

```java
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerChangeService {
    private final JdbcClient client;

    public CustomerChangeService(JdbcClient client) {
        this.client = client;
    }

    @Transactional
    public void renameAndAudit(
            long tenantId, long customerId, String newName) {
        int count = client.sql("""
                UPDATE customer
                SET name = :name
                WHERE tenant_id = :tenantId AND id = :id
                """)
            .param("name", newName)
            .param("tenantId", tenantId)
            .param("id", customerId)
            .update();

        if (count != 1) {
            throw new IllegalStateException(
                "Expected exactly one customer update"
            );
        }

        client.sql("""
                INSERT INTO audit_log(tenant_id, customer_id, event_type)
                VALUES (:tenantId, :id, :event)
                """)
            .param("tenantId", tenantId)
            .param("id", customerId)
            .param("event", "RENAME")
            .update();
    }
}
```

**Điều kiện của ví dụ:** phải có bảng `audit_log` với các cột tương ứng và transaction manager liên kết đến đúng `DataSource`. Khi bean service được Spring gọi qua cơ chế `@Transactional` (không phải tự gọi method nội bộ bỏ qua proxy), hai câu SQL có thể tham gia cùng transaction. Nếu câu `INSERT` bị lỗi và ngoại lệ đi ra, Spring có thể rollback theo chính sách giao dịch. Nếu không có transaction, lệnh `UPDATE` đầu có thể đã được commit trước khi lệnh `INSERT` sau thất bại.

`JdbcClient` không làm các lệnh này nguyên tử thay cho `@Transactional`. Transaction còn phụ thuộc datasource/driver, isolation, constraint, khóa và exception semantics. Tình huống mất kết nối ở commit có thể làm trạng thái giao dịch chưa xác định; không retry lệnh ghi mù quáng. Với `@Transactional(readOnly = true)`, ý định read-only không mặc định khóa mọi lệnh ghi ở tất cả DB/driver.

**Cơ chế thực thi bên dưới vẫn tuân theo Spring `DataSourceUtils` và transaction-bound connection** như `JdbcTemplate`. Không tự gọi `connection.close()`, `commit()` hay `rollback()` trong mapper của `JdbcClient` để “chữa” transaction.

## 13. Kết nối và connection pool: vẫn qua DataSource

Cả `JdbcClient` và `JdbcTemplate` cuối cùng dùng một `DataSource` để lấy JDBC connection. Nếu `DataSource` được cấu hình với HikariCP:

- Pool vẫn kiểm soát số connection, thời gian chờ mượn, kiểm tra connection sống và thay thế connection hỏng.
- Đóng kết nối mượn từ pool thường là **trả quyền mượn về pool**, chứ không nhất thiết đóng socket mỗi lần.
- Query thực tế vẫn cần JDBC driver hỗ trợ loại DB, TLS, timeout và chuẩn dữ liệu.
- `JdbcClient` không tạo cơ chế pool thứ hai bên cạnh pool của DataSource đã dùng.
- Pool hết connection hoặc DB khởi động lại vẫn có thể làm query qua `JdbcClient` thất bại giống query qua `JdbcTemplate`.

Một lỗi hiệu năng thường bị bỏ sót: lấy nhiều kết quả bằng `.list()` có thể đưa toàn bộ kết quả vào RAM. Dù câu lệnh trông gọn, không nên viết `SELECT *` không có filter cho một bảng có hàng triệu dòng rồi kỳ vọng hạ tầng fluent tự phân trang hoặc stream. Hãy lọc SQL, giới hạn dữ liệu, phân trang chính xác và theo dõi số request chờ connection.

Việc chọn `JdbcClient` thay cho `JdbcTemplate` **không tự làm giảm số query, giảm round-trip DB, tạo index hay tránh N+1**. Tất cả vẫn phụ thuộc thiết kế SQL, cách gọi và kiến trúc.

## 14. Ngoại lệ: Spring DataAccessException vẫn là ranh giới quen thuộc

Trong JDBC thuần, các thao tác có thể ném checked `SQLException`. `JdbcTemplate` thực thi và dịch nhiều ngoại lệ JDBC sang hệ `org.springframework.dao.DataAccessException` (unchecked). `JdbcClient` **ủy quyền qua template**, nên lỗi dữ liệu không “biến mất”, cũng không tự đổi sang hệ ngoại lệ của JPA.

Ví dụ những loại tình huống phải phân biệt:

| Tình huống | Ý nghĩa | Cách tiếp cận |
| --- | --- | --- |
| Query lọc không có hàng và gọi `.list()` | Kết quả bình thường rỗng | Nhận danh sách rỗng |
| Query theo khóa không có hàng và gọi `.optional()` | Kết quả bình thường 0 hoặc 1 | Nhận `Optional.empty()` |
| Query kỳ vọng một hàng nhưng trả 0 hoặc nhiều hàng | Vi phạm hợp đồng kích thước kết quả | Xem `.single()`/`.optional()` và ràng buộc unique |
| SQL sai tên bảng/cột | Sai SQL/schema | Sửa SQL/migration, không retry vô hạn |
| Trùng khóa duy nhất khi `INSERT` | Vi phạm constraint | Xử lý nghiệp vụ và dữ liệu |
| Mất kết nối hoặc pool cạn | Sự cố hạ tầng | Xem driver/pool, trạng thái giao dịch và timeout |
| Deadlock/serialization failure | Xung đột transaction | Xem transaction boundaries, retry có điều kiện |

Không viết:

```java
try {
    return client.sql(sql).query(Customer.class).list();
} catch (Exception ex) {
    return List.of(); // Sai: che lỗi DB thành "không có dữ liệu".
}
```

Đây là **anti-pattern minh họa** với `client`, `sql`, `Customer` trong ngữ cảnh phương thức chưa hoàn chỉnh. Lỗi JDBC khác với kết quả rỗng hợp lệ; nuốt ngoại lệ có thể khiến caller nghĩ truy vấn thành công.

Nếu đã cấu hình `SQLExceptionTranslator` tùy chỉnh cho `JdbcTemplate`, dùng `JdbcClient.create(existingJdbcTemplate)` giúp truy vấn trên delegate đó đi qua hạ tầng dịch lỗi đang dùng. Điều này khác với việc tạo một template hoàn toàn mới với cấu hình mặc định rồi mong mọi hành vi được giữ nguyên.

## 15. Vì sao JdbcClient vẫn đồng bộ, không phải R2DBC?

Tên `JdbcClient` có thể khiến người học liên tưởng `WebClient` hoặc một HTTP client async. Nhưng `JdbcClient` là API thao tác **JDBC truyền thống**, dùng các lời gọi JDBC theo mô hình đồng bộ/chặn của driver JDBC.

```text
Thread xử lý request
    -> client.sql(...).query(...).list()
    -> JdbcTemplate / JDBC Driver
    -> chờ DB/driver thực hiện truy vấn
    -> nhận dữ liệu, ánh xạ, trả về caller
```

Đổi tên API từ `JdbcTemplate.query(...)` thành `JdbcClient.sql(...).query(...)` không biến cơ sở dữ liệu thành reactive source hay tự trả `Mono`/`Flux`. Công nghệ Spring R2DBC dùng abstraction/driver và cơ chế truy cập khác cho luồng reactive. Nếu cần mô hình non-blocking end-to-end, phải chọn hạ tầng thích hợp thay vì giả định `JdbcClient` tự cung cấp.

Tương tự, `JdbcClient` không phải HTTP client, không gửi REST request cho DB và không điều khiển connection pool kiểu WebClient.

## 16. Khi nào vẫn dùng JdbcTemplate hoặc NamedParameterJdbcTemplate trực tiếp?

Theo hướng dẫn Spring, `JdbcClient` là facade **linh hoạt nhưng đơn giản hóa** cho các thao tác query/update thông thường. Không nên ép mọi trường hợp vào fluent API.

| Công việc | Hướng ưu tiên | Lý do |
| --- | --- | --- |
| SELECT một hàng, danh sách, COUNT | `JdbcClient` | Cú pháp fluent gọn, rõ |
| UPDATE/INSERT/DELETE đơn giản | `JdbcClient` | `.update()` trả số hàng tác động |
| SQL có nhiều tham số đặt tên | `JdbcClient` hoặc `NamedParameterJdbcTemplate` | Hai API cùng dựa trên named binding |
| Batch insert/update phức tạp | `JdbcTemplate.batchUpdate(...)` hoặc API batch chuyên dụng khi phù hợp | Điều khiển lô và JDBC callback trực tiếp |
| Stored procedure/CallableStatement | `SimpleJdbcCall` hoặc `JdbcTemplate` | Hỗ trợ chuyên biệt, metadata và out parameters |
| Tạo khóa tự sinh nhiều kiểu DB | `SimpleJdbcInsert` hoặc API JDBC tương ứng | Cần hỗ trợ cụ thể của driver/DB và schema |
| Statement/callback JDBC tùy chỉnh sâu | `JdbcTemplate` trực tiếp | Cho phép truy cập nhiều overload/callback mức thấp |
| ORM entity graph, dirty checking | JPA/Hibernate nếu cần | Không phải năng lực tự có của `JdbcClient` |
| Reactive/non-blocking SQL | Spring R2DBC khi có driver hỗ trợ | Khác hạ tầng JDBC đồng bộ |

Một project hoàn toàn có thể dùng `JdbcClient` cho 90% truy vấn thông thường và sử dụng `JdbcTemplate` ở một repository chuyên biệt. **Không cần di chuyển toàn bộ mã cũ chỉ để đổi cách gọi API**; lợi ích cần được so với chi phí thay đổi và kiểm thử.

Một số phiên bản Spring mới bổ sung tùy chọn fluent sâu hơn cho từng statement. Nếu dự án chạy Spring Framework 6.1, đừng dùng cú pháp lấy từ Javadoc “current” của Spring 7 mà không kiểm tra `Since` của phương thức.

## 17. Hiệu năng: API ngắn hơn chưa chắc truy vấn nhanh hơn

So sánh hai phương thức về ý nghĩa:

```java
// Cách JdbcTemplate:
List<Long> ids1 = jdbcTemplate.query(
    "SELECT id FROM customer WHERE tenant_id = ? ORDER BY id",
    (rs, rowNum) -> rs.getLong("id"),
    10L
);

// Cách JdbcClient:
List<Long> ids2 = jdbcClient
    .sql("SELECT id FROM customer WHERE tenant_id = ? ORDER BY id")
    .param(10L)
    .query(Long.class)
    .list();
```

Nếu cùng `DataSource`, SQL và tham số, chúng nhằm thực hiện một truy vấn tương đương ở DB. Không có lý do để mặc định `JdbcClient` bỏ qua network, query planner hay I/O chỉ vì code viết ngắn hơn.

Muốn cải thiện hiệu năng thực tế, đo đạc:

1. **Số lượt SQL:** có phát sinh một query cho mỗi phần tử hay không? N+1 là vấn đề thiết kế, không phải lựa chọn API.
2. **Kế hoạch thực thi:** index, selective predicate, JOIN, GROUP BY, sorting và số hàng quét.
3. **Số hàng trả về:** đừng lấy 1 triệu hàng để dùng 10 hàng.
4. **Thời gian giữ connection:** map quá nặng, chờ I/O khác trong lúc stream hoặc transaction dài.
5. **Pool/driver timeout:** mượn connection, query timeout, socket timeout là những cơ chế khác nhau.
6. **Khả năng tái sử dụng câu SQL:** bind tham số phù hợp; đừng nối giá trị user input làm SQL mới liên tục.

Với dữ liệu lớn, có thể cân nhắc fetch size và streaming **nếu driver hỗ trợ**, nhưng phải kiểm tra phiên bản Spring. Không phải mọi tính năng cấu hình statement ở `JdbcTemplate` đều được expose y nguyên ở `JdbcClient` 6.1.

## 18. Quy tắc về quyền, tenant và tính đúng dữ liệu

Dù truy vấn viết bằng `JdbcClient` hay `JdbcTemplate`, SQL vẫn phải áp những điều kiện bảo vệ dữ liệu thuộc nghiệp vụ.

Ví dụ trong ứng dụng nhiều tenant, không được bỏ `tenant_id` chỉ vì có ID:

```java
// Sai nếu request chỉ được đọc tenant hiện tại:
jdbcClient.sql("SELECT id, name FROM customer WHERE id = :id")
    .param("id", id)
    .query(Customer.class)
    .optional();
```

Đúng với ranh giới tenant đã xác định:

```java
jdbcClient.sql(
        "SELECT id, name FROM customer " +
        "WHERE tenant_id = :tenantId AND id = :id"
    )
    .param("tenantId", tenantId)
    .param("id", id)
    .query(Customer.class)
    .optional();
```

`JdbcClient` không suy ra quyền xem dữ liệu từ field của Java record. Nó chỉ gửi SQL theo tham số bạn cung cấp. Kiểm soát phân quyền cần thiết kế ở controller/service/repository/DB tùy kiến trúc.

Tương tự, cập nhật `UPDATE customer SET ... WHERE id=:id` không tự bảo vệ bằng khóa lạc quan. Nếu cần optimistic locking, phải có cột version và điều kiện `WHERE id=:id AND version=:version`; kiểm tra `affected` để biết có cạnh tranh chỉnh sửa. Nếu cần khóa bi quan, phải dùng câu SQL và transaction hợp lệ theo dialect. Thay API không thay semantics đồng thời.

## 19. Unit test và integration test: nên kiểm tra điều gì?

Khi chuyển một phương thức repository từ `JdbcTemplate` sang `JdbcClient`, mục tiêu không phải chỉ xác nhận chuỗi fluent có thể biên dịch. Phải kiểm tra hành vi quan sát được vẫn như cũ:

| Test | Cần xác minh |
| --- | --- |
| 0 hàng | `list()` trả rỗng, `optional()` empty, `single()` xử lý đúng hợp đồng |
| 1 hàng | Mapper/record có cột và kiểu đúng |
| >1 hàng | `single()`/`optional()` không lặng lẽ bỏ hàng thừa |
| Tham số theo vị trí | Vị trí `?` và thứ tự `param(...)` đúng |
| Tham số có tên | Tên `:x` khớp với `param("x", ...)` |
| SQL NULL | Getter primitive và `rs.wasNull()` xử lý như mong muốn |
| Update 0/1/n hàng | Kiểm tra `affected`, không coi không lỗi là đã cập nhật |
| Transaction 2 câu SQL | Giao dịch rollback/commit theo cấu hình thực |
| Tenant khác | Không rò rỉ dữ liệu ngoài tenant |
| Ngoại lệ JDBC | Được Spring xử lý; không biến thành danh sách rỗng giả |
| Số query, độ trễ | Không tăng lượt SQL, round-trip hoặc quá tải pool |
| Large result/stream | Tài nguyên stream đóng đúng và bộ nhớ trong giới hạn |

**Unit test** tốt cho mapper, ràng buộc tham số và quy tắc xử lý kết quả. **Integration test** với DB tương thích mới chứng minh SQL thực thi, mapping đúng, transaction manager và ngoại lệ kết nối hoạt động như mong muốn.

Không dựa vào unit test mock của `JdbcClient.sql()` để kết luận transaction thực sự rollback: cần chạy với Spring transaction infrastructure và DB thử nghiệm. Nếu dự án có custom exception translator, kiểm thử rằng client tạo từ đúng template để nhận cấu hình tương ứng.

## 20. Java 17 độc lập: mô phỏng facade ủy quyền, không dùng Spring

Ví dụ dưới đây chỉ dùng JDK 17. Nó tạo:

- `MiniFluentClient`: lớp fluent mô phỏng `JdbcClient`.
- `SqlExecutor`: hợp đồng thực thi chung, tượng trưng cho `JdbcTemplate`.
- `FakeJdbcExecutor`: mô phỏng tầng JDBC và dữ liệu, **không kết nối DB thật**.

Nó không cố triển khai SQL parser hay JDBC driver; mục tiêu là phân biệt **API diễn đạt** và **delegate thực thi**. Trong ứng dụng Spring thật, `JdbcClient` và `JdbcTemplate` thay cho hai thành phần mô phỏng, còn SQL đi đến JDBC driver/DB.

Tạo tệp `JdbcFacadeMentalModelDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.NoSuchElementException;

public final class JdbcFacadeMentalModelDemo {
    record Customer(long id, String name) {}

    interface SqlExecutor {
        Customer queryOne(String sql, List<Object> bind);
    }

    static final class FakeJdbcExecutor implements SqlExecutor {
        @Override
        public Customer queryOne(String sql, List<Object> bind) {
            System.out.println("delegate: JDBC executor");
            System.out.println("sql: " + sql);
            System.out.println("bind: " + bind);
            long id = ((Number) bind.get(0)).longValue();
            if (id == 1L) {
                return new Customer(1L, "Lan");
            }
            if (id == 2L) {
                return new Customer(2L, "Minh");
            }
            throw new NoSuchElementException("No customer: " + id);
        }
    }

    static final class MiniFluentClient {
        private final SqlExecutor delegate;

        MiniFluentClient(SqlExecutor delegate) {
            this.delegate = delegate;
        }

        Statement sql(String text) {
            return new Statement(delegate, text);
        }
    }

    static final class Statement {
        private final SqlExecutor delegate;
        private final String sql;
        private final List<Object> params = new ArrayList<>();

        Statement(SqlExecutor delegate, String sql) {
            this.delegate = delegate;
            this.sql = sql;
        }

        Statement param(Object value) {
            params.add(value);
            return this;
        }

        Customer single() {
            return delegate.queryOne(sql, List.copyOf(params));
        }
    }

    public static void main(String[] args) {
        MiniFluentClient client = new MiniFluentClient(
            new FakeJdbcExecutor()
        );

        Customer value = client
            .sql("SELECT id, name FROM customer WHERE id = ?")
            .param(2L)
            .single();

        System.out.println("result: " + value);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 JdbcFacadeMentalModelDemo.java
java JdbcFacadeMentalModelDemo
```

Đầu ra chính xác:

```text
delegate: JDBC executor
sql: SELECT id, name FROM customer WHERE id = ?
bind: [2]
result: Customer[id=2, name=Minh]
```

Ở đây, `client.sql(...).param(...).single()` chỉ là cách cấu hình yêu cầu. Phương thức `single()` **ủy quyền** cho `SqlExecutor.queryOne(...)`; executor mô phỏng công việc bên dưới. Điều có thể xác minh từ stdout: cú pháp fluent không tự mang dữ liệu lên mà cần delegate làm phần thực thi.

**Không coi `MiniFluentClient` là API thật của Spring.** Nó không bảo đảm tài nguyên, dịch `SQLException`, transaction, mapping hoặc JDBC I/O; chỉ minh họa kiến trúc ủy quyền để tránh nhầm lẫn “API mới = DB protocol mới”.

## 21. Các hiểu nhầm điển hình

**Hiểu nhầm 1 — “JdbcClient thay hẳn JdbcTemplate”.**  
Không. `JdbcClient` **delegate** cho `JdbcTemplate` và `NamedParameterJdbcTemplate`. Với thao tác nâng cao, template trực tiếp vẫn có giá trị.

**Hiểu nhầm 2 — “Đổi sang JdbcClient thì hết SQL injection”.**  
Không tự động. Vẫn cần bind giá trị qua `param(...)`, không ghép chuỗi user input vào SQL, không dùng parameter thay identifier.

**Hiểu nhầm 3 — “JdbcClient biết quan hệ entity như JPA”.**  
Không. Dữ liệu đến từ SQL và mapper/record. Không có persistence context hoặc dirty checking tự có.

**Hiểu nhầm 4 — “Fluent chain tự tạo một transaction”.**  
Không. Transaction được điều phối bởi Spring transaction manager; nhiều lời gọi `update()` cần `@Transactional` nếu muốn một đơn vị nguyên tử.

**Hiểu nhầm 5 — “JdbcClient là non-blocking”.**  
Không. Nó vẫn chạy trên JDBC driver đồng bộ; R2DBC là hạ tầng khác.

**Hiểu nhầm 6 — “Cứ query(...).single() là lấy hàng đầu”.**  
Không. Đây là hợp đồng một kết quả; 0 hoặc >1 hàng là tình huống lỗi theo cơ chế Spring, không phải lệnh SQL chọn một hàng.

**Hiểu nhầm 7 — “Có thể không đóng stream vì đã dùng Spring”.**  
Không. `stream()` cần được đóng khi hoàn tất tiêu thụ để giải phóng tài nguyên liên quan.

**Hiểu nhầm 8 — “JdbcClient giảm số round-trip DB”.**  
Không tự động. Cùng câu SQL và tham số sẽ vẫn phải gửi đến DB; tối ưu query và kết nối là việc riêng.

**Hiểu nhầm 9 — “query(Customer.class) luôn map đúng mọi schema”.**  
Không. Cột, alias, tên field/record component và kiểu dữ liệu phải phù hợp; logic phức tạp cần mapper tường minh.

**Hiểu nhầm 10 — “Có JdbcClient nên không cần DataSource/pool”.**  
Không. `DataSource` vẫn cung cấp connection; pool/driver đảm nhiệm kết nối vật lý và timeout.

**Hiểu nhầm 11 — “JdbcClient là API của mọi Spring 6.x”.**  
Không. Nó bắt đầu từ **6.1**, không phải 6.0. Tùy chọn từng statement mới hơn có thể chỉ có từ Spring 7; luôn đối chiếu phiên bản.

**Hiểu nhầm 12 — “JdbcClient.create(dataSource) luôn tái dùng mọi tùy chỉnh của JdbcTemplate cũ”.**  
Không nhất thiết. Nếu cần tái sử dụng delegate đã có cấu hình, dùng factory nhận chính template đó.

## 22. Bài tập tự kiểm tra

**1. `JdbcClient` đứng trên hay dưới `JdbcTemplate`?**  
Đứng ở lớp API phía trên và **ủy quyền** thực thi. `JdbcTemplate` vẫn tham gia xử lý JDBC.

**2. JDBC driver có trực tiếp hiểu `:tenantId` không?**  
Không phải quy tắc chung. Spring hỗ trợ named parameters và chuyển sang binding JDBC theo vị trí.

**3. Hai lời gọi `update()` liên tiếp trên cùng client có tự động chung một transaction không?**  
Không. Cần transaction manager và ranh giới `@Transactional` phù hợp để bảo đảm atomicity theo DB.

**4. `query(Customer.class).list()` trả gì nếu SQL có 0 hàng?**  
Một danh sách rỗng. Nếu cần phân biệt 0 hoặc 1, có thể dùng `optional()` với SQL đúng hợp đồng.

**5. Có một triệu hàng; chỉ đổi sang `JdbcClient` có giảm memory và query time không?**  
Không tự động. Phải lọc/phân trang/tối ưu SQL, sử dụng stream hợp lệ và đo lường kết nối/bộ nhớ.

**6. Khi cần batch inserts và stored procedure, có nên loại bỏ mọi `JdbcTemplate`?**  
Không. Spring vẫn cung cấp template/các helper chuyên dụng cho thao tác nâng cao.

**7. `param("name", value)` có thay được tên bảng trong `FROM :name` không?**  
Không. Bind chỉ dành cho giá trị SQL, không thay cấu trúc identifier; phải quản lý tên bảng qua code đáng tin.

**8. `JdbcClient.create(existingJdbcTemplate)` hữu ích khi nào?**  
Khi ứng dụng cần sử dụng lại delegate hiện có cùng DataSource và các cấu hình custom, thay vì tạo thêm template mới độc lập.

**9. Vì sao `RowMapper` và JDBC NULL vẫn phải hiểu?**  
Vì `JdbcClient` vẫn lấy dữ liệu từ JDBC ResultSet; getter primitive có thể mất thông tin null, mapping có thể sai kiểu/tên.

**10. Có thể kết luận `JdbcClient` là JPA, R2DBC hoặc NoSQL driver không?**  
Không. Nó là facade cho **Spring JDBC** truyền thống.

## 23. Ghi nhớ

- **`JdbcClient` là facade fluent thống nhất cho các thao tác JDBC phổ biến, được giới thiệu từ Spring Framework 6.1.**
- **Thực thi vẫn dựa trên `JdbcTemplate`/`NamedParameterJdbcTemplate`**, sau đó đi qua `DataSource`, `Connection`, JDBC driver và DB.
- `sql(...).param(...).query(...).list()` làm code đọc dễ hơn, **không làm thay đổi bản chất SQL/JDBC**.
- Parameter binding vẫn bắt buộc, `RowMapper` và kiểu dữ liệu vẫn phải đúng; `single()`, `optional()` và `list()` có hợp đồng kết quả khác nhau.
- Transaction vẫn do Spring transaction manager điều phối, lỗi JDBC vẫn đi qua hạ tầng `DataAccessException`, connection pool vẫn thuộc `DataSource`.
- `JdbcClient` **không tự là ORM, không tự có reactive I/O, không tự sửa SQL chậm hoặc N+1**, không tự bảo đảm phân quyền.
- **Dùng `JdbcClient` cho query/update thông thường; dùng template/helper trực tiếp khi cần thao tác JDBC nâng cao**. Không cần viết lại code cũ đang ổn chỉ để đổi API.
- Tạo client từ **template đã được cấu hình** nếu muốn tái dùng đúng delegate và chiến lược xử lý của ứng dụng.

### Tài liệu tham khảo

- [Spring Framework Reference — Unified JDBC Query/Update Operations: JdbcClient](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html)
- [Spring Framework Javadoc — JdbcClient](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.html)
- [Spring Framework Javadoc — JdbcClient.StatementSpec](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.StatementSpec.html)
- [Spring Framework Javadoc — JdbcClient.MappedQuerySpec](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.MappedQuerySpec.html)
- [Spring Framework Reference — Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
- [Spring Framework Reference — Choosing an Approach for JDBC Database Access](https://docs.spring.io/spring-framework/reference/data-access/jdbc/choose-style.html)

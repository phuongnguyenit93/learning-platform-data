# Bind tham số để bảo vệ giá trị đầu vào khỏi SQL injection

Trong ứng dụng Spring Data Relational R2DBC, dữ liệu từ HTTP request, message, file import hoặc hệ thống bên ngoài thường được dùng trong câu SQL. Nếu ghép trực tiếp dữ liệu đó vào chuỗi SQL, kẻ tấn công có thể làm thay đổi cấu trúc câu lệnh và thực hiện SQL injection. Cách phòng vệ quan trọng nhất ở tầng truy cập dữ liệu là dùng parameter binding: viết câu SQL với placeholder, sau đó bind từng giá trị bằng API của Spring Data R2DBC hoặc R2DBC SPI.

Bind tham số tách câu lệnh SQL khỏi dữ liệu. Driver nhận câu lệnh và các giá trị riêng biệt, từ đó xử lý giá trị như dữ liệu của biểu thức thay vì phân tích nó như cú pháp SQL. Cách này giúp ngăn input biến thành toán tử, điều kiện, comment hoặc câu lệnh SQL bổ sung. Tuy nhiên, bind chỉ áp dụng cho giá trị; tên bảng, tên cột, từ khóa, hướng sắp xếp và các đoạn SQL động vẫn phải được kiểm soát bằng allowlist hoặc cấu trúc truy vấn an toàn.

## 1. SQL injection xảy ra như thế nào?

SQL injection xuất hiện khi ứng dụng ghép dữ liệu không đáng tin cậy vào SQL theo cách khiến dữ liệu được diễn giải thành cú pháp. Ví dụ một ứng dụng đăng nhập tạo câu lệnh bằng nối chuỗi:

```java
String sql = "SELECT id, username FROM app_user "
        + "WHERE username = '" + username + "' "
        + "AND password_hash = '" + passwordHash + "'";
```

Nếu người dùng gửi giá trị đặc biệt như:

```text
' OR '1'='1' --
```

phần input có thể đóng dấu nháy, thêm điều kiện luôn đúng và comment phần còn lại của câu lệnh. Câu SQL sau khi ghép có thể không còn mang ý nghĩa mà lập trình viên dự định.

Rủi ro không chỉ giới hạn ở form đăng nhập. Bất kỳ giá trị nào được nối vào SQL đều có thể trở thành điểm injection: từ khóa tìm kiếm, ID, email, bộ lọc, nội dung import, giá trị sort, phân trang hoặc dữ liệu đã lưu trước đó.

## 2. Vì sao parameter binding ngăn injection?

Với bind parameters, câu SQL giữ nguyên cấu trúc và giá trị được gửi riêng:

```java
return databaseClient.sql("""
        SELECT id, username
        FROM app_user
        WHERE username = :username
          AND password_hash = :passwordHash
        """)
        .bind("username", username)
        .bind("passwordHash", passwordHash)
        .map((row, metadata) -> new UserSummary(
                row.get("id", Long.class),
                row.get("username", String.class)))
        .one();
```

`username` và `passwordHash` được truyền như các giá trị. Nếu username chứa dấu nháy hoặc chuỗi `OR 1=1`, nó vẫn chỉ là nội dung của tham số. Driver không ghép nội dung đó thành cú pháp SQL mới.

Về mặt khái niệm:

```text
SQL template:  SELECT ... WHERE username = :username
Parameter:     username = "' OR '1'='1' --"

Database nhận cấu trúc câu lệnh và giá trị bind tách biệt.
Giá trị không thể tự đóng placeholder để thêm một mệnh đề SQL.
```

Driver có thể dùng prepared statement, protocol bind riêng hoặc cơ chế tương ứng với database. Không nên phụ thuộc vào việc driver có cache execution plan hay không để đánh giá an toàn; điều cần bảo đảm là giá trị được truyền bằng API bind chứ không được nối vào SQL text.

## 3. Quy tắc cốt lõi: bind mọi giá trị đầu vào

Mỗi giá trị đến từ bên ngoài cần được truyền qua placeholder thay vì nối chuỗi. Ví dụ:

| Dữ liệu | Cách an toàn |
| --- | --- |
| Username, email, tên | Bind vào điều kiện `WHERE` |
| ID hoặc mã tham chiếu | Bind vào `=`, `IN`, `JOIN` condition |
| Giá trị cập nhật | Bind vào `SET column = :value` |
| Ngày, số tiền, trạng thái | Bind với kiểu Java phù hợp |
| Từ khóa tìm kiếm | Bind vào `LIKE`/`ILIKE` hoặc full-text expression |
| `LIMIT`/`OFFSET` | Bind nếu driver/database và API hỗ trợ; đồng thời validate giới hạn |
| Danh sách ID | Dùng cơ chế mở rộng collection được hỗ trợ hoặc tạo placeholder an toàn |

Không nối giá trị vào SQL, kể cả khi đã gọi `trim()`, chuyển chữ hoa/thường, loại dấu nháy hoặc escape thủ công. Việc xử lý chuỗi không thay thế parameter binding.

## 4. Dùng `DatabaseClient` với named parameters

`DatabaseClient` của Spring Framework cung cấp API SQL reactive và hỗ trợ bind tham số có tên. Placeholder có dạng `:parameterName` trong SQL:

```java
public Mono<Customer> findByEmail(String email) {
    return databaseClient.sql("""
            SELECT id, email, display_name
            FROM customer
            WHERE email = :email
            """)
            .bind("email", email)
            .map((row, metadata) -> new Customer(
                    row.get("id", Long.class),
                    row.get("email", String.class),
                    row.get("display_name", String.class)))
            .one();
}
```

Named parameter giúp code dễ đọc vì bind theo tên thay vì phải nhớ vị trí. `DatabaseClient` chuyển named parameter sang marker mà R2DBC driver đang dùng. Ví dụ PostgreSQL thường dùng marker `$1`, `$2`; một số driver dùng `?` hoặc cú pháp khác. Khi dùng `DatabaseClient`, ứng dụng thường không cần tự viết marker vật lý của driver.

Các phương thức `bind(...)` trả về execute spec để tiếp tục cấu hình. Cần bind tất cả tham số bắt buộc trước khi gọi `fetch()`, `map()`, `rowsUpdated()` hoặc API thực thi tương ứng.

## 5. Bind trong `INSERT`, `UPDATE` và `DELETE`

Parameter binding áp dụng cho mọi loại câu lệnh DML, không chỉ truy vấn `SELECT`.

### INSERT

```java
public Mono<Long> insertCustomer(CreateCustomerCommand command) {
    return databaseClient.sql("""
            INSERT INTO customer (email, display_name)
            VALUES (:email, :displayName)
            """)
            .bind("email", command.email())
            .bind("displayName", command.displayName())
            .fetch()
            .rowsUpdated();
}
```

### UPDATE

```java
public Mono<Long> renameCustomer(Long customerId, String newName) {
    return databaseClient.sql("""
            UPDATE customer
            SET display_name = :displayName
            WHERE id = :id
            """)
            .bind("displayName", newName)
            .bind("id", customerId)
            .fetch()
            .rowsUpdated();
}
```

### DELETE

```java
public Mono<Long> deleteCustomer(Long customerId) {
    return databaseClient.sql("DELETE FROM customer WHERE id = :id")
            .bind("id", customerId)
            .fetch()
            .rowsUpdated();
}
```

Trong cả ba ví dụ, cấu trúc SQL được viết cố định; giá trị thay đổi được bind riêng. Không ghép `customerId`, tên hoặc email vào chuỗi SQL.

## 6. Dùng bind parameters trong Spring Data R2DBC repository

Derived query methods của Spring Data R2DBC tạo truy vấn dựa trên tên method và bind tham số theo metadata. Ví dụ:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findByEmail(String email);

    Flux<Customer> findByDisplayNameContaining(String keyword);

    Mono<Boolean> existsByEmail(String email);
}
```

Với derived query, không cần tự ghép SQL. Spring Data tạo điều kiện truy vấn và bind giá trị method argument theo cơ chế mapping.

Khi cần SQL tùy chỉnh, dùng `@Query` với named parameter:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    @Query("SELECT * FROM customer WHERE email = :email")
    Mono<Customer> findExactEmail(@Param("email") String email);

    @Modifying
    @Query("UPDATE customer SET active = :active WHERE id = :id")
    Mono<Integer> updateActive(
            @Param("id") Long id,
            @Param("active") boolean active);
}
```

`@Param` chỉ rõ tên method argument tương ứng placeholder. Hãy dùng package annotation của Spring Data repository query (`org.springframework.data.repository.query.Param`). Chữ ký update và kiểu trả về cần phù hợp phiên bản Spring Data R2DBC; với thao tác cần kiểm soát số hàng cập nhật, có thể chọn kiểu trả về được phiên bản hỗ trợ hoặc dùng `DatabaseClient`.

`@Query` không tự làm cho SQL text an toàn nếu lập trình viên đã nối input vào chuỗi annotation/runtime. Placeholder và bind method argument mới là phần tách giá trị khỏi SQL.

## 7. Dùng `R2dbcEntityTemplate` và Criteria

Khi truy vấn động theo nhiều điều kiện, `R2dbcEntityTemplate` cùng `Criteria` giúp biểu diễn điều kiện bằng API thay vì nối SQL:

```java
public Flux<Customer> searchCustomers(String email, Boolean active) {
    Criteria criteria = Criteria.empty();

    if (email != null && !email.isBlank()) {
        criteria = criteria.and("email").is(email);
    }

    if (active != null) {
        criteria = criteria.and("active").is(active);
    }

    return template.select(Customer.class)
            .matching(Query.query(criteria))
            .all();
}
```

Criteria lưu điều kiện và giá trị riêng; Spring Data chuyển thành query có bind parameters. Tên property được mapping sang cột theo metadata entity. Cần xử lý trường hợp không có điều kiện theo yêu cầu nghiệp vụ, ví dụ giới hạn kết quả hoặc từ chối truy vấn toàn bảng.

Không ghép input vào một `Criteria` dạng raw SQL. Dùng API có kiểu và kiểm soát các field mà client được phép lọc.

## 8. Bind trực tiếp bằng R2DBC SPI `Statement`

Khi dùng SPI trực tiếp, tạo `Statement` với SQL có marker theo driver rồi bind giá trị:

```java
Statement statement = connection.createStatement(
        "SELECT id, email FROM customer WHERE email = $1");

statement.bind(0, email);

Flux<CustomerSummary> customers = Flux.from(statement.execute())
        .concatMap(result -> Flux.from(result.map((row, metadata) ->
                new CustomerSummary(
                        row.get("id", Long.class),
                        row.get("email", String.class)))));
```

Trong ví dụ PostgreSQL, marker SQL `$1` được bind bằng index `0` trong API SPI. Chỉ số `bind` của `Statement` bắt đầu từ 0, còn marker hiển thị trong SQL của PostgreSQL bắt đầu từ `$1`. Với driver dùng `?`, SQL sẽ dùng placeholder theo driver đó; không sao chép cú pháp marker của PostgreSQL sang hệ quản trị khác.

R2DBC SPI có `bind(index, value)` và `bindNull(index, type)`. Không truyền null trực tiếp vào `bind`. Khi dùng `DatabaseClient`, Spring quản lý việc chuyển named parameter sang marker của driver; khi dùng SPI trực tiếp, ứng dụng phải tuân theo marker và kiểu dữ liệu của driver.

## 9. Bind tham số không áp dụng cho tên bảng hoặc tên cột

Placeholder đại diện cho một giá trị trong biểu thức SQL. Nó không thể thay thế tên bảng, tên cột, từ khóa hoặc toàn bộ đoạn SQL.

Ví dụ sai:

```java
databaseClient.sql("SELECT * FROM :tableName WHERE id = :id")
        .bind("tableName", tableName)
        .bind("id", id);
```

Database không diễn giải `:tableName` thành identifier. Nó là vị trí giá trị, trong khi `FROM` cần một tên bảng đã được phân tích cú pháp trước khi bind.

Tương tự, các ví dụ sau không hoạt động theo ý định:

```sql
SELECT * FROM customer ORDER BY :columnName
SELECT * FROM customer ORDER BY created_at :direction
SELECT * FROM :schemaName.customer
```

Bind `:columnName` trong `ORDER BY` thường chỉ tạo một biểu thức giá trị hằng, không chọn cột để sắp xếp. Không dùng bind để truyền `ASC`, `DESC`, tên schema, tên bảng, tên cột, toán tử hoặc keyword.

## 10. Allowlist cho identifier động

Nếu nghiệp vụ thật sự cần chọn cột sort, hãy ánh xạ input sang một tập identifier do ứng dụng định nghĩa. Không đưa chuỗi client gửi trực tiếp vào SQL.

```java
private static final Map<String, String> SORT_COLUMNS = Map.of(
        "createdAt", "created_at",
        "displayName", "display_name",
        "email", "email"
);

public Flux<Customer> findCustomers(String sortField, Sort.Direction direction) {
    String column = SORT_COLUMNS.get(sortField);
    if (column == null) {
        return Flux.error(new IllegalArgumentException("Unsupported sort field"));
    }

    String sqlDirection = direction == Sort.Direction.DESC ? "DESC" : "ASC";
    String sql = "SELECT id, email, display_name, created_at "
            + "FROM customer ORDER BY " + column + " " + sqlDirection;

    return databaseClient.sql(sql)
            .map((row, metadata) -> mapCustomer(row))
            .all();
}
```

Trong ví dụ, `column` chỉ có thể nhận một trong ba chuỗi SQL cố định từ map; `sqlDirection` chỉ có thể là `ASC` hoặc `DESC` do enum quyết định. Không có chuỗi identifier thô từ request được nối trực tiếp vào SQL.

Có thể dùng `switch` thay cho map. Điều quan trọng là allowlist được định nghĩa trong code và mọi giá trị không nằm trong danh sách đều bị từ chối hoặc chuyển sang default an toàn đã công bố.

Không dùng regex đơn giản như `^[a-zA-Z_]+$` làm biện pháp duy nhất. Một identifier hợp lệ về ký tự vẫn có thể là cột nhạy cảm hoặc không được phép sort. Allowlist kiểm soát cả cú pháp lẫn quyền truy cập ở mức ứng dụng.

## 11. Phân biệt identifier, keyword và value

| Thành phần SQL | Có thể bind như value? | Cách kiểm soát |
| --- | --- | --- |
| `WHERE email = :email` | Có | Bind giá trị email |
| `SET display_name = :name` | Có | Bind giá trị name |
| `LIMIT :limit` | Thường có, tùy driver/database | Bind và validate phạm vi |
| `ORDER BY :column` | Không chọn được identifier | Allowlist tên cột rồi ghép identifier cố định |
| `ASC`/`DESC` | Không | Enum/allowlist |
| Tên bảng/schema | Không | Cấu hình nội bộ hoặc allowlist |
| Toán tử như `=`, `LIKE`, `>` | Không | Chọn từ enum/nhánh code cố định |
| Đoạn `WHERE` tùy ý | Không | Xây bằng Criteria hoặc các fragment cố định |

Quy tắc: bind giá trị; kiểm soát identifier và cú pháp bằng code tin cậy.

## 12. Xây dựng WHERE động mà vẫn bind mọi giá trị

Một màn hình tìm kiếm có thể có nhiều bộ lọc tùy chọn. Có thể ghép các fragment SQL cố định và bind giá trị tương ứng:

```java
StringBuilder sql = new StringBuilder(
        "SELECT id, email, display_name, active FROM customer WHERE 1 = 1");

if (filter.email() != null) {
    sql.append(" AND email = :email");
}
if (filter.active() != null) {
    sql.append(" AND active = :active");
}

DatabaseClient.GenericExecuteSpec spec = databaseClient.sql(sql.toString());
if (filter.email() != null) {
    spec = spec.bind("email", filter.email());
}
if (filter.active() != null) {
    spec = spec.bind("active", filter.active());
}

return spec.map((row, metadata) -> mapCustomer(row)).all();
```

Nếu số điều kiện phức tạp, dùng `Criteria` hoặc một query builder có kiểu thường dễ bảo trì hơn tự dựng chuỗi. Dù dùng cách nào, không nối input thô vào fragment SQL.

## 13. Tìm kiếm với `LIKE` và ký tự wildcard

Bind parameter ngăn SQL injection nhưng không tự loại bỏ ý nghĩa wildcard của `LIKE`. Trong SQL, `%` đại diện cho chuỗi bất kỳ và `_` đại diện cho một ký tự. Nếu người dùng muốn tìm chính xác chuỗi có chứa `%` hoặc `_`, cần escape wildcard theo semantics của database.

Ví dụ dùng `!` làm escape character:

```java
private String escapeLikeLiteral(String value) {
    return value.replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_");
}

public Flux<Customer> searchName(String keyword) {
    String pattern = "%" + escapeLikeLiteral(keyword) + "%";

    return databaseClient.sql("""
            SELECT id, email, display_name
            FROM customer
            WHERE display_name LIKE :pattern ESCAPE '!'
            """)
            .bind("pattern", pattern)
            .map((row, metadata) -> mapCustomer(row))
            .all();
}
```

Giá trị vẫn được bind. Escape ở đây chỉ thay đổi semantics tìm kiếm để `%` và `_` được hiểu như ký tự literal; nó không phải biện pháp chống SQL injection. Cú pháp `ESCAPE` và hành vi collation/case sensitivity có thể khác giữa hệ quản trị. Với PostgreSQL, có thể cân nhắc `ILIKE` cho tìm kiếm không phân biệt hoa thường; kiểm tra cú pháp và index phù hợp với database mục tiêu.

## 14. Bind collection trong mệnh đề `IN`

Khi cần tìm nhiều ID, không nối danh sách bằng cách tạo chuỗi SQL từ input:

```java
// Không an toàn: danh sách ID được ghép vào SQL text.
String sql = "SELECT * FROM customer WHERE id IN (" + ids + ")";
```

`DatabaseClient` hỗ trợ named parameter expansion cho collection trong các phiên bản Spring Framework tương ứng:

```java
public Flux<Customer> findByIds(List<Long> ids) {
    if (ids.isEmpty()) {
        return Flux.empty();
    }

    return databaseClient.sql("""
            SELECT id, email, display_name
            FROM customer
            WHERE id IN (:ids)
            """)
            .bind("ids", ids)
            .map((row, metadata) -> mapCustomer(row))
            .all();
}
```

Spring `DatabaseClient` có thể mở rộng collection thành số lượng bind marker tương ứng. Đây là hành vi của lớp Spring named parameter expansion; không nên giả định R2DBC SPI `Statement.bind` thô nhận một `List` và mọi driver đều tự mở rộng nó.

Danh sách rỗng cần được xử lý trước khi tạo query vì `IN ()` không hợp lệ trên nhiều hệ quản trị và ý nghĩa nghiệp vụ có thể là không trả kết quả. Với danh sách rất lớn, chia batch hoặc dùng bảng tạm/array binding theo khả năng database và driver; tránh tạo câu SQL có hàng chục nghìn marker.

## 15. Phân trang và giới hạn kết quả

Các giá trị `LIMIT` và `OFFSET` thường là tham số có thể bind, tùy driver/database:

```java
public Flux<Customer> findPage(int pageSize, long offset) {
    int safeSize = Math.max(1, Math.min(pageSize, 200));
    long safeOffset = Math.max(0, offset);

    return databaseClient.sql("""
            SELECT id, email, display_name
            FROM customer
            ORDER BY id
            LIMIT :limit OFFSET :offset
            """)
            .bind("limit", safeSize)
            .bind("offset", safeOffset)
            .map((row, metadata) -> mapCustomer(row))
            .all();
}
```

Bind ngăn input thay đổi cú pháp SQL, nhưng validation vẫn cần thiết. Nếu client gửi page size cực lớn, query có thể tiêu thụ nhiều CPU, memory và connection dù không có injection. Giới hạn phạm vi và chọn thứ tự ổn định.

Với bảng lớn, cân nhắc keyset pagination thay vì offset sâu để tránh database phải bỏ qua nhiều hàng. Cursor/keyset vẫn cần bind mọi giá trị như `lastId` hoặc `lastCreatedAt`.

## 16. Bind giá trị null đúng cách

`DatabaseClient.bind(name, value)` không dùng để truyền Java `null`. Khi cần SQL `NULL`, dùng `bindNull(name, type)`:

```java
public Mono<Long> updatePhone(Long customerId, String phone) {
    DatabaseClient.GenericExecuteSpec spec = databaseClient.sql("""
            UPDATE customer
            SET phone_number = :phone
            WHERE id = :id
            """)
            .bind("id", customerId);

    if (phone == null) {
        spec = spec.bindNull("phone", String.class);
    } else {
        spec = spec.bind("phone", phone);
    }

    return spec.fetch().rowsUpdated();
}
```

Với R2DBC SPI trực tiếp, dùng `Statement.bindNull(index, type)`. Kiểu Java phải tương thích với kiểu SQL và codec của driver. Không truyền null vào `bind` thông thường.

Parameter binding cũng không tự quyết định ý nghĩa PATCH. Trong API PATCH, field bị thiếu có thể có nghĩa giữ nguyên, còn field hiện diện với null có thể có nghĩa xóa giá trị. DTO cần biểu diễn presence rõ ràng trước khi quyết định bind null hay bỏ cột khỏi câu lệnh.

## 17. Không dùng nối chuỗi để tạo literal SQL

Các cách sau vẫn nguy hiểm dù input đã được kiểm tra sơ bộ:

```java
String sql = "SELECT * FROM customer WHERE email = '" + email.trim() + "'";

String escaped = email.replace("'", "''");
String sql2 = "SELECT * FROM customer WHERE email = '" + escaped + "'";
```

Tự escape thủ công dễ sai do encoding, dấu nháy, kiểu dữ liệu, database dialect và ngữ cảnh SQL. Một chuỗi được escape đúng trong literal chuỗi có thể không an toàn trong identifier, JSON expression, LIKE pattern hoặc một đoạn SQL khác.

Hãy để driver bind giá trị. Nếu một thư viện yêu cầu cung cấp câu SQL và tham số riêng, dùng API tham số của thư viện đó. Không viết hàm `sanitizeSql()` chung rồi coi mọi chuỗi đã sanitize là an toàn để nối vào bất kỳ vị trí SQL nào.

## 18. Tránh second-order SQL injection

Second-order injection xảy ra khi dữ liệu được lưu an toàn lúc đầu nhưng về sau được lấy ra và ghép vào câu SQL động mà không bind. Ví dụ một tên báo cáo do người dùng cấu hình được lưu trong bảng, sau đó job nền dùng tên đó để tạo câu lệnh SQL:

```java
String configuredFilter = report.getFilterExpression();
String sql = "SELECT * FROM customer WHERE " + configuredFilter;
```

Dữ liệu có thể không gây hại khi insert, nhưng trở thành cú pháp SQL khi được dùng lại ở vị trí động. Mọi lần sử dụng dữ liệu không đáng tin cậy trong SQL đều phải được kiểm soát, kể cả dữ liệu đã nằm trong database.

Không lưu nguyên một đoạn SQL do người dùng gửi rồi thực thi sau này trừ khi sản phẩm thực sự cung cấp một ngôn ngữ truy vấn riêng được parse, giới hạn và kiểm soát quyền nghiêm ngặt. Với bộ lọc báo cáo, lưu cấu trúc có kiểu như field/operator/value rồi ánh xạ field/operator qua allowlist và bind value.

## 19. Dynamic query an toàn bằng enum và allowlist

Ví dụ bộ lọc cho phép so sánh giá trị bằng, lớn hơn hoặc nhỏ hơn. Không nhận toán tử SQL thô từ client:

```java
enum Comparison {
    EQUALS,
    GREATER_THAN,
    LESS_THAN
}

private String sqlOperator(Comparison comparison) {
    return switch (comparison) {
        case EQUALS -> "=";
        case GREATER_THAN -> ">";
        case LESS_THAN -> "<";
    };
}
```

Sau đó chỉ nối toán tử do switch trả về và bind giá trị:

```java
public Flux<Order> findByTotal(
        Comparison comparison,
        BigDecimal amount) {

    String operator = sqlOperator(comparison);
    String sql = "SELECT id, total FROM orders WHERE total "
            + operator + " :amount";

    return databaseClient.sql(sql)
            .bind("amount", amount)
            .map((row, metadata) -> new Order(
                    row.get("id", Long.class),
                    row.get("total", BigDecimal.class)))
            .all();
}
```

`operator` chỉ có thể nhận ba chuỗi hằng do ứng dụng kiểm soát. Giá trị `amount` luôn được bind. Nếu field cũng động, dùng một allowlist riêng cho tên cột.

## 20. Dùng `Sort` và `Pageable` an toàn

Spring Data có abstraction `Sort` và `Pageable`. Khi dùng repository/template API hỗ trợ chúng, framework xây dựng phần sort/page từ metadata và identifier theo cơ chế của nó. Tuy nhiên, dữ liệu sort đến từ request vẫn cần được giới hạn ở những property được phép.

Ví dụ tạo sort từ input qua allowlist:

```java
private static final Map<String, String> SORT_PROPERTY = Map.of(
        "name", "displayName",
        "created", "createdAt"
);

public Flux<Customer> findSorted(String requestedSort, boolean descending) {
    String property = SORT_PROPERTY.get(requestedSort);
    if (property == null) {
        return Flux.error(new IllegalArgumentException("Unsupported sort"));
    }

    Sort.Direction direction = descending
            ? Sort.Direction.DESC
            : Sort.Direction.ASC;

    return template.select(Customer.class)
            .matching(Query.query(Criteria.empty())
                    .sort(Sort.by(direction, property)))
            .all();
}
```

Không truyền trực tiếp một chuỗi sort tùy ý từ client vào SQL. Dùng property hợp lệ của entity và giới hạn số lượng/độ sâu phân trang. Nếu dùng `DatabaseClient` với SQL tùy chỉnh, dùng allowlist identifier như phần trên.

## 21. Stored procedure và function cũng cần bind

Khi gọi stored procedure hoặc function, giá trị đầu vào vẫn phải được truyền qua parameter binding. Không ghép input vào câu `CALL` hoặc function expression:

```java
return databaseClient.sql("SELECT * FROM search_customers(:keyword)")
        .bind("keyword", keyword)
        .map((row, metadata) -> mapCustomer(row))
        .all();
```

Parameter binding bảo vệ ranh giới giữa giá trị và câu lệnh gọi. Tuy nhiên, stored procedure bên trong cũng phải tránh dynamic SQL không an toàn. Nếu procedure dùng `EXECUTE`/dynamic SQL bằng cách nối input, injection vẫn có thể xảy ra ở phía database.

Kiểm tra code procedure, quyền thực thi và quyền của database role. Không coi việc gọi stored procedure là biện pháp tự động loại bỏ SQL injection.

## 22. Parameter binding không thay thế authorization

Một câu SQL có bind vẫn có thể cho phép người dùng đọc hoặc sửa dữ liệu mà họ không được phép truy cập nếu thiếu điều kiện ownership/tenant. Ví dụ:

```java
return databaseClient.sql("DELETE FROM orders WHERE id = :id")
        .bind("id", orderId)
        .fetch()
        .rowsUpdated();
```

Câu lệnh không có SQL injection, nhưng nếu không kiểm tra người dùng sở hữu order, họ có thể xóa order của người khác bằng cách đổi ID.

Nên đưa phạm vi quyền vào query:

```java
return databaseClient.sql("""
        DELETE FROM orders
        WHERE id = :id
          AND tenant_id = :tenantId
        """)
        .bind("id", orderId)
        .bind("tenantId", authenticatedTenantId)
        .fetch()
        .rowsUpdated();
```

`authenticatedTenantId` phải lấy từ principal/context đã xác thực ở server, không tin tenant ID do client tự khai báo. Bind chống injection; authorization và tenant isolation bảo vệ quyền truy cập. Cần cả hai.

## 23. Kiểm tra kiểu dữ liệu và giới hạn đầu vào

Bind parameter không tự validate dữ liệu nghiệp vụ. Giá trị quá dài, số âm, ngày sai phạm vi hoặc page size quá lớn vẫn có thể gây lỗi hoặc làm tăng tải.

Hãy validate trước khi bind:

- Chuỗi: độ dài tối đa, định dạng và quy tắc chuẩn hóa.
- Số: min/max, precision/scale và overflow.
- ID: phạm vi và quyền sở hữu.
- Ngày giờ: timezone và khoảng thời gian cho phép.
- Danh sách: số phần tử tối đa, loại bỏ duplicate nếu phù hợp.
- Pagination: giới hạn page size và offset.
- LIKE pattern: giới hạn độ dài và wildcard semantics.

Bind giúp giá trị không bị phân tích thành SQL, nhưng không ngăn một query hợp lệ tiêu thụ tài nguyên quá mức. Validation, authorization, rate limit và query limit vẫn cần thiết.

## 24. Logging và xử lý lỗi an toàn

Không log SQL parameter chứa password, token, thông tin thanh toán hoặc dữ liệu cá nhân ở dạng đầy đủ. Log SQL có thể hữu ích để debug, nhưng cần:

- Che hoặc bỏ giá trị nhạy cảm.
- Dùng query name/operation label thay vì ghi toàn bộ payload.
- Không gửi stack trace hoặc SQL nội bộ về HTTP client.
- Ghi correlation ID để liên kết request với database error.
- Phân biệt lỗi cú pháp, constraint, timeout và lỗi kết nối.
- Kiểm soát quyền truy cập log và thời gian lưu log.

Khi bind value, driver hoặc instrumentation có thể ghi lại tham số tùy cấu hình. Hãy kiểm tra log ở môi trường thật; không mặc định parameter binding tự động che dữ liệu nhạy cảm.

## 25. Kiểm thử chống SQL injection

Test nên chứng minh input độc hại được xem là dữ liệu literal và không làm thay đổi phạm vi query. Với một search method:

```java
@Test
void treatsSqlInjectionPayloadAsLiteralValue() {
    String payload = "' OR '1'='1' --";

    StepVerifier.create(customerRepository.findByEmail(payload))
            .verifyComplete();
}
```

Test này giả định database không có email đúng bằng payload. Kết quả rỗng chứng minh payload không biến thành điều kiện luôn đúng. Một test bổ sung nên lưu chuỗi đó vào một cột text (nếu schema cho phép), đọc lại và xác nhận nó được lưu nguyên văn.

Integration test nên dùng database/driver giống production, ví dụ PostgreSQL qua Testcontainers nếu ứng dụng triển khai PostgreSQL. Mock repository không chứng minh driver và SQL binding thực sự hoạt động như mong đợi.

Các ca test nên gồm:

1. Chuỗi có dấu nháy đơn và dấu nháy kép.
2. Payload có `OR 1=1`, comment marker `--` hoặc dấu chấm phẩy.
3. Chuỗi Unicode và ký tự tiếng Việt.
4. Giá trị null qua `bindNull`.
5. Danh sách `IN` rỗng, nhỏ và đạt giới hạn tối đa.
6. Sort field và direction hợp lệ/không hợp lệ.
7. LIKE chứa `%`, `_` và escape character.
8. ID hợp lệ nhưng thuộc tenant khác để kiểm tra authorization.
9. Dữ liệu đã lưu được tái sử dụng trong query động để phát hiện second-order injection.

## 26. Kiểm thử bằng `DatabaseClient` và `StepVerifier`

Ví dụ test kiểm tra payload không mở rộng kết quả:

```java
@Test
void searchDoesNotInterpretKeywordAsSql() {
    String malicious = "' OR '1'='1' --";

    StepVerifier.create(customerSearchService.findByEmail(malicious))
            .verifyComplete();
}
```

Với dữ liệu fixture có một customer hợp lệ:

```java
@Test
void exactSearchReturnsOnlyMatchingCustomer() {
    StepVerifier.create(customerSearchService.findByEmail("an@example.com"))
            .assertNext(customer ->
                    assertThat(customer.email()).isEqualTo("an@example.com"))
            .verifyComplete();
}
```

Để kiểm tra sort allowlist, truyền một identifier không hợp lệ như `email; DROP TABLE customer` và xác minh service từ chối trước khi query được thực thi. Đừng chỉ kiểm tra SQL cuối cùng trong unit test; integration test giúp xác minh hành vi với database thật.

## 27. Những lỗi thường gặp

| Lỗi | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Nối input vào SQL bằng `+` hoặc `StringBuilder` | Input có thể trở thành cú pháp SQL | Dùng placeholder và bind |
| Tự escape dấu nháy | Escape sai theo dialect/ngữ cảnh | Để driver bind value |
| Dùng placeholder cho tên bảng/cột | SQL không hợp lệ hoặc identifier không được kiểm soát | Dùng allowlist identifier |
| Bind chuỗi `ASC`/`DESC` | Không chọn được hướng sort như dự kiến | Dùng enum/allowlist và SQL fragment cố định |
| Cho client gửi toán tử SQL tùy ý | Có thể chèn cú pháp vào query động | Map enum sang toán tử cố định |
| Dùng `IN` bằng cách nối list | Injection và lỗi format | Dùng collection expansion hoặc bind marker an toàn |
| Không xử lý list rỗng | SQL `IN ()` có thể lỗi | Trả empty hoặc xử lý nhánh riêng |
| Dùng `bind(name, null)` | Lỗi bind | Dùng `bindNull(name, type)` |
| Cho rằng bind loại bỏ wildcard `LIKE` | Kết quả tìm kiếm rộng hơn mong đợi | Escape `%`/`_` nếu muốn tìm literal |
| Bind nhưng không validate page size | Query hợp lệ vẫn có thể gây tải lớn | Giới hạn kích thước và thời gian |
| Chỉ bind ở insert, nối dữ liệu đã lưu ở query sau | Second-order SQL injection | Bind mọi lần dùng dữ liệu trong SQL |
| Nghĩ bind thay thế authorization | Người dùng vẫn có thể truy cập dữ liệu không thuộc quyền | Thêm ownership/tenant condition và kiểm tra quyền |
| Log toàn bộ bind values | Lộ dữ liệu nhạy cảm | Mask/redact và giới hạn quyền log |
| Chỉ test bằng mock | Không xác minh driver/database thật | Integration test với database tương thích production |

## 28. Quy trình xây dựng truy vấn an toàn

Khi viết một query có dữ liệu đầu vào, thực hiện theo thứ tự:

1. Viết cấu trúc SQL cố định trước, đánh dấu mọi vị trí giá trị bằng placeholder.
2. Xác định dữ liệu nào là value và dữ liệu nào là identifier/keyword.
3. Bind mọi value bằng `DatabaseClient`, repository `@Query` hoặc `Statement.bind`.
4. Với identifier động, map input qua allowlist và chỉ ghép fragment do ứng dụng kiểm soát.
5. Với điều kiện động, dùng Criteria/query builder hoặc các fragment cố định; không ghép input thô.
6. Xử lý collection `IN`, danh sách rỗng và giới hạn số phần tử.
7. Dùng `bindNull` cho SQL NULL và kiểu Java phù hợp.
8. Validate định dạng, độ dài, phạm vi và quyền truy cập trước khi query.
9. Kiểm tra LIKE wildcard, sort, pagination và second-order injection.
10. Không log bind values nhạy cảm; xử lý lỗi database bằng response an toàn.
11. Viết unit test cho allowlist và integration test với payload injection trên database/driver thật.

## 29. Nguyên tắc thực hành

- Không nối giá trị đầu vào vào SQL text.
- Dùng `DatabaseClient.bind`, repository derived query/`@Query` hoặc R2DBC SPI `Statement.bind` cho mọi value.
- Dùng `bindNull` khi cần gửi SQL NULL; không truyền null vào `bind` thông thường.
- Nhớ rằng `DatabaseClient` named parameter được chuyển sang marker của driver; SPI trực tiếp phải dùng marker theo driver.
- Bind giá trị, không bind tên bảng, tên cột, keyword, toán tử hoặc đoạn SQL.
- Dùng allowlist cho sort field, direction, identifier và toán tử động.
- Dùng Criteria hoặc query builder có kiểu cho filter động.
- Dùng collection expansion được Spring hỗ trợ cho `IN`, xử lý list rỗng và giới hạn kích thước.
- Escape wildcard `LIKE` khi cần tìm literal; bind vẫn là lớp bảo vệ SQL injection.
- Validate dữ liệu và quyền truy cập; parameter binding không thay thế authorization hoặc rate limiting.
- Coi dữ liệu đã lưu cũng là không đáng tin cậy khi dùng trong câu SQL động.
- Không tự viết hàm escape/sanitize chuỗi để thay thế bind parameters.
- Không log password, token hoặc giá trị nhạy cảm trong bind parameters.
- Kiểm thử payload độc hại, identifier allowlist, null, collection và tenant isolation trên database tương thích production.

## 30. Kết luận

Parameter binding là biện pháp nền tảng để ngăn SQL injection trong Spring Data Relational R2DBC. Hãy viết SQL với placeholder và truyền dữ liệu qua `DatabaseClient.bind`, tham số repository `@Query` hoặc `Statement.bind` của R2DBC SPI. Driver nhận giá trị riêng với cấu trúc SQL, nên dấu nháy, comment marker hoặc chuỗi giống cú pháp SQL không thể tự biến thành một phần của câu lệnh.

Bind chỉ bảo vệ vị trí value. Tên bảng, tên cột, hướng sort, toán tử và fragment SQL động phải được kiểm soát bằng allowlist hoặc query builder có kiểu. Kết hợp bind với validation, authorization, giới hạn truy vấn, logging an toàn và integration test trên driver/database thực tế sẽ tạo lớp bảo vệ vững chắc cho các thao tác dữ liệu reactive.

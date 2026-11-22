# Tham số có tên, tham số theo vị trí và ký hiệu bind của trình điều khiển

Khi viết truy vấn trong Spring Data R2DBC, ứng dụng cần truyền giá trị vào câu SQL mà không ghép trực tiếp dữ liệu đầu vào thành chuỗi. Tham số bind giúp database xử lý giá trị như dữ liệu, giảm nguy cơ SQL injection và cho phép driver chuẩn bị câu lệnh theo cơ chế của nó.

Cần phân biệt ba khái niệm thường bị nhầm lẫn:

- **Tham số có tên (named parameter):** dùng tên dễ đọc như `:email` hoặc `:status`. Đây là cách viết tiện lợi của Spring Data/Spring DatabaseClient; framework chuyển nó thành bind marker mà driver hiểu.
- **Tham số theo vị trí (positional parameter):** giá trị được gắn với vị trí thứ nhất, thứ hai, thứ ba... trong câu lệnh. Cách viết placeholder phụ thuộc API và driver, thường gặp dấu `?` hoặc marker native.
- **Bind marker của driver:** ký hiệu thực sự mà R2DBC driver nhận trong SQL, ví dụ PostgreSQL dùng `$1`, `$2`, trong khi nhiều driver dùng `?`. Cú pháp không được quy định giống nhau cho mọi database.

Hiểu đúng ranh giới này giúp viết truy vấn có thể đọc, bảo trì và tương thích với database mục tiêu.

## 1. Vì sao cần bind tham số?

Không nên tạo SQL bằng cách nối giá trị do người dùng cung cấp:

```java
String sql = "SELECT * FROM customer WHERE email = '" + email + "'";
```

Nếu `email` chứa dấu nháy hoặc đoạn SQL độc hại, nội dung câu lệnh có thể bị thay đổi. Cách nối chuỗi còn khiến việc xử lý escaping và kiểu dữ liệu trở thành trách nhiệm của ứng dụng.

Thay vào đó, viết câu SQL với placeholder và truyền giá trị qua API bind:

```java
databaseClient.sql("SELECT * FROM customer WHERE email = :email")
    .bind("email", email)
    .map((row, metadata) -> row.get("id", Long.class))
    .one();
```

Ở đây, `:email` là tên tham số do Spring nhận diện. Giá trị `email` được truyền riêng qua `.bind(...)`, vì vậy nội dung giá trị không trở thành một phần cú pháp SQL.

Bind tham số cũng giúp driver xử lý kiểu dữ liệu, chuyển đổi giá trị và thực thi câu lệnh theo giao thức của database. Tuy nhiên, bind chỉ áp dụng cho **giá trị**. Tên bảng, tên cột, từ khóa SQL, hướng sắp xếp và toán tử không phải giá trị bind được.

## 2. Tham số có tên trong @Query

Với repository, Spring Data R2DBC cho phép dùng named parameter trong `@Query`. Cách này giúp câu SQL mô tả ý nghĩa của từng tham số trực tiếp.

```java
import java.util.UUID;
import org.springframework.data.r2dbc.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    @Query("""
        SELECT *
        FROM customer
        WHERE tenant_id = :tenantId
          AND email = :email
        """)
    Mono<Customer> findByTenantAndEmail(
        @Param("tenantId") UUID tenantId,
        @Param("email") String email
    );
}
```

Tên sau dấu `:` phải khớp với tên được khai báo trong `@Param`. Khi dùng `@Param`, tên tham số không phụ thuộc vào việc compiler có lưu metadata tên tham số trong bytecode hay không.

Trong một số cấu hình, Spring Data có thể lấy tên tham số trực tiếp từ metadata của Java nếu build bật tùy chọn giữ tên tham số (chẳng hạn `-parameters`). Dù vậy, với truy vấn có nhiều tham số hoặc khi muốn code rõ ràng giữa các môi trường build, `@Param` tường minh thường dễ đọc và ít phụ thuộc cấu hình hơn.

### 2.1 Named parameter trong DatabaseClient

`DatabaseClient` cũng hỗ trợ cú pháp tham số có tên:

```java
Mono<Integer> updateEmail(Long id, String newEmail) {
    return databaseClient.sql("""
            UPDATE customer
            SET email = :email
            WHERE id = :id
            """)
        .bind("email", newEmail)
        .bind("id", id)
        .fetch()
        .rowsUpdated();
}
```

Tên tham số trong SQL được liên kết với tên truyền vào `.bind(String, value)`. Có thể gọi bind theo thứ tự khác với thứ tự xuất hiện trong SQL vì framework ghép theo tên. Điều này giúp thay đổi định dạng truy vấn dễ hơn mà không phải tính lại chỉ số vị trí.

Named parameter là abstraction của Spring. Framework phân tích câu SQL, tạo bind marker phù hợp với dialect/driver và gắn giá trị vào đúng marker. Không nên giả định database nhận trực tiếp cú pháp `:email` như một phần của SQL chuẩn.

## 3. Tham số theo vị trí

Tham số theo vị trí liên kết giá trị với thứ tự placeholder. Cách này ngắn gọn với câu SQL nhỏ, nhưng người đọc phải theo dõi chính xác vị trí của từng giá trị.

Ví dụ với API `DatabaseClient` dùng placeholder theo cú pháp mà driver mục tiêu hỗ trợ:

```java
Mono<Integer> updateCustomer(Long id, String email) {
    return databaseClient.sql(
            "UPDATE customer SET email = $1 WHERE id = $2")
        .bind(0, email)
        .bind(1, id)
        .fetch()
        .rowsUpdated();
}
```

Đây là ví dụ theo marker native của PostgreSQL: `$1` là tham số đầu tiên, `$2` là tham số thứ hai. Trong API R2DBC, chỉ số truyền cho `.bind(int, value)` bắt đầu từ 0, vì vậy `$1` tương ứng `.bind(0, ...)` và `$2` tương ứng `.bind(1, ...)`.

Với driver sử dụng dấu `?`, SQL có thể có dạng:

```java
databaseClient.sql("UPDATE customer SET email = ? WHERE id = ?")
    .bind(0, email)
    .bind(1, id)
    .fetch()
    .rowsUpdated();
```

Không chuyển nguyên ví dụ PostgreSQL sang driver dùng `?` hoặc ngược lại. Khi dùng positional marker ở tầng `DatabaseClient`/R2DBC, cần viết đúng cú pháp mà dialect và driver của ứng dụng hỗ trợ.

## 4. Bind marker native của R2DBC driver

R2DBC SPI không áp đặt một ký hiệu placeholder duy nhất cho mọi driver. Driver phân tích câu SQL và cung cấp cơ chế bind phù hợp với database. Một số dạng thường gặp:

| Database/driver thường dùng | Marker trong SQL | Ví dụ vị trí |
|---|---|---|
| PostgreSQL R2DBC | `$1`, `$2`, `$3` | `WHERE id = $1 AND status = $2` |
| Một số driver khác | `?` hoặc marker riêng của driver | Kiểm tra cú pháp marker được hỗ trợ trong tài liệu driver/dialect |

Ví dụ sử dụng R2DBC SPI trực tiếp với PostgreSQL:

```java
ConnectionFactory connectionFactory = ...;

Mono<Integer> update = Mono.usingWhen(
    connectionFactory.create(),
    connection -> {
        Statement statement = connection.createStatement(
            "UPDATE customer SET email = $1 WHERE id = $2");

        statement.bind(0, newEmail);
        statement.bind(1, customerId);

        return Flux.from(statement.execute())
            .flatMap(result -> result.getRowsUpdated())
            .reduce(0L, Long::sum)
            .map(Long::intValue);
    },
    Connection::close,
    (connection, error) -> connection.close(),
    Connection::close
);
```

Đoạn mã minh họa việc dùng SPI trực tiếp: `createStatement` nhận SQL có marker native và `bind` nhận index bắt đầu từ 0. Trong code thực tế, cần bảo đảm connection được đóng an toàn cả khi publisher lỗi hoặc bị hủy; nên dùng helper quản lý connection hoặc Spring `DatabaseClient`/`R2dbcEntityTemplate` để tránh tự quản lý vòng đời connection ở mọi truy vấn.

Khi sử dụng Spring Data R2DBC ở tầng repository hoặc `DatabaseClient`, nên ưu tiên named parameter nếu muốn giảm phụ thuộc vào cú pháp marker của từng driver. Khi làm việc trực tiếp với `Connection.createStatement`, phải theo đúng marker native của driver.

## 5. Named parameter và positional parameter khác nhau thế nào?

| Tiêu chí | Named parameter | Positional parameter |
|---|---|---|
| Cách viết | `:tenantId`, `:status` | `?`, `$1`, `$2` hoặc marker native khác |
| Liên kết giá trị | Theo tên | Theo thứ tự/index |
| Khả năng đọc | Tên thể hiện ý nghĩa | Cần đối chiếu vị trí với lời gọi bind |
| Thay đổi thứ tự điều kiện | Thường không cần đổi cách bind theo tên | Có thể phải cập nhật index hoặc thứ tự bind |
| Phụ thuộc driver | Spring có thể chuyển named marker sang marker phù hợp | Cú pháp placeholder phụ thuộc driver/dialect |
| Phù hợp | Repository query, SQL nhiều điều kiện, query dễ bảo trì | SQL ngắn, API SPI trực tiếp hoặc khi cần kiểm soát marker cụ thể |

Hai cách đều truyền giá trị riêng với câu SQL và có thể an toàn nếu được bind đúng. Khác biệt chính nằm ở cách xác định tham số và mức độ phụ thuộc vào driver.

## 6. Bind giá trị NULL

Không thể bind `null` giống như một object thông thường vì framework/driver cần biết kiểu SQL dự kiến của tham số. Với `DatabaseClient`, dùng `bindNull` và chỉ rõ kiểu Java:

```java
databaseClient.sql("""
        UPDATE customer
        SET nickname = :nickname
        WHERE id = :id
        """)
    .bindNull("nickname", String.class)
    .bind("id", customerId)
    .fetch()
    .rowsUpdated();
```

Với positional binding:

```java
databaseClient.sql("UPDATE customer SET nickname = ? WHERE id = ?")
    .bindNull(0, String.class)
    .bind(1, customerId)
    .fetch()
    .rowsUpdated();
```

Kiểu truyền cho `bindNull` cần tương ứng với kiểu Java mà driver dùng để mã hóa giá trị cột. Ví dụ cột chuỗi có thể dùng `String.class`, cột số có thể dùng `Integer.class` hoặc `BigDecimal.class`. Nếu cột có kiểu native đặc thù, cần kiểm tra yêu cầu codec của driver.

Không dùng `column = NULL` để so sánh với giá trị null. Trong SQL, phải dùng `IS NULL` hoặc `IS NOT NULL`:

```sql
SELECT * FROM customer WHERE nickname IS NULL;
```

Nếu muốn một điều kiện tùy chọn có thể bỏ qua khi tham số null, hãy quyết định rõ logic trong code hoặc dùng biểu thức SQL có chủ đích. Biểu thức `(:nickname IS NULL OR nickname = :nickname)` khi nickname null sẽ không lọc theo cột đó; đây có thể là hành vi mong muốn trong tìm kiếm, nhưng cần đặc biệt thận trọng khi dùng với `UPDATE` hoặc `DELETE`.

## 7. Bind collection và điều kiện IN

Một truy vấn có thể cần tìm các hàng theo danh sách ID. Với named parameter trong Spring, một số API hỗ trợ mở rộng collection thành nhiều bind marker trong mệnh đề `IN`:

```java
databaseClient.sql("SELECT * FROM customer WHERE id IN (:ids)")
    .bind("ids", ids)
    .map((row, metadata) -> mapCustomer(row))
    .all();
```

Khả năng mở rộng collection và cách xử lý phụ thuộc API/phiên bản Spring, dialect và driver. Cần kiểm tra tài liệu của phiên bản đang dùng. Việc mở rộng danh sách thành nhiều marker khác với bind một SQL ARRAY duy nhất; hai cách có yêu cầu codec và cú pháp khác nhau.

Nếu danh sách rỗng, không tạo truy vấn `IN ()` theo giả định rằng mọi database đều chấp nhận. Hãy xử lý trước:

```java
if (ids == null || ids.isEmpty()) {
    return Flux.empty();
}
```

Với thao tác ghi hoặc xóa, không để danh sách rỗng vô tình chuyển thành một thao tác rộng hơn như `deleteAll()`. Cần xác định rõ semantics của danh sách rỗng theo nghiệp vụ.

## 8. Bind giá trị không bind được tên bảng hoặc cột

Placeholder chỉ đại diện cho giá trị. Các đoạn sau không hoạt động theo ý nghĩa mong muốn:

```sql
SELECT * FROM :tableName WHERE :columnName = :value
ORDER BY :sortColumn
```

Database hiểu placeholder là một giá trị biểu thức, không phải định danh SQL. Nếu cần chọn cột sắp xếp hoặc bảng theo request, hãy dùng allowlist trong code:

```java
String orderBy = switch (sortField) {
    case "createdAt" -> "created_at";
    case "email" -> "email";
    default -> throw new IllegalArgumentException("Unsupported sort field");
};

String direction = descending ? "DESC" : "ASC";

String sql = "SELECT id, email FROM customer ORDER BY "
    + orderBy + " " + direction;
```

Ở ví dụ này, các đoạn SQL động đến từ lựa chọn đã kiểm soát trong code. `sortField` của người dùng không được nối trực tiếp. Nếu có thể, dùng API query builder hoặc `Sort` của Spring Data để tránh tự ghép identifier.

## 9. Tránh lỗi thường gặp khi bind

### 9.1 Sai tên tham số

SQL dùng `:customerId` nhưng code gọi `.bind("id", value)` sẽ không khớp. Với `@Query`, tên trong `@Param` phải giống tên placeholder. Nên thống nhất cách viết camelCase hoặc tên rõ nghĩa và kiểm tra lỗi khi chạy truy vấn.

### 9.2 Sai thứ tự positional binding

Với SQL `SET email = ? WHERE id = ?`, bind index 0 là email, index 1 là ID. Nếu đảo ngược, database có thể báo lỗi kiểu dữ liệu hoặc cập nhật nhầm dữ liệu nếu hai kiểu tương thích. Hãy đặt tên biến và bind ngay cạnh vị trí placeholder để dễ kiểm tra.

### 9.3 Trộn cú pháp marker của nhiều driver

SQL dùng `$1` của PostgreSQL có thể không chạy trên driver chỉ nhận `?`. Nếu ứng dụng cần hỗ trợ nhiều database, ưu tiên named parameter cùng abstraction có dialect hỗ trợ hoặc tách truy vấn theo dialect. Không thay thế marker bằng tìm/replace chuỗi đơn giản vì SQL có thể chứa dấu marker trong literal hoặc comment.

### 9.4 Thiếu kiểu cho null

Gọi `.bind("note", null)` không cung cấp đủ thông tin cho driver. Dùng `.bindNull("note", String.class)` hoặc overload theo index và kiểu tương ứng.

### 9.5 Dùng sai kiểu Java

Giá trị `Long` bind vào cột UUID hoặc `String` bind vào cột native enum có thể không được driver chấp nhận. Hãy chọn kiểu Java phù hợp với codec và schema, hoặc đăng ký converter.

### 9.6 Không khớp số lượng placeholder

Mỗi marker phải có giá trị được bind. Thiếu bind hoặc bind dư index thường làm câu lệnh thất bại trước khi thực thi. Khi tạo SQL động, cần tạo danh sách placeholder và bind tương ứng trong cùng một nhánh logic.

## 10. Ví dụ repository kết hợp nhiều named parameter

Truy vấn có nhiều điều kiện thường dễ bảo trì hơn khi dùng tên:

```java
public interface OrderRepository
        extends ReactiveCrudRepository<PurchaseOrder, Long> {

    @Query("""
        SELECT *
        FROM purchase_order
        WHERE tenant_id = :tenantId
          AND status = :status
          AND created_at >= :fromTime
          AND created_at < :toTime
        ORDER BY created_at DESC
        """)
    Flux<PurchaseOrder> findOrders(
        @Param("tenantId") UUID tenantId,
        @Param("status") String status,
        @Param("fromTime") Instant fromTime,
        @Param("toTime") Instant toTime
    );
}
```

Mỗi tham số được đặt tên theo ý nghĩa, và điều kiện khoảng thời gian dùng cận dưới bao gồm (`>=`) cùng cận trên không bao gồm (`<`). Cách viết này thường thuận tiện cho phân trang theo thời gian hoặc chia khoảng dữ liệu mà không bị trùng ở ranh giới.

Nếu cần phân trang, có thể dùng API phân trang mà repository hỗ trợ hoặc viết câu SQL với limit/offset theo dialect. Tham số limit/offset cũng là giá trị và nên bind, trong khi tên cột trong `ORDER BY` cần được kiểm soát bằng allowlist hoặc API `Sort`.

## 11. Chọn cách bind theo tầng truy cập dữ liệu

| Tầng sử dụng | Cách viết nên cân nhắc |
|---|---|
| Spring Data repository với `@Query` | Named parameter `:name` và `@Param` để thể hiện rõ liên kết. |
| `DatabaseClient` | Named parameter và `.bind("name", value)` để giảm phụ thuộc marker native. |
| `DatabaseClient` cần positional binding | Dùng index 0-based và marker được dialect/driver hỗ trợ. |
| R2DBC SPI trực tiếp | Dùng native marker của driver trong `createStatement`, bind theo index hoặc tên nếu driver hỗ trợ. |
| Ứng dụng đa database | Ưu tiên abstraction theo dialect; kiểm thử query trên từng driver mục tiêu. |

Với phần lớn truy vấn nghiệp vụ, named parameter làm code dễ đọc và ít nhầm thứ tự. Positional binding vẫn hữu ích ở tầng thấp hoặc với SQL ngắn, nhưng phải gắn chặt với cú pháp của driver.

## 12. Quy trình kiểm tra truy vấn có tham số

Khi thêm một truy vấn mới, nên kiểm tra theo các bước sau:

1. Xác định database và R2DBC driver mà ứng dụng thực sự sử dụng.
2. Chọn named parameter của Spring hoặc native positional marker của driver.
3. Đảm bảo tên hoặc index bind khớp chính xác với placeholder.
4. Chọn kiểu Java phù hợp với kiểu cột và codec của driver.
5. Xử lý `NULL` bằng `bindNull` với kiểu rõ ràng.
6. Xử lý collection rỗng và số lượng phần tử lớn.
7. Không bind identifier; dùng allowlist cho tên cột, bảng và hướng sắp xếp động.
8. Chạy truy vấn trên database/driver mục tiêu với giá trị bình thường, null, ký tự đặc biệt và dữ liệu biên.

Named parameter, positional parameter và bind marker native đều phục vụ việc truyền giá trị an toàn vào câu SQL. Spring Data R2DBC và `DatabaseClient` cung cấp abstraction để giảm sự phụ thuộc vào marker của từng driver, trong khi R2DBC SPI trực tiếp yêu cầu tuân theo cú pháp mà driver triển khai. Chọn đúng tầng abstraction, bind đúng kiểu và kiểm soát phần SQL động giúp truy vấn ổn định, dễ bảo trì và an toàn hơn.

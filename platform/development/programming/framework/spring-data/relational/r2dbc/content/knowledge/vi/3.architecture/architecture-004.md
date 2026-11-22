# Vai trò của DatabaseClient trong Spring R2DBC

`DatabaseClient` là API truy cập SQL ở mức thấp của Spring Framework dành cho R2DBC. Nó cung cấp một cách thống nhất để tạo câu lệnh, bind tham số, thực thi SQL bất đồng bộ và đọc kết quả dưới dạng các publisher reactive. Trong kiến trúc Spring Data R2DBC, `DatabaseClient` là một thành phần nền tảng: `R2dbcEntityTemplate` sử dụng nó để thực hiện các thao tác có ánh xạ entity, còn repository cung cấp lớp trừu tượng cao hơn cho các nghiệp vụ CRUD.

Khi làm việc trực tiếp với `DatabaseClient`, lập trình viên chủ động viết SQL và quyết định cách ánh xạ từng hàng kết quả sang kiểu dữ liệu của ứng dụng. Đổi lại, ứng dụng có quyền kiểm soát rõ ràng đối với phép chiếu cột, join, truy vấn đặc thù của database, cập nhật hàng loạt và các câu lệnh mà repository method khó biểu đạt.

## 1. DatabaseClient nằm ở đâu trong kiến trúc?

Spring R2DBC tổ chức các lớp truy cập dữ liệu từ API SQL cấp thấp đến các abstraction hướng entity. Một luồng điển hình có thể hình dung như sau:

```text
Application service
        |
        +-----------------------------+
        |                             |
        v                             v
Spring Data repository          DatabaseClient
        |                             |
        v                             |
R2dbcEntityTemplate                  |
        |                             |
        +-------------+---------------+
                      |
                      v
               R2DBC SPI
                      |
                      v
                R2DBC driver
                      |
                      v
                 Database
```

Sơ đồ nhấn mạnh hai cách tiếp cận ở tầng ứng dụng:

- **Repository / `R2dbcEntityTemplate`:** làm việc với entity, metadata ánh xạ và các thao tác theo mô hình Spring Data.
- **`DatabaseClient`:** làm việc trực tiếp với SQL, tham số, hàng và metadata kết quả. Ứng dụng tự định nghĩa cách chuyển hàng thành DTO hoặc kiểu dữ liệu mong muốn.

`DatabaseClient` sử dụng `ConnectionFactory` của R2DBC để tiếp cận database. Nó xử lý những chi tiết lặp lại của việc thực thi SQL và tích hợp với cơ chế quản lý connection, transaction và xử lý lỗi của Spring. Nó không phải là một JDBC `JdbcTemplate` chạy trên thread chặn: API trả về `Mono` hoặc `Flux`, phù hợp với mô hình reactive của R2DBC.

### Trách nhiệm chính

`DatabaseClient` tập trung vào các trách nhiệm sau:

1. Nhận câu SQL và tạo một thao tác thực thi thông qua R2DBC.
2. Bind giá trị tham số vào các bind marker được driver hỗ trợ.
3. Thực thi câu lệnh theo mô hình reactive.
4. Đọc `Row` và `RowMetadata`, sau đó cho phép ứng dụng ánh xạ thành kiểu kết quả.
5. Trả kết quả dưới dạng `Mono<T>`, `Flux<T>` hoặc số hàng bị ảnh hưởng.
6. Tích hợp với hạ tầng Spring như exception translation và reactive transaction management.

`DatabaseClient` không tự quyết định nghiệp vụ, không suy luận câu SQL từ tên phương thức và không tự thiết kế schema. Câu truy vấn, điều kiện lọc, thứ tự sắp xếp và cách ánh xạ vẫn thuộc trách nhiệm của ứng dụng khi sử dụng API này.

## 2. Khi nào nên dùng DatabaseClient?

Hãy dùng `DatabaseClient` khi cần kiểm soát SQL trực tiếp nhưng vẫn muốn giữ trải nghiệm reactive và tích hợp Spring.

Các tình huống thường gặp:

- Truy vấn join nhiều bảng và ánh xạ kết quả sang DTO riêng.
- Dùng CTE, window function, subquery, biểu thức hoặc cú pháp đặc thù của hệ quản trị.
- Truy vấn projection chỉ lấy một số cột cần thiết thay vì tải toàn bộ entity.
- Thực hiện câu lệnh cập nhật hoặc xóa có điều kiện phức tạp.
- Thực thi truy vấn thống kê, báo cáo hoặc tổng hợp dữ liệu.
- Cần SQL rõ ràng để kiểm soát execution plan và tối ưu hiệu năng.
- Có câu lệnh mà repository query derivation hoặc API thao tác entity không diễn đạt thuận tiện.

Nếu nghiệp vụ chỉ cần CRUD thông thường trên một aggregate, repository thường dễ đọc và dễ bảo trì hơn. Nếu cần thao tác theo entity nhưng vẫn muốn API truy vấn linh hoạt, `R2dbcEntityTemplate` là lựa chọn trung gian. Không nên chuyển tất cả thao tác CRUD sang SQL thủ công chỉ vì `DatabaseClient` có thể thực hiện chúng.

## 3. Khởi tạo và cấu hình DatabaseClient

`DatabaseClient` cần một `ConnectionFactory`. Trong ứng dụng Spring, `ConnectionFactory` thường được cấu hình từ driver R2DBC và thông tin kết nối của database.

Có thể tạo client trực tiếp:

```java
import io.r2dbc.spi.ConnectionFactory;
import org.springframework.r2dbc.core.DatabaseClient;

DatabaseClient databaseClient = DatabaseClient.create(connectionFactory);
```

Hoặc khai báo thành bean trong cấu hình Spring khi ứng dụng cần tự quản lý bean này:

```java
@Configuration
public class R2dbcConfiguration {

    @Bean
    DatabaseClient databaseClient(ConnectionFactory connectionFactory) {
        return DatabaseClient.create(connectionFactory);
    }
}
```

Trong ứng dụng Spring Boot có starter R2DBC, hãy tận dụng cấu hình `ConnectionFactory` và các bean do auto-configuration cung cấp nếu đã có. Tránh tạo nhiều `ConnectionFactory` hoặc `DatabaseClient` độc lập cho cùng một database nếu không có lý do kiến trúc rõ ràng. Đặc biệt, client dùng trong transaction cần gắn với cùng `ConnectionFactory` mà reactive transaction manager quản lý.

Builder cũng có thể được dùng khi cần tùy chỉnh cách tạo client:

```java
DatabaseClient databaseClient = DatabaseClient.builder()
    .connectionFactory(connectionFactory)
    .build();
```

Chi tiết builder và các tùy chọn có thể thay đổi theo phiên bản Spring Framework. Hãy đối chiếu API của phiên bản dự án đang sử dụng trước khi thêm cấu hình riêng.

## 4. Thực thi truy vấn SELECT

Một thao tác thường bắt đầu bằng `databaseClient.sql(...)`. Sau đó ứng dụng bind tham số, định nghĩa cách ánh xạ hàng và chọn cách lấy kết quả.

Giả sử ứng dụng có kiểu dữ liệu:

```java
public record Customer(Long id, String name, String email) {}
```

Có thể truy vấn và ánh xạ như sau:

```java
public Flux<Customer> findActiveCustomers(DatabaseClient databaseClient) {
    return databaseClient.sql("""
            SELECT id, name, email
            FROM customer
            WHERE active = :active
            ORDER BY id
            """)
        .bind("active", true)
        .map((row, metadata) -> new Customer(
            row.get("id", Long.class),
            row.get("name", String.class),
            row.get("email", String.class)))
        .all();
}
```

Trong ví dụ này:

- `sql(...)` nhận câu SQL cần thực thi.
- `bind("active", true)` gắn giá trị cho tham số có tên `active`.
- `map(...)` nhận một `Row` cùng `RowMetadata` và chuyển thành `Customer`.
- `all()` trả về `Flux<Customer>` chứa các hàng kết quả.

Hàm ánh xạ nhận metadata để có thể kiểm tra thông tin cột khi cần. Trong ví dụ đơn giản, ứng dụng lấy cột theo tên. Nên dùng alias rõ ràng trong SQL để tránh nhầm lẫn, nhất là khi truy vấn join nhiều bảng có các cột trùng tên như `id`, `name` hoặc `created_at`.

### 4.1. Chọn cách lấy kết quả phù hợp

Sau khi ánh xạ, `DatabaseClient` cung cấp các cách lấy kết quả theo số lượng mong muốn:

```java
// Lấy hàng đầu tiên nếu có; bỏ qua các hàng tiếp theo.
Mono<Customer> first = databaseClient.sql("""
        SELECT id, name, email
        FROM customer
        WHERE active = true
        ORDER BY id
        """)
    .map((row, metadata) -> new Customer(
        row.get("id", Long.class),
        row.get("name", String.class),
        row.get("email", String.class)))
    .first();
```

Các lựa chọn quan trọng:

| Phương thức | Kiểu kết quả | Ý nghĩa |
|---|---|---|
| `first()` | `Mono<T>` | Lấy hàng đầu tiên nếu có; không yêu cầu kết quả chỉ có một hàng |
| `one()` | `Mono<T>` | Mong đợi tối đa một hàng; nhiều hàng là lỗi sai kích thước kết quả |
| `all()` | `Flux<T>` | Phát tất cả các hàng kết quả |

Hãy chọn theo hợp đồng nghiệp vụ. Nếu truy vấn theo khóa chính và mong đợi duy nhất một hàng, `one()` thể hiện rõ kỳ vọng hơn. Nếu chỉ cần một hàng đầu tiên theo thứ tự đã xác định, `first()` phù hợp. Nếu cần xử lý danh sách, dùng `all()`.

Không dùng `first()` để che giấu lỗi dữ liệu có nhiều hàng trong trường hợp nghiệp vụ yêu cầu duy nhất. Khi đó, `one()` giúp phát hiện vi phạm kỳ vọng sớm hơn.

## 5. Bind tham số an toàn

Tham số hóa truy vấn giúp tách dữ liệu đầu vào khỏi cấu trúc SQL. Với named parameter, câu SQL có thể dễ đọc:

```java
Mono<Customer> findById(Long id) {
    return databaseClient.sql("""
            SELECT id, name, email
            FROM customer
            WHERE id = :id
            """)
        .bind("id", id)
        .map((row, metadata) -> new Customer(
            row.get("id", Long.class),
            row.get("name", String.class),
            row.get("email", String.class)))
        .one();
}
```

Spring chuyển named parameter sang bind marker phù hợp với driver R2DBC. Cách biểu diễn marker ở tầng driver có thể khác nhau giữa các database, vì vậy nên sử dụng cơ chế bind của `DatabaseClient` thay vì tự ghép giá trị vào chuỗi SQL.

### 5.1. Giá trị null

Không thể bind `null` như một giá trị thông thường trong R2DBC vì driver cần biết kiểu dữ liệu của tham số null. Hãy dùng `bindNull` và chỉ rõ kiểu:

```java
DatabaseClient.GenericExecuteSpec spec = databaseClient.sql("""
        SELECT id, name, email
        FROM customer
        WHERE email = :email
        """);

spec = spec.bindNull("email", String.class);

Flux<Customer> result = spec
    .map((row, metadata) -> new Customer(
        row.get("id", Long.class),
        row.get("name", String.class),
        row.get("email", String.class)))
    .all();
```

Nếu tham số có giá trị, dùng `bind("email", value)`. Nếu giá trị là null, dùng `bindNull("email", String.class)` hoặc kiểu tương ứng với cột database.

### 5.2. Không ghép chuỗi dữ liệu đầu vào vào SQL

Không xây dựng câu truy vấn bằng cách nối trực tiếp giá trị do người dùng gửi:

```java
// Không an toàn: dữ liệu đầu vào trở thành một phần của cú pháp SQL.
String sql = "SELECT * FROM customer WHERE name = '" + name + "'";
```

Hãy bind giá trị:

```java
databaseClient.sql("SELECT id, name FROM customer WHERE name = :name")
    .bind("name", name)
    .map((row, metadata) -> new Customer(
        row.get("id", Long.class),
        row.get("name", String.class),
        null))
    .all();
```

Bind parameter dùng cho **giá trị**, không dùng để thay thế tên bảng, tên cột, từ khóa `ORDER BY` hoặc một đoạn cú pháp SQL. Nếu cần chọn cột sắp xếp theo yêu cầu người dùng, hãy ánh xạ lựa chọn đó qua danh sách cho phép:

```java
String orderColumn = switch (sortField) {
    case "name" -> "name";
    case "createdAt" -> "created_at";
    default -> "id";
};

String sql = "SELECT id, name FROM customer ORDER BY "
    + orderColumn + " LIMIT :limit";

Flux<Customer> customers = databaseClient.sql(sql)
    .bind("limit", 100)
    .map((row, metadata) -> new Customer(
        row.get("id", Long.class),
        row.get("name", String.class),
        null))
    .all();
```

Trong ví dụ, `orderColumn` chỉ có thể nhận một trong các tên cột đã định nghĩa trong code. Không đưa trực tiếp chuỗi tùy ý từ request vào cấu trúc SQL.

## 6. Thực thi INSERT, UPDATE và DELETE

Không phải câu SQL nào cũng trả về tập hàng. Với câu lệnh thay đổi dữ liệu, ứng dụng thường quan tâm đến số hàng bị ảnh hưởng. `fetch().rowsUpdated()` trả kết quả dạng `Mono<Long>`.

Ví dụ cập nhật trạng thái:

```java
Mono<Long> deactivateCustomer(Long customerId) {
    return databaseClient.sql("""
            UPDATE customer
            SET active = false
            WHERE id = :id
            """)
        .bind("id", customerId)
        .fetch()
        .rowsUpdated();
}
```

Giá trị phát ra cho biết số hàng được cập nhật theo báo cáo của driver. Ứng dụng có thể dùng giá trị này để xác định bản ghi có tồn tại hoặc có được thay đổi hay không:

```java
Mono<Void> deactivateOrFail(Long customerId) {
    return deactivateCustomer(customerId)
        .flatMap(rows -> rows == 1
            ? Mono.empty()
            : Mono.error(new IllegalStateException(
                "Customer không tồn tại hoặc không được cập nhật")))
        .then();
}
```

Với INSERT đơn giản:

```java
Mono<Long> insertCustomer(String name, String email) {
    return databaseClient.sql("""
            INSERT INTO customer(name, email, active)
            VALUES (:name, :email, true)
            """)
        .bind("name", name)
        .bind("email", email)
        .fetch()
        .rowsUpdated();
}
```

Nếu cần lấy khóa được sinh tự động, cách viết phụ thuộc database và driver. Ví dụ, PostgreSQL hỗ trợ `RETURNING`:

```java
Mono<Long> insertAndReturnId(String name, String email) {
    return databaseClient.sql("""
            INSERT INTO customer(name, email, active)
            VALUES (:name, :email, true)
            RETURNING id
            """)
        .bind("name", name)
        .bind("email", email)
        .map((row, metadata) -> row.get("id", Long.class))
        .one();
}
```

`RETURNING` là ví dụ đặc thù PostgreSQL, không phải cú pháp SQL phổ quát. Với database khác, hãy dùng cơ chế lấy generated key mà driver và hệ quản trị hỗ trợ.

## 7. Ánh xạ Row sang DTO và kết quả JOIN

Một ưu điểm lớn của `DatabaseClient` là có thể ánh xạ kết quả theo đúng hình dạng mà use case cần, không nhất thiết phải khôi phục đầy đủ một entity.

Giả sử cần hiển thị đơn hàng cùng tên khách hàng:

```sql
SELECT
    o.id AS order_id,
    o.total_amount AS order_total,
    c.id AS customer_id,
    c.name AS customer_name
FROM orders o
JOIN customer c ON c.id = o.customer_id
WHERE o.status = :status
ORDER BY o.id
```

Khai báo DTO:

```java
public record OrderSummary(
    Long orderId,
    BigDecimal total,
    Long customerId,
    String customerName
) {}
```

Ánh xạ kết quả:

```java
Flux<OrderSummary> findOrderSummaries(String status) {
    return databaseClient.sql("""
            SELECT
                o.id AS order_id,
                o.total_amount AS order_total,
                c.id AS customer_id,
                c.name AS customer_name
            FROM orders o
            JOIN customer c ON c.id = o.customer_id
            WHERE o.status = :status
            ORDER BY o.id
            """)
        .bind("status", status)
        .map((row, metadata) -> new OrderSummary(
            row.get("order_id", Long.class),
            row.get("order_total", BigDecimal.class),
            row.get("customer_id", Long.class),
            row.get("customer_name", String.class)))
        .all();
}
```

Alias giúp tránh trùng tên cột và làm rõ ý nghĩa của từng trường. Cần chú ý kiểu Java mà driver trả về cho từng kiểu SQL. Với kiểu số, ngày giờ, JSON hoặc kiểu đặc thù, hãy kiểm tra mapping của driver và thực hiện chuyển đổi tường minh khi cần.

`Row` chỉ có thể được sử dụng trong phạm vi callback ánh xạ theo hợp đồng của R2DBC. Hãy chuyển giá trị cần thiết sang DTO hoặc object của ứng dụng ngay trong callback, thay vì giữ đối tượng `Row` để sử dụng sau khi kết quả đã được tiêu thụ.

## 8. DatabaseClient và ánh xạ entity của Spring Data

Điểm cần phân biệt là `DatabaseClient` tập trung vào SQL và hàng kết quả. Khi gọi `map(...)`, ứng dụng tự đọc cột và tự tạo object. Nó không tự động áp dụng toàn bộ metadata entity như khi dùng Spring Data mapping layer.

Ví dụ, khi dùng `DatabaseClient` trực tiếp, ứng dụng cần tự quyết định:

- Cột nào được chọn và ánh xạ vào thuộc tính nào.
- Alias nào tương ứng với trường DTO.
- Cách chuyển kiểu database sang kiểu Java.
- Cách xử lý giá trị null và cột thiếu.
- Cách áp dụng quy tắc nghiệp vụ như version, auditing hoặc cập nhật trường thời gian.

Đối với thao tác entity, `R2dbcEntityTemplate` cung cấp abstraction cao hơn. Nó sử dụng hạ tầng mapping của Spring Data R2DBC, bao gồm mapping metadata và converter, để chuyển đổi giữa entity và dữ liệu quan hệ. Repository lại xây dựng API theo mô hình repository trên tầng thao tác entity.

| Tiêu chí | `DatabaseClient` | `R2dbcEntityTemplate` | Repository |
|---|---|---|---|
| Mức trừu tượng | SQL-centric, thấp hơn | Entity-centric, trung gian | Repository-centric, cao hơn |
| Viết SQL | Trực tiếp | Có thể dùng API query/update hoặc SQL qua client | Có thể dùng derived query, `@Query` và các API được hỗ trợ |
| Ánh xạ entity | Thường tự viết mapper | Tích hợp Spring Data converter và metadata | Dựa trên tầng entity của Spring Data |
| DTO/projection tùy chỉnh | Rất linh hoạt qua `map` | Có API truy vấn phù hợp, tùy use case | Hỗ trợ projection theo khả năng repository |
| Phù hợp | SQL phức tạp, báo cáo, truy vấn đặc thù | Thao tác entity cần kiểm soát linh hoạt | CRUD và truy vấn theo hợp đồng repository |

Không phải mọi tính năng Spring Data đều tự động chạy khi dùng raw `DatabaseClient`. Ví dụ, không nên giả định auditing, entity callbacks, quy tắc optimistic locking hoặc mapping theo annotation sẽ tự áp dụng cho câu SQL do ứng dụng viết. Nếu cần các tính năng đó, hãy cân nhắc `R2dbcEntityTemplate` hoặc repository, hoặc chủ động thực hiện quy tắc tương ứng trong câu lệnh và service.

## 9. Tích hợp với reactive transaction

`DatabaseClient` có thể tham gia transaction do Spring quản lý. Với R2DBC, transaction manager phổ biến là `R2dbcTransactionManager`. Connection được quản lý theo reactive context để các thao tác trong cùng transaction sử dụng connection thuộc transaction đó.

Ví dụ service thực hiện cập nhật và sau đó đọc lại bản ghi:

```java
@Service
public class CustomerService {

    private final DatabaseClient databaseClient;

    public CustomerService(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    @Transactional
    public Mono<Customer> rename(Long id, String newName) {
        Mono<Long> update = databaseClient.sql("""
                UPDATE customer
                SET name = :name
                WHERE id = :id
                """)
            .bind("name", newName)
            .bind("id", id)
            .fetch()
            .rowsUpdated();

        Mono<Customer> readBack = databaseClient.sql("""
                SELECT id, name, email
                FROM customer
                WHERE id = :id
                """)
            .bind("id", id)
            .map((row, metadata) -> new Customer(
                row.get("id", Long.class),
                row.get("name", String.class),
                row.get("email", String.class)))
            .one();

        return update.then(readBack);
    }
}
```

Khi phương thức reactive được gọi trong ngữ cảnh Spring transaction phù hợp, các thao tác trong publisher được thực thi trong transaction đó. Nếu một thao tác phát lỗi, transaction manager có thể rollback theo quy tắc transaction.

Một số nguyên tắc quan trọng:

- `DatabaseClient` và `R2dbcTransactionManager` phải dùng cùng `ConnectionFactory` tương ứng.
- Phương thức transactional reactive nên trả về publisher (`Mono` hoặc `Flux`) để Spring quản lý ranh giới thực thi.
- Không gọi `block()` bên trong luồng reactive để chờ thao tác database.
- Không tự tạo connection riêng bằng `ConnectionFactory.create()` cho từng câu lệnh nếu muốn các thao tác tham gia transaction do Spring quản lý.
- Giữ transaction đủ ngắn để tránh giữ connection và khóa quá lâu.

Nếu cần kiểm soát transaction bằng code, có thể dùng `TransactionalOperator` để bao quanh publisher. Cách này hữu ích khi ranh giới transaction được xác định trong một pipeline thay vì annotation trên phương thức.

## 10. Vòng đời reactive: subscribe, demand và cancellation

Các thao tác `DatabaseClient` là lazy theo mô hình reactive. Việc tạo một `Mono` hoặc `Flux` mô tả công việc; truy vấn thường bắt đầu khi publisher được subscribe.

```java
Flux<Customer> customers = databaseClient.sql("""
        SELECT id, name, email
        FROM customer
        WHERE active = true
        """)
    .map((row, metadata) -> new Customer(
        row.get("id", Long.class),
        row.get("name", String.class),
        row.get("email", String.class)))
    .all();
```

Tại thời điểm gán vào biến `customers`, ứng dụng đã mô tả publisher. Việc thực thi được kích hoạt khi có subscriber tiêu thụ publisher đó. Nếu cùng một publisher được subscribe nhiều lần, thao tác SQL có thể được thực thi lại cho mỗi subscription; không nên mặc định rằng kết quả đã được cache.

Vì kết quả là reactive publisher:

- Downstream điều tiết lượng phần tử cần nhận thông qua Reactive Streams demand.
- Khi downstream xử lý chậm, việc phát dữ liệu có thể được điều tiết qua các tầng hỗ trợ backpressure.
- Khi subscription bị hủy, client và driver có cơ hội dừng việc tiêu thụ kết quả và giải phóng tài nguyên theo khả năng hỗ trợ.
- Chi tiết đọc trước, buffer, cursor và phản ứng với cancellation phụ thuộc driver và database.

Backpressure không thay thế giới hạn SQL. Nếu nghiệp vụ chỉ cần tối đa 100 hàng, hãy đặt `LIMIT 100` trong câu truy vấn. Nếu cần xử lý lượng dữ liệu lớn theo từng lượt, hãy dùng phân trang hoặc keyset pagination thay vì giữ một truy vấn không giới hạn trong thời gian dài.

Tránh gom toàn bộ kết quả lớn thành một collection:

```java
// Có thể giữ tất cả hàng trong bộ nhớ.
Mono<List<Customer>> allCustomers = customers.collectList();
```

Với dữ liệu lớn, hãy xử lý từng phần tử hoặc từng batch có kích thước hữu hạn. Trong WebFlux, trả publisher về tầng web để framework quản lý subscription; không chặn thread bằng `.block()` trong request path.

## 11. Xử lý lỗi và exception translation

R2DBC driver phát sinh các lỗi thuộc hệ sinh thái R2DBC, chẳng hạn lỗi kết nối, lỗi cú pháp SQL, vi phạm constraint hoặc timeout. Spring `DatabaseClient` tích hợp exception translation để chuyển nhiều lỗi R2DBC sang hệ thống `DataAccessException` của Spring.

Nhờ vậy, tầng service có thể xử lý lỗi theo nhóm trừu tượng của Spring thay vì phụ thuộc hoàn toàn vào exception cụ thể của từng driver. Ví dụ, vi phạm khóa duy nhất có thể được biểu diễn bằng một loại lỗi dữ liệu tương ứng trong hệ thống `DataAccessException`.

Ví dụ xử lý lỗi ở reactive pipeline:

```java
Mono<Long> updateEmail(Long id, String email) {
    return databaseClient.sql("""
            UPDATE customer
            SET email = :email
            WHERE id = :id
            """)
        .bind("email", email)
        .bind("id", id)
        .fetch()
        .rowsUpdated()
        .onErrorMap(DataAccessException.class, ex ->
            new CustomerPersistenceException(
                "Không thể cập nhật email khách hàng", ex));
}
```

Chỉ chuyển đổi những lỗi mà tầng service thực sự muốn trừu tượng hóa. Không nên bắt mọi exception rồi trả về giá trị thành công giả, vì điều đó che giấu lỗi dữ liệu và làm transaction khó xử lý đúng.

Các lỗi timeout, connection reset hoặc lỗi mạng có thể có tính chất tạm thời, nhưng không phải mọi câu lệnh đều an toàn để retry. Đặc biệt, với INSERT hoặc thao tác có side effect, cần xác định database đã commit hay chưa trước khi retry để tránh thực hiện nghiệp vụ hai lần. Retry phải có chính sách rõ ràng và cân nhắc idempotency.

## 12. Phân trang và giới hạn truy vấn

Vì `DatabaseClient` cho phép viết SQL trực tiếp, ứng dụng có thể kiểm soát rõ số hàng trả về và chiến lược phân trang.

Ví dụ phân trang offset:

```java
Flux<Customer> findPage(int page, int size) {
    int safePage = Math.max(0, page);
    int safeSize = Math.max(1, Math.min(size, 200));
    long offset = (long) safePage * safeSize;

    return databaseClient.sql("""
            SELECT id, name, email
            FROM customer
            ORDER BY id
            LIMIT :size OFFSET :offset
            """)
        .bind("size", safeSize)
        .bind("offset", offset)
        .map((row, metadata) -> new Customer(
            row.get("id", Long.class),
            row.get("name", String.class),
            row.get("email", String.class)))
        .all();
}
```

Giới hạn `safeSize` bảo vệ database khỏi request yêu cầu một trang quá lớn. `ORDER BY` ổn định giúp kết quả trang có thứ tự xác định. Với trang rất sâu hoặc tác vụ quét dữ liệu tuần tự, keyset pagination thường hiệu quả hơn offset:

```sql
SELECT id, name, email
FROM customer
WHERE id > :afterId
ORDER BY id
LIMIT :size
```

Ứng dụng truyền `id` cuối cùng của trang trước vào `afterId`. Cột cursor cần có thứ tự ổn định và index phù hợp. Nếu sắp xếp theo nhiều cột, điều kiện cursor phải phản ánh đầy đủ thứ tự đó.

`DatabaseClient` không tự động bảo đảm truy vấn chạy nhanh chỉ vì kết quả được trả về bằng `Flux`. Cần kiểm tra execution plan, index, số cột được chọn, điều kiện lọc và kích thước dữ liệu. Với truy vấn báo cáo lớn, nên cân nhắc giới hạn thời gian, quyền truy cập và tải database theo chính sách vận hành.

## 13. Kiểm thử DatabaseClient

Kiểm thử nên xác nhận cả hành vi của ứng dụng lẫn SQL thực tế trên database tương thích.

### 13.1. Kiểm thử tích hợp

Với các câu SQL có dialect cụ thể, kiểm thử tích hợp trên cùng hệ quản trị hoặc phiên bản tương thích là cách đáng tin cậy để xác nhận:

- Cú pháp SQL được database chấp nhận.
- Bind marker và kiểu dữ liệu được driver xử lý đúng.
- Ánh xạ `Row` sang DTO hoạt động với kiểu dữ liệu thực tế.
- Transaction commit và rollback theo kỳ vọng.
- Constraint, generated key và số hàng bị ảnh hưởng có hành vi đúng.

Database nhúng hoặc container có thể được dùng tùy theo hạ tầng kiểm thử của dự án. Không nên chỉ dựa vào mock `DatabaseClient` để kết luận SQL hợp lệ, vì mock không thực thi câu lệnh trên database.

### 13.2. Kiểm tra reactive publisher

Có thể dùng Reactor `StepVerifier` để xác nhận số phần tử, giá trị và tín hiệu kết thúc:

```java
StepVerifier.create(customerService.findActiveCustomers())
    .expectNextMatches(customer -> customer.id() != null)
    .expectNextCount(1)
    .verifyComplete();
```

Ví dụ trên minh họa cách xác nhận publisher phát ra dữ liệu và hoàn tất. Test thực tế cần chuẩn bị dữ liệu xác định, kiểm tra đầy đủ các trường quan trọng và xử lý cả trường hợp không có hàng hoặc phát sinh lỗi.

### 13.3. Quan sát trong môi trường chạy

Các chỉ số hữu ích khi vận hành `DatabaseClient` gồm:

- Thời gian thực thi theo loại truy vấn và theo endpoint.
- Số hàng được trả về, số hàng bị cập nhật và kích thước batch.
- Tỷ lệ truy vấn lỗi, timeout và lỗi kết nối.
- Số connection active/idle, thời gian chờ acquire và thời gian giữ connection.
- Bộ nhớ heap, GC và độ trễ của downstream khi xử lý kết quả lớn.
- Execution plan và mức sử dụng CPU, I/O, lock ở database.

Không ghi log giá trị nhạy cảm của tham số truy vấn như mật khẩu, token, email hoặc dữ liệu cá nhân nếu chính sách bảo mật không cho phép. Khi cần truy vết, ưu tiên log loại thao tác, thời gian, mã tương quan và thông tin đã được che hoặc loại bỏ dữ liệu nhạy cảm.

## 14. Những lỗi thường gặp khi dùng DatabaseClient

| Lỗi | Vì sao có vấn đề? | Cách xử lý |
|---|---|---|
| Ghép dữ liệu đầu vào trực tiếp vào SQL | Có thể tạo SQL injection và lỗi cú pháp | Dùng `bind` / `bindNull` cho giá trị |
| Bind tên cột hoặc tên bảng như một tham số | Bind marker chỉ đại diện cho giá trị | Dùng danh sách định danh được cho phép để chọn identifier |
| Dùng `first()` khi cần bảo đảm duy nhất | Nhiều hàng có thể bị bỏ qua mà không báo sai kích thước | Dùng `one()` khi hợp đồng yêu cầu tối đa một hàng |
| Không đặt alias cho cột join | Các cột trùng tên gây ánh xạ nhầm | Đặt alias duy nhất và ánh xạ theo alias |
| Giả định entity mapping tự động xảy ra | Raw `DatabaseClient.map` không tự áp dụng toàn bộ mapping metadata | Tự viết mapper hoặc dùng `R2dbcEntityTemplate` |
| Gọi `.block()` trong request reactive | Chặn thread và phá vỡ lợi ích non-blocking | Trả `Mono` / `Flux` và compose bằng toán tử Reactor |
| Gọi `collectList()` với kết quả không giới hạn | Có thể làm tăng heap đến mức cạn bộ nhớ | Giới hạn SQL và xử lý theo batch |
| Tạo publisher nhưng không subscribe | Truy vấn lazy có thể chưa được thực thi | Compose publisher vào luồng được framework subscribe |
| Subscribe nhiều lần ngoài ý muốn | Cùng publisher có thể thực thi SQL nhiều lần | Quản lý subscription rõ ràng; cache chỉ khi có chủ đích |
| Dùng `ConnectionFactory` khác transaction manager | Các thao tác có thể không tham gia cùng transaction | Dùng cùng `ConnectionFactory` được quản lý |
| Retry mọi lỗi database | Có thể lặp side effect hoặc che lỗi lâu dài | Chỉ retry lỗi phù hợp, có timeout và idempotency |

## 15. Chọn DatabaseClient, template hay repository

Quyết định nên dựa trên mức độ kiểm soát SQL và mức độ hỗ trợ entity mà use case cần.

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| CRUD đơn giản theo aggregate | Spring Data repository | API ngắn, rõ ý nghĩa nghiệp vụ và giảm boilerplate |
| Thao tác entity linh hoạt, có mapping Spring Data | `R2dbcEntityTemplate` | Giữ entity metadata và converter, đồng thời linh hoạt hơn repository method |
| SQL phức tạp, join và projection tùy chỉnh | `DatabaseClient` | Kiểm soát câu SQL và mapper trực tiếp |
| Báo cáo, thống kê hoặc truy vấn đặc thù database | `DatabaseClient` | Dễ dùng biểu thức và tính năng SQL của database |
| Cần tự kiểm soát từng cột trả về | `DatabaseClient` | Mapper chỉ đọc những cột được chọn |
| Cần dùng lifecycle, auditing và entity mapping của Spring Data | Repository hoặc `R2dbcEntityTemplate` | Tích hợp với tầng mapping và callback của Spring Data |

Các lựa chọn có thể cùng tồn tại trong một ứng dụng. Một service có thể dùng repository cho thao tác CRUD phổ biến, `R2dbcEntityTemplate` cho thao tác entity linh hoạt và `DatabaseClient` cho truy vấn báo cáo hoặc SQL chuyên biệt. Nên thống nhất quy ước trong nhóm để mỗi use case có một abstraction dễ hiểu và dễ kiểm thử.

## 16. Nguyên tắc thiết kế khi đưa DatabaseClient vào dự án

1. **Đặt SQL ở nơi dễ tìm và dễ kiểm thử.** Gom các truy vấn theo repository adapter hoặc lớp persistence phù hợp với kiến trúc, tránh rải chuỗi SQL tùy tiện trong controller.
2. **Dùng bind cho mọi giá trị đầu vào.** Kiểm soát riêng các identifier động bằng danh sách cho phép.
3. **Chọn đúng kiểu publisher.** Dùng `Mono` cho kết quả đơn hoặc số hàng bị ảnh hưởng; dùng `Flux` cho tập kết quả.
4. **Định nghĩa rõ cardinality.** Dùng `one()` khi mong đợi tối đa một hàng, `first()` khi chỉ cần hàng đầu tiên và `all()` khi cần toàn bộ kết quả.
5. **Đặt giới hạn ở SQL.** Dùng filter, `LIMIT`, phân trang và index phù hợp; không coi reactive stream là giới hạn tổng số hàng.
6. **Ánh xạ có chủ đích.** Đặt alias rõ ràng, kiểm tra kiểu dữ liệu driver và chỉ lấy cột cần thiết.
7. **Giữ transaction ngắn và nhất quán.** Đảm bảo cùng `ConnectionFactory` và không chặn publisher.
8. **Để lỗi được quan sát.** Không nuốt exception; xác định rõ chính sách retry, timeout và xử lý lỗi nghiệp vụ.
9. **Đo trên database thực tế.** Dùng integration test, execution plan và metrics để xác nhận hiệu năng.
10. **Chọn abstraction vừa đủ.** Dùng repository hoặc template khi cần lợi ích entity mapping; dùng `DatabaseClient` khi SQL trực tiếp đem lại giá trị rõ ràng.

`DatabaseClient` đóng vai trò cầu nối giữa ứng dụng Spring reactive và câu lệnh SQL của database. Nó cung cấp API thực thi không chặn, bind tham số an toàn, ánh xạ kết quả linh hoạt và tích hợp với transaction của Spring. Khi hiểu rõ ranh giới của nó so với `R2dbcEntityTemplate` và repository, nhóm phát triển có thể chọn đúng tầng abstraction cho từng truy vấn, giữ SQL minh bạch và xây dựng lớp truy cập dữ liệu dễ kiểm soát trong Spring R2DBC.

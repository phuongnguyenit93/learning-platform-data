# R2DBC: kết nối, truy vấn và ánh xạ kết quả theo luồng

Ứng dụng reactive cần truy cập cơ sở dữ liệu mà không chặn thread trong lúc chờ I/O. JDBC truyền thống thường thực hiện truy vấn đồng bộ: thread gọi `executeQuery()` phải chờ database trả kết quả. R2DBC (*Reactive Relational Database Connectivity*) cung cấp SPI để truy cập cơ sở dữ liệu quan hệ bằng các publisher Reactive Streams. Trong Spring, `DatabaseClient`, Spring Data R2DBC và `R2dbcEntityTemplate` giúp xây dựng truy vấn, ánh xạ hàng dữ liệu và kết hợp thao tác database với `Mono` hoặc `Flux`.

Module `REACTIVE_PROGRAMMING` tập trung vào các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; đồng thời thực hành `Mono`, `Flux`, operator, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Bài học này trình bày cách cấu hình kết nối R2DBC, truy vấn một hoặc nhiều hàng, ánh xạ kết quả, quản lý transaction reactive và kiểm soát tài nguyên khi xử lý dữ liệu theo luồng.

## 1. R2DBC khác JDBC ở đâu?

JDBC cung cấp API blocking quen thuộc: ứng dụng mở `Connection`, tạo `Statement`, chạy truy vấn và đọc `ResultSet` trên thread gọi. Cách này phù hợp với ứng dụng đồng bộ, nhưng nếu dùng trực tiếp trên event loop của WebFlux, thread phục vụ nhiều request có thể bị giữ trong lúc database phản hồi.

R2DBC định nghĩa API bất đồng bộ dựa trên Reactive Streams. Việc lấy connection, thực thi statement và đọc kết quả được biểu diễn bằng publisher. Subscriber nhận dữ liệu theo demand và có thể hủy subscription khi không còn cần kết quả.

| Khía cạnh | JDBC | R2DBC |
|---|---|---|
| Lấy connection | API đồng bộ trả về `Connection`. | `ConnectionFactory.create()` trả về `Publisher<Connection>`. |
| Thực thi query | `Statement.executeQuery()` trả `ResultSet`. | `Statement.execute()` trả publisher các `Result`. |
| Đọc hàng | Vòng lặp đồng bộ trên `ResultSet`. | Kết quả có thể được chuyển thành publisher các hàng. |
| Chờ I/O | Thread gọi thường bị chặn. | API được thiết kế để không cần giữ thread trong lúc chờ I/O. |
| Backpressure | Không có hợp đồng Reactive Streams ở API JDBC. | Publisher và subscriber phối hợp demand theo Reactive Streams. |
| Tích hợp Spring | JDBC, `JdbcTemplate`, transaction manager đồng bộ. | `DatabaseClient`, Spring Data R2DBC, `R2dbcTransactionManager`. |

R2DBC không làm database truy vấn nhanh hơn một cách tự động. Nó thay đổi cách ứng dụng chờ I/O và điều phối kết quả. Hiệu năng còn phụ thuộc database, driver, query plan, connection pool, chỉ mục và cách pipeline tiêu thụ dữ liệu.

### Chọn R2DBC khi nào?

R2DBC phù hợp khi ứng dụng đã dùng WebFlux/Reactor và cần giữ đường đi I/O bất đồng bộ đến database. Nó cũng hữu ích với các luồng đọc nhiều hàng, nơi kết quả có thể được xử lý dần theo demand.

JDBC vẫn có thể phù hợp với ứng dụng blocking, batch job đồng bộ hoặc thư viện chỉ hỗ trợ JDBC. Không nên chuyển sang R2DBC chỉ vì muốn dùng một API có hậu tố `Reactive`; hãy đánh giá driver hỗ trợ, tính năng database cần dùng, transaction, migration, quan sát và năng lực vận hành.

## 2. Cấu hình driver và `ConnectionFactory`

R2DBC SPI dùng `ConnectionFactory` làm điểm tạo connection. Mỗi database cần driver R2DBC tương ứng, ví dụ PostgreSQL, MariaDB, MySQL, SQL Server hoặc H2. Dependency phải khớp với database và phiên bản Spring/R2DBC trong dự án.

Một cấu hình URL thường có dạng:

```text
r2dbc:postgresql://db-host:5432/orders
```

Trong ứng dụng Spring Boot, cấu hình thường được đặt trong `application.yml`:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/orders
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
```

Thông tin xác thực nên lấy từ biến môi trường hoặc secret manager. Không ghi mật khẩu thật vào source control, log hoặc ví dụ chia sẻ.

Khi không dùng Spring Boot auto-configuration, có thể tạo `ConnectionFactory` trực tiếp:

```java
ConnectionFactory connectionFactory = ConnectionFactories.get(
    ConnectionFactoryOptions.builder()
        .option(ConnectionFactoryOptions.DRIVER, "postgresql")
        .option(ConnectionFactoryOptions.HOST, "localhost")
        .option(ConnectionFactoryOptions.PORT, 5432)
        .option(ConnectionFactoryOptions.DATABASE, "orders")
        .option(ConnectionFactoryOptions.USER, dbUsername)
        .option(ConnectionFactoryOptions.PASSWORD, dbPassword)
        .build()
);
```

`ConnectionFactories.get(...)` tìm driver phù hợp với tùy chọn kết nối. Driver chịu trách nhiệm giao tiếp giao thức với database. Trong ứng dụng Spring, thường nên để framework quản lý `ConnectionFactory` và các bean liên quan để transaction manager, repository và client dùng chung cấu hình.

### Connection pool

Mở một kết nối mạng mới cho mỗi thao tác có thể tốn chi phí. Trong môi trường production, ứng dụng thường dùng connection pool R2DBC để tái sử dụng connection. Pool cần có giới hạn kích thước, thời gian chờ lấy connection, thời gian idle và chính sách validation phù hợp.

Pool không làm tăng vô hạn năng lực database. Nếu pool cho phép quá nhiều connection đồng thời, database có thể tốn tài nguyên cho quản lý session, lock và query đang chạy. Hãy đặt giới hạn dựa trên năng lực database và tổng số instance ứng dụng, không chỉ dựa trên một instance.

Một connection đang được sử dụng bởi query hoặc transaction không nên được chia sẻ tùy tiện giữa nhiều luồng xử lý độc lập. Hãy để `DatabaseClient` hoặc transaction manager quản lý việc lấy và trả connection theo scope thao tác.

## 3. Truy vấn bằng Spring `DatabaseClient`

`DatabaseClient` cung cấp API fluent để tạo SQL, bind tham số, ánh xạ hàng và chọn cách lấy kết quả. Đây là lựa chọn phù hợp khi cần SQL tường minh nhưng vẫn muốn kết quả ở dạng reactive.

```java
@Repository
class CustomerQueries {
    private final DatabaseClient databaseClient;

    CustomerQueries(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    Mono<Customer> findById(long id) {
        return databaseClient.sql("""
                SELECT id, email, display_name
                FROM customer
                WHERE id = :id
                """)
            .bind("id", id)
            .map((row, metadata) -> new Customer(
                row.get("id", Long.class),
                row.get("email", String.class),
                row.get("display_name", String.class)
            ))
            .one();
    }
}
```

Các bước chính:

1. `sql(...)` tạo một thao tác SQL.
2. `bind(...)` gắn giá trị vào named parameter.
3. `map((row, metadata) -> ...)` chuyển mỗi hàng thành object domain.
4. `one()` yêu cầu tối đa một hàng và trả `Mono<Customer>`.

Named parameter như `:id` giúp câu SQL dễ đọc. `DatabaseClient` chuyển named parameter sang placeholder mà driver sử dụng. Không nối chuỗi trực tiếp từ dữ liệu người dùng vào SQL; bind parameter giúp tránh SQL injection và xử lý giá trị theo quy tắc driver.

### Bind giá trị null

Nếu một tham số có thể null, không gọi `bind(name, null)`. Dùng `bindNull(name, Type.class)` để khai báo kiểu của tham số null:

```java
DatabaseClient.GenericExecuteSpec spec = databaseClient
    .sql("INSERT INTO customer (email, display_name) VALUES (:email, :name)")
    .bind("email", email);

if (displayName == null) {
    spec = spec.bindNull("name", String.class);
} else {
    spec = spec.bind("name", displayName);
}

Mono<Long> inserted = spec.fetch().rowsUpdated();
```

Khai báo kiểu giúp driver biết kiểu SQL cần dùng cho giá trị null. Kiểu Java cần tương thích với kiểu cột và khả năng chuyển đổi của driver.

### `one()`, `first()` và `all()`

`DatabaseClient` cung cấp các cách tiêu thụ kết quả khác nhau:

| Phương thức | Kiểu kết quả | Ngữ nghĩa |
|---|---|---|
| `one()` | `Mono<T>` | Yêu cầu tối đa một hàng; nếu query trả nhiều hơn một hàng thì phát lỗi. |
| `first()` | `Mono<T>` | Lấy hàng đầu tiên nếu có; các hàng còn lại không được chuyển xuống. |
| `all()` | `Flux<T>` | Phát các hàng của kết quả theo luồng. |
| `rowsUpdated()` | `Mono<Long>` | Phát số hàng được cập nhật bởi thao tác ghi. |

Nếu truy vấn có thể trả nhiều hàng nhưng nghiệp vụ chỉ cần một hàng bất kỳ, `first()` có thể phù hợp. Tuy nhiên, nếu cần kết quả xác định, hãy thêm `ORDER BY` rõ ràng. SQL không bảo đảm thứ tự hàng nếu không có `ORDER BY`.

`one()` hữu ích khi truy vấn theo khóa duy nhất và muốn phát hiện dữ liệu sai giả định. Nếu cột được cho là duy nhất nhưng query trả hai hàng, lỗi của `one()` giúp phát hiện vấn đề thay vì âm thầm chọn một hàng.

## 4. Ánh xạ hàng dữ liệu thành object domain

R2DBC SPI biểu diễn một hàng bằng `Row` và metadata bằng `RowMetadata`. `DatabaseClient.map(...)` cho phép ánh xạ từng hàng sang kiểu Java mà ứng dụng sử dụng.

Ví dụ ánh xạ kiểu dữ liệu và null:

```java
record OrderRow(
    Long id,
    String orderNumber,
    BigDecimal total,
    Instant createdAt,
    String note
) {}

Flux<OrderRow> findRecentOrders() {
    return databaseClient.sql("""
            SELECT id, order_number, total, created_at, note
            FROM orders
            ORDER BY created_at DESC, id DESC
            LIMIT :limit
            """)
        .bind("limit", 100)
        .map((row, metadata) -> new OrderRow(
            row.get("id", Long.class),
            row.get("order_number", String.class),
            row.get("total", BigDecimal.class),
            row.get("created_at", Instant.class),
            row.get("note", String.class)
        ))
        .all();
}
```

Một số lưu ý khi ánh xạ:

- Tên cột trong `row.get(...)` phải khớp với tên hoặc alias mà query trả về.
- Giá trị nullable có thể trả về `null`; record/domain constructor cần chấp nhận hoặc xử lý trường hợp đó.
- Kiểu Java cần tương thích với kiểu dữ liệu và codec của driver. Không phải mọi database đều ánh xạ cùng một kiểu SQL sang cùng một kiểu Java.
- Với kiểu JSON, enum, UUID hoặc kiểu database riêng, có thể cần codec hoặc converter tương ứng.
- Chỉ lấy những cột cần thiết để giảm dữ liệu truyền qua mạng và chi phí ánh xạ.

Không nên thực hiện truy vấn khác hoặc gọi service mạng bên trong mapper đồng bộ của từng hàng. Mapper nên là bước chuyển đổi nhẹ. Nếu cần enrich bất đồng bộ, hãy chuyển sang operator sau khi đã ánh xạ:

```java
Flux<OrderView> views = findRecentOrders()
    .flatMap(order -> customerService.findById(order.customerId())
        .map(customer -> new OrderView(order, customer))
    , 8);
```

Trong ví dụ, concurrency của `flatMap` được giới hạn ở tám publisher con. Nếu cần giữ thứ tự đầu ra theo thứ tự query, cân nhắc `flatMapSequential` hoặc `concatMap`.

## 5. Truy vấn nhiều hàng và xử lý theo luồng

Khi query trả về nhiều hàng, `all()` cung cấp `Flux<T>`. Subscriber có thể yêu cầu dữ liệu theo demand và xử lý từng hàng khi publisher phát ra.

```java
Flux<Customer> activeCustomers() {
    return databaseClient.sql("""
            SELECT id, email, display_name
            FROM customer
            WHERE status = :status
            ORDER BY id
            """)
        .bind("status", "ACTIVE")
        .map((row, metadata) -> new Customer(
            row.get("id", Long.class),
            row.get("email", String.class),
            row.get("display_name", String.class)
        ))
        .all();
}
```

Sau đó có thể nối các bước xử lý reactive:

```java
Mono<Long> countProcessed = activeCustomers()
    .filter(customer -> customer.email() != null)
    .concatMap(customer -> customerService.refreshProfile(customer))
    .count();
```

`concatMap` giữ thứ tự xử lý và chỉ chạy publisher con tiếp theo sau khi publisher hiện tại hoàn tất. Nếu các thao tác độc lập và database/service downstream có thể chịu tải song song, dùng `flatMap` với concurrency hữu hạn.

### `Flux` không đồng nghĩa với việc toàn bộ driver luôn stream từng hàng từ server

API trả `Flux<T>` cho phép ứng dụng tiêu thụ kết quả theo hợp đồng reactive. Tuy nhiên, mức độ streaming thực tế còn phụ thuộc driver, database protocol, fetch size, cursor và cấu hình. Một driver có thể fetch theo batch hoặc giữ một phần dữ liệu trong bộ nhớ trước khi phát xuống.

Khi truy vấn dữ liệu lớn, hãy kiểm tra tài liệu driver và cấu hình fetch phù hợp. Không nên mặc định rằng `all()` luôn đồng nghĩa database chỉ gửi đúng một hàng mỗi lần request. Đồng thời, tránh `collectList()` trên kết quả không giới hạn vì nó gom toàn bộ hàng vào bộ nhớ trước khi phát một danh sách.

### Phân trang theo keyset cho tập dữ liệu lớn

Với bảng lớn, phân trang bằng `OFFSET` cao có thể tốn chi phí vì database vẫn phải đi qua nhiều hàng trước vị trí cần lấy. Keyset pagination dùng giá trị cuối của trang trước để lấy trang tiếp theo:

```java
Flux<OrderRow> nextPage(long afterId, int pageSize) {
    return databaseClient.sql("""
            SELECT id, order_number, total
            FROM orders
            WHERE id > :afterId
            ORDER BY id
            LIMIT :pageSize
            """)
        .bind("afterId", afterId)
        .bind("pageSize", pageSize)
        .map((row, metadata) -> new OrderRow(
            row.get("id", Long.class),
            row.get("order_number", String.class),
            row.get("total", BigDecimal.class),
            null,
            null
        ))
        .all();
}
```

Ví dụ giả định `id` tăng đơn điệu và là khóa sắp xếp duy nhất. Nếu thứ tự dựa trên nhiều cột, cursor cần chứa đủ các cột để tạo điều kiện tiếp theo không bỏ sót hoặc lặp hàng. Keyset pagination phù hợp cho quá trình quét dữ liệu theo lô và có thể được nối bằng `expand` hoặc một vòng điều khiển reactive, nhưng cần xác định ranh giới dữ liệu khi bảng vẫn thay đổi trong lúc đọc.

## 6. Thao tác ghi và số hàng bị ảnh hưởng

`rowsUpdated()` trả `Mono<Long>` cho biết số hàng bị ảnh hưởng bởi câu lệnh ghi. Đây là tín hiệu hữu ích để kiểm tra kết quả insert, update hoặc delete.

```java
Mono<Long> updateCustomerEmail(long id, String email) {
    return databaseClient.sql("""
            UPDATE customer
            SET email = :email
            WHERE id = :id
            """)
        .bind("email", email)
        .bind("id", id)
        .fetch()
        .rowsUpdated();
}
```

Ứng dụng có thể kiểm tra số hàng được cập nhật:

```java
Mono<Void> changeEmail(long id, String email) {
    return updateCustomerEmail(id, email)
        .flatMap(updated -> {
            if (updated != 1L) {
                return Mono.error(new IllegalStateException(
                    "Expected one customer row, updated " + updated
                ));
            }
            return Mono.empty();
        });
}
```

Nếu update theo khóa chính, số hàng khác 1 có thể cho biết bản ghi không tồn tại hoặc giả định dữ liệu bị vi phạm. Với câu lệnh update hàng loạt, số hàng lớn hơn một có thể là kết quả mong muốn. Quy tắc kiểm tra phải phản ánh nghiệp vụ.

### Insert và giá trị được sinh

Khả năng trả về generated key phụ thuộc database và driver. Với `DatabaseClient`, có thể dùng `filter` hoặc API hỗ trợ generated values theo phiên bản Spring và driver. Khi cần tính di động, hãy kiểm tra tài liệu driver cho cú pháp `RETURNING` hoặc generated values.

Ví dụ PostgreSQL:

```java
Mono<Long> insertOrder(String orderNumber, BigDecimal total) {
    return databaseClient.sql("""
            INSERT INTO orders (order_number, total)
            VALUES (:number, :total)
            RETURNING id
            """)
        .bind("number", orderNumber)
        .bind("total", total)
        .map((row, metadata) -> row.get("id", Long.class))
        .one();
}
```

`RETURNING` là cú pháp PostgreSQL; không nên giả định mọi hệ quản trị quan hệ đều hỗ trợ cú pháp này. Nếu cần hỗ trợ nhiều database, hãy đặt phần khác biệt vào repository/adapter tương ứng.

## 7. Sử dụng Spring Data R2DBC Repository

Nếu thao tác dữ liệu phù hợp với CRUD và quy ước entity, Spring Data R2DBC có thể giảm lượng SQL và mapper phải viết thủ công.

```java
@Table("customer")
public class CustomerEntity {
    @Id
    private Long id;
    private String email;
    private String displayName;
    private String status;

    // constructors, getters and setters
}

public interface CustomerRepository
        extends ReactiveCrudRepository<CustomerEntity, Long> {

    Flux<CustomerEntity> findByStatus(String status);

    Mono<CustomerEntity> findByEmail(String email);
}
```

`ReactiveCrudRepository` cung cấp các thao tác CRUD trả về `Mono` hoặc `Flux`. Query method có thể được suy ra từ tên phương thức nếu biểu thức truy vấn được Spring Data hỗ trợ. Với query phức tạp hoặc cần kiểm soát SQL cụ thể, có thể dùng `@Query` hoặc `DatabaseClient`.

Ví dụ service:

```java
@Service
class CustomerService {
    private final CustomerRepository repository;

    CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    Flux<CustomerEntity> activeCustomers() {
        return repository.findByStatus("ACTIVE");
    }

    Mono<CustomerEntity> rename(long id, String name) {
        return repository.findById(id)
            .switchIfEmpty(Mono.error(
                new CustomerNotFoundException(id)
            ))
            .map(customer -> {
                customer.setDisplayName(name);
                return customer;
            })
            .flatMap(repository::save);
    }
}
```

`findById` trả `Mono.empty()` nếu không tìm thấy. `switchIfEmpty` chuyển trường hợp rỗng thành lỗi domain. `flatMap(repository::save)` nối thao tác lưu bất đồng bộ vào pipeline.

### `save` không phải lúc nào cũng chỉ là INSERT

Spring Data R2DBC dùng thông tin entity và trạng thái mới/cũ để quyết định insert hay update theo quy tắc của phiên bản và entity. Với entity có ID tự sinh, cần hiểu cơ chế xác định entity mới; khi cần kiểm soát rõ, có thể dùng `Persistable` hoặc chiến lược ID phù hợp. Không nên giả định mọi lời gọi `save` luôn tạo một hàng mới.

## 8. Dùng `R2dbcEntityTemplate` khi cần thao tác entity linh hoạt

`R2dbcEntityTemplate` cung cấp API fluent cho truy vấn và thao tác entity mà không cần tạo repository method cho mọi trường hợp.

```java
Flux<CustomerEntity> findActiveCustomers(R2dbcEntityTemplate template) {
    Query query = Query.query(
        Criteria.where("status").is("ACTIVE")
    ).sort(Sort.by(Sort.Order.asc("id")));

    return template.select(query, CustomerEntity.class);
}
```

Có thể dùng `insert`, `update`, `delete` và các API query tương ứng để thao tác entity. `R2dbcEntityTemplate` phù hợp khi muốn dùng mapping metadata của Spring Data nhưng cần tạo query động hoặc thao tác linh hoạt hơn repository.

Chọn công cụ theo mức độ trừu tượng:

| Công cụ | Khi phù hợp |
|---|---|
| `ReactiveCrudRepository` | CRUD và query method phổ biến, API repository rõ ràng. |
| `R2dbcEntityTemplate` | Query động, thao tác entity linh hoạt, vẫn dùng mapping metadata. |
| `DatabaseClient` | SQL tường minh, join/phép tổng hợp phức tạp hoặc cần kiểm soát câu lệnh. |
| R2DBC SPI trực tiếp | Adapter cấp thấp, driver feature đặc thù hoặc cần quản lý connection/statement thủ công. |

Không nên trộn nhiều tầng truy cập dữ liệu trong cùng một phương thức nếu không có lý do. Chọn một abstraction phù hợp giúp transaction, mapping và kiểm thử nhất quán hơn.

## 9. Quản lý connection và kết quả ở mức R2DBC SPI

Trong đa số ứng dụng Spring, `DatabaseClient` và repository quản lý connection theo operation. Khi viết adapter cấp thấp, cần nhớ rằng `ConnectionFactory.create()` trả về publisher và `Connection.close()` cũng là một publisher. Không được mở connection rồi bỏ qua việc close.

Ví dụ đọc một hàng bằng SPI và quản lý connection với `Mono.usingWhen`:

```java
Mono<Customer> findOne(ConnectionFactory factory, long id) {
    return Mono.usingWhen(
        Mono.from(factory.create()),
        connection -> Mono.from(
                connection.createStatement(
                    "SELECT id, email FROM customer WHERE id = $1"
                )
                .bind(0, id)
                .execute()
            )
            .flatMap(result -> Mono.from(result.map((row, metadata) ->
                new Customer(
                    row.get("id", Long.class),
                    row.get("email", String.class)
                )
            ))),
        connection -> Mono.from(connection.close()),
        (connection, error) -> Mono.from(connection.close()),
        connection -> Mono.from(connection.close())
    );
}
```

Ví dụ này minh họa các ý chính:

- `Mono.from(factory.create())` lấy một connection từ factory.
- `createStatement(...).bind(0, id)` tạo statement và bind positional parameter.
- `execute()` trả publisher các `Result`.
- `Result.map(...)` ánh xạ hàng thành object.
- `usingWhen` đóng connection trong cả complete, error và cancel.

Cú pháp placeholder và cách bind phụ thuộc driver. Ví dụ dùng `$1` theo kiểu PostgreSQL. Với query trả nhiều hàng, dùng `Flux.usingWhen` và chuyển `Result.map(...)` thành `Flux`; cần bảo đảm result được consume đúng cách và connection chỉ được đóng sau khi publisher đọc kết quả kết thúc hoặc bị hủy.

Trong mã ứng dụng Spring thông thường, ưu tiên `DatabaseClient` hoặc Spring Data vì chúng giảm nguy cơ quản lý sai connection và transaction. Chỉ dùng SPI trực tiếp khi cần điều khiển thấp hơn và đã hiểu vòng đời `Connection`, `Statement`, `Result`.

## 10. Transaction reactive với `R2dbcTransactionManager`

Transaction reactive cần phối hợp connection và transaction state theo subscription context. Spring cung cấp `R2dbcTransactionManager` để quản lý transaction cho một `ConnectionFactory`, và `TransactionalOperator` để kết hợp transaction với `Mono`/`Flux`.

```java
@Configuration
class DatabaseConfiguration {
    @Bean
    R2dbcTransactionManager transactionManager(
            ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }

    @Bean
    TransactionalOperator transactionalOperator(
            R2dbcTransactionManager transactionManager) {
        return TransactionalOperator.create(transactionManager);
    }
}
```

Service có thể đặt nhiều thao tác database trong cùng transaction:

```java
Mono<OrderEntity> createOrder(
        OrderEntity order,
        TransactionalOperator tx,
        OrderRepository orderRepository,
        InventoryRepository inventoryRepository) {

    Mono<OrderEntity> work = orderRepository.save(order)
        .flatMap(saved -> inventoryRepository.reserve(
                saved.getProductId(), saved.getQuantity()
            )
            .thenReturn(saved)
        );

    return tx.transactional(work);
}
```

`tx.transactional(work)` điều phối transaction cho publisher. Nếu publisher hoàn tất bình thường, transaction được commit; nếu phát lỗi, transaction được rollback theo cơ chế transaction manager. Các repository cần tham gia cùng transaction manager và `ConnectionFactory` để dùng chung transaction context.

### Transaction reactive không dựa trên ThreadLocal như transaction imperative

Trong reactive pipeline, các tín hiệu có thể đi qua nhiều thread. Transaction state được gắn với Reactor Context thông qua cơ chế Spring quản lý, không dựa vào việc mọi bước luôn chạy trên cùng một thread. Vì vậy, hãy giữ các thao tác trong cùng chuỗi publisher và tránh tự subscribe lồng nhau hoặc gọi `block()` giữa transaction.

Không nên:

```java
Mono<OrderEntity> unsafe = tx.transactional(
    orderRepository.save(order)
        .doOnNext(saved -> inventoryRepository
            .reserve(saved.getProductId(), saved.getQuantity())
            .block())
);
```

`block()` tạo một subscription riêng và phá vỡ chuỗi transaction reactive. Hãy dùng `flatMap`, `then` hoặc operator tương ứng để nối thao tác tiếp theo.

### Transaction phải ngắn và chỉ bao gồm công việc cần tính nguyên tử

Không giữ transaction mở trong lúc gọi API mạng chậm hoặc chờ người dùng. Một transaction dài giữ connection và có thể giữ lock, làm giảm throughput và tăng nguy cơ timeout. Nếu quy trình cần gọi dịch vụ bên ngoài rồi cập nhật database, hãy cân nhắc saga, outbox/inbox hoặc quy trình bù trừ thay vì giữ transaction database trong suốt thời gian gọi mạng.

## 11. Xử lý lỗi database và retry có điều kiện

Lỗi R2DBC có thể đến từ kết nối, timeout, vi phạm constraint, cú pháp SQL, mapping hoặc transaction. Hãy phân loại lỗi trước khi chọn operator.

```java
Mono<Customer> loadCustomer(long id) {
    return customerRepository.findById(id)
        .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)))
        .onErrorMap(R2dbcTransientResourceException.class,
            error -> new DatabaseUnavailableException(error));
}
```

`onErrorMap` chuyển lỗi kỹ thuật thành lỗi ở tầng ứng dụng. Không nên đổi mọi exception thành cùng một lỗi chung nếu cần phân biệt not found, constraint violation và database unavailable.

### Retry chỉ an toàn khi thao tác có thể lặp

Một truy vấn đọc thường có thể retry khi gặp lỗi kết nối tạm thời. Một lệnh ghi có thể đã được database thực hiện nhưng response bị mất; retry mù quáng có thể tạo bản ghi trùng hoặc lặp side effect.

```java
Mono<Customer> readWithRetry(long id) {
    return customerRepository.findById(id)
        .retryWhen(Retry.backoff(2, Duration.ofMillis(100))
            .filter(this::isTransientDatabaseFailure));
}
```

Với thao tác ghi, hãy dùng khóa idempotency, unique constraint hoặc transaction boundary phù hợp trước khi retry. Retry cần giới hạn số lần, có backoff và không retry lỗi dữ liệu vĩnh viễn như vi phạm constraint.

### Không che giấu lỗi bằng giá trị rỗng

`onErrorResume(error -> Mono.empty())` biến lỗi thành hoàn tất rỗng. Điều này có thể khiến caller hiểu nhầm rằng không có dữ liệu hoặc thao tác thành công mà không có kết quả. Chỉ dùng fallback rỗng khi nghiệp vụ định nghĩa rõ lỗi đó có thể được bỏ qua.

## 12. Backpressure, streaming và tài nguyên database

Một `Flux<Row>` có thể phát nhiều hàng theo demand, nhưng query vẫn sử dụng connection trong thời gian kết quả còn được tiêu thụ. Nếu downstream xử lý chậm, connection có thể bị giữ lâu hơn dự kiến.

Một số nguyên tắc:

- Chọn cột cần thiết thay vì `SELECT *`.
- Dùng filter, sort và limit ở SQL để giảm dữ liệu phải truyền về ứng dụng.
- Đọc theo batch hoặc keyset pagination với tập dữ liệu lớn.
- Tránh `collectList()` nếu số hàng không có giới hạn rõ ràng.
- Không gọi API mạng chậm trong lúc đang giữ cursor/connection nếu có thể tách thành giai đoạn khác.
- Giới hạn concurrency của các truy vấn đồng thời theo connection pool và năng lực database.
- Đặt timeout cho query và thời gian chờ lấy connection.
- Theo dõi pool usage, query latency, số connection đang mượn và thời gian xử lý từng hàng.

Ví dụ giới hạn số truy vấn đồng thời:

```java
Flux<CustomerSummary> summaries = customerIds.flatMap(
    id -> customerRepository.findById(id)
        .map(this::toSummary),
    12
);
```

Concurrency 12 có nghĩa tối đa 12 publisher con đang hoạt động qua `flatMap`. Giá trị phù hợp phụ thuộc kích thước pool, số connection dành cho các luồng khác, thời gian query và giới hạn database. Không nên đặt concurrency bằng kích thước pool mà quên rằng health check, transaction khác và request khác cũng cần connection.

### Backpressure không thay thế giới hạn truy vấn

Backpressure điều tiết việc phát và tiêu thụ phần tử trong pipeline. Nó không tự giới hạn chi phí query, số hàng database phải scan hoặc lượng dữ liệu driver đã fetch. Cần tối ưu SQL, index, fetch strategy và pagination cùng với demand.

## 13. Không trộn JDBC blocking vào pipeline R2DBC

R2DBC chỉ giữ được lợi ích non-blocking nếu toàn bộ đường đi I/O không bị chặn bởi một API đồng bộ. Nếu một bước vẫn phải dùng JDBC hoặc thư viện blocking, hãy cô lập nó trên `Schedulers.boundedElastic()`.

```java
Mono<LegacyCustomer> loadLegacyCustomer(long id) {
    return Mono.fromCallable(() -> jdbcDao.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
}
```

Không chạy JDBC trên event loop hoặc `Schedulers.parallel()`. Không dùng `block()` để nối JDBC với R2DBC. Nếu có thể, hãy chuyển phần truy cập dữ liệu đó sang driver reactive để giữ pipeline non-blocking xuyên suốt.

## 14. Kiểm thử truy vấn và mapping bằng `StepVerifier`

Vì repository và `DatabaseClient` trả publisher, có thể kiểm thử logic service bằng `StepVerifier`. Unit test thường mock repository để xác minh cách pipeline xử lý kết quả, empty và error.

Ví dụ kiểm thử kết quả:

```java
when(customerRepository.findById(42L))
    .thenReturn(Mono.just(new CustomerEntity(42L, "a@example.test")));

StepVerifier.create(customerService.loadCustomer(42L))
    .assertNext(customer -> {
        assertEquals(42L, customer.getId());
        assertEquals("a@example.test", customer.getEmail());
    })
    .verifyComplete();
```

Kiểm thử trường hợp không tìm thấy:

```java
when(customerRepository.findById(99L))
    .thenReturn(Mono.empty());

StepVerifier.create(customerService.loadCustomer(99L))
    .expectError(CustomerNotFoundException.class)
    .verify();
```

Kiểm thử mapping SQL thực tế cần một database test tương thích R2DBC, chẳng hạn Testcontainers với image database phù hợp hoặc H2 R2DBC nếu cú pháp và tính năng được dùng tương thích. Unit test mock không phát hiện được lỗi tên cột, bind parameter, kiểu dữ liệu, SQL dialect hoặc transaction thực tế.

### Những trường hợp cần kiểm thử

- Query trả đúng một hàng, không có hàng và nhiều hơn một hàng khi dùng `one()`.
- `first()` chọn hàng theo `ORDER BY` xác định.
- `all()` phát đúng số hàng và không gom toàn bộ dữ liệu ngoài ý muốn.
- Null parameter được bind bằng `bindNull` đúng kiểu.
- Kiểu SQL được ánh xạ đúng sang Java, gồm timestamp, decimal, UUID và enum nếu có.
- `rowsUpdated()` trả số hàng phù hợp với điều kiện update/delete.
- Transaction commit khi thành công và rollback khi lỗi.
- Retry chỉ áp dụng cho lỗi tạm thời và không lặp side effect ngoài ý muốn.
- Cancellation dừng việc tiêu thụ kết quả và trả connection về pool.
- Query timeout và connection acquisition timeout được xử lý đúng.

Với kiểm thử transaction, cần xác minh dữ liệu sau khi transaction kết thúc, không chỉ xác minh publisher phát complete. Với kiểm thử cancellation, cần quan sát connection pool hoặc tài nguyên để xác nhận connection được trả về.

## 15. Tình huống thực tế: đọc đơn hàng và chi tiết theo luồng

Một API cần trả về danh sách đơn hàng gần đây cùng tổng tiền. Có thể để database thực hiện join và aggregate thay vì tải từng bảng rồi gọi nhiều query riêng:

```java
record OrderSummary(
    Long orderId,
    String orderNumber,
    BigDecimal total,
    Instant createdAt
) {}

Flux<OrderSummary> recentOrderSummaries(int limit) {
    return databaseClient.sql("""
            SELECT o.id AS order_id,
                   o.order_number,
                   COALESCE(SUM(l.quantity * l.unit_price), 0) AS total,
                   o.created_at
            FROM orders o
            LEFT JOIN order_line l ON l.order_id = o.id
            GROUP BY o.id, o.order_number, o.created_at
            ORDER BY o.created_at DESC, o.id DESC
            LIMIT :limit
            """)
        .bind("limit", limit)
        .map((row, metadata) -> new OrderSummary(
            row.get("order_id", Long.class),
            row.get("order_number", String.class),
            row.get("total", BigDecimal.class),
            row.get("created_at", Instant.class)
        ))
        .all();
}
```

API có thể chuyển kết quả thành response reactive:

```java
@GetMapping("/orders/recent")
Flux<OrderSummary> recentOrders(
        @RequestParam(defaultValue = "50") int limit) {
    int safeLimit = Math.min(Math.max(limit, 1), 200);
    return orderQueries.recentOrderSummaries(safeLimit);
}
```

`limit` được kiểm soát trong ứng dụng và bind vào query. SQL join và aggregate giảm số lượt gọi database so với N+1 query. `Flux` cho phép server chuyển kết quả theo luồng; kích thước trang vẫn cần giới hạn để bảo vệ database và ứng dụng.

Nếu API cần transaction nhất quán giữa nhiều query, hãy đưa các publisher database vào cùng `TransactionalOperator`. Nếu chỉ có một query đọc, transaction tường minh thường không cần thiết trừ khi yêu cầu isolation của nghiệp vụ đòi hỏi.

## 16. Checklist khi xây dựng truy cập dữ liệu R2DBC

- Chọn driver R2DBC tương thích database và phiên bản framework.
- Quản lý URL, username và password qua cấu hình an toàn.
- Cấu hình connection pool với giới hạn dựa trên tổng tải database.
- Dùng `DatabaseClient`, `ReactiveCrudRepository` hoặc `R2dbcEntityTemplate` theo mức độ truy vấn cần thiết.
- Bind mọi giá trị đầu vào; dùng `bindNull` cho tham số null có kiểu.
- Chọn `one()`, `first()`, `all()` hoặc `rowsUpdated()` theo cardinality và ý nghĩa kết quả.
- Thêm `ORDER BY` khi thứ tự hàng có ý nghĩa.
- Ánh xạ từng hàng bằng mapper nhẹ; không thực hiện I/O khác bên trong mapper.
- Xử lý tập dữ liệu lớn bằng streaming, batch hoặc keyset pagination; tránh gom toàn bộ vào list.
- Dùng `usingWhen` nếu quản lý connection trực tiếp ở SPI; bảo đảm cleanup trên complete, error và cancel.
- Dùng `R2dbcTransactionManager`/`TransactionalOperator` cho transaction reactive.
- Giữ transaction ngắn; không gọi `block()` hoặc `subscribe()` lồng nhau trong transaction.
- Phân loại lỗi database; retry có giới hạn và chỉ với thao tác an toàn khi lặp.
- Giới hạn concurrency theo pool và năng lực database.
- Không chạy JDBC blocking trên event loop; cô lập legacy I/O trên `boundedElastic`.
- Kiểm thử cả logic publisher và SQL thực tế bằng database tương thích R2DBC.

R2DBC đưa truy cập cơ sở dữ liệu quan hệ vào mô hình Publisher–Subscriber để ứng dụng có thể kết hợp query, mapping và transaction với `Mono`/`Flux`. `DatabaseClient` và Spring Data R2DBC giúp quản lý phần lớn vòng đời kết nối, còn `usingWhen` phù hợp khi cần thao tác trực tiếp ở SPI. Khi phối hợp demand, query có giới hạn, connection pool, transaction reactive và kiểm thử với database thật, pipeline có thể xử lý dữ liệu bất đồng bộ mà vẫn kiểm soát được tài nguyên và tính nhất quán.

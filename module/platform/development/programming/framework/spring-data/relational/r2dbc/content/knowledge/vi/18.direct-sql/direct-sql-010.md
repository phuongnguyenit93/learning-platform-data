# Sử dụng R2DBC SPI trực tiếp và nghĩa vụ quản lý kết quả, tài nguyên

Spring Data Relational R2DBC cung cấp repository, mapping metadata và các abstraction giúp ứng dụng thao tác với database theo kiểu reactive. Trong một số trường hợp, ứng dụng cần kiểm soát chi tiết hơn: dùng API đặc thù của driver, thực hiện lệnh SQL động, đọc nhiều result segment, lấy generated key hoặc kết hợp nhiều thao tác trên cùng một connection. Khi đó có thể làm việc trực tiếp với R2DBC SPI.

R2DBC SPI là bộ giao diện chuẩn cho truy cập cơ sở dữ liệu quan hệ theo kiểu reactive. Những thành phần quan trọng gồm `ConnectionFactory`, `Connection`, `Statement`, `Result`, `Row` và `RowMetadata`. SPI cung cấp các publisher để mở connection, thực thi statement, đọc kết quả và đóng tài nguyên.

Dùng SPI trực tiếp đồng nghĩa ứng dụng phải hiểu và quản lý vòng đời của các tài nguyên đó. Connection phải được đóng hoặc trả về pool trên mọi đường kết thúc; result phải được tiêu thụ đúng cách; row chỉ được đọc trong thời gian callback mapping; transaction phải được commit hoặc rollback; và cancellation cũng phải kích hoạt cleanup.

Bài học này trình bày cấu trúc R2DBC SPI, cách mở và giải phóng connection, cách bind parameter, đọc row và metadata, xử lý update count và generated values, quản lý transaction, batch, lỗi và cancellation, cùng các trường hợp nên dùng SPI trực tiếp thay vì repository.

## 1. R2DBC SPI nằm ở đâu trong kiến trúc?

Một ứng dụng Spring Data R2DBC thường có các tầng:

~~~text
Service
   |
   v
Reactive Repository / DatabaseClient
   |
   v
Spring Data Relational
   |
   v
R2DBC SPI
   |
   v
R2DBC Driver
   |
   v
Database
~~~

Repository và `DatabaseClient` sử dụng R2DBC SPI ở bên dưới. Khi dùng repository, Spring Data tạo câu SQL, bind tham số và ánh xạ dữ liệu theo entity metadata. Khi dùng `DatabaseClient`, ứng dụng kiểm soát SQL và cách map kết quả nhiều hơn nhưng vẫn dùng abstraction của Spring.

Khi gọi R2DBC SPI trực tiếp, ứng dụng làm việc gần driver hơn:

- Tự yêu cầu connection từ `ConnectionFactory`.
- Tạo `Statement` trên connection.
- Bind các tham số theo quy tắc của driver.
- Gọi `execute()` và tiêu thụ các `Result`.
- Đọc `Row` hoặc update count.
- Đóng connection khi công việc hoàn tất, lỗi hoặc bị hủy.
- Tự quản lý transaction nếu cần.

R2DBC SPI không phải API JDBC bất đồng bộ. Các thao tác trả về Reactive Streams Publisher, vì vậy không dùng `block()` hoặc gọi API đồng bộ để chờ kết quả trong luồng reactive.

## 2. Các thành phần cốt lõi của R2DBC SPI

| Thành phần | Vai trò |
|---|---|
| `ConnectionFactory` | Cung cấp connection tới database |
| `Connection` | Đại diện một phiên làm việc với database |
| `Statement` | Đại diện câu SQL được chuẩn bị để thực thi |
| `Result` | Đại diện kết quả của một lần thực thi statement |
| `Row` | Đại diện một hàng dữ liệu được đọc |
| `RowMetadata` | Cung cấp metadata của các cột trong hàng |
| `ColumnMetadata` | Mô tả tên, kiểu và thuộc tính của cột |
| `ConnectionFactoryMetadata` | Cung cấp thông tin về connection factory/driver |

Luồng truy vấn cơ bản:

~~~text
ConnectionFactory.create()
        |
        v
     Connection
        |
        v
createStatement(sql)
        |
        v
bind parameters
        |
        v
Statement.execute()
        |
        v
      Result
        |
        +---- map(Row, RowMetadata) ----> dữ liệu
        |
        +---- getRowsUpdated() ---------> số hàng thay đổi
        |
        v
Connection.close()
~~~

Các phương thức SPI thường trả về `Publisher` thay vì `Mono` hoặc `Flux`. Trong ứng dụng Reactor, dùng `Mono.from(...)` hoặc `Flux.from(...)` để chuyển đổi publisher theo số lượng phần tử cần xử lý.

Ví dụ, `ConnectionFactory.create()` trả về một publisher có thể phát connection. Một lần gọi `Statement.execute()` có thể phát ra một hoặc nhiều `Result`, tùy statement và driver.

## 3. Lấy connection từ ConnectionFactory

`ConnectionFactory` là điểm bắt đầu để mở connection:

~~~java
Publisher<? extends Connection> publisher =
        connectionFactory.create();
~~~

Trong ứng dụng Reactor, có thể chuyển sang `Mono`:

~~~java
Mono<Connection> connectionMono =
        Mono.from(connectionFactory.create());
~~~

Không gọi `block()` để lấy connection trong service reactive:

~~~java
// Không nên trong reactive application.
Connection connection = Mono.from(connectionFactory.create()).block();
~~~

Cách này chặn thread cho tới khi có connection và làm mất lợi ích non-blocking. Hãy nối các thao tác tiếp theo bằng `flatMap`, `map`, `usingWhen` hoặc các toán tử Reactor phù hợp.

### 3.1. ConnectionFactory và connection pool

Trong ứng dụng Spring, `ConnectionFactory` thường được cấu hình bởi starter/auto-configuration hoặc do ứng dụng khai báo. Có thể dùng connection pool để tái sử dụng kết nối vật lý.

Khi lấy connection từ pool, `Connection.close()` thường trả connection về pool để tái sử dụng; nó không nhất thiết đóng socket vật lý. Ứng dụng vẫn phải gọi close để pool biết connection đã được trả lại.

Không giữ connection trong field của singleton service để dùng chung giữa các request. Connection là tài nguyên có trạng thái: transaction, auto-commit, isolation và statement có thể ảnh hưởng các thao tác khác nếu dùng sai vòng đời.

## 4. Nghĩa vụ quan trọng nhất: đóng connection trên mọi đường kết thúc

Khi dùng SPI trực tiếp, ứng dụng phải bảo đảm connection được giải phóng khi:

- Công việc hoàn tất thành công.
- Truy vấn phát lỗi.
- Mapping dữ liệu phát lỗi.
- Subscriber hủy subscription.
- Request timeout hoặc client ngắt kết nối.

Không chỉ đóng connection trong nhánh thành công. Nếu có lỗi trước khi gọi close, connection có thể bị rò rỉ và làm cạn pool.

### 4.1. Dùng usingWhen để quản lý tài nguyên bất đồng bộ

Reactor có `usingWhen` dành cho tài nguyên cần cleanup trả về publisher. Đây là cách phù hợp với `Connection.close()` vì close cũng là thao tác reactive.

Ví dụ đọc nhiều hàng:

~~~java
Flux<Customer> findCustomers(String city) {
    return Flux.usingWhen(
            connectionFactory.create(),
            connection -> {
                Statement statement = connection.createStatement("""
                        SELECT id, customer_name
                        FROM customer
                        WHERE city = ?
                        """);

                statement.bind(0, city);

                return Flux.from(statement.execute())
                        .concatMap(result ->
                                Flux.from(result.map((row, metadata) ->
                                        new Customer(
                                                row.get("id", Long.class),
                                                row.get("customer_name", String.class)))));
            },
            connection -> Mono.from(connection.close()),
            (connection, error) ->
                    Mono.from(connection.close()),
            connection -> Mono.from(connection.close())
    );
}
~~~

Ba callback cleanup lần lượt xử lý:

1. Publisher hoàn tất bình thường.
2. Publisher kết thúc bằng lỗi.
3. Publisher bị cancellation.

`usingWhen` đợi cleanup publisher hoàn tất theo semantics của Reactor. Điều này quan trọng vì `Connection.close()` là asynchronous; chỉ gọi method mà không nối publisher thì không bảo đảm close đã hoàn tất.

Ví dụ trên minh họa mapping đơn giản; constructor và kiểu dữ liệu phải khớp entity thực tế. Nếu connection factory hoặc driver có hành vi riêng, hãy kiểm tra tài liệu tương ứng.

### 4.2. Vì sao không dùng doFinally để đóng connection?

`doFinally` nhận tín hiệu kết thúc nhưng callback của nó không trả về publisher để Reactor chờ. Nếu gọi:

~~~java
.doFinally(signal -> connection.close())
~~~

publisher close được tạo ra nhưng không được subscribe như một phần của chuỗi cleanup. Vì vậy, không thể bảo đảm tài nguyên được trả về pool đúng thời điểm.

Tương tự, không nên gọi `close().subscribe()` bên trong `doOnTerminate`, `doOnError` hoặc `finally` để tạo một subscription tách rời. Hãy dùng `usingWhen` hoặc một cấu trúc composition có cleanup publisher rõ ràng.

### 4.3. Không dùng try-with-resources cho connection reactive

`Connection` không nên được quản lý theo kiểu đồng bộ như một tài nguyên đóng ngay khi thoát khỏi block:

~~~java
// Không phù hợp với connection được sử dụng bất đồng bộ.
try (Connection connection = ...) {
    // execute reactive operation
}
~~~

Publisher có thể chưa thực thi xong khi block Java kết thúc. Connection khi đó bị đóng trước khi truy vấn hoàn thành. `usingWhen` được thiết kế để cleanup gắn với vòng đời bất đồng bộ.

## 5. Tạo Statement và bind parameter

Tạo statement từ connection:

~~~java
Statement statement = connection.createStatement(
        "SELECT id, customer_name FROM customer WHERE id = ?");
~~~

Sau đó bind giá trị. Chỉ số bind trong R2DBC SPI bắt đầu từ 0:

~~~java
statement.bind(0, 10L);
~~~

Ví dụ dùng `DatabaseClient` có thể dùng named parameter, nhưng SPI trực tiếp làm việc theo khả năng bind mà driver cung cấp. Cú pháp placeholder trong SQL phụ thuộc driver/dialect: có driver dùng `?`, có driver dùng `$1`, hoặc cú pháp khác. Không giả định một câu SQL placeholder có thể chạy trên mọi driver.

### 5.1. Bind giá trị null bằng bindNull

Không gọi `bind(index, null)` để bind SQL NULL. R2DBC SPI cung cấp `bindNull` để khai báo kiểu Java của giá trị null:

~~~java
statement.bindNull(0, String.class);
~~~

Ví dụ:

~~~java
Statement statement = connection.createStatement("""
        INSERT INTO customer (customer_name, phone_number)
        VALUES (?, ?)
        """);

statement.bind(0, "Nguyen An");
statement.bindNull(1, String.class);
~~~

Kiểu Java được cung cấp giúp driver xác định cách bind giá trị null. Chọn kiểu tương thích với cột và mapping của driver.

### 5.2. Không nối dữ liệu người dùng vào SQL

Không tạo SQL bằng cách nối trực tiếp chuỗi đầu vào:

~~~java
// Không an toàn.
String sql = "SELECT * FROM customer WHERE name = '" + name + "'";
~~~

Hãy bind parameter:

~~~java
Statement statement = connection.createStatement(
        "SELECT id, customer_name FROM customer WHERE customer_name = ?");

statement.bind(0, name);
~~~

Parameter binding giúp tách dữ liệu khỏi cấu trúc SQL và ngăn injection qua giá trị. Tuy nhiên, không thể bind tên bảng, tên cột hoặc từ khóa sort như một giá trị thông thường. Các identifier động cần được chọn từ whitelist do ứng dụng kiểm soát.

## 6. Thực thi Statement và tiêu thụ Result

`Statement.execute()` trả về publisher của `Result`:

~~~java
Publisher<? extends Result> results = statement.execute();
~~~

Không nên giả định `execute()` trả về một entity hoặc một hàng trực tiếp. Ứng dụng cần tiêu thụ từng `Result` bằng API phù hợp:

- `Result.map(...)` để đọc các hàng.
- `Result.getRowsUpdated()` để đọc số hàng bị thay đổi.
- `Result.flatMap(...)` để xử lý result segment khi cần.

Ví dụ đọc hàng:

~~~java
Flux<Customer> customers =
        Flux.from(statement.execute())
                .concatMap(result ->
                        Flux.from(result.map((row, metadata) ->
                                new Customer(
                                        row.get("id", Long.class),
                                        row.get("customer_name", String.class)))));
~~~

`concatMap` xử lý từng result theo thứ tự. Nếu dùng `flatMap`, nhiều publisher con có thể được xử lý đồng thời; với một statement có nhiều result hoặc thứ tự có ý nghĩa, `concatMap` thường dễ kiểm soát hơn.

Không bỏ qua result sau khi execute. Việc tiêu thụ kết quả là một phần của giao thức driver và có thể cần thiết để giải phóng tài nguyên hoặc cho phép connection thực hiện statement tiếp theo.

### 6.1. Mỗi Result phải được tiêu thụ theo đúng kiểu

Với SELECT, dùng `map` để đọc hàng. Với UPDATE/DELETE, dùng `getRowsUpdated` để nhận số hàng bị tác động. Không gọi đồng thời nhiều cách tiêu thụ trên cùng một `Result` nếu driver/SPI không cho phép; chọn cách phù hợp với loại kết quả và tiêu thụ nó một lần theo contract.

Nếu statement trả nhiều result, xử lý từng result được phát ra. Nếu statement là batch hoặc stored procedure, có thể có nhiều result segment hoặc kiểu output khác nhau tùy driver.

## 7. Đọc Row và RowMetadata

`Row` chứa các giá trị của một hàng. `RowMetadata` mô tả các cột trong hàng, ví dụ tên cột, kiểu dữ liệu và thông tin khác do driver cung cấp.

Đọc theo nhãn:

~~~java
String customerName =
        row.get("customer_name", String.class);
~~~

Đọc theo index:

~~~java
Long id = row.get(0, Long.class);
~~~

Dùng nhãn thường dễ đọc hơn khi SQL có alias. Dùng index có thể phù hợp khi query cố định và cần kiểm soát vị trí cột.

### 7.1. Row chỉ có ý nghĩa trong callback mapping

Không lưu `Row` vào field hoặc trả nó ra ngoài callback:

~~~java
// Không nên: Row gắn với vòng đời của result/driver.
AtomicReference<Row> savedRow = new AtomicReference<>();

result.map((row, metadata) -> {
    savedRow.set(row);
    return row;
});
~~~

`Row` là view trên dữ liệu do driver quản lý. Sau khi callback hoàn tất hoặc result được tiêu thụ, ứng dụng không nên tiếp tục truy cập row cũ. Hãy chuyển các giá trị cần thiết thành object Java ngay trong callback:

~~~java
result.map((row, metadata) ->
        new Customer(
                row.get("id", Long.class),
                row.get("customer_name", String.class)));
~~~

Đối tượng `Customer` được tạo từ các giá trị đã đọc và có thể được dùng sau đó theo vòng đời ứng dụng.

### 7.2. Dùng RowMetadata

Có thể đọc metadata của cột:

~~~java
result.map((row, metadata) -> {
    String firstColumnName =
            metadata.getColumnMetadata(0).getName();

    Long id = row.get("id", Long.class);

    return new CustomerIdView(id, firstColumnName);
});
~~~

`RowMetadata` hữu ích khi viết mapper tổng quát, log cấu trúc result set hoặc xử lý SQL động. Với query cố định, không cần đọc metadata cho mọi hàng nếu không có nhu cầu.

Tên cột, chữ hoa/chữ thường và kiểu dữ liệu được driver cung cấp theo dialect. Nếu alias có quote hoặc trùng tên, hãy chọn alias riêng và kiểm tra metadata thực tế.

### 7.3. Giá trị SQL NULL

Một cột nullable có thể trả về Java `null`:

~~~java
String phoneNumber = row.get("phone_number", String.class);
~~~

Nếu cột là SQL NULL, `phoneNumber` có thể null. Không dùng primitive Java khi cột có thể null; dùng wrapper như `Long`, `Integer` hoặc `Boolean`.

Phân biệt:

- Không có hàng: result không phát row.
- Có hàng nhưng cột là SQL NULL: mapper được gọi và giá trị cột có thể null.
- Truy vấn lỗi: publisher phát `onError`.

## 8. Đọc nhiều hàng và giữ reactive stream

Với SELECT nhiều hàng, mỗi `Result` có thể phát nhiều row. Có thể chuyển các row thành `Flux<T>`:

~~~java
Flux<Customer> findAllCustomers(Connection connection) {
    Statement statement = connection.createStatement("""
            SELECT id, customer_name
            FROM customer
            ORDER BY id
            """);

    return Flux.from(statement.execute())
            .concatMap(result ->
                    Flux.from(result.map((row, metadata) ->
                            new Customer(
                                    row.get("id", Long.class),
                                    row.get("customer_name", String.class)))));
}
~~~

Phương thức trên nhận connection đã được cấp; nó không sở hữu connection và không đóng connection. Quyền sở hữu tài nguyên cần rõ ràng: nơi mở connection phải bảo đảm nơi đó đóng connection sau khi publisher hoàn tất.

Nếu phương thức trả `Flux` và tự mở connection, dùng `Flux.usingWhen` để gắn vòng đời connection với toàn bộ stream. Nếu caller truyền connection vào, caller chịu trách nhiệm cleanup.

Không thu thập mọi row thành list nếu result set lớn. `Flux` cho phép xử lý từng hàng và hỗ trợ backpressure; `collectList()` chỉ nên dùng khi số lượng kết quả được giới hạn hợp lý.

## 9. Đọc update count bằng getRowsUpdated

Với câu lệnh UPDATE hoặc DELETE, ứng dụng thường cần số hàng bị ảnh hưởng:

~~~java
Mono<Long> updateCustomerName(
        Connection connection,
        Long id,
        String name) {

    Statement statement = connection.createStatement("""
            UPDATE customer
            SET customer_name = ?
            WHERE id = ?
            """);

    statement.bind(0, name);
    statement.bind(1, id);

    return Mono.from(statement.execute())
            .flatMap(result ->
                    Mono.from(result.getRowsUpdated()));
}
~~~

`getRowsUpdated()` trả về publisher số hàng bị thay đổi. Kiểu `Long` phù hợp với SPI vì số hàng có thể lớn hơn giới hạn `int`.

Cần phân biệt:

- Phát `0`: statement chạy thành công nhưng không có hàng nào bị ảnh hưởng.
- Phát số dương: có hàng bị ảnh hưởng.
- `onError`: statement thất bại, ví dụ lỗi SQL hoặc constraint.
- Publisher hoàn tất mà không phát count: tùy statement/driver; không nên tự giả định luôn có một giá trị nếu driver không cung cấp.

Không dùng `Result.map` để đọc update count. Dùng đúng API `getRowsUpdated()`.

## 10. Lấy generated values

Một số driver hỗ trợ yêu cầu trả về giá trị được database tạo, ví dụ khóa chính tự tăng. SPI có `Statement.returnGeneratedValues(...)` khi driver hỗ trợ.

Ví dụ:

~~~java
Mono<Long> insertCustomer(Connection connection, String name) {
    Statement statement = connection.createStatement("""
            INSERT INTO customer (customer_name)
            VALUES (?)
            """);

    statement.bind(0, name);
    statement.returnGeneratedValues("id");

    return Mono.from(statement.execute())
            .flatMap(result ->
                    Mono.from(result.map((row, metadata) ->
                            row.get("id", Long.class))));
}
~~~

Khả năng trả generated values và tên cột cần yêu cầu phụ thuộc database/driver. Một số database có cú pháp `RETURNING`; driver có thể dùng cú pháp riêng để triển khai. Kiểm tra tài liệu driver và integration test.

Nếu driver không hỗ trợ `returnGeneratedValues`, cần dùng cách lấy ID phù hợp với database, chẳng hạn sequence hoặc truy vấn theo cơ chế được hỗ trợ. Không suy ra ID bằng cách gọi `MAX(id)` sau insert vì request đồng thời có thể tạo bản ghi khác.

## 11. Bind nhiều bộ giá trị và batch statement

R2DBC SPI hỗ trợ thêm nhiều bộ binding cho một statement bằng `Statement.add()`:

~~~java
Statement statement = connection.createStatement("""
        INSERT INTO customer (customer_name, email_address)
        VALUES (?, ?)
        """);

statement.bind(0, "Nguyen An")
        .bind(1, "an@example.com")
        .add();

statement.bind(0, "Tran Binh")
        .bind(1, "binh@example.com");

Publisher<? extends Result> results = statement.execute();
~~~

Mỗi lần `add()` đưa bộ binding hiện tại vào batch và cho phép thiết lập bộ binding tiếp theo theo contract của SPI. Các giá trị cần được bind đầy đủ cho từng bộ.

Batch có thể giảm overhead khi ghi nhiều hàng, nhưng hành vi và hiệu năng phụ thuộc driver/database. Batch không tự động có nghĩa toàn bộ lệnh nằm trong một transaction; nếu cần tất cả cùng thành công hoặc rollback, hãy dùng transaction tường minh.

Nếu một phần tử trong batch lỗi, kết quả và trạng thái các phần tử khác phụ thuộc database, driver và transaction. Đừng giả định batch có tính nguyên tử nếu chưa đặt trong transaction.

## 12. Quản lý transaction trực tiếp qua Connection

R2DBC SPI cung cấp các thao tác transaction như:

- `beginTransaction()`
- `commitTransaction()`
- `rollbackTransaction()`
- `setTransactionIsolationLevel(...)`
- `setAutoCommit(...)`

Ví dụ, khi dùng transaction thủ công, chỉ commit sau khi mọi thao tác cần thiết hoàn tất. Nếu có lỗi, rollback.

Với Spring, thường nên ưu tiên `R2dbcTransactionManager` và `TransactionalOperator` để transaction context được quản lý thống nhất trong reactive pipeline. Chỉ tự điều khiển transaction qua SPI khi có yêu cầu đặc biệt và hiểu rõ connection ownership.

### 12.1. Ví dụ transaction và cleanup

Ví dụ khái quát sử dụng `usingWhen` để mở connection, bắt đầu transaction, commit khi thành công, rollback khi lỗi hoặc cancellation và cuối cùng đóng connection:

~~~java
Mono<Customer> createCustomerAtomically(String name) {
    return Mono.usingWhen(
            connectionFactory.create(),
            connection ->
                    Mono.from(connection.beginTransaction())
                            .then(insertCustomer(connection, name))
                            .flatMap(customer ->
                                    Mono.from(connection.commitTransaction())
                                            .thenReturn(customer)),
            connection ->
                    Mono.from(connection.close()),
            (connection, error) ->
                    Mono.from(connection.rollbackTransaction())
                            .onErrorResume(rollbackError -> Mono.empty())
                            .then(Mono.from(connection.close())),
            connection ->
                    Mono.from(connection.rollbackTransaction())
                            .onErrorResume(rollbackError -> Mono.empty())
                            .then(Mono.from(connection.close()))
    );
}
~~~

Đây là mẫu minh họa. Trong code production, cần cân nhắc cả lỗi khi `beginTransaction`, lỗi rollback và lỗi close; đồng thời ghi log lỗi cleanup mà không làm mất nguyên nhân gốc. Cấu hình driver, transaction manager và connection pool cũng ảnh hưởng hành vi thực tế.

Không trộn transaction do Spring quản lý với transaction tự điều khiển trên một connection khác. Nếu repository và SPI trực tiếp không dùng cùng connection/transaction context, chúng có thể chạy ở hai transaction khác nhau.

### 12.2. Isolation level và consistency

Có thể đặt isolation level khi nghiệp vụ cần mức nhất quán cụ thể. Hỗ trợ và semantics của các mức isolation phụ thuộc database. Không nâng isolation tùy tiện vì có thể làm tăng lock, contention hoặc chi phí versioning.

Một transaction phải có thời gian sống ngắn và gắn với một use case. Không giữ connection/transaction trong khi người dùng tương tác hoặc duyệt nhiều trang.

## 13. Lỗi và cancellation trong reactive pipeline

Reactive stream có ba tín hiệu chính:

- `onNext`: phát dữ liệu.
- `onComplete`: hoàn tất bình thường.
- `onError`: kết thúc do lỗi.

Ngoài ra subscriber có thể gửi cancellation. Cancellation không phải tín hiệu kết thúc do publisher phát ra; đó là yêu cầu dừng subscription.

Khi dùng R2DBC SPI trực tiếp, cleanup cần xử lý cả ba trường hợp kết thúc và cancellation. `usingWhen` cung cấp callback cleanup riêng cho success, error và cancel.

Không nên:

- Chỉ close connection trong `doOnSuccess`.
- Chỉ rollback khi bắt được exception đồng bộ.
- Gọi `subscribe()` để chạy cleanup tách rời.
- Giữ connection trong field và tái sử dụng sau cancellation.
- Bỏ qua publisher trả về từ `close`, `commit` hoặc `rollback`.

Nếu cleanup cũng lỗi, cần có chính sách logging và giữ lại lỗi gốc. Không nên âm thầm bỏ mọi lỗi cleanup trong production chỉ để pipeline trông như thành công.

## 14. Connection validation và trạng thái connection

Một connection có trạng thái, ví dụ transaction đang mở, auto-commit, isolation level hoặc savepoint. Không nên giả định connection vừa lấy từ pool luôn có trạng thái tùy ý mà ứng dụng mong muốn nếu pool/driver có cấu hình riêng.

SPI cung cấp API validation tùy driver, ví dụ `Connection.validate(...)`. Validation có thể hữu ích trong một số trường hợp nhưng không nên thay thế connection pool hoặc cơ chế quản lý connection chuẩn.

Sau khi sử dụng transaction, bảo đảm commit/rollback trước khi trả connection về pool. Nếu connection bị lỗi hoặc không thể cleanup, pool/driver có thể loại bỏ nó tùy implementation. Ứng dụng không được tiếp tục dùng connection sau khi đã close.

## 15. Khi nào nên dùng R2DBC SPI trực tiếp?

| Nhu cầu | Lựa chọn nên cân nhắc |
|---|---|
| CRUD entity thông thường | Spring Data repository |
| SQL tùy chỉnh, muốn giữ abstraction Spring | `DatabaseClient` |
| SQL động phức tạp, mapping thủ công | `DatabaseClient` hoặc SPI |
| Tính năng riêng của driver hoặc SPI result segment | R2DBC SPI trực tiếp |
| Quản lý statement, binding hoặc generated values đặc thù | R2DBC SPI trực tiếp nếu abstraction cao hơn không đủ |
| Muốn tự kiểm soát connection/transaction ở mức thấp | SPI trực tiếp, với trách nhiệm cleanup đầy đủ |
| Cần mapping entity, converter và naming strategy của Spring | Repository hoặc Spring Data mapping API |

Dùng SPI trực tiếp làm tăng trách nhiệm của ứng dụng. Hãy chọn nó khi cần quyền kiểm soát mà repository hoặc `DatabaseClient` không cung cấp thuận tiện. Với CRUD phổ biến, repository giúp code ngắn hơn, dễ kiểm thử và giảm nguy cơ rò rỉ connection.

## 16. Các lỗi thường gặp khi dùng R2DBC SPI

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Không gọi `Connection.close()` | Rò rỉ connection, cạn pool | Dùng `usingWhen` và cleanup success/error/cancel |
| Gọi `close()` nhưng không nối publisher | Cleanup có thể chưa chạy xong | Trả publisher close từ cleanup callback |
| Dùng `doFinally` để close bất đồng bộ | Reactor không chờ close publisher | Dùng `usingWhen` |
| Dùng `block()` để lấy connection | Chặn thread reactive | Nối publisher bằng `flatMap`/`usingWhen` |
| Dùng `bind(index, null)` | Bind null không hợp lệ | Dùng `bindNull(index, type)` |
| Dùng sai index bind | Giá trị gắn vào placeholder khác | Nhớ index bắt đầu từ 0 |
| Giả định placeholder giống nhau trên mọi driver | SQL không chạy trên dialect khác | Dùng cú pháp placeholder của driver mục tiêu |
| Không tiêu thụ `Result` | Result/connection có thể không được giải phóng đúng | Dùng `map`, `getRowsUpdated` hoặc API result phù hợp |
| Đọc `Row` sau callback | Dữ liệu có thể không còn hợp lệ | Map sang object Java ngay trong callback |
| Nhầm update count với row mapping | Không nhận được số hàng bị tác động | Dùng `getRowsUpdated()` |
| Không rollback khi lỗi hoặc cancel | Transaction có thể còn mở | Gắn rollback vào cleanup error/cancel |
| Trộn connection SPI với repository transaction khác | Thao tác không cùng transaction | Dùng chung transaction context hoặc cùng connection được quản lý |
| Dùng `MAX(id)` để lấy ID vừa insert | Có thể lấy ID của request khác | Dùng generated values/sequence phù hợp |
| Dùng batch nhưng cho rằng luôn atomic | Có thể ghi một phần khi lỗi | Dùng transaction nếu cần nguyên tử |
| Dùng một connection cho nhiều request đồng thời | Trạng thái và statement có thể xung đột | Mỗi operation có vòng đời connection rõ ràng |

## 17. Quy trình thực hiện một truy vấn SPI an toàn

Khi viết một thao tác trực tiếp bằng R2DBC SPI, hãy đi theo trình tự:

1. Xác định driver/dialect và cú pháp placeholder.
2. Lấy connection từ `ConnectionFactory` trong reactive pipeline.
3. Tạo statement và bind mọi giá trị, dùng `bindNull` cho SQL NULL.
4. Thực thi statement và tiêu thụ từng `Result`.
5. Với SELECT, map `Row` thành object trong callback.
6. Với UPDATE/DELETE, đọc `getRowsUpdated()`.
7. Nếu cần generated key, kiểm tra hỗ trợ `returnGeneratedValues` của driver.
8. Nếu nhiều thao tác cần atomicity, mở transaction và commit/rollback đúng nhánh.
9. Gắn cleanup connection cho success, error và cancellation bằng `usingWhen`.
10. Trả publisher cho caller; không tự subscribe hoặc block trong service.
11. Integration test trên đúng database/driver, bao gồm lỗi SQL, cancellation và cleanup.
12. Theo dõi pool metrics để phát hiện connection bị giữ quá lâu hoặc rò rỉ.

## 18. Kiểm thử vòng đời tài nguyên

Kiểm thử không chỉ cần xác nhận kết quả SQL. Cũng cần xác nhận connection được trả về khi:

- Truy vấn thành công.
- Truy vấn không có hàng.
- SQL phát lỗi.
- Mapping phát lỗi.
- Subscriber hủy subscription trước khi hoàn tất.
- Transaction bị rollback.

Có thể dùng `StepVerifier` để kiểm tra tín hiệu:

~~~java
StepVerifier.create(customerService.findCustomers("Hanoi"))
        .expectNextCount(2)
        .verifyComplete();
~~~

Với cancellation:

~~~java
StepVerifier.create(customerService.streamCustomers(), 0)
        .thenRequest(1)
        .expectNextCount(1)
        .thenCancel()
        .verify();
~~~

Để xác nhận cleanup, có thể dùng connection factory/driver test double có ghi nhận `close`, hoặc kiểm tra pool metrics trong integration test. Với transaction, xác nhận dữ liệu đã rollback sau khi cố ý gây lỗi giữa các thao tác.

Không chỉ test happy path. Resource leak thường chỉ xuất hiện sau nhiều request hoặc khi lỗi/cancellation xảy ra.

## 19. Ghi nhớ

- R2DBC SPI cung cấp các abstraction thấp hơn như `ConnectionFactory`, `Connection`, `Statement`, `Result`, `Row` và `RowMetadata`.
- Mọi thao tác đều reactive; không dùng `block()` trong chuỗi non-blocking.
- Ứng dụng mở connection phải bảo đảm close trên success, error và cancellation.
- Dùng `usingWhen` để chờ cleanup bất đồng bộ; `doFinally` không thay thế được cleanup publisher.
- Bind index bắt đầu từ 0; dùng `bindNull` để bind SQL NULL.
- Placeholder và một số khả năng như generated values phụ thuộc driver/database.
- Tiêu thụ `Result` bằng API phù hợp: `map` cho row và `getRowsUpdated` cho update count.
- Map `Row` thành object Java trong callback; không giữ Row để dùng sau.
- Transaction trực tiếp cần commit khi thành công và rollback khi lỗi hoặc cancellation.
- Không giả định batch tự atomic hoặc hai connection khác nhau dùng chung transaction.
- Ưu tiên repository hoặc `DatabaseClient` cho thao tác thông thường; dùng SPI trực tiếp khi cần quyền kiểm soát thấp hơn.
- Kiểm thử cả kết quả, lỗi, cancellation và việc giải phóng connection trên database/driver mục tiêu.


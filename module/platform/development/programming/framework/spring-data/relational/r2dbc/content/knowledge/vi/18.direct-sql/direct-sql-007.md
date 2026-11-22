# Tùy chỉnh Statement và các tùy chọn được trình điều khiển hỗ trợ

R2DBC SPI cung cấp `Connection.createStatement(sql)` để tạo một `Statement` thực thi câu SQL. Trước khi gọi `execute()`, ứng dụng có thể bind tham số, thêm nhiều bộ giá trị cho một batch và yêu cầu một số hành vi tùy chọn như lấy giá trị được database sinh ra hoặc gợi ý kích thước fetch.

Các tùy chọn này thuộc tầng R2DBC driver. SPI định nghĩa một số điểm mở rộng chung, nhưng không bảo đảm mọi driver đều hỗ trợ mọi tùy chọn hoặc có hành vi giống nhau. Khi dùng tính năng cụ thể của PostgreSQL, MySQL, SQL Server hay database khác, cần kiểm tra tài liệu và phiên bản driver thực tế.

## 1. Vòng đời của Statement

Một thao tác ở tầng SPI thường có trình tự:

1. Lấy `Connection` từ `ConnectionFactory` hoặc từ transaction đang quản lý.
2. Gọi `connection.createStatement(sql)` để tạo statement.
3. Bind các giá trị theo tên hoặc theo vị trí.
4. Áp dụng các tùy chọn mà driver hỗ trợ.
5. Gọi `execute()` để nhận publisher của `Result`.
6. Subscribe và tiêu thụ từng `Result` theo cách phù hợp: đọc hàng bằng `map(...)` hoặc lấy số hàng bị ảnh hưởng bằng `getRowsUpdated()`.
7. Đóng connection theo đúng vòng đời; nếu dùng transaction hoặc connection được quản lý bởi Spring, để transaction manager quản lý tài nguyên.

Ví dụ đọc dữ liệu bằng R2DBC SPI:

```java
Mono<Customer> findCustomer(ConnectionFactory factory, Long id) {
    return Mono.usingWhen(
        factory.create(),
        connection -> {
            Statement statement = connection.createStatement(
                "SELECT id, email FROM customer WHERE id = $1");
            statement.bind(0, id);

            return Flux.from(statement.execute())
                .flatMap(result -> result.map((row, metadata) ->
                    new Customer(
                        row.get("id", Long.class),
                        row.get("email", String.class))))
                .singleOrEmpty();
        },
        Connection::close,
        (connection, error) -> connection.close(),
        Connection::close
    );
}
```

Ví dụ dùng marker `$1` theo PostgreSQL R2DBC driver. Với driver khác, marker có thể khác. `bind(0, id)` dùng chỉ số bắt đầu từ 0 ở API SPI. `usingWhen` đảm bảo connection được đóng khi publisher hoàn tất, lỗi hoặc bị hủy.

Trong ứng dụng Spring Data R2DBC, thông thường nên dùng `DatabaseClient` hoặc `R2dbcEntityTemplate` thay vì tự tạo connection cho từng thao tác. Các abstraction này tích hợp tốt hơn với mapping, exception translation và transaction context của Spring. Làm việc trực tiếp với `Statement` phù hợp khi cần một tính năng SPI cụ thể hoặc cần kiểm soát SQL ở mức thấp.

## 2. Bind tham số trước khi thực thi

`Statement` hỗ trợ bind theo vị trí hoặc theo tên, tùy marker mà driver chấp nhận:

```java
Statement statement = connection.createStatement(
    "UPDATE customer SET email = $1 WHERE id = $2");

statement.bind(0, newEmail);
statement.bind(1, customerId);
```

Với bind theo tên, driver phải hỗ trợ marker có tên:

```java
Statement statement = connection.createStatement(
    "SELECT id FROM customer WHERE email = :email");

statement.bind("email", email);
```

Không phải driver nào cũng nhận named marker trực tiếp ở tầng SPI. Cú pháp `:email` thường được cung cấp như abstraction ở tầng Spring `DatabaseClient`, nơi framework có thể chuyển tên tham số thành marker native. Khi gọi `Connection.createStatement` trực tiếp, hãy theo đúng cú pháp của driver.

Giá trị null cần bind bằng `bindNull` và chỉ rõ kiểu Java:

```java
statement.bindNull(0, String.class);
```

Không dùng `bind(index, null)` vì driver không có đủ thông tin để xác định kiểu tham số. Cũng không nối dữ liệu đầu vào vào SQL. Bind chỉ áp dụng cho giá trị, không áp dụng cho tên bảng, tên cột hoặc từ khóa SQL.

## 3. Thêm nhiều bộ tham số bằng Statement.add()

`Statement.add()` cho phép thực thi cùng một câu SQL với nhiều bộ tham số. Sau khi bind xong một bộ giá trị, gọi `add()` để đưa bộ đó vào batch; sau đó bind bộ tiếp theo. Khi gọi `execute()`, driver xử lý các bộ đã thêm cùng với bộ cuối cùng hiện tại.

Ví dụ insert nhiều khách hàng:

```java
Statement statement = connection.createStatement(
    "INSERT INTO customer (email, display_name) VALUES ($1, $2)");

statement.bind(0, "an@example.com")
    .bind(1, "An")
    .add()
    .bind(0, "binh@example.com")
    .bind(1, "Binh");

Flux.from(statement.execute())
    .flatMap(Result::getRowsUpdated)
    .reduce(0L, Long::sum);
```

Trong ví dụ, `add()` chốt bộ tham số đầu tiên và reset trạng thái bind để nhận bộ tiếp theo. Bộ cuối cùng được thực thi khi gọi `execute()`, không cần gọi `add()` thêm lần nữa sau bộ cuối.

Batch bằng `Statement.add()` có một câu SQL và nhiều bộ giá trị. Nó khác với việc ghép nhiều câu SQL khác nhau bằng dấu chấm phẩy. Nếu mỗi thao tác có SQL khác nhau hoặc logic khác nhau, hãy thực hiện các statement riêng hoặc dùng cơ chế batch được database/driver hỗ trợ.

### 3.1 Khi nào batch có lợi?

Batch thường hữu ích khi nhập nhiều hàng cùng cấu trúc, cập nhật một tập bản ghi theo cùng câu lệnh hoặc giảm số lần round-trip giữa ứng dụng và database. Tuy nhiên, batch lớn có thể chiếm bộ nhớ, giữ connection lâu và làm tăng lượng công việc trong một transaction.

Nên chia dữ liệu thành batch có kích thước hợp lý. Kích thước tối ưu phụ thuộc độ rộng hàng, mạng, database, giới hạn bind marker và driver. Không nên mặc định gom toàn bộ file hoặc toàn bộ danh sách đầu vào vào một batch duy nhất.

### 3.2 Kết quả của batch

`execute()` trả về `Publisher<? extends Result>`. Tùy driver và cách thực thi, ứng dụng có thể nhận nhiều `Result`. Với lệnh cập nhật, có thể cộng số hàng bị ảnh hưởng:

```java
Mono<Long> totalUpdated = Flux.from(statement.execute())
    .flatMap(Result::getRowsUpdated)
    .reduce(0L, Long::sum);
```

Không giả định mọi driver trả một `Result` duy nhất cho toàn batch hoặc luôn cung cấp số lượng theo cùng cách. Hãy kiểm tra semantics của driver, đặc biệt khi cần biết số hàng cho từng bộ tham số hoặc cần xử lý lỗi ở giữa batch.

## 4. Yêu cầu giá trị do database sinh ra

Một số database có thể tạo giá trị khi insert, ví dụ khóa chính tự tăng, sequence value hoặc giá trị mặc định. `Statement.returnGeneratedValues(...)` cho phép yêu cầu driver trả lại các cột được database sinh ra nếu driver hỗ trợ tính năng này.

Ví dụ:

```java
Statement statement = connection.createStatement(
    "INSERT INTO customer (email) VALUES ($1)");

statement.bind(0, email);
statement.returnGeneratedValues("id");

Mono<Long> generatedId = Flux.from(statement.execute())
    .flatMap(result -> result.map((row, metadata) ->
        row.get("id", Long.class)))
    .single();
```

`returnGeneratedValues("id")` là yêu cầu đối với driver; nó không tự bảo đảm mọi driver hoặc mọi loại câu lệnh đều hỗ trợ. Nếu tính năng không được hỗ trợ, driver có thể báo `UnsupportedOperationException` hoặc lỗi thực thi tùy cách triển khai và phiên bản. Cần xác minh khả năng hỗ trợ trước khi phụ thuộc vào nó.

Với PostgreSQL, một cách khác là dùng cú pháp SQL `RETURNING id`:

```sql
INSERT INTO customer (email)
VALUES ($1)
RETURNING id;
```

`RETURNING` là cú pháp SQL của PostgreSQL, không phải cú pháp portable cho mọi database. Chọn `returnGeneratedValues` hoặc SQL native theo khả năng driver/database; tránh yêu cầu cùng một giá trị theo hai cơ chế mà không hiểu cách driver xử lý.

Khi dùng Spring `DatabaseClient`, có thể áp dụng statement filter nếu phiên bản API hỗ trợ để cấu hình `returnGeneratedValues` trước khi execute. Ví dụ minh họa:

```java
databaseClient.sql("INSERT INTO customer (email) VALUES (:email)")
    .bind("email", email)
    .filter((statement, next) ->
        next.execute(statement.returnGeneratedValues("id")))
    .map((row, metadata) -> row.get("id", Long.class))
    .one();
```

Chữ ký và vị trí của `filter` cần đối chiếu với phiên bản Spring Framework/Spring R2DBC trong dự án. Nếu driver không hỗ trợ generated values, hãy dùng cách được database cung cấp hoặc thiết kế ID do ứng dụng tạo trước khi insert.

## 5. Gợi ý fetch size

`Statement.fetchSize(int)` cho phép ứng dụng đưa ra gợi ý về số hàng nên được lấy trong mỗi lần fetch khi đọc kết quả. Tùy driver, gợi ý này có thể hỗ trợ đọc theo từng đợt thay vì tải toàn bộ kết quả về một lần.

Ví dụ:

```java
Statement statement = connection.createStatement("""
    SELECT id, email
    FROM customer
    ORDER BY id
    """);

statement.fetchSize(200);

Flux<Customer> customers = Flux.from(statement.execute())
    .flatMap(result -> result.map((row, metadata) ->
        new Customer(
            row.get("id", Long.class),
            row.get("email", String.class))));
```

`200` là gợi ý cho driver, không phải giới hạn tổng số hàng trả về và cũng không tương đương `LIMIT 200`. Truy vấn vẫn có thể trả về toàn bộ kết quả; fetch size chỉ ảnh hưởng cách driver lấy hoặc chuyển dữ liệu nếu driver triển khai hỗ trợ.

Một số driver bỏ qua fetch size hoặc chỉ hỗ trợ trong một số chế độ. Việc đọc theo cursor/server-side fetch có thể còn phụ thuộc transaction, autocommit, cấu hình kết nối và cách subscribe. Hãy xem tài liệu driver để biết điều kiện cụ thể.

Không đặt fetch size quá lớn chỉ vì muốn giảm số round-trip. Kích thước quá lớn có thể tăng bộ nhớ; quá nhỏ có thể tăng số lần trao đổi với database. Đo bằng dữ liệu và tải gần thực tế trước khi chọn giá trị.

## 6. Các tùy chọn Statement chuẩn và mức độ hỗ trợ

Một số phương thức của `Statement` là điểm mở rộng tùy chọn trong SPI:

| Phương thức | Mục đích | Điều cần xác minh |
|---|---|---|
| `bind(index, value)` | Bind giá trị theo vị trí | Marker native, kiểu Java và codec của driver. |
| `bind(name, value)` | Bind giá trị theo tên | Driver có hỗ trợ bind marker có tên ở tầng SPI hay không. |
| `bindNull(index/name, type)` | Bind SQL `NULL` có kiểu | Kiểu Java phải tương thích codec/cột. |
| `add()` | Thêm bộ tham số hiện tại vào batch | Cách driver thực thi batch và trả `Result`. |
| `returnGeneratedValues(columns...)` | Yêu cầu trả cột được sinh ra | Driver/database có hỗ trợ generated values cho câu lệnh đó hay không. |
| `fetchSize(rows)` | Gợi ý số hàng mỗi lần fetch | Driver có hỗ trợ streaming/cursor và điều kiện sử dụng. |
| `execute()` | Thực thi statement và trả kết quả reactive | Cách tiêu thụ `Result` đúng một lần theo từng result. |

SPI có thể cung cấp method chung nhưng không có nghĩa mọi driver phải thực hiện đầy đủ mọi tính năng tùy chọn. Với tùy chọn không được hỗ trợ, cần xử lý hành vi theo hợp đồng API và tài liệu phiên bản driver; không dựa vào một driver cụ thể rồi cho rằng tính năng portable.

## 7. Tùy chọn của ConnectionFactory khác với tùy chọn Statement

Không phải mọi cấu hình liên quan database đều thuộc `Statement`. `ConnectionFactoryOptions` dùng để cấu hình việc tạo connection/factory, ví dụ driver, host, port, database, username, password, SSL hoặc các tùy chọn riêng của driver. Pool có cấu hình riêng như kích thước tối đa, thời gian chờ acquire và thời gian sống connection.

Trong khi đó, `Statement` điều khiển một lần thực thi cụ thể: bind dữ liệu, batch, fetch size và generated values. Ví dụ:

| Phạm vi | Ví dụ cấu hình |
|---|---|
| Driver/ConnectionFactory | URL, host, port, database, SSL, authentication, schema mặc định tùy driver. |
| Connection pool | `maxSize`, `initialSize`, acquire timeout, idle/lifetime timeout tùy pool. |
| Statement | bind marker, `add()`, `fetchSize`, `returnGeneratedValues`. |
| Reactive flow | Subscription, cancellation, backpressure và cách tiêu thụ `Flux`/`Mono`. |
| Transaction | Transaction manager, isolation, read-only và phạm vi transaction. |

Một số tùy chọn như statement timeout hoặc query timeout không có API chuẩn đồng nhất trên `Statement` của R2DBC. Chúng thường được cấu hình qua driver/database, session hoặc cơ chế riêng. Nếu cần timeout, hãy xác định timeout ở đúng tầng: thời gian chờ lấy connection, thời gian thực thi query ở database, hoặc thời gian chờ của publisher không phải là cùng một khái niệm.

## 8. Tùy chọn riêng của driver

Driver có thể cung cấp cấu hình riêng ngoài những method chuẩn của `Statement`. Ví dụ, driver có thể cho phép bật chế độ cursor, điều chỉnh cách trả generated values, chọn kiểu dữ liệu đặc thù, điều khiển fetch behavior hoặc thiết lập session. Tên tùy chọn và cách bật phụ thuộc vendor.

Khi cần dùng tùy chọn riêng:

1. Xác định driver và phiên bản thực tế từ dependency tree hoặc runtime.
2. Đọc tài liệu chính thức đúng phiên bản, không dùng ví dụ từ driver khác.
3. Kiểm tra tùy chọn thuộc `ConnectionFactoryOptions`, cấu hình pool, API connection hay `Statement`.
4. Xác minh giá trị hợp lệ, đơn vị thời gian, default và hành vi khi không hỗ trợ.
5. Viết kiểm thử tích hợp trên đúng database/driver mục tiêu.
6. Ghi rõ phần cấu hình không portable để khi đổi database có thể thay thế đúng chỗ.

Không nên truyền một option name tùy ý với kỳ vọng mọi driver hiểu nó. Nếu SPI không cung cấp điểm mở rộng chuẩn cho tùy chọn đó, cần dùng API của driver hoặc cấu hình mà driver công bố; tránh ép kiểu hoặc phụ thuộc vào implementation nội bộ không ổn định.

## 9. Tiêu thụ Result đúng cách

Sau khi `execute()`, mỗi `Result` cần được tiêu thụ bằng một trong các cách phù hợp. Với truy vấn trả hàng, dùng `Result.map(...)`. Với lệnh thay đổi dữ liệu, dùng `Result.getRowsUpdated()`.

Ví dụ đọc hàng:

```java
Flux<Customer> rows = Flux.from(statement.execute())
    .flatMap(result -> result.map((row, metadata) ->
        new Customer(
            row.get("id", Long.class),
            row.get("email", String.class))));
```

Ví dụ lấy số hàng cập nhật:

```java
Mono<Long> updated = Flux.from(statement.execute())
    .flatMap(Result::getRowsUpdated)
    .reduce(0L, Long::sum);
```

Không tiêu thụ cùng một `Result` bằng nhiều đường khác nhau như vừa `map` vừa `getRowsUpdated()` trừ khi hợp đồng driver/API cho phép rõ ràng. Kết quả thường được thiết kế để tiêu thụ một lần. Nếu cần cả dữ liệu được trả về và số hàng, hãy dùng kiểu kết quả mà database/driver cung cấp và thiết kế việc đọc phù hợp.

Đối với truy vấn có nhiều hàng, giữ publisher ở dạng `Flux` nếu có thể để tránh thu thập toàn bộ vào bộ nhớ. Backpressure và cách driver fetch dữ liệu sẽ ảnh hưởng đến lượng dữ liệu được truyền qua pipeline, nhưng không thay thế giới hạn SQL hoặc pagination khi tập kết quả quá lớn.

## 10. Kết hợp Statement với transaction

Một statement sử dụng connection trong phạm vi thực thi. Nếu thao tác thuộc transaction, phải sử dụng connection tham gia transaction đó. Khi Spring quản lý transaction reactive, các thao tác qua `DatabaseClient`/`R2dbcEntityTemplate` được cấu hình phù hợp có thể tham gia cùng transaction context.

Nếu tự lấy connection từ `ConnectionFactory` trong khi một transaction Spring đang hoạt động, có nguy cơ tạo connection khác và thao tác không nằm trong transaction mong muốn. Khi cần dùng SPI trực tiếp trong service có transaction, hãy sử dụng cơ chế lấy connection gắn với transaction do Spring cung cấp hoặc cân nhắc viết custom integration phù hợp. Không gọi `block()` để lấy connection hay kết quả trong reactive chain.

Batch cũng không tự động đồng nghĩa với transaction. Nếu một batch gồm nhiều thao tác phải cùng thành công hoặc thất bại, cần chạy nó trong transaction phù hợp và hiểu hành vi lỗi của driver. Một số database có thể thực hiện một phần batch trước khi lỗi; transaction là cơ chế để rollback khi yêu cầu nghiệp vụ cần tính nguyên tử.

## 11. Hủy truy vấn và quản lý tài nguyên

R2DBC hoạt động theo Reactive Streams. Việc subscribe bắt đầu thực thi publisher; việc cancel có thể khiến quá trình đọc kết quả dừng. Driver có thể hỗ trợ hủy statement hoặc gửi tín hiệu hủy xuống database, nhưng thời điểm và mức độ dừng phụ thuộc driver cùng database.

Không nên giả định cancel luôn rollback mọi thay đổi hoặc bảo đảm server dừng ngay lập tức. Với thao tác ghi, transaction và trạng thái commit cần được quản lý rõ ràng. Khi dùng SPI trực tiếp, bảo đảm connection được đóng khi hoàn tất, lỗi hoặc cancel; dùng `usingWhen` hoặc cơ chế resource management phù hợp.

## 12. Lựa chọn giữa SPI trực tiếp và Spring abstraction

| Nhu cầu | Cách tiếp cận |
|---|---|
| CRUD theo entity và mapping thông thường | Repository hoặc `R2dbcEntityTemplate`. |
| SQL tùy chỉnh nhưng muốn named parameter, exception translation và tích hợp Spring | `DatabaseClient`. |
| Cần `fetchSize` hoặc `returnGeneratedValues` qua statement filter | `DatabaseClient` filter nếu phiên bản hỗ trợ, hoặc SPI trực tiếp. |
| Batch với cùng SQL và nhiều bộ bind | `Statement.add()` hoặc API batch phù hợp. |
| Tính năng riêng của driver không được abstraction Spring bộc lộ | Dùng API driver được tài liệu hóa hoặc custom integration. |
| Quản lý connection/transaction ở mức thấp | R2DBC SPI cùng cơ chế quản lý tài nguyên và transaction rõ ràng. |

Không nên hạ xuống SPI trực tiếp chỉ để thay đổi một tùy chọn nếu Spring `DatabaseClient` đã có filter phù hợp. Giữ ở abstraction cao hơn giúp giảm trách nhiệm quản lý connection và thường làm code dễ bảo trì hơn. Chỉ dùng API riêng của driver khi thực sự cần và chấp nhận ràng buộc với vendor.

## 13. Quy trình áp dụng và xác minh một tùy chọn Statement

Khi muốn tùy chỉnh statement, thực hiện theo trình tự:

1. Xác định mục tiêu: batch, generated values, fetch size hay một tùy chọn riêng của driver.
2. Kiểm tra SPI có method chuẩn tương ứng không.
3. Kiểm tra driver mục tiêu có hỗ trợ method đó và có giới hạn gì.
4. Xác định có thể cấu hình qua `DatabaseClient` filter hay phải dùng SPI trực tiếp.
5. Bind đầy đủ tham số, bao gồm kiểu rõ ràng cho giá trị null.
6. Tiêu thụ `Result` đúng một lần và xử lý số hàng hoặc dữ liệu trả về.
7. Quản lý connection và transaction qua reactive flow, kể cả lỗi và cancellation.
8. Kiểm thử với đúng database/driver, dữ liệu lớn và trường hợp tính năng không được hỗ trợ.

`Statement` là điểm kiểm soát ở mức thực thi của R2DBC. SPI cung cấp bind, batch, gợi ý fetch size và yêu cầu generated values, nhưng các tính năng tùy chọn vẫn phụ thuộc driver. Tách bạch cấu hình factory, pool, statement, transaction và reactive flow giúp chọn đúng nơi để cấu hình, đồng thời tránh phụ thuộc nhầm vào hành vi riêng của một driver khi ứng dụng cần hỗ trợ nhiều môi trường.

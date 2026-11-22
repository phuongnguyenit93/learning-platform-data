# Nhiều bộ tham số trên Statement và giới hạn trình điều khiển

Khi ghi nhiều bản ghi trong Spring Data Relational R2DBC, ứng dụng có thể thực thi cùng một câu SQL với nhiều bộ giá trị tham số. R2DBC SPI cung cấp `Statement.add()` để thêm một bộ tham số mới vào cùng một `Statement`. Cách này hữu ích khi nhiều hàng có cùng cấu trúc INSERT hoặc UPDATE nhưng giá trị khác nhau.

Tuy nhiên, nhiều bộ tham số trên một `Statement` không đồng nghĩa với một câu SQL có nhiều nhóm `VALUES`, cũng không bảo đảm driver gửi đúng một packet hay database xử lý toàn bộ như một transaction. Khả năng hỗ trợ, cách thực thi, giới hạn số bộ tham số và mức độ buffering phụ thuộc driver, database và giao thức. Muốn ghi dữ liệu lớn ổn định, cần kiểm soát batch size, số bind marker, concurrency, transaction và cách xử lý lỗi một cách rõ ràng.

## 1. Một câu lệnh, nhiều bộ tham số

Giả sử cần chèn nhiều khách hàng vào cùng bảng:

```sql
INSERT INTO customer(name, email)
VALUES ($1, $2)
```

Mỗi hàng có cùng cấu trúc gồm `name` và `email`, chỉ giá trị khác nhau. Thay vì tạo một câu SQL mới cho mỗi hàng, R2DBC SPI cho phép tạo một `Statement`, bind bộ giá trị đầu tiên, gọi `add()`, rồi bind bộ giá trị tiếp theo.

```java
Statement statement = connection.createStatement("""
    INSERT INTO customer(name, email)
    VALUES ($1, $2)
    """);

statement.bind(0, "An")
    .bind(1, "an@example.com")
    .add()
    .bind(0, "Binh")
    .bind(1, "binh@example.com");
```

Ví dụ dùng cú pháp bind marker `$1`, `$2` của PostgreSQL. Marker SQL phụ thuộc driver; với database khác có thể là `?` hoặc cú pháp riêng. Chỉ số truyền vào `bind(int, value)` của R2DBC SPI bắt đầu từ 0, kể cả khi marker trong SQL được đánh số từ 1.

Ý nghĩa của chuỗi thao tác:

1. `createStatement(...)` tạo statement với một câu SQL cố định.
2. `bind(0, ...).bind(1, ...)` gắn bộ tham số thứ nhất.
3. `add()` kết thúc bộ tham số hiện tại và bắt đầu một bộ mới.
4. Các lệnh `bind` tiếp theo gắn giá trị cho bộ tham số mới.
5. `execute()` thực thi statement với các bộ tham số đã khai báo.

Mỗi bộ phải bind đầy đủ những tham số cần thiết trước khi chuyển sang bộ tiếp theo. Không để một tham số bị thiếu hoặc tái sử dụng giá trị cũ ngoài ý muốn.

## 2. Statement.add() khác với SQL multi-row INSERT

Có hai cách thường được gọi chung là “insert nhiều hàng”, nhưng chúng có hình dạng khác nhau.

### 2.1. Nhiều bộ tham số với Statement.add()

Một câu SQL có một nhóm placeholder được tái sử dụng cho nhiều bộ giá trị:

```sql
INSERT INTO customer(name, email) VALUES ($1, $2)
```

Các bộ tham số được thêm qua API:

```text
Set 1: name = An,   email = an@example.com
Set 2: name = Binh, email = binh@example.com
Set 3: name = Chi,  email = chi@example.com
```

Đây là chức năng `Statement.add()` của R2DBC SPI. Driver quyết định cách chuyển các bộ tham số tới database.

### 2.2. Một câu SQL có nhiều nhóm VALUES

Một câu SQL khác có thể chứa nhiều nhóm giá trị trong cùng câu lệnh:

```sql
INSERT INTO customer(name, email)
VALUES
    ($1, $2),
    ($3, $4),
    ($5, $6);
```

Ở đây câu SQL có sáu bind marker khác nhau cho ba hàng. Đây là một câu SQL multi-row INSERT. Ứng dụng hoặc framework phải tạo số nhóm `VALUES` và marker tương ứng.

### 2.3. So sánh hai cách

| Tiêu chí | `Statement.add()` | Multi-row `VALUES` |
|---|---|---|
| Câu SQL | Một nhóm placeholder được tái sử dụng | Có nhiều nhóm placeholder trong SQL |
| Số bộ giá trị | Nhiều bộ trên cùng Statement | Một bộ tham số lớn cho toàn câu SQL |
| Số bind marker trong mẫu SQL | Cố định theo số cột/placeholder mỗi hàng | Tăng theo số hàng được tạo trong SQL |
| Hỗ trợ | Phụ thuộc driver hỗ trợ `Statement.add()` | Phụ thuộc dialect và giới hạn câu SQL/parameter |
| Kích thước câu SQL | Thường không tăng theo số bộ tham số | Tăng theo số nhóm `VALUES` |
| Cách thực thi | Driver quyết định cách thực thi các bộ | Database nhận một câu lệnh multi-row |
| Tính nguyên tử | Không tự tạo transaction; cần xác nhận semantics driver/database | Một statement, nhưng vẫn phải hiểu semantics transaction và database |

Không có cách nào luôn nhanh hơn. `Statement.add()` tránh phải tạo chuỗi SQL có hàng nghìn nhóm placeholder, nhưng driver có thể phải buffer nhiều bộ tham số hoặc thực thi chúng theo cách riêng. Multi-row `VALUES` có thể giảm overhead statement nhưng làm tăng số bind marker và kích thước SQL. Hãy benchmark trên database và driver thực tế.

## 3. Thực thi Statement với nhiều bộ tham số

Sau khi thêm các bộ tham số, gọi `execute()` để nhận kết quả reactive:

```java
Publisher<? extends Result> results = statement.execute();
```

Với câu lệnh INSERT/UPDATE/DELETE, thường cần đọc số hàng bị ảnh hưởng từ `Result.getRowsUpdated()`:

```java
Flux.from(statement.execute())
    .concatMap(result -> Flux.from(result.getRowsUpdated()))
    .reduce(0L, Long::sum);
```

`execute()` là lazy theo mô hình Reactive Streams: câu lệnh được thực thi khi Publisher được subscribe. Nếu không nối Publisher vào pipeline hoặc không có subscriber, không thể giả định dữ liệu đã được ghi.

Số `Result` và số giá trị `rowsUpdated` quan sát được có thể phụ thuộc cách driver biểu diễn kết quả thực thi. Đừng giả định luôn có đúng một `Result` cho cả batch hoặc luôn có đúng một giá trị cập nhật cho mỗi bộ tham số. Hãy kiểm tra driver và integration test.

### 3.1. Ví dụ đầy đủ với R2DBC SPI

Ví dụ sau ghi một danh sách khách hàng. Nó sử dụng PostgreSQL bind marker để minh họa; điều chỉnh SQL theo driver đang dùng.

```java
import io.r2dbc.spi.Connection;
import io.r2dbc.spi.ConnectionFactory;
import io.r2dbc.spi.Statement;
import java.util.List;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

record CustomerInput(String name, String email) {}

Mono<Long> insertBatch(
        ConnectionFactory connectionFactory,
        List<CustomerInput> customers) {

    if (customers.isEmpty()) {
        return Mono.just(0L);
    }

    return Mono.usingWhen(
        Mono.from(connectionFactory.create()),
        connection -> {
            Statement statement = connection.createStatement("""
                INSERT INTO customer(name, email)
                VALUES ($1, $2)
                """);

            for (int i = 0; i < customers.size(); i++) {
                if (i > 0) {
                    statement.add();
                }

                CustomerInput customer = customers.get(i);
                statement.bind(0, customer.name());

                if (customer.email() == null) {
                    statement.bindNull(1, String.class);
                } else {
                    statement.bind(1, customer.email());
                }
            }

            return Flux.from(statement.execute())
                .concatMap(result -> Flux.from(result.getRowsUpdated()))
                .reduce(0L, Long::sum);
        },
        connection -> Mono.from(connection.close()),
        (connection, error) -> Mono.from(connection.close()),
        connection -> Mono.from(connection.close())
    );
}
```

Trong ví dụ:

- Danh sách rỗng trả về 0 mà không tạo connection hoặc câu SQL.
- `Statement.add()` được gọi trước khi bind mỗi bộ tham số từ bộ thứ hai trở đi.
- `bindNull(1, String.class)` dùng khi email có thể null; R2DBC cần kiểu Java cho giá trị null.
- `Mono.usingWhen` quản lý connection khi pipeline complete, error hoặc cancel.
- Số hàng bị ảnh hưởng được cộng lại từ các kết quả mà driver phát ra.

Đây là ví dụ dùng R2DBC SPI trực tiếp. Nếu ứng dụng cần tham gia Spring-managed reactive transaction, không nên mặc định rằng `connectionFactory.create()` trực tiếp sẽ lấy connection đã được Spring gắn với transaction context. Hãy dùng `DatabaseClient`/cơ chế lấy connection của Spring hoặc `ConnectionFactoryUtils` phù hợp, và bảo đảm cùng `ConnectionFactory` với transaction manager.

### 3.2. Binding giá trị null

Không truyền null trực tiếp vào `bind`:

```java
// Không dùng cách này cho giá trị null.
statement.bind(1, null);
```

Hãy dùng `bindNull` và khai báo kiểu:

```java
statement.bindNull(1, String.class);
```

Kiểu được khai báo phải tương thích với kiểu cột và mapping của driver. Nếu cột không cho phép NULL, database sẽ báo lỗi khi thực thi; `bindNull` không bỏ qua ràng buộc schema.

## 4. Statement.add() có được mọi driver hỗ trợ không?

R2DBC SPI định nghĩa `Statement.add()` cho nhiều bộ tham số, nhưng khả năng thực thi phụ thuộc driver. Một số driver có thể không hỗ trợ thao tác này hoặc có giới hạn riêng. Vì vậy, không nên suy luận rằng chỉ cần code biên dịch là mọi database đều thực hiện được batch theo cách giống nhau.

Trước khi dùng, cần xác nhận:

- Driver có hỗ trợ `Statement.add()` trong phiên bản đang triển khai không.
- Loại statement nào được hỗ trợ: INSERT, UPDATE, DELETE hay các dạng khác.
- Driver có hỗ trợ parameter binding cho tất cả kiểu dữ liệu cần ghi không.
- Kết quả `execute()` được phát theo từng bộ tham số hay theo cách tổng hợp.
- Hành vi khi một bộ tham số lỗi giữa batch là gì.
- Có giới hạn số bộ tham số hoặc kích thước batch không.
- Statement có thể được dùng trong transaction và connection pool theo cách dự kiến không.

Nếu driver báo `UnsupportedOperationException` hoặc một lỗi tương tự khi gọi `add()`/`execute()`, hãy chọn chiến lược khác như thực thi tuần tự, multi-row INSERT nếu dialect hỗ trợ hoặc API bulk riêng của database/driver.

## 5. Phân biệt Statement với Batch trong R2DBC SPI

R2DBC SPI còn có API `Batch`, nhưng nó khác `Statement`.

- `Statement` dùng một câu SQL có thể chứa bind marker, bind giá trị và có thể thêm nhiều bộ tham số bằng `add()`.
- `Batch` gom nhiều câu SQL thành một batch bằng `add(String sql)`; API này không cung cấp cùng mô hình bind tham số như `Statement`.

Ví dụ hình thức của `Batch`:

```java
Batch batch = connection.createBatch();
batch.add("UPDATE customer SET active = false WHERE id = 10");
batch.add("UPDATE customer SET active = false WHERE id = 20");

Publisher<? extends Result> results = batch.execute();
```

Ví dụ trên minh họa API và dùng literal cố định để dễ thấy khác biệt. Không nối dữ liệu đầu vào của người dùng vào chuỗi SQL đưa cho `Batch.add()`: làm vậy có nguy cơ SQL injection và lỗi quoting. Khi cần truyền dữ liệu động, ưu tiên `Statement` với bind parameter.

`Batch` cũng phụ thuộc driver. Không phải mọi driver đều hỗ trợ mọi dạng batch SQL, và không nên xem `Batch` là thay thế an toàn cho prepared statement có bind.

## 6. Giới hạn trình điều khiển và database

Batch size không chỉ là số hàng ứng dụng muốn ghi. Nó chịu ảnh hưởng của nhiều giới hạn ở các tầng khác nhau.

| Giới hạn | Tác động |
|---|---|
| Số bind marker trong một statement | Giới hạn số tham số của một câu SQL, đặc biệt với multi-row `VALUES` |
| Số bộ tham số trong một Statement | Driver có thể giới hạn hoặc phải buffer số bộ được thêm bằng `add()` |
| Độ dài SQL | Câu SQL multi-row có thể vượt giới hạn parser hoặc protocol |
| Kích thước request/packet | Tổng dữ liệu bind có thể vượt giới hạn của driver, giao thức hoặc server |
| Kích thước một giá trị | Một cột text/binary lớn có thể vượt giới hạn kiểu SQL hoặc driver |
| Bộ nhớ driver/client | Driver có thể giữ nhiều giá trị trước khi gửi hoặc trong khi xử lý batch |
| Thời gian statement | Batch quá lớn có thể chạy lâu, timeout hoặc giữ connection quá lâu |
| Giới hạn transaction | Một batch lớn có thể tạo transaction dài, nhiều lock hoặc nhiều WAL/undo |
| Giới hạn database | Constraint, trigger, log, lock, replication và tài nguyên server ảnh hưởng khả năng ghi |

Các con số cụ thể phụ thuộc hệ quản trị, phiên bản database, driver và cấu hình. Ví dụ, giới hạn số parameter của SQL Server, giới hạn expression trong danh sách `IN` của Oracle và giới hạn biến host parameter của SQLite là các giới hạn khác nhau; chúng không thể dùng làm một con số chung cho R2DBC.

Ngoài giới hạn cứng, còn có giới hạn thực tế về hiệu năng. Một batch có thể hợp lệ về mặt protocol nhưng vẫn gây thời gian giữ connection quá dài, tăng độ trễ các request khác hoặc làm database quá tải.

## 7. Tính số bind marker trong multi-row INSERT

Với multi-row INSERT, số bind marker tăng theo số hàng và số cột cần bind.

Giả sử mỗi hàng có `C` cột được bind và câu lệnh chứa `N` hàng:

\[
P = N \times C
\]

Nếu có thêm `F` tham số cố định ngoài các nhóm hàng:

\[
P = N \times C + F
\]

Ví dụ mỗi hàng có 4 cột và muốn chèn 300 hàng:

\[
P = 300 \times 4 = 1200
\]

Nếu câu lệnh còn 2 tham số dùng chung, tổng số marker là 1.202. Cần so sánh tổng số này với giới hạn parameter thực tế của database/driver.

Với `Statement.add()`, mẫu SQL vẫn có `C` marker cho một hàng, còn số bộ tham số là `N`. Điều đó có thể tránh giới hạn marker tăng theo `N`, nhưng không loại bỏ giới hạn số bộ, kích thước dữ liệu, bộ nhớ và thời gian thực thi của driver.

Đây là khác biệt quan trọng: multi-row `VALUES` chủ yếu làm tăng số placeholder trong câu SQL; `Statement.add()` chủ yếu làm tăng số parameter set của cùng một statement.

## 8. Chọn batch size

Không có một batch size tối ưu cho mọi hệ thống. Batch quá nhỏ tạo nhiều round trip và chi phí statement; batch quá lớn có thể tăng bộ nhớ, lock, thời gian xử lý và độ trễ.

Khi chọn batch size, cần cân nhắc:

- Số cột và kiểu dữ liệu của mỗi hàng.
- Kích thước trung bình và lớn nhất của từng giá trị, đặc biệt `VARCHAR`, JSON và binary.
- Khả năng `Statement.add()` của driver.
- Số bộ tham số tối đa mà driver/database hỗ trợ.
- Thời gian thực thi mong muốn cho một batch.
- Kích thước connection pool và số request ghi đồng thời.
- Transaction timeout, lock contention và yêu cầu rollback.
- Khả năng retry và xử lý batch thất bại một phần.

Một giá trị như 100 hoặc 500 hàng mỗi batch chỉ là điểm bắt đầu để benchmark, không phải quy tắc phổ quát. Dùng số liệu đo được để điều chỉnh.

## 9. Chia dữ liệu lớn thành nhiều batch hữu hạn

Không nên đưa hàng trăm nghìn hoặc hàng triệu bộ tham số vào một `Statement` duy nhất. Hãy chia nguồn thành các batch có kích thước hữu hạn.

Ví dụ xử lý tuần tự:

```java
Flux<Long> insertAll(
        ConnectionFactory connectionFactory,
        Flux<CustomerInput> source) {

    int batchSize = 200;

    return source
        .buffer(batchSize)
        .concatMap(batch -> insertBatch(connectionFactory, batch));
}
```

`buffer(batchSize)` gom tối đa 200 phần tử thành một danh sách. `concatMap` đợi batch hiện tại hoàn tất rồi mới thực hiện batch tiếp theo. Cách này giới hạn số batch đang chạy đồng thời và thường dễ kiểm soát connection hơn.

Nếu workload và database cho phép nhiều batch chạy song song, có thể đặt concurrency hữu hạn:

```java
Flux<Long> insertAll(
        ConnectionFactory connectionFactory,
        Flux<CustomerInput> source) {

    int batchSize = 200;
    int concurrency = 2;

    return source
        .buffer(batchSize)
        .flatMap(batch -> insertBatch(connectionFactory, batch), concurrency);
}
```

Concurrency 2 cho phép tối đa hai batch được xử lý đồng thời trong toán tử đó. Cần cân đối với `maxSize` của pool, các thao tác khác trong ứng dụng và ngân sách connection của database.

### 9.1. Không gom toàn bộ nguồn trước khi chia batch

Với nguồn lớn, tránh:

```java
source.collectList()
    .flatMapMany(all -> Flux.fromIterable(all).buffer(200));
```

Cách này materialize toàn bộ nguồn trước khi chia batch, làm mất lợi ích giới hạn bộ nhớ. Dùng `buffer(batchSize)` trực tiếp trên Flux để chỉ giữ một batch cùng lúc, trừ khi nguồn vốn đã là danh sách có kích thước được kiểm soát.

### 9.2. Batch cuối có thể nhỏ hơn

Nếu tổng số phần tử không chia hết cho batch size, batch cuối chứa ít hàng hơn. Ví dụ 450 hàng với batch size 200 tạo ba batch có kích thước 200, 200 và 50. Không cần thêm hàng giả hoặc bind placeholder không sử dụng cho batch cuối.

### 9.3. Xử lý nguồn rỗng

`buffer` trên Flux rỗng không phát batch nào, vì vậy `insertAll` hoàn tất mà không gọi `insertBatch`. Nếu method cần trả tổng số hàng đã ghi, có thể cộng số lượng từng batch:

```java
Mono<Long> insertAllAndCount(
        ConnectionFactory connectionFactory,
        Flux<CustomerInput> source) {

    return source
        .buffer(200)
        .concatMap(batch -> insertBatch(connectionFactory, batch))
        .reduce(0L, Long::sum);
}
```

## 10. Kết hợp batch với transaction

`Statement.add()` không tự tạo transaction. Nó mô tả nhiều bộ tham số cho một statement; tính nguyên tử của thao tác vẫn phụ thuộc database, driver và transaction boundary.

Nếu nghiệp vụ yêu cầu tất cả batch phải thành công hoặc rollback cùng nhau, cần đặt các batch trong một reactive transaction phù hợp. Ví dụ về mặt service:

```java
@Transactional
public Mono<Long> importCustomers(Flux<CustomerInput> source) {
    return source
        .buffer(200)
        .concatMap(this::insertBatchUsingSpringManagedConnection)
        .reduce(0L, Long::sum);
}
```

`insertBatchUsingSpringManagedConnection` phải sử dụng connection được Spring quản lý trong cùng transaction, không tự mở connection độc lập ngoài transaction context. Tất cả repository/template/client cũng cần dùng cùng `ConnectionFactory` với `R2dbcTransactionManager`.

### 10.1. Một transaction cho toàn bộ import

Ưu điểm:

- Có thể rollback toàn bộ khi một batch thất bại.
- Các thao tác nằm trong cùng transaction boundary.
- Phù hợp khi tính nguyên tử toàn bộ tập dữ liệu là yêu cầu nghiệp vụ.

Nhược điểm:

- Transaction dài và có thể giữ connection lâu.
- Nhiều lock hoặc phiên bản dữ liệu cũ có thể được giữ lâu hơn.
- Transaction log/WAL/undo có thể tăng đáng kể.
- Nếu import rất lớn, rollback có thể tốn thời gian và tài nguyên.

### 10.2. Một transaction cho mỗi batch

Mỗi batch có transaction riêng:

- Giảm thời gian giữ transaction và giới hạn phạm vi rollback.
- Có thể lưu checkpoint sau từng batch.
- Khi batch sau thất bại, batch trước vẫn có thể đã commit.
- Cần cơ chế resume, idempotency hoặc đánh dấu trạng thái để tránh ghi trùng khi chạy lại.

Hãy chọn ranh giới transaction theo yêu cầu nghiệp vụ, không chỉ theo hiệu năng. Nếu cần import có thể tiếp tục sau lỗi, thiết kế trạng thái batch và khóa idempotency ngay từ đầu.

## 11. Lỗi giữa batch và kết quả một phần

Khi một batch có nhiều bộ tham số, một bộ có thể vi phạm constraint hoặc gặp lỗi giữa quá trình thực thi. Cách driver báo lỗi và mức độ hoàn tất của các bộ trước đó phụ thuộc implementation và transaction.

Ứng dụng cần xác định:

- Một lỗi có làm dừng toàn bộ `execute()` không?
- Các bộ trước lỗi có thể đã được ghi hay chưa?
- Driver phát bao nhiêu `Result` trước khi báo lỗi?
- Transaction có rollback toàn bộ không?
- Có thể xác định chính xác hàng nào thất bại không?
- Retry toàn batch có thể tạo bản ghi trùng không?

Nếu không có transaction bao quanh và driver/database thực hiện một phần rồi báo lỗi, ứng dụng có thể không biết chắc những hàng nào đã commit. Không nên giả định “batch báo lỗi thì không có hàng nào được ghi”.

### 11.1. Idempotency khi retry

Với dữ liệu import, có thể dùng một khóa nghiệp vụ duy nhất hoặc idempotency key để nhận diện một hàng đã được xử lý. Ví dụ:

```sql
CREATE TABLE imported_customer (
    external_id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    email VARCHAR(250)
);
```

`external_id` là khóa duy nhất do nguồn dữ liệu cung cấp. Khi retry, database có thể từ chối duplicate hoặc ứng dụng dùng upsert theo dialect để xử lý lại an toàn. Cú pháp upsert khác nhau giữa database; hãy dùng cơ chế được hỗ trợ và xác định rõ việc cập nhật bản ghi cũ.

Không retry mù quáng một batch INSERT không idempotent sau khi mất kết nối trong lúc commit. Kết quả commit có thể không rõ ràng: server đã ghi nhưng client chưa nhận được xác nhận.

## 12. Generated ID và kết quả của batch

Khi INSERT từng entity qua repository/template, ứng dụng có thể cần nhận lại ID do database sinh. Với `Statement.add()` ở tầng SPI, cách driver trả generated values phụ thuộc API, database và implementation. Không nên giả định `getRowsUpdated()` cung cấp danh sách ID.

Nếu cần ID được sinh cho từng hàng:

- Kiểm tra driver có hỗ trợ generated values cho statement có nhiều bộ tham số không.
- Kiểm tra cách truy xuất generated columns hoặc `RETURNING` theo database.
- Xác nhận thứ tự kết quả có tương ứng thứ tự đầu vào không.
- Nếu driver không hỗ trợ, cân nhắc multi-row `INSERT ... RETURNING`, ghi từng hàng hoặc dùng khóa do ứng dụng tạo trước.

Ví dụ PostgreSQL hỗ trợ `RETURNING` cho nhiều hàng:

```sql
INSERT INTO customer(name, email)
VALUES ($1, $2), ($3, $4)
RETURNING id, name;
```

Đây là cú pháp PostgreSQL và không phải cú pháp portable. Cần kiểm tra cách bind và mapping generated rows với R2DBC driver đang dùng.

## 13. DatabaseClient, repository và Statement.add()

Các abstraction Spring Data có mức kiểm soát khác nhau:

| API | Mục đích | Ghi nhiều hàng |
|---|---|---|
| `ReactiveCrudRepository.save(...)` | Lưu một entity | Một thao tác save cho entity |
| `ReactiveCrudRepository.saveAll(...)` | Lưu một publisher/collection entity | Không nên mặc định rằng luôn tạo một `Statement.add()` batch; hành vi phụ thuộc implementation/version |
| `R2dbcEntityTemplate` | Thao tác entity và mapping | Thuận tiện cho insert/update theo entity; cần kiểm tra cách thực thi của phiên bản |
| `DatabaseClient` | Thực thi SQL và bind giá trị | API fluent thông thường mô tả một bộ bind cho một lần thực thi; có thể dùng callback/connection-level API hoặc SPI trực tiếp khi cần nhiều bộ |
| R2DBC SPI `Statement.add()` | Kiểm soát nhiều bộ tham số trên cùng Statement | Trực tiếp, nhưng phụ thuộc hỗ trợ của driver |

Không suy luận rằng tên method `saveAll` đồng nghĩa với một batch protocol ở database. Nếu hiệu năng batch là yêu cầu, hãy xác minh số câu SQL, cách bind và round trip bằng logging/metrics hoặc test với driver thật.

### 13.1. Khi nào dùng repository/template?

Dùng repository hoặc `R2dbcEntityTemplate` khi:

- Cần mapping entity, lifecycle và converter của Spring Data.
- Khối lượng ghi vừa phải.
- API lưu hiện có đáp ứng SLA.
- Không cần điều khiển trực tiếp cách driver gửi nhiều bộ tham số.

### 13.2. Khi nào dùng Statement.add()?

Cân nhắc SPI trực tiếp khi:

- Có khối lượng ghi lớn với cùng một cấu trúc SQL.
- Driver xác nhận hỗ trợ nhiều parameter set.
- Cần kiểm soát batch size và vòng đời connection.
- Ứng dụng chấp nhận tự quản lý mapping, generated values và transaction integration.
- Đã kiểm thử hành vi khi batch lỗi hoặc bị cancel.

Nếu dùng SPI trực tiếp trong Spring, cần chú ý connection được quản lý bởi transaction manager. Truy cập trực tiếp `ConnectionFactory.create()` có thể tạo connection ngoài transaction context nếu không dùng cơ chế Spring tương ứng.

## 14. Backpressure và giới hạn số batch đang chạy

Reactive không có nghĩa là ứng dụng có thể phát hàng triệu bản ghi vào driver cùng lúc mà không tốn bộ nhớ. Các toán tử và driver có thể buffer dữ liệu.

Các điểm cần kiểm soát:

- Nguồn `Flux` có thể phát nhanh hơn tốc độ ghi; dùng demand và batch operator phù hợp.
- `buffer(batchSize)` giới hạn số phần tử trong một batch, nhưng batch đang xử lý vẫn chiếm bộ nhớ.
- `concatMap` chỉ xử lý một batch tại một thời điểm.
- `flatMap(..., concurrency)` cho phép nhiều batch đồng thời; tổng dữ liệu đang giữ có thể tăng theo concurrency.
- Driver có thể buffer toàn bộ parameter sets của một `Statement.add()` trước khi gửi.
- Connection pool giới hạn số connection, nhưng không tự giới hạn số phần tử được giữ trong heap.

Ví dụ giới hạn concurrency:

```java
source.buffer(200)
    .flatMap(this::writeBatch, 2);
```

Nếu mỗi batch có 200 phần tử và concurrency là 2, ứng dụng có thể giữ dữ liệu của nhiều batch cùng lúc. Đây chỉ là ước lượng ở tầng pipeline; driver còn có thể có buffer riêng. Hãy đo heap và pool metrics khi tải thực tế.

## 15. Timeout và giới hạn thời gian

Batch lớn có thể chạy lâu hơn một thao tác đơn. Cần phân biệt:

| Loại timeout | Ý nghĩa |
|---|---|
| Connection acquire timeout | Thời gian chờ lấy connection từ pool |
| Connection creation timeout | Thời gian mở connection mới |
| Statement/query timeout | Thời gian database/driver cho phép câu lệnh chạy |
| Transaction timeout | Thời gian transaction được phép tồn tại |
| Application deadline | Tổng thời gian use case được phép chạy |

Timeout của một request không tự động hủy mọi công việc ở database theo cùng một cách trên mọi driver. Khi timeout hoặc cancellation, cần xác nhận statement được hủy, connection được trả về pool và transaction được rollback/đóng theo kỳ vọng.

Không đặt timeout quá ngắn khiến batch hợp lệ thường xuyên bị hủy; cũng không để batch giữ connection vô thời hạn. Hãy dựa vào kích thước batch, latency và SLA thực tế.

## 16. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Quên gọi `add()` giữa các bộ | Giá trị có thể ghi đè bộ trước hoặc statement chỉ dùng một bộ | Gọi `add()` sau khi bind đủ một bộ và trước bộ tiếp theo |
| Gọi `add()` trước khi bind đủ tham số | Bộ tham số hiện tại thiếu binding | Bind đầy đủ tất cả placeholder trước khi add |
| Dùng sai chỉ số bind | Giá trị vào nhầm cột hoặc lỗi runtime | Nhớ index R2DBC SPI bắt đầu từ 0 |
| Truyền null vào `bind` | Lỗi vì driver không biết kiểu null | Dùng `bindNull(index, type)` |
| Giả định mọi driver hỗ trợ `Statement.add()` | Lỗi unsupported hoặc hành vi khác | Kiểm tra tài liệu và integration test driver |
| Nghĩ `add()` tương đương multi-row VALUES | Hiểu sai giới hạn parameter và cách thực thi | Phân biệt nhiều parameter set với nhiều placeholder trong SQL |
| Cho rằng batch là một transaction | Có thể có dữ liệu ghi một phần khi lỗi | Dùng reactive transaction nếu cần atomicity |
| Đưa quá nhiều hàng vào một batch | Tăng memory, latency, lock và nguy cơ vượt giới hạn | Chia batch có kích thước đo được |
| Dùng `flatMap` không giới hạn | Quá nhiều batch/connection đồng thời | Đặt concurrency hoặc dùng `concatMap` |
| Gom toàn bộ nguồn bằng `collectList()` | Materialize dữ liệu lớn trong heap | Dùng `buffer(batchSize)` trực tiếp |
| Retry batch ghi không idempotent | Có thể tạo bản ghi trùng | Dùng unique key, upsert hoặc idempotency key |
| Dùng raw connection ngoài transaction context | Thao tác có thể không tham gia transaction Spring | Dùng connection utility/client do Spring quản lý |
| Giả định `saveAll` luôn là một batch driver | Đánh giá sai số round trip và hiệu năng | Đo SQL và xác minh implementation/version |
| Không kiểm tra generated ID | Không lấy được ID như mong đợi | Xác minh generated values support của driver |

## 17. Quy trình triển khai ghi nhiều bộ tham số

Khi xây dựng chức năng bulk write, có thể đi theo trình tự:

1. Xác định cấu trúc SQL và số tham số mỗi hàng.
2. Chọn API: repository/template cho thao tác entity thông thường, `Statement.add()` khi cần nhiều parameter set và driver hỗ trợ.
3. Xác nhận cú pháp bind marker và khả năng `add()` trên đúng phiên bản driver.
4. Xác định batch size dựa trên số bộ, kích thước giá trị và giới hạn driver/database.
5. Xử lý danh sách rỗng, giá trị null, kiểu dữ liệu và generated values.
6. Chia nguồn lớn bằng `buffer(batchSize)`; dùng `concatMap` hoặc concurrency hữu hạn.
7. Chọn transaction boundary theo yêu cầu atomicity và khả năng resume.
8. Xác định chiến lược lỗi, kết quả một phần và idempotency trước khi retry.
9. Kiểm tra cancellation, timeout và cleanup connection.
10. Benchmark và quan sát số hàng ghi, thời gian batch, lỗi, heap, connection pool và database load.

## 18. Kiểm thử và quan sát

Kiểm thử phải chạy trên database và R2DBC driver sẽ dùng trong môi trường triển khai. Mock `Statement` không chứng minh driver thực sự hỗ trợ `add()` hoặc xử lý lỗi batch đúng cách.

Các trường hợp nên kiểm tra:

- Không có bản ghi đầu vào.
- Một bộ tham số và nhiều bộ tham số.
- Batch có kích thước tối đa cấu hình và batch cuối nhỏ hơn.
- Giá trị null được bind bằng `bindNull`.
- Vi phạm unique constraint ở bộ đầu, giữa và cuối batch.
- Lỗi kết nối khi đang execute.
- Cancellation trong khi ghi.
- Transaction rollback toàn batch hoặc commit theo từng batch như thiết kế.
- Generated ID nếu use case cần nhận lại khóa.
- Chạy nhiều batch đồng thời ở concurrency đã cấu hình.
- Kích thước dữ liệu lớn và thời gian statement.

Các chỉ số hữu ích:

| Chỉ số | Mục đích |
|---|---|
| Số hàng mỗi batch | Xác nhận batch size thực tế |
| Thời gian thực thi batch | Theo dõi latency và phát hiện batch quá lớn |
| Tổng số hàng được ghi | Đối chiếu với nguồn dữ liệu |
| Số lỗi theo loại | Phân biệt lỗi constraint, timeout và kết nối |
| Số batch retry | Phát hiện lỗi tạm thời hoặc retry storm |
| Connection acquire/pending | Phát hiện pool bão hòa |
| Heap và GC | Phát hiện buffering quá lớn |
| Database CPU, I/O, lock và transaction log | Đánh giá tải phía server |

Không ghi log toàn bộ nội dung bind nếu có email, token, dữ liệu cá nhân hoặc payload nhạy cảm. Nên log correlation ID, số hàng trong batch, thời gian, loại thao tác và thông tin lỗi đã được xử lý phù hợp.

## 19. Nguyên tắc cần nhớ

- `Statement.add()` thêm một bộ tham số mới cho cùng một câu SQL trong R2DBC SPI.
- Bind đầy đủ bộ hiện tại trước khi gọi `add()`; chỉ số `bind(int, ...)` bắt đầu từ 0.
- Dùng `bindNull(index, type)` cho giá trị null.
- Phân biệt nhiều parameter set trên một Statement với một SQL multi-row `VALUES` có nhiều bind marker.
- `Statement.add()` phụ thuộc hỗ trợ của driver; kiểm tra tài liệu và thử trên database thực tế.
- `Batch` là API khác, gom nhiều câu SQL và không thay thế prepared statement có bind parameter.
- Giới hạn driver/database gồm số parameter, số bộ, độ dài SQL, packet, kích thước giá trị, bộ nhớ và thời gian.
- Tính cả số tham số cố định khi ước lượng giới hạn của multi-row INSERT.
- Chia nguồn lớn bằng `buffer(batchSize)`; dùng `concatMap` hoặc concurrency hữu hạn.
- Không materialize toàn bộ nguồn trước khi chia batch nếu dữ liệu lớn.
- `Statement.add()` không tự tạo transaction; chọn transaction boundary theo yêu cầu nghiệp vụ.
- Xử lý lỗi giữa batch, kết quả một phần và retry bằng idempotency.
- Xác minh generated values và `saveAll` behavior thay vì giả định mọi driver/framework đều batch giống nhau.
- Đo batch latency, heap, connection pool và database load để chọn kích thước phù hợp.

Nhiều bộ tham số trên `Statement` là công cụ cấp thấp hữu ích khi cần ghi lặp lại cùng một câu SQL trong R2DBC. Nó có thể giảm chi phí tạo statement và giúp driver tối ưu cách gửi dữ liệu, nhưng hiệu quả và giới hạn thực tế phụ thuộc implementation. Khi kết hợp `Statement.add()` với batch size hữu hạn, transaction có chủ đích, concurrency được kiểm soát và kiểm thử trên driver thật, ứng dụng có thể ghi nhiều bản ghi ổn định mà vẫn giữ được khả năng phản ứng với lỗi và áp lực tài nguyên.

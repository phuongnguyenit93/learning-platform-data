# Batch ở R2DBC SPI và khác biệt với Statement có bind

R2DBC SPI cung cấp hai cơ chế thường được nhắc đến khi cần ghi nhiều câu lệnh hoặc nhiều bản ghi: `Batch` và `Statement` có nhiều bộ giá trị bind. Hai cơ chế này đều có thể giảm chi phí gọi database so với việc tạo và thực thi một thao tác riêng cho từng hàng, nhưng chúng giải quyết hai bài toán khác nhau.

`Batch` được tạo bằng `Connection.createBatch()` và nhận các chuỗi SQL thông qua `Batch.add(String)`. Nó phù hợp với nhiều câu lệnh SQL cố định, không có API bind tham số. `Statement` được tạo bằng `Connection.createStatement(sql)`; ứng dụng bind giá trị cho các placeholder rồi gọi `Statement.add()` để đưa bộ bind hiện tại vào batch của cùng câu SQL. Cách thứ hai phù hợp khi cần thực hiện lặp lại một câu lệnh có tham số với nhiều bộ dữ liệu.

Phân biệt đúng hai API giúp chọn cách ghi an toàn, dễ kiểm soát và phù hợp với driver. Cần nhớ rằng batching ở SPI không tự bảo đảm transaction, tính nguyên tử, một network round trip hay hiệu năng tốt hơn trong mọi trường hợp. Những đặc tính đó còn phụ thuộc driver, database, kích thước batch và cách ứng dụng quản lý kết nối.

## 1. Batch trong R2DBC SPI là gì?

`io.r2dbc.spi.Batch` đại diện cho một nhóm câu lệnh SQL được thêm dưới dạng chuỗi. Ứng dụng lấy batch từ một `Connection`, thêm các câu lệnh bằng `add(String)` rồi gọi `execute()`.

```java
Batch batch = connection.createBatch();

batch.add("DELETE FROM expired_token WHERE expires_at < CURRENT_TIMESTAMP");
batch.add("UPDATE maintenance_job SET last_run = CURRENT_TIMESTAMP " +
          "WHERE job_name = 'token-cleanup'");

Publisher<? extends Result> results = batch.execute();
```

Các đặc điểm cần nhớ:

- Mỗi lần `Batch.add(sql)` thêm một chuỗi SQL vào batch.
- `Batch` không có các phương thức `bind(...)` hoặc `bindNull(...)`.
- Các giá trị cần thay đổi phải được biểu diễn sẵn trong SQL nếu dùng `Batch`; vì vậy không nên ghép dữ liệu đầu vào của người dùng vào chuỗi SQL.
- `Batch.execute()` trả về publisher của các `Result`; ứng dụng cần subscribe và tiêu thụ kết quả.
- Cách driver gửi và thực thi các câu lệnh là chi tiết triển khai của driver.

Batch phù hợp với các câu lệnh cố định như lệnh bảo trì, cập nhật metadata, hoặc một số thao tác SQL độc lập không cần giá trị bind. Nó không phải lựa chọn phù hợp để chèn hàng trăm bản ghi có dữ liệu khác nhau bằng cách nối chuỗi SQL cho từng hàng.

## 2. `Statement` có bind là gì?

`io.r2dbc.spi.Statement` đại diện cho một câu lệnh SQL. Ứng dụng tạo statement bằng `Connection.createStatement(sql)`, bind các giá trị cho placeholder rồi gọi `execute()`.

```java
Statement statement = connection.createStatement(
        "INSERT INTO customer (id, name) VALUES ($1, $2)");

statement.bind(0, 101L)
        .bind(1, "An Nguyen");

Publisher<? extends Result> result = statement.execute();
```

Trong ví dụ PostgreSQL, SQL dùng placeholder `$1`, `$2`. Chỉ số truyền vào `bind` là chỉ số tham số theo API R2DBC, bắt đầu từ `0`; do đó `$1` tương ứng với `bind(0, ...)`, `$2` tương ứng với `bind(1, ...)`.

Với driver khác, cú pháp placeholder có thể khác. Ví dụ một số driver dùng dấu `?`. Hãy dùng cú pháp tham số mà driver R2DBC của hệ quản trị hỗ trợ, không sao chép nguyên cú pháp PostgreSQL sang MySQL hoặc hệ quản trị khác.

Ưu điểm của bind parameters:

- Tách câu SQL khỏi dữ liệu đầu vào.
- Tránh nối chuỗi giá trị và giảm nguy cơ SQL injection.
- Driver nhận được kiểu Java của tham số để chuyển đổi theo codec phù hợp.
- Có thể tái sử dụng cùng cấu trúc SQL với nhiều bộ giá trị.

## 3. Khác biệt quan trọng giữa `Batch.add` và `Statement.add`

Hai phương thức cùng tên `add` nhưng ý nghĩa khác nhau:

| API | Cách gọi | Thứ được thêm vào | Có bind tham số? |
| --- | --- | --- | --- |
| `Batch.add(String sql)` | `batch.add("UPDATE ...")` | Một chuỗi SQL mới | Không |
| `Statement.add()` | `statement.bind(...).add()` | Bộ giá trị bind hiện tại của cùng một câu SQL | Có, thông qua `bind`/`bindNull` |

Hình dung:

```text
Batch
  add(SQL câu 1)
  add(SQL câu 2)
  add(SQL câu 3)
  execute()

Statement
  tạo một SQL có placeholder
  bind bộ giá trị A
  add()       -> đưa bộ A vào batch
  bind bộ giá trị B
  add()       -> đưa bộ B vào batch
  bind bộ giá trị C
  execute()   -> thực thi cả các bộ bind đã thêm và bộ cuối
```

`Batch` gom nhiều chuỗi SQL có thể khác nhau. `Statement.add()` gom nhiều bộ bind cho cùng một câu SQL. Không nên nhầm `Statement.add()` là cách thêm một câu SQL mới vào statement.

## 4. Dùng `Batch` cho nhiều câu SQL cố định

Ví dụ cần chạy hai thao tác bảo trì có câu SQL cố định:

```java
Batch batch = connection.createBatch()
        .add("DELETE FROM expired_token " +
             "WHERE expires_at < CURRENT_TIMESTAMP")
        .add("UPDATE maintenance_job " +
             "SET last_run = CURRENT_TIMESTAMP " +
             "WHERE job_name = 'token-cleanup'");

Flux.from(batch.execute())
        .concatMap(result -> Flux.from(result.getRowsUpdated()))
        .then();
```

`Batch.execute()` trả các `Result`. Với câu lệnh DML, `Result.getRowsUpdated()` cung cấp publisher số hàng bị ảnh hưởng nếu driver hỗ trợ thông tin đó cho thao tác. `concatMap` tiêu thụ kết quả theo thứ tự phát ra; `.then()` chỉ quan tâm việc hoàn tất và trả `Mono<Void>`.

Trong code thực tế, cần trả publisher này từ phương thức để tầng gọi quản lý subscription. Đoạn code minh họa không tự chạy chỉ vì biến `Publisher` hoặc `Flux` được tạo ra.

### Quản lý vòng đời connection

Connection R2DBC cần được đóng sau khi hoàn tất. Có thể dùng `Mono.usingWhen` để quản lý tài nguyên reactive:

```java
public Mono<Void> runCleanup(ConnectionFactory connectionFactory) {
    return Mono.usingWhen(
            Mono.from(connectionFactory.create()),
            connection -> {
                Batch batch = connection.createBatch()
                        .add("DELETE FROM expired_token " +
                             "WHERE expires_at < CURRENT_TIMESTAMP")
                        .add("UPDATE maintenance_job " +
                             "SET last_run = CURRENT_TIMESTAMP " +
                             "WHERE job_name = 'token-cleanup'");

                return Flux.from(batch.execute())
                        .concatMap(result -> Flux.from(result.getRowsUpdated()))
                        .then();
            },
            connection -> Mono.from(connection.close()),
            (connection, error) -> Mono.from(connection.close()),
            connection -> Mono.from(connection.close())
    );
}
```

`usingWhen` đóng connection khi publisher hoàn tất, phát lỗi hoặc bị hủy. Ví dụ chỉ minh họa việc quản lý tài nguyên; nó chưa mở transaction. Nếu batch cần tính nguyên tử, phải chạy trong transaction phù hợp.

## 5. Vì sao `Batch` không phù hợp để chèn dữ liệu động?

`Batch` không cung cấp API bind tham số. Ví dụ sau có thể trông đơn giản nhưng không an toàn:

```java
String sql = "INSERT INTO customer(name) VALUES ('" + userInput + "')";
batch.add(sql);
```

Nếu `userInput` chứa dấu nháy hoặc nội dung SQL độc hại, câu lệnh có thể bị thay đổi. Việc tự escape chuỗi theo cách thủ công rất dễ sai và phụ thuộc database/encoding.

Không dùng `Batch.add` để ghép giá trị người dùng vào SQL. Nếu cần ghi nhiều hàng với dữ liệu khác nhau, hãy dùng `Statement` có bind và `Statement.add()` hoặc API cấp cao hơn phù hợp.

`Batch` có thể vẫn dùng cho câu lệnh có literal cố định do ứng dụng kiểm soát, nhưng không nên biến nó thành cơ chế thay thế prepared statement.

## 6. Dùng `Statement.add()` để ghi nhiều hàng cùng cấu trúc

Giả sử cần chèn nhiều khách hàng. Tất cả hàng dùng cùng một cấu trúc `INSERT`, chỉ khác giá trị:

```sql
INSERT INTO customer (id, name, email)
VALUES ($1, $2, $3)
```

Tạo một `Statement`, bind từng bộ giá trị và gọi `add()` giữa các bộ:

```java
Statement statement = connection.createStatement(
        "INSERT INTO customer (id, name, email) VALUES ($1, $2, $3)");

statement.bind(0, 101L)
        .bind(1, "An Nguyen")
        .bind(2, "an@example.com")
        .add();

statement.bind(0, 102L)
        .bind(1, "Binh Tran")
        .bind(2, "binh@example.com");

Publisher<? extends Result> results = statement.execute();
```

Trong ví dụ:

1. Bộ bind thứ nhất được gán cho các placeholder.
2. `add()` đưa bộ giá trị thứ nhất vào batch của statement.
3. Các lệnh bind tiếp theo tạo bộ giá trị thứ hai cho cùng câu SQL.
4. `execute()` thực thi statement với các bộ giá trị đã thêm và bộ cuối cùng hiện tại.

Không cần tạo một `Statement` mới cho từng hàng nếu muốn dùng cơ chế nhiều bộ bind. Cũng không gọi `add()` sau bộ cuối cùng nếu không có bộ tiếp theo; sau lần bind cuối, gọi `execute()`.

## 7. Ví dụ đầy đủ với `Statement.add()` và R2DBC SPI

Định nghĩa dữ liệu đầu vào:

```java
public record CustomerRow(
        Long id,
        String name,
        String email
) {
}
```

Phương thức insert nhiều hàng:

```java
public Mono<Void> insertCustomers(
        ConnectionFactory connectionFactory,
        List<CustomerRow> customers) {

    if (customers.isEmpty()) {
        return Mono.empty();
    }

    return Mono.usingWhen(
            Mono.from(connectionFactory.create()),
            connection -> {
                Statement statement = connection.createStatement(
                        "INSERT INTO customer (id, name, email) " +
                        "VALUES ($1, $2, $3)");

                for (int i = 0; i < customers.size(); i++) {
                    CustomerRow customer = customers.get(i);

                    statement.bind(0, customer.id())
                            .bind(1, customer.name())
                            .bind(2, customer.email());

                    if (i < customers.size() - 1) {
                        statement.add();
                    }
                }

                return Flux.from(statement.execute())
                        .concatMap(result ->
                                Flux.from(result.getRowsUpdated()))
                        .then();
            },
            connection -> Mono.from(connection.close()),
            (connection, error) -> Mono.from(connection.close()),
            connection -> Mono.from(connection.close())
    );
}
```

Đây là ví dụ theo placeholder PostgreSQL (`$1`, `$2`, `$3`). Với driver dùng `?`, thay câu SQL theo cú pháp của driver; chỉ số bind theo SPI vẫn được truyền theo vị trí tham số của statement.

Các điểm cần chú ý:

- Nếu danh sách rỗng, trả `Mono.empty()` và không cần mở connection.
- Một `Statement` được tạo cho một lần thực thi.
- Mỗi hàng có một bộ bind riêng.
- `add()` chỉ được gọi giữa các bộ bind; bộ cuối cùng được thực thi khi gọi `execute()`.
- Publisher từ `execute()` được tiêu thụ để thao tác thực sự chạy.
- Connection được đóng trong cả trường hợp thành công, lỗi và hủy.

Ví dụ dùng ID do ứng dụng cấp để tập trung vào cơ chế bind. Nếu database sinh ID, cần kiểm tra hỗ trợ trả generated values cho nhiều bộ bind của driver cụ thể; không giả định mọi driver đều trả khóa sinh theo cùng một cách.

## 8. Bind giá trị null bằng `bindNull`

`Statement.bind(index, value)` không nhận `null` như một giá trị bind thông thường. Khi tham số cần SQL `NULL`, dùng `bindNull(index, type)` và cung cấp kiểu Java tương ứng:

```java
statement.bind(0, customer.id())
        .bind(1, customer.name());

if (customer.note() == null) {
    statement.bindNull(2, String.class);
} else {
    statement.bind(2, customer.note());
}
```

Kiểu được truyền vào `bindNull` giúp driver biết kiểu tham số null cần bind. Chọn kiểu tương thích với cột và driver, ví dụ `String.class` cho cột chuỗi, `Long.class` cho số nguyên lớn hoặc `LocalDateTime.class` cho timestamp tương ứng.

Khi dùng `Statement.add()`, mọi bộ bind cần gán đầy đủ các placeholder bắt buộc. Nếu một trường nullable, mỗi bộ phải gọi `bindNull` cho trường đó thay vì bỏ quên tham số. Nếu không, driver có thể báo lỗi tham số chưa được bind.

## 9. Ví dụ nhiều bộ bind có cột nullable

```java
public record CustomerImportRow(
        Long id,
        String name,
        String note
) {
}

public void addCustomerBinding(
        Statement statement,
        CustomerImportRow row) {

    statement.bind(0, row.id())
            .bind(1, row.name());

    if (row.note() == null) {
        statement.bindNull(2, String.class);
    } else {
        statement.bind(2, row.note());
    }
}
```

Sau đó lặp qua dữ liệu:

```java
Statement statement = connection.createStatement(
        "INSERT INTO customer_import (id, name, note) VALUES ($1, $2, $3)");

for (int i = 0; i < rows.size(); i++) {
    addCustomerBinding(statement, rows.get(i));

    if (i < rows.size() - 1) {
        statement.add();
    }
}
```

Tách logic bind thành phương thức riêng giúp bảo đảm mỗi bộ giá trị có cùng thứ tự và cùng quy tắc null. Với nhiều cột hoặc kiểu đặc thù, nên có test xác minh từng vị trí bind tương ứng đúng cột.

## 10. Bảng so sánh hai cơ chế

| Tiêu chí | `Batch` | `Statement` với `add()` |
| --- | --- | --- |
| Tạo từ | `connection.createBatch()` | `connection.createStatement(sql)` |
| Phương thức thêm | `add(String sql)` | `add()` |
| Đơn vị được thêm | Một câu SQL dạng chuỗi | Bộ giá trị bind hiện tại cho cùng câu SQL |
| Bind tham số | Không có API bind | Có `bind` và `bindNull` |
| Số dạng SQL | Có thể thêm các câu SQL khác nhau | Một cấu trúc SQL cho các bộ bind trong statement |
| Trường hợp điển hình | Nhiều lệnh SQL cố định | Insert/update lặp lại với dữ liệu khác nhau |
| An toàn với dữ liệu động | Không phù hợp để ghép giá trị vào SQL | Phù hợp nhờ bind parameters |
| Kết quả | Publisher của `Result` | Publisher của `Result` |
| Transaction | Không tự bảo đảm atomicity | Không tự bảo đảm atomicity |

Quy tắc chọn nhanh:

- Nhiều câu SQL cố định, không cần bind: cân nhắc `Batch`.
- Cùng một câu SQL, nhiều bộ dữ liệu: dùng `Statement` với `bind` và `add()`.
- Cần entity mapping, converter, callback và abstraction repository: dùng API Spring Data phù hợp.
- Cần SQL phức tạp nhưng từng thao tác có tham số: dùng `DatabaseClient` hoặc `Statement` bind; không nối dữ liệu vào SQL.

## 11. `saveAll()` có phải luôn là batch ở SPI không?

Spring Data R2DBC cung cấp `ReactiveCrudRepository.saveAll(...)` để lưu nhiều entity:

```java
public Flux<Customer> importCustomers(Publisher<Customer> customers) {
    return customerRepository.saveAll(customers);
}
```

Đây là abstraction cấp repository. Nó giúp ứng dụng làm việc với entity, mapping metadata, conversion và các cơ chế persistence của Spring Data. Tuy nhiên, chữ ký `saveAll` không phải cam kết rằng implementation sẽ gọi `Connection.createBatch()` hoặc tạo một `Statement` rồi gọi `Statement.add()` cho mọi driver và phiên bản.

Chiến lược thực thi có thể phụ thuộc Spring Data Relational, driver và các đặc điểm của entity như ID sinh, callbacks hoặc mapping. Không nên suy ra số network round trip chỉ từ tên `saveAll`. Nếu yêu cầu hiệu năng cần batching ở mức SPI, hãy đo implementation thực tế hoặc chủ động dùng API phù hợp.

Khi chuyển xuống SPI trực tiếp, ứng dụng phải tự chịu trách nhiệm bind kiểu dữ liệu, chuyển đổi domain value, generated key, mapping, xử lý lỗi và vòng đời connection. Không còn tự động có toàn bộ tiện ích entity mapping chỉ vì đang dùng cùng một `ConnectionFactory`.

## 12. `DatabaseClient` và bind tham số

`DatabaseClient` của Spring cung cấp API SQL có bind tham số:

```java
public Mono<Long> insertCustomer(CustomerCommand command) {
    return databaseClient.sql(
                    "INSERT INTO customer (name, email) " +
                    "VALUES (:name, :email)")
            .bind("name", command.name())
            .bind("email", command.email())
            .fetch()
            .rowsUpdated();
}
```

`DatabaseClient` dùng placeholder có tên theo cú pháp Spring (`:name`, `:email`) rồi chuyển đổi sang cách bind mà driver hỗ trợ. Đây là API cấp cao hơn `Statement` trực tiếp và giúp không phải tự quản lý connection trong trường hợp thông thường.

Một lời gọi `DatabaseClient.sql(...).bind(...).fetch()` mô tả một thao tác thực thi. Không nên giả định rằng gọi `.bind()` nhiều lần tạo ra nhiều bộ bind như `Statement.add()`. Nếu cần lặp lại cùng SQL cho nhiều bản ghi, có thể dùng `saveAll`, lặp các thao tác `DatabaseClient` có kiểm soát, hoặc dùng SPI `Statement.add()` khi cần batch binding tường minh.

Với dữ liệu null, `DatabaseClient` có các phương thức bind null phù hợp như `bindNull(name, type)`; dùng API đúng với phiên bản Spring Framework/Spring Data đang chạy.

## 13. Batch không tự tạo transaction

Một nhầm lẫn phổ biến là cho rằng các câu lệnh trong một `Batch` hoặc các bộ bind của một `Statement` luôn thành công hoặc thất bại cùng nhau. Batching và transaction là hai khái niệm khác nhau:

- **Batching** gom nhiều câu lệnh hoặc bộ bind vào một lần thực thi API.
- **Transaction** xác định ranh giới commit/rollback và tính nguyên tử theo database.

Nếu không có transaction, một số câu lệnh có thể đã được thực hiện trước khi một câu lệnh sau phát sinh lỗi. Kết quả và hành vi chính xác phụ thuộc driver/database. Không giả định batch lỗi đồng nghĩa mọi thay đổi trước đó tự động được hoàn tác.

Nếu nhiều lần ghi phải cùng thành công hoặc cùng rollback, hãy thực thi chúng trong transaction. Trong ứng dụng Spring, với thao tác qua repository hoặc `DatabaseClient` được quản lý bởi Spring, có thể dùng `@Transactional` trên phương thức reactive hoặc `TransactionalOperator`.

```java
public Mono<Void> importCustomers(List<CustomerCommand> commands) {
    return transactionalOperator.transactional(
            Flux.fromIterable(commands)
                    .concatMap(command -> databaseClient.sql(
                                    "INSERT INTO customer (name, email) " +
                                    "VALUES (:name, :email)")
                            .bind("name", command.name())
                            .bind("email", command.email())
                            .fetch()
                            .rowsUpdated())
                    .then()
    );
}
```

Ví dụ này thể hiện transaction reactive cho các thao tác `DatabaseClient` trong cùng Spring-managed transaction context. Nó không dùng `Statement.add()`; các insert vẫn là những thao tác DatabaseClient riêng. Nếu dùng trực tiếp `ConnectionFactory.create()` để lấy connection ngoài cơ chế Spring transaction, không được giả định connection đó tự tham gia transaction của `TransactionalOperator`. Khi làm việc ở SPI trực tiếp, cần quản lý transaction trên chính connection đó hoặc dùng cơ chế lấy connection transaction-aware phù hợp.

## 14. Transaction khi dùng SPI trực tiếp

Khi tự lấy `Connection` từ `ConnectionFactory`, có thể điều khiển transaction qua các phương thức SPI như `beginTransaction()`, `commitTransaction()` và `rollbackTransaction()`.

Quy trình khái niệm:

```text
create connection
begin transaction
create Batch hoặc Statement
bind/add và execute
consume mọi Result
    nếu thành công: commit
    nếu lỗi: rollback
close connection
```

Các thao tác bắt đầu, commit và rollback đều là reactive publisher; phải nối chúng vào pipeline và xử lý cả lỗi lẫn cancellation. Không gọi `subscribe()` rời rạc cho từng bước vì có thể làm mất thứ tự, quản lý tài nguyên và đường truyền lỗi.

Với code ứng dụng Spring, ưu tiên transaction manager của Spring nếu toàn bộ thao tác dùng cùng transaction-aware connection infrastructure. Khi tự quản lý SPI, cần bảo đảm một connection được dùng xuyên suốt transaction và được đóng ở mọi nhánh hoàn tất, lỗi hoặc hủy.

## 15. Kết quả thực thi và `rowsUpdated`

`Batch.execute()` và `Statement.execute()` trả publisher của `Result`. Với thao tác ghi, `Result.getRowsUpdated()` có thể cung cấp số hàng bị ảnh hưởng:

```java
Flux<Long> affectedRows = Flux.from(statement.execute())
        .concatMap(result -> Flux.from(result.getRowsUpdated()));
```

Không nên luôn giả định có đúng một `Result` hoặc chỉ đọc `Mono.from(execute())` nếu driver có thể phát nhiều kết quả. Hãy tiêu thụ publisher theo hợp đồng API và nhu cầu của ứng dụng.

Nếu chỉ cần biết thao tác hoàn tất, có thể bỏ qua số lượng bằng `.then()`. Nếu cần thống kê số hàng ghi, hãy cộng các giá trị một cách có kiểm soát:

```java
Mono<Long> totalRowsUpdated = Flux.from(statement.execute())
        .concatMap(result -> Flux.from(result.getRowsUpdated()))
        .reduce(0L, Long::sum);
```

Khả năng báo số hàng bị ảnh hưởng và cách biểu diễn kết quả có thể phụ thuộc loại câu lệnh và driver. Nếu ứng dụng cần số lượng chính xác cho logic nghiệp vụ, hãy xác minh trên driver/database mục tiêu.

## 16. Driver quyết định chiến lược batching

R2DBC SPI chuẩn hóa hợp đồng API, nhưng không bắt buộc mọi driver phải thực hiện batch theo cùng một chiến lược vật lý. Tùy driver, một batch có thể được gửi bằng giao thức native, thực thi tuần tự, chia thành nhiều lần gửi hoặc dùng cơ chế nội bộ khác.

Do đó:

- Không mặc định `Statement.add()` luôn tương ứng một network round trip.
- Không mặc định `Batch` nhanh hơn một câu lệnh riêng lẻ.
- Không mặc định mọi driver hỗ trợ cùng giới hạn kích thước batch hoặc cùng cách trả generated values.
- Không suy ra thứ tự xử lý, mức song song hoặc atomicity ngoài những gì SPI/database bảo đảm.
- Hãy benchmark trên driver và database thực tế với kích thước dữ liệu gần production.

Batch có thể giảm overhead phía ứng dụng và tạo cơ hội cho driver tối ưu, nhưng hiệu năng cuối cùng còn phụ thuộc index, constraint, trigger, log ghi, lock, transaction và tải đồng thời.

## 17. Chia batch thành các lô nhỏ

Không nên gom vô hạn hàng vào một statement batch. Một batch quá lớn có thể tiêu thụ nhiều bộ nhớ, giữ connection lâu, vượt giới hạn driver/database hoặc làm transaction kéo dài.

Có thể chia dữ liệu thành các lô cố định:

```java
Flux.fromIterable(customers)
        .buffer(500)
        .concatMap(this::insertCustomerChunk);
```

`buffer(500)` tạo các danh sách tối đa 500 phần tử; `concatMap` xử lý từng lô tuần tự, tránh tạo nhiều batch lớn cùng lúc. `insertCustomerChunk` có thể dùng một `Statement` và `Statement.add()` cho các phần tử trong lô.

Kích thước 500 chỉ là ví dụ. Hãy đo thời gian thực thi, bộ nhớ, số tham số, giới hạn packet và transaction duration trên workload thật. Một lô nhỏ hơn có thể tốt hơn nếu mỗi hàng có nhiều cột hoặc trigger phức tạp.

Nếu xử lý song song nhiều chunk bằng `flatMap`, cần giới hạn concurrency. Mỗi chunk có thể mở connection và tăng tải database; không để số batch đang chạy tăng không giới hạn.

## 18. Lỗi và retry khi thực thi batch

Một batch có thể thất bại do vi phạm unique/foreign key, dữ liệu không hợp lệ, timeout, mất kết nối hoặc lỗi driver. Lỗi được truyền qua reactive publisher khi thao tác thực thi.

Một số lưu ý:

- Nếu batch không nằm trong transaction, một phần thao tác có thể đã thành công trước khi lỗi xảy ra.
- Nếu nằm trong transaction và lỗi được truyền đúng tới transaction manager, transaction có thể rollback toàn bộ phần thay đổi tham gia transaction.
- Không retry mù quáng một batch ghi không idempotent. Lần chạy trước có thể đã ghi một phần hoặc toàn bộ trước khi kết nối bị mất.
- Với import có thể chạy lại, dùng khóa nghiệp vụ/unique constraint, upsert theo quy tắc rõ ràng hoặc bảng staging để xác định bản ghi đã xử lý.
- Phân loại lỗi tạm thời và lỗi dữ liệu. Vi phạm constraint thường không được giải quyết bằng retry ngay lập tức.

Nếu cần báo lỗi theo từng bản ghi, một batch gộp có thể làm việc xác định phần tử lỗi khó hơn tùy driver. Khi đó cân nhắc chia chunk nhỏ, lưu trạng thái import hoặc xử lý từng bản ghi có kiểm soát.

## 19. Quản lý kết nối và concurrency

`Connection` và `Statement` là các đối tượng gắn với một lần thực thi. Không chia sẻ cùng một `Statement` mutable giữa nhiều request hoặc nhiều luồng reactive đồng thời. Các lời gọi `bind`, `add` và `execute` cần được thực hiện theo đúng thứ tự trên một pipeline.

Tránh tạo statement ở ngoài publisher rồi dùng lại cho nhiều subscription. Thay vào đó, tạo connection và statement bên trong luồng thực thi cho mỗi lần gọi. `Mono.usingWhen` hoặc cơ chế resource management tương ứng giúp đóng connection khi hoàn tất, lỗi hoặc cancellation.

Khi import nhiều chunk, cần cân bằng:

- Số chunk đang thực thi đồng thời.
- Số connection trong pool.
- Thời gian giữ connection và transaction.
- Năng lực ghi của database.
- Bộ nhớ dùng để giữ các hàng chưa thực thi.

R2DBC non-blocking không có nghĩa có thể mở số connection hoặc chạy số batch vô hạn. Hãy giới hạn concurrency và theo dõi pool/database.

## 20. Kiểu dữ liệu và conversion khi dùng SPI trực tiếp

Khi dùng Spring Data repository/template, Spring Data hỗ trợ mapping entity và custom conversions. Khi dùng R2DBC SPI trực tiếp, ứng dụng bind giá trị Java vào statement; driver cần hỗ trợ codec cho kiểu đó.

Ví dụ các kiểu thường gặp:

| Kiểu Java | Kiểu SQL thường tương ứng | Lưu ý |
| --- | --- | --- |
| `String` | `VARCHAR`, `TEXT` | Kiểm tra độ dài và encoding |
| `Long` | `BIGINT` | Kiểm tra null và giới hạn giá trị |
| `Integer` | `INTEGER` | Không bind `Long` nếu driver/schema yêu cầu kiểu khác mà chưa xác minh |
| `BigDecimal` | `DECIMAL`, `NUMERIC` | Kiểm soát precision và scale |
| `Boolean` | `BOOLEAN` | Kiểu hỗ trợ phụ thuộc database |
| `LocalDate` | `DATE` | Biểu diễn ngày không có giờ |
| `LocalDateTime` | `TIMESTAMP` | Không tự mang múi giờ |
| `Instant`/`OffsetDateTime` | Kiểu timestamp có semantics thời điểm/offset | Kiểm tra driver và schema |
| `UUID` | `UUID` hoặc kiểu tương ứng | Hỗ trợ phụ thuộc hệ quản trị và driver |

Với giá trị null, dùng `bindNull(index, type)`. Với kiểu domain riêng, cần chuyển sang kiểu store mà driver hiểu hoặc cấu hình codec phù hợp. Không giả định custom converter của `R2dbcConverter` tự động được áp dụng khi bind trực tiếp bằng SPI.

## 21. So sánh với ghi nhiều lần bằng vòng lặp

Một cách đơn giản là tạo một statement cho mỗi hàng:

```java
Flux.fromIterable(customers)
        .concatMap(customer -> databaseClient.sql(
                        "INSERT INTO customer (id, name) VALUES (:id, :name)")
                .bind("id", customer.id())
                .bind("name", customer.name())
                .fetch()
                .rowsUpdated());
```

Ưu điểm là dễ đọc, dễ xử lý lỗi theo từng hàng và dùng API cấp cao `DatabaseClient`. Nhược điểm là mỗi hàng là một thao tác SQL riêng ở mức API; driver có thể không gom các thao tác đó thành một batch.

Với `Statement.add()`, cùng một statement nhận nhiều bộ bind rồi thực thi một lần qua API. Điều này có thể giảm overhead, nhưng việc xử lý lỗi và thống kê từng hàng có thể phụ thuộc driver. Hãy chọn theo yêu cầu về hiệu năng, khả năng quan sát lỗi và mapping, sau đó đo thay vì giả định batch luôn tốt hơn.

## 22. Lựa chọn API theo tình huống

| Nhu cầu | Cách tiếp cận | Lý do |
| --- | --- | --- |
| Lưu một entity | Repository `save` hoặc template | Giữ entity mapping và abstraction Spring Data |
| Lưu một publisher các entity | `ReactiveCrudRepository.saveAll` | API cấp cao, phù hợp CRUD; không mặc định là SPI batch |
| Nhiều câu SQL cố định, không có dữ liệu động | R2DBC `Batch` | Thêm các SQL string bằng `Batch.add` |
| Một câu SQL với nhiều bộ giá trị | R2DBC `Statement` + `bind` + `add()` | Tái sử dụng cùng câu SQL với nhiều binding set |
| Một thao tác SQL tham số đơn lẻ | `DatabaseClient` | Bind thuận tiện và quản lý kết nối qua Spring |
| Import lớn cần conversion/validation nghiệp vụ | Chia chunk, xử lý qua service/repository hoặc SPI theo nhu cầu | Kiểm soát bộ nhớ, lỗi và transaction |
| Cần atomicity qua nhiều thao tác | Transaction reactive hoặc transaction trên cùng SPI connection | Batching không tự thay thế transaction |

## 23. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ `Batch.add` và `Statement.add` giống nhau | Dùng sai API hoặc không bind được dữ liệu | Nhớ `Batch.add(sql)` thêm SQL; `Statement.add()` thêm bộ bind |
| Dùng `Batch` với dữ liệu người dùng bằng nối chuỗi | SQL injection và lỗi escape | Dùng `Statement` bind hoặc DatabaseClient |
| Dùng sai placeholder của driver | Lỗi parse hoặc bind tham số | Dùng marker theo driver; kiểm tra thứ tự bind index |
| Quên `Statement.add()` giữa các bộ bind | Chỉ bộ bind cuối hoặc một bộ được thực thi | Gọi add sau mỗi bộ trừ bộ cuối |
| Gọi `add()` sau bộ cuối rồi không bind bộ mới | Có thể tạo bộ bind rỗng/chưa đầy đủ | Chỉ gọi add khi chuẩn bị bộ tiếp theo |
| Không bind một tham số trong một bộ | Driver báo thiếu tham số hoặc lỗi execute | Bind đầy đủ mọi placeholder, dùng `bindNull` khi cần |
| Truyền null vào `bind` | Lỗi do API không chấp nhận null | Dùng `bindNull(index, type)` |
| Không tiêu thụ publisher `execute()` | SQL không được thực thi | Trả/subscribe publisher đúng vòng đời |
| Chỉ đọc một Result | Bỏ qua kết quả còn lại | Tiêu thụ toàn bộ publisher Result |
| Cho rằng batch tự atomic | Dữ liệu có thể được ghi một phần khi lỗi | Dùng transaction khi cần all-or-nothing |
| Chia sẻ Statement giữa nhiều request | Bind bị trộn hoặc trạng thái mutable không an toàn | Tạo statement riêng cho từng lần thực thi |
| Tạo batch quá lớn | Tăng bộ nhớ, thời gian giữ connection và nguy cơ timeout | Chia chunk và giới hạn concurrency |
| Cho rằng `saveAll` luôn gọi SPI batch | Kỳ vọng hiệu năng không đúng với implementation | Đo driver/framework hoặc dùng SPI có chủ đích |
| Retry toàn bộ batch không idempotent | Có thể ghi trùng hoặc xử lý lặp | Dùng transaction, khóa duy nhất và cơ chế idempotency |

## 24. Quy trình triển khai một luồng ghi batch

Khi cần ghi nhiều bản ghi, có thể đi theo trình tự:

1. Xác định các bản ghi dùng cùng một cấu trúc SQL hay cần nhiều câu SQL khác nhau.
2. Nếu là nhiều câu SQL cố định, cân nhắc `Batch`; nếu cùng một SQL với nhiều giá trị, chọn `Statement` có bind.
3. Kiểm tra cú pháp placeholder và kiểu bind của driver mục tiêu.
4. Xác định cách xử lý null và chuyển đổi kiểu dữ liệu.
5. Chọn kích thước chunk và concurrency phù hợp với pool/database.
6. Quản lý connection và statement trong reactive lifecycle; đóng connection ở mọi nhánh.
7. Xác định các thao tác có cần transaction all-or-nothing không.
8. Tiêu thụ toàn bộ `Result` và ghi nhận số hàng bị ảnh hưởng nếu cần.
9. Thiết kế xử lý lỗi, retry và idempotency trước khi chạy import có thể lặp lại.
10. Benchmark trên driver/database thật và theo dõi pool, latency, throughput, lock và lỗi.

## 25. Nguyên tắc thực hành

- Dùng `Batch` cho nhiều câu SQL dạng chuỗi đã được ứng dụng kiểm soát; không dùng nó để ghép giá trị động.
- Dùng `Statement` khi cần thực thi cùng một câu SQL với nhiều bộ giá trị bind.
- Hiểu rằng `Batch.add(String)` thêm câu SQL, còn `Statement.add()` thêm bộ bind hiện tại.
- Dùng placeholder theo driver và bind đúng thứ tự tham số.
- Gọi `bindNull(index, type)` cho tham số null; không truyền null vào `bind`.
- Gọi `Statement.add()` giữa các bộ bind và gọi `execute()` sau bộ cuối.
- Tạo Statement riêng cho mỗi lần thực thi; không chia sẻ object mutable giữa các pipeline đồng thời.
- Tiêu thụ tất cả `Result` từ publisher execute.
- Dùng transaction riêng khi cần đảm bảo nhiều thao tác cùng thành công hoặc rollback.
- Với API Spring Data `saveAll`, không giả định implementation luôn dùng SPI batching.
- Chia dữ liệu thành chunk và giới hạn concurrency để bảo vệ pool cùng database.
- Đo hiệu năng trên driver thực tế; SPI không cam kết một network round trip hoặc một chiến lược thực thi cố định.
- Khi dùng SPI trực tiếp, tự chịu trách nhiệm về mapping, conversion, generated values, lỗi và vòng đời connection.

## 26. Kết luận

R2DBC SPI có hai cơ chế batching với mục đích khác nhau. `Batch` gom nhiều chuỗi SQL thông qua `Batch.add(String)` và không có API bind tham số. `Statement` giữ một câu SQL có placeholder; ứng dụng bind một bộ giá trị, gọi `Statement.add()` để đưa bộ đó vào batch, rồi bind bộ tiếp theo trước khi `execute()`.

Với nhiều câu lệnh SQL cố định, `Batch` có thể phù hợp. Với nhiều bản ghi cùng cấu trúc và dữ liệu khác nhau, `Statement` có bind là lựa chọn thích hợp hơn và an toàn hơn so với nối chuỗi SQL. Trong Spring Data R2DBC, `saveAll` là abstraction lưu nhiều entity chứ không phải cam kết dùng `Statement.add()`. Hãy chọn đúng tầng API, quản lý transaction và connection rõ ràng, chia chunk hợp lý, tiêu thụ kết quả reactive và kiểm thử trên driver/database mục tiêu.

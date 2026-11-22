# Đọc theo cursor và transaction

Trong Spring Batch, `JdbcCursorItemReader<T>` đọc dữ liệu database bằng một JDBC cursor. Reader mở một câu truy vấn, giữ `ResultSet` đang mở và lần lượt chuyển tới từng row bằng `ResultSet.next()`. Cách đọc này phù hợp khi cần duyệt một tập kết quả lớn theo thứ tự mà không tải toàn bộ dữ liệu vào bộ nhớ.

Khi dùng cursor trong chunk-oriented step, cần hiểu rõ hai vòng đời chạy đồng thời:

- **Cursor lifecycle:** mở connection/statement/result set, đọc row, lưu vị trí checkpoint và đóng resource.
- **Chunk transaction lifecycle:** bắt đầu transaction, đọc và xử lý một nhóm item, ghi kết quả rồi commit hoặc rollback theo chunk.

Theo cấu hình mặc định, `JdbcCursorItemReader` mở cursor trên một connection riêng, tách khỏi connection mà step dùng cho transaction xử lý chunk. Điều này giúp cursor tiếp tục mở qua các lần commit của chunk. Nếu muốn chia sẻ connection với step, phải bật cơ chế extended connection và dùng `ExtendedConnectionDataSourceProxy`; database driver cũng cần hỗ trợ cursor có thể tồn tại qua commit.

Không nên coi việc đọc qua cursor là một transaction duy nhất bao trùm toàn bộ job. Cursor có thể sống trong suốt step, trong khi transaction ghi thường kết thúc sau từng chunk. Cách tách biệt này ảnh hưởng tới isolation, tính nhất quán của tập dữ liệu, rollback, restart và việc giữ connection trong thời gian dài.

## Cursor là gì?

Trong JDBC, một câu `SELECT` có thể trả về `ResultSet`. Cursor biểu diễn vị trí hiện tại trong tập kết quả đó. Ứng dụng gọi `next()` để chuyển tới row kế tiếp và đọc các cột của row hiện tại.

```text
SQL query
   |
   v
PreparedStatement.executeQuery()
   |
   v
ResultSet / cursor
   |
   +--> next() -> row 1
   +--> next() -> row 2
   +--> next() -> row 3
   +--> ...
   +--> next() -> false (EOF)
```

Cursor thường được dùng theo hướng tiến về phía trước (*forward-only*). Driver có thể lấy dữ liệu từ database theo từng đợt thông qua fetch size, nhưng chi tiết phụ thuộc driver và cấu hình database.

`JdbcCursorItemReader` bao bọc JDBC cursor thành hợp đồng `ItemReader<T>` của Spring Batch. Mỗi lần gọi `read()` trả về một object ánh xạ từ row tiếp theo; khi hết kết quả, reader trả `null`.

### Cursor khác với đọc tất cả row vào List

Với cách query thông thường, ứng dụng có thể gọi `queryForList` hoặc `query` để materialize toàn bộ kết quả thành collection. Với cursor reader, các row được tiêu thụ tuần tự:

| Cách đọc | Đặc điểm |
| --- | --- |
| Query trả `List` | Kết quả thường được materialize trong memory trước khi xử lý tiếp |
| `JdbcCursorItemReader` | Giữ cursor mở và ánh xạ từng row khi step gọi `read()` |
| `JdbcPagingItemReader` | Chạy nhiều query theo từng page, thường dùng sort key để tiếp tục trang kế tiếp |

Cursor giảm nhu cầu giữ toàn bộ object trong memory, nhưng giữ connection và database cursor trong thời gian step hoạt động. Nó không tự động nhanh hơn paging trong mọi database hoặc workload.

## JdbcCursorItemReader hoạt động như thế nào?

`JdbcCursorItemReader<T>` nằm trong package `org.springframework.batch.item.database`. Nó thực thi SQL khi mở reader và giữ các JDBC resource cần thiết cho tới khi step đóng reader.

Vòng đời tổng quát:

```text
Step bắt đầu
    |
    v
reader.open(ExecutionContext)
    |
    +--> lấy connection
    +--> tạo PreparedStatement
    +--> executeQuery()
    +--> giữ ResultSet/cursor
    |
    v
reader.read() lặp theo item
    |
    +--> ResultSet.next()
    +--> RowMapper ánh xạ row thành item
    +--> trả item cho chunk
    |
    v
Chunk transaction commit/rollback theo cấu hình step
    |
    +--> reader.update(ExecutionContext) tại checkpoint
    |
    v
Step kết thúc
    |
    v
reader.close()
    |
    +--> đóng ResultSet
    +--> đóng Statement
    +--> giải phóng connection theo ownership
```

Đây là mô hình lifecycle khái quát. Spring Batch quản lý việc gọi các callback `ItemStream`; không tự gọi `open`, `update` hoặc `close` trong code nghiệp vụ của reader.

## Cấu hình JdbcCursorItemReader cơ bản

Giả sử database có bảng `customer`:

```sql
CREATE TABLE customer (
    customer_id BIGINT PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL,
    balance DECIMAL(18, 2),
    created_at TIMESTAMP NOT NULL
);
```

Model Java:

```java
public record Customer(
        long customerId,
        String fullName,
        BigDecimal balance,
        LocalDateTime createdAt) {
}
```

Reader dùng builder:

```java
@Bean
@StepScope
JdbcCursorItemReader<Customer> customerCursorReader(
        DataSource dataSource,
        @Value("#{jobParameters['cutoffTime']}") String cutoffTime) {

    Timestamp cutoff = Timestamp.valueOf(
            LocalDateTime.parse(cutoffTime));

    return new JdbcCursorItemReaderBuilder<Customer>()
            .name("customerCursorReader")
            .dataSource(dataSource)
            .sql("""
                    SELECT customer_id, full_name, balance, created_at
                    FROM customer
                    WHERE created_at < ?
                    ORDER BY customer_id
                    """)
            .preparedStatementSetter(ps -> ps.setTimestamp(1, cutoff))
            .rowMapper((rs, rowNum) -> new Customer(
                    rs.getLong("customer_id"),
                    rs.getString("full_name"),
                    rs.getBigDecimal("balance"),
                    rs.getTimestamp("created_at").toLocalDateTime()))
            .fetchSize(500)
            .saveState(true)
            .build();
}
```

Các phần chính:

- `dataSource`: datasource dùng để mở cursor connection.
- `sql`: câu truy vấn lấy dữ liệu.
- `preparedStatementSetter`: bind các giá trị cho placeholder `?`.
- `rowMapper`: chuyển từng row trong `ResultSet` thành object.
- `fetchSize`: gợi ý cho JDBC driver về số row nên lấy mỗi đợt.
- `saveState(true)`: cho phép reader lưu vị trí để hỗ trợ restart.
- `name`: tên ổn định dùng cho state trong `ExecutionContext`.

Ví dụ giả định `cutoffTime` có định dạng ISO local date-time, chẳng hạn `2026-11-15T00:00:00`. Nếu dữ liệu thời gian mang timezone, hãy dùng kiểu/format có offset và quy đổi nhất quán với database; không parse một thời điểm có timezone thành `LocalDateTime` rồi bỏ mất offset.

## RowMapper và vị trí cursor

`RowMapper<T>` nhận `ResultSet` đang đứng tại row hiện tại và ánh xạ row đó thành object. Nó không được tự gọi `ResultSet.next()`.

```java
RowMapper<Customer> customerMapper = (rs, rowNum) ->
        new Customer(
                rs.getLong("customer_id"),
                rs.getString("full_name"),
                rs.getBigDecimal("balance"),
                rs.getTimestamp("created_at").toLocalDateTime());
```

Spring Batch đã di chuyển cursor tới row cần đọc trước khi gọi mapper. Nếu mapper tự gọi `next()`, nó sẽ bỏ qua row hoặc làm thay đổi vị trí cursor ngoài dự kiến.

`JdbcCursorItemReader` có tùy chọn `verifyCursorPosition` để kiểm tra mapper có làm thay đổi vị trí cursor hay không. Nên giữ kiểm tra này bật trong trường hợp thông thường. Chỉ tắt nếu có lý do cụ thể và đã kiểm soát mapper.

Không giữ `ResultSet` hoặc `PreparedStatement` trong object nghiệp vụ sau khi mapper trả về. Resource JDBC thuộc reader và sẽ được đóng khi step kết thúc.

## Cursor connection và chunk transaction

Đây là phần quan trọng nhất khi đọc theo cursor. Một chunk-oriented step có transaction manager và transaction boundary riêng. `JdbcCursorItemReader` mặc định mở cursor bằng connection riêng; transaction của chunk thường dùng connection khác để ghi dữ liệu hoặc cập nhật metadata.

### Mặc định: cursor dùng connection riêng

Theo mặc định, reader mở connection riêng cho cursor. Connection này được giữ trong suốt thời gian đọc và không phải connection mà transaction manager của chunk dùng để thực thi writer.

```text
                Step execution
                     |
          +----------+----------+
          |                     |
          v                     v
  Cursor connection       Chunk transaction
          |                     |
  SELECT ...               BEGIN
          |                     |
  ResultSet.next()         Processor
          |                     |
  RowMapper                JDBC writer
          |                     |
  next item                COMMIT / ROLLBACK
          |                     |
  cursor vẫn mở            chunk kế tiếp
          |                     |
          +----------+----------+
                     |
              Step kết thúc
                     |
              đóng cursor
```

Ưu điểm của connection riêng là commit/rollback của chunk không tự đóng cursor connection. Reader có thể tiếp tục đọc các row tiếp theo qua nhiều chunk transaction.

Hệ quả là câu `SELECT` của cursor không mặc nhiên nằm trong cùng transaction với các lệnh `INSERT`/`UPDATE` của writer. Hai connection có thể nhìn thấy dữ liệu theo isolation level và snapshot riêng. Nếu writer cập nhật chính các row mà cursor đang đọc, cần hiểu rõ database semantics và tránh giả định reader sẽ thấy ngay thay đổi vừa commit từ writer.

### Chunk transaction không rollback chuyển động cursor

Khi `ResultSet.next()` di chuyển tới row tiếp theo, đó là trạng thái của cursor trên connection reader. Rollback transaction ghi của chunk không làm database cursor tự lùi về row trước.

Spring Batch quản lý item buffering, checkpoint và reader state theo cơ chế của step. Không tự gọi `ResultSet.previous()` hoặc tự tua cursor trong processor/writer để cố khôi phục khi rollback. Reader cần triển khai đúng `ItemStream` contract và để framework quản lý restart/retry.

Khi một chunk thất bại, cần phân biệt:

- Transaction database của chunk có thể rollback các thay đổi chưa commit.
- Cursor vật lý đã được advance khi reader lấy item.
- Spring Batch có cơ chế xử lý item đã đọc trong chunk và state checkpoint theo step/fault-tolerance configuration.
- Khi process/job restart, reader mở lại query và phục hồi vị trí từ state đã lưu.

Vì vậy, không được suy ra rằng rollback database sẽ làm `JdbcCursorItemReader` đọc lại từ đầu chunk bằng cách rollback cursor. Hãy kiểm thử retry/skip với đúng step configuration và database driver.

## Shared extended connection

Trong một số trường hợp, ứng dụng muốn cursor dùng connection được chia sẻ với các hoạt động xử lý của step. `JdbcCursorItemReader` hỗ trợ tùy chọn `useSharedExtendedConnection`.

Để dùng cơ chế này, datasource cần được bọc bằng `ExtendedConnectionDataSourceProxy`, và JDBC driver/database phải hỗ trợ cursor có thể tồn tại qua commit (*holdable cursor*). Reader yêu cầu holdability phù hợp để cursor không bị đóng khi chunk transaction commit.

Ví dụ cấu hình datasource proxy:

```java
@Bean
ExtendedConnectionDataSourceProxy extendedDataSource(DataSource dataSource) {
    return new ExtendedConnectionDataSourceProxy(dataSource);
}
```

Sau đó cấu hình reader dùng datasource proxy và bật shared connection:

```java
@Bean
@StepScope
JdbcCursorItemReader<Customer> sharedCustomerReader(
        ExtendedConnectionDataSourceProxy extendedDataSource) {

    return new JdbcCursorItemReaderBuilder<Customer>()
            .name("sharedCustomerReader")
            .dataSource(extendedDataSource)
            .sql("SELECT customer_id, full_name FROM customer ORDER BY customer_id")
            .rowMapper((rs, rowNum) -> new Customer(
                    rs.getLong("customer_id"),
                    rs.getString("full_name"),
                    null,
                    null))
            .useSharedExtendedConnection(true)
            .saveState(true)
            .build();
}
```

Ví dụ chỉ minh họa reader. Trong cấu hình thật, transaction manager và các component dùng chung datasource cần được cấu hình nhất quán để proxy có thể chia sẻ extended connection đúng cách. Đừng tạo proxy riêng biệt cho reader và transaction manager rồi cho rằng chúng tự chia sẻ cùng một connection; chúng cần cùng cơ chế proxy/target resource theo hướng dẫn của Spring.

### Điều kiện và giới hạn

Trước khi bật `useSharedExtendedConnection`, kiểm tra:

- Database driver hỗ trợ holdable cursor qua commit.
- Connection có thể yêu cầu `ResultSet.HOLD_CURSORS_OVER_COMMIT`.
- `ExtendedConnectionDataSourceProxy` được dùng đúng trong cấu hình datasource/transaction manager.
- Không có component khác đóng hoặc thay đổi connection ngoài lifecycle được quản lý.
- Hành vi khi rollback, commit và restart đã được kiểm thử trên driver production.

Nếu driver không hỗ trợ holdable cursor, việc chia sẻ connection có thể làm cursor bị đóng sau commit hoặc reader không hoạt động như mong muốn. Khi đó, giữ cấu hình mặc định dùng connection riêng thường là lựa chọn an toàn hơn.

### Khi nào cần shared connection?

Chỉ bật khi có yêu cầu rõ ràng về transaction/connection sharing. Ví dụ, một quy trình cần đọc và ghi trên cùng connection/resource để đạt semantics database cụ thể. Tuy nhiên, shared connection có thể làm tăng coupling giữa cursor lifecycle và transaction lifecycle, đồng thời giữ connection trong thời gian dài.

Không bật chỉ vì nghĩ rằng reader và writer phải luôn dùng cùng connection. Với phần lớn batch read/write thông thường, connection riêng mặc định là thiết kế hợp lý.

## Isolation level và tính nhất quán của dữ liệu

Cursor đọc một tập kết quả trong khi các transaction khác có thể thêm, sửa hoặc xóa row. Việc reader nhìn thấy dữ liệu thay đổi như thế nào phụ thuộc database, isolation level, cursor implementation và thời điểm query được thực thi.

Một số khái niệm cần phân biệt:

- **Read committed:** mỗi lần đọc có thể chỉ nhìn thấy dữ liệu đã commit; snapshot có thể khác nhau theo statement hoặc transaction tùy database.
- **Repeatable read:** hạn chế một số thay đổi đối với row đã đọc, nhưng semantics cụ thể phụ thuộc database.
- **Snapshot isolation/MVCC:** query có thể đọc một snapshot nhất quán tại một thời điểm, tùy engine và transaction scope.
- **Serializable:** mức cô lập cao hơn, có thể tăng locking/contention và giảm concurrency.

Không thể khẳng định mọi cursor JDBC luôn nhìn thấy một snapshot cố định tới EOF. Một số database tạo snapshot cho câu SELECT tại thời điểm mở cursor; một số hành vi phụ thuộc transaction isolation và cấu hình server. Hãy kiểm tra tài liệu database/driver thực tế.

### Dữ liệu thay đổi trong lúc job chạy

Giả sử cursor đọc bảng `orders` trong khi một ứng dụng khác thêm row mới hoặc cập nhật `status`:

```text
T0: batch mở cursor và chạy SELECT
T1: batch đọc order 1..100
T2: ứng dụng khác INSERT order 101 và COMMIT
T3: batch đọc tiếp
```

Liệu order 101 có xuất hiện hay không phụ thuộc semantics cursor/snapshot của database. Tương tự, row đã được đọc có thể phản ánh giá trị tại thời điểm query mở hay thời điểm fetch tùy engine.

Nếu nghiệp vụ yêu cầu tập input cố định, có thể:

- Chọn cutoff/watermark và chỉ đọc row có `created_at` nhỏ hơn cutoff.
- Dùng trạng thái batch/staging để đóng băng tập dữ liệu.
- Dùng snapshot isolation phù hợp nếu database hỗ trợ và thời lượng transaction chấp nhận được.
- Lưu manifest các khóa cần xử lý.
- Đọc từ bảng staging/immutable source.

Chỉ dùng `ORDER BY` để ổn định thứ tự, không phải để đóng băng tập dữ liệu. Thứ tự ổn định và snapshot ổn định là hai yêu cầu khác nhau.

## ORDER BY là điều kiện quan trọng cho restart

Khi restart, `JdbcCursorItemReader` thường thực thi lại SQL và khôi phục vị trí bằng cách tiến tới row tương ứng với số item đã checkpoint. Nếu kết quả query không có thứ tự xác định, cùng một vị trí có thể trỏ tới row khác ở lần chạy sau.

Nên có `ORDER BY` trên một khóa duy nhất hoặc một tổ hợp khóa duy nhất:

```sql
SELECT order_id, customer_id, amount
FROM orders
WHERE batch_status = 'READY'
ORDER BY created_at, order_id
```

`created_at` có thể trùng giữa nhiều row; `order_id` bổ sung tie-breaker duy nhất. Nếu chỉ `ORDER BY created_at`, database có thể trả các row cùng timestamp theo thứ tự khác nhau ở lần query tiếp theo.

Không dựa vào thứ tự vật lý của bảng, index hoặc execution plan. Query cần xác định thứ tự một cách tường minh.

## Checkpoint và restart của JdbcCursorItemReader

`JdbcCursorItemReader` triển khai `ItemStream`, do đó có thể lưu state vào `ExecutionContext`. Khi `saveState(true)`, reader ghi vị trí item đã đọc theo cơ chế của `AbstractCursorItemReader` và sử dụng state đó khi mở lại.

Ở lần restart, reader thường:

1. Mở lại SQL query.
2. Khôi phục số item đã xử lý/đọc theo checkpoint đã commit.
3. Di chuyển cursor tới vị trí cần tiếp tục.
4. Tiếp tục trả item kế tiếp.

Tùy driver và cấu hình, reader có thể dùng `ResultSet.absolute()` để di chuyển nhanh nếu `driverSupportsAbsolute` được bật và driver hỗ trợ; nếu không, reader có thể tiến cursor tuần tự tới vị trí checkpoint. Không bật tùy chọn absolute chỉ dựa trên suy đoán; xác nhận driver hỗ trợ.

### Tên reader phải ổn định

Tên reader được dùng để tạo key state trong `ExecutionContext`. Giữ `.name("customerCursorReader")` ổn định qua restart. Đổi tên có thể khiến reader không tìm thấy checkpoint cũ.

### SQL và parameters phải ổn định

Khi restart cùng `JobInstance`, query cần trả về cùng logical dataset và cùng thứ tự. Nếu thay cutoff, filter, join hoặc identifying parameters, checkpoint cũ có thể không còn phù hợp.

Nếu query phụ thuộc thời gian hiện tại (`CURRENT_TIMESTAMP`) hoặc dữ liệu mutable mà không có cutoff, lần restart có thể nhận tập kết quả khác. Tính các giá trị cutoff trước khi launch, truyền qua `JobParameters` và giữ nguyên khi restart.

### saveState false

Nếu tắt `saveState`, reader không lưu vị trí để restart. Job có thể không tiếp tục từ checkpoint như mong đợi. Chỉ tắt state khi step không cần restart hoặc ứng dụng có cơ chế định vị lại dữ liệu khác.

Không tự sửa key trong `ExecutionContext` hoặc thay `currentItemCount` bằng SQL metadata khi không có hiểu biết về reader state contract. Để reader và `JobRepository` quản lý checkpoint.

## Cursor và rollback trong fault-tolerant step

Khi step có retry hoặc skip, reader có thể được gọi trong một chuỗi thực thi phức tạp hơn chunk bình thường. Spring Batch có thể buffer item đã đọc để reprocess mà không cần đọc lại cursor, tùy chế độ xử lý và reader semantics.

Các điểm cần nhớ:

- Cursor thường tiến về phía trước; database rollback không tua `ResultSet`.
- Item đã đọc trong chunk có thể được framework giữ trong buffer khi retry/rollback.
- Checkpoint chỉ nên đại diện cho tiến độ được commit theo step lifecycle.
- Reader không nên có side effect nghiệp vụ trong `read()`.
- Nếu nguồn đọc là transactional queue hoặc resource có semantics khác, cần cấu hình buffering phù hợp.

Không tự thêm retry cho mọi lỗi đọc cursor. Lỗi SQL syntax, schema mismatch hoặc mapping sai thường không phục hồi bằng retry. Lỗi kết nối tạm thời có thể retry theo chính sách, nhưng cursor/connection có thể đã mất và step có thể cần fail/restart từ checkpoint.

Nếu writer ghi vào cùng bảng mà reader đang query, cân nhắc nguy cơ row bị đọc lại, bỏ qua hoặc thay đổi trạng thái trong khi cursor đang mở. Có thể tách source và target, dùng staging table hoặc đánh dấu batch bằng một quy trình claim/lease riêng.

## Connection pool và tài nguyên database

Cursor giữ connection mở trong suốt thời gian reader hoạt động. Với một step chạy lâu, connection có thể bị giữ hàng phút hoặc hàng giờ. Điều này ảnh hưởng trực tiếp tới connection pool và khả năng phục vụ các job khác.

Ví dụ, pool có 10 connection nhưng 8 job đồng thời giữ cursor connection. Chỉ còn 2 connection cho transaction writer, metadata repository và request khác. Nếu writer cần connection từ cùng pool, có thể xảy ra chờ hoặc deadlock pool nếu cấu hình pool không đủ.

Các nguyên tắc vận hành:

- Tính số connection cần cho cursor, chunk transaction, repository và các worker khác.
- Đặt pool size theo concurrency thực tế, không chỉ số thread launcher.
- Đặt query timeout và connection/network timeout phù hợp.
- Đóng reader trong mọi đường kết thúc step; để Spring Batch quản lý lifecycle.
- Theo dõi connection active, borrowed duration và cursor count.
- Tránh giữ cursor trong step chờ một thao tác bên ngoài không có timeout.
- Kiểm tra giới hạn cursor/open statement của database.

Nếu dùng nhiều datasource, phân biệt pool dành cho cursor với pool dành cho transaction processing. Việc tách pool có thể giảm tranh chấp nhưng tăng tổng connection mà database phải chịu.

## Fetch size và hiệu năng

`fetchSize` là hint cho JDBC driver về số row nên lấy từ database trong một đợt. Ví dụ `.fetchSize(500)` đề nghị driver fetch khoảng 500 row mỗi round trip.

Fetch size không phải chunk size:

| Cấu hình | Ý nghĩa |
| --- | --- |
| JDBC fetch size | Gợi ý số row driver lấy mỗi lần từ server |
| Spring Batch chunk size | Số item được xử lý trong một transaction chunk |
| Page size | Số row mỗi query/page với paging reader |

Ví dụ fetch size 500 và chunk size 100 có thể khiến driver fetch dữ liệu theo đợt 500 row, trong khi Spring Batch commit sau mỗi 100 item. Cách driver buffer thực tế phụ thuộc driver và database.

Fetch size quá nhỏ có thể tăng round trip; quá lớn có thể tăng memory ở driver/client. Một số driver chỉ stream dữ liệu khi kết hợp fetch size với auto-commit/isolation hoặc cấu hình đặc biệt. Đọc tài liệu JDBC driver và benchmark trên môi trường gần production.

Ngoài fetch size, hiệu năng còn phụ thuộc:

- Index hỗ trợ điều kiện `WHERE` và `ORDER BY`.
- Số cột trả về và kích thước row.
- Chi phí `RowMapper` và conversion.
- Thời gian xử lý processor/writer.
- Cursor holdability và isolation level.
- Network latency giữa batch node và database.

Chỉ select các cột cần dùng, tránh `SELECT *` nếu bảng có BLOB/CLOB hoặc nhiều cột lớn không cần thiết.

## Query timeout, max rows và warning

`JdbcCursorItemReader` hỗ trợ các cấu hình JDBC liên quan tới query, tùy builder/version:

- `queryTimeout`: giới hạn thời gian thực thi statement theo hỗ trợ của driver.
- `maxRows`: giới hạn số row được trả về nếu nghiệp vụ cần giới hạn tập đọc.
- `fetchSize`: hint về số row fetch mỗi đợt.
- `ignoreWarnings`: quyết định cách xử lý SQL warning theo cấu hình reader.
- `verifyCursorPosition`: kiểm tra mapper không tự di chuyển cursor.

Các giới hạn này không thay thế timeout ở connection pool, socket hoặc database server. Nếu query bị treo do lock hoặc network, cần timeout ở tầng phù hợp.

Không đặt `maxRows` chỉ để job chạy nhanh hơn nếu nó làm mất dữ liệu. Nếu cần chia batch, dùng cutoff, partition hoặc giới hạn nghiệp vụ được ghi nhận trong `JobParameters`.

## Đọc và ghi cùng database

Một pattern thường gặp là cursor đọc từ bảng nguồn, processor biến đổi item, writer ghi vào bảng đích:

```text
JdbcCursorItemReader
        |
        v
ItemProcessor
        |
        v
JdbcBatchItemWriter
        |
        v
Target table
```

Nếu reader và writer cùng dùng một datasource nhưng reader mặc định dùng connection riêng, writer transaction không nhất thiết kiểm soát query cursor. Cần xem xét:

- Hai connection có isolation level khác nhau không?
- Query có đọc những row mà writer đang update không?
- Writer có thay đổi cột dùng trong điều kiện `WHERE` của cursor không?
- Có thể phát sinh deadlock/lock contention không?
- Khi restart, query có còn trả về đúng tập row ban đầu không?

Ví dụ rủi ro: cursor query `WHERE status = 'READY' ORDER BY id`, writer cập nhật `status = 'DONE'` trên cùng bảng. Nếu cursor được mở lại sau restart, các row đã chuyển `DONE` có thể không còn trong kết quả query; số row đã checkpoint có thể không còn ánh xạ đúng vị trí. Cần dùng tập input ổn định hơn, chẳng hạn claim `batch_id` trước khi đọc hoặc copy khóa cần xử lý vào staging table.

### Không nên dùng offset/checkpoint theo vị trí trên tập kết quả mutable

Restart theo số row đã đọc giả định query result có thứ tự và nội dung ổn định. Nếu các row bị xóa hoặc thay đổi điều kiện lọc, vị trí thứ N có thể trỏ tới item khác. Với nguồn mutable, dùng keyset/watermark hoặc snapshot manifest để định vị ổn định.

## Cursor reader và paging reader

`JdbcCursorItemReader` và `JdbcPagingItemReader` đều đọc dữ liệu database theo từng item, nhưng cách giữ state và tương tác database khác nhau.

| Tiêu chí | Cursor reader | Paging reader |
| --- | --- | --- |
| Cách truy vấn | Một query mở cursor/ResultSet kéo dài | Nhiều query theo từng page |
| Connection | Thường giữ cursor connection mở suốt step | Thường thực thi query theo page và giải phóng statement/connection theo lifecycle từng query |
| Điều kiện restart | Mở lại query và khôi phục vị trí cursor | Dùng sort key/page state để tiếp tục |
| Phù hợp | Database/driver hỗ trợ cursor tốt, cần đọc tuần tự | Dataset lớn, muốn chia truy vấn theo page hoặc cần keyset-style continuation |
| Tài nguyên | Giữ cursor/connection lâu | Nhiều query round trip, ít phụ thuộc cursor dài hạn |
| Dữ liệu thay đổi | Snapshot/cursor semantics phụ thuộc database | Page boundary cũng có thể bị ảnh hưởng nếu sort key/dataset thay đổi |

Không có lựa chọn tốt nhất cho mọi database. Cursor thường hiệu quả khi driver stream tốt và query result ổn định. Paging phù hợp khi cần query theo từng trang và có sort key đáng tin cậy. Đánh giá trên workload, driver, index và isolation thực tế.

## Đọc nhiều cursor hoặc nhiều step

Một job có thể có nhiều step, mỗi step dùng cursor reader riêng. Cần đặt tên reader khác nhau để state không đè nhau và tính đủ connection pool cho các step có thể chạy đồng thời.

Không nên chia sẻ cùng một `JdbcCursorItemReader` instance giữa nhiều step hoặc nhiều `StepExecution` đồng thời. Reader giữ cursor, ResultSet và vị trí hiện tại; state này thuộc một execution.

Nếu cần nhiều query song song, tạo reader riêng cho mỗi partition hoặc step scope. Mỗi reader phải có SQL/parameter/resource phù hợp và state riêng.

## Đăng ký ItemStream và scope

`JdbcCursorItemReader` triển khai `ItemStream`, nên khi được cấu hình trực tiếp làm reader của step, Spring Batch quản lý lifecycle của nó:

```java
.reader(customerCursorReader)
```

Nếu reader bị ẩn trong một wrapper không forward `ItemStream`, cần đăng ký stream delegate tường minh bằng `.stream(...)` hoặc để wrapper implement/forward `ItemStreamReader<T>`.

Reader thường nên là `@StepScope` khi SQL hoặc parameter phụ thuộc `JobParameters`/`ExecutionContext`. Điều này trì hoãn việc tạo reader cho tới khi step execution có context.

Không tạo một singleton reader mutable rồi dùng đồng thời cho nhiều execution. Mỗi step execution cần reader state và cursor riêng.

## Transaction manager và datasource

Chunk step được cấu hình với `PlatformTransactionManager`. Writer database nên dùng datasource tương ứng với transaction manager nếu muốn ghi dữ liệu cùng transaction chunk.

```java
@Bean
Step readCustomersStep(
        JobRepository jobRepository,
        @Qualifier("businessTransactionManager") PlatformTransactionManager transactionManager,
        JdbcCursorItemReader<Customer> customerCursorReader,
        ItemProcessor<Customer, CustomerSummary> summaryProcessor,
        JdbcBatchItemWriter<CustomerSummary> summaryWriter) {

    return new StepBuilder("readCustomersStep", jobRepository)
            .<Customer, CustomerSummary>chunk(200, transactionManager)
            .reader(customerCursorReader)
            .processor(summaryProcessor)
            .writer(summaryWriter)
            .build();
}
```

Nếu `JobRepository` dùng datasource/transaction manager khác với business writer, cần hiểu cách metadata transaction và business transaction được phối hợp. Một chunk có thể commit business output nhưng lỗi khi cập nhật metadata ở resource khác, hoặc ngược lại, tùy cấu hình transaction manager. Không mặc định nhiều datasource tạo thành một distributed transaction.

Với transaction manager cục bộ, một transaction thường chỉ bảo vệ một transactional resource. Nếu cần atomicity giữa nhiều database hoặc giữa database và file/message, cân nhắc outbox, staging, compensation hoặc distributed transaction phù hợp.

## Kiểm thử cursor và transaction

Test cần chạy trên database/driver gần với production vì cursor holdability, fetch size, isolation và auto-commit có thể khác nhau giữa H2, PostgreSQL, Oracle, SQL Server hoặc các JDBC driver khác.

### Kiểm thử đọc tuần tự

Tạo bảng fixture với khóa duy nhất, mở reader và xác nhận:

- Row được trả theo thứ tự `ORDER BY`.
- Mỗi row chỉ được trả một lần trong lần chạy bình thường.
- `read()` trả `null` ở EOF.
- Mapper không tự di chuyển cursor.
- Reader đóng connection/statement/result set khi step kết thúc.

### Kiểm thử chunk commit

Chạy step với chunk size nhỏ, ví dụ 2 hoặc 3. Sau mỗi chunk, xác nhận writer đã commit số row mong đợi và step tiếp tục đọc cursor cho tới EOF. Kiểm tra cursor vẫn hoạt động sau nhiều lần commit trên driver thực tế.

### Kiểm thử rollback

Tạo writer test double hoặc constraint violation ở một chunk. Xác nhận database changes của chunk hiện tại rollback theo transaction manager, còn chunk trước đã commit vẫn tồn tại. Quan sát reader retry/buffering theo cấu hình step; không giả định rollback database tua cursor.

### Kiểm thử restart

Cho job đọc một số chunk rồi thất bại. Restart cùng identifying `JobParameters` và xác nhận reader:

- Mở lại cùng SQL và parameter.
- Dùng cùng reader name.
- Tiếp tục từ checkpoint đã commit.
- Không bỏ sót hoặc lặp row.
- Có cùng thứ tự kết quả nhờ `ORDER BY` ổn định.

Thử thêm trường hợp source table thay đổi giữa hai lần chạy để xác nhận job phát hiện hoặc ngăn restart trên dataset không tương thích.

### Kiểm thử connection riêng và shared extended connection

Nếu dùng default connection riêng, xác nhận cursor còn mở qua chunk commit và connection được giải phóng khi step kết thúc. Nếu bật shared extended connection, chạy test trên đúng driver production để xác nhận holdable cursor tồn tại qua commit và resource không bị đóng sớm.

### Kiểm thử connection pool

Chạy nhiều job đồng thời và theo dõi active connection. Xác nhận pool đủ cho cursor connection cộng với transaction connections và repository connections. Test cần có timeout để phát hiện pool starvation.

### Kiểm thử isolation và concurrent update

Trong một transaction khác, thêm/sửa/xóa row trong khi cursor đang đọc. Quan sát kết quả theo isolation level của database. Dùng test này để chứng minh semantics snapshot thực tế, không dựa trên giả định chung về JDBC cursor.

## Lỗi thường gặp

### Nghĩ cursor nằm trong transaction chunk

Mặc định reader dùng connection riêng. Cursor query không mặc nhiên thuộc transaction mà writer dùng. Hiểu rõ connection ownership và isolation.

### Nghĩ rollback sẽ tua ResultSet về trước

Cursor position là trạng thái của JDBC ResultSet, không phải row update trong transaction writer. Để Spring Batch quản lý buffering/checkpoint/restart; không tự gọi `previous()`.

### Dùng shared connection mà không có proxy

`useSharedExtendedConnection(true)` cần `ExtendedConnectionDataSourceProxy` và driver hỗ trợ holdable cursor. Thiếu điều kiện có thể làm cursor đóng sau commit.

### Không có ORDER BY ổn định

Thứ tự query có thể thay đổi giữa lần chạy/restart. Sắp xếp bằng khóa duy nhất hoặc tổ hợp khóa duy nhất.

### Query trả dataset mutable

Row bị thêm/xóa hoặc đổi điều kiện filter có thể làm checkpoint theo vị trí không còn khớp. Dùng cutoff, staging, snapshot hoặc manifest.

### RowMapper gọi next()

Reader đã di chuyển cursor tới row hiện tại. Mapper gọi `next()` sẽ bỏ qua dữ liệu và phá cursor position. Chỉ ánh xạ row hiện tại.

### Giữ cursor quá lâu và cạn connection pool

Cursor connection sống trong thời gian step. Tính pool capacity, timeout và concurrency; đóng reader đúng lifecycle.

### Nhầm fetch size với chunk size

Fetch size là hint cho driver; chunk size là transaction unit của Spring Batch. Chọn độc lập dựa trên driver và workload.

### Tắt saveState nhưng vẫn mong restart

Không có checkpoint reader thì không thể tiếp tục đúng vị trí theo cơ chế reader. Bật state và giữ tên reader ổn định nếu cần restart.

### Đổi SQL/parameter khi restart

Query result thay đổi làm checkpoint trỏ tới row khác. Giữ identifying parameters, cutoff và SQL semantics ổn định.

### Dùng một reader instance cho nhiều execution

Cursor và vị trí đọc là state mutable. Dùng `@StepScope` hoặc instance riêng cho mỗi execution/partition.

## Nguyên tắc thiết kế

Khi đọc database theo cursor trong Spring Batch, hãy xác định:

1. Query có `ORDER BY` trên khóa duy nhất hoặc tổ hợp khóa duy nhất không?
2. Tập row có ổn định trong suốt job và qua restart không?
3. Reader mặc định dùng connection riêng có đáp ứng yêu cầu không?
4. Có thật sự cần `useSharedExtendedConnection` không?
5. Nếu dùng shared connection, datasource proxy và holdable cursor có được hỗ trợ không?
6. Chunk transaction và cursor connection có isolation/visibility như mong đợi không?
7. Writer có dùng đúng transaction manager/datasource không?
8. `fetchSize`, `queryTimeout` và pool capacity có phù hợp driver/workload không?
9. Reader name, SQL parameters và `saveState` có ổn định khi restart không?
10. RowMapper có chỉ đọc row hiện tại và không di chuyển cursor không?
11. Retry/rollback có được kiểm thử trên step thật không?
12. Monitoring có theo dõi cursor, connection duration, pool usage và query time không?

Với phần lớn batch read tuần tự, bắt đầu bằng `JdbcCursorItemReader` dùng connection riêng mặc định, query có thứ tự xác định, `RowMapper` stateless và `saveState(true)`. Chỉ bật shared extended connection khi database/driver hỗ trợ và có nhu cầu transaction/connection sharing cụ thể. Giữ dataset ổn định bằng cutoff hoặc staging, tính đủ connection pool và kiểm thử commit, rollback, restart trên đúng database production.

## Ghi nhớ

`JdbcCursorItemReader` mở một SQL cursor/`ResultSet` và trả từng row qua `read()`, thường dùng `RowMapper` để ánh xạ object. Cursor là resource sống trong suốt step; chunk transaction lại commit/rollback theo từng nhóm item. Mặc định reader dùng connection riêng để cursor không bị đóng bởi chunk commit; do đó SELECT không mặc nhiên nằm trong cùng transaction với writer. Muốn chia sẻ connection phải bật `useSharedExtendedConnection`, dùng `ExtendedConnectionDataSourceProxy` và driver hỗ trợ holdable cursor qua commit. Rollback không tua `ResultSet`; Spring Batch quản lý buffering/checkpoint và restart. Giữ query có `ORDER BY` duy nhất, parameters và dataset ổn định, bật `saveState`, giữ reader name, chọn fetch size phù hợp và tính connection pool cho cursor chạy lâu. Kiểm thử isolation, commit, rollback, restart và shared connection trên đúng JDBC driver/database production.

# Đo JDBC và tách thời gian lấy kết nối, thực thi, đọc kết quả

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Mô tả vòng đời một thao tác JDBC từ lúc ứng dụng yêu cầu connection đến khi đọc xong kết quả và trả connection về pool.
- Đo riêng thời gian chờ lấy connection, thời gian gọi execute, thời gian tiêu thụ ResultSet và thời gian commit/release.
- Giải thích vì sao thời gian `executeQuery()` không luôn bằng thời gian database thực thi SQL.
- Phân biệt thời gian client, thời gian server, thời gian mạng, thời gian chờ pool và chi phí ánh xạ dữ liệu.
- Dùng số liệu theo phân vị và theo query fingerprint để tìm nút thắt trong ứng dụng Java.
- Kết hợp JDBC instrumentation với execution plan và metric của connection pool để kiểm chứng tối ưu.

## 1. Vì sao cần tách thời gian trong JDBC?

Một API Java gọi cơ sở dữ liệu có thể chậm vì nhiều nguyên nhân khác nhau: chờ connection trong pool, mở kết nối vật lý, truyền câu lệnh qua mạng, database lập kế hoạch và thực thi SQL, truyền các hàng kết quả về, driver giải mã dữ liệu, ứng dụng ánh xạ ResultSet thành object hoặc transaction commit phải chờ log flush.

Nếu chỉ đo tổng thời gian của repository method, ta biết thao tác chậm nhưng chưa biết phần nào chiếm thời gian. Nếu chỉ đo `executeQuery()`, ta cũng có thể bỏ sót thời gian đọc các hàng do driver có thể lấy kết quả theo từng đợt hoặc buffer toàn bộ.

Phạm vi DATABASE_PERFORMANCE tập trung vào đo tải, execution plan, thống kê và cơ chế truy cập dữ liệu. Với ứng dụng Java, cần nối số liệu ở tầng JDBC với số liệu database để phân biệt thời gian chờ pool, network, server execution và result processing.

Một phép đo hữu ích cần trả lời:

- Ứng dụng chờ bao lâu để lấy connection?
- Mất bao lâu từ lúc gọi execute đến khi driver trả quyền điều khiển?
- Mất bao lâu để đọc hết ResultSet và chuyển thành dữ liệu ứng dụng?
- Transaction commit mất bao lâu?
- Có bao nhiêu hàng được đọc, bao nhiêu câu SQL được gửi và bao nhiêu lần gọi database?
- Thời gian chậm đến từ một vài truy vấn hay từ pool/concurrency toàn ứng dụng?

## 2. Vòng đời một thao tác JDBC

Một luồng truy vấn phổ biến có thể được chia thành các giai đoạn:

```text
Ứng dụng bắt đầu thao tác
          |
          v
DataSource.getConnection()
          |
          v
Chờ pool / tạo kết nối vật lý / xác thực
          |
          v
Tạo PreparedStatement và bind tham số
          |
          v
executeQuery() / execute()
          |
          v
Server xử lý + network + driver nhận kết quả
          |
          v
ResultSet.next() / getXxx() / mapping object
          |
          v
COMMIT (nếu transaction tường minh)
          |
          v
Đóng ResultSet/Statement
          |
          v
Connection.close() trả connection về pool
          |
          v
Hoàn tất thao tác
```

Đây là mô hình đo lường, không phải mọi driver đều thực hiện các bước hoàn toàn tách biệt. Driver có thể buffer dữ liệu ngay trong `executeQuery()`, hoặc chỉ lấy thêm dữ liệu khi ứng dụng gọi `ResultSet.next()`. Vì vậy, ranh giới timer ở client phản ánh thời gian của API được đo, không luôn cô lập chính xác công việc server.

## 3. Định nghĩa các khoảng thời gian

### Thời gian lấy connection (connection acquisition)

Đo từ lúc gọi `DataSource.getConnection()` đến khi nhận được `Connection` sử dụng được.

Với connection pool, khoảng này có thể bao gồm:

- Thời gian chờ một connection rảnh được trả về pool.
- Thời gian pool tạo connection vật lý mới khi chưa đủ connection.
- DNS, TCP handshake, TLS handshake và xác thực nếu cần mở kết nối mới.
- Khởi tạo session hoặc thiết lập một số thuộc tính connection.

Trong trường hợp pool đã có connection rảnh, thời gian acquisition chủ yếu là chi phí mượn connection và đồng bộ nội bộ. Khi pool cạn, thời gian chờ có thể tăng mạnh dù database vẫn xử lý SQL nhanh.

Để phân tích sâu, cần phân biệt pool borrow wait với physical connection creation. Một metric acquisition tổng hợp không cho biết chắc chắn thời gian đến từ chờ pool hay mở kết nối mới; hãy dùng metric/event của pool để tách hai trường hợp.

### Thời gian gọi execute (execute-call time)

Đo thời gian từ ngay trước `executeQuery()`, `executeUpdate()` hoặc `execute()` đến khi phương thức trả về hoặc ném lỗi.

Khoảng này có thể chứa:

- Gửi request qua driver và network.
- Parse, bind, plan hoặc tìm cached plan ở server.
- Thời gian database thực thi đủ để trả dữ liệu ban đầu.
- Driver buffer một phần hoặc toàn bộ result set.
- Chờ network fetch nếu driver cần nhận dữ liệu trước khi trả về.

Do đó, execute-call time là thời gian của lời gọi JDBC từ phía client. Nó không phải phép đo thuần server execution time.

### Thời gian đọc và tiêu thụ ResultSet

Đo thời gian từ lúc bắt đầu duyệt ResultSet đến khi đọc hết các hàng cần thiết và hoàn tất mapping.

Khoảng này có thể bao gồm:

- Các lần `ResultSet.next()` và fetch thêm batch từ server.
- Truyền dữ liệu qua network theo từng fetch.
- Driver chuyển đổi kiểu dữ liệu và giải mã giá trị.
- Ứng dụng gọi `getLong`, `getString`, `getTimestamp` hoặc getter tương ứng.
- Mapping mỗi hàng thành DTO/entity và các phép xử lý trong vòng lặp.

Nếu driver đã buffer toàn bộ kết quả trong execute-call, thời gian đọc có thể ngắn. Nếu driver dùng cursor hoặc fetch theo batch, thời gian đọc có thể chứa phần lớn network transfer và server fetch tiếp theo.

### Commit và release

Với transaction tường minh, commit có thể chờ database flush log theo durability mode. Đo commit riêng giúp phát hiện trường hợp SQL chạy nhanh nhưng xác nhận transaction chậm.

`Connection.close()` trong ứng dụng dùng pool thường trả connection về pool, không nhất thiết đóng socket hoặc session vật lý. Thời gian close/release thường nhỏ, nhưng nếu có reset session, rollback transaction chưa hoàn tất hoặc validation, nó có thể đáng kể.

## 4. Đo bằng đồng hồ đơn điệu trong Java

Dùng `System.nanoTime()` để đo khoảng thời gian. Đây là đồng hồ đơn điệu phù hợp cho elapsed time; không dùng `System.currentTimeMillis()` để đo duration vì đồng hồ lịch có thể bị điều chỉnh.

Ví dụ sau đo acquisition, execute-call và đọc kết quả riêng:

```java
long requestStart = System.nanoTime();
long acquireNanos = 0L;
long executeCallNanos = 0L;
long resultConsumeNanos = 0L;
long rowsRead = 0L;

try (Connection connection = dataSource.getConnection()) {
    long acquiredAt = System.nanoTime();
    acquireNanos = acquiredAt - requestStart;

    String sql = """
        SELECT order_id, customer_id, total_amount
        FROM orders
        WHERE customer_id = ?
        ORDER BY created_at DESC
        """;

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setLong(1, customerId);

        long executeStart = System.nanoTime();
        try (ResultSet rs = statement.executeQuery()) {
            long executeReturnedAt = System.nanoTime();
            executeCallNanos = executeReturnedAt - executeStart;

            long consumeStart = System.nanoTime();
            while (rs.next()) {
                long orderId = rs.getLong("order_id");
                long customer = rs.getLong("customer_id");
                BigDecimal amount = rs.getBigDecimal("total_amount");
                mapOrder(orderId, customer, amount);
                rowsRead++;
            }
            resultConsumeNanos = System.nanoTime() - consumeStart;
        }
    }
}

long totalNanos = System.nanoTime() - requestStart;
recordJdbcTimings(
    acquireNanos,
    executeCallNanos,
    resultConsumeNanos,
    totalNanos,
    rowsRead
);
```

Đây là ví dụ minh họa cách đặt timer. Trong code production, cần xử lý exception, ghi nhận lỗi và bảo đảm metric được phát ra cả khi thao tác thất bại. `mapOrder` là hàm ứng dụng giả định; thời gian mapping của nó đang nằm trong `resultConsumeNanos`.

### Đơn vị và chuyển đổi

`System.nanoTime()` trả về số nanosecond tương đối. Có thể chuyển sang millisecond để ghi metric:

```java
double millis = nanos / 1_000_000.0;
```

Giữ độ phân giải nanosecond trong phép tính, nhưng không diễn giải rằng hệ thống đo có độ chính xác vật lý đến từng nanosecond. Độ phân giải và overhead thực tế phụ thuộc JVM, OS và phần cứng.

## 5. Không cộng các timer lồng nhau một cách máy móc

Trong ví dụ trên, `executeCallNanos` và `resultConsumeNanos` được đo nối tiếp. Tổng của chúng cùng acquisition có thể gần bằng tổng thao tác, nhưng các khoảng khác như statement preparation, mapping, commit hoặc close chưa được đo riêng.

Nếu một timer cha bao trùm timer con, không cộng cả hai vào tổng vì sẽ đếm trùng. Ví dụ:

```text
total request:       |--------------------------------------|
connection acquire:  |----|
execute call:             |----------|
result consume:                      |----------------|
commit:                                                |---|
```

Định nghĩa metric rõ ràng:

- `jdbc.connection.acquire`: thời gian chờ `getConnection()`.
- `jdbc.statement.execute`: thời gian gọi execute API.
- `jdbc.result.consume`: thời gian duyệt ResultSet và mapping.
- `jdbc.transaction.commit`: thời gian commit tường minh.
- `jdbc.connection.release`: thời gian trả connection về pool.
- `jdbc.operation.total`: thời gian từ đầu thao tác đến khi hoàn tất.

Không nên suy ra `server_execution = execute_call - network` vì network, buffering và driver behavior không được đo độc lập trong timer client.

## 6. Tách pool wait khỏi mở kết nối vật lý

Connection pool như HikariCP quản lý một tập connection vật lý để ứng dụng mượn và trả lại. Khi gọi `getConnection()`, ứng dụng có thể:

1. Nhận ngay connection rảnh.
2. Chờ một connection đang được request khác sử dụng trả về.
3. Chờ pool tạo thêm connection nếu chưa đạt maximum và có thể mở kết nối.
4. Chờ timeout khi pool đã cạn và không có connection được trả về.

Metric cần theo dõi cùng acquisition latency:

- Active connections: số connection đang được mượn.
- Idle connections: số connection rảnh trong pool.
- Pending/waiting threads: số request đang chờ connection.
- Total connections: tổng connection hiện có.
- Connection creation rate và creation time.
- Acquisition timeout và số lần timeout.
- Connection usage duration: thời gian ứng dụng giữ connection.

Nếu acquisition p95 tăng cùng active connections chạm maximum và pending threads tăng, khả năng cao pool đang bão hòa. Nếu pool có idle connection nhưng acquisition vẫn chậm, hãy xem lock nội bộ pool, validation, DNS hoặc hành vi driver.

### Pool quá nhỏ và pool quá lớn

Pool quá nhỏ có thể khiến request chờ connection dù database còn năng lực xử lý. Pool quá lớn có thể đẩy database vào quá nhiều session đồng thời, tăng memory, context switching, lock contention và CPU scheduling.

Kích thước pool cần dựa trên năng lực database, số instance ứng dụng, số worker, thời gian giữ connection và mức concurrency cần phục vụ. Nếu có 12 instance, mỗi instance pool tối đa 30, database có thể nhận đến 360 connection từ ứng dụng đó; cần tính tổng với worker, admin, scheduler và service khác.

Không tăng pool chỉ vì acquisition latency cao. Trước hết kiểm tra database có đang bão hòa CPU, I/O hoặc lock hay không. Thêm connection vào một database đã bão hòa có thể làm execute time và p99 xấu hơn.

## 7. Đo execute-call time đúng cách

Đo ngay quanh lời gọi JDBC:

```java
long start = System.nanoTime();
try (ResultSet rs = statement.executeQuery()) {
    long elapsed = System.nanoTime() - start;
    metrics.recordExecuteCall(elapsed);
    // Đọc ResultSet ở bước riêng
}
```

Trong ví dụ này, `executeQuery()` trả về trước khi phần đọc ResultSet bắt đầu. Tuy nhiên, driver có thể đã nhận hoặc buffer nhiều dữ liệu trong lúc thực thi phương thức. Với driver khác, execute có thể trả về khi chỉ có một phần kết quả sẵn sàng.

Vì vậy, hãy ghi rõ metric là `execute-call`, không đặt tên là `database-time` nếu chưa có phép đo server-side tương ứng.

### Chuẩn bị statement và bind tham số

Thời gian tạo `PreparedStatement`, bind tham số và đóng statement có thể được đo riêng nếu cần. Tuy nhiên, đừng chia quá nhỏ ngay từ đầu nếu overhead instrumentation lớn hoặc số liệu không giúp quyết định.

PreparedStatement có thể giúp tái sử dụng statement và bind giá trị an toàn. Nhưng prepared statement ở JDBC không đảm bảo mọi hệ quản trị luôn dùng một server-side prepared plan; hành vi phụ thuộc driver, cấu hình và engine.

### Cache và lần chạy đầu

Lần chạy đầu có thể gồm parse, plan, load metadata, mở kết nối hoặc cache miss. Các lần sau có thể dùng plan cache, statement cache, buffer cache hoặc connection pool.

Đo riêng warm-up và steady state. Nếu chỉ đo lần đầu, có thể nhầm chi phí khởi tạo với chi phí thực thi ổn định. Nếu chỉ đo sau warm-up, có thể bỏ qua chi phí cold start quan trọng với workload ít chạy.

## 8. Đo thời gian đọc ResultSet và số hàng

ResultSet consumption cần được đo cùng số hàng và số byte ước lượng. Một truy vấn mất 20 ms để execute nhưng đọc 100.000 hàng trong 800 ms có profile khác truy vấn execute 400 ms rồi trả về 10 hàng.

Các metric hữu ích:

- Số hàng trả về.
- Thời gian từ hàng đầu tiên đến hàng cuối cùng.
- Thời gian `ResultSet.next()` nếu cần tách riêng.
- Thời gian gọi getter và mapping DTO/entity.
- Kích thước kết quả ước lượng hoặc số byte nhận qua network nếu driver/proxy cung cấp.
- Số fetch round trip hoặc fetch batch nếu quan sát được.

### Tách fetch khỏi mapping

Nếu cần biết thời gian do network/driver hay do logic mapping, có thể đo hai phần trong vòng lặp:

```java
long fetchAndReadStart = System.nanoTime();
long mappingNanos = 0L;
long rows = 0L;

while (rs.next()) {
    long mappingStart = System.nanoTime();

    OrderDto dto = new OrderDto(
        rs.getLong("order_id"),
        rs.getBigDecimal("total_amount")
    );
    output.add(dto);

    mappingNanos += System.nanoTime() - mappingStart;
    rows++;
}

long consumeNanos = System.nanoTime() - fetchAndReadStart;
```

`consumeNanos` bao gồm `next()`, getter, mapping và thời gian fetch do driver thực hiện. `mappingNanos` là phần đo lồng bên trong, vì vậy không cộng hai metric này với nhau. Đây là phép đo gần đúng; getter cũng có thể kích hoạt chuyển đổi hoặc giải mã dữ liệu.

Đừng tạo timer cho từng hàng trong mọi request nếu chi phí đo đáng kể. Có thể bật chi tiết theo sampling, theo endpoint hoặc trong benchmark.

## 9. Fetch size, cursor và buffering của JDBC driver

JDBC `Statement.setFetchSize()` là gợi ý cho driver về số hàng nên lấy mỗi lần fetch. Đây không phải cam kết chuẩn rằng mọi driver sẽ dùng cursor server-side hoặc thực hiện đúng số hàng đó.

```java
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setFetchSize(500);
    ps.setLong(1, customerId);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // xử lý từng hàng
        }
    }
}
```

Ý nghĩa fetch size phụ thuộc driver và cấu hình:

- Một số driver buffer toàn bộ kết quả mặc định; execute-call có thể chịu phần lớn chi phí truyền.
- Một số driver hỗ trợ cursor hoặc fetch theo batch; `ResultSet.next()` có thể chờ network khi cần batch tiếp theo.
- Một số driver cần tắt auto-commit hoặc cấu hình riêng mới dùng cursor streaming.
- Fetch size quá nhỏ làm tăng số round trip; quá lớn làm tăng memory ở client và lượng dữ liệu mỗi lần fetch.

Ví dụ PostgreSQL JDBC có các điều kiện riêng để dùng cursor-based fetching, trong đó auto-commit và fetch size cần được cấu hình phù hợp. MySQL Connector/J có các chế độ streaming/cursor khác nhau theo thuộc tính driver. Hãy đọc tài liệu đúng phiên bản driver thay vì giả định `setFetchSize()` luôn tạo streaming.

### Chọn fetch size

Chọn fetch size dựa trên:

- Số hàng trung bình và kích thước mỗi hàng.
- RAM của ứng dụng và số truy vấn đọc đồng thời.
- Round-trip latency giữa app và database.
- Khả năng driver buffer dữ liệu.
- Thời gian giữ cursor, connection và transaction.

Fetch size lớn có thể giảm round trip nhưng tăng memory footprint và thời gian giữ connection. Với dữ liệu lớn, streaming giảm bộ nhớ client nhưng có thể giữ transaction/snapshot và connection lâu hơn.

## 10. Transaction commit là một khoảng thời gian riêng

Trong auto-commit mode, mỗi statement thường được commit tự động theo hành vi driver và database. Nếu ứng dụng cần nhiều statement cùng atomicity, nên dùng transaction tường minh và đo commit riêng.

```java
long commitNanos = 0L;

connection.setAutoCommit(false);
try {
    updateOrder(connection, orderId);
    insertAudit(connection, orderId);

    long commitStart = System.nanoTime();
    connection.commit();
    commitNanos = System.nanoTime() - commitStart;
} catch (SQLException e) {
    connection.rollback();
    throw e;
}
```

Commit latency có thể chịu ảnh hưởng bởi log flush, group commit, replication acknowledgement, storage latency và transaction size. Một statement có thể execute nhanh nhưng commit chậm do durability path.

Đo commit riêng giúp liên hệ với WAL/redo/transaction log metrics. Không giảm độ bền commit hoặc tắt synchronous durability chỉ để làm metric đẹp hơn nếu yêu cầu nghiệp vụ cần durable commit.

Với transaction nhiều statement, nên ghi cả tổng transaction duration và từng execute duration. Tổng thời gian giữ connection/transaction có thể ảnh hưởng pool và lock contention ngay cả khi từng câu SQL riêng lẻ nhanh.

## 11. Phân biệt thời gian client với server execution

Client timer không thể tự tách chính xác server execution, network và driver overhead. Để tìm server-side cost, cần đối chiếu metric của database:

- Query fingerprint hoặc normalized SQL.
- Số lần gọi và tổng thời gian thực thi.
- Execution plan và estimated/actual rows.
- Logical reads, physical reads, buffer hits.
- CPU time, elapsed time và wait events.
- Lock wait, I/O wait, memory grant hoặc spill.
- Số hàng trả về và bytes truyền nếu có.

### PostgreSQL

`pg_stat_statements` có thể cung cấp số lần gọi, tổng/thời gian trung bình và các số liệu block cho query fingerprint khi extension đã được cài đặt và bật. `EXPLAIN (ANALYZE, BUFFERS)` cho phép xem actual rows, loops và buffer activity của một truy vấn cụ thể.

### MySQL

Performance Schema statement events và statement digest có thể giúp thống kê thời gian, số lần gọi, rows examined, rows sent và wait theo statement. `EXPLAIN ANALYZE` ở các phiên bản hỗ trợ cung cấp số liệu thực thi thực tế cho truy vấn.

### SQL Server

Query Store, actual execution plan, `SET STATISTICS IO, TIME ON` và các DMV có thể giúp liên hệ query với CPU, duration, logical reads, waits và plan changes.

Metric server-side có cách định nghĩa thời gian khác nhau giữa sản phẩm. Ví dụ elapsed time có thể bao gồm wait trong server; CPU time không bao gồm mọi thời gian chờ. Không so sánh trực tiếp các cột có tên giống nhau mà chưa hiểu cách đo.

## 12. Tương quan request, JDBC span và query fingerprint

Để ghép một request Java với truy vấn database, cần một định danh tương quan. Có thể dùng trace ID, span ID, request ID hoặc query fingerprint đã chuẩn hóa.

Một trace có thể gồm:

```text
HTTP request
  |
  +-- service method
       |
       +-- connection acquire
       |
       +-- JDBC execute
       |       +-- database query fingerprint
       |
       +-- ResultSet consume
       |
       +-- transaction commit
       |
       +-- connection release
```

Trace giúp nhận ra một endpoint gọi nhiều query tuần tự, query lặp N+1, connection pool wait hoặc result mapping tốn CPU.

Không đưa toàn bộ SQL có literal, giá trị tham số nhạy cảm, access token hoặc dữ liệu cá nhân vào trace/log. Dùng fingerprint hoặc câu SQL đã chuẩn hóa, giới hạn độ dài và áp dụng chính sách bảo mật telemetry.

## 13. Thống kê theo phân vị thay vì chỉ trung bình

Thời gian trung bình có thể che các request rất chậm. Ví dụ 99 request mất 10 ms và một request mất 1.000 ms có average gần 20 ms, nhưng người dùng gặp request chậm vẫn cảm nhận một giây.

Cần theo dõi:

- p50: mức latency điển hình ở trung vị.
- p90/p95: phần request chậm hơn phần lớn request.
- p99/p99.9: tail latency.
- Maximum: hữu ích cho điều tra nhưng nhạy với outlier.
- Throughput và error/timeout rate trong cùng cửa sổ.

Phân vị cần đủ số mẫu và cửa sổ thời gian phù hợp. Với metric có cardinality cao, tránh tạo một time series cho mỗi user ID hoặc order ID. Phân nhóm theo endpoint, query fingerprint, database, pool hoặc loại thao tác.

### Histogram và timer

Timer/histogram cho phép tổng hợp phân vị ở backend metrics. Nếu nhiều instance ứng dụng, histogram có thể được hợp nhất theo bucket; không nên lấy trung bình các p95 của từng instance để tạo p95 toàn hệ thống.

Đo acquisition, execute-call, result-consume và commit riêng theo cùng bộ tag cơ bản để so sánh. Theo dõi cả tổng operation để biết tổng thời gian có tăng hay không.

## 14. Phát hiện N+1 và truy vấn lặp từ JDBC metrics

Nếu một request có 1 lần lấy danh sách và N lần gọi cùng một query fingerprint, số execute tăng theo số hàng. JDBC instrumentation có thể phát hiện:

- Số query trên mỗi request.
- Số lần gọi trên từng fingerprint.
- Tổng thời gian execute theo fingerprint.
- Số hàng trả về mỗi lần.
- Số connection acquisition và thời gian giữ connection.

Ví dụ một request trả 100 đơn nhưng tạo 101 query: một query danh sách đơn và 100 query tìm khách hàng. Dù từng query chỉ mất 2 ms, tổng round trip và server overhead có thể đáng kể.

Các cách cải thiện có thể gồm JOIN, fetch join trong ORM, batch loading theo tập ID, DataLoader hoặc cache theo request. Cần kiểm tra cardinality và tránh tạo hàng nhân bản khi JOIN quan hệ một-nhiều.

Đừng chỉ đếm số query. Một request có 2 query nhưng query thứ hai scan 10 triệu hàng có thể tốn hơn 100 query point lookup. Kết hợp query count với execution time, rows examined, rows returned và plan.

## 15. ORM và lớp repository có thể che chi phí JDBC

JPA/Hibernate hoặc framework repository có thể phát sinh SQL ngoài câu lệnh được viết trực tiếp trong service:

- Lazy loading tạo query bổ sung khi getter được gọi.
- Flush có thể phát SQL tại thời điểm commit hoặc trước query.
- Batch fetch và JDBC batching phụ thuộc cấu hình.
- Entity hydration, dirty checking và persistence context có chi phí CPU/RAM.
- Transaction interceptor có thể mở/commit transaction bên ngoài method được đo.

Nếu chỉ đo một method repository, có thể bỏ sót thời điểm ORM flush hoặc mapping xảy ra ở lớp khác. Dùng JDBC proxy/instrumentation hoặc tracing datasource để quan sát statement thực tế, nhưng tránh đo trùng với instrumentation đã có sẵn.

Với Hibernate, statistics và SQL logging có thể giúp điều tra số query, entity fetch và batch; bật SQL log chi tiết trên production cần cân nhắc overhead và dữ liệu nhạy cảm.

## 16. Ví dụ đo bằng wrapper quanh DataSource

Trong hệ thống lớn, không nên viết timer thủ công cho từng câu SQL. Có thể dùng datasource proxy, JDBC instrumentation hoặc OpenTelemetry instrumentation để tạo span cho acquire, statement và result set.

Một wrapper tối giản có thể đo thời gian lấy connection:

```java
public final class TimedDataSource implements DataSource {
    private final DataSource delegate;
    private final Timer connectionAcquireTimer;

    public TimedDataSource(DataSource delegate, Timer timer) {
        this.delegate = delegate;
        this.connectionAcquireTimer = timer;
    }

    @Override
    public Connection getConnection() throws SQLException {
        long start = System.nanoTime();
        try {
            return delegate.getConnection();
        } finally {
            connectionAcquireTimer.record(
                System.nanoTime() - start,
                TimeUnit.NANOSECONDS
            );
        }
    }

    @Override
    public Connection getConnection(String user, String password)
            throws SQLException {
        long start = System.nanoTime();
        try {
            return delegate.getConnection(user, password);
        } finally {
            connectionAcquireTimer.record(
                System.nanoTime() - start,
                TimeUnit.NANOSECONDS
            );
        }
    }

    // Các phương thức DataSource còn lại delegate sang đối tượng gốc.
}
```

Đây là skeleton minh họa, chưa phải implementation đầy đủ của interface `DataSource`. Trong production cần delegate mọi phương thức, xử lý unwrap/wrapper, logging và exception theo contract. Timer ghi cả thời gian thành công lẫn lỗi; có thể cần metric riêng cho acquisition timeout.

Đo execute và ResultSet đầy đủ đòi hỏi proxy `Connection`, `Statement` và `ResultSet`, hoặc thư viện instrumentation đã được kiểm chứng. Không tự viết proxy phức tạp nếu framework hiện tại đã có công cụ tương thích.

## 17. Thiết kế metric và tránh overhead quan sát

Instrumentation cũng tiêu tốn CPU, allocation và có thể làm thay đổi latency mà nó đang đo. Một số nguyên tắc:

- Dùng `nanoTime()` và tránh format string trong đường nóng.
- Dùng histogram/timer có số tag hữu hạn.
- Không log từng hàng hoặc từng execute thành công ở mức INFO.
- Sampling trace cho workload lớn; giữ metric tổng hợp cho toàn bộ request.
- Đo overhead bằng benchmark có instrumentation bật và tắt.
- Ghi metric cả khi exception, timeout hoặc cancel.
- Tránh đồng bộ lock nặng trong callback metric.
- Không lưu raw SQL hoặc tham số nhạy cảm nếu không có chính sách bảo vệ.

Metric nên có tag như operation, query fingerprint, datasource, database role và outcome. Tránh tag có giá trị thay đổi theo từng request như customer ID, email hoặc order ID vì gây cardinality bùng nổ.

## 18. Benchmark để xác định từng giai đoạn

Để đo đúng, chuẩn bị workload và chạy các trường hợp có chủ đích:

1. **Pool nóng:** pool đã có connection idle; đo acquisition khi không có contention.
2. **Pool bão hòa:** tăng concurrency để quan sát pending threads và acquisition p95.
3. **Kết nối vật lý mới:** đo riêng thời gian tạo connection khi pool mở rộng hoặc khởi động lạnh.
4. **Kết quả nhỏ:** truy vấn trả vài hàng để tập trung execute-call và server work.
5. **Kết quả lớn:** truy vấn trả nhiều hàng để đo fetch, network và mapping.
6. **Mapping nặng:** dùng cùng dữ liệu nhưng tăng xử lý DTO/entity để nhận diện CPU phía ứng dụng.
7. **Transaction commit:** so sánh execute và commit latency trong cùng durability mode.
8. **Concurrency thực tế:** chạy theo mức đồng thời production để tìm pool, CPU, I/O và lock bottleneck.

Giữ ổn định dữ liệu, tham số, plan, cache state, driver version, pool size, network path và cấu hình database khi so sánh. Tách warm-up khỏi phép đo và chạy đủ mẫu để có phân vị đáng tin cậy.

## 19. Quy trình điều tra một API JDBC chậm

1. **Đo tổng request.** Xác định endpoint, p50/p95/p99, throughput và error rate.
2. **Tách connection acquisition.** Kiểm tra pool active/idle/pending, timeout và connection creation.
3. **Tách execute-call.** Gắn query fingerprint và ghi số lần gọi, loại statement, outcome.
4. **Đo ResultSet consumption.** Ghi rows read, thời gian fetch/consume và chi phí mapping.
5. **Đo commit và release.** Xác định thời gian log flush, transaction duration và trả connection.
6. **Đối chiếu server metrics.** Xem query stats, actual plan, rows examined, buffer reads, CPU và wait events.
7. **Đối chiếu network và app CPU.** Kiểm tra RTT, bytes, retransmission, allocation và GC nếu result processing chậm.
8. **Xác định nguyên nhân chính.** Pool starvation, server execution, I/O, network, result size hay mapping.
9. **Thử một thay đổi.** Tối ưu query/index, giảm rows/columns, fetch size, pool hoặc mapping theo bằng chứng.
10. **Đo lại toàn luồng.** Xác nhận cả endpoint latency và từng stage, không chỉ timer của câu SQL.

## 20. Ví dụ diễn giải một profile

Giả sử một API có profile p95 như sau:

| Giai đoạn | p95 trước tối ưu | Tỷ trọng gần đúng |
| --- | ---: | ---: |
| Lấy connection | 180 ms | 18% |
| Execute call | 90 ms | 9% |
| Đọc ResultSet và mapping | 620 ms | 62% |
| Commit và release | 30 ms | 3% |
| Xử lý khác trong request | 80 ms | 8% |

Profile cho thấy thời gian lớn nhất nằm ở đọc kết quả và mapping. Nếu chỉ tối ưu execution plan để giảm execute-call từ 90 ms xuống 45 ms, tổng request chỉ giảm một phần nhỏ.

Cần xem số hàng trả về, fetch size, bytes truyền, getter, object allocation và GC. Nếu API chỉ cần 20 hàng nhưng query trả 20.000 hàng rồi lọc ở Java, chuyển điều kiện lọc và LIMIT xuống SQL có thể giảm network, driver và mapping cost.

Trường hợp khác, acquisition p95 chiếm 300 ms và pending threads tăng, trong khi execute và result consume đều thấp. Khi đó cần điều tra pool sizing, connection leak, transaction giữ connection quá lâu hoặc database đang nhận quá nhiều session.

Không cộng p95 của các stage để suy ra p95 tổng một cách chính xác: các phân vị của từng stage có thể đến từ các request khác nhau. Muốn biết tổng p95, đo trực tiếp tổng operation hoặc phân tích trace từng request.

## 21. Những sai lầm thường gặp

- **Gọi execute-call time là database execution time.** Timer client có thể chứa network và driver buffering, hoặc chưa bao gồm fetch hết kết quả.
- **Không đo connection acquisition.** Pool wait có thể chiếm phần lớn latency.
- **Cho rằng `Connection.close()` đóng socket.** Với pool, close thường trả connection về pool.
- **Chỉ đo `executeQuery()` rồi bỏ ResultSet.** Dữ liệu lớn có thể mất phần lớn thời gian trong fetch và mapping.
- **Coi `setFetchSize()` là cam kết streaming.** Hành vi phụ thuộc driver và cấu hình.
- **Cộng timer cha và timer con.** Có thể đếm trùng thời gian.
- **Dùng `currentTimeMillis()` để đo duration.** Đồng hồ lịch có thể bị điều chỉnh; dùng `nanoTime()`.
- **Chỉ nhìn average.** Tail latency p95/p99 thường phản ánh pool wait và fetch chậm tốt hơn.
- **Tăng pool khi acquisition chậm mà không kiểm tra database.** Pool lớn hơn có thể làm server bão hòa.
- **Không đếm số query trên mỗi request.** N+1 có thể làm tổng round trip tăng dù từng query nhanh.
- **Ghi raw SQL và tham số nhạy cảm.** Telemetry có thể làm lộ dữ liệu hoặc tạo cardinality lớn.
- **So sánh hai lần đo khác điều kiện.** Cache, concurrency, driver, plan và dữ liệu khác nhau làm kết luận sai.

## 22. Danh sách kiểm tra trước khi tối ưu JDBC

- [ ] Có timer tổng operation dùng đồng hồ đơn điệu.
- [ ] Đã đo riêng thời gian `DataSource.getConnection()`.
- [ ] Đã phân biệt pool wait với tạo connection vật lý khi có thể.
- [ ] Đã đo execute-call quanh API JDBC và đặt tên metric đúng nghĩa.
- [ ] Đã đo thời gian duyệt ResultSet, số hàng và mapping.
- [ ] Đã đo commit cho transaction tường minh.
- [ ] Đã theo dõi active/idle/pending connection, timeout và usage duration.
- [ ] Đã kiểm tra fetch size và hành vi buffer/cursor của đúng driver.
- [ ] Đã liên kết request với query fingerprint hoặc trace ID an toàn.
- [ ] Đã đối chiếu server-side query stats và execution plan.
- [ ] Có p50/p95/p99, throughput và error rate theo cùng cửa sổ.
- [ ] Không cộng lặp các timer lồng nhau và không gọi client timer là server time.
- [ ] Đã đánh giá overhead và cardinality của instrumentation.
- [ ] Đã benchmark lại toàn luồng dưới concurrency đại diện.

## Kết luận

Đo JDBC hiệu quả cần tách thời gian lấy connection, gọi execute, đọc và ánh xạ ResultSet, commit và trả connection về pool. `executeQuery()` chỉ cho biết thời gian của lời gọi client; driver có thể buffer kết quả hoặc fetch theo batch nên thời gian đọc còn lại thay đổi theo cấu hình. Hãy dùng `System.nanoTime()`, ghi số hàng và query fingerprint, theo dõi pool active/idle/pending, rồi đối chiếu với execution plan, server-side query statistics, network và app CPU. Đo phân vị cùng throughput trên workload đại diện sẽ cho biết nên tối ưu pool, SQL, fetch strategy hay mapping, thay vì chỉ làm nhanh một đoạn code riêng lẻ.

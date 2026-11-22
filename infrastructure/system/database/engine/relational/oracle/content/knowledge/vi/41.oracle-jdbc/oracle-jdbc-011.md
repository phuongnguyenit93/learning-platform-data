# Fetch size, row prefetch và giảm số lần trao đổi mạng

## 1. Vì sao truy vấn JDBC cần fetch size?

Khi Java chạy một câu `SELECT` qua Oracle JDBC, database không nhất thiết gửi toàn bộ kết quả về ứng dụng trong một lần. Driver lấy kết quả theo từng nhóm dòng (fetch batch). Mỗi lần cần batch tiếp theo, driver có thể phải trao đổi thêm dữ liệu với database qua mạng.

Nếu truy vấn trả về nhiều dòng và mỗi batch chỉ có vài dòng, ứng dụng phát sinh nhiều lần fetch. Khi độ trễ mạng (round-trip time, RTT) đáng kể, thời gian chờ mạng có thể chiếm tỷ lệ lớn dù câu SQL và thao tác đọc dữ liệu ở database không quá tốn CPU.

**Fetch size** là gợi ý số dòng mà JDBC driver nên lấy trong một lần fetch. Với Oracle JDBC, khái niệm liên quan là **row prefetch**: driver yêu cầu Oracle trả trước một nhóm dòng để giảm số lần trao đổi mạng.

Fetch size tác động đến cách truyền kết quả từ database về client. Nó không thay đổi điều kiện SQL, không giới hạn tổng số dòng mà câu truy vấn có thể trả về và không thay thế phân trang. Một truy vấn trả 100.000 dòng vẫn có thể trả đủ 100.000 dòng dù fetch size là 100; driver chỉ chia việc nhận kết quả thành nhiều batch.

## 2. Fetch size và Oracle row prefetch

### 2.1. Fetch size theo JDBC

JDBC định nghĩa `Statement.setFetchSize(int)` và `ResultSet.setFetchSize(int)` để ứng dụng gợi ý số dòng cần lấy mỗi lần driver phải fetch thêm dữ liệu.

Ví dụ:

```java
try (PreparedStatement statement = connection.prepareStatement(
        "SELECT order_id, order_date, amount FROM orders WHERE status = ?")) {
    statement.setString(1, "SHIPPED");
    statement.setFetchSize(200);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long orderId = resultSet.getLong("order_id");
            Date orderDate = resultSet.getDate("order_date");
            BigDecimal amount = resultSet.getBigDecimal("amount");
            process(orderId, orderDate, amount);
        }
    }
}
```

Ở đây, `200` là số dòng driver được gợi ý lấy trong một batch. JDBC định nghĩa đây là hint; driver có thể áp dụng theo cách riêng và có các giới hạn tùy loại result set hoặc dữ liệu trả về.

Giá trị mặc định của `Statement.getFetchSize()` trong JDBC có thể là `0`, nghĩa là ứng dụng chưa đưa ra gợi ý riêng. Khi đó driver dùng mặc định của mình. Không nên hiểu `0` là Oracle không fetch dữ liệu hoặc fetch toàn bộ kết quả cùng lúc.

### 2.2. Oracle row prefetch

Oracle JDBC gọi cơ chế fetch theo batch là row prefetch. Trong Oracle JDBC, mặc định row prefetch thường là 10 dòng nếu không được cấu hình khác. Driver lấy batch đầu tiên khi thực thi truy vấn và tiếp tục lấy batch mới khi ứng dụng đọc vượt quá số dòng đã có sẵn.

JDBC `setFetchSize` là cách chuẩn, có tính portable giữa các JDBC driver. Oracle JDBC ánh xạ fetch size vào cơ chế row prefetch của driver. Oracle cũng cung cấp API riêng như `OracleStatement.setRowPrefetch(int)` và cấu hình mặc định ở cấp connection qua API Oracle tương ứng trong một số phiên bản driver.

Khi phát triển ứng dụng mới, nên ưu tiên JDBC `setFetchSize` để tránh phụ thuộc API riêng của Oracle nếu không cần tính năng đặc thù. Nếu ứng dụng dùng API row prefetch của Oracle, cần đọc tài liệu đúng phiên bản `ojdbc` và không cấu hình hai cơ chế với giá trị mâu thuẫn.

### 2.3. Cấu hình ở cấp statement hay connection?

Có thể cấu hình fetch size ở nhiều phạm vi:

| Phạm vi | Cách cấu hình | Khi phù hợp |
|---|---|---|
| Một câu SQL | `PreparedStatement.setFetchSize(n)` | Truy vấn cụ thể có lượng dữ liệu/độ rộng dòng riêng |
| Một ResultSet | `ResultSet.setFetchSize(n)` | Muốn thay đổi gợi ý cho quá trình fetch của result set đang mở, nếu driver hỗ trợ |
| Oracle statement API | `OracleStatement.setRowPrefetch(n)` | Ứng dụng chủ động dùng API đặc thù Oracle |
| Connection/driver default | Cấu hình row prefetch mặc định của Oracle connection/driver | Muốn thiết lập baseline chung cho các statement dùng connection đó |

Fetch size ở statement thường dễ kiểm soát hơn vì mỗi truy vấn có thể trả số cột và kích thước dòng khác nhau. Cấu hình mặc định toàn connection quá lớn có thể làm tăng bộ nhớ cho nhiều result set đồng thời, kể cả những truy vấn nhỏ không cần batch lớn.

## 3. Fetch batch giúp giảm network round-trip như thế nào?

### 3.1. Ví dụ số dòng và fetch size

Giả sử một truy vấn trả về 10.000 dòng và mỗi fetch lấy tối đa một batch theo fetch size. Số batch fetch lý thuyết xấp xỉ:

\[
Number\ of\ batches \approx \left\lceil \frac{N}{F} \right\rceil
\]

Trong đó:

- (N): tổng số dòng kết quả.
- (F): fetch size/row prefetch.

| Tổng số dòng | Fetch size | Số batch fetch xấp xỉ |
|---:|---:|---:|
| 10.000 | 10 | 1.000 |
| 10.000 | 100 | 100 |
| 10.000 | 200 | 50 |
| 10.000 | 500 | 20 |
| 10.000 | 1.000 | 10 |

Đây là phép ước lượng số batch, không phải số round-trip chính xác cho mọi câu SQL. Execute, parse, metadata, LOB access, protocol overhead và hành vi cụ thể của driver có thể tạo thêm trao đổi mạng. Trong nhiều trường hợp, batch đầu tiên được trả cùng phản hồi thực thi nên không nên cộng máy móc một round-trip cho mỗi batch.

### 3.2. Tác động của network latency

Giả sử RTT giữa ứng dụng và database là 8 ms. Nếu một truy vấn phải lấy 1.000 batch và mỗi batch cần một lần trao đổi mạng, riêng thời gian chờ mạng lý thuyết có thể lên tới khoảng:

\[
1.000 \times 8\ ms = 8.000\ ms
\]

Nếu tăng fetch size làm số batch còn 100, phần chờ RTT lý thuyết giảm còn khoảng 800 ms. Thời gian thực tế còn phụ thuộc thời gian database xử lý, truyền dữ liệu, deserialize, ứng dụng xử lý từng dòng và khả năng overlap giữa các công đoạn.

Điều này giải thích vì sao tăng fetch size có thể cải thiện rõ rệt truy vấn qua WAN hoặc mạng có RTT cao, trong khi tác động có thể nhỏ hơn trên mạng LAN độ trễ thấp.

### 3.3. Fetch size không làm SQL chạy nhanh hơn ở database

Fetch size chủ yếu giảm số lần trao đổi để chuyển kết quả. Nó không tự cải thiện:

- Access path hoặc index được optimizer chọn.
- Join order và join method.
- Số block database phải đọc.
- Predicate hoặc cardinality estimate.
- Thời gian tính toán của biểu thức SQL.

Nếu SQL đang full scan hàng tỷ dòng trong khi chỉ cần một phần nhỏ, tăng fetch size không thay thế việc tối ưu SQL. Hãy phân biệt thời gian database thực thi với thời gian client chờ fetch và xử lý kết quả.

## 4. Chọn fetch size phù hợp

### 4.1. Không có một con số tối ưu cho mọi truy vấn

Fetch size càng lớn thì số batch và round-trip thường càng ít, nhưng driver phải giữ nhiều dữ liệu hơn trong bộ nhớ cho mỗi batch. Một batch 500 dòng với ba cột số ngắn khác hoàn toàn 500 dòng có nhiều cột `VARCHAR2` lớn, `RAW` hoặc dữ liệu LOB.

Các yếu tố ảnh hưởng đến lựa chọn:

- RTT giữa JVM và database.
- Tổng số dòng dự kiến và tốc độ ứng dụng đọc result set.
- Số cột được chọn và kích thước trung bình của mỗi dòng.
- Số result set mở đồng thời và số request concurrency.
- Heap memory của JVM và mức allocation/GC.
- Kiểu dữ liệu, đặc biệt LOB và kiểu dữ liệu streaming.
- Driver version, statement type và scrollability.

### 4.2. Bắt đầu bằng một giá trị vừa phải

Có thể thử các mức như 50, 100, 200, 500 và 1.000 trên workload đại diện. Đây là các điểm thử nghiệm, không phải giá trị khuyến nghị cố định. So sánh throughput, p95/p99 latency, số lần fetch/round-trip, heap usage và GC.

Ví dụ:

```java
int[] fetchSizes = {50, 100, 200, 500, 1000};

for (int fetchSize : fetchSizes) {
    try (PreparedStatement statement = connection.prepareStatement(SQL)) {
        statement.setFetchSize(fetchSize);
        // Execute and consume the complete ResultSet.
    }
}
```

Khi benchmark, cần chạy cùng dữ liệu, cùng bind values, cùng mức concurrency và cùng cách tiêu thụ kết quả. Không chỉ đo thời gian `executeQuery()`: nhiều driver trả về batch đầu ở giai đoạn execute, còn phần lớn dữ liệu được lấy trong vòng lặp `ResultSet.next()`.

### 4.3. Ước lượng bộ nhớ batch

Ước lượng thô lượng dữ liệu một batch:

\[
Batch\ memory \approx F \times Average\ row\ size
\]

Ví dụ, nếu một dòng sau khi chuyển đổi và lưu trong driver/application chiếm trung bình 2 KB, fetch size 500 tương đương khoảng 1 MB dữ liệu thô cho một batch. Bộ nhớ thực tế có thể lớn hơn do object overhead, encoding, buffer của driver và dữ liệu tạm.

Nếu có 40 result set đồng thời với fetch size 500, tổng dữ liệu/buffer có thể tăng đáng kể. Do đó, phải xem concurrency chứ không chỉ một query đơn lẻ.

### 4.4. Truy vấn trả ít dòng

Nếu truy vấn thường chỉ trả 5–20 dòng, tăng fetch size lên 500 có thể không đem lại lợi ích. Batch đầu có thể đã chứa toàn bộ kết quả, và driver có thể cấp buffer lớn hơn cần thiết. Dùng fetch size theo đặc điểm query thay vì đặt một giá trị cực lớn toàn ứng dụng.

## 5. Cấu hình trong Oracle JDBC

### 5.1. Dùng JDBC setFetchSize

Đây là cách khuyến nghị chung:

```java
String sql = """
    SELECT order_id, customer_id, order_date, amount
    FROM orders
    WHERE order_date >= ?
    ORDER BY order_date, order_id
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setDate(1, Date.valueOf("2026-01-01"));
    statement.setFetchSize(200);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long orderId = resultSet.getLong(1);
            long customerId = resultSet.getLong(2);
            LocalDate orderDate = resultSet.getDate(3).toLocalDate();
            BigDecimal amount = resultSet.getBigDecimal(4);

            processOrder(orderId, customerId, orderDate, amount);
        }
    }
}
```

Đặt fetch size trước `executeQuery()` giúp cấu hình được áp dụng từ đầu cho result set. `try-with-resources` đóng result set, statement và connection đúng vòng đời. Trong ứng dụng dùng connection pool, `close()` thường trả connection về pool thay vì đóng physical connection.

### 5.2. Đặt fetch size trên ResultSet

JDBC cũng cho phép:

```java
try (PreparedStatement statement = connection.prepareStatement(SQL);
     ResultSet resultSet = statement.executeQuery()) {

    resultSet.setFetchSize(300);

    while (resultSet.next()) {
        process(resultSet);
    }
}
```

Việc thay đổi fetch size sau khi result set đã được tạo có thể chỉ ảnh hưởng các lần fetch tiếp theo và phụ thuộc driver. Để kết quả dễ dự đoán, nên cấu hình trên statement trước khi execute. Nếu cần thay đổi giữa chừng, hãy kiểm tra hành vi của phiên bản Oracle JDBC đang dùng.

### 5.3. Oracle-specific row prefetch API

Oracle JDBC cung cấp API đặc thù để thiết lập row prefetch, ví dụ:

```java
import oracle.jdbc.OracleStatement;

try (PreparedStatement statement = connection.prepareStatement(SQL)) {
    OracleStatement oracleStatement = statement.unwrap(OracleStatement.class);
    oracleStatement.setRowPrefetch(200);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            process(resultSet);
        }
    }
}
```

`unwrap` là cách JDBC chuẩn để lấy interface vendor-specific nếu driver hỗ trợ. API và class cần được đối chiếu với đúng phiên bản `ojdbc`; trong code portable, ưu tiên `Statement.setFetchSize`.

Không nên gọi cả `setFetchSize(100)` và `setRowPrefetch(500)` rồi giả định giá trị nào sẽ có hiệu lực. Oracle JDBC có quan hệ ánh xạ giữa JDBC fetch size và row prefetch; quy tắc ưu tiên có thể phụ thuộc thứ tự gọi và driver version. Chọn một API, cấu hình một giá trị rõ ràng và kiểm chứng bằng đo đạc.

### 5.4. Cấu hình mặc định ở cấp connection/driver

Oracle JDBC có cơ chế đặt row prefetch mặc định cho connection/driver. Cách cấu hình cụ thể phụ thuộc version, ví dụ API Oracle connection có thể cung cấp `setDefaultRowPrefetch(int)` hoặc connection property tương ứng.

Chỉ đặt default toàn connection khi phần lớn truy vấn trong workload có đặc điểm gần nhau. Nếu ứng dụng có cả query nhỏ, query lớn và query chứa LOB, hãy để từng DAO/repository đặt fetch size riêng cho truy vấn cần tối ưu.

Tránh sao chép property name từ ví dụ của driver cũ sang `ojdbc` mới mà chưa kiểm tra tài liệu. Oracle có thể thay đổi tên property/API hoặc hành vi theo phiên bản.

## 6. Quan hệ giữa fetch size, pagination và streaming

### 6.1. Fetch size không phải pagination

Fetch size quy định số dòng driver lấy trong một batch; pagination giới hạn hoặc chia tập kết quả ở cấp SQL/ứng dụng.

Ví dụ pagination bằng `OFFSET/FETCH`:

```sql
SELECT order_id, order_date, amount
FROM orders
ORDER BY order_date, order_id
OFFSET :offset ROWS FETCH NEXT :page_size ROWS ONLY;
```

Fetch size 200 với `page_size=50` vẫn chỉ có tối đa 50 dòng trong page. Ngược lại, fetch size 200 với câu SQL không giới hạn vẫn có thể đọc toàn bộ hàng triệu dòng qua nhiều batch.

Pagination hữu ích khi cần giới hạn dữ liệu mỗi request, hỗ trợ UI hoặc tránh giữ một result set rất dài. Fetch size hữu ích khi cần stream một result set lớn mà không muốn mỗi lần chỉ lấy một vài dòng qua mạng.

### 6.2. Keyset pagination cho dữ liệu lớn

Với trang sâu, `OFFSET` lớn có thể khiến database phải bỏ qua nhiều dòng trước khi trả page. Keyset pagination dùng khóa sắp xếp cuối cùng của trang trước để lấy trang tiếp theo:

```sql
SELECT order_id, order_date, amount
FROM orders
WHERE (order_date, order_id) > (:last_order_date, :last_order_id)
ORDER BY order_date, order_id
FETCH FIRST :page_size ROWS ONLY;
```

Ví dụ dùng row-value comparison cần kiểm tra hỗ trợ cú pháp và semantics theo Oracle release; có thể viết điều kiện tương đương bằng các predicate `OR` nếu cần. Khóa sắp xếp phải xác định thứ tự ổn định, thường có thêm primary key làm tie-break.

### 6.3. Streaming result set

Để xử lý kết quả lớn, nên đọc từng dòng rồi xử lý/ghi ra đích thay vì đưa toàn bộ kết quả vào một `List`:

```java
try (PreparedStatement statement = connection.prepareStatement(SQL)) {
    statement.setFetchSize(500);

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            exportRow(rs);
        }
    }
}
```

Fetch size giới hạn số dòng driver lấy theo batch, nhưng ứng dụng vẫn có thể làm cạn heap nếu `exportRow` giữ mọi object trong bộ nhớ. Cần xử lý từng dòng và giải phóng tham chiếu khi không còn dùng.

Một ResultSet đang mở thường giữ statement và connection cho tới khi hoàn tất/đóng. Không nên stream trong khi thực hiện công việc ngoài database kéo dài, vì connection bị giữ lâu và làm cạn pool. Nếu phải stream dữ liệu rất lâu, cân nhắc chia page hoặc ghi ra staging file/batch với transaction boundary phù hợp.

## 7. Các trường hợp đặc biệt: LOB, LONG và scrollable ResultSet

### 7.1. LOB và kiểu dữ liệu streaming

Các cột `BLOB`, `CLOB`, `NCLOB`, `LONG` hoặc `LONG RAW` có thể được driver xử lý theo cơ chế streaming hoặc locator, khác với cột số/văn bản ngắn. Oracle JDBC có các giới hạn/điều chỉnh row prefetch cho một số kiểu dữ liệu này; trong một số trường hợp driver giảm prefetch xuống 1 để xử lý an toàn.

Nếu query chứa LOB, không giả định fetch size 500 sẽ luôn tạo batch 500 dòng giống query chỉ có NUMBER/VARCHAR2. Việc đọc nội dung LOB còn có thể phát sinh thêm network round-trip tùy kích thước và cách đọc stream.

Với LOB lớn:

- Chỉ chọn LOB khi thực sự cần; tránh `SELECT *` nếu không dùng nội dung LOB.
- Đọc LOB theo stream/chunk thay vì materialize toàn bộ vào byte array hoặc String lớn.
- Đóng stream/LOB locator và result set đúng cách.
- Đo riêng query lấy metadata và bước tải nội dung LOB.
- Kiểm tra tài liệu Oracle JDBC theo driver version để biết giới hạn prefetch cụ thể.

### 7.2. Scrollable ResultSet

Scrollable result set cho phép di chuyển con trỏ tới trước/sau hoặc vị trí tùy ý, khác với forward-only result set thường dùng để đọc tuần tự. Scrollability có thể làm tăng bộ nhớ/cache và ảnh hưởng cách driver fetch.

Nếu ứng dụng chỉ duyệt một chiều:

```java
connection.prepareStatement(
    SQL,
    ResultSet.TYPE_FORWARD_ONLY,
    ResultSet.CONCUR_READ_ONLY
);
```

Forward-only/read-only thường phù hợp với export và batch processing. Chỉ dùng scrollable result set khi nghiệp vụ thực sự cần di chuyển con trỏ.

### 7.3. ResultSet holdability

Holdability xác định ResultSet còn mở hay bị đóng khi transaction commit. Đây là thuộc tính khác với fetch size. Không dùng holdability để tối ưu network fetch; chọn lifecycle phù hợp để tránh giữ cursor/connection lâu hơn cần thiết.

## 8. Fetch size và các yếu tố JDBC liên quan

### 8.1. Fetch size không phải setMaxRows

`Statement.setMaxRows(n)` giới hạn số dòng tối đa mà ResultSet trả về theo JDBC. `setFetchSize(n)` chỉ là gợi ý batch fetch. Hai API có mục đích khác nhau:

```java
statement.setMaxRows(1000);   // giới hạn tổng số dòng nhìn thấy
statement.setFetchSize(200);  // gợi ý lấy mỗi batch khoảng 200 dòng
```

Nếu đặt `maxRows=1000`, ứng dụng không đọc được dòng thứ 1001 từ ResultSet, dù database có nhiều dòng thỏa điều kiện. Nếu chỉ đặt fetch size 200, ứng dụng vẫn có thể đọc mọi dòng kết quả.

### 8.2. Fetch size không phải batch update size

`setFetchSize` áp dụng cho việc đọc ResultSet. Batch update dùng `addBatch()` và `executeBatch()` để gom DML; đây là cơ chế khác, không điều khiển bằng fetch size.

```java
try (PreparedStatement statement = connection.prepareStatement(
        "INSERT INTO audit_log(id, message) VALUES (?, ?)")) {
    for (AuditRecord record : records) {
        statement.setLong(1, record.id());
        statement.setString(2, record.message());
        statement.addBatch();
    }
    statement.executeBatch();
}
```

Batch update có thể giảm round-trip DML, còn fetch size giảm round-trip khi lấy kết quả query. Không nhầm hai cơ chế dù cả hai đều chia dữ liệu thành batch.

### 8.3. Fetch direction

`Statement.setFetchDirection()` là một hint khác với fetch size. Ví dụ `FETCH_FORWARD` mô tả hướng ứng dụng dự định đọc result set. Nó không đặt số dòng trong một batch và không thay thế `setFetchSize`.

## 9. Đo lường hiệu quả

### 9.1. Đo toàn bộ quá trình tiêu thụ ResultSet

Không chỉ đo thời gian `executeQuery()`. Hãy đo từ trước execute đến khi đọc hết result set:

```java
long start = System.nanoTime();
long rows = 0;

try (PreparedStatement statement = connection.prepareStatement(SQL)) {
    statement.setFetchSize(fetchSize);

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            consume(rs);
            rows++;
        }
    }
}

long elapsedNanos = System.nanoTime() - start;
double elapsedMillis = elapsedNanos / 1_000_000.0;
System.out.printf("fetchSize=%d rows=%d elapsed=%.2f ms%n",
        fetchSize, rows, elapsedMillis);
```

Đảm bảo `consume(rs)` làm công việc tương đương giữa các lần benchmark. Nếu một lần benchmark chỉ gọi `next()` còn lần khác parse JSON/ghi file, kết quả không thể so sánh.

### 9.2. Các chỉ số cần quan sát

- Thời gian tổng từ execute tới dòng cuối cùng.
- Thời gian execute và thời gian fetch/consume riêng nếu instrumentation cho phép.
- Số dòng nhận và số batch/fetch round-trip theo driver metrics hoặc tracing.
- Throughput (rows/sec) và latency p50/p95/p99.
- Heap usage, allocation rate, GC pause và peak memory.
- Số connection đang active, thời gian giữ connection và pool wait time.
- Network bytes/packets và RTT khi có công cụ đo mạng.
- Database CPU, logical reads, physical reads và wait events để xác định bottleneck có nằm ở DB hay không.

### 9.3. Thiết kế benchmark công bằng

1. Dùng cùng SQL, bind values và dữ liệu.
2. Giữ cùng fetch direction, result set type và cách xử lý dòng.
3. Chạy nhiều lần để tách ảnh hưởng cache/warm-up.
4. Thử nhiều fetch size, từ nhỏ đến lớn.
5. Chạy cả một client và mức concurrency gần production.
6. Ghi nhận heap/GC và latency, không chỉ thời gian trung bình.
7. Thử riêng query có LOB và query có dòng rộng.
8. Chọn giá trị cho workload đại diện, rồi theo dõi sau triển khai.

Nếu tăng fetch size giảm round-trip nhưng làm heap/GC tăng mạnh hoặc giảm concurrency, đó có thể không phải lựa chọn tốt. Mục tiêu là tối ưu throughput/latency tổng thể dưới giới hạn tài nguyên.

## 10. Các lỗi cấu hình thường gặp

### 10.1. Đặt fetch size quá lớn cho mọi query

Một giá trị rất lớn có thể làm tăng buffer memory, đặc biệt khi nhiều query chạy đồng thời hoặc mỗi dòng có dữ liệu rộng. Dùng giá trị theo query hoặc default vừa phải, rồi benchmark.

### 10.2. Tưởng fetch size giới hạn tổng kết quả

Ứng dụng đặt fetch size 100 nhưng vẫn đọc 1 triệu dòng, vì 100 là số dòng mỗi batch. Nếu cần giới hạn tổng dữ liệu, dùng SQL predicate, pagination hoặc `setMaxRows` theo đúng mục đích.

### 10.3. Đo mỗi executeQuery

Nếu driver trả batch đầu cùng lúc execute, đo mỗi `executeQuery()` có thể bỏ qua phần lớn thời gian fetch. Hãy đo đến khi vòng lặp `ResultSet.next()` hoàn tất.

### 10.4. Ứng dụng giữ toàn bộ dữ liệu trong List

Tăng fetch size không ngăn ứng dụng tích lũy tất cả object vào heap. Với kết quả lớn, xử lý từng dòng hoặc từng page và ghi ra đích dần dần.

### 10.5. Kết quả LOB không cải thiện như dự kiến

Driver có thể thay đổi row prefetch khi query chứa LOB/kiểu streaming. Hơn nữa, đọc nội dung LOB có thể cần các lần trao đổi riêng. Đo query có LOB riêng và kiểm tra API/driver version.

### 10.6. Cấu hình fetch size sau khi statement đã chạy

Đặt fetch size trước khi execute giúp tránh phụ thuộc hành vi thay đổi fetch size của driver khi ResultSet đã mở. Nếu đổi trên ResultSet, kiểm tra nó ảnh hưởng từ lần fetch tiếp theo hay không theo driver đang dùng.

### 10.7. Nhầm fetch size với array fetch trong API khác

OCI, ODP.NET, PL/SQL bulk collect và Oracle JDBC có các thuật ngữ/buffer tương tự nhưng API và semantics khác nhau. Không sao chép giá trị hoặc công thức từ driver khác sang JDBC nếu chưa kiểm tra tài liệu tương ứng.

## 11. Quy trình áp dụng trong ứng dụng Java

1. Xác định query trả nhiều dòng và có dấu hiệu chờ network fetch.
2. Đo thời gian từ execute đến khi tiêu thụ xong ResultSet, cùng RTT và số dòng thực tế.
3. Xác định kiểu dữ liệu và kích thước dòng; lưu ý LOB, LONG và result set scrollable.
4. Đặt `PreparedStatement.setFetchSize()` trước `executeQuery()` cho query đó.
5. Thử nhiều giá trị hợp lý, chẳng hạn 50, 100, 200, 500 và 1.000.
6. Đo round-trip/batch, throughput, p95/p99 latency, heap, GC và connection hold time.
7. Giữ forward-only/read-only nếu ứng dụng chỉ cần đọc tuần tự.
8. Không giữ connection trong khi xử lý ngoài database lâu; đóng ResultSet/Statement và trả connection về pool đúng lúc.
9. Nếu tổng kết quả quá lớn, dùng pagination/keyset pagination hoặc streaming; không kỳ vọng fetch size giới hạn tổng số dòng.
10. Ghi lại fetch size theo query và theo dõi sau triển khai khi tải, driver hoặc network thay đổi.

## 12. Nguyên tắc cần ghi nhớ

- JDBC fetch size là hint số dòng cho mỗi lần lấy batch; Oracle JDBC triển khai qua row prefetch.
- Oracle JDBC thường có row prefetch mặc định 10 dòng khi không cấu hình khác; kiểm tra đúng driver version.
- Tăng fetch size thường giảm số fetch round-trip nhưng tăng lượng dữ liệu/buffer giữ trong client.
- Fetch size không thay đổi SQL, không giới hạn tổng kết quả và không thay thế pagination.
- Đặt fetch size trên statement trước execute để hành vi rõ ràng; dùng JDBC API chuẩn nếu không cần Oracle-specific API.
- Query có LOB/LONG/streaming data có thể có quy tắc prefetch riêng và thêm round-trip khi đọc nội dung.
- Đo toàn bộ vòng đời đọc ResultSet, không chỉ thời gian `executeQuery()`.
- Cần benchmark dưới concurrency thực tế và quan sát heap, GC, network, DB waits và connection pool.
- Với kết quả rất lớn, xử lý từng dòng hoặc từng page; đừng giữ toàn bộ kết quả trong heap.

## Tài liệu Oracle tham khảo

- [Oracle Database 19c JDBC Developer's Guide — Row Prefetching](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/performance-extensions.html)
- [Oracle Database 19c JDBC Developer's Guide — Performance Extensions](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/)
- [Oracle Database 19c JDBC Java API Reference — OracleStatement](https://docs.oracle.com/en/database/oracle/oracle-database/19/jajdb/)
- [Java SE API — Statement.setFetchSize](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Statement.html#setFetchSize(int))
- [Java SE API — ResultSet.setFetchSize](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/ResultSet.html#setFetchSize(int))

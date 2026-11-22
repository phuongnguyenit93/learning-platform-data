# Kiểm thử timeout, pool cạn, kết nối đứt và kết quả commit chưa rõ

Ứng dụng Java kết nối MySQL qua JDBC hoặc connection pool có thể gặp nhiều lỗi trông giống nhau: request chờ quá lâu, không lấy được connection, query bị timeout, socket bị ngắt hoặc client mất kết nối đúng lúc commit. Những tình huống này có nguyên nhân và cách xử lý khác nhau. Nếu gộp tất cả thành một lỗi “database timeout” rồi retry ngay, ứng dụng có thể tạo giao dịch trùng, giữ connection bị hỏng trong pool hoặc làm tải MySQL tăng thêm.

Một trường hợp đặc biệt khó là **ambiguous commit outcome**: client gửi `COMMIT`, MySQL có thể đã commit thành công nhưng phản hồi bị mất trên đường mạng. Client nhận exception và không biết giao dịch đã commit hay chưa. Gọi `rollback()` trên connection đã đứt không chứng minh giao dịch chưa được commit. Muốn xử lý đúng, ứng dụng cần phân loại timeout theo từng tầng, kiểm soát transaction và dùng idempotency key để có thể xác định hoặc thử lại thao tác an toàn.

Bài học này tập trung vào kiểm thử hệ thống Java/Spring Boot dùng MySQL và JDBC. Các ví dụ giả định bảng nghiệp vụ dùng InnoDB, có connection pool như HikariCP và MySQL 8.0. Tên property cụ thể cần đối chiếu với phiên bản driver, pool và framework đang triển khai.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt timeout khi lấy connection, connect timeout, query timeout, lock wait timeout và socket/network timeout.
- Nhận diện pool exhaustion, connection leak và connection stale.
- Kiểm thử lỗi kết nối ở các thời điểm trước DML, trong DML và quanh `COMMIT`.
- Giải thích vì sao mất phản hồi commit tạo ra kết quả chưa xác định đối với client.
- Thiết kế idempotency key, checkpoint và retry có giới hạn.
- Kiểm tra trạng thái dữ liệu sau lỗi bằng một connection mới tới nguồn dữ liệu có thẩm quyền.
- Thu thập metrics từ HikariCP, JDBC và MySQL để xác định nguyên nhân.
- Viết test fault-injection có thể tái hiện, không phụ thuộc vào timing ngẫu nhiên.

## 1. Phân biệt các tầng timeout

Một request đi qua nhiều tầng trước khi nhận kết quả từ MySQL. Mỗi tầng có timeout riêng; hết thời gian ở một tầng không có nghĩa các tầng còn lại tự động dừng.

```text
HTTP request / service deadline
             |
             v
       Connection pool
       chờ lấy connection
             |
             v
       TCP connect / TLS
             |
             v
       JDBC statement
       query timeout
             |
             v
       MySQL execution
       lock wait / execution
             |
             v
       Socket read/write
             |
             v
       COMMIT response
```

| Timeout | Tầng | Ví dụ cấu hình | Điều nó giới hạn |
|---|---|---|---|
| Pool acquisition timeout | Connection pool | Hikari `connectionTimeout` | Thời gian chờ một connection rảnh từ pool |
| Connect timeout | JDBC/network | Connector/J `connectTimeout` | Thời gian thiết lập kết nối TCP tới server |
| Query timeout | JDBC statement | `Statement.setQueryTimeout()` | Thời gian driver cho phép một statement thực thi trước khi yêu cầu hủy |
| Transaction timeout | Framework/transaction manager | Spring `@Transactional(timeout=...)` | Giới hạn thời gian transaction theo khả năng của transaction manager |
| Lock wait timeout | InnoDB | `innodb_lock_wait_timeout` | Thời gian chờ row lock của InnoDB |
| Socket/network timeout | JDBC socket | Connector/J `socketTimeout` | Thời gian chờ dữ liệu phản hồi trên socket trước khi driver báo lỗi |
| Idle session timeout | MySQL server | `wait_timeout` | Thời gian session không tương tác bị server đóng do idle |
| Network packet timeout | MySQL server | `net_read_timeout`, `net_write_timeout` | Thời gian server chờ đọc/ghi một phần dữ liệu qua kết nối |

Không đặt tất cả timeout bằng cùng một số. Ví dụ, pool acquisition timeout thường ngắn hơn request deadline; connect timeout phải phù hợp với mạng; socket timeout phải đủ dài cho truy vấn hợp lệ nhưng vẫn nằm trong giới hạn request; transaction timeout cần tính đến thời gian lấy connection và xử lý ứng dụng.

### 1.1. Timeout lấy connection từ pool

Nếu pool đã dùng hết connection và không có connection nào được trả về trước `connectionTimeout`, lời gọi `getConnection()` có thể thất bại. Khi đó, câu SQL chưa được gửi tới MySQL.

Nguyên nhân thường gặp:

- Một số request giữ connection quá lâu hoặc quên đóng connection.
- Transaction mở rộng qua thời gian gọi HTTP, xử lý file hoặc chờ dịch vụ khác.
- Query chậm, lock wait hoặc database quá tải khiến connection không được trả về.
- Pool quá nhỏ so với concurrency thực tế.
- Pool được cấu hình quá lớn so với khả năng chịu tải của MySQL, làm số query đồng thời tăng cao.

Pool cạn là triệu chứng, không tự chứng minh cần tăng `maximumPoolSize`. Trước tiên hãy xem active, idle, pending connection, thời gian giữ connection và truy vấn đang chạy.

### 1.2. Connect timeout và socket timeout

Với MySQL Connector/J, `connectTimeout` và `socketTimeout` được cấu hình theo milliseconds trong các phiên bản hiện hành. Ví dụ:

```text
jdbc:mysql://db.example:3306/app?connectTimeout=3000&socketTimeout=15000
```

`connectTimeout` áp dụng lúc thiết lập kết nối. `socketTimeout` ảnh hưởng việc chờ dữ liệu trên socket sau khi đã kết nối. Nếu `socketTimeout` hết hạn trong lúc query hoặc commit, driver có thể đóng connection vì không còn biết trạng thái trao đổi.

Không đặt socket timeout quá thấp để “bảo vệ” request. Một truy vấn hợp lệ có thể cần thời gian lâu hơn; timeout quá ngắn sẽ tạo lỗi giả, reconnect và retry làm tải hệ thống tăng thêm. Cần đặt theo SLO, phân bố latency thực tế và giới hạn ở tầng ứng dụng.

### 1.3. Query timeout không giống socket timeout

JDBC hỗ trợ:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT id, status FROM orders WHERE customer_id = ?")) {
    ps.setLong(1, customerId);
    ps.setQueryTimeout(5); // seconds
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Đọc kết quả.
        }
    }
}
```

`setQueryTimeout(5)` yêu cầu driver hủy statement nếu quá thời gian theo hợp đồng JDBC. Cách hủy phụ thuộc driver và server; nó không đảm bảo TCP socket bị đóng, cũng không tự động rollback toàn bộ transaction. Sau query timeout, ứng dụng phải xác định trạng thái transaction và rollback nếu cần trước khi tái sử dụng connection.

Trong MySQL, `max_execution_time` giới hạn thời gian thực thi một số câu `SELECT` chỉ đọc, tính bằng milliseconds; nó không phải timeout tổng quát cho mọi `INSERT`, `UPDATE`, `DELETE` hoặc transaction. Ví dụ:

```sql
SET SESSION max_execution_time = 5000;
```

Không dùng biến này thay cho JDBC query timeout hoặc transaction timeout. Với lock contention, xem `innodb_lock_wait_timeout`; với thời gian request, xem deadline ở tầng service/API.

### 1.4. Idle timeout và connection stale

MySQL có thể đóng session idle theo `wait_timeout`. Firewall, NAT, load balancer hoặc proxy cũng có thể loại kết nối idle trước khi pool biết điều đó. Connection vẫn nằm trong pool nhưng socket đã chết được gọi là stale connection.

HikariCP có các thuộc tính như `maxLifetime`, `keepaliveTime` và `validationTimeout`. Thông thường:

- Đặt `maxLifetime` ngắn hơn giới hạn tuổi kết nối của proxy hoặc hạ tầng mạng.
- Đặt `keepaliveTime` thấp hơn `maxLifetime` nếu cần kiểm tra các connection đang idle; Hikari chỉ chạy keepalive trên connection idle.
- Dùng cơ chế validation JDBC4 (`Connection.isValid`) nếu driver hỗ trợ; không thêm `connectionTestQuery` nếu không cần.
- Không giữ connection lâu hơn cần thiết trong code ứng dụng.

`wait_timeout` của MySQL và timeout của pool phục vụ mục đích khác nhau. Pool nên loại connection trước khi hạ tầng đóng nó, hoặc phát hiện connection không còn hợp lệ trước khi giao cho request.

## 2. Cấu hình và quan sát HikariCP

Ví dụ cấu hình Spring Boot:

```yaml
spring:
  datasource:
    url: jdbc:mysql://db.example:3306/app?connectTimeout=3000&socketTimeout=20000
    username: app_user
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 3000
      validation-timeout: 1000
      max-lifetime: 1500000
      keepalive-time: 300000
      leak-detection-threshold: 30000
```

Các con số chỉ để minh họa, không phải cấu hình khuyến nghị chung. `maxLifetime` và `keepaliveTime` phải phù hợp với giới hạn của MySQL, proxy và hạ tầng. `leak-detection-threshold` chỉ ghi cảnh báo về connection được giữ quá lâu; nó không tự giải phóng connection và không thay thế việc đóng resource đúng cách.

### 2.1. Metrics cần theo dõi

HikariCP có thể cung cấp các số liệu như:

- `active`: số connection đang được ứng dụng mượn.
- `idle`: số connection rảnh.
- `pending`: số thread đang chờ connection.
- `total`: tổng connection hiện tại.
- Timeout count và thời gian acquire/usage nếu metrics integration được bật.

Diễn giải một số dấu hiệu:

| Dấu hiệu | Khả năng cần điều tra |
|---|---|
| `active` luôn bằng `maximumPoolSize`, `pending` tăng | Pool cạn do query chậm, transaction dài, leak hoặc concurrency quá cao |
| `idle=0`, `active` cao nhưng MySQL ít query | Connection bị giữ trong ứng dụng, chờ lock ngoài DB hoặc chờ công việc khác |
| Timeout xuất hiện sau thời gian idle dài | Connection stale do `wait_timeout` hoặc thiết bị mạng |
| Active tăng dần và không giảm | Leak, code không đóng resource hoặc transaction không kết thúc |
| Active cao cùng `Threads_running` và latency cao | Database có thể đang quá tải hoặc có lock contention |

Không tăng pool size chỉ dựa trên pending count. Tăng số connection có thể làm MySQL nhận nhiều query đồng thời hơn và kéo dài thời gian xử lý của tất cả request.

### 2.2. Metrics phía MySQL

Kiểm tra connection và tải:

```sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
  'Threads_connected',
  'Threads_running',
  'Max_used_connections',
  'Connections',
  'Aborted_connects',
  'Aborted_clients'
);

SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
  'max_connections',
  'wait_timeout',
  'net_read_timeout',
  'net_write_timeout',
  'innodb_lock_wait_timeout',
  'max_execution_time'
);
```

Kiểm tra transaction và session đang chạy:

```sql
SELECT *
FROM information_schema.innodb_trx
ORDER BY trx_started;

SHOW FULL PROCESSLIST;
```

`Threads_connected` cao không nhất thiết đồng nghĩa pool cạn; có thể là nhiều pool, nhiều service hoặc session idle. Kết hợp metrics của ứng dụng với `Threads_running`, transaction age và query latency để xác định điểm nghẽn.

## 3. Thiết kế test timeout và pool exhaustion

Test phải có mục tiêu cụ thể và có cách phục hồi. Không tạo vòng lặp mở connection vô hạn trên database dùng chung. Dùng MySQL test instance/container và pool nhỏ để tạo tình huống có thể tái hiện.

### 3.1. Kiểm thử pool cạn có kiểm soát

Ví dụ cấu hình test với pool chỉ có một connection:

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 1
      minimum-idle: 1
      connection-timeout: 500
```

Test có thể mượn connection đầu tiên và giữ nó, sau đó yêu cầu connection thứ hai. Yêu cầu thứ hai phải timeout gần với giới hạn đã cấu hình. Sau khi trả connection đầu tiên, yêu cầu tiếp theo phải lấy được connection.

Kết quả cần xác minh:

1. Lần acquire thứ hai thất bại trong giới hạn thời gian dự kiến.
2. Không có SQL nào được gửi từ request không lấy được connection.
3. Khi connection đầu được đóng/trả pool, pending giảm và acquire mới thành công.
4. Pool không còn connection bị giữ sau khi test kết thúc.

Đây là test cho pool acquisition, không phải test MySQL query timeout. Không dùng `Thread.sleep()` dài làm đồng bộ chính; dùng latch/barrier để bảo đảm connection đầu tiên đang được giữ trước khi yêu cầu thứ hai.

### 3.2. Kiểm thử connection leak

Tạo một code path cố ý không đóng connection trong test fixture hoặc mock service, sau đó quan sát leak warning và pool metrics. Không đưa lỗi leak cố ý vào code production. Sau test, bảo đảm resource được giải phóng và pool được đóng.

Trong code thật, ưu tiên try-with-resources:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(
         "SELECT COUNT(*) FROM orders WHERE status = ?")) {
    ps.setString(1, "PENDING");
    try (ResultSet rs = ps.executeQuery()) {
        rs.next();
        return rs.getLong(1);
    }
}
```

Với Spring Data JPA/JdbcTemplate, để framework quản lý connection; không tự lấy connection từ pool rồi giữ qua thời gian gọi HTTP, gửi email hoặc xử lý file.

### 3.3. Kiểm thử lock wait timeout

Dùng hai session tới cùng MySQL test instance:

```sql
-- Session A
START TRANSACTION;
UPDATE accounts SET balance = balance - 10 WHERE id = 1;
-- Giữ transaction mở để khóa hàng.
```

```sql
-- Session B
SET SESSION innodb_lock_wait_timeout = 2;
START TRANSACTION;
UPDATE accounts SET balance = balance + 10 WHERE id = 1;
```

Session B sẽ chờ row lock; nếu Session A chưa commit/rollback trong thời gian giới hạn, Session B nhận lỗi lock wait timeout. Sau lỗi, kiểm tra trạng thái transaction của Session B và rollback toàn transaction theo logic ứng dụng trước khi tái sử dụng connection.

Giải phóng Session A:

```sql
-- Session A
COMMIT;
```

Test cần xác minh không có cập nhật một phần ngoài dự kiến, transaction được kết thúc và connection trở về pool. Deadlock khác lock wait timeout: deadlock detector có thể chọn một transaction làm nạn nhân và rollback transaction đó trước khi `innodb_lock_wait_timeout` hết.

## 4. Kiểm thử kết nối đứt

Kết nối có thể đứt ở nhiều thời điểm. Kết quả phụ thuộc request đã tới server hay chưa và MySQL đã xử lý đến bước nào.

| Thời điểm đứt | Điều client biết | Điều cần làm |
|---|---|---|
| Trước khi TCP connect thành công | Kết nối chưa được thiết lập | Retry connect có giới hạn nếu lỗi tạm thời |
| Sau connect nhưng trước khi gửi statement | Chưa có statement được gửi nếu xác định được chắc chắn | Loại connection lỗi; mở connection mới |
| Trong lúc gửi/thi hành DML | Server có thể chưa nhận, đang thực thi hoặc đã thực thi xong statement; client có thể mất phản hồi | Với InnoDB, statement có tính nguyên tử, nhưng transaction có thể vẫn chưa commit; xác minh theo khóa idempotency |
| Sau DML nhưng trước `COMMIT` | Transaction có thể còn mở trên server hoặc session đã đóng | Server sẽ rollback transaction chưa commit khi session kết thúc, nhưng client cần xác minh nếu trạng thái kết nối chưa rõ |
| Trong lúc gửi `COMMIT` hoặc chờ phản hồi | Commit có thể đã thành công nhưng ACK bị mất, hoặc commit chưa hoàn tất | Xem là kết quả chưa xác định; tra cứu bằng idempotency key trên primary có thẩm quyền |
| Sau khi nhận phản hồi commit thành công | Client đã nhận xác nhận commit từ server | Ghi nhận thành công; xử lý lỗi downstream riêng |

Khi connection mất, server thường phát hiện session đóng và rollback transaction InnoDB chưa commit. Tuy nhiên, nếu commit đã được xử lý trước khi server phát hiện socket mất, thay đổi vẫn có thể đã commit. Vì vậy, lỗi socket không tự trả lời được câu hỏi “giao dịch đã ghi hay chưa?”.

### 4.1. Fault injection

Để tái hiện lỗi mạng, có thể dùng proxy kiểm thử như Toxiproxy giữa ứng dụng và MySQL, hoặc firewall rule trong môi trường cô lập. Tạo các kịch bản:

- Chặn kết nối mới để kiểm tra connect timeout.
- Cắt kết nối idle để kiểm tra stale connection và validation của pool.
- Thêm latency hoặc giới hạn băng thông để kiểm tra socket/query timeout.
- Reset kết nối khi query đang chạy.
- Cắt đường truyền ngay sau khi server xử lý commit nhưng trước khi client nhận phản hồi.

Kịch bản cuối khó xác định chỉ bằng một thao tác ngắt mạng ngẫu nhiên. Để kiểm thử đúng ambiguous commit, cần một điểm đồng bộ có thể quan sát, ví dụ test proxy có thể trì hoãn/drop phản hồi server sau khi chuyển tiếp request commit, hoặc một test hook ở phía server/proxy xác nhận commit đã tới server trước khi chặn response.

Không chạy fault injection trên production hoặc mạng dùng chung. Mỗi test cần timeout tổng, cleanup proxy rule và phục hồi kết nối trong `finally` để các test tiếp theo không bị ảnh hưởng.

## 5. Ambiguous commit outcome

Giả sử ứng dụng thực hiện:

```java
connection.setAutoCommit(false);
insertPayment(connection, payment);
connection.commit();
```

MySQL có thể đã commit transaction nhưng phản hồi commit bị mất do mạng đứt. JDBC ném exception, nhưng client không có cách suy ra chỉ từ exception rằng server đã rollback hay đã commit. Gọi `connection.rollback()` sau khi socket đã hỏng thường không gửi được lệnh tới server và không thay đổi kết quả commit đã hoàn tất.

Đây là lý do retry một thao tác tài chính hoặc tạo đơn hàng chỉ dựa trên “client nhận lỗi” có thể tạo dữ liệu trùng. Cần thiết kế thao tác có định danh idempotent để lần gửi lại có thể xác định kết quả lần trước.

### 5.1. Phân biệt lỗi chắc chắn và kết quả chưa xác định

- Nếu lỗi xảy ra trước khi request được gửi tới server và ứng dụng có bằng chứng điều đó, thao tác chưa chạy; có thể thử lại.
- Nếu MySQL trả lỗi SQL rõ ràng cho statement và transaction vẫn kết nối, ứng dụng có thể xử lý theo loại lỗi rồi rollback hoặc sửa dữ liệu.
- Nếu mất kết nối khi statement hoặc commit đang được gửi/thực thi, kết quả có thể chưa xác định.
- Nếu đã nhận xác nhận commit thành công, transaction đã được server xác nhận commit; lỗi phát sinh sau đó ở HTTP hoặc message broker cần xử lý theo luồng downstream.

Không phân loại mọi `SQLTransientConnectionException`, `SQLRecoverableException` hoặc SQLState class `08` thành “chưa commit”. Các exception này báo vấn đề kết nối, không xác nhận trạng thái transaction ở server.

## 6. Idempotency key để xử lý kết quả chưa rõ

Một request nghiệp vụ có thể mang `request_id` duy nhất do client hoặc service tạo. Server lưu request ID cùng kết quả nghiệp vụ trong **cùng transaction**. Nếu client mất phản hồi rồi gửi lại cùng request ID, unique key ngăn thực hiện tác vụ lần thứ hai.

Ví dụ bảng lưu dấu vết request:

```sql
CREATE TABLE payment_requests (
  request_id VARCHAR(64) NOT NULL,
  payload_hash BINARY(32) NOT NULL,
  payment_id BIGINT UNSIGNED NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (request_id),
  UNIQUE KEY uk_payment_requests_payment (payment_id)
) ENGINE = InnoDB;
```

Bảng nghiệp vụ `payments` cũng cần khóa duy nhất phù hợp với yêu cầu. Ví dụ luồng xử lý:

```text
Nhận request_id và payload
          |
          v
START TRANSACTION
          |
          v
Tạo payment và request record
trong cùng transaction
          |
          v
COMMIT
          |
     +----+----+
     |         |
   ACK nhận   ACK mất
     |         |
   Trả kết quả Client chưa rõ
               |
               v
        Gửi lại cùng request_id
               |
               v
        Tìm payment_requests
               |
        +------+------+
        |             |
      Đã có         Chưa có
        |             |
  Kiểm tra hash   Thực hiện lại
  trả kết quả     theo idempotency
```

Thứ tự lưu phải được thực hiện trong một transaction InnoDB. Nếu payment đã commit nhưng request record không được lưu cùng transaction, cơ chế deduplication có thể không biết giao dịch đã xảy ra. Ngược lại, nếu request record commit mà payment không commit, kết quả cũng không nhất quán.

### 6.1. Kiểm tra payload để tránh dùng lại key sai

Một request ID chỉ được đại diện cho một payload nghiệp vụ. Khi nhận lại cùng key:

- Nếu `payload_hash` giống nhau, trả lại kết quả đã lưu.
- Nếu hash khác nhau, từ chối request vì client đã tái sử dụng key cho một thao tác khác.
- Nếu request đang được xử lý, unique constraint có thể khiến transaction cạnh tranh chờ transaction đầu commit/rollback; cần đặt timeout và xử lý duplicate theo logic.

Hash cần được tạo từ biểu diễn payload đã chuẩn hóa, không phụ thuộc thứ tự field hoặc format JSON ngẫu nhiên. Không dùng hash thay cho xác thực request hoặc kiểm tra quyền nghiệp vụ.

### 6.2. Ví dụ xử lý duplicate

Pseudo-code JDBC:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        long paymentId = insertPayment(connection, command);
        insertPaymentRequest(
            connection,
            command.requestId(),
            command.payloadHash(),
            paymentId
        );
        connection.commit();
        return loadPaymentResult(connection, paymentId);
    } catch (SQLException e) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            e.addSuppressed(rollbackError);
        }
        throw e;
    }
}
```

Đây là khung transaction cho lần thực hiện đầu. Khi nhận duplicate key hoặc lỗi kết nối chưa rõ quanh commit, xử lý bằng một connection mới tới primary có thẩm quyền: truy vấn `payment_requests` theo `request_id`, so sánh `payload_hash` và trả kết quả đã lưu nếu có. Nếu chưa thấy record, đừng vội kết luận transaction cũ đã rollback: server có thể vẫn đang xử lý hoặc chưa phát hiện session mất kết nối. Một cách đồng bộ là thử tạo lại cùng idempotency key trong transaction mới; unique index sẽ khiến lần thử chờ transaction trước commit/rollback. Nếu lần trước commit, thao tác mới nhận duplicate key; nếu lần trước rollback, lần thử có thể tạo record và tiếp tục. Cần đặt lock wait timeout và xử lý duplicate theo logic. Chỉ retry sau khi xác định đang thao tác trên primary có thẩm quyền.

Trong triển khai thật, cần phân biệt duplicate key ở bảng `payment_requests` với duplicate key ở bảng `payments`, bảo đảm thứ tự insert và unique constraint phù hợp. Pseudo-code trên không bao gồm đầy đủ nhánh duplicate/reconciliation.

### 6.3. Đọc từ primary có thẩm quyền

Sau lỗi commit chưa rõ, không nên truy vấn một replica bất đồng bộ rồi kết luận request chưa commit chỉ vì chưa thấy row. Replica có thể chưa apply giao dịch. Đọc trạng thái từ primary đang có quyền nhận ghi hoặc dùng cơ chế read-after-write/consistency phù hợp.

Nếu primary đã failover, cần xác định transaction có được truyền sang primary mới hay không. Với asynchronous replication, giao dịch đã commit trên primary cũ nhưng chưa replicate có thể bị mất khi failover. Idempotency record chỉ giúp xác định những gì còn tồn tại trên topology hiện tại; nó không tự khôi phục một commit bị mất khỏi mọi node.

## 7. Retry có giới hạn và đúng phạm vi

Retry phải dựa trên loại lỗi và tính idempotent của thao tác. Một chính sách tốt thường có:

- Số lần thử tối đa nhỏ và rõ ràng.
- Exponential backoff có jitter để nhiều client không retry đồng thời.
- Deadline tổng cho toàn request.
- Chỉ retry lỗi tạm thời đã phân loại; không retry lỗi dữ liệu, quyền hoặc cú pháp.
- Retry toàn transaction sau deadlock hoặc rollback được xác nhận, không chỉ chạy lại câu lệnh cuối.
- Dùng cùng idempotency key khi trạng thái commit chưa rõ.
- Ghi log attempt, request ID, SQLState, vendor code và thời gian chờ mà không ghi secret hoặc dữ liệu nhạy cảm.

Ví dụ logic backoff khái quát:

```text
delay = min(max_delay, base_delay * 2^attempt) + random_jitter
retry only if transient and request is idempotent
stop when attempts or request deadline is exhausted
```

Không retry vô hạn. Khi database đang quá tải, retry làm tăng số kết nối và query, khiến pool cạn nhanh hơn. Dùng circuit breaker hoặc load shedding nếu dịch vụ cần từ chối sớm trong thời gian database không khỏe.

### 7.1. Deadlock và lock wait timeout

Deadlock thường khiến InnoDB rollback một transaction được chọn làm victim. Ứng dụng có thể retry toàn bộ transaction nếu thao tác idempotent và lỗi được phân loại đúng. Lock wait timeout mặc định thường rollback statement đang chờ; transaction có thể vẫn còn mở. Hãy rollback toàn transaction ở tầng ứng dụng trước khi retry để tránh giữ lock từ những statement trước.

### 7.2. Socket timeout và lỗi commit

Nếu socket timeout xảy ra trong `commit()`, không coi đây là một lỗi retry thông thường. Ghi request ID, loại connection và thời điểm, sau đó mở connection mới để reconciliation theo idempotency key. Không dùng lại connection bị lỗi và không gửi một thao tác nghiệp vụ mới với request ID khác cho cùng hành động.

## 8. Spring transaction và timeout

Spring cung cấp transaction boundary ở tầng service:

```java
@Transactional(timeout = 10)
public PaymentResult createPayment(CreatePaymentCommand command) {
    // Ghi payment và idempotency record trong cùng transaction.
    return paymentRepository.create(command);
}
```

`@Transactional(timeout=10)` biểu đạt timeout transaction theo giây cho transaction manager. Việc timeout được áp dụng tới JDBC statement như thế nào phụ thuộc transaction manager, JDBC driver và cách truy cập dữ liệu. Nó không tự thay thế `connectTimeout`, `socketTimeout`, pool `connectionTimeout` hoặc deadline HTTP.

Không đặt một transaction bao quanh các thao tác chậm ngoài database như gọi HTTP, gửi email hoặc chờ người dùng. Giữ transaction ngắn giúp giảm thời gian giữ connection và lock.

Nếu cần publish event sau khi ghi database, cân nhắc transactional outbox: ghi business row và outbox row trong cùng transaction, sau đó worker gửi event và đánh dấu đã xử lý. Cách này tránh trường hợp database commit nhưng message publish thất bại hoặc ngược lại. Consumer vẫn cần idempotent vì message có thể được gửi lại.

## 9. Kiểm thử các kịch bản lỗi

Một test suite nên bao phủ cả pool, MySQL, network và trạng thái transaction.

| Kịch bản | Cách tạo trong môi trường test | Kết quả cần xác minh |
|---|---|---|
| Pool exhaustion | Pool size nhỏ; giữ connection bằng latch rồi yêu cầu thêm | Acquire timeout đúng giới hạn; SQL không được gửi; pool phục hồi khi trả connection |
| Connection leak | Cố ý giữ connection trong test fixture | Leak warning/metrics xuất hiện; cleanup đóng resource |
| Connect timeout | Chặn cổng MySQL hoặc trỏ tới endpoint không phản hồi | Lỗi xảy ra trong connect deadline; không để thread chờ vô hạn |
| Query timeout | Chạy truy vấn test có thời gian dài và đặt `setQueryTimeout` | Driver báo timeout; transaction được xử lý đúng; connection không bị tái sử dụng khi trạng thái không rõ |
| Lock wait timeout | Session A giữ row lock; Session B update cùng row với timeout ngắn | Session B nhận lock wait error; ứng dụng rollback transaction và không giữ lock |
| Idle stale connection | Đóng socket idle qua proxy hoặc đặt idle timeout test ngắn | Pool loại connection hỏng và cấp connection mới |
| Disconnect trong DML | Reset kết nối khi statement đang thực thi | Ứng dụng phân loại kết quả chưa rõ và reconciliation theo request ID |
| Disconnect quanh commit | Chuyển tiếp COMMIT tới server rồi drop response | Client không tạo duplicate; truy vấn idempotency record xác định kết quả |
| Failover sau commit | Mô phỏng primary lỗi sau commit trước khi replica nhận log | Kiểm tra RPO, GTID và giới hạn của asynchronous replication |

### 9.1. Kiểm thử ambiguous commit có đồng bộ

Một test đúng cần tạo được hai kết quả đối chứng:

**Trường hợp A — server đã commit, response bị mất:**

1. Client bắt đầu transaction, ghi payment và request record.
2. Proxy chuyển tiếp lệnh COMMIT tới MySQL.
3. Test xác nhận server đã xử lý commit, sau đó chặn/drop response về client.
4. Client nhận lỗi kết nối.
5. Client reconnect tới primary và truy vấn cùng request ID.
6. Test xác nhận chỉ có một payment và kết quả được trả lại từ request record.

**Trường hợp B — commit chưa tới server:**

1. Client bắt đầu transaction và ghi dữ liệu chưa commit.
2. Proxy chặn request COMMIT trước khi nó tới server hoặc ngắt session trước commit.
3. Client nhận lỗi.
4. Test chờ server đóng session và rollback transaction chưa commit.
5. Client retry với cùng request ID.
6. Test xác nhận chỉ có một payment sau lần thực hiện thành công.

Không dùng một test chỉ ngắt socket ngẫu nhiên rồi khẳng định đã kiểm thử ambiguous commit. Nếu không kiểm soát được điểm cắt, test có thể chỉ kiểm tra lỗi connect hoặc query.

### 9.2. Assertion sau lỗi

Sau mỗi kịch bản, xác minh:

- Số lượng bản ghi nghiệp vụ theo request ID.
- Số lượng idempotency record và payload hash.
- Số dư hoặc tổng tiền trước/sau nếu test nghiệp vụ tài chính.
- Không có transaction treo và connection bị giữ trong pool.
- Metrics active/idle/pending trở về trạng thái bình thường.
- Replica lag và GTID được xử lý theo yêu cầu test.
- Retry không tạo side effect lặp ở message broker hoặc hệ thống ngoài.

## 10. Chẩn đoán sự cố trong môi trường chạy thật

Khi nhận lỗi timeout hoặc connection reset, thu thập bằng chứng theo thứ tự:

1. **Tầng request:** request ID, deadline, endpoint, thời gian bắt đầu/kết thúc và số lần retry.
2. **Pool:** active/idle/pending/total, acquire latency, timeout count, leak warning.
3. **JDBC:** loại exception, SQLState, vendor code, operation đang chạy (`getConnection`, `execute`, `commit`) và driver version.
4. **MySQL:** `Threads_connected`, `Threads_running`, process list, transaction age, lock wait, error log.
5. **Network:** reset, retransmission, proxy idle timeout, DNS, firewall và latency giữa ứng dụng với DB.
6. **Transaction:** request có idempotency key không, commit đã được xác nhận chưa và dữ liệu có tồn tại trên primary không.
7. **Topology:** có failover hoặc replica lag trong khoảng thời gian lỗi không; endpoint hiện tại có trỏ tới primary có thẩm quyền không.

Không log password, full connection URL chứa secret, token hoặc payload nhạy cảm. Với lỗi commit chưa rõ, cần giữ request ID và các dấu thời gian đủ để đối chiếu log ứng dụng, proxy và MySQL.

## 11. Bài thực hành

Một service Spring Boot tạo đơn hàng và thanh toán bằng MySQL. HikariCP có `maximumPoolSize=10`. Trong đợt tải cao:

- API đôi lúc trả timeout.
- Hikari báo `Connection is not available, request timed out`.
- Một số log JDBC có `Communications link failure`.
- Client thử lại request và đôi khi tạo hai payment cho cùng một đơn.
- MySQL có `Threads_running` tăng và một số transaction chờ lock.

Hãy lập kế hoạch điều tra và kiểm thử:

1. Phân biệt pool acquisition timeout, connect timeout, query timeout, lock wait timeout và socket timeout trong tình huống này.
2. Những metrics Hikari nào cần thu thập để phân biệt pool leak với query chậm?
3. Viết hai session SQL để tạo lock wait timeout có kiểm soát và xác định transaction cần rollback.
4. Thiết kế test pool exhaustion bằng pool size nhỏ và latch, không dùng sleep dài để đồng bộ.
5. Dùng proxy tạo lỗi trước khi gửi DML, trong lúc DML và sau khi chuyển tiếp COMMIT nhưng trước khi trả response.
6. Thiết kế bảng idempotency có unique request ID và payload hash; bảo đảm payment cùng request record commit trong một transaction.
7. Nếu mất kết nối trong `commit()`, vì sao không thể dựa vào exception hoặc `rollback()` để kết luận kết quả?
8. Vì sao phải tra cứu idempotency record trên primary thay vì replica bất đồng bộ ngay sau lỗi?
9. Thiết kế retry có giới hạn, exponential backoff, jitter và deadline tổng.
10. Nêu assertion để chứng minh retry không tạo payment trùng, không giữ connection và không làm pool tiếp tục cạn.
11. Nếu primary failover trước khi giao dịch được replicate, cần xem xét RPO và GTID thế nào?

Một phương án tốt phải có ma trận lỗi theo từng tầng, điểm fault injection có thể đồng bộ, idempotency key ổn định và tiêu chí xác minh dữ liệu sau từng lần thử. Chạy toàn bộ bài thực hành trên MySQL test instance cô lập.

## 12. Những nhầm lẫn thường gặp

- **Gọi mọi timeout là query timeout:** lỗi có thể xảy ra khi chờ pool, connect, lock, socket hoặc request deadline.
- **Tăng pool size ngay khi pool cạn:** nếu MySQL đang quá tải, thêm connection có thể làm tình hình tệ hơn.
- **Cho rằng query timeout tự rollback transaction:** cần kiểm tra trạng thái transaction và rollback theo đúng connection.
- **Cho rằng socket timeout nghĩa MySQL chưa chạy câu lệnh:** server có thể đã nhận và thực thi request.
- **Cho rằng `rollback()` sau mất kết nối chứng minh chưa commit:** lệnh rollback có thể không tới server; commit có thể đã hoàn tất.
- **Retry với request ID mới:** làm mất khả năng deduplicate thao tác cũ.
- **Đọc replica ngay để xác định commit:** replica bất đồng bộ có thể chưa nhận hoặc apply giao dịch.
- **Dùng leak detection như cơ chế tự giải phóng:** cảnh báo chỉ giúp phát hiện connection được giữ lâu.
- **Chỉ kiểm thử bằng cách tắt MySQL:** không tái hiện được mọi trạng thái đứt mạng quanh commit.
- **Không phân biệt commit với side effect ngoài DB:** dùng outbox và idempotent consumer cho luồng tích hợp.

## Kết luận

Timeout và mất kết nối phải được phân loại theo tầng: pool, connect, statement, lock, socket và request. Pool exhaustion thường phản ánh connection bị giữ lâu hoặc database đang chậm; tăng pool size không phải lúc nào cũng giải quyết được. Đặc biệt, mất phản hồi trong `COMMIT` tạo ra kết quả chưa xác định ở phía client: transaction có thể đã commit. Thiết kế idempotency key và lưu dấu vết request cùng dữ liệu nghiệp vụ trong một transaction giúp ứng dụng truy vấn lại kết quả và retry an toàn. Hãy kiểm thử bằng fault injection có điểm đồng bộ, theo dõi cả metrics ứng dụng lẫn MySQL và xác minh dữ liệu sau mỗi kịch bản.

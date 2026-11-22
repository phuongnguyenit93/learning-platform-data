# Mô phỏng deadlock, pool cạn, timeout và mất kết nối

Một sự cố database trong ứng dụng Java thường không xuất hiện riêng lẻ. Khi tải tăng, transaction giữ lock lâu có thể làm query khác chờ; query chờ giữ connection trong pool; pool cạn khiến request mới timeout. Nếu ứng dụng retry thiếu kiểm soát, số request và connection tăng thêm. Nếu kết nối đứt quanh thời điểm commit, client có thể không biết thao tác đã được ghi hay chưa và retry có thể tạo dữ liệu trùng.

Bài thực hành này dựng một môi trường MySQL/InnoDB và ứng dụng JDBC/HikariCP để mô phỏng bốn nhóm sự cố: deadlock, pool exhaustion, timeout và mất kết nối. Mục tiêu là tái hiện lỗi có kiểm soát, đọc bằng chứng ở cả ứng dụng lẫn MySQL, xử lý transaction đúng cách và xác minh dữ liệu sau phục hồi.

Các ví dụ giả định MySQL 8.0.16 trở lên, InnoDB, Java JDBC và HikariCP để constraint `CHECK` trong schema được thực thi. Chỉ chạy những kịch bản cố ý khóa bảng, làm cạn pool hoặc ngắt mạng trên database kiểm thử cô lập. Không dùng dữ liệu hoặc endpoint production.

## Mục tiêu thực hành

Sau bài học, bạn có thể:

- Dựng schema và fixture đủ để tái hiện các lỗi concurrency.
- Tạo deadlock có thể lặp lại bằng hai session khóa hàng theo thứ tự ngược nhau.
- Phân biệt deadlock error `1213` với lock wait timeout `1205`.
- Làm cạn HikariCP bằng latch và xác minh request không lấy được connection chưa gửi SQL.
- Phân biệt pool acquisition timeout, JDBC query timeout, socket timeout và InnoDB lock wait timeout.
- Mô phỏng kết nối đứt trước, trong và sau DML/COMMIT.
- Xử lý kết quả commit chưa rõ bằng idempotency key và truy vấn đối soát.
- Đọc process list, transaction, lock wait, Hikari metrics và log ứng dụng.
- Thiết kế retry có giới hạn và chạy lại toàn transaction khi cần.

## 1. Kiến trúc lab

Lab có một MySQL test instance, một ứng dụng Java dùng HikariCP và một proxy mạng tùy chọn để tạo lỗi kết nối có thể kiểm soát.

```text
                 Test runner
                     |
                     v
             Java service / JDBC
                     |
                HikariCP pool
                     |
              (optional proxy)
                     |
                     v
              MySQL 8.0 / InnoDB
               |       |       |
             accounts orders operation_requests
```

Mỗi kịch bản cần có:

1. Điều kiện bắt đầu xác định.
2. Cách kích hoạt lỗi có thể lặp lại.
3. Dấu hiệu quan sát ở client và server.
4. Hành động phục hồi đúng với trạng thái transaction.
5. Assertion xác nhận dữ liệu và resource đã trở về trạng thái mong đợi.

Không dựa vào `Thread.sleep()` để tạo thứ tự giữa các worker. Dùng latch/barrier trong Java hoặc điều khiển rõ ràng hai SQL session để biết chắc session nào đang giữ lock trước khi session còn lại chạy.

## 2. Chuẩn bị schema và dữ liệu

Tạo database test riêng:

```sql
CREATE DATABASE mysql_incident_lab
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

USE mysql_incident_lab;

CREATE TABLE accounts (
  account_id BIGINT UNSIGNED NOT NULL,
  owner_name VARCHAR(100) NOT NULL,
  balance DECIMAL(18, 2) NOT NULL,
  PRIMARY KEY (account_id),
  CONSTRAINT chk_accounts_balance_nonnegative CHECK (balance >= 0)
) ENGINE = InnoDB;

CREATE TABLE orders (
  order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  customer_id BIGINT UNSIGNED NOT NULL,
  status VARCHAR(30) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (order_id),
  KEY idx_orders_customer_status (customer_id, status)
) ENGINE = InnoDB;

INSERT INTO accounts (account_id, owner_name, balance)
VALUES
  (1, 'Account A', 1000.00),
  (2, 'Account B', 1000.00);
```

Bảng `accounts` phục vụ deadlock và lock wait; bảng `orders` dùng cho query timeout hoặc DML thử nghiệm. Dùng InnoDB để transaction và row lock có hành vi cần kiểm tra.

### 2.1. Bảng idempotency cho thử nghiệm commit chưa rõ

Tạo bảng payment và request marker:

```sql
CREATE TABLE payments (
  payment_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  request_id VARCHAR(64) NOT NULL,
  amount DECIMAL(18, 2) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (payment_id),
  UNIQUE KEY uk_payments_request (request_id)
) ENGINE = InnoDB;

CREATE TABLE operation_requests (
  request_id VARCHAR(64) NOT NULL,
  payload_hash BINARY(32) NOT NULL,
  payment_id BIGINT UNSIGNED NOT NULL,
  completed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (request_id),
  UNIQUE KEY uk_operation_payment (payment_id)
) ENGINE = InnoDB;
```

Trong thiết kế production, payment và request marker phải được ghi trong cùng transaction InnoDB. Hai bảng dùng unique key để một request ID không thể tạo hai payment. Bảng lab được tạo tối giản để tập trung vào hành vi commit và retry.

Kiểm tra dữ liệu ban đầu:

```sql
SELECT * FROM accounts ORDER BY account_id;
SELECT COUNT(*) AS payment_count FROM payments;
SELECT COUNT(*) AS request_count FROM operation_requests;
```

Giữa các lượt chạy, chỉ reset khi mọi worker/transaction đã dừng:

```sql
DELETE FROM operation_requests;
DELETE FROM payments;
UPDATE accounts SET balance = 1000.00 WHERE account_id IN (1, 2);
```

## 3. Thu thập trạng thái trước khi gây lỗi

Trước mỗi kịch bản, lưu baseline để phân biệt trạng thái bình thường với trạng thái sau sự cố.

```sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
  'Threads_connected',
  'Threads_running',
  'Max_used_connections',
  'Connection_errors_max_connections',
  'Aborted_connects',
  'Aborted_clients'
);

SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
  'max_connections',
  'innodb_lock_wait_timeout',
  'wait_timeout',
  'max_execution_time'
);

SHOW FULL PROCESSLIST;
```

Với MySQL 8.0, có thể xem transaction và lock wait:

```sql
SELECT
  trx_id,
  trx_state,
  trx_started,
  trx_mysql_thread_id,
  trx_rows_locked,
  trx_rows_modified
FROM information_schema.innodb_trx
ORDER BY trx_started;

SELECT
  REQUESTING_ENGINE_TRANSACTION_ID,
  REQUESTING_THREAD_ID,
  BLOCKING_ENGINE_TRANSACTION_ID,
  BLOCKING_THREAD_ID
FROM performance_schema.data_lock_waits;
```

Nếu tài khoản quan sát không có quyền xem đầy đủ session hoặc Performance Schema, dùng account monitoring được cấp quyền phù hợp trong lab.

Ở phía HikariCP, ghi lại `active`, `idle`, `pending`, `total`, acquisition time, usage time và timeout count. Gắn request ID hoặc scenario ID vào log để ghép sự kiện ở Java với process list và timestamp MySQL.

## 4. Kịch bản A — Tạo deadlock bằng hai session

Deadlock xảy ra khi hai transaction giữ lock mà transaction kia cần, tạo thành vòng chờ. InnoDB phát hiện chu trình và chọn một transaction làm victim; lỗi thường gặp là `1213` (`ER_LOCK_DEADLOCK`, SQLState `40001`).

### 4.1. Chuẩn bị hai session

Mở hai SQL connection độc lập tới `mysql_incident_lab`. Chạy lệnh theo thứ tự sau, đồng bộ giữa hai session tại điểm được chỉ định.

**Session A**

```sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 10.00
WHERE account_id = 1;
```

Session A giữ exclusive row lock trên account 1.

**Session B**

```sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 20.00
WHERE account_id = 2;
```

Session B giữ exclusive row lock trên account 2.

Sau khi cả hai lệnh đầu hoàn tất, yêu cầu hai session cập nhật hàng còn lại:

**Session A**

```sql
UPDATE accounts
SET balance = balance + 10.00
WHERE account_id = 2;
```

**Session B**

```sql
UPDATE accounts
SET balance = balance + 20.00
WHERE account_id = 1;
```

Session A chờ account 2 do B giữ; session B chờ account 1 do A giữ. InnoDB phát hiện deadlock và rollback một transaction. Session bị chọn victim nhận lỗi 1213; transaction còn lại có thể tiếp tục sau khi lock của victim được giải phóng.

### 4.2. Quan sát deadlock

Ngay sau khi xảy ra lỗi:

```sql
SHOW ENGINE INNODB STATUS\G
```

Tìm phần `LATEST DETECTED DEADLOCK` để xem hai transaction, các lock đang giữ và lock đang chờ. Trong lab có thể bật log mọi deadlock để lưu bằng chứng:

```sql
SET GLOBAL innodb_print_all_deadlocks = ON;
```

Đây là cấu hình phục vụ quan sát; nếu thay đổi global variable trong môi trường dùng chung, phải có quyền và khôi phục cấu hình sau lab. Trong môi trường thật, bật log cần cân nhắc lượng log phát sinh.

### 4.3. Xử lý đúng sau deadlock

- Xác định transaction nào bị rollback; không giả định câu lệnh cuối là thao tác duy nhất bị hoàn tác.
- Với InnoDB, lỗi deadlock thường khiến toàn bộ transaction victim bị rollback.
- Ứng dụng phải chạy lại toàn bộ đơn vị nghiệp vụ trong transaction mới nếu thao tác có thể retry an toàn.
- Dùng idempotency key để tránh lặp side effect nếu client không chắc kết quả.
- Giảm deadlock bằng cách truy cập các row theo cùng thứ tự khóa trong mọi luồng.

Đừng chỉ retry câu SQL bị lỗi nếu các câu trước trong transaction là một phần của cùng nghiệp vụ. Điều đó có thể tạo trạng thái một phần hoặc sai invariant.

### 4.4. Kiểm tra kết quả

Sau khi cả hai session kết thúc bằng commit/rollback phù hợp:

```sql
SELECT account_id, balance
FROM accounts
ORDER BY account_id;
```

Xác nhận không có transaction treo, tổng số dư bằng tổng trước test (nếu mọi thay đổi chỉ là chuyển giữa hai account) và session victim đã kết thúc transaction. Sau khi cả hai session đã kết thúc, reset fixture về 1000.00 trước khi chạy lại:

```sql
UPDATE accounts
SET balance = 1000.00
WHERE account_id IN (1, 2);
```

## 5. Kịch bản B — Phân biệt deadlock và lock wait timeout

Lock wait timeout không nhất thiết có chu trình deadlock. Một transaction chỉ đơn giản chờ row lock quá thời gian được cấu hình.

**Session A — giữ lock**

```sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 5.00
WHERE account_id = 1;
```

Giữ transaction mở và chưa commit.

**Session B — đặt timeout ngắn rồi chờ**

```sql
SET SESSION innodb_lock_wait_timeout = 2;
START TRANSACTION;

UPDATE accounts
SET balance = balance + 5.00
WHERE account_id = 1;
```

Session B chờ account 1. Sau khoảng thời gian cấu hình, nó nhận lỗi `1205` (`ER_LOCK_WAIT_TIMEOUT`). Theo mặc định, InnoDB rollback statement bị timeout; transaction có thể vẫn còn mở với những thay đổi trước đó. Ứng dụng nên rollback toàn transaction nếu muốn retry nghiệp vụ từ đầu.

Kết thúc Session A:

```sql
COMMIT;
```

Sau đó Session B:

```sql
ROLLBACK;
```

So sánh với deadlock:

| Đặc điểm | Deadlock | Lock wait timeout |
|---|---|---|
| Điều kiện | Có chu trình chờ lock | Chờ một lock vượt giới hạn |
| Phát hiện | InnoDB deadlock detector | `innodb_lock_wait_timeout` |
| Mã lỗi thường gặp | `1213` | `1205` |
| Phạm vi rollback mặc định | Toàn bộ transaction victim | Statement bị timeout; transaction có thể vẫn mở |
| Retry | Transaction mới, toàn bộ nghiệp vụ | Rollback toàn transaction ở ứng dụng rồi mới retry |

## 6. Kịch bản C — Làm cạn HikariCP có kiểm soát

Pool exhaustion xảy ra ở ứng dụng khi không còn connection rảnh để cấp cho request. Có thể tái hiện mà không cần làm MySQL hết `max_connections`.

### 6.1. Cấu hình pool test nhỏ

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 2
      minimum-idle: 2
      connection-timeout: 1000
```

Chỉ dùng cấu hình này cho profile test. Tạo ba worker nhưng chỉ hai worker đầu được phép mượn connection và giữ nó; worker thứ ba yêu cầu connection sau khi hai latch xác nhận đã mượn đủ.

### 6.2. Pseudocode Java dùng latch

```java
CountDownLatch bothConnectionsBorrowed = new CountDownLatch(2);
CountDownLatch releaseConnections = new CountDownLatch(1);
ExecutorService executor = Executors.newFixedThreadPool(3);

Runnable holder = () -> {
    try (Connection connection = dataSource.getConnection()) {
        bothConnectionsBorrowed.countDown();
        releaseConnections.await();
    } catch (Exception e) {
        throw new RuntimeException(e);
    }
};

Future<?> first = executor.submit(holder);
Future<?> second = executor.submit(holder);

try {
    if (!bothConnectionsBorrowed.await(5, TimeUnit.SECONDS)) {
        throw new AssertionError("Pool holders did not acquire both connections");
    }

    long startedAt = System.nanoTime();
    try (Connection ignored = dataSource.getConnection()) {
        throw new AssertionError("Third borrower unexpectedly acquired a connection");
    } catch (SQLException expected) {
        long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
            System.nanoTime() - startedAt);
        // Kiểm tra đây là lỗi pool acquisition timeout và thời gian gần connectionTimeout.
    }
} finally {
    releaseConnections.countDown();
    executor.shutdownNow();
}

first.get();
second.get();
```

Đây là pseudocode minh họa đồng bộ; phần cleanup giải phóng latch và dừng executor trong `finally` để không giữ connection nếu assertion thất bại. Kiểm tra exception/cause cụ thể của HikariCP ở phiên bản đang dùng để phân biệt pool timeout với lỗi kết nối MySQL. Không chỉ assert elapsed time bằng một con số tuyệt đối vì scheduler và CI có sai số; dùng khoảng thời gian có biên hợp lý.

### 6.3. Kết quả cần xác minh

- Hai worker đầu lấy được hai connection và giữ chúng.
- Worker thứ ba timeout ở bước `getConnection()`.
- Worker thứ ba chưa gửi SQL tới MySQL.
- Hikari metrics cho thấy `active=2`, `idle=0`, `pending` tăng trong lúc chờ.
- Sau khi hai worker đóng connection, pool phục hồi và request mới lấy được connection.
- Không còn pending thread hoặc connection active sau cleanup.

Đây là pool acquisition timeout, không phải MySQL error 1040. MySQL vẫn có thể còn nhiều connection khả dụng.

## 7. Kịch bản D — Query timeout và lock wait timeout qua JDBC

Hai timeout này cần được kiểm thử riêng vì một cái giới hạn statement ở phía JDBC, cái kia giới hạn chờ row lock trong InnoDB.

### 7.1. Query timeout với SELECT SLEEP

Ví dụ dùng một connection test:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
         "SELECT SLEEP(10)")) {
    statement.setQueryTimeout(2);

    try (ResultSet resultSet = statement.executeQuery()) {
        resultSet.next();
    }
}
```

Driver được yêu cầu hủy statement sau khoảng hai giây. Hành vi thực tế phụ thuộc driver và cách gửi lệnh cancel; test nên ghi exception, SQLState, thời gian và trạng thái connection. Query timeout không tự động có nghĩa toàn transaction đã rollback. Nếu connection còn hợp lệ và transaction đang mở, rollback theo logic ứng dụng; nếu connection không còn đáng tin cậy, loại nó khỏi pool.

### 7.2. Lock wait timeout qua JDBC

Mở Session A giữ row lock như kịch bản B. Từ connection khác, đặt:

```sql
SET SESSION innodb_lock_wait_timeout = 2;
```

Sau đó thực hiện update cùng hàng bằng JDBC. Xác minh driver nhận lỗi vendor code `1205`, transaction được rollback theo chính sách ứng dụng và connection được trả pool sạch.

### 7.3. Không nhầm timeout tầng request với timeout SQL

Một request có thể timeout ở HTTP gateway trước khi JDBC query timeout xảy ra. Việc client HTTP ngừng chờ không nhất thiết hủy statement đang chạy ở server. Ứng dụng cần truyền deadline/cancellation xuống tầng xử lý, nhưng vẫn phải kiểm tra transaction và resource lifecycle.

Đặt thứ tự timeout có chủ đích: deadline request đủ lớn để service hoàn tất hoặc dừng có kiểm soát; pool acquisition ngắn hơn deadline còn lại; connect/query/socket timeout phù hợp với từng thao tác. Không đặt tất cả cùng một giá trị rồi giả định chúng hủy nhau.

## 8. Kịch bản E — Mất kết nối trước và trong DML

Để tạo lỗi mạng có kiểm soát, đặt proxy test giữa ứng dụng và MySQL, chẳng hạn Toxiproxy. Cấu hình JDBC trỏ tới proxy; proxy chuyển tiếp bình thường trước khi test bật lỗi.

Các tình huống:

| Điểm ngắt | Cách tạo | Điều cần quan sát |
|---|---|---|
| Trước khi connect | Proxy không chuyển tiếp kết nối mới | Connect timeout/refused; chưa có SQL |
| Khi connection idle | Reset socket đang idle | Pool validation phát hiện connection stale và loại bỏ |
| Trong query đọc | Tăng latency rồi cắt response | JDBC nhận socket/communications error; connection có thể bị đóng |
| Trong DML | Ngắt mạng sau khi request gửi tới server | Client không biết statement đã hoàn tất hay chưa; với InnoDB statement có tính nguyên tử nhưng transaction có thể chưa commit |
| Sau DML, trước commit | Cắt session trước khi COMMIT tới server | Transaction chưa commit sẽ được rollback khi server phát hiện session kết thúc |

Không dùng `KILL QUERY` để thay thế test mất kết nối: nó kiểm tra hủy statement ở server, không kiểm tra trạng thái socket/network. Cũng không chỉ tắt MySQL để kết luận đã kiểm thử được mọi điểm đứt mạng.

Sau khi connection mất, không tiếp tục dùng connection đó cho câu lệnh khác. Connection phải được đóng/loại khỏi pool. Nếu transaction chưa commit, server thường rollback khi session đóng; nhưng nếu client không biết request đã tới server chưa, phải đối soát theo request ID trước khi retry.

## 9. Kịch bản F — Mất phản hồi quanh COMMIT

Đây là kịch bản quan trọng nhất vì client có thể nhận exception trong khi MySQL đã commit transaction thành công.

### 9.1. Ghi business row và idempotency record cùng transaction

Mỗi thao tác có `request_id` ổn định. Trong cùng transaction InnoDB:

1. Insert payment với request ID.
2. Insert operation request record chứa payload hash và payment ID.
3. Commit.

Ví dụ luồng xử lý:

```java
PaymentResult createPayment(PaymentCommand command) throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);
        try {
            long paymentId = insertPayment(connection, command);
            insertOperationRequest(
                connection,
                command.requestId(),
                command.payloadHash(),
                paymentId
            );
            connection.commit();
            return new PaymentResult(paymentId);
        } catch (SQLException e) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                e.addSuppressed(rollbackError);
            }
            throw e;
        }
    }
}
```

Đây là khung cho lần thực hiện đầu. Trong triển khai thật, xử lý duplicate request ID bằng cách đọc kết quả đã lưu và so sánh payload hash; không tạo request ID mới khi retry cùng một thao tác nghiệp vụ. Nếu rollback thất bại hoặc connection đã đứt, không tái sử dụng connection có trạng thái không rõ.

### 9.2. Reconciliation sau lỗi commit

Nếu socket đứt trong lúc `commit()`:

1. Ghi nhận request ID, thời điểm và loại thao tác; coi kết quả là chưa xác định.
2. Loại connection lỗi khỏi pool.
3. Mở connection mới tới primary có thẩm quyền, không đọc replica bất đồng bộ để kết luận ngay.
4. Tìm `operation_requests` theo request ID.
5. Nếu có record, so sánh payload hash và trả lại payment đã tạo.
6. Nếu chưa thấy record, đừng kết luận ngay transaction cũ đã rollback: session cũ có thể chưa được server phát hiện là mất kết nối.
7. Thử lại bằng cùng request ID và unique key. Nếu transaction cũ commit, unique constraint sẽ làm lần thử nhận duplicate; nếu transaction cũ rollback, lần thử có thể tạo record mới. Xử lý lock wait/duplicate theo quy tắc idempotency.

Unique index trên `payments.request_id` và `operation_requests.request_id` giúp serialize các lần thử cùng key. Nếu hai request cùng key nhưng payload hash khác nhau, từ chối request thay vì trả kết quả của payload khác.

### 9.3. Tạo tình huống commit đã thành công nhưng ACK bị mất

Để test đúng ambiguous commit, proxy phải cho request COMMIT tới MySQL và chặn phản hồi từ server về client sau khi server đã xử lý commit. Một proxy TCP thuần không tự hiểu ranh giới câu lệnh MySQL; nếu không có khả năng quan sát protocol, cần dùng test hook hoặc đồng bộ phía server để xác nhận commit đã hoàn tất trước khi drop response.

Hai trường hợp cần kiểm thử riêng:

**Trường hợp 1 — commit đã hoàn tất:**

- Client gửi transaction và COMMIT.
- Test xác nhận server đã commit.
- Proxy drop response về client.
- JDBC báo communications error.
- Client reconnect với cùng request ID.
- Kết quả phải trả về payment đã tồn tại; số payment theo request ID vẫn bằng một.

**Trường hợp 2 — COMMIT chưa tới server:**

- Client gửi DML nhưng proxy chặn COMMIT trước khi tới server rồi reset/đóng kết nối để MySQL phát hiện session đã mất.
- Server kết thúc session và rollback transaction chưa commit.
- Client retry với cùng request ID.
- Lần thử mới tạo đúng một payment và một operation record.

Nếu chỉ rút cáp hoặc tắt server ngẫu nhiên, không thể biết chắc test đang mô phỏng trường hợp nào. Cần điểm đồng bộ rõ ràng và kiểm tra dữ liệu sau mỗi lần thử.

## 10. Retry đúng phạm vi

Không retry tất cả exception. Phân loại lỗi trước:

| Lỗi | Hướng xử lý |
|---|---|
| Deadlock `1213` | InnoDB rollback transaction victim; chạy lại toàn transaction trong transaction mới nếu nghiệp vụ idempotent |
| Lock wait timeout `1205` | Statement bị timeout; rollback toàn transaction ở tầng ứng dụng rồi mới retry |
| Pool acquisition timeout | Chưa có connection nên SQL chưa chạy; điều tra pool/DB và áp dụng backpressure |
| Connect failure trước khi kết nối | Có thể retry connect có giới hạn nếu endpoint/mạng hồi phục |
| Query timeout | Kiểm tra transaction và connection; rollback nếu cần, không giả định query cancel đã rollback toàn transaction |
| Socket failure trong DML | Kết quả client chưa chắc chắn; đối soát theo idempotency key trước retry |
| Socket failure trong COMMIT | Ambiguous outcome; không tạo request ID mới, reconciliation trên primary |
| Duplicate key | Đọc record hiện có, so sánh payload hash; không retry vô hạn |
| Thiếu quyền/sai SQL/dữ liệu không hợp lệ | Sửa nguyên nhân; retry không giúp |

Chính sách retry nên có số lần thử tối đa, exponential backoff, jitter và deadline tổng. Retry toàn transaction phải nằm ngoài transaction đã thất bại; trong Spring, đặt retry ở tầng gọi bên ngoài method `@Transactional` hoặc tạo transaction mới cho từng attempt. Không lặp câu lệnh trong cùng transaction đã bị rollback hoặc có trạng thái không rõ.

## 11. Runbook chẩn đoán tổng hợp

Khi test hoặc hệ thống xuất hiện lỗi, đi theo thứ tự:

1. **Xác định nơi thất bại:** `getConnection()`, `executeQuery/executeUpdate`, `commit()` hay request deadline.
2. **Ghi nhận lỗi:** exception class, SQLState, vendor code, request/scenario ID và timestamp.
3. **Kiểm tra pool:** active, idle, pending, total, acquire time, usage time và leak warning.
4. **Kiểm tra MySQL:** `Threads_connected`, `Threads_running`, process list và error log.
5. **Kiểm tra transaction/lock:** `innodb_trx`, `data_lock_waits`, `SHOW ENGINE INNODB STATUS`.
6. **Phân loại transaction:** đã rollback chắc chắn, còn mở, đã commit được xác nhận hay kết quả chưa rõ.
7. **Phục hồi:** rollback transaction còn hoạt động; loại connection hỏng; reconcile idempotency key; retry toàn transaction khi an toàn.
8. **Xác minh:** số hàng, số dư, payment theo request ID, pool metrics và transaction treo.

Các câu lệnh quan sát nhanh:

```sql
SHOW FULL PROCESSLIST;
SHOW ENGINE INNODB STATUS\G
SELECT *
FROM information_schema.innodb_trx
ORDER BY trx_started;

SELECT *
FROM performance_schema.data_lock_waits;
```

## 12. Ma trận kiểm thử cuối lab

| ID | Kịch bản | Kích hoạt | Lỗi/dấu hiệu mong đợi | Assertion dữ liệu/resource |
|---|---|---|---|---|
| A1 | Deadlock | Hai session khóa hai account theo thứ tự ngược | Một transaction nhận `1213` | Victim rollback; transaction còn lại kết thúc; tổng số dư đúng |
| B1 | Lock wait timeout | A giữ row lock, B chờ với timeout 2 giây | B nhận `1205` | Ứng dụng rollback toàn transaction; không còn lock treo |
| C1 | Pool exhaustion | Pool size 2, hai holder giữ connection, borrower thứ ba chờ | Hikari acquisition timeout | SQL không chạy ở borrower thứ ba; pool phục hồi sau release |
| D1 | Query timeout | `SELECT SLEEP(10)` với query timeout ngắn | JDBC báo query timeout/cancel | Connection/transaction được xử lý sạch; không còn resource bị giữ |
| E1 | Disconnect trong DML | Proxy reset khi query đang thực thi | Communications/socket error | Không retry mù; kiểm tra request ID và trạng thái dữ liệu |
| F1 | Commit ACK mất | Chuyển tiếp COMMIT, drop response sau commit | Client thấy connection error | Retry cùng key trả cùng payment; không có bản ghi trùng |
| F2 | Commit chưa tới server | Proxy chặn COMMIT trước server | Client thấy connection error | Transaction cũ rollback; retry cùng key tạo đúng một payment |

Mỗi test phải có cleanup trong `finally` hoặc lifecycle hook. Nếu test làm mất connection, đóng/evict connection; nếu test giữ lock, luôn rollback/đóng session A; nếu proxy được bật, khôi phục proxy trước khi test tiếp theo. Suite phải kết thúc với pool không còn active/pending bất thường và database có fixture ban đầu.

## 13. Bài thực hành tổng hợp

Một dịch vụ chuyển tiền dùng MySQL 8.0/InnoDB và HikariCP. Hai worker cập nhật account theo thứ tự khác nhau; pool có `maximumPoolSize=4`. Một endpoint báo timeout khi tải tăng, log có cả `1213`, `1205` và `Communications link failure`. Một số client retry và tạo payment trùng.

Hãy thực hiện lab theo thứ tự:

1. Tạo schema, seed hai account và bảng idempotency.
2. Chạy hai-session deadlock; lưu output `SHOW ENGINE INNODB STATUS` và xác định victim.
3. Chạy lock wait timeout riêng; giải thích vì sao phạm vi rollback khác deadlock.
4. Chạy pool exhaustion với hai connection holder và borrower thứ ba theo cấu hình pool size 2; xác minh MySQL chưa nhất thiết chạm `max_connections`.
5. Chạy query timeout bằng `SELECT SLEEP()` và kiểm tra transaction/connection sau lỗi.
6. Dùng proxy mô phỏng mất kết nối trước khi gửi DML và trong khi DML đang thực thi.
7. Tạo ambiguous commit có đồng bộ: server đã commit nhưng client không nhận ACK.
8. Retry cùng request ID, đối chiếu payload hash và chứng minh chỉ có một payment.
9. Lặp lại với COMMIT bị chặn trước khi tới server và chứng minh transaction cũ không để lại payment.
10. Thu thập Hikari metrics, process list, transaction, lock wait và log ứng dụng cho từng kịch bản.
11. Thêm retry policy có giới hạn và backpressure; chạy lại test tải để xác nhận không tạo retry storm.
12. Reset fixture, đóng proxy và executor, xác nhận không còn connection hoặc transaction bị giữ.

### Câu hỏi đánh giá

1. Điều kiện nào tạo ra deadlock và tại sao InnoDB chỉ rollback một transaction làm victim?
2. Khác biệt chính giữa lỗi 1213 và 1205 là gì?
3. Vì sao pool acquisition timeout có thể xảy ra khi MySQL vẫn còn connection trống?
4. Hikari `active=max`, `idle=0`, `pending>0` cho biết điều gì và chưa chứng minh điều gì?
5. Vì sao không nên giữ transaction trong lúc gọi HTTP hoặc chờ latch?
6. Query timeout có tự động rollback toàn transaction không?
7. Khi socket đứt trong DML hoặc COMMIT, vì sao exception không cho biết chắc dữ liệu đã commit hay chưa?
8. Vì sao idempotency record phải commit cùng payment trong một transaction?
9. Vì sao reconciliation nên đọc primary có thẩm quyền thay vì replica bất đồng bộ?
10. Retry cần đặt ở đâu để mỗi attempt dùng transaction mới?
11. Những assertion nào chứng minh pool và database đã phục hồi sau test?

## Kết luận

Lab tích hợp cần tạo từng lỗi ở đúng tầng và xác minh trạng thái sau đó. Deadlock `1213` thường rollback toàn transaction victim; lock wait timeout `1205` mặc định rollback statement đang chờ nên ứng dụng cần quyết định rollback transaction. Pool exhaustion xảy ra ở bước mượn connection và có thể xuất hiện trước khi MySQL hết `max_connections`. Query timeout, socket timeout và request deadline cũng có phạm vi khác nhau. Đặc biệt, mất phản hồi quanh COMMIT tạo kết quả chưa rõ ở client; idempotency key và unique constraint cho phép đối soát, retry an toàn và tránh tạo giao dịch trùng. Hãy dùng latch và fault injection có đồng bộ, quan sát cả Hikari lẫn MySQL, rồi chỉ kết thúc lab khi dữ liệu, transaction và pool đã trở về trạng thái sạch.

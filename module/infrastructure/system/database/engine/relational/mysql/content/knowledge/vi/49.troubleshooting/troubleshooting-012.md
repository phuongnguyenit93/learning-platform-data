# Too many connections, connection leak và pool ứng dụng cạn

Ứng dụng Java kết nối MySQL thường dùng connection pool để tái sử dụng kết nối. Khi hệ thống tăng tải, một lỗi có thể xuất hiện ở hai nơi: MySQL từ chối kết nối mới với lỗi `Too many connections` (error 1040), hoặc ứng dụng không lấy được connection từ pool trong thời gian chờ và báo pool timeout. Hai lỗi có liên quan nhưng không giống nhau. MySQL có thể vẫn còn chỗ nhưng pool ứng dụng đã cạn; ngược lại, pool còn chỗ nhưng MySQL đã chạm `max_connections`.

Nguyên nhân thường nằm ở ngân sách connection toàn hệ thống, connection bị giữ quá lâu, query/transaction chậm, connection leak hoặc cấu hình pool không phù hợp với khả năng chịu tải của database. Tăng `max_connections` hay tăng pool size ngay lập tức có thể chỉ đẩy vấn đề sang tầng khác và làm MySQL quá tải hơn.

Bài học này tập trung vào MySQL 8.0, JDBC và HikariCP trong ứng dụng Spring Boot. Các ví dụ cấu hình chỉ mang tính minh họa; cần điều chỉnh theo số instance, workload, giới hạn hạ tầng và phiên bản thư viện thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt MySQL `Too many connections` với pool acquisition timeout.
- Tính ngân sách connection từ tất cả application instance, worker và công cụ vận hành.
- Đọc `max_connections`, `max_user_connections` và process list để tìm nguồn kết nối.
- Phân tích HikariCP active, idle, pending và connection usage.
- Nhận diện connection leak, transaction dài và connection bị giữ trong lúc gọi dịch vụ ngoài.
- Xử lý sự cố theo thứ tự an toàn, tránh kill session hoặc tăng giới hạn thiếu kiểm soát.
- Thiết kế kiểm thử pool exhaustion, leak và tải đồng thời.

## 1. Hai loại cạn connection khác nhau

Một ứng dụng thường có pool riêng. Pool quản lý số kết nối vật lý từ ứng dụng tới MySQL. Mỗi request cần truy cập database sẽ mượn một connection; khi hoàn tất và đóng resource, connection được trả về pool để request khác sử dụng.

```text
Request A ----+                       +---- MySQL
Request B ----+---- HikariCP pool ----+---- max_connections
Request C ----+                       +---- account limits
                  active / idle
                  pending / total
```

| Tình huống | Dấu hiệu thường thấy | Vấn đề ở đâu? |
|---|---|---|
| MySQL hết chỗ nhận client connection | Error 1040 `Too many connections` | Tổng session trên server chạm giới hạn hoặc account chạm giới hạn riêng |
| Pool ứng dụng hết connection rảnh | Hikari báo `Connection is not available, request timed out` | Request đang chờ connection trong pool; có thể các connection đều đang được mượn |
| MySQL từ chối một account cụ thể | Error 1226 `ER_USER_LIMIT_REACHED` hoặc thông báo vượt resource limit | Account có `MAX_USER_CONNECTIONS` hoặc giới hạn global áp dụng |
| Connection cũ bị đóng nhưng pool chưa nhận biết | `Communications link failure`, connection validation thất bại | Idle timeout, proxy, firewall hoặc mạng làm connection stale |

Pool exhaustion có thể xảy ra khi MySQL vẫn còn nhiều connection khả dụng: một pool có `maximumPoolSize=10` nhưng cả 10 connection đang bị giữ thì request thứ 11 vẫn phải chờ. Ngược lại, MySQL có thể hết connection do nhiều ứng dụng hoặc công cụ khác, dù một pool riêng lẻ chưa đạt giới hạn.

## 2. Ngân sách connection toàn hệ thống

`max_connections` giới hạn số client connection đồng thời trên một MySQL server. Cần tính tổng khả năng mở connection của tất cả ứng dụng, không chỉ một JVM.

Ví dụ một hệ thống có:

| Thành phần | Số instance tối đa | Pool tối đa mỗi instance | Tổng khả năng kết nối |
|---|---:|---:|---:|
| API service | 6 | 20 | 120 |
| Background worker | 3 | 10 | 30 |
| Scheduler | 2 | 5 | 10 |
| Migration, monitoring và admin | — | — | 20 |
| **Tổng dự kiến** | | | **180** |

Nếu MySQL đặt `max_connections=220`, hệ thống còn khoảng 40 connection headroom theo cấu hình trên. Phải tính theo số replica tối đa khi autoscaling, số DataSource/pool trong mỗi process, job chạy song song, công cụ backup, migration và kết nối vận hành. Nếu mỗi pod có hai pool, cần cộng cả hai.

Ngân sách cần đáp ứng:

\[
\sum (\text{số instance tối đa} \times \text{pool tối đa mỗi instance})
 + \text{kết nối ngoài ứng dụng}
 < \text{max\_connections}
\]

Phần chênh lệch là headroom cho deploy rolling, kết nối quản trị, burst và những thành phần chưa được liệt kê. Không cấu hình tổng pool bằng đúng `max_connections`: khi rollout tạo instance mới trước khi instance cũ dừng, số kết nối có thể vượt dự kiến.

### 2.1. Pool size không phải số request đồng thời

`maximumPoolSize` là số connection tối đa mà một pool có thể giữ, bao gồm connection active và idle. Nó không phải số thread HTTP, cũng không phải số request mà hệ thống nên chạy đồng thời.

Nếu có 100 request cùng lúc nhưng pool chỉ có 20 connection, tối đa 20 request có thể sử dụng database đồng thời qua pool đó; các request khác chờ hoặc bị giới hạn ở tầng ứng dụng. Đây có thể là backpressure có chủ đích. Nếu tăng pool lên 100, MySQL phải xử lý nhiều query đồng thời hơn và throughput tổng thể có thể giảm do tranh chấp CPU, I/O, buffer pool hoặc lock.

Chọn pool size bằng load test và đo latency/throughput của database. Không dùng một công thức cố định chỉ dựa trên số CPU của application server.

### 2.2. Giới hạn theo tài khoản

Ngoài giới hạn server, MySQL có giới hạn connection theo account. Biến `max_user_connections` đặt giới hạn mặc định theo user; account cũng có thể có resource limit riêng `MAX_USER_CONNECTIONS`.

Kiểm tra cấu hình:

```sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
  'max_connections',
  'max_user_connections'
);
```

Xem giới hạn của account:

```sql
SHOW CREATE USER 'app_user'@'10.%';
```

Ví dụ tạo account có giới hạn riêng:

```sql
CREATE USER 'app_worker'@'10.%'
  IDENTIFIED BY '<secret-from-secret-manager>'
  WITH MAX_USER_CONNECTIONS 30;
```

Account limit hữu ích để một service không chiếm hết connection của server. Nhưng nếu giới hạn quá thấp so với số replica và pool, chính service đó sẽ nhận lỗi dù MySQL tổng thể còn chỗ. Hãy tính giới hạn theo số instance tối đa và số pool thực tế.

## 3. Chẩn đoán từ phía MySQL

Khi có lỗi 1040, cần xem giới hạn, số connection hiện tại, mức cao nhất và nguồn session.

### 3.1. Kiểm tra status và variable

```sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
  'Threads_connected',
  'Threads_running',
  'Max_used_connections',
  'Connections',
  'Connection_errors_max_connections',
  'Aborted_connects',
  'Aborted_clients'
);

SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
  'max_connections',
  'max_user_connections',
  'wait_timeout',
  'interactive_timeout'
);
```

Ý nghĩa các chỉ số chính:

- `Threads_connected`: số client connection đang mở tại thời điểm đọc.
- `Threads_running`: số thread đang thực thi thay vì chỉ chờ trong trạng thái idle.
- `Max_used_connections`: mức đồng thời cao nhất kể từ khi server khởi động hoặc status được reset.
- `Connections`: số lần thử kết nối tới server kể từ khi khởi động hoặc reset status; không phải số connection hiện tại.
- `Connection_errors_max_connections`: số lần kết nối bị từ chối vì đạt giới hạn connection tối đa.
- `Aborted_connects` và `Aborted_clients`: số liệu về kết nối thất bại hoặc client ngắt không đúng cách; cần đọc cùng error log và trạng thái mạng.

Nếu `Max_used_connections` thường xuyên gần `max_connections`, hệ thống có ít headroom. Nếu `Threads_connected` cao nhưng `Threads_running` thấp, nhiều session có thể đang idle hoặc bị giữ trong pool. Điều đó chưa đủ để kết luận có leak.

### 3.2. Xem process list

```sql
SHOW FULL PROCESSLIST;
```

Hoặc truy vấn chi tiết:

```sql
SELECT
  ID,
  USER,
  HOST,
  DB,
  COMMAND,
  TIME,
  STATE,
  LEFT(INFO, 200) AS SQL_TEXT
FROM information_schema.PROCESSLIST
ORDER BY TIME DESC;
```

Để đếm connection theo user, host và trạng thái:

```sql
SELECT
  USER,
  HOST,
  COMMAND,
  COUNT(*) AS connection_count,
  MAX(TIME) AS longest_time_seconds
FROM information_schema.PROCESSLIST
GROUP BY USER, HOST, COMMAND
ORDER BY connection_count DESC;
```

`COMMAND='Sleep'` nghĩa session đang không thực thi statement tại thời điểm quan sát. Một số lượng Sleep connection là bình thường vì pool giữ connection rảnh để tái sử dụng. Tuy nhiên, một session Sleep vẫn có thể đang giữ transaction mở và row lock nếu ứng dụng đã chạy DML nhưng chưa commit/rollback. Kiểm tra transaction InnoDB:

```sql
SELECT
  t.trx_mysql_thread_id AS connection_id,
  p.USER,
  p.HOST,
  p.COMMAND,
  p.TIME AS process_time_seconds,
  t.trx_started,
  t.trx_state,
  t.trx_rows_locked,
  t.trx_rows_modified
FROM information_schema.innodb_trx AS t
LEFT JOIN information_schema.PROCESSLIST AS p
  ON p.ID = t.trx_mysql_thread_id
ORDER BY t.trx_started;
```

Cần so sánh số lượng Sleep session với tổng pool capacity và thời gian idle; không kill toàn bộ Sleep session chỉ vì chúng xuất hiện trong process list.

Quyền `PROCESS` có thể cần thiết để xem đầy đủ session của người dùng khác. Nếu chỉ thấy connection của tài khoản hiện tại, hãy dùng tài khoản giám sát được cấp quyền phù hợp theo chính sách.

### 3.3. Phân biệt pool idle bình thường với leak

Một connection Sleep lâu có thể là connection idle bình thường của pool. Dấu hiệu leak đáng chú ý hơn là:

- Pool báo active luôn sát `maximumPoolSize`, idle bằng 0 và pending tăng.
- Connection usage time kéo dài bất thường, không giảm sau khi request hoàn tất.
- Leak detection log lặp lại cùng code path hoặc stack trace.
- Application thread giữ connection trong khi chờ HTTP, queue, file hoặc khóa ứng dụng.
- Số session theo user/host tăng dần sau mỗi đợt request và không giảm về baseline.

Đối chiếu timestamp của Hikari metrics, application logs, process list và transaction age. Chỉ dựa vào `COMMAND='Sleep'` hoặc `Threads_connected` không đủ để kết luận leak.

## 4. Chẩn đoán từ HikariCP

HikariCP quản lý connection vật lý và cấp chúng cho code ứng dụng. Những metrics quan trọng gồm:

| Metric | Ý nghĩa | Dấu hiệu cần điều tra |
|---|---|---|
| `active` | Connection đang được ứng dụng mượn | Luôn bằng max pool size |
| `idle` | Connection rảnh trong pool | Bằng 0 khi pending tăng |
| `pending` | Thread đang chờ connection | Tăng kéo dài hoặc tăng theo tải |
| `total` | Tổng connection pool đang có | Chạm `maximumPoolSize` |
| Acquire time | Thời gian chờ mượn connection | Tăng mạnh trước pool timeout |
| Usage time | Thời gian giữ connection | Dài hơn thời gian xử lý SQL dự kiến |

Một số cách diễn giải:

- `active=max`, `idle=0`, `pending>0`: pool đã cạn ở application. Tìm connection đang bị giữ, query chậm hoặc transaction dài.
- `active` thấp, `idle` cao nhưng kết nối mới vẫn lỗi 1040: kiểm tra server-wide connection budget và các client khác.
- `active` tăng dần theo thời gian: có thể leak hoặc code giữ connection lâu; xác minh stack trace và lifecycle.
- `total` thấp hơn max và `getConnection()` vẫn lỗi: có thể pool không tạo được connection mới do MySQL từ chối, account limit, DNS, TLS hoặc network.

### 4.1. Cấu hình ví dụ

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 3000
      validation-timeout: 1000
      max-lifetime: 1500000
      keepalive-time: 300000
      leak-detection-threshold: 30000
```

Các giá trị trên chỉ là ví dụ. `connection-timeout` giới hạn thời gian chờ lấy connection từ pool; nó không phải query timeout. `max-lifetime` giúp pool loại connection theo tuổi; `keepalive-time` kiểm tra connection idle theo chu kỳ nếu được hỗ trợ. Hai giá trị phải phù hợp với idle/lifetime timeout của MySQL, proxy và network.

`leak-detection-threshold` làm Hikari ghi cảnh báo khi connection được mượn quá ngưỡng. Nó không tự đóng connection hoặc giải phóng transaction. Một query hợp lệ chạy lâu hay transaction dài cũng có thể tạo cảnh báo, vì vậy hãy xem stack trace tại thời điểm connection được mượn và đối chiếu usage time.

### 4.2. Connection.close() trong pool có ý nghĩa gì?

Với connection lấy từ HikariCP, gọi `Connection.close()` thường trả connection về pool để tái sử dụng, không đóng socket vật lý ngay lập tức. Vì thế, việc không gọi `close()` sẽ giữ connection ở trạng thái active và có thể làm pool cạn.

Dùng try-with-resources:

```java
String sql = "SELECT id, status FROM orders WHERE customer_id = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, customerId);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long id = resultSet.getLong("id");
            String status = resultSet.getString("status");
            // Xử lý dữ liệu.
        }
    }
}
```

Đóng `ResultSet`, `Statement` và `Connection` ở đúng phạm vi giúp driver và pool giải phóng resource. Nếu dùng Spring Data JPA hoặc `JdbcTemplate`, thường để framework quản lý connection; không tự đóng connection đang được transaction manager quản lý.

## 5. Connection leak và transaction giữ connection quá lâu

Connection leak xảy ra khi code mượn connection nhưng không trả lại pool. Một số trường hợp không phải leak theo nghĩa quên close nhưng vẫn gây cạn pool: connection được giữ quá lâu trong một transaction, result stream chưa đóng hoặc request chờ dịch vụ ngoài khi transaction còn mở.

### 5.1. Các mẫu code dễ gây leak

Không đóng connection khi có exception:

```java
Connection connection = dataSource.getConnection();
PreparedStatement statement = connection.prepareStatement(sql);
ResultSet resultSet = statement.executeQuery();

// Nếu có exception trước khi close, connection có thể bị giữ.
```

Mẫu đúng là dùng try-with-resources như ví dụ trước hoặc để framework quản lý lifecycle.

### 5.2. Không giữ transaction trong lúc gọi dịch vụ ngoài

Ví dụ thiết kế không tốt:

```java
@Transactional
public void placeOrder(OrderCommand command) {
    orderRepository.save(command.toEntity());
    paymentClient.authorize(command.payment()); // Gọi HTTP trong transaction
    notificationClient.send(command);           // Gọi dịch vụ khác
}
```

Transaction có thể giữ connection và lock trong toàn bộ thời gian chờ HTTP, kể cả khi MySQL không thực thi query. Nếu dịch vụ ngoài chậm, nhiều request sẽ đồng thời giữ connection và làm pool cạn.

Thiết kế lại transaction ngắn, chỉ bao quanh thao tác database cần nguyên tử. Dùng outbox hoặc workflow/saga phù hợp để phối hợp dịch vụ ngoài; không kéo dài transaction DB qua nhiều network call.

### 5.3. Stream và cursor

JPA/Hibernate stream hoặc JDBC `ResultSet` có thể giữ connection trong suốt thời gian đọc. Nếu ứng dụng trả stream ra ngoài rồi xử lý chậm hoặc quên đóng, connection không được trả pool.

Đóng stream rõ ràng:

```java
try (Stream<Order> orders = repository.streamPendingOrders()) {
    orders.forEach(this::processOrder);
}
```

Với Spring Data JPA, stream cần được dùng trong transaction phù hợp và đóng trước khi transaction kết thúc. Nếu xử lý khối lượng lớn, cân nhắc phân trang theo khóa hoặc chunk để giới hạn thời gian giữ connection và persistence context.

## 6. Xử lý sự cố Too many connections

Khi production báo error 1040, ưu tiên khôi phục khả năng quản trị và giảm nguồn tạo connection mới.

### 6.1. Quy trình ứng phó

1. **Xác nhận phạm vi:** phân biệt lỗi 1040 từ MySQL với pool acquisition timeout ở ứng dụng. Thu thập thời điểm, endpoint, user và host bị ảnh hưởng.
2. **Dùng kênh quản trị dự phòng:** nếu đã cấu hình, MySQL 8.0.14 trở lên hỗ trợ một kết nối quản trị bổ sung cho account có quyền `CONNECTION_ADMIN` khi đạt `max_connections`. Giữ thông tin đăng nhập quản trị riêng và kiểm tra khả năng sử dụng trước sự cố.
3. **Thu thập bằng chứng:** đọc status, variables, process list, transaction age và error log trước khi kill session.
4. **Xác định nguồn chiếm connection:** nhóm theo user/host/command, đối chiếu với số instance và pool capacity.
5. **Giảm tải có kiểm soát:** tạm dừng worker/batch không thiết yếu, giới hạn concurrency hoặc giảm traffic tại gateway. Không scale out ứng dụng nếu mỗi instance tự mở thêm pool.
6. **Giải phóng session có chọn lọc:** chỉ kết thúc session được xác định là runaway hoặc không còn cần thiết; đánh giá rollback và tác động nghiệp vụ trước.
7. **Khôi phục ngân sách:** điều chỉnh pool, số instance hoặc giới hạn MySQL dựa trên capacity đã đo; giữ headroom cho admin và công việc vận hành.
8. **Xác minh:** theo dõi connection count, pending, error 1040, latency, transaction và replica lag sau khi hệ thống ổn định.

### 6.2. Kill session có chọn lọc

Sau khi xác định đúng session, có thể dùng:

```sql
KILL CONNECTION 12345;
```

`KILL CONNECTION` đóng session. Nếu session có transaction InnoDB chưa commit, server sẽ rollback transaction đó; rollback có thể tốn thời gian và tạo tải I/O. `KILL QUERY` chỉ dừng statement đang chạy, connection vẫn còn.

Không kill tất cả session `Sleep`: phần lớn có thể là connection idle hợp lệ trong pool. Kill hàng loạt sẽ khiến pool mất connection, phải tạo lại kết nối và có thể tạo một đợt connection storm mới. Không kill session chỉ vì `TIME` lớn; xác định user, host, transaction, query và chủ sở hữu trước.

### 6.3. Có nên tăng max_connections?

`max_connections` có thể thay đổi động trong MySQL. Ví dụ:

```sql
SET GLOBAL max_connections = 250;
```

Lệnh trên chỉ minh họa thao tác quản trị; cần quyền hệ thống phù hợp và đánh giá tài nguyên trước khi áp dụng. Thay đổi bằng `SET GLOBAL` không tự đảm bảo được giữ sau restart; cấu hình bền vững cần được quản lý trong file cấu hình hoặc cơ chế persist được phiên bản hỗ trợ.

Trước khi tăng, đánh giá:

- Bộ nhớ cho mỗi connection và buffer/session resource.
- Số thread, CPU scheduling và context switching.
- Khả năng chịu tải của storage, buffer pool và query workload.
- Tổng pool capacity của mọi service khi autoscaling tối đa.
- `max_user_connections` và resource limit của account.
- Headroom dành cho admin, backup, monitoring và migration.

Tăng giới hạn có thể giúp vượt qua một đỉnh tải ngắn, nhưng không sửa connection leak hoặc transaction bị giữ lâu. Nếu server không đủ tài nguyên, nhiều connection hơn có thể làm latency và số lỗi tăng.

## 7. Phòng ngừa pool exhaustion

### 7.1. Đóng resource ở mọi nhánh

- Dùng try-with-resources cho JDBC connection, statement và result set.
- Không lưu connection trong field singleton hoặc truyền connection qua nhiều tầng không rõ ownership.
- Với transaction manager, để framework mở/đóng connection theo transaction.
- Đóng stream/cursor và không trả chúng ra ngoài phạm vi transaction nếu không có thiết kế rõ.
- Kiểm tra exception path, timeout path và cancellation path; resource phải được đóng cả khi lỗi.

### 7.2. Giữ transaction ngắn

- Chỉ mở transaction khi bắt đầu phần xử lý database cần nhất quán.
- Không gọi HTTP, gửi email, chờ queue hoặc xử lý file trong transaction.
- Tránh đọc dữ liệu lớn rồi xử lý lâu trong khi giữ connection.
- Dùng batch/chunk và commit theo phạm vi nghiệp vụ hợp lý.
- Kiểm tra transaction dài bằng `information_schema.innodb_trx` và process list.

### 7.3. Áp dụng backpressure

Pool là giới hạn concurrency ở tầng database, không phải hàng đợi vô hạn. Nếu số request vượt năng lực DB:

- Giới hạn số worker và executor queue.
- Dùng rate limit hoặc load shedding ở gateway.
- Đặt timeout lấy connection phù hợp với request deadline.
- Tránh retry dồn dập khi pool đã cạn.
- Tách workload đọc/ghi hoặc job nền theo nhu cầu, nhưng vẫn tính tổng ngân sách trên từng MySQL server.

Không dùng một queue vô hạn để giữ hàng nghìn request đang chờ connection. Queue lớn chỉ làm tăng thời gian chờ và bộ nhớ; nên từ chối hoặc điều tiết sớm khi vượt năng lực.

## 8. Kiểm thử connection leak và pool exhaustion

Kiểm thử cần chạy trên MySQL test instance cô lập với pool có kích thước nhỏ. Không cố ý làm cạn connection trên production.

### 8.1. Test pool exhaustion bằng latch

Cấu hình test:

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 1
      minimum-idle: 1
      connection-timeout: 500
```

Kịch bản:

1. Thread A lấy connection đầu tiên và giữ nó sau một `CountDownLatch` báo đã mượn.
2. Thread B chờ latch, sau đó yêu cầu connection thứ hai.
3. Xác nhận Thread B nhận pool acquisition timeout gần với ngưỡng đã cấu hình; không có SQL từ Thread B tới MySQL.
4. Thread A đóng connection trong `finally`.
5. Yêu cầu connection mới và xác nhận pool cấp lại thành công.

Dùng latch/barrier để điều khiển thứ tự. Không dựa vào `Thread.sleep()` dài vì timing của test sẽ không ổn định.

### 8.2. Test leak detection

Tạo test fixture cố ý giữ connection lâu hơn `leak-detection-threshold`, xác nhận Hikari phát cảnh báo và stack trace trỏ tới vị trí mượn connection. Sau đó đóng connection và xác nhận pool phục hồi.

Leak detection chỉ cảnh báo connection được giữ quá lâu; test phải xác nhận cả việc giải phóng thật sự. Một truy vấn hợp lệ chạy lâu cũng có thể vượt threshold, nên cần phân biệt leak với usage time hợp lệ.

### 8.3. Test MySQL max_connections

Nếu cần kiểm thử lỗi 1040, dùng một MySQL test server riêng với `max_connections` thấp và tài khoản test. Mở connection có kiểm soát tới giới hạn, xác nhận kết nối tiếp theo bị từ chối, rồi đóng tất cả connection trong cleanup. Không dùng test này trên server dùng chung hoặc môi trường có dữ liệu thật.

Kiểm tra cả giới hạn account bằng `MAX_USER_CONNECTIONS` nếu ứng dụng có resource limit riêng. Phân biệt lỗi 1040 server-wide với lỗi giới hạn account qua exception, error log và trạng thái server.

### 8.4. Test tải toàn hệ thống

Mô phỏng số application replica tối đa và tất cả pool cùng lúc. Đo:

- Tổng connection mở trên MySQL.
- Hikari active/idle/pending trên từng instance.
- Acquire latency và request p95/p99.
- `Threads_running`, CPU, I/O, lock wait và query latency.
- Connection count trong rolling deployment và autoscaling.

Test phải xác minh hệ thống còn headroom cho admin/monitoring và không vượt giới hạn account hoặc server khi scale tới cấu hình tối đa.

## 9. Bảng chẩn đoán nhanh

| Triệu chứng | Khả năng nguyên nhân | Bước kiểm tra tiếp theo |
|---|---|---|
| MySQL trả error 1040 | Server chạm `max_connections` | Xem `Threads_connected`, `Max_used_connections`, process list và `Connection_errors_max_connections` |
| Hikari pool timeout, MySQL còn connection | Pool cạn do active connection bị giữ | Xem active/idle/pending, usage time, leak warning và transaction |
| Chỉ một service bị từ chối kết nối | `MAX_USER_CONNECTIONS` hoặc pool riêng quá lớn | `SHOW CREATE USER`, nhóm process list theo user/host |
| Nhiều Sleep session từ một host | Pool giữ idle connection hoặc connection không được retire | So sánh với số instance và pool size; kiểm tra `wait_timeout`, `maxLifetime` |
| Active tăng liên tục sau mỗi request | Connection leak hoặc transaction không kết thúc | Leak stack trace, code path, `innodb_trx`, application thread dump |
| Pool cạn cùng `Threads_running` cao | Query chậm, lock contention hoặc DB quá tải | Process list, slow query, lock wait và execution plan |
| Lỗi sau deploy/autoscaling | Tổng pool capacity tăng vượt ngân sách | Tính replica tối đa, số DataSource và rolling deployment surge |
| Kết nối mới liên tục sau khi kill session | Pool đang tái tạo connection bị đóng | Dừng kill hàng loạt; xử lý nguồn tạo tải và để pool ổn định |

## 10. Bài thực hành

Một cụm ứng dụng có 8 API pod, mỗi pod dùng HikariCP `maximumPoolSize=25`; 4 worker pod dùng pool tối đa 10 connection. MySQL đặt `max_connections=240`. Trong giờ cao điểm:

- API có lúc báo `Connection is not available, request timed out`.
- MySQL thỉnh thoảng trả error 1040.
- Process list cho thấy nhiều session `Sleep` từ API và một số transaction chạy lâu từ worker.
- Sau rolling deployment, lỗi tăng mạnh.

Hãy điều tra và đề xuất thay đổi:

1. Tính tổng pool capacity hiện tại khi đủ 8 API và 4 worker pod.
2. So sánh tổng đó với `max_connections=240`; còn bao nhiêu chỗ cho monitoring, migration và admin?
3. Nếu rolling deployment tạm thời chạy thêm 3 API pod và 2 worker pod, tổng khả năng mở connection là bao nhiêu?
4. Viết các câu lệnh kiểm tra `Threads_connected`, `Max_used_connections`, `Connection_errors_max_connections` và process list theo user/host.
5. Phân biệt Sleep session bình thường trong pool với connection leak.
6. Những metrics Hikari nào cần lấy từ từng pod để biết pool nào cạn?
7. Xác định vì sao transaction dài ở worker có thể làm API pool timeout dù hai service dùng account khác nhau.
8. Đề xuất cách giảm concurrency và điều tiết worker trong khi vẫn giữ headroom quản trị.
9. Khi nào nên tăng `max_connections`, và cần kiểm tra tài nguyên nào trước khi tăng?
10. Thiết kế test pool exhaustion, leak detection và server-wide 1040 trên môi trường test cô lập.

Một phương án tốt phải tính cả số instance tối đa khi rollout, các pool trong mỗi process, giới hạn account và kết nối ngoài ứng dụng. Hãy nêu tiêu chí xác nhận sau thay đổi: không còn error 1040, pending trở về baseline, acquire latency ổn định và MySQL không bị quá tải.

## 11. Những nhầm lẫn thường gặp

- **Chỉ nhìn `max_connections`:** pool có thể cạn trước khi MySQL chạm giới hạn server.
- **Chỉ nhìn Hikari:** các service khác, migration và công cụ quản trị cũng dùng connection trên MySQL.
- **Kill tất cả Sleep session:** connection idle có thể là tài nguyên pool đang giữ có chủ đích; kill hàng loạt gây reconnect storm.
- **Tăng pool size để chữa pool timeout:** nếu DB đã bão hòa, thêm concurrency có thể làm query chậm hơn.
- **Tăng `max_connections` không đo tài nguyên:** mỗi connection có chi phí bộ nhớ và xử lý; giới hạn lớn không đồng nghĩa server chịu được.
- **Coi leak detection là auto cleanup:** Hikari chỉ cảnh báo connection bị giữ lâu, code vẫn phải đóng resource.
- **Cho rằng `Connection.close()` luôn đóng socket:** trong pool, nó thường trả connection về pool.
- **Giữ transaction khi gọi HTTP:** làm connection và lock bị giữ trong lúc database không làm việc.
- **Quên tính rolling deployment:** số pod tạm thời có thể cao hơn replica count bình thường.
- **Retry dồn dập khi pool cạn:** retry làm tăng áp lực lên pool và MySQL.

## Kết luận

`Too many connections` là giới hạn ở MySQL hoặc account; pool exhaustion là tình trạng ứng dụng không còn connection rảnh để cấp cho request. Muốn xử lý đúng, hãy tính tổng pool capacity của mọi instance, kiểm tra server status và process list, đối chiếu Hikari active/idle/pending, rồi tìm connection bị giữ lâu hoặc query/transaction chậm. Đóng resource đầy đủ, giữ transaction ngắn, điều tiết concurrency và dành headroom cho vận hành. Chỉ tăng `max_connections` sau khi đã đánh giá tài nguyên và ngân sách connection toàn hệ thống.

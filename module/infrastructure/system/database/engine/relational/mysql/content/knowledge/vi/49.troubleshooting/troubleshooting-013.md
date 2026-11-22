# MySQL server has gone away/lost connection và timeout/gói quá lớn

Các lỗi `MySQL server has gone away`, `Lost connection to MySQL server during query` hoặc JDBC `Communications link failure` cho biết client không còn trao đổi được với MySQL trên connection hiện tại. Chúng không chỉ có một nguyên nhân. Server có thể đã đóng connection nhàn rỗi, process MySQL có thể restart hoặc crash, mạng/proxy có thể ngắt socket, client có thể hết thời gian chờ, hoặc một câu lệnh/result packet vượt giới hạn cho phép.

Thông báo `Packet too large` thường liên quan `max_allowed_packet`. Tăng timeout hoặc packet limit một cách tùy tiện có thể che lỗi, làm tăng bộ nhớ sử dụng hoặc kéo dài thời gian giữ connection. Cần xác định connection bị mất ở giai đoạn nào, đối chiếu log client/server, rồi điều chỉnh đúng giới hạn và thiết kế retry an toàn.

## 1. Nhận diện nhóm lỗi

Các thông báo thường gặp:

| Mã/thông báo | Ý nghĩa thường gặp | Hướng điều tra đầu tiên |
|---|---|---|
| `ERROR 2006 (HY000): MySQL server has gone away` | Client gửi lệnh tới connection đã mất hoặc server đã đóng | Idle timeout, server restart/crash, packet quá lớn, connection stale |
| `ERROR 2013 (HY000): Lost connection to MySQL server during query` | Mất kết nối trong khi câu lệnh đang chạy hoặc trả kết quả | Socket/network timeout, server crash, proxy reset, query/result quá lâu |
| `ERROR 1153 (08S01): Got a packet bigger than 'max_allowed_packet' bytes` | Packet vượt giới hạn server hoặc đường truyền của client | Kích thước statement/row/result và packet limit ở hai phía |
| JDBC `CommunicationsException` / `Communications link failure` | Connector/J không trao đổi được với server | Xem SQLState, exception gốc, thời điểm gửi/nhận packet và timeout JDBC |
| `Connection reset`, `Broken pipe`, `EOFException` | Socket bị peer hoặc tầng mạng đóng | Server log, proxy/load balancer, firewall/NAT và pool stale connection |
| `Too many connections` (`1040`) | Server hết slot connection | Pool sizing, `max_connections`, connection leak và số ứng dụng |

Hai mã 2006 và 2013 là triệu chứng ở client, không xác định được nguyên nhân gốc. Ví dụ, 2006 có thể xuất hiện ở lệnh đầu tiên sau một khoảng idle vì server đã đóng session; 2013 có thể xuất hiện khi server đang trả một result set lớn nhưng proxy đã hết idle timeout.

## 2. Phân biệt timeout theo từng lớp

Từ “timeout” có thể chỉ nhiều giới hạn khác nhau. Trước khi sửa, xác định chính xác đồng hồ nào hết hạn:

| Giới hạn | Nơi cấu hình | Đo khoảng thời gian nào? |
|---|---|---|
| `connect_timeout` | MySQL server | Server chờ client gửi gói kết nối ban đầu |
| `connectTimeout` | Connector/J | Client chờ thiết lập kết nối TCP/handshake theo driver |
| `wait_timeout` | MySQL server | Thời gian connection non-interactive không hoạt động trước khi server đóng |
| `interactive_timeout` | MySQL server | Thời gian nhàn rỗi cho client kết nối với cờ interactive |
| `net_read_timeout` | MySQL server | Server chờ thêm dữ liệu từ client trong lúc đọc packet |
| `net_write_timeout` | MySQL server | Server chờ ghi một block dữ liệu tới client |
| `socketTimeout` | Connector/J | Thời gian client chờ dữ liệu đọc từ socket; thường được tính bằng mili giây |
| `connection-timeout` | HikariCP | Thời gian ứng dụng chờ mượn được connection từ pool |
| `Statement.setQueryTimeout()` | JDBC | Giới hạn thời gian thực thi statement theo API JDBC, tính bằng giây |
| `max_execution_time` | MySQL | Giới hạn thời gian thực thi một số câu `SELECT`, tính bằng mili giây |
| `innodb_lock_wait_timeout` | InnoDB | Thời gian chờ row lock |
| `lock_wait_timeout` | MySQL server | Thời gian chờ metadata lock |

Không tăng `wait_timeout` để sửa lỗi `innodb_lock_wait_timeout`, và không tăng `socketTimeout` để xử lý một truy vấn đang bị chặn bởi row lock. Mỗi giới hạn tác động tới một giai đoạn khác nhau.

## 3. Thu thập cấu hình và trạng thái trước khi thay đổi

Chạy các truy vấn sau trên server gặp lỗi:

```sql
SELECT VERSION(), @@version_comment, @@hostname, @@port;

SHOW GLOBAL VARIABLES WHERE Variable_name IN (
  'wait_timeout',
  'interactive_timeout',
  'connect_timeout',
  'net_read_timeout',
  'net_write_timeout',
  'max_allowed_packet',
  'net_buffer_length',
  'max_connections',
  'log_error'
);

SELECT
  @@GLOBAL.max_allowed_packet,
  @@SESSION.max_allowed_packet,
  @@SESSION.wait_timeout,
  @@SESSION.net_read_timeout,
  @@SESSION.net_write_timeout;
```

Giá trị GLOBAL là mặc định hoặc giới hạn cho session mới theo phạm vi biến; session đang tồn tại có thể giữ giá trị đã nhận trước đó. Khi điều tra connection cụ thể, luôn xem `@@SESSION` từ chính connection đó.

Thu thập status counter:

```sql
SHOW GLOBAL STATUS WHERE Variable_name IN (
  'Uptime',
  'Connections',
  'Threads_connected',
  'Threads_running',
  'Max_used_connections',
  'Aborted_clients',
  'Aborted_connects',
  'Bytes_received',
  'Bytes_sent'
);
```

Các counter phần lớn tích lũy từ lúc server khởi động. Ghi lại giá trị trước/sau trong cùng cửa sổ để tính delta; không diễn giải một con số tích lũy như tỷ lệ lỗi hiện tại. `Uptime` giảm mạnh hoặc reset là dấu hiệu server vừa khởi động lại. `Aborted_clients` có thể tăng khi client đóng bất thường hoặc bị ngắt; `Aborted_connects` liên quan kết nối không hoàn tất thành công.

## 4. Connection nhàn rỗi bị đóng bởi wait_timeout

Đây là nguyên nhân phổ biến khi ứng dụng dùng connection pool. MySQL tự đóng connection non-interactive sau một khoảng thời gian không có hoạt động. JDBC thường là non-interactive client, nên `wait_timeout` thường là biến cần kiểm tra.

Ví dụ tình huống:

1. Ứng dụng mở connection và trả nó về HikariCP.
2. Connection nằm idle lâu hơn `wait_timeout` của MySQL hoặc giới hạn idle của proxy/firewall.
3. Server hoặc tầng mạng đóng socket.
4. Pool vẫn giữ đối tượng connection vì chưa biết socket đã chết.
5. Request tiếp theo mượn connection đó và nhận lỗi 2006/2013 khi gửi lệnh.

Kiểm tra:

```sql
SHOW GLOBAL VARIABLES LIKE 'wait_timeout';
SHOW GLOBAL VARIABLES LIKE 'interactive_timeout';
```

Để xem giá trị của session hiện tại:

```sql
SELECT CONNECTION_ID(), @@SESSION.wait_timeout;
```

`wait_timeout` chỉ áp dụng khi connection không hoạt động giữa các lệnh. Một câu `SELECT` đang chạy lâu không tự bị ngắt chỉ vì vượt quá `wait_timeout`. Nếu query đang chạy bị ngắt, hãy xem `socketTimeout`, `net_read_timeout`, `net_write_timeout`, query limit, proxy và server log.

### Đồng bộ vòng đời connection pool

HikariCP có các thuộc tính thường dùng:

- `maxLifetime`: tuổi thọ tối đa của connection trong pool; nên thấp hơn giới hạn tuổi thọ connection do database/proxy áp dụng, có một khoảng đệm.
- `keepaliveTime`: chu kỳ kiểm tra/giữ sống connection idle; phải thấp hơn `maxLifetime` và phù hợp với idle timeout nhỏ nhất trên đường đi.
- `idleTimeout`: thời gian connection dư thừa có thể nằm idle trước khi pool loại bỏ, trong giới hạn cấu hình pool.
- `connectionTimeout`: thời gian request chờ connection được cấp từ pool; không phải timeout truy vấn MySQL.
- `validationTimeout`: thời gian dành cho kiểm tra connection.

Ví dụ cấu hình Spring Boot minh họa:

```yaml
spring:
  datasource:
    hikari:
      connection-timeout: 30000
      validation-timeout: 5000
      max-lifetime: 1500000
      keepalive-time: 120000
```

Các giá trị tính bằng mili giây và chỉ là ví dụ. Hãy chọn `keepalive-time` ngắn hơn idle timeout thực tế của MySQL, proxy, NAT hoặc load balancer; chọn `max-lifetime` ngắn hơn giới hạn tuổi thọ connection của hạ tầng. Không giả định `wait_timeout` là giới hạn duy nhất: proxy có thể đóng socket sớm hơn.

JDBC 4 driver thường hỗ trợ `Connection.isValid()` để pool kiểm tra connection. Không cần cấu hình `connectionTestQuery` nếu driver và pool đã hỗ trợ validation chuẩn, trừ khi có yêu cầu cụ thể. Kiểm tra connection trước khi dùng giúp phát hiện một số socket stale, nhưng không thể loại bỏ hoàn toàn race condition giữa validation và lần thực thi tiếp theo.

## 5. ConnectionTimeout, SocketTimeout và timeout truy vấn trong Connector/J

Connector/J có các thuộc tính kết nối riêng. Ví dụ URL:

```text
jdbc:mysql://db.example.internal:3306/orders?connectTimeout=10000&socketTimeout=60000&tcpKeepAlive=true
```

- `connectTimeout=10000`: giới hạn chờ kết nối/handshake phía client khoảng 10 giây.
- `socketTimeout=60000`: giới hạn chờ đọc dữ liệu từ socket khoảng 60 giây.
- `tcpKeepAlive=true`: yêu cầu TCP keepalive ở socket; thời điểm probe thực tế còn phụ thuộc cấu hình OS.

Đơn vị của hai thuộc tính timeout trong Connector/J là mili giây. Giá trị `0` thường có nghĩa không giới hạn theo thuộc tính đó; hãy kiểm tra tài liệu đúng phiên bản driver.

`socketTimeout` không phải giới hạn thời gian SQL ở server. Nếu query hợp lệ cần 90 giây nhưng client đặt `socketTimeout=60000`, client có thể đóng socket ở giây thứ 60 dù MySQL vẫn đang thực thi. Server có thể tiếp tục làm việc một khoảng thời gian trước khi nhận ra client đã ngắt. Chọn timeout dựa trên SLO, thời gian query được phép và timeout ở proxy; không đặt quá thấp để chỉ làm lỗi xuất hiện nhanh hơn.

### Hikari connection-timeout khác Connector/J connectTimeout

Hai thuộc tính dễ bị nhầm:

- Hikari `connectionTimeout`: thời gian chờ lấy connection từ pool. Pool hết connection hoặc tất cả connection đang bận có thể khiến request chờ hết giới hạn này.
- Connector/J `connectTimeout`: thời gian tạo một physical connection mới tới MySQL.

Nếu log cho biết Hikari timeout khi chờ pool, kiểm tra leak, transaction giữ connection lâu, pool size và DB saturation. Tăng `connectTimeout` sẽ không giải quyết tình trạng không còn connection rảnh trong pool.

### Query timeout là một lớp khác

JDBC có thể đặt timeout cho statement:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT id, status FROM orders WHERE customer_id = ?")) {
    ps.setLong(1, customerId);
    ps.setQueryTimeout(20); // giây

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Đọc kết quả
        }
    }
}
```

`setQueryTimeout()` yêu cầu driver giới hạn thời gian thực thi statement. Cách driver gửi cancel và độ chính xác của timeout phụ thuộc implementation. Với MySQL, có thể dùng `max_execution_time` hoặc optimizer hint `MAX_EXECUTION_TIME` cho SELECT khi cần chính sách phía server:

```sql
SET SESSION max_execution_time = 20000;

SELECT /*+ MAX_EXECUTION_TIME(20000) */ id, status
FROM orders
WHERE customer_id = 501;
```

Giá trị tính bằng mili giây. `max_execution_time` áp dụng cho SELECT theo phạm vi MySQL hỗ trợ; nó không thay thế timeout cho mọi loại statement hoặc thời gian chờ connection pool.

## 6. net_read_timeout và net_write_timeout

Hai biến này liên quan việc MySQL trao đổi dữ liệu với client:

- `net_read_timeout`: số giây server chờ đọc thêm dữ liệu từ client trước khi bỏ kết nối. Có thể liên quan client gửi packet chậm, upload dữ liệu hoặc mạng không ổn định.
- `net_write_timeout`: số giây server chờ ghi một block dữ liệu tới client trước khi bỏ kết nối. Có thể liên quan client đọc result set chậm, mạng nghẽn hoặc proxy không chuyển tiếp dữ liệu.

Kiểm tra:

```sql
SHOW VARIABLES LIKE 'net_read_timeout';
SHOW VARIABLES LIKE 'net_write_timeout';
```

Nếu upload BLOB lớn hoặc gửi batch qua mạng chậm, xem `net_read_timeout` và tốc độ gửi thực tế. Nếu query trả hàng triệu dòng và ứng dụng đọc từng dòng rất chậm, xem `net_write_timeout`, fetch strategy và thời gian client tiêu thụ result set.

Không tăng hai biến này nếu nguyên nhân là query plan xấu hoặc client không đóng result set. Một timeout dài hơn có thể khiến server giữ thread/connection lâu hơn mà không cải thiện throughput.

## 7. max_allowed_packet và lỗi packet quá lớn

MySQL truyền dữ liệu theo packet. `max_allowed_packet` giới hạn kích thước packet mà server hoặc client chấp nhận. Packet quá lớn có thể khiến MySQL trả lỗi `ER_NET_PACKET_TOO_LARGE` (1153) và đóng connection. Client cũng có thể có giới hạn riêng; tăng server limit không tự tăng giới hạn của mọi driver/tool.

Các trường hợp dễ tạo packet lớn:

- Một câu `INSERT` nhiều dòng được ghép thành statement rất dài.
- Một cột `BLOB`, `MEDIUMBLOB`, `LONGBLOB`, JSON hoặc TEXT chứa payload lớn.
- Batch JDBC được rewrite thành một câu SQL lớn.
- Một hàng trả về có trường lớn hoặc result set chứa nhiều dữ liệu.
- Ứng dụng gửi một danh sách `IN (...)` quá dài thay vì chia nhóm hoặc dùng bảng tạm.

Kiểm tra giá trị global và session:

```sql
SHOW GLOBAL VARIABLES LIKE 'max_allowed_packet';
SELECT @@GLOBAL.max_allowed_packet, @@SESSION.max_allowed_packet;
```

`max_allowed_packet` có thể cấu hình tới 1 GB trong các phiên bản MySQL hiện hành, nhưng không có nghĩa nên đặt mặc định ở mức đó. Mức lớn làm tăng giới hạn bộ nhớ có thể cần cho packet và có thể tạo rủi ro khi nhiều client đồng thời gửi payload lớn. Giá trị mặc định cũng thay đổi theo phiên bản và loại client; luôn đọc cấu hình thực tế.

### Tăng packet limit có kiểm soát

Ví dụ tăng server global lên 64 MiB:

```sql
SET GLOBAL max_allowed_packet = 67108864;
```

Thay đổi GLOBAL thường ảnh hưởng các session mới. Hãy mở connection mới và kiểm tra `@@SESSION.max_allowed_packet`. Nếu cần đặt session cụ thể và phiên bản hỗ trợ phạm vi SESSION, có thể đặt trong session đó:

```sql
SET SESSION max_allowed_packet = 67108864;
```

Để giữ cấu hình sau restart, quản lý biến trong file cấu hình MySQL hoặc cơ chế cấu hình được tổ chức sử dụng, sau khi đã kiểm thử. Đồng thời kiểm tra giới hạn ở client, Connector/J, proxy và công cụ import/export. Với MySQL command-line client, có thể cấu hình `--max_allowed_packet` theo tài liệu của đúng phiên bản.

Không đặt server limit lớn hơn mức cần thiết nếu ứng dụng vẫn tạo statement không giới hạn. Hãy đo kích thước payload thực tế và thêm giới hạn ở tầng API/ứng dụng.

## 8. Chia batch và xử lý BLOB/result set lớn

Nếu một transaction gửi hàng chục nghìn dòng trong một câu insert, hãy xem lại kích thước batch. Chia batch theo số dòng và tổng byte ước tính, không chỉ theo số dòng cố định. Một batch 500 dòng có thể nhỏ với vài cột số nhưng quá lớn nếu mỗi dòng chứa JSON/BLOB vài trăm KB.

Với JDBC batch:

```java
connection.setAutoCommit(false);

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO import_item (external_id, payload) VALUES (?, ?)")) {
    int batchSize = 0;

    for (ImportItem item : items) {
        ps.setString(1, item.externalId());
        ps.setBytes(2, item.payload());
        ps.addBatch();
        batchSize++;

        if (batchSize == 200) {
            ps.executeBatch();
            connection.commit();
            batchSize = 0;
        }
    }

    if (batchSize > 0) {
        ps.executeBatch();
        connection.commit();
    }
} catch (SQLException e) {
    connection.rollback();
    throw e;
} finally {
    connection.setAutoCommit(true);
}
```

Ví dụ minh họa cách chia batch; code production cần bảo đảm rollback/restore connection state an toàn và không dùng connection đã hỏng. Nếu một batch commit thành công rồi batch sau thất bại, dữ liệu trước đó vẫn đã commit. Dùng batch ID, unique key hoặc idempotency key để retry không tạo duplicate.

Khi dùng `rewriteBatchedStatements=true` trong Connector/J, driver có thể gộp các lệnh batch thành statement lớn hơn để tăng hiệu năng. Điều này có thể làm packet lớn hơn; thử nghiệm với payload thực tế và điều chỉnh batch size phù hợp.

Với BLOB lớn, cân nhắc `setBinaryStream()`/`setCharacterStream()` để tránh tự tạo thêm bản sao lớn trong heap ứng dụng, nhưng kiểm tra driver có buffer dữ liệu hay không và giới hạn packet vẫn áp dụng. Với file rất lớn, lưu nội dung trong object storage rồi lưu metadata/URI trong MySQL có thể phù hợp hơn.

`LOAD DATA LOCAL INFILE` thường phù hợp cho nạp file hàng loạt và truyền dữ liệu theo luồng của giao thức. Không nên hiểu rằng cả file luôn phải nằm trong một packet duy nhất; vẫn cần kiểm tra giới hạn, cấu hình client/server và lỗi thực tế.

### Đọc result set lớn

Nếu truy vấn trả nhiều dòng hoặc mỗi dòng có payload lớn, tránh tải toàn bộ result set vào bộ nhớ khi không cần. Connector/J có các cách dùng cursor/fetch theo phiên bản, ví dụ cấu hình `useCursorFetch=true` cùng fetch size dương cho server-side cursor. Kiểm tra driver version và cách triển khai cụ thể.

Đọc result set chậm có thể làm server phải giữ connection và tiếp tục gửi dữ liệu lâu. Luôn đóng `ResultSet`, `Statement` và trả connection về pool; nếu stream kết quả, tiêu thụ hoặc đóng stream trước khi chạy câu lệnh tiếp theo trên connection đó.

## 9. Server restart, crash hoặc bị hệ điều hành kill

Nếu process MySQL dừng, mọi connection đang mở đều mất. Client thường thấy 2006, 2013, `Connection reset` hoặc lỗi JDBC ở thời điểm server restart.

Các nguyên nhân thường gặp:

- Restart có kế hoạch, deploy hoặc thay cấu hình.
- MySQL crash do lỗi phần mềm, assertion hoặc lỗi storage.
- Hệ điều hành kill process do OOM.
- Container bị restart, reschedule hoặc health check thất bại.
- Host reboot, storage/network bị gián đoạn.
- Quản trị viên hoặc automation kill connection/process.

Kiểm tra:

```sql
SHOW GLOBAL STATUS LIKE 'Uptime';
SHOW VARIABLES LIKE 'log_error';
```

Đọc MySQL error log tại đường dẫn cấu hình, log service/container và log kernel/host. Tìm dấu hiệu `ready for connections`, shutdown, crash recovery, out-of-memory killer, disk full, I/O error hoặc signal. `Uptime` chỉ giúp nhận ra restart; error log mới thường cho biết nguyên nhân.

Nếu MySQL chạy trong container, kiểm tra restart count, exit code, container logs, memory limit, volume health và orchestration events. Không chỉ kiểm tra trạng thái container hiện tại; container có thể đã restart và đang healthy trở lại trong khi ứng dụng vẫn giữ socket cũ.

Nếu lỗi xảy ra đúng lúc một truy vấn nặng, kiểm tra query có làm tăng memory, temporary table, sort hoặc scan; đối chiếu log OOM/crash và tài nguyên host. Không kết luận query là nguyên nhân chỉ vì thời điểm trùng nhau.

## 10. Network, firewall, NAT và proxy

Connection TCP có thể bị ngắt bởi nhiều tầng giữa ứng dụng và MySQL:

- Firewall/NAT xóa connection idle sau một khoảng thời gian.
- Load balancer hoặc proxy có idle timeout riêng.
- ProxySQL hoặc dịch vụ database proxy đóng connection do giới hạn pool hoặc trạng thái backend.
- Network packet loss, TCP reset, route change hoặc DNS chuyển sang địa chỉ khác.
- TLS middlebox hoặc chứng thư hết hạn làm handshake thất bại với kết nối mới.

Nếu connection lỗi sau một khoảng idle gần như cố định nhưng MySQL `wait_timeout` lớn hơn, hãy kiểm tra timeout của proxy/firewall/NAT. Nếu chỉ một subnet hoặc một AZ gặp lỗi, kiểm tra route, security group, DNS và network telemetry.

`tcpKeepAlive=true` bật TCP keepalive ở socket client, nhưng chu kỳ probe do hệ điều hành quyết định và có thể dài hơn idle timeout của hạ tầng. Nó không thay thế keepalive ở tầng ứng dụng/pool. Một query đang truyền dữ liệu thường xuyên cũng khác với connection hoàn toàn idle.

`mysqladmin ping` có thể xác nhận server trả lời một kết nối mới, nhưng không chứng minh connection cũ trong pool còn hợp lệ. Cần kiểm tra connection được mượn từ pool và xem log proxy/network ở đúng thời điểm lỗi.

## 11. Connection pool và cách loại bỏ connection hỏng

Khi một JDBC connection gặp lỗi giao tiếp, không tiếp tục dùng nó cho statement kế tiếp. Đóng/evict connection vật lý và để pool tạo connection mới. Với HikariCP, exception do driver cung cấp có thể giúp pool nhận diện connection broken; tuy nhiên, ứng dụng cần đóng connection đúng cách và không giữ reference để tái sử dụng.

Các nguyên tắc:

- Dùng try-with-resources cho `Connection`, `PreparedStatement` và `ResultSet` theo đúng quyền sở hữu.
- Không giữ connection trong field singleton hoặc qua nhiều request.
- Không giữ transaction mở trong lúc gọi API bên ngoài hoặc chờ người dùng.
- Đặt pool size dựa trên khả năng chịu tải của MySQL, không chỉ số thread ứng dụng.
- Dùng keepalive và max lifetime phù hợp với timeout của database/proxy.
- Theo dõi active, idle, pending và timeout của pool.
- Sau lỗi network, loại connection hỏng; không chỉ chạy `SELECT 1` trên cùng socket đã biết là lỗi.

Không dựa vào `autoReconnect` như cách khôi phục transaction. Reconnect tạo session mới, mất transaction, session variables, temporary table, user variables và trạng thái lock của connection cũ. Connector/J hiện đại không khuyến nghị dựa vào auto-reconnect cho ứng dụng giao dịch; hãy để pool cấp connection mới ở ranh giới transaction.

## 12. Retry an toàn khi connection bị mất

Mất kết nối ở giữa transaction có hai tình huống khác nhau:

- **Chưa commit:** server có thể rollback transaction khi phát hiện connection đóng, nhưng client không nên giả định đã biết chắc trạng thái nếu lỗi xảy ra đúng lúc truyền lệnh.
- **Đang commit hoặc vừa gửi COMMIT:** client có thể không nhận được phản hồi dù server đã commit thành công. Đây là kết quả không xác định từ góc nhìn client.

Vì vậy, không retry mù quáng một thao tác ghi không idempotent. Ví dụ, gửi lại lệnh tạo đơn có thể tạo hai đơn nếu lần đầu đã commit nhưng response bị mất.

### Dùng idempotency key

Tạo một request ID ổn định từ client hoặc tầng nghiệp vụ, lưu nó với unique constraint:

```sql
CREATE TABLE payment_requests (
  request_id BINARY(16) NOT NULL,
  payment_id BIGINT UNSIGNED NOT NULL,
  amount DECIMAL(14,2) NOT NULL,
  status VARCHAR(20) NOT NULL,
  PRIMARY KEY (request_id),
  UNIQUE KEY uq_payment_id (payment_id)
) ENGINE=InnoDB;
```

Khi retry, dùng cùng `request_id`. Nếu lần đầu đã commit, ứng dụng tìm thấy request đã tồn tại và trả kết quả đã lưu thay vì tạo payment mới. Nếu chưa tồn tại, có thể thực hiện lại theo transaction đã thiết kế. Quy tắc xử lý xung đột phải xác minh dữ liệu request trùng khớp, không chỉ bỏ qua lỗi duplicate.

### Quy trình xử lý kết quả COMMIT không rõ

1. Đánh dấu thao tác có kết quả chưa xác định; không phát lại ngay với ID mới.
2. Mở connection mới từ pool.
3. Tra cứu theo idempotency key hoặc business key duy nhất.
4. Nếu giao dịch đã tồn tại và ở trạng thái thành công, trả lại kết quả đó.
5. Nếu chưa tồn tại, chạy lại transaction với cùng key.
6. Nếu trạng thái còn pending, dùng quy trình reconciliation để xác định kết quả trước khi thử lại.

Retry chỉ nên áp dụng cho lỗi tạm thời đã phân loại, có giới hạn số lần, exponential backoff và jitter. Không retry lỗi SQL logic như duplicate do dữ liệu sai, permission denied hoặc syntax error.

## 13. Chẩn đoán theo thời điểm xảy ra lỗi

Thời điểm lỗi giúp thu hẹp nguyên nhân:

| Thời điểm | Nguyên nhân cần ưu tiên kiểm tra |
|---|---|
| Ngay khi mở connection | DNS/TCP, `connectTimeout`, `connect_timeout`, TLS, server quá tải hoặc `max_connections` |
| Lệnh đầu tiên sau thời gian idle | `wait_timeout`, proxy/NAT idle timeout, pool stale connection |
| Trong lúc gửi dữ liệu lớn | `max_allowed_packet`, `net_read_timeout`, client packet limit và tốc độ upload |
| Trong lúc query chạy lâu | `socketTimeout`, query execution limit, server crash/restart, network hoặc proxy timeout |
| Khi đọc result set lớn | `net_write_timeout`, socket timeout, client đọc chậm, fetch/buffering và packet lớn |
| Đúng lúc commit | Network interruption và kết quả commit không xác định; cần idempotency/reconciliation |
| Chỉ khi concurrency cao | Hết connection, pool queue, memory pressure, lock contention hoặc saturation |
| Theo chu kỳ cố định | Timeout hạ tầng, job restart, rotation/deploy hoặc lifetime connection |

Đừng chỉ nhìn stack trace cuối cùng. Thu thập exception chain, SQLState, vendor error code, thời điểm request, connection ID nếu có, query/digest, trạng thái pool và server log cùng timestamp.

## 14. Runbook điều tra theo thứ tự

Khi sự cố xảy ra, thực hiện theo trình tự để giữ được bằng chứng:

**Bước 1 — Xác định phạm vi.** Một ứng dụng, một node, một AZ hay toàn bộ client đều lỗi? Chỉ connection cũ lỗi hay kết nối mới cũng không mở được? Lỗi xuất hiện sau idle, khi upload, trong query hay khi đọc kết quả?

**Bước 2 — Thu thập lỗi phía client.** Ghi vendor code, SQLState, exception chain, thời gian từ lần packet cuối, URL/driver version và pool metrics. Che password, token và dữ liệu nhạy cảm khỏi log.

**Bước 3 — Kiểm tra server.** Xác nhận MySQL đang chạy, xem `Uptime`, `max_connections`, error log, crash/OOM và dung lượng disk. Kiểm tra `Aborted_clients`, `Aborted_connects` theo delta.

**Bước 4 — Kiểm tra timeout.** Đối chiếu `wait_timeout`, `net_read_timeout`, `net_write_timeout`, Connector/J `connectTimeout`/`socketTimeout`, Hikari timeout và idle timeout của proxy.

**Bước 5 — Kiểm tra packet.** Ước lượng kích thước statement, row, BLOB/JSON và result; so sánh với `max_allowed_packet` ở server, session và client. Kiểm tra batch rewriting.

**Bước 6 — Kiểm tra network.** Đối chiếu TCP reset, firewall/NAT, load balancer, proxy, DNS và TLS log ở đúng timestamp.

**Bước 7 — Phục hồi có kiểm soát.** Evict connection hỏng, reconnect ở ranh giới transaction, xác minh trạng thái ghi theo idempotency key và chỉ retry thao tác an toàn.

**Bước 8 — Xác minh sau sửa.** Chạy lại kịch bản idle, query dài, payload lớn và pool load; theo dõi lỗi, latency, connection churn và resource utilization.

## 15. Ma trận triệu chứng và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Lỗi ngay sau vài phút idle | MySQL/proxy đóng connection nhàn rỗi | Đo idle timeout nhỏ nhất; cấu hình Hikari keepalive/maxLifetime hoặc loại idle connection |
| `2006` ngay sau server restart | Connection cũ trỏ tới process đã dừng | Xem error log/uptime; evict connection và reconnect |
| `2013` sau thời gian query gần bằng socket timeout | Connector/J đóng socket do read timeout | Đánh giá query duration và SLO; điều chỉnh socketTimeout hợp lý hoặc tối ưu query |
| Lỗi khi gửi BLOB/JSON | Packet vượt giới hạn | Đo payload, kiểm tra cả client/server max packet, chia payload hoặc stream |
| Lỗi khi JDBC batch lớn | Statement sau rewrite quá lớn | Giảm batch size theo byte, kiểm tra `rewriteBatchedStatements`, tăng packet limit có kiểm soát |
| Lỗi khi client tải nhiều dòng | Server ghi chậm hoặc client tiêu thụ result set chậm | Dùng pagination/cursor fetch, đóng result set, kiểm tra `net_write_timeout` và socket timeout |
| Hikari báo connection timeout | Pool không cấp được connection trong giới hạn | Kiểm tra pending/active, leak, transaction duration và MySQL capacity |
| `Too many connections` | Pool tổng cộng vượt khả năng server | Tính tổng pool mọi instance, giảm connection dư và tối ưu concurrency |
| Lỗi sau proxy nhưng MySQL vẫn healthy | Proxy/NAT đã đóng socket | Kiểm tra timeout và log proxy; cấu hình keepalive hoặc connection lifetime phù hợp |
| Không rõ lần ghi trước đã commit chưa | Mất response trong lúc commit | Tra cứu idempotency key/business key trước khi retry |

## 16. Tình huống thực hành

Một dịch vụ Spring Boot dùng HikariCP kết nối MySQL qua proxy. Ban ngày request bình thường; sau giờ ít tải, request đầu tiên của một số instance thỉnh thoảng lỗi `Communications link failure`. Một job import khác lại lỗi `Packet too large` khi batch chứa JSON lớn.

**Phần A — Connection idle:**

1. Ghi timestamp lần query cuối và lần lỗi đầu tiên sau idle.
2. Đọc `@@SESSION.wait_timeout`, `@@GLOBAL.wait_timeout` và cấu hình idle timeout của proxy.
3. So sánh khoảng idle thực tế với `keepaliveTime` và `maxLifetime` của Hikari.
4. Kiểm tra pool có connection stale, số lần validation fail và log proxy.
5. Đặt keepalive nhỏ hơn timeout idle thấp nhất, max lifetime thấp hơn giới hạn tuổi thọ connection và kiểm thử qua một khoảng idle dài hơn trước đây.

**Phần B — Packet quá lớn:**

1. Ghi kích thước JSON lớn nhất và kích thước statement sau khi batch được ghép.
2. So sánh `@@SESSION.max_allowed_packet`, `@@GLOBAL.max_allowed_packet` và giới hạn client/driver.
3. Giảm batch theo tổng byte thay vì chỉ số dòng.
4. Nếu payload hợp lệ vẫn vượt giới hạn, tăng packet limit vừa đủ trên server và client, rồi tạo connection mới để xác minh.
5. Kiểm thử payload biên, concurrency và memory; bảo đảm ứng dụng từ chối payload vượt giới hạn nghiệp vụ.

**Phần C — An toàn khi retry:**

1. Gắn `import_batch_id` và khóa duy nhất cho mỗi dòng nguồn.
2. Sau lỗi connection, mở connection mới và kiểm tra batch đã commit tới đâu.
3. Chỉ chạy lại phần chưa hoàn tất bằng cùng batch ID.
4. Đối soát số dòng thành công, bị từ chối và đang chờ xử lý.

Kết quả mong muốn là connection pool không tái sử dụng socket đã bị đóng, batch import có giới hạn kích thước rõ ràng và retry không tạo dữ liệu trùng.

## 17. Checklist phòng ngừa

- [ ] Đã ghi nhận MySQL, Connector/J, pool, proxy và OS/network timeout.
- [ ] Đã phân biệt `wait_timeout`, `connect_timeout`, `net_read_timeout`, `net_write_timeout` và `socketTimeout`.
- [ ] Hikari `connectionTimeout` được hiểu là thời gian chờ pool, không phải query timeout.
- [ ] `maxLifetime` và `keepaliveTime` phù hợp với giới hạn nhỏ nhất của DB/proxy/NAT.
- [ ] Pool không giữ connection trong transaction hoặc tác vụ bên ngoài quá lâu.
- [ ] Có metric pool active/idle/pending, validation failure và connection creation.
- [ ] Đã đo kích thước statement, row, BLOB/JSON và result set lớn nhất.
- [ ] Packet limit ở server, session, client và driver được kiểm tra đồng bộ.
- [ ] Batch được giới hạn theo tổng byte và có checkpoint/idempotency key.
- [ ] Result set, statement và connection được đóng đúng cách.
- [ ] Error log, uptime, OOM, restart và network reset có thể đối chiếu theo timestamp.
- [ ] Không dùng auto-reconnect để giả định transaction được phục hồi.
- [ ] Retry có giới hạn, backoff và cơ chế xác minh kết quả commit không rõ.
- [ ] Có kiểm thử idle, query dài, payload lớn, concurrency và failover trên môi trường riêng.

## 18. Tài liệu hóa sự cố để lần sau xử lý nhanh hơn

Sau khi khắc phục, lưu lại:

- Thông báo lỗi đầy đủ, vendor code, SQLState và driver version.
- Thời điểm, connection ID, endpoint và node ứng dụng gặp lỗi.
- Khoảng idle hoặc thời gian query trước khi lỗi xảy ra.
- Giá trị timeout và packet limit ở server, client, pool và proxy.
- MySQL error log, container/service log, network event và pool metrics.
- Kích thước payload, batch size, số dòng và query digest liên quan.
- Transaction có thể đã commit hay không và cách reconciliation được thực hiện.
- Thay đổi cấu hình/code cùng kết quả kiểm thử sau sửa.

Không lưu password, token, dữ liệu cá nhân hoặc toàn bộ payload nhạy cảm vào runbook. Chỉ giữ metadata và mẫu đã được ẩn danh cần thiết để tái hiện vấn đề.

`MySQL server has gone away` và `Lost connection` là dấu hiệu mất đường giao tiếp, còn timeout và packet-too-large chỉ ra những giới hạn khác nhau trong đường đi của request. Xác định connection bị ngắt khi idle, khi gửi dữ liệu, trong lúc server thực thi hay khi trả kết quả sẽ giúp chọn đúng biện pháp: căn chỉnh pool lifetime, sửa timeout ở đúng lớp, chia batch theo byte, tăng packet limit có kiểm soát hoặc xử lý server/network restart. Với thao tác ghi, luôn xác minh kết quả commit trước khi retry để tránh tạo dữ liệu trùng.

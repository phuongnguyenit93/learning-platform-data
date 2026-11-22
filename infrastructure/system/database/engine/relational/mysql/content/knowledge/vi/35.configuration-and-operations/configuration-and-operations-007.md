# Quản lý max_connections, timeout và giới hạn tài nguyên phiên

MySQL cần giới hạn số kết nối đồng thời và thời gian một phiên được phép chờ để bảo vệ tài nguyên máy chủ. Nếu max_connections quá thấp, ứng dụng có thể gặp lỗi 1040 khi tải tăng. Nếu đặt quá cao mà không tính bộ nhớ, thread, file descriptor và connection pool, máy chủ có thể cạn tài nguyên trước khi đạt ngưỡng kết nối. Timeout quá ngắn làm rớt kết nối hợp lệ; timeout quá dài có thể giữ phiên nhàn rỗi, transaction mở hoặc lock lâu hơn cần thiết.

Quản lý kết nối vì thế phải nhìn đồng thời vào MySQL server, tài khoản database, connection pool của ứng dụng và giới hạn của hệ điều hành. Các biến max_connections, max_user_connections, wait_timeout, connect_timeout, net_read_timeout, net_write_timeout, max_execution_time và các giới hạn tài nguyên theo tài khoản giải quyết những tình huống khác nhau; không thể thay thế tất cả bằng một con số timeout duy nhất.

Trong module DATABASE_MYSQL, mục tiêu là tính được ngân sách kết nối, chọn timeout theo loại chờ, giới hạn tài nguyên theo account, theo dõi mức sử dụng và thay đổi cấu hình có kiểm soát. Các ví dụ hướng tới MySQL 8.0; những biến chỉ có ở một bản minor được ghi rõ để tránh áp dụng nhầm lên server cũ.

## Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt tổng số kết nối đồng thời với giới hạn kết nối của từng account.
- Đọc và thay đổi max_connections ở runtime và cấu hình bền vững.
- Tính ngân sách kết nối từ số instance ứng dụng, pool size và workload nền.
- Hiểu tác động của mỗi connection lên thread, memory, file descriptor và scheduler.
- Phân biệt handshake timeout, idle timeout, network read/write timeout và query timeout.
- Quản lý wait_timeout, interactive_timeout, connect_timeout, net_read_timeout và net_write_timeout.
- Dùng giới hạn tài nguyên theo account: MAX_USER_CONNECTIONS, MAX_CONNECTIONS_PER_HOUR, MAX_QUERIES_PER_HOUR và MAX_UPDATES_PER_HOUR.
- Phân biệt timeout chờ metadata lock, InnoDB row lock và thời gian chạy SELECT.
- Nhận diện các buffer được cấp phát theo session hoặc theo operation.
- Theo dõi connection saturation bằng status variables, Performance Schema và process list.
- Cấu hình connection pool để tránh connection storm và stale connection.
- Thay đổi cấu hình bằng SET GLOBAL, SET PERSIST và option file đúng cách.
- Xử lý lỗi Too many connections và thiết kế đường truy cập quản trị khi server gần cạn kết nối.

## 1. Bản đồ giới hạn kết nối và timeout

Một kết nối MySQL đi qua nhiều giai đoạn. Mỗi giai đoạn có một loại giới hạn riêng:

| Giai đoạn | Giới hạn thường dùng | Ý nghĩa |
|---|---|---|
| Client mở kết nối và handshake | connect_timeout | Server chờ client gửi connect packet/hoàn tất bước đầu của handshake |
| Số phiên đồng thời toàn server | max_connections | Trần tổng số client connections đồng thời |
| Số phiên đồng thời theo account | max_user_connections, MAX_USER_CONNECTIONS | Giới hạn connection của một account |
| Phiên đã kết nối nhưng idle | wait_timeout, interactive_timeout | Đóng phiên không có hoạt động trong khoảng thời gian quy định |
| Client đang gửi dữ liệu | net_read_timeout | Server chờ thêm dữ liệu từ client |
| Server đang gửi kết quả | net_write_timeout | Server chờ ghi dữ liệu tới client |
| Câu lệnh SELECT đang chạy | max_execution_time | Giới hạn thời gian chạy của read-only SELECT, tính bằng millisecond |
| Chờ metadata lock | lock_wait_timeout | Giới hạn thời gian chờ metadata lock |
| Chờ InnoDB row lock | innodb_lock_wait_timeout | Giới hạn thời gian chờ row lock của InnoDB |

Không dùng wait_timeout để giải quyết một truy vấn SELECT chạy quá lâu. Không dùng max_execution_time để sửa lỗi handshake. Hãy xác định chính xác phiên đang chờ ở giai đoạn nào trước khi thay đổi biến.

~~~mermaid
flowchart TD
    A[Application opens connection] --> B{Server has connection capacity?}
    B -- No --> X[Error 1040: Too many connections]
    B -- Yes --> C[Handshake]
    C --> D{Handshake completes in time?}
    D -- No --> Y[connect_timeout]
    D -- Yes --> E[Authenticated session]
    E --> F{Session idle?}
    F -- Yes --> G[wait_timeout / interactive_timeout]
    F -- No --> H[Client sends request]
    H --> I{Network transfer stalls?}
    I -- Client to server --> J[net_read_timeout]
    I -- Server to client --> K[net_write_timeout]
    I -- No --> L[Statement executes]
    L --> M{SELECT exceeds execution limit?}
    M -- Yes --> N[max_execution_time]
    M -- No --> O[Result returned]
~~~

## 2. max_connections: giới hạn toàn server

max_connections là số client connections đồng thời tối đa mà MySQL server chấp nhận. Đây là giới hạn tổng của server, áp dụng cho tất cả ứng dụng và account cùng kết nối tới instance đó.

Khi đã đạt ngưỡng, kết nối mới thường nhận lỗi:

~~~text
ERROR 1040 (HY000): Too many connections
~~~

max_connections không phải số request đồng thời của ứng dụng và cũng không phải số query được chạy song song. Một session có thể đang chạy query, chờ lock hoặc ngủ ở trạng thái Sleep. Tất cả vẫn chiếm một connection cho tới khi disconnect.

### 2.1. Kiểm tra giá trị hiện tại

~~~sql
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SHOW GLOBAL STATUS LIKE 'Max_used_connections';
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Threads_running';
~~~

- max_connections: trần kết nối đồng thời hiện tại.
- Max_used_connections: số kết nối đồng thời cao nhất đã quan sát kể từ khi server khởi động hoặc lần reset status liên quan.
- Threads_connected: số session đang kết nối tại thời điểm lấy mẫu.
- Threads_running: số thread không ở trạng thái ngủ; không đồng nghĩa với số CPU core hoặc số query đang tiêu thụ CPU.

Tỷ lệ sử dụng tại thời điểm lấy mẫu có thể ước tính:

~~~text
connection_utilization = Threads_connected / max_connections
peak_utilization       = Max_used_connections / max_connections
~~~

Đừng chỉ nhìn một snapshot. Ghi nhận các giá trị theo thời gian, giờ cao điểm, sau deploy và khi batch job chạy.

### 2.2. Thay đổi runtime

Nếu biến hỗ trợ dynamic change và tài khoản có quyền quản trị biến hệ thống:

~~~sql
SET GLOBAL max_connections = 300;

SHOW GLOBAL VARIABLES LIKE 'max_connections';
~~~

Thay đổi này áp dụng cho server đang chạy nhưng không tự lưu thành cấu hình sau restart. Giá trị thực tế có thể bị giới hạn bởi khả năng hệ điều hành hoặc cấu hình build; luôn đọc lại biến sau khi thay đổi.

### 2.3. Lưu cấu hình qua restart

Có thể lưu trong option file của MySQL, trong section [mysqld]:

~~~ini
[mysqld]
max_connections = 300
~~~

Hoặc với MySQL 8.0, dùng SET PERSIST nếu biến cho phép persist:

~~~sql
SET PERSIST max_connections = 300;
~~~

SET PERSIST cập nhật biến global runtime và lưu giá trị bền vững trong cấu hình do MySQL quản lý. SET PERSIST_ONLY chỉ ghi giá trị bền vững để áp dụng khi server khởi động lại, không đổi giá trị runtime hiện tại.

~~~sql
SET PERSIST_ONLY max_connections = 350;
~~~

Không sửa trực tiếp file mysqld-auto.cnf; dùng lệnh SET PERSIST/RESET PERSIST để MySQL quản lý cấu hình persisted. Trước khi persist, kiểm tra thay đổi có phù hợp với memory budget, OS limits và cấu hình triển khai hay không.

### 2.4. Kết nối quản trị dự phòng

MySQL dành một kết nối bổ sung cho tài khoản có quyền quản trị phù hợp để hỗ trợ xử lý khi số kết nối thông thường đã chạm max_connections. Từ MySQL 8.0.14, quyền CONNECTION_ADMIN được dùng cho cơ chế này; các phiên bản cũ có thể dùng SUPER theo cơ chế cũ.

Không cấp CONNECTION_ADMIN cho tài khoản ứng dụng thông thường. Hãy giữ một tài khoản vận hành riêng, có xác thực mạnh và quyền tối thiểu cần thiết. Một số triển khai có thể cấu hình giao diện quản trị riêng qua admin_address/admin_port; đây là lựa chọn triển khai bổ sung, không thay thế việc kiểm soát quyền.

## 3. Tính ngân sách kết nối trước khi tăng giới hạn

Không đặt max_connections bằng cách lấy một con số lớn tùy ý. Tính số kết nối có thể mở từ tất cả thành phần:

~~~text
total_pool_connections =
    sum(application_instances * pool_max_size)
  + background_workers
  + scheduled_jobs
  + migration_and_reporting_clients
  + monitoring_and_admin_connections
~~~

Ví dụ:

| Thành phần | Số instance | Pool tối đa mỗi instance | Tổng |
|---|---:|---:|---:|
| API service | 6 | 20 | 120 |
| Worker service | 3 | 8 | 24 |
| Reporting | 1 | 10 | 10 |
| Scheduler | 1 | 4 | 4 |
| Migration/monitoring/admin | — | — | 12 |
| **Tổng có thể mở** | | | **170** |

Nếu cấu hình server là 180, headroom chỉ còn 10 connection. Một đợt rolling deployment có thể chạy đồng thời instance cũ và mới, làm pool tăng tạm thời vượt dự tính. Cần tính cả số instance tối đa trong quá trình deploy/autoscaling, không chỉ số instance bình thường.

### 3.1. Để lại headroom

Một ngân sách thực tế cần dành chỗ cho:

- Kết nối quản trị và monitoring.
- Migration, backup client và tác vụ khẩn cấp.
- Tăng replica hoặc autoscaling tạm thời.
- Kết nối retry sau sự cố mạng.
- Một số client vượt dự kiến trong thời gian ngắn.

Headroom không phải một tỷ lệ cố định áp dụng cho mọi hệ thống. Chọn dựa trên peak usage, mức burst và năng lực server.

### 3.2. Connection pooling

Ứng dụng thường dùng pool để tái sử dụng một số kết nối lâu dài thay vì mở/đóng TCP connection cho mỗi request. Pool cần có:

- maximumPoolSize: số kết nối tối đa của một instance.
- minimumIdle: số kết nối nhàn rỗi duy trì nếu pool hỗ trợ.
- connectionTimeout: thời gian request chờ lấy connection từ pool; đây là timeout của pool, khác connect_timeout của MySQL.
- idleTimeout: thời gian pool giữ connection idle trước khi thu hồi.
- maxLifetime hoặc maxIdleTime: tuổi thọ connection để pool chủ động thay mới.
- Validation/keepalive: kiểm tra hoặc giữ kết nối sống theo driver/pool.

Đặt tuổi thọ hoặc keepalive phù hợp với wait_timeout, proxy/load balancer và chính sách mạng. Pool nên chủ động loại bỏ connection trước khi server hoặc middlebox đóng nó, đồng thời kiểm tra connection khi checkout nếu driver hỗ trợ.

### 3.3. Tránh connection storm

Khi database khởi động lại hoặc mất mạng, hàng trăm instance có thể đồng loạt reconnect. Dùng exponential backoff có jitter, giới hạn retry và pool startup ramp-up. Không để mỗi request web tự tạo một kết nối mới sau lỗi 1040; việc retry dồn dập làm tình trạng quá tải nặng hơn.

## 4. Connection có chi phí tài nguyên gì?

Mỗi connection cần trạng thái session, thread hoặc worker execution context, socket, metadata và một phần bộ nhớ. MySQL thường dùng mô hình một thread phục vụ một connection trong cấu hình phổ biến. Các buffer lớn không nhất thiết được cấp phát toàn bộ ngay lúc connect, nhưng có thể được cấp phát khi session thực hiện operation tương ứng.

Một số nguồn tiêu thụ tài nguyên:

| Tài nguyên | Tác động |
|---|---|
| Thread/session state | Tăng theo số connection |
| Stack và memory nền | Tăng theo thread/connection |
| Sort/join/read buffers | Có thể cấp phát theo session hoặc operation |
| Internal temporary tables | Tăng theo truy vấn cần materialization |
| File descriptors/sockets | Mỗi connection cần socket; server còn mở file/table |
| CPU scheduling | Quá nhiều thread runnable làm tăng context switching và tranh chấp CPU |
| Transaction/locks | Session giữ transaction mở có thể giữ row lock, metadata lock hoặc undo history lâu hơn |

Vì vậy, tăng max_connections không làm server tự có thêm CPU/RAM. Trước khi tăng, đo memory ở giờ cao điểm, số thread, query concurrency, file descriptor và giới hạn OS.

### 4.1. Không cộng tất cả buffer như thể luôn được cấp phát

Các biến như sort_buffer_size, join_buffer_size, read_buffer_size và read_rnd_buffer_size có thể tạo chi phí theo session hoặc theo operation. Một query có nhiều join/sort có thể cần nhiều buffer hơn một session chỉ đang Sleep.

Không lấy một công thức nhân mọi buffer với max_connections rồi coi đó là mức dùng RAM chính xác. Nhưng cũng không giả định các buffer không thể cộng dồn: nhiều session chạy truy vấn nặng đồng thời có thể tạo memory pressure. Dùng Performance Schema, process metrics và workload thực tế để đo.

## 5. Giới hạn kết nối theo account

max_connections giới hạn toàn server. max_user_connections giới hạn số kết nối đồng thời của một MySQL account. Account được xác định bởi cặp user và host, ví dụ 'api_user'@'10.%' khác 'api_user'@'localhost'.

### 5.1. Giới hạn global theo account

~~~sql
SHOW GLOBAL VARIABLES LIKE 'max_user_connections';

SET GLOBAL max_user_connections = 30;
~~~

Giá trị 0 có nghĩa là không áp dụng giới hạn đồng thời toàn cục theo account. Khi được đặt số dương, giới hạn này áp dụng cho từng account, trừ khi account có resource option riêng ghi đè.

### 5.2. Giới hạn riêng bằng ALTER USER

MySQL cho phép đặt resource limits cho account:

- MAX_USER_CONNECTIONS: số kết nối đồng thời tối đa của account.
- MAX_CONNECTIONS_PER_HOUR: số lần kết nối tối đa trong một giờ.
- MAX_QUERIES_PER_HOUR: số query tối đa trong một giờ.
- MAX_UPDATES_PER_HOUR: số câu lệnh update tối đa trong một giờ.

Ví dụ:

~~~sql
ALTER USER 'api_user'@'10.%'
    WITH
        MAX_USER_CONNECTIONS 20
        MAX_CONNECTIONS_PER_HOUR 5000
        MAX_QUERIES_PER_HOUR 20000
        MAX_UPDATES_PER_HOUR 5000;
~~~

Các giá trị trên chỉ là ví dụ. Chọn quota theo workload và khả năng của dịch vụ. Giới hạn theo giờ là quota sử dụng trong một khoảng một giờ của account, không phải rate limit mượt theo từng giây; ứng dụng vẫn cần rate limiting riêng.

Kiểm tra thông tin account:

~~~sql
SHOW CREATE USER 'api_user'@'10.%';
SHOW GRANTS FOR 'api_user'@'10.%';
~~~

### 5.3. Khi nào dùng từng giới hạn?

| Giới hạn | Bảo vệ điều gì? | Ví dụ mục tiêu |
|---|---|---|
| max_connections | Tổng server | Ngăn toàn bộ client chiếm vô hạn connection |
| max_user_connections | Một account | Không để một dịch vụ chiếm hết pool |
| MAX_CONNECTIONS_PER_HOUR | Tần suất mở connection theo giờ | Phát hiện client reconnect liên tục |
| MAX_QUERIES_PER_HOUR | Số query theo giờ | Hạn chế workload account có quota |
| MAX_UPDATES_PER_HOUR | Số update theo giờ | Giới hạn account báo cáo/batch theo chính sách |

Các quota account không thay thế privilege kiểm soát dữ liệu. Một account chỉ có quota thấp vẫn có thể đọc hoặc sửa dữ liệu ngoài phạm vi nếu được cấp quyền SQL quá rộng.

## 6. connect_timeout: timeout khi bắt tay kết nối

connect_timeout là số giây server chờ connect packet từ client trước khi coi handshake không hợp lệ/không hoàn tất. Nó xử lý giai đoạn đầu của kết nối, trước khi session được sử dụng bình thường.

~~~sql
SHOW GLOBAL VARIABLES LIKE 'connect_timeout';

SET GLOBAL connect_timeout = 15;
~~~

Nếu client ở mạng có độ trễ cao hoặc handshake qua proxy chậm, giá trị quá thấp có thể gây lỗi kết nối. Nếu đặt quá cao, các kết nối nửa chừng có thể giữ tài nguyên lâu hơn. Điều chỉnh theo latency thực tế và log Aborted_connects.

connect_timeout không phải thời gian ứng dụng chờ lấy connection từ pool và cũng không phải TCP connect timeout của driver. Driver thường có thiết lập riêng cho TCP/socket connect và handshake.

## 7. wait_timeout và interactive_timeout

wait_timeout giới hạn số giây server chờ hoạt động tiếp theo trên một noninteractive connection trước khi đóng nó. Đây là timeout cho session idle, không phải thời gian chạy tối đa của một query.

interactive_timeout dùng cho interactive connection. Khi kết nối được tạo với cờ client interactive, giá trị wait_timeout session ban đầu được lấy từ interactive_timeout; với kết nối noninteractive, nó được lấy từ wait_timeout global. Sau khi session được tạo, có thể xem giá trị session thực tế.

### 7.1. Kiểm tra global và session

~~~sql
SHOW GLOBAL VARIABLES LIKE 'wait_timeout';
SHOW GLOBAL VARIABLES LIKE 'interactive_timeout';

SELECT
    @@GLOBAL.wait_timeout AS global_wait_timeout,
    @@SESSION.wait_timeout AS this_session_wait_timeout,
    @@GLOBAL.interactive_timeout AS global_interactive_timeout;
~~~

Đừng kết luận mọi session dùng cùng timeout chỉ từ giá trị global. Mỗi session có giá trị riêng và có thể được đặt lại.

### 7.2. Thay đổi timeout

~~~sql
SET GLOBAL wait_timeout = 900;
SET SESSION wait_timeout = 900;
~~~

SET GLOBAL thay giá trị mặc định cho các session được tạo sau đó; nó không tự thay @@SESSION.wait_timeout của những connection đã tồn tại. SET SESSION chỉ thay đổi session hiện tại.

Để persist:

~~~sql
SET PERSIST wait_timeout = 900;
SET PERSIST interactive_timeout = 900;
~~~

Không đặt timeout quá ngắn nếu pool có connection idle hợp lệ. Khi server đóng một connection vì idle timeout, pool có thể vẫn tưởng connection đó còn sống cho tới lần checkout tiếp theo. Cấu hình pool phải nhận biết và loại bỏ connection stale.

### 7.3. Idle transaction nguy hiểm hơn idle session

Một session Sleep có thể vẫn đang giữ transaction mở. Transaction mở lâu có thể giữ row locks, giữ metadata liên quan hoặc ngăn purge dọn undo history cũ. Hãy theo dõi trx_started, trạng thái transaction và tuổi transaction, không chỉ nhìn Command = Sleep.

Từ MySQL 8.0.24, có các biến idle_transaction_timeout, idle_write_transaction_timeout và idle_readonly_transaction_timeout để đóng session idle trong transaction theo các phạm vi tương ứng. Chỉ dùng sau khi xác nhận phiên bản và hiểu rằng session bị ngắt có thể làm ứng dụng nhận lỗi và phải rollback/retry transaction ở tầng ứng dụng. Giá trị 0 tắt giới hạn tương ứng.

~~~sql
SHOW GLOBAL VARIABLES LIKE 'idle%transaction%timeout';
~~~

Đừng dùng các biến này để thay thế việc đóng transaction đúng cách trong ứng dụng. Chúng là lớp bảo vệ cho transaction bị bỏ quên.

## 8. net_read_timeout và net_write_timeout

Hai biến này xử lý việc truyền dữ liệu qua kết nối:

- net_read_timeout: số giây server chờ thêm dữ liệu từ client trước khi hủy thao tác đọc.
- net_write_timeout: số giây server chờ ghi một block dữ liệu tới client trước khi hủy thao tác ghi.

~~~sql
SHOW GLOBAL VARIABLES LIKE 'net_read_timeout';
SHOW GLOBAL VARIABLES LIKE 'net_write_timeout';
~~~

Tình huống thường gặp:

- Client upload payload lớn hoặc gửi request chậm: xem net_read_timeout.
- Client nhận result set lớn qua mạng chậm hoặc bị nghẽn: xem net_write_timeout.
- Client bị mất mạng giữa lúc truyền dữ liệu: kiểm tra cả server error log và driver exception.

Đây không phải idle timeout. Một session không gửi câu lệnh nào bị xử lý bởi wait_timeout; một session đang truyền dữ liệu bị xử lý bởi network timeout phù hợp.

Không tăng timeout để che giấu client chậm vô hạn. Kiểm tra bandwidth, kích thước payload, result set, proxy timeout và khả năng tiêu thụ dữ liệu của client.

## 9. max_execution_time: giới hạn thời gian chạy SELECT

max_execution_time đặt giới hạn thời gian thực thi tính bằng millisecond cho read-only SELECT statements. Giá trị 0 nghĩa là không áp dụng giới hạn này.

~~~sql
SHOW GLOBAL VARIABLES LIKE 'max_execution_time';

SET SESSION max_execution_time = 2000;
~~~

Giới hạn session áp dụng cho các SELECT phù hợp được thực thi trong session đó. Có thể đặt giới hạn riêng cho một câu lệnh bằng optimizer hint:

~~~sql
SELECT /*+ MAX_EXECUTION_TIME(1500) */
       order_id, created_at
FROM orders
WHERE customer_id = 1001;
~~~

Giá trị trong hint là millisecond. Hint hữu ích khi chỉ một truy vấn báo cáo cần giới hạn riêng mà không muốn thay mọi query của session.

### 9.1. Giới hạn và phạm vi

- max_execution_time áp dụng cho read-only SELECT statements; không phải timeout tổng quát cho mọi DML.
- Nó không giới hạn thời gian chờ lấy connection từ pool.
- Nó không thay thế lock_wait_timeout hoặc innodb_lock_wait_timeout.
- Nó không điều khiển thời gian truyền result set qua mạng sau khi server hoàn tất xử lý theo cách mà net_write_timeout điều khiển.
- Một số SELECT trong stored program hoặc ngữ cảnh đặc biệt có thể không chịu tác động như truy vấn client thông thường; kiểm tra tài liệu đúng phiên bản và thử trong staging.

Khi query bị dừng bởi giới hạn này, ứng dụng cần xử lý lỗi statement bị interrupt và không giả định rằng kết quả đã đầy đủ.

## 10. Timeout chờ lock khác timeout session

Một query có thể không chạy vì đang chờ lock. Có hai loại timeout cần phân biệt:

| Biến | Loại lock | Đơn vị | Mục đích |
|---|---|---|---|
| lock_wait_timeout | Metadata lock (MDL) | Giây | Giới hạn thời gian chờ metadata lock |
| innodb_lock_wait_timeout | InnoDB row lock | Giây | Giới hạn thời gian chờ row lock |
| max_execution_time | Read-only SELECT execution | Millisecond | Giới hạn thời gian thực thi SELECT |

Kiểm tra:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'lock_wait_timeout';
SHOW GLOBAL VARIABLES LIKE 'innodb_lock_wait_timeout';
~~~

Một DDL như ALTER TABLE có thể chờ metadata lock do transaction khác đang sử dụng bảng. Tăng max_execution_time không giải quyết việc chờ MDL. Tương tự, một UPDATE chờ row lock InnoDB không được điều khiển bởi wait_timeout vì session đang hoạt động và chờ lock, không phải idle.

Khi gặp lỗi lock wait:

1. Xác định loại lock và session đang giữ lock.
2. Xem transaction age, câu SQL và trạng thái session.
3. Kiểm tra transaction có mở lâu hoặc quên commit/rollback không.
4. Cân nhắc rút ngắn transaction và thay đổi thứ tự truy cập tài nguyên.
5. Chỉ thay timeout sau khi hiểu tác động tới tính đúng đắn và retry.

## 11. Giới hạn buffer và bộ nhớ theo session

Một connection không có một memory limit per session đơn giản áp dụng cho mọi allocation. MySQL có nhiều biến điều khiển buffer theo loại operation; một số được cấp phát khi cần và có thể được giải phóng khi operation kết thúc hoặc session đóng.

| Biến | Vai trò thường gặp | Cách tiếp cận |
|---|---|---|
| sort_buffer_size | Buffer cho sort operation | Không tăng lớn toàn cục khi chưa đo sort workload |
| join_buffer_size | Buffer cho join không dùng index phù hợp | Ưu tiên sửa index/query shape; tăng có chọn lọc |
| read_buffer_size | Buffer đọc tuần tự | Đánh giá scan workload và memory impact |
| read_rnd_buffer_size | Buffer đọc theo thứ tự sau sort | Đo workload có filesort/read-random |
| tmp_table_size | Giới hạn kích thước internal in-memory temporary table theo phiên bản | Kiểm tra hành vi TempTable theo MySQL minor |
| max_heap_table_size | Giới hạn bảng MEMORY và một số đường internal temp table tùy phiên bản | Không nhầm với giới hạn mọi JSON/document |
| max_allowed_packet | Kích thước packet/message tối đa được phép | Đặt theo payload thực tế và bảo vệ protocol |

Một số buffer có thể được cấp phát nhiều lần trong một query hoặc bởi nhiều query đồng thời. Không tăng join_buffer_size hay sort_buffer_size chỉ vì một query chậm; trước tiên xem EXPLAIN, index và số hàng phải xử lý.

### 11.1. Internal temporary table

Query có GROUP BY, DISTINCT, UNION, ORDER BY hoặc materialization có thể cần internal temporary table. Tùy phiên bản MySQL và loại dữ liệu, temporary table có thể dùng TempTable hoặc cơ chế khác, và có thể chuyển sang lưu trữ trên disk khi vượt giới hạn.

Trong MySQL 8.0.28+, tmp_table_size áp dụng giới hạn theo từng internal in-memory TempTable. temptable_max_ram điều khiển ngân sách RAM của TempTable engine ở mức server. Đây là hai lớp khác nhau: giới hạn từng bảng tạm và ngân sách RAM dùng chung. Kiểm tra biến thực tế trước khi áp dụng vì các minor release có thay đổi hành vi.

~~~sql
SHOW GLOBAL VARIABLES LIKE 'tmp_table_size';
SHOW GLOBAL VARIABLES LIKE 'temptable_max_ram';
SHOW GLOBAL VARIABLES LIKE 'temptable_max_mmap';
~~~

Không nhân tmp_table_size với số connection rồi kết luận server sẽ dùng đúng lượng RAM đó; không phải mọi session đều có internal temp table cùng lúc. Nhưng workload có nhiều query materialize đồng thời có thể gây memory/disk pressure.

### 11.2. max_allowed_packet không phải session memory cap

max_allowed_packet giới hạn kích thước packet/message mà client/server chấp nhận, ví dụ payload lớn hoặc result column lớn. Nó không giới hạn tổng memory mà một session có thể sử dụng.

~~~sql
SHOW GLOBAL VARIABLES LIKE 'max_allowed_packet';
~~~

Nếu tăng biến này, hãy đồng thời kiểm soát request body, kích thước blob/document, số lượng hàng và thời gian truyền. Không dùng packet limit làm chính sách bảo vệ duy nhất.

## 12. Thread cache, file descriptor và giới hạn OS

thread_cache_size kiểm soát số thread server giữ lại để tái sử dụng khi connection mới đến. Nó có thể giảm chi phí tạo thread khi connection churn cao, nhưng không giới hạn số connection đồng thời.

open_files_limit, table_open_cache và giới hạn file descriptor của hệ điều hành ảnh hưởng đến số file/table/socket server có thể quản lý. Tăng max_connections có thể yêu cầu kiểm tra các giới hạn này.

~~~sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
    'max_connections',
    'thread_cache_size',
    'open_files_limit',
    'table_open_cache',
    'back_log'
);
~~~

back_log liên quan đến hàng đợi kết nối đang chờ accept ở tầng server/OS; nó không thay thế max_connections. Hệ điều hành có thể áp dụng giới hạn riêng cho backlog, file descriptor, process/thread và memory.

Khi tăng kết nối:

1. Kiểm tra giới hạn file descriptor/service manager của OS.
2. Kiểm tra giá trị open_files_limit thực tế MySQL nhận được.
3. Kiểm tra memory và thread count ở peak.
4. Kiểm tra table_open_cache và workload mở bảng.
5. Kiểm tra connection churn và hiệu quả thread cache.
6. Thay đổi theo từng bước, theo dõi sau mỗi lần.

## 13. Quan sát mức sử dụng kết nối

### 13.1. Status variables quan trọng

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Threads_connected',
    'Threads_running',
    'Max_used_connections',
    'Connection_errors_max_connections',
    'Aborted_connects',
    'Connections',
    'Threads_created',
    'Uptime'
);
~~~

| Status | Cách đọc |
|---|---|
| Threads_connected | Session hiện đang kết nối |
| Threads_running | Thread không ở trạng thái sleeping |
| Max_used_connections | Peak connection count kể từ lần reset liên quan |
| Connection_errors_max_connections | Kết nối bị từ chối do đạt max_connections |
| Aborted_connects | Kết nối thất bại trong quá trình connect/authenticate |
| Connections | Tổng số lần kết nối server đã nhận kể từ lần reset liên quan |
| Threads_created | Số thread server đã tạo |

So sánh chênh lệch counter theo thời gian thay vì chỉ xem tổng tích lũy. Ví dụ Connections tăng nhanh trong khi Threads_connected luôn thấp có thể chỉ ra connection churn và pool chưa hiệu quả.

### 13.2. Xem session và transaction

~~~sql
SHOW FULL PROCESSLIST;
~~~

Tìm các session:

- Sleep lâu nhưng vẫn giữ transaction.
- Chạy cùng một query quá lâu.
- Chờ metadata lock hoặc row lock.
- Thuộc một account đang chiếm phần lớn connection.
- Đến từ host/ứng dụng không còn được nhận diện.

Có thể xem sys.processlist hoặc các bảng Performance Schema như performance_schema.threads và performance_schema.events_statements_current nếu đã bật instrument phù hợp. Không bật toàn bộ instrument trên production mà chưa đánh giá overhead.

### 13.3. Tìm account chiếm nhiều connection

~~~sql
SELECT
    USER,
    SUBSTRING_INDEX(HOST, ':', 1) AS client_host,
    COUNT(*) AS connection_count
FROM performance_schema.processlist
GROUP BY USER, SUBSTRING_INDEX(HOST, ':', 1)
ORDER BY connection_count DESC;
~~~

Truy vấn này giúp tìm nguồn chiếm connection theo user/host. Với MySQL 8.0.22+, ưu tiên Performance Schema processlist; INFORMATION_SCHEMA.PROCESSLIST đã deprecated từ bản này. Cần quyền phù hợp để thấy đầy đủ session của người dùng khác. Trong môi trường dùng proxy, host hiển thị có thể là proxy thay vì application instance.

### 13.4. Theo dõi query digest

Performance Schema có thể tổng hợp statement theo digest để xác định query nào tạo tải hoặc chạy lâu. Kết hợp:

- Số lần thực thi.
- Tổng thời gian và thời gian trung bình.
- Rows examined/rows sent.
- Lock time và lỗi.
- Số connection đồng thời của dịch vụ phát sinh workload.

Mục tiêu là tìm nguyên nhân làm connection bị giữ lâu, ví dụ query thiếu index hoặc transaction chờ lock, thay vì chỉ tăng số connection cho đủ chỗ xếp hàng.

## 14. Xử lý Too many connections

Khi nhận lỗi 1040, không bắt đầu bằng việc tăng max_connections ngay lập tức. Thu thập thông tin và giải phóng connection an toàn:

1. Kiểm tra Threads_connected, Max_used_connections và Connection_errors_max_connections.
2. Xem SHOW FULL PROCESSLIST để tìm account/host chiếm connection.
3. Phân biệt session Sleep, query chạy lâu, session chờ lock và transaction idle.
4. Kiểm tra pool size trên mọi application instance, kể cả instance đang rolling deploy.
5. Kiểm tra connection leak, retry storm và ứng dụng không trả connection về pool.
6. Dùng tài khoản có quyền CONNECTION_ADMIN hoặc kênh quản trị dự phòng nếu cần.
7. Chỉ kết thúc session sau khi xác định chủ sở hữu và tác động tới transaction.
8. Nếu cần tăng max_connections, kiểm tra memory/OS headroom trước.
9. Điều chỉnh pool, timeout hoặc query gây nghẽn.
10. Theo dõi lại counters sau khi xử lý.

### 14.1. KILL QUERY và KILL CONNECTION

~~~sql
KILL QUERY 12345;
KILL CONNECTION 12345;
~~~

KILL QUERY yêu cầu dừng câu lệnh hiện tại nhưng giữ session. KILL CONNECTION đóng toàn bộ connection; transaction chưa commit của session sẽ bị rollback khi connection kết thúc. Không kill một session chỉ vì trạng thái Sleep mà chưa kiểm tra transaction và owner.

### 14.2. Retry sau lỗi 1040

Ứng dụng cần:

- Retry có backoff và jitter.
- Giới hạn tổng retry và thời gian chờ.
- Không mở một connection mới cho mỗi lần retry không giới hạn.
- Trả lỗi có kiểm soát khi pool không thể lấy connection.
- Ghi metric pool active/idle/pending và thời gian chờ checkout.

Nếu mọi request đều retry ngay lập tức, server bị bão reconnect và tình trạng 1040 kéo dài hơn.

## 15. Cấu hình thay đổi có kiểm soát

Một thay đổi cấu hình nên có baseline, mục tiêu, phạm vi, cách rollback và metric xác nhận:

1. Ghi lại biến global/session hiện tại.
2. Xác định biến có dynamic và persistable không.
3. Tính tác động lên tất cả session/instance.
4. Thử trong staging với workload tương đương.
5. Thay đổi runtime bằng SET GLOBAL/SET SESSION hoặc SET PERSIST phù hợp.
6. Xác minh giá trị bằng SHOW VARIABLES.
7. Theo dõi connection, memory, thread, latency và lỗi.
8. Nếu không đạt mục tiêu, rollback bằng giá trị cũ và xử lý persisted value nếu có.
9. Ghi lại lý do, thời điểm, người thực hiện và kết quả.

### 15.1. Phân biệt các lệnh cấu hình

| Lệnh | Tác động runtime | Sau restart |
|---|---|---|
| SET GLOBAL var = value | Đổi global runtime | Mất nếu không có cấu hình bền vững khác |
| SET SESSION var = value | Đổi session hiện tại | Không áp dụng cho session khác |
| SET PERSIST var = value | Đổi global runtime | Được lưu để tồn tại sau restart |
| SET PERSIST_ONLY var = value | Không đổi runtime hiện tại | Được lưu để áp dụng khi restart |
| Option file [mysqld] | Có hiệu lực khi server đọc cấu hình | Có hiệu lực sau restart |

Không phải mọi biến đều dynamic hoặc persistable. Một số biến chỉ có thể đặt khi startup. Luôn kiểm tra tài liệu đúng phiên bản và quyền SYSTEM_VARIABLES_ADMIN (hoặc quyền quản trị tương thích phiên bản cũ) trước khi thay đổi.

### 15.2. Rollback persisted value

Nếu đã dùng SET PERSIST, cần xử lý persisted setting khi rollback để lần restart sau không bật lại giá trị không mong muốn:

~~~sql
RESET PERSIST IF EXISTS max_connections;
~~~

Sau đó đặt giá trị runtime hoặc option file theo cấu hình mong muốn. Nếu option file cũng có cùng biến, hãy bảo đảm không có hai nguồn cấu hình xung đột.

## 16. Ví dụ cấu hình theo môi trường

Không có một bộ timeout tối ưu chung cho mọi workload. Một API OLTP, batch loader và reporting service có hành vi khác nhau. Bảng sau minh họa cách suy nghĩ khi thiết kế:

| Nhóm workload | Kết nối/pool | Idle timeout | Query timeout | Lưu ý |
|---|---|---|---|---|
| API OLTP | Pool nhỏ, giới hạn tổng theo số instance | Theo chu kỳ giữ connection của pool | Giới hạn SELECT theo endpoint nếu phù hợp | Ưu tiên query ngắn và transaction ngắn |
| Worker queue | Pool theo concurrency của worker | Phù hợp khoảng nghỉ giữa job | Theo SLA của job | Backoff khi database quá tải |
| Reporting | Pool riêng, ít connection | Không giữ session nhàn rỗi không cần thiết | Giới hạn SELECT rõ ràng | Dùng replica/warehouse nếu workload nặng |
| Migration/admin | Kết nối hạn chế, kiểm soát thủ công | Theo công cụ | Theo thao tác | Có tài khoản quản trị dự phòng |

Ví dụ cấu hình khởi đầu trong option file, cần điều chỉnh theo capacity test:

~~~ini
[mysqld]
max_connections = 300
max_user_connections = 40
wait_timeout = 900
interactive_timeout = 1800
connect_timeout = 15
net_read_timeout = 60
net_write_timeout = 60
max_execution_time = 3000
~~~

Đây là ví dụ minh họa, không phải khuyến nghị áp dụng nguyên trạng. max_user_connections ở đây giới hạn từng account; account có resource option riêng có thể có giới hạn riêng. Các timeout cần khớp với client, proxy, query SLA và batch size.

## 17. Những lỗi thiết kế phổ biến

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Tăng max_connections để chữa mọi lỗi timeout | Tăng memory/thread pressure mà không xử lý nguyên nhân | Phân loại lỗi theo handshake, idle, network, query hoặc lock |
| Đặt pool max size lớn trên mọi instance | Tổng pool vượt capacity server | Tính tổng pool qua toàn bộ fleet và rolling deployment |
| Đặt wait_timeout thấp hơn chu kỳ idle của pool | Pool giữ connection đã bị server đóng | Cấu hình pool recycle/keepalive và validate |
| Dùng connect_timeout để giới hạn pool checkout | Timeout sai tầng, không kiểm soát hàng chờ trong pool | Dùng timeout riêng của pool/driver |
| Tăng net_read_timeout để chữa query chậm | Không giải quyết execution hoặc lock wait | Xem query plan và lock diagnostics |
| Dùng max_execution_time cho UPDATE | Biến không có phạm vi áp dụng như mong muốn | Quản lý DML bằng transaction, lock timeout và application deadline |
| Tăng join_buffer_size toàn cục | Nhiều query đồng thời có thể tiêu thụ RAM lớn | Sửa index/query trước; tăng có chọn lọc |
| Không giới hạn account | Một dịch vụ chiếm hết connection | Đặt MAX_USER_CONNECTIONS theo account |
| Retry 1040 ngay lập tức | Tạo connection storm | Exponential backoff có jitter |
| Kill session Sleep mà không kiểm tra | Có thể rollback transaction hoặc làm lỗi nghiệp vụ | Kiểm tra transaction age và owner trước |
| Chỉ dùng SHOW PROCESSLIST một lần | Bỏ lỡ spike ngắn hoặc connection churn | Thu thập metrics theo thời gian |
| Persist cấu hình nhưng quên rollback | Giá trị xấu quay lại sau restart | Quản lý SET PERSIST và RESET PERSIST cùng change record |

## 18. Runbook kiểm tra connection saturation

Khi alert connection utilization tăng cao:

**Bước 1 — Xác nhận mức sử dụng**

~~~sql
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Threads_running';
SHOW GLOBAL STATUS LIKE 'Max_used_connections';
SHOW GLOBAL STATUS LIKE 'Connection_errors_max_connections';
~~~

**Bước 2 — Tìm account và host chiếm nhiều session**

~~~sql
SELECT USER, HOST, COUNT(*) AS sessions
FROM performance_schema.processlist
GROUP BY USER, HOST
ORDER BY sessions DESC;
~~~

**Bước 3 — Phân loại session**

~~~sql
SHOW FULL PROCESSLIST;
~~~

Ghi lại số session Sleep, query đang chạy, session chờ lock và session thuộc các account quan trọng.

**Bước 4 — Đối chiếu application pool**

Kiểm tra active, idle, pending checkout, timeout, connection creation rate và pool size trên tất cả instance. Đối chiếu với số session MySQL theo account/host.

**Bước 5 — Giải phóng và khôi phục**

Ưu tiên sửa leak, giảm pool burst, dừng batch không cần thiết hoặc xử lý query/transaction gây nghẽn. Chỉ kill session sau khi đánh giá tác động. Nếu tăng max_connections tạm thời, phải kiểm tra memory/OS headroom và có thời hạn đánh giá lại.

**Bước 6 — Ngăn tái diễn**

Thêm alert cho peak connection, Connection_errors_max_connections, pool pending, idle transaction age và connection churn. Ghi lại ngân sách pool và giới hạn account trong cấu hình triển khai.

## 19. Bài thực hành

Thực hiện trên MySQL lab; không thay đổi giới hạn production trong bài tập:

1. Đọc max_connections, max_user_connections, Threads_connected, Threads_running và Max_used_connections.
2. Mô phỏng nhiều session và quan sát Threads_connected tăng/giảm.
3. Tính ngân sách connection từ ba service có nhiều instance và pool size khác nhau.
4. Đặt MAX_USER_CONNECTIONS cho một account lab; mở kết nối tới khi chạm giới hạn và quan sát lỗi.
5. Kiểm tra SHOW CREATE USER để xác nhận quota account.
6. So sánh wait_timeout global với @@SESSION.wait_timeout trong hai session đã mở trước và sau khi đổi global.
7. Dùng session hiện tại để đặt SET SESSION wait_timeout; xác nhận session khác không bị đổi.
8. Tạo một client interactive và một client noninteractive; so sánh giá trị wait_timeout ban đầu theo interactive_timeout/wait_timeout.
9. Đọc connect_timeout, net_read_timeout và net_write_timeout; mô tả giai đoạn mà mỗi biến bảo vệ.
10. Dùng max_execution_time hoặc optimizer hint để giới hạn một SELECT trong lab.
11. So sánh lock_wait_timeout, innodb_lock_wait_timeout và max_execution_time bằng ba tình huống riêng.
12. Quan sát một transaction mở lâu ở trạng thái Sleep; kiểm tra transaction age và lý do không nên chỉ nhìn process command.
13. Kiểm tra các buffer session và mô tả operation nào có thể làm chúng được cấp phát.
14. Theo dõi Connection_errors_max_connections, Connections và Threads_created qua một khoảng thời gian để nhận diện connection churn.
15. Thử SET GLOBAL và SET PERSIST trên biến dynamic trong môi trường lab; xác nhận runtime và persisted value.
16. Dùng RESET PERSIST để xóa persisted override và xác minh cấu hình sau restart giả lập/khởi động lại lab.
17. Viết runbook ứng phó lỗi 1040 với bước đo, phân loại, giải phóng session và ngăn retry storm.
18. Thiết kế pool budget cho API, worker, reporting và admin, có tính đến rolling deployment và headroom.

## 20. Nguyên tắc cần ghi nhớ

- max_connections là trần connection đồng thời toàn server; max_user_connections và MAX_USER_CONNECTIONS giới hạn theo account.
- Account được nhận diện bằng user và host; cùng username ở hai host pattern có thể là hai account khác nhau.
- Tăng max_connections làm tăng khả năng tiêu thụ thread, memory, socket và file descriptor; phải đo capacity trước.
- Pool size phải được cộng trên toàn bộ instance, worker, scheduler, migration và monitoring.
- connect_timeout bảo vệ handshake; wait_timeout/interactive_timeout bảo vệ session idle.
- net_read_timeout và net_write_timeout bảo vệ truyền dữ liệu, không phải thời gian chạy query.
- max_execution_time giới hạn read-only SELECT theo millisecond.
- lock_wait_timeout dành cho metadata lock; innodb_lock_wait_timeout dành cho InnoDB row lock.
- Global variable mới không tự thay session variable của connection đang tồn tại.
- SET GLOBAL là runtime; SET PERSIST lưu cấu hình qua restart; SET SESSION chỉ ảnh hưởng session hiện tại.
- Các buffer theo session/operation có thể cộng dồn khi nhiều query nặng chạy đồng thời.
- thread_cache_size không phải giới hạn số connection.
- Theo dõi Threads_connected, Threads_running, Max_used_connections và Connection_errors_max_connections theo thời gian.
- Không retry lỗi 1040 vô hạn; dùng backoff, jitter và giới hạn tổng retry.
- Kiểm tra transaction trước khi kill một session Sleep.
- Chọn timeout theo đúng giai đoạn chờ và SLA của workload, không dùng một timeout chung cho mọi vấn đề.

# Số kết nối, kích thước pool ứng dụng và tác động đến thông lượng

Mỗi kết nối MySQL là một session có trạng thái riêng: user, schema mặc định, transaction, isolation level, biến session, temporary table và các thiết lập khác. Ứng dụng thường giữ một tập kết nối đã mở trong **connection pool** để tái sử dụng thay vì tạo kết nối mới cho từng request.

Kích thước pool ảnh hưởng trực tiếp đến số công việc có thể đồng thời lấy connection để truy cập database. Pool quá nhỏ làm request xếp hàng ở ứng dụng dù MySQL còn khả năng xử lý. Pool quá lớn có thể đẩy quá nhiều truy vấn vào MySQL, làm tăng contention, memory pressure, context switching và latency p95/p99. Vì vậy, tăng số connection không đồng nghĩa tăng throughput.

Cần tách ba đại lượng:

- **Số connection mở**: session đang được giữ bởi ứng dụng, kể cả connection idle trong pool.
- **Số operation đồng thời**: số request/transaction đang thực sự sử dụng connection.
- **Throughput**: số transaction hoặc request hoàn tất trong một đơn vị thời gian.

Bài học thuộc phạm vi DATABASE_MYSQL: lập ngân sách connection cho toàn hệ thống, chọn kích thước pool theo thời gian giữ connection và năng lực database, đo queueing/latency/throughput, xử lý connection churn và stale connection, đồng thời tránh để pool làm quá tải MySQL trong autoscaling hoặc rolling deployment.

## 1. Connection, session và request là ba khái niệm khác nhau

Khi ứng dụng mở kết nối tới MySQL, server tạo một session. Session tồn tại lâu hơn một câu SQL đơn lẻ và có trạng thái riêng.

Một request HTTP có thể:
- Không truy cập database.
- Chạy một hoặc nhiều query trên cùng connection.
- Mở một transaction gồm nhiều query.
- Gọi nhiều service, trong đó chỉ một phần thời gian giữ connection.
- Giữ connection quá lâu nếu code không đóng đúng cách.

Không nên thiết kế một connection cho mỗi request rồi giữ connection suốt vòng đời request nếu request còn phải gọi HTTP API, xử lý file hoặc chờ người dùng. Connection nên được mượn trong khoảng thời gian thật sự cần thao tác database và trả lại pool ngay khi hoàn tất.

### 1.1. Connection pool tái sử dụng session

Luồng thông thường:

~~~text
HTTP request / worker
        |
        v
Application connection pool
   |       |        |
   v       v        v
 Conn A  Conn B   Conn C
   |       |        |
   +-------+--------+
           |
           v
       MySQL Server
           |
           v
      InnoDB / SQL
~~~

Pool quản lý:
- Tạo connection mới khi cần và còn dưới giới hạn.
- Cấp connection rảnh cho thread/request.
- Đưa connection về trạng thái có thể tái sử dụng.
- Đóng connection idle hoặc quá tuổi theo chính sách.
- Chờ hoặc từ chối request khi hết connection.

Một pool thường được tạo ở cấp ứng dụng/process và dùng chung. Không tạo một pool mới cho mỗi HTTP request, repository hoặc DAO.

### 1.2. Một connection không xử lý nhiều statement độc lập cùng lúc

Với mô hình client/server thông thường, một connection MySQL thực thi một command tại một thời điểm. Nhiều request có thể chạy đồng thời khi chúng dùng các connection khác nhau.

Nếu một request cần chạy nhiều query tuần tự trong cùng transaction, các query đó thường dùng cùng connection. Không mượn connection thứ hai cho từng query trong cùng transaction nếu không có lý do rõ ràng; làm vậy có thể phá transaction boundary và tiêu tốn pool.

## 2. MySQL quản lý connection như thế nào?

Theo mô hình mặc định, MySQL dùng mô hình thread-per-connection: mỗi client connection được phục vụ bởi một server thread. Thread thực hiện command của session, xử lý kết quả và chờ command tiếp theo.

Điều đó không có nghĩa mỗi connection luôn chiếm một CPU core. Thread có thể đang ngủ, chờ network, chờ lock hoặc chờ I/O. Tuy nhiên, nhiều thread đồng thời vẫn tiêu tốn bộ nhớ, cấu trúc quản lý, lịch CPU và tài nguyên hệ điều hành.

### 2.1. Thread cache không phải connection pool

MySQL có thread cache để tái sử dụng server thread sau khi client disconnect. Các biến thường xem:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'thread_cache_size';
SHOW GLOBAL STATUS LIKE 'Threads_created';
SHOW GLOBAL STATUS LIKE 'Threads_cached';
SHOW GLOBAL STATUS LIKE 'Threads_connected';
~~~

Phân biệt:

| Cơ chế | Quản lý cái gì? | Tác dụng |
|---|---|---|
| Application connection pool | Client connection/session tới MySQL | Tái sử dụng kết nối, giảm handshake và xác thực lặp lại |
| MySQL thread cache | Server thread phục vụ connection | Giảm chi phí tạo/hủy thread khi connection churn |
| MySQL max_connections | Số client connection đồng thời được chấp nhận | Đặt giới hạn bảo vệ server |

Thread cache không giữ connection phía ứng dụng và không làm giảm số session đang mở. Tăng thread_cache_size không thay thế việc cấu hình pool.

### 2.2. Thread pool phía server

Một số bản phân phối MySQL có giải pháp thread pool để điều tiết số worker thread phục vụ nhiều connection. MySQL Enterprise Edition cung cấp Thread Pool plugin; các bản phân phối khác có thể có triển khai riêng.

Thread pool phía server và connection pool phía ứng dụng giải quyết các tầng khác nhau:
- Application pool giới hạn số connection ứng dụng mở và số operation được phép lấy connection.
- Server thread pool điều phối việc thực thi của connection bên trong MySQL.

Không giả định plugin thread pool có sẵn trên mọi edition. Kiểm tra phiên bản, edition, plugin và tài liệu của nhà cung cấp trước khi thiết kế dựa trên nó.

## 3. Vì sao pool quá nhỏ làm giảm thông lượng?

Giả sử ứng dụng có 100 request đồng thời nhưng pool chỉ có 5 connection. Tối đa 5 request có thể sử dụng connection tại một thời điểm; những request khác chờ ở pool.

Nếu mỗi operation giữ connection 40 ms và không có contention, một connection về lý thuyết có thể phục vụ khoảng 25 operation/giây. Năm connection có thể phục vụ khoảng 125 operation/giây trong mô hình đơn giản đó. Thực tế còn phụ thuộc thời gian query, transaction, lock, network và chi phí ứng dụng.

Dấu hiệu pool quá nhỏ:
- Số connection active luôn gần maximumPoolSize.
- Số thread pending chờ connection tăng.
- Connection acquisition latency cao.
- Có timeout lấy connection dù MySQL chưa bão hòa.
- MySQL Threads_running và CPU vẫn còn dư địa.
- Tăng pool một bước nhỏ làm queue giảm mà DB latency không tăng đáng kể.

Không kết luận pool nhỏ chỉ từ active=max. Cần xem thời gian giữ connection và năng lực MySQL. Nếu connection bị giữ lâu vì transaction hoặc query chậm, tăng pool có thể chỉ làm tăng số công việc đồng thời đang chờ database.

## 4. Vì sao pool quá lớn có thể làm throughput giảm?

Pool lớn cho phép nhiều operation đi vào MySQL cùng lúc. Khi database đã đạt giới hạn CPU, I/O, lock hoặc memory, thêm concurrency có thể làm mọi operation chậm hơn.

Các tác động:
- Nhiều thread tranh CPU và tăng context switching.
- Nhiều transaction giữ row lock cùng lúc.
- Buffer pool và cache chịu áp lực lớn hơn.
- Temporary table và per-thread buffer có thể tăng memory usage.
- I/O queue dài hơn.
- Deadlock và lock wait có thể tăng.
- Tail latency p95/p99 tăng dù throughput không tăng.
- Server tiến gần max_connections và khó dành chỗ cho quản trị.

Ví dụ, nếu database xử lý ổn định 400 transaction/giây ở concurrency 16, tăng concurrency lên 64 không bảo đảm đạt 1.600 transaction/giây. Nếu tài nguyên đã bão hòa, throughput có thể gần như giữ nguyên trong khi thời gian chờ tăng mạnh.

### 4.1. Throughput và latency phải được xem cùng nhau

Một cấu hình tốt cần đáp ứng cả:
- Throughput đạt mục tiêu.
- p95/p99 latency nằm trong SLO.
- Connection acquisition wait thấp.
- Database còn headroom cho burst và tác vụ nền.
- Không có tăng trưởng bất thường về lock wait, deadlock hoặc lỗi kết nối.

Chỉ nhìn requests/second có thể che giấu việc hệ thống đang tích lũy queue và trả kết quả chậm hơn.

## 5. Ngân sách connection toàn hệ thống

\`max_connections\` là giới hạn toàn server, không phải giới hạn cho từng ứng dụng. Phải tính tổng pool của tất cả process/replica cùng kết nối vào instance.

Một ngân sách đơn giản:

\[
C_{app} = \sum_{i=1}^{n}(R_i \times P_i)
\]

Trong đó:
- \(R_i\): số replica tối đa của ứng dụng i.
- \(P_i\): maximum pool size của mỗi replica i.
- \(C_{app}\): tổng số connection tối đa từ các pool ứng dụng.

Ngân sách server cần dành chỗ cho:
- Ứng dụng chính.
- Worker/background jobs.
- Migration và batch jobs.
- Monitoring/exporter.
- DBA và kết nối khẩn cấp.
- Replication hoặc service nội bộ tùy topology.
- Burst và rolling deployment.

Không đặt tổng maximum pool bằng đúng max_connections. Phải giữ headroom và một lối vào quản trị khi ứng dụng bị lỗi hoặc pool cạn.

### 5.1. Ví dụ tính tổng pool

Giả sử hệ thống có:
- 6 replica API, mỗi replica pool tối đa 12.
- 3 replica worker, mỗi replica pool tối đa 4.
- 2 tác vụ batch, mỗi tác vụ có thể dùng 3 connection.
- Monitoring và công cụ vận hành cần khoảng 5 connection.

Tổng nhu cầu tối đa dự kiến:

\[
6 \times 12 + 3 \times 4 + 2 \times 3 + 5 = 95
\]

Nếu MySQL max_connections là 140, còn 45 slot cho headroom, quản trị, tác vụ khác và thay đổi tải. Tuy nhiên, con số này chỉ là ngân sách connection, không chứng minh MySQL đủ CPU/memory để phục vụ 95 operation đồng thời.

### 5.2. Tính cả rolling deployment và autoscaling

Nếu deployment chạy song song bản cũ và bản mới trong một khoảng thời gian, số replica tạm thời có thể lớn hơn desired replicas. Autoscaling cũng có thể tăng replica nhanh hơn dự kiến.

Ví dụ 6 replica bình thường nhưng rolling update tạm thời tạo 2 replica bổ sung:
- Pool API: \(8 \times 12 = 96\) connection.
- Worker và batch vẫn hoạt động.
- Tổng có thể vượt ngân sách đã tính theo 6 replica.

Hãy tính theo maximum replicas và surge replicas thực tế trong cấu hình orchestrator, không chỉ theo số pod bình thường.

## 6. Đọc giới hạn và trạng thái connection của MySQL

Kiểm tra giới hạn:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SHOW GLOBAL VARIABLES LIKE 'max_user_connections';
SHOW GLOBAL VARIABLES LIKE 'wait_timeout';
SHOW GLOBAL VARIABLES LIKE 'thread_cache_size';
~~~

Đọc các status counter:

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Threads_connected',
    'Threads_running',
    'Threads_created',
    'Threads_cached',
    'Connections',
    'Max_used_connections',
    'Aborted_connects',
    'Connection_errors_max_connections'
);
~~~

Ý nghĩa:

| Biến | Ý nghĩa |
|---|---|
| Threads_connected | Số client thread/connection hiện đang kết nối |
| Threads_running | Số thread không ở trạng thái ngủ; có thể bao gồm thread đang chờ tài nguyên |
| Threads_created | Số thread server đã tạo để phục vụ connection |
| Threads_cached | Số thread hiện nằm trong thread cache |
| Connections | Số lần client connection attempt được ghi nhận kể từ khi server khởi động/reset status |
| Max_used_connections | Mức connection đồng thời cao nhất kể từ khi server khởi động/reset status |
| Aborted_connects | Số lần kết nối thất bại theo nhóm server ghi nhận |
| Connection_errors_max_connections | Số lần từ chối kết nối vì đạt max_connections |

Một số status variable có thể khác theo phiên bản hoặc distribution. Kiểm tra bằng SHOW GLOBAL STATUS trên đúng server.

### 6.1. Threads_connected không phải số query đang chạy

Connection trong pool có thể idle, nên Threads_connected thường lớn hơn Threads_running. Threads_running cũng không phải số query đang tiêu thụ CPU: thread có thể đang chờ lock hoặc I/O.

Hãy xem thêm processlist, Performance Schema và application pool metrics để biết connection đang làm gì.

### 6.2. Max_used_connections là peak, không phải hiện tại

Max_used_connections cho biết peak connection đồng thời kể từ lần khởi động/reset counter. Nếu giá trị gần max_connections, có thể đã từng có nguy cơ chạm trần; nhưng nó không nói hiện tại server đang có bao nhiêu connection.

Lấy snapshot định kỳ và so sánh với thời điểm deploy, batch job hoặc traffic burst.

## 7. Tính tốc độ connection và connection churn

Connections là counter tích lũy. Để tính số lần kết nối mới mỗi giây, lấy hai snapshot:

\[
ConnectionRate = \frac{Connections_{t2} - Connections_{t1}}{t2-t1}
\]

Ví dụ counter tăng 1.200 trong 60 giây:

\[
ConnectionRate = \frac{1200}{60}=20
\]

Tức khoảng 20 connection attempt mỗi giây trong cửa sổ đo.

Connection rate cao kéo dài có thể cho thấy:
- Ứng dụng không dùng pool hoặc pool bị tạo/hủy liên tục.
- Pool lifetime quá ngắn.
- Health check mở connection mới liên tục.
- Application process restart thường xuyên.
- Network lỗi làm client reconnect.
- Có nhiều client ngắn hạn như script hoặc job.

Không phải mọi connection attempt đều thành công; đối chiếu Aborted_connects và error counters.

### 7.1. Threads_created và thread cache

Nếu Threads_created tăng nhanh so với Connections, có thể server thường xuyên phải tạo thread thay vì lấy từ cache. Đây là tín hiệu để xem thread_cache_size và connection churn, nhưng không phải lý do tự động tăng cache vô hạn.

Thread cache chỉ giảm chi phí tạo server thread. Application connection pool vẫn cần thiết để giảm handshake, authentication và session setup lặp lại.

## 8. Chọn pool size bằng định luật Little

Định luật Little mô tả mối quan hệ giữa throughput, thời gian ở trong hệ thống và số công việc trung bình đang tồn tại:

\[
L = \lambda \times W
\]

Trong đó:
- \(L\): số operation trung bình đang đồng thời trong hệ thống.
- \(\lambda\): throughput (operation/giây).
- \(W\): thời gian trung bình một operation ở trong hệ thống (giây).

Đối với connection pool, nếu một transaction giữ một connection trong suốt thời gian xử lý database, có thể ước lượng số connection đang được sử dụng trung bình bằng:

\[
C_{active,avg} \approx TPS \times T_{hold}
\]

Ví dụ:
- Mục tiêu 300 transaction/giây.
- Mỗi transaction giữ connection trung bình 40 ms = 0,04 giây.

\[
C_{active,avg} \approx 300 \times 0.04 = 12
\]

Trung bình cần khoảng 12 connection active trong điều kiện workload và thời gian giữ connection như giả định.

Đây là điểm khởi đầu để benchmark, không phải công thức chốt maximumPoolSize. Cần thêm:
- Burst và phân bố arrival.
- p95/p99 thời gian giữ connection.
- Tỷ lệ transaction dài.
- Thời gian query và lock wait.
- Năng lực CPU/I/O của MySQL.
- Số replica và worker.
- Headroom cho tác vụ nền và sự cố.

### 8.1. Dùng thời gian giữ connection, không chỉ thời gian SQL

Nếu request giữ connection 2 giây nhưng chỉ chạy SQL trong 50 ms rồi gọi HTTP API 1,5 giây, pool bị chiếm trong gần 2 giây. Đây là thiết kế giữ connection quá lâu.

Tách:
- Thời gian chờ lấy connection.
- Thời gian connection được giữ.
- Thời gian SQL thực thi.
- Thời gian chờ lock/I/O.
- Thời gian ứng dụng xử lý ngoài database.

Giảm thời gian giữ connection thường cải thiện capacity mà không cần tăng pool.

## 9. Benchmark pool size thay vì đoán

Một quy trình thực tế:
1. Chọn workload đại diện và dữ liệu đủ gần production.
2. Ghi baseline throughput, p50/p95/p99, error rate và DB resource.
3. Chạy với pool nhỏ, ví dụ 4 connection mỗi replica.
4. Tăng từng bước có kiểm soát, ví dụ 8, 12, 16.
5. Mỗi lần chạy đủ warm-up và thời gian ổn định.
6. Giữ số replica và traffic nhất quán.
7. Ghi application pool active/idle/pending/acquire wait.
8. Ghi MySQL Threads_connected/Threads_running, CPU, I/O, lock waits và memory.
9. Dừng tăng khi throughput không còn cải thiện hoặc latency/error tăng.
10. Chọn cấu hình có headroom và SLO tốt, không chỉ peak throughput cao nhất.

### 9.1. Ví dụ bảng benchmark

| Pool max mỗi replica | Throughput | p95 latency | Pending acquire | DB CPU | Nhận xét |
|---:|---:|---:|---:|---:|---|
| 4 | 180 TPS | 240 ms | Cao | 45% | Có thể pool đang giới hạn |
| 8 | 310 TPS | 170 ms | Thấp | 68% | Thông lượng cải thiện |
| 12 | 350 TPS | 190 ms | Thấp | 82% | Gần vùng bão hòa |
| 20 | 355 TPS | 420 ms | Tăng | 95% | Throughput gần như không tăng, latency xấu |

Số liệu chỉ minh họa. Kết luận cần dựa trên phép đo thực tế. Trong ví dụ, pool 20 không đem lại throughput đáng kể nhưng làm p95 tăng mạnh; đó là dấu hiệu tăng concurrency vượt khả năng xử lý hiệu quả của database.

## 10. Các chỉ số phải theo dõi ở application pool

Một dashboard pool nên có:

| Metric | Ý nghĩa | Dấu hiệu cần điều tra |
|---|---|---|
| Total connections | Tổng connection pool đang quản lý | Tăng bất thường hoặc sát maximum |
| Active connections | Connection đang được mượn | Luôn bằng maximum |
| Idle connections | Connection sẵn sàng | Bằng 0 kéo dài khi tải cao |
| Pending/waiting threads | Request đang chờ connection | Tăng và không giảm |
| Acquire latency | Thời gian lấy connection | p95/p99 tăng |
| Connection timeout count | Lần không lấy được connection đúng hạn | Tăng đột biến |
| Usage/hold duration | Thời gian giữ connection | Dài hơn thời gian SQL |
| Creation/close rate | Tốc độ tạo và đóng connection | Churn cao |
| Leak detection | Connection bị giữ quá lâu | Cảnh báo lặp lại |
| Validation failures | Connection không còn sử dụng được | Tăng sau idle/network event |

Không chỉ xem active connection. Nếu active cao nhưng acquire wait thấp và throughput ổn định, pool có thể đang hoạt động đúng. Nếu pending tăng, acquire p95 tăng và timeout xuất hiện, pool đang trở thành hàng đợi.

### 10.1. Pool wait khác query latency

Một request có thể mất:
- 100 ms chờ lấy connection.
- 20 ms chạy SQL.
- 10 ms xử lý kết quả.

Nếu chỉ đo SQL latency, dashboard có thể báo 20 ms dù người dùng chờ 130 ms. Hãy đo acquisition latency và end-to-end request latency riêng.

## 11. Cấu hình HikariCP trong ứng dụng Java

HikariCP là một JDBC connection pool phổ biến. Ví dụ cấu hình minh họa:

~~~java
HikariConfig config = new HikariConfig();

config.setJdbcUrl(
    "jdbc:mysql://mysql.internal:3306/app_db?connectTimeout=5000&socketTimeout=30000"
);
config.setUsername("app_user");
config.setPassword(System.getenv("DB_PASSWORD"));

config.setMaximumPoolSize(12);
config.setMinimumIdle(4);

config.setConnectionTimeout(1500);
config.setValidationTimeout(1000);

config.setIdleTimeout(300000);
config.setMaxLifetime(1500000);

// Chỉ bật nếu cần giữ connection idle khỏi bị network/server đóng.
config.setKeepaliveTime(120000);

HikariDataSource dataSource = new HikariDataSource(config);
~~~

Các giá trị tính bằng millisecond trong HikariCP. Đây là ví dụ, không phải cấu hình dùng chung cho mọi workload.

### 11.1. maximumPoolSize

Giới hạn tổng connection mà một pool có thể quản lý. Phải tính theo số replica và mọi pool khác cùng trỏ vào database.

Không đặt maximumPoolSize bằng max_connections của MySQL vì mỗi replica có pool riêng.

### 11.2. minimumIdle

Số connection nhàn rỗi pool cố gắng duy trì. Giá trị cao giúp sẵn sàng khi có burst nhưng giữ nhiều session idle trên MySQL. Tổng minimumIdle của tất cả replica cũng phải được tính vào ngân sách.

Nếu muốn pool có kích thước cố định, cấu hình minimumIdle bằng maximumPoolSize theo chính sách của HikariCP và đo tác động. Không cần giữ mọi connection mở nếu workload thưa.

### 11.3. connectionTimeout

Thời gian một thread chờ lấy connection từ pool trước khi nhận timeout. Đây không phải TCP connect timeout tới MySQL.

Nếu connection pool cạn, giảm connectionTimeout không làm database nhanh hơn; nó chỉ khiến request thất bại sớm hơn. Chọn giá trị phù hợp với request deadline và retry policy.

### 11.4. connectTimeout và socketTimeout

Đây là tham số JDBC driver (Connector/J), khác với pool timeout:
- connectTimeout: giới hạn thời gian thiết lập kết nối mạng.
- socketTimeout: giới hạn thời gian chờ dữ liệu trên socket theo driver.

Không đặt socketTimeout quá thấp khiến query hợp lệ bị cắt giữa chừng. Đặt theo SLO, query duration và hành vi retry.

### 11.5. idleTimeout, maxLifetime và keepaliveTime

- idleTimeout: pool có thể loại bỏ connection idle dư thừa sau khoảng thời gian cấu hình, nếu pool được phép co lại.
- maxLifetime: giới hạn tuổi tối đa của connection trước khi pool loại bỏ khi phù hợp; tránh trùng với timeout cưỡng bức của database/proxy/network.
- keepaliveTime: kiểm tra/giữ connection idle theo chu kỳ nếu được bật và phiên bản pool hỗ trợ.

Đặt maxLifetime thấp hơn giới hạn tuổi connection do proxy hoặc hạ tầng áp đặt. Nếu MySQL wait_timeout đóng session idle, có thể dùng idleTimeout phù hợp hoặc keepalive/validation; không nhầm wait_timeout với maxLifetime vì chúng đo hai điều kiện khác nhau.

### 11.6. Validation

Với JDBC 4 driver hỗ trợ Connection.isValid(), thường không cần cấu hình test query riêng. Chỉ dùng connectionTestQuery khi driver hoặc môi trường yêu cầu.

Validation giúp phát hiện connection stale, nhưng kiểm tra quá thường xuyên cũng tạo thêm round trip. Dùng cơ chế pool đã được hỗ trợ và theo dõi validation failure.

## 12. Lấy và trả connection đúng cách

Ví dụ Java JDBC:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
         "SELECT order_id, status FROM orders WHERE order_id = ?")) {

    statement.setLong(1, orderId);

    try (ResultSet resultSet = statement.executeQuery()) {
        if (resultSet.next()) {
            long id = resultSet.getLong("order_id");
            String status = resultSet.getString("status");
            // Xử lý kết quả nhanh, không giữ connection cho công việc ngoài DB.
        }
    }
}
~~~

Khi Connection được đóng trong try-with-resources, pool thường nhận lại connection thay vì đóng socket vật lý. Việc đóng statement/result set giúp giải phóng tài nguyên và tránh giữ connection lâu hơn cần thiết.

### 12.1. Không giữ connection khi gọi dịch vụ ngoài

Mẫu không tốt:

~~~java
try (Connection connection = dataSource.getConnection()) {
    Order order = loadOrder(connection, orderId);
    PaymentResult result = paymentClient.charge(order); // Có thể chờ mạng lâu.
    updatePayment(connection, orderId, result);
}
~~~

Trong ví dụ, connection và có thể cả transaction bị giữ trong lúc gọi payment API. Nếu API chậm, pool nhanh chóng cạn.

Thiết kế tốt hơn cần xác định ranh giới nghiệp vụ:
- Đọc dữ liệu và hoàn tất transaction ngắn.
- Gọi dịch vụ ngoài theo workflow phù hợp.
- Mở transaction mới để ghi kết quả nếu cần.
- Dùng idempotency/outbox/saga khi phải phối hợp nhiều hệ thống.

Không tách transaction một cách tùy tiện nếu cần bảo đảm atomicity; hãy thiết kế quy trình nghiệp vụ rõ ràng.

## 13. Transaction dài làm pool cạn

Một connection bị giữ trong transaction lâu sẽ không thể phục vụ request khác. Transaction dài còn có thể:
- Giữ row lock.
- Giữ metadata lock liên quan.
- Giữ read view và làm purge chậm.
- Tăng undo history.
- Làm tăng xác suất deadlock.
- Giữ connection dù query hiện tại đã kết thúc.

Ví dụ:
1. Ứng dụng mở transaction.
2. SELECT/UPDATE một số hàng.
3. Chờ user xác nhận.
4. Gọi API khác.
5. Sau vài giây mới COMMIT.

Trong thời gian đó, connection bị chiếm và lock có thể được giữ. Hãy tránh chờ người dùng hoặc network bên ngoài bên trong transaction.

Theo dõi:
- Transaction age.
- Connection usage duration.
- Idle-in-transaction session.
- Rows locked và lock wait.
- Pool pending count.

Pool lớn hơn có thể che giấu transaction dài trong ngắn hạn, nhưng không giải quyết nguyên nhân.

## 14. Session state và rò rỉ trạng thái giữa request

Connection pool tái sử dụng session. Vì vậy, session state do request trước thay đổi có thể ảnh hưởng request sau nếu không được reset.

Các trạng thái cần quan tâm:
- autocommit.
- transaction chưa kết thúc.
- transaction isolation level.
- read_only.
- time_zone.
- sql_mode.
- default schema.
- user variables.
- temporary tables.
- session system variables.
- prepared statements và session-level settings.

Ví dụ một request chạy:

~~~sql
SET time_zone = '+07:00';
SET @tenant_id = 42;
~~~

Nếu connection được trả về pool mà state không được reset, request tiếp theo có thể nhận session với timezone hoặc user variable cũ.

Quy tắc:
- Tránh thay session state nếu có thể dùng cấu hình connection chuẩn.
- Nếu phải thay đổi, khôi phục trước khi trả connection.
- Đảm bảo transaction luôn COMMIT hoặc ROLLBACK.
- Dùng pool có cơ chế reset được kiểm chứng với driver/version.
- Không giả định mọi biến session, temporary table hoặc user variable đều tự được khôi phục giống nhau.

### 14.1. Connection leak

Leak xảy ra khi ứng dụng mượn connection nhưng không trả lại, ví dụ:
- Exception đi qua nhánh không đóng connection.
- ResultSet/Statement không đóng.
- Async task giữ connection quá lâu.
- Connection lưu trong field hoặc ThreadLocal.
- Transaction không kết thúc.

Dùng try-with-resources, pool leak detection ở môi trường phù hợp và metric connection usage. Leak detection là cảnh báo điều tra, không phải cơ chế tự sửa mọi trường hợp.

## 15. wait_timeout và connection stale

MySQL có timeout cho session idle. Với connection noninteractive, wait_timeout thường là biến cần xem:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'wait_timeout';
SHOW GLOBAL VARIABLES LIKE 'interactive_timeout';
~~~

JDBC connection thường là noninteractive. Nếu server đóng connection do idle timeout trong lúc pool vẫn nghĩ connection còn hợp lệ, ứng dụng có thể nhận lỗi communications link failure khi mượn lại connection.

Các biện pháp:
- Đặt idleTimeout của pool phù hợp với wait_timeout và timeout của proxy/network.
- Dùng keepalive/validation nếu cần.
- Đặt maxLifetime thấp hơn giới hạn tuổi connection cưỡng bức ở hạ tầng.
- Bắt và xử lý lỗi kết nối theo transaction boundary.
- Không retry một transaction không idempotent mà không xác định kết quả commit.

### 15.1. Không retry mù khi connection mất

Nếu connection bị mất lúc COMMIT, client có thể không biết transaction đã commit ở server hay chưa. Retry toàn bộ request có thể tạo đơn hàng hoặc thanh toán trùng.

Dùng idempotency key, unique business key hoặc transaction status lookup để xử lý kết quả không chắc chắn. Connection pool không thể giải quyết ambiguity của commit.

## 16. Memory và tài nguyên theo connection

Mỗi connection có overhead quản lý session/thread và có thể dùng các buffer theo hoạt động. Một số buffer được cấp phát khi query cần, không nhất thiết toàn bộ được cấp ngay khi connection mở.

Ví dụ biến cần hiểu:
- thread_stack.
- net_buffer_length và max_allowed_packet.
- sort_buffer_size.
- join_buffer_size.
- read_buffer_size.
- read_rnd_buffer_size.
- Các giới hạn temporary table và TempTable engine.
- Memory của prepared statement, session và instrumentation.

Không lấy tổng tất cả biến buffer nhân max_connections rồi coi đó là memory usage thực tế; cũng không bỏ qua rủi ro vì nhiều query đồng thời có thể cấp phát buffer lớn.

### 16.1. max_connections không miễn phí

Tăng max_connections cho phép nhiều session hơn nhưng không tự tạo thêm RAM, CPU, IOPS hoặc năng lực lock manager. Nếu ứng dụng mở hàng nghìn connection nhưng chỉ database xử lý hiệu quả một phần nhỏ, server vẫn phải quản lý các session dư thừa.

Tính ngân sách memory theo:
- Base memory của mysqld.
- InnoDB buffer pool.
- Per-connection/session overhead.
- Buffer được cấp theo query.
- Temporary table theo concurrency.
- Performance Schema và sys overhead.
- Replication, background thread và plugin.
- OS page cache và các process khác.

Benchmark với peak concurrency và query shape đại diện.

## 17. max_connections và giới hạn theo account

Kiểm tra:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SHOW GLOBAL VARIABLES LIKE 'max_user_connections';
~~~

Có thể đặt giới hạn toàn server bằng cấu hình runtime hoặc startup option phù hợp. Thay đổi max_connections cần đánh giá RAM, file descriptor, thread và workload.

Giới hạn theo account giúp một user không chiếm hết connection:

~~~sql
ALTER USER 'app_user'@'%'
    WITH MAX_USER_CONNECTIONS 40;
~~~

Giới hạn account không thay thế ngân sách pool toàn hệ thống. Nếu nhiều account cùng tồn tại, tổng quota vẫn có thể vượt max_connections.

Một số phiên bản MySQL có cơ chế dành kết nối quản trị cho account có quyền phù hợp khi server đạt giới hạn. Kiểm tra quyền và tài liệu phiên bản cụ thể; không dùng slot khẩn cấp làm capacity cho ứng dụng.

### 17.1. Khi gặp Too many connections

Không chỉ tăng max_connections ngay. Kiểm tra:
1. Threads_connected hiện tại và Max_used_connections.
2. Application pool active/idle/pending trên từng replica.
3. Số replica thực tế và surge trong rolling update.
4. Connection churn và Aborted_connects.
5. Session idle hoặc transaction dài.
6. Client/job bất thường.
7. CPU, memory, I/O và Threads_running.
8. Connection budget cho quản trị và monitoring.

Nếu cần khôi phục quyền quản trị, dùng account/endpoint khẩn cấp đã chuẩn bị trước. Sau incident, sửa pool budget hoặc leak thay vì chỉ nâng giới hạn.

## 18. Proxy và multiplexing connection

Một proxy database có thể định tuyến, cân bằng hoặc quản lý kết nối backend. Một số proxy như ProxySQL có khả năng multiplex nhiều frontend session qua ít backend connection trong những điều kiện nhất định.

Tuy nhiên, multiplexing bị hạn chế khi session cần trạng thái riêng hoặc transaction đang hoạt động, ví dụ:
- Transaction chưa kết thúc.
- Temporary table.
- User variables.
- Session system variables.
- Prepared statement/session state tùy proxy.
- Lock hoặc cursor/session feature cần duy trì backend affinity.

MySQL Router chủ yếu cung cấp routing giữa client và topology; không mặc định xem nó là connection multiplexer.

Nếu dùng proxy:
- Tính cả frontend và backend connection.
- Xác định pooling ở tầng ứng dụng, proxy hay cả hai.
- Kiểm tra session pinning/multiplexing rules.
- Đo backend connection count và queue.
- Kiểm thử transaction, prepared statements và session variables.
- Không giả định proxy cho phép mở pool ứng dụng vô hạn.

## 19. Connection pool và autoscaling

Mỗi replica mới thường tạo pool riêng. Khi autoscaling tăng replica, tổng connection có thể tăng ngay cả khi traffic chưa tăng tương ứng.

Ví dụ:
- 4 replica × pool max 20 = 80.
- Autoscaling lên 10 replica × pool max 20 = 200.
- Rolling update có surge lên 12 replica = 240.

Nếu MySQL chỉ dành 180 connection cho workload ứng dụng, scale-out có thể làm các replica tranh connection và gây lỗi đồng loạt.

Thiết kế:
- Đặt maximum replicas trong capacity model.
- Đặt pool size theo tổng budget, không theo từng pod riêng lẻ.
- Cân nhắc pool nhỏ hơn cho worker ít ưu tiên.
- Giới hạn tốc độ scale-out nếu database là bottleneck.
- Dùng backpressure ở tầng ứng dụng.
- Theo dõi tổng pool connections across replicas.
- Có circuit breaker/load shedding khi DB quá tải.

Scale application không tự động scale database. Hai tầng phải có capacity plan tương ứng.

## 20. Đọc connection và thread bằng Performance Schema

Có thể xem foreground thread:

~~~sql
SELECT
    THREAD_ID,
    PROCESSLIST_ID,
    PROCESSLIST_USER,
    PROCESSLIST_HOST,
    PROCESSLIST_DB,
    PROCESSLIST_COMMAND,
    PROCESSLIST_TIME,
    PROCESSLIST_STATE
FROM performance_schema.threads
WHERE TYPE = 'FOREGROUND'
ORDER BY PROCESSLIST_TIME DESC;
~~~

Một số thread có PROCESSLIST_ID NULL hoặc thuộc background worker. Đừng cộng tất cả thread trong Performance Schema rồi gọi đó là số client connection.

Kết hợp với processlist:

~~~sql
SHOW FULL PROCESSLIST;
~~~

Hoặc view tiện ích nếu sys schema có sẵn:

~~~sql
SELECT *
FROM sys.processlist
ORDER BY time DESC;
~~~

View và cột cụ thể phụ thuộc phiên bản sys schema. Dùng DESCRIBE/SHOW CREATE VIEW trước khi viết script vận hành.

## 21. Cấu hình và quan sát theo cửa sổ thời gian

Không chỉ nhìn một snapshot. Lấy các chỉ số ở nhiều thời điểm và tính delta:

\[
ConnectionRate = \frac{\Delta Connections}{\Delta t}
\]

\[
ThreadCreationRate = \frac{\Delta ThreadsCreated}{\Delta t}
\]

\[
PeakConnectionUtilization =
\frac{MaxUsedConnections}{max\_connections}
\]

Ví dụ peak utilization 0,92 cho thấy server từng đạt 92% giới hạn. Đây là cảnh báo cần xem thời điểm peak và headroom, không nhất thiết là trạng thái hiện tại.

Nếu counter reset sau restart, không lấy delta xuyên qua lần reset. Ghi uptime, server_uuid và thời điểm snapshot.

### 21.1. Dashboard kết hợp hai phía

Dashboard tốt nên ghép:

| Application pool | MySQL |
|---|---|
| Active/idle/total | Threads_connected |
| Pending borrowers | Threads_running |
| Acquire latency | Statement latency |
| Connection timeout | Connection_errors_max_connections |
| Usage duration | Long transaction / lock waits |
| Create/close rate | Connections, Threads_created |
| Pool max across replicas | max_connections, Max_used_connections |

Nếu app pending cao nhưng MySQL còn CPU và Threads_running thấp, có thể pool nhỏ hoặc connection bị giữ ngoài DB. Nếu MySQL CPU/lock/I/O đã bão hòa, tăng pool có thể làm tình hình xấu hơn.

## 22. Các tình huống chẩn đoán thường gặp

### 22.1. Pool timeout nhưng MySQL chưa đạt max_connections

Nguyên nhân có thể:
- Pool max quá nhỏ.
- Connection bị leak.
- Transaction dài.
- Request giữ connection trong lúc gọi dịch vụ ngoài.
- Một số connection bị kẹt do query chậm.
- Pool có validation hoặc connection creation chậm.

Hướng xử lý:
1. Xem active, idle, pending và usage duration.
2. Tìm thread đang giữ connection.
3. Đối chiếu query latency và transaction age.
4. Kiểm tra code path đóng connection.
5. Chỉ tăng pool sau khi xác nhận DB còn capacity.

### 22.2. Too many connections

Nguyên nhân có thể:
- Tổng pool các replica vượt ngân sách.
- Autoscaling/rolling deployment tạo surge.
- Không dùng pool hoặc connection churn.
- Pool minIdle quá cao.
- Job/script tạo connection riêng.
- Session idle không được thu hồi.

Hướng xử lý:
1. Xem Threads_connected và Max_used_connections.
2. Phân nhóm user/host.
3. Tính tổng pool max theo replica.
4. Kiểm tra connection rate và thread creation rate.
5. Khôi phục kết nối quản trị bằng account dự phòng.
6. Hạ pool/scale ứng dụng có kiểm soát hoặc kết thúc session được xác nhận an toàn.
7. Điều chỉnh ngân sách và cảnh báo.

### 22.3. Throughput không tăng khi tăng pool

Nguyên nhân thường là bottleneck đã chuyển sang database:
- CPU gần bão hòa.
- Storage latency cao.
- Lock contention.
- Query scan nhiều.
- Transaction dài.
- Buffer pool miss.
- I/O hoặc network.

Hãy xem statement digest, EXPLAIN, waits, InnoDB lock diagnostics và OS metrics. Không tiếp tục tăng pool chỉ để giảm pending nếu DB đã quá tải.

### 22.4. Threads_connected cao nhưng Threads_running thấp

Có thể ứng dụng giữ nhiều connection idle trong pool. Điều này không tự động là lỗi nếu ngân sách còn đủ, nhưng có thể:
- Chiếm connection slot.
- Tăng session overhead.
- Làm giảm headroom cho batch/DBA.
- Che giấu pool minIdle quá cao.

Đánh giá số connection thực sự cần, idleTimeout và tổng số replica.

### 22.5. Threads_created tăng nhanh

Có thể do connection churn hoặc thread_cache_size không phù hợp. So sánh delta Threads_created với delta Connections, kiểm tra pool lifecycle và restart. Không nhầm tăng Threads_created với tăng số query đang chạy.

## 23. Runbook chọn và điều chỉnh pool size

1. Xác định max_connections và connection dành cho tác vụ không thuộc ứng dụng.
2. Liệt kê mọi ứng dụng, worker, job, monitoring và công cụ quản trị kết nối tới instance.
3. Tính maximum replicas, rolling surge và autoscaling ceiling.
4. Tính tổng pool max và minimumIdle trên toàn bộ replica.
5. Đo throughput, p95/p99, thời gian giữ connection và thời gian SQL.
6. Dùng Little's Law để ước lượng concurrency trung bình.
7. Benchmark pool ở nhiều mức trong môi trường đại diện.
8. Quan sát active, idle, pending, acquire latency và timeout.
9. Quan sát Threads_connected, Threads_running, CPU, memory, I/O, lock wait và error counters.
10. Chọn pool max đạt SLO với headroom, không theo số connection lớn nhất có thể.
11. Đặt acquisition timeout theo request deadline.
12. Đặt idleTimeout/maxLifetime phù hợp với MySQL và proxy/network.
13. Kiểm thử restart, failover, rolling deployment và autoscaling.
14. Đặt cảnh báo trước khi đạt max_connections.
15. Ghi lại cấu hình, baseline và điều kiện rollback.

## 24. Bài tập thực hành

### Bài 1: Đọc trạng thái connection

Chạy SHOW GLOBAL STATUS cho Threads_connected, Threads_running, Threads_created, Threads_cached, Connections và Max_used_connections. Mở thêm một số session trong lab rồi quan sát thay đổi.

### Bài 2: So sánh connection và thread cache

Tạo workload kết nối/ngắt kết nối liên tục trong lab. Quan sát Connections và Threads_created trước/sau khi thay đổi thread_cache_size. Giải thích vì sao thread cache không thay thế application pool.

### Bài 3: Tính ngân sách nhiều replica

Giả sử có 8 API replica, 4 worker replica và 2 batch job. Tính tổng connection tối đa theo pool size khác nhau. Dành ngân sách cho monitoring, DBA và rolling deployment.

### Bài 4: Áp dụng Little's Law

Đo throughput và thời gian giữ connection trung bình. Tính concurrency trung bình. So sánh với số active connection thực tế của pool và giải thích chênh lệch.

### Bài 5: Benchmark pool size

Chạy cùng workload với pool max 4, 8, 12 và 16. Ghi throughput, p95/p99, acquire wait, pending borrowers, DB CPU và Threads_running. Chọn mức phù hợp với SLO.

### Bài 6: Mô phỏng pool exhaustion

Trong lab, giữ connection lâu có chủ đích. Quan sát pending và acquisition timeout. Sửa code để connection được trả sớm và so sánh.

### Bài 7: Mô phỏng connection leak

Tạo một nhánh code không đóng connection trong môi trường thử nghiệm. Quan sát pool active tăng dần. Sửa bằng try-with-resources và xác nhận pool phục hồi.

### Bài 8: Session state contamination

Mượn connection, thay time_zone và user variable, trả connection rồi mượn lại. Kiểm tra state còn tồn tại hay được reset theo pool/driver. Thiết kế cleanup rõ ràng.

### Bài 9: Stale connection

Trong lab, đặt wait_timeout thấp hơn idle period của pool. Quan sát connection stale và kiểm tra validation/keepalive/idleTimeout. Không thay đổi timeout production để thử.

### Bài 10: Rolling deployment budget

Tính connection khi replica cũ và mới chạy song song. Mô phỏng scale-out và xác định thời điểm tổng pool có thể vượt max_connections.

### Bài 11: Connection limit theo user

Đặt MAX_USER_CONNECTIONS cho account lab. Tạo nhiều session và quan sát giới hạn. Xác định tác động khi nhiều ứng dụng dùng chung account.

### Bài 12: Incident Too many connections

Giả lập pool tổng vượt ngân sách. Dùng status variables, processlist và metrics ứng dụng để xác định nguồn connection. Viết runbook khôi phục có kiểm soát.

## 25. Checklist trước khi triển khai production

- [ ] Connection pool được tạo ở cấp ứng dụng/process, không phải mỗi request.
- [ ] Connection chỉ được giữ trong thời gian cần thao tác database.
- [ ] Mọi Connection/Statement/ResultSet được đóng đúng cách.
- [ ] Transaction luôn kết thúc bằng COMMIT hoặc ROLLBACK.
- [ ] Không giữ connection khi chờ user hoặc gọi dịch vụ ngoài.
- [ ] Đã tính tổng pool max của mọi replica và worker.
- [ ] Đã tính autoscaling ceiling và rolling deployment surge.
- [ ] Tổng connection budget có headroom cho DBA, monitoring và tác vụ nền.
- [ ] Đã phân biệt connection count, active operation và throughput.
- [ ] Đã phân biệt application pool với MySQL thread cache/thread pool.
- [ ] Đã đo active, idle, pending, acquire latency và usage duration.
- [ ] Đã theo dõi Threads_connected, Threads_running, Max_used_connections và connection errors.
- [ ] Đã đo connection churn và Threads_created theo delta.
- [ ] Đã dùng Little's Law làm ước lượng ban đầu, không coi là công thức cố định.
- [ ] Đã benchmark pool size với workload đại diện.
- [ ] Đã theo dõi throughput cùng p95/p99 latency.
- [ ] Đã đặt connectionTimeout theo request deadline.
- [ ] Đã phân biệt pool timeout với JDBC connectTimeout/socketTimeout.
- [ ] Đã đồng bộ idleTimeout/keepalive/maxLifetime với MySQL và proxy/network.
- [ ] Đã kiểm tra stale connection và validation behavior.
- [ ] Đã kiểm soát session state khi tái sử dụng connection.
- [ ] Đã đánh giá per-connection memory và max_connections.
- [ ] Đã đặt cảnh báo trước khi chạm max_connections.
- [ ] Đã có account quản trị khẩn cấp và runbook Too many connections.
- [ ] Đã kiểm thử failover, restart, scale-out và rolling deployment.

## 26. Kết luận

Connection pool là cơ chế giới hạn và tái sử dụng session MySQL ở tầng ứng dụng. Pool quá nhỏ tạo queue và làm giảm thông lượng; pool quá lớn có thể làm database bão hòa, tăng lock contention, memory pressure và tail latency. Kích thước hợp lý phải được tính trên toàn bộ replica, worker và batch job, đồng thời tính cả surge khi autoscaling hoặc rolling deployment.

Dùng định luật Little để ước lượng concurrency trung bình từ throughput và thời gian giữ connection, sau đó benchmark nhiều mức pool với cùng workload. Theo dõi cả application pool metrics lẫn MySQL status counters; phân biệt connection mở với operation đang chạy, pool wait với query latency và thread cache với connection pool. Giữ transaction ngắn, trả connection đúng cách, làm sạch session state và đồng bộ timeout với server/proxy/network.

Không tăng max_connections hoặc pool size chỉ để xóa cảnh báo. Trước hết xác định bottleneck, tính capacity budget và giữ headroom cho quản trị. Một cấu hình tốt đạt throughput mục tiêu với p95/p99 phù hợp, connection acquisition wait thấp và database vẫn còn khả năng chịu burst.

## Tài liệu tham khảo chính thức

- [MySQL 8.4 Reference Manual – Connection Interfaces](https://dev.mysql.com/doc/refman/8.4/en/connection-interfaces.html)
- [MySQL 8.4 Reference Manual – Server System Variables: max_connections](https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html#sysvar_max_connections)
- [MySQL 8.4 Reference Manual – Server Status Variables](https://dev.mysql.com/doc/refman/8.4/en/server-status-variables.html)
- [MySQL 8.4 Reference Manual – Thread Information](https://dev.mysql.com/doc/refman/8.4/en/thread-information.html)
- [MySQL 8.4 Reference Manual – Thread Cache](https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html#sysvar_thread_cache_size)
- [MySQL 8.4 Reference Manual – Limits on Number of Connections](https://dev.mysql.com/doc/refman/8.4/en/connection-interfaces.html#connection-interfaces-max-connections)
- [MySQL 8.4 Reference Manual – Account Resource Limits](https://dev.mysql.com/doc/refman/8.4/en/user-resources.html)
- [MySQL 8.4 Reference Manual – Performance Schema Threads Table](https://dev.mysql.com/doc/refman/8.4/en/performance-schema-threads-table.html)
- [MySQL 8.4 Reference Manual – Performance Schema Connection Control](https://dev.mysql.com/doc/refman/8.4/en/connection-control.html)
- [HikariCP – Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby)
- [HikariCP – Pool Sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing)
- [MySQL Connector/J – Configuration Properties](https://dev.mysql.com/doc/connector-j/en/connector-j-reference-configuration-properties.html)


# Hết kết nối và sự cố dây chuyền từ pool ứng dụng

Pool kết nối giúp ứng dụng tái sử dụng các kết nối PostgreSQL thay vì mở và đóng kết nối cho từng yêu cầu. Pool cũng giới hạn số phiên mà một tiến trình ứng dụng có thể đồng thời sử dụng. Khi cấu hình phù hợp, pool làm giảm chi phí thiết lập kết nối và bảo vệ database khỏi số lượng client tăng đột biến.

Tuy nhiên, pool có thể trở thành điểm nghẽn. Khi tất cả kết nối trong pool đều đang bận, yêu cầu mới phải chờ. Nếu truy vấn chậm, transaction giữ kết nối lâu hoặc ứng dụng mở quá nhiều pool trên nhiều replica, thời gian chờ sẽ tăng. Request timeout có thể kích hoạt retry, retry làm tăng tải, các worker tiếp tục chiếm kết nối và một sự cố ban đầu có thể lan thành lỗi trên toàn hệ thống.

Bài này giải thích cách nhận biết pool bị cạn kết nối, phân biệt sự cố ở ứng dụng với giới hạn của PostgreSQL, tìm nguyên nhân giữ kết nối lâu và xử lý tình huống dây chuyền. Các ví dụ dùng PostgreSQL và một số cấu hình Java phổ biến; tên tham số của pool khác có thể khác nhau.

## 1. Pool kết nối hoạt động như thế nào?

Khi ứng dụng cần truy cập database, nó yêu cầu một kết nối từ pool. Nếu pool có kết nối rảnh, pool giao kết nối đó cho ứng dụng. Nếu mọi kết nối đều đang được sử dụng và pool đã đạt giới hạn tối đa, yêu cầu phải chờ cho đến khi có kết nối được trả về hoặc hết thời gian chờ.

Luồng cơ bản:

1. Một request hoặc worker yêu cầu kết nối.
2. Pool cấp một kết nối rảnh hoặc đưa yêu cầu vào hàng đợi chờ.
3. Ứng dụng thực thi SQL và xử lý kết quả.
4. Ứng dụng commit hoặc rollback transaction.
5. Ứng dụng đóng đối tượng connection; pool đưa kết nối vật lý trở lại trạng thái rảnh để tái sử dụng.

Trong ứng dụng dùng pool, gọi close trên connection được mượn thường trả kết nối về pool, không đóng socket PostgreSQL ngay lập tức. Nếu code quên đóng connection, pool không thể biết kết nối đã hết nhu cầu và sẽ xem nó vẫn đang được sử dụng.

Pool thường có các giới hạn:

- **Maximum pool size:** số kết nối tối đa pool có thể quản lý.
- **Minimum idle:** số kết nối rảnh tối thiểu pool cố gắng duy trì.
- **Connection acquisition timeout:** thời gian tối đa một yêu cầu chờ để mượn kết nối.
- **Idle timeout:** thời gian một kết nối rảnh có thể tồn tại trước khi bị thu hồi, tùy cấu hình và loại pool.
- **Maximum lifetime:** tuổi thọ tối đa của kết nối vật lý trước khi pool thay thế nó.

Các tham số này giải quyết những vấn đề khác nhau. Tăng maximum pool size làm tăng mức đồng thời có thể gửi đến database, nhưng cũng làm tăng số phiên PostgreSQL và mức tranh chấp tài nguyên. Tăng connection acquisition timeout chỉ làm request chờ lâu hơn; nó không tạo thêm năng lực xử lý cho database.

## 2. Hai nơi có thể hết kết nối

Cụm từ “hết connection” thường chỉ hai tình trạng khác nhau. Cần phân biệt chúng trước khi thay đổi cấu hình.

### 2.1. Pool ứng dụng đã đầy

Pool có thể đã sử dụng hết số connection cho phép dù PostgreSQL vẫn còn khả năng nhận thêm kết nối. Khi đó, yêu cầu mới xếp hàng trong ứng dụng.

Dấu hiệu thường thấy:

- Log ứng dụng báo timeout khi lấy connection từ pool.
- Số active connection của pool bằng maximum pool size.
- Số pending hoặc waiting request tăng.
- Thời gian chờ lấy connection tăng, trong khi PostgreSQL chưa đạt max_connections.
- Database có thể vẫn hoạt động bình thường với các client khác.

Ví dụ log có thể chứa thông báo như “Connection is not available, request timed out” hoặc “Timeout waiting for connection from pool”. Nội dung cụ thể tùy thư viện.

Trong tình huống này, tăng max_connections của PostgreSQL có thể không giúp gì, vì ứng dụng chưa mở thêm kết nối đến server. Cần tìm vì sao các kết nối đang mượn chưa được trả về hoặc vì sao tốc độ xử lý truy vấn thấp hơn tốc độ request đến.

### 2.2. PostgreSQL đã đạt giới hạn kết nối

PostgreSQL giới hạn số client đồng thời bằng cấu hình max_connections, cùng các slot được dành riêng theo cấu hình và phiên bản. Khi không còn slot phù hợp, kết nối mới bị từ chối. Ứng dụng có thể ghi log lỗi như “too many connections” hoặc lỗi không thể mở kết nối.

Dấu hiệu:

- Log PostgreSQL cho biết đã đạt giới hạn kết nối.
- Nhiều ứng dụng hoặc pool khác nhau cùng không thể kết nối.
- Tổng số backend gần giới hạn cấu hình.
- Kết nối quản trị thông thường cũng có thể thất bại nếu không còn slot dành cho chúng.

Nguyên nhân có thể là một pool được đặt quá lớn, số replica tăng, nhiều service cùng kết nối trực tiếp, job nền tạo kết nối riêng hoặc connection leak. Một hệ thống có nhiều pool nhỏ vẫn có thể vượt giới hạn khi cộng tổng số replica.

### 2.3. Phân biệt bằng số liệu

| Quan sát | Pool ứng dụng đầy | PostgreSQL hết slot |
|---|---|---|
| Active connection trong pool | Bằng giới hạn hoặc gần giới hạn | Có thể bằng giới hạn |
| Pending request trong pool | Thường tăng | Có thể tăng do kết nối mới bị từ chối |
| PostgreSQL max_connections | Có thể còn nhiều slot | Đã chạm giới hạn hữu dụng |
| Lỗi điển hình | Timeout khi mượn connection | Too many connections / connection refused |
| Phạm vi ảnh hưởng | Có thể chỉ một instance hoặc service | Có thể ảnh hưởng nhiều ứng dụng |

Cần xem cả metric pool và số liệu phía PostgreSQL. Chỉ nhìn một phía có thể dẫn đến chẩn đoán sai.

## 3. Những nguyên nhân thường làm pool cạn kết nối

### 3.1. Truy vấn chậm hoặc truy vấn chờ khóa

Một kết nối được giữ trong suốt thời gian ứng dụng sử dụng nó. Nếu SQL chạy lâu, kết nối không thể phục vụ request khác trong khoảng thời gian đó. Nếu nhiều request cùng chạy truy vấn chậm, pool có thể đầy dù số request mỗi giây không tăng.

Truy vấn cũng có thể đang chờ khóa thay vì sử dụng CPU. Ví dụ, một transaction cập nhật một hàng rồi giữ transaction mở; các transaction khác cần cập nhật cùng hàng phải chờ. Mỗi request chờ vẫn có thể giữ một connection trong pool.

Cần kiểm tra thời gian truy vấn, wait event, lock và kế hoạch thực thi. Tăng pool size trong lúc truy vấn bị chậm có thể khiến nhiều truy vấn cùng tranh CPU, I/O và khóa hơn.

### 3.2. Transaction mở quá lâu

Transaction nên bao quanh phần công việc database cần tính nhất quán. Nếu ứng dụng mở transaction rồi thực hiện gọi HTTP, đọc file, chờ người dùng hoặc xử lý nghiệp vụ dài, connection có thể bị giữ trong suốt thời gian chờ đó.

Ví dụ luồng không tốt:

~~~text
Mượn connection
BEGIN
UPDATE inventory
Gọi dịch vụ thanh toán qua HTTP
Chờ phản hồi 8 giây
UPDATE orders
COMMIT
Trả connection về pool
~~~

Nếu dịch vụ HTTP chậm, transaction và connection đều bị giữ lâu. Các transaction khác có thể phải chờ khóa trên inventory, làm pool đầy nhanh hơn.

Nên tách phần xử lý không cần nằm trong transaction ra ngoài. Nếu nghiệp vụ cần phối hợp database và dịch vụ bên ngoài, cân nhắc thiết kế trạng thái trung gian, outbox hoặc saga thay vì giữ transaction database trong suốt một cuộc gọi mạng.

### 3.3. Connection leak trong ứng dụng

Connection leak xảy ra khi ứng dụng mượn connection nhưng không trả lại pool. Các tình huống phổ biến:

- Không đóng connection trong nhánh exception.
- ResultSet hoặc Statement giữ connection sống lâu hơn dự kiến.
- Transaction không được commit hoặc rollback khi xử lý lỗi.
- Luồng bất đồng bộ nhận connection nhưng không đóng trong callback.
- Code trả về từ hàm trước khi chạy phần cleanup.
- Một connection được giữ trong biến dùng chung hoặc cache ngoài phạm vi request.

Trong Java, try-with-resources giúp đóng tài nguyên ngay cả khi có exception:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
         connection.prepareStatement(
             "SELECT order_id, status FROM orders WHERE order_id = ?")) {

    statement.setLong(1, orderId);

    try (ResultSet resultSet = statement.executeQuery()) {
        if (resultSet.next()) {
            long id = resultSet.getLong("order_id");
            String status = resultSet.getString("status");
            // Map the row to the application model.
        }
    }
}
~~~

Nếu dùng Spring transaction management, để framework quản lý transaction theo ranh giới service và tránh tự đóng connection được framework quản lý. Cần bảo đảm mọi đường đi thành công và thất bại đều kết thúc transaction.

Leak thường biểu hiện bằng số active connection tăng dần theo thời gian, trong khi throughput không tăng tương ứng. Nếu pool có leak detection, log của pool có thể chỉ ra stack trace nơi connection được mượn và giữ quá lâu. Công cụ này hữu ích khi điều tra, nhưng ngưỡng quá thấp có thể tạo cảnh báo giả cho truy vấn hợp lệ chạy lâu.

### 3.4. Pool được nhân lên theo số replica

Maximum pool size thường là giới hạn của một instance ứng dụng, không phải toàn bộ hệ thống. Nếu có nhiều replica, tổng kết nối tối đa là tổng các pool trên tất cả replica và worker.

Ví dụ:

| Thành phần | Số instance | Pool tối đa mỗi instance | Tổng tối đa |
|---|---:|---:|---:|
| API service | 8 | 20 | 160 |
| Worker service | 4 | 12 | 48 |
| Scheduler | 2 | 5 | 10 |
| Tổng | 14 | | 218 |

Nếu PostgreSQL có ngân sách 180 kết nối cho các workload ứng dụng, cấu hình trên có thể vượt ngân sách khi tất cả pool cùng mở đầy đủ kết nối. Điều này có thể xảy ra sau một lần scale out dù từng instance vẫn dùng cấu hình cũ.

Khi lập kế hoạch, tính cả job migration, tác vụ quản trị, replication, monitoring, công cụ BI và những service khác. Không lấy max_connections chia cho một pool rồi bỏ qua các client còn lại.

### 3.5. Retry và timeout tạo tải khuếch đại

Một sự cố database có thể tạo vòng lặp:

1. Truy vấn chậm làm pool đầy.
2. Request chờ lấy connection rồi timeout.
3. Client hoặc gateway retry request.
4. Retry tạo thêm request và tiếp tục chờ connection.
5. Worker, thread và hàng đợi ứng dụng bị chiếm dụng.
6. Khi database hồi phục một phần, lượng retry đồng loạt đổ vào làm pool đầy trở lại.

Đây là retry storm. Nó biến một sự cố cục bộ thành sự cố dây chuyền ở API, worker, gateway và các dịch vụ phụ thuộc.

Retry chỉ phù hợp với lỗi tạm thời và thao tác có thể retry an toàn. Cần giới hạn số lần retry, dùng exponential backoff có jitter, đặt deadline tổng cho request và tránh retry đồng thời ở nhiều tầng. Một request không nên bị retry ở client, gateway, service và database wrapper mà không có ngân sách chung.

## 4. Quan sát pool và PostgreSQL

Chẩn đoán nên bắt đầu từ metric thay vì thay đổi cấu hình theo cảm tính. Cần theo dõi cả pool ở ứng dụng và backend ở PostgreSQL.

### 4.1. Metric quan trọng ở pool ứng dụng

Tùy thư viện, tên metric khác nhau, nhưng nên thu thập:

| Metric | Ý nghĩa | Cách đọc |
|---|---|---|
| Active connections | Kết nối đang được ứng dụng mượn | Tăng đến giới hạn cho thấy pool bận |
| Idle connections | Kết nối sẵn sàng cho request mới | Bằng 0 trong thời gian dài có thể là dấu hiệu nghẽn |
| Pending / waiting threads | Yêu cầu đang chờ connection | Tăng liên tục cho thấy nhu cầu vượt năng lực cấp connection |
| Acquisition time | Thời gian chờ mượn connection | P95/P99 tăng thường xuất hiện trước lỗi timeout |
| Usage duration | Thời gian connection được giữ | Tăng cho thấy truy vấn hoặc phần code giữ connection lâu |
| Timeout count | Số lần mượn connection thất bại do timeout | Tăng là tín hiệu người dùng có thể đã bị ảnh hưởng |
| Connection creation / failure | Tốc độ tạo connection và lỗi kết nối | Tăng đột biến có thể chỉ ra database hoặc mạng không ổn định |

Nên ghi nhận metric theo từng application instance và pool name. Nếu chỉ tổng hợp toàn hệ thống, có thể bỏ sót một replica bị leak hoặc cấu hình sai.

### 4.2. Đếm kết nối trên PostgreSQL

Có thể xem số backend theo trạng thái:

~~~sql
SELECT
    state,
    count(*) AS connections
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY state
ORDER BY connections DESC;
~~~

Xem số kết nối theo database, user, application và trạng thái:

~~~sql
SELECT
    datname,
    usename,
    application_name,
    state,
    count(*) AS connections
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY datname, usename, application_name, state
ORDER BY connections DESC;
~~~

So sánh tổng kết nối client với cấu hình:

~~~sql
SHOW max_connections;

SELECT count(*) AS current_client_connections
FROM pg_stat_activity
WHERE backend_type = 'client backend';
~~~

pg_stat_activity cung cấp một dòng cho mỗi server process và cho biết trạng thái hiện tại. Cột application_name hữu ích nếu từng service đặt tên riêng trong connection string hoặc cấu hình driver. Nếu mọi ứng dụng dùng cùng một tên, việc phân biệt nguồn kết nối sẽ khó hơn.

Một số trạng thái cần chú ý:

- **active:** backend đang thực thi câu lệnh.
- **idle:** backend đang chờ câu lệnh mới, không có transaction đang mở.
- **idle in transaction:** transaction còn mở nhưng hiện không chạy câu lệnh.
- **idle in transaction (aborted):** transaction đã gặp lỗi nhưng chưa được kết thúc bằng rollback.

Một lượng lớn idle connection có thể chỉ là pool giữ kết nối sẵn sàng. Một lượng lớn idle in transaction thường đáng điều tra vì transaction chưa kết thúc có thể giữ lock và ngăn vacuum thu hồi phiên bản hàng cũ.

### 4.3. Tìm truy vấn chạy lâu và transaction cũ

Truy vấn sau liệt kê backend đang hoạt động cùng thời gian truy vấn:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    now() - xact_start AS transaction_age,
    left(query, 500) AS query_sample
FROM pg_stat_activity
WHERE backend_type = 'client backend'
  AND state IS DISTINCT FROM 'idle'
ORDER BY xact_start NULLS LAST, query_start NULLS LAST;
~~~

Các trường wait_event_type và wait_event giúp phân biệt backend đang chờ lock, I/O, client hoặc một sự kiện khác. query_age cho biết câu lệnh đã chạy bao lâu; transaction_age cho biết transaction đã mở bao lâu. Một câu lệnh vừa bắt đầu trong transaction cũ vẫn có thể giữ trạng thái và lock từ các thao tác trước.

Tìm transaction idle lâu:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    now() - xact_start AS transaction_age,
    state,
    left(query, 500) AS last_query
FROM pg_stat_activity
WHERE state LIKE 'idle in transaction%'
ORDER BY xact_start;
~~~

Không nên kết luận một truy vấn bị treo chỉ dựa trên tuổi của nó. Cần xem wait event, lock, kế hoạch và vai trò của transaction trước khi can thiệp.

### 4.4. Kiểm tra giới hạn và cấu hình timeout

Một số lệnh giúp kiểm tra cấu hình server:

~~~sql
SHOW max_connections;
SHOW superuser_reserved_connections;
SHOW statement_timeout;
SHOW lock_timeout;
SHOW idle_in_transaction_session_timeout;
SHOW idle_session_timeout;
~~~

idle_session_timeout có mặt ở các phiên bản PostgreSQL mới; hãy kiểm tra tài liệu của phiên bản đang vận hành trước khi dựa vào tham số này. Cấu hình timeout cần phù hợp với workload và loại client. Đặc biệt, việc ngắt idle session có thể ảnh hưởng đến ứng dụng dùng connection pool nếu pool không phát hiện và loại bỏ kết nối đã bị server đóng.

## 5. Tìm chuỗi nguyên nhân gây cạn pool

Khi có cảnh báo, hãy ghép số liệu theo cùng mốc thời gian. Một biểu đồ active connection đơn lẻ không đủ để phân biệt truy vấn chậm, leak, scale out hay retry storm.

| Dấu hiệu | Khả năng cần điều tra |
|---|---|
| Active connections tăng dần qua nhiều giờ, usage duration dài | Connection leak hoặc code giữ connection |
| Active tăng cùng query latency và wait event lock | Tranh chấp khóa hoặc transaction dài |
| Kết nối tăng ngay sau khi tăng số replica | Tổng pool theo replica vượt ngân sách |
| Pending threads và timeout tăng, DB vẫn còn slot | Pool quá nhỏ hoặc connection bị giữ lâu |
| Nhiều service đồng thời báo too many connections | PostgreSQL đạt giới hạn hoặc có client khác mở quá nhiều |
| Lỗi tăng mạnh sau sự cố mạng, request retry dày đặc | Retry storm hoặc reconnect storm |
| Idle in transaction tăng | Transaction không được kết thúc hoặc ứng dụng chờ bên ngoài khi giữ transaction |

### 5.1. Xem lock đang chặn nhau

Có thể tìm blocker bằng hàm pg_blocking_pids:

~~~sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.application_name AS blocked_app,
    now() - blocked.query_start AS blocked_for,
    blocker.pid AS blocker_pid,
    blocker.application_name AS blocker_app,
    now() - blocker.xact_start AS blocker_xact_age,
    left(blocked.query, 300) AS blocked_query,
    left(blocker.query, 300) AS blocker_query
FROM pg_stat_activity AS blocked
CROSS JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) AS p(blocker_pid)
JOIN pg_stat_activity AS blocker
  ON blocker.pid = p.blocker_pid
ORDER BY blocked.query_start;
~~~

Một transaction blocker có thể khiến nhiều request khác chờ. Thay vì chỉ nhìn các query đang chờ, hãy xác định transaction giữ lock ban đầu, người dùng ứng dụng và thời gian nó đã mở.

### 5.2. So sánh thời gian giữ connection với thời gian SQL

Nếu pool cung cấp usage duration và ứng dụng có thể đo thời gian thực thi SQL, hãy so sánh hai số liệu:

- SQL chạy 100 ms nhưng connection được giữ 10 giây: phần thời gian còn lại có thể nằm trong xử lý ứng dụng, chờ mạng dịch vụ khác hoặc transaction scope quá rộng.
- SQL chạy 10 giây và connection được giữ 10 giây: cần tối ưu truy vấn, index, lock hoặc tài nguyên database.
- SQL đã hoàn tất nhưng connection vẫn active trong pool: kiểm tra code chưa đóng connection hoặc transaction chưa kết thúc.

Không phải mọi pool đều cung cấp thời gian giữ connection theo cách giống nhau. Có thể instrument tại data access layer hoặc dùng leak detection để thu thập stack trace khi cần.

## 6. Thiết kế pool có giới hạn phù hợp

### 6.1. Tính ngân sách kết nối toàn hệ thống

Không nên đặt maximum pool size độc lập trên từng service. Hãy tính tổng kết nối tối đa có thể phát sinh:

~~~text
Tổng kết nối ứng dụng tối đa
  = tổng (số replica của service × pool tối đa mỗi replica)
    + worker và job nền
    + client trực tiếp khác
~~~

Sau đó so sánh với ngân sách dành cho client của PostgreSQL:

~~~text
Ngân sách pool ứng dụng
  = max_connections
    - slot dành riêng và dự phòng quản trị
    - kết nối của workload khác
    - headroom vận hành
~~~

Ví dụ, giả sử server có max_connections là 300. Nhóm vận hành dành 20 slot cho quản trị và tác vụ đặc biệt, 40 slot cho workload khác, và muốn giữ 30 slot dự phòng. Ngân sách còn lại cho ứng dụng là 210.

Nếu có 6 replica API giống nhau và không có pool khác, giới hạn trung bình mỗi replica phải nằm trong ngân sách 210/6, tức 35 connection. Nếu còn worker hoặc scheduler, phải trừ phần của chúng trước khi chia cho API.

Đây là phép tính giới hạn trên, không phải khuyến nghị luôn mở hết số connection đó. PostgreSQL có thể đạt thông lượng tốt hơn với số query active nhỏ hơn nhiều so với max_connections. Pool cần được điều chỉnh dựa trên khả năng CPU, I/O, loại truy vấn và mức đồng thời thực tế.

### 6.2. Pool lớn hơn không đồng nghĩa nhanh hơn

Mỗi backend PostgreSQL cần tài nguyên. Khi quá nhiều truy vấn cùng hoạt động, chúng cạnh tranh CPU, bộ nhớ, I/O, cache và lock. Số lượng query active tăng có thể làm thời gian từng query dài hơn, khiến kết nối bị giữ lâu hơn và tiếp tục làm pool đầy.

Do đó, tăng maximum pool size có thể tạo vòng phản hồi xấu:

~~~text
Pool lớn hơn
   |
   v
Nhiều query chạy đồng thời
   |
   v
Tranh chấp CPU / I/O / lock tăng
   |
   v
Query lâu hơn, connection giữ lâu hơn
   |
   v
Pool tiếp tục đầy
~~~

Hãy thử mức pool nhỏ hơn hoặc giới hạn concurrency ở tầng ứng dụng nếu database đã bão hòa. Mục tiêu là duy trì mức đồng thời mà PostgreSQL xử lý hiệu quả, không phải làm cho mọi request đều có thể mở một backend riêng.

### 6.3. Đặt timeout ở nhiều tầng

Một request có thể chờ ở nhiều nơi: hàng đợi ứng dụng, pool, kết nối mạng, lock và câu SQL. Nên có deadline tổng và ngân sách cho từng giai đoạn.

Các timeout thường dùng:

- **Pool acquisition timeout:** giới hạn thời gian chờ mượn connection.
- **Connect timeout:** giới hạn thời gian thiết lập kết nối mới.
- **Statement timeout:** giới hạn thời gian thực thi câu lệnh ở PostgreSQL.
- **Lock timeout:** giới hạn thời gian chờ lấy lock.
- **Idle in transaction timeout:** kết thúc session để transaction idle quá lâu.
- **Request deadline:** giới hạn thời gian toàn bộ request được phép xử lý.

Thứ tự timeout cần có chủ đích. Ví dụ, request deadline 5 giây thì không nên để pool acquisition timeout 30 giây. Nếu client đã bỏ request, server vẫn có thể tiếp tục truy vấn và chiếm connection nếu cancellation không được truyền xuống database.

PostgreSQL có thể cấu hình statement_timeout và lock_timeout ở cấp role hoặc database, hoặc đặt theo session/transaction khi ứng dụng quản lý được. Tránh đặt giá trị quá thấp cho mọi workload vì báo cáo hoặc batch hợp lệ có thể cần thời gian dài hơn.

### 6.4. Ví dụ cấu hình HikariCP

Với Java dùng HikariCP, một cấu hình minh họa:

~~~properties
spring.datasource.hikari.maximum-pool-size=20
spring.datasource.hikari.minimum-idle=4
spring.datasource.hikari.connection-timeout=3000
spring.datasource.hikari.validation-timeout=1000
spring.datasource.hikari.max-lifetime=1500000
spring.datasource.hikari.idle-timeout=300000
spring.datasource.hikari.pool-name=orders-api
~~~

Các giá trị chỉ là ví dụ, cần tính lại theo ngân sách kết nối và thời gian của workload. HikariCP quản lý vòng đời kết nối và cung cấp metric pool qua integration phù hợp. Cần tránh coi connection-timeout là thời gian chạy SQL: đây là thời gian chờ lấy connection từ pool.

max-lifetime nên thấp hơn giới hạn tuổi thọ kết nối do database proxy hoặc hạ tầng mạng áp đặt, nếu có. minimum-idle quyết định mức kết nối rảnh duy trì; nếu đặt cao trên nhiều replica, hệ thống có thể mở một lượng lớn kết nối ngay khi scale out.

Có thể bật leak detection trong giai đoạn điều tra để tìm nơi mượn connection quá lâu. Không nên đặt ngưỡng thấp tùy tiện hoặc dùng cảnh báo đó như bằng chứng chắc chắn có leak, vì truy vấn hợp lệ dài hơn ngưỡng cũng tạo cảnh báo.

## 7. Dùng PgBouncer khi cần quản lý nhiều client

PgBouncer là connection pooler đặt giữa ứng dụng và PostgreSQL. Ứng dụng kết nối đến PgBouncer; PgBouncer quản lý một tập server connection để phục vụ nhiều client connection.

~~~text
API replicas / workers
        |
        | client connections
        v
    PgBouncer
        |
        | server connections
        v
    PostgreSQL
~~~

PgBouncer có thể giảm số kết nối vật lý đến PostgreSQL khi có nhiều client ứng dụng. Nó đặc biệt hữu ích khi hệ thống có nhiều replica, nhiều worker hoặc client tạo kết nối ngắn hạn.

### 7.1. Các chế độ pooling

PgBouncer có ba chế độ phổ biến:

| Chế độ | Thời điểm trả server connection | Đặc điểm |
|---|---|---|
| session | Khi client ngắt kết nối | Giữ trạng thái session; mức chia sẻ thấp |
| transaction | Khi transaction kết thúc | Cho phép nhiều client chia sẻ ít server connection hơn |
| statement | Sau mỗi câu lệnh | Mỗi statement là transaction riêng; không phù hợp nhiều ứng dụng |

**Session pooling** giữ một server connection trong toàn bộ phiên client. Cách này tương thích hơn với tính năng phụ thuộc session nhưng giảm khả năng chia sẻ connection.

**Transaction pooling** chỉ giữ server connection trong một transaction. Khi transaction commit hoặc rollback, server connection có thể phục vụ client khác. Cách này tăng khả năng multiplex nhiều client, nhưng ứng dụng không được giả định lần transaction tiếp theo sẽ dùng đúng server session cũ.

Trong transaction pooling, cần chú ý trạng thái session như SET tùy ý, temporary table sống qua transaction, LISTEN, session advisory lock và các tính năng phụ thuộc connection. Một số khả năng liên quan prepared statement phụ thuộc phiên bản PgBouncer và cấu hình; hãy xác minh tương thích trước khi chuyển chế độ.

**Statement pooling** không cho phép transaction nhiều câu lệnh theo cách thông thường vì server connection có thể được trả lại sau mỗi statement. Chỉ dùng khi workload thực sự phù hợp.

### 7.2. Cấu hình PgBouncer minh họa

Một cấu hình khái quát:

~~~ini
[databases]
app = host=postgres port=5432 dbname=app

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 6432
pool_mode = transaction
max_client_conn = 1000
default_pool_size = 30
reserve_pool_size = 5
reserve_pool_timeout = 3
~~~

Các giá trị trên chỉ minh họa cú pháp và cách tách client limit khỏi server pool. Pool thực tế còn được chia theo database và user, nên tổng server connection có thể là tổng của nhiều pool. Cần tính toàn bộ tổ hợp database/user và các cấu hình override, không coi default_pool_size là giới hạn tổng duy nhất cho toàn bộ PgBouncer.

max_client_conn giới hạn client connection PgBouncer nhận; default_pool_size điều khiển số server connection trong mỗi pool theo cấu hình; reserve pool cho phép mở thêm một lượng giới hạn khi cần. Tăng max_client_conn không làm PostgreSQL có thêm năng lực xử lý, vì client vẫn phải chia sẻ server connection.

### 7.3. Quan sát PgBouncer

Các lệnh quản trị thường dùng:

~~~sql
SHOW POOLS;
SHOW STATS;
SHOW CLIENTS;
SHOW SERVERS;
SHOW CONFIG;
~~~

Trong SHOW POOLS, theo dõi client đang chờ server connection, server đang active và server idle. Nếu client wait tăng nhưng server pool đã đầy, PgBouncer đang xếp hàng vì không có server connection rảnh. Cần xem query latency, pool size và tải PostgreSQL trước khi tăng pool.

PgBouncer bổ sung một hàng đợi nữa. Nếu ứng dụng pool đã chờ PgBouncer, rồi PgBouncer lại chờ PostgreSQL, request có thể tích tụ ở hai tầng. Cần theo dõi acquisition time ở ứng dụng và wait time ở PgBouncer để biết hàng đợi nằm ở đâu.

## 8. Xử lý sự cố dây chuyền theo thứ tự

Khi pool đã đầy và lỗi lan rộng, ưu tiên khôi phục khả năng phục vụ và ngăn tải mới tiếp tục khuếch đại sự cố. Không nên tăng đồng thời pool size, max_connections và retry count vì sẽ làm mất khả năng xác định tác động của từng thay đổi.

### Bước 1: Xác định phạm vi ảnh hưởng

Kiểm tra service nào bị lỗi, lỗi bắt đầu khi nào, replica nào có pool đầy và PostgreSQL có đạt giới hạn kết nối hay không. Đối chiếu pool active, idle, pending và timeout; số backend theo database, user, application_name và state; query latency, lock wait, CPU, I/O và connection count; số replica, worker và job nền; tỷ lệ retry, request timeout và queue depth.

Nếu chỉ một service có pool đầy nhưng PostgreSQL còn nhiều slot, tập trung vào pool và code của service đó. Nếu nhiều service đồng thời không kết nối được, điều tra giới hạn hoặc tải ở PostgreSQL và các client dùng chung.

### Bước 2: Chặn retry storm và tải không thiết yếu

Giảm retry tự động, đặt backoff có jitter và ngừng retry vô hạn. Tạm dừng job nền, batch hoặc consumer có thể trì hoãn nếu chúng đang cạnh tranh kết nối với request quan trọng.

Nếu API có thể từ chối sớm khi pool không còn capacity, dùng load shedding có kiểm soát để trả lỗi quá tải nhanh thay vì giữ hàng nghìn request chờ. Hàng đợi ứng dụng cần có giới hạn; một queue không giới hạn chỉ chuyển nơi tích tụ bộ nhớ và độ trễ.

### Bước 3: Giảm concurrency ở nguồn gây tải

Giảm số worker hoặc replica đang tạo quá nhiều truy vấn. Nếu vừa scale out và tổng pool vượt ngân sách, có thể scale back hoặc hạ pool maximum của các instance mới. Không tăng pool size để cố giải phóng hàng đợi khi database đang bão hòa.

Giữ đủ năng lực cho tác vụ quan trọng và quản trị. Có thể tạm tắt một luồng không thiết yếu để database phục hồi, sau đó bật lại có kiểm soát.

### Bước 4: Tìm query hoặc transaction giữ connection

Dùng pg_stat_activity và pg_blocking_pids để tìm truy vấn dài, idle in transaction và blocker. Kiểm tra log ứng dụng để ghép PID hoặc application_name với request/job nếu hệ thống ghi nhận được.

Nếu một transaction bị bỏ quên hoặc đang giữ lock dây chuyền, xác định chủ sở hữu service để xem có thể hủy hay không. Không kết thúc backend chỉ dựa vào việc query chạy lâu; nó có thể là tác vụ hợp lệ hoặc đang thực hiện công việc quan trọng.

### Bước 5: Giải phóng connection có chọn lọc

Nếu đã xác định backend gây nghẽn và được phép hủy, có thể dùng pg_cancel_backend để yêu cầu hủy câu lệnh đang chạy:

~~~sql
SELECT pg_cancel_backend(12345);
~~~

Nếu cần kết thúc toàn bộ session, pg_terminate_backend sẽ ngắt kết nối:

~~~sql
SELECT pg_terminate_backend(12345);
~~~

Hãy thay PID bằng backend đã xác minh. Hủy session sẽ rollback transaction chưa commit và có thể làm request thất bại. Ưu tiên cancel query trước nếu chỉ cần dừng câu lệnh; terminate session chỉ khi cần giải phóng session hoặc cancel không đủ. Không dùng lệnh này hàng loạt theo trạng thái mà không xác định owner và tác động.

### Bước 6: Khôi phục lưu lượng từ từ

Khi query latency, connection wait và số backend ổn định, bật lại worker và tăng lưu lượng từng bước. Theo dõi pool pending, request latency, lỗi và tải PostgreSQL sau mỗi lần tăng.

Nếu toàn bộ client reconnect cùng lúc, có thể xuất hiện reconnect storm. Dùng backoff có jitter và tránh restart đồng loạt tất cả replica. Pool thường có thể tự phục hồi khi connection được trả về; restart ứng dụng chỉ nên dùng khi pool hoặc client state thực sự bị kẹt và đã cân nhắc tác động reconnect.

### Bước 7: Ghi lại nguyên nhân gốc và biện pháp ngăn tái diễn

Sau khi dịch vụ phục hồi, xác định chuỗi sự kiện: thay đổi tải, query chậm, lock, leak, replica tăng, pool config hay retry. Gắn mỗi nguyên nhân với một thay đổi có thể kiểm chứng như sửa ranh giới transaction, thêm index, giới hạn concurrency, giảm pool, đặt timeout hoặc thêm metric.

## 9. Timeout, retry và backpressure

Ba cơ chế này cần phối hợp để giữ cho hệ thống ổn định khi database chậm.

### 9.1. Timeout phải có ngân sách

Giả sử request có deadline 4 giây. Có thể phân bổ một phần cho pool acquisition, một phần cho SQL và phần còn lại cho xử lý ứng dụng. Nếu mỗi tầng tự đặt timeout dài hơn deadline của tầng trên, request có thể tiếp tục chiếm tài nguyên sau khi client đã bỏ cuộc.

Ví dụ minh họa:

| Giai đoạn | Ngân sách |
|---|---:|
| Chờ pool | 500 ms |
| Thực thi SQL và lock | 2.500 ms |
| Xử lý và trả kết quả | 1.000 ms |
| Tổng deadline | 4.000 ms |

Các con số cần dựa trên SLO và phân bố latency thực tế. Một tác vụ báo cáo dài nên có deadline riêng thay vì dùng cùng timeout với API tương tác.

### 9.2. Retry có giới hạn

Chỉ retry lỗi có khả năng tạm thời và thao tác có tính idempotent hoặc có cơ chế chống ghi trùng. Ví dụ, một request tạo đơn hàng không nên được gửi lại mù quáng nếu lần đầu có thể đã commit nhưng response bị mất.

Một chính sách retry thường có:

- Số lần thử tối đa nhỏ.
- Exponential backoff.
- Jitter để các client không retry cùng một thời điểm.
- Tổng retry budget nằm trong request deadline.
- Phân loại lỗi để không retry lỗi cấu hình, constraint hoặc SQL không hợp lệ.

Không retry lỗi pool acquisition timeout liên tục ngay trong cùng một request nếu pool đã bão hòa. Hành động đó chỉ tạo thêm cạnh tranh cho tài nguyên đang thiếu.

### 9.3. Backpressure và giới hạn hàng đợi

Backpressure làm chậm hoặc từ chối việc nhận thêm công việc khi downstream không còn khả năng xử lý. Với PostgreSQL, có thể áp dụng ở nhiều tầng:

- Giới hạn số request đồng thời được phép vào tầng repository.
- Giới hạn worker concurrency theo ngân sách database.
- Giới hạn queue length và thời gian chờ.
- Dùng semaphore hoặc bulkhead riêng cho workload nặng.
- Ưu tiên request quan trọng và tạm dừng batch không cấp thiết.

Bulkhead ngăn một loại workload chiếm hết connection của loại khác. Ví dụ, API giao dịch và báo cáo có thể dùng pool hoặc giới hạn concurrency riêng, nhưng tổng ngân sách của chúng vẫn phải nằm trong khả năng PostgreSQL.

## 10. Kiểm thử và diễn tập tình huống pool cạn

Sự cố pool nên được tái hiện trong môi trường thử nghiệm có giới hạn, không thử gây quá tải trên production. Một bài kiểm thử có thể dùng pool nhỏ và nhiều worker đồng thời:

~~~text
Pool maximum = 5
Worker count = 20
Mỗi worker:
  1. Mượn connection
  2. Chạy một câu SQL có thời gian chờ kiểm soát
  3. Trả connection
Quan sát:
  - active connections
  - pending workers
  - acquisition time
  - timeout count
~~~

Bài kiểm thử cần xác minh:

- Active connection không vượt maximum pool size.
- Worker chờ được cấp connection khi một worker khác trả kết nối.
- Khi acquisition timeout hết hạn, ứng dụng xử lý lỗi rõ ràng và không giữ thread vô hạn.
- Exception trong truy vấn vẫn trả connection về pool.
- Transaction lỗi được rollback.
- Hủy test không để lại session hoặc transaction không mong muốn.

Có thể tạo một test leak có chủ đích trong môi trường cô lập để xác minh leak detection hoạt động. Sau đó thêm test cho đường exception và callback bất đồng bộ để bảo đảm cleanup được thực hiện.

Với kiểm thử PostgreSQL max_connections, dùng instance riêng có giới hạn thấp và kết nối có kiểm soát. Không thay max_connections trên server dùng chung để mô phỏng sự cố. Cần nhớ thay đổi max_connections yêu cầu restart PostgreSQL, vì vậy đây không phải nút điều chỉnh tức thời trong lúc production đang gặp sự cố.

## 11. Checklist vận hành và phòng ngừa

Trước khi triển khai cấu hình pool mới, xác minh:

- Tổng pool maximum trên mọi replica, worker và service nằm trong ngân sách kết nối.
- Có headroom cho migration, monitoring, quản trị và workload khác.
- Pool acquisition timeout phù hợp với request deadline.
- Connection và transaction được đóng trong cả đường thành công lẫn exception.
- Transaction không bao trùm lời gọi HTTP hoặc thao tác chờ không cần thiết.
- Query latency, lock wait và connection usage được theo dõi.
- Retry có giới hạn, backoff và jitter.
- Queue và concurrency có giới hạn.
- application_name phân biệt được các service.
- Có quy trình kiểm tra và hủy blocker đã xác minh.
- Nếu dùng PgBouncer, pool mode tương thích với hành vi session của ứng dụng.
- Có dashboard và cảnh báo cho active/idle/pending connection, acquisition latency và timeout.

Các cảnh báo nên được đặt trước ngưỡng lỗi nghiêm trọng. Ví dụ, cảnh báo khi pending request tăng liên tục hoặc acquisition P95 tăng trong vài phút có thể giúp xử lý trước khi toàn bộ pool timeout. Không nên chỉ cảnh báo khi PostgreSQL đã đạt max_connections.

## 12. Nguyên tắc duy trì ổn định

Pool kết nối là cơ chế điều tiết truy cập PostgreSQL, không phải nguồn năng lực vô hạn. Cấu hình pool cần dựa trên tổng số replica, khả năng xử lý truy vấn và ngân sách kết nối toàn hệ thống. Khi pool đầy, cần xác định kết nối đang bận vì query, lock, transaction dài, leak hay tải tăng đột biến.

Một hệ thống chịu lỗi tốt giới hạn concurrency, đặt timeout theo deadline, retry có ngân sách, áp dụng backpressure và thu thập metric ở cả ứng dụng lẫn PostgreSQL. Khi có sự cố, giảm tải và ngăn retry storm trước, tìm blocker và giải phóng session có chọn lọc, sau đó khôi phục lưu lượng từ từ. Những biện pháp này giúp ngăn một pool bị cạn kéo theo toàn bộ ứng dụng và database.


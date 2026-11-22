# Cạn nhóm kết nối, hàng đợi tăng và hiệu ứng thử lại dồn dập

Một ứng dụng Java có thể ngừng phục vụ yêu cầu dù cơ sở dữ liệu vẫn đang chạy, chỉ vì không còn connection rảnh trong connection pool. Request mới phải chờ lấy connection; hàng đợi tăng làm thời gian phản hồi dài hơn; client timeout khiến ứng dụng thử lại; các lần thử lại tạo thêm tải và tiếp tục chiếm connection. Vòng lặp này có thể biến một sự cố chậm ban đầu thành retry storm, làm cả ứng dụng lẫn database suy giảm nhanh chóng.

Trong chương **Chẩn đoán sự cố** của module **DATABASE_PERFORMANCE**, bài học này giải thích cách nhận diện cạn nhóm kết nối, phân tích hàng đợi tăng và ngăn hiệu ứng thử lại dồn dập. Module **DATABASE_PERFORMANCE** rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung bao gồm thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng sau điều chỉnh. Vì vậy, xử lý pool exhaustion cần kết hợp số liệu ứng dụng, thời gian giữ connection, kế hoạch truy vấn, lock wait, giới hạn database và chính sách retry trên toàn hệ thống.

## 1. Connection pool giải quyết vấn đề gì?

Mở một kết nối vật lý đến database có chi phí: thiết lập TCP/TLS, xác thực, khởi tạo session, thiết lập tham số và cấp phát tài nguyên phía server. Nếu mỗi request tự mở rồi đóng kết nối, ứng dụng có thể tạo lượng lớn kết nối ngắn hạn, gây overhead và khó kiểm soát giới hạn connection của database.

Connection pool giữ một số connection đã được tạo sẵn. Khi cần truy cập database, request mượn một connection; sau khi hoàn tất transaction và đóng connection handle, connection vật lý được trả về pool để request khác dùng lại.

Một pool thường có:

- **Active connections:** connection đang được ứng dụng mượn.
- **Idle connections:** connection sẵn sàng cho request mới.
- **Maximum pool size:** giới hạn connection tối đa của pool.
- **Pending waiters:** request đang chờ connection.
- **Acquire timeout:** thời gian tối đa request được phép chờ lấy connection.
- **Connection hold time:** khoảng thời gian từ lúc mượn đến lúc trả connection.
- **Connection creation/validation:** hoạt động tạo mới hoặc kiểm tra connection.

Pool giới hạn số session database mà một instance ứng dụng tạo ra và giảm chi phí thiết lập kết nối. Pool không làm truy vấn nhanh hơn một cách tự động. Nếu query chậm hoặc transaction giữ connection lâu, pool sẽ bị chiếm lâu hơn và ít connection còn lại cho request khác.

## 2. Pool exhaustion là gì?

Pool exhaustion xảy ra khi mọi connection có thể cấp phát đều đang được mượn hoặc chưa sẵn sàng, trong khi request mới tiếp tục xin connection. Với pool có maximum size là 20, nếu cả 20 connection đang active, request thứ 21 phải chờ hoặc nhận timeout.

Một tình huống điển hình:

1. Lưu lượng tăng hoặc một truy vấn bắt đầu chậm.
2. Request giữ connection lâu hơn bình thường.
3. Số active connections tiến tới maximum pool size.
4. Request mới xếp hàng chờ connection.
5. Acquire latency tăng và request timeout.
6. Client hoặc tầng gọi thử lại.
7. Retry tạo thêm request và cạnh tranh cùng pool.
8. Queue dài hơn, timeout tăng và hệ thống có thể mất khả năng phục vụ.

Cạn pool là triệu chứng của mất cân bằng giữa tốc độ request cần database, thời gian giữ connection và số connection khả dụng. Nó không chứng minh rằng database đã đạt giới hạn CPU hay max_connections. Database có thể còn tài nguyên nhưng ứng dụng vẫn hết pool vì connection bị giữ trong code, chờ lock, chờ network hoặc chờ một dịch vụ bên ngoài.

## 3. Hàng đợi tăng và vòng lặp phản hồi dương

Hàng đợi connection có thể tăng khi tốc độ request đến nhanh hơn tốc độ connection được trả lại. Nếu request timeout rồi được retry, số lần gọi thực tế tới database có thể lớn hơn số hành động ban đầu của người dùng.

Ví dụ, một thao tác người dùng tạo một request. Gateway retry hai lần và service retry thêm hai lần. Nếu các lớp không phối hợp, một thao tác có thể tạo nhiều lần thực thi. Khi tải tăng, retry càng làm tải tăng thêm.

Vòng lặp phản hồi dương:

~~~text
Query/DB chậm
      |
      v
Connection được giữ lâu
      |
      v
Pool hết connection rảnh
      |
      v
Request xếp hàng và timeout
      |
      v
Client/service retry
      |
      v
Nhiều request hơn cùng tranh connection
      |
      +----------> Query/DB càng chậm
~~~

Điểm nguy hiểm là retry thường được thiết kế để giúp request vượt qua lỗi tạm thời. Khi hệ thống đang quá tải, retry không tạo thêm năng lực xử lý; nó chỉ tăng số công việc phải cạnh tranh.

## 4. Mối quan hệ giữa throughput, pool size và thời gian giữ connection

Có thể dùng định luật Little để hiểu quan hệ giữa số request đang ở trong hệ thống, throughput và thời gian xử lý:

~~~text
Số connection active trung bình
    ≈ throughput database × thời gian giữ connection trung bình
~~~

Nếu ứng dụng thực hiện 200 thao tác database mỗi giây và mỗi thao tác giữ connection trung bình 100 ms, số connection active trung bình xấp xỉ 20.

Nếu thời gian giữ connection tăng lên 500 ms trong khi throughput vẫn là 200 thao tác/giây, số connection active trung bình có thể tăng lên khoảng 100. Pool size không đổi sẽ bắt đầu tạo hàng đợi.

Đây là phép ước lượng theo trạng thái ổn định. Trong thực tế cần tính burst, phân bố thời gian giữ connection, transaction dài, request đồng thời và thời gian chờ lock. p95/p99 của hold time có thể quan trọng hơn giá trị trung bình.

Pool lớn hơn có thể hấp thụ một phần burst ngắn, nhưng nếu database đã bão hòa, thêm connection có thể làm tăng context switching, lock contention, memory usage và I/O queue. Cần tìm mức concurrency mà database xử lý hiệu quả, không đặt pool bằng một con số lớn tùy ý.

## 5. Phân biệt thời gian chờ lấy connection và thời gian chạy SQL

Một request dùng database thường có nhiều giai đoạn:

1. Chờ lấy connection từ pool.
2. Bind tham số và gửi statement.
3. Chờ database thực thi.
4. Nhận và đọc kết quả.
5. Commit hoặc rollback.
6. Đóng statement/result set và trả connection về pool.

Nếu chỉ đo tổng thời gian request, khó biết bottleneck ở đâu. Hãy tách:

- **Connection acquisition time:** thời gian từ lúc xin đến lúc nhận connection.
- **Connection usage/hold time:** thời gian connection nằm trong tay ứng dụng.
- **SQL execution time:** thời gian thực thi câu lệnh, theo cách đo của driver hoặc database.
- **Result consumption time:** thời gian đọc hết kết quả.
- **Transaction duration:** từ BEGIN đến COMMIT/ROLLBACK.
- **Queue time ở tầng ứng dụng:** thời gian chờ executor, semaphore hoặc request queue.

Acquire time cao nhưng SQL execution time bình thường thường cho thấy pool đang bận, connection bị giữ lâu hoặc số connection khả dụng quá thấp. SQL execution time cao cho thấy cần xem kế hoạch truy vấn, lock, I/O, CPU hoặc database. Hai tình huống có thể đồng thời xảy ra.

## 6. Những nguyên nhân thường làm connection bị giữ lâu

### 6.1. Truy vấn chậm

Query scan quá nhiều hàng, join sai thứ tự, sort/hash spill, thiếu index hoặc cardinality estimate sai có thể kéo dài thời gian sử dụng connection.

### 6.2. Lock contention

Transaction chờ lock vẫn có thể giữ connection. Một câu UPDATE chờ transaction khác commit có thể chiếm slot pool trong nhiều giây dù CPU database thấp.

### 6.3. Transaction quá dài

Ứng dụng mở transaction rồi thực hiện nhiều bước không cần thiết, gọi API ngoài, xử lý file hoặc chờ người dùng trước khi commit. Connection và có thể cả lock bị giữ trong suốt khoảng thời gian đó.

### 6.4. Đọc ResultSet chậm

Ứng dụng đọc một ResultSet rất lớn, chuyển đổi từng hàng hoặc gửi dữ liệu cho client chậm trong khi vẫn giữ connection. Thời gian fetch và xử lý kết quả có thể lớn hơn thời gian SQL thực thi.

### 6.5. Rò rỉ connection

Một nhánh code không đóng connection hoặc không trả connection về pool sau exception. Số active connections tăng dần và không giảm dù request đã kết thúc.

### 6.6. Chờ dịch vụ khác khi đang giữ connection

Ứng dụng mượn connection, đọc một hàng, gọi HTTP tới service khác rồi mới tiếp tục ghi database. Nếu service ngoài chậm, connection bị giữ dù database không làm việc.

### 6.7. Nested acquisition và deadlock ở tầng ứng dụng

Một luồng đang giữ connection có thể gọi một service khác cần mượn connection thứ hai. Nếu nhiều luồng cùng làm vậy trong khi pool đã cạn, các luồng có thể chờ nhau dù database không có lock deadlock.

## 7. Phát hiện rò rỉ connection và giữ connection quá lâu

Rò rỉ connection thường có dấu hiệu active connections tăng dần và không trở về mức nền sau khi tải giảm. Hãy xem:

- Active, idle và pending connection theo thời gian.
- Thời gian giữ connection p50/p95/p99.
- Số lần acquire timeout.
- Số connection được tạo mới và đóng.
- Thread stack của các luồng đang chờ hoặc đang giữ connection.
- Log transaction chưa kết thúc.
- Vị trí code mượn connection nhưng không đóng trong mọi nhánh.

Trong JDBC, dùng try-with-resources để đảm bảo connection handle, statement và result set được đóng:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
         "SELECT order_id, status FROM orders WHERE order_id = ?")) {

    statement.setLong(1, orderId);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            processOrder(resultSet);
        }
    }
}
~~~

Với connection lấy từ pool, close trên handle thường trả connection về pool thay vì đóng socket vật lý. Không được bỏ close vì nghĩ pool tự thu hồi ngay. Pool chỉ có thể tái sử dụng connection sau khi ứng dụng trả nó về.

Nếu processOrder thực hiện công việc chậm hoặc gọi dịch vụ khác, hãy cân nhắc đọc dữ liệu cần thiết vào cấu trúc phù hợp, đóng ResultSet/connection khi có thể rồi thực hiện phần xử lý ngoài database. Cần cân nhắc bộ nhớ và tính nhất quán khi tách các bước.

## 8. Transaction boundary và connection hold time

Transaction nên bao quanh phần công việc cần tính nguyên tử, nhất quán và cô lập. Mở transaction quá sớm hoặc commit quá muộn làm tăng connection hold time và có thể giữ lock.

Một mẫu không tốt:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    Order order = loadOrder(connection, orderId);
    ExternalResponse response = paymentClient.authorize(order);
    updateOrder(connection, order, response);

    connection.commit();
}
~~~

Trong ví dụ này, connection và transaction được giữ trong lúc gọi payment service. Nếu HTTP timeout 5 giây, connection có thể bị chiếm ít nhất 5 giây dù database không làm việc.

Có thể tách phần gọi dịch vụ ngoài khỏi transaction nếu nghiệp vụ cho phép, dùng state machine hoặc transactional outbox để phối hợp các bước. Không tách transaction một cách tùy tiện nếu điều đó phá vỡ invariant nghiệp vụ.

Nguyên tắc là không giữ connection trong lúc chờ công việc không cần database. Chuẩn bị dữ liệu trước, mở transaction sát thời điểm đọc/ghi cần thiết, commit sớm sau khi hoàn thành và luôn rollback khi có lỗi.

## 9. Đọc các chỉ số pool

Một dashboard pool nên có tối thiểu:

| Chỉ số | Ý nghĩa | Dấu hiệu cần điều tra |
|---|---|---|
| Active connections | Connection đang được mượn | Bám sát maximum trong thời gian dài |
| Idle connections | Connection sẵn sàng | Bằng 0 cùng lúc pending tăng |
| Pending threads/waiters | Request chờ connection | Tăng liên tục hoặc không giảm sau peak |
| Acquire latency | Thời gian chờ lấy connection | p95/p99 tăng |
| Acquire timeout count | Số lần hết thời gian chờ | Tăng theo đợt tải |
| Usage/hold duration | Thời gian giữ connection | Tăng trước khi pool cạn |
| Connection creation rate | Tốc độ tạo connection mới | Tăng bất thường hoặc lỗi tạo |
| Connection timeout/validation failures | Kết nối không sử dụng được | Có thể là network, database hoặc cấu hình |

Đừng chỉ nhìn phần trăm pool usage. Pool có active 90% nhưng không có pending và acquire latency thấp có thể đang hoạt động bình thường. Ngược lại, pool chỉ active 70% nhưng một phần connection bị treo, idle không cấp phát được hoặc acquisition timeout vẫn có thể gây lỗi.

Theo dõi các chỉ số theo instance, pod, service và database endpoint. Nếu mỗi instance có pool riêng, tổng connection từ toàn bộ instance mới là con số cần so với khả năng database.

## 10. Chẩn đoán ở database

Khi pool cạn, hãy kiểm tra phía database cùng thời điểm:

- Số session đang active và idle.
- Query nào chạy lâu nhất.
- Lock wait và blocking chain.
- CPU, I/O latency, buffer/cache hit và temp I/O.
- Số transaction đang mở và tuổi transaction.
- Connection limit và reserved connections.
- Replication hoặc maintenance workload.
- Error log, deadlock và statement timeout.

Nếu pool active tối đa nhưng database có ít session đang chạy query, connection có thể bị giữ ở ứng dụng, chờ network, chờ external service hoặc nằm trong transaction idle. Nếu database có nhiều query active và lock wait cao, cần giải quyết bottleneck database hoặc giảm concurrency.

Với PostgreSQL, pg_stat_activity giúp xem backend, state, xact_start và wait_event. Với SQL Server, xem session/request, wait stats và blocking. Với MySQL, xem process list, Performance Schema và InnoDB lock waits. Với Oracle, xem session, wait events và SQL Monitor khi có. Tên view và quyền truy cập khác nhau theo hệ quản trị.

Không kết luận database khỏe chỉ vì CPU thấp. Lock wait, storage latency, connection limit, log flush hoặc network có thể là nút thắt dù CPU không cao.

## 11. Tính pool size trên toàn bộ hệ thống

Giả sử database cho phép tối đa 300 connection ứng dụng sau khi trừ connection dành cho quản trị, replication, monitoring và các service khác. Nếu có 6 instance ứng dụng, mỗi instance đặt maximumPoolSize là 60, tổng tiềm năng đã là 360, vượt ngân sách.

Cần tính:

~~~text
Tổng connection tối đa =
    số instance × pool tối đa mỗi instance
  + connection từ worker/job khác
  + connection từ công cụ và dịch vụ khác
~~~

Pool sizing phải xét autoscaling. Nếu số pod tăng gấp đôi nhưng mỗi pod giữ pool size cố định, tổng connection cũng tăng gấp đôi. Khi deployment rolling, pod cũ và pod mới có thể cùng tồn tại tạm thời, làm peak connection vượt dự kiến.

Đặt một ngân sách kết nối toàn hệ thống và phân bổ cho từng service. Dành một phần connection cho hoạt động quản trị và phục hồi. Đừng dùng toàn bộ max_connections của database cho ứng dụng bình thường.

## 12. Vì sao tăng maximumPoolSize có thể làm sự cố nặng hơn?

Tăng pool size có thể giảm acquire wait nếu database còn khả năng xử lý thêm concurrency. Nhưng nếu database đã bão hòa, thêm connection sẽ làm nhiều truy vấn cùng chạy và cạnh tranh CPU, I/O, lock, memory grant và buffer cache.

Hệ quả có thể là:

- Query latency tăng.
- Lock contention và deadlock tăng.
- Memory usage của database tăng.
- I/O queue dài hơn.
- Số transaction đồng thời tăng.
- Thời gian giữ connection dài hơn.
- Pending queue vẫn tăng dù pool lớn hơn.

Pool size nên dựa trên concurrency tối ưu của database và số lượng instance, không dựa trên số thread của web server. Một pool nhỏ có thể tạo backpressure lành mạnh, trong khi pool quá lớn chuyển hàng đợi từ ứng dụng vào database và làm toàn hệ thống khó kiểm soát.

## 13. Hàng đợi phải có giới hạn

Nếu request có thể chờ vô hạn để lấy connection, hàng đợi sẽ tích tụ và giữ thread, bộ nhớ, request context. Khi database hồi phục, một lượng lớn request cũ có thể cùng chạy, tạo thêm tải.

Hãy xác định:

- Acquire timeout phù hợp với request deadline.
- Giới hạn số request đang chờ hoặc số request đang chạy database.
- Queue capacity và hành vi khi queue đầy.
- Cancellation khi client đã hủy request.
- Deadline truyền xuyên suốt các service.
- Load shedding khi hệ thống quá tải.

Timeout lấy connection cần nhỏ hơn hoặc bằng phần ngân sách còn lại của request. Nếu request chỉ còn 100 ms nhưng pool acquire timeout là 30 giây, thread sẽ bị giữ lâu sau khi kết quả không còn hữu ích.

Hàng đợi hữu hạn giúp hệ thống từ chối sớm một phần tải khi không thể xử lý, giữ tài nguyên cho request có khả năng hoàn thành. Từ chối có kiểm soát thường tốt hơn để toàn bộ service treo và timeout dây chuyền.

## 14. Retry storm hình thành như thế nào?

Retry storm xảy ra khi nhiều request thất bại hoặc timeout gần cùng lúc rồi thử lại với tần suất cao. Nếu mọi client dùng cùng delay cố định, các retry có thể đồng bộ thành từng đợt (thundering herd).

Ví dụ, 1.000 request timeout sau 2 giây và tất cả retry ngay lập tức. Database đang phục hồi phải nhận thêm 1.000 request mới đúng lúc queue đã đầy. Nếu retry thêm nhiều lần, số lần thực thi có thể tăng theo cấp số nhân qua các tầng gọi.

Một số nguyên nhân:

- Retry không có backoff.
- Nhiều lớp cùng retry một request.
- Retry cả lỗi không thể khắc phục.
- Timeout ở client ngắn hơn thời gian xử lý thật, khiến request gốc vẫn chạy ở server.
- Retry không có giới hạn tổng thời gian.
- Request không idempotent được gửi lại.
- Queue không giới hạn và retry tiếp tục được nhận vào.
- Không có circuit breaker hoặc load shedding.

Retry phải là một phần của thiết kế kiểm soát tải, không phải một vòng lặp tự động quanh mọi exception.

## 15. Phân loại lỗi trước khi retry

Không phải mọi lỗi đều có thể phục hồi bằng cách thử lại.

Có thể cân nhắc retry với một số lỗi tạm thời:

- Connection reset hoặc lỗi mạng ngắn hạn.
- Database failover đã hoàn tất và endpoint mới sẵn sàng.
- Deadlock victim nếu transaction có thể chạy lại an toàn.
- Serialization failure trong isolation level yêu cầu retry transaction.
- Một số lỗi throttling hoặc resource transient được database xác định.

Không nên retry tự động với:

- Syntax error hoặc schema mismatch.
- Vi phạm constraint do dữ liệu nghiệp vụ không hợp lệ.
- Authentication/authorization failure.
- Lỗi chuyển đổi kiểu dữ liệu.
- Query plan hoặc logic sai.
- Request đã hết deadline.
- Lỗi không rõ transaction đã commit hay chưa mà thao tác không idempotent.

Trong Java, SQLState, vendor error code và exception subtype có thể giúp phân loại, nhưng quy tắc phải dựa trên driver/database cụ thể. Không coi mọi SQLException là transient.

## 16. Exponential backoff và jitter

Exponential backoff tăng thời gian chờ giữa các lần retry:

~~~text
delay(n) = min(max_delay, base_delay × 2^n)
~~~

Nếu không có jitter, nhiều client cùng gặp lỗi sẽ retry theo các mốc giống nhau. Jitter thêm độ ngẫu nhiên để phân tán retry:

~~~text
actual_delay = random(0, delay(n))
~~~

Ví dụ minh họa:

| Lần retry | Backoff tối đa | Khoảng chờ với full jitter |
|---|---:|---:|
| 1 | 100 ms | 0–100 ms |
| 2 | 200 ms | 0–200 ms |
| 3 | 400 ms | 0–400 ms |
| 4 | 800 ms | 0–800 ms |
| 5 | 1.600 ms | 0–1.600 ms |

Giới hạn max delay và số lần retry. Tổng thời gian retry phải nằm trong request deadline. Nếu request không còn đủ thời gian để hoàn tất, hãy dừng retry thay vì tạo công việc vô ích.

Jitter không thay thế retry budget hoặc circuit breaker. Nó chỉ làm các lần thử lại bớt đồng bộ.

## 17. Retry budget và tránh retry nhiều tầng

Một request có thể đi qua API gateway, service A, service B và database client. Nếu mỗi tầng tự retry ba lần, một lỗi ở database có thể tạo nhiều lần thực thi hơn nhiều so với dự kiến.

Hãy quy định retry budget ở cấp request hoặc operation:

- Tổng số lần thử tối đa.
- Tổng thời gian được phép retry.
- Tầng nào sở hữu retry.
- Loại lỗi nào được retry.
- Request nào không được retry.
- Tỷ lệ retry tối đa so với request gốc.

Ưu tiên một tầng có đủ ngữ cảnh để quyết định retry. Các tầng khác nên truyền lỗi lên thay vì tự nhân số lần thử. Nếu dùng nhiều tầng, cần tính tổng số lần gọi tối đa theo đường đi thực tế.

Retry budget có thể được theo dõi như tỷ lệ retry trên request gốc trong một cửa sổ thời gian. Khi tỷ lệ vượt ngưỡng, hệ thống có thể giảm retry hoặc chuyển sang fail-fast.

## 18. Deadline và timeout phải nhất quán

Các timeout khác nhau cần phối hợp:

- Request deadline ở gateway hoặc API.
- Timeout chờ connection pool.
- Statement/query timeout.
- Lock timeout.
- Socket/network timeout.
- Timeout của dịch vụ ngoài.
- Tổng thời gian dành cho retry và backoff.

Ví dụ request có deadline 2 giây. Nếu gateway đã dùng 300 ms, ứng dụng còn 1.700 ms. Không nên đặt pool acquisition timeout 2 giây và statement timeout 5 giây rồi hy vọng request hoàn tất đúng hạn.

Truyền deadline còn lại qua các tầng. Trước mỗi retry, kiểm tra ngân sách thời gian còn đủ cho backoff và một lần thực thi hợp lý hay không. Khi client hủy request, ứng dụng nên cố gắng hủy statement nếu an toàn và không tiếp tục retry request đã bị bỏ.

Timeout không nhất thiết dừng công việc ở server ngay lập tức. Client có thể ngừng chờ trong khi database vẫn tiếp tục query. Hãy kiểm tra cơ chế cancel của driver và database, đồng thời đo số query còn chạy sau khi client timeout.

## 19. Circuit breaker, bulkhead và load shedding

### 19.1. Circuit breaker

Circuit breaker theo dõi tỷ lệ lỗi hoặc độ trễ và tạm ngừng gửi request tới dependency khi nó có dấu hiệu không khỏe.

Các trạng thái thường gặp:

- **Closed:** cho phép request đi qua và theo dõi lỗi.
- **Open:** từ chối nhanh request trong một khoảng thời gian.
- **Half-open:** cho phép một số request thử để kiểm tra dependency đã phục hồi chưa.

Circuit breaker tránh tiếp tục dồn request vào database đang quá tải. Cần cấu hình ngưỡng, cửa sổ thống kê, thời gian mở và số request thử phù hợp. Không đặt ngưỡng quá nhạy khiến breaker mở/đóng liên tục.

### 19.2. Bulkhead

Bulkhead giới hạn tài nguyên cho từng nhóm workload. Ví dụ, báo cáo phân tích dùng executor và pool riêng có giới hạn; request thanh toán có ngân sách connection riêng. Khi một nhóm bị chậm, nó không chiếm hết tài nguyên của nhóm khác.

Bulkhead có thể được triển khai bằng pool riêng, semaphore, executor riêng hoặc giới hạn concurrency theo endpoint. Tránh tạo nhiều pool lớn trên cùng database mà không tính tổng connection.

### 19.3. Load shedding

Load shedding từ chối hoặc trì hoãn một phần request khi năng lực xử lý đã đạt giới hạn. Có thể ưu tiên request quan trọng, từ chối truy vấn báo cáo không cấp thiết hoặc trả trạng thái retry-after khi hệ thống có thể phục hồi.

Load shedding cần rõ ràng với client. Nếu client nhận 503 rồi lập tức retry không backoff, chính sách từ chối có thể làm retry storm nặng hơn. Kết hợp response code, Retry-After, jitter và retry budget.

## 20. Cấu hình pool trong Java và HikariCP

HikariCP là một connection pool phổ biến trong ứng dụng Java. Một số cấu hình thường được xem xét:

- maximumPoolSize: số connection tối đa của pool.
- minimumIdle: số connection idle tối thiểu mà pool cố duy trì.
- connectionTimeout: thời gian tối đa chờ lấy connection.
- idleTimeout: thời gian connection idle vượt mức có thể bị loại bỏ trong điều kiện phù hợp.
- maxLifetime: vòng đời tối đa của connection trước khi pool thay thế.
- validationTimeout: thời gian kiểm tra connection.
- leakDetectionThreshold: ngưỡng ghi cảnh báo connection được giữ quá lâu nếu bật.

Ví dụ cấu hình minh họa:

~~~properties
spring.datasource.hikari.maximum-pool-size=20
spring.datasource.hikari.minimum-idle=5
spring.datasource.hikari.connection-timeout=1000
spring.datasource.hikari.validation-timeout=500
spring.datasource.hikari.max-lifetime=1700000
~~~

Các giá trị trên chỉ minh họa cách khai báo. Chúng không phải cấu hình khuyến nghị cho mọi ứng dụng. Cần tính tổng pool trên tất cả instance, giới hạn database, thời gian giữ connection, timeout request và khả năng xử lý concurrency.

maxLifetime thường nên thấp hơn giới hạn lifetime hoặc timeout do database, proxy hay load balancer áp dụng, để pool chủ động thay connection trước khi phía ngoài đóng nó. Không đặt quá thấp khiến pool liên tục tạo connection mới. leakDetectionThreshold có thể giúp phát hiện connection giữ quá lâu trong môi trường chẩn đoán; cảnh báo không tự chứng minh có leak và cần được đối chiếu với stack trace cùng đường đi code.

## 21. Đo lường trong ứng dụng Java

Ghi metric ở cấp pool và request:

- Active, idle, total và pending connections.
- Acquisition latency p50/p95/p99.
- Connection usage duration p50/p95/p99.
- Timeout count và connection creation failure.
- Số query đang chạy và query duration.
- Transaction duration và rollback count.
- Retry count theo loại lỗi và tầng gọi.
- Circuit breaker state và rejected request.
- Executor queue depth, active thread và rejected task.
- Connection pool wait theo service/pod.

Nếu dùng Micrometer hoặc hệ thống metrics tương đương, giữ tag có cardinality hợp lý. Không gắn user ID hoặc request ID làm label metric vì có thể tạo số lượng time series quá lớn. Dùng trace/log để truy vết từng request; dùng metric để xem xu hướng và phân vị.

Correlation ID giúp nối log của gateway, service, JDBC và database. Khi có trace, ghi rõ span chờ connection, span SQL, commit và thời gian xử lý ngoài database. Điều này cho biết request bị chậm ở pool hay ở query.

## 22. Quy trình chẩn đoán khi pool cạn

Khi cảnh báo pool exhaustion xuất hiện, thực hiện theo thứ tự:

1. **Xác định phạm vi:** một instance, một service, một database hay toàn hệ thống.
2. **Xem pool metrics:** active, idle, pending, acquire latency và timeout.
3. **Xem hold time:** connection được giữ bao lâu, có tăng trước khi queue tăng không.
4. **Kiểm tra request/trace:** chờ pool, chạy SQL, đọc kết quả, commit hay gọi dịch vụ ngoài.
5. **Kiểm tra leak:** thread stack, log leak detection và các nhánh exception không close.
6. **Kiểm tra transaction:** transaction dài, idle in transaction, lock wait và rollback.
7. **Kiểm tra database:** session, query, CPU, I/O, lock, temp, connection limit và log.
8. **Kiểm tra autoscaling:** tổng maximum pool trên số instance hiện tại và số instance khi rollout.
9. **Kiểm tra retry:** số lần gọi so với request gốc, backoff, jitter và timeout từng tầng.
10. **Giảm áp lực:** giới hạn concurrency, tạm dừng job nặng hoặc load shed request ít ưu tiên.
11. **Sửa nguyên nhân:** tối ưu query, rút ngắn transaction, sửa leak hoặc điều chỉnh pool theo ngân sách.
12. **Đo sau thay đổi:** queue, acquire latency, hold time, query latency, retry rate và throughput.
13. **Kiểm tra phục hồi:** bảo đảm queue giảm, retry trở về nền và database không bị tải dồn sau khi mở lại.

Không chỉ tăng pool size hoặc restart ứng dụng rồi kết luận sự cố đã hết. Restart có thể giải phóng connection bị leak tạm thời nhưng nguyên nhân trong code vẫn còn. Sau restart, retry và reconnect đồng loạt còn có thể tạo một đợt tải mới.

## 23. Ứng phó sự cố đang diễn ra

Trong sự cố thực tế, mục tiêu đầu tiên là ngăn tải tiếp tục tăng và bảo vệ phần chức năng quan trọng.

Có thể thực hiện theo mức độ:

- Tạm dừng hoặc giới hạn batch job, báo cáo nặng và backfill.
- Giảm concurrency ở endpoint gây tải cao.
- Bật load shedding hoặc circuit breaker cho request ít ưu tiên.
- Giảm retry ở các client và bảo đảm backoff có jitter.
- Dừng nhận request mới khi deadline đã hết.
- Xác định session/query/transaction giữ connection lâu.
- Chỉ hủy query hoặc session khi hiểu tác động và khả năng rollback.
- Khi database phục hồi, mở tải dần thay vì cho toàn bộ queue chạy cùng lúc.

Không xóa queue hoặc terminate session hàng loạt mà không biết request và transaction đang làm gì. Một transaction có thể đã ghi dữ liệu một phần trong transaction chưa commit; rollback cần được xử lý theo database. Với request không rõ kết quả commit, cần đối soát hoặc dùng idempotency trước khi gửi lại.

## 24. Ví dụ: một truy vấn chậm gây retry storm

Giả sử một API lấy trạng thái đơn hàng dùng pool tối đa 30 connection. Bình thường query mất 20 ms. Sau một thay đổi dữ liệu, một truy vấn thiếu index mất 2 giây và giữ connection lâu hơn.

Ban đầu:

- 100 request/giây.
- Hold time trung bình 20 ms.
- Nhu cầu trung bình khoảng 2 connection active.

Sau thay đổi:

- Một phần query mất 2 giây.
- Nhiều request cùng chờ connection.
- Active connections đạt 30.
- Pending waiters tăng và acquire timeout xuất hiện.
- Gateway retry request timeout sau 1 giây.
- Query gốc có thể vẫn chạy ở database; retry tạo query thứ hai.
- Tổng số query tăng, khiến database càng chậm.

Cách điều tra và xử lý:

**Bước 1: Xem trace.** Thời gian chờ pool tăng trước, sau đó query span cũng dài. Điều này cho thấy pool exhaustion là hậu quả của query chậm và concurrency.

**Bước 2: Xem execution plan.** Xác định query đọc quá nhiều hàng do thiếu index hoặc estimate sai. Sửa truy vấn/index và kiểm tra actual rows, buffers cùng latency.

**Bước 3: Dừng retry khuếch đại.** Giảm số lần retry, thêm exponential backoff và jitter, truyền deadline và tránh retry request đã hết hạn.

**Bước 4: Giới hạn tải.** Tạm giới hạn concurrency của endpoint hoặc load shed request ít ưu tiên để query quan trọng có thể hoàn tất.

**Bước 5: Kiểm tra transaction/connection lifecycle.** Bảo đảm ResultSet, Statement và Connection được đóng; không giữ connection khi gọi service ngoài.

**Bước 6: Tính lại pool size.** So sánh hold time, throughput và khả năng database. Chỉ tăng pool nếu database còn khả năng xử lý thêm và tổng connection trên mọi instance vẫn trong ngân sách.

**Bước 7: Kiểm chứng phục hồi.** Đo pending waiters, acquisition latency, query p95/p99, retry ratio, DB CPU/I/O và throughput. Xác nhận hệ thống ổn định dưới tải đại diện.

Ví dụ cho thấy pool exhaustion không nhất thiết bắt đầu từ cấu hình pool. Một thay đổi ở SQL có thể kéo dài hold time, sau đó timeout và retry tạo thành vòng lặp làm suy giảm toàn hệ thống.

## 25. Những sai lầm thường gặp

- **Tăng maximumPoolSize ngay khi pool cạn.** Có thể đẩy database vượt concurrency tối ưu.
- **Đặt pool size bằng số thread web.** Thread không đồng nghĩa với số query database có thể chạy hiệu quả.
- **Chỉ xem active connections.** Cần xem pending, acquire latency và hold duration.
- **Cho request chờ vô hạn.** Thread và bộ nhớ bị giữ, queue tiếp tục tăng.
- **Retry mọi SQLException.** Lỗi dữ liệu, constraint hoặc cú pháp không tự hết khi thử lại.
- **Retry ở nhiều tầng.** Số lần thực thi bị nhân lên.
- **Dùng delay cố định không jitter.** Retry đồng bộ tạo thundering herd.
- **Retry thao tác không idempotent.** Có thể ghi trùng hoặc thực hiện nghiệp vụ hai lần.
- **Giữ connection trong lúc gọi HTTP.** Connection bị chiếm khi database không làm việc.
- **Bỏ qua transaction dài hoặc idle.** Connection và lock có thể bị giữ lâu.
- **Restart pool mà không sửa leak/query.** Sự cố có thể tái diễn ngay khi tải quay lại.
- **Mở queue không giới hạn.** Request cũ tích tụ và tiếp tục chạy khi hệ thống hồi phục.
- **Đánh giá pool từng instance riêng lẻ.** Tổng connection từ autoscaling và rollout có thể vượt ngân sách.
- **Chỉ đo throughput.** p95/p99 và tác động lên workload khác có thể xấu đi.

## 26. Checklist phòng ngừa pool exhaustion và retry storm

- [ ] Đã đặt ngân sách connection ở cấp toàn hệ thống.
- [ ] Đã tính tổng pool theo số instance và tình huống autoscaling/rolling deploy.
- [ ] Đã dành connection cho quản trị, monitoring và replication.
- [ ] Đã đo active, idle, pending, acquire latency và hold duration.
- [ ] Đã tách thời gian chờ pool khỏi thời gian SQL và transaction.
- [ ] Đã dùng try-with-resources cho JDBC resource.
- [ ] Đã giữ transaction ngắn và không gọi dịch vụ ngoài khi đang giữ connection.
- [ ] Đã kiểm tra query plan, lock wait, I/O và transaction dài.
- [ ] Đã đặt acquire timeout theo request deadline.
- [ ] Đã giới hạn queue và concurrency.
- [ ] Đã phân loại lỗi trước retry.
- [ ] Đã dùng exponential backoff, jitter, retry limit và retry budget.
- [ ] Đã tránh retry trùng ở nhiều tầng.
- [ ] Đã dùng idempotency cho thao tác có thể được gửi lại.
- [ ] Đã có circuit breaker, bulkhead hoặc load shedding phù hợp.
- [ ] Đã theo dõi retry rate, timeout, breaker state và rejected requests.
- [ ] Đã kiểm thử tình huống database chậm, failover và network interruption.
- [ ] Đã đo lại p95/p99, throughput và ảnh hưởng lên workload khác sau thay đổi.

## 27. Nguyên tắc cần ghi nhớ

Pool exhaustion xảy ra khi connection được giữ lâu hoặc nhu cầu đồng thời vượt khả năng cấp phát của pool. Hàng đợi tăng làm acquisition latency và timeout tăng; retry không kiểm soát có thể khuếch đại tải, tạo retry storm và khiến database càng khó phục hồi.

Hãy chẩn đoán bằng cách tách thời gian chờ pool, thời gian giữ connection, thời gian SQL và transaction; kiểm tra leak, lock, query plan, network và tổng connection trên mọi instance. Giữ transaction ngắn, đóng JDBC resource đúng cách, giới hạn queue/concurrency và đặt timeout theo deadline. Retry chỉ lỗi tạm thời, có giới hạn, exponential backoff, jitter, retry budget và idempotency. Dùng circuit breaker, bulkhead và load shedding để bảo vệ phần dịch vụ quan trọng. Sau mỗi thay đổi, đo lại acquisition latency, hold time, query p95/p99, retry rate, throughput và tải database dưới concurrency thực tế.

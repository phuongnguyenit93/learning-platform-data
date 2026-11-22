# Nhóm kết nối (connection pool), số kết nối hoạt động và hàng đợi

Ứng dụng thường xử lý nhiều request đồng thời, trong khi mỗi kết nối database tiêu tốn bộ nhớ, socket, trạng thái session và tài nguyên quản lý ở cả client lẫn server. Tạo một kết nối mới cho từng câu SQL có thể làm tăng chi phí bắt tay mạng, xác thực và khởi tạo session. Ngược lại, mở quá nhiều kết nối cùng lúc có thể làm database chịu áp lực bộ nhớ, lập lịch, chuyển ngữ cảnh, khóa và I/O. Connection pool giải quyết phần lớn chi phí vòng đời kết nối bằng cách tái sử dụng một tập kết nối có giới hạn.

Tối ưu connection pool không chỉ là tăng maximumPoolSize. Cần hiểu số kết nối đang được ứng dụng mượn, số kết nối nhàn rỗi, số request đang chờ, thời gian giữ connection, giới hạn toàn bộ các instance ứng dụng và năng lực thực tế của database. Pool quá nhỏ tạo hàng đợi ở ứng dụng; pool quá lớn có thể đẩy hàng đợi xuống database và làm mọi truy vấn chậm hơn. Mục tiêu là giữ mức đồng thời phù hợp với năng lực xử lý của database, đồng thời giới hạn hàng đợi và thời gian chờ để hệ thống suy giảm có kiểm soát.

Trong DATABASE_PERFORMANCE, connection pool là một phần của đường đi truy vấn cùng với SQL, execution plan, index, transaction và tài nguyên mạng. Vì vậy, phải đo cả pool wait lẫn thời gian SQL thực thi; nếu chỉ nhìn số connection active thì chưa thể kết luận database đang quá tải hay ứng dụng đang giữ connection không hợp lý.

## 1. Connection pool là gì?

Connection pool là bộ quản lý một tập kết nối database đã được tạo sẵn hoặc tạo theo nhu cầu. Khi một request cần truy cập database, ứng dụng mượn một connection từ pool, sử dụng nó trong một khoảng thời gian, sau đó trả connection về pool để request khác dùng lại.

Vòng đời cơ bản:

1. Ứng dụng yêu cầu một connection.
2. Pool cấp một connection nhàn rỗi nếu có.
3. Nếu chưa có connection và pool chưa đạt giới hạn, pool có thể tạo connection mới.
4. Nếu pool đã đạt giới hạn, request phải chờ trong hàng đợi.
5. Khi request hoàn tất, connection được trả về pool.
6. Pool kiểm tra, giữ lại, tái sử dụng hoặc đóng connection theo cấu hình.

Pool quản lý kết nối vật lý hoặc kết nối logic tùy thư viện và kiến trúc. Với JDBC pool phổ biến, một object Connection mà ứng dụng nhận thường là proxy/wrapper. Khi gọi close(), wrapper trả kết nối thật về pool thay vì đóng socket database ngay lập tức.

### 1.1. Vì sao không tạo kết nối cho từng câu SQL?

Một lần tạo kết nối mới có thể bao gồm:

- Mở TCP socket và thực hiện handshake.
- TLS handshake nếu kết nối được mã hóa.
- Xác thực người dùng.
- Thiết lập session, transaction defaults, timezone, role hoặc schema.
- Cấp phát trạng thái và tài nguyên ở database server.
- Thiết lập trạng thái driver và protocol ở ứng dụng.

Khi request chỉ chạy một truy vấn ngắn, chi phí tạo kết nối có thể lớn hơn thời gian thực thi SQL. Tái sử dụng connection giảm chi phí này và giúp kiểm soát số session database.

Tuy nhiên, pool không làm truy vấn SQL tự nhanh hơn. Một câu truy vấn thiếu index vẫn có thể quét hàng triệu dòng khi chạy trên connection được tái sử dụng. Pool chủ yếu quản lý khả năng tiếp cận database và mức đồng thời từ ứng dụng.

### 1.2. Pool không phải cache kết quả truy vấn

Connection pool giữ kết nối và trạng thái session. Nó không mặc nhiên lưu kết quả SELECT để trả lại cho request sau. Data cache, plan cache và application cache là các cơ chế khác.

Một connection được tái sử dụng có thể còn session state nếu ứng dụng hoặc driver không reset đúng cách. Điều này khác với cache dữ liệu và có thể gây lỗi nếu request sau kế thừa schema, role, isolation level, timezone hoặc biến session của request trước.

## 2. Các trạng thái và chỉ số của pool

Để đọc đúng tình trạng pool, cần phân biệt các khái niệm:

| Chỉ số | Ý nghĩa |
|---|---|
| Maximum pool size | Số connection tối đa pool được phép quản lý |
| Active / in-use | Connection đang được ứng dụng mượn |
| Idle / available | Connection sẵn sàng cấp cho request |
| Pending / waiting | Request đang chờ connection |
| Total | Tổng connection pool hiện có, thường bằng active cộng idle |
| Acquire time | Thời gian từ lúc request xin connection đến lúc nhận được |
| Usage / hold time | Thời gian ứng dụng giữ connection trước khi trả lại |
| Creation time | Thời gian tạo kết nối mới |
| Timeout count | Số lần không lấy được connection trong thời hạn |

Tên metric có thể khác nhau giữa HikariCP, DBCP, c3p0, framework và proxy. Hãy hiểu ý nghĩa thay vì chỉ dựa vào tên.

### 2.1. Active connection

Active connection là kết nối đang được ứng dụng mượn. Nó có thể đang thực thi SQL, đang chờ database trả kết quả hoặc đang bị giữ trong code dù không chạy câu lệnh nào.

Vì vậy, active cao không đồng nghĩa database đang chạy nhiều truy vấn. Một ứng dụng có thể giữ connection trong khi:

- Chờ gọi HTTP service khác.
- Xử lý dữ liệu hoặc serialize JSON.
- Chờ người dùng hoặc message broker.
- Thực hiện công việc CPU không cần database.
- Quên đóng ResultSet, Statement hoặc Connection.
- Mở transaction rồi không commit/rollback.

Nếu active gần maximum trong thời gian dài, cần đo usage time và xác định connection đang được giữ ở đâu.

### 2.2. Idle connection

Idle connection là connection đang nằm trong pool và chưa được request mượn. Idle không nhất thiết là lãng phí: nó giúp request tiếp theo nhận kết nối ngay mà không phải tạo mới.

Giữ quá nhiều idle connection có thể tiêu tốn session và bộ nhớ phía database. Giữ quá ít có thể làm tăng chi phí tạo kết nối khi traffic tăng đột ngột. Cần cân bằng theo mẫu traffic, thời gian tạo kết nối và giới hạn database.

### 2.3. Pending request và hàng đợi

Pending là số request đang chờ pool cấp connection. Hàng đợi xuất hiện khi nhu cầu mượn connection tạm thời vượt số connection có thể cấp.

Một lượng pending ngắn trong burst có thể bình thường. Pending tăng liên tục, acquire latency tăng và timeout xuất hiện cho thấy pool hoặc database không đáp ứng kịp tốc độ yêu cầu.

Hàng đợi không tạo thêm năng lực xử lý. Nó chỉ giữ request lại để chờ. Nếu hàng đợi không giới hạn, khi database quá tải, số request chờ có thể tăng đến mức làm cạn thread, bộ nhớ và deadline của toàn ứng dụng.

## 3. Pool size ảnh hưởng đến database như thế nào?

Mỗi connection thường tương ứng với một session hoặc một đơn vị thực thi có trạng thái ở database. Tùy engine, session có thể tiêu thụ bộ nhớ nền, bộ nhớ session, worker hoặc slot lập lịch. Nhiều connection đồng thời có thể làm tăng:

- Bộ nhớ dùng cho session và query execution.
- Số worker cần lập lịch và chuyển ngữ cảnh.
- Số truy vấn cùng cạnh tranh CPU, I/O và buffer cache.
- Khả năng tranh chấp khóa trên các hàng hoặc index nóng.
- Số transaction đồng thời và lượng phiên bản dữ liệu cần giữ.
- Áp lực connection management, authentication và network.

Tăng pool size có thể cải thiện throughput khi database còn năng lực và ứng dụng trước đó bị giới hạn bởi số connection. Nhưng sau một điểm, throughput có thể không tăng trong khi latency và contention tăng.

### 3.1. Pool nhỏ quá

Khi pool quá nhỏ so với mức đồng thời cần thiết:

- Request chờ connection dù database vẫn còn năng lực.
- Acquire latency và pending tăng.
- Thread ứng dụng bị giữ trong lúc chờ.
- Một truy vấn giữ connection lâu có thể chặn nhiều request ngắn phía sau.

Tuy nhiên, không nên tăng pool ngay khi thấy pending. Nếu connection đang bị giữ lâu do SQL chậm hoặc transaction mở rộng, tăng pool chỉ đưa thêm truy vấn vào database và có thể làm tình trạng nặng hơn.

### 3.2. Pool lớn quá

Pool lớn có thể làm nhiều truy vấn cùng chạy. Nếu database đã bão hòa CPU hoặc I/O, thêm connection không làm tăng số công việc hoàn tất mỗi giây. Chúng chỉ cạnh tranh tài nguyên, tăng context switching, lock wait và memory pressure.

Ví dụ, database xử lý hiệu quả khoảng 40 truy vấn đồng thời cho workload hiện tại. Nếu ứng dụng mở 300 connection và tất cả cùng chạy truy vấn nặng, database có thể phải lập lịch nhiều công việc hơn năng lực thực tế. Latency của từng truy vấn tăng, connection bị giữ lâu hơn và pool càng dễ bão hòa.

Con số tối ưu phải được đo theo loại truy vấn, schema, index, phần cứng, engine và mức tải. Không có quy tắc chung rằng mỗi CPU core cần một số connection cố định.

## 4. Tính tổng kết nối trên toàn hệ thống

maximumPoolSize thường áp dụng cho một pool trong một process hoặc một instance ứng dụng. Nếu chạy nhiều pod/VM, tổng số connection có thể là bội số của giá trị đó.

Ví dụ:

| Thành phần | Số lượng | Pool tối đa mỗi instance | Tổng tối đa |
|---|---:|---:|---:|
| API service | 6 | 20 | 120 |
| Worker service | 3 | 10 | 30 |
| Reporting service | 2 | 8 | 16 |
| Tổng ứng dụng | 11 | — | 166 |

Database còn cần connection cho DBA, migration, monitoring, replication, scheduler và dịch vụ khác. Vì vậy, không thể dùng toàn bộ giới hạn max_connections cho pool của một ứng dụng.

### 4.1. Công thức ngân sách kết nối

Một cách lập ngân sách đơn giản:

\[
N_{\text{app}} =
\sum_{i=1}^{k}
R_i \times P_i
\]

Trong đó:

- \(R_i\) là số replica của nhóm ứng dụng i.
- \(P_i\) là pool tối đa trên mỗi replica.
- \(N_{\text{app}}\) là tổng connection tối đa mà các pool có thể mở.

Ngân sách cần thỏa:

\[
N_{\text{app}} + N_{\text{other}} + N_{\text{reserve}}
\leq N_{\text{db-limit}}
\]

N_other là kết nối cho tác vụ ngoài ứng dụng chính; N_reserve là phần dự phòng vận hành và failover. Công thức này chỉ là giới hạn cấu hình. Số connection tối đa cho phép không phải số connection database có thể xử lý hiệu quả cùng lúc.

### 4.2. Tính cả kịch bản scale-out và failover

Nếu autoscaling tăng số replica từ 6 lên 15, tổng pool có thể tăng hơn gấp đôi ngay cả khi mỗi replica không thay đổi cấu hình. Nếu hai cụm cùng trỏ về database trong lúc chuyển vùng, tổng connection tạm thời có thể cao hơn trạng thái bình thường.

Khi lập ngân sách, cần tính:

- Số replica tối đa theo autoscaler.
- Rolling deployment khi phiên bản cũ và mới cùng tồn tại.
- Blue/green deployment với hai cụm chạy song song.
- Failover và thời gian node cũ chưa ngắt hết connection.
- Pool riêng cho read/write, tenant hoặc datasource khác nhau.
- Connection do migration, monitoring và công cụ quản trị mở.

Không chỉ kiểm tra cấu hình ở một pod. Hãy kiểm tra tổng số session thực tế trên database và đối chiếu với số pool/replica đang chạy.

## 5. Dùng thời gian chiếm connection để ước lượng mức đồng thời

Một cách hữu ích để ước lượng nhu cầu connection là dùng định luật Little:

\[
L = \lambda \times W
\]

Trong đó:

- \(L\) là số công việc trung bình đang ở trong hệ thống.
- \(\lambda\) là tốc độ hoàn tất hoặc đến trung bình, tính theo công việc mỗi giây.
- \(W\) là thời gian trung bình một công việc nằm trong hệ thống.

Với pool, có thể dùng gần đúng số connection trung bình đang được giữ:

\[
C_{\text{avg}} \approx \lambda_{\text{db}} \times T_{\text{hold}}
\]

T_hold là thời gian một request giữ connection, bao gồm thời gian SQL và mọi khoảng thời gian ứng dụng giữ connection giữa các thao tác. Phải dùng thời gian giữ connection đo được, không chỉ thời gian SQL.

Ví dụ workload hoàn tất 500 thao tác database mỗi giây và mỗi thao tác giữ connection trung bình 40 ms:

\[
500 \times 0.040 = 20
\]

Mức sử dụng trung bình tương ứng khoảng 20 connection đang được giữ nếu mỗi thao tác chỉ cần một connection trong một khoảng thời gian không chồng lấn. Đây là điểm xuất phát để benchmark, không phải kết luận pool size phải bằng 20. Cần cộng dự phòng cho burst, phân bố latency, transaction dài và nhiều câu SQL trên cùng connection.

### 5.1. Đo thời gian giữ connection

Giả sử một request:

1. Mượn connection.
2. Chạy SELECT trong 15 ms.
3. Chuyển đổi dữ liệu trong 80 ms.
4. Gọi một HTTP service trong 200 ms.
5. Chạy UPDATE trong 10 ms.
6. Trả connection.

SQL chỉ chạy 25 ms, nhưng connection bị giữ khoảng 305 ms. Pool phải tính theo khoảng thời gian 305 ms. Nếu chuyển bước gọi HTTP ra ngoài transaction/connection, usage time có thể giảm đáng kể.

### 5.2. Đừng sizing chỉ theo trung bình

Nếu p95 usage time cao hơn nhiều so với trung bình, một số request dài có thể chiếm connection và làm request ngắn phải chờ.

Hãy xem histogram của acquire time và usage time, không chỉ giá trị trung bình. Theo dõi cả p95/p99, số request đang giữ connection lâu và phân bố theo loại truy vấn.

## 6. Hàng đợi, backpressure và giới hạn đồng thời

Pool là một điểm giới hạn đồng thời. Khi tất cả connection đã được mượn, request mới phải chờ hoặc bị từ chối sau timeout.

Một hàng đợi hữu ích cần có giới hạn:

- Số request tối đa được chờ.
- Thời gian chờ tối đa.
- Số thread hoặc task được phép đợi.
- Chính sách từ chối hoặc giảm tải khi vượt ngưỡng.

Backpressure là cơ chế báo ngược cho tầng gọi rằng hệ thống không thể tiếp nhận thêm việc ở tốc độ hiện tại. Thay vì để request xếp hàng vô hạn, ứng dụng có thể trả lỗi tạm thời, giảm concurrency, giới hạn tốc độ hoặc đưa công việc vào hàng đợi bền vững.

### 6.1. Vì sao hàng đợi dài làm latency tăng dây chuyền?

Khi database chậm:

1. Connection được giữ lâu hơn.
2. Active connection tiến gần giới hạn pool.
3. Request mới chờ trong pool.
4. Thread ứng dụng bị chiếm trong lúc chờ.
5. Thread pool cạn và request ở tầng HTTP cũng xếp hàng.
6. Deadline của request hết trước khi SQL được chạy.
7. Client retry, tạo thêm request và làm tải tăng.

Đây là một vòng phản hồi tiêu cực. Timeout, queue limit, rate limit và retry policy cần phối hợp để chặn vòng lặp.

### 6.2. Queue không thay thế năng lực xử lý

Tăng hàng đợi chỉ có thể hấp thụ burst ngắn nếu database sẽ xử lý hết backlog sau đó. Nếu tốc độ request đến lâu dài lớn hơn tốc độ database hoàn tất, backlog tiếp tục tăng. Khi đó cần giảm tải, tăng năng lực có kiểm soát hoặc tối ưu truy vấn.

Một queue lớn có thể che giấu sự cố trong vài phút rồi làm toàn bộ request timeout cùng lúc. Hãy chọn queue capacity dựa trên deadline và khả năng phục hồi, không dựa trên số thread tối đa mà ứng dụng có thể tạo.

## 7. Thời gian chờ lấy connection và timeout

Acquire timeout giới hạn thời gian request chờ pool cấp connection. Nó khác với query timeout và lock timeout:

| Timeout | Giới hạn điều gì? |
|---|---|
| Pool acquisition timeout | Thời gian chờ mượn connection từ pool |
| Connection creation timeout | Thời gian tạo kết nối mới, nếu thư viện có cấu hình riêng |
| Query/command timeout | Thời gian chờ kết quả câu lệnh ở driver |
| Statement timeout | Giới hạn thực thi ở database server |
| Lock timeout | Thời gian chờ lấy khóa |
| Transaction timeout/deadline | Thời gian cho toàn bộ đơn vị giao dịch hoặc công việc |

Ví dụ một API có deadline 1 giây:

- Pool acquire timeout: 150 ms.
- Statement timeout: 600 ms.
- Client command timeout: 700 ms.
- Phần còn lại dành cho xử lý ứng dụng và trả response.

Đây chỉ là ví dụ phân bổ. Nếu pool wait đã tiêu thụ 150 ms, thời gian còn lại của request giảm tương ứng. Không đặt query timeout lớn hơn deadline của API rồi để ứng dụng chờ một kết quả không còn giá trị.

Khi acquire timeout xảy ra, thường chưa có SQL nào được gửi tới database. Log lỗi như query timeout sẽ gây chẩn đoán sai nếu nguyên nhân thật là pool exhaustion.

## 8. Vòng đời connection và quản lý tài nguyên

Một connection phải được trả về pool dù câu SQL thành công, thất bại, timeout hay code phát sinh exception. Nếu ứng dụng quên đóng connection, pool không thể tái sử dụng nó và số active có thể tăng dần đến maximum.

### 8.1. Dùng try-with-resources trong Java

Với JDBC, Connection, PreparedStatement và ResultSet đều cần được đóng. Try-with-resources bảo đảm gọi close kể cả khi có exception:

~~~java
String sql = "SELECT id, status FROM orders WHERE id = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, orderId);

    try (ResultSet resultSet = statement.executeQuery()) {
        if (resultSet.next()) {
            return new OrderStatus(
                resultSet.getLong("id"),
                resultSet.getString("status")
            );
        }
    }
}
~~~

Trong pool JDBC, connection.close() trả connection về pool. Không đóng connection có thể gây leak; đóng nhiều lần thường được wrapper xử lý, nhưng không nên dựa vào hành vi đó.

### 8.2. Không giữ connection trong lúc làm việc ngoài database

Tránh mẫu:

~~~java
try (Connection connection = dataSource.getConnection()) {
    Order order = loadOrder(connection, orderId);
    PaymentResult result = paymentClient.charge(order);
    updatePayment(connection, orderId, result);
}
~~~

Nếu payment service mất 2 giây, connection bị giữ suốt thời gian chờ dù database không làm việc. Nếu transaction đang mở, khóa có thể còn được giữ trong suốt cuộc gọi mạng.

Thiết kế tốt hơn thường là:

1. Đọc dữ liệu trong một transaction ngắn.
2. Commit và trả connection.
3. Gọi dịch vụ bên ngoài ngoài transaction.
4. Mở transaction mới để ghi kết quả, dùng trạng thái/idempotency để xử lý retry.

Không thể áp dụng máy móc nếu nghiệp vụ cần tính nguyên tử xuyên nhiều hệ thống; khi đó cần saga, outbox hoặc giao thức phối hợp phù hợp thay vì giữ connection và khóa trong lúc gọi mạng.

### 8.3. Transaction phải có ranh giới rõ

Connection có thể được trả về pool khi transaction đã commit hoặc rollback. Không để transaction mở qua nhiều thao tác không cần thiết.

Một transaction dài có thể:

- Giữ row/table lock lâu.
- Giữ snapshot và phiên bản dữ liệu cũ.
- Làm tăng deadlock hoặc lock wait.
- Giữ connection và giảm số connection sẵn sàng.
- Làm vacuum/undo cleanup hoặc log truncation bị trì hoãn tùy engine.

Pool sizing không thể bù cho transaction kéo dài do thiết kế ứng dụng.

## 9. Ví dụ cấu hình Java với HikariCP

HikariCP là một JDBC connection pool phổ biến. Ví dụ cấu hình:

~~~properties
spring.datasource.hikari.maximum-pool-size=16
spring.datasource.hikari.minimum-idle=4
spring.datasource.hikari.connection-timeout=500
spring.datasource.hikari.idle-timeout=600000
spring.datasource.hikari.max-lifetime=1740000
spring.datasource.hikari.validation-timeout=1000
~~~

Ý nghĩa khái quát:

- maximum-pool-size: số connection tối đa của pool.
- minimum-idle: số connection nhàn rỗi mục tiêu mà pool cố duy trì.
- connection-timeout: thời gian tối đa chờ lấy connection, tính bằng mili giây.
- idle-timeout: thời gian connection nhàn rỗi có thể được thu hồi khi pool có nhiều hơn minimum idle.
- max-lifetime: tuổi thọ tối đa của connection trước khi pool thay thế.
- validation-timeout: thời gian tối đa kiểm tra connection còn hợp lệ.

Các giá trị trên chỉ minh họa cách viết cấu hình, không phải khuyến nghị dùng nguyên trạng. maximum-pool-size=16 cần được tính cùng số replica và giới hạn database. minimum-idle thấp hơn maximum giúp pool co giãn theo tải, nhưng có thể làm tăng thời gian tạo connection khi burst. Một số workload cần giữ sẵn nhiều idle connection; hãy đo.

### 9.1. Leak detection

HikariCP có leakDetectionThreshold để cảnh báo connection bị giữ lâu hơn ngưỡng. Đây là công cụ chẩn đoán, không phải cơ chế tự thu hồi connection bị leak.

Một connection giữ lâu có thể là:

- Leak thật do quên close.
- Transaction hợp lệ nhưng kéo dài.
- Truy vấn chậm hoặc bị block.
- Code giữ connection trong lúc gọi dịch vụ ngoài.

Đọc stack trace và usage duration để phân biệt. Đặt ngưỡng quá thấp tạo nhiều cảnh báo giả; đặt quá cao có thể phát hiện leak quá muộn.

### 9.2. maxLifetime và kết nối bị hạ tầng đóng

Một số database, proxy, firewall hoặc load balancer đóng connection sau một thời gian. maxLifetime nên thấp hơn giới hạn tuổi thọ của tầng hạ tầng nếu có thể, để pool chủ động thay connection trước khi nó bị đóng bất ngờ.

Không đặt maxLifetime quá ngắn vì sẽ tạo churn: nhiều kết nối phải xác thực và khởi tạo lại. Pool thường có cơ chế lệch thời điểm retire để tránh đóng hàng loạt; hãy kiểm tra hành vi của phiên bản thư viện.

### 9.3. Keepalive và validation

Validation giúp phát hiện connection không còn dùng được trước khi cấp cho request. Keepalive có thể giữ connection nhàn rỗi không bị proxy hoặc firewall đóng, nhưng tạo thêm traffic nền.

Không bật validation query nặng cho mỗi lần mượn connection nếu driver có JDBC4 isValid() hoặc cơ chế hiệu quả hơn. Hãy kiểm tra cấu hình của pool và driver đang dùng.

## 10. Kết hợp pool với thread pool và request concurrency

Nếu web server có 300 request thread nhưng datasource chỉ có 20 connection, tối đa khoảng 20 request có thể đồng thời mượn connection từ pool đó. Các request còn lại có thể chờ.

Đây không nhất thiết là lỗi. Giới hạn đồng thời có thể bảo vệ database. Nhưng nếu hàng trăm thread bị giữ trong acquire wait, chúng có thể làm cạn thread pool và khiến endpoint không cần database cũng bị ảnh hưởng.

### 10.1. Giới hạn concurrency trước pool

Có thể dùng semaphore, bulkhead hoặc giới hạn concurrency theo endpoint để chỉ cho một số request vào vùng cần database. Khi đạt giới hạn, request mới được từ chối hoặc xếp hàng có kiểm soát.

Ví dụ khái niệm:

~~~java
if (!databasePermit.tryAcquire()) {
    throw new ServiceOverloadedException();
}

try {
    return service.executeDatabaseWork();
} finally {
    databasePermit.release();
}
~~~

Permit phải được giải phóng trong finally. Số permit cần phối hợp với pool size và các luồng khác dùng cùng database; không cấp permit bằng maximum pool size cho từng endpoint riêng lẻ nếu chúng cùng chia sẻ một pool.

### 10.2. Virtual threads không làm tăng năng lực database

Virtual threads có thể giảm chi phí thread ở ứng dụng và cho phép nhiều tác vụ chờ I/O hơn. Chúng không làm database có thêm CPU, memory hoặc worker. Nếu hàng nghìn virtual thread cùng xin một pool 20 connection, vẫn chỉ có tối đa 20 connection được cấp và phần còn lại vẫn phải chờ hoặc bị giới hạn.

Pool và concurrency limit vẫn cần được sizing theo năng lực database, kể cả khi ứng dụng dùng virtual threads hoặc reactive programming.

## 11. Pool ở ứng dụng và connection pooler/proxy

Có hai tầng thường gặp:

- Application pool: quản lý connection từ từng process ứng dụng đến database hoặc proxy.
- Database-side pooler/proxy: nhận nhiều client connection và ghép/multiplex chúng vào ít server connection hơn, nếu chế độ pooling cho phép.

Ví dụ PgBouncer có các chế độ:

| Chế độ | Cách gán server connection | Hệ quả |
|---|---|---|
| Session pooling | Giữ server connection trong suốt client session | Tương thích session state tốt hơn nhưng ít multiplex |
| Transaction pooling | Gán server connection trong transaction, trả lại sau COMMIT/ROLLBACK | Tăng khả năng chia sẻ nhưng giới hạn tính năng phụ thuộc session |
| Statement pooling | Trả server connection sau mỗi statement; không cho transaction nhiều statement | Hạn chế hơn và không phù hợp mọi ứng dụng |

Transaction pooling có thể không tương thích với session state như temporary table, session-level SET, advisory lock gắn session, cursor giữ qua nhiều transaction hoặc prepared statement theo cách ứng dụng mong đợi. Khả năng hỗ trợ một số tính năng đã thay đổi theo phiên bản PgBouncer; phải kiểm tra tài liệu và cấu hình thực tế.

Không phải mọi proxy database đều multiplex được mọi loại giao dịch. Nếu dùng pooler, cần phân biệt client connections, server connections, pool theo database/user và số request chờ ở cả hai tầng.

### 11.1. Tránh nhân đôi hàng đợi

Nếu application pool có hàng đợi lớn và proxy cũng có hàng đợi lớn, request có thể chờ ở nhiều tầng. Điều này làm thời gian chờ khó quan sát và có thể khiến deadline hết trước khi SQL tới database.

Đặt timeout theo thứ tự và đo:

- Thời gian chờ application pool.
- Thời gian chờ proxy/server pool.
- Thời gian chờ lock.
- Thời gian thực thi SQL.

Mỗi request nên có trace hoặc correlation ID để nối các khoảng thời gian này.

## 12. Đọc dấu hiệu bão hòa pool

Một pool có thể ở các trạng thái:

| Active | Idle | Pending | Cách diễn giải ban đầu |
|---:|---:|---:|---|
| Thấp | Cao | 0 | Pool còn dư, chưa có dấu hiệu bão hòa |
| Gần max | Thấp | 0 | Pool đang sử dụng cao nhưng chưa có hàng chờ; cần xem xu hướng và usage time |
| Bằng max | 0 | Tăng | Pool bão hòa, request phải chờ |
| Thấp | Thấp | Tăng | Có thể pool đang tạo connection chậm, connection lỗi hoặc metric không cùng thời điểm |
| Cao | Cao | 0 | Có thể pool max lớn và một phần connection đang idle; xem tổng và nhu cầu thực |

Đây là cách đọc sơ bộ. Cần ghép với acquire latency, connection creation, database session count, query duration và wait events.

### 12.1. Pool bão hòa nhưng database chưa bận

Có thể xảy ra khi:

- Ứng dụng giữ connection trong lúc gọi dịch vụ ngoài.
- Connection leak.
- Transaction idle hoặc mở quá lâu.
- Pool có connection lỗi hoặc validation chậm.
- Một số request bị block ở tầng khác trong khi vẫn giữ connection.

Kiểm tra stack trace leak detection, connection usage duration, transaction age và session state trên database.

### 12.2. Database bão hòa dù pool chưa đầy

Database có thể chậm do I/O, CPU, memory pressure hoặc lock contention trước khi pool đạt maximum. Khi query duration tăng, active connection sẽ dần tăng vì connection được giữ lâu hơn.

Kiểm tra actual execution plan, physical reads, wait events, lock blockers, sort/hash spill và throughput. Đừng tăng pool chỉ vì active tăng; xác định database còn năng lực tiếp nhận thêm truy vấn hay không.

## 13. Chẩn đoán và quan sát

### 13.1. Metric ở tầng ứng dụng

Theo dõi theo từng pool:

- Active, idle, total và maximum.
- Pending/waiting thread.
- Acquire latency p50/p95/p99.
- Connection usage duration p50/p95/p99.
- Connection creation và validation failure.
- Acquire timeout và connection leak warning.
- Số lần connection bị retire hoặc đóng bất thường.
- Số request đang giữ connection lâu hơn ngưỡng.

Phân tách theo datasource, service, replica và workload. Metric tổng toàn cụm có thể che một pod bị leak hoặc một pool riêng bị bão hòa.

### 13.2. Metric ở database

Đối chiếu với:

- Số session/connection theo trạng thái.
- Active query, idle session và idle-in-transaction.
- CPU, memory, IOPS, read/write latency.
- Lock wait, deadlock và wait events.
- Transaction age và số transaction mở.
- Throughput commit/rollback.
- Số truy vấn, query duration và physical/logical reads.

Nếu pool báo active 20 nhưng database chỉ thấy 5 query đang chạy, phần chênh lệch có thể là connection idle trong transaction hoặc ứng dụng đang giữ connection mà không gửi SQL.

### 13.3. Trace một request từ đầu đến cuối

Một trace hữu ích tách các span:

1. Chờ connection pool.
2. Gửi câu SQL.
3. Database execute và chờ kết quả.
4. Đọc result set.
5. Xử lý dữ liệu trong ứng dụng.
6. Trả connection về pool.

Nếu chỉ ghi tổng thời gian repository method, sẽ khó biết request chậm vì acquire wait, SQL hay code giữ connection sau khi truy vấn hoàn tất.

## 14. Quy trình sizing pool có kiểm soát

1. **Đo workload:** request/transaction mỗi giây, số câu SQL mỗi request và thời gian giữ connection.
2. **Tách workload:** API, batch, reporting, worker và migration có đặc tính khác nhau.
3. **Tính ngân sách toàn fleet:** nhân pool size với replica tối đa, cộng các client khác và phần dự phòng database.
4. **Chọn pool ban đầu:** dùng Little's Law và số liệu occupancy để đưa ra giá trị thử nghiệm, không dùng một công thức cứng.
5. **Giới hạn concurrency:** bảo đảm tổng số truy vấn đồng thời không vượt năng lực database trong workload đại diện.
6. **Đặt queue/acquire timeout:** giới hạn thời gian chờ và tránh backlog vô hạn.
7. **Đo dưới tải:** tăng dần concurrency, theo dõi throughput, p95/p99, CPU, I/O, lock wait và pending.
8. **Tìm điểm bão hòa:** xác định khi tăng pool không còn tăng throughput hoặc làm latency tăng mạnh.
9. **Kiểm tra usage time:** tìm transaction dài, connection leak và công việc ngoài database trong thời gian mượn.
10. **Kiểm tra scale-out/failover:** chạy thử với số replica tối đa và kịch bản rolling deployment.
11. **Điều chỉnh:** thay đổi pool size, query, index, transaction boundary hoặc backpressure dựa trên bằng chứng.
12. **Theo dõi sau triển khai:** cảnh báo khi pending, acquire p95, active/max hoặc timeout tăng bất thường.

### 14.1. Ví dụ thử nghiệm pool size

Giả sử một service có thể chạy 8 replica. Thử ba cấu hình:

| Pool mỗi replica | Tổng connection tối đa | Câu hỏi cần trả lời |
|---:|---:|---|
| 8 | 64 | Có đủ throughput không? Pending và acquire p95 thế nào? |
| 12 | 96 | Throughput có tăng không? Database CPU/I/O có bão hòa không? |
| 16 | 128 | Lợi ích còn tăng hay latency, lock wait và memory pressure xấu đi? |

Chạy cùng workload và cùng dữ liệu, giữ nguyên cấu hình database. Chọn cấu hình có throughput đạt mục tiêu, latency ổn định và còn khoảng dự phòng cho tác vụ vận hành. Nếu pool 16 không tăng throughput nhưng làm p99 cao hơn, cấu hình 8 hoặc 12 có thể phù hợp hơn.

Không chọn cấu hình chỉ vì pending bằng 0. Pool quá lớn có thể xóa hàng đợi ở ứng dụng nhưng tạo một hàng đợi dài hơn bên trong database.

## 15. Các lỗi thiết kế thường gặp

- **Tăng maximum pool size mỗi khi có timeout:** có thể làm database quá tải hơn.
- **Chỉ nhìn active connection:** không biết connection đang chạy SQL hay bị giữ trong ứng dụng.
- **Không tính số replica:** cấu hình pool hợp lý trên một process có thể vượt giới hạn khi scale-out.
- **Để queue vô hạn:** request chờ quá deadline và chiếm thread.
- **Giữ connection trong lúc gọi HTTP hoặc xử lý CPU:** làm usage time tăng dù SQL ngắn.
- **Không đóng connection trong exception path:** gây leak và pool exhaustion.
- **Trả connection khi transaction chưa kết thúc:** request tiếp theo có thể kế thừa transaction hoặc session state.
- **Đặt minIdle bằng maximum mà không cần thiết:** giữ nhiều session nhàn rỗi và tăng áp lực database.
- **Đặt maxLifetime quá ngắn:** tạo connection churn và xác thực liên tục.
- **Đặt acquire timeout quá dài:** che bão hòa và làm request hết deadline ở tầng khác.
- **Nhầm pool timeout với query timeout:** dẫn đến chẩn đoán sai nguyên nhân.
- **Dùng một pool cho workload có đặc tính rất khác mà không có giới hạn:** báo cáo dài có thể chiếm hết connection của API.
- **Cho rằng virtual threads loại bỏ giới hạn connection:** database vẫn có giới hạn session và năng lực xử lý.
- **Dùng transaction pooling mà không kiểm tra session state:** có thể làm hỏng giả định về temporary table, SET hoặc prepared statement.
- **Chỉ benchmark ở tải thấp:** không thấy điểm bão hòa và hành vi queue khi burst.

## 16. Checklist vận hành connection pool

- [ ] Đã đo active, idle, pending, total và maximum theo từng pool.
- [ ] Có histogram acquire time và connection usage time.
- [ ] Đã phân biệt pool wait, query timeout, lock timeout và connection creation.
- [ ] Đã tính tổng connection từ mọi replica, service và datasource.
- [ ] Ngân sách còn chỗ cho DBA, monitoring, replication và migration.
- [ ] Pool size được kiểm chứng dưới tải đại diện và kịch bản scale-out.
- [ ] Database CPU, memory, I/O và lock wait chưa bị bão hòa ở mức pool đã chọn.
- [ ] Request có queue limit, acquire timeout và backpressure.
- [ ] Connection được đóng trong mọi nhánh thành công và exception.
- [ ] Transaction ngắn và không giữ connection khi gọi dịch vụ ngoài.
- [ ] Session state được reset trước khi connection quay lại pool.
- [ ] Leak detection và cảnh báo connection giữ lâu được cấu hình hợp lý.
- [ ] maxLifetime phù hợp giới hạn của database/proxy/firewall.
- [ ] Workload API, batch và reporting có giới hạn đồng thời phù hợp.
- [ ] Nếu có proxy/pooler, đã đo hàng đợi ở cả application pool và server pool.
- [ ] Đã kiểm thử failover, rolling deployment và retry khi pool cạn.

Connection pool giúp tái sử dụng kết nối và giới hạn mức đồng thời từ ứng dụng đến database. Active, idle và pending cho biết pool đang được sử dụng ra sao; acquire time và usage time giải thích request chờ ở đâu và connection bị giữ bao lâu. Hãy sizing dựa trên thời gian chiếm connection, năng lực database và tổng số replica, sau đó đặt hàng đợi cùng timeout có giới hạn. Khi pool bão hòa, cần phân biệt SQL chậm, lock contention, transaction dài và connection leak trước khi tăng số kết nối.

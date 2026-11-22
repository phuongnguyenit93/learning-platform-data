# Phân biệt thời gian chờ lấy kết nối với thời gian chạy SQL

## Vì sao cần tách thời gian lấy kết nối và thời gian chạy SQL?

Một API truy vấn cơ sở dữ liệu có thể phản hồi chậm dù câu SQL chạy nhanh. Ví dụ, database hoàn thành truy vấn trong 20 ms nhưng request mất 500 ms trước khi nhận được kết quả. Nếu chỉ xem thời gian thực thi SQL, nhóm vận hành có thể kết luận sai rằng database không có vấn đề và bỏ qua nguyên nhân thật: ứng dụng phải chờ connection pool cấp một kết nối.

Ngược lại, thời gian lấy kết nối có thể rất thấp nhưng request vẫn chậm vì SQL thực thi lâu, phải chờ khóa, truyền nhiều hàng qua mạng hoặc ứng dụng xử lý kết quả quá lâu. Muốn tối ưu đúng, cần chia thời gian end-to-end thành các giai đoạn có thể đo riêng.

Một request điển hình có thể trải qua:

1. Chờ lấy connection từ pool.
2. Nếu pool cần mở kết nối mới, thực hiện DNS lookup, TCP handshake, TLS handshake và xác thực.
3. Gửi câu lệnh qua driver và mạng.
4. Database parse, lập kế hoạch nếu cần, thực thi và chờ tài nguyên.
5. Trả metadata và hàng kết quả qua mạng.
6. Driver đọc (fetch) dữ liệu; ứng dụng ánh xạ và xử lý kết quả.
7. Ứng dụng đóng hoặc trả connection về pool.

Các giai đoạn này có thể chồng lấp hoặc được driver thực hiện theo cách khác nhau. Một số API đo execute bao gồm round-trip đến server và nhận phần kết quả đầu tiên; fetch phần còn lại được đo riêng. Một số công cụ chỉ ghi tổng thời gian từ lúc gửi lệnh đến lúc đọc hết kết quả. Vì vậy, phải hiểu chính xác điểm bắt đầu và kết thúc của từng metric.

Trong tối ưu hiệu năng cơ sở dữ liệu, cần phân biệt:

- **Connection acquisition time:** thời gian ứng dụng yêu cầu và nhận được một connection từ pool hoặc từ cơ chế tạo kết nối.
- **Physical connection establishment time:** thời gian tạo kết nối mới đến database, gồm các bước mạng và xác thực.
- **SQL client elapsed time:** thời gian phía client quan sát từ lúc gọi execute đến khi hoàn tất phần được đo; có thể bao gồm network round-trip, server processing và một phần hoặc toàn bộ fetch.
- **Database execution time:** thời gian database engine thực hiện công việc theo cách đo của hệ quản trị.
- **Result fetch/transfer time:** thời gian lấy và truyền hết các hàng kết quả đến ứng dụng.
- **Request end-to-end time:** tổng thời gian request ở tầng ứng dụng, gồm cả công việc ngoài database.

Một chỉ số tổng không cho biết giai đoạn nào đang chi phối. Bài học này hướng dẫn cách phân rã latency, đọc số liệu connection pool, đối chiếu telemetry ứng dụng với database, chẩn đoán pool exhaustion và tối ưu timeout/concurrency dựa trên đo đạc.

## Vòng đời connection trong ứng dụng

### Connection pool làm nhiệm vụ gì?

Mở kết nối vật lý đến database có chi phí: phân giải tên máy chủ, thiết lập TCP, thương lượng TLS nếu bật, xác thực, khởi tạo session và thiết lập trạng thái session. Nếu ứng dụng tạo rồi đóng kết nối vật lý cho mọi request, phần chi phí này có thể lớn và tạo tải không cần thiết cho database.

Connection pool giữ một số kết nối đã mở để tái sử dụng. Khi request cần database, nó mượn một connection đang rảnh; sau khi hoàn tất, connection được trả lại pool. Pool thường quản lý:

- Số connection tối thiểu và tối đa.
- Connection đang được sử dụng và đang rảnh.
- Request đang chờ một connection.
- Thời gian chờ lấy connection.
- Thời gian tạo connection vật lý.
- Kiểm tra connection còn hợp lệ hay không.
- Thời gian nhàn rỗi, tuổi thọ và chính sách loại bỏ connection.
- Các timeout và cơ chế phát hiện connection bị giữ quá lâu.

Pool không làm cho database có năng lực xử lý vô hạn. Nó giới hạn số session đồng thời và tái sử dụng kết nối. Nếu số request đồng thời vượt số connection khả dụng, request phải chờ. Nếu pool quá lớn, database có thể phải xử lý quá nhiều session và transaction cùng lúc, làm tăng context switching, lock contention, memory usage và queueing.

### Lấy connection từ pool không giống mở TCP connection

Khi ứng dụng gọi getConnection hoặc API tương đương, thời gian đo được có thể bao gồm nhiều trường hợp:

- **Pool có connection rảnh:** lấy connection và trả về gần như ngay lập tức.
- **Tất cả connection đang bận:** request xếp hàng đợi đến khi một connection được trả về.
- **Pool còn chỗ và cần tạo connection:** pool mở kết nối vật lý mới; thời gian lấy connection có thể bao gồm DNS, TCP, TLS, xác thực và khởi tạo session.
- **Connection cũ không hợp lệ:** pool loại bỏ hoặc kiểm tra lại rồi tạo connection khác.
- **Pool đã đạt giới hạn:** request tiếp tục chờ hoặc hết acquisition timeout.

Vì vậy, một metric acquisition cao chưa đủ để kết luận database chậm kết nối. Cần xem đồng thời số connection active, idle, pending, số lần tạo connection mới, thời gian tạo connection và số lần timeout.

### Trả connection về pool

Với JDBC, đóng đối tượng Connection lấy từ pool thường trả connection logic về pool thay vì đóng socket vật lý ngay lập tức. Nếu ứng dụng quên close, connection có thể bị giữ mãi và pool dần cạn.

Cách an toàn là dùng try-with-resources:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
         connection.prepareStatement(
             "SELECT order_id, status FROM orders WHERE order_id = ?")) {

    statement.setLong(1, orderId);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long id = resultSet.getLong("order_id");
            String status = resultSet.getString("status");
            // Xử lý kết quả cần thiết
        }
    }
}
~~~

Khối try-with-resources bảo đảm ResultSet, Statement và Connection logic được đóng theo thứ tự phù hợp ngay cả khi có exception. Với pool, thao tác close connection trả nó về pool. Cần tránh giữ connection trong lúc gọi HTTP service, chờ người dùng hoặc thực hiện công việc CPU dài không liên quan đến database.

### Connection pool và transaction

Một transaction thường cần giữ connection trong toàn bộ khoảng từ khi bắt đầu đến khi commit hoặc rollback. Nếu ứng dụng bắt đầu transaction rồi thực hiện nhiều thao tác ngoài database trước khi kết thúc, connection bị chiếm lâu dù database không thực thi SQL liên tục.

Ví dụ không tốt:

~~~java
Connection connection = dataSource.getConnection();
try {
    connection.setAutoCommit(false);

    updateOrder(connection, orderId);

    // Gọi dịch vụ từ xa trong khi vẫn giữ transaction/connection
    callExternalPaymentService();

    insertAuditRecord(connection, orderId);
    connection.commit();
} catch (Exception e) {
    connection.rollback();
    throw e;
} finally {
    connection.close();
}
~~~

Lời gọi dịch vụ ngoài có thể mất hàng trăm mili giây hoặc vài giây. Trong khoảng đó, connection và có thể cả lock database vẫn bị giữ. Pool dễ cạn khi tải tăng.

Thiết kế tốt hơn thường rút ngắn transaction và tách các bước ngoài database bằng một quy trình phù hợp như outbox, saga hoặc trạng thái trung gian nếu nghiệp vụ yêu cầu phối hợp nhiều hệ thống. Không được đơn giản chuyển lời gọi ra ngoài transaction nếu điều đó làm mất tính nguyên tử cần thiết; phải thiết kế lại ranh giới nghiệp vụ.

## Phân rã latency của một request

### Mô hình thời gian

Một mô hình đơn giản để phân tích:

~~~text
request_elapsed =
    application_queue_time
  + connection_acquisition_time
  + sql_client_elapsed_time
  + result_processing_time
  + other_application_time
~~~

Nếu pool cần tạo kết nối mới, connection_acquisition_time có thể chứa physical_connection_establishment_time. Nếu kết nối đã được mở sẵn, thời gian tạo vật lý không xuất hiện trong request đó.

Có thể phân rã SQL client elapsed thêm:

~~~text
sql_client_elapsed =
    driver_prepare_and_bind
  + network_round_trip
  + database_server_work
  + result_transfer_and_fetch
~~~

Đây chỉ là mô hình tư duy. Trong thực tế, driver có thể buffer kết quả, thực hiện prefetch, dùng protocol bất đồng bộ hoặc truyền dữ liệu theo nhiều round-trip. Server work và network transfer có thể xen kẽ khi ứng dụng fetch từng batch.

Không cộng các metric nếu chúng chồng lấp. Ví dụ, một span execute có thể đã bao gồm thời gian chờ server và round-trip; nếu cộng thêm server elapsed từ database vào tổng client elapsed, có thể đếm trùng.

### Ví dụ: pool wait chi phối

Một request có các số liệu:

| Giai đoạn | Thời gian |
|---|---:|
| Chờ lấy connection | 420 ms |
| Execute SQL phía client | 35 ms |
| Fetch và ánh xạ kết quả | 15 ms |
| Xử lý ứng dụng còn lại | 20 ms |
| Tổng | 490 ms |

SQL chỉ chiếm phần nhỏ. Tối ưu index để giảm execute từ 35 ms xuống 25 ms chỉ tiết kiệm khoảng 10 ms, trong khi nguyên nhân chính là 420 ms chờ pool. Cần điều tra connection bị giữ lâu, pool quá nhỏ, transaction dài hoặc database đã đạt giới hạn concurrency.

### Ví dụ: SQL chi phối

Một request khác:

| Giai đoạn | Thời gian |
|---|---:|
| Chờ lấy connection | 2 ms |
| Execute SQL phía client | 680 ms |
| Fetch và ánh xạ kết quả | 70 ms |
| Xử lý ứng dụng còn lại | 18 ms |
| Tổng | 770 ms |

Ở đây pool không phải nút thắt. Cần xem actual execution plan, logical reads, wait events, lock wait, sort/hash spill và lượng dữ liệu trả về. Tăng pool có thể không giúp và thậm chí làm database chịu thêm tải.

### Ví dụ: kết nối vật lý chi phối

Một service vừa khởi động hoặc liên tục tạo lại connection có thể ghi nhận acquisition time cao. Nếu pool không giữ được connection nóng, request có thể phải trả chi phí DNS, TCP, TLS, authentication và session initialization.

Cần so sánh thời gian tạo connection với thời gian mượn connection đã có sẵn. Nếu physical connection creation chậm, kiểm tra DNS, network path, TLS handshake, authentication provider, database listener, giới hạn session và chính sách pool. Nếu connection bị đóng quá thường xuyên, kiểm tra max lifetime, idle timeout, validation và network intermediary.

## Đọc metric của connection pool

### Các số liệu cơ bản

| Metric | Ý nghĩa | Dấu hiệu cần điều tra |
|---|---|---|
| Active connections | Connection đang được ứng dụng mượn | Liên tục chạm max có thể gây queue |
| Idle connections | Connection sẵn sàng được mượn | Bằng 0 trong giờ cao điểm có thể đi kèm pool wait |
| Pending/waiting borrowers | Request đang chờ connection | Tăng kéo dài cho thấy pool không đáp ứng kịp |
| Maximum pool size | Giới hạn connection của pool | Quá nhỏ gây chờ; quá lớn có thể quá tải DB |
| Acquisition time | Thời gian lấy connection | p95/p99 tăng cần phân biệt queue và tạo mới |
| Connection creation time | Thời gian mở connection vật lý | Cao có thể do DNS/TCP/TLS/auth hoặc DB listener |
| Usage/hold time | Thời gian connection được giữ | Cao có thể do transaction dài, fetch chậm hoặc connection leak |
| Timeout count | Số lần không lấy được connection đúng hạn | Có thể gây lỗi request và retry storm |
| Connection lifetime/idle | Tuổi thọ hoặc thời gian nhàn rỗi | Quá ngắn có thể tạo kết nối mới liên tục |

Tên metric khác nhau theo thư viện. HikariCP, Apache DBCP, c3p0, application server pool và driver có cách xuất metric riêng. Hãy dùng tài liệu của phiên bản đang chạy và kiểm tra đơn vị, histogram, counter hay gauge trước khi so sánh.

### Active cao không tự chứng minh pool quá nhỏ

Nếu active bằng maximum trong thời gian ngắn nhưng acquisition latency vẫn thấp, pool có thể đang hoạt động đúng. Nếu active luôn chạm maximum, pending tăng và acquisition p95/p99 tăng, đó là dấu hiệu pool đang bão hòa.

Cần xem usage duration. Nếu connection được giữ lâu do truy vấn chậm, transaction dài hoặc ứng dụng xử lý kết quả trong khi vẫn giữ connection, tăng pool chỉ tăng số session database cùng lúc. Tìm nguyên nhân giữ connection trước khi tăng giới hạn.

### Idle bằng không không luôn là sự cố

Pool có thể dùng gần hết connection trong một đợt tải ngắn nhưng nhanh chóng phục hồi. Một snapshot idle = 0 không đủ để kết luận. Cần xem chuỗi thời gian của active, idle, pending, acquisition latency và timeout.

Nếu idle thường xuyên bằng 0 và pending tăng liên tục, pool không có đủ connection rảnh so với tốc độ request cần mượn. Khi đó hãy phân biệt do pool max quá thấp hay connection usage time quá dài.

### Phát hiện connection leak

Connection leak xảy ra khi ứng dụng mượn connection nhưng không trả lại pool. Dấu hiệu:

- Active tăng dần và không giảm sau khi request hoàn tất.
- Idle giảm về 0 dù lưu lượng request không tăng tương ứng.
- Pending và acquisition timeout tăng.
- Usage time có đuôi dài bất thường.
- Một số connection giữ transaction hoặc session state lâu hơn dự kiến.

Bật leak detection hoặc tracing trong môi trường phù hợp để tìm call site giữ connection quá lâu. Một cảnh báo leak có thể là transaction hợp lệ nhưng dài; cần kiểm tra stack trace và thời gian thực tế trước khi sửa. Không giảm leak detection threshold quá thấp nếu nó tạo nhiều cảnh báo giả.

## Phân biệt các giai đoạn thời gian bằng instrumentation

### Đo acquisition riêng

Đặt timer quanh lời gọi lấy connection:

~~~java
long started = System.nanoTime();
try (Connection connection = dataSource.getConnection()) {
    long acquiredAt = System.nanoTime();
    long acquisitionNanos = acquiredAt - started;

    // Ghi acquisitionNanos vào histogram/trace
    executeBusinessQuery(connection);
}
~~~

Phép đo này ghi thời gian từ lúc ứng dụng gọi getConnection đến lúc nhận connection. Nếu pool phải tạo physical connection, khoảng đo có thể bao gồm cả thời gian tạo đó. Để tách rõ queue wait và creation time, cần dùng metric của pool hoặc instrumentation bên trong pool; không thể suy ra chỉ từ một timer ngoài.

Dùng monotonic clock như System.nanoTime cho thời gian trôi qua. Không dùng đồng hồ lịch có thể bị điều chỉnh bởi NTP để tính duration.

### Đo execute và fetch riêng

Ví dụ JDBC:

~~~java
long executeStarted = System.nanoTime();
boolean hasResult = statement.execute();
long executeReturned = System.nanoTime();

long executeNanos = executeReturned - executeStarted;

long fetchStarted = System.nanoTime();
if (hasResult) {
    try (ResultSet rs = statement.getResultSet()) {
        while (rs.next()) {
            consume(rs);
        }
    }
}
long fetchNanos = System.nanoTime() - fetchStarted;
~~~

executeNanos là thời gian từ lúc gọi execute đến khi driver trả về từ lời gọi đó. Tùy driver và protocol, nó có thể bao gồm gửi lệnh, server xử lý đến điểm có kết quả đầu tiên và nhận metadata hoặc một phần dữ liệu. fetchNanos đo thời gian ứng dụng duyệt phần kết quả được cung cấp qua ResultSet, có thể bao gồm network transfer theo batch và xử lý client.

Để hiểu đúng, kiểm tra driver có fetch size, prefetch hoặc buffering ra sao. Nếu driver tải toàn bộ kết quả vào bộ nhớ trước khi execute trả về, executeNanos có thể bao gồm phần lớn transfer. Không xem hai số đo là server execution time thuần túy.

### Đo thời gian phía database

Dùng thống kê query và công cụ của database để xem thời gian server-side, số lần gọi, số hàng, logical reads, physical reads, CPU và wait events. Một số hệ quản trị có query store hoặc statement statistics; một số cung cấp actual execution plan hoặc trace theo session.

Cần ghép dữ liệu ứng dụng và database bằng trace ID, session ID, query ID hoặc query fingerprint phù hợp. Tránh ghi tham số nhạy cảm hoặc toàn bộ SQL chứa dữ liệu cá nhân vào log. Có thể dùng normalized query fingerprint và metadata an toàn.

Thời gian database báo cáo có thể khác thời gian client:
- Client có thể bắt đầu đo trước khi gửi lệnh.
- Server có thể ghi nhận thời gian thực thi nhưng không gồm toàn bộ network transfer.
- Client có thể fetch chậm hoặc xử lý kết quả lâu.
- Một truy vấn có thể chờ network hoặc client consumption tùy protocol và server behavior.
- Công cụ có thể báo CPU time, elapsed time hoặc wait time theo định nghĩa khác nhau.

Đừng so sánh hai metric chỉ vì cả hai đều có đơn vị millisecond. Hãy đọc định nghĩa, điểm bắt đầu/kết thúc và phần công việc được bao gồm.

## Network round-trip và truyền kết quả

### Round-trip time

Một câu SQL cần gửi từ client đến server và nhận phản hồi. Độ trễ mạng, TLS, proxy, load balancer và khoảng cách địa lý có thể ảnh hưởng thời gian round-trip. Nếu ứng dụng gửi nhiều câu lệnh tuần tự trong một transaction, mỗi round-trip có thể cộng thêm latency.

Ví dụ, một thao tác nghiệp vụ thực hiện 30 câu SQL nhỏ tuần tự trên đường truyền có round-trip 8 ms có thể tiêu tốn ít nhất khoảng 240 ms chỉ cho các lượt trao đổi, chưa tính server work và transfer. Nếu có thể gộp thao tác, dùng batch hoặc một câu SQL phù hợp, số round-trip có thể giảm.

Tuy nhiên, batch quá lớn có thể tăng log, lock duration, memory và rollback cost. Chọn batch size dựa trên workload và ranh giới transaction.

### Fetch size và lượng dữ liệu trả về

Một truy vấn có thể thực thi nhanh nhưng fetch chậm vì trả về hàng triệu hàng hoặc cột lớn. Cần xem:

- Số hàng và byte trả về.
- Kích thước mỗi hàng.
- Fetch size hoặc batch size của driver.
- Số round-trip trong quá trình fetch.
- Thời gian ánh xạ đối tượng, giải mã JSON hoặc chuyển kiểu.
- Ứng dụng có xử lý từng hàng chậm trong khi giữ connection không.

Giảm cột không cần thiết, lọc dữ liệu ở database, phân trang hoặc streaming có thể giảm dữ liệu truyền. Nhưng streaming giữ connection lâu hơn nếu ứng dụng tiêu thụ chậm; cần cân bằng bộ nhớ ứng dụng, thời gian giữ connection và throughput.

### Network latency không đồng nghĩa database chậm

Nếu database server-side elapsed thấp nhưng client elapsed cao, phần chênh lệch có thể đến từ network round-trip, proxy, fetch, driver, TLS hoặc ứng dụng. Đo latency từ nhiều điểm và đối chiếu cùng timestamp. Không suy ra network là nguyên nhân chỉ từ chênh lệch giữa hai timer nếu các timer có phạm vi khác nhau.

## Chẩn đoán các tình huống thường gặp

### Acquisition latency cao, SQL time thấp

Dấu hiệu:
- Connection acquisition p95/p99 tăng.
- Pending borrowers tăng.
- Active gần maximum, idle thấp.
- SQL server time của truy vấn vẫn ổn định.

Nguyên nhân có thể:
- Pool max quá nhỏ so với concurrency cần thiết.
- Transaction hoặc connection usage time dài.
- Connection leak.
- Database đã đạt giới hạn concurrency nên tăng pool không giúp.
- Một đợt tạo connection mới chậm do DNS/TLS/auth hoặc database listener.

Cách điều tra:
1. So sánh active, idle, pending và max theo thời gian.
2. Đo usage/hold time và tìm call site giữ connection lâu.
3. Kiểm tra transaction mở lâu, lock wait và thao tác ngoài database trong transaction.
4. Xem connection creation rate/time riêng với acquisition.
5. Kiểm tra database session count, CPU, I/O và wait events.
6. Chỉ điều chỉnh pool sau khi biết database còn khả năng xử lý thêm hay không.

### Acquisition thấp, SQL time cao

Dấu hiệu:
- Connection lấy nhanh, pending gần 0.
- SQL client elapsed và server elapsed tăng.
- Logical reads, CPU, lock wait hoặc I/O wait tăng.

Cách điều tra:
- Lấy actual execution plan.
- So sánh estimated rows và actual rows.
- Kiểm tra index scan/seek, join, sort, spill.
- Kiểm tra blocking, deadlock và wait events.
- Đo số hàng trả về và fetch time.
- Kiểm tra query plan regression và độ lệch tham số.

Tối ưu SQL, chỉ mục hoặc transaction dựa trên bằng chứng. Không tăng pool như biện pháp chữa SQL chậm.

### Physical connection creation chậm

Dấu hiệu:
- Acquisition latency tăng khi pool mở rộng hoặc sau restart.
- Connection creation time cao.
- Request đầu tiên chậm hơn request dùng connection đã có.

Kiểm tra:
- DNS resolution và thời gian phân giải nhiều địa chỉ.
- TCP connect và firewall/network route.
- TLS handshake, certificate validation và cipher negotiation.
- Authentication provider, token exchange hoặc LDAP/Kerberos nếu có.
- Database listener, proxy và giới hạn session.
- Pool lifetime/idle settings có làm connection bị tạo lại quá thường xuyên không.

Có thể dùng connection warm-up có kiểm soát nếu startup latency là vấn đề. Không mở đồng loạt quá nhiều connection lúc khởi động vì có thể tạo connection storm.

### SQL client time cao nhưng server time thấp

Khả năng:
- Network round-trip hoặc proxy chậm.
- Fetch nhiều hàng hoặc cột lớn.
- Driver buffering hoặc fetch size chưa phù hợp.
- Client xử lý từng hàng chậm.
- Có nhiều câu SQL tuần tự thay vì batch.
- Client thread bị CPU starvation hoặc scheduler delay.

Đo execute và fetch riêng, số hàng/byte, số round-trip, network latency và CPU ứng dụng. Nếu server time chỉ là thời gian xử lý statement, không cộng nó với client elapsed để kết luận phần chênh lệch chính xác khi hai metric chồng lấp.

### Pool timeout và retry storm

Khi acquisition timeout xảy ra, ứng dụng có thể retry ngay. Nếu nhiều request cùng retry, số request chờ và connection demand tăng thêm, làm pool càng bão hòa. Retry ở tầng ứng dụng phải có giới hạn, backoff và jitter, đồng thời phân biệt lỗi tạm thời với lỗi không thể phục hồi.

Không đặt acquisition timeout quá dài để che giấu pool exhaustion; request sẽ tích tụ và chiếm thread. Cũng không đặt quá ngắn nếu workload có burst bình thường và hệ thống có khả năng phục hồi. Timeout cần nằm trong ngân sách latency của request và được quan sát bằng histogram cùng timeout count.

## Chọn kích thước connection pool

### Pool nhỏ và pool lớn đều có đánh đổi

Pool quá nhỏ:
- Request phải chờ connection dù database còn khả năng xử lý thêm.
- Acquisition p95/p99 tăng.
- Throughput ứng dụng có thể bị giới hạn bởi pool.

Pool quá lớn:
- Nhiều session và transaction đồng thời hơn.
- Database tiêu tốn thêm bộ nhớ/session state.
- Lock contention, CPU scheduling và I/O queue có thể tăng.
- Các request tranh chấp tài nguyên làm latency dài hơn.
- Nhiều connection nhàn rỗi gây overhead không cần thiết.

Kích thước pool cần được đánh giá ở cấp toàn hệ thống. Nếu có 20 instance ứng dụng, mỗi instance có pool max 50, database có thể nhận tối đa khoảng 1.000 connection từ service đó, chưa kể worker, migration, admin và ứng dụng khác. Tính tổng connection demand theo mọi instance và mọi pool.

### Dùng Little's Law như công cụ ước lượng

Little's Law mô tả quan hệ giữa số công việc trung bình trong hệ thống, throughput và thời gian lưu lại:

~~~text
L = lambda * W
~~~

Trong đó:
- L là số request/transaction trung bình đang ở trong hệ thống.
- lambda là tốc độ hoàn tất trung bình (request/second).
- W là thời gian trung bình trong hệ thống (second).

Ví dụ, nếu database workload hoàn tất 200 transaction/giây và mỗi transaction giữ connection trung bình 0,05 giây, số connection đang được sử dụng trung bình theo mô hình là khoảng 10. Đây là ước lượng trung bình, không phải pool max khuyến nghị. Cần cộng biên cho burst, độ biến động và các workload khác, đồng thời kiểm tra database có xử lý được concurrency cao hơn hay không.

Không dùng Little's Law để chọn pool mà không đo usage time, throughput và hàng đợi. Nếu thời gian giữ connection tăng vì SQL chậm, tính toán có thể gợi ý pool lớn hơn nhưng làm database quá tải hơn.

### Đo concurrency tối ưu

Thử nghiệm tăng giới hạn pool theo từng mức trong môi trường có workload đại diện. Mỗi mức cần ghi:
- Throughput request và transaction.
- Acquisition p50/p95/p99.
- SQL client elapsed và server elapsed.
- Active/idle/pending/timeout.
- Database session count, CPU, memory và wait events.
- Lock wait, deadlock và I/O latency.
- Request p95/p99 và lỗi.

Điểm phù hợp thường là mức throughput đạt mục tiêu mà acquisition wait thấp, database chưa bão hòa và p95/p99 nằm trong SLO. Không có một pool size phổ quát cho mọi database hoặc ứng dụng.

## Timeout cần đặt theo đúng giai đoạn

### Acquisition timeout

Giới hạn thời gian chờ lấy connection từ pool. Khi hết thời gian, ứng dụng nên nhận lỗi rõ ràng và ghi nhận metric. Timeout này không nhất thiết giới hạn thời gian mở physical connection nếu thư viện có cấu hình riêng cho việc tạo kết nối.

### Connect timeout

Giới hạn thời gian thiết lập kết nối vật lý đến database hoặc endpoint. Có thể áp dụng cho TCP connect, TLS hoặc driver connection flow tùy thư viện. Đọc tài liệu driver vì tên và phạm vi khác nhau.

### Query/statement timeout

Giới hạn thời gian một câu SQL được phép thực thi hoặc chờ theo cơ chế của driver/database. Một số hệ quản trị có statement_timeout hoặc query governor; JDBC có setQueryTimeout với semantics phụ thuộc driver. Timeout không bảo đảm server đã dừng công việc ngay lập tức trong mọi trường hợp; cần kiểm tra cancellation và transaction state.

### Socket/read timeout

Giới hạn thời gian chờ dữ liệu mạng hoặc phản hồi từ server ở tầng socket/driver. Nếu quá thấp, một truy vấn hợp lệ nhưng trả kết quả lớn hoặc chạy lâu có thể bị ngắt. Nếu quá cao, request có thể giữ connection và thread lâu khi network bị treo.

### Request deadline

Tầng API nên có deadline tổng. Các timeout con cần phối hợp để request không vượt ngân sách. Ví dụ, nếu deadline còn 800 ms, không nên bắt đầu một query timeout 2 giây sau khi đã chờ pool 500 ms. Hãy truyền phần thời gian còn lại xuống các bước và để ứng dụng có thời gian xử lý lỗi/cleanup.

## Quy trình đo và chẩn đoán

1. **Định nghĩa latency end-to-end:** xác định điểm bắt đầu và kết thúc của request.
2. **Instrument từng giai đoạn:** pool acquisition, physical connection creation, execute, fetch, transaction commit và xử lý ứng dụng.
3. **Thu thập histogram:** p50/p95/p99, không chỉ average; ghi timeout và error rate.
4. **Thu thập pool gauges:** active, idle, pending, max, creation rate và usage duration.
5. **Ghép với database telemetry:** query fingerprint, server elapsed, CPU, logical reads, wait events, blocking và session count.
6. **Đo network:** DNS, connect, TLS, round-trip, bytes transfer và retransmission nếu có.
7. **Phân nhóm request:** theo endpoint, query fingerprint, tenant, kích thước kết quả và thời điểm.
8. **Xác định giai đoạn chi phối:** pool wait, connect, SQL, fetch, network hay ứng dụng.
9. **Đưa ra một giả thuyết và thay đổi có kiểm soát:** ví dụ sửa connection leak, rút ngắn transaction, tối ưu SQL hoặc điều chỉnh pool.
10. **Đo lại cùng workload:** giữ dữ liệu, concurrency, tham số và môi trường tương đương; kiểm tra cả latency và throughput.
11. **Kiểm tra tác động phụ:** số session, lock wait, memory, CPU, timeout, retry và lỗi.
12. **Theo dõi sau triển khai:** quan sát giờ cao điểm và các nhóm request khác nhau.

Khi dùng distributed tracing, tạo span riêng cho acquire connection, query execution và fetch nếu thư viện cho phép. Gắn trace ID hoặc request ID để nối log ứng dụng với database session/query. Không ghi password, token, connection string đầy đủ hoặc dữ liệu nhạy cảm trong span.

## Ví dụ tổng hợp: API tra cứu đơn hàng

Một API có p95 600 ms. Log ứng dụng chỉ ghi một trường database_duration = 580 ms. Nhóm ban đầu nghĩ SQL chậm. Sau khi tách metric, kết quả cho thấy:

| Thành phần | p95 minh họa |
|---|---:|
| Pool acquisition | 390 ms |
| Physical connection creation | 3 ms |
| Execute client elapsed | 85 ms |
| Fetch và ánh xạ | 90 ms |
| Xử lý ứng dụng khác | 35 ms |
| Tổng | 603 ms |

Database query stats cho thấy server elapsed khoảng 45 ms và logical reads ổn định. Pool metrics cho thấy active thường chạm max, pending tăng vào giờ cao điểm, usage time có đuôi dài. Trace cho thấy một số request giữ connection trong lúc gọi dịch vụ vận chuyển.

Nhóm xử lý:
1. Rút ngắn thời gian giữ connection và không giữ transaction trong lời gọi dịch vụ ngoài khi có thể thiết kế lại an toàn.
2. Kiểm tra mọi nhánh exception có trả connection về pool.
3. Đo lại active, pending, usage và acquisition.
4. Chỉ tăng pool nếu database còn năng lực và benchmark chứng minh lợi ích.
5. Tiếp tục tối ưu fetch vì kết quả trả về nhiều cột không cần thiết.

Sau điều chỉnh, acquisition p95 có thể giảm đáng kể mà SQL server time gần như không đổi. Đây là cải thiện đúng vì request đã chờ pool ít hơn, không phải vì execution plan thay đổi.

Các số liệu trong ví dụ chỉ minh họa cách phân rã. Trong hệ thống thực, các khoảng thời gian có thể chồng lấp; hãy dùng span và định nghĩa metric để tránh cộng trùng.

## Những sai lầm thường gặp

- **Gọi toàn bộ thời gian getConnection là TCP connect:** phần lớn lần lấy có thể chỉ mượn connection đã mở; thời gian còn lại có thể là queue wait.
- **Gộp pool wait vào SQL execution:** khiến nhóm tối ưu sai tầng.
- **Dùng server query duration làm end-to-end duration:** bỏ qua network, fetch và client processing.
- **Đo execute nhưng không đo fetch:** bỏ sót thời gian truyền kết quả lớn.
- **Tăng pool ngay khi acquisition chậm:** có thể làm database quá tải nếu SQL hoặc lock mới là nguyên nhân giữ connection.
- **Chỉ xem active connection tại một thời điểm:** bỏ qua pending, usage duration và xu hướng theo thời gian.
- **Quên đóng connection khi có exception:** gây leak và pool exhaustion.
- **Giữ connection khi gọi dịch vụ ngoài:** làm connection bị chiếm trong lúc không có SQL chạy.
- **Đặt timeout không phối hợp:** query hoặc connect timeout có thể dài hơn request deadline.
- **Retry ngay khi pool timeout:** tạo retry storm và tăng tải.
- **So sánh metric không cùng phạm vi:** client elapsed, server elapsed và wait time có thể chồng lấp.
- **Không tính tổng pool trên mọi instance:** tổng connection demand có thể vượt khả năng database.
- **Dùng average thay cho percentile:** tail latency có thể rất xấu dù trung bình thấp.
- **Không kiểm tra lượng dữ liệu trả về:** server query nhanh nhưng fetch và mapping vẫn chậm.

## Checklist phân biệt pool wait và SQL time

- [ ] Có timer riêng quanh lời gọi lấy connection không?
- [ ] Đã phân biệt acquisition wait với physical connection creation chưa?
- [ ] Có metric active, idle, pending, max và timeout của pool không?
- [ ] Có đo connection usage/hold time và phát hiện leak không?
- [ ] Đã đo execute và fetch riêng, hiểu semantics của driver chưa?
- [ ] Có query fingerprint và server-side execution statistics không?
- [ ] Đã đối chiếu logical reads, CPU, lock wait, I/O wait và actual plan chưa?
- [ ] Đã đo network round-trip, TLS/connect và bytes transfer khi cần chưa?
- [ ] Có request deadline và timeout riêng cho acquire/connect/query/socket không?
- [ ] Đã tính tổng pool size trên tất cả instance và service chưa?
- [ ] Đã kiểm tra transaction dài và lời gọi dịch vụ ngoài khi giữ connection chưa?
- [ ] Đã đo p50/p95/p99, throughput, timeout và retry rate chưa?
- [ ] Sau thay đổi, database session count và các workload khác có còn trong giới hạn không?

## Kết luận

Thời gian chờ lấy connection và thời gian chạy SQL là hai giai đoạn khác nhau. Acquisition có thể bao gồm chờ pool, kiểm tra connection hoặc tạo kết nối vật lý; SQL client elapsed có thể bao gồm round-trip, server processing và một phần fetch; database server time lại được đo theo phạm vi riêng của engine. Nếu không hiểu các điểm bắt đầu/kết thúc, nhóm có thể cộng trùng hoặc gán sai nguyên nhân.

Hãy instrument từng giai đoạn, theo dõi histogram cùng active/idle/pending/usage của pool, rồi ghép với query stats, execution plan, wait events và network telemetry. Khi acquisition wait cao, kiểm tra pool saturation, connection leak, transaction dài và database capacity. Khi SQL hoặc fetch chi phối, tối ưu truy vấn, dữ liệu trả về và đường truyền tương ứng. Điều chỉnh pool và timeout theo workload thực tế, sau đó xác nhận cả độ trễ, throughput và sức khỏe database dưới tải đại diện.
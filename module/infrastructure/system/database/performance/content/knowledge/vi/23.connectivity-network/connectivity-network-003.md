# Định cỡ nhóm kết nối theo khả năng xử lý của cơ sở dữ liệu

Nhóm kết nối (connection pool) giúp ứng dụng tái sử dụng các kết nối đến cơ sở dữ liệu thay vì mở và đóng kết nối vật lý cho từng request. Tuy nhiên, tăng kích thước pool không đồng nghĩa với tăng thông lượng. Nếu ứng dụng mở quá nhiều kết nối hoạt động cùng lúc, database có thể phải dành thêm bộ nhớ và worker cho session, chuyển ngữ cảnh thường xuyên, tranh chấp CPU, I/O và lock. Khi đó, nhiều request cùng chạy nhưng tổng số công việc hoàn tất mỗi giây có thể giảm.

Định cỡ pool phải dựa trên khả năng xử lý bền vững của database và số lượng request thực sự cần truy cập đồng thời. Cần phân biệt số kết nối đang mở với số truy vấn đang hoạt động, đo thời gian một request giữ connection, tìm điểm mà tăng concurrency không còn cải thiện throughput, rồi chia ngân sách kết nối cho mọi instance ứng dụng, job nền và công cụ vận hành.

Trong tối ưu hiệu năng cơ sở dữ liệu, một pool phù hợp giúp giữ số thao tác đồng thời trong vùng database xử lý hiệu quả, đồng thời đặt hàng đợi ở tầng ứng dụng với giới hạn và timeout rõ ràng. Bài học này trình bày cách tính tải bằng Little's Law, cách tìm concurrency tối ưu qua benchmark, cách tính tổng pool khi ứng dụng scale ngang, các loại pooling, khác biệt giữa DBMS và quy trình giám sát khi triển khai.

## 1. Connection, session, transaction và query active

Các khái niệm này liên quan nhưng không đồng nghĩa:

- **Connection:** kênh giao tiếp từ ứng dụng hoặc proxy đến database, thường tồn tại qua nhiều request khi được pool tái sử dụng.
- **Session:** ngữ cảnh phía database gắn với một client connection, có thể giữ trạng thái như biến session, role, transaction settings và tài nguyên liên quan.
- **Transaction:** đơn vị công việc bắt đầu và kết thúc bằng COMMIT hoặc ROLLBACK.
- **Active query:** câu lệnh đang được database thực thi hoặc đang chờ một tài nguyên để tiếp tục.
- **Idle connection:** connection đang mở nhưng tại thời điểm quan sát không thực thi câu lệnh.
- **Idle in transaction:** session không chạy câu lệnh nhưng transaction vẫn mở; trạng thái này có thể giữ lock hoặc snapshot và gây tác động đáng kể.

Một ứng dụng có thể giữ 100 connection trong pool nhưng chỉ có 8 connection đang chạy query; 92 connection còn lại đang idle và sẵn sàng phục vụ request tiếp theo. Ngược lại, 20 connection hoạt động cùng lúc có thể đủ làm database bão hòa nếu mỗi query cần nhiều CPU hoặc I/O.

Do đó, khi định cỡ pool, không chỉ hỏi database cho phép mở bao nhiêu connection. Cần hỏi database có thể xử lý bao nhiêu transaction hoặc query đồng thời mà vẫn đạt mục tiêu throughput và latency.

## 2. Vì sao mở quá nhiều connection có thể làm database chậm hơn?

Mỗi connection có thể tạo ra chi phí ở cả phía ứng dụng và database:

- Bộ nhớ cho session, trạng thái giao thức, buffer và cấu trúc nội bộ.
- Process hoặc thread phía server, tùy kiến trúc DBMS.
- Chi phí xác thực, thiết lập TLS, khởi tạo session và thiết lập biến session khi tạo mới.
- Context switching khi có nhiều worker runnable hơn năng lực CPU.
- Tranh chấp trên buffer pool, latch, lock, log và các cấu trúc chia sẻ.
- Nhiều query đồng thời làm tăng nhu cầu memory grant, sort/hash workspace và I/O queue.
- Tăng số transaction có thể cùng sửa một vùng dữ liệu, làm lock wait hoặc deadlock tăng.

Khi CPU hoặc storage đã bão hòa, thêm connection chỉ làm nhiều công việc chờ nhau. Elapsed time tăng, connection bị giữ lâu hơn, pool càng khó trả connection về trạng thái idle. Điều này tạo vòng lặp: request chậm giữ connection lâu, pool cạn, request mới xếp hàng, timeout tăng.

### 2.1. Connection ceiling không phải mục tiêu concurrency

Tham số như max_connections, user connection limit hoặc session limit thường là giới hạn bảo vệ và vận hành. Nó không phải lời khuyên rằng ứng dụng nên duy trì số connection hoạt động bằng đúng giới hạn đó.

Một database có thể cho phép hàng trăm hoặc hàng nghìn session nhưng chỉ đạt throughput tốt nhất khi một phần nhỏ trong số đó đang chạy truy vấn nặng. Số session nhàn rỗi có thể chấp nhận được nếu tài nguyên session thấp, nhưng chúng vẫn tiêu thụ bộ nhớ và làm tăng chi phí quản lý.

Không tăng giới hạn connection chỉ để xóa lỗi “too many connections”. Trước hết hãy xác định connection đang bị giữ bởi request dài, rò rỉ connection, transaction mở, pool quá lớn hay tải thực sự cần tăng.

## 3. Vì sao pool quá nhỏ cũng gây vấn đề?

Nếu pool chỉ có vài connection trong khi database còn khả năng xử lý thêm, request phải chờ connection được trả về. Hệ quả:

- Pool acquire wait tăng dù CPU và I/O database còn dư.
- Throughput ứng dụng thấp hơn khả năng database có thể phục vụ.
- Request timeout ở tầng ứng dụng trước khi query được gửi.
- Một transaction dài có thể chiếm phần lớn pool và chặn request ngắn.
- Tải tăng đột biến tạo hàng đợi dài ở pool.

Pool nhỏ có thể là lựa chọn tốt nếu database đã gần bão hòa. Nhưng nếu pool nhỏ hơn concurrency cần thiết trong vùng hoạt động hiệu quả, nó trở thành nút thắt ở tầng ứng dụng.

Phải phân biệt hai loại chờ:

1. **Chờ lấy connection:** request đang đợi pool cấp một connection.
2. **Chờ database xử lý:** connection đã được cấp nhưng query đang chờ CPU, I/O, lock hoặc worker.

Nếu chỉ tăng pool khi database đang bão hòa, ta có thể chuyển hàng đợi từ ứng dụng xuống database và làm tình hình xấu hơn. Nếu database còn dư năng lực nhưng pool quá nhỏ, tăng pool có kiểm soát có thể cải thiện throughput.

## 4. Định luật Little và ước lượng concurrency

Little's Law mô tả quan hệ giữa số công việc trung bình trong hệ thống, tốc độ công việc đi vào và thời gian trung bình một công việc ở trong hệ thống:

\[
L=\lambda\times W
\]

Trong đó:

- \(L\): số công việc trung bình đang tồn tại trong hệ thống.
- \(\lambda\): throughput, số công việc hoàn tất mỗi giây.
- \(W\): thời gian trung bình một công việc ở trong hệ thống, tính bằng giây.

Để ước lượng số connection đồng thời cần cho một workload, có thể dùng:

\[
C_{avg}\approx \lambda_{tx}\times T_{hold}
\]

Trong đó \(\lambda_{tx}\) là số transaction mỗi giây và \(T_{hold}\) là thời gian trung bình một transaction giữ connection từ lúc checkout khỏi pool đến lúc trả lại pool.

Ví dụ:

- Ứng dụng hoàn tất 240 transaction database mỗi giây.
- Mỗi transaction giữ connection trung bình 30 ms, tức 0,03 giây.

\[
C_{avg}\approx 240\times0,03=7,2
\]

Mức concurrency trung bình xấp xỉ 8 connection đang được giữ. Đây là ước lượng trung bình, không phải cấu hình pool cuối cùng. Cần xem phân phối thời gian, burst, p95/p99, số query trong một transaction và số request có thể đồng thời đến.

### 4.1. Dùng đúng thời gian giữ connection

Thời gian giữ connection không nhất thiết bằng thời gian SQL server thực thi query. Nếu ứng dụng checkout connection rồi gọi API bên ngoài, xử lý dữ liệu hoặc chờ người dùng trước khi commit/return, connection vẫn bị giữ trong khoảng đó.

Ví dụ:

~~~text
Checkout connection
  -> BEGIN
  -> SELECT
  -> gọi HTTP service mất 800 ms
  -> UPDATE
  -> COMMIT
Return connection
~~~

Trong ví dụ, thời gian gọi HTTP cũng kéo dài thời gian giữ connection dù database không thực hiện query trong phần lớn khoảng đó. Cách sửa thường là tránh giữ transaction/connection trong lúc chờ công việc ngoài database, nếu nghiệp vụ cho phép.

Để áp dụng Little's Law, hãy đo thời gian từ checkout đến check-in tại pool, đồng thời đo riêng thời gian query và thời gian chờ database. Không dùng thời gian response HTTP tổng thể nếu phần lớn thời gian nằm ngoài connection.

### 4.2. Một request có thể dùng nhiều transaction

Nếu mỗi request tạo nhiều transaction hoặc nhiều lần checkout connection, cần tính theo số lần sử dụng connection chứ không chỉ số request HTTP. Một request có thể thực hiện ba transaction tuần tự; một request khác có thể chạy nhiều query song song.

Hãy xác định đơn vị công việc phù hợp: transaction, connection checkout hoặc query execution. Công thức chỉ có ý nghĩa khi throughput và thời gian được đo cho cùng một đơn vị.

### 4.3. Không dùng giá trị trung bình làm giới hạn duy nhất

Concurrency trung bình 8 không có nghĩa pool size 8 luôn đủ. Tải đến theo burst và thời gian giữ connection có đuôi dài. Hãy xem histogram hoặc percentile của thời gian checkout, số connection active, pool wait và request arrival rate.

Có thể thử một số mức pool quanh concurrency quan sát được, nhưng cần tìm bằng benchmark điểm mà throughput bắt đầu bão hòa và latency tăng. Không nhân concurrency trung bình với một hệ số tùy ý rồi coi đó là công thức chính xác.

## 5. Tìm điểm bão hòa của database

Database thường có một vùng concurrency mà throughput tăng khi thêm công việc đồng thời. Sau một điểm, tài nguyên trở thành nút thắt và throughput tăng rất ít hoặc không tăng; latency và wait time tiếp tục tăng. Điểm chuyển này thường được gọi là saturation knee.

Một thử nghiệm khái quát:

| Active concurrency | Throughput | p95 latency | Diễn giải |
|---:|---:|---:|---|
| 2 | 120 tx/s | 18 ms | Còn dư năng lực |
| 4 | 220 tx/s | 20 ms | Throughput tăng rõ |
| 8 | 360 tx/s | 25 ms | Vẫn tăng hiệu quả |
| 16 | 390 tx/s | 55 ms | Bắt đầu bão hòa |
| 32 | 395 tx/s | 140 ms | Throughput gần như không tăng |
| 64 | 390 tx/s | 310 ms | Cạnh tranh làm latency xấu |

Các con số chỉ minh họa. Nếu workload thực tế có kết quả tương tự, mức concurrency quanh 8 đến 16 cần được kiểm tra kỹ hơn; không nên chọn 64 chỉ vì database cho phép 64 connection.

### 5.1. Throughput và latency phải được xem cùng nhau

Một cấu hình có throughput cao hơn một chút nhưng p99 tăng nhiều có thể không đáp ứng SLO. Hãy xem:

- Transaction/second hoặc query/second.
- p50, p95, p99 latency.
- CPU utilization và run queue.
- Logical/physical I/O và storage latency.
- Lock wait, latch wait và deadlock.
- Memory pressure, sort/hash spill.
- Connection pool wait và timeout.

### 5.2. Benchmark từng bước

Tăng concurrency theo các nấc, giữ nguyên truy vấn, dữ liệu, cache condition và tỷ lệ đọc/ghi. Mỗi nấc cần đủ thời gian để workload ổn định, không chỉ đo một burst ngắn. Dừng khi throughput không tăng tương xứng hoặc latency/wait vượt ngưỡng.

Nên benchmark với tải nền đại diện. Một database nhàn rỗi có thể chịu được concurrency lớn hơn nhiều so với giờ cao điểm khi có backup, replication, reporting và maintenance.

## 6. Tính ngân sách connection toàn hệ thống

Pool được cấu hình ở mỗi process hoặc instance ứng dụng, nhưng database nhìn thấy tổng kết nối từ mọi nguồn.

Một ngân sách tổng quát:

\[
C_{total}=C_{app}+C_{jobs}+C_{ops}+C_{other}
\]

Trong đó:

- \(C_{app}\): connection từ các service ứng dụng.
- \(C_{jobs}\): worker ETL, scheduler, consumer hoặc batch job.
- \(C_{ops}\): monitoring, migration, DBA và công cụ quản trị.
- \(C_{other}\): replication client, proxy, integration và workload khác tùy DBMS.

Tổng này phải nằm dưới giới hạn kết nối an toàn, đồng thời không vượt concurrency database có thể xử lý bền vững.

### 6.1. Tính theo số instance ứng dụng

Nếu một service có P instance và mỗi instance có pool tối đa S, số connection tối đa từ service đó là:

\[
C_{service}=P\times S
\]

Ví dụ:

- Ứng dụng có 4 replica.
- Mỗi replica có pool max 12.
- Một worker ETL có thể dùng tối đa 6 connection.
- Công cụ quản trị và monitoring cần dự trù 4 connection.

Tổng khả năng mở connection là:

\[
4\times12+6+4=58
\]

Khi autoscaling tăng từ 4 lên 10 replica mà không đổi pool size, riêng ứng dụng có thể mở đến 120 connection. Vì vậy, phải tính theo số instance tối đa hoặc đặt cơ chế điều chỉnh pool theo quy mô deployment.

### 6.2. Chừa ngân sách cho vận hành

Không phân bổ toàn bộ connection budget cho application pool. Cần dành chỗ cho:

- DBA và truy cập khẩn cấp.
- Monitoring, health check và migration.
- Background worker và scheduler.
- Replication hoặc integration client.
- Kết nối dự phòng khi một service khởi động lại hoặc failover.

Nếu DBMS có reserved connection hoặc administrative connection, cần hiểu cơ chế và không tính chúng như slot ứng dụng thông thường.

### 6.3. Chia ngân sách giữa nhiều service

Nếu nhiều service dùng chung database, mỗi service không thể tự quyết định pool max mà không xét các service còn lại. Hãy có một ngân sách tổng và phân bổ theo mức ưu tiên, throughput, độ trễ và số request thực tế.

Một service chạy báo cáo có thể cần ít connection hơn nhưng giữ chúng lâu hơn. Service OLTP có nhiều request ngắn có thể cần pool khác. Dùng cùng pool size cho mọi service thường không phản ánh khác biệt workload.

## 7. Ví dụ tính pool khi ứng dụng autoscale

Giả sử benchmark cho thấy database xử lý tốt nhất khoảng 32 transaction đang giữ connection đồng thời cho workload ứng dụng chính. Để chừa tài nguyên cho job nền và DBA, nhóm vận hành dành tối đa 24 slot cho service này.

Deployment có thể scale từ 3 đến 6 replica. Nếu chia đều ngân sách ở mức tối đa:

\[
S_{per-instance}=\left\lfloor\frac{24}{6}\right\rfloor=4
\]

Mỗi instance đặt pool max 4, tổng tối đa ở 6 replica là 24. Nếu chỉ cấu hình 8 mỗi instance dựa trên 3 replica hiện tại, khi scale lên 6 instance, tổng pool có thể tăng thành 48 và vượt ngân sách.

Một cách khác là dùng proxy hoặc pooler tập trung có giới hạn server connection tổng. Dù vậy, cần kiểm tra proxy có thực sự multiplex session hay chỉ chuyển tiếp kết nối, và các tính năng session của ứng dụng có tương thích với pooling mode hay không.

## 8. Cấu hình pool cần những giới hạn nào?

Một pool production thường cần nhiều tham số, không chỉ max size:

| Tham số | Ý nghĩa | Điều cần cân nhắc |
|---|---|---|
| Minimum/initial size | Số connection duy trì sẵn hoặc tạo ban đầu | Tránh cold start quá chậm nhưng không mở dư thừa |
| Maximum size | Số connection tối đa pool có thể cấp | Phải nằm trong ngân sách toàn hệ thống |
| Acquire/connection timeout | Thời gian request chờ lấy connection | Đặt theo latency budget của ứng dụng |
| Max queue/pending requests | Số request tối đa được chờ pool | Tránh hàng đợi không giới hạn và cạn bộ nhớ |
| Idle timeout | Thời gian connection nhàn rỗi trước khi đóng | Cân bằng chi phí mở lại với connection idle |
| Max lifetime | Tuổi thọ tối đa của connection | Giúp luân chuyển connection; tránh tất cả connection hết hạn cùng lúc |
| Validation/keepalive | Kiểm tra hoặc giữ connection sống | Không tạo probe quá dày hoặc round trip thừa |
| Leak detection | Phát hiện connection giữ quá lâu | Dùng để điều tra; ngưỡng phải phù hợp với transaction dài hợp lệ |

### 8.1. Acquire timeout

Nếu pool đã đầy, request chờ đến khi có connection được trả lại hoặc hết timeout. Timeout quá dài làm request tích tụ và kéo dài thời gian phản hồi; timeout quá ngắn có thể tạo lỗi trong burst ngắn dù database vẫn có thể xử lý.

Đặt acquire timeout theo SLO của request và thời gian còn lại dành cho query cùng xử lý ứng dụng. Không đặt timeout vô hạn.

### 8.2. Giới hạn hàng đợi

Hàng đợi không giới hạn có thể biến một đợt quá tải ngắn thành backlog lớn, tiêu thụ bộ nhớ và khiến request hết hạn trước khi được xử lý. Hãy đặt giới hạn pending request hoặc dùng admission control để từ chối sớm khi hệ thống đã quá tải.

### 8.3. Idle timeout và max lifetime

Idle timeout giúp thu hồi connection dư khi tải giảm. Max lifetime giúp luân chuyển connection để tránh giữ session quá lâu hoặc vượt giới hạn hạ tầng. Nếu mọi connection được tạo cùng thời điểm và hết hạn cùng lúc, pool có thể tạo connection storm. Nên dùng jitter hoặc cơ chế lifetime phân tán nếu pool hỗ trợ.

## 9. Giữ thời gian checkout ngắn

Pool size có thể bị lãng phí nếu ứng dụng giữ connection lâu hơn thời gian cần thiết.

Ví dụ không tốt:

~~~text
checkout connection
BEGIN
SELECT account
gọi dịch vụ thanh toán bên ngoài
chờ người dùng xác nhận
UPDATE account
COMMIT
return connection
~~~

Connection và transaction bị giữ trong lúc gọi dịch vụ hoặc chờ người dùng. Điều này có thể làm pool cạn và giữ lock/snapshot lâu.

Thiết kế tốt hơn, nếu nghiệp vụ cho phép:

~~~text
đọc dữ liệu cần thiết
return connection
gọi dịch vụ bên ngoài
checkout connection
kiểm tra version/trạng thái hiện tại
UPDATE theo điều kiện
COMMIT
return connection
~~~

Cách này cần dùng optimistic concurrency, idempotency hoặc quy tắc nghiệp vụ phù hợp để xử lý dữ liệu thay đổi giữa hai lần truy cập. Không được tách transaction nếu tính nguyên tử của nghiệp vụ yêu cầu tất cả thao tác nằm trong cùng một transaction.

Các nguyên nhân khác làm connection bị giữ lâu:

- Connection leak do không đóng/return trong nhánh lỗi.
- Streaming result chưa được đọc hết hoặc đóng.
- Transaction mở mà quên commit/rollback.
- Query timeout không hủy statement hoặc không trả connection về pool đúng cách.
- Application giữ connection trong khi xử lý serialization hoặc gọi API.
- Một query chậm do lock/I/O khiến checkout duration tăng.

Hãy dùng try/finally, context manager hoặc transaction scope của thư viện để bảo đảm connection được trả lại khi có exception.

## 10. Session pooling, transaction pooling và statement pooling

Không phải mọi pool đều hoạt động ở cùng tầng.

### 10.1. Session pooling

Pooler gán một server connection cho client trong suốt session. Trạng thái session thường được giữ giữa các transaction. Cách này tương thích với nhiều ứng dụng nhưng mức multiplexing thấp hơn vì một client đang idle vẫn có thể giữ server connection.

### 10.2. Transaction pooling

Pooler chỉ gán server connection trong thời gian một transaction. Sau COMMIT/ROLLBACK, server connection có thể được dùng cho client khác. Cách này cho phép nhiều client connection chia sẻ một số lượng server connection nhỏ hơn.

Tuy nhiên, ứng dụng không được giả định trạng thái session tồn tại qua các transaction. Các tính năng cần kiểm tra gồm:

- SET session variable hoặc thay đổi session state.
- Temporary table sống qua transaction.
- Session-level advisory lock.
- LISTEN/NOTIFY hoặc subscription gắn với session.
- Cursor giữ qua transaction.
- Prepared statement phía server và cách pooler quản lý chúng.
- Role, search path, timezone hoặc cấu hình session.

Khả năng hỗ trợ từng tính năng phụ thuộc pooler, phiên bản và cấu hình. Với PostgreSQL/PgBouncer, transaction pooling có một số giới hạn session semantics; một số tính năng prepared statement được hỗ trợ ở các phiên bản/cấu hình mới hơn, vì vậy phải kiểm tra đúng phiên bản.

### 10.3. Statement pooling

Statement pooling trả server connection sau từng statement và thường không cho phép transaction nhiều câu lệnh theo cách thông thường. Đây là chế độ hạn chế nhất, chỉ phù hợp với ứng dụng và giao thức được thiết kế cho nó.

### 10.4. Chọn đúng pooling mode

Nếu ứng dụng dựa vào session state, session pooling có thể cần thiết. Nếu workload gồm transaction ngắn, độc lập và không phụ thuộc session state, transaction pooling có thể tăng khả năng multiplex. Đừng chuyển pooling mode mà không chạy kiểm thử tích hợp cho temporary table, prepared statement, transaction, advisory lock và các tính năng session đang dùng.

## 11. Khác biệt giữa các hệ quản trị

### 11.1. PostgreSQL

PostgreSQL thường tạo một backend process cho mỗi client connection thông thường. Nhiều session vì vậy có thể tiêu thụ bộ nhớ và tài nguyên process đáng kể. Với ứng dụng có nhiều client ngắn, PgBouncer hoặc một pooler tương thích có thể giảm số backend server connection cần duy trì.

Các điểm cần theo dõi:

- max_connections và reserved connection slots theo phiên bản.
- Số backend active, idle và idle in transaction.
- wait events, query duration và transaction age.
- PgBouncer client/server connections, pool wait và queue.
- Replication, autovacuum và background workers.

Tăng max_connections có thể làm tăng tài nguyên nền cần thiết. Hãy benchmark số backend active thay vì đặt max_connections theo số client ứng dụng.

### 11.2. MySQL

MySQL quản lý client sessions và thread theo cấu hình/version. Mỗi connection có trạng thái và tài nguyên liên quan; thread pool plugin ở các bản phân phối/edition hỗ trợ có thể điều phối một số lượng thread phục vụ nhỏ hơn số connection. Thread pool không có nghĩa mọi session được multiplex theo ngữ nghĩa transaction như PgBouncer transaction pooling.

Theo dõi:

- max_connections và Threads_connected.
- Threads_running và connection errors.
- Thread pool queue/active threads nếu sử dụng.
- Connection creation rate và aborted connections.
- Lock waits, InnoDB I/O và replication applier.

Nếu Threads_connected cao nhưng Threads_running thấp, nhiều session đang mở nhưng không hoạt động. Nếu Threads_running cao cùng CPU/run queue và latency tăng, có thể database đang chịu quá nhiều concurrency.

### 11.3. SQL Server

SQL Server dùng worker thread và scheduler để thực thi request. Connection pooling thường nằm ở client provider như ADO.NET; pool tái sử dụng connection vật lý và có max pool size riêng. Số session không đồng nghĩa số request đang chạy.

Theo dõi:

- User connections và request đang active.
- Worker thread availability.
- Scheduler runnable queue.
- Wait statistics, blocking và deadlocks.
- Connection pool active/free/waiting ở application provider.
- Resource Governor nếu cần giới hạn workload.

Không tăng max worker threads hoặc max pool size chỉ vì ứng dụng gặp timeout. Hãy xác định timeout ở tầng lấy connection, worker queue hay database execution.

### 11.4. Oracle Database

Oracle phân biệt session và process, đồng thời có các mô hình kết nối và chia sẻ server khác nhau. Database Resident Connection Pooling (DRCP) có thể chia sẻ server process/session resources giữa nhiều client trong môi trường phù hợp. Shared server và DRCP có điều kiện sử dụng và trade-off riêng.

Theo dõi:

- Sessions/processes và giới hạn cấu hình.
- Active sessions, wait events và resource manager consumer group.
- Connection pool phía client hoặc DRCP pool statistics.
- PGA/UGA và tài nguyên theo session.
- Listener và connection establishment rate.

Không đồng nhất số session với số dedicated server process trong mọi cấu hình Oracle.

## 12. Connection storm khi khởi động hoặc scale ngang

Một service có 20 replica, mỗi replica khởi động cùng lúc và tạo 30 connection sẽ có thể tạo 600 lần handshake gần như đồng thời. Điều này gây:

- CPU tăng do authentication và TLS.
- Connection queue ở listener/proxy.
- Bộ nhớ session tăng đột ngột.
- Database chạm connection limit.
- Health check thất bại, khiến orchestrator khởi động lại container và tạo storm lớn hơn.

Các biện pháp giảm:

- Tạo connection lazy hoặc warm-up có giới hạn.
- Dùng startup jitter và connection creation rate limit.
- Giới hạn max pool theo số replica tối đa.
- Dùng proxy/pooler tập trung khi phù hợp.
- Đặt readiness check dựa trên khả năng phục vụ thực tế, tránh restart loop.
- Dùng exponential backoff với jitter khi kết nối thất bại.
- Không để mọi replica cùng reconnect theo chu kỳ cố định.

Khi database failover hoặc khởi động lại, pool phải loại bỏ connection lỗi và tái tạo có kiểm soát. Nếu mọi client reconnect đồng thời, database vừa phục hồi có thể bị quá tải ngay lập tức.

## 13. Autoscaling và ngân sách pool động

Autoscaling làm số process ứng dụng thay đổi. Nếu pool max là cố định theo instance, tổng connection tiềm năng thay đổi theo số replica.

Ví dụ:

| Số replica | Pool max mỗi replica | Tổng connection tối đa |
|---:|---:|---:|
| 2 | 10 | 20 |
| 4 | 10 | 40 |
| 8 | 10 | 80 |
| 12 | 10 | 120 |

Nếu database chỉ có ngân sách 48 connection cho service, cấu hình 10 mỗi replica sẽ vượt ngân sách khi scale lên 8 replica.

Các lựa chọn:

- Chia pool max theo số replica tối đa đã dự kiến.
- Dùng một pooler/proxy có giới hạn server connection tổng.
- Dùng connection budget trung tâm hoặc admission control.
- Giảm pool mỗi instance khi autoscaling tăng.
- Tách workload đọc/ghi hoặc chuyển một phần truy vấn sang replica khi kiến trúc cho phép.

Không nên dựa vào số replica hiện tại. Hãy tính theo max replicas, rolling deployment (old và new replica có thể cùng tồn tại), worker process, canary và các service dùng chung database.

## 14. Pool metrics cần giám sát

### 14.1. Phía ứng dụng/pool

- Total/open connections.
- Active/in-use connections.
- Idle connections.
- Pending/acquire queue length.
- Acquire wait time: p50, p95, p99.
- Acquire timeout count.
- Connection creation/destruction rate.
- Connection lifetime và idle duration.
- Checkout duration và leak detection.
- Số transaction giữ connection lâu.

### 14.2. Phía database

- Total sessions/connections.
- Active sessions và idle sessions.
- Active query count.
- CPU utilization, run queue và worker availability.
- I/O latency, IOPS, throughput và queue depth.
- Lock/latch waits, deadlocks và blocking.
- Memory pressure, temp spill và cache hit.
- Log flush latency, replication lag và background tasks.

### 14.3. Ghép metric hai phía

Một dashboard hữu ích nên đặt pool active, pending và acquire wait cạnh DB active sessions, CPU, I/O và lock waits.

Ví dụ diễn giải:

- Pool pending cao, DB active thấp, CPU thấp: có thể pool quá nhỏ, connection bị giữ trong ứng dụng hoặc một số connection bị leak.
- Pool active cao, DB active cao, CPU/run queue cao: có thể database đã bão hòa; tăng pool có nguy cơ làm xấu latency.
- Pool active cao, DB active thấp nhưng transaction age dài: xem connection đang bị giữ trong ứng dụng hoặc session idle in transaction.
- Pool active thấp, DB CPU cao: có thể một vài truy vấn nặng đang tiêu thụ CPU hoặc workload khác ngoài service đang chạy.
- DB sessions cao nhưng active query thấp: nhiều connection idle; kiểm tra pool tổng, autoscaling và giới hạn session.

## 15. Ví dụ truy vấn quan sát session

Tên view và quyền truy cập tùy DBMS. Các câu sau chỉ là điểm bắt đầu để điều tra.

### PostgreSQL

~~~sql
SELECT state, wait_event_type, wait_event, COUNT(*) AS sessions
FROM pg_stat_activity
GROUP BY state, wait_event_type, wait_event
ORDER BY sessions DESC;
~~~

Để tìm transaction mở lâu:

~~~sql
SELECT pid, usename, application_name, state,
       now() - xact_start AS transaction_age,
       wait_event_type, wait_event
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

### MySQL

~~~sql
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Threads_running';
SHOW GLOBAL STATUS LIKE 'Connections';
~~~

Có thể xem session bằng Performance Schema hoặc process list tùy phiên bản và quyền.

### SQL Server

~~~sql
SELECT
    s.session_id,
    s.status AS session_status,
    r.status AS request_status,
    r.cpu_time,
    r.total_elapsed_time,
    r.wait_type,
    r.wait_time
FROM sys.dm_exec_sessions AS s
LEFT JOIN sys.dm_exec_requests AS r
    ON r.session_id = s.session_id
WHERE s.is_user_process = 1;
~~~

Các DMV có thể yêu cầu quyền xem trạng thái server. Kết quả cần được lọc theo workload và thời điểm; không kết luận từ một snapshot đơn lẻ.

## 16. Chẩn đoán pool cạn và database quá tải

| Triệu chứng | Khả năng | Hướng kiểm tra |
|---|---|---|
| Pool pending cao, DB CPU thấp | Pool quá nhỏ hoặc connection bị giữ lâu | Checkout duration, leak, transaction age, số pool/instance |
| Pool pending cao, DB CPU và run queue cao | Database bão hòa | Giảm concurrency, tối ưu query, benchmark saturation knee |
| DB sessions cao, active query thấp | Pool mở dư hoặc idle session tích tụ | Tổng pool qua replica, idle timeout, autoscaling |
| Connection timeout khi deploy | Connection storm hoặc max connection budget thiếu | Startup rate, rolling deployment, retry/backoff, max replicas |
| p99 tăng khi tăng pool max | Oversubscription, lock/I/O contention | Active query, waits, CPU, I/O queue và DOP |
| Một vài request giữ connection rất lâu | Transaction dài, streaming hoặc gọi dịch vụ ngoài | Trace checkout/checkin, transaction boundary |
| DB active thấp nhưng pool vẫn full | Connection leak hoặc app giữ connection ngoài query | Leak detection, stack trace checkout, idle in transaction |
| Replica đọc dữ liệu trễ | Apply lag hoặc pool/route đến replica không phù hợp | Replication queue, active sessions và read routing |
| Lỗi connection sau idle period | Firewall/NAT/proxy timeout hoặc server reset | Keepalive, validation, max lifetime và connection error |

Để phân biệt nguyên nhân, cần đồng bộ timestamp giữa application metrics, pool metrics và database metrics. Nếu chỉ xem tổng số connection ở một phía, khó xác định nơi request đang chờ.

## 17. Quy trình benchmark và chọn pool size

1. **Lập sơ đồ kết nối.** Liệt kê service, replica tối đa, pool mỗi instance, worker job, proxy, monitoring và DBA access.
2. **Đo workload.** Thu thập transaction rate, query rate, thời gian giữ connection, query service time và phân phối burst.
3. **Xác định giới hạn tài nguyên.** Đo CPU, memory, I/O, lock, worker và connection budget của DBMS.
4. **Tìm saturation knee.** Tăng active concurrency theo từng nấc và ghi throughput, p95/p99, CPU, I/O và wait.
5. **Chọn concurrency mục tiêu.** Chọn vùng có throughput tốt và latency chấp nhận được, có headroom cho tải nền.
6. **Tính pool toàn hệ thống.** Phân bổ budget cho mọi service theo max replicas, rolling deploy và job nền.
7. **Đặt queue và timeout.** Giới hạn pending request, acquire timeout, query timeout và transaction timeout theo SLO.
8. **Kiểm tra transaction lifetime.** Bảo đảm connection chỉ được giữ khi cần truy cập database; phát hiện leak và idle-in-transaction.
9. **Thử scale và failover.** Kiểm tra connection storm, reconnect, proxy failover và autoscaling.
10. **Theo dõi sau triển khai.** So sánh pool wait, active sessions, throughput, p95/p99, DB resource và lỗi timeout với baseline.

Khi benchmark, thay đổi một yếu tố mỗi lần. Không tăng đồng thời pool size, worker count, DOP và batch size rồi quy kết quả cho một thay đổi cụ thể.

## 18. Ví dụ lựa chọn cấu hình theo số đo

Giả sử benchmark workload OLTP cho thấy:

- Database đạt throughput gần cực đại ở khoảng 28 đến 36 transaction active.
- Trên 40 active transaction, throughput gần như không tăng nhưng p99 latency tăng nhanh.
- Job báo cáo và monitoring cần tối đa 8 connection riêng.
- Nhóm vận hành muốn giữ 4 connection dự phòng.
- Ứng dụng có thể scale tối đa 6 replica.

Ngân sách dành cho service OLTP có thể đặt ở mức 28 connection đồng thời để bắt đầu thử nghiệm, sau đó đo lại khi chạy chung với workload nền. Chia đều cho 6 replica:

\[
PoolMax_{instance}=\left\lfloor\frac{28}{6}\right\rfloor=4
\]

Tổng tối đa là 24 connection, thấp hơn ngân sách 28 một chút để giữ headroom. Phần còn lại có thể được phân bổ có chủ đích hoặc để trống; không cần lấp đầy mọi slot.

Nếu mỗi transaction giữ connection trung bình 25 ms và workload đạt 240 transaction/s:

\[
C_{avg}\approx240\times0,025=6
\]

Concurrency trung bình chỉ khoảng 6, nhưng burst có thể cao hơn. Pool max 24 là giới hạn cho phép burst và phân tán qua replica, không phải yêu cầu duy trì 24 connection active liên tục. Cần xem acquire wait và DB active concurrency trong peak để xác nhận.

Nếu service scale lên 10 replica, pool max 4 mỗi instance có thể tạo 40 connection. Khi đó phải giảm pool mỗi instance, giới hạn tổng qua proxy hoặc thay đổi budget có kiểm chứng. Không được để autoscaling tự nhân tổng connection vượt giới hạn database.

## 19. Những sai lầm thường gặp

- **Đặt pool max bằng max_connections của database.** Còn nhiều workload và connection vận hành khác cần dùng database.
- **Cho rằng nhiều connection luôn tăng throughput.** Database có thể bão hòa CPU, I/O, lock hoặc worker.
- **Dùng số CPU làm công thức duy nhất.** Query có mức CPU, I/O và lock khác nhau; DOP cũng làm thay đổi concurrency.
- **Chỉ tính pool trên một instance.** Tổng kết nối tăng theo replica, worker và rolling deployment.
- **Đồng nhất connection với query active.** Nhiều connection có thể idle; một query có thể dùng nhiều worker.
- **Chỉ đo số hàng hoặc request/second.** Cần đo thời gian giữ connection, log, CPU, I/O và latency.
- **Tăng pool để xử lý pool timeout mà không xem DB.** Có thể chuyển hàng đợi xuống database và làm p99 xấu hơn.
- **Để queue không giới hạn.** Backlog làm request chờ quá lâu và tiêu thụ tài nguyên ứng dụng.
- **Giữ connection khi gọi API ngoài.** Thời gian checkout tăng mà database không làm việc.
- **Không xử lý connection leak.** Pool max lớn chỉ che giấu vấn đề và làm database nhận thêm session.
- **Chuyển transaction pooling mà không kiểm tra session state.** Temporary table, advisory lock, prepared statement hoặc session variable có thể không hoạt động như kỳ vọng.
- **Reconnect đồng loạt sau failover.** Connection storm có thể làm database vừa phục hồi lại quá tải.
- **Chỉ theo dõi DB connections.** Cần theo dõi active sessions, pool pending, acquire wait, CPU, I/O và lock waits cùng nhau.

## 20. Checklist định cỡ connection pool

- [ ] Đã phân biệt connection, session, transaction và active query.
- [ ] Đã đo thời gian giữ connection từ checkout đến check-in.
- [ ] Đã dùng Little's Law với throughput và thời gian cùng đơn vị.
- [ ] Đã đo burst, p95/p99 và concurrency peak, không chỉ giá trị trung bình.
- [ ] Đã benchmark để tìm saturation knee của database.
- [ ] Đã kiểm tra CPU, I/O, memory, lock, worker và query plan ở từng mức concurrency.
- [ ] Đã tính tổng pool qua tất cả service, replica, job và công cụ vận hành.
- [ ] Đã tính số replica tối đa, rolling deployment và connection storm.
- [ ] Đã đặt max size, acquire timeout, queue limit, idle timeout và max lifetime.
- [ ] Đã bảo đảm transaction ngắn và connection được trả về trong mọi nhánh lỗi.
- [ ] Đã kiểm tra idle-in-transaction và connection leak.
- [ ] Đã chọn session/transaction/statement pooling phù hợp với session semantics.
- [ ] Đã xác minh giới hạn và cơ chế pooling của DBMS đang dùng.
- [ ] Đã theo dõi pool active/idle/pending, acquire wait và timeout.
- [ ] Đã theo dõi database active sessions, CPU, I/O, lock, worker và replication.
- [ ] Đã thử autoscaling, failover, reconnect và retry có backoff.
- [ ] Đã xác nhận throughput và p95/p99 của toàn workload đạt SLO sau triển khai.

Định cỡ connection pool là bài toán phân bổ concurrency theo năng lực database, không phải bài toán mở càng nhiều connection càng tốt. Little's Law giúp ước lượng concurrency trung bình từ throughput và thời gian giữ connection; benchmark giúp tìm điểm database bắt đầu bão hòa; ngân sách toàn hệ thống bảo đảm tổng pool không tăng vượt mức khi có nhiều service và replica. Khi kết hợp queue có giới hạn, timeout phù hợp, transaction ngắn và giám sát cả hai phía ứng dụng/database, hệ thống có thể hấp thụ burst mà vẫn giữ throughput và độ trễ ổn định.

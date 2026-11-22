# Tăng số kết nối có thể làm tăng chờ và giảm thông lượng như thế nào

## Nhiều kết nối hơn không đồng nghĩa với xử lý nhanh hơn

Connection pool thường được tăng kích thước khi ứng dụng gặp lỗi chờ lấy connection. Cách suy nghĩ dễ gặp là: nếu 10 connection đang bận và request thứ 11 phải chờ, tăng pool lên 20 sẽ giúp request chạy ngay. Điều này chỉ đúng khi database còn đủ tài nguyên để xử lý thêm công việc song song.

Database có năng lực hữu hạn. CPU, bộ nhớ, buffer pool, I/O, index, khóa và các điểm ghi dùng chung đều giới hạn số công việc có thể tiến triển hiệu quả tại cùng một thời điểm. Khi số session hoạt động vượt ngưỡng phù hợp, mỗi session phải tranh giành cùng tài nguyên. Thời gian chờ tăng lên, chi phí quản lý tăng và thông lượng có thể đứng yên hoặc giảm.

Một connection bổ sung có thể giúp khi database đang nhàn rỗi và pool quá nhỏ. Nhưng nếu database đã bão hòa, connection bổ sung chủ yếu đưa thêm công việc vào hàng chờ bên trong database. Hàng chờ chỉ chuyển từ connection pool sang lock manager, scheduler, I/O hoặc CPU.

**Connection pool vừa là nơi tái sử dụng kết nối, vừa là giới hạn admission control:** nó kiểm soát bao nhiêu công việc được phép đồng thời chiếm connection database. Tăng giới hạn này cần dựa trên phép đo năng lực thực tế, không dựa riêng vào số request đang chờ.

## Phân biệt ba loại số lượng

Khi phân tích kết nối, cần tách ba khái niệm:

- **Số request đến ứng dụng:** số yêu cầu HTTP, message hoặc job mà ứng dụng đang nhận.
- **Số connection đang được ứng dụng mượn:** số connection pool đã cấp cho code để thực hiện công việc. Một connection có thể đang chạy SQL, đang chờ lock hoặc bị giữ trong khi ứng dụng xử lý.
- **Số session database đang hoạt động:** số session đang thực thi, chờ khóa, chờ I/O hoặc tiêu thụ tài nguyên ở database. Connection idle trong pool thường vẫn là session tồn tại nhưng không nhất thiết đang chạy SQL.

Ba số này không bằng nhau. Một request có thể gọi nhiều câu SQL tuần tự trên cùng connection. Một request có thể không cần database. Một request khác có thể giữ connection trong khi chờ HTTP bên ngoài. Connection pool cũng có thể có nhiều connection idle không được request mượn.

Khi dashboard chỉ hiển thị `max_connections`, bạn chưa biết database có đang xử lý quá nhiều SQL hay không. Khi dashboard chỉ hiển thị số request HTTP, bạn cũng chưa biết bao nhiêu request đang chờ pool hoặc chờ row lock.

## Hiệu ứng hàng chờ khi tải tiến gần năng lực phục vụ

Giả sử database có thể hoàn tất trung bình μ giao dịch mỗi giây trên một tài nguyên xử lý đang xét, còn ứng dụng gửi tới λ giao dịch mỗi giây. Với mô hình hàng chờ đơn giản, thời gian trong hệ thống tăng rất nhanh khi tốc độ đến tiến gần tốc độ phục vụ.

Trong mô hình M/M/1 minh họa:

\[
\rho = \frac{\lambda}{\mu}, \qquad
W = \frac{1}{\mu-\lambda}
\]

Trong đó:

- \(\lambda\) là tốc độ công việc đến (request/giây).
- \(\mu\) là tốc độ phục vụ tối đa của tài nguyên trong mô hình (request/giây).
- \(\rho\) là mức sử dụng tài nguyên.
- \(W\) là thời gian trung bình trong hệ thống theo mô hình này.

Đây không phải công thức dự báo chính xác cho một database nhiều CPU, nhiều I/O queue và nhiều loại truy vấn. Nó minh họa một hiện tượng quan trọng: khi mức sử dụng tiến sát 100%, chỉ một biến động nhỏ của tải hoặc thời gian xử lý cũng có thể làm hàng chờ tăng mạnh.

Ví dụ với một tài nguyên giả định có thể phục vụ 100 giao dịch/giây:

| Tốc độ đến | Mức sử dụng | Thời gian trung bình theo mô hình M/M/1 |
| ---: | ---: | ---: |
| 50 giao dịch/giây | 50% | 20 ms |
| 80 giao dịch/giây | 80% | 50 ms |
| 90 giao dịch/giây | 90% | 100 ms |
| 95 giao dịch/giây | 95% | 200 ms |
| 99 giao dịch/giây | 99% | 1.000 ms |

Khi tải tăng từ 90 lên 99 giao dịch/giây, tốc độ đến chỉ tăng 10%, nhưng thời gian trung bình theo mô hình tăng từ 100 ms lên 1 giây. Khi độ trễ tăng, request giữ connection lâu hơn; pool có thể đầy và request mới phải chờ thêm ở tầng ứng dụng.

### Little's Law và số công việc đang tồn tại

Little's Law mô tả mối quan hệ giữa số công việc trung bình trong hệ thống, tốc độ hoàn tất và thời gian trung bình:

\[
L = \lambda W
\]

Ví dụ, nếu hệ thống hoàn tất 200 giao dịch/giây và mỗi giao dịch mất trung bình 100 ms trong khu vực đang xét, số giao dịch trung bình đang ở trong khu vực đó là:

\[
L = 200 \times 0.1 = 20
\]

Nếu độ trễ tăng lên 300 ms trong khi thông lượng vẫn là 200 giao dịch/giây, số giao dịch trung bình đang tồn tại tăng lên 60. Điều đó không có nghĩa cần tạo thêm 40 connection. Các giao dịch bổ sung có thể đang chờ lock hoặc I/O; tăng connection chỉ làm số công việc cạnh tranh lớn hơn.

Little's Law giúp ước lượng concurrency quan sát được từ throughput và latency. Nó không tự đưa ra kích thước pool tối ưu, vì pool còn phải xét thời gian connection được mượn, tỷ lệ truy cập database, transaction duration và năng lực từng loại tài nguyên.

## Khi tăng pool, hàng chờ có thể chuyển vào database

Giả sử pool có 10 connection. Mười request đầu tiên mượn đủ connection; request thứ 11 chờ ở pool. Nếu tăng pool lên 30, request thứ 11 có thể được cấp connection ngay. Nhưng database giờ nhận nhiều công việc đồng thời hơn.

Nếu database còn CPU và I/O nhàn rỗi, throughput có thể tăng. Nếu database đã gần bão hòa, các session bổ sung làm tăng:

- số truy vấn cùng tranh CPU;
- số transaction cùng giữ và chờ khóa;
- lượng dữ liệu và page phải giữ trong bộ nhớ;
- số thao tác đọc/ghi chờ storage;
- chi phí lập lịch và chuyển đổi context;
- lượng công việc phải xử lý sau khi một hotspot được giải phóng.

Kết quả là thời gian SQL và thời gian giữ connection tăng. Pool mới có thể giảm `connection acquisition wait` nhưng làm tăng `database execution time` hoặc `lock wait time`. Nếu chỉ nhìn một chỉ số pool, ta có thể tưởng hệ thống đã tốt hơn trong khi độ trễ end-to-end và thông lượng xấu đi.

### Minh họa hai vị trí hàng chờ

```text
Request
   |
   v
+----------------------+
| Connection pool      |
|                      |
|  10 connections      |
|  pending requests    |
+----------------------+
   |
   | pool nhỏ: chờ tại đây
   | pool lớn: nhiều request được chuyển tiếp
   v
+----------------------+
| Database             |
|                      |
| CPU / scheduler      |
| row locks            |
| buffer / I/O         |
| internal queues      |
+----------------------+
   |
   v
Commit / response
```

Tăng pool có thể làm hàng chờ ở pool ngắn lại trong khi hàng chờ bên trong database dài hơn. Mục tiêu không phải xóa mọi hàng chờ ở pool; một pool có giới hạn hữu ích có thể bảo vệ database khỏi bị quá tải.

## Lock contention: nhiều connection cùng tranh một dữ liệu

Database có thể xử lý nhiều transaction song song khi chúng thao tác trên dữ liệu độc lập. Nhưng nếu hàng trăm connection cùng cập nhật một dòng, một index entry hoặc một tập dữ liệu nóng, chúng phải tuần tự hóa ở điểm tranh chấp.

Ví dụ:

```sql
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 42;
```

Nếu nhiều request cùng mua sản phẩm `42`, InnoDB hoặc PostgreSQL phải điều phối các khóa ghi trên dòng tương ứng. Transaction thứ hai có thể chờ transaction thứ nhất commit. Thêm connection không giúp hai transaction cùng sửa một dòng đồng thời; nó chỉ cho phép nhiều transaction xếp hàng chờ khóa đó.

### Vì sao độ trễ tăng mạnh ở hotspot?

Giả sử một dòng bị khóa trung bình 20 ms cho mỗi giao dịch. Nếu nhiều transaction cùng cần dòng đó, phần thao tác ghi trên dòng này có tính tuần tự. Dù database có nhiều core, các transaction vẫn phải lần lượt lấy khóa tương ứng.

Khi tăng số worker, số transaction chờ cùng dòng tăng. Chúng có thể giữ connection trong toàn bộ thời gian chờ. Một số hệ thống còn giữ thêm các khóa khác trước khi chờ dòng nóng, khiến lock footprint lớn hơn và tăng nguy cơ deadlock.

Các dấu hiệu thường gặp:

- `lock wait` tăng cùng số connection active;
- p95/p99 tăng nhanh hơn p50;
- deadlock hoặc lock timeout tăng;
- throughput của thao tác ghi trên một aggregate không tăng dù worker nhiều hơn;
- connection pool pending tăng dù database CPU không đạt 100%, vì bottleneck nằm ở lock.

### Cách xử lý hotspot

Trước khi tăng pool, hãy xác định vì sao nhiều transaction cần cùng tài nguyên:

1. Rút ngắn transaction và chỉ giữ khóa trong thời gian cần thiết.
2. Không gọi HTTP, gửi email hoặc chờ người dùng trong khi đang giữ khóa.
3. Tối ưu index và điều kiện cập nhật để khóa ít dòng hơn.
4. Dùng câu `UPDATE` có điều kiện hoặc atomic increment thay cho quy trình đọc rồi ghi kéo dài ở ứng dụng.
5. Phân vùng dữ liệu hoặc chia bộ đếm nóng khi nghiệp vụ cho phép.
6. Giới hạn số worker xử lý cùng một key/aggregate.
7. Đưa công việc có thể xử lý nền vào hàng đợi để điều tiết tốc độ.

## Chi phí của quá nhiều connection

Mỗi connection database có chi phí quản lý. Chi phí cụ thể phụ thuộc hệ quản trị, cấu hình và trạng thái connection, nhưng thường gồm:

- cấu trúc session, buffer và metadata;
- bộ nhớ cho trạng thái transaction, statement và hoạt động đang chạy;
- socket, file descriptor và tài nguyên kernel;
- chi phí authentication, TLS và thiết lập session khi tạo mới;
- chi phí lập lịch thread/process và chuyển đổi context;
- bộ nhớ tạm cho sort, hash join hoặc operation theo session;
- áp lực lên cache CPU và buffer cache khi nhiều công việc hoạt động cùng lúc.

Connection idle thường nhẹ hơn connection đang chạy truy vấn, nhưng số lượng idle connection rất lớn vẫn tiêu thụ tài nguyên và làm tăng chi phí quản trị. Một số hệ quản trị có mô hình process/thread riêng cho session; một số hỗ trợ thread pool hoặc proxy để tách số client connection khỏi số worker backend. Không nên giả định mọi engine có cùng chi phí cho mỗi connection.

### Oversubscription CPU

Nếu database có ít core hơn nhiều so với số tác vụ CPU-bound đang chạy, scheduler phải chia thời gian CPU giữa nhiều runnable thread/process. Khi số runnable task quá lớn, thời gian chuyển đổi context và cạnh tranh cache tăng. Mỗi truy vấn có thể tiến triển chậm hơn dù tổng số truy vấn đang hoạt động cao hơn.

Tình huống này tương tự việc mở quá nhiều worker trên một máy xử lý giới hạn: nhiều worker cùng tồn tại không làm máy tính thêm nhanh. Chúng chỉ chia sẻ cùng năng lực xử lý.

### Bộ nhớ và I/O

Nhiều truy vấn đồng thời có thể cùng tạo sort, hash table, temporary result hoặc đọc các page khác nhau. Bộ nhớ cần cho các operation này có thể tăng theo concurrency. Khi áp lực bộ nhớ cao, hệ thống có thể phải dùng temporary storage hoặc làm giảm cache hit ratio.

Nhiều session cùng phát sinh I/O cũng có thể đẩy storage tới giới hạn IOPS hoặc throughput. Lúc đó, query time tăng dù CPU còn dư. Tăng pool làm số operation I/O đồng thời cao hơn nhưng không làm thiết bị lưu trữ có thêm năng lực.

## Throughput có thể tăng, đứng yên hoặc giảm

Quan hệ giữa số connection và throughput thường có ba vùng:

Đường cong minh họa dưới đây mô tả xu hướng khái niệm, không phải benchmark của một database cụ thể:

```text
Throughput
500 |                         *---*
450 |                    *         \
400 |               *                *
300 |          *
200 |      *
100 |  *
  0 +------------------------------------> Connections
      1  2  4  8  12 16 24 32 48
```

Ở đoạn đầu, thêm connection làm throughput tăng. Gần điểm bão hòa, đường cong phẳng dần. Khi concurrency quá cao, throughput có thể giảm do contention và chi phí quản lý.

1. **Vùng thiếu concurrency:** database còn tài nguyên nhưng số request được gửi vào quá ít. Thêm connection giúp tận dụng CPU, I/O và latency của các thao tác độc lập tốt hơn.
2. **Vùng bão hòa:** throughput tiến gần năng lực tối đa. Thêm connection chỉ cải thiện rất ít hoặc không cải thiện throughput; latency và queue bắt đầu tăng rõ.
3. **Vùng quá tải:** contention, scheduling, memory pressure và I/O queue làm mỗi giao dịch chậm hơn. Throughput có thể giảm trong khi latency tăng mạnh.

Đường cong thực tế không nhất thiết có hình dạng giống biểu đồ. Nó phụ thuộc workload, database engine, schema, hardware, cache state và tỷ lệ đọc/ghi. Điều cần tìm là vùng throughput đạt mức tốt với latency và error rate còn chấp nhận được.

### Throughput và latency phải được xem cùng nhau

Một hệ thống có thể hoàn tất cùng 1.000 giao dịch/giây nhưng p99 latency tăng từ 100 ms lên 2 giây. Với người dùng, hệ thống đã chậm đi đáng kể dù throughput không đổi.

Ngược lại, nếu giảm pool từ 100 xuống 30, throughput có thể vẫn giữ nguyên trong khi p99 giảm vì ít transaction cạnh tranh hơn. Connection pool nhỏ hơn có thể cải thiện độ ổn định khi nó giới hạn tải vào database ở mức database xử lý hiệu quả.

Không tối ưu một chỉ số riêng lẻ. Cần xem throughput, p50/p95/p99 latency, lỗi timeout, pool wait và database wait cùng nhau.

## Connection pool là cơ chế backpressure

Pool giới hạn số connection được mượn đồng thời. Khi tất cả connection đang bận, request mới chờ trong hàng đợi pool hoặc bị từ chối sau acquisition timeout.

Điều đó có thể là hành vi mong muốn. Nếu database chỉ xử lý hiệu quả 20 transaction nặng cùng lúc, pool có giới hạn gần năng lực này giúp tránh gửi 200 transaction nặng vào database trong cùng một thời điểm.

Backpressure giúp hệ thống:

- giới hạn lượng công việc đồng thời ở tầng database;
- giữ hàng chờ tại tầng có thể kiểm soát thay vì để database bị quá tải;
- bảo vệ memory, CPU và lock manager;
- tạo điểm timeout rõ ràng cho request không thể chờ lâu;
- giúp ứng dụng từ chối hoặc điều tiết tải khi dependency suy giảm.

Tuy nhiên, hàng đợi pool cũng cần giới hạn thời gian và lượng request chờ. Nếu hàng đợi không giới hạn, ứng dụng có thể tích tụ quá nhiều request, tiêu thụ bộ nhớ và tạo một đợt tải dồn khi database hồi phục.

### Pool wait và lock wait là hai chỉ số khác nhau

| Chỉ số | Ý nghĩa | Hướng điều tra |
| --- | --- | --- |
| Connection acquisition time | Thời gian chờ mượn connection từ pool. | Pool quá nhỏ, connection bị giữ lâu, leak hoặc pool queue quá dài. |
| Active connections | Số connection đang được ứng dụng mượn. | Đối chiếu với pool maximum và thời gian giữ connection. |
| Idle connections | Connection sẵn sàng được mượn. | Có thể còn capacity; cần xem thời điểm và workload. |
| Pending threads | Số thread đang chờ connection. | Pool đã hết connection khả dụng hoặc connection trả về quá chậm. |
| SQL execution time | Thời gian thực thi câu lệnh ở database/driver. | Query plan, CPU, I/O, network và contention. |
| Lock wait time | Thời gian chờ khóa database. | Hot row, transaction dài, thứ tự truy cập khóa, deadlock. |
| Connection usage time | Thời gian một request giữ connection. | Transaction dài, nhiều round trip, gọi dịch vụ ngoài trong transaction. |

Nếu acquisition time cao nhưng database active session thấp và có nhiều idle capacity, pool có thể quá nhỏ hoặc connection không được trả về đúng lúc. Nếu acquisition time cao, mọi connection đều active và database lock wait cao, tăng pool có thể làm tình hình xấu hơn.

## Ví dụ: tăng pool làm throughput giảm

Giả sử một API cập nhật trạng thái đơn hàng. Mỗi transaction:

1. Đọc đơn hàng.
2. Khóa một dòng tồn kho dùng chung.
3. Cập nhật số lượng.
4. Ghi audit và commit.

Một benchmark minh họa có thể cho kết quả như sau:

| Pool maximum | Throughput | p95 latency | Lock wait trung bình | Nhận xét |
| ---: | ---: | ---: | ---: | --- |
| 8 | 420 tx/s | 90 ms | 8 ms | Có thể còn thiếu concurrency. |
| 16 | 610 tx/s | 130 ms | 18 ms | Throughput tăng đáng kể. |
| 24 | 640 tx/s | 260 ms | 75 ms | Gần điểm bão hòa. |
| 40 | 625 tx/s | 620 ms | 240 ms | Nhiều transaction chờ cùng tài nguyên nóng. |
| 64 | 560 tx/s | 1.200 ms | 510 ms | Overload làm giảm throughput. |

Các con số chỉ minh họa cách đọc kết quả. Trong tình huống này, pool 16 hoặc 24 có thể phù hợp hơn pool 64, dù pool 64 cho phép nhiều request cùng mượn connection hơn. Cách giải quyết tiếp theo có thể là giảm tranh chấp trên dòng tồn kho, rút ngắn transaction hoặc phân phối tải theo sản phẩm.

Nếu workload chủ yếu là đọc dữ liệu độc lập và database còn CPU/I/O, đường cong có thể khác. Vì vậy, không lấy con số từ một benchmark làm cấu hình chung cho mọi ứng dụng.

## Pool size phải tính trên toàn bộ ứng dụng

Một lỗi phổ biến là cấu hình pool theo từng instance mà quên tổng số instance.

Giả sử:

- 8 instance ứng dụng;
- mỗi instance có pool maximum 30;
- có 2 worker service cũng dùng database, mỗi worker có pool maximum 10.

Số connection tối đa mà các pool này có thể mở là:

\[
8 \times 30 + 2 \times 10 = 260
\]

Database phải chịu được tổng 260 connection từ các client đó, cộng thêm connection quản trị, migration, monitoring, batch job và ứng dụng khác. Nếu database chỉ có ngân sách 180 connection, cấu hình per-instance đã vượt ngân sách trước khi tính traffic đột biến.

### Lập ngân sách connection

Hãy tính theo công thức:

\[
\text{Tổng pool tối đa} = \sum_i (\text{số instance}_i \times \text{pool max}_i)
\]

Sau đó trừ đi phần connection dành cho:

- quản trị và vận hành khẩn cấp;
- migration, backup hoặc maintenance;
- monitoring và observability;
- worker, scheduler và batch job;
- ứng dụng khác dùng chung database;
- headroom cho scale-out hoặc failover.

Không cấu hình pool bằng đúng `max_connections` của database. Khi ứng dụng chiếm hết connection, DBA hoặc hệ thống monitoring có thể không còn slot để điều tra và khắc phục sự cố.

### Scale-out làm tổng connection tăng

Nếu autoscaling tăng số application instance từ 4 lên 20 và mỗi instance giữ pool tối đa 25, tổng khả năng mở connection tăng từ 100 lên 500. Database có thể bị quá tải đúng lúc autoscaler cố gắng xử lý traffic tăng.

Do đó, pool max cần được xem là ngân sách toàn hệ thống. Khi scale-out, có thể cần giảm pool trên mỗi instance, dùng proxy/pooler tập trung, giới hạn số instance hoặc điều tiết worker để tổng connection không vượt năng lực database.

## Connection pool sizing: tìm điểm phù hợp bằng phép đo

Không có một con số pool size đúng cho mọi database. Số connection hợp lý phụ thuộc:

- số core và năng lực CPU database;
- workload CPU-bound hay I/O-bound;
- tỷ lệ read/write và mức lock contention;
- thời gian transaction giữ connection;
- thời gian round trip giữa app và database;
- số application instance và worker;
- giới hạn connection và mô hình session của database;
- nhu cầu failover, scale-out và headroom vận hành.

Một heuristic có thể dùng làm điểm bắt đầu, nhưng không thay cho benchmark. Công thức kiểu `core_count * 2` hoặc các quy tắc cố định khác có thể hữu ích trong một số workload, song không phản ánh lock hotspot, I/O latency, query mix hay số instance thực tế.

### Quy trình benchmark có kiểm soát

1. **Chọn workload đại diện:** dùng cùng tỷ lệ đọc/ghi, kích thước dữ liệu, index, transaction duration và phân bố key như production.
2. **Giữ database và hạ tầng cố định:** không thay CPU, memory, storage hoặc schema giữa các lần đo.
3. **Warm up:** cho ứng dụng và database nạp class, connection, query plan và cache trước khi ghi kết quả.
4. **Tăng concurrency theo bậc:** ví dụ pool maximum 4, 8, 12, 16, 24, 32; mỗi lần chỉ đổi một biến.
5. **Đo đủ lâu:** tránh kết luận từ vài giây đầu hoặc một spike ngắn.
6. **Theo dõi cả ứng dụng và database:** pool wait, active/idle/pending, CPU, memory, I/O, lock wait, deadlock và query latency.
7. **Lặp lại:** chạy nhiều lần với cùng điều kiện để phân biệt xu hướng ổn định với nhiễu.
8. **Chọn điểm cân bằng:** throughput gần cực đại nhưng p95/p99, error rate và tài nguyên vẫn trong ngân sách.

### Open-loop và closed-loop load test

Trong closed-loop test, mỗi virtual user gửi request mới sau khi request trước hoàn tất. Khi hệ thống chậm, tốc độ gửi tự giảm. Điều này có thể che giấu khả năng xử lý tải đến cố định vì generator vô tình gửi ít request hơn khi server chậm.

Trong open-loop test, load generator gửi theo tốc độ đã định trước, độc lập với thời gian phản hồi. Cách này giúp quan sát hàng chờ tăng khi arrival rate vượt năng lực phục vụ. Cần giới hạn backlog và theo dõi số request thực sự được phát, hoàn tất, timeout hoặc bị bỏ.

Với cả hai loại, tránh chỉ báo cáo throughput của client mà không báo số request bị drop hoặc timeout. Một bài test có thể trông như throughput ổn định chỉ vì load generator không còn gửi đủ tải.

## Những chỉ số nên theo dõi

### Ở tầng ứng dụng và connection pool

- pool maximum và minimum;
- active, idle và pending connection;
- acquisition time p50/p95/p99;
- connection usage/lease duration;
- số lần timeout khi lấy connection;
- số lần tạo mới, đóng connection và connection validation failure;
- thread bị block trong lúc giữ connection;
- connection leak hoặc transaction mở quá lâu.

### Ở tầng database

- số session total, active, idle và idle-in-transaction;
- CPU utilization và runnable queue;
- buffer/cache hit ratio và memory pressure;
- storage latency, IOPS và throughput;
- lock wait, deadlock và blocked session;
- query latency theo fingerprint hoặc normalized SQL;
- temporary table, sort spill và hash spill;
- transaction duration và long-running transaction;
- replication lag nếu workload dùng read replica.

Không diễn giải một chỉ số riêng lẻ. Ví dụ, database CPU 40% không chứng minh còn capacity nếu workload bị chặn bởi một row lock nóng hoặc storage latency. Ngược lại, connection count cao không có nghĩa tất cả connection đang chạy truy vấn; nhiều connection có thể idle.

### Tách thời gian một request

Một request có thể có thời gian tổng:

\[
T_{total} = T_{pool} + T_{db} + T_{app} + T_{network}
\]

Trong đó `T_db` có thể gồm thời gian thực thi SQL và chờ khóa; `T_app` có thể bao gồm xử lý logic trong lúc đang giữ connection. Đây là cách phân rã khái niệm, các khoảng thời gian thực tế có thể chồng lấp khi có async hoặc nhiều truy vấn song song.

Hãy instrument thời điểm bắt đầu mượn connection, lúc lấy được connection, lúc gửi SQL và lúc trả connection. Khi biết phần thời gian nào tăng theo tải, bạn mới chọn đúng biện pháp.

## Cấu hình pool trong Java/Spring

Ví dụ HikariCP:

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 16
      minimum-idle: 4
      connection-timeout: 3000
      validation-timeout: 1000
      idle-timeout: 600000
      max-lifetime: 1800000
```

Các giá trị trên chỉ là ví dụ minh họa, không phải cấu hình khuyến nghị chung. `maximum-pool-size` giới hạn connection tối đa của một pool; `connection-timeout` giới hạn thời gian chờ lấy connection. `minimum-idle` điều khiển số connection nhàn rỗi mục tiêu; `max-lifetime` giúp thay connection theo vòng đời phù hợp với database/proxy.

Khi cấu hình:

- Tính tổng pool trên mọi instance, không chỉ một JVM.
- Đặt acquisition timeout hữu hạn để request không chờ vô hạn.
- Không tăng `maximum-pool-size` chỉ vì thấy pending thread; xem database active sessions và wait events trước.
- Không giữ connection trong khi gọi dịch vụ ngoài hoặc xử lý logic không cần database.
- Theo dõi connection leak và transaction kéo dài.
- Đảm bảo health check hoặc monitoring không mở thêm quá nhiều connection ngoài ngân sách.

### Virtual threads không làm database có thêm capacity

Java virtual threads giúp xử lý nhiều tác vụ blocking với chi phí thread thấp hơn trong một số workload. Nhưng chúng không tăng số CPU core, IOPS, row lock hay năng lực transaction của database.

Nếu tạo hàng nghìn virtual thread và để tất cả cùng gọi database, connection pool vẫn giới hạn số connection được mượn. Nếu tăng pool để theo số virtual thread, database có thể nhận quá nhiều session và bị quá tải. Hãy giữ giới hạn concurrency ở tầng database riêng với số lượng thread của ứng dụng.

## Pooler và proxy: tách client connection khỏi backend session

Trong một số kiến trúc, có thể dùng connection pooler hoặc database proxy để nhiều client connection được ghép vào một tập backend connection nhỏ hơn. Ví dụ, PgBouncer có các pooling mode như session, transaction và statement, mỗi mode có giới hạn về cách sử dụng session state.

Pooler có thể giảm số backend session và chi phí tạo connection, nhưng không làm database thực hiện được nhiều transaction CPU-bound hơn năng lực phần cứng. Nếu backend pool đã bão hòa, client vẫn phải chờ ở pooler.

Transaction pooling có thể thay đổi giả định về session affinity. Ứng dụng không nên dựa vào temporary table, session variable, session-level advisory lock hoặc prepared statement có vòng đời gắn với một backend qua nhiều transaction nếu pooling mode không bảo đảm cùng backend. Hãy chọn mode phù hợp với hành vi ứng dụng và kiểm tra tài liệu pooler.

Proxy/pooler cũng cần ngân sách backend connection, timeout, giới hạn client và metric riêng. Không chỉ nhìn số client connection để đánh giá tải database.

## Các biện pháp thay thế việc tăng connection

Nếu throughput không tăng khi pool lớn hơn, hãy tìm bottleneck trước khi thay cấu hình:

| Triệu chứng | Biện pháp nên xem xét |
| --- | --- |
| Pool pending cao, database còn CPU/I/O và lock wait thấp | Tăng pool từng bước hoặc giảm thời gian giữ connection; xác nhận pool chưa bị leak. |
| Pool pending cao, DB CPU gần bão hòa | Tối ưu query/index, giảm truy vấn thừa, cache hợp lý hoặc giới hạn concurrency. |
| Lock wait cao trên một vài dòng | Giảm hotspot, rút ngắn transaction, phân phối key hoặc serialize công việc theo aggregate. |
| Storage latency/IOPS cao | Giảm I/O, cải thiện index và query plan, tăng năng lực storage nếu cần. |
| Nhiều transaction idle-in-transaction | Sửa code giữ transaction quá lâu, đóng transaction trước khi chờ công việc ngoài. |
| Connection acquisition timeout do leak | Kiểm tra đường thoát exception, resource close và transaction propagation. |
| Scale-out làm tổng connection vượt ngân sách | Giảm pool mỗi instance, giới hạn replica, dùng pooler hoặc tính lại ngân sách toàn hệ thống. |
| Một request thực hiện quá nhiều SQL tuần tự | Giảm round trip, batch hợp lý hoặc gom truy vấn mà không làm transaction quá dài. |
| Background worker chiếm hết pool | Dùng pool/bulkhead riêng hoặc giới hạn số worker để giữ capacity cho request tương tác. |

### Giảm thời gian giữ connection

Một connection bị mượn lâu có thể do query chậm, nhưng cũng có thể do ứng dụng giữ connection trong lúc làm việc không cần database. Ví dụ:

```java
@Transactional
public void createOrder(CreateOrderRequest request) {
    Order order = orderRepository.save(Order.from(request));
    paymentClient.charge(request.payment());
    emailClient.sendConfirmation(order);
}
```

Transaction ở đây giữ connection trong khi chờ hai dịch vụ ngoài. Nếu payment hoặc email chậm, connection bị chiếm lâu dù database không làm việc trong toàn bộ thời gian đó.

Hãy tách thao tác bên ngoài ra khỏi transaction database và dùng outbox hoặc workflow có thể phục hồi khi phù hợp. Transaction ngắn giúp connection quay lại pool sớm hơn, giảm số connection cần thiết cho cùng throughput.

## Giới hạn concurrency theo loại công việc

Không phải mọi loại truy vấn có cùng chi phí. Một truy vấn đọc nhỏ theo primary key khác với báo cáo scan hàng triệu dòng. Nếu tất cả dùng chung một pool không có giới hạn theo workload, một đợt báo cáo nặng có thể chiếm hết connection và làm request tương tác phải chờ.

Có thể cân nhắc:

- giới hạn worker cho batch/reporting;
- dùng queue để điều tiết công việc nền;
- bulkhead hoặc semaphore ở tầng ứng dụng;
- pool riêng cho workload đọc dài và workload tương tác, nếu tổng connection được tính chung;
- read replica cho truy vấn đọc phù hợp với consistency requirement;
- ưu tiên request tương tác bằng admission control ở tầng ứng dụng.

Pool riêng không tạo thêm capacity database. Nếu tạo hai pool, phải cộng giới hạn của chúng vào tổng ngân sách và tránh cấu hình mỗi pool như thể nó có toàn bộ `max_connections`.

## Khi nào tăng connection là lựa chọn hợp lý?

Tăng pool có thể hợp lý khi các phép đo cho thấy:

1. Acquisition wait cao và pool thường xuyên hết connection.
2. Database còn CPU, memory và I/O capacity đáng kể.
3. Lock wait và deadlock thấp, không có hotspot nghiêm trọng.
4. Connection usage duration hợp lý và không có leak hoặc transaction dài bất thường.
5. Benchmark tăng pool giúp throughput tăng mà p95/p99 và error rate vẫn trong SLO.
6. Tổng connection sau khi nhân số replica vẫn nằm trong ngân sách database.

Nếu chỉ một trong các điều kiện này không đúng, hãy điều tra trước khi tăng pool. Tăng connection không phải cách chữa mặc định cho mọi loại latency.

## Quy trình điều tra khi pool bị đầy

Khi thấy connection pool đạt maximum và request bắt đầu timeout, có thể đi theo trình tự:

1. Xác định acquisition wait p95/p99 và số pending thread.
2. Xác định active connection đang chạy SQL, chờ lock hay bị giữ trong code ứng dụng.
3. Đối chiếu database session, CPU, I/O, lock wait và long transaction.
4. Phân loại bottleneck: pool quá nhỏ, query chậm, lock contention, connection leak, external call trong transaction hay database saturation.
5. Thử một thay đổi nhỏ trên môi trường benchmark: giảm transaction duration, tối ưu query hoặc tăng pool một bậc.
6. So sánh throughput, latency percentile, error rate và resource usage.
7. Cập nhật ngân sách connection theo tổng số replica và worker sau thay đổi.

Nếu database đã bão hòa, có thể giảm pool hoặc giới hạn concurrency để giảm queue và bảo vệ latency. Điều đó có thể làm số request chờ ở tầng ứng dụng tăng, nhưng tránh đẩy database vào trạng thái quá tải. Chọn vị trí hàng chờ có kiểm soát và timeout phù hợp.

## Bài tập vận dụng

Một dịch vụ Java có 12 instance. Mỗi instance cấu hình HikariCP `maximum-pool-size = 25`. Database có giới hạn 250 connection; ngoài dịch vụ này còn có 30 connection dành cho monitoring, migration và các worker khác. Khi traffic tăng, pool pending tăng, database CPU đạt 95%, lock wait cũng tăng và p99 latency tăng gấp ba. Nhóm vận hành đề xuất tăng pool lên 40 trên mỗi instance.

Hãy phân tích:

1. Tổng số connection tối đa của 12 instance hiện tại là bao nhiêu? Nếu tăng pool lên 40 thì tổng là bao nhiêu?
2. Sau khi dành 30 connection cho monitoring, migration và worker, ngân sách còn lại cho dịch vụ là bao nhiêu?
3. Vì sao tăng pool trong lúc database CPU và lock wait đều cao có thể làm p99 tệ hơn?
4. Cần phân biệt pool acquisition wait, SQL execution time và lock wait bằng những metric nào?
5. Những thay đổi nào có thể giảm connection usage duration hoặc lock contention?
6. Nếu workload batch đang chiếm connection của request tương tác, có thể dùng cơ chế nào để giới hạn concurrency?

Tổng pool hiện tại có thể mở là `12 × 25 = 300`, đã vượt giới hạn database trước khi cộng 30 connection khác. Nếu tăng lên 40, tổng sẽ là `480`. Ngân sách còn lại cho dịch vụ là `250 - 30 = 220`, tương đương trung bình khoảng 18 connection mỗi instance nếu phân bổ đều và không cần headroom khác. Tuy nhiên, không nên đơn giản đặt 18 mà cần giữ dự phòng cho scale-out, failover và workload đột biến.

Vì database CPU đã đạt 95% và lock wait tăng, tăng pool lên 40 có nguy cơ đưa thêm transaction vào hàng chờ nội bộ, làm latency và contention cao hơn. Nhóm nên kiểm tra query plan, hotspot, transaction duration, connection leak và worker concurrency; sau đó benchmark với pool nằm trong ngân sách và so sánh throughput cùng p95/p99. Có thể giảm số worker batch, dùng bulkhead, rút ngắn transaction và điều tiết tải trước khi cân nhắc tăng concurrency database.

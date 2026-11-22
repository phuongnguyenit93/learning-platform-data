# Đo tải với dữ liệu đại diện, khởi động tải và độ trễ phân vị

Một bài benchmark MySQL chỉ có ý nghĩa khi dữ liệu, truy vấn, tỷ lệ đọc/ghi và mức đồng thời gần với cách hệ thống hoạt động thực tế. Chạy vài câu `SELECT` trên bảng nhỏ rồi lấy thời gian trung bình không cho biết database sẽ phản ứng thế nào khi có hàng triệu bản ghi, nhiều người dùng cùng cập nhật một nhóm hàng hoặc buffer pool không còn chứa toàn bộ working set.

Quy trình đo tải cần chuẩn bị dữ liệu có phân bố hợp lý, tạo workload có nhịp gửi rõ ràng, tách giai đoạn khởi động khỏi giai đoạn đo ổn định, rồi phân tích throughput, lỗi và các phân vị latency như p50, p95, p99. Các số liệu phải được đối chiếu với CPU, I/O, buffer pool, lock wait và replication để xác định giới hạn nằm ở ứng dụng, mạng hay MySQL.

## 1. Xác định câu hỏi trước khi benchmark

Trước khi chọn công cụ, hãy xác định điều cần đo. Một benchmark có thể trả lời các câu hỏi khác nhau:

- Một instance MySQL xử lý được bao nhiêu transaction mỗi giây với workload hiện tại?
- Khi tăng số client đồng thời, latency bắt đầu tăng mạnh ở mức nào?
- Index mới có cải thiện p95 của truy vấn quan trọng hay chỉ làm insert chậm hơn?
- Buffer pool có đủ chứa working set thường xuyên được truy cập không?
- Một thay đổi schema, cấu hình hoặc phiên bản có làm tăng lock wait hay replication lag không?
- Ứng dụng đạt SLO latency khi lưu lượng tăng đột biến hay không?

Viết tiêu chí thành các đại lượng có thể đo:

| Đại lượng | Ý nghĩa |
|---|---|
| Offered load | Số request/transaction mà công cụ tạo ra mỗi giây |
| Throughput | Số request/transaction hoàn tất thành công mỗi giây |
| Latency | Thời gian từ lúc gửi đến lúc nhận kết quả theo ranh giới đã chọn |
| Error rate | Tỷ lệ lỗi SQL, HTTP, timeout, retry hoặc request bị loại |
| Concurrency | Số client/session hoặc request đang hoạt động đồng thời |
| Resource utilization | CPU, RAM, disk IOPS/latency, network và tài nguyên connection |
| Replication lag | Độ trễ áp dụng transaction trên replica nếu topology có replication |

Phải xác định ranh giới latency. Đo tại HTTP API bao gồm queueing, application code, connection pool, network và MySQL; đo thời gian statement trong MySQL chỉ phản ánh phần xử lý ở database. Cả hai đều hữu ích, nhưng không thể thay thế cho nhau.

## 2. Tạo dữ liệu đại diện

Dataset là một phần của benchmark, không phải dữ liệu phụ để làm cho test chạy được. Một bảng chỉ có vài trăm dòng thường nằm trọn trong buffer pool và có thể được truy vấn bằng scan mà không bộc lộ vấn đề index. Khi tăng dữ liệu, cardinality, phân bố giá trị và kích thước working set có thể làm execution plan cũng như latency thay đổi đáng kể.

### Những đặc tính cần tái hiện

| Đặc tính | Câu hỏi cần trả lời | Vì sao quan trọng |
|---|---|---|
| Số dòng và dung lượng | Bảng có bao nhiêu dòng, data/index chiếm bao nhiêu GB? | Ảnh hưởng I/O, cache, thời gian scan và backup |
| Cardinality | Một cột có bao nhiêu giá trị phân biệt? | Ảnh hưởng selectivity và lựa chọn index |
| Skew/hot key | Một vài customer/product có nhận phần lớn request không? | Tạo hot page, lock contention và cache locality |
| Phân bố thời gian | Dữ liệu mới có được truy cập nhiều hơn dữ liệu cũ không? | Mô phỏng truy vấn theo thời gian và retention |
| Kích thước bản ghi | Có nhiều JSON/text hoặc cột nullable không? | Ảnh hưởng số page, I/O và memory |
| Quan hệ bảng | Tỷ lệ parent/child, số dòng mỗi đơn hàng, số event mỗi user? | Ảnh hưởng join, foreign key và cascade |
| Index | Có các secondary index giống production không? | Ảnh hưởng cả đọc, ghi và dung lượng |
| Tính hợp lệ | Constraint, NULL, duplicate và dữ liệu biên có tương tự không? | Tránh benchmark trên dữ liệu quá sạch so với thực tế |

Không chỉ tạo ID tăng dần và giá trị phân bố đều nếu production có dữ liệu lệch. Ví dụ, một số khách hàng lớn có thể tạo ra 30% truy vấn; một số trạng thái chỉ chiếm 1% dữ liệu; các đơn hàng mới thường được đọc nhiều hơn đơn cũ. Phân bố này ảnh hưởng trực tiếp tới cache và kế hoạch truy vấn.

### Working set và buffer pool

Phải biết mục tiêu benchmark là cache-friendly hay disk-bound:

- **Cache-friendly:** phần dữ liệu/index thường truy cập nhỏ hơn đáng kể so với `innodb_buffer_pool_size`. Mục tiêu là đo throughput và latency khi dữ liệu chủ yếu ở RAM.
- **Disk-bound:** working set lớn hơn buffer pool hoặc truy cập có tính phân tán. Mục tiêu là đo read I/O, cache miss và khả năng storage phục vụ tải.
- **Mixed:** một nhóm dữ liệu nóng nằm trong RAM, phần còn lại lạnh hơn. Đây thường là tình huống thực tế của workload giao dịch.

Không kết luận database xử lý được tải production chỉ vì benchmark trên dataset nhỏ có latency thấp. Ngược lại, cũng không cố làm working set lớn hơn RAM nếu production thực tế luôn có tỷ lệ cache hit cao. Hãy mô tả rõ kịch bản đang đo.

### Tạo dữ liệu có thể tái lập

Seed dữ liệu nên ổn định để các lần chạy có cùng phân bố. Ghi lại script, seed, số dòng, kích thước bảng, index và checksum hoặc thống kê tổng hợp. Nếu dùng bản sao production, phải loại bỏ hoặc ẩn danh dữ liệu nhạy cảm và giữ nguyên đặc tính phân bố cần thiết.

Ví dụ bảng đơn hàng:

```sql
CREATE TABLE orders (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  customer_id BIGINT UNSIGNED NOT NULL,
  status VARCHAR(24) NOT NULL,
  total_amount DECIMAL(14,2) NOT NULL,
  created_at DATETIME(6) NOT NULL,
  PRIMARY KEY (id),
  KEY idx_orders_customer_created (customer_id, created_at),
  KEY idx_orders_status_created (status, created_at)
) ENGINE=InnoDB;
```

Dataset cần có đủ customer, status và mốc thời gian để các truy vấn theo customer, trạng thái và khoảng ngày có selectivity tương tự workload thật. Nếu mọi dòng đều có cùng `status`, benchmark sẽ không đại diện cho phân bố production.

## 3. Mô hình hóa workload

Một workload thực tế thường là hỗn hợp nhiều loại thao tác, không phải lặp vô hạn một câu `SELECT` duy nhất. Hãy phân loại theo transaction hoặc use case:

| Nhóm | Ví dụ | Thành phần chi phí |
|---|---|---|
| Point read | Tìm đơn theo primary key | B-tree lookup, buffer pool, round trip |
| Range read | Lấy đơn của customer trong khoảng thời gian | Index range scan, sort, rows examined |
| Join/report | Tổng hợp đơn và chi tiết đơn | Join order, cardinality, temporary table, aggregation |
| Insert | Tạo đơn và các dòng chi tiết | Primary/secondary index, redo, binlog, commit |
| Update | Đổi trạng thái hoặc cập nhật tồn kho | Row lock, index maintenance, contention |
| Delete/cleanup | Xóa dữ liệu hết hạn theo batch | Undo, purge, lock, replication |
| Mixed transaction | Đọc tồn kho, ghi đơn và trừ số lượng | Nhiều statement trong cùng transaction và tính nguyên tử |

Tạo tỷ lệ thao tác theo số liệu quan sát hoặc giả định được ghi rõ. Ví dụ workload minh họa có 65% read, 25% insert, 8% update và 2% delete. Tỷ lệ này chỉ là ví dụ; hệ thống báo cáo, hệ thống đơn hàng và hệ thống telemetry có thể khác rất xa.

Mỗi transaction nên có ranh giới giống ứng dụng: số statement, thứ tự đọc/ghi, isolation level, thời gian giữ transaction và cách commit. Một benchmark chạy từng statement autocommit không mô phỏng đúng transaction gồm năm lần đọc và hai lần ghi.

### Giá trị tham số cũng phải đại diện

Không gửi cùng một `customer_id` cho mọi truy vấn nếu production truy cập hàng triệu customer. Ngược lại, cũng không phân phối đều nếu có một số key nóng. Dùng phân bố tham số gần thực tế để tạo đúng cache locality và lock contention.

Với truy vấn range, mô phỏng nhiều kích thước khoảng: truy vấn 10 dòng, 100 dòng và 10.000 dòng. Với tìm kiếm theo trạng thái, dùng tỷ lệ phổ biến/hiếm. Với update, tạo cả trường hợp mỗi worker cập nhật một hàng riêng và nhiều worker cùng cập nhật hàng nóng.

## 4. Chuẩn bị môi trường benchmark

Benchmark nên chạy trên MySQL instance hoặc clone được dành riêng cho thử nghiệm. Không tạo tải lớn trên production nếu chưa có phê duyệt vận hành và giới hạn an toàn.

Ghi lại ít nhất:

- MySQL version, edition, storage engine và cấu hình server.
- CPU, RAM, số core, loại volume/storage, IOPS và filesystem.
- `innodb_buffer_pool_size`, redo capacity, connection limit, SQL mode và isolation level.
- Schema, index, collation, charset, số dòng và dung lượng từng bảng.
- Binary log, replication topology, durability settings và backup workload.
- Client/driver/tool version, số máy phát tải và cấu hình network.
- Phiên bản ứng dụng, JVM, connection pool và cấu hình thread.

Kiểm tra cấu hình MySQL:

```sql
SELECT VERSION(), @@version_comment;

SHOW VARIABLES WHERE Variable_name IN (
  'innodb_buffer_pool_size',
  'innodb_redo_log_capacity',
  'max_connections',
  'transaction_isolation',
  'sql_mode',
  'binlog_format',
  'sync_binlog',
  'innodb_flush_log_at_trx_commit'
);
```

Đảm bảo các điều kiện so sánh tương đương. Nếu một lần chạy có backup hoặc replica catch-up còn lần khác không có, kết quả không thể so sánh trực tiếp. Ghi lại mọi thay đổi cấu hình và không thay nhiều tham số cùng lúc khi đang tìm nguyên nhân.

### Tách máy phát tải khỏi database

Client benchmark cũng tiêu thụ CPU, RAM, socket và network. Nếu máy phát tải hết CPU, throughput đo được sẽ phản ánh giới hạn của load generator chứ không phải MySQL.

Theo dõi CPU và network ở cả client lẫn server. Với tải lớn, dùng nhiều load generator hoặc tăng tài nguyên client. Kiểm tra công cụ có tạo đủ request theo lịch hay không; nếu không, không được kết luận MySQL đã đạt giới hạn.

## 5. Chọn công cụ đo tải

Chọn công cụ theo lớp cần đo:

| Công cụ | Phạm vi phù hợp | Lưu ý |
|---|---|---|
| `sysbench` | Benchmark MySQL trực tiếp, OLTP read/write, thread/concurrency | Workload mẫu tiện dụng; cần tùy biến Lua để gần truy vấn thật |
| JMeter | HTTP, JDBC và các luồng tích hợp | JDBC sampler có thể tạo overhead; cấu hình connection và transaction cẩn thận |
| k6 | API/HTTP với mô hình arrival rate và threshold | Đo trải nghiệm end-to-end; không chỉ riêng thời gian MySQL |
| Gatling | HTTP/API và kịch bản người dùng | Phù hợp mô phỏng luồng request, cần kiểm soát feeder và injection profile |
| Công cụ nội bộ | Transaction nghiệp vụ riêng của ứng dụng | Cần timestamp/histogram chính xác và kiểm soát overhead đo |

Với benchmark MySQL trực tiếp, `sysbench` là điểm bắt đầu tốt. Ví dụ chuẩn bị dữ liệu OLTP:

```bash
sysbench oltp_read_write \
  --db-driver=mysql \
  --mysql-host=127.0.0.1 \
  --mysql-port=3306 \
  --mysql-user=bench_user \
  --mysql-password='REPLACE_WITH_SECRET' \
  --mysql-db=bench \
  --tables=8 \
  --table-size=1000000 \
  prepare
```

Sau khi chuẩn bị, chạy workload với concurrency và thời gian cố định:

```bash
sysbench oltp_read_write \
  --db-driver=mysql \
  --mysql-host=127.0.0.1 \
  --mysql-port=3306 \
  --mysql-user=bench_user \
  --mysql-password='REPLACE_WITH_SECRET' \
  --mysql-db=bench \
  --tables=8 \
  --table-size=1000000 \
  --threads=64 \
  --time=300 \
  --report-interval=10 \
  --percentile=95 \
  run
```

Các thông số chỉ minh họa. Thay mật khẩu mẫu bằng secret được quản lý an toàn; tránh để secret xuất hiện trong shell history hoặc log CI. Chạy `cleanup` chỉ khi đã xác nhận đúng database benchmark và dữ liệu có thể xóa. Workload mặc định của sysbench không tự đại diện cho nghiệp vụ cụ thể; hãy dùng script Lua tùy chỉnh nếu truy vấn, tỷ lệ thao tác hoặc phân bố key khác.

## 6. Warm-up: vì sao không nên đo ngay khi vừa khởi động?

Lần chạy đầu sau khi khởi động có thể chậm hơn vì nhiều lớp chưa được làm nóng:

- InnoDB buffer pool chưa chứa các page thường truy cập.
- OS page cache và storage cache chưa có working set.
- Connection pool chưa tạo đủ kết nối.
- JVM JIT chưa biên dịch các đường code thường dùng.
- Prepared statement và metadata cache chưa được sử dụng đầy đủ.
- DNS, TLS session hoặc connection initialization còn phát sinh chi phí ban đầu.

Nếu mục tiêu là đo steady state, cần một giai đoạn warm-up riêng trước khi bắt đầu ghi số liệu chính. Tuy nhiên, warm-up không được che giấu cold-start behavior nếu hệ thống có yêu cầu phục vụ ngay sau restart. Khi đó, đo cả cold-start và warm steady-state thành hai kịch bản độc lập.

### Quy trình warm-up

1. Khởi động MySQL và ứng dụng với đúng cấu hình benchmark.
2. Tạo connection pool và chạy health check như ứng dụng thực.
3. Phát workload đại diện ở mức thấp rồi tăng dần tới mức đo dự kiến.
4. Tiếp tục chạy cho tới khi latency, throughput và cache metrics ổn định trong một khoảng quan sát đủ dài.
5. Đánh dấu rõ thời điểm kết thúc warm-up; không gộp mẫu warm-up vào thống kê steady-state.
6. Bắt đầu cửa sổ đo chính mà không thay đổi cấu hình hoặc reset dữ liệu ngoài kế hoạch.

Không dùng một thời lượng warm-up cố định cho mọi hệ thống. Một bảng nhỏ có thể nóng sau vài giây; một working set nhiều GB có thể cần lâu hơn hoặc không bao giờ nằm hoàn toàn trong buffer pool. Tiêu chí tốt hơn là trạng thái ổn định của metric và workload.

### Warm cache và cold cache là hai kịch bản khác nhau

Để đo cold-cache, cần quy trình khởi động/restart hoặc trạng thái cache được kiểm soát. Không thể giả định `FLUSH TABLES` làm trống InnoDB buffer pool hay OS page cache. Việc xóa cache hệ điều hành hoặc restart production để tạo cold-cache có thể gây gián đoạn và không nên làm tùy tiện.

Với cold-start test, ghi rõ MySQL vừa restart hay chỉ ứng dụng vừa restart; buffer pool có được load từ dump hay không; OS page cache ở trạng thái nào. Với warm-cache test, chạy warm-up theo đúng phân bố key dự kiến.

## 7. Ramp-up, steady-state, spike và soak test

Một lần chạy đo tải nên chia thành các pha có mục tiêu riêng:

| Pha | Mục tiêu | Quan sát |
|---|---|---|
| Baseline | Đo latency và throughput khi tải rất thấp | Chi phí cơ bản của truy vấn và kết nối |
| Warm-up | Làm nóng cache, pool và runtime | Thời gian ổn định, buffer pool reads, JIT |
| Ramp-up | Tăng dần offered load hoặc concurrency | Điểm bắt đầu latency tăng và resource saturation |
| Steady-state | Giữ tải mục tiêu đủ lâu | p50/p95/p99, throughput, lỗi và tài nguyên |
| Spike | Tăng tải nhanh trong thời gian ngắn | Khả năng hấp thụ burst, queue và recovery |
| Soak | Giữ tải trung bình/cao trong thời gian dài | Memory leak, connection leak, purge, disk growth, lag |
| Cool-down | Giảm tải và theo dõi phục hồi | Queue drain, replica catch-up và latency trở lại bình thường |

Không gộp tất cả pha thành một con số. Một hệ thống có thể đạt p95 tốt trong steady state nhưng timeout khi spike; hoặc chạy tốt 5 phút nhưng suy giảm sau 2 giờ do queue, history list hoặc dung lượng tạm tăng.

## 8. Closed-loop và open-loop load

Mô hình phát tải ảnh hưởng cách đọc kết quả.

### Closed-loop: số người dùng đồng thời cố định

Trong mô hình closed-loop, mỗi virtual user gửi request tiếp theo sau khi request trước hoàn tất. Nếu latency tăng, số request được phát ra tự nhiên giảm. Mô hình này gần với người dùng chờ phản hồi rồi mới thao tác tiếp, nhưng có thể che giấu mức tải mà hệ thống không phục vụ kịp.

### Open-loop: tốc độ gửi độc lập với phản hồi

Trong mô hình open-loop, load generator cố gắng phát request theo lịch cố định, ví dụ 500 request/giây, bất kể response trước đã hoàn tất hay chưa. Mô hình này hữu ích để kiểm tra hệ thống dưới offered load ổn định và phát hiện queue tăng khi server bão hòa.

| Mô hình | Ưu điểm | Rủi ro khi diễn giải |
|---|---|---|
| Closed-loop | Dễ mô phỏng số người dùng đồng thời | Khi server chậm, offered load giảm theo, có thể che saturation |
| Open-loop | Kiểm soát tốc độ request độc lập với latency | Queue có thể tăng nhanh; cần giới hạn và theo dõi request bị drop |

Hiện tượng coordinated omission xảy ra khi load generator chỉ đo request được gửi sau khi request trước hoàn tất, nên bỏ qua khoảng thời gian lẽ ra request khác phải được phát trong lúc server đang chậm. Kết quả latency có thể đẹp giả tạo đúng lúc hệ thống bị nghẽn. Chọn công cụ hỗ trợ arrival-rate model hoặc histogram có hiệu chỉnh coordinated omission; ghi nhận dropped iterations và queueing delay.

Không chỉ nhìn số virtual users. 100 virtual users có thể tạo ra tốc độ request rất khác nhau tùy thời gian think time và response time. Báo cáo cả concurrency, offered rate và completed rate.

## 9. Hiểu p50, p95 và p99

Latency thường có phân bố lệch: phần lớn request nhanh nhưng một số request rất chậm do lock wait, disk read, checkpoint, GC, network hoặc query plan. Trung bình không mô tả tốt phần đuôi phân bố.

- **p50 (median):** 50% request hoàn tất trong thời gian này hoặc nhanh hơn. Đây là mức trải nghiệm điển hình.
- **p95:** 95% request hoàn tất trong thời gian này hoặc nhanh hơn; 5% chậm hơn.
- **p99:** 99% request hoàn tất trong thời gian này hoặc nhanh hơn; 1% chậm hơn.
- **p99.9:** hữu ích với hệ thống có lượng request rất lớn và yêu cầu tail latency chặt, nhưng cần đủ mẫu để ước lượng ổn định.

Ví dụ:

| Chỉ số | Latency |
|---|---:|
| p50 | 18 ms |
| p95 | 95 ms |
| p99 | 420 ms |
| max | 2.8 s |

Trong ví dụ, request điển hình khá nhanh nhưng 1% request chậm hơn 420 ms. Nếu chỉ báo cáo average 35 ms, nhóm vận hành có thể bỏ qua vấn đề tail latency.

### Tính phân vị đúng cách

Thu thập latency của từng request hoặc histogram có độ phân giải đủ tốt. Sắp xếp mẫu tăng dần; p95 là ngưỡng mà ít nhất 95% mẫu không vượt qua. Với dữ liệu lớn, công cụ thường dùng histogram hoặc thuật toán ước lượng phân vị.

Không lấy trung bình p95 của từng worker để tạo p95 tổng. Ví dụ worker A có 1.000 request và worker B có 10 request; trung bình hai p95 sẽ không phải p95 của toàn bộ 1.010 request. Hãy hợp nhất histogram hoặc mẫu thô theo cách công cụ hỗ trợ rồi tính phân vị toàn cục.

Percentile cần đủ mẫu. p99 từ vài trăm request có độ tin cậy thấp vì chỉ có vài mẫu nằm ở phần đuôi. Báo cáo số mẫu, thời gian cửa sổ và phương pháp tính cùng percentile.

### Latency cần tính những thành phần nào?

Ở tầng ứng dụng, có thể tách:

```text
Request latency
  = client scheduling/queue
  + network to application
  + application processing
  + connection-pool wait
  + network to MySQL
  + database execution/lock/commit
  + response serialization/network
```

Đây là phân rã khái niệm; các phần có thể chồng lấp tùy kiến trúc. Dùng tracing hoặc instrumentation để phân biệt pool wait với query execution. Nếu API p99 tăng nhưng MySQL statement latency không tăng, tìm bottleneck ở pool, thread, GC hoặc network.

## 10. Throughput, error rate và điểm bão hòa

Throughput là số thao tác hoàn tất trong một đơn vị thời gian. Phân biệt:

- **Offered throughput:** tốc độ load generator dự định gửi.
- **Completed throughput:** tốc độ hệ thống hoàn tất.
- **Successful throughput:** tốc độ hoàn tất không lỗi.

Khi tải tăng, completed throughput thường tăng cho tới vùng bão hòa. Sau điểm đó, throughput có thể đi ngang trong khi latency và error rate tăng mạnh. Đây là dấu hiệu hệ thống đã chạm một giới hạn tài nguyên hoặc tranh chấp.

Ví dụ đường cong minh họa:

```text
Throughput
  ^
  |                         _________
  |                    ____/
  |               ____/
  |          ____/
  |     ____/
  |____/________________________________> Offered load
       vùng tăng       vùng bão hòa
```

Không chọn cấu hình ở sát điểm bão hòa nếu hệ thống cần chịu burst hoặc tăng trưởng. Xác định operating point với headroom đủ để latency và error rate còn nằm trong SLO.

Theo dõi cả lỗi và retry. Một request retry ba lần có thể tạo ba transaction ở MySQL dù client chỉ nhìn thấy một thao tác nghiệp vụ. Retry không giới hạn có thể làm tải tăng thêm đúng lúc database đang quá tải.

Little's Law có thể dùng để kiểm tra tính hợp lý ở trạng thái ổn định:

\[
L = \lambda W
\]

Trong đó `L` là số request trung bình đang ở trong hệ thống, `λ` là throughput trung bình và `W` là thời gian trung bình trong hệ thống. Công thức áp dụng cho hệ thống ổn định với cách đo nhất quán; không dùng để suy luận khi queue đang tăng không giới hạn.

## 11. Đo latency và throughput bằng k6 ở tầng API

Nếu mục tiêu là đo trải nghiệm của API Spring Boot gọi MySQL, dùng công cụ HTTP như k6. Ví dụ sau tạo arrival rate cố định:

```javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    steady_api_load: {
      executor: 'constant-arrival-rate',
      rate: 200,
      timeUnit: '1s',
      duration: '10m',
      preAllocatedVUs: 50,
      maxVUs: 300,
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<250', 'p(99)<500'],
    http_req_failed: ['rate<0.01'],
  },
};

export default function () {
  const response = http.get(
    'https://test.example.internal/api/orders?status=PAID'
  );

  check(response, {
    'status is 200': (r) => r.status === 200,
  });
}
```

Các giá trị rate, URL và threshold chỉ là ví dụ. Endpoint phải sử dụng dataset đại diện và tài khoản test có quyền giới hạn. Chạy warm-up riêng trước kịch bản đo steady-state; nếu `preAllocatedVUs` không đủ, k6 có thể phải tạo thêm VU và phát sinh dropped iterations. Theo dõi `dropped_iterations`, VU active và CPU của load generator.

`http_req_duration` đo thời gian HTTP ở client, không phải riêng thời gian SQL. Kết hợp APM/tracing hoặc metric phía server để biết thời gian chờ connection pool và thời gian statement. Nếu muốn đo MySQL trực tiếp, dùng sysbench hoặc một harness JDBC được thiết kế cho transaction cần kiểm tra.

## 12. Đo MySQL trong lúc tải

Chụp trạng thái trước, trong và sau mỗi lần chạy. Dùng cùng khoảng thời gian để liên hệ thay đổi của DB với latency ở client.

### Connection và mức đồng thời

```sql
SHOW GLOBAL STATUS WHERE Variable_name IN (
  'Threads_connected',
  'Threads_running',
  'Connections',
  'Max_used_connections',
  'Aborted_connects'
);
```

`Threads_connected` là số connection hiện mở; `Threads_running` là số thread không ở trạng thái sleep. Nếu `Threads_running` tăng cao cùng với latency, kiểm tra CPU, lock wait và query concurrency. Không tăng `max_connections` một cách tự động: thêm connection có thể làm contention và memory pressure nặng hơn.

### Buffer pool

```sql
SHOW GLOBAL STATUS WHERE Variable_name IN (
  'Innodb_buffer_pool_read_requests',
  'Innodb_buffer_pool_reads',
  'Innodb_buffer_pool_pages_data',
  'Innodb_buffer_pool_pages_free',
  'Innodb_buffer_pool_wait_free'
);
```

`Innodb_buffer_pool_read_requests` đếm logical read request; `Innodb_buffer_pool_reads` phản ánh số lần phải đọc page từ disk vì không có trong buffer pool. Có thể xem tỷ lệ miss gần đúng trong một khoảng lấy mẫu bằng:

\[
\text{miss ratio} = \frac{\Delta \text{physical reads}}{\Delta \text{logical read requests}}
\]

Đây là chỉ báo tổng quan, không phải thước đo duy nhất về hiệu năng. Một tỷ lệ nhỏ vẫn có thể tạo nhiều I/O tuyệt đối nếu QPS lớn; cần xem disk latency và số byte đọc cùng lúc.

### Statement digest

Performance Schema tổng hợp các statement theo digest:

```sql
SELECT
  DIGEST_TEXT,
  COUNT_STAR,
  ROUND(AVG_TIMER_WAIT / 1000000000000, 3) AS avg_seconds,
  ROUND(MAX_TIMER_WAIT / 1000000000000, 3) AS max_seconds,
  SUM_ROWS_EXAMINED,
  SUM_ROWS_SENT,
  SUM_CREATED_TMP_DISK_TABLES
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST_TEXT IS NOT NULL
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
```

Timer của Performance Schema được biểu diễn theo picosecond; phép chia ở ví dụ chuyển sang giây. Summary by digest cung cấp count, tổng/thời gian trung bình/tối đa và số hàng được đọc/gửi, nhưng không thay thế histogram latency ở phía client. Bật instrumentation có overhead nhất định; giữ cấu hình quan sát nhất quán giữa các lần benchmark.

### Lock và deadlock

```sql
SHOW GLOBAL STATUS WHERE Variable_name IN (
  'Innodb_row_lock_current_waits',
  'Innodb_row_lock_time',
  'Innodb_row_lock_waits',
  'Innodb_deadlocks'
);

SHOW ENGINE INNODB STATUS\G
```

So sánh delta trước/sau để biết số lần chờ và deadlock phát sinh trong cửa sổ benchmark. Một deadlock đơn lẻ có thể là hành vi được xử lý bằng retry, nhưng tỷ lệ tăng nhanh khi concurrency tăng là dấu hiệu cần xem lại thứ tự cập nhật, transaction duration và index.

### I/O và hệ điều hành

MySQL status cần được đối chiếu với metric host: CPU utilization, run queue, memory pressure, swap, disk read/write IOPS, throughput, fsync latency và network. Một query chậm không nhất thiết do SQL; storage bị giới hạn IOPS hoặc CPU steal trên VM cũng có thể là nguyên nhân.

## 13. Đọc execution plan trong bối cảnh tải

Khi một digest chiếm nhiều thời gian, lấy truy vấn đại diện và xem plan:

```sql
EXPLAIN
SELECT id, created_at, total_amount
FROM orders
WHERE customer_id = 501
  AND created_at >= '2026-11-01'
ORDER BY created_at DESC
LIMIT 50;
```

Trên MySQL hỗ trợ, `EXPLAIN ANALYZE` thực thi câu truy vấn và trả số liệu thực tế về iterator:

```sql
EXPLAIN ANALYZE
SELECT id, created_at, total_amount
FROM orders
WHERE customer_id = 501
  AND created_at >= '2026-11-01'
ORDER BY created_at DESC
LIMIT 50;
```

`EXPLAIN ANALYZE` thực sự chạy truy vấn. Chỉ dùng với SELECT có chi phí đã hiểu trên môi trường benchmark; không chạy tùy tiện một truy vấn nặng trên production. Đối chiếu estimated rows với actual rows, số vòng lặp, temporary table, filesort và index được chọn.

Một index có thể giảm latency đọc nhưng làm insert/update chậm hơn vì phải duy trì thêm B-tree. Benchmark phải đo cả workload hỗn hợp trước và sau thay đổi index, không chỉ chạy lại SELECT đã tối ưu.

## 14. Cách tổ chức một ma trận benchmark

Thay vì thử ngẫu nhiên, lập ma trận có kiểm soát:

| Lần chạy | Dataset | Concurrency/arrival rate | Mục tiêu |
|---|---|---|---|
| A | Working set nhỏ hơn buffer pool | Thấp | Baseline cache-friendly |
| B | Dataset đại diện | Thấp | Baseline workload thật |
| C | Dataset đại diện | Tăng dần 1x, 2x, 4x | Tìm vùng latency bắt đầu tăng |
| D | Dataset đại diện, key skew | Tải mục tiêu | Đo hot-key contention |
| E | Dataset lớn hơn buffer pool | Tải mục tiêu | Đo disk-bound behavior |
| F | Dataset đại diện | Spike ngắn | Đo khả năng hấp thụ burst và phục hồi |
| G | Dataset đại diện | Tải ổn định dài | Soak test và phát hiện suy giảm theo thời gian |

Mỗi lần chỉ thay một yếu tố khi so sánh, ví dụ index A/B hoặc `innodb_buffer_pool_size`. Nếu đồng thời thay index, số worker và buffer pool, sẽ khó biết yếu tố nào tạo ra khác biệt.

Lặp lại benchmark nhiều lần sau khi khôi phục cùng trạng thái dữ liệu và cache theo kịch bản. Báo cáo median của các lần chạy cùng phân vị trong từng lần, đồng thời giữ lại độ biến động giữa các lần chạy. Một lần chạy may mắn không đủ để quyết định cấu hình production.

## 15. Đọc kết quả và tìm bottleneck

| Dấu hiệu | Khả năng cần kiểm tra |
|---|---|
| Throughput tăng, p95 ổn định | Hệ thống còn headroom trong vùng tải hiện tại |
| Throughput đi ngang, p95/p99 tăng nhanh | CPU, I/O, lock hoặc queue đã bão hòa |
| CPU cao, disk thấp, query nhiều rows examined | Query plan, scan, join, sort hoặc concurrency CPU-bound |
| I/O latency cao và buffer pool physical reads tăng | Working set lớn, cache miss hoặc storage chậm |
| Lock wait/deadlock tăng | Hot row, transaction dài, thứ tự cập nhật hoặc index chưa phù hợp |
| Pool wait tăng nhưng MySQL statement time thấp | Connection pool thiếu connection hoặc connection bị giữ quá lâu |
| Client dropped iterations tăng | Load generator không phát đủ tốc độ hoặc server không nhận kịp offered load |
| Replica lag tăng trong khi primary throughput tốt | Applier, network hoặc replica resource là bottleneck |
| Latency tăng dần trong soak test | Leak, queue tích lũy, purge/checkpoint, memory hoặc disk pressure |

Đừng kết luận chỉ từ một metric. Ví dụ CPU cao có thể là do query scan, compression, encryption hoặc quá nhiều thread; cần digest, execution plan và OS metric để xác nhận.

## 16. Những sai lầm làm benchmark mất giá trị

- **Dataset quá nhỏ:** tất cả page nằm trong cache, không phản ánh kích thước production.
- **Dữ liệu phân bố đều giả tạo:** không có hot key hoặc skew như workload thật.
- **Chỉ chạy một query:** không tính chi phí đọc/ghi hỗn hợp và index maintenance.
- **Bắt đầu đo ngay:** warm-up, connection creation và JIT làm méo kết quả steady-state.
- **Chỉ báo cáo average:** che tail latency và các request chậm.
- **Không ghi offered load:** không biết server xử lý tải nào hay load generator đã tự giảm tải.
- **Coordinated omission:** bỏ qua thời gian lẽ ra request phải được phát trong lúc hệ thống chậm.
- **Load generator quá yếu:** CPU/network phía client bão hòa trước database.
- **Thay nhiều biến cùng lúc:** không xác định được nguyên nhân thay đổi.
- **Không đo lỗi và retry:** throughput có thể trông cao dù request thất bại hoặc bị thực hiện lặp.
- **Không ghi trạng thái cache:** so sánh cold run với warm run như thể tương đương.
- **Benchmark trên production không kiểm soát:** gây ảnh hưởng người dùng và làm kết quả không thể lặp lại.

## 17. Báo cáo benchmark có thể tái lập

Một báo cáo nên có đủ thông tin để người khác chạy lại và hiểu giới hạn của kết quả:

1. Mục tiêu, SLO và câu hỏi benchmark.
2. Topology, MySQL version, phần cứng, storage và cấu hình server.
3. Dataset: số dòng, dung lượng, index, cardinality, skew và cách tạo.
4. Workload: loại transaction, tỷ lệ read/write, phân bố tham số và isolation level.
5. Load model: closed-loop/open-loop, offered rate, concurrency và số load generator.
6. Các pha baseline, warm-up, ramp-up, steady-state, spike/soak và cool-down.
7. p50, p95, p99, max, throughput thành công, error rate và dropped iterations.
8. CPU, RAM, disk IOPS/latency, buffer pool, lock wait, redo và replication lag.
9. Execution plan/digest quan trọng và các thay đổi đã thử.
10. Số lần lặp, biến động kết quả, giới hạn và kết luận vận hành.

Ví dụ bảng kết quả:

| Kịch bản | Offered req/s | Completed req/s | p50 | p95 | p99 | Error rate |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 100 | 100 | 12 ms | 28 ms | 45 ms | 0.00% |
| Tải mục tiêu | 300 | 298 | 20 ms | 85 ms | 190 ms | 0.05% |
| Gần bão hòa | 600 | 430 | 34 ms | 620 ms | 1.8 s | 2.4% |

Các con số trên chỉ minh họa cách trình bày. Khi completed throughput thấp hơn offered load, phải xem queue, dropped iterations, timeout và tài nguyên để xác định request bị chậm hay bị loại.

## 18. Tình huống thực hành

Một API Spring Boot phục vụ lịch sử đơn hàng. Production có 20 triệu đơn, 2 triệu customer, phần lớn request đọc 50 đơn gần nhất; 20% customer tạo 70% traffic. Mỗi lần tạo đơn ghi một order và vài order item. Yêu cầu là duy trì p95 dưới 250 ms ở tải 300 request/giây, error rate dưới 0,5%.

**Bước 1 — Tạo dataset.** Sinh 20 triệu đơn với phân bố customer lệch như production, trạng thái và thời gian tạo đa dạng. Tạo order item theo phân bố số dòng mỗi đơn, giữ index và foreign key như schema thật. Ghi lại dung lượng data/index và seed.

**Bước 2 — Xây workload.** Tạo transaction đọc 50 đơn gần nhất theo customer, transaction tạo order cùng items, và một tỷ lệ update trạng thái. Dùng phân bố customer sao cho một nhóm key nóng nhận phần lớn request.

**Bước 3 — Baseline và warm-up.** Chạy tải thấp, làm nóng connection pool và working set. Theo dõi buffer pool physical reads, throughput và latency cho tới khi ổn định. Lưu riêng kết quả cold-start nếu đó cũng là yêu cầu.

**Bước 4 — Ramp-up.** Tăng arrival rate theo các mức 100, 200, 300, 400 và 500 request/giây. Giữ mỗi mức đủ lâu để queue và cache đạt trạng thái quan sát được. Ghi offered/completed rate, p50/p95/p99, error và dropped iterations.

**Bước 5 — Tìm bottleneck.** Nếu p99 tăng và digest cho thấy truy vấn lịch sử đọc nhiều hàng, xem `EXPLAIN ANALYZE` và index. Nếu lock wait tăng ở bước tạo đơn, kiểm tra hot customer, thứ tự ghi và transaction duration. Nếu pool wait cao nhưng DB statement nhanh, xem pool size và thời gian giữ connection.

**Bước 6 — Đo lại sau thay đổi.** Thay một yếu tố, chẳng hạn index hoặc batch insert, rồi chạy lại cùng dataset, seed, load profile và warm-up. So sánh cả read latency, write latency, throughput và dung lượng index.

**Bước 7 — Soak test.** Giữ tải 300 request/giây trong thời gian dài, theo dõi p95/p99, error, memory, redo, purge, disk và replica lag. Chỉ kết luận đạt SLO khi kết quả ổn định và có headroom phù hợp.

## 19. Checklist trước khi công bố kết quả benchmark

- [ ] Mục tiêu, SLO và ranh giới latency đã được xác định.
- [ ] Dataset có kích thước, cardinality, skew, hot key và working set đại diện.
- [ ] Schema, index, constraint, SQL mode và MySQL version giống môi trường mục tiêu.
- [ ] Workload mô phỏng tỷ lệ read/write, transaction boundary và phân bố tham số thực tế.
- [ ] Load generator đủ tài nguyên và có thể tạo offered load đã định.
- [ ] Đã ghi rõ closed-loop hay open-loop và kiểm tra coordinated omission.
- [ ] Warm-up được tách khỏi steady-state; cold-start được đo riêng nếu cần.
- [ ] Đã chạy baseline, ramp-up, steady-state và spike/soak theo mục tiêu.
- [ ] Có p50, p95, p99, throughput, error rate, timeout và dropped iterations.
- [ ] Percentile được tính từ mẫu/histogram hợp nhất, không lấy trung bình percentile của worker.
- [ ] Có số mẫu và thời gian đo đủ để phần đuôi latency có ý nghĩa.
- [ ] Đã theo dõi CPU, RAM, I/O, buffer pool, lock, redo, connection và replication.
- [ ] Đã lưu execution plan, statement digest và cấu hình thay đổi.
- [ ] Đã lặp lại với cùng seed và trạng thái cache có kiểm soát.
- [ ] Báo cáo nêu giới hạn, độ biến động và điều kiện không được kiểm thử.

Benchmark MySQL đáng tin cậy phải mô phỏng dữ liệu và hành vi truy cập, không chỉ tạo thật nhiều kết nối. Tách warm-up khỏi cửa sổ đo, kiểm soát offered load, báo cáo p50/p95/p99 cùng throughput và error rate, rồi đối chiếu với metric InnoDB giúp xác định đúng điểm bão hòa. Khi dữ liệu, workload, cấu hình và phương pháp đo được ghi lại đầy đủ, kết quả mới có thể so sánh giữa các lần tối ưu và hỗ trợ quyết định vận hành.

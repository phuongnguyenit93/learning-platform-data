# Xuất metric, thiết lập cảnh báo và mức hiệu năng cơ sở

Một hệ thống MySQL có thể vẫn trả lời kết nối nhưng đang suy giảm: số phiên chờ tăng, truy vấn chậm dần, buffer pool phải đọc đĩa nhiều hơn, replication tụt lại hoặc dung lượng đĩa sắp cạn. Muốn phát hiện các thay đổi đó trước khi người dùng báo lỗi, đội vận hành cần biến trạng thái nội bộ của MySQL và máy chủ thành metric có thể thu thập, lưu trữ, trực quan hóa và cảnh báo.

Bài học này đặt việc quan sát trong phạm vi vận hành MySQL: chọn nguồn metric, hiểu đúng loại dữ liệu, xuất metric bằng exporter, xây dashboard, đặt cảnh báo và xác lập mức hiệu năng cơ sở (baseline). Ví dụ sử dụng MySQL 8.0/8.4 và mô hình Prometheus; tên metric cụ thể có thể thay đổi theo phiên bản MySQL, phiên bản exporter và collector được bật. Trước khi đưa quy tắc vào production, hãy đối chiếu endpoint /metrics thực tế của môi trường.

## 1. Kết quả cần đạt

Sau bài học, người học có thể:

- Mô tả đường đi từ instrumentation trong MySQL đến hệ thống time-series và cảnh báo.
- Phân biệt counter, gauge và histogram; biết khi nào cần lấy tốc độ thay đổi thay vì đọc giá trị tích lũy.
- Chọn metric phản ánh khả dụng, tải, độ trễ, lỗi và mức sử dụng tài nguyên.
- Dùng Performance Schema, sys schema và global status để điều tra metric.
- Cấu hình tài khoản giám sát có quyền tối thiểu và triển khai MySQL exporter an toàn.
- Tạo dashboard theo góc nhìn dịch vụ, database, InnoDB và hệ điều hành.
- Viết cảnh báo có cửa sổ thời gian, mức độ nghiêm trọng và hành động xử lý rõ ràng.
- Thiết lập baseline theo workload, thời gian trong ngày và xu hướng tăng trưởng.

## 2. Kiến trúc thu thập metric

Một pipeline quan sát metric thường có sáu thành phần:

1. **Nguồn dữ liệu**: MySQL status variables, Performance Schema, sys schema, trạng thái replication và metric của hệ điều hành.
2. **Exporter/collector**: đọc các nguồn trên, chuẩn hóa thành metric và công bố endpoint để hệ thống giám sát lấy dữ liệu.
3. **Scraper**: Prometheus hoặc nền tảng tương đương định kỳ gọi endpoint của exporter.
4. **Kho time-series**: lưu mẫu metric theo timestamp và các nhãn như instance, job, environment.
5. **Dashboard và truy vấn**: Grafana hoặc giao diện tương đương hiển thị xu hướng, tỷ lệ và tương quan.
6. **Alerting và xử lý sự cố**: đánh giá điều kiện, gom nhóm thông báo, chuyển đến người trực và liên kết runbook.

Với Prometheus, mô hình phổ biến là pull: exporter mở HTTP endpoint, Prometheus chủ động scrape. Exporter không cần tự gửi từng mẫu metric vào Prometheus. Cách tổ chức này giúp Prometheus quản lý chu kỳ lấy dữ liệu, nhãn mục tiêu và trạng thái scrape.

~~~mermaid
flowchart LR
    A[MySQL Server] --> B[mysql exporter]
    C[Node exporter] --> D[Prometheus]
    B --> D
    D --> E[Time-series]
    E --> F[Grafana dashboard]
    E --> G[Alert rules]
    G --> H[Alertmanager]
    H --> I[On-call / Runbook]
~~~

MySQL exporter và node exporter quan sát hai lớp khác nhau. MySQL exporter cung cấp trạng thái database như số kết nối, truy vấn, InnoDB và replication. Node exporter cung cấp CPU, RAM, filesystem, network và disk I/O của máy chạy MySQL. Chỉ nhìn metric database có thể bỏ sót nguyên nhân ở hệ điều hành; chỉ nhìn CPU và RAM cũng không giải thích được truy vấn nào đang chậm.

Không nên coi một dashboard là toàn bộ hệ thống quan sát. Metric cho biết điều gì đang thay đổi; log cho biết sự kiện đã xảy ra; trace hoặc APM cho biết một request đi qua những thành phần nào. Với MySQL, slow query log và Performance Schema thường bổ sung ngữ cảnh mà metric tổng hợp không thể hiện.

## 3. Nguồn metric bên trong MySQL

### 3.1. Global status và system variables

<code>SHOW GLOBAL STATUS</code> trả về các bộ đếm và trạng thái của server. Có thể đọc một số giá trị bằng:

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
  'Uptime',
  'Threads_connected',
  'Threads_running',
  'Max_used_connections',
  'Connections',
  'Aborted_connects',
  'Questions',
  'Queries',
  'Slow_queries',
  'Created_tmp_tables',
  'Created_tmp_disk_tables',
  'Innodb_buffer_pool_read_requests',
  'Innodb_buffer_pool_reads',
  'Innodb_row_lock_waits',
  'Innodb_row_lock_time',
  'Innodb_log_waits'
);
~~~

Trên các phiên bản có Performance Schema, có thể truy vấn <code>performance_schema.global_status</code> và <code>performance_schema.global_variables</code>. Đây là nguồn thuận tiện cho công cụ tự động hóa. <code>SHOW GLOBAL VARIABLES</code> hoặc <code>performance_schema.global_variables</code> giúp lấy cấu hình như <code>max_connections</code>, <code>innodb_buffer_pool_size</code> và <code>slow_query_log</code>.

Không phải mọi status variable đều có cùng ngữ nghĩa. <code>Threads_connected</code> là số phiên hiện đang kết nối, vì vậy nó là gauge. <code>Connections</code> là số lần client thử kết nối kể từ khi server khởi động, vì vậy nó là counter. <code>Uptime</code> là thời gian server đã chạy. Đọc một counter đơn lẻ không cho biết tải hiện tại; cần tính tốc độ tăng của nó trong một cửa sổ thời gian.

### 3.2. Performance Schema

Performance Schema ghi nhận hoạt động bên trong server: statement, wait event, table I/O, file I/O, lock, memory và thread. Nó cho phép trả lời những câu hỏi sâu hơn status tổng quát:

- Digest SQL nào tiêu thụ tổng thời gian lớn nhất?
- Bảng nào có nhiều lần đọc hoặc ghi nhất?
- Thread đang chờ loại tài nguyên nào?
- File nào có độ trễ I/O cao?
- Có metadata lock đang chặn DDL hay không?

Một số bảng đáng biết:

| Bảng Performance Schema | Mục đích |
|---|---|
| <code>events_statements_summary_by_digest</code> | Tổng hợp statement theo digest, số lần thực thi và thời gian |
| <code>events_statements_current</code> | Statement đang chạy tại thời điểm quan sát |
| <code>events_waits_summary_global_by_event_name</code> | Tổng hợp wait theo loại event |
| <code>table_io_waits_summary_by_table</code> | I/O logic theo bảng và index |
| <code>file_summary_by_instance</code> | Hoạt động I/O theo file |
| <code>memory_summary_global_by_event_name</code> | Bộ nhớ được instrument theo event |
| <code>threads</code> | Thread MySQL và trạng thái instrument |
| <code>metadata_locks</code> | Metadata lock đang được giữ hoặc chờ |

Các consumer và instrument có thể được bật/tắt theo cấu hình. Nếu instrument cần thiết đang tắt, truy vấn summary có thể thiếu dữ liệu hoặc chỉ phản ánh một phần hoạt động. Hãy kiểm tra trạng thái trước khi kết luận rằng server không có wait hoặc statement:

~~~sql
SELECT NAME, ENABLED, TIMED
FROM performance_schema.setup_instruments
WHERE NAME LIKE 'statement/%'
   OR NAME LIKE 'wait/io/%'
ORDER BY NAME
LIMIT 30;

SELECT NAME, ENABLED
FROM performance_schema.setup_consumers
ORDER BY NAME;
~~~

Bật instrument rộng có thể tạo thêm overhead và làm tăng dữ liệu nội bộ. Chọn đúng nhóm cần quan sát, đo tác động trên môi trường thử nghiệm và áp dụng theo chính sách vận hành của hệ thống.

### 3.3. sys schema

sys schema cung cấp view dễ đọc dựa trên Performance Schema. Một số view hữu ích:

- <code>sys.statement_analysis</code>: statement digest, số lần chạy, latency tổng/trung bình, rows examined, rows sent và temporary table.
- <code>sys.schema_table_statistics</code>: hoạt động đọc/ghi và latency theo bảng.
- <code>sys.io_global_by_file_by_bytes</code>: I/O file theo số byte.
- <code>sys.io_global_by_file_by_latency</code>: I/O file theo latency.
- <code>sys.innodb_lock_waits</code>: thông tin lock wait của InnoDB.
- <code>sys.user_summary</code> và <code>sys.host_summary</code>: hoạt động theo user hoặc host.

Ví dụ tìm statement có tổng latency lớn:

~~~sql
SELECT
  db,
  exec_count,
  total_latency,
  avg_latency,
  rows_examined,
  rows_sent,
  tmp_disk_tables,
  query
FROM sys.statement_analysis
ORDER BY total_latency DESC
LIMIT 10;
~~~

View sys giúp điều tra sau khi metric báo bất thường. Không nên biến toàn bộ nội dung truy vấn, connection ID hoặc từng thread thành nhãn time-series có cardinality cao. Hãy giữ dữ liệu chi tiết trong Performance Schema, slow log hoặc hệ thống truy vấn log; metric chỉ nên giữ nhóm tổng hợp cần thiết.

## 4. Hiểu đúng loại metric

### 4.1. Counter

Counter là giá trị tích lũy, thường chỉ tăng trong vòng đời server và có thể trở về 0 sau restart hoặc reset. Ví dụ: số kết nối đã nhận, số truy vấn, số lần đọc vật lý, số lần lock wait.

Muốn biết hoạt động trong khoảng thời gian, hãy dùng delta hoặc rate:

~~~promql
rate(mysql_global_status_questions[5m])
increase(mysql_global_status_aborted_connects[10m])
~~~

<code>rate</code> ước tính tốc độ tăng mỗi giây và xử lý việc counter reset theo cách phù hợp với chuỗi thời gian. <code>increase</code> ước tính tổng mức tăng trong cửa sổ. Đừng lấy giá trị counter hiện tại làm QPS hoặc số lỗi trong 5 phút.

### 4.2. Gauge

Gauge có thể tăng hoặc giảm. Ví dụ: số kết nối hiện tại, số thread đang chạy, dung lượng bộ nhớ, số transaction đang hoạt động và dung lượng filesystem còn trống.

Gauge thường được quan sát trực tiếp hoặc so với giới hạn:

~~~promql
mysql_global_status_threads_connected
mysql_global_status_threads_running
100 * mysql_global_status_threads_connected
  / mysql_global_variables_max_connections
~~~

Giá trị gauge có thể dao động nhanh. Một cảnh báo chỉ dựa trên một mẫu có thể báo động giả; thường cần điều kiện kéo dài trong một khoảng <code>for</code>.

### 4.3. Histogram và quantile

Histogram chia quan sát thành các bucket để phân tích phân phối, chẳng hạn latency truy vấn. Từ histogram có thể ước tính p95 hoặc p99. Một giá trị trung bình thấp không bảo đảm tail latency tốt: phần lớn request có thể nhanh trong khi một nhóm nhỏ bị chậm nghiêm trọng.

Không phải mọi metric do mysqld_exporter cung cấp đều là histogram latency. Nếu endpoint chỉ có tổng số lần thực thi và tổng thời gian, không thể suy ra p95 chính xác từ hai giá trị đó. Muốn theo dõi phân vị, cần nguồn histogram phù hợp như instrumentation ứng dụng, APM hoặc collector được thiết kế để xuất bucket. Khi so sánh histogram giữa instance, bucket phải tương thích.

## 5. Bộ metric nền tảng cho MySQL

Nên bắt đầu bằng các nhóm metric gắn với triệu chứng dịch vụ, sau đó bổ sung metric nội bộ để giải thích nguyên nhân.

| Nhóm | Metric hoặc nguồn thường dùng | Câu hỏi vận hành |
|---|---|---|
| Khả dụng | <code>up</code> của Prometheus, exporter scrape success, MySQL uptime | Prometheus có scrape được exporter không? Server có vừa restart không? |
| Kết nối | <code>Threads_connected</code>, <code>Threads_running</code>, <code>Max_used_connections</code>, <code>Connections</code>, <code>Aborted_connects</code> | Pool có cạn? Có bão kết nối hoặc lỗi xác thực? |
| Throughput | <code>Questions</code>, <code>Queries</code>, <code>Com_select</code>, <code>Com_insert</code>, <code>Com_update</code>, <code>Com_delete</code> | Lưu lượng và cơ cấu đọc/ghi thay đổi ra sao? |
| Truy vấn chậm | <code>Slow_queries</code>, digest summary, slow query log | Truy vấn chậm tăng do query mix hay do tải? |
| Buffer pool | <code>Innodb_buffer_pool_read_requests</code>, <code>Innodb_buffer_pool_reads</code>, dirty pages và dung lượng buffer pool | Có tăng đọc vật lý hoặc áp lực cache? |
| Lock | <code>Innodb_row_lock_waits</code>, <code>Innodb_row_lock_time</code>, deadlock từ InnoDB status/monitoring | Transaction có tranh chấp dữ liệu? |
| Temporary table | <code>Created_tmp_tables</code>, <code>Created_tmp_disk_tables</code>, sort counters | Truy vấn có tạo nhiều temporary table trên đĩa? |
| Redo/log | <code>Innodb_log_waits</code>, redo/checkpoint metrics theo phiên bản | Ghi dữ liệu có bị nghẽn do log hoặc flush? |
| Replication | Replica status, receiver/applier state, lag và lỗi replication | Replica có theo kịp nguồn? |
| Hệ điều hành | CPU, memory, swap, disk latency, free space, network | Database đang bị giới hạn bởi host hoặc storage? |

Metric cụ thể và tên exporter có thể khác nhau. Hãy kiểm tra mô tả metric, đơn vị, loại counter/gauge và nhãn trong endpoint trước khi viết query. Không suy luận đơn vị chỉ từ tên.

### 5.1. Kết nối và mức bão hòa

- <code>Threads_connected</code>: số client đang kết nối tại thời điểm lấy mẫu.
- <code>Threads_running</code>: số thread không ở trạng thái ngủ; giá trị cao kéo dài có thể phản ánh nhiều truy vấn đang hoạt động hoặc chờ tài nguyên.
- <code>Max_used_connections</code>: đỉnh kết nối đồng thời kể từ khi server khởi động.
- <code>max_connections</code>: giới hạn kết nối cấu hình.
- <code>Connections</code>: số lần client thử kết nối trong vòng đời server.
- <code>Aborted_connects</code>: kết nối thất bại theo định nghĩa của server.

Tỷ lệ <code>Threads_connected / max_connections</code> cho thấy mức dùng giới hạn, nhưng không cho biết pool còn bao nhiêu kết nối hữu ích. Một server có nhiều kết nối idle vẫn có thể thiếu worker hoặc tài nguyên khi tải tăng. Theo dõi đồng thời <code>Threads_running</code>, tỷ lệ timeout, latency ứng dụng và số connection chờ ở pool.

### 5.2. Buffer pool và đọc đĩa

InnoDB buffer pool giữ page dữ liệu và index trong bộ nhớ. <code>Innodb_buffer_pool_read_requests</code> đếm logical read request; <code>Innodb_buffer_pool_reads</code> phản ánh các lần cần đọc page từ đĩa vào buffer pool. Có thể ước tính tỷ lệ cache hit trong một cửa sổ bằng:

<code>1 - (physical reads / logical read requests)</code>

Trong đó phải dùng delta/rate của hai counter trên cùng khoảng thời gian, và bỏ qua phép chia khi mẫu số bằng 0. Tỷ lệ này chỉ là tín hiệu tổng quan: cache hit cao không chứng minh truy vấn nhanh, và cache hit giảm có thể bình thường sau restart hoặc khi workload chuyển sang tập dữ liệu mới.

Đọc cùng với disk read latency, số byte đọc, buffer pool size, dirty page, query mix và working set. Tăng buffer pool chỉ hợp lý khi host còn RAM và dữ liệu cho thấy áp lực cache; không nên thay đổi cấu hình chỉ để làm đẹp một tỷ lệ.

### 5.3. Lock, temporary table và redo

<code>Innodb_row_lock_waits</code> và <code>Innodb_row_lock_time</code> giúp nhận diện tranh chấp row lock. Chúng không thay thế điều tra transaction cụ thể: khi cảnh báo, cần tìm transaction đang giữ lock, thời gian mở transaction, thứ tự truy cập bảng và câu lệnh gây chờ.

<code>Created_tmp_disk_tables</code> tăng nhanh có thể chỉ ra truy vấn cần temporary table trên đĩa. Hãy so sánh với tổng temporary table và throughput truy vấn, rồi kiểm tra digest, sort, group by, join và cấu hình liên quan. Không phải mọi temporary table trên đĩa đều là lỗi.

<code>Innodb_log_waits</code> tăng có thể báo hiệu transaction phải chờ không gian redo log. Đọc cùng redo generation, checkpoint age, write latency và workload ghi. Tên và khả năng thu thập metric redo chi tiết phụ thuộc phiên bản.

### 5.4. Replication

Giám sát replication cần nhiều hơn một con số lag. Tối thiểu cần biết:

- Receiver/I/O thread và applier/SQL thread có đang hoạt động không.
- Có lỗi đọc relay log, áp dụng transaction hoặc kết nối nguồn không.
- Lag có tăng liên tục hay chỉ tăng ngắn khi có burst.
- Có transaction lớn hoặc DDL làm applier bị chặn không.
- Replica có đủ disk, CPU và I/O để theo kịp không.

Trên MySQL 8.0, ưu tiên câu lệnh và cột theo tên mới như <code>SHOW REPLICA STATUS</code> khi phiên bản hỗ trợ; môi trường cũ có thể vẫn dùng tên <code>SLAVE</code>. <code>Seconds_Behind_Source</code>/<code>Seconds_Behind_Master</code> không phải lúc nào cũng là thước đo hoàn hảo, nhất là khi thread dừng, nguồn không gửi event hoặc có sai lệch đồng hồ. Đọc trạng thái thread và lỗi cùng với lag. Metric exporter cho replication có thể đổi tên theo phiên bản, nên phải xác minh trên endpoint.

## 6. Theo dõi chất lượng truy vấn

Metric tổng hợp cho biết số truy vấn hoặc tổng thời gian, nhưng thường không chỉ ra digest nào cần tối ưu. Kết hợp Performance Schema và sys schema để tìm nhóm truy vấn gây tải:

~~~sql
SELECT
  SCHEMA_NAME,
  DIGEST,
  COUNT_STAR,
  ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS total_seconds,
  ROUND(AVG_TIMER_WAIT / 1000000000, 3) AS avg_milliseconds,
  SUM_ROWS_EXAMINED,
  SUM_ROWS_SENT,
  SUM_CREATED_TMP_DISK_TABLES
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
~~~

Timer trong Performance Schema thường được lưu ở đơn vị picosecond; phép đổi ở ví dụ cần được kiểm tra với đơn vị của cột trên phiên bản đang chạy. Dùng <code>sys.statement_analysis</code> khi muốn đọc nhanh, nhưng luôn xem định nghĩa cột và đơn vị trước khi so sánh.

Đừng chỉ xếp hạng theo average latency. Một digest chạy hàng triệu lần với latency trung bình thấp có thể tiêu thụ nhiều thời gian server hơn một truy vấn hiếm nhưng rất chậm. Cần xem ít nhất:

- Số lần thực thi và tổng latency.
- Average latency và phân phối tail latency nếu có nguồn đo.
- Rows examined so với rows sent.
- Temporary table trên đĩa, full scan và sort.
- Thay đổi theo thời gian, schema và phiên bản ứng dụng.

Slow query log là nguồn tốt để xem mẫu câu lệnh thực tế, nhưng phải quản lý dung lượng, quyền truy cập và thông tin nhạy cảm. Cân nhắc ngưỡng <code>long_query_time</code>, cách ghi log và cơ chế rotate. Bật log với ngưỡng quá thấp trên hệ thống tải lớn có thể tạo nhiều I/O và dữ liệu. Performance Schema digest thường giúp gom câu lệnh theo cấu trúc, giảm việc phải lưu từng giá trị literal.

## 7. Xuất metric bằng mysqld_exporter

### 7.1. Tài khoản giám sát

Exporter cần tài khoản riêng, chỉ kết nối từ host hoặc subnet giám sát. Ví dụ dưới đây minh họa cách tạo tài khoản; quyền chính xác phụ thuộc phiên bản exporter và collector đang bật:

~~~sql
CREATE USER 'metrics'@'10.20.30.%'
  IDENTIFIED BY 'REPLACE_WITH_SECRET';

GRANT PROCESS, REPLICATION CLIENT
  ON *.* TO 'metrics'@'10.20.30.%';

GRANT SELECT
  ON performance_schema.* TO 'metrics'@'10.20.30.%';
~~~

Một số collector cần đọc thêm metadata hoặc schema cụ thể. Chỉ cấp quyền bổ sung khi đã xác định collector nào yêu cầu và phạm vi đọc nào cần thiết. Không dùng tài khoản ứng dụng hoặc tài khoản quản trị cho exporter. Đưa mật khẩu vào secret manager hoặc file cấu hình được bảo vệ; không commit secret vào Git, không đặt mật khẩu trên dòng lệnh có thể bị ghi vào process list.

Nếu triển khai theo hướng dẫn exporter yêu cầu quyền <code>SELECT</code> rộng hơn, hãy đánh giá từng collector và thu hẹp phạm vi nếu có thể. Tài khoản giám sát vẫn là một tài khoản truy cập production; phải quản lý vòng đời mật khẩu, TLS, network policy và audit như các tài khoản dịch vụ khác.

### 7.2. Cấu hình kết nối

Một file client option có thể có dạng:

~~~ini
[client]
user=metrics
password=REPLACE_WITH_SECRET
host=127.0.0.1
port=3306
protocol=tcp
~~~

Lưu file với quyền đọc chỉ dành cho user chạy exporter. Nếu exporter chạy trên host khác, dùng địa chỉ MySQL và TLS theo chính sách nội bộ. Không mở port exporter hoặc MySQL ra Internet công cộng.

Chạy exporter bằng service manager hoặc container đã được quản lý. Một cách triển khai phổ biến là exporter lắng nghe HTTP trên port 9104; port, flag và định dạng cấu hình có thể thay đổi giữa các phiên bản. Hãy cố định phiên bản image/binary, đọc release notes và kiểm tra flag hỗ trợ trước khi nâng cấp.

### 7.3. Kiểm tra endpoint

Sau khi khởi động, kiểm tra endpoint từ mạng giám sát:

~~~bash
curl -s http://127.0.0.1:9104/metrics | head
~~~

Tìm metric đại diện và xác minh:

- Endpoint trả HTTP thành công.
- Có metric scrape health và metric database mong đợi.
- Giá trị có đơn vị, loại và nhãn hợp lý.
- Exporter kết nối đúng instance, không phải nhầm môi trường.
- Log exporter không báo thiếu quyền, timeout hoặc lỗi TLS.

Endpoint /metrics có thể tiết lộ tên database, cấu hình hoặc trạng thái vận hành. Giới hạn truy cập bằng firewall, private network, authentication proxy hoặc cơ chế bảo vệ phù hợp. Chỉ expose endpoint trong vùng giám sát tin cậy.

## 8. Cấu hình Prometheus scrape

Ví dụ tối giản trong prometheus.yml:

~~~yaml
scrape_configs:
  - job_name: mysql
    scrape_interval: 15s
    scrape_timeout: 10s
    static_configs:
      - targets:
          - db-a.internal:9104
          - db-b.internal:9104
~~~

<code>scrape_interval</code> là tần suất lấy mẫu; <code>scrape_timeout</code> phải nhỏ hơn hoặc bằng interval. Khoảng 15 giây là ví dụ, không phải mặc định phù hợp cho mọi hệ thống. Tăng tần suất làm tăng chi phí scrape, lưu trữ và xử lý; giảm tần suất có thể bỏ lỡ sự kiện ngắn. Chọn dựa trên tốc độ thay đổi, yêu cầu phát hiện và tải thực tế.

Sau khi cập nhật cấu hình, kiểm tra cấu hình Prometheus và trạng thái target. Một target ở trạng thái DOWN có thể do DNS, route, firewall, exporter dừng, TLS hoặc MySQL chậm khiến exporter timeout. Phân biệt scrape thất bại với MySQL không khả dụng: exporter có thể không truy cập được database dù process exporter vẫn sống.

Nếu chạy nhiều môi trường, thêm nhãn có kiểm soát như <code>environment</code>, <code>region</code>, <code>cluster</code> và <code>role</code>. Dùng nhãn để phân nhóm dashboard và cảnh báo. Không đưa thông tin bí mật, SQL literal, email hoặc ID người dùng vào nhãn.

## 9. Thiết kế metric và nhãn có kiểm soát

Mỗi chuỗi time-series là một metric kết hợp với một tập nhãn. Nếu một nhãn có hàng trăm nghìn giá trị thay đổi liên tục, số chuỗi có thể tăng rất nhanh, gây tốn RAM, CPU, dung lượng và làm truy vấn dashboard chậm.

Nên dùng các nhãn có tập giá trị hữu hạn và ổn định:

- <code>environment</code>: dev, staging, production.
- <code>cluster</code>: tên cụm đã được quản lý.
- <code>instance</code>: hostname hoặc định danh instance ổn định.
- <code>role</code>: primary, replica hoặc vai trò tương đương.
- <code>job</code>: tên nhóm scrape.

Tránh nhãn có cardinality cao hoặc biến động:

- SQL text đầy đủ hoặc literal trong câu lệnh.
- Connection ID, thread ID, transaction ID.
- Request ID, user ID, email hoặc session token.
- Tên file có thể sinh vô hạn theo ngày hoặc request.

Nếu cần điều tra một request cụ thể, dùng log hoặc trace có cơ chế truy vấn phù hợp. Metric nên trả lời câu hỏi tổng hợp và kích hoạt cảnh báo. Với digest SQL, chỉ xuất nhóm top-N hoặc thống kê đã giới hạn cardinality; cân nhắc hash digest và không gắn nội dung query thô làm label.

Đặt retention theo nhu cầu điều tra và chi phí. Dữ liệu độ phân giải cao hữu ích khi phân tích sự cố gần thời điểm xảy ra; dữ liệu dài hạn có thể downsample hoặc giữ dưới dạng recording rule. Đừng tăng retention mà chưa tính cardinality, số instance, scrape interval và dung lượng dự kiến.

## 10. Dashboard vận hành

Dashboard cần giúp người trực trả lời nhanh: dịch vụ có khỏe không, tải thay đổi thế nào, tài nguyên nào đang bão hòa và sự cố bắt đầu từ lúc nào.

Một dashboard MySQL thực dụng có thể chia thành các hàng:

| Hàng | Biểu đồ | Cách đọc |
|---|---|---|
| Dịch vụ | Target up, uptime, restart, replication role | Xác định instance còn được scrape và có vừa khởi động lại |
| Tải | QPS, read/write rate, connections, threads running | So sánh tải hiện tại với baseline cùng khung giờ |
| Độ trễ | Query latency, application DB latency, p95/p99 nếu có | Tìm tail latency và thời điểm bắt đầu tăng |
| InnoDB | Buffer pool reads, dirty pages, redo/log waits, row lock waits | Tìm áp lực cache, ghi và tranh chấp |
| Truy vấn | Slow query rate, digest top-N, rows examined | Tìm nhóm truy vấn tiêu thụ tài nguyên |
| Replication | Thread state, lag, apply rate, error | Phát hiện replica không theo kịp hoặc đã dừng |
| Host | CPU, RAM, swap, disk latency, free space, network | Phân biệt nghẽn database và nghẽn hạ tầng |

Đồng bộ timezone và cách hiển thị thời gian giữa dashboard, MySQL, exporter và log. Đánh dấu thời điểm deploy, thay đổi cấu hình, backup, DDL và failover. Annotation giúp liên kết một bước thay đổi với biến động metric.

Panel nên có đơn vị, legend rõ, khoảng thời gian mặc định hợp lý và link tới runbook. Không đặt quá nhiều panel chỉ vì metric tồn tại. Một panel không gắn với câu hỏi vận hành hoặc quyết định cụ thể thường gây nhiễu.

## 11. Nguyên tắc thiết lập cảnh báo

Một alert tốt mô tả triệu chứng có ý nghĩa đối với dịch vụ, kéo dài đủ lâu để loại nhiễu và có hành động tiếp theo. Alert không nên chỉ báo rằng một metric đã vượt một con số tùy ý.

Trước khi tạo alert, xác định:

1. **Tác động**: người dùng, giao dịch hoặc mục tiêu dịch vụ nào bị ảnh hưởng?
2. **Tín hiệu**: metric nào phản ánh tác động đáng tin cậy?
3. **Điều kiện**: ngưỡng, cửa sổ đánh giá và thời gian duy trì là bao lâu?
4. **Mức độ**: critical, warning hay thông tin?
5. **Hành động**: người nhận cần kiểm tra gì trước tiên?
6. **Phạm vi**: một instance, một cụm hay toàn bộ dịch vụ?

Ưu tiên cảnh báo theo triệu chứng như database không thể phục vụ request, latency ứng dụng tăng, connection pool cạn, replication vượt giới hạn nghiệp vụ hoặc disk sắp đầy. Metric nguyên nhân như buffer pool hit ratio giảm thường là cảnh báo hỗ trợ điều tra, trừ khi đã chứng minh nó gắn trực tiếp với sự cố.

### 11.1. Cửa sổ thời gian và độ trễ scrape

Điều kiện <code>for</code> yêu cầu biểu thức đúng liên tục trong một khoảng thời gian trước khi alert firing. Chọn khoảng này dựa trên thời gian scrape, độ dài sự kiện có hại và thời gian phản ứng mong muốn. Cảnh báo availability có thể cần phản ứng nhanh hơn cảnh báo tăng dần của dung lượng.

Nếu cửa sổ truy vấn ngắn hơn nhiều so với scrape interval, kết quả có thể thiếu mẫu hoặc dao động. Nếu <code>for</code> quá dài, cảnh báo đến muộn. Nếu quá ngắn, các burst bình thường tạo nhiều thông báo. Kiểm tra rule với dữ liệu lịch sử trước khi bật paging.

### 11.2. Phân loại mức độ

- **Critical**: dịch vụ không khả dụng, lỗi ảnh hưởng trực tiếp đến giao dịch hoặc nguy cơ mất khả năng phục vụ trong thời gian ngắn. Cần người trực phản ứng ngay.
- **Warning**: xu hướng bão hòa hoặc suy giảm có khả năng trở thành sự cố nếu tiếp tục. Cần điều tra trong giờ làm việc hoặc theo SLA đã thống nhất.
- **Info**: thay đổi vận hành cần ghi nhận, không cần paging.

Không gán critical cho mọi cảnh báo metric. Nếu mỗi lần vượt ngưỡng đều đánh thức người trực, đội vận hành sẽ mất khả năng phân biệt tín hiệu quan trọng. Dùng grouping, inhibition và deduplication trong Alertmanager để giảm thông báo lặp.

## 12. Ví dụ Prometheus alert rules

Ví dụ sau minh họa cú pháp và tư duy. Tên metric <code>mysql_global_status_*</code> và <code>mysql_global_variables_*</code> là dạng thường gặp ở mysqld_exporter; cần kiểm tra đúng tên trong môi trường thực tế.

~~~yaml
groups:
  - name: mysql-availability
    rules:
      - alert: MySQLExporterScrapeFailed
        expr: up{job="mysql"} == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Không scrape được MySQL exporter"
          description: "Kiểm tra exporter, mạng, target và trạng thái MySQL."

  - name: mysql-capacity
    rules:
      - alert: MySQLConnectionsNearLimit
        expr: |
          100 *
          mysql_global_status_threads_connected
          / mysql_global_variables_max_connections > 85
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "MySQL dùng gần hết giới hạn kết nối"
          description: "Kiểm tra pool, connection leak và xu hướng Threads_running."

  - name: mysql-errors
    rules:
      - alert: MySQLAbortedConnectionsIncreasing
        expr: increase(mysql_global_status_aborted_connects[10m]) > 20
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Số kết nối MySQL thất bại tăng"
          description: "Kiểm tra lỗi xác thực, timeout, network và log server."
~~~

Rule exporter scrape failed không chứng minh MySQL đã dừng. Nó chỉ cho biết Prometheus không lấy được endpoint. Cần một tín hiệu độc lập hoặc probe kết nối database để phân biệt exporter, network và server.

### 12.1. Theo dõi tốc độ truy vấn và slow query

~~~promql
rate(mysql_global_status_questions[5m])
rate(mysql_global_status_slow_queries[5m])
~~~

Hai biểu thức trên thích hợp để vẽ xu hướng. Muốn cảnh báo, hãy so với baseline hoặc mục tiêu dịch vụ và kết hợp với latency/error rate. Một đợt tăng QPS có thể là chiến dịch hợp lệ; slow query tăng nhưng không ảnh hưởng latency có thể chỉ là thay đổi workload.

### 12.2. Theo dõi lock wait

~~~promql
rate(mysql_global_status_innodb_row_lock_waits[5m])
rate(mysql_global_status_innodb_row_lock_time[5m])
~~~

Đây là tín hiệu về tốc độ phát sinh lock wait và thời gian lock wait tích lũy. Đơn vị của metric time phụ thuộc exporter. Xác minh unit trước khi đặt ngưỡng. Khi cảnh báo firing, dùng <code>sys.innodb_lock_waits</code>, transaction đang mở và process list để xác định blocker.

### 12.3. Buffer pool read pressure

Có thể tính tỷ lệ đọc vật lý trên logical read bằng recording rule, sau khi xác nhận tên metric và counter:

~~~yaml
groups:
  - name: mysql-derived
    rules:
      - record: mysql:innodb_physical_reads_per_logical_read:ratio_rate5m
        expr: |
          rate(mysql_global_status_innodb_buffer_pool_reads[5m])
          /
          clamp_min(
            rate(mysql_global_status_innodb_buffer_pool_read_requests[5m]),
            1
          )
~~~

Đây là tỷ lệ gần đúng của read cần lấy từ storage trên tổng logical read request. Đừng biến nó thành cảnh báo critical độc lập. Hãy liên hệ với disk latency, throughput, query latency, working set và sự kiện restart. <code>clamp_min</code> tránh chia cho 0 nhưng không làm cho mẫu số nhỏ trở thành dữ liệu có ý nghĩa; dashboard nên xử lý giai đoạn thiếu dữ liệu riêng.

### 12.4. Không cảnh báo trên một metric đơn lẻ khi thiếu ngữ cảnh

Ví dụ: <code>Threads_running</code> tăng có thể do tải tăng hợp lệ, truy vấn chậm, lock wait hoặc CPU bị giới hạn. <code>Created_tmp_disk_tables</code> tăng có thể do một báo cáo định kỳ. <code>Seconds_Behind_Source</code> tăng ngắn có thể được phục hồi tự động. Kết hợp nhiều tín hiệu, đặt cửa sổ thời gian và xác định tác động trước khi paging.

## 13. Xác lập mức hiệu năng cơ sở (baseline)

Baseline là mô tả định lượng về hành vi bình thường của hệ thống trong một workload và điều kiện đã biết. Nó giúp phân biệt biến động bình thường với suy giảm, ước lượng capacity và đánh giá hiệu quả sau khi thay đổi.

Một baseline có giá trị cần ghi rõ:

- Phiên bản MySQL, cấu hình chính, loại instance, CPU/RAM/storage và topology.
- Kích thước dữ liệu, index, buffer pool và tốc độ tăng dữ liệu.
- Phiên bản ứng dụng, connection pool, query mix và số client.
- Throughput, latency, error rate, lock wait và replication.
- Thời điểm đo, múi giờ, ngày thường/cuối tuần, batch hoặc giờ cao điểm.
- Các thay đổi triển khai, backup, batch job và maintenance trong thời gian đo.

Đừng dùng một lần benchmark ngắn làm baseline production. Đo trong nhiều chu kỳ nghiệp vụ, gồm giờ cao điểm và các job định kỳ. Lấy dữ liệu đủ dài để bao phủ biến động ngày/tuần nhưng vẫn tách các giai đoạn có thay đổi kiến trúc hoặc workload.

### 13.1. Các mức thống kê

Với metric liên tục, ghi nhận:

- Trung vị (p50) để mô tả mức điển hình.
- p95 và p99 để mô tả tail latency hoặc tail utilization.
- Min/max để phát hiện biên bất thường, nhưng không dùng riêng chúng làm mục tiêu.
- Tốc độ tăng theo thời gian cho counter.
- Mức cao nhất theo cửa sổ nghiệp vụ, ví dụ 5 phút hoặc 1 giờ.

Với latency, ưu tiên phân phối từ ứng dụng hoặc nguồn histogram. Nếu chỉ có average, ghi rõ giới hạn của dữ liệu. Average có thể che giấu một nhóm request chậm.

### 13.2. So sánh cùng điều kiện

So sánh QPS của 10 giờ sáng thứ Hai với baseline cùng khung giờ có ý nghĩa hơn so với so với trung bình cả tuần. Khi query mix thay đổi, cùng QPS không có nghĩa cùng chi phí. Một workload đọc theo index khác với workload full scan hoặc ghi nhiều transaction.

Khi so sánh trước/sau deploy, giữ nguyên khoảng thời gian và tải nếu có thể; ghi nhận khác biệt về dataset, cache warm-up, số replica và cấu hình. Nếu không thể giữ nguyên tải, chuẩn hóa theo request, transaction hoặc số hàng xử lý.

### 13.3. Baseline và capacity

Capacity không chỉ là mức CPU trung bình. Hãy xác định điểm mà latency, error rate hoặc queue bắt đầu tăng nhanh khi tải tăng. Thực hiện load test có kiểm soát để tìm giới hạn thực tế, đồng thời quan sát CPU, disk latency, memory, connection pool, lock và replication.

Đặt headroom cho burst, failover và rolling maintenance. Primary có thể phải nhận thêm tải khi replica được nâng cấp hoặc khi một node ngừng hoạt động. Không vận hành sát giới hạn chỉ vì benchmark hiện tại vẫn đạt throughput.

### 13.4. Ví dụ baseline

Giả sử một hệ thống OLTP có giờ cao điểm từ 09:00 đến 11:00. Baseline sau khi đo nhiều ngày có thể ghi:

| Chỉ số | Baseline giờ cao điểm | Cách sử dụng |
|---|---:|---|
| QPS | 2.000–2.600 | So sánh cùng khung giờ và query mix |
| Application DB latency p95 | 35–55 ms | Tín hiệu trải nghiệm người dùng |
| Threads_connected | 180–240 | Theo dõi pool và headroom |
| Threads_running | 12–28 | Đọc cùng CPU và latency |
| Connection limit | 600 | Đặt ngưỡng warning theo xu hướng |
| Replica lag | thường dưới 2 giây | Đánh giá theo yêu cầu đọc replica |
| Disk utilization | 45–65% | Đọc cùng disk latency và queue |

Các số trên chỉ là dữ liệu giả định để minh họa cách ghi baseline, không phải ngưỡng khuyến nghị cho mọi MySQL. Mỗi hệ thống phải đo lại theo phần cứng, query mix, SLO và topology thực tế.

## 14. Chọn ngưỡng cảnh báo từ baseline và SLO

Một cách đặt ngưỡng tốt là kết hợp ba lớp:

1. **SLO hoặc mục tiêu nghiệp vụ**: ví dụ tỷ lệ request thành công, latency p95/p99, thời gian đồng bộ replica tối đa.
2. **Baseline**: hành vi thường thấy theo thời gian và workload.
3. **Giới hạn kỹ thuật**: max_connections, dung lượng đĩa, memory, giới hạn replication hoặc giới hạn dịch vụ.

Ngưỡng cần có khoảng dự phòng trước khi chạm giới hạn cứng. Ví dụ, cảnh báo connection utilization ở 80–85% có thể là điểm bắt đầu để điều tra, nhưng cần kiểm chứng theo pool, burst và thời gian mở rộng. Cảnh báo disk free phải tính tốc độ tăng dữ liệu và thời gian cần để cấp thêm dung lượng, không chỉ dùng một phần trăm chung.

Phân biệt alert theo mức hiện tại và alert theo tốc độ suy giảm. Filesystem còn 30% có thể ổn nếu tăng chậm; còn 30% nhưng tăng 5% mỗi giờ có thể cần xử lý ngay. Với counter, dùng tốc độ tăng; với gauge, xem mức, xu hướng và dự báo phù hợp.

Không tự động thay đổi <code>max_connections</code>, buffer pool hoặc redo log chỉ để làm alert biến mất. Thay đổi cấu hình phải có giả thuyết, đánh giá RAM/CPU/I/O, kế hoạch rollback và xác minh sau thay đổi.

## 15. Kiểm chứng chất lượng cảnh báo

Trước khi paging production:

- Chạy rule trên dữ liệu lịch sử để xem thời điểm firing và số lần false positive.
- Kiểm tra trường hợp thiếu metric, server restart và counter reset.
- Xác minh nhãn instance/cluster để thông báo đến đúng đội.
- Kiểm tra Alertmanager grouping, inhibition, deduplication và route.
- Đưa link dashboard, runbook và truy vấn kiểm tra vào annotation.
- Thử một sự kiện có kiểm soát trên staging hoặc môi trường diễn tập.
- Định kỳ rà soát alert không còn hữu ích hoặc không có người chịu trách nhiệm.

Mỗi alert nên có owner, mức độ, điều kiện giải quyết và hướng dẫn xử lý. Alert không có runbook hoặc không có người nhận thường trở thành tiếng ồn.

## 16. Quy trình điều tra khi cảnh báo

Khi có cảnh báo MySQL, đi theo thứ tự từ tác động đến nguyên nhân:

1. Xác định instance, role, cluster, thời điểm bắt đầu và phạm vi người dùng bị ảnh hưởng.
2. Kiểm tra target up, exporter log, MySQL error log và trạng thái kết nối.
3. Đối chiếu application latency/error rate với QPS và connection pool.
4. Kiểm tra CPU, memory, swap, disk latency, filesystem và network.
5. Kiểm tra Threads_running, lock wait, digest SQL, slow log và temporary table.
6. Kiểm tra buffer pool, redo/log wait và I/O.
7. Nếu là replica, kiểm tra receiver/applier, lỗi và tốc độ apply.
8. Ghi nhận thay đổi gần nhất: deploy, DDL, batch, backup, failover hoặc cấu hình.
9. Chọn hành động giảm tác động, ghi lại bằng chứng và theo dõi sau xử lý.

Không vội restart MySQL khi chỉ thấy latency tăng. Restart có thể xóa trạng thái quan sát tạm thời, làm cache lạnh và kéo dài sự cố. Thu thập status, process list, digest, lock wait và log trước khi thực hiện hành động ảnh hưởng đến instance, trừ khi runbook khẩn cấp đã quy định khác.

## 17. Các tình huống thường gặp

### 17.1. Exporter sống nhưng metric MySQL thiếu

Kiểm tra log exporter, tài khoản, quyền trên Performance Schema, collector có bật không và timeout. Endpoint HTTP thành công chỉ chứng minh exporter trả lời; nó không bảo đảm mọi collector đọc database thành công. So sánh metric hiện có với <code>SHOW GLOBAL STATUS</code> và truy vấn Performance Schema bằng tài khoản giám sát.

### 17.2. Prometheus báo target DOWN

Kiểm tra DNS, route, firewall, port exporter, TLS, service state và timeout. Từ host Prometheus thử kết nối endpoint. Nếu exporter đang chạy nhưng MySQL chậm hoặc không truy cập được, kiểm tra log exporter và kết nối database độc lập.

### 17.3. QPS tăng nhưng latency vẫn ổn

Đối chiếu với giờ cao điểm, lịch batch, chiến dịch kinh doanh và query mix. Nếu SLO vẫn đạt, đây có thể là tải bình thường. Theo dõi headroom CPU, connection, disk và replica để phát hiện rủi ro tiếp theo.

### 17.4. Latency tăng nhưng CPU thấp

Xem lock wait, disk latency, fsync, network, metadata lock và thread đang chờ. CPU thấp không có nghĩa database rảnh; thread có thể đang chờ storage, lock hoặc dịch vụ bên ngoài.

### 17.5. Buffer pool hit ratio giảm

Kiểm tra server vừa restart, dataset/working set thay đổi, truy vấn mới, scan lớn và memory pressure. So sánh physical read rate với disk latency và application latency. Không tăng buffer pool trước khi kiểm tra RAM khả dụng và các giới hạn của host.

### 17.6. Replica lag tăng

Kiểm tra trạng thái receiver/applier, lỗi SQL, transaction lớn, DDL, tải ghi trên primary, CPU/I/O của replica và network. Xác định lag tăng đều hay tăng theo burst. Nếu replica phục vụ read traffic, đánh giá stale-read impact trước khi điều hướng traffic.

### 17.7. Alert bắn liên tục sau restart

Counter có thể reset và buffer pool cần warm-up. Dùng <code>rate</code>/<code>increase</code> đúng cách, xử lý giai đoạn thiếu dữ liệu và cân nhắc thời gian ổn định sau restart. Không che mọi alert trong thời gian dài; chỉ trì hoãn những điều kiện đã biết là transient và vẫn giữ kiểm tra availability.

## 18. Thực hành: triển khai metric và cảnh báo cho một MySQL instance

### Bước 1: Lập danh sách câu hỏi vận hành

Với một instance primary, trả lời:

- Có scrape được exporter không?
- Kết nối đã dùng bao nhiêu phần giới hạn?
- QPS và read/write rate thay đổi ra sao?
- Slow query và lock wait có tăng không?
- Buffer pool có phát sinh nhiều physical read?
- CPU, RAM, disk và filesystem còn headroom không?

Chọn một metric cho mỗi câu hỏi, ghi rõ nguồn, loại metric, đơn vị và tần suất thu thập.

### Bước 2: Tạo user và kiểm tra quyền

Tạo tài khoản giám sát riêng theo ví dụ ở mục 7. Đăng nhập bằng đúng tài khoản đó, thử đọc status và các bảng Performance Schema cần thiết. Nếu collector lỗi quyền, xác định collector nào yêu cầu quyền bổ sung trước khi cấp.

### Bước 3: Cài exporter và xác minh endpoint

Triển khai exporter với phiên bản cố định, file credential được bảo vệ và network policy giới hạn truy cập. Gọi /metrics, tìm các metric kết nối, truy vấn và InnoDB. So sánh vài giá trị với <code>SHOW GLOBAL STATUS</code> để xác minh instance và đơn vị.

### Bước 4: Thêm Prometheus target

Khai báo scrape target, kiểm tra cấu hình, reload theo quy trình triển khai và xác minh target UP. Ghi nhận scrape duration, scrape error và số chuỗi time-series được tạo.

### Bước 5: Xây dashboard

Tạo các panel cho availability, QPS, connections, threads running, slow query rate, buffer pool read rate, lock wait, replication và host. Đặt cùng time range để so sánh biến động giữa database và OS.

### Bước 6: Tạo hai alert đầu tiên

Bắt đầu với exporter scrape failed và connection utilization gần giới hạn. Đặt <code>for</code>, severity, summary, description, owner và runbook. Kiểm tra rule với dữ liệu staging hoặc lịch sử trước khi bật paging.

### Bước 7: Thu baseline

Thu thập metric qua nhiều ngày và chu kỳ nghiệp vụ. Ghi lại p50/p95/p99 khi có nguồn phù hợp, QPS, query mix, connection, latency, host utilization và sự kiện triển khai. Chọn ngưỡng cảnh báo từ baseline kết hợp SLO và headroom.

### Bước 8: Diễn tập

Tạo tải thử có kiểm soát hoặc mô phỏng exporter không truy cập được trên staging. Xác nhận alert firing, thông báo đúng người, dashboard có đủ dữ liệu và runbook dẫn tới hành động hữu ích. Sau diễn tập, tắt tải thử và xác minh alert resolved.

## 19. Bài tập tự kiểm tra

1. Vì sao <code>Connections</code> cần dùng <code>rate()</code> còn <code>Threads_connected</code> thường được đọc trực tiếp?
2. Prometheus target UP có chứng minh MySQL hoạt động bình thường không? Giải thích các trường hợp còn thiếu.
3. Vì sao không nên dùng SQL text hoặc connection ID làm label?
4. Nếu QPS tăng gấp đôi nhưng latency và error rate không đổi, cần kiểm tra điều gì trước khi kết luận có sự cố?
5. <code>Innodb_buffer_pool_reads</code> tăng nhanh có đủ để kết luận buffer pool quá nhỏ không?
6. Vì sao average latency không thay thế được p95/p99?
7. Một replica báo lag tăng nhưng applier thread đang dừng vì lỗi SQL. Metric và runbook cần thể hiện những gì?
8. Hãy chọn một alert cho disk capacity. Bạn cần biết tốc độ tăng, headroom và thời gian cấp thêm dung lượng như thế nào?
9. Nếu exporter thiếu metric Performance Schema nhưng status metric vẫn có, bạn sẽ kiểm tra gì?
10. Hãy đề xuất baseline cho một workload có batch job lúc nửa đêm và giờ cao điểm buổi sáng.

## 20. Checklist đưa vào vận hành

- [ ] Metric có nguồn, đơn vị, loại counter/gauge và ý nghĩa được ghi rõ.
- [ ] Exporter chạy bằng tài khoản riêng, quyền tối thiểu và secret được bảo vệ.
- [ ] Endpoint chỉ truy cập được từ mạng giám sát được phép.
- [ ] Prometheus scrape đúng instance, có timeout và interval phù hợp.
- [ ] Dashboard bao gồm database và host; có timezone và annotation triển khai.
- [ ] Không có label chứa SQL literal, ID request hoặc dữ liệu cá nhân.
- [ ] Alert gắn với tác động, có cửa sổ thời gian, severity, owner và runbook.
- [ ] Ngưỡng được so với baseline, SLO và giới hạn kỹ thuật.
- [ ] Counter reset, thiếu dữ liệu, restart và scrape failure đã được xem xét.
- [ ] Đã diễn tập alert và xác minh quy trình thông báo.
- [ ] Có kế hoạch retention, cardinality và rà soát chi phí lưu trữ.

## 21. Tài liệu tham khảo

- [MySQL 8.4 Reference Manual — Server Status Variables](https://dev.mysql.com/doc/refman/8.4/en/server-status-variables.html)
- [MySQL 8.4 Reference Manual — Performance Schema](https://dev.mysql.com/doc/refman/8.4/en/performance-schema.html)
- [MySQL 8.4 Reference Manual — sys Schema](https://dev.mysql.com/doc/refman/8.4/en/sys-schema.html)
- [MySQL 8.4 Reference Manual — Replication Monitoring](https://dev.mysql.com/doc/refman/8.4/en/replication-monitoring.html)
- [Prometheus — Configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)
- [Prometheus — Query functions](https://prometheus.io/docs/prometheus/latest/querying/functions/)
- [Prometheus — Alerting rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
- [Prometheus — Instrumentation practices](https://prometheus.io/docs/practices/instrumentation/)
- [Prometheus Community — mysqld_exporter](https://github.com/prometheus/mysqld_exporter)

Tên collector, metric và quyền MySQL cần được xác minh theo phiên bản exporter đang triển khai. Tài liệu tham khảo ở đây là điểm bắt đầu để kiểm tra hành vi thực tế, không thay thế release notes và cấu hình của môi trường.

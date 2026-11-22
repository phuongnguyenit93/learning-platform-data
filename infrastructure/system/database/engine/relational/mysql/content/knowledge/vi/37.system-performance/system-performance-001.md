# Phân biệt nghẽn CPU, I/O, bộ nhớ, khóa và mạng

Trong module **DATABASE_MYSQL**, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Khi MySQL chậm, biểu hiện ở ứng dụng thường giống nhau: request kéo dài, timeout, hàng đợi tăng và throughput giảm. Tuy nhiên, nguyên nhân có thể nằm ở CPU, thiết bị lưu trữ, bộ nhớ, tranh chấp khóa hoặc đường truyền mạng. Chọn sai lớp nguyên nhân thường dẫn đến thay đổi cấu hình không hiệu quả, thậm chí làm hệ thống mất ổn định hơn.

Bài học này hướng dẫn cách phân biệt năm nhóm bottleneck bằng cách kết hợp số liệu MySQL với số liệu của hệ điều hành và ứng dụng. Mỗi nhóm được xem xét qua dấu hiệu, phép đo, câu lệnh kiểm tra và hướng xử lý. Mục tiêu là xác định tài nguyên nào đang bão hòa hoặc tạo hàng đợi, sau đó kiểm chứng giả thuyết bằng dữ liệu theo cùng một khoảng thời gian.

## 1. Mục tiêu và nguyên tắc chẩn đoán

Sau bài học, người học có thể:

- Phân biệt CPU saturation, storage I/O pressure, memory pressure, lock contention và network bottleneck.
- Thu thập status counter và Performance Schema data phù hợp với từng giả thuyết.
- Đối chiếu số liệu MySQL với CPU, RAM, disk và network metrics của host hoặc container.
- Nhận diện các chỉ số dễ bị hiểu sai, chẳng hạn Threads_running, buffer pool hit ratio hoặc SUM_TIMER_WAIT.
- Tìm statement, file, transaction hoặc kết nối liên quan đến hiện tượng chậm.
- Xây dựng baseline, lấy snapshot theo thời gian và tính delta.
- Chọn biện pháp xử lý theo bằng chứng và xác nhận hiệu quả sau thay đổi.

### 1.1. Bottleneck là tài nguyên giới hạn throughput hoặc latency

Một tài nguyên trở thành bottleneck khi nhu cầu sử dụng tiến gần hoặc vượt năng lực cung cấp, khiến công việc phải chờ. CPU có thể bão hòa, thiết bị lưu trữ có hàng đợi I/O dài, bộ nhớ thiếu khiến hệ điều hành swap, transaction chờ khóa hoặc client chờ dữ liệu qua mạng.

Không phải mọi chỉ số cao đều chứng minh bottleneck:

- CPU cao có thể là workload tăng hợp lý; cần xem run queue, thời gian xử lý và latency.
- Disk throughput cao có thể là thiết bị đang hoạt động hiệu quả; cần xem độ trễ và queue depth.
- Buffer pool hit ratio cao không loại trừ ghi log hoặc flush I/O bị nghẽn.
- Threads_running cao không đồng nghĩa tất cả thread đang tiêu thụ CPU; một số thread có thể đang chờ.
- Socket wait cao không tự chứng minh mạng ngoài host bị lỗi; server có thể đang chờ client đọc kết quả.

Hãy tìm mối liên hệ giữa nhu cầu, hàng đợi, thời gian chờ và tác động lên request.

### 1.2. Đo cùng một cửa sổ thời gian

Một phép so sánh có ý nghĩa cần ghi lại:

- Thời điểm bắt đầu và kết thúc.
- MySQL uptime và thời điểm restart gần nhất.
- Throughput, số kết nối và loại workload.
- CPU, memory, disk latency và network metrics.
- Statement, wait event và transaction nổi bật.
- Deploy, backup, batch job hoặc thay đổi cấu hình trong cùng khoảng đó.

Không so một counter tích lũy từ khi server khởi động với một biểu đồ OS chỉ có dữ liệu trong một phút. Với các counter tích lũy, lấy hai snapshot và tính chênh lệch.

## 2. Quy trình triage tổng quát

Khi nhận báo cáo MySQL chậm, đi theo trình tự sau:

1. Xác nhận phạm vi: một endpoint, một tenant, một câu SQL, mọi kết nối hay toàn bộ instance.
2. Xác nhận thời gian: vấn đề bắt đầu lúc nào, có kéo dài hay chỉ xuất hiện theo đợt.
3. Đo tác động: request latency, timeout, throughput, queue depth và số kết nối.
4. Kiểm tra host: CPU, run queue, RAM, swap, disk latency, IOPS, network errors và retransmissions.
5. Kiểm tra MySQL: Threads_running, connection counters, InnoDB status, Performance Schema waits và statement summaries.
6. Xác định loại chờ nổi bật: CPU execution, file I/O, memory reclaim, lock hoặc socket.
7. Tìm đối tượng cụ thể: statement digest, file instance, transaction, metadata lock hoặc client connection.
8. Đặt giả thuyết có thể kiểm chứng và chọn một phép đo tiếp theo.
9. Chỉ thay đổi một nhóm yếu tố trong một lần thử nếu có thể.
10. So sánh trước và sau trên workload tương đương; rollback nếu kết quả xấu đi.

### 2.1. Sơ đồ định hướng

~~~mermaid
flowchart TD
    A[MySQL chậm hoặc timeout] --> B[Đo latency và throughput]
    B --> C[Đối chiếu CPU, RAM, disk, network]
    C --> D{Tài nguyên nào có hàng đợi hoặc chờ nổi bật?}
    D -->|CPU| E[Top process, run queue, statement digest]
    D -->|Disk I/O| F[Disk latency, IOPS, file summary, InnoDB]
    D -->|Memory| G[Available RAM, swap, OOM, memory summary]
    D -->|Locks| H[Data lock, metadata lock, transaction]
    D -->|Network| I[RTT, retransmit, socket waits, bytes]
    E --> J[Kiểm chứng giả thuyết]
    F --> J
    G --> J
    H --> J
    I --> J
    J --> K[Thay đổi có kiểm soát và đo lại]
~~~

### 2.2. Thu thập trạng thái MySQL ban đầu

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Uptime',
    'Questions',
    'Queries',
    'Threads_connected',
    'Threads_running',
    'Max_used_connections',
    'Connections',
    'Aborted_connects',
    'Bytes_received',
    'Bytes_sent',
    'Innodb_buffer_pool_read_requests',
    'Innodb_buffer_pool_reads',
    'Innodb_data_reads',
    'Innodb_data_writes',
    'Innodb_data_read',
    'Innodb_data_written',
    'Innodb_log_waits',
    'Innodb_row_lock_waits',
    'Innodb_row_lock_time',
    'Innodb_deadlocks'
);
~~~

Một số status variable có thể khác theo phiên bản hoặc storage engine. Nếu một tên không có, kiểm tra danh sách biến của đúng phiên bản. Lưu kết quả cùng timestamp và lấy snapshot thứ hai sau một cửa sổ tải đại diện.

### 2.3. Đừng suy luận từ một snapshot

Threads_running bằng 80 tại một thời điểm không nói được 80 thread đó đang làm gì. Innodb_buffer_pool_reads tăng từ lúc boot cũng không cho biết tốc độ đọc vật lý hiện tại. Bytes_sent lớn có thể chỉ phản ánh server đã chạy lâu.

Với counter tích lũy:

~~~text
delta_counter = counter_moi - counter_cu
rate_per_second = delta_counter / elapsed_seconds
~~~

Nếu server restart, counter bị reset hoặc Performance Schema bị reset trong khoảng đo, không lấy hiệu số trực tiếp. Ghi nhận uptime và reset boundary.

## 3. Phân biệt nghẽn CPU

CPU bottleneck xảy ra khi nhu cầu xử lý CPU cao hơn năng lực sẵn có trong thời gian đủ dài. MySQL có thể phải xử lý nhiều phép join, sort, biểu thức, JSON, mã hóa, kiểm tra điều kiện hoặc số lượng statement quá lớn.

### 3.1. Dấu hiệu thường gặp

- CPU user/system của host duy trì ở mức cao trong lúc latency tăng.
- Run queue tăng và tiến trình mysqld chiếm phần lớn CPU.
- Throughput không tăng dù số thread hoạt động tăng.
- Các câu SQL có nhiều hàng examined, sort, join hoặc biểu thức tốn CPU.
- CPU giảm rõ khi workload SQL giảm, trong khi disk latency và network vẫn bình thường.

CPU cao trong thời gian ngắn chưa đủ để kết luận. Backup nén, replication apply, antivirus hoặc một process khác cũng có thể chiếm CPU.

### 3.2. Kiểm tra ở hệ điều hành Linux

~~~bash
uptime
top -H -p "$(pidof mysqld)"
pidstat -u -p "$(pidof mysqld)" 1
vmstat 1
~~~

- uptime cho biết load average, cần so với số CPU logic.
- top -H hiển thị thread và mức CPU của tiến trình mysqld.
- pidstat theo dõi mức sử dụng CPU theo process.
- vmstat giúp xem run queue, blocked process và CPU breakdown.

Nếu có quyền và công cụ phù hợp, perf top hoặc profiler có thể giúp tìm hàm đang tiêu thụ CPU. Profiling production cần đánh giá overhead và tuân thủ quy trình vận hành.

Trên Windows, dùng Task Manager hoặc Performance Monitor để theo dõi CPU của mysqld, CPU tổng, processor queue length và tiến trình cạnh tranh tài nguyên. Trong container, đối chiếu CPU usage với quota/cpu limit; một container có thể bị throttle dù host còn CPU rảnh.

### 3.3. Đọc số liệu MySQL

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Threads_running',
    'Threads_connected',
    'Questions',
    'Queries',
    'Slow_queries',
    'Created_tmp_tables',
    'Created_tmp_disk_tables',
    'Select_scan',
    'Sort_rows',
    'Sort_merge_passes'
);
~~~

Các biến này là tín hiệu workload, không phải CPU meter. Ví dụ Threads_running đếm thread không ở trạng thái ngủ, bao gồm cả một số thread đang chờ. Cần đối chiếu với CPU của process và wait events.

### 3.4. Tìm statement tiêu thụ thời gian

~~~sql
SELECT
    SCHEMA_NAME,
    DIGEST_TEXT,
    COUNT_STAR,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 2) AS total_elapsed_seconds,
    ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS average_elapsed_seconds,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT,
    SUM_SORT_ROWS,
    SUM_CREATED_TMP_TABLES,
    SUM_CREATED_TMP_DISK_TABLES
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
~~~

SUM_TIMER_WAIT đo thời gian elapsed của statement, không phải CPU time thuần. Thời gian này có thể bao gồm thời gian chờ I/O hoặc lock. Dùng nó để tìm nhóm đáng điều tra, rồi đối chiếu wait events và OS CPU metrics.

### 3.5. Hướng xử lý CPU bottleneck

- Tối ưu query plan để giảm rows examined, join fan-out và sort không cần thiết.
- Thêm hoặc điều chỉnh index sau khi kiểm tra selectivity và chi phí ghi.
- Tránh gọi cùng lookup quá nhiều lần; xem xét batching hoặc cache phù hợp.
- Giảm truy vấn N+1 ở tầng ứng dụng.
- Kiểm tra biểu thức, chuyển kiểu, function và xử lý dữ liệu lớn trong SQL.
- Điều chỉnh concurrency và connection pool nếu quá nhiều truy vấn tranh CPU.
- Tăng CPU hoặc scale instance khi workload hợp lý nhưng vượt năng lực máy.

Không tăng thread hoặc max_connections chỉ vì CPU cao. Nhiều truy vấn đồng thời hơn có thể làm CPU contention nặng thêm.

## 4. Phân biệt nghẽn storage I/O

Storage bottleneck xảy ra khi đọc hoặc ghi dữ liệu, redo log, binary log, temporary file hoặc tablespace phải chờ thiết bị lưu trữ. Throughput có thể cao hoặc thấp; chỉ số quan trọng là độ trễ, hàng đợi, IOPS và loại I/O.

### 4.1. Dấu hiệu thường gặp

- Disk await/latency tăng trong cùng thời điểm MySQL chậm.
- Device queue kéo dài hoặc I/O utilization gần bão hòa.
- MySQL có file I/O waits tăng, đặc biệt ở data file hoặc log file.
- InnoDB phải đọc vật lý thường xuyên do working set không nằm trong buffer pool.
- Flush hoặc redo log chậm khiến transaction commit phải chờ.
- Temporary table trên disk tăng cùng query latency.

Một thiết bị có %util cao chưa chắc là bottleneck trên mọi loại storage; SSD, NVMe, SAN và cloud volume có đặc tính khác nhau. Hãy xem latency và queue depth cùng với giới hạn IOPS/throughput của nền tảng.

### 4.2. Kiểm tra Linux

~~~bash
iostat -xz 1
vmstat 1
pidstat -d -p "$(pidof mysqld)" 1
~~~

iostat -xz cho biết read/write throughput, await, queue và utilization theo thiết bị. pidstat -d giúp xem process có hoạt động I/O. vmstat cho biết blocked process và swap activity.

Trong cloud hoặc container, lấy thêm volume latency, burst balance, IOPS/throughput throttling và host-level storage metrics. Trong Windows, dùng Performance Monitor theo dõi Avg. Disk sec/Read, Avg. Disk sec/Write, Disk Reads/sec, Disk Writes/sec và queue length.

### 4.3. Kiểm tra InnoDB buffer pool

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Innodb_buffer_pool_read_requests',
    'Innodb_buffer_pool_reads',
    'Innodb_data_reads',
    'Innodb_data_writes',
    'Innodb_data_read',
    'Innodb_data_written',
    'Innodb_buffer_pool_pages_dirty',
    'Innodb_buffer_pool_pages_flushed',
    'Innodb_log_waits'
);
~~~

- Innodb_buffer_pool_read_requests: yêu cầu đọc logic từ buffer pool.
- Innodb_buffer_pool_reads: lần phải đọc page từ storage vì page không có trong buffer pool.
- Innodb_data_reads và Innodb_data_writes: số hoạt động đọc/ghi dữ liệu InnoDB.
- Innodb_data_read và Innodb_data_written: lượng byte đọc/ghi tích lũy.
- Innodb_buffer_pool_pages_dirty: page bẩn đang chờ flush.
- Innodb_log_waits: số lần phải chờ do log buffer không thể được ghi tiếp theo cách cần thiết.

Đọc delta của các biến trong cùng cửa sổ. Tỷ lệ buffer pool hit cao không chứng minh toàn bộ I/O ổn định: redo log, flush, binary log, doublewrite hoặc temporary file vẫn có thể nghẽn.

### 4.4. Xem file I/O trong Performance Schema

Nếu file instruments đang được thu thập:

~~~sql
SELECT
    EVENT_NAME,
    FILE_NAME,
    COUNT_READ,
    SUM_NUMBER_OF_BYTES_READ,
    ROUND(SUM_TIMER_READ / 1000000000000, 3) AS read_seconds,
    COUNT_WRITE,
    SUM_NUMBER_OF_BYTES_WRITE,
    ROUND(SUM_TIMER_WRITE / 1000000000000, 3) AS write_seconds
FROM performance_schema.file_summary_by_instance
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
~~~

Bảng file_summary_by_instance tổng hợp hoạt động theo file instance. Kết quả phụ thuộc instruments được bật; thời gian timer là thời gian chờ được đo, không phải CPU time. Có thể nhóm theo EVENT_NAME để xem loại file nào nổi bật.

### 4.5. Phân biệt data I/O và log I/O

Đọc data page thường liên quan buffer pool miss và data files. Ghi transaction có thể liên quan redo log, binary log, doublewrite và flush dirty page. Commit chậm không nhất thiết do data file đọc chậm.

Kiểm tra:

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

Đọc phần LOG, BUFFER POOL AND MEMORY, FILE I/O và TRANSACTIONS. Đối chiếu với Performance Schema file summary và metrics thiết bị.

### 4.6. Hướng xử lý I/O bottleneck

- Tối ưu truy vấn để giảm random reads và số page phải truy cập.
- Xem lại index dư thừa hoặc index không phù hợp làm tăng write amplification.
- Đánh giá buffer pool theo working set và RAM thực tế.
- Kiểm tra checkpoint, dirty page, redo log và tốc độ flush.
- Tách workload đọc/ghi hoặc log theo kiến trúc khi có căn cứ.
- Kiểm tra storage throttling, burst credit, queue và giới hạn volume.
- Chọn thiết bị lưu trữ có latency và IOPS phù hợp.

Không tăng innodb_buffer_pool_size nếu host đang swap hoặc thiếu RAM. Không tăng log size chỉ vì commit chậm khi chưa phân biệt nguyên nhân.

## 5. Phân biệt nghẽn bộ nhớ

Memory pressure xảy ra khi MySQL và các process khác cần nhiều RAM hơn lượng có thể cấp ổn định. Hệ điều hành có thể reclaim cache, swap, kill process do OOM hoặc khiến latency tăng vì page fault.

### 5.1. Dấu hiệu thường gặp

- Available memory giảm liên tục trong khi mysqld RSS tăng.
- Swap in/out tăng và major page fault xuất hiện.
- Kernel log ghi nhận OOM kill hoặc memory allocation failure.
- Container chạm memory limit dù host còn RAM.
- MySQL phát lỗi cấp phát bộ nhớ hoặc query tạm thời thất bại.
- Latency tăng đồng thời với memory reclaim và I/O swap.

Không kết luận thiếu RAM chỉ vì Linux dùng nhiều memory cho page cache. Cần xem available memory, swap activity, reclaim, process RSS và giới hạn container.

### 5.2. Kiểm tra hệ điều hành

~~~bash
free -h
vmstat 1
cat /proc/meminfo
~~~

Kiểm tra thêm kernel log theo quyền và chính sách môi trường:

~~~bash
dmesg -T
~~~

Trên Windows, dùng Task Manager hoặc Performance Monitor để xem Available MBytes, committed bytes, paging file usage và working set của mysqld. Trong container, kiểm tra memory.current, memory.max hoặc thống kê runtime tương ứng.

### 5.3. Phân biệt bộ nhớ toàn cục và bộ nhớ theo session

Một số cấu hình MySQL tiêu thụ bộ nhớ toàn cục:

- innodb_buffer_pool_size.
- innodb_log_buffer_size.
- key_buffer_size nếu có MyISAM workload.
- Performance Schema memory.
- Các cấu trúc cache và metadata của server.

Một số buffer được cấp phát theo hoạt động hoặc session, chẳng hạn:

- sort_buffer_size.
- join_buffer_size.
- read_buffer_size.
- read_rnd_buffer_size.
- thread stack và connection/session overhead.
- Bộ nhớ cho internal temporary table.

Không nhân tất cả biến session với max_connections rồi coi đó là RAM chắc chắn được cấp trước; nhiều buffer chỉ cấp phát khi cần. Tuy vậy, nhiều session đồng thời thực hiện sort/join lớn có thể làm tổng memory tăng đột biến.

### 5.4. Theo dõi memory trong MySQL

Nếu Performance Schema memory instruments được bật:

~~~sql
SELECT
    EVENT_NAME,
    CURRENT_NUMBER_OF_BYTES_USED,
    HIGH_NUMBER_OF_BYTES_USED
FROM performance_schema.memory_summary_global_by_event_name
ORDER BY CURRENT_NUMBER_OF_BYTES_USED DESC
LIMIT 20;
~~~

Xem theo account:

~~~sql
SELECT
    USER,
    EVENT_NAME,
    CURRENT_NUMBER_OF_BYTES_USED,
    HIGH_NUMBER_OF_BYTES_USED
FROM performance_schema.memory_summary_by_account_by_event_name
ORDER BY CURRENT_NUMBER_OF_BYTES_USED DESC
LIMIT 20;
~~~

Một số bảng memory summary chỉ có dữ liệu khi memory instrumentation được hỗ trợ và bật. Giá trị Performance Schema không nhất thiết bao gồm mọi allocation ngoài phạm vi instrument. Đối chiếu với RSS/process memory và OS metrics.

Có thể dùng view sys.memory_global_by_current_bytes hoặc sys.memory_global_total nếu sys schema được cài và phù hợp với phiên bản.

### 5.5. Hướng xử lý memory pressure

- Xác định global memory lớn nhất và workload session đang cấp phát buffer.
- Giảm concurrency hoặc giới hạn connection pool khi có quá nhiều session cùng chạy truy vấn nặng.
- Điều chỉnh buffer per-session sau khi đo nhu cầu thực tế.
- Kiểm tra temporary table lớn và query tạo sort/group trung gian.
- Đánh giá buffer pool theo RAM dành riêng cho database, không chiếm toàn bộ bộ nhớ host.
- Kiểm tra memory leak hoặc tăng trưởng bất thường của process và plugin.
- Đặt container memory limit có khoảng dự phòng và theo dõi OOM event.

Tránh tăng hàng loạt buffer session vì một truy vấn đơn lẻ bị chậm. Tăng buffer có thể khiến nhiều session cùng lúc tiêu thụ RAM lớn hơn.

## 6. Phân biệt nghẽn khóa và tranh chấp đồng thời

Lock contention xảy ra khi transaction phải chờ transaction khác nhả khóa. Metadata lock cũng có thể làm DDL hoặc truy vấn chờ vì một transaction đang giữ metadata của đối tượng.

### 6.1. Dấu hiệu thường gặp

- Threads_running tăng nhưng CPU không tương ứng.
- Query latency tăng và nhiều session ở trạng thái Waiting for ... lock.
- Một số transaction mở lâu hoặc chưa commit/rollback.
- Deadlock hoặc lock wait timeout tăng.
- DDL chờ metadata lock và kéo theo các truy vấn khác xếp hàng.
- Throughput giảm khi số session đồng thời tăng.

Đây là trường hợp dễ nhầm với CPU bottleneck: thread count tăng nhưng phần lớn thời gian có thể là chờ khóa.

### 6.2. Kiểm tra InnoDB lock counters

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Innodb_row_lock_current_waits',
    'Innodb_row_lock_time',
    'Innodb_row_lock_time_avg',
    'Innodb_row_lock_time_max',
    'Innodb_row_lock_waits',
    'Innodb_deadlocks'
);
~~~

Đọc delta của counter theo cửa sổ thời gian. Deadlock là sự kiện cần phân tích transaction và thứ tự khóa; không chỉ nhìn tổng số từ lúc server khởi động.

### 6.3. Xem data lock waits trên MySQL 8.0+

~~~sql
SELECT
    r.ENGINE_TRANSACTION_ID AS waiting_trx,
    r.OBJECT_SCHEMA,
    r.OBJECT_NAME,
    r.INDEX_NAME,
    r.LOCK_TYPE AS waiting_lock_type,
    b.ENGINE_TRANSACTION_ID AS blocking_trx,
    b.LOCK_TYPE AS blocking_lock_type
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS r
  ON r.ENGINE = w.ENGINE
 AND r.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS b
  ON b.ENGINE = w.ENGINE
 AND b.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID;
~~~

Bảng data_locks và data_lock_waits cho biết lock đang chờ và lock đang chặn. Ghép thêm thông tin transaction hoặc thread để xác định session và câu SQL liên quan. Tên cột và khả năng có sẵn cần đối chiếu với phiên bản.

### 6.4. Xem metadata lock đang chờ

~~~sql
SELECT
    OBJECT_TYPE,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    LOCK_TYPE,
    LOCK_DURATION,
    LOCK_STATUS,
    OWNER_THREAD_ID
FROM performance_schema.metadata_locks
WHERE LOCK_STATUS = 'PENDING';
~~~

Một metadata lock đang PENDING có thể chỉ ra DDL hoặc statement phải chờ transaction khác. Tìm owner thread và transaction giữ lock; không kết luận rằng mọi query chậm đều do row lock.

### 6.5. Xem transaction và trạng thái InnoDB

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_wait_started,
    trx_mysql_thread_id,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

InnoDB status có phần TRANSACTIONS và LATEST DETECTED DEADLOCK hữu ích để xem transaction đang chờ và chi tiết deadlock gần nhất. Thông tin deadlock gần nhất có thể bị thay thế bởi sự kiện mới.

### 6.6. Hướng xử lý lock contention

- Rút ngắn transaction và commit/rollback sớm.
- Giữ thứ tự truy cập bảng/hàng nhất quán giữa các transaction.
- Thêm index phù hợp để giảm số hàng bị khóa khi tìm kiếm hoặc cập nhật.
- Chia batch update lớn thành batch nhỏ có kiểm soát.
- Tránh giữ transaction mở trong lúc chờ người dùng hoặc gọi dịch vụ ngoài.
- Xem lại isolation level và phạm vi truy vấn sau khi hiểu yêu cầu nhất quán.
- Xử lý deadlock bằng retry có giới hạn ở tầng ứng dụng khi thao tác có thể retry an toàn.
- Lập kế hoạch DDL để tránh metadata lock kéo dài.

Không tăng innodb_lock_wait_timeout như cách sửa gốc. Timeout cao hơn chỉ làm session chờ lâu hơn nếu transaction chặn vẫn chưa được xử lý.

## 7. Phân biệt nghẽn mạng

Network bottleneck có thể nằm giữa ứng dụng và MySQL, giữa MySQL và storage/network service, hoặc ở proxy/load balancer. Độ trễ mạng, mất gói, retransmission, giới hạn băng thông và quá nhiều round trip đều có thể làm request chậm.

### 7.1. Dấu hiệu thường gặp

- Ứng dụng chậm nhưng CPU, RAM và disk của MySQL không bão hòa.
- Thời gian kết nối hoặc thời gian đọc kết quả tăng.
- RTT cao, packet loss hoặc TCP retransmission tăng.
- Server gửi lượng dữ liệu lớn qua mạng.
- Nhiều query nhỏ nối tiếp nhau tạo quá nhiều round trip.
- Một số client hoặc subnet bị ảnh hưởng, các client khác bình thường.

Network chậm có thể khiến MySQL thread chờ socket hoặc client đọc dữ liệu chậm. Tuy nhiên, socket wait ở server không tự phân biệt được mạng ngoài host với client chậm xử lý dữ liệu.

### 7.2. Kiểm tra số liệu MySQL

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Connections',
    'Threads_connected',
    'Threads_running',
    'Aborted_connects',
    'Bytes_received',
    'Bytes_sent',
    'Connection_errors_accept',
    'Connection_errors_internal',
    'Connection_errors_max_connections',
    'Connection_errors_peer_address'
);
~~~

Các biến bytes là counter tích lũy. Tính delta để biết lượng dữ liệu nhận/gửi trong cửa sổ:

~~~text
delta_bytes_sent = Bytes_sent_B - Bytes_sent_A
delta_bytes_received = Bytes_received_B - Bytes_received_A
average_bytes_per_second = delta_bytes / elapsed_seconds
~~~

Kiểm tra socket summary nếu Performance Schema socket instruments đang được thu thập:

~~~sql
SELECT
    EVENT_NAME,
    COUNT_READ,
    SUM_NUMBER_OF_BYTES_READ,
    COUNT_WRITE,
    SUM_NUMBER_OF_BYTES_WRITE
FROM performance_schema.socket_summary_by_event_name
ORDER BY SUM_NUMBER_OF_BYTES_WRITE DESC
LIMIT 20;
~~~

Tên bảng hoặc cột socket summary có thể khác theo phiên bản. Một số hệ thống dùng socket_summary_by_instance để xem từng socket. Socket wait là thời gian thao tác socket được đo tại server, không phải phép đo RTT đầu cuối.

### 7.3. Kiểm tra từ hệ điều hành và ứng dụng

Trên Linux:

~~~bash
ss -ti
sar -n DEV,TCP,ETCP 1
ping <mysql-host>
~~~

Theo dõi RTT, retransmissions, drops, throughput và trạng thái TCP. Ping có thể bị firewall hoặc chính sách mạng giới hạn; kết quả ping không thay thế phép đo kết nối TCP tới cổng MySQL.

Trên Windows, dùng ping, tracert, Test-NetConnection và Performance Monitor để xem network interface throughput, errors và TCP retransmissions nếu có counter phù hợp.

Trong môi trường cloud, đối chiếu network throughput, packet drops, flow logs, load balancer và proxy metrics. Kiểm tra cả đường đi từ ứng dụng đến proxy và từ proxy đến MySQL.

### 7.4. Hướng xử lý network bottleneck

- Đặt ứng dụng gần MySQL theo topology mạng và vùng triển khai.
- Giảm round trip bằng batching, prepared statement và thiết kế request hợp lý.
- Tránh SELECT trả về cột hoặc hàng không cần thiết.
- Phân trang và giới hạn result set.
- Xem xét compression khi payload lớn và CPU còn dư; đo cả chi phí nén/giải nén.
- Kiểm tra DNS, TLS handshake, proxy, firewall, NAT và connection pool.
- Xác minh MTU, retransmission, packet loss và giới hạn băng thông.

Không tăng max_allowed_packet để xử lý mọi lỗi kết nối. Biến này giới hạn kích thước packet được chấp nhận; nó không sửa RTT, mất gói hoặc client đọc chậm.

## 8. Bảng phân biệt nhanh năm nhóm bottleneck

| Nhóm | Dấu hiệu phía host | Dấu hiệu phía MySQL | Phép đo xác nhận |
|---|---|---|---|
| CPU | CPU user/system và run queue cao | Nhiều statement hoạt động, rows examined hoặc xử lý biểu thức lớn | top/pidstat, statement summary, execution plan |
| Storage I/O | Disk await/latency và queue tăng | File I/O waits, physical reads, flush hoặc log waits | iostat, file_summary_by_instance, InnoDB status |
| Memory | Available RAM thấp, swap/reclaim/OOM | Memory allocation tăng, nhiều session dùng buffer, temp memory lớn | free/vmstat, process RSS, memory_summary |
| Lock | CPU có thể thấp dù latency cao | Data lock/metadata lock waits, transaction lâu, deadlock | data_lock_waits, metadata_locks, innodb_trx |
| Network | RTT/retransmit/drop/throughput bất thường | Socket waits, bytes sent/received hoặc connection errors tăng | ss/sar, socket summary, application tracing |

Một incident có thể có nhiều bottleneck nối tiếp nhau. Ví dụ truy vấn đọc quá nhiều dữ liệu làm tăng disk I/O, sau đó truyền result set lớn làm tăng network time. Hãy xác định nguyên nhân gốc và tác động dây chuyền.

## 9. Kết hợp Performance Schema và sys schema

Performance Schema cung cấp số liệu chi tiết về statement, waits, file, socket, memory và transaction. Schema sys trình bày một số thông tin ở dạng dễ đọc hơn.

Các view hữu ích tùy phiên bản và cấu hình:

- sys.statement_analysis: nhóm statement theo digest và latency.
- sys.innodb_lock_waits: transaction đang chờ và transaction chặn.
- sys.io_global_by_file_by_bytes: file có lượng I/O lớn.
- sys.io_global_by_file_by_latency: file có thời gian I/O lớn.
- sys.memory_global_by_current_bytes: phân bổ memory theo event.
- sys.processlist: session và trạng thái hiện tại.

Ví dụ xem các file có latency I/O cao:

~~~sql
SELECT *
FROM sys.io_global_by_file_by_latency
ORDER BY total_latency DESC
LIMIT 20;
~~~

Ví dụ xem lock waits:

~~~sql
SELECT *
FROM sys.innodb_lock_waits;
~~~

Các view sys dựa trên Performance Schema và có thể thay đổi theo bản phát hành. Nếu view không tồn tại hoặc cột khác tên, kiểm tra định nghĩa view của server đang dùng.

## 10. Phân biệt các trường hợp dễ nhầm

### 10.1. CPU cao và lock wait

CPU cao cùng throughput cao có thể là workload compute-bound. Nếu Threads_running tăng nhưng CPU thấp và nhiều session có wait event lock, vấn đề có thể là contention. Đọc thread state và Performance Schema waits trước khi tăng CPU.

### 10.2. I/O cao và memory pressure

Swap I/O do memory pressure khác với data file I/O của InnoDB. Dùng iostat để thấy thiết bị bận nhưng cần vmstat, swap counters, file summary và process memory để phân biệt.

### 10.3. Network wait và client xử lý chậm

MySQL có thể chờ socket ghi dữ liệu vì client đọc result chậm. Xem bytes sent, kích thước result, application trace và client CPU. Không kết luận mạng bị mất gói chỉ từ socket wait.

### 10.4. Disk latency và commit latency

Commit chậm có thể liên quan redo log flush hoặc binary log synchronization. Kiểm tra log waits, file summary và cấu hình durability. Không mặc định mọi commit chậm đều do data page read.

### 10.5. Nhiều connection và thiếu CPU

Threads_connected cao cho biết nhiều connection đang mở; nó không nói rằng tất cả đều hoạt động. Đối chiếu Threads_running, connection pool, wait events và CPU. Giới hạn pool có thể giúp tránh overload.

## 11. Xây dựng baseline và so sánh trước/sau

Một lần đo riêng lẻ không đủ để chứng minh thay đổi cải thiện hệ thống. Baseline nên có:

- Workload đại diện và thời lượng đo cố định.
- Request rate, throughput, p50/p95/p99 latency ở tầng ứng dụng.
- CPU utilization, run queue và throttling.
- Available memory, swap in/out, mysqld RSS.
- Disk read/write latency, IOPS, throughput và queue.
- Network RTT, retransmission, packet loss và bytes.
- MySQL status counters, statement summaries và wait summaries.

Sau thay đổi, giữ nguyên hoặc ghi rõ các yếu tố khác biệt: dữ liệu, cache warm/cold, concurrency, số client, background job và thời điểm backup. So sánh delta counter và latency distribution, không chỉ so một số tổng.

### 11.1. Mẫu ghi nhận phép đo

| Hạng mục | Trước thay đổi | Sau thay đổi |
|---|---|---|
| Thời gian đo | Cửa sổ A | Cửa sổ B |
| Request rate | Ghi số liệu | Ghi số liệu |
| p95 latency | Ghi số liệu | Ghi số liệu |
| CPU và run queue | Ghi số liệu | Ghi số liệu |
| Available RAM và swap | Ghi số liệu | Ghi số liệu |
| Disk latency và queue | Ghi số liệu | Ghi số liệu |
| Network RTT/retransmit | Ghi số liệu | Ghi số liệu |
| Threads_running và waits | Ghi số liệu | Ghi số liệu |
| Statement top và rows examined | Ghi số liệu | Ghi số liệu |

Không điền số giả định vào báo cáo production. Ghi nguồn, đơn vị và khoảng thời gian của mỗi chỉ số.

## 12. Quy tắc thay đổi an toàn

1. Ghi lại cấu hình và status ban đầu.
2. Xác định một giả thuyết cụ thể, ví dụ disk read latency cao do buffer pool miss.
3. Chọn phép đo có thể bác bỏ giả thuyết đó.
4. Thay đổi một nhóm cấu hình hoặc một query tại một thời điểm.
5. Định nghĩa tiêu chí thành công và điều kiện rollback trước khi áp dụng.
6. Chạy workload tương đương và thu thập lại cùng chỉ số.
7. Kiểm tra tác động phụ như RAM, write latency, replication lag và lỗi ứng dụng.
8. Lưu kết quả để so sánh các lần điều chỉnh sau.

Tránh điều chỉnh nhiều biến cùng lúc, chẳng hạn buffer pool, thread count, timeout và index trong cùng một đợt. Nếu hiệu năng thay đổi, sẽ khó biết nguyên nhân.

## 13. Bài thực hành: chẩn đoán theo bằng chứng

Thực hiện trong môi trường lab hoặc staging. Không tạo tải lớn, không chạy stress test trên production và không thay đổi giới hạn OS của máy dùng chung.

### 13.1. Thu thập baseline MySQL

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Uptime',
    'Threads_connected',
    'Threads_running',
    'Questions',
    'Bytes_received',
    'Bytes_sent',
    'Innodb_buffer_pool_read_requests',
    'Innodb_buffer_pool_reads',
    'Innodb_data_reads',
    'Innodb_data_writes',
    'Innodb_log_waits',
    'Innodb_row_lock_waits',
    'Innodb_deadlocks'
);
~~~

Lưu kết quả và timestamp. Chờ một cửa sổ workload ổn định rồi lấy snapshot thứ hai. Tính delta cho counter tích lũy.

### 13.2. Kiểm tra statement và wait

~~~sql
SELECT
    DIGEST_TEXT,
    COUNT_STAR,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS elapsed_seconds,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 10;
~~~

Nếu có statement latency cao, chọn một query đại diện và đọc EXPLAIN. Đối chiếu với CPU, file I/O và lock waits trong cùng khoảng thời gian.

### 13.3. Đọc wait events

~~~sql
SELECT
    EVENT_NAME,
    COUNT_STAR,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS total_wait_seconds
FROM performance_schema.events_waits_summary_global_by_event_name
WHERE COUNT_STAR > 0
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
~~~

Bảng wait summary có thể không được thu thập nếu wait instruments bị tắt. Wait event cho biết loại chờ được instrument; nó không tự giải thích nguyên nhân ở tầng ứng dụng hoặc OS.

### 13.4. Lập giả thuyết

Với mỗi hiện tượng, ghi:

- Tài nguyên nghi ngờ.
- Chỉ số hỗ trợ giả thuyết.
- Chỉ số có thể bác bỏ giả thuyết.
- Phép đo tiếp theo.
- Thay đổi có thể thử.
- Tiêu chí rollback.

Ví dụ: nếu CPU cao nhưng disk latency thấp, kiểm tra query CPU cost và concurrency trước khi tăng storage. Nếu CPU thấp nhưng nhiều transaction chờ lock, tìm blocking transaction thay vì thêm CPU.

### 13.5. Dọn lab

Chỉ xóa các đối tượng do chính bài tập tạo. Không reset toàn bộ Performance Schema trên server dùng chung và không xóa dữ liệu ứng dụng.

## 14. Runbook khi MySQL đột ngột chậm

1. Xác nhận sự cố ảnh hưởng một instance, một endpoint hay toàn hệ thống.
2. Ghi timestamp, uptime, request rate, p95/p99 và số lỗi.
3. Kiểm tra CPU, run queue, memory, swap, disk latency và network errors.
4. Kiểm tra Threads_running, Threads_connected và connection errors.
5. Xem statement summaries, wait summaries và InnoDB status.
6. Nếu CPU bão hòa, xác định process và statement tiêu thụ CPU.
7. Nếu disk latency cao, xác định file I/O, data/log workload và storage throttling.
8. Nếu memory pressure, kiểm tra RSS, swap, OOM và session buffers.
9. Nếu lock waits tăng, xác định blocking transaction và metadata lock.
10. Nếu network bất thường, đối chiếu RTT, retransmission, socket metrics và kích thước result.
11. Chọn thay đổi nhỏ nhất có thể kiểm chứng và chuẩn bị rollback.
12. Đo lại trong cửa sổ tương đương, ghi rõ kết quả và tác động phụ.

## 15. Checklist vận hành

### Khi bắt đầu điều tra

- [ ] Có timestamp và khoảng thời gian sự cố.
- [ ] Có request rate, throughput và latency distribution.
- [ ] Đã ghi MySQL uptime và status snapshot.
- [ ] Đã lấy CPU, memory, disk và network metrics cùng cửa sổ.
- [ ] Đã kiểm tra workload nền như backup, batch hoặc deploy.

### Khi xác định bottleneck

- [ ] CPU được xác nhận bằng process usage và run queue.
- [ ] I/O được xác nhận bằng latency, queue và file-level data.
- [ ] Memory được xác nhận bằng available RAM, swap, reclaim hoặc OOM.
- [ ] Lock được xác nhận bằng wait/lock tables và transaction owner.
- [ ] Network được xác nhận bằng RTT, retransmission, drops hoặc socket/client evidence.
- [ ] Đã phân biệt nguyên nhân gốc với triệu chứng dây chuyền.

### Sau khi thay đổi

- [ ] Có baseline trước thay đổi.
- [ ] Chỉ thay đổi phạm vi có giả thuyết rõ.
- [ ] Đã đo lại cùng chỉ số và workload.
- [ ] Đã kiểm tra tác động phụ và replication.
- [ ] Có kết quả, nguồn dữ liệu và điều kiện rollback được ghi nhận.

## 16. Nguyên tắc cần ghi nhớ

- CPU bottleneck cần được xác nhận bằng CPU usage, run queue và process/thread activity; Threads_running không phải CPU meter.
- Performance Schema statement timer đo elapsed time, có thể bao gồm thời gian chờ, không phải CPU time thuần.
- Storage bottleneck cần xem latency, queue, IOPS và loại file I/O; throughput cao riêng lẻ chưa đủ kết luận.
- Buffer pool read counters cần được đọc theo delta; hit ratio cao không loại trừ log hoặc flush I/O bottleneck.
- Memory pressure thể hiện qua available RAM, swap/reclaim, OOM và process/container memory, không chỉ qua tổng RAM đã dùng.
- Buffer theo session có thể cấp phát khi truy vấn cần; nhiều session chạy truy vấn nặng có thể làm memory tăng đột biến.
- Lock contention làm thread chờ; tìm transaction chặn, metadata lock và deadlock trước khi tăng concurrency.
- Network bottleneck cần bằng chứng RTT, packet loss, retransmission, bandwidth hoặc client/socket behavior.
- Socket wait phía MySQL không tự phân biệt mạng chậm với client đọc chậm.
- Counter tích lũy cần snapshot và delta; restart hoặc reset làm phép so sánh mất hiệu lực.
- Kết hợp MySQL metrics, OS metrics và application tracing để xác định nguyên nhân.
- Thay đổi một nhóm yếu tố mỗi lần và xác nhận trên workload tương đương.

Chẩn đoán hiệu năng MySQL hiệu quả bắt đầu từ việc phân biệt CPU, I/O, memory, lock và network bằng bằng chứng cùng thời điểm. Khi xác định đúng tài nguyên đang tạo hàng đợi, người vận hành có thể tập trung vào statement, file, transaction hoặc kết nối liên quan, thử một thay đổi có kiểm soát và đo lại kết quả thay vì điều chỉnh cấu hình theo cảm tính.

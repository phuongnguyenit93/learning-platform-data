# Hoàn thiện sổ tay vận hành với sơ đồ, metric và bằng chứng phục hồi

Bài thực hành này thuộc module **DATABASE_MYSQL**. Mục tiêu của module là làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời; đồng thời thực hành đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ.

Trong bài này, ta tổng hợp các kỹ năng đó thành một **sổ tay vận hành MySQL (operations handbook)** có thể dùng khi bàn giao dịch vụ, trực ca, xử lý sự cố và diễn tập phục hồi. Một sổ tay hữu ích phải trả lời được những câu hỏi cụ thể: hệ thống gồm những thành phần nào, ai chịu trách nhiệm, cần theo dõi metric nào, dấu hiệu nào cần cảnh báo, thao tác kiểm tra nào an toàn, khi nào phải chuyển cấp và làm sao chứng minh dữ liệu đã phục hồi đúng.

Sổ tay không phải tập hợp lệnh rời rạc. Mỗi quy trình cần nêu mục tiêu, điều kiện bắt đầu, quyền cần có, bước thực hiện, kết quả mong đợi, cách dừng/rollback và bằng chứng cần lưu. Các ngưỡng cảnh báo phải được hiệu chỉnh theo baseline của hệ thống; ví dụ trong bài là khung để xây dựng, không phải ngưỡng áp dụng chung cho mọi workload.

## 1. Kết quả cần bàn giao

Sau bài thực hành, nhóm vận hành có một bộ tài liệu tối thiểu gồm:

1. Sơ đồ kiến trúc và luồng dữ liệu.
2. Danh mục instance, môi trường, phiên bản và vai trò từng node.
3. Danh mục metric, dashboard, cảnh báo và cách diễn giải.
4. Quy trình kiểm tra sức khỏe định kỳ.
5. Runbook xử lý sự cố thường gặp.
6. Quy trình backup, lưu giữ binary log và phục hồi.
7. Kế hoạch diễn tập restore có đo RPO/RTO.
8. Danh sách bằng chứng chứng minh backup và restore có thể sử dụng.
9. Ma trận quyền, người chịu trách nhiệm và thông tin escalation.
10. Checklist bàn giao và lịch rà soát sổ tay.

Một tài liệu chỉ ghi “backup chạy thành công” là chưa đủ. Cần có bằng chứng về thời điểm, nguồn dữ liệu, GTID hoặc binlog coordinate, checksum, kết quả restore, thời gian phục hồi và kiểm tra dữ liệu sau restore.

## 2. Xác định phạm vi dịch vụ

Trước khi viết runbook, ghi rõ dịch vụ mà sổ tay bao phủ. Không dùng tên môi trường chung chung như “database chính” nếu hệ thống có nhiều cụm hoặc nhiều vùng.

Mẫu thông tin dịch vụ:

| Trường | Nội dung cần ghi |
|---|---|
| Service name | Tên dịch vụ database theo danh mục nội bộ |
| Business owner | Nhóm sở hữu nghiệp vụ |
| Technical owner | Nhóm chịu trách nhiệm MySQL |
| On-call | Nhóm trực chính và nhóm escalation |
| Environment | Development, staging, production |
| Database product | MySQL Community/Enterprise hoặc dịch vụ tương thích được xác nhận |
| Version | Phiên bản server, Connector/J và công cụ backup |
| Topology | Standalone, source/replica, Group Replication hoặc managed cluster |
| Data classification | Phân loại dữ liệu và yêu cầu bảo vệ |
| Criticality | Mức độ quan trọng và giờ hoạt động |
| RPO | Mức mất dữ liệu tối đa chấp nhận được |
| RTO | Thời gian tối đa để khôi phục dịch vụ |
| Change window | Khung giờ được phép triển khai thay đổi |
| Backup owner | Người/nhóm vận hành backup và restore |

Không điền giá trị phỏng đoán. Nếu chưa biết RPO, RTO, phiên bản hoặc owner, đánh dấu là “chưa xác nhận”, gán người chịu trách nhiệm và ngày cần hoàn thành.

### 2.1. Chốt RPO và RTO theo nghiệp vụ

- **RPO (Recovery Point Objective):** khoảng dữ liệu tối đa mà doanh nghiệp chấp nhận mất khi xảy ra sự cố.
- **RTO (Recovery Time Objective):** thời gian tối đa từ lúc dịch vụ gián đoạn đến khi dịch vụ được khôi phục ở mức đã thống nhất.

Ví dụ: RPO 5 phút nghĩa là trong kịch bản đã thiết kế và kiểm thử, điểm phục hồi không được cũ hơn thời điểm sự cố quá 5 phút. RTO 60 phút nghĩa là mục tiêu đưa dịch vụ trở lại trong vòng 60 phút.

RPO/RTO phải được phê duyệt theo mức ảnh hưởng nghiệp vụ, không được chọn chỉ vì công cụ backup có thể đáp ứng. Nếu hệ thống chưa chứng minh được khả năng đạt mục tiêu, ghi rõ khoảng cách và kế hoạch cải thiện.

## 3. Sơ đồ kiến trúc và luồng dữ liệu

Sơ đồ cần cho người trực biết ứng dụng kết nối tới đâu, dữ liệu đi qua node nào và backup được đưa ra khỏi hệ thống như thế nào.

Ví dụ topology source/replica:

~~~mermaid
flowchart LR
    APP[Ứng dụng] --> POOL[Connection pool]
    POOL --> PROXY[Proxy hoặc endpoint ghi]
    PROXY --> SRC[(MySQL source)]
    SRC --> BINLOG[Binary log]
    BINLOG --> R1[(Replica đọc 1)]
    BINLOG --> R2[(Replica đọc 2)]
    SRC --> BKP[Backup pipeline]
    BINLOG --> ARCHIVE[Lưu trữ binary log]
    BKP --> VAULT[(Kho backup tách biệt)]
    ARCHIVE --> VAULT
    SRC --> EXP[Exporter / Performance Schema]
    R1 --> EXP
    R2 --> EXP
    EXP --> PROM[Prometheus / Monitoring]
    PROM --> DASH[Dashboard và alert]
~~~

Sơ đồ trên chỉ là mẫu. Nếu hệ thống dùng Group Replication, InnoDB Cluster, managed database hoặc multi-source replication, thay bằng sơ đồ đúng với topology thực tế. Không vẽ replica như một bản backup: replication sao chép thay đổi, nên thao tác xóa nhầm hoặc dữ liệu hỏng có thể được truyền sang replica.

### 3.1. Ghi rõ luồng đọc và ghi

Sổ tay phải nêu:

- Endpoint ghi hiện tại.
- Endpoint đọc và quy tắc phân phối truy vấn.
- Thành phần proxy/load balancer nếu có.
- Node có quyền nhận ghi.
- Cách ứng dụng xử lý khi replica chậm.
- Cách chuyển endpoint khi failover.
- Cách ngăn source cũ tiếp tục nhận ghi sau khi promote node mới.

Không để ứng dụng tự chọn một node bất kỳ theo danh sách IP nếu chưa có cơ chế kiểm soát writer duy nhất. Khi failover, phải có bước fencing hoặc biện pháp tương đương để ngăn split-brain.

### 3.2. Sơ đồ phụ thuộc và ranh giới tin cậy

Bổ sung các thành phần ngoài MySQL:

- DNS, proxy, load balancer và firewall.
- Secret manager và chứng thư TLS.
- Backup scheduler, kho object storage và khóa mã hóa.
- Monitoring, log collector và alert manager.
- Hệ thống xác thực, IAM và jump host.
- Dịch vụ ứng dụng, queue consumer, ETL và BI.

Đánh dấu đường kết nối nào được phép, tài khoản nào được dùng và dữ liệu nào rời khỏi vùng mạng database. Không đưa mật khẩu, token, private key hoặc chuỗi kết nối có secret vào sơ đồ hay tài liệu.

## 4. Danh mục instance và cấu hình chuẩn

Mỗi instance cần có một bản ghi inventory. Không dùng một bảng chung mà không thể phân biệt source, replica, staging và node đã ngừng hoạt động.

| Trường | Ví dụ định dạng |
|---|---|
| Instance ID | mysql-prod-a |
| Environment | production |
| Role | source / replica / recovery target |
| Host / endpoint | DNS nội bộ, không ghi secret |
| Port | 3306 nếu dùng mặc định |
| Server version | Kết quả VERSION() |
| server_id | Giá trị số duy nhất trong topology |
| server_uuid | UUID lấy từ @@server_uuid |
| Storage engine | InnoDB |
| GTID mode | ON/OFF |
| Binary logging | ON/OFF |
| Replication channel | Tên channel nếu có |
| Data directory | Đường dẫn đã xác nhận |
| Backup policy | Lịch, loại backup, retention |
| Monitoring target | Nhãn target trong hệ thống giám sát |

Lấy thông tin cơ bản trên từng instance:

~~~sql
SELECT
    VERSION() AS server_version,
    @@version_comment AS distribution,
    @@hostname AS hostname,
    @@port AS port,
    @@server_id AS server_id,
    @@server_uuid AS server_uuid,
    @@datadir AS data_directory,
    @@log_bin AS log_bin,
    @@gtid_mode AS gtid_mode,
    @@default_storage_engine AS default_engine;
~~~

Kiểm tra cấu hình quan trọng:

~~~sql
SHOW VARIABLES
WHERE Variable_name IN (
    'max_connections',
    'wait_timeout',
    'interactive_timeout',
    'innodb_buffer_pool_size',
    'innodb_redo_log_capacity',
    'slow_query_log',
    'long_query_time',
    'binlog_expire_logs_seconds',
    'read_only',
    'super_read_only',
    'time_zone',
    'sql_mode'
);
~~~

Một số biến không tồn tại ở phiên bản MySQL cũ hoặc có tên khác. Sổ tay cần ghi phiên bản tham chiếu và cách kiểm tra tương ứng; không coi một cấu hình mẫu là đúng cho mọi bản phát hành.

## 5. Thiết kế hệ thống metric

Metric cần giúp trả lời sáu câu hỏi:

1. Dịch vụ có sẵn sàng không?
2. Truy vấn có chậm hoặc lỗi không?
3. Tài nguyên có gần bão hòa không?
4. Transaction và lock có làm giảm throughput không?
5. Replica có theo kịp source không?
6. Backup và khả năng phục hồi có còn đáng tin cậy không?

Chia metric theo nhóm:

| Nhóm | Câu hỏi vận hành | Ví dụ |
|---|---|---|
| Availability | Instance và endpoint có hoạt động? | Probe kết nối, uptime, trạng thái replication |
| Traffic | Tải đang tăng hay giảm? | QPS, transactions/s, connections |
| Latency | Truy vấn có chậm? | p50/p95/p99, slow query count |
| Errors | Có thao tác thất bại? | Connection errors, deadlocks, SQL errors |
| Saturation | Tài nguyên có cạn? | CPU, memory, disk, IOPS, connection usage |
| InnoDB | Storage engine có bị nghẽn? | Buffer pool, row locks, redo log waits |
| Replication | Dữ liệu có theo kịp? | GTID gap, applier errors, lag |
| Backup/recovery | Có thể phục hồi? | Backup age, duration, checksum, restore drill |

### 5.1. Availability và connection

Theo dõi:

- Probe kết nối tới endpoint ghi.
- Probe đọc từ replica nếu replica phục vụ truy vấn.
- Uptime và restart count.
- Threads_connected.
- Threads_running.
- Max_used_connections.
- Connections và Aborted_connects.
- Connection errors theo nguyên nhân.
- Tỷ lệ connection pool đang dùng, chờ và timeout ở phía ứng dụng.

Lấy status:

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Uptime',
    'Threads_connected',
    'Threads_running',
    'Max_used_connections',
    'Connections',
    'Aborted_connects'
);
~~~

Threads_connected cao không luôn đồng nghĩa có sự cố; connection pool có thể giữ kết nối nhàn rỗi. Threads_running tăng kéo dài cùng CPU, latency và hàng đợi connection mới là dấu hiệu cần điều tra.

Không tăng max_connections chỉ để xóa cảnh báo. Mỗi connection tiêu thụ tài nguyên; giới hạn phải được thiết kế cùng pool size, concurrency và memory budget.

### 5.2. Traffic và latency

Theo dõi số lệnh và transaction theo thời gian:

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Questions',
    'Queries',
    'Com_select',
    'Com_insert',
    'Com_update',
    'Com_delete',
    'Slow_queries'
);
~~~

Các status counter phần lớn là bộ đếm tích lũy từ khi server khởi động hoặc reset counter. Để tính tốc độ, lấy chênh lệch giữa hai lần scrape chia cho khoảng thời gian. Sau restart, counter có thể quay về giá trị thấp; hệ thống giám sát cần xử lý reset counter đúng cách.

QPS không thể hiện đầy đủ hiệu năng. Một workload có ít truy vấn nhưng mỗi truy vấn quét hàng triệu dòng vẫn có thể làm hệ thống chậm. Kết hợp QPS với latency, rows examined, lock waits và query digest.

Nếu ứng dụng có metrics theo endpoint, ghi nhận p50/p95/p99 latency và error rate tại tầng ứng dụng. MySQL status counters không tự cung cấp latency end-to-end của request.

### 5.3. Slow query và query digest

Bật slow query log theo chính sách đã kiểm thử:

~~~sql
SHOW VARIABLES LIKE 'slow_query_log';
SHOW VARIABLES LIKE 'long_query_time';
SHOW VARIABLES LIKE 'log_queries_not_using_indexes';
~~~

Không bật log mọi truy vấn không dùng index một cách thiếu kiểm soát trên production; có thể tạo lượng log rất lớn và nhiều false positive. Chọn ngưỡng dựa trên baseline và workload.

Performance Schema có thể tổng hợp statement theo digest:

~~~sql
SELECT
    SCHEMA_NAME,
    DIGEST_TEXT,
    COUNT_STAR,
    SUM_TIMER_WAIT,
    AVG_TIMER_WAIT,
    MAX_TIMER_WAIT,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT
FROM performance_schema.events_statements_summary_by_digest
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
~~~

Các trường TIMER_WAIT thường được lưu theo đơn vị picosecond trong Performance Schema. Khi trình bày metric, chuyển đổi đơn vị rõ ràng. Bảng digest có giới hạn số statement và số liệu có thể reset khi server restart hoặc Performance Schema bị reset.

Khi điều tra một query digest:

1. Lấy SQL mẫu và schema liên quan.
2. Xem số lần chạy, tổng thời gian, thời gian trung bình và tối đa.
3. So sánh rows examined với rows sent.
4. Chạy EXPLAIN trên truy vấn đại diện.
5. Dùng EXPLAIN ANALYZE khi phiên bản hỗ trợ và có thể chạy an toàn.
6. Kiểm tra index, cardinality, thống kê và dữ liệu skew.
7. Đánh giá thay đổi bằng benchmark trước/sau.

Không chạy EXPLAIN ANALYZE trên một câu lệnh ghi hoặc truy vấn nặng ở production nếu chưa hiểu tác động thực thi của nó.

### 5.4. InnoDB buffer pool và storage

Theo dõi các counter:

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Innodb_buffer_pool_read_requests',
    'Innodb_buffer_pool_reads',
    'Innodb_buffer_pool_pages_total',
    'Innodb_buffer_pool_pages_free',
    'Innodb_buffer_pool_pages_dirty',
    'Innodb_row_lock_waits',
    'Innodb_row_lock_time',
    'Innodb_row_lock_current_waits',
    'Innodb_log_waits'
);
~~~

Các chỉ số cần diễn giải cùng nhau:

- Buffer pool read requests: yêu cầu đọc logic vào buffer pool.
- Buffer pool reads: số lần phải đọc page từ storage.
- Pages dirty: page đã thay đổi nhưng chưa được flush.
- Row lock waits/time: dấu hiệu transaction phải chờ khóa.
- Deadlocks: số deadlock được phát hiện.
- Log waits: tình huống transaction phải chờ redo log được flush/ghi.

Để xem bộ đếm deadlock của InnoDB nếu metric tương ứng được bật, có thể kiểm tra:

~~~sql
SELECT NAME, COUNT, STATUS
FROM information_schema.innodb_metrics
WHERE NAME IN ('lock_deadlocks', 'lock_timeouts');
~~~

Nếu metric đang tắt hoặc không có trong phiên bản triển khai, dùng phần LATEST DETECTED DEADLOCK trong SHOW ENGINE INNODB STATUS và hệ thống monitoring tương ứng. Không giả định mọi bản MySQL xuất cùng một bộ status variable.

Tỷ lệ cache hit có thể dùng để theo dõi xu hướng, nhưng không nên dùng một ngưỡng cố định làm tiêu chí duy nhất. Workload scan lớn, cache warm-up và cách đo có thể làm tỷ lệ thay đổi. Đối chiếu với I/O latency, buffer pool size, working set và query plan.

Ngoài metric MySQL, theo dõi hệ điều hành và storage:

- CPU utilization, load average và CPU steal nếu chạy máy ảo.
- RAM, swap và OOM event.
- Disk free space theo từng filesystem.
- IOPS, throughput và latency đọc/ghi.
- Filesystem inode nếu nền tảng có giới hạn.
- Dung lượng data, redo, undo, relay log và binary log.
- Dung lượng backup và tốc độ tăng trưởng.

Disk free là metric có tính thời gian. Cảnh báo theo cả phần trăm còn trống và tốc độ tăng dung lượng để có đủ thời gian xử lý trước khi filesystem đầy.

### 5.5. Lock, transaction và undo history

Khi truy vấn chậm bất thường, kiểm tra transaction đang mở và lock:

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_wait_started,
    trx_mysql_thread_id,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Kiểm tra trạng thái InnoDB:

~~~sql
SHOW ENGINE INNODB STATUS\G
~~~

Tìm các dấu hiệu:

- Transaction mở lâu.
- Lock wait tăng.
- Deadlock lặp lại.
- Transaction sửa nhiều hàng.
- Undo history/history list tăng kéo dài.
- Flush hoặc redo log có dấu hiệu nghẽn.

Một transaction đọc lâu theo REPEATABLE READ có thể giữ read view và làm purge không giải phóng được undo version cũ. Không kill session chỉ vì nó lâu; trước tiên xác định owner, câu lệnh, transaction đã thay đổi gì và tác động rollback.

### 5.6. Replication và GTID

Với asynchronous replication, theo dõi:

- Trạng thái receiver và applier.
- Last_IO_Error và Last_SQL_Error.
- Retrieved_Gtid_Set và Executed_Gtid_Set.
- Khoảng GTID còn thiếu.
- Số worker đang hoạt động và lỗi applier.
- Dung lượng relay log.
- Độ trễ theo metric của nền tảng và thời gian commit/apply.

MySQL 8.0.22 trở lên:

~~~sql
SHOW REPLICA STATUS\G
~~~

Các bản cũ có thể dùng SHOW SLAVE STATUS. Không dùng Seconds_Behind_Source như nguồn chân lý duy nhất. Giá trị có thể NULL khi thread dừng hoặc trạng thái chưa xác định, và có thể không phản ánh đầy đủ độ trễ quan sát từ ứng dụng.

Với GTID, có thể kiểm tra:

~~~sql
SELECT
    @@GLOBAL.gtid_executed AS executed_gtids,
    @@GLOBAL.gtid_purged AS purged_gtids,
    @@GLOBAL.server_uuid AS server_uuid;
~~~

Để xác nhận replica đã áp dụng tới một GTID mục tiêu:

~~~sql
SELECT WAIT_FOR_EXECUTED_GTID_SET(
    'UUID:1-1000',
    30
) AS wait_result;
~~~

Thay UUID:1-1000 bằng GTID set thực tế. Giá trị 0 nghĩa là đã thực thi xong tập yêu cầu; 1 nghĩa là timeout. Chỉ chạy sau khi đã xác định rõ điểm đồng bộ cần kiểm tra.

Với Group Replication, theo dõi trạng thái member:

~~~sql
SELECT
    MEMBER_ID,
    MEMBER_HOST,
    MEMBER_PORT,
    MEMBER_STATE,
    MEMBER_ROLE
FROM performance_schema.replication_group_members;
~~~

Member cần ở trạng thái phù hợp với vai trò cụm. Không promote hoặc bootstrap một group chỉ dựa vào metric lag; cần theo quy trình cluster và quorum đã được kiểm chứng.

## 6. Xây dựng dashboard vận hành

Dashboard nên có một màn hình tổng quan và các màn hình chuyên sâu. Không nhồi mọi metric vào một biểu đồ.

### 6.1. Dashboard tổng quan

| Panel | Hiển thị | Cách đọc |
|---|---|---|
| Service availability | Probe endpoint, trạng thái instance | Phát hiện mất kết nối hoặc node dừng |
| Request latency | p50/p95/p99 của ứng dụng | Nhìn trải nghiệm thực tế |
| Query throughput | QPS, transaction/s | Phân biệt tăng tải với giảm tải |
| Error rate | Lỗi SQL, timeout, connection error | Phát hiện lỗi tăng đột biến |
| Connection usage | Threads_connected, pool utilization | Nhìn nguy cơ cạn connection |
| CPU and memory | CPU, RAM, swap | Nhìn bão hòa compute |
| Disk and I/O | Free space, IOPS, latency | Nhìn nguy cơ storage |
| Replication | Thread state, GTID gap, apply lag | Nhìn khả năng phục vụ đọc/failover |
| Backup freshness | Thời điểm backup thành công gần nhất | Nhìn độ mới của bản sao |
| Restore drill | Lần restore test gần nhất, thời gian | Nhìn khả năng phục hồi đã được chứng minh |

### 6.2. Dashboard hiệu năng

Nên có:

- Top query digest theo tổng thời gian.
- Top digest theo thời gian trung bình và tối đa.
- Rows examined/rows sent.
- Slow query count.
- Threads_running.
- Lock wait và deadlock rate.
- Buffer pool reads.
- Disk read/write latency.
- Redo log waits.
- Temporary tables trên disk.

Dùng cùng time range để đối chiếu các biểu đồ. Ví dụ latency tăng cùng Threads_running và disk latency có thể chỉ ra bão hòa tài nguyên; latency tăng trong khi CPU thấp có thể liên quan lock wait, network hoặc dependency bên ngoài.

### 6.3. Dashboard bảo vệ dữ liệu

Đây là dashboard bắt buộc với database quan trọng:

- Backup thành công gần nhất theo từng instance/database.
- Backup age và thời lượng backup.
- Kích thước backup, tốc độ tăng/giảm bất thường.
- Checksum/manifest verification.
- Binary log archive freshness và retention.
- Dung lượng còn trống trong kho backup.
- Restore drill gần nhất.
- Thời gian restore và replay binlog.
- Kết quả kiểm tra row count/checksum/business invariants.
- RPO/RTO đo được ở lần diễn tập gần nhất.

Backup job xanh không có nghĩa restore thành công. Dashboard phải thể hiện restore test như một tín hiệu độc lập.

## 7. Xây dựng cảnh báo có hành động rõ ràng

Mỗi alert cần có:

- Tên và mức độ nghiêm trọng.
- Điều kiện kích hoạt và thời gian duy trì.
- Tác động nghiệp vụ.
- Runbook liên quan.
- Nhóm nhận alert và escalation.
- Cách xác nhận đã xử lý.
- Điều kiện đóng alert.

Mẫu cảnh báo:

| Alert | Điều kiện tham khảo | Hành động đầu tiên |
|---|---|---|
| MySQL endpoint unavailable | Probe lỗi liên tục trong cửa sổ đã định | Kiểm tra instance, network, proxy và error log |
| Connection saturation | Pool/connection usage gần giới hạn kéo dài | Kiểm tra pool wait, Threads_running và truy vấn giữ connection |
| Slow query regression | p95 hoặc tổng query time vượt baseline | Xác định digest mới hoặc thay đổi plan |
| Disk pressure | Dự báo thời gian tới đầy dưới ngưỡng vận hành | Kiểm tra data growth, binlog, relay log và backup |
| Replica applier stopped | Applier không chạy hoặc Last_SQL_Error khác rỗng | Thu thập status/error trước khi can thiệp |
| Replica lag | Lag vượt ngưỡng nghiệp vụ kéo dài | Kiểm tra source load, network, applier workers và query |
| Backup stale | Không có backup xác minh được trong khoảng mục tiêu | Kiểm tra scheduler, credentials, storage và log |
| Restore drill overdue | Quá hạn diễn tập theo chính sách | Lên lịch restore test và ghi nhận bằng chứng |
| Deadlock increase | Tốc độ deadlock vượt baseline | Thu thập deadlock detail, truy vấn và transaction order |

Các điều kiện “gần giới hạn”, “vượt baseline” cần được chuyển thành con số sau giai đoạn quan sát. Không sao chép ngưỡng 80% CPU, 90% disk hay một giá trị lag cố định cho mọi hệ thống. Cảnh báo phải phản ánh thời gian duy trì và tốc độ thay đổi để tránh alert noise.

### 7.1. Ví dụ logic alert theo xu hướng

Với disk, cảnh báo không chỉ dựa vào phần trăm đã dùng. Nếu dung lượng tăng rất nhanh, volume còn 30% vẫn có thể đầy trước ca trực tiếp theo. Kết hợp:

- Free bytes.
- Tốc độ tăng dữ liệu theo giờ/ngày.
- Tốc độ tăng binary log.
- Kích thước backup đang ghi.
- Dung lượng dự phòng cần cho restore.

Với replication, cảnh báo khi applier dừng hoặc GTID gap tăng liên tục thường quan trọng hơn một mẫu Seconds_Behind_Source đơn lẻ.

## 8. Quy trình kiểm tra sức khỏe định kỳ

Một health check nên thực hiện từ read-only account nếu có thể. Không chạy thao tác ghi thử lên production chỉ để kiểm tra kết nối.

### 8.1. Kiểm tra kết nối và phiên bản

~~~sql
SELECT NOW(6) AS server_time,
       VERSION() AS version,
       @@hostname AS hostname,
       @@server_id AS server_id,
       @@server_uuid AS server_uuid,
       @@read_only AS read_only,
       @@super_read_only AS super_read_only;
~~~

Xác nhận endpoint và vai trò node đúng với inventory. Kiểm tra read_only/super_read_only theo topology: source ghi có thể cho phép ghi; replica đọc thường được bảo vệ.

### 8.2. Kiểm tra lỗi và tài nguyên

- Đọc error log theo cửa sổ thời gian.
- Kiểm tra connection usage và Threads_running.
- Kiểm tra disk free, I/O latency và CPU.
- Kiểm tra deadlock, lock wait và transaction mở lâu.
- Kiểm tra slow query và top digest.
- Kiểm tra buffer pool và redo log waits.

Health check không chỉ trả “OK”. Nó cần lưu thời điểm, node, phiên bản, kết quả, các metric bất thường và người thực hiện.

### 8.3. Kiểm tra replication

Với replica, xác nhận:

- Receiver/applier đang ở trạng thái mong đợi.
- Không có lỗi IO/SQL mới.
- Executed GTID tiến triển.
- Không có GTID errant ngoài dự kiến.
- Lag trong giới hạn nghiệp vụ.
- Relay log không tăng vô hạn.

Không sửa replication khi chưa lưu trạng thái ban đầu. Nếu thread dừng, thu thập error message và GTID set trước khi restart.

### 8.4. Kiểm tra backup

Xác nhận backup mới nhất:

- Hoàn tất với exit code thành công.
- Có manifest và checksum.
- Kích thước nằm trong khoảng hợp lý.
- GTID/binlog metadata được ghi lại.
- Đã được chuyển tới kho lưu trữ.
- Không bị retention policy xóa trước thời hạn.
- Restore test gần nhất vẫn nằm trong chu kỳ được phê duyệt.

## 9. Runbook: MySQL không kết nối được

**Triệu chứng:** ứng dụng timeout hoặc báo connection refused.

**Mục tiêu:** xác định lỗi ở ứng dụng, network, proxy hay mysqld.

1. Xác nhận phạm vi ảnh hưởng: một ứng dụng, một endpoint hay mọi client.
2. Kiểm tra DNS, route, firewall, TLS và trạng thái proxy.
3. Kiểm tra process/service MySQL và error log qua kênh quản trị.
4. Nếu có quyền, xác nhận instance đang nghe đúng port và interface.
5. Kiểm tra connection pool: active, idle, pending, timeout và leak.
6. Kiểm tra Aborted_connects, connection errors và Threads_connected.
7. Không restart ngay nếu chưa thu thập error log, process state và tài nguyên.
8. Nếu instance dừng, xác định nguyên nhân trước khi start lại.
9. Sau khi endpoint hoạt động, chạy read-only health check và smoke test ứng dụng.
10. Ghi thời gian bắt đầu/kết thúc, nguyên nhân và bằng chứng.

Các truy vấn hỗ trợ:

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Threads_connected',
    'Threads_running',
    'Max_used_connections',
    'Connections',
    'Aborted_connects'
);

SHOW VARIABLES LIKE 'max_connections';
~~~

Nếu connection saturation, kiểm tra cả pool size của mọi application instance. Tăng max_connections có thể làm tăng memory pressure và không giải quyết được connection leak hoặc truy vấn bị giữ lâu.

## 10. Runbook: Truy vấn chậm hoặc latency tăng

**Triệu chứng:** p95/p99 tăng, request timeout, throughput giảm.

1. Xác định thời điểm bắt đầu và nhóm request bị ảnh hưởng.
2. So sánh latency ứng dụng với database query latency.
3. Xem CPU, disk I/O, Threads_running, connection pool wait và lock waits.
4. Lấy top query digest theo tổng thời gian và số lần chạy.
5. So sánh digest với baseline trước thay đổi gần nhất.
6. Chạy EXPLAIN cho truy vấn đại diện.
7. Kiểm tra index, statistics, rows examined, sort/temp table và data skew.
8. Kiểm tra transaction dài, lock wait và deadlock.
9. Chỉ áp dụng thay đổi sau khi có phương án kiểm thử và rollback.
10. Đo lại p95/p99, throughput và tài nguyên sau thay đổi.

Truy vấn kiểm tra digest:

~~~sql
SELECT
    DIGEST_TEXT,
    COUNT_STAR,
    AVG_TIMER_WAIT,
    MAX_TIMER_WAIT,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT
FROM performance_schema.events_statements_summary_by_digest
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 10;
~~~

Khi cần xác minh execution plan, lưu cả SQL mẫu, EXPLAIN output, schema/index liên quan và dữ liệu thống kê. Một kế hoạch có vẻ tốt trên staging chưa chắc tốt trên production nếu cardinality và phân bố dữ liệu khác nhau.

## 11. Runbook: Disk gần đầy

**Triệu chứng:** cảnh báo filesystem, ghi dữ liệu thất bại hoặc MySQL không thể tạo file tạm/redo/binlog.

1. Xác định filesystem nào gần đầy: datadir, tmpdir, relay log, binlog hay backup mount.
2. Ghi nhận free bytes, tốc độ tăng và tiến trình đang ghi.
3. Kiểm tra kích thước data, binary log, relay log, general/slow/error log và temporary files.
4. Kiểm tra backup có đang ghi dở hoặc lưu nhầm vào datadir không.
5. Kiểm tra replica có bị dừng khiến relay log tích tụ không.
6. Xác định retention policy và replica/backup nào còn cần binary log.
7. Mở rộng storage hoặc giải phóng file theo quy trình đã phê duyệt.
8. Không xóa thủ công file InnoDB, redo, undo, relay log hoặc binary log đang được MySQL quản lý.
9. Nếu purge binary log, dùng lệnh MySQL phù hợp và xác minh mọi replica/backup không còn cần log đó.
10. Sau xử lý, xác nhận disk growth ổn định và cảnh báo được đóng.

Kiểm tra binary log:

~~~sql
SHOW BINARY LOGS;
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';
SHOW VARIABLES LIKE 'log_bin_basename';
~~~

Không chạy PURGE BINARY LOGS chỉ để làm trống disk khi chưa kiểm tra replica lag và nhu cầu point-in-time recovery. Binary log có thể là phần duy nhất giúp phục hồi đến thời điểm gần sự cố.

## 12. Runbook: Replica lag hoặc applier dừng

**Triệu chứng:** truy vấn đọc trả dữ liệu cũ, replica status lỗi hoặc GTID gap tăng.

1. Xác nhận node và channel đang được kiểm tra.
2. Lưu SHOW REPLICA STATUS trước khi thay đổi.
3. Kiểm tra receiver/applier thread và lỗi gần nhất.
4. So sánh GTID_EXECUTED giữa source và replica.
5. Kiểm tra source còn binary log mà replica cần.
6. Xem CPU, I/O, network, lock và truy vấn chạy trên replica.
7. Kiểm tra DDL hoặc transaction lớn đang chặn applier.
8. Không bỏ qua transaction lỗi chỉ để thread chuyển sang Yes.
9. Nếu source đã purge log cần thiết, lập kế hoạch dựng lại replica từ backup có GTID state đúng.
10. Chờ tới GTID mục tiêu và xác minh dữ liệu trước khi đưa replica vào pool đọc.

Với MySQL 8.0.22 trở lên:

~~~sql
SHOW REPLICA STATUS\G
~~~

Kiểm tra GTID:

~~~sql
SELECT @@GLOBAL.gtid_executed,
       @@GLOBAL.gtid_purged;
~~~

Nếu replica lag, cân nhắc tạm ngừng route read traffic tới replica theo chính sách ứng dụng. Không thay đổi source/replica role trong lúc chưa xác định writer authoritative.

## 13. Runbook: Deadlock và lock wait

**Triệu chứng:** transaction thất bại với lỗi 1213 hoặc 1205, request retry tăng.

1. Thu thập mã lỗi, SQL template và request ID.
2. Kiểm tra deadlock detail trong SHOW ENGINE INNODB STATUS.
3. Xác định các transaction và index record liên quan.
4. Kiểm tra thứ tự truy cập bảng/hàng giữa các luồng.
5. Xác định truy vấn thiếu index làm khóa phạm vi lớn.
6. Giảm transaction duration và số thao tác bên ngoài transaction.
7. Chuẩn hóa thứ tự cập nhật nhiều hàng giữa các luồng.
8. Với deadlock, retry toàn bộ transaction có giới hạn và jitter nếu nghiệp vụ idempotent.
9. Với lock wait timeout, xác định transaction giữ lock trước khi điều chỉnh timeout.
10. Theo dõi deadlock rate và latency sau khi sửa.

Không retry riêng statement cuối trong một transaction đã thất bại. Với lỗi deadlock, InnoDB rollback transaction được chọn làm nạn nhân; ứng dụng cần chạy lại toàn bộ đơn vị công việc trong một transaction mới nếu phù hợp.

## 14. Thiết kế chính sách backup

Backup phải được thiết kế từ RPO/RTO và khối lượng dữ liệu.

### 14.1. Các loại backup

| Loại | Đặc điểm | Khi phù hợp |
|---|---|---|
| Logical backup | Xuất schema và dữ liệu thành SQL/dump | Di chuyển dữ liệu, khôi phục đối tượng, database nhỏ/vừa |
| Physical backup | Sao chép page/data files bằng công cụ hỗ trợ | Dataset lớn, restore nhanh hơn |
| Snapshot | Snapshot volume/storage có cơ chế consistency | Nền tảng hỗ trợ snapshot nhất quán |
| Binary log archive | Lưu chuỗi thay đổi sau backup | Point-in-time recovery |
| Replica-based backup | Backup từ replica để giảm tải source | Khi công cụ và topology bảo đảm consistency |

Một replica không phải backup độc lập. Nếu xóa nhầm dữ liệu trên source, thay đổi có thể được replicate. Cần bản backup có retention và quyền truy cập tách biệt.

### 14.2. Lập lịch và retention

Ví dụ chính sách cần điền theo RPO/RTO:

- Full backup: chu kỳ theo dung lượng và thời gian restore.
- Incremental backup: nếu công cụ hỗ trợ và quy trình đã được kiểm thử.
- Binary log archive: liên tục hoặc theo chu kỳ ngắn phù hợp RPO.
- Offsite/immutable copy: lưu ngoài failure domain của database.
- Retention: đủ cho yêu cầu khôi phục, audit và pháp lý.
- Restore drill: định kỳ và sau thay đổi lớn của công cụ/phiên bản.

Retention phải tính tới thời gian phát hiện lỗi. Nếu dữ liệu bị xóa nhầm nhưng chỉ được phát hiện sau nhiều ngày, bản backup còn lại phải đủ cũ để khôi phục trước thời điểm lỗi và đủ binary log để tiến tới điểm ngay trước thao tác sai.

### 14.3. Logical backup với mysqldump

Ví dụ cho schema InnoDB:

~~~bash
mysqldump --single-transaction \
  --routines --triggers --events \
  --hex-blob \
  --databases shop > shop.sql
~~~

--single-transaction tạo consistent snapshot cho các bảng transactional như InnoDB. Không bảo đảm nhất quán nếu trong lúc dump có DDL thay đổi cấu trúc hoặc có bảng dùng engine không transactional. Cần kiểm soát DDL và ghi rõ giới hạn của backup.

Các tùy chọn khác phụ thuộc GTID, phiên bản và mục tiêu restore. Nếu cần giữ GTID metadata, kiểm tra --set-gtid-purged và chính sách backup của tổ chức. Không bật tùy chọn GTID theo thói quen cho mọi dump, vì restore vào instance khác có thể làm thay đổi trạng thái GTID theo cách không mong muốn.

Khi backup lớn, đánh giá MySQL Shell dump utilities hoặc công cụ physical backup tương thích với phiên bản server. Chọn công cụ có hỗ trợ consistency, GTID metadata, compression, encryption và restore đã được kiểm thử.

### 14.4. Physical backup

Physical backup thường phù hợp dataset lớn khi thời gian restore là yếu tố quan trọng. Dùng công cụ được hỗ trợ cho đúng MySQL version, storage engine và nền tảng. Ví dụ có thể là MySQL Enterprise Backup hoặc Percona XtraBackup với ma trận tương thích tương ứng.

Sổ tay phải ghi:

- Phiên bản tool và server.
- Lệnh backup/prepare/copy-back đã kiểm thử.
- Điều kiện khóa hoặc flush cần thiết.
- Cách xử lý redo/undo và metadata.
- Quy trình restore lên data directory trống.
- Yêu cầu quyền filesystem và owner.
- Bước xác minh trước khi mysqld nhận traffic.

Không tự copy các file trong datadir của MySQL đang chạy bằng lệnh filesystem thông thường rồi gọi đó là physical backup nhất quán.

## 15. Bảo vệ và xác minh backup

Mỗi backup nên có manifest gồm:

| Trường | Nội dung |
|---|---|
| Backup ID | ID duy nhất |
| Source instance | Host/instance và vai trò |
| Server version | Phiên bản MySQL |
| Tool version | Phiên bản backup tool |
| Start/end time | Timestamp UTC |
| Backup type | Logical/physical/snapshot |
| Databases | Phạm vi database |
| GTID state | GTID_EXECUTED và GTID_PURGED nếu liên quan |
| Binlog coordinate | File/position hoặc thông tin GTID |
| Size | Kích thước |
| Checksum | SHA-256 hoặc checksum theo chính sách |
| Encryption | Trạng thái mã hóa và key reference |
| Storage location | URI/path nội bộ, không ghi credential |
| Exit status | Kết quả công cụ |
| Restore test | Backup đã được restore test hay chưa |

Kiểm tra checksum sau khi upload và trước khi restore. Checksum chứng minh file không thay đổi so với lúc tạo checksum; nó không chứng minh nội dung SQL hợp lệ hoặc database có thể khởi động.

Ví dụ tính SHA-256 trên Linux:

~~~bash
sha256sum shop.sql
~~~

Trên Windows PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath .\shop.sql
~~~

Backup phải được mã hóa khi truyền và khi lưu. Quyền đọc/xóa backup cần tách biệt với tài khoản ứng dụng và tài khoản MySQL thường ngày. Dùng immutable retention hoặc cơ chế chống xóa theo chính sách để giảm nguy cơ ransomware hoặc thao tác nhầm.

Không lưu password, private key hoặc nội dung secret trong manifest. Chỉ lưu tham chiếu tới secret manager.

## 16. Bằng chứng backup thành công

Một backup được coi là hoàn tất khi có đủ bằng chứng theo quy trình:

1. Job có exit code thành công.
2. Log không chứa lỗi chưa xử lý.
3. File/backup object tồn tại và kích thước hợp lý.
4. Manifest được ghi.
5. Checksum được tính và xác minh sau khi truyền.
6. GTID/binlog metadata được lưu khi cần PITR.
7. Backup nằm trong kho lưu trữ đúng retention và encryption.
8. Monitoring cập nhật trạng thái backup mới nhất.
9. Backup được chọn cho restore drill theo lịch.

Bằng chứng cần có timestamp UTC, backup ID, instance nguồn, tool version, kích thước và checksum. Không chụp màn hình duy nhất làm bằng chứng; ưu tiên log máy đọc được và metadata có thể đối chiếu.

## 17. Runbook: Restore full backup

Restore phải thực hiện trên host/instance được chỉ định và cô lập khỏi traffic production cho đến khi xác minh xong.

### 17.1. Chuẩn bị

1. Mở incident/change record và xác định người phê duyệt.
2. Xác định backup ID và manifest.
3. Kiểm tra checksum và encryption key access.
4. Xác định phiên bản MySQL tương thích với backup.
5. Chuẩn bị target có dung lượng đủ cho data, redo, temporary và binary log.
6. Cô lập target khỏi ứng dụng và replication production.
7. Ghi lại server_uuid/server_id hiện tại nếu target có dữ liệu cần giữ.
8. Xác định restore là phục hồi độc lập, thay thế source hay dựng replica.

Không restore đè lên instance đang phục vụ traffic nếu chưa có kế hoạch cutover và backup trạng thái hiện tại.

### 17.2. Restore logical dump

Với dump đã chứa CREATE DATABASE:

~~~bash
mysql < shop.sql
~~~

Nếu dump không tạo database, chọn đúng database đích trong lệnh hoặc trong dump. Kiểm tra charset, collation, user/grant, routines, triggers, events và DEFINER. Một dump dữ liệu không nhất thiết bao gồm toàn bộ cấu hình server, tài khoản hệ thống hoặc file cấu hình.

Sau restore, xác nhận:

~~~sql
SHOW DATABASES;
SHOW TABLE STATUS FROM shop;
SHOW CREATE TABLE shop.orders\G
~~~

### 17.3. Restore physical backup

Thực hiện theo tài liệu đúng phiên bản của công cụ backup:

1. Dừng mysqld trên target.
2. Chuẩn bị data directory trống và quyền filesystem phù hợp.
3. Chạy bước prepare/apply log nếu công cụ yêu cầu.
4. Copy-back/restore theo đúng công cụ.
5. Đặt owner và permission.
6. Kiểm tra cấu hình server, datadir và port.
7. Xác minh danh tính server và replication settings trước khi mở network.
8. Khởi động mysqld trong chế độ cô lập.
9. Kiểm tra error log, InnoDB recovery và dữ liệu.
10. Chỉ đưa target vào topology sau khi hoàn tất xác minh.

Không kết hợp các bước của hai công cụ backup khác nhau. Quy trình prepare và copy-back phải khớp với tool version đã tạo backup.

## 18. Point-in-time recovery (PITR)

PITR khôi phục từ full backup rồi áp dụng binary log tới một thời điểm hoặc transaction mục tiêu.

~~~mermaid
flowchart LR
    A[Full backup tại T0] --> B[Restore lên recovery target]
    B --> C[Đọc binlog sau T0]
    C --> D[Replay transaction theo thứ tự]
    D --> E[Stop trước thao tác lỗi tại T1]
    E --> F[Kiểm tra dữ liệu và ứng dụng]
    F --> G[Phê duyệt cutover]
~~~

### 18.1. Điều kiện PITR

- Full backup nhất quán và có thể restore.
- Binary log đầy đủ từ điểm backup tới điểm phục hồi.
- Binlog coordinate hoặc GTID metadata chính xác.
- Các file binlog được lưu theo thứ tự, không thiếu file.
- Công cụ mysqlbinlog tương thích.
- Điểm dừng được xác định rõ và dùng timezone thống nhất.
- Có quy trình xử lý transaction đang mở hoặc thao tác sai cần loại trừ.

Nếu binary log bị purge hoặc archive thiếu một đoạn, không thể replay liên tục qua khoảng trống đó. Đây là lý do phải kiểm tra tính liên tục của archive, không chỉ kiểm tra file mới nhất.

### 18.2. Xác định điểm dừng

Có thể chọn:

- Thời điểm UTC ngay trước thao tác gây lỗi.
- Binlog file và position đã xác minh.
- GTID/transaction boundary đã xác định.

Dùng transaction boundary an toàn để tránh dừng giữa một giao dịch. Nếu chọn thời điểm, chuyển đổi và xác nhận timezone rõ ràng; đừng dùng giờ local không kèm offset khi có DST.

Ví dụ minh họa với file binlog local đã tải về:

~~~bash
mysqlbinlog \
  --start-position=12345 \
  --stop-datetime="2026-11-19 09:55:00" \
  mysql-bin.000123 mysql-bin.000124 \
  | mysql --host=recovery-db.example.net
~~~

Các giá trị file, position và thời điểm chỉ là ví dụ. Lệnh phải được điều chỉnh theo backup metadata, file thực tế, timezone và điểm dừng đã phê duyệt. Không chạy trực tiếp trên source production để thử. Nên kiểm tra nội dung binlog trước khi replay và phục hồi trên target cô lập.

Khi dùng GTID, phải xác định transaction cần bao gồm hoặc loại trừ và tuân theo quy trình PITR của phiên bản/công cụ. Không tự chỉnh gtid_purged để làm cho lịch sử có vẻ khớp.

### 18.3. Phục hồi sau thao tác xóa nhầm

Một quy trình thường gặp:

1. Dừng hoặc hạn chế writer để tránh thay đổi thêm, nếu nghiệp vụ cho phép.
2. Xác định transaction gây xóa nhầm từ audit log, application log và binlog.
3. Chọn full backup trước thời điểm xóa.
4. Restore lên recovery instance cô lập.
5. Replay binlog tới ngay trước transaction gây lỗi.
6. Xác minh hàng cần khôi phục và các quan hệ liên quan.
7. Xuất/đối soát dữ liệu cần đưa lại production.
8. Áp dụng thay đổi có kiểm soát, có backup trước thao tác.
9. Kiểm tra foreign key, unique key, tổng tiền và trạng thái nghiệp vụ.
10. Mở lại traffic theo kế hoạch và theo dõi.

Không nhất thiết phải thay thế toàn bộ production bằng recovery instance. Nếu chỉ một tập hàng bị xóa, có thể trích xuất dữ liệu từ bản phục hồi và merge có kiểm soát. Việc merge phải xử lý ID, khóa ngoại, transaction mới phát sinh và xung đột unique.

## 19. Đo và chứng minh RPO/RTO

Sau mỗi lần restore drill, ghi:

| Mốc | Thời điểm UTC |
|---|---|
| Incident/drill bắt đầu | T0 |
| Backup được chọn | Backup timestamp |
| Restore bắt đầu | T1 |
| Restore full backup hoàn tất | T2 |
| Binlog replay bắt đầu/kết thúc | T3/T4 |
| Kiểm tra dữ liệu hoàn tất | T5 |
| Ứng dụng smoke test thành công | T6 |
| Phê duyệt phục hồi | T7 |

Tính:

- **Measured RTO:** thời gian từ mốc bắt đầu theo định nghĩa được phê duyệt đến khi dịch vụ đạt tiêu chí phục hồi.
- **Measured RPO:** khoảng cách giữa thời điểm dữ liệu mới nhất có thể khôi phục và thời điểm sự cố/điểm mất dữ liệu được xác định.

Không đo RTO chỉ bằng thời gian lệnh restore chạy. Cần tính cả thời gian phát hiện, quyết định, cấp hạ tầng, restore, replay, kiểm tra và cutover nếu các bước đó thuộc định nghĩa RTO của tổ chức.

Ví dụ báo cáo diễn tập:

| Chỉ số | Mục tiêu | Kết quả đo | Kết luận |
|---|---:|---:|---|
| RPO | 5 phút | Điền sau diễn tập | Pass/Fail |
| RTO | 60 phút | Điền sau diễn tập | Pass/Fail |
| Full restore | Theo kế hoạch | Điền thời gian | Pass/Fail |
| Binlog continuity | Không thiếu đoạn | Có/Không | Pass/Fail |
| Data validation | Không sai lệch trọng yếu | Có/Không | Pass/Fail |
| App smoke test | Tất cả bước bắt buộc thành công | Có/Không | Pass/Fail |

Không ghi Pass nếu chưa có số đo và bằng chứng. Nếu không đạt, ghi khoảng cách, nguyên nhân, owner và ngày diễn tập lại.

## 20. Bộ bằng chứng phục hồi

Một lần diễn tập được coi là có bằng chứng khi có đủ các nhóm sau:

### 20.1. Bằng chứng nguồn backup

- Backup ID và manifest.
- Instance nguồn, server version và backup tool version.
- Backup timestamp UTC.
- GTID_EXECUTED/GTID_PURGED hoặc binlog file/position.
- Kích thước và checksum.
- Log job và exit code.
- Vị trí lưu trữ, encryption status và retention.

### 20.2. Bằng chứng restore

- Recovery target và cấu hình cô lập.
- Thời điểm bắt đầu/kết thúc restore.
- Log của công cụ restore.
- Kết quả khởi động MySQL và error log.
- Phiên bản server và trạng thái InnoDB.
- GTID/binlog position sau restore.
- Dung lượng data và bảng quan trọng.

### 20.3. Bằng chứng dữ liệu

Kiểm tra row count cho các bảng quan trọng:

~~~sql
SELECT 'customers' AS table_name, COUNT(*) AS row_count
FROM shop.customers
UNION ALL
SELECT 'orders', COUNT(*)
FROM shop.orders
UNION ALL
SELECT 'order_items', COUNT(*)
FROM shop.order_items;
~~~

Row count chỉ là kiểm tra sơ bộ. Hai database có cùng số hàng nhưng nội dung khác nhau vẫn có thể sai. Bổ sung checksum theo chunk, so sánh các khóa nghiệp vụ hoặc dùng công cụ consistency check phù hợp.

Kiểm tra quan hệ không có orphan:

~~~sql
SELECT COUNT(*) AS orphan_order_items
FROM shop.order_items AS oi
LEFT JOIN shop.orders AS o
    ON o.order_id = oi.order_id
WHERE o.order_id IS NULL;
~~~

Kiểm tra tổng đơn hàng với dòng hàng theo quy tắc nghiệp vụ. Ví dụ:

~~~sql
SELECT o.order_id, o.order_number
FROM shop.orders AS o
LEFT JOIN shop.order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY
    o.order_id,
    o.order_number,
    o.subtotal,
    o.discount_amount,
    o.shipping_fee,
    o.total_amount
HAVING
    o.subtotal <> COALESCE(SUM(oi.quantity * oi.unit_price), 0.00)
    OR o.discount_amount <> COALESCE(SUM(oi.discount_amount), 0.00)
    OR o.total_amount <>
       COALESCE(SUM(oi.line_total), 0.00) + o.shipping_fee;
~~~

Điều chỉnh truy vấn theo schema và các loại phí/thuế thực tế. Một kiểm tra chỉ có giá trị nếu nó phản ánh đúng invariant nghiệp vụ.

### 20.4. Bằng chứng ứng dụng

- Ứng dụng kết nối đúng endpoint recovery/cutover.
- Các truy vấn đọc/ghi smoke test thành công.
- Tạo một giao dịch thử theo quy trình an toàn nếu được phép.
- Kiểm tra quyền user, stored routine, trigger, event và DEFINER.
- Kiểm tra charset, collation, SQL mode và timezone.
- Kiểm tra job/queue không phát sinh hành động ngoài ý muốn trong môi trường test.
- Nếu có replica, xác minh replication sau khi cấu hình lại.

Không đưa dữ liệu cá nhân hoặc secret vào ảnh chụp màn hình/báo cáo. Dùng ID test và dữ liệu đã mask.

## 21. Failover và đưa dịch vụ trở lại

Failover là chuyển vai trò writer sang node khác; đây là thay đổi topology có rủi ro split-brain. Sổ tay cần chỉ định rõ người có quyền phê duyệt và công cụ điều phối.

Trước promote:

1. Xác định source cũ có còn nhận ghi không.
2. Fencing source cũ hoặc bảo đảm nó không thể tiếp tục nhận ghi.
3. Chọn replica có GTID đã áp dụng phù hợp nhất.
4. Xác minh không có transaction cần thiết còn ở relay log chưa được áp dụng.
5. Kiểm tra server_uuid/server_id và tình trạng node.
6. Thực hiện promote theo quy trình đã kiểm thử.
7. Chuyển endpoint ghi qua proxy/DNS/service discovery.
8. Cấu hình các replica còn lại theo source mới.
9. Kiểm tra ứng dụng và transaction mới.
10. Lưu GTID set trước/sau và thời gian cutover.

Không promote chỉ vì một replica có lag thấp hơn ở một lần đọc status. Cần kiểm tra GTID và đảm bảo source cũ đã được fencing. Nếu không thể xác định node authoritative, dừng thay đổi tự phát và escalation theo incident commander.

Sau failover, không vội đưa node cũ trở lại làm replica. Trước hết phải xác định dữ liệu và GTID của nó có thể rejoin an toàn hay cần dựng lại từ backup/clone mới.

## 22. Quyền truy cập và an toàn vận hành

Sổ tay nên mô tả quyền theo vai trò:

| Vai trò | Quyền điển hình | Giới hạn |
|---|---|---|
| Application user | SELECT/INSERT/UPDATE/DELETE trên schema cần thiết | Không có quyền quản trị, không cấp SUPER |
| Read-only analyst | SELECT trên schema/view được phép | Không ghi, không xem dữ liệu ngoài phạm vi |
| Backup agent | Quyền cần thiết cho công cụ backup | Không dùng tài khoản ứng dụng |
| Monitoring agent | Đọc status/Performance Schema theo yêu cầu exporter | Không cấp quyền ghi dữ liệu |
| DBA operator | Thao tác vận hành theo quy trình | Dùng tài khoản cá nhân, audit và approval |
| Emergency admin | Quyền cao nhất khi có sự cố | Cất trong vault, dùng có thời hạn và hậu kiểm |

Các nguyên tắc:

- Least privilege: chỉ cấp quyền cần cho công việc.
- Tài khoản cá nhân cho thao tác quản trị; tránh dùng chung account.
- Secret trong secret manager, rotate theo chính sách.
- TLS cho kết nối qua mạng.
- Audit thay đổi quyền và cấu hình.
- Không chia sẻ mật khẩu trong ticket, chat hoặc runbook.
- Dùng read-only query khi chỉ cần điều tra.
- Ghi rõ lệnh có tác động ghi, restart, failover, purge hoặc reset.

Các lệnh như KILL, SET GLOBAL, ALTER USER, PURGE BINARY LOGS, RESET REPLICA và thao tác DDL phải được phân loại theo mức rủi ro, quyền cần thiết và yêu cầu phê duyệt.

## 23. Ma trận mức độ sự cố và escalation

| Mức | Ví dụ | Phản hồi |
|---|---|---|
| SEV-1 | Writer unavailable, mất dữ liệu đang diễn ra, nghi split-brain | Kích hoạt incident commander, DBA on-call và owner nghiệp vụ ngay |
| SEV-2 | Replica toàn bộ dừng, disk gần đầy, backup không có bản mới | DBA on-call xử lý khẩn, thông báo owner và đánh giá RPO |
| SEV-3 | Slow query ảnh hưởng một phần workload, lag tăng nhưng còn trong giới hạn | Nhóm database điều tra theo runbook |
| SEV-4 | Cảnh báo xu hướng, dung lượng hoặc backup drill sắp quá hạn | Tạo task có owner và deadline |

Mỗi tổ chức cần điền thời gian phản hồi, kênh liên hệ và người thay thế. Không để số điện thoại cá nhân hoặc thông tin nhạy cảm trong tài liệu có quyền truy cập rộng; dùng danh bạ nội bộ được kiểm soát.

## 24. Lịch vận hành định kỳ

Một lịch tham khảo:

| Chu kỳ | Công việc | Bằng chứng |
|---|---|---|
| Mỗi ca trực | Kiểm tra availability, alert, replication, backup freshness | Health check record |
| Hàng ngày | Kiểm tra backup, binlog archive, disk trend, lỗi mới | Dashboard snapshot/log |
| Hàng tuần | Review slow query, deadlock, connection pool, dung lượng | Performance review |
| Hàng tháng | Kiểm tra user/grant, retention, capacity forecast, alert noise | Access/capacity report |
| Hàng quý | Restore drill và đo RPO/RTO | Restore evidence pack |
| Sau nâng cấp | Regression test, backup/restore test, replication validation | Change validation |
| Sau failover | Rejoin/repair replica, rà soát GTID và dữ liệu | Failover report |

Chu kỳ thực tế phải phù hợp criticality và chính sách. Một dịch vụ thanh toán có thể cần diễn tập thường xuyên hơn một hệ thống báo cáo ít quan trọng.

## 25. Mẫu incident record

Mỗi sự cố cần một hồ sơ có cấu trúc:

| Trường | Nội dung |
|---|---|
| Incident ID | Mã sự cố |
| Severity | SEV-1/2/3/4 |
| Start/end UTC | Thời điểm bắt đầu và kết thúc |
| Affected service | Dịch vụ và môi trường |
| Symptoms | Triệu chứng quan sát được |
| Business impact | Người dùng/giao dịch bị ảnh hưởng |
| Detection | Alert, người báo hay health check |
| Timeline | Các mốc và hành động |
| Evidence | Log, metric, query, GTID, backup ID |
| Root cause | Nguyên nhân đã xác minh hoặc giả thuyết |
| Resolution | Hành động khắc phục |
| Data integrity | Cách xác minh dữ liệu |
| RPO/RTO | Kết quả nếu có phục hồi |
| Follow-up | Việc cần làm, owner và deadline |

Phân biệt dữ kiện đã xác minh với giả thuyết. Không ghi nguyên nhân gốc là “MySQL bị lỗi” nếu chưa có bằng chứng cụ thể.

## 26. Bài thực hành: hoàn thiện sổ tay cho một dịch vụ mẫu

Giả sử hệ thống có một MySQL source, hai replica, ứng dụng Spring Boot và backup hằng ngày kèm binary log archive. Thực hiện lần lượt:

### Bước 1 — Inventory và topology

- Điền server version, server_id, server_uuid cho ba node.
- Vẽ endpoint ghi/đọc và luồng replication.
- Ghi network boundary, proxy và backup storage.
- Xác định writer authoritative và cơ chế fencing.

### Bước 2 — Chọn metric

Tối thiểu phải có:

- Availability probe.
- p95/p99 application latency.
- QPS và transaction rate.
- Connection usage và pool wait.
- CPU, memory, disk free và I/O latency.
- Slow query digest, rows examined.
- Deadlock/lock wait.
- Replica thread state, GTID gap và lag.
- Backup age, checksum và restore drill age.

Mỗi metric ghi đơn vị, nguồn, tần suất scrape, nhãn instance và người chịu trách nhiệm.

### Bước 3 — Thiết lập dashboard và alert

- Tạo overview dashboard.
- Tạo performance dashboard.
- Tạo replication dashboard.
- Tạo backup/recovery dashboard.
- Viết runbook cho từng alert.
- Diễn tập một alert giả lập trong staging để xác nhận kênh nhận thông báo.

### Bước 4 — Viết runbook

Hoàn thiện tối thiểu các quy trình:

- MySQL không kết nối được.
- Connection pool cạn.
- Query latency tăng.
- Disk gần đầy.
- Deadlock/lock wait tăng.
- Replica lag hoặc applier dừng.
- Backup thất bại.
- Restore full backup.
- PITR sau thao tác xóa nhầm.
- Failover và rejoin replica.

Mỗi runbook cần có lệnh kiểm tra, kết quả mong đợi, quyền cần thiết, bước escalation và điều kiện dừng.

### Bước 5 — Diễn tập restore

- Chọn backup và xác minh manifest/checksum.
- Restore lên target cô lập.
- Replay binary log tới điểm đã chọn.
- Chạy row count, checksum và business invariants.
- Chạy smoke test ứng dụng.
- Đo RPO/RTO.
- Lưu bằng chứng và ghi khoảng cách so với mục tiêu.

### Bước 6 — Review và bàn giao

- DBA và owner nghiệp vụ rà soát.
- Kiểm tra mọi URL, host và account có thể truy cập đúng phạm vi.
- Kiểm tra runbook không chứa secret.
- Gán owner cho mọi mục còn thiếu.
- Đặt ngày review tiếp theo và version của sổ tay.

## 27. Mẫu checklist trước khi đóng một sự cố

- [ ] Dịch vụ và node đã trở về trạng thái mong đợi.
- [ ] Writer authoritative đã được xác nhận.
- [ ] Không còn source cũ nhận ghi ngoài ý muốn.
- [ ] Replica đã theo kịp GTID mục tiêu.
- [ ] Không còn lỗi IO/SQL/applier chưa xử lý.
- [ ] Dữ liệu quan trọng đã được đối soát.
- [ ] Backup mới sau sự cố đã hoàn tất và được xác minh.
- [ ] Dashboard và alert đã trở về trạng thái ổn định.
- [ ] Ứng dụng smoke test thành công.
- [ ] RPO/RTO được đo nếu sự cố có phục hồi dữ liệu.
- [ ] Timeline, log, metric và quyết định đã được lưu.
- [ ] Follow-up có owner và deadline.

## 28. Checklist hoàn thiện sổ tay vận hành

- [ ] Có service owner, technical owner và on-call.
- [ ] Có phiên bản MySQL, Connector/J và backup tool.
- [ ] Có inventory instance với server_id/server_uuid.
- [ ] Có sơ đồ kiến trúc và luồng đọc/ghi.
- [ ] Có sơ đồ backup, binlog archive và recovery target.
- [ ] Có RPO/RTO được nghiệp vụ phê duyệt.
- [ ] Có danh mục metric và đơn vị đo.
- [ ] Có dashboard availability, performance, replication và backup.
- [ ] Có alert gắn runbook và escalation.
- [ ] Có health check read-only.
- [ ] Có runbook cho connection, slow query, disk, lock và replication.
- [ ] Có chính sách backup/retention và binary log retention.
- [ ] Có manifest, checksum và mã hóa backup.
- [ ] Có restore procedure cho logical/physical backup phù hợp.
- [ ] Có PITR procedure với điểm dừng và timezone rõ ràng.
- [ ] Có restore drill và bằng chứng data validation.
- [ ] Có kết quả RPO/RTO đo được.
- [ ] Có quy trình failover, fencing và rejoin.
- [ ] Có ma trận quyền và secret handling.
- [ ] Có lịch vận hành và lịch review.
- [ ] Có incident record template.
- [ ] Có owner/deadline cho các khoảng trống chưa giải quyết.

## 29. Tự kiểm tra

1. Vì sao replica không thể thay thế một bản backup độc lập?
2. Một sơ đồ kiến trúc vận hành MySQL cần thể hiện những endpoint và luồng dữ liệu nào?
3. Threads_connected khác Threads_running như thế nào?
4. Vì sao QPS tăng không nhất thiết có nghĩa hệ thống nhanh hơn?
5. Nên kết hợp những metric nào để điều tra slow query?
6. Vì sao Seconds_Behind_Source không nên là nguồn chân lý duy nhất về replication lag?
7. Một backup có checksum đúng đã đủ chứng minh có thể restore chưa? Vì sao?
8. RPO và RTO khác nhau thế nào, và cần đo từ những mốc nào?
9. PITR cần những metadata và file nào để replay đúng từ full backup?
10. Vì sao phải fencing source cũ trước khi promote replica?
11. Bằng chứng nào chứng minh dữ liệu sau restore đúng với quy tắc nghiệp vụ?
12. Hãy xây dựng dashboard và ba alert quan trọng nhất cho một MySQL service có RPO 5 phút, RTO 60 phút.

Sổ tay vận hành hoàn chỉnh phải nối được kiến trúc, metric, hành động và bằng chứng. Người trực cần biết node nào là writer, dấu hiệu nào cho thấy hệ thống đang bão hòa, lệnh nào an toàn để kiểm tra, khi nào phải escalation và cách phục hồi đã được chứng minh. Chỉ khi backup được restore thử, dữ liệu được đối soát và RPO/RTO được đo, nhóm mới có cơ sở tin rằng quy trình phục hồi đáp ứng yêu cầu dịch vụ.

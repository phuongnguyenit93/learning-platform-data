# Phân biệt chờ khóa với thiếu kết nối, CPU hoặc I/O

Khi ứng dụng truy cập database chậm, triệu chứng thường thấy là request mất nhiều thời gian, truy vấn timeout, connection pool cạn hoặc throughput giảm. Những biểu hiện này chưa cho biết nguyên nhân gốc. Một request có thể chậm vì phải đợi transaction khác nhả khóa, vì không lấy được connection từ pool, vì database thiếu CPU, vì đọc/ghi đĩa chậm hoặc vì dữ liệu phải truyền qua mạng quá lâu.

Muốn chẩn đoán đúng, cần xác định **thời gian bị tiêu tốn ở đâu** và **tài nguyên nào đang khiến công việc không thể tiến lên**. Không nên thấy connection pool đầy rồi kết luận database thiếu connection; pool có thể đầy vì các connection đang bị giữ trong lúc truy vấn chờ khóa. Cũng không nên thấy query chạy lâu rồi kết luận thiếu I/O; truy vấn có thể đang đợi một transaction khác.

Bốn nhóm cần phân biệt:

- **Chờ khóa (lock wait):** transaction cần tài nguyên đang bị transaction khác giữ.
- **Thiếu hoặc chờ connection:** ứng dụng không lấy được connection từ pool, không mở được kết nối tới database hoặc database đã gần/vượt giới hạn session.
- **Bão hòa CPU:** database có nhiều công việc cần xử lý hơn khả năng CPU hiện tại, hoặc một số truy vấn tiêu thụ CPU quá lớn.
- **Nút thắt I/O:** đọc/ghi dữ liệu, transaction log hoặc storage chậm; truy vấn phải đợi dữ liệu hoặc thao tác ghi hoàn tất.

Các nhóm này có thể xảy ra cùng lúc. Ví dụ, truy vấn giữ khóa lâu vì quét bảng lớn do thiếu chỉ mục; việc quét bảng làm tăng I/O, transaction khác phải chờ khóa, connection pool giữ nhiều connection lâu và cuối cùng request mới timeout khi lấy connection. Chẩn đoán cần tìm chuỗi nguyên nhân, không chỉ chọn một chỉ số đang cao.

## 1. Bắt đầu từ đường đi của một request

Một request dùng database thường đi qua các giai đoạn:

```text
HTTP request đến ứng dụng
        |
        v
Chờ lấy connection từ pool
        |
        v
Mở connection / xác thực nếu cần
        |
        v
Gửi SQL tới database
        |
        v
Database lập kế hoạch và thực thi
   |       |        |         |
   |       |        |         +-- chờ I/O
   |       |        +------------ chờ khóa
   |       +--------------------- dùng CPU
   +---------------------------- chờ tài nguyên khác
        |
        v
Đọc kết quả và truyền qua mạng
        |
        v
Trả connection về pool
        |
        v
HTTP response hoàn tất
```

Thời gian request có thể được phân rã thành:

- `pool_acquire_time`: thời gian chờ lấy connection.
- `connect_time`: thời gian tạo kết nối, DNS/TCP/TLS và xác thực khi cần mở connection mới.
- `query_execution_time`: thời gian database thực thi câu lệnh, bao gồm cả thời gian chờ khóa và I/O.
- `result_fetch_time`: thời gian đọc hết kết quả từ driver.
- `application_processing_time`: thời gian xử lý trước/sau database.

Không phải thư viện nào cũng cung cấp sẵn mọi span này. Có thể dùng metrics của connection pool, tracing ở JDBC/driver và thống kê của database để tách chúng ra.

Ví dụ: request mất 8 giây nhưng SQL chỉ thực thi 100 ms; nếu `pool_acquire_time` chiếm 7,5 giây thì vấn đề nằm trước khi SQL được gửi. Ngược lại, nếu pool acquire chỉ 2 ms nhưng SQL chạy 7 giây và database báo `LCK_M_X`, cần điều tra khóa.

## 2. Bảng dấu hiệu ban đầu

| Nhóm nguyên nhân | Dấu hiệu ở ứng dụng | Dấu hiệu ở database/hệ điều hành | Câu hỏi đầu tiên |
|---|---|---|---|
| Lock wait | Request liên quan cùng dữ liệu bị treo; timeout có tính chọn lọc | Có session bị block, wait type/event liên quan lock | Session nào giữ khóa và vì sao chưa kết thúc transaction? |
| Pool/connection | `getConnection()` hoặc pool acquire timeout; pending borrowers tăng | Số session cao hoặc database từ chối kết nối; đôi khi database vẫn nhàn rỗi | Ứng dụng đang chờ pool hay database đang từ chối mở connection? |
| CPU | Nhiều truy vấn cùng chậm; throughput giảm dù ít lock wait | CPU cao, runnable queue tăng, truy vấn active dùng CPU | SQL nào tiêu thụ CPU và kế hoạch thực thi có hợp lý không? |
| I/O | Truy vấn đọc dữ liệu lớn hoặc ghi commit chậm | Storage latency/queue cao, wait đọc page hoặc ghi log | Đang chờ data file, transaction log hay thiết bị lưu trữ? |

Các dấu hiệu chỉ là định hướng. CPU cao có thể làm blocker giữ khóa lâu hơn; lock wait có thể là hậu quả của truy vấn bị chậm bởi I/O. Hãy kiểm tra cùng một khoảng thời gian và cùng một operation.

## 3. Chờ khóa: tìm waiter và blocker

Một lock wait xảy ra khi transaction cần khóa không tương thích với khóa đang được transaction khác giữ. Session đang chờ là **waiter/blocked session**; session giữ khóa gây chặn là **blocker/blocking session**.

```text
T1: BEGIN
T1: UPDATE account SET balance = ... WHERE id = 10
T1: chưa COMMIT, vẫn giữ khóa trên hàng account(10)

T2: BEGIN
T2: UPDATE account SET balance = ... WHERE id = 10
T2: chờ T1 nhả khóa
```

Nếu chỉ nhìn T2, có thể thấy truy vấn đang chạy rất lâu. Nhưng T2 không nhất thiết đang dùng CPU hoặc đọc đĩa; nó đang đợi T1. Tìm blocker thường cho biết nguyên nhân trực tiếp hơn là tối ưu câu SQL của waiter.

Hãy thu thập:

- ID session của waiter và blocker.
- Loại khóa hoặc tài nguyên bị chặn: row/key, page, table, metadata hay schema.
- Thời gian chờ và wait type/event.
- SQL hiện tại của waiter và SQL gần nhất của blocker.
- Transaction của blocker bắt đầu từ lúc nào, đang mở bao lâu và có ở trạng thái idle không.
- Blocker có phải đầu chuỗi blocking hay chỉ là một waiter bị session khác chặn tiếp.
- Mức cô lập, access path và chỉ mục của các câu lệnh liên quan.

Một blocker có thể chặn nhiều session tạo thành **blocking chain**. Session đứng đầu chuỗi thường là nơi cần điều tra trước. Tuy nhiên, blocker không nhất thiết đang chạy SQL; nó có thể đã chạy xong câu lệnh nhưng vẫn để transaction mở.

### SQL Server: request đang chờ và blocker

```sql
SELECT
    r.session_id,
    r.blocking_session_id,
    r.status,
    r.command,
    r.wait_type,
    r.wait_time,
    r.wait_resource,
    r.cpu_time,
    r.total_elapsed_time,
    DB_NAME(r.database_id) AS database_name,
    s.host_name,
    s.program_name,
    s.login_name,
    txt.text AS sql_text
FROM sys.dm_exec_requests AS r
JOIN sys.dm_exec_sessions AS s
  ON s.session_id = r.session_id
OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) AS txt
WHERE r.session_id <> @@SPID
ORDER BY r.wait_time DESC;
```

Các wait type bắt đầu bằng `LCK_M_` thường chỉ ra lock wait, ví dụ `LCK_M_X`, `LCK_M_S`, `LCK_M_U`. `blocking_session_id` giúp tìm session chặn. Giá trị 0 hoặc NULL thường không cho biết blocker trực tiếp; cần đọc cùng trạng thái request và DMV khác.

Để xem các khóa đang chờ:

```sql
SELECT
    request_session_id,
    resource_type,
    request_mode,
    request_status,
    resource_description
FROM sys.dm_tran_locks
WHERE request_status = 'WAIT'
ORDER BY request_session_id;
```

Để tìm transaction đang mở lâu và session liên quan:

```sql
SELECT
    st.session_id,
    at.transaction_id,
    at.transaction_begin_time,
    DATEDIFF(SECOND, at.transaction_begin_time, SYSDATETIME()) AS transaction_age_seconds,
    s.status AS session_status,
    s.host_name,
    s.program_name,
    s.login_name
FROM sys.dm_tran_active_transactions AS at
JOIN sys.dm_tran_session_transactions AS st
  ON st.transaction_id = at.transaction_id
JOIN sys.dm_exec_sessions AS s
  ON s.session_id = st.session_id
ORDER BY at.transaction_begin_time;
```

Các DMV này cần quyền xem trạng thái server phù hợp. Không kết luận chỉ từ một snapshot; lấy lại thông tin sau một khoảng ngắn để xem session còn chờ hay blocker đã thay đổi.

### PostgreSQL: pg_stat_activity và pg_blocking_pids

PostgreSQL cho biết session đang chờ qua `wait_event_type` và `wait_event`. `wait_event_type = 'Lock'` là dấu hiệu quan trọng của lock wait.

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    now() - xact_start AS transaction_age,
    pg_blocking_pids(pid) AS blocking_pids,
    query
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
ORDER BY query_start NULLS LAST;
```

Nếu `wait_event_type = 'Lock'`, hãy lấy PID trong `pg_blocking_pids(pid)` rồi truy vấn các PID đó trong `pg_stat_activity`. Chú ý `state = 'idle in transaction'`: session có thể không chạy SQL nhưng vẫn giữ transaction và khóa.

Có thể đối chiếu lock đang tồn tại:

```sql
SELECT
    l.pid,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.query
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a
  ON a.pid = l.pid
WHERE NOT l.granted
   OR l.pid IN
      (SELECT unnest(pg_blocking_pids(pid))
       FROM pg_stat_activity);
```

### MySQL InnoDB: data_lock_waits

Trong MySQL 8, Performance Schema cung cấp quan hệ giữa transaction đang chờ và transaction giữ khóa:

```sql
SELECT
    req.ENGINE_TRANSACTION_ID AS waiting_trx_id,
    req.THREAD_ID AS waiting_thread_id,
    req.OBJECT_SCHEMA,
    req.OBJECT_NAME,
    req.INDEX_NAME,
    req.LOCK_TYPE,
    req.LOCK_MODE AS waiting_lock_mode,
    blk.ENGINE_TRANSACTION_ID AS blocking_trx_id,
    blk.THREAD_ID AS blocking_thread_id,
    blk.LOCK_MODE AS blocking_lock_mode
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS req
  ON req.ENGINE = w.ENGINE
 AND req.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS blk
  ON blk.ENGINE = w.ENGINE
 AND blk.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID;
```

Để liên kết thread với câu SQL đang chạy, xem `performance_schema.threads` và `events_statements_current`, hoặc dùng view `sys.innodb_lock_waits` nếu phiên bản có cung cấp. Trên bản MySQL cũ hơn, cách hiển thị lock wait có thể khác; `SHOW ENGINE INNODB STATUS` cũng hữu ích để xem transaction và deadlock gần nhất.

## 4. Thiếu connection: phân biệt pool wait với database connection limit

“Thiếu connection” thường chỉ ít nhất hai vấn đề:

1. **Ứng dụng không lấy được connection từ pool:** connection đang được request khác mượn, pool đã đạt `maximumPoolSize`, hoặc connection bị giữ quá lâu.
2. **Ứng dụng không mở được connection mới tới database:** database chạm giới hạn session, mạng/DNS/TLS lỗi, xác thực thất bại hoặc database không chấp nhận kết nối.

Nếu pool acquire timeout, request thường chưa gửi SQL tới database. Nếu database từ chối kết nối mới, driver có thể báo lỗi ở giai đoạn connect/authentication. Nếu connection đã được cấp nhưng câu SQL đang chờ lock, đó không phải pool acquisition wait dù connection pool vẫn có thể dần cạn vì các connection bị giữ lâu.

### Metrics của connection pool

Với HikariCP, theo dõi tối thiểu:

- `active`: số connection đang được ứng dụng mượn.
- `idle`: số connection sẵn sàng trong pool.
- `pending`: số thread đang chờ connection.
- `max`: giới hạn connection của pool.
- `connection acquire time`: thời gian từ lúc yêu cầu connection đến lúc được cấp.
- `usage time`: thời gian connection được giữ trước khi trả về pool.
- `creation time` và lỗi tạo connection: thời gian mở connection mới và lỗi connect.

| Quan sát | Diễn giải cần kiểm tra |
|---|---|
| `active = max`, `idle = 0`, `pending > 0` | Pool bão hòa; tìm connection đang bị giữ ở đâu |
| `active` thấp, `pending = 0`, acquire nhanh | Pool không phải nút thắt chính tại thời điểm đo |
| Connection creation chậm/lỗi | Kiểm tra DNS, TCP, TLS, xác thực, database listener và giới hạn kết nối |
| `usage time` tăng, active giữ lâu | SQL chậm, lock wait, ứng dụng giữ connection quá lâu hoặc transaction mở lâu |
| Pool full cùng lúc database có nhiều lock waiter | Pool exhaustion có thể là hậu quả của lock contention |

Không tăng `maximumPoolSize` ngay khi pool đầy. Nếu database đã bão hòa CPU, I/O hoặc khóa, tăng pool có thể đưa thêm request vào database và làm tình trạng tệ hơn. Hãy xác định connection đang được giữ bởi SQL nào, transaction nào hoặc đoạn code nào.

### Kiểm tra session và giới hạn kết nối ở database

**SQL Server:**

```sql
SELECT
    status,
    program_name,
    host_name,
    COUNT(*) AS session_count
FROM sys.dm_exec_sessions
WHERE is_user_process = 1
GROUP BY status, program_name, host_name
ORDER BY session_count DESC;
```

**PostgreSQL:**

```sql
SELECT
    state,
    application_name,
    usename,
    COUNT(*) AS connection_count
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY state, application_name, usename
ORDER BY connection_count DESC;

SHOW max_connections;
```

**MySQL:**

```sql
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Threads_running';
SHOW VARIABLES LIKE 'max_connections';
```

Các lệnh trên cho biết session/connection đang tồn tại và giới hạn cấu hình; chúng không thay thế metrics ở pool. Một ứng dụng có thể hết pool dù database vẫn còn khả năng nhận thêm connection, hoặc database hết giới hạn dù pool phía ứng dụng còn idle connection stale.

## 5. Bão hòa CPU: truy vấn đang tính toán thay vì chờ khóa

Khi CPU database bão hòa, nhiều truy vấn có thể chậm cùng lúc. Các session vẫn ở trạng thái active, nhưng không nhất thiết có blocker. Database có thể có nhiều công việc runnable đang tranh CPU, hoặc một số truy vấn dùng CPU quá nhiều vì scan, join, sort, aggregate, biểu thức tốn kém hay kế hoạch thực thi không phù hợp.

Dấu hiệu CPU:

- CPU của máy/database service duy trì ở mức cao đúng lúc request chậm.
- Runnable queue hoặc scheduler pressure tăng.
- Nhiều truy vấn active có `cpu_time` tăng nhanh nhưng không có wait event lock.
- Top SQL theo CPU tập trung vào một vài câu lệnh hoặc workload.
- Throughput không tăng dù tăng số worker/connection.
- Thời gian query tăng trên nhiều request cùng lúc, kể cả các hàng không liên quan nhau.

CPU cao không nhất thiết là database cần thêm vCPU. Một query plan kém, thiếu index, cardinality estimate sai hoặc truy vấn lặp N+1 có thể tạo tải CPU không cần thiết.

### SQL Server: CPU của request và scheduler

```sql
SELECT
    r.session_id,
    r.status,
    r.command,
    r.cpu_time,
    r.total_elapsed_time,
    r.wait_type,
    r.wait_time,
    r.logical_reads,
    r.reads,
    r.writes,
    DB_NAME(r.database_id) AS database_name,
    txt.text AS sql_text
FROM sys.dm_exec_requests AS r
OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) AS txt
WHERE r.session_id <> @@SPID
ORDER BY r.cpu_time DESC;
```

`SOS_SCHEDULER_YIELD` có thể xuất hiện khi worker đã dùng hết quantum CPU và nhường scheduler. Đây là dấu hiệu cần điều tra CPU pressure, nhưng một wait type đơn lẻ không chứng minh toàn server thiếu CPU. Hãy đối chiếu CPU host, runnable tasks và top query theo CPU.

### PostgreSQL: active query và thống kê câu lệnh

Trong `pg_stat_activity`, session `state = 'active'` mà `wait_event` là NULL có thể đang thực thi trên CPU hoặc chưa ở trạng thái chờ được ghi nhận. Cần kết hợp với CPU host, query duration và thống kê statement; không kết luận CPU chỉ từ `wait_event IS NULL`.

Nếu đã cài `pg_stat_statements`, xem các truy vấn tiêu thụ thời gian thực thi:

```sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    query
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

`total_exec_time` là tổng thời gian thực thi theo thống kê extension, không phải CPU time thuần. Hãy dùng nó để tìm ứng viên rồi xem `EXPLAIN (ANALYZE, BUFFERS)` trên truy vấn đại diện ở môi trường an toàn.

### MySQL: statement digest và CPU host

MySQL Performance Schema có thể tổng hợp statement theo digest:

```sql
SELECT
    SCHEMA_NAME,
    DIGEST_TEXT,
    COUNT_STAR,
    SUM_TIMER_WAIT,
    AVG_TIMER_WAIT,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT
FROM performance_schema.events_statements_summary_by_digest
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
```

`SUM_TIMER_WAIT` là thời gian được ghi nhận cho statement event, không phải CPU time thuần. Hãy đối chiếu với CPU host và execution plan để xác định CPU là nút thắt hay query đang chờ tài nguyên khác.

## 6. Nút thắt I/O: phân biệt data file, log và mạng

I/O không chỉ là “đĩa chậm”. Database có thể chờ:

- **Data read:** đọc page từ data file khi page chưa có trong buffer cache.
- **Data write/checkpoint:** ghi page đã thay đổi về data file.
- **Transaction log write/flush:** ghi log bền vững trước khi commit được xác nhận.
- **Temp/work files:** sort, hash hoặc spill trung gian ra storage.
- **Network I/O:** truyền dữ liệu giữa ứng dụng và database hoặc giữa database nodes.

Một transaction cập nhật ít hàng vẫn có thể commit chậm nếu log storage có độ trễ cao. Một truy vấn báo cáo có thể đọc nhiều page và bị giới hạn bởi data storage. Hai trường hợp đều có thể làm query chậm nhưng cách khắc phục khác nhau.

Dấu hiệu I/O:

- CPU không quá cao nhưng query elapsed time lớn.
- Storage latency, queue depth hoặc throughput bất thường.
- Wait event chỉ ra chờ data file, log flush hoặc temp I/O.
- Truy vấn đọc nhiều page, cache hit thấp hoặc spill ra temp storage.
- Commit latency tăng đồng loạt, đặc biệt với transaction có ghi.
- I/O chậm kéo dài transaction và gián tiếp làm tăng lock wait.

### SQL Server: PAGEIOLATCH và WRITELOG

Một số wait type thường gặp:

- `PAGEIOLATCH_SH` / `PAGEIOLATCH_EX`: chờ page được đọc vào buffer hoặc I/O liên quan page latch.
- `WRITELOG`: chờ ghi/flush transaction log.
- `IO_COMPLETION`: chờ một thao tác I/O hoàn tất, cần xem thêm ngữ cảnh.

Các wait type này cần được đọc cùng file I/O latency và truy vấn đang chạy. `PAGEIOLATCH_*` cao có thể phản ánh đọc vật lý chậm hoặc workload đọc nhiều page; không tự động có nghĩa storage hỏng. `WRITELOG` cao thường hướng điều tra về log throughput/latency, transaction commit frequency và cấu hình log storage.

Xem thống kê I/O file:

```sql
SELECT
    DB_NAME(vfs.database_id) AS database_name,
    mf.type_desc,
    mf.physical_name,
    vfs.num_of_reads,
    vfs.io_stall_read_ms,
    CASE WHEN vfs.num_of_reads = 0 THEN 0
         ELSE vfs.io_stall_read_ms * 1.0 / vfs.num_of_reads END AS avg_read_ms,
    vfs.num_of_writes,
    vfs.io_stall_write_ms,
    CASE WHEN vfs.num_of_writes = 0 THEN 0
         ELSE vfs.io_stall_write_ms * 1.0 / vfs.num_of_writes END AS avg_write_ms
FROM sys.dm_io_virtual_file_stats(NULL, NULL) AS vfs
JOIN sys.master_files AS mf
  ON mf.database_id = vfs.database_id
 AND mf.file_id = vfs.file_id
ORDER BY avg_read_ms DESC;
```

Các bộ đếm trong DMV là số liệu tích lũy kể từ lần thống kê được khởi tạo/reset. Muốn biết I/O hiện tại, hãy lấy hai snapshot cách nhau một khoảng thời gian rồi tính delta; không so sánh trực tiếp tổng tích lũy giữa hai database có tuổi khác nhau.

### PostgreSQL: wait event I/O và buffer statistics

Trong PostgreSQL, `pg_stat_activity` có thể cho biết session đang chờ I/O qua `wait_event_type = 'IO'` và tên `wait_event` phù hợp phiên bản. Ví dụ:

```sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    query
FROM pg_stat_activity
WHERE state = 'active'
  AND wait_event_type = 'IO'
ORDER BY query_start;
```

Ở các phiên bản PostgreSQL hỗ trợ `pg_stat_io`, có thể xem I/O theo backend/object/context:

```sql
SELECT *
FROM pg_stat_io
ORDER BY backend_type, object, context;
```

Schema và các cột `pg_stat_io` phụ thuộc phiên bản. Đối chiếu thêm `EXPLAIN (ANALYZE, BUFFERS)`, thống kê block read/hit và metrics storage. `shared_blks_read` không đồng nghĩa mọi block đều phải đọc trực tiếp từ đĩa vật lý; kernel cache và các tầng storage cache cũng ảnh hưởng.

### MySQL: Performance Schema và InnoDB

MySQL có thể hiển thị các sự kiện chờ file trong Performance Schema nếu instrumentation được bật:

```sql
SELECT
    EVENT_NAME,
    COUNT_STAR,
    SUM_TIMER_WAIT,
    AVG_TIMER_WAIT
FROM performance_schema.events_waits_summary_global_by_event_name
WHERE EVENT_NAME LIKE 'wait/io/file/%'
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
```

Các sự kiện file wait có thể liên quan data file, redo log hoặc file khác. Cần liên kết với `performance_schema.file_summary_by_instance`, InnoDB metrics, query digest và storage telemetry để biết file nào thực sự chậm.

## 7. Không nhầm chờ khóa với CPU hoặc I/O

Một session bị lock wait thường có blocker cụ thể và trạng thái wait liên quan khóa. Một session bị I/O wait thường không có blocker khóa; nó chờ thao tác đọc/ghi. Một truy vấn CPU-bound có thể active nhưng không có wait event cụ thể tại thời điểm lấy mẫu.

| Câu hỏi | Lock wait | CPU pressure | I/O pressure |
|---|---|---|---|
| Có blocker session không? | Thường có | Không nhất thiết | Không nhất thiết |
| Wait type/event | Lock-related | Scheduler/CPU contention hoặc active không có wait | I/O-related |
| CPU host | Có thể thấp hoặc cao do blocker khác | Thường cao | Có thể thấp hoặc vừa |
| Storage latency | Không nhất thiết cao | Không nhất thiết cao | Thường cao ở thiết bị liên quan |
| Hành động đầu tiên | Tìm blocker và transaction giữ khóa | Tìm top CPU query, plan và runnable pressure | Xác định file/device, loại I/O và query tạo I/O |

Đừng dựa vào một tên wait đơn lẻ. Một query có thể luân phiên giữa lock wait, CPU và I/O. Lấy mẫu nhiều lần và xem delta giúp phân biệt session đang chờ ổn định với session đang tiến triển.

## 8. Một số tình huống dễ chẩn đoán nhầm

### Pool đầy vì connection bị giữ trong lúc chờ khóa

Ứng dụng báo HikariCP active bằng max, pending borrowers tăng. Database cho thấy nhiều session chờ `LCK_M_X` hoặc PostgreSQL `wait_event_type = 'Lock'`. Đây có thể là lock contention kéo dài làm connection không được trả về pool. Tăng pool chỉ làm số waiter ở database tăng thêm.

Hãy tìm blocker đầu chuỗi, kiểm tra transaction mở lâu, câu lệnh cập nhật và thứ tự lấy khóa. Sau khi giảm thời gian giữ khóa hoặc xử lý blocker, pool có thể tự phục hồi.

### Database không có lock wait nhưng ứng dụng vẫn chờ lấy connection

Pool active = max nhưng database không có request tương ứng. Có thể code giữ connection rồi chờ HTTP call, chờ user input, chờ future hoặc bị leak. Hãy kiểm tra connection usage duration, leak detection, stack trace của thread và các đoạn code mượn connection mà không trả về.

### CPU cao và lock wait tăng cùng lúc

Một truy vấn CPU-heavy có thể giữ transaction và khóa lâu hơn. Các transaction khác chờ khóa, trong khi CPU vẫn bão hòa. Cần xem cả blocker và truy vấn tiêu thụ CPU; tối ưu query plan có thể giảm cả CPU lẫn thời gian giữ khóa.

### I/O chậm làm transaction giữ khóa lâu

Một transaction cập nhật nhiều hàng và chờ log flush hoặc data I/O có thể tiếp tục giữ khóa cho đến commit. Các transaction khác chờ khóa. Waiter nhìn thấy lock wait, nhưng nguyên nhân làm blocker chưa commit có thể là I/O. Điều tra phải đi từ waiter đến blocker rồi xem blocker đang chờ gì.

### Connection creation chậm do mạng hoặc xác thực

Nếu pool phải tạo connection mới, thời gian connect có thể tăng vì DNS, TLS handshake, firewall, network route, database listener hoặc authentication. Database có thể không có lock wait nào. Tách connect time khỏi pool acquire time và query time để tránh điều tra nhầm transaction.

## 9. Quy trình điều tra sự cố theo thứ tự

1. **Xác định khoảng thời gian và phạm vi ảnh hưởng.** Ghi thời điểm bắt đầu, service/endpoint, database, số request lỗi và liệu mọi query hay chỉ một nhóm query bị chậm.
2. **Phân rã thời gian ở ứng dụng.** Xem pool acquire, connect, query, result fetch và application time. Nếu chưa có tracing, đo thời gian quanh `getConnection`, execute và close.
3. **Kiểm tra pool.** Xem active/idle/pending/max, acquire timeout, usage time và connection creation errors. Phân biệt chờ pool với chờ database.
4. **Kiểm tra session database.** Xem số connection, session active/idle, query đang chạy, transaction mở lâu và session bị chặn.
5. **Tìm wait type/event.** Lock, I/O, log flush, network hay scheduler? Ghi lại waiter và blocker nếu có.
6. **Nếu lock wait, lần theo blocking chain.** Xác định session đầu chuỗi, transaction begin time, SQL hiện tại/cuối cùng và lý do chưa commit.
7. **Nếu CPU pressure, tìm top CPU SQL.** Kiểm tra execution plan, logical reads, số hàng ước lượng/thực tế, sort/hash spill và truy vấn lặp.
8. **Nếu I/O pressure, xác định loại file.** Data read, data write, log flush hay temp I/O; đối chiếu latency thiết bị và wait statistics.
9. **Đối chiếu cùng một thời điểm.** Không so pool metrics lúc 10:05 với database wait stats lúc 10:20 rồi kết luận quan hệ nhân quả.
10. **Thử biện pháp nhỏ, đo lại.** Thay đổi một yếu tố, so p50/p95/p99, throughput, errors, wait duration và tài nguyên sau thay đổi.

### Cây quyết định ngắn

```text
Request chậm
   |
   +-- Thời gian chờ pool acquire cao?
   |      |
   |      +-- Có --> pool active/pending? connection leak hay query giữ lâu?
   |      |             |
   |      |             +-- DB có lock wait? -> điều tra blocker
   |      |             +-- DB không bận? -> code giữ connection/pool sizing
   |      |
   |      +-- Không
   |
   +-- SQL execution time cao?
          |
          +-- Có blocker / lock wait? -> điều tra blocking chain
          +-- CPU cao / scheduler pressure? -> top CPU query và plan
          +-- I/O wait / storage latency? -> data/log/temp I/O
          +-- Không rõ? -> kiểm tra network, result fetch, plan và telemetry
```

## 10. Đo wait statistics đúng cách

Wait statistics là công cụ mạnh nhưng dễ bị diễn giải sai:

- Nhiều hệ quản trị lưu wait stats tích lũy kể từ khi instance khởi động hoặc từ lần reset. Một wait count lớn không chứng minh nó đang là vấn đề hiện tại.
- Hãy lấy snapshot ở hai thời điểm và tính delta trong cửa sổ sự cố.
- Loại bỏ hoặc diễn giải riêng các wait nền/idle phù hợp với database engine.
- Kết hợp wait stats với session hiện tại, query text, execution plan, CPU host và storage telemetry.
- Không tối ưu chỉ để giảm một wait statistic nếu throughput và latency người dùng không được cải thiện.

Với SQL Server, `sys.dm_os_wait_stats` là số liệu tích lũy toàn instance; cần so sánh delta và hiểu các wait phổ biến của phiên bản/workload. Với PostgreSQL, `pg_stat_activity` phản ánh wait hiện tại của backend; các extension hoặc phiên bản có thể cung cấp thống kê bổ sung. Với MySQL, Performance Schema ghi nhận event waits theo instrumentation đang bật.

## 11. Cách khắc phục theo từng nguyên nhân

### Khi là lock contention

- Giữ transaction ngắn; không gọi HTTP hoặc chờ người dùng trong lúc giữ khóa.
- Truy cập nhiều hàng theo thứ tự nhất quán để giảm deadlock.
- Tạo hoặc điều chỉnh index để câu lệnh tìm ít hàng hơn và giữ khóa ngắn hơn.
- Cập nhật theo batch vừa phải, tránh transaction sửa quá nhiều hàng trong một lần.
- Dùng optimistic locking hoặc atomic conditional update nếu workload phù hợp.
- Chọn isolation level và phạm vi khóa theo bất biến nghiệp vụ.
- Đặt lock timeout hợp lý và retry toàn bộ transaction khi lỗi có thể thử lại.
- Chỉ kết thúc session blocker khi đã hiểu tác động và có quy trình vận hành cho phép.

### Khi là pool hoặc connection shortage

- Tìm connection bị giữ lâu, leak hoặc không được đóng trong `finally`/try-with-resources.
- Không giữ connection trong lúc gọi dịch vụ ngoài hoặc chờ tác vụ bất đồng bộ.
- Đặt pool size theo khả năng database và số instance ứng dụng, không theo số thread tối đa.
- Đặt connection timeout và query timeout phù hợp với deadline của request.
- Kiểm tra database max sessions, authentication, DNS/TLS và network path.
- Dùng connection pool metrics và leak detection để tìm stack trace giữ connection quá lâu.

### Khi là CPU saturation

- Tìm top SQL theo CPU và execution count.
- Kiểm tra index, predicate, join order, cardinality estimate và plan regression.
- Tránh query lặp, N+1 và xử lý dữ liệu không cần thiết ở database.
- Giảm concurrency nếu tăng worker chỉ làm runnable queue dài hơn.
- Cân nhắc thêm CPU sau khi đã loại bỏ truy vấn lãng phí và xác nhận workload thực sự cần năng lực xử lý cao hơn.

### Khi là I/O bottleneck

- Xác định data file, log file hoặc temp file gây latency.
- Kiểm tra storage latency, queue depth, throughput và cấu hình cache.
- Giảm số page phải đọc bằng index và query plan phù hợp.
- Kiểm tra transaction log flush, batch commit và kích thước transaction.
- Tránh chạy báo cáo quét lớn cùng thời điểm với workload giao dịch nhạy latency nếu có thể tách workload.
- Đánh giá storage tier hoặc cấu hình I/O khi số liệu xác nhận thiết bị là giới hạn.

## 12. Những việc không nên làm khi chưa xác định nguyên nhân

- Không tăng pool size chỉ vì thấy pool đầy; trước hết tìm connection đang bị giữ bởi việc gì.
- Không tăng `max_connections` hoặc số session tùy tiện; nhiều connection hơn có thể làm CPU, memory và lock contention nặng hơn.
- Không kill blocker chỉ vì nó là blocker; xác định transaction, chủ sở hữu và tác động rollback trước.
- Không đặt mọi timeout thành giá trị rất lớn; điều đó có thể biến lỗi rõ ràng thành hàng đợi kéo dài.
- Không dùng `NOLOCK` để che lock wait nếu nghiệp vụ cần dữ liệu nhất quán.
- Không thêm index mà không xem execution plan, chi phí ghi và dung lượng.
- Không kết luận I/O chậm chỉ từ tổng `reads` hoặc CPU thấp; xem wait và latency theo thiết bị/file.
- Không dùng wait statistics tích lũy từ lúc khởi động như thể chúng mô tả đúng vài phút sự cố.

## 13. Ví dụ tổng hợp: từ triệu chứng đến nguyên nhân gốc

Giả sử API cập nhật đơn hàng có p99 tăng từ 300 ms lên 12 giây. HikariCP cho thấy active đạt max và pending tăng. Nếu chỉ nhìn pool, có thể nghĩ cần tăng connection.

Điều tra tiếp:

1. Trace cho thấy phần lớn request mất 10 giây ở SQL update; pool acquire chỉ 5 ms.
2. Database cho thấy các request update đang chờ `LCK_M_X`.
3. Nhiều waiter cùng bị một session chặn.
4. Session blocker đang mở transaction 11 phút; câu SQL cuối là một batch update lớn.
5. Transaction đó đang có I/O latency cao vì đọc nhiều page, đồng thời giữ khóa trong toàn bộ thời gian batch.

Chuỗi nguyên nhân:

```text
Batch query đọc/ghi quá nhiều page
          |
          v
I/O và thời gian transaction tăng
          |
          v
Blocker giữ khóa lâu
          |
          v
Nhiều request chờ lock
          |
          v
Connection bị giữ lâu
          |
          v
Pool active đạt max, pending tăng
          |
          v
HTTP request timeout
```

Giải pháp có thể là tối ưu access path, chia batch, rút ngắn transaction và tránh giữ khóa trong lúc làm công việc không cần thiết. Sau thay đổi, đo lại lock wait, transaction age, I/O latency, pool acquire và p99 để xác nhận chuỗi nguyên nhân đã được cải thiện.

## 14. Những điểm cần nhớ

- Request chậm không tự nói lên nguyên nhân; hãy tách pool acquire, connect, query, fetch và application time.
- Lock wait cần xác định waiter, blocker và blocking chain; transaction idle vẫn có thể giữ khóa.
- Pool exhaustion có thể là vấn đề riêng ở ứng dụng hoặc là hậu quả của query/transaction giữ connection quá lâu.
- CPU saturation thường biểu hiện qua CPU host, runnable pressure và truy vấn tiêu thụ CPU; không phải mọi session active đều đang bị khóa.
- I/O bottleneck cần phân biệt data read/write, transaction log, temp I/O và network.
- SQL Server `LCK_M_*`, PostgreSQL `wait_event_type = 'Lock'` và MySQL `performance_schema.data_lock_waits` là các điểm bắt đầu để tìm lock wait.
- SQL Server `PAGEIOLATCH_*`/`WRITELOG`, PostgreSQL I/O wait events và MySQL file wait events giúp điều tra I/O nhưng cần đối chiếu storage telemetry.
- Wait statistics tích lũy cần được đọc theo delta trong đúng cửa sổ sự cố.
- Nhiều nguyên nhân có thể nối tiếp nhau; hãy lần từ request đến session, blocker, query plan và tài nguyên hệ điều hành.
- Chỉ thay đổi pool, isolation, index, timeout hoặc hạ tầng sau khi có bằng chứng về nút thắt thực sự.

Chẩn đoán tốt bắt đầu bằng việc xác định request đang chờ ở tầng nào. Sau đó đối chiếu metrics ứng dụng với session và wait event của database, lần theo blocker nếu có, rồi kiểm tra CPU và I/O trong cùng khoảng thời gian. Khi tìm được nguyên nhân gốc và mối liên hệ giữa các tầng, việc chọn biện pháp xử lý sẽ chính xác hơn và ít gây tác dụng phụ cho hệ thống.

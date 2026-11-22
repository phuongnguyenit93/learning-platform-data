# Phân loại khối lượng công việc và xác định nút thắt

Tối ưu tài nguyên PostgreSQL bắt đầu bằng việc hiểu database đang làm công việc gì và tài nguyên nào đang giới hạn khả năng xử lý.


## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt OLTP, OLAP, reporting, batch, ETL và mixed workloads.
- Mô tả workload bằng throughput, latency percentiles, concurrency, read/write ratio và data access patterns.
- Thiết lập baseline và so sánh metrics theo cùng khoảng thời gian.
- Dùng PostgreSQL statistics views để tìm query và database activity tiêu tốn tài nguyên.
- Đọc wait events, locks, connection usage, buffer/cache behavior và I/O statistics.
- Nhận diện CPU, memory, storage, network, WAL, checkpoint và connection bottlenecks.
- Dùng EXPLAIN/EXPLAIN ANALYZE để phân tích chi phí query.
- Phân biệt query-level problem với system-wide resource saturation.
- Xây dựng giả thuyết, kiểm chứng và xác nhận bottleneck bằng thay đổi có kiểm soát.
- Ước lượng capacity và thiết kế benchmark phù hợp workload.
- Tránh các sai lầm như tăng work_mem, max_connections hoặc shared_buffers mà không đo.
- Xây dựng dashboard, alert và quy trình xử lý hiệu năng lặp lại.

## 2. Workload là gì?

Workload là tập hoạt động database trong một khoảng thời gian: SQL statements, transaction patterns, data volume, concurrency, background tasks và replication/maintenance work.

### 2.1. Query mix

Ghi nhận các loại statements: SELECT, INSERT, UPDATE, DELETE, DDL, bulk loads, reporting queries và stored procedures.

### 2.2. Transaction profile

Transaction có thể rất ngắn với vài statements, hoặc dài với nhiều reads/writes. Transaction duration ảnh hưởng locks, snapshots, vacuum và connection occupancy.

### 2.3. Data access pattern

Workload có thể truy cập vài rows thường xuyên, quét bảng lớn, đọc theo time range, join nhiều bảng hoặc cập nhật một tập hot keys.

### 2.4. Concurrency

Số clients cùng hoạt động và số requests đang chạy ảnh hưởng queueing, locks, CPU scheduling, memory và I/O.

### 2.5. Time variation

Workload thay đổi theo giờ, ngày, cuối tháng, campaign, batch window hoặc backup window. Một snapshot đơn lẻ không mô tả được toàn bộ tải.

## 3. Các lớp workload phổ biến

| Workload | Đặc điểm | Mục tiêu thường gặp |
|---|---|---|
| OLTP | Nhiều transaction nhỏ, concurrent reads/writes | Latency thấp, correctness |
| OLAP | Scan/join/aggregate dữ liệu lớn | Throughput và query completion |
| Reporting | Đọc định kỳ, có thể nặng | Freshness và predictable runtime |
| Batch | Nhiều writes/updates theo đợt | Hoàn thành trong cửa sổ thời gian |
| ETL/ELT | Extract/transform/load | Data throughput và restartability |
| Mixed | Nhiều loại workload cùng cluster | Isolation và predictable SLO |

### 3.1. OLTP

Ví dụ order creation, account lookup, inventory updates. Thường nhạy với p95/p99 latency, lock contention và connection queueing.

### 3.2. OLAP

Các truy vấn scan nhiều rows, join lớn và aggregate. Có thể tận dụng parallel query nhưng tiêu thụ CPU, memory và storage bandwidth đáng kể.

### 3.3. Reporting

Dashboard và scheduled reports có thể lặp lại cùng query shape. Cần cân nhắc materialized views, summary tables hoặc read replicas nếu workload ảnh hưởng OLTP.

### 3.4. Batch processing

Batch có thể tạo WAL bursts, dead tuples, checkpoint pressure và lock contention. Batch size/commit frequency có thể quan trọng hơn số query trung bình.

### 3.5. Mixed workloads

Một cluster có thể vừa phục vụ API latency-sensitive vừa chạy analytics. Một workload có thể chiếm tài nguyên và làm tăng latency của workload khác dù tổng CPU chưa đạt 100%.

## 4. Đặc trưng workload bằng các chỉ số nào?

Không nên chỉ phân loại bằng tên ứng dụng. Hãy mô tả workload bằng các dimensions có thể đo.

### 4.1. Throughput

Requests/transactions/queries mỗi giây (QPS/TPS) cho biết khối lượng hoàn thành. Phân biệt offered load (được gửi tới) với completed throughput (được xử lý xong).

### 4.2. Latency percentiles

Đo p50, p95, p99 và max. Average có thể che giấu một nhóm request rất chậm; p99 đặc biệt quan trọng với user-facing OLTP.

### 4.3. Concurrency và queue depth

Ghi số active requests, active database sessions, pool waiters và requests đang chờ. Throughput có thể không tăng khi concurrency tăng vì queueing.

### 4.4. Read/write mix

Tỷ lệ reads/writes, row changes, WAL bytes và transaction mix ảnh hưởng cache, storage, WAL và vacuum.

### 4.5. Query shape

Ghi các query fingerprints/normalized statements, joins, sorts, aggregates, rows scanned/returned, temp files và plan stability.

### 4.6. Data distribution

Cardinality, skew, hot keys, tenant size, partition size và correlation ảnh hưởng planner estimates và contention.

### 4.7. Freshness/consistency requirement

Một read có thể chấp nhận stale data vài giây; một read-after-write không thể. Yêu cầu này ảnh hưởng routing và replication capacity.

## 5. Throughput, latency và concurrency

Ba chỉ số này liên hệ với nhau qua queueing behavior.

~~~text
Incoming requests
       |
       v
   Waiting queue
       |
       v
 Active database work
       |
       v
 Completed responses
~~~

### 5.1. Offered load

Số requests ứng dụng gửi vào. Nếu offered load lớn hơn service capacity, queue sẽ tăng.

### 5.2. Completed throughput

Số requests thực sự hoàn thành. Khi tài nguyên đã bão hòa, tăng offered load thường làm latency tăng mà throughput không tăng đáng kể.

### 5.3. Queueing latency

Request có thể mất thời gian chờ connection pool, lock, CPU, I/O hoặc worker slot trước khi thực thi.

### 5.4. Little's Law

Trong trạng thái ổn định, số requests trung bình trong hệ thống bằng throughput nhân với thời gian response trung bình: L = lambda × W. Khi W tăng mà throughput không đổi, số requests đang tồn tại tăng.

### 5.5. Đừng tối ưu một metric riêng lẻ

Tăng throughput bằng cách batch lớn có thể làm p99 latency của OLTP xấu hơn. Giảm latency một query có thể tăng CPU tổng nếu nó khiến app tạo nhiều requests hơn.

## 6. Xác định SLO và workload class

Trước khi tuning, xác định mỗi workload cần đạt gì.

### 6.1. User-facing OLTP

Đặt target latency p95/p99, error rate và transaction success. Phân biệt database execution time với end-to-end request time.

### 6.2. Reporting

Có thể đặt query completion time, data freshness và concurrency limit thay vì yêu cầu p99 dưới vài chục milliseconds.

### 6.3. Batch

Đặt completion window, rows/second, WAL volume và giới hạn ảnh hưởng tới foreground traffic.

### 6.4. Background maintenance

Vacuum, analyze, index maintenance và backups cần đủ thời gian chạy nhưng không làm cạn storage/CPU trong peak traffic.

### 6.5. Workload isolation

Dùng connection pools riêng, query timeouts, resource groups ở tầng orchestration, read replicas hoặc scheduling để giảm interference. PostgreSQL core không cung cấp một resource group scheduler tổng quát cho mọi workload.

## 7. Thu thập baseline trước khi tối ưu

Baseline là tập metrics đại diện cho hệ thống ở trạng thái bình thường và các peak windows.

### 7.1. Chọn thời gian quan sát

Thu thập đủ chu kỳ daily/weekly và các batch windows. Một vài phút không đại diện cho cuối tháng hoặc campaign.

### 7.2. Ghi phiên bản và cấu hình

Lưu PostgreSQL version, hardware, storage type, parameters, extensions, connection pool settings và topology. Metrics không có context dễ dẫn đến kết luận sai.

### 7.3. Đồng bộ timestamps

Dùng timezone thống nhất, tốt nhất UTC cho correlation giữa application, PostgreSQL, OS và cloud metrics.

### 7.4. Ghi workload events

Đánh dấu deployments, data loads, vacuum, backups, failovers, schema changes và traffic campaigns trên timeline.

### 7.5. So sánh cùng điều kiện

So sánh trước/sau với cùng query mix, data size, concurrency và cache state nếu có thể. Nếu workload khác, không thể gán thay đổi performance cho một parameter duy nhất.

## 8. Các lớp metrics cần quan sát

| Lớp | Metrics tiêu biểu | Câu hỏi |
|---|---|---|
| Application | Request rate, latency, pool wait, errors | Người dùng chờ ở đâu? |
| PostgreSQL | Query stats, sessions, waits, locks | Database đang làm gì? |
| OS/VM | CPU, memory, run queue, disk, network | Host bị giới hạn gì? |
| Storage | IOPS, throughput, latency, queue depth | I/O nào đang chậm? |
| Replication | WAL rate, lag, slots, archive | Replica có theo kịp? |
| Business | Orders/sec, jobs, freshness | Tác động tới nghiệp vụ? |

### 8.1. Correlate thay vì đọc riêng lẻ

CPU cao cùng query time cao có thể là CPU-bound; CPU thấp cùng latency cao có thể là lock/I/O/network wait. Cần ghép metrics theo cùng time range.

### 8.2. Tách foreground và background

Query API, batch jobs, autovacuum, checkpoint và backup có thể cạnh tranh tài nguyên. Biết hoạt động nào tăng vào cùng thời điểm.

### 8.3. Theo dõi rate và absolute values

Một counter tăng từ 1 triệu lên 1.1 triệu cần tính delta/time. Một giá trị cumulative không cho biết tốc độ hiện tại.

### 8.4. Reset statistics

Một số statistics counters reset khi restart/reset stats. Ghi stats_reset và uptime để tránh so sánh các khoảng không tương đương.

### 8.5. Sampling interval

Interval quá dài che mất spikes; quá ngắn tạo noise và overhead. Chọn interval phù hợp latency/SLO và lưu history đủ lâu.


## 9. PostgreSQL statistics: database và table activity

Các statistics views cung cấp góc nhìn tổng quan về hoạt động database. Chúng là counters tích lũy hoặc estimates, nên cần lấy delta theo thời gian và xem cùng uptime/reset time.

~~~sql
SELECT
    datname,
    numbackends,
    xact_commit,
    xact_rollback,
    blks_read,
    blks_hit,
    tup_returned,
    tup_fetched,
    tup_inserted,
    tup_updated,
    tup_deleted,
    temp_files,
    temp_bytes,
    deadlocks,
    stats_reset
FROM pg_stat_database
WHERE datname = current_database();
~~~

### 9.1. Transactions

xact_commit/xact_rollback giúp ước lượng transaction volume và rollback trends. Không đồng nhất một transaction với một HTTP request.

### 9.2. Buffer hits và reads

blks_hit là blocks được lấy từ shared buffers theo thống kê; blks_read là blocks được đọc vào database buffers. OS page cache vẫn có thể phục vụ một block read mà không cần physical disk I/O.

### 9.3. Tuples

tup_returned/fetched/inserted/updated/deleted giúp hiểu read/write activity ở mức database. Đây là counters tổng hợp, không thay query-level analysis.

### 9.4. Temporary files

temp_files/temp_bytes tăng có thể chỉ ra sorts/hashes spill ra disk hoặc operations dùng temp storage. Xem query nào tạo temp và plan memory requirements.

### 9.5. Deadlocks

deadlocks tăng là tín hiệu concurrency/transaction design cần điều tra, không phải đơn giản là CPU bottleneck.

## 10. Table-level statistics và bloat clues

View `pg_stat_user_tables</BT> cho biết table activity và vacuum/analyze history.

~~~sql
SELECT
    schemaname,
    relname,
    seq_scan,
    seq_tup_read,
    idx_scan,
    idx_tup_fetch,
    n_live_tup,
    n_dead_tup,
    n_mod_since_analyze,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY seq_tup_read DESC;
~~~

### 10.1. Sequential scans

Seq scans không mặc nhiên xấu. Scan toàn bảng nhỏ có thể nhanh hơn index; bảng lớn bị quét lặp lại cho lookup nhỏ mới đáng điều tra.

### 10.2. Index scans

idx_scan và idx_tup_fetch cho thấy index activity, nhưng không chứng minh index hữu ích hay query plan tối ưu.

### 10.3. Dead tuples

n_dead_tup là estimate. Giá trị tăng lâu dài có thể liên quan autovacuum lag, long transactions hoặc update/delete churn.

### 10.4. Analyze freshness

Stats cũ có thể khiến planner ước lượng sai. Theo dõi n_mod_since_analyze và last_autoanalyze cùng plan changes.

### 10.5. Table size

Kết hợp `pg_total_relation_size</BT>, `pg_relation_size</BT> và index sizes để tìm bảng/index tăng nhanh hoặc chiếm phần lớn storage.

## 11. Query-level statistics với pg_stat_statements

Extension `pg_stat_statements</BT> tổng hợp execution statistics theo normalized query identity, hữu ích để tìm query tiêu tốn tổng thời gian hoặc có latency cao.

~~~sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    min_exec_time,
    max_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_written,
    wal_bytes,
    query
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

### 11.1. Total time và mean time

Query có mean 1 ms nhưng chạy một triệu lần có thể tiêu tốn tổng CPU lớn. Query chạy một lần mất 30 giây có thể là outlier cần xử lý riêng.

### 11.2. Calls và rows

Calls/rows giúp xác định query frequency và output volume. Một query trả quá nhiều rows có thể tốn network/application memory dù database execution nhanh.

### 11.3. Shared blocks

shared_blks_hit/read gợi ý buffer activity. Read counters không đồng nghĩa physical disk reads vì OS cache có thể phục vụ data.

### 11.4. Temp blocks

temp_blks_written giúp tìm sorts/hash aggregates spill. Kết hợp EXPLAIN và log_temp_files để xác định nguyên nhân.

### 11.5. Statistics không giữ nguyên mọi execution

Các entries là aggregates và có thể reset/evict. Query text có thể bị normalize/truncate theo cấu hình; không dùng nó làm audit log.

## 12. Bật và quản lý pg_stat_statements

Extension cần preload library và được tạo trong database theo hướng dẫn phiên bản.

### 12.1. shared_preload_libraries

~~~conf
shared_preload_libraries = 'pg_stat_statements'
pg_stat_statements.max = 10000
pg_stat_statements.track = all
~~~

Nếu đã có extensions trong shared_preload_libraries, nối tên library thay vì ghi đè danh sách hiện có.

### 12.2. Tạo extension

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
~~~

### 12.3. Track level

`pg_stat_statements.track</BT> có thể theo dõi top-level statements hoặc cả nested statements tùy cấu hình. Nested tracking làm tăng chi tiết và overhead.

### 12.4. Reset có kiểm soát

`pg_stat_statements_reset()</BT> xóa thống kê tương ứng. Chụp/export baseline trước khi reset nếu cần so sánh.

### 12.5. Privacy

Query text có thể chứa literals tùy normalization/setting và phiên bản. Kiểm soát quyền truy cập view, logs và dashboard theo data policy.

## 13. Active sessions với pg_stat_activity

View này giúp xác định sessions đang chạy, chờ và transaction age.

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    now() - xact_start AS transaction_age,
    left(query, 300) AS query_sample
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start NULLS LAST;
~~~

### 13.1. active và idle

active nghĩa backend đang thực thi query; idle nghĩa session đang chờ client. idle in transaction có thể giữ snapshot/locks dù không chạy query.

### 13.2. Query age

Query chạy lâu không nhất thiết là bottleneck. Có thể là legitimate report; cần biết query type, resource consumption và impact tới workload khác.

### 13.3. Transaction age

Transaction cũ có thể giữ locks/snapshots, cản vacuum cleanup và gây bloat. Đặc biệt chú ý idle in transaction.

### 13.4. Wait events

wait_event_type/wait_event cho biết backend đang chờ điều gì. Không có wait event không tự chứng minh CPU saturation; lấy nhiều samples để phân biệt.

### 13.5. Query visibility

Quyền xem query text của sessions khác phụ thuộc privileges và PostgreSQL version. Tránh cấp quyền rộng chỉ để dashboard hiển thị SQL.

## 14. Wait events: nhìn thời gian backend đang chờ

Wait events phân loại thời gian backend không tiến hành CPU work vì đang chờ một resource/event.

| Wait category | Ví dụ | Hướng điều tra |
|---|---|---|
| Lock | relation, transactionid | Blocking sessions, transaction order |
| LWLock | buffer/contention locks | Shared memory contention, workload |
| IO | DataFileRead/Write, WAL I/O | Storage latency/queue |
| Client | ClientRead/Write | Client/network/backpressure |
| IPC | Parallel worker coordination | Parallel execution/workers |
| Timeout | Various timeout waits | Timers and workload behavior |

### 14.1. Lock wait

Query có thể chậm vì chờ transaction khác, dù CPU/disk thấp. Tìm blocker chain trước khi tối ưu SQL.

### 14.2. I/O wait

IO wait tăng cùng storage latency/queue có thể chỉ ra disk bottleneck. Phân biệt data file, WAL, temp file và relation extension.

### 14.3. Client wait

Backend chờ client gửi lệnh hoặc nhận kết quả. ClientRead phổ biến ở idle sessions; ClientWrite có thể tăng khi client/network đọc chậm.

### 14.4. LWLock

Contention trên shared memory structures có thể xuất hiện ở concurrency cao. Cần xem wait event cụ thể, version và workload; không giải quyết bằng tăng disk throughput.

### 14.5. Sampling

Wait events là trạng thái tại thời điểm quan sát. Dùng sampling liên tục hoặc historical monitoring để thấy tỷ lệ thời gian theo category.

## 15. Lock contention và blocking chains

Lock contention thường bị nhầm với query CPU bottleneck vì user chỉ thấy latency tăng.

~~~sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.application_name AS blocked_app,
    blocker.pid AS blocker_pid,
    blocker.application_name AS blocker_app,
    now() - blocker.xact_start AS blocker_xact_age,
    left(blocked.query, 200) AS blocked_query,
    left(blocker.query, 200) AS blocker_query
FROM pg_stat_activity AS blocked
JOIN pg_stat_activity AS blocker
  ON blocker.pid = ANY (pg_blocking_pids(blocked.pid))
ORDER BY blocker.xact_start NULLS FIRST;
~~~

### 15.1. Blocking query và blocker

Query đang chờ có thể không phải query gây vấn đề. Tìm blocker transaction giữ lock lâu.

### 15.2. Transaction design

Transaction quá dài, gọi external API trong transaction hoặc chờ user input có thể giữ locks lâu. Rút ngắn transaction thường quan trọng hơn tăng CPU.

### 15.3. Lock modes

DDL, row updates, foreign keys và explicit locking dùng các lock modes khác nhau. Đọc pg_locks cùng pg_stat_activity để hiểu conflict.

### 15.4. Deadlock

Deadlock là cycle trong lock wait graph. PostgreSQL phát hiện và abort một transaction; xem logs và thiết kế thứ tự acquire locks nhất quán.

### 15.5. Không kill backend theo cảm tính

Trước khi pg_cancel_backend/pg_terminate_backend, xác định transaction, owner, side effects và rollback cost. Terminate có thể làm rollback lớn và tạo thêm I/O.


## 16. CPU bottleneck

CPU bottleneck xuất hiện khi database có nhiều runnable work hơn số CPU capacity có thể xử lý. Dấu hiệu thường là CPU utilization cao kéo dài, run queue tăng và query execution time tăng dù lock/I/O waits không chiếm phần lớn thời gian.

### 16.1. OS CPU metrics

Theo dõi user/system CPU, CPU steal trong môi trường VM, load average và run queue. Load average cao không đồng nghĩa CPU luôn bão hòa; cần xem số cores và I/O wait.

### 16.2. PostgreSQL process distribution

PostgreSQL thường dùng backend processes cho client connections và các background processes. Xem process-level CPU để tìm query/backends hoặc autovacuum/checkpointer tiêu thụ nhiều CPU.

### 16.3. Query CPU

Sort, hash aggregate, JSON processing, regex, expression evaluation, large joins và sequential scans có thể CPU-intensive. Dùng pg_stat_statements để tìm total time/calls, rồi EXPLAIN ANALYZE để xác định plan nodes.

### 16.4. Concurrency và context switching

Quá nhiều active sessions có thể làm tăng context switching và cache contention. Tăng max_connections không làm CPU có thêm capacity.

### 16.5. Parallel query

Parallel workers có thể rút ngắn một số scans/aggregates nhưng tăng tổng CPU và worker contention. Kiểm tra parallel plan, worker availability và tác động tới OLTP.

## 17. Phân biệt CPU-bound và wait-bound

Một query có elapsed time dài nhưng CPU time thấp có thể đang chờ locks, I/O hoặc client. Không suy bottleneck từ duration đơn lẻ.

### 17.1. CPU-bound symptoms

CPU utilization cao, query execution tiêu thụ CPU, run queue lớn và wait events không giải thích phần lớn latency.

### 17.2. I/O-bound symptoms

Backend thường chờ IO, storage latency/queue tăng, cache misses hoặc temp I/O cao. CPU có thể không bận.

### 17.3. Lock-bound symptoms

Nhiều active sessions có wait_event_type=Lock và blocking chain rõ. CPU tổng có thể thấp nhưng latency rất cao.

### 17.4. Client-bound symptoms

Sessions chờ ClientRead/ClientWrite hoặc application pool wait cao. Database có thể không phải nơi gây delay chính.

### 17.5. Mixed bottleneck

Một query có thể vừa CPU-intensive vừa I/O-intensive; lock waits còn có thể là hậu quả của query giữ transaction lâu. Phân tích timeline và nhiều samples.

## 18. Memory: shared buffers, work_mem và memory pressure

PostgreSQL dùng nhiều vùng memory với lifecycle khác nhau. Không có một con số “memory used by PostgreSQL” duy nhất phản ánh toàn bộ nhu cầu.

### 18.1. shared_buffers

Shared buffers là cache nội bộ của PostgreSQL cho data pages. Tăng quá nhiều có thể giảm memory cho OS page cache và các processes khác; lợi ích phụ thuộc working set, storage và OS cache behavior.

### 18.2. work_mem

work_mem là giới hạn memory cơ bản cho mỗi sort/hash operation trước khi có thể spill ra temporary files. Một query có nhiều nodes hoặc parallel workers có thể dùng nhiều lần work_mem.

### 18.3. Không tính work_mem theo một connection

Một session có thể chạy nhiều sort/hash operations; nhiều sessions hoạt động đồng thời và parallel workers có thể cùng cấp phát. Tổng memory tiềm năng có thể lớn hơn rất nhiều so với work_mem nhân max_connections.

### 18.4. maintenance_work_mem

Dùng cho một số maintenance operations như VACUUM và index creation. Nhiều maintenance jobs đồng thời có thể cùng dùng memory.

### 18.5. Backend/process memory

Mỗi backend và background worker có private memory. Extensions, PL runtimes, query execution structures và application concurrency làm tổng RSS tăng.

## 19. Nhận diện memory pressure

Memory pressure có thể khiến OS reclaim pages, swap, OOM kill hoặc database latency tăng.

### 19.1. OS metrics

Theo dõi available memory, swap-in/swap-out, page faults, OOM events và process RSS. Free memory thấp không tự động là lỗi nếu OS đang dùng RAM cho cache; xem available memory và pressure.

### 19.2. Swap activity

Sustained swap-in/out thường gây latency khó dự đoán. PostgreSQL workloads nhạy với page faults; tránh thiết kế tổng memory allocation vượt physical RAM.

### 19.3. Temporary file growth

Temp files tăng có thể cho thấy sort/hash spill. Xem log_temp_files và query plan để quyết định có cần thay query, index hoặc work_mem.

### 19.4. Hash memory

Hash joins/aggregates có thể dùng nhiều memory; spill sang nhiều batches nếu không đủ. Tăng work_mem có thể giúp một query nhưng làm nhiều concurrent queries gây OOM.

### 19.5. Memory accounting

Xem shared_buffers, OS cache, backend RSS, autovacuum/maintenance workers và extension memory cùng lúc. Tránh cộng các số liệu RSS/shared memory bị double-count.

## 20. Storage I/O bottleneck

Storage có thể giới hạn throughput hoặc tạo tail latency. Phân biệt IOPS, throughput, latency và queue depth.

### 20.1. IOPS

IOPS là số operations mỗi giây. Random small reads/writes thường bị giới hạn IOPS hơn sequential throughput.

### 20.2. Throughput

MB/s đo lượng bytes truyền. Sequential scans, backups, WAL archive và bulk loads có thể đạt throughput limit.

### 20.3. Latency

Disk latency cao làm query chờ lâu, đặc biệt với random reads và synchronous writes. Quan sát p95/p99 storage latency, không chỉ average.

### 20.4. Queue depth

Queue depth tăng có thể cho biết storage đã bận hoặc host gửi quá nhiều I/O. Queue lớn có thể tăng latency; thêm concurrency không luôn tăng throughput.

### 20.5. Storage classes

Local NVMe, network block storage, SAN và cloud volumes có latency/throughput/IOPS characteristics khác nhau. Benchmark trên đúng storage class và provisioned limits.


## 21. PostgreSQL I/O statistics

Từ PostgreSQL 16, view pg_stat_io cung cấp thống kê I/O theo backend type, object và context. Availability/columns phụ thuộc major version.

~~~sql
SELECT
    backend_type,
    object,
    context,
    reads,
    read_time,
    writes,
    write_time,
    extends,
    fsyncs,
    fsync_time
FROM pg_stat_io
ORDER BY backend_type, object, context;
~~~

### 21.1. Backend type

Phân biệt client backends, autovacuum workers, background writer, checkpointer và các backend types khác theo version.

### 21.2. Object và context

Giúp xem I/O liên quan relation, temporary files hoặc context như normal/bulkread/bulkwrite theo catalog version.

### 21.3. Timings

Read/write/fsync timings chỉ hữu ích nếu I/O timing collection được hỗ trợ/bật theo version/config. Xem pg_settings và documentation của major version.

### 21.4. Counters và deltas

Lấy snapshots theo thời gian để tính rates. Một counter lớn sau nhiều ngày không chứng minh hiện tại đang nghẽn.

### 21.5. Kết hợp OS metrics

pg_stat_io không thay thế disk metrics của OS/cloud. Kết hợp device latency, throughput, queue, filesystem và volume throttling.

## 22. track_io_timing và timing overhead

PostgreSQL có thể thu thập I/O timing để hỗ trợ phân tích.

~~~sql
SHOW track_io_timing;
~~~

### 22.1. Bật timing

Có thể bật track_io_timing theo version và deployment policy. Đo overhead trên workload thực tế trước khi bật rộng trong hệ thống nhạy latency.

### 22.2. I/O time trong query stats

Một số statistics views/EXPLAIN output có thể hiển thị I/O timing khi được bật. Dùng để tìm query spend time waiting on I/O.

### 22.3. Timing không đồng nghĩa device latency thuần

Số liệu có thể phản ánh thời gian call/OS path và cách platform đo. Đối chiếu với storage metrics độc lập.

### 22.4. Virtualized storage

Cloud storage có throttling, burst credits và network path. Kiểm tra volume limits/credits cùng disk queue.

### 22.5. Khi nào tắt?

Nếu overhead đo được đáng kể hoặc không còn cần instrumentation, điều chỉnh theo policy; giữ đủ metrics cho recurring performance investigations.

## 23. Query plan: EXPLAIN và EXPLAIN ANALYZE

EXPLAIN cho biết planner dự định thực thi query thế nào. EXPLAIN ANALYZE thực sự chạy query và báo actual rows/timing; chỉ dùng khi execution side effects và load đã được xem xét.

~~~sql
EXPLAIN (ANALYZE, BUFFERS, WAL, SETTINGS)
SELECT
    customer_id,
    count(*)
FROM public.orders
WHERE created_at >= now() - interval '7 days'
GROUP BY customer_id;
~~~

### 23.1. Estimated rows và actual rows

Sai lệch lớn giữa estimated rows và actual rows có thể làm planner chọn join/order strategy không phù hợp. Xem statistics, skew và correlation.

### 23.2. Cost không phải milliseconds

Planner cost là đơn vị tương đối dùng để so sánh plans theo cost parameters. Không đọc cost=1000 như 1000 ms.

### 23.3. Buffers

BUFFERS cho biết shared/local/temp buffer hits/reads/writes ở plan nodes. Nó giúp xác định plan đọc nhiều pages, nhưng shared read không nhất thiết là physical disk read.

### 23.4. WAL

Tùy version và statement, WAL option có thể cho biết WAL records/FPI/bytes được tạo bởi execution. Hữu ích cho write-heavy statements.

### 23.5. SETTINGS

Hiển thị các planner-related settings khác default ảnh hưởng plan. Dùng để phát hiện session-level tuning hoặc environment differences.

## 24. Đọc plan nodes để tìm chi phí

Một plan cần đọc từ root xuống các child nodes và so estimated/actual rows, loops, buffers và time.

### 24.1. Seq Scan

Seq Scan đọc lần lượt pages của relation. Phù hợp với bảng nhỏ hoặc query cần phần lớn rows; có thể đắt nếu bảng lớn và filter selectivity cao.

### 24.2. Index Scan và Index Only Scan

Index Scan dùng index để tìm tuples nhưng có thể truy cập heap nhiều lần. Index Only Scan có thể tránh heap fetch khi visibility map cho phép.

### 24.3. Bitmap Heap Scan

Bitmap plan có thể gom heap locations rồi đọc pages hiệu quả hơn với nhiều matches. Không phải lúc nào cũng nhanh hơn Index Scan.

### 24.4. Nested Loop

Nested Loop có thể tốt khi outer side nhỏ và inner lookup có index. Nếu outer rows lớn, inner loops nhiều có thể gây rất nhiều random I/O.

### 24.5. Hash Join và Merge Join

Hash Join xây hash table và có thể spill; Merge Join cần inputs được sắp xếp theo join keys. Chọn plan phụ thuộc cardinality, memory và ordering.

### 24.6. Sort và Aggregate

Sort/HashAggregate có thể tiêu thụ memory/temp I/O. Xem sort method, memory, disk usage và rows processed.

## 25. Query-plan red flags

Một node có thời gian lớn không tự động là lỗi; cần hiểu dữ liệu và query semantics.

### 25.1. Rows estimate lệch lớn

Planner estimates sai có thể do stale statistics, skew, correlated columns hoặc parameter-sensitive plans.

### 25.2. Loops rất cao

Nested Loop với inner scan lặp hàng trăm nghìn lần có thể tạo nhiều work. Kiểm tra index, join order và cardinality.

### 25.3. Rows removed by filter lớn

Nhiều rows đọc rồi loại bỏ có thể gợi ý index/selectivity problem, nhưng seq scan vẫn có thể là lựa chọn hợp lý nếu phần lớn bảng được cần.

### 25.4. Sort spill

Sort Method external merge hoặc temp blocks lớn cho thấy sort dùng disk. Cân nhắc index/order, giảm rows sớm hoặc memory policy.

### 25.5. Heap fetches trên Index Only Scan

Heap fetches cao có thể do visibility map chưa đủ all-visible, thường liên quan update churn/vacuum. Index Only Scan không bảo đảm zero heap I/O.

## 26. Query optimization hay resource scaling?

Không phải bottleneck nào cũng giải quyết bằng cách thêm CPU/RAM/disk.

### 26.1. Query-specific bottleneck

Một query duy nhất chiếm phần lớn total_exec_time hoặc tạo nhiều reads/temp files. Tối ưu SQL/index/plan thường có tác động trực tiếp.

### 26.2. System-wide bottleneck

Nhiều query độc lập chậm cùng lúc, resource saturation và queueing tăng. Có thể cần scale hoặc workload isolation.

### 26.3. Connection/pool bottleneck

Application chờ lấy connection trong khi database còn headroom. Điều chỉnh pool, concurrency và transaction lifecycle trước khi scale database.

### 26.4. Lock bottleneck

Latency tăng do blocker transaction. Thêm CPU không làm lock được giải phóng nhanh hơn nếu transaction logic không đổi.

### 26.5. Storage bottleneck

Nếu query plan đã hợp lý nhưng storage latency/throttling cao, cân nhắc storage tier, IOPS/throughput limits, data locality và cache strategy.

## 27. Checkpoint và WAL pressure

Write-heavy workloads có thể bị ảnh hưởng bởi WAL generation, checkpoint cadence và storage write throughput.

### 27.1. WAL generation rate

Bulk loads, UPDATE/DELETE churn, index builds và frequent commits có thể tạo WAL nhiều. Theo dõi pg_stat_wal và archive/replication rates theo version.

### 27.2. Checkpoint activity

Checkpoint writes dirty buffers và tạo I/O. Checkpoint quá dày hoặc write bursts có thể làm tăng latency; xem checkpoint stats/logs theo major version.

### 27.3. max_wal_size

max_wal_size là soft limit liên quan checkpoint scheduling, không phải hard cap tuyệt đối cho pg_wal. Archive/replication slots và checkpoint conditions ảnh hưởng actual retention.

### 27.4. checkpoint_timeout và completion target

Các settings này điều khiển thời điểm và pacing checkpoint. Tuning phải dựa trên WAL rate, storage throughput và recovery requirements.

### 27.5. Full-page images

Sau checkpoint, page modifications có thể tạo full-page images trong WAL tùy wal_log_hints/checksum/full_page_writes conditions. Workload write pattern ảnh hưởng WAL volume.

## 28. Vacuum và autovacuum như workload

Vacuum là công việc cần thiết để reclaim reusable space, maintain visibility map và ngăn transaction ID wraparound. Nó tiêu thụ I/O/CPU và có thể cạnh tranh với foreground queries.

### 28.1. Update/delete churn

Các bảng update/delete nhiều tạo dead tuples. Autovacuum cần chạy đủ nhanh để theo kịp churn.

### 28.2. Long-running transactions

Snapshot cũ có thể ngăn vacuum loại bỏ tuple versions. Tìm long transactions và idle-in-transaction sessions.

### 28.3. Autovacuum workers

Theo dõi số workers, vacuum duration, table size, dead tuples và logs. Tăng workers có thể tăng concurrency I/O; cần capacity.

### 28.4. Analyze

Planner statistics cần được cập nhật. Analyze có thể là bottleneck nếu bảng lớn và statistics targets cao, nhưng stale stats cũng làm query plans kém.

### 28.5. Vacuum không phải lúc nào cũng là nguyên nhân

Một autovacuum đang chạy cùng lúc với latency spike chỉ là correlation. Xác nhận bằng I/O/CPU, table activity và timeline trước khi thay settings.


## 29. Connection bottleneck và connection pooling

Mỗi PostgreSQL connection thường tương ứng một backend process. Quá nhiều concurrent connections có thể làm tăng memory use, process scheduling và contention.

### 29.1. Connection count

Theo dõi tổng sessions, active, idle, idle in transaction và số connections theo application_name/user. So sánh với max_connections và reserved slots.

~~~sql
SELECT
    application_name,
    usename,
    state,
    count(*) AS sessions
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY application_name, usename, state
ORDER BY sessions DESC;
~~~

### 29.2. Active sessions không đồng nghĩa useful throughput

Nhiều sessions active có thể cùng chờ locks hoặc I/O. Đo completed TPS và wait events thay vì chỉ đếm active connections.

### 29.3. Pool wait time

Nếu app pool hết connection, request chờ ở application trước khi tới PostgreSQL. Cần instrument pool acquisition latency và queue length.

### 29.4. Pool sizing

Chọn pool size theo database capacity, query concurrency và số application instances. Một pool quá lớn trên mỗi pod có thể nhân thành hàng nghìn connections.

### 29.5. PgBouncer

Connection pooler có thể giảm backend count và connection churn. Transaction pooling có các giới hạn với session state, temp tables, prepared statements và session-level features; kiểm tra compatibility của ứng dụng.

## 30. Network bottleneck

Network có thể giới hạn query response, replication, backup hoặc app-to-database throughput.

### 30.1. Latency và bandwidth

RTT ảnh hưởng round trips của query chatty. Bandwidth giới hạn large result sets, COPY, replication và backups.

### 30.2. Query result size

Một query trả hàng triệu rows có thể database execution nhanh nhưng client response chậm do network và serialization. Chỉ trả columns/rows ứng dụng thực sự cần.

### 30.3. Client-side processing

Application có thể đọc toàn bộ result rồi xử lý tuần tự. Đo database execution time, transfer time và application processing time riêng.

### 30.4. Packet loss và retransmits

Packet loss/retransmissions làm latency tăng dù average bandwidth chưa đạt giới hạn. Theo dõi network metrics ở cả host và cloud/network layer.

### 30.5. Cross-region calls

Database round trips qua region có RTT cao. Giảm chatty queries, batch operations phù hợp hoặc đặt application gần database.

## 31. Replication và backup như workload consumers

Replication/backup cũng sử dụng CPU, disk và network trên cùng infrastructure.

### 31.1. WAL sender/receiver

Physical replication gửi WAL liên tục; logical replication decode/apply changes. Theo dõi sender/receiver lag và network throughput.

### 31.2. Logical decoding

Logical decoding có CPU/I/O cost và replication slots giữ WAL. Một consumer chậm có thể làm WAL retained tăng.

### 31.3. Backup load

Base backups và logical dumps đọc nhiều pages, tạo network egress và có thể cạnh tranh với query workloads.

### 31.4. Archive commands

WAL archiving cần hoàn tất đủ nhanh. Archive backlog có thể tăng pg_wal usage; kiểm tra archive status và external storage latency.

### 31.5. Schedule và throttle

Lên lịch backup/batch nặng tránh peak nếu policy cho phép. Dùng bandwidth/IO limits của tooling để giảm interference, đồng thời vẫn đáp ứng RPO/RTO.

## 32. Temp files và temporary I/O

Temporary files thường được tạo bởi sort/hash spill, materialization hoặc các operations cần temp storage.

### 32.1. log_temp_files

Có thể cấu hình log_temp_files để ghi các temp files vượt ngưỡng. Chọn threshold phù hợp để không tạo quá nhiều log noise.

### 32.2. Query-level attribution

Dùng pg_stat_statements temp_blks_written và EXPLAIN ANALYZE BUFFERS để tìm query tạo temp I/O.

### 32.3. Sort spill

External sort cho thấy dữ liệu sort vượt memory được cấp. Có thể giảm rows trước sort, thêm index phù hợp hoặc điều chỉnh memory có kiểm soát.

### 32.4. Hash batches

Hash operations có thể dùng nhiều batches khi memory không đủ. Kiểm tra plan output và cardinality estimate.

### 32.5. Temp tables của ứng dụng

Ứng dụng có thể tạo temp tables và giữ session lâu. Theo dõi session lifecycle và temp storage; transaction pooling có thể không tương thích với temp table/session assumptions.


## 33. Query planning và statistics problems

Một query chậm không nhất thiết do thiếu tài nguyên. Planner có thể chọn plan không phù hợp vì statistics hoặc parameter behavior.

### 33.1. Stale statistics

Data distribution thay đổi nhưng analyze chưa chạy có thể làm estimates lệch. Xem last_autoanalyze, n_mod_since_analyze và plan.

### 33.2. Data skew

Một tenant/key có nhiều rows hơn hẳn phần còn lại. Histogram/MCV stats có thể không mô tả đầy đủ skew hoặc correlated columns.

### 33.3. Extended statistics

Extended statistics có thể giúp planner ước lượng dependencies, n-distinct hoặc most-common value combinations cho nhiều columns. Tạo theo query/data evidence, rồi analyze.

### 33.4. Generic và custom plans

Prepared statements có thể dùng generic plan hoặc custom plan theo behavior/version/settings. Một plan tốt cho average parameter có thể rất tệ cho tenant lớn.

### 33.5. Plan regression

Sau deploy, data growth, analyze, version upgrade hoặc parameter change, plan có thể thay đổi. Lưu representative EXPLAIN outputs và query latency history.

## 34. Index workload và write amplification

Indexes giúp reads nhưng làm writes tốn hơn.

### 34.1. Index maintenance

INSERT/UPDATE/DELETE cần cập nhật indexes liên quan. Nhiều indexes trên bảng write-heavy tăng WAL, CPU và storage I/O.

### 34.2. Unused indexes

Index ít được dùng vẫn chiếm disk/cache và tăng write cost. Xem pg_stat_user_indexes, nhưng kiểm tra reset window, constraints và periodic jobs trước khi drop.

### 34.3. Missing indexes

Query lookup/selective filter không có index có thể scan nhiều rows. Index design phải theo predicates, joins, ordering và data distribution.

### 34.4. Index bloat

Index bloat làm tăng pages đọc và cache footprint. Dùng index maintenance theo evidence; REINDEX có thể tạo I/O/space peak và cần plan.

### 34.5. Covering indexes

INCLUDE columns có thể hỗ trợ index-only access nhưng tăng index size/write cost. Chỉ thêm columns có giá trị cho workload quan trọng.

## 35. Partitioning và workload distribution

Partitioning có thể giảm phạm vi scan/maintenance và hỗ trợ retention, nhưng không tự động làm query nhanh hơn.

### 35.1. Partition pruning

Query phải có predicates tương thích partition key để planner loại bỏ partitions không cần đọc. Kiểm tra plan thực tế.

### 35.2. Too many partitions

Nhiều partitions có thể tăng planning overhead, catalog size và operational complexity. Số partition nên dựa vào data volume/retention/query patterns.

### 35.3. Partition-wise operations

Một số joins/aggregates có thể thực hiện theo partition khi settings và partition keys phù hợp. Kiểm tra plan và worker availability.

### 35.4. Hot partition

Một partition nhận phần lớn writes có thể trở thành hotspot dù toàn database còn capacity. Đánh giá key distribution và partition boundaries.

### 35.5. Maintenance per partition

Vacuum/analyze/index operations và retention có thể được quản lý theo partition. Lịch maintenance cần tránh tạo đồng thời I/O bursts.

## 36. Workload interference và resource isolation

Một workload có thể làm workload khác chậm dù từng query riêng lẻ không có vấn đề.

### 36.1. Noisy neighbor

Batch scan lớn có thể evict useful cache pages, tiêu thụ I/O và tăng p99 latency của OLTP.

### 36.2. Connection isolation

Dùng pools/users riêng để đặt concurrency caps và query timeouts cho reporting/batch. Connection pool riêng không tự cô lập CPU/disk.

### 36.3. Read replicas

Đẩy reporting/read-heavy work sang replicas có thể giảm primary load, nhưng replication lag, replica conflicts và network capacity cần được tính.

### 36.4. Scheduling

Chạy batch/backup/vacuum-intensive tasks theo windows nếu business requirements cho phép. Đừng trì hoãn maintenance tới mức tạo bloat/wraparound risk.

### 36.5. Query governance

Đặt statement_timeout/lock_timeout phù hợp theo role/application class. Giới hạn query runaway và bảo đảm timeout không làm retry storm.

## 37. Bottleneck patterns: triệu chứng và giả thuyết

| Triệu chứng | Giả thuyết đầu tiên | Bằng chứng cần tìm |
|---|---|---|
| CPU 95%, run queue cao | CPU saturation | Process CPU, query total time, plan |
| CPU thấp, latency cao | Lock/I/O/network wait | Wait events, blockers, storage |
| Temp bytes tăng | Sort/hash spill | Query stats, EXPLAIN, temp logs |
| Disk latency cao | Storage bottleneck | IOPS, queue, volume throttling |
| Pool wait cao, DB nhàn | App pool undersized | Pool metrics, active sessions |
| Connections gần limit | Connection pressure | Session states, pool sizing |
| WAL disk tăng | Slot/archive/checkpoint issue | Slots, archive status, WAL rate |
| Replica lag tăng | Network/replay bottleneck | Sender/receiver LSN, CPU/I/O |
| p99 tăng theo batch | Workload interference | Query timeline, I/O/CPU overlap |
| Một query chậm sau deploy | Plan regression | Query fingerprint, plan diff |

### 37.1. Một symptom có nhiều causes

Latency cao có thể do connection wait, locks, I/O hoặc CPU. Chỉ chọn giả thuyết sau khi nhìn được wait/resource evidence.

### 37.2. Một cause có nhiều symptoms

Storage saturation có thể làm query chậm, autovacuum trễ, checkpoint kéo dài và replication lag tăng.

### 37.3. Xác định primary bottleneck

Tìm resource hoặc dependency mà khi bị giới hạn sẽ làm throughput không thể tăng. Các bottlenecks thứ cấp có thể biến mất sau khi primary bottleneck được giải quyết.

### 37.4. Không nhầm correlation với causation

CPU và latency cùng tăng có thể do traffic spike; CPU có thể là nguyên nhân hoặc hệ quả của retry storm. Cần timeline và controlled test.

### 37.5. Ghi confidence

Phân biệt measured fact, hypothesis và confirmed cause. Nếu chưa có bằng chứng, không gọi đó là root cause.

## 38. Quy trình điều tra bottleneck có hệ thống

Một quy trình nhất quán giúp tránh thay nhiều parameters cùng lúc.

1. Xác định service/workload bị ảnh hưởng và SLO bị vi phạm.
2. Chọn time window bắt đầu/kết thúc và ghi workload events.
3. Xác định query fingerprints, applications và tenants liên quan.
4. Lấy PostgreSQL sessions, wait events, locks và statistics deltas.
5. Lấy OS CPU/memory/disk/network và cloud storage metrics.
6. Phân loại bottleneck hypothesis: CPU, memory, I/O, lock, connection, network, WAL hoặc plan.
7. Kiểm tra query plans và data distribution khi query-specific.
8. Thực hiện một thay đổi nhỏ có kiểm soát hoặc một benchmark tái lập.
9. So sánh latency, throughput, resource use và side effects.
10. Giữ/rollback thay đổi theo tiêu chí đã định.
11. Cập nhật dashboard/alert/runbook và capacity model.

### 38.1. Xác định impact trước

Chọn query class, API, database hoặc tenant có SLO fail. Không tuning cả cluster khi chỉ một report query chậm.

### 38.2. Thu thập cùng một time window

Lấy application traces, pg_stat_statements deltas, pg_stat_activity samples và OS metrics cùng timestamps.

### 38.3. Kiểm tra workload change

Traffic rate, data size, deploy, batch job, query parameters hoặc cache warmness có thể đã thay đổi.

### 38.4. Tạo hypothesis cụ thể

Ví dụ: p99 tăng vì query X chuyển từ index scan sang seq scan sau data growth. Một hypothesis tốt có metric/plan dự kiến để kiểm chứng.

### 38.5. Một biến mỗi lần

Thay index, query, work_mem hoặc storage configuration theo từng bước nếu có thể. Nhiều thay đổi cùng lúc làm mất khả năng quy nguyên nhân.


## 39. Xác nhận bottleneck bằng controlled experiments

Một giả thuyết chỉ trở thành kết luận khi có thể tái hiện hoặc kiểm chứng bằng thay đổi có kiểm soát.

### 39.1. Chọn workload đại diện

Dùng query mix, parameter distribution, concurrency và data volume gần production. Một query đơn lẻ không mô phỏng được mixed workload.

### 39.2. Giữ các biến khác ổn định

Cố định version, schema, dataset, hardware, storage, connection pool, cache state và background jobs càng nhiều càng tốt.

### 39.3. Đo trước và sau

Ghi throughput, p50/p95/p99 latency, CPU, memory, disk, network, locks, temp I/O và WAL. Một thay đổi tốt phải cải thiện SLO mà không tạo regression nghiêm trọng ở workload khác.

### 39.4. Lặp lại

Chạy nhiều lần để phân biệt noise với thay đổi ổn định. Ghi rõ warm-cache và cold-cache scenarios.

### 39.5. Rollback criteria

Định nghĩa trước điều kiện rollback: p99 tăng, error rate tăng, WAL/slot growth bất thường, disk headroom giảm hoặc replica lag vượt SLO.

## 40. Benchmark với pgbench

pgbench là công cụ đi kèm PostgreSQL để tạo workload transaction và đo throughput/latency.

~~~bash
pgbench -i -s 50 appdb
pgbench -c 32 -j 8 -T 300 -P 10 appdb
~~~

Các lệnh trên là ví dụ lab. Initialize sẽ tạo/ghi dữ liệu benchmark; không chạy trên database production.

### 40.1. Scale factor

Scale factor ảnh hưởng kích thước dataset. Dataset phải đủ lớn để thử cache/storage behavior mà bạn muốn đo.

### 40.2. Clients và threads

-c là số clients, -j là số worker threads của pgbench. Tăng clients để tìm saturation point, nhưng không mặc định càng nhiều càng tốt.

### 40.3. Duration và progress

-T đặt thời lượng test; -P in progress interval. Chạy đủ lâu để quan sát steady state và checkpoint/maintenance effects.

### 40.4. Latency và TPS

Ghi TPS, latency average/percentiles nếu output cung cấp, failed transactions và connection behavior. So sánh cùng options và environment.

### 40.5. Custom scripts

Dùng script pgbench để mô phỏng transaction mix gần ứng dụng: reads, writes, think time và parameter distributions.

## 41. Benchmark không giống production

Một benchmark có thể đẹp nhưng production vẫn chậm nếu workload không tương đương.

### 41.1. Data shape

Dataset benchmark thường đều hơn production. Skew, hot tenants, large rows và long-tail queries có thể bị bỏ sót.

### 41.2. Cache state

Test warm-cache có thể không phản ánh restart/failover/cold-start behavior. Ghi rõ cache conditions.

### 41.3. Concurrency pattern

Production có burstiness, retries, pool wait, external API latency và user think time. Constant-rate load không mô phỏng hết.

### 41.4. Background activity

Autovacuum, checkpoints, backups, replication và scheduled jobs có thể tạo interference. Đưa các tác vụ đại diện vào test khi phù hợp.

### 41.5. Test environment parity

CPU generation, storage class, network, kernel, PostgreSQL version và config phải đủ tương đồng để kết quả có ý nghĩa.

## 42. Capacity planning từ workload

Capacity planning ước lượng tài nguyên cần để đáp ứng workload hiện tại và tăng trưởng dự kiến.

### 42.1. CPU capacity

Ước lượng CPU seconds/transaction và peak TPS. Dự trù headroom cho bursts, maintenance, failover catch-up và background jobs.

### 42.2. Memory capacity

Tính shared_buffers, OS cache, backend private memory, concurrent sort/hash operations, maintenance workers và OS reserve. Không chỉ cộng work_mem nhân max_connections.

### 42.3. Storage capacity

Tính data, indexes, WAL, temp files, backups, archive staging, bloat và growth/retention. Tách capacity khỏi IOPS/throughput requirements.

### 42.4. Network capacity

Ước lượng query result egress, replication/WAL, backup transfer và cross-region traffic. Cộng burst/headroom và protocol overhead.

### 42.5. Growth model

Dùng trend data volume, TPS, index growth và tenant count. Tạo forecast theo tháng/quý và kiểm tra lại bằng actuals.

## 43. Headroom và saturation point

Không nên vận hành liên tục sát giới hạn tài nguyên nếu workload có burst hoặc failure modes.

### 43.1. Headroom

Giữ phần capacity cho peak traffic, vacuum/checkpoint, backup, replication catch-up và failover. Headroom cụ thể phụ thuộc workload/SLO.

### 43.2. Saturation curve

Chạy load tăng dần và ghi throughput/latency. Saturation point thường là nơi throughput gần như ngừng tăng trong khi latency/queue tăng nhanh.

### 43.3. Safe operating range

Đặt operating limit dưới saturation point để có buffer cho bursts. Một node có thể đạt 100% CPU trong benchmark nhưng không phải target vận hành liên tục.

### 43.4. Failover capacity

Khi primary mất, surviving node có thể phải nhận toàn bộ workload và đồng thời chạy catch-up/maintenance. HA capacity phải được test ở failure mode.

### 43.5. Scale trigger

Định nghĩa trigger từ sustained latency, queue, resource utilization, disk forecast và growth rate; tránh scale chỉ vì một spike ngắn.


## 44. Tuning parameters theo bằng chứng

Parameter tuning phải theo bottleneck cụ thể, PostgreSQL version và deployment environment.

| Parameter/area | Có thể ảnh hưởng | Cần đo trước |
|---|---|---|
| shared_buffers | Buffer cache | Working set, OS cache, memory |
| work_mem | Sort/hash spill | Concurrent operations, temp files |
| max_connections | Session capacity | Pool wait, backend count, memory |
| effective_cache_size | Planner estimates | Available cache estimate |
| random_page_cost | Planner cost model | Storage/cache characteristics |
| checkpoint settings | Write pacing/WAL | WAL rate, checkpoint logs, I/O |
| autovacuum settings | Cleanup/analyze rate | Churn, dead tuples, I/O headroom |
| parallel settings | Parallel query workers | CPU headroom, query mix |

### 44.1. shared_buffers

Tăng shared_buffers chỉ khi cache behavior và memory budget cho thấy có lợi. Kiểm tra restart requirements và OS page cache.

### 44.2. work_mem

Điều chỉnh có thể giảm temp spills cho query phù hợp. Dùng role/session-specific settings khi có thể; ước lượng concurrency trước khi tăng global default.

### 44.3. max_connections

Tăng giới hạn có thể làm tăng process/memory pressure. Dùng pooler và concurrency control trước khi nâng giới hạn nếu application tạo quá nhiều sessions.

### 44.4. Planner cost parameters

random_page_cost/effective_cache_size ảnh hưởng planner estimates, không trực tiếp tăng tốc disk. Tuning sai có thể làm plan xấu hơn.

### 44.5. Checkpoint/autovacuum settings

Tăng/giảm phải dựa trên WAL rate, dirty buffers, vacuum backlog và storage capacity. Đừng disable maintenance để che triệu chứng.

## 45. Monitoring dashboard và alert design

Dashboard cần cho biết workload đang ở trạng thái nào và resource nào giới hạn.

### 45.1. Workload panel

TPS/QPS, query class, p50/p95/p99, errors, pool wait, active sessions và transaction duration.

### 45.2. PostgreSQL panel

Top queries by total time, mean time, calls, temp blocks, buffers, WAL bytes, wait events, blockers và deadlocks.

### 45.3. Host/storage panel

CPU/run queue, available memory/swap, disk latency/IOPS/throughput/queue, filesystem free space và network throughput/retransmits.

### 45.4. Maintenance/replication panel

Autovacuum activity, dead tuples, checkpoint/WAL rate, archive lag, replication lag và slot retention.

### 45.5. Alert theo SLO và trend

Alert sustained p99/throughput/error violations, disk forecast, slot WAL growth, blocked transaction age và replica freshness. Đặt duration/threshold để giảm noise.

## 46. Anti-patterns khi tìm bottleneck

1. Tăng shared_buffers chỉ vì RAM còn trống.
2. Tăng work_mem toàn cục vì một query spill.
3. Tăng max_connections để chữa pool wait.
4. Tạo index cho mọi filter mà không tính write amplification.
5. Dùng EXPLAIN ANALYZE trên statement có side effects hoặc load không kiểm soát.
6. Coi blks_read là physical disk reads chắc chắn.
7. Coi CPU thấp là database không bottleneck.
8. Coi CPU cao là luôn cần thêm cores.
9. Kill backend lâu nhất mà không kiểm tra blocker/transaction owner.
10. Disable autovacuum để giảm I/O.
11. Chạy backup/batch cùng peak mà không đo interference.
12. Benchmark trên dataset quá nhỏ hoặc cache luôn warm.
13. So sánh metrics cumulative thay vì delta/rate.
14. Đọc một snapshot wait event như toàn bộ lịch sử.
15. Thay nhiều parameters cùng lúc rồi không biết thay đổi nào có tác dụng.
16. Tối ưu average latency nhưng bỏ qua p99.
17. Chỉ nhìn query time mà không đo pool wait/network/application time.
18. Scale storage mà không xác định IOPS, throughput hay latency là giới hạn.
19. Scale CPU trong khi query đang chờ lock.
20. Không có rollback criteria hoặc post-change monitoring.

## 47. Lab: phân loại workload và lập baseline

Dùng database thử nghiệm có query mix gần một ứng dụng thực tế.

### 47.1. Mô tả workload

Liệt kê API transactions, reporting queries, batch writes và background maintenance. Ghi frequency, concurrency, read/write mix và freshness requirement.

### 47.2. Thu thập baseline

Lấy pg_stat_database, pg_stat_user_tables, pg_stat_activity, pg_stat_statements và OS metrics trong peak window.

### 47.3. Đánh dấu events

Ghi deploy, batch, vacuum, backup và traffic spikes trên cùng timeline.

### 47.4. Tạo workload profile

Tổng hợp TPS, p50/p95/p99, active sessions, top queries, temp bytes, CPU, memory, disk và network.

### 47.5. Đưa ra giả thuyết

Chọn một bottleneck có bằng chứng, nêu metric cần thay đổi nếu hypothesis đúng và điều gì sẽ bác bỏ nó.

## 48. Lab: tìm CPU, I/O và lock bottleneck

### 48.1. CPU workload

Chạy query aggregate/join trên dataset lab, tăng concurrency từng bước. Theo dõi process CPU, run queue, TPS và latency.

### 48.2. I/O workload

Dùng dataset lớn hơn memory cache hoặc scan nhiều pages. Theo dõi wait events, pg_stat_io (PostgreSQL 16+), storage latency và queue.

### 48.3. Lock workload

Mở transaction update một row rồi giữ transaction trong lab. Từ session khác cập nhật cùng row và xem pg_blocking_pids/pg_stat_activity.

### 48.4. So sánh symptoms

Ghi CPU, I/O waits, lock waits và latency trong từng test. Xác định tại sao cùng một symptom latency cao lại có nguyên nhân khác nhau.

### 48.5. Cleanup

Rollback/commit lab transactions và dừng workload generator. Không để sessions giữ locks/snapshots sau test.


## 49. Lab: tìm query đắt và kiểm chứng tuning

### 49.1. Thu top queries

Dùng pg_stat_statements để tìm query theo total_exec_time, calls, mean time, temp blocks và shared reads.

### 49.2. Chụp plan

Chạy EXPLAIN trước; dùng EXPLAIN ANALYZE trên lab khi an toàn. Ghi estimated/actual rows, loops, buffers, temp I/O và execution time.

### 49.3. Thử một thay đổi

Ví dụ cập nhật statistics, sửa predicate, thêm index phù hợp hoặc giảm rows trước sort. Chỉ thay một biến mỗi lần.

### 49.4. Benchmark lại

Chạy cùng data, query parameters, concurrency và cache conditions. So sánh p95/p99, throughput và resource consumption.

### 49.5. Ghi trade-off

Một index có thể cải thiện SELECT nhưng làm INSERT/UPDATE chậm hơn. Đánh giá toàn query mix trước khi giữ thay đổi.

## 50. Checklist xác định bottleneck

- [ ] Workload class và SLO đã được xác định?
- [ ] Có baseline đủ dài và timestamp đồng bộ?
- [ ] Throughput, p50/p95/p99 và queue depth được đo?
- [ ] Top query fingerprints/calls/total time đã biết?
- [ ] Wait events và blocking chains đã được kiểm tra?
- [ ] CPU/run queue/memory/swap có dữ liệu cùng thời điểm?
- [ ] Storage latency/IOPS/throughput/queue đã đo?
- [ ] Network/pool wait/result size đã xem?
- [ ] WAL/checkpoint/autovacuum/replication có gây interference?
- [ ] Query plan và estimated/actual rows đã đối chiếu?
- [ ] Hypothesis có bằng chứng và cách bác bỏ?
- [ ] Benchmark đại diện có cùng workload/data shape?
- [ ] Có rollback criteria và post-change monitoring?
- [ ] SLO và capacity headroom được đáp ứng sau thay đổi?

## 51. Bảng tra cứu nhanh

| Thành phần | Dùng để hiểu |
|---|---|
| OLTP | Transaction nhỏ, latency-sensitive |
| OLAP | Scan/join/aggregate dữ liệu lớn |
| Throughput | Work hoàn thành mỗi đơn vị thời gian |
| p95/p99 latency | Tail response time |
| pg_stat_database | Counters cấp database |
| pg_stat_user_tables | Table scans, tuples, vacuum/analyze |
| pg_stat_statements | Query-level aggregates |
| pg_stat_activity | Sessions, states, waits |
| pg_blocking_pids | Blocking sessions |
| pg_stat_io | I/O stats theo backend/object/context trên PostgreSQL 16+ |
| pg_stat_wal | WAL activity stats theo version |
| EXPLAIN | Estimated execution plan |
| EXPLAIN ANALYZE | Actual execution và timing |
| BUFFERS | Buffer activity trong plan |
| work_mem | Memory budget cơ bản cho sort/hash operation |
| shared_buffers | PostgreSQL shared buffer cache |
| max_connections | Giới hạn client connections |
| IOPS | Storage operations/second |
| Throughput | Bytes/second |
| Queue depth | I/O requests đang chờ/được xử lý |
| WAL | Write-Ahead Log |
| Checkpoint | Ghi dirty buffers theo checkpoint process |
| Autovacuum | Cleanup/analyze tự động |
| Connection pool | Tái sử dụng và giới hạn sessions |
| Bottleneck | Resource/dependency giới hạn throughput hoặc latency |
| Headroom | Capacity dự phòng dưới saturation |
| pgbench | Benchmark workload generator |

## 52. Kết luận

**Phân loại workload trước, đo bottleneck sau, rồi mới chọn cách tối ưu.** OLTP, OLAP, reporting và batch có mục tiêu khác nhau; cần mô tả chúng bằng query mix, transaction duration, throughput, latency percentiles, concurrency, data distribution và consistency requirements. Baseline phải bao phủ peak windows và ghi cùng timeline với deployments, backups, vacuum và batch events.

PostgreSQL cung cấp statistics views để hiểu database/query activity; OS và storage metrics cho biết host đang bị giới hạn ở đâu; EXPLAIN/EXPLAIN ANALYZE giúp tìm plan nodes và cardinality errors. CPU cao, I/O waits, lock waits, pool wait, temp files và WAL pressure cần các hướng điều tra khác nhau. Một query chậm không nhất thiết là thiếu tài nguyên, và một host CPU thấp không có nghĩa database không bottleneck.

Quy trình hiệu quả là xác định SLO/impact, thu thập metrics đồng bộ, lập hypothesis cụ thể, kiểm chứng bằng plan hoặc controlled benchmark, thay một biến mỗi lần và đo lại toàn workload. Capacity planning phải tính cả peak, background maintenance, replication, backup, failover và headroom. Tuning shared_buffers, work_mem, max_connections hay storage chỉ có ý nghĩa khi có bằng chứng về giới hạn đang gặp.

Nguyên tắc vận hành: **đo đúng workload, phân biệt execution với waiting, xác định bottleneck bằng nhiều nguồn dữ liệu, và chứng minh cải thiện bằng benchmark đại diện cùng SLO.**


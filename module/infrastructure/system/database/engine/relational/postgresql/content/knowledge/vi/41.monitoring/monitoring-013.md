# Lưu baseline và đối chiếu chỉ số trước sau thay đổi trong PostgreSQL

## 1. Vì sao cần baseline?

Một thay đổi PostgreSQL có thể làm hệ thống nhanh hơn ở một khía cạnh nhưng chậm hơn ở khía cạnh khác. Thêm index có thể giảm thời gian đọc nhưng tăng chi phí INSERT/UPDATE và dung lượng lưu trữ. Tăng memory cho một workload có thể giảm physical reads nhưng làm giảm RAM còn lại cho hệ điều hành hoặc các services khác. Thay đổi autovacuum có thể giảm dead tuples nhưng làm tăng I/O trong giờ cao điểm.

Nếu chỉ nhìn một biểu đồ sau khi triển khai, rất khó kết luận thay đổi có tạo ra khác biệt hay không. Cần lưu baseline: tập hợp số liệu đại diện cho trạng thái hệ thống trước thay đổi, kèm thời gian đo, workload, cấu hình và bối cảnh vận hành. Sau thay đổi, thu thập cùng nhóm metrics theo cách tương đương rồi đối chiếu.

Baseline giúp trả lời các câu hỏi cụ thể:

- Throughput có tăng hoặc giảm không?
- Latency p50, p95 và p99 thay đổi thế nào?
- Error rate, timeout và failed transactions có tăng không?
- CPU, memory, disk I/O, network và connection pressure biến động ra sao?
- Query nào thay đổi nhiều nhất?
- Replication lag, WAL generation hoặc vacuum behavior có xấu đi không?
- Kết quả có còn đúng khi chuẩn hóa theo lượng request/transaction?
- Có thể quy kết khác biệt cho thay đổi vừa triển khai hay còn yếu tố khác?
- Ngưỡng nào buộc phải rollback?

Baseline không chỉ là một ảnh chụp số liệu. Nó là một phép đo có thể lặp lại, có phạm vi và điều kiện rõ ràng.

```text
        CHANGE PROPOSAL
              |
              v
     Define expected outcome
              |
              v
     Capture PRE-CHANGE baseline
              |
              v
       Apply one controlled change
              |
              v
     Capture POST-CHANGE metrics
              |
              v
   Normalize for workload and duration
              |
              v
   Compare outcomes and guardrails
          /             \
         v               v
      Accept           Roll back
         |
         v
   Save evidence and new baseline
```

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích baseline và vai trò của nó trong vận hành PostgreSQL.
2. Phân biệt counter tích lũy, gauge tức thời, rate và percentile.
3. Xác định phạm vi, thời lượng và workload cần đo.
4. Ghi lại PostgreSQL version, cấu hình, topology và môi trường.
5. Thu thập database, query, connection, lock, vacuum và replication metrics.
6. Theo dõi WAL generation, checkpoint và I/O.
7. Dùng pg_stat_statements để so sánh workload theo query fingerprint.
8. Chuẩn hóa số liệu theo transaction, request hoặc đơn vị công việc.
9. Phân biệt cache hit ratio với disk I/O thực tế.
10. Đọc pg_stat_activity và wait events.
11. Phát hiện statistics reset và các thay đổi làm sai phép so sánh.
12. So sánh trước/sau bằng cùng cửa sổ thời gian và điều kiện tải.
13. Đánh giá thay đổi query plan bằng EXPLAIN.
14. Kết hợp PostgreSQL metrics với OS, application và infrastructure metrics.
15. Thiết lập guardrails và rollback criteria.
16. Lưu baseline có metadata và lịch sử thay đổi.
17. Tránh kết luận sai do workload seasonality hoặc traffic mix.
18. Xây dashboard so sánh và báo cáo change impact.
19. Diễn giải regression, improvement và trade-off.
20. Tổ chức quy trình đo lường lặp lại sau mỗi thay đổi quan trọng.

## 3. Baseline là gì và cần lưu những gì?

### 3.1. Baseline mô tả trạng thái có thể so sánh

Một baseline hữu ích ghi lại không chỉ giá trị metric mà cả điều kiện tạo ra giá trị đó. Ví dụ, CPU 65% không có ý nghĩa đầy đủ nếu không biết số request/second, loại query, số connections và thời điểm trong ngày.

Mỗi lần đo nên có metadata:

- Cluster/database identity và môi trường.
- PostgreSQL major/minor version.
- Thời gian bắt đầu/kết thúc và timezone.
- Primary/standby role, timeline và replication topology.
- CPU, RAM, storage type/capacity và network placement.
- Các cấu hình quan trọng từ pg_settings.
- Phiên bản ứng dụng, schema migration và release ID.
- Workload profile: requests, transactions, batch jobs, concurrency.
- Maintenance đang diễn ra: VACUUM, ANALYZE, backup, index build.
- Statistics reset time và thời điểm restart.
- Thay đổi khác xảy ra trong cửa sổ đo.
- Người thực hiện và change ticket.

### 3.2. Baseline có nhiều tầng

Có thể tổ chức baseline thành bốn nhóm:

| Tầng | Nội dung | Ví dụ |
| --- | --- | --- |
| Business/application | Người dùng và workload | requests/s, transactions/s, p95 latency, error rate |
| PostgreSQL | Database behavior | commits, rollbacks, query time, cache, WAL, locks |
| Host/infrastructure | Tài nguyên | CPU, RAM, disk latency, IOPS, network |
| Configuration/topology | Điều kiện hệ thống | version, settings, replicas, storage, pool size |

Một thay đổi có thể tác động gián tiếp. Ví dụ, query nhanh hơn nhưng connection pool giữ connection lâu hơn, làm tổng số active sessions tăng. Cần xem các tầng cùng lúc.

### 3.3. Baseline trước thay đổi không phải một giá trị duy nhất

Một ảnh chụp lúc 02:00 có thể không đại diện cho giờ cao điểm. Nên đo qua nhiều cửa sổ tương đương và lưu cả phân bố, peak và trend.

### 3.4. Tạo baseline mới sau khi thay đổi được chấp nhận

Khi một thay đổi đã được xác nhận ổn định, kết quả post-change có thể trở thành baseline mới cho các lần thay đổi tiếp theo. Giữ lại baseline cũ để truy vết lịch sử, không ghi đè mất dữ liệu.

## 4. Thiết kế phép đo trước khi thu thập

### 4.1. Viết giả thuyết

Mỗi thay đổi nên có một giả thuyết kiểm chứng được.

Ví dụ:

- Thêm index vào bảng orders sẽ giảm p95 của truy vấn tìm đơn hàng.
- Điều chỉnh pool size sẽ giảm thời gian chờ connection.
- Thay autovacuum threshold sẽ giảm dead tuple accumulation.
- Thay đổi synchronous replication sẽ làm commit latency tăng nhưng giảm RPO.
- Tối ưu query sẽ giảm shared buffer reads và tổng execution time.

Giả thuyết cần nêu metric chính và các metric guardrail có thể xấu đi.

### 4.2. Chọn primary metrics và guardrails

Ví dụ với index mới:

| Vai trò | Metric |
| --- | --- |
| Primary outcome | Query p95 latency, execution time/request |
| Guardrail | INSERT/UPDATE latency, WAL bytes, index size |
| Capacity | CPU, I/O latency, free disk |
| Correctness | Row counts, query result consistency |
| Availability | Error rate, connection failures |

Đừng chỉ chọn metric có khả năng cải thiện. Ghi trước cả các chỉ số có thể bị ảnh hưởng xấu.

### 4.3. Chọn cửa sổ đo

Cửa sổ pre và post cần tương đương về:

- Giờ trong ngày và ngày trong tuần.
- Traffic volume và loại request.
- Batch/cron jobs.
- Data size và cache warmness.
- Số clients và concurrency.
- Maintenance activities.
- Replica state và network conditions.

Nếu workload thay đổi mạnh, chuẩn hóa theo request/transaction hoặc dùng load test có kịch bản cố định.

### 4.4. Giữ thời lượng đủ dài

Một phép đo ngắn có thể bỏ lỡ checkpoint, autovacuum, batch job hoặc peak traffic. Thời lượng phụ thuộc chu kỳ workload; hệ thống có batch hằng ngày cần cửa sổ dài hơn một API service ổn định.

### 4.5. Chỉ thay một biến chính khi có thể

Nếu cùng lúc đổi index, PostgreSQL memory settings, connection pool và application release, kết quả khó quy cho một thay đổi. Tách thành các bước nhỏ hoặc thiết kế thử nghiệm có nhóm control/canary.

## 5. Phân loại metric để tránh đọc sai

### 5.1. Counter tích lũy

Counter thường tăng từ lần reset gần nhất, ví dụ:

- xact_commit và xact_rollback.
- blks_read và blks_hit.
- wal_bytes.
- shared_blks_read trong pg_stat_statements.
- confl_snapshot trong pg_stat_database_conflicts.

Không so sánh trực tiếp counter tích lũy giữa hai thời điểm nếu thời lượng khác nhau. Lấy delta rồi tính rate.

Công thức:

```text
delta = counter_after - counter_before
rate_per_second = delta / elapsed_seconds
rate_per_transaction = delta / committed_transactions
```

Nếu counter giảm, có thể statistics đã reset, server restart hoặc view/identity thay đổi. Kiểm tra reset timestamp trước khi tính.

### 5.2. Gauge tức thời

Gauge là trạng thái tại một thời điểm:

- numbackends.
- Số active sessions.
- Disk free space.
- Replication lag hiện tại.
- Memory usage.
- Số locks đang chờ.

Lưu theo chu kỳ để tính min/median/max và phân vị; một snapshot không mô tả peak trong cửa sổ.

### 5.3. Rate

Rate là lượng thay đổi trong một đơn vị thời gian, ví dụ transactions/s, WAL MB/s, reads/s hoặc requests/s. Rate phù hợp để so sánh cửa sổ có độ dài khác nhau, nhưng vẫn cần xem workload mix.

### 5.4. Percentile và histogram

Latency p50/p95/p99 cho biết phân bố thời gian phản hồi. Mean có thể che giấu tail latency: phần lớn requests nhanh nhưng một số ít rất chậm.

PostgreSQL statistics views không cung cấp percentile latency đầy đủ cho mọi query. Thu thập histogram từ application tracing, APM, proxy hoặc metrics system. pg_stat_statements cung cấp tổng và trung bình theo query fingerprint, không thay histogram.

### 5.5. Ratio

Cache hit ratio, error percentage và replication success ratio là ratio. Tính từ delta của numerator/denominator trong cùng cửa sổ khi có thể. Không lấy trung bình đơn giản các ratio của nhiều khoảng có số lượng request khác nhau.

### 5.6. Snapshot và delta phải được ghép cặp

Mỗi snapshot cần timestamp và metadata. Dùng cùng instance, database, role và metric definition. Không trừ counter từ hai server hoặc hai lần reset khác nhau.

## 6. Ghi metadata và cấu hình PostgreSQL

### 6.1. Version và identity

```sql
SELECT
    version() AS server_version,
    current_setting('server_version_num') AS server_version_num,
    current_database() AS database_name,
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port,
    pg_postmaster_start_time() AS server_started_at,
    clock_timestamp() AS captured_at;
```

Trên Unix socket, inet_server_addr() có thể NULL. Lưu cluster identity từ inventory/backup metadata nếu cần phân biệt các instances có cùng database name.

### 6.2. Các settings quan trọng

```sql
SELECT
    name,
    setting,
    unit,
    context,
    source,
    sourcefile,
    sourceline,
    pending_restart
FROM pg_catalog.pg_settings
WHERE name IN (
    'shared_buffers',
    'work_mem',
    'maintenance_work_mem',
    'effective_cache_size',
    'max_connections',
    'max_worker_processes',
    'max_parallel_workers',
    'max_parallel_workers_per_gather',
    'autovacuum',
    'autovacuum_max_workers',
    'checkpoint_timeout',
    'checkpoint_completion_target',
    'max_wal_size',
    'min_wal_size',
    'wal_level',
    'synchronous_commit',
    'synchronous_standby_names',
    'effective_io_concurrency'
)
ORDER BY name;
```

Không phải setting nào cũng có trên mọi major version. Với cấu hình quan trọng khác, thêm vào danh sách theo change đang đánh giá. sourcefile có thể NULL nếu role không có quyền xem file cấu hình hoặc setting không đến từ file.

### 6.3. Phân biệt setting đã nạp và file đã sửa

pg_settings.setting là giá trị hiệu lực tại runtime. pending_restart = true cho biết một số thay đổi chưa có hiệu lực vì cần restart. Không dùng nội dung file cấu hình làm bằng chứng duy nhất rằng server đã chạy với giá trị mới.

### 6.4. Ghi cấu hình theo role

Với HA, lưu settings riêng của primary và từng standby. Một số setting có semantics khác nhau theo role hoặc chỉ có hiệu lực ở một node. Ghi lại topology và synchronous standby state cùng baseline.

### 6.5. Bảo vệ metadata nhạy cảm

Không đưa password, connection strings chứa secrets, private keys hoặc tokens vào baseline export. Lưu tên secret reference và version nếu cần truy vết.

## 7. Database-level metrics từ pg_stat_database

### 7.1. Snapshot cơ bản

```sql
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
    conflicts,
    temp_files,
    temp_bytes,
    deadlocks,
    stats_reset
FROM pg_catalog.pg_stat_database
WHERE datname IS NOT NULL
ORDER BY datname;
```

Đây là các counters/gauges tích lũy từ lần reset statistics gần nhất, tùy semantics của từng cột. Lưu snapshot trước và sau cửa sổ đo.

### 7.2. Transactions per second

Dùng delta xact_commit + xact_rollback chia cho thời gian đo để ước lượng transaction completion rate. Nếu ứng dụng có transactions rỗng hoặc nhiều statements trong một transaction, TPS không đồng nghĩa request rate.

### 7.3. Rollback rate

```text
rollback_ratio = delta_xact_rollback
                 / (delta_xact_commit + delta_xact_rollback)
```

Một tỷ lệ rollback tăng có thể chỉ ra application errors, retry logic hoặc transaction conflicts. Phân loại SQLSTATE và application logs trước khi kết luận.

### 7.4. Cache hit ratio

```sql
SELECT
    datname,
    round(
        100.0 * blks_hit
        / NULLIF(blks_hit + blks_read, 0),
        2
    ) AS shared_buffer_hit_pct
FROM pg_catalog.pg_stat_database
WHERE datname IS NOT NULL;
```

Đây là tỷ lệ hit trong PostgreSQL shared buffers theo các counters của database. blks_read không đồng nghĩa chắc chắn phải đọc storage vật lý: OS page cache có thể phục vụ read. Không dùng một ngưỡng hit ratio đơn lẻ để quyết định tăng shared_buffers.

### 7.5. Temporary files

temp_files và temp_bytes tăng có thể cho thấy sorts, hashes hoặc materialization spill ra disk. So sánh delta theo transaction/request và xem query nào tạo temp blocks trong pg_stat_statements.

### 7.6. Database conflicts

Trên standby, pg_stat_database_conflicts cung cấp counters cho các recovery conflicts. Ghi snapshot riêng nếu thay đổi liên quan tới hot standby, VACUUM, DDL hoặc replay delay.

## 8. Query-level baseline với pg_stat_statements

### 8.1. Vì sao cần query fingerprint?

Database-level TPS có thể không đổi nhưng một query quan trọng chậm hơn nhiều. pg_stat_statements nhóm các câu lệnh tương tự theo query identity, cho phép tìm query chiếm phần lớn execution time hoặc I/O.

### 8.2. Cài đặt và điều kiện

Extension thường cần được nạp qua shared_preload_libraries, sau đó restart server và tạo extension trong database phù hợp:

```sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
```

Chỉ thực hiện setup theo change process. Cần kiểm tra pg_stat_statements.track, pg_stat_statements.max, track_planning và reset/deallocation behavior theo version. Extension có thể tạo overhead, vì vậy cấu hình tracking phù hợp với mục tiêu đo.

### 8.3. Snapshot các query tốn thời gian

```sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    shared_blks_dirtied,
    shared_blks_written,
    temp_blks_read,
    temp_blks_written,
    wal_bytes,
    left(query, 300) AS query_sample
FROM pg_catalog.pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 50;
```

Các cột phụ thuộc version/extension version. Nếu một cột không tồn tại, kiểm tra schema của view trên server thay vì giả định mọi cluster giống nhau.

### 8.4. So sánh delta theo queryid

Lưu snapshot trước và sau. Ghép cùng queryid trong cùng database/user context, sau đó tính:

- Delta calls.
- Delta total_exec_time.
- Delta rows.
- Delta shared_blks_read/hit.
- Delta temp blocks.
- Delta wal_bytes.

Từ delta, tính mean execution time trong cửa sổ:

```text
window_mean_exec_ms = delta_total_exec_time / NULLIF(delta_calls, 0)
```

Không trừ trực tiếp mean_exec_time trước và sau vì đó là trung bình tích lũy từ lần reset, không phải trung bình riêng của cửa sổ hiện tại.

### 8.5. Queryid có thể thay đổi

Query fingerprint có thể khác theo PostgreSQL version, normalization hoặc query text changes. Lưu query sample, database, user và version cùng queryid. Không ghép chỉ bằng queryid giữa clusters/version khác nhau mà chưa xác minh.

### 8.6. Total time và mean time trả lời hai câu hỏi

Một query có mean thấp nhưng được gọi hàng triệu lần có thể tiêu thụ phần lớn tổng CPU. Một query hiếm có mean cao có thể gây tail latency. Xếp hạng theo total time, calls và mean cùng lúc.

### 8.7. pg_stat_statements không cung cấp p95

Mean execution time không thể thay p95/p99. Dùng APM, tracing hoặc application histogram để đo latency end-to-end và tail latency. Đối chiếu với query-level stats để tìm nguồn.

### 8.8. Reset và deallocation

pg_stat_statements_reset() xóa statistics và làm phép so sánh delta không còn hợp lệ nếu không có snapshot trước reset. View pg_stat_statements_info ở các version hỗ trợ có thể giúp theo dõi reset/deallocation. Lưu reset timestamps cùng dữ liệu.

## 9. Connection và transaction metrics

### 9.1. Phân bố connection state

```sql
SELECT
    datname,
    state,
    wait_event_type,
    wait_event,
    count(*) AS sessions
FROM pg_catalog.pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY datname, state, wait_event_type, wait_event
ORDER BY datname, sessions DESC;
```

Các state thường gặp gồm active, idle và idle in transaction. Một lượng lớn idle connections có thể bình thường nếu dùng pool; cần so với pool configuration và max_connections.

### 9.2. Active query và wait events

```sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    query_start,
    clock_timestamp() - query_start AS query_age,
    xact_start,
    clock_timestamp() - xact_start AS transaction_age,
    left(query, 300) AS query_sample
FROM pg_catalog.pg_stat_activity
WHERE backend_type = 'client backend'
  AND state = 'active'
ORDER BY query_start;
```

Wait event giúp phân biệt query đang chạy CPU với query đang chờ lock, I/O, client hoặc một resource khác. Tên và cách phân loại event có thể thay đổi theo version.

### 9.3. Idle in transaction

```sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    xact_start,
    clock_timestamp() - xact_start AS xact_age,
    state_change,
    clock_timestamp() - state_change AS state_age,
    backend_xmin,
    left(query, 200) AS last_query
FROM pg_catalog.pg_stat_activity
WHERE state LIKE 'idle in transaction%'
ORDER BY xact_start;
```

Transactions mở lâu có thể giữ snapshots, locks và vacuum horizons. So sánh trước/sau thay đổi connection pool hoặc application transaction handling.

### 9.4. Connection saturation

Đối chiếu numbackends, max_connections, pool active/idle/waiting và connection establishment rate. Không tăng max_connections chỉ vì thấy nhiều sessions; mỗi backend có chi phí memory và scheduling.

### 9.5. Ghi nhận connection churn

Một pool tạo/hủy connections liên tục có thể làm tăng authentication overhead và backend startup. Theo dõi số connections mới, pool wait time và PostgreSQL connection failures từ application metrics.

## 10. Lock và blocking metrics

### 10.1. Đếm locks đang chờ

```sql
SELECT
    locktype,
    mode,
    relation::regclass AS relation,
    count(*) AS waiting_locks
FROM pg_catalog.pg_locks
WHERE NOT granted
GROUP BY locktype, mode, relation
ORDER BY waiting_locks DESC;
```

### 10.2. Tìm blocker và blocked session

```sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.application_name AS blocked_app,
    blocked.wait_event_type,
    blocked.wait_event,
    clock_timestamp() - blocked.query_start AS blocked_query_age,
    blocker.pid AS blocker_pid,
    blocker.application_name AS blocker_app,
    blocker.state AS blocker_state,
    clock_timestamp() - blocker.xact_start AS blocker_xact_age,
    left(blocked.query, 200) AS blocked_query,
    left(blocker.query, 200) AS blocker_query
FROM pg_catalog.pg_stat_activity AS blocked
CROSS JOIN LATERAL unnest(pg_catalog.pg_blocking_pids(blocked.pid)) AS b(pid)
JOIN pg_catalog.pg_stat_activity AS blocker
  ON blocker.pid = b.pid
ORDER BY blocked.query_start;
```

Một lock snapshot không đủ để mô tả vấn đề. Lưu số lần blocking, duration và query identity trong cửa sổ đo.

### 10.3. Deadlocks

Dùng delta deadlocks từ pg_stat_database, đồng thời giữ PostgreSQL logs có log_lock_waits/deadlock reports theo policy. Deadlock count tăng là guardrail quan trọng khi thay schema, index hoặc transaction boundaries.

### 10.4. Lock timeout và statement timeout

Nếu thay đổi timeout settings, ghi cả số query bị timeout/cancel trong application logs. Một p95 tốt hơn do query bị hủy không phải improvement.

## 11. Vacuum, analyze và table health

### 11.1. Table statistics

```sql
SELECT
    schemaname,
    relname,
    seq_scan,
    idx_scan,
    n_live_tup,
    n_dead_tup,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_catalog.pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 50;
```

Các tuple counts là estimates. So sánh trend và relation size, không xem chúng như exact row counts.

### 11.2. VACUUM progress

```sql
SELECT
    p.pid,
    p.relid::regclass AS relation,
    p.phase,
    p.heap_blks_total,
    p.heap_blks_scanned,
    p.heap_blks_vacuumed,
    a.query_start,
    clock_timestamp() - a.query_start AS runtime,
    a.wait_event_type,
    a.wait_event
FROM pg_catalog.pg_stat_progress_vacuum AS p
JOIN pg_catalog.pg_stat_activity AS a
  ON a.pid = p.pid
ORDER BY a.query_start;
```

### 11.3. Analyze freshness

Sau thay đổi data distribution hoặc bulk load, statistics có thể chưa được ANALYZE cập nhật. Query plan có thể thay đổi vì stats stale, không phải vì index/config mới. Ghi lại thời điểm analyze và last_autoanalyze.

### 11.4. XID age và freeze safety

Theo dõi database/table transaction age, autovacuum progress và anti-wraparound warnings. Thay đổi giữ snapshots lâu hoặc tăng write churn có thể làm freeze pressure tăng.

### 11.5. VACUUM không nhất thiết thu nhỏ file

VACUUM thường đánh dấu space để PostgreSQL tái sử dụng. Relation file có thể không giảm size trên filesystem. Nếu đánh giá storage, xem free space, relation growth và bloat measurement phù hợp; không kết luận VACUUM thất bại chỉ vì file không shrink.

## 12. WAL, checkpoint và write workload

### 12.1. pg_stat_wal

Ở các PostgreSQL versions có view này, thu thập:

```sql
SELECT *
FROM pg_catalog.pg_stat_wal;
```

Các counters hữu ích gồm WAL records, full-page images, bytes và WAL buffers full. Lưu reset context nếu view cung cấp.

### 12.2. WAL bytes per second

Tính delta wal_bytes chia elapsed seconds. So sánh theo transaction hoặc request để xem một thay đổi làm tăng write amplification hay không.

### 12.3. Full-page images

wal_fpi tăng có thể liên quan tới checkpoint cadence, page modifications và full-page write behavior. Không diễn giải riêng lẻ; đối chiếu WAL volume, checkpoint activity và workload.

### 12.4. Checkpoint metrics

Các view checkpoint/background writer thay đổi giữa major versions. Một số version mới tách pg_stat_checkpointer khỏi pg_stat_bgwriter. Trước khi xây dashboard, kiểm tra view và columns của server thực tế.

Theo dõi checkpoint count, write/sync time, buffers written, backend writes và checkpoint warnings nếu có. So sánh theo cửa sổ và workload.

### 12.5. WAL volume là guardrail cho index/schema changes

Tạo index, bulk update hoặc thay đổi application write pattern có thể làm WAL tăng. Kiểm tra archive bandwidth, replication lag, backup storage và disk headroom cùng lúc.

## 13. I/O và storage metrics

### 13.1. PostgreSQL shared buffer metrics

blks_read/blks_hit ở pg_stat_database phản ánh truy cập shared buffers. Chúng không đo đầy đủ physical disk reads vì OS cache và storage layers có thể phục vụ dữ liệu.

### 13.2. pg_stat_io

PostgreSQL 16 trở lên có pg_stat_io để phân tích I/O theo backend type, object và context:

```sql
SELECT
    backend_type,
    object,
    context,
    reads,
    writes,
    extends,
    op_bytes,
    hits,
    evictions,
    reuses,
    fsyncs,
    read_time,
    write_time,
    extend_time,
    fsync_time
FROM pg_catalog.pg_stat_io
ORDER BY backend_type, object, context;
```

Các cột và timing behavior phụ thuộc version/configuration. Một số timing chỉ được ghi khi track_io_timing được bật. Kiểm tra schema thực tế.

### 13.3. track_io_timing

```sql
SHOW track_io_timing;
```

Bật timing có thể có overhead tùy platform. Nếu cần so sánh I/O time, giữ setting nhất quán trước/sau và ghi rõ trạng thái.

### 13.4. OS-level metrics

Kết hợp với hệ điều hành hoặc cloud monitoring:

- Device read/write latency.
- IOPS và throughput.
- Queue depth.
- CPU iowait.
- Disk utilization.
- Filesystem free space.
- Network throughput/packet retransmits.
- Memory pressure, swap và OOM events.

### 13.5. Storage latency có thể bị che bởi cache

Một query có nhiều shared buffer hits vẫn có thể bị ảnh hưởng bởi WAL fsync, temp file I/O hoặc storage latency trên đường ghi. Theo dõi reads và writes riêng.

## 14. Replication và standby metrics

### 14.1. Primary: pg_stat_replication

```sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag,
    reply_time
FROM pg_catalog.pg_stat_replication
ORDER BY application_name;
```

### 14.2. Standby: receive và replay

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_commit_time;
```

### 14.3. WAL receiver

```sql
SELECT *
FROM pg_catalog.pg_stat_wal_receiver;
```

View không có row thường có nghĩa không có WAL receiver connection đang hoạt động tại thời điểm lấy snapshot. Kết hợp logs và recovery state.

### 14.4. LSN span không phải thời gian lag

Có thể dùng pg_wal_lsn_diff() để đo khoảng byte giữa hai LSN cùng WAL history. Không chuyển trực tiếp byte thành giây nếu WAL generation rate biến động.

### 14.5. Lag metric có thể stale khi workload idle

Replication lag intervals không phải lúc nào cũng thể hiện thời gian bắt kịp trong mọi trạng thái. Khi không có WAL mới, timestamp/lag có thể phản ánh message gần nhất thay vì một backlog đang tăng. Dùng LSNs, WAL generation rate và workload context.

### 14.6. Logical subscriptions

Nếu thay đổi liên quan logical replication, bổ sung pg_stat_subscription, pg_subscription_rel, replication origins và apply error counters theo version. Physical replication metrics không đủ mô tả logical apply progress.

## 15. Application và infrastructure metrics

### 15.1. Database không thấy toàn bộ trải nghiệm người dùng

PostgreSQL có thể báo query execution time thấp nhưng application vẫn chậm do connection pool wait, network, serialization, queueing hoặc external services. Thu thập end-to-end latency.

### 15.2. Metrics nên lấy từ application/APM

- Request rate và transaction rate.
- p50/p95/p99 latency.
- Error/timeout rate.
- Retry count và retry success.
- Connection pool active/idle/waiting.
- Connection acquisition latency.
- Queue depth và worker utilization.
- Cache hit/miss ở application layer.
- External dependency latency.

### 15.3. Infrastructure metrics

Lưu CPU utilization, load average, memory available, swap, disk latency, IOPS, throughput, network throughput và packet drops. Với cloud storage, lấy metrics từ provider monitoring.

### 15.4. Đồng bộ timestamp

Đảm bảo PostgreSQL, application, monitoring và host clocks đồng bộ. Dùng UTC hoặc timestamp có offset. Clock skew có thể khiến một event bị ghép với sai cửa sổ.

### 15.5. Correlation IDs

Nếu tracing có request/trace IDs, liên kết slow requests với query logs và query fingerprints khi có thể. Không đưa dữ liệu nhạy cảm hoặc full SQL parameters vào baseline không được bảo vệ.

## 16. Query plan baseline với EXPLAIN

### 16.1. Lưu execution plan của query quan trọng

```sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT order_id, created_at, status
FROM public.orders
WHERE customer_id = 42001
ORDER BY created_at DESC
LIMIT 50;
```

EXPLAIN ANALYZE thực thi query. Dùng truy vấn đọc an toàn hoặc môi trường test. Với DML, câu lệnh có thể tạo side effects; không chạy trên production chỉ để lấy plan nếu chưa có phương án an toàn.

### 16.2. So sánh actual và estimated rows

Chênh lệch lớn giữa estimated rows và actual rows có thể dẫn đến join/order strategy không phù hợp. Ghi cả plan nodes, actual time, loops và buffers.

### 16.3. BUFFERS

BUFFERS cho biết shared/local/temp buffer activity của plan. Nó giúp hiểu I/O trong PostgreSQL nhưng không đồng nhất với physical device I/O.

### 16.4. SETTINGS

SETTINGS hiển thị các planner-related settings khác default có liên quan tới plan ở các versions hỗ trợ. Ghi PostgreSQL version và effective settings cùng plan.

### 16.5. WAL option

Các versions hỗ trợ có thể thêm WAL vào EXPLAIN options để hiển thị WAL generated by statement. Kiểm tra version trước khi dùng.

### 16.6. Không so sánh plan trong điều kiện khác nhau

Plan có thể thay đổi theo statistics, parameter values, prepared statement generic/custom plans, cache state và planner settings. Giữ input representative và ghi parameter distribution.

## 17. Cách lưu snapshot và tạo delta

### 17.1. Lưu hai snapshot có nhãn

Ví dụ tên file hoặc record:

```text
2026-11-14T09:00:00Z_pre_change_release_42
2026-11-14T10:00:00Z_post_change_release_42
```

Tên thực tế cần có cluster, environment, change ID và phase. Lưu metadata riêng để máy có thể ghép các snapshot.

### 17.2. Không reset statistics để tạo baseline tùy tiện

Reset stats làm mất khả năng quan sát trend của các consumers khác và có thể ảnh hưởng dashboard. Ưu tiên chụp snapshot rồi tính delta. Chỉ reset trong test riêng hoặc khi change plan đã xác định tác động và ghi lại reset time.

### 17.3. Tính rate

```text
rate = (counter_after - counter_before) / seconds_between_snapshots
```

Tính riêng cho WAL bytes, commits, rollbacks, blocks, query calls và temp bytes.

### 17.4. Chuẩn hóa theo workload

```text
per_request_cost = delta_metric / completed_requests
per_transaction_cost = delta_metric / completed_transactions
error_rate = failed_requests / total_requests
```

Chỉ chuẩn hóa bằng denominator phù hợp. Ví dụ, một transaction có thể chứa nhiều requests; chọn đơn vị business phản ánh workload thật.

### 17.5. So sánh cùng query fingerprint

Với pg_stat_statements, tính delta theo queryid và so với số calls. Một query có tổng execution time tăng vì calls tăng gấp đôi không nhất thiết chậm hơn.

### 17.6. Xử lý missing/reset counters

Nếu snapshot sau có counter nhỏ hơn snapshot trước:

1. Kiểm tra stats_reset hoặc server restart.
2. Kiểm tra extension reset/deallocation.
3. Kiểm tra queryid hoặc database identity.
4. Đánh dấu cửa sổ không thể so sánh nếu không có snapshot mới sau reset.
5. Không biến delta âm thành zero để che vấn đề.

## 18. So sánh trước/sau công bằng

### 18.1. Match workload

So sánh cùng loại requests và transaction mix. Nếu post-change có ít report queries hơn, p95 tổng thể có thể cải thiện mà query mục tiêu không thay đổi.

### 18.2. Match duration

Cửa sổ 10 phút không so trực tiếp với cửa sổ 2 giờ bằng raw counters. Dùng rates/deltas và percentile trên cùng loại sample.

### 18.3. Match time-of-day

Traffic và cache behavior thường khác nhau theo giờ/ngày. Lấy baseline ở các cửa sổ tương đương, hoặc chạy load test cố định.

### 18.4. Warm-up

Sau restart, index build, cache invalidation hoặc deploy, hệ thống có thể cần warm-up. Tách warm-up window khỏi steady-state window. Nếu cold-start behavior quan trọng, đo riêng thay vì bỏ qua.

### 18.5. Maintenance overlap

Backup, VACUUM, ANALYZE, checkpoint, autovacuum hoặc index creation có thể làm thay đổi I/O. Ghi nhận và so sánh cùng điều kiện; không loại bỏ event nếu nó là một phần của workload production thực tế.

### 18.6. Có nhóm control khi cần

Với thay đổi có thể triển khai canary, so sánh instance/canary với control cùng lúc giúp giảm tác động seasonality. Bảo đảm control có workload và resource tương đương.

## 19. Đọc kết quả: improvement, regression và trade-off

### 19.1. Improvement

Một thay đổi có thể được xem là cải thiện khi primary outcome tốt hơn có ý nghĩa, guardrails vẫn trong giới hạn, correctness được giữ và kết quả lặp lại được.

### 19.2. Regression

Regression có thể là:

- p95/p99 latency tăng.
- Error/timeout rate tăng.
- CPU hoặc I/O saturation tăng.
- WAL bytes/request tăng mạnh.
- Replication lag vượt SLA.
- Connection pool wait tăng.
- Deadlocks hoặc lock wait tăng.
- Disk growth vượt capacity plan.

### 19.3. Trade-off

Ví dụ, synchronous replication làm commit latency tăng nhưng cải thiện durability; thêm index làm SELECT nhanh hơn nhưng write cost tăng; bật hot_standby_feedback giảm query cancellation nhưng tăng tuple retention. Báo cáo phải nêu cả lợi ích và chi phí.

### 19.4. Không kết luận từ một metric

Cache hit ratio tăng không đủ chứng minh query nhanh hơn. TPS tăng không đủ nếu error rate cũng tăng. CPU giảm không tốt nếu throughput giảm cùng lúc. Đặt metrics trong quan hệ với nhau.

### 19.5. Xem sample size

p99 từ 100 requests không ổn định bằng p99 từ hàng triệu requests. Ghi số mẫu và confidence/variability. Nếu sample nhỏ, kéo dài phép đo hoặc dùng load test.

## 20. Ví dụ đối chiếu: thêm index cho truy vấn orders

Giả sử thay đổi tạo index trên orders(customer_id, created_at DESC) để tối ưu truy vấn tìm đơn hàng gần đây.

### 20.1. Trước thay đổi

Lưu:

- Query fingerprint và execution plan.
- Calls, total execution time, mean execution time.
- Shared buffer reads/hits.
- Application p95/p99 latency.
- Request volume và concurrency.
- CPU, disk reads, WAL rate.
- Table/index size.
- INSERT/UPDATE latency.

### 20.2. Sau thay đổi

Lấy cùng các metrics trong workload tương đương. Không so sánh chỉ query SELECT mà bỏ write path.

### 20.3. Ví dụ bảng kết quả

| Metric | Trước | Sau | Diễn giải |
| --- | ---: | ---: | --- |
| Query p95 | 180 ms | 55 ms | Cải thiện truy vấn mục tiêu |
| Query calls/min | 1.000 | 1.020 | Workload gần tương đương |
| Mean execution | 90 ms | 28 ms | Giảm theo query stats |
| INSERT p95 | 12 ms | 15 ms | Write cost tăng nhẹ |
| WAL MB/min | 40 | 44 | Có thêm write amplification |
| Index size | 0 | 2,4 GB | Tăng storage |
| Error rate | 0,1% | 0,1% | Không đổi trong ví dụ |

Các con số chỉ minh họa cách trình bày, không phải mục tiêu chuẩn. Quyết định dựa trên SLA, capacity và lợi ích business.

### 20.4. Kiểm tra correctness

So sánh kết quả query trước/sau với cùng parameters. Index không được làm thay đổi kết quả logic. Kiểm tra constraints và application behavior.

## 21. Ví dụ đối chiếu: thay đổi connection pool

### 21.1. Giả thuyết

Tăng pool size có thể giảm thời gian chờ lấy connection, nhưng cũng tăng số backend và memory pressure trên PostgreSQL.

### 21.2. Baseline

Lưu pool active/idle/waiting, acquisition latency, PostgreSQL numbackends, active sessions, CPU, memory và query latency.

### 21.3. Sau thay đổi

So sánh:

- Pool wait time.
- Số connection mở mới/giây.
- Backend count và active query count.
- CPU/context switching.
- Query p95/p99.
- Lock waits và database errors.
- Memory usage.

### 21.4. Diễn giải

Nếu pool wait giảm nhưng PostgreSQL CPU tăng mạnh và query latency xấu đi, pool có thể đã đẩy concurrency vượt khả năng xử lý. Không tối ưu pool bằng cách chỉ nhìn ứng dụng.

## 22. Ví dụ đối chiếu: thay đổi autovacuum

### 22.1. Giả thuyết

Điều chỉnh threshold/scale factor có thể giúp vacuum bắt đầu sớm hơn trên bảng có write churn.

### 22.2. Baseline

Lưu n_dead_tup estimates, relation size, last_autovacuum, vacuum runtime/progress, transaction rate, XID age, disk I/O và query latency.

### 22.3. Sau thay đổi

Theo dõi ít nhất đủ lâu để bảng trải qua chu kỳ workload tương ứng. So sánh dead tuple trend, vacuum frequency/runtime, I/O và XID age.

### 22.4. Diễn giải

Dead tuples giảm nhưng I/O và latency giờ cao điểm tăng có thể là trade-off. Nếu dead tuples không giảm, kiểm tra xmin horizon, long transactions và replication slots; tăng worker count không thể xóa tuple còn được snapshot giữ.

## 23. Dashboard baseline đề xuất

Một dashboard so sánh nên có các panels:

| Panel | Metrics | Phân loại |
| --- | --- | --- |
| Workload | requests/s, transactions/s, rows changed | Rate |
| Latency | p50/p95/p99, pool wait | Percentile/gauge |
| Errors | failed requests, SQLSTATE, rollbacks, timeouts | Rate/counter delta |
| Query cost | calls, total/mean execution, buffers, temp, WAL | Counter delta |
| Connections | active/idle/waiting, max utilization | Gauge |
| Locks | blocked sessions, wait duration, deadlocks | Gauge/rate |
| Vacuum | dead tuple estimates, autovacuum, XID age | Gauge/trend |
| WAL/checkpoint | wal_bytes/s, checkpoint duration, FPI | Rate/counter delta |
| I/O | read/write latency, IOPS, throughput, queue | Gauge/rate |
| Replication | send/write/flush/replay LSN, lag, sync state | Gauge/trend |
| Storage | pg_wal size, relation size, free disk | Gauge/trend |
| Configuration | settings diff, version, restart pending | Metadata |

### 23.1. Hiển thị pre/post cùng trục thời gian

Đánh dấu thời điểm change deployment bằng annotation. Có thể dùng hai đường hoặc vùng màu khác nhau cho pre/post. Đảm bảo scale và units giống nhau.

### 23.2. Hiển thị workload cùng latency

Một chart latency không có request rate có thể gây hiểu nhầm. Luôn hiển thị traffic volume và error rate cạnh latency.

### 23.3. Link từ tổng quan tới query

Dashboard database nên cho phép drill down vào top query fingerprints, wait events, relation stats và logs theo cùng time range.

### 23.4. Không tạo quá nhiều alert từ một lần đo

Baseline là dữ liệu để đặt alert threshold, nhưng threshold phải xét seasonality, noise và business impact. Dùng duration/persistence và multi-signal conditions khi phù hợp.

## 24. Quy trình baseline trước thay đổi

### Bước 1. Xác định change ID và mục tiêu

Ghi rõ thay đổi nào sẽ được áp dụng, lý do và outcome cần cải thiện.

### Bước 2. Chọn metric chính và guardrails

Chọn metric trực tiếp phản ánh mục tiêu cùng các chỉ số có thể bị ảnh hưởng.

### Bước 3. Chụp cấu hình và topology

Lưu version, pg_settings, role, replication topology, hardware/storage và application release.

### Bước 4. Chọn cửa sổ đại diện

Chọn thời gian bao phủ workload bình thường và peak cần bảo vệ. Ghi các batch/maintenance overlap.

### Bước 5. Chụp snapshot đầu/cuối

Lưu counters, gauges và query stats với timestamp. Đo OS/application metrics song song.

### Bước 6. Kiểm tra reset và sample quality

Xác minh stats_reset, server start time, extension reset và số request mẫu. Đánh dấu cửa sổ không hợp lệ nếu counters bị reset giữa chừng.

### Bước 7. Lưu baseline bất biến

Lưu raw snapshots và metadata ở nơi có retention/access control. Không chỉ lưu ảnh dashboard.

## 25. Quy trình đo sau thay đổi

### Bước 1. Ghi change completion time

Đánh dấu chính xác thời điểm setting/deployment có hiệu lực. Nếu cần restart, ghi thời gian bắt đầu/kết thúc restart.

### Bước 2. Tách warm-up và steady state

Đo riêng giai đoạn khởi động/cache warm-up nếu có. Chỉ so sánh steady state với baseline steady state.

### Bước 3. Giữ workload tương đương

Theo dõi request mix, concurrency và batch jobs. Nếu workload khác, chuẩn hóa hoặc chạy controlled load test.

### Bước 4. Thu thập cùng metric definitions

Dùng cùng SQL, labels, units và scrape intervals. Không đổi metric formula giữa pre và post.

### Bước 5. Tính delta, rate và normalized cost

Tính counter deltas, rate per second, per request/transaction và percentile từ cùng nguồn.

### Bước 6. Đánh giá guardrails

Kiểm tra errors, latency, storage, WAL, replication, vacuum, locks và correctness.

### Bước 7. Quyết định

Accept, tiếp tục quan sát hoặc rollback theo tiêu chí đã định trước. Ghi bằng chứng và lý do.

## 26. Rollback criteria và change decision

### 26.1. Định nghĩa trước khi deploy

Ví dụ minh họa:

- Rollback nếu application error rate vượt ngưỡng đã thống nhất trong 5 phút liên tục.
- Rollback nếu p95 latency tăng hơn 25% trong khi workload tương đương và không có external cause.
- Dừng rollout nếu replication lag vượt SLA hoặc disk headroom xuống dưới safety margin.
- Dừng nếu deadlocks, failed transactions hoặc data validation errors tăng bất thường.

Các ngưỡng này phải lấy từ SLA và baseline thật; không dùng các con số ví dụ như tiêu chuẩn chung.

### 26.2. Phân biệt warning và stop condition

Warning báo metric lệch baseline nhưng chưa cần rollback. Stop condition là điều kiện đủ nghiêm trọng để dừng rollout hoặc rollback. Ghi owner có quyền ra quyết định.

### 26.3. Rollback có thể có chi phí

Một index mới có thể drop được nhưng cần lock/maintenance; config có thể cần restart; schema migration có thể không reversible. Đánh giá rollback path trước change.

### 26.4. Không chờ hết cửa sổ đo nếu guardrail đã vượt

Nếu data correctness, availability hoặc storage safety bị đe dọa, dừng theo incident procedure. Baseline không phải lý do trì hoãn hành động bảo vệ hệ thống.

### 26.5. Lưu kết quả sau rollback

Thu thập metrics để xác minh hệ thống trở lại trạng thái ổn định. Ghi lại rollback duration và side effects.

## 27. Các nguyên nhân làm phép so sánh sai

| Vấn đề | Vì sao gây sai lệch | Cách xử lý |
| --- | --- | --- |
| Traffic khác nhau | Counters/latency phản ánh workload khác | Match hoặc normalize workload |
| Peak vs off-peak | Cache và concurrency khác | So cùng time-of-day |
| Stats reset | Delta âm hoặc nhỏ giả tạo | Kiểm tra reset timestamps |
| Server restart | Counter scope hoặc warm-up thay đổi | Tách restart/warm-up |
| Query fingerprint đổi | Không ghép đúng query | Lưu query text/version/user/db |
| Cache cold/warm | I/O và latency khác | Đo riêng cold/warm phases |
| Background jobs | Cạnh tranh CPU/I/O | Ghi nhận hoặc match batch schedule |
| Data volume đổi | Planner, cache và storage khác | Ghi table/index size và row counts |
| Config khác ngoài change | Không thể quy kết nguyên nhân | Lưu settings diff |
| Network/storage event | Tạo latency ngoài database | Ghép infrastructure telemetry |
| Sample quá nhỏ | Percentiles không ổn định | Tăng sample/window |
| Mean che tail | Một số query rất chậm bị ẩn | Dùng p95/p99 histogram |
| Counter tích lũy | Cửa sổ khác độ dài | Tính delta/rate |
| Nhiều thay đổi cùng lúc | Attribution không rõ | Tách changes hoặc dùng control |
| Dashboard aggregation | Average-of-averages sai | Aggregate từ raw counts/histograms |

## 28. Lưu trữ và quản lý baseline

### 28.1. Baseline cần versioning

Lưu baseline theo change ID, release, cluster và timestamp. Mỗi record cần chỉ ra source, metric query/version và measurement window.

### 28.2. Lưu raw data

Giữ raw snapshots hoặc time series export để có thể tính lại khi metric definition thay đổi. Ảnh dashboard chỉ là tài liệu trình bày.

### 28.3. Ghi metric dictionary

Mỗi metric cần có:

- Tên và định nghĩa.
- Unit.
- Counter/gauge/rate/percentile.
- Source view/system.
- Scrape interval.
- Reset semantics.
- Scope: cluster/database/query/host/application.
- Version availability.
- Owner.

### 28.4. Retention và access control

Baseline có thể chứa query samples, schema names và operational metadata. Áp dụng retention và quyền truy cập phù hợp. Không lưu secrets hoặc raw parameters nhạy cảm.

### 28.5. Không ghi đè baseline cũ

Khi baseline mới được chấp nhận, tạo version mới và liên kết với change đã tạo ra nó. Điều này giúp biết hệ thống đã thay đổi thế nào qua các releases.

## 29. Bài tập thực hành có đáp án

Các bài tập giả định bạn có một PostgreSQL lab hoặc staging. Không reset statistics hay thay cấu hình production chỉ để làm bài.

### Bài 1. Baseline là gì?

**Đáp án:** Tập hợp metrics và metadata đại diện cho trạng thái hệ thống trước một thay đổi, được thu thập theo điều kiện có thể so sánh.

### Bài 2. Vì sao cần metadata cùng metrics?

**Đáp án:** Để biết workload, version, cấu hình, topology và thời điểm nào tạo ra các số liệu.

### Bài 3. Counter khác gauge thế nào?

**Đáp án:** Counter tích lũy theo thời gian; gauge mô tả giá trị tại một thời điểm.

### Bài 4. Vì sao không so raw xact_commit trước/sau?

**Đáp án:** Đây là counter tích lũy; cần tính delta và chuẩn hóa theo thời gian/workload.

### Bài 5. Công thức rate của counter?

**Đáp án:** (counter_after - counter_before) chia cho elapsed seconds.

### Bài 6. p95 latency cho biết gì?

**Đáp án:** 95% requests có latency không vượt quá giá trị p95 trong cửa sổ đo.

### Bài 7. Mean latency có thay p95 không?

**Đáp án:** Không. Mean có thể che tail latency.

### Bài 8. pg_stat_database cung cấp metrics gì?

**Đáp án:** Transaction, block access, tuple activity, temp files, deadlocks và các counters theo database.

### Bài 9. stats_reset dùng để làm gì?

**Đáp án:** Cho biết thời điểm statistics được reset, giúp xác định counter scope.

### Bài 10. blks_read có nghĩa mọi block đều đọc từ disk vật lý?

**Đáp án:** Không. OS cache có thể phục vụ read sau khi PostgreSQL miss shared buffers.

### Bài 11. Cache hit ratio có đủ đánh giá performance?

**Đáp án:** Không. Cần query latency, I/O, workload và storage metrics.

### Bài 12. temp_bytes tăng có thể chỉ ra gì?

**Đáp án:** Sort/hash/materialization spill ra temporary files.

### Bài 13. pg_stat_statements dùng để làm gì?

**Đáp án:** Tổng hợp execution statistics theo query fingerprint.

### Bài 14. pg_stat_statements có p95 latency không?

**Đáp án:** Không. Dùng APM/tracing/histogram cho percentile.

### Bài 15. Vì sao tính mean riêng cửa sổ bằng delta?

**Đáp án:** mean_exec_time là trung bình tích lũy; delta total time chia delta calls cho cửa sổ hiện tại.

### Bài 16. Queryid có thể thay đổi không?

**Đáp án:** Có, theo version, query structure và normalization. Lưu query sample và metadata.

### Bài 17. View nào xem active queries và wait events?

**Đáp án:** pg_stat_activity.

### Bài 18. Vì sao idle in transaction quan trọng?

**Đáp án:** Nó có thể giữ snapshot, locks và vacuum horizon dù không chạy query.

### Bài 19. View nào xem locks?

**Đáp án:** pg_locks.

### Bài 20. pg_blocking_pids() giúp gì?

**Đáp án:** Xác định PID đang block một backend.

### Bài 21. View nào xem vacuum progress?

**Đáp án:** pg_stat_progress_vacuum.

### Bài 22. n_dead_tup có phải exact count?

**Đáp án:** Không. Đây là estimate từ statistics.

### Bài 23. Vì sao cần theo dõi XID age?

**Đáp án:** Để bảo đảm vacuum/freeze progress và tránh transaction ID wraparound.

### Bài 24. pg_stat_wal giúp gì?

**Đáp án:** Theo dõi WAL records, full-page images, bytes và một số WAL activity counters ở versions hỗ trợ.

### Bài 25. WAL bytes/request tăng có thể nghĩa gì?

**Đáp án:** Write amplification tăng hoặc workload mix thay đổi; cần đối chiếu transaction mix.

### Bài 26. pg_stat_io có từ version nào?

**Đáp án:** PostgreSQL 16 trở lên.

### Bài 27. pg_stat_io phân loại I/O theo gì?

**Đáp án:** Backend type, object và context, cùng các counters liên quan.

### Bài 28. track_io_timing làm gì?

**Đáp án:** Cho phép thu thập timing cho một số I/O operations; cần xem overhead và giữ setting nhất quán khi so sánh.

### Bài 29. pg_stat_replication xem ở đâu?

**Đáp án:** Trên primary, để xem các WAL senders/standbys kết nối trực tiếp.

### Bài 30. Receive LSN và replay LSN khác nhau thế nào?

**Đáp án:** Receive là WAL đã nhận; replay là WAL đã áp dụng trên standby.

### Bài 31. replay_lag có luôn là thời gian bắt kịp chính xác?

**Đáp án:** Không. Khi workload idle hoặc không có WAL mới, lag interval có thể stale; cần LSN và workload context.

### Bài 32. Vì sao phải lưu PostgreSQL version?

**Đáp án:** Views, columns và semantics thay đổi giữa major versions.

### Bài 33. pending_restart có ý nghĩa gì?

**Đáp án:** Setting có thay đổi nhưng cần restart mới có hiệu lực.

### Bài 34. Vì sao phải lưu source của pg_settings?

**Đáp án:** Để biết giá trị hiệu lực đến từ config file, role/database setting, command line hay nguồn khác.

### Bài 35. Vì sao phải match time-of-day?

**Đáp án:** Workload, cache và concurrency có thể khác nhau theo giờ/ngày.

### Bài 36. Vì sao cần warm-up window?

**Đáp án:** Cache và background initialization sau restart/deploy có thể làm số liệu ban đầu khác steady state.

### Bài 37. Một query nhanh hơn nhưng INSERT chậm hơn có thể là gì?

**Đáp án:** Trade-off, ví dụ thêm index giảm read cost nhưng tăng write cost.

### Bài 38. Vì sao không thay nhiều biến cùng lúc?

**Đáp án:** Khó xác định thay đổi nào tạo ra kết quả.

### Bài 39. Normalize per request dùng để làm gì?

**Đáp án:** So sánh chi phí tài nguyên trên một đơn vị workload khi request volume khác nhau.

### Bài 40. Vì sao không lấy average của các average?

**Đáp án:** Các cửa sổ có sample size khác nhau; cần aggregate từ raw counts/histograms hoặc weighted averages phù hợp.

### Bài 41. EXPLAIN ANALYZE có thực thi query không?

**Đáp án:** Có. Cần đánh giá side effects và chỉ chạy câu lệnh an toàn trong môi trường phù hợp.

### Bài 42. BUFFERS cho biết gì?

**Đáp án:** Shared/local/temp buffer activity của plan, không trực tiếp đo mọi physical device reads.

### Bài 43. Vì sao cần application p95 cùng database query time?

**Đáp án:** Application latency còn gồm pool wait, network, serialization và external dependencies.

### Bài 44. Vì sao cần ghi batch jobs?

**Đáp án:** Batch jobs có thể cạnh tranh CPU/I/O và làm baseline bị lệch nếu chỉ xuất hiện ở một cửa sổ.

### Bài 45. Control group giúp gì?

**Đáp án:** Giúp tách tác động của thay đổi khỏi seasonality/traffic changes khi có canary/control tương đương.

### Bài 46. Khi nào baseline post-change được dùng làm baseline mới?

**Đáp án:** Khi change đã được chấp nhận và hệ thống ổn định qua cửa sổ đại diện.

### Bài 47. Vì sao không reset statistics tùy tiện?

**Đáp án:** Làm mất trend và ảnh hưởng các consumers/dashboard khác; snapshot rồi tính delta an toàn hơn.

### Bài 48. Nếu counter sau nhỏ hơn trước thì làm gì?

**Đáp án:** Kiểm tra reset, restart, extension reset và identity; đánh dấu cửa sổ không so sánh được nếu cần.

### Bài 49. Rollback criteria cần được định nghĩa khi nào?

**Đáp án:** Trước khi triển khai thay đổi, dựa trên SLA và baseline.

### Bài 50. Error rate tăng nhưng p95 giảm có phải thành công?

**Đáp án:** Không thể kết luận; latency có thể giảm do requests lỗi nhanh hơn. Phải xem correctness và errors.

### Bài 51. Disk free giảm sau khi thêm index cần xem gì?

**Đáp án:** Index size, WAL, tablespace capacity, backup/storage headroom và write cost.

### Bài 52. Vì sao không thể kết luận từ một snapshot?

**Đáp án:** Snapshot không thể hiện trend, peak, rate hay workload variation.

### Bài 53. Baseline cần lưu raw data không?

**Đáp án:** Có. Raw snapshots/time series cho phép tính lại khi metric definition thay đổi.

### Bài 54. Metric dictionary nên có gì?

**Đáp án:** Definition, unit, type, source, scope, scrape interval, reset semantics và version availability.

### Bài 55. Vì sao cần đồng bộ clocks?

**Đáp án:** Để ghép PostgreSQL, application và infrastructure events đúng thời gian.

### Bài 56. Khi nào nên dùng load test cố định?

**Đáp án:** Khi production traffic không đủ ổn định hoặc cần cô lập tác động của một thay đổi.

### Bài 57. Một p99 từ 100 requests có đáng tin không?

**Đáp án:** Không ổn định; cần sample size đủ lớn và ghi số mẫu.

### Bài 58. Vì sao phải đo replication và WAL khi thay index?

**Đáp án:** Index build/write activity có thể làm WAL và replication lag tăng.

### Bài 59. Baseline có phải một ngưỡng alert cố định?

**Đáp án:** Không. Baseline là dữ liệu tham chiếu; alert cần thêm SLA, seasonality và persistence conditions.

### Bài 60. Lập checklist so sánh trước/sau thay đổi PostgreSQL

**Đáp án gợi ý:**

1. Ghi change ID, mục tiêu và giả thuyết.
2. Chọn primary metrics, guardrails và rollback thresholds.
3. Ghi version, topology, pg_settings và application release.
4. Chọn cửa sổ pre/post tương đương.
5. Chụp raw snapshots và metadata.
6. Ghi workload volume, mix, concurrency và batch jobs.
7. Kiểm tra stats_reset, restart và extension resets.
8. Tính delta, rate, per-request cost và percentile.
9. Đối chiếu query plans, query fingerprints, locks, vacuum, WAL, replication và OS metrics.
10. Quyết định accept/observe/rollback và lưu evidence thành baseline version mới.

## 30. Checklist production

| Kiểm tra | Điều cần bảo đảm |
| --- | --- |
| Change ID | Có liên kết với release/ticket |
| Hypothesis | Nêu outcome có thể đo |
| Primary metrics | Phản ánh trực tiếp mục tiêu |
| Guardrails | Bao phủ latency, errors, capacity và correctness |
| PostgreSQL version | Được ghi lại |
| Cluster identity | Không nhầm primary/standby hoặc môi trường |
| Topology | Replica, DCS, routing và storage được ghi |
| pg_settings | Giá trị runtime và pending_restart được lưu |
| Application release | Được ghi theo snapshot |
| Workload | Rate, mix, concurrency và batch jobs |
| Measurement window | Pre/post tương đương |
| Clock | UTC/offset và synchronized |
| Stats reset | Reset time được kiểm tra |
| Counter deltas | Tính từ hai snapshots hợp lệ |
| Rates | Chuẩn hóa theo elapsed time |
| Per-request cost | Dùng denominator phù hợp |
| Percentiles | Có sample size và nguồn histogram |
| pg_stat_database | Transactions, blocks, temp, deadlocks |
| pg_stat_statements | Query fingerprints và deltas |
| pg_stat_activity | Sessions, waits, long transactions |
| pg_locks | Blocking và deadlocks |
| Vacuum | Dead tuples, progress, XID age |
| WAL/checkpoint | Bytes, FPI và checkpoint activity |
| I/O | PostgreSQL và OS/storage metrics |
| Replication | LSN, lag, sync state |
| Application | p50/p95/p99, errors, pool waits |
| Query plans | Representative EXPLAIN evidence |
| Dashboard | Pre/post annotation và cùng units |
| Rollback | Threshold, owner và procedure |
| Evidence | Raw snapshots và logs được lưu |
| New baseline | Chỉ tạo sau khi change được chấp nhận |
| Data protection | Không lưu secrets/nhạy cảm không cần thiết |

## 31. Tổng kết

Baseline và đối chiếu trước/sau thay đổi là quy trình đo lường để biết một thay đổi PostgreSQL có tạo ra kết quả mong muốn hay không. Kết luận đáng tin cần kết hợp workload, database metrics, query behavior, infrastructure, cấu hình và correctness.

Những nguyên tắc quan trọng:

1. **Baseline phải có bối cảnh.** Lưu version, topology, workload, cấu hình và cửa sổ đo.
2. **Phân biệt counter, gauge, rate và percentile.** Mỗi loại cần cách so sánh riêng.
3. **Dùng delta cho counter tích lũy.** Kiểm tra reset/restart trước khi tính.
4. **Match workload trước/sau.** So sánh cùng time-of-day, traffic mix và concurrency hoặc chuẩn hóa phù hợp.
5. **Theo dõi cả primary outcomes và guardrails.** Latency tốt hơn không đủ nếu errors, WAL hoặc storage xấu đi.
6. **pg_stat_database cho góc nhìn database.** Kết hợp pg_stat_statements để tìm query fingerprint.
7. **Application metrics vẫn cần thiết.** PostgreSQL không nhìn thấy toàn bộ pool wait và end-to-end latency.
8. **Cache hit ratio không phải disk I/O ratio.** Đọc cùng OS/storage metrics.
9. **Theo dõi locks, vacuum, WAL và replication.** Thay đổi đọc có thể ảnh hưởng writes và HA.
10. **EXPLAIN ANALYZE thực thi query.** Chỉ dùng với câu lệnh an toàn và môi trường phù hợp.
11. **Không reset stats tùy tiện.** Chụp snapshot rồi tính delta để giữ lịch sử.
12. **Một snapshot không phải baseline.** Dùng nhiều cửa sổ đại diện và sample đủ lớn.
13. **Đặt rollback criteria trước deploy.** Không đợi hết cửa sổ đo khi guardrail quan trọng bị vượt.
14. **Lưu raw evidence và metric dictionary.** Có thể tái tính và giải thích kết quả về sau.
15. **Chỉ cập nhật baseline mới sau khi chấp nhận change.** Giữ lịch sử để truy vết.

Mô hình quyết định:

```text
Mục tiêu thay đổi đo được?
          |
          v
Baseline có workload tương đương?
          |
          v
Stats và snapshots hợp lệ?
          |
          v
Primary outcome cải thiện?
          |
          v
Guardrails và correctness đạt?
       /              \
      Có               Không
      |                  |
      v                  v
Accept/observe        Roll back hoặc
      |               điều tra thêm
      v
Lưu post-change làm baseline mới
```

**Câu hỏi review cuối cùng:** “Nếu một thay đổi index làm query p95 giảm một nửa nhưng WAL, write latency và disk usage tăng, chúng ta có đủ baseline để định lượng trade-off không? Số liệu trước/sau có cùng workload, cùng metric definitions và cùng thời lượng không? Nếu statistics đã reset giữa hai snapshot, chúng ta có nhận ra phép so sánh không còn hợp lệ không?” Một quy trình baseline tốt phải trả lời được các câu hỏi đó bằng raw metrics, metadata và tiêu chí quyết định đã thống nhất trước thay đổi.

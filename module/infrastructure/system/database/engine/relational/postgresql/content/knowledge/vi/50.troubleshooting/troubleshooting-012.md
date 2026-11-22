# Thu thập bằng chứng, giảm tác động và xác minh sau xử lý sự cố PostgreSQL

Khi PostgreSQL gặp sự cố, áp lực lớn nhất thường là khôi phục dịch vụ càng sớm càng tốt. Tuy nhiên, một hành động vội vàng như restart server, terminate hàng loạt sessions, xóa WAL files hoặc failover không đúng quy trình có thể làm mất bằng chứng, kéo dài downtime hoặc biến một sự cố có thể phục hồi thành mất dữ liệu.

Một quy trình xử lý sự cố đáng tin cậy cần ba hoạt động nối tiếp nhau: **thu thập bằng chứng**, **giảm tác động**, và **xác minh sau xử lý**. Bằng chứng cho biết điều gì đang xảy ra và giúp chọn hành động phù hợp. Giảm tác động nhằm khôi phục khả năng phục vụ trong giới hạn RPO/RTO và tránh làm hỏng thêm dữ liệu. Xác minh chứng minh database, ứng dụng, replication, backup và các workload quan trọng đã trở lại trạng thái mong muốn.

Bài học thuộc chương **Xử lý sự cố** của module *Database Engine Relational PostgreSQL*. Nội dung trình bày cách tổ chức incident response, lưu timeline và trạng thái ban đầu, dùng PostgreSQL catalogs/statistics cùng OS/container telemetry, xử lý các tình huống phổ biến, kiểm soát hành động có rủi ro, kiểm tra dữ liệu và dịch vụ sau mitigation, rồi chuyển kết quả thành cải tiến vận hành.

> **Nguyên tắc:** Trước khi thay đổi trạng thái hệ thống, hãy lưu lại những bằng chứng có thể biến mất sau hành động đó. Chọn mitigation nhỏ nhất có thể giảm impact, ghi rõ điều kiện dừng/rollback, rồi xác minh bằng metrics và dữ liệu độc lập.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt symptom, impact, cause, mitigation và recovery.
2. Tổ chức incident response với severity, owner, timeline và decision log.
3. Thu thập bằng chứng PostgreSQL trước khi restart, cancel query hoặc failover.
4. Dùng pg_stat_activity, pg_locks, pg_blocking_pids và các statistics views.
5. Kiểm tra connections, long-running transactions, lock waits và query activity.
6. Thu thập WAL, replication, archiver, slot và vacuum evidence.
7. Kết hợp database metrics với OS, storage, container và Kubernetes events.
8. Bảo vệ logs, query samples, configuration và timestamps mà không làm lộ secrets.
9. Chọn mitigation có phạm vi nhỏ và có thể đảo ngược.
10. Xử lý connection exhaustion, lock contention và slow queries.
11. Xử lý disk pressure, WAL growth, replication lag và autovacuum problems.
12. Xử lý startup failure, crash recovery, backup failure và failover.
13. Biết khi nào cần dừng thao tác và chuyển sang recovery/DR procedure.
14. Xác minh service health, data integrity, replicas và backup sau xử lý.
15. Xây dựng incident report, root cause analysis và follow-up actions.

## 2. Phân biệt symptom, impact, cause và recovery

Trong incident, những khái niệm này dễ bị trộn lẫn:

- **Symptom:** điều quan sát được, ví dụ query timeout, connection refused hoặc replica lag.
- **Impact:** điều người dùng/hệ thống thực sự chịu, ví dụ checkout thất bại, dữ liệu chưa đồng bộ hoặc API p99 vượt SLO.
- **Cause:** cơ chế gây ra symptom, ví dụ lock queue, storage latency, connection leak hoặc một release thay đổi query plan.
- **Mitigation:** hành động làm giảm impact ngay lúc incident, ví dụ giảm traffic, cancel một query được xác định là runaway hoặc tăng capacity volume.
- **Recovery:** đưa hệ thống về trạng thái vận hành ổn định, bao gồm dữ liệu, replicas, backup và downstream consumers.

Một symptom có thể có nhiều causes. Ví dụ connection timeout có thể đến từ pooler hết connections, PostgreSQL hết slots, network failure, DNS hoặc server đang recovery. Không chọn mitigation chỉ dựa trên một symptom.

### 2.1. Phân loại theo impact

Đánh giá:
- Bao nhiêu users, tenants hoặc services bị ảnh hưởng?
- Read, write hay cả hai bị gián đoạn?
- Có transaction đã commit nhưng chưa replicate/archive không?
- Có nguy cơ mất dữ liệu hoặc duplicate processing không?
- Sự cố có lan sang các databases/regions khác không?
- Có vượt RPO, RTO hoặc availability SLO không?
- Có ảnh hưởng tới backup, restore hoặc failover capability không?

### 2.2. Phân biệt service degradation và data integrity incident

Database có thể vẫn accept connections nhưng trả kết quả sai, ghi thiếu rows hoặc commit trùng. Khi có nghi ngờ data integrity, không chỉ đo availability. Cần giữ lại transaction IDs, request IDs, keys và evidence để reconciliation.

### 2.3. Severity phải dựa trên tác động

Severity không nên chỉ dựa vào CPU 100% hoặc một alert đỏ. Một spike CPU ngắn có thể không gây impact; một query chậm trên critical workflow có thể làm mất doanh thu dù CPU thấp. Dùng SLO và business impact để phân loại.

## 3. Quy trình incident response tổng thể

Một quy trình tham khảo:

```text
DETECT
  Alert / report / SLO breach
       |
       v
ASSESS
  Scope, severity, user impact, data risk
       |
       v
PRESERVE EVIDENCE
  Timeline, logs, sessions, locks, WAL,
  replication, storage, config and versions
       |
       v
MITIGATE
  Smallest safe action with an owner
       |
       v
VERIFY
  Database + application + data + replicas
       |
       v
STABILIZE
  Observe through a representative workload window
       |
       v
REVIEW
  Root cause, prevention, runbooks and owners
```

### 3.1. Assign incident roles

Tùy quy mô tổ chức, có thể phân vai:
- Incident lead: điều phối, ưu tiên và quyết định.
- Database operator: thu thập evidence và thực hiện database actions.
- Application owner: kiểm tra release, traffic và request behavior.
- Infrastructure/storage owner: kiểm tra host, disk, network và cloud volumes.
- Communications owner: cập nhật trạng thái tới stakeholders.

Một người có thể đảm nhiệm nhiều vai trò trong incident nhỏ, nhưng cần xác định ai đang chịu trách nhiệm cho từng quyết định.

### 3.2. Ghi timeline ngay từ đầu

Ghi thời điểm:
- Alert đầu tiên.
- User impact bắt đầu.
- Deployment/configuration change gần nhất.
- Các triệu chứng mới xuất hiện.
- Mỗi mitigation được thực hiện.
- Database/replica recovery.
- Service được mở traffic lại.
- Incident được đóng.

Dùng timestamp có timezone rõ ràng, tốt nhất lưu UTC cùng timezone hiển thị cho người vận hành. Đồng bộ clock giữa database, application, hosts và monitoring.

### 3.3. Giữ một decision log

Mỗi hành động quan trọng nên ghi:
- Giả thuyết đang kiểm tra.
- Evidence hỗ trợ.
- Người thực hiện/duyệt.
- Phạm vi tác động.
- Kết quả quan sát.
- Điều kiện rollback hoặc bước tiếp theo.

Điều này tránh việc nhiều operator thực hiện các thay đổi trái ngược trong cùng incident.

## 4. Thu thập bằng chứng trước khi thay đổi trạng thái

Một số bằng chứng biến mất khi:
- Restart PostgreSQL/container/host.
- Terminate backend sessions.
- Cancel query.
- Failover/promote standby.
- Reset statistics.
- Rotate hoặc truncate logs.
- Thay đổi configuration.
- Xóa/replace volume.
- Chạy maintenance commands làm thay đổi state.

Vì vậy, nếu hệ thống còn đủ ổn định, thu thập snapshot ban đầu trước mitigation.

### 4.1. Evidence tối thiểu

Tùy incident, ghi lại:
- Ngày giờ, timezone và incident ID.
- PostgreSQL version và image/package digest.
- Database, cluster, node và role (primary/standby).
- application_name, client address và deployment version.
- Relevant settings từ pg_settings.
- Active sessions và wait events.
- Blocking/blocker PIDs.
- Long transactions và prepared transactions nếu có.
- Replication state, slots và WAL archive status.
- Database/table sizes và filesystem capacity.
- CPU, memory, I/O, network và container events.
- PostgreSQL/application logs.
- Deployment/configuration changes.
- Backup status và restore point gần nhất.

### 4.2. Ưu tiên read-only diagnostics

Các truy vấn catalog/statistics thường là điểm bắt đầu ít tác động. Dù vậy, chúng vẫn tiêu tốn connections/CPU và có thể đọc thông tin nhạy cảm. Chạy với role được cấp quyền phù hợp, giới hạn output và tránh polling quá dày.

### 4.3. Chụp nhiều snapshot theo thời gian

Một snapshot chỉ cho biết trạng thái tại một thời điểm. Nếu incident kéo dài, thu thập lại theo chu kỳ hợp lý để thấy:
- Waits tăng hay giảm.
- PIDs nào tồn tại lâu.
- Replication lag có tiếp tục tăng.
- WAL generation có vượt tốc độ replay.
- Disk usage có tăng liên tục.
- Mitigation có cải thiện metrics hay không.

Không chạy query nặng liên tục chỉ để có nhiều samples.

### 4.4. Không reset statistics khi chưa lưu snapshot

Các hàm reset statistics như pg_stat_reset() làm mất counters hữu ích cho điều tra. Trước khi reset, export số liệu hiện tại và ghi thời điểm. Trong incident, thường nên giữ counters để so sánh.

## 5. Xác nhận database identity, version và role

Bắt đầu bằng việc xác định chính xác server mà operator đang kết nối.

```sql
SELECT
    current_database() AS database_name,
    current_user AS database_user,
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port,
    pg_backend_pid() AS backend_pid,
    version() AS server_version,
    pg_is_in_recovery() AS is_standby;
```

### 5.1. Vì sao cần xác nhận endpoint?

Pooler, proxy, DNS và failover endpoint có thể chuyển connection tới node khác. Operator có thể nghĩ mình đang kiểm tra primary nhưng thực tế đang kết nối standby hoặc cluster khác.

### 5.2. Xác định recovery state

pg_is_in_recovery() trả true trên standby đang ở recovery. Trước các thao tác write hoặc failover, xác định role bằng cơ chế HA đang sử dụng, không chỉ dựa vào hostname.

### 5.3. Thu thập settings liên quan

```sql
SELECT
    name,
    setting,
    unit,
    source,
    pending_restart
FROM pg_settings
WHERE name IN (
    'max_connections',
    'shared_buffers',
    'work_mem',
    'maintenance_work_mem',
    'statement_timeout',
    'lock_timeout',
    'idle_in_transaction_session_timeout',
    'shared_preload_libraries',
    'wal_level',
    'max_wal_size',
    'archive_mode',
    'synchronous_commit'
)
ORDER BY name;
```

Settings và khả năng xuất hiện phụ thuộc PostgreSQL version. Chỉ lấy những settings liên quan incident; không cần dump mọi setting ra kênh chat công khai.

### 5.4. Ghi lại configuration source

pg_settings.source giúp nhận diện nguồn của setting. Có thể dùng pg_file_settings để xem nội dung/các lỗi parse của config files nếu role có quyền phù hợp. Redact secrets và connection strings trước khi lưu hoặc chia sẻ.

## 6. Thu thập session và query activity

pg_stat_activity là điểm bắt đầu để xem các server processes và client sessions.

```sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query_start,
    clock_timestamp() - query_start AS query_age,
    clock_timestamp() - xact_start AS transaction_age,
    left(query, 1000) AS query_sample
FROM pg_stat_activity
WHERE pid <> pg_backend_pid()
ORDER BY xact_start NULLS LAST, query_start NULLS LAST;
```

### 6.1. Hiểu state

Các state thường gặp:
- active: backend đang thực thi query.
- idle: đang chờ command tiếp theo.
- idle in transaction: transaction còn mở nhưng không chạy query.
- idle in transaction (aborted): transaction đã lỗi nhưng chưa rollback/đóng.
- fastpath function call: backend thực hiện fast-path function call.

Một session idle không nhất thiết là lỗi. idle in transaction kéo dài có thể giữ locks và snapshot, cản vacuum.

### 6.2. Hiểu wait_event_type và wait_event

Nếu backend active nhưng có wait event, thời gian có thể đang nằm ở lock, I/O, client, IPC hoặc một wait category khác. active không đồng nghĩa CPU đang chạy.

Các wait event names và categories có thể thay đổi theo major version. Dùng catalog pg_wait_events nếu có và đối chiếu đúng phiên bản.

### 6.3. Không coi query text là đầy đủ bằng chứng

Query text có thể bị truncate theo track_activity_query_size, có thể chứa literal nhạy cảm hoặc không cho thấy prepared statement parameters. Kết hợp query ID, application logs và trace/request IDs khi cần.

### 6.4. Phân biệt query age và transaction age

Query có thể vừa bắt đầu trong một transaction mở từ lâu. Transaction age quan trọng vì snapshot/locks có thể được giữ qua nhiều statements. Đừng chỉ sort theo query_start.

### 6.5. Application name

Đặt application_name theo service/worker/version để phân biệt traffic. Nếu mọi clients dùng cùng tên hoặc để trống, điều tra connection ownership khó hơn.

## 7. Tìm blocking sessions và lock queues

Lock contention có thể làm nhiều requests xếp hàng dù chỉ một transaction giữ lock.

### 7.1. Dùng pg_blocking_pids

```sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.application_name AS blocked_app,
    blocked.state AS blocked_state,
    blocked.wait_event_type,
    blocked.wait_event,
    clock_timestamp() - blocked.query_start AS blocked_query_age,
    blocker.pid AS blocker_pid,
    blocker.application_name AS blocker_app,
    blocker.state AS blocker_state,
    blocker.xact_start AS blocker_xact_start,
    left(blocker.query, 1000) AS blocker_query
FROM pg_stat_activity AS blocked
CROSS JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) AS p(blocker_pid)
JOIN pg_stat_activity AS blocker
    ON blocker.pid = p.blocker_pid
ORDER BY blocked.query_start;
```

### 7.2. Tìm blocker gốc

Blocking chain có thể nhiều tầng. Một backend đang bị block cũng có thể đang block backend khác. Tìm session ở đầu chuỗi đang giữ lock cần thiết, không chỉ xử lý PID đầu tiên thấy trong alert.

### 7.3. Kiểm tra transaction mở lâu

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    clock_timestamp() - xact_start AS xact_age,
    backend_xid,
    backend_xmin,
    wait_event_type,
    wait_event,
    left(query, 1000) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

### 7.4. Kiểm tra lock details

```sql
SELECT
    l.pid,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation_name,
    l.transactionid,
    a.application_name,
    a.state,
    a.xact_start,
    left(a.query, 500) AS query_sample
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a
    ON a.pid = l.pid
ORDER BY l.granted, l.pid;
```

relation::regclass có thể không resolve thành tên relation cho mọi lock type. Transaction, virtual transaction và object locks có fields khác nhau; giữ locktype và các identifiers khi phân tích.

### 7.5. Kiểm tra DDL đang chờ

Một DDL chờ AccessExclusiveLock có thể tạo queue phía sau nó. Nếu query mới bắt đầu chờ cùng relation, user impact có thể lan nhanh dù DDL chưa lấy được lock. Ghi lại waiter/blocker chain trước khi cancel migration.

## 8. Kiểm tra connection capacity

Khi app báo connection timeout, xác định pooler hay PostgreSQL đang cạn capacity.

```sql
SELECT
    datname,
    usename,
    application_name,
    state,
    count(*) AS connections
FROM pg_stat_activity
GROUP BY datname, usename, application_name, state
ORDER BY connections DESC;
```

Tổng connections so với configured limit:

```sql
SELECT
    count(*) AS current_connections,
    current_setting('max_connections')::integer AS max_connections
FROM pg_stat_activity;
```

### 8.1. Phân biệt server slots và application pool

Kiểm tra:
- Application pool queue và pool exhaustion.
- Pooler client/server connections.
- PostgreSQL backend count.
- Reserved slots và role limits.
- Background workers/replication connections.
- Connection churn/reconnect storm.

Một app pool có thể hết connections dù PostgreSQL còn slots; ngược lại PostgreSQL có thể hết slots trong khi app pool vẫn cố mở thêm.

### 8.2. Idle in transaction

Các sessions này có thể giữ locks, snapshot và ngăn vacuum cleanup. Thu thập PID, app, transaction age và owner trước khi xử lý.

### 8.3. Không tăng max_connections ngay lập tức

Tăng max_connections làm tăng potential backend/resource usage. Nếu nguyên nhân là connection leak hoặc query queue, tăng limit có thể đẩy server vào memory pressure và làm sự cố nặng hơn.

### 8.4. Xác định reserved capacity

Một số PostgreSQL versions có reserved connection settings ngoài max_connections. Kiểm tra cấu hình và privileges của emergency operator trước khi incident xảy ra.

## 9. Thu thập WAL, replication và archive evidence

Khi replica lag hoặc recovery chậm, xác định bottleneck nằm ở primary send, network, standby write hay replay.

### 9.1. Primary: pg_stat_replication

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
    replay_lag
FROM pg_stat_replication
ORDER BY application_name;
```

Fields và lag semantics có thể khác theo version. Lag columns có thể trở thành NULL khi không có WAL activity gần đây; không diễn giải NULL đơn giản là zero lag.

### 9.2. Standby: pg_stat_wal_receiver

```sql
SELECT
    status,
    receive_start_lsn,
    written_lsn,
    flushed_lsn,
    received_tli,
    last_msg_send_time,
    last_msg_receipt_time,
    latest_end_lsn,
    latest_end_time,
    slot_name,
    sender_host,
    sender_port
FROM pg_stat_wal_receiver;
```

View có thể không có row nếu server không chạy WAL receiver hoặc đang ở trạng thái khác. So sánh timestamps với primary và network metrics.

### 9.3. Replication slots

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    temporary
FROM pg_replication_slots
ORDER BY slot_name;
```

Một inactive slot có thể giữ WAL và làm filesystem đầy. Không drop slot chỉ để giải phóng disk trước khi xác định consumer và khả năng resync/reseed của nó. Một số cột khác như wal_status/safe_wal_size phụ thuộc PostgreSQL version.

### 9.4. Archive status

```sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
```

Nếu archive failures tăng, kiểm tra archive destination, permissions, credentials, network và archive command logs. WAL archive backlog có thể ảnh hưởng PITR readiness và storage.

### 9.5. Xác định WAL pressure

Thu thập:
- WAL directory size.
- pg_wal_lsn_diff giữa LSNs phù hợp.
- Slot restart LSN.
- Archive success/failure.
- Replica receive/write/flush/replay progress.
- Checkpoint/WAL generation.
- Disk free space.

Không dùng pg_wal directory size đơn lẻ để kết luận replica lag; retention và checkpoint behavior cũng ảnh hưởng dung lượng.

## 10. Thu thập vacuum, bloat và table health evidence

Autovacuum bị chặn hoặc không theo kịp có thể gây table/index bloat, transaction ID pressure và disk growth.

### 10.1. Autovacuum activity

```sql
SELECT
    pid,
    datname,
    relid::regclass AS relation_name,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed,
    index_vacuum_count,
    num_dead_tuples,
    max_dead_tuples
FROM pg_stat_progress_vacuum
ORDER BY datname, relation_name;
```

View và columns có thể khác giữa PostgreSQL versions; kiểm tra progress views của server hiện tại.

### 10.2. Dead tuples và vacuum timestamps

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
```

Các tuple counts là estimates, không phải exact counts. Dùng để xác định xu hướng và đối tượng cần điều tra.

### 10.3. Long-running snapshots

Transaction age, backend_xmin, replication slots và standby feedback có thể giữ lại xmin horizon. Xác định consumer giữ horizon trước khi thay đổi vacuum settings.

### 10.4. Transaction ID age

Theo dõi database/table age để phát hiện wraparound risk. Khi có cảnh báo anti-wraparound autovacuum, ưu tiên xử lý theo PostgreSQL runbook và không tắt autovacuum một cách tùy tiện.

### 10.5. Không chạy VACUUM FULL như phản xạ

VACUUM FULL cần lock mạnh và rewrite table, có thể cần disk space lớn. Trong incident, nó thường làm tăng downtime/impact. Xác định root cause, blockers và phương án maintenance trước.

## 11. Thu thập query performance evidence

Khi một endpoint chậm, xác định query fingerprint và thay đổi gần nhất.

### 11.1. pg_stat_statements

Nếu đã cài và cấu hình:

```sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_written,
    left(query, 1000) AS query_sample
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

Columns thay đổi theo extension version. Counters tích lũy từ lần reset gần nhất, nên lưu snapshot và tính delta theo incident window.

### 11.2. EXPLAIN ANALYZE có tác động

EXPLAIN ANALYZE thực thi query thật. Query SELECT có thể vẫn tiêu thụ CPU/I/O; UPDATE/DELETE sẽ thay đổi dữ liệu. Dùng bản clone/staging hoặc chọn query an toàn và giới hạn cẩn thận trong production.

### 11.3. Thu plan trước khi thay indexes/settings

Lưu plan, settings, parameters và statistics context trước khi đổi index, work_mem, planner settings hoặc query. Sau thay đổi, so sánh plan và actual workload.

### 11.4. Không ép planner bằng settings toàn cục để chữa một query

Các settings như enable_seqscan hoặc enable_nestloop có thể hữu ích cho diagnosis trong session thử nghiệm, nhưng thay global config để ép một plan thường tạo regression cho workload khác.

### 11.5. Correlate query với application traces

Dùng request ID, trace ID, application_name, query ID và timestamp để liên kết query với endpoint/version. Tránh ghi bind values nhạy cảm vào incident report.

## 12. Kết hợp PostgreSQL evidence với OS và platform telemetry

Database statistics cho thấy backend đang làm gì; OS/platform metrics cho thấy tài nguyên bên dưới có đáp ứng không.

### 12.1. CPU và run queue

Linux:
```bash
uptime
vmstat 1 5
top -b -n 1
```

CPU cao có thể do query, autovacuum, compression, encryption, background workers hoặc process khác trên host. Xác định PID/process/container trước khi kết luận.

### 12.2. Memory và OOM

```bash
free -h
cat /proc/meminfo
dmesg -T | tail -n 100
```

Container/Kubernetes có thể có memory limit thấp hơn host memory. Kiểm tra cgroup memory metrics, OOMKilled events và container limits.

### 12.3. Disk và inode pressure

```bash
df -h
df -i
lsblk
du -xhd1 /var/lib/postgresql
```

du trên data directory lớn có thể tạo I/O đáng kể; giới hạn scope và dùng khi phù hợp. Một filesystem đầy có thể khác filesystem chứa PGDATA, pg_wal, temp hoặc tablespaces.

### 12.4. Storage latency

```bash
iostat -xz 1 5
```

Chú ý await/latency, queue depth và utilization theo device. Tên metric có thể khác theo OS/tool version.

### 12.5. Network

Kiểm tra packet loss, retransmits, connection resets, DNS resolution, firewall/security groups và throughput giữa primary, standby, pooler và application. Một database query chờ client/network không nhất thiết là server CPU bottleneck.

### 12.6. Container logs và events

Docker:
```bash
docker ps -a
docker inspect <container>
docker logs --since 30m <container>
```

Kubernetes:
```bash
kubectl get pods -o wide
kubectl describe pod <pod>
kubectl logs <pod> --since=30m
kubectl get events --sort-by=.lastTimestamp
```

Các commands có thể trả environment variables, mount paths, labels hoặc query text nhạy cảm. Redact trước khi chia sẻ.

### 12.7. Cloud storage events

Kiểm tra volume throttling, attach/detach events, burst balance/credits nếu provider có, IOPS limits và maintenance events. Không chỉ nhìn CPU của database instance.

## 13. Thu thập logs và giữ chain of evidence

Logs thường chứa thông tin quan trọng nhất về thứ tự xảy ra sự kiện.

### 13.1. PostgreSQL logs

Tìm:
- FATAL, PANIC, ERROR, WARNING.
- Checkpoint warnings/durations.
- Deadlock reports.
- Recovery/startup messages.
- WAL/archive errors.
- Autovacuum cancellations.
- Connection authentication failures.
- Out-of-memory/disk errors.
- Extension/background worker crashes.

### 13.2. Application logs

Thu thập SQLSTATE, endpoint, deployment version, retry count, connection pool metrics và request IDs. Tránh chỉ lưu message “database timeout” mà không có timeout phase.

### 13.3. Logs rotation

Ghi nhận file/log stream, timestamp range, rotation boundaries và retention. Copy/export logs theo cách không thay đổi file đang được PostgreSQL ghi.

### 13.4. Evidence integrity

Nếu incident cần audit:
- Lưu bản copy read-only.
- Ghi nguồn và timestamp thu thập.
- Tạo checksum cho artifacts nếu policy yêu cầu.
- Hạn chế quyền truy cập.
- Ghi lại redactions.
- Không chỉnh sửa bản gốc.

### 13.5. Data minimization

Query text, parameters, usernames, client IPs và logs có thể chứa PII, tokens hoặc secrets. Chỉ lưu phần cần thiết, redact theo policy và dùng kênh chia sẻ được phê duyệt.

## 14. Chọn mitigation: giảm impact trước

Mitigation tốt thường có các thuộc tính:
- Nhắm vào một workload/session/resource được xác định.
- Có phạm vi nhỏ.
- Có thể rollback.
- Không phá data integrity.
- Có metrics để đo hiệu quả.
- Có owner và thời hạn.
- Không che mất evidence quan trọng.

### 14.1. Ưu tiên traffic shaping

Có thể giảm impact bằng cách:
- Rate limit một endpoint/workload.
- Tạm dừng batch jobs không critical.
- Giảm concurrency ở worker.
- Giới hạn retry storm.
- Queue công việc để xử lý sau.
- Chuyển reads sang replicas nếu consistency policy cho phép.

### 14.2. Không làm tăng tải trong incident

Tránh chạy full table scans, full dumps, index builds hoặc diagnostic loops nặng trên primary đang quá tải nếu không cần thiết. Thu evidence có chọn lọc và dùng replica/clone khi phù hợp.

### 14.3. Chọn một mitigation tại một thời điểm

Nếu đồng thời restart, tăng connections, thay planner settings và terminate sessions, rất khó xác định thay đổi nào có hiệu quả hoặc gây regression. Thực hiện từng bước có quan sát, trừ trường hợp emergency procedure đã được định nghĩa.

### 14.4. Ghi rollback trigger

Ví dụ: nếu p95 không cải thiện sau một khoảng đo, error rate tăng hoặc replication lag vượt threshold, dừng rollout và quay về trạng thái trước. Định nghĩa threshold trước khi thực hiện.

## 15. Cancel query và terminate backend an toàn

PostgreSQL cung cấp các functions để yêu cầu hủy query hoặc kết thúc session.

### 15.1. Cancel query

```sql
SELECT pg_cancel_backend(12345);
```

Hàm yêu cầu cancel query hiện tại của backend. Session vẫn tồn tại; transaction đang lỗi có thể cần client rollback. Hàm trả boolean cho biết request cancel có được gửi hay không, không chứng minh mọi side effect đã được dọn xong.

### 15.2. Terminate session

```sql
SELECT pg_terminate_backend(12345);
```

Hàm yêu cầu kết thúc backend session. Active transaction sẽ rollback; rollback có thể cần thời gian và tài nguyên. Locks được giải phóng sau khi transaction/session cleanup hoàn tất.

### 15.3. Trước khi cancel/terminate

Xác nhận:
- PID thuộc database/cluster nào.
- Application/owner nào.
- Query và transaction age.
- Backend có phải replication, autovacuum, logical worker hay maintenance process không.
- Query có đang thực hiện business-critical work không.
- Retry có thể tạo duplicate side effects không.
- Có thể rate-limit source thay vì kill session không.

### 15.4. Không terminate hàng loạt theo state

Một batch terminate mọi idle hoặc mọi active sessions có thể ngắt healthy workloads. Chỉ xử lý PID đã xác định, có lý do và người chịu trách nhiệm.

### 15.5. Không kill OS process trực tiếp như cách đầu tiên

Dùng PostgreSQL cancellation/termination APIs khi phù hợp. Kill process ở OS level có thể bỏ qua graceful cleanup và làm crash/recovery. Chỉ dùng quy trình OS-level khi PostgreSQL control path không còn hoạt động và runbook đã quy định.

## 16. Xử lý connection exhaustion

Triệu chứng:
- App không lấy được connection.
- PostgreSQL báo too many connections.
- Pool wait time tăng.
- Số idle in transaction hoặc idle tăng bất thường.

Quy trình:
1. Thu snapshot connection counts theo app/user/state.
2. Kiểm tra pooler và application pool queues.
3. Xác định connection leak, retry storm hoặc rollout tạo quá nhiều pools.
4. Giảm incoming traffic/worker concurrency.
5. Khắc phục pool sizing hoặc connection lifecycle.
6. Chỉ terminate sessions đã xác định là orphan/stale và có approval.
7. Xác minh free slots, pool wait time và request error rate.

### 16.1. Pool sizing

Tổng connections của mọi replicas/workers phải tính chung. Ví dụ 20 pods × pool size 30 có thể tạo 600 server connections trước khi tính admin, monitoring và replication.

### 16.2. Idle session không nhất thiết cần kill

Pooler có thể giữ idle connections để tái sử dụng. Đánh giá theo pool policy, idle age và capacity. Ưu tiên điều chỉnh pool/traffic ở application layer.

### 16.3. Emergency access

Duy trì một emergency role/process với quyền và connection capacity phù hợp để operator có thể chẩn đoán khi application đã chiếm hết slots. Kiểm tra cơ chế reserved connections theo PostgreSQL version.

## 17. Xử lý lock contention và deadlocks

Triệu chứng:
- Query wait event là Lock.
- Nhiều requests cùng chờ một relation/transaction.
- DDL migration không lấy được lock.
- Deadlock errors tăng.

Quy trình:
1. Capture blocking tree và pg_locks.
2. Xác định blocker gốc, transaction age và owner.
3. Kiểm tra deployment/migration/batch job mới.
4. Giảm traffic gây thêm waiter nếu cần.
5. Liên hệ owner để commit/rollback transaction nếu có thể.
6. Cancel query hoặc terminate đúng session khi đã đánh giá.
7. Kiểm tra lock queue tan và request latency phục hồi.

### 17.1. Long transaction

Transaction mở lâu có thể giữ row/table locks và snapshot. Một session idle in transaction thường cần điều tra application code/connection pool.

### 17.2. Deadlock

Deadlock được PostgreSQL phát hiện và abort một transaction. Kiểm tra deadlock logs để xác định lock order. Mitigation dài hạn thường là consistent lock ordering, transaction ngắn và retry logic cho SQLSTATE 40P01.

### 17.3. DDL lock queue

Nếu DDL đang chờ lock mạnh, cân nhắc hủy migration đang chờ trước khi nó gây queue dài. Sau đó xử lý blocker và lên lịch retry với lock_timeout phù hợp.

### 17.4. Không chạy VACUUM FULL hoặc REINDEX nặng giữa lock incident

Các thao tác này có thể cần locks/tài nguyên lớn. Thu evidence, ổn định traffic và lên maintenance plan riêng.

## 18. Xử lý slow queries và CPU saturation

Triệu chứng:
- Query latency tăng.
- CPU cao.
- Throughput giảm.
- Pool queue tăng do connections bị giữ lâu.

Quy trình:
1. Xác định query fingerprints và application version.
2. Capture pg_stat_activity và pg_stat_statements.
3. Kiểm tra wait events để phân biệt CPU-bound, I/O-bound và lock-bound.
4. So sánh query plan với baseline.
5. Kiểm tra statistics, data skew và index changes.
6. Giảm hoặc tạm dừng workload không critical.
7. Rollback release/configuration đã gây regression nếu evidence hỗ trợ.
8. Xác minh latency và resource usage sau mitigation.

### 18.1. Không chạy EXPLAIN ANALYZE bừa bãi

Query có thể tiêu thụ nhiều CPU/I/O hoặc mutate data. Dùng query representative trên clone/staging khi có thể.

### 18.2. Không tạo index trong incident nếu chưa đánh giá

Index build có thể tiêu thụ I/O/WAL và cạnh tranh storage với workload đang bị ảnh hưởng. Nếu index là mitigation, đánh giá CREATE INDEX CONCURRENTLY, disk headroom, lock và rollback trước.

### 18.3. Query cancellation

Nếu một query runaway gây impact lớn, cân nhắc cancel query cụ thể sau khi lưu PID/query evidence và xác nhận retry semantics. Không terminate toàn bộ application pool.

### 18.4. Work_mem

Tăng work_mem có thể giảm spill cho query cụ thể nhưng được cấp theo operation/worker, không phải một lần cho toàn server. Tăng global setting trong incident có thể làm memory usage tăng mạnh khi concurrency cao. Nếu cần, thử ở session/workload scope có kiểm soát.

## 19. Xử lý disk full và storage pressure

Disk full có thể làm PostgreSQL không ghi WAL, temp files, relation updates hoặc logs.

Quy trình:
1. Xác định filesystem/volume thực sự đầy.
2. Kiểm tra PGDATA, pg_wal, tablespaces, temp paths và log mounts.
3. Thu df, inode usage, volume metrics và growth timeline.
4. Xác định nguyên nhân: WAL retention, archive failure, inactive replication slot, runaway temp files, logs, bloat hoặc growth bình thường.
5. Tăng volume capacity hoặc provisioned throughput nếu platform hỗ trợ.
6. Dọn logs/backups/temp artifacts theo retention và ownership policy.
7. Xử lý slot/archive/transaction cause bằng PostgreSQL-supported procedure.
8. Xác minh writes, checkpoints, archiving và replicas tiếp tục bình thường.

### 19.1. Tuyệt đối không xóa WAL files bằng shell

Không dùng rm để xóa files trong pg_wal. PostgreSQL cần WAL cho crash recovery, replication và archive. Xóa thủ công có thể làm cluster không thể khởi động hoặc gây mất dữ liệu.

### 19.2. Replication slots giữ WAL

Slot inactive có thể khiến WAL được giữ lại lâu. Xác định consumer và khả năng rebuild/reseed trước khi drop/recreate slot.

### 19.3. Temp files

Temp files có thể tăng do sort/hash spills hoặc query concurrency. Xác định query/session gây ra, giới hạn workload hoặc sửa query; không xóa file temp đang được process sử dụng.

### 19.4. Inodes và quota

Filesystem có thể hết inodes dù còn bytes; PVC quota có thể khác capacity hiển thị. Kiểm tra cả bytes, inodes và provider limits.

### 19.5. Không xóa relation files

Không xóa files trong base/, global/, pg_tblspc/ hoặc các directories PostgreSQL quản lý. Dùng SQL/maintenance procedures và backup/recovery tools.

## 20. Xử lý WAL archive failure và replication lag

### 20.1. Archive failure

Kiểm tra:
- Archive command exit status.
- Permissions/credentials.
- Network/DNS/TLS.
- Destination capacity.
- Object store throttling.
- Duplicate/collision behavior.
- Archive timeout và retry logs.

Nếu archive không chạy, WAL có thể tích tụ trên primary. Phục hồi archive path trước khi dọn bất kỳ files nào.

### 20.2. Replication lag

Phân biệt:
- Send lag: primary chưa gửi đủ WAL.
- Write lag: standby chưa ghi WAL nhận được.
- Flush lag: standby chưa flush WAL xuống storage.
- Replay lag: standby đã nhận/flush nhưng chưa replay.

Dùng LSNs và timestamps từ cả hai phía, network metrics và standby storage latency.

### 20.3. Standby replay chậm

Kiểm tra CPU/I/O trên standby, long-running queries, recovery conflicts, max_standby_streaming_delay, hot_standby_feedback và query workload. Không thay đổi conflict settings nếu chưa hiểu read availability và WAL retention trade-off.

### 20.4. Replication slot lag

Kiểm tra restart LSN và consumer progress. Một slot giữ WAL có thể đầy disk ngay cả khi standby khác vẫn khỏe.

### 20.5. Không promote standby chỉ vì lag

Promotion là quyết định HA/data-loss. Xác định primary còn sống không, fencing, replay position, synchronous commit policy và RPO trước khi promote.

## 21. Xử lý autovacuum không theo kịp

Triệu chứng:
- Dead tuples tăng.
- Table/index bloat.
- Transaction ID age cao.
- Query performance suy giảm.
- Disk usage tăng.

Quy trình:
1. Kiểm tra progress views và table stats.
2. Tìm long transactions, prepared transactions và xmin holders.
3. Kiểm tra replication slots/standby feedback.
4. Xác định table có write rate cao hoặc vacuum thresholds không phù hợp.
5. Đảm bảo đủ I/O và maintenance capacity.
6. Điều chỉnh per-table autovacuum settings sau khi đánh giá.
7. Theo dõi vacuum progress, dead tuples và transaction ID age.

### 21.1. Không disable autovacuum như mitigation mặc định

Tắt autovacuum có thể làm bloat và wraparound risk tăng. Nếu cần điều chỉnh, làm ở phạm vi table/setting cụ thể, có thời hạn và owner.

### 21.2. Freeze và wraparound

Anti-wraparound vacuum có thể được ưu tiên dù workload bị ảnh hưởng. Không kill process này theo phản xạ. Xác định database/table age và làm theo PostgreSQL recovery guidance.

### 21.3. Long-running transaction

Một transaction giữ snapshot cũ có thể ngăn vacuum loại bỏ dead tuples. Xử lý owner/transaction root cause trước khi tăng worker count một cách mù quáng.

## 22. Xử lý PostgreSQL không khởi động hoặc crash recovery

Khi server không accept connections:
1. Xác nhận process/container/node và endpoint.
2. Thu logs trước khi recreate/restart thêm lần nữa.
3. Kiểm tra volume attach, filesystem read-only, disk space và permissions.
4. Kiểm tra config parse errors, missing libraries/extensions và port conflicts.
5. Xác định startup state: crash recovery, standby recovery, archive recovery hay startup failure.
6. Kiểm tra WAL/control file errors trong logs.
7. Bảo toàn data directory và backup/snapshot.
8. Chọn recovery procedure dựa trên evidence.

### 22.1. Không xóa postmaster.pid tùy tiện

File này chứa metadata về server process. Xóa khi postmaster còn chạy có thể cho phép một server khác cố mở cùng data directory. Trước khi xử lý stale PID file, xác nhận không có process nào sử dụng cluster và theo đúng runbook.

### 22.2. Không chạy initdb trên data directory hiện hữu

initdb tạo cluster mới. Nếu chạy nhầm vào path/volume có dữ liệu, có thể làm mất hoặc ghi đè state. Xác nhận PG_VERSION, volume identity và backup trước mọi thao tác.

### 22.3. Không đổi major image để thử

Binary major version phải tương thích với data directory hoặc được nâng cấp bằng phương thức hỗ trợ. Nếu startup fail sau image update, giữ source volume và quay về đúng binary tương thích theo rollback plan; không chạy nhiều major binaries thử trên cùng data directory.

### 22.4. PANIC/corruption symptoms

Khi logs có PANIC, checksum errors hoặc I/O errors, tránh chạy các repair commands không hiểu rõ. Bảo toàn snapshot/backup, dừng writes nếu cần theo incident lead và chuyển sang recovery/corruption procedure.

## 23. Xử lý failover và split-brain risk

Failover có thể khôi phục availability nhưng sai trình tự có thể tạo hai primaries hoặc mất acknowledged transactions.

### 23.1. Trước promotion

Xác nhận:
- Primary cũ thực sự không thể tiếp tục ghi hoặc đã được fenced.
- Candidate standby có timeline/replay position phù hợp.
- Replication mode và synchronous commit guarantees.
- RPO chấp nhận được.
- HA controller state và lease/leader election.
- Application endpoint routing.

### 23.2. Fencing

Fencing ngăn primary cũ tiếp tục nhận writes sau khi standby mới được promote. Network partition có thể làm node cũ vẫn hoạt động dù operator không reach được. Không coi không ping được là bằng chứng node đã dừng.

### 23.3. Sau promotion

Kiểm tra node mới writable, application connections trỏ đúng endpoint, WAL timeline mới, replicas follow primary mới và old primary không thể tự động quay lại writable.

### 23.4. Rejoin old primary

Dùng quy trình rejoin/rewind/rebuild được hỗ trợ. Không chỉ khởi động lại old primary trên data directory cũ rồi cho nó nhận writes.

### 23.5. Ghi nhận RPO thực tế

Ghi LSN/timeline, last known commit/replication state và dữ liệu có thể bị mất. Truyền đạt rõ uncertainty thay vì tuyên bố zero data loss khi chưa có evidence.

## 24. Xử lý backup và restore failures

### 24.1. Backup job fail

Thu logs, exit code, duration, backup type, source node, target storage, WAL/archive state và free space. Kiểm tra credential/network/permissions và provider throttling.

### 24.2. Backup thành công không đồng nghĩa restore được

Backup completion chỉ chứng minh job đã hoàn tất theo tool. Restore test mới chứng minh artifacts, WAL chain, extension packages và procedures đủ để phục hồi.

### 24.3. Khi restore fail

Giữ nguyên backup source. Kiểm tra:
- Backup manifest/checksums.
- PostgreSQL major/version.
- Tablespaces.
- WAL continuity.
- Extension binaries.
- Encryption keys.
- Credentials.
- Target filesystem capacity/permissions.
- Recovery target time.

### 24.4. Không ghi đè source backup

Thử restore vào target directory/volume mới. Giữ source backup immutable theo retention policy cho tới khi restore validation hoàn tất.

## 25. Dùng timeout và cancellation có kiểm soát

Timeout là guardrail giúp giới hạn resource occupancy, nhưng thay đổi timeout giữa incident có thể tạo side effects.

### 25.1. lock_timeout

Giới hạn thời gian chờ lock. Có thể dùng SET LOCAL lock_timeout trong transaction/migration để DDL fail nhanh nếu không lấy được lock.

### 25.2. statement_timeout

Giới hạn thời gian statement chạy. Nếu set quá thấp toàn server, queries hợp lệ hoặc maintenance có thể bị cancel.

### 25.3. idle_in_transaction_session_timeout

Có thể bảo vệ khỏi sessions idle trong transaction kéo dài. Cần đánh giá application behavior và transaction boundaries trước khi bật rộng.

### 25.4. Client-side timeout

Application/pooler timeout có thể xảy ra trước server statement timeout. Khi client disconnect, query/server-side transaction behavior cần được kiểm tra. Timeout không tự động bảo đảm mọi request được rollback đúng như business cần.

### 25.5. Timeout change procedure

Ghi giá trị cũ, scope, thời hạn, expected behavior và rollback. Ưu tiên session/role/database scope nếu phù hợp thay vì thay global config trong incident.

## 26. Thay đổi configuration trong incident

Một số settings có thể reload; một số cần restart. Một số thay đổi có thể làm memory/CPU pressure tăng.

Trước khi đổi:
1. Thu giá trị hiện tại và source.
2. Kiểm tra setting context và pending_restart.
3. Đọc tác động đến tất cả workloads.
4. Thử scope nhỏ nếu có thể.
5. Ghi rollback value.
6. Theo dõi metrics ngay sau thay đổi.

Không thay nhiều settings cùng lúc. Nếu performance cải thiện, cần biết setting nào tạo khác biệt để có thể giữ hoặc revert có chủ đích.

## 27. Giảm tác động bằng application-level controls

Database incident thường cần phối hợp application layer.

### 27.1. Rate limiting

Giới hạn request tới endpoint gây query storm. Giữ capacity cho authentication, checkout hoặc workflow critical.

### 27.2. Circuit breaker

Nếu database hoặc downstream dependency đang quá tải, tạm ngừng request mới tới dependency và trả fallback/error có kiểm soát. Tránh retry liên tục làm tăng load.

### 27.3. Backoff và jitter

Retries cần exponential backoff, jitter và maximum attempts. Retry mọi SQLSTATE có thể gây duplicate writes hoặc khuếch đại incident.

### 27.4. Queue batch jobs

Tạm dừng hoặc giảm concurrency của analytics, imports, backfills và scheduled jobs không critical. Ghi backlog để xử lý sau khi service ổn định.

### 27.5. Read routing

Có thể chuyển read-only workload sang replica nếu consistency/freshness requirement cho phép. Không route reads yêu cầu read-after-write sang replica đang lag.

### 27.6. Feature flags

Tắt feature mới gây query cost cao hoặc rollout gây regression. Ghi flag state và tenant/traffic scope để tránh thay đổi ngoài ý muốn.

## 28. Xác minh ngay sau mitigation

Sau mỗi hành động, đo đúng metric liên quan đến giả thuyết ban đầu.

Ví dụ:
- Cancel blocker: lock wait count và blocked query age giảm?
- Rate limit: connection/pool queue và latency có giảm?
- Expand volume: filesystem free space có tăng và PostgreSQL có ghi được?
- Fix archive: pg_stat_archiver failures có ngừng tăng?
- Restore replication: replay LSN có tiến triển và lag có giảm?
- Rollback release: query plan/latency/error rate có trở lại baseline?

Không kết luận thành công chỉ vì alert biến mất. Alert có thể hết do monitoring reset hoặc workload ngừng gửi traffic.

## 29. Xác minh database health

Kiểm tra:
- PostgreSQL process đang chạy ổn định.
- Database connections hoạt động.
- Không còn startup/recovery errors mới.
- Critical settings/config đúng.
- Active sessions/waits ở mức bình thường.
- Lock queues đã tan.
- Long transactions đã được xử lý.
- Disk/inodes có headroom.
- WAL/archive đang tiến triển.
- Autovacuum/checkpoints hoạt động.
- Không có crash/restart loop.

### 29.1. Smoke query

Chạy query nhỏ qua application role và endpoint production path, ví dụ:

```sql
SELECT
    current_database(),
    current_user,
    pg_is_in_recovery(),
    now();
```

Đây chỉ là connectivity smoke test, không thay thế business transaction validation.

### 29.2. Kiểm tra connection pool

Xác nhận app pool wait time, active/idle counts, acquisition errors và reconnect rate. Database có thể healthy trong khi pooler vẫn giữ stale connections.

### 29.3. Kiểm tra wait events

Một vài waits bình thường là expected. So sánh với baseline và workload; không yêu cầu mọi wait count bằng zero.

## 30. Xác minh data integrity và business invariants

Nếu incident liên quan write failures, retries, failover hoặc partial processing, cần kiểm tra dữ liệu.

### 30.1. Row counts và key ranges

So sánh counts theo partitions/time windows/tenant hoặc business keys. Một COUNT toàn bảng có thể tốn I/O; chọn scope có ý nghĩa và dùng snapshot/replica phù hợp.

### 30.2. Constraint validation

Kiểm tra constraints cần thiết đang validated và không có rows vi phạm. Với unique/FK invariants, dùng queries phù hợp và không dựa vào sample nhỏ.

### 30.3. Reconciliation

Đối chiếu:
- Request/event IDs.
- Orders/payments/ledger records.
- Outbox/inbox state.
- Duplicate/missing operations.
- Aggregates hoặc balances.
- External system acknowledgments.

### 30.4. Idempotency và retry outcomes

Sau retry storm hoặc client timeout, xác định requests nào đã commit nhưng client không nhận response. Reconcile bằng idempotency keys và transaction records trước khi replay.

### 30.5. Không chạy repair SQL không có dry run

Trước bulk update/delete:
- SELECT tập rows mục tiêu.
- Lưu row count và key sample.
- Xác nhận mapping/expected values.
- Chạy trên clone nếu có thể.
- Chia batch và có checkpoint.
- Dùng transaction phù hợp.
- Có backup/rollback/reconciliation plan.

## 31. Xác minh replication, archive và backup

Service có thể hoạt động lại trong khi DR posture vẫn bị suy giảm.

### 31.1. Replication

Kiểm tra primary có các standbys mong đợi, state là streaming, LSN tiến triển, lag trở về budget và slots không giữ WAL bất thường.

### 31.2. Archive

Xác nhận WAL mới được archive thành công và có thể truy xuất từ archive storage. Một metric archive success không chứng minh toàn bộ WAL chain từ base backup vẫn liên tục.

### 31.3. Backup

Xác nhận backup gần nhất:
- Có status thành công.
- Có manifest/checksum.
- Nằm trên independent storage.
- Có retention.
- Có thể restore theo procedure hiện tại.

### 31.4. Restore point sau incident

Sau incident có data repair hoặc failover, tạo backup mới phù hợp và ghi recovery point. Không thay thế bản backup trước incident trước khi xác định retention/legal requirements.

### 31.5. DR readiness

Nếu failover/restore đã được dùng, re-establish DR topology và test lại replication/restore. Không đóng incident khi chỉ primary đã hoạt động nhưng standby chưa được rejoined.

## 32. Xác minh application và end-to-end service

Kiểm tra từ ngoài database:
- Critical API success/error rate.
- p50/p95/p99 latency.
- Pool acquisition time.
- Business transaction success.
- Queue backlog và worker lag.
- Scheduled jobs.
- Cache invalidation/refresh.
- CDC/ETL/analytics consumers.
- External integrations.

### 32.1. Synthetic transactions

Chạy một giao dịch kiểm thử có thể xác định và cleanup/reconcile được. Không dùng test data gây side effects thật như gửi payment/email nếu chưa có sandbox/guard.

### 32.2. Traffic canary

Mở lại traffic theo từng phần nếu incident nghiêm trọng. Theo dõi error/latency/resource budgets trước khi tăng tiếp.

### 32.3. Observe a representative window

Khoảng quan sát cần bao phủ peak traffic, scheduled jobs hoặc batch cycle liên quan. Một phút healthy sau restart không chứng minh incident đã hết.

## 33. Khi nào cần escalation hoặc dừng thao tác?

Chuyển sang incident lead/DBA/DR owner khi:
- Có dấu hiệu data corruption hoặc checksum errors.
- Không rõ primary nào là authoritative.
- Có nguy cơ split brain.
- WAL chain hoặc backup integrity không rõ.
- Storage báo I/O errors.
- Cần thao tác trực tiếp trên data files/control files.
- Cần drop replication slot hoặc thay đổi recovery target.
- Cần restore/rewind/reseed cluster.
- Bulk repair có thể thay đổi nhiều dữ liệu.
- RPO/RTO có thể bị vượt.

Khi chưa hiểu state, giữ nguyên source data và thu thập evidence. Không thử nhiều repair commands để xem command nào chạy được.

## 34. Incident handoff và communication

Handoff tốt giúp người tiếp nhận hiểu được trạng thái mà không phải tái điều tra từ đầu.

Ghi:
- Incident summary và severity.
- User/business impact.
- Affected cluster/database/node.
- Timeline.
- Current primary/standby roles.
- Evidence links/locations.
- Actions already taken.
- Current metrics/state.
- Data integrity concerns.
- Pending decisions.
- Next recommended action.
- Owner và escalation contact.

Cập nhật rõ điều gì đã xác minh, điều gì mới là giả thuyết và điều gì chưa biết. Tránh dùng từ fixed trước khi verification criteria đạt.

## 35. Post-incident review và root cause analysis

Mục tiêu là giảm xác suất/tác động tái diễn, không tìm người để đổ lỗi.

### 35.1. Timeline

Dựng lại từ alert, logs, deploy events, database stats và operator notes. Dùng timestamps thống nhất và đánh dấu khoảng trống evidence.

### 35.2. Root cause và contributing factors

Phân biệt:
- Triggering event.
- Root cause kỹ thuật.
- Contributing conditions.
- Detection gap.
- Mitigation delay.
- Recovery bottleneck.

Ví dụ một query regression có thể được trigger bởi release, nhưng contributing factors là thiếu plan regression tests, statistics cũ và không có query-level alert.

### 35.3. Five whys không phải mục tiêu tự thân

Dùng câu hỏi để tìm cơ chế và control gaps. Không ép mọi incident thành một nguyên nhân đơn lẻ nếu thực tế là nhiều yếu tố tương tác.

### 35.4. Blameless review

Tập trung vào system design, tooling, runbooks, observability, permissions, deployment controls và capacity planning. Ghi hành động cụ thể, owner và due date.

### 35.5. Action items

Chia thành:
- Prevention: giảm khả năng xảy ra.
- Detection: phát hiện sớm hơn.
- Mitigation: giảm blast radius.
- Recovery: giảm thời gian phục hồi.
- Evidence: bảo đảm incident sau có dữ liệu tốt hơn.

## 36. Incident report template

Có thể dùng cấu trúc sau:

```markdown
# PostgreSQL Incident Report

## Summary
- Incident ID:
- Severity:
- Start/end time (UTC):
- Affected cluster/database:
- User impact:

## Timeline
- Detection:
- First symptom:
- Mitigations:
- Recovery:
- Verification complete:

## Evidence
- PostgreSQL version/role:
- Relevant logs:
- Sessions/locks:
- Query IDs/plans:
- WAL/replication:
- Storage/OS:
- Recent changes:

## Actions
- Action:
- Owner:
- Reason/evidence:
- Result:
- Rollback:

## Data and recovery
- Integrity checks:
- Replicas:
- WAL archive:
- Backup/restore point:
- RPO/RTO impact:

## Root cause
- Trigger:
- Root cause:
- Contributing factors:
- Detection/recovery gaps:

## Follow-up
- Prevention:
- Detection:
- Mitigation:
- Recovery:
- Owner/due date:
```

Không đưa secrets, raw credentials hoặc PII không cần thiết vào report.

## 37. Ví dụ thực hành: connection storm sau deployment

**Triệu chứng:** API bắt đầu timeout ngay sau khi deploy phiên bản mới. PostgreSQL connection count tăng nhanh.

**Thu thập evidence:**
1. Xác nhận primary endpoint và version.
2. Lấy connections theo application_name, state và user.
3. Lấy pool metrics từ từng application replica.
4. Ghi deployment timestamp/version.
5. Kiểm tra long transactions và wait events.
6. Kiểm tra CPU, memory và database error logs.

**Giả thuyết:** mỗi application pod tạo pool mới quá lớn hoặc retry logic tạo reconnect storm.

**Mitigation:**
1. Rate limit endpoint không critical.
2. Giảm worker concurrency hoặc tạm dừng batch jobs.
3. Rollback deployment nếu evidence liên kết trực tiếp với release.
4. Chỉ terminate sessions đã xác định là orphan/stale khi cần.

**Verification:**
- Connection count trở về capacity budget.
- Pool acquisition wait giảm.
- API error rate và p95/p99 phục hồi.
- Business writes không bị duplicate.
- Worker backlog được xử lý có kiểm soát.

## 38. Ví dụ thực hành: DDL gây lock queue

**Triệu chứng:** Nhiều queries trên một table bị chờ lock; migration đang chạy hoặc chờ.

**Thu thập evidence:**
- Blocking tree từ pg_blocking_pids.
- DDL query và migration owner.
- Transaction age của blocker.
- Waiters và relation.
- Recent application release/migration event.

**Mitigation:**
1. Dừng tạo thêm traffic vào table nếu cần.
2. Xác định DDL đang chạy hay chỉ đang chờ.
3. Nếu DDL chờ lock tạo queue, cân nhắc cancel DDL theo migration runbook.
4. Xử lý transaction blocker với owner.
5. Retry migration sau khi đặt lock timeout và chọn thời điểm phù hợp.

**Verification:**
- Lock queue tan.
- Queries của ứng dụng hoàn tất.
- Migration state nhất quán.
- Constraint/index status được xác nhận.
- Không có partial migration step bị bỏ sót.

## 39. Ví dụ thực hành: replication lag và WAL disk growth

**Triệu chứng:** Primary disk tăng nhanh; standby replay lag tăng.

**Thu thập evidence:**
- pg_stat_replication ở primary.
- pg_stat_wal_receiver ở standby.
- Replication slots và restart LSN.
- pg_stat_archiver.
- Disk/IOPS/latency trên cả hai nodes.
- WAL generation rate và application write throughput.

**Mitigation:**
1. Xác định bottleneck là send, network, write, flush hay replay.
2. Giảm bulk writes/backfills không critical.
3. Khôi phục archive destination nếu lỗi.
4. Tăng volume capacity nếu cần và platform hỗ trợ.
5. Xử lý inactive slot chỉ sau khi xác nhận owner và rebuild path.

**Verification:**
- Receive/flush/replay LSN tiến triển.
- Lag giảm về budget.
- WAL retention ổn định.
- Archive success trở lại.
- Standby có thể phục vụ workload theo freshness requirement.

## 40. Ví dụ thực hành: volume gần đầy

**Triệu chứng:** Writes bắt đầu fail và primary volume gần hết dung lượng.

**Thu thập evidence:**
- Filesystem/inode usage.
- PGDATA, pg_wal, tablespace và temp paths.
- Replication slots.
- Archive failures.
- Long-running transactions.
- Backup/log growth.

**Mitigation:**
1. Mở rộng volume nếu có thể.
2. Tạm dừng workload tạo nhiều WAL.
3. Sửa archive failure hoặc consumer lag.
4. Dọn artifacts ngoài PostgreSQL data directory theo retention policy.
5. Không xóa WAL/relation files bằng shell.

**Verification:**
- Free space có headroom.
- PostgreSQL ghi/flush WAL bình thường.
- Checkpoints và archive tiếp tục.
- Replicas catch up.
- Backup mới hoàn tất.

## 41. Checklist thu thập bằng chứng

- [ ] Incident ID, severity và timeline được ghi.
- [ ] Cluster/database/endpoint và primary/standby role được xác nhận.
- [ ] PostgreSQL version, image/package và recent deployments được ghi.
- [ ] pg_stat_activity snapshot được lưu.
- [ ] Blocking PIDs và lock details được lưu.
- [ ] Long transactions/idle-in-transaction được xác định.
- [ ] Connection counts/pool metrics được lưu.
- [ ] WAL, replication, slots và archive state được lưu.
- [ ] Vacuum/progress và transaction age được kiểm tra.
- [ ] Query fingerprints/plans được lưu khi cần.
- [ ] CPU, memory, disk, I/O, network và platform events được đối chiếu.
- [ ] Logs được export với timestamps.
- [ ] Secrets/PII được redact theo policy.
- [ ] Statistics chưa bị reset trước khi snapshot.

## 42. Checklist giảm tác động

- [ ] Impact và data-loss risk được xác định.
- [ ] Incident owner và action owner rõ ràng.
- [ ] Mitigation có phạm vi nhỏ nhất phù hợp.
- [ ] Evidence đã được lưu trước thao tác làm mất state.
- [ ] Traffic/retries/batch concurrency được kiểm soát.
- [ ] Cancel/terminate chỉ áp dụng cho PID đã xác minh.
- [ ] Không xóa WAL/relation files hoặc data directory bằng shell.
- [ ] Không failover khi chưa fencing/đánh giá RPO.
- [ ] Config changes có old value và rollback.
- [ ] Mỗi action có metric và điều kiện dừng.

## 43. Checklist xác minh sau xử lý

- [ ] PostgreSQL startup/recovery ổn định.
- [ ] Critical connections và queries hoạt động.
- [ ] Lock queues và long transactions đã được xử lý.
- [ ] Disk, memory, CPU và I/O có headroom.
- [ ] Query latency/throughput trở lại SLO.
- [ ] Application pools và worker queues bình thường.
- [ ] Data integrity/reconciliation hoàn tất.
- [ ] Primary/standby roles và replication lag đúng.
- [ ] WAL archiving hoạt động.
- [ ] Backup mới có status và restore path phù hợp.
- [ ] DR topology đã được khôi phục nếu bị ảnh hưởng.
- [ ] Quan sát đủ một workload window đại diện.
- [ ] Incident timeline, decision log và follow-ups được lưu.

## 44. Best practices

- Thu thập snapshot trước khi restart, terminate, failover hoặc reset statistics.
- Xác nhận database identity và primary/standby role trước khi hành động.
- Dùng pg_stat_activity, pg_locks, pg_blocking_pids và replication views theo đúng version.
- Kết hợp database evidence với OS, storage, container và application telemetry.
- Ghi timestamp/timezone, application version, request ID và operator action.
- Redact secrets/PII và bảo vệ evidence artifacts.
- Ưu tiên rate limiting, backpressure và mitigation có thể đảo ngược.
- Cancel query cụ thể sau khi xác định owner/impact; hạn chế terminate sessions.
- Không xóa WAL, relation files hoặc PID files theo phỏng đoán.
- Không promote standby nếu chưa đánh giá fencing, timeline và RPO.
- Xác minh data integrity, replication, archive và backup sau khi service phục hồi.
- Dùng post-incident review để cải thiện detection, mitigation và recovery.

## 45. Tài liệu chính thức tham khảo

- [PostgreSQL — Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring.html): activity monitoring và statistics views.
- [PostgreSQL — Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html): statistics collection và reset behavior.
- [PostgreSQL — System Administration Functions](https://www.postgresql.org/docs/current/functions-admin.html): backend cancel/terminate và administrative functions.
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): lock modes và deadlocks.
- [PostgreSQL — WAL Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html): WAL, checkpoints và durability-related settings.
- [PostgreSQL — Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html): standby and streaming replication.
- [PostgreSQL — Replication Slots](https://www.postgresql.org/docs/current/warm-standby.html#STREAMING-REPLICATION-SLOTS): slot retention behavior.
- [PostgreSQL — Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html): vacuum, analyze và transaction ID maintenance.
- [PostgreSQL — Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html): SQLSTATE codes.
- [PostgreSQL — Continuous Archiving and PITR](https://www.postgresql.org/docs/current/continuous-archiving.html): backup, WAL archive và recovery.
- [PostgreSQL — pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html): query-level workload statistics.

Các catalog columns, statistics views và wait events có thể thay đổi giữa major versions. Khi xử lý production, dùng manual đúng phiên bản đang chạy và đối chiếu quyền của operator role. Diagnostic queries cũng tiêu thụ tài nguyên; chỉ thu thập phạm vi cần thiết.

## 46. Tổng kết

Xử lý sự cố PostgreSQL không kết thúc khi process hoạt động lại hoặc alert chuyển xanh. Cần giữ bằng chứng, giảm impact bằng hành động có kiểm soát, sau đó xác minh database, dữ liệu, ứng dụng, replication và backup đã phục hồi.

1. **Thu thập:** xác nhận identity/role, lưu timeline, sessions, locks, WAL, replication, logs và OS/platform metrics trước khi thay đổi state.
2. **Đánh giá:** phân biệt symptom với impact, xác định data-loss risk, severity và blast radius.
3. **Mitigate:** giảm traffic/concurrency, xử lý đúng blocker hoặc resource bottleneck, ghi owner và rollback condition.
4. **Bảo vệ dữ liệu:** không xóa WAL/data files, không dùng failover hoặc repair commands khi chưa hiểu recovery state.
5. **Xác minh:** đo lại service health, business correctness, replicas, archive, backups và SLO qua workload window đại diện.
6. **Cải tiến:** lưu incident report, root cause/contributing factors và action items có owner/deadline.

Một incident chỉ được xem là phục hồi khi dịch vụ đáp ứng yêu cầu, dữ liệu được xác minh, replication/backup posture đã trở lại mức chấp nhận được và đội vận hành có evidence cho các kết luận đó.

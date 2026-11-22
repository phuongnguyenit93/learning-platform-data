# Chọn chỉ số theo độ trễ, thông lượng, lỗi và tài nguyên trong PostgreSQL

Giám sát PostgreSQL không chỉ là nhìn CPU, RAM hay số kết nối. Một database có thể dùng CPU thấp nhưng truy vấn vẫn chậm vì chờ lock; replication có thể streaming nhưng replay lag tăng; disk còn nhiều dung lượng nhưng I/O latency cao; transaction rate ổn định nhưng tỷ lệ lỗi tăng. Muốn hiểu hệ thống đang khỏe hay gặp vấn đề, cần chọn chỉ số theo câu hỏi vận hành.

Bốn nhóm tín hiệu chính:

- **Độ trễ (Latency):** một thao tác mất bao lâu từ lúc bắt đầu tới lúc hoàn tất.
- **Thông lượng (Throughput):** hệ thống xử lý bao nhiêu công việc trong một đơn vị thời gian.
- **Lỗi (Errors):** bao nhiêu thao tác thất bại, timeout, bị retry hoặc không đáp ứng kết quả mong đợi.
- **Tài nguyên (Resources):** CPU, memory, storage, I/O, network và connection capacity đang được sử dụng hoặc bão hòa ra sao.

Bốn nhóm cần được đọc cùng nhau. Throughput tăng có thể là tăng trưởng tốt, nhưng cũng có thể là retry storm. Latency trung bình thấp có thể che giấu một nhóm request p99 rất chậm. CPU cao có thể do workload hữu ích hoặc query plan kém. Error rate tăng có thể do database, ứng dụng, network hoặc dependency bên ngoài.

```text
                 Người dùng / ứng dụng
                         |
                         v
                  PostgreSQL service
                         |
       +-----------------+-----------------+
       |                 |                 |
       v                 v                 v
    Latency           Throughput         Errors
  p50/p95/p99       tx/s, rows/s       SQLSTATE, timeout
       |                 |                 |
       +-----------------+-----------------+
                         |
                         v
                     Resources
            CPU / memory / disk / I/O / network
                         |
                         v
                 SLO, alerts, runbooks
```

Bài học thuộc module **Database Engine Relational PostgreSQL**, chương **Giám sát**, với đề tài **“Chọn chỉ số theo độ trễ, thông lượng, lỗi và tài nguyên”**. Mục tiêu là xây dựng cách chọn metric có ý nghĩa, hiểu nguồn dữ liệu PostgreSQL, thiết kế dashboard và alert có thể hành động, đồng thời liên hệ chỉ số với SLO và nguyên nhân vận hành.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt metric, log, trace, event và profile.
2. Giải thích bốn nhóm tín hiệu latency, throughput, errors và resources.
3. Dùng mô hình RED để quan sát rate, errors và duration.
4. Dùng mô hình USE để quan sát utilization, saturation và errors của tài nguyên.
5. Chọn latency percentile p50, p95 và p99 phù hợp với SLO.
6. Phân biệt latency phía ứng dụng, connection, query execution và transaction.
7. Đo throughput bằng transaction rate, query rate, rows và WAL generation.
8. Phân biệt counter, gauge, histogram và summary.
9. Tính rate từ cumulative counters và xử lý stats reset.
10. Theo dõi error rate, SQLSTATE, deadlock, timeout và cancellation.
11. Phân tích CPU, memory, disk capacity, IOPS, throughput và I/O latency.
12. Theo dõi connection usage, pool saturation và transaction age.
13. Dùng pg_stat_activity, pg_stat_database và pg_stat_statements.
14. Dùng pg_stat_replication, pg_stat_wal_receiver và pg_replication_slots.
15. Dùng pg_stat_user_tables, pg_stat_user_indexes và progress views.
16. Hiểu khác biệt phiên bản của pg_stat_io, pg_stat_bgwriter và pg_stat_checkpointer.
17. Kết hợp PostgreSQL statistics với OS/cloud metrics.
18. Thiết kế dashboard theo workload, service objective và failure mode.
19. Tạo alert dựa trên triệu chứng, trend, duration và impact.
20. Phân biệt alert threshold, warning, critical và SLO burn rate.
21. Tránh cardinality cao, label nhạy cảm và metric không có owner.
22. Xây dựng baseline, capacity forecast và runbook chẩn đoán.
23. Đánh giá hiệu quả thay đổi bằng before/after metrics.

**Phạm vi:** PostgreSQL hiện đại. Một số statistics views và cột thay đổi theo major version. pg_stat_io có từ PostgreSQL 16; thống kê checkpoint/background writer thay đổi đáng kể ở PostgreSQL 17. Luôn đối chiếu catalog của version triển khai. Các ví dụ dùng các cột phổ biến và cần xác nhận quyền truy cập.

---

## 2. Monitoring cần trả lời câu hỏi nào?

Một metric chỉ hữu ích khi nó giúp trả lời một câu hỏi cụ thể.

| Câu hỏi | Nhóm tín hiệu | Ví dụ |
| --- | --- | --- |
| Người dùng có đang chờ lâu không? | Latency | p95 query/transaction latency |
| Hệ thống xử lý được bao nhiêu việc? | Throughput | transactions/s, queries/s |
| Bao nhiêu thao tác thất bại? | Errors | error rate, timeout, deadlock |
| Tài nguyên nào sắp hết? | Resources | CPU, disk free, connections |
| Standby có theo kịp không? | Latency + throughput | replay lag, WAL rate |
| Vacuum có theo kịp không? | Throughput + resources | dead tuples, vacuum duration |
| Backup còn dùng được không? | Errors + freshness | last successful backup, restore test |
| Có nguy cơ mất dữ liệu không? | Errors + resources | archive failures, slot retention |
| Một query cụ thể đang chậm vì sao? | Latency + waits | query duration, wait_event, plan |

### 2.1. Bắt đầu từ dịch vụ, sau đó mới đến database

Người dùng quan tâm thời gian phản hồi và kết quả nghiệp vụ. PostgreSQL metrics giải thích một phần nguyên nhân, nhưng application metrics cần cho biết request nào bị chậm, endpoint nào lỗi và tác động tới người dùng.

### 2.2. Chỉ số phải có ngữ cảnh

CPU usage 90% có thể bình thường trong batch window, nhưng đáng lo nếu API latency tăng và queue backlog tích tụ. Connection count 500 có thể bình thường với pool lớn, nhưng nguy hiểm nếu gần max_connections và nhiều session idle in transaction.

### 2.3. Không có một metric đơn lẻ đại diện cho sức khỏe

Kết hợp latency, throughput, errors, resource saturation và trạng thái dữ liệu. Dùng nhiều tín hiệu độc lập để tránh kết luận sai.

---

## 3. Mô hình RED: Rate, Errors, Duration

RED thường dùng cho dịch vụ hoặc request path.

### 3.1. Rate

Rate đo số request/operation trong một đơn vị thời gian, ví dụ request/s hoặc transaction/s.

Câu hỏi:
- Tải có tăng hay giảm?
- Có spike bất thường không?
- Sau deploy, throughput thay đổi thế nào?
- Có retry làm số request tăng giả tạo không?

### 3.2. Errors

Errors đo số request thất bại hoặc tỷ lệ thất bại.

Câu hỏi:
- Bao nhiêu phần trăm request lỗi?
- Lỗi do SQL, timeout, connection, constraint hay dependency?
- Lỗi có tập trung vào endpoint hoặc query family nào không?
- Error budget đang bị tiêu thụ nhanh tới đâu?

### 3.3. Duration

Duration đo thời gian xử lý request. Nên theo dõi phân phối latency và percentiles, không chỉ average. Một tỷ lệ nhỏ request cực chậm có thể làm người dùng quan trọng bị ảnh hưởng dù average vẫn thấp.

### 3.4. RED cho PostgreSQL

| RED | Application/service | PostgreSQL |
| --- | --- | --- |
| Rate | Requests/s | Transactions/s, statements/s |
| Errors | HTTP 5xx, failed requests | SQL errors, deadlocks, cancellations, connection failures |
| Duration | Request latency | Query/transaction latency, lock wait, commit latency |

RED giúp bắt đầu từ tác động người dùng rồi drill down tới database.

---

## 4. Mô hình USE: Utilization, Saturation, Errors

### 4.1. Utilization

Tỷ lệ thời gian hoặc capacity đang được dùng.

Ví dụ:
- CPU busy percentage.
- Disk utilization.
- Network bandwidth utilization.
- Connection pool usage.
- Buffer/cache behavior cần được diễn giải đúng, không coi mọi cache usage cao là xấu.

### 4.2. Saturation

Mức công việc phải chờ vì tài nguyên không đáp ứng kịp.

Ví dụ:
- CPU run queue.
- I/O queue depth.
- Requests chờ connection.
- Lock waiters.
- Disk queue.
- Worker slots hết.
- Replication backlog tăng liên tục.

### 4.3. Errors

Lỗi ở tài nguyên:
- Disk I/O errors.
- Filesystem read-only.
- Connection refused.
- Out-of-memory kill.
- Network retransmits/drops.
- WAL archive failures.

### 4.4. USE cho PostgreSQL

| Tài nguyên | Utilization | Saturation | Errors |
| --- | --- | --- | --- |
| CPU | CPU busy | run queue, CPU pressure | throttling, steal |
| Memory | working set, cache | reclaim/swap pressure | OOM kill |
| Disk | capacity, busy time | queue depth, latency | I/O errors |
| Network | bandwidth | queue/retransmit | drops, resets |
| Connections | used/max | pool waiters | connection refused |
| WAL | generation/retention | archive/slot backlog | archive failures |
| Locks | lock count | blocked sessions | deadlocks |
| Workers | active/available | waiting jobs | worker launch failures |

### 4.5. Không chỉ nhìn utilization

CPU 40% vẫn có thể có saturation ở một core, một storage queue hoặc connection pool riêng. Tìm queue và waiters, không chỉ phần trăm sử dụng.

---

## 5. Latency: đo thời gian đúng lớp

Latency là thời gian từ một mốc bắt đầu tới một mốc kết thúc. Cần định nghĩa mốc đo trước khi so sánh.

### 5.1. Application request latency

Từ khi ứng dụng nhận request tới khi trả response. Bao gồm:
- Queueing trong application.
- Connection pool wait.
- Network tới database.
- SQL execution.
- Serialization và business logic.
- External dependencies.

Đây thường là metric gần trải nghiệm người dùng nhất.

### 5.2. Connection acquisition latency

Thời gian chờ lấy connection từ pool hoặc thiết lập connection mới. Nếu pool cạn, request có thể chậm trước khi query bắt đầu.

### 5.3. Query latency

Thời gian thực thi một statement ở database. Cần phân biệt execution time, planning time và thời gian chờ lock/I/O.

### 5.4. Transaction latency

Thời gian từ BEGIN tới COMMIT/ROLLBACK. Transaction dài có thể giữ locks và snapshots, gây ảnh hưởng nhiều query khác.

### 5.5. Commit latency

Thời gian COMMIT chờ WAL flush hoặc synchronous standby acknowledgement. Có thể tăng khi storage chậm hoặc synchronous replica/network chậm.

### 5.6. Lock wait latency

Thời gian query/session chờ lock. Query có execution plan nhanh vẫn có thể chậm nếu bị block.

### 5.7. Replication apply lag

Khoảng thời gian hoặc WAL position giữa primary và standby. Cần phân biệt receive lag với replay lag.

### 5.8. Storage latency

Thời gian hoàn tất read/write I/O. Disk latency tăng có thể ảnh hưởng checkpoint, WAL flush, table scans và vacuum.

---

## 6. Percentiles: p50, p95 và p99

Average che giấu tail latency. Percentiles giúp hiểu phân phối thời gian phản hồi.

### 6.1. p50

50% request hoàn tất trong hoặc dưới thời gian p50. Đây là median, đại diện trải nghiệm ở giữa phân phối.

### 6.2. p95

95% request hoàn tất trong hoặc dưới p95. 5% còn lại chậm hơn.

### 6.3. p99

99% request hoàn tất trong hoặc dưới p99. 1% request còn lại chậm hơn. Với workload lớn, 1% có thể là số lượng request đáng kể.

### 6.4. Ví dụ

Giả sử 10.000 query có phân phối:

| Metric | Thời gian |
| --- | ---: |
| p50 | 8 ms |
| p95 | 70 ms |
| p99 | 900 ms |
| Average | 24 ms |

Average 24 ms không cho thấy nhóm query p99 mất gần một giây. Điều tra tail latency có thể tìm ra lock wait, cache miss, plan variation hoặc storage stalls.

### 6.5. Percentile không thể cộng tùy tiện

p95 của query A cộng p95 của query B không nhất thiết bằng p95 của request chứa cả hai. Muốn đo request end-to-end, instrument ở application boundary.

### 6.6. Histogram và bucket

Histogram lưu phân phối theo buckets, cho phép tính quantiles gần đúng khi aggregate nhiều instances. Bucket phải đủ chi tiết quanh ngưỡng SLO.

### 6.7. Summary và histogram

Summary có thể tính quantile tại từng process nhưng khó aggregate quantile đúng giữa nhiều instances. Histogram thường phù hợp hơn cho distributed aggregation nếu thiết kế buckets hợp lý.

### 6.8. Chọn percentile theo mục tiêu

- p50: theo dõi trải nghiệm thông thường.
- p95: phát hiện phần đuôi phổ biến.
- p99: phát hiện tail latency ảnh hưởng nhóm request nhỏ nhưng quan trọng.
- Max: hữu ích cho điều tra nhưng rất nhạy với outlier và sample size.

Không chọn p99 nếu lượng request quá ít để percentile có ý nghĩa thống kê.

---

## 7. Thiết kế latency SLO

SLO (Service Level Objective) là mục tiêu chất lượng dịch vụ trong một khoảng thời gian.

Ví dụ:
- 99% request đọc hoàn tất trong 100 ms trong cửa sổ 30 ngày.
- 99.9% transaction ghi thành công trong giới hạn latency đã thống nhất.
- 99.95% thời gian write endpoint sẵn sàng.

### 7.1. SLO cần định nghĩa scope

Nêu rõ endpoint hoặc workload, request được tính, timeout/cancel có tính là lỗi không, cửa sổ đo, percentile hoặc tỷ lệ đáp ứng, và cách xử lý maintenance/dependency outage.

### 7.2. Database SLI và application SLI

Database query latency không thay thế application request latency. Có thể dùng database SLI để chẩn đoán và application SLI để đo trải nghiệm.

### 7.3. Error budget

Nếu SLO cho phép một tỷ lệ request lỗi, phần cho phép đó là error budget. Burn rate cho biết tốc độ tiêu thụ budget.

### 7.4. Không đặt SLO theo metric dễ lấy

Đặt mục tiêu theo nhu cầu người dùng và business impact, sau đó chọn metrics có thể đo.

---

## 8. Throughput: đo lượng công việc

Throughput là lượng công việc hoàn tất trong một đơn vị thời gian. Một số metric đo số thao tác, một số đo bytes hoặc rows.

### 8.1. Transactions per second

Có thể ước tính từ commit/rollback counters trong pg_stat_database:

```sql
SELECT
    datname,
    xact_commit,
    xact_rollback,
    stats_reset
FROM pg_catalog.pg_stat_database
WHERE datname IS NOT NULL;
```

Đây là cumulative counters. Để tính transactions/s, lấy chênh lệch giữa hai snapshots rồi chia cho khoảng thời gian, có xét stats_reset.

### 8.2. Queries per second

Không đồng nhất với transactions/s. Một transaction có thể chạy nhiều statements; prepared statements và batch cũng làm quan hệ khác nhau.

### 8.3. Rows processed

pg_stat_database có thể cung cấp tuples returned/fetched/inserted/updated/deleted ở mức database. Đây là counters tổng hợp, không cho biết query cụ thể nào xử lý rows.

### 8.4. WAL generation rate

pg_stat_wal cung cấp counters liên quan WAL. Delta wal_bytes theo thời gian giúp ước lượng write workload và capacity archive/replication.

```sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full,
    stats_reset
FROM pg_catalog.pg_stat_wal;
```

Tên/các cột có thể khác theo version. Dùng catalog hiện có để xác nhận.

### 8.5. I/O throughput

OS/cloud metrics cho biết bytes read/write mỗi giây, IOPS và queue. PostgreSQL-level counters giúp gắn I/O với database/backend khi version hỗ trợ.

### 8.6. Replication throughput

Theo dõi WAL bytes sent/received/flushed/replayed và backlog. Throughput cao không đồng nghĩa lag thấp nếu source sinh WAL nhanh hơn standby xử lý.

### 8.7. Không dùng connection count làm throughput

Connection count là số session đang tồn tại, không phải số request được xử lý. Một connection idle có thể tồn tại hàng giờ.

---

## 9. Counter, gauge, histogram và summary

### 9.1. Counter

Counter chỉ tăng theo thời gian cho tới khi process/server restart hoặc statistics reset.

Ví dụ:
- xact_commit.
- blks_read.
- deadlocks.
- wal_bytes.
- archive failures.

Để có rate, tính delta giữa hai thời điểm.

### 9.2. Gauge

Gauge có thể tăng hoặc giảm.

Ví dụ:
- active connections.
- current sessions.
- disk free space.
- current WAL backlog.
- replication slot retained bytes.

Không tính rate từ gauge nếu không có ý nghĩa.

### 9.3. Histogram

Histogram chia observations vào buckets. Phù hợp với latency distribution, request size hoặc batch duration.

### 9.4. Summary

Summary cung cấp count/sum và có thể quantile theo process/exporter. Phải hiểu giới hạn khi aggregate nhiều instances.

### 9.5. Stats reset

PostgreSQL statistics có thể reset khi server restart hoặc stats reset được gọi. Cần dùng stats_reset để tránh tính rate âm hoặc sai.

### 9.6. Rate calculation

Giả sử counter tăng từ 1.000.000 lên 1.006.000 trong 60 giây:

\[
\text{rate} = \frac{1{,}006{,}000 - 1{,}000{,}000}{60}
= 100 \text{ events/s}
\]

Nếu counter giảm do reset, không diễn giải delta âm như workload âm. Xác định reset rồi bắt đầu baseline mới.

### 9.7. Scrape interval

Interval quá dài có thể bỏ lỡ spike ngắn; quá ngắn tạo overhead và cardinality/storage lớn. Chọn theo độ nhanh của failure mode và chi phí monitoring.

---

## 10. Error metrics: phân loại thay vì đếm chung

Một số lỗi có mức độ nghiêm trọng khác nhau. Cần phân loại theo loại, nguồn và tác động.

### 10.1. SQL errors

Ví dụ:
- Syntax/invalid input.
- Unique violation.
- Foreign-key violation.
- Permission denied.
- Serialization failure.
- Deadlock detected.
- Query canceled.
- Statement timeout.

Một số lỗi là expected business validation, không phải database outage.

### 10.2. Connection errors

- Connection refused.
- Too many connections.
- Authentication failure.
- TLS handshake failure.
- Connection reset.
- Pool acquisition timeout.

### 10.3. Transaction errors

- Deadlock.
- Serialization retry.
- Lock timeout.
- Statement timeout.
- Transaction rollback.

Theo dõi tỷ lệ retry và số lần retry thành công/thất bại.

### 10.4. Replication errors

- WAL receiver disconnect.
- Requested WAL segment missing.
- Timeline mismatch.
- Replication slot invalidation.
- Replay conflict.
- Replication lag vượt policy.

### 10.5. Backup/archive errors

- Base backup job failed.
- Archive command failed.
- Restore command không tìm thấy segment.
- Checksum mismatch.
- Backup repository full.
- Restore drill failed.

### 10.6. Infrastructure errors

- Disk I/O error.
- Filesystem read-only.
- OOM kill.
- Node restart.
- Network packet loss.
- Cloud storage throttling.

### 10.7. SQLSTATE

PostgreSQL cung cấp SQLSTATE code cho lỗi SQL. Nên nhóm theo class/code thay vì parse error text tùy ngôn ngữ, nhưng vẫn cần giữ message/context cho điều tra.

Ví dụ một số class:
- 08: connection exception.
- 22: data exception.
- 23: integrity constraint violation.
- 40: transaction rollback.
- 42: syntax/access rule.
- 53: insufficient resources.
- 55: object not in prerequisite state.
- 57: operator intervention.
- 58: system error.

Mã cụ thể và phân loại đầy đủ cần tra theo PostgreSQL Error Codes cho version phù hợp.

### 10.8. Error rate

\[
\text{Error rate} =
\frac{\text{Failed operations}}{\text{Total operations}}
\]

Nêu rõ mẫu số: requests, transactions, statements hay connections. Không trộn error count của SQL validation với server availability errors.

---

## 11. Deadlocks, lock waits và blocked sessions

Lock contention thường là nguyên nhân latency tăng dù CPU thấp.

### 11.1. Kiểm tra active sessions và wait events

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
    left(query, 200) AS query_sample
FROM pg_catalog.pg_stat_activity
WHERE state <> 'idle'
ORDER BY query_start NULLS LAST;
```

Cần quyền phù hợp để xem query text của session khác; dữ liệu nhạy cảm có thể bị che theo quyền và cấu hình.

### 11.2. Tìm blocked sessions

```sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.usename AS blocked_user,
    blocking.pid AS blocking_pid,
    blocking.usename AS blocking_user,
    now() - blocked.query_start AS blocked_for,
    left(blocked.query, 160) AS blocked_query,
    left(blocking.query, 160) AS blocking_query
FROM pg_catalog.pg_stat_activity AS blocked
JOIN LATERAL unnest(pg_catalog.pg_blocking_pids(blocked.pid))
    AS blocker_pid(pid) ON true
JOIN pg_catalog.pg_stat_activity AS blocking
    ON blocking.pid = blocker_pid.pid
ORDER BY blocked.query_start;
```

### 11.3. Deadlock counter

```sql
SELECT
    datname,
    deadlocks,
    stats_reset
FROM pg_catalog.pg_stat_database
WHERE datname IS NOT NULL;
```

Đây là counter tích lũy; tính rate bằng delta.

### 11.4. Lock wait không giống deadlock

Lock wait có thể được giải phóng khi transaction blocker kết thúc. Deadlock là chu trình phụ thuộc và PostgreSQL sẽ chọn một transaction để abort.

### 11.5. Alert theo thời gian và impact

Một session chờ lock vài mili giây không giống một request quan trọng bị block 5 phút. Alert cần xét số session bị ảnh hưởng, tuổi wait và workload.

---

## 12. Theo dõi query bằng pg_stat_statements

pg_stat_statements là extension phổ biến để tổng hợp thống kê thực thi statement theo query identity.

### 12.1. Bật extension

Tùy cấu hình, cần thêm extension vào shared_preload_libraries và restart:

```conf
shared_preload_libraries = 'pg_stat_statements'
compute_query_id = auto
```

Sau khi server khởi động và extension được tạo trong database:

```sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
```

### 12.2. Truy vấn query có total time cao

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
    left(query, 200) AS query_sample
FROM pg_catalog.pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

Cột và semantics thay đổi theo version. Các bản cũ có thể dùng tên cột khác, ví dụ total_time/mean_time.

### 12.3. Total time và mean time

- total_exec_time cao: query family tiêu tốn nhiều thời gian database tổng cộng.
- mean_exec_time cao: mỗi lần gọi trung bình chậm.
- calls cao: query được gọi thường xuyên.
- rows cao: query trả về nhiều rows.
- temp blocks written cao: query dùng temporary files/blocks đáng kể.

### 12.4. Không chỉ sort theo mean

Một query 2 giây chạy một lần có thể ít ảnh hưởng hơn query 20 ms chạy hàng trăm nghìn lần. Xem calls, total time và business criticality.

### 12.5. Query normalization

pg_stat_statements thường gộp query tương tự bằng query ID và chuẩn hóa constants. Điều này hữu ích cho aggregate nhưng có thể che khác biệt do parameter values hoặc plan variation.

### 12.6. Reset thống kê có chủ đích

Reset có thể làm mất baseline lịch sử. Trước khi reset, lưu snapshot hoặc dùng time-series exporter để giữ dữ liệu.

### 12.7. Query text có thể nhạy cảm

Query có thể chứa tên bảng, schema hoặc literal tùy extension/configuration/version. Kiểm soát quyền và retention của monitoring store.

---

## 13. Theo dõi workload ở mức database

pg_stat_database cung cấp các counters tổng hợp theo database.

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
    deadlocks,
    temp_files,
    temp_bytes,
    stats_reset
FROM pg_catalog.pg_stat_database
WHERE datname IS NOT NULL;
```

### 13.1. Cache hit ratio

Có thể tính gần đúng:

\[
\text{hit ratio} =
\frac{\text{blks\_hit}}
{\text{blks\_hit}+\text{blks\_read}}
\]

Tuy nhiên đây là metric tổng hợp và không bao gồm mọi I/O path. OS page cache, sequential scans, workload mix và data size đều ảnh hưởng. Không tối ưu chỉ để đạt một tỷ lệ hit cao.

### 13.2. temp_bytes và temp_files

Tăng có thể cho biết sort/hash spill ra disk, query cần memory/work_mem khác hoặc workload thay đổi. Không tăng work_mem toàn cục một cách máy móc vì nó có thể được dùng đồng thời bởi nhiều operations/sessions.

### 13.3. conflicts

Trên standby, conflicts có thể cho biết read queries bị ảnh hưởng bởi WAL replay. Kết hợp pg_stat_database_conflicts và logs.

### 13.4. numbackends

Đây là số backend kết nối tại thời điểm lấy snapshot, không phải throughput và không thay thế connection pool metrics.

### 13.5. Counter theo thời gian

Lưu snapshot có timestamp để tính rate. Ghi lại stats_reset và xử lý server restart.

---

## 14. Connections và pool saturation

### 14.1. Connections đang dùng

```sql
SELECT
    state,
    count(*) AS sessions
FROM pg_catalog.pg_stat_activity
GROUP BY state
ORDER BY sessions DESC;
```

### 14.2. Theo database và application

```sql
SELECT
    datname,
    application_name,
    usename,
    state,
    count(*) AS sessions
FROM pg_catalog.pg_stat_activity
GROUP BY datname, application_name, usename, state
ORDER BY sessions DESC;
```

### 14.3. So với max_connections

```sql
SHOW max_connections;
```

Không dùng max_connections như mục tiêu cần tăng liên tục. Mỗi backend tiêu thụ memory/process resources. Connection pooling thường giúp giới hạn concurrency tốt hơn.

### 14.4. Idle in transaction

```sql
SELECT
    pid,
    usename,
    application_name,
    now() - xact_start AS xact_age,
    state,
    wait_event_type,
    wait_event,
    left(query, 160) AS query_sample
FROM pg_catalog.pg_stat_activity
WHERE state = 'idle in transaction'
ORDER BY xact_start;
```

Transaction idle có thể giữ locks, snapshots và làm vacuum không thu hồi được dead tuples.

### 14.5. Pool metrics cần có ở application/proxy

- Pool size.
- Active/idle connections.
- Waiting clients.
- Acquisition latency.
- Connection creation rate.
- Connection errors.
- Queue timeout.
- Recycle/reconnect rate.

### 14.6. Phân biệt database full và pool full

Ứng dụng có thể hết pool connections dù PostgreSQL còn chỗ. Hoặc PostgreSQL hết backend slots dù pool chưa đạt cấu hình. Theo dõi cả hai lớp.

---

## 15. CPU và query execution

### 15.1. CPU utilization

OS/cloud metrics cho biết CPU usage, per-core usage, run queue, steal/throttling và pressure. PostgreSQL statistics không thay thế host metrics.

### 15.2. CPU saturation

Một query single-thread có thể làm một core bão hòa dù tổng CPU thấp trên host nhiều core. Theo dõi per-core và process-level CPU khi điều tra.

### 15.3. Query CPU attribution

pg_stat_statements cho execution time và calls, nhưng không phải CPU time chính xác cho mọi query. Dùng OS profiling/observability tools phù hợp nếu cần attribution sâu.

### 15.4. Query plan

Dùng EXPLAIN để xem plan. EXPLAIN ANALYZE thực thi query thật, nên có thể gây side effects với DML hoặc tải đáng kể. Dùng transaction rollback cho thử nghiệm phù hợp và tránh chạy query nặng trên production mà không đánh giá.

### 15.5. Plan regression

Sau deploy/statistics change/index change, query plan có thể thay đổi. So sánh calls, mean/total execution time, rows, buffers và plan trước/sau.

### 15.6. CPU cao không nhất thiết xấu

CPU cao với throughput tăng và latency ổn định có thể là sử dụng tài nguyên hiệu quả. CPU cao kèm run queue, p99 tăng và throughput không tăng là dấu hiệu saturation.

---

## 16. Memory và cache

### 16.1. shared_buffers

Đây là vùng shared memory PostgreSQL dùng cache data pages. Theo dõi cấu hình và hiệu quả workload, nhưng không coi tỷ lệ dùng cao là lỗi.

### 16.2. OS page cache

PostgreSQL thường dựa thêm vào filesystem cache. Vì vậy shared buffer reads không phải lúc nào cũng tương ứng physical disk reads.

### 16.3. work_mem

Memory cho một số operations như sort/hash, thường áp dụng theo operation và có thể được dùng đồng thời bởi nhiều sessions. Tăng quá cao có thể gây memory pressure.

### 16.4. maintenance_work_mem

Ảnh hưởng một số maintenance operations như VACUUM và CREATE INDEX. Theo dõi maintenance duration và memory capacity.

### 16.5. Memory pressure

Theo dõi available/used memory, swap-in/swap-out, page faults, OOM kills, container memory limit, PostgreSQL process memory và temporary file growth.

### 16.6. Không kết luận từ RSS một process

PostgreSQL dùng shared memory và nhiều processes. Cộng RSS của tất cả backend có thể đếm shared pages nhiều lần. Dùng công cụ OS phù hợp để đọc PSS/cgroup memory và hiểu shared mappings.

### 16.7. Cache hit ratio không phải mục tiêu độc lập

Tỷ lệ hit cao vẫn có thể có query chậm vì CPU, locks, network hoặc cache misses. Một workload sequential scan lớn có thể tạo hit ratio thấp nhưng vẫn chạy tốt.

---

## 17. Disk capacity và I/O

### 17.1. Disk capacity

Theo dõi data filesystem free bytes/percent, WAL filesystem free space, tablespace usage, temporary storage, backup repository capacity, archive repository capacity, growth rate và estimated time to full.

### 17.2. IOPS

Số read/write operations mỗi giây. IOPS cao không tự nói workload tốt/xấu; cần xem size, latency và queue.

### 17.3. Throughput

Bytes read/write mỗi giây. Workload sequential lớn có throughput cao nhưng IOPS vừa phải; random I/O có thể tiêu thụ nhiều IOPS với bytes thấp.

### 17.4. I/O latency

Đo thời gian hoàn tất I/O. Latency tăng thường ảnh hưởng WAL flush, checkpoints, scans, vacuum và temp files.

### 17.5. Queue depth

Queue tăng cho biết I/O requests chờ. Kết hợp với latency và utilization để nhận diện saturation.

### 17.6. WAL riêng

Nếu pg_wal ở volume riêng, theo dõi dung lượng, latency và throughput riêng. WAL flush chậm có thể làm commit latency tăng.

### 17.7. Temporary files

temp_files/temp_bytes ở pg_stat_database và OS disk metrics giúp phát hiện query spill. Xác định query family trước khi thay work_mem.

### 17.8. Không chỉ alert khi disk đầy

Disk growth rate có thể dự báo sự cố sớm. Alert theo estimated time to full hữu ích hơn chờ free space xuống sát 0.

---

## 18. Checkpoint, WAL và background writer

Checkpoint và WAL generation ảnh hưởng write I/O, recovery time và latency.

### 18.1. WAL generation

Theo dõi wal_bytes/s, wal_records/s và full-page images. Workload write spike có thể làm WAL archive và replication traffic tăng.

### 18.2. Checkpoint frequency

Checkpoint quá thường xuyên có thể tăng write pressure; checkpoint quá xa có thể tăng recovery work. Theo dõi checkpoint write/sync time và requested checkpoints.

### 18.3. Checkpoint metrics theo version

Trước PostgreSQL 17, nhiều checkpoint/background writer counters nằm trong pg_stat_bgwriter. Từ PostgreSQL 17, checkpoint statistics được tách rõ hơn vào pg_stat_checkpointer và pg_stat_bgwriter tập trung vào background writer. Cột cụ thể phụ thuộc version.

### 18.4. Checkpoint write/sync time

Nếu checkpoint write/sync time tăng cùng storage latency và query latency, kiểm tra I/O capacity, checkpoint settings và workload.

### 18.5. full_page_writes/FPI

Full-page images có thể làm WAL volume tăng sau checkpoint. wal_fpi giúp quan sát một phần hoạt động này; đừng tắt full_page_writes để giảm WAL nếu chưa hiểu rủi ro durability/corruption.

### 18.6. Background writer

Background writer giúp ghi dirty buffers trước khi backend cần ghi chúng. Theo dõi buffers_clean, buffers_backend và buffers_backend_fsync theo version.

---

## 19. pg_stat_io trên PostgreSQL 16 trở lên

pg_stat_io cung cấp thống kê I/O theo backend type, object và context ở các phiên bản hỗ trợ.

Ví dụ khám phá:

```sql
SELECT *
FROM pg_catalog.pg_stat_io;
```

### 19.1. Backend type

Có thể phân biệt các nhóm backend thực hiện I/O như client backend, background writer, checkpointer và các loại khác tùy version.

### 19.2. Object và context

Giúp hiểu I/O theo object/context mà view hỗ trợ, ví dụ relation hoặc temporary relation. Schema cụ thể cần đọc trên server.

### 19.3. Counters

View có thể cung cấp read/write counts, bytes, evictions, reuses, fsyncs và timing fields theo version.

### 19.4. Timing không tự bật ở mọi cấu hình

Một số timing metrics phụ thuộc track_io_timing hoặc điều kiện cấu hình. Đánh giá overhead trước khi bật rộng.

### 19.5. Không thay OS I/O metrics

pg_stat_io giúp phân tích PostgreSQL activity; OS/cloud metrics vẫn cần để hiểu physical device latency, queue và throttling.

---

## 20. Vacuum, autovacuum và table health

Vacuum ảnh hưởng bloat, transaction ID safety và query performance.

### 20.1. Table activity

```sql
SELECT
    schemaname,
    relname,
    seq_scan,
    seq_tup_read,
    idx_scan,
    idx_tup_fetch,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_catalog.pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
```

### 20.2. Dead tuples

n_dead_tup là ước tính thống kê, không phải số đo chính xác tức thời. Tăng liên tục có thể cho thấy vacuum không theo kịp hoặc transaction giữ snapshot quá lâu.

### 20.3. Vacuum progress

```sql
SELECT *
FROM pg_catalog.pg_stat_progress_vacuum;
```

Dùng để xem vacuum đang xử lý phase nào và tiến độ trên các phiên bản hỗ trợ.

### 20.4. Analyze freshness

Statistics cũ có thể làm planner chọn plan kém. Theo dõi last_autoanalyze và workload changes.

### 20.5. Transaction ID age

Database/table XID age cần được giám sát để tránh transaction ID wraparound. Cần cảnh báo trước ngưỡng nguy hiểm, không đợi autovacuum emergency.

### 20.6. Long transactions

Transaction lâu giữ xmin/snapshot và có thể ngăn vacuum cleanup. Theo dõi xact_start, backend_xmin và idle-in-transaction.

---

## 21. Index usage và index health

### 21.1. Index statistics

```sql
SELECT
    schemaname,
    relname AS table_name,
    indexrelname AS index_name,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_catalog.pg_stat_user_indexes
ORDER BY idx_scan ASC
LIMIT 50;
```

### 21.2. Index không được dùng

idx_scan thấp có thể gợi ý index ít dùng, nhưng không đủ để drop. Statistics có thể reset, workload theo mùa hoặc index phục vụ rare critical query.

### 21.3. Sequential scans

Seq scan không mặc nhiên xấu. Với table nhỏ hoặc query cần phần lớn rows, sequential scan có thể tối ưu.

### 21.4. Index bloat

Không có một metric built-in duy nhất đo chính xác mọi loại bloat. Cần dùng catalog estimates hoặc extension/tool phù hợp và cân nhắc chi phí đo.

### 21.5. Index build progress

```sql
SELECT *
FROM pg_catalog.pg_stat_progress_create_index;
```

Theo dõi tiến trình CREATE INDEX/REINDEX trên version hỗ trợ.

---

## 22. Replication và standby metrics

### 22.1. Primary-side replication

```sql
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_catalog.pg_stat_replication;
```

### 22.2. Standby receive/replay

```sql
SELECT
    pg_is_in_recovery(),
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn(),
    pg_last_xact_replay_timestamp();
```

### 22.3. WAL receiver

```sql
SELECT *
FROM pg_catalog.pg_stat_wal_receiver;
```

### 22.4. Replication slots

```sql
SELECT *
FROM pg_catalog.pg_replication_slots;
```

### 22.5. Cần đo cả lag và retention

Một standby có thể lag tăng nhưng primary vẫn giữ đủ WAL. Một standby có lag nhỏ nhưng slot/archive sắp mất khả năng giữ WAL cũng cần chú ý.

### 22.6. Sync state

Theo dõi sync_state và topology thực tế. Nếu synchronous standby biến mất, commit behavior có thể thay đổi theo synchronous_standby_names và policy.

### 22.7. Timeline

Ghi timeline ID cùng LSN khi có failover/promotion. Không so sánh LSN giữa hai nhánh divergent như cùng một lịch sử.

---

## 23. Backup và archive metrics

### 23.1. Backup freshness

Metric cần có:
- Age của base backup mới nhất.
- Thời gian backup gần nhất thành công.
- Duration và bytes copied.
- Backup size growth.
- Verification status.
- Restore test age.

### 23.2. WAL archive

```sql
SELECT *
FROM pg_catalog.pg_stat_archiver;
```

Theo dõi failed_count, last_failed_time và last_archived_time.

### 23.3. Archive gap

Một last_archived_time gần đây không chứng minh mọi segment liên tục. Cần kiểm tra inventory theo segment/timeline và manifest.

### 23.4. Restore metrics

Đo download/copy duration, restore duration, WAL replay duration, startup duration, validation duration và time to application-ready.

### 23.5. Backup success không bằng recoverability

Chỉ restore drill mới chứng minh chuỗi backup + WAL + config + credentials + extensions có thể dùng trong thực tế.

---

## 24. Errors trong PostgreSQL logs

Statistics views không ghi lại mọi lỗi. Logs cần được cấu hình để quan sát các sự kiện phù hợp.

### 24.1. log_min_error_statement

Ghi statement liên quan lỗi từ mức được chọn trở lên. Cẩn thận query có dữ liệu nhạy cảm.

### 24.2. log_min_duration_statement

Ghi statement chạy lâu hơn ngưỡng. Có thể tạo lượng log lớn nếu đặt quá thấp.

### 24.3. log_lock_waits

Ghi thông tin lock waits vượt deadlock_timeout. Hữu ích khi điều tra contention.

### 24.4. log_checkpoints

Hữu ích để quan sát checkpoint behavior; chi tiết output thay đổi theo version.

### 24.5. log_connections và log_disconnections

Có thể hỗ trợ điều tra connection churn, nhưng có thể tăng log volume.

### 24.6. log_line_prefix

Nên có timestamp, PID/session, user, database, application_name và transaction/session identifiers phù hợp để liên kết events.

### 24.7. Structured logging

CSV/JSON logs hoặc centralized log pipeline giúp group theo SQLSTATE, application_name, host và time window.

### 24.8. Bảo vệ log

Logs có thể chứa query text, object names, client IP và thông tin nghiệp vụ. Phân quyền, masking, encryption và retention theo policy.

---

## 25. Wait events: hiểu query đang chờ gì

pg_stat_activity cung cấp wait_event_type và wait_event cho các sessions đang chờ.

### 25.1. Lock

Wait event liên quan lock có thể chỉ ra contention do transaction khác giữ lock.

### 25.2. IO

Wait event I/O có thể cho biết backend đang chờ đọc/ghi. Kết hợp OS storage latency để xác nhận.

### 25.3. Client

Session có thể chờ client đọc kết quả hoặc gửi dữ liệu. Ứng dụng đọc chậm có thể giữ backend lâu.

### 25.4. LWLock

Các lightweight locks bảo vệ shared internal structures. Chờ LWLock có thể liên quan contention nội bộ, cần drill down theo event cụ thể.

### 25.5. IPC

Waits giữa processes/background workers có thể liên quan coordination hoặc parallel query.

### 25.6. Active không đồng nghĩa đang dùng CPU

Một session state active nhưng có wait_event vẫn đang chờ. Đếm active sessions đơn thuần có thể đánh giá sai CPU demand.

### 25.7. Snapshot query

```sql
SELECT
    wait_event_type,
    wait_event,
    state,
    count(*) AS sessions
FROM pg_catalog.pg_stat_activity
WHERE state <> 'idle'
GROUP BY wait_event_type, wait_event, state
ORDER BY sessions DESC;
```

---

## 26. Progress views cho tác vụ dài

PostgreSQL có nhiều progress views để theo dõi tác vụ đang chạy.

Ví dụ:
- pg_stat_progress_vacuum.
- pg_stat_progress_create_index.
- pg_stat_progress_analyze.
- pg_stat_progress_cluster.
- pg_stat_progress_basebackup.
- pg_stat_progress_copy.

Tên và cột cần kiểm tra theo version.

### 26.1. Vì sao cần progress metrics?

Một job đang chạy lâu có thể là bình thường nếu còn tiến triển. Nếu progress đứng lâu, có thể gặp lock, I/O bottleneck hoặc resource issue.

### 26.2. Không alert theo duration đơn lẻ

CREATE INDEX trên table lớn có thể mất hàng giờ. Cần theo phase, progress, blocking và maintenance window.

### 26.3. Backup progress

pg_stat_progress_basebackup giúp theo dõi một số base backup đang chạy trên server nguồn ở các phiên bản hỗ trợ.

### 26.4. Copy progress

pg_stat_progress_copy hữu ích cho bulk import/export. Kết hợp bytes/tuples processed và application job state.

---

## 27. Metric cho connection pool và ứng dụng

Database views không biết toàn bộ request queue của ứng dụng.

### 27.1. Application latency

Đo request duration ở API/service boundary. Gắn route, operation class và outcome.

### 27.2. Pool wait

Đo thời gian chờ connection. Nếu pool wait tăng trong khi database query latency ổn định, bottleneck có thể nằm ở pool sizing hoặc leaked connections.

### 27.3. Retry rate

Retry có thể làm tăng throughput counters ở database và khuếch đại overload. Theo dõi retry attempts và retry success.

### 27.4. Request concurrency

Đếm in-flight requests và queue depth. Một hệ thống có request arrival rate cao hơn service rate sẽ tích tụ queue.

### 27.5. Query correlation

Gắn application_name có ý nghĩa vào connection để phân biệt service/job. Có thể dùng trace/request identifiers ở logs của application; tránh đưa ID duy nhất vào metric labels.

### 27.6. Connection pooler

Nếu dùng PgBouncer hoặc proxy, theo dõi client connections, server connections, pool waiters, waiting time, pool saturation, connection errors và transaction/statement pooling behavior.

---

## 28. Cardinality và chất lượng metric labels

### 28.1. Cardinality là số lượng chuỗi label combinations

Một metric có label environment, cluster, instance, database và state thường có cardinality kiểm soát được. Nếu thêm user ID, request ID hoặc raw SQL text, số chuỗi có thể tăng rất lớn.

### 28.2. Cardinality cao gây chi phí

- Tăng memory của monitoring backend.
- Tăng storage/indexing.
- Query dashboard chậm.
- Alert evaluation nặng.
- Dữ liệu khó quản lý và dễ lộ thông tin.

### 28.3. Labels phù hợp

Thường dùng environment, cluster, instance, database (nếu số lượng hữu hạn), application_name đã chuẩn hóa, operation class, error class/SQLSTATE class và region/zone.

### 28.4. Tránh labels duy nhất

Không dùng user ID, order ID, session ID, request ID, full SQL, arbitrary exception message hoặc unbounded tenant IDs nếu số lượng lớn.

Đưa các giá trị duy nhất vào logs/traces với retention và access control phù hợp.

### 28.5. Normalize application_name

Đặt application_name theo service/job role, không thêm UUID cho mỗi process. Có thể thêm instance label ở mức exporter nếu cần và kiểm soát số lượng.

---

## 29. Dashboard: tổ chức theo câu hỏi vận hành

Một dashboard tốt không phải tập hợp mọi metric có thể lấy. Nó phải giúp người trực ca trả lời nhanh: người dùng có bị ảnh hưởng không, thành phần nào chậm và hành động nào cần làm.

### 29.1. Overview

Hiển thị service availability, request latency p50/p95/p99, request/transaction rate, error rate, active/queued requests, current primary/standby role và SLO/error budget.

### 29.2. Database workload

- Transactions/s.
- Query calls and total execution time.
- Top query families.
- Rows returned/changed.
- WAL bytes/s.
- Temporary bytes/s.
- Connection count by state/application.

### 29.3. Latency and waits

- Query latency distribution.
- Lock waits and blockers.
- Wait event breakdown.
- Commit/WAL flush latency.
- Storage I/O latency.
- Connection pool acquisition latency.

### 29.4. Resources

- CPU per core and run queue.
- Memory available, swap, OOM.
- Disk free bytes and time to full.
- IOPS, throughput, latency, queue depth.
- Network throughput/errors/retransmits.
- Connection pool and backend usage.

### 29.5. Replication and HA

- Primary/standby roles.
- Sync state.
- Sent/write/flush/replay LSN.
- Lag bytes/time.
- Slot retention.
- WAL archive failures.
- Last failover and fencing status.

### 29.6. Backup and recovery

- Last base backup age.
- Last successful archive time.
- Archive continuity.
- Repository capacity.
- Last restore drill.
- Measured RPO/RTO.

### 29.7. Vacuum and maintenance

- Dead tuples.
- Last autovacuum/analyze.
- Long transactions.
- XID age.
- Vacuum/index progress.
- Table/index growth.

### 29.8. Dashboard hierarchy

Overview → service/workload → database → query/instance → host/storage. Người vận hành cần drill down từ triệu chứng tới nguyên nhân.

---

## 30. Alert: từ metric tới hành động

Alert cần cho biết triệu chứng, phạm vi, mức độ và bước kiểm tra đầu tiên.

### 30.1. Latency alert

Ví dụ p95 API latency vượt SLO trong 10 phút, p99 query latency tăng đột biến so với baseline, hoặc commit latency cao đồng thời WAL flush time tăng.

### 30.2. Throughput alert

Throughput giảm mạnh trong khi incoming request rate ổn định; queue depth tăng liên tục; WAL generation tăng đột ngột vượt capacity dự kiến.

Throughput thấp không phải lúc nào cũng lỗi; workload có thể giảm. So sánh với arrival rate và business schedule.

### 30.3. Error alert

SQL connection errors vượt ngưỡng, deadlocks tăng nhanh, statement timeout tăng, archive failures liên tiếp, backup job thất bại hoặc HA manager mất quorum.

### 30.4. Resource alert

Disk time-to-full dưới ngưỡng, memory pressure/swap/OOM, I/O latency và queue tăng, connection pool gần saturation hoặc replication slot retained WAL vượt budget.

### 30.5. Alert phải có duration

Một spike 10 giây có thể không cần page người trực. Một tình trạng kéo dài 10 phút có thể cần escalation. Dùng pending duration theo failure mode.

### 30.6. Warning và critical

- Warning: cần theo dõi hoặc lên kế hoạch.
- Critical: user impact hoặc nguy cơ sự cố lớn cần hành động ngay.

Không tạo critical alert cho mọi metric vượt một ngưỡng tùy tiện.

---

## 31. SLO burn rate và alert nhiều cửa sổ

### 31.1. Error budget

Nếu SLO cho phép 0.1% request lỗi, error budget là phần lỗi tối đa trong cửa sổ đánh giá.

### 31.2. Burn rate

Burn rate là tốc độ tiêu thụ error budget so với tốc độ cho phép theo SLO.

### 31.3. Vì sao nhiều cửa sổ?

Một cửa sổ ngắn bắt sự cố nhanh; cửa sổ dài xác nhận ảnh hưởng đủ lớn. Kết hợp cả hai giúp giảm alert do spike thoáng qua và phát hiện outage thật.

### 31.4. Ví dụ khái niệm

Một service có SLO 99.9% trong 30 ngày. Nếu tỷ lệ lỗi hiện tại cao gấp nhiều lần mức cho phép và kéo dài qua các cửa sổ ngắn/dài, burn rate tăng nhanh và cần page.

### 31.5. Không dùng SLO cho mọi metric

SLO nên gắn với user-visible service behavior. CPU, disk queue và dead tuple thường là diagnostic/capacity indicators, không nhất thiết là SLI trực tiếp.

---

## 32. Baseline và anomaly detection

### 32.1. Baseline theo thời gian

Workload có thể khác nhau giữa giờ làm việc và ban đêm, ngày thường và cuối tuần, cuối tháng và ngày thường, batch window và interactive traffic, mùa cao điểm và thấp điểm.

### 32.2. So sánh cùng loại thời điểm

So CPU 9 giờ sáng thứ Hai với baseline của các thứ Hai tương tự có ý nghĩa hơn so với nửa đêm Chủ nhật.

### 32.3. Seasonality

Dùng lịch business jobs, ETL, backup, vacuum và maintenance để giải thích spike định kỳ.

### 32.4. Anomaly detection không thay runbook

Một anomaly score chỉ báo khác thường. Operator vẫn cần biết metric nào đổi, workload nào bị ảnh hưởng và cách xác minh.

### 32.5. Tránh tự động scale theo một metric

Tăng CPU/RAM khi latency tăng có thể không giải quyết lock contention hoặc bad query plan. Xác định bottleneck trước khi thay capacity.

---

## 33. Capacity planning từ throughput và resources

### 33.1. Growth rate

Theo dõi database size, table/index growth, WAL generation, connection growth và request rate theo tuần/tháng.

### 33.2. Headroom

Giữ capacity đủ cho workload peak, failover mode và maintenance. Một primary dùng 95% CPU bình thường có thể không còn headroom khi nhận thêm traffic sau standby failure.

### 33.3. Failover capacity

Khi một node mất, node còn lại có thể phải xử lý toàn bộ read/write load. Capacity planning phải mô phỏng degraded mode.

### 33.4. Storage forecast

Ước tính thời gian tới full từ growth rate và free space. Xét data, WAL, temp, logs, backup và archive.

### 33.5. WAL budget

WAL generation tăng do bulk load, index build, full-page images, write-heavy workload hoặc logical decoding. Dùng rate và slot retention để forecast disk.

### 33.6. Connection capacity

Ước lượng concurrent workload và pool size. Không tăng max_connections mà không xem memory per backend và query concurrency.

### 33.7. Forecast không phải guarantee

Growth có thể thay đổi do product launches, data retention và workload mix. Cập nhật forecast bằng actual measurements.

---

## 34. Cách điều tra sự cố theo bốn tín hiệu

### 34.1. Latency tăng, throughput ổn định, errors ổn định

Khả năng:
- Lock contention.
- Storage latency.
- Query plan regression.
- CPU saturation.
- Connection pool wait.

Bước đầu:
1. Xác định endpoint/query family bị ảnh hưởng.
2. Xem wait events và blockers.
3. Xem top queries, plans và buffers.
4. So sánh CPU, I/O và pool wait.

### 34.2. Latency tăng, throughput giảm, errors tăng

Khả năng:
- Database overload.
- Connection exhaustion.
- Network outage.
- Storage stall.
- Failover hoặc recovery event.

Bước đầu:
1. Xác nhận service health và primary role.
2. Kiểm tra connections, errors và waiters.
3. Kiểm tra disk/CPU/network.
4. Kiểm tra PostgreSQL logs và HA events.

### 34.3. Throughput tăng, latency ổn định, CPU tăng

Có thể là tăng trưởng bình thường. Kiểm tra headroom, queue và SLO trước khi scale.

### 34.4. Throughput tăng, latency tăng nhanh, queue tăng

Có dấu hiệu saturation. Xác định resource bottleneck, rate limit hoặc điều tiết workload.

### 34.5. CPU thấp, latency cao

Tìm waits: lock, I/O, network, connection pool hoặc external dependency. CPU thấp không loại trừ bottleneck.

### 34.6. Disk free giảm, WAL rate cao

Kiểm tra replication slots, archive failures, long-running consumers và WAL generation. Đừng xóa file pg_wal thủ công.

### 34.7. Standby lag tăng, primary query latency ổn định

Kiểm tra network, standby I/O/CPU, replay conflicts, slot retention và archive path.

---

## 35. Phiên bản PostgreSQL và statistics views

Các statistics views phát triển theo major version. Một query monitoring chạy trên PostgreSQL 13 có thể không chạy trên PostgreSQL 17 nếu cột đã đổi hoặc view được tách.

### 35.1. Xác định version

```sql
SELECT version();
SHOW server_version;
SHOW server_version_num;
```

### 35.2. Khám phá schema view

```sql
SELECT
    table_schema,
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'pg_catalog'
  AND table_name IN (
      'pg_stat_database',
      'pg_stat_bgwriter',
      'pg_stat_checkpointer',
      'pg_stat_io',
      'pg_stat_wal',
      'pg_stat_replication',
      'pg_replication_slots'
  )
ORDER BY table_name, ordinal_position;
```

Một số views có thể không tồn tại ở version cũ; truy vấn chỉ trả các cột có trong catalog.

### 35.3. pg_stat_io

Có từ PostgreSQL 16. Không giả định cluster cũ có view này.

### 35.4. Checkpoint statistics

Ở PostgreSQL 17, checkpoint stats được tách vào pg_stat_checkpointer; pg_stat_bgwriter thay đổi phạm vi/cột so với bản trước. Query exporter cần version-aware mapping.

### 35.5. pg_stat_statements

Cột timing/query fields thay đổi theo version. Dùng extension version tương thích server và kiểm tra view schema.

### 35.6. Exporter phải tương thích

Nếu dùng Prometheus exporter, kiểm tra phiên bản exporter, SQL collectors và PostgreSQL major version. Một collector lỗi có thể làm mất cả nhóm metrics.

---

## 36. Bảo mật và quyền đọc statistics

### 36.1. Statistics có thể tiết lộ workload

Query text, database names, role names, client addresses và timing có thể nhạy cảm.

### 36.2. Least privilege

Cấp quyền monitoring phù hợp. Một số view/function cần pg_monitor hoặc role tương đương theo version. Không cấp superuser chỉ để lấy metrics nếu không cần.

### 36.3. Query text

Giới hạn người có quyền xem query text. Mask literals nếu log/monitoring pipeline hỗ trợ và policy yêu cầu.

### 36.4. Network metrics

Client address và application_name có thể tiết lộ cấu trúc nội bộ. Bảo vệ dashboard và log access.

### 36.5. Retention

Giữ metrics đủ dài để trend/capacity analysis nhưng không lưu không giới hạn. Logs/traces có policy riêng do dữ liệu chi tiết hơn.

---

## 37. Công cụ thu thập và lưu trữ metrics

### 37.1. PostgreSQL native views

System statistics views là nguồn dữ liệu gốc cho nhiều database metrics. Chúng thường là counters/gauges cần scrape định kỳ.

### 37.2. Prometheus và exporter

Exporter truy vấn PostgreSQL views rồi xuất metrics cho Prometheus hoặc hệ thống tương tự. Cần chọn collectors có giá trị và giới hạn cardinality.

### 37.3. Grafana

Dashboard giúp trình bày time-series, percentiles, rates, alerts và drill-down. Dashboard phải có annotation deploy/failover/maintenance để giải thích thay đổi.

### 37.4. Centralized logs

Thu thập PostgreSQL logs và application logs để phân loại errors, SQLSTATE, slow queries và failover events.

### 37.5. Distributed tracing

Trace kết nối request ở application với database spans. Giúp biết một request chậm do pool wait, network, SQL hay external service.

### 37.6. Cloud provider metrics

Managed database có thể cung cấp CPU, memory, storage, IOPS, connections, replica lag và backup status. Hiểu cách provider định nghĩa metric trước khi so sánh với native PostgreSQL.

### 37.7. Chọn công cụ theo câu hỏi

Không cần thu thập mọi metric có thể có. Bắt đầu với SLO, failure modes và runbook; sau đó thêm metrics cần thiết để phân biệt nguyên nhân.

---

## 38. Quy trình thiết kế metric cho một workload mới

### Bước 1: Mô tả workload

Xác định read/write mix, transaction size, peak concurrency, data volume, batch/interactive schedule và replication/backup requirements.

### Bước 2: Xác định user-visible SLI

Ví dụ request latency, success rate, queue delay hoặc transaction completion.

### Bước 3: Ánh xạ sang RED

Rate, errors và duration cho service/API.

### Bước 4: Ánh xạ tài nguyên sang USE

CPU, memory, disk, network, connections, WAL, locks và worker pools.

### Bước 5: Chọn PostgreSQL views

Chọn pg_stat_activity, pg_stat_database, pg_stat_statements, replication, WAL, vacuum và I/O views theo câu hỏi.

### Bước 6: Xác định loại metric

Counter, gauge, histogram hay summary. Quyết định scrape interval, labels và retention.

### Bước 7: Tạo dashboard

Overview trước, sau đó workload/resource/replication/backup drill-down.

### Bước 8: Định nghĩa alerts

Mỗi alert cần symptom, impact, threshold/duration, owner, runbook và escalation.

### Bước 9: Kiểm thử

Tạo workload lab hoặc fault injection có kiểm soát để xác nhận metric thực sự thay đổi khi sự cố xảy ra.

### Bước 10: Rà soát định kỳ

Xóa metric không dùng, giảm cardinality và cập nhật khi version/schema thay đổi.

---

## 39. Lab 1: lấy baseline latency và throughput

Lab dùng database riêng và workload không ảnh hưởng production.

### 39.1. Lấy baseline database counters

```sql
SELECT
    datname,
    xact_commit,
    xact_rollback,
    tup_returned,
    tup_fetched,
    tup_inserted,
    tup_updated,
    tup_deleted,
    stats_reset
FROM pg_catalog.pg_stat_database
WHERE datname = current_database();
```

### 39.2. Lấy snapshot thứ hai

Sau một khoảng thời gian đã định, chạy lại query. Tính delta commit/rollback và chia cho số giây.

### 39.3. Lấy query statistics

Nếu pg_stat_statements đã được bật:

```sql
SELECT
    queryid,
    calls,
    mean_exec_time,
    total_exec_time,
    rows,
    left(query, 120) AS query_sample
FROM pg_catalog.pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 10;
```

### 39.4. Đo application latency

Gửi một workload nhỏ từ ứng dụng hoặc benchmark tool và ghi histogram duration. Không dùng database average thay application latency.

### 39.5. Ghi baseline

Lưu timestamp, version, workload size, concurrency, CPU, disk latency, connections và query mix.

---

## 40. Lab 2: quan sát lock wait và error metrics

### 40.1. Mở transaction thứ nhất

```sql
BEGIN;
UPDATE public.monitoring_lab
SET value = value + 1
WHERE id = 1;
-- Giữ transaction mở trong lab.
```

### 40.2. Session thứ hai

Thử update cùng row và quan sát query chờ lock. Chỉ thực hiện trong database lab.

### 40.3. Quan sát wait events

```sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    pg_blocking_pids(pid) AS blockers
FROM pg_catalog.pg_stat_activity
WHERE state <> 'idle';
```

### 40.4. Kết thúc transaction

Commit hoặc rollback transaction giữ lock và quan sát blocked query tiếp tục.

### 40.5. Deadlock

Tạo hai transactions khóa hai rows theo thứ tự ngược nhau trong lab để quan sát deadlock. Đọc SQLSTATE/logs và deadlocks counter.

### 40.6. Kết luận

Phân biệt query execution time, lock wait time, statement timeout và deadlock error.

---

## 41. Lab 3: quan sát I/O và temporary files

### 41.1. Lấy database temp counters

```sql
SELECT
    datname,
    temp_files,
    temp_bytes,
    blks_read,
    blks_hit,
    stats_reset
FROM pg_catalog.pg_stat_database
WHERE datname = current_database();
```

### 41.2. Tạo workload sort lớn trong lab

Dùng bảng lab đủ lớn để tạo sort/hash workload. Có thể thử EXPLAIN (ANALYZE, BUFFERS) trong môi trường riêng.

### 41.3. Quan sát counters delta

Lấy snapshot trước/sau và tính temp bytes/file delta.

### 41.4. Kiểm tra pg_stat_io

Nếu PostgreSQL 16 trở lên:

```sql
SELECT *
FROM pg_catalog.pg_stat_io;
```

### 41.5. So sánh OS metrics

Theo dõi disk throughput, IOPS, latency và queue depth. Đối chiếu với PostgreSQL query activity.

### 41.6. Kết luận

Xác định workload spill, I/O bottleneck và vì sao cache hit ratio đơn lẻ không đủ.

---

## 42. Lab 4: replication lag và WAL throughput

Lab cần primary và standby riêng.

### 42.1. Primary snapshot

```sql
SELECT
    application_name,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_catalog.pg_stat_replication;
```

### 42.2. Standby snapshot

```sql
SELECT
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn(),
    pg_last_xact_replay_timestamp();
```

### 42.3. Tạo workload có kiểm soát

Ghi batch rows trong lab. Theo dõi wal_bytes delta và replication LSN progression.

### 42.4. Tạo replay delay có chủ đích

Chỉ trong lab, dùng một read workload hoặc cấu hình delayed apply đã hiểu rõ. Quan sát receive và replay tách nhau.

### 42.5. Kiểm tra slot retention

```sql
SELECT *
FROM pg_catalog.pg_replication_slots;
```

### 42.6. Kết luận

Phân biệt WAL generation rate, network throughput, flush lag, replay lag và retained WAL.

---

## 43. Lab 5: thiết kế dashboard và alert

### 43.1. Chọn một service SLO

Ví dụ p95 request latency dưới 150 ms và error rate dưới 0.5% trong cửa sổ đo đã thống nhất.

### 43.2. Chọn RED metrics

Rate, errors, duration theo endpoint/operation class.

### 43.3. Chọn USE metrics

CPU, memory pressure, disk latency, free space, connection pool waiters và network errors.

### 43.4. Chọn PostgreSQL metrics

pg_stat_activity, pg_stat_database, pg_stat_statements, replication, WAL, slots, archiver và vacuum.

### 43.5. Xây dashboard hierarchy

Overview → workload → latency/waits → resources → replication/backup.

### 43.6. Viết alert

Mỗi alert ghi tên và triệu chứng, threshold và duration, user impact, runbook link, owner/escalation và cách xác nhận hết sự cố.

### 43.7. Test alert

Tạo tải/lock wait/replication delay trong lab. Xác nhận alert bật đúng và không gây false page khi workload idle.

---

## 44. Bài tập thực hành

### Bài 1 — Metric taxonomy

Phân biệt metric, log, trace, event và profile bằng ví dụ PostgreSQL.

### Bài 2 — RED

Thiết kế ba nhóm RED metrics cho một API sử dụng PostgreSQL.

### Bài 3 — USE

Lập bảng utilization, saturation và errors cho CPU, memory, disk, network và connections.

### Bài 4 — Latency layers

Phân biệt application latency, pool wait, query latency, transaction latency và commit latency.

### Bài 5 — Percentiles

Một service có p50 10 ms, p95 100 ms và p99 2 giây. Giải thích tại sao average không đủ.

### Bài 6 — Histogram

Vì sao histogram phù hợp để aggregate latency từ nhiều application instances hơn quantile summary tại từng instance?

### Bài 7 — SLO

Viết SLO cho read API và write API. Nêu scope, percentile, window và error classification.

### Bài 8 — Throughput

Tính transactions/s từ hai snapshots pg_stat_database và xử lý trường hợp stats_reset thay đổi.

### Bài 9 — WAL rate

Tính WAL bytes/s từ pg_stat_wal. Nêu tác động tới archive, replication và disk.

### Bài 10 — Counter và gauge

Phân loại 12 metrics: deadlocks, active sessions, disk free, wal_bytes, temp_bytes, replication lag bytes, xact_commit, CPU usage, archive failures, slot retained bytes, p95 latency và pool waiters.

### Bài 11 — Error rate

Định nghĩa error rate cho SQL statements và cho HTTP requests. Vì sao không trộn hai mẫu số?

### Bài 12 — SQLSTATE

Phân loại connection exception, constraint violation, transaction rollback và insufficient resources theo SQLSTATE class.

### Bài 13 — Lock waits

Viết query tìm blocked sessions và blocking PIDs. Giải thích khác biệt giữa lock wait và deadlock.

### Bài 14 — pg_stat_statements

Tìm top 10 query theo total execution time và giải thích vì sao calls/mean/total cần xem cùng nhau.

### Bài 15 — Database stats

Tính cache hit ratio và nêu ít nhất ba lý do tỷ lệ đó có thể gây hiểu nhầm.

### Bài 16 — Connection pool

Pool wait tăng nhưng query latency ổn định. Đề xuất các chỉ số và bước điều tra.

### Bài 17 — CPU

CPU tổng 35% nhưng p99 query latency tăng. Những nguyên nhân nào vẫn có thể xảy ra?

### Bài 18 — Memory

Giải thích vì sao cộng RSS của các PostgreSQL backend có thể đếm shared memory nhiều lần.

### Bài 19 — Disk

Disk free còn 40% nhưng query latency tăng. Những I/O metrics nào cần xem?

### Bài 20 — Checkpoint

Giải thích checkpoint write/sync time và sự khác biệt statistics views trước/sau PostgreSQL 17.

### Bài 21 — pg_stat_io

Nêu phiên bản hỗ trợ pg_stat_io và vì sao cần kết hợp OS metrics.

### Bài 22 — Vacuum

n_dead_tup tăng và transaction lâu tồn tại. Thiết kế quy trình điều tra vacuum lag.

### Bài 23 — Index

Một index có idx_scan thấp. Vì sao chưa đủ bằng chứng để drop?

### Bài 24 — Replication

Phân biệt sent/write/flush/replay LSN và thiết kế alert cho từng loại lag.

### Bài 25 — Backup

Thiết kế dashboard backup freshness, archive failures, WAL continuity và restore drill age.

### Bài 26 — Wait events

Giải thích lock, IO, Client, LWLock và IPC waits. Nêu cách kết hợp với CPU/I/O metrics.

### Bài 27 — Progress views

Chọn progress view cho VACUUM, CREATE INDEX, COPY và BASE BACKUP.

### Bài 28 — Cardinality

Vì sao không dùng user ID, request ID hoặc full SQL làm metric labels?

### Bài 29 — Alert quality

Một alert CPU > 80% trong 10 giây gây nhiều false positives. Thiết kế lại alert theo saturation và user impact.

### Bài 30 — SLO burn rate

Giải thích error budget và burn rate. Vì sao dùng nhiều cửa sổ thời gian?

### Bài 31 — Baseline

Thiết kế baseline cho workload có batch ban đêm và peak traffic đầu tháng.

### Bài 32 — Capacity

Database size tăng 8% mỗi tháng. Lập forecast storage và nêu các yếu tố cần tính thêm.

### Bài 33 — Latency tăng, CPU thấp

Viết trình tự điều tra lock, I/O, pool wait và external dependency.

### Bài 34 — Throughput tăng, latency tăng

Xác định khi nào đây là tăng trưởng bình thường và khi nào là saturation.

### Bài 35 — Replication lag

Standby receive LSN tiến nhưng replay LSN đứng. Chọn metrics và logs để xác định bottleneck.

### Bài 36 — Stats reset

Một exporter tính rate âm sau restart PostgreSQL. Giải thích nguyên nhân và cách xử lý counter reset.

### Bài 37 — Version compatibility

Viết quy trình khám phá columns của pg_stat_bgwriter, pg_stat_checkpointer và pg_stat_io trước khi triển khai exporter.

### Bài 38 — Monitoring permissions

Thiết kế role monitoring có quyền tối thiểu và kiểm soát truy cập query text.

### Bài 39 — Dashboard

Vẽ dashboard hierarchy cho một cluster gồm primary, hai standby, backup repository và API services.

### Bài 40 — End-to-end incident

Sau deploy, p99 API latency tăng gấp 5, throughput giảm 20%, error rate tăng, CPU 45%, disk latency tăng và standby replay lag tăng. Xây dựng trình tự điều tra, metric cần xem, giả thuyết và điều kiện kết thúc incident.

---

## 45. Checklist chọn chỉ số và vận hành

| Nhóm | Chỉ số cần cân nhắc | Câu hỏi |
| --- | --- | --- |
| Latency | Request p50/p95/p99 | Người dùng có chờ lâu? |
| Latency | Query/transaction duration | Workload nào chậm? |
| Latency | Pool acquisition wait | Có thiếu connection? |
| Latency | Lock wait duration | Ai đang block? |
| Latency | Commit/WAL flush time | Commit có chờ storage/standby? |
| Latency | Storage I/O latency | Disk có chậm? |
| Throughput | Requests/s | Incoming load thay đổi? |
| Throughput | xact_commit/xact_rollback rate | Transaction rate ra sao? |
| Throughput | Query calls/s | Query workload tăng? |
| Throughput | Rows inserted/updated/deleted | Write volume ra sao? |
| Throughput | wal_bytes/s | WAL generation tăng? |
| Throughput | IOPS/bytes/s | Storage workload ra sao? |
| Errors | SQLSTATE/error rate | Loại lỗi nào tăng? |
| Errors | Deadlocks | Transaction conflict? |
| Errors | Statement/lock timeout | Có quá tải/chờ lâu? |
| Errors | Connection failures | Pool/network/auth? |
| Errors | Archive failures | PITR chain có nguy cơ? |
| Errors | Backup/restore failures | Recoverability có được bảo đảm? |
| Resources | CPU per core/run queue | CPU saturation? |
| Resources | Memory/swap/OOM | Memory pressure? |
| Resources | Disk free/time to full | Sắp hết dung lượng? |
| Resources | I/O queue/latency | Storage saturation? |
| Resources | Network drops/retransmits | Network bottleneck? |
| Resources | Active/max connections | Backend capacity? |
| Resources | Pool waiters | Pool saturation? |
| Resources | Slot retained WAL | WAL retention pressure? |
| Resources | Dead tuples/XID age | Vacuum có theo kịp? |
| Replication | Sent/write/flush/replay LSN | Chậm ở giai đoạn nào? |
| Replication | Sync state/timeline | Standby có đủ điều kiện? |
| Backup | Backup age/WAL continuity | Có thể restore tới đâu? |
| HA | Leader/quorum/fencing | Failover có an toàn? |
| Service | Availability/error budget | SLO có đạt? |

## Kết luận

Chọn metric hiệu quả bắt đầu từ câu hỏi vận hành và tác động tới người dùng. RED giúp quan sát rate, errors và duration của dịch vụ; USE giúp tìm utilization, saturation và errors của từng tài nguyên. Với PostgreSQL, cần kết hợp statistics views, logs, application metrics, OS/cloud metrics và tracing để hiểu nguyên nhân.

Những nguyên tắc cần nhớ:

1. **Latency phải có percentile và scope.** p50 mô tả phần giữa, p95/p99 làm lộ tail latency; đo cả request boundary và database layer.
2. **Throughput phải được tính theo thời gian.** Counter tích lũy cần delta/rate và phải xử lý stats reset.
3. **Errors cần được phân loại.** SQLSTATE, deadlock, timeout, connection, replication và archive failures có nguyên nhân/hành động khác nhau.
4. **Resources cần cả utilization lẫn saturation.** CPU thấp không loại trừ lock, I/O hoặc pool bottleneck.
5. **Wait events giải thích thời gian không dùng CPU.** Kết hợp pg_stat_activity với blockers, logs và host metrics.
6. **pg_stat_statements giúp tìm query families.** Xem calls, total time, mean time, rows và buffer/temp activity cùng nhau.
7. **Replication và backup cần metrics riêng.** Theo dõi receive/replay lag, slot retention, archive continuity, backup freshness và restore test.
8. **Metric type quyết định cách tính.** Counter cần rate; gauge cần đọc giá trị hiện tại; histogram dùng để hiểu phân phối.
9. **Cardinality phải được kiểm soát.** Đưa request/user identifiers và raw SQL vào logs/traces khi cần, không đưa thành labels không giới hạn.
10. **Alert phải dẫn tới hành động.** Mỗi alert có impact, duration, owner, runbook và điều kiện clear.
11. **SLO phải phản ánh trải nghiệm người dùng.** Database metrics là tín hiệu chẩn đoán; không thay application SLI.
12. **Baseline phải xét seasonality.** So sánh cùng workload window và ghi annotation deploy/maintenance/failover.
13. **Capacity planning cần headroom cho degraded mode.** Sau failover, node còn lại có thể phải gánh toàn bộ workload.
14. **Statistics views phụ thuộc version.** Đặc biệt chú ý pg_stat_io và sự thay đổi checkpoint stats ở PostgreSQL 17.
15. **Restore và failover drills xác nhận khả năng thực tế.** Metrics chỉ hữu ích khi dẫn tới một quy trình có thể kiểm chứng.

Một hệ thống giám sát tốt không phải hệ thống có nhiều biểu đồ nhất. Đó là hệ thống giúp người vận hành nhận ra người dùng đang bị ảnh hưởng ở đâu, workload nào thay đổi, tài nguyên nào đang bão hòa, dữ liệu có còn an toàn và hành động tiếp theo cần làm là gì.
# Chọn chỉ số giám sát PostgreSQL theo độ trễ, thông lượng, lỗi và tài nguyên

## 1. Vì sao phải chọn metric theo câu hỏi vận hành?

Một hệ thống PostgreSQL có thể xuất ra hàng trăm counters, gauges và timing values. Thu thập tất cả không tự động tạo ra khả năng quan sát tốt. Một dashboard có nhiều đường biểu diễn nhưng không chỉ ra người dùng đang bị ảnh hưởng ra sao, request chậm ở đâu hoặc tài nguyên nào sắp cạn thì rất khó dùng khi xử lý incident.

Cách chọn metric hiệu quả bắt đầu từ câu hỏi cần trả lời:

- **Latency:** Một thao tác mất bao lâu? Người dùng đang chờ bao lâu?
- **Throughput:** Hệ thống xử lý được bao nhiêu công việc trong một đơn vị thời gian?
- **Errors:** Bao nhiêu thao tác thất bại, bị timeout, rollback hoặc trả kết quả sai?
- **Saturation/resources:** Tài nguyên nào đang gần giới hạn và hàng đợi nào đang tích tụ?

Bốn nhóm này bổ sung cho nhau. Latency tăng có thể do CPU bão hòa, storage chậm, lock contention hoặc connection pool queue. Throughput giảm có thể là hậu quả của lỗi, thiếu tài nguyên hoặc traffic giảm. Error rate tăng có thể xuất hiện trước khi latency tăng. Resource utilization cao không nhất thiết là sự cố nếu hệ thống vẫn có headroom và đáp ứng SLO.

```text
                 USER / APPLICATION SLO
                          |
                          v
                 Latency + Errors
                          |
                          v
                    Throughput
                          |
                          v
               Saturation / Resources
                          |
                          v
             Diagnose bottleneck and impact
                          |
                          v
                 Actionable alert / fix
```

Bài học này trình bày cách chọn một tập metric vừa đủ, hiểu nguồn dữ liệu PostgreSQL, xây dashboard theo mục đích và thiết kế cảnh báo có thể dẫn tới hành động cụ thể.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt metric, log, trace và event.
2. Áp dụng RED và USE để chọn chỉ số.
3. Định nghĩa latency, throughput, error rate và saturation.
4. Chọn metric theo endpoint, transaction và workload class.
5. Đọc các PostgreSQL statistics views quan trọng.
6. Dùng pg_stat_statements để tìm query tiêu tốn thời gian.
7. Đo percentile latency bằng application instrumentation.
8. Tính rates từ cumulative counters bằng delta.
9. Phân biệt active connections, idle sessions và lock waits.
10. Theo dõi CPU, memory, disk I/O, WAL, checkpoints và temporary files.
11. Giám sát autovacuum, dead tuples và transaction ID age.
12. Giám sát replication, archive và connection pool.
13. Xây SLI/SLO, alert threshold và burn-rate alerts.
14. Tránh false positives, metric cardinality cao và dashboard quá tải.
15. Xây runbook từ metric tới nguyên nhân và hành động.

---

## 2. Bốn nhóm tín hiệu chính

| Nhóm | Câu hỏi | Ví dụ metric | Đơn vị |
|---|---|---|---|
| Latency | Mất bao lâu? | Query duration, transaction duration, lock wait | ms, s |
| Throughput | Xử lý bao nhiêu? | Transactions/s, queries/s, WAL bytes/s | count/s, bytes/s |
| Errors | Bao nhiêu thao tác lỗi? | SQL errors, deadlocks, failed connections, rollbacks | count/s, % |
| Saturation/resources | Gần giới hạn nào? | CPU, memory, disk latency, connection usage, queue depth | %, bytes, ms, count |

### 2.1. Latency phản ánh trải nghiệm

Người dùng quan tâm request hoàn thành nhanh hay chậm. Database query time là một thành phần của request time, nhưng request còn có application processing, network, queueing và external dependencies.

### 2.2. Throughput cho biết tải và năng lực xử lý

TPS tăng có thể là traffic tăng hoặc batch chạy. TPS giảm có thể là traffic giảm hoặc database bị nghẽn. Phải đặt throughput cạnh latency và errors để diễn giải.

### 2.3. Errors cho biết chất lượng xử lý

Không chỉ đếm SQL syntax errors. Cần theo dõi transaction rollback, deadlocks, connection failures, statement cancellations, timeouts và application-level failures.

### 2.4. Saturation cho biết hệ thống còn headroom không

CPU 90% có thể bình thường trong một workload tối ưu, nhưng nếu run queue, latency và queue depth cùng tăng thì có thể sắp bão hòa. Một metric utilization đơn lẻ hiếm khi đủ.

## 3. RED và USE: hai cách chọn metric

**RED** thường dùng cho request/service:

- Rate: số request hoặc operation mỗi giây.
- Errors: số hoặc tỷ lệ request lỗi.
- Duration: thời gian xử lý request.

**USE** thường dùng cho resource:

- Utilization: phần thời gian/tài nguyên đang được dùng.
- Saturation: mức hàng đợi hoặc công việc phải chờ.
- Errors: lỗi của resource như disk/network errors.

### 3.1. RED cho PostgreSQL endpoint

Ví dụ endpoint tìm đơn hàng:
- Rate: SELECT operations/s.
- Errors: timeout, SQLSTATE errors, failed requests.
- Duration: p50, p95, p99 response/query latency.

### 3.2. USE cho storage

- Utilization: disk throughput/IOPS so với giới hạn.
- Saturation: queue depth, I/O wait, pending operations.
- Errors: I/O errors, filesystem errors, volume throttling.

### 3.3. Kết hợp cả hai

RED cho biết user-facing symptom. USE giúp tìm resource bottleneck. PostgreSQL metrics cung cấp context về queries, locks, WAL, vacuum và replication.

### 3.4. Không áp dụng máy móc

Một database cluster có nhiều workload. Chọn metric theo service tier, business operation và resource path đang điều tra.

## 4. Bắt đầu từ SLI và SLO

Trước khi chọn alert threshold, xác định service-level indicator (SLI) và objective (SLO).

Ví dụ:
- SLI latency: tỷ lệ request đọc hoàn thành trong 200 ms.
- SLI availability: tỷ lệ request hợp lệ nhận kết quả thành công.
- SLI freshness: độ trễ dữ liệu standby so với primary.
- SLI transaction success: tỷ lệ business transactions commit thành công.

SLO ví dụ:
- 99% request đọc hoàn thành dưới 200 ms trong rolling 30 ngày.
- 99,9% transaction ghi thành công trong rolling 30 ngày.
- Standby replay lag dưới 5 giây trong 99% thời gian có write activity.

Đây chỉ là ví dụ minh họa. Mục tiêu phải phù hợp với business impact và architecture.

### 4.1. Metric kỹ thuật không tự là SLO

CPU utilization 85% không phải business SLO. Nó là một tín hiệu hỗ trợ chẩn đoán hoặc capacity planning.

### 4.2. Chọn đúng population

SLO phải xác định request nào được tính, thời gian nào được tính, cách xử lý retry và các loại lỗi nào bị loại trừ.

### 4.3. Đo ở đúng boundary

Nếu SLO là API latency, đo ở application/API boundary. Query duration ở PostgreSQL giúp chẩn đoán nhưng không thay thế end-to-end measurement.

## 5. Chọn latency metric

Latency nên được đo ở nhiều tầng:

| Tầng | Metric | Ý nghĩa |
|---|---|---|
| API | End-to-end request duration | Người dùng chờ bao lâu |
| Pool | Acquire/wait duration | Chờ lấy connection |
| Database | Query execution duration | Query chạy bao lâu |
| Transaction | Transaction duration | Bao lâu từ BEGIN tới COMMIT/ROLLBACK |
| Lock | Lock wait duration | Chờ lock bao lâu |
| Storage | Read/write/fsync latency | I/O mất bao lâu |
| Replication | Commit/replica apply delay | Chờ đồng bộ tới standby |

### 5.1. p50, p95, p99

- p50: median, một nửa observations nhanh hơn.
- p95: 95% observations không vượt giá trị này.
- p99: phản ánh tail latency của 1% observations chậm nhất.

Mean có thể che các request cực chậm. Theo dõi percentiles cùng request count/sample size.

### 5.2. Percentile cần histogram hoặc raw observations

Không thể tính chính xác p95 từ một mean hoặc từ tổng thời gian và số calls. Cần application/APM histogram, metrics histogram hoặc lưu observations đủ để tính percentile.

### 5.3. Tránh chỉ theo dõi p99 khi volume thấp

Nếu một endpoint chỉ có vài request mỗi phút, p99 có thể biến động mạnh. Xem sample count, rolling window và p95/maximum cùng context.

### 5.4. Đo cả queue time

Một query có execution time 5 ms nhưng request chờ connection pool 500 ms vẫn tạo latency lớn. Tách pool wait, network, query và application time.

## 6. Đo query latency bằng pg_stat_statements

Extension pg_stat_statements thu thập thống kê planning/execution của các query đã được chuẩn hóa theo query identity.

Khởi tạo extension cần cấu hình shared_preload_libraries và restart server nếu chưa được preload, sau đó tạo extension trong database theo hướng dẫn của version.

```sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
```

Query ví dụ:

```sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_written
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

### 6.1. total_exec_time

Tổng thời gian thực thi tích lũy của query entry kể từ lần stats reset. Query có total lớn có thể do chạy thường xuyên, chạy rất lâu hoặc cả hai.

### 6.2. mean_exec_time

Thời gian trung bình mỗi lần thực thi. Mean không thể hiện tail latency và có thể bị che bởi distribution lệch.

### 6.3. calls

Số lần query được thực thi. Kết hợp calls với mean/total để hiểu query đắt do frequency hay do mỗi lần chạy.

### 6.4. Query identity

queryid giúp gom các lần thực thi tương tự. Không dùng query text chứa literal/user input làm label metrics có cardinality cao.

### 6.5. Version và configuration

Các cột như planning statistics, WAL statistics và fields chi tiết có thể thay đổi theo PostgreSQL/extension version. Kiểm tra schema thực tế của pg_stat_statements trước khi dùng query dashboard.

## 7. pg_stat_statements không cung cấp p95 query latency

Một hiểu lầm phổ biến là mean_exec_time có thể dùng thay p95. Điều đó sai.

Ví dụ:
- Query A chạy 100 lần, 99 lần mất 5 ms, 1 lần mất 2 giây.
- Mean có thể không phản ánh đúng cảm nhận tail của request.
- p95/p99 cần histogram hoặc từng observation.

### 7.1. Lấy percentile ở application

Instrument database client/ORM để ghi histogram duration theo operation/query class. Dùng metric labels giới hạn như service, operation, database và outcome.

### 7.2. Dùng logs có chọn lọc

log_min_duration_statement có thể ghi query vượt ngưỡng. Cân nhắc log volume, parameter exposure và overhead. Không log toàn bộ statements lâu dài nếu không cần.

### 7.3. auto_explain

auto_explain có thể ghi execution plans cho queries chậm, hữu ích khi cần plan evidence. Cấu hình logging/timing/buffers có overhead; bật có mục tiêu và theo policy.

### 7.4. Query plan và duration

Một query có duration tăng có thể do plan đổi, row estimate sai, cache state khác hoặc I/O. Kết hợp EXPLAIN (ANALYZE, BUFFERS) trên môi trường phù hợp và dữ liệu đại diện.

## 8. Transaction latency và long-running transactions

Query riêng lẻ không phản ánh hết transaction duration. Một transaction có thể chạy nhiều câu lệnh và giữ locks/snapshot trong thời gian dài.

Truy vấn active sessions:

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - xact_start AS transaction_age,
    now() - query_start AS query_age,
    left(query, 300) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

### 8.1. idle in transaction

Session ở trạng thái idle in transaction có transaction mở nhưng không chạy query. Nó có thể giữ locks, snapshot và ngăn vacuum cleanup.

### 8.2. Query age khác transaction age

Một query có thể chạy 20 ms trong transaction đã mở 30 phút. Theo dõi cả hai.

### 8.3. Application name

Đặt application_name có ý nghĩa cho từng service/worker để phân biệt workload. Tránh nhét user ID/request ID riêng lẻ vào application_name.

### 8.4. Transaction duration phải theo workload

OLTP transaction thường ngắn; reporting/maintenance transaction có thể dài có chủ đích. Alert theo class và business policy.

## 9. Lock wait latency

Lock contention có thể làm query chậm dù CPU và storage còn rảnh.

Một truy vấn xem sessions đang chờ lock:

```sql
SELECT
    pid,
    usename,
    application_name,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    pg_blocking_pids(pid) AS blocking_pids,
    left(query, 250) AS query_sample
FROM pg_stat_activity
WHERE wait_event_type = 'Lock'
ORDER BY query_start;
```

### 9.1. Blocking query

Dùng pg_blocking_pids để tìm PID đang block session. Tiếp tục truy vấn blocker trong pg_stat_activity.

### 9.2. Lock wait time

Application/APM có thể đo wait duration theo request. PostgreSQL có thể cho biết session đang chờ tại thời điểm scrape; không phải mọi wait event đều có cumulative duration dễ dùng.

### 9.3. Deadlock khác lock wait

Lock wait có thể kết thúc bình thường khi blocker commit. Deadlock là chu trình chờ; PostgreSQL phát hiện và abort một transaction.

### 9.4. Alert theo tuổi và impact

Một lock wait 100 ms có thể bình thường; một blocker giữ hàng nghìn requests trong 30 giây là incident. Theo dõi số sessions bị block, blocker age và affected workload.

## 10. Chọn throughput metric

Throughput đo lượng công việc hoàn tất trong một đơn vị thời gian.

Các metric thường dùng:
- Transactions committed/s.
- Transactions rolled back/s.
- Queries/calls per second.
- Rows returned/changed per second.
- WAL bytes generated/s.
- Connections opened/s.
- Replication bytes/s.
- Background job completions/s.

### 10.1. TPS từ database counters

pg_stat_database có counters xact_commit và xact_rollback theo database.

```sql
SELECT
    datname,
    xact_commit,
    xact_rollback,
    stats_reset
FROM pg_stat_database
ORDER BY datname;
```

Đây là counters tích lũy, không phải TPS tức thời.

### 10.2. Tính TPS từ delta

Lấy hai samples cách nhau một khoảng thời gian:

```text
TPS = (commits_2 - commits_1
       + rollbacks_2 - rollbacks_1)
      / elapsed_seconds
```

Nếu muốn successful commit throughput, chỉ dùng delta xact_commit. Ghi rõ định nghĩa metric.

### 10.3. Không tính rate từ counter nếu stats reset

Nếu counter giảm vì stats reset, server restart hoặc database drop/recreate, delta âm không phải throughput âm. Reset baseline và bắt đầu window mới.

### 10.4. TPS không phải business throughput

Một transaction có thể tạo một order hoặc cập nhật hàng nghìn rows. Nếu business quan tâm orders/minute, đo business event ở application.

## 11. Queries per second và calls

pg_stat_statements.calls là counter theo query entry. Lấy delta theo thời gian để tính calls/s.

Không cộng calls của mọi query rồi gọi đó là user requests/s: một API request có thể chạy nhiều SQL statements, retries và background queries.

### 11.1. Theo query class

Nhóm query theo operation/queryid hoặc application service để tìm workload tạo tải.

### 11.2. Read/write throughput

Có thể xem rows returned/changed và block activity, nhưng cần cẩn trọng vì một query có thể trả 0 rows hoặc scan nhiều rows.

### 11.3. Batch workload

Một job có thể tạo throughput rất cao trong thời gian ngắn. Gắn workload label và schedule để dashboard không hiểu batch spike là traffic bất thường.

## 12. WAL throughput

WAL generation rate là tín hiệu quan trọng cho write workload, replication capacity và archive storage.

Ở các PostgreSQL versions có pg_stat_wal:

```sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full,
    stats_reset
FROM pg_stat_wal;
```

Tính WAL bytes/s từ delta wal_bytes chia elapsed time.

### 12.1. WAL bytes không bằng data bytes

Một UPDATE nhỏ có thể tạo WAL lớn do indexes, full-page images và page changes. WAL rate không trực tiếp là database growth rate.

### 12.2. WAL burst

Bulk loads, index builds, mass updates và checkpoint-related full-page images có thể tạo burst. Đo peak và duration, không chỉ daily average.

### 12.3. WAL buffers full

Counter wal_buffers_full có thể giúp nhận diện WAL buffer pressure theo version. Đọc delta và kết hợp workload; không kết luận chỉ từ tổng counter.

### 12.4. Archive/replication capacity

WAL throughput cao làm tăng yêu cầu network, archive throughput, standby replay và storage retention. Theo dõi các đường này cùng nhau.

## 13. Error metrics: đếm đúng lỗi

Một error dashboard tốt phân biệt:
- Application request failures.
- SQL statement errors.
- Transaction rollbacks.
- Deadlocks.
- Lock timeouts.
- Statement timeouts/cancellations.
- Failed connections/authentication.
- Replication apply/archive errors.
- Storage/network errors.

### 13.1. Error rate

```text
Error rate (%) = failed operations / total operations * 100
```

Định nghĩa failed operation rõ ràng và dùng cùng population với success rate.

### 13.2. Rollback không phải lúc nào cũng là lỗi

Ứng dụng có thể rollback có chủ đích do validation/business rule. Phân loại expected rollback và unexpected failure.

### 13.3. SQLSTATE

PostgreSQL error codes có thể nhóm theo class. Thu thập SQLSTATE từ driver/logs để phân biệt unique violation, serialization failure, deadlock, connection exception và timeout.

### 13.4. Error count cần volume context

10 errors/phút trên 100 requests là khác 10 errors/phút trên 1 triệu requests. Hiển thị cả absolute count và rate/percentage.

## 14. Deadlocks và conflicts

pg_stat_database có counters như deadlocks và conflicts (conflicts chủ yếu liên quan standby recovery conflicts theo database stats).

```sql
SELECT
    datname,
    deadlocks,
    conflicts,
    xact_commit,
    xact_rollback,
    stats_reset
FROM pg_stat_database
ORDER BY datname;
```

### 14.1. Deadlock rate

Lấy delta deadlocks theo thời gian. Một deadlock abort một transaction; application cần retry theo policy và idempotency.

### 14.2. Recovery conflicts

Trên hot standby, conflicts có thể làm query bị cancel để replay WAL tiếp tục. Theo dõi pg_stat_database_conflicts chi tiết trên standby.

### 14.3. Lock timeout và statement timeout

Các timeout errors có thể biểu hiện latency guardrail đang hoạt động. Ghi riêng timeout type và request impact.

### 14.4. Logs bổ sung context

Counters không cho biết query/transaction cụ thể. Dùng logs với SQLSTATE, application_name, PID và timestamp để điều tra.

## 15. Connection failures và pool errors

PostgreSQL server statistics không phải nguồn đầy đủ cho mọi connection attempt thất bại. Một kết nối bị từ chối trước khi tạo backend có thể chỉ xuất hiện trong server logs, proxy hoặc application metrics.

Theo dõi:
- Connection attempts/s.
- Successful connections/s.
- Authentication failures.
- Connection refused/reset.
- Pool acquire wait.
- Pool timeout.
- Active/idle/idle-in-transaction connections.
- Pool saturation và queue length.

### 15.1. max_connections

Đây là giới hạn cấu hình backend connections, không phải mục tiêu cần sử dụng hết. Nhiều connection active đồng thời có thể làm tăng memory/CPU contention.

### 15.2. Connection pool

Theo dõi pool utilization, idle count, active count, pending waiters và acquire latency ở application/pooler layer.

### 15.3. Idle connection không giống idle in transaction

Idle session không giữ transaction mở. Idle in transaction có thể giữ snapshot/locks và cần chú ý hơn.

### 15.4. Connection churn

Tạo/hủy connection liên tục gây overhead authentication, TLS, backend startup và resource usage. Theo dõi connection rate cùng pool configuration.

## 16. Resource metrics: CPU

CPU metrics nên có:
- Host CPU utilization theo user/system/iowait/steal.
- Per-core utilization.
- Run queue/load average.
- PostgreSQL process CPU.
- Container CPU throttling nếu chạy trong container.
- Query CPU/plan evidence khi cần.

### 16.1. CPU utilization cao không tự là sự cố

Nếu latency và throughput vẫn tốt, CPU cao có thể là sử dụng hiệu quả. Quan tâm headroom, queueing và trend.

### 16.2. CPU thấp nhưng latency cao

Có thể query đang chờ lock, disk I/O, network, connection pool hoặc external dependency. CPU thấp không có nghĩa database khỏe.

### 16.3. CPU steal/throttling

VM hoặc container có thể bị giới hạn CPU dù guest utilization trông không quá cao. Theo dõi steal time/cgroup throttling.

### 16.4. Correlate với query stats

Dùng pg_stat_statements, wait events và query plans để tìm SQL tiêu tốn CPU hoặc thực hiện quá nhiều calls.

## 17. Resource metrics: memory

PostgreSQL memory gồm nhiều vùng:
- shared_buffers.
- Backend-local memory và work_mem cho sort/hash operations.
- maintenance_work_mem.
- WAL buffers.
- Memory của OS page cache.
- Extension/background process memory.
- Container/cgroup limits.

### 17.1. Không có một con số “PostgreSQL memory used” đơn giản

RSS cộng của mọi backend có thể đếm trùng shared memory. Dùng OS/cgroup metrics và hiểu memory accounting.

### 17.2. work_mem là per-operation budget

Một query có thể có nhiều sort/hash nodes, nhiều workers và nhiều concurrent sessions. Tổng memory có thể lớn hơn work_mem rất nhiều.

### 17.3. Swap pressure

Swap in/out và major page faults có thể làm latency tăng mạnh. Theo dõi host memory available, swap activity và OOM kills.

### 17.4. Shared buffers hit ratio

Hit ratio có thể là một tín hiệu nhưng không phải mục tiêu tuyệt đối. Một workload scan lớn hoặc OS page cache có thể làm diễn giải phức tạp; ưu tiên read latency, physical I/O và workload context.

## 18. Resource metrics: disk và I/O

Theo dõi:
- Free space và growth rate.
- Read/write IOPS.
- Read/write throughput.
- I/O latency.
- Queue depth.
- Filesystem errors.
- Volume throttling/credit balance nếu cloud storage có cơ chế đó.
- WAL directory usage.
- Temporary files/bytes.
- Data, index và tablespace growth.

### 18.1. Disk full là failure mode nghiêm trọng

Database có thể không ghi được WAL/data/temp files. Alert free space theo bytes và thời gian còn lại dựa trên growth rate.

### 18.2. Latency quan trọng hơn utilization đơn lẻ

Một volume đạt 100% throughput limit và latency tăng là tín hiệu saturation. Utilization cao nhưng latency thấp và có headroom khác có thể vẫn ổn.

### 18.3. Tách data và WAL

Nếu data directory và pg_wal ở volume khác nhau, giám sát từng volume. Một volume đầy có thể ảnh hưởng cluster dù volume kia còn trống.

### 18.4. Tablespaces

Theo dõi từng filesystem/mount chứa tablespaces. Dung lượng tổng host còn nhiều không có nghĩa mount riêng không đầy.

## 19. pg_stat_io cho I/O context

PostgreSQL 16 trở lên có pg_stat_io để quan sát I/O theo backend type, object và context.

```sql
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
    fsync_time,
    stats_reset
FROM pg_stat_io
ORDER BY backend_type, object, context;
```

Kiểm tra columns trên đúng version vì view có thể thay đổi.

### 19.1. Counters và timing

Reads/writes/fsyncs là counters; read_time/write_time/fsync_time có thể phụ thuộc track_io_timing. Lấy delta để tính rate và average timing.

### 19.2. track_io_timing

Setting này cho phép thu thập timing I/O ở những vị trí hỗ trợ, nhưng có overhead tùy platform/workload. Đo tác động trước khi bật rộng.

### 19.3. Không thay OS metrics

pg_stat_io cung cấp context PostgreSQL. OS/cloud volume metrics vẫn cần để thấy queue, throttling, device latency và lỗi hệ thống.

### 19.4. pg_stat_database block counters

blks_read và blks_hit có thể hỗ trợ theo dõi hoạt động block-level theo database, nhưng không phân biệt đầy đủ physical device path.

## 20. Temporary files và sort/hash spill

Khi sort/hash operation không vừa memory budget, PostgreSQL có thể ghi temporary files. Điều này làm tăng disk I/O và query latency.

```sql
SELECT
    datname,
    temp_files,
    temp_bytes,
    stats_reset
FROM pg_stat_database
ORDER BY temp_bytes DESC;
```

### 20.1. temp_bytes là counter tích lũy

Tính delta theo thời gian để xem temp write rate. Một tổng lớn từ nhiều tháng không chứng minh hiện tại đang spill nhiều.

### 20.2. Query-level temporary blocks

pg_stat_statements có thể cung cấp temp_blks_read/temp_blks_written theo version. Dùng để tìm query tạo spill nhiều.

### 20.3. work_mem tuning

Tăng work_mem có thể giảm spill nhưng làm memory usage tăng theo số operation/concurrency. Xác định query class và concurrency trước.

### 20.4. Disk headroom

Temporary files có thể làm filesystem đầy nhanh. Theo dõi free space và temp bytes/s trong batch windows.

## 21. Checkpoints và WAL

Checkpoint flushes dirty buffers và ghi checkpoint records vào WAL. Checkpoint quá thường xuyên hoặc I/O pressure có thể ảnh hưởng write latency.

Theo dõi:
- Checkpoint count và timing.
- Buffers written by checkpoints.
- Checkpoint write/sync time.
- WAL bytes generated.
- WAL files retained.
- Backend writes.
- Checkpoint warnings trong logs.

### 21.1. Version differences

Các thống kê checkpoint đã thay đổi giữa major versions. PostgreSQL 17 có pg_stat_checkpointer tách riêng một số thông tin trước đây nằm trong pg_stat_bgwriter. Dùng view/cột đúng version.

### 21.2. Không copy query từ version khác

Kiểm tra catalog view trước khi đưa query checkpoint vào dashboard. Không giả định pg_stat_bgwriter có cùng schema trên mọi version.

### 21.3. checkpoint_timeout và max_wal_size

Các setting ảnh hưởng checkpoint scheduling/volume nhưng không phải alert threshold. Tune dựa trên workload, recovery objectives và storage performance.

### 21.4. Checkpoint warning

Log cảnh báo checkpoint thường xuyên hơn dự kiến có thể cho biết WAL generation vượt dự báo hoặc max_wal_size thấp. Đọc logs cùng checkpoint stats và WAL rate.

## 22. Vacuum và bloat

Autovacuum giữ visibility map/statistics và thu hồi dead tuples có thể tái sử dụng. Vacuum chậm hoặc bị ngăn có thể làm table/index bloat tăng và transaction ID wraparound risk.

Xem table stats:

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
```

### 22.1. n_dead_tup là estimate

Đây là thống kê ước lượng, không phải số row dead chính xác tại thời điểm query.

### 22.2. Autovacuum activity

Theo dõi pg_stat_progress_vacuum và active sessions để biết vacuum đang xử lý relation nào.

### 22.3. Vacuum bị chặn

Long-running transactions, replication slots và standby feedback có thể giữ xmin horizon, ngăn cleanup. Theo dõi oldest transaction, slot xmin và vacuum progress.

### 22.4. Bloat không đo trực tiếp bằng dead tuple count

Cần extension/tool hoặc phương pháp size/visibility analysis phù hợp. Đừng gọi n_dead_tup là exact bloat bytes.

## 23. Transaction ID age và wraparound risk

Transaction ID wraparound là rủi ro cần giám sát riêng. Một database có datfrozenxid age tăng gần giới hạn có thể cần vacuum khẩn cấp; PostgreSQL có cơ chế bảo vệ để tránh wraparound.

Ví dụ truy vấn:

```sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;
```

### 23.1. XID age không phải latency metric

Đây là gauge cho độ cũ transaction ID cần freeze. Theo dõi trend và khoảng cách tới autovacuum_freeze_max_age/policy.

### 23.2. Cần phân biệt database và table

Một table có relfrozenxid cũ có thể là vấn đề dù database-level summary trông bình thường. Kiểm tra relation age theo catalog khi điều tra.

### 23.3. Alert sớm

Không chờ tới ngưỡng critical. Alert theo warning/critical thresholds phù hợp version và vận hành, kết hợp autovacuum progress và blockers.

### 23.4. Replication slots

Logical/physical slots có thể giữ xmin/catalog_xmin hoặc WAL lâu hơn, ảnh hưởng vacuum/retention. Theo dõi slot state và owner.

## 24. Connections, backends và active workload

Xem phân bố session:

```sql
SELECT
    datname,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    count(*) AS sessions
FROM pg_stat_activity
GROUP BY
    datname, usename, application_name,
    state, wait_event_type, wait_event
ORDER BY sessions DESC;
```

### 24.1. Active

Active sessions đang thực thi query hoặc ở trạng thái active. Không phải mọi active session đều dùng CPU; có thể đang chờ I/O/lock.

### 24.2. Idle

Idle session không chạy query. Pool giữ connection idle có thể bình thường nếu trong giới hạn.

### 24.3. Idle in transaction

Cần quan tâm vì transaction mở có thể giữ locks/snapshots và làm vacuum bị trì hoãn.

### 24.4. Max connections headroom

Theo dõi connections hiện tại so với max_connections, reserved slots và pool capacity. Đặt warning trước khi hết chỗ cho admin/replication.

## 25. Locks và blocking tree

Khi latency tăng, xác định blocking chain:

```sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.application_name AS blocked_app,
    now() - blocked.query_start AS blocked_for,
    blocker.pid AS blocker_pid,
    blocker.application_name AS blocker_app,
    now() - blocker.xact_start AS blocker_xact_age,
    left(blocker.query, 200) AS blocker_query
FROM pg_stat_activity AS blocked
CROSS JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) AS p(blocker_pid)
JOIN pg_stat_activity AS blocker
  ON blocker.pid = p.blocker_pid
ORDER BY blocked.query_start;
```

### 25.1. Lock count không đủ

Số lượng locks cao không tự có nghĩa contention. Quan trọng là lock waits, duration và số request bị block.

### 25.2. Blocking transaction

Transaction mở lâu có thể block nhiều sessions. Tìm root blocker thay vì chỉ nhìn session đang chờ cuối chuỗi.

### 25.3. DDL locks

Migration/ALTER TABLE có thể yêu cầu locks mạnh và chặn traffic. Theo dõi lock wait trước và trong deployment.

### 25.4. Deadlock metrics

Kết hợp deadlock counter, server logs và application retry behavior.

## 26. Replication và archive metrics

Với HA, chọn metrics theo vai trò replica:
- Connection state.
- Sent/write/flush/replay LSN.
- Byte lag và time lag.
- WAL generation/replay rate.
- Synchronous state.
- Replication slot retained WAL.
- Archive success/failure.
- Standby recovery conflicts.

Trên primary:

```sql
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
```

Archive stats:

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

### 26.1. Không dùng time lag làm actual RPO

Lag fields là tín hiệu quan sát. Actual RPO cần failover/restore evidence và acknowledged transaction markers.

### 26.2. Archive và streaming là hai đường

Standby streaming khỏe không chứng minh WAL archive khỏe. PITR readiness cần archive continuity và restore tests.

### 26.3. Slot retention

Một consumer lag có thể làm WAL giữ lại và disk tăng. Theo dõi retained distance cùng filesystem free space.

### 26.4. Read freshness

Nếu standby phục vụ reads, đo read-after-write wait/freshness theo token khi business cần.

## 27. Cache hit ratio: dùng đúng cách

Một công thức thường thấy:

```text
shared buffer hit ratio
  = blks_hit / (blks_hit + blks_read)
```

Tính từ delta counters trong một window thường có ý nghĩa hơn tổng từ lúc stats reset.

### 27.1. Không đặt mục tiêu 99% cho mọi workload

Sequential scans, data warehouse và working set lớn có thể có ratio thấp nhưng vẫn đạt performance tốt.

### 27.2. PostgreSQL shared buffers không phải toàn bộ cache

OS page cache có thể phục vụ reads sau khi PostgreSQL yêu cầu block từ filesystem. blks_read không đồng nghĩa chắc chắn thiết bị storage đã đọc physical media.

### 27.3. Latency và I/O quan trọng hơn ratio riêng lẻ

Xem query latency, pg_stat_io, OS device latency và working set.

### 27.4. Ratio tăng nhưng query vẫn chậm

Có thể CPU, locks, plan hoặc network là bottleneck. Cache hit ratio không phải SLO.

## 28. Metric types: counter, gauge và histogram

| Loại | Ý nghĩa | Ví dụ | Cách dùng |
|---|---|---|---|
| Counter | Tăng tích lũy | xact_commit, deadlocks, wal_bytes | Tính rate bằng delta |
| Gauge | Giá trị tại thời điểm | active connections, free disk, replay LSN | Theo dõi current/trend |
| Histogram | Phân phối observations | request duration buckets | Tính quantile/SLO |
| Summary | Quantile/aggregate từ instrumentation | Client latency summary | Xem giới hạn aggregation |

### 28.1. Counter reset

Counter có thể reset sau restart, stats reset hoặc object lifecycle. Exporter cần xử lý reset đúng.

### 28.2. Gauge không được cộng theo thời gian như counter

CPU utilization 70% tại hai samples không có nghĩa 140%. Dùng average/max theo window.

### 28.3. Histogram buckets

Chọn buckets quanh SLO boundaries và tail ranges. Bucket quá thưa có thể làm quantile thiếu chính xác.

### 28.4. Labels và cardinality

Dùng labels có tập giá trị giới hạn. Tránh raw SQL, user ID, order ID, request ID hoặc arbitrary tenant ID làm label.

## 29. Stats reset và cách tính rate chính xác

PostgreSQL statistics views thường chứa cumulative counters. Muốn có rate:
1. Lấy counter ở thời điểm T1.
2. Lấy counter ở T2.
3. Tính delta.
4. Chia cho elapsed time.
5. Kiểm tra stats_reset và counter reset.
6. Gắn server/database identity vào sample.

```text
rate_per_second = (counter_T2 - counter_T1)
                  / (T2 - T1)
```

### 29.1. Không lấy snapshot bằng query độc lập rồi giả định elapsed chính xác

Ghi sample timestamp từ monitoring collector và dùng monotonic time để đo duration.

### 29.2. Stats consistency

Statistics collector/cache có thể có snapshot semantics. Trong một transaction dài, stats snapshot có thể không tự cập nhật theo cách bạn kỳ vọng. Dùng transaction ngắn hoặc refresh snapshot phù hợp theo version.

### 29.3. stats_reset

Lưu stats_reset cùng metric để nhận diện reset. Sau reset, bắt đầu baseline mới.

### 29.4. Server restart

Một số counters reset khi restart hoặc có behavior phụ thuộc version. Exporter nên phân biệt restart generation.

## 30. Chọn metric theo loại workload

| Workload | Latency | Throughput | Errors | Resources |
|---|---|---|---|---|
| OLTP | p95/p99 transaction/query, lock wait | TPS, calls/s | deadlocks, timeouts, rollback | CPU, connections, I/O |
| Reporting | query duration, queue time | queries/s, rows scanned | cancellations, statement timeout | I/O, memory, temp files |
| Batch/ETL | job duration, stage duration | rows/s, WAL bytes/s | failed batches, retries | CPU, disk, WAL, temp |
| Logical subscriber | apply freshness, lag | changes/s, WAL/logical bytes | apply errors, sync errors | slot retention, CPU, disk |
| Physical standby | replay freshness | WAL receive/replay rate | disconnects, archive failures | network, disk, recovery CPU |
| Connection pool | acquire latency | checkouts/s | acquire timeout | active/idle/waiters |

### 30.1. OLTP

Ưu tiên tail latency, lock waits, transaction success và connection pool. Average TPS không đủ.

### 30.2. Reporting

Ưu tiên long query duration, I/O, temp spill, cancellations và impact lên replay/vacuum.

### 30.3. Batch

Ưu tiên job completion time, rows processed, WAL generation, checkpoint/temporary I/O và resource headroom.

### 30.4. HA/replication

Ưu tiên replay freshness, acknowledged durability, archive continuity, slot retention và failover readiness.

## 31. Workload attribution

Nếu chỉ có cluster-wide metrics, khó biết service nào tạo tải. Thu thập context:
- application_name.
- database/user.
- Query ID.
- Endpoint/operation class ở application.
- Background job name.
- Tenant tier nếu cardinality được kiểm soát.

### 31.1. application_name

Đặt tên ổn định như api-orders, worker-billing, reporting. Tránh một tên riêng cho từng request.

### 31.2. Query ID

pg_stat_statements queryid giúp gom query shape. Query text cần bảo vệ vì có thể chứa schema/table/logic nhạy cảm.

### 31.3. Tenant labels

Nếu cần tenant-level metrics, dùng bounded tiers/cohorts hoặc sampled logs. Không tạo hàng triệu time series theo tenant ID.

### 31.4. Attribution không thay isolation

Metric cho biết workload nào tạo tải; resource quotas, pool limits và workload isolation mới giúp kiểm soát ảnh hưởng.

## 32. Dashboard: tổng quan dịch vụ

Dashboard đầu tiên nên trả lời:
- Service có đang đạt SLO không?
- Request rate đang tăng hay giảm?
- p50/p95/p99 latency?
- Error rate và timeout rate?
- Throughput commit/rollback?
- Primary/standby role và health?
- CPU, memory, disk headroom?
- Connection pool utilization?
- Các alert đang firing?

### 32.1. Đặt user-facing metrics ở đầu

Không bắt người vận hành nhìn 20 panel CPU trước khi biết người dùng có bị ảnh hưởng hay không.

### 32.2. Hiển thị time range và resolution

Một dashboard 5 phút không trả lời câu hỏi trend 30 ngày. Cho phép xem ngắn/dài hạn và giữ sample resolution phù hợp.

### 32.3. Annotate deployments và incidents

Đánh dấu release, migration, failover, vacuum maintenance và config changes để correlation dễ hơn.

### 32.4. Không nhồi mọi metric vào một trang

Tách overview, query performance, locks, storage, vacuum, replication và capacity.

## 33. Dashboard: query performance

Các panel gợi ý:
1. p50/p95/p99 query/API duration.
2. Top queries theo total_exec_time.
3. Top queries theo mean_exec_time/calls.
4. Calls/s theo query class.
5. Rows và block reads/hits.
6. Temporary blocks written.
7. Planning vs execution time khi được bật.
8. Query timeouts/cancellations.
9. Lock wait duration/blockers.
10. Long-running transactions.

### 33.1. Top total time

Tìm query tiêu tốn tổng database time lớn nhất.

### 33.2. Top mean time

Tìm query chậm mỗi lần chạy, dù frequency thấp.

### 33.3. Top calls

Tìm query nhỏ nhưng bị gọi quá thường xuyên, có thể là N+1 pattern.

### 33.4. Top temp writes

Tìm query spill nhiều ra disk.

## 34. Dashboard: resources và saturation

Panel gợi ý:
- CPU user/system/iowait/steal.
- Memory available, swap, OOM, cgroup throttling.
- Disk free bytes/growth, IOPS, throughput, latency, queue depth.
- WAL bytes/s và pg_wal size.
- Temporary files/bytes/s.
- Connections active/idle/idle in transaction.
- Pool waiters/acquire latency.
- Lock waits/blocker age.
- Checkpoint timing.
- Autovacuum progress/dead tuples/XID age.
- Replication slot retention.

### 34.1. Saturation là hàng đợi

CPU 70% có thể chưa bão hòa. Nếu run queue tăng và latency tăng, có thể CPU đang trở thành bottleneck.

### 34.2. Disk headroom theo thời gian

Không chỉ xem free 100 GB. Nếu tăng 20 GB/giờ, chỉ còn 5 giờ. Tính time-to-full theo trend.

### 34.3. Memory pressure

Theo dõi swap/OOM và available memory, không chỉ PostgreSQL shared_buffers.

### 34.4. Connection saturation

Khi pool hết connection, request chờ trước khi query bắt đầu. Database query latency có thể trông thấp trong khi API latency cao.

## 35. Alerting: alert theo symptom và cause

Alert tốt thường có:
- Metric và threshold.
- Duration/window.
- Severity.
- Affected service/database.
- User impact/SLO.
- Likely cause.
- Runbook link.
- Owner/escalation.

### 35.1. Symptom alert

Ví dụ p95 API latency vượt SLO và error rate tăng. Đây là tín hiệu user impact.

### 35.2. Cause alert

Ví dụ disk free dưới 10%, replication slot retained WAL tăng nhanh hoặc XID age gần threshold. Đây là tín hiệu rủi ro kỹ thuật.

### 35.3. Không alert mọi metric ở mọi ngưỡng

Một cảnh báo không dẫn tới hành động sẽ tạo alert fatigue. Dùng dashboard cho context và alert cho tình huống cần can thiệp.

### 35.4. Duration/hysteresis

Dùng window để tránh spike ngắn. Với disk-full, connection exhaustion hoặc replication loss, có thể cần alert nhanh hơn.

## 36. Error budget và burn rate

Nếu SLO định nghĩa 99,9% success, error budget là phần lỗi được phép trong cửa sổ đo.

Burn rate cho biết tốc độ tiêu thụ error budget so với mức cho phép.

### 36.1. Fast burn

Error rate tăng mạnh trong vài phút có thể làm cạn budget nhanh; cần alert ưu tiên cao.

### 36.2. Slow burn

Một lỗi nhỏ nhưng kéo dài có thể không gây page ngay, nhưng tích lũy thành vi phạm SLO. Dùng alert theo cửa sổ dài hơn.

### 36.3. Không dùng resource utilization thay error budget

CPU 95% không tự có nghĩa SLO đã bị vi phạm. Đo trực tiếp request success/latency.

### 36.4. Exclusions phải rõ

Maintenance, synthetic checks và expected client errors cần được xử lý theo SLO policy đã công bố.

## 37. Correlation: tìm nguyên nhân từ nhiều metric

Một chuỗi điều tra mẫu:

| Triệu chứng | Metric liên quan | Hướng điều tra |
|---|---|---|
| p95 tăng, CPU tăng | CPU, query total time, plans | Query plan/CPU saturation |
| p95 tăng, CPU thấp | lock waits, I/O latency, pool wait | Lock, storage hoặc connection queue |
| TPS giảm, WAL lag tăng | WAL rate, replay rate, sender state | Replication pressure |
| Errors tăng, latency tăng | SQLSTATE, deadlocks, timeouts | Transaction failures/locks |
| Disk free giảm nhanh | temp bytes, WAL, table growth | Temp spill, slot retention, workload growth |
| Vacuum chậm, dead tuples tăng | long transactions, xmin, slots | Vacuum horizon/blockers |
| API chậm, DB query nhanh | pool wait, network, app traces | Pooling/network/application |
| Connection count cao | active/idle, pool waiters, backend CPU | Pool sizing/churn/leaked sessions |

### 37.1. Correlation không phải causation

Hai metrics tăng cùng lúc không chứng minh metric này gây metric kia. Dùng timeline, traces, query evidence và controlled changes.

### 37.2. So sánh baseline

So với cùng giờ/ngày và workload class. Traffic pattern có thể theo mùa/giờ làm việc.

### 37.3. Deployment annotations

Một query plan regression ngay sau release có thể giải thích latency spike. Giữ deploy markers trong dashboard.

### 37.4. Theo critical path

Tìm nơi request dành phần lớn thời gian: queue, network, database execution, lock, I/O hay external service.

## 38. Sampling interval và metric overhead

Sampling quá dày có thể tạo overhead; sampling quá thưa bỏ lỡ spike và khó tính percentile.

Cân nhắc:
- 5–15 giây cho alert metrics quan trọng, tùy scale.
- 30–60 giây cho nhiều resource/counter metrics.
- 1–5 phút cho capacity trends.
- Histograms ở application để thu thập latency liên tục.
- Event/log-based collection cho errors hiếm nhưng quan trọng.

Đây là khoảng tham khảo, không phải quy tắc cứng.

### 38.1. Query monitoring cũng tạo tải

Một query pg_stat_activity/pg_stat_statements định kỳ có overhead nhỏ nhưng không bằng zero. Tránh query catalog phức tạp mỗi giây trên cluster lớn.

### 38.2. Scrape timeout

Collector không được giữ connection hoặc transaction lâu. Đặt timeout và dùng role monitoring phù hợp.

### 38.3. Avoid synchronized scrapes

Nhiều exporters scrape đồng thời có thể tạo spike. Dùng jitter hoặc lịch lệch.

### 38.4. Metric cardinality

Query text, raw IDs và labels không giới hạn có thể làm monitoring backend tốn memory/storage. Chuẩn hóa query classes.

## 39. Security và privacy khi giám sát

Monitoring có thể chứa:
- SQL text.
- Table/schema names.
- User/database names.
- Client addresses.
- Error details.
- Parameter values nếu logging quá rộng.

### 39.1. Không log secrets

Không ghi passwords, tokens, personal data hoặc payload nhạy cảm vào query logs/labels.

### 39.2. Monitoring role

Dùng least privilege, ví dụ role được cấp quyền monitoring cần thiết. Không cấp superuser cho exporter chỉ để đọc stats.

### 39.3. Retention và access control

Metrics/logs có thể tiết lộ workload và business activity. Đặt retention, access policy và redaction phù hợp.

### 39.4. Query text exposure

pg_stat_statements query text có thể chứa literals tùy normalization/version/config. Giới hạn quyền và tránh export raw text không cần thiết.

## 40. Version-aware metric collection

PostgreSQL statistics views thay đổi theo major version:
- pg_stat_io xuất hiện từ PostgreSQL 16.
- Checkpoint statistics thay đổi, PostgreSQL 17 có pg_stat_checkpointer.
- pg_stat_statements fields phụ thuộc extension version và options.
- Một số columns của replication/subscription views thay đổi theo version.

### 40.1. Kiểm tra server version

```sql
SELECT version();
```

Hoặc lấy version number:

```sql
SHOW server_version_num;
```

### 40.2. Kiểm tra view columns

Có thể dùng information_schema.columns cho views phù hợp hoặc đọc catalog definitions trong pg_catalog. Xác minh exporter query trên version thực tế.

### 40.3. Dashboard nhiều major versions

Dùng exporter/version-specific queries hoặc compatibility layer. Không assume một SQL query hoạt động trên mọi cluster.

### 40.4. Đánh dấu missing metrics

Nếu version không có một metric, ghi unavailable/unsupported thay vì hiển thị 0.

## 41. Bộ metric tối thiểu theo lớp

Một baseline thực dụng:

**Service/application**
- Request rate.
- Success/error rate.
- p50/p95/p99 latency.
- Connection pool acquire wait.
- Business operation throughput.

**PostgreSQL**
- TPS commits/rollbacks.
- Top query total/mean/calls.
- Active/idle/idle-in-transaction sessions.
- Lock waits/deadlocks.
- Temporary bytes/files.
- Database size and growth.

**Host/storage**
- CPU/run queue.
- Memory available/swap/OOM.
- Disk free, latency, IOPS, throughput, queue.
- WAL filesystem usage.

**Maintenance/HA**
- Autovacuum progress/dead tuples/XID age.
- Checkpoint/WAL metrics.
- Replication positions/lag/state.
- Slot retained WAL.
- Archive success/failure.

### 41.1. Bắt đầu nhỏ

Bật một tập metric cốt lõi và mở rộng theo incident patterns. Tránh triển khai hàng trăm alerts trước khi biết chúng được ai xử lý.

### 41.2. Có owner cho mỗi alert

Alert cần owner/on-call path. Không có owner thì alert khó tạo ra hành động.

### 41.3. Có runbook cho critical alerts

Tối thiểu ghi query, cách xác minh, stop conditions, escalation và rollback/mitigation.

## 42. Ví dụ: latency tăng nhưng throughput không đổi

Tình huống:
- TPS ổn định.
- p95 query latency tăng từ 40 ms lên 900 ms.
- CPU 45%.
- Disk latency tăng.
- Lock wait không tăng.

Hướng điều tra:
1. Xem pg_stat_statements query nào tăng mean/total.
2. Xem pg_stat_io và OS disk latency.
3. Kiểm tra volume throttling/queue depth.
4. Xem temp bytes và query spill.
5. Kiểm tra checkpoint/backup workload.
6. So sánh với deployment hoặc storage change.

Không kết luận CPU là bottleneck chỉ vì database chậm.

## 43. Ví dụ: throughput giảm và errors tăng

Tình huống:
- TPS commit giảm.
- Rollback/error rate tăng.
- Deadlocks tăng.
- Active sessions có nhiều lock waits.
- CPU thấp.

Hướng điều tra:
1. Tìm blocking sessions bằng pg_blocking_pids.
2. Đọc deadlock logs.
3. Xác định transaction giữ lock lâu.
4. So sánh application deployment/transaction ordering.
5. Kiểm tra retry storm làm tăng tải.
6. Sửa transaction order/giảm lock duration và retry có backoff.

CPU thấp ở đây có thể do backend đang chờ lock, không phải thiếu traffic.

## 44. Ví dụ: disk tăng nhanh dù database size ít thay đổi

Tình huống:
- Data directory tăng.
- Table size gần như ổn định.
- pg_wal tăng.
- Replication slot inactive.
- Archive failures xuất hiện.

Hướng điều tra:
1. Kiểm tra pg_replication_slots restart_lsn và active state.
2. Xác định slot owner/consumer.
3. Xem pg_stat_archiver và logs.
4. Kiểm tra archive storage credentials/capacity.
5. Tính retained WAL distance và disk headroom.
6. Sửa consumer/archive path; chỉ drop slot khi có kế hoạch resync.

## 45. Ví dụ: API chậm nhưng PostgreSQL query nhanh

Tình huống:
- API p95 = 1,2 giây.
- Database query p95 = 20 ms.
- Pool acquire wait = 900 ms.
- Pool active connections gần giới hạn.
- Database CPU còn thấp.

Nguyên nhân có thể là pool saturation hoặc connection leak. Tăng max_connections ngay có thể làm tăng backend pressure. Điều tra pool size, request concurrency, connection lifetime và transaction leaks trước.

## 46. Checklist chọn metric cho một vấn đề

| Câu hỏi | Metric cần xem |
|---|---|
| Người dùng có bị chậm? | API p95/p99, DB query duration |
| Có bao nhiêu thao tác? | Request rate, TPS, query calls/s |
| Thao tác có thất bại? | Error rate, SQLSTATE, rollback, deadlock |
| Đang chờ connection? | Pool acquire latency, waiters |
| Đang chờ lock? | Lock wait, blocker age, blocked sessions |
| CPU có bão hòa? | CPU, run queue, throttling |
| Storage có chậm? | I/O latency, queue depth, IOPS, throughput |
| Memory có áp lực? | Available memory, swap, OOM |
| Disk sắp đầy? | Free bytes, growth rate, WAL/temp usage |
| Query spill ra disk? | temp_files/temp_bytes, temp blocks |
| Vacuum có bị chặn? | dead tuples, long transactions, xmin, slots |
| Standby có stale? | replay LSN, lag, freshness token |
| PITR archive có lỗi? | archiver counters, WAL inventory |
| Query nào tốn thời gian? | pg_stat_statements total/mean/calls |
| Query nào tail chậm? | Application/APM histogram, slow logs |

## 47. Tài liệu PostgreSQL chính thức

- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring.html) — activity statistics, views và progress reporting.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — pg_stat_database, pg_stat_activity, replication và statistics behavior.
- [pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html) — query planning/execution statistics.
- [Monitoring I/O](https://www.postgresql.org/docs/current/monitoring-stats.html) — I/O statistics và pg_stat_io.
- [Monitoring Progress](https://www.postgresql.org/docs/current/progress-reporting.html) — vacuum, analyze, copy, create index và other progress views.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html) — autovacuum, dead tuples và freezing.
- [Resource Consumption](https://www.postgresql.org/docs/current/runtime-config-resource.html) — memory, worker và resource settings.
- [WAL Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html) — WAL, checkpoint và durability settings.
- [Replication Configuration](https://www.postgresql.org/docs/current/runtime-config-replication.html) — replication slots/senders/receivers.
- [Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html) — SQLSTATE classes/codes.

Các view columns, counters và extensions có thể khác giữa PostgreSQL major versions. Dùng tài liệu đúng version, kiểm tra pg_settings/view definitions và xác nhận exporter query trên server thực tế.

## 48. Bài tập thực hành có đáp án

### Bài 1. Bốn nhóm tín hiệu chính trong bài là gì?

**Đáp án:** Latency, throughput, errors và saturation/resources.

### Bài 2. RED viết tắt của gì?

**Đáp án:** Rate, Errors, Duration.

### Bài 3. USE viết tắt của gì?

**Đáp án:** Utilization, Saturation, Errors.

### Bài 4. Vì sao cần cả RED và USE?

**Đáp án:** RED cho thấy user-facing symptoms; USE giúp tìm resource bottleneck và saturation.

### Bài 5. p95 có nghĩa gì?

**Đáp án:** 95% observations có latency không vượt giá trị p95 trong window/population được định nghĩa.

### Bài 6. Mean latency có thay thế p99 không?

**Đáp án:** Không. Mean có thể che tail latency; cần histogram/raw observations.

### Bài 7. pg_stat_statements có cung cấp p95 query latency không?

**Đáp án:** Không. Nó cung cấp aggregate statistics như calls, total/mean execution time; percentile cần instrumentation khác.

### Bài 8. Query có total_exec_time lớn có thể do đâu?

**Đáp án:** Chạy nhiều lần, mỗi lần chậm hoặc cả hai; xem calls và mean.

### Bài 9. Query có calls rất cao nhưng mean thấp có thể là gì?

**Đáp án:** N+1 pattern hoặc query nhỏ được gọi quá thường xuyên.

### Bài 10. Query age và transaction age khác gì?

**Đáp án:** Query age đo statement hiện tại; transaction age đo từ lúc transaction bắt đầu.

### Bài 11. idle in transaction nguy hiểm vì sao?

**Đáp án:** Có thể giữ locks/snapshot và cản autovacuum cleanup.

### Bài 12. TPS từ pg_stat_database là counter hay gauge?

**Đáp án:** xact_commit/xact_rollback là cumulative counters; phải tính delta/time.

### Bài 13. Nếu counter giảm giữa hai samples thì sao?

**Đáp án:** Có thể stats reset/restart; reset baseline, không tính rate âm.

### Bài 14. TPS có bằng business orders/s không?

**Đáp án:** Không nhất thiết; một transaction có thể tạo nhiều hoặc không tạo order nào.

### Bài 15. WAL bytes/s đo gì?

**Đáp án:** Tốc độ WAL được tạo, hữu ích cho replication/archive/storage capacity.

### Bài 16. WAL bytes có bằng data growth không?

**Đáp án:** Không. WAL còn chứa index/page/full-page images và các record nội bộ.

### Bài 17. Error rate cần mẫu số gì?

**Đáp án:** Tổng số operations thuộc cùng population/time window.

### Bài 18. Rollback nào cũng là lỗi?

**Đáp án:** Không. Một số rollback là business/validation flow có chủ đích.

### Bài 19. SQLSTATE giúp gì?

**Đáp án:** Phân loại lỗi PostgreSQL theo code/class, ví dụ unique violation, deadlock, serialization failure.

### Bài 20. pg_stat_database deadlocks là counter hay gauge?

**Đáp án:** Counter tích lũy; tính delta để có deadlocks/s.

### Bài 21. Connection failure trước khi backend được tạo có luôn thấy trong pg_stat_activity?

**Đáp án:** Không. Có thể chỉ xuất hiện trong server logs, proxy hoặc application metrics.

### Bài 22. CPU utilization cao có tự là incident?

**Đáp án:** Không. Cần xem latency, throughput, run queue, headroom và workload.

### Bài 23. CPU thấp nhưng latency cao có thể do đâu?

**Đáp án:** Lock waits, disk I/O, network, pool queue hoặc external dependency.

### Bài 24. Vì sao RSS cộng tất cả PostgreSQL backends có thể sai?

**Đáp án:** Shared memory có thể bị tính trùng giữa process.

### Bài 25. work_mem có phải tổng memory tối đa cho một query?

**Đáp án:** Không. Một query có nhiều sort/hash operations và workers; concurrent sessions nhân mức sử dụng.

### Bài 26. Disk free bytes có nên alert theo growth rate?

**Đáp án:** Có. Time-to-full có thể quan trọng hơn một ngưỡng phần trăm cố định.

### Bài 27. pg_stat_io có từ version nào?

**Đáp án:** PostgreSQL 16 trở lên.

### Bài 28. track_io_timing có thể có overhead không?

**Đáp án:** Có; đo tác động trên platform/workload trước khi bật rộng.

### Bài 29. temp_bytes trong pg_stat_database là counter hay gauge?

**Đáp án:** Counter tích lũy; tính delta để có temp write rate.

### Bài 30. Tăng work_mem có thể gây rủi ro gì?

**Đáp án:** Memory usage tăng theo operations, workers và concurrency, có thể dẫn tới memory pressure/OOM.

### Bài 31. PostgreSQL 17 có thay đổi nào về checkpoint statistics?

**Đáp án:** Có pg_stat_checkpointer tách riêng một số checkpoint statistics trước đây nằm trong pg_stat_bgwriter.

### Bài 32. n_dead_tup có phải số dead rows chính xác?

**Đáp án:** Không. Đây là estimate từ statistics.

### Bài 33. Dead tuples tăng có luôn chứng minh bloat tăng cùng tỷ lệ?

**Đáp án:** Không. Bloat phụ thuộc page reuse, visibility, index và workload; cần phân tích riêng.

### Bài 34. age(datfrozenxid) dùng để theo dõi gì?

**Đáp án:** Transaction ID age và rủi ro wraparound/freezing.

### Bài 35. Replication slot có thể ảnh hưởng vacuum không?

**Đáp án:** Có. xmin/catalog_xmin hoặc retained WAL có thể giữ dữ liệu/WAL lâu hơn.

### Bài 36. active connections và pool waiters khác gì?

**Đáp án:** Active connections đang dùng backend; pool waiters đang chờ pool cấp connection.

### Bài 37. Lock count cao có luôn là contention?

**Đáp án:** Không. Cần đo wait duration, blocked sessions và impact.

### Bài 38. pg_blocking_pids giúp gì?

**Đáp án:** Xác định PID đang block một backend cụ thể.

### Bài 39. Archive khỏe có chứng minh standby streaming khỏe?

**Đáp án:** Không. Archive và streaming là hai đường dữ liệu riêng.

### Bài 40. Cache hit ratio 99% có bảo đảm query nhanh?

**Đáp án:** Không. CPU, locks, plans, network và storage vẫn có thể là bottleneck.

### Bài 41. Vì sao cần phân biệt counter và gauge?

**Đáp án:** Counter dùng delta/rate; gauge phản ánh giá trị tại thời điểm và cần phân tích trend/window.

### Bài 42. Histogram dùng để làm gì?

**Đáp án:** Lưu phân phối observations và tính quantiles/SLO latency.

### Bài 43. Label raw query text có rủi ro gì?

**Đáp án:** Cardinality cao, storage/memory lớn và có thể lộ dữ liệu nhạy cảm.

### Bài 44. Vì sao cần application_name ổn định?

**Đáp án:** Để attribution workload theo service/worker mà không tạo label riêng cho từng request.

### Bài 45. API chậm nhưng DB query nhanh; metric nào cần xem?

**Đáp án:** Connection pool acquire wait, network, application traces và external dependency duration.

### Bài 46. TPS giảm, deadlocks tăng, CPU thấp gợi ý gì?

**Đáp án:** Có thể transaction đang bị block/deadlock; điều tra lock graph và deadlock logs.

### Bài 47. Disk tăng nhanh, pg_wal tăng, slot inactive gợi ý gì?

**Đáp án:** Replication slot có thể giữ WAL; xác định owner/consumer và archive health trước khi can thiệp.

### Bài 48. Vì sao alert cần duration/window?

**Đáp án:** Để tránh paging vì spike ngắn và phân biệt transient noise với sustained incident.

### Bài 49. Vì sao dashboard cần deployment annotations?

**Đáp án:** Giúp liên hệ latency/errors/resource changes với release, migration hoặc configuration changes.

### Bài 50. Một metric alert tốt cần những thành phần gì?

**Đáp án:** Metric/threshold/window, severity, affected service, user impact, owner, likely cause và runbook/action.

## 49. Checklist chọn và vận hành metric

| Bước | Việc cần xác nhận |
|---|---|
| Business | User-facing operation/SLO nào cần bảo vệ? |
| Latency | Đo ở API, pool, query, transaction hay lock boundary? |
| Percentile | Có histogram/sample count cho p95/p99? |
| Throughput | Định nghĩa operations/s, TPS hay business events/s? |
| Errors | Phân biệt expected rollback và unexpected failures? |
| Resources | CPU, memory, I/O, disk, connections có headroom? |
| Saturation | Có queue/waiters/lock waits không? |
| Query | pg_stat_statements có được bật và version-compatible? |
| Stats | Counters có stats_reset/restart handling? |
| Vacuum | Dead tuples, long transactions, XID age và slots? |
| HA | Replication lag, archive health và failover freshness? |
| Cardinality | Labels có bounded và an toàn? |
| Security | SQL text/parameters/secrets được bảo vệ? |
| Alert | Có threshold, duration, severity và owner? |
| Runbook | Có query/diagnosis/mitigation/verification? |
| Review | Có baseline và deployment/incident annotations? |

## 50. Tổng kết: đo trải nghiệm, giải thích tải và tìm điểm bão hòa

```text
USER / BUSINESS SLO
        |
        v
  LATENCY + ERRORS
        |
        v
     THROUGHPUT
        |
        v
 SATURATION / RESOURCES
        |
        v
 PostgreSQL views + OS + APM
        |
        v
 Correlate -> Diagnose -> Act -> Verify
```

Những nguyên tắc cần nhớ:

1. **Bắt đầu từ user impact và SLO.** Metric chỉ hữu ích khi giúp trả lời một câu hỏi vận hành.
2. **RED đo request rate, errors và duration.** Đây là nền tảng cho service-facing dashboards.
3. **USE đo utilization, saturation và errors của resource.** Dùng để tìm CPU, memory, disk, network hoặc queue bottleneck.
4. **Theo dõi p50/p95/p99, không chỉ mean.** Tail latency thường là nơi trải nghiệm xấu xuất hiện trước.
5. **pg_stat_statements cho aggregate query statistics.** Muốn p95/p99 query latency cần histogram hoặc observations ở tầng instrumentation.
6. **Cumulative counters phải tính delta/time.** Luôn xử lý stats reset và server restart.
7. **Kết hợp database metrics với OS, pool và application metrics.** Một tầng riêng lẻ không giải thích toàn bộ request.
8. **Theo dõi errors cùng volume.** Rollback có thể là expected; SQLSTATE giúp phân loại.
9. **Resource utilization cao cần đặt cạnh queue và latency.** Saturation thể hiện ở công việc phải chờ.
10. **Giám sát vacuum, XID, WAL, replication và disk retention.** Chúng có thể tạo incident dù query dashboard bình thường.
11. **Dùng labels có cardinality giới hạn và bảo vệ query text.** Monitoring cũng cần capacity và security.
12. **Alert phải có owner và hành động.** Dashboard giải thích; alert báo tình huống cần can thiệp.

**Một câu để nhớ:** *Chọn metric theo câu hỏi: request chậm ở đâu, hệ thống xử lý bao nhiêu, thao tác nào thất bại và tài nguyên nào đang bão hòa; sau đó ghép các tín hiệu theo cùng một timeline để tìm nguyên nhân.*


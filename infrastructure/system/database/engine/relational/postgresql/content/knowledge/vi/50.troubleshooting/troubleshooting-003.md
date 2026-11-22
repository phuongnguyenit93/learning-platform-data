# Truy vấn chậm đột ngột do kế hoạch, dữ liệu hoặc thống kê

Một truy vấn PostgreSQL chạy ổn định trong nhiều tuần nhưng đột nhiên chậm hơn vài lần hoặc vài trăm lần thường không có một nguyên nhân duy nhất. Có thể dữ liệu đã tăng, phân bố dữ liệu thay đổi, statistics không còn phản ánh thực tế, planner chọn execution plan khác, parameter values bị lệch phân bố, index không còn phù hợp, hoặc truy vấn đang chờ lock/I/O thay vì thực sự tốn CPU để thực thi.

Cách xử lý hiệu quả bắt đầu bằng việc xác định **điều gì đã thay đổi và thời điểm thay đổi**. Hãy so sánh query cùng parameters, cùng môi trường và cùng trạng thái workload; đọc execution plan với actual rows và buffer usage; kiểm tra statistics, locks, waits và tài nguyên ở cả database lẫn hệ điều hành. Chỉ sau khi có bằng chứng mới thay đổi query, statistics, index hoặc planner settings.

Bài học này trình bày quy trình điều tra sự cố truy vấn chậm đột ngột trong PostgreSQL. Trọng tâm là phân biệt ba nhóm nguyên nhân lớn: **execution plan thay đổi**, **dữ liệu/workload thay đổi**, và **statistics hoặc cardinality estimates sai lệch**. Các yếu tố như lock contention, cache, I/O, memory, prepared statements, autovacuum và cấu hình cũng được xem xét vì chúng thường xuất hiện cùng lúc.

~~~text
                 Truy vấn chậm đột ngột
                           |
                           v
                 Xác định phạm vi sự cố
                           |
            +--------------+--------------+
            |              |              |
            v              v              v
        Plan đổi       Data đổi       Stats lệch
            |              |              |
            +--------------+--------------+
                           |
                           v
              EXPLAIN (ANALYZE, BUFFERS)
                           |
              +------------+------------+
              |            |            |
              v            v            v
           CPU/plan       I/O/cache    Lock/wait
              |            |            |
              +------------+------------+
                           |
                           v
                Chọn mitigation có bằng chứng
                           |
                           v
                 Đo lại và theo dõi regression
~~~

Bài học thuộc module **Database Engine Relational PostgreSQL**, chương **Xử lý sự cố**, với đề tài **“Truy vấn chậm đột ngột do kế hoạch, dữ liệu hoặc thống kê”**.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt truy vấn thực sự chậm với truy vấn đang chờ lock, I/O hoặc network.
2. Xác định phạm vi, thời điểm bắt đầu và mức độ ảnh hưởng của sự cố.
3. Dùng pg_stat_statements để tìm query có latency tăng.
4. Dùng pg_stat_activity, pg_locks và pg_blocking_pids để điều tra wait và blockers.
5. Thu thập EXPLAIN và EXPLAIN ANALYZE đúng cách.
6. Đọc actual rows, estimated rows, loops, buffers, temp blocks và rows removed.
7. Nhận biết sequential scan, index scan, bitmap scan, nested loop, hash join và sort.
8. Phân biệt plan regression với data growth hoặc thay đổi selectivity.
9. Giải thích vì sao stale statistics làm planner chọn plan không phù hợp.
10. Dùng ANALYZE và theo dõi autovacuum/autoanalyze.
11. Đọc pg_stats và hiểu MCV, histogram, n_distinct, correlation.
12. Dùng extended statistics cho các columns có tương quan.
13. Nhận biết parameter skew và generic/custom prepared plans.
14. Kiểm tra ảnh hưởng của index, partition pruning và table bloat.
15. Phân tích lock waits, long transactions và deadlocks.
16. Kiểm tra cache, disk I/O, temporary files, memory và CPU pressure.
17. Đánh giá tác động của work_mem, parallelism, JIT và cost settings.
18. Sử dụng auto_explain và logging để thu thập bằng chứng trong production.
19. Chọn mitigation an toàn, có thể rollback và đo được.
20. Thiết kế baseline, regression monitoring và incident runbook.
21. Tránh các thao tác gây rủi ro như VACUUM FULL, REINDEX hoặc restart không có bằng chứng.
22. Xây dựng kế hoạch kiểm thử lại sau khi xử lý.

**Phạm vi:** PostgreSQL hiện đại, gồm các công cụ catalog và statistics phổ biến. Một số view/columns/options phụ thuộc major version; ví dụ pg_stat_io chỉ có ở các phiên bản hỗ trợ nó. Luôn kiểm tra tài liệu của đúng phiên bản và quyền truy cập được cấp trong môi trường production.

---

## 2. Trước hết: truy vấn chậm hay đang chờ?

Thời gian người dùng cảm nhận không nhất thiết bằng thời gian PostgreSQL dành cho CPU execution. Một request có thể mất 20 giây vì chờ lock, chờ disk, chờ remote service hoặc chờ connection pool, trong khi plan bản thân chỉ cần vài mili giây.

### 2.1. Các dạng latency

| Dạng | Dấu hiệu thường gặp | Nơi cần kiểm tra |
| --- | --- | --- |
| CPU-bound | CPU cao, query active, ít wait | Plan, join/aggregate, functions, parallelism |
| I/O-bound | Read latency cao, nhiều physical reads | Buffers, storage metrics, cache, plan |
| Lock-bound | wait_event_type = Lock | pg_blocking_pids, pg_locks, transactions |
| Memory/temp-bound | temp blocks/files, sort/hash spill | work_mem, cardinality, query shape |
| Network-bound | Chờ client/remote response, rows lớn | Application, FDW, network, result size |
| Connection-bound | Request chờ pool cấp connection | Pool metrics, connection count |
| Planning-bound | Planning time cao, query rất phức tạp | Parse/rewrite/plan, statistics, remote estimates |
| Resource contention | Nhiều queries cùng chậm | CPU, I/O, memory, checkpoints, concurrency |

### 2.2. Đừng bắt đầu bằng việc tạo index

Nếu query đang chờ một transaction khác giữ row lock, thêm index thường không giải quyết nguyên nhân. Nếu bottleneck là connection pool, thay đổi SQL cũng có thể không giúp.

### 2.3. Xác định thời điểm bắt đầu

Ghi nhận:
- Lần cuối query chạy bình thường.
- Thời điểm latency bắt đầu tăng.
- Deploy/application release gần nhất.
- Migration hoặc index change.
- Data import/batch job.
- ANALYZE/autovacuum/VACUUM.
- Thay đổi PostgreSQL configuration.
- Failover, restart hoặc storage/network incident.
- Thay đổi traffic và concurrency.

### 2.4. Xác định phạm vi

Hỏi:
- Một queryid hay nhiều query?
- Một bảng/schema hay toàn database?
- Một tenant/parameter value hay tất cả?
- Chỉ một application instance hay mọi clients?
- Chỉ giờ cao điểm hay liên tục?
- Query chậm từ đầu hay chỉ khi result set lớn?

Nếu nhiều query không liên quan cùng chậm, hãy điều tra tài nguyên, locks, storage và connection pool trước khi tối ưu từng SQL riêng lẻ.

### 2.5. Giữ lại bằng chứng trước khi thay đổi

Thu thập query text đã chuẩn hóa, parameters đại diện, plan, statistics, waits, logs và timestamps. Đừng reset pg_stat_statements, restart server hoặc xóa cache trước khi lưu dữ liệu điều tra.

---

## 3. Quy trình điều tra có thứ tự

Một incident nên được xử lý theo các bước có thể lặp lại.

### Bước 1: xác nhận triệu chứng

Đo latency hiện tại và so với baseline. Xác định queryid, endpoint, tenant, parameter class và tần suất.

### Bước 2: kiểm tra query có đang chờ

Dùng pg_stat_activity và pg_blocking_pids để tìm locks/waits. Nếu bị block, xác định blocker và transaction age.

### Bước 3: thu execution plan

Lấy EXPLAIN VERBOSE và, khi an toàn, EXPLAIN ANALYZE với BUFFERS. So sánh estimated rows với actual rows.

### Bước 4: kiểm tra data và statistics

Xem row counts, modifications, last_autoanalyze, pg_stats, partition sizes, indexes và data distribution.

### Bước 5: kiểm tra plan history và parameters

So sánh plan cũ/mới, query parameters, prepared statements, generic/custom plans và thay đổi query text.

### Bước 6: kiểm tra resource

CPU, I/O, memory, temp files, checkpoints, WAL, network, connection pool và concurrency.

### Bước 7: chọn một mitigation

Thay đổi nhỏ, có thể rollback. Ví dụ ANALYZE một bảng, điều chỉnh query, bổ sung index có kế hoạch hoặc xử lý blocker theo runbook.

### Bước 8: đo lại

Dùng cùng parameter class và workload tương đương. So sánh latency, rows, buffers, temp usage, CPU và ảnh hưởng tới các query khác.

### Bước 9: ghi lại root cause

Phân biệt nguyên nhân trực tiếp, điều kiện kích hoạt, yếu tố làm trầm trọng và biện pháp phòng ngừa.

---

## 4. Tìm query chậm bằng pg_stat_statements

pg_stat_statements thu thập thống kê thực thi cho các normalized SQL statements. Đây thường là điểm bắt đầu tốt để xác định query nào tiêu tốn nhiều thời gian hoặc có latency tăng.

### 4.1. Cài extension

Trên server, pg_stat_statements thường cần được thêm vào shared_preload_libraries. Đây là startup setting và thường yêu cầu restart PostgreSQL sau khi thay đổi.

Kiểm tra:

~~~sql
SHOW shared_preload_libraries;
~~~

Nếu chưa có pg_stat_statements, cấu hình qua postgresql.conf, parameter group hoặc cơ chế của managed service:

~~~conf
shared_preload_libraries = 'pg_stat_statements'
~~~

Nếu đã có các libraries khác, giữ nguyên danh sách và thêm pg_stat_statements theo cú pháp đúng.

Sau khi server khởi động lại, trong database cần quan sát:

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
~~~

### 4.2. Tìm query có tổng thời gian cao

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
    temp_blks_read,
    temp_blks_written,
    left(query, 500) AS query_sample
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

Các columns cụ thể phụ thuộc PostgreSQL/extension version. Điều chỉnh query theo schema của phiên bản đang chạy.

### 4.3. Tìm query có mean latency cao

~~~sql
SELECT
    queryid,
    calls,
    mean_exec_time,
    max_exec_time,
    rows,
    left(query, 500) AS query_sample
FROM pg_stat_statements
WHERE calls > 10
ORDER BY mean_exec_time DESC
LIMIT 20;
~~~

Một query chạy rất ít lần có thể có mean cao nhưng tác động tổng thể nhỏ. Kết hợp calls, total time và business impact.

### 4.4. Tìm query có nhiều temp blocks

~~~sql
SELECT
    queryid,
    calls,
    temp_blks_read,
    temp_blks_written,
    mean_exec_time,
    left(query, 400) AS query_sample
FROM pg_stat_statements
ORDER BY temp_blks_written DESC
LIMIT 20;
~~~

Temp blocks có thể gợi ý sort/hash operations spill ra disk. Chúng không tự chứng minh work_mem quá thấp; query có thể xử lý lượng dữ liệu lớn bất thường.

### 4.5. Đọc shared_blks_hit và shared_blks_read

- shared_blks_hit: blocks được tìm thấy trong PostgreSQL shared buffers.
- shared_blks_read: blocks PostgreSQL phải đọc vào shared buffers từ tầng storage/cache thấp hơn.

shared_blks_read không nhất thiết là physical disk read vì OS cache có thể đáp ứng. Đối chiếu với I/O metrics và track_io_timing nếu bật.

### 4.6. Queryid và normalized statements

Nhiều executions với literal values khác nhau có thể được gộp vào cùng queryid. Điều này hữu ích để tổng hợp nhưng có thể che parameter skew: cùng một query shape có values rất khác nhau về selectivity.

### 4.7. Khoảng thời gian thống kê

pg_stat_statements thường tích lũy từ lần reset hoặc server lifecycle phù hợp. Nếu không lưu snapshot định kỳ, khó biết latency vừa tăng trong 10 phút hay đã cao từ nhiều ngày.

Nên lấy snapshots theo thời gian ở monitoring system, tính delta giữa các snapshots và ghi rõ thời điểm reset.

### 4.8. Không reset trong lúc điều tra

Reset thống kê sẽ xóa baseline đang cần. Chỉ reset khi có chủ đích, được ghi nhận và đã lưu snapshot trước đó.

### 4.9. Quyền truy cập

View có thể cần quyền thích hợp hoặc role monitoring. Không cấp quyền superuser rộng chỉ để xem query stats; dùng monitoring roles theo policy.

---

## 5. Kiểm tra query đang chạy bằng pg_stat_activity

pg_stat_activity cho biết backend đang làm gì tại thời điểm quan sát.

### 5.1. Query active lâu

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    clock_timestamp() - query_start AS query_age,
    clock_timestamp() - xact_start AS transaction_age,
    left(query, 1000) AS query_sample
FROM pg_stat_activity
WHERE state = 'active'
  AND pid <> pg_backend_pid()
ORDER BY query_start;
~~~

### 5.2. Phân biệt state và wait event

- active: backend đang thực thi query, nhưng có thể đang chờ.
- idle: backend không thực thi query.
- idle in transaction: transaction mở nhưng session không chạy statement.
- wait_event_type/wait_event: mô tả loại resource mà backend đang chờ.

Một query active có wait_event_type = Lock có thể đang bị block, không phải chạy chậm do plan.

### 5.3. Tìm transactions lâu

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    clock_timestamp() - xact_start AS xact_age,
    wait_event_type,
    wait_event,
    left(query, 500) AS last_query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Long transactions có thể giữ locks, snapshot cũ, ngăn vacuum dọn dead tuples và làm tăng bloat.

### 5.4. Tìm idle in transaction

~~~sql
SELECT
    pid,
    usename,
    application_name,
    clock_timestamp() - xact_start AS xact_age,
    state_change,
    left(query, 500) AS last_query
FROM pg_stat_activity
WHERE state = 'idle in transaction'
ORDER BY xact_start;
~~~

Điều tra application code, connection pool và transaction boundaries. Không terminate session chỉ vì nó idle; xác định owner và tác động trước.

### 5.5. Không nhầm query age với CPU time

query_age là thời gian từ query_start. Nó bao gồm cả thời gian chờ. Để phân biệt, đọc wait events, plan và OS metrics.

---

## 6. Điều tra blocking và lock contention

Lock contention là nguyên nhân phổ biến của sự cố “query đột nhiên chậm” sau một deploy hoặc batch job.

### 6.1. Tìm blockers

~~~sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.usename AS blocked_user,
    blocked.application_name AS blocked_app,
    clock_timestamp() - blocked.query_start AS blocked_query_age,
    blocker.pid AS blocker_pid,
    blocker.usename AS blocker_user,
    blocker.application_name AS blocker_app,
    clock_timestamp() - blocker.xact_start AS blocker_xact_age,
    left(blocked.query, 500) AS blocked_query,
    left(blocker.query, 500) AS blocker_query
FROM pg_stat_activity AS blocked
CROSS JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) AS p(blocker_pid)
JOIN pg_stat_activity AS blocker
    ON blocker.pid = p.blocker_pid
ORDER BY blocker.xact_start NULLS LAST;
~~~

### 6.2. Xem lock details

~~~sql
SELECT
    a.pid,
    a.usename,
    a.state,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation,
    l.page,
    l.tuple,
    a.wait_event_type,
    a.wait_event,
    left(a.query, 400) AS query_sample
FROM pg_locks AS l
JOIN pg_stat_activity AS a
    ON a.pid = l.pid
ORDER BY a.pid, l.granted, l.locktype;
~~~

Không phải mọi lock đang tồn tại đều là vấn đề. Lock granted là bình thường; tập trung vào waits và blocker chain.

### 6.3. Lock chain

Một backend có thể block backend khác, rồi chính nó bị block bởi một transaction thứ ba. Xem đầy đủ blocker chain trước khi xử lý.

### 6.4. DDL gây chậm

ALTER TABLE, CREATE INDEX, DROP INDEX, VACUUM FULL và một số DDL có thể yêu cầu lock mạnh. Một DDL chờ lock có thể tạo hàng dài query chờ phía sau.

### 6.5. Long transaction

Transaction mở lâu có thể giữ row/table locks và snapshot. Kiểm tra xact_start, state và application_name.

### 6.6. Xử lý blocker

Trước khi cancel/terminate:
1. Xác định session owner và application.
2. Kiểm tra transaction đang làm gì.
3. Xác định dữ liệu có thể rollback hoặc side effects.
4. Thông báo theo incident procedure.
5. Ưu tiên cancel query nếu phù hợp.
6. Terminate backend chỉ khi có quyết định rõ và hiểu transaction rollback.
7. Theo dõi lock queue sau khi xử lý.

### 6.7. Lock timeout và deadlock

lock_timeout giới hạn thời gian chờ lock; deadlock_timeout điều khiển thời điểm PostgreSQL kiểm tra deadlock. log_lock_waits có thể ghi lock waits vượt ngưỡng liên quan.

Không tăng timeout để che lock contention nếu hệ thống cần fail fast.

---

## 7. Đọc EXPLAIN và EXPLAIN ANALYZE

Execution plan cho biết PostgreSQL dự định hoặc đã thực hiện các operations nào.

### 7.1. EXPLAIN

~~~sql
EXPLAIN
SELECT *
FROM orders
WHERE customer_id = 42;
~~~

EXPLAIN chỉ lập kế hoạch, không thực thi SELECT. Nó hiển thị estimated rows, cost và plan nodes.

### 7.2. EXPLAIN ANALYZE

~~~sql
EXPLAIN (ANALYZE)
SELECT *
FROM orders
WHERE customer_id = 42;
~~~

ANALYZE thực thi query và thu actual rows/timing. Dùng trên production cần hiểu query có thể tốn tài nguyên như lần chạy thật.

### 7.3. EXPLAIN với buffers

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT
    order_id,
    total_amount
FROM orders
WHERE customer_id = 42;
~~~

BUFFERS cho biết shared/local/temp buffer activity theo plan nodes. Đây là dữ liệu quan trọng để phân biệt query đọc nhiều pages hay chủ yếu CPU.

### 7.4. Thêm WAL và SETTINGS

~~~sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    WAL,
    SETTINGS,
    VERBOSE,
    SUMMARY
)
SELECT
    order_id,
    total_amount
FROM orders
WHERE customer_id = 42;
~~~

Một số options/fields phụ thuộc PostgreSQL version. WAL hữu ích cho các statements ghi dữ liệu; SETTINGS hiển thị một số planner-related settings khác default. Không dùng mọi option nếu target version không hỗ trợ.

### 7.5. EXPLAIN ANALYZE có thực thi query

Với SELECT, query vẫn có thể đọc lượng dữ liệu lớn, chiếm CPU, I/O, memory và locks. Với INSERT/UPDATE/DELETE, nó thực hiện thay đổi thật.

Nếu thử DML trong transaction rồi ROLLBACK, không giả định mọi side effects đều được hoàn tác: sequence increments và external side effects từ functions/triggers có thể không rollback như table rows. Ưu tiên staging hoặc bản sao dữ liệu cho thử nghiệm nguy hiểm.

### 7.6. Không chạy plan thử trên mọi query production

Chọn query representative, giới hạn concurrency, kiểm tra timeout/cancellation và có kế hoạch dừng. EXPLAIN ANALYZE không phải lệnh quan sát miễn phí.

---

## 8. Đọc estimated rows và actual rows

Sai lệch cardinality estimates là dấu hiệu quan trọng của statistics hoặc data-distribution problems.

### 8.1. Estimated rows

rows trong plan không có ANALYZE là số rows planner dự đoán một node sẽ trả.

### 8.2. Actual rows

EXPLAIN ANALYZE hiển thị số rows thực tế node trả về. Khi có loops, actual rows/time thường là giá trị trung bình mỗi loop trong output; tổng work của node cần xem cùng loops.

### 8.3. Ví dụ estimate sai

~~~text
Index Scan using orders_customer_idx on orders
  (cost=0.42..12.50 rows=5 width=48)
  (actual time=0.040..85.000 rows=85000 loops=1)
~~~

Planner dự đoán 5 rows nhưng thực tế trả 85.000 rows. Đây là sai lệch rất lớn. Nested Loop phía trên có thể trở nên cực kỳ tốn kém nếu planner dựa vào estimate nhỏ.

### 8.4. Tính sai lệch

Có thể dùng tỷ lệ actual/estimated như heuristic để tìm nodes lệch lớn. Không có một ngưỡng duy nhất phù hợp mọi query; sai lệch 10 lần ở node nhỏ có thể không quan trọng bằng sai lệch 2 lần ở node xử lý hàng triệu rows.

### 8.5. Kiểm tra từ dưới lên

Bắt đầu ở leaf scans:
- Seq Scan.
- Index Scan.
- Bitmap Heap Scan.
- Foreign Scan.
- Function Scan.

Nếu rows ở leaf sai, join order và aggregate estimates phía trên có thể sai theo.

### 8.6. Rows Removed by Filter

Giá trị cao cho thấy node đọc nhiều rows nhưng loại bỏ phần lớn sau filter. Điều này có thể là dấu hiệu predicate không được dùng hiệu quả bởi index hoặc filter chạy sau join.

### 8.7. Rows Removed by Join Filter

Có thể cho thấy join tạo nhiều candidate pairs rồi loại bỏ nhiều. Xem join condition, cardinality estimates và indexes.

### 8.8. Loops

Một Index Scan trả 100 rows với loops=1000 có thể thực hiện tổng cộng khoảng 100.000 row visits. Đừng chỉ nhìn actual rows mà bỏ qua loops.

### 8.9. Timing

Actual time trong node thường là thời gian tích lũy theo execution path của node, không cộng đơn giản tất cả node times vì parent bao gồm thời gian child. Đừng cộng các dòng plan để tính query duration.

---

## 9. Đọc buffers, I/O và temporary files

### 9.1. shared hit

Block đã có trong PostgreSQL shared buffers. Hit cao có thể vẫn tốn CPU để xử lý nhiều tuples.

### 9.2. shared read

PostgreSQL phải đưa block vào shared buffers. OS page cache có thể đáp ứng nên không đồng nghĩa chắc chắn có physical disk read.

### 9.3. dirtied và written

Dirtied blocks được thay đổi trong shared buffers; written blocks được ghi ra storage trong execution path theo cách thống kê của EXPLAIN. Phân tích cùng WAL/checkpoint metrics.

### 9.4. temp read/write

Sort/hash operations có thể spill ra temporary files khi dữ liệu vượt memory budget. Temp usage lớn thường làm query chậm rõ rệt.

### 9.5. I/O timing

track_io_timing có thể bổ sung thời gian đọc/ghi trong thống kê và EXPLAIN trên các version hỗ trợ. Bật nó có overhead tùy platform; đo trước và tuân thủ policy.

### 9.6. Cache effects

Lần chạy đầu có thể chậm vì pages chưa nằm trong cache. Lần sau nhanh hơn không nhất thiết plan đã cải thiện.

So sánh query trong trạng thái cache tương đương hoặc dùng workload monitoring dài hạn. Không cố xóa OS cache/shared buffers trên production để tạo “cold run”.

### 9.7. pg_stat_io

Trên PostgreSQL versions có pg_stat_io, view này cung cấp thống kê I/O theo backend/object/context. Dùng để bổ sung góc nhìn toàn server, không thay EXPLAIN BUFFERS.

### 9.8. Phân biệt storage bottleneck và scan quá rộng

Một query đọc 10 GB vì plan cần scan nhiều rows khác với query đọc 10 GB do storage latency bất thường. Xem cả blocks và thời gian I/O.

---

## 10. Statistics của PostgreSQL hoạt động thế nào?

Planner dùng statistics để ước lượng selectivity, số rows, distinct values và phân bố dữ liệu. Từ đó planner chọn scan type, join order, join algorithm, aggregation và parallelism.

### 10.1. ANALYZE

ANALYZE lấy sample rows và cập nhật column statistics. PostgreSQL có thể chạy ANALYZE thủ công hoặc qua autovacuum/autoanalyze.

### 10.2. Statistics không phải dữ liệu chính xác từng row

Statistics là mô hình ước lượng từ sample. Chúng không lưu mọi giá trị của bảng và có thể không phản ánh tốt phân bố cực lệch hoặc tương quan nhiều columns.

### 10.3. pg_stats

~~~sql
SELECT
    schemaname,
    tablename,
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    histogram_bounds,
    correlation
FROM pg_stats
WHERE schemaname = 'public'
  AND tablename = 'orders';
~~~

View này hiển thị column statistics ở dạng dễ đọc hơn. Quyền truy cập phụ thuộc privileges.

### 10.4. null_frac

Tỷ lệ NULL ước lượng. Nếu NULL fraction thay đổi mạnh, predicates IS NULL/IS NOT NULL có thể có selectivity khác.

### 10.5. n_distinct

Số distinct values ước lượng. Giá trị âm có ý nghĩa là tỷ lệ so với số rows thay vì số tuyệt đối. Đọc theo semantics của catalog, không coi mọi giá trị là cardinality nguyên dương.

### 10.6. most_common_vals và most_common_freqs

Most Common Values (MCV) cùng tần suất giúp planner ước lượng các values phổ biến. Nếu một tenant/status chiếm tỷ lệ rất lớn, MCV có thể ảnh hưởng mạnh tới plan.

### 10.7. histogram_bounds

Histogram mô tả phân bố phần values không nằm trong MCV list. Planner dùng nó để ước lượng range predicates.

### 10.8. correlation

Correlation mô tả quan hệ giữa thứ tự vật lý và giá trị column. Nó ảnh hưởng ước lượng chi phí của index scans có thể phải đọc heap pages theo thứ tự kém locality.

### 10.9. Statistics target

Statistics target điều khiển mức chi tiết sample/MCV/histogram cho column. Tăng target có thể giúp phân bố phức tạp nhưng làm ANALYZE tốn hơn và tăng catalog size.

~~~sql
ALTER TABLE orders
ALTER COLUMN status SET STATISTICS 500;

ANALYZE orders (status);
~~~

Giá trị 500 chỉ là ví dụ. Chỉ tăng cho columns có bằng chứng estimates sai.

---

## 11. Stale statistics và autoanalyze

Một bảng có thể tăng nhanh hoặc phân bố thay đổi sau bulk load/update. Statistics cũ khiến planner ước lượng sai.

### 11.1. Kiểm tra analyze timestamps

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze,
    last_vacuum,
    last_autovacuum
FROM pg_stat_user_tables
WHERE relname = 'orders';
~~~

### 11.2. n_mod_since_analyze

Đây là ước lượng số rows đã thay đổi kể từ lần ANALYZE gần nhất trên các versions cung cấp column này. Giá trị lớn so với table size có thể là dấu hiệu statistics cần cập nhật.

### 11.3. Autoanalyze thresholds

Autovacuum quyết định autoanalyze dựa trên threshold và scale factor cùng các điều kiện khác. Với bảng lớn, default scale factor có thể khiến số rows thay đổi trước khi analyze khá lớn.

### 11.4. Bảng partitioned

Statistics của partitioned parent và partitions có behavior/version nuances. Cần kiểm tra analyze strategy trên cả parent và partitions. Đừng giả định autoanalyze một partition tự động giải quyết mọi parent-level estimates.

### 11.5. Bulk load

Sau một bulk load lớn hoặc data migration, chạy ANALYZE phù hợp để planner thấy distribution mới. Không chờ autovacuum nếu workload cần plan tốt ngay.

### 11.6. Manual ANALYZE

~~~sql
ANALYZE orders;
~~~

Có thể phân tích riêng table/columns:

~~~sql
ANALYZE orders (customer_id, status, created_at);
~~~

ANALYZE thường nhẹ hơn VACUUM FULL nhiều, nhưng vẫn đọc sample pages và tiêu thụ I/O/CPU. Chọn thời điểm phù hợp với workload.

### 11.7. ANALYZE không dọn dead tuples

ANALYZE cập nhật statistics; VACUUM xử lý dead tuples/visibility và các nhiệm vụ bảo trì khác. Hai thao tác có mục tiêu khác nhau.

### 11.8. Autoanalyze không chạy được

Điều tra:
- Autovacuum có bị tắt toàn cục hoặc table-level không.
- Worker capacity.
- Long transactions/snapshots.
- I/O saturation.
- Table settings.
- Autovacuum logs.
- Table churn rate.

Không chỉ tăng số workers mà không xem CPU/I/O capacity.

---

## 12. Extended statistics cho các columns có tương quan

Single-column statistics có thể không đủ nếu query filter nhiều columns phụ thuộc lẫn nhau.

### 12.1. Ví dụ correlated columns

Giả sử bảng orders có region và postal_code. Một postal code chỉ thuộc một region. Nếu planner giả định hai predicates độc lập, nó có thể nhân selectivities và ước lượng rows quá thấp.

### 12.2. Dependencies

Functional dependencies statistics mô tả quan hệ phụ thuộc giữa columns.

~~~sql
CREATE STATISTICS orders_region_postal_dep (dependencies)
ON region, postal_code
FROM orders;

ANALYZE orders;
~~~

### 12.3. MCV statistics

~~~sql
CREATE STATISTICS orders_region_status_mcv (mcv)
ON region, status
FROM orders;

ANALYZE orders;
~~~

MCV extended statistics ghi nhận combinations phổ biến của nhiều columns.

### 12.4. N-distinct statistics

~~~sql
CREATE STATISTICS orders_region_status_nd (ndistinct)
ON region, status
FROM orders;

ANALYZE orders;
~~~

N-distinct giúp ước lượng số groups khi GROUP BY nhiều columns.

### 12.5. Kết hợp các kinds

~~~sql
CREATE STATISTICS orders_region_status_stats
    (dependencies, mcv, ndistinct)
ON region, status
FROM orders;

ANALYZE orders;
~~~

Không phải mọi loại extended statistics được dùng cho mọi loại clause. Kiểm tra documentation và plan của phiên bản đang chạy.

### 12.6. Extended statistics không tự sửa mọi correlation

Chúng không thay thế schema design, indexes hoặc data modeling. Tạo statistics cho combinations có bằng chứng planner estimate sai.

### 12.7. Statistics target

Extended statistics cũng có target/size và chi phí thu thập. Tăng target khi MCV combinations cần nhiều mẫu hơn, sau đó đo lại.

---

## 13. Data growth và thay đổi phân bố

Truy vấn có thể chậm dù plan không đổi vì lượng dữ liệu hoặc selectivity đã khác.

### 13.1. Table growth

Bảng tăng từ 100 nghìn lên 100 triệu rows. Sequential scan từng rẻ có thể trở nên đắt; index cũng có thể không đủ selective nếu query trả phần lớn rows.

### 13.2. Data skew

Một status trước đây chỉ chiếm 1% rows nay chiếm 70%. Cùng predicate có selectivity khác và có thể cần plan khác.

### 13.3. Tenant skew

Multi-tenant table có thể có một tenant rất lớn và hàng nghìn tenant nhỏ. Một query shape có thể phù hợp với tenant nhỏ nhưng kém với tenant lớn.

### 13.4. Hot values

MCV distribution thay đổi khi business state thay đổi, ví dụ nhiều orders chuyển sang archived hoặc pending.

### 13.5. Partition growth

Partition mới có thể không có statistics, index hoặc constraints giống partitions cũ. Kiểm tra partition pruning và metadata.

### 13.6. Data age

Query tìm dữ liệu gần đây có thể trở nên chậm nếu recent range chiếm phần lớn table hoặc index correlation thay đổi.

### 13.7. Deleted rows và dead tuples

UPDATE/DELETE tạo dead tuples. Vacuum không theo kịp có thể làm scan đọc nhiều pages hơn và tăng bloat.

### 13.8. Table bloat vs table growth

Kích thước lớn có thể do dữ liệu thật tăng hoặc do dead space/bloat. So sánh live/dead tuples, relation size, vacuum history và workload churn. Không kết luận bloat chỉ từ pg_relation_size.

### 13.9. Kiểm tra relation size

~~~sql
SELECT
    relid::regclass AS relation,
    pg_size_pretty(pg_relation_size(relid)) AS heap_size,
    pg_size_pretty(pg_indexes_size(relid)) AS indexes_size,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_catalog.pg_statio_user_tables
WHERE relid = 'public.orders'::regclass;
~~~

### 13.10. Kiểm tra table activity

~~~sql
SELECT
    relname,
    seq_scan,
    seq_tup_read,
    idx_scan,
    idx_tup_fetch,
    n_live_tup,
    n_dead_tup
FROM pg_stat_user_tables
WHERE relname = 'orders';
~~~

Các counters tích lũy từ stats reset; dùng delta theo thời gian thay vì so một snapshot đơn lẻ.

---

## 14. Execution plan thay đổi

Cùng một SQL text có thể có execution plan khác sau khi data, statistics, PostgreSQL version, configuration hoặc parameter context thay đổi.

### 14.1. Sequential Scan thành Index Scan hoặc ngược lại

Sequential scan không phải lúc nào cũng xấu. Nếu query cần phần lớn rows, sequential scan có thể rẻ hơn index scan cộng random heap fetches.

Một index scan có thể trở nên chậm khi:
- Predicate trả nhiều rows.
- Heap access rải rác.
- Cache lạnh.
- Index/table lớn.
- Correlation thấp.
- Visibility map không hỗ trợ index-only scan.

### 14.2. Nested Loop

Nested Loop tốt khi outer side nhỏ và inner side có index phù hợp. Nếu estimate outer rows quá thấp, inner scan có thể lặp hàng triệu lần.

### 14.3. Hash Join

Hash Join phù hợp với nhiều joins không cần order. Nếu hash table lớn hơn memory budget, nó có thể chia batches và spill ra disk.

### 14.4. Merge Join

Merge Join cần inputs có ordering phù hợp; có thể cần Sort. Nếu sort spill hoặc input cardinality sai, query có thể chậm.

### 14.5. Sort

Sort có thể chuyển từ in-memory sang external merge khi vượt work_mem. EXPLAIN ANALYZE có thể hiển thị Sort Method và Disk usage.

### 14.6. Aggregate

HashAggregate có thể spill/batch khi groups hoặc hash table lớn. GroupAggregate có thể cần sorted input. So sánh estimated groups và actual groups.

### 14.7. Parallel plan

Planner có thể bật/tắt parallel scans/joins/aggregates dựa trên costs, table size và settings. Worker availability cũng ảnh hưởng thực tế.

### 14.8. JIT

JIT compilation có overhead. Với query ngắn, chi phí compile có thể lớn hơn lợi ích. Với query CPU-intensive dài, JIT có thể giúp. So sánh JIT timing trong plan và settings.

### 14.9. Plan change không tự chứng minh root cause

Plan đổi có thể là phản ứng hợp lý với data mới. Nếu latency tăng, cần xem plan mới và workload metrics để biết nó là nguyên nhân hay chỉ đồng thời xuất hiện.

---

## 15. Prepared statements và parameter-sensitive plans

Một nguyên nhân khó thấy là cùng query text nhưng parameter values có phân bố rất khác.

### 15.1. Ví dụ skew

~~~sql
SELECT *
FROM orders
WHERE customer_id = $1;
~~~

Customer 10 có 3 rows; customer 99 có 2 triệu rows. Một plan duy nhất có thể không tốt cho cả hai.

### 15.2. Custom plan

Custom plan được lập dựa trên parameter values cụ thể, vì vậy planner có thể chọn index scan cho tenant nhỏ và sequential scan cho tenant lớn.

### 15.3. Generic plan

Generic plan được tạo mà không tối ưu riêng cho mỗi parameter value. Nó có thể giảm planning overhead nhưng không phù hợp với parameter skew.

### 15.4. PostgreSQL plan cache

Prepared statements có thể dùng custom/generic plans theo heuristic của PostgreSQL. Kết quả phụ thuộc driver, server-side prepare settings và số lần execution.

### 15.5. Kiểm tra prepared statements

~~~sql
SELECT
    name,
    statement,
    prepare_time,
    parameter_types,
    from_sql,
    generic_plans,
    custom_plans
FROM pg_prepared_statements;
~~~

Các columns counters như generic_plans/custom_plans tùy version. View chỉ thấy prepared statements trong current session.

### 15.6. EXPLAIN EXECUTE

Tạo prepared statement trong session và xem plan với các parameters khác nhau:

~~~sql
PREPARE order_lookup(bigint) AS
SELECT *
FROM orders
WHERE customer_id = $1;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE order_lookup(10);

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE order_lookup(99);

DEALLOCATE order_lookup;
~~~

Chỉ dùng ANALYZE nếu query an toàn và workload được kiểm soát.

### 15.7. plan_cache_mode

Có thể thử trong session/transaction:

~~~sql
SET plan_cache_mode = force_custom_plan;
~~~

Hoặc:

~~~sql
SET plan_cache_mode = force_generic_plan;
~~~

Đây là công cụ chẩn đoán/điều chỉnh có chủ đích. Không đặt globally ngay vì có thể cải thiện query này nhưng làm chậm query khác hoặc tăng planning CPU.

### 15.8. Driver prepare thresholds

JDBC driver có thể có settings liên quan server-side prepared statements và prepare threshold. Kiểm tra driver version/config trước khi kết luận PostgreSQL tự chọn generic plan.

### 15.9. Giải pháp theo evidence

- Tối ưu index và statistics cho skew.
- Tách query path theo parameter class nếu nghiệp vụ cho phép.
- Điều chỉnh prepared statement behavior ở scope hẹp.
- Dùng partitioning hoặc data model phù hợp.
- Không giả định force_custom_plan là fix chung.

---

## 16. Indexes: có index nhưng query vẫn chậm

Một query chậm không có nghĩa thiếu index. Có thể index hiện tại không phù hợp, không selective hoặc planner có lý do chọn sequential scan.

### 16.1. Kiểm tra index definitions

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename = 'orders'
ORDER BY indexname;
~~~

### 16.2. Index scan không luôn nhanh

Nếu query cần 60% table rows, index scan có thể gây nhiều heap fetches ngẫu nhiên. Sequential scan thường rẻ hơn.

### 16.3. Multicolumn index

Với B-tree, thứ tự columns có ảnh hưởng. Equality conditions trên leading columns thường quan trọng; range conditions và ordering cần được thiết kế theo query workload cụ thể.

~~~sql
CREATE INDEX orders_customer_created_idx
ON orders (customer_id, created_at DESC);
~~~

Đây chỉ là ví dụ khi query lọc customer_id và range/order theo created_at. Không áp dụng thứ tự này cho mọi query.

### 16.4. Partial index

~~~sql
CREATE INDEX orders_open_customer_idx
ON orders (customer_id, created_at)
WHERE status = 'open';
~~~

Query predicate phải chứng minh được điều kiện partial index. Prepared generic plan hoặc predicate parameterized có thể không chứng minh được implication tại planning time.

### 16.5. Covering index và INCLUDE

~~~sql
CREATE INDEX orders_customer_created_cover_idx
ON orders (customer_id, created_at)
INCLUDE (status, total_amount);
~~~

INCLUDE có thể giúp index-only scan khi các columns cần có trong index, nhưng index-only scan còn phụ thuộc visibility map. INCLUDE làm index lớn hơn và tăng write overhead.

### 16.6. Index-only scan và Heap Fetches

Nếu plan cho Index Only Scan nhưng Heap Fetches cao, visibility map có thể chưa đánh dấu đủ pages all-visible. Vacuum phù hợp có thể giúp visibility map cập nhật; không phải lúc nào cũng là giải pháp nếu table update liên tục.

### 16.7. Bitmap scans

Bitmap Index Scan kết hợp nhiều index conditions hoặc gom heap page visits. Bitmap Heap Scan có thể phù hợp khi selectivity trung bình.

### 16.8. BRIN

BRIN có thể phù hợp với bảng lớn mà physical row order tương quan với timestamp/sequence. Nếu data order thay đổi hoặc ranges quá rộng, hiệu quả giảm.

### 16.9. GIN/GiST

JSONB, full-text, arrays, ranges và spatial predicates có thể cần index method chuyên biệt. B-tree không thay thế mọi access method.

### 16.10. Index bloat và write amplification

Quá nhiều indexes làm INSERT/UPDATE/DELETE tốn hơn, tăng storage và vacuum work. Chỉ thêm index khi workload và plan chứng minh lợi ích.

### 16.11. CREATE INDEX CONCURRENTLY

Trong production, CREATE INDEX CONCURRENTLY giảm blocking writes so với build index thông thường nhưng có giới hạn và có thể để lại invalid index nếu thất bại. Lập kế hoạch lock, disk, I/O và migration behavior.

### 16.12. Không ép planner bằng enable_seqscan=off

Tắt scan methods chỉ để plan dùng index không phải giải pháp production chung. Có thể dùng trong session lab để hiểu alternative plan, nhưng không thay cost model khi chưa xác định nguyên nhân.

---

## 17. Partitioning và partition pruning

### 17.1. Query không prune partitions

Nếu predicate không thể xác định partition bounds, PostgreSQL có thể scan nhiều partitions.

### 17.2. Predicate phù hợp

Với range partition theo created_at, dùng range predicate có type rõ ràng:

~~~sql
SELECT count(*)
FROM orders
WHERE created_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-12-01 00:00:00+00';
~~~

### 17.3. Cast trên partition key

Bọc partition key trong function/cast có thể cản pruning trong một số trường hợp. Kiểm tra plan và giữ predicate sargable khi có thể.

### 17.4. Runtime pruning

Prepared statements hoặc parameters có thể cho phép runtime partition pruning. Đọc plan với Subplans Removed/loops và actual execution để xác nhận.

### 17.5. Partition mới

Kiểm tra partition mới có indexes, constraints, statistics và permissions tương ứng. Một partition lớn thiếu index có thể làm query tháng hiện tại chậm đột ngột.

### 17.6. Partition count

Quá nhiều partitions có thể tăng planning overhead và catalog work. Partitioning không phải cách tự động tăng tốc mọi query.

---

## 18. Vacuum, dead tuples và visibility map

### 18.1. VACUUM

VACUUM đánh dấu/thu hồi space của dead tuples cho reuse, cập nhật visibility map và hỗ trợ freeze transaction IDs. Nó không nhất thiết trả space về OS.

### 18.2. ANALYZE

ANALYZE cập nhật statistics phục vụ planner. VACUUM và ANALYZE có thể chạy cùng trong VACUUM ANALYZE nhưng giải quyết các mục tiêu khác nhau.

### 18.3. Kiểm tra vacuum history

~~~sql
SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
WHERE schemaname = 'public'
ORDER BY n_dead_tup DESC
LIMIT 30;
~~~

### 18.4. Dead tuples nhiều

Có thể do update/delete churn cao, autovacuum không theo kịp, long-running snapshots hoặc vacuum bị chặn.

### 18.5. Autovacuum settings per table

Các bảng có churn cao có thể cần scale factor/threshold riêng. Điều chỉnh dựa trên table size, write rate và vacuum capacity.

### 18.6. Long snapshots

Long transactions hoặc replication slots có thể giữ xmin và ngăn vacuum loại bỏ tuples cũ. Kiểm tra transaction age và replication slot retention.

### 18.7. VACUUM FULL không phải phản xạ đầu tiên

VACUUM FULL rewrite table và yêu cầu lock mạnh, có thể gây downtime/blocking. Không dùng chỉ vì một query chậm hoặc table size lớn.

### 18.8. REINDEX không phải fix mặc định

Index bloat có thể tồn tại nhưng cần đo. REINDEX có I/O, disk và lock implications; chọn REINDEX CONCURRENTLY nếu phù hợp version/operation và có runbook.

---

## 19. Workload và resource pressure

Một plan không đổi có thể chạy chậm vì server đang chịu workload khác.

### 19.1. CPU saturation

Kiểm tra CPU utilization, run queue, parallel workers, background jobs và query concurrency. Query CPU-bound có thể tăng latency khi nhiều queries tranh CPU.

### 19.2. Storage latency

Kiểm tra read/write latency, throughput, queue depth, cloud volume throttling và disk capacity. Shared buffer hits cao không loại trừ CPU bottleneck.

### 19.3. Memory pressure

work_mem là budget cho mỗi sort/hash operation, không phải một pool duy nhất cho mỗi server. Một query có nhiều operations và nhiều concurrent sessions có thể tiêu thụ memory lớn.

### 19.4. Hash/sort spill

EXPLAIN có thể cho thấy:
- Sort Method: external merge.
- Disk usage.
- Hash batches > 1.
- Temp blocks read/written.

### 19.5. Checkpoints và WAL

Checkpoint pressure, WAL generation lớn hoặc storage write saturation có thể ảnh hưởng workload. Đối chiếu checkpoint statistics/logs, WAL rate và write latency.

### 19.6. Autovacuum contention

Autovacuum cần I/O/CPU. Nó thường quan trọng cho health database, nhưng workload nặng có thể cạnh tranh tài nguyên. Không tắt autovacuum để làm query nhanh hơn mà không có kế hoạch thay thế.

### 19.7. Connection count

Nhiều active backends có thể tăng context switching và memory usage. Kiểm tra pool sizing, connection leaks và workload concurrency.

### 19.8. Network

Nếu query trả nhiều rows qua network, thời gian truyền/serialization có thể chiếm phần lớn latency. Kiểm tra rows, row width, client consumption và network RTT.

### 19.9. Replicas

Nếu query chạy trên read replica, kiểm tra replay lag, conflicts, recovery waits và replica resource contention. Một query chậm trên replica có thể không phải cùng nguyên nhân với primary.

---

## 20. Planner cost settings và cấu hình

Planner cost constants là mô hình tương đối, không phải thời gian thực tế. Chỉnh sai có thể làm nhiều query chọn plan kém.

### 20.1. Xem settings

~~~sql
SHOW random_page_cost;
SHOW seq_page_cost;
SHOW effective_cache_size;
SHOW work_mem;
SHOW maintenance_work_mem;
SHOW max_parallel_workers_per_gather;
SHOW jit;
SHOW plan_cache_mode;
~~~

Không phải mọi setting đều là nguyên nhân của incident. Ghi lại current values và thay đổi gần đây.

### 20.2. random_page_cost

Ước lượng chi phí random page access tương đối với sequential page access. Thay đổi theo storage/cache characteristics, nhưng không nên giảm chỉ để ép index scans.

### 20.3. effective_cache_size

Là estimate cho lượng cache có thể dùng bởi một query; không cấp phát memory. Đặt quá thấp/cao có thể ảnh hưởng planner cost choices.

### 20.4. work_mem

Tăng work_mem có thể giảm spill cho sort/hash, nhưng memory được dùng theo operation và concurrent queries. Thử ở session/query scope trước, đo peak usage.

### 20.5. Parallelism

max_parallel_workers_per_gather và related settings ảnh hưởng parallel plans. Parallel plan có overhead; query nhỏ có thể chậm hơn nếu parallelism không đáng.

### 20.6. JIT

Kiểm tra JIT compilation time và execution time. Tắt JIT trong session thử nghiệm có thể giúp xác định overhead, nhưng không coi đó là fix chung.

### 20.7. SET LOCAL để thử nghiệm

~~~sql
BEGIN;
SET LOCAL work_mem = '64MB';

EXPLAIN (ANALYZE, BUFFERS)
SELECT ...
FROM orders
WHERE ...;

ROLLBACK;
~~~

Dùng giá trị minh họa phù hợp môi trường. SET LOCAL chỉ có hiệu lực trong transaction hiện tại.

### 20.8. SETTINGS trong EXPLAIN

EXPLAIN SETTINGS (khi version hỗ trợ) giúp hiển thị một số planner-related settings khác default, hỗ trợ so sánh môi trường.

### 20.9. Không chỉnh global trong incident khi chưa đo

Global setting thay đổi behavior của mọi sessions và queries. Ưu tiên thử nghiệm session-scoped, canary hoặc controlled rollout.

---

## 21. Query text và application changes

Một query có thể thay đổi performance do application release dù queryid gần giống.

### 21.1. SQL text changed

Kiểm tra:
- Thêm/bớt predicates.
- Join order hoặc join conditions.
- SELECT * thay cho columns cụ thể.
- Casts.
- Functions trên columns.
- CTE materialization.
- ORDER BY/DISTINCT.
- Pagination strategy.
- Parameter types.

### 21.2. Bind parameter types

JDBC có thể bind một value với type khác so với trước, khiến PostgreSQL áp dụng cast hoặc chọn operator khác. Kiểm tra PreparedStatement setter và inferred parameter types.

### 21.3. CTE behavior

CTE có thể được inline hoặc materialize tùy query shape/version và explicit MATERIALIZED/NOT MATERIALIZED. Materialization có thể ngăn predicate pushdown giữa các query levels.

### 21.4. Function changes

Function body, volatility, cost hoặc SQL definition thay đổi có thể ảnh hưởng estimates/plan. Kiểm tra CREATE OR REPLACE FUNCTION deployments.

### 21.5. Search_path và object resolution

Thay đổi search_path có thể khiến SQL resolve sang function/operator/table khác. Trong security-sensitive code, schema-qualify objects khi phù hợp.

### 21.6. ORM changes

Hibernate/Spring Data/jOOQ version upgrade có thể sinh SQL khác:
- JOIN strategy.
- N+1 behavior.
- Pagination count query.
- Parameter binding.
- Fetch size.
- Batch behavior.

Lưu SQL thực tế từ application và so với query trước release.

### 21.7. N+1 không phải plan regression

Nếu một endpoint tăng từ 2 queries lên 500 queries, mỗi query riêng có thể nhanh nhưng tổng request chậm. Dùng application tracing và pg_stat_statements calls để phát hiện.

---

## 22. Logging và auto_explain

Khi sự cố không tái hiện dễ dàng, logging có thể cung cấp bằng chứng tại thời điểm query chạy.

### 22.1. log_min_duration_statement

Có thể log các statements vượt một ngưỡng duration. Chọn threshold theo workload và log volume.

~~~conf
log_min_duration_statement = 1000
~~~

Giá trị 1000 milliseconds chỉ là ví dụ.

### 22.2. log_lock_waits

Bật để ghi waits vượt deadlock_timeout. Hữu ích khi nghi lock contention.

### 22.3. log_temp_files

Ghi temporary files vượt threshold. Hữu ích khi sort/hash spill.

### 22.4. auto_explain

auto_explain có thể ghi execution plans cho queries vượt ngưỡng. Cần được preload và cấu hình theo version/policy.

Ví dụ settings minh họa:

~~~conf
shared_preload_libraries = 'pg_stat_statements,auto_explain'
auto_explain.log_min_duration = '1s'
auto_explain.log_analyze = on
auto_explain.log_buffers = on
auto_explain.log_timing = off
auto_explain.log_nested_statements = off
~~~

Nếu shared_preload_libraries đã có modules khác, giữ danh sách hiện tại và thêm module cần thiết. Cấu hình auto_explain có overhead; log_analyze có thể làm query tốn thêm thời gian và log volume tăng.

### 22.5. Sampling

Dùng sample rate hoặc threshold phù hợp nếu workload lớn. Không log plan của mọi query ngắn nếu lượng log không thể quản lý.

### 22.6. Sensitive values

Query text, parameters và plans có thể chứa identifiers hoặc literals nhạy cảm. Kiểm soát access, retention và redaction.

### 22.7. Không bật mọi instrumentation cùng lúc

Mỗi instrumentation có overhead. Bắt đầu bằng metrics sẵn có, sau đó bật logging/auto_explain có scope để thu thập bằng chứng.

---

## 23. Phân biệt các nhóm root cause

| Dấu hiệu | Plan regression | Data growth/skew | Stale stats | Resource/lock |
| --- | --- | --- | --- | --- |
| Remote/plan node khác | Thường có | Có thể | Thường có | Không nhất thiết |
| Actual rows tăng | Có thể | Thường có | Có thể | Không nhất thiết |
| Estimated vs actual lệch | Có thể | Có thể | Rất thường | Không nhất thiết |
| Buffers tăng | Có thể | Thường có | Có thể | Có thể |
| Wait event Lock | Không phải dấu hiệu chính | Không phải dấu hiệu chính | Không | Rất rõ |
| Nhiều queries cùng chậm | Ít hơn | Theo bảng/workload | Theo bảng | Thường có |
| ANALYZE cải thiện | Có thể nếu stats là nguyên nhân | Có thể | Thường có | Không |
| Query text đổi | Có thể | Không | Không | Không |
| Latency theo parameter | Có thể | Rất thường | Có thể | Có thể |

Bảng này là hướng dẫn điều tra, không phải bộ phân loại tuyệt đối. Một incident có thể có nhiều nguyên nhân cùng lúc.

---

## 24. Quy trình so sánh plan cũ và mới

### 24.1. Giữ cùng query

Đảm bảo SQL text, parameter types, parameter values và session settings tương đương.

### 24.2. Giữ cùng data context

Nếu data đã thay đổi, ghi nhận row counts/distribution. Không kỳ vọng plan cũ luôn tối ưu với data mới.

### 24.3. So sánh node tree

Tìm:
- Scan method thay đổi.
- Join order/algorithm thay đổi.
- Aggregate strategy thay đổi.
- Sort mới xuất hiện.
- Parallelism thay đổi.
- Partition pruning khác.
- Materialize/Memoize nodes.
- Filter chuyển vị trí.

### 24.4. So sánh cardinality

Tại từng node, so estimated rows với actual rows. Tìm điểm đầu tiên estimates lệch lớn.

### 24.5. So sánh buffers và timing

Plan có ít rows hơn nhưng đọc nhiều buffers hơn có thể kém. Xem temp, heap fetches, I/O timing và loops.

### 24.6. So sánh planner settings

Kiểm tra PostgreSQL version, extensions, cost constants, work_mem, parallelism, JIT, plan_cache_mode và search_path.

### 24.7. Plan hash không đủ

Plan text/hash có thể thay đổi do costs, aliases hoặc version mà performance không thay đổi đáng kể. Cần so node semantics và actual execution.

### 24.8. Không assert plan string cứng trong tests

Planner có thể đổi plan theo statistics, version và dataset. Nếu cần regression test, assert performance/behavior characteristics phù hợp và giữ dataset/conditions deterministic.

---

## 25. Mitigation: chọn hành động ít rủi ro trước

### 25.1. Khi statistics stale

- Chạy ANALYZE đúng bảng/columns.
- Đo lại query cùng parameters.
- Theo dõi autoanalyze và churn.
- Chỉ tăng statistics target hoặc tạo extended statistics nếu estimates vẫn sai.

### 25.2. Khi data distribution thay đổi

- Xác định parameter classes/tenants có skew.
- Kiểm tra MCV và histogram.
- Xem lại indexes và query paths.
- Cân nhắc partitioning hoặc query specialization nếu workload ổn định và có lý do.

### 25.3. Khi plan regression do prepared plan

- So sánh generic/custom plans.
- Thử plan_cache_mode ở session scope.
- Xác nhận driver prepare behavior.
- Chọn thay đổi scope nhỏ và đo các parameter classes khác.

### 25.4. Khi thiếu index

- Xác định predicate/join/order pattern.
- Kiểm tra index hiện tại và selectivity.
- Thiết kế index có thứ tự columns phù hợp.
- Ước lượng write/storage overhead.
- Dùng CREATE INDEX CONCURRENTLY nếu phù hợp production operation.
- Xác minh index valid và query plan mới.

### 25.5. Khi lock contention

- Xác định blocker chain.
- Liên hệ owner/incident commander.
- Cancel/terminate theo policy.
- Rút ngắn transaction hoặc sửa access order.
- Kiểm tra retry behavior phía application.

### 25.6. Khi I/O hoặc memory pressure

- Kiểm tra storage/host metrics.
- Xem query buffers/temp.
- Giảm concurrency hoặc workload không thiết yếu nếu incident procedure cho phép.
- Điều chỉnh query/work_mem có scope.
- Không thay global memory settings nếu chưa tính concurrency.

### 25.7. Khi application release gây SQL regression

- So SQL trước/sau release.
- Rollback/canary nếu có bằng chứng và quy trình.
- Sửa ORM/query shape.
- Giữ migration/schema compatibility.
- Theo dõi queryid và endpoint latency.

### 25.8. Khi data growth là nguyên nhân thật

- Tối ưu index/query theo scale mới.
- Partition hoặc archive theo retention policy.
- Pre-aggregate/materialize nếu phù hợp.
- Điều chỉnh capacity.
- Không cố ép sequential scan thành index scan nếu query cần phần lớn table.

---

## 26. Những hành động không nên làm vội

| Hành động | Vì sao rủi ro | Khi nào cân nhắc |
| --- | --- | --- |
| Restart PostgreSQL | Không sửa statistics/SQL; mất evidence, ảnh hưởng connections | Có sự cố server/process theo runbook |
| VACUUM FULL | Lock mạnh, rewrite table, cần disk | Có bloat đã đo và maintenance window |
| REINDEX toàn database | I/O/disk/locks, phạm vi lớn | Index corruption/bloat đã xác nhận và có kế hoạch |
| Tắt autovacuum | Tích lũy dead tuples, transaction ID risk | Chỉ thao tác đặc biệt, có thay thế rõ |
| SET enable_seqscan=off global | Làm méo planner cho mọi query | Chẩn đoán alternative plan trong session |
| Tăng work_mem global lớn | Memory nhân theo operations/concurrency | Sau khi tính peak memory và workload |
| Terminate mọi query lâu | Có thể rollback công việc hợp lệ, gây retry storm | Sau khi xác định blocker/owner/impact |
| Reset pg_stat_statements | Mất baseline cần điều tra | Sau khi lưu snapshot và có chủ đích |
| Tạo nhiều indexes ngay | Tăng write cost, storage, vacuum | Khi workload evidence hỗ trợ |
| Tăng timeout vô hạn | Che wait/lock hoặc request treo | Không phải mitigation mặc định |

---

## 27. Thiết kế query để ổn định hơn

### 27.1. Predicate sargable

Tránh bọc indexed column bằng function nếu có thể biểu diễn tương đương bằng range hoặc expression index phù hợp.

### 27.2. Type-safe parameters

Bind parameters với JDBC types đúng. Tránh implicit casts khiến planner không dùng operator/index mong muốn.

### 27.3. Explicit projections

Chỉ SELECT columns cần thiết để giảm heap fetch, network và application mapping overhead.

### 27.4. Pagination

OFFSET sâu có thể phải scan/skip nhiều rows. Keyset pagination dùng last-seen key và index phù hợp thường scale tốt hơn.

### 27.5. LIMIT cần ORDER BY ổn định

Không dựa vào thứ tự ngầm định. Dùng unique tie-breaker để pagination deterministic.

### 27.6. Join keys

Đảm bảo data types tương thích và có indexes khi workload cần. Tránh cast một phía trong join predicate nếu có thể.

### 27.7. CTE

Chỉ dùng MATERIALIZED khi muốn optimization fence/materialization có chủ đích. Để planner inline khi phù hợp hoặc dùng NOT MATERIALIZED theo version/semantics.

### 27.8. Avoid N+1

Dùng join fetch, batch fetching hoặc query tổng hợp hợp lý. Kiểm tra số calls trong pg_stat_statements và application traces.

### 27.9. Stable query paths

Nếu parameter skew rất lớn, một query plan duy nhất có thể không phù hợp. Tách query path theo nghiệp vụ/parameter class có thể giúp, nhưng cần đo chi phí maintenance và correctness.

---

## 28. Monitoring để phát hiện regression sớm

### 28.1. Query-level metrics

Theo dõi:
- Calls.
- Total execution time.
- Mean/median/p95/p99 latency nếu hệ thống metrics có thể tính.
- Rows.
- Shared block reads/hits.
- Temp blocks.
- WAL generated.
- Planning time khi có.
- Queryid và normalized query sample.

### 28.2. Table-level metrics

Theo dõi:
- Relation size.
- n_live_tup/n_dead_tup.
- n_mod_since_analyze.
- Last autoanalyze/autovacuum.
- Sequential/index scans.
- Index usage.
- Partition sizes.

### 28.3. Server-level metrics

Theo dõi:
- CPU.
- Memory.
- Storage latency/IOPS/throughput.
- Connections.
- Lock waits.
- Checkpoint/WAL.
- Temp files.
- Replication lag.
- Autovacuum workers.

### 28.4. Baseline theo parameter class

Nếu query phụ thuộc tenant/customer/date range, lưu metrics theo class hoặc endpoint context đã được mask. Một mean duy nhất có thể che slow tail.

### 28.5. Alerting

Alert theo:
- p95/p99 tăng vượt baseline.
- Total query time tăng bất thường.
- Temp files hoặc reads tăng.
- Blocking duration.
- Connection pool saturation.
- Autovacuum lag hoặc dead tuples tăng.
- Replica lag nếu query đọc replica.

### 28.6. Không alert chỉ theo một lần max latency

Một outlier có thể do cache miss hoặc scheduling. Kết hợp duration, calls, percentile, rate và impact.

### 28.7. Query text privacy

Query monitoring có thể chứa literals nhạy cảm. Dùng normalized statements, parameter masking và role-based access.

---

## 29. Runbook: truy vấn chậm đột ngột

### Bước 1: ghi nhận incident

Ghi queryid, endpoint, database, start time, current latency, baseline, frequency và user impact.

### Bước 2: xác định query đang active

Dùng pg_stat_activity. Xác định state, wait_event, transaction age và application_name.

### Bước 3: kiểm tra blockers

Dùng pg_blocking_pids và pg_locks. Nếu bị block, xử lý lock path trước khi tối ưu plan.

### Bước 4: lấy statistics snapshot

Lấy pg_stat_statements row và table/index stats. Không reset counters.

### Bước 5: lấy plan

Chạy EXPLAIN. Nếu an toàn, chạy EXPLAIN ANALYZE BUFFERS trên query đại diện. Lưu parameters và settings.

### Bước 6: tìm node đầu tiên estimate sai

Đọc từ leaf scans lên. Kiểm tra actual/estimated rows, loops và rows removed.

### Bước 7: kiểm tra data/statistics

Xem row growth, MCV, histogram, last_autoanalyze, n_mod_since_analyze, partition stats và extended stats.

### Bước 8: kiểm tra plan context

Xem generic/custom plan, driver settings, query changes, PostgreSQL version, configuration và indexes.

### Bước 9: kiểm tra resource

CPU, I/O, memory, temp files, network, connections và concurrent workload.

### Bước 10: chọn mitigation nhỏ nhất

Ví dụ ANALYZE, query rewrite, session-scoped setting, blocker handling hoặc index change có review.

### Bước 11: xác nhận và theo dõi

So sánh latency/plan/rows/buffers với baseline; theo dõi query khác để phát hiện side effects.

### Bước 12: post-incident review

Ghi root cause, detection gap, mitigation, long-term fix, owner và alert/runbook cần bổ sung.

---

## 30. Ví dụ tổng hợp: statistics cũ làm Nested Loop quá tốn kém

Giả sử query join customers với orders. Planner nghĩ một customer chỉ có vài orders, nhưng thực tế customer lớn có hàng trăm nghìn orders.

### 30.1. Plan bất lợi

~~~text
Nested Loop
  -> Index Scan on customers
       (rows=1) (actual rows=1)
  -> Index Scan on orders
       (rows=10) (actual rows=250000 loops=1)
~~~

Estimate inner side quá thấp hoặc outer cardinality sai có thể làm planner chọn nested loop không phù hợp.

### 30.2. Kiểm tra statistics

~~~sql
SELECT
    attname,
    n_distinct,
    most_common_vals,
    most_common_freqs
FROM pg_stats
WHERE schemaname = 'public'
  AND tablename = 'orders'
  AND attname = 'customer_id';
~~~

### 30.3. Cập nhật statistics

~~~sql
ANALYZE orders (customer_id);
~~~

### 30.4. Đo lại

Chạy EXPLAIN với cùng parameters. Planner có thể chọn hash join hoặc plan khác nếu estimates thay đổi. Không yêu cầu một join algorithm cụ thể; xác nhận latency và total work tốt hơn.

### 30.5. Nếu skew vẫn còn

Tăng statistics target cho customer_id, kiểm tra parameter skew và cân nhắc query path khác cho customers rất lớn.

---

## 31. Ví dụ tổng hợp: correlated predicates và extended statistics

Giả sử bảng events có tenant_id và region. Một số region chỉ xuất hiện trong một nhóm tenant. Single-column statistics có thể ước lượng sai khi filter cả hai.

### 31.1. Query

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT count(*)
FROM events
WHERE tenant_id = 42
  AND region = 'north';
~~~

### 31.2. So sánh estimates

Tìm scan node và so estimated rows với actual rows.

### 31.3. Tạo MCV/dependencies

~~~sql
CREATE STATISTICS events_tenant_region_stats
    (mcv, dependencies)
ON tenant_id, region
FROM events;

ANALYZE events;
~~~

### 31.4. Chạy lại plan

So sánh estimated rows và actual rows. Nếu estimates cải thiện, planner có thể chọn plan phù hợp hơn.

### 31.5. Giới hạn

Extended statistics không giúp mọi query shape hoặc mọi expression. Đánh giá bằng plan và workload thật.

---

## 32. Ví dụ tổng hợp: generic plan không hợp parameter skew

### 32.1. Prepared query

~~~sql
PREPARE find_orders(bigint) AS
SELECT order_id, total_amount
FROM orders
WHERE customer_id = $1;
~~~

### 32.2. Thử values có selectivity khác nhau

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
EXECUTE find_orders(10);

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE find_orders(99);
~~~

### 32.3. Thử custom plan trong session

~~~sql
SET plan_cache_mode = force_custom_plan;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE find_orders(99);
~~~

### 32.4. Diễn giải

So sánh estimated/actual rows và execution times. Nếu custom plan cải thiện một parameter class nhưng làm planning overhead hoặc values khác xấu đi, cần đánh giá tổng thể.

### 32.5. Dọn prepared statement

~~~sql
DEALLOCATE find_orders;
~~~

Không đặt force_custom_plan globally chỉ dựa vào một test.

---

## 33. Ví dụ tổng hợp: query chậm vì sort spill

### 33.1. Plan

~~~text
Sort
  Sort Key: created_at DESC
  Sort Method: external merge  Disk: ...
  Buffers: temp read=... written=...
  -> Seq Scan on orders
~~~

### 33.2. Xác định nguyên nhân

- Query cần sort bao nhiêu rows?
- Có predicate selective không?
- Có index phù hợp với filter/order không?
- Row width có quá lớn do SELECT *?
- work_mem có phù hợp với concurrency?
- Data volume có tăng bất thường?

### 33.3. Thử session work_mem

~~~sql
BEGIN;
SET LOCAL work_mem = '64MB';

EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM orders
ORDER BY created_at DESC
LIMIT 1000;

ROLLBACK;
~~~

### 33.4. So sánh alternative

Nếu query có WHERE customer_id = ?, index trên customer_id, created_at có thể tốt hơn tăng work_mem. Hãy kiểm tra plan với workload thật.

### 33.5. Kết luận

Sort spill là dấu hiệu memory/dataset/query shape cần xem xét; không tự động chứng minh work_mem global cần tăng.

---

## 34. Ví dụ tổng hợp: index scan chậm hơn sequential scan

### 34.1. Tình huống

Query filter status='processed' và trả về phần lớn table. Index tồn tại nhưng planner chọn Seq Scan.

### 34.2. Điều tra

- Tỷ lệ rows thỏa predicate.
- MCV frequency của status.
- Heap page locality.
- Index size.
- Table size.
- Shared buffers/cache.
- Estimated vs actual rows.

### 34.3. Không ép index

Nếu 80% rows phù hợp, Seq Scan có thể là plan đúng. Tạo thêm index không nhất thiết giúp.

### 34.4. Tối ưu query

Chọn ít columns, chia workload theo thời gian/tenant, dùng partitioning nếu phù hợp hoặc tạo partial index cho trạng thái hiếm và query thực sự selective.

### 34.5. Kết luận

Index là access path, không phải bảo đảm query nhanh. Planner cần chọn path rẻ nhất cho selectivity và storage behavior hiện tại.

---

## 35. Lab 1: quan sát query statistics và execution plan

Dùng database development/staging với dữ liệu synthetic.

### 35.1. Cài pg_stat_statements

Cấu hình shared_preload_libraries theo môi trường, restart khi cần và tạo extension trong database test.

### 35.2. Tạo bảng

~~~sql
CREATE TABLE orders_lab (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    amount NUMERIC(12,2) NOT NULL
);
~~~

### 35.3. Nạp dữ liệu

~~~sql
INSERT INTO orders_lab (customer_id, status, created_at, amount)
SELECT
    (g % 10000) + 1,
    CASE WHEN g % 100 = 0 THEN 'rare'
         WHEN g % 5 = 0 THEN 'pending'
         ELSE 'paid'
    END,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + (g % 365) * INTERVAL '1 day',
    (g % 100000) / 100.0
FROM generate_series(1, 500000) AS g;
~~~

### 35.4. Chạy query nhiều lần

~~~sql
SELECT count(*)
FROM orders_lab
WHERE status = 'paid';

SELECT count(*)
FROM orders_lab
WHERE status = 'rare';
~~~

### 35.5. Xem pg_stat_statements

Tìm normalized statements và so calls/mean/total execution time. Lưu snapshot trước khi reset bất kỳ statistics nào.

### 35.6. EXPLAIN ANALYZE

Chạy EXPLAIN (ANALYZE, BUFFERS) cho hai predicates và so actual rows, buffers và plan.

### 35.7. Kết luận

Cùng query shape có thể có selectivity khác nhau theo parameter/value distribution.

---

## 36. Lab 2: stale statistics và ANALYZE

### 36.1. Thu statistics ban đầu

~~~sql
ANALYZE orders_lab;

SELECT
    attname,
    n_distinct,
    most_common_vals,
    most_common_freqs
FROM pg_stats
WHERE tablename = 'orders_lab';
~~~

### 36.2. Thay đổi data distribution

Insert một lượng lớn rows có status='rare' hoặc update nhiều rows từ paid sang rare.

### 36.3. Xem table statistics

~~~sql
SELECT
    relname,
    n_live_tup,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE relname = 'orders_lab';
~~~

### 36.4. Chạy plan trước ANALYZE

So estimated rows với actual rows cho predicate status='rare'. Dataset nhỏ có thể tự autoanalyze; điều khiển lab threshold hoặc tạo đủ data để quan sát, không giả định statistics chắc chắn stale.

### 36.5. Chạy ANALYZE

~~~sql
ANALYZE orders_lab;
~~~

### 36.6. Chạy plan lại

So estimates và actual rows. Quan sát planner có chọn scan method khác hay không.

### 36.7. Kết luận

ANALYZE cập nhật mô hình phân bố; plan có thể thay đổi khi estimates tốt hơn.

---

## 37. Lab 3: extended statistics

### 37.1. Tạo correlated columns

~~~sql
CREATE TABLE customer_events_lab AS
SELECT
    g AS event_id,
    (g % 100) + 1 AS tenant_id,
    CASE
        WHEN (g % 100) < 50 THEN 'north'
        ELSE 'south'
    END AS region
FROM generate_series(1, 500000) AS g;
~~~

### 37.2. Analyze

~~~sql
ANALYZE customer_events_lab;
~~~

### 37.3. Kiểm tra plan

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT count(*)
FROM customer_events_lab
WHERE tenant_id = 1
  AND region = 'north';
~~~

### 37.4. Tạo extended stats

~~~sql
CREATE STATISTICS customer_events_tenant_region
    (dependencies, mcv)
ON tenant_id, region
FROM customer_events_lab;

ANALYZE customer_events_lab;
~~~

### 37.5. So sánh

So estimated rows trước/sau. Dữ liệu lab có thể không tạo correlation đủ mạnh cho mọi statistics kind; hãy thử nhiều distributions và giải thích kết quả.

### 37.6. Kết luận

Extended statistics giúp planner mô hình hóa quan hệ giữa columns thay vì luôn giả định độc lập.

---

## 38. Lab 4: prepared plans và parameter skew

### 38.1. Tạo skewed data

Tạo một customer có nhiều orders và nhiều customers chỉ có ít orders.

### 38.2. Tạo index

~~~sql
CREATE INDEX orders_lab_customer_idx
ON orders_lab(customer_id);
~~~

### 38.3. Chuẩn bị statement

~~~sql
PREPARE orders_by_customer(bigint) AS
SELECT order_id, amount
FROM orders_lab
WHERE customer_id = $1;
~~~

### 38.4. So sánh parameters

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_by_customer(1);

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_by_customer(9999);
~~~

### 38.5. Thử plan_cache_mode

Thử force_custom_plan và force_generic_plan trong session. Ghi lại plan và timings cho từng parameter class.

### 38.6. Dọn statement

~~~sql
DEALLOCATE orders_by_customer;
~~~

### 38.7. Kết luận

Prepared plan behavior có thể làm cùng SQL text phản ứng khác nhau với skewed parameters.

---

## 39. Lab 5: lock contention và sort spill

### 39.1. Lock test

Mở hai psql sessions:
- Session A: BEGIN; SELECT ... FOR UPDATE trên một row.
- Session B: UPDATE cùng row.
- Quan sát pg_stat_activity, pg_locks và pg_blocking_pids.
- Commit/rollback session A và xem session B tiếp tục.

### 39.2. Lock timeout

Trong session B, thử SET LOCAL lock_timeout trong transaction và quan sát SQLSTATE khi timeout.

### 39.3. Sort test

Tạo query sort một lượng lớn rows với projection rộng. Chạy EXPLAIN (ANALYZE, BUFFERS) và quan sát Sort Method/temp blocks.

### 39.4. Thử index/order path

Tạo index phù hợp với filter/order trong lab, chạy lại và so buffers/latency.

### 39.5. Thử work_mem session-scoped

Dùng SET LOCAL work_mem trong transaction thử nghiệm. So sánh temp usage và memory risk.

### 39.6. Kết luận

Một query chậm có thể bị lock hoặc spill; cần xác định wait/resource trước khi thay đổi planner.

---

## 40. Bài tập thực hành

### Bài 1 — Incident triage

Một endpoint tăng latency từ 100 ms lên 8 giây. Viết danh sách thông tin cần thu thập trước khi sửa query.

### Bài 2 — Query vs wait

Phân biệt CPU-bound, I/O-bound, lock-bound và connection-pool-bound.

### Bài 3 — pg_stat_statements

Viết query tìm top 20 statements theo total_exec_time và mean_exec_time.

### Bài 4 — Queryid

Vì sao normalized queryid có thể che parameter skew? Đề xuất cách quan sát parameter classes an toàn.

### Bài 5 — Stats reset

Giải thích vì sao không nên reset pg_stat_statements khi incident vừa bắt đầu.

### Bài 6 — pg_stat_activity

Viết query tìm active queries chạy lâu và hiển thị wait_event_type/wait_event.

### Bài 7 — Idle in transaction

Một backend idle in transaction 30 phút. Những rủi ro nào cần kiểm tra trước khi terminate?

### Bài 8 — Blocking

Viết query dùng pg_blocking_pids để xác định blocked pid và blocker pid.

### Bài 9 — Lock details

Dùng pg_locks và pg_stat_activity để xác định lock mode, relation và granted status.

### Bài 10 — EXPLAIN

Phân biệt EXPLAIN với EXPLAIN ANALYZE. Vì sao ANALYZE có thể gây tác động production?

### Bài 11 — DML plan

Vì sao BEGIN; EXPLAIN ANALYZE UPDATE; ROLLBACK không bảo đảm mọi side effects được hoàn tác?

### Bài 12 — Actual vs estimated

Một scan ước lượng 10 rows nhưng thực tế 100.000 rows. Điều đó có thể ảnh hưởng join choice như thế nào?

### Bài 13 — Loops

Một Index Scan trả 20 rows với loops=5000. Ước lượng tổng số row visits và giải thích vì sao cần đọc loops.

### Bài 14 — Buffers

Phân biệt shared hit, shared read, dirtied, written và temp blocks.

### Bài 15 — Cache

Lần đầu query chậm, lần thứ hai nhanh. Làm thế nào phân biệt cache warming với plan improvement?

### Bài 16 — Statistics

Giải thích null_frac, n_distinct, MCV, histogram_bounds và correlation.

### Bài 17 — Autoanalyze

Viết query xem n_mod_since_analyze, last_autoanalyze và n_dead_tup của một table.

### Bài 18 — Manual ANALYZE

Khi nào nên chạy ANALYZE sau bulk load? Vì sao ANALYZE khác VACUUM?

### Bài 19 — Statistics target

Một status hiếm không xuất hiện trong MCV. Khi nào tăng statistics target có thể giúp?

### Bài 20 — Extended statistics

Tạo dependencies, MCV và ndistinct statistics cho hai correlated columns.

### Bài 21 — Data skew

Một tenant có 60% rows trong bảng multi-tenant. Vì sao cùng query có thể cần plan khác cho tenant này và tenant nhỏ?

### Bài 22 — Nested Loop

Giải thích vì sao Nested Loop có thể trở nên chậm nếu outer row estimate quá thấp.

### Bài 23 — Hash spill

Nhận diện Hash Join/HashAggregate spill trong EXPLAIN và đề xuất cách điều tra.

### Bài 24 — Sort spill

Một Sort dùng external merge và ghi temp blocks. Những yếu tố nào cần kiểm tra trước khi tăng work_mem?

### Bài 25 — Generic/custom plan

Giải thích sự khác nhau và dùng EXPLAIN EXECUTE để so sánh parameter values.

### Bài 26 — plan_cache_mode

Thử force_custom_plan và force_generic_plan ở session scope. Vì sao không nên đặt global ngay?

### Bài 27 — JDBC prepare

Những cấu hình nào của PostgreSQL JDBC driver có thể ảnh hưởng server-side prepared statements?

### Bài 28 — Index selectivity

Vì sao index scan có thể chậm hơn sequential scan khi predicate trả phần lớn bảng?

### Bài 29 — Multicolumn index

Thiết kế index cho query lọc customer_id và range created_at; giải thích thứ tự columns.

### Bài 30 — Partial index

Một partial index WHERE status='open' không được planner dùng cho prepared query. Hãy phân tích predicate implication và generic plan.

### Bài 31 — Index-only scan

Vì sao Index Only Scan vẫn có nhiều Heap Fetches? Visibility map liên quan thế nào?

### Bài 32 — Partition pruning

Một query scan mọi partitions dù chỉ cần một tháng. Kiểm tra predicate, casts và partition bounds.

### Bài 33 — Vacuum

N_dead_tup tăng mạnh và last_autovacuum cũ. Liệt kê nguyên nhân có thể và dữ liệu cần kiểm tra.

### Bài 34 — Long snapshots

Giải thích vì sao long transaction hoặc replication slot có thể ngăn vacuum dọn tuples.

### Bài 35 — Resource pressure

Nhiều queries không liên quan cùng chậm. Xây dựng checklist CPU, I/O, memory, connections, checkpoints và network.

### Bài 36 — auto_explain

Cấu hình auto_explain có ngưỡng và buffers. Nêu tradeoff của log_analyze/log_timing.

### Bài 37 — Application regression

Sau nâng Hibernate, số queries tăng từ 3 lên 200. Phân biệt N+1 với plan regression bằng pg_stat_statements và tracing.

### Bài 38 — Safe mitigation

Một blocker giữ lock 20 phút. Nêu quy trình xác minh owner/transaction/impact trước cancel hoặc terminate.

### Bài 39 — Incident postmortem

Viết mẫu root cause report phân biệt trigger, direct cause, contributing factors, mitigation và prevention.

### Bài 40 — End-to-end diagnosis

Một query report đột ngột chậm sau bulk import và deploy ứng dụng. Xây dựng kế hoạch lấy pg_stat_statements, pg_stat_activity, blockers, EXPLAIN ANALYZE BUFFERS, stats, indexes, parameter plans, resource metrics; chọn mitigation, xác minh và theo dõi regression.

---

## 41. Checklist điều tra truy vấn chậm

| Hạng mục | Điều cần xác nhận |
| --- | --- |
| Impact | Query/endpoint/tenant nào bị ảnh hưởng |
| Start time | Thời điểm latency bắt đầu tăng |
| Baseline | p50/p95/p99 và calls trước/sau |
| Query identity | queryid, normalized SQL, parameter class |
| Application release | SQL/ORM/driver changes |
| pg_stat_statements | total/mean/max time, rows, buffers, temp |
| Active sessions | state, wait_event, query_age, xact_age |
| Blocking | pg_blocking_pids và lock chain |
| Plan | EXPLAIN/EXPLAIN ANALYZE phù hợp |
| Cardinality | estimated vs actual rows ở từng node |
| Loops | Nested Loop và repeated scans |
| Buffers | hit/read/dirtied/written/temp |
| Sort/hash | spill, batches, disk usage |
| Statistics | last_analyze/autoanalyze, n_mod_since_analyze |
| Distribution | MCV, histogram, null_frac, n_distinct |
| Correlation | extended statistics có cần thiết |
| Table growth | live/dead tuples, relation size |
| Indexes | definitions, selectivity, usage, validity |
| Partitions | pruning, partition stats/indexes |
| Prepared plans | generic/custom, driver prepare behavior |
| Settings | work_mem, costs, parallelism, JIT, plan_cache_mode |
| Resource | CPU, memory, I/O latency, temp, WAL/checkpoints |
| Connections | pool saturation, active/idle sessions |
| Autovacuum | worker activity, lag, blockers |
| Logs | duration, lock waits, temp files, auto_explain |
| Safety | EXPLAIN ANALYZE impact and data sensitivity |
| Mitigation | smallest reversible change |
| Validation | same parameters/workload and result correctness |
| Regression | monitor query and collateral workloads |
| Documentation | root cause, owner, follow-up and alert |

## Kết luận

Truy vấn chậm đột ngột thường xuất phát từ sự thay đổi trong execution plan, data volume/distribution hoặc statistics; đôi khi query đang chờ lock, I/O hay tài nguyên dùng chung. PostgreSQL planner chỉ có thể chọn plan tốt khi estimates đủ sát với dữ liệu và cost model phản ánh môi trường. Vì vậy, điều tra phải kết hợp query statistics, active sessions, locks, execution plan, table statistics và host metrics.

Những nguyên tắc cần nhớ:

1. **Xác định query đang chạy hay đang chờ.** Wait events và blockers giúp tránh tối ưu nhầm nguyên nhân.
2. **Lưu evidence trước khi thay đổi.** Giữ queryid, parameters, plan, statistics và timestamps.
3. **Dùng pg_stat_statements để tìm workload gây ảnh hưởng.** Kết hợp calls, total time, mean/max và buffers.
4. **Đọc EXPLAIN ANALYZE cùng BUFFERS.** So actual rows với estimates, loops, temp usage và rows removed.
5. **Tìm node đầu tiên estimate sai.** Sai cardinality ở leaf có thể dẫn tới join order và algorithm không phù hợp.
6. **ANALYZE sau thay đổi dữ liệu lớn.** Kiểm tra autoanalyze và n_mod_since_analyze thay vì đoán statistics đã cập nhật.
7. **Dùng extended statistics khi columns tương quan.** MCV, dependencies và ndistinct giúp mô hình hóa những quan hệ mà single-column stats bỏ sót.
8. **Kiểm tra parameter skew và prepared plans.** Một generic plan có thể không phù hợp với mọi parameter values.
9. **Index không phải lúc nào cũng tốt hơn Seq Scan.** Selectivity, heap locality, cache và row width quyết định access path.
10. **Phân biệt bloat với data growth.** Vacuum, ANALYZE và REINDEX giải quyết các vấn đề khác nhau.
11. **Không chỉnh global settings theo cảm tính.** Thử session-scoped và đo cả concurrency/resource impact.
12. **Không restart, VACUUM FULL hoặc terminate sessions vội.** Những thao tác này có thể làm mất evidence hoặc gây gián đoạn lớn.
13. **So sánh cùng parameter class và workload.** Một lần chạy nhanh hơn chưa chứng minh regression đã được sửa.
14. **Theo dõi cả database lẫn application.** N+1, connection pool, network và remote services có thể làm endpoint chậm dù query plan tốt.
15. **Ghi lại root cause và prevention.** Bổ sung baseline, alerts, migration checks và runbook để phát hiện sớm lần sau.

Một quy trình xử lý đáng tin cậy bắt đầu bằng quan sát, tìm node hoặc resource tạo ra độ trễ, kiểm tra statistics và data distribution, rồi thử một mitigation có thể rollback. Chỉ xác nhận sự cố đã giải quyết khi kết quả truy vấn vẫn đúng, latency cải thiện trên parameter classes đại diện và workload còn lại không bị suy giảm.

## Tài liệu tham khảo

- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html)
- [PostgreSQL — Planner Statistics](https://www.postgresql.org/docs/current/planner-stats.html)
- [PostgreSQL — Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html)
- [PostgreSQL — Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html)
- [PostgreSQL — pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html)
- [PostgreSQL — auto_explain](https://www.postgresql.org/docs/current/auto-explain.html)
- [PostgreSQL — CREATE STATISTICS](https://www.postgresql.org/docs/current/sql-createstatistics.html)
- [PostgreSQL — Planner Configuration](https://www.postgresql.org/docs/current/runtime-config-query.html)


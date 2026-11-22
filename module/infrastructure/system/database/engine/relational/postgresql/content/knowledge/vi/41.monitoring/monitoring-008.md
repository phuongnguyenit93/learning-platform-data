# Theo dõi tiến độ VACUUM, tạo chỉ mục, COPY và sao lưu trong PostgreSQL

Các tác vụ bảo trì và nạp dữ liệu trong PostgreSQL có thể chạy từ vài giây tới nhiều giờ. Khi một lệnh `VACUUM`, `CREATE INDEX`, `COPY` hoặc `pg_basebackup` đang chạy, chỉ nhìn thấy một session ở trạng thái `active` không đủ để biết nó đã làm tới đâu, đang chờ điều gì hay còn bao lâu mới xong.

PostgreSQL cung cấp các **progress reporting views** trong schema `pg_catalog`. Các view `pg_stat_progress_*` hiển thị một hàng cho mỗi tiến trình đang thực hiện loại công việc tương ứng, gồm phase hiện tại và các bộ đếm tiến độ. Kết hợp chúng với `pg_stat_activity`, statistics views và log sẽ giúp DBA quan sát được hoạt động mà không cần đoán từ thời gian chạy.

Bài học này tập trung vào bốn nhóm tác vụ: VACUUM/ANALYZE, tạo và xây dựng lại index, COPY và physical base backup. Nội dung gồm cách đọc phase/counters, tính tiến độ, nhận biết tác vụ đang chờ, viết truy vấn giám sát và xử lý các trường hợp không có phần trăm hoàn thành đáng tin cậy.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích progress reporting và sự khác nhau giữa progress view với activity/statistics view.
2. Theo dõi VACUUM, autovacuum, ANALYZE và VACUUM FULL.
3. Theo dõi `CREATE INDEX`, `CREATE INDEX CONCURRENTLY` và `REINDEX`.
4. Theo dõi `COPY FROM` và `COPY TO`, hiểu khi nào không có tổng bytes.
5. Theo dõi `pg_basebackup` và các phase của backup.
6. Join progress views với `pg_stat_activity` để biết user, database, query, wait event và thời gian chạy.
7. Diễn giải counters, phần trăm hoàn thành và giới hạn của ETA.
8. Nhận diện blocking, I/O pressure, dead tuples, replication lag và WAL/archive bottlenecks.
9. Thiết kế dashboard/alerts phù hợp cho production.
10. Hiểu khác biệt phiên bản và quyền truy cập khi giám sát.

## 2. Progress reporting là gì?

### 2.1. Activity và progress khác nhau

`pg_stat_activity` trả lời câu hỏi **session/process đang làm gì**: PID, user, database, state, query, thời điểm bắt đầu, wait event và transaction age.

`pg_stat_progress_*` trả lời câu hỏi **một loại tác vụ cụ thể đã đi tới đâu**: phase, blocks/tuples/bytes đã xử lý, tổng số đã biết và các bộ đếm theo tác vụ.

Statistics views như `pg_stat_user_tables`, `pg_stat_database` hoặc `pg_stat_archiver` mô tả hoạt động tích lũy trong một khoảng thời gian hoặc kể từ lần reset stats; chúng không nhất thiết là progress của một lệnh đang chạy.

### 2.2. Một progress row tương ứng một backend

Progress views thường có cột `pid` để xác định backend đang thực hiện công việc. Join `pid` với `pg_stat_activity.pid` để lấy context của session.

~~~sql
SELECT
    p.pid,
    a.usename,
    a.datname,
    a.application_name,
    a.client_addr,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.query_start,
    now() - a.query_start AS elapsed,
    a.query
FROM pg_stat_activity AS a
WHERE a.state = 'active'
ORDER BY a.query_start;
~~~

Progress view chỉ có hàng khi tác vụ đang ở loại công việc được instrument và backend còn thực hiện tác vụ đó. Khi lệnh hoàn tất, row biến mất; cần lưu metrics/logs nếu muốn có lịch sử.

### 2.3. Phase là trạng thái công việc, không phải phần trăm

Một tác vụ có thể đi qua nhiều phase. Ví dụ index build có thể chờ writers, scan heap, sort tuples và chờ snapshots cũ. Một phase có counters nhưng phase khác chỉ biểu diễn trạng thái chờ.

Không lấy `phase` làm số phần trăm. Đọc các counters tương ứng phase đó và hiểu đơn vị của chúng.

### 2.4. Progress view không phải audit log

Progress views là ảnh chụp trạng thái hiện tại. Chúng không giữ lịch sử sau khi backend kết thúc và không chứng minh tác vụ đã thành công. Dùng PostgreSQL logs, monitoring time series hoặc job orchestration để ghi nhận start/end, exit status và duration.

### 2.5. Permissions

Người dùng cần quyền đọc statistics phù hợp. Theo phiên bản, một số cột nhạy cảm như query text có thể bị che với user không có quyền giám sát. Các role như `pg_monitor`/`pg_read_all_stats` có thể được cấp theo least privilege. Không cấp superuser chỉ để xem dashboard.

### 2.6. Version differences

Progress views và columns được bổ sung qua các major releases. Một query dùng cột mới có thể lỗi trên server cũ. Luôn xem catalog trên version triển khai:

~~~sql
SELECT
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'pg_catalog'
  AND table_name LIKE 'pg_stat_progress_%'
ORDER BY table_name, ordinal_position;
~~~

Không phải mọi system view đều được mô tả đầy đủ trong `information_schema` trên mọi version; có thể tra `pg_catalog`/`\d+ pg_catalog.pg_stat_progress_vacuum` bằng psql.

## 3. Các progress views liên quan

| View | Công việc được theo dõi | Một số counters/fields |
| --- | --- | --- |
| `pg_stat_progress_vacuum` | VACUUM thường và autovacuum | heap blocks, dead tuples, index vacuum count |
| `pg_stat_progress_analyze` | ANALYZE | sample rows, inheritance sample rows, phase |
| `pg_stat_progress_cluster` | CLUSTER và VACUUM FULL | heap blocks scanned/written, tuples |
| `pg_stat_progress_create_index` | CREATE INDEX, REINDEX | lockers, blocks, tuples, partitions |
| `pg_stat_progress_copy` | COPY FROM/TO | bytes processed/total, tuples processed/excluded |
| `pg_stat_progress_basebackup` | pg_basebackup | backup bytes, tablespaces, phase |

View/cột cụ thể phụ thuộc major version. `pg_stat_progress_basebackup` phản ánh tiến độ base backup được server phục vụ; đây không phải view theo dõi mọi sản phẩm backup bên ngoài hoặc mọi kiểu filesystem snapshot.

## 4. Quy trình chung để theo dõi một tác vụ

### 4.1. Xác định PID và loại công việc

Trước tiên xem session:

~~~sql
SELECT
    pid,
    backend_type,
    usename,
    datname,
    application_name,
    state,
    wait_event_type,
    wait_event,
    query_start,
    now() - query_start AS elapsed,
    left(query, 300) AS query
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY query_start;
~~~

`backend_type` có mặt ở các version mới; nếu server cũ không có cột này, bỏ khỏi query.

### 4.2. Đọc progress view tương ứng

Tùy loại lệnh, truy vấn view tương ứng. Không có một view tổng hợp duy nhất cho tất cả operations.

### 4.3. Join để có context

Mẫu chung:

~~~sql
SELECT
    p.pid,
    a.usename,
    a.datname,
    a.application_name,
    now() - a.query_start AS elapsed,
    a.wait_event_type,
    a.wait_event,
    p.phase
FROM some_progress_view AS p
LEFT JOIN pg_stat_activity AS a USING (pid);
~~~

Thay `some_progress_view` và `phase` bằng view/cột thực tế. Không phải mọi progress view đều có cột tên `phase` giống nhau.

### 4.4. Tính tỷ lệ khi có total hợp lệ

Với counters cùng đơn vị và tổng lớn hơn zero:

\[
\text{Progress \%} =
\frac{\text{Done}}{\text{Total}} \times 100
\]

Nếu total bằng zero/NULL hoặc chưa được ước tính, hiển thị `unknown`/NULL thay vì chia cho zero hoặc báo 100%.

### 4.5. ETA chỉ là ước lượng

Có thể ước lượng tốc độ từ hai snapshots cách nhau một khoảng thời gian:

\[
\text{Rate} = \frac{\Delta \text{Done}}{\Delta t}
\]

\[
\text{ETA} \approx \frac{\text{Total} - \text{Done}}{\text{Rate}}
\]

Phép tính chỉ có ý nghĩa khi total ổn định, counters đơn điệu và tác vụ tiếp tục cùng tốc độ. Phase change, waits, disk contention, parallel workers và thay đổi workload làm ETA sai lệch. Đối với tác vụ không có total, không hiển thị ETA giả tạo.

### 4.6. Quan sát theo thời gian

Chạy query lặp lại mỗi vài giây hoặc thu thập qua monitoring agent. Không poll quá dày gây tải không cần thiết. Lưu timestamp, PID, relation, phase và counters để vẽ time series.

### 4.7. Tác vụ biến mất khỏi view

Khi progress row biến mất, có thể tác vụ đã hoàn tất, bị cancel, backend crash hoặc chuyển sang loại hoạt động không có progress instrumentation. Kiểm tra `pg_stat_activity`, client result, logs và job runner để phân biệt.

## 5. Theo dõi VACUUM và autovacuum

### 5.1. VACUUM làm gì?

PostgreSQL dùng MVCC. UPDATE/DELETE tạo row versions cũ; VACUUM xác định tuples không còn cần cho bất kỳ snapshot nào, đánh dấu không gian có thể tái sử dụng, cập nhật visibility/free-space metadata và hỗ trợ ngăn transaction ID wraparound.

VACUUM thường không viết lại toàn bộ table. Nó xử lý heap và indexes theo các phase, vì vậy một lệnh có thể chạy lâu ở bước index cleanup hoặc chờ điều kiện để cắt phần cuối relation.

### 5.2. Progress view

View `pg_stat_progress_vacuum` theo dõi VACUUM thường và autovacuum worker. Các cột quan trọng:

| Cột | Ý nghĩa |
| --- | --- |
| `pid` | Backend PID |
| `datid`, `datname` | Database |
| `relid` | OID của relation đang vacuum |
| `phase` | Phase hiện tại |
| `heap_blks_total` | Tổng heap blocks cần xử lý |
| `heap_blks_scanned` | Heap blocks đã scan |
| `heap_blks_vacuumed` | Heap blocks đã vacuum |
| `index_vacuum_count` | Số lần index vacuum đã thực hiện |
| `max_dead_tuples` | Capacity của dead-tuple store |
| `num_dead_tuples` | Dead tuples hiện có trong store |

### 5.3. Các phase VACUUM

| Phase | Công việc |
| --- | --- |
| `initializing` | Chuẩn bị VACUUM và các cấu trúc cần thiết |
| `scanning heap` | Scan heap, tìm dead tuples và cập nhật thông tin |
| `vacuuming indexes` | Dọn các index entries tham chiếu dead tuples |
| `vacuuming heap` | Xử lý heap pages và tuples đã xác định |
| `cleaning up indexes` | Cleanup index structures sau các vòng xử lý |
| `truncating heap` | Có thể truncate empty pages ở cuối relation |
| `performing final cleanup` | Hoàn tất bookkeeping và cleanup cuối |

Các phase có thể lặp lại theo vòng xử lý dead tuples; không giả định mỗi phase chỉ xuất hiện đúng một lần.

### 5.4. Query xem tiến độ VACUUM

~~~sql
SELECT
    p.pid,
    p.datname,
    p.relid::regclass AS relation,
    p.phase,
    p.heap_blks_total,
    p.heap_blks_scanned,
    round(
        100.0 * p.heap_blks_scanned /
        NULLIF(p.heap_blks_total, 0),
        1
    ) AS scan_percent,
    p.heap_blks_vacuumed,
    p.index_vacuum_count,
    p.num_dead_tuples,
    p.max_dead_tuples,
    now() - a.query_start AS elapsed,
    a.wait_event_type,
    a.wait_event,
    a.query
FROM pg_stat_progress_vacuum AS p
LEFT JOIN pg_stat_activity AS a USING (pid)
ORDER BY a.query_start;
~~~

`scan_percent` chỉ là phần heap blocks đã scan. Nó không phải phần trăm tổng công việc VACUUM. Nếu phase là `vacuuming indexes`, scan có thể đã hoàn thành nhưng tác vụ vẫn còn nhiều việc.

### 5.5. Scan progress và vacuum progress

`heap_blks_scanned` thể hiện scan progress; `heap_blks_vacuumed` thể hiện heap blocks đã được xử lý. Hai counters không nhất thiết bằng nhau. Một block có thể không cần vacuum hoặc có thể bị bỏ qua tùy trạng thái visibility.

Không tính (`heap_blks_scanned` + `heap_blks_vacuumed`) / `heap_blks_total` vì hai counters không phải hai phần độc lập của cùng một tổng.

### 5.6. Theo dõi autovacuum

Autovacuum workers cũng xuất hiện trong `pg_stat_progress_vacuum`. Dùng `pg_stat_activity.backend_type` trên version có hỗ trợ hoặc query text/application metadata để phân biệt worker.

~~~sql
SELECT
    p.pid,
    p.datname,
    p.relid::regclass AS relation,
    p.phase,
    p.heap_blks_scanned,
    p.heap_blks_total,
    p.num_dead_tuples,
    a.backend_type,
    a.query_start,
    now() - a.query_start AS elapsed,
    a.wait_event_type,
    a.wait_event
FROM pg_stat_progress_vacuum AS p
JOIN pg_stat_activity AS a USING (pid)
ORDER BY a.query_start;
~~~

Nếu `backend_type` không có trên server cũ, bỏ cột đó. Autovacuum worker có thể thực hiện VACUUM hoặc ANALYZE tùy trigger/configuration; xem query/command context khi cần.

### 5.7. Dead tuples và index vacuum cycles

`num_dead_tuples` cho biết số dead tuples hiện được giữ trong memory store; khi store đạt giới hạn, VACUUM có thể xử lý indexes rồi quay lại scan/cleanup. `index_vacuum_count` tăng qua các vòng vacuum index.

Một table có rất nhiều dead tuples hoặc nhiều indexes có thể cần nhiều vòng. Đừng kết luận bị treo chỉ vì phase `vacuuming indexes` kéo dài; kiểm tra I/O, locks, counters và log.

### 5.8. VACUUM có thể chờ hoặc bị ảnh hưởng bởi workload

Các yếu tố làm VACUUM chậm:

- Table lớn, nhiều dead tuples;
- Nhiều indexes cần cleanup;
- Storage I/O chậm hoặc contention;
- `maintenance_work_mem` thấp làm tăng số vòng index vacuum;
- Long-running transactions/replication slots giữ xmin và khiến tuples chưa thể reclaim;
- I/O throttling và cost delay;
- Lock/DDL contention;
- WAL/checkpoint pressure.

VACUUM thường lấy lock tương đối nhẹ, nhưng vẫn có thể xung đột với một số DDL/operations. Theo dõi wait events và blockers.

### 5.9. VACUUM FULL dùng progress view khác

`VACUUM FULL` viết lại relation và cần lock `ACCESS EXCLUSIVE`. Tiến độ của nó được báo qua `pg_stat_progress_cluster`, không phải `pg_stat_progress_vacuum`. Tương tự, `CLUSTER` cũng dùng progress view này.

### 5.10. Theo dõi ANALYZE

`pg_stat_progress_analyze` theo dõi ANALYZE khi server có hỗ trợ. Các counters thường bao gồm sample blocks, extended statistics và child tables; phase có thể gồm acquiring sample rows, computing statistics và finalizing.

~~~sql
SELECT
    p.pid,
    p.datname,
    p.relid::regclass AS relation,
    p.phase,
    p.sample_blks_total,
    p.sample_blks_scanned,
    p.ext_stats_total,
    p.ext_stats_computed,
    p.child_tables_total,
    p.child_tables_done,
    now() - a.query_start AS elapsed,
    a.wait_event_type,
    a.wait_event,
    a.query
FROM pg_stat_progress_analyze AS p
LEFT JOIN pg_stat_activity AS a USING (pid);
~~~

Các columns có thể khác giữa major versions. ANALYZE lấy sample; sample block counters không phải số lượng toàn bộ table blocks đã đọc. Một số phase không có total phù hợp để tính phần trăm.

### 5.11. Theo dõi VACUUM FULL và CLUSTER

~~~sql
SELECT
    p.pid,
    p.datname,
    p.relid::regclass AS relation,
    p.command,
    p.phase,
    p.heap_tuples_scanned,
    p.heap_tuples_written,
    p.heap_blks_total,
    p.heap_blks_scanned,
    now() - a.query_start AS elapsed,
    a.wait_event_type,
    a.wait_event
FROM pg_stat_progress_cluster AS p
LEFT JOIN pg_stat_activity AS a USING (pid);
~~~

`command` phân biệt CLUSTER và VACUUM FULL. Các phase gồm scan heap, sort tuples, write new heap, swap relation files, recreate indexes và final cleanup tùy command/version.

### 5.12. Khi VACUUM chạy lâu

Kiểm tra:

1. Phase và counters có tăng qua các snapshots không;
2. `pg_stat_activity` có wait event hay không;
3. Blocking DDL/transaction;
4. Long-running transactions và replication slots giữ xmin;
5. Dead tuple volume, table size, index count;
6. Disk latency, throughput và free space;
7. Autovacuum logs, cost delay và worker limits.

Không kill VACUUM chỉ vì elapsed time lớn. Đầu tiên xác định nó đang tiến triển, chờ lock, chờ I/O hay bị giữ lại bởi transaction lâu.

## 6. Theo dõi CREATE INDEX và REINDEX

### 6.1. Vì sao index build cần progress reporting?

Tạo index có thể đọc hàng triệu/hàng tỷ rows, sort tuples, ghi index pages và chờ transactions khác. Với `CREATE INDEX CONCURRENTLY`, PostgreSQL phải thực hiện thêm các bước validation và chờ snapshots/transactions cũ để bảo đảm index an toàn cho concurrent writes.

### 6.2. Progress view

`pg_stat_progress_create_index` theo dõi `CREATE INDEX`, `CREATE INDEX CONCURRENTLY`, `REINDEX` và các biến thể tương ứng khi có hỗ trợ.

| Cột | Ý nghĩa |
| --- | --- |
| `pid` | Backend PID |
| `datid`, `datname` | Database |
| `relid` | Table đang được index |
| `index_relid` | OID của index đang tạo/rebuild |
| `command` | CREATE INDEX hoặc REINDEX command |
| `phase` | Phase hiện tại |
| `lockers_total`, `lockers_done` | Số transaction/locker cần chờ và đã xử lý trong phase liên quan |
| `current_locker_pid` | PID của locker hiện đang được chờ, nếu có |
| `blocks_total`, `blocks_done` | Block progress của phase hiện tại |
| `tuples_total`, `tuples_done` | Tuple progress của phase hiện tại |
| `partitions_total`, `partitions_done` | Partition progress với partitioned index |

Ý nghĩa/cách cập nhật counters phụ thuộc phase; không phải tất cả counters đều có giá trị hữu ích trong mọi phase.

### 6.3. Các phase chính

| Phase | Diễn giải |
| --- | --- |
| `initializing` | Chuẩn bị index build |
| `waiting for writers before build` | Chờ transactions có thể ghi vào table trước khi bắt đầu build |
| `building index` | Scan table/build index |
| `waiting for writers before validation` | Chờ writers trước validation của concurrent build |
| `index validation: scanning index` | Scan index để validation |
| `index validation: sorting tuples` | Sort tuple identifiers phục vụ validation |
| `index validation: scanning table` | Scan table để kiểm tra entries |
| `waiting for old snapshots` | Chờ snapshots cũ không còn cần thiết |
| `waiting for readers before marking dead` | Chờ readers trước khi đánh dấu index cũ/invalid state theo bước cleanup |

Một số phase chỉ xuất hiện với concurrent build hoặc các biến thể nhất định. Tên phase/counters phải đối chiếu đúng PostgreSQL major version.

### 6.4. Query theo dõi index build

~~~sql
SELECT
    p.pid,
    p.datname,
    p.relid::regclass AS table_name,
    p.index_relid::regclass AS index_name,
    p.command,
    p.phase,
    p.lockers_total,
    p.lockers_done,
    p.current_locker_pid,
    p.blocks_total,
    p.blocks_done,
    round(
        100.0 * p.blocks_done / NULLIF(p.blocks_total, 0),
        1
    ) AS blocks_percent,
    p.tuples_total,
    p.tuples_done,
    p.partitions_total,
    p.partitions_done,
    now() - a.query_start AS elapsed,
    a.wait_event_type,
    a.wait_event,
    a.query
FROM pg_stat_progress_create_index AS p
LEFT JOIN pg_stat_activity AS a USING (pid)
ORDER BY a.query_start;
~~~

`blocks_percent` chỉ phản ánh block progress khi counters tương ứng phase có ý nghĩa. Trong phase chờ lockers hoặc old snapshots, counters có thể đứng yên; điều đó không tự chứng minh backend bị treo.

### 6.5. Theo dõi partitioned index

Khi build index trên partitioned table, progress view có thể cung cấp `partitions_total` và `partitions_done`. Dùng hai counters này để biết số partitions đã xử lý, nhưng không suy ra bytes/tổng thời gian còn lại vì các partitions có kích thước khác nhau.

### 6.6. CREATE INDEX thường và CONCURRENTLY

`CREATE INDEX` thường có thể chặn writes vào table trong thời gian build do lock mode. Nó thường nhanh hơn và phù hợp khi có maintenance window.

`CREATE INDEX CONCURRENTLY` cho phép INSERT/UPDATE/DELETE tiếp tục trong phần lớn quá trình, nhưng tốn nhiều công việc hơn, có nhiều phase chờ/validation và có thể mất thời gian dài hơn. Nó không thể chạy bên trong transaction block.

### 6.7. Vì sao concurrent build đứng ở phase chờ?

`CREATE INDEX CONCURRENTLY` có thể chờ transaction cũ hoặc snapshot lâu. Kiểm tra:

- `current_locker_pid`;
- `pg_stat_activity.xact_start` và `backend_xmin`;
- Long-running queries/transactions;
- Idle in transaction sessions;
- Prepared transactions;
- Replication feedback/standby snapshots khi liên quan.

Đừng chỉ tăng `lock_timeout` hoặc cancel blocker mà không hiểu transaction đang làm gì.

### 6.8. Xác định blocker

~~~sql
SELECT
    p.pid AS index_build_pid,
    p.phase,
    p.current_locker_pid,
    a.usename AS blocker_user,
    a.datname AS blocker_database,
    a.application_name,
    a.state,
    a.xact_start,
    now() - a.xact_start AS transaction_age,
    a.wait_event_type,
    a.wait_event,
    a.query
FROM pg_stat_progress_create_index AS p
LEFT JOIN pg_stat_activity AS a
  ON a.pid = p.current_locker_pid;
~~~

`current_locker_pid` có thể NULL nếu không ở phase chờ locker. Dùng `pg_blocking_pids()` và `pg_locks` để điều tra các quan hệ lock khác.

### 6.9. Index build bị cancel

Nếu `CREATE INDEX CONCURRENTLY` bị cancel/fail, có thể để lại index invalid. Kiểm tra catalog:

~~~sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    i.indisready,
    i.indisvalid,
    i.indislive
FROM pg_index AS i
JOIN pg_class AS idx ON idx.oid = i.indexrelid
JOIN pg_class AS tbl ON tbl.oid = i.indrelid
JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
WHERE NOT i.indisvalid
ORDER BY ns.nspname, tbl.relname, idx.relname;
~~~

Index invalid không được planner sử dụng như index hợp lệ, nhưng có thể vẫn chiếm storage và trong một số trạng thái tiếp tục nhận maintenance overhead. Xác định nguyên nhân, sau đó DROP/REINDEX theo quy trình phù hợp; không xóa file index thủ công.

### 6.10. Theo dõi index build song song

Parallel index build có thể dùng nhiều workers. Progress row chính thuộc backend thực hiện command; workers không nhất thiết tạo nhiều hàng độc lập trong progress view. Theo dõi CPU, I/O và `pg_stat_activity` để đánh giá worker activity.

### 6.11. REINDEX và concurrent REINDEX

`REINDEX` rebuild index và có thể gây lock tùy mode. `REINDEX CONCURRENTLY` giảm mức blocking nhưng thêm các bước chờ/validation và yêu cầu nhiều tài nguyên hơn. Progress view giúp phân biệt đang build hay đang chờ readers/writers.

### 6.12. Kiểm tra kết quả sau build

Sau khi command kết thúc:

- Kiểm tra client nhận success;
- Kiểm tra `pg_index.indisvalid` và `indisready`;
- Xác nhận index tồn tại trong schema mong muốn;
- Kiểm tra query plan khi cần;
- Theo dõi disk usage, WAL generation và replication lag;
- Xem log nếu build thất bại.

Progress đạt 100% trong một phase không đồng nghĩa toàn bộ command đã commit thành công.

## 7. Theo dõi COPY FROM và COPY TO

### 7.1. Progress view

`pg_stat_progress_copy` theo dõi lệnh `COPY` đang chạy ở server. Các cột chính:

| Cột | Ý nghĩa |
| --- | --- |
| `pid` | Backend PID |
| `datid`, `datname` | Database |
| `relid` | Relation liên quan; có thể bằng 0 với COPY query TO |
| `command` | `COPY FROM` hoặc `COPY TO` |
| `type` | Nguồn/đích dữ liệu như FILE, PROGRAM, PIPE hoặc CALLBACK |
| `bytes_processed` | Số bytes đã xử lý |
| `bytes_total` | Tổng bytes nếu server biết được |
| `tuples_processed` | Số tuples đã xử lý |
| `tuples_excluded` | Số tuples bị loại bởi WHERE clause trên các version hỗ trợ |

Một số cột/semantics phụ thuộc major version. Ví dụ `tuples_excluded` liên quan khả năng `COPY FROM ... WHERE` của version mới.

### 7.2. Query theo dõi COPY

~~~sql
SELECT
    p.pid,
    p.datname,
    CASE
        WHEN p.relid = 0 THEN NULL
        ELSE p.relid::regclass::text
    END AS relation,
    p.command,
    p.type,
    p.bytes_processed,
    p.bytes_total,
    round(
        100.0 * p.bytes_processed / NULLIF(p.bytes_total, 0),
        1
    ) AS bytes_percent,
    p.tuples_processed,
    p.tuples_excluded,
    now() - a.query_start AS elapsed,
    a.application_name,
    a.wait_event_type,
    a.wait_event,
    a.query
FROM pg_stat_progress_copy AS p
LEFT JOIN pg_stat_activity AS a USING (pid);
~~~

Khi `bytes_total` là 0 hoặc không biết, `bytes_percent` là NULL. Dùng `tuples_processed` làm counter hoạt động, nhưng không chia cho một total không tồn tại.

### 7.3. COPY FROM file trên server

Với `COPY table FROM '/path/file.csv'`, file được server process đọc. `bytes_total` có thể biết được nếu nguồn là regular file và server truy cập được metadata. Server-side file access cần quyền filesystem của OS user chạy PostgreSQL và quyền SQL tương ứng.

### 7.4. COPY FROM STDIN và psql \copy

Với `COPY ... FROM STDIN`, dữ liệu được client gửi qua connection. Server thường không biết tổng bytes trước khi nhận hết nên không có total đáng tin cậy.

Lệnh psql `\copy` đọc/ghi file ở phía client rồi chuyển stream qua connection. Trên server, operation vẫn được quan sát như COPY qua pipe/callback; server không thể tự đọc file path local của máy client.

### 7.5. COPY TO file và COPY TO STDOUT

`COPY table TO '/path/file.csv'` ghi file ở phía server. `COPY ... TO STDOUT` gửi bytes về client. Với query COPY TO, `relid` có thể không đại diện cho một table cụ thể; xem `command` và query text để xác định nguồn.

### 7.6. Đo tốc độ COPY

Chụp `bytes_processed` hoặc `tuples_processed` ở hai thời điểm:

\[
\text{Throughput} =
\frac{\text{Counter}_{t2} - \text{Counter}_{t1}}{t2-t1}
\]

Đơn vị là bytes/s hoặc tuples/s. Nếu counter reset do backend mới, PID đổi hoặc operation kết thúc, bắt đầu một series mới.

### 7.7. COPY chậm do đâu?

Các nguyên nhân phổ biến:

- Disk/network throughput;
- Source file nằm trên storage chậm;
- Client upload/download chậm;
- WAL generation và synchronous replication;
- Index/foreign key/trigger maintenance khi COPY FROM;
- Constraint checks;
- Row-level security hoặc conversion/encoding;
- Lock contention;
- Checkpoint/I/O pressure;
- Compression/decompression ở client hoặc pipeline.

### 7.8. COPY FROM có thể làm replication lag tăng

Bulk load tạo WAL nhanh. Nếu standby hoặc WAL archive không theo kịp, potential RPO và disk retention risk tăng. Theo dõi `pg_stat_replication`, `pg_stat_archiver`, replication slots và disk trong lúc import lớn.

### 7.9. COPY bị cancel hoặc lỗi

Khi COPY thất bại, progress row biến mất và transaction có thể rollback phần thay đổi theo transaction semantics. Kiểm tra client error, server logs và transaction state. Không coi counter cuối cùng là số rows đã commit.

### 7.10. COPY và monitoring phía client

Nếu dùng psql `\copy`, GUI, ETL hoặc application driver, client có thể hiển thị progress riêng. Server progress view phản ánh phần server đã xử lý, có thể khác số bytes đã đọc ở client hoặc bytes đã ghi xuống file cuối.

## 8. Theo dõi pg_basebackup

### 8.1. Progress view

`pg_stat_progress_basebackup` theo dõi các lệnh `pg_basebackup` đang kết nối tới server qua replication protocol. View thường gồm:

| Cột | Ý nghĩa |
| --- | --- |
| `pid` | PID của replication connection trên server |
| `phase` | Phase backup hiện tại |
| `backup_total` | Tổng bytes ước tính cho backup |
| `backup_streamed` | Bytes database files đã stream |
| `tablespaces_total` | Số tablespaces cần chuyển |
| `tablespaces_streamed` | Số tablespaces đã chuyển xong |
| `tablespace_total` | Tổng bytes của tablespace hiện tại |
| `tablespace_streamed` | Bytes đã stream của tablespace hiện tại |

Các giá trị có thể chưa biết trong giai đoạn đầu hoặc tùy format/metadata. Không tính phần trăm nếu total bằng zero.

### 8.2. Các phase base backup

| Phase | Diễn giải |
| --- | --- |
| `initializing` | Chuẩn bị backup |
| `waiting for checkpoint to finish` | Chờ checkpoint cần thiết hoàn tất |
| `estimating backup size` | Ước lượng kích thước backup |
| `streaming database files` | Stream data files và tablespaces |
| `waiting for WAL archiving to finish` | Chờ WAL archive khi backup method cần điều kiện này |
| `transferring WAL files` | Chuyển WAL files vào backup |

Tên phase và hành vi phụ thuộc version và WAL method. `pg_basebackup` có thể cần chờ WAL archive trong một số cấu hình `-X fetch`.

### 8.3. Query theo dõi base backup

~~~sql
SELECT
    p.pid,
    p.phase,
    p.backup_total,
    p.backup_streamed,
    round(
        100.0 * p.backup_streamed / NULLIF(p.backup_total, 0),
        1
    ) AS backup_percent,
    p.tablespaces_total,
    p.tablespaces_streamed,
    p.tablespace_total,
    p.tablespace_streamed,
    now() - a.backend_start AS connection_age,
    a.usename,
    a.application_name,
    a.client_addr,
    a.wait_event_type,
    a.wait_event
FROM pg_stat_progress_basebackup AS p
LEFT JOIN pg_stat_activity AS a USING (pid);
~~~

`backup_percent` là tỷ lệ bytes database files đã stream so với total estimate, không bao gồm mọi công việc hậu kỳ/WAL transfer theo cùng một cách. Khi phase chuyển sang chờ WAL, phần trăm bytes có thể đứng yên dù backup vẫn đang tiến triển.

### 8.4. pg_basebackup và WAL method

- `-X stream`: stream WAL song song với database files; progress backup bytes có thể hoàn thành trước khi WAL stream kết thúc.
- `-X fetch`: lấy WAL ở cuối backup; có thể chờ archive hoàn tất và cần đủ WAL segment từ đầu tới cuối backup.
- `-X none`: không đưa WAL vào backup; cần quy trình WAL bên ngoài bảo đảm khả năng recovery/consistency.

Đọc tài liệu đúng major version để xác nhận options và điều kiện hỗ trợ.

### 8.5. Backup lớn và nhiều tablespaces

Với nhiều tablespaces, `tablespaces_streamed` cho biết số tablespaces đã xong; `tablespace_streamed/total` có thể biểu diễn progress của tablespace hiện tại. Không cộng các counters có phạm vi khác nhau để tính tổng phần trăm.

### 8.6. Backup progress không phải backup verification

Progress row biến mất khi server kết thúc replication backup session. Điều đó không chứng minh file backup đã được ghi đầy đủ, manifest hợp lệ hoặc có thể restore. Dùng `pg_verifybackup` khi backup format/major version hỗ trợ và thực hiện restore test.

### 8.7. Backup manager bên ngoài

`pg_stat_progress_basebackup` theo dõi `pg_basebackup`. Công cụ như pgBackRest, Barman hoặc giải pháp cloud có thể dùng cơ chế riêng; chúng không nhất thiết xuất hiện trong view này. Dùng metrics/logs của công cụ đó và đối chiếu với PostgreSQL activity.

### 8.8. Backup progress và WAL archive

Một base backup có thể stream data nhanh nhưng chờ WAL lâu. Kiểm tra `pg_stat_archiver`, archive command errors, network/object storage latency và WAL retention. Đừng kết luận backup bị treo chỉ từ `backup_percent` đứng yên ở phase chờ.

### 8.9. Backup client disconnected

Nếu client `pg_basebackup` bị disconnect, replication connection trên server kết thúc và progress row biến mất. Kiểm tra exit code/output phía client, server logs, slot state và output directory; dọn/giữ partial backup theo chính sách của backup tool.

### 8.10. Theo dõi nhiều backups

Mỗi replication connection có PID riêng. Dùng `application_name`, `client_addr` và thời điểm connection để phân biệt job. Đặt tên application rõ ràng khi tool hỗ trợ, và tránh chạy quá nhiều base backups đồng thời làm cạnh tranh I/O/network.

## 9. Kết hợp progress với activity, locks và statistics

### 9.1. Progress cho biết tiến độ; activity cho biết trạng thái chờ

Một task có thể có counter không tăng vì đang chờ lock, I/O, WAL, network hoặc transaction khác. Kết hợp:

- Progress view: phase và counters;
- `pg_stat_activity`: state, query, xact age, wait event;
- `pg_locks`/`pg_blocking_pids()`: lock blockers;
- OS/cloud metrics: disk, CPU, network;
- PostgreSQL logs: errors, cancellation và checkpoint details.

Không kết luận tác vụ bị treo chỉ từ một snapshot.

### 9.2. Tìm blocking sessions

~~~sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.usename AS blocked_user,
    blocked.application_name AS blocked_app,
    now() - blocked.query_start AS blocked_duration,
    blocked.wait_event_type,
    blocked.wait_event,
    left(blocked.query, 250) AS blocked_query,
    blocker.pid AS blocker_pid,
    blocker.usename AS blocker_user,
    blocker.application_name AS blocker_app,
    blocker.state AS blocker_state,
    blocker.xact_start AS blocker_xact_start,
    now() - blocker.xact_start AS blocker_xact_age,
    left(blocker.query, 250) AS blocker_query
FROM pg_stat_activity AS blocked
CROSS JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) AS b(pid)
JOIN pg_stat_activity AS blocker ON blocker.pid = b.pid
ORDER BY blocked.query_start;
~~~

`pg_blocking_pids()` có thể trả nhiều blockers. Một task có thể chờ một transaction đã idle in transaction; query và `xact_start` của blocker giúp tìm nguyên nhân.

### 9.3. Tìm transaction lâu

~~~sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    state,
    xact_start,
    now() - xact_start AS xact_age,
    backend_xmin,
    wait_event_type,
    wait_event,
    left(query, 300) AS query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Long-running transaction có thể giữ snapshot cũ, ngăn VACUUM reclaim tuples hoặc làm concurrent index build chờ old snapshots. Không terminate chỉ dựa vào tuổi; xác minh owner và business impact trước.

### 9.4. Theo dõi table maintenance counters

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    n_mod_since_analyze,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count,
    last_analyze,
    last_autoanalyze,
    analyze_count,
    autoanalyze_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
~~~

Đây là statistics tích lũy/ước lượng, không phải progress của VACUUM đang chạy. `n_live_tup` và `n_dead_tup` là estimates; dùng để tìm table đáng chú ý, không thay thế kiểm tra thực tế.

### 9.5. Theo dõi index usage sau build

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    indexrelname AS index_name,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
ORDER BY pg_relation_size(indexrelid) DESC
LIMIT 50;
~~~

Index mới tạo có thể chưa được planner sử dụng ngay vì workload chưa chạy query phù hợp. Không drop index chỉ vì `idx_scan = 0` trong một cửa sổ quan sát ngắn.

### 9.6. Theo dõi database-level COPY/tuple activity

~~~sql
SELECT
    datname,
    tup_inserted,
    tup_updated,
    tup_deleted,
    conflicts,
    deadlocks,
    temp_files,
    temp_bytes,
    stats_reset
FROM pg_stat_database
ORDER BY datname;
~~~

Các counters này tích lũy theo database và không chỉ dành cho COPY. Chúng hỗ trợ đối chiếu hoạt động tổng thể nhưng không thay thế `pg_stat_progress_copy`.

### 9.7. Theo dõi WAL/archive trong bulk load và backup

~~~sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
~~~

Kết hợp với `pg_stat_replication` để xem standby send/write/flush/replay lag. Một COPY lớn hoặc index build có thể làm WAL generation tăng, ảnh hưởng standby và archive.

### 9.8. Statistics snapshot và polling

Statistics views có cơ chế snapshot/caching theo transaction và version. Khi chạy nhiều query trong cùng transaction, số liệu có thể không refresh như mong đợi. Dùng autocommit hoặc `pg_stat_clear_snapshot()` khi cần lấy snapshot mới trong session hỗ trợ.

Progress views thường phản ánh trạng thái hiện tại của backend; vẫn nên polling có khoảng nghỉ hợp lý thay vì vòng lặp truy vấn liên tục.

## 10. Thiết kế dashboard tiến độ

### 10.1. Các trường chung

Một bảng dashboard hợp nhất nên có:

| Trường | Mục đích |
| --- | --- |
| collected_at | Timestamp snapshot |
| server/cluster | Nhận diện nguồn |
| pid | Backend PID |
| database | Database |
| relation/index | Đối tượng đang xử lý |
| operation | VACUUM, INDEX, COPY, BASEBACKUP |
| phase | Phase hiện tại |
| done/total | Counters và đơn vị |
| percent | Chỉ khi total hợp lệ |
| elapsed | Thời gian đã chạy |
| wait_event | Nguyên nhân chờ gần nhất |
| application_name | Job/client owner |

Các view có schema khác nhau. Tốt hơn là collector chuẩn hóa mỗi operation thành metric riêng thay vì tạo một SQL query cố ép mọi counters vào cùng ý nghĩa.

### 10.2. Không gộp counters khác đơn vị

Không cộng heap blocks với tuples, bytes với partitions hoặc locker counts để tạo một percentage chung. Mỗi metric phải giữ unit và total tương ứng.

### 10.3. Phase timeline

Lưu phase transitions theo PID + start timestamp. Một operation có thể chuyển phase nhiều lần; dashboard dạng timeline giúp nhận ra thời gian chờ kéo dài hơn một ảnh chụp đơn lẻ.

### 10.4. Xử lý PID reuse

PID có thể được tái sử dụng sau khi backend kết thúc. Ghép series bằng server identity, PID và backend/query start timestamp; không dùng PID một mình làm key lâu dài.

### 10.5. Hiển thị unknown rõ ràng

Nếu total bằng zero, NULL hoặc chưa được tính, hiển thị “N/A”/“unknown”. Không đặt percent = 0 vì 0% hàm ý total đã biết nhưng chưa làm gì; cũng không đặt 100%.

### 10.6. Phân biệt active và waiting

Progress phase có thể vẫn hiện trong khi backend chờ. Hiển thị wait event type/name, blockers và elapsed. Màu sắc dashboard nên phân biệt “đang xử lý”, “đang chờ”, “đã hoàn tất” và “lỗi” theo trạng thái thực tế.

### 10.7. Ghi nhận lịch sử task

Progress views không lưu lịch sử. Collector có thể chụp counters mỗi 5–15 giây tùy workload, lưu phase transitions, operation start/end và kết quả client. Với tác vụ ngắn, dùng log/job runner vì polling có thể bỏ lỡ toàn bộ operation.

### 10.8. Labels và cardinality

Tránh đưa query text đầy đủ, PID mới liên tục hoặc relation names không giới hạn vào labels của metrics time-series nếu backend monitoring có cardinality cost cao. Lưu query text ở log có kiểm soát; metrics dùng labels ổn định.

### 10.9. Dashboard theo từng operation

- VACUUM: relation, phase, heap blocks scanned/vacuumed, dead tuples, transaction age;
- Index: table/index, command, phase, blocks/tuples, lockers/current blocker;
- COPY: direction/type, bytes/tuples, total availability, throughput;
- Base backup: phase, bytes streamed, tablespace progress, WAL/archive wait.

### 10.10. Dashboard không thay runbook

Mỗi panel/alert cần link tới hướng dẫn điều tra: phase nào bình thường, counter nào cần tăng, blocker nào được phép terminate, và khi nào phải escalate.

## 11. Alerting và ngưỡng giám sát

### 11.1. Alert theo trạng thái, không chỉ elapsed time

Một VACUUM chạy 3 giờ có thể bình thường trên table lớn; một concurrent index build chờ lock 10 phút có thể cần điều tra. Alert nên dựa trên loại operation, phase, counter progress, wait event và tác động workload.

### 11.2. VACUUM alerts

Theo dõi:

- Autovacuum không chạy hoặc thường xuyên không bắt kịp write rate;
- `n_dead_tup` tăng kéo dài;
- Table không được vacuum/analyze trong khoảng mong muốn;
- Long-running transactions giữ xmin;
- Transaction ID age tiến gần wraparound danger;
- `pg_wal`/disk pressure tăng do workload hoặc slot retention;
- VACUUM thường xuyên ở phase chờ lâu.

Không đặt alert chỉ vì `last_autovacuum` cũ; table ít thay đổi có thể không cần vacuum gần đây.

### 11.3. Transaction ID wraparound

Theo dõi tuổi `datfrozenxid`:

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;
~~~

Đây là cluster/database health signal quan trọng. Khi tuổi transaction ID cao, ưu tiên điều tra anti-wraparound autovacuum và freeze progress; không tắt autovacuum để giảm tải mà không có kế hoạch thay thế.

### 11.4. Index build alerts

Alert khi:

- Build chờ locker/old snapshots vượt thời gian policy;
- Blocks/tuples không tăng trong khi backend active;
- Build tiêu thụ I/O gây latency cho production;
- Concurrent build fail/cancel;
- Index invalid còn tồn tại sau operation.

Elapsed threshold phải khác nhau cho `CREATE INDEX` và `CREATE INDEX CONCURRENTLY`, và phải tính theo kích thước table.

### 11.5. COPY alerts

Alert theo:

- Throughput giảm mạnh so với baseline;
- `bytes_total` đã biết nhưng progress không tăng;
- Operation chạy quá lâu so với file/row volume;
- WAL/replication/archive lag tăng;
- Disk space gần đầy;
- COPY errors/retries ở client pipeline.

Với STDIN/STDOUT không biết total, theo dõi throughput và client-side progress thay vì percentage.

### 11.6. Base backup alerts

Theo dõi:

- Backup không bắt đầu hoặc không hoàn tất trong cửa sổ;
- Phase chờ checkpoint/WAL archive kéo dài;
- Bytes streamed không tăng;
- Client disconnect/failure;
- Backup output thiếu manifest hoặc verification fail;
- WAL archive gap;
- Storage quota/capacity;
- Backup age vượt RPO/retention policy.

Backup job success cần xác nhận exit status và artifact/manifest, không chỉ progress view biến mất.

### 11.7. Alert theo business impact

Đặt ngưỡng dựa trên:

- Maintenance window;
- Workload peak;
- RPO/RTO;
- Disk free headroom;
- Latency/error budget;
- Maximum allowed lock wait;
- Backup completion deadline.

Ngưỡng cụ thể phải được xác định từ baseline và restore/failover drills.

### 11.8. Tránh alert storm

Gộp alert theo operation/PID/table, dùng for duration và hysteresis để tránh cảnh báo bật/tắt liên tục. Khi một tác vụ đã được incident owner xử lý, giữ context/annotations để người trực sau không điều tra lại từ đầu.

## 12. Troubleshooting theo từng tác vụ

### 12.1. VACUUM scan percentage đứng yên

Kiểm tra:

1. Phase hiện tại;
2. `wait_event_type`/`wait_event`;
3. Disk throughput/latency;
4. Blocking locks;
5. Long-running transactions và `backend_xmin`;
6. Autovacuum cost delay và worker availability;
7. Có phải counters đã đạt total nhưng đang xử lý index/cleanup phase không.

### 12.2. VACUUM ở phase vacuuming indexes rất lâu

Kiểm tra số indexes, kích thước index, `maintenance_work_mem`, dead tuple volume, storage latency và `index_vacuum_count`. Một VACUUM có thể cần nhiều vòng xử lý; theo dõi counter qua nhiều snapshots.

### 12.3. VACUUM FULL không có row trong pg_stat_progress_vacuum

Đây là hành vi dự kiến. VACUUM FULL được theo dõi qua `pg_stat_progress_cluster`. Đồng thời xác định session có đang chờ `ACCESS EXCLUSIVE` lock hay không.

### 12.4. Autovacuum không xuất hiện

Kiểm tra autovacuum có bật, worker limits, table-specific storage parameters, threshold/scale factor, transaction age, logs và liệu table có vượt trigger threshold. Một table ít thay đổi có thể không cần autovacuum.

### 12.5. CREATE INDEX đứng ở waiting for writers

Xem `current_locker_pid`, `pg_stat_activity`, transaction age và application owner. Xác định session nào giữ transaction lâu; phối hợp owner trước khi cancel/terminate.

### 12.6. CREATE INDEX CONCURRENTLY đứng ở waiting for old snapshots

Tìm long-running transactions, idle-in-transaction sessions, prepared transactions và standby feedback. Một snapshot cũ có thể giữ bước validation không hoàn tất dù index đã được build gần xong.

### 12.7. CREATE INDEX bị fail nhưng index còn trong catalog

Kiểm tra `pg_index.indisvalid`, `indisready` và server log. Index invalid có thể còn tồn tại sau concurrent build failure. Xác định index có được planner sử dụng hay không, sau đó drop/rebuild theo quy trình được hỗ trợ.

### 12.8. COPY bytes percent không hiển thị

Nếu `bytes_total` là zero/NULL, server không biết tổng nguồn/đích. Điều này thường gặp với STDIN/STDOUT hoặc streaming input. Theo dõi `tuples_processed`, byte throughput và client metrics.

### 12.9. COPY throughput thấp

Phân tách thời gian đọc source, truyền network, parse/convert, insert, index/constraint/trigger và WAL flush. Test riêng source storage/client network/server storage để tìm bottleneck.

### 12.10. COPY hoàn tất nhưng row count khác kỳ vọng

Kiểm tra client row count, `WHERE` clause nếu version hỗ trợ, error/reject behavior theo version, duplicate/constraint errors, transaction rollback và rows bị loại. Progress counters không phải bằng chứng số rows đã commit.

### 12.11. pg_basebackup phase chờ WAL archive

Kiểm tra `archive_mode`, `archive_command`, `pg_stat_archiver`, archive destination permissions/network và WAL segment cần thiết. Đừng xóa WAL đang cần để “giải phóng” archive.

### 12.12. pg_basebackup bytes đứng yên

Kiểm tra server-side wait events, source disk I/O, client disk throughput, network, tablespace mount và client process. Xác minh process còn sống và không chờ filesystem/object storage.

### 12.13. Backup progress row biến mất

Xác minh client exit code, logs và backup directory/manifest. Row biến mất có thể do success, failure hoặc disconnect.

### 12.14. Monitoring query báo column does not exist

Xác minh PostgreSQL major version và columns hiện có trong progress view. Điều chỉnh query theo version; tránh deploy một query dashboard duy nhất giả định mọi server có schema giống nhau.

### 12.15. User không nhìn thấy query text

Kiểm tra quyền đọc statistics và role membership. Cấp `pg_monitor`/`pg_read_all_stats` theo policy nếu cần; không cấp superuser rộng rãi.

## 13. Operational workflow cho maintenance window

### 13.1. Trước khi bắt đầu

Ghi nhận:

- Database/table/index target;
- Dung lượng heap/index và row estimates;
- Dead tuple estimates;
- Workload/peak window;
- Disk headroom và I/O baseline;
- Replication lag và WAL archive health;
- Locking impact;
- Người sở hữu operation và cancellation plan.

### 13.2. Trong khi chạy

1. Ghi PID và query start;
2. Poll đúng progress view;
3. Ghi phase/counters/wait events;
4. Kiểm tra application latency và I/O;
5. Theo dõi standby/archive lag;
6. Ghi nhận blockers và escalation owner;
7. Không thay đổi cấu hình nhiều lần khi chưa xác định bottleneck.

### 13.3. Khi hoàn tất

Xác nhận client exit status, log, catalog state và tác động workload. Với VACUUM/ANALYZE, kiểm tra table statistics; với index build, kiểm tra validity; với COPY, đối chiếu row counts/constraints; với backup, xác minh manifest và restore test.

### 13.4. Khi cần cancel

Ưu tiên `pg_cancel_backend(pid)` để gửi cancel tới query. Chỉ cân nhắc `pg_terminate_backend(pid)` khi cần dừng session và đã đánh giá transaction rollback/impact. Không kill postmaster hoặc xóa relation/WAL files để dừng operation.

### 13.5. Sau maintenance

Đo lại latency, query plans, dead tuples, replication lag, WAL/archive backlog và disk. Ghi actual duration/phase durations vào runbook để cải thiện dự báo lần sau.

## 14. Ví dụ thực hành trong lab

### 14.1. Chuẩn bị bảng thử nghiệm

~~~sql
CREATE TABLE progress_demo (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payload text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO progress_demo (payload)
SELECT repeat(md5(g::text), 4)
FROM generate_series(1, 1000000) AS g;
~~~

Quy mô lab cần điều chỉnh theo máy. Không chạy bulk load lớn trên production chỉ để quan sát progress.

### 14.2. Quan sát VACUUM

~~~sql
UPDATE progress_demo
SET payload = payload || 'x'
WHERE id % 3 = 0;

DELETE FROM progress_demo
WHERE id % 5 = 0;

VACUUM (VERBOSE) progress_demo;
~~~

Trong một session khác, query `pg_stat_progress_vacuum` liên tục để xem phase và counters. Với table nhỏ, operation có thể hoàn tất trước lần poll đầu tiên.

### 14.3. Quan sát ANALYZE

~~~sql
ANALYZE progress_demo;
~~~

Query `pg_stat_progress_analyze` trong session thứ hai. Sample thường nhanh với table nhỏ; tăng dữ liệu lab hoặc dùng table lớn hơn để quan sát rõ.

### 14.4. Quan sát CREATE INDEX

~~~sql
CREATE INDEX progress_demo_payload_idx
ON progress_demo (payload);
~~~

Theo dõi `pg_stat_progress_create_index`. Lặp lại trong lab với `CREATE INDEX CONCURRENTLY` ngoài transaction block để quan sát các phase validation/waiting.

### 14.5. Quan sát COPY

~~~sql
COPY progress_demo TO '/tmp/progress_demo.csv' WITH (FORMAT csv, HEADER true);
~~~

Đường dẫn phải tồn tại và server OS user có quyền ghi. Nếu không có quyền filesystem, dùng `COPY ... TO STDOUT`/client `\copy` và quan sát bytes/tuples theo khả năng của server.

### 14.6. Quan sát base backup

Chạy `pg_basebackup` từ một lab server có replication access và theo dõi `pg_stat_progress_basebackup` trên source server. Đặt `application_name` nếu client/tool hỗ trợ để nhận diện job.

### 14.7. Lưu snapshots

Chụp progress query định kỳ vào file/monitoring store. So sánh counters qua thời gian để tính throughput và nhận biết phase chờ.

## 15. Những giới hạn cần nhớ

### 15.1. Không phải mọi tác vụ đều có progress view

Chỉ các operations được instrument mới xuất hiện. Một lệnh SQL tùy chỉnh, extension hoặc backup tool bên ngoài có thể không có progress view tương ứng.

### 15.2. Không có phần trăm chung cho mọi phase

Counters có thể đổi ý nghĩa giữa phases. Một phần trăm block scan không phải phần trăm toàn bộ command; một số phase là waits và không có total.

### 15.3. Total có thể chưa biết hoặc là estimate

Backup size có thể được ước lượng; COPY stream có thể không có total; ANALYZE dùng sample. Hiển thị unknown thay vì tự tạo denominator.

### 15.4. Progress row không lưu lịch sử

Khi operation kết thúc, row biến mất. Cần collector/logging nếu muốn biết duration, outcome và phase timeline sau sự kiện.

### 15.5. Permissions có thể che thông tin

Một số users không nhìn thấy query text hoặc statistics của session khác. Dùng monitoring role có phạm vi phù hợp.

### 15.6. Version compatibility

Progress views/counters/phase names thay đổi theo major version. Kiểm tra documentation và system catalogs của server thực tế trước khi triển khai dashboard.

### 15.7. Polling không thay metrics hệ điều hành

Progress view không cung cấp đầy đủ disk latency, queue depth, CPU steal, network retransmits hoặc cloud storage throttling. Kết hợp OS/cloud telemetry để tìm bottleneck.

### 15.8. Không dự đoán ETA quá chính xác

Workload và phase thay đổi khiến ETA biến động. Nên hiển thị range/ước lượng kèm timestamp sample, hoặc bỏ ETA khi counters không phù hợp.

## 16. Thu thập progress bằng psql và monitoring agent

### 16.1. Poll thủ công bằng psql

Có thể chạy query progress trong psql và dùng `\watch` để lặp:

~~~sql
SELECT
    pid,
    relid::regclass AS relation,
    phase,
    heap_blks_scanned,
    heap_blks_total
FROM pg_stat_progress_vacuum;
~~~

Sau khi chạy query, nhập `\watch 2` để refresh mỗi hai giây. `\watch` là psql meta-command, không phải SQL gửi tới server.

### 16.2. Polling interval

Chọn interval theo thời lượng task:

- Task kéo dài vài giờ: 5–30 giây thường đủ cho dashboard;
- Task ngắn: log/event-based monitoring có thể hữu ích hơn polling;
- Production server tải cao: tránh poll nhiều lần mỗi giây trên tất cả databases.

### 16.3. Collector tách operation type

Một monitoring agent có thể chạy các query riêng cho từng progress view và gắn nhãn operation. Đừng dựa vào một query động ghép view name từ user input; giữ query rõ ràng, version-aware và kiểm soát quyền.

### 16.4. Lưu lịch sử

Lưu:

- Server identity và database;
- PID + backend start/query start;
- Relation/index OID và tên đã resolve;
- Operation, command, phase;
- Counters và units;
- Wait events;
- Collected timestamp;
- Job/client identity.

Khi operation kết thúc, lưu event terminal từ client/job runner gồm success/failure/cancel và elapsed time.

### 16.5. Không lưu query text vô hạn

Query text có thể chứa literals nhạy cảm. Chỉ lưu nếu policy cho phép; cân nhắc normalize/redact hoặc giữ trong hệ thống logs có access control. Metrics nên lưu query fingerprint/operation labels thay vì toàn bộ text.

### 16.6. Health of the monitor

Monitor cũng có thể bị lỗi. Theo dõi collector last-success timestamp, query errors, permissions, scrape duration và missing series. Dashboard trống có thể có nghĩa không có task hoặc monitor không đọc được view.

## 17. Bài tập thực hành: progress reporting

Các bài tập dùng PostgreSQL lab. Tạo workload đủ lớn để quan sát nhưng không chạy thử trên production. Với câu hỏi phụ thuộc version, xác minh columns/phase trên server đang học.

### Bài 1 — Activity vs progress

Giải thích sự khác nhau giữa `pg_stat_activity` và `pg_stat_progress_*`. Cho ví dụ một câu hỏi mà mỗi view trả lời tốt hơn.

### Bài 2 — Progress row

Vì sao progress row biến mất khi operation kết thúc? Làm sao giữ lịch sử duration và outcome?

### Bài 3 — VACUUM counters

Phân biệt `heap_blks_scanned` và `heap_blks_vacuumed`. Vì sao không cộng hai counters này để tính percentage?

### Bài 4 — VACUUM phase

Liệt kê các phase chính của `pg_stat_progress_vacuum`. Phase nào cho biết đang xử lý indexes?

### Bài 5 — Autovacuum

Viết query join `pg_stat_progress_vacuum` với `pg_stat_activity` để hiển thị PID, relation, phase, elapsed và wait event.

### Bài 6 — Long transaction

Một VACUUM chạy lâu và dead tuples không giảm. Viết query tìm transactions lâu và giải thích `backend_xmin` có thể ảnh hưởng reclaim như thế nào.

### Bài 7 — VACUUM FULL

Vì sao không thấy VACUUM FULL trong `pg_stat_progress_vacuum`? View nào theo dõi operation này?

### Bài 8 — ANALYZE

Giải thích vì sao sample blocks trong `pg_stat_progress_analyze` không phải tổng blocks của table.

### Bài 9 — Index progress

Viết query hiển thị table, index, command, phase, blocks done/total và elapsed từ `pg_stat_progress_create_index`.

### Bài 10 — Concurrent index wait

Một index build đang ở `waiting for old snapshots`. Nêu ít nhất bốn nguồn snapshot/transaction cần điều tra.

### Bài 11 — Blocker PID

Dùng `current_locker_pid` để tìm session đang chặn index build. Nêu giới hạn khi cột này NULL.

### Bài 12 — Invalid index

Một `CREATE INDEX CONCURRENTLY` bị cancel. Viết query kiểm tra `indisvalid` và giải thích cách xử lý index invalid.

### Bài 13 — COPY progress

Viết query hiển thị command, type, bytes processed/total và tuples processed từ `pg_stat_progress_copy`.

### Bài 14 — COPY STDIN

Vì sao `bytes_total` có thể bằng zero với COPY FROM STDIN? Metric nào nên dùng thay percentage?

### Bài 15 — psql copy

Phân biệt file path của `COPY FROM '/path'` với psql `copy` meta-command. File được đọc ở host nào?

### Bài 16 — COPY throughput

Hai snapshots cách nhau 10 giây: `bytes_processed` tăng từ 100 MB lên 450 MB. Tính throughput trung bình.

### Bài 17 — COPY row count

Vì sao `tuples_processed` không nhất thiết bằng rows đã commit? Nêu ảnh hưởng của WHERE/excluded rows và transaction rollback.

### Bài 18 — Base backup progress

Viết query đọc phase, backup bytes, tablespace progress và connection context từ `pg_stat_progress_basebackup`.

### Bài 19 — Backup phase

Một base backup đã stream hết database files nhưng phase đang chờ WAL archiving. Giải thích vì sao backup chưa hoàn tất.

### Bài 20 — WAL method

So sánh `-X stream`, `-X fetch` và `-X none` trong `pg_basebackup`. Method nào có thể phải chờ archive ở cuối?

### Bài 21 — Backup verification

Vì sao progress row biến mất không chứng minh backup có thể restore? Nêu vai trò của `pg_verifybackup`.

### Bài 22 — External backup manager

Một job pgBackRest không xuất hiện trong `pg_stat_progress_basebackup`. Vì sao điều đó có thể bình thường? Cần lấy metrics từ đâu?

### Bài 23 — ETA

Giải thích cách tính throughput/ETA từ hai snapshots và nêu ba lý do ETA có thể sai.

### Bài 24 — Phase-aware dashboard

Thiết kế dashboard phân biệt processing, waiting, unknown total, completed và failed. Những counters nào không được cộng chung?

### Bài 25 — Permissions

User monitoring nhìn thấy PID nhưng không thấy query text. Kiểm tra quyền nào và vì sao không nên cấp superuser?

### Bài 26 — VACUUM alerts

Đề xuất alerts cho dead tuple growth, autovacuum lag, transaction ID age và long-running transactions.

### Bài 27 — Index build alerts

Một concurrent index build không tăng counters trong 15 phút. Hãy lập các bước điều tra theo thứ tự.

### Bài 28 — Backup alerts

Một backup không hoàn tất trong cửa sổ. Liệt kê metrics/logs cần kiểm tra ở server, client, WAL archive và storage.

### Bài 29 — PID reuse

Vì sao PID không đủ làm định danh duy nhất cho một task trong time-series database? Đề xuất composite key.

### Bài 30 — Capstone: monitoring maintenance và backup

Một PostgreSQL production chạy VACUUM/autovacuum, concurrent index builds, bulk COPY và nightly `pg_basebackup`. Team cần dashboard và alerts để phát hiện blocking, progress stall, WAL pressure và backup failure.

**Yêu cầu:**

1. Xây query cho bốn progress views chính.
2. Join `pg_stat_activity` để lấy user, query, elapsed và wait events.
3. Thiết kế blockers/long-transaction diagnostics.
4. Định nghĩa percentage chỉ khi total hợp lệ.
5. Tính throughput từ counter deltas và xử lý PID reuse.
6. Theo dõi `pg_stat_archiver`, `pg_stat_replication` và disk headroom.
7. Phân biệt progress view với cumulative statistics và client-side progress.
8. Thiết kế alerts theo phase, elapsed, counter stall và business impact.
9. Viết runbook cho VACUUM, index wait, COPY throughput và backup WAL wait.
10. Lưu lịch sử start/end/exit status và xác minh backup sau khi hoàn tất.

**Tiêu chí đạt:** dashboard không tạo phần trăm giả khi total unknown, chỉ ra được blocker/waiting reason, phân biệt task progress với operation outcome và có alert/runbook giúp on-call hành động an toàn.

## 18. Câu hỏi thường gặp

### 18.1. Progress view có lưu lịch sử không?

Không. Đây là trạng thái hiện tại của backend. Muốn xem lịch sử, dùng logs, monitoring collector hoặc job orchestration lưu snapshots và kết quả cuối.

### 18.2. Vì sao query đang active nhưng không có progress row?

Có thể loại command không được instrument, version không hỗ trợ view, operation đã chuyển phase khác, backend không còn chạy tác vụ đó hoặc user không có quyền xem. Kiểm tra `pg_stat_activity` và version.

### 18.3. Có thể tính chính xác phần trăm VACUUM không?

Không có một phần trăm chung chính xác cho toàn VACUUM. `heap_blks_scanned / heap_blks_total` chỉ biểu diễn scan progress; index cleanup, heap vacuum và final cleanup có thể còn tiếp tục.

### 18.4. Vì sao VACUUM FULL nằm trong pg_stat_progress_cluster?

VACUUM FULL viết lại relation tương tự thao tác CLUSTER về mặt tiến trình, nên được theo dõi qua progress view cluster, không phải view VACUUM thường.

### 18.5. Autovacuum có xuất hiện trong progress view không?

Có. Autovacuum worker đang VACUUM xuất hiện trong `pg_stat_progress_vacuum`; ANALYZE có progress view riêng khi version hỗ trợ.

### 18.6. Vì sao VACUUM có thể lặp phase?

Dead tuple store có giới hạn; VACUUM có thể xử lý indexes theo nhiều vòng rồi tiếp tục heap scan/cleanup. Theo dõi `index_vacuum_count` và counters qua thời gian.

### 18.7. CREATE INDEX CONCURRENTLY có luôn không block không?

Nó cho phép writes tiếp tục trong phần lớn quá trình nhưng vẫn có các bước chờ locks/snapshots và có thể bị trì hoãn. Nó không đồng nghĩa không có tác động tới workload.

### 18.8. Index build bị cancel có để lại index không?

Có thể. Kiểm tra `pg_index.indisvalid`/`indisready` và logs. Xử lý index invalid bằng DROP/REINDEX theo quy trình, không xóa file thủ công.

### 18.9. Vì sao index build progress đứng ở waiting?

Thường do transaction/locker hoặc old snapshot. Xem `current_locker_pid`, `pg_stat_activity`, transaction age và blocking relationships.

### 18.10. `blocks_percent` có phải toàn bộ index build percent?

Không. Nó chỉ có ý nghĩa trong phase mà block counters được cập nhật. Concurrent build có validation/wait phases sau khi scan/build.

### 18.11. COPY FROM STDIN có bytes_total không?

Server thường không biết tổng stream bytes trước khi nhận hết, nên `bytes_total` có thể là zero. Dùng `tuples_processed`, throughput và client progress.

### 18.12. `\copy` đọc file ở đâu?

psql đọc file ở máy client rồi stream qua connection. SQL `COPY FROM '/path'` đọc file ở máy server và dùng OS permissions của server process.

### 18.13. `tuples_processed` có bằng rows đã commit?

Không nhất thiết. Rows có thể bị loại, lỗi hoặc transaction rollback. Đối chiếu client result, command success và dữ liệu sau commit.

### 18.14. pg_basebackup progress nằm ở máy client hay server?

`pg_stat_progress_basebackup` được đọc trên PostgreSQL server đang phục vụ replication connection. Client `pg_basebackup -P` cũng có progress output riêng.

### 18.15. Backup bytes đạt 100% nhưng job vẫn chạy?

Có thể đang chờ WAL archive, chuyển WAL files hoặc hoàn tất bước client-side. Xem phase và client output thay vì chỉ nhìn bytes percentage.

### 18.16. pgBackRest có xuất hiện trong pg_stat_progress_basebackup?

Không nhất thiết. View này dành cho `pg_basebackup`; dùng metrics/logs của backup manager tương ứng.

### 18.17. Có thể poll progress mỗi 100 ms không?

Không nên mặc định như vậy. Polling dày làm tăng load và có thể không thêm giá trị. Chọn interval theo thời lượng task và dùng logs/events cho operation ngắn.

### 18.18. User monitoring cần superuser không?

Không. Cấp quyền statistics phù hợp như `pg_monitor` hoặc `pg_read_all_stats` theo policy. Một số thông tin có thể bị che nếu thiếu quyền.

### 18.19. Vì sao progress query báo cột không tồn tại?

Progress view schema thay đổi theo major version. Kiểm tra columns có sẵn trên server và điều chỉnh query/dashboard theo version.

### 18.20. Progress view có thay thế PostgreSQL logs không?

Không. Progress view hiển thị state hiện tại; logs ghi events/errors. Dùng cả hai để điều tra và lưu kết quả operation.

### 18.21. ETA có đáng tin không?

Chỉ là ước lượng từ counter deltas. ETA có thể sai khi phase thay đổi, task chờ lock/I/O hoặc tốc độ workload biến động.

### 18.22. Dashboard nên hiển thị gì khi total là zero?

Hiển thị unknown/N/A. Không chia cho zero và không gán 0% hoặc 100% vì total chưa biết.

### 18.23. Tại sao COPY làm replication lag tăng?

Bulk load tạo WAL nhanh. Nếu network, standby disk/replay hoặc archive không theo kịp, WAL backlog tăng. Theo dõi WAL rate, replication lag, archive và disk.

### 18.24. Làm sao biết backup thực sự dùng được?

Kiểm tra client exit status, manifest/verification, WAL continuity và thực hiện restore test. Progress row biến mất không đủ chứng minh backup hợp lệ.

### 18.25. Có một progress view tổng hợp cho mọi operation không?

Không. Mỗi operation có progress view riêng với counters/units khác nhau. Collector có thể chuẩn hóa dữ liệu nhưng phải giữ semantics gốc.

## 19. Tài liệu PostgreSQL chính thức

Luôn chọn tài liệu đúng major version đang chạy vì progress views, phase names và columns có thể thay đổi:

- [Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html): tổng quan progress reporting và các views.
- [VACUUM Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html#VACUUM-PROGRESS-REPORTING): `pg_stat_progress_vacuum`.
- [CLUSTER Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html#CLUSTER-PROGRESS-REPORTING): CLUSTER và VACUUM FULL.
- [CREATE INDEX Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html#CREATE-INDEX-PROGRESS-REPORTING): index build phases/counters.
- [COPY Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html#COPY-PROGRESS-REPORTING): COPY progress.
- [Base Backup Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html#BASEBACKUP-PROGRESS-REPORTING): `pg_basebackup` progress.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_activity`, locks và statistics views.
- [pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html): options và WAL methods của base backup.
- [COPY](https://www.postgresql.org/docs/current/sql-copy.html): server-side COPY, STDIN/STDOUT và options.
- [VACUUM](https://www.postgresql.org/docs/current/sql-vacuum.html): VACUUM/ANALYZE behavior.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): concurrent index build.
- [REINDEX](https://www.postgresql.org/docs/current/sql-reindex.html): rebuild indexes và concurrent mode.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html): autovacuum, freezing và maintenance.
- [pg_verifybackup](https://www.postgresql.org/docs/current/app-pgverifybackup.html): xác minh backup manifest.

## 20. Tổng kết

Progress reporting giúp DBA quan sát công việc đang diễn ra trong PostgreSQL. Mỗi loại operation có view và counters riêng:

| Operation | Progress view | Chỉ số cần chú ý |
| --- | --- | --- |
| VACUUM/autovacuum | `pg_stat_progress_vacuum` | phase, heap blocks, dead tuples, index vacuum cycles |
| ANALYZE | `pg_stat_progress_analyze` | sample blocks, extended stats, child tables |
| VACUUM FULL/CLUSTER | `pg_stat_progress_cluster` | heap blocks/tuples scanned và written |
| CREATE INDEX/REINDEX | `pg_stat_progress_create_index` | phase, blocks, tuples, lockers, partitions |
| COPY | `pg_stat_progress_copy` | bytes/tuples processed và total |
| pg_basebackup | `pg_stat_progress_basebackup` | phase, bytes streamed, tablespaces |

Hãy kết hợp progress với `pg_stat_activity`, locks, statistics, PostgreSQL logs và OS/cloud metrics. Phần trăm chỉ hợp lệ khi numerator/denominator cùng đơn vị và total đã biết; ETA chỉ là ước lượng. Khi operation kết thúc, progress row biến mất nên cần collector hoặc job logs để lưu lịch sử và outcome.

**Theo dõi tốt không chỉ trả lời “đã chạy bao lâu”, mà còn phải trả lời “đang ở phase nào, đang chờ điều gì, counters có tiến triển không và tác động tới production ra sao”.** Dùng những thông tin đó để phát hiện sớm blockers, I/O bottlenecks, WAL/archive lag và backup failures.

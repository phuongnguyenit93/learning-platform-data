# pg_stat_database, thống kê bảng và chỉ mục trong PostgreSQL

PostgreSQL cung cấp các **cumulative statistics views** để quan sát hoạt động của database, bảng và chỉ mục. Những view này giúp trả lời các câu hỏi vận hành như:

- Database đang xử lý bao nhiêu transaction?
- Tỷ lệ buffer hit và lượng block phải đọc đang thay đổi thế nào?
- Bảng nào có nhiều sequential scans hoặc index scans?
- Bảng nào phát sinh nhiều INSERT, UPDATE, DELETE?
- Autovacuum và autoanalyze có theo kịp workload không?
- Chỉ mục nào đang được sử dụng, chỉ mục nào ít được truy cập?
- I/O của heap, index và TOAST đang tập trung ở đâu?
- Có nhiều temporary files, deadlocks hoặc recovery conflicts không?

Bài **“pg_stat_database, thống kê bảng và chỉ mục”**, thuộc chương **Giám sát** của module **Database Engine Relational PostgreSQL**, tập trung vào các view cốt lõi:

- `pg_stat_database`: thống kê tổng hợp theo database.
- `pg_stat_user_tables` và `pg_stat_all_tables`: truy cập, thay đổi và maintenance theo bảng.
- `pg_statio_user_tables` và `pg_statio_all_tables`: block I/O của heap, index và TOAST.
- `pg_stat_user_indexes` và `pg_stat_all_indexes`: mức độ sử dụng từng index.
- `pg_statio_user_indexes` và `pg_statio_all_indexes`: block I/O theo index.

Bài cũng giải thích cách đọc counter, tính delta/rate, diễn giải cache hit ratio, theo dõi vacuum/analyze, nhận diện index ít dùng và xây dựng dashboard mà không nhầm thống kê tích lũy với trạng thái tức thời.

> **Nguyên tắc:** các statistics views chủ yếu là bộ đếm tích lũy từ một thời điểm reset. Một con số lớn chưa chắc là vấn đề; hãy so sánh delta theo thời gian, đối chiếu với workload, thời gian quan sát và các giới hạn của từng metric.

---

## 1. Cumulative statistics là gì?

PostgreSQL ghi nhận nhiều hoạt động trong các statistics counters. Các view trong schema `pg_catalog` trình bày những counter này để DBA và monitoring tools truy vấn.

Ví dụ:

- Số transaction commit.
- Số block được đọc hoặc tìm thấy trong shared buffers.
- Số lần sequential scan/index scan.
- Số rows được insert, update hoặc delete.
- Số block heap/index được hit hoặc read.
- Số lần vacuum và analyze.

Đa số counter có tính tích lũy: giá trị tăng dần cho tới khi statistics được reset hoặc được khởi tạo lại theo lifecycle của server/database.

### 1.1. Counter khác gauge

| Loại metric | Ví dụ | Cách đọc |
|---|---|---|
| Counter | `xact_commit`, `seq_scan`, `idx_scan` | Tăng theo thời gian; nên tính delta/rate |
| Gauge/current value | `numbackends` | Giá trị tại thời điểm quan sát |
| Estimate | `n_live_tup`, `n_dead_tup` | Ước lượng, không phải số đếm chính xác |
| Timestamp | `last_autovacuum`, `stats_reset` | Mốc thời gian của một sự kiện |

Không áp dụng cùng một phép tính cho tất cả loại metric. Ví dụ, lấy delta của `numbackends` không cho biết số kết nối mới, vì đây là số backend hiện tại.

## 2. Tổng quan các statistics views

| View | Phạm vi | Câu hỏi chính |
|---|---|---|
| `pg_stat_database` | Một dòng theo database | Workload và I/O tổng thể |
| `pg_stat_database_conflicts` | Một dòng theo database trên standby | Recovery conflicts |
| `pg_stat_all_tables` | Bảng user và system | Scan, tuple changes, vacuum/analyze |
| `pg_stat_user_tables` | Bảng user | Scan, tuple changes, vacuum/analyze |
| `pg_statio_all_tables` | Bảng user và system | Heap/index/TOAST block I/O |
| `pg_statio_user_tables` | Bảng user | Block I/O của bảng user |
| `pg_stat_all_indexes` | Mỗi index | Index scan và tuple counters |
| `pg_stat_user_indexes` | Index trên bảng user | Index usage |
| `pg_statio_all_indexes` | Mỗi index | Block read/hit |
| `pg_statio_user_indexes` | Index trên bảng user | Index I/O |

Các view có hậu tố `user` thường loại trừ system catalogs. Hậu tố `all` bao gồm cả object hệ thống. Khi điều tra ứng dụng, bắt đầu với user views thường dễ đọc hơn.

## 3. pg_stat_database

`pg_stat_database` cung cấp thống kê tổng hợp cho từng database trong cluster.

Truy vấn cơ bản:

~~~sql
SELECT *
FROM pg_stat_database
ORDER BY datname NULLS FIRST;
~~~

Một số cột thường dùng:

| Cột | Ý nghĩa |
|---|---|
| `datid` | OID của database |
| `datname` | Tên database |
| `numbackends` | Số backend hiện đang kết nối tới database |
| `xact_commit` | Số transaction commit |
| `xact_rollback` | Số transaction rollback |
| `blks_read` | Số block được đọc từ filesystem vào PostgreSQL buffers |
| `blks_hit` | Số block được tìm thấy trong shared buffers |
| `tup_returned` | Số tuples được trả về bởi các scans |
| `tup_fetched` | Số tuples được fetch bằng index scans |
| `tup_inserted` | Số tuples được insert |
| `tup_updated` | Số tuples được update |
| `tup_deleted` | Số tuples được delete |
| `temp_files` | Số temporary files được tạo |
| `temp_bytes` | Tổng bytes ghi vào temporary files |
| `deadlocks` | Số deadlocks được phát hiện |
| `conflicts` | Số recovery conflicts trên standby |
| `stats_reset` | Thời điểm reset thống kê |

Các PostgreSQL versions mới có thể bổ sung session counters, checksum statistics và các trường thời gian. Luôn xem schema của version đang vận hành.

### 3.1. Lọc một database

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

Trên một số phiên bản, view còn có row tổng hợp cho shared objects với `datname` NULL. Khi làm dashboard theo database, lọc rõ database cần quan sát.

## 4. numbackends: số backend hiện tại

`numbackends` là số server processes hiện đang kết nối tới database tại thời điểm thống kê.

Nó là gauge, không phải tổng số connection đã từng mở.

Ví dụ:

- `numbackends = 20`: hiện có 20 backend kết nối tới database.
- Giá trị tăng từ 20 lên 35: số backend hiện tại tăng 15.
- Giá trị giảm: connection đã đóng hoặc backend kết thúc.

Để biết chi tiết từng session, dùng `pg_stat_activity`:

~~~sql
SELECT
    datname,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    count(*) AS sessions
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY
    datname,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event
ORDER BY sessions DESC;
~~~

`pg_stat_database` phù hợp cho tổng quan; `pg_stat_activity` dùng để điều tra session cụ thể.

## 5. Transaction commit và rollback

Hai counter:

- `xact_commit`: số transaction commit.
- `xact_rollback`: số transaction rollback.

Tổng của hai counter giúp quan sát transaction throughput ở mức database.

~~~sql
SELECT
    datname,
    xact_commit,
    xact_rollback,
    xact_commit + xact_rollback AS completed_transactions,
    stats_reset
FROM pg_stat_database
WHERE datname = current_database();
~~~

Tuy nhiên, giá trị tích lũy không cho biết tốc độ hiện tại. Lấy hai mẫu cách nhau một khoảng thời gian để tính transaction rate.

### 5.1. Tính transaction rate

Giả sử hai mẫu cách nhau 60 giây:

- Mẫu đầu `xact_commit = 1,000,000`.
- Mẫu sau `xact_commit = 1,006,000`.

Số commit trong khoảng là 6.000, tương đương 100 commits/giây.

Công thức:

~~~text
commit_rate = (commit_new - commit_old) / elapsed_seconds
~~~

Tính rollback rate tương tự. Ghi nhận `stats_reset` cùng mẫu để phát hiện counter bị reset giữa hai lần lấy dữ liệu.

### 5.2. Rollback ratio

Có thể tính tỷ lệ rollback trong số transaction hoàn tất:

~~~sql
SELECT
    datname,
    xact_commit,
    xact_rollback,
    round(
        100.0 * xact_rollback
        / NULLIF(xact_commit + xact_rollback, 0),
        2
    ) AS rollback_percent
FROM pg_stat_database
WHERE datname = current_database();
~~~

Rollback cao có thể đến từ ứng dụng chủ động rollback, transaction lỗi, deadlock retry hoặc logic nghiệp vụ. Không kết luận database có lỗi chỉ từ tỷ lệ này.

## 6. blks_read và blks_hit

Hai counter I/O tổng hợp:

- `blks_read`: số block PostgreSQL phải đọc vào shared buffers.
- `blks_hit`: số lần block được tìm thấy trong shared buffers mà không cần đọc từ filesystem ở tầng PostgreSQL buffer manager.

Đây là chỉ báo hữu ích về buffer cache behavior.

### 6.1. Tính buffer hit ratio

~~~sql
SELECT
    datname,
    blks_read,
    blks_hit,
    round(
        100.0 * blks_hit
        / NULLIF(blks_hit + blks_read, 0),
        2
    ) AS shared_buffer_hit_percent
FROM pg_stat_database
WHERE datname = current_database();
~~~

Công thức:

~~~text
hit ratio = blks_hit / (blks_hit + blks_read)
~~~

Ví dụ:

- `blks_hit = 9,000,000`.
- `blks_read = 1,000,000`.
- Hit ratio = 90%.

### 6.2. Hit ratio không phải tỷ lệ đọc từ RAM tuyệt đối

`blks_read` nghĩa là PostgreSQL phải yêu cầu đọc block từ filesystem. Hệ điều hành có thể phục vụ request từ page cache, không nhất thiết phải đọc physical disk.

Do đó:

- Hit ratio thấp không đồng nghĩa mọi read đều chạm storage device.
- Hit ratio cao không bảo đảm query latency thấp.
- Workload tuần tự đọc bảng lớn có thể có hit ratio thấp nhưng vẫn hoạt động bình thường.
- Một workload nhỏ, lặp lại trên hot data có thể có hit ratio cao.

Luôn kết hợp hit ratio với latency, block read rate, I/O metrics và query workload.

## 7. tup_returned và tup_fetched

Hai counter này phản ánh hoạt động đọc rows ở mức database:

- `tup_returned`: số tuples được trả về bởi scans.
- `tup_fetched`: số tuples được fetch qua index scans.

Đây là counter tổng hợp, không phải số rows ứng dụng nhận qua network. Một query có thể scan nhiều rows nhưng chỉ trả một vài rows sau filter.

Ví dụ:

~~~sql
SELECT *
FROM orders
WHERE created_at >= now() - interval '1 day'
  AND status = 'paid';
~~~

Nếu điều kiện không chọn lọc, PostgreSQL có thể đọc nhiều tuples rồi lọc phần lớn. Đối chiếu database counters với table/index scan stats và query-level statistics để tìm nguyên nhân.

## 8. tup_inserted, tup_updated và tup_deleted

Các counter này ghi nhận số tuple modifications theo database:

| Counter | Ý nghĩa |
|---|---|
| `tup_inserted` | Rows được insert |
| `tup_updated` | Rows được update |
| `tup_deleted` | Rows được delete |

Chúng giúp phân loại workload:

- Database thiên về read.
- Database có nhiều INSERT.
- Database thường xuyên UPDATE.
- Database có nhiều DELETE/batch cleanup.

Tuy nhiên, đây là số liệu tích lũy. Dùng delta theo phút/giờ để phát hiện workload spikes.

### 8.1. So sánh write rate

~~~sql
SELECT
    datname,
    tup_inserted,
    tup_updated,
    tup_deleted,
    tup_inserted + tup_updated + tup_deleted AS tuple_modifications
FROM pg_stat_database
WHERE datname = current_database();
~~~

Một bảng có write rate cao có thể cần chú ý autovacuum, index maintenance, WAL volume và bloat. Xem thống kê theo bảng để tìm object chịu phần lớn thay đổi.

## 9. Temporary files và temp_bytes

`temp_files` và `temp_bytes` phản ánh temporary files được tạo và lượng dữ liệu ghi vào các file đó.

Các thao tác có thể spill ra disk:

- Sort lớn.
- Hash aggregation.
- Hash join.
- Materialization.
- Một số operations cần workspace lớn hơn memory được cấp.

Truy vấn:

~~~sql
SELECT
    datname,
    temp_files,
    pg_size_pretty(temp_bytes) AS temp_data_written
FROM pg_stat_database
WHERE datname = current_database();
~~~

Temporary files không nhất thiết là lỗi. Nhưng `temp_bytes` tăng nhanh có thể chỉ ra query cần sort/hash lớn hoặc `work_mem` không phù hợp.

### 9.1. Không tăng work_mem toàn cục một cách máy móc

`work_mem` được dùng theo operation và có thể được cấp cho nhiều operations trong một query, nhiều sessions cùng lúc. Tăng quá cao có thể làm memory consumption vượt dự tính.

Dùng query plan, concurrent session count và temp I/O để quyết định điều chỉnh.

## 10. Deadlocks và conflicts

`deadlocks` là số deadlocks được phát hiện trong database.

Deadlock thường xảy ra khi hai hoặc nhiều transactions giữ locks theo thứ tự khác nhau và chờ nhau.

Ví dụ:

- Transaction A khóa row 1 rồi chờ row 2.
- Transaction B khóa row 2 rồi chờ row 1.
- PostgreSQL phát hiện cycle và abort một transaction.

Điều tra bằng server logs, application logs và `pg_stat_activity`/`pg_locks`.

`conflicts` trong `pg_stat_database` phản ánh recovery conflicts trên standby, ví dụ query standby bị hủy do recovery cần áp dụng WAL. Nó không phải cùng loại với duplicate-key conflict trong logical replication.

## 11. Thống kê thời gian I/O

Nếu `track_io_timing` được bật, PostgreSQL có thể ghi nhận thời gian đọc/ghi block:

~~~sql
SHOW track_io_timing;
~~~

Các cột thường gặp trong `pg_stat_database`:

- `blk_read_time`: tổng thời gian đọc block.
- `blk_write_time`: tổng thời gian ghi block.

Truy vấn:

~~~sql
SELECT
    datname,
    blks_read,
    blk_read_time,
    blks_hit,
    blk_write_time
FROM pg_stat_database
WHERE datname = current_database();
~~~

Thời gian này hữu ích để quan sát I/O wait ở tầng PostgreSQL, nhưng là counter tích lũy. Tính delta thời gian I/O theo cùng khoảng lấy mẫu và so sánh với elapsed time.

Việc bật `track_io_timing` có thể tạo overhead phụ thuộc platform/workload. Đánh giá trên môi trường thực tế và kiểm tra version/OS.

## 12. pg_stat_database_conflicts

Trên standby, view `pg_stat_database_conflicts` phân loại recovery conflicts:

~~~sql
SELECT *
FROM pg_stat_database_conflicts
ORDER BY datname;
~~~

Các nhóm thường gặp:

- `confl_tablespace`: tablespace không còn tồn tại.
- `confl_lock`: recovery cần lock xung đột với query standby.
- `confl_snapshot`: snapshot của query không thể tiếp tục vì cleanup/recovery.
- `confl_bufferpin`: query giữ buffer pin gây cản trở recovery.
- `confl_deadlock`: deadlock liên quan recovery conflict.

Kết hợp view này với `pg_stat_database.conflicts` và logs để hiểu query nào bị cancel trên standby.

## 13. pg_stat_all_tables và pg_stat_user_tables

`pg_stat_all_tables` cung cấp thống kê cho mọi bảng, bao gồm system catalogs. `pg_stat_user_tables` chỉ tập trung vào user tables.

Truy vấn:

~~~sql
SELECT *
FROM pg_stat_user_tables
ORDER BY schemaname, relname;
~~~

Một số columns quan trọng:

| Cột | Ý nghĩa |
|---|---|
| `relid` | OID của relation |
| `schemaname` | Schema |
| `relname` | Tên bảng |
| `seq_scan` | Số sequential scans bắt đầu trên bảng |
| `seq_tup_read` | Số tuples đọc bởi sequential scans |
| `idx_scan` | Số index scans bắt đầu trên bảng |
| `idx_tup_fetch` | Số live tuples được fetch qua index scans |
| `n_tup_ins` | Số tuples được insert |
| `n_tup_upd` | Số tuples được update |
| `n_tup_del` | Số tuples được delete |
| `n_tup_hot_upd` | Số HOT updates |
| `n_live_tup` | Ước lượng live tuples |
| `n_dead_tup` | Ước lượng dead tuples |
| `last_vacuum` | Lần manual vacuum gần nhất |
| `last_autovacuum` | Lần autovacuum gần nhất |
| `last_analyze` | Lần manual analyze gần nhất |
| `last_autoanalyze` | Lần autoanalyze gần nhất |

Columns có thể khác theo major version; dùng lệnh mô tả view trong psql để kiểm tra schema.

## 14. Sequential scans

`seq_scan` đếm số sequential scans bắt đầu trên bảng.

Sequential scan không mặc định là xấu. PostgreSQL có thể chọn sequential scan khi:

- Bảng nhỏ.
- Query đọc tỷ lệ lớn rows.
- Điều kiện filter không chọn lọc.
- Statistics cho thấy sequential scan rẻ hơn index access.
- Query cần đọc gần như toàn bộ bảng.

Xem các bảng có nhiều sequential scans:

~~~sql
SELECT
    schemaname,
    relname,
    seq_scan,
    seq_tup_read,
    n_live_tup,
    round(
        seq_tup_read::numeric / NULLIF(seq_scan, 0),
        1
    ) AS avg_tuples_per_seq_scan
FROM pg_stat_user_tables
ORDER BY seq_tup_read DESC
LIMIT 20;
~~~

Nếu một bảng lớn có nhiều sequential scans và query latency cao, xem query plans và filter patterns. Không thêm index chỉ vì `seq_scan` lớn.

## 15. Index scans ở mức bảng

`idx_scan` trong `pg_stat_user_tables` đếm số index scans được bắt đầu trên bảng. Nó tổng hợp hoạt động qua các indexes của bảng.

~~~sql
SELECT
    schemaname,
    relname,
    seq_scan,
    idx_scan,
    seq_tup_read,
    idx_tup_fetch,
    n_live_tup
FROM pg_stat_user_tables
ORDER BY idx_scan DESC
LIMIT 20;
~~~

Tỷ lệ seq/index scan có thể giúp hiểu access pattern, nhưng không trực tiếp cho biết query nào chậm hoặc index nào hiệu quả.

Một query dùng bitmap index scan có thể làm `idx_scan` tăng ở index view, trong khi cách đếm tuples fetched khác simple index scan. Xem semantics từng counter trước khi so sánh.

## 16. HOT updates

`n_tup_hot_upd` đếm số HOT updates (Heap-Only Tuple updates).

HOT update có thể tránh cập nhật index khi các điều kiện phù hợp, chẳng hạn:

- Các cột được update không được index tham chiếu.
- Trang heap có đủ free space cho tuple version mới.

HOT giúp giảm index maintenance và WAL overhead trong một số workload.

Có thể xem tỷ lệ HOT update:

~~~sql
SELECT
    schemaname,
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    round(
        100.0 * n_tup_hot_upd
        / NULLIF(n_tup_upd, 0),
        2
    ) AS hot_update_percent
FROM pg_stat_user_tables
WHERE n_tup_upd > 0
ORDER BY n_tup_upd DESC;
~~~

Tỷ lệ thấp không tự chứng minh cấu hình sai. Xem các columns được index, fillfactor, page free space và update pattern.

## 17. n_live_tup và n_dead_tup

Hai trường này là estimates:

- `n_live_tup`: ước lượng số live tuples.
- `n_dead_tup`: ước lượng số dead tuples.

Chúng không phải kết quả `COUNT(*)` chính xác tại đúng thời điểm query.

Dead tuples phát sinh khi UPDATE/DELETE tạo phiên bản row cũ không còn cần cho MVCC snapshots. VACUUM có thể thu hồi không gian tuple đó để tái sử dụng bên trong relation.

### 17.1. Dead tuples không đồng nghĩa bloat chính xác

Một bảng có `n_dead_tup` cao có thể đang chờ autovacuum. Không thể suy ra chính xác bloat chỉ từ counter này.

Để đánh giá:

- Xem dead tuple estimate theo thời gian.
- Xem last_autovacuum và vacuum_count.
- Xem long-running transactions/replication slots giữ xmin.
- Xem table/index size.
- Dùng công cụ phân tích bloat phù hợp nếu cần.

Không chạy VACUUM FULL chỉ vì `n_dead_tup` lớn; VACUUM FULL cần rewrite relation và lock mạnh.

## 18. Theo dõi vacuum và autovacuum

Truy vấn:

~~~sql
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
~~~

Các câu hỏi cần đặt ra:

- Bảng nào có dead tuples tăng liên tục?
- Autovacuum có chạy gần đây?
- Một bảng lớn có bị bỏ qua quá lâu?
- Có transaction lâu hoặc replication slot giữ xmin?
- Autovacuum workers có đủ capacity?
- Vacuum có bị cancel hoặc không hoàn tất?

Autovacuum là cơ chế nền tảng để kiểm soát dead tuples và transaction ID wraparound. Không tắt nó chỉ để giảm background I/O.

## 19. Analyze và autoanalyze

`ANALYZE` thu thập statistics về phân phối dữ liệu để query planner ước lượng row counts và chọn execution plan.

`pg_stat_user_tables` có:

- `last_analyze`.
- `last_autoanalyze`.
- `analyze_count`.
- `autoanalyze_count`.

Xem bảng chưa được analyze gần đây:

~~~sql
SELECT
    schemaname,
    relname,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze,
    autoanalyze_count
FROM pg_stat_user_tables
ORDER BY n_mod_since_analyze DESC NULLS LAST
LIMIT 30;
~~~

`n_mod_since_analyze` có trên các versions hỗ trợ. Nếu server cũ hơn không có column này, bỏ khỏi query và dựa vào counters/time fields sẵn có.

Sau bulk load hoặc thay đổi lớn, có thể cần ANALYZE chủ động:

~~~sql
ANALYZE public.orders;
~~~

## 20. n_mod_since_analyze

`n_mod_since_analyze` là ước lượng số row modifications kể từ lần analyze gần nhất trên các versions hỗ trợ.

Giá trị tăng cao có thể cho biết planner statistics không còn phản ánh workload mới. Tuy nhiên, ngưỡng autoanalyze phụ thuộc bảng, số rows, scale factor và cấu hình autovacuum.

Đối chiếu table size, modification count, last analyze, query plans và planner estimate so với actual rows trong EXPLAIN ANALYZE.

## 21. pg_statio_all_tables và pg_statio_user_tables

Các view này thống kê block I/O theo bảng.

`pg_statio_user_tables` thường có:

| Cột | Ý nghĩa |
|---|---|
| `heap_blks_read` | Heap blocks được đọc vào PostgreSQL buffers |
| `heap_blks_hit` | Heap blocks tìm thấy trong shared buffers |
| `idx_blks_read` | Index blocks được đọc |
| `idx_blks_hit` | Index blocks tìm thấy trong shared buffers |
| `toast_blks_read` | TOAST blocks được đọc |
| `toast_blks_hit` | TOAST blocks hit |
| `tidx_blks_read` | TOAST index blocks được đọc |
| `tidx_blks_hit` | TOAST index blocks hit |

Truy vấn:

~~~sql
SELECT
    schemaname,
    relname,
    heap_blks_read,
    heap_blks_hit,
    idx_blks_read,
    idx_blks_hit,
    toast_blks_read,
    toast_blks_hit,
    tidx_blks_read,
    tidx_blks_hit
FROM pg_statio_user_tables
ORDER BY heap_blks_read + idx_blks_read DESC
LIMIT 30;
~~~

Dùng view này để tìm bảng có nhiều block reads/hits, sau đó xem query plans và index usage.

## 22. Heap, index và TOAST

PostgreSQL lưu table rows trong heap relation; indexes là các relations riêng. TOAST lưu các giá trị lớn được nén hoặc tách khỏi tuple chính.

- `heap_blks_*`: hoạt động đọc block của heap.
- `idx_blks_*`: hoạt động đọc block index.
- `toast_blks_*`: hoạt động đọc TOAST data.
- `tidx_blks_*`: hoạt động đọc TOAST index.

Một ứng dụng lưu JSON/text lớn có thể có TOAST I/O đáng kể. Nếu query thường lấy toàn bộ large values, kiểm tra projection và cách ứng dụng truy cập dữ liệu.

## 23. Tính hit ratio theo bảng

Có thể tính tỷ lệ hit của heap:

~~~sql
SELECT
    schemaname,
    relname,
    heap_blks_read,
    heap_blks_hit,
    round(
        100.0 * heap_blks_hit
        / NULLIF(heap_blks_hit + heap_blks_read, 0),
        2
    ) AS heap_hit_percent
FROM pg_statio_user_tables
ORDER BY heap_blks_read + heap_blks_hit DESC;
~~~

Tính riêng index:

~~~sql
SELECT
    schemaname,
    relname,
    idx_blks_read,
    idx_blks_hit,
    round(
        100.0 * idx_blks_hit
        / NULLIF(idx_blks_hit + idx_blks_read, 0),
        2
    ) AS index_hit_percent
FROM pg_statio_user_tables
ORDER BY idx_blks_read + idx_blks_hit DESC;
~~~

Hit ratio per table giúp phân tích object-level cache behavior, nhưng cũng bị ảnh hưởng bởi workload mix và cache warm-up.

## 24. pg_stat_all_indexes và pg_stat_user_indexes

`pg_stat_user_indexes` có một dòng cho mỗi index trên user tables.

Các cột chính:

| Cột | Ý nghĩa |
|---|---|
| `schemaname` | Schema của bảng |
| `relname` | Tên bảng |
| `indexrelname` | Tên index |
| `idx_scan` | Số index scans bắt đầu trên index |
| `idx_tup_read` | Số index entries được đọc bởi scans |
| `idx_tup_fetch` | Số live table rows được fetch bởi simple index scans |

Truy vấn:

~~~sql
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY idx_scan DESC
LIMIT 50;
~~~

View này giúp hiểu index nào đang được planner sử dụng trong khoảng thống kê hiện tại.

## 25. idx_scan, idx_tup_read và idx_tup_fetch

Không nên xem ba counter này là cùng một thứ:

- `idx_scan`: số index scans được bắt đầu.
- `idx_tup_read`: số index entries được đọc.
- `idx_tup_fetch`: số live table rows được fetch bởi simple index scans.

Bitmap index scans có thể làm `idx_tup_read` tăng nhưng không làm `idx_tup_fetch` tăng tương ứng, vì table rows được truy cập theo bitmap heap scan.

Một scan có thể đọc nhiều index entries rồi filter nhiều rows. Vì vậy tỷ lệ `idx_tup_fetch / idx_tup_read` không phải một thước đo chất lượng index độc lập.

## 26. Index có vẻ không được sử dụng

Tìm index có `idx_scan = 0`:

~~~sql
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_scan,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
WHERE idx_scan = 0
ORDER BY pg_relation_size(indexrelid) DESC;
~~~

Đây chỉ là danh sách để điều tra. Không drop index tự động vì:

- Statistics có thể vừa reset.
- Index có thể chỉ dùng theo chu kỳ tháng/quý.
- Unique index/primary key bảo vệ constraint.
- Index có thể phục vụ foreign key checks hoặc query hiếm.
- Planner có thể dùng index trong workload chưa xảy ra trong cửa sổ quan sát.
- Index có thể cần cho một maintenance/reporting job.

Kiểm tra catalog constraints và workload trước khi quyết định.

## 27. Phân biệt index scan với index size

Một index lớn nhưng ít scans có thể là ứng viên cần xem xét, nhưng dung lượng không chứng minh index dư thừa.

Xem kích thước:

~~~sql
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_scan,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
ORDER BY pg_relation_size(indexrelid) DESC
LIMIT 30;
~~~

Đối chiếu index definition:

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schemaname, tablename, indexname;
~~~

Index có thể chứa INCLUDE columns, partial predicate, expression hoặc uniqueness; không so sánh chỉ bằng tên và số lần scan.

## 28. pg_statio_all_indexes và pg_statio_user_indexes

`pg_statio_user_indexes` cung cấp block read/hit cho từng index.

~~~sql
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_blks_read,
    idx_blks_hit,
    round(
        100.0 * idx_blks_hit
        / NULLIF(idx_blks_hit + idx_blks_read, 0),
        2
    ) AS index_hit_percent
FROM pg_statio_user_indexes
ORDER BY idx_blks_read DESC
LIMIT 30;
~~~

Đây là I/O counters của index relation. Kết hợp với `pg_stat_user_indexes` để biết một index vừa được dùng bao nhiêu lần vừa có hoạt động block read/hit ra sao.

## 29. Ghép thống kê bảng và index

Có thể ghép hai view để xem table access và index usage cùng nhau:

~~~sql
SELECT
    t.schemaname,
    t.relname,
    t.seq_scan,
    t.idx_scan,
    t.n_live_tup,
    t.n_dead_tup,
    i.indexrelname,
    i.idx_scan AS index_scan_count,
    pg_size_pretty(pg_relation_size(i.indexrelid)) AS index_size
FROM pg_stat_user_tables AS t
LEFT JOIN pg_stat_user_indexes AS i
  ON i.relid = t.relid
ORDER BY t.seq_scan DESC, t.relname, i.indexrelname;
~~~

Một dòng có thể xuất hiện cho mỗi index của bảng. Bảng không có index vẫn có dòng nhờ LEFT JOIN.

Đừng cộng `t.seq_scan` qua kết quả join rồi coi đó là tổng bảng; giá trị table counters bị lặp lại trên từng index row.

## 30. Xem bảng có nhiều modifications

~~~sql
SELECT
    schemaname,
    relname,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_tup_hot_upd,
    n_live_tup,
    n_dead_tup
FROM pg_stat_user_tables
ORDER BY n_tup_ins + n_tup_upd + n_tup_del DESC
LIMIT 30;
~~~

Những bảng write-heavy thường cần theo dõi autovacuum frequency, dead tuple estimates, index maintenance, WAL generation, replication lag và table/index size.

Không phải mọi update đều tạo cùng mức bloat; HOT update, fillfactor và MVCC snapshot horizon ảnh hưởng đáng kể.

## 31. Kết hợp table stats với I/O stats

~~~sql
SELECT
    t.schemaname,
    t.relname,
    t.seq_scan,
    t.idx_scan,
    t.n_live_tup,
    t.n_dead_tup,
    io.heap_blks_read,
    io.heap_blks_hit,
    io.idx_blks_read,
    io.idx_blks_hit
FROM pg_stat_user_tables AS t
JOIN pg_statio_user_tables AS io
  ON io.relid = t.relid
ORDER BY io.heap_blks_read + io.idx_blks_read DESC
LIMIT 30;
~~~

Query này giúp tìm các bảng có nhiều scans và I/O. Sau đó chọn query cụ thể từ application telemetry hoặc `pg_stat_statements` để xem plan.

## 32. Phân biệt database-level và table-level counters

Một thao tác có thể làm nhiều counter tăng:

- Query đọc table: `pg_stat_database` có thể tăng `tup_returned`; table stats tăng `seq_scan`/`seq_tup_read` hoặc index stats.
- Query dùng index: database counters và index counters cùng thay đổi.
- INSERT: database tuple counters và table `n_tup_ins` tăng.
- Temporary sort: database `temp_files`/`temp_bytes` tăng.

Không cộng database-level với table-level counters để tính một tổng duy nhất; chúng là các góc nhìn khác nhau của cùng hoạt động.

## 33. Cumulative counters và delta

Để giám sát, nên lưu mẫu định kỳ:

| Timestamp | xact_commit |
|---|---:|
| 10:00 | 100,000 |
| 10:01 | 106,500 |
| 10:02 | 112,000 |

Tốc độ commit:

- 10:00–10:01: 6.500/min.
- 10:01–10:02: 5.500/min.

Counter tuyệt đối cho biết tổng từ thời điểm reset; delta cho biết hoạt động trong cửa sổ quan sát.

### 33.1. Phát hiện counter reset

Lưu thêm `stats_reset`. Nếu timestamp reset thay đổi, không tính delta xuyên qua ranh giới reset.

Nếu counter mới nhỏ hơn counter cũ, có thể đã reset hoặc có thay đổi lifecycle. Bắt đầu một baseline mới thay vì tạo rate âm.

## 34. Ví dụ lưu samples

Nếu monitoring system lưu snapshot vào bảng riêng, có thể dùng schema đơn giản:

~~~sql
CREATE TABLE monitoring.database_stat_samples (
    sampled_at timestamptz NOT NULL,
    datname name NOT NULL,
    stats_reset timestamptz,
    xact_commit bigint,
    blks_read bigint,
    blks_hit bigint,
    PRIMARY KEY (sampled_at, datname)
);
~~~

Một truy vấn tính rate cần ghép mẫu trước/sau, kiểm tra `stats_reset` không đổi và thời gian elapsed dương.

Trong production, monitoring agent thường thu thập và lưu metric bên ngoài PostgreSQL. Không cần tạo bảng trong database ứng dụng chỉ để đọc stats nếu hệ thống metrics đã có storage phù hợp.

## 35. Statistics snapshot và transaction

Các statistics views có semantics snapshot/caching tùy PostgreSQL version và cấu hình `stats_fetch_consistency`.

Nếu chạy nhiều câu SELECT trong một transaction dài, kết quả có thể phản ánh cùng một statistics snapshot thay vì luôn cập nhật ngay theo từng query.

Có thể làm mới snapshot trong session bằng:

~~~sql
SELECT pg_stat_clear_snapshot();
~~~

Khi cần so sánh hai thời điểm:

- Dùng transaction ngắn.
- Lấy mẫu độc lập.
- Ghi timestamp.
- Xem `stats_reset`.
- Tránh giữ transaction read-only dài chỉ để polling counters.

Kiểm tra tài liệu version đang dùng vì chi tiết statistics collection/fetch behavior thay đổi giữa các major releases.

## 36. Statistics không phải dữ liệu giao dịch

Các statistics views dùng để quan sát, không phải audit log hay nguồn dữ liệu nghiệp vụ.

Không dùng chúng để:

- Chứng minh một user cụ thể đã sửa row nào.
- Khôi phục chính xác thứ tự transaction.
- Xác định query text của mọi lần scan.
- Thay thế WAL/audit logs.
- Tính row counts chính xác tại một snapshot.
- Làm cơ sở duy nhất cho billing hoặc compliance evidence.

Cần audit logging, application events, WAL decoding hoặc query-level telemetry cho các mục tiêu đó.

## 37. Reset statistics

PostgreSQL có các functions để reset statistics, chẳng hạn:

~~~sql
SELECT pg_stat_reset();
~~~

Có các functions reset theo database/table hoặc nhóm statistics khác tùy version và quyền.

Reset làm mất baseline của counters. Nếu dashboard chỉ hiển thị counter tuyệt đối, sau reset có thể thấy giá trị đột ngột về thấp.

Không reset statistics thường xuyên chỉ để “làm sạch dashboard”. Monitoring nên tính delta và lưu reset timestamp.

### 37.1. Reset không xóa dữ liệu

Statistics reset không xóa rows, tables hoặc indexes. Nó chỉ reset các counters liên quan theo function được gọi.

Tuy nhiên, reset trên production có thể làm mất dữ liệu quan sát lịch sử mà monitoring chưa kịp thu thập. Chỉ thực hiện có chủ đích và hiểu scope.

## 38. Quyền truy cập statistics

Các statistics views có thể hiển thị dữ liệu ở mức khác nhau tùy quyền.

Predefined role `pg_monitor` thường phù hợp cho tài khoản giám sát chỉ đọc. Role `pg_read_all_stats` cấp khả năng xem đầy đủ hơn các thống kê bị giới hạn cho user thông thường.

Ví dụ cấp quyền:

~~~sql
GRANT pg_monitor TO monitoring_user;
~~~

Đây là quyền giám sát, không đồng nghĩa superuser. Kiểm tra policy bảo mật và quyền cần thiết theo PostgreSQL version.

Không dùng superuser cho monitoring agent nếu chỉ cần đọc statistics.

## 39. Version compatibility

Statistics views được bổ sung và thay đổi qua các major versions.

Một số ví dụ:

- Các session counters mới có thể không có trên server cũ.
- `wal_status` hoặc `safe_wal_size` thuộc những version hỗ trợ slot fields tương ứng.
- `pg_stat_io` có trên PostgreSQL versions mới hơn.
- Một số timestamp hoặc worker columns được bổ sung theo version.
- Các trường `n_mod_since_analyze` và statistics chi tiết khác cần kiểm tra catalog view thực tế.

Trước khi triển khai query:

~~~sql
SELECT version();
~~~

Trong psql, có thể mô tả view bằng lệnh phù hợp để kiểm tra columns:

~~~text
\d+ pg_stat_database
\d+ pg_stat_user_tables
\d+ pg_statio_user_tables
\d+ pg_stat_user_indexes
~~~

Không copy một dashboard query từ major version mới sang server cũ mà chưa kiểm tra columns.

## 40. pg_stat_io là view bổ sung

Trên PostgreSQL versions có hỗ trợ `pg_stat_io`, view này cung cấp thống kê I/O theo backend type, object và context.

~~~sql
SELECT *
FROM pg_stat_io
ORDER BY backend_type, object, context;
~~~

`pg_stat_io` bổ sung góc nhìn I/O rộng hơn; nó không thay thế `pg_statio_user_tables` hoặc `pg_statio_user_indexes` khi cần biết relation cụ thể.

Sử dụng trên version có view này và kiểm tra schema vì columns có thể thay đổi theo major version.

## 41. pg_stat_statements bổ sung query-level statistics

`pg_stat_statements` là extension thường dùng để thống kê query patterns:

- Số lần gọi query.
- Tổng/min/max/mean execution time.
- Rows.
- Shared/local/temp block hits/reads/writes.
- WAL bytes trên các versions hỗ trợ.

Nó giúp tìm query nào gây workload, trong khi `pg_stat_database` và table/index stats cho biết database/object đang hoạt động thế nào.

Cần cài extension và cấu hình preload theo hướng dẫn của version. Không coi `pg_stat_statements` là một statistics view mặc định luôn có sẵn.

## 42. Dashboard database-level nên có gì?

Một dashboard tổng quan có thể gồm:

| Nhóm | Metric |
|---|---|
| Workload | Commit/s, rollback/s, active connections |
| Reads | Block reads/s, buffer hits/s |
| Writes | Tuple insert/update/delete per second |
| Temporary I/O | Temp files/s, temp bytes/s |
| Concurrency | Deadlocks, conflicts |
| Latency | Block read/write time deltas |
| Health | Stats reset time, checksum failures nếu hỗ trợ |

Hiển thị rate và trend theo thời gian. Tránh dashboard chỉ có các counter tuyệt đối tích lũy từ ngày database được tạo.

## 43. Dashboard table-level nên có gì?

Theo từng bảng:

- `seq_scan` delta.
- `idx_scan` delta.
- `seq_tup_read` rate.
- `idx_tup_fetch` rate.
- Insert/update/delete rates.
- HOT update percentage.
- Live/dead tuple estimates.
- Last vacuum/autovacuum.
- Last analyze/autoanalyze.
- Heap/index/TOAST block read/hit.
- Relation size.

Dùng top-N tables theo I/O, modification rate và dead tuple estimates để phát hiện nơi cần điều tra.

## 44. Dashboard index-level nên có gì?

Theo từng index:

- `idx_scan` rate.
- `idx_tup_read` và `idx_tup_fetch`.
- `idx_blks_read`/`idx_blks_hit`.
- Index size.
- Table name.
- Index definition.
- Unique/primary/constraint dependency.

Index usage counters phải được quan sát trong một cửa sổ đủ dài, bao phủ cả batch jobs và workload theo lịch.

## 45. Tìm bảng có nhiều sequential I/O

~~~sql
SELECT
    t.schemaname,
    t.relname,
    t.seq_scan,
    t.seq_tup_read,
    io.heap_blks_read,
    io.heap_blks_hit,
    pg_size_pretty(
        pg_total_relation_size(t.relid)
    ) AS total_size
FROM pg_stat_user_tables AS t
JOIN pg_statio_user_tables AS io
  ON io.relid = t.relid
ORDER BY io.heap_blks_read DESC
LIMIT 20;
~~~

Một bảng có heap reads cao có thể là bảng lớn được scan hợp lệ. Xem query plan, filter selectivity, partition pruning và workload frequency trước khi thêm index.

## 46. Tìm bảng có dead tuples và maintenance cũ

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_autovacuum,
    last_autoanalyze,
    autovacuum_count,
    autoanalyze_count,
    pg_size_pretty(
        pg_total_relation_size(relid)
    ) AS total_size
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
~~~

Bảng lớn, dead tuple estimate tăng và autovacuum lâu không chạy cần được xem xét. Điều tra long transactions, replication slots, autovacuum settings và worker availability trước khi thay đổi cấu hình.

## 47. Kích thước relation và statistics

Statistics views không cung cấp đầy đủ size của table/index. Dùng các size functions:

~~~sql
SELECT
    schemaname,
    relname,
    pg_size_pretty(pg_relation_size(relid)) AS heap_size,
    pg_size_pretty(pg_indexes_size(relid)) AS indexes_size,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 30;
~~~

- `pg_relation_size`: size của relation được chỉ định (thường heap khi truyền table OID).
- `pg_indexes_size`: tổng size các indexes của table.
- `pg_total_relation_size`: table và các thành phần liên quan như indexes/TOAST.

Kích thước lớn không tự chứng minh bloat. So sánh với row volume, data types, fillfactor, index definitions và lịch sử growth.

## 48. Đọc index usage có trách nhiệm

Trước khi kết luận một index không cần thiết:

1. Kiểm tra `stats_reset`.
2. Xác định thời gian quan sát.
3. Bao phủ workload theo ngày/tháng/quý.
4. Kiểm tra primary key và unique constraints.
5. Kiểm tra foreign key usage/maintenance needs.
6. Kiểm tra query plans và index definitions.
7. Xem index có overlap với index khác không.
8. Đánh giá write overhead và disk cost.
9. Thử nghiệm trên staging.
10. Chỉ drop qua migration có rollback plan.

Một index có `idx_scan = 0` trong một giờ không phải lý do đủ để xóa.

## 49. Diễn giải cache hit ratio có trách nhiệm

Không đặt một ngưỡng hit ratio duy nhất cho mọi database.

Ví dụ:

- OLTP hot set nhỏ có thể kỳ vọng hit ratio cao.
- Data warehouse scan lớn có thể có tỷ lệ thấp hơn.
- Sau restart hoặc cache warm-up, ratio có thể giảm.
- Một workload đọc tuần tự có thể chủ động bypass hoặc không tận dụng cache giống workload random.
- OS page cache không được phản ánh đầy đủ như shared-buffer hits.

Theo dõi trend cùng block read latency, physical storage metrics, query latency và workload type.

## 50. Thống kê thay đổi theo workload

Counter tích lũy có thể che khuất thay đổi gần đây.

Ví dụ một bảng có 1 tỷ sequential scans từ nhiều tháng trước nhưng hôm nay không có scan nào. Giá trị `seq_scan` lớn không có nghĩa workload hiện tại vẫn scan nhiều.

Hãy lưu mẫu định kỳ và dùng delta:

~~~text
scan_rate = (seq_scan_new - seq_scan_old) / elapsed_seconds
~~~

Làm tương tự cho `idx_scan`, tuple modifications và block I/O counters.

## 51. Troubleshooting: hit ratio thấp

Kiểm tra:

- Database có vừa restart/warm-up?
- Workload có scan bảng lớn?
- Shared buffers có phù hợp?
- OS cache và storage latency thế nào?
- Có query đọc working set lớn hơn memory?
- Query plan có scan nhiều block không?
- Có thể giảm columns/rows đọc bằng predicate/projection?
- Index có giúp giảm reads hay chỉ tăng write overhead?

Không tăng `shared_buffers` hoặc tạo index chỉ từ một lần nhìn hit ratio.

## 52. Troubleshooting: temp_bytes tăng nhanh

Kiểm tra:

- Query sort/hash nào đang chạy.
- EXPLAIN ANALYZE và temporary block counters.
- `work_mem` hiện tại.
- Số concurrent sessions.
- Query có sort/hash lặp lại nhiều lần không.
- Có thể giảm rows trước sort/join không.
- Có index/order phù hợp không.

Dùng `pg_stat_statements` và logs phù hợp để tìm query gây spill.

## 53. Troubleshooting: n_dead_tup cao

Kiểm tra:

- Last autovacuum.
- Autovacuum thresholds/scale factors.
- Long-running transactions.
- Idle-in-transaction sessions.
- Replication slots và xmin horizons.
- Table write rate.
- Vacuum logs và worker capacity.
- Relation size trend.

Nếu snapshot lâu giữ old row versions, vacuum không thể thu hồi chúng dù autovacuum chạy thường xuyên.

## 54. Troubleshooting: idx_scan bằng 0

Kiểm tra:

- Statistics vừa reset?
- Observation window đủ dài?
- Workload có seasonal?
- Index có phải unique/primary key?
- Constraint nào phụ thuộc index?
- Query planner có dùng index trong plan khác?
- Index có chỉ phục vụ một report hiếm?

Không tự động DROP index dựa trên một counter.

## 55. Troubleshooting: deadlocks tăng

Dùng server logs để xác định:

- SQL statements liên quan.
- Transaction IDs/sessions.
- Lock types và objects.
- Lock acquisition order.
- Application retry behavior.

Biện pháp thường gồm chuẩn hóa thứ tự cập nhật rows, rút ngắn transaction và tránh giữ locks khi gọi external services.

`pg_stat_database.deadlocks` là counter tổng hợp, không lưu chi tiết từng deadlock.

## 56. Monitoring interval và retention

Chọn interval theo mục đích:

- 5–15 giây: quan sát ngắn hạn khi điều tra sự cố.
- 30–60 giây: dashboard workload thông thường.
- 5 phút: trend dài hơn và giảm sampling volume.

Đây là gợi ý vận hành, không phải quy tắc PostgreSQL. Cần cân bằng độ phân giải với chi phí thu thập/lưu trữ.

Lưu raw snapshots hoặc time-series deltas đủ lâu để so sánh peak hours, batch windows và seasonal workload.

## 57. Checklist xây dựng dashboard

**Database-level**

1. Có transaction commit/rollback rates?
2. Có current backend count?
3. Có block read/hit rates?
4. Có temp bytes/files rates?
5. Có deadlock/conflict rates?
6. Có I/O timing khi cần?
7. Có stats_reset và reset detection?

**Table-level**

8. Có seq/index scan deltas?
9. Có tuple modification rates?
10. Có live/dead tuple estimates?
11. Có vacuum/analyze timestamps?
12. Có heap/index/TOAST block I/O?
13. Có table sizes?

**Index-level**

14. Có idx_scan delta?
15. Có idx_tup_read/fetch?
16. Có index block read/hit?
17. Có index size và definition?
18. Có bảo vệ constraint indexes khỏi quyết định drop sai?

**Vận hành**

19. Monitoring role có quyền tối thiểu?
20. Query tương thích major version?
21. Có cảnh báo khi counters reset?
22. Có lưu trend theo thời gian?
23. Có runbook xử lý metric bất thường?

## 58. Bài tập thực hành

### Bài 1 — pg_stat_database

View này cung cấp thống kê ở cấp nào?

**Gợi ý:** theo database.

### Bài 2 — numbackends

Đây là counter hay gauge?

**Gợi ý:** gauge, số backend hiện tại.

### Bài 3 — xact_commit

Counter này đo gì?

**Gợi ý:** transaction commit.

### Bài 4 — xact_rollback

Counter tăng có luôn có nghĩa database lỗi không?

**Gợi ý:** không; ứng dụng có thể chủ động rollback.

### Bài 5 — blks_read

Counter này có nghĩa physical disk read tuyệt đối không?

**Gợi ý:** không; OS cache có thể phục vụ request.

### Bài 6 — blks_hit

Nó đo điều gì?

**Gợi ý:** block được tìm thấy trong shared buffers.

### Bài 7 — Hit ratio

Viết công thức shared buffer hit ratio.

**Gợi ý:** blks_hit / (blks_hit + blks_read).

### Bài 8 — tup_returned

Counter này đo gì?

**Gợi ý:** tuples được trả về bởi scans.

### Bài 9 — tup_fetched

Nó liên quan hoạt động nào?

**Gợi ý:** tuples fetched qua index scans.

### Bài 10 — temp_bytes

Counter tăng nhanh gợi ý điều gì?

**Gợi ý:** queries spill temporary data ra files.

### Bài 11 — deadlocks

View nào có counter deadlocks theo database?

**Gợi ý:** pg_stat_database.

### Bài 12 — conflicts

conflicts trong pg_stat_database chủ yếu nói về gì?

**Gợi ý:** recovery conflicts trên standby.

### Bài 13 — pg_stat_user_tables

View này loại trừ nhóm object nào?

**Gợi ý:** system catalogs.

### Bài 14 — seq_scan

Counter này đo gì?

**Gợi ý:** số sequential scans bắt đầu trên bảng.

### Bài 15 — idx_scan

Ở table stats, idx_scan là gì?

**Gợi ý:** số index scans trên bảng.

### Bài 16 — n_tup_ins

Counter này đo gì?

**Gợi ý:** số tuples được insert.

### Bài 17 — n_tup_hot_upd

HOT update giúp giảm điều gì?

**Gợi ý:** index maintenance khi điều kiện cho phép.

### Bài 18 — n_live_tup

Đây là số đếm chính xác không?

**Gợi ý:** không, là estimate.

### Bài 19 — n_dead_tup

Dead tuples phát sinh chủ yếu từ cơ chế nào?

**Gợi ý:** MVCC và UPDATE/DELETE.

### Bài 20 — autovacuum

Cột nào cho biết lần autovacuum gần nhất?

**Gợi ý:** last_autovacuum.

### Bài 21 — autoanalyze

ANALYZE có mục đích gì?

**Gợi ý:** cập nhật planner statistics.

### Bài 22 — pg_statio_user_tables

View này quan sát block I/O nào?

**Gợi ý:** heap, index, TOAST và TOAST index.

### Bài 23 — heap_blks_hit

Counter này đo gì?

**Gợi ý:** heap blocks tìm thấy trong shared buffers.

### Bài 24 — pg_stat_user_indexes

Một row của view đại diện cho gì?

**Gợi ý:** một index trên user table.

### Bài 25 — idx_tup_read

Nó đo index entries hay table rows?

**Gợi ý:** index entries được đọc.

### Bài 26 — idx_tup_fetch

Nó khác idx_tup_read thế nào?

**Gợi ý:** live table rows fetch qua simple index scans.

### Bài 27 — Bitmap scan

Vì sao idx_tup_read có thể lớn hơn idx_tup_fetch?

**Gợi ý:** bitmap scans không tăng fetch counter theo cùng cách.

### Bài 28 — Index không dùng

idx_scan=0 có đủ để drop index không?

**Gợi ý:** không; cần xét reset, workload window và constraints.

### Bài 29 — pg_statio_user_indexes

View này cung cấp metric gì?

**Gợi ý:** index block reads/hits.

### Bài 30 — pg_stat_database_conflicts

View này hữu ích trên server nào?

**Gợi ý:** standby/recovery server.

### Bài 31 — track_io_timing

Setting này ảnh hưởng thống kê nào?

**Gợi ý:** block read/write time.

### Bài 32 — Counter delta

Vì sao cần lấy hai mẫu?

**Gợi ý:** tính rate trong một khoảng thời gian.

### Bài 33 — stats_reset

Vì sao phải lưu timestamp này?

**Gợi ý:** phát hiện counter reset và tránh delta sai.

### Bài 34 — Statistics snapshot

Một transaction dài có thể nhìn thấy gì?

**Gợi ý:** cached statistics snapshot tùy consistency setting/version.

### Bài 35 — pg_stat_clear_snapshot

Function này làm gì?

**Gợi ý:** xóa stats snapshot hiện tại trong session.

### Bài 36 — pg_stat_reset

Reset statistics có xóa dữ liệu table không?

**Gợi ý:** không, chỉ reset counters theo scope.

### Bài 37 — pg_monitor

Role này thường dùng cho ai?

**Gợi ý:** monitoring/observability account.

### Bài 38 — pg_stat_io

View này bổ sung góc nhìn nào?

**Gợi ý:** I/O theo backend type/object/context trên versions hỗ trợ.

### Bài 39 — pg_stat_statements

Extension này cung cấp góc nhìn nào?

**Gợi ý:** query-level execution statistics.

### Bài 40 — Dashboard

Vì sao counter tuyệt đối không đủ cho monitoring?

**Gợi ý:** không cho biết tốc độ/biến động trong cửa sổ hiện tại.

## 59. Câu hỏi thường gặp

### pg_stat_database có một row cho mỗi table không?

Không. Nó tổng hợp theo database. Dùng pg_stat_user_tables để xem từng bảng.

### numbackends có phải tổng connection đã mở từ khi server chạy?

Không. Đây là số backend hiện đang kết nối tới database.

### blks_read có luôn là physical disk reads không?

Không. PostgreSQL yêu cầu đọc block vào buffers; OS page cache có thể phục vụ mà không cần thiết bị storage.

### Hit ratio 99% có bảo đảm query nhanh?

Không. Query có thể bị chậm vì CPU, locks, network, execution plan, temp I/O hoặc các nguyên nhân khác.

### seq_scan cao có phải cần tạo index?

Không nhất thiết. Sequential scan thường là lựa chọn tốt cho bảng nhỏ hoặc query đọc phần lớn rows.

### n_dead_tup có phải số dead rows chính xác?

Không. Đây là estimate từ statistics.

### Autovacuum vừa chạy có nghĩa bảng đã sạch hoàn toàn?

Không. Vacuum có giới hạn bởi snapshots, locks, dead tuples còn được tham chiếu và workload.

### idx_scan bằng 0 có nghĩa index vô dụng?

Không. Cần xét observation window, reset time, constraints và workload hiếm.

### idx_tup_read có thể lớn hơn idx_tup_fetch không?

Có. Bitmap scans và các cách truy cập index khác làm semantics hai counter khác nhau.

### pg_stat_user_indexes có hiển thị system indexes không?

Không. Dùng pg_stat_all_indexes để xem cả system objects.

### Làm sao biết query nào gây temp files?

Database-level temp counters không chỉ ra query cụ thể. Dùng pg_stat_statements, log_temp_files và query-level diagnostics phù hợp.

### Có thể reset statistics mỗi ngày không?

Có thể theo quyền và policy, nhưng thường không cần thiết. Monitoring nên tính delta và lưu reset timestamp.

### Vì sao hai lần SELECT trong cùng transaction cho kết quả không đổi?

Statistics snapshot có thể được cache trong transaction theo stats_fetch_consistency/version. Có thể kết thúc transaction hoặc gọi pg_stat_clear_snapshot khi cần lấy snapshot mới.

### Có cần superuser để xem statistics không?

Không phải lúc nào cũng cần. Dùng pg_monitor hoặc pg_read_all_stats theo nhu cầu và version; tránh cấp superuser cho monitoring user.

### pg_stat_io có thay thế pg_statio_user_tables không?

Không. pg_stat_io bổ sung góc nhìn theo backend/object/context; pg_statio views vẫn hữu ích để xem relation-level I/O.

## 60. Tổng kết

Các truy vấn cốt lõi:

~~~sql
-- Tổng quan database.
SELECT
    datname,
    numbackends,
    xact_commit,
    xact_rollback,
    blks_read,
    blks_hit,
    temp_files,
    temp_bytes,
    deadlocks,
    conflicts,
    stats_reset
FROM pg_stat_database
WHERE datname = current_database();

-- Buffer hit ratio.
SELECT
    datname,
    round(
        100.0 * blks_hit
        / NULLIF(blks_hit + blks_read, 0),
        2
    ) AS hit_percent
FROM pg_stat_database
WHERE datname = current_database();

-- Table scans, writes và maintenance.
SELECT
    schemaname,
    relname,
    seq_scan,
    idx_scan,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_live_tup,
    n_dead_tup,
    last_autovacuum,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY seq_scan DESC;

-- Table block I/O.
SELECT
    schemaname,
    relname,
    heap_blks_read,
    heap_blks_hit,
    idx_blks_read,
    idx_blks_hit,
    toast_blks_read,
    toast_blks_hit
FROM pg_statio_user_tables;

-- Index usage.
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY idx_scan DESC;

-- Index block I/O.
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_blks_read,
    idx_blks_hit
FROM pg_statio_user_indexes;

-- Database conflicts on standby.
SELECT *
FROM pg_stat_database_conflicts;
~~~

Những nguyên tắc cần nhớ:

1. `pg_stat_database` cung cấp thống kê tổng hợp theo database.
2. `numbackends` là gauge hiện tại; phần lớn các counters còn lại là tích lũy.
3. `xact_commit` và `xact_rollback` giúp đo transaction workload.
4. `blks_hit`/`blks_read` hỗ trợ tính shared buffer hit ratio nhưng không mô tả physical disk I/O tuyệt đối.
5. `tup_returned` và `tup_fetched` phản ánh hoạt động đọc ở mức database.
6. `temp_files`/`temp_bytes` giúp phát hiện sort/hash spills.
7. `deadlocks` và `conflicts` là hai loại vấn đề khác nhau; conflicts trong database stats liên quan recovery trên standby.
8. `pg_stat_user_tables` theo dõi scans, tuple modifications và vacuum/analyze.
9. `seq_scan` cao không mặc định là xấu; phải xét table size và query plan.
10. `n_live_tup`/`n_dead_tup` là estimates, không phải COUNT chính xác.
11. `pg_statio_user_tables` tách heap, index và TOAST I/O.
12. `pg_stat_user_indexes` theo dõi index scans và tuple counters.
13. `idx_tup_read` khác `idx_tup_fetch`, nhất là với bitmap scans.
14. `idx_scan = 0` không đủ căn cứ để drop index.
15. `pg_statio_user_indexes` cho biết block read/hit theo index.
16. Dùng `stats_reset` để nhận diện counter reset.
17. Lưu mẫu định kỳ và tính delta/rate thay vì chỉ nhìn giá trị tích lũy.
18. Statistics snapshots có thể được cache trong transaction; dùng transaction ngắn khi polling.
19. Statistics là telemetry, không phải audit log hay dữ liệu giao dịch.
20. Cấp quyền monitoring tối thiểu, kiểm tra columns theo PostgreSQL major version.
21. Kết hợp `pg_stat_io` và `pg_stat_statements` khi cần thêm chiều I/O/query-level.
22. Đọc database, table, index và filesystem metrics cùng nhau trước khi điều chỉnh cấu hình.

Sơ đồ chọn view:

~~~text
Muốn quan sát workload PostgreSQL?
              |
              v
      Phạm vi database?
              |
              v
      pg_stat_database
              |
              +--> Transaction / cache / temp / deadlocks
              |
              v
       Cần tìm bảng?
              |
              v
      pg_stat_user_tables
              |
              +--> Scan / writes / vacuum / analyze
              |
              v
      Cần biết block I/O?
              |
              v
      pg_statio_user_tables
              |
              v
      Cần xem từng index?
              |
              v
      pg_stat_user_indexes
              |
              +--> Scan / tuple counters
              |
              v
      pg_statio_user_indexes
              |
              v
      Lưu samples và tính delta/rate
              |
              v
      Đối chiếu query plans, logs, OS I/O
~~~

**Kết luận:** `pg_stat_database` cho biết workload tổng thể; table statistics chỉ ra bảng nào đang được scan, thay đổi hoặc cần maintenance; index statistics cho biết indexes được truy cập và tiêu thụ I/O ra sao. Dùng các view này hiệu quả khi **phân biệt counter với gauge và estimate, tính delta theo thời gian, kiểm tra stats_reset, hiểu semantics của từng cột, và kết hợp với query plans cùng metrics hệ điều hành**.

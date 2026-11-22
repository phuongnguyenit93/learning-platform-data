# Đo hàng chết, lần VACUUM và tiến độ bảo trì trong PostgreSQL

## 1. Vì sao cần đo VACUUM?

PostgreSQL dùng MVCC để nhiều transactions có thể đọc các phiên bản dữ liệu phù hợp với snapshot của chúng. Khi một row được UPDATE hoặc DELETE, phiên bản cũ thường chưa thể xóa ngay vì transaction khác có thể vẫn cần nhìn thấy nó. Những tuple versions không còn cần thiết được gọi là dead tuples; VACUUM xác định khi nào chúng có thể được reclaim và cập nhật các metadata cần thiết.

Trong production, câu hỏi vận hành không chỉ là “bảng có bao nhiêu dead tuples?”. Ta cần biết:

- Ước lượng dead tuples đang tăng nhanh đến mức nào?
- Lần VACUUM thủ công và autovacuum gần nhất diễn ra khi nào?
- Autovacuum có đang chạy, đang ở phase nào và đã scan bao nhiêu heap blocks?
- Một VACUUM chạy lâu vì bảng lớn, index cleanup, I/O, lock hay vì horizon bị giữ bởi transaction cũ?
- Bảng có thực sự thiếu không gian hay chỉ có free space có thể tái sử dụng?
- Autovacuum có theo kịp tốc độ UPDATE/DELETE/INSERT không?
- Statistics có mới hay vừa bị reset/chưa được cập nhật?
- Partition nào đang cần bảo trì khi parent table không chứa heap pages?

Không có một metric duy nhất trả lời tất cả. Cần kết hợp table statistics, progress views, activity, logs, kích thước relation và kiểm tra vật lý có chọn lọc.

```text
Table statistics
  n_live_tup / n_dead_tup / last_autovacuum
                    |
                    v
       Estimate where maintenance is needed
                    |
                    v
pg_stat_progress_vacuum ---- pg_stat_activity
 phase, heap blocks           worker, waits, blockers
                    |
                    v
          Logs + relation size
                    |
                    v
      Diagnose cause and measure trend
                    |
                    v
        Tune / schedule / verify
```

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt live tuples, dead tuples, obsolete tuple versions và reusable free space.
2. Hiểu vì sao n_dead_tup chỉ là ước lượng.
3. Đọc pg_stat_user_tables và pg_stat_all_tables.
4. Diễn giải last_vacuum, last_autovacuum, vacuum_count và autovacuum_count.
5. Phân biệt VACUUM cleanup trigger với freeze trigger.
6. Ước lượng autovacuum threshold theo table size.
7. Hiểu insert-triggered vacuum và analyze threshold.
8. Xác định ảnh hưởng của per-table reloptions.
9. Theo dõi một VACUUM đang chạy qua pg_stat_progress_vacuum.
10. Diễn giải phase, heap_blks_scanned, heap_blks_vacuumed và index_vacuum_count.
11. Phân biệt progress VACUUM với progress ANALYZE.
12. Tìm autovacuum workers và wait events trong pg_stat_activity.
13. Dùng log_autovacuum_min_duration để quan sát các lần autovacuum.
14. Phân biệt dead tuple estimates với số đo vật lý từ pgstattuple.
15. Hiểu bloat, free space và khả năng trả disk space về hệ điều hành.
16. Tìm transaction/replication horizon đang ngăn tuple removal.
17. Đánh giá vacuum cadence theo tốc độ ghi và kích thước bảng.
18. Xây dashboard, alert và runbook bảo trì.
19. Xử lý các trường hợp vacuum chạy lâu, không chạy hoặc chạy liên tục.
20. Xác minh hiệu quả sau khi thay đổi cấu hình hoặc chạy VACUUM thủ công.

## 3. Các khái niệm cần đo

### 3.1. Live tuple

Live tuple là phiên bản row còn được xem là có hiệu lực theo trạng thái dữ liệu hiện tại. Một logical row có thể có nhiều tuple versions do UPDATE; chỉ một version phù hợp với snapshot mới nhất là current version.

### 3.2. Dead tuple

Dead tuple là tuple version không còn visible với bất kỳ transaction snapshot hợp lệ nào và có thể được reclaim. Một tuple vừa bị DELETE chưa chắc đã dead ngay: transaction cũ vẫn có thể cần nhìn thấy nó.

### 3.3. Tuple không còn visible nhưng chưa reclaim được

Có trường hợp tuple đã bị thay thế nhưng một transaction có snapshot cũ vẫn có thể cần version đó. VACUUM phải giữ lại cho đến khi global visibility horizon tiến đủ xa. Vì vậy, dead tuple estimate có thể tăng trong khi VACUUM vẫn chạy mà không loại bỏ được mọi tuple dự kiến.

### 3.4. Free space có thể tái sử dụng

VACUUM thường đánh dấu không gian trong heap pages để PostgreSQL có thể dùng lại cho INSERT/UPDATE sau này. Điều đó không có nghĩa file relation lập tức nhỏ đi trên filesystem.

### 3.5. Bloat

Bloat là phần không gian bị sử dụng kém hiệu quả do tuple versions, page fill patterns, index structure hoặc fragmentation. Dead tuple count là một tín hiệu, không phải phép đo bloat đầy đủ.

### 3.6. Vì sao phân biệt các khái niệm này?

| Quan sát | Có thể kết luận | Không thể kết luận |
| --- | --- | --- |
| n_dead_tup cao | Statistics ước lượng nhiều dead tuples | VACUUM chắc chắn đang bị lỗi |
| n_dead_tup thấp | Ước lượng ít dead tuples | Table/index không bị bloat |
| last_autovacuum gần đây | Autovacuum đã hoàn tất một lần được ghi nhận | Lần đó đã xử lý hết mọi vấn đề |
| VACUUM progress 100% heap scan | Heap scan đã đi hết phạm vi báo cáo | Toàn bộ vacuum đã kết thúc |
| Relation size không giảm | File chưa shrink | VACUUM không có tác dụng |
| vacuum_count tăng | Có VACUUM thủ công được ghi nhận | Autovacuum đã chạy |
| autovacuum_count tăng | Có autovacuum được ghi nhận | Tất cả bảng đều được bảo trì đúng hạn |

## 4. Đọc pg_stat_user_tables

Đây là view thường dùng đầu tiên để quan sát các bảng user.

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    n_mod_since_analyze,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze,
    vacuum_count,
    autovacuum_count,
    analyze_count,
    autoanalyze_count
FROM pg_catalog.pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 50;
```

### 4.1. Những cột quan trọng

| Cột | Ý nghĩa |
| --- | --- |
| schemaname, relname | Schema và tên bảng |
| n_live_tup | Ước lượng live tuples |
| n_dead_tup | Ước lượng dead tuples |
| n_mod_since_analyze | Số row modifications ước lượng kể từ ANALYZE gần nhất |
| last_vacuum | Thời điểm VACUUM thủ công gần nhất được ghi nhận |
| last_autovacuum | Thời điểm autovacuum gần nhất được ghi nhận |
| last_analyze | Thời điểm ANALYZE thủ công gần nhất |
| last_autoanalyze | Thời điểm autoanalyze gần nhất |
| vacuum_count | Số lần VACUUM thủ công được ghi nhận từ lần reset statistics |
| autovacuum_count | Số lần autovacuum được ghi nhận từ lần reset statistics |
| analyze_count | Số lần ANALYZE thủ công được ghi nhận |
| autoanalyze_count | Số lần autoanalyze được ghi nhận |

### 4.2. pg_stat_all_tables khác gì?

pg_stat_user_tables tập trung vào user tables. pg_stat_all_tables bao gồm cả system tables. Khi điều tra catalog hoặc relation hệ thống, dùng view all thay vì chỉ user view.

### 4.3. Dead percentage chỉ là tỷ lệ ước lượng

Có thể tạo một tỷ lệ để sắp xếp bảng:

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    round(
        100.0 * n_dead_tup
        / NULLIF(n_live_tup + n_dead_tup, 0),
        2
    ) AS estimated_dead_pct,
    pg_size_pretty(
        pg_total_relation_size(
            format('%I.%I', schemaname, relname)::regclass
        )
    ) AS total_size
FROM pg_catalog.pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 50;
```

Tên cột estimated_dead_pct cố ý nhấn mạnh đây là ước lượng. Một bảng 10.000 rows có tỷ lệ dead 30% có thể ít quan trọng hơn bảng 2 tỷ rows với tỷ lệ 3%, tùy dung lượng và tốc độ thay đổi.

### 4.4. Xem cả số lượng tuyệt đối và tỷ lệ

Dashboard nên có:

- Dead tuple estimate tuyệt đối.
- Dead percentage ước lượng.
- Total relation size.
- Tốc độ tăng dead tuples theo thời gian.
- Thời gian từ lần vacuum gần nhất.
- Write rate và thời gian vacuum gần nhất.

Không xếp ưu tiên chỉ theo phần trăm hoặc chỉ theo số lượng.

## 5. Hiểu giới hạn của statistics

### 5.1. n_dead_tup không phải COUNT(*) chính xác

PostgreSQL duy trì table statistics bằng cơ chế thu thập thống kê. Các giá trị live/dead tuple trong view là ước lượng, có thể trễ và có thể thay đổi sau ANALYZE/VACUUM hoặc các lần cập nhật statistics.

Đừng coi truy vấn sau là phép đếm vật lý chính xác:

```sql
SELECT n_dead_tup
FROM pg_stat_user_tables
WHERE relname = 'orders';
```

### 5.2. Statistics có thể chưa phản ánh workload vừa xảy ra

Nếu vừa chạy một đợt UPDATE lớn, statistics chưa chắc được cập nhật ngay. Đợi collector/backend flush và đọc lại trong transaction/session phù hợp.

### 5.3. Snapshot statistics trong transaction

Các statistics views có thể được đọc từ snapshot đã cache trong transaction hiện tại tùy phiên bản và cấu hình consistency. Khi cần đọc mới, dùng transaction ngắn hoặc gọi pg_stat_clear_snapshot() trước lần đọc kế tiếp nếu phù hợp với phiên bản.

### 5.4. Reset counters làm thay đổi cách diễn giải

Các hàm như pg_stat_reset() và pg_stat_reset_single_table_counters() có thể reset counters. Sau reset, vacuum_count/autovacuum_count có thể trở về 0 và lịch sử thống kê bị mất.

Không reset statistics để “làm dashboard đẹp” hoặc trước khi lưu evidence. Nếu cần reset cho một thử nghiệm, ghi nhận thời điểm và phạm vi reset.

### 5.5. NULL timestamp không đồng nghĩa lỗi

last_autovacuum IS NULL có thể nghĩa là chưa có autovacuum nào được ghi nhận kể từ lần reset hoặc bảng chưa từng được autovacuum. Kiểm tra stats reset, table age, thresholds và logs trước khi kết luận.

## 6. Theo dõi lịch sử VACUUM và ANALYZE

Một query tiện cho dashboard:

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
    last_autoanalyze,
    analyze_count,
    autoanalyze_count
FROM pg_catalog.pg_stat_user_tables
ORDER BY
    COALESCE(last_autovacuum, last_vacuum) NULLS FIRST,
    n_dead_tup DESC;
```

### 6.1. Thời điểm không phải runtime

last_autovacuum cho biết thời điểm lần gần nhất được ghi nhận, không cho biết lần đó chạy bao lâu. Runtime cần lấy từ progress/activity khi đang chạy hoặc từ logs sau khi hoàn tất.

### 6.2. Count không phải tổng lịch sử vĩnh viễn

Counters phụ thuộc statistics reset và vòng đời instance. Nếu cần lịch sử audit nhiều tháng, xuất metrics/logs sang monitoring system thay vì dựa vào counter trong database mãi mãi.

### 6.3. Vacuum thủ công và autovacuum là hai nguồn khác nhau

Một DBA chạy VACUUM table_name không làm autovacuum_count tăng. Ngược lại, autovacuum worker được ghi nhận ở autovacuum_count.

### 6.4. Analyze không thay VACUUM

ANALYZE cập nhật planner statistics. Nó không loại dead tuples hoặc thay freezing. VACUUM có thể được gọi với tùy chọn ANALYZE để thực hiện cả hai công việc, nhưng mục tiêu và counters vẫn khác nhau.

## 7. Ước lượng autovacuum threshold

Autovacuum cleanup theo dead tuples thường sử dụng threshold kết hợp scale factor.

Một công thức gần đúng:

```text
vacuum threshold =
    autovacuum_vacuum_threshold
    + autovacuum_vacuum_scale_factor * reltuples
```

Trong đó reltuples là ước lượng row count trong pg_class, không nhất thiết chính xác tuyệt đối.

### 7.1. Ví dụ

Giả sử:

- autovacuum_vacuum_threshold = 50
- autovacuum_vacuum_scale_factor = 0.2
- reltuples = 1,000,000

Ngưỡng ước lượng:

```text
50 + 0.2 * 1,000,000 = 200,050 dead tuples
```

Một bảng lớn có thể tích lũy rất nhiều dead tuples trước khi trigger theo scale factor. Đây là lý do một số bảng lớn cần per-table settings thấp hơn.

### 7.2. Đọc global settings

```sql
SELECT
    name,
    setting,
    unit,
    source
FROM pg_catalog.pg_settings
WHERE name IN (
    'autovacuum',
    'track_counts',
    'autovacuum_vacuum_threshold',
    'autovacuum_vacuum_scale_factor',
    'autovacuum_vacuum_insert_threshold',
    'autovacuum_vacuum_insert_scale_factor',
    'autovacuum_analyze_threshold',
    'autovacuum_analyze_scale_factor',
    'autovacuum_max_workers',
    'autovacuum_naptime'
)
ORDER BY name;
```

Nếu setting không tồn tại trên major version hiện tại, nó đơn giản không xuất hiện trong kết quả.

### 7.3. Per-table reloptions có thể override global values

Một bảng có thể khai báo các options riêng như autovacuum vacuum scale factor/threshold. Vì vậy công thức dùng global settings chỉ là ước lượng khi bảng không override.

Xem cấu hình relation:

```sql
SELECT
    c.oid::regclass AS relation,
    c.reltuples,
    c.reloptions
FROM pg_catalog.pg_class AS c
WHERE c.relkind IN ('r', 'm')
  AND c.reloptions IS NOT NULL
ORDER BY c.oid::regclass::text;
```

### 7.4. Ví dụ đặt scale factor cho một bảng lớn

```sql
ALTER TABLE app.orders
SET (
    autovacuum_vacuum_scale_factor = 0.02,
    autovacuum_vacuum_threshold = 5000
);
```

Đây chỉ là ví dụ. Chọn giá trị dựa trên write rate, table size, vacuum runtime, I/O capacity và yêu cầu bloat. Không copy cùng một giá trị lên mọi bảng.

### 7.5. Xem lại sau khi đổi

Sau thay đổi, theo dõi nhiều chu kỳ:

- Dead tuple estimate ngay trước vacuum.
- Thời gian để trigger.
- Runtime và phase.
- Dead tuple estimate sau vacuum.
- Disk/IO impact.
- Có vacuum chạy liên tục hay không.

Một cấu hình quá thấp có thể khiến autovacuum chạy thường xuyên và cạnh tranh I/O; quá cao có thể để bảng tích tụ dead tuples quá lâu.

## 8. Insert-triggered vacuum và ANALYZE threshold

### 8.1. Bảng append-only cũng có thể cần autovacuum

Bảng chỉ INSERT ít dead tuples vẫn có thể cần vacuum để freeze transaction IDs. Ngoài trigger theo dead tuples, PostgreSQL có cơ chế vacuum dựa trên số rows insert mới và freeze age.

### 8.2. Insert threshold

Một công thức gần đúng cho insert-triggered vacuum:

```text
insert vacuum threshold =
    autovacuum_vacuum_insert_threshold
    + autovacuum_vacuum_insert_scale_factor * reltuples
```

Cơ chế này đặc biệt hữu ích cho bảng insert-heavy, vì không thể chờ dead tuples mới chạy vacuum freeze.

### 8.3. Analyze threshold

Autoanalyze được kích hoạt dựa trên số modifications ước lượng:

```text
analyze threshold =
    autovacuum_analyze_threshold
    + autovacuum_analyze_scale_factor * reltuples
```

Analyze cần cập nhật statistics để planner chọn kế hoạch phù hợp. Một bảng có dead tuple thấp vẫn có thể cần ANALYZE sau một đợt phân phối dữ liệu thay đổi lớn.

### 8.4. n_mod_since_analyze

Cột này giúp nhận biết số modifications kể từ analyze gần nhất. Nó là estimate/counter theo statistics, không phải số transaction hay số SQL statements.

### 8.5. Freeze threshold là cơ chế riêng

Không nhầm cleanup trigger với autovacuum_freeze_max_age hoặc MultiXact freeze thresholds. Một relation có thể được yêu cầu anti-wraparound vacuum ngay cả khi dead tuple count thấp.

## 9. Xem quan hệ nào cần ưu tiên bảo trì

Query kết hợp size, dead tuples, timestamps và vacuum cadence:

```sql
SELECT
    s.schemaname,
    s.relname,
    s.n_live_tup,
    s.n_dead_tup,
    round(
        100.0 * s.n_dead_tup
        / NULLIF(s.n_live_tup + s.n_dead_tup, 0),
        2
    ) AS estimated_dead_pct,
    pg_size_pretty(pg_relation_size(s.relid)) AS heap_size,
    pg_size_pretty(pg_indexes_size(s.relid)) AS indexes_size,
    pg_size_pretty(pg_total_relation_size(s.relid)) AS total_size,
    s.last_autovacuum,
    s.autovacuum_count,
    s.last_vacuum,
    s.vacuum_count
FROM pg_catalog.pg_stat_user_tables AS s
ORDER BY
    pg_total_relation_size(s.relid) DESC,
    s.n_dead_tup DESC
LIMIT 100;
```

### 9.1. Vì sao cần heap size và index size?

VACUUM có thể phải xử lý cả heap và indexes. Một bảng có heap nhỏ nhưng index lớn vẫn có thể mất nhiều thời gian ở index vacuum phase.

### 9.2. Partitioned tables

Parent partitioned table thường không lưu heap rows. Theo dõi từng leaf partition và index tương ứng; nếu cần tổng hợp, group theo parent/partition tree bằng catalog inheritance metadata.

### 9.3. TOAST

Giá trị lớn có thể được lưu trong TOAST relation. Khi điều tra bảng có payload lớn, nhớ rằng total relation size bao gồm TOAST/index components, còn heap-only size không phản ánh toàn bộ dung lượng.

## 10. Đo vật lý bằng pgstattuple

Khi statistics estimates không đủ để điều tra, extension pgstattuple cung cấp thông tin vật lý chi tiết hơn.

### 10.1. Cài extension

Cần quyền phù hợp và extension phải có trong installation:

```sql
CREATE EXTENSION IF NOT EXISTS pgstattuple;
```

### 10.2. Đo chi tiết bằng pgstattuple

```sql
SELECT *
FROM pgstattuple('app.orders'::regclass);
```

Kết quả thường bao gồm:

| Cột | Ý nghĩa |
| --- | --- |
| table_len | Kích thước relation bytes |
| tuple_count | Số live tuples được quan sát |
| tuple_len | Bytes thuộc live tuples |
| tuple_percent | Phần trăm bytes live tuple |
| dead_tuple_count | Số dead tuples được quan sát |
| dead_tuple_len | Bytes dead tuples |
| dead_tuple_percent | Phần trăm bytes dead tuples |
| free_space | Free bytes |
| free_percent | Tỷ lệ free bytes |

pgstattuple phải scan relation và có thể tạo I/O đáng kể. Chọn thời điểm và phạm vi cẩn thận, nhất là với bảng hàng trăm GB/TB.

### 10.3. pgstattuple_approx

```sql
SELECT *
FROM pgstattuple_approx('app.orders'::regclass);
```

Hàm approximate tận dụng visibility map để giảm lượng scan trong một số trường hợp. Kết quả là phép đo gần đúng, không thay cho full scan chính xác.

### 10.4. Không chạy pgstattuple liên tục trên mọi bảng

Đây là công cụ chẩn đoán, không phải metric polling mỗi vài giây. Dùng để xác minh một nghi vấn hoặc lấy baseline theo lịch có kiểm soát.

### 10.5. So sánh với statistics

| Nguồn | Ưu điểm | Giới hạn |
| --- | --- | --- |
| pg_stat_user_tables | Nhẹ, phù hợp dashboard | Estimates, có độ trễ |
| pgstattuple | Đo vật lý chi tiết | Có thể scan toàn relation, tốn I/O |
| pgstattuple_approx | Ít scan hơn trong điều kiện phù hợp | Approximate, phụ thuộc VM |
| VACUUM VERBOSE log | Thấy kết quả một lần vacuum | Chỉ có khi bật/thu log phù hợp |

## 11. VACUUM không nhất thiết làm file nhỏ đi

Một trong các nhầm lẫn thường gặp: chạy VACUUM xong nhưng pg_total_relation_size không giảm.

### 11.1. Reuse space

VACUUM thường đánh dấu free space để PostgreSQL dùng lại trong relation. File có thể giữ nguyên kích thước trên filesystem nhưng các pages bên trong đã có không gian trống có ích.

### 11.2. Truncation ở cuối heap

Trong một số điều kiện, VACUUM có thể truncate các empty pages ở cuối relation và trả chúng về filesystem. Điều này cần điều kiện phù hợp và có thể cần lock; không phải mọi free pages đều có thể truncate.

### 11.3. VACUUM FULL

VACUUM FULL rewrite relation để thu hồi không gian mạnh hơn, nhưng cần lock mạnh, thời gian và disk headroom. Nó không phải thao tác thường kỳ thay cho VACUUM.

### 11.4. Index bloat

VACUUM heap không nhất thiết làm index file shrink đáng kể. Index cleanup có thể đánh dấu/recycle index pages theo loại index và phương thức; nếu index bloat nghiêm trọng, cần điều tra riêng. Không kết luận từ heap dead tuples.

### 11.5. Đo cả heap, index và total size

```sql
SELECT
    c.oid::regclass AS relation,
    pg_size_pretty(pg_relation_size(c.oid)) AS heap_size,
    pg_size_pretty(pg_indexes_size(c.oid)) AS indexes_size,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
FROM pg_catalog.pg_class AS c
WHERE c.oid = 'app.orders'::regclass;
```

Lấy số đo trước/sau theo cùng điều kiện để thấy xu hướng.

## 12. Theo dõi VACUUM đang chạy bằng pg_stat_progress_vacuum

View này cho biết VACUUM nào đang chạy và tiến độ các phase.

```sql
SELECT
    p.pid,
    a.datname,
    p.relid::regclass AS relation,
    p.phase,
    p.heap_blks_total,
    p.heap_blks_scanned,
    p.heap_blks_vacuumed,
    p.index_vacuum_count,
    p.max_dead_tuples,
    p.num_dead_tuples,
    round(
        100.0 * p.heap_blks_scanned
        / NULLIF(p.heap_blks_total, 0),
        1
    ) AS heap_scan_pct,
    clock_timestamp() - a.query_start AS runtime,
    a.wait_event_type,
    a.wait_event
FROM pg_catalog.pg_stat_progress_vacuum AS p
JOIN pg_catalog.pg_stat_activity AS a
  ON a.pid = p.pid
ORDER BY a.query_start;
```

### 12.1. Các cột quan trọng

| Cột | Diễn giải |
| --- | --- |
| pid | Backend đang chạy VACUUM |
| relid | Relation được vacuum |
| phase | Phase hiện tại |
| heap_blks_total | Tổng heap blocks trong phạm vi progress |
| heap_blks_scanned | Heap blocks đã scan |
| heap_blks_vacuumed | Heap blocks đã vacuum |
| index_vacuum_count | Số chu kỳ index vacuum đã thực hiện |
| max_dead_tuples | Capacity của dead tuple storage array |
| num_dead_tuples | Số dead tuples hiện đang giữ trong array |

### 12.2. Các phase thường gặp

Tên phase cụ thể có thể thay đổi theo major version, nhưng thường bao gồm:

1. initializing: khởi tạo VACUUM.
2. scanning heap: scan heap để tìm dead tuples và các metadata cần xử lý.
3. vacuuming indexes: xử lý index entries trỏ tới dead tuples.
4. vacuuming heap: xử lý heap pages sau index phase.
5. cleaning up indexes: cleanup index structures.
6. truncating heap: thử truncate empty pages ở cuối heap nếu phù hợp.
7. performing final cleanup: cập nhật catalog/statistics và hoàn tất công việc.

Không giả định mọi phiên bản hoặc mọi lần VACUUM đều hiển thị chính xác toàn bộ các phase trên.

### 12.3. Tính heap scan percentage

heap_scan_pct là tỷ lệ blocks đã scan so với tổng blocks mà progress view báo cáo. Nó hữu ích khi phase là scanning heap.

Khi VACUUM chuyển sang vacuuming indexes hoặc cleanup, heap scan có thể đã đạt 100% trong khi công việc chưa hoàn tất. Vì vậy không dùng một tỷ lệ này làm “percent complete” chung.

### 12.4. num_dead_tuples không phải tổng dead tuples trong bảng

num_dead_tuples là số tuples đang được giữ trong buffer/array của tiến trình vacuum để xử lý index cleanup. Khi array đầy, VACUUM có thể phải chạy một chu kỳ index vacuum rồi tiếp tục scan. Nó không phải table-wide dead tuple count.

### 12.5. index_vacuum_count

Nếu VACUUM phải lặp nhiều chu kỳ index cleanup, giá trị này có thể tăng. Một số chu kỳ không tự động có nghĩa lỗi; nhưng trên bảng lớn, nó giúp giải thích vì sao index phase lặp lại.

### 12.6. Không thấy row trong progress view nghĩa là gì?

Chỉ có nghĩa không có VACUUM process được hiển thị tại thời điểm truy vấn. VACUUM có thể chưa được schedule, đã kết thúc, đang chờ worker slot hoặc bị chặn trước khi vào phase quan sát được. Kiểm tra lịch sử, logs, stats và autovacuum launcher.

## 13. Theo dõi autovacuum worker qua pg_stat_activity

```sql
SELECT
    pid,
    datname,
    backend_type,
    application_name,
    state,
    query_start,
    clock_timestamp() - query_start AS runtime,
    wait_event_type,
    wait_event,
    left(query, 300) AS query_sample
FROM pg_catalog.pg_stat_activity
WHERE backend_type = 'autovacuum worker'
   OR query LIKE 'autovacuum:%'
ORDER BY query_start;
```

### 13.1. backend_type

Các phiên bản PostgreSQL hiện đại có thể phân loại backend bằng backend_type. Nếu phiên bản cũ không có cột này, dùng query text/application name phù hợp với version.

### 13.2. Wait events

- IO: worker đang chờ I/O.
- Lock: đang chờ lock.
- BufferPin: có thể đang chờ buffer pin.
- Không có wait event: backend có thể đang chạy CPU hoặc không ở trạng thái chờ.

Wait event chỉ là tín hiệu. Cần xem phase, runtime và workload để xác định nguyên nhân.

### 13.3. Autovacuum không nhất thiết có query text dễ đọc

Query có thể hiển thị command autovacuum hoặc chuỗi nội bộ tùy version. Dùng pg_stat_progress_vacuum.relid để xác định relation chính xác khi worker đang VACUUM.

### 13.4. Nhiều worker chạy đồng thời

Autovacuum có thể chạy nhiều workers trên các relations khác nhau. Đừng chỉ kiểm tra một PID; tổng hợp số workers, relations, runtime và waits.

## 14. Theo dõi ANALYZE riêng

VACUUM progress và ANALYZE progress là hai view khác nhau. Khi ANALYZE chạy, xem:

```sql
SELECT
    p.pid,
    a.datname,
    p.relid::regclass AS relation,
    p.phase,
    p.sample_blks_total,
    p.sample_blks_scanned,
    p.ext_stats_total,
    p.ext_stats_computed,
    clock_timestamp() - a.query_start AS runtime
FROM pg_catalog.pg_stat_progress_analyze AS p
JOIN pg_catalog.pg_stat_activity AS a
  ON a.pid = p.pid;
```

Các cột/phase cụ thể có thể thay đổi theo phiên bản. Nếu không có row trong view, ANALYZE có thể chưa chạy hoặc đã kết thúc.

### 14.1. Vì sao analyze progress quan trọng?

Một bảng có thể được vacuum thường xuyên nhưng planner statistics vẫn stale nếu analyze không theo kịp. Query plan kém có thể làm workload chậm và tạo thêm pressure cho hệ thống.

### 14.2. VACUUM ANALYZE

```sql
VACUUM (ANALYZE, VERBOSE) app.orders;
```

Lệnh này yêu cầu cả vacuum và analyze. Chạy ngoài transaction block. Với bảng lớn, đánh giá runtime/I/O và chọn thời điểm phù hợp.

## 15. VACUUM VERBOSE và logs

### 15.1. Chạy thủ công với VERBOSE

```sql
VACUUM (VERBOSE) app.orders;
```

Verbose output cung cấp thông tin về pages, tuples và index cleanup mà VACUUM đã thực hiện. Nội dung chi tiết phụ thuộc PostgreSQL version.

### 15.2. log_autovacuum_min_duration

Setting này kiểm soát việc ghi log các lần autovacuum/autoanalyze đủ dài:

```sql
SHOW log_autovacuum_min_duration;
```

- Giá trị âm thường tắt log autovacuum theo setting này.
- 0 ghi log mọi lần autovacuum.
- Giá trị dương ghi các lần kéo dài ít nhất số milliseconds đã cấu hình.

Bật log toàn bộ trong thời gian dài có thể tạo nhiều log; cân nhắc dung lượng, retention và mục tiêu điều tra.

### 15.3. Tìm logs có ích

Log có thể cho biết:

- Relation được vacuum.
- Số pages scan/vacuum.
- Tuples removed hoặc còn lại.
- Index cleanup cycles.
- Buffer usage/cost.
- Runtime.
- Lý do autovacuum được kích hoạt trong một số thông báo/version.

### 15.4. Log và statistics bổ sung cho nhau

Statistics giúp dashboard nhanh; progress view giúp theo dõi đang chạy; logs giúp xem chi tiết sau khi hoàn tất. Dùng cả ba để có timeline.

## 16. Xác định vacuum bị chặn bởi transaction horizon

VACUUM không thể loại bỏ tuple versions nếu snapshot cũ còn có thể cần chúng. Khi n_dead_tup cao và VACUUM chạy nhưng không giảm, hãy kiểm tra horizon blockers.

### 16.1. Transaction lâu nhất

```sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    state,
    xact_start,
    clock_timestamp() - xact_start AS xact_age,
    backend_xmin,
    CASE
        WHEN backend_xmin IS NOT NULL THEN age(backend_xmin)
    END AS backend_xmin_age,
    wait_event_type,
    wait_event,
    left(query, 250) AS query_sample
FROM pg_catalog.pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

### 16.2. Idle in transaction

```sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    xact_start,
    clock_timestamp() - xact_start AS xact_age,
    state_change,
    clock_timestamp() - state_change AS idle_age,
    backend_xmin,
    left(query, 250) AS last_query
FROM pg_catalog.pg_stat_activity
WHERE state = 'idle in transaction'
ORDER BY xact_start;
```

Transaction read-only cũng có thể giữ snapshot cũ. Không chỉ tìm sessions đang UPDATE/DELETE.

### 16.3. Replication slots

```sql
SELECT
    slot_name,
    slot_type,
    active,
    xmin,
    CASE WHEN xmin IS NOT NULL THEN age(xmin) END AS xmin_age,
    catalog_xmin,
    CASE
        WHEN catalog_xmin IS NOT NULL THEN age(catalog_xmin)
    END AS catalog_xmin_age,
    restart_lsn
FROM pg_catalog.pg_replication_slots
ORDER BY GREATEST(
    COALESCE(age(xmin), 0),
    COALESCE(age(catalog_xmin), 0)
) DESC;
```

Slot có thể giữ WAL và/hoặc visibility/catalog horizon. Xác minh owner và consumer trước khi thay đổi hoặc drop slot.

### 16.4. Prepared transactions

```sql
SELECT
    transaction,
    gid,
    prepared,
    clock_timestamp() - prepared AS prepared_age,
    owner,
    database
FROM pg_catalog.pg_prepared_xacts
ORDER BY prepared;
```

Prepared transactions tồn tại lâu có thể giữ locks và transaction state. Resolve qua coordinator/runbook; không tự động rollback mọi prepared transaction.

### 16.5. Diễn giải khi vacuum không reclaim được

Một VACUUM có thể scan thành công nhưng không loại bỏ được tất cả tuples dự kiến vì global horizon. Khi đó tăng workers hoặc tăng cost limit không giải quyết blocker gốc.

## 17. VACUUM, visibility map và index cleanup

### 17.1. Heap và index có công việc khác nhau

VACUUM tìm tuple versions không còn cần thiết trong heap, sau đó xử lý index entries tham chiếu tới chúng. Bảng có nhiều indexes hoặc index lớn có thể tốn nhiều thời gian ở index phases.

### 17.2. Visibility map

VM lưu trạng thái all-visible/all-frozen theo page. Nó giúp index-only scans và cho phép một số vacuum scans bỏ qua pages đã an toàn. VM không phải dead tuple counter.

### 17.3. Index cleanup bị trì hoãn

Một số tùy chọn VACUUM và điều kiện workload có thể ảnh hưởng việc index cleanup. Nếu cleanup bị trì hoãn, dead index entries có thể tồn tại lâu hơn; đừng suy luận chỉ từ heap n_dead_tup.

### 17.4. Heap vacuumed blocks

heap_blks_vacuumed cho biết blocks đã được vacuum trong progress context. Nó không đo số bytes trả về OS hoặc tổng bloat đã xóa.

### 17.5. Index size nên được theo dõi riêng

Dùng pg_indexes_size() và kiểm tra index usage/structure theo workload. Nếu index có dấu hiệu bloat, đánh giá công cụ phù hợp như REINDEX/REINDEX CONCURRENTLY theo version và locking requirements; đó là công việc riêng với VACUUM thường.

## 18. Theo dõi table size và thay đổi theo thời gian

Một snapshot size đơn lẻ ít ý nghĩa hơn trend.

```sql
SELECT
    s.schemaname,
    s.relname,
    pg_relation_size(s.relid) AS heap_bytes,
    pg_indexes_size(s.relid) AS index_bytes,
    pg_total_relation_size(s.relid) AS total_bytes,
    s.n_live_tup,
    s.n_dead_tup,
    s.last_autovacuum
FROM pg_catalog.pg_stat_user_tables AS s
ORDER BY pg_total_relation_size(s.relid) DESC
LIMIT 100;
```

Lưu kết quả định kỳ ở hệ thống monitoring bên ngoài để phân tích:

- Heap/index/total size theo ngày.
- Dead tuple estimates.
- Vacuum timestamps/runtime.
- Insert/update/delete rates.
- Vacuum progress duration.
- Disk free space.
- WAL generation và replication lag.

Không tạo bảng metrics trong cùng database với retention vô hạn mà không có cleanup plan.

## 19. Capacity planning và vacuum cadence

### 19.1. Throughput là yếu tố chính

Một bảng 100 GB với vài nghìn updates mỗi ngày khác một bảng 100 GB nhận hàng triệu updates mỗi giờ. Cần đánh giá tốc độ phát sinh tuple versions và khả năng vacuum xử lý.

### 19.2. Runtime so với interval

Nếu một bảng cần vacuum mỗi 10 phút nhưng mỗi lần mất 30 phút, worker capacity hoặc threshold strategy có vấn đề. Theo dõi runtime và interval qua logs/metrics.

### 19.3. Autovacuum worker slots

Nhiều bảng cùng vượt ngưỡng có thể cạnh tranh autovacuum_max_workers. Một relation quan trọng có thể phải chờ worker slot dù đủ điều kiện vacuum.

### 19.4. I/O budget

VACUUM cạnh tranh storage bandwidth với ứng dụng, backups và replication. Cost delay giúp điều tiết nhưng có thể khiến vacuum không theo kịp. Đo latency và throughput thay vì chỉ tăng cost limit.

### 19.5. Bảng lớn

Scale factor cố định khiến ngưỡng dead tuples tăng theo table size. Có thể dùng scale factor nhỏ hơn cho bảng lớn, kết hợp threshold tối thiểu để tránh vacuum quá thường xuyên ở bảng nhỏ.

### 19.6. Partitioning

Partitioning có thể giới hạn phạm vi bảo trì và giúp vacuum từng partition. Tuy nhiên, quá nhiều partitions làm tăng catalog overhead và autovacuum scheduling work. Chọn partition granularity phù hợp.

## 20. Dashboard đề xuất

Một dashboard vận hành nên có các nhóm:

| Nhóm | Metric | Mục đích |
| --- | --- | --- |
| Table health | n_dead_tup, estimated_dead_pct | Phát hiện tích tụ |
| Table health | heap/index/total bytes | Xác định tác động dung lượng |
| Maintenance history | last_autovacuum, last_vacuum | Phát hiện bảng lâu chưa vacuum |
| Maintenance history | autovacuum_count, vacuum_count | Nhìn hoạt động từ lần reset |
| Analyze | n_mod_since_analyze, last_autoanalyze | Phát hiện planner stats stale |
| Active progress | phase, heap_blks_scanned/total | Theo dõi vacuum hiện tại |
| Active progress | runtime, wait events | Phân tích chậm |
| Horizon | oldest xact age, backend_xmin | Tìm blockers |
| Replication | slot xmin/catalog_xmin, lag | Phát hiện retention |
| Capacity | autovacuum workers, I/O, disk free | Xác định khả năng theo kịp |
| Freeze | XID/MXID age | Chống wraparound |

### 20.1. Alert theo xu hướng

Cảnh báo khi dead tuple estimate tăng liên tục qua nhiều lần scrape, vacuum interval dài bất thường, runtime vượt baseline hoặc freeze age tiến gần ngưỡng.

### 20.2. Không alert theo một mẫu đơn lẻ

Statistics có thể lag hoặc reset. Dùng nhiều mẫu, thresholds và context của table size/write rate để giảm false positives.

### 20.3. Severity theo tác động

- **Info:** vacuum vừa chạy, metrics ổn định.
- **Warning:** dead tuple estimate tăng, vacuum interval/runtime cao hơn baseline.
- **Critical:** anti-wraparound age gần ngưỡng, vacuum không tiến triển, disk/WAL gần đầy hoặc horizon blocker nghiêm trọng.

## 21. Runbook khi dead tuples tăng cao

### Bước 1. Xác định bảng và quy mô

Lấy n_dead_tup, estimated percentage, heap/index/total size, write rate và partition scope.

### Bước 2. Kiểm tra lần vacuum gần nhất

Đọc last_autovacuum, last_vacuum, counters và reset history. Xác định bảng có từng được autovacuum chưa.

### Bước 3. Xem autovacuum có đang chạy

Dùng pg_stat_progress_vacuum và pg_stat_activity. Nếu worker đang chạy, xem phase, runtime, wait event và relation.

### Bước 4. Kiểm tra threshold

Đọc global settings, reltuples và reloptions. Tính rough threshold và so với write rate. Không kết luận autovacuum “bị hỏng” chỉ vì nó chưa chạy khi bảng chưa đạt trigger.

### Bước 5. Tìm horizon blockers

Kiểm tra long transactions, idle-in-transaction, prepared transactions, replication slots và standby feedback.

### Bước 6. Kiểm tra logs

Dùng autovacuum logs để xác định runtime, pages, tuples, index cycles và các lần bị cancel/failure.

### Bước 7. Chọn hành động

- Nếu chưa tới threshold: cân nhắc table-specific tuning nếu workload yêu cầu.
- Nếu worker slot thiếu: xem số workers và backlog.
- Nếu I/O chậm: đo storage và cân bằng vacuum cost.
- Nếu horizon bị giữ: xử lý blocker có kiểm soát.
- Nếu index cleanup là bottleneck: điều tra index workload/size.
- Nếu chỉ cần đo chính xác: chạy pgstattuple có chọn lọc.

### Bước 8. Xác minh sau hành động

Đọc lại estimates, timestamps, progress/logs và size trend. Đừng chỉ coi lệnh VACUUM trả exit code 0 là đã giải quyết.

## 22. Chạy VACUUM thủ công đúng cách

### 22.1. VACUUM thường

```sql
VACUUM (VERBOSE) app.orders;
```

### 22.2. VACUUM kèm ANALYZE

```sql
VACUUM (ANALYZE, VERBOSE) app.orders;
```

### 22.3. VACUUM FREEZE

```sql
VACUUM (FREEZE, VERBOSE) app.orders;
```

Dùng khi cần freeze sớm hơn theo kế hoạch. Freeze và anti-wraparound là chủ đề riêng; xem cả XID/MXID age, không chỉ dead tuples.

### 22.4. VACUUM không chạy trong transaction block

Không bọc các lệnh trên trong explicit BEGIN ... COMMIT. Một số migration tools tự động tạo transaction; cấu hình cách chạy VACUUM riêng.

### 22.5. Chọn đúng relation

Nếu relation là partitioned parent, VACUUM parent có thể không làm công việc heap như bạn mong đợi; xác định leaf partitions. Kiểm tra quyền và maintenance window.

### 22.6. VACUUM FULL không phải default

Chỉ dùng VACUUM FULL khi mục tiêu thực sự là rewrite/shrink và đã lên kế hoạch lock, runtime, disk headroom. Nó không phải cách thay thế cho autovacuum thường.

## 23. Các tình huống chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Bằng chứng tiếp theo |
| --- | --- | --- |
| n_dead_tup cao, last_autovacuum NULL | Chưa trigger, stats reset, autovacuum disabled hoặc worker chưa chạy | Settings, reloptions, logs, counters |
| n_dead_tup cao, worker đang scanning | Bảng lớn hoặc vacuum đang tiến triển | Progress phase, runtime, blocks |
| Heap scan xong nhưng worker còn chạy | Index cleanup/final cleanup | phase, index_vacuum_count, waits |
| Vacuum chạy nhiều lần nhưng estimate vẫn cao | Write rate cao, estimate lag, horizon blocker | Trend, transactions, logs |
| Dead estimate thấp nhưng size lớn | Free space/bloat/index size | pgstattuple, index size, history |
| VACUUM xong size không giảm | Space được reuse trong relation | Heap size trend, future inserts |
| Autovacuum chạy liên tục | Threshold quá thấp hoặc workload churn cao | reloptions, write rate, runtime |
| Một partition stale | Parent không chứa heap; partition không đạt trigger hoặc worker backlog | Stats từng leaf partition |
| Analyze timestamp cũ | Analyze threshold chưa đạt hoặc stats reset | n_mod_since_analyze, analyze settings |
| Vacuum không reclaim tuple | Snapshot/horizon còn giữ | backend_xmin, slots, prepared xacts |
| Nhiều index vacuum cycles | Dead tuple array bị lấp nhiều lần | index_vacuum_count, index count, logs |
| Vacuum bị chậm vì IO | Storage contention/cost throttling | wait events, disk metrics, logs |

## 24. Các sai lầm cần tránh

1. Coi n_dead_tup là số đếm chính xác.
2. Đánh giá vacuum chỉ bằng last_autovacuum mà không xem runtime và kết quả.
3. Nhầm vacuum_count với autovacuum_count.
4. Kết luận bảng không cần vacuum vì không có UPDATE/DELETE.
5. Coi heap scan 100% là toàn bộ vacuum đã xong.
6. Coi num_dead_tuples trong progress view là tổng dead tuples của bảng.
7. Chạy pgstattuple liên tục trên mọi bảng lớn.
8. Reset statistics trước khi lưu evidence.
9. Tăng autovacuum workers mà không đo I/O/CPU.
10. Tăng scale factor chỉ để giảm tần suất log.
11. Tắt autovacuum để tránh I/O.
12. Cancel anti-wraparound vacuum vì workload thấy chậm.
13. Dùng VACUUM FULL như giải pháp mặc định.
14. Kỳ vọng VACUUM thường luôn shrink file trên filesystem.
15. Bỏ qua index/TOAST/partition khi đo total relation size.
16. Bỏ qua transaction cũ và replication slot.
17. So sánh metrics giữa hai thời điểm khác nhau mà không biết stats reset.
18. Alert chỉ theo một sample n_dead_tup.
19. Coi ANALYZE thay thế VACUUM.
20. Không lưu logs/metrics nên không thể biết vacuum cadence theo thời gian.

## 25. Bài tập thực hành có đáp án

Các bài tập dùng PostgreSQL catalog/statistics views. Những lệnh VACUUM phải chạy ngoài transaction block.

### Bài 1. Dead tuple là gì?

**Đáp án:** Tuple version không còn visible với bất kỳ snapshot hợp lệ nào và có thể được reclaim khi VACUUM xử lý.

### Bài 2. Vì sao tuple vừa DELETE chưa chắc được reclaim?

**Đáp án:** Transaction snapshot cũ có thể vẫn cần nhìn thấy tuple version đó.

### Bài 3. n_dead_tup có phải COUNT chính xác?

**Đáp án:** Không. Đây là estimate từ statistics.

### Bài 4. View nào theo dõi user tables?

**Đáp án:** pg_stat_user_tables.

### Bài 5. View nào bao gồm cả system tables?

**Đáp án:** pg_stat_all_tables.

### Bài 6. n_live_tup có ý nghĩa gì?

**Đáp án:** Ước lượng số live tuples của relation.

### Bài 7. last_autovacuum khác last_vacuum thế nào?

**Đáp án:** Một bên là autovacuum gần nhất, bên kia là VACUUM thủ công gần nhất được ghi nhận.

### Bài 8. autovacuum_count có đếm VACUUM thủ công?

**Đáp án:** Không. VACUUM thủ công được theo dõi bằng vacuum_count.

### Bài 9. n_mod_since_analyze dùng làm gì?

**Đáp án:** Ước lượng số row modifications kể từ ANALYZE gần nhất.

### Bài 10. NULL last_autovacuum chứng minh autovacuum bị tắt?

**Đáp án:** Không. Có thể chưa chạy, stats vừa reset hoặc chưa được ghi nhận.

### Bài 11. Công thức dead tuple vacuum threshold?

```text
autovacuum_vacuum_threshold
+ autovacuum_vacuum_scale_factor * reltuples
```

**Đáp án:** Threshold cộng scale factor nhân ước lượng row count.

### Bài 12. Với threshold 50, scale factor 0.2 và 1 triệu rows, ngưỡng gần bao nhiêu?

**Đáp án:** 200.050 dead tuples.

### Bài 13. reltuples là số đếm tuyệt đối chính xác?

**Đáp án:** Không. Đây là estimate trong pg_class.

### Bài 14. reloptions có thể làm thay đổi threshold?

**Đáp án:** Có. Per-table options có thể override global settings.

### Bài 15. Insert-triggered vacuum hữu ích khi nào?

**Đáp án:** Với bảng insert-heavy/append-only ít dead tuples nhưng vẫn cần vacuum freeze.

### Bài 16. Autoanalyze trigger dùng gì?

**Đáp án:** Analyze threshold cộng analyze scale factor nhân reltuples theo cấu hình hiệu lực.

### Bài 17. Freeze trigger có giống dead tuple trigger?

**Đáp án:** Không. Anti-wraparound dựa trên XID/MultiXact age.

### Bài 18. Query nào cho biết lần autovacuum gần nhất?

**Đáp án:** Đọc cột last_autovacuum trong pg_stat_user_tables hoặc pg_stat_all_tables.

### Bài 19. last_autovacuum cho biết runtime không?

**Đáp án:** Không. Runtime cần progress view hoặc logs.

### Bài 20. Vì sao counters có thể trở về 0?

**Đáp án:** Statistics có thể bị reset bởi các hàm reset hoặc sự kiện quản trị.

### Bài 21. Có nên reset stats trước khi đo?

**Đáp án:** Chỉ trong lab/experiment có kiểm soát và phải ghi lại baseline; không reset production để che lịch sử.

### Bài 22. View theo dõi VACUUM đang chạy?

**Đáp án:** pg_stat_progress_vacuum.

### Bài 23. heap_blks_scanned là gì?

**Đáp án:** Số heap blocks đã được scan trong progress context.

### Bài 24. heap_blks_total là gì?

**Đáp án:** Tổng heap blocks được progress view báo cáo cho relation trong lần vacuum đó.

### Bài 25. Heap scan 100% nghĩa vacuum đã hoàn tất?

**Đáp án:** Không. Index cleanup, truncation và final cleanup có thể còn.

### Bài 26. num_dead_tuples có phải n_dead_tup không?

**Đáp án:** Không. Nó là số dead tuples đang giữ trong buffer của vacuum để xử lý.

### Bài 27. index_vacuum_count cho biết gì?

**Đáp án:** Số chu kỳ vacuum index đã diễn ra trong tiến trình đó.

### Bài 28. Vì sao một VACUUM có nhiều index cycles?

**Đáp án:** Dead tuple storage array có thể đầy, khiến vacuum phải cleanup indexes theo nhiều vòng.

### Bài 29. Không có row trong pg_stat_progress_vacuum nghĩa gì?

**Đáp án:** Không có VACUUM được hiển thị ngay thời điểm query; nó không chứng minh bảng không cần vacuum.

### Bài 30. View theo dõi autovacuum worker?

**Đáp án:** pg_stat_activity, kết hợp backend_type/query text và pg_stat_progress_vacuum.

### Bài 31. Wait event IO có thể nói gì?

**Đáp án:** Backend đang chờ I/O; cần đối chiếu storage metrics và phase.

### Bài 32. View theo dõi ANALYZE progress?

**Đáp án:** pg_stat_progress_analyze.

### Bài 33. VACUUM ANALYZE làm gì?

**Đáp án:** Yêu cầu cả vacuum cleanup/freezing và cập nhật planner statistics.

### Bài 34. Setting log autovacuum là gì?

**Đáp án:** log_autovacuum_min_duration.

### Bài 35. Giá trị 0 của log_autovacuum_min_duration nghĩa gì?

**Đáp án:** Ghi log mọi lần autovacuum/autoanalyze phù hợp setting này.

### Bài 36. pgstattuple khác pg_stat_user_tables thế nào?

**Đáp án:** pgstattuple đo vật lý chi tiết hơn; pg_stat_user_tables cung cấp estimates nhẹ cho monitoring.

### Bài 37. Vì sao pgstattuple có thể tốn I/O?

**Đáp án:** Nó scan relation để đo tuple/free-space information.

### Bài 38. pgstattuple_approx dùng gì để giảm scan?

**Đáp án:** Có thể tận dụng visibility map để ước lượng/skip pages trong điều kiện phù hợp.

### Bài 39. VACUUM thường có luôn làm file nhỏ đi?

**Đáp án:** Không. Nó thường đánh dấu space để reuse; chỉ truncate pages cuối heap khi điều kiện cho phép.

### Bài 40. VACUUM FULL khác VACUUM thường thế nào?

**Đáp án:** FULL rewrite relation, thu hồi space mạnh hơn và cần lock mạnh.

### Bài 41. Vì sao cần đo index size riêng?

**Đáp án:** Index cleanup và index bloat có lifecycle/cost khác heap dead tuples.

### Bài 42. Query nào đo total relation size?

```sql
SELECT pg_size_pretty(pg_total_relation_size('app.orders'::regclass));
```

**Đáp án:** pg_total_relation_size() bao gồm relation, indexes và TOAST liên quan.

### Bài 43. Partition parent có heap blocks như leaf partition không?

**Đáp án:** Thường không; cần theo dõi các leaf partitions chứa heap storage.

### Bài 44. Vì sao long transaction giữ dead tuples?

**Đáp án:** Snapshot cũ có thể vẫn cần các tuple versions trước đó.

### Bài 45. backend_xmin giúp điều tra gì?

**Đáp án:** Nó phản ánh xmin horizon mà backend đang giữ trong một số trạng thái; dùng để tìm snapshot cũ.

### Bài 46. Replication slot field nào có thể giữ vacuum horizon?

**Đáp án:** xmin và catalog_xmin; restart_lsn là WAL retention marker khác.

### Bài 47. Có nên drop inactive slot để VACUUM nhanh hơn?

**Đáp án:** Không tự động. Xác minh consumer, retention và recovery/resync plan trước.

### Bài 48. Autovacuum chạy liên tục có luôn là lỗi?

**Đáp án:** Không. Có thể workload ghi lớn hoặc threshold thấp có chủ đích; so runtime, interval, I/O và backlog.

### Bài 49. Tại sao bảng lớn có thể cần scale factor thấp hơn?

**Đáp án:** Scale factor cao tạo threshold tuyệt đối rất lớn, để dead tuples tích tụ quá nhiều trước trigger.

### Bài 50. Tăng autovacuum_max_workers có rủi ro gì?

**Đáp án:** Tăng I/O/CPU contention nếu storage/capacity không đủ.

### Bài 51. Vì sao không nên tắt autovacuum?

**Đáp án:** Có thể tích tụ dead tuples, stale statistics và nguy cơ wraparound.

### Bài 52. Sau VACUUM, size không đổi có nghĩa lệnh vô ích?

**Đáp án:** Không. Space có thể đã được đánh dấu để PostgreSQL tái sử dụng.

### Bài 53. Dead percentage thấp nhưng dead bytes lớn có thể xảy ra?

**Đáp án:** Có. Bảng rất lớn có thể có tỷ lệ thấp nhưng số bytes dead đáng kể.

### Bài 54. pg_stat_progress_vacuum có cho biết runtime không?

**Đáp án:** Không trực tiếp; join pg_stat_activity và tính từ query_start.

### Bài 55. Tại sao cần đọc logs sau khi vacuum kết thúc?

**Đáp án:** Progress view chỉ hiển thị tiến trình đang chạy; logs giữ chi tiết kết quả của lần đã kết thúc.

### Bài 56. Vì sao phải kiểm tra stats reset time?

**Đáp án:** Counters/timestamps có thể phản ánh khoảng thời gian từ lần reset chứ không phải toàn bộ lịch sử.

### Bài 57. VACUUM bị chặn bởi horizon thì tăng cost limit có đủ không?

**Đáp án:** Không. Cần xử lý transaction/slot/prepared transaction đang giữ horizon.

### Bài 58. Nên đo cadence như thế nào?

**Đáp án:** Lưu timestamps/runtime và write/dead tuple trends qua nhiều chu kỳ, rồi so interval với tốc độ phát sinh tuples.

### Bài 59. Alert dead tuples nên dựa trên một sample?

**Đáp án:** Không. Dùng nhiều mẫu, size, write rate và trend để tránh false positives do statistics lag.

### Bài 60. Lập checklist điều tra bảng có n_dead_tup tăng

**Đáp án gợi ý:**

1. Lấy n_live_tup, n_dead_tup, estimated percentage và relation size.
2. Xem last_autovacuum/last_vacuum, counters và statistics reset context.
3. Tính rough threshold từ global settings, reltuples và reloptions.
4. Xem pg_stat_progress_vacuum và phase/runtime.
5. Kiểm tra autovacuum worker waits trong pg_stat_activity.
6. Đọc log_autovacuum_min_duration/log VACUUM VERBOSE nếu có.
7. Tìm long transactions, idle-in-transaction, prepared transactions và slot xmin.
8. Nếu cần, đo vật lý bằng pgstattuple có chọn lọc.
9. Chọn tuning/action theo blocker, threshold, I/O và workload.
10. Đo lại dead estimates, timestamps, runtime và size trend sau hành động.

## 26. Checklist vận hành production

| Kiểm tra | Điều cần bảo đảm |
| --- | --- |
| n_live_tup/n_dead_tup | Theo dõi estimate và trend |
| Dead percentage | Gắn nhãn estimate |
| Heap/index/total size | Đo riêng |
| last_autovacuum | Theo dõi bảng quan trọng |
| last_vacuum | Phân biệt manual với auto |
| vacuum_count/autovacuum_count | Biết stats reset context |
| n_mod_since_analyze | Theo dõi planner statistics |
| Global autovacuum settings | Có baseline |
| Per-table reloptions | Được kiểm tra |
| Insert vacuum threshold | Xem với append-only tables |
| Freeze threshold | Giám sát riêng với dead tuple threshold |
| pg_stat_progress_vacuum | Theo dõi phase và blocks |
| pg_stat_activity | Worker runtime/wait events |
| pg_stat_progress_analyze | Theo dõi analyze khi cần |
| log_autovacuum_min_duration | Log phù hợp mục tiêu |
| pgstattuple | Chỉ dùng chẩn đoán có chọn lọc |
| Long transactions | Có alert/runbook |
| Idle in transaction | Có kiểm soát |
| Prepared transactions | Có owner/runbook |
| Replication slots | Theo dõi xmin/catalog_xmin/restart_lsn |
| Partition leaf tables | Được theo dõi riêng |
| TOAST/index size | Được tính vào tổng dung lượng |
| Autovacuum workers | Đủ capacity, không quá tải |
| Storage I/O | Có headroom |
| VACUUM runtime/interval | Có baseline theo relation |
| Dead tuple trend | Không chỉ snapshot |
| Disk free space | Đủ cho maintenance |
| Freeze age | Theo dõi wraparound riêng |
| Post-vacuum verification | Có đo trước/sau |
| Metrics retention | Đủ để xem xu hướng dài hạn |

## 27. Tổng kết

Đo dead tuples và tiến độ VACUUM là một quy trình quan sát nhiều lớp. pg_stat_user_tables cung cấp estimates và lịch sử; pg_stat_progress_vacuum cho biết tiến trình đang ở đâu; pg_stat_activity giúp hiểu worker và waits; logs giải thích kết quả sau khi hoàn tất; pgstattuple hỗ trợ đo vật lý khi thật sự cần.

Những nguyên tắc quan trọng:

1. **n_dead_tup là estimate.** Dùng nó để phát hiện xu hướng và ưu tiên điều tra.
2. **last_autovacuum và last_vacuum khác nhau.** Đừng gộp manual và automatic maintenance.
3. **Counters phụ thuộc statistics reset.** Giữ context khi phân tích lịch sử.
4. **Dead tuple threshold khác freeze threshold.** Append-only tables vẫn cần vacuum.
5. **Global settings có thể bị reloptions override.** Tính trigger chỉ là ước lượng nếu chưa xét per-table config.
6. **Progress phase quan trọng hơn một phần trăm đơn lẻ.** Heap scan 100% không có nghĩa index/final cleanup đã xong.
7. **num_dead_tuples trong progress view không phải table-wide dead count.**
8. **VACUUM thường giúp reuse space.** File không nhất thiết shrink trên filesystem.
9. **Heap, indexes và TOAST cần được nhìn riêng.** Một bảng có thể có index cost lớn dù heap nhỏ.
10. **Long transactions và replication slots giữ horizon.** Vacuum có thể chạy nhưng không reclaim được tuple mong muốn.
11. **Logs bổ sung cho statistics và progress views.** Chúng giữ runtime/result của các lần đã kết thúc.
12. **pgstattuple là công cụ chẩn đoán có cost.** Không polling full scan trên mọi relation lớn.
13. **Autovacuum capacity phải theo write rate.** Điều chỉnh workers/cost settings có đo lường.
14. **Alert theo trend và tác động.** Kết hợp dead bytes, size, runtime, cadence và freeze age.
15. **Luôn xác minh sau thay đổi.** Kiểm tra stats, logs, progress và size theo cùng phạm vi.

Mô hình điều tra ngắn:

```text
Dead tuple estimate tăng?
          |
          v
Bảng nào, lớn bao nhiêu, write rate?
          |
          v
Threshold đã đạt? reloptions có override?
          |
          v
Autovacuum đang chạy?
      +---+---+
      |       |
     Có      Không
      |       |
      v       v
Phase / wait  Worker slot / scheduling /
/ runtime     config / logs
      |       |
      +---+---+
          |
          v
Có horizon blocker không?
          |
          v
Đo lại stats + logs + size trend
          |
          v
Xác nhận vacuum đang theo kịp workload
```

**Câu hỏi review cuối cùng:** “Khi n_dead_tup tăng, chúng ta có thể xác định đó là estimate stale, vacuum chưa đạt threshold, worker đang chờ I/O, index cleanup còn chạy hay transaction cũ đang giữ horizon không? Sau khi VACUUM hoàn tất, chúng ta có bằng chứng rằng maintenance đã theo kịp workload thay vì chỉ thấy lệnh trả về thành công không?” Một dashboard tốt phải giúp trả lời được câu hỏi đó bằng metrics và timeline có thể kiểm chứng.

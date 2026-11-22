# Bảo trì chỉ mục, thống kê và dung lượng PostgreSQL theo lịch

Một PostgreSQL cluster có thể hoạt động ổn định trong ngày đầu nhưng chậm dần theo thời gian nếu indexes phình to, statistics không còn phản ánh dữ liệu, autovacuum không theo kịp hoặc dung lượng lưu trữ tăng nhanh hơn dự báo. Những vấn đề này thường không xuất hiện như một lỗi duy nhất; chúng tích lũy qua nhiều tuần hoặc nhiều tháng rồi trở thành query chậm, disk đầy, backup kéo dài hay replication bị gián đoạn.

Quản trị tốt cần một lịch bảo trì có mục tiêu, có số liệu trước/sau và có giới hạn an toàn. Lịch không có nghĩa chạy mọi lệnh vào một ngày cố định bất kể workload. Cần kết hợp các cơ chế tự động của PostgreSQL như autovacuum/autoanalyze với các tác vụ chủ động như kiểm tra index, refresh statistics, đánh giá dung lượng, xác minh backup và dọn dữ liệu theo retention policy.

Bài học này trình bày cách lập lịch bảo trì indexes, statistics và capacity; cách chọn công cụ, viết truy vấn quan sát, tổ chức maintenance window, quản lý rủi ro lock/I/O/WAL và thiết kế runbook có thể vận hành lặp lại.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt bảo trì index, VACUUM, ANALYZE và quản lý dung lượng.
2. Theo dõi kích thước table/index và phát hiện dấu hiệu index growth bất thường.
3. Đánh giá index usage mà không xóa index chỉ dựa trên một counter.
4. Chọn giữa REINDEX, REINDEX CONCURRENTLY, pg_repack và các phương án khác.
5. Duy trì planner statistics bằng autoanalyze và ANALYZE có mục tiêu.
6. Thiết kế lịch kiểm tra table/index statistics, dead tuples và transaction age.
7. Đo dung lượng database, relation, tablespace, WAL, temp files và backup.
8. Theo dõi tốc độ tăng trưởng, ước lượng thời điểm chạm ngưỡng và chuẩn bị capacity.
9. Tổ chức maintenance window có lock timeout, statement timeout và rollback plan.
10. Lập lịch bằng OS scheduler hoặc pg_cron theo quyền và phiên bản.
11. Ghi log, tránh chạy trùng job và xử lý lỗi có thể retry an toàn.
12. Xây dashboard, alerts, runbook và chu kỳ review phù hợp production.

## 2. Vì sao cần bảo trì theo lịch?

### 2.1. Bảo trì là một chu trình vận hành

Một chu trình hữu ích gồm:

1. **Observe:** thu thập kích thước, statistics, query latency, index usage, dead tuples và storage headroom.
2. **Diagnose:** xác định nguyên nhân bằng dữ liệu; phân biệt bloat, stale stats, query regression và thiếu capacity.
3. **Plan:** chọn hành động, thời điểm, tài nguyên, lock impact và người chịu trách nhiệm.
4. **Execute:** chạy trong giới hạn đã định, theo dõi progress và workload.
5. **Verify:** kiểm tra kết quả, dữ liệu, query plans, disk, replication và backup.
6. **Learn:** cập nhật baseline, lịch và runbook.

### 2.2. Không phải mọi tác vụ đều cần chạy hàng ngày

Autovacuum/autoanalyze thường hoạt động liên tục theo thresholds. Kiểm tra capacity có thể chạy mỗi ngày. Index health review có thể hàng tuần/tháng tùy workload. REINDEX chỉ nên chạy khi có lý do. Chạy VACUUM FULL hoặc REINDEX toàn database theo lịch cứng có thể gây lock, I/O spike và WAL burst không cần thiết.

### 2.3. Tách bảo trì tự động và bảo trì có quyết định

| Nhóm | Ví dụ | Cách vận hành |
| --- | --- | --- |
| Tự động thường xuyên | autovacuum, autoanalyze, monitoring | PostgreSQL tự kích hoạt theo activity/config |
| Kiểm tra định kỳ | capacity snapshot, index usage, table stats | Scheduled query/collector |
| Bảo trì có điều kiện | ANALYZE table, REINDEX một index | Chạy khi metrics cho thấy cần |
| Bảo trì có change window | VACUUM FULL, pg_repack, bulk rewrite | Plan, approval, resource/rollback controls |
| Khôi phục | restore backup, PITR | Runbook incident/DR, không phải routine cleanup |

### 2.4. Lịch phải dựa trên workload

Table append-only, table cập nhật liên tục, partitioned table, lookup table và archive table có đặc tính khác nhau. Chọn frequency theo write rate, query sensitivity, size, business criticality và khả năng chịu lock/downtime.

## 3. Index maintenance: khái niệm và tín hiệu

### 3.1. Index giúp gì?

Index giúp planner tìm rows mà không phải scan toàn table trong một số query patterns. Index cũng có chi phí: disk space, WAL, write amplification, vacuum work và cache pressure. Mỗi index cần có workload justification.

### 3.2. Index growth

Index có thể tăng kích thước theo insert/update/delete, page splits, churn và phân bố key. Với B-tree, page utilization và fragmentation có thể ảnh hưởng hiệu quả lưu trữ/cache. Kích thước lớn không tự chứng minh index bị bloat; một index lớn có thể phản ánh dữ liệu thực sự lớn.

### 3.3. Bloat là gì?

Bloat là phần không gian đã cấp phát nhưng không được sử dụng hiệu quả do tuple churn, page splits, free space hoặc lịch sử thay đổi. Bloat không thể được xác định chính xác chỉ bằng cách so sánh `pg_relation_size()` với row count.

### 3.4. Index usage

`pg_stat_user_indexes` cung cấp counters như `idx_scan`, `idx_tup_read`, `idx_tup_fetch`. Đây là số liệu tích lũy kể từ khi statistics được reset, không phải mức sử dụng vĩnh viễn. Sau restart/reset, counters có thể thấp lại.

### 3.5. Không drop index chỉ vì idx_scan bằng zero

Một index có thể phục vụ query hiếm, constraint enforcement, primary key/unique constraint, foreign key workload hoặc seasonal reports. Trước khi cân nhắc drop:

- Quan sát đủ một chu kỳ nghiệp vụ;
- Xác minh index có backing constraint không;
- Kiểm tra query plans và query logs;
- Xem workload theo mùa;
- Xác định index có được planner chọn hay không;
- Đánh giá chi phí recreate và rủi ro.

### 3.6. Index invalid

Một concurrent index build bị lỗi/cancel có thể để lại index invalid. Index invalid không được planner dùng như index hợp lệ, nhưng vẫn chiếm storage và có thể còn overhead tùy trạng thái. Đưa việc phát hiện invalid indexes vào scheduled inventory.

### 3.7. Index health không chỉ là size

Đánh giá đồng thời:

- Size và growth rate;
- Scan/read/fetch counters;
- Constraint dependencies;
- Query plans và latency;
- B-tree page statistics nếu có extension phù hợp;
- Corruption checks;
- Write amplification và WAL volume.

## 4. Inventory kích thước table và index

### 4.1. Kích thước relation

Các hàm thường dùng:

| Hàm | Phạm vi |
| --- | --- |
| `pg_relation_size(relation)` | Kích thước một fork của relation, mặc định main fork |
| `pg_table_size(relation)` | Table storage, gồm TOAST và auxiliary forks, không gồm indexes |
| `pg_indexes_size(relation)` | Tổng kích thước indexes của table |
| `pg_total_relation_size(relation)` | Table + indexes + TOAST/auxiliary storage |
| `pg_database_size(database)` | Tổng kích thước database |
| `pg_tablespace_size(tablespace)` | Dung lượng relation trong tablespace |
| `pg_size_pretty(bytes)` | Format số bytes dễ đọc |

### 4.2. Top tables theo dung lượng

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    pg_size_pretty(pg_table_size(relid)) AS table_size,
    pg_size_pretty(pg_indexes_size(relid)) AS indexes_size,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
    pg_total_relation_size(relid) AS total_bytes
FROM pg_catalog.pg_statio_user_tables
ORDER BY total_bytes DESC
LIMIT 30;
~~~

`pg_total_relation_size` bao gồm cả indexes và TOAST. Dùng bytes cho sort/threshold; `pg_size_pretty` chỉ dành cho display.

### 4.3. Top indexes theo kích thước

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    indexrelname AS index_name,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch,
    pg_relation_size(indexrelid) AS index_bytes,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
ORDER BY index_bytes DESC
LIMIT 50;
~~~

### 4.4. Table và index size cùng một dòng

~~~sql
SELECT
    s.schemaname,
    s.relname AS table_name,
    pg_relation_size(s.relid) AS heap_bytes,
    pg_indexes_size(s.relid) AS index_bytes,
    pg_total_relation_size(s.relid) AS total_bytes,
    s.n_live_tup,
    s.n_dead_tup,
    s.last_vacuum,
    s.last_autovacuum,
    s.last_analyze,
    s.last_autoanalyze
FROM pg_stat_user_tables AS s
ORDER BY total_bytes DESC
LIMIT 100;
~~~

### 4.5. Dung lượng database

~~~sql
SELECT
    datname,
    pg_database_size(datname) AS bytes,
    pg_size_pretty(pg_database_size(datname)) AS size
FROM pg_database
ORDER BY bytes DESC;
~~~

### 4.6. Dung lượng tablespace

~~~sql
SELECT
    spcname,
    pg_tablespace_size(oid) AS bytes,
    pg_size_pretty(pg_tablespace_size(oid)) AS size
FROM pg_tablespace
ORDER BY bytes DESC;
~~~

### 4.7. Kích thước index theo schema

~~~sql
SELECT
    schemaname,
    sum(pg_relation_size(indexrelid)) AS index_bytes,
    pg_size_pretty(sum(pg_relation_size(indexrelid))) AS index_size,
    count(*) AS index_count
FROM pg_stat_user_indexes
GROUP BY schemaname
ORDER BY index_bytes DESC;
~~~

### 4.8. Kích thước logic khác dung lượng filesystem

Các hàm size báo bytes đã cấp phát cho PostgreSQL relations trong database/tablespace. Chúng không cho biết free space trên filesystem, snapshot reserve, filesystem metadata, WAL nằm ở volume khác hoặc dung lượng object storage. Capacity dashboard phải kết hợp metrics của OS/cloud storage.

### 4.9. Quyền và phạm vi

Các size functions có thể đọc relation/database metadata theo quyền; một số system-wide views cần quyền monitoring. Khi query inventory nhiều databases, chạy kết nối vào từng database vì `pg_stat_user_tables`/`pg_stat_user_indexes` là per-database views.

## 5. Thu thập index health và bloat evidence

### 5.1. Index usage counters

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    indexrelname AS index_name,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch,
    last_idx_scan,
    pg_relation_size(indexrelid) AS index_bytes
FROM pg_stat_user_indexes
ORDER BY index_bytes DESC;
~~~

`last_idx_scan` chỉ có trên một số major versions mới. Bỏ cột này nếu server chưa hỗ trợ.

### 5.2. Indexes không được scan

~~~sql
SELECT
    s.schemaname,
    s.relname AS table_name,
    s.indexrelname AS index_name,
    s.idx_scan,
    pg_size_pretty(pg_relation_size(s.indexrelid)) AS index_size,
    i.indisprimary,
    i.indisunique,
    i.indisvalid
FROM pg_stat_user_indexes AS s
JOIN pg_index AS i ON i.indexrelid = s.indexrelid
WHERE s.idx_scan = 0
ORDER BY pg_relation_size(s.indexrelid) DESC;
~~~

Đây là danh sách cần review, không phải danh sách tự động xóa. `idx_scan` có thể bằng zero vì stats vừa reset, workload chưa chạy hoặc index được dùng bởi constraint/operation hiếm.

### 5.3. Index invalid

~~~sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    i.indisready,
    i.indisvalid,
    i.indislive,
    pg_size_pretty(pg_relation_size(idx.oid)) AS index_size
FROM pg_index AS i
JOIN pg_class AS idx ON idx.oid = i.indexrelid
JOIN pg_class AS tbl ON tbl.oid = i.indrelid
JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
WHERE NOT i.indisvalid
ORDER BY ns.nspname, tbl.relname, idx.relname;
~~~

### 5.4. Ước lượng bloat không phải phép đo tuyệt đối

Các query bloat dựa trên page fill assumptions, tuple widths và catalog statistics chỉ là estimates. Chúng có thể sai khi data distribution lệch, TOAST lớn, fillfactor tùy chỉnh hoặc statistics stale. Dùng estimate để ưu tiên điều tra, không dùng làm trigger destructive action duy nhất.

### 5.5. pgstattuple extension

Extension `pgstattuple` cung cấp functions để đọc tuple/page statistics của relation, gồm live/dead tuple length và free space. Với B-tree có `pgstatindex()` để quan sát leaf density, fragmentation và page counts. Đây là các phép kiểm tra có thể đọc nhiều pages, nên chạy theo lịch/thời điểm phù hợp.

Ví dụ trong database lab:

~~~sql
CREATE EXTENSION IF NOT EXISTS pgstattuple;

SELECT *
FROM pgstattuple('public.orders'::regclass);

SELECT *
FROM pgstatindex('public.orders_created_at_idx'::regclass);
~~~

Việc cài extension cần quyền phù hợp và package tương ứng trên server. Không chạy full relation scan quá thường xuyên trên bảng rất lớn trong giờ peak.

### 5.6. amcheck

Extension/module `amcheck` cung cấp kiểm tra cấu trúc index như B-tree invariants. `bt_index_check()` và `bt_index_parent_check()` có chi phí/locking khác nhau; chọn chế độ phù hợp, xem tài liệu version và chạy theo risk-based schedule.

~~~sql
CREATE EXTENSION IF NOT EXISTS amcheck;

SELECT bt_index_check('public.orders_pkey'::regclass);
~~~

Không nhầm integrity check với bloat measurement. Index có thể lớn nhưng hợp lệ; index có thể nhỏ nhưng corrupt.

### 5.7. Khi nào cần REINDEX?

Xem xét REINDEX khi:

- Bloat đã được xác nhận và gây chi phí đáng kể;
- Index corruption được xác nhận và cần rebuild;
- Collation version thay đổi làm ordering/indexes cần rebuild;
- Một index invalid cần được tạo lại;
- Có evidence hiệu năng/space rõ ràng và phương án thay thế đã được thử.

Không REINDEX chỉ vì index vượt một size cố định.

## 6. Lựa chọn phương án bảo trì index

### 6.1. REINDEX

`REINDEX` rebuilds index từ dữ liệu table, có thể tạo lại cấu trúc index và loại bỏ bloat/corruption tùy nguyên nhân. REINDEX thường cần lock mạnh hơn và có thể chặn writes vào relation trong một phần đáng kể của operation.

~~~sql
REINDEX INDEX public.orders_created_at_idx;
REINDEX TABLE public.orders;
~~~

Chạy trong maintenance window khi mức blocking chấp nhận được. Đảm bảo disk headroom cho index mới và WAL, đặc biệt nếu database có replication/archiving.

### 6.2. REINDEX CONCURRENTLY

`REINDEX CONCURRENTLY` giảm blocking đối với concurrent reads/writes nhưng thực hiện nhiều phase, dùng thêm disk và có thể mất lâu hơn. Nó không thể chạy bên trong transaction block.

~~~sql
REINDEX INDEX CONCURRENTLY public.orders_created_at_idx;
~~~

Theo dõi `pg_stat_progress_create_index`, lock waits, temporary storage, WAL và replication lag. Kiểm tra version support và giới hạn với partitioned indexes trước khi lập lịch.

### 6.3. REINDEX DATABASE

`REINDEX DATABASE` có thể tạo workload lớn và lock nhiều relations. Tránh chạy như routine toàn database nếu chỉ một số indexes có evidence cần rebuild. Lập danh sách target, chạy tuần tự hoặc theo batch đã đo capacity.

### 6.4. pg_repack

`pg_repack` là extension/tool bên ngoài PostgreSQL core giúp reorganize table/index với mức blocking thấp trong phần lớn quá trình bằng cách copy và đồng bộ changes, sau đó swap trong một bước ngắn. Nó cần extension/binary tương thích, quyền và disk headroom; có thể tạo WAL và load lớn.

Không coi pg_repack là zero-lock hoặc không rủi ro. Kiểm tra version compatibility, primary key/unique key requirements cho table, long transactions, replication lag và quy trình abort/retry.

### 6.5. VACUUM và REINDEX không thay thế nhau

VACUUM xử lý dead tuples và khả năng tái sử dụng space; REINDEX tạo lại index structure. VACUUM thường có thể dọn index entries nhưng không luôn trả filesystem space. REINDEX có thể giải phóng bloat index sau khi swap/cleanup nhưng không thay VACUUM cho heap.

### 6.6. VACUUM FULL

`VACUUM FULL` viết lại table để trả space cho filesystem nhưng cần `ACCESS EXCLUSIVE` lock và dung lượng tạm đủ cho rewrite. Nó không phải routine index maintenance và thường gây downtime/lock impact đáng kể.

### 6.7. CLUSTER

`CLUSTER` sắp xếp lại table theo index, có thể cải thiện locality cho workload phù hợp nhưng viết lại relation, cần lock mạnh và tạo I/O/WAL lớn. Chỉ chạy khi có evidence query benefit và maintenance window.

### 6.8. Chọn action theo evidence

| Quan sát | Hành động có thể cân nhắc |
| --- | --- |
| Planner estimates stale | ANALYZE |
| Dead tuples tăng, autovacuum lag | Điều chỉnh autovacuum/VACUUM |
| Index bloat được xác nhận | REINDEX/pg_repack theo lock budget |
| Index invalid | Điều tra build failure, drop/rebuild an toàn |
| Index corruption | Restore/REINDEX theo hướng dẫn corruption response |
| Table cần trả space cho filesystem | Đánh giá VACUUM FULL/pg_repack |
| Query plan không dùng index | Kiểm tra statistics, predicate, operator class và workload |

## 7. Statistics maintenance

### 7.1. Planner statistics

PostgreSQL planner dùng statistics để ước lượng số rows, phân bố giá trị, distinct values, most common values và selectivity. Statistics stale có thể khiến planner chọn join order, scan type hoặc join method không phù hợp.

### 7.2. ANALYZE

`ANALYZE` lấy sample từ table và cập nhật catalog statistics. PostgreSQL thường tự chạy autoanalyze sau khi table thay đổi đủ nhiều; DBA có thể chạy chủ động sau bulk load, major data distribution changes hoặc khi query plan regressions cho thấy stats stale.

~~~sql
ANALYZE public.orders;
ANALYZE (VERBOSE) public.orders;
ANALYZE public.orders (customer_id, created_at, status);
~~~

ANALYZE không rewrite table và thường ít blocking hơn DDL, nhưng vẫn đọc pages/tiêu thụ I/O và có thể ảnh hưởng workload.

### 7.3. VACUUM (ANALYZE)

~~~sql
VACUUM (ANALYZE, VERBOSE) public.orders;
~~~

Kết hợp VACUUM và ANALYZE khi cả dead tuple cleanup lẫn planner stats đều cần. Không chạy ANALYZE sau mỗi transaction; dựa trên workload/thresholds.

### 7.4. Theo dõi analyze counters

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze,
    analyze_count,
    autoanalyze_count
FROM pg_stat_user_tables
ORDER BY n_mod_since_analyze DESC
LIMIT 50;
~~~

`n_mod_since_analyze` là estimate/counter thay đổi kể từ lần analyze gần nhất trên các versions hỗ trợ. Cột/cách reset có thể thay đổi; kiểm tra catalog của major version.

### 7.5. Autoanalyze thresholds

Autoanalyze được kích hoạt dựa trên số modifications và thresholds/scale factors, không phải lịch cố định. Các settings gồm `autovacuum_analyze_threshold`, `autovacuum_analyze_scale_factor` và per-table storage parameters.

Với table rất lớn, scale factor mặc định có thể khiến autoanalyze chờ tới khi có nhiều rows thay đổi. Có thể đặt per-table threshold/scale factor phù hợp thay vì hạ global threshold quá thấp.

~~~sql
ALTER TABLE public.orders
SET (autovacuum_analyze_scale_factor = 0.02);
~~~

Ví dụ chỉ minh họa per-table tuning; chọn giá trị từ modification rate và planner sensitivity.

### 7.6. Statistics target

`default_statistics_target` quyết định mức chi tiết mặc định cho statistics. Có thể đặt target cao hơn cho cột skewed/quan trọng, nhưng tăng target làm ANALYZE tốn thêm sample/work và tăng catalog size.

~~~sql
ALTER TABLE public.orders
ALTER COLUMN status SET STATISTICS 500;

ANALYZE public.orders (status);
~~~

Không tăng target toàn database khi chỉ một số columns cần độ chi tiết cao.

### 7.7. Extended statistics

Khi các columns có tương quan, statistics đơn lẻ có thể khiến planner ước lượng sai. Extended statistics hỗ trợ dependencies, ndistinct và most-common-values cho các nhóm cột.

~~~sql
CREATE STATISTICS orders_customer_status_stats
    (dependencies, ndistinct, mcv)
ON customer_id, status
FROM public.orders;

ANALYZE public.orders;
~~~

Chọn loại statistics dựa trên query predicates/grouping. Extended statistics không thay mọi loại multi-column estimation và cần ANALYZE để cập nhật.

### 7.8. Bulk load và statistics

Sau bulk load/import lớn, ANALYZE table affected giúp planner cập nhật row distribution. Nếu table partitioned, xem version và cách analyze parent/partitions để bảo đảm planner có statistics cần thiết.

### 7.9. Statistics sau partition maintenance

Khi attach/detach/drop partitions, bulk load partition mới hoặc thay đổi distribution, lập lịch ANALYZE trên parent/partition liên quan. Kiểm tra planner estimates trên các queries quan trọng sau khi thay đổi.

### 7.10. Không reset statistics để “làm sạch” dashboard

Reset counters làm mất baseline và khiến index usage/maintenance counters khó diễn giải. Nếu cần chu kỳ đo, lưu snapshot trước khi reset và ghi rõ reset timestamp. Không reset stats chỉ để làm số liệu đẹp.

## 8. VACUUM và autovacuum trong lịch bảo trì

### 8.1. Autovacuum là cơ chế mặc định cần được giữ hoạt động

Autovacuum cleanup dead tuples và freeze tuples để hạn chế table/index bloat và transaction ID wraparound. Autoanalyze cập nhật planner statistics. Lịch DBA nên quan sát và điều chỉnh cơ chế này, không thay thế nó bằng một lệnh VACUUM tổng quát chạy mỗi đêm.

### 8.2. Theo dõi dead tuples và vacuum history

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    round(
        100.0 * n_dead_tup /
        NULLIF(n_live_tup + n_dead_tup, 0),
        2
    ) AS estimated_dead_pct,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 50;
~~~

Tỷ lệ này là estimate dựa trên statistics, không phải page-level bloat. Dùng nó để chọn table cần điều tra.

### 8.3. Autovacuum per-table tuning

~~~sql
ALTER TABLE public.events
SET (
    autovacuum_vacuum_scale_factor = 0.02,
    autovacuum_vacuum_threshold = 5000,
    autovacuum_analyze_scale_factor = 0.01,
    autovacuum_analyze_threshold = 2000
);
~~~

Ví dụ này minh họa cách đặt threshold/scale factor. Với bảng rất lớn hoặc write-heavy, giá trị cần được tính theo row churn, vacuum duration, storage và RPO. Không sao chép trực tiếp vào mọi table.

### 8.4. Autovacuum capacity

Các settings cần hiểu:

- `autovacuum_max_workers`: số worker autovacuum đồng thời;
- `autovacuum_naptime`: khoảng nghỉ giữa các lần launcher kiểm tra;
- `autovacuum_vacuum_cost_limit` và `autovacuum_vacuum_cost_delay`: throttling;
- `maintenance_work_mem`/`autovacuum_work_mem`: memory cho maintenance;
- Per-table vacuum/analyze thresholds và scale factors.

Tăng workers có thể giúp catch up nhưng cũng tăng I/O/CPU. Điều chỉnh dựa trên quan sát throughput và user latency.

### 8.5. Freeze và wraparound

Transaction ID wraparound là rủi ro availability nghiêm trọng. Đưa `age(datfrozenxid)` vào daily monitoring và ưu tiên anti-wraparound vacuum khi cảnh báo. Không trì hoãn freeze work để chạy index maintenance không cấp thiết.

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;
~~~

### 8.6. Long transactions và replication slots

Transaction snapshots lâu hoặc replication slots giữ xmin có thể ngăn vacuum reclaim tuples. Đưa transaction age, `backend_xmin`, `xmin` của replication slots và retained WAL vào daily checks.

### 8.7. VACUUM VERBOSE và logs

Trong maintenance window, `VACUUM (VERBOSE)` giúp hiểu pages/tuples đã xử lý. Với autovacuum, cấu hình logging phù hợp (ví dụ `log_autovacuum_min_duration`) để phát hiện operation lâu, skipped pages và worker behavior.

### 8.8. VACUUM không trả hết disk space

VACUUM thường đánh dấu space có thể tái sử dụng bên trong relation; filesystem file size thường không giảm. Để trả space cho OS cần rewrite/compaction strategy như VACUUM FULL hoặc pg_repack với lock/capacity planning.

## 9. Capacity management: inventory và growth

### 9.1. Capacity không chỉ là database size

Capacity planning phải theo dõi các lớp:

- Heap tables và TOAST;
- Indexes;
- Tablespaces/filesystems;
- WAL directory và archive staging;
- Temporary files;
- Backup repositories/snapshots;
- Replication slot retained WAL;
- Logs, audit files và monitoring data;
- Free space cần cho maintenance/rewrite/restore.

### 9.2. Database size snapshot

Chạy query định kỳ và lưu kết quả cùng timestamp:

~~~sql
SELECT
    now() AS collected_at,
    datname,
    pg_database_size(datname) AS database_bytes
FROM pg_database
WHERE datallowconn
ORDER BY datname;
~~~

Chạy trên từng cluster và giữ cluster identity/version/region để so sánh đúng nguồn.

### 9.3. Relation size snapshot

~~~sql
SELECT
    now() AS collected_at,
    current_database() AS database_name,
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.relkind,
    pg_relation_size(c.oid) AS main_bytes,
    pg_total_relation_size(c.oid) AS total_bytes
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm', 'i', 't')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY total_bytes DESC;
~~~

Đối với partitioned tables, parent relation không chứa toàn bộ dữ liệu partitions như một ordinary heap. Inventory cần tính leaf partitions để không báo thiếu dung lượng.

### 9.4. Tablespace usage

`pg_tablespace_size()` cho biết bytes được dùng trong tablespace. Nó không cho biết free bytes của volume. Thu thập thêm filesystem/cloud volume capacity, free space, quota và IOPS/throughput.

### 9.5. WAL capacity

WAL có thể tăng do bulk load, index build, replication slots, archive failures hoặc standby lag. Theo dõi:

- Kích thước `pg_wal` trên filesystem;
- `max_wal_size` và checkpoint activity;
- Replication slots giữ WAL;
- Archive backlog/failure;
- WAL generation rate;
- Disk free headroom.

### 9.6. Replication slot retained WAL

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    CASE
        WHEN restart_lsn IS NULL THEN NULL
        ELSE pg_size_pretty(
            pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint
        )
    END AS retained_wal_estimate
FROM pg_replication_slots
ORDER BY slot_name;
~~~

Query này ước lượng khoảng WAL từ current LSN tới restart LSN; không phải phép đo chính xác bytes đang chiếm trên filesystem vì segment boundaries, archive và WAL recycling cũng ảnh hưởng. Các cột phụ thuộc slot type/version.

### 9.7. Temporary files

~~~sql
SELECT
    datname,
    temp_files,
    temp_bytes,
    stats_reset
FROM pg_stat_database
ORDER BY temp_bytes DESC;
~~~

Temp bytes là counters tích lũy, không phải lượng temp file hiện đang tồn tại. Kết hợp `log_temp_files`, query plans, `work_mem` và filesystem monitoring để tìm sort/hash spills.

### 9.8. Backup repository capacity

Theo dõi:

- Full/base backup size;
- Incremental backup chain size;
- WAL archive bytes;
- Retention count/age;
- Immutable object versions;
- Failed/partial backups;
- Object storage quota/requests/egress;
- Restore staging capacity.

Retention policy phải hiểu dependencies của incremental chain và WAL. Không xóa backup/WAL chỉ theo file age nếu nó còn cần cho recovery chain.

### 9.9. Capacity headroom

Giữ headroom cho normal growth, burst workload và maintenance. REINDEX/pg_repack/VACUUM FULL có thể cần additional space tạm thời. Restore drill cũng cần staging space đủ để phục hồi backup.

Không đợi volume đạt 95% mới đặt kế hoạch mở rộng. Dùng warning/critical thresholds dựa trên growth rate và thời gian provisioning.

## 10. Growth rate và forecasting

### 10.1. Growth theo hai snapshots

Với hai snapshots:

\[
\text{Growth rate} =
\frac{\text{Size}_{new}-\text{Size}_{old}}{\Delta t}
\]

Ví dụ database tăng 120 GB trong 30 ngày thì average growth xấp xỉ 4 GB/ngày. Dùng bytes và thời gian thực, không trừ các giá trị đã format bằng `pg_size_pretty`.

### 10.2. Forecast thời điểm chạm ngưỡng

\[
\text{Days to threshold} =
\frac{\text{Capacity}-\text{Current usage}-\text{Reserve}}
{\text{Average daily growth}}
\]

Đây là linear estimate. Workload có seasonality, batch cycles, retention expiry và data spikes nên cần nhiều cửa sổ đo và scenario planning.

### 10.3. Growth theo relation

Lưu snapshot per relation giúp thấy table/index nào tăng nhanh nhất. Khi relation được rename/drop/partition rotate, dùng OID + database identity và ghi lifecycle events để nối lịch sử chính xác.

### 10.4. Tách data growth và bloat growth

Database size tăng có thể do business data, index growth, dead space, TOAST, WAL hoặc backup retention. Phân tích component trước khi kết luận cần tăng storage hay cần reorganization.

### 10.5. Partitioning và retention

Với time-series/event data, partitioning có thể giúp retention bằng cách detach/drop old partitions thay vì DELETE hàng triệu rows. Lập lịch partition creation, attach/detach, analyze và backup policy. Drop partition là thao tác destructive; kiểm tra legal/retention policy và backup requirements trước.

### 10.6. Compression và archival

Đưa dữ liệu cũ sang archive/warehouse hoặc nén theo format phù hợp có thể giảm primary storage, nhưng cần xác định query access, restore latency, encryption và retention. Không coi archive là bản backup duy nhất.

### 10.7. Capacity review

Mỗi kỳ review cần trả lời:

- Growth rate theo database/table/index;
- Thời điểm chạm warning/critical threshold;
- Volume/quota cần mở rộng;
- WAL/backup retention có hợp lý không;
- Partition retention có chạy đúng không;
- Maintenance/rebuild có đủ temporary space không;
- DR region có đủ capacity để nhận workload không.

## 11. Lập lịch maintenance

### 11.1. Lịch mẫu theo nhóm công việc

Lịch dưới đây là điểm khởi đầu để điều chỉnh theo workload; không phải tần suất bắt buộc:

| Tần suất tham khảo | Công việc | Mục đích |
| --- | --- | --- |
| Liên tục | autovacuum/autoanalyze, replication/archive monitoring | Cleanup và statistics theo activity |
| Mỗi 5–15 phút | capacity/lag/backup health metrics | Phát hiện sớm pressure |
| Hàng ngày | database/table growth snapshot, xid age, slot/WAL review | Theo dõi trend và risk |
| Hàng tuần | index usage/invalid index review, long transaction review | Phát hiện index/transaction issues |
| Hàng tháng | bloat sampling, index integrity checks theo risk, capacity forecast | Đánh giá maintenance có điều kiện |
| Theo change/bulk load | ANALYZE affected tables, verify plans | Cập nhật statistics sau thay đổi |
| Theo incident/restore drill | backup verification và restore test | Chứng minh recoverability |
| Theo nhu cầu | REINDEX/pg_repack/CLUSTER/VACUUM FULL | Xử lý vấn đề đã xác nhận |

### 11.2. Chọn maintenance window

Chọn giờ có workload thấp nhưng vẫn có on-call và business coverage. Xem batch jobs, reporting windows, replication/backup windows, cloud maintenance và timezone. Không xếp nhiều tác vụ I/O nặng cùng lúc.

### 11.3. Thứ tự tác vụ

Một chuỗi có thể là:

1. Capture baseline/capacity;
2. Kiểm tra replication/archive/backup health;
3. Chạy ANALYZE hoặc VACUUM có mục tiêu nếu cần;
4. Chạy index operation theo batch;
5. Xác minh query plans/integrity;
6. Capture metrics sau bảo trì;
7. Ghi kết quả và follow-up.

Nếu freeze/wraparound risk, xử lý ưu tiên trước các tác vụ tối ưu index không khẩn cấp.

### 11.4. Job duration budget

Đặt expected duration, hard timeout, lock timeout và stop conditions. Nếu job vượt budget, xác định đang tiến triển hay bị block trước khi quyết định cancel. Không tự động kill tất cả operations khi hết maintenance window nếu cancellation có thể gây rollback lâu.

### 11.5. Job dependencies

Không chạy REINDEX khi volume không còn đủ space; không chạy backup nặng cùng lúc với storage migration; không chạy nhiều bulk COPY/index builds khi standby/archive đang lag. Dùng scheduler/orchestrator dependencies để tránh cạnh tranh.

### 11.6. Idempotency

Inventory query có thể chạy lặp an toàn. DDL/maintenance action cần xác định trạng thái trước khi chạy và ghi kết quả. Không retry mù lệnh đã timeout nếu không biết server đã hoàn tất hay chưa.

### 11.7. Không chạy trùng job

Dùng scheduler concurrency policy, OS lock (ví dụ `flock` trên Linux) hoặc PostgreSQL advisory lock để chỉ cho phép một instance của job. Nếu dùng advisory lock, giữ cùng session connection trong suốt thời gian operation; lock session không còn hiệu lực khi connection kết thúc.

### 11.8. Thời gian và timezone

Lưu lịch theo timezone đã thống nhất; server, scheduler và monitoring có thể dùng timezone khác nhau. Dùng UTC cho event timestamps/log correlation và hiển thị local time rõ trong runbook.

### 11.9. Maintenance window thay đổi

Khi workload peak, business schedule hoặc SLA thay đổi, review lại window. Không giữ lịch cũ chỉ vì job đã chạy ổn trong nhiều tháng.

## 12. Lập lịch bằng pg_cron hoặc OS scheduler

### 12.1. Chọn scheduler

| Cơ chế | Phù hợp khi | Điểm cần quản lý |
| --- | --- | --- |
| OS cron/systemd timer | Job cần chạy script, psql, filesystem/cloud CLI | OS identity, credentials, logs, retries |
| pg_cron | Job SQL chạy trong PostgreSQL | Extension availability, database scope, role, job history |
| Orchestrator bên ngoài | Workflow nhiều bước/phụ thuộc nhiều hệ thống | Concurrency, secrets, retry, alerting, audit |
| Managed service scheduler | Database service cung cấp automation | Provider limits, permissions và behavior |

Không cài scheduler mới chỉ để chạy một query đơn giản nếu platform đã có job orchestration phù hợp.

### 12.2. pg_cron

`pg_cron` là extension scheduler chạy SQL theo cron syntax. Cần cài package/extension theo PostgreSQL major version, cấu hình preload nếu yêu cầu, cấp quyền và kiểm tra database nơi job sẽ chạy.

Ví dụ schedule ANALYZE mỗi đêm:

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_cron;

SELECT cron.schedule(
    'nightly-analyze-orders',
    '15 2 * * *',
    'ANALYZE public.orders'
);
~~~

Ví dụ schedule inventory query hoặc function bảo trì:

~~~sql
SELECT cron.schedule(
    'daily-capacity-snapshot',
    '10 1 * * *',
    'SELECT ops.capture_capacity_snapshot()'
);
~~~

Function ví dụ phải được tạo trước, có schema/permissions rõ và ghi nhận kết quả. Không schedule REINDEX, VACUUM FULL hay destructive DDL trên toàn database chỉ vì cron có thể chạy được.

### 12.3. Job trong database khác

Một số phiên bản pg_cron hỗ trợ `cron.schedule_in_database()` để chỉ định database đích. Kiểm tra extension version và documentation đang cài; không giả định mọi cluster có cùng API.

### 12.4. Quản lý job

Xem jobs và run history qua các catalog views của pg_cron như `cron.job` và `cron.job_run_details` trên các phiên bản hỗ trợ. Theo dõi status, return message, start/end time và duration; lưu retention log phù hợp.

### 12.5. OS cron/systemd với psql

Ví dụ chạy ANALYZE qua psql:

~~~bash
psql "service=prod-maintenance dbname=appdb" \
  -X -v ON_ERROR_STOP=1 \
  -c "ANALYZE public.orders"
~~~

`service=prod-maintenance` tham chiếu service definition trong libpq service file; credentials nên dùng `.pgpass` hoặc secret manager với file permissions chặt. Tránh password literal trong command line, script hoặc crontab.

### 12.6. Nhiều lệnh trong cùng session

Có thể dùng nhiều `-c` options để gửi lệnh theo thứ tự trong cùng psql session:

~~~bash
psql "service=prod-maintenance dbname=appdb" \
  -X -v ON_ERROR_STOP=1 \
  -c "SET lock_timeout = '5s'" \
  -c "SET statement_timeout = '45min'" \
  -c "REINDEX INDEX CONCURRENTLY public.orders_created_at_idx"
~~~

Lưu ý `REINDEX CONCURRENTLY` không chạy trong transaction block. Giữ các `SET` và lệnh maintenance trong cùng session nhưng tách command calls như ví dụ, và xác nhận hành vi của psql/version đang dùng.

### 12.7. Không đặt lệnh maintenance dài trong một transaction

VACUUM, CREATE INDEX CONCURRENTLY và REINDEX CONCURRENTLY có các giới hạn transaction riêng. Scheduler/job runner không được tự bọc các command này trong explicit transaction. Kiểm tra tool có tự mở transaction hay không.

### 12.8. Credentials và permissions

Tạo role maintenance có quyền tối thiểu cần thiết. Role chạy ANALYZE/VACUUM trên tables cần quyền owner hoặc quyền phù hợp theo version; REINDEX/DDL cần quyền sở hữu/được cấp. Không dùng superuser cho toàn bộ scheduled jobs nếu không cần.

### 12.9. Job timezone

Cron expression có thể được diễn giải theo timezone scheduler/extension. Chốt timezone, daylight saving behavior và cách xử lý giờ bị lặp/bỏ qua. Dùng timestamp UTC trong logs.

### 12.10. Scheduler downtime

Nếu scheduler ngừng hoạt động, job có thể không chạy đúng lịch. Theo dõi last successful run và overdue state, không chỉ kiểm tra scheduler process đang sống.

## 13. Job logging, concurrency và error handling

### 13.1. Ghi nhận mỗi lần chạy

Một log table đơn giản có thể lưu metadata:

~~~sql
CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.maintenance_run (
    run_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_name text NOT NULL,
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at timestamptz,
    status text NOT NULL DEFAULT 'running',
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    error_message text
);
~~~

Job runner tạo row lúc bắt đầu, cập nhật finish/status khi kết thúc. Nếu process chết đột ngột, row ở trạng thái running có thể giúp phát hiện stale job; cần policy đánh dấu failed sau timeout.

### 13.2. Không coi SQL success là business success

ANALYZE thành công không chứng minh query plans đã tốt; REINDEX thành công không chứng minh application latency đã giảm; capacity query thành công không chứng minh filesystem còn đủ chỗ. Job cần post-check theo mục tiêu.

### 13.3. Concurrency control

Một job không nên chạy đồng thời trên cùng target nếu operations xung đột hoặc cạnh tranh tài nguyên. Dùng scheduler concurrency limit, OS lock hoặc session-level advisory lock.

Ví dụ advisory lock:

~~~sql
SELECT pg_try_advisory_lock(548001::bigint) AS acquired;
~~~

Nếu `acquired` là false, job khác đang giữ lock; job mới nên thoát với trạng thái skipped/overlap. Giữ session mở trong lúc chạy và release lock khi hoàn tất:

~~~sql
SELECT pg_advisory_unlock(548001::bigint);
~~~

Advisory lock chỉ phối hợp các jobs cùng tuân theo key convention; nó không ngăn DBA/DDL khác chạy trực tiếp.

### 13.4. Retry policy

Retry chỉ phù hợp với lỗi transient và operation đã được xác định an toàn để chạy lại. Với timeout/disconnect, trước tiên kiểm tra server state vì lệnh có thể đã hoàn tất dù client không nhận được response.

### 13.5. Backoff

Khi scheduler hoặc storage/network lỗi, dùng exponential backoff có jitter và giới hạn số lần retry. Không tạo nhiều jobs đồng thời retry một lỗi chung khiến hệ thống quá tải hơn.

### 13.6. Exit codes

Script phải trả non-zero khi psql/command fail. Dùng `ON_ERROR_STOP=1` trong psql scripts, kiểm tra exit status và ghi stderr. Không redirect output theo cách làm mất exit code hoặc che lỗi.

### 13.7. Logs

Ghi:

- Task name và run ID;
- Cluster/database/schema/target;
- Start/end timestamp và timezone;
- SQL/tool version;
- Exit code/status;
- Elapsed time;
- Rows/bytes/index sizes trước/sau nếu có;
- Warnings/errors;
- Actor/service account;
- Change/incident reference.

Không ghi passwords, connection strings chứa secrets hoặc query literals nhạy cảm.

### 13.8. Stale job detection

Định nghĩa expected duration/heartbeat. Nếu một run vẫn `running` vượt deadline, kiểm tra backend/OS process trước khi kill. Tách “job runner chết” khỏi “database operation vẫn đang chạy”.

## 14. Maintenance safety controls

### 14.1. Baseline trước/sau

Trước operation, chụp:

- Relation/index sizes;
- Query latency/throughput;
- CPU, disk IOPS/latency và free space;
- Replication lag/WAL archive;
- Lock waits và long transactions;
- Backup health.

Sau operation, đo lại cùng metric và so sánh.

### 14.2. lock_timeout

`lock_timeout` giới hạn thời gian một statement chờ lock. Giá trị nhỏ có thể giúp maintenance không chặn traffic lâu khi DDL cần lock mạnh; tuy nhiên job có thể fail/retry nếu workload đang bận.

### 14.3. statement_timeout

`statement_timeout` giới hạn thời gian statement. Đặt theo expected duration và rollback cost. Timeout một lệnh rewrite dài có thể kích hoạt rollback đáng kể; đừng đặt quá thấp theo thói quen.

### 14.4. maintenance_work_mem

`maintenance_work_mem` ảnh hưởng các thao tác maintenance như index build và VACUUM. Tăng có thể giảm số vòng/giúp sort nhưng tổng memory tiêu thụ nhân theo số jobs/workers đồng thời. Đặt session-level cho job cụ thể sau khi tính capacity.

### 14.5. I/O throttling

VACUUM cost delay/limit có thể giới hạn I/O impact. Với REINDEX/pg_repack/CLUSTER, cân nhắc thời điểm, parallelism và storage throughput. Không chạy nhiều jobs nặng cùng lúc nếu làm production latency vượt SLO.

### 14.6. Replication/WAL safety

Theo dõi synchronous standby, async lag, archive failures và slot-retained WAL. Dừng/hoãn maintenance nếu làm potential RPO vượt target hoặc WAL disk gần đầy.

### 14.7. Disk preflight

Trước REINDEX/pg_repack/VACUUM FULL, ước lượng target size và temporary space. Kiểm tra cả tablespace destination, WAL volume, temp volume và filesystem reserve. Nếu không đủ headroom, hoãn hoặc chọn phương án khác.

### 14.8. Stop conditions

Định nghĩa trước điều kiện dừng:

- Application latency/error rate vượt threshold;
- Disk free xuống dưới reserve;
- Replication lag vượt RPO budget;
- WAL archive thất bại kéo dài;
- Lock wait gây ảnh hưởng critical transactions;
- Maintenance job không có tiến triển và không rõ blocker.

### 14.9. Rollback/compensation

ANALYZE có thể chạy lại; index rebuild có thể cần drop/retry nếu invalid; pg_repack có quy trình riêng; partition drop có thể không reversible nếu không có backup. Phân loại action trước khi chạy và giữ recovery path.

### 14.10. Change management

DDL lớn, thay đổi autovacuum settings, retention, tablespace và scheduler nên có owner, review, window, monitoring và post-check. Ghi lại config cũ để revert khi cần.

## 15. Capacity alerts và dashboard

### 15.1. Tách logical usage và physical free space

Dashboard nên có hai nhóm:

- PostgreSQL logical usage: database/table/index/tablespace sizes, WAL retention estimates, temp bytes và backup size;
- Infrastructure capacity: filesystem free bytes, volume quota, IOPS, throughput, latency, object storage capacity và provisioning lead time.

Một database size query thành công không có nghĩa volume còn đủ chỗ. WAL, logs, temp files và backup staging có thể nằm trên volume khác.

### 15.2. Threshold theo thời gian dự phòng

Đặt warning khi thời gian dự báo chạm capacity gần bằng lead time mở rộng cộng reserve. Critical khi free space xuống dưới mức cần để hoàn thành maintenance/backup an toàn. Ví dụ 20% free có thể là warning hợp lý ở một hệ thống nhưng quá muộn ở hệ thống tăng nhiều TB mỗi ngày.

### 15.3. Growth alert

Alert khi:

- Database/table/index growth vượt baseline;
- Growth rate thay đổi đột ngột;
- Một tablespace tăng nhanh hơn phần còn lại;
- WAL usage tăng liên tục;
- Backup repository tăng vượt retention forecast;
- Temp bytes hoặc temp files tăng bất thường.

Phân biệt spike tạm thời với growth bền vững bằng nhiều snapshots.

### 15.4. Index health dashboard

Hiển thị:

- Top indexes theo bytes;
- Index scan/read/fetch counters;
- Index size growth;
- Invalid indexes;
- Bloat sampling results;
- Index integrity check status;
- REINDEX/pg_repack history.

Đừng tự động biến panel “idx_scan = 0” thành action drop index.

### 15.5. Statistics dashboard

Hiển thị:

- `n_mod_since_analyze`;
- `last_analyze`/`last_autoanalyze`;
- `n_dead_tup`;
- `last_vacuum`/`last_autovacuum`;
- Transaction ID age;
- Planner row estimate vs actual rows từ query plan sampling;
- Query latency/plan regression.

### 15.6. Capacity dashboard

Hiển thị:

- Database/table/index/tablespace bytes;
- Filesystem free/used;
- Daily/weekly growth rate;
- Days to warning/critical capacity;
- WAL and slot retained bytes;
- Temp files/bytes;
- Backup/archive bytes and retention;
- Maintenance temporary-space reserve.

### 15.7. Alert ownership

Mỗi alert cần owner, severity, runbook và action. Capacity warning có thể thuộc platform/SRE; stale statistics thuộc DBA; invalid index thuộc DBA/application; backup retention thuộc backup owner. Không tạo alert không có người xử lý.

## 16. Runbook bảo trì index theo tháng

### 16.1. Trước review

1. Xác nhận workload window và business calendar;
2. Thu thập index sizes/usage counters;
3. Kiểm tra statistics reset timestamp;
4. Kiểm tra constraint dependencies và query workload;
5. Chạy bloat sampling trên candidates;
6. Kiểm tra invalid indexes và integrity alerts;
7. Kiểm tra disk headroom, WAL và replication lag.

### 16.2. Xếp hạng candidates

Ưu tiên index có:

- Bloat được xác nhận và dung lượng lớn;
- Query latency/plan impact rõ;
- Corruption/invalid state;
- Collation version change cần rebuild;
- Write overhead cao nhưng benefit thấp được chứng minh qua workload review.

### 16.3. Chọn operation

- REINDEX thường khi lock window được chấp nhận;
- REINDEX CONCURRENTLY khi writes phải tiếp tục và disk headroom đủ;
- pg_repack khi cần reorganize table/index với low blocking theo tool constraints;
- Không hành động nếu evidence chưa đủ.

### 16.4. Thực hiện

Chạy một target hoặc batch nhỏ trước. Đặt lock/statement timeouts, theo dõi progress, CPU/I/O, WAL, replication và application latency. Nếu metrics vượt stop conditions, dừng theo runbook.

### 16.5. Sau operation

Kiểm tra index valid/ready, query plan, latency, index size, replication lag và disk free. Ghi size trước/sau và actual duration.

## 17. Runbook statistics và capacity theo ngày/tuần

### 17.1. Daily checks

- Xem database/table/tablespace growth;
- Kiểm tra filesystem free space;
- Xem WAL usage, replication slots và archive health;
- Kiểm tra transaction ID age;
- Xem long-running transactions;
- Kiểm tra backup last success và repository capacity;
- Xem autovacuum/autoanalyze progress hoặc lag.

### 17.2. Weekly checks

- Review top tables/indexes theo growth;
- Review index usage và invalid indexes;
- Kiểm tra stale statistics trên high-churn tables;
- Review temp files và query spills;
- Review partition retention/creation;
- Kiểm tra replication/backup trends;
- Cập nhật days-to-capacity forecast.

### 17.3. Monthly checks

- Bloat sampling theo risk;
- Index integrity checks theo risk/criticality;
- Review autovacuum thresholds/worker capacity;
- Review statistics targets/extended stats;
- Review REINDEX/pg_repack candidates;
- Review backup retention và restore drill outcomes;
- Review capacity forecast và budget.

### 17.4. Sau bulk load hoặc schema change

Chạy ANALYZE trên tables bị ảnh hưởng, kiểm tra query plans, index validity, table growth và replication lag. Với partition mới, xác minh indexes/constraints được attach đúng và planner có statistics cần thiết.

### 17.5. Sau major upgrade

Kiểm tra extension compatibility, statistics refresh theo hướng dẫn upgrade, collation changes, index validity/integrity, autovacuum settings và scheduled jobs. Không chạy hàng loạt REINDEX nếu chưa có lý do/plan; collation version mismatch có thể cần xử lý cụ thể.

## 18. Ví dụ lập lịch hoàn chỉnh

### 18.1. Bảng lịch cho một OLTP cluster

| Job | Lịch ví dụ | Thời lượng budget | Kết quả cần lưu |
| --- | --- | --- | --- |
| Capacity snapshot | Mỗi 15 phút | Dưới 1 phút | Database/relation/volume bytes |
| WAL/slot/archive check | Mỗi 5 phút | Dưới 30 giây | Lag, retained WAL, archive failures |
| Daily stats inventory | 01:00 UTC | Dưới 5 phút | Table changes, vacuum/analyze dates |
| Daily ANALYZE hot tables | Sau bulk batch, nếu cần | Theo table | Stats refresh result |
| Weekly index inventory | Chủ nhật | Dưới 10 phút | Size/usage/invalid candidates |
| Monthly bloat sample | Maintenance window | Theo target | pgstattuple/index report |
| Integrity check | Theo risk tier | Theo index size | amcheck outcome |
| REINDEX candidate | Change window | Theo index size | Progress, size, plan comparison |
| Restore verification | Theo DR policy | Theo RTO | Restore result and measured time |

Đây là lịch minh họa. Tần suất, giờ và duration budget phải được hiệu chỉnh từ metrics của cluster.

### 18.2. Inventory query cho daily job

~~~sql
SELECT
    now() AS collected_at,
    current_database() AS database_name,
    count(*) AS user_table_count,
    sum(pg_total_relation_size(relid)) AS total_relation_bytes,
    sum(pg_relation_size(relid)) AS main_fork_bytes,
    sum(pg_indexes_size(relid)) AS index_bytes,
    sum(n_live_tup) AS estimated_live_tuples,
    sum(n_dead_tup) AS estimated_dead_tuples
FROM pg_stat_user_tables;
~~~

Các tuple counts là estimates; sums qua table views dùng để trend, không thay exact row counts. Chạy query trong từng database.

### 18.3. Daily capacity alert input

~~~sql
SELECT
    datname,
    pg_database_size(datname) AS database_bytes,
    age(datfrozenxid) AS xid_age
FROM pg_database
WHERE datallowconn
ORDER BY database_bytes DESC;
~~~

Đưa output vào monitoring store cùng filesystem metrics. Xác định threshold theo capacity và wraparound policy.

### 18.4. Scheduled ANALYZE sau import

Một pipeline import có thể gọi ANALYZE trực tiếp sau khi commit bulk load:

~~~sql
ANALYZE public.orders;
ANALYZE public.order_items;
~~~

Chỉ chạy sau khi import thành công và transaction đã commit. Nếu pipeline retry, ghi nhận job state để không chạy trùng các bước nặng không cần thiết.

### 18.5. Batch REINDEX

Tạo danh sách candidates đã được review và chạy từng index theo batch nhỏ. Không dùng một vòng lặp không giới hạn tự động REINDEX tất cả indexes vượt threshold; kiểm tra disk/lag/latency sau mỗi batch và dừng khi stop condition xảy ra.

## 19. Những sai lầm thường gặp

### 19.1. REINDEX tất cả theo lịch cứng

Gây I/O/WAL burst, tốn disk và có thể chặn workload. Chọn target theo evidence.

### 19.2. VACUUM FULL mỗi đêm

Đòi hỏi lock mạnh và rewrite storage. Autovacuum/VACUUM thường là cơ chế duy trì hàng ngày; rewrite chỉ dùng khi có lý do.

### 19.3. Drop index chỉ vì idx_scan = 0

Counters có thể vừa reset hoặc chưa đi qua workload hiếm. Kiểm tra constraints, workload window và query plans trước.

### 19.4. Xem relation size là filesystem free space

Logical bytes không bao gồm mọi volume usage. Kết hợp OS/cloud metrics.

### 19.5. Bỏ qua WAL/replication khi maintenance

Index rebuild, COPY và rewrite có thể tạo nhiều WAL. Theo dõi standby/archive và disk headroom.

### 19.6. Tăng maintenance_work_mem toàn cục

Nhiều maintenance jobs đồng thời có thể nhân mức memory tiêu thụ. Ưu tiên session/per-job settings sau khi tính capacity.

### 19.7. Chạy scheduler bằng superuser

Mở rộng blast radius. Dùng role riêng, least privilege, secret manager và audit.

### 19.8. Không ghi nhận lần chạy thất bại

Nếu chỉ log success, job overdue/fail có thể bị bỏ qua. Theo dõi last attempted và last successful run riêng.

### 19.9. Retry mù sau timeout

Lệnh có thể đã hoàn tất phía server. Kiểm tra state/catalog trước khi chạy lại.

### 19.10. Không kiểm tra kết quả sau maintenance

Command exit code 0 chưa chứng minh latency, plan, capacity hay integrity đã tốt hơn. So sánh baseline/post-check.

## 20. Bài tập thực hành: bảo trì index, statistics và capacity

Các bài tập dùng lab hoặc dữ liệu giả lập. Không chạy REINDEX, VACUUM FULL, pg_repack hay thao tác partition destructive trên production chỉ để làm bài. Với extension/columns phụ thuộc version, kiểm tra tài liệu đúng môi trường.

### Bài 1 — Maintenance cycle

Mô tả chu trình observe, diagnose, plan, execute, verify và learn. Cho ví dụ một tác vụ cho mỗi bước.

### Bài 2 — Index cost

Giải thích vì sao thêm nhiều indexes có thể làm INSERT/UPDATE chậm và tăng WAL.

### Bài 3 — Index usage

Viết query top 20 indexes theo kích thước và hiển thị idx_scan, idx_tup_read, idx_tup_fetch.

### Bài 4 — Zero scans

Một index lớn có idx_scan = 0 trong 7 ngày. Nêu ít nhất sáu bước cần kiểm tra trước khi đề xuất DROP.

### Bài 5 — Invalid index

Viết query tìm indexes có indisvalid = false. Nêu cách xử lý một index còn invalid sau CREATE INDEX CONCURRENTLY bị cancel.

### Bài 6 — Bloat

Giải thích vì sao pg_relation_size và row count không đủ xác định index bloat. Nêu vai trò của pgstattuple/pgstatindex.

### Bài 7 — Integrity

Phân biệt bloat sampling và amcheck. Công cụ nào kiểm tra cấu trúc B-tree?

### Bài 8 — REINDEX modes

So sánh REINDEX thường với REINDEX CONCURRENTLY về lock, disk, runtime và transaction restrictions.

### Bài 9 — pg_repack

Mô tả cách pg_repack giảm blocking và nêu các prerequisites/risks cần xác minh.

### Bài 10 — VACUUM vs REINDEX

Một table có dead tuples cao và index lớn. Vì sao chỉ REINDEX hoặc chỉ VACUUM có thể chưa giải quyết toàn bộ vấn đề?

### Bài 11 — Table inventory

Viết query top 30 user tables theo pg_total_relation_size, tách heap, index và total bytes.

### Bài 12 — Database size

Viết query sắp xếp databases theo pg_database_size và giải thích vì sao cần chạy capacity monitoring ngoài PostgreSQL.

### Bài 13 — Tablespace

Viết query size cho từng tablespace. Vì sao size này không cho biết free space của filesystem?

### Bài 14 — Growth rate

Database tăng từ 800 GB lên 920 GB trong 30 ngày. Tính growth trung bình GB/ngày và dự báo thời gian tới khi volume còn 200 GB free.

### Bài 15 — WAL retained

Viết query ước lượng WAL từ current LSN tới replication slot restart_lsn. Nêu giới hạn của estimate.

### Bài 16 — Temp files

Phân biệt temp_bytes tích lũy trong pg_stat_database với temp files hiện đang tồn tại. Nêu metrics cần bổ sung.

### Bài 17 — Analyze

Giải thích vì sao bulk load lớn nên được theo sau bởi ANALYZE trên các tables bị ảnh hưởng.

### Bài 18 — Autoanalyze

Một bảng 500 triệu rows có 2 triệu modifications. Giải thích tác động của scale factor tới thời điểm autoanalyze và cách tuning per-table.

### Bài 19 — Statistics target

Một cột status có phân bố lệch mạnh. Viết ALTER TABLE SET STATISTICS và ANALYZE cho riêng cột đó; nêu trade-off.

### Bài 20 — Extended statistics

Hai cột customer_id và status có tương quan. Viết CREATE STATISTICS với dependencies/MCV và ANALYZE; giải thích lợi ích.

### Bài 21 — Autovacuum monitoring

Viết query tìm top tables theo estimated dead tuples và hiển thị last_autovacuum/last_autoanalyze.

### Bài 22 — Wraparound

Viết query xếp database theo age(datfrozenxid). Vì sao đây là daily health check quan trọng?

### Bài 23 — Maintenance schedule

Thiết kế lịch daily/weekly/monthly cho một OLTP database 2 TB. Tách monitoring, routine cleanup và destructive maintenance.

### Bài 24 — Maintenance window

Một REINDEX CONCURRENTLY cần chạy trong window 30 phút. Thiết kế preflight, lock_timeout, statement_timeout, stop conditions và post-check.

### Bài 25 — pg_cron

Viết ví dụ schedule ANALYZE mỗi đêm bằng pg_cron. Nêu prerequisites và cách kiểm tra job history.

### Bài 26 — OS scheduler

Viết command psql qua service definition để chạy ANALYZE, bật ON_ERROR_STOP và bảo vệ credentials.

### Bài 27 — Prevent overlap

Giải thích scheduler concurrency limit và session advisory lock. Vì sao lock session cần cùng connection trong toàn job?

### Bài 28 — Job logging

Thiết kế bảng log lưu task, start/end, status, duration và error. Xử lý thế nào nếu process chết và row vẫn running?

### Bài 29 — Capacity alerts

Một volume còn 15% free nhưng tăng 100 GB/ngày và cần 5 ngày để mở rộng. Thiết kế warning/critical thresholds dựa trên lead time.

### Bài 30 — Capstone: maintenance program cho PostgreSQL production

Một cluster OLTP có 3 TB data, 800 GB indexes, 50.000 writes/second ở peak, ba tablespaces, synchronous standby ở AZ khác và async DR region. Storage chỉ còn 25% free; một số indexes tăng nhanh, autoanalyze bị trễ và backup window đang kéo dài.

**Yêu cầu:**

1. Tạo daily inventory cho database, tables, indexes và tablespaces.
2. Thu thập growth snapshots và dự báo days-to-capacity.
3. Theo dõi WAL, replication slots, archive và temp files.
4. Xác định top index candidates bằng usage, size và bloat evidence.
5. Kiểm tra invalid indexes và integrity theo risk.
6. Điều chỉnh autoanalyze/autovacuum per-table dựa trên workload.
7. Chọn REINDEX/REINDEX CONCURRENTLY/pg_repack có lock và disk budget.
8. Lập lịch pg_cron hoặc OS scheduler với least privilege, logs và concurrency control.
9. Đặt alerts/stop conditions cho disk, WAL, lag, latency và job duration.
10. Viết runbook trước/trong/sau maintenance, gồm retry và failure handling.
11. Xác minh query plans, index validity, backup duration và application latency sau maintenance.
12. Trình bày lịch vận hành hàng ngày/hàng tuần/hàng tháng cùng owner và acceptance criteria.

**Tiêu chí đạt:** mọi hành động có evidence, maintenance không vượt lock/I/O/RPO budget, capacity forecast đủ thời gian mở rộng và kết quả có baseline/post-check cùng lịch sử job.

## 21. Câu hỏi thường gặp

### 21.1. Có nên REINDEX toàn database mỗi tháng không?

Không mặc định. Chỉ rebuild indexes có evidence về bloat, corruption, collation change hoặc vấn đề hiệu năng. REINDEX toàn database có thể tạo I/O/WAL lớn, cần disk và lock.

### 21.2. VACUUM có làm giảm file size không?

VACUUM thường đánh dấu space có thể tái sử dụng bên trong relation. Nó thường không trả hết space cho filesystem. Muốn compact file có thể cần VACUUM FULL hoặc công cụ rewrite như pg_repack.

### 21.3. VACUUM có thay REINDEX không?

Không. VACUUM dọn dead tuples và cập nhật visibility/free-space metadata; REINDEX rebuild index structure.

### 21.4. REINDEX CONCURRENTLY có không block hoàn toàn không?

Không. Nó giảm blocking đối với reads/writes trong phần lớn quá trình nhưng vẫn có phase chờ locks/snapshots và cần thêm disk/WAL.

### 21.5. Khi nào dùng pg_repack?

Khi cần reorganize table/index với mức blocking thấp hơn rewrite thông thường và tool đáp ứng version/prerequisites. Nó vẫn cần disk, WAL, extension/binary tương thích và một bước swap ngắn.

### 21.6. idx_scan = 0 có nghĩa index không cần thiết?

Không. Statistics có thể reset, workload có tính mùa vụ hoặc index phục vụ constraints/query hiếm. Review đủ workload window và dependencies trước khi drop.

### 21.7. pg_relation_size có phải bloat không?

Không. Nó chỉ cho biết bytes relation đã cấp phát. Cần thêm bloat evidence như pgstattuple/pgstatindex và workload impact.

### 21.8. pgstattuple có nên chạy hàng ngày?

Không nhất thiết. Nó có thể đọc nhiều pages và gây I/O. Chọn sample/risk-based schedule và chạy ngoài peak trên relation lớn.

### 21.9. amcheck có đo bloat không?

Không. amcheck kiểm tra cấu trúc/invariants của index; pgstattuple/pgstatindex cung cấp page/tuple statistics phục vụ đánh giá space.

### 21.10. Khi nào chạy ANALYZE?

Sau bulk load, thay đổi phân bố dữ liệu lớn, schema/data maintenance hoặc khi evidence cho thấy planner statistics stale. Autoanalyze vẫn nên được bật.

### 21.11. ANALYZE có lock table không?

ANALYZE dùng lock nhẹ hơn DDL và không rewrite table, nhưng vẫn đọc pages/tiêu thụ I/O. Xem wait/impact trên workload.

### 21.12. Tăng statistics target có luôn tốt hơn?

Không. Target cao tăng sample/work và catalog size. Chỉ tăng cho columns có skew/correlation quan trọng và xác minh query plans sau đó.

### 21.13. Extended statistics thay index không?

Không. Extended statistics cải thiện planner estimates cho quan hệ giữa columns; index là cấu trúc truy cập dữ liệu.

### 21.14. Có nên chạy VACUUM mỗi đêm trên mọi table?

Không cần nếu autovacuum hoạt động đúng và table không có nhu cầu đặc biệt. Theo dõi dead tuples, freeze age và autovacuum history; chạy manual VACUUM theo evidence.

### 21.15. Vì sao autovacuum không chạy trên table ít thay đổi?

Threshold/scale factor chưa đạt hoặc table không cần cleanup. Kiểm tra modification counters, settings và logs trước khi kết luận worker bị lỗi.

### 21.16. Tại sao transaction ID age phải monitor?

Nếu transaction IDs tiến gần wraparound, PostgreSQL có thể phải vào chế độ bảo vệ và hạn chế writes. Freeze/autovacuum health là ưu tiên vận hành.

### 21.17. pg_database_size có tính WAL không?

Không phải phép đo toàn bộ filesystem usage. WAL, logs, temp files, backups và các volumes khác cần metrics riêng.

### 21.18. pg_tablespace_size có cho biết free disk?

Không. Nó cho biết relation bytes đã dùng trong tablespace; phải lấy filesystem/cloud volume free space riêng.

### 21.19. Làm sao dự báo thời điểm disk đầy?

Lưu snapshots, tính growth rate theo nhiều cửa sổ, trừ reserve/maintenance space và so với provisioning lead time. Điều chỉnh forecast theo seasonality/retention.

### 21.20. Replication slot có ảnh hưởng dung lượng không?

Có. Slot có thể giữ WAL cần thiết cho consumer offline/lagging, làm pg_wal tăng. Theo dõi retained WAL và có policy xử lý slot stale.

### 21.21. temp_bytes là dung lượng temp hiện tại?

Không. Đây là counter tích lũy trong statistics. Dùng filesystem metrics, logs và query monitoring để biết temp files hiện tại/spill workload.

### 21.22. Có thể dùng pg_cron cho mọi maintenance job?

Không. pg_cron phù hợp job SQL; workflow cần OS tools, object storage, filesystem, approval hoặc nhiều dependencies nên dùng scheduler/orchestrator bên ngoài.

### 21.23. Có nên chạy scheduler bằng superuser?

Không nếu role hẹp hơn đủ làm việc. Dùng dedicated role, least privilege, secret manager và audit.

### 21.24. Vì sao phải chống chạy trùng job?

Hai maintenance jobs đồng thời có thể tranh lock, disk, CPU, memory và I/O. Dùng concurrency policy/advisory lock và kiểm tra task đang chạy trước khi retry.

### 21.25. Job timeout có nghĩa SQL chưa chạy xong?

Không chắc. Client có thể timeout/disconnect sau khi server hoàn tất. Kiểm tra backend/catalog/job logs trước khi retry.

### 21.26. Có thể đặt lock_timeout rất thấp cho mọi job không?

Không nên dùng một giá trị cho mọi operation. Giá trị thấp giúp tránh chờ lock lâu nhưng có thể làm job fail liên tục. Chọn theo lock impact và maintenance window.

### 21.27. Vì sao REINDEX cần disk headroom?

Index mới được xây dựng trước khi thay thế index cũ trong nhiều modes. Cần space tạm cho old/new structures, WAL và các operations đồng thời.

### 21.28. Bao lâu nên chạy index integrity checks?

Theo criticality, corruption risk, workload và chi phí scan. Đặt risk-based schedule, không giả định một frequency phù hợp mọi database.

### 21.29. Có cần ANALYZE sau mỗi REINDEX không?

Không tự động. REINDEX không thay đổi dữ liệu table distribution. Chạy ANALYZE khi statistics stale hoặc có thay đổi dữ liệu/partition cần cập nhật.

### 21.30. Lịch bảo trì tốt nhất là gì?

Lịch tốt là lịch dựa trên workload và evidence, có owner, budget, stop conditions, logs và post-check. Autovacuum/autoanalyze xử lý routine work; DBA dùng lịch để quan sát, review và chạy maintenance có điều kiện.

## 22. Tài liệu PostgreSQL chính thức

Luôn chọn tài liệu đúng major version của cluster; các columns, options và extension compatibility có thể thay đổi:

- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html): VACUUM, ANALYZE, autovacuum và freezing.
- [VACUUM](https://www.postgresql.org/docs/current/sql-vacuum.html): cú pháp và behavior của VACUUM.
- [ANALYZE](https://www.postgresql.org/docs/current/sql-analyze.html): cập nhật planner statistics.
- [Planner Statistics](https://www.postgresql.org/docs/current/planner-stats.html): statistics target và extended statistics.
- [CREATE STATISTICS](https://www.postgresql.org/docs/current/sql-createstatistics.html): tạo extended statistics.
- [REINDEX](https://www.postgresql.org/docs/current/sql-reindex.html): rebuild indexes và concurrent mode.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): index creation và concurrent build.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): table/index/database statistics views.
- [Database Object Size Functions](https://www.postgresql.org/docs/current/functions-admin.html#FUNCTIONS-ADMIN-DBSIZE): relation, database và tablespace size functions.
- [Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html): theo dõi VACUUM, index build và các operations khác.
- [Routine Reindexing](https://www.postgresql.org/docs/current/routine-reindex.html): khi nào cân nhắc REINDEX.
- [Replication Slots](https://www.postgresql.org/docs/current/warm-standby.html#STREAMING-REPLICATION-SLOTS): slot retention và streaming replication.
- [pgstattuple](https://www.postgresql.org/docs/current/pgstattuple.html): tuple/page statistics extension.
- [amcheck](https://www.postgresql.org/docs/current/amcheck.html): kiểm tra cấu trúc indexes.
- [pg_cron project](https://github.com/citusdata/pg_cron): cài đặt và vận hành scheduler extension; xác minh version/package với môi trường.

## 23. Tổng kết

Bảo trì theo lịch là một chương trình quản trị liên tục, kết hợp autovacuum/autoanalyze, inventory, index review, capacity forecasting, scheduled jobs và maintenance có điều kiện.

| Nhóm | Theo dõi | Hành động |
| --- | --- | --- |
| Indexes | Size, usage, bloat evidence, validity, integrity | REINDEX/pg_repack khi có lý do |
| Statistics | Modifications, last analyze, planner estimates | Autoanalyze/ANALYZE, extended statistics |
| VACUUM | Dead tuples, freeze age, autovacuum progress | Điều chỉnh thresholds/workers, VACUUM có mục tiêu |
| Capacity | Database/relation/tablespace/WAL/temp/backup bytes | Forecast, expand, retention/partition policy |
| Scheduler | Last success, duration, overlap, exit status | Retry có kiểm soát, alert và runbook |
| Safety | Lock, latency, I/O, replication lag, disk reserve | Stop conditions, maintenance window, post-check |

Không chạy REINDEX, VACUUM FULL hoặc drop index chỉ vì lịch tới hạn. Hãy thu thập evidence, chọn operation phù hợp và đo tác động trước/sau. Dùng growth snapshots để mở rộng storage trước khi cạn dung lượng, theo dõi WAL/slots để tránh đầy disk, và giữ backup/restore process độc lập với routine maintenance.

**Một lịch bảo trì hiệu quả là lịch có thể giải thích được vì sao mỗi job chạy, ai chịu trách nhiệm, nó được phép tiêu thụ bao nhiêu tài nguyên và kết quả nào chứng minh hệ thống khỏe hơn sau khi hoàn tất.**
# Bảo trì chỉ mục, thống kê và dung lượng PostgreSQL theo lịch

Một PostgreSQL database cần được chăm sóc liên tục để query planner có thông tin đúng, indexes hoạt động hiệu quả và storage còn đủ chỗ cho workload cùng các thao tác bảo trì. Nếu chỉ chờ người dùng báo query chậm hoặc volume đầy mới xử lý, các vấn đề thường đã tích lũy trong một thời gian dài.

Bảo trì theo lịch là cách tổ chức những việc cần quan sát và thực hiện lặp lại: theo dõi index usage và trạng thái index, duy trì planner statistics, quan sát autovacuum, ghi nhận dung lượng theo thời gian, kiểm tra WAL/backup và dự báo capacity. Một lịch tốt dựa trên workload và tín hiệu vận hành. Nó không phải danh sách lệnh phải chạy bất kể database có cần hay không.

Các hoạt động cũng có mức rủi ro khác nhau. Thu thập metrics thường ít tác động. ANALYZE đọc dữ liệu để cập nhật statistics. VACUUM dọn các tuple versions có thể reclaim. REINDEX hoặc pg_repack có thể tiêu thụ I/O và storage đáng kể. VACUUM FULL cần lock mạnh và rewrite table. Vì vậy, mỗi job cần mục tiêu, giới hạn thời gian, owner, điều kiện chạy và cách xác minh kết quả.

Bài học này hướng dẫn thiết kế lịch bảo trì cho indexes, statistics và dung lượng; chọn tác vụ dựa trên evidence; lập lịch bằng scheduler phù hợp; tránh chạy trùng; kiểm soát locks/I/O/WAL; và xây runbooks cho production.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt index maintenance, VACUUM, ANALYZE và capacity management.
2. Thu thập baseline về kích thước tables/indexes và mức sử dụng indexes.
3. Phát hiện index invalid và các dấu hiệu cần điều tra.
4. Đánh giá index usage mà không xóa index chỉ dựa trên một counter.
5. Chọn giữa REINDEX, REINDEX CONCURRENTLY, pg_repack và phương án khác.
6. Giải thích planner statistics và vai trò của ANALYZE/autoanalyze.
7. Điều chỉnh analyze thresholds và statistics targets theo table/column.
8. Theo dõi dead tuples, autovacuum và transaction horizons.
9. Đo database, relation, tablespace, WAL, temporary files và filesystem.
10. Lưu snapshots để tính growth rate và dự báo capacity.
11. Thiết kế daily, weekly, monthly và event-driven maintenance schedules.
12. Chạy maintenance bằng OS scheduler hoặc pg_cron theo quyền và version.
13. Ngăn job chạy chồng lấn và ghi nhận job outcomes.
14. Quản lý lock timeout, statement timeout, I/O budget và rollback.
15. Thiết kế dashboard, alerts, runbooks và 80 bài tập thực hành.

## 2. Nguyên tắc thiết kế lịch bảo trì

Một lịch hiệu quả kết hợp kiểm tra thường xuyên với hành động có điều kiện.

### 2.1. Observe, decide, execute, verify

Một chu trình vận hành có thể gồm:

1. **Observe:** thu thập size, statistics, index usage, dead tuples, query latency và storage headroom.
2. **Decide:** xác định tín hiệu có ý nghĩa và chọn hành động cần thiết.
3. **Schedule:** chọn thời điểm, giới hạn tài nguyên, owner và stop conditions.
4. **Execute:** chạy job có logging và concurrency control.
5. **Verify:** kiểm tra trạng thái index, query plans, statistics, disk, replication và application behavior.
6. **Record:** lưu kết quả để so sánh với baseline và điều chỉnh lịch.

### 2.2. Không phải mọi tác vụ đều chạy theo lịch cứng

Autovacuum và autoanalyze vốn là cơ chế tự động dựa trên hoạt động của table. Capacity snapshots có thể chạy định kỳ. Index usage review có thể chạy hàng tuần. REINDEX chỉ nên chạy khi có bằng chứng cần thiết. VACUUM FULL không phải tác vụ nightly mặc định.

### 2.3. Tách collection khỏi action

Metrics collection thường có thể chạy thường xuyên và ít tác động hơn. Các hành động như REINDEX, rewrite hoặc thay đổi retention cần điều kiện rõ ràng và change control. Không để một câu query phát hiện bloat tự động gọi REINDEX trên mọi index vượt ngưỡng ước lượng.

### 2.4. Lịch phụ thuộc workload

Một table append-only, table update-heavy, partitioned event table và lookup table có maintenance needs khác nhau. Chọn cadence theo:
- Tốc độ insert/update/delete.
- Kích thước table và index.
- Query criticality và latency SLA.
- Mức độ skew của dữ liệu.
- Transaction duration và replication topology.
- Storage throughput và maintenance window.
- Yêu cầu backup, retention và audit.

### 2.5. Ưu tiên an toàn dữ liệu và availability

Không để index optimization trì hoãn anti-wraparound vacuum. Không chạy rewrite khi không đủ disk. Không chạy job nặng đồng thời với backup, bulk load và peak reporting nếu chúng tranh chấp cùng storage.

## 3. Các nhóm công việc bảo trì

| Nhóm | Hoạt động | Cách vận hành |
| --- | --- | --- |
| Index inventory | Size, usage, validity, dependencies | Thu thập định kỳ |
| Index maintenance | REINDEX, pg_repack, xử lý invalid index | Chỉ chạy khi có evidence |
| Planner statistics | ANALYZE, autoanalyze, extended statistics | Theo modifications và query behavior |
| Tuple cleanup | VACUUM, autovacuum tuning | PostgreSQL tự động, DBA giám sát |
| Capacity | Database/table/index/tablespace/filesystem size | Snapshot và forecast |
| WAL/replication | WAL rate, slot retention, archive lag | Monitoring liên tục |
| Backup | Backup freshness, retention, restore test | Theo policy và DR schedule |
| Retention | Drop/detach partitions, archive old data | Theo business/legal policy |
| Integrity | amcheck/pg_amcheck và restore validation | Theo risk và maintenance window |

### 3.1. Kiểm tra định kỳ không đồng nghĩa thay đổi dữ liệu

Inventory và metrics không nên tự động xóa index, drop partition hoặc thay đổi schema. Những hành động có tác động dữ liệu phải có approval và kiểm tra dependencies.

### 3.2. Event-driven maintenance

Một số tác vụ nên được kích hoạt sau sự kiện:
- Bulk load hoàn tất: ANALYZE các tables bị ảnh hưởng.
- Partition mới được attach: cập nhật statistics và xác minh index.
- Major data distribution change: ANALYZE hoặc tăng statistics target có mục tiêu.
- Extension/engine upgrade: kiểm tra indexes, statistics và compatibility.
- Backup restore rehearsal: đo restore time và storage headroom.

## 4. Thu thập baseline về kích thước

Dùng bytes cho calculations và formatted size chỉ để hiển thị.

### 4.1. Kích thước database

~~~sql
SELECT
    datname,
    pg_database_size(oid) AS size_bytes,
    pg_size_pretty(pg_database_size(oid)) AS size
FROM pg_database
WHERE datallowconn
ORDER BY pg_database_size(oid) DESC;
~~~

Chạy query trong một database có quyền phù hợp. Database size không bao gồm mọi file khác trên filesystem như logs, archive staging hoặc backup repository.

### 4.2. Kích thước table và index

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    pg_table_size(relid) AS table_bytes,
    pg_indexes_size(relid) AS index_bytes,
    pg_total_relation_size(relid) AS total_bytes,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables
ORDER BY total_bytes DESC
LIMIT 50;
~~~

pg_table_size bao gồm table storage và TOAST/auxiliary forks, không bao gồm indexes. pg_total_relation_size bao gồm cả indexes.

### 4.3. Index size

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    indexrelname AS index_name,
    pg_relation_size(indexrelid) AS index_bytes,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
ORDER BY index_bytes DESC
LIMIT 50;
~~~

### 4.4. Tablespace size

~~~sql
SELECT
    spcname,
    pg_tablespace_location(oid) AS location,
    pg_tablespace_size(oid) AS size_bytes,
    pg_size_pretty(pg_tablespace_size(oid)) AS size
FROM pg_tablespace
ORDER BY pg_tablespace_size(oid) DESC;
~~~

Tablespace size và database size là hai góc nhìn khác nhau của cùng relation files ở nhiều trường hợp; không cộng hai metrics để ra tổng disk usage.

### 4.5. Filesystem capacity

PostgreSQL size functions không thay thế filesystem metrics. Thu thập used/free bytes và inode availability cho:
- PGDATA.
- pg_wal nếu nằm trên volume riêng.
- Mỗi tablespace mount.
- PostgreSQL logs.
- Temporary/staging directories.
- WAL archive spool.
- Backup staging nếu cùng host.

Với Linux, các công cụ phổ biến là df -h và df -i. Với managed PostgreSQL, dùng provider metrics cho allocated/used/free storage và quota.

### 4.6. Baseline có context

Mỗi sample nên lưu cluster/environment, database, timestamp, PostgreSQL version, bytes, host/volume identity và stats reset time nếu là cumulative counter. Không so sánh hai sample thuộc hai cluster khác nhau chỉ vì database name giống nhau.

## 5. Index usage và inventory

PostgreSQL cung cấp pg_stat_user_indexes để xem usage counters của từng index.

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    indexrelname AS index_name,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch,
    pg_relation_size(indexrelid) AS index_bytes
FROM pg_stat_user_indexes
ORDER BY idx_scan ASC, index_bytes DESC;
~~~

### 5.1. Ý nghĩa counters

- idx_scan: số lần index được scan theo thống kê.
- idx_tup_read: số index entries được đọc.
- idx_tup_fetch: số live table rows được fetch qua index scans.

Các counters là thống kê tích lũy và có thể reset sau restart hoặc stats reset. Diễn giải chúng trong một khoảng quan sát đã biết.

### 5.2. Index scan thấp không chứng minh index thừa

Index có thể được dùng hiếm theo mùa, dùng bởi constraint, hỗ trợ foreign key checks hoặc phục vụ một query critical. Kiểm tra query logs, plans, constraints và workload cycle trước khi đề xuất drop.

### 5.3. Constraint indexes

~~~sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    i.indisprimary,
    i.indisunique,
    i.indisvalid,
    i.indisready
FROM pg_index AS i
JOIN pg_class AS idx ON idx.oid = i.indexrelid
JOIN pg_class AS tbl ON tbl.oid = i.indrelid
JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
ORDER BY ns.nspname, tbl.relname, idx.relname;
~~~

Index phục vụ PRIMARY KEY hoặc UNIQUE constraint không được loại bỏ chỉ vì idx_scan thấp. Xem constraint definitions và dependencies trước.

### 5.4. Invalid indexes

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
ORDER BY 1, 2, 3;
~~~

Concurrent index build bị lỗi hoặc bị hủy có thể để lại index invalid. Inventory nên phát hiện những indexes này để DBA xem xét nguyên nhân và phương án xử lý.

### 5.5. Indexes theo table

Một table có nhiều indexes làm tăng storage, cache pressure và write amplification. Đối chiếu từng index với query patterns, constraint needs và write cost. Không xóa index chỉ vì một query sample không dùng.

### 5.6. Index health evidence

Kết hợp:
- Size và size growth.
- idx_scan/idx_tup_read/idx_tup_fetch.
- Constraint/dependency information.
- Query plans và latency.
- B-tree page statistics nếu có công cụ phù hợp.
- Invalid/corruption checks.
- WAL generation và write workload.

## 6. Khi nào cần REINDEX?

REINDEX xây dựng lại index từ dữ liệu table hiện tại. Nó có thể thu hồi index bloat hoặc khắc phục một số tình trạng index, nhưng không phải tác vụ bắt buộc theo lịch cố định.

### 6.1. Tín hiệu cần điều tra

- Index tăng size nhanh hơn data growth mà không có giải thích.
- Có bằng chứng bloat đáng kể.
- Index invalid sau một operation thất bại.
- Có báo cáo index corruption hoặc lỗi từ công cụ kiểm tra.
- Index được tạo lại theo một maintenance plan đã đo đạc.
- Query performance thay đổi và evidence cho thấy index structure là yếu tố liên quan.

### 6.2. REINDEX thông thường

~~~sql
REINDEX INDEX app.orders_customer_id_idx;
~~~

REINDEX thông thường có thể lấy lock mạnh ảnh hưởng tới truy cập đồng thời. Đọc lock behavior theo object type và PostgreSQL version, rồi lên maintenance window.

### 6.3. REINDEX CONCURRENTLY

~~~sql
REINDEX INDEX CONCURRENTLY app.orders_customer_id_idx;
~~~

Concurrent mode giảm mức blocking đối với workload thông thường nhưng thực hiện nhiều phase, tốn thời gian và I/O hơn. Nó không có nghĩa là không có lock hoặc không thể thất bại.

### 6.4. Ràng buộc của concurrent mode

- Không chạy trong transaction block.
- Có thể không hỗ trợ một số loại relations hoặc objects ở các versions cụ thể.
- Có thể để lại invalid index nếu operation thất bại.
- Cần thêm storage trong quá trình xây index mới.
- Phải theo dõi locks và tiến độ.
- Kiểm tra documentation đúng major version trước khi tự động hóa.

### 6.5. REINDEX TABLE và DATABASE

REINDEX TABLE có thể tác động tới toàn bộ indexes của table. REINDEX DATABASE tác động tới indexes trong database hiện tại và có phạm vi lớn hơn. Tránh dùng phạm vi rộng theo lịch nếu chỉ một vài indexes có vấn đề.

### 6.6. Index partitioned tables

Với partitioned indexes, kiểm tra hỗ trợ của phiên bản và trạng thái từng partition. Một số concurrent reindex operations trên parent partitioned index có giới hạn; có thể cần xử lý leaf indexes riêng theo runbook.

## 7. pg_repack và các phương án reorganization

pg_repack là công cụ/extension bên ngoài có thể tổ chức lại tables hoặc indexes với thời gian blocking ngắn hơn một số phương pháp rewrite truyền thống. Nó có prerequisites, lock phases, triggers/log tables và yêu cầu disk đáng kể.

### 7.1. Khi nào cân nhắc?

- Bloat đã được xác nhận.
- VACUUM thường không trả file size về OS.
- Maintenance window không chấp nhận ACCESS EXCLUSIVE lock kéo dài như VACUUM FULL.
- Có đủ disk headroom và phiên bản/tool compatibility.
- Đã rehearsal trên clone.

### 7.2. Disk overhead

Reorganization thường tạo bản copy mới trong khi relation cũ vẫn tồn tại. Tính dung lượng cho table, indexes, temporary/logging objects và WAL. Không chạy khi volume gần đầy.

### 7.3. Không phải giải pháp miễn phí lock

pg_repack vẫn cần locks ở một số giai đoạn và có thể bị block bởi long transactions. Đọc documentation của đúng version và kiểm tra active sessions.

### 7.4. VACUUM FULL

~~~sql
VACUUM (FULL, ANALYZE) app.orders;
~~~

VACUUM FULL rewrite table, trả lại phần storage dư cho filesystem khi thành công nhưng cần ACCESS EXCLUSIVE lock và extra disk. Chỉ chạy trong window được phê duyệt, có headroom và rollback/recovery plan.

### 7.5. VACUUM thông thường

~~~sql
VACUUM (ANALYZE) app.orders;
~~~

VACUUM thường dọn dead tuples có thể reclaim và giúp space được tái sử dụng. Nó không thường xuyên làm relation file nhỏ lại đáng kể; không lập lịch VACUUM FULL chỉ vì VACUUM thường không giảm size.

## 8. Kiểm tra index integrity

Index size và usage không đủ để xác nhận index không có corruption. Với B-tree indexes, PostgreSQL cung cấp extension amcheck và command-line utility pg_amcheck ở các phiên bản hỗ trợ.

### 8.1. amcheck

Cài extension theo policy:

~~~sql
CREATE EXTENSION amcheck;
~~~

Một số functions có thể kiểm tra B-tree structure ở mức khác nhau. Đọc tài liệu version để chọn function, quyền và lock behavior phù hợp.

### 8.2. pg_amcheck

pg_amcheck là công cụ client có thể kiểm tra database objects và indexes theo options của version. Chạy trên database phù hợp với quyền cần thiết, giới hạn scope và theo dõi I/O.

### 8.3. Tần suất kiểm tra

Chọn theo criticality, storage reliability, change rate và yêu cầu assurance. Không nhất thiết quét mọi index lớn với tần suất cao nếu overhead không phù hợp.

### 8.4. Corruption response

Nếu phát hiện corruption:
1. Bảo toàn logs và evidence.
2. Xác định object, extent và failure scope.
3. Kiểm tra storage/kernel/hardware logs.
4. Xác minh backup có thể restore.
5. Tham khảo hướng dẫn PostgreSQL/vendor.
6. Chỉ REINDEX hoặc restore khi hiểu corruption có nằm trong index hay cả table/data files.

REINDEX có thể xây lại một index bị hỏng nếu table data còn tốt; nó không sửa corruption trong heap hoặc storage layer.

## 9. Planner statistics và ANALYZE

Planner statistics giúp PostgreSQL ước lượng cardinality/selectivity để chọn execution plan. Khi dữ liệu thay đổi đáng kể, statistics cũ có thể khiến planner chọn scan, join order hoặc join method không phù hợp.

### 9.1. ANALYZE

~~~sql
ANALYZE app.orders;
~~~

ANALYZE lấy sample từ table và cập nhật statistics trong catalogs. Có thể chạy trên một table hoặc columns cụ thể.

~~~sql
ANALYZE app.orders (customer_id, status, created_at);
~~~

### 9.2. ANALYZE VERBOSE

~~~sql
ANALYZE (VERBOSE) app.orders;
~~~

VERBOSE cung cấp thông tin xử lý hữu ích trong logs/client output. ANALYZE tiêu thụ I/O và CPU nhưng thường không cần lock độc quyền ngăn DML thông thường.

### 9.3. Autoanalyze

Autovacuum launcher cũng có thể kích hoạt autoanalyze dựa trên modification counters và thresholds. Với table có churn cao, autoanalyze có thể chạy thường xuyên; với table rất lớn, default scale factor có thể khiến lần analyze tiếp theo tới muộn.

### 9.4. Theo dõi analyze state

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze,
    analyze_count,
    autoanalyze_count
FROM pg_stat_user_tables
ORDER BY n_mod_since_analyze DESC
LIMIT 50;
~~~

Các columns/counter semantics có thể khác theo version. n_live_tup và n_mod_since_analyze là estimates/statistics, không phải exact row counts.

### 9.5. Autoanalyze threshold

Autoanalyze threshold thường kết hợp một ngưỡng tuyệt đối với tỷ lệ trên số rows ước lượng. Các settings phổ biến gồm autovacuum_analyze_threshold và autovacuum_analyze_scale_factor.

~~~sql
ALTER TABLE app.orders
SET (
    autovacuum_analyze_threshold = 2000,
    autovacuum_analyze_scale_factor = 0.02
);
~~~

Ví dụ minh họa cách cấu hình per-table. Chọn giá trị theo modifications, table size và độ nhạy của query plans.

### 9.6. Statistics target

default_statistics_target điều khiển độ chi tiết mặc định. Có thể đặt target riêng cho một column skewed hoặc có ảnh hưởng lớn tới query plan:

~~~sql
ALTER TABLE app.orders
ALTER COLUMN status SET STATISTICS 500;

ANALYZE app.orders (status);
~~~

Target cao hơn có thể cải thiện estimates nhưng tăng sample work và catalog statistics size. Không tăng toàn cluster nếu chỉ một vài columns cần.

### 9.7. Extended statistics

Khi nhiều columns tương quan, statistics độc lập có thể không mô tả đúng phân bố kết hợp.

~~~sql
CREATE STATISTICS orders_customer_status_stats
    (dependencies, ndistinct, mcv)
ON customer_id, status
FROM app.orders;

ANALYZE app.orders;
~~~

Chọn loại extended statistics theo predicates/grouping thực tế. Extended statistics không thay mọi loại cardinality estimation.

### 9.8. Sau bulk load hoặc data redistribution

Sau import lớn, partition attach hoặc thay đổi distribution, chạy ANALYZE trên tables/columns liên quan trước khi đưa workload quan trọng vào. So sánh EXPLAIN plans và estimated rows với baseline.

## 10. Autovacuum trong maintenance schedule

Autovacuum cần được giám sát liên tục. Lịch DBA nên điều chỉnh thresholds/capacity theo workload, không thay thế autovacuum bằng một VACUUM ALL định kỳ.

### 10.1. Dead tuple estimates

~~~sql
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
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 50;
~~~

Tỷ lệ dead tuples là estimate. Dùng nó để ưu tiên kiểm tra, không coi là phép đo byte bloat chính xác.

### 10.2. Per-table vacuum thresholds

~~~sql
ALTER TABLE app.events
SET (
    autovacuum_vacuum_threshold = 5000,
    autovacuum_vacuum_scale_factor = 0.02,
    autovacuum_analyze_threshold = 2000,
    autovacuum_analyze_scale_factor = 0.01
);
~~~

Đây là ví dụ cho table write-heavy. Cần benchmark worker throughput, I/O, vacuum duration và query latency trước khi áp dụng rộng.

### 10.3. Worker capacity

Các settings như autovacuum_max_workers, autovacuum_naptime, autovacuum_vacuum_cost_limit, autovacuum_vacuum_cost_delay và autovacuum_work_mem ảnh hưởng khả năng catch up. Tăng workers có thể tăng I/O contention.

### 10.4. Long transactions

Transaction lâu hoặc snapshot cũ có thể giữ dead tuples cần thiết cho snapshot, ngăn vacuum reclaim. Theo dõi xact_start, backend_xmin và replication slot xmin.

### 10.5. Freeze và wraparound

Theo dõi transaction ID age:

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;
~~~

Anti-wraparound vacuum là vấn đề availability quan trọng. Khi gần ngưỡng cảnh báo, ưu tiên xử lý freeze thay vì chạy index maintenance không cấp thiết.

### 10.6. VACUUM và filesystem

VACUUM thường làm space reusable bên trong relation; file size thường không giảm tương ứng. Chỉ rewrite/compaction phù hợp mới trả lại phần lớn storage cho filesystem. Tính lock và extra disk trước khi thực hiện.

## 11. Theo dõi dung lượng và tăng trưởng

Capacity review cần theo dõi nhiều lớp:

- Heap/table và TOAST.
- Indexes.
- Tablespaces và filesystem volumes.
- pg_wal và archive backlog.
- Temporary files.
- Replication slot retained WAL.
- Logs và audit files.
- Backup repository và restore staging.
- Headroom cho REINDEX/rewrite/bulk load.

### 11.1. Database snapshot

~~~sql
SELECT
    clock_timestamp() AS sampled_at,
    datname,
    pg_database_size(oid) AS size_bytes
FROM pg_database
WHERE datallowconn
ORDER BY datname;
~~~

### 11.2. Relation snapshot

~~~sql
SELECT
    clock_timestamp() AS sampled_at,
    current_database() AS database_name,
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.relkind,
    pg_relation_size(c.oid) AS main_bytes,
    pg_total_relation_size(c.oid) AS total_bytes
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm', 'i', 't')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY total_bytes DESC;
~~~

Partitioned parents không chứa toàn bộ data pages của partitions. Inventory cần tính leaf partitions và tránh cộng trùng parent/child.

### 11.3. WAL retention

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    CASE
        WHEN restart_lsn IS NULL THEN NULL
        ELSE pg_size_pretty(
            pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint
        )
    END AS wal_distance_estimate
FROM pg_replication_slots
ORDER BY slot_name;
~~~

Khoảng cách LSN chỉ là estimate, không phải số bytes chính xác được slot độc quyền chiếm. Kiểm tra archive failures, consumer health và filesystem metrics trước khi xử lý slots.

### 11.4. Temporary writes

~~~sql
SELECT
    datname,
    temp_files,
    temp_bytes,
    stats_reset
FROM pg_stat_database
ORDER BY temp_bytes DESC;
~~~

temp_bytes là counter tích lũy từ stats reset, không phải lượng temporary files đang nằm trên disk tại thời điểm query. Lấy delta theo thời gian và kết hợp log_temp_files/query statistics.

### 11.5. Growth rate

Với hai snapshots cách nhau Δt giây:

\[
\text{growth bytes/sec} =
\frac{\text{new size bytes} - \text{old size bytes}}{\Delta t}
\]

Giữ delta âm nếu object bị drop/truncate/rewrite. Khi forecast, dùng rolling average hoặc percentile đủ dài để phản ánh workload peaks.

### 11.6. Time to reserve

Nếu volume còn F bytes, cần giữ reserve R bytes và net growth G bytes/day:

\[
\text{days to reserve} = \frac{F-R}{G}
\]

Chỉ tính khi G dương và F lớn hơn R. Đây là linear estimate; cần tính burst, seasonality, provisioning lead time và maintenance headroom.

### 11.7. Không cộng trùng các lớp

pg_database_size, pg_tablespace_size và relation size là các góc nhìn chồng lấn. Dùng chúng để breakdown, không cộng tùy tiện. Filesystem/provider metrics mới là nguồn để xác định free bytes thực tế.

## 12. Snapshot store và retention

Có thể lưu capacity samples trong monitoring database hoặc metrics platform. Nếu lưu trong cluster đang đo, kiểm soát retention để monitoring tables không tăng vô hạn.

~~~sql
CREATE SCHEMA IF NOT EXISTS monitoring;

CREATE TABLE monitoring.database_size_samples (
    sampled_at timestamptz NOT NULL,
    cluster_name text NOT NULL,
    database_name name NOT NULL,
    size_bytes bigint NOT NULL,
    PRIMARY KEY (sampled_at, cluster_name, database_name)
);
~~~

Lưu sample:

~~~sql
INSERT INTO monitoring.database_size_samples (
    sampled_at,
    cluster_name,
    database_name,
    size_bytes
)
SELECT
    clock_timestamp(),
    'production-primary',
    datname,
    pg_database_size(oid)
FROM pg_database
WHERE datallowconn;
~~~

### 12.1. Tính delta

~~~sql
WITH samples AS (
    SELECT
        cluster_name,
        database_name,
        sampled_at,
        size_bytes,
        lag(sampled_at) OVER (
            PARTITION BY cluster_name, database_name
            ORDER BY sampled_at
        ) AS previous_at,
        lag(size_bytes) OVER (
            PARTITION BY cluster_name, database_name
            ORDER BY sampled_at
        ) AS previous_bytes
    FROM monitoring.database_size_samples
)
SELECT
    cluster_name,
    database_name,
    sampled_at,
    size_bytes - previous_bytes AS delta_bytes,
    extract(epoch FROM sampled_at - previous_at) AS elapsed_seconds,
    (size_bytes - previous_bytes)
        / NULLIF(extract(epoch FROM sampled_at - previous_at), 0)
        AS bytes_per_second
FROM samples
WHERE previous_at IS NOT NULL
ORDER BY sampled_at DESC;
~~~

### 12.2. Counter reset

Với pg_stat_database hoặc pg_stat_wal, lưu stats_reset. Nếu reset time đổi, không tính delta qua hai counter epochs khác nhau.

### 12.3. Retention

Giữ raw samples đủ cho incident analysis, sau đó roll up hourly/daily/weekly aggregates theo policy. Dữ liệu lịch sử giúp phát hiện seasonal growth và đánh giá forecast accuracy.

### 12.4. Relation lifecycle

Relation có thể rename, drop hoặc được tạo lại. Nếu cần history theo object identity, lưu database identity và OID cùng schema/name, đồng thời ghi event lifecycle. OID cũng có thể được tái sử dụng theo thời gian, nên không phải ID vĩnh viễn.

## 13. Lịch bảo trì mẫu

Bảng dưới đây là điểm khởi đầu; điều chỉnh theo workload, SLA, maintenance window và dung lượng.

| Tần suất tham khảo | Công việc | Điều kiện/đầu ra |
| --- | --- | --- |
| Liên tục | Autovacuum, autoanalyze, replication/archive monitoring | Theo dõi health và backlog |
| Mỗi 5–15 phút | Storage, WAL, replication lag, backup health metrics | Alert sớm |
| Hàng ngày | Database/table size snapshots, xid age, long transactions, failed jobs | Báo cáo capacity và risk |
| Hàng tuần | Index usage/invalid index review, analyze freshness, dead tuple review | Danh sách đối tượng cần điều tra |
| Hàng tháng | Bloat sampling, index integrity sampling, growth forecast, restore evidence review | Kế hoạch maintenance có điều kiện |
| Sau bulk load | ANALYZE affected tables, verify query plans | Planner stats mới |
| Sau partition change | Verify partition indexes, ANALYZE, retention inventory | Partition tree nhất quán |
| Theo change window | REINDEX/pg_repack/rewrite đã được phê duyệt | Có pre/post metrics |
| Theo DR policy | Backup restore/PITR rehearsal | Chứng minh khả năng phục hồi |

### 13.1. Daily checks

Daily jobs nên ưu tiên inventory nhẹ, capacity snapshots, transaction age, replication slots, archive status và backup freshness. Tránh full index scans hoặc bloat estimation nặng trên mọi relation mỗi ngày.

### 13.2. Weekly checks

Review indexes tăng nhanh, invalid indexes, statistics freshness, autovacuum history và query regressions. Hành động sửa index cần ticket/runbook riêng.

### 13.3. Monthly/quarterly checks

Chọn sample relations để đánh giá bloat/integrity, review growth forecasts, storage quota, retention policy, restore drills và extension/index maintenance needs. Critical systems có thể cần cadence khác.

### 13.4. Event-driven checks

Sau import lớn, migration, partition attach/detach, schema change hoặc upgrade, chạy đúng checks bị ảnh hưởng thay vì đợi tới lịch tuần tiếp theo.

## 14. Lập maintenance window

Một maintenance window cần chỉ rõ:
- Start/end time và timezone.
- Tác vụ được phép.
- Database/table/index scope.
- Expected duration.
- Owner và on-call contact.
- Lock/statement timeout.
- Disk/WAL headroom.
- Replication/backup state.
- Stop conditions.
- Verification và rollback/recovery procedure.

### 14.1. Không xếp nhiều I/O-heavy jobs cùng lúc

Tránh chạy đồng thời REINDEX lớn, bulk import, backup full và storage migration trên cùng volume nếu chưa benchmark. Các operations có thể cạnh tranh CPU, IOPS, throughput và WAL capacity.

### 14.2. Lock timeout

Có thể đặt lock_timeout cho session maintenance để job không chờ lock vô hạn:

~~~sql
SET lock_timeout = '5s';
REINDEX INDEX CONCURRENTLY app.orders_customer_id_idx;
~~~

Giá trị là ví dụ. Lock timeout quá thấp có thể làm job thất bại thường xuyên; quá cao có thể kéo dài blocking queue.

### 14.3. Statement timeout

statement_timeout giới hạn thời gian statement. Chọn theo expected runtime và khả năng rollback. Với thao tác dài, timeout quá thấp có thể khiến job bị cancel và để lại cleanup cần xử lý.

### 14.4. VACUUM ngoài transaction block

VACUUM không được chạy bên trong transaction block. Khi lập lịch, chạy trực tiếp qua client command/job phù hợp; không bọc VACUUM trong một function/DO block thông thường.

### 14.5. REINDEX CONCURRENTLY ngoài transaction block

REINDEX CONCURRENTLY cũng không chạy trong transaction block. Scheduler phải gửi statement theo cách không tự bọc toàn bộ job trong BEGIN/COMMIT.

### 14.6. Stop conditions

Ví dụ:
- Free space xuống dưới reserve.
- Replication lag vượt RPO budget.
- Application p99 latency vượt stop threshold.
- Lock wait queue tăng bất thường.
- Backup/archive đang lỗi.
- Job không tiến triển hoặc vượt runtime budget.

## 15. Chọn scheduler

Có thể dùng OS scheduler, orchestration platform hoặc pg_cron. Chọn một cơ chế phù hợp với kiến trúc và có owner rõ ràng.

### 15.1. OS scheduler

Cron, systemd timers hoặc Windows Task Scheduler có thể gọi psql/script. Ưu điểm là job orchestration tách khỏi database; cần quản lý credentials, network, client versions, logs và retries.

### 15.2. pg_cron

pg_cron là extension scheduler chạy job SQL theo lịch. Cần cài package tương thích, cấu hình theo tài liệu extension, tạo extension trong database phù hợp và cấp quyền cho job owner. Một số cấu hình yêu cầu shared_preload_libraries và restart.

### 15.3. Job identity

Mỗi job nên chạy bằng role chuyên dụng, chỉ có quyền đọc metrics hoặc thực hiện maintenance cụ thể. Không chạy toàn bộ maintenance scheduler bằng superuser nếu không cần.

### 15.4. Managed PostgreSQL

Một số providers hỗ trợ pg_cron hoặc scheduler riêng với allowlist/parameter requirements. Xác minh service capabilities trước khi thiết kế.

### 15.5. Một nguồn lịch chuẩn

Tránh cùng một job được lên lịch trong cả cron và pg_cron. Duy trì inventory gồm job name, schedule, owner, command, timezone, timeout, concurrency policy và destination logs.

## 16. Tránh job chạy chồng lấn

Nếu một job mất nhiều thời gian hơn interval, lần chạy tiếp theo có thể bắt đầu khi lần trước chưa hoàn tất, tùy scheduler.

### 16.1. Scheduler concurrency policy

Dùng cấu hình scheduler để giới hạn một instance mỗi job. Với pg_cron, đọc behavior theo version và cách kết nối; không giả định tất cả jobs có cùng concurrency semantics.

### 16.2. Advisory locks

Một script có thể lấy advisory lock trước khi thực hiện job. Dùng cùng session connection trong suốt job và release lock khi hoàn tất. Nếu connection đóng, session-level advisory lock được giải phóng.

### 16.3. Lock key

Chọn key ổn định theo job/cluster để các instances cùng tranh chấp một lock. Ghi log khi không lấy được lock và đánh dấu job skipped/overlap, không coi là success.

### 16.4. Không giữ transaction bao trùm maintenance

Advisory lock không bắt buộc phải đi cùng transaction dài. Với VACUUM/REINDEX CONCURRENTLY, thiết kế runner giữ session-level lock trong khi gửi commands riêng lẻ, không bọc commands vào một transaction block.

### 16.5. Lease và stale state

Nếu dùng external lock/lease table, cần xử lý worker crash, lease expiry, clock skew và job ownership. Advisory locks thường đơn giản hơn khi mọi workers kết nối cùng PostgreSQL cluster.

## 17. Ghi log và theo dõi job runs

Một job không nên chỉ trả exit code mà không lưu kết quả.

~~~sql
CREATE SCHEMA IF NOT EXISTS maintenance;

CREATE TABLE maintenance.job_runs (
    run_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_name text NOT NULL,
    started_at timestamptz NOT NULL,
    finished_at timestamptz,
    status text NOT NULL,
    executor text,
    target_object text,
    rows_or_objects bigint,
    details text,
    error_text text
);
~~~

### 17.1. Job metadata

Ghi job name, run ID, start/end, duration, executor role, database, object scope, status, error code/message và link tới logs.

### 17.2. Không lưu secrets

Không ghi connection passwords, tokens hoặc sensitive query literals vào maintenance tables/logs.

### 17.3. Exit status

Script cần trả exit status rõ ràng để scheduler biết success/failure. psql có thể dùng ON_ERROR_STOP để dừng khi SQL error.

### 17.4. Retry policy

Inventory queries thường retry an toàn. DDL/maintenance actions cần kiểm tra server state trước khi retry; timeout ở client không chứng minh server operation đã dừng.

### 17.5. Idempotency

Mỗi job phải xác định trạng thái trước khi action. Ví dụ, không drop/recreate index mù quáng chỉ vì job lần trước không ghi được log cuối.

## 18. Ví dụ chạy maintenance từ psql

Một script OS scheduler có thể gọi psql với connection service/credential store đã cấu hình.

~~~bash
psql "service=maintenance_db" \
  -v ON_ERROR_STOP=1 \
  -c "ANALYZE app.orders;"
~~~

Không đặt password trực tiếp trong command line hoặc script repository. Dùng .pgpass với permissions phù hợp, service file, secret manager hoặc provider identity mechanism.

### 18.1. Chạy nhiều commands

Đặt từng operation có mục tiêu và log riêng. Không gom nhiều destructive actions vào một chuỗi không có checkpoints/verification.

### 18.2. VACUUM

~~~bash
psql "service=maintenance_db" \
  -v ON_ERROR_STOP=1 \
  -c "VACUUM (ANALYZE, VERBOSE) app.orders;"
~~~

### 18.3. REINDEX CONCURRENTLY

~~~bash
psql "service=maintenance_db" \
  -v ON_ERROR_STOP=1 \
  -c "REINDEX INDEX CONCURRENTLY app.orders_customer_id_idx;"
~~~

Đảm bảo client/session không bọc command trong transaction block và version hỗ trợ operation.

### 18.4. Connection identity

Đặt application_name riêng cho maintenance job để DBA có thể nhận diện trong pg_stat_activity. Dùng role chuyên dụng và database/schema được giới hạn.

## 19. Lịch ANALYZE có mục tiêu

ANALYZE không nhất thiết phải chạy trên toàn database mỗi đêm. Chọn tables dựa trên modification counters, bulk loads và query plan evidence.

### 19.1. Tables thay đổi nhiều

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_mod_since_analyze,
    last_autoanalyze,
    last_analyze
FROM pg_stat_user_tables
ORDER BY n_mod_since_analyze DESC
LIMIT 30;
~~~

### 19.2. Sau bulk load

Chạy ANALYZE trên tables vừa import, đặc biệt nếu row distribution thay đổi mạnh. Nếu nhiều partitions mới được attach, xác định cần analyze leaf partitions, parent statistics hoặc cả hai theo version/planner behavior.

### 19.3. Column-specific analyze

Chạy ANALYZE trên columns ảnh hưởng tới predicates/joins khi cần. Nếu tăng statistics target, ghi lại lý do và query pattern tương ứng.

### 19.4. Verify planner

Dùng EXPLAIN (ANALYZE, BUFFERS) trong môi trường phù hợp để so estimated rows với actual rows. EXPLAIN ANALYZE thực thi statement; chỉ chạy với query an toàn và hiểu tác động.

### 19.5. Không analyze liên tục

ANALYZE quá thường xuyên tiêu thụ I/O/CPU và có thể tạo churn trong statistics. Dựa trên modification rates và planner regressions.

## 20. Lịch index review có mục tiêu

Một index review hàng tuần có thể tạo report, không tự động reindex.

### 20.1. Report size và usage

~~~sql
SELECT
    s.schemaname,
    s.relname AS table_name,
    s.indexrelname AS index_name,
    s.idx_scan,
    pg_relation_size(s.indexrelid) AS size_bytes,
    i.indisprimary,
    i.indisunique,
    i.indisvalid
FROM pg_stat_user_indexes AS s
JOIN pg_index AS i ON i.indexrelid = s.indexrelid
ORDER BY size_bytes DESC;
~~~

### 20.2. Compare theo thời gian

Lưu counters và size snapshots. Tính delta giữa các samples cùng stats epoch. Khi stats reset, bắt đầu baseline mới.

### 20.3. Review index candidates

Đánh dấu index có size lớn, usage thấp hoặc invalid để review. Kiểm tra query logs, constraints, foreign keys và workload seasonal trước quyết định.

### 20.4. REINDEX candidate

Tạo ticket với:
- Index/table name.
- Size hiện tại.
- Evidence bloat/corruption.
- Expected benefit.
- Disk headroom.
- Lock mode/duration.
- Replication/WAL impact.
- Maintenance window.
- Verification/rollback plan.

## 21. Integrity checks và amcheck schedule

Với database quan trọng, đưa index integrity checks vào risk-based schedule.

### 21.1. Chọn scope

Có thể ưu tiên indexes của tables critical, indexes vừa rebuild, storage có lỗi hoặc objects có corruption symptoms.

### 21.2. pg_amcheck

pg_amcheck là client tool có options theo version để kiểm tra databases/schemas/tables/indexes. Chạy với concurrency/I/O limits phù hợp.

### 21.3. amcheck functions

Extension amcheck cung cấp functions kiểm tra một số index structures. Function/lock requirements tùy version và mode.

### 21.4. Kết quả bất thường

Giữ logs, xác định object và failure scope. Không tự động reindex mọi object sau một warning chung; xác minh bằng hướng dẫn PostgreSQL và storage evidence.

## 22. Capacity snapshots và forecasting

### 22.1. Lưu database sizes

Tạo metrics store bên ngoài hoặc bảng monitoring có retention:

~~~sql
CREATE TABLE maintenance.database_size_samples (
    sampled_at timestamptz NOT NULL,
    database_name name NOT NULL,
    size_bytes bigint NOT NULL,
    PRIMARY KEY (sampled_at, database_name)
);
~~~

### 22.2. Tính growth rate

Nếu size tăng từ S1 lên S2 trong Δt seconds:

\[
\text{bytes per day} =
\frac{S_2-S_1}{\Delta t} \times 86400
\]

Lưu bytes và timestamps; không tính từ chuỗi pg_size_pretty.

### 22.3. Forecast tới reserve

\[
\text{days to reserve} =
\frac{\text{free bytes}-\text{reserve bytes}}
{\text{positive growth bytes/day}}
\]

Dùng rolling average/percentile và tính peak/batch scenarios. Linear forecast không dự đoán được thay đổi workload đột ngột.

### 22.4. Maintenance headroom

Dự trù extra disk cho:
- REINDEX hoặc concurrent index build.
- VACUUM FULL/CLUSTER.
- pg_repack shadow table/index.
- Bulk import và sort spill.
- Backup/restore staging.
- WAL archive backlog và replication slots.

### 22.5. Volume-specific forecast

Nếu tablespaces hoặc pg_wal ở volumes riêng, forecast từng mount. Database size tổng có thể ổn định trong khi một volume cụ thể sắp đầy.

## 23. Theo dõi WAL, replication và archive

### 23.1. WAL generation

Trên versions có pg_stat_wal:

~~~sql
SELECT *
FROM pg_stat_wal;
~~~

Lấy delta wal_bytes theo thời gian để tính WAL generation rate. Ghi stats_reset để nhận biết counter epoch.

### 23.2. Replication slots

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
~~~

Inactive slots có thể giữ WAL. Xác định owner/consumer và recovery plan trước khi drop.

### 23.3. Archive status

~~~sql
SELECT *
FROM pg_stat_archiver;
~~~

Archive failures có thể làm WAL tích tụ. Kiểm tra logs, destination capacity, permissions và retry behavior.

### 23.4. Replication lag

Đọc pg_stat_replication trên primary và subscriber/standby metrics phù hợp. Một maintenance job tạo WAL lớn có thể làm replica lag tăng và giữ thêm WAL.

### 23.5. Capacity gate

Không bắt đầu REINDEX/rewrite lớn nếu WAL volume, archive hoặc replication đã gần ngưỡng critical mà chưa có headroom.

## 24. Backup và restore trong lịch bảo trì

Backup là một phần của maintenance program. Một backup job thành công không chứng minh restore sẽ hoạt động.

### 24.1. Backup freshness

Kiểm tra last successful backup, duration, size, WAL archive continuity, retention và destination capacity.

### 24.2. Restore verification

Theo lịch DR, restore backup vào môi trường cô lập, replay WAL nếu cần và kiểm tra database opens, extensions, roles, critical queries và application-level consistency.

### 24.3. Maintenance và backup contention

REINDEX, bulk load, VACUUM FULL hoặc pg_repack có thể tăng I/O/WAL và kéo dài backup. Không xếp chồng nếu storage budget chưa được benchmark.

### 24.4. Backup trước destructive maintenance

Trước DROP/partition retention hoặc rewrite lớn, xác nhận backup/PITR chain và retention/legal requirements. Backup không thay thế việc review object dependencies.

## 25. Retention và partition maintenance

Với dữ liệu time-series/event, partitioning có thể làm retention hiệu quả hơn xóa từng row.

### 25.1. Partition lifecycle

Lập lịch:
- Tạo partitions tương lai.
- Xác minh partition bounds.
- Attach partition sau khi validate.
- Analyze affected relations.
- Detach/drop partitions hết hạn theo policy.
- Cập nhật inventory và backup retention.

### 25.2. Drop partition

DROP/DETACH có thể giải phóng storage nhanh hơn DELETE hàng triệu rows, nhưng là thay đổi dữ liệu có tính destructive. Xác minh business retention, foreign keys, replication/publication và downstream consumers.

### 25.3. Default partition growth

Theo dõi default partition. Nếu routing lỗi hoặc thiếu partition tương lai, default partition có thể tăng nhanh bất thường.

### 25.4. Partition indexes

Xác minh indexes của partition mới khớp parent partitioned index và application query requirements. Kiểm tra invalid/incomplete index attachments.

## 26. Thiết kế maintenance jobs theo loại

### 26.1. Inventory job

Chỉ đọc metrics, ghi snapshot và tạo report. Có thể chạy thường xuyên hơn nếu query cost thấp.

### 26.2. Analyze job

Chọn tables cần analyze từ modification counters, bulk-load events hoặc query plan evidence. Chạy bằng role có quyền thích hợp.

### 26.3. Vacuum job

Ưu tiên autovacuum. Chỉ chạy manual VACUUM khi có mục tiêu rõ, ví dụ sau bulk delete hoặc maintenance event. Không thay autovacuum bằng nightly full sweep thiếu kiểm soát.

### 26.4. Index job

Review candidate trước. Reindex từng object/batch có giới hạn, tránh reindex toàn cluster chỉ vì lịch.

### 26.5. Capacity job

Thu database/relation/tablespace/WAL/filesystem/backup metrics. Tính growth rate và forecast. Không dùng SQL size functions để suy ra filesystem free space.

### 26.6. Integrity job

Chạy amcheck/pg_amcheck theo risk, giới hạn I/O và lưu kết quả. Có quy trình incident nếu phát hiện lỗi.

## 27. Quyền và bảo mật cho maintenance

Tạo roles riêng cho từng nhóm nhiệm vụ.

| Role | Quyền cần thiết |
| --- | --- |
| maintenance_monitor | Đọc activity/statistics và metrics cần thiết |
| maintenance_analyzer | Quyền cần để ANALYZE các tables trong scope |
| maintenance_operator | Chạy VACUUM/REINDEX được phê duyệt |
| capacity_collector | Đọc size/catalog/provider metrics |
| backup_operator | Thực hiện backup/restore theo policy |
| database_owner | Quản lý objects/schema theo trách nhiệm |

### 27.1. Least privilege

Không chạy mọi job bằng superuser. Một số operations cần owner/superuser hoặc predefined roles; cấp quyền đúng scope và version.

### 27.2. Credentials

Dùng secret manager, service files hoặc cơ chế identity phù hợp. Không lưu password trong cron line, repository hoặc logs.

### 27.3. Application name

Đặt application_name cho job để nhận diện trong pg_stat_activity và logs.

### 27.4. Audit

Ghi actor, timestamp, command/object scope, change reference và result. Hạn chế query text/secret leakage.

## 28. Troubleshooting: maintenance job bị block

1. Xác định PID/application_name của job.
2. Đọc state, query age, transaction age và wait events.
3. Dùng pg_blocking_pids để tìm blockers.
4. Xem blocker state và transaction age.
5. Xác định job có cần tiếp tục trong window hay không.
6. Liên hệ owner của blocker hoặc dời lịch.
7. Chỉ cancel/terminate theo incident policy.
8. Xác nhận job state và retry safety trước khi chạy lại.

Không cancel một job chỉ vì duration vượt dự kiến; trước hết xác định nó đang tiến triển hay chờ lock.

## 29. Troubleshooting: REINDEX thất bại

Nguyên nhân có thể là lock timeout, disk thiếu, concurrent build conflict, cancellation, server restart hoặc corruption.

Quy trình:
1. Đọc server/client logs và xác định phase.
2. Kiểm tra index validity/readiness.
3. Kiểm tra filesystem/WAL headroom.
4. Xác định concurrent sessions và blockers.
5. Xác minh application queries/constraints.
6. Dùng supported cleanup/retry procedure.
7. Không drop index thủ công nếu nó backing constraint.
8. Re-run verification và query plan tests.

## 30. Troubleshooting: planner chọn plan xấu sau maintenance

1. Thu EXPLAIN (ANALYZE, BUFFERS) nếu query an toàn.
2. So estimated rows với actual rows.
3. Kiểm tra last_analyze/autoanalyze và modification counters.
4. Kiểm tra statistics targets và data skew.
5. Xem extended statistics nếu columns tương quan.
6. Kiểm tra parameter values, search_path và prepared statement behavior.
7. Chạy ANALYZE có mục tiêu nếu stats stale.
8. So sánh plans/latency sau thay đổi.

Không tạo index mới chỉ vì planner chọn sequential scan; sequential scan có thể là plan tối ưu khi query đọc phần lớn table.

## 31. Troubleshooting: dung lượng tăng nhanh

1. Xác định volume/mount thực sự tăng.
2. So database/relation size snapshots.
3. Xếp hạng table/index/partition theo delta.
4. Kiểm tra WAL directory, slots và archive backlog.
5. Kiểm tra temporary files và query spills.
6. Kiểm tra logs, backups và staging files.
7. Kiểm tra dead tuples, autovacuum và transaction horizons.
8. Xác định growth do business data, bloat, WAL hay artifacts.
9. Mở rộng volume hoặc giảm đúng nguồn tăng theo runbook.
10. Xác nhận free space và recovery health sau xử lý.

## 32. Lập lịch theo môi trường

### 32.1. Development

Có thể chạy inventory thường xuyên và thử maintenance operations trên dữ liệu nhỏ. Không dùng lịch development làm mặc định production.

### 32.2. Staging

Dùng staging để rehearse job schedule, permissions, locks, runtime, disk headroom và failure/retry behavior với dữ liệu đại diện.

### 32.3. Production

Pin job versions, change windows, owner, timeout, concurrency policy và alerts. Theo dõi impact lên application SLO.

### 32.4. Multi-region/HA

Xác định maintenance chạy trên primary hay standby. Không chạy DDL/reindex đồng thời trên mọi nodes nếu operation không được thiết kế cho topology đó. Đồng bộ package/config và kiểm tra failover readiness.

## 33. Review và cải tiến lịch

Mỗi tháng/quý, đánh giá:
- Job nào thường xuyên không cần thiết?
- Job nào hay bị skip do lock?
- Duration có tăng theo data size không?
- Job nào cạnh tranh backup hoặc batch workload?
- Index candidates có thực sự cải thiện sau REINDEX?
- ANALYZE có giảm cardinality estimation errors?
- Autovacuum có bắt kịp churn?
- Capacity forecasts sai lệch bao nhiêu?
- Restore drills có đáp ứng RTO/RPO?
- Có job trùng lặp giữa scheduler systems?

Lịch nên thay đổi khi workload, data volume, SLA hoặc kiến trúc storage thay đổi.

## 34. Bài tập thực hành PostgreSQL

Thực hiện trên lab/staging hoặc môi trường được phép. Không chạy destructive operations, VACUUM FULL hoặc REINDEX lớn trên production chỉ để thử nghiệm.

1. **Inventory:** liệt kê databases và sizes bằng pg_database_size.
2. **Tables:** liệt kê 50 tables lớn nhất.
3. **Indexes:** liệt kê 50 indexes lớn nhất.
4. **Breakdown:** so sánh pg_table_size, pg_indexes_size và pg_total_relation_size.
5. **Tablespace:** liệt kê tablespace locations và sizes.
6. **Filesystem:** thu thập free bytes và inode availability từ host/provider.
7. **Index usage:** đọc idx_scan, idx_tup_read và idx_tup_fetch.
8. **Stats reset:** xác định thời điểm statistics được reset.
9. **Unused candidate:** tạo report indexes idx_scan bằng zero.
10. **Constraint review:** xác định indexes backing primary/unique constraints.
11. **Invalid index:** tìm indexes có indisvalid=false.
12. **Index growth:** lưu hai size snapshots và tính delta.
13. **Index bloat:** tìm hiểu một phương pháp estimate và giới hạn của nó.
14. **amcheck:** cài extension trong lab và chạy integrity check được hỗ trợ.
15. **pg_amcheck:** chạy tool với scope giới hạn.
16. **REINDEX:** reindex một index lab và so size trước/sau.
17. **REINDEX CONCURRENTLY:** thử operation và quan sát phases/locks.
18. **Transaction block:** kiểm tra vì sao REINDEX CONCURRENTLY không chạy trong transaction block.
19. **Invalid cleanup:** mô phỏng failed concurrent build và lập quy trình xử lý.
20. **pg_repack:** rehearsal trên clone nếu tool được hỗ trợ.
21. **VACUUM:** chạy VACUUM thường và quan sát dead tuples.
22. **VACUUM FULL:** chạy trên table nhỏ lab và đo lock/disk overhead.
23. **ANALYZE:** chạy ANALYZE VERBOSE trên một table.
24. **Autoanalyze:** quan sát autoanalyze counters/timestamps.
25. **Modification count:** xếp hạng tables theo n_mod_since_analyze nếu version hỗ trợ.
26. **Analyze threshold:** điều chỉnh per-table analyze scale factor trong lab.
27. **Statistics target:** tăng target một column skewed và đo analyze/query planning.
28. **Extended statistics:** tạo dependencies/ndistinct/MCV stats.
29. **Plan comparison:** so estimated rows trước/sau ANALYZE.
30. **Bulk load:** import rows và ANALYZE affected table.
31. **Partition analyze:** tạo partition mới và xác định statistics cần cập nhật.
32. **Dead tuples:** xếp hạng tables theo n_dead_tup.
33. **Autovacuum history:** kiểm tra last_autovacuum và vacuum_count.
34. **Per-table vacuum:** cấu hình thresholds trên table write-heavy trong lab.
35. **Worker capacity:** đọc autovacuum_max_workers và cost settings.
36. **Long transaction:** tạo transaction lâu và quan sát vacuum horizon.
37. **XID age:** xếp hạng databases theo age(datfrozenxid).
38. **WAL slots:** inventory replication slots và retained WAL estimates.
39. **Database snapshot:** tạo bảng database_size_samples.
40. **Growth rate:** tính bytes/day từ hai snapshots.
41. **Time to reserve:** tính ngày tới reserve threshold.
42. **Relation snapshot:** lưu table/index size theo relation.
43. **Partition growth:** tìm partition có growth lớn nhất.
44. **Tablespace alert:** thiết kế alert theo từng volume.
45. **Temporary files:** đọc temp_files/temp_bytes và tính rate.
46. **Archive:** đọc pg_stat_archiver và cảnh báo failures.
47. **Backup freshness:** tạo report last successful backup theo policy.
48. **Restore drill:** restore một backup vào staging và ghi runtime.
49. **Job inventory:** lập danh sách job, owner, schedule và command.
50. **Cron:** tạo một inventory job chạy qua OS scheduler.
51. **pg_cron:** cài/configure pg_cron trong lab nếu được hỗ trợ.
52. **Permissions:** tạo maintenance_monitor role chỉ đọc metrics.
53. **Analyzer role:** thiết kế quyền cho role chạy ANALYZE.
54. **Operator role:** xác định quyền cần cho REINDEX/VACUUM.
55. **Credentials:** cấu hình psql service/secret store mà không hard-code password.
56. **Application name:** đặt application_name cho maintenance runner.
57. **Job logs:** tạo maintenance.job_runs table.
58. **Exit status:** cấu hình psql ON_ERROR_STOP và kiểm tra scheduler result.
59. **Overlap:** mô phỏng job kéo dài và ngăn instance thứ hai chạy.
60. **Advisory lock:** dùng session-level advisory lock trong runner.
61. **VACUUM runner:** chạy VACUUM trực tiếp ngoài transaction block.
62. **REINDEX runner:** chạy REINDEX CONCURRENTLY đúng session/transaction behavior.
63. **Lock timeout:** đặt lock_timeout cho maintenance job lab.
64. **Statement timeout:** thử timeout và quan sát cancellation/retry implications.
65. **Stop condition:** dừng job khi disk free xuống dưới reserve.
66. **Backup contention:** benchmark backup cùng lúc với index build trong staging.
67. **I/O budget:** đo storage latency trước/sau maintenance.
68. **Capacity gate:** chặn REINDEX khi thiếu disk headroom.
69. **Event-driven:** tạo job ANALYZE sau bulk load event.
70. **Retention:** thiết kế partition detach/drop theo retention policy.
71. **Default partition:** cảnh báo khi default partition tăng bất thường.
72. **Index partition:** xác minh partition indexes sau attach.
73. **Runbook:** viết quy trình xử lý invalid index.
74. **Runbook:** viết quy trình xử lý job bị block.
75. **Runbook:** viết quy trình xử lý planner regression.
76. **Runbook:** viết quy trình xử lý storage growth spike.
77. **Schedule review:** đánh giá một lịch maintenance có job trùng/overlap.
78. **Staging rehearsal:** chạy maintenance window đầy đủ trên dữ liệu đại diện.
79. **SLO review:** so sánh p95/p99 latency và replication lag trước/sau maintenance.
80. **Thiết kế tổng hợp:** xây lịch bảo trì PostgreSQL production gồm index inventory/integrity, conditional reindex, statistics/autovacuum, capacity snapshots/forecast, backup verification, scheduler permissions, concurrency control, logging, alerts, maintenance windows và rollback runbooks.

## 35. Checklist vận hành

### Indexes

- [ ] Có inventory size và usage theo database.
- [ ] Stats reset time được ghi nhận.
- [ ] Constraint/dependency indexes được bảo vệ.
- [ ] Invalid indexes được phát hiện.
- [ ] Bloat/corruption có evidence trước khi reindex.
- [ ] REINDEX method phù hợp lock/downtime requirements.
- [ ] Extra disk và WAL headroom được kiểm tra.
- [ ] Kết quả/query plans được xác minh sau maintenance.

### Statistics và vacuum

- [ ] Autoanalyze thresholds phù hợp table size/churn.
- [ ] Bulk loads có ANALYZE follow-up.
- [ ] Statistics targets chỉ tăng cho columns cần thiết.
- [ ] Extended statistics được dùng khi có tương quan phù hợp.
- [ ] Dead tuples và autovacuum history được theo dõi.
- [ ] Long transactions và xmin horizons được theo dõi.
- [ ] XID age/anti-wraparound được ưu tiên.
- [ ] Không thay autovacuum bằng VACUUM sweep thiếu kiểm soát.

### Capacity

- [ ] Database/relation/index/tablespace snapshots có lịch sử.
- [ ] Filesystem/provider free bytes và inodes được theo dõi.
- [ ] WAL, slots, archive và temp usage được theo dõi.
- [ ] Backup repository có metrics/retention riêng.
- [ ] Growth rate và time-to-reserve được tính.
- [ ] Headroom cho REINDEX/rewrite/restore được dự trù.
- [ ] Forecast được review theo workload peaks.

### Scheduler và change control

- [ ] Mỗi job có owner, role và command rõ.
- [ ] Không có lịch trùng giữa nhiều scheduler.
- [ ] Job không chạy chồng lấn ngoài policy.
- [ ] Credentials được quản lý an toàn.
- [ ] VACUUM/REINDEX CONCURRENTLY chạy ngoài transaction block.
- [ ] Logs, exit codes, retries và duration được lưu.
- [ ] Lock/statement timeout và stop conditions được xác định.
- [ ] Maintenance window có verification và rollback plan.

## 36. Tổng kết

Bảo trì PostgreSQL theo lịch là một chương trình quan sát và hành động có điều kiện:

~~~text
COLLECT BASELINE
  indexes / statistics / vacuum / storage
             |
             v
REVIEW SIGNALS
  usage / invalid state / stale stats / growth
             |
             v
PLAN MAINTENANCE
  owner / window / locks / I/O / disk / rollback
             |
             v
EXECUTE CONTROLLED JOBS
  ANALYZE / VACUUM / REINDEX / capacity tasks
             |
             v
VERIFY AND RECORD
  plans / integrity / free space / replication / backup
             |
             v
REFINE THE SCHEDULE
~~~

Những nguyên tắc quan trọng:

- **Autovacuum và autoanalyze là nền tảng tự động.** DBA theo dõi và tuning theo workload thay vì thay thế bằng một lịch VACUUM/ANALYZE cứng.
- **Index review không phải lệnh xóa index.** Kết hợp usage, constraints, query plans, workload seasonality và size history.
- **REINDEX cần evidence và capacity.** Concurrent mode giảm blocking nhưng vẫn tốn I/O, thời gian, locks và extra storage.
- **Statistics phải theo kịp thay đổi dữ liệu.** Sau bulk load hoặc distribution changes, ANALYZE có mục tiêu giúp planner có estimates phù hợp.
- **Capacity cần lịch sử.** Snapshots theo database/relation/volume cho phép tính growth và dự báo thời gian tới reserve.
- **Filesystem free space khác reusable page space.** VACUUM thường không làm relation file shrink đáng kể.
- **Scheduler cần concurrency control và logs.** Tránh job chạy trùng, retry mù hoặc giữ transaction quá lâu.
- **Maintenance phải có stop conditions.** Disk, replication lag, application latency và lock queues đều có thể yêu cầu dừng hoặc dời job.
- **Backup/restore verification là một phần của maintenance.** Backup success cần được bổ sung bằng restore drills.
- **Lịch phải được review.** Khi data volume, workload, SLA hoặc storage thay đổi, cadence và maintenance windows cũng cần thay đổi.

Một chương trình bảo trì tốt giúp phát hiện vấn đề trước khi thành incident, giữ planner statistics phù hợp, indexes ở trạng thái có thể sử dụng, storage trong capacity budget và mọi thao tác maintenance có thể giải thích, kiểm chứng và lặp lại an toàn.


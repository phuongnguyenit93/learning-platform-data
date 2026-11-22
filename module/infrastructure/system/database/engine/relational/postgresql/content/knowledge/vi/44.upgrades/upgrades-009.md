# Thu thập lại thống kê và kiểm tra hồi quy kế hoạch

Sau khi nâng cấp PostgreSQL, database có thể khởi động thành công và dữ liệu vẫn đầy đủ nhưng query performance thay đổi đáng kể. Một nguyên nhân quan trọng là optimizer cần statistics phù hợp với dữ liệu hiện tại và phiên bản mới. Planner dùng statistics để ước lượng số rows, selectivity, số distinct values, phân phối giá trị và chi phí của các lựa chọn thực thi. Nếu statistics chưa được thu thập lại, đã cũ hoặc không mô tả đúng data distribution, PostgreSQL có thể chọn sequential scan thay cho index scan, sai join order, tạo hash/sort lớn hoặc dùng parallelism không phù hợp.

Major upgrade còn thay đổi planner code, cost model behavior, executor, collation libraries, extension versions và một số defaults. Một query có thể có plan khác dù SQL và dữ liệu không đổi. Vì vậy, quy trình nâng cấp cần có hai công việc riêng: **thu thập lại statistics sau upgrade** và **kiểm tra hồi quy kế hoạch truy vấn**. ANALYZE tạo dữ liệu thống kê cho optimizer; plan regression testing xác định những query quan trọng có plan/latency thay đổi theo hướng bất lợi hay không.

Không nên đánh giá thành công chỉ bằng việc server start hoặc một vài smoke tests chạy được. Sau upgrade, workload cần được quan sát trong điều kiện đại diện: query parameters phổ biến và hiếm, concurrency, cache state, batch windows và data volume thực tế. So sánh phải bao gồm cả execution plan lẫn latency, rows, buffers, temporary I/O, WAL và tác động tới các query khác. Một plan khác chưa chắc là regression; planner có thể chọn plan mới tốt hơn. Ngược lại, plan giống nhau cũng không đảm bảo runtime giống nhau nếu hardware, storage, cache hoặc concurrency đã đổi.

Bài học thuộc chương **Nâng cấp** của module **Database Engine Relational PostgreSQL**. Nội dung trình bày vai trò của planner statistics, cách ANALYZE sau major upgrade, extended statistics, autovacuum/analyze, lưu baseline plans, so sánh trước/sau và xử lý các dạng plan regression.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích planner statistics ảnh hưởng tới cardinality estimates và execution plans.
- Phân biệt statistics catalog với runtime statistics.
- Hiểu vì sao cần thu thập lại statistics sau PostgreSQL major upgrade.
- Dùng ANALYZE, VACUUM (ANALYZE) và vacuumdb để cập nhật statistics.
- Lập lịch analyze theo database/table/partition và workload.
- Kiểm tra last_analyze, n_mod_since_analyze và analyze progress.
- Điều chỉnh statistics target và tạo extended statistics khi có bằng chứng.
- Lưu query fingerprints, representative parameters và EXPLAIN plans trước upgrade.
- So sánh estimated/actual rows, plan nodes, buffers, I/O và runtime sau upgrade.
- Phân biệt plan change hợp lý với performance regression.
- Điều tra regression do stale stats, skew, collation, index, config, extension hoặc prepared plans.
- Xây dựng rollout, acceptance criteria, rollback và monitoring sau nâng cấp.

## 2. Planner statistics là gì?

PostgreSQL planner ước lượng chi phí của nhiều execution strategies trước khi chọn một plan. Statistics giúp planner ước lượng lượng dữ liệu sẽ đi qua mỗi node.

### 2.1. Cardinality estimates

Planner cần dự đoán số rows mà scan, filter, join, aggregate và subquery sẽ trả về. Ước lượng sai có thể làm sai lựa chọn join method và join order.

### 2.2. Selectivity

Selectivity biểu diễn tỷ lệ rows thỏa predicate. Ví dụ filter trên một status phổ biến có selectivity khác filter trên một UUID hiếm.

### 2.3. Value distribution

Histogram bounds, most common values và null fraction mô tả cách dữ liệu phân bố trong một column.

### 2.4. Distinct values

Số distinct values giúp planner ước lượng group cardinality, distinct operations và join behavior.

### 2.5. Correlation

Correlation giữa thứ tự vật lý của rows và giá trị column có thể ảnh hưởng chi phí index access. Correlation giữa nhiều columns cũng ảnh hưởng selectivity estimation.

## 3. Statistics khác runtime statistics

PostgreSQL có nhiều hệ thống statistics với mục đích khác nhau. Cần phân biệt trước khi điều tra.

| Loại | Ví dụ | Mục đích |
|---|---|---|
| Planner statistics | pg_statistic, pg_stats | Ước lượng rows/selectivity |
| Table activity | pg_stat_user_tables | Scans, tuples, analyze/vacuum history |
| Query activity | pg_stat_statements | Calls, execution time, buffers |
| Session/wait | pg_stat_activity | Active sessions và wait events |
| I/O activity | pg_stat_io | I/O counters theo backend/context ở version hỗ trợ |
| Progress | pg_stat_progress_analyze | Theo dõi ANALYZE đang chạy ở version hỗ trợ |

### 3.1. Planner statistics

Được tạo bởi ANALYZE và lưu trong system catalogs. Planner đọc chúng khi lập plan.

### 3.2. Runtime statistics

Ghi nhận hoạt động thực tế như calls, elapsed time, blocks, sessions và waits. Chúng giúp biết query nào đang tốn tài nguyên.

### 3.3. Statistics reset

Một số runtime counters có thể reset hoặc mất khi restart. Planner statistics là catalog data và có lifecycle khác.

### 3.4. Không dùng pg_stat_statements thay cho ANALYZE

pg_stat_statements cho biết query đã chạy thế nào; nó không thay thế histogram/MCV statistics cần cho optimizer.

### 3.5. Cần kết hợp hai loại

Planner stats giúp giải thích quyết định plan; runtime stats cho biết quyết định đó có tạo ra hiệu năng tốt trong workload thực tế hay không.

## 4. Vì sao phải ANALYZE sau major upgrade?

Major upgrade có thể tạo cluster mới hoặc cập nhật catalog/system metadata theo cách khiến optimizer statistics cũ không được mang sang như một phần đáng tin cậy của quá trình nâng cấp.

### 4.1. Statistics có thể không được chuyển

Với quy trình pg_upgrade, optimizer statistics cần được tạo lại trên cluster mới. Công cụ upgrade thường cung cấp hoặc hướng dẫn chạy analyze script sau khi upgrade.

### 4.2. Planner version đã thay đổi

Planner mới có thể có costing, cardinality estimation hoặc plan selection behavior khác. Statistics mới giúp planner có input phù hợp với cluster mới.

### 4.3. Extension và type changes

Extension upgrade, custom types, operator classes, collations hoặc function definitions có thể ảnh hưởng selectivity/ordering semantics. Statistics cần được tạo lại sau khi objects tương thích.

### 4.4. Data có thể đã thay đổi

Trong quá trình upgrade/cutover, backfill, logical replication hoặc ETL có thể làm data distribution khác baseline. ANALYZE phải phản ánh dữ liệu tại target.

### 4.5. Không mở toàn bộ workload trước khi đủ stats

Query quan trọng có thể nhận plan kém nếu planner chỉ có statistics thiếu hoặc mặc định. Xác định critical tables và analyze trước khi tăng traffic.

## 5. ANALYZE hoạt động như thế nào?

ANALYZE lấy sample rows từ table/partition, tính statistics cho các columns và lưu kết quả vào catalog.

~~~sql
ANALYZE;
~~~

### 5.1. Database-wide analyze

Không chỉ định relation sẽ phân tích các tables phù hợp trong current database. Có thể tốn thời gian trên database lớn.

### 5.2. Table-specific analyze

~~~sql
ANALYZE public.orders;
~~~

Dùng khi cần ưu tiên table quan trọng hoặc vừa backfill.

### 5.3. Column-specific analyze

~~~sql
ANALYZE public.orders (tenant_id, status, created_at);
~~~

Có thể tập trung vào columns quan trọng, nhưng cần bảo đảm các statistics khác không bị bỏ qua lâu dài.

### 5.4. VACUUM (ANALYZE)

~~~sql
VACUUM (ANALYZE) public.orders;
~~~

Kết hợp cleanup và statistics collection. VACUUM có mục tiêu riêng; không cần chạy VACUUM chỉ để lấy statistics nếu ANALYZE là đủ.

### 5.5. Analyze không khóa table như exclusive DDL

ANALYZE thường cho phép concurrent reads/writes, nhưng vẫn dùng I/O/CPU và có thể cạnh tranh tài nguyên. Lập lịch phù hợp với peak workload.

## 6. ANALYZE sau pg_upgrade

Sau major upgrade bằng pg_upgrade, cần chạy analyze trên cluster mới trước khi kết luận performance ổn định.

### 6.1. Đọc output của pg_upgrade

Kiểm tra thông báo và scripts được tạo trong working directory của upgrade. Làm theo đúng hướng dẫn của major version đang dùng.

### 6.2. analyze_new_cluster.sh

Một số quy trình pg_upgrade tạo script như analyze_new_cluster.sh để chạy analyze trên cluster mới. Kiểm tra file/script được tạo trong lần upgrade cụ thể, quyền thực thi và target cluster trước khi chạy.

### 6.3. vacuumdb --analyze-in-stages

Có thể dùng vacuumdb với tùy chọn analyze-in-stages để tạo statistics hữu ích nhanh ở giai đoạn đầu rồi tăng dần statistics target trong các giai đoạn tiếp theo.

~~~bash
vacuumdb --all --analyze-in-stages --jobs=4
~~~

Điều chỉnh jobs theo CPU, I/O headroom và workload. Kiểm tra tùy chọn trong vacuumdb đúng major version.

### 6.4. Ưu tiên databases/tables quan trọng

Nếu toàn cluster quá lớn để analyze ngay, ưu tiên critical databases và tables phục vụ login, transactions, routing, inventory hoặc workload có SLO chặt. Theo dõi phần còn lại tới khi hoàn tất.

### 6.5. Ghi lại tiến độ

Ghi database/table, start/end time, rows/size nếu có, errors và các tables còn pending. Không coi command khởi chạy thành công là toàn bộ analyze đã hoàn tất.

## 7. Analyze theo database, schema và table

Chọn phạm vi theo kích thước dữ liệu, độ quan trọng và thời gian maintenance cho phép.

### 7.1. Database hiện tại

~~~sql
ANALYZE;
~~~

Đơn giản cho database nhỏ hoặc khi có đủ maintenance window.

### 7.2. Danh sách tables cụ thể

~~~sql
ANALYZE public.customers;
ANALYZE public.orders;
ANALYZE public.order_items;
~~~

Ưu tiên theo critical query dependencies.

### 7.3. Schema scope

Có thể tạo danh sách relations từ catalogs rồi chạy ANALYZE theo từng relation. Không giả định một câu ANALYZE schema là syntax hợp lệ.

### 7.4. Table vừa bulk load

Sau COPY/import lớn, chạy ANALYZE cho tables bị ảnh hưởng để planner biết distribution mới.

### 7.5. Temporary tables

Temporary tables có statistics/session behavior riêng; application có thể cần ANALYZE sau khi populate trước query phức tạp.

## 8. Kiểm tra analyze history

pg_stat_user_tables và pg_stat_all_tables ghi nhận analyze activity cùng modification counters.

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_mod_since_analyze DESC NULLS LAST;
~~~

### 8.1. last_analyze

Thời điểm ANALYZE chạy thủ công gần nhất.

### 8.2. last_autoanalyze

Thời điểm autovacuum launcher/worker thực hiện auto-analyze gần nhất.

### 8.3. n_mod_since_analyze

Ước lượng số row modifications kể từ analyze gần nhất. Giá trị cao có thể chỉ ra statistics đã cũ tương đối so với workload.

### 8.4. n_live_tup

Ước lượng live tuples, không phải exact COUNT(*). Dùng để hiểu quy mô và autovacuum thresholds.

### 8.5. Không chỉ dựa vào timestamp

Một table vừa analyze nhưng sau đó bulk load hàng triệu rows có thể cần analyze lại. Xem modification count và data distribution changes.

## 9. Autovacuum và auto-analyze

Autovacuum tự động thực hiện vacuum/analyze theo thresholds và settings. Sau upgrade, auto-analyze có thể chưa kịp xử lý mọi tables trước khi traffic lớn quay lại.

### 9.1. Analyze threshold

Auto-analyze được kích hoạt khi modifications vượt threshold kết hợp với scale factor theo table size. Các settings và behavior thay đổi theo PostgreSQL version.

### 9.2. Global settings

Xem autovacuum_analyze_threshold và autovacuum_analyze_scale_factor cùng worker capacity.

### 9.3. Per-table settings

Có thể override scale factor/threshold cho tables lớn hoặc thay đổi nhanh:

~~~sql
ALTER TABLE public.orders
SET (autovacuum_analyze_scale_factor = 0.02);
~~~

Chỉ điều chỉnh khi workload và analyze cadence cho thấy cần thiết.

### 9.4. Worker capacity

autovacuum_max_workers, cost delay và I/O budget ảnh hưởng khả năng bắt kịp nhiều tables. Tăng workers có thể tăng I/O contention.

### 9.5. Autovacuum không thay thế post-upgrade plan

Không chờ một chu kỳ autovacuum tự nhiên nếu critical queries cần stats trước khi mở traffic. Chủ động analyze theo upgrade runbook.

## 10. Kiểm tra ANALYZE progress

Các PostgreSQL versions hỗ trợ progress reporting cho ANALYZE cung cấp view pg_stat_progress_analyze.

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS relation,
    phase,
    sample_blks_total,
    sample_blks_scanned,
    ext_stats_total,
    ext_stats_computed,
    child_tables_total,
    child_tables_done
FROM pg_stat_progress_analyze;
~~~

### 10.1. Phase

Cho biết analyze đang ở giai đoạn nào. Tên phases/columns cần xác nhận theo major version.

### 10.2. Sample blocks

sample_blks_total/scanned cho thấy tiến độ đọc sample blocks nếu được cung cấp bởi version.

### 10.3. Extended statistics

Các counters liên quan extended stats có thể giúp nhận biết công việc tạo multi-column statistics.

### 10.4. Partition children

Nếu analyze relation có partition children, progress có thể phản ánh số children đã xử lý theo version.

### 10.5. Progress không phải ETA chính xác

Sample size, I/O latency và relation characteristics khiến thời gian còn lại thay đổi. Dùng để quan sát, không hứa ETA từ một snapshot.

## 11. Statistics target và sample quality

default_statistics_target điều khiển mức chi tiết mặc định cho nhiều loại planner statistics. Target cao hơn thường cần sample lớn hơn và tăng analyze cost.

### 11.1. Default target

~~~sql
SHOW default_statistics_target;
~~~

Giá trị mặc định thường đủ cho nhiều columns, nhưng data skew mạnh có thể cần target riêng.

### 11.2. Column-specific target

~~~sql
ALTER TABLE public.orders
ALTER COLUMN status SET STATISTICS 500;

ANALYZE public.orders (status);
~~~

### 11.3. Target quá thấp

MCV/histogram có thể không mô tả đủ các values phổ biến/hiếm, khiến selectivity estimates kém.

### 11.4. Target quá cao

Analyze cần sample lớn hơn, tăng CPU/I/O và catalog storage. Tăng mọi columns không phải chiến lược mặc định.

### 11.5. Chọn columns theo query evidence

Ưu tiên columns xuất hiện trong predicates, joins, groupings và columns có skew. Đánh giá estimates/plans sau khi tăng target.

## 12. Đọc planner statistics qua pg_stats

pg_stats là view dễ đọc hơn catalog nội bộ pg_statistic.

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
  AND tablename = 'orders'
ORDER BY attname;
~~~

### 12.1. null_frac

Tỷ lệ NULL được ước lượng trong column. Predicate IS NULL phụ thuộc thông tin này.

### 12.2. n_distinct

Số distinct values ước lượng. Giá trị âm có thể biểu thị tỷ lệ distinct so với số rows.

### 12.3. most_common_vals/freqs

Danh sách values phổ biến và tần suất tương ứng. Có ích với skew và hot values.

### 12.4. histogram_bounds

Histogram mô tả phân phối phần values không thuộc MCV list. Nó hỗ trợ range selectivity estimates.

### 12.5. correlation

Correlation giữa thứ tự vật lý và giá trị column nằm trong khoảng -1 đến 1; giá trị gần tuyệt đối 1 có thể làm index access có locality tốt hơn theo chiều tương ứng.



## 13. Extended statistics cho correlated columns

Single-column statistics giả định độc lập trong nhiều ước lượng. Khi columns có dependencies hoặc correlated values, planner có thể nhân selectivities sai.

### 13.1. Ví dụ data correlation

Một bảng orders có tenant_id và region_id. Mỗi tenant chỉ thuộc một region; hai predicates không độc lập. Nếu planner coi chúng độc lập, estimated rows có thể thấp hơn nhiều so với actual rows.

### 13.2. Dependencies

Dependencies statistics mô tả functional dependencies giữa columns.

~~~sql
CREATE STATISTICS orders_tenant_region_dep
    (dependencies)
ON tenant_id, region_id
FROM public.orders;

ANALYZE public.orders;
~~~

### 13.3. N-distinct

N-distinct statistics cải thiện ước lượng số nhóm distinct của nhiều columns.

~~~sql
CREATE STATISTICS orders_tenant_status_nd
    (ndistinct)
ON tenant_id, status
FROM public.orders;

ANALYZE public.orders;
~~~

### 13.4. Most common combinations

MCV extended statistics lưu các combinations phổ biến của columns.

~~~sql
CREATE STATISTICS orders_tenant_status_mcv
    (mcv)
ON tenant_id, status
FROM public.orders;

ANALYZE public.orders;
~~~

### 13.5. Không tạo extended stats cho mọi cặp columns

Chỉ tạo khi query plans/estimates cho thấy correlation hoặc multi-column predicates gây sai lệch. Extended stats tăng analyze work và catalog footprint.

## 14. Expression statistics và expression indexes

Query có predicates trên expressions có thể cần statistics/index phù hợp với expression.

### 14.1. Expression index

~~~sql
CREATE INDEX idx_users_lower_email
ON public.users (lower(email));
~~~

Planner có thể dùng index khi query expression tương thích.

### 14.2. Statistics trên expression

PostgreSQL hỗ trợ statistics objects cho expressions ở các versions phù hợp:

~~~sql
CREATE STATISTICS users_lower_email_stats
ON (lower(email))
FROM public.users;

ANALYZE public.users;
~~~

### 14.3. Expression consistency

Expression trong query, index và statistics cần tương thích về function/operator semantics. Immutable requirements áp dụng cho index expressions; kiểm tra command-specific rules.

### 14.4. Functional transformations

Các predicates như date_trunc, lower, casts hoặc arithmetic có thể làm selectivity estimation khó hơn nếu planner không có statistics phù hợp.

### 14.5. Kiểm tra plan

Dùng EXPLAIN để xác nhận planner dùng index/statistics và actual rows có gần estimate hơn.

## 15. Partitioned tables và statistics

Partitioning thêm dimension về parent/child relations, partition pruning và data distribution khác nhau giữa partitions.

### 15.1. Parent và partitions

Kiểm tra statistics ở partitioned parent và leaf partitions theo major version. Đảm bảo analyze đã xử lý relations mà critical queries truy cập.

### 15.2. Skew giữa partitions

Một partition gần đây có thể chứa phần lớn hot rows, trong khi historical partitions rất lớn nhưng ít truy cập. Global assumptions có thể không mô tả mọi query.

### 15.3. Incremental data growth

New partition sau upgrade cần analyze sau khi load data. Đừng chờ auto-analyze nếu partition vừa được bulk populated và query ngay.

### 15.4. Partition pruning

EXPLAIN cần cho thấy partitions không liên quan được loại bỏ. Statistics tốt không sửa được query thiếu predicate trên partition key.

### 15.5. Parent-level planning

Kiểm tra plan ở parent relation với representative parameters; test trực tiếp leaf partition không thay thế plan của query production.

## 16. Statistics và collation changes

Major upgrade có thể đi kèm thay đổi libc/ICU collation provider hoặc collation version. Điều này có thể ảnh hưởng sort/equality order, indexes và planner behavior.

### 16.1. Collation version

Kiểm tra collation version metadata và warnings trong logs. Thay đổi collation semantics có thể yêu cầu REINDEX để index ordering phù hợp.

### 16.2. REINDEX trước workload

Nếu collation version mismatch yêu cầu rebuild indexes, thực hiện theo upgrade runbook trước khi đánh giá plan regression. ANALYZE không sửa index ordering.

### 16.3. Statistics sau reindex

Sau khi indexes được rebuild và schema/data đã ổn định, ANALYZE để planner có statistics phù hợp.

### 16.4. ICU/libc differences

Different collation providers/versions có thể thay đổi ordering và comparisons. Kiểm tra deployment OS/library versions và database collation definitions.

### 16.5. Tách hai vấn đề

Plan regression do stale statistics và incorrect index ordering là hai loại nguyên nhân khác nhau. Đừng cố giải quyết collation mismatch chỉ bằng tăng statistics target.

## 17. Thu thập baseline query trước upgrade

Để kiểm tra regression, cần biết query nào quan trọng và hoạt động ra sao trên cluster cũ.

### 17.1. Chọn representative workload

Lấy top queries theo total execution time, mean/p95 latency nếu tracing có, calls, rows, buffers, temp blocks và WAL.

### 17.2. Query fingerprints

Lưu normalized query text, queryid, application_name, database, role và workload class. Queryid có thể thay đổi giữa major versions; không dùng nó làm khóa đối chiếu duy nhất qua upgrade.

### 17.3. Representative parameters

Lưu parameter classes như tenant nhỏ/lớn, status phổ biến/hiếm, date range ngắn/dài và NULL/non-NULL. Tránh lưu sensitive literals không cần thiết.

### 17.4. Baseline EXPLAIN

Thu EXPLAIN (FORMAT JSON) hoặc TEXT với settings/buffers phù hợp. Với runtime measurements, dùng EXPLAIN ANALYZE trên staging/production theo policy an toàn.

### 17.5. Baseline environment

Lưu PostgreSQL version, extensions, schema/index definitions, planner settings, hardware/storage, collation versions và data size.

## 18. Chọn query cần regression testing

Không cần test mọi statement trong application; ưu tiên các query có business impact hoặc resource cost lớn.

### 18.1. High-frequency queries

Một query rất nhỏ nhưng chạy hàng triệu lần có thể chiếm đáng kể CPU và connection capacity.

### 18.2. High-total-time queries

Query có total execution time cao ảnh hưởng throughput tổng. Tối ưu nó có thể giải phóng capacity lớn.

### 18.3. Tail-latency queries

Các query hiếm nhưng p99/max rất cao có thể làm user-facing SLO fail hoặc giữ locks lâu.

### 18.4. Critical business paths

Login, checkout, payment, inventory, account lookup và transactional writes cần representative tests ngay cả khi pg_stat_statements chưa xếp chúng top.

### 18.5. Maintenance/reporting queries

ETL, reports, backup metadata, vacuum-sensitive queries và scheduled jobs cũng cần test vì có thể cạnh tranh với OLTP.

## 19. Lưu EXPLAIN plan trước và sau upgrade

EXPLAIN JSON giúp lưu plan có cấu trúc để diff, parse và hiển thị trong tooling.

~~~sql
EXPLAIN (FORMAT JSON, SETTINGS)
SELECT *
FROM public.orders
WHERE tenant_id = 42
  AND status = 'open'
  AND created_at >= DATE '2026-01-01';
~~~

### 19.1. FORMAT JSON

JSON giữ node types, costs, estimates, relation names, index names và plan properties có thể xử lý tự động.

### 19.2. SETTINGS

Ghi planner settings khác default có ảnh hưởng plan theo version. Lưu cả relevant GUCs ở session/server.

### 19.3. EXPLAIN ANALYZE

Trên staging, có thể chạy:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, WAL, SETTINGS, VERBOSE)
SELECT count(*)
FROM public.orders
WHERE status = 'open';
~~~

EXPLAIN ANALYZE thực thi query thật; với INSERT/UPDATE/DELETE hoặc functions có side effects, dùng transaction rollback chỉ khi semantics cho phép và hiểu external effects. Ưu tiên staging/clone cho tests.

### 19.4. Plan-only và runtime test

EXPLAIN FORMAT JSON không thực thi query; EXPLAIN ANALYZE đo actual runtime. Cần cả hai vì plan shape khác và runtime regression là hai tín hiệu khác nhau.

### 19.5. Normalize environment

Cùng role, search_path, parameters, planner settings, prepared statement mode và data snapshot giúp so sánh có ý nghĩa.

## 20. Đọc plan diff sau upgrade

Plan diff phải tập trung vào thay đổi có thể ảnh hưởng execution cost.

### 20.1. Node type changes

Seq Scan đổi thành Index Scan, Nested Loop đổi Hash Join hoặc parallel plan xuất hiện/mất đi. Không tự động đánh dấu mọi thay đổi là regression.

### 20.2. Join order

Planner có thể đổi thứ tự joins do cardinality/cost estimates khác. Kiểm tra intermediate rows và loops.

### 20.3. Estimated rows

So estimated rows trước/sau và actual rows. Estimate cải thiện có thể là plan change tốt dù node tree khác.

### 20.4. Cost estimates

Cost parameters/defaults hoặc planner changes có thể làm costs khác. Cost không phải runtime; không so sánh như milliseconds.

### 20.5. Buffers và temp usage

Runtime plans có thể cho thấy shared blocks, temp blocks và WAL khác nhau. Dùng chúng cùng latency và host metrics để xác nhận impact.

## 21. Plan regression là gì?

Plan regression là thay đổi execution strategy khiến một workload/query có performance hoặc resource impact xấu đi so với baseline trong điều kiện tương đương.

### 21.1. Latency regression

Query runtime hoặc p95/p99 tăng đáng kể, vượt SLO hoặc business threshold.

### 21.2. Resource regression

Query tiêu thụ nhiều CPU, reads, temp I/O, WAL hoặc memory hơn dù latency chưa tăng rõ do headroom còn lớn.

### 21.3. Concurrency regression

Plan mới giữ locks lâu hơn, mở nhiều workers hơn hoặc tạo queueing khiến các requests khác chậm.

### 21.4. Plan change không phải luôn regression

Planner có thể đổi sang plan mới nhanh hơn. Đánh giá theo measured workload, không chỉ diff node names.

### 21.5. Same plan không đảm bảo same performance

Hardware, OS cache, storage, data size, collation, concurrent load và cache warmth có thể thay runtime mà plan tree không đổi.

## 22. Cardinality estimate errors sau upgrade

Ước lượng rows sai là nguyên nhân phổ biến của bad plans.

### 22.1. Estimated vs actual

Trong EXPLAIN ANALYZE, so rows estimated với actual rows ở từng node, lưu ý loops để hiểu tổng work.

### 22.2. Sai lệch ở scan node

Có thể do stale stats, histogram không đủ chi tiết, data skew hoặc predicates trên expressions.

### 22.3. Sai lệch ở join node

Có thể do correlated join keys, duplicate distributions, FK relationships hoặc assumptions độc lập giữa columns.

### 22.4. Extended stats

Dependencies, ndistinct và MCV extended stats có thể cải thiện multi-column estimates. Tạo dựa trên evidence và analyze sau đó.

### 22.5. Data growth

Nếu data volume tăng nhiều trong upgrade/cutover, old statistics hoặc benchmark dataset nhỏ có thể không phản ánh production distribution.


## 23. Nguyên nhân thường gặp của plan regression

Sau upgrade, một query có thể đổi plan vì nhiều inputs thay đổi cùng lúc. Phân loại nguyên nhân giúp chọn đúng biện pháp.

### 23.1. Statistics thiếu hoặc cũ

Target cluster chưa ANALYZE, analyze chỉ chạy trên một số tables hoặc data thay đổi sau analyze.

### 23.2. Statistics target không đủ

MCV/histogram không mô tả skew quan trọng. Một column có distribution rất lệch có thể cần target riêng.

### 23.3. Correlated predicates

Planner giả định độc lập giữa columns nhưng thực tế chúng có dependencies. Extended statistics có thể giúp.

### 23.4. Index/schema differences

Index bị thiếu, invalid, chưa rebuild, operator class/collation khác hoặc schema migration thay đổi query path.

### 23.5. Planner settings và cost parameters

random_page_cost, effective_cache_size, work_mem, enable_* settings, parallel thresholds và JIT thresholds có thể khác giữa clusters.

### 23.6. Version behavior changes

Planner/executor improvements hoặc bug fixes có thể thay đổi plan selection. Đọc release notes đúng major versions và tái hiện trên staging.

### 23.7. Collation/type/extension changes

Ordering, comparison operators, custom selectivity functions và extension upgrade có thể ảnh hưởng plan hoặc index usage.

## 24. Prepared statements và generic/custom plans

Prepared statements có thể dùng generic plan tái sử dụng hoặc custom plan tối ưu theo parameter cụ thể. Điều này quan trọng khi parameter distribution skew.

### 24.1. Generic plan

Generic plan không phụ thuộc giá trị parameter cụ thể, giảm planning overhead nhưng có thể kém cho parameter extremes.

### 24.2. Custom plan

Custom plan được tạo theo parameter values cụ thể, có thể chọn tốt hơn cho skew nhưng tăng planning work.

### 24.3. plan_cache_mode

Có thể dùng plan_cache_mode để điều tra:

~~~sql
SHOW plan_cache_mode;
SET plan_cache_mode = force_custom_plan;
~~~

Đây là công cụ diagnostic/session-level; không đổi global policy nếu chưa benchmark toàn workload.

### 24.4. Parameter-sensitive testing

Test tenant lớn/nhỏ, date range rộng/hẹp, common/rare values và NULLs. Một parameter mẫu duy nhất không đủ.

### 24.5. Driver/pooler behavior

Prepared statement lifecycle phụ thuộc driver, pool mode và server-side prepare settings. Test đúng cách ứng dụng thực tế gửi statements.

## 25. Planner configuration sau upgrade

Không copy mù quáng toàn bộ postgresql.conf cũ sang major version mới hoặc environment khác.

### 25.1. Compare settings

Xuất pg_settings ở cả old/new clusters, so setting, unit, context, source và pending_restart.

### 25.2. Defaults may change

Một số defaults hoặc behavior có thể thay đổi giữa major versions. Dùng release notes và documentation target version.

### 25.3. effective_cache_size

Đây là planner estimate về cache available cho một query, không cấp phát memory. Đặt dựa trên shared buffers, OS cache và concurrency assumptions.

### 25.4. random_page_cost

Planner cost assumption về random page access. Giá trị phù hợp phụ thuộc storage/cache; không đặt thấp chỉ để ép index scans.

### 25.5. work_mem và parallelism

Work_mem/parallel settings ảnh hưởng memory và worker concurrency. Tuning plan một query có thể gây resource regression khi nhiều queries chạy đồng thời.

## 26. Query plan và index state sau upgrade

Plan regression có thể đến từ index availability/validity hoặc physical characteristics.

### 26.1. Kiểm tra index validity

~~~sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    i.indisvalid,
    i.indisready,
    i.indisunique
FROM pg_index AS i
JOIN pg_class AS idx ON idx.oid = i.indexrelid
JOIN pg_class AS tbl ON tbl.oid = i.indrelid
JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
WHERE ns.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY 1, 2, 3;
~~~

### 26.2. Collation mismatch

Kiểm tra collation version mismatch và reindex requirements trước khi kết luận optimizer không dùng index.

### 26.3. Operator classes

Index operator class/opfamily phải tương thích với operators query sử dụng. Extension/type upgrades có thể yêu cầu kiểm tra lại.

### 26.4. Index-only scans

Visibility map state và vacuum history ảnh hưởng heap fetches. Sau upgrade/bulk load, plan Index Only Scan có thể vẫn phải truy cập heap.

### 26.5. Index bloat và cache footprint

Index lớn hơn làm tăng pages cần đọc và cache footprint. So sánh relation sizes và I/O trước/sau.

## 27. Runtime regression testing

Plan comparison cần đi cùng runtime tests với workload đại diện.

### 27.1. Same data snapshot

Dùng bản copy hoặc snapshot tương đương của dataset. Nếu data differs, record khác biệt và tránh so sánh trực tiếp.

### 27.2. Same parameters

Dùng parameter sets giống nhau, gồm values phổ biến, hiếm, boundary và NULL khi hợp lệ.

### 27.3. Same concurrency

Test ở nhiều mức concurrency đại diện: single query, normal load, peak load và burst.

### 27.4. Cache conditions

Chạy warm-cache và cold-cache scenarios riêng. Không xóa OS cache trên production để tạo cold test.

### 27.5. Multiple runs

Lặp nhiều lần và so median/percentiles; loại bỏ run bị ảnh hưởng bởi startup, JIT warm-up hoặc background tasks nếu mục tiêu là steady state.

## 28. So sánh latency và resource consumption

Một plan có thể chạy nhanh hơn cho một query nhưng làm toàn hệ thống chậm hơn.

### 28.1. Query execution time

Ghi mean/median/p95/p99 và max theo query class. EXPLAIN ANALYZE là một sample, không thay distribution của production.

### 28.2. Planning time

Planning time có thể tăng do complex query, many partitions hoặc generic/custom plan behavior. Track planning time khi planning overhead quan trọng.

### 28.3. Buffer activity

So shared hit/read, local/temp blocks và heap fetches. Đọc counters theo cùng plan/test conditions.

### 28.4. CPU và I/O

Đo process CPU, storage latency/IOPS/throughput và wait events. Một plan có ít elapsed time trong cache test có thể tạo I/O burst trong production.

### 28.5. WAL và writes

Write query có thể tạo WAL/index work khác sau upgrade. So wal_bytes, rows modified, checkpoint pressure và replica lag.

## 29. pg_stat_statements trước/sau upgrade

Query statistics giúp ưu tiên regression investigations, nhưng cần chú ý reset và query identity changes.

~~~sql
SELECT
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_written,
    wal_bytes,
    query
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 50;
~~~

### 29.1. Export baseline

Lưu snapshots định kỳ trước upgrade, không đợi tới lúc bắt đầu downtime. Ghi stats_reset và interval.

### 29.2. Reset/epoch trên target

Sau cutover, bắt đầu một measurement interval mới hoặc ghi mốc stats reset. Không so counters cumulative có lịch sử khác nhau.

### 29.3. Query identity

queryid có thể thay đổi giữa PostgreSQL major versions, cấu hình hoặc query normalization behavior. Đối chiếu bằng normalized SQL/application context, không chỉ queryid.

### 29.4. Calls và total time

Query có total time tăng có thể do calls tăng thay vì mỗi execution chậm. So calls, mean time và latency distribution.

### 29.5. Query text sensitivity

Giữ query text và parameters theo privacy policy. Dùng normalized fingerprints và redact sensitive literals trong artifact/report.

## 30. auto_explain và slow query logging

Nếu regression chỉ xuất hiện dưới production parameter/load, logging có thể giúp thu execution plans.

### 30.1. log_min_duration_statement

Ghi các statements vượt ngưỡng duration. Chọn threshold để thu query quan trọng mà không tạo log volume quá lớn.

### 30.2. auto_explain

Extension auto_explain có thể log execution plans của statements vượt threshold. Cần preload/configuration và quyền truy cập logs.

### 30.3. log_analyze và buffers

Có thể bật analyze/buffers trong auto_explain theo policy; chúng tăng overhead. Thử trên staging và bật có chọn lọc.

### 30.4. Sampling và log volume

Không nhất thiết log mọi query với ANALYZE. Dùng thresholds, sampling và duration windows; monitor log storage/rotation.

### 30.5. Production safety

EXPLAIN logging phải không làm overload server hoặc lộ sensitive query details. Có emergency switch để tắt instrumentation nếu overhead tăng.

## 31. Phân tích regression theo query class

Không nên chỉ sửa top query một cách độc lập. Phân loại impact theo workload.

### 31.1. OLTP critical path

Test latency thấp, high-frequency lookups, updates và transaction boundaries. Kiểm tra lock duration, connection use và p99.

### 31.2. Reporting/OLAP

Test large scans, joins, sorts, aggregates, parallel workers và temp files. Đo completion time và impact tới foreground traffic.

### 31.3. Batch/ETL

Test rows/sec, WAL bytes, commit cadence, dead tuples, replication lag và restartability.

### 31.4. Administrative queries

Test catalog scans, monitoring dashboards, backup metadata và maintenance jobs. Những query này có thể bị ảnh hưởng bởi catalog/version changes.

### 31.5. Cross-workload impact

Một fix cho OLAP có thể tăng shared_buffers churn hoặc CPU và làm OLTP p99 xấu hơn. Acceptance criteria phải bao gồm cả workloads liên quan.

## 32. Ưu tiên regression theo severity

Đánh giá regression bằng business impact và resource impact, không chỉ tỷ lệ phần trăm.

| Mức | Ví dụ | Hành động |
|---|---|---|
| Critical | Checkout/payment vượt SLO hoặc timeout | Dừng rollout/rollback theo policy |
| High | Core query p99 tăng mạnh, replica lag vượt ngưỡng | Hotfix hoặc tune trước mở traffic |
| Medium | Report chậm nhưng trong completion window | Theo dõi và tối ưu có kế hoạch |
| Low | Plan khác nhưng latency/resource không xấu | Ghi nhận, không cần sửa ngay |

### 32.1. Absolute và relative change

Tăng từ 1 ms lên 2 ms là 100% nhưng có thể không đáng kể; tăng từ 2 s lên 3 s có thể phá SLO. Dùng cả absolute và relative impact.

### 32.2. Frequency

Query hiếm và query chạy hàng triệu lần có mức impact khác nhau. Tính total workload cost.

### 32.3. Business criticality

Ưu tiên payment, account, inventory và transaction integrity trước reports ít quan trọng.

### 32.4. Resource externalities

Một report tăng runtime 2 lần nhưng không ảnh hưởng OLTP khác với một query làm storage queue tăng cho toàn cluster.

### 32.5. Regression budget

Đặt thresholds trước upgrade: latency, throughput, errors, CPU, memory, I/O, WAL và replication lag. Không đặt ngưỡng sau khi đã thấy kết quả.



## 33. Quy trình thu thập statistics sau upgrade

Một quy trình có thứ tự giúp cluster mới có statistics trước khi nhận toàn bộ workload.

### 33.1. Hoàn tất upgrade mechanics

Xác nhận PostgreSQL mới khởi động, catalogs/extensions được upgrade, data directory đúng, logs sạch và database list đầy đủ.

### 33.2. Kiểm tra schema/index state

Xác nhận migration scripts, extension upgrades, indexes validity, collation requirements và objects cần tạo lại đã hoàn tất.

### 33.3. Chạy analyze stages

Dùng script do pg_upgrade tạo hoặc vacuumdb --analyze-in-stages theo version/tooling. Kiểm tra output và exit status.

### 33.4. Ưu tiên critical relations

Nếu analyze toàn bộ cần thời gian, chạy ANALYZE cho critical tables/columns trước khi mở workload tương ứng. Theo dõi remaining work.

### 33.5. Re-analyze sau data changes

Nếu cutover logical replication, backfill hoặc ETL tiếp tục ghi dữ liệu sau analyze, chạy analyze lại các relations có distribution thay đổi đáng kể.

## 34. Sequencing khi logical replication dùng cho upgrade

Một major upgrade dùng logical replication có thể có target nhận writes/copy data trong nhiều giai đoạn.

### 34.1. Analyze sau initial load

Sau khi initial copy hoàn tất và target data ổn định, analyze target tables để planner có statistics gần data distribution thật.

### 34.2. Cutover writes

Freeze source writes, để replication catch up và chuyển application sang target theo runbook.

### 34.3. Analyze sau catch-up

Nếu lượng changes sau initial analyze đáng kể hoặc skew thay đổi, chạy analyze lại critical tables sau catch-up.

### 34.4. Sequence state

Logical replication không tự đảm bảo sequence state được đồng bộ. Sequence alignment là task riêng trong upgrade runbook; không nhầm với planner statistics.

### 34.5. Validate before opening full traffic

Kiểm tra row counts/invariants, schema, indexes, sequences, planner stats và critical query plans trước khi tăng traffic.

## 35. Upgrade staging và rehearsal

Staging rehearsal là nơi xác định thời gian analyze và query regressions trước production.

### 35.1. Dataset representative

Dùng sanitized copy có kích thước và skew gần production. Dataset nhỏ có thể che giấu plan regressions.

### 35.2. Run full upgrade sequence

Thực hiện cùng pg_upgrade/logical migration, extension updates, collation checks, analyze và application deployment.

### 35.3. Capture analyze duration

Ghi thời gian theo database/table, CPU/I/O impact và concurrency. Dùng dữ liệu này để estimate maintenance window.

### 35.4. Plan regression suite

Chạy representative queries với parameters đã chọn và lưu EXPLAIN/ANALYZE results.

### 35.5. Rehearse remediation

Thử analyze target, tăng statistics target, extended stats, index correction và configuration changes trên staging. Ghi rõ cải thiện/regression.

## 36. Production cutover checklist cho statistics

### 36.1. Trước cutover

Lưu old cluster query baseline, critical query list, representative parameters, pg_settings, extensions, schema/index inventory và hardware/storage profile.

### 36.2. Sau upgrade

Chạy extension/schema/index/collation steps và ANALYZE theo plan. Kiểm tra analyze history/progress.

### 36.3. Trước traffic ramp

Chạy critical EXPLAIN plans và safe runtime tests. Xác nhận estimate quality và không có critical plan regression.

### 36.4. Trong traffic ramp

Tăng traffic theo stages, theo dõi p95/p99, throughput, CPU/I/O, waits, temp files, WAL và replica lag.

### 36.5. Sau full traffic

Tiếp tục thu query stats trong các peak windows và batch cycles. Một giờ đầu không đại diện cho month-end/weekly jobs.

## 37. Khi nào cần chạy ANALYZE lại?

ANALYZE không phải chỉ làm một lần sau upgrade.

### 37.1. Bulk load

Sau COPY/import hoặc large insert, analyze relations vừa load.

### 37.2. Backfill/update distribution

Backfill có thể thay đổi NULL fraction, MCV, histogram và correlation. Analyze sau khi batch hoàn tất.

### 37.3. Partition attach/detach

Sau khi thêm hoặc thay đổi partitions, cập nhật statistics theo relation scope và version behavior.

### 37.4. Sudden data skew

Tenant growth, status concentration hoặc hot keys có thể khiến statistics cũ không còn mô tả workload.

### 37.5. Plan estimates lệch

Nếu actual rows khác estimates đáng kể, kiểm tra stats freshness/targets và data correlation trước khi force plan.

## 38. Xử lý plan regression do stale statistics

Đây là nguyên nhân đầu tiên nên kiểm tra sau upgrade.

### 38.1. Xác nhận analyze history

Xem last_analyze/last_autoanalyze, n_mod_since_analyze và target relation.

### 38.2. Analyze đúng relation

Chạy ANALYZE table hoặc columns liên quan, sau đó lấy lại EXPLAIN với cùng parameters.

### 38.3. So estimated/actual rows

Nếu estimate cải thiện và plan/runtime trở lại tốt, stale/inadequate stats có thể là nguyên nhân.

### 38.4. Không analyze toàn cluster lặp lại vô điều kiện

Nếu chỉ một table có issue, analyze scope nhỏ giúp giảm I/O và tránh làm nhiễu hệ thống.

### 38.5. Ghi nhận kết quả

Ghi relation, analyze time, estimates trước/sau, plan change và runtime impact.

## 39. Xử lý regression do skew/correlation

Single-column stats có thể chưa đủ cho multi-column predicates.

### 39.1. Xác định predicates liên quan

Tìm các columns cùng xuất hiện trong WHERE/JOIN/GROUP BY và xác định business/data dependency.

### 39.2. Inspect pg_stats

Xem MCV, histogram, null fraction và distinct estimates cho từng column.

### 39.3. Tạo extended statistics

Chọn dependencies, ndistinct hoặc MCV phù hợp; chạy ANALYZE rồi kiểm tra plan.

### 39.4. Tăng target có chọn lọc

Nếu một column có nhiều MCV/skew quan trọng, tăng per-column statistics target và đo analyze cost.

### 39.5. Tránh ép join order trước khi sửa estimates

Planner hints/enable_* changes có thể che nguyên nhân. Sửa statistics/data model trước và benchmark lại.


## 40. Xử lý regression do index/collation

### 40.1. Kiểm tra index validity

Xem indisvalid/indisready và logs của upgrade/concurrent index operations.

### 40.2. Kiểm tra collation version

Nếu mismatch, làm theo reindex procedure phù hợp. Analyze không thay thế REINDEX.

### 40.3. Kiểm tra query expression

Query predicate phải khớp expression/operator/index design. Type casts và function wrappers có thể thay đổi index eligibility.

### 40.4. Kiểm tra visibility map

Nếu Index Only Scan có nhiều heap fetches, vacuum/visibility state có thể ảnh hưởng runtime.

### 40.5. Đánh giá write cost

Index bổ sung có thể chữa read regression nhưng tăng write latency/WAL. Test mixed workload trước khi chấp nhận.

## 41. Xử lý regression do planner settings/version behavior

### 41.1. Compare settings

So sánh planner-related GUCs và source values ở old/new clusters. Kiểm tra defaults đã thay đổi.

### 41.2. Test session-level alternatives

Dùng SET LOCAL hoặc session settings trong staging để thử cost parameters, work_mem, parallelism hoặc plan_cache_mode.

### 41.3. Đừng disable plan nodes toàn cục

enable_seqscan/enable_nestloop và các enable_* settings chủ yếu là diagnostic controls, không phải giải pháp tuning tổng quát.

### 41.4. Read release notes

Tìm planner, statistics, collation, executor và extension changes giữa major versions. Xác định behavior changes có liên quan.

### 41.5. Chỉ persist setting sau benchmark

Nếu một setting giúp query A nhưng làm query B chậm, đánh giá total workload/SLO trước khi đặt global.

## 42. Query plan stability và parameter sets

Một query có thể có nhiều plan phù hợp với parameter values khác nhau.

### 42.1. Parameter matrix

Tạo matrix common/rare, small/large tenant, short/long time range, null/non-null và boundary values.

### 42.2. Generic/custom behavior

Test cách prepared statements thực tế được prepare/execute qua driver và pooler. Dùng plan_cache_mode để diagnostic nếu cần.

### 42.3. Data distribution matrix

Test cả current partitions và historical partitions, tenant skew và table growth.

### 42.4. Plan stability không phải mục tiêu tuyệt đối

Một plan thay đổi theo parameter có thể là lựa chọn đúng. Mục tiêu là runtime predictable và SLO đạt.

### 42.5. Regression suite automation

Lưu query templates, safe parameters, environment metadata và expected performance bands. Tránh assert plan text chính xác nếu minor differences không ảnh hưởng hiệu năng.

## 43. Rollback và mitigation khi regression nghiêm trọng

Nếu critical workload không đạt SLO, cần quyết định theo upgrade rollback policy đã chuẩn bị.

### 43.1. Pause traffic ramp

Giữ traffic ở mức hiện tại hoặc chuyển sang restricted mode cho critical operations. Không tăng load khi regression chưa hiểu.

### 43.2. Quick mitigations

Có thể analyze, sửa query, điều chỉnh targeted statistics, khôi phục index hoặc áp dụng session-level config đã benchmark.

### 43.3. Rollback boundary

Major version upgrade có thể làm data directory/catalog không tương thích với old binaries. Rollback thường cần old cluster còn nguyên, snapshot/backup hoặc reverse replication plan.

### 43.4. Data writes sau cutover

Nếu target đã nhận writes, rollback về source có thể yêu cầu reverse replication hoặc reconciliation. Không chỉ đổi connection string.

### 43.5. Business decision

Nếu mitigation không đạt SLO, incident/change owner và business owner quyết định continue/rollback theo data safety, RPO và downtime impact.

## 44. Theo dõi sau upgrade qua nhiều chu kỳ

Performance ổn định cần được xác nhận qua peak và periodic jobs.

### 44.1. First-hour checks

Theo dõi critical query latency, active sessions, CPU/I/O, errors và replica lag ngay sau traffic ramp.

### 44.2. Daily peak

So sánh p95/p99 và throughput ở giờ cao điểm với baseline cùng traffic profile.

### 44.3. Batch windows

Chạy ETL/report/maintenance jobs và so completion time, WAL, temp files, checkpoint/vacuum behavior.

### 44.4. Weekly/month-end jobs

Một số regressions chỉ xuất hiện khi data range lớn hoặc concurrency theo mùa tăng. Chờ hoặc rehearsal các workload đó.

### 44.5. Closeout

Chỉ đóng upgrade performance follow-up khi acceptance thresholds đạt qua chu kỳ đại diện hoặc risk đã được owner chấp nhận.

## 45. Tài liệu và evidence cần lưu

Một performance baseline hữu ích cần đủ metadata để tái hiện.

### 45.1. Environment

PostgreSQL versions/builds, OS/kernel, CPU/RAM, storage class, network, extensions, collations và config snapshots.

### 45.2. Schema/data

DDL, indexes, partition layout, row counts/size estimates, data distribution và snapshot identifier.

### 45.3. Query artifacts

Normalized SQL, application/workload class, parameter class, EXPLAIN JSON, ANALYZE outputs và timing samples.

### 45.4. Statistics evidence

Analyze timestamps, statistics targets, pg_stats excerpts cần thiết và extended statistics definitions.

### 45.5. Decision record

Regression severity, owner, mitigation, benchmark result, approval và rollback decision.


## 46. Lab: ANALYZE sau major upgrade

Lab dùng hai PostgreSQL environments cùng một dataset representative, một phiên bản cũ và một phiên bản mới.

### 46.1. Chuẩn bị dataset

Tạo tables có data skew, tenant distribution, date ranges và indexes tương tự workload thực tế. Ghi snapshot identifier và table sizes.

### 46.2. Thu baseline ở old cluster

Chạy representative queries với parameter classes đã chọn. Lưu EXPLAIN JSON, EXPLAIN ANALYZE, buffers và runtime samples.

### 46.3. Thực hiện upgrade trên target

Dùng upgrade procedure đã rehearsal. Hoàn tất extension/catalog/schema/index/collation steps trước khi chạy benchmark.

### 46.4. Thu statistics

Chạy vacuumdb --analyze-in-stages hoặc analyze script phù hợp. Theo dõi duration, progress, analyze history và resource usage.

### 46.5. So sánh sau analyze

Chạy cùng query/parameters, so estimated rows, plan nodes, buffers, runtime và resource metrics. Ghi các query chưa đạt threshold.

## 47. Lab: phát hiện cardinality estimate regression

### 47.1. Tạo dữ liệu skew

Tạo bảng có một status rất phổ biến và nhiều status hiếm; thêm tenant_id có phân phối không đồng đều.

### 47.2. Chạy query với parameters khác nhau

Test status phổ biến/hiếm và tenant nhỏ/lớn. Ghi estimated rows và actual rows.

### 47.3. Tăng statistics target

Thử tăng target cho column skew, chạy ANALYZE và lấy lại plans.

### 47.4. Thử extended statistics

Tạo dependencies hoặc MCV statistics cho columns correlated, ANALYZE rồi so estimate accuracy.

### 47.5. Đánh giá trade-off

So analyze time, catalog stats size, plan behavior và runtime trên cả parameter matrix. Không chỉ chọn kết quả tốt nhất cho một value.

## 48. Lab: kiểm tra prepared statements

### 48.1. Chuẩn bị query parameterized

Dùng một query có predicate trên tenant_id/status với data skew rõ.

### 48.2. Chạy prepared executions

Thực hiện nhiều parameter values qua cùng connection/driver behavior tương tự production.

### 48.3. So generic/custom

Trong session lab, thử plan_cache_mode=force_generic_plan và force_custom_plan để quan sát khác biệt. Trả setting về mặc định sau thử nghiệm.

### 48.4. Thu EXPLAIN/runtime

So plan, planning time, execution time và buffers cho từng parameter class.

### 48.5. Chọn policy theo workload

Nếu custom plans tốt hơn cho skew nhưng planning overhead cao, đánh giá aggregate workload và driver behavior trước khi đổi policy.

## 49. Lab: regression suite trước/sau upgrade

### 49.1. Chọn query set

Chọn critical OLTP, high-total-time, tail-latency, reporting và batch queries.

### 49.2. Đóng gói test inputs

Lưu normalized SQL, parameter class, role, search_path, settings và expected data state.

### 49.3. Chạy trên old/new clusters

Giữ data, concurrency, cache conditions và hardware tương đương nhất có thể. Ghi rõ những khác biệt không thể loại bỏ.

### 49.4. So sánh có ngưỡng

So p50/p95/p99, throughput, error rate, plan shape, estimated/actual rows, buffers, temp blocks, WAL và CPU/I/O.

### 49.5. Lập regression report

Ghi query, impact, evidence, likely cause, mitigation, owner và acceptance/rollback decision.

## 50. Những lỗi thường gặp sau upgrade

1. Mở toàn bộ traffic trước khi ANALYZE các critical tables.
2. Cho rằng pg_upgrade đã chuyển đầy đủ optimizer statistics.
3. Chỉ chạy ANALYZE một lần rồi tiếp tục backfill/ETL làm data distribution đổi.
4. Chạy ANALYZE trên database nhưng bỏ sót tables/partitions quan trọng.
5. Chờ autovacuum auto-analyze trong khi query critical đang có plan xấu.
6. Tăng default_statistics_target cho mọi columns mà không đo analyze cost.
7. Bỏ qua correlated predicates và extended statistics.
8. Dùng pg_stat_statements queryid làm khóa duy nhất qua major versions.
9. So sánh cumulative counters có stats_reset khác nhau.
10. So plan costs như thể chúng là milliseconds.
11. Coi mọi plan shape change là regression.
12. Coi plan giống nhau là bảo đảm runtime giống nhau.
13. Chỉ test một parameter value và bỏ qua data skew.
14. Bỏ qua prepared statement generic/custom plan behavior.
15. Nhầm stale statistics với collation/index validity issue.
16. Chạy EXPLAIN ANALYZE DML trên production mà không đánh giá side effects.
17. Tăng work_mem để chữa một sort spill mà không tính concurrency.
18. Force index/join strategy trước khi sửa cardinality estimates.
19. Chỉ test OLTP mà quên batch/reporting/maintenance workloads.
20. Đóng upgrade ngay sau smoke test mà chưa qua peak/batch cycles.

## 51. Bài tập thực hành

### Bài 1 — Planner statistics

Planner statistics giúp PostgreSQL quyết định điều gì?

**Đáp án:** Ước lượng cardinality/selectivity và chi phí để chọn execution plan.

### Bài 2 — Runtime statistics

pg_stat_statements thay thế pg_stats được không?

**Đáp án:** Không; một view thống kê runtime query, view kia phản ánh planner statistics theo columns.

### Bài 3 — Major upgrade

Vì sao cần ANALYZE sau pg_upgrade?

**Đáp án:** Optimizer statistics cần được thu thập lại trên cluster mới để planner có inputs phù hợp.

### Bài 4 — Table analyze

Lệnh nào analyze một table?

**Đáp án:** ANALYZE schema.table.

### Bài 5 — Analyze stages

vacuumdb --analyze-in-stages có mục tiêu gì?

**Gợi ý:** Tạo statistics usable nhanh trước, sau đó tăng dần mức chi tiết.

### Bài 6 — n_mod_since_analyze

Column này giúp nhận biết điều gì?

**Đáp án:** Ước lượng số row modifications kể từ lần analyze gần nhất.

### Bài 7 — auto-analyze

Autovacuum auto-analyze có luôn chạy ngay sau bulk load không?

**Đáp án:** Không; nó phụ thuộc thresholds, scheduling và worker capacity.

### Bài 8 — Statistics target

Tăng target có trade-off nào?

**Đáp án:** Statistics chi tiết hơn nhưng analyze tốn sample/CPU/I/O và catalog space hơn.

### Bài 9 — MCV

most_common_vals/freqs dùng để làm gì?

**Đáp án:** Mô tả các giá trị phổ biến và tần suất của chúng.

### Bài 10 — Histogram

histogram_bounds hữu ích cho loại predicate nào?

**Đáp án:** Range predicates và selectivity estimation trên phân phối values.

### Bài 11 — Correlation

Column correlation trong pg_stats mô tả điều gì?

**Đáp án:** Mức liên hệ giữa thứ tự vật lý của rows và giá trị column.

### Bài 12 — Extended statistics

Khi nào dùng dependencies/MCV statistics?

**Gợi ý:** Khi nhiều columns correlated và planner ước lượng predicates kết hợp sai.

### Bài 13 — n-distinct

Extended n-distinct statistics cải thiện ước lượng gì?

**Đáp án:** Số distinct combinations/groups của nhiều columns.

### Bài 14 — Partition

Vì sao cần analyze partition mới sau bulk load?

**Đáp án:** Planner cần statistics phản ánh data distribution trong partition.

### Bài 15 — Collation

ANALYZE có sửa index collation mismatch không?

**Đáp án:** Không; cần xử lý collation version/reindex theo upgrade procedure.

### Bài 16 — EXPLAIN JSON

FORMAT JSON có lợi ích gì?

**Đáp án:** Plan có cấu trúc để lưu, parse và diff tự động.

### Bài 17 — Cost

Planner cost=5000 có nghĩa query mất 5 giây không?

**Đáp án:** Không; cost là đơn vị tương đối, không phải elapsed milliseconds.

### Bài 18 — Actual rows

Estimated rows khác actual rows lớn gợi ý điều gì?

**Gợi ý:** Statistics thiếu/cũ, skew, correlation hoặc parameter-sensitive behavior.

### Bài 19 — queryid

Có nên match query chỉ bằng queryid giữa major versions không?

**Đáp án:** Không; queryid có thể thay đổi. Cần normalized SQL/application context.

### Bài 20 — Generic plan

Generic plan có nhược điểm gì với data skew?

**Đáp án:** Nó không tối ưu riêng theo từng parameter value.

### Bài 21 — plan_cache_mode

Dùng force_custom_plan trong production ngay có an toàn không?

**Đáp án:** Không; trước tiên dùng để diagnostic/benchmark, sau đó đánh giá planning overhead.

### Bài 22 — pg_stat_statements

Calls tăng gấp đôi nhưng mean time giữ nguyên, total time thay đổi thế nào?

**Đáp án:** Total execution time xấp xỉ tăng gấp đôi nếu các điều kiện khác không đổi.

### Bài 23 — EXPLAIN ANALYZE

EXPLAIN ANALYZE có thực thi statement không?

**Đáp án:** Có; cần cân nhắc side effects và workload impact.

### Bài 24 — auto_explain

auto_explain giúp điều tra điều gì?

**Đáp án:** Ghi execution plans của statements theo threshold/configuration.

### Bài 25 — Plan regression

Plan node đổi từ Seq Scan sang Index Scan có luôn tốt hơn không?

**Đáp án:** Không; cần đo rows, buffers, runtime và workload impact.

### Bài 26 — Statistics after backfill

Vì sao cần analyze lại sau backfill lớn?

**Đáp án:** Backfill có thể thay đổi null fraction, histogram, MCV và correlations.

### Bài 27 — Regression severity

Một report tăng runtime nhưng vẫn trong completion window cần rollback không?

**Đáp án:** Không nhất thiết; đánh giá business impact và acceptance thresholds.

### Bài 28 — Rollback

Sau major upgrade, có thể chỉ khởi động old binaries trên data directory mới không?

**Đáp án:** Không; cần rollback topology/backup/reverse replication phù hợp.

### Bài 29 — Benchmark

Vì sao phải giữ parameter distribution và concurrency tương đương?

**Đáp án:** Để so sánh workload đại diện và tránh quy nhầm khác biệt input thành regression.

### Bài 30 — Acceptance

Nêu các nhóm metrics cần theo dõi trong traffic ramp.

**Gợi ý:** p95/p99, throughput, errors, CPU/I/O, waits, temp files, WAL và replication lag.

## 52. Checklist thu thập statistics sau upgrade

- [ ] Đã xác nhận upgrade/cutover hoàn tất?
- [ ] Extension, schema, indexes và collation steps đã xong?
- [ ] Đã đọc pg_upgrade output/scripts cho cluster cụ thể?
- [ ] Đã chạy analyze script hoặc vacuumdb --analyze-in-stages?
- [ ] Critical tables/partitions đã được ưu tiên?
- [ ] Bulk load/backfill/cutover changes đã được tính?
- [ ] last_analyze/last_autoanalyze và n_mod_since_analyze đã xem?
- [ ] Statistics targets/extended stats quan trọng đã được kiểm tra?
- [ ] Analyze errors/pending relations đã được ghi?
- [ ] Resource impact và completion time đã được ghi?
- [ ] Traffic chỉ mở theo criteria sau khi stats critical sẵn sàng?

## 53. Checklist plan regression testing

- [ ] Old-version baseline có normalized SQL và query context?
- [ ] Representative parameter matrix có skew/boundary values?
- [ ] Old/new environment metadata được lưu?
- [ ] EXPLAIN JSON/ANALYZE artifacts đã được capture an toàn?
- [ ] Estimated/actual rows, loops và join order được so sánh?
- [ ] Buffers, temp I/O, WAL và planning time được xem?
- [ ] Runtime p50/p95/p99 và throughput được benchmark?
- [ ] Queryid changes giữa versions không làm sai matching?
- [ ] Generic/custom prepared plan behavior đã test?
- [ ] Collation/index validity và extension compatibility đã xác nhận?
- [ ] Critical OLTP/reporting/batch workloads đều có coverage?
- [ ] Severity/acceptance/rollback thresholds được xác định?
- [ ] Regression decisions có evidence, owner và action?

## 54. Bảng tra cứu nhanh

| Thành phần | Mục đích |
|---|---|
| ANALYZE | Thu thập planner statistics |
| VACUUM (ANALYZE) | Cleanup và cập nhật statistics |
| vacuumdb --analyze-in-stages | Analyze nhiều giai đoạn sau upgrade |
| pg_stats | View đọc planner statistics |
| pg_statistic | Catalog lưu planner statistics |
| pg_stat_user_tables | Analyze history/modification estimates |
| n_mod_since_analyze | Modifications từ lần analyze gần nhất |
| default_statistics_target | Default statistics detail level |
| ALTER COLUMN SET STATISTICS | Statistics target riêng cho column |
| CREATE STATISTICS | Extended statistics object |
| dependencies | Multi-column functional dependencies |
| ndistinct | Distinct combinations |
| mcv | Most common combinations |
| pg_stat_progress_analyze | Analyze progress ở versions hỗ trợ |
| EXPLAIN FORMAT JSON | Structured estimated plan |
| EXPLAIN ANALYZE | Actual execution measurements |
| pg_stat_statements | Query workload aggregates |
| auto_explain | Log execution plans theo điều kiện |
| queryid | Normalized query identifier, có thể thay đổi giữa versions |
| generic plan | Plan không phụ thuộc parameter cụ thể |
| custom plan | Plan được tạo theo parameter values |
| plan_cache_mode | Điều khiển generic/custom plan behavior |
| Plan regression | Plan/runtime thay đổi gây performance degradation |
| pg_upgrade | Major version upgrade utility |

## 55. Kết luận

**Sau major upgrade, hãy thu thập lại planner statistics và kiểm tra query plans trước khi coi performance đã ổn định.** ANALYZE cung cấp thông tin về null fraction, MCV, histogram, distinct values và correlation để planner ước lượng rows/selectivity. vacuumdb --analyze-in-stages hoặc script analyze do pg_upgrade tạo có thể giúp tạo statistics theo giai đoạn; critical tables cần được ưu tiên nếu traffic phải mở sớm. Sau bulk load, backfill hoặc partition changes, cần analyze lại khi data distribution đã thay đổi.

Plan regression testing cần bắt đầu từ baseline trước upgrade: query fingerprints, parameter classes, schema/index, planner settings và EXPLAIN artifacts. Sau upgrade, so estimated/actual rows, join order, node types, buffers, temp I/O, WAL, planning time và runtime percentiles. Queryid có thể thay đổi giữa major versions; đối chiếu bằng normalized SQL và application context. Một plan khác không tự động là regression, và một plan giống nhau không đảm bảo runtime giống nhau.

Khi phát hiện regression, điều tra theo thứ tự: statistics freshness/targets, skew/correlation, index validity/collation, prepared generic/custom plans, planner settings và version behavior. Kiểm chứng bằng workload/data/parameters/concurrency đại diện; thay một biến mỗi lần và đặt rollback criteria. Theo dõi sau cutover qua peak và batch cycles, không chỉ smoke tests ban đầu.

Nguyên tắc nâng cấp: **ANALYZE để planner hiểu dữ liệu mới, benchmark để hiểu hành vi mới, và chỉ chấp nhận upgrade khi critical workloads đáp ứng SLO với evidence có thể tái hiện.**


## 23. Nguyên nhân thường gặp của plan regression

Sau upgrade, một query có thể đổi plan vì nhiều inputs thay đổi cùng lúc. Phân loại nguyên nhân giúp chọn đúng biện pháp.

### 23.1. Statistics thiếu hoặc cũ

Target cluster chưa ANALYZE, analyze chỉ chạy trên một số tables hoặc data thay đổi sau analyze.

### 23.2. Statistics target không đủ

MCV/histogram không mô tả skew quan trọng. Một column có distribution rất lệch có thể cần target riêng.

### 23.3. Correlated predicates

Planner giả định độc lập giữa columns nhưng thực tế chúng có dependencies. Extended statistics có thể giúp.

### 23.4. Index/schema differences

Index bị thiếu, invalid, chưa rebuild, operator class/collation khác hoặc schema migration thay đổi query path.

### 23.5. Planner settings và cost parameters

random_page_cost, effective_cache_size, work_mem, enable_* settings, parallel thresholds và JIT thresholds có thể khác giữa clusters.

### 23.6. Version behavior changes

Planner/executor improvements hoặc bug fixes có thể thay đổi plan selection. Đọc release notes đúng major versions và tái hiện trên staging.

### 23.7. Collation/type/extension changes

Ordering, comparison operators, custom selectivity functions và extension upgrade có thể ảnh hưởng plan hoặc index usage.

## 24. Prepared statements và generic/custom plans

Prepared statements có thể dùng generic plan tái sử dụng hoặc custom plan tối ưu theo parameter cụ thể. Điều này quan trọng khi parameter distribution skew.

### 24.1. Generic plan

Generic plan không phụ thuộc giá trị parameter cụ thể, giảm planning overhead nhưng có thể kém cho parameter extremes.

### 24.2. Custom plan

Custom plan được tạo theo parameter values cụ thể, có thể chọn tốt hơn cho skew nhưng tăng planning work.

### 24.3. plan_cache_mode

Có thể dùng plan_cache_mode để điều tra:

~~~sql
SHOW plan_cache_mode;
SET plan_cache_mode = force_custom_plan;
~~~

Đây là công cụ diagnostic/session-level; không đổi global policy nếu chưa benchmark toàn workload.

### 24.4. Parameter-sensitive testing

Test tenant lớn/nhỏ, date range rộng/hẹp, common/rare values và NULLs. Một parameter mẫu duy nhất không đủ.

### 24.5. Driver/pooler behavior

Prepared statement lifecycle phụ thuộc driver, pool mode và server-side prepare settings. Test đúng cách ứng dụng thực tế gửi statements.

## 25. Planner configuration sau upgrade

Không copy mù quáng toàn bộ postgresql.conf cũ sang major version mới hoặc environment khác.

### 25.1. Compare settings

Xuất pg_settings ở cả old/new clusters, so setting, unit, context, source và pending_restart.

### 25.2. Defaults may change

Một số defaults hoặc behavior có thể thay đổi giữa major versions. Dùng release notes và documentation target version.

### 25.3. effective_cache_size

Đây là planner estimate về cache available cho một query, không cấp phát memory. Đặt dựa trên shared buffers, OS cache và concurrency assumptions.

### 25.4. random_page_cost

Planner cost assumption về random page access. Giá trị phù hợp phụ thuộc storage/cache; không đặt thấp chỉ để ép index scans.

### 25.5. work_mem và parallelism

Work_mem/parallel settings ảnh hưởng memory và worker concurrency. Tuning plan một query có thể gây resource regression khi nhiều queries chạy đồng thời.

## 26. Query plan và index state sau upgrade

Plan regression có thể đến từ index availability/validity hoặc physical characteristics.

### 26.1. Kiểm tra index validity

~~~sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    i.indisvalid,
    i.indisready,
    i.indisunique
FROM pg_index AS i
JOIN pg_class AS idx ON idx.oid = i.indexrelid
JOIN pg_class AS tbl ON tbl.oid = i.indrelid
JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
WHERE ns.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY 1, 2, 3;
~~~

### 26.2. Collation mismatch

Kiểm tra collation version mismatch và reindex requirements trước khi kết luận optimizer không dùng index.

### 26.3. Operator classes

Index operator class/opfamily phải tương thích với operators query sử dụng. Extension/type upgrades có thể yêu cầu kiểm tra lại.

### 26.4. Index-only scans

Visibility map state và vacuum history ảnh hưởng heap fetches. Sau upgrade/bulk load, plan Index Only Scan có thể vẫn phải truy cập heap.

### 26.5. Index bloat và cache footprint

Index lớn hơn làm tăng pages cần đọc và cache footprint. So sánh relation sizes và I/O trước/sau.

## 27. Runtime regression testing

Plan comparison cần đi cùng runtime tests với workload đại diện.

### 27.1. Same data snapshot

Dùng bản copy hoặc snapshot tương đương của dataset. Nếu data differs, record khác biệt và tránh so sánh trực tiếp.

### 27.2. Same parameters

Dùng parameter sets giống nhau, gồm values phổ biến, hiếm, boundary và NULL khi hợp lệ.

### 27.3. Same concurrency

Test ở nhiều mức concurrency đại diện: single query, normal load, peak load và burst.

### 27.4. Cache conditions

Chạy warm-cache và cold-cache scenarios riêng. Không xóa OS cache trên production để tạo cold test.

### 27.5. Multiple runs

Lặp nhiều lần và so median/percentiles; loại bỏ run bị ảnh hưởng bởi startup, JIT warm-up hoặc background tasks nếu mục tiêu là steady state.

## 28. So sánh latency và resource consumption

Một plan có thể chạy nhanh hơn cho một query nhưng làm toàn hệ thống chậm hơn.

### 28.1. Query execution time

Ghi mean/median/p95/p99 và max theo query class. EXPLAIN ANALYZE là một sample, không thay distribution của production.

### 28.2. Planning time

Planning time có thể tăng do complex query, many partitions hoặc generic/custom plan behavior. Track planning time khi planning overhead quan trọng.

### 28.3. Buffer activity

So shared hit/read, local/temp blocks và heap fetches. Đọc counters theo cùng plan/test conditions.

### 28.4. CPU và I/O

Đo process CPU, storage latency/IOPS/throughput và wait events. Một plan có ít elapsed time trong cache test có thể tạo I/O burst trong production.

### 28.5. WAL và writes

Write query có thể tạo WAL/index work khác sau upgrade. So wal_bytes, rows modified, checkpoint pressure và replica lag.

## 29. pg_stat_statements trước/sau upgrade

Query statistics giúp ưu tiên regression investigations, nhưng cần chú ý reset và query identity changes.

~~~sql
SELECT
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_written,
    wal_bytes,
    query
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 50;
~~~

### 29.1. Export baseline

Lưu snapshots định kỳ trước upgrade, không đợi tới lúc bắt đầu downtime. Ghi stats_reset và interval.

### 29.2. Reset/epoch trên target

Sau cutover, bắt đầu một measurement interval mới hoặc ghi mốc stats reset. Không so counters cumulative có lịch sử khác nhau.

### 29.3. Query identity

queryid có thể thay đổi giữa PostgreSQL major versions, cấu hình hoặc query normalization behavior. Đối chiếu bằng normalized SQL/application context, không chỉ queryid.

### 29.4. Calls và total time

Query có total time tăng có thể do calls tăng thay vì mỗi execution chậm. So calls, mean time và latency distribution.

### 29.5. Query text sensitivity

Giữ query text và parameters theo privacy policy. Dùng normalized fingerprints và redact sensitive literals trong artifact/report.

## 30. auto_explain và slow query logging

Nếu regression chỉ xuất hiện dưới production parameter/load, logging có thể giúp thu execution plans.

### 30.1. log_min_duration_statement

Ghi các statements vượt ngưỡng duration. Chọn threshold để thu query quan trọng mà không tạo log volume quá lớn.

### 30.2. auto_explain

Extension auto_explain có thể log execution plans của statements vượt threshold. Cần preload/configuration và quyền truy cập logs.

### 30.3. log_analyze và buffers

Có thể bật analyze/buffers trong auto_explain theo policy; chúng tăng overhead. Thử trên staging và bật có chọn lọc.

### 30.4. Sampling và log volume

Không nhất thiết log mọi query với ANALYZE. Dùng thresholds, sampling và duration windows; monitor log storage/rotation.

### 30.5. Production safety

EXPLAIN logging phải không làm overload server hoặc lộ sensitive query details. Có emergency switch để tắt instrumentation nếu overhead tăng.

## 31. Phân tích regression theo query class

Không nên chỉ sửa top query một cách độc lập. Phân loại impact theo workload.

### 31.1. OLTP critical path

Test latency thấp, high-frequency lookups, updates và transaction boundaries. Kiểm tra lock duration, connection use và p99.

### 31.2. Reporting/OLAP

Test large scans, joins, sorts, aggregates, parallel workers và temp files. Đo completion time và impact tới foreground traffic.

### 31.3. Batch/ETL

Test rows/sec, WAL bytes, commit cadence, dead tuples, replication lag và restartability.

### 31.4. Administrative queries

Test catalog scans, monitoring dashboards, backup metadata và maintenance jobs. Những query này có thể bị ảnh hưởng bởi catalog/version changes.

### 31.5. Cross-workload impact

Một fix cho OLAP có thể tăng shared_buffers churn hoặc CPU và làm OLTP p99 xấu hơn. Acceptance criteria phải bao gồm cả workloads liên quan.

## 32. Ưu tiên regression theo severity

Đánh giá regression bằng business impact và resource impact, không chỉ tỷ lệ phần trăm.

| Mức | Ví dụ | Hành động |
|---|---|---|
| Critical | Checkout/payment vượt SLO hoặc timeout | Dừng rollout/rollback theo policy |
| High | Core query p99 tăng mạnh, replica lag vượt ngưỡng | Hotfix hoặc tune trước mở traffic |
| Medium | Report chậm nhưng trong completion window | Theo dõi và tối ưu có kế hoạch |
| Low | Plan khác nhưng latency/resource không xấu | Ghi nhận, không cần sửa ngay |

### 32.1. Absolute và relative change

Tăng từ 1 ms lên 2 ms là 100% nhưng có thể không đáng kể; tăng từ 2 s lên 3 s có thể phá SLO. Dùng cả absolute và relative impact.

### 32.2. Frequency

Query hiếm và query chạy hàng triệu lần có mức impact khác nhau. Tính total workload cost.

### 32.3. Business criticality

Ưu tiên payment, account, inventory và transaction integrity trước reports ít quan trọng.

### 32.4. Resource externalities

Một report tăng runtime 2 lần nhưng không ảnh hưởng OLTP khác với một query làm storage queue tăng cho toàn cluster.

### 32.5. Regression budget

Đặt thresholds trước upgrade: latency, throughput, errors, CPU, memory, I/O, WAL và replication lag. Không đặt ngưỡng sau khi đã thấy kết quả.


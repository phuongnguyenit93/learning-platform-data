# Insert-heavy workload và bảng có tốc độ thay đổi lớn

Các bảng PostgreSQL có lượng INSERT lớn hoặc thường xuyên UPDATE/DELETE cần chiến lược VACUUM phù hợp với tốc độ phát sinh dữ liệu. Một bảng append-only có thể tạo rất ít dead tuples nhưng vẫn cần vacuum để cập nhật visibility map và freeze tuple cũ. Một bảng có churn cao lại tạo nhiều tuple versions, dead index entries và áp lực cleanup. Cùng một cấu hình autovacuum có thể hoạt động tốt với bảng nhỏ nhưng không theo kịp bảng hàng tỷ rows hoặc bảng nhận hàng chục nghìn thay đổi mỗi giây.

Tối ưu VACUUM cho workload lớn không đơn giản là tăng số worker hay hạ scale factor. Cần hiểu **loại thay đổi đang diễn ra**, **ngưỡng vacuum/analyze**, **khả năng I/O và WAL**, **HOT updates và indexes**, **transaction horizon**, **partitioning/retention**, rồi đo hiệu quả bằng thống kê thực tế. Mục tiêu là giữ dead tuples và XID age trong giới hạn, duy trì planner statistics, tránh bloat không cần thiết và không làm ảnh hưởng latency của ứng dụng.

Bài học thuộc chương **VACUUM** trong module **Database Engine Relational PostgreSQL**. Nội dung tập trung vào bảng insert-heavy, bảng có tốc độ thay đổi lớn, cách autovacuum phản ứng với INSERT, cách tune theo từng bảng và phương pháp giám sát/kiểm thử trên workload gần thực tế.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt insert-heavy, update-heavy, delete-heavy và mixed-churn workloads.
- Hiểu vì sao INSERT nhiều không đồng nghĩa dead tuples nhiều.
- Giải thích insert-triggered autovacuum và vai trò của visibility map/freeze.
- Tính ngưỡng vacuum/analyze từ threshold và scale factor.
- Nhận diện HOT updates, index churn, TOAST và fillfactor.
- Tune autovacuum theo từng bảng dựa trên row count, write rate và I/O budget.
- Hiểu tác động của vacuum workers, cost delay, work memory và WAL.
- Tìm transaction lâu, replication slots và standby feedback đang giữ cleanup horizon.
- Dùng partitioning/retention cho bảng time-series hoặc dữ liệu hết hạn.
- Theo dõi thống kê, tiến độ vacuum, lock waits và XID age.
- Xây dựng lab insert-heavy/high-churn và đọc kết quả.
- Lập kế hoạch bảo trì mà không gây nghẽn connection pool hoặc disk.

## 2. Phân loại workload trước khi tune

Không phải mọi bảng lớn đều có cùng vấn đề. Hãy phân loại theo cách dữ liệu được ghi và vòng đời của rows.

| Workload | Đặc điểm | Áp lực chính |
|---|---|---|
| Insert-heavy, append-only | INSERT liên tục, ít UPDATE/DELETE | Visibility map, freeze, indexes, WAL, disk growth |
| Update-heavy | Một row bị sửa nhiều lần | Dead tuples, HOT eligibility, index churn |
| Delete-heavy | Xóa hàng loạt hoặc liên tục | Dead tuples, cleanup, index bloat, free space |
| Mixed churn | INSERT/UPDATE/DELETE đều cao | Vacuum throughput, indexes, WAL, I/O |
| Bulk load | Nạp lượng dữ liệu lớn theo đợt | Analyze, index build, checkpoints, autovacuum overlap |
| Time-series | Dữ liệu theo ngày/tháng, retention | Partition lifecycle, vacuum theo partition |
| Mostly-static | Ít thay đổi sau khi tạo | Freeze, visibility map, statistics khi có thay đổi |

### 2.1. Insert-heavy không nhất thiết có dead tuple nhiều

Một INSERT mới tạo tuple version hiện hành. Nếu không có UPDATE/DELETE, nó không tạo một version cũ cần dọn. Tuy nhiên, các pages mới có thể chưa được đánh dấu all-visible, và tuples vẫn cần được freeze theo thời gian.

### 2.2. Update-heavy tạo nhiều phiên bản

Một UPDATE thường tạo version mới và khiến version cũ trở thành dead khi không còn snapshot nào cần nó. Cùng một row được update hàng trăm lần có thể tạo lượng cleanup lớn dù số logical rows không đổi.

### 2.3. Delete-heavy tạo cleanup backlog

DELETE đánh dấu tuple cũ không còn hiện hành. VACUUM cần xác định thời điểm version đó không còn được snapshot nào cần trước khi thu hồi chỗ.

### 2.4. Bulk load khác continuous writes

Một batch INSERT vài trăm triệu rows trong khoảng ngắn có thể cần ANALYZE sau load và chiến lược indexes/constraints riêng. Continuous INSERT lại cần autovacuum chạy ổn định theo thời gian.

### 2.5. Đo write rate theo cửa sổ thời gian

Một snapshot `n_tup_ins=10000000` không nói tốc độ nếu không biết thời gian quan sát. Hãy so sánh delta counters giữa hai thời điểm và ghi nhận workload window.

## 3. Insert-heavy table vẫn cần VACUUM vì sao?

VACUUM không chỉ dọn dead tuples. Với bảng append-only, nó còn giúp quản lý visibility map và freeze transaction IDs.

### 3.1. Visibility map và index-only scans

PostgreSQL có thể đánh dấu heap pages là all-visible khi mọi tuples trên page visible với tất cả transactions hiện tại. Index-only scan có thể tránh đọc heap cho các pages được đánh dấu phù hợp.

### 3.2. INSERT làm page mới chưa all-visible

Khi thêm rows, page có dữ liệu mới chưa thể mặc định all-visible. Nếu bảng chỉ insert, không có delete, vẫn có thể cần vacuum để xác nhận page visibility sau khi các điều kiện snapshot cho phép.

### 3.3. Freeze XIDs

Tuple có transaction ID cũ dần cần được freeze để bảo vệ khỏi XID wraparound. Bảng append-only vẫn có tuples cũ dù không có dead rows.

### 3.4. Insert-triggered autovacuum

PostgreSQL có các tham số riêng cho vacuum được kích hoạt bởi INSERT:

- `autovacuum_vacuum_insert_threshold`
- `autovacuum_vacuum_insert_scale_factor`

Các tham số này giúp vacuum một bảng ngay cả khi dead tuple threshold chưa đạt, vì insert-heavy table vẫn có nhu cầu cập nhật visibility/freeze.

### 3.5. Không nhầm insert-triggered vacuum với cleanup dead tuples

Một lần vacuum do INSERT kích hoạt có thể không làm `n_dead_tup` giảm đáng kể nếu bảng vốn ít dead tuples. Nó vẫn có thể có ích cho visibility map và freeze.

## 4. Ngưỡng autovacuum cho INSERT

Ngưỡng insert-triggered vacuum được tính theo dạng tổng quát:

~~~text
insert vacuum threshold =
    autovacuum_vacuum_insert_threshold
    + autovacuum_vacuum_insert_scale_factor
      * estimated_table_tuples
~~~

### 4.1. Threshold là phần cố định

`autovacuum_vacuum_insert_threshold` đặt số tuples insert tối thiểu trước khi vacuum được kích hoạt theo insert count. Giá trị `-1` có thể dùng để vô hiệu hóa insert-triggered vacuum; cần xem tài liệu phiên bản và chính sách cụ thể trước khi thay đổi.

### 4.2. Scale factor phụ thuộc quy mô bảng

`autovacuum_vacuum_insert_scale_factor` nhân với số tuples ước lượng của table. Một bảng lớn có thể cần rất nhiều inserts trước khi đạt threshold nếu scale factor quá cao.

### 4.3. Ví dụ tính ngưỡng

Giả sử một bảng có khoảng 10 triệu rows, insert threshold là 1.000 và insert scale factor là 0,1:

~~~text
threshold = 1.000 + 0,1 * 10.000.000
          = 1.001.000 inserts
~~~

Đây là phép tính minh họa. Số rows và counters thực tế do PostgreSQL ước lượng/ghi nhận; hãy đọc setting đang áp dụng trên server.

### 4.4. Bảng lớn có thể phải đợi quá lâu

Nếu một bảng có hàng trăm triệu rows, scale factor 0,2 có thể tạo ra ngưỡng rất lớn. Điều này có thể làm vacuum insert-triggered ít thường xuyên hơn mong muốn.

### 4.5. Không hạ scale factor theo cảm tính

Vacuum sớm hơn có thể tăng I/O và worker load. Chọn threshold theo insert rate, tỷ lệ pages cần vacuum, nhu cầu index-only scan, freeze age và headroom storage.

## 5. Ngưỡng autovacuum cho UPDATE/DELETE

Vacuum do dead tuples thường dùng công thức:

~~~text
vacuum threshold =
    autovacuum_vacuum_threshold
    + autovacuum_vacuum_scale_factor
      * estimated_table_tuples
~~~

### 5.1. Dead tuple estimate

`n_dead_tup` trong `pg_stat_user_tables` là ước lượng, không phải phép đếm vật lý chính xác tức thời.

### 5.2. Bảng nhỏ và bảng lớn

Với bảng nhỏ, threshold cố định có thể chi phối. Với bảng lớn, scale factor thường chi phối tổng ngưỡng.

### 5.3. Update/delete burst

Một đợt update/delete lớn có thể làm dead tuple count tăng nhanh hơn tốc độ autovacuum. Khi đó cần xem vacuum có bị trễ do worker, I/O, lock hoặc xmin horizon.

### 5.4. Không gộp mọi counters thành một metric

Insert-triggered vacuum và dead-tuple-triggered vacuum phản ánh nhu cầu khác nhau. Quan sát riêng `n_ins_since_vacuum`, `n_dead_tup` và `n_mod_since_analyze` nếu phiên bản cung cấp.

### 5.5. Threshold chỉ là trigger

Đạt threshold không bảo đảm worker bắt đầu ngay lập tức. Launcher cần phát hiện table, worker slot phải sẵn sàng, lock phải lấy được và tài nguyên phải cho phép.

## 6. ANALYZE cũng quan trọng trong workload lớn

Vacuum cleanup và ANALYZE statistics là hai nhiệm vụ khác nhau.

~~~text
INSERT / UPDATE / DELETE
          |
          +----> vacuum thresholds
          |         |
          |         v
          |      VACUUM
          |      cleanup / visibility / freeze
          |
          +----> analyze thresholds
                    |
                    v
                 ANALYZE
                 planner statistics
~~~

### 6.1. Insert-heavy làm phân bố dữ liệu thay đổi

Nếu dữ liệu mới tập trung vào một vùng giá trị hoặc một partition, statistics cũ có thể không phản ánh phân bố hiện tại. Query planner có thể chọn plan không phù hợp.

### 6.2. n_mod_since_analyze

`n_mod_since_analyze` giúp theo dõi số thay đổi kể từ lần analyze gần nhất trong những phiên bản có counter này.

### 6.3. Analyze threshold

Các tham số `autovacuum_analyze_threshold` và `autovacuum_analyze_scale_factor` điều khiển ngưỡng analyze. Chúng độc lập với vacuum threshold.

### 6.4. Bulk load nên xem xét ANALYZE sau load

Sau một batch load lớn, planner có thể cần statistics mới ngay cả khi autovacuum chưa đến lượt. Chạy ANALYZE có mục tiêu sau load có thể giúp query plan phù hợp hơn.

### 6.5. Extended statistics

Nếu query phụ thuộc tương quan giữa nhiều cột, extended statistics (`CREATE STATISTICS`) có thể hữu ích. VACUUM không tự tạo các statistics objects này.

## 7. Update-heavy table và HOT updates

HOT (*Heap-Only Tuple*) là một tối ưu giúp một số UPDATE tránh tạo index entries mới.

### 7.1. Điều kiện tổng quát

HOT update có thể xảy ra khi các cột được UPDATE không thuộc những index cần cập nhật và có đủ chỗ trống phù hợp trên cùng heap page. Chi tiết còn phụ thuộc loại index và phiên bản PostgreSQL.

### 7.2. Vì sao HOT giúp giảm churn?

Nếu HOT update thành công, PostgreSQL có thể giữ chain tuple versions trong heap page mà không phải tạo index entries mới cho mỗi update. Điều này giảm index write amplification và công việc cleanup index.

### 7.3. Index trên cột thường xuyên thay đổi

Nếu status, last_seen hoặc counter được index, cập nhật các cột đó có thể khiến HOT không đủ điều kiện và tăng index churn.

### 7.4. Không bỏ index chỉ để ép HOT

Index có thể cần thiết cho query/constraint. Hãy đo query workload, index usage và update patterns trước khi thay đổi schema.

### 7.5. Theo dõi HOT ratio

`n_tup_hot_upd` và `n_tup_upd` trong `pg_stat_user_tables` cho phép ước lượng tỷ lệ HOT updates:

~~~text
HOT ratio = n_tup_hot_upd / n_tup_upd
~~~

Dùng delta counters trong một khoảng thời gian nếu muốn đo theo workload window; counter tích lũy từ lần reset stats có thể gây hiểu nhầm.

## 8. Fillfactor cho bảng có UPDATE thường xuyên

Fillfactor quy định mức độ lấp đầy mục tiêu của page khi tạo/rewrite relation. Để lại free space có thể tăng cơ hội HOT update.

~~~sql
CREATE TABLE app.sessions (
    session_id UUID PRIMARY KEY,
    status TEXT NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL
) WITH (fillfactor = 80);
~~~

### 8.1. Fillfactor thấp hơn tạo khoảng trống

Ví dụ fillfactor 80 hướng tới giữ một phần page trống trong các thao tác tạo/rewrite page phù hợp. Nó không phải cam kết mỗi page luôn đúng 20% free space.

### 8.2. Hữu ích cho update-heavy patterns

Nếu UPDATE sửa các cột không được index và row có thể ở lại page, free space có thể giúp HOT updates.

### 8.3. Không nhất thiết có lợi cho append-only table

Một bảng chỉ INSERT có thể không hưởng lợi từ fillfactor thấp; page density thấp làm tăng dung lượng và I/O cho cùng số rows.

### 8.4. ALTER TABLE SET fillfactor không tự rewrite dữ liệu hiện tại

Thay storage parameter ảnh hưởng những lần page được tạo/rewrite sau đó theo semantics; để áp dụng đầy đủ cho pages cũ có thể cần rewrite/maintenance có chủ đích.

### 8.5. Đo bằng workload

So sánh HOT ratio, index writes, heap size, query latency và disk footprint trên staging trước khi áp dụng production.

## 9. Indexes làm tăng chi phí của workload churn

Mỗi index có thể làm INSERT/UPDATE/DELETE tốn thêm công việc.

### 9.1. INSERT phải cập nhật indexes

Một row mới thường cần index entries cho các indexes liên quan. Bảng có nhiều indexes có thể có write amplification đáng kể.

### 9.2. UPDATE cột index có thể tạo index churn

Khi indexed column thay đổi, PostgreSQL có thể cần cập nhật index entries; điều này làm tăng dead index entries và cleanup workload.

### 9.3. Index-only scan cần visibility map

Dù index có chứa các cột SELECT, PostgreSQL vẫn cần biết heap page all-visible để bỏ qua heap visibility check. VACUUM giúp duy trì visibility map.

### 9.4. Không xóa indexes không dùng chỉ dựa trên một lần thống kê

Index có thể được dùng bởi constraint, rare queries hoặc maintenance jobs. Xem `pg_stat_user_indexes`, query plans và workload đủ dài.

### 9.5. Partial/covering indexes

Có thể giảm index footprint nếu predicate và truy vấn phù hợp. Nhưng mỗi index mới vẫn tăng chi phí writes và maintenance.

## 10. TOAST và rows có payload lớn

Các giá trị lớn như JSONB, TEXT, BYTEA có thể được lưu ngoài heap qua TOAST.

### 10.1. Update payload lớn có thể tốn nhiều hơn update cột nhỏ

Nếu mỗi UPDATE thay một JSONB document lớn, có thể tạo nhiều TOAST chunks mới và để lại chunks cũ cần cleanup.

### 10.2. HOT eligibility có thể thay đổi

Các cột được index và tuple layout ảnh hưởng HOT. Payload columns không được index có thể vẫn cho phép HOT trong một số trường hợp, nhưng TOAST write volume vẫn tồn tại.

### 10.3. Không lưu toàn bộ event history trong một row mutable nếu cần audit

Một mô hình append-only event table và một current-state table có thể tách lịch sử immutable khỏi trạng thái hay cập nhật. Chọn theo query/consistency requirements.

### 10.4. Đo total relation size

`pg_total_relation_size` bao gồm indexes và TOAST liên quan, trong khi `pg_relation_size` chỉ nhìn main relation. Dùng đúng metric khi điều tra.

### 10.5. Compression không thay thế vacuum

TOAST compression giảm storage cho values, nhưng không làm biến mất tuple versions cũ do UPDATE/DELETE.

## 11. Insert-heavy, WAL và checkpoint pressure

INSERT lớn tạo WAL và ghi data pages. VACUUM cũng có thể tạo WAL cho các thay đổi metadata/data cleanup liên quan.

### 11.1. WAL không được VACUUM dọn hộ

WAL retention/archiving/replication có cơ chế riêng. VACUUM không phải lệnh dọn WAL files cũ.

### 11.2. Nhiều indexes tăng WAL

Mỗi index cần duy trì entries cho rows mới. Schema có quá nhiều indexes có thể làm WAL generation và write amplification tăng.

### 11.3. Checkpoints và storage throughput

Bulk insert có thể đẩy nhiều dirty pages; checkpoint settings và storage performance ảnh hưởng write latency. Đừng quy mọi disk I/O cao cho VACUUM.

### 11.4. WAL archive lag

Nếu archiver hoặc remote storage không theo kịp, WAL có thể tích tụ. Cần monitor `pg_stat_archiver`, archive failures và dung lượng filesystem.

### 11.5. Replication lag

High write rate có thể khiến standby replay lag. Lag có thể ảnh hưởng backup/failover RPO và, nếu feedback/slots giữ xmin, còn liên quan vacuum horizon.

## 12. Partitioning cho insert-heavy/time-series tables

Với dữ liệu theo thời gian, partitioning giúp giới hạn maintenance và retention theo từng phần.

~~~text
events (partitioned parent)
   |
   +-- events_2026_10
   +-- events_2026_11
   +-- events_2026_12
~~~

### 12.1. Inserts định tuyến tới partition

Partition key cần phù hợp với dữ liệu và truy vấn. Partition pruning giúp query chỉ đọc các partitions liên quan khi predicate phù hợp.

### 12.2. Vacuum theo leaf partitions

Mỗi partition là relation riêng. Churn và autovacuum activity có thể khác nhau giữa partition mới (insert-heavy) và partition cũ (read-mostly).

### 12.3. Retention bằng detach/drop

Khi dữ liệu hết hạn, detach/drop partition có thể hiệu quả hơn DELETE hàng triệu rows. Tuy nhiên, DDL locks, FK dependencies, indexes và archive policies phải được tính đến.

### 12.4. Partition mới có thể chưa có statistics phù hợp

Sau khi tạo/nạp partition mới, cần xem ANALYZE và planner behavior. Parent-level statistics có thể cần cập nhật tùy PostgreSQL version.

### 12.5. Tránh tạo quá nhiều partitions nhỏ

Quá nhiều partitions làm tăng planning/catalog overhead, maintenance coordination và operational complexity. Chọn granularity theo retention/query/write rate.

## 13. Bulk load: chiến lược trước, trong và sau import

Một lần nạp dữ liệu lớn có thể tạo workload khác hẳn traffic bình thường.

### 13.1. Trước load

- Ước lượng dung lượng rows, indexes và WAL.
- Kiểm tra disk headroom và replication/archiver capacity.
- Xác định có thể nạp vào staging table hay không.
- Chọn COPY/batch size và transaction boundaries phù hợp.
- Xem xét thứ tự tạo indexes/constraints theo mục tiêu và ràng buộc consistency.

### 13.2. Trong load

- Theo dõi insert rate, WAL generation, checkpoint và replication lag.
- Không tắt autovacuum toàn cluster chỉ để tăng tốc.
- Giới hạn concurrency để tránh saturate disk/CPU.
- Giám sát lock, transaction age và error rate.

### 13.3. Sau load

- Chạy ANALYZE khi cần để planner biết phân bố mới.
- Kiểm tra identity/sequence nếu explicit IDs được nạp.
- Xem vacuum insert thresholds và visibility map behavior.
- Xác minh indexes/constraints và số rows.
- Theo dõi autovacuum sau load để bảo đảm không có backlog.

### 13.4. Index creation trước hay sau load?

Với bulk load vào table mới, tạo indexes sau load đôi khi hiệu quả hơn tạo từng index entry cho mỗi row. Nhưng constraints, uniqueness validation, availability và downtime requirements có thể quyết định lựa chọn khác.

### 13.5. Không gộp toàn bộ load vào transaction vô hạn

Transaction quá dài giữ snapshot/locks, tạo rollback lớn và có thể ảnh hưởng cleanup. Chia batch theo semantics nghiệp vụ và khả năng restart.

## 14. Tuning autovacuum theo từng loại bảng

| Loại bảng | Trọng tâm tuning |
|---|---|
| Append-only log | Insert threshold, freeze, visibility, partition retention |
| Current-state table | Dead tuple threshold, HOT, fillfactor, index churn |
| Session/presence | UPDATE churn, TTL cleanup, short transactions |
| Audit/event | Insert rate, indexes, WAL, partitioning |
| Large JSON document | TOAST, update pattern, payload size |
| Reference table | Freeze/ANALYZE khi có thay đổi, ít vacuum churn |
| Bulk staging | Analyze sau load, dọn/drop staging đúng vòng đời |

### 14.1. Per-table storage parameters cho INSERT

~~~sql
ALTER TABLE telemetry.events
SET (
    autovacuum_vacuum_insert_threshold = 5000,
    autovacuum_vacuum_insert_scale_factor = 0.03
);
~~~

Các số chỉ minh họa. Đặt threshold thấp hơn khiến insert-triggered vacuum được cân nhắc sớm hơn; cần đánh giá I/O và worker capacity.

### 14.2. Bảng update-heavy

~~~sql
ALTER TABLE app.sessions
SET (
    autovacuum_vacuum_threshold = 500,
    autovacuum_vacuum_scale_factor = 0.01
);
~~~

Scale factor nhỏ hơn có thể giảm dead tuple backlog, nhưng vacuum thường xuyên hơn.

### 14.3. Bảng cần analyze thường xuyên

~~~sql
ALTER TABLE app.orders
SET (
    autovacuum_analyze_threshold = 500,
    autovacuum_analyze_scale_factor = 0.01
);
~~~

Phù hợp khi planner statistics cần được cập nhật sớm sau thay đổi. Đánh giá chi phí analyze và query plans.

### 14.4. Xem reloptions hiện tại

~~~sql
SELECT
    n.nspname,
    c.relname,
    c.reloptions
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname IN ('telemetry', 'app')
  AND c.relkind IN ('r', 'm', 'p')
ORDER BY 1, 2;
~~~

### 14.5. Reset một số options

~~~sql
ALTER TABLE telemetry.events
RESET (
    autovacuum_vacuum_insert_threshold,
    autovacuum_vacuum_insert_scale_factor
);
~~~

Reset chỉ những options cần trở về server defaults. Không dùng lệnh này để xóa mọi reloptions không liên quan.

## 15. Vacuum cost, workers và I/O budget

Autovacuum cần tài nguyên để đọc pages, thu thập dead tuple identifiers và cleanup indexes. Tuning cần cân bằng tốc độ vacuum với workload foreground.

### 15.1. autovacuum_max_workers

Tăng worker slots có thể xử lý nhiều tables đồng thời. Nhưng tổng CPU, RAM và I/O cũng tăng.

### 15.2. autovacuum_naptime

Điều khiển khoảng chờ giữa các lần launcher kiểm tra. Giảm naptime không bảo đảm mỗi table được vacuum ngay nếu không có worker capacity hoặc threshold chưa đạt.

### 15.3. Vacuum cost limit/delay

Cơ chế cost-based throttling giới hạn tốc độ hoạt động vacuum để giảm ảnh hưởng workload. Đặt quá chậm có thể làm vacuum không theo kịp churn.

### 15.4. autovacuum_work_mem

Bộ nhớ làm việc ảnh hưởng khả năng giữ dead tuple identifiers và số vòng index cleanup. Cần tính tổng memory nếu nhiều workers chạy đồng thời.

### 15.5. Per-worker và global resource budget

Đừng chỉ tăng workers mà không xem disk throughput, memory, IOPS, WAL, CPU và latency. Tuning phải được đánh giá trên cả cluster.

## 16. Transaction horizon: blocker thường bị bỏ sót

Ngay cả khi threshold đã đạt và worker có sẵn, VACUUM không thể thu hồi versions còn cần cho snapshot cũ.

### 16.1. Long-running transaction

Một transaction mở lâu có thể giữ `backend_xmin` cũ, khiến dead tuples tiếp tục được giữ lại.

### 16.2. Idle in transaction

Connection đã chạy BEGIN nhưng đang idle vẫn có thể giữ snapshot. Đây là lỗi application lifecycle phổ biến.

### 16.3. Replication slot xmin

Logical replication slots có thể giữ `xmin/catalog_xmin`, làm vacuum không dọn được một số tuple/catalog versions.

### 16.4. Hot standby feedback

Standby feedback có thể ngăn cleanup làm query trên standby bị conflict, nhưng đánh đổi bằng việc giữ versions trên primary lâu hơn.

### 16.5. Không thể tune threshold để vượt qua horizon

Hạ scale factor hoặc tăng workers không thể xóa tuples mà PostgreSQL vẫn phải giữ vì visibility semantics. Hãy tìm root cause của horizon trước.

## 17. Monitoring: đo tốc độ thay đổi

`pg_stat_user_tables` cung cấp các counters hữu ích:

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_tup_hot_upd,
    n_mod_since_analyze,
    n_ins_since_vacuum,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze,
    autovacuum_count
FROM pg_stat_user_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n_tup_ins DESC
LIMIT 30;
~~~

Một số columns phụ thuộc phiên bản PostgreSQL. Hãy xem schema view trên server thật trước khi triển khai query giám sát.

### 17.1. Counters tích lũy

Các counters có thể reset theo stats reset/restart/version/config. Lưu hai snapshots cách nhau một khoảng thời gian để tính delta.

### 17.2. Insert rate

~~~text
insert rate = delta(n_tup_ins) / elapsed_seconds
~~~

### 17.3. Update/Delete rate

~~~text
change rate = (delta(n_tup_upd) + delta(n_tup_del))
              / elapsed_seconds
~~~

Đây là counters của operations, không phải số logical rows duy nhất bị thay đổi.

### 17.4. HOT ratio

~~~text
HOT ratio = delta(n_tup_hot_upd) / delta(n_tup_upd)
~~~

Nếu update count bằng zero thì ratio không xác định; không chia cho zero.

### 17.5. Dead tuple ratio chỉ là tín hiệu

Có thể xem `n_dead_tup / (n_live_tup + n_dead_tup)` như một ước lượng thô, nhưng không dùng nó làm tỷ lệ bloat vật lý chính xác.

## 18. Monitoring: kích thước và free space

~~~sql
SELECT
    s.schemaname,
    s.relname,
    s.n_live_tup,
    s.n_dead_tup,
    pg_size_pretty(
        pg_relation_size(
            format('%I.%I', s.schemaname, s.relname)::regclass
        )
    ) AS heap_size,
    pg_size_pretty(
        pg_indexes_size(
            format('%I.%I', s.schemaname, s.relname)::regclass
        )
    ) AS indexes_size,
    pg_size_pretty(
        pg_total_relation_size(
            format('%I.%I', s.schemaname, s.relname)::regclass
        )
    ) AS total_size
FROM pg_stat_user_tables AS s
ORDER BY pg_total_relation_size(
    format('%I.%I', s.schemaname, s.relname)::regclass
) DESC
LIMIT 30;
~~~

### 18.1. Heap và indexes

Một bảng insert-heavy có thể tăng index size nhanh hơn dự kiến nếu có nhiều indexes.

### 18.2. TOAST

Nếu payload lớn, total size có thể bị chi phối bởi TOAST relation; cần nhìn total relation size.

### 18.3. Free space map không phải số bloat tuyệt đối

Free pages có thể được reuse. Không nên mặc định mọi free space đều phải compact.

### 18.4. pgstattuple

Extension `pgstattuple` có thể cung cấp phân tích sâu hơn về live/dead/free space nhưng có chi phí scan và yêu cầu quyền/cài extension. Dùng theo kế hoạch.

### 18.5. Theo dõi theo thời gian

Một chart size hằng ngày cùng insert/update/delete rate và autovacuum history hữu ích hơn một ảnh chụp đơn lẻ.

## 19. Monitoring: autovacuum workers và progress

~~~sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    left(query, 160) AS query_sample
FROM pg_stat_activity
WHERE query LIKE 'autovacuum:%'
   OR backend_type = 'autovacuum worker'
ORDER BY query_start;
~~~

### 19.1. pg_stat_progress_vacuum

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS relation,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed,
    index_vacuum_count
FROM pg_stat_progress_vacuum;
~~~

### 19.2. Phase và tiến độ

VACUUM có thể đi qua heap scan, index vacuum, heap vacuum, index cleanup và final cleanup. Một phase lâu không tự chứng minh worker bị treo.

### 19.3. Lock waits

Kết hợp `pg_locks`, `pg_stat_activity` và `pg_blocking_pids(pid)` để xác định blocker. Worker có thể chờ lock do DDL hoặc maintenance khác.

### 19.4. Progress view không phải history

Progress view chỉ phản ánh operations đang chạy; lưu logs/metrics nếu cần lịch sử thời gian.

### 19.5. Quyền giám sát

Một số cột/query text có thể bị hạn chế tùy role và version. Dùng role monitor phù hợp, không cấp superuser chỉ để dashboard đọc mọi thứ.

## 20. Monitoring: XID age và replication horizon

Tuổi XID theo database:

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;
~~~

Replication slots:

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    xmin,
    catalog_xmin,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
~~~

### 20.1. XID age phải có alert

Không chỉ kiểm tra dead tuples; bảng append-only ít dead tuples vẫn cần freeze.

### 20.2. Slot inactive không tự vô hại

Một slot inactive có thể giữ WAL/xmin lâu nếu consumer đã mất hoặc ngừng chạy.

### 20.3. WAL disk và tuple horizon

`restart_lsn` liên quan WAL retention; `xmin/catalog_xmin` liên quan vacuum cleanup horizon. Theo dõi riêng từng loại.

### 20.4. Standby lag

Kiểm tra replication status/lag và feedback configuration. Một standby chậm có thể ảnh hưởng cả WAL retention lẫn vacuum horizon.

### 20.5. Không drop slot để chữa bloat mà không xác nhận owner

Drop slot có thể phá replication consumer hoặc logical decoding workflow. Phải có kế hoạch rebuild/resnapshot.

## 21. Tránh các thao tác làm autovacuum không theo kịp

### 21.1. Transactions quá dài

Chia batch và commit theo ranh giới nghiệp vụ. Không giữ transaction mở khi ứng dụng chờ người dùng hoặc gọi API bên ngoài.

### 21.2. Một transaction bulk update quá lớn

Batch update có thể giảm transaction lifetime và rollback footprint, nhưng cần thiết kế idempotency, ordering và consistency.

### 21.3. Nhiều workers cạnh tranh

Tăng worker count khi I/O đã saturated có thể làm foreground workload chậm hơn mà vacuum throughput không cải thiện.

### 21.4. Quá nhiều indexes

Rà soát indexes trùng lặp/ít dùng với evidence. Mỗi index thêm write/cleanup cost.

### 21.5. Delete retention theo row

Với time-series, cân nhắc partition detach/drop để tránh tạo hàng triệu dead tuples, nếu business retention và dependencies cho phép.

## 22. Thiết kế bảng insert-heavy

### 22.1. Primary key

Chọn khóa phù hợp với query, uniqueness và write pattern. Sequential keys có thể tạo hotspot/behavior riêng trên B-tree ở quy mô cao; UUID/random keys có trade-offs về index locality và kích thước.

### 22.2. Index tối thiểu cần thiết

Mỗi index có write cost. Thiết kế theo truy vấn thực tế và constraint requirements, không index mọi cột chỉ vì có thể.

### 22.3. Partition key

Nếu dữ liệu được truy vấn/retention theo thời gian, partition theo time range có thể hỗ trợ pruning và lifecycle management. Chọn partition key có tính ổn định và khớp query predicates.

### 22.4. Append-only event model

Nếu dữ liệu là events bất biến, append-only có thể tránh update churn. Current state có thể được materialize ở bảng riêng theo nhu cầu.

### 22.5. Idempotency và deduplication

Một ingest pipeline retry có thể tạo duplicates nếu không có unique key/idempotency key. Dùng constraints và conflict handling có chủ đích; tránh xóa duplicates liên tục như cơ chế ingest bình thường.

## 23. Thiết kế bảng update-heavy

### 23.1. Tách dữ liệu thường thay đổi

Nếu một row lớn có payload bất biến và vài cột trạng thái thay đổi liên tục, cân nhắc tách mutable state sang bảng nhỏ hơn để giảm tuple/TOAST churn.

### 23.2. Đừng index mọi cột trạng thái

Index trên cột thường xuyên đổi có thể làm HOT updates không đủ điều kiện. Chỉ index nếu workload cần.

### 23.3. Fillfactor thử nghiệm

Dùng fillfactor thấp hơn trên bảng update-heavy có thể giúp HOT nếu có page space và các cột sửa không bị index. Đo hiệu quả thay vì áp dụng toàn database.

### 23.4. Giới hạn update không cần thiết

Không UPDATE row khi giá trị mới bằng giá trị cũ nếu application có thể xác định điều đó an toàn. Tránh tạo tuple version và WAL không cần thiết.

### 23.5. Tránh ghi last_seen mỗi request nếu không cần

Có thể batch/debounce cập nhật telemetry hoặc lưu heartbeat ở hệ thống khác nếu semantics cho phép. Giảm update frequency có thể giảm bloat đáng kể.

## 24. Thiết kế bảng delete-heavy và retention

### 24.1. Xóa theo batch

Nếu phải DELETE rows, chia batch có giới hạn và commit thường xuyên hơn thay vì một transaction khổng lồ.

### 24.2. VACUUM sau delete burst

Sau một đợt xóa lớn, theo dõi autovacuum và có thể chạy manual VACUUM/ANALYZE nếu workload cần, nhưng không mặc định FULL.

### 24.3. Partition drop

Với partition cũ hết hạn, DROP/DETACH PARTITION có thể loại bỏ cả relation nhanh hơn row-by-row deletion.

### 24.4. FK và cascade

Một DELETE parent có thể gây cascade lớn ở bảng con. Phải tính churn và lock trên toàn dependency graph.

### 24.5. Audit/history

Nếu cần giữ lịch sử xóa, ghi audit hoặc event log theo schema riêng; VACUUM không thay chính sách retention của nghiệp vụ.

## 25. Autovacuum và bulk load vào bảng mới

Một bulk load lớn vào bảng mới thường có trình tự khác bảng đã hoạt động lâu năm.

### 25.1. Load vào table mới

Nếu có thể, nạp dữ liệu vào staging table rồi xác minh trước khi swap/attach vào cấu trúc production.

### 25.2. Tạo indexes sau load

Trong một số trường hợp, tạo indexes sau khi COPY nhanh hơn duy trì từng index entry trong quá trình load. Cần cân nhắc unique constraints, availability và write downtime.

### 25.3. ANALYZE sau load

Sau load lớn, chạy ANALYZE khi planner cần statistics mới ngay.

### 25.4. Visibility/freeze

Một lần VACUUM sau load có thể cập nhật visibility/freeze metadata, nhưng hãy xem insert-triggered autovacuum và XID age thay vì luôn chạy FULL.

### 25.5. Kiểm tra identity/sequence

Nếu load explicit values vào identity column, xác minh trạng thái sequence/identity để insert tiếp không trùng key.

## 26. Cấu hình và thay đổi tham số an toàn

Xem setting và nguồn cấu hình:

~~~sql
SELECT
    name,
    setting,
    unit,
    source,
    context,
    pending_restart
FROM pg_settings
WHERE name LIKE 'autovacuum%'
   OR name LIKE 'vacuum_%'
ORDER BY name;
~~~

### 26.1. SHOW chỉ cho giá trị hiện tại

`SHOW` cho biết setting hiện tại, nhưng `pg_settings` có thêm source/context để hiểu setting đến từ đâu và có cần restart không.

### 26.2. Reload hay restart

Các parameters có context khác nhau; kiểm tra `context` và `pending_restart`. Không tự giả định `ALTER SYSTEM` có hiệu lực ngay lập tức.

### 26.3. ALTER SYSTEM

`ALTER SYSTEM` ghi vào `postgresql.auto.conf`, là thay đổi cấp server. Cần quy trình change management và quyền thích hợp.

### 26.4. Per-table reloptions

Ưu tiên tune per-table khi chỉ một nhóm bảng có pattern đặc biệt. Điều này giảm nguy cơ thay đổi behavior của mọi database/table.

### 26.5. Ghi lại baseline và rollback

Trước tuning, lưu setting/reloptions cũ, metric baseline, mục tiêu và tiêu chí rollback. Không thay hàng loạt nhiều tham số cùng lúc khiến khó xác định tác động.

## 27. Các metric vận hành cần alert

| Metric | Vì sao quan trọng |
|---|---|
| Insert/update/delete rate | Xác định write churn |
| `n_dead_tup` estimate | Tín hiệu cleanup backlog |
| `n_ins_since_vacuum` | Insert-triggered vacuum activity |
| `n_mod_since_analyze` | Statistics có thể cũ |
| Last autovacuum / duration | Biết maintenance có chạy |
| XID age | Chống wraparound |
| HOT update ratio | Index churn của UPDATE |
| Heap/index/TOAST size | Bloat và storage growth |
| Autovacuum worker saturation | Capacity/backlog |
| Vacuum progress/phase | Công việc đang ở đâu |
| Lock waits/blockers | Maintenance bị chặn |
| WAL generation/archive lag | Khả năng archive/replication |
| Replication lag/slot xmin | Horizon và recovery risks |
| Disk free/IOPS/latency | Headroom và bottleneck |
| Query latency | Tác động lên ứng dụng |

### 27.1. Alert theo xu hướng

Một metric tăng trong một phút có thể là batch hợp lệ. Alert cần threshold, duration, rate-of-change và context.

### 27.2. Không chỉ alert n_dead_tup

Bảng insert-heavy có thể cần vacuum vì insert/freeze dù dead tuple count thấp. Monitor XID age và insert counters riêng.

### 27.3. Không chỉ alert disk free

Filesystem có thể còn nhiều dung lượng trong khi vacuum đã quá trễ và XID age tăng. Hai nhóm alert bảo vệ những rủi ro khác nhau.

## 28. Chẩn đoán autovacuum lag theo thứ tự

Khi bảng thay đổi nhanh và `n_dead_tup` tăng:

1. Xác nhận write rate và loại churn (INSERT/UPDATE/DELETE).
2. Kiểm tra `last_autovacuum`, vacuum counters và progress.
3. Kiểm tra dead tuple estimate, relation size và index size.
4. Kiểm tra worker slots, cost delay, memory và I/O latency.
5. Kiểm tra long transactions, idle-in-transaction và prepared transactions.
6. Kiểm tra replication slots, xmin/catalog_xmin và standby feedback.
7. Kiểm tra lock waits/DDL/maintenance blockers.
8. Xem threshold/scale factor của đúng table.
9. Điều chỉnh một yếu tố có mục tiêu và theo dõi.
10. Xác nhận workload foreground, vacuum throughput và XID age đều cải thiện.

### 28.1. Worker không xuất hiện

Có thể threshold chưa đạt, launcher chưa tới vòng kiểm tra, workers đã bận, table không đủ điều kiện hoặc statistics chưa cập nhật.

### 28.2. Worker chạy nhưng không dọn nhiều

Có thể snapshot horizon giữ tuples hoặc dead tuple estimate không chính xác tại thời điểm quan sát.

### 28.3. Worker chậm

Kiểm tra I/O, cost delay, index cleanup, relation size và cạnh tranh với query workload.

### 28.4. Bloat tiếp tục tăng

Xem update pattern, indexes, fillfactor, TOAST và rate của writes; một lần vacuum không thể thắng workload tạo dead tuples nhanh hơn.

### 28.5. XID age tăng

Ưu tiên kiểm tra freeze progress, oldest relation/database, slots và transaction horizon. Không chỉ tăng dead-tuple workers.

## 29. Lab: tạo insert-heavy table

**Chỉ thực hành trong database thử nghiệm.** Tạo schema và bảng:

~~~sql
CREATE SCHEMA vacuum_workload_lab;

CREATE TABLE vacuum_workload_lab.events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL
);
~~~

### 29.1. Nạp nhiều rows

~~~sql
INSERT INTO vacuum_workload_lab.events (
    tenant_id, event_time, event_type, payload
)
SELECT
    (g % 1000)::integer,
    clock_timestamp(),
    CASE WHEN g % 4 = 0 THEN 'click' ELSE 'view' END,
    repeat('x', 200)
FROM generate_series(1, 200000) AS g;
~~~

### 29.2. Kiểm tra counters

~~~sql
SELECT
    relname,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_dead_tup,
    n_ins_since_vacuum,
    last_autovacuum
FROM pg_stat_user_tables
WHERE schemaname = 'vacuum_workload_lab';
~~~

Nếu `n_ins_since_vacuum` không có trong phiên bản đang chạy, bỏ cột đó và dùng counters khả dụng.

### 29.3. Kiểm tra visibility-related behavior gián tiếp

Dùng `VACUUM (VERBOSE, ANALYZE)` trong lab và quan sát output/plan. Visibility map có thể xem sâu hơn qua extension/công cụ phù hợp nếu được cài.

### 29.4. Không kỳ vọng dead tuples cao

Bảng mới chủ yếu INSERT nên dead tuples có thể thấp. Bài lab minh họa vì sao insert-triggered vacuum khác dead-tuple vacuum.

### 29.5. Đo size

~~~sql
SELECT
    pg_size_pretty(pg_relation_size('vacuum_workload_lab.events')) AS heap,
    pg_size_pretty(pg_indexes_size('vacuum_workload_lab.events')) AS indexes,
    pg_size_pretty(pg_total_relation_size('vacuum_workload_lab.events')) AS total;
~~~

## 30. Lab: tạo update/delete churn

~~~sql
UPDATE vacuum_workload_lab.events
SET payload = repeat('y', 220)
WHERE event_id % 3 = 0;

UPDATE vacuum_workload_lab.events
SET event_type = 'updated'
WHERE event_id % 10 = 0;

DELETE FROM vacuum_workload_lab.events
WHERE event_id % 7 = 0;
~~~

### 30.1. Kiểm tra stats

~~~sql
SELECT
    n_live_tup,
    n_dead_tup,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_tup_hot_upd
FROM pg_stat_user_tables
WHERE schemaname = 'vacuum_workload_lab'
  AND relname = 'events';
~~~

### 30.2. Tạo index để so sánh churn

~~~sql
CREATE INDEX events_type_idx
ON vacuum_workload_lab.events(event_type);
~~~

Sau đó update indexed column trong lab và quan sát HOT ratio/size. Index có thể làm HOT eligibility giảm khi cột được cập nhật thuộc index.

### 30.3. VACUUM và ANALYZE

~~~sql
VACUUM (VERBOSE, ANALYZE) vacuum_workload_lab.events;
~~~

### 30.4. So sánh trước/sau

Ghi dead tuple estimate, heap/index size và latency query. Autovacuum có thể chạy giữa các bước nên ghi lại timestamps.

### 30.5. Không dùng lab để suy số tuyệt đối production

Kết quả phụ thuộc version, settings, page size, indexes, storage và workload concurrency.

## 31. Lab: tune insert-triggered vacuum cho bảng thử nghiệm

Xem settings hiện hành:

~~~sql
SHOW autovacuum_vacuum_insert_threshold;
SHOW autovacuum_vacuum_insert_scale_factor;
SHOW autovacuum_vacuum_threshold;
SHOW autovacuum_vacuum_scale_factor;
~~~

### 31.1. Đặt reloptions minh họa

~~~sql
ALTER TABLE vacuum_workload_lab.events
SET (
    autovacuum_vacuum_insert_threshold = 1000,
    autovacuum_vacuum_insert_scale_factor = 0.02
);
~~~

### 31.2. Kiểm tra reloptions

~~~sql
SELECT relname, reloptions
FROM pg_class
WHERE oid = 'vacuum_workload_lab.events'::regclass;
~~~

### 31.3. Tạo thêm inserts

~~~sql
INSERT INTO vacuum_workload_lab.events (
    tenant_id, event_time, event_type, payload
)
SELECT
    (g % 1000)::integer,
    clock_timestamp(),
    'batch',
    repeat('z', 200)
FROM generate_series(1, 50000) AS g;
~~~

### 31.4. Theo dõi autovacuum

Quan sát `last_autovacuum`, `n_ins_since_vacuum`, `pg_stat_activity` và progress view. Worker không nhất thiết chạy ngay tại thời điểm INSERT kết thúc.

### 31.5. Reset options sau lab nếu muốn

~~~sql
ALTER TABLE vacuum_workload_lab.events
RESET (
    autovacuum_vacuum_insert_threshold,
    autovacuum_vacuum_insert_scale_factor
);
~~~

## 32. Lab: so sánh fillfactor và HOT

Tạo hai bảng cùng cấu trúc:

~~~sql
CREATE TABLE vacuum_workload_lab.sessions_default (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status TEXT NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL
);

CREATE TABLE vacuum_workload_lab.sessions_ff (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status TEXT NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL
) WITH (fillfactor = 75);
~~~

### 32.1. Nạp dữ liệu ban đầu

~~~sql
INSERT INTO vacuum_workload_lab.sessions_default(status, last_seen)
SELECT 'active', now()
FROM generate_series(1, 50000);

INSERT INTO vacuum_workload_lab.sessions_ff(status, last_seen)
SELECT 'active', now()
FROM generate_series(1, 50000);
~~~

### 32.2. Cập nhật cột không index

~~~sql
UPDATE vacuum_workload_lab.sessions_default
SET last_seen = now()
WHERE id % 2 = 0;

UPDATE vacuum_workload_lab.sessions_ff
SET last_seen = now()
WHERE id % 2 = 0;
~~~

### 32.3. So sánh HOT counters

~~~sql
SELECT
    relname,
    n_tup_upd,
    n_tup_hot_upd
FROM pg_stat_user_tables
WHERE schemaname = 'vacuum_workload_lab'
  AND relname IN ('sessions_default', 'sessions_ff');
~~~

Kết quả phụ thuộc page layout, timing, autovacuum và workload; fillfactor thấp hơn chỉ tạo cơ hội chứ không đảm bảo HOT.

### 32.4. Thêm index trên last_seen rồi thử lại

~~~sql
CREATE INDEX sessions_default_seen_idx
ON vacuum_workload_lab.sessions_default(last_seen);

CREATE INDEX sessions_ff_seen_idx
ON vacuum_workload_lab.sessions_ff(last_seen);
~~~

Lặp update và so sánh. Vì cột được index, update có thể không còn HOT eligible.

### 32.5. Dọn lab

Sau khi hoàn tất quan sát, có thể drop schema lab trong database thử nghiệm nếu không cần dữ liệu nữa:

~~~sql
DROP SCHEMA vacuum_workload_lab CASCADE;
~~~

Chỉ chạy lệnh drop trong lab do chính bạn tạo, không chạy trên schema có dữ liệu khác.

## 33. Troubleshooting: triệu chứng và hướng điều tra

| Triệu chứng | Kiểm tra đầu tiên |
|---|---|
| Insert-heavy table không autovacuum | Insert threshold/scale factor, last_autovacuum, worker capacity |
| Dead tuples tăng nhanh | Update/delete rate, horizon, lock, I/O |
| n_dead_tup thấp nhưng XID age tăng | Freeze/autovacuum, old snapshots, relation age |
| HOT ratio thấp | Index trên cột update, fillfactor, page free space |
| Index size tăng nhanh | Index count, update indexed columns, churn |
| TOAST size lớn | Payload update size/frequency, data model |
| Vacuum workers bận liên tục | Cost settings, I/O, table sizes, churn |
| Vacuum chờ lock | DDL, long transaction, blockers |
| Replication slot giữ xmin | Consumer lag/slot owner, retention |
| WAL disk đầy | Archive/replication lag, slot restart_lsn |
| Planner chọn plan xấu sau load | ANALYZE, statistics, extended stats |
| Query latency tăng khi vacuum | I/O saturation, worker concurrency, cost delay |
| Partition mới query chậm | ANALYZE parent/leaf, partition pruning |
| Delete retention gây bloat | Batch deletes, partition drop/detach |
| Bảng tăng size dù vacuum chạy | Workload churn, indexes, free space, TOAST |

### 33.1. Không phản ứng bằng VACUUM FULL trước khi chẩn đoán

FULL có thể compact một lần nhưng không sửa write pattern, transaction horizon hoặc autovacuum capacity. Bloat sẽ quay lại nếu nguyên nhân vẫn tồn tại.

### 33.2. Tách heap bloat và index bloat

Đo heap/index/TOAST riêng. Một bảng có heap ổn định nhưng index tăng nhanh cần hướng xử lý khác.

### 33.3. Phân biệt backlog với normal growth

Bảng append-only tăng kích thước theo số rows là tăng trưởng dữ liệu hợp lệ, không tự là bloat.

### 33.4. Xem xét WAL và disk riêng

WAL accumulation không phải dead tuple bloat. Điều tra archiver/replication slot và filesystem riêng biệt.

## 34. Những hiểu lầm thường gặp

1. **“Insert-heavy không cần VACUUM vì không DELETE.”** Sai: insert-triggered vacuum hỗ trợ visibility map và freeze.
2. **“INSERT tạo dead tuples như UPDATE.”** Sai: INSERT tạo version mới hiện hành, không tự tạo version cũ.
3. **“Autovacuum chỉ chạy khi n_dead_tup cao.”** Sai: có insert-triggered vacuum và anti-wraparound.
4. **“Scale factor càng thấp càng tốt.”** Sai: vacuum thường xuyên có thể tăng I/O và contention.
5. **“Tăng workers luôn làm vacuum nhanh hơn.”** Sai: worker thêm có thể tranh chấp CPU/RAM/I/O.
6. **“Dead tuple estimate là số chính xác.”** Sai: đây là thống kê ước lượng.
7. **“VACUUM thường luôn làm file nhỏ.”** Sai: chủ yếu tái sử dụng free space nội bộ.
8. **“VACUUM FULL là cách tối ưu bảng insert-heavy.”** Sai: FULL rewrite và lock ACCESS EXCLUSIVE.
9. **“Bảng append-only không có XID wraparound risk.”** Sai: tuple cũ vẫn cần freeze.
10. **“HOT update xảy ra nếu cột không đổi.”** Sai: cần điều kiện index/page space phù hợp.
11. **“Fillfactor thấp luôn tốt.”** Sai: tăng storage và I/O cho insert-only workloads.
12. **“Index càng nhiều càng tốt.”** Sai: mỗi index tăng write/maintenance cost.
13. **“UPDATE một cột nhỏ không ảnh hưởng TOAST.”** Không luôn đúng; row version và payload behavior cần xem thực tế.
14. **“Tăng autovacuum_naptime thấp là đủ.”** Sai: worker/threshold/horizon/resource vẫn quyết định.
15. **“Long transaction chỉ gây lock.”** Sai: có thể giữ snapshot và ngăn vacuum cleanup.
16. **“Drop replication slot là cách dọn dead tuples an toàn.”** Sai: có thể phá consumer và không có rollback đơn giản.
17. **“Replica tự bảo vệ khỏi dữ liệu bị xóa nhầm.”** Sai: thay đổi được replay.
18. **“ANALYZE và VACUUM là một.”** Sai: statistics khác cleanup/freeze.
19. **“Bulk load xong không cần ANALYZE.”** Sai: planner có thể dùng statistics cũ.
20. **“Delete retention luôn nên dùng DELETE.”** Sai: partition lifecycle có thể phù hợp hơn.
21. **“n_tup_ins tích lũy cho biết insert rate.”** Sai: cần delta và elapsed time.
22. **“Một lần autovacuum là đủ cho cả đời bảng.”** Sai: workload tiếp tục thay đổi.
23. **“WAL đầy là VACUUM không chạy.”** Đây là hai vấn đề khác nhau, dù có thể cùng bị ảnh hưởng bởi slot/replication.
24. **“VACUUM FULL chữa được mọi bloat.”** Sai: không sửa root cause và có thể gây downtime.
25. **“Không có row trong progress view nghĩa không có vacuum.”** Sai: operation có thể đã kết thúc/chưa bắt đầu hoặc view khác.
26. **“Có thể chạy VACUUM trong transaction block.”** Sai: VACUUM phải chạy ngoài explicit transaction block.

## 35. Bài tập thực hành

### Bài 1 — Insert-only

Một bảng chỉ INSERT, không UPDATE/DELETE. Vì sao vẫn cần autovacuum?

**Gợi ý:** Visibility map và freeze XIDs.

### Bài 2 — Dead tuples

INSERT thuần túy có tự tạo dead tuple version như UPDATE không?

**Đáp án:** Không.

### Bài 3 — Insert threshold

Tham số nào đặt ngưỡng INSERT tối thiểu cho insert-triggered vacuum?

**Đáp án:** `autovacuum_vacuum_insert_threshold`.

### Bài 4 — Insert scale factor

Tham số nào làm ngưỡng insert vacuum thay đổi theo quy mô bảng?

**Đáp án:** `autovacuum_vacuum_insert_scale_factor`.

### Bài 5 — Công thức

Viết công thức insert vacuum threshold tổng quát.

**Gợi ý:** Threshold cố định + scale factor × estimated table tuples.

### Bài 6 — Bảng lớn

Vì sao scale factor 0,2 có thể tạo threshold quá cao trên bảng hàng tỷ rows?

**Gợi ý:** Phần ngưỡng theo tỷ lệ trở thành hàng trăm triệu inserts.

### Bài 7 — Dead tuple threshold

Tham số scale factor nào áp dụng cho vacuum do UPDATE/DELETE?

**Đáp án:** `autovacuum_vacuum_scale_factor`.

### Bài 8 — ANALYZE

Vì sao bulk load có thể cần ANALYZE ngay?

**Gợi ý:** Query planner cần statistics phản ánh phân bố mới.

### Bài 9 — n_ins_since_vacuum

Counter này giúp theo dõi điều gì?

**Đáp án:** Số tuples insert kể từ lần vacuum gần nhất, khi view/version hỗ trợ.

### Bài 10 — n_dead_tup

Đây có phải số dead tuples chính xác tức thời?

**Đáp án:** Không.

### Bài 11 — HOT

HOT viết tắt của gì?

**Đáp án:** Heap-Only Tuple.

### Bài 12 — HOT eligibility

Hai điều kiện quan trọng để HOT update có thể xảy ra?

**Gợi ý:** Không thay đổi các cột index cần update và có đủ page space.

### Bài 13 — Index churn

Vì sao index trên cột status thường xuyên thay đổi có thể tăng maintenance cost?

**Gợi ý:** Update phải duy trì index entries, giảm HOT opportunities.

### Bài 14 — HOT ratio

Cách ước lượng HOT ratio?

**Đáp án:** Delta `n_tup_hot_upd / n_tup_upd`.

### Bài 15 — Fillfactor

Fillfactor 75 hướng tới điều gì?

**Gợi ý:** Chừa page space để có thể hỗ trợ HOT/update.

### Bài 16 — Insert-only fillfactor

Vì sao fillfactor thấp có thể không phù hợp bảng append-only?

**Gợi ý:** Giảm page density, tăng storage/I/O.

### Bài 17 — TOAST

Vì sao update JSONB payload lớn thường xuyên có thể tăng TOAST churn?

**Gợi ý:** Tạo phiên bản/chunks mới, phiên bản cũ cần cleanup.

### Bài 18 — WAL

VACUUM có phải lệnh dọn WAL files không?

**Đáp án:** Không.

### Bài 19 — Partitioning

Vì sao drop partition cũ có thể hiệu quả hơn DELETE hàng triệu rows?

**Gợi ý:** Loại bỏ relation theo phạm vi lớn, giảm row-by-row churn.

### Bài 20 — Partition stats

Vì sao cần xem ANALYZE cho partitioned parent sau load?

**Gợi ý:** Planner cần statistics ở cấp parent theo version/behavior.

### Bài 21 — Autovacuum workers

Tăng max workers có thể tạo rủi ro gì?

**Gợi ý:** Cạnh tranh CPU/RAM/I/O.

### Bài 22 — Cost delay

Nếu cost delay quá cao, điều gì có thể xảy ra?

**Đáp án:** Vacuum chạy chậm và backlog tăng.

### Bài 23 — Long transaction

Một idle-in-transaction session có thể ngăn vacuum thế nào?

**Gợi ý:** Giữ snapshot/xmin horizon cũ.

### Bài 24 — Replication slot

Cột nào trong pg_replication_slots liên quan tới cleanup horizon?

**Đáp án:** `xmin`, `catalog_xmin`.

### Bài 25 — WAL retention

Cột nào liên quan WAL position slot cần giữ?

**Đáp án:** `restart_lsn`.

### Bài 26 — XID age

View nào xem age của database frozen XID?

**Đáp án:** `pg_database` với `age(datfrozenxid)`.

### Bài 27 — Monitoring

View nào chứa n_tup_ins/n_tup_upd/n_tup_del?

**Đáp án:** `pg_stat_user_tables`.

### Bài 28 — Progress

View nào xem VACUUM thường đang chạy?

**Đáp án:** `pg_stat_progress_vacuum`.

### Bài 29 — Lock

Function nào xác định PID đang block một backend?

**Đáp án:** `pg_blocking_pids(pid)`.

### Bài 30 — Insert rate

Cần dữ liệu gì để tính insert rate?

**Gợi ý:** Delta n_tup_ins và elapsed time giữa hai snapshots.

### Bài 31 — Bloat

Một table tăng size sau một triệu INSERT mới có tự chứng minh bloat không?

**Đáp án:** Không; đó có thể là tăng trưởng hợp lệ.

### Bài 32 — Bulk load

Tại sao không nên giữ một transaction bulk load khổng lồ vô thời hạn?

**Gợi ý:** Snapshot/locks, rollback footprint và cleanup horizon.

### Bài 33 — Analyze threshold

Tham số nào tune auto-analyze theo tỷ lệ?

**Đáp án:** `autovacuum_analyze_scale_factor`.

### Bài 34 — Append-only freeze

Một bảng append-only rất cũ có thể có rủi ro gì dù n_dead_tup gần zero?

**Đáp án:** XID wraparound nếu tuples không được freeze đúng hạn.

### Bài 35 — Chọn giải pháp

Một bảng event 500 triệu rows chỉ INSERT, n_dead_tup thấp, query index-only scan kém. Bạn kiểm tra gì?

**Gợi ý:** Insert-triggered vacuum thresholds, visibility map, ANALYZE, indexes và query plan.

### Bài 36 — Chọn giải pháp

Một bảng session 20 triệu rows, mỗi row update mỗi phút, n_dead_tup tăng liên tục. Bạn kiểm tra gì?

**Gợi ý:** Dead tuple threshold, HOT ratio, indexed columns, fillfactor, transaction horizon, workers/I/O.

### Bài 37 — Chọn giải pháp

WAL disk tăng nhanh nhưng n_dead_tup thấp. Có nên chạy VACUUM FULL không?

**Đáp án:** Không; kiểm tra archiver, replication slots, lag và WAL retention.

### Bài 38 — Chọn giải pháp

Một bảng log có dữ liệu theo tháng, cần xóa dữ liệu sau 18 tháng. Chiến lược nào đáng cân nhắc?

**Gợi ý:** Range partitioning và detach/drop partition theo retention.

### Bài 39 — Chọn giải pháp

Autovacuum worker chạy lâu, không dọn thêm tuples. Bạn điều tra gì trước?

**Gợi ý:** backend_xmin, long transactions, replication slot xmin, locks và progress phase.

### Bài 40 — Thiết kế tổng hợp

Thiết kế chiến lược cho bảng event append-only 1 tỷ rows/ngày, retention 30 ngày, query theo tenant/time, cần index-only scan và RPO thấp.

**Gợi ý:** Time partitioning, index theo query/tenant/time, insert-triggered vacuum và freeze monitoring, ANALYZE, WAL/archive/replication capacity, retention bằng partition lifecycle, offsite backup và restore tests; đo I/O và visibility map.

## 36. Checklist vận hành cho insert-heavy/high-churn tables

### 36.1. Hiểu workload

- [ ] Đã phân loại insert/update/delete rates?
- [ ] Đã đo rate bằng delta counters theo thời gian?
- [ ] Có batch bursts hay continuous writes?
- [ ] Có payload lớn/TOAST?
- [ ] Có index trên các cột thay đổi thường xuyên?
- [ ] Có partition/retention theo thời gian?

### 36.2. Autovacuum và ANALYZE

- [ ] Insert-triggered threshold/scale factor có phù hợp?
- [ ] Dead tuple threshold có phù hợp?
- [ ] Analyze threshold có cập nhật planner đủ nhanh?
- [ ] Worker count/cost delay/work_mem có cân bằng I/O?
- [ ] Per-table reloptions được ghi lại và có rollback?
- [ ] Autovacuum không bị tắt vô tình?

### 36.3. Transaction horizon

- [ ] Không có idle-in-transaction sessions lâu?
- [ ] Không có prepared transactions bỏ quên?
- [ ] Replication slots có active consumers?
- [ ] xmin/catalog_xmin không bị giữ quá lâu?
- [ ] Standby feedback và lag được monitor?

### 36.4. Storage và performance

- [ ] Heap/index/TOAST sizes được theo dõi riêng?
- [ ] HOT ratio phù hợp với update pattern?
- [ ] Fillfactor đã được đo trên staging?
- [ ] WAL/archive/checkpoint/disk capacity đủ?
- [ ] Vacuum progress và lock waits được monitor?
- [ ] Không chạy VACUUM FULL tùy tiện trong giờ cao điểm?

### 36.5. Dữ liệu và retention

- [ ] Indexes chỉ giữ những cái có giá trị?
- [ ] Partition granularity hợp lý?
- [ ] Retention dùng detach/drop khi phù hợp?
- [ ] Bulk load có ANALYZE/validation sau load?
- [ ] Identity/sequence được đồng bộ khi import explicit IDs?
- [ ] Có backup và restore test trước thay đổi lớn?

## 37. Bảng tra cứu nhanh

| Thành phần | Ý nghĩa |
|---|---|
| Insert-heavy | Nhiều INSERT, có thể ít dead tuples |
| High churn | Nhiều UPDATE/DELETE tạo tuple versions |
| `autovacuum_vacuum_insert_threshold` | Ngưỡng INSERT cố định |
| `autovacuum_vacuum_insert_scale_factor` | Ngưỡng INSERT theo quy mô |
| `autovacuum_vacuum_threshold` | Ngưỡng dead tuples cố định |
| `autovacuum_vacuum_scale_factor` | Ngưỡng dead tuples theo quy mô |
| `autovacuum_analyze_threshold` | Ngưỡng auto-analyze cố định |
| `autovacuum_analyze_scale_factor` | Ngưỡng auto-analyze theo quy mô |
| `n_ins_since_vacuum` | Inserts kể từ vacuum, nếu version hỗ trợ |
| `n_dead_tup` | Ước lượng dead tuples |
| `n_mod_since_analyze` | Thay đổi kể từ analyze |
| `n_tup_hot_upd` | Số HOT updates |
| HOT update | Heap-only update, giảm index churn |
| Fillfactor | Mục tiêu page density, có thể chừa chỗ cho update |
| Visibility map | All-visible/all-frozen page metadata |
| Freeze | Bảo vệ XID wraparound |
| TOAST | Storage cho values lớn |
| `pg_stat_user_tables` | Table-level counters/history |
| `pg_stat_progress_vacuum` | Vacuum progress |
| `pg_stat_activity` | Sessions/transactions |
| `pg_locks` | Locks và waits |
| `pg_replication_slots` | WAL và xmin retention |
| `pg_total_relation_size` | Heap + indexes + TOAST |
| Partition retention | Loại bỏ dữ liệu theo relation |
| WAL archive | Bảo vệ/replay lịch sử WAL |
| Bulk load | Nạp dữ liệu lớn theo đợt |
| Autovacuum cost delay | Throttle vacuum activity |
| XID age | Theo dõi freeze/wraparound risk |

## 38. Kết luận

**Insert-heavy và high-churn là hai kiểu workload cần cách nhìn VACUUM khác nhau.** Bảng append-only có thể gần như không tạo dead tuples nhưng vẫn cần insert-triggered vacuum để cập nhật visibility map và freeze các tuples cũ. Bảng UPDATE/DELETE liên tục cần cleanup dead tuple versions, quản lý index churn và bảo đảm autovacuum theo kịp tốc độ thay đổi.

Đừng bắt đầu bằng cách tăng mọi autovacuum settings. Hãy đo insert/update/delete rates, dead tuple estimates, insert-since-vacuum counters, analyze backlog, HOT ratio, heap/index/TOAST size, worker saturation và XID age. Nếu vacuum không thu hồi được tuples, tìm transaction lâu, idle-in-transaction, replication slots, standby feedback và blockers trước khi thay threshold.

Với bảng có tốc độ ghi lớn, chiến lược tốt thường kết hợp **per-table autovacuum tuning, index/fillfactor hợp lý, transaction ngắn, partitioning/retention và giám sát WAL/I/O**. Bulk load cần kế hoạch trước-trong-sau; update-heavy table cần giảm writes không cần thiết và tạo điều kiện cho HOT; time-series table có thể dùng partition lifecycle thay mass DELETE.

Nguyên tắc vận hành là: **tune theo pattern dữ liệu và giới hạn tài nguyên thật, giữ autovacuum/freeze hoạt động, xử lý cleanup horizon và xác minh bằng metrics theo thời gian**. VACUUM FULL không phải giải pháp mặc định cho workload lớn; nó chỉ phù hợp khi cần rewrite/reclaim rõ ràng và đã chấp nhận chi phí disk cùng lock.


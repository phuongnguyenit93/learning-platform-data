# Lập lịch bảo trì PostgreSQL dựa trên bằng chứng thay vì thao tác định kỳ mù

## 1. Vì sao không nên chạy VACUUM chỉ vì đến giờ?

Một cron job có thể chạy:

```sql
VACUUM (ANALYZE);
```

trên toàn bộ database mỗi đêm. Lệnh này đôi khi hữu ích, nhưng nếu đó là chính sách duy nhất thì nhóm vận hành không biết bảng nào thực sự cần bảo trì, autovacuum đã xử lý đến đâu, transaction ID age có đang tiến gần ngưỡng wraparound, hay thao tác có làm tăng I/O và latency trong giờ cao điểm.

Một bảng OLTP có UPDATE/DELETE liên tục có thể tích lũy dead tuples nhanh. Một bảng append-only lại có ít dead tuples nhưng vẫn cần freeze và cập nhật visibility map. Một bảng mới bulk load có thể cần ANALYZE để planner hiểu phân bố dữ liệu. Một bảng có free space lớn có thể vẫn tái sử dụng tốt và không cần rewrite để thu nhỏ file.

**Lập lịch dựa trên bằng chứng** nghĩa là xác định mục tiêu, thu thập tín hiệu, đặt ngưỡng theo workload, chọn đúng thao tác và đo lại kết quả. Autovacuum vẫn là tuyến bảo trì tự động chính; lịch thủ công bổ sung cho các tình huống cần can thiệp có kiểm soát.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt VACUUM, ANALYZE, autovacuum, anti-wraparound vacuum, VACUUM FULL và REINDEX.
2. Hiểu các ngưỡng autovacuum/analyze và ảnh hưởng của kích thước bảng, churn và insert rate.
3. Xác định bảng cần bảo trì từ dead tuple estimates, modifications, kích thước và lịch sử vacuum.
4. Theo dõi transaction ID age và MultiXact age để ưu tiên freeze.
5. Nhận diện long-running transactions và replication slots đang trì hoãn cleanup.
6. Quan sát tiến độ vacuum, wait events, lock blockers và autovacuum logs.
7. Phân biệt nhu cầu tái sử dụng free space với nhu cầu thu hồi dung lượng filesystem.
8. Điều chỉnh autovacuum per-table có căn cứ thay vì áp một cấu hình cho mọi bảng.
9. Xây dựng lịch maintenance theo workload, partition lifecycle và thời gian phục hồi.
10. Thiết kế runbook có trigger, hành động, verification và guardrails.
11. Tránh chạy VACUUM FULL theo cron hoặc tắt autovacuum để giảm I/O.
12. Đo lại kết quả sau khi thay đổi maintenance policy.

---

## 2. VACUUM làm gì và không làm gì?

PostgreSQL dùng MVCC để giữ nhiều phiên bản tuple. Khi UPDATE hoặc DELETE, tuple cũ không nhất thiết biến mất ngay. Sau khi không còn transaction/snapshot nào cần phiên bản cũ, VACUUM có thể thu hồi không gian để PostgreSQL tái sử dụng.

```text
INSERT / UPDATE / DELETE
          |
          v
Tuple versions tích lũy trên heap
          |
          v
Tuple cũ còn cần cho snapshot?
          |
          +-- Có -> chưa thể thu hồi an toàn
          |
          +-- Không -> VACUUM/pruning có thể dọn
                         |
                         +-- cập nhật free-space metadata
                         +-- visibility/freeze metadata
                         +-- index cleanup khi phù hợp
```

VACUUM thông thường có thể:

- Thu hồi tuple versions không còn cần thiết.
- Đánh dấu không gian để tái sử dụng trong relation.
- Cập nhật Free Space Map (FSM).
- Cập nhật Visibility Map (VM) khi đủ điều kiện.
- Thực hiện index cleanup theo lựa chọn và phiên bản.
- Freeze tuple cũ nhằm chống transaction ID wraparound.

VACUUM thông thường không hứa:

- Viết lại toàn bộ bảng để thu gọn mọi page.
- Trả toàn bộ free space về filesystem.
- Làm mọi index hết bloat.
- Cập nhật planner statistics đầy đủ như ANALYZE nếu chỉ chạy VACUUM.
- Thu hồi được tuple vẫn cần cho snapshot cũ.
- Sửa query plan kém chỉ bằng việc chạy nhiều lần.

### 2.1. Phân biệt các thao tác

| Thao tác | Mục tiêu chính |
|---|---|
| VACUUM | Thu hồi tuple chết để tái sử dụng, duy trì FSM/VM và freeze |
| ANALYZE | Lấy mẫu dữ liệu để cập nhật statistics cho planner |
| VACUUM (ANALYZE) | Thực hiện cả hai |
| Autovacuum | Daemon tự kích hoạt vacuum/analyze theo ngưỡng |
| Anti-wraparound vacuum | Vacuum ưu tiên để tránh XID/MultiXact wraparound |
| VACUUM FULL | Rewrite relation để thu hồi dung lượng filesystem |
| REINDEX | Xây dựng lại index |

Khi báo cáo, hãy ghi rõ thao tác nào đã chạy và vì sao. Không dùng từ “vacuum” để chỉ chung mọi loại maintenance.

## 3. Ba câu hỏi trước khi lập lịch

**Câu 1 — Mục tiêu cần đạt là gì?**

- Thu hồi dead tuples để page được tái sử dụng?
- Cập nhật statistics vì dữ liệu thay đổi nhiều?
- Freeze tuple để giữ transaction ID age an toàn?
- Cải thiện index-only scan bằng visibility map?
- Thu hồi file space do relation thực sự phình?
- Xây lại index có vấn đề?

**Câu 2 — Bằng chứng nào cho thấy cần làm?**

Ví dụ: dead tuple growth tăng nhanh, modifications vượt ngưỡng, XID age cao, vacuum lag, VM coverage giảm, query plan ước lượng sai hoặc storage tăng bất thường.

**Câu 3 — Tác động của thao tác là gì?**

Cần biết lock mode, I/O, WAL, disk headroom, replication lag, connection pressure và latency của ứng dụng.

Nếu không trả lời được ba câu hỏi này, một cron chạy toàn database thường chỉ tạo thêm tải và log mà không chứng minh đã giải quyết vấn đề.

## 4. Autovacuum là tuyến bảo trì mặc định

Autovacuum gồm launcher và các worker thực hiện vacuum/analyze khi bảng đạt điều kiện. Trong cấu hình thông thường, PostgreSQL tự xử lý phần lớn bảng mà không cần lịch VACUUM thủ công hằng ngày.

Các nhóm trigger quan trọng:

- Vacuum do UPDATE/DELETE làm tăng dead tuples.
- Vacuum do INSERT để duy trì visibility/freeze trong các phiên bản hỗ trợ insert-vacuum threshold.
- Autoanalyze khi dữ liệu thay đổi đủ nhiều so với statistics hiện tại.
- Vacuum do ngưỡng freeze/anti-wraparound.

Autovacuum không chỉ chạy theo đồng hồ. Nó dựa vào ngưỡng, thống kê và trạng thái hệ thống.

### 4.1. Các tham số chính

| Tham số | Ý nghĩa |
|---|---|
| autovacuum | Bật/tắt autovacuum daemon thông thường |
| autovacuum_vacuum_threshold | Ngưỡng dead tuples tối thiểu |
| autovacuum_vacuum_scale_factor | Tỷ lệ theo số tuples ước lượng để tính ngưỡng vacuum |
| autovacuum_vacuum_insert_threshold | Ngưỡng insert tối thiểu cho insert-triggered vacuum |
| autovacuum_vacuum_insert_scale_factor | Thành phần tỷ lệ của ngưỡng insert-vacuum |
| autovacuum_analyze_threshold | Ngưỡng modifications tối thiểu cho analyze |
| autovacuum_analyze_scale_factor | Thành phần tỷ lệ của ngưỡng analyze |
| autovacuum_naptime | Khoảng thời gian launcher ngủ giữa các lần kiểm tra |
| autovacuum_max_workers | Số worker autovacuum tối đa |
| autovacuum_work_mem | Bộ nhớ làm việc dành cho autovacuum |
| autovacuum_vacuum_cost_delay | Cost-based delay cho autovacuum |
| autovacuum_vacuum_cost_limit | Cost limit cho autovacuum |
| autovacuum_freeze_max_age | Ngưỡng tuổi XID để kích hoạt vacuum chống wraparound |
| autovacuum_multixact_freeze_max_age | Ngưỡng tuổi MultiXact cho vacuum tương ứng |

Tên, mặc định và một số chi tiết thay đổi theo PostgreSQL version. Kiểm tra cấu hình server:

```sql
SELECT
    name,
    setting,
    unit,
    source
FROM pg_settings
WHERE name LIKE 'autovacuum%'
   OR name LIKE 'vacuum_%'
ORDER BY name;
```

### 4.2. Không nên tắt autovacuum để giảm tải mà không có phương án thay thế

Tắt autovacuum có thể khiến dead tuples, statistics cũ và freeze age tích lũy. PostgreSQL vẫn có cơ chế khởi chạy vacuum khẩn cấp để chống wraparound ngay cả khi autovacuum thông thường bị tắt, nhưng không nên dựa vào cơ chế khẩn cấp làm chính sách vận hành.

## 5. Ngưỡng autovacuum: số tuyệt đối cộng với tỷ lệ

Ở mức khái quát, vacuum do UPDATE/DELETE được cân nhắc khi số dead tuples vượt ngưỡng:

```text
vacuum threshold
  = autovacuum_vacuum_threshold
  + autovacuum_vacuum_scale_factor * estimated_tuple_count
```

Autoanalyze dùng dạng tương tự:

```text
analyze threshold
  = autovacuum_analyze_threshold
  + autovacuum_analyze_scale_factor * estimated_tuple_count
```

Các phiên bản hỗ trợ insert-triggered vacuum có thêm ngưỡng insert tương ứng. Chi tiết chính xác, bao gồm cách tính dựa trên estimates và insert scale factor, cần đối chiếu tài liệu của server version đang chạy.

### 5.1. Ví dụ với bảng lớn

Giả sử cấu hình minh họa:

- autovacuum_vacuum_threshold = 50
- autovacuum_vacuum_scale_factor = 0.20
- Bảng có 10.000.000 tuples ước lượng.

Ngưỡng gần đúng:

```text
50 + 0.20 * 10,000,000
= 2,000,050 dead tuples
```

Với bảng lớn, 20% có thể tương đương hàng triệu dead tuples trước khi trigger. Nếu bảng có UPDATE/DELETE liên tục, chờ tới ngưỡng đó có thể quá muộn cho mục tiêu latency hoặc storage.

### 5.2. Ví dụ với bảng nhỏ

Nếu bảng có 1.000 tuples:

```text
50 + 0.20 * 1,000
= 250 dead tuples
```

Ngưỡng tuyệt đối có ảnh hưởng lớn hơn scale factor. Vì vậy một cấu hình chung có thể tạo hành vi rất khác giữa bảng nhỏ và bảng lớn.

### 5.3. Scale factor không phải lịch chạy

autovacuum_vacuum_scale_factor = 0.05 không có nghĩa vacuum chạy mỗi 5% thời gian hay mỗi 5% dung lượng đĩa. Nó là thành phần của ngưỡng theo số tuples ước lượng.

### 5.4. Threshold chỉ là một tín hiệu

Autovacuum còn chịu ảnh hưởng của worker availability, cost delay, locks, table state và điều kiện freeze. Đạt ngưỡng không bảo đảm worker bắt đầu ngay tức thì.

## 6. Insert-heavy table cũng có nhu cầu vacuum

Một bảng chỉ INSERT và hầu như không UPDATE/DELETE có thể ít dead tuples, nhưng vẫn có nhu cầu vacuum:

- Freeze các tuple cũ.
- Cập nhật Visibility Map để hỗ trợ index-only scans.
- Giảm rủi ro transaction ID age.
- Duy trì khả năng quản lý page lifecycle.

Các phiên bản PostgreSQL hiện đại có ngưỡng insert-vacuum. Vì vậy không kết luận “bảng append-only không cần vacuum”.

### 6.1. Khi nào insert-vacuum đặc biệt hữu ích?

Một bảng append-only rất lớn, được truy vấn bằng index-only scans, có thể hưởng lợi khi page đã ổn định và all-visible. Vacuum giúp VM phản ánh trạng thái này nếu điều kiện snapshot cho phép.

### 6.2. Không nhầm insert rate với dead tuple count

Bảng có thể có ít dead tuples nhưng nhiều page mới chưa all-visible hoặc chưa freeze. Theo dõi insert churn, VM, freeze age và index-only scan heap fetches thay vì chỉ nhìn n_dead_tup.

## 7. Analyze cũng phải dựa trên thay đổi dữ liệu

Planner dựa vào statistics để ước lượng số rows, selectivity, distinct values và phân bố dữ liệu. Statistics cũ có thể khiến chọn join strategy, scan method hoặc cardinality estimate không phù hợp.

Autoanalyze thường được kích hoạt dựa trên số modifications kể từ lần analyze gần nhất và ngưỡng tương ứng.

### 7.1. Dấu hiệu cần ANALYZE

- Bảng mới được nạp lượng dữ liệu lớn.
- Phân bố giá trị thay đổi đáng kể.
- Query plan ước lượng rows sai xa actual rows.
- Partition vừa được load/attach.
- Query latency tăng sau batch import.
- Các cột có correlation/skew cao nhưng statistics chưa phản ánh đúng.

### 7.2. ANALYZE không phải VACUUM

```sql
ANALYZE public.orders;
```

Lệnh này cập nhật statistics, không dọn dead tuples và không reclaim relation storage.

### 7.3. Statistics target cho cột skew

Nếu một cột có phân bố lệch mạnh, có thể cân nhắc tăng statistics target:

```sql
ALTER TABLE public.orders
ALTER COLUMN status SET STATISTICS 500;

ANALYZE public.orders (status);
```

Target cao hơn có thể tăng độ chi tiết statistics và chi phí lấy mẫu/lưu metadata. Chỉ điều chỉnh khi query evidence cho thấy planner ước lượng chưa tốt.

### 7.4. Partitioned table cần lưu ý riêng

Autovacuum không tự xử lý mọi thống kê của partitioned parent theo cách nhiều người kỳ vọng. Khi load/attach dữ liệu vào partitions, có thể cần chạy ANALYZE ở parent để cập nhật inheritance/partition-level planner statistics theo version và cấu trúc cụ thể.

## 8. Evidence 1: dead tuple estimates và table churn

View pg_stat_user_tables là điểm bắt đầu hữu ích:

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    n_mod_since_analyze,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_tup_hot_upd,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
```

Các cột có thể khác theo version; kiểm tra view hiện hành trước khi đưa query vào monitoring lâu dài.

### 8.1. Dead percentage chỉ là chỉ báo

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
    ) AS estimated_dead_percent
FROM pg_stat_user_tables
ORDER BY estimated_dead_percent DESC NULLS LAST;
```

n_live_tup và n_dead_tup là estimates. Không dùng một tỷ lệ 10% hoặc 20% như ngưỡng tuyệt đối cho mọi bảng.

### 8.2. Cần nhìn tốc độ tăng

Một bảng có 100.000 dead tuples ổn định có thể ít khẩn cấp hơn một bảng tăng từ 10.000 lên 500.000 trong 15 phút.

Lưu snapshot metrics theo thời gian để tính:

```text
dead tuple growth rate
  = (dead_tuples_now - dead_tuples_previous)
    / elapsed_time
```

Đồng thời theo dõi n_tup_upd/n_tup_del, kích thước bảng và autovacuum timestamps.

### 8.3. Stats có thể reset

Statistics có thể reset do server restart, reset stats hoặc thao tác quản trị. Nếu chỉ đọc một snapshot mà không biết thời gian từ lần reset, có thể hiểu sai tốc độ churn.

## 9. Evidence 2: table size và storage growth

Đo riêng main/table/index/total size:

```sql
SELECT
    schemaname,
    relname,
    pg_size_pretty(pg_relation_size(relid)) AS main_fork_size,
    pg_size_pretty(pg_table_size(relid)) AS table_size,
    pg_size_pretty(pg_indexes_size(relid)) AS indexes_size,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 30;
```

### 9.1. Main fork không phải toàn bộ footprint

pg_relation_size mặc định đo main fork. pg_table_size tính thêm thành phần table liên quan như TOAST/forks. pg_indexes_size đo indexes. pg_total_relation_size tổng hợp table và indexes theo semantics của hàm.

Không cộng các cột size chồng lặp để tạo một tổng sai.

### 9.2. Kích thước tăng chưa chắc là bloat

Một bảng tăng từ 10 GB lên 12 GB có thể đơn giản vì thêm dữ liệu sống. Cần so với row count, tuple width, insert/update rate, dead tuples và TOAST/index growth.

### 9.3. Free space có thể là tài sản tái sử dụng

VACUUM làm free space có thể dùng cho INSERT/UPDATE tiếp theo. Không phải mọi page còn trống đều cần được thu hồi về filesystem.

## 10. Evidence 3: transaction ID age và freeze horizon

PostgreSQL dùng transaction IDs có không gian hữu hạn. VACUUM phải freeze tuple cũ trước khi wraparound đe dọa tính đúng đắn visibility.

Kiểm tra age ở cấp database:

```sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age,
    current_setting('autovacuum_freeze_max_age')::bigint
        AS configured_freeze_max_age
FROM pg_database
ORDER BY xid_age DESC;
```

### 10.1. Age không phải thời gian theo ngày

age(datfrozenxid) đo khoảng cách transaction ID, không phải số ngày database đã chạy. Tốc độ tăng phụ thuộc transaction throughput.

### 10.2. Cấp relation

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.relkind,
    age(c.relfrozenxid) AS xid_age,
    c.relminmxid
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm', 't')
ORDER BY xid_age DESC
LIMIT 30;
```

Query cần được điều chỉnh theo version/catalog và có thể bao gồm TOAST relations. Dùng để tìm relations có XID age cao, không thay thế dashboard wraparound của cluster.

### 10.3. MultiXact age cũng quan trọng

MultiXact được sử dụng trong một số tình huống nhiều transaction cùng khóa tuple. PostgreSQL có ngưỡng freeze MultiXact riêng. Theo dõi datminmxid/relminmxid và age bằng các hàm/cột phù hợp với phiên bản.

### 10.4. Freeze age là tín hiệu ưu tiên cao

Khi XID/MultiXact age tiến gần ngưỡng cấu hình, bảo trì chống wraparound có thể quan trọng hơn latency ngắn hạn. Không chờ dead tuple percentage cao mới xử lý freeze.

## 11. Anti-wraparound vacuum không phải lịch bảo trì tùy chọn

Autovacuum có thể chạy vacuum ưu tiên để tránh wraparound khi tuổi transaction ID đạt ngưỡng. Đây là cơ chế bảo vệ tính đúng đắn của database.

Các tham số liên quan gồm:

- autovacuum_freeze_max_age.
- autovacuum_multixact_freeze_max_age.
- vacuum_freeze_min_age.
- vacuum_freeze_table_age.
- vacuum_multixact_freeze_min_age.
- vacuum_multixact_freeze_table_age.

Mặc định và tương tác giữa các tham số thay đổi theo version. Kiểm tra pg_settings thay vì sao chép cấu hình từ một bài viết cũ.

### 11.1. Vì sao anti-wraparound cần theo dõi riêng?

Một bảng có rất ít UPDATE/DELETE vẫn có thể có tuple rất cũ. Ngược lại, một bảng churn cao có nhiều dead tuples nhưng XID age chưa gần ngưỡng. Hai vấn đề cần hai nhóm tín hiệu.

### 11.2. Khi nào phải ưu tiên ngay?

- XID age tăng nhanh và tiến gần freeze max age.
- Log có cảnh báo wraparound.
- Autovacuum anti-wraparound không hoàn thành hoặc bị cản.
- Một số relation có relfrozenxid rất cũ.
- Database tiến gần trạng thái bảo vệ ghi do wraparound.

### 11.3. Không tắt autovacuum để giải quyết tải

Nếu autovacuum đang làm tăng I/O, cần điều chỉnh cost/workers/scheduling dựa trên số đo. Tắt nó có thể biến một vấn đề tải có thể điều chỉnh thành sự cố wraparound.

## 12. Evidence 4: long-running transactions và xmin horizon

Một transaction giữ snapshot cũ có thể khiến VACUUM không loại bỏ tuple versions mà transaction đó vẫn cần.

Tìm các transaction lâu:

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    now() - xact_start AS transaction_age,
    now() - query_start AS query_age,
    backend_xmin,
    wait_event_type,
    wait_event,
    left(query, 250) AS query_excerpt
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

### 12.1. Không chỉ tìm active queries

Một session idle in transaction có thể giữ transaction mở dù không chạy query. Đây là dấu hiệu đáng chú ý khi vacuum không thu hồi được tuples.

### 12.2. Backend xmin

backend_xmin có thể giúp thấy snapshot horizon của backend. Giá trị NULL không tự chứng minh session không có ảnh hưởng khác; hãy kết hợp state, xact_start và transaction context.

### 12.3. Không terminate session chỉ vì lâu

Một transaction lâu có thể là batch job hợp lệ. Xác định owner, query, locks, business impact và khả năng rollback trước khi terminate.

### 12.4. Kiểm soát từ ứng dụng

- Không giữ transaction mở qua remote API hoặc user interaction.
- Đảm bảo exception paths luôn rollback/close transaction.
- Cấu hình timeout phù hợp.
- Theo dõi connection pool và idle-in-transaction.
- Kiểm tra test framework có để transaction mở quá lâu không.

## 13. Evidence 5: replication slots và cleanup horizon

Replication slots có thể giữ WAL và trong một số trường hợp giữ xmin/catalog_xmin, làm chậm việc thu hồi tuple/catalog versions.

Kiểm tra:

```sql
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
```

### 13.1. Slot inactive không có nghĩa vô hại

Một slot không active nhưng vẫn giữ restart_lsn/xmin có thể giữ tài nguyên lâu dài. Cần xác định consumer có còn được sử dụng hay không.

### 13.2. Không xóa slot để “giải phóng vacuum” theo phản xạ

Xóa replication slot có thể làm consumer mất khả năng tiếp tục replication từ vị trí cũ và cần resync/rebuild. Xác nhận owner, retention và recovery plan trước.

### 13.3. WAL retention và vacuum retention là hai biểu hiện liên quan nhưng khác nhau

Slot có thể giữ WAL thông qua restart LSN; xmin/catalog_xmin có thể ảnh hưởng horizon cleanup. Kiểm tra từng cột, không kết luận từ một metric duy nhất.

## 14. Evidence 6: vacuum có đang chạy không và ở phase nào?

View pg_stat_progress_vacuum cho biết tiến độ vacuum đang hoạt động:

```sql
SELECT
    pid,
    relid::regclass AS relation_name,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed,
    index_vacuum_count,
    num_dead_tuples,
    max_dead_tuples
FROM pg_stat_progress_vacuum
ORDER BY pid;
```

Các cột/phase có thể thay đổi theo PostgreSQL version; kiểm tra view trên server thực tế.

### 14.1. Progress phase giúp phân biệt công việc

Một số phase có thể gồm:

- Scanning heap.
- Vacuuming indexes.
- Vacuuming heap.
- Cleaning up indexes.
- Truncating heap.
- Performing final cleanup.

Tên phase chính xác phụ thuộc version.

### 14.2. Tỷ lệ tiến độ không phải ETA tuyệt đối

heap_blks_scanned / heap_blks_total cho thấy tiến độ quét heap theo block. Nhưng thời gian còn lại còn phụ thuộc index cleanup, I/O, cost delay, lock waits và page skipping.

### 14.3. Nhiều vacuum cùng lúc có thể tạo cạnh tranh

Số worker, storage throughput và query workload đều có giới hạn. Tăng worker không tự làm tổng thời gian giảm nếu bottleneck là disk I/O hoặc CPU.

## 15. Evidence 7: lock waits và blockers

VACUUM thông thường có thể chạy đồng thời với nhiều thao tác đọc/ghi, nhưng vẫn có thể chờ một số locks hoặc bị ảnh hưởng bởi DDL/maintenance khác.

Tìm session đang bị block:

```sql
SELECT
    a.pid,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    pg_blocking_pids(a.pid) AS blocking_pids,
    now() - a.query_start AS query_age,
    left(a.query, 200) AS query_excerpt
FROM pg_stat_activity AS a
WHERE cardinality(pg_blocking_pids(a.pid)) > 0
ORDER BY a.query_start;
```

### 15.1. VACUUM FULL có lock mạnh

VACUUM FULL rewrite relation và thường yêu cầu ACCESS EXCLUSIVE lock, có thể chặn SELECT/DML trên bảng trong quá trình thực hiện.

### 15.2. Standard VACUUM vẫn có thể chịu tác động từ DDL

ALTER TABLE, DROP/REWRITE và các thao tác maintenance khác có thể xung đột về lock. Không lập lịch vacuum mà bỏ qua lịch migration/DDL.

### 15.3. Không nhầm lock wait với vacuum chậm do cost throttling

Một worker có thể chậm vì cost delay/I/O dù không có blocker. Xem wait events, progress view và log để phân biệt.

## 16. Evidence 8: autovacuum logs

Có thể cấu hình:

```conf
log_autovacuum_min_duration = '1s'
```

Đây là ví dụ ghi log các autovacuum vượt ngưỡng thời gian. Giá trị 0 có thể log mọi lần, còn -1 tắt logging theo tham số; hãy xác minh cú pháp/version và khối lượng log trước khi áp dụng.

Log có thể giúp nhận ra:

- Bảng được vacuum/analyze.
- Số pages scanned/vacuumed.
- Số dead tuples removed.
- Index cleanup và thời gian.
- Buffer/cost throttling.
- Vacuum bị skip hoặc không hoàn thành theo điều kiện.
- Thời gian từng phase/operation theo format của version.

### 16.1. Log volume là một chi phí

Log mọi autovacuum ở database lớn có thể tạo rất nhiều sự kiện. Có thể dùng ngưỡng thời gian, sampling và tập trung log theo bảng trọng yếu.

### 16.2. Liên kết log với relation identity

Tên schema/table, database, PID, duration và timestamp giúp liên kết với metrics. Không chỉ đọc một dòng log rồi kết luận toàn cluster ổn định.

## 17. Evidence 9: query performance và visibility map

Vacuum có thể cải thiện khả năng index-only scan khi page trở thành all-visible. Một tín hiệu có thể đến từ:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM public.orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 20;
```

Nếu plan có Index Only Scan, chú ý Heap Fetches.

### 17.1. Heap Fetches cao có thể là tín hiệu

Một index-only plan có nhiều heap fetches có thể liên quan page chưa all-visible. Nhưng cũng cần xét query selectivity, updates, vacuum history và các yếu tố khác.

### 17.2. Vacuum không tự sửa index design

Nếu query cần cột không có trong index, planner có thể chọn heap access. Nếu predicate/order không phù hợp index, vacuum không thay thế việc thiết kế index.

### 17.3. Không chạy VACUUM liên tục chỉ để đạt 0 heap fetches

VM thay đổi theo workload; UPDATE có thể clear bits. Cân bằng lợi ích index-only scan với chi phí vacuum và write workload.

## 18. Bảng evidence tổng hợp

| Tín hiệu | Nguồn quan sát | Câu hỏi cần trả lời |
|---|---|---|
| Dead tuple estimate | pg_stat_user_tables | Có tăng nhanh hay vượt ngưỡng hợp lý? |
| Modification count | n_mod_since_analyze | Planner statistics đã lỗi thời? |
| Insert/update/delete rate | Table stats hoặc telemetry | Churn loại nào đang tạo áp lực? |
| Table/index/TOAST size | Các hàm relation size | Thành phần nào tăng? |
| XID age | pg_database, age() | Có nguy cơ wraparound? |
| MultiXact age | datminmxid, relminmxid | Có cần freeze MultiXact? |
| Long transaction | pg_stat_activity | Snapshot nào đang giữ cleanup horizon? |
| Replication slot | pg_replication_slots | Slot nào giữ xmin/WAL? |
| Vacuum progress | pg_stat_progress_vacuum | Worker đang làm gì và tiến tới đâu? |
| Lock blockers | pg_blocking_pids, pg_locks | Có session nào cản trở? |
| Autovacuum history | Table stats, logs | Bảng có được xử lý thường xuyên? |
| Index-only heap fetches | EXPLAIN (ANALYZE, BUFFERS) | VM có đang hỗ trợ truy vấn? |
| Disk/I/O pressure | OS/cloud metrics | Maintenance có thể làm quá tải storage? |
| Replication lag | Replication monitoring | WAL/maintenance có ảnh hưởng replica? |
| Application latency | APM/metrics | Tác động người dùng có tăng không? |

Không dùng một metric đơn lẻ để quyết định thao tác rewrite.

## 19. Xây ngưỡng từ baseline, không sao chép số của người khác

Một tổ chức có thể đặt ngưỡng cảnh báo dead tuple 10%, nhưng con số đó không phải chuẩn chung cho PostgreSQL.

Cách xây baseline:

1. Thu thập metrics theo từng bảng trong giai đoạn đủ đại diện.
2. Ghi nhận workload giờ cao điểm/thấp điểm.
3. Đo tốc độ tăng dead tuples và table size.
4. Quan sát autovacuum duration, frequency và completion.
5. Đo query latency, index-only scans và disk I/O.
6. So sánh trước/sau các lần vacuum/analyze.
7. Xác định mức backlog mà ứng dụng vẫn đáp ứng SLO.
8. Đặt warning/critical thresholds theo risk và thời gian phản ứng.
9. Điều chỉnh theo từng nhóm bảng.
10. Review sau khi thay đổi traffic, schema hoặc version.

### 19.1. Dùng nhiều cấp cảnh báo

Ví dụ policy minh họa:

| Cấp | Tín hiệu | Phản ứng |
|---|---|---|
| Info | Autovacuum hoàn tất trong baseline | Ghi nhận, không can thiệp |
| Warning | Dead tuple growth tăng, vacuum lag kéo dài | Điều tra churn, workers, cost |
| Critical | Freeze age tiến gần ngưỡng hoặc anti-wraparound vacuum không hoàn thành | Ưu tiên xử lý ngay |
| Capacity | Table/TOAST/index growth vượt dự báo | Phân tích thành phần storage |
| Performance | Planner stats stale hoặc heap fetch tăng bất thường | ANALYZE/kiểm tra VM và query plan |

Các cấp chỉ là ví dụ; đặt ngưỡng thực tế theo tốc độ XID, workload và khả năng phản ứng.

### 19.2. Ngưỡng phải có thời gian duy trì

Một spike ngắn có thể không cần hành động. Dùng duration/persistence để giảm false alerts, trừ tín hiệu wraparound cần xử lý khẩn.

### 19.3. Tính tốc độ tiêu thụ ngân sách XID

Nếu XID age hiện tại là 100 triệu và tăng 2 triệu mỗi ngày, thời gian tới ngưỡng phải được ước lượng để có thời gian xử lý. Không đợi tới một con số cố định rồi mới gọi người trực.

## 20. Lập nhóm workload và chính sách khác nhau

Không đặt một ngưỡng vacuum cho tất cả tables. Có thể phân nhóm:

| Nhóm bảng | Đặc điểm | Bằng chứng ưu tiên |
|---|---|---|
| Hot OLTP | UPDATE/DELETE nhiều | Dead tuple growth, vacuum lag, lock/I/O |
| Append-only event | INSERT nhiều, ít update | Insert vacuum, freeze age, VM |
| Large history | Lớn, ít thay đổi | Freeze horizon, partition lifecycle |
| Queue/work table | INSERT/DELETE nhanh | Churn, dead tuples, index bloat |
| Reference tables | Nhỏ, ít thay đổi | Analyze khi load/migration |
| Partitioned fact table | Nhiều partitions | Per-partition churn, parent ANALYZE |
| TOAST-heavy documents | Giá trị lớn | TOAST size, update pattern, I/O |
| Materialized views | Refresh theo lịch | Analyze sau refresh, size/lock |

### 20.1. Hot OLTP table

Có thể cần scale factor nhỏ hơn để autovacuum xử lý sớm, cost limit đủ cao và giám sát latency chặt.

### 20.2. Append-only table

Theo dõi insert-triggered vacuum và freeze age. Nếu chỉ nhìn n_dead_tup, có thể bỏ qua nhu cầu VM/freeze.

### 20.3. Queue table

Một queue có INSERT/DELETE liên tục có thể tạo churn lớn. Cân nhắc partitioning/retention, batching và index design cùng với autovacuum.

### 20.4. History table

Partition theo thời gian có thể giúp drop/detach partition cũ nhanh hơn xóa hàng triệu rows, tùy retention requirements. Tuy nhiên mỗi partition vẫn cần analyze/freeze theo lifecycle của nó.

## 21. Điều chỉnh autovacuum theo bảng

PostgreSQL cho phép storage parameters per-table, ví dụ:

```sql
ALTER TABLE public.orders SET (
    autovacuum_vacuum_threshold = 5000,
    autovacuum_vacuum_scale_factor = 0.02,
    autovacuum_analyze_threshold = 5000,
    autovacuum_analyze_scale_factor = 0.01
);
```

Các số chỉ là ví dụ minh họa, không phải khuyến nghị chung. Hãy tính ngưỡng từ row estimates, churn và thời gian vacuum thực tế.

### 21.1. Vì sao scale factor thấp hơn có thể hữu ích?

Bảng lớn có thể tích lũy quá nhiều dead tuples trước khi chạm ngưỡng mặc định. Giảm scale factor giúp trigger sớm hơn.

### 21.2. Vì sao threshold tuyệt đối vẫn quan trọng?

Với bảng rất nhỏ, số tuyệt đối có thể chi phối. Nếu đặt threshold quá thấp, vacuum/analyze có thể chạy quá thường xuyên.

### 21.3. Đừng giảm threshold mọi bảng cùng lúc

Nếu hàng nghìn bảng cùng đạt threshold, worker pool có thể bị quá tải. Điều chỉnh theo nhóm, quan sát queue và duration.

### 21.4. Xác nhận reloptions sau thay đổi

```sql
SELECT
    c.oid::regclass AS relation,
    c.reloptions
FROM pg_class AS c
WHERE c.oid = 'public.orders'::regclass;
```

Đây là kiểm tra cấu hình lưu trên relation; không chứng minh vacuum đã chạy hay threshold đã đạt.

## 22. Cost-based vacuum delay: điều tiết I/O

VACUUM có cost-based delay để tránh chiếm dụng tài nguyên quá mức. Các tham số liên quan gồm:

- vacuum_cost_delay.
- vacuum_cost_limit.
- autovacuum_vacuum_cost_delay.
- autovacuum_vacuum_cost_limit.
- vacuum_cost_page_hit.
- vacuum_cost_page_miss.
- vacuum_cost_page_dirty.

### 22.1. Cost limit thấp

Vacuum nhường tài nguyên nhiều hơn nhưng có thể kéo dài, khiến dead tuples tồn tại lâu hơn.

### 22.2. Cost limit cao hoặc delay thấp

Vacuum hoàn thành nhanh hơn trong một số workload nhưng có thể cạnh tranh I/O/CPU với ứng dụng và replication.

### 22.3. Cost limit và nhiều workers

Khi nhiều autovacuum workers hoạt động, cost budget có thể được chia sẻ theo cơ chế của phiên bản. Không nhân số worker với cost limit rồi giả định tổng I/O cố định; xem tài liệu/version và đo thực tế.

### 22.4. Đừng tối ưu duration đơn lẻ

Mục tiêu là cân bằng dead tuple backlog, query latency, disk throughput, replication lag, XID age và vacuum completion time. Một vacuum chạy 30 phút có thể phù hợp nếu xử lý bảng lớn mà không ảnh hưởng SLO.

## 23. Workers và capacity planning

Các tham số:

- autovacuum_max_workers.
- autovacuum_naptime.
- autovacuum_work_mem.
- autovacuum_vacuum_cost_limit.
- autovacuum_vacuum_cost_delay.

### 23.1. Tăng workers khi nào?

Có bằng chứng nhiều bảng cùng chờ autovacuum, worker luôn bận và storage/CPU còn headroom.

### 23.2. Không tăng workers khi disk đã bão hòa

Thêm workers có thể làm I/O queue dài hơn, khiến query người dùng chậm hơn.

### 23.3. Memory cho dead tuple tracking

Bảng có rất nhiều dead tuples/indexes có thể cần bộ nhớ cho vacuum. Nếu memory không đủ, vacuum có thể phải chia thành nhiều index cleanup cycles. Theo dõi logs/progress và cân nhắc autovacuum_work_mem theo RAM/worker budget.

### 23.4. Capacity không chỉ là worker count

Cần xét số relations, churn, index count, table sizes, storage throughput, WAL/replication và thời gian cho maintenance.

## 24. Partitioning và lịch bảo trì

Partitioning thay đổi cách lập lịch:

- Một partition cũ có thể gần như read-only.
- Partition hiện tại có churn cao.
- Partition mới vừa bulk load cần ANALYZE.
- Partition cũ có thể được detach/drop theo retention thay vì DELETE từng row.
- Parent partitioned table có thể cần ANALYZE thủ công để planner có statistics phù hợp.

### 24.1. Bảng parent và child

```sql
SELECT
    inhparent::regclass AS parent_table,
    inhrelid::regclass AS partition_table
FROM pg_inherits
WHERE inhparent = 'public.events'::regclass
ORDER BY inhrelid::regclass::text;
```

Mỗi partition là relation riêng có size, statistics, reloptions và maintenance state riêng.

### 24.2. Load partition mới

Sau bulk load, chạy ANALYZE partition/parent theo nhu cầu query planner. Đừng giả định autovacuum đã cập nhật mọi statistics ngay sau thao tác attach.

### 24.3. Retention bằng DROP/DETACH

Drop partition có thể nhanh hơn DELETE nhiều rows và vacuum cleanup, nhưng DDL lock, FK dependencies, replication, backup/retention và concurrent queries cần được đánh giá.

### 24.4. Partition cũ vẫn cần freeze

Read-only không đồng nghĩa miễn bảo trì XID. Theo dõi age của các partition cũ và TOAST relation liên quan.

## 25. Lịch maintenance nên có nhiều loại trigger

Một lịch vận hành thực tế có thể phối hợp:

1. Continuous autovacuum: xử lý threshold bình thường.
2. Metrics scrape: thu thập table stats, XID age, progress, blockers.
3. Event-triggered manual VACUUM: khi backlog hoặc lag vượt policy.
4. Event-triggered ANALYZE: sau bulk load hoặc data distribution change.
5. Freeze-priority maintenance: theo XID/MultiXact horizon.
6. Capacity review: xem table/index/TOAST growth.
7. Rewrite/reindex window: chỉ khi có evidence và kế hoạch riêng.
8. Post-maintenance verification: xác nhận mục tiêu đã đạt.

### 25.1. Không phải mọi việc đều cần cron

Metrics có thể được scrape định kỳ; autovacuum tự chạy theo trigger; manual action chỉ xảy ra khi điều kiện cụ thể được thỏa.

### 25.2. Lịch giờ thấp điểm không thay thế trigger

Nếu freeze age tới ngưỡng nguy hiểm lúc 14:00, không nên đợi đến cửa sổ cuối tuần chỉ vì lịch. Ưu tiên dựa trên risk, không dựa vào tên ngày.

### 25.3. Lịch phải xét thời gian hoàn thành

Một vacuum bảng 2 TB có thể chạy nhiều giờ. Nếu bắt đầu quá muộn trong maintenance window, nó có thể kéo dài qua giờ cao điểm. Ước lượng duration từ lịch sử và có monitoring.

## 26. Quyết định VACUUM hay VACUUM (ANALYZE)?

Dùng VACUUM khi evidence chủ yếu là dead tuples/free-space/freeze/visibility maintenance.

Dùng ANALYZE khi evidence chủ yếu là statistics stale hoặc planner estimate sai.

Dùng VACUUM (ANALYZE) khi cả hai nhu cầu cùng tồn tại và thao tác kết hợp phù hợp.

Ví dụ targeted:

```sql
VACUUM (ANALYZE, VERBOSE) public.orders;
```

VACUUM phải chạy ngoài transaction block thông thường. Không đặt trong transaction do ứng dụng tự mở nếu server cấm thao tác đó.

### 26.1. VERBOSE hỗ trợ điều tra

Output/log có thể cho biết pages, tuples, index cleanup và freeze details tùy version. Dùng để ghi lại bằng chứng trước/sau.

### 26.2. Analyze một số cột

```sql
ANALYZE public.orders (status, customer_id, created_at);
```

Có thể tiết kiệm phạm vi khi chỉ một số cột quan trọng cần statistics, nhưng chọn cột dựa trên query patterns.

### 26.3. Đừng dùng VACUUM để sửa query chậm không liên quan

Nếu plan chọn sequential scan vì bảng nhỏ, predicate không selective hoặc query trả phần lớn dữ liệu, vacuum có thể không thay đổi kết quả đáng kể.

## 27. Khi nào cần VACUUM FREEZE?

VACUUM FREEZE hoặc VACUUM (FREEZE) yêu cầu vacuum freeze mạnh hơn theo semantics của PostgreSQL. Đây không phải lệnh phải chạy trên mọi bảng mỗi đêm.

Có thể cân nhắc khi:

- XID age cần được giảm có kế hoạch.
- Table sắp trở thành read-only dài hạn.
- Cần chuẩn bị dữ liệu trước một workflow snapshot/backup phù hợp.
- Có yêu cầu freeze maintenance cụ thể sau bulk load.
- Cần xử lý tình huống vận hành theo khuyến nghị PostgreSQL.

### 27.1. Freeze không thay retention

Freeze không xóa dữ liệu và không làm relation nhỏ lại.

### 27.2. Freeze vẫn cần snapshot horizon phù hợp

Một transaction/snapshot cũ có thể hạn chế những tuple nào được freeze/thu hồi trong lần chạy.

### 27.3. Không lạm dụng FREEZE để đạt một con số đẹp

Theo dõi XID/MultiXact age và kết quả vacuum. Một lần freeze có thể tốn I/O lớn; chọn thời điểm theo risk và workload.

## 28. Khi nào mới cân nhắc VACUUM FULL?

VACUUM FULL nhằm rewrite relation để thu hồi space về filesystem. Chỉ cân nhắc khi:

- Có bằng chứng relation chứa lượng free/dead space lớn khó tái sử dụng trong workload.
- Disk pressure thực sự cần reclaim.
- Có đủ dung lượng tạm cho rewrite.
- Có maintenance window và chấp nhận lock mạnh.
- Đã đánh giá long transactions, replication và downstream impact.
- Có backup/restore và kế hoạch xử lý nếu thất bại.

Ví dụ:

```sql
VACUUM FULL public.orders;
```

### 28.1. Tác động lock

VACUUM FULL thường cần ACCESS EXCLUSIVE lock, chặn truy cập khác vào relation trong quá trình rewrite.

### 28.2. Dung lượng tạm

Rewrite có thể cần không gian để tạo bản mới trước khi thay thế bản cũ. Một filesystem đã gần đầy có thể khiến thao tác thất bại hoặc làm hệ thống gặp sự cố.

### 28.3. WAL và replication

Rewrite có thể tạo nhiều I/O/WAL và tác động replication/storage. Đo và lập kế hoạch với kích thước relation thực tế.

### 28.4. VACUUM FULL không nên là cron định kỳ

Nếu tuần nào cũng cần VACUUM FULL, hãy điều tra autovacuum threshold/worker lag, long transactions, replication slots, UPDATE pattern/HOT ratio, schema/partition/retention, index bloat và storage growth thực tế.

### 28.5. Công cụ rewrite online

Một số hệ thống dùng extension/tool như pg_repack để giảm thời gian khóa so với VACUUM FULL, nhưng đây là công cụ riêng có prerequisites, trigger/temporary storage và trade-offs. Không coi nó là lệnh core miễn phí hoặc không cần kiểm thử.

## 29. Khi nào cần REINDEX?

REINDEX xây dựng lại index. Nó không phải phương án thay thế VACUUM cho heap.

Bằng chứng có thể gồm:

- Index size tăng bất thường so với heap/row count.
- Index-specific bloat evidence từ công cụ phù hợp.
- Index corruption hoặc invalid state được xác nhận.
- Một số pattern delete/update khiến index entries không được cleanup như kỳ vọng.
- Query plan/index performance cho thấy vấn đề sau khi loại trừ nguyên nhân khác.

### 29.1. Xem index sizes

```sql
SELECT
    schemaname,
    relname AS table_name,
    indexrelname AS index_name,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY pg_relation_size(indexrelid) DESC
LIMIT 30;
```

Một index lớn không tự động là bloat; có thể chứa nhiều key/INCLUDE columns hoặc phục vụ workload hợp lệ.

### 29.2. REINDEX CONCURRENTLY

Với phiên bản hỗ trợ, có thể cân nhắc:

```sql
REINDEX INDEX CONCURRENTLY public.idx_orders_customer;
```

Nó có trade-offs, nhiều phase và yêu cầu không chạy trong transaction block thông thường. Kiểm tra tài liệu version và theo dõi disk/locks.

### 29.3. Index cleanup trong VACUUM

Standard VACUUM có thể làm index cleanup để loại bỏ index entries liên quan tuple chết. Tuy nhiên điều đó không có nghĩa mọi loại index bloat đều được giải quyết hoàn toàn.

## 30. Tránh chạy toàn bộ database theo một chu kỳ cứng

Một job:

```text
Every Sunday 02:00:
  VACUUM FULL every table
  REINDEX every index
  ANALYZE every table
```

có thể gây lock, I/O và WAL lớn mà không dựa trên nhu cầu cụ thể.

Một lịch dựa trên evidence thay thế:

```text
Continuous:
  autovacuum + autoanalyze
  scrape stats and XID age

When churn threshold exceeded:
  inspect blockers and run targeted VACUUM

After bulk load / planner drift:
  targeted ANALYZE

When freeze risk rises:
  prioritize anti-wraparound/freeze work

When storage reclaim is proven necessary:
  plan a rewrite/repack window

After every intervention:
  verify metrics and record outcome
```

### 30.1. Bảng ít thay đổi có thể không cần VACUUM thường xuyên

Nhưng vẫn cần theo dõi freeze age và các yêu cầu visibility/maintenance.

### 30.2. Bảng nhiều thay đổi có thể cần autovacuum liên tục

Không nhất thiết chờ cửa sổ đêm nếu backlog tăng nhanh và ảnh hưởng truy vấn.

### 30.3. “Chạy định kỳ” vẫn có thể hữu ích

Một số tổ chức có health checks hoặc analyze sau load theo lịch. Điểm khác là thao tác có mục tiêu, baseline và verification; không phải cứ đến giờ là rewrite toàn bộ database.

## 31. Thực hành: dashboard bảng cần chú ý

Một query tổng hợp có thể làm điểm khởi đầu:

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
    s.n_mod_since_analyze,
    s.last_autovacuum,
    s.last_autoanalyze,
    s.autovacuum_count,
    pg_size_pretty(pg_total_relation_size(s.relid)) AS total_size
FROM pg_stat_user_tables AS s
ORDER BY
    s.n_dead_tup DESC,
    pg_total_relation_size(s.relid) DESC
LIMIT 50;
```

### 31.1. Cách đọc

- Dead tuples cao: kiểm tra tốc độ tăng, vacuum history và snapshot horizons.
- Modifications cao: xem analyze freshness và query plan.
- Size lớn: tách main/TOAST/index.
- Autovacuum count thấp: không tự kết luận daemon hỏng; bảng có thể ít churn hoặc chưa đạt threshold.
- Last autovacuum cũ: kết hợp n_dead_tup và XID age trước khi hành động.

### 31.2. Dashboard không phải lệnh tự động

Đừng lấy top 50 rồi tự động chạy VACUUM FULL. Dashboard cung cấp bằng chứng để DBA quyết định đúng operation.

## 32. Thực hành: theo dõi XID risk

```sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age,
    current_setting('autovacuum_freeze_max_age')::bigint
        AS freeze_max_age,
    round(
        100.0 * age(datfrozenxid)
        / NULLIF(
            current_setting('autovacuum_freeze_max_age')::bigint,
            0
        ),
        2
    ) AS percent_of_configured_max
FROM pg_database
ORDER BY xid_age DESC;
```

### 32.1. Cách đọc

Tỷ lệ gần 100% là tín hiệu khẩn theo ngưỡng cấu hình, nhưng cần xét các giới hạn/trigger cụ thể của version và database. Không chờ đến 100% mới alert.

### 32.2. Theo dõi xu hướng

Lưu metric theo phút/giờ/ngày để biết:
- Age đang tăng hay giảm.
- Tốc độ tăng.
- Vacuum anti-wraparound có xử lý được không.
- Một database cụ thể có tiến gần ngưỡng nhanh hơn phần còn lại không.

### 32.3. Cluster nhiều database

Xếp hạng tất cả database; một database ít được sử dụng vẫn có thể giữ datfrozenxid cũ và ảnh hưởng khả năng quản lý cluster.

## 33. Thực hành: tìm vacuum đang chạy và transaction gây trì hoãn

Progress:

```sql
SELECT
    p.pid,
    p.relid::regclass AS relation_name,
    p.phase,
    p.heap_blks_total,
    p.heap_blks_scanned,
    p.heap_blks_vacuumed
FROM pg_stat_progress_vacuum AS p;
```

Long transactions:

```sql
SELECT
    pid,
    application_name,
    usename,
    state,
    now() - xact_start AS xact_age,
    backend_xmin,
    wait_event_type,
    wait_event,
    left(query, 200) AS query_excerpt
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

### 33.1. Cần tương quan PID

Kết hợp PID từ progress với pg_stat_activity để thấy application, state và wait event. Không suy ra từ phase duy nhất.

### 33.2. Nếu không thấy vacuum progress

Có thể không có vacuum đang chạy, hoặc bạn thiếu quyền xem thông tin. Xác minh privileges và query view phù hợp.

### 33.3. Tìm replication slots

```sql
SELECT
    slot_name,
    active,
    xmin,
    catalog_xmin,
    restart_lsn
FROM pg_replication_slots;
```

Nếu thấy slot giữ xmin lâu, xác định consumer/owner và kế hoạch xử lý trước khi drop slot.

## 34. Thực hành: điều chỉnh một bảng có churn cao

Giả sử bảng public.orders có 20 triệu rows, UPDATE/DELETE thường xuyên và dead tuple backlog tăng nhanh. Sau khi đo baseline, DBA có thể thử cấu hình minh họa:

```sql
ALTER TABLE public.orders SET (
    autovacuum_vacuum_threshold = 5000,
    autovacuum_vacuum_scale_factor = 0.02,
    autovacuum_analyze_threshold = 5000,
    autovacuum_analyze_scale_factor = 0.01
);
```

### 34.1. Trước khi thay đổi

Ghi lại dead tuple estimates/growth rate, autovacuum duration/frequency, query p95/p99, disk I/O/queue, XID age, transaction/replication horizons và index count/size.

### 34.2. Sau khi thay đổi

Quan sát cùng các metrics trong workload tương đương. Mục tiêu có thể là backlog thấp hơn, vacuum hoàn thành trước khi ảnh hưởng query, XID age ổn định, latency không tăng đáng kể và storage growth có thể giải thích.

### 34.3. Nếu vacuum chạy quá thường xuyên

Threshold có thể quá thấp, worker capacity/cost delay chưa phù hợp hoặc churn cao hơn dự kiến. Điều chỉnh threshold có đo lường, không tắt autovacuum.

### 34.4. Nếu vacuum không bắt kịp

Kiểm tra blockers, long snapshots, workers, cost throttling, indexes và storage. Chỉ tăng cost limit/workers khi hệ thống còn headroom.

## 35. Bảng quyết định: bằng chứng nào dẫn tới thao tác nào?

| Bằng chứng chính | Hành động thường xem xét | Tránh phản xạ |
|---|---|---|
| Dead tuples tăng, autovacuum lag | Điều tra horizon/worker; targeted VACUUM nếu cần | VACUUM FULL ngay |
| Modifications lớn, planner estimates lệch | ANALYZE | REINDEX |
| XID age gần ngưỡng | Ưu tiên freeze/anti-wraparound vacuum | Chờ lịch cuối tuần |
| MultiXact age cao | Kiểm tra MultiXact freeze và vacuum | Chỉ nhìn dead tuples |
| Long transaction giữ xmin | Xử lý owner/transaction lifecycle | Chạy VACUUM liên tục |
| Replication slot giữ xmin/WAL | Điều tra consumer/retention | Drop slot tùy tiện |
| Main heap lớn nhưng free space tái sử dụng tốt | Theo dõi/reuse | Rewrite chỉ để giảm file |
| Heap bloat đã xác nhận, cần reclaim | Kế hoạch VACUUM FULL/pg_repack | Cron VACUUM FULL |
| Index-specific bloat/corruption evidence | REINDEX phù hợp | VACUUM FULL thay mọi việc |
| Index-only scan heap fetch tăng | Kiểm tra VM, update churn, vacuum | Chạy VACUUM liên tục |
| Bulk load/partition attach | ANALYZE partition/parent theo nhu cầu | Chờ statistics tự đúng |
| I/O saturation trong autovacuum | Điều chỉnh cost/workers và workload | Tăng workers vô hạn |
| Autovacuum không có activity nhưng bảng ít churn | Tiếp tục quan sát | Coi daemon hỏng |
| Table growth do dữ liệu sống | Capacity planning/partition retention | Gọi đó là bloat |

## 36. Lập lịch theo rủi ro và workload

Một chính sách có thể chia thành các vòng:

### Liên tục

- Autovacuum/autoanalyze hoạt động.
- Thu thập dead tuples, modifications, size, XID age.
- Theo dõi long transactions, replication slots và blockers.
- Alert khi freeze risk hoặc backlog vượt baseline.

### Sau sự kiện dữ liệu

- Sau bulk load: ANALYZE.
- Sau attach partition: ANALYZE parent/partition phù hợp.
- Sau migration làm thay đổi phân bố dữ liệu: ANALYZE.
- Sau một đợt delete/update lớn: theo dõi VACUUM và storage.
- Sau restore/upgrade: kiểm tra statistics và maintenance state.

### Theo cửa sổ bảo trì

- Review bloat và storage capacity.
- Thực hiện REINDEX hoặc rewrite khi có evidence.
- Xem lại table-level autovacuum parameters.
- Kiểm tra XID/MultiXact horizons.
- Thực hiện kiểm tra restore/replication sau thay đổi lớn.

### Khẩn cấp

- XID age tiến sát ngưỡng nguy hiểm.
- Autovacuum anti-wraparound không hoàn thành.
- Disk gần đầy và relation tăng bất thường.
- Vacuum không thể tiến triển do blockers/horizon.
- Sự cố corruption hoặc index invalid cần recovery plan.

Cửa sổ bảo trì là công cụ quản lý tác động, không phải lý do trì hoãn một rủi ro dữ liệu nghiêm trọng.

## 37. Runbook bảo trì theo bằng chứng

**Bước 1 — Thu thập trạng thái.** Lấy table stats, relation sizes, XID age, vacuum progress, activity, locks, slots và I/O.

**Bước 2 — Xác định loại vấn đề.** Dead tuple backlog, stale planner stats, freeze risk, index bloat, heap bloat, blocker hay disk pressure.

**Bước 3 — Xác định owner và tác động.** Bảng thuộc service nào? Có workload cao điểm không? Có replica/CDC/backup phụ thuộc không?

**Bước 4 — Chọn thao tác nhỏ nhất đủ giải quyết.** VACUUM, ANALYZE, điều chỉnh threshold, xử lý transaction/slot, REINDEX hoặc rewrite theo bằng chứng.

**Bước 5 — Kiểm tra prerequisites.** Quyền, disk headroom, lock impact, WAL/replication, maintenance window, rollback/restore.

**Bước 6 — Thực hiện và giám sát.** Theo dõi progress, locks, latency, I/O, replication lag và logs.

**Bước 7 — Xác minh mục tiêu.** Dead tuples/growth, XID age, stats/plans, free-space reuse và storage đã thay đổi đúng hướng chưa?

**Bước 8 — Ghi nhận kết quả.** Lưu thời điểm, relation, evidence trước/sau, command, duration, warnings và người chịu trách nhiệm.

## 38. Verification sau VACUUM

Sau khi chạy targeted vacuum, kiểm tra:

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
WHERE schemaname = 'public'
  AND relname = 'orders';
```

Kết hợp:
- pg_relation_size/pg_total_relation_size.
- age(relfrozenxid) hoặc database XID age.
- pg_stat_progress_vacuum khi đang chạy.
- pg_stat_activity và pg_locks.
- Query plan/Heap Fetches nếu VM là mục tiêu.
- Application latency và I/O.

### 38.1. Đừng mong dead tuples luôn về 0

Concurrent workload tiếp tục UPDATE/DELETE. Stats là estimates và cleanup bị giới hạn bởi snapshot horizon.

### 38.2. Đừng mong file size giảm sau VACUUM thường

Mục tiêu thường là tái sử dụng không gian. Nếu file size giữ nguyên nhưng dead tuples giảm và page reuse tốt hơn, thao tác vẫn có thể thành công.

### 38.3. Đừng kết luận thành công chỉ từ command exit code

Một VACUUM hoàn tất không chứng minh đã giải quyết nguyên nhân: long transaction/replication slot có thể tiếp tục giữ versions, churn có thể tái tạo backlog, hoặc index bloat vẫn còn.

## 39. Verification sau ANALYZE

Kiểm tra:
- last_analyze/last_autoanalyze.
- Query plan estimated rows vs actual rows.
- Join order và scan strategy.
- Query latency theo workload đại diện.
- Statistics target của các cột quan trọng.

Ví dụ:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM public.orders
WHERE status = 'PENDING';
```

Nếu estimated rows và actual rows còn chênh lớn, cần điều tra skew, correlation, extended statistics hoặc query predicate. Chạy ANALYZE không bảo đảm planner tự chọn plan tối ưu trong mọi trường hợp.

## 40. Verification sau VACUUM FULL hoặc REINDEX

### VACUUM FULL

- Xác nhận relation size sau rewrite.
- Xác nhận disk headroom không bị cạn.
- Xác nhận lock release và ứng dụng truy cập bình thường.
- Kiểm tra replication lag/WAL impact.
- Kiểm tra indexes và query latency sau rewrite.
- Xác nhận backup/recovery plan nếu có sự cố.

### REINDEX

- Xác nhận index hợp lệ/ready theo catalog.
- Kiểm tra size và query plans.
- Kiểm tra locks/downtime impact.
- Kiểm tra unique constraints nếu thao tác thất bại giữa chừng.
- Xác nhận các index phụ thuộc được xử lý đúng.

Không coi hai thao tác này là một loại maintenance giống nhau.

## 41. Những lỗi khi lập lịch bảo trì

### Lỗi 1 — VACUUM FULL toàn bộ database mỗi tuần

Tạo lock và I/O lớn; không có bằng chứng từng bảng cần rewrite.

### Lỗi 2 — VACUUM theo giờ nhưng không theo dõi kết quả

Có thể lặp thao tác vô ích trong khi nguyên nhân thực là long transaction.

### Lỗi 3 — Tắt autovacuum vì thấy CPU tăng

Có thể làm dead tuples và freeze age tích lũy, tạo rủi ro lớn hơn.

### Lỗi 4 — Chỉ nhìn n_dead_tup

Bỏ qua XID age, insert-vacuum, visibility map và statistics.

### Lỗi 5 — Chỉ nhìn table size

Không phân biệt dữ liệu sống, TOAST, indexes và free space tái sử dụng.

### Lỗi 6 — Dùng một scale factor cho mọi bảng

Bảng nhỏ, lớn, hot OLTP và append-only có workload khác nhau.

### Lỗi 7 — Giảm threshold quá thấp trên toàn cluster

Có thể tạo nhiều vacuum/analyze đồng thời và tăng I/O/worker contention.

### Lỗi 8 — Tăng workers mà không đo storage headroom

Nhiều worker có thể làm disk saturation nặng hơn.

### Lỗi 9 — Chạy vacuum khi transaction cũ vẫn giữ horizon

Vacuum có thể chạy nhưng không thu hồi được những tuple cần thiết.

### Lỗi 10 — Xóa replication slot để vacuum nhanh hơn

Có thể làm mất khả năng tiếp tục replication và buộc consumer resync.

### Lỗi 11 — Gọi mọi storage growth là bloat

Dữ liệu sống, index/TOAST growth và partition retention có thể là nguyên nhân hợp lệ.

### Lỗi 12 — Chạy ANALYZE rồi kết luận dead tuples đã được dọn

ANALYZE chỉ cập nhật statistics.

### Lỗi 13 — Chạy REINDEX để sửa heap bloat

REINDEX xây index, không rewrite heap.

### Lỗi 14 — Chạy VACUUM FULL mà không có disk headroom

Rewrite cần thêm dung lượng tạm và có thể thất bại khi disk gần đầy.

### Lỗi 15 — Chạy VACUUM trong transaction block

VACUUM thông thường không thể chạy bên trong transaction block. Dùng session/connection phù hợp.

### Lỗi 16 — Chỉ theo dõi tiến độ bằng thời gian đã chạy

Một vacuum lâu có thể đang tiến triển tốt; một vacuum mới chạy ít phút có thể bị block. Dùng progress và wait events.

### Lỗi 17 — Không ghi baseline trước maintenance

Không thể biết thao tác cải thiện hay làm xấu latency/storage.

### Lỗi 18 — Không xác minh sau maintenance

Command thành công không chứng minh mục tiêu nghiệp vụ/operational đã đạt.

### Lỗi 19 — Quên partitioned parent statistics

Planner có thể dùng statistics không phù hợp sau partition load/attach.

### Lỗi 20 — Không theo dõi MultiXact

XID age có thể bình thường trong khi MultiXact freeze pressure cần chú ý.

## 42. Ví dụ policy cho ba nhóm bảng

Các số bên dưới chỉ là minh họa để xây policy, không phải ngưỡng PostgreSQL chuẩn.

| Nhóm | Chính sách tham khảo | Bằng chứng quyết định |
|---|---|---|
| orders hot OLTP | Scale factor thấp hơn default, theo dõi vacuum duration thường xuyên | Update/delete rate, dead tuple growth, p95 |
| events append-only | Insert-vacuum/freeze và analyze sau bulk load | Insert rate, XID age, VM/index-only scans |
| audit_history partitioned | Theo dõi từng partition, analyze parent sau load/attach, retention bằng partition lifecycle | Partition size, freeze age, query plan |

### 42.1. Không dùng chính sách này mà chưa đo

Một bảng có 100 triệu rows và 1% churn có thể tạo nhiều dead tuples hơn bảng 100 nghìn rows với 20% churn. Cần xem số tuyệt đối, tốc độ và chi phí xử lý.

### 42.2. Ghi lại lý do của mỗi override

Khi đặt per-table reloptions, ghi workload pattern, threshold cũ/mới, evidence, mục tiêu, ngày review và người chịu trách nhiệm. Điều này giúp tránh cấu hình tạm thời tồn tại mãi sau khi workload thay đổi.

## 43. Tự động hóa an toàn

Có thể tự động hóa **thu thập metrics và cảnh báo** trước khi tự động hóa DDL/maintenance mạnh.

### 43.1. Mức tự động hóa thấp rủi ro

- Scrape pg_stat_user_tables.
- Scrape XID/MultiXact age.
- Ghi vacuum duration và progress.
- Alert khi long transaction/slot giữ horizon.
- Tính growth rate và dự báo threshold.
- Báo bảng chưa analyze sau bulk load.

### 43.2. Mức tự động hóa cần guardrails

- Targeted VACUUM/ANALYZE theo danh sách allowlist.
- Thay per-table reloptions theo policy versioned.
- Thực hiện maintenance ngoài peak khi đủ điều kiện.
- Throttle concurrency và dừng khi I/O/latency vượt giới hạn.

### 43.3. Không tự động chạy VACUUM FULL từ một metric duy nhất

Một dead tuple estimate cao không đủ chứng minh cần rewrite. Yêu cầu xác nhận bloat, disk need, lock window và storage headroom.

### 43.4. Idempotent scheduler

Job scheduler nên:
- Không chạy trùng một relation đồng thời ngoài kế hoạch.
- Có timeout và ghi nhận exit status.
- Không nuốt lỗi.
- Ghi evidence trước/sau.
- Có cơ chế pause khi hệ thống đang degraded.
- Không thay đổi quyền/role ngoài phạm vi cần thiết.

## 44. Lịch vận hành mẫu

### Hằng phút hoặc vài phút

- XID age và MultiXact age.
- Autovacuum progress.
- Long-running transactions.
- Replication slot horizon.
- Disk/I/O và replication lag.
- Alerts theo critical thresholds.

### Hằng giờ

- Dead tuple growth snapshots.
- Modification count/analyze freshness.
- Autovacuum activity/failure logs.
- Pool/DB latency và query workload.

### Hằng ngày

- Review top relations theo dead tuple growth và total size.
- Kiểm tra vacuum/analyze completion của bảng trọng yếu.
- Kiểm tra bảng bulk-loaded/partition mới.
- Review alerts unresolved.

### Hằng tuần hoặc theo chu kỳ review

- Đánh giá per-table thresholds/workers/cost.
- Review bloat evidence.
- Kiểm tra index growth và query plans.
- Review long transactions/replication slots.
- Lên kế hoạch rewrite/reindex nếu đã có bằng chứng.

### Theo sự kiện

- Sau restore/upgrade/bulk load.
- Sau schema migration/partition attach.
- Sau thay đổi traffic hoặc retention.
- Khi XID age tăng bất thường.
- Khi vacuum bị block hoặc disk gần đầy.

Đây là lịch quan sát và review; không có nghĩa mọi ngày/tuần phải chạy VACUUM FULL hoặc REINDEX.

## 45. Bài tập thực hành có đáp án

### Bài 1. Một cron VACUUM FULL toàn database mỗi Chủ nhật có phải chính sách tốt?

**Đáp án:** Không. Nó gây rewrite/lock/I/O trên mọi bảng bất kể nhu cầu. Hãy dùng autovacuum và chỉ lên kế hoạch rewrite khi evidence chứng minh cần reclaim space.

### Bài 2. VACUUM và ANALYZE khác nhau thế nào?

**Đáp án:** VACUUM quản lý tuple chết/free space/freeze; ANALYZE thu thập statistics cho planner.

### Bài 3. n_dead_tup có phải số tuple chết tuyệt đối?

**Đáp án:** Không. Đây là estimate trong statistics view.

### Bài 4. Bảng có 10 triệu rows, scale factor 0.2, threshold 50; vacuum threshold xấp xỉ?

**Đáp án:** 50 + 0.2 × 10.000.000 = 2.000.050 dead tuples, theo công thức khái quát của update/delete trigger.

### Bài 5. Scale factor 0.02 có nghĩa chạy vacuum mỗi 2 giờ?

**Đáp án:** Không. Nó là tỷ lệ theo số tuples ước lượng trong ngưỡng, không phải thời gian.

### Bài 6. Bảng append-only không có DELETE có cần vacuum?

**Đáp án:** Có thể cần insert-triggered vacuum, freeze và cập nhật VM; ít dead tuples không có nghĩa không cần maintenance.

### Bài 7. Sau bulk load lớn planner chọn plan kém; nên kiểm tra gì?

**Đáp án:** Statistics freshness và chạy ANALYZE phù hợp, sau đó so sánh EXPLAIN estimates/actual rows.

### Bài 8. ANALYZE có thu hồi dead tuples không?

**Đáp án:** Không.

### Bài 9. Database XID age được xem bằng gì?

```sql
SELECT datname, age(datfrozenxid)
FROM pg_database
ORDER BY age(datfrozenxid) DESC;
```

**Đáp án:** age(datfrozenxid) cho khoảng cách XID age ở cấp database.

### Bài 10. XID age là số ngày từ lần vacuum gần nhất?

**Đáp án:** Không. Nó là khoảng cách transaction ID, không phải thời gian.

### Bài 11. Autovacuum bị disable thì anti-wraparound vacuum có còn được bảo vệ?

**Đáp án:** PostgreSQL vẫn có thể khởi chạy vacuum khẩn cấp để chống wraparound; tuy vậy không được dựa vào đó thay autovacuum bình thường.

### Bài 12. Một transaction idle in transaction có thể cản VACUUM không?

**Đáp án:** Có, nếu giữ snapshot/horizon cũ khiến tuple versions vẫn cần thiết.

### Bài 13. Có nên terminate mọi transaction chạy trên 30 phút?

**Đáp án:** Không. Cần xác định owner, query, locks, snapshot impact và business consequences.

### Bài 14. Replication slot inactive có thể ảnh hưởng cleanup không?

**Đáp án:** Có. Slot có thể giữ xmin/catalog_xmin hoặc WAL retention dù không active.

### Bài 15. Xóa replication slot có an toàn để giải phóng vacuum horizon?

**Đáp án:** Không tự động. Có thể làm replication consumer mất khả năng tiếp tục và cần resync.

### Bài 16. pg_stat_progress_vacuum giúp gì?

**Đáp án:** Theo dõi relation, phase và số heap blocks scanned/vacuumed của vacuum đang chạy.

### Bài 17. Vacuum chạy 2 giờ có nghĩa bị treo?

**Đáp án:** Không. Cần xem progress, wait events, I/O, cost throttling và blockers.

### Bài 18. log_autovacuum_min_duration = 0 có trade-off gì?

**Đáp án:** Ghi mọi autovacuum, hữu ích điều tra nhưng có thể tạo log volume lớn.

### Bài 19. Heap lớn lên 20% có chứng minh bloat?

**Đáp án:** Không. Có thể dữ liệu sống tăng; cần tách live/dead, TOAST, indexes và free space.

### Bài 20. VACUUM thường có trả toàn bộ space về filesystem?

**Đáp án:** Không. Nó chủ yếu làm free space tái sử dụng; một số trailing pages có thể được truncate khi đủ điều kiện.

### Bài 21. Khi nào dùng VACUUM FULL?

**Đáp án:** Khi đã xác nhận cần reclaim filesystem space, có đủ disk headroom, chấp nhận ACCESS EXCLUSIVE lock và có kế hoạch vận hành.

### Bài 22. VACUUM FULL có phù hợp chạy cron hằng ngày?

**Đáp án:** Không.

### Bài 23. REINDEX có dọn heap bloat?

**Đáp án:** Không. Nó xây lại index.

### Bài 24. Index size lớn có tự chứng minh index bloat?

**Đáp án:** Không. Có thể index chứa nhiều keys/INCLUDE columns hoặc phục vụ lượng dữ liệu lớn; cần đánh giá theo row count và index-specific evidence.

### Bài 25. Vì sao bảng queue cần chính sách riêng?

**Đáp án:** INSERT/DELETE churn cao có thể tạo dead tuples và index cleanup pressure; retention/partitioning/batching cũng cần xem xét.

### Bài 26. n_mod_since_analyze cao gợi ý điều gì?

**Đáp án:** Statistics có thể stale; kiểm tra query plans và analyze threshold.

### Bài 27. Một partition mới vừa attach có cần ANALYZE parent?

**Đáp án:** Có thể cần để planner có statistics phù hợp; autovacuum không tự xử lý mọi thống kê của partitioned parent như mong đợi.

### Bài 28. Giảm autovacuum scale factor từ 0.2 xuống 0.02 sẽ luôn tốt hơn?

**Đáp án:** Không. Vacuum có thể chạy sớm hơn nhưng tăng I/O/worker pressure; phải đo.

### Bài 29. Tăng autovacuum workers có luôn giảm vacuum backlog?

**Đáp án:** Không nếu bottleneck là storage/CPU hoặc workers cùng cạnh tranh tài nguyên.

### Bài 30. Cost delay thấp hơn có ý nghĩa gì?

**Đáp án:** Vacuum thường chạy tích cực hơn và nhường ít thời gian hơn, nhưng có thể tăng contention/I/O.

### Bài 31. VM all-visible giúp gì?

**Đáp án:** Hỗ trợ index-only scan bỏ qua heap visibility checks khi đủ điều kiện.

### Bài 32. Có nên vacuum liên tục để Heap Fetches luôn bằng 0?

**Đáp án:** Không. UPDATE có thể clear VM bits; cần cân bằng chi phí vacuum và workload.

### Bài 33. Freeze có xóa dữ liệu cũ?

**Đáp án:** Không. Freeze quản lý transaction ID visibility, không phải retention/delete.

### Bài 34. MultiXact age có cần theo dõi riêng?

**Đáp án:** Có. MultiXact có ngưỡng freeze riêng và không được đại diện đầy đủ bởi XID age.

### Bài 35. pg_total_relation_size giúp phân biệt những gì?

**Đáp án:** Tổng table và indexes/TOAST liên quan; cần dùng thêm các hàm size khác để tách thành phần.

### Bài 36. Vacuum bị chậm, bước đầu nên xem gì?

**Đáp án:** Progress, wait events, blockers, cost throttling, long transactions và replication slots.

### Bài 37. Có thể chạy VACUUM trong BEGIN/COMMIT thông thường không?

**Đáp án:** Không. VACUUM không chạy trong transaction block thông thường.

### Bài 38. Sau VACUUM, file size không giảm nhưng dead tuples giảm; có thành công không?

**Đáp án:** Có thể thành công nếu mục tiêu là tái sử dụng free space và cleanup; không phải mọi vacuum đều reclaim filesystem.

### Bài 39. Sau ANALYZE, estimated rows vẫn sai xa; làm gì?

**Đáp án:** Kiểm tra skew, statistics target, extended statistics, predicate và query plan; ANALYZE không bảo đảm mọi estimate chính xác.

### Bài 40. Chọn hành động cho bảng có dead tuple tăng nhanh, XID age bình thường, một transaction giữ xmin nhiều giờ.

**Đáp án:** Điều tra transaction owner/horizon và xử lý nguyên nhân; targeted vacuum sau khi cleanup horizon cho phép. Chạy vacuum liên tục khi horizon chưa đổi có thể không giải quyết được backlog.

### Bài 41. Chọn hành động cho bảng insert-only lớn, index-only scan có nhiều heap fetches và freeze age tăng.

**Đáp án:** Kiểm tra insert-vacuum/freeze policy, VM coverage và query plan; targeted vacuum có thể phù hợp nếu đủ điều kiện.

### Bài 42. Chọn hành động khi chỉ planner statistics stale sau bulk load.

**Đáp án:** ANALYZE partition/table phù hợp, không cần VACUUM FULL.

### Bài 43. Chọn hành động khi index-specific bloat được xác nhận, heap bình thường.

**Đáp án:** Đánh giá REINDEX phù hợp, có thể CONCURRENTLY nếu version/operation hỗ trợ; không rewrite heap vô cớ.

### Bài 44. Chọn hành động khi heap bloat được xác nhận, disk gần đầy và không đủ temporary space.

**Đáp án:** Không bắt đầu VACUUM FULL. Cần capacity plan/giải phóng headroom và lựa chọn phương án rewrite an toàn.

### Bài 45. Một maintenance job cần ghi lại những gì?

**Đáp án:** Relation, trigger/evidence, command, start/end/duration, progress, locks, I/O/replication, kết quả trước/sau, warnings và người chịu trách nhiệm.

## 46. Checklist trước và sau bảo trì

| Giai đoạn | Câu hỏi |
|---|---|
| Trước | Mục tiêu là cleanup, analyze, freeze hay reclaim filesystem? |
| Trước | Có evidence cụ thể và baseline không? |
| Trước | XID/MultiXact age có khẩn cấp không? |
| Trước | Có long transactions hoặc replication slots giữ horizon? |
| Trước | Có blockers/DDL conflict không? |
| Trước | Storage có đủ headroom cho rewrite không? |
| Trước | I/O, CPU và replication còn headroom? |
| Trước | Có application SLO/peak window cần bảo vệ? |
| Trước | Lệnh có chạy được ngoài transaction block? |
| Trước | Quyền và extension cần thiết đã sẵn sàng? |
| Trong | Vacuum progress/phase có tiến triển? |
| Trong | Lock waits và query latency có tăng? |
| Trong | Disk/WAL/replication lag có vượt guardrail? |
| Sau | Dead tuple growth có giảm? |
| Sau | XID/MultiXact age có cải thiện? |
| Sau | Planner statistics/estimated rows có phù hợp hơn? |
| Sau | Table/index/TOAST size thay đổi ra sao? |
| Sau | VM/index-only heap fetch có cải thiện khi đó là mục tiêu? |
| Sau | Ứng dụng và replicas có bình thường? |
| Sau | Có cần thay threshold/worker/cost policy? |
| Sau | Kết quả đã được ghi lại và có ngày review tiếp? |

## 47. Tài liệu PostgreSQL chính thức

- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html) — VACUUM, ANALYZE, autovacuum và freezing.
- [VACUUM](https://www.postgresql.org/docs/current/sql-vacuum.html) — cú pháp, options và giới hạn vận hành.
- [ANALYZE](https://www.postgresql.org/docs/current/sql-analyze.html) — thu thập planner statistics.
- [Autovacuum Configuration](https://www.postgresql.org/docs/current/runtime-config-autovacuum.html) — trigger thresholds, workers, freeze và cost.
- [Vacuum Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html#VACUUM-PROGRESS-REPORTING) — pg_stat_progress_vacuum.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — table stats, activity, locks và database statistics.
- [pg_stat_activity](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-ACTIVITY-VIEW) — transactions và backend state.
- [pg_replication_slots](https://www.postgresql.org/docs/current/view-pg-replication-slots.html) — slot state, xmin và WAL positions.
- [Routine Reindexing](https://www.postgresql.org/docs/current/routine-reindex.html) — khi nào và cách reindex.
- [REINDEX](https://www.postgresql.org/docs/current/sql-reindex.html) — concurrent và non-concurrent reindex operations.
- [Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html) — lifecycle và maintenance của partitioned tables.

Các ngưỡng, view columns và options có thể thay đổi theo PostgreSQL version/distribution. Trước khi áp dụng, xác minh server_version, pg_settings, catalog và tài liệu đúng phiên bản đang vận hành.

## 48. Tổng kết: maintenance là một quyết định có bằng chứng

```text
Quan sát
   |
   +-- Dead tuples/churn tăng?
   |      -> kiểm tra vacuum trigger, horizon, worker
   |
   +-- Statistics stale?
   |      -> ANALYZE
   |
   +-- XID/MultiXact age tăng?
   |      -> ưu tiên freeze/anti-wraparound
   |
   +-- Long transaction/replication slot giữ cleanup?
   |      -> xử lý horizon trước
   |
   +-- Heap/index bloat đã xác nhận?
   |      -> chọn VACUUM / REINDEX / rewrite đúng mục tiêu
   |
   +-- Sau thao tác?
          -> đo lại, xác nhận và ghi nhận
```

Những nguyên tắc cần nhớ:

1. **Autovacuum là tuyến bảo trì thường xuyên.** Lịch thủ công nên bổ sung cho nhu cầu cụ thể, không thay thế daemon.
2. **Dead tuples, stale statistics và freeze age là ba vấn đề khác nhau.** Chúng cần các tín hiệu và thao tác khác nhau.
3. **Ngưỡng autovacuum phụ thuộc số tuples và scale factor.** Một cấu hình chung có thể không phù hợp với cả bảng nhỏ và bảng rất lớn.
4. **Insert-only table vẫn cần vacuum.** Freeze và visibility map vẫn quan trọng.
5. **Long transactions và replication slots có thể giữ tuple versions.** Vacuum chạy không có nghĩa cleanup chắc chắn đạt mục tiêu.
6. **XID/MultiXact age là tín hiệu bảo vệ tính đúng đắn.** Không chờ dead tuple percentage cao mới xử lý wraparound risk.
7. **VACUUM thường tạo free space để tái sử dụng.** Không đồng nghĩa file luôn nhỏ lại.
8. **VACUUM FULL là rewrite có lock và chi phí lớn.** Chỉ dùng khi cần reclaim filesystem space và có kế hoạch rõ.
9. **ANALYZE cập nhật statistics, REINDEX xây lại index.** Không dùng nhầm chúng để giải quyết một loại vấn đề khác.
10. **Workers/cost tuning là đánh đổi giữa backlog và tải hệ thống.** Tăng tốc vacuum có thể làm workload chính chậm hơn.
11. **Partition lifecycle là một phần của maintenance.** Analyze parent, freeze partitions và retention phải được thiết kế cùng nhau.
12. **Mọi thao tác cần verification.** Đo trước/sau, kiểm tra XID, dead tuples, plans, storage, locks và latency.

**Một câu để nhớ:** *Lập lịch VACUUM tốt không phải là chạy cùng một lệnh vào cùng một ngày; đó là quan sát churn, visibility, statistics, transaction horizons và storage, rồi chọn đúng thao tác vào đúng thời điểm với tác động đã được đo.*


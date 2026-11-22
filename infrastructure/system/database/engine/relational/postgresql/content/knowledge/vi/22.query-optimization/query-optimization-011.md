# Đo hồi quy hiệu năng sau thay đổi schema, dữ liệu hoặc cấu hình trong PostgreSQL

Trong PostgreSQL, một câu SQL không đổi vẫn có thể chạy chậm hơn sau khi triển khai:

- Thêm index để tăng tốc SELECT nhưng làm chi phí INSERT/UPDATE tăng.
- Thay đổi kiểu cột, constraint hoặc cấu trúc partition.
- Bảng tăng từ hàng triệu lên hàng trăm triệu bản ghi.
- Phân bố dữ liệu lệch: một tenant có nhiều hàng hơn các tenant còn lại.
- Thống kê được cập nhật bằng `ANALYZE`, khiến planner chọn kế hoạch mới.
- Thay đổi `work_mem`, `random_page_cost`, parallelism, JIT hoặc cấu hình connection pool.
- Nâng cấp PostgreSQL, driver JDBC hoặc thay đổi cách dùng prepared statements.
- Autovacuum, backup, checkpoint, cache hoặc tải đồng thời tạo nhiễu ở thời điểm đo.

Nếu một truy vấn tăng từ 40 ms lên 70 ms, cần phân biệt **hồi quy hiệu năng thực sự** với chênh lệch do cache, CPU, dữ liệu hoặc workload. Mặt khác, một thay đổi có thể giữ nguyên latency trung bình nhưng làm **p99 latency** tăng mạnh, khiến một nhóm người dùng thường xuyên gặp timeout.

Bài học **“Đo hồi quy hiệu năng sau thay đổi schema, dữ liệu hoặc cấu hình”**, thuộc chương **Tối ưu truy vấn** của module **Database Engine Relational PostgreSQL**, hướng dẫn cách xây dựng một phép đo có thể tái tạo: xác định baseline, chuẩn hóa môi trường, thu thập kế hoạch thực thi và số liệu, so trước/sau, tìm nguyên nhân và quyết định triển khai dựa trên bằng chứng.

Bài sử dụng dataset SQL có thể tạo lại, `EXPLAIN (ANALYZE, BUFFERS)`, `pg_stat_statements`, `pg_stat_database`, `pgbench` và các mẫu quy trình regression gate. Các ví dụ tạo dữ liệu chỉ dành cho **database lab riêng**, không chạy trên production.

## 1. Hồi quy hiệu năng là gì?

**Performance regression** là sự suy giảm đáng kể một hoặc nhiều đặc tính hiệu năng so với một mốc so sánh có ý nghĩa sau một thay đổi.

Các biểu hiện gồm:

- Thời gian đáp ứng một query/request/transaction tăng.
- Số giao dịch xử lý mỗi giây giảm.
- CPU, I/O, memory hoặc WAL tăng cho cùng khối lượng công việc.
- Số lần chờ khóa, deadlock, timeout hoặc lỗi tăng.
- Số hàng đọc/đường truy cập bị thay đổi theo hướng kém hiệu quả.
- Tail latency của nhóm tham số đặc biệt tăng dù mean không đổi.

**Hồi quy không tự có nghĩa SQL sai.** Truy vấn vẫn có thể trả kết quả đúng nhưng dùng nhiều tài nguyên hơn. Ngược lại, truy vấn nhanh hơn vì vô tình bỏ sót hàng cũng **không phải tối ưu thành công**.

### 1.1. Một ví dụ số liệu

| Chỉ số | Baseline | Candidate | Tín hiệu |
|---|---:|---:|---|
| p50 latency | 12 ms | 13 ms | Thay đổi nhỏ |
| p95 latency | 45 ms | 95 ms | Suy giảm rõ |
| p99 latency | 120 ms | 430 ms | Tail latency rất xấu |
| Throughput | 1500 req/s | 1430 req/s | Giảm khoảng 4,7% |
| CPU database | 45% | 75% | Cần kiểm tra tải/tài nguyên |
| Timeout rate | 0,1% | 1,8% | Cần điều tra |

Đây là **số liệu giả định** để minh họa, không phải kết quả đo PostgreSQL.

## 2. Tách ba loại thay đổi cần đo

### 2.1. Thay đổi schema

Ví dụ:

- Thêm/bỏ B-tree, BRIN, GIN, GiST hoặc partial index.
- Thêm cột `INCLUDE` trong index.
- Đổi kiểu cột hoặc sửa constraint.
- Chuyển bảng thành partitioned table.
- Thay đổi cấu trúc view/materialized view.
- Migration rewrite bảng hoặc tạo index trên bảng rất lớn.

Một index có thể làm SELECT nhanh nhưng làm INSERT/UPDATE chậm vì phải duy trì index và phát sinh WAL.

### 2.2. Thay đổi dữ liệu

Ví dụ:

- Bảng tăng quy mô.
- Một tenant có số hàng vượt trội.
- Tỷ lệ `status='active'` tăng từ 20% lên 95%.
- Dữ liệu được archive, xóa hoặc nạp hàng loạt.
- Tương quan giữa `tenant_id` và `state` thay đổi.
- Số lượng partitions hoặc kích thước từng partition thay đổi.

Cùng SQL, cùng index, PostgreSQL vẫn có thể chọn plan khác do **selectivity/cardinality** đã đổi.

### 2.3. Thay đổi cấu hình hoặc phiên bản

Ví dụ:

- `work_mem`, `shared_buffers`, `effective_cache_size`.
- `random_page_cost` hoặc `seq_page_cost`.
- Số parallel workers, JIT, `plan_cache_mode`.
- Autovacuum settings hoặc connection pool size.
- PostgreSQL major version, pgJDBC, storage hay CPU quota.

Nhóm này có thể ảnh hưởng nhiều query cùng lúc, nên cần đo **workload tổng thể** chứ không chỉ một SELECT.

## 3. Chọn đơn vị đo: query, transaction hay endpoint

Một HTTP request có thể chạy nhiều SQL:

~~~text
GET /orders
    |
    +--> SELECT quyền truy cập
    +--> SELECT đơn hàng
    +--> SELECT tổng hợp
    +--> SELECT thông tin khách
~~~

Các tầng cần phân biệt:

| Cấp độ | Đo gì? |
|---|---|
| SQL query | Planning, execution time, rows, buffers, scan/join |
| Transaction | Tổng các query, lock waits, commit và retry |
| Endpoint | DB + network + serialization + ứng dụng |
| Batch job | Thời gian hoàn tất và tài nguyên cả đợt |
| Database workload | TPS, concurrency, CPU/I/O/WAL/errors |

Nếu `EXPLAIN ANALYZE` của một SELECT không đổi nhưng endpoint chậm, có thể nguyên nhân ở **N+1 queries, pool wait, network hoặc lock**, không phải plan của SELECT đó.

## 4. Baseline là gì?

**Baseline** là bộ số liệu trước thay đổi, được đo và ghi ngữ cảnh đủ để so sánh với candidate.

Một baseline có ích cần:

1. Tên query hoặc endpoint.
2. SQL template và nhóm tham số.
3. Phiên bản schema/index.
4. Dataset snapshot, row counts và phân bố dữ liệu.
5. PostgreSQL version, driver và GUC liên quan.
6. Hardware, storage, connection pool và concurrency.
7. Chính sách warm-up/cache.
8. Thời lượng chạy và số lượt lặp.
9. Latency, throughput, errors và resource metrics.
10. EXPLAIN plan/ảnh chụp thống kê tại thời điểm đo.

Ví dụ khung metadata:

~~~text
benchmark_id: orders-list-2026-11-14
schema_revision: <migration-id>
postgres_version: <server-version>
dataset_revision: <snapshot-id>
query_template: list_recent_orders
parameter_groups: tenant-small, tenant-medium, tenant-large
clients: 16
warmup_seconds: 60
measure_seconds: 300
cache_policy: warm
isolation: read_committed
baseline_commit: <git-revision>
~~~

Các dấu `<...>` trong khung trên là placeholder cần thay bằng giá trị thật, không phải kết quả đã đo.

### 4.1. Không lấy một lần đo làm baseline

~~~text
GET /orders: 32 ms
~~~

không mô tả phân bố, độ nhiễu hay các tham số cụ thể. Nó chưa đủ cho một kết luận hồi quy đáng tin cậy.

## 5. Những metric cần theo dõi

| Metric | Ý nghĩa | Cạm bẫy |
|---|---|---|
| p50 latency | Trung vị | Che giấu tail latency |
| p95/p99 latency | Phân vị cao | Cần đủ số mẫu |
| Average latency | Trung bình | Nhạy với outliers |
| TPS/RPS | Throughput | Phải so cùng workload |
| Error/timeout rate | Chất lượng xử lý dưới tải | Không loại các request lỗi khi tổng kết |
| Planning Time | Chi phí planner | Prepared statements có thể làm khác |
| Execution Time | Chi phí chạy plan | Không bao toàn bộ client latency |
| Shared buffers hit/read | Buffer accesses | Read không chắc là disk vật lý |
| Temp reads/writes | Sort/hash spill | Không phải mọi query dùng temp |
| WAL bytes/records | Chi phí ghi | Quan trọng sau khi thêm index |
| CPU/memory | Tài nguyên | Phải so cùng concurrency |
| Lock waits | Chờ transaction khác | Không phải plan regression |
| Estimated/actual rows | Chất lượng ước lượng | Không tự là metric latency |
| Rows returned/affected | Khối lượng công việc | Cần so đúng semantics |

Không nên chỉ đo thời gian query rồi gọi là kiểm thử hiệu năng đầy đủ.

## 6. Công thức so sánh trước và sau

Với metric **càng thấp càng tốt** như latency:

\[
\Delta_{\%}=\frac{\text{after}-\text{before}}{\text{before}}\times100
\]

Ví dụ p95 từ 120 ms lên 150 ms:

\[
\Delta_{\%}=\frac{150-120}{120}\times100=25\%
\]

Với metric **càng cao càng tốt** như throughput, có thể báo:

\[
\text{throughput change}_{\%}
=\frac{\text{after}-\text{before}}{\text{before}}\times100
\]

Nếu TPS từ 1000 giảm xuống 900 thì chênh lệch là **-10%**.

Nếu baseline bằng 0 (ví dụ lỗi trước thay đổi bằng 0), không thể dùng công thức tỷ lệ thông thường. Khi đó nên báo chênh lệch tuyệt đối hoặc quy ước rõ.

### 6.1. Cần xét cả phần trăm và giá trị tuyệt đối

Từ 0,3 ms lên 0,6 ms là +100% nhưng chỉ thêm 0,3 ms. Từ 200 ms lên 240 ms là +20% nhưng thêm 40 ms và có thể vi phạm SLO.

Một gate có thể cần cả ngưỡng tương đối, tuyệt đối và độ tái hiện; không tồn tại một ngưỡng chuẩn cho mọi sản phẩm.

## 7. Kịch bản so sánh tương đương

Khi muốn đo **riêng tác động schema hoặc cấu hình**, cần cố gắng giữ nguyên:

- SQL và parameter values.
- Dataset snapshot.
- Query result semantics.
- PostgreSQL version nếu không thử upgrade.
- Hardware/storage class.
- Client concurrency và arrival rate.
- Transaction isolation.
- Driver/pool settings.
- Background workload.
- Warm-up và cache policy.

Nếu chính biến cần thử là **dữ liệu tăng trưởng**, không thể giữ dataset giống nhau. Khi đó phải mô tả rõ:

~~~text
Baseline: 10 triệu rows, 20% completed
Candidate: 30 triệu rows, 90% completed
Schema/config: giữ nguyên
~~~

Trong trường hợp này cần tách **scale effect** khỏi **plan regression**, có thể bổ sung benchmark cùng dữ liệu để làm đối chứng.

## 8. Warm cache và cold cache

Hai lần chạy cùng query có thể có thời gian rất khác do cache:

~~~text
Lần 1: 220 ms  (trang chưa ở shared buffers)
Lần 2: 35 ms   (cache ấm hơn)
Lần 3: 32 ms
~~~

Các lớp cache có thể gồm:

- PostgreSQL shared buffers.
- OS page cache.
- Storage controller/cache.
- Cache ứng dụng.

### 8.1. Chính sách đo

- **Warm-cache:** có lượt warm-up không tính vào kết quả.
- **Cold-ish:** dùng môi trường kiểm thử biệt lập có cơ chế chuẩn hóa cache, không tác động production.
- **Steady-state:** mô phỏng tải thực để cache hoạt động tự nhiên.

Không restart production hoặc xóa cache toàn máy chỉ để tạo điều kiện benchmark “lạnh”.

### 8.2. Tránh thứ tự luôn thiên về candidate

Nếu baseline luôn chạy trước và candidate luôn chạy sau, candidate có thể được hưởng cache ấm. Khi có thể, thực hiện nhiều lượt A/B/A/B hoặc dùng hai môi trường tương đương được dựng từ cùng snapshot.

## 9. Một truy vấn tốt chưa chắc tạo workload tốt

Giả sử lưu lượng thật:

~~~text
70% SELECT theo tenant
20% INSERT
8% UPDATE
2% báo cáo tổng hợp
~~~

Nếu chỉ benchmark SELECT mới có index, bạn bỏ qua chi phí index mới lên DML.

Nên định nghĩa:

- Query mix.
- Parameter distribution.
- Request frequency.
- Concurrency.
- Result size.
- Transaction boundary.
- Mức tải thấp, trung bình và giờ cao điểm.

Nên có **microbenchmark** để giải thích một query và **workload benchmark** để thấy tác động toàn hệ thống.

## 10. Tạo dataset lab có thể tái tạo

Trong **database lab trống**, tạo bảng 200.000 events với tenant rất lớn và nhiều tenant nhỏ:

~~~sql
CREATE SCHEMA perf_lab;

CREATE TABLE perf_lab.events (
    event_id BIGINT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    state TEXT NOT NULL
        CHECK (state IN ('ok', 'failed')),
    occurred_at TIMESTAMPTZ NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    payload TEXT NOT NULL
);

INSERT INTO perf_lab.events (
    event_id, tenant_id, state,
    occurred_at, amount, payload
)
SELECT
    g::BIGINT,
    CASE
        WHEN g <= 150000 THEN 1
        ELSE 2 + g % 50
    END,
    CASE
        WHEN g % 997 = 0 THEN 'failed'
        ELSE 'ok'
    END,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + g * INTERVAL '1 second',
    (g % 10000 + 1)::NUMERIC(12,2),
    repeat('x', 64)
FROM generate_series(1, 200000) AS g;

CREATE INDEX idx_events_tenant_time
ON perf_lab.events (
    tenant_id,
    occurred_at DESC,
    event_id DESC
);

ANALYZE perf_lab.events;
~~~

Dữ liệu không dùng `random()`, nên cùng câu SQL seed cho cùng số hàng/giá trị xác định nếu chạy từ trạng thái database mới.

- Tenant 1 có 150.000 hàng.
- Các tenant khác chia 50.000 hàng còn lại.
- `failed` xuất hiện khoảng 0,1% vì `g % 997 = 0`.
- Cột `amount` không nằm trong index ban đầu.
- Index ban đầu hỗ trợ tenant/thứ tự thời gian nhưng chưa có `state`.

### 10.1. Kiểm tra phân bố

~~~sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (
        WHERE tenant_id = 1
    ) AS tenant_1_rows,
    COUNT(*) FILTER (
        WHERE state = 'failed'
    ) AS failed_rows
FROM perf_lab.events;

SELECT
    tenant_id, state, COUNT(*) AS row_count
FROM perf_lab.events
GROUP BY tenant_id, state
ORDER BY tenant_id, state;
~~~

Không cần cố đạt một số thời gian EXPLAIN được dự báo trước; mục tiêu là so sánh trên môi trường cụ thể.

## 11. Query mục tiêu để lấy baseline

~~~sql
SELECT
    event_id,
    occurred_at,
    amount
FROM perf_lab.events
WHERE tenant_id = 1
  AND state = 'failed'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 50;
~~~

Đối với tenant 1, `state='failed'` hiếm. Index ban đầu có:

~~~text
(tenant_id, occurred_at DESC, event_id DESC)
~~~

nên có thể hỗ trợ thứ tự nhưng không dùng state như một thành phần khóa index để thu hẹp trực tiếp.

Planner có thể chọn index scan, seq scan, bitmap scan hoặc kế hoạch khác tùy số liệu và cost model. **Không khẳng định kế hoạch nào nhất định xuất hiện**.

### 11.1. Query theo tenant nhỏ

~~~sql
SELECT event_id, occurred_at, amount
FROM perf_lab.events
WHERE tenant_id = 2
  AND state = 'failed'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 50;
~~~

So sánh nhiều nhóm tham số vì query trên tenant lớn và nhỏ có thể có chi phí rất khác. Trong production nên sử dụng tần suất thực tế thay vì chỉ hai tenant tự chọn.

## 12. EXPLAIN và ý nghĩa planner cost

~~~sql
EXPLAIN
SELECT event_id, occurred_at, amount
FROM perf_lab.events
WHERE tenant_id = 1
  AND state = 'failed'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 50;
~~~

`EXPLAIN` không `ANALYZE` báo kế hoạch và ước lượng:

- Node types.
- Estimated rows.
- Estimated startup/total cost.
- Điều kiện index/filter.
- Sort, join, aggregate hoặc parallel nodes.

**Cost không phải milliseconds.** Không diễn giải `cost=100` là query sẽ mất 100 ms.

Một cost thấp hơn có thể là tín hiệu planner ưu tiên nhưng chưa chứng minh execution thật nhanh hơn.

## 13. EXPLAIN ANALYZE BUFFERS

~~~sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS,
    VERBOSE,
    SUMMARY,
    FORMAT TEXT
)
SELECT
    event_id,
    occurred_at,
    amount
FROM perf_lab.events
WHERE tenant_id = 1
  AND state = 'failed'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 50;
~~~

Những trường cần đọc:

| Trường | Cách hiểu |
|---|---|
| `Planning Time` | Thời gian lập plan cho lần thực thi |
| `Execution Time` | Thời gian chạy plan trên server |
| `actual rows` | Số hàng thực tế node tạo ra |
| `loops` | Số lần thực hiện node |
| `Rows Removed by Filter` | Hàng đọc nhưng bị loại |
| `Buffers: shared hit/read` | Buffer đã ở shared cache / cần đọc vào shared cache |
| `temp read/written` | Các I/O tạm của sort/hash |
| `Sort Method` | Phương pháp sort, RAM hoặc external |
| `Heap Fetches` | Lượt truy cập heap của Index Only Scan khi cần |
| `Workers Planned/Launched` | Parallelism khi có |
| `Settings` | Một số cấu hình khác mặc định ảnh hưởng plan |

### 13.1. Actual rows có thể là trung bình mỗi loop

Nếu node có `actual rows=100 loops=10`, không thể đọc 100 là tổng toàn bộ công việc; xem loops và node con để đánh giá.

### 13.2. ANAlYZE thực thi statement

`EXPLAIN (ANALYZE)` thực sự chạy query. Đối với SELECT là đọc, còn với UPDATE/DELETE/INSERT/MERGE có thể ghi dữ liệu. Không dùng EXPLAIN ANALYZE DML trên production khi không có kiểm soát.

### 13.3. TIMING OFF

Khi query rất ngắn, instrumentation từng node có overhead. Có thể thử:

~~~sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    TIMING OFF,
    SUMMARY ON
)
SELECT COUNT(*)
FROM perf_lab.events
WHERE tenant_id = 1;
~~~

Cách này hạn chế đo timing từng node nhưng vẫn cho nhiều counters và execution time tổng, tùy PostgreSQL version.

## 14. Đọc BUFFERS mà không hiểu sai

Ví dụ output giả định:

~~~text
Buffers: shared hit=1500 read=100
~~~

- `shared hit`: tìm thấy page trong PostgreSQL shared buffer cache.
- `shared read`: PostgreSQL đọc page vào shared buffers từ tầng dưới.

`shared read` **không đồng nghĩa chắc chắn một physical disk read**, vì OS page cache có thể phục vụ nó.

`temp read/written` thường liên quan tệp tạm của sort/hash spill. `shared dirtied/written` có ý nghĩa riêng khi query/bảo trì làm thay đổi pages.

### 14.1. Hit cao chưa chắc nhanh

Một query đọc rất nhiều pages từ shared buffers vẫn có thể tốn CPU. Query ít rows với một vài reads có thể hoàn thành nhanh hơn.

Dùng buffers để giải thích **khối lượng công việc**, cùng actual rows và execution time.

## 15. Lưu kế hoạch dạng JSON

~~~sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS,
    FORMAT JSON
)
SELECT event_id, occurred_at, amount
FROM perf_lab.events
WHERE tenant_id = 1
  AND state = 'failed'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 50;
~~~

Định dạng JSON thuận tiện cho pipeline:

- So node type, join order và index name.
- So planned vs actual rows.
- So buffers, loops, time và spill.
- Lưu bản trước/sau để điều tra về sau.

**Không diff từng byte JSON** rồi coi mọi chênh lệch timing là regression; thời gian, counters và thông tin runtime tự nhiên biến động.

Nên so **plan shape** tách biệt với **metric distribution**.

## 16. Kịch bản schema: thêm index mới

Sau khi ghi baseline, thêm index trong database lab:

~~~sql
CREATE INDEX idx_events_tenant_state_time
ON perf_lab.events (
    tenant_id,
    state,
    occurred_at DESC,
    event_id DESC
)
INCLUDE (amount);

ANALYZE perf_lab.events;
~~~

Index mới:

- Có thể thu hẹp theo `tenant_id` và `state`.
- Có thể hỗ trợ thứ tự thời gian.
- Chứa `amount` để tăng khả năng index-only scan.

Chạy lại **cùng query**:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT event_id, occurred_at, amount
FROM perf_lab.events
WHERE tenant_id = 1
  AND state = 'failed'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 50;
~~~

### 16.1. Không hứa chắc Index Only Scan

Dù index có đủ cột, planner có thể chọn index scan/seq scan khác. Index-only scan còn phụ thuộc **visibility map**; nếu pages chưa all-visible, plan có thể có `Heap Fetches`.

Nếu VACUUM chỉ chạy ở một vế đo, kết quả có thể bị ảnh hưởng bởi VM, không chỉ index.

### 16.2. Đo DML sau khi thêm index

Index mới cần được cập nhật khi INSERT/UPDATE liên quan, có thể:

- Tăng WAL.
- Tăng index storage.
- Tăng CPU/I/O ghi.
- Giảm khả năng HOT update khi cột được index tham chiếu bị sửa.
- Ảnh hưởng vacuum và cache.

Vì vậy không kết luận migration thành công chỉ vì một SELECT nhanh hơn.

## 17. Kiểm tra kích thước index

~~~sql
SELECT
    pg_size_pretty(
        pg_relation_size('perf_lab.events'::regclass)
    ) AS heap_size,
    pg_size_pretty(
        pg_indexes_size('perf_lab.events'::regclass)
    ) AS indexes_size,
    pg_size_pretty(
        pg_total_relation_size('perf_lab.events'::regclass)
    ) AS total_size;
~~~

Đối chiếu trước/sau:

- Heap size.
- Tổng index size.
- Tổng relation size.
- WAL/IO của workload ghi.
- Tốc độ SELECT và DML.

Một index lớn hơn có thể hợp lý nếu workload truy vấn được hưởng lợi nhiều hơn chi phí ghi/lưu trữ. Cần quyết định theo tỷ trọng đọc/ghi thật.

## 18. Schema migration và thời gian rollout

Hiệu năng cần đo cả **trong lúc migration** và **sau migration**.

Thêm index với `CREATE INDEX` thông thường trên bảng lớn có thể chặn/ảnh hưởng ghi trong lúc tạo. `CREATE INDEX CONCURRENTLY` giảm một số loại blocking nhưng:

- Có chi phí và thời gian riêng.
- Không chạy trong explicit transaction block.
- Có điều kiện chờ các transaction/snapshot.
- Khi thất bại có thể để lại index không hợp lệ.
- Vẫn tiêu tốn CPU/I/O.

### 18.1. Kiểm tra index hợp lệ

~~~sql
SELECT
    c.relname AS index_name,
    x.indisvalid,
    x.indisready
FROM pg_index AS x
JOIN pg_class AS c
    ON c.oid = x.indexrelid
WHERE x.indrelid = 'perf_lab.events'::regclass
ORDER BY c.relname;
~~~

Nếu index không `indisvalid`, planner có thể không dùng nó như dự kiến. Đừng gán lỗi “planner regression” khi migration/index build chưa hoàn tất hợp lệ.

## 19. Đổi kiểu cột, constraint hoặc partitioning

Ngoài index, những thay đổi khác cũng tác động hiệu năng:

**Kiểu dữ liệu:** có thể thay operator, cast, kích thước hàng, index compatibility và chi phí chuyển đổi.

**Constraints:** `CHECK`, `UNIQUE`, `FOREIGN KEY` có thể làm DML phải kiểm tra thêm; một số thông tin ràng buộc cũng có thể hỗ trợ planner.

**Partitioning:** query đúng partition key có thể được pruning tốt; query thiếu điều kiện có thể chạm nhiều partition và tốn planning.

**Views/materialized views:** thay cách JOIN, refresh hoặc predicate pushdown có thể đổi query plan.

Khi đo, cần phân biệt thời gian migration và hiệu năng steady-state, cũng như kiểm tra kết quả SQL không đổi ngoài những thay đổi nghiệp vụ được chủ động thiết kế.

## 20. Data growth và data skew

Một truy vấn từ 10 ms lên 100 ms khi bảng tăng từ 100.000 lên 100 triệu hàng có thể là **scale effect**, không hẳn do code/planner regress.

Những câu hỏi quan trọng:

- Số rows tăng bao nhiêu?
- Có thêm giá trị rất phổ biến không?
- Có tenant mới cực lớn không?
- Query trả nhiều hàng hơn không?
- Index có còn đủ chọn lọc?
- Statistics đã phản ánh phân bố mới?
- Có partition mới hoặc partition quá lớn?
- CPU/I/O trên mỗi đơn vị công việc thay đổi ra sao?

### 20.1. Hai phép đo bổ trợ

**A — Same-data test:** cùng snapshot, đổi schema/config, để cô lập nguyên nhân.

**B — Scale test:** cùng schema/config, nhân dataset với các cỡ 1M/5M/20M/100M, đo độ tăng chi phí và throughput.

Không trộn hai bài toán rồi đưa ra một kết luận nguyên nhân duy nhất.

## 21. Phân tích pg_stats và ANALYZE

~~~sql
SELECT
    schemaname,
    tablename,
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs
FROM pg_stats
WHERE schemaname = 'perf_lab'
  AND tablename = 'events'
  AND attname IN ('tenant_id', 'state');
~~~

`most_common_vals` và `most_common_freqs` phản ánh các giá trị/tần suất phổ biến mà planner ước lượng.

Nếu sau ETL tỷ lệ `failed` tăng từ 0,1% lên 60% nhưng stats chưa cập nhật, kế hoạch cũ có thể không phù hợp.

~~~sql
ANALYZE perf_lab.events;
~~~

`ANALYZE` cập nhật thống kê, không thay nội dung row. Nó **có thể làm plan thay đổi**. Khi benchmark trước/sau, ghi rõ lúc nào ANALYZE chạy, không lén đổi statistics chỉ ở candidate rồi gán mọi khác biệt cho index.

### 21.1. Extended statistics cho cột tương quan

~~~sql
CREATE STATISTICS st_events_tenant_state
    (mcv, dependencies)
ON tenant_id, state
FROM perf_lab.events;

ANALYZE perf_lab.events;
~~~

Có thể giúp một số ước lượng nhiều cột khi `tenant_id` và `state` tương quan. Không bảo đảm mọi query hoặc JOIN đều được tối ưu.

Đây là một **thay đổi riêng cần đo riêng**, không nên ghép cùng lúc với index mới nếu muốn xác định tác động từng yếu tố.

## 22. Estimated rows khác actual rows

Ví dụ minh họa:

~~~text
Nested Loop  (cost=... rows=10 ...)
             (actual ... rows=50000 ...)
~~~

Planner ước lượng 10 hàng nhưng thực tế 50.000. Sai lệch cardinality có thể khiến:

- Nested Loop lặp nhiều hơn dự kiến.
- Sort/hash spill.
- Chọn Index Scan thay vì Seq Scan phù hợp.
- Join order tạo nhiều rows trung gian.

Tuy nhiên estimated/actual rows lệch **chưa đủ** để chứng minh hồi quy. Cần xem thời gian, buffers, node loops và khả năng có kế hoạch thay thế tốt hơn.

### 22.1. Quy trình kiểm tra ước lượng sai

1. Thống kê gần đây chưa?
2. Phân bố dữ liệu có đổi?
3. Có tương quan nhiều cột không?
4. Một tham số có rất khác nhóm khác không?
5. Query có cast/hàm khiến index/selectivity khó đánh giá?
6. Prepared statement có đang generic plan không?
7. Join cardinality bị khuếch đại ở node nào?

## 23. Đo thay đổi cấu hình

Một số GUC thường được xem xét:

| Cấu hình | Ý nghĩa với benchmark |
|---|---|
| `work_mem` | Memory cho sort/hash; spill và áp lực RAM |
| `shared_buffers` | Shared buffer cache, thường cần restart |
| `effective_cache_size` | Ước lượng cache hữu dụng cho planner, không cấp phát RAM |
| `random_page_cost` | Cost đọc ngẫu nhiên |
| `seq_page_cost` | Cost đọc tuần tự |
| `max_parallel_workers_per_gather` | Parallelism cho plan |
| `jit` | JIT compilation khi áp dụng |
| `plan_cache_mode` | Generic/custom prepared plans |
| Autovacuum settings | Ảnh hưởng bảo trì MVCC/stats |

Xem giá trị và nguồn cấu hình:

~~~sql
SELECT
    name,
    setting,
    unit,
    source,
    context,
    pending_restart
FROM pg_settings
WHERE name IN (
    'work_mem',
    'shared_buffers',
    'effective_cache_size',
    'random_page_cost',
    'seq_page_cost',
    'max_parallel_workers_per_gather',
    'jit',
    'plan_cache_mode'
)
ORDER BY name;
~~~

`pending_restart` giúp phát hiện thay đổi đang chờ restart, tránh benchmark với giả định “đã đổi” khi thực tế setting chưa có hiệu lực.

## 24. Dùng SET LOCAL để thử nghiệm

Trong database lab:

~~~sql
BEGIN;

SET LOCAL work_mem = '32MB';

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT tenant_id, state, COUNT(*)
FROM perf_lab.events
GROUP BY tenant_id, state
ORDER BY COUNT(*) DESC;

ROLLBACK;
~~~

`SET LOCAL` chỉ có hiệu lực trong transaction hiện tại. Nó giúp giới hạn phạm vi nhiều GUC hỗ trợ chỉnh ở session/transaction, tránh làm ảnh hưởng connection pool sau thí nghiệm.

### 24.1. Không phải GUC nào cũng SET LOCAL được

Một số GUC chỉ có thể điều chỉnh ở cấp file/server/restart hoặc cần quyền đặc biệt. Không giả định `shared_buffers` đã đổi nếu chỉ thử `SET LOCAL` và server từ chối.

### 24.2. Tăng work_mem không luôn cải thiện workload

Một query có thể có nhiều sort/hash operators; nhiều query chạy đồng thời và parallel workers sẽ dùng tài nguyên cùng lúc. Tăng work_mem quá lớn có thể làm một query đơn nhanh hơn nhưng gây memory pressure/OOM khi concurrency cao.

Cần đo **single-query** và **multi-client workload**.

## 25. Thử cost parameter có phạm vi

~~~sql
BEGIN;

SET LOCAL random_page_cost = 1.5;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT event_id, occurred_at, amount
FROM perf_lab.events
WHERE tenant_id = 1
  AND state = 'failed'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 50;

ROLLBACK;
~~~

Nếu plan đổi sang index scan, điều đó cho thấy cost model nhạy với parameter. Nhưng cần so **actual time/buffers** và workload trước khi quyết định triển khai.

Không tắt `enable_seqscan` hay ép nested loop toàn hệ thống chỉ để làm một plan có vẻ đẹp.

## 26. Prepared statements: generic plan và custom plan

Một query dùng tham số:

~~~sql
PREPARE event_lookup(integer, text) AS
SELECT event_id, occurred_at, amount
FROM perf_lab.events
WHERE tenant_id = $1
  AND state = $2
ORDER BY occurred_at DESC, event_id DESC
LIMIT 50;
~~~

Ở `plan_cache_mode=auto`, PostgreSQL có thể chọn **custom plan** có xét giá trị tham số hoặc **generic plan** có thể tái sử dụng cho nhiều giá trị. Khi tenant lớn/nhỏ khác nhau, một generic plan có thể không phù hợp mọi trường hợp.

So cùng prepared statement:

~~~sql
SET plan_cache_mode = force_custom_plan;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE event_lookup(1, 'failed');

SET plan_cache_mode = force_generic_plan;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE event_lookup(1, 'failed');

RESET plan_cache_mode;

DEALLOCATE event_lookup;
~~~

### 26.1. EXPLAIN literal chưa chắc đại diện JDBC

~~~sql
WHERE tenant_id = 1 AND state = 'failed'
~~~

cho planner biết giá trị ngay lúc planning. Một generic plan với `$1`/`$2` không có cùng thông tin lúc lập kế hoạch.

Nếu regression chỉ xảy ra sau nhiều lần API chạy, cần xác minh `EXPLAIN EXECUTE` tương đương và connection/pool/driver behavior. Không kết luận “generic chắc chắn xuất hiện sau lần thứ sáu”; PostgreSQL dùng heuristic dựa trên chi phí ước lượng.

## 27. pg_stat_statements để theo dõi SQL tích lũy

Nếu extension được cài và cấu hình phù hợp, `pg_stat_statements` cho phép thống kê SQL chuẩn hóa.

Việc kích hoạt extension có thể cần `shared_preload_libraries` và restart theo môi trường; không tự thay production khi chỉ muốn làm ví dụ.

~~~sql
-- Chỉ khi môi trường đã hỗ trợ:
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
~~~

Truy vấn:

~~~sql
SELECT
    queryid,
    calls,
    rows,
    ROUND(total_exec_time::NUMERIC, 2) AS total_exec_ms,
    ROUND(mean_exec_time::NUMERIC, 3) AS mean_exec_ms,
    ROUND(stddev_exec_time::NUMERIC, 3) AS stddev_exec_ms,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_read,
    temp_blks_written
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

### 27.1. Calls và total time

Một query chạy một lần mất 5 giây và một query chạy 100.000 lần mất 5 ms có đóng góp tổng tài nguyên rất khác.

`calls`, `mean_exec_time` và `total_exec_time` giúp ưu tiên query theo tổng ảnh hưởng hoặc độ chậm mỗi lần.

### 27.2. pg_stat_statements là số tích lũy

Để đo một khoảng `t1 → t2`, lưu hai snapshot rồi tính:

\[
\mathrm{calls}_{interval}=\mathrm{calls}_{t2}-\mathrm{calls}_{t1}
\]

\[
\mathrm{mean}_{interval}=
\frac{\mathrm{totalExec}_{t2}-\mathrm{totalExec}_{t1}}
{\mathrm{calls}_{t2}-\mathrm{calls}_{t1}}
\]

khi delta calls dương và không có reset. Không đơn thuần lấy `mean_exec_time` tích lũy ở t2 trừ t1.

### 27.3. Giới hạn của view

- Không lưu đầy đủ từng execution để tính **p95/p99 chính xác** chỉ từ mean/stddev.
- `queryid` không phải định danh bền vững tuyệt đối giữa mọi major versions/schema changes.
- Số liệu có thể reset hoặc bị evict.
- `pg_stat_statements.track_planning` có thể tắt, khi đó planning metrics không đầy đủ.
- SQL normalized không cho biết mọi nhóm tham số khác nhau có latency ra sao.

Muốn đo p99 và parameter skew, cần thêm telemetry ứng dụng hoặc load tester có histogram.

## 28. Quan sát thống kê cấp database

~~~sql
SELECT
    datname,
    xact_commit,
    xact_rollback,
    blks_read,
    blks_hit,
    temp_files,
    temp_bytes,
    deadlocks,
    blk_read_time,
    blk_write_time
FROM pg_stat_database
WHERE datname = current_database();
~~~

Có thể lấy snapshot đầu/cuối và tính delta, nhưng đây là **thống kê cho toàn database** chứ không riêng query đang benchmark.

### 28.1. track_io_timing

`blk_read_time` và `blk_write_time` chỉ mang ý nghĩa đo I/O timing khi cấu hình tracking tương ứng được bật.

Kiểm tra:

~~~sql
SHOW track_io_timing;
~~~

Đừng kết luận I/O không tốn thời gian nếu server không bật tracking.

### 28.2. pg_stat_io trên PostgreSQL 16+

Trên những phiên bản hỗ trợ:

~~~sql
SELECT
    backend_type,
    object,
    context,
    SUM(reads) AS reads,
    SUM(hits) AS hits,
    SUM(writes) AS writes
FROM pg_stat_io
GROUP BY backend_type, object, context
ORDER BY backend_type, object, context;
~~~

View giúp xem hoạt động I/O theo nhóm backend/object/context, nhưng không thay `EXPLAIN BUFFERS` để điều tra một query cụ thể.

## 29. Chờ khóa có thể bị nhầm với plan regression

Một query có execution plan tốt nhưng chờ lock vẫn chậm từ góc nhìn client.

~~~sql
SELECT
    pid,
    usename,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    left(query, 160) AS query_excerpt
FROM pg_stat_activity
WHERE datname = current_database()
  AND state <> 'idle'
ORDER BY query_start;
~~~

Nếu `wait_event_type='Lock'`, cần điều tra blocker, transaction và DDL/DML liên quan.

**Plan regression**: scan/join, cardinality, I/O hoặc execution cost xấu đi.

**Lock regression**: request chờ transaction khác lâu hơn dù plan không đổi.

Không thêm index chỉ để chữa một tình trạng chờ lock do migration hoặc transaction quá dài.

## 30. Đo WAL/chi phí DML sau thay đổi index

Đối với câu lệnh ghi, `EXPLAIN` có tùy chọn WAL ở các phiên bản hỗ trợ:

~~~sql
-- Chỉ thực hiện trong database lab:
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE perf_lab.events
SET amount = amount + 1
WHERE event_id BETWEEN 1 AND 100;

ROLLBACK;
~~~

**Lệnh thực sự UPDATE** trước khi rollback. Rollback phục hồi thay đổi transactional trong database, nhưng:

- WAL/IO đã phát sinh không tự biến mất.
- Trigger có side effects ngoài DB có thể không được rollback.
- Sequence increments trong ví dụ khác có thể không hoàn nguyên.
- Không dùng mẫu này làm cách benchmark an toàn tuyệt đối trên production.

Đo WAL bytes, execution time, số rows affected và write throughput trên **cùng số lượng hàng DML** để so công bằng.

## 31. Dùng pgbench với custom read workload

`pgbench` hỗ trợ chạy script SQL tùy chỉnh. Nội dung file `queries.sql` trên máy chạy benchmark:

~~~text
\set tenant_id random(1, 51)

SELECT event_id, occurred_at, amount
FROM perf_lab.events
WHERE tenant_id = :tenant_id
ORDER BY occurred_at DESC, event_id DESC
LIMIT 20;
~~~

Chạy vào **database lab**:

~~~bash
pgbench -n -M prepared -c 8 -j 2 -T 120 -P 10 -r \
  -f queries.sql postgres_lab
~~~

Các tham số:

- `-n`: bỏ bước vacuum tự động của pgbench theo cơ chế tương ứng.
- `-M prepared`: chế độ protocol prepared của pgbench.
- `-c 8`: 8 clients.
- `-j 2`: 2 worker threads.
- `-T 120`: đo 120 giây.
- `-P 10`: báo tiến độ mỗi 10 giây.
- `-r`: per-command latency stats.
- `-f`: custom script.
- `postgres_lab`: tên database ví dụ.

### 31.1. Cảnh báo về parameter mix

`random(1,51)` chọn tenant gần đều, nhưng dataset có tenant 1 sở hữu phần lớn hàng. Nếu production có 70% request về tenant 1, workload này không đại diện.

Cần thiết kế phân bố tham số theo traffic thật hoặc có kịch bản tách riêng tenant lớn/nhỏ.

### 31.2. Không dùng benchmark để tạo tải production tùy tiện

Dù chỉ SELECT, nhiều client chạy liên tục có thể gây CPU/I/O, cache eviction và ảnh hưởng SLO. Chạy trong test/staging tương đương hoặc production test được kiểm soát và phê duyệt.

## 32. Đọc pgbench: throughput và latency

pgbench có thể báo:

~~~text
number of transactions actually processed: ...
latency average = ... ms
tps = ... (without initial connection time)
~~~

Cần đối chiếu:

- TPS.
- Average latency.
- Concurrency.
- Errors/failed transactions.
- Run duration.
- Per-command latency.
- CPU/IO/locks server.

Để lấy p95/p99 chính xác, dùng công cụ có latency histogram hoặc log từng transaction rồi xử lý phù hợp. Không tuyên bố pgbench mặc định đã cung cấp đầy đủ phân vị p99 trong mọi chế độ.

### 32.1. Thử nhiều mức concurrency

| Clients | TPS | p95 | Error rate |
|---:|---:|---:|---:|
| 1 | đo | đo | đo |
| 8 | đo | đo | đo |
| 16 | đo | đo | đo |
| 32 | đo | đo | đo |
| 64 | đo | đo | đo |

So baseline và candidate **tại cùng một mức concurrency**. TPS ở 64 clients không so trực tiếp với TPS ở 8 clients để kết luận một cấu hình tốt hơn.

## 33. Lặp phép đo và phân tích độ nhiễu

Ví dụ p95 baseline qua 5 lượt:

~~~text
101, 103, 99, 100, 102 ms
~~~

Candidate:

~~~text
128, 130, 127, 133, 129 ms
~~~

Độ tách biệt rõ. Nhưng nếu candidate:

~~~text
98, 115, 101, 109, 103 ms
~~~

thì nhiễu chồng lấp nhiều với baseline; cần chạy thêm và xem môi trường.

Một thực hành tốt:

- Warm-up riêng.
- Chạy nhiều lượt đủ dài.
- Đảo thứ tự A/B nếu có thể.
- Ghi background load.
- Dùng percentiles và phân bố.
- Cân nhắc bootstrap confidence intervals hoặc phương pháp phù hợp.
- So theo nhóm tham số, không chỉ tổng trung bình.

**Ý nghĩa thống kê** và **mức ảnh hưởng thực tế** là hai việc khác nhau. Một thay đổi +0,1 ms có thể đo được nhưng không đáng đổi hệ thống; +40 ms trên endpoint quan trọng lại rất đáng chú ý.

## 34. Ngưỡng cảnh báo hồi quy

Một bộ quy tắc ví dụ:

| Mức | Quy tắc minh họa | Hành động |
|---|---|---|
| Pass | Biến động trong phạm vi noise lịch sử | Ghi nhận |
| Warning | p95 tăng >10% và >5 ms | Đo lại, xem plan |
| Block | p95 tăng >20% và >20 ms ở query trọng yếu | Điều tra trước triển khai |
| Correctness fail | Kết quả khác hoặc sai dữ liệu | Không triển khai |
| Resource fail | CPU/WAL/IO vượt budget dưới cùng tải | Điều tra capacity |

Đây **không phải tiêu chuẩn PostgreSQL chính thức**. Ngưỡng phụ thuộc SLO, tính quan trọng, hiệu năng hiện tại và độ biến động môi trường.

### 34.1. Đừng bỏ qua lỗi hiếm

Một p99 spike có thể do noise hoặc một sự cố nghiêm trọng. Gate nên khuyến khích tái hiện nhưng không được bỏ qua tỷ lệ timeout/error tăng chỉ vì nó không xuất hiện trong mọi lượt đo.

## 35. CI/CD regression test

Một pipeline có thể tổ chức:

~~~text
Commit / migration
       |
       v
Dựng database test với cùng hardware class
       |
       v
Restore snapshot dữ liệu đại diện
       |
       v
Chạy baseline revision hoặc lấy baseline tương đương
       |
       v
Áp thay đổi candidate
       |
       v
ANALYZE theo chính sách cố định
       |
       v
Warm-up
       |
       v
Microbenchmark + workload benchmark
       |
       v
Lưu EXPLAIN JSON, latency samples, resource metrics
       |
       v
So p50/p95/p99, TPS, buffers, CPU, WAL, errors
       |
       v
PASS / WARN / BLOCK
~~~

### 35.1. Baseline từ hôm qua có thể không tương đương

Nếu hôm qua benchmark trên máy khác, snapshot khác hoặc cache khác, so candidate hôm nay với kết quả đó có thể tạo false positives.

Khi khả thi, chạy baseline revision và candidate revision **trong cùng môi trường test và cùng snapshot**. Với migration không thể đảo ngược, dùng hai môi trường clone tương đương.

## 36. Lưu artifacts cho phép tái hiện

Một bộ minh chứng gợi ý:

~~~text
perf-report/
  metadata.txt
  postgres-version.txt
  settings.txt
  schema-revision.txt
  dataset-summary.txt
  query-templates.sql
  parameter-groups.txt
  explain-before.json
  explain-after.json
  latency-before.csv
  latency-after.csv
  pgbench-before.txt
  pgbench-after.txt
  metrics-before.csv
  metrics-after.csv
  conclusions.md
~~~

Đây là **sơ đồ đề xuất**, không phải những file đã được tạo từ ví dụ.

`metadata.txt` cần ghi thời điểm, commit/migration, PostgreSQL/driver versions, hardware class, concurrency, warm-up, cache policy và query mix.

Không cần lưu toàn bộ dữ liệu nhạy cảm để chứng minh regression. Có thể dùng dữ liệu tổng hợp hoặc snapshot đã ẩn danh có kiểm soát.

## 37. Case study A: index mới cải thiện SELECT nhưng giảm TPS

Giả sử thêm index:

~~~sql
CREATE INDEX idx_orders_customer_created
ON orders(customer_id, created_at DESC);
~~~

Sau thay đổi:

- Endpoint list orders nhanh hơn.
- INSERT TPS giảm.
- Write p95 tăng.
- WAL tăng.
- Index size tăng.
- Autovacuum/index maintenance chịu thêm tải.

Cách phân tích:

1. Xác nhận SELECT thật sự dùng index mới.
2. So actual rows/buffers/time SELECT.
3. So INSERT/UPDATE ở cùng concurrency.
4. Ghi WAL, index size, CPU/IO.
5. Xem tỷ lệ đọc/ghi trong workload.
6. Kiểm tra index có trùng cấu trúc với index hiện có không.
7. Tính tác động tổng thể lên SLO.

Kết luận không thể chỉ là “index giúp SELECT nhanh 80% nên phải giữ”.

## 38. Case study B: nạp dữ liệu làm Seq Scan xuất hiện

Giả sử trước ETL:

~~~text
2 triệu rows
state='failed': 0,1%
Query dùng Index Scan
~~~

Sau ETL:

~~~text
20 triệu rows
state='failed': 60%
Query dùng Seq Scan
~~~

Đây chưa chắc là sai lầm của planner. Nếu `WHERE` trả hơn nửa bảng, Seq Scan có thể hợp lý.

Kiểm tra:

- Query trả bao nhiêu hàng sau ETL?
- Stats đã cập nhật?
- Seq Scan so với Index Scan cái nào nhanh thật?
- Query có `LIMIT`/`ORDER BY` phù hợp không?
- Có nên dùng index khác hoặc tách workload theo status không?
- SLO đã tính đến data growth chưa?

Không ép `enable_seqscan=off` chỉ để giữ kế hoạch cũ.

## 39. Case study C: tăng work_mem nhưng workload chậm

Tăng `work_mem` có thể giúp một sort đơn tránh spill. Nhưng dưới nhiều kết nối đồng thời, tổng memory pressure tăng.

Triệu chứng có thể:

- Latency p95/p99 tăng.
- OS swapping hoặc OOM.
- Throughput giảm.
- Temp bytes giảm nhưng CPU wait/memory pressure tăng.

Bài học: giảm temp I/O không phải chiến thắng nếu tổng hệ thống mất ổn định. Phải đo single-query và concurrency, không chỉ một plan.

## 40. Case study D: JDBC prepared query chậm sau nhiều lần

Một ứng dụng dùng:

~~~sql
WHERE tenant_id = $1
~~~

Sau nhiều lần execute, PostgreSQL có thể cân nhắc generic plan. Dữ liệu tenant skew có thể khiến một plan chung kém cho tenant nhỏ.

Chẩn đoán:

~~~sql
PREPARE tenant_lookup(integer) AS
SELECT event_id, occurred_at, amount
FROM perf_lab.events
WHERE tenant_id = $1
ORDER BY occurred_at DESC, event_id DESC
LIMIT 50;

SET plan_cache_mode = force_custom_plan;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE tenant_lookup(2);

SET plan_cache_mode = force_generic_plan;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE tenant_lookup(2);

RESET plan_cache_mode;
DEALLOCATE tenant_lookup;
~~~

Phân biệt `prepareThreshold` của pgJDBC với cơ chế generic/custom của server. Không mặc định PostgreSQL luôn chọn generic từ lần thứ sáu; quyết định dựa trên ước lượng chi phí.

Nếu custom tốt hơn:

- Kiểm tra stats.
- Xem index phù hợp.
- Xem query mix/parameter skew.
- Cân nhắc mode cục bộ hoặc tách query templates.
- Đo planning CPU và total latency trước khi quyết định.

## 41. Case study E: nâng cấp PostgreSQL

Major upgrade có thể thay:

- Planner cost model/plan strategy.
- Cardinality estimation.
- Partition pruning, parallelism, JIT.
- Index/access method.
- Thống kê và cách ghi metrics.
- Driver/pool compatibility.

Một quy trình:

1. Clone snapshot đại diện.
2. Chạy baseline trên version cũ.
3. Dựng version mới cùng hardware class.
4. Khôi phục/migrate dữ liệu đúng cách.
5. Đảm bảo stats phù hợp.
6. Replay query mix và parameter groups.
7. So correctness, plan shape, latency và resources.
8. Điều tra regression theo từng query.
9. Đặt rollback/cutover plan.
10. Theo dõi production sau nâng cấp.

`queryid` và format plan không nhất thiết ổn định qua major versions; dùng mapping SQL/endpoint và metric thật.

## 42. Một truy vấn nhanh hơn nhưng kết quả có thể sai

Ví dụ:

~~~sql
SELECT event_id, amount
FROM perf_lab.events
LIMIT 50;
~~~

Không có `ORDER BY` nên PostgreSQL **không bảo đảm cùng 50 hàng** giữa các plan hoặc sau khi tạo index.

Nếu logic nghiệp vụ yêu cầu trang đầu xác định, dùng:

~~~sql
SELECT event_id, amount
FROM perf_lab.events
ORDER BY event_id
LIMIT 50;
~~~

Khi so correctness, không chỉ xem cùng số rows; còn cần kiểm tra key set, ordering và giá trị quan trọng. Một query trả thiếu dữ liệu nhưng chạy nhanh hơn không phải tối ưu.

## 43. Quan sát autovacuum và visibility map

Một index-only scan có thể cần nhiều `Heap Fetches` sau UPDATE dù SQL/index không đổi vì nhiều pages mất cờ all-visible.

Đồng thời:

- Dead tuples có thể tích tụ.
- VACUUM chưa thu dọn vì transaction dài.
- Stats cũ.
- Heap/index bloat tăng.

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze,
    n_tup_ins,
    n_tup_upd,
    n_tup_del
FROM pg_stat_user_tables
WHERE schemaname = 'perf_lab'
  AND relname = 'events';
~~~

`n_dead_tup` thường là **ước lượng**, không phải COUNT(*) chính xác.

Nếu chỉ candidate được chạy `VACUUM (ANALYZE)`, index-only scan có thể cải thiện một phần do VM. Hãy ghi lại maintenance giữa các lượt đo.

## 44. Checklist điều tra theo loại thay đổi

### 44.1. Schema

- Có index/constraint/partition mới nào?
- Query plan trước/sau khác ở node nào?
- Index mới có valid và usable không?
- Có tăng WAL/lock/chi phí DML không?
- Migration có block writes không?
- Index có trùng lặp với index cũ không?

### 44.2. Dữ liệu

- Rows/bytes tăng bao nhiêu?
- Distribution/MCV/tenant skew đổi không?
- ANALYZE đã cập nhật stats chưa?
- Có thêm dead tuples/bloat không?
- Query trả nhiều rows hơn không?
- Plan chậm do đọc nhiều dữ liệu hơn hay do chiến lược kém?

### 44.3. Cấu hình

- GUC nào thực sự đổi và có hiệu lực chưa?
- Có restart làm lạnh cache không?
- Parallelism/JIT/work_mem thay đổi thế nào?
- Có áp lực RAM/CPU/IO dưới concurrency không?
- Có ảnh hưởng nhiều query ngoài query mục tiêu không?
- Có rollback settings an toàn không?

## 45. Những hiểu lầm thường gặp

### Hiểu lầm 1 — EXPLAIN cost là milliseconds

Sai. Cost là đơn vị tương đối của planner, cần đo actual time.

### Hiểu lầm 2 — EXPLAIN ANALYZE chỉ dự đoán

Sai. Nó **thực thi** statement.

### Hiểu lầm 3 — shared read là physical disk read

Không chắc. OS cache có thể phục vụ.

### Hiểu lầm 4 — Một lần đo chậm hơn chứng minh regression

Không. Cache, load, locks và thống kê có thể gây nhiễu.

### Hiểu lầm 5 — Mean ổn thì người dùng không bị ảnh hưởng

Sai. p95/p99 và timeout có thể xấu.

### Hiểu lầm 6 — Thêm index chỉ giúp, không có chi phí

Sai. Index làm tăng storage, DML/WAL và maintenance.

### Hiểu lầm 7 — ANALYZE không ảnh hưởng plan

Sai. Statistics có thể làm planner chọn chiến lược khác.

### Hiểu lầm 8 — Query trả nhiều hàng hơn nhưng chậm hơn là regression của optimizer

Chưa chắc. Có thể đơn giản vì workload lớn hơn.

### Hiểu lầm 9 — pg_stat_statements chứa p99

Không thể tính chính xác p99 từ mean/stddev tổng hợp; cần histogram/samples.

### Hiểu lầm 10 — QueryID ổn định giữa mọi migration/upgrade

Không nên giả định như vậy.

### Hiểu lầm 11 — Benchmark 1 client dự đoán được throughput 100 clients

Không. Concurrency tạo contention và memory pressure.

### Hiểu lầm 12 — SET work_mem lớn luôn nhanh

Sai. Mỗi query/node có thể dùng nhiều memory, tổng concurrency có thể nghẽn.

### Hiểu lầm 13 — Chạy VACUUM chỉ ở candidate không ảnh hưởng so sánh

Sai. VM và cleanup có thể tác động index-only scans.

### Hiểu lầm 14 — Plan giống nhau nghĩa latency chắc giống nhau

Không. Cache, IO, locks, runtime parameter distribution vẫn khác.

### Hiểu lầm 15 — Plan khác nhau luôn là hồi quy

Không. Planner có thể đổi sang phương án phù hợp hơn vì dữ liệu thay đổi.

### Hiểu lầm 16 — Restart ứng dụng là giải pháp generic plan regression

Có thể chỉ reset prepared cache tạm thời; root cause còn.

### Hiểu lầm 17 — Throughput cao hơn luôn tốt hơn

Nếu latency/error rate và resource cost xấu hơn dưới điều kiện khác, chưa chắc.

### Hiểu lầm 18 — Query nhanh hơn nhưng trả khác kết quả vẫn chấp nhận được

Không, trừ khi thay đổi semantics là chủ ý và được kiểm chứng.

### Hiểu lầm 19 — DML EXPLAIN ANALYZE trong transaction luôn vô hại

Rollback không hủy WAL hay side effects ngoài DB.

### Hiểu lầm 20 — Một GUC tốt cho một query nên áp toàn cluster

Có thể hại các workload khác; thử có phạm vi.

## 46. Quy trình đo hồi quy từ đầu đến cuối

**Bước 1 — Định nghĩa thay đổi.** Ghi migration/config/data snapshot, mục tiêu và phạm vi.

**Bước 2 — Xác định query/workload.** Có template, parameter mix, concurrency và result expectations.

**Bước 3 — Dựng baseline.** Cùng môi trường/dataset, ghi version và GUC.

**Bước 4 — Warm-up.** Thực hiện warm-up riêng, ghi cache policy.

**Bước 5 — Đo baseline nhiều lượt.** Ghi latency samples/histogram, TPS, errors, buffers và plan JSON.

**Bước 6 — Áp candidate.** Thay đổi đúng một nhóm yếu tố khi có thể; ghi lại mọi bước migration/VACUUM/ANALYZE.

**Bước 7 — Kiểm tra correctness.** So key set, row count, result ordering, business constraints.

**Bước 8 — Đo candidate giống baseline.** Cùng parameters, duration, arrival rate, concurrency và warm-up.

**Bước 9 — Phân tích plan drift.** So scan/join/sort nodes, estimates, actual rows, loops và buffers.

**Bước 10 — Phân tích tài nguyên.** CPU, IO, WAL, memory, temp spill, locks và errors.

**Bước 11 — Xác nhận tái hiện.** Lặp hoặc so A/B/A khi có thể.

**Bước 12 — So ngưỡng.** Xét mức tuyệt đối/tương đối, noise và SLO.

**Bước 13 — Quyết định.** PASS, WARN, BLOCK hoặc rollback/điều chỉnh.

**Bước 14 — Lưu artifacts.** Baseline, candidate, SQL, plan, stats và kết luận.

**Bước 15 — Theo dõi sau triển khai.** Workload production có thể khác staging; giám sát regression thật và có đường rollback.

## 47. Bài tập thực hành

### Bài 1 — Hồi quy tương đối

p95 baseline 100 ms, candidate 130 ms. Tỷ lệ tăng là bao nhiêu?

**Gợi ý:** 30%.

### Bài 2 — Throughput

TPS từ 2000 xuống 1800. Tỷ lệ thay đổi là bao nhiêu?

**Gợi ý:** -10%.

### Bài 3 — Latency metric

Mean ổn nhưng người dùng báo request chậm bất thường. Cần xem thêm gì?

**Gợi ý:** p95/p99, timeout, wait events.

### Bài 4 — EXPLAIN cost

`cost=1000` nghĩa là 1000 ms không?

**Gợi ý:** không.

### Bài 5 — EXPLAIN ANALYZE

Vì sao không dùng tùy tiện với UPDATE/DELETE production?

**Gợi ý:** nó thực thi DML thật.

### Bài 6 — Shared buffers

`shared read` luôn là physical disk read không?

**Gợi ý:** không; OS cache có thể phục vụ.

### Bài 7 — Plan JSON

Tại sao lưu `EXPLAIN FORMAT JSON` hữu ích hơn ảnh chụp màn hình khi so tự động?

**Gợi ý:** cấu trúc máy đọc, so node/rows/buffers.

### Bài 8 — Query sau thêm index

Index `(tenant_id, state, occurred_at DESC, event_id DESC) INCLUDE(amount)` có thể hỗ trợ query nào trong lab?

**Gợi ý:** truy vấn failed events theo tenant và thứ tự thời gian.

### Bài 9 — Index overhead

Nêu ba loại chi phí có thể tăng sau khi thêm index.

**Gợi ý:** WAL, DML latency, storage/maintenance.

### Bài 10 — Data growth

Bảng tăng 10 lần, query chậm 3 lần. Có chắc là planner regression không?

**Gợi ý:** chưa; xem scale effect.

### Bài 11 — pg_stats

Viết SQL lấy `most_common_vals` và `most_common_freqs` của `state`.

**Gợi ý:** `pg_stats` lọc theo schema/table/attname.

### Bài 12 — ANALYZE

Vì sao nên ghi việc chạy ANALYZE giữa hai lượt benchmark?

**Gợi ý:** thống kê có thể làm plan đổi.

### Bài 13 — Parameter skew

Vì sao phải benchmark tenant 1 và tenant nhỏ?

**Gợi ý:** số hàng rất khác, plan/latency có thể khác.

### Bài 14 — pg_stat_statements

`calls` từ 1000 lên 1600 nghĩa là có bao nhiêu lượt trong khoảng nếu không reset?

**Gợi ý:** 600.

### Bài 15 — Mean theo khoảng

`total_exec_time` tăng 3000 ms và `calls` tăng 600. Mean interval là bao nhiêu?

**Gợi ý:** 5 ms.

### Bài 16 — Tail latency

Có thể tính p99 chính xác chỉ từ `mean_exec_time` và `stddev_exec_time` không?

**Gợi ý:** không.

### Bài 17 — QueryID

Dùng queryid làm ID ổn định duy nhất qua major upgrade có an toàn không?

**Gợi ý:** không nên; kết hợp SQL/endpoint mapping.

### Bài 18 — pending_restart

`pg_settings.pending_restart=true` báo hiệu gì?

**Gợi ý:** setting chờ restart để có hiệu lực.

### Bài 19 — work_mem

Vì sao work_mem lớn có thể giúp một query nhưng hại toàn bộ 100 concurrent sessions?

**Gợi ý:** memory usage nhân theo operations/sessions/workers.

### Bài 20 — WAL

Khi thêm index, nên kiểm tra chi phí ghi bằng những metric nào?

**Gợi ý:** TPS/latency DML, WAL và index size.

### Bài 21 — pg_stat_database

Dùng `blks_read` cấp database có chỉ đúng một query đọc nhiều hơn không?

**Gợi ý:** không; tổng nhiều workload.

### Bài 22 — pgbench

Có so trực tiếp TPS ở 8 clients baseline và 64 clients candidate được không?

**Gợi ý:** không, concurrency không tương đương.

### Bài 23 — Generic/custom

Prepared query chậm nhưng literal nhanh. Nên thử gì?

**Gợi ý:** `EXPLAIN EXECUTE` với `force_generic_plan`/`force_custom_plan`.

### Bài 24 — Sort spill

Trong EXPLAIN thấy `Sort Method: external merge Disk`. Điều đó gợi ý gì?

**Gợi ý:** sort đã dùng tệp tạm, cần xét rows/work_mem.

### Bài 25 — Parallelism

Tại sao tăng parallel workers có thể giúp query đơn nhưng không tăng TPS dưới tải cao?

**Gợi ý:** tranh CPU/workers và overhead.

### Bài 26 — Lock waits

Plan/buffers giống nhau, endpoint chậm hơn do chờ lock. Đây chủ yếu là plan regression không?

**Gợi ý:** không; điều tra blocker/transaction.

### Bài 27 — Cache

Candidate luôn được chạy sau baseline. Nguy cơ gì?

**Gợi ý:** cache ấm ưu ái candidate.

### Bài 28 — Result correctness

Hai query cùng trả 50 rows nhưng khác key set. Có thể coi performance comparison hợp lệ không?

**Gợi ý:** phải xác nhận semantics và ordering trước.

### Bài 29 — CI gate

Vì sao không nên BLOCK chỉ vì một run chậm hơn 2 ms?

**Gợi ý:** noise, mức tuyệt đối/tương đối và tính tái hiện.

### Bài 30 — Full workload

Index giúp SELECT nhưng INSERT TPS giảm. Những thông tin nào quyết định giữ index?

**Gợi ý:** query mix, SLO, WAL/IO/CPU, p95 DML và lợi ích SELECT.

## 48. Câu hỏi thường gặp

### Có phải một index mới luôn cải thiện hiệu năng?

Không. Có thể cải thiện SELECT cụ thể nhưng tăng overhead ghi, WAL và storage. Planner cũng không bắt buộc chọn index.

### Có nên chạy VACUUM/ANALYZE trước mọi phép đo?

`ANALYZE` thường hợp lý khi cần thống kê đại diện, nhưng phải **thống nhất chiến lược** ở hai vế. `VACUUM` còn ảnh hưởng visibility map và heap/index cleanup. Không chỉ thực hiện maintenance ở candidate rồi quy hết cải thiện cho schema.

### EXPLAIN không ANALYZE có đủ để kết luận latency không?

Không. Nó cho plan ước lượng; cần thực thi benchmark trong điều kiện kiểm soát để đo actual time.

### Có thể lấy p99 từ pg_stat_statements không?

Không chính xác chỉ từ tổng/mean/stddev. Cần samples hoặc histogram ở client/tracing.

### Nếu một query nhanh hơn sau config change, có nên bật GUC toàn cluster?

Chưa đủ. Kiểm tra các query khác, concurrency, CPU/memory/IO và cách rollback.

### Baseline giữa hai môi trường khác hardware có dùng được không?

Có thể tham khảo xu hướng nhưng chưa phải phép so công bằng. Cần kiểm soát hoặc ghi rõ chênh lệch hardware và run baseline/candidate trên cùng loại tài nguyên khi có thể.

### Nếu không sao chép được production data?

Có thể tạo dataset tổng hợp có quy mô/skew tương tự hoặc snapshot đã ẩn danh. Phải nêu rõ những điểm chưa mô phỏng được, tránh khẳng định test phản ánh chính xác production.

### Query sau deploy chậm lần đầu có chắc là regression?

Không. Cache lạnh, JIT, prepared statement warm-up, background load hoặc plan invalidation có thể ảnh hưởng. Đo cả cold-start và steady-state nếu SLO yêu cầu.

## 49. Tổng kết

- **Hồi quy hiệu năng** cần được đo với **baseline và workload có thể so sánh**, không phải cảm nhận từ một lần query chậm.
- Thay đổi **schema, dữ liệu, cấu hình hoặc phiên bản PostgreSQL** có thể làm execution plan và tài nguyên thay đổi ngay cả khi SQL giữ nguyên.
- Cần đo **p50/p95/p99, throughput, errors, planning/execution time, buffers, CPU/IO/WAL, memory và lock waits** khi phù hợp.
- `EXPLAIN` cho plan/ước lượng; `EXPLAIN ANALYZE` thực thi để cho actual rows/time; `BUFFERS` giúp giải thích khối lượng truy cập pages.
- **Planner cost không phải milliseconds** và `shared read` không chắc là physical disk read.
- `pg_stat_statements` cung cấp thống kê SQL **tích lũy**; so interval bằng **delta**, không nhầm số tổng với khoảng đo.
- p99 không thể suy chính xác từ mean/stddev tổng hợp; dùng histogram/samples thực.
- `pg_stats`, `ANALYZE` và extended statistics giúp hiểu **data skew/cardinality** và các thay đổi kế hoạch.
- Index mới có thể giúp SELECT nhưng tăng chi phí DML/WAL/storage; phải đo **workload hỗn hợp**.
- GUC như `work_mem`, `random_page_cost` hay parallelism cần thử trong phạm vi hẹp và dưới concurrency thực tế.
- Cache, autovacuum, checkpoint, transaction dài và replication có thể gây nhiễu; phải ghi lại ngữ cảnh.
- Với JDBC/prepared statements, **generic/custom plans** và nhóm tham số có thể làm latency khác nhau; xem `EXPLAIN EXECUTE` đúng ngữ cảnh.
- `pgbench` hỗ trợ workload lặp, nhưng **parameter mix phải đại diện thực tế** và benchmark không được gây tải không kiểm soát trên production.
- Pipeline có thể lưu **EXPLAIN JSON, latency samples, query mapping và resource metrics** rồi đánh giá PASS/WARN/BLOCK theo ngưỡng đã thiết kế.
- **Đúng kết quả là điều kiện bắt buộc**: query trả thiếu/sai dữ liệu nhưng nhanh hơn không phải tối ưu.
- `EXPLAIN ANALYZE` trên DML thực sự ghi/xóa; rollback không đảo ngược mọi chi phí hoặc tác động ngoài database.

Nguyên tắc cốt lõi là **“đo cùng câu hỏi trong những điều kiện được kiểm soát, rồi giải thích chênh lệch bằng kế hoạch và chỉ số quan sát được.”** Khi đã lưu baseline, phân bố tham số, nguồn nhiễu và bằng chứng thực thi, việc phát hiện hồi quy PostgreSQL sau migration hoặc tuning trở thành một quy trình **có thể lặp lại và ra quyết định bằng dữ liệu**.

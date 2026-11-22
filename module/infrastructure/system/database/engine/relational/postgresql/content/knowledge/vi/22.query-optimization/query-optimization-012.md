# Tránh ép kế hoạch khi chưa xác định nguyên nhân gốc trong PostgreSQL

Một truy vấn PostgreSQL đang chậm. Bạn chạy `EXPLAIN` và thấy `Seq Scan` trên bảng có hàng triệu dòng, hoặc `Nested Loop` được lặp hàng trăm nghìn lần. Cách xử lý hấp tấp thường là **tắt `enable_seqscan`**, **tắt `enable_nestloop`**, **tăng `work_mem` lên rất lớn**, **ép một index** hoặc tìm công cụ để “đóng đinh” một kế hoạch truy vấn.

Đôi khi những cách này làm một lần chạy nhanh hơn. Nhưng nếu nguyên nhân thật sự là **thống kê cũ**, **ước lượng số hàng sai**, **parameter skew**, **index không phù hợp**, **ép kiểu làm mất khả năng dùng index**, **I/O đang nghẽn**, **khóa giao dịch** hoặc **query shape chưa hợp lý**, thì ép plan có thể chỉ che giấu lỗi, làm những tham số khác chậm hơn và gây regression khi dữ liệu thay đổi.

**Nguyên tắc của bài học: tối ưu bằng bằng chứng, không tối ưu bằng việc ghét một tên node trong EXPLAIN.** Kế hoạch tốt là kế hoạch trả kết quả đúng với chi phí thực tế phù hợp workload, chứ không nhất thiết là kế hoạch có Index Scan, Hash Join hay Parallel Scan.

Trong chương **Tối ưu truy vấn**, bài này trình bày một quy trình thực hành: đo truy vấn đúng bối cảnh, đọc **estimated vs actual**, tìm nút đầu tiên mà thống kê hoặc chi phí bắt đầu sai, xác nhận giả thuyết với một thử nghiệm cô lập, sửa **nguyên nhân gốc**, rồi so sánh trên nhiều tham số và mức tải trước khi triển khai.

## 1. Mục tiêu học tập

Sau khi hoàn thành, bạn có thể:

1. Phân biệt **query plan**, **planner estimates** và **runtime evidence**.
2. Đọc `EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS)` mà không nhầm `cost` với thời gian thực.
3. Phát hiện sai lệch giữa `rows` ước lượng và `actual rows`, có xét `loops`.
4. Giải thích vì sao **Seq Scan có thể đúng**, còn Index Scan có thể tệ.
5. Nhận diện một `Nested Loop` chậm do **sai cardinality estimate** thay vì do node Nested Loop luôn xấu.
6. Kiểm tra `ANALYZE`, `pg_stats`, `reltuples`, `n_distinct`, most-common-values và **extended statistics**.
7. Nhận diện khác biệt giữa **generic** và **custom plans** của prepared statements khi tham số có phân bố lệch.
8. Viết lại truy vấn để điều kiện lọc có thể dùng index (*sargable*) thay vì tắt planner nodes.
9. Phân biệt chậm do plan với chậm do **khóa, I/O, temp spills, cache, JIT, parallel worker starvation** hay ứng dụng.
10. Dùng `SET LOCAL enable_seqscan=off`, `enable_nestloop=off` và các cấu hình khác **chỉ như thí nghiệm chẩn đoán có giới hạn**.
11. Đánh giá rủi ro của hints, plan pinning và thay đổi tham số planner toàn hệ thống.
12. Lập runbook cho query regression: baseline → hypothesis → controlled test → root-cause fix → rollback.

## 2. PostgreSQL chọn kế hoạch bằng cách nào?

Một câu SQL khai báo **kết quả muốn lấy**, không khai báo bắt buộc phải dùng phương thức truy cập nào.

~~~sql
SELECT order_id, total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'paid';
~~~

PostgreSQL có thể cân nhắc:

- `Seq Scan`: đọc nhiều heap blocks và lọc;
- `Index Scan`: dùng B-tree để tìm TIDs rồi đọc heap;
- `Index Only Scan`: đọc dữ liệu từ index khi đủ cột và điều kiện visibility;
- `Bitmap Index Scan + Bitmap Heap Scan`: gom vị trí heap và đọc theo block;
- Các đường truy cập song song khi an toàn và có lợi;
- Những biến thể khác tùy cấu trúc bảng, index, partition và phiên bản.

Planner xây dựng các **candidate paths**, ước tính số hàng qua từng bước và chi phí xử lý, rồi chọn **một plan có cost ước tính tốt**. Nó không thực thi toàn bộ các candidate plans để biết thời gian thật.

~~~mermaid
flowchart TD
    A["SQL + parameters"] --> B["Parser / rewrite"]
    B --> C["Planner: candidate paths"]
    S["Table / column / extended stats"] --> C
    G["Cost settings + index definitions"] --> C
    C --> D["Chọn plan theo cost estimate"]
    D --> E["Executor chạy với dữ liệu thực"]
    E --> F["Actual rows / time / buffers / waits"]
    F --> H{"Có chậm hoặc regression?"}
    H -->|Có| I["Điều tra nguyên nhân gốc"]
    I --> S
    I --> G
    I --> A
    H -->|Không| J["Theo dõi, không ép plan"]
~~~

### 2.1. Estimated cost không phải đồng hồ thời gian

Trong output:

~~~text
Seq Scan on orders (cost=0.00..12000.00 rows=50000 width=32)
~~~

`cost=12000` là **đơn vị chi phí nội bộ tương đối**, không phải 12 giây hay 12.000 ms. Tham số như `seq_page_cost`, `random_page_cost`, `cpu_tuple_cost`, `cpu_index_tuple_cost` và `cpu_operator_cost` tham gia mô hình này.

Phần:

~~~text
(actual time=0.012..145.321 rows=48000 loops=1)
~~~

chỉ có khi chạy `EXPLAIN ANALYZE`; đây mới là thống kê thời gian thực tế của lượt thực thi ấy. Không so `cost` và `actual time` bằng phép trừ đơn vị trực tiếp.

### 2.2. Planner sai có hai kiểu khác nhau

**Sai về cardinality:** planner dự đoán 100 hàng, thực tế 100.000 hàng. Nó có thể chọn Nested Loop rất tốn kém vì tưởng inner scan chỉ lặp 100 lần.

**Cardinality đúng, nhưng cost/runtime khác dự kiến:** số hàng gần đúng nhưng truy vấn vẫn chậm vì random I/O, cache lạnh, sort tràn đĩa, runtime có lock wait, CPU đang bận hoặc môi trường phần cứng khác giả định của cost model.

Hai tình huống cần hướng điều tra khác nhau. **Đừng điều chỉnh `random_page_cost` để che một sai lệch 1.000 lần trong estimated rows.**

### 2.3. Một tên node không kết luận được tốt/xấu

| Node | Có thể tốt khi | Có thể chậm khi |
| --- | --- | --- |
| `Seq Scan` | Lọc phần lớn bảng, bảng nhỏ, dữ liệu nằm trong cache | Chỉ cần rất ít hàng của bảng lớn nhưng thiếu index |
| `Index Scan` | Điều kiện chọn lọc, ít heap fetch | Lấy phần lớn bảng bằng random heap I/O |
| `Index Only Scan` | Index chứa đủ dữ liệu và heap pages all-visible | Nhiều `Heap Fetches`, index lớn |
| `Bitmap Heap Scan` | Nhiều hàng phân tán, gom heap access theo page | Bitmap lossy và recheck nhiều, sort thêm |
| `Nested Loop` | Outer nhỏ, inner lookup hiệu quả | Outer bị ước lượng quá thấp, inner lặp hàng triệu lần |
| `Hash Join` | Input phù hợp, hash table có memory | Hash spill/batches, input lớn hơn ước tính |
| `Merge Join` | Hai input có thứ tự thích hợp | Sort lớn hoặc join selectivity sai |
| `Gather/Gather Merge` | Scan/aggregate/sort nặng có thể chia việc | Worker startup, transfer và leader bottleneck |

Mục tiêu không phải **xóa node trông đáng ngờ**, mà hiểu **vì sao planner chọn nó và nó thực sự tiêu tốn gì**.

## 3. Năm nguồn chậm phải tách trước khi nói tới plan

Một query chậm có thể do:

1. **Kế hoạch không phù hợp:** cardinality/cost sai, index không dùng được, join order tệ.
2. **Dữ liệu/SQL:** query trả quá nhiều hàng, điều kiện lọc mơ hồ, N+1 queries, `OFFSET` sâu.
3. **Tài nguyên:** I/O, shared buffer misses, temp spills, CPU, memory pressure, autovacuum cạnh tranh.
4. **Đồng thời:** lock wait, transaction dài, blocked backend, serialization retries.
5. **Đường đi ngoài database:** connection pool, network, client fetch, serialization JSON, ORM hydration.

Ví dụ: ứng dụng báo endpoint mất 8 giây, nhưng `EXPLAIN ANALYZE` của SQL hoàn thành trong 35 ms. **Không nên chỉnh join planner** nếu sáu giây còn lại nằm ở connection pool hoặc gọi API bên ngoài.

### 3.1. Định nghĩa đúng đơn vị thời gian

~~~text
HTTP request latency
  = chờ connection
  + round-trip tới PostgreSQL
  + SQL execute time
  + fetch rows / network
  + ORM mapping / JSON
  + các công việc khác
~~~

Thời gian **trong PostgreSQL** khác thời gian **người dùng cuối** nhìn thấy. Thu thập cả hai khi có thể.

### 3.2. Câu hỏi đầu tiên: query nào thật sự chậm?

- SQL nguyên văn hoặc phiên bản chuẩn hóa;
- Giá trị tham số và kiểu tham số;
- Database, role, `search_path`, `TimeZone` khi ảnh hưởng semantics;
- Số hàng trả về;
- Thời gian và tần suất;
- Sự khác biệt giữa lúc nhanh và lúc chậm;
- Mức tải hệ thống và contention;
- Kế hoạch được ghi nhận lúc nhanh/chậm.

Nếu chỉ biết “màn hình đơn hàng chậm” mà chưa biết SQL nào chậm, việc ép `enable_hashjoin` đã quá sớm.

## 4. Quy trình điều tra có kiểm chứng

### Bước 1 — Tái hiện đúng câu SQL và tham số

Ưu tiên lấy câu SQL cùng **bind parameter types** mà ứng dụng thực sự gửi. Hai giá trị `tenant_id=1` và `tenant_id=487` có thể có phân bố dữ liệu hoàn toàn khác nhau.

**Không dùng một literal ngẫu nhiên để benchmark** rồi suy rộng cho tất cả tenants.

### Bước 2 — Ghi baseline an toàn

~~~sql
EXPLAIN (VERBOSE, SETTINGS)
SELECT ...
~~~

`EXPLAIN` không `ANALYZE` chỉ xây kế hoạch; thích hợp để xem một statement chưa được phép chạy thật. Nếu câu truy vấn là `SELECT` không có side effect và trên môi trường phù hợp, mở rộng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS)
SELECT ...
~~~

**Cẩn thận:** `EXPLAIN ANALYZE` **thực thi câu SQL**. Dùng nó trên `UPDATE`, `DELETE`, `INSERT` hoặc function có side effect có thể thay đổi dữ liệu thật. Không dùng trên production khi chưa có quyền/kế hoạch.

### Bước 3 — Đọc cây từ dưới lên

Tìm:

- Node đầu vào đang đọc bao nhiêu hàng;
- `rows` ước lượng so với `actual rows`;
- `loops` nhân chi phí lặp lại của inner path;
- `Rows Removed by Filter`, `Rows Removed by Join Filter`;
- `Index Cond` so với `Filter`;
- `Sort Method`, Disk, `Hash Batches`, temp buffers;
- `Workers Planned/Launched`;
- Nơi execution time/buffer I/O tăng mạnh.

### Bước 4 — Đặt giả thuyết cụ thể

Ví dụ:

> Planner dự đoán 150 hàng của tenant, thực tế 160.000; Nested Loop phải lookup inner index quá nhiều. Nghi nguyên nhân là thống kê phân bố `tenant_id` cũ hoặc prepared generic plan không phù hợp với tenant lớn.

Giả thuyết này **có thể kiểm tra**, khác với câu “PostgreSQL chọn Nested Loop ngu”.

### Bước 5 — Chạy một thí nghiệm thay đổi duy nhất

Ví dụ:

~~~sql
BEGIN;
SET LOCAL enable_nestloop = off;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT ...;

ROLLBACK;
~~~

**Kết quả nhanh hơn** chứng minh một **đường thay thế có thể nhanh hơn trong điều kiện thử**, **không chứng minh** Nested Loop là nguyên nhân gốc hay cần vô hiệu hóa nó toàn hệ thống.

### Bước 6 — Sửa nguyên nhân gốc

Có thể là:

- `ANALYZE`/statistics target;
- Extended statistics cho cột phụ thuộc;
- Index composite/partial/expression phù hợp;
- Rewrite predicate để sargable;
- Sửa kiểu tham số, cast, timezone, collation;
- Điều chỉnh schema, constraint hoặc join logic;
- Chọn custom plan khi skew đáng kể và workflow phù hợp;
- Giải quyết lock, I/O, memory, temp spill;
- Chỉ điều chỉnh cost parameter nếu đã có **bằng chứng hệ thống**.

### Bước 7 — Đo lại và triển khai có rollback

Đo các tenants/tham số phổ biến và ngoại lệ, cache nóng/lạnh, lúc tải nhẹ/cao, sau `ANALYZE` và sau data growth nếu có thể. Ghi lại kết quả và chuẩn bị rollback.

## 5. Bộ dữ liệu lab: tái hiện tình huống planner có thể chọn khác nhau

Trong lab, chúng ta tạo một bảng đơn hàng có **tenant lớn** và **nhiều tenant nhỏ**, rồi thử query có nhiều cách truy cập.

**Lưu ý:** SQL sau ghi hàng trăm nghìn dòng, tạo WAL và tiêu tốn đĩa. Chỉ chạy trên PostgreSQL lab; nếu tài nguyên hạn chế, giảm `generate_series` nhưng plan có thể khác. Không ép hàng triệu records vào production để “thử index”.

### 5.1. Tạo schema và bảng

~~~sql
CREATE SCHEMA plan_lab_291;

CREATE TABLE plan_lab_291.customers (
    customer_id INTEGER PRIMARY KEY,
    region TEXT NOT NULL
        CHECK (region IN ('north', 'south', 'central')),
    customer_type TEXT NOT NULL
        CHECK (customer_type IN ('regular', 'vip'))
);

CREATE TABLE plan_lab_291.orders (
    order_id BIGINT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL
        REFERENCES plan_lab_291.customers(customer_id),
    status TEXT NOT NULL
        CHECK (status IN ('paid', 'pending')),
    ordered_at TIMESTAMPTZ NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL
        CHECK (total_amount >= 0),
    payload TEXT NOT NULL DEFAULT ''
);
~~~

### 5.2. Nạp 10.000 khách hàng

~~~sql
INSERT INTO plan_lab_291.customers
    (customer_id, region, customer_type)
SELECT
    g::integer,
    CASE g % 3
        WHEN 0 THEN 'north'
        WHEN 1 THEN 'south'
        ELSE 'central'
    END,
    CASE
        WHEN g % 10 = 0 THEN 'vip'
        ELSE 'regular'
    END
FROM generate_series(1, 10000) AS s(g);
~~~

### 5.3. Nạp 400.000 đơn với phân bố lệch

~~~sql
INSERT INTO plan_lab_291.orders (
    order_id,
    tenant_id,
    customer_id,
    status,
    ordered_at,
    total_amount,
    payload
)
SELECT
    g::bigint,
    CASE
        WHEN g % 10 < 8 THEN 1
        ELSE (g % 500) + 2
    END::integer,
    ((g % 10000) + 1)::integer,
    CASE
        WHEN g % 10 < 8 THEN 'paid'
        ELSE 'pending'
    END,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + ((g * 97) % 31536000) * INTERVAL '1 second',
    ((g % 100000)::numeric / 100)::numeric(12, 2),
    repeat('x', 80)
FROM generate_series(1, 400000) AS s(g);
~~~

Tập dữ liệu có chủ ý:

- **80%** đơn có `tenant_id=1` và `status='paid'`.
- **20%** còn lại có `status='pending'` và `tenant_id` không phải 1; các mã tenant nhỏ xuất hiện theo `g % 500`.
- `tenant_id` và `status` có **tương quan rất mạnh**.
- `customer_id` lặp lại, phục vụ thử `JOIN`.
- Dữ liệu có khoảng 400.000 hàng với payload để chi phí truy cập khác biệt đáng kể.

### 5.4. Kiểm tra phân bố

~~~sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE tenant_id = 1) AS big_tenant_rows,
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_rows,
    COUNT(*) FILTER (
        WHERE tenant_id = 1 AND status = 'pending'
    ) AS big_tenant_pending_rows
FROM plan_lab_291.orders;
~~~

Kết quả logic mong đợi:

| Chỉ số | Giá trị |
| --- | ---: |
| `all_orders` | 400.000 |
| `big_tenant_rows` | 320.000 |
| `paid_rows` | 320.000 |
| `big_tenant_pending_rows` | 0 |

Do công thức dữ liệu, không tồn tại đơn `pending` cho tenant 1. Điều này thuận lợi để minh họa cách **ước lượng bằng giả định độc lập giữa các cột** có thể khác thực tế.

### 5.5. Thu thập thống kê

~~~sql
ANALYZE plan_lab_291.customers;
ANALYZE plan_lab_291.orders;
~~~

`ANALYZE` thu thập **thống kê dạng mẫu** cho planner. Thống kê có thể không hoàn hảo, đặc biệt khi phân bố lệch hoặc tương quan nhiều cột. Nhưng nó là điểm khởi đầu đúng hơn so với việc tắt một scan method.

## 6. Bài kiểm tra đầu tiên: Seq Scan có thật sự sai?

### 6.1. Query lấy phần lớn bảng

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM plan_lab_291.orders
WHERE tenant_id = 1;
~~~

80% hàng thuộc tenant 1. Nếu planner chọn `Seq Scan` hoặc `Parallel Seq Scan`, **đó có thể là một kế hoạch hoàn toàn hợp lý**: đọc hàng loạt pages có thể rẻ hơn hàng trăm nghìn random heap lookups qua index.

### 6.2. Query lấy một tenant nhỏ

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, total_amount
FROM plan_lab_291.orders
WHERE tenant_id = 500;
~~~

Truy vấn này thường rất chọn lọc so với tenant 1. Nếu chưa có index `tenant_id`, Seq Scan có thể chậm vì phải đọc cả bảng để tìm ít hàng.

### 6.3. Thêm index đúng nhu cầu

~~~sql
CREATE INDEX idx_orders_tenant_291
ON plan_lab_291.orders (tenant_id);

ANALYZE plan_lab_291.orders;
~~~

Thử lại cả hai query. PostgreSQL **có thể**:

- Vẫn Seq Scan cho tenant 1, vì có quá nhiều hàng.
- Dùng Index/Bitmap Scan cho tenant nhỏ, vì lọc rất ít.

**Đây là điều tốt:** optimizer được quyền chọn đường khác nhau theo tham số và dữ liệu. Việc cố ép `Index Scan` cho tenant 1 có thể làm chậm hơn.

### 6.4. Không đánh giá theo output plan dự đoán duy nhất

Bảng demo, cache, visibility map, statistics và cấu hình có thể khiến PostgreSQL chọn plan khác ví dụ. **Bài học không đòi buộc nó in ra đúng một node.** Hãy ghi lại số hàng, buffers và elapsed time thay vì coi tên node là điểm số.

## 7. Phân biệt Index Cond và Filter

Xét chỉ mục:

~~~sql
CREATE INDEX idx_orders_ordered_at_291
ON plan_lab_291.orders (ordered_at);
~~~

Truy vấn sargable:

~~~sql
EXPLAIN
SELECT order_id, ordered_at
FROM plan_lab_291.orders
WHERE ordered_at >= TIMESTAMPTZ '2026-05-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-06-01 00:00:00+00';
~~~

Một `Index Cond` trên `ordered_at` có thể giúp giới hạn phạm vi phải quét. So sánh với:

~~~sql
EXPLAIN
SELECT order_id, ordered_at
FROM plan_lab_291.orders
WHERE ordered_at::date = DATE '2026-05-01';
~~~

Phép `timestamptz::date` áp dụng lên cột không phải cùng biểu thức với khóa B-tree trên `ordered_at`, đồng thời phụ thuộc `TimeZone` của session. Query này không tự tương đương một range trên cột mà planner chắc chắn có thể suy ra.

### 7.1. Rewrite thành half-open range

Đối với một **ngày theo timezone nghiệp vụ đã xác định**, tính hai mốc bắt đầu/kết thúc rồi lọc:

~~~sql
SELECT order_id, ordered_at
FROM plan_lab_291.orders
WHERE ordered_at >= TIMESTAMPTZ '2026-05-01 00:00:00+07'
  AND ordered_at <  TIMESTAMPTZ '2026-05-02 00:00:00+07';
~~~

Việc xác định riêng hai midnights theo timezone thật giúp tránh sai lệch DST ở các vùng có đổi giờ; không mặc định một ngày địa phương luôn 24 giờ.

### 7.2. Tại sao không tắt Seq Scan ngay?

Nếu query ban đầu không có `Index Cond` vì hàm/cast trên cột, tắt `enable_seqscan` có thể buộc PostgreSQL thử một index không phù hợp, nhưng **không làm điều kiện trở nên sargable**. Sửa cách viết predicate thường là giải pháp gốc.

### 7.3. Biểu thức cần dùng thường xuyên

Nếu business thật sự truy vấn theo `lower(email)` hay một biểu thức **IMMUTABLE** ổn định, có thể tạo **expression index** tương ứng. Tuy nhiên, không bọc `timestamptz::date` trong một hàm tự khai báo IMMUTABLE sai chỉ để vượt hạn chế: timezone/session thay đổi khiến khóa index sai.

## 8. Sai cardinality: nguyên nhân “đằng sau” Nested Loop chậm

Giả sử plan có:

~~~text
Nested Loop
  (cost=... rows=100 ...)
  (actual ... rows=180000 loops=1)
  -> Index Scan on orders o
       (estimated rows=100, actual rows=180000)
  -> Index Scan on customers c
       Index Cond: (customer_id = o.customer_id)
       (actual rows=1 loops=180000)
~~~

Một cách chẩn đoán hời hợt:

> Nested Loop rất tệ; hãy `SET enable_nestloop=off`.

Một cách chẩn đoán đúng hơn:

> Planner ước lượng chỉ 100 đơn hàng ở outer, nhưng thực tế 180.000. Vì thế nó tưởng 100 lần lookup inner index là rẻ; thực tế cần 180.000 lần. Nguyên nhân đầu tiên cần kiểm tra là **estimate của outer relation**, không phải chỉ tên Nested Loop.

### 8.1. Nested Loop có lúc rất tốt

~~~sql
SELECT o.order_id, c.region
FROM plan_lab_291.orders AS o
JOIN plan_lab_291.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.order_id = 12345;
~~~

Outer chỉ một đơn, lookup customer theo primary key thường rất hiệu quả. `Nested Loop` ở đây có thể là giải pháp lý tưởng.

### 8.2. Khi outer rất lớn

~~~sql
SELECT o.order_id, c.region
FROM plan_lab_291.orders AS o
JOIN plan_lab_291.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.tenant_id = 1;
~~~

Outer có nhiều hàng; Hash Join, Nested Loop hoặc chiến lược khác có thể được cân nhắc. Đừng khẳng định chỉ một loại join là đúng mà không có cardinality/chi phí thực tế.

### 8.3. Loops là nhân tử rất quan trọng

~~~text
Index Scan on customers
  actual time=0.003..0.004 rows=1 loops=180000
~~~

Một lần index lookup mất khoảng vài micro/milliseconds có thể nhỏ, nhưng **180.000 lượt** cộng lại tạo chi phí lớn. Đọc `actual rows` mà bỏ qua `loops` sẽ đánh giá sai điểm nghẽn.

### 8.4. Chọn phương án sửa

- Nếu outer rows estimate sai: kiểm tra thống kê, tương quan cột, parameter, query rewrite.
- Nếu estimate đúng nhưng inner lookup tốn I/O: xem index, caching, join access.
- Nếu Hash Join thay thế nhanh rõ rệt: xác định vì sao planner đánh giá sai chi phí rồi thử sửa nguyên nhân tương ứng.
- Nếu join trả quá nhiều hàng do điều kiện thiếu: **sửa SQL semantics**, không ép join method.

## 9. Thống kê cũ hoặc chưa đủ chi tiết

PostgreSQL không đọc toàn bộ bảng mỗi lần lập kế hoạch. Nó dựa trên **statistics đã thu thập** và các ước lượng về kích thước relation/index. Khi bảng đã tăng trưởng mạnh mà thống kê chưa cập nhật, planner có thể tin vào số hàng thấp hơn thực tế rất nhiều.

### 9.1. Kiểm tra thống kê bảng

~~~sql
SELECT
    s.relid::regclass AS table_name,
    s.n_live_tup,
    s.n_dead_tup,
    s.last_analyze,
    s.last_autoanalyze,
    s.analyze_count,
    s.autoanalyze_count
FROM pg_catalog.pg_stat_user_tables AS s
WHERE s.schemaname = 'plan_lab_291'
ORDER BY s.relname;
~~~

**Lưu ý:** `n_live_tup` và `n_dead_tup` là các **ước lượng thống kê**, không phải phép `COUNT(*)` chính xác tại thời điểm truy vấn. `last_analyze` gần đây cũng không đảm bảo thống kê đủ tốt nếu dữ liệu có độ lệch lớn.

### 9.2. Xem số hàng dự kiến trong catalog

~~~sql
SELECT
    c.oid::regclass AS relation_name,
    c.reltuples::bigint AS estimated_rows,
    c.relpages AS estimated_pages,
    pg_catalog.pg_size_pretty(
        pg_catalog.pg_total_relation_size(c.oid)
    ) AS total_size
FROM pg_catalog.pg_class AS c
WHERE c.oid IN (
    'plan_lab_291.orders'::regclass,
    'plan_lab_291.customers'::regclass
);
~~~

`reltuples`/`relpages` được cập nhật qua maintenance/statistics và có thể được planner điều chỉnh theo kích thước file thực. Không dùng chúng như bảng đếm chính xác phục vụ nghiệp vụ.

### 9.3. ANALYZE đúng bảng

~~~sql
ANALYZE plan_lab_291.orders;
~~~

Sau đó chạy lại **cùng SQL, cùng giá trị tham số, cùng điều kiện tải**. Nếu estimated rows thay đổi đáng kể và plan hợp lý hơn, thống kê có thể là nguyên nhân quan trọng.

**Không chạy `VACUUM FULL` hoặc `REINDEX` chỉ vì thiếu statistics.** `ANALYZE` là công cụ đúng khi vấn đề là mẫu thống kê dùng cho planner; các lệnh kia giải quyết những mục đích khác và có chi phí/khóa riêng.

### 9.4. Khi mẫu mặc định bỏ sót đuôi phân phối

Với một cột có hàng nghìn giá trị, một vài tenant lớn và rất nhiều tenant nhỏ, mẫu thống kê mặc định có thể thiếu chi tiết. Có thể cân nhắc tăng **statistics target riêng cho cột**:

~~~sql
ALTER TABLE plan_lab_291.orders
ALTER COLUMN tenant_id SET STATISTICS 500;

ANALYZE plan_lab_291.orders;
~~~

Không nhầm `SET STATISTICS 500` với “thêm 500 workers” hoặc “tăng 500% RAM”. Nó tác động mức chi tiết/mẫu thống kê khi ANALYZE, đổi lại tốn công collect/stats storage và có thể tăng planning work.

Không tăng mọi cột lên `10000` trên production chỉ vì một query chậm. Tập trung cột đang làm planner sai estimate.

### 9.5. Thuộc tính thống kê của từng cột

~~~sql
SELECT
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    histogram_bounds,
    correlation
FROM pg_catalog.pg_stats
WHERE schemaname = 'plan_lab_291'
  AND tablename = 'orders'
  AND attname IN ('tenant_id', 'status', 'ordered_at')
ORDER BY attname;
~~~

Giải thích:

| Thuộc tính | Vai trò |
| --- | --- |
| `null_frac` | Tỷ lệ giá trị NULL trong mẫu |
| `n_distinct` | Ước lượng số giá trị khác nhau; giá trị âm thể hiện tỷ lệ tương đối với số hàng |
| `most_common_vals` | Những giá trị xuất hiện nhiều nhất (MCV) |
| `most_common_freqs` | Tần suất ước lượng của các MCV |
| `histogram_bounds` | Các mốc phân phối phục vụ ước lượng range |
| `correlation` | Tương quan thứ tự giá trị với vị trí vật lý, ảnh hưởng cost index scan |

Trong tập dữ liệu lab, `tenant_id=1` là giá trị rất phổ biến. `most_common_vals` và `most_common_freqs` có thể phản ánh điều đó.

### 9.6. Correlation trong pg_stats không phải phụ thuộc giữa hai cột

`pg_stats.correlation` đo mối liên hệ giữa **giá trị một cột và thứ tự vật lý của hàng** — hữu ích cho ước lượng heap I/O qua index. Nó **không** đo trực tiếp phụ thuộc giữa `tenant_id` và `status`.

Muốn mô tả **tương quan nhiều cột** cho planner, sử dụng **extended statistics** phù hợp.

## 10. Extended statistics: sửa ước lượng sai do giả định độc lập

Trong dữ liệu lab:

~~~text
tenant_id = 1         → 320.000 hàng
status = 'pending'    → 80.000 hàng
tenant_id=1 AND pending → 0 hàng
~~~

Nếu chỉ biết tần suất từng cột và giả định độc lập, một phép tính ước lượng đơn giản sẽ là:

\[
P(\text{tenant}=1 \land \text{pending})
\approx 0.8 \times 0.2 = 0.16
\]

Nhân với 400.000 hàng cho ra khoảng **64.000**, trong khi thực tế có **0**. Đây là minh họa cho tính nguy hiểm của **giả định độc lập giữa những cột có tương quan**; con số estimated rows thực tế của PostgreSQL còn phụ thuộc MCV/statistics/kiểu predicate nên không bắt buộc đúng 64.000.

### 10.1. Tái hiện một query có tương quan

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM plan_lab_291.orders
WHERE tenant_id = 1
  AND status = 'pending';
~~~

Kết quả SQL đúng bằng **0**, nhưng planner có thể ước lượng cao hơn nhiều nếu chưa biết sự phụ thuộc. Một plan scan lớn để trả về 0 hàng không tự chứng minh PostgreSQL “không hỗ trợ index”; cần hiểu số hàng đã bị ước lượng sai.

### 10.2. Tạo thống kê đa cột

~~~sql
CREATE STATISTICS st_orders_tenant_status_291
    (dependencies, mcv, ndistinct)
ON tenant_id, status
FROM plan_lab_291.orders;

ANALYZE plan_lab_291.orders;
~~~

Các loại:

- **`dependencies`:** thông tin phụ thuộc chức năng/tương quan giữa cột, có ích cho các điều kiện kiểu equality trong những trường hợp PostgreSQL hỗ trợ.
- **`mcv`:** nhóm tổ hợp giá trị phổ biến nhiều cột, giúp ước lượng những tổ hợp như `tenant_id=1, status='pending'`.
- **`ndistinct`:** số tổ hợp khác nhau, hữu ích trong một số ước lượng như `GROUP BY`.

Không xem chúng như ba phép “tắt sai số” tuyệt đối. Một số dạng predicate, join, expressions và tập dữ liệu vẫn khó ước lượng; phải đo lại estimated/actual.

### 10.3. Xem extended statistics

~~~sql
SELECT
    statistics_name,
    attnames,
    kinds,
    n_distinct,
    dependencies,
    most_common_vals,
    most_common_freqs
FROM pg_catalog.pg_stats_ext
WHERE schemaname = 'plan_lab_291'
  AND tablename = 'orders'
ORDER BY statistics_name;
~~~

View `pg_stats_ext` giúp quan sát thông tin mà PostgreSQL giữ cho những stats objects đủ quyền xem. Các cột/chi tiết có thể khác theo major version; khi vận hành hãy đối chiếu docs phù hợp.

### 10.4. Extended stats có giới hạn

Chúng không biến planner thành hệ thống suy luận mọi quan hệ liên bảng. Đặc biệt, **extended statistics của một bảng không giải quyết mọi vấn đề ước lượng join selectivity qua nhiều bảng**. Nó cũng không thay:

- SQL JOIN đúng khóa;
- Foreign key/unique constraints phù hợp;
- Index theo predicate thực tế;
- Mô hình dữ liệu có ngữ nghĩa;
- Dữ liệu và thống kê đại diện workload.

### 10.5. Vì sao đây là sửa gốc hơn ép join?

Nếu sai estimate do `tenant_id` và `status` không độc lập, tắt `enable_nestloop` chỉ ép planner một đường khác **với cùng ước lượng dữ liệu sai**. Thêm MCV stats có thể giúp planner **hiểu số hàng đúng hơn**, từ đó chọn tốt hơn giữa scan, join và aggregate cho nhiều truy vấn liên quan.

## 11. Prepared statements: generic plan so với custom plan

Một nguồn regression khó nhận ra là **cùng câu SQL với tham số khác nhau** nhưng ứng dụng dùng **prepared statement**. PostgreSQL có thể chọn:

- **Custom plan:** lập kế hoạch có xét **giá trị tham số cụ thể** của lượt EXECUTE.
- **Generic plan:** kế hoạch tái sử dụng, **không tối ưu cho riêng một giá trị tham số**, nhằm giảm planning overhead.

Sự khác biệt đặc biệt quan trọng với dữ liệu skew như tenant 1 (320.000 hàng) và tenant 500 (rất ít hàng).

### 11.1. Hai tham số, hai nhu cầu truy cập

~~~sql
SELECT order_id, total_amount
FROM plan_lab_291.orders
WHERE tenant_id = 1;
~~~

so với:

~~~sql
SELECT order_id, total_amount
FROM plan_lab_291.orders
WHERE tenant_id = 500;
~~~

Tối ưu cho tenant 1 có thể nghiêng về Seq/Parallel Seq Scan; tối ưu cho tenant 500 có thể nghiêng về Index Scan. Một generic plan không biết giá trị `tenant_id` tại planning time có thể là thỏa hiệp không tối ưu cho một trong hai.

### 11.2. PREPARE và EXECUTE

~~~sql
PREPARE get_orders_by_tenant(integer) AS
SELECT order_id, total_amount
FROM plan_lab_291.orders
WHERE tenant_id = $1;

EXPLAIN EXECUTE get_orders_by_tenant(1);
EXPLAIN EXECUTE get_orders_by_tenant(500);
~~~

`PREPARE` định nghĩa statement parameterized; PostgreSQL sẽ quyết định plan theo chính sách hiện hành khi EXECUTE. Không được suy ra cứ nhìn thấy `PREPARE` thì generic plan chắc chắn được dùng ngay từ lần đầu.

### 11.3. So sánh có kiểm soát bằng plan_cache_mode

**Thử custom plan:**

~~~sql
BEGIN;
SET LOCAL plan_cache_mode = force_custom_plan;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE get_orders_by_tenant(1);

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE get_orders_by_tenant(500);

ROLLBACK;
~~~

**Thử generic plan:**

~~~sql
BEGIN;
SET LOCAL plan_cache_mode = force_generic_plan;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE get_orders_by_tenant(1);

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE get_orders_by_tenant(500);

ROLLBACK;
~~~

Ở đây `plan_cache_mode` dùng **chỉ để chẩn đoán** trong transaction. `force_custom_plan` có thể giúp các tham số skew, nhưng tăng **planning CPU** trên nhiều executions. `force_generic_plan` có thể giảm planning overhead nhưng dẫn đến run-time tệ cho giá trị không đại diện.

### 11.4. Xem thông tin prepared statement

~~~sql
SELECT
    name,
    parameter_types,
    generic_plans,
    custom_plans
FROM pg_catalog.pg_prepared_statements
WHERE name = 'get_orders_by_tenant';
~~~

Chỉ số generic/custom trong view giúp hiểu lựa chọn ở session hiện tại. **Prepared statements sống trong session**, không phải một bảng lưu toàn bộ statement của mọi client kết nối.

### 11.5. Trả về trạng thái bình thường

~~~sql
DEALLOCATE get_orders_by_tenant;
~~~

`ROLLBACK` ở các khối `SET LOCAL` đã khôi phục cấu hình của transaction, nhưng không tự có nghĩa xóa prepared statement đã được tạo **trước** các transaction ấy. `DEALLOCATE` giải phóng statement lab.

### 11.6. Một kinh nghiệm sản xuất quan trọng

Nếu một query nhanh ở `psql` khi chèn literal nhưng chậm trong ứng dụng:

1. Lấy đúng SQL và kiểu bind parameters;
2. Kiểm tra prepared/generic plan behavior của driver/connection pool;
3. So sánh custom/generic trên cả tham số lớn và nhỏ;
4. Đánh giá planning overhead so với execution time;
5. Cân nhắc rewrite/index/stats trước khi ép `force_custom_plan` toàn hệ thống.

## 12. Sargability: sửa SQL trước khi tìm hint

*Sargable predicate* là điều kiện có thể được bộ máy truy cập dữ liệu khai thác tốt, thường bằng cách áp dụng một range/equality trực tiếp lên cột đã index.

### 12.1. Hàm áp lên cột

~~~sql
-- Không nhất thiết dùng được B-tree trên ordered_at:
WHERE date_trunc('day', ordered_at) =
      TIMESTAMPTZ '2026-05-01 00:00:00+00'
~~~

Ngoài ảnh hưởng index, `date_trunc(text, timestamptz)` có ngữ nghĩa phụ thuộc timezone của session. Một phép so sánh ngày đúng phải xuất phát từ **timezone nghiệp vụ**, sau đó dùng range trên `ordered_at`.

### 12.2. Cộng/trừ hằng số trên cột

~~~sql
-- Có thể làm biểu thức khác khóa index total_amount:
SELECT order_id
FROM plan_lab_291.orders
WHERE total_amount + 100 >= 500;
~~~

Nếu muốn lọc `total_amount >= 400` và loại dữ liệu numeric không có side effect:

~~~sql
SELECT order_id
FROM plan_lab_291.orders
WHERE total_amount >= 400;
~~~

Index trên `total_amount` (nếu được tạo) phù hợp trực tiếp hơn. **Chỉ biến đổi đại số khi ngữ nghĩa được bảo toàn**, đặc biệt với NULL, overflow, float rounding và kiểu dữ liệu.

### 12.3. LIKE và tiền tố

~~~sql
WHERE email LIKE '%example.com'
~~~

khác với:

~~~sql
WHERE email LIKE 'anh%'
~~~

B-tree thông thường không tối ưu mọi substring predicate; prefix có thể cần operator class phù hợp với collation. Khi thật sự cần substring search, cân nhắc extension `pg_trgm` và GIN/GiST phù hợp; **đừng tắt Seq Scan** để ép một B-tree không hỗ trợ điều kiện tìm kiếm như mong muốn.

### 12.4. Ép kiểu tham số

~~~sql
WHERE customer_id::text = '123'
~~~

biểu thức ở vế trái khác B-tree trên `customer_id INTEGER`. Khi API có số nguyên hợp lệ, phù hợp hơn:

~~~sql
WHERE customer_id = 123
~~~

**Không sửa bằng một cast ngẫu nhiên** có thể làm query sai hoặc mất dữ liệu; mục tiêu là thống nhất **kiểu cột, tham số JDBC/ORM và toán tử**.

### 12.5. OR, IN và UNION ALL

Với những điều kiện `OR` trên nhiều cột, PostgreSQL có thể dùng `BitmapOr` trên indexes hoặc Seq Scan. Đôi khi rewrite thành `UNION ALL` với hai nhánh lọc riêng có lợi, nhưng chỉ đúng nếu hiểu **ngữ nghĩa trùng hàng**:

~~~sql
-- Ví dụ minh họa:
SELECT order_id
FROM plan_lab_291.orders
WHERE tenant_id = 1
   OR customer_id = 42;
~~~

Nếu tách làm hai query ghép `UNION ALL`, một hàng thỏa cả hai nhánh có thể bị **trả hai lần**. Đừng đổi kế hoạch bằng rewrite làm sai kết quả. `UNION` loại trùng nhưng có chi phí sort/hash; cần đo thay vì áp dụng như công thức.

## 13. Một index phù hợp có thể tốt hơn mọi hint

Thay vì ép scan method, hãy đặt câu hỏi **đường truy cập nào phục vụ chính predicate + sort + limit**.

### 13.1. Index composite cho multi-tenant query

~~~sql
CREATE INDEX idx_orders_tenant_status_time_291
ON plan_lab_291.orders (
    tenant_id,
    status,
    ordered_at DESC,
    order_id DESC
);
~~~

Truy vấn:

~~~sql
SELECT
    order_id,
    ordered_at,
    total_amount
FROM plan_lab_291.orders
WHERE tenant_id = 500
  AND status = 'pending'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
~~~

Index có thể hỗ trợ:

- Equality trên `tenant_id`/`status`;
- Order theo `ordered_at DESC, order_id DESC`;
- Dừng sớm với `LIMIT 20` khi đường truy cập thích hợp.

### 13.2. Vì sao thứ tự cột index quan trọng?

B-tree composite thông thường đặc biệt hữu ích với điều kiện theo **tiền tố khóa**. Index `(tenant_id, status, ordered_at DESC)` không phải câu trả lời tối ưu mặc định cho:

~~~sql
WHERE ordered_at >= ...
~~~

khi không có điều kiện trên hai cột đầu; planner có thể phải xem chiến lược khác. Thiết kế index từ **query patterns**, không chỉ từ danh sách cột hay dùng trong bảng.

### 13.3. Partial index khi predicate ổn định

~~~sql
CREATE INDEX idx_orders_paid_tenant_time_291
ON plan_lab_291.orders (
    tenant_id,
    ordered_at DESC
)
WHERE status = 'paid';
~~~

Index này chỉ chứa các đơn `paid`. Nó có thể hữu ích nếu query thường xuyên lọc `status='paid'` và tập paid có đặc điểm phù hợp; **trong dataset lab paid chiếm 80%**, nên partial index không nhất thiết đặc biệt nhỏ. Không tạo partial index chỉ vì tên “partial” nghe nhanh hơn.

Planner cần nhận ra query predicate **hàm ý** điều kiện `status='paid'` của index. Với generic plans có tham số `status=$1` chưa biết lúc lập kế hoạch, index partial theo literal có thể **không được suy luận là phù hợp** cho mọi giá trị.

### 13.4. Covering index không miễn phí

~~~sql
CREATE INDEX idx_orders_tenant_cover_291
ON plan_lab_291.orders (tenant_id, ordered_at DESC)
INCLUDE (total_amount);
~~~

`INCLUDE` có thể giúp index-only scan khi đủ cột và heap visibility cho phép, nhưng:

- Index lớn hơn;
- `INSERT`/`UPDATE` tốn thêm công bảo trì;
- `Heap Fetches` vẫn có thể xảy ra;
- B-tree index-only scan không tự có ích với mọi predicate.

Đừng tạo nhiều index gần trùng chỉ để plan nhìn “đẹp” hơn.

### 13.5. Kiểm tra index usage

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    indexrelname AS index_name,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_catalog.pg_stat_user_indexes
WHERE schemaname = 'plan_lab_291'
ORDER BY idx_scan DESC, indexrelname;
~~~

`idx_scan=0` trong một khoảng đo ngắn không chứng minh index vô dụng, nhất là index `UNIQUE` dùng bảo vệ dữ liệu khi ghi. Statistics có thể reset; cần biết thời gian quan sát và workload.

## 14. Sort spill và Hash spill: vấn đề bộ nhớ, không hẳn vấn đề plan

Một query có thể có **ước lượng số hàng tương đối đúng** nhưng chạy chậm vì phép sort hoặc hash không đủ bộ nhớ, phải sử dụng file tạm trên đĩa.

### 14.1. Quan sát Sort Method

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_id,
    total_amount
FROM plan_lab_291.orders
ORDER BY total_amount DESC, order_id DESC;
~~~

Một plan minh họa:

~~~text
Sort
  Sort Key: total_amount DESC, order_id DESC
  Sort Method: external merge  Disk: 16000kB
  -> Seq Scan on orders
~~~

`external merge` và `Disk` cho biết sort đã phải sử dụng lưu trữ tạm. Nếu trông thấy:

~~~text
Sort Method: quicksort  Memory: 24000kB
~~~

thì sort ở node đó dùng phương thức và memory khác.

**Không suy ra cứ có Sort là planner sai.** Nếu query yêu cầu sắp toàn bộ kết quả và không có đường truy cập đã sắp phù hợp, sort là công việc bắt buộc.

### 14.2. work_mem không phải RAM tối đa của một query

`work_mem` là mức ngân sách cho **một số operation** như sort/hash trước khi spill, không phải giới hạn RAM cho toàn SQL.

~~~sql
BEGIN;

SET LOCAL work_mem = '64MB';

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT order_id, total_amount
FROM plan_lab_291.orders
ORDER BY total_amount DESC, order_id DESC;

ROLLBACK;
~~~

Đây là thí nghiệm cô lập. Nếu tăng `work_mem` khiến sort không còn spill và query nhanh hơn, bạn đã có bằng chứng về **memory pressure ở sort**. Nhưng tăng global `work_mem` lên vài GB cho hàng trăm connections có thể dẫn tới OOM/swap, đặc biệt khi một query có nhiều sort/hash và parallel workers.

### 14.3. Tạo index theo thứ tự cũng là một lựa chọn

~~~sql
CREATE INDEX idx_orders_amount_desc_291
ON plan_lab_291.orders (
    total_amount DESC,
    order_id DESC
);
~~~

Với:

~~~sql
SELECT order_id, total_amount
FROM plan_lab_291.orders
ORDER BY total_amount DESC, order_id DESC
LIMIT 20;
~~~

index có thể cho phép đọc **20 hàng đầu tiên** nhanh hơn một sort toàn bảng. Nhưng với query yêu cầu **tất cả 400.000 dòng**, single index scan chưa chắc rẻ hơn Seq Scan + Sort, vì heap access và dữ liệu trả về.

**Không tạo index chỉ từ giả thuyết**; đo đúng query/limit và chi phí ghi.

### 14.4. Hash Join spill

Trong `EXPLAIN ANALYZE` của một Hash Join, có thể thấy:

~~~text
Hash
  Buckets: ...
  Batches: 16
  Memory Usage: ...
Buffers: temp read=... written=...
~~~

`Batches > 1` có thể phản ánh hash table phải xử lý theo nhiều batch, thường liên quan memory/data size. Nếu dữ liệu thực lớn hơn nhiều ước lượng, gốc có thể vẫn là **cardinality estimate sai**; nếu estimate đúng nhưng hash spill do bộ nhớ thấp, thử memory per-operation một cách có kiểm soát.

### 14.5. Đừng tắt Hash Join vì Hash spill

~~~sql
SET LOCAL enable_hashjoin = off;
~~~

có thể khiến planner chọn Merge Join hoặc Nested Loop, nhưng nếu vấn đề thật là work_mem, rows ước lượng sai hoặc thiếu index để sort, một join method khác có thể tốn kém hơn. Kiểm tra cả **memory**, **cardinality** và **join keys** trước khi chốt phương án.

## 15. Parallel query: thiếu workers không đồng nghĩa sai planner

Với query tổng hợp lớn:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT COUNT(*), SUM(total_amount)
FROM plan_lab_291.orders
WHERE status = 'paid';
~~~

Plan có thể:

~~~text
Finalize Aggregate
  -> Gather
       Workers Planned: 3
       Workers Launched: 1
       -> Partial Aggregate
            -> Parallel Seq Scan on orders
~~~

Nếu launch ít workers hơn planned, tổng thời gian có thể cao hơn kỳ vọng. **Đổi `enable_seqscan`** không giải quyết việc không có workers.

### 15.1. Những giới hạn cần xem

~~~sql
SHOW max_parallel_workers_per_gather;
SHOW max_parallel_workers;
SHOW max_worker_processes;
SHOW parallel_setup_cost;
SHOW parallel_tuple_cost;
SHOW parallel_leader_participation;
~~~

Kiểm tra thêm tải CPU và số query đồng thời. Nâng `max_parallel_workers_per_gather` không tạo thêm CPU vật lý; một query nhanh hơn lúc ít tải có thể làm **throughput tổng thể kém đi** khi nhiều request tranh workers.

### 15.2. Gather chuyển quá nhiều hàng

Nếu `Gather` phải thu hàng triệu tuples để trả `SELECT *`, leader và mạng/client có thể là bottleneck. `Partial Aggregate` hoặc `LIMIT`/pagination đúng nghiệp vụ có thể giảm lượng dữ liệu chuyển hơn việc tăng workers.

### 15.3. Gather Merge và ORDER BY

`Gather Merge` bảo toàn **thứ tự theo các sort keys** của những luồng đã sắp; `Gather` thông thường không bảo toàn thứ tự toàn cục. Nếu query cần:

~~~sql
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20
~~~

một B-tree composite index và single index scan có thể rẻ hơn parallel scan + Gather Merge. Đừng ép parallel chỉ vì thấy server còn nhiều cores.

### 15.4. Bảng nhỏ, query ngắn

Trên bảng có vài trăm hàng, chi phí worker startup có thể vượt thời gian của Seq Scan. “Không có Parallel Seq Scan” **không phải regression** khi latency đã rất thấp.

## 16. JIT compilation: CPU startup đôi khi che mất lợi ích

PostgreSQL có thể dùng **JIT (Just-in-Time compilation)** cho một số query theo cấu hình và ngưỡng cost. JIT có thể giúp workload CPU-bound lớn nhưng có **chi phí khởi tạo compilation**.

### 16.1. Kiểm tra

~~~sql
SHOW jit;
SHOW jit_above_cost;
SHOW jit_inline_above_cost;
SHOW jit_optimize_above_cost;
~~~

### 16.2. EXPLAIN có thông tin JIT

Trên server/plan có JIT, `EXPLAIN ANALYZE` có thể ghi thời gian `Generation`, `Inlining`, `Optimization`, `Emission`. Nếu query thực thi chỉ vài milliseconds nhưng JIT startup chiếm tỷ trọng đáng kể, hãy xem chính sách JIT.

### 16.3. Thử nghiệm cô lập

~~~sql
BEGIN;

SET LOCAL jit = off;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT SUM(total_amount * 1.05)
FROM plan_lab_291.orders;

ROLLBACK;
~~~

So với cùng query có JIT khi bật và được planner kích hoạt. **Không kết luận JIT là nguyên nhân khi plan không dùng JIT hoặc dữ liệu không đại diện**. Việc tắt JIT toàn bộ server để chữa một câu SQL nhỏ có thể làm những query phân tích lớn chạy chậm hơn.

## 17. Chờ khóa: EXPLAIN đơn lẻ có thể không tái hiện

Một backend có thể dùng kế hoạch tốt nhưng bị chặn bởi transaction khác:

~~~text
Session A:
  BEGIN;
  UPDATE một hàng;
  ... giữ transaction lâu chưa COMMIT ...

Session B:
  UPDATE cùng hàng;
  ... phải chờ row lock ...
~~~

Nếu B mất 20 giây vì chờ A, việc thay planner từ Index Scan sang Seq Scan không giải quyết khóa.

### 17.1. Xem wait event và blocker

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.xact_start,
    now() - a.xact_start AS transaction_age,
    pg_catalog.pg_blocking_pids(a.pid) AS blocking_pids,
    a.query
FROM pg_catalog.pg_stat_activity AS a
WHERE a.wait_event_type = 'Lock'
ORDER BY a.xact_start NULLS LAST;
~~~

Quyền xem query text và thông tin session khác phụ thuộc role/cluster. Cần xem cả **query đang giữ khóa**, transaction mở lâu và logic ứng dụng.

### 17.2. idle in transaction

~~~sql
SELECT
    pid,
    datname,
    application_name,
    state,
    now() - xact_start AS transaction_age,
    backend_xmin
FROM pg_catalog.pg_stat_activity
WHERE state = 'idle in transaction'
ORDER BY xact_start;
~~~

Một session idle in transaction có thể giữ row locks/snapshot và làm chậm các query khác hoặc VACUUM. Tối ưu plan của session B không thay thế việc **kết thúc transaction A đúng lúc**.

### 17.3. Phân biệt timeout

Các cấu hình `lock_timeout` và `statement_timeout` có mục đích khác:

- `lock_timeout` giới hạn thời gian chờ lấy khóa;
- `statement_timeout` giới hạn thời gian một câu SQL chạy;
- `idle_in_transaction_session_timeout` giúp xử lý session ở trạng thái idle trong transaction quá lâu.

**Timeout là hàng rào vận hành**, không phải giải pháp cho join order hay cardinality estimate. Cần xử lý nguyên nhân tắc nghẽn thay vì chỉ tăng timeout.

### 17.4. Đừng tự kết thúc blocker

`pg_cancel_backend`/`pg_terminate_backend` là biện pháp có tác động tới transaction và ứng dụng. Trước khi dùng trên production, xác định owner, nghiệp vụ đang chạy, khả năng rollback và quyền thực hiện. Không cắt một transaction thanh toán/migration chỉ để benchmark một plan.

## 18. Cache, I/O và correlation: cùng plan nhưng thời gian khác

Một `Index Scan` có thể nhanh khi heap pages đã nằm trong shared buffers/OS cache và chậm hơn nhiều khi phải đọc random blocks từ đĩa.

### 18.1. BUFFERS

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, total_amount
FROM plan_lab_291.orders
WHERE tenant_id = 500;
~~~

Các trường:

- `shared hit`: số lần truy cập block lấy từ shared buffers;
- `shared read`: block phải được đọc vào shared buffers, nhưng **không đồng nghĩa mọi lần read đều là đĩa vật lý chậm** vì còn OS cache;
- `shared dirtied/written`: thay đổi/ghi block khi phù hợp;
- `temp read/written`: sử dụng file tạm trong các operations như sort/hash.

### 18.2. Vì sao không so hai lượt chạy mà bỏ cache?

~~~text
Lượt 1: dữ liệu chưa nóng → shared reads nhiều
Lượt 2: dữ liệu đã cache → shared hits nhiều
~~~

Nếu trước/sau thay đổi plan còn có khác biệt cache, **không thể quy toàn bộ speedup cho planner toggle**. Nên đo nhiều lượt và ghi bối cảnh cache/tải.

### 18.3. B-tree vs Seq Scan trên nhiều hàng

Index Scan có thể cần nhiều random heap visits. Khi query lọc phần lớn bảng, Seq Scan đọc các pages tuần tự có thể tốt hơn ngay cả trên SSD. Chọn `random_page_cost` thấp hơn chỉ vì dùng SSD **không tự chứng minh** rằng mọi Index Scan nên thắng.

### 18.4. Correlation và sắp xếp vật lý

`pg_stats.correlation` cao theo tuyệt đối có thể giúp một index scan tiếp cận heap có tính tuần tự hơn. Nếu dữ liệu đã thay đổi nhiều, correlation có thể khác trước. Tuy nhiên, `CLUSTER`/rewrite bảng để thay thứ tự vật lý là thao tác có chi phí/khóa lớn; không phải bước đầu tiên chỉ vì query có Seq Scan.

### 18.5. Quan sát nguồn I/O lớn hơn

Khi có quyền và phiên bản hỗ trợ, các chỉ số `pg_stat_io` (PostgreSQL hiện đại), OS I/O, cloud storage latency, checkpoint activity và autovacuum activity có thể giúp tách vấn đề thiết bị khỏi plan. **EXPLAIN BUFFERS là một nguồn bằng chứng, không phải máy đo chính xác mọi thời gian chờ đĩa.**

## 19. Phân vùng, pruning và nguyên nhân ẩn phía sau Append

Nếu bảng được partition theo `ordered_at` hoặc `tenant_id`, một query có thể đọc nhiều partitions không cần thiết vì predicate không cho phép **partition pruning**.

Ví dụ ý tưởng:

~~~text
Append
  -> Seq Scan on orders_2026_01
  -> Seq Scan on orders_2026_02
  -> Seq Scan on orders_2026_03
  ...
~~~

Nếu query chỉ cần tháng 3 nhưng plan đọc cả 12 partitions, câu hỏi đầu tiên là:

> Điều kiện lọc có khớp partition key/opclass và có thể được planner/executor dùng để prune không?

Không phải:

> Tắt Seq Scan để từng partition dùng Index Scan.

### 19.1. Lọc bằng range sargable

~~~sql
WHERE ordered_at >= TIMESTAMPTZ '2026-03-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-04-01 00:00:00+00'
~~~

thường giúp prune khi partition theo range tương thích. Áp hàm không phù hợp lên partition key có thể khiến PostgreSQL không suy ra các partitions cần bỏ qua.

### 19.2. Pruning có thể xảy ra lúc thực thi

Prepared statements với tham số có thể được PostgreSQL prune ở **planning time** hoặc **execution time** tùy plan và cơ chế pruning. Trong `EXPLAIN ANALYZE` đôi khi thấy các subplans không chạy hoặc “Subplans Removed”. Không kết luận một generic plan có nhiều partition nodes hiển thị sẽ thực sự quét hết mọi partition.

### 19.3. Thống kê trên partitions

Mỗi partition có thống kê/size riêng. Khi dữ liệu phân bố lệch, thống kê parent và partitions, autovacuum/analyze behavior, và số lượng partitions đều có thể ảnh hưởng ước lượng. Cần xác định **partition nào thật sự tốn thời gian/buffers**.

## 20. Hiểu chính xác ý nghĩa của planner switches

PostgreSQL có các tham số:

~~~sql
SHOW enable_seqscan;
SHOW enable_indexscan;
SHOW enable_indexonlyscan;
SHOW enable_bitmapscan;
SHOW enable_nestloop;
SHOW enable_hashjoin;
SHOW enable_mergejoin;
SHOW enable_sort;
SHOW enable_material;
SHOW enable_hashagg;
SHOW enable_memoize;
~~~

Một số tham số được hỗ trợ tùy major version. Các công tắc dạng `enable_*` giúp planner cân nhắc hoặc **discourage** một loại plan node.

### 20.1. "off" không luôn là vô hiệu tuyệt đối

Đặc biệt, PostgreSQL không thể loại bỏ hoàn toàn mọi `Seq Scan` hay `Nested Loop`: có trường hợp đó là cách khả thi hoặc bắt buộc. `enable_seqscan=off` thường **làm chi phí giả định của Seq Scan trở nên rất kém hấp dẫn**, không đảm bảo plan cuối hoàn toàn không có Seq Scan.

### 20.2. Mục đích đúng: thí nghiệm phản chứng

Giả sử nghi:

> Planner chọn Nested Loop vì đánh giá chi phí Hash Join quá cao.

Bạn có thể:

~~~sql
BEGIN;

SET LOCAL enable_nestloop = off;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT
    o.order_id,
    c.region
FROM plan_lab_291.orders AS o
JOIN plan_lab_291.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.tenant_id = 1;

ROLLBACK;
~~~

Thử nghiệm nói **có tồn tại đường thay thế tốt không**, không trả lời một cách tự động **tại sao đường cũ bị chọn**. Trả lời câu hỏi thứ hai cần xem rows estimate, stats, query pattern và cost assumptions.

### 20.3. Thí nghiệm với Seq Scan

~~~sql
BEGIN;

SET LOCAL enable_seqscan = off;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT order_id
FROM plan_lab_291.orders
WHERE tenant_id = 500;

ROLLBACK;
~~~

Nếu plan đổi sang Index Scan và chạy nhanh hơn, kiểm tra liệu:

- Bảng/index đã ANALYZE chưa?
- Predicate có đúng kiểu cột và có index phù hợp không?
- Planner đang đánh giá bao nhiêu rows?
- Index còn chọn lọc trên những tham số khác không?
- Cache/runtime test có tương đồng không?

### 20.4. Không dùng SET SESSION rồi quên khôi phục

~~~sql
SET enable_seqscan = off;
~~~

thay đổi setting trong session và có thể tồn tại trên connection được pool tái sử dụng nếu ứng dụng/pool không reset. **Đối với thí nghiệm, ưu tiên `SET LOCAL` trong `BEGIN ... ROLLBACK`** để không làm ảnh hưởng những query về sau.

### 20.5. Không thay postgresql.conf trước khi có baseline

Chỉnh `enable_nestloop=off` hay `random_page_cost` toàn server là thay đổi phạm vi rộng, ảnh hưởng các truy vấn có phân bố tham số khác nhau, thậm chí những query trước đây nhanh. Nếu bắt buộc thử cấu hình rộng, cần change management, phạm vi, thời gian, phép đo và rollback.

## 21. Thay cost parameters: chỉ khi có bằng chứng môi trường

Các tham số:

| Tham số | Nội dung phản ánh |
| --- | --- |
| `seq_page_cost` | Chi phí tương đối của đọc page tuần tự |
| `random_page_cost` | Chi phí tương đối của đọc page ngẫu nhiên |
| `cpu_tuple_cost` | Chi phí xử lý tuple |
| `cpu_index_tuple_cost` | Chi phí xử lý index tuple |
| `cpu_operator_cost` | Chi phí toán tử/hàm trong ước lượng |
| `effective_cache_size` | Ước lượng bộ nhớ cache có thể tận dụng, **không phải RAM cấp phát** |
| `effective_io_concurrency` | Gợi ý/điều chỉnh liên quan khả năng I/O concurrent của storage |
| `parallel_setup_cost` | Chi phí ước tính khởi tạo parallel plan |
| `parallel_tuple_cost` | Chi phí ước tính chuyển tuples từ workers |

### 21.1. Không lấy random_page_cost=1.1 như “mẹo SSD” mặc định

Một SSD nhanh có thể làm random I/O rẻ hơn so với HDD, nhưng chi phí planner còn phụ thuộc cache, workload, table correlation và mức I/O thực tế. Nếu hệ thống có nhiều query lớn thì một thay đổi ngầm định rẻ hơn cho random reads có thể khiến planner dùng nhiều Index Scans với heap fetches lớn.

### 21.2. effective_cache_size không phân bổ bộ nhớ

~~~sql
SHOW effective_cache_size;
~~~

Đây là **ước lượng cache sẵn có** mà planner dùng để costing khả năng đọc pages, không phải lệnh cấp thêm một vùng RAM đúng bằng giá trị ấy. Tăng nó không tự tăng `shared_buffers` hay làm OS cache lớn hơn.

### 21.3. Có phải cần đặt chi phí “đúng bằng milliseconds”?

Không. Các cost constants là hệ quy chiếu tương đối. Phép điều chỉnh muốn có giá trị cần so sánh các plan của **nhiều query đại diện** và đảm bảo không làm chi phí chung lệch vô lý.

### 21.4. Thử nghiệm có phạm vi

~~~sql
BEGIN;

SET LOCAL random_page_cost = 1.5;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT order_id, total_amount
FROM plan_lab_291.orders
WHERE tenant_id = 500;

ROLLBACK;
~~~

Khi kết quả đổi, chỉ ghi nhận đây là **thử nghiệm cost sensitivity**. Để quyết định chỉnh cấu hình thật, cần bằng chứng rộng hơn từ production-like workload.

## 22. Join order, FROM collapse và GEQO: đừng ép theo trực giác

Với một query có nhiều joins, PostgreSQL phải quyết định:

- Thứ tự join;
- Join method của từng cặp;
- Index scan/Seq Scan cho từng base relation;
- Nơi đặt filter và aggregate;
- Khi nào cần materialize/sort/hash.

Các cấu hình như `join_collapse_limit` và `from_collapse_limit` ảnh hưởng không gian tìm kiếm kế hoạch. Trên truy vấn rất nhiều relations, planner còn có thể dùng `GEQO (Genetic Query Optimizer)` theo ngưỡng phù hợp.

### 22.1. SQL viết thứ tự FROM không phải luôn thứ tự thực thi

~~~sql
SELECT ...
FROM a
JOIN b ON ...
JOIN c ON ...
WHERE ...;
~~~

Với inner joins có tính hoán đổi phù hợp, planner được phép sắp xếp lại. **Không nên “sửa” bằng cách đổi thứ tự JOIN trong SQL rồi mặc định executor sẽ chạy theo thứ tự đó.**

### 22.2. Thí nghiệm join_collapse_limit

~~~sql
BEGIN;
SET LOCAL join_collapse_limit = 1;

EXPLAIN
SELECT ...
FROM ...
JOIN ... ON ...;

ROLLBACK;
~~~

Đây là **cú pháp minh họa cho query thật của bạn**, không phải một câu SQL hoàn chỉnh để chạy nguyên xi. Giảm `join_collapse_limit` có thể hạn chế planner reorder explicit JOINs, nhưng không thay ràng buộc ngữ nghĩa của outer joins và không giải quyết estimate sai.

### 22.3. Vì sao không nên đóng đinh join order vội?

Một join order tốt với bảng A nhỏ hôm nay có thể rất tệ sau khi A tăng 100 lần hoặc một tenant có phân bố dữ liệu khác. Nếu gốc là **thiếu index, thiếu stats hay join predicate viết sai**, ép order có thể che giấu vấn đề trong thời gian ngắn.

## 23. Hints, plan pinning và rủi ro phụ thuộc extension

PostgreSQL core **không dùng bộ cú pháp query hints kiểu `/*+ INDEX(...) */`** làm cơ chế ép plan mặc định giống một số hệ quản trị khác. Có extension bên ngoài như **pg_hint_plan** trong những môi trường hỗ trợ, nhưng:

- Không mặc định được cài hoặc hoạt động trên managed service;
- Có yêu cầu version/configuration riêng;
- Hints có thể phụ thuộc tên bảng/index và query shape;
- Dễ stale khi schema, version, stats, dữ liệu thay đổi;
- Có thể giảm tính linh hoạt của planner;
- Một hint không sửa cardinality/semantics sai;
- Không nên coi hints là lớp thay thế cho quan trắc và regression testing.

### 23.1. Khi nào có thể cân nhắc hint/plan control?

Một số môi trường đặc thù có thể cần một workaround tạm thời khi:

1. Đã đo truy vấn/plan cụ thể;
2. Đã xác định lỗi planner hoặc regression có bằng chứng;
3. Đã thử stats/index/query rewrite hợp lý;
4. Có deadline sự cố và cần mitigations trong thời gian chờ sửa gốc;
5. Có phạm vi ảnh hưởng và **kế hoạch gỡ bỏ** hint;
6. Có kiểm thử nhiều giá trị tham số và dữ liệu tăng trưởng.

Nhưng đây là **ngoại lệ có kiểm soát**, không phải bước đầu tiên mỗi khi nhìn thấy một Seq Scan.

### 23.2. Từ workaround tới nợ kỹ thuật

~~~text
Ngày 1: ép Index Scan cho query tenant nhỏ → nhanh.
Ngày 60: tenant trở thành tenant lớn → Index Scan random heap I/O.
Ngày 120: đổi index/schema → hint không còn tác dụng
          hoặc ép kế hoạch rất chậm.
~~~

Một workaround thiếu owner, ngày hết hạn và điều kiện kiểm chứng có thể trở thành **nợ vận hành** nguy hiểm hơn chính plan ban đầu.

### 23.3. Không nhầm plan pinning với kiểm soát kết quả

Một kế hoạch truy vấn chỉ là **cách** trả kết quả SQL. Nó không bảo đảm dữ liệu đúng nếu SQL thiếu `JOIN ON`, điều kiện NULL sai, timezone không được xác định hoặc transaction isolation không đáp ứng nghiệp vụ. **Đúng nghĩa SQL luôn là yêu cầu trước khi tối ưu tốc độ.**

## 24. Quan sát ở production: tìm query có tác động thật

Trước khi chỉnh một cấu hình planner, cần xác định query đang gây tốn tài nguyên **trên toàn workload**, không chỉ query bạn tình cờ thấy chậm trong một lần chạy.

### 24.1. pg_stat_statements

Extension `pg_stat_statements` có thể tập hợp thống kê cho các query theo dạng đã chuẩn hóa, khi đã được administrator cài/cấu hình đúng. Đây không phải extension mặc định luôn có ở mọi cluster/managed service.

Nếu môi trường **đã có extension và quyền phù hợp**, một truy vấn đọc:

~~~sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    stddev_exec_time,
    rows
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

Nó giúp tìm:

- Query tốn **tổng thời gian** nhiều nhất;
- Query có **mean execution time** cao;
- Query có độ biến thiên đáng chú ý;
- Query chạy cực nhiều lần dù mỗi lần tương đối nhanh;
- Mối quan hệ giữa số lần thực thi và số rows.

**Cẩn thận:** một normalized statement có thể đại diện cả `tenant_id=1` và `tenant_id=500`; thời gian trung bình có thể che đuôi phân phối. Cần thu thập bind parameters một cách an toàn và hợp pháp khi điều tra skew.

### 24.2. Không chỉ nhìn mean

~~~text
Query A:
  99% lần chạy: 5 ms
   1% lần chạy: 9.000 ms

Query B:
  100% lần chạy: 70 ms
~~~

Nếu chỉ nhìn mean, bạn có thể bỏ qua đuôi độ trễ của A hoặc đánh giá sai mức ưu tiên. Hệ thống A có thể gây timeout/p99 regression nghiêm trọng dù phần lớn request tốt.

`pg_stat_statements` không lưu đầy đủ mọi latency percentile/bind-value distribution cho tất cả trường hợp. Kết hợp **application tracing**, logs và monitoring khi cần.

### 24.3. auto_explain cho slow plans

Module `auto_explain` của PostgreSQL có thể ghi lại plan của những truy vấn vượt ngưỡng khi được cấu hình thích hợp. Nó đặc biệt hữu ích khi plan chỉ chậm trong application context mà không tái hiện dễ dàng bằng `psql`.

Những lưu ý:

- Có thể yêu cầu cấu hình preload/permission và phụ thuộc môi trường quản trị.
- `auto_explain.log_analyze=on` đo runtime chi tiết và **có overhead**.
- Cần sampling/threshold và chính sách log để tránh log quá nhiều, lộ tham số nhạy cảm hoặc giảm hiệu năng.
- Log plan là bằng chứng tại thời điểm thực thi; vẫn phải xem query inputs và wait context.

Không tự bật logging chi tiết cho toàn bộ traffic production mà chưa đánh giá chi phí/riêng tư.

### 24.4. log_min_duration_statement

Khi được DBA cấu hình hợp lý, `log_min_duration_statement` giúp ghi các statements vượt ngưỡng. Nhưng log SQL thô có thể chứa dữ liệu nhạy cảm; cần tuân thủ chính sách bảo mật, retention và quyền truy cập log.

**Log độ trễ không tự cho biết query chậm vì CPU, I/O hay lock**. Hãy kết hợp với `pg_stat_activity`, `EXPLAIN ANALYZE` hoặc những metric phù hợp.

### 24.5. Chú ý queryid và cấu trúc schema

Một query ID giúp nhóm những statements có cấu trúc giống nhau, nhưng không phải mã nghiệp vụ bất biến qua mọi phiên bản, cấu hình, schema hay môi trường. Khi so regression giữa releases, lưu thêm SQL fingerprint, migration version và query source.

## 25. Đo đúng: benchmark một thay đổi planner thế nào?

### 25.1. Kiểm soát biến độc lập

Thử nghiệm tốt:

~~~text
Baseline A:
  cùng SQL
  cùng tham số
  cùng dữ liệu
  cùng vai trò/schema
  đo nhiều lượt

Thử nghiệm B:
  thay đúng một yếu tố
  (ANALYZE, index, query rewrite hoặc SET LOCAL...)
  đo lại với những điều kiện tương đồng
~~~

Nếu vừa tạo index, vừa tăng work_mem, vừa thay random_page_cost rồi query nhanh, bạn không biết yếu tố nào thực sự giúp.

### 25.2. Bảo đảm kết quả SQL tương đương

Một rewrite từ `LEFT JOIN` thành `INNER JOIN` có thể chạy nhanh hơn vì loại mất hàng. Một `LIMIT` thêm vào có thể giảm dữ liệu trả về nhưng thay hợp đồng API. **Nhanh hơn mà sai kết quả không phải tối ưu hợp lệ.**

### 25.3. Lưu cả baseline và phương án mới

| Trường cần ghi | Baseline | Thử nghiệm |
| --- | --- | --- |
| SQL/query ID | Bản đang chạy | Tương đương nghiệp vụ |
| Bind parameters/types | Ghi rõ | Giữ nguyên |
| PostgreSQL version | Ghi rõ | Giữ nguyên |
| Dataset/stats | Ghi rõ | Ghi thay đổi |
| Planner GUCs | Mặc định hiện tại | Chỉ thay yếu tố thử |
| Plan root & join order | Đo | Đo |
| Estimated rows vs actual | Đo | Đo |
| Execution Time | Đo nhiều lượt | Đo nhiều lượt |
| Buffers hit/read | Đo | Đo |
| Temp I/O | Đo | Đo |
| Workers Launched | Đo nếu có | Đo nếu có |
| Lock wait/IO load | Quan sát | Quan sát |
| Kết quả/row count | Xác minh | Phải tương đương |
| Ảnh hưởng throughput | Đo ở tải đại diện | Đo ở tải đại diện |

### 25.4. Không lấy một lượt chạy duy nhất

Thời gian có thể biến động bởi:

- Shared buffers/OS cache nóng-lạnh;
- Vacuum/checkpoint/backup đang hoạt động;
- Worker availability;
- Network và client fetch;
- CPU contention;
- Storage burst credits hoặc I/O throttling;
- JIT compilation;
- Số hàng và tham số.

Chạy nhiều lượt, thay đổi thứ tự A/B hợp lý, báo cáo trung vị, p95/p99 khi phù hợp và diễn giải độ biến thiên.

### 25.5. Thử trên dữ liệu giống production

Một query dùng Index Scan trên bảng 400.000 hàng có thể dùng Seq Scan trên bảng 40 triệu hàng; phân bố tenant và correlation cũng có thể khác. Benchmark lab giúp học cơ chế, không thay load test trên dữ liệu đại diện.

### 25.6. SET LOCAL để cô lập các phép thử

~~~sql
BEGIN;

SET LOCAL enable_nestloop = off;
SET LOCAL work_mem = '32MB';

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT
    c.region,
    COUNT(*)
FROM plan_lab_291.orders AS o
JOIN plan_lab_291.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.tenant_id = 1
GROUP BY c.region;

ROLLBACK;
~~~

`ROLLBACK` kết thúc transaction và hủy những `SET LOCAL` của transaction; vì query lab là `SELECT` nên không có thay đổi dữ liệu nghiệp vụ để hoàn tác. Trên production, ngay cả query SELECT nặng vẫn có thể gây I/O/CPU đáng kể, nên chỉ benchmark trong phạm vi được phép.

### 25.7. EXPLAIN ANALYZE với DML

Không chạy trực tiếp:

~~~sql
-- CẢNH BÁO: câu dưới thật sự UPDATE nếu được chạy.
-- EXPLAIN (ANALYZE, BUFFERS)
-- UPDATE plan_lab_291.orders
-- SET status='paid'
-- WHERE tenant_id=1;
~~~

Nếu cần đo DML thật trong lab, hãy dùng transaction và rollback có kiểm soát, đồng thời hiểu rằng sequence, external side effects, lock behavior và công việc ghi thực tế có thể không hoàn toàn được “đảo ngược” theo kỳ vọng. **Không coi ROLLBACK là giấy phép thử mọi DML trên production.**

## 26. Ưu tiên sửa nguyên nhân theo mức rủi ro

Thay vì một danh sách “những tham số nên chỉnh”, hãy phân loại biện pháp:

| Dấu hiệu | Thử chẩn đoán | Hướng sửa gốc thường hợp lý | Rủi ro nếu ép plan vội |
| --- | --- | --- | --- |
| `estimated rows` sai nhiều | So `actual`, đọc `pg_stats` | ANALYZE/extended stats/statistics target | Join method bị ép với cardinality sai |
| Query có function/cast trên cột indexed | Xem `Index Cond` vs `Filter` | Rewrite sargable/expression index hợp lệ | Index không thể áp đúng điều kiện |
| Tenant lớn và nhỏ khác nhau | So custom/generic plans | Stats, index, phân nhánh logic hoặc custom plan có chọn lọc | Plan tốt cho tenant nhỏ gây thảm họa tenant lớn |
| Seq Scan trên 80% bảng | So buffer/IO Index Scan | Có thể giữ Seq Scan | Random heap reads lớn |
| Nested Loop lặp 200.000 lần | Xem estimate outer, loops inner | Sửa estimate/index/join logic | Hash Join bị ép có thể spill |
| Sort external merge | Đọc Disk/temp buffers | Query/index/limit/work_mem có giới hạn | Tắt Sort không đáp ứng ORDER BY |
| Hash Batches cao | Đọc memory/temp | Tối ưu join/rows/work_mem | Tắt hash join chỉ chuyển nút nghẽn |
| Planned 4, Launched 0 | Xem limits/concurrency | Điều phối workers/công việc | Tăng per-gather không cấp thêm CPU |
| WaitEvent=Lock | Xem blocking PIDs | Transaction/lock strategy | Thay plan không bỏ lock wait |
| Query nhanh ở DB, API chậm | Đo connection/network/fetch | Sửa application path | Cấu hình planner sai mục tiêu |
| Truy vấn tuần tự rất nhanh | Đo latency/throughput | Có thể không cần sửa | Overhead parallel workers |
| Index Only Scan có nhiều Heap Fetches | Xem VACUUM/visibility map | Bảo trì MVCC, giảm cập nhật không cần thiết | Ép index-only không loại heap access |
| Partitions không prune | Xem partition keys/predicate | Rewrite range/predicate/stats | Mỗi partition vẫn quét thừa |

### 26.1. Thứ tự ưu tiên đề xuất

1. **Kết quả đúng/semantics rõ**.
2. **Định danh query và bind parameters chính xác**.
3. **Đo estimated vs actual, wait và I/O**.
4. **Sửa SQL/schema/stats/index** theo bằng chứng.
5. **Đo lại trên nhiều workload**.
6. **Chỉ cân nhắc planner GUCs/hints** khi vẫn còn vấn đề được chứng minh và có phạm vi/rollback.

Không nhất thiết mọi lỗi đều được giải bằng `ANALYZE`: nếu query đang chờ lock, stats mới không giải quyết gì; nếu query lọc cột không index với selectivity cao, bổ sung index có thể cần thiết.

## 27. Các tình huống điển hình và suy luận nguyên nhân gốc

### Tình huống A — PostgreSQL chọn Seq Scan dù đã có index

~~~text
Seq Scan on orders
  Filter: tenant_id = 1
  actual rows: 320000
~~~

Trong lab, tenant 1 chiếm 80%. Đây có thể là **lựa chọn đúng**, không cần sửa. Hãy xem size, shared read/hit, số hàng cần trả và so với một Index Scan trong **thí nghiệm cô lập**.

### Tình huống B — Seq Scan trên tenant nhỏ

~~~text
Seq Scan on orders
  Filter: tenant_id = 500
  actual rows: ~800
~~~

Nếu thiếu index và query chạy thường xuyên, xem index `tenant_id` hoặc composite index cho query cụ thể. Nếu index đã có nhưng planner vẫn Seq Scan, xem estimated rows, random page cost/cache, selectivity và data stats.

### Tình huống C — Nested Loop ước lượng 1, thực tế 100.000

~~~text
Nested Loop
  -> ... (estimated rows=1, actual rows=100000)
  -> Index Scan ... (loops=100000)
~~~

Điều tra node sinh outer rows; stats đa cột/parameterization/join condition có thể quan trọng hơn công tắc `enable_nestloop`.

### Tình huống D — Cùng SQL nhanh/chậm theo tenant

~~~text
tenant_id=1   → 320000 rows
tenant_id=500 → ~800 rows
~~~

Nếu ứng dụng dùng prepared statement chung, kiểm tra **generic/custom plan**. Đừng chọn một plan “chuẩn” dựa trên tenant nhỏ rồi áp cho tenant rất lớn.

### Tình huống E — EXPLAIN cho thấy rows đúng nhưng vẫn chậm

Nếu `estimated rows≈actual rows`, tìm:

- `shared read` và I/O wait;
- Sort/Hash temp spill;
- Worker availability;
- CPU/JIT overhead;
- Client fetch/network;
- Lock wait;
- Những function tốn CPU trong Filter/Output.

**Cardinality đúng không đồng nghĩa planner cost model hoàn hảo**, nhưng nó giúp thu hẹp phạm vi tìm nguyên nhân.

### Tình huống F — Query chậm sau thêm index mới

Index mới có thể khiến planner chuyển từ Seq Scan sang Index Scan với random heap reads tệ hơn nếu dữ liệu/chi phí không giống ước tính. Kiểm tra:

- Stats sau migration;
- Độ chọn lọc thực tế;
- `Heap Fetches`, `Buffers`, table correlation;
- Query parameters lớn/nhỏ;
- Các plan trước/sau;
- Tác động ghi/WAL và index maintenance.

Đừng coi “nhiều index hơn” luôn là tối ưu.

### Tình huống G — Query nhanh sau SET enable_hashjoin=off

Kết quả này gợi ý đường Merge/Nested Loop thay thế có thể tốt hơn trong test. Tiếp tục tìm:

- Hash input thực/ước lượng;
- Batches, Memory Usage, temp I/O;
- Keys và predicate có bị pushdown phù hợp không;
- Workload tham số khác nhau;
- Query join nhiều hàng bất thường?

Nếu chỉ để lại `enable_hashjoin=off` cho toàn application, có thể làm chậm hàng trăm truy vấn khác.

### Tình huống H — Query chậm sau nâng cấp PostgreSQL

Một major upgrade có thể thay planner features, cost assumptions, statistics, collation hoặc cấu trúc hệ thống. Quy trình hợp lý:

1. Thu plan trước/sau nếu có;
2. Thu `ANALYZE`/stats sau nâng cấp theo hướng dẫn;
3. Kiểm tra index/collation validity khi liên quan;
4. So query parameters và workload;
5. Xác định regression cụ thể;
6. Thử rewrite/index/settings **có giới hạn**;
7. Có phương án rollback/fix-forward theo quy trình upgrade.

Không tắt hàng loạt planner features mới chỉ vì một query regression.

## 28. Những ngộ nhận phổ biến

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| `Seq Scan` luôn chậm | Hợp lý khi cần đọc phần lớn bảng hoặc bảng nhỏ |
| Có index là planner bắt buộc dùng | Planner chọn theo cost ước lượng |
| `enable_seqscan=off` chắc chắn loại bỏ Seq Scan | Chủ yếu làm node đó kém hấp dẫn, không luôn loại bỏ hoàn toàn |
| `enable_nestloop=off` sửa mọi join chậm | Không sửa sai estimated rows hay query semantics |
| `cost=10000` nghĩa 10 giây | Cost là đơn vị tương đối, không phải ms |
| Estimated rows bằng 1 là “planner đã đếm dữ liệu” | Là số ước lượng dựa trên stats/cost logic |
| `actual rows` luôn là tổng hàng global | Cần xét `loops` và vị trí node |
| Một plan nhanh trong psql sẽ nhanh với ORM | Bind parameters, generic plan, client fetch và load có thể khác |
| `ANALYZE` bảo đảm estimate hoàn hảo | Nó thu mẫu; skew/correlation vẫn có thể khó |
| `pg_stats.correlation` đo phụ thuộc tenant/status | Nó đo tương quan giá trị với thứ tự vật lý |
| Extended stats sửa mọi join estimates | Có giới hạn, nhất là tương quan qua nhiều bảng |
| Nested Loop lặp nhiều lần chắc chắn sai | Tốt nếu outer nhỏ/inner index lookup nhanh |
| Hash Join không bao giờ spill | Có thể dùng nhiều batches/temp files |
| Tăng `work_mem` là cách chữa mọi Sort | Có thể gây quá tải RAM khi concurrent queries |
| `effective_cache_size` cấp thêm cache | Chỉ là thông tin để planner costing |
| `shared read` luôn là đĩa vật lý | Có thể được phục vụ từ OS cache |
| Query chậm 20s vì plan, nên đổi index | Có thể chờ lock 19s |
| Parallel workers planned là đã launch | Runtime có thể launch ít hơn |
| Có Gather là query được phân tán sang replicas | Parallel query chạy trong một instance |
| `EXPLAIN ANALYZE` chỉ xem không thực thi | Nó thực thi SQL, kể cả DML |
| Generic plan luôn xấu | Có thể tiết kiệm planning và tốt với tham số ổn định |
| Force custom luôn tốt | Planning overhead lớn nếu truy vấn chạy hàng triệu lần |
| Partial index luôn được dùng nếu có tên predicate giống nhau | Planner phải chứng minh predicate phù hợp; generic parameters có thể cản |
| `UNION ALL` là rewrite OR miễn phí | Có thể gây duplicate và thay kết quả |
| `ORDER BY` không cần tie-break vì index ổn định | Pagination có khóa bằng nhau cần thứ tự đủ |
| Chỉ cần benchmark một lần sau đổi config | Cache/load/worker availability làm kết quả biến động |
| `pg_stat_statements` mean đại diện mọi tenants | Phân bố skew/p99 có thể bị che |
| Hint tốt hôm nay sẽ tốt vĩnh viễn | Dữ liệu/schema/stats đổi, plan pinning có thể stale |
| Tuning xong không cần rollback plan | Mọi thay đổi production cần phương án quay lại |

## 29. Bài tập thực hành

Các bài tập dùng `plan_lab_291` và dữ liệu 400.000 hàng. Không đòi phải nhìn thấy đúng một node; phần trọng tâm là **phương pháp suy luận** và giải thích bằng số liệu. Nếu hạn chế tài nguyên, giảm số hàng và ghi nhận ảnh hưởng tới planner.

### Bài 1 — Tại sao không ép Seq Scan?

Với một truy vấn lọc 80% bảng, giải thích vì sao Seq Scan có thể rẻ hơn Index Scan. Liệt kê các yếu tố page reads, random heap accesses và CPU.

### Bài 2 — Tìm tenant lớn

~~~sql
SELECT COUNT(*)
FROM plan_lab_291.orders
WHERE tenant_id = 1;
~~~

**Kỳ vọng logic:** 320.000. Chạy `EXPLAIN` và giải thích plan được chọn mà không gọi nó sai chỉ vì tên node.

### Bài 3 — Tìm tenant nhỏ

~~~sql
SELECT COUNT(*)
FROM plan_lab_291.orders
WHERE tenant_id = 500;
~~~

**Kỳ vọng:** 800 hàng theo công thức dữ liệu. So sánh plan trước/sau index trên `tenant_id`.

### Bài 4 — Đọc cost so với actual

Cho:

~~~text
cost=0.00..20000.00 rows=1000
actual time=0.1..150.0 rows=200000 loops=1
~~~

**Câu hỏi:** tham số nào cho biết sai lệch cardinality? Vì sao không thể nói planner dự đoán 20 giây?

### Bài 5 — Lỗi nhân loops

Một Nested Loop có inner Index Scan `actual rows=1 loops=250000`.

**Câu hỏi:** bao nhiêu lần inner node chạy? Nếu thời gian mỗi lượt nhỏ, vì sao tổng thời gian vẫn có thể lớn?

### Bài 6 — Phân biệt Index Cond/Filter

So `WHERE ordered_at::date = DATE '2026-05-01'` với half-open range trên `ordered_at`.

**Câu hỏi:** cấu trúc nào phù hợp với B-tree trên cột `ordered_at` và giữ được timezone semantics?

### Bài 7 — Dữ liệu tương quan hai cột

Trên lab, giải thích tại sao:

~~~sql
WHERE tenant_id = 1 AND status = 'pending'
~~~

trả 0 hàng dù từng điều kiện riêng có nhiều hàng.

### Bài 8 — Ước lượng độc lập sai

Với `P(tenant=1)=0.8` và `P(pending)=0.2`, giả định độc lập cho kết quả bao nhiêu hàng trong 400.000?

**Đáp án minh họa:** 64.000. Vì sao thực tế là 0?

### Bài 9 — Extended statistics

Tạo `CREATE STATISTICS ... (dependencies, mcv, ndistinct)` trên `(tenant_id,status)` rồi `ANALYZE`.

**Câu hỏi:** estimated rows của query kết hợp thay đổi thế nào? Có còn đúng bằng một con số cố định không?

### Bài 10 — pg_stats

Chạy `pg_stats` cho tenant_id và đọc `most_common_vals`, `most_common_freqs`, `n_distinct`.

**Câu hỏi:** tenant 1 có được nhận là MCV không? Vì sao histogram không thay toàn bộ thông tin MCV?

### Bài 11 — Correlation khác dependencies

Giải thích sự khác nhau giữa `pg_stats.correlation` và extended stats `dependencies`. Loại nào mô tả quan hệ giữa tenant_id và status?

### Bài 12 — Statistics target

Đặt riêng `tenant_id SET STATISTICS 500`, chạy `ANALYZE` và so query plan/stats.

**Câu hỏi:** tăng target có làm SQL chạy nhanh hơn trong mọi trường hợp không? Chi phí bổ sung là gì?

### Bài 13 — Custom vs generic plan

Chuẩn bị `PREPARE get_orders_by_tenant(integer)`, so `force_custom_plan` và `force_generic_plan` cho tham số 1/500.

**Bài tập:** ghi estimated/actual rows, plan node và execution time; vì sao generic plan có thể yếu với skew?

### Bài 14 — Planning overhead

Một query chạy 10 triệu lần/ngày, execution 1ms nhưng custom planning mất thêm 1ms/lần.

**Câu hỏi:** nếu dùng force_custom toàn ứng dụng, planning CPU có thể tăng thế nào? Cần cân nhắc tổng thời gian và workload nào?

### Bài 15 — Index composite

Viết index cho:

~~~sql
WHERE tenant_id = 500 AND status = 'pending'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20
~~~

**Đáp án gợi ý:** khóa `(tenant_id,status,ordered_at DESC,order_id DESC)`.

### Bài 16 — Partial index với generic plan

Vì sao partial index `WHERE status='paid'` có thể không được dùng trong generic plan có `status=$1`? Đề xuất cách kiểm tra riêng.

### Bài 17 — UNIQUE không phải hint

Một query join qua `customers.customer_id PRIMARY KEY`. Vì sao constraint này vừa bảo vệ dữ liệu vừa giúp planner có thông tin về tính duy nhất?

### Bài 18 — Sort external merge

Trong `EXPLAIN ANALYZE` có:

~~~text
Sort Method: external merge Disk: 600MB
~~~

**Câu hỏi:** tối thiểu ba hướng điều tra khác nhau trước khi tăng `work_mem`? Tại sao work_mem có thể nhân lên theo operations/workers?

### Bài 19 — Hash Batches

Một Hash Join có `Batches: 32` và temp read/write cao. Phân biệt khả năng **input lớn hơn ước lượng** với **work_mem không đủ**, rồi đề xuất thí nghiệm.

### Bài 20 — No Workers Launched

Planner dự kiến 4 parallel workers nhưng thực tế launch 0. Kiểm tra giới hạn nào, và vì sao `SET max_parallel_workers_per_gather=8` không giải quyết global worker starvation?

### Bài 21 — Lock wait

Một `UPDATE` bị chặn 30 giây. Viết query `pg_stat_activity` với `pg_blocking_pids` để tìm blocker.

**Câu hỏi:** lúc nào cần sửa transaction scope thay vì index/plan?

### Bài 22 — Cache nóng và cache lạnh

Một query có cùng plan chạy lần 1 500ms, lần 2 35ms. `shared read` giảm và `shared hit` tăng.

**Câu hỏi:** có đủ bằng chứng planner đã tối ưu khác nhau chưa?

**Đáp án:** không; rất có thể khác trạng thái cache.

### Bài 23 — JIT

So `EXPLAIN ANALYZE` có JIT và một lượt `SET LOCAL jit=off` nếu server hỗ trợ.

**Câu hỏi:** có trường hợp JIT compilation overhead vượt lợi ích không? Vì sao không nên tắt global chỉ vì query ngắn?

### Bài 24 — Partition pruning

Một plan Append quét 12 partitions dù query chỉ cần một tháng. Viết lại predicate theo range của partition key và giải thích tại sao nó có thể giúp pruning.

### Bài 25 — Nested Loop đúng

Query chọn `order_id=12345` rồi join sang customer theo PK. Vì sao Nested Loop thường là lựa chọn hợp lý? Khi nào outer lớn khiến nó tốn kém?

### Bài 26 — enable_nestloop=off

Thử `SET LOCAL enable_nestloop=off` trong transaction cho một query join lab.

**Câu hỏi:** nếu Hash Join nhanh hơn trong lượt này, bạn đã chứng minh điều gì và **chưa** chứng minh điều gì?

### Bài 27 — enable_seqscan=off

Thử tắt Seq Scan cục bộ cho query tenant 1 và tenant 500.

**Câu hỏi:** một cấu hình có thể giúp tenant nào, làm chậm tenant nào? Vì sao không nên đặt toàn server?

### Bài 28 — Index-only và visibility

Một `Index Only Scan` có `Heap Fetches` cao. Những yếu tố gì về visibility map, VACUUM và cập nhật hàng có thể liên quan?

### Bài 29 — Thay effective_cache_size

Giải thích vì sao:

~~~sql
SET effective_cache_size = '32GB';
~~~

không thực sự cấp thêm 32GB RAM cho PostgreSQL. Nó ảnh hưởng ước lượng planner như thế nào?

### Bài 30 — Rewriting OR bằng UNION ALL

Với predicate `tenant_id=1 OR customer_id=42`, hãy chứng minh có hàng có thể thỏa cả hai. Vì sao rewrite thành `UNION ALL` có thể làm số hàng tăng?

### Bài 31 — Auto_explain và quan sát production

Nếu query chỉ chậm trong ứng dụng nhưng `psql` chạy nhanh, những bằng chứng nào nên thu thập? Nêu ít nhất SQL fingerprint, bind types, generic/custom plan, application trace, wait events và log plan có sampling.

### Bài 32 — pg_stat_statements và parameter skew

Một normalized query có mean 50ms nhưng p99 endpoint 6s.

**Câu hỏi:** tại sao mean không đủ? Bạn sẽ phân nhóm theo tenant/status/rowcount như thế nào mà vẫn tuân thủ bảo mật?

### Bài 33 — Thử nghiệm trước/sau không công bằng

Nhóm A đổi `random_page_cost` sau khi chạy truy vấn lần đầu làm cache nóng rồi báo “tối ưu 10 lần”.

**Bài tập:** chỉ ra những biến gây nhiễu và thiết kế A/B benchmark nhiều lượt có log buffers.

### Bài 34 — Khi nào cân nhắc hint?

Nêu các điều kiện tối thiểu: đã xác định root cause, có bằng chứng regression, thử stats/index/rewrite, scope giới hạn, rollback, tests nhiều tham số, owner và ngày xem xét lại.

### Bài 35 — Một query, nhiều giá trị tham số

Thiết kế bảng kiểm thử tối thiểu cho tenant 1, 500 và một tenant không tồn tại:

| Case | Row count dự kiến | Custom plan | Generic plan | Latency/buffers |
| --- | ---: | --- | --- | --- |
| Tenant 1 | 320.000 | Đo | Đo | Đo |
| Tenant 500 | 800 | Đo | Đo | Đo |
| Tenant 999 | 0 | Đo | Đo | Đo |

**Bài tập:** giải thích tại sao tối ưu chỉ theo tenant lớn hoặc chỉ theo tenant nhỏ là chưa đủ.

### Bài 36 — Plan nhanh nhưng query sai

Một developer thay `LEFT JOIN` thành `INNER JOIN` để bỏ `Sort` và giảm số hàng output; query chạy nhanh hơn 70%.

**Câu hỏi:** nếu business cần cả các khách hàng không có đơn, tại sao đây **không** phải một tối ưu hợp lệ? Làm thế nào kiểm tra sự tương đương về semantics trước khi benchmark?

### Bài 37 — API chậm nhưng SQL nhanh

Endpoint trả 100.000 đơn hàng mất 12 giây; `EXPLAIN ANALYZE` của query mất 150ms.

**Bài tập:** đề xuất kiểm tra connection pool, pagination, network, JSON serialization, ORM object mapping, client fetch và N+1 queries trước khi chỉnh planner.

### Bài 38 — Tạo index mà không dựa vào query

Một team tạo B-tree index riêng trên mọi cột của `orders`.

**Câu hỏi:** vì sao cách này có thể làm `INSERT`/`UPDATE` chậm hơn mà không giúp query chính? So sánh index đơn lẻ với composite theo `WHERE + ORDER BY + LIMIT` thực tế.

### Bài 39 — Tình huống regression sau migration

Một release đổi kiểu bind `customer_id` từ integer thành text và query bắt đầu xuất hiện `customer_id::text` ở vế trái.

**Bài tập:** tìm nguyên nhân vì sao index INTEGER không còn được dùng theo kỳ vọng; đề xuất sửa mapping JDBC/ORM và kiểm tra plan mới.

### Bài 40 — Viết biên bản tối ưu

Viết một đoạn báo cáo gồm:

1. SQL fingerprint và tham số tái hiện;
2. Baseline p50/p95, buffers, plan;
3. Chênh lệch estimated/actual rows và node đầu tiên sai;
4. Giả thuyết nguyên nhân;
5. Thí nghiệm có `SET LOCAL` hoặc query rewrite;
6. Bằng chứng xác nhận/phủ định;
7. Giải pháp gốc;
8. Các tham số khác đã benchmark;
9. Rủi ro/rollback/giám sát sau triển khai.

**Mục tiêu:** quyết định tối ưu có thể được đồng nghiệp kiểm tra và người vận hành khôi phục, không phải kết luận “đã tắt Seq Scan nên nhanh”.

## 30. Bộ truy vấn chẩn đoán có thể dùng lại

Những câu dưới đây tập trung **đọc thông tin**. Chúng không tự tạo index, đổi server config hay hủy backend. Hãy dùng đúng quyền và tránh chạy các câu `EXPLAIN ANALYZE` nặng trong thời điểm hệ thống đang sự cố nếu nó làm tăng tải.

### 30.1. Xem planner configuration đang có

~~~sql
SELECT
    name,
    setting,
    unit,
    source,
    context
FROM pg_catalog.pg_settings
WHERE name IN (
    'enable_seqscan',
    'enable_nestloop',
    'enable_hashjoin',
    'enable_mergejoin',
    'random_page_cost',
    'seq_page_cost',
    'effective_cache_size',
    'work_mem',
    'max_parallel_workers_per_gather',
    'plan_cache_mode',
    'jit'
)
ORDER BY name;
~~~

Nếu thấy `source='session'` hoặc nguồn cấu hình khác dự kiến, trước tiên xem **có thử nghiệm cũ hoặc connection pool làm rò trạng thái không**.

### 30.2. Xem tình trạng ANALYZE của bảng

~~~sql
SELECT
    relid::regclass AS relation_name,
    n_live_tup,
    last_analyze,
    last_autoanalyze,
    analyze_count,
    autoanalyze_count
FROM pg_catalog.pg_stat_all_tables
WHERE relid = 'plan_lab_291.orders'::regclass;
~~~

### 30.3. Xem MCV/histogram một cột

~~~sql
SELECT
    attname,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    histogram_bounds
FROM pg_catalog.pg_stats
WHERE schemaname = 'plan_lab_291'
  AND tablename = 'orders'
  AND attname IN ('tenant_id', 'status')
ORDER BY attname;
~~~

### 30.4. Xem extended statistics đang tồn tại

~~~sql
SELECT
    statistics_name,
    attnames,
    kinds,
    dependencies,
    most_common_vals
FROM pg_catalog.pg_stats_ext
WHERE schemaname = 'plan_lab_291'
  AND tablename = 'orders';
~~~

### 30.5. Xem index definitions

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_catalog.pg_indexes
WHERE schemaname = 'plan_lab_291'
  AND tablename = 'orders'
ORDER BY indexname;
~~~

### 30.6. Xem số lần sử dụng index

~~~sql
SELECT
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_catalog.pg_stat_user_indexes
WHERE schemaname = 'plan_lab_291'
  AND relname = 'orders'
ORDER BY idx_scan DESC, indexrelname;
~~~

### 30.7. Xem session nào đang chờ khóa

~~~sql
SELECT
    pid,
    datname,
    state,
    wait_event_type,
    wait_event,
    pg_catalog.pg_blocking_pids(pid) AS blockers,
    now() - query_start AS query_age
FROM pg_catalog.pg_stat_activity
WHERE wait_event_type = 'Lock'
ORDER BY query_start;
~~~

### 30.8. Xem prepared statements trong session hiện tại

~~~sql
SELECT
    name,
    parameter_types,
    generic_plans,
    custom_plans
FROM pg_catalog.pg_prepared_statements
ORDER BY name;
~~~

### 30.9. Xem kích thước bảng và indexes

~~~sql
SELECT
    'plan_lab_291.orders'::regclass AS relation_name,
    pg_catalog.pg_size_pretty(
        pg_catalog.pg_relation_size(
            'plan_lab_291.orders'::regclass
        )
    ) AS table_heap_size,
    pg_catalog.pg_size_pretty(
        pg_catalog.pg_indexes_size(
            'plan_lab_291.orders'::regclass
        )
    ) AS indexes_size,
    pg_catalog.pg_size_pretty(
        pg_catalog.pg_total_relation_size(
            'plan_lab_291.orders'::regclass
        )
    ) AS total_size;
~~~

### 30.10. Xem kết quả đúng và số hàng của từng tham số

~~~sql
SELECT
    tenant_id,
    COUNT(*) AS rows_for_tenant,
    COUNT(*) FILTER (WHERE status = 'paid')
        AS paid_rows,
    COUNT(*) FILTER (WHERE status = 'pending')
        AS pending_rows
FROM plan_lab_291.orders
WHERE tenant_id IN (1, 500)
GROUP BY tenant_id
ORDER BY tenant_id;
~~~

Nếu `EXPLAIN` cho hai tenants có estimated rows giống nhau nhưng thực tế chênh rất lớn, đây là manh mối để xem **generic plan, skew, statistics và selective paths**.

## 31. Runbook xử lý query regression trong production

### Giai đoạn A — Ghi nhận sự cố

Thu thập:

- Truy vấn hoặc query ID và phiên bản ứng dụng/ORM;
- Database, PostgreSQL version, role và môi trường;
- Tham số ảnh hưởng, kiểu bind và tần suất;
- Mốc thời gian bắt đầu chậm;
- Latency ở ứng dụng so với database;
- CPU, RAM, I/O, lock waits, hoạt động VACUUM/checkpoint;
- Có migration/index change/ANALYZE/config/upgrade gần đó không?

**Đừng thực hiện ngay `ALTER SYSTEM SET enable_seqscan=off`.** Một thay đổi planner toàn cluster trong lúc sự cố có thể làm nhiều query khác regress và khiến việc xác định nguyên nhân càng khó.

### Giai đoạn B — Khoanh vùng nguyên nhân

<escape>**Nếu query bị block:**</escape> dùng `pg_stat_activity`/`pg_blocking_pids` để xác định transaction gây chờ.

<escape>**Nếu query chạy nhưng output rất lớn:**</escape> xem pagination, projection, số lượng rows và client fetch.

<escape>**Nếu plan rows estimate sai:**</escape> xem `ANALYZE`, cột MCV, correlations, extended stats, prepared params.

<escape>**Nếu rows estimate đúng nhưng tốn I/O:**</escape> xem buffers, cache, access path, index selectivity, storage.

<escape>**Nếu Sort/Hash spill:**</escape> xem temp I/O, query shape, index, work_mem theo operation và concurrency.

<escape>**Nếu số workers thiếu:**</escape> xem parallel limits, tải đồng thời, yêu cầu CPU/leader.

### Giai đoạn C — Tạo phương án sửa ít rủi ro nhất

Thứ tự cân nhắc tùy bằng chứng:

1. Query rewrite giữ nguyên semantics;
2. Cập nhật/điều chỉnh thống kê;
3. Index phù hợp với predicate/sort và chi phí ghi;
4. Sửa bind types, prepared plan behavior nếu có bằng chứng;
5. Sửa transaction/lock design hoặc tài nguyên I/O;
6. Điều chỉnh memory/parallel/cost có scope hẹp;
7. Hint/plan pinning tạm thời khi còn lý do bất khả kháng.

### Giai đoạn D — Đo nhiều nhóm tham số

Đừng chỉ kiểm tra tenant gây sự cố. Chọn:

- Tenant có nhiều rows;
- Tenant ít rows;
- Giá trị hiếm hoặc không tồn tại;
- Giá trị thời gian rất mới/cũ;
- Query limit nhỏ/lớn;
- Workload concurrency thật.

So kết quả SQL, estimated/actual rows, buffers, spill, workers và latency.

### Giai đoạn E — Triển khai và giám sát

Khi thay đổi production:

- Có owner/phạm vi rõ;
- Có migration an toàn cho index/stats nếu cần;
- Đo error rate, slow query count, p95/p99, CPU/I/O;
- Theo dõi cùng các query khác, không chỉ query mục tiêu;
- Có rollback/fix-forward;
- Ghi lại giả thuyết và kết quả để tránh lặp lại “mẹo” thiếu bằng chứng.

### Giai đoạn F — Gỡ workaround

Nếu đã dùng `plan_cache_mode` override, `enable_*` toggle, cost GUC hoặc hint tạm:

1. Ghi lại phạm vi và lý do;
2. Đặt ngày/điều kiện đánh giá lại;
3. Áp dụng giải pháp gốc;
4. Kiểm thử mà **không cần** workaround;
5. Gỡ override, xác nhận connection pool/session đã trở về mặc định;
6. Theo dõi regression sau khi gỡ.

**Một workaround không có kế hoạch gỡ là một rủi ro dài hạn.**

## 32. Sơ đồ quyết định: có nên ép plan không?

~~~mermaid
flowchart TD
    A["Query chậm / regression"] --> B{"Có SQL + bind values thật?"}
    B -->|Chưa| C["Thu thập traces/logs/queryid"]
    B -->|Có| D["EXPLAIN / EXPLAIN ANALYZE an toàn"]
    D --> E{"Chậm do lock / network / client?"}
    E -->|Có| F["Sửa lock hoặc application path"]
    E -->|Không| G{"Estimated rows sai nhiều?"}
    G -->|Có| H["ANALYZE, MCV, extended stats, generic/custom"]
    G -->|Không| I{"I/O, sort/hash spill, workers, JIT?"}
    I -->|Có| J["Sửa query/index/resources theo bằng chứng"]
    I -->|Không| K["Thử alternative plan với SET LOCAL"]
    H --> L["Đo lại nhiều tham số/workloads"]
    J --> L
    K --> L
    L --> M{"Giải pháp gốc đủ tốt?"}
    M -->|Có| N["Triển khai có rollback + monitoring"]
    M -->|Chưa| O["Nghiên cứu planner bug/cost/hint có scope"]
    O --> N
~~~

Sơ đồ là **quy trình tư duy**, không phải logic tự động để chạy lệnh. Trên production, mỗi nhánh có thể cần quyền DBA, kiểm soát bảo mật và change management riêng.

## 33. Từ vựng cần nhớ

| Thuật ngữ | Nghĩa trong bài |
| --- | --- |
| **Query plan** | Cây thao tác PostgreSQL chọn để thực thi SQL |
| **Cardinality estimate** | Số rows planner dự đoán ở một node |
| **Actual rows** | Số hàng executor quan sát ở node, phải đọc cùng loops |
| **Cost model** | Mô hình chi phí tương đối cho scan/join/sort/parallel |
| **Seq Scan** | Đọc tuần tự các heap pages thích hợp |
| **Nested Loop** | Lặp inner path theo các rows outer |
| **Hash Join** | Dùng hash table cho điều kiện join phù hợp |
| **Sargable predicate** | Điều kiện có thể khai thác đường truy cập/index thích hợp |
| **MCV** | Most Common Values: giá trị/tổ hợp giá trị phổ biến trong thống kê |
| **Extended statistics** | Thống kê nhiều cột/biểu thức để hỗ trợ estimate |
| **Custom plan** | Plan theo giá trị bind cụ thể |
| **Generic plan** | Plan dùng chung nhiều executions |
| **Index Cond** | Điều kiện được index access method dùng để giới hạn truy cập |
| **Filter** | Điều kiện executor áp sau/ngoài bước truy cập |
| **Spill** | Sort/hash dùng file tạm vì dữ liệu vượt ngân sách memory |
| **JIT** | Biên dịch lúc thực thi, có startup cost và lợi ích tùy workload |
| **Plan hint** | Cơ chế tác động/ép lựa chọn plan, không tự sửa estimate |
| **Plan regression** | Kế hoạch/hiệu năng thay đổi theo hướng bất lợi trong workload |
| **Root cause** | Nguyên nhân thật sự gây hiệu năng kém, không chỉ tên node bị nghi |
| **SET LOCAL** | Cấu hình chỉ hiệu lực trong transaction hiện tại |

## 34. Tài liệu PostgreSQL chính thức

Các liên kết dưới đây phục vụ đọc thêm. Khi triển khai, chọn **đúng major version PostgreSQL** đang vận hành thay vì sao chép nguyên các giá trị mặc định của môi trường khác.

- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): cách đọc plan, estimated cost/rows, actual rows/loops, joins và scans.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): `ANALYZE`, `BUFFERS`, `VERBOSE`, `SETTINGS` và các tùy chọn.
- [Planner Statistics](https://www.postgresql.org/docs/current/planner-stats.html): statistics mà optimizer sử dụng.
- [Multivariate Statistics Examples](https://www.postgresql.org/docs/current/multivariate-statistics-examples.html): extended stats, dependencies, ndistinct, MCV và sai lệch ước lượng.
- [ANALYZE](https://www.postgresql.org/docs/current/sql-analyze.html): cách thu thập thống kê, quyền và đặc tính sampling.
- [CREATE STATISTICS](https://www.postgresql.org/docs/current/sql-createstatistics.html): cú pháp, các loại thống kê và phạm vi áp dụng.
- [pg_stats](https://www.postgresql.org/docs/current/view-pg-stats.html): số liệu một cột cho planner.
- [pg_stats_ext](https://www.postgresql.org/docs/current/view-pg-stats-ext.html): quan sát extended statistics.
- [Planner Method Configuration](https://www.postgresql.org/docs/current/runtime-config-query.html#RUNTIME-CONFIG-QUERY-ENABLE): các `enable_*` switches.
- [Planner Cost Constants](https://www.postgresql.org/docs/current/runtime-config-query.html#RUNTIME-CONFIG-QUERY-CONSTANTS): `random_page_cost`, `seq_page_cost`, CPU costs và parallel costs.
- [PREPARE](https://www.postgresql.org/docs/current/sql-prepare.html): generic/custom plan behavior và quyết định lựa chọn.
- [Resource Consumption](https://www.postgresql.org/docs/current/runtime-config-resource.html): `work_mem`, parallel workers và tài nguyên.
- [Indexes](https://www.postgresql.org/docs/current/indexes.html): B-tree, multicolumn, partial, expression, index-only.
- [Partition Pruning](https://www.postgresql.org/docs/current/ddl-partitioning.html#DDL-PARTITION-PRUNING): pruning ở planning/execution time.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_activity`, `pg_stat_all_tables`, index usage.
- [pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html): thống kê workload khi extension được bật.
- [auto_explain](https://www.postgresql.org/docs/current/auto-explain.html): tự ghi execution plans theo điều kiện log.
- [JIT Compilation](https://www.postgresql.org/docs/current/jit.html): chi phí và lợi ích của JIT.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): lock waits và deadlock khác vấn đề plan.

`pg_hint_plan` là extension ngoài PostgreSQL core, không nên giả định hệ thống có sẵn hoặc phiên bản nào cũng hoạt động giống nhau. Nếu cần, hãy đọc tài liệu extension tương ứng và chính sách managed PostgreSQL của môi trường.

## 35. Tổng kết

Khi một truy vấn chậm, **đừng bắt đầu bằng câu “làm thế nào ép Index Scan/Hash Join/Parallel Scan?”**. Hãy bắt đầu bằng câu **“bằng chứng nào cho thấy plan đang chọn sai, và sai bắt đầu từ đâu?”**.

Các nguyên nhân nền thường gặp là: **estimated rows khác actual**, thiếu hoặc lỗi thời **statistics**, tương quan nhiều cột chưa được biết, tham số bị **skew** nhưng dùng **generic plan**, điều kiện lọc không sargable, index không phục vụ đúng `WHERE + ORDER BY`, sort/hash spill, thiếu parallel workers, contention CPU/I/O, lock wait hoặc phần chậm nằm ngoài PostgreSQL.

Các công tắc `enable_seqscan`, `enable_nestloop`, `enable_hashjoin`, `plan_cache_mode` và cost GUC có ích trong **thí nghiệm có kiểm soát** để so sánh alternative plans. Nhưng một alternative plan chạy nhanh hơn **không chứng minh** rằng cần ép nó mãi mãi. Với dữ liệu thay đổi theo tenant, thời gian, phiên bản schema hoặc load, một plan bị đóng đinh có thể trở thành regression nghiêm trọng.

Quy trình bền vững là **đo đúng SQL và tham số → đọc `EXPLAIN ANALYZE` → tìm điểm estimated/actual hoặc runtime evidence lệch → xác định giả thuyết → thử thay đổi tối thiểu bằng `SET LOCAL`/lab → sửa thống kê, SQL, index hoặc tài nguyên thật sự → đo trên nhiều workloads → triển khai có giám sát và rollback**.

**Kết luận cần ghi nhớ:** *đổi kế hoạch là một kết quả có thể xảy ra của việc tối ưu; nó không phải mục tiêu tự thân*. PostgreSQL tối ưu tốt nhất khi được cung cấp **ngữ nghĩa SQL đúng, thống kê sát dữ liệu, cấu trúc index phù hợp và giả định chi phí hợp lý**. Tránh ép kế hoạch khi chưa biết nguyên nhân gốc sẽ giúp hệ thống ổn định hơn, ít nợ kỹ thuật hơn và giữ hiệu năng tốt khi dữ liệu cũng như workload tiếp tục thay đổi.

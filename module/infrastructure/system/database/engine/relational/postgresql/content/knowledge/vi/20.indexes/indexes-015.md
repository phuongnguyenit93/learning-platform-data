# Đo lợi ích chỉ mục bằng dữ liệu và khối lượng công việc thực tế trong PostgreSQL

**Tạo index không tự động đồng nghĩa truy vấn nhanh hơn hoặc hệ thống tốt hơn.** Một B-tree index có thể giảm thời gian tìm một đơn hàng từ hàng trăm mili giây xuống vài mili giây, nhưng index đó cũng có thể làm tăng chi phí của mọi `INSERT`, một số `UPDATE` và công việc `VACUUM`. Ngược lại, một truy vấn đọc gần hết bảng có thể vẫn nên dùng `Seq Scan` dù có index.

Vì vậy, câu hỏi cần trả lời trong một dự án PostgreSQL không phải chỉ là “có nên tạo index trên `customer_id` không?”, mà là:

> **Với dữ liệu, phân bố tham số, tỷ lệ đọc–ghi, mức đồng thời và yêu cầu độ trễ thực tế, index ứng viên có mang lại lợi ích đủ lớn để bù chi phí vận hành hay không?**

Bài học thuộc chương **Chỉ mục** của module **Database Engine Relational PostgreSQL** và tập trung vào **phương pháp đo**, không chỉ cách viết `CREATE INDEX`. Bạn sẽ học cách thiết kế phép thử có baseline, dữ liệu đại diện, khối lượng công việc (*workload*) gồm cả đọc và ghi, chỉ số đo hiệu năng, cách tránh những kết luận sai từ một lần `EXPLAIN ANALYZE`, và cách đưa ra quyết định giữ hoặc bỏ index.

Các năng lực đạt được:

- Biết xác định **truy vấn nào đang gây đau đớn** trước khi đề xuất index.
- Chuẩn bị dữ liệu kiểm thử gần với production về **số hàng, selectivity, skew, correlation, độ rộng tuple và tỷ lệ cập nhật**.
- Đọc `EXPLAIN (ANALYZE, BUFFERS)` và phân biệt `Index Cond`, `Filter`, `Rows Removed by Filter`, `Heap Fetches`, `Sort`.
- Đo chi phí **`INSERT` / `UPDATE` / `DELETE`**, mức tiêu thụ WAL, tỷ lệ HOT và dung lượng index.
- Dùng `pg_stat_statements`, `pg_stat_user_indexes`, `pg_stat_user_tables`, `pgbench` khi phù hợp.
- Thiết kế thử nghiệm **A/B công bằng**, kiểm soát cache, thống kê, concurrency, prepared/generic plan và thứ tự thử nghiệm.
- Kết luận dựa trên **SLO và workload tổng thể**, thay vì chỉ nhìn một truy vấn nhanh hơn.

## 1. Một index tốt phải chứng minh được lợi ích

Giả sử ứng dụng thương mại điện tử có ba loại công việc:

1. Mỗi giây có 2.000 lượt tra đơn mới nhất theo khách hàng.
2. Mỗi giây có 500 lệnh chèn đơn.
3. Mỗi giây có 300 lệnh cập nhật trạng thái đơn.

Một index đa cột `(customer_id, created_at DESC)` có thể giúp loại công việc thứ nhất. Nhưng nếu trạng thái không nằm trong index thì một số UPDATE trạng thái có thể còn cơ hội HOT; nếu thêm `status` vào index để tối ưu thêm truy vấn khác, tình hình ghi có thể thay đổi.

Ngược lại, một index trên `updated_at` có thể tăng tốc dashboard chỉ chạy mỗi giờ một lần, nhưng mọi UPDATE đều sửa `updated_at`, khiến index được bảo trì liên tục.

Cả hai đều có thể là index “hợp lệ” theo SQL. **Chỉ số workload mới cho biết index có đáng giá.**

### Ba nhóm bằng chứng cần có

| Nhóm | Câu hỏi | Chỉ số gợi ý |
| --- | --- | --- |
| **Hiệu năng đọc** | Query mục tiêu có giảm chi phí không? | p50/p95/p99 latency, execution time, shared block hit/read, rows, sorts |
| **Giá phải trả khi ghi** | Việc bảo trì index có làm workload khác xấu đi? | Throughput INSERT/UPDATE, latency ghi, WAL bytes, HOT ratio, lock wait |
| **Vận hành và tài nguyên** | Index chiếm gì và duy trì ra sao? | Index size, table/index bloat, replica lag, VACUUM, thời gian build/rebuild |

Một phép thử chỉ chứng minh `SELECT` nhanh hơn mà bỏ qua ghi và storage là **chưa đủ** để kết luận nên giữ index.

## 2. Bắt đầu từ câu hỏi có thể kiểm chứng

Câu hỏi mơ hồ:

> Truy vấn đơn hàng đang chậm. Hãy thêm index.

Câu hỏi có thể đo:

> Trong workload 80% đọc và 20% ghi, với bảng 30 triệu đơn, index `(tenant_id, status, created_at DESC, order_id DESC)` có giảm p95 của API lấy 25 đơn mới nhất của tenant thường từ 120 ms xuống dưới 40 ms, **mà không làm p95 ghi tăng quá 15% và không làm replica lag vượt ngưỡng** không?

Câu hỏi thứ hai buộc ta xác định:

- **Query cụ thể** và danh sách tham số.
- **Dữ liệu thực tế**: bao nhiêu hàng, tenant nào nhiều dữ liệu.
- **SLO**: ngưỡng độ trễ và throughput chấp nhận được.
- **Ràng buộc chi phí**: ghi, WAL, storage, replication.
- **Phương pháp so sánh**: baseline không có index ứng viên so với phương án có index đó.

Nếu không xác định tiêu chí từ đầu, sau khi đo rất dễ chọn ra vài con số đẹp để biện minh cho phương án đã thích sẵn.

## 3. Đừng đo bằng dữ liệu quá nhỏ

Ví dụ:

~~~sql
CREATE TABLE tiny_orders (
    order_id integer PRIMARY KEY,
    customer_id integer NOT NULL
);

INSERT INTO tiny_orders
SELECT g, g % 10 FROM generate_series(1, 100) AS g;
~~~

Một bảng chỉ có 100 hàng thường vừa trong rất ít trang dữ liệu. PostgreSQL có thể chọn `Seq Scan` vì đọc cả bảng rẻ hơn việc đi qua B-tree rồi truy cập heap.

Điều đó **không chứng minh index vô dụng trên bảng 100 triệu hàng**.

Ngược lại, một index chứng minh có lợi với 100 hàng cũng không nói lên điều gì về 100 triệu hàng có nhiều cập nhật và nhiều người dùng đồng thời.

### Dữ liệu đại diện cần phản ánh gì?

| Khía cạnh | Tác động đến việc chọn index |
| --- | --- |
| Số hàng và số block | Thay đổi tỷ lệ chi phí Seq Scan / Index Scan |
| Số giá trị phân biệt (`n_distinct`) | Quyết định điều kiện có chọn lọc hay không |
| Skew (lệch phân bố) | Tenant lớn và tenant nhỏ có plan khác nhau |
| Tỷ lệ NULL | Ảnh hưởng predicate, selectivity, partial index |
| Correlation với vị trí heap | Quyết định số lần truy cập trang rải rác |
| Độ rộng hàng | Quyết định heap pages, cache footprint và index-only lợi thế ra sao |
| Tỷ lệ INSERT/UPDATE/DELETE | Quyết định giá bảo trì index và HOT |
| Dữ liệu đã bị UPDATE/DELETE lâu ngày | Ảnh hưởng bloat, visibility map và index-only scan |
| Kiểu tham số thực của API | Quyết định generic/custom plan và khả năng dùng partial index |
| Mức đồng thời | Ảnh hưởng lock, cache contention, WAL, I/O saturation |

**Dữ liệu random đều có thể dẫn đến kết luận rất sai** nếu production có một tenant chiếm 60% tổng số đơn, còn 99 tenant khác chia nhau 40%.

## 4. Workload là hỗn hợp truy vấn, không phải một câu SELECT

Một ứng dụng thực tế thường có các nhóm thao tác:

| Ký hiệu | Công việc | Tỷ trọng minh họa |
| --- | --- | ---: |
| Q1 | Lấy 25 đơn gần nhất của một tenant theo trạng thái | 35% |
| Q2 | Tra một đơn bằng primary key | 20% |
| Q3 | Tra đơn của một khách hàng | 15% |
| Q4 | Tổng hợp trạng thái phục vụ dashboard | 10% |
| W1 | INSERT đơn mới | 10% |
| W2 | UPDATE status hoặc thông tin đơn | 8% |
| W3 | DELETE/cleanup theo điều kiện | 2% |

Các tỷ lệ **chỉ để minh họa**, không phải mô hình mặc định cho mọi doanh nghiệp.

Một index có thể tối ưu Q1 rất mạnh nhưng làm W2 chậm hơn. Nếu Q1 chỉ chiếm 0,1% và W2 chiếm 70%, index đó có thể không đáng giữ.

### Trọng số và độ trễ không tuyến tính

Có thể xem một chỉ số mô tả đơn giản như:

\[
T_{\mathrm{weighted}} = \sum_i w_i \times T_i
\]

trong đó `w_i` là tỷ trọng thao tác, `T_i` là thời gian trung bình của nhóm thao tác `i`.

Nhưng **trung bình có trọng số không thay thế p95/p99 hay SLO**. Một API có độ trễ đuôi rất cao có thể gây trải nghiệm xấu ngay cả khi trung bình toàn hệ thống giảm. Một phép thử tốt báo cáo **cả tổng workload lẫn từng nhóm nghiệp vụ quan trọng**.

## 5. Quy trình đo: baseline → thay đổi một index → đo lại

~~~mermaid
flowchart TD
    A["Thu thập query + workload + SLO"] --> B["Dữ liệu/ môi trường đại diện"]
    B --> C["Baseline: chưa có index ứng viên"]
    C --> D["Lưu plans, latency, buffers, WAL, writes"]
    D --> E["Tạo đúng một index ứng viên"]
    E --> F["ANALYZE / chuẩn bị thí nghiệm tương đương"]
    F --> G["Đo lại đọc và ghi ở cùng tải"]
    G --> H["So sánh p50/p95/p99, TPS, size, HOT, WAL"]
    H --> I{"Lợi ích vượt chi phí và ổn định?"}
    I -->|"Có"| J["Lập kế hoạch triển khai/giám sát"]
    I -->|"Không"| K["Sửa hoặc bỏ index ứng viên"]
~~~

Để kết luận có cơ sở:

1. Lưu **baseline trước khi thay đổi**.
2. Chỉ thay đổi **một yếu tố chính** trong mỗi lần so sánh.
3. Dùng cùng truy vấn, tham số, volume, tỷ lệ đọc/ghi và mức đồng thời.
4. Ghi lại configuration, PostgreSQL major version, trạng thái thống kê và cache.
5. Chạy đủ lần để thấy biến động, không tin một kết quả ngẫu nhiên.
6. Tách **microbenchmark** của một truy vấn và **workload benchmark** của ứng dụng.
7. Kiểm tra kết quả ghi có đúng nghiệp vụ, không “nhanh” vì bỏ qua công việc.

## 6. Chuẩn bị database lab riêng

Các câu lệnh sau dùng schema `measure_idx_lab` để minh họa. **Script có `DROP SCHEMA ... CASCADE` sẽ xóa dữ liệu trong schema đó.** Chỉ chạy trên database thực hành riêng, không dùng production hay database có dữ liệu người khác.

Bộ dữ liệu cố ý có:

- **5.000 khách hàng**.
- **300.000 đơn hàng**.
- **100 tenant** với phân bố lệch: tenant 1 có khoảng 60% đơn; các tenant khác chia số còn lại.
- Trạng thái `failed` hiếm (0,5%), `paid` khoảng 19,5%, `pending` khoảng 80%.
- `created_at` tăng theo `order_id` để tạo tương quan vật lý trong dữ liệu chèn.
- Các cột ghi thường xuyên (`status`, `note`, `updated_at`) để đo write amplification.

Đây là **dữ liệu giả được tạo xác định**, dễ chạy lại, không phải “giống production” chỉ vì có vài trăm nghìn hàng. Trong dự án thật, hãy thay bằng snapshot đã khử dữ liệu nhạy cảm hoặc dữ liệu sinh theo **phân bố đã đo**.

### 6.1. Tạo schema và bảng

~~~sql
-- CHỈ CHẠY TRONG DATABASE LAB.
DROP SCHEMA IF EXISTS measure_idx_lab CASCADE;
CREATE SCHEMA measure_idx_lab;

CREATE TABLE measure_idx_lab.customers (
    customer_id integer PRIMARY KEY,
    display_name text NOT NULL,
    email text NOT NULL UNIQUE
);

CREATE TABLE measure_idx_lab.orders (
    order_id bigint PRIMARY KEY,
    tenant_id integer NOT NULL CHECK (tenant_id BETWEEN 1 AND 100),
    customer_id integer NOT NULL
        REFERENCES measure_idx_lab.customers(customer_id),
    status text NOT NULL CHECK (
        status IN ('pending', 'paid', 'failed', 'cancelled')
    ),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    total numeric(12,2) NOT NULL CHECK (total >= 0),
    note text,
    payload text NOT NULL
);

INSERT INTO measure_idx_lab.customers (
    customer_id, display_name, email
)
SELECT
    g,
    'Customer ' || g,
    'customer' || g || '@example.test'
FROM generate_series(1, 5000) AS s(g);
~~~

Hai bảng đã có index phục vụ **PRIMARY KEY** và `customers.email UNIQUE`. Chưa có index riêng trên `orders.tenant_id`/`status`/`created_at`/`customer_id`. Đây là baseline có ý nghĩa hơn việc giả định bảng hoàn toàn không có index.

### 6.2. Nạp 300.000 đơn

~~~sql
INSERT INTO measure_idx_lab.orders (
    order_id,
    tenant_id,
    customer_id,
    status,
    created_at,
    updated_at,
    total,
    note,
    payload
)
SELECT
    g::bigint,
    CASE
        WHEN g % 10 < 6 THEN 1
        ELSE 2 + (g % 99)
    END,
    1 + ((g * 37) % 5000),
    CASE
        WHEN g % 200 = 0 THEN 'failed'
        WHEN g % 5 = 0 THEN 'paid'
        ELSE 'pending'
    END,
    timestamptz '2026-01-01 00:00:00+00'
        + g * interval '1 minute',
    timestamptz '2026-01-01 00:00:00+00'
        + g * interval '1 minute',
    (50 + g % 950)::numeric(12,2),
    CASE
        WHEN g % 100 = 0 THEN 'review requested'
        ELSE NULL
    END,
    repeat('x', 80)
FROM generate_series(1, 300000) AS s(g);

VACUUM (ANALYZE) measure_idx_lab.orders;
VACUUM (ANALYZE) measure_idx_lab.customers;
~~~

**Lưu ý:** `VACUUM` phải chạy **ngoài transaction block explicit**. Lệnh `VACUUM (ANALYZE)` giúp có thống kê mới và visibility map phù hợp cho lab. Trong production, không tự đặt một đợt VACUUM nặng chỉ để làm benchmark mà chưa có kế hoạch.

### 6.3. Kiểm tra số hàng và phân bố

~~~sql
SELECT
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (WHERE status = 'pending') AS pending_orders,
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_orders,
    COUNT(*) FILTER (WHERE status = 'failed') AS failed_orders,
    MIN(created_at) AS earliest_created,
    MAX(created_at) AS latest_created
FROM measure_idx_lab.orders;

SELECT tenant_id, COUNT(*) AS orders_count
FROM measure_idx_lab.orders
GROUP BY tenant_id
ORDER BY orders_count DESC, tenant_id
LIMIT 10;
~~~

Dự kiến có `300000` đơn và khoảng:

| Trạng thái | Số hàng |
| --- | ---: |
| pending | 240.000 |
| paid | 58.500 |
| failed | 1.500 |

Các con số này đến từ công thức sinh dữ liệu, không dựa vào thời gian chạy thực.

Với `tenant_id = 1`, khoảng 60% hàng; với `tenant_id` khác 1, chỉ một phần nhỏ. **Hai loại tham số có độ chọn lọc khác nhau rất mạnh**.

## 7. Định nghĩa workload đọc trước khi tạo index

Nên ghi ra **query template** và các kiểu tham số mà ứng dụng thật gửi. Với lab, dùng bốn query.

### Q1 — Lấy 25 đơn pending mới nhất của tenant

~~~sql
SELECT
    order_id,
    created_at,
    total
FROM measure_idx_lab.orders
WHERE tenant_id = 27
  AND status = 'pending'
ORDER BY created_at DESC, order_id DESC
LIMIT 25;
~~~

Query này có **lọc theo tenant + trạng thái + thứ tự + LIMIT**. Đây là ứng viên hợp lý cho một B-tree composite.

### Q2 — Lấy 25 đơn pending của tenant rất lớn

~~~sql
SELECT
    order_id,
    created_at,
    total
FROM measure_idx_lab.orders
WHERE tenant_id = 1
  AND status = 'pending'
ORDER BY created_at DESC, order_id DESC
LIMIT 25;
~~~

Dù SQL gần như giống Q1, số hàng tenant 1 lớn hơn nhiều. Không được đo một tenant nhỏ rồi tuyên bố ứng dụng đáp ứng SLO cho mọi tenant.

### Q3 — Tìm đơn của một khách hàng

~~~sql
SELECT
    order_id,
    created_at,
    status
FROM measure_idx_lab.orders
WHERE customer_id = 1250
ORDER BY created_at DESC
LIMIT 50;
~~~

Đây là một query pattern khác Q1. Index theo tenant/status **không thay thế đầy đủ** một index bắt đầu bằng customer_id cho kiểu truy vấn này.

### Q4 — Quét nhóm phổ biến và tính tổng

~~~sql
SELECT
    status,
    COUNT(*) AS total_orders,
    SUM(total) AS sum_total
FROM measure_idx_lab.orders
GROUP BY status
ORDER BY status;
~~~

Query này đọc tất cả hàng để tính tổng; một B-tree trên status **không nhất thiết** mang lợi ích. Nó giúp bạn kiểm tra rằng benchmark không chỉ chứa những truy vấn “được dàn dựng” cho index ứng viên thắng.

### Đặt trọng số trước khi đo

Ví dụ giả lập read workload:

| Query | Tỷ trọng |
| --- | ---: |
| Q1 với tenant nhỏ | 40% |
| Q2 với tenant lớn | 10% |
| Q3 theo customer_id | 30% |
| Q4 tổng hợp | 20% |

Tỷ trọng trong production phải dựa trên telemetry. Không dùng con số minh họa làm bằng chứng rằng index composite phù hợp với một công ty thực tế.

## 8. Ghi lại baseline bằng EXPLAIN

Chạy khi chưa tạo index ứng viên:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, SUMMARY ON)
SELECT order_id, created_at, total
FROM measure_idx_lab.orders
WHERE tenant_id = 27
  AND status = 'pending'
ORDER BY created_at DESC, order_id DESC
LIMIT 25;
~~~

Lặp lại với tenant 1 và Q3/Q4. Ghi lại:

- Plan: `Seq Scan` / `Index Scan` / `Bitmap Heap Scan` / `Sort`.
- `actual rows` và `Rows Removed by Filter`.
- `Buffers: shared hit/read`.
- `Execution Time`.
- `Sort Method` và bộ nhớ/dung lượng tạm nếu có.
- Thống kê/estimated rows của từng node.

`TIMING OFF` giảm overhead đo thời gian ở từng node; `Execution Time` tổng vẫn được báo cáo. Nếu cần tìm một node chậm cụ thể, có thể bật timing trong phép thử chẩn đoán riêng.

### Không khẳng định plan giống nhau trên mọi máy

Planner có thể chọn các kế hoạch khác nhau theo version, `work_mem`, `random_page_cost`, parallel settings, thống kê, cache và I/O. Bài học là **biết cách đọc plan và chứng minh lý do**, không phải ghi nhớ một output cố định.

## 9. Đọc Index Cond và Filter

Hai dòng này khác ý nghĩa:

~~~text
Index Cond: (tenant_id = 27)
Filter: (status = 'pending')
~~~

`Index Cond` cho biết biểu thức có thể dùng trong quá trình truy cập index. `Filter` có thể phải kiểm tra **sau khi lấy dữ liệu ứng viên**.

Nếu index chỉ có `tenant_id`, query có thể tìm hàng của tenant 27 rồi vẫn lọc `status` và sort `created_at`.

Một index đa cột có thể giúp:

~~~text
Index Cond: ((tenant_id = 27) AND (status = 'pending'))
~~~

và đồng thời cung cấp thứ tự phù hợp để tránh `Sort`. Lợi ích thực tế phải được xem qua buffers, số hàng quét và latency.

### Rows Removed by Filter

Nếu query chọn 25 hàng nhưng cần xem 100.000 hàng rồi mới lọc, kế hoạch có thể có `Rows Removed by Filter` lớn. Đó là tín hiệu cần hỏi:

- Có index phù hợp điều kiện không?
- Điều kiện có chọn lọc không?
- Planner có ước lượng đúng số hàng không?
- Query có dùng biểu thức khiến index không được áp không?

Không được tự kết luận “Rows Removed by Filter lớn thì luôn phải tạo index”: nếu query lấy phần lớn bảng hoặc index có chi phí ghi cao, Seq Scan vẫn có thể hợp lý.

## 10. Tạo đúng một index ứng viên rồi đo lại

Với Q1/Q2, thử:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON measure_idx_lab.orders (
    tenant_id,
    status,
    created_at DESC,
    order_id DESC
);

ANALYZE measure_idx_lab.orders;
~~~

Các cột đầu có điều kiện bằng, hai cột sau phục vụ thứ tự `ORDER BY created_at DESC, order_id DESC`.

Đo lại:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, SUMMARY ON)
SELECT order_id, created_at, total
FROM measure_idx_lab.orders
WHERE tenant_id = 27
  AND status = 'pending'
ORDER BY created_at DESC, order_id DESC
LIMIT 25;
~~~

và:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, SUMMARY ON)
SELECT order_id, created_at, total
FROM measure_idx_lab.orders
WHERE tenant_id = 1
  AND status = 'pending'
ORDER BY created_at DESC, order_id DESC
LIMIT 25;
~~~

Một plan tốt có thể dùng index để lấy 25 hàng theo đúng thứ tự và **dừng sớm**. Đó thường là lợi ích lớn hơn việc chỉ giảm số hàng từ 300.000 xuống vài nghìn.

### Không đo chỉ query mà bạn biết chắc sẽ thắng

Sau khi tạo index, chạy **cả Q3 và Q4**. Nếu chúng không cải thiện, kết luận đó cũng quan trọng. Nếu workload thiên về Q3, có thể ứng viên cần khác.

## 11. Tính phần trăm cải thiện một cách đúng nghĩa

Giả sử phép đo minh họa (không phải số đo thực tế của lab) ghi:

| Metric | Trước | Sau |
| --- | ---: | ---: |
| p95 Q1 | 85 ms | 12 ms |
| p95 Q2 | 190 ms | 15 ms |
| p95 Q3 | 70 ms | 71 ms |
| p95 W2 UPDATE | 8 ms | 10 ms |

Với latency, phần trăm giảm:

\[
\text{Latency reduction} =
\frac{T_{\text{before}}-T_{\text{after}}}
{T_{\text{before}}}\times100\%
\]

Ví dụ Q1 giảm từ 85 xuống 12 ms, tức giảm khoảng 85,9%.

Với throughput, phần trăm tăng có mẫu số khác:

\[
\text{Throughput gain} =
\frac{X_{\text{after}}-X_{\text{before}}}
{X_{\text{before}}}\times100\%
\]

**Không gọi “nhanh hơn 86%” khi không nói rõ đang đo latency hay throughput.** Latency giảm 50% tương đương tốc độ xử lý một đơn vị công việc có thể tăng gấp đôi trong mô hình đơn giản, nhưng throughput toàn hệ thống còn phụ thuộc mức đồng thời, saturation và các thành phần khác.

Số liệu ở bảng trên chỉ giải thích cách tính. **Không trích nó làm kết quả đo đã được thực thi.**

## 12. Đo nhiều lần và báo cáo biến động

Một lần `EXPLAIN ANALYZE` có thể bị ảnh hưởng bởi:

- Buffer cache còn lạnh hay đã nóng.
- PostgreSQL vừa checkpoint hoặc autovacuum.
- Một truy vấn khác đang sử dụng CPU/I/O.
- JIT compilation và parallel startup.
- Thay đổi execution plan.
- Các background tasks hoặc host bị tranh CPU.

Với mỗi tình huống, nên có:

1. Một giai đoạn warm-up phù hợp.
2. Nhiều lượt đo có cùng tham số.
3. Những lượt đo với tập tham số đại diện, không chỉ một giá trị.
4. Giá trị **median/p50**, **p95/p99** khi mẫu đủ lớn, độ phân tán.
5. Số buffer hit/read, disk I/O, temp usage và trạng thái cache.
6. Metadata phiên bản PostgreSQL, cấu hình chính, kích thước dữ liệu.

### p95 không giống thời gian chậm nhất

Trong 1.000 lần gọi, **p95** là mức mà khoảng 95% phép đo không vượt quá, không phải là giá trị lớn nhất và không phải `AVG × 1.95`. **p99** nhạy hơn với đuôi chậm, cần đủ mẫu để có ý nghĩa.

Khi dùng benchmark client, đo **end-to-end latency** từ phía client nếu SLO của API bao gồm network, pool checkout, serialization, authentication hoặc các bước ngoài database. Thời gian `EXPLAIN` trong server **không đại diện cho toàn bộ độ trễ API**.

## 13. Cache nóng và cache lạnh là hai bài toán khác

PostgreSQL có **shared buffers**; hệ điều hành còn có page cache. Một query chạy lần đầu có thể phải đọc dữ liệu từ lưu trữ; lần sau có thể hưởng lợi vì phần lớn trang đã cache.

Trong `EXPLAIN (ANALYZE, BUFFERS)`:

~~~text
Buffers: shared hit=...
Buffers: shared read=...
~~~

- `hit`: block có sẵn trong shared buffers.
- `read`: block PostgreSQL phải đưa vào shared buffers, **không khẳng định chắc chắn là đọc từ đĩa vật lý**, vì OS page cache có thể phục vụ.

### Sai lầm điển hình

~~~text
Trước index: chạy query một lần (cache lạnh) → 100 ms
Tạo index: chạy query lần hai (cache đã nóng) → 10 ms
Kết luận: index cải thiện 90%
~~~

Kết luận này có thể sai vì **cache đã thay đổi** đồng thời với index.

### Cách làm có cơ sở hơn

- Warm-up **cả baseline và candidate** theo quy trình giống nhau.
- So sánh nhiều lần trên cùng mức tải.
- Ghi cả execution time lẫn buffer hit/read.
- Nếu production thường có dữ liệu nóng trong cache, đo kịch bản warm-cache là quan trọng.
- Nếu production phải xử lý dữ liệu lạnh, dùng môi trường kiểm thử có khả năng tái tạo điều kiện đó mà không gây gián đoạn production.

**Không xóa cache OS hoặc restart server production chỉ để “đo cache lạnh”**. Đây là thao tác nguy hiểm và có thể ảnh hưởng toàn bộ hệ thống.

## 14. Parameter skew: tenant lớn và tenant nhỏ

Dữ liệu lab cố ý cho tenant 1 có phần lớn đơn hàng, còn các tenant khác tương đối nhỏ.

~~~sql
SELECT
    tenant_id,
    COUNT(*) AS order_count
FROM measure_idx_lab.orders
WHERE tenant_id IN (1, 27, 58, 99)
GROUP BY tenant_id
ORDER BY order_count DESC;
~~~

Nếu chỉ đo `tenant_id = 27`, query có thể rất nhanh nhờ độ chọn lọc cao. Nhưng tenant 1 có thể tạo số hàng ứng viên lớn và kế hoạch khác nếu query thiếu `LIMIT` hoặc có thống kê khác.

### Thiết kế bộ tham số thử

| Nhóm tham số | Ví dụ | Mục tiêu |
| --- | --- | --- |
| Tenant rất lớn | 1 | Phát hiện plan cho phân bố skew |
| Tenant trung bình/nhỏ | 27, 58, 99 | Đo truy vấn điển hình |
| Status rất phổ biến | pending | Kiểm tra trường hợp lọc kém chọn lọc |
| Status hiếm | failed | Kiểm tra index/partial index |
| Customer không có đơn | ID ngoài phạm vi hoặc data riêng | Đo miss lookup |
| Khoảng thời gian hẹp/rộng | 1 ngày / 6 tháng | Kiểm tra range selectivity |

Một phép thử tốt có thể **lấy trọng số theo tần suất request thực**, nhưng vẫn kiểm tra riêng tenant lớn vì nó có thể chi phối p99.

## 15. Prepared statement và generic plan có thể đổi kết luận

Ứng dụng Java/JDBC thường không gửi cùng một câu SQL mới hoàn toàn mỗi lần. Nó có thể dùng `PreparedStatement`, plan cache hoặc cơ chế server-side prepared statements.

Để minh họa:

~~~sql
PREPARE latest_orders(integer, text) AS
SELECT order_id, created_at, total
FROM measure_idx_lab.orders
WHERE tenant_id = $1
  AND status = $2
ORDER BY created_at DESC, order_id DESC
LIMIT 25;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE latest_orders(27, 'pending');

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE latest_orders(1, 'pending');

DEALLOCATE latest_orders;
~~~

PostgreSQL có thể dùng **custom plan** dựa vào tham số một lần thực thi, hoặc **generic plan** có thể tái sử dụng cho nhiều lần, tùy chính sách planning và chi phí.

### Vì sao điều này ảnh hưởng index?

- Tenant nhỏ và tenant lớn có selectivity khác nhau.
- Một partial index `WHERE status='failed'` có thể không được generic plan sử dụng nếu tham số trạng thái chưa biết tại planning.
- Lần đo literal `WHERE tenant_id=27` có thể cho plan khác ứng dụng thực tế dùng prepared statement.
- Ứng dụng có thể gửi parameter types khác với literal trong psql, làm thay đổi kế hoạch.

### Thử nghiệm có kiểm soát

Ở những phiên bản hỗ trợ `plan_cache_mode`, trong **session lab** có thể so sánh:

~~~sql
SET plan_cache_mode = force_custom_plan;

PREPARE latest_orders_test(integer, text) AS
SELECT order_id, created_at, total
FROM measure_idx_lab.orders
WHERE tenant_id = $1
  AND status = $2
ORDER BY created_at DESC, order_id DESC
LIMIT 25;

EXPLAIN EXECUTE latest_orders_test(27, 'pending');
EXPLAIN EXECUTE latest_orders_test(1, 'pending');

SET plan_cache_mode = force_generic_plan;

EXPLAIN EXECUTE latest_orders_test(27, 'pending');
EXPLAIN EXECUTE latest_orders_test(1, 'pending');

DEALLOCATE latest_orders_test;
RESET plan_cache_mode;
~~~

Đây là **thí nghiệm chẩn đoán**. Không đặt `force_custom_plan` hoặc `force_generic_plan` làm cấu hình toàn hệ thống chỉ để đạt kết quả benchmark đẹp; cần kiểm tra độ trễ planning và execution trên workload thực tế.

## 16. Partial index có thể hiệu quả cho query hiếm, nhưng phải đo bằng đúng SQL

Nếu các request cần xử lý `failed` chỉ chiếm 0,5% hàng và thường tìm theo tenant, thử một partial index **thay thế** cho một candidate khác trong thí nghiệm riêng:

~~~sql
CREATE INDEX idx_orders_failed_by_tenant
ON measure_idx_lab.orders (
    tenant_id,
    created_at DESC,
    order_id DESC
)
WHERE status = 'failed';
~~~

Query có literal predicate:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM measure_idx_lab.orders
WHERE tenant_id = 27
  AND status = 'failed'
ORDER BY created_at DESC, order_id DESC
LIMIT 25;
~~~

Vì index chỉ chứa hàng failed, nó có thể rất nhỏ so với full composite index.

### Nhớ ba điều khi đo

1. Query production có thật sự thường lọc failed không?
2. Câu SQL production có diễn đạt điều kiện để planner chứng minh dùng được partial index không?
3. UPDATE thay đổi status từ pending sang failed hoặc ngược lại có chi phí thay đổi membership của index không?

Một partial index có thể thắng microbenchmark Q-failed nhưng **không đáng giá** nếu nhóm query đó chạy rất hiếm và workflow ghi trạng thái diễn ra liên tục.

## 17. Index Only Scan phải xem Heap Fetches

Để trả `total` từ một index mà không nhất thiết fetch heap, có thể thử:

~~~sql
CREATE INDEX idx_orders_tenant_cover
ON measure_idx_lab.orders (
    tenant_id,
    status,
    created_at DESC,
    order_id DESC
)
INCLUDE (total);
~~~

Index chứa cột tìm kiếm/thứ tự và thêm `total` như payload.

Một plan có thể là:

~~~text
Index Only Scan using idx_orders_tenant_cover ...
  Index Cond: (...)
  Heap Fetches: ...
~~~

**Không mặc định Heap Fetches = 0.** PostgreSQL cần tuân thủ MVCC visibility; nếu nhiều trang heap chưa all-visible theo visibility map, phải đọc heap để kiểm tra.

### Vì sao phải đo sau một giai đoạn ghi?

Ngay sau `VACUUM` trên dữ liệu ít biến động, Index Only Scan có thể rất đẹp. Nhưng trong production, nếu đơn hàng liên tục bị UPDATE, nhiều trang có thể mất all-visible flag và cần heap fetch.

Một phép thử công bằng nên có:

- Kịch bản dữ liệu ít cập nhật.
- Kịch bản có UPDATE tương tự workload thật.
- `EXPLAIN` với `Heap Fetches` và buffers.
- Chi phí index rộng hơn, đặc biệt khi `total` thay đổi.

**Không giữ cả full composite index và covering index trùng chức năng chỉ vì cả hai đều có plan tốt**; hãy so sánh và chọn tập index có tổng chi phí hợp lý.

## 18. Chi phí INSERT: mỗi index phải được bảo trì

Với table `orders`, khi thêm một hàng:

~~~sql
INSERT INTO measure_idx_lab.orders (
    order_id, tenant_id, customer_id, status,
    created_at, updated_at, total, note, payload
)
VALUES (
    300001, 27, 1250, 'pending',
    '2026-10-01 12:00:00+00',
    '2026-10-01 12:00:00+00',
    199.00,
    NULL,
    repeat('x', 80)
);
~~~

PostgreSQL ghi tuple vào heap và bảo trì các index mà hàng thuộc phạm vi. Với 1 primary key và 5 index bổ sung, thao tác ghi có thể cần cập nhật nhiều cấu trúc hơn so với chỉ primary key.

Chi phí không tỷ lệ tuyến tính cố định với số index, nhưng có thể tăng:

- Trang B-tree/GIN phải đọc/ghi.
- WAL records và full-page images.
- Page splits.
- Cache footprint.
- CPU so sánh khóa/đánh giá expression.
- Contention khi nhiều phiên ghi.
- Chi phí truyền/replay WAL trên replica.

### Đo INSERT như thế nào?

Không chỉ chạy một INSERT rồi đo 1 ms. Hãy so sánh:

- Số rows INSERT mỗi giây tại mức concurrency mục tiêu.
- p50/p95/p99 transaction latency.
- WAL bytes/transaction nếu có.
- CPU/I/O/replica lag.
- Storage/index growth sau một số lượng INSERT tương đương.

**Phải bắt đầu hai phương án từ cùng snapshot dữ liệu**, hoặc ít nhất có phương pháp cân bằng ảnh hưởng do bảng phát triển và cache. Nếu baseline chạy khi bảng 300.000 hàng còn candidate chạy sau 10 triệu INSERT, đó không còn là A/B công bằng.

## 19. Chi phí UPDATE: index có thể làm mất cơ hội HOT

PostgreSQL dùng MVCC, nên `UPDATE` thông thường tạo tuple version mới. Với các điều kiện phù hợp, cơ chế **HOT (Heap-Only Tuple)** có thể giúp tránh bảo trì index entry cho những UPDATE không thay đổi các giá trị liên quan index, nếu còn chỗ trên heap page.

Thử hai dạng:

~~~sql
-- W2a: thay note; không nằm trong index ứng viên trên tenant/status/time.
UPDATE measure_idx_lab.orders
SET note = 'reviewed'
WHERE order_id = 10001;
~~~

~~~sql
-- W2b: thay status; status là cột khóa trong candidate.
UPDATE measure_idx_lab.orders
SET status = 'paid'
WHERE order_id = 10001
  AND status = 'pending';
~~~

W2b có thể làm thay đổi entry trong index `(tenant_id,status,created_at,order_id)`. Nếu index này không tồn tại, một số UPDATE status có thể đủ điều kiện HOT; khi thêm index, HOT có thể giảm.

### Đo bằng pg_stat_user_tables

~~~sql
SELECT
    schemaname,
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    n_dead_tup
FROM pg_stat_user_tables
WHERE schemaname = 'measure_idx_lab'
  AND relname = 'orders';
~~~

Tỷ lệ tham khảo:

\[
\mathrm{HOT\ ratio} =
\frac{\mathrm{n\_tup\_hot\_upd}}
{\mathrm{n\_tup\_upd}}
\]

Chỉ tính khi `n_tup_upd > 0`. Các bộ đếm có lịch sử và có thể trễ; muốn so sánh A/B, lấy **delta trong một khoảng đo** thay vì dùng tổng tồn tại từ nhiều ngày trước.

### Không kết luận chỉ từ HOT ratio

HOT còn phụ thuộc khoảng trống trên heap page, fillfactor, kích thước tuple và những index khác. Tỷ lệ HOT giảm là tín hiệu đánh đổi, nhưng chưa chứng minh index duy nhất đó là nguyên nhân của mọi thay đổi độ trễ ghi.

## 20. Chi phí DELETE và VACUUM

`DELETE` cũng là thao tác có hai mặt:

- Index có thể giúp tìm các hàng cần xóa.
- Tuple và entry index không lập tức biến mất khỏi mọi cấu trúc vật lý khi DELETE commit; PostgreSQL cần phối hợp MVCC và VACUUM để thu hồi những phiên bản đủ điều kiện.

Ví dụ trên **database lab**, rollback để không làm lệch seed:

~~~sql
BEGIN;

DELETE FROM measure_idx_lab.orders
WHERE order_id BETWEEN 200001 AND 200100
RETURNING order_id;

ROLLBACK;
~~~

Để đo workload DELETE thật, cần **một dataset clone dùng một lần** và cho các giao dịch commit theo quy tắc thực tế; việc luôn rollback các DELETE không mô phỏng đầy đủ vòng đời dữ liệu committed, autovacuum và bloat.

### Tại sao rollback không phải benchmark ghi production?

Khi UPDATE/INSERT rồi rollback, PostgreSQL vẫn có thể tạo phiên bản tuple, WAL và công việc dọn dẹp. Hệ quả khác với các transaction commit đều đặn; một benchmark luôn rollback có thể đo một workload không giống thực tế.

Dùng rollback để **học cú pháp an toàn**; dùng database disposable, giao dịch commit và reset dữ liệu tương đương để **đo write throughput nghiêm túc**.

## 21. Đo WAL bằng EXPLAIN khi phiên bản hỗ trợ

Từ PostgreSQL 13 trở lên, `EXPLAIN` có tùy chọn `WAL` dùng cùng `ANALYZE`. Trên database lab:

~~~sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL, TIMING OFF)
UPDATE measure_idx_lab.orders
SET status = 'paid',
    updated_at = clock_timestamp()
WHERE order_id BETWEEN 120001 AND 120100
  AND status = 'pending';

ROLLBACK;
~~~

Quan sát những dòng liên quan WAL records, full-page images và bytes nếu được báo cáo.

**Hai lưu ý:**

1. `EXPLAIN ANALYZE UPDATE` **thực thi UPDATE thật**, không phải ước lượng không ghi.
2. Thử trong transaction rồi rollback vẫn tạo công việc ghi và không tương đương workload production commit. Tùy môi trường, con số WAL còn phụ thuộc checkpoint/full-page writes, cache và trạng thái dữ liệu.

Với PostgreSQL cũ hơn không hỗ trợ tùy chọn `WAL` tương ứng, bỏ nó và dùng công cụ thống kê phù hợp khác. Khi dùng PostgreSQL 14+, có thể khảo sát view `pg_stat_wal` trong phạm vi quyền và phiên bản cho phép.

## 22. Đo WAL bytes trong khoảng workload

`pg_stat_wal` (trong các phiên bản hỗ trợ) báo thống kê toàn instance, bao gồm `wal_bytes`.

~~~sql
-- PostgreSQL 14+; quyền/trường có thể phụ thuộc phiên bản.
SELECT
    wal_records,
    wal_fpi,
    wal_bytes
FROM pg_stat_wal;
~~~

Cách sử dụng:

1. Đọc giá trị **trước** workload.
2. Chạy khối lượng giao dịch đã định.
3. Đọc giá trị **sau** workload.
4. Lấy chênh lệch theo cùng khoảng.
5. Ghi lại traffic nền từ database khác hoặc autovacuum/checkpoints.

**Quan trọng:** `pg_stat_wal` là thống kê cấp instance, không tự tách WAL cho đúng một query, table hoặc tenant. Đừng lấy delta trong một cluster đang rất bận rồi khẳng định tất cả WAL sinh ra từ một index mới.

Nếu môi trường benchmark là cluster riêng chỉ chạy workload thử, diễn giải delta sẽ đáng tin hơn. Với production, cân nhắc các công cụ quan sát/phân tích bổ sung.

## 23. Đo dung lượng index và tổng footprint

Khi tạo nhiều candidate, dùng hàm kích thước:

~~~sql
SELECT
    pg_size_pretty(
        pg_table_size('measure_idx_lab.orders'::regclass)
    ) AS table_size,
    pg_size_pretty(
        pg_indexes_size('measure_idx_lab.orders'::regclass)
    ) AS indexes_size,
    pg_size_pretty(
        pg_total_relation_size('measure_idx_lab.orders'::regclass)
    ) AS total_size;
~~~

Liệt kê từng index:

~~~sql
SELECT
    i.relname AS index_name,
    pg_size_pretty(pg_relation_size(i.oid)) AS index_size
FROM pg_class AS t
JOIN pg_namespace AS n
    ON n.oid = t.relnamespace
JOIN pg_index AS x
    ON x.indrelid = t.oid
JOIN pg_class AS i
    ON i.oid = x.indexrelid
WHERE n.nspname = 'measure_idx_lab'
  AND t.relname = 'orders'
ORDER BY pg_relation_size(i.oid) DESC;
~~~

So sánh dung lượng phải làm sau khi dữ liệu và trạng thái VACUUM tương đương.

### Dung lượng “thừa” có tác động gì?

- Tăng chi phí backup/restore.
- Chiếm disk và cache.
- Làm tăng thời gian và I/O khi build/rebuild.
- Tăng công việc replication/recovery.
- Có thể làm các vùng dữ liệu nóng của index khác bị đẩy khỏi cache.

**Một index chiếm 3 GB không tự là xấu** nếu nó giảm p99 của API quan trọng; một index 50 MB vẫn có thể vô ích nếu không phục vụ query hoặc constraint nào đáng kể.

## 24. Xem số lượt dùng index qua pg_stat_user_indexes

~~~sql
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'measure_idx_lab'
ORDER BY relname, indexrelname;
~~~

Các trường này giúp hiểu index nào được scan trong một khoảng thời gian:

- `idx_scan`: số lần bắt đầu index scan theo thống kê.
- `idx_tup_read`: số entry index được đọc theo cơ chế thống kê.
- `idx_tup_fetch`: số heap tuple được fetch trong những kiểu scan mà trường này theo dõi.

### Vì sao không được đọc idx_scan=0 như “index thừa”?

Một index:

- Có thể bảo vệ `PRIMARY KEY`/`UNIQUE`, dù ít được dùng làm SELECT lookup.
- Có thể phục vụ query báo cáo cuối tháng, chưa xuất hiện trong cửa sổ quan sát.
- Có thể mới được tạo sau khi stats reset.
- Có thể tham gia các đường scan không hiện đầy đủ theo cách người mới kỳ vọng qua một trường đếm đơn lẻ.
- Có thể giảm đột biến latency khi xảy ra một trường hợp hiếm quan trọng.

**Không drop index production chỉ vì `idx_scan=0` trong một buổi chiều.** Cần quan sát đủ dài, bao phủ batch jobs và kiểm tra constraint/dependency.

## 25. Thu thập truy vấn thật bằng pg_stat_statements

`pg_stat_statements` là extension PostgreSQL hữu ích để tổng hợp thống kê **các SQL statements thực thi** theo query identity.

### Điều kiện sử dụng

Phần lớn môi trường cần cấu hình `shared_preload_libraries` và **restart PostgreSQL** để thư viện được preload; sau đó cần `CREATE EXTENSION` trong database với quyền phù hợp.

~~~sql
-- Chỉ chạy nếu môi trường đã cho phép preload extension,
-- có quyền cần thiết và được chủ quản database chấp thuận.
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
~~~

**Không chỉnh `shared_preload_libraries` hay restart production chỉ để làm bài lab**. Nếu extension chưa sẵn sàng, vẫn có thể dùng `EXPLAIN`, logs/telemetry và benchmark client.

### Truy vấn thống kê

~~~sql
SELECT
    queryid,
    calls,
    round(total_exec_time::numeric, 2) AS total_exec_ms,
    round(mean_exec_time::numeric, 2) AS mean_exec_ms,
    round(stddev_exec_time::numeric, 2) AS stddev_exec_ms,
    rows,
    shared_blks_hit,
    shared_blks_read,
    left(query, 180) AS query_template
FROM pg_stat_statements
WHERE dbid = (
    SELECT oid
    FROM pg_database
    WHERE datname = current_database()
)
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

`pg_stat_statements` có khả năng gom các câu SQL tương tự bằng cách chuẩn hóa một phần giá trị literal. Cấu trúc/trường chính xác cần đối chiếu với phiên bản extension. Quyền xem query text/thống kê của user khác có thể bị giới hạn.

### Cách chọn query để tối ưu

Không chỉ sắp theo `mean_exec_time`. Một query trung bình 2 ms nhưng được chạy 2 triệu lần có thể tiêu tốn nhiều tổng thời gian hơn query 200 ms chỉ chạy 5 lần.

Những nhóm nên xem:

- **Tổng execution time cao** (tần suất lớn × thời gian).
- **p95/p99 API cao** (cần telemetry từ app vì pg_stat_statements không trực tiếp cung cấp mọi percentile latency).
- **Rows/buffers cao** so với số hàng thực sự cần.
- **Query có temp file hoặc I/O lớn**.
- **Query ghi** khiến TPS hoặc replica lag xấu.
- **Query hiếm nhưng SLO rất quan trọng**.

`pg_stat_statements.mean_exec_time` không tự đại diện cho p95/p99 của API. Đừng dùng trung bình để suy ra percentile.

## 26. pg_stat_statements là tổng hợp, không phải bản ghi từng request

Các giới hạn cần hiểu:

1. Nó tổng hợp nhiều lần thực thi nên khó tách riêng tenant lớn/nhỏ nếu cùng queryid.
2. Không cung cấp một timeline độ trễ riêng của từng request để tính mọi percentile.
3. Thống kê có thể reset, bị giới hạn số entry và thay đổi theo cấu hình.
4. Query text có thể được chuẩn hóa/truncated theo cơ chế và phiên bản.
5. Thời gian thực thi SQL không bao gồm mọi latency ở connection pool/API.
6. Một truy vấn chứa nhiều DML trong transaction có thể bị ảnh hưởng bởi khóa, commit time và I/O ngoài phần số đo đơn lẻ.

Vì vậy hãy kết hợp **pg_stat_statements + application tracing/metrics + EXPLAIN + benchmark**. Không coi extension là một công cụ “chấm điểm index” tự động.

## 27. Đo từ phía client bằng pgbench

`pgbench` là công cụ benchmark đi kèm hệ sinh thái PostgreSQL. Ngoài benchmark chuẩn, bạn có thể cung cấp **custom SQL script** qua `-f` để đo workload giống ứng dụng hơn.

**Chỉ chạy trên database lab hoặc môi trường staging chuyên dụng.** Benchmark có nhiều worker có thể tăng tải bất thường, gây WAL và làm thay đổi dữ liệu.

### Ví dụ file read-only: latest-orders.sql

~~~text
\set tenant_id random(2, 100)
SELECT order_id, created_at, total
FROM measure_idx_lab.orders
WHERE tenant_id = :tenant_id
  AND status = 'pending'
ORDER BY created_at DESC, order_id DESC
LIMIT 25;
~~~

Lưu file ví dụ tên `latest-orders.sql` trong máy chạy benchmark của bạn, sau đó chạy:

~~~bash
pgbench -n -c 8 -j 4 -T 60 -M prepared \
  -f latest-orders.sql \
  "postgresql://bench_user@localhost:5432/bench_db"
~~~

Ý nghĩa tham số:

| Tham số | Ý nghĩa |
| --- | --- |
| `-n` | Không thực hiện phần vacuum của benchmark chuẩn trước khi chạy |
| `-c 8` | 8 kết nối client đồng thời |
| `-j 4` | 4 worker threads phía pgbench |
| `-T 60` | Thời lượng benchmark 60 giây |
| `-M prepared` | Dùng prepared protocol phù hợp custom script |
| `-f` | File chứa custom script |
| URI | Kết nối tới **database lab**, không phải production |

`pgbench` báo TPS và một số thống kê latency, tùy phiên bản/lựa chọn. Có thể dùng `-l` để ghi per-transaction logs cho phân tích chi tiết hơn, với chú ý file log có thể rất lớn và chứa dữ liệu nhạy cảm từ tên tham số/tập workload.

### Tại sao ví dụ random tenant 2–100 chưa đủ?

Nó **bỏ qua tenant lớn 1**. Nếu production có nhiều request đến tenant 1, benchmark này sẽ đánh giá quá lạc quan.

Có thể tạo script riêng cho tenant 1, hoặc thiết kế phân phối tham số theo telemetry thật, rồi phối hợp tỷ trọng các script. Không nên chỉ dùng `random(1,100)` nếu production skew mạnh.

## 28. Đo hỗn hợp nhiều script và trọng số

`pgbench` hỗ trợ dùng nhiều `-f` và trong các phiên bản có hỗ trợ **weight** cho script, có thể cấu hình tần suất chọn kịch bản, ví dụ:

~~~bash
pgbench -n -c 16 -j 4 -T 120 -M prepared \
  -f latest-orders.sql@8 \
  -f update-order.sql@2 \
  "postgresql://bench_user@localhost:5432/bench_db"
~~~

Cú pháp `@weight` cần đối chiếu với phiên bản pgbench đang dùng. Ý tưởng là mô phỏng **8 phần đọc / 2 phần ghi**.

File `update-order.sql` minh họa:

~~~text
\set order_id random(1, 300000)
UPDATE measure_idx_lab.orders
SET note = 'seen by benchmark',
    updated_at = clock_timestamp()
WHERE order_id = :order_id;
~~~

### Vì sao không thể đo A/B chỉ bằng cách chạy script này hai lượt liên tiếp trên cùng table?

Lượt đầu làm dữ liệu thay đổi, sinh dead tuples, thay đổi visibility map và phân bố cột `note`. Lượt sau không còn bắt đầu từ cùng trạng thái heap/index.

Để so sánh:

- Chuẩn bị **hai bản sao dữ liệu ban đầu tương đương**.
- Ở phương án A không tạo candidate; phương án B có candidate.
- Warm-up tương đương.
- Dùng cùng tập biến/tỷ lệ kịch bản và số kết nối.
- Đo đủ thời gian, ghi tổng các giao dịch đã chạy.
- Không chạy hai test cùng lúc trên cùng phần cứng nếu chúng tranh tài nguyên, trừ khi cố ý kiểm thử concurrent mixed tenants.

Nếu sử dụng hai database riêng nhưng cùng host, cần chắc rằng một benchmark không còn chạy và chiếm I/O/cache khi benchmark kia bắt đầu.

### Tải thực vs tải tối đa

Hai cách kiểm tra khác nhau:

- **Fixed offered load:** giữ cùng mức request/sec để xem latency và SLO có cải thiện không.
- **Saturation test:** tăng load đến khi throughput không tăng thêm hoặc latency vượt ngưỡng.

`pgbench` có khả năng mô phỏng tốc độ giao dịch giới hạn qua các tùy chọn phù hợp (như `-R`). Nếu so A/B ở saturation nhưng một phương án xử lý nhiều request hơn, đừng chỉ so p95 latency mà không ghi rõ throughput tương ứng.

## 29. Một file SQL đo ghi cần làm việc gì?

Nếu ứng dụng có workload 30% INSERT và 70% UPDATE, script benchmark nên phản ánh đúng hành vi:

- INSERT các khóa mới duy nhất, có FK hợp lệ.
- UPDATE chỉ những hàng thuộc trạng thái nguồn hợp lệ.
- Có transaction boundary giống service.
- Không tạo lỗi constraint hàng loạt để “giảm tải”.
- Không gửi cùng một idempotency key rồi `DO NOTHING` khiến tất cả INSERT sau bị bỏ qua.
- Không luôn update một hàng duy nhất, trừ khi đang đo hot-row contention cố ý.

### Một cách sinh INSERT tuần tự an toàn cho lab

Trên database benchmark riêng, dùng một **sequence** để cấp ID cho mỗi script:

~~~sql
CREATE SEQUENCE measure_idx_lab.bench_order_id_seq
START WITH 1000000;
~~~

Một INSERT mẫu:

~~~sql
INSERT INTO measure_idx_lab.orders (
    order_id, tenant_id, customer_id, status,
    created_at, updated_at, total, note, payload
)
VALUES (
    nextval('measure_idx_lab.bench_order_id_seq'),
    27,
    1250,
    'pending',
    clock_timestamp(),
    clock_timestamp(),
    199.00,
    NULL,
    repeat('x', 80)
);
~~~

Sequence tránh tranh cùng primary key giữa clients, nhưng **không đại diện mọi ứng dụng** (UUID random, ULID, v7, tenant key, partitioning có đặc tính ghi khác).

Nếu benchmark cần so sánh index mới đối với INSERT, **cả A và B phải dùng cùng chiến lược ID, lượng dữ liệu được chèn, tỷ lệ tenant/status và phương thức transaction**.

## 30. Đo chi phí ghi bằng throughput và p95, không chỉ EXPLAIN UPDATE

Một câu:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE measure_idx_lab.orders
SET status = 'paid'
WHERE order_id = 12345;
~~~

cho biết plan và thông tin của một statement, nhưng không phản ánh đầy đủ:

- Nhiều phiên cùng cập nhật cùng key.
- WAL flush/commit behavior với lượng transaction thực.
- Trigger và logic nghiệp vụ dài.
- Replication lag khi ghi liên tục.
- Autovacuum sau hàng triệu UPDATE.
- Tail latency của kết nối pool.
- Cạnh tranh CPU/cache/I/O giữa các query.

Do đó phép thử ghi nên gồm ít nhất:

| Metric | Đọc bằng chứng ở đâu |
| --- | --- |
| Committed transactions/sec | pgbench/app workload |
| p50/p95/p99 transaction latency | client tracing / transaction log |
| WAL bytes per window | `pg_stat_wal` / EXPLAIN WAL phù hợp |
| HOT ratio | delta `pg_stat_user_tables` |
| Buffer hit/read/dirtied/written | EXPLAIN BUFFERS và thống kê liên quan |
| Index size growth | `pg_relation_size` |
| Dead tuples/vacuum activity | `pg_stat_user_tables` |
| CPU/disk saturation | Monitoring OS/instance |
| Replica lag | Monitoring replication nếu có |
| Lock waits | `pg_stat_activity`, `pg_locks`, app timeouts |

**Không trộn một phép đo Q1 SELECT không tải với phép đo W2 UPDATE dưới tải cao rồi so sánh thời gian trực tiếp**. Đó là hai điều kiện khác nhau.

## 31. Chỉ đo read latency có thể bỏ qua write amplification

Giả sử một index giúp:

- Q1 p95 giảm từ 120 xuống 20 ms.
- UPDATE status p95 tăng từ 10 lên 14 ms.
- INSERT TPS giảm 12%.
- WAL tăng 35%.
- Index thêm 6 GB.
- Replica lag vẫn dưới 1 giây.

Nên giữ hay bỏ?

**Chưa thể trả lời chỉ từ các con số này**, vì còn thiếu:

- Q1 chiếm bao nhiêu traffic và có phải API quan trọng không?
- UPDATE/INSERT có đang ở ngưỡng throughput tối đa?
- Các SLO nào là hard constraints?
- Dung lượng 6 GB có đáng kể so với tài nguyên thực?
- WAL 35% tăng có làm replica/backup nghẽn ở peak không?
- Có phương án partial index hoặc thay đổi query ít chi phí hơn không?

Đo lường tốt dẫn đến **quyết định có điều kiện và trade-off rõ ràng**, không phải phán “index nhanh thì phải giữ”.

## 32. Benchmark nóng/lạnh và hiệu ứng thứ tự A/B

Thứ tự thử nghiệm:

~~~text
A (chưa index) → B (có index)
~~~

có thể tạo thiên lệch do cache, background vacuum hoặc workload drift. Một quy trình chặt hơn có thể dùng:

~~~text
A → B → A → B
~~~

với dữ liệu được khôi phục về trạng thái tương đương trước từng lượt và warm-up như nhau.

### Vì sao thử A lần nữa?

Nếu A lần hai cũng nhanh lên so với A lần đầu, một phần lợi ích có thể đến từ cache/tài nguyên thay đổi, không chỉ index B.

### Không thể A/B dễ dàng trên production đang ghi liên tục

Trên production:

- Data distribution thay đổi theo giờ.
- Không thể tạo/drop index lớn liên tục mà không tính lock/I/O.
- Warm cache, autovacuum và replica lag có thể bị ảnh hưởng.
- Khó đảm bảo cùng client traffic ở hai cửa sổ thời gian.

Cách làm tốt hơn thường là:

1. Đo telemetry production để xác định query/tham số.
2. Clone dữ liệu đã khử thông tin nhạy cảm sang staging.
3. Chạy A/B có kiểm soát ở staging.
4. Nếu triển khai production, làm rollout có giám sát và khả năng rollback.
5. Đánh giá sau triển khai trên workload thật, nhưng không dùng production như nơi benchmark gây tải quá mức.

## 33. Index scan không có nghĩa index thật sự đem lợi ích lớn

Giả sử trước có Seq Scan 4 ms, sau có Index Scan 3,5 ms. Đúng là plan dùng index, nhưng chênh lệch chỉ 0,5 ms trên môi trường lab. Nếu tạo index làm INSERT chậm hơn 10% và tăng storage nhiều GB, có thể không đáng.

Một số tín hiệu:

- Kế hoạch đổi từ Seq Scan sang Index Scan nhưng `Buffers` không giảm nhiều.
- Index scan vẫn phải đọc rất nhiều tuple vì điều kiện kém chọn lọc.
- `Heap Fetches` cao trong Index Only Scan.
- Query mới cần `Sort` lớn do index không cung cấp đúng thứ tự.
- Lợi ích biến mất với tenant lớn hoặc prepared generic plan.
- Bất lợi xuất hiện khi table bị update thường xuyên.

**Mục tiêu không phải buộc planner chọn index. Mục tiêu là giảm chi phí tổng thể của workload cần phục vụ.**

## 34. Khi nào phải cập nhật thống kê trước khi so plan?

PostgreSQL chọn plan dựa trên các thống kê như `n_distinct`, histogram, most common values và correlation. Nếu bạn vừa nạp 300.000 hàng nhưng chưa `ANALYZE`, planner có thể ước lượng không phù hợp.

Trong lab:

~~~sql
ANALYZE measure_idx_lab.orders;
~~~

Kiểm tra thống kê cơ bản:

~~~sql
SELECT
    attname,
    null_frac,
    n_distinct,
    correlation,
    most_common_vals,
    most_common_freqs
FROM pg_stats
WHERE schemaname = 'measure_idx_lab'
  AND tablename = 'orders'
  AND attname IN (
      'tenant_id', 'status', 'created_at', 'customer_id'
  )
ORDER BY attname;
~~~

### Cách hiểu selectivity từ pg_stats

- `n_distinct` giúp ước lượng số giá trị khác nhau (có ngữ nghĩa đặc biệt khi âm).
- `most_common_vals` và `most_common_freqs` cho biết giá trị phổ biến, hữu ích với dữ liệu skew.
- `correlation` mô tả tương quan giữa thứ tự giá trị cột và thứ tự vật lý heap trong phạm vi thống kê.

Chỉ nhìn `COUNT(DISTINCT tenant_id) = 100` sẽ che mất thực tế tenant 1 chứa 60% hàng. **Giá trị phổ biến và phân bố tần suất** mới quyết định một phần lớn kế hoạch.

### Đừng tự tăng statistics target cho mọi cột

Có thể cần statistics target cao hơn nếu planner ước lượng sai trên dữ liệu skew, nhưng làm vậy tăng chi phí thu thập/lưu thống kê. Hãy nhắm vào cột/query có vấn đề và đo thay đổi trước–sau.

## 35. Multicolumn correlation và extended statistics

Đôi khi `tenant_id` và `status` có quan hệ mạnh. Ví dụ tenant doanh nghiệp có 90% paid, tenant nhỏ có 90% pending. Nếu planner giả định các điều kiện độc lập, số hàng dự đoán cho:

~~~sql
WHERE tenant_id = 1
  AND status = 'paid'
~~~

có thể sai nhiều.

PostgreSQL hỗ trợ **extended statistics** để cải thiện một số trường hợp ước lượng tương quan giữa cột:

~~~sql
CREATE STATISTICS st_orders_tenant_status (
    dependencies,
    mcv
)
ON tenant_id, status
FROM measure_idx_lab.orders;

ANALYZE measure_idx_lab.orders;
~~~

### Extended statistics có thay index không?

Không. Statistics giúp planner **dự đoán số hàng tốt hơn**, còn index cung cấp **đường truy cập dữ liệu**. Có thể cải thiện plan mà không cần index mới nếu nguyên nhân chính là estimate sai, hoặc kết hợp cả thống kê và index.

Đừng mặc định tạo extended statistics luôn giúp query: cần đo estimate và plan trước/sau; không phải mọi phép JOIN/phân phối dữ liệu đều được hỗ trợ đầy đủ bằng cùng một loại statistics.

## 36. Đừng dùng enable_seqscan=off làm bằng chứng index tốt

Đôi khi để thử một đường truy cập, người ta dùng:

~~~sql
SET enable_seqscan = off;
~~~

Điều này **làm planner tránh Seq Scan khi có phương án khác khả dụng**, nhưng không chứng minh Index Scan có chi phí thấp hơn trong môi trường thật.

Nếu index chỉ thắng khi cưỡng ép planner, có thể có các vấn đề:

- Index không hợp với selectivity.
- Thống kê không tốt.
- Parameter/generic plan khác kỳ vọng.
- Chi phí random I/O lớn.
- Bảng đủ nhỏ nên Seq Scan hợp lý.

Dùng thay đổi planner flags **chỉ trong session lab để chẩn đoán**, rồi:

~~~sql
RESET enable_seqscan;
~~~

Không cấu hình chúng toàn hệ thống chỉ để report “index được sử dụng”. Quyết định index phải dựa trên workload với planner và settings bình thường.

## 37. So sánh index đơn, composite và partial một cách có kiểm soát

Ví dụ ba candidate cho truy vấn trạng thái:

**A — Index đơn:**

~~~sql
CREATE INDEX idx_candidate_status
ON measure_idx_lab.orders(status);
~~~

**B — Composite:**

~~~sql
CREATE INDEX idx_candidate_tenant_status_created
ON measure_idx_lab.orders(
    tenant_id, status, created_at DESC, order_id DESC
);
~~~

**C — Partial cho failed:**

~~~sql
CREATE INDEX idx_candidate_failed
ON measure_idx_lab.orders(
    tenant_id, created_at DESC, order_id DESC
)
WHERE status = 'failed';
~~~

**Không chạy cả ba rồi gọi kết quả là benchmark từng candidate.** Khi cùng tồn tại, planner có thể chọn bất kỳ index nào hoặc kết hợp, và mọi DML phải bảo trì cả ba.

Thiết kế công bằng:

1. Chỉ có baseline và những index bắt buộc.
2. Đo A.
3. Khôi phục dataset và cấu hình ban đầu.
4. Tạo candidate A, đo đọc+ghi.
5. Khôi phục.
6. Tạo candidate B, đo đọc+ghi.
7. Khôi phục.
8. Tạo candidate C, đo đọc+ghi.
9. So sánh theo workload và chọn tập index cần thử tiếp.

Với production, không tự chạy vòng tạo/drop index như vậy. Hãy dùng clone/staging.

## 38. Quy tắc chọn phép đo đủ dài

Một benchmark 2 giây có thể không thấy:

- Checkpoint.
- Autovacuum.
- Cache eviction khi dataset lớn hơn RAM.
- WAL replay lag.
- Page splits/B-tree growth.
- Bloat sau nhiều UPDATE/DELETE.
- Thay đổi latency khi connection pool đạt giới hạn.

Nên có nhiều tầng thử nghiệm:

| Tầng | Mục tiêu | Ví dụ |
| --- | --- | --- |
| **EXPLAIN một query** | Hiểu plan và I/O của SQL | 1 query × nhiều tham số |
| **Microbenchmark** | So phiên bản một query ở tải thấp | 1–5 phút tùy hệ thống |
| **Mixed workload** | Đo trade-off đọc–ghi ở concurrency thực | 10–30 phút hoặc đủ số giao dịch |
| **Soak test** | Quan sát ổn định, bloat, WAL, VACUUM, replica | Thời gian đủ để gặp maintenance cycles |
| **Production observation** | Kiểm tra lợi ích sau rollout | Qua peak traffic và batch jobs |

Các mốc thời gian trong bảng là **gợi ý minh họa, không phải tiêu chuẩn bắt buộc**. Benchmark chỉ đáng tin khi đủ lâu để đo các hiện tượng có ý nghĩa trong hệ thống đó.

## 39. Chọn một phương án có thể rollback khi triển khai

Sau khi benchmark cho thấy candidate phù hợp, trên bảng production lớn có thể cần `CREATE INDEX CONCURRENTLY` để giảm chặn các thao tác ghi thông thường:

~~~sql
-- Ví dụ cú pháp: không chạy trên production nếu chưa có kế hoạch.
CREATE INDEX CONCURRENTLY idx_orders_tenant_status_created
ON measure_idx_lab.orders (
    tenant_id, status, created_at DESC, order_id DESC
);
~~~

Những điều cần biết:

- `CONCURRENTLY` không được chạy trong transaction block explicit.
- Có thể cần nhiều lượt scan và chờ transaction/snapshot liên quan.
- Vẫn tiêu tốn CPU/I/O/WAL và có thể ảnh hưởng latency.
- Nếu thất bại, có thể để lại index invalid.
- Cần theo dõi tiến trình/health và có cách xử lý khi fail.

Quan sát `pg_stat_progress_create_index` (nếu phiên bản có hỗ trợ) có thể giúp biết build đang ở giai đoạn nào:

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS table_name,
    index_relid::regclass AS index_name,
    phase,
    blocks_total,
    blocks_done
FROM pg_stat_progress_create_index;
~~~

### Phải đo sau rollout

Một index có lợi trong staging nhưng chưa chắc giống khi production có:

- Prepared statements/generic plans.
- Dữ liệu nhiều partition khác nhau.
- Tần suất UPDATE cao hơn.
- Query theo tenant phân bố khác.
- Replica lag hoặc WAL saturation.
- Peak traffic chưa xuất hiện lúc staging.

Sau rollout, đo lại **đúng các SLO và chi phí đã định nghĩa trước**, không chỉ kiểm tra index đã tồn tại.

## 40. Có thể dùng pg_stat_statements để đánh giá sau triển khai như thế nào?

Giả sử trước và sau rollout bạn có cùng query template và các chỉ số:

- `calls`.
- `total_exec_time`.
- `mean_exec_time` và độ phân tán.
- `shared_blks_hit/read`.
- Rows xử lý.
- Thống kê bên ứng dụng về p95/p99 và tenant.

Điều quan trọng là lấy **delta qua các khoảng thời gian tương đương** và chú ý:

- Số requests có thay đổi không?
- Tỷ lệ tenant lớn/nhỏ có đổi không?
- Tỷ lệ cache hit có giống không?
- Có thay đổi code/parameter/plan khác cùng lúc không?
- Có migration hay background job trong khoảng đó không?

Nếu từ 1.000 request/phút tăng lên 10.000 request/phút sau index, `total_exec_time` có thể tăng dù mỗi request nhanh hơn. Vì vậy không dùng một chỉ số tổng đơn lẻ để kết luận tối ưu thất bại.

## 41. Khi nào nên bỏ một index?

Một ứng viên bỏ index có thể có những dấu hiệu:

- Không phục vụ PRIMARY KEY/UNIQUE/exclusion constraint cần thiết.
- Không có query quan trọng dùng index qua một cửa sổ quan sát đầy đủ.
- Có index khác thay thế phần lớn nhu cầu với chi phí thấp hơn.
- Chi phí bảo trì ghi/WAL/storage cao so với lợi ích.
- Index là bản duplicate do migration.
- Query đã đổi, không còn lọc/sắp theo những cột đó.

Nhưng cần kiểm tra thêm:

- FK/DELETE parent workloads có phụ thuộc index không?
- Batch jobs cuối tháng có cần index không?
- Có truy vấn bảo mật/tenant hiếm nhưng rất quan trọng không?
- Nếu drop, kế hoạch rollback/recreate mất bao lâu?
- Đã đo lại trong staging trước quyết định chưa?

Với index không phục vụ constraint, có thể cân nhắc `DROP INDEX CONCURRENTLY` khi phù hợp, với các giới hạn riêng. Không drop index production theo một cảnh báo tự động thiếu ngữ cảnh.

## 42. Một bảng quyết định minh họa

Giả sử có ba index ứng viên, số liệu **giả định** từ một benchmark hỗn hợp được thiết kế công bằng:

| Tiêu chí | Không candidate | Composite đầy đủ | Partial failed |
| --- | ---: | ---: | ---: |
| p95 latest-orders (ms) | 120 | 22 | 115 |
| p95 failed-orders (ms) | 140 | 23 | 18 |
| INSERT TPS | 3.000 | 2.750 | 2.940 |
| UPDATE status p95 (ms) | 9 | 12 | 10 |
| Dung lượng thêm | 0 | 160 MB | 12 MB |

Nếu 70% request là latest-orders, composite có khả năng đem lợi ích lớn hơn dù chi phí ghi cao. Nếu chỉ 1% request là latest-orders, nhưng nhóm failed-orders là API có SLO khắt khe, partial có thể hợp lý hơn.

**Không kết luận phương án thắng chỉ bằng cách đếm số ô tốt hơn.** Hãy đặt SLO, tỷ trọng traffic, giới hạn storage và yêu cầu availability trước, rồi phân tích trade-off.

Các số trên là dữ liệu minh họa phương pháp ra quyết định, **không phải kết quả đã đo bằng công cụ**.

## 43. Bẫy khi so hai phương án trên dữ liệu khác trạng thái

Những thay đổi sau có thể khiến phép so không công bằng:

- Baseline chạy trước `VACUUM`, candidate chạy ngay sau `VACUUM`.
- Candidate được đo khi `shared_buffers` đã warm, baseline thì cold.
- Baseline 300.000 hàng, candidate 350.000 hàng sau nhiều INSERT.
- Một bên có `ANALYZE` mới, bên kia thống kê cũ.
- Bên baseline thử Q1 với tenant 1, bên candidate tenant 27.
- Một bên dùng literal SQL, bên kia prepared generic plan.
- Một bên có autovacuum đang chạy, bên kia không.
- Một bên chạy 1 connection, bên kia 32 connections.
- Một bên thử commit, bên kia rollback.
- Một bên có trigger/FK check khác.
- Benchmark candidate cùng lúc một job phân tích chạy nền.

Hệ thống có thể thay đổi ngoài tầm kiểm soát. Việc làm đúng là **ghi rõ những yếu tố đó**, cân bằng chúng khi có thể, và không tuyên bố mức cải thiện chính xác hơn độ tin cậy của thí nghiệm.

## 44. Benchmark không được làm hỏng tính đúng đắn

Một benchmark cho thấy UPDATE status chạy nhanh hơn nhưng bỏ qua constraint hoặc trigger có thể không so sánh cùng nghiệp vụ. Tương tự, script có:

~~~sql
INSERT INTO measure_idx_lab.orders (...)
VALUES (...)
ON CONFLICT DO NOTHING;
~~~

nếu mọi client đều gửi trùng khóa, phần lớn “INSERT” thực tế **không chèn hàng nào**. TPS có thể rất cao vì ít công việc ghi.

Các quy tắc:

1. Xác nhận số hàng được chèn, cập nhật, xóa đúng dự kiến.
2. Tỷ lệ conflict/retry phải giống workload thực.
3. Với upsert, đo cả nhánh INSERT mới và nhánh DO UPDATE/DO NOTHING theo tỷ trọng thật.
4. Không bỏ authorization/constraint/trigger chỉ để benchmark thắng.
5. Không đổi kiểu dữ liệu, fillfactor hoặc độ rộng payload giữa A/B mà quên ghi nhận.
6. Dùng production-like role/permission và transaction policy khi cần so ứng dụng.

**Tốc độ cao trên một workload sai không phải bằng chứng cải thiện hiệu năng hệ thống thật.**

## 45. Bài tập thực hành có đáp án

Các bài tập dùng schema `measure_idx_lab` từ mục 6. Với bài DDL thêm index, nếu đã tạo index tương đương thì hãy đo trên bản clone/reset theo hướng dẫn thay vì tích lũy index trùng nhau. Với bài ghi, không chạy trên production và dùng transaction/rollback chỉ khi học thao tác.

### Bài 1. Xác định vấn đề trước khi tạo index

**Yêu cầu:** Một query chạy 2 ms nhưng được gọi 1 triệu lần/ngày; query khác chạy 250 ms và được gọi 20 lần/ngày. Nên xem query nào trước?

**Đáp án:** Không quyết định chỉ từ một con số. Query đầu có tổng CPU/time đáng kể; query hai có thể vi phạm p95/SLO hoặc là nghiệp vụ quan trọng. Thu thập tổng execution time, p95/p99 và ảnh hưởng nghiệp vụ rồi ưu tiên có căn cứ.

### Bài 2. Vì sao seed đều không đại diện tenant skew?

**Đáp án:** Nếu production có tenant 1 chiếm 60% đơn, còn seed chia đều 100 tenant, planner và benchmark có thể đánh giá sai số hàng, I/O và p95 theo tham số. Cần mô phỏng phân bố thực tế.

### Bài 3. Ghi baseline Q1

~~~sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT order_id, created_at, total
FROM measure_idx_lab.orders
WHERE tenant_id = 27
  AND status = 'pending'
ORDER BY created_at DESC, order_id DESC
LIMIT 25;
~~~

**Đáp án:** Ghi plan, execution time, shared hits/reads, rows và sort trước khi tạo index. Không tự điền số ms khi chưa chạy.

### Bài 4. Tạo một index phục vụ Q1

~~~sql
CREATE INDEX idx_exercise_latest
ON measure_idx_lab.orders (
    tenant_id, status, created_at DESC, order_id DESC
);
~~~

**Đáp án:** Index có thể hỗ trợ lọc bằng hai cột đầu rồi lấy các hàng theo đúng thứ tự LIMIT. Cần đo, không cam kết planner luôn chọn.

### Bài 5. Vì sao Q4 có thể vẫn Seq Scan?

~~~sql
SELECT status, COUNT(*), SUM(total)
FROM measure_idx_lab.orders
GROUP BY status;
~~~

**Đáp án:** Truy vấn cần xử lý toàn bộ bảng để tính tổng. Index theo tenant/status không nhất thiết giúp; Seq Scan có thể là kế hoạch rẻ hơn.

### Bài 6. Tính phần trăm giảm latency

Một query từ 100 ms xuống 25 ms.

**Đáp án:** Latency giảm `(100-25)/100 = 75%`. Đừng nhầm với throughput toàn hệ thống tăng 75%.

### Bài 7. Index Scan có thật sự tốt hơn không?

Trước Seq Scan 4,0 ms; sau Index Scan 3,8 ms. INSERT TPS giảm 20%.

**Đáp án:** Chưa đủ lý do giữ index chỉ vì plan đổi. Lợi ích đọc rất nhỏ, chi phí ghi lớn; cần xem tần suất query, SLO và độ ổn định phép đo.

### Bài 8. Vì sao heap fetch quan trọng?

**Đáp án:** Index Only Scan vẫn cần kiểm tra MVCC visibility; khi trang chưa all-visible, có thể phải fetch heap. Cần xem `Heap Fetches` và đo sau giai đoạn UPDATE, không chỉ ngay sau VACUUM.

### Bài 9. Đo HOT ratio

~~~sql
SELECT n_tup_upd, n_tup_hot_upd
FROM pg_stat_user_tables
WHERE schemaname = 'measure_idx_lab'
  AND relname = 'orders';
~~~

**Đáp án:** Lấy delta giữa trước và sau workload, chia số HOT UPDATE cho tổng UPDATE trong cùng khoảng; không dùng bộ đếm lũy kế cũ như thể chỉ phản ánh lần test.

### Bài 10. Vì sao UPDATE status có thể đắt hơn sau composite index?

**Đáp án:** Vì `status` nằm trong index key nên thay trạng thái có thể cần index maintenance và giảm cơ hội HOT, tăng WAL/I/O. Mức tăng phải đo bằng workload ghi thực.

### Bài 11. Cách xem index chiếm bao nhiêu dung lượng

~~~sql
SELECT
    pg_size_pretty(
        pg_indexes_size('measure_idx_lab.orders'::regclass)
    ) AS indexes_size;
~~~

**Đáp án:** Trả tổng dung lượng các index gắn với bảng trong thời điểm query.

### Bài 12. Tại sao shared read không luôn là disk read?

**Đáp án:** `shared read` là trang được đưa vào shared buffers; nó có thể được phục vụ từ OS page cache, không chắc là I/O vật lý xuống đĩa.

### Bài 13. Có nên restart production để đo cache lạnh?

**Đáp án:** Không. Dùng staging/benchmark riêng với quy trình kiểm soát cache và workload; restart/xóa cache production có thể gây ảnh hưởng lớn và không cần thiết.

### Bài 14. pg_stat_statements có p95 sẵn không?

**Đáp án:** Không phải công cụ cung cấp đầy đủ per-request percentiles mặc định; nó có mean/stddev và thống kê tổng hợp. Lấy p95/p99 từ application tracing, benchmark logs hoặc nguồn telemetry thích hợp.

### Bài 15. Partial index failed có lợi cho mọi query không?

**Đáp án:** Không. Nó giúp các query mà planner chứng minh predicate phù hợp, đặc biệt status failed. Query pending không thể dùng partial index đó để tìm mọi hàng pending.

### Bài 16. Vì sao generic plan có thể bỏ qua partial index?

**Đáp án:** Với `WHERE status = $1`, generic plan không biết `$1='failed'` cho mọi lần thực thi, nên không chắc predicate query bao hàm `WHERE status='failed'` của partial index.

### Bài 17. Cách tìm tenant có nhiều đơn nhất

~~~sql
SELECT tenant_id, COUNT(*) AS n
FROM measure_idx_lab.orders
GROUP BY tenant_id
ORDER BY n DESC, tenant_id
LIMIT 5;
~~~

**Đáp án:** Giúp xác nhận skew; không dùng một tenant ngẫu nhiên để đại diện mọi tham số.

### Bài 18. Vì sao không đo UPDATE trong transaction luôn rollback?

**Đáp án:** Dù rollback, PostgreSQL có thể vẫn sinh tuple/WAL và ảnh hưởng cleanup; kết quả không đại diện hoàn toàn cho workload commit, index growth và vòng đời autovacuum. Muốn so ghi thật, dùng dataset disposable và các transaction commit tương đương.

### Bài 19. Thay đổi một hay nhiều index cùng lúc?

**Đáp án:** Để biết hiệu ứng riêng của một candidate, thay **một yếu tố** trong mỗi lần so, reset về baseline trước candidate tiếp theo. Nếu tạo ba index đồng thời, không tách được lợi ích và chi phí từng index.

### Bài 20. idx_scan bằng 0 có đủ để drop index?

**Đáp án:** Không. Index có thể phục vụ constraint, query hiếm, workload chưa diễn ra hoặc stats vừa reset. Cần đánh giá đầy đủ.

### Bài 21. pg_stat_wal delta đo cho đúng một bảng không?

**Đáp án:** Không. Đây là view cấp instance; delta có thể gồm WAL của database/session khác và background activity. Cần môi trường đo cô lập hoặc công cụ bổ sung.

### Bài 22. Vì sao LIMIT làm composite index hấp dẫn?

**Đáp án:** Nếu index cung cấp đúng điều kiện và thứ tự, PostgreSQL có thể dừng sau khi tìm đủ 25 hàng, thay vì đọc/sắp xếp một tập lớn.

### Bài 23. Đánh giá một index dùng INCLUDE(total)

**Đáp án:** Kiểm tra Index Only Scan/Heap Fetches, dung lượng index tăng, UPDATE total có phát sinh maintenance và HOT giảm không. Không chỉ nhìn một lần SELECT sau VACUUM.

### Bài 24. Khi nào cần CREATE INDEX CONCURRENTLY?

**Đáp án:** Khi cần giảm mức chặn ghi trong quá trình build trên bảng đang phục vụ, theo điều kiện và hạn chế của PostgreSQL. Nó vẫn tốn thời gian/tài nguyên, không được chạy trong explicit transaction block và có thể để lại index INVALID khi thất bại.

## 46. Mẫu báo cáo đo index nên có những trường nào?

Một báo cáo ngắn nhưng có thể kiểm chứng nên có:

| Mục | Nội dung phải ghi |
| --- | --- |
| Mục tiêu | Query/SLO nào cần cải thiện, giới hạn write overhead |
| Môi trường | PostgreSQL version, CPU, RAM, storage, shared_buffers, work_mem, connection count |
| Dữ liệu | Số hàng, kích thước, phân bố tenant/status, NULL/skew/correlation |
| Workload | Query templates, tỷ trọng, concurrency, parameter sets, transaction boundary |
| Baseline | Plans, latency percentiles, TPS, buffers, HOT/WAL, index size |
| Candidate | CREATE INDEX statement, estimated storage, build method |
| Phép thử | Warm-up, thời lượng, số lượt, A/B order, workload reset |
| Kết quả đọc | p50/p95/p99 từng query và toàn workflow, blocks, sorts |
| Kết quả ghi | INSERT/UPDATE/DELETE TPS, latency, WAL, HOT, locks |
| Vận hành | Storage growth, replica lag, autovacuum, tiến trình build |
| Rủi ro | Parameter skew, generic plan, cache, workload drift, data privacy |
| Quyết định | Giữ/sửa/bỏ index; điều kiện rollback và theo dõi sau rollout |

Ví dụ kết luận có điều kiện:

> Với dữ liệu 30 triệu đơn và workload đã mô tả, candidate làm p95 của API latest-orders giảm dưới SLO 40 ms trong nhiều lượt thử, còn p95 ghi tăng trong giới hạn 15%, replica lag không vượt ngưỡng và storage có dự phòng. Đề xuất triển khai theo lịch và theo dõi p95, TPS, WAL/replica lag sau rollout; rollback nếu ngưỡng đã định bị vượt.

Đó là một quyết định tốt hơn câu “EXPLAIN có Index Scan nên index hiệu quả”.

## 47. Những sai lầm thường gặp khi đo lợi ích index

1. **Chỉ kiểm tra index có tồn tại**, không đo query thật.
2. **Chỉ chạy một EXPLAIN** rồi kết luận cho toàn workload.
3. **Dùng bảng vài trăm hàng** để suy hiệu năng hàng triệu hàng.
4. **Dùng dữ liệu random đều**, bỏ qua tenant skew và NULL distribution.
5. **Chỉ thử một tenant**, không đo các nhóm tham số phổ biến/đắt.
6. **Không có baseline** trước khi tạo index.
7. **Tạo nhiều candidate cùng lúc** nên không biết index nào mang lợi ích.
8. **Đo baseline cache lạnh, candidate cache nóng**.
9. **Bật enable_seqscan=off** rồi gọi plan có Index Scan là thành công.
10. **Không ANALYZE** sau thay đổi dữ liệu lớn.
11. **Bỏ qua prepared/generic plan** khác literal query.
12. **Không xem Sort/Index Cond/Filter/Heap Fetches** mà chỉ nhìn nhãn scan.
13. **Đo read mà bỏ qua INSERT/UPDATE/DELETE throughput**.
14. **Đo ghi bằng rollback-only**, không phản ánh vòng đời commit/vacuum.
15. **Không xem WAL/replica lag** dù production dùng replication.
16. **Không tính index storage/backup/rebuild**.
17. **Coi shared read là disk read tuyệt đối**.
18. **Coi pg_stat_statements mean là p95**.
19. **Lấy global pg_stat_wal delta rồi quy cho một query** trong cluster nhiều workload.
20. **Drop index vì idx_scan=0**, quên UNIQUE/PK và job hiếm.
21. **Benchmark toàn conflict DO NOTHING** nhưng gọi đó là INSERT workload.
22. **So đo hai phương án ở concurrency khác nhau**.
23. **Kết luận từ thời gian ngắn hơn chu kỳ autovacuum/checkpoint**.
24. **Quên kiểm tra tính đúng của dữ liệu sau benchmark**.
25. **Triển khai CREATE INDEX production mà bỏ qua locks/I/O và phương án rollback**.
26. **Nhầm chỉ số query với end-to-end API latency**.
27. **Không ghi ngữ cảnh phần cứng/cấu hình/major version** nên không tái lập được.
28. **Tối ưu query cực hiếm nhưng làm xấu những write path quan trọng**.

## 48. Checklist thực hành

- [ ] Xác định query/API chậm dựa trên telemetry, không dựa cảm giác.
- [ ] Ghi SLO và ngưỡng chi phí write/storage trước khi đo.
- [ ] Kiểm tra index hiện có, nhất là PRIMARY KEY/UNIQUE/composite.
- [ ] Có dataset đại diện về size, skew, correlation và độ rộng hàng.
- [ ] Có danh sách query templates cùng phân bố tham số thực.
- [ ] Có tỷ lệ READ/INSERT/UPDATE/DELETE và số concurrent clients.
- [ ] Baseline được đo trên trạng thái dữ liệu/thống kê rõ ràng.
- [ ] Candidate chỉ thay một yếu tố; không tích lũy index trùng.
- [ ] Dùng EXPLAIN (ANALYZE, BUFFERS) cho truy vấn SELECT an toàn.
- [ ] Đọc Index Cond, Filter, Rows Removed, Sort, Heap Fetches.
- [ ] Thử cả tenant lớn và tenant nhỏ, status phổ biến và hiếm.
- [ ] Thử prepared/generic plan khi ứng dụng có parameterized SQL.
- [ ] Warm-up và số lượt thử tương đương ở A/B.
- [ ] Ghi p50/p95/p99, throughput, buffers và tail latency.
- [ ] Đo W1/W2/W3 bằng transaction commit trên môi trường disposable.
- [ ] Ghi HOT ratio, WAL delta, index size, vacuum/replica lag.
- [ ] Không làm các thao tác benchmark phá hoại trên production.
- [ ] Có kế hoạch tạo index phù hợp, cân nhắc CONCURRENTLY.
- [ ] Có telemetry sau rollout và ngưỡng rollback.
- [ ] Có báo cáo ngắn giải thích **lợi ích và giá phải trả**.

## 49. Tài liệu PostgreSQL chính thức

Để đối chiếu chi tiết theo **major version** server và công cụ đang sử dụng:

- [Indexes](https://www.postgresql.org/docs/current/indexes.html) — vai trò index và đánh đổi chung.
- [Examining Index Usage](https://www.postgresql.org/docs/current/indexes-examine.html) — xem planner có dùng index không.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html) — plan, ANALYZE, BUFFERS.
- [EXPLAIN command](https://www.postgresql.org/docs/current/sql-explain.html) — các tùy chọn, bao gồm WAL theo version.
- [Statistics Used by the Planner](https://www.postgresql.org/docs/current/planner-stats.html) — statistics và extended statistics.
- [Index-Only Scans and Covering Indexes](https://www.postgresql.org/docs/current/indexes-index-only-scans.html) — INCLUDE/visibility map.
- [Partial Indexes](https://www.postgresql.org/docs/current/indexes-partial.html) — predicate và giới hạn generic plan.
- [Multicolumn Indexes](https://www.postgresql.org/docs/current/indexes-multicolumn.html) — thứ tự cột và lựa chọn plan.
- [HOT Updates](https://www.postgresql.org/docs/current/storage-hot.html) — Heap-Only Tuple, tương tác với index.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — pg_stat_user_tables, pg_stat_user_indexes, pg_stat_wal.
- [pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html) — extension gom thống kê SQL.
- [pgbench](https://www.postgresql.org/docs/current/pgbench.html) — custom scripts, transaction latency và benchmark clients.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html) — CONCURRENTLY, build và hạn chế.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html) — MVCC cleanup/autovacuum.
- [System Information Functions](https://www.postgresql.org/docs/current/functions-admin.html) — đo kích thước quan hệ/index.

`/current/` dẫn đến tài liệu PostgreSQL hiện hành trên website. Khi soạn migration hoặc đo server cũ, mở đúng tài liệu major version, đặc biệt với `pg_stat_wal`, `EXPLAIN WAL`, `pgbench` và các tùy chọn planner.

## 50. Tổng kết

**Đo lợi ích index là đo một thay đổi đối với toàn workload, không phải chỉ đo một lệnh SELECT.**

Một quy trình có thể tin cậy gồm:

1. **Xác định nhu cầu và SLO** của query/API trước khi tối ưu.
2. **Có dữ liệu đại diện** về kích thước, skew, correlation, NULL, MVCC và phân bố tham số.
3. **Ghi baseline** rồi thử từng index ứng viên trong điều kiện công bằng.
4. **Đọc EXPLAIN và buffers** để hiểu nguyên nhân cải thiện, không chỉ nhìn tên Index Scan.
5. **Đo cả đọc lẫn ghi**: latency percentiles, TPS, WAL, HOT, disk/index size, lock, vacuum và replica lag.
6. **Xác nhận bằng workload tham số hóa thực tế** thay vì chỉ literal query hoặc synthetic query không đại diện.
7. **Triển khai có kiểm soát và theo dõi sau rollout**, sẵn sàng điều chỉnh nếu lợi ích không bù được chi phí.

Index đáng giữ là index giúp PostgreSQL đạt **mục tiêu latency/throughput/tính đúng** của hệ thống trong khi chi phí ghi, WAL, storage và vận hành **vẫn nằm trong giới hạn chấp nhận được**. Câu trả lời tốt nhất luôn dựa trên số đo **trong điều kiện phản ánh ứng dụng thật**, không dựa vào số lượng index hay một kết quả benchmark đơn lẻ.

# Thống kê cột, histogram, giá trị phổ biến và tương quan trong PostgreSQL

Hai câu truy vấn có cú pháp gần như giống nhau có thể nhận hai kế hoạch thực thi hoàn toàn khác:

```sql
SELECT *
FROM orders
WHERE status = 'paid';

SELECT *
FROM orders
WHERE status = 'cancelled';
```

Nếu `paid` chiếm 90% đơn hàng còn `cancelled` chỉ chiếm 0,2%, PostgreSQL không nên giả định hai truy vấn trả cùng số dòng. Câu đầu có thể phù hợp với quét bảng tuần tự (*sequential scan*); câu sau có thể dùng index để đọc một tập nhỏ các dòng. Tương tự, điều kiện `created_at >= ...` có thể trả gần như mọi dòng hoặc chỉ vài dòng, tùy **phân bố giá trị thời gian**. Một index tốt về cấu trúc cũng chưa chắc được sử dụng nếu PostgreSQL ước lượng truy cập nó sẽ đắt hơn quét bảng.

Để ra quyết định, **bộ tối ưu truy vấn (query planner/optimizer)** cần thống kê về dữ liệu. PostgreSQL thu thập các thống kê như tỷ lệ NULL, số giá trị phân biệt ước lượng, **most-common values (MCV)**, **histogram bounds** và **correlation** giữa thứ tự giá trị với vị trí vật lý. Đây là cơ sở để ước lượng *selectivity* (tỷ lệ hàng thỏa điều kiện), *cardinality* (số hàng dự kiến ở từng bước) và chi phí các phương án truy cập.

Bài học này giải thích từng thống kê, cách đọc `pg_stats`, cách chúng tác động đến `EXPLAIN`, vì sao ước lượng sai khi hai cột có tương quan, cách dùng `CREATE STATISTICS` và quy trình chẩn đoán khi dữ liệu thay đổi khiến planner đưa ra lựa chọn không phù hợp.

> **Phân biệt quan trọng:** `correlation` trong `pg_stats` thường mô tả **tương quan giữa thứ tự giá trị một cột và vị trí vật lý của hàng trong bảng**. Nó **không** phải chỉ số cho biết hai cột `tenant_id` và `status` phụ thuộc nhau. Tương quan/phụ thuộc **giữa các cột** là bài toán khác, có thể được mô hình hóa bằng *extended statistics*.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả vai trò của thống kê cột đối với cardinality và cost estimation.
2. Giải thích `ANALYZE` thu thập dữ liệu mẫu và vì sao thống kê không phải bảng đếm chính xác theo thời gian thực.
3. Đọc các trường `null_frac`, `avg_width`, `n_distinct`, `most_common_vals`, `most_common_freqs`, `histogram_bounds` và `correlation` trong `pg_stats`.
4. Phân biệt MCV với histogram; hiểu vì sao giá trị xuất hiện trong MCV không cần lặp trong histogram.
5. Biết cách suy luận định tính về `=`, `IN`, so sánh phạm vi và `IS NULL` dựa trên phân bố dữ liệu.
6. Hiểu giá trị âm của `n_distinct` và ước lượng số distinct thay đổi theo số hàng.
7. Hiểu tương quan vật lý ảnh hưởng chi phí index scan, khác với dependency giữa các cột.
8. Nhận biết khi nào cần `CREATE STATISTICS ... (dependencies, ndistinct, mcv)`.
9. Chẩn đoán stale statistics, data skew, prepared statement generic plan và query có ước lượng sai.
10. Đánh giá kế hoạch bằng `EXPLAIN (ANALYZE, BUFFERS)`, cập nhật thống kê đúng cách và không thay đổi cấu hình mù quáng.

## 2. Planner cần biết gì trước khi chọn kế hoạch?

Giả sử bảng `events` có 10 triệu hàng. Một truy vấn:

```sql
SELECT event_id, created_at
FROM events
WHERE tenant_id = 10
  AND status = 'paid'
  AND created_at >= TIMESTAMPTZ '2026-11-01 00:00+00'
ORDER BY created_at DESC
LIMIT 20;
```

Planner phải quyết định giữa các phương án như:

- Quét tuần tự cả bảng và lọc.
- Dùng B-tree index để tìm các khóa phù hợp.
- Kết hợp một số index bằng bitmap.
- Sử dụng thứ tự index để tránh `Sort`, đặc biệt với `LIMIT`.
- Trong query có JOIN, chọn hash join, merge join hoặc nested loop, đồng thời quyết định thứ tự JOIN.

Để so sánh chi phí, planner cần ước lượng:

| Câu hỏi của planner | Thống kê có liên quan |
| --- | --- |
| Bảng có khoảng bao nhiêu hàng? | `pg_class.reltuples` và thông tin kích thước relation. |
| Giá trị `status='paid'` thường xuất hiện bao nhiêu? | `most_common_vals` / `most_common_freqs`; `n_distinct` khi cần. |
| Có bao nhiêu hàng có `status IS NULL`? | `null_frac`. |
| `created_at >= cutoff` chọn bao nhiêu phần trăm? | Histogram, MCV khi có, thống kê phân bố và ước lượng của planner. |
| Hai điều kiện trên tenant và region có phụ thuộc nhau? | Có thể cần extended statistics. |
| Truy cập qua index có đọc heap theo cách ngẫu nhiên hay gần tuần tự? | `correlation`, số trang, cấu hình chi phí và các thuộc tính kế hoạch. |
| Một hàng trung bình rộng bao nhiêu? | `avg_width`, thông tin kích thước và width của các biểu thức. |
| Sau filter/JOIN còn bao nhiêu hàng? | Kết hợp selectivity estimates và metadata có liên quan. |

### 2.1. Selectivity và cardinality

**Selectivity** của một predicate được hiểu là phần hàng ước lượng sẽ thỏa điều kiện. Trong ví dụ đơn giản:

\[
\operatorname{selectivity} \approx
\frac{\text{số hàng thỏa điều kiện}}{\text{tổng số hàng}}
\]

Nếu bảng có 100.000 hàng, dự đoán 2% thỏa điều kiện:

\[
\operatorname{estimated\_rows}
\approx 100000 \times 0.02 = 2000
\]

Đây chỉ là mô hình trực giác. Trong truy vấn thực, PostgreSQL còn tính đến kích thước quan hệ, join clauses, giới hạn, đặc điểm hàm/toán tử, thống kê nhiều cột và nhiều phép biến đổi của optimizer.

### 2.2. Estimate khác actual

`EXPLAIN` có thể hiển thị:

```text
Seq Scan on events  (cost=... rows=500 width=...)
  Filter: (status = 'paid')
```

`rows=500` là **ước lượng của planner** cho node đó. Không phải PostgreSQL đã quét và đếm chính xác 500 hàng khi chỉ chạy `EXPLAIN`.

Với:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM events
WHERE status = 'paid';
```

PostgreSQL **thực thi truy vấn**, sau đó báo số hàng thực tế, thời gian và buffers. Khi dữ liệu lệch mạnh hoặc thống kê lỗi thời, estimated rows và actual rows có thể chênh lệch đáng kể.

Không thay `EXPLAIN` bằng `EXPLAIN ANALYZE` tùy tiện với các statement ghi dữ liệu: `ANALYZE` trong `EXPLAIN` sẽ thực sự chạy câu lệnh.

## 3. Nguồn thống kê của PostgreSQL

PostgreSQL lưu thống kê phục vụ planner trong catalog nội bộ, nổi bật là `pg_statistic`. Giao diện thân thiện cho người dùng là view **`pg_stats`**.

```sql
SELECT
    schemaname,
    tablename,
    attname,
    null_frac,
    avg_width,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    histogram_bounds,
    correlation
FROM pg_stats
WHERE schemaname = 'public'
  AND tablename = 'events'
ORDER BY attname;
```

Ở đây `public.events` chỉ là bảng giả định để giới thiệu; từ phần 4 ta tạo một bảng lab cụ thể.

### 3.1. pg_stats không phải pg_stat_user_tables

Hai nhóm view thường bị nhầm:

| Nguồn | Mục đích |
| --- | --- |
| `pg_stats` | Phân bố giá trị của **từng cột**: null_frac, MCV, histogram, correlation... |
| `pg_stats_ext` | Thống kê **nhiều cột** từ các statistics objects, khi phiên bản hỗ trợ. |
| `pg_stat_user_tables` | Thống kê hoạt động bảng: scan counts, tuple changes, thời điểm ANALYZE/vacuum... |
| `pg_class` | Metadata relation, gồm ước lượng `reltuples` và `relpages`. |
| `pg_statistic` | Catalog thống kê nội bộ, không phải điểm truy cập đầu tiên cho người học. |

Tên có tiền tố `pg_stat` không có nghĩa mọi view đều cập nhật mỗi lần query. `pg_stats` cho thấy kết quả thu thập từ `ANALYZE`, còn các view hoạt động có chu kỳ và cơ chế thống kê riêng.

### 3.2. Thống kê không phải giá trị SQL bất biến

Ví dụ `n_distinct=100` là **ước lượng**, không phải unique constraint. Khi thêm nhiều hàng sau ANALYZE, giá trị thống kê có thể không theo kịp, dù index và dữ liệu thực đã thay đổi.

### 3.3. Quyền truy cập

`pg_stats` được thiết kế để chỉ cho người dùng đọc thống kê những bảng họ có quyền phù hợp, tránh một số rò rỉ thông tin từ bảng không được phép truy cập. Ngược lại, một quản trị viên giám sát vẫn cần cẩn thận: MCV của cột nhạy cảm có thể lộ những **giá trị dữ liệu thật** nếu chép nguyên view vào log hoặc ticket công khai.

## 4. Dựng dữ liệu lab có phân bố lệch và tương quan

Ta tạo 50.000 sự kiện giả định. Dataset có:

- `tenant_id=1` xuất hiện thường xuyên hơn các tenant khác.
- `region='north'` liên hệ mạnh với `tenant_id=1`.
- `status` phân bố không đều giữa tenant/region.
- `promo_code` phần lớn là NULL.
- `amount` chủ yếu ở mức thấp nhưng có một tỷ lệ nhỏ giá trị lớn.
- `created_at` tăng cùng thứ tự chèn, để có tương quan vật lý đáng quan sát.

Chỉ chạy trong một **database thực hành**; không thêm dữ liệu vào bảng production.

### 4.1. Tạo schema và bảng

```sql
CREATE SCHEMA IF NOT EXISTS query_stats_lab;

CREATE TABLE query_stats_lab.events (
    event_id bigint PRIMARY KEY,
    tenant_id integer NOT NULL,
    region text NOT NULL,
    status text NOT NULL,
    customer_id bigint NOT NULL,
    amount numeric(12, 2) NOT NULL,
    created_at timestamptz NOT NULL,
    promo_code text
);
```

### 4.2. Tạo dữ liệu theo quy luật

```sql
INSERT INTO query_stats_lab.events
    (event_id, tenant_id, region, status,
     customer_id, amount, created_at, promo_code)
SELECT
    g::bigint AS event_id,
    CASE
        WHEN g % 10 < 7 THEN 1
        ELSE 2 + (g % 9)
    END AS tenant_id,
    CASE
        WHEN g % 10 < 7 THEN 'north'
        ELSE 'south'
    END AS region,
    CASE
        WHEN g % 10 < 7 THEN
            CASE WHEN g % 5 < 4 THEN 'paid'
                 ELSE 'pending' END
        ELSE
            CASE WHEN g % 3 = 0 THEN 'paid'
                 ELSE 'cancelled' END
    END AS status,
    100000 + (g % 30000) AS customer_id,
    CASE
        WHEN g % 100 < 3 THEN 5000 + (g % 3000)
        ELSE 50 + (g % 500)
    END::numeric(12, 2) AS amount,
    TIMESTAMPTZ '2025-01-01 00:00+00'
        + (g * INTERVAL '1 minute') AS created_at,
    CASE
        WHEN g % 20 = 0 THEN 'PROMO-' || (g % 11)::text
        ELSE NULL
    END AS promo_code
FROM generate_series(1, 50000) AS series(g);
```

Chèn một lần trên bảng rỗng. Nếu chạy lại, primary key trên `event_id` báo lỗi trùng. Các giá trị được sinh có quy luật nhân tạo để dễ tái hiện; **không dùng phân bố này để suy luận kết quả kinh doanh thực tế**.

### 4.3. Kiểm tra dữ liệu logic

```sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (WHERE tenant_id = 1) AS tenant_1_rows,
    COUNT(*) FILTER (WHERE region = 'north') AS north_rows,
    COUNT(*) FILTER (WHERE promo_code IS NULL) AS no_promo_rows,
    MIN(created_at) AS earliest_event,
    MAX(created_at) AS latest_event
FROM query_stats_lab.events;
```

Với đúng câu `generate_series(1,50000)`, các giá trị được thiết kế:

| Đại lượng | Số hàng |
| --- | ---: |
| Tổng số sự kiện | 50.000 |
| `tenant_id=1` | 35.000 (70%) |
| `region='north'` | 35.000 (70%) |
| `promo_code IS NULL` | 47.500 (95%) |

Việc `tenant_id=1` và `region='north'` xuất hiện **trên cùng các hàng** có ý nghĩa quan trọng cho phần extended statistics.

### 4.4. Xem phân bố thực bằng GROUP BY

```sql
SELECT
    status,
    COUNT(*) AS actual_rows,
    ROUND(
        COUNT(*)::numeric * 100
            / SUM(COUNT(*)) OVER (),
        2
    ) AS actual_percent
FROM query_stats_lab.events
GROUP BY status
ORDER BY actual_rows DESC;
```

Đây là phép đếm trên dữ liệu thật, **khác** với việc đọc MCV ước lượng từ sampling.

Kiểm tra phân bố joint:

```sql
SELECT
    tenant_id,
    region,
    status,
    COUNT(*) AS actual_rows
FROM query_stats_lab.events
GROUP BY tenant_id, region, status
ORDER BY actual_rows DESC, tenant_id, region, status;
```

### 4.5. Thêm index phục vụ thí nghiệm về plan

```sql
CREATE INDEX idx_events_tenant_status_time
ON query_stats_lab.events
    (tenant_id, status, created_at DESC);

CREATE INDEX idx_events_created
ON query_stats_lab.events (created_at);

CREATE INDEX idx_events_amount
ON query_stats_lab.events (amount);
```

Index là **đường truy cập**; thống kê là **thông tin giúp chọn đường truy cập**. Tạo index không thay thế ANALYZE, và tăng statistics target không tự tạo index.

### 4.6. ANALYZE bảng lab

```sql
ANALYZE query_stats_lab.events;
```

Đây là bước then chốt để PostgreSQL thu thập thống kê sau khi có dữ liệu. Nếu chưa ANALYZE, planner có thể dùng thông tin rất hạn chế hoặc estimate mặc định/ban đầu; tùy autovacuum chạy lúc nào, stats có thể tự được thu thập sau đó, nhưng trong bài thực hành ta chủ động gọi ANALYZE để dễ quan sát.

## 5. ANALYZE thu thập thống kê như thế nào?

`ANALYZE` lấy mẫu dữ liệu và ước lượng phân bố. Với bảng rất lớn, PostgreSQL thường **không cần quét và lưu mọi giá trị của mọi hàng** chỉ để tính histogram/MCV. Thuật toán lấy mẫu, kích thước mẫu và chi tiết nội bộ có thể thay đổi giữa các major PostgreSQL.

### 5.1. ANALYZE không giống VACUUM

```sql
ANALYZE query_stats_lab.events;
```

Mục đích chính là cập nhật thống kê cho optimizer.

```sql
VACUUM (ANALYZE) query_stats_lab.events;
```

Chạy VACUUM và thu thập thống kê. Nhưng:

- `ANALYZE` **không** xóa dead tuples như VACUUM.
- `VACUUM` không phải điều kiện bắt buộc để thu thập phân bố cột.
- Cần chọn thao tác theo mục tiêu: lỗi estimate thường dẫn tới kiểm tra ANALYZE trước, trong khi bloat/MVCC cleanup cần phân tích VACUUM riêng.

### 5.2. ANALYZE lấy mẫu, không cam kết giá trị tuyệt đối

Với `status` chỉ có vài giá trị, mẫu có thể phản ánh tỷ lệ tương đối tốt. Với các giá trị hiếm, phân bố lệch mạnh hoặc nhiều giá trị distinct, mẫu có thể bỏ sót giá trị quan trọng. Các ước lượng từ hai lần ANALYZE có thể hơi khác nhau.

Không viết ứng dụng nghiệp vụ dựa vào `pg_stats.most_common_freqs` để tính doanh số/tỷ lệ khách hàng **chính xác**. Dùng `SELECT COUNT(*)`/aggregation đúng trên dữ liệu khi cần số liệu nghiệp vụ chính thức.

### 5.3. Các bước nhìn thấy công việc ANALYZE

```sql
ANALYZE VERBOSE query_stats_lab.events;
```

`VERBOSE` cho PostgreSQL báo thêm thông tin về xử lý thống kê theo phiên bản và client. Không sao chép một dòng output làm chuẩn mọi PostgreSQL major.

### 5.4. ANALYZE tác động đến kế hoạch, không làm dữ liệu thay đổi

Khi ANALYZE xong, dữ liệu nghiệp vụ của bảng không bị đổi chỉ vì thu thập statistics. Tuy nhiên cùng một câu SELECT có thể nhận plan khác vì planner **ước lượng số hàng và chi phí khác**.

Điều này giải thích vì sao đôi khi một query "đột nhiên nhanh lên" sau ANALYZE mà không cần thêm index. Ngược lại, khi stats sampling chưa đại diện một phân bố quá lệch, ANALYZE đơn thuần chưa chắc đủ giải quyết.

## 6. Các trường cơ bản của pg_stats

Truy vấn mẫu:

```sql
SELECT
    attname,
    null_frac,
    avg_width,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    histogram_bounds,
    correlation
FROM pg_stats
WHERE schemaname = 'query_stats_lab'
  AND tablename = 'events'
ORDER BY attname;
```

Bảng diễn giải:

| Trường | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `attname` | Tên cột được thống kê. | Một cột có thể chưa có entry nếu chưa ANALYZE/không thu thập stats. |
| `null_frac` | Ước lượng tỷ lệ giá trị NULL. | Thường trong khoảng 0 đến 1. |
| `avg_width` | Độ rộng trung bình ước lượng của dữ liệu cột, tính bằng byte theo cơ chế thống kê. | Không phải số ký tự trung bình với Unicode. |
| `n_distinct` | Số giá trị phân biệt ước lượng hoặc tỷ lệ âm so với số hàng. | Âm không nghĩa là số distinct âm. |
| `most_common_vals` | Danh sách các giá trị xuất hiện thường xuyên. | Có thể NULL nếu không có MCV list. |
| `most_common_freqs` | Tần suất ước lượng khớp thứ tự các giá trị MCV. | Tỷ lệ trên tập hàng của relation, không phải chỉ hàng non-NULL. |
| `histogram_bounds` | Các mốc biên chia phân bố giá trị **ngoài MCV** thành những khoảng gần đều số quan sát. | Không nhất thiết có cho mọi cột. |
| `correlation` | Mức tương quan của thứ tự cột với thứ tự vật lý hàng. | Không phải độ phụ thuộc giữa hai cột. |

Ngoài ra `pg_stats` còn có `inherited` và một số trường đặc thù cho arrays/ranges hoặc những loại thống kê khác, tùy kiểu dữ liệu và phiên bản.

### 6.1. Có thể thấy NULL ở chính các trường pg_stats

Nếu `histogram_bounds IS NULL`, không thể kết luận dữ liệu cột không có phân bố. PostgreSQL có thể không thấy histogram hữu ích, cột có ít giá trị distinct, các giá trị chủ yếu nằm trong MCV, statistics target hạn chế, hoặc chưa có thống kê.

Tương tự `correlation` có thể NULL nếu dữ liệu/kiểu toán tử không cho phép tính thống kê phù hợp hoặc không đủ thông tin.

### 6.2. Tỷ lệ ước lượng không phải ràng buộc

Nếu `null_frac=0`, không có nghĩa cột được ràng buộc `NOT NULL`. Nó có thể chỉ là mẫu hiện tại không có NULL. Chỉ `NOT NULL`, constraint phù hợp hoặc cấu trúc dữ liệu mới thể hiện quy tắc được database kiểm soát.

Nếu `n_distinct=-1`, không có nghĩa cột đã được đảm bảo `UNIQUE`. Nó mô tả ước lượng distinct, không phải unique constraint thực thi.

## 7. null_frac: tỷ lệ giá trị thiếu

Trong bảng lab, `promo_code` có NULL ở khoảng 95% hàng. Sau ANALYZE:

```sql
SELECT
    attname,
    null_frac
FROM pg_stats
WHERE schemaname = 'query_stats_lab'
  AND tablename = 'events'
  AND attname IN ('promo_code', 'status', 'amount');
```

Kỳ vọng:

- `promo_code` có `null_frac` gần **0.95**.
- `status` và `amount` được khai báo NOT NULL nên dữ liệu lab không có NULL.

Planner có thể dùng thông tin này khi ước lượng:

```sql
SELECT COUNT(*)
FROM query_stats_lab.events
WHERE promo_code IS NULL;
```

và:

```sql
SELECT COUNT(*)
FROM query_stats_lab.events
WHERE promo_code IS NOT NULL;
```

### 7.1. Công thức trực giác

Nếu bảng có N hàng và `null_frac=f`:

\[
\operatorname{rows}(col\ IS\ NULL) \approx Nf
\]

\[
\operatorname{rows}(col\ IS\ NOT\ NULL) \approx N(1-f)
\]

Với 50.000 hàng và `f≈0.95`:

```text
IS NULL     ~47,500 hàng
IS NOT NULL ~ 2,500 hàng
```

Thực tế có thể khác do sampling, stale statistics, snapshot và các phép biến đổi khác.

### 7.2. NULL không nằm trong MCV như một giá trị thông thường

Tỷ lệ NULL được thống kê riêng ở `null_frac`. Đừng tìm một chuỗi `'NULL'` trong `most_common_vals` rồi coi đó là NULL SQL. Chuỗi text `'NULL'` là dữ liệu bình thường, còn `NULL` SQL biểu thị giá trị không biết/không có.

Truy vấn `WHERE promo_code = NULL` cũng không phải cách đếm NULL; phải dùng `IS NULL`.

## 8. avg_width: vì sao độ rộng hàng ảnh hưởng kế hoạch?

Giả sử hai query cùng dự đoán trả 100.000 hàng:

```sql
SELECT event_id
FROM query_stats_lab.events;

SELECT *
FROM query_stats_lab.events;
```

Query thứ hai có thể cần chuyển và xử lý dữ liệu rộng hơn; các operator như Sort, Hash Join hoặc HashAggregate có thể nhạy với kích thước tuple trung gian. `avg_width` giúp planner ước lượng kích thước các dữ liệu tương ứng.

### 8.1. avg_width không phải kích thước file trên đĩa

Với cột `text` hoặc `numeric`, độ rộng trong statistics không đồng nhất hoàn toàn với kích thước row trong heap, TOAST storage, overhead của page hay kích thước index. Do đó không thể cộng `avg_width` của vài cột rồi coi là `pg_relation_size(table)`.

Muốn đo kích thước file vật lý, dùng các hàm khác:

```sql
SELECT
    pg_size_pretty(
        pg_relation_size('query_stats_lab.events')
    ) AS heap_size,
    pg_size_pretty(
        pg_total_relation_size('query_stats_lab.events')
    ) AS total_size;
```

### 8.2. Chọn cột trả về cũng là một phần hiệu năng

Một query `SELECT *` thường tốn mạng/deserialize hơn query chỉ lấy cột cần thiết. Tuy nhiên không nên suy luận mọi query `SELECT *` chắc chắn dùng seq scan; planner còn xét filter, index, số hàng và row width.

## 9. n_distinct: số giá trị khác nhau ước lượng

`n_distinct` là một trong những trường dễ bị hiểu sai nhất vì có thể mang dấu âm.

### 9.1. Giá trị dương

Nếu `n_distinct = 5`, PostgreSQL ước lượng có khoảng **5 giá trị phân biệt** trong cột của relation. Không phải cam kết luôn chính xác tuyệt đối; dữ liệu và thống kê có thể thay đổi.

`status` trong lab chỉ thuộc ba trạng thái `paid`, `pending`, `cancelled`. Vì vậy nếu mẫu đủ đại diện, `n_distinct` thường phản ánh khoảng 3 giá trị.

### 9.2. Giá trị âm

PostgreSQL dùng `n_distinct` âm để biểu diễn **tỷ lệ số distinct so với số hàng** khi số distinct dự kiến tăng cùng kích thước relation.

Ví dụ giả định:

| `n_distinct` | Ý nghĩa thực dụng khi bảng có N hàng |
| ---: | --- |
| `100` | Khoảng 100 giá trị distinct. |
| `-1` | Số giá trị distinct xấp xỉ N. |
| `-0.5` | Số distinct xấp xỉ 0.5 × N. |
| `-0.1` | Số distinct xấp xỉ 0.1 × N. |

Đây là cách biểu diễn **ước lượng tăng theo relation size**, không phải một phép đếm số âm.

### 9.3. Đối chiếu với dữ liệu thật

```sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(DISTINCT tenant_id) AS actual_tenants,
    COUNT(DISTINCT status) AS actual_statuses,
    COUNT(DISTINCT customer_id) AS actual_customers,
    COUNT(DISTINCT created_at) AS actual_timestamps
FROM query_stats_lab.events;
```

Và statistics:

```sql
SELECT attname, n_distinct
FROM pg_stats
WHERE schemaname = 'query_stats_lab'
  AND tablename = 'events'
  AND attname IN (
      'tenant_id', 'status', 'customer_id', 'created_at'
  )
ORDER BY attname;
```

Hai truy vấn trả những đại lượng **khác phương pháp**: GROUP BY/COUNT truy vấn dữ liệu thực, `pg_stats` trả estimate từ lần ANALYZE.

### 9.4. n_distinct và equality selectivity

Khi điều kiện `col = value` **không** thuộc MCV list, planner có thể dựa vào phần tần suất còn lại, `n_distinct` và thông tin khác để ước lượng. Trực giác đơn giản trong dữ liệu phân bố đều không có NULL:

\[
P(col=x) \approx \frac{1}{\text{number of distinct values}}
\]

Nhưng với dữ liệu lệch, lấy 1/`n_distinct` cho mọi giá trị là sai. Đó là lý do PostgreSQL cần MCV.

## 10. Most-common values (MCV): giá trị phổ biến

MCV là tập những giá trị xuất hiện đủ thường xuyên để đáng lưu thống kê riêng, đi kèm một mảng tần suất tương ứng.

```sql
SELECT
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs
FROM pg_stats
WHERE schemaname = 'query_stats_lab'
  AND tablename = 'events'
  AND attname IN ('tenant_id', 'region', 'status', 'promo_code')
ORDER BY attname;
```

### 10.1. Cách ghép values và frequencies

Ví dụ minh họa (không phải output cam kết từ sampling):

```text
most_common_vals  = {paid,pending,cancelled}
most_common_freqs = {0.70,0.10,0.20}
```

Thành phần cùng vị trí trong hai mảng tương ứng cùng một giá trị:

- `paid` → 70%.
- `pending` → 10%.
- `cancelled` → 20%.

Với `status` không NULL, tổng gần 1 nếu cả ba giá trị được lưu trong MCV. Nếu chỉ một phần giá trị có trong MCV hoặc có NULL, tổng mảng frequencies có thể **nhỏ hơn 1**.

### 10.2. Tần suất là tỷ lệ toàn bộ hàng

Ví dụ một bảng giả định có:

| Giá trị | Số hàng |
| --- | ---: |
| `paid` | 600 |
| `pending` | 200 |
| `cancelled` | 100 |
| `NULL` | 100 |
| **Tổng** | **1000** |

Khi đó:

- `null_frac = 0.1`.
- Nếu các trạng thái có trong MCV, tần suất tương ứng khoảng `0.6`, `0.2`, `0.1`.
- Tổng MCV = `0.9`, cộng null_frac = `1`.

**Không chia thêm frequencies cho (1 - null_frac)** nếu đang muốn biết tỷ lệ trong toàn bảng. Nếu cần tỷ lệ có điều kiện trên non-NULL, khi ấy mới chuẩn hóa theo tập non-NULL và giải thích rõ mẫu số.

### 10.3. Equality lookup của một giá trị phổ biến

```sql
SELECT event_id, created_at
FROM query_stats_lab.events
WHERE status = 'paid';
```

Nếu `paid` có tần suất rất cao, PostgreSQL có thể ước lượng rất nhiều hàng. Dùng index cho một predicate trả phần lớn bảng có thể gây đọc heap ngẫu nhiên nhiều hơn việc sequential scan; planner có thể chọn seq scan dù có index trên status.

### 10.4. Equality lookup của một giá trị hiếm

```sql
SELECT event_id, created_at
FROM query_stats_lab.events
WHERE status = 'cancelled';
```

Nếu cancelled hiếm hơn nhiều, một index phù hợp có thể đáng giá hơn. Nhưng không phải bất cứ tần suất nào nhỏ cũng bảo đảm Index Scan: cần xét query trả bao nhiêu cột, table size, cache, index layout và chi phí dự kiến.

### 10.5. MCV không chứa mọi giá trị

Nếu cột có hàng triệu giá trị distinct, PostgreSQL chỉ lưu một số giá trị được xem là phổ biến theo statistics target và sampling; **những giá trị không nằm trong MCV không tự có tần suất 0**.

Khi không tìm thấy giá trị trong MCV, planner dùng giả định/ước lượng khác cho phần giá trị còn lại.

### 10.6. Giá trị mới có thể chưa được đại diện

Giả sử sau lần ANALYZE, ứng dụng đổ vào hàng triệu sự kiện với trạng thái mới `'queued'`. `pg_stats` cũ chưa biết phân bố queued; kế hoạch dựa trên stats cũ có thể ước lượng sai. Cần xem thời điểm ANALYZE và mức biến động của dữ liệu, không chỉ đọc MCV một lần.

## 11. Histogram: các ranh giới phân vị của phần còn lại

Một MCV list hữu ích với giá trị rời rạc lặp lại thường xuyên. Nhưng với `amount` hoặc `created_at` có nhiều giá trị khác nhau, planner còn cần mô hình hóa **vị trí các giá trị trên trục số/thời gian** để ước lượng những phép so sánh phạm vi.

Đây là vai trò của **`histogram_bounds`**.

```sql
SELECT
    attname,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    histogram_bounds
FROM pg_stats
WHERE schemaname = 'query_stats_lab'
  AND tablename = 'events'
  AND attname IN ('created_at', 'amount')
ORDER BY attname;
```

### 11.1. Histogram không chia khoảng bằng độ rộng

Giả sử một tập 1.000 giá trị tập trung nhiều ở 0–10 và rất ít ở 100–1000.

**Histogram theo ranh giới phân vị gần đều số quan sát** sẽ đặt nhiều mốc ở khu vực dày dữ liệu và ít mốc ở khu vực thưa dữ liệu.

```text
Trục giá trị tăng dần

0  1  2  3  4    8       100                  1000
|--|--|--|--|----|--------|---------------------|
  ^ nhiều ranh giới gần nhau ở vùng dày dữ liệu
                        ^ khoảng ranh giới thưa hơn ở vùng ít dữ liệu
```

Không nên đọc `histogram_bounds` là “mỗi khoảng có cùng bề rộng”. Mục đích thông thường là chia số lượng quan sát thành các phần có xác suất gần nhau, **không phải các đoạn số học bằng nhau**.

### 11.2. Histogram của PostgreSQL thường loại MCV

Đây là điểm quan trọng:

> **`histogram_bounds` được xây dựng cho những giá trị không thuộc MCV, không tính NULL.**

Các giá trị quá phổ biến được mô tả riêng trong MCV để tránh làm biến dạng histogram. Khi planner ước lượng một phép so sánh phạm vi, nó có thể kết hợp:

1. Tần suất của những giá trị MCV thỏa điều kiện.
2. Ước lượng phần còn lại từ histogram.
3. Tỷ lệ NULL và những yếu tố thống kê khác.

Do vậy, **không cộng phần trăm của histogram như thể nó biểu diễn đủ 100% hàng**. Nó biểu diễn phân bố phần còn lại sau khi đã tách những trường hợp đặc biệt.

### 11.3. Số mốc histogram

Với statistics target mặc định thường là 100, histogram có thể có tối đa khoảng target+1 ranh giới khi dữ liệu/kiểu cột phù hợp. Không phải mỗi cột luôn có đúng 101 mốc:

- Nếu cột có ít giá trị distinct, MCV có thể đã mô tả gần hết giá trị.
- Với kiểu dữ liệu/toán tử không phù hợp, histogram có thể không có.
- Thống kê target và cách sampling có thể cho danh sách ngắn hơn.
- Một số phiên bản có khác biệt chi tiết thuật toán.

Hãy xem thông tin thực của bảng, không gán mặc định một số điểm cố định cho mọi kết quả `pg_stats`.

### 11.4. Ví dụ histogram theo điểm

Giả sử histogram có 6 ranh giới minh họa:

```text
histogram_bounds = {10, 20, 30, 60, 120, 400}
```

Năm đoạn giữa các mốc gần như có cùng số quan sát **trong tập non-null, non-MCV**:

```text
[10,20], [20,30], [30,60], [60,120], [120,400]
```

Khoảng giá trị lớn dần, nhưng khối lượng quan sát giữa các mốc tương đối cân bằng. Các mốc ở đây **chỉ để minh họa nguyên tắc**, không phải output từ bảng lab.

### 11.5. Ước lượng điều kiện range

Truy vấn:

```sql
SELECT event_id, amount
FROM query_stats_lab.events
WHERE amount >= 1000;
```

Dataset lab có phần lớn amount nhỏ hơn 550 và một số amount từ 5000 trở lên. Histogram và MCV (nếu có) giúp planner nhận biết vùng amount lớn ít xuất hiện hơn, so với giả định phân bố đều từ min đến max.

Truy vấn khác:

```sql
SELECT event_id, created_at
FROM query_stats_lab.events
WHERE created_at >= TIMESTAMPTZ '2025-02-01 00:00+00';
```

Histogram theo created_at giúp planner ước lượng tỷ lệ thời gian nằm sau cutoff. Không có nghĩa planner thực sự đếm từng hàng sau ngày này trong lúc lập kế hoạch.

### 11.6. Interpolation và sai số

Nếu ranh giới điều kiện nằm **giữa hai mốc histogram**, planner có thể dùng nội suy hoặc những hàm selectivity phù hợp với kiểu dữ liệu/toán tử. Cách tính chi tiết không phải công thức chung cho mọi operator hoặc kiểu.

Sai số có thể lớn khi:

- Dữ liệu tập trung bất thường giữa hai mốc.
- Có đỉnh phân bố rất hẹp nhưng không lọt MCV.
- Predicate có correlation với cột khác.
- Giá trị mới xuất hiện sau ANALYZE.
- Một bảng partitioned có các phân vùng phân bố khác nhau.

**Histogram là bản tóm tắt xác suất, không phải index và cũng không phải bản sao dữ liệu.**

## 12. Phân biệt histogram với width_bucket và percentile

Một histogram cho planner khác với histogram thống kê bạn tự dựng trong SQL.

### 12.1. Dựng histogram theo khoảng có độ rộng cố định

```sql
SELECT
    width_bucket(
        amount,
        0::numeric,
        8000::numeric,
        8
    ) AS bucket,
    COUNT(*) AS observations
FROM query_stats_lab.events
WHERE amount >= 0
  AND amount < 8000
GROUP BY bucket
ORDER BY bucket;
```

`width_bucket` ở đây chia khoảng [0,8000) thành tám phần có **độ rộng bằng nhau**. Các bucket có thể có số hàng cực lệch vì phần lớn amount nằm trong đoạn 0–1000.

Ngược lại, `pg_stats.histogram_bounds` chứa các ranh giới được chọn để phản ánh phân bố quan sát với số lượng gần đều, **sau khi tách MCV**.

### 12.2. Percentile là một bài toán khác

```sql
SELECT
    percentile_cont(0.5)
        WITHIN GROUP (ORDER BY amount::double precision)
        AS median_amount,
    percentile_cont(0.95)
        WITHIN GROUP (ORDER BY amount::double precision)
        AS p95_amount
FROM query_stats_lab.events;
```

`percentile_cont` trả ngưỡng phân vị theo **dữ liệu query thực** trong ngữ cảnh chạy SQL; nó không chỉ đọc sẵn mốc `pg_stats.histogram_bounds` như một bảng kết quả kinh doanh chính xác.

Không thể coi một mốc từ `pg_stats` là “giá trị p95 chính thức” nếu chưa nêu định nghĩa, cohort, NULL policy và độ chính xác của sampling.

### 12.3. MCV vs histogram vs percentile

| Công cụ | Trả lời câu hỏi | Mục đích điển hình |
| --- | --- | --- |
| `most_common_vals` | Những giá trị nào xuất hiện thường xuyên? | Planner ước lượng equality/range. |
| `most_common_freqs` | Các giá trị phổ biến có tỷ lệ bao nhiêu? | Planner ước lượng selectivity. |
| `histogram_bounds` | Giá trị không thuộc MCV được phân bố dọc trục như thế nào? | Planner ước lượng range. |
| `width_bucket` | Một hàng thuộc khoảng độ rộng cố định nào? | Báo cáo histogram tùy chỉnh. |
| `percentile_cont/disc` | Ngưỡng giá trị tại phân vị do query tính là bao nhiêu? | Analytics/nghiệp vụ. |

## 13. Correlation: thứ tự vật lý so với thứ tự giá trị

Trong `pg_stats`, `correlation` là đại lượng thường nằm trong khoảng **-1 đến +1**:

- Gần **+1**: cột có xu hướng tăng theo thứ tự vật lý của hàng.
- Gần **-1**: cột có xu hướng giảm theo thứ tự vật lý của hàng.
- Gần **0**: thứ tự vật lý và thứ tự giá trị ít có quan hệ tuyến tính/đơn điệu theo phép đo này.

PostgreSQL có thể dùng thông tin đó để ước lượng mức độ *random heap page access* của một số kế hoạch index scan.

### 13.1. Tại sao tương quan vật lý quan trọng?

Giả sử index B-tree trên `created_at`.

**Trường hợp A: dữ liệu chèn theo thời gian tăng**

```text
Heap page 1: Jan 01 -> Jan 02
Heap page 2: Jan 03 -> Jan 04
Heap page 3: Jan 05 -> Jan 06
...

Index scan theo thời gian:
  gặp heap pages gần nhau
```

**Trường hợp B: dữ liệu chèn ngẫu nhiên theo thời gian**

```text
Heap page 1: Jan 08, Jan 01, Jan 15
Heap page 2: Jan 03, Jan 20, Jan 02
Heap page 3: Jan 11, Jan 05, Jan 17
...

Index scan theo thời gian:
  có thể phải nhảy qua nhiều heap pages
```

Khi nhiều index entries trỏ đến các heap pages gần nhau, index scan theo phạm vi có thể ít I/O ngẫu nhiên hơn. Khi heap hoàn toàn xáo trộn, planner có thể tính chi phí index scan đắt hơn so với cách truy cập khác.

### 13.2. Quan sát correlation trong lab

```sql
SELECT
    attname,
    correlation
FROM pg_stats
WHERE schemaname = 'query_stats_lab'
  AND tablename = 'events'
  AND attname IN (
      'event_id', 'tenant_id', 'status', 'amount', 'created_at'
  )
ORDER BY attname;
```

Vì data generator chèn theo `g` tăng, `event_id` và `created_at` cùng tăng, correlation thường gần **+1** ngay sau lần nạp và ANALYZE trên bảng lab mới.

Ngược lại `status` và `tenant_id` được gán theo modulo/CASE, nên thứ tự vật lý không tăng đơn điệu theo hai cột đó. Correlation của chúng không nhất thiết cao.

**Không hứa kết quả chính xác bằng 1.0000:** dữ liệu hiện hữu, thao tác cập nhật, cách PostgreSQL lấy mẫu và thứ tự chèn thực tế có thể ảnh hưởng thống kê.

### 13.3. Minh họa tương quan âm

Nếu muốn thấy cột thời gian **giảm theo vị trí vật lý**, tạo bảng lab mới theo thứ tự đảo:

```sql
CREATE TABLE query_stats_lab.reverse_events AS
SELECT event_id, created_at
FROM query_stats_lab.events
ORDER BY created_at DESC;

ANALYZE query_stats_lab.reverse_events;

SELECT
    attname,
    correlation
FROM pg_stats
WHERE schemaname = 'query_stats_lab'
  AND tablename = 'reverse_events'
  AND attname IN ('event_id', 'created_at');
```

Trên bảng mới được tạo vật lý theo dữ liệu giảm dần, correlation của `created_at` và `event_id` thường **gần -1**. Thực tế có thể khác một chút tùy cách ghi trang và sampling.

Số **-1 không có nghĩa index vô dụng**. B-tree có thể quét theo chiều phù hợp; điều quan trọng ở đây là thứ tự vật lý vẫn có mối quan hệ mạnh với giá trị cột, chỉ khác chiều.

### 13.4. Index không tự sắp lại bảng heap

Tạo:

```sql
CREATE INDEX idx_reverse_events_created
ON query_stats_lab.reverse_events (created_at);
```

**không tự chuyển các heap rows thành thứ tự index**. Index có trật tự riêng, trong khi thứ tự vật lý của heap chủ yếu phụ thuộc lịch sử ghi/rewrite/CLUSTER.

Trong PostgreSQL, thao tác như `CLUSTER` có thể rewrite dữ liệu theo một index, nhưng nó có ràng buộc lock và bảo trì riêng. Không chạy CLUSTER chỉ để “làm correlation đẹp” mà chưa cân nhắc chi phí và workload.

### 13.5. Correlation không bảo đảm mọi query phải Index Scan

Correlation gần +1 hoặc -1 có thể giảm chi phí ước lượng của index scan theo range, nhưng planner vẫn xét:

- Số hàng phù hợp.
- Số trang heap và index.
- Số cột cần đọc.
- Index-only scan và visibility map.
- `random_page_cost`, `seq_page_cost`, cache assumptions.
- ORDER BY/LIMIT.
- JOIN và toàn bộ cây thực thi.

Không gán giá trị `correlation=0.99` thành quy tắc “chắc chắn sẽ không có Seq Scan”.

## 14. Correlation trong pg_stats không phải dependency giữa hai cột

Một lỗi diễn giải phổ biến:

> “`pg_stats.correlation` của region gần 0, vậy region và tenant_id không liên quan.”

Kết luận ấy **sai**. `pg_stats.correlation` của region đo quan hệ với vị trí vật lý, không phải với tenant.

Trong lab, ta cố ý tạo:

```text
tenant_id = 1  <=> region = 'north'
tenant_id != 1 <=> region = 'south'
```

Tức tenant_id và region có **phụ thuộc dữ liệu rất mạnh**, dù một trong hai có thể không tăng dần cùng thứ tự hàng trong heap.

### 14.1. So sánh ba khái niệm

| Khái niệm | Đối tượng so sánh | Ý nghĩa |
| --- | --- | --- |
| `pg_stats.correlation` | **Giá trị một cột** và **thứ tự vật lý các tuple**. | Ảnh hưởng ước lượng I/O của truy cập heap theo index. |
| Functional dependencies | **Các cột với nhau**, ví dụ tenant_id quyết định region. | Có thể giúp sửa ước lượng khi các predicate equality phụ thuộc nhau. |
| Multivariate MCV | **Các tổ hợp giá trị của nhiều cột** xuất hiện phổ biến. | Giúp ước lượng kết hợp predicate lệch/skew. |

Vì tên “correlation” thường được dùng rộng trong thống kê, cần luôn hỏi: **“Tương quan của đại lượng nào với đại lượng nào?”**

### 14.2. Chứng minh dependency bằng GROUP BY

```sql
SELECT
    tenant_id,
    COUNT(DISTINCT region) AS regions_per_tenant
FROM query_stats_lab.events
GROUP BY tenant_id
ORDER BY tenant_id;
```

Trong data generator, mỗi tenant chỉ nằm ở một region; `COUNT(DISTINCT region)` là 1 cho mỗi tenant.

Ngược lại, region south chứa nhiều tenant, nên dependency có thể có hướng: tenant xác định region, nhưng region south không xác định duy nhất một tenant.

### 14.3. Vì sao điều này làm planner ước lượng sai?

Xét truy vấn:

```sql
SELECT COUNT(*)
FROM query_stats_lab.events
WHERE tenant_id = 1
  AND region = 'north';
```

Tỷ lệ thật trong lab:

```text
P(tenant_id = 1)            = 0.70
P(region = 'north')         = 0.70
P(both)                     = 0.70
```

Nếu một bộ ước lượng giả định độc lập hoàn toàn giữa hai predicate:

\[
P(A\cap B) \approx P(A)\times P(B)
= 0.7\times 0.7=0.49
\]

thì nó dự đoán khoảng **24.500 hàng** thay vì **35.000 hàng**. Đây là **ví dụ minh họa của giả định độc lập**, không phải cam kết plan PostgreSQL sẽ luôn báo rows=24500: optimizer có thể có thông tin khác, đặc biệt sau khi tạo extended statistics.

### 14.4. Sai số có thể khuếch đại qua JOIN

Một sai số ở một filter có thể ảnh hưởng:

- Thứ tự JOIN.
- Lựa chọn nested loop/hash/merge join.
- Kích thước hash table dự kiến.
- Khả năng chọn index scan hoặc seq scan.
- Ước lượng số hàng và chi phí Sort/Aggregate.

Với nhiều bước JOIN, sai số selectivity tích lũy có thể khiến planner chọn plan rất khác phương án tốt nhất.

## 15. Chỉ một cột: selectivity cho =, IN, range và NULL

Để hiểu thống kê, hãy xét từng dạng predicate.

### 15.1. Điều kiện bằng

```sql
SELECT COUNT(*)
FROM query_stats_lab.events
WHERE status = 'paid';
```

Nếu `paid` có trong MCV, planner có ước lượng tần suất riêng. Với giá trị không nằm trong MCV, nó phải phân bổ tần suất còn lại theo giả định phù hợp.

### 15.2. IN và OR

```sql
SELECT COUNT(*)
FROM query_stats_lab.events
WHERE status IN ('paid', 'pending');
```

Với các giá trị khác nhau của cùng cột và điều kiện độc lập theo tập giá trị, trực giác là cộng tần suất từng trạng thái. Planner còn phải tính đến operator, NULL và chuyển đổi nội bộ; đừng khẳng định mọi truy vấn `OR` đều được ước lượng bằng phép cộng đơn giản.

### 15.3. Range

```sql
SELECT COUNT(*)
FROM query_stats_lab.events
WHERE amount >= 5000;
```

Histogram và MCV cho phép ước lượng phần hàng rơi vào vùng giá trị lớn. Với lab, khoảng cao này khá hiếm; query thực có thể cần đọc nhiều ít khác nhau tùy index và cột trả về.

### 15.4. IS NULL

```sql
SELECT COUNT(*)
FROM query_stats_lab.events
WHERE promo_code IS NULL;
```

`null_frac` là đầu mối trực tiếp. Các so sánh như `promo_code = 'PROMO-1'` chỉ xét non-NULL values theo semantics SQL tương ứng.

### 15.5. Biểu thức và hàm

```sql
SELECT COUNT(*)
FROM query_stats_lab.events
WHERE date_trunc('month', created_at)
    = TIMESTAMPTZ '2025-02-01 00:00+00';
```

Khi predicate áp dụng một hàm lên cột, thống kê cột gốc **không phải lúc nào cũng đủ** để planner ước lượng chính xác giá trị biểu thức. Có thể cân nhắc:

- Viết điều kiện dạng range trên cột gốc khi đúng ngữ nghĩa và tương thích index.
- Dùng expression index hoặc expression statistics phù hợp theo phiên bản.
- Thiết kế generated column nếu workload có nhu cầu ổn định và tính toán phù hợp.

Lưu ý `date_trunc` trên `timestamptz` còn phụ thuộc timezone theo cú pháp/phiên bản; không thay nó bằng range mà không định nghĩa ranh giới múi giờ.

## 16. Thống kê nhiều cột: CREATE STATISTICS

PostgreSQL có **extended statistics** để mô tả một số quan hệ giữa nhiều cột mà thống kê một-cột không thể biểu đạt đầy đủ.

Ví dụ:

```sql
CREATE STATISTICS stats_events_tenant_region
    (dependencies, ndistinct, mcv)
ON tenant_id, region
FROM query_stats_lab.events;

ANALYZE query_stats_lab.events;
```

Các kiểu chính:

| Loại | Công dụng |
| --- | --- |
| `dependencies` | Ước lượng phụ thuộc chức năng giữa các cột, giúp sửa một số tình huống lọc kết hợp equality/IN thích hợp. |
| `ndistinct` | Ước lượng số tổ hợp giá trị distinct của nhiều cột, hữu ích cho các ước lượng grouping. |
| `mcv` | Danh sách các **tổ hợp giá trị** phổ biến, giúp ước lượng filter nhiều cột lệch và tương quan. |

### 16.1. Khác với statistics một cột

`pg_stats.most_common_vals` của `tenant_id` có thể biết tenant 1 chiếm 70%; `pg_stats.most_common_vals` của `region` có thể biết north chiếm 70%.

Nhưng hai danh sách riêng lẻ **không cho biết hai tỷ lệ này nằm trên cùng 35.000 hàng**.

Multivariate MCV có thể ghi nhận tổ hợp:

```text
(tenant_id=1, region='north') xuất hiện rất thường xuyên
```

Dependencies có thể ghi nhận hướng tương quan gần như `tenant_id -> region`.

### 16.2. CREATE STATISTICS chỉ tạo đối tượng định nghĩa

Sau `CREATE STATISTICS`, cần `ANALYZE` để PostgreSQL thu thập dữ liệu cho object:

```sql
ANALYZE query_stats_lab.events;
```

Không kỳ vọng `CREATE STATISTICS` tự quét bảng và có ngay MCV mới nếu chưa có lần ANALYZE tương ứng.

### 16.3. Phiên bản hỗ trợ

Extended statistics đã được PostgreSQL bổ sung dần qua các major. Các kiểu `dependencies`/`ndistinct` và multivariate `mcv` không có lịch sử hỗ trợ hoàn toàn giống nhau; ví dụ multivariate MCV có từ PostgreSQL 12. Nếu đang ở một major cũ, kiểm tra cú pháp và các kiểu được hỗ trợ trước khi dùng.

### 16.4. Không tự dùng cho mọi loại JOIN

Extended statistics hữu ích với một số filter và grouping, nhưng PostgreSQL có những **giới hạn planner** về cách sử dụng nó, đặc biệt các ước lượng JOIN phức tạp. Đừng hứa tạo `CREATE STATISTICS` sẽ sửa mọi nested-loop sai hoặc mọi join cardinality estimate.

Phải kiểm tra số rows dự đoán ở **từng plan node** trước/sau, và kết luận trên query thật.

## 17. Xem extended statistics trong pg_stats_ext

Sau khi ANALYZE:

```sql
SELECT
    schemaname,
    tablename,
    statistics_name,
    attnames,
    kinds,
    n_distinct,
    dependencies,
    most_common_vals,
    most_common_freqs
FROM pg_stats_ext
WHERE schemaname = 'query_stats_lab'
  AND tablename = 'events'
ORDER BY statistics_name;
```

Các cột hiện hữu/chi tiết hiển thị có thể thay đổi theo major PostgreSQL, nhất là với expression statistics. Trên các phiên bản hiện đại hỗ trợ `pg_stats_ext`, các trường trên giúp thấy:

- Tên object.
- Danh sách thuộc tính liên quan.
- Loại thống kê đã yêu cầu.
- Phân bố số tổ hợp distinct.
- Dependency coefficients.
- MCV đa biến cùng frequencies.

### 17.1. Phụ thuộc có hướng

Nếu mỗi tenant chỉ thuộc đúng một region:

```text
tenant_id -> region  : dependency mạnh
region -> tenant_id  : có thể yếu hơn
```

Bởi vì region south chứa nhiều tenant. Một dependency coefficient có thể gợi ý sức mạnh quan hệ theo hướng cụ thể; **không đọc đó là tỷ lệ nhân quả**.

### 17.2. MCV combination vs product of individual frequencies

Một bảng phân phối:

| tenant_id | region | Tỷ lệ giả định |
| ---: | --- | ---: |
| 1 | north | 70% |
| 2 | south | 10% |
| 3 | south | 10% |
| 4 | south | 10% |

Từ thống kê một cột:

```text
P(tenant=1) = 0.70
P(north)    = 0.70
```

Nếu nhân độc lập được 0.49; nếu dùng joint MCV biết cặp (1,north) chiếm 0.70, ước lượng có thể gần thực tế hơn.

Bảng trên chỉ là hình minh họa gồm 4 tenant cho dễ tính; dataset lab thực tế có nhiều tenant south tùy modulo.

### 17.3. MCV dựa trên mẫu vẫn có sai số

Danh sách MCV nhiều cột không lưu tất cả những tổ hợp hiếm. Nếu điều kiện nhắm tới một cặp mới xuất hiện sau ANALYZE, planner vẫn có thể ước lượng kém.

Thêm hàng chục statistics objects cũng không thay thế việc cập nhật stats thường xuyên và đo đúng workload.

## 18. Một thí nghiệm so kế hoạch trước và sau extended stats

### 18.1. Trước extended stats

Nếu chưa tạo object ở phần 16, chạy:

```sql
EXPLAIN
SELECT *
FROM query_stats_lab.events
WHERE tenant_id = 1
  AND region = 'north';
```

Ghi lại estimated `rows` ở node filter.

### 18.2. Tạo extended stats và ANALYZE

```sql
CREATE STATISTICS IF NOT EXISTS stats_events_tenant_region
    (dependencies, ndistinct, mcv)
ON tenant_id, region
FROM query_stats_lab.events;

ANALYZE query_stats_lab.events;
```

Đo lại:

```sql
EXPLAIN
SELECT *
FROM query_stats_lab.events
WHERE tenant_id = 1
  AND region = 'north';
```

### 18.3. Tính actual rows

```sql
SELECT COUNT(*)
FROM query_stats_lab.events
WHERE tenant_id = 1
  AND region = 'north';
```

Với bảng lab nguyên trạng, kết quả là **35.000 hàng**.

So sánh estimate với actual. Nếu plan không đổi, không vội kết luận extended stats vô dụng. Có thể trước đó optimizer đã ước lượng đủ tốt hoặc không có sự đổi plan đáng giá; **độ chính xác rows** và **chi phí thực tế** là hai câu hỏi liên quan nhưng không giống nhau.

### 18.4. Vì sao không xem cost giảm là điều kiện thành công duy nhất?

Khi extended stats sửa estimate từ thấp lên gần actual, **estimated cost có thể tăng** vì planner biết truy vấn thực sự xử lý nhiều hàng hơn. Đó có thể là cải thiện quan trọng: nó tránh chọn nested loop hoặc index scan không phù hợp. Đừng coi cost dự đoán càng nhỏ càng đúng.

### 18.5. Giới hạn của thí nghiệm

Dataset 50.000 hàng vẫn khá nhỏ, các giá trị được sinh theo modulo nên không giống workload production. `EXPLAIN ANALYZE`, cache state và máy chủ thực có thể cho số thời gian khác nhau. Bài học ở đây là **đọc estimate và hiểu nguyên nhân sai lệch**, không phải ép PostgreSQL chạy một loại plan cố định.

## 19. n_distinct đa cột và GROUP BY

Một query grouping:

```sql
SELECT
    tenant_id,
    region,
    COUNT(*)
FROM query_stats_lab.events
GROUP BY tenant_id, region;
```

Planner cần ước lượng **số nhóm (tenant_id,region)**. Nếu chỉ biết số distinct tenant và region riêng biệt rồi giả định độc lập, số tổ hợp nhóm có thể bị ước lượng không tốt.

Extended statistics `ndistinct` giúp cung cấp ước lượng số tổ hợp distinct của nhiều cột.

### 19.1. Đếm thật bằng SQL

```sql
SELECT COUNT(*) AS actual_groups
FROM (
    SELECT tenant_id, region
    FROM query_stats_lab.events
    GROUP BY tenant_id, region
) AS groups;
```

So với:

```sql
EXPLAIN
SELECT tenant_id, region, COUNT(*)
FROM query_stats_lab.events
GROUP BY tenant_id, region;
```

Các node aggregation có estimated rows cho số nhóm. Nếu estimated groups sai rất nhiều, kích thước hash aggregate và khả năng spill có thể bị ảnh hưởng.

### 19.2. n_distinct đa cột không phải UNIQUE constraint

Một stats object ghi nhận số tổ hợp distinct không ngăn hai hàng mới có cùng tổ hợp. Nếu muốn cặp `(tenant_id,region)` unique, phải có unique constraint/index phù hợp — nhưng trong lab có 35.000 hàng cùng cặp (1,north), nên **không được tạo unique constraint như vậy**.

Thống kê dự báo dữ liệu hiện có; constraint định nghĩa quy tắc cơ sở dữ liệu phải bảo vệ.

## 20. Statistics target: điều chỉnh độ chi tiết

PostgreSQL có tham số mặc định:

```sql
SHOW default_statistics_target;
```

Giá trị thường gặp là **100**. Statistics target ảnh hưởng mức chi tiết của histogram/MCV và lượng sampling/work khi ANALYZE. Không có nghĩa mỗi cột chứa đúng 100 giá trị hoặc ANALYZE đọc đúng 100 hàng.

### 20.1. Tăng target cho một cột cụ thể

Ví dụ:

```sql
ALTER TABLE query_stats_lab.events
    ALTER COLUMN amount SET STATISTICS 500;

ALTER TABLE query_stats_lab.events
    ALTER COLUMN created_at SET STATISTICS 500;

ANALYZE query_stats_lab.events;
```

Điều này cho phép PostgreSQL thu thập thống kê chi tiết hơn cho các cột `amount` và `created_at`, khi có ích. Nhưng tăng target không hứa query tự nhanh hơn: sampling khác, plan có thể đổi hoặc không, ANALYZE có thể tốn thêm CPU/I/O.

### 20.2. Kiểm tra target đã đặt

```sql
SELECT
    attname,
    attstattarget
FROM pg_attribute
WHERE attrelid = 'query_stats_lab.events'::regclass
  AND attnum > 0
  AND NOT attisdropped
ORDER BY attnum;
```

`attstattarget=-1` thường nghĩa là dùng default statistics target; giá trị dương là override của cột.

### 20.3. Khôi phục mặc định

```sql
ALTER TABLE query_stats_lab.events
    ALTER COLUMN amount SET STATISTICS -1;

ALTER TABLE query_stats_lab.events
    ALTER COLUMN created_at SET STATISTICS -1;

ANALYZE query_stats_lab.events;
```

Đổi target rồi **chưa ANALYZE** thì thống kê đã lưu chưa nhất thiết phản ánh target mới.

### 20.4. Target cao có giải quyết tương quan đa cột?

Không đủ. Tăng target của `tenant_id` và `region` làm mỗi thống kê cột chi tiết hơn, nhưng hai danh sách một cột **vẫn không tự mã hóa rằng tenant=1 và north luôn xuất hiện cùng nhau**.

Nếu sai lệch chính đến từ joint distribution, nên cân nhắc extended MCV/dependencies trước khi chỉ tăng sampling mỗi cột.

### 20.5. Không tăng default cho toàn hệ thống một cách mù quáng

Tăng `default_statistics_target` trên mọi cột của nhiều bảng có thể làm ANALYZE nặng hơn, tăng catalog storage và planning overhead. Nếu lỗi chỉ xảy ra với một vài cột cực skew hoặc query đặc biệt, điều chỉnh cục bộ rồi đo có thể hiệu quả hơn.

## 21. Thống kê lỗi thời (stale statistics)

Planner có thể đưa ra một kế hoạch không phù hợp dù thuật toán ước lượng bình thường là hợp lý, chỉ vì thống kê mô tả **tình trạng cũ của dữ liệu**.

### 21.1. Kịch bản phổ biến

```text
Ngày 1:
  100.000 đơn
  80% paid, 20% pending
  ANALYZE

Ngày 2:
  Import thêm 2.000.000 đơn pending
  Không có ANALYZE kịp thời

Ngày 2, buổi chiều:
  SELECT ... WHERE status = 'pending'

Planner có thể vẫn ước lượng theo phân bố cũ
thay vì tỷ lệ pending mới sau import.
```

Khi một bảng thay đổi rất nhanh, MCV, histogram, null_frac và n_distinct đều có thể trở nên lỗi thời.

### 21.2. Theo dõi ANALYZE của bảng

```sql
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
WHERE schemaname = 'query_stats_lab'
  AND relname = 'events';
```

Diễn giải:

| Trường | Ý nghĩa |
| --- | --- |
| `n_live_tup` | Ước lượng số hàng sống theo thống kê. |
| `n_mod_since_analyze` | Ước lượng số hàng được thay đổi kể từ ANALYZE gần nhất theo cơ chế thống kê. |
| `last_analyze` | Lần ANALYZE thủ công gần nhất đã được ghi nhận. |
| `last_autoanalyze` | Lần autoanalyze gần nhất đã được ghi nhận. |
| `analyze_count` | Số lượt ANALYZE thủ công trong thống kê. |
| `autoanalyze_count` | Số lượt autoanalyze trong thống kê. |

Các giá trị này không phải số đếm chính xác bất biến. Có thể có độ trễ cập nhật, reset thống kê và thay đổi theo transaction/snapshot thống kê. Không dùng `n_mod_since_analyze` như số hàng chính xác đã sửa cho mục đích audit.

### 21.3. Khi nào nên ANALYZE thủ công?

Có thể cân nhắc sau:

- Bulk load rất lớn.
- Import/ETL khiến phân bố cột lệch mạnh.
- Thêm trạng thái nghiệp vụ mới được dùng nhiều.
- Thay đổi phần lớn các giá trị `tenant_id`/`status`.
- Tạo một statistics object mới.
- Nâng statistics target của cột quan trọng.
- Truncate/reload hoặc migration lớn khiến quan hệ thay đổi đặc điểm.

Ví dụ:

```sql
ANALYZE query_stats_lab.events;
```

Không phải lúc nào cũng cần ANALYZE ngay sau từng vài INSERT vì tự động hóa autovacuum/autoanalyze đã được thiết kế để duy trì thống kê theo threshold. Với bulk import lớn mà truy vấn nhạy về plan sẽ chạy ngay sau đó, ANALYZE chủ động thường hữu ích.

### 21.4. Không phải “ANALYZE càng thường xuyên càng tốt”

ANALYZE cũng tốn CPU/I/O, có thể ảnh hưởng workload. Chạy liên tục không làm thống kê trở nên chính xác tuyệt đối hoặc giải quyết mọi vấn đề planning.

Nếu sai số nằm ở **hai cột phụ thuộc nhau** mà chỉ có thông tin một cột, ANALYZE nhiều lần chưa tạo ra dependency stats nếu chưa có statistics object phù hợp.

## 22. Autoanalyze được kích hoạt như thế nào?

Autovacuum launcher/worker của PostgreSQL không chỉ xử lý VACUUM mà còn có thể thực hiện **ANALYZE tự động** khi bảng thay đổi đủ nhiều.

Mô hình cơ bản của ngưỡng kích hoạt autoanalyze:

\[
\text{autoanalyze threshold}
\approx
\text{autovacuum\_analyze\_threshold}
+
\text{autovacuum\_analyze\_scale\_factor}
\times \text{estimated relation rows}
\]

Ví dụ giả định:

- `autovacuum_analyze_threshold=50`.
- `autovacuum_analyze_scale_factor=0.1`.
- Bảng có 100.000 hàng.

Ngưỡng cơ bản là `50 + 0.1 × 100000 = 10050` thay đổi, trong phạm vi những điều kiện thực tế phù hợp.

### 22.1. Xem cấu hình thực tế

```sql
SHOW autovacuum;
SHOW autovacuum_analyze_threshold;
SHOW autovacuum_analyze_scale_factor;
SHOW autovacuum_naptime;
```

Đây là tham số cấu hình. Giá trị có thể được override theo bảng bằng storage parameters; lịch chạy thực còn phụ thuộc tài nguyên, tình trạng server và phiên bản PostgreSQL.

### 22.2. Vì sao một bảng lớn có thể autoanalyze chậm?

Với scale factor cao, **số hàng phải thay đổi** trước khi đạt threshold sẽ tăng theo kích thước bảng. Một bảng có hàng trăm triệu hàng có thể thay đổi hàng triệu bản ghi trước khi autoanalyze theo ngưỡng cơ bản.

Nếu workload rất nhạy với sự thay đổi phân bố của những cột quan trọng, cần theo dõi `n_mod_since_analyze`, độ mới của stats và kế hoạch sau các đợt ETL, rồi tinh chỉnh hợp lý.

### 22.3. Override theo bảng

Ví dụ trong lab:

```sql
ALTER TABLE query_stats_lab.events
SET (
    autovacuum_analyze_threshold = 100,
    autovacuum_analyze_scale_factor = 0.02
);
```

Điều này làm bảng đủ điều kiện autoanalyze theo ngưỡng thấp hơn trong điều kiện phù hợp, **không bảo đảm ANALYZE chạy ngay tức thì**. Nó cũng không thay thế việc xử lý thống kê nhiều cột.

### 22.4. Khôi phục storage parameters trong lab

```sql
ALTER TABLE query_stats_lab.events
RESET (
    autovacuum_analyze_threshold,
    autovacuum_analyze_scale_factor
);
```

Đây là cú pháp DDL thay cấu hình relation; không nên chạy trên bảng production mà không có quyền quyết định và kế hoạch vận hành.

### 22.5. ANALYZE và VACUUM là hai bài toán khác nhau

Hãy phân biệt:

```text
n_mod_since_analyze tăng
   -> dữ liệu đổi, thống kê cho planner có thể lỗi thời

n_dead_tup tăng
   -> nhiều tuple cũ cần cân nhắc VACUUM theo MVCC
```

Cùng một bảng có thể vừa cần ANALYZE để cải thiện ước lượng vừa cần VACUUM để dọn dead tuples. Nhưng thay đổi một ngưỡng không tự giải quyết mục tiêu của ngưỡng kia.

## 23. Sai lệch ước lượng làm đổi kế hoạch JOIN

Giả sử một bảng sự kiện lớn JOIN với bảng khách:

```sql
CREATE TABLE query_stats_lab.customers (
    customer_id bigint PRIMARY KEY,
    customer_group text NOT NULL
);

INSERT INTO query_stats_lab.customers (
    customer_id, customer_group
)
SELECT
    100000 + g,
    CASE WHEN g % 10 = 0 THEN 'vip'
         ELSE 'regular' END
FROM generate_series(0, 29999) AS series(g);

ANALYZE query_stats_lab.customers;
```

Dataset lab có `customer_id` từ 100000 đến 129999. Bảng `events` sử dụng cùng miền ID thông qua modulo.

Query:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    c.customer_group,
    COUNT(*) AS events_count
FROM query_stats_lab.events AS e
JOIN query_stats_lab.customers AS c
    ON c.customer_id = e.customer_id
WHERE e.tenant_id = 1
  AND e.region = 'north'
  AND e.status = 'paid'
GROUP BY c.customer_group;
```

### 23.1. Filter sai có thể ảnh hưởng JOIN

Nếu planner ước lượng số hàng events sau `tenant_id+region+status` quá thấp, nó có thể chọn một cách JOIN thích hợp cho vài chục hàng nhưng không lý tưởng khi thực tế có hàng chục nghìn hàng.

Các yếu tố khác cũng rất quan trọng:

- Kích thước bảng customers.
- Index trên customer_id.
- Số distinct customer_id.
- Bố cục heap/index và cache.
- Workload đồng thời.

Không khẳng định cứ sai estimate là PostgreSQL phải chọn nested loop sai; đây là một **nguy cơ về cost model**, cần xem plan thực tế.

### 23.2. Kiểm tra ước lượng từng bước

Đọc kế hoạch từ dưới lên:

1. Scan `events` còn bao nhiêu hàng dự kiến/thực?
2. Scan `customers` có row estimates đúng không?
3. JOIN tạo bao nhiêu hàng dự kiến/thực?
4. Aggregate dự đoán bao nhiêu nhóm?
5. Có Sort hoặc Hash bị dùng nhiều bộ nhớ/spill không?

Sửa một ước lượng ở tầng scan có thể giúp plan tốt hơn, nhưng không hứa sửa toàn bộ ước lượng join vì extended stats có giới hạn áp dụng.

### 23.3. EXPLAIN ANALYZE đo thực thi, không chỉ đếm rows

Ví dụ:

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT
    c.customer_group,
    COUNT(*)
FROM query_stats_lab.events AS e
JOIN query_stats_lab.customers AS c
    ON c.customer_id = e.customer_id
WHERE e.tenant_id = 1
  AND e.region = 'north'
GROUP BY c.customer_group;
```

`VERBOSE` thêm thông tin node và output. `BUFFERS` giúp nhìn số block hit/read và những thống kê liên quan, nhưng runtime có thể biến động do cache và hoạt động concurrent.

## 24. Đọc EXPLAIN có hệ thống

Giả sử có một output minh họa:

```text
Hash Join  (cost=... rows=250 width=...)
           (actual time=... rows=12000 loops=1)
  Hash Cond: (e.customer_id = c.customer_id)
  -> Seq Scan on events e
       (cost=... rows=300 ...)
       (actual ... rows=14000 loops=1)
       Filter: (...)
  -> Hash
       -> Seq Scan on customers c
```

**Đây là output minh họa để hướng dẫn cách đọc**, không phải kết quả được đo trên schema lab. Ý chính là số `rows` của planner có thể khác `actual rows`.

### 24.1. Phân biệt các thông số

| Thông số | Giải thích |
| --- | --- |
| `cost=startup..total` | Đơn vị chi phí tương đối do planner ước lượng, không phải milliseconds. |
| `rows=N` | Số hàng ước lượng node trả trong một lần thực thi. |
| `width=W` | Kích thước trung bình ước lượng mỗi row, thường tính bằng byte. |
| `actual time` | Thời gian đo khi query chạy với ANALYZE. |
| `actual rows` | Số hàng thực tế trả trong mỗi lần node được gọi, thường hiển thị trung bình theo loops. |
| `loops` | Số lần node được thực thi. |
| `Buffers: shared hit/read` | Số lần truy cập buffer cache hoặc đọc page vào cache được ghi nhận theo node. |

### 24.2. Chú ý loops

Nếu một node `Index Scan` trong nested loop có:

```text
actual rows=2 loops=1000
```

thì tổng số row phát ra qua những lần thực thi có thể khoảng **2.000**. Không nên so trực tiếp `actual rows=2` với `rows=2000` ở node khác mà không xét `loops`.

Tương tự `actual time` thường được báo theo mỗi vòng lặp; tổng thời gian không tính bằng cách cộng cơ học tất cả time của các node cha/con vì thời gian node cha có thể bao gồm thời gian node con.

### 24.3. Vì sao estimated rows quan trọng hơn so cost đơn lẻ?

Nếu estimate thấp 100 lần, root cause có thể ở thống kê. Nếu estimate khá đúng nhưng query vẫn chậm, nguyên nhân có thể là:

- I/O đắt.
- Index không phù hợp.
- Truy xuất rất nhiều hàng là yêu cầu thật.
- Khóa/chờ.
- Sort/hash spill.
- Cấu hình memory và cost không phản ánh phần cứng.

Đừng gọi `ANALYZE` như một “lệnh sửa mọi truy vấn chậm”. Nó chủ yếu cải thiện **thông tin đầu vào cho optimizer**.

### 24.4. Truy vấn có LIMIT

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, created_at
FROM query_stats_lab.events
WHERE tenant_id = 1
  AND status = 'paid'
ORDER BY created_at DESC
LIMIT 10;
```

Số rows của index/filter và cost phải được hiểu cùng cơ chế **dừng sớm** do LIMIT. Một index scan có thể lấy 10 hàng nhanh dù điều kiện phù hợp với rất nhiều hàng; hoặc phải quét nhiều hàng nếu filter nằm sau đoạn index có thứ tự.

Histogram, MCV và correlation có thể ảnh hưởng đến ước lượng số index entries/heap pages cần truy cập trước khi thỏa LIMIT.

## 25. Data skew và kế hoạch prepared statement

Một ứng dụng Java/JDBC thường dùng câu SQL có tham số:

```sql
SELECT event_id, created_at
FROM query_stats_lab.events
WHERE tenant_id = $1
ORDER BY created_at DESC
LIMIT 100;
```

Trong lab:

- Tenant 1 chiếm khoảng 70% hàng.
- Một số tenant khác rất nhỏ.

Vì vậy cùng một SQL có thể có **chi phí thực khác xa theo giá trị tham số**.

### 25.1. Custom plan và generic plan

PostgreSQL có cơ chế lựa chọn giữa:

- **Custom plan:** kế hoạch được lập cho những giá trị tham số cụ thể, có thể sử dụng MCV/skew tương ứng.
- **Generic plan:** một kế hoạch có thể dùng lại cho nhiều lần thực thi, không chuyên biệt hóa theo giá trị tham số như custom plan.

Sử dụng generic plan có thể giảm planning cost, nhưng khi phân bố rất lệch, plan chung có thể không phù hợp cả tenant rất lớn lẫn tenant rất nhỏ.

### 25.2. Thí nghiệm với PREPARE

```sql
PREPARE events_by_tenant(integer) AS
SELECT event_id, created_at
FROM query_stats_lab.events
WHERE tenant_id = $1
ORDER BY created_at DESC
LIMIT 100;
```

Xem custom plan cho hai tenant:

```sql
BEGIN;
SET LOCAL plan_cache_mode = force_custom_plan;

EXPLAIN EXECUTE events_by_tenant(1);
EXPLAIN EXECUTE events_by_tenant(10);

ROLLBACK;
```

Xem generic plan:

```sql
BEGIN;
SET LOCAL plan_cache_mode = force_generic_plan;

EXPLAIN EXECUTE events_by_tenant(1);
EXPLAIN EXECUTE events_by_tenant(10);

ROLLBACK;
```

Kết thúc khi không còn dùng statement:

```sql
DEALLOCATE events_by_tenant;
```

`plan_cache_mode` là tính năng trên các PostgreSQL major hỗ trợ (từ PostgreSQL 12). Việc thiết lập `SET LOCAL` chỉ hiệu lực đến cuối transaction thực hành, tránh giữ thay đổi cấu hình cho session ngoài thí nghiệm.

### 25.3. Không mặc định generic plan là lỗi

Nếu các tenant có phân bố gần đều hoặc plan chung thực hiện đủ nhanh, generic plan có thể rất hợp lý. Không cấu hình ép custom plan toàn hệ thống chỉ vì một query skew.

Tại ứng dụng thật, cần đối chiếu:

- Phần trăm request thuộc tenant lớn/nhỏ.
- Số lần thực thi.
- Planning time và execution time.
- Index có sẵn.
- Generic/custom plan của câu SQL thật.
- Phiên bản PostgreSQL và behavior của driver/server-side prepared statements.

### 25.4. MCV giúp custom plan nhưng không làm generic biết tham số

MCV trên tenant_id có thể biết tenant 1 rất phổ biến. Tuy nhiên trong generic plan, tại thời điểm lập kế hoạch, planner không thể coi `$1` chắc chắn là 1. Đây là **giới hạn thông tin giá trị tham số**, khác với việc thiếu statistics.

Do đó tăng statistics target cũng không nhất thiết giải quyết một generic plan không thể chuyên biệt hóa.

## 26. Thống kê cho biểu thức và index biểu thức

Một query thường gặp:

```sql
SELECT COUNT(*)
FROM query_stats_lab.events
WHERE lower(region) = 'north';
```

Trong lab, region đã là chuỗi lowercase, nhưng hệ thống thực tế có thể cần chuẩn hóa text.

### 26.1. Expression index

```sql
CREATE INDEX idx_events_lower_region
ON query_stats_lab.events (lower(region));

ANALYZE query_stats_lab.events;
```

Index trên biểu thức có thể giúp truy vấn với biểu thức tương ứng; PostgreSQL cũng có thể thu thập thống kê về biểu thức index khi ANALYZE.

Nhưng đừng viết `lower(region)` chỉ để được dùng index nếu region đã chuẩn hóa và query `region='north'` có cùng ngữ nghĩa mong muốn; việc thêm function vào mọi query có thể làm thiết kế phức tạp không cần thiết.

### 26.2. Extended statistics cho biểu thức

Trên các PostgreSQL major hỗ trợ expression statistics (từ PostgreSQL 14), có thể định nghĩa:

```sql
CREATE STATISTICS stats_events_tenant_lower_region
ON tenant_id, (lower(region))
FROM query_stats_lab.events;

ANALYZE query_stats_lab.events;
```

Stats này có thể phục vụ một số ước lượng cho các predicate/expression tương ứng, không tạo index để truy cập dữ liệu. Phiên bản PostgreSQL và khả năng áp dụng trong query cụ thể quyết định hiệu quả.

### 26.3. Không dùng một expression statistics cho mọi biến thể hàm

`lower(region)` khác `upper(region)` hoặc `substr(region,1,3)` về biểu thức và ngữ nghĩa. Một stats object không tự mô hình hóa mọi biểu thức có thể viết trên cột.

Với giá trị thời gian, cũng phải xét timezone nếu tạo biểu thức ngày/tháng từ `timestamptz`; chỉ những biểu thức đáp ứng yêu cầu của kiểu index tương ứng mới được dùng làm index expression.

## 27. Bảng partitioned: local stats và inherited stats

Trong cơ sở dữ liệu lớn, một bảng sự kiện có thể được **partition theo ngày/tháng**. Khi đó:

- Mỗi partition có thể có phân bố dữ liệu riêng.
- Partition pruning làm thay đổi tập dữ liệu cần xét.
- Planner có thể dùng thống kê của từng partition và thống kê bao quát/inherited ở parent trong những tình huống khác nhau.

### 27.1. Vì sao parent stats quan trọng?

Giả sử tenant 1 có phần lớn đơn ở tháng 10, tenant 2 lại có phần lớn đơn ở tháng 11. Một thống kê toàn parent có thể khác rất xa thống kê từng partition. Một query chỉ đọc tháng 11 có selectivity không giống query quét cả năm.

Khi kế hoạch bất thường, xem:

1. Có partition pruning đúng không?
2. Stats của partition được dùng có mới không?
3. Parent/inherited stats có được cập nhật không?
4. Những partitions mới tạo đã được ANALYZE chưa?

### 27.2. ANALYZE parent khi cần

Đối với partitioned table, quá trình autoanalyze parent không nhất thiết được kích hoạt chỉ vì dữ liệu trong các partitions con thay đổi; trong một số tình huống cần chủ động **ANALYZE parent** để có thống kê bao quát phù hợp.

Ví dụ cú pháp với bảng partitioned giả định:

```sql
-- Nếu public.events_partitioned là partitioned table thực:
-- ANALYZE public.events_partitioned;
```

Không chạy ví dụ này trong lab vì chưa tạo `public.events_partitioned`. Ý chính là **statistics maintenance phải xét cả cây partition**, không chỉ một bảng vật lý.

### 27.3. pg_stats.inherited

`pg_stats` có trường `inherited` để phân biệt thống kê liên quan tập dữ liệu có tính kế thừa/partition, tùy quan hệ và phiên bản:

```sql
SELECT
    schemaname,
    tablename,
    attname,
    inherited,
    n_distinct
FROM pg_stats
WHERE schemaname = 'query_stats_lab'
  AND tablename = 'events'
ORDER BY attname, inherited;
```

Với bảng lab thông thường, không nên kỳ vọng có một hàng inherited aggregate như partitioned parent. Trường này được nêu để biết cách đọc stats khi áp dụng vào partitioning/inheritance.

## 28. Đọc thêm thống kê đặc thù arrays và ranges

Ngoài những trường chính, `pg_stats` có các thống kê dành cho một số kiểu dữ liệu:

- `most_common_elems`: những phần tử hay gặp trong các cột array và trường hợp được hỗ trợ khác.
- `most_common_elem_freqs`: tần suất tương ứng của những phần tử phổ biến.
- `elem_count_histogram`: phân bố số phần tử trong array.
- Các trường cho range như `range_length_histogram` và `range_empty_frac` khi phù hợp với kiểu cột.

Ví dụ array tags:

```sql
CREATE TABLE query_stats_lab.tagged_events (
    event_id bigint PRIMARY KEY,
    tags text[] NOT NULL
);

INSERT INTO query_stats_lab.tagged_events (event_id, tags)
VALUES
    (1, ARRAY['postgres', 'sql']),
    (2, ARRAY['postgres', 'index']),
    (3, ARRAY['java']),
    (4, ARRAY['postgres', 'sql']),
    (5, ARRAY['java', 'sql']),
    (6, ARRAY['postgres']);

ANALYZE query_stats_lab.tagged_events;
```

Đọc thống kê nếu cột/operator hỗ trợ:

```sql
SELECT
    attname,
    most_common_elems,
    most_common_elem_freqs,
    elem_count_histogram
FROM pg_stats
WHERE schemaname = 'query_stats_lab'
  AND tablename = 'tagged_events'
  AND attname = 'tags';
```

Không nên ép những thống kê này vào mô hình **một MCV list scalar và một histogram scalar**. Query trên array containment hoặc range operators có những estimator/operator-specific behavior riêng.

### 28.1. Array element occurrence khác số hàng?

Với một mảng chứa cùng phần tử nhiều lần, câu hỏi “phần tử xuất hiện trong bao nhiêu hàng” khác “tổng số lần token xuất hiện trong mọi array”. Thống kê array được thiết kế cho selectivity của các toán tử array phù hợp, không phải phép đếm nghiệp vụ số tag chính xác.

Để báo cáo chính xác, phải truy vấn dữ liệu gốc, ví dụ với `unnest` và aggregation tùy định nghĩa.

## 29. Planner statistics khác execution statistics

Không nên trộn các nhóm dữ liệu sau:

| Nhóm | Ví dụ | Trả lời câu hỏi |
| --- | --- | --- |
| **Column statistics** | `pg_stats` | Dữ liệu cột phân bố ra sao theo ước lượng? |
| **Multivariate statistics** | `pg_stats_ext` | Các cột/biểu thức có quan hệ phân bố chung nào? |
| **Relation metadata** | `pg_class.reltuples`, `relpages` | Relation có khoảng bao nhiêu hàng/trang? |
| **Runtime/activity statistics** | `pg_stat_user_tables` | Bảng được scan/update/analyze bao nhiêu, lần gần nhất? |
| **Per-query execution evidence** | `EXPLAIN (ANALYZE, BUFFERS)` | Query này thực sự chạy plan nào, bao nhiêu hàng/buffers/time? |

### 29.1. reltuples cũng là estimate

```sql
SELECT
    c.relname,
    c.reltuples,
    c.relpages
FROM pg_class AS c
WHERE c.oid = 'query_stats_lab.events'::regclass;
```

`reltuples` và `relpages` không phải counters được cập nhật chính xác mỗi INSERT. PostgreSQL có thể điều chỉnh estimate dựa trên kích thước quan hệ hiện tại và metadata khi lập plan.

### 29.2. Thống kê hệ thống có thể được cache trong transaction

Nếu đang so sánh các lần đọc `pg_stat_*`, cơ chế snapshot/caching của thống kê hoạt động có thể khiến số liệu nhìn thấy chưa đổi ngay trong cùng transaction, tùy phiên bản và thiết lập. Có hàm `pg_stat_clear_snapshot()` để làm mới cách đọc thống kê theo ngữ cảnh phù hợp:

```sql
SELECT pg_stat_clear_snapshot();
```

Đây **không phải** lệnh ANALYZE cột, không cập nhật histogram/MCV và không thay đổi snapshot MVCC của một câu SELECT nghiệp vụ.

## 30. Runbook: điều tra truy vấn chậm do ước lượng sai

Giả sử sau một đợt ETL, query từng chạy trong 100 ms nay mất vài giây. Một cách điều tra có kiểm soát:

### Bước 1. Ghi lại câu SQL và tham số thật

Không chỉ ghi:

```sql
SELECT ... WHERE tenant_id = $1 AND status = $2;
```

Hãy xác định những tham số nào gây chậm, ví dụ tenant rất lớn hay nhỏ, status phổ biến hay hiếm, khung thời gian rộng hay hẹp.

Nếu không có giá trị tham số, dễ bỏ qua data skew và generic/custom planning.

### Bước 2. Xem plan và row estimates

Trong môi trường cho phép:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, created_at, amount
FROM query_stats_lab.events
WHERE tenant_id = 1
  AND status = 'paid'
  AND created_at >= TIMESTAMPTZ '2025-01-15 00:00+00'
ORDER BY created_at DESC
LIMIT 100;
```

Đọc từ node scan đến các node cha, tìm chỗ estimated rows lệch nhiều nhất so với actual. Ghi cả `loops` và thông số buffers.

### Bước 3. Đọc thống kê cột

```sql
SELECT
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    histogram_bounds,
    correlation
FROM pg_stats
WHERE schemaname = 'query_stats_lab'
  AND tablename = 'events'
  AND attname IN ('tenant_id', 'status', 'created_at');
```

Những câu hỏi:

- MCV có phản ánh tenant/status phổ biến không?
- Histogram của created_at có bao phủ thời gian đã nạp không?
- Cột đang có bao nhiêu distinct theo ước lượng?
- Cột thời gian còn tương quan vật lý cao không?
- Predicate có dùng biểu thức khác cột gốc không?

### Bước 4. Kiểm tra độ mới của thống kê

```sql
SELECT
    last_analyze,
    last_autoanalyze,
    n_mod_since_analyze,
    n_live_tup
FROM pg_stat_user_tables
WHERE schemaname = 'query_stats_lab'
  AND relname = 'events';
```

Nếu vừa nạp hoặc thay đổi rất nhiều rows và stats cũ, thực hiện ANALYZE phù hợp trên bảng sau khi đánh giá chi phí.

### Bước 5. Tìm phụ thuộc giữa nhiều cột

```sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (
        WHERE tenant_id = 1
    ) AS tenant_1_rows,
    COUNT(*) FILTER (
        WHERE region = 'north'
    ) AS north_rows,
    COUNT(*) FILTER (
        WHERE tenant_id = 1 AND region = 'north'
    ) AS both_rows
FROM query_stats_lab.events;
```

Nếu tỷ lệ kết hợp lệch xa tích xác suất độc lập, xem `pg_stats_ext` và cân nhắc extended statistics tương ứng với query.

### Bước 6. Đánh giá statistics target cục bộ

Với những cột phân bố phức tạp hoặc nhiều giá trị hiếm quan trọng, target mặc định có thể chưa đủ chi tiết. Cân nhắc tăng target **trên cột cụ thể**, ANALYZE và đo estimate/plan.

Không tăng `default_statistics_target` cho toàn cluster chỉ vì một truy vấn.

### Bước 7. Xem index, caching và chi phí truy cập

Ngay cả với row estimate đúng, query vẫn có thể chậm vì:

- Thiếu index phù hợp.
- Index không khớp ORDER BY/LIMIT.
- Read nhiều heap pages ngẫu nhiên.
- Cột được đọc quá rộng.
- Dữ liệu lớn hơn nhiều so với trước.
- Bloat, I/O contention hoặc lock waits.

`pg_stats.correlation` có thể giải thích một phần chi phí heap access qua index, nhưng cần chứng cứ buffers và plan.

### Bước 8. Kiểm tra prepared query và generic plan

Nếu một tenant rất lớn làm query chậm còn tenant nhỏ nhanh, đối chiếu custom vs generic plan của prepared statement. Đừng dựa vào `EXPLAIN` với literal duy nhất để kết luận plan của ứng dụng luôn giống vậy.

### Bước 9. Theo dõi sau thay đổi

Sau ANALYZE hoặc thêm stats object:

- So estimated rows với actual rows.
- So latency và buffers với baseline.
- Xem các giá trị tham số khác nhau, không chỉ một trường hợp.
- Đo ảnh hưởng đến planning overhead và write workload.
- Ghi lại thay đổi có thể rollback.

### Bước 10. Ghi nhận root cause

Một báo cáo sự cố hữu ích nên phân biệt:

```text
Root cause A: statistics cũ sau bulk load
Root cause B: cột tenant và region có dependency nhưng thiếu extended stats
Root cause C: generic plan không phù hợp tenant lớn
Root cause D: index không khớp lọc/range/order
Root cause E: correlation vật lý giảm sau nhiều UPDATE
Root cause F: thiếu tài nguyên hoặc I/O/lock ngoài planner
```

Các nguyên nhân này có thể cùng tồn tại. Không nên lấy “ANALYZE chạy xong query nhanh hơn” làm bằng chứng duy nhất rằng chẳng có vấn đề nào khác.

## 31. Tình huống thực tế: cùng SQL nhưng hai giá trị tham số rất khác

Một trang quản trị hiển thị các sự kiện của tenant:

```sql
SELECT event_id, created_at, status
FROM query_stats_lab.events
WHERE tenant_id = 1
ORDER BY created_at DESC
LIMIT 100;
```

và:

```sql
SELECT event_id, created_at, status
FROM query_stats_lab.events
WHERE tenant_id = 10
ORDER BY created_at DESC
LIMIT 100;
```

### 31.1. Vì sao selectivity khác nhau?

Trong lab, tenant 1 chiếm khoảng 70% sự kiện, còn tenant 10 chiếm một phần nhỏ hơn nhiều. Với index trên `(tenant_id,status,created_at DESC)`, hai truy vấn chỉ có tenant equality nên cột `status` vẫn phân nhóm dữ liệu trong tenant; index **không tự cung cấp thời gian giảm toàn tenant**. Planner có thể dùng một index khác, sort hoặc seq scan.

### 31.2. Khó khăn của generic plan

Một generic plan không phân biệt cụ thể tenant 1 và tenant 10 như custom plan có thể. MCV có thể biết skew, nhưng **plan không chuyên biệt theo giá trị chưa biết** có thể dùng ước lượng trung bình.

### 31.3. Thiết kế index cho query thật

Nếu hot query luôn là “sự kiện mới nhất của tenant”, index cân nhắc:

```sql
CREATE INDEX idx_events_tenant_created
ON query_stats_lab.events (tenant_id, created_at DESC);
```

Tuy nhiên index này làm tăng chi phí duy trì và có thể chỉ đáng giá nếu workload thật thường xuyên, nhiều dữ liệu và có lợi thế đo được.

Nếu `WHERE status='paid'` luôn xuất hiện, index `(tenant_id,status,created_at DESC)` đã tạo có thể phù hợp hơn. Statistics và index design cần **phối hợp**, không thay thế cho nhau.

## 32. Tình huống thực tế: ngày gần đây và dữ liệu tăng dần

Một bảng sự kiện nhận hàng liên tục với `created_at` tăng theo thời gian. Truy vấn báo cáo:

```sql
SELECT event_id
FROM query_stats_lab.events
WHERE created_at >= TIMESTAMPTZ '2025-01-30 00:00+00';
```

### 32.1. Khi histogram chưa cập nhật

Nếu ANALYZE gần nhất xảy ra khi created_at tối đa là ngày 20, sau đó nhiều dữ liệu mới tới ngày 30, histogram cũ không mô tả phần thời gian mới. Một range cutoff rơi ngoài vùng histogram có thể làm selectivity estimate sai.

### 32.2. Đừng cố sửa bằng cách đổi correlation

Correlation created_at có thể vẫn gần +1 vì dữ liệu mới được append theo thời gian. Nhưng **correlation nói về heap locality**, không nói có bao nhiêu hàng sau cutoff mới.

Muốn sửa estimate số hàng phù hợp thường cần thống kê phân bố **mới/đủ đại diện** hoặc cơ chế khác phù hợp, không phải giả định correlation cao thì histogram tự biết ngày mới.

### 32.3. Khi bảng partition theo ngày

Một kiến trúc partitioning theo thời gian có thể giúp partition pruning giới hạn vùng dữ liệu cần đọc. Khi đó vẫn cần thống kê phù hợp của partitions. Không coi partitioning là cách thay thế mọi vấn đề thống kê phân bố.

## 33. Tình huống thực tế: một sự kiện rất hiếm

Giả sử hệ thống giám sát có `event_type='critical'` ở 0,001% hàng nhưng nó là hot query phục vụ cảnh báo.

### 33.1. MCV có thể bỏ qua giá trị hiếm

Nếu sample không gặp hoặc không xem `critical` là MCV, planner không có tần suất riêng chính xác cho giá trị đó. Nó có thể dùng ước lượng phần không thuộc MCV, dẫn tới sai lệch.

### 33.2. Có thể tăng statistics target?

Có thể thử trên cột `event_type`, nhưng không được hứa rằng tăng target sẽ luôn đưa mọi giá trị cực hiếm vào MCV. Còn phụ thuộc tỷ lệ, mẫu, số giá trị distinct và thuật toán.

### 33.3. Partial index là một hướng khác

Nếu query luôn tìm critical và policy cho phép:

```sql
-- Ví dụ độc lập, vì bảng lab không có cột event_type:
-- CREATE INDEX idx_critical_time
-- ON monitoring_events (created_at DESC)
-- WHERE event_type = 'critical';
```

Partial index chuyên biệt có thể hữu ích cho predicate hiếm nhưng quan trọng. Nó vẫn cần được đánh giá theo workload, tham số query và chi phí cập nhật.

**Thống kê tốt giúp chọn kế hoạch; cấu trúc index tốt cung cấp phương án truy cập.** Hai công việc bổ sung cho nhau.

## 34. Tình huống thực tế: phân bố nhiều cột biến động theo tenant

Trong hệ thống SaaS:

```text
Tenant A: 90% paid, 10% pending
Tenant B: 10% paid, 90% pending
```

Thống kê một cột có thể thấy:

```text
P(status='paid') ~50%
```

nhưng không thể suy ra trực tiếp:

```text
P(status='paid' | tenant='A') = 90%
P(status='paid' | tenant='B') = 10%
```

### 34.1. Vì sao điều kiện hai cột quan trọng?

```sql
SELECT *
FROM query_stats_lab.events
WHERE tenant_id = 1
  AND status = 'paid';
```

Thống kê riêng tenant_id và status có thể không mô tả đúng tần suất cặp này. Multivariate MCV hữu ích khi có những tổ hợp lặp lại rất thường xuyên.

### 34.2. Cần stats cho đúng cặp cột

```sql
CREATE STATISTICS stats_events_tenant_status
    (mcv, dependencies, ndistinct)
ON tenant_id, status
FROM query_stats_lab.events;

ANALYZE query_stats_lab.events;
```

Không kỳ vọng object trên `tenant_id,region` tự mô tả mọi tương quan giữa `tenant_id,status`. Mỗi statistics object chỉ mô tả những biểu thức/cột được định nghĩa và loại thống kê tương ứng.

### 34.3. Khi các giá trị rất hiếm

Nếu có hàng triệu cặp tenant/status và nhiều cặp hiếm, một MCV list hữu hạn không thể lưu đầy đủ xác suất mọi cặp. Planner vẫn phải ước lượng phần còn lại; với workload cực skew, có thể cần thiết kế dữ liệu/index hoặc query khác.

## 35. Các hiểu nhầm thường gặp

### Hiểu nhầm 1. “ANALYZE sẽ đếm tất cả dữ liệu chính xác”

Không. ANALYZE thường lấy mẫu để thu thập statistics ước lượng. `COUNT(*)` trên dữ liệu thật là một thao tác khác.

### Hiểu nhầm 2. “pg_stats là thống kê runtime của từng câu SELECT”

Không. `pg_stats` mô tả phân bố cột dùng cho planning; `EXPLAIN ANALYZE` mới đo thực thi một query cụ thể.

### Hiểu nhầm 3. “MCV bao gồm mọi giá trị distinct”

Không. MCV lưu một số giá trị phổ biến. Giá trị không nằm trong list vẫn có thể chiếm phần đáng kể của dữ liệu.

### Hiểu nhầm 4. “most_common_freqs tính phần trăm trên tập non-NULL”

Không mặc định. Frequencies biểu diễn tỷ lệ theo tổng số hàng tương ứng của thống kê; `null_frac` được ghi riêng.

### Hiểu nhầm 5. “Histogram chứa đủ cả các MCV”

Không. Histogram của PostgreSQL thường mô tả **phần giá trị không thuộc MCV và không NULL**.

### Hiểu nhầm 6. “Histogram chia số học thành các đoạn rộng bằng nhau”

Không. Các ranh giới hướng tới phân chia phần dữ liệu có **khối lượng quan sát gần đều** giữa các mốc.

### Hiểu nhầm 7. “histogram_bounds luôn có đúng target+1 mốc”

Không. Số mốc phụ thuộc dữ liệu, kiểu, sample và target; cột ít distinct có thể không có histogram.

### Hiểu nhầm 8. “n_distinct=-1 nghĩa là có -1 giá trị”

Không. Giá trị âm mô tả tỷ lệ distinct so với số hàng, ví dụ -1 ≈ mỗi hàng có giá trị khác nhau.

### Hiểu nhầm 9. “n_distinct=-1 bảo đảm UNIQUE”

Không. Chỉ ràng buộc UNIQUE/PRIMARY KEY phù hợp mới đảm bảo uniqueness ở mức database.

### Hiểu nhầm 10. “null_frac=0 đảm bảo cột không thể có NULL”

Không. Nó có thể chỉ là estimate mẫu; `NOT NULL` mới là ràng buộc schema tương ứng.

### Hiểu nhầm 11. “Correlation của tenant_id nói tenant phụ thuộc status”

Không. `pg_stats.correlation` nói về quan hệ giá trị cột với vị trí vật lý của rows.

### Hiểu nhầm 12. “Correlation=-1 nghĩa là dữ liệu không có quan hệ và index không thể dùng”

Không. -1 cho thấy thứ tự gần như đảo với vị trí vật lý, vẫn có tương quan mạnh và có thể hữu ích.

### Hiểu nhầm 13. “Correlation=+1 nghĩa query phải dùng Index Scan”

Không. Planner còn xét selectivity, số hàng, page costs, query shape, index và LIMIT.

### Hiểu nhầm 14. “ANALYZE nhiều lần tự sinh extended stats”

Không. Phải `CREATE STATISTICS` cho các cột/biểu thức cần mô hình hóa, rồi ANALYZE.

### Hiểu nhầm 15. “Extended stats sửa mọi JOIN cardinality”

Không. Khả năng áp dụng của dependencies/MCV/ndistinct phụ thuộc loại truy vấn và giới hạn PostgreSQL.

### Hiểu nhầm 16. “CREATE STATISTICS giống CREATE INDEX”

Không. Stats cung cấp thông tin cho optimizer, index cung cấp đường truy cập/constraint phù hợp.

### Hiểu nhầm 17. “Một mcv đa cột mô tả mọi tổ hợp”

Không. Multivariate MCV vẫn hữu hạn và lấy mẫu, không lưu toàn bộ tổ hợp hiếm.

### Hiểu nhầm 18. “n_mod_since_analyze là số DML chính xác”

Không. Đây là thống kê hoạt động ước lượng, không phải audit log hoặc row-level changelog.

### Hiểu nhầm 19. “Giảm autovacuum_analyze_scale_factor khiến query lập tức đổi plan”

Không. Nó thay ngưỡng đủ điều kiện autoanalyze; không bảo đảm worker chạy ngay và stats được cập nhật tức thì.

### Hiểu nhầm 20. “Mọi query chậm do thiếu ANALYZE”

Không. Có thể do index, I/O, blocking, bloat, query design hoặc dữ liệu thực sự quá lớn.

### Hiểu nhầm 21. “Seq Scan nghĩa planner không đọc statistics”

Không. Seq Scan có thể chính là phương án chi phí thấp nhất **theo statistics**, nhất là filter rất phổ biến.

### Hiểu nhầm 22. “Estimated cost nhỏ hơn luôn là cải thiện”

Không. Khi sửa estimate từ 1.000 lên 100.000 rows, chi phí dự đoán có thể tăng nhưng phương án chọn có thể thực tế tốt hơn.

### Hiểu nhầm 23. “EXPLAIN ANALYZE không chạy SQL”

Sai. ANALYZE option của EXPLAIN thực thi câu SQL, có thể gây tác động nếu đó là DML. Cần thận trọng trên production.

### Hiểu nhầm 24. “pg_stats có giá trị giống nhau giữa mọi tenant”

`pg_stats` của một cột toàn bảng mô tả **phân bố toàn relation**, không phải histogram riêng cho từng tenant. Muốn joint distribution có thể dùng extended MCV; partitioning cũng thay đổi phạm vi thống kê được sử dụng.

### Hiểu nhầm 25. “Generic plan biết tenant_id=$1 sẽ là tenant 1”

Không. Generic plan không chuyên biệt theo tham số cụ thể. MCV có thể giúp custom plan nhưng không biến tham số chưa biết thành literal.

### Hiểu nhầm 26. “Có extended stats rồi không cần ANALYZE”

Không. Statistics object cần được thu thập/cập nhật qua ANALYZE tương ứng.

### Hiểu nhầm 27. “Thống kê cột thay được index”

Không. Biết 0,1% hàng phù hợp không tạo ra cách nhảy ngay đến chúng nếu thiếu access path phù hợp.

### Hiểu nhầm 28. “Tăng statistics target toàn cluster là tối ưu miễn phí”

Không. ANALYZE, lưu trữ stats và planning có thể tốn thêm tài nguyên; nên đặt mục tiêu dựa trên sai số query thật.

### Hiểu nhầm 29. “Partition parent tự có mọi thống kê chính xác khi child đổi”

Không phải trong mọi trường hợp. Có thể cần ANALYZE parent, các partition riêng và kiểm tra inherited statistics.

### Hiểu nhầm 30. “Histogram của pg_stats là ngưỡng phân vị chính thức cho dashboard”

Không. Đây là tóm tắt sampling của planner; muốn ngưỡng phân vị nghiệp vụ cần query/analytics có định nghĩa và độ chính xác phù hợp.

## 36. Bài tập thực hành

Các bài tập sử dụng `query_stats_lab.events` từ phần 4 và PostgreSQL major hỗ trợ những tính năng được nêu. Với bài yêu cầu thay đổi cấu hình/thống kê, chỉ làm trên **database lab**; không thay đổi production để luyện tập. Câu hỏi EXPLAIN yêu cầu giải thích khả năng, không yêu cầu cố làm xuất hiện một loại scan duy nhất.

### Bài 1. Xác định các nguồn thống kê

Phân biệt mục đích của `pg_stats`, `pg_stats_ext`, `pg_stat_user_tables` và `pg_class.reltuples`. Nguồn nào cung cấp histogram của một cột, nguồn nào ghi lần autoanalyze gần nhất?

### Bài 2. null_frac bằng tay

Một bảng có 10.000 hàng, trong đó 1.500 hàng có `promo_code IS NULL`. Tính `null_frac` thực tế và dự đoán số hàng `promo_code IS NOT NULL`.

### Bài 3. null_frac trong lab

Viết SQL đọc `null_frac` cho `promo_code` và đếm chính xác số hàng có promo_code NULL trong `query_stats_lab.events`. Kỳ vọng con số xấp xỉ là bao nhiêu?

### Bài 4. MCV và frequencies

Giả sử:

```text
null_frac         = 0.10
most_common_vals  = {paid,pending,cancelled}
most_common_freqs = {0.60,0.20,0.10}
```

Trên bảng 100.000 hàng, ước lượng số hàng `status='paid'` và số hàng NULL. Có được coi frequencies đã chuẩn hóa trên non-NULL không?

### Bài 5. Equality khi không có MCV

Nếu cột có 1.000 giá trị distinct và không có MCV rõ ràng, tại sao giả định phân bố đều cho `col='x'` có thể sai với một giá trị hiếm hoặc rất phổ biến?

### Bài 6. Histogram và mốc phân vị

Giải thích vì sao histogram có các mốc `{10,20,30,60,120,400}` không có các khoảng rộng bằng nhau. Đây có phải output bắt buộc của PostgreSQL hay chỉ là ví dụ?

### Bài 7. MCV và histogram

Giả sử status='paid' chiếm 80% hàng và nằm trong MCV. Khi đọc `histogram_bounds`, có nên hiểu histogram vẫn bao phủ cả 80% paid theo cách đồng đều không?

### Bài 8. Numeric range

Viết query lấy mọi sự kiện có `amount >= 5000`. PostgreSQL có thể tận dụng loại thống kê nào để ước lượng tỷ lệ hàng?

### Bài 9. n_distinct âm

Một bảng 200.000 hàng có `n_distinct=-0.25` cho cột customer_id. Diễn giải giá trị đó và ước lượng số distinct theo mô hình cơ bản.

### Bài 10. n_distinct và UNIQUE

Giải thích tại sao `n_distinct=-1` không thay thế được unique constraint, kể cả khi hiện tại mọi event_id đều khác nhau.

### Bài 11. Correlation vật lý

Một cột created_at có correlation gần +1; cùng cột ở bảng được nạp đảo thời gian có correlation gần -1. Hai kết quả có nghĩa gì về vị trí vật lý? Giá trị -1 có chứng minh B-tree vô dụng không?

### Bài 12. Correlation giữa tenant_id và region

Trong lab, `tenant_id=1` luôn đi cùng `region='north'`. Có thể kiểm tra quan hệ ấy bằng `pg_stats.correlation` của tenant_id không? Nên dùng công cụ nào?

### Bài 13. Độc lập xác suất

Với `P(tenant=1)=0.7`, `P(north)=0.7`, nhưng `P(tenant=1 AND north)=0.7`, tính estimate nếu giả định hai predicate độc lập trên bảng 50.000 hàng. So với actual.

### Bài 14. CREATE STATISTICS

Viết SQL tạo extended statistics loại `dependencies`, `ndistinct` và `mcv` cho cặp `tenant_id,region`, sau đó thu thập thống kê.

### Bài 15. Phân biệt ba loại extended statistics

Kiểu nào giúp phân tích quan hệ phụ thuộc giữa các cột? Kiểu nào hỗ trợ số nhóm distinct của `GROUP BY`? Kiểu nào lưu các cặp giá trị phổ biến?

### Bài 16. Đọc pg_stats_ext

Viết truy vấn lấy tên statistics object, các cột tham gia, các kiểu thống kê và MCV frequencies của các object trên `query_stats_lab.events`.

### Bài 17. Statistics target

Tăng target cột amount lên 300, chạy ANALYZE, rồi trả về default target sau bài. Tăng target có đảm bảo query nhanh hơn không?

### Bài 18. Autoanalyze threshold

Giả định `autovacuum_analyze_threshold=100`, `autovacuum_analyze_scale_factor=0.05` và bảng ước lượng 200.000 hàng. Tính ngưỡng cơ bản. Nó có nghĩa autoanalyze chắc chắn chạy ngay đúng lúc đạt ngưỡng không?

### Bài 19. Stale stats

Một bảng vừa được nạp thêm một triệu hàng sau lần ANALYZE cuối. Viết query kiểm tra thời điểm ANALYZE và `n_mod_since_analyze`. Đề xuất hành động hợp lý.

### Bài 20. EXPLAIN estimated vs actual

Một node có `rows=300` trong `EXPLAIN` nhưng `actual rows=30000 loops=1` trong `EXPLAIN ANALYZE`. Planner đang sai bao nhiêu lần theo tỷ số số hàng? Những nhóm nguyên nhân nào nên kiểm tra?

### Bài 21. Loops

Một nested-loop inner index scan báo `actual rows=3 loops=1000`. Khoảng bao nhiêu hàng được node ấy xuất qua toàn bộ các lần gọi? Có nên lấy 3 làm tổng số hàng không?

### Bài 22. Generic và custom plan

Tại sao một query prepared `WHERE tenant_id=$1` có thể chạy rất khác giữa tenant lớn và nhỏ, dù thống kê một cột biết tenant lớn rất phổ biến? Nêu cách thí nghiệm với `plan_cache_mode`.

### Bài 23. Statistics và index

Một cột có giá trị hiếm 0.01% nhưng bảng không có index nào phù hợp. Tăng statistics target có tự làm query index scan được không? Vì sao?

### Bài 24. Histogram vs width_bucket

Viết query dùng `width_bucket(amount,0,8000,8)` để đếm hàng mỗi khoảng. Kết quả có phải cùng thứ với `pg_stats.histogram_bounds` không?

### Bài 25. Partitioned table

Một parent table partition theo tháng nhận dữ liệu mới vào các partitions con. Vì sao nên theo dõi thống kê của parent và từng partition, chứ không chỉ `last_autoanalyze` của một child?

### Bài 26. Sai số do group correlation

Một query `GROUP BY tenant_id,region` có số nhóm thực tế nhỏ hơn nhiều số nhóm planner ước lượng theo thống kê riêng lẻ. Loại extended statistics nào có khả năng hữu ích trực tiếp?

### Bài 27. Dữ liệu thay đổi theo thời gian

created_at tăng rất đều cùng thứ tự chèn, nhưng histogram được thu thập trước đợt import mới. Correlation cao có đủ để ước lượng chính xác `created_at >= yesterday` không?

### Bài 28. Thiết kế runbook

Hãy mô tả năm bước đầu để chẩn đoán một query đã chậm sau deployment: cần biết SQL/tham số, kế hoạch, phân bố cột, độ mới stats và mối liên hệ nhiều cột như thế nào?

## 37. Gợi ý lời giải

### Đáp án 1. Nguồn thống kê

- `pg_stats`: phân bố từng cột gồm MCV/histogram/correlation.
- `pg_stats_ext`: dữ liệu thống kê nhiều cột/biểu thức theo statistics objects.
- `pg_stat_user_tables`: hoạt động bảng, trong đó có `last_autoanalyze`.
- `pg_class.reltuples`: ước lượng số hàng của relation.

Không nhầm `pg_stats` với view thống kê runtime của mỗi query.

### Đáp án 2. null_frac

\[
\text{null\_frac}=\frac{1500}{10000}=0.15
\]

Số hàng không NULL là `10000-1500=8500`.

### Đáp án 3. promo_code

```sql
SELECT attname, null_frac
FROM pg_stats
WHERE schemaname = 'query_stats_lab'
  AND tablename = 'events'
  AND attname = 'promo_code';

SELECT COUNT(*) AS actual_null_rows
FROM query_stats_lab.events
WHERE promo_code IS NULL;
```

Dataset lab có 47.500 hàng NULL, gần 95%; `null_frac` từ ANALYZE kỳ vọng gần 0.95 vì sampling.

### Đáp án 4. MCV

Với 100.000 hàng:

- `paid` khoảng 60.000.
- SQL NULL khoảng 10.000.

`most_common_freqs` biểu diễn tỷ lệ trên **tập hàng toàn bảng**, không phải riêng non-NULL. Phần trăm 60% là tỷ lệ trong toàn relation.

### Đáp án 5. Giá trị không trong MCV

Giả định đều `1/n_distinct` chỉ là fallback/trực giác đơn giản. Dữ liệu thực có thể skew rất mạnh. Một giá trị có thể xuất hiện một lần, giá trị khác hàng chục nghìn lần; nếu không được mô tả riêng thì estimate cho từng literal có thể kém.

### Đáp án 6. Histogram

Các khoảng có thể có độ rộng khác nhau để đại diện số lượng quan sát gần đều giữa các ranh giới, sau khi loại MCV/NULL. Dãy {10,20,30,60,120,400} là ví dụ minh họa, không phải output cố định.

### Đáp án 7. MCV và histogram

Không. PostgreSQL mô hình hóa các giá trị MCV riêng. Histogram nhằm mô tả phân bố phần còn lại **non-null, non-MCV**; nếu coi histogram bao phủ đủ 100% thì sẽ tính đôi tần suất.

### Đáp án 8. Range

```sql
SELECT event_id, amount
FROM query_stats_lab.events
WHERE amount >= 5000;
```

Planner có thể dùng `histogram_bounds` và `most_common_vals/most_common_freqs` của amount để ước lượng phần hàng lớn hơn cutoff; chi phí scan còn phụ thuộc index/cột cần đọc.

### Đáp án 9. n_distinct

`-0.25` biểu diễn số distinct dự kiến gần 25% số hàng. Với 200.000 hàng:

\[
200000\times0.25=50000
\]

Đây là ước lượng; không phải phép đếm đảm bảo đúng mọi thời điểm.

### Đáp án 10. Unique

`n_distinct=-1` là metadata thống kê, không ngăn INSERT trùng. Muốn bảo vệ tính duy nhất của event_id phải có PRIMARY KEY hoặc UNIQUE index/constraint phù hợp. Bảng lab đã khai báo primary key trên event_id.

### Đáp án 11. Correlation

Gần +1: giá trị có xu hướng tăng cùng vị trí vật lý. Gần -1: giá trị có xu hướng giảm khi đi qua vị trí vật lý; vẫn là quan hệ rất mạnh nhưng ngược chiều. Index B-tree vẫn có thể hữu ích, vì PostgreSQL cân nhắc chiều quét, locality và chi phí.

### Đáp án 12. Tương quan hai cột

Không. `pg_stats.correlation` không đo quan hệ tenant-region. Có thể kiểm tra bằng:

```sql
SELECT tenant_id, COUNT(DISTINCT region)
FROM query_stats_lab.events
GROUP BY tenant_id;
```

Sau đó dùng `CREATE STATISTICS ... (dependencies,mcv,ndistinct)` và `pg_stats_ext` để mô hình hóa một số quan hệ nhiều cột.

### Đáp án 13. Ước lượng độc lập

\[
0.7 \times 0.7 = 0.49
\]

\[
50000 \times 0.49 = 24500
\]

Thực tế là 35.000 hàng, chênh **10.500 hàng**. Đó là minh họa của giả định độc lập, không phải con số mà mọi PostgreSQL plan bắt buộc in ra.

### Đáp án 14. Tạo stats

```sql
CREATE STATISTICS IF NOT EXISTS stats_exercise_tenant_region
    (dependencies, ndistinct, mcv)
ON tenant_id, region
FROM query_stats_lab.events;

ANALYZE query_stats_lab.events;
```

Không có ANALYZE thì statistics object mới chưa có thông tin đã thu thập cho planner tương ứng.

### Đáp án 15. Các loại extended statistics

- `dependencies`: phụ thuộc chức năng.
- `ndistinct`: số tổ hợp distinct.
- `mcv`: các tổ hợp giá trị phổ biến và tần suất.

Ba loại có mục tiêu khác nhau; không nên chọn tất cả mặc định nếu query không cần.

### Đáp án 16. pg_stats_ext

```sql
SELECT
    statistics_name,
    attnames,
    kinds,
    most_common_vals,
    most_common_freqs
FROM pg_stats_ext
WHERE schemaname = 'query_stats_lab'
  AND tablename = 'events'
ORDER BY statistics_name;
```

Thông tin MCV chỉ có nếu object đã thu thập kiểu mcv và dữ liệu/phiên bản phù hợp.

### Đáp án 17. Target

```sql
ALTER TABLE query_stats_lab.events
    ALTER COLUMN amount SET STATISTICS 300;

ANALYZE query_stats_lab.events;

ALTER TABLE query_stats_lab.events
    ALTER COLUMN amount SET STATISTICS -1;

ANALYZE query_stats_lab.events;
```

Target cao có thể cải thiện độ chi tiết thống kê, nhưng không đảm bảo query nhanh hơn và có chi phí thu thập/duy trì.

### Đáp án 18. Ngưỡng autoanalyze

\[
100 + 0.05\times 200000 = 10100
\]

Đây là ngưỡng cơ bản; autovacuum worker không được bảo đảm chạy đúng tức thì vào thời điểm số thay đổi chạm giá trị ấy.

### Đáp án 19. Stale stats

```sql
SELECT
    relname,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = 'query_stats_lab'
  AND relname = 'events';
```

Nếu dữ liệu đổi mạnh và stats cũ, cân nhắc chạy:

```sql
ANALYZE query_stats_lab.events;
```

Rồi đối chiếu row estimates và plan của truy vấn nhạy. Không mặc định autoanalyze sẽ chạy ngay sau bulk load.

### Đáp án 20. Sai số hàng

`30000/300=100` lần. Cần kiểm tra thống kê cũ, MCV/histogram, missing multivariate statistics, skew theo tham số, biểu thức không có stats và khả năng plan phụ thuộc partition.

### Đáp án 21. Loops

`3×1000≈3000` hàng được phát qua 1.000 lần gọi nếu số rows trong output là trung bình mỗi lần. Không lấy 3 làm tổng.

### Đáp án 22. Generic/custom plan

Tenant lớn và nhỏ có số hàng khác nhau rất nhiều. Generic plan không dùng chính xác giá trị `$1` để chuyên biệt hóa như custom plan. Thử:

```sql
BEGIN;
SET LOCAL plan_cache_mode = force_custom_plan;
-- EXPLAIN EXECUTE tên statement đã PREPARE với tenant lớn/nhỏ
ROLLBACK;

BEGIN;
SET LOCAL plan_cache_mode = force_generic_plan;
-- EXPLAIN EXECUTE cùng statement với hai giá trị
ROLLBACK;
```

Phải PREPARE statement trước thí nghiệm như phần 25. Không đổi plan_cache_mode toàn hệ thống chỉ vì một query.

### Đáp án 23. Statistics vs index

Không. Statistics giúp planner biết một giá trị rất hiếm, nhưng không tạo index path. Có thể vẫn phải seq scan nếu không có index hoặc phương án truy cập phù hợp.

### Đáp án 24. width_bucket

```sql
SELECT
    width_bucket(
        amount, 0::numeric, 8000::numeric, 8
    ) AS bucket,
    COUNT(*) AS n
FROM query_stats_lab.events
WHERE amount >= 0
  AND amount < 8000
GROUP BY 1
ORDER BY 1;
```

Đây là histogram **khoảng rộng bằng nhau** theo định nghĩa query. `pg_stats.histogram_bounds` thường có các ranh giới để các phần non-MCV có lượng quan sát gần đều.

### Đáp án 25. Partitioned table

Mỗi partition có phân bố và lịch analyze riêng; parent/inherited stats ảnh hưởng một số plans trên toàn cây. Autoanalyze parent không nhất thiết được kích hoạt chỉ bởi child changes. Cần xem partition pruning, stats cục bộ và ANALYZE parent khi phù hợp.

### Đáp án 26. Số nhóm

Extended statistics loại `ndistinct` trên `(tenant_id, region)` có thể cải thiện ước lượng số tổ hợp distinct cho GROUP BY tương ứng.

### Đáp án 27. Correlation không thay histogram

Không. Correlation gần +1 nói thời gian tăng theo vị trí heap, không nói chính xác **tỷ lệ rows sau yesterday**. Nếu histogram cũ không bao phủ giá trị mới, cần cập nhật thống kê và đo lại estimate, đồng thời xét partitioning nếu có.

### Đáp án 28. Runbook

1. Thu thập SQL, bind parameters, tần suất và latency thật.
2. Xem `EXPLAIN (ANALYZE, BUFFERS)` theo ngữ cảnh an toàn, xác định node có estimated/actual rows lệch.
3. Đọc `pg_stats` của các cột filter/order: MCV, histogram, null_frac, n_distinct, correlation.
4. Kiểm tra `last_analyze`, `last_autoanalyze` và mức thay đổi từ lần thu thập thống kê.
5. Kiểm tra phụ thuộc nhiều cột và `pg_stats_ext`; chỉ tạo thêm stats/đổi target/đổi index sau khi xác định nguồn sai số.

## 38. Checklist khi thiết kế, chẩn đoán và duy trì thống kê

1. **Xác định query thật:** SELECT, JOIN, ORDER BY, LIMIT và bind values cụ thể.
2. **Xác định trọng tâm sai số:** node nào có estimated rows khác actual rows lớn nhất?
3. **Đừng nhầm estimated cost với thời gian:** cost là đơn vị tương đối, actual time cần ANALYZE.
4. **Đừng quên loops:** actual rows mỗi lần node chạy không phải luôn tổng số hàng.
5. **Kiểm tra độ mới:** ANALYZE gần nhất khi nào, dữ liệu đổi từ đó ra sao?
6. **Đọc NULL đúng:** `null_frac` riêng; không dùng `= NULL`.
7. **Đọc MCV đúng:** values và frequencies khớp theo vị trí; frequencies trên tập hàng.
8. **Đọc histogram đúng:** không tính MCV/NULL, mốc gần đều số quan sát chứ không đều khoảng giá trị.
9. **Đọc n_distinct âm đúng:** là tỷ lệ distinct so với số hàng.
10. **Đừng dùng stats như constraint:** n_distinct=-1 không thay UNIQUE, null_frac=0 không thay NOT NULL.
11. **Đọc correlation đúng:** tương quan với vị trí vật lý, không phải giữa hai cột.
12. **Xem skew:** tenant hoặc status phổ biến có plan cần khác giá trị hiếm không?
13. **Kiểm tra dependencies:** các predicate có liên quan khiến giả định độc lập sai không?
14. **Dùng multivariate MCV khi cần:** các cặp/nhóm giá trị phổ biến có quyết định selectivity không?
15. **Dùng ndistinct đa cột đúng chỗ:** số nhóm GROUP BY có bị đoán sai không?
16. **Cập nhật stats sau CREATE STATISTICS:** ANALYZE là bước thu thập thông tin.
17. **Đánh giá target cục bộ:** chỉ tăng nơi sai số thực có thể được cải thiện.
18. **Xem biểu thức:** query có function/cast làm thống kê cột gốc không đủ không?
19. **Xem generic/custom plan:** tham số có skew mạnh không?
20. **Xem partitions:** stats parent/child có phù hợp dữ liệu và pruning không?
21. **Xem index:** biết selectivity không tạo access path nếu index không phù hợp.
22. **Xem runtime thực:** buffers, I/O, memory, blocking, cache và concurrency.
23. **Đo trước/sau:** đối chiếu nhiều representative parameters, không chỉ một trường hợp.
24. **Bảo mật thống kê:** MCV có thể chứa giá trị dữ liệu thật, tránh lộ nội dung nhạy cảm.

## 39. Tổng kết

**Thống kê cột là cầu nối giữa dữ liệu thực tế và quyết định của PostgreSQL query planner.** Không có thông tin về phân bố, optimizer dễ đánh giá sai chi phí ngay cả khi hệ thống đã có index phù hợp.

Những điều quan trọng nhất:

- **`ANALYZE`** thu thập thống kê bằng sampling để planner ước lượng, không phải phép đếm chính xác mọi hàng.
- **`null_frac`** cho biết tỷ lệ NULL, còn **`avg_width`** hỗ trợ ước lượng độ rộng dữ liệu.
- **`n_distinct`** diễn tả số giá trị phân biệt: dương là estimate số lượng, âm là tỷ lệ ước lượng trên số hàng.
- **`most_common_vals` / `most_common_freqs`** mô tả những giá trị phổ biến cùng tần suất, rất quan trọng với điều kiện equality trên dữ liệu lệch.
- **`histogram_bounds`** mô tả các ranh giới của **phần non-NULL, non-MCV**, thường chia theo lượng quan sát gần đều, hữu ích cho điều kiện phạm vi.
- **`correlation`** trong `pg_stats` cho biết mối liên hệ giữa giá trị cột và thứ tự vật lý tuple, ảnh hưởng chi phí dự kiến khi dùng index scan. Nó **không đo sự phụ thuộc giữa các cột**.
- **`CREATE STATISTICS`** giúp mô hình hóa một số đặc trưng **nhiều cột**: dependencies, ndistinct và multivariate MCV, nhưng không tự sửa mọi JOIN estimate.
- **Stale statistics và data skew** là hai nguyên nhân thường gặp khiến estimated rows khác actual rows; autoanalyze, statistics target và prepared-plan behavior cần được xem theo workload.
- **`EXPLAIN (ANALYZE, BUFFERS)`** giúp kiểm chứng plan, nhưng phải đọc đúng `loops`, chi phí, thời gian và buffers. Dùng an toàn vì ANALYZE option thực sự chạy truy vấn.
- **Thống kê không thay thế index, constraints hoặc thiết kế truy vấn.** Nó giúp chọn giữa những phương án hiện có; hiệu quả thật vẫn phụ thuộc dữ liệu, I/O, cache, concurrency và kiến trúc.

Nguyên tắc làm việc có thể ghi nhớ:

> Khi PostgreSQL chọn một kế hoạch có vẻ bất hợp lý, trước hết hãy kiểm tra **nó đang nghĩ có bao nhiêu hàng thỏa điều kiện, dựa trên những thống kê nào, và phân bố thật có khác giả định đó không**. Sau đó mới quyết định cần ANALYZE, extended statistics, index khác hay sửa chính truy vấn.

Đó là cách chuyển tối ưu PostgreSQL từ việc “thử tạo index ngẫu nhiên” thành một quy trình có bằng chứng, có khả năng giải thích và có thể lặp lại.





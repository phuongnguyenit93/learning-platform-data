# Tối ưu tổng hợp, lọc có điều kiện và truy vấn báo cáo trong PostgreSQL

Truy vấn báo cáo thường được viết sau khi một hệ thống đã có dữ liệu: doanh thu theo ngày, số đơn theo trạng thái, tỷ lệ thanh toán, số khách duy nhất, top sản phẩm, doanh thu theo khu vực và bảng điều khiển nhiều chỉ số. Những truy vấn này nhìn qua có vẻ chỉ là `SELECT` với `SUM` và `GROUP BY`, nhưng ở quy mô lớn chúng có thể trở thành phần tốn CPU, RAM, I/O và thời gian xử lý nhất.

Ví dụ đơn giản:

```sql
SELECT
    region,
    COUNT(*) AS orders,
    SUM(total_amount) AS revenue
FROM orders
WHERE ordered_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND status = 'PAID'
GROUP BY region;
```

Đây là truy vấn hợp lý, nhưng để biết nó có tối ưu và **đúng nghiệp vụ** hay không, cần trả lời thêm:

- Có index hỗ trợ lọc thời gian và trạng thái không?
- Truy vấn đang đọc bao nhiêu hàng trước khi GROUP BY?
- Nếu thêm bảng `order_items` và `payments`, tổng tiền có bị nhân bản do JOIN một-nhiều không?
- Báo cáo cần tính **giá trị đơn hàng**, **doanh thu đã thu**, **hoàn tiền**, hay **doanh thu ròng**?
- Dùng `WHERE`, `HAVING`, `FILTER (WHERE ...)` hoặc `CASE` trong trường hợp nào?
- `COUNT(DISTINCT customer_id)` tiêu tốn tài nguyên ra sao?
- PostgreSQL chọn `HashAggregate`, `GroupAggregate` hay parallel aggregation? Có spill ra temporary files không?
- Khi có dashboard lặp lại nhiều lần, có nên dùng bảng tổng hợp hoặc materialized view không?
- Lọc ngày theo múi giờ của người dùng có còn sử dụng index tốt không?
- Tính đúng kết quả có giữ được khi dữ liệu được cập nhật đồng thời hay khi replica chậm?

Bài học này tập trung vào **tối ưu tổng hợp, lọc có điều kiện và truy vấn báo cáo trong PostgreSQL** theo hai trục không thể tách rời: **kết quả đúng** và **chi phí thực thi phù hợp**. Một báo cáo chạy nhanh nhưng nhân đôi doanh thu vì JOIN sai còn nguy hiểm hơn một báo cáo chạy chậm.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Xác định chính xác **grain** của dữ liệu và của kết quả trước khi viết GROUP BY.
2. Phân biệt `WHERE`, `HAVING` và `FILTER (WHERE ...)`; dùng mỗi cơ chế cho đúng mục đích.
3. Viết **conditional aggregation** bằng `COUNT(*) FILTER`, `SUM(...) FILTER` và `CASE`.
4. Hiểu `COUNT(*)`, `COUNT(column)`, `COUNT(DISTINCT column)` và vai trò của NULL.
5. Tránh lỗi **join fan-out** làm nhân đôi SUM và COUNT khi JOIN nhiều bảng một-nhiều.
6. Tối ưu báo cáo bằng **pre-aggregation**, nhóm sớm, lọc sớm và giảm số hàng trung gian.
7. Chọn điều kiện lọc thời gian **half-open interval** để giữ index-friendly và tránh sai phạm vi.
8. Dùng `date_trunc`, `GROUPING SETS`, `ROLLUP` và `CUBE` cho báo cáo nhiều cấp.
9. Đọc `EXPLAIN (ANALYZE, BUFFERS)` với `HashAggregate`, `GroupAggregate`, `Sort`, `Bitmap Heap Scan`, `Gather` và temporary I/O.
10. Đánh giá B-tree, partial index, covering index, BRIN, partition pruning và thống kê planner.
11. Xem xét `COUNT(DISTINCT)`, high-cardinality grouping, work memory và spill.
12. Hiểu lợi ích và rủi ro của `MATERIALIZED VIEW`, bảng summary và incremental aggregation.
13. Phân biệt dữ liệu report snapshot, dữ liệu thay đổi trong transaction và độ trễ replica.
14. Thiết kế phép đo trước/sau và giám sát báo cáo bằng các công cụ phù hợp.

> **Phạm vi:** PostgreSQL hiện đại. Hành vi cụ thể của planner thay đổi theo phiên bản, dữ liệu, thống kê và cấu hình. Các câu SQL thay đổi schema/dữ liệu chỉ dành cho **database thực hành được phép reset**, không áp dụng nguyên xi cho production.

---

## 2. Trước khi tối ưu: xác định grain và ý nghĩa chỉ số

**Grain** là mức chi tiết mà mỗi hàng đại diện:

| Quan hệ | Mỗi hàng là gì? | Khóa điển hình |
| --- | --- | --- |
| `orders` | Một đơn hàng | `order_id` |
| `order_items` | Một dòng sản phẩm trong đơn | `item_id` |
| `payment_events` | Một sự kiện thu/hoàn tiền | `payment_id` |
| Báo cáo ngày–khu vực | Một ngày trong một khu vực | `report_day, region` |
| Báo cáo ngày–khu vực–trạng thái | Một ngày, khu vực và trạng thái | `report_day, region, status` |

Một báo cáo “số đơn theo ngày” có grain đầu ra là **ngày**, nhưng nếu JOIN vào bảng item thì grain dữ liệu trung gian có thể là **dòng item**, không còn là đơn. Nếu đếm ngay sau JOIN, một đơn có ba item có thể bị tính thành ba đơn.

### 2.1. Chỉ số phải có định nghĩa nghiệp vụ

Các khái niệm thường bị trộn lẫn:

- **Order count:** số đơn hàng.
- **Paid order count:** số đơn có status PAID theo quy ước.
- **Gross captured payments:** tổng sự kiện tiền đã thu.
- **Refunds:** tổng sự kiện hoàn tiền.
- **Net payment flow:** tiền thu trừ tiền hoàn trong phạm vi được chọn.
- **Order value:** giá trị đặt hàng trên bản ghi order; có thể không bằng dòng tiền thực thu.
- **Unique customers:** số customer_id phân biệt.
- **Average order value:** tổng tiền của những đơn được định nghĩa hợp lệ / số đơn của nhóm đó.

Đừng đặt tên cột `revenue` rồi cộng mọi `orders.total_amount` mà không thống nhất những trạng thái nào được tính và cách xử lý hoàn tiền, thuế, hủy, đơn trả lại.

### 2.2. Ba bước kiểm tra tính đúng

Trước mỗi truy vấn báo cáo:

1. Ghi rõ grain đầu ra: ví dụ một hàng cho mỗi `(UTC day, region)`.
2. Ghi rõ **tập bản ghi hợp lệ**: ví dụ đơn status PAID; thời gian dựa trên ordered_at hay paid_at?
3. Ghi rõ đơn vị và công thức: `NUMERIC(14,2)`, tiền tệ, số khách phân biệt, doanh thu trước hay sau hoàn tiền.

**Tối ưu truy vấn không được đổi định nghĩa metric.** Hai câu SQL trả số khác nhau vì khác điều kiện nghiệp vụ không thể được coi là “cùng truy vấn, phiên bản nhanh hơn”.

---

## 3. Lab: bảng đơn hàng, dòng đơn và thanh toán

Lab minh họa đủ các tình huống GROUP BY, JOIN fan-out và conditional aggregates.

> **Cảnh báo:** Những câu `DROP TABLE IF EXISTS` xóa dữ liệu bảng lab có cùng tên. Chỉ chạy trên một **database thử nghiệm riêng** hoặc schema được phép reset.

### 3.1. Tạo schema

```sql
CREATE SCHEMA IF NOT EXISTS report_opt_lab;

DROP TABLE IF EXISTS report_opt_lab.payment_events;
DROP TABLE IF EXISTS report_opt_lab.order_items;
DROP TABLE IF EXISTS report_opt_lab.orders;

CREATE TABLE report_opt_lab.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    region TEXT NOT NULL
        CHECK (region IN ('NORTH', 'CENTRAL', 'SOUTH')),
    status TEXT NOT NULL
        CHECK (status IN ('PAID', 'REFUNDED', 'CANCELED', 'PENDING')),
    ordered_at TIMESTAMPTZ NOT NULL,
    total_amount NUMERIC(14,2) NOT NULL
        CHECK (total_amount >= 0)
);

CREATE TABLE report_opt_lab.order_items (
    item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES report_opt_lab.orders(order_id),
    sku TEXT NOT NULL,
    category TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    line_amount NUMERIC(14,2) NOT NULL
        CHECK (line_amount >= 0)
);

CREATE TABLE report_opt_lab.payment_events (
    payment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES report_opt_lab.orders(order_id),
    event_type TEXT NOT NULL
        CHECK (event_type IN ('CAPTURE', 'REFUND')),
    amount NUMERIC(14,2) NOT NULL CHECK (amount >= 0),
    event_at TIMESTAMPTZ NOT NULL
);
```

Mỗi order có thể có nhiều items và nhiều payment events. Đây chính là mối quan hệ tạo ra nguy cơ **nhân bản hàng** khi JOIN.

### 3.2. Nạp 15.000 đơn

```sql
INSERT INTO report_opt_lab.orders (
    order_id, customer_id, region, status, ordered_at, total_amount
)
SELECT
    g.n::BIGINT,
    (g.n % 1000) + 1,
    CASE (g.n % 3)
        WHEN 0 THEN 'NORTH'
        WHEN 1 THEN 'CENTRAL'
        ELSE 'SOUTH'
    END,
    CASE (g.n % 10)
        WHEN 0 THEN 'REFUNDED'
        WHEN 1 THEN 'CANCELED'
        WHEN 2 THEN 'PENDING'
        ELSE 'PAID'
    END,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + (g.n % 120) * INTERVAL '1 day'
        + (g.n % 86400) * INTERVAL '1 second',
    ROUND(20::NUMERIC + (g.n % 49999)::NUMERIC / 100, 2)
FROM generate_series(1, 15000) AS g(n);
```

Thời gian đơn nằm trong một khoảng đầu năm 2026 theo UTC; giá trị `status` và `region` phân bổ lặp để có đủ nhóm.

### 3.3. Mỗi đơn có ba dòng item

```sql
INSERT INTO report_opt_lab.order_items (
    order_id, sku, category, quantity, line_amount
)
SELECT
    o.order_id,
    'SKU-' || LPAD(
        (1 + (o.order_id + x.i) % 50)::TEXT, 3, '0'
    ),
    CASE x.i
        WHEN 1 THEN 'ACCESSORY'
        WHEN 2 THEN 'MAIN'
        ELSE 'SERVICE'
    END,
    1,
    CASE x.i
        WHEN 1 THEN ROUND(o.total_amount * 0.20, 2)
        WHEN 2 THEN ROUND(o.total_amount * 0.30, 2)
        ELSE o.total_amount
           - ROUND(o.total_amount * 0.20, 2)
           - ROUND(o.total_amount * 0.30, 2)
    END
FROM report_opt_lab.orders AS o
CROSS JOIN generate_series(1, 3) AS x(i);
```

Trong lab, tổng ba dòng item bằng `orders.total_amount`. Điều này được tạo **có chủ đích** để có mốc đối chiếu khi tổng hợp, không phải một quy tắc tự động của bảng orders ngoài thực tế.

### 3.4. Mô phỏng sự kiện thu và hoàn tiền

```sql
-- Đơn PAID hoặc REFUNDED đều từng có một lần CAPTURE.
INSERT INTO report_opt_lab.payment_events (
    order_id, event_type, amount, event_at
)
SELECT
    order_id, 'CAPTURE', total_amount,
    ordered_at + INTERVAL '10 minutes'
FROM report_opt_lab.orders
WHERE status IN ('PAID', 'REFUNDED');

-- Một số đơn REFUNDED có thêm một sự kiện hoàn một nửa tiền.
INSERT INTO report_opt_lab.payment_events (
    order_id, event_type, amount, event_at
)
SELECT
    order_id, 'REFUND',
    ROUND(total_amount * 0.50, 2),
    ordered_at + INTERVAL '1 day'
FROM report_opt_lab.orders
WHERE status = 'REFUNDED';

ANALYZE report_opt_lab.orders;
ANALYZE report_opt_lab.order_items;
ANALYZE report_opt_lab.payment_events;
```

Bảng thanh toán có thể có **hai sự kiện cho một đơn**, còn mỗi đơn có ba item. JOIN cả ba bảng thô có thể tạo **sáu hàng trung gian cho một đơn REFUNDED**.

### 3.5. Xác nhận dữ liệu gốc

```sql
SELECT
    (SELECT COUNT(*) FROM report_opt_lab.orders)
        AS order_count,
    (SELECT COUNT(*) FROM report_opt_lab.order_items)
        AS item_count,
    (SELECT COUNT(*) FROM report_opt_lab.payment_events)
        AS payment_event_count;
```

Kết quả định tính:

- 15.000 hàng orders.
- 45.000 hàng order_items.
- Payment events tùy số hàng PAID/REFUNDED và REFUND trong mẫu.

Kiểm tra tổng item có bằng order amount:

```sql
SELECT COUNT(*) AS orders_with_mismatch
FROM (
    SELECT
        o.order_id,
        o.total_amount,
        SUM(i.line_amount) AS item_total
    FROM report_opt_lab.orders AS o
    JOIN report_opt_lab.order_items AS i
      ON i.order_id = o.order_id
    GROUP BY o.order_id, o.total_amount
) AS s
WHERE s.item_total IS DISTINCT FROM s.total_amount;
```

Với dữ liệu nạp ở trên, kết quả mong đợi là **0**. Đây là kiểm tra tính đúng của lab, không phải benchmark hiệu năng.

---

## 4. WHERE, HAVING và FILTER: ba câu hỏi khác nhau

Ba vị trí lọc thường bị dùng lẫn lộn.

| Thành phần | Hoạt động ở mức nào? | Ví dụ |
| --- | --- | --- |
| `WHERE` | Giới hạn **hàng đầu vào** trước aggregation | Chỉ xét đơn trong tháng Một |
| `HAVING` | Giới hạn **nhóm đầu ra** dựa trên biểu thức nhóm | Chỉ giữ khu vực có hơn 1.000 đơn |
| `FILTER (WHERE ...)` | Chỉ đưa **những hàng thỏa điều kiện vào một aggregate cụ thể** | Cùng một nhóm tính số PAID và CANCELED |

### 4.1. WHERE lọc trước khi GROUP BY

```sql
SELECT region, COUNT(*) AS paid_orders
FROM report_opt_lab.orders
WHERE status = 'PAID'
GROUP BY region;
```

Ở đây, các đơn không PAID **không còn là đầu vào của mọi aggregate trong statement**.

### 4.2. HAVING lọc các nhóm đã hình thành

```sql
SELECT
    region,
    COUNT(*) AS order_count
FROM report_opt_lab.orders
GROUP BY region
HAVING COUNT(*) > 4000;
```

`HAVING` kiểm tra giá trị tổng hợp theo region. Nó không thay `WHERE` khi cần sớm loại các hàng không thuộc phạm vi báo cáo.

### 4.3. FILTER lọc riêng từng aggregate

```sql
SELECT
    region,
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders,
    COUNT(*) FILTER (WHERE status = 'CANCELED')
        AS canceled_orders,
    COUNT(*) FILTER (WHERE status = 'REFUNDED')
        AS refunded_orders,
    COUNT(*) FILTER (WHERE status = 'PENDING')
        AS pending_orders
FROM report_opt_lab.orders
GROUP BY region
ORDER BY region;
```

Từng `FILTER` chỉ áp dụng cho aggregate ngay trước nó; các aggregate khác vẫn nhìn tập hàng của nhóm theo điều kiện `WHERE` chung.

### 4.4. Một lỗi định nghĩa metric thường gặp

Sai nếu muốn đếm **tất cả đơn và số đơn PAID**:

```sql
SELECT
    region,
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders
FROM report_opt_lab.orders
WHERE status = 'PAID'
GROUP BY region;
```

Vì `WHERE status='PAID'` đã bỏ các đơn khác, `all_orders` và `paid_orders` bằng nhau. Câu SQL hợp lệ nhưng ý nghĩa all_orders sai.

**Nguyên tắc:** dùng `WHERE` cho phạm vi chung của report, còn `FILTER` cho điều kiện riêng của từng chỉ số.

---

## 5. Conditional aggregation với FILTER và CASE

PostgreSQL hỗ trợ cú pháp:

```sql
aggregate(expression) FILTER (WHERE condition)
```

Ví dụ doanh thu các đơn PAID và số đơn từng trạng thái:

```sql
SELECT
    DATE_TRUNC('day', ordered_at AT TIME ZONE 'UTC')::DATE
        AS order_day_utc,
    COUNT(*) AS orders,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders,
    COUNT(*) FILTER (WHERE status = 'REFUNDED')
        AS refunded_orders,
    SUM(total_amount) FILTER (WHERE status = 'PAID')
        AS paid_order_value
FROM report_opt_lab.orders
WHERE ordered_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-02-01 00:00:00+00'
GROUP BY order_day_utc
ORDER BY order_day_utc;
```

Trong mẫu này, `paid_order_value` có nghĩa là **tổng giá trị đơn đang mang status PAID**, không phải tổng dòng tiền đã thu hoặc doanh thu ròng sau hoàn tiền.

### 5.1. Cùng logic bằng CASE

```sql
SELECT
    region,
    COUNT(*) AS orders,
    SUM(
        CASE WHEN status = 'PAID' THEN 1 ELSE 0 END
    ) AS paid_orders_case,
    COUNT(*) FILTER (
        WHERE status = 'PAID'
    ) AS paid_orders_filter
FROM report_opt_lab.orders
GROUP BY region;
```

Hai cách này thường cho cùng số lượng khi CASE được viết đúng.

`FILTER` có ưu điểm biểu đạt rõ điều kiện gắn với aggregate, đặc biệt khi một SELECT có nhiều metric. Nhưng **FILTER không tự bảo đảm luôn nhanh hơn CASE**: planner và executor vẫn phải đọc đủ dữ liệu cần thiết. Benchmark với dữ liệu thực mới biết khác biệt đáng kể hay không.

### 5.2. Cẩn thận COUNT với CASE

Hai mẫu sau **khác nhau**:

```sql
-- Đúng: COUNT chỉ đếm các hàng CASE trả giá trị khác NULL.
COUNT(CASE WHEN status = 'PAID' THEN 1 END)

-- Sai nếu muốn đếm riêng PAID: mọi hàng đều trả 0 hoặc 1,
-- nên COUNT đếm tất cả hàng trong nhóm.
COUNT(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END)
```

Nếu muốn dùng CASE có ELSE 0, dùng `SUM(...)`. Nếu dùng COUNT, để những hàng không khớp trả NULL.

### 5.3. NULL: COUNT và SUM có hành vi khác nhau

```sql
SELECT
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_count,
    SUM(total_amount) FILTER (
        WHERE status = 'PAID'
    ) AS paid_total
FROM report_opt_lab.orders
WHERE ordered_at >= TIMESTAMPTZ '2030-01-01 00:00:00+00';
```

Nếu không có hàng nào trong phạm vi:

- `COUNT(*)` trả **0**.
- `SUM(...)` trả **NULL**, không phải 0.

Để tạo output tài chính có mặc định 0 khi không có input:

```sql
COALESCE(
    SUM(total_amount) FILTER (WHERE status = 'PAID'),
    0::NUMERIC
) AS paid_total
```

Việc chọn 0 hay NULL là **quyết định ngữ nghĩa**: 0 nghĩa không có doanh thu, NULL có thể mang nghĩa không có dữ liệu/không xác định. Không COALESCE mọi aggregate về 0 theo thói quen nếu nghiệp vụ cần phân biệt.

---

## 6. COUNT(*), COUNT(column), COUNT(DISTINCT)

Ba hàm đếm tưởng giống nhau nhưng có nghĩa khác.

```sql
SELECT
    region,
    COUNT(*) AS row_count,
    COUNT(customer_id) AS non_null_customer_rows,
    COUNT(DISTINCT customer_id) AS unique_customers
FROM report_opt_lab.orders
GROUP BY region;
```

- `COUNT(*)` đếm **mọi hàng** trong nhóm, không phụ thuộc NULL của cột.
- `COUNT(column)` đếm hàng có cột **khác NULL**.
- `COUNT(DISTINCT column)` đếm **giá trị phân biệt khác NULL**.

Trong lab, `customer_id` là `NOT NULL` nên COUNT(*) và COUNT(customer_id) bằng nhau nếu không có JOIN sinh hàng lặp. Nhưng khi JOIN, số hàng đầu vào có thể lớn hơn số đơn.

### 6.1. DISTINCT có chi phí riêng

Một aggregate:

```sql
COUNT(DISTINCT customer_id)
```

không thể chỉ cộng một counter đơn giản nếu cùng customer_id xuất hiện nhiều lần. Engine phải phân biệt các giá trị, thường cần bộ nhớ, sắp xếp/hash hoặc kế hoạch phù hợp. Với số giá trị phân biệt rất lớn, chi phí có thể tăng mạnh.

### 6.2. COUNT(DISTINCT) không chữa mọi lỗi JOIN

Khi JOIN fan-out, `COUNT(DISTINCT o.order_id)` có thể sửa **số đơn**, nhưng:

```sql
SUM(o.total_amount)
```

vẫn có thể bị nhân lên.

Còn:

```sql
SUM(DISTINCT o.total_amount)
```

không phải cách sửa: hai đơn khác nhau cùng số tiền 100 phải được cộng thành 200, nhưng SUM(DISTINCT) chỉ cộng 100 một lần.

**Cách sửa đúng là khôi phục grain và cấu trúc JOIN**, không dùng DISTINCT để che lỗi tùy tiện.

### 6.3. DISTINCT trên tập đầu vào đã rút gọn

Nếu cần số khách phân biệt theo ngày và region, đôi khi có thể tách:

```sql
WITH customer_days AS (
    SELECT DISTINCT
        (ordered_at AT TIME ZONE 'UTC')::DATE AS day_utc,
        region,
        customer_id
    FROM report_opt_lab.orders
    WHERE status = 'PAID'
)
SELECT
    day_utc,
    region,
    COUNT(*) AS unique_paid_customers
FROM customer_days
GROUP BY day_utc, region
ORDER BY day_utc, region;
```

Kế hoạch này làm rõ grain `(day, region, customer)` trước khi đếm. Nó không tự luôn nhanh hơn `COUNT(DISTINCT)`: phải đo theo dữ liệu, số nhóm và index.

---

## 7. Sai lầm nghiêm trọng: JOIN fan-out nhân đôi tổng tiền

Mỗi đơn có ba items. Đơn REFUNDED có hai payment events. Nếu JOIN trực tiếp:

```sql
SELECT
    o.order_id,
    COUNT(*) AS joined_rows,
    SUM(o.total_amount) AS wrong_order_sum
FROM report_opt_lab.orders AS o
JOIN report_opt_lab.order_items AS i
  ON i.order_id = o.order_id
JOIN report_opt_lab.payment_events AS p
  ON p.order_id = o.order_id
WHERE o.status = 'REFUNDED'
GROUP BY o.order_id
ORDER BY o.order_id
LIMIT 5;
```

Một đơn REFUNDED có:

```text
1 order
  x 3 order_items
  x 2 payment_events
  = 6 hàng trong kết quả JOIN
```

Vì vậy `SUM(o.total_amount)` của một đơn có thể gấp **6 lần giá trị thật**. Đây là lỗi **join fan-out**, **join multiplication** hoặc **row explosion**.

### 7.1. Vì sao GROUP BY sau JOIN không sửa được?

GROUP BY gom những hàng trung gian theo khóa nhóm, nhưng nếu một giá trị xuất hiện sáu lần trong input thì SUM vẫn cộng nó sáu lần.

```text
Sai grain:
orders (1 row/order)
  JOIN items (3 rows/order)
  JOIN payments (2 rows/order)
    -> 6 rows/order
GROUP BY order_id
    -> 1 output row/order
    -> SUM(order_amount) đã bị cộng 6 lần
```

Số hàng đầu ra có thể đúng, còn giá trị aggregate vẫn sai.

### 7.2. Cách sửa: aggregate mỗi quan hệ 1:N về grain order trước JOIN

```sql
WITH item_totals AS (
    SELECT
        order_id,
        SUM(line_amount) AS item_amount,
        SUM(quantity) AS item_quantity
    FROM report_opt_lab.order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT
        order_id,
        SUM(amount) FILTER (
            WHERE event_type = 'CAPTURE'
        ) AS captured_amount,
        SUM(amount) FILTER (
            WHERE event_type = 'REFUND'
        ) AS refunded_amount
    FROM report_opt_lab.payment_events
    GROUP BY order_id
)
SELECT
    o.order_id,
    o.total_amount,
    i.item_amount,
    COALESCE(p.captured_amount, 0::NUMERIC)
        AS captured_amount,
    COALESCE(p.refunded_amount, 0::NUMERIC)
        AS refunded_amount
FROM report_opt_lab.orders AS o
LEFT JOIN item_totals AS i
  ON i.order_id = o.order_id
LEFT JOIN payment_totals AS p
  ON p.order_id = o.order_id
WHERE o.order_id = 10;
```

Các CTE đưa `order_items` và `payment_events` về **một hàng trên order_id** rồi mới JOIN. Mỗi đơn không bị nhân số hàng do hai quan hệ 1:N.

### 7.3. Chỉ pre-aggregate những bảng cần dùng

Nếu báo cáo chỉ hỏi số đơn và tổng order value theo region, **đừng JOIN items/payments** khi không cần. Mỗi JOIN có chi phí và có thể làm biến dạng grain.

### 7.4. Không quên những order không có payment

`LEFT JOIN payment_totals` giữ đơn chưa thanh toán. Với những đơn không có payment, các cột từ bảng phải là NULL; `COALESCE` về 0 chỉ khi chỉ số nghiệp vụ muốn diễn giải “chưa có sự kiện tiền”.

Nếu dùng `INNER JOIN payment_totals`, các đơn không có payment sẽ bị loại. Điều đó có thể đúng cho báo cáo “đơn từng có giao dịch thanh toán”, nhưng sai cho “tất cả đơn”.

---

## 8. Báo cáo từ nhiều bảng: xây từ grain đúng

Ta muốn báo cáo theo `region`:

- Số đơn.
- Tổng order value của các đơn PAID.
- Tổng tiền đã CAPTURE.
- Tổng tiền đã REFUND.
- Tiền thu ròng = captured − refunded.
- Tổng số item của các đơn.

Một cách làm rõ grain:

```sql
WITH item_by_order AS (
    SELECT
        order_id,
        SUM(quantity) AS quantity
    FROM report_opt_lab.order_items
    GROUP BY order_id
),
payment_by_order AS (
    SELECT
        order_id,
        COALESCE(
            SUM(amount) FILTER (WHERE event_type = 'CAPTURE'),
            0::NUMERIC
        ) AS captured,
        COALESCE(
            SUM(amount) FILTER (WHERE event_type = 'REFUND'),
            0::NUMERIC
        ) AS refunded
    FROM report_opt_lab.payment_events
    GROUP BY order_id
)
SELECT
    o.region,
    COUNT(*) AS order_count,
    COALESCE(
        SUM(o.total_amount) FILTER (WHERE o.status = 'PAID'),
        0::NUMERIC
    ) AS paid_order_value,
    COALESCE(SUM(p.captured), 0::NUMERIC) AS captured,
    COALESCE(SUM(p.refunded), 0::NUMERIC) AS refunded,
    COALESCE(SUM(p.captured - p.refunded), 0::NUMERIC)
        AS net_payment_flow,
    COALESCE(SUM(i.quantity), 0::BIGINT)
        AS item_quantity
FROM report_opt_lab.orders AS o
LEFT JOIN item_by_order AS i
  ON i.order_id = o.order_id
LEFT JOIN payment_by_order AS p
  ON p.order_id = o.order_id
GROUP BY o.region
ORDER BY o.region;
```

### 8.1. Vì sao COALESCE trong payment_by_order?

Nếu một order có CAPTURE nhưng không có REFUND:

```text
SUM(amount) FILTER (WHERE event_type='REFUND') = NULL
```

Nếu không COALESCE, `captured - refunded` thành NULL và bị `SUM` bỏ qua, khiến tiền thu ròng sai. Đưa NULL về 0 **theo định nghĩa nghiệp vụ** trước khi tính hiệu.

### 8.2. Lưu ý phạm vi theo thời gian

Nếu báo cáo theo **ngày đặt đơn**, lọc `o.ordered_at`. Nếu báo cáo theo **ngày dòng tiền**, lọc `p.event_at`. Hai kết quả có thể khác nhau vì tiền được hoàn ngày hôm sau.

Không được “tối ưu” bằng cách lọc ngày đặt đơn rồi đặt tên `cashflow_by_payment_day`. Đó là thay đổi định nghĩa báo cáo.

### 8.3. Có thể giảm phạm vi trước khi aggregate

Truy vấn ở trên tổng hợp **toàn bộ item/payment của mọi order**, dù báo cáo chỉ cần một khoảng ngày nhỏ. Với bảng lớn, đây có thể là dư thừa.

Một biến thể lọc orders trước rồi mới lấy dữ liệu liên quan:

```sql
WITH selected_orders AS (
    SELECT *
    FROM report_opt_lab.orders
    WHERE ordered_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
      AND ordered_at <  TIMESTAMPTZ '2026-03-01 00:00:00+00'
),
item_by_order AS (
    SELECT
        i.order_id,
        SUM(i.quantity) AS quantity
    FROM report_opt_lab.order_items AS i
    JOIN selected_orders AS o
      ON o.order_id = i.order_id
    GROUP BY i.order_id
),
payment_by_order AS (
    SELECT
        p.order_id,
        COALESCE(
            SUM(p.amount) FILTER (WHERE p.event_type = 'CAPTURE'),
            0::NUMERIC
        ) AS captured,
        COALESCE(
            SUM(p.amount) FILTER (WHERE p.event_type = 'REFUND'),
            0::NUMERIC
        ) AS refunded
    FROM report_opt_lab.payment_events AS p
    JOIN selected_orders AS o
      ON o.order_id = p.order_id
    GROUP BY p.order_id
)
SELECT
    o.region,
    COUNT(*) AS orders,
    COALESCE(SUM(p.captured - p.refunded), 0::NUMERIC)
        AS net_payment_flow,
    COALESCE(SUM(i.quantity), 0::BIGINT) AS quantity
FROM selected_orders AS o
LEFT JOIN item_by_order AS i ON i.order_id = o.order_id
LEFT JOIN payment_by_order AS p ON p.order_id = o.order_id
GROUP BY o.region;
```

Ý tưởng: **đẩy bộ lọc có chọn lọc xuống sớm**, chỉ tổng hợp những bảng con liên quan tập order được chọn.

Nhưng PostgreSQL có optimizer và có thể inline CTE; không mặc định viết thành CTE là nhanh hơn. Cần xem EXPLAIN, số hàng trung gian và phạm vi chọn lọc.

---

## 9. Điều kiện thời gian: half-open interval

Một báo cáo “tháng Hai 2026 theo UTC” nên có điều kiện:

```sql
WHERE ordered_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-03-01 00:00:00+00'
```

Đây là khoảng **[start, end)**: gồm đầu khoảng, không gồm cuối khoảng.

### 9.1. Tránh BETWEEN với mốc cuối ngày mơ hồ

Dạng:

```sql
WHERE ordered_at BETWEEN
    TIMESTAMPTZ '2026-02-01 00:00:00+00'
    AND TIMESTAMPTZ '2026-02-28 23:59:59+00'
```

sẽ bỏ các bản ghi có fractional seconds ở giây cuối. Nếu cố chèn `.999999` cũng dễ phụ thuộc độ chính xác và kiểu dữ liệu.

Dùng mốc đầu của tháng tiếp theo loại lỗi này:

```sql
ordered_at >= start_at AND ordered_at < end_exclusive
```

### 9.2. Vì sao không bao cột bằng DATE trong WHERE?

Truy vấn:

```sql
WHERE ordered_at::DATE = DATE '2026-02-01'
```

có thể khó tận dụng index B-tree thông thường trên `ordered_at` vì biểu thức thay đổi cột và kết quả phụ thuộc timezone của session khi cast `TIMESTAMPTZ` sang `DATE`.

Dạng range so sánh trực tiếp cột:

```sql
WHERE ordered_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-02-02 00:00:00+00'
```

thường là cách diễn đạt **sargable** hơn cho B-tree trên `ordered_at`.

### 9.3. Sargability là gì?

Một điều kiện được gọi là **sargable** trong ngữ cảnh phổ biến khi PostgreSQL có thể dùng cấu trúc index phù hợp để thu hẹp phạm vi tìm kiếm, thay vì phải tính hàm trên từng hàng trước khi so sánh.

Ví dụ:

| Ít thuận lợi cho index thường | Thường thuận lợi hơn |
| --- | --- |
| `ordered_at::DATE = DATE '2026-02-01'` | `ordered_at >= start AND ordered_at < end` |
| `LOWER(region) = 'north'` với index chỉ trên region | So cột đã chuẩn hóa hoặc expression index `LOWER(region)` |
| `EXTRACT(YEAR FROM ordered_at) = 2026` | Khoảng thời gian năm 2026 |
| `amount + 10 > 100` | `amount > 90`, nếu phép biến đổi bảo toàn semantics |

Không phải mọi hàm trên cột đều không dùng index: PostgreSQL hỗ trợ **expression index**. Vấn đề là index và biểu thức truy vấn có phù hợp hay không.

### 9.4. Ngày nghiệp vụ theo múi giờ

“Nửa đêm ngày 1/2 tại Việt Nam” không phải `2026-02-01 00:00:00+00`. Ví dụ:

```sql
-- Khoảng ngày 2026-02-01 theo Asia/Ho_Chi_Minh,
-- biểu diễn bằng mốc có offset +07.
WHERE ordered_at >= TIMESTAMPTZ '2026-02-01 00:00:00+07'
  AND ordered_at <  TIMESTAMPTZ '2026-02-02 00:00:00+07'
```

Điều kiện vẫn so sánh trực tiếp `TIMESTAMPTZ` với mốc thời gian tuyệt đối. Với timezone có DST, cần xác định hai mốc đầu/cuối theo timezone nghiệp vụ thay vì giả định một ngày luôn dài đúng 24 giờ.

---

## 10. Gom nhóm theo ngày, tuần, tháng

### 10.1. Theo ngày UTC

```sql
SELECT
    (ordered_at AT TIME ZONE 'UTC')::DATE AS day_utc,
    region,
    COUNT(*) AS orders,
    SUM(total_amount) AS order_value
FROM report_opt_lab.orders
WHERE ordered_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-02-01 00:00:00+00'
GROUP BY day_utc, region
ORDER BY day_utc, region;
```

Dùng `AT TIME ZONE 'UTC'` để tạo ngày UTC không phụ thuộc timezone hiển thị mặc định của session. Cột `day_utc` có grain ngày UTC.

### 10.2. Theo tháng UTC

```sql
SELECT
    DATE_TRUNC('month', ordered_at AT TIME ZONE 'UTC')
        AS month_utc,
    region,
    COUNT(*) AS orders
FROM report_opt_lab.orders
GROUP BY month_utc, region
ORDER BY month_utc, region;
```

Ở đây `DATE_TRUNC` trả timestamp without time zone vì đầu vào đã là `ordered_at AT TIME ZONE 'UTC'`.

### 10.3. Cẩn thận tuần ISO

Khi báo cáo theo tuần:

```sql
SELECT
    DATE_TRUNC('week', ordered_at AT TIME ZONE 'UTC')::DATE
        AS week_start_utc,
    COUNT(*)
FROM report_opt_lab.orders
GROUP BY week_start_utc
ORDER BY week_start_utc;
```

Thường dễ hơn so với GROUP BY riêng `EXTRACT(WEEK)` mà bỏ qua **ISO year**, đặc biệt những ngày cuối năm/đầu năm. Một tuần ISO có thể thuộc năm ISO khác năm lịch của ngày.

### 10.4. Date bucketing và index

Nếu WHERE lọc theo raw `ordered_at`, index thời gian có thể được dùng để thu hẹp số hàng rồi mới bucket. Nếu query muốn tra cứu trực tiếp bucket được tính sẵn, có thể cân nhắc generated column hoặc expression index phù hợp với chính sách timezone.

Không mặc định tạo index cho mọi `date_trunc('day', ordered_at)`. Nhiều query vẫn phải đọc rất nhiều hàng và aggregate; index thêm có chi phí ghi/duy trì.

---

## 11. COUNT DISTINCT theo ngày: tránh cộng số khách sai

Báo cáo:

```sql
SELECT
    (ordered_at AT TIME ZONE 'UTC')::DATE AS day_utc,
    COUNT(DISTINCT customer_id) AS unique_customers
FROM report_opt_lab.orders
GROUP BY day_utc
ORDER BY day_utc;
```

Mỗi customer có thể có nhiều đơn trong một ngày, nên cần DISTINCT nếu chỉ đếm một lần mỗi khách/ngày.

### 11.1. Không cộng distinct counts từ các ngày để ra distinct toàn tháng

Ví dụ customer #10 mua vào cả ngày 1 và ngày 2:

```text
Ngày 1: unique_customers = 1
Ngày 2: unique_customers = 1

Tổng bằng 2 không có nghĩa tháng có 2 khách khác nhau.
Tháng chỉ có 1 khách khác nhau trong ví dụ này.
```

**Distinct không phải chỉ số cộng dồn độc lập giữa các nhóm có thể chồng lấn.**

Nếu dashboard cần unique customers theo tháng, phải tính distinct trên toàn khoảng tháng hoặc dùng một cấu trúc dữ liệu/thuật toán hỗ trợ union distinct đúng.

### 11.2. Pre-aggregate không phải phép màu

Nếu dữ liệu cực lớn, pre-aggregate theo `(day, customer_id)` có thể giảm số hàng trùng. Nhưng khi tổng hợp nhiều ngày thành tháng, vẫn cần loại customer_id trùng giữa các ngày.

Không thay `COUNT(DISTINCT)` bằng `SUM(daily_unique_customers)` nếu không có chứng minh các tập khách hàng rời nhau.

### 11.3. Approximate distinct

Một số hệ sinh thái sử dụng HyperLogLog hoặc thuật toán sketch qua extension/công cụ ngoài để ước lượng số lượng distinct và hợp nhất sketch giữa các nhóm. Đây **không phải tính năng mặc định tương đương COUNT(DISTINCT) trong PostgreSQL core**.

Nếu dùng approximate distinct:

- Ghi rõ sai số cho phép.
- Xác định extension/phiên bản đang được cài.
- Phân biệt báo cáo tài chính cần exact count với dashboard chấp nhận approximation.
- Kiểm tra khả năng merge và tính đúng theo interval, tenant, filter.

---

## 12. Trung bình, tỷ lệ và phép chia an toàn

### 12.1. Average order value

Giả sử AOV chỉ tính đơn PAID:

```sql
SELECT
    region,
    COALESCE(
        SUM(total_amount) FILTER (WHERE status = 'PAID'),
        0::NUMERIC
    ) AS paid_order_value,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_order_count,
    ROUND(
        SUM(total_amount) FILTER (WHERE status = 'PAID')
        / NULLIF(
            COUNT(*) FILTER (WHERE status = 'PAID'),
            0
        ),
        2
    ) AS avg_paid_order_value
FROM report_opt_lab.orders
GROUP BY region;
```

`NULLIF(...,0)` tránh chia cho 0. Nếu không có đơn PAID, AOV trả NULL để thể hiện không có mẫu số, thường chính xác hơn trả 0.

### 12.2. Không tính trung bình của trung bình nếu không có trọng số

Ví dụ:

```text
Ngày A: 1 đơn, AOV = 1000
Ngày B: 99 đơn, AOV = 10

(1000 + 10) / 2 = 505   <- trung bình sai theo mỗi đơn
(1*1000 + 99*10)/100 = 19.9 <- đúng theo mỗi đơn
```

Khi roll-up các nhóm, cần giữ **sum và count** để tính average có trọng số, không chỉ giữ cột avg.

### 12.3. Tỷ lệ thanh toán

```sql
SELECT
    region,
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders,
    ROUND(
        100::NUMERIC
        * COUNT(*) FILTER (WHERE status = 'PAID')
        / NULLIF(COUNT(*), 0),
        2
    ) AS paid_percent
FROM report_opt_lab.orders
GROUP BY region;
```

`100::NUMERIC` đảm bảo phép toán thập phân phù hợp. Đơn vị của paid_percent ở đây là **phần trăm**, không phải số từ 0 đến 1.

### 12.4. Không dùng FLOAT cho tiền tệ nếu cần độ chính xác thập phân

PostgreSQL `NUMERIC(p,s)` phù hợp cho giá trị tiền tệ theo chính sách làm tròn rõ ràng. `REAL` và `DOUBLE PRECISION` có biểu diễn nhị phân gần đúng, có thể làm sai kết quả so sánh/tổng tiền nếu dùng như số tiền exact.

Nếu hệ thống đa tiền tệ, phải group theo currency hoặc chuyển đổi theo tỷ giá có chính sách rõ. Không SUM VND và USD trực tiếp rồi gọi kết quả là revenue.

---

## 13. JOIN một-nhiều và LEFT JOIN khi muốn nhóm có 0

Bài toán: hiển thị **mọi region**, kể cả region không có đơn trong phạm vi ngày.

Nếu chỉ GROUP BY từ orders:

```sql
SELECT region, COUNT(*)
FROM report_opt_lab.orders
WHERE ordered_at >= TIMESTAMPTZ '2030-01-01 00:00:00+00'
GROUP BY region;
```

sẽ trả 0 hàng, không phải ba region với số 0.

### 13.1. Dùng bảng dimension hoặc danh sách region

```sql
WITH regions(region) AS (
    VALUES ('NORTH'::TEXT), ('CENTRAL'), ('SOUTH')
)
SELECT
    r.region,
    COUNT(o.order_id) AS order_count,
    COALESCE(SUM(o.total_amount), 0::NUMERIC)
        AS order_value
FROM regions AS r
LEFT JOIN report_opt_lab.orders AS o
  ON o.region = r.region
 AND o.ordered_at >= TIMESTAMPTZ '2030-01-01 00:00:00+00'
 AND o.ordered_at <  TIMESTAMPTZ '2030-02-01 00:00:00+00'
GROUP BY r.region
ORDER BY r.region;
```

Kết quả có ba region, mỗi region có order_count=0 và order_value=0.

### 13.2. COUNT(*) sau LEFT JOIN dễ sai

Với LEFT JOIN, nếu region không khớp order nào, PostgreSQL vẫn tạo **một hàng** từ phía trái với cột order NULL.

Vì vậy:

```sql
COUNT(*)          -- có thể bằng 1 cho region không có order
COUNT(o.order_id) -- bằng 0 khi không có order khớp
```

Hãy đếm **khóa không NULL của bảng phải** khi muốn số hàng liên quan sau LEFT JOIN.

### 13.3. Đặt bộ lọc bảng phải trong ON

Nếu viết:

```sql
FROM regions r
LEFT JOIN orders o ON o.region = r.region
WHERE o.ordered_at >= ...
```

thì WHERE loại các hàng có `o.ordered_at IS NULL`, khiến LEFT JOIN có thể cư xử như INNER JOIN với những region không có order.

Đặt điều kiện thời gian của orders trong `ON` khi mục tiêu là **giữ mọi region**, hoặc cấu trúc query phù hợp khác.

---

## 14. Báo cáo có các ngày không phát sinh đơn

Một chart theo ngày cần trục ngày liên tục, kể cả ngày không có dữ liệu.

### 14.1. Tạo dãy ngày bằng generate_series

```sql
WITH days AS (
    SELECT d::DATE AS day_utc
    FROM generate_series(
        DATE '2026-02-01',
        DATE '2026-02-10',
        INTERVAL '1 day'
    ) AS g(d)
),
daily AS (
    SELECT
        (ordered_at AT TIME ZONE 'UTC')::DATE AS day_utc,
        COUNT(*) AS orders,
        SUM(total_amount) AS order_value
    FROM report_opt_lab.orders
    WHERE ordered_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
      AND ordered_at <  TIMESTAMPTZ '2026-02-11 00:00:00+00'
    GROUP BY day_utc
)
SELECT
    days.day_utc,
    COALESCE(daily.orders, 0::BIGINT) AS orders,
    COALESCE(daily.order_value, 0::NUMERIC)
        AS order_value
FROM days
LEFT JOIN daily USING (day_utc)
ORDER BY days.day_utc;
```

### 14.2. Tại sao aggregate trước rồi LEFT JOIN?

Nếu JOIN từng order với dãy ngày trước rồi aggregate, query có thể tạo nhiều hàng trung gian không cần thiết. Pre-aggregate orders về grain ngày thường giúp số hàng JOIN ít hơn, đặc biệt khi dữ liệu có nhiều đơn mỗi ngày.

### 14.3. Sinh ngày chỉ trong phạm vi yêu cầu

Không tạo dãy hàng triệu ngày nếu dashboard chỉ cần 30 ngày. Bộ lọc ngày phải có boundary rõ, timezone phù hợp và giới hạn đầu ra.

---

## 15. GROUPING SETS, ROLLUP và CUBE

Báo cáo quản trị thường cần nhiều cấp:

- Theo ngày và region.
- Chỉ theo ngày.
- Chỉ theo region.
- Tổng toàn bộ.

Viết bốn query rồi UNION ALL có thể đọc và aggregate nhiều lần. PostgreSQL có **GROUPING SETS** để biểu đạt nhiều cấp tổng hợp trong một statement.

### 15.1. GROUPING SETS

```sql
SELECT
    (ordered_at AT TIME ZONE 'UTC')::DATE AS day_utc,
    region,
    COUNT(*) AS orders,
    SUM(total_amount) AS order_value
FROM report_opt_lab.orders
WHERE ordered_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-03-01 00:00:00+00'
GROUP BY GROUPING SETS (
    ((ordered_at AT TIME ZONE 'UTC')::DATE, region),
    ((ordered_at AT TIME ZONE 'UTC')::DATE),
    (region),
    ()
)
ORDER BY day_utc NULLS LAST, region NULLS LAST;
```

Các grouping sets tương ứng:

1. `(day_utc, region)`: chi tiết.
2. `(day_utc)`: tổng theo ngày.
3. `(region)`: tổng theo region.
4. `()`: grand total.

### 15.2. ROLLUP

```sql
SELECT
    region,
    status,
    COUNT(*) AS orders
FROM report_opt_lab.orders
GROUP BY ROLLUP (region, status)
ORDER BY region NULLS LAST, status NULLS LAST;
```

`ROLLUP(region,status)` cho:

- (region, status).
- (region).
- Grand total.

Thứ tự các cột trong ROLLUP quyết định các cấp subtotal.

### 15.3. CUBE

```sql
SELECT
    region,
    status,
    COUNT(*) AS orders
FROM report_opt_lab.orders
GROUP BY CUBE (region, status);
```

`CUBE(region,status)` tạo mọi tổ hợp grouping keys: `(region,status)`, `(region)`, `(status)` và `()`.

Với nhiều chiều, số grouping sets có thể tăng theo cấp số mũ. Không dùng CUBE với hàng chục dimension mà không có giới hạn và kế hoạch tài nguyên.

### 15.4. NULL trong subtotal cần phân biệt NULL dữ liệu

Khi dimension có NULL thật, chỉ nhìn `region IS NULL` không phân biệt được “region thiếu” và “hàng tổng”.

Sử dụng `GROUPING(...)`:

```sql
SELECT
    region,
    status,
    GROUPING(region) AS region_rolled_up,
    GROUPING(status) AS status_rolled_up,
    COUNT(*) AS orders
FROM report_opt_lab.orders
GROUP BY ROLLUP (region, status)
ORDER BY region_rolled_up, status_rolled_up, region, status;
```

`GROUPING(column)` cho biết cột có bị bỏ khỏi grouping set ở hàng kết quả đó hay không.

### 15.5. GROUPING SETS không đảm bảo nhanh hơn trong mọi điều kiện

Một statement có thể giảm công việc lặp, nhưng vẫn cần tính nhiều nhóm, quản lý bộ nhớ và sắp xếp. Với tổ hợp nhóm rất lớn, nhiều grouping sets có thể tốn tài nguyên. Cần đo plan và chi phí thực tế.

---

## 16. Lọc sớm có phải lúc nào cũng tốt?

Nguyên tắc thực hành thường hữu ích là **giảm cardinality trước những phép JOIN/GROUP BY đắt**.

Ví dụ nếu chỉ báo cáo tháng Hai:

```sql
SELECT region, COUNT(*), SUM(total_amount)
FROM report_opt_lab.orders
WHERE ordered_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-03-01 00:00:00+00'
GROUP BY region;
```

Tập input có thể nhỏ hơn tổng bảng nếu điều kiện thời gian chọn lọc.

Nhưng:

- PostgreSQL optimizer có thể đã tự đẩy predicate xuống.
- Một điều kiện không chọn lọc (90% bảng) có thể khiến Seq Scan tốt hơn Index Scan.
- Một index scan phải truy cập heap rời rạc nhiều lần có thể đắt hơn quét tuần tự.
- Điều kiện `HAVING SUM(...) > ...` **không luôn có thể** đẩy xuống WHERE mà không đổi semantics.

### 16.1. WHERE không thay HAVING được

```sql
SELECT customer_id, SUM(total_amount) AS total
FROM report_opt_lab.orders
GROUP BY customer_id
HAVING SUM(total_amount) > 1000;
```

Không tương đương với:

```sql
WHERE total_amount > 1000
```

vì khách có nhiều đơn nhỏ tổng trên 1.000 có thể bị loại sai.

### 16.2. HAVING với điều kiện không phụ thuộc aggregate

Nếu một điều kiện chỉ phụ thuộc grouping key, PostgreSQL có thể di chuyển/xử lý theo cách tối ưu, nhưng mã SQL rõ nghĩa hơn khi đưa lọc hàng phù hợp vào WHERE:

```sql
SELECT region, COUNT(*)
FROM report_opt_lab.orders
WHERE region = 'NORTH'
GROUP BY region;
```

Không đặt mọi điều kiện vào HAVING chỉ vì query có GROUP BY.

---

## 17. Index cho bộ lọc báo cáo: B-tree

Giả sử truy vấn lặp nhiều:

```sql
SELECT region, SUM(total_amount)
FROM report_opt_lab.orders
WHERE ordered_at >= :from_time
  AND ordered_at <  :to_time
GROUP BY region;
```

Một index cần benchmark:

```sql
CREATE INDEX idx_report_orders_ordered_at
ON report_opt_lab.orders (ordered_at);

ANALYZE report_opt_lab.orders;
```

### 17.1. Khi nào index thời gian giúp?

Nếu chọn một khoảng ngắn trong bảng nhiều năm, index B-tree theo thời gian có thể giảm số hàng cần đọc. Nếu cần đọc 70–90% bảng, Seq Scan hoặc parallel scan có thể nhanh hơn.

Index không giúp bỏ chi phí aggregate trên mọi hàng đã chọn. Nó chỉ giúp **tìm và đọc tập ứng viên** hiệu quả trong trường hợp phù hợp.

### 17.2. Composite index theo status và thời gian

Query chủ yếu:

```sql
WHERE status = 'PAID'
  AND ordered_at >= ...
  AND ordered_at < ...
```

có thể cân nhắc:

```sql
CREATE INDEX idx_report_orders_status_date
ON report_opt_lab.orders (status, ordered_at);
```

Trong mô hình B-tree phổ biến, equality trên cột đứng đầu rồi range trên cột tiếp theo là pattern hữu ích. Nhưng nếu hầu hết hàng đều PAID, độ chọn lọc status thấp, thứ tự cột và sự cần thiết của index vẫn cần benchmark.

### 17.3. Đừng tự tạo mọi thứ tự composite

Ba index:

```text
(status, ordered_at)
(ordered_at, status)
(region, ordered_at, status)
```

không mặc định đều cần. Mỗi index tăng disk, WAL và chi phí INSERT/UPDATE/DELETE. Đọc `EXPLAIN` và xem query patterns trước khi bổ sung.

### 17.4. Index có thể hỗ trợ GROUP BY?

Một index có thứ tự phù hợp với các grouping keys có thể giúp một số plan tận dụng dữ liệu đã có thứ tự và giảm/bỏ một bước Sort; tuy nhiên query lọc, JOIN và cách planner chọn access path còn quyết định.

Không chỉ nhìn `GROUP BY region` rồi kết luận index region sẽ giúp SUM hàng triệu dòng trở thành O(1). Aggregate vẫn phải xử lý những giá trị đầu vào cần thiết trừ khi có summary phù hợp.

---

## 18. Partial index cho báo cáo có điều kiện

Nếu phần lớn truy vấn báo cáo chỉ xét đơn PAID, có thể xem xét partial index:

```sql
CREATE INDEX idx_report_paid_date
ON report_opt_lab.orders (ordered_at)
WHERE status = 'PAID';
```

Nó chỉ chứa hàng PAID, có thể nhỏ hơn index toàn bảng.

Truy vấn:

```sql
SELECT
    (ordered_at AT TIME ZONE 'UTC')::DATE AS day_utc,
    SUM(total_amount) AS paid_order_value
FROM report_opt_lab.orders
WHERE status = 'PAID'
  AND ordered_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-03-01 00:00:00+00'
GROUP BY day_utc;
```

có predicate phù hợp với partial index.

### 18.1. Partial index không dùng cho mọi truy vấn conditional aggregation

Truy vấn:

```sql
SELECT
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid,
    COUNT(*) FILTER (WHERE status = 'CANCELED') AS canceled
FROM report_opt_lab.orders
WHERE ordered_at >= ...
```

cần xét **cả PAID và CANCELED**. Index chỉ gồm PAID không tự đáp ứng toàn bộ phạm vi của query. Cũng không thể coi điều kiện nằm bên trong `FILTER` là tương đương việc toàn statement chỉ đọc hàng PAID.

### 18.2. Prepared statements và generic plan

PostgreSQL cần xác định query predicate suy ra predicate partial index. Với query tham số hóa (ví dụ `status = $1`), một generic plan không nhất thiết chứng minh `$1 = 'PAID'` cho mọi lần gọi, nên có thể không dùng partial index như bạn mong đợi.

Cần kiểm tra kế hoạch trong môi trường sử dụng parameter thực, custom/generic plan và phiên bản PostgreSQL, không chỉ EXPLAIN với literal.

---

## 19. Covering index và index-only scan

Một index có cột `INCLUDE`:

```sql
CREATE INDEX idx_report_paid_date_cover
ON report_opt_lab.orders (ordered_at)
INCLUDE (region, total_amount)
WHERE status = 'PAID';
```

có thể giúp một số query đọc `ordered_at`, `region` và `total_amount` mà không phải truy cập heap thường xuyên, nếu các điều kiện khác đáp ứng.

### 19.1. INCLUDE không phải indexed key cho range/sort

`region` và `total_amount` trong `INCLUDE` là **payload**, không được dùng giống các key đầu của B-tree để điều hướng tìm kiếm theo range và thứ tự.

Nếu query cần `WHERE region='NORTH'` với độ chọn lọc cao, một index khác có region là key có thể phù hợp hơn.

### 19.2. Index-only scan không có nghĩa luôn không đọc heap

PostgreSQL MVCC cần xác định tuple visible theo snapshot. Index-only scan có thể dựa vào **visibility map** để tránh heap fetch trên những page all-visible.

Nếu bảng liên tục UPDATE/DELETE, visibility map có thể chưa đánh dấu đủ all-visible, nên vẫn có heap fetch dù index chứa đủ cột.

Cần xem:

```text
Index Only Scan ...
  Heap Fetches: ...
```

Không tuyên bố covering index chắc chắn làm báo cáo đọc 0 heap pages.

### 19.3. Covering index cũng có chi phí ghi

INCLUDE thêm dữ liệu vào index. Một UPDATE làm thay đổi included column có thể ảnh hưởng khả năng HOT, làm tăng write amplification. Hãy đánh đổi tốc độ report với write throughput.

---

## 20. BRIN cho bảng sự kiện lớn theo thời gian

Với bảng log/event **append-heavy** mà `ordered_at` hoặc `event_at` có tương quan mạnh với vị trí vật lý, BRIN có thể là một ứng viên nhỏ gọn:

```sql
CREATE INDEX idx_report_orders_ordered_at_brin
ON report_opt_lab.orders
USING BRIN (ordered_at);
```

### 20.1. BRIN khác B-tree

- **B-tree:** chỉ mục từng giá trị khóa, tốt cho range/equality chọn lọc, có kích thước/maintenance riêng.
- **BRIN:** tóm tắt dữ liệu theo các **page ranges**, có thể rất nhỏ và hiệu quả khi dữ liệu có tương quan vật lý.

BRIN thường trả các dải trang ứng viên và cần recheck vì thông tin tóm tắt có thể thô. Nếu dữ liệu timestamp phân bố ngẫu nhiên trên mọi trang, BRIN có thể kém chọn lọc.

### 20.2. Không tạo BRIN chỉ vì cột là TIMESTAMPTZ

Cần xem:

- Bảng lớn đến mức nào?
- Dữ liệu có tương quan với thứ tự INSERT/physical pages không?
- Các query lấy khoảng thời gian dài hay rất ngắn?
- Hệ thống có thường xuyên UPDATE timestamp không?
- Mức độ heap recheck và số page bị đọc?

Trên lab 15.000 hàng, B-tree/Seq Scan có thể hợp lý hơn; BRIN là bài học về workload lớn.

---

## 21. Partition pruning trong báo cáo thời gian

Với bảng hàng trăm triệu hoặc hàng tỷ dòng, phân vùng theo thời gian có thể giúp giới hạn số partition phải quét.

Ví dụ schema khái niệm:

```sql
CREATE TABLE analytics_events (
    event_id BIGINT NOT NULL,
    event_at TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL,
    value NUMERIC(14,2)
) PARTITION BY RANGE (event_at);

CREATE TABLE analytics_events_2026_01
PARTITION OF analytics_events
FOR VALUES FROM ('2026-01-01 00:00:00+00')
             TO ('2026-02-01 00:00:00+00');
```

Một WHERE dùng trực tiếp partition key:

```sql
WHERE event_at >= TIMESTAMPTZ '2026-01-10 00:00:00+00'
  AND event_at <  TIMESTAMPTZ '2026-01-20 00:00:00+00'
```

có thể cho phép PostgreSQL loại partition không liên quan (**partition pruning**).

### 21.1. Partition không tự làm aggregate rẻ

Nếu report phải quét toàn bộ năm với 12 partition, engine vẫn cần xử lý dữ liệu của các partition liên quan. Partition có thể giúp quản lý retention, maintenance và pruning, nhưng không tạo summary tự động.

### 21.2. Tránh bao partition key bằng biểu thức khó suy luận

Nếu query chủ yếu dùng `event_at::DATE = ...` trên partition key TIMESTAMPTZ, pruning/indexability có thể kém rõ ràng hơn range raw timestamp. Nên biểu diễn khoảng thời gian chính xác theo partitioning scheme.

### 21.3. Partition-wise aggregate

PostgreSQL có thể tận dụng partition-wise aggregation trong những điều kiện và cấu hình hỗ trợ. Nó không tự áp dụng cho mọi GROUP BY, đặc biệt khi grouping key không phù hợp partition key hoặc phép tổng hợp không thể phân rã theo cách đó.

Hãy quan sát plan thật thay vì bật tùy chọn rồi kỳ vọng tốc độ tăng theo số partition.

---

## 22. HashAggregate và GroupAggregate: hiểu kế hoạch thực thi

Một truy vấn:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    region, status, COUNT(*), SUM(total_amount)
FROM report_opt_lab.orders
GROUP BY region, status;
```

có thể chọn `HashAggregate`, `GroupAggregate` hoặc kế hoạch song song tùy dữ liệu và thống kê.

### 22.1. HashAggregate

Mô hình:

```text
Scan rows
   |
   v
Hash table:
  key=(region,status)
  state=(count,sum)
   |
   v
Emit one row per group
```

Phù hợp khi số nhóm và aggregate states có thể quản lý hiệu quả trong bộ nhớ hoặc cơ chế batch/spill được hỗ trợ.

Nếu số nhóm lớn và memory limit bị vượt, PostgreSQL có thể chia batch hoặc dùng temporary disk. Không mặc định hash aggregate luôn nằm trọn trong RAM.

### 22.2. GroupAggregate

Mô hình:

```text
Rows đã được sắp theo group keys
              |
              v
GroupAggregate xử lý từng nhóm
              |
              v
Kết quả
```

Nếu input chưa có thứ tự, planner có thể thêm `Sort`. Nếu index cung cấp thứ tự hữu ích, có thể tránh/giảm sort tùy plan.

### 22.3. Số nhóm ảnh hưởng trực tiếp

`GROUP BY region` có ba nhóm trong lab; `GROUP BY customer_id` có tới khoảng 1.000 nhóm; `GROUP BY order_id` có 15.000 nhóm. Hash table, sorting và output volume tăng khi cardinality tăng.

Đừng GROUP BY thêm những cột không cần thiết: tăng số nhóm có thể phá mục tiêu aggregation và làm query chậm.

### 22.4. Đọc memory, batch và temporary I/O

Tùy phiên bản PostgreSQL, EXPLAIN có thể hiển thị các chi tiết như:

```text
HashAggregate ...
  Batches: ...
  Memory Usage: ...
  Disk Usage: ...
```

hoặc ở Sort:

```text
Sort Method: external merge  Disk: ...
```

Các dòng trên chỉ là **mẫu cấu trúc**, không phải kết quả benchmark của lab.

Spill ra disk là tín hiệu cần điều tra, nhưng không tự chứng minh query sai hoặc bắt buộc tăng `work_mem` ngay lập tức.

---

## 23. Parallel aggregation

Một báo cáo lớn có thể tận dụng nhiều worker:

```text
Parallel Seq Scan
        |
        v
  Partial Aggregate (mỗi worker)
        |
        v
 Gather / Gather Merge
        |
        v
 Finalize Aggregate
        |
        v
       Output
```

Ví dụ plan có thể gồm `Partial HashAggregate` và `Finalize HashAggregate`.

### 23.1. Khi nào parallel aggregation giúp?

Khi đủ dữ liệu cần xử lý và phần việc có thể song song hiệu quả, việc aggregate từng phần ở nhiều worker rồi hợp nhất có thể giảm thời gian chạy.

Nhưng parallelization có overhead:

- Khởi tạo worker.
- Truyền và hợp nhất dữ liệu.
- Chia sẻ I/O.
- Memory sử dụng theo worker.
- Một số hàm aggregate hoặc expression không hỗ trợ partial/parallel execution tương đương.

Không phải mọi aggregate, DISTINCT, ordered-set aggregate hoặc user-defined function đều có thể được chia nhỏ hiệu quả.

### 23.2. Đừng chỉnh max_parallel_workers_per_gather theo cảm tính

Một query nhanh hơn với 4 worker không có nghĩa 20 dashboard queries cùng lúc đều nhanh hơn nếu mỗi query dùng 4 worker. Tổng CPU/I/O và resource contention có thể tăng.

Cần đo cả **latency một query** và **throughput khi nhiều query đồng thời**.

### 23.3. Parallel query và COUNT DISTINCT

Một số aggregate có DISTINCT/ORDER BY hoặc các đặc tính khác có hạn chế nhất định đối với partial aggregation. Đừng mặc định mọi `COUNT(DISTINCT ...)` có cùng khả năng parallel như `COUNT(*)`.

---

## 24. work_mem, hash_mem_multiplier và spill

Các aggregate và sort có thể cần bộ nhớ cho:

- Hash tables.
- Sort runs.
- Distinct tracking.
- Join/hash join.
- Intermediate results.

Trong PostgreSQL, `work_mem` là một giới hạn quan trọng cho nhiều operation, nhưng **không phải một budget bộ nhớ duy nhất cho cả query**.

### 24.1. Vì sao tăng work_mem có thể nguy hiểm?

Một query có thể chứa nhiều Sort/Hash nodes; nhiều query chạy đồng thời; mỗi worker song song có thể tiêu thụ memory cho các operation tương ứng.

Ví dụ giả định:

```text
20 queries đồng thời
  x 3 memory-heavy nodes
  x 4 workers/participants
  x memory budget
= mức tiêu thụ có thể rất lớn
```

Đây chỉ là cách cảnh báo khả năng nhân tài nguyên, không phải công thức dự đoán RAM chính xác. Việc cấp phát thực còn phụ thuộc phiên bản, node và khối lượng dữ liệu.

### 24.2. hash_mem_multiplier

Một số hash operations có memory limit dựa trên `work_mem` và `hash_mem_multiplier`, tùy phiên bản/cơ chế. Không mặc định mọi node dùng đúng `work_mem` và không tự nâng các thông số ở mức server chỉ vì một báo cáo bị spill.

### 24.3. SET LOCAL trong thử nghiệm

Khi đã có quyền và môi trường test:

```sql
BEGIN;

SET LOCAL work_mem = '64MB';

EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, SUM(total_amount)
FROM report_opt_lab.orders
GROUP BY customer_id;

ROLLBACK;
```

Đây là cách thử scope một transaction, không thay configuration lâu dài. Giá trị 64MB chỉ là minh họa; cần benchmark với tải thật và xem tổng concurrency.

### 24.4. Tối ưu hình dạng query trước khi thêm RAM

Nếu query đang JOIN nhân 10 lần số hàng, tăng work_mem có thể che triệu chứng nhưng vẫn tính sai và tốn thêm tài nguyên. Sửa grain/JOIN/WHERE trước, sau đó mới xem memory tuning.

---

## 25. CTE: rõ nghĩa nhưng không phải luôn nhanh hơn

CTE giúp chia truy vấn phức tạp thành các bước logic:

```sql
WITH filtered AS (
    SELECT order_id, region, total_amount
    FROM report_opt_lab.orders
    WHERE status = 'PAID'
),
totals AS (
    SELECT region, SUM(total_amount) AS paid_amount
    FROM filtered
    GROUP BY region
)
SELECT * FROM totals;
```

CTE có thể làm mã dễ hiểu hơn, nhưng **không tự buộc PostgreSQL chạy nhanh hơn**. Trên những phiên bản hiện đại, CTE SELECT đơn giản thường có thể được inline theo điều kiện; trong các trường hợp khác nó có thể được materialize.

### 25.1. MATERIALIZED và NOT MATERIALIZED

PostgreSQL hỗ trợ cú pháp điều khiển một số hành vi:

```sql
WITH filtered AS MATERIALIZED (
    SELECT *
    FROM report_opt_lab.orders
    WHERE status = 'PAID'
)
SELECT region, COUNT(*)
FROM filtered
GROUP BY region;
```

và:

```sql
WITH filtered AS NOT MATERIALIZED (
    SELECT *
    FROM report_opt_lab.orders
    WHERE status = 'PAID'
)
SELECT region, COUNT(*)
FROM filtered
GROUP BY region;
```

Hai tùy chọn có điều kiện và giới hạn áp dụng; không dùng như mẹo “MATERIALIZED nhanh” hay “NOT MATERIALIZED luôn nhanh”.

- Materialization có thể giúp khi một kết quả trung gian đắt được dùng nhiều lần.
- Nhưng nó cũng có thể ngăn predicate pushdown hoặc tạo chi phí lưu trung gian.
- Inlining có thể cho optimizer nhiều cơ hội, nhưng cũng có thể tính lại biểu thức nếu được dùng nhiều lần.

### 25.2. Tránh chia CTE tới mức nhân việc

Nếu viết năm CTE mỗi cái scan toàn orders để tính một metric, planner có thể hoặc không thể gộp hiệu quả. Có thể xem xét conditional aggregation tính nhiều metric trong **một lần nhóm**.

---

## 26. Nhiều báo cáo trong một lần quét

Một dashboard muốn:

- Tổng số đơn.
- Số PAID.
- Số REFUNDED.
- Tổng tiền PAID.
- Tổng tiền của đơn REFUNDED.
- Khách duy nhất.

Một statement có thể gom các metric:

```sql
SELECT
    region,
    COUNT(*) AS orders,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders,
    COUNT(*) FILTER (WHERE status = 'REFUNDED')
        AS refunded_orders,
    COALESCE(
        SUM(total_amount) FILTER (WHERE status = 'PAID'),
        0::NUMERIC
    ) AS paid_order_value,
    COALESCE(
        SUM(total_amount) FILTER (WHERE status = 'REFUNDED'),
        0::NUMERIC
    ) AS refunded_order_value,
    COUNT(DISTINCT customer_id) AS unique_customers
FROM report_opt_lab.orders
WHERE ordered_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-03-01 00:00:00+00'
GROUP BY region
ORDER BY region;
```

Lợi ích tiềm năng: các aggregate dùng chung dữ liệu đã scan.

Nhưng query càng nhiều aggregate, đặc biệt DISTINCT và ordered-set, memory/CPU vẫn tăng. Không hiểu “một scan” là “miễn phí mọi metric”.

### 26.1. Một scan còn tăng tính nhất quán snapshot

Trong PostgreSQL, một statement SELECT thông thường nhìn dữ liệu theo snapshot áp dụng cho statement đó. Nếu dashboard gửi sáu query riêng ở READ COMMITTED, mỗi query có thể nhận snapshot khác nhau và số liệu không khớp nhau trong lúc có ghi.

Một SELECT tổng hợp nhiều metric giúp chúng dựa trên **cùng snapshot** của statement, giảm một nguồn không nhất quán.

Nếu dashboard bắt buộc nhiều query có snapshot thống nhất, cân nhắc isolation/transaction như `REPEATABLE READ` theo thiết kế, nhưng đừng giữ transaction đọc quá lâu vì có thể ảnh hưởng MVCC cleanup.

---

## 27. LATERAL và correlated subqueries: khi nào nên dùng?

Đôi khi ứng dụng cần lấy vài số tổng hợp **cho từng hàng đã chọn**, ví dụ trang chỉ hiển thị 20 đơn gần nhất cùng số item của chúng.

Có thể dùng `LATERAL`:

```sql
SELECT
    o.order_id,
    o.ordered_at,
    item_stats.item_count,
    item_stats.item_amount
FROM (
    SELECT order_id, ordered_at
    FROM report_opt_lab.orders
    ORDER BY ordered_at DESC, order_id DESC
    LIMIT 20
) AS o
LEFT JOIN LATERAL (
    SELECT
        COUNT(*) AS item_count,
        COALESCE(SUM(line_amount), 0::NUMERIC)
            AS item_amount
    FROM report_opt_lab.order_items AS i
    WHERE i.order_id = o.order_id
) AS item_stats ON TRUE
ORDER BY o.ordered_at DESC, o.order_id DESC;
```

Nếu có index `order_items(order_id)`, đây có thể là cách tốt khi chỉ cần số liệu của ít order được chọn.

### 27.1. Correlated subquery có thể đắt với hàng triệu order

Nếu không giới hạn order, một subquery chạy theo từng order có thể tạo nhiều lần truy cập index hoặc scan. Planner có thể tối ưu một phần, nhưng không được giả định nó luôn biến thành một grouped join.

Với báo cáo toàn bộ orders theo ngày, **aggregate items một lần rồi JOIN** thường là phương án đáng so sánh.

### 27.2. Cần index trên khóa liên kết

```sql
CREATE INDEX idx_report_items_order_id
ON report_opt_lab.order_items (order_id);

CREATE INDEX idx_report_payments_order_id
ON report_opt_lab.payment_events (order_id);
```

Hai index này có thể giúp truy cập các hàng con của một order, đặc biệt với LATERAL/Nested Loop và một tập order nhỏ. Với báo cáo quét hầu hết bảng con, Seq Scan + HashAggregate vẫn có thể tốt hơn.

---

## 28. Window functions sau GROUP BY

Một báo cáo có thể cần:

- Tổng tiền mỗi ngày.
- Tổng tiền lũy kế.
- Thứ hạng ngày theo doanh thu.
- Tỷ trọng ngày trong tổng tháng.

Nên aggregate về grain ngày trước, sau đó dùng window function:

```sql
WITH daily AS (
    SELECT
        (ordered_at AT TIME ZONE 'UTC')::DATE AS day_utc,
        SUM(total_amount) FILTER (
            WHERE status = 'PAID'
        ) AS paid_order_value
    FROM report_opt_lab.orders
    WHERE ordered_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
      AND ordered_at <  TIMESTAMPTZ '2026-03-01 00:00:00+00'
    GROUP BY day_utc
)
SELECT
    day_utc,
    COALESCE(paid_order_value, 0::NUMERIC)
        AS paid_order_value,
    SUM(COALESCE(paid_order_value, 0::NUMERIC))
        OVER (
            ORDER BY day_utc
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_paid_value,
    RANK() OVER (
        ORDER BY paid_order_value DESC NULLS LAST
    ) AS revenue_rank
FROM daily
ORDER BY day_utc;
```

### 28.1. Vì sao aggregate trước?

Nếu tính window trên raw orders rồi tiếp tục GROUP BY, dễ lẫn grain và tăng số hàng phải sort/window-process. Pre-aggregate theo ngày làm dữ liệu đầu vào window nhỏ và ngữ nghĩa rõ hơn.

### 28.2. ROWS thay vì RANGE ở khung lũy kế

Với grain ngày một hàng/ngày, `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` diễn đạt rõ cộng dồn từng dòng. Nếu có nhiều hàng cùng ORDER BY key, mặc định RANGE có thể xử lý nhóm peers cùng lúc; cần hiểu window frame và thứ tự deterministic.

### 28.3. Lũy kế và ngày thiếu

Nếu cần hiển thị lũy kế qua mọi ngày, kể cả ngày không có đơn, trước hết tạo date series và LEFT JOIN daily rồi mới tính running SUM, để không mất các ngày rỗng trên trục biểu đồ.

---

## 29. Materialized view cho dashboard lặp lại

Nếu cùng một báo cáo theo ngày/region được gọi hàng trăm lần và dữ liệu nền ít thay đổi, tính lại GROUP BY toàn bộ bảng mỗi request có thể lãng phí.

PostgreSQL hỗ trợ `MATERIALIZED VIEW`:

```sql
CREATE MATERIALIZED VIEW report_opt_lab.daily_region_orders
AS
SELECT
    (ordered_at AT TIME ZONE 'UTC')::DATE AS day_utc,
    region,
    COUNT(*) AS order_count,
    COUNT(*) FILTER (WHERE status = 'PAID')
        AS paid_count,
    COALESCE(
        SUM(total_amount) FILTER (WHERE status = 'PAID'),
        0::NUMERIC
    ) AS paid_order_value
FROM report_opt_lab.orders
GROUP BY day_utc, region
WITH DATA;
```

Query dashboard:

```sql
SELECT *
FROM report_opt_lab.daily_region_orders
WHERE day_utc >= DATE '2026-02-01'
  AND day_utc <  DATE '2026-03-01'
ORDER BY day_utc, region;
```

### 29.1. Materialized view không tự cập nhật sau mỗi INSERT/UPDATE

Materialized view của PostgreSQL là **snapshot vật hóa** kết quả query ở thời điểm REFRESH, không phải bảng tự đồng bộ từng hàng khi base table đổi.

```sql
REFRESH MATERIALIZED VIEW
    report_opt_lab.daily_region_orders;
```

Lệnh refresh tính lại kết quả theo chính sách của PostgreSQL. Độ trễ dữ liệu là phần của thiết kế dashboard.

### 29.2. REFRESH CONCURRENTLY

Khi đáp ứng các điều kiện như có **unique index hợp lệ dựa trên cột, phủ mọi hàng** (không phải expression/partial unique index) và view đã được populate, có thể dùng:

```sql
CREATE UNIQUE INDEX idx_daily_region_orders_unique
ON report_opt_lab.daily_region_orders (day_utc, region);

REFRESH MATERIALIZED VIEW CONCURRENTLY
    report_opt_lab.daily_region_orders;
```

Cần kiểm tra quyền, phiên bản và giới hạn của `REFRESH ... CONCURRENTLY`. Concurrent refresh nhằm giảm chặn SELECT vào view, nhưng có chi phí riêng và không đồng nghĩa “miễn phí” hoặc cho phép vô hạn lượt refresh đồng thời cùng view.

### 29.3. Lựa chọn giữa normal view và materialized view

| Phương án | Độ tươi dữ liệu | Chi phí mỗi lần đọc |
| --- | --- | --- |
| View thường | Query base data theo snapshot truy vấn | Có thể aggregate lại |
| Materialized view | Snapshot tại lần REFRESH gần nhất | Đọc summary đã lưu |
| Summary table incremental | Gần thời gian thực tùy pipeline | Đọc summary đã cập nhật |
| Cache ứng dụng | Theo TTL/invalidation | Có thể rất nhanh nhưng dễ stale |

Không chọn materialized view nếu nghiệp vụ đòi hỏi số liệu tức thì mà không có cơ chế refresh đáp ứng yêu cầu.

### 29.4. REFRESH toàn bộ dữ liệu có thể đắt

PostgreSQL materialized view built-in không tự động là **incremental materialized view** cho mọi DML. Với bảng nguồn rất lớn và refresh liên tục, chi phí recompute có thể đáng kể.

Khi đó cần xem summary table, incremental pipeline hoặc công cụ chuyên biệt, kèm độ phức tạp đảm bảo đúng dữ liệu.

---

## 30. Bảng tổng hợp tăng dần: thiết kế cẩn thận

Một bảng daily summary có thể được duy trì theo mỗi event:

```sql
CREATE TABLE report_opt_lab.daily_region_summary (
    day_utc DATE NOT NULL,
    region TEXT NOT NULL,
    order_count BIGINT NOT NULL DEFAULT 0,
    paid_order_count BIGINT NOT NULL DEFAULT 0,
    paid_order_value NUMERIC(18,2) NOT NULL DEFAULT 0,
    PRIMARY KEY (day_utc, region)
);
```

Ví dụ tăng một đơn PAID **mới được tạo và chỉ được xử lý một lần**:

```sql
INSERT INTO report_opt_lab.daily_region_summary (
    day_utc, region, order_count,
    paid_order_count, paid_order_value
)
VALUES (
    DATE '2026-02-01', 'NORTH', 1, 1, 100.00
)
ON CONFLICT (day_utc, region)
DO UPDATE SET
    order_count =
        report_opt_lab.daily_region_summary.order_count + 1,
    paid_order_count =
        report_opt_lab.daily_region_summary.paid_order_count + 1,
    paid_order_value =
        report_opt_lab.daily_region_summary.paid_order_value
        + EXCLUDED.paid_order_value;
```

**Cảnh báo:** Đây chỉ là ví dụ về delta ứng với **một event tạo đơn mới**. Chạy lại cùng câu lệnh sẽ tăng trùng summary; nó **không idempotent**.

### 30.1. UPDATE, refund và cancellation làm bài toán khó hơn

Nếu order chuyển:

```text
PENDING -> PAID -> REFUNDED
```

hệ thống summary phải xác định:

- Lúc tạo order, order_count tăng như thế nào?
- Lúc PAID, tăng paid_count/paid_value.
- Lúc REFUNDED, có giảm paid_count không theo định nghĩa? Có ghi refund theo ngày event không?
- Nếu chuyển region, phải trừ summary region cũ và cộng region mới?
- Nếu total_amount đổi, phải cộng **delta** chứ không cộng toàn bộ thêm một lần.

Không thể chỉ dùng `ON CONFLICT DO UPDATE SET total = total + NEW.amount` cho mọi UPDATE mà mong đúng.

### 30.2. Idempotency và event ordering

Một pipeline thường cần:

- Mã event bất biến và unique.
- Cơ chế xử lý đúng-once ở mức state effect hoặc deduplication khi retry.
- Theo dõi version/sequence của aggregate.
- Xử lý event đến muộn hoặc sai thứ tự.
- Transaction lưu processed event cùng update summary khi phù hợp.
- Reconciliation định kỳ với bảng nguồn.

**Summary sai rồi được đọc nhanh không phải tối ưu.**

### 30.3. Distinct count tăng dần khó hơn SUM/COUNT

Để duy trì distinct customers theo ngày, chỉ cộng khi customer xuất hiện lần đầu trong nhóm. Nếu một customer có nhiều đơn và một đơn bị hủy, không thể đơn giản trừ 1 khỏi distinct count: cần biết customer còn đơn hợp lệ nào khác hay không.

Có thể cần bảng grain `(day, region, customer_id)` với số đơn tham gia, hoặc thuật toán/summary phù hợp.

---

## 31. EXPLAIN (ANALYZE, BUFFERS): đọc đúng phép đo

Câu đầu tiên nên đo:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    (ordered_at AT TIME ZONE 'UTC')::DATE AS day_utc,
    region,
    COUNT(*) AS orders,
    SUM(total_amount) AS order_value
FROM report_opt_lab.orders
WHERE ordered_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-03-01 00:00:00+00'
GROUP BY day_utc, region;
```

### 31.1. Một số node thường thấy

| Node / thông tin | Ý nghĩa |
| --- | --- |
| `Seq Scan` | Đọc tuần tự bảng |
| `Index Scan` | Dùng index tìm hàng, có thể truy cập heap |
| `Index Only Scan` | Có thể giảm heap visits nếu visibility cho phép |
| `Bitmap Index Scan` | Tạo tập vị trí ứng viên |
| `Bitmap Heap Scan` | Truy cập heap theo bitmap |
| `Hash Join` | Dùng hash để JOIN |
| `Nested Loop` | Lặp truy cập phía trong theo hàng phía ngoài |
| `HashAggregate` | Gom nhóm bằng cấu trúc hash |
| `GroupAggregate` | Gom nhóm theo input có thứ tự |
| `Sort` | Sắp dữ liệu |
| `Gather / Gather Merge` | Hợp nhất dòng từ parallel workers |
| `Partial/Finalize Aggregate` | Tính một phần rồi hoàn tất aggregate |
| `Buffers: shared hit/read` | Hoạt động trong shared buffers |
| `Buffers: temp read/written` | Dữ liệu tạm do spill/operation tương ứng |
| `actual rows, loops` | Số hàng thực tế và số lần thực thi node |
| `Planning/Execution Time` | Thời gian của phép đo |

### 31.2. Estimate sai dẫn đến plan sai

Nếu PostgreSQL ước lượng vài chục hàng nhưng thực tế đọc hàng triệu, planner có thể chọn Nested Loop hoặc aggregation path kém phù hợp.

Cần so:

```text
rows=...     (ước lượng)
actual rows=... (thực tế)
loops=...
```

Sai lệch lớn có thể do thống kê cũ, cột tương quan, phân phối dữ liệu lệch hoặc điều kiện phức tạp.

### 31.3. Đo bốn thứ

Với báo cáo:

1. **Correctness:** kết quả có đúng grain, metric, NULL, JOIN và timezone?
2. **Logical work:** bao nhiêu hàng scan/JOIN/group?
3. **Physical work:** shared buffers, temp files, disk I/O.
4. **Latency/resource:** thời gian, CPU, memory, concurrent workload.

Không lấy riêng Execution Time của một lần chạy trên cache nóng làm bằng chứng mọi môi trường sẽ nhanh.

### 31.4. Đừng nhầm EXPLAIN ANALYZE với mô phỏng không thực thi

Với SELECT, `EXPLAIN ANALYZE` chạy truy vấn và đo thật. Với UPDATE/DELETE/INSERT, nó cũng **thực thi DML thật**. Trong bài này phần đo tập trung vào SELECT; nếu thử DML trên lab phải hiểu transaction và rollback không loại hết WAL/I/O đã phát sinh.

---

## 32. Statistics và extended statistics

PostgreSQL optimizer cần thống kê để ước lượng:

- Số hàng sau WHERE.
- Số nhóm sau GROUP BY.
- Độ chọn lọc của các predicate kết hợp.
- Chi phí JOIN, HashAggregate, Sort.
- Khi nào Index Scan rẻ hơn Seq Scan.

### 32.1. ANALYZE sau thay đổi dữ liệu lớn

```sql
ANALYZE report_opt_lab.orders;
ANALYZE report_opt_lab.order_items;
ANALYZE report_opt_lab.payment_events;
```

`ANALYZE` làm mới thống kê planner; nó **không phải VACUUM dọn dead tuples**.

### 32.2. Phụ thuộc giữa các cột

Nếu `status` và `region` có tương quan mạnh, planner giả định các điều kiện độc lập có thể ước lượng sai.

PostgreSQL có **extended statistics** cho một số dạng tương quan:

```sql
CREATE STATISTICS st_orders_region_status
    (dependencies, ndistinct, mcv)
ON region, status
FROM report_opt_lab.orders;

ANALYZE report_opt_lab.orders;
```

Các loại thống kê thường gặp:

- `dependencies`: phụ thuộc chức năng giữa cột trong phạm vi hỗ trợ.
- `ndistinct`: ước lượng số tổ hợp phân biệt.
- `mcv`: các tổ hợp giá trị xuất hiện nhiều.

Những thống kê này không đảm bảo sửa mọi estimate và không thay index. Cần xác định kế hoạch sai có liên quan tới correlation trước khi tạo.

### 32.3. Mục tiêu thống kê của cột

Ở bảng rất lớn, có thể điều chỉnh statistics target cho những cột quan trọng. Nhưng target cao hơn làm ANALYZE tốn tài nguyên và lưu stats lớn hơn. Không nâng tất cả cột lên giá trị cực cao.

### 32.4. Autovacuum/autoanalyze

Trong workload thay đổi liên tục, autovacuum và autoanalyze giúp bảng được bảo trì và planner có thống kê tương đối mới. Bảng có phân phối thay đổi nhanh vẫn có thể cần giám sát/ANALYZE bổ sung sau những batch quan trọng.

---

## 33. Giám sát query báo cáo trong production

Nếu extension `pg_stat_statements` được bật và cấu hình phù hợp, nó giúp quan sát thống kê thực thi các query đã được chuẩn hóa.

Một ví dụ mang tính định hướng:

```sql
SELECT
    query,
    calls,
    total_exec_time,
    mean_exec_time,
    rows
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

**Lưu ý:** view này chỉ tồn tại khi extension được cấu hình/cài đặt; việc thay đổi shared_preload_libraries có thể cần restart. Không tự kích hoạt extension trên production nếu không có quyền/phê duyệt.

### 33.1. Nên theo dõi metric nào?

- P50/P95/P99 latency của endpoint báo cáo.
- Số lần chạy và tổng thời gian tiêu thụ.
- Rows scanned/returned (qua plan/log monitoring phù hợp).
- Shared/temp I/O.
- Query cancellations/timeouts.
- Số report chạy đồng thời.
- CPU và memory pressure.
- Thời điểm refresh view/summary.
- Data freshness và reconciliation errors.
- Read replica lag nếu dashboard đọc standby.

### 33.2. Query nhanh có thể gây chi phí lớn nếu gọi quá nhiều

Một report mất 80 ms nhưng được gọi 500 lần mỗi giây có thể tiêu thụ nhiều tài nguyên hơn report 5 giây chỉ chạy mỗi giờ. Tối ưu tổng workload cần xem **calls × cost**, không chỉ latency của một lần.

### 33.3. Caching có thể là phương án tốt hơn index mới

Nếu dashboard theo ngày được làm mới mỗi 5 phút, caching/matview có thể giảm load. Nhưng cache phải có TTL/invalidation/permission scope và thông báo data freshness phù hợp. Không dùng cache để che dấu lỗi metric.

---

## 34. Tính nhất quán khi đọc báo cáo đồng thời với DML

Một báo cáo nhiều metric có thể bị không nhất quán nếu ứng dụng chạy nhiều SELECT ở các thời điểm khác nhau:

```text
T1: SELECT COUNT(*)          -> 100 đơn
T2: INSERT một đơn và COMMIT
T3: SELECT SUM(total_amount) -> tổng tiền của 101 đơn
```

Nếu UI ghép hai số từ hai snapshot nhưng hiển thị như cùng thời điểm, người dùng có thể thấy dữ liệu tưởng như mâu thuẫn.

### 34.1. Một SELECT nhiều aggregate

Tính các metric cùng phạm vi trong một SELECT thường có ưu điểm tất cả dùng cùng snapshot của statement theo cơ chế PostgreSQL.

### 34.2. Nhiều SELECT cùng transaction

Nếu cần nhiều truy vấn với cùng snapshot dữ liệu, có thể cân nhắc `REPEATABLE READ` cho **một transaction đọc ngắn** và thiết kế rõ transaction boundary. `READ COMMITTED` có thể cho snapshot mới ở mỗi statement.

Không giữ transaction đọc hàng giờ chỉ để dashboard không thay số: snapshot lâu có thể ảnh hưởng MVCC cleanup.

### 34.3. Báo cáo trên asynchronous replica

Replica có thể chưa replay các giao dịch mới. Report trên standby có thể trễ so với primary; đây là **replication lag**, không phải lỗi SUM.

Nếu cần read-after-write chính xác tức thì, có thể route một số báo cáo sang primary hoặc dùng cơ chế chờ replay phù hợp. Phải thống nhất hợp đồng độ tươi dữ liệu.

### 34.4. RLS và tenant filters

Row-Level Security hoặc điều kiện tenant scope có thể làm số liệu report thay đổi theo caller. Không chạy query tổng trên toàn dữ liệu rồi lọc tenant chỉ ở frontend. Chính sách truy cập phải được thực thi server-side/database trước khi trả kết quả.

---

## 35. Ba tình huống tối ưu điển hình

### Tình huống A — Dashboard doanh thu theo 30 ngày

**Vấn đề:** Mỗi request chạy full scan nhiều năm.

Điều tra:

1. Xác định đúng mốc 30 ngày theo timezone nghiệp vụ.
2. Chuyển filter sang half-open range trên raw timestamp.
3. Xem index `ordered_at` hoặc partial index theo trạng thái cần thiết.
4. Đánh giá materialized view/summary ngày nếu nhiều request cùng đọc.
5. Đo plan và freshness sau thay đổi.

Không tự tạo index theo `DATE(ordered_at)` khi query vẫn cần raw range; thường nên xem range index trước.

### Tình huống B — Doanh thu gấp 6 lần sau khi thêm bảng payments

**Vấn đề:** Query JOIN orders × 3 items × 2 payments.

Điều tra:

1. Đếm `COUNT(*)` theo order_id sau JOIN.
2. Xác định grain từng bảng.
3. Aggregate items và payments về một hàng/order trước JOIN.
4. So sánh tổng tiền trước/sau trên tập nhỏ đã biết.
5. Cấm sửa bằng `SUM(DISTINCT total_amount)` vì làm sai hai đơn có cùng số tiền.

Đây trước hết là **lỗi đúng dữ liệu**, không phải lỗi cần thêm RAM.

### Tình huống C — COUNT(DISTINCT) tốn nhiều bộ nhớ

**Vấn đề:** Báo cáo nhóm theo nhiều dimension có hàng triệu distinct customers, HashAggregate/Sort spill ra disk.

Điều tra:

1. Kiểm tra grain cần thiết và liệu báo cáo có thể giảm chiều nhóm.
2. Lọc thời gian/tenant sớm.
3. Tránh JOIN nhân hàng trước DISTINCT.
4. So sánh pre-dedup theo đúng khóa.
5. Cân nhắc summary grain (day,region,customer) khi được dùng lặp lại.
6. Đánh giá mức memory và concurrent queries.
7. Nếu được phép approximate, nghiên cứu extension/sketch và error budget.

Không đơn giản cộng distinct counts theo ngày để có tháng.

---

## 36. Lỗi và hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Báo cáo nhanh là báo cáo đúng.” | Cần kiểm tra grain, metric, JOIN, NULL, timezone |
| “WHERE và HAVING thay nhau được.” | WHERE lọc hàng, HAVING lọc nhóm |
| “FILTER làm WHERE chung cho query.” | FILTER chỉ áp dụng một aggregate cụ thể |
| “COUNT(CASE WHEN ... THEN 1 ELSE 0 END) đếm điều kiện đúng.” | COUNT đếm mọi giá trị khác NULL, gồm 0 |
| “SUM không có hàng trả 0.” | SUM trả NULL; dùng COALESCE khi metric yêu cầu |
| “COUNT(*) sau LEFT JOIN bằng số hàng bảng phải.” | Hàng unmatched vẫn tạo một dòng; dùng COUNT(right.id) |
| “COUNT(DISTINCT order_id) sửa toàn bộ vấn đề JOIN.” | Chỉ sửa số order, không sửa SUM bị nhân |
| “SUM(DISTINCT amount) sửa fan-out.” | Gộp nhầm những đơn khác nhau có cùng amount |
| “JOIN nhiều bảng 1:N không đổi số hàng.” | Có thể nhân số hàng theo số match |
| “GROUP BY sau JOIN tự loại nhân bản tiền.” | SUM vẫn cộng trên mọi hàng đã join |
| “AVG(avg_per_day) bằng avg toàn tháng.” | Cần trọng số theo count |
| “Cộng unique daily ra unique monthly.” | Distinct sets giữa ngày chồng lấn |
| “BETWEEN 23:59:59 lấy hết ngày.” | Có fractional seconds sau 23:59:59 |
| “ordered_at::DATE luôn dùng index trên ordered_at.” | Biểu thức có thể ngăn dùng B-tree thông thường |
| “Ngày UTC giống ngày Việt Nam.” | Mốc ngày phụ thuộc timezone |
| “GROUP BY week number đủ cho mọi năm.” | Cần ISO year hoặc week_start rõ |
| “Tạo index cho mọi GROUP BY là nhanh.” | Còn số hàng đầu vào, sorting/hash cost |
| “Partial index PAID phục vụ toàn bộ metric gồm CANCELED.” | Index thiếu hàng ngoài predicate |
| “INCLUDE giúp range filter trên cột include.” | INCLUDE là payload, không giống key |
| “Index-only scan không bao giờ truy cập heap.” | Visibility map quyết định heap fetch |
| “BRIN là B-tree nhỏ hơn.” | BRIN tóm tắt page ranges, cần correlation |
| “Partition tự tính summary.” | Partition pruning giảm phạm vi; aggregation vẫn cần làm |
| “HashAggregate luôn ở RAM.” | Có thể spill, chia batch |
| “GroupAggregate luôn nhanh hơn HashAggregate.” | Phụ thuộc input order, số nhóm, sort cost |
| “work_mem là giới hạn RAM cho toàn query.” | Có thể có nhiều nodes và parallel workers |
| “Parallel query luôn nhanh hơn.” | Có overhead và cạnh tranh tài nguyên |
| “CTE luôn materialized” | Tùy phiên bản/điều kiện, có thể inline |
| “MATERIALIZED luôn tối ưu.” | Có thể cản predicate pushdown |
| “Materialized view luôn fresh.” | Chỉ có dữ liệu tới lần REFRESH |
| “REFRESH CONCURRENTLY không cần unique index.” | Có những điều kiện unique index và populated view |
| “Summary incremental chỉ cần cộng NEW.amount.” | UPDATE/refund/retry cần delta, dedupe, ordering |
| “COUNT(DISTINCT) luôn phân rã cộng dồn.” | Không thể cộng distinct groups chồng lấn |
| “EXPLAIN cost là milliseconds.” | Cost là thước đo ước lượng tương đối |
| “Seq Scan luôn xấu.” | Có thể tối ưu với bảng nhỏ hoặc phạm vi rất lớn |
| “Một benchmark đủ kết luận.” | Cache, stats, load, spill, concurrency thay đổi |
| “Report trên replica luôn mới nhất.” | Async replication có thể lag |
| “Cache report không cần quyền tenant.” | Cache key và authorization phải đúng scope |

---

## 37. Bài tập thực hành

### Bài 1 — Xác định grain

Nêu grain của orders, order_items, payment_events, báo cáo region–day và báo cáo order. Vì sao SUM(o.total_amount) sau JOIN cả items và payments dễ sai?

### Bài 2 — Đếm trạng thái bằng FILTER

Viết SELECT theo region có COUNT all, paid, refunded, canceled và pending trong một query. Vì sao WHERE status='PAID' khiến all count sai?

### Bài 3 — CASE so với FILTER

Viết cùng metric paid_count bằng `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` và `COUNT(*) FILTER (...)`. Giải thích lỗi của `COUNT(CASE ... ELSE 0 END)`.

### Bài 4 — NULL và SUM

Tìm một khoảng thời gian không có đơn. COUNT trả gì, SUM trả gì? Khi nào nên COALESCE(SUM,0) và khi nào giữ NULL?

### Bài 5 — WHERE và HAVING

Tìm region có tổng order value PAID trên một ngưỡng, nhưng chỉ xét tháng Hai. Đặt điều kiện tháng ở đâu? Điều kiện SUM ở đâu?

### Bài 6 — COUNT DISTINCT

Đếm unique customers theo region. Nếu một customer mua ba đơn cùng region, COUNT(*), COUNT(customer_id) và COUNT(DISTINCT customer_id) khác thế nào?

### Bài 7 — Distinct ngày và tháng

Một khách mua cả hai ngày trong tháng. Vì sao SUM(daily_unique_customers) không bằng monthly_unique_customers?

### Bài 8 — Lỗi fan-out

JOIN orders, items, payment_events cho một đơn REFUNDED. Đếm joined rows và chứng minh SUM(o.total_amount) bị nhân lên.

### Bài 9 — Sửa fan-out bằng pre-aggregation

Viết item_by_order và payment_by_order, JOIN về orders. So sánh item_total, captured, refunded với số liệu gốc của một order.

### Bài 10 — SUM(DISTINCT) có sửa được không?

Tạo hai order có cùng total_amount nhưng khác order_id. Giải thích vì sao SUM(DISTINCT total_amount) cho kết quả sai nếu dùng để chữa JOIN multiplication.

### Bài 11 — Half-open date range

Viết WHERE cho toàn bộ ngày 2026-02-01 theo UTC và theo Asia/Ho_Chi_Minh, giữ ordered_at không bị bao hàm trong hàm/cast.

### Bài 12 — Timestamp có fractional seconds

Giải thích vì sao BETWEEN tới 23:59:59 bỏ các mốc có microsecond sau giây đó. Viết cách thay thế an toàn.

### Bài 13 — Báo cáo tuần

Viết báo cáo GROUP BY week_start UTC. Vì sao chỉ GROUP BY EXTRACT(WEEK) có thể trộn tuần thuộc các năm khác nhau?

### Bài 14 — Tỷ lệ và mẫu số 0

Tính paid_percent theo region dùng NUMERIC và NULLIF. Nếu không có hàng trong nhóm, phải thể hiện tỷ lệ ra sao?

### Bài 15 — AOV có trọng số

Có một ngày 1 đơn AOV=1000 và một ngày 99 đơn AOV=10. Tính AOV toàn hai ngày chính xác bằng SUM và COUNT.

### Bài 16 — Region có 0 đơn

Dùng CTE VALUES ba region và LEFT JOIN orders cho tháng không có dữ liệu. So sánh COUNT(*) với COUNT(o.order_id).

### Bài 17 — Những ngày không có dữ liệu

Dùng generate_series tạo dãy ngày 10 ngày, LEFT JOIN daily aggregation. Vì sao nên aggregate theo ngày trước JOIN nếu orders rất lớn?

### Bài 18 — GROUPING SETS

Viết report theo (day,region), theo day và grand total. Dùng GROUPING để phân biệt subtotal với NULL thật ở dimension nullable.

### Bài 19 — ROLLUP và CUBE

Cho hai chiều region/status: ROLLUP(region,status) có những cấp nào? CUBE có thêm cấp nào? Với 10 dimensions, CUBE có thể tạo bao nhiêu grouping sets?

### Bài 20 — B-tree và partial index

Đề xuất index cho query PAID trong khoảng thời gian ngắn. Giải thích khi nào partial index giúp và khi nào query có metric PAID+CANCELED không thể chỉ dựa index đó.

### Bài 21 — Covering index

Với index ordered_at INCLUDE(region,total_amount), khi nào planner có thể chọn Index Only Scan? Tại sao vẫn có Heap Fetches?

### Bài 22 — BRIN

Bảng event append-heavy theo event_at: khi nào BRIN đáng thử hơn B-tree? Dữ liệu timestamp ngẫu nhiên ảnh hưởng thế nào?

### Bài 23 — Partition pruning

Với partition theo tháng của event_at, viết WHERE chọn 10 ngày trong tháng Một. Vì sao dùng raw timestamp range giúp pruning dễ hơn một biểu thức không phù hợp?

### Bài 24 — HashAggregate và GroupAggregate

Chạy EXPLAIN cho GROUP BY region, rồi GROUP BY order_id. So sánh ước lượng số nhóm, memory và plan. Vì sao số nhóm ảnh hưởng chi phí?

### Bài 25 — Spill và work_mem

Một plan có Sort Method: external merge Disk và HashAggregate Batches nhiều. Đề xuất thứ tự điều tra trước khi tăng work_mem toàn hệ thống.

### Bài 26 — Parallel aggregate

Giải thích Partial Aggregate, Gather và Finalize Aggregate. Vì sao COUNT DISTINCT không mặc định có cùng đặc tính parallel với COUNT(*)?

### Bài 27 — CTE materialization

So sánh CTE inline và materialize trong báo cáo có filter ngày. Khi nào materialize có thể chặn pushdown? Khi nào nó giúp tránh tính lại dữ liệu đắt?

### Bài 28 — LATERAL

Viết query lấy 20 đơn mới nhất kèm COUNT item bằng LEFT JOIN LATERAL. Vì sao có thể hiệu quả cho 20 đơn nhưng không nhất thiết tốt khi cần mọi đơn?

### Bài 29 — Window trên kết quả aggregate

Tạo daily revenue rồi tính running total bằng window. Vì sao aggregate trước rồi window có thể giảm số hàng cần xử lý?

### Bài 30 — Materialized view

Tạo daily_region_orders materialized view và unique index phù hợp. Nêu điều kiện REFRESH CONCURRENTLY và vì sao dữ liệu có thể stale.

### Bài 31 — Summary incremental

Thiết kế logic xử lý đơn PENDING → PAID → REFUNDED trong summary. Vì sao không được cộng total_amount cho mọi event? Dùng idempotency/delta như thế nào?

### Bài 32 — ANALYZE và extended statistics

Tạo extended stats cho region/status và ANALYZE. Vì sao statistics giúp planner nhưng không thay index?

### Bài 33 — EXPLAIN

Chạy EXPLAIN (ANALYZE, BUFFERS) cho một query report. Ghi chú Seq Scan/Index Scan, HashAggregate/GroupAggregate, actual rows, loops, temp I/O và Execution Time.

### Bài 34 — Nhất quán snapshot

Dashboard gọi COUNT và SUM bằng hai SELECT riêng trong READ COMMITTED; có INSERT ở giữa. Điều gì có thể xảy ra? Đề xuất hai cách để các metric dùng snapshot phù hợp.

### Bài 35 — Bài thiết kế tổng hợp

Một công ty có 300 triệu orders, 900 triệu items, 400 triệu payment events; dashboard yêu cầu revenue theo ngày/region, unique customers theo tháng, refund cash flow, xếp hạng sản phẩm và dữ liệu tươi trong 5 phút. Hãy nêu:

- Grain/định nghĩa từng metric.
- Những JOIN phải pre-aggregate.
- Index/partition cần benchmark.
- Summary/materialized view và lịch refresh.
- Cơ chế xử lý UPDATE/refund/duplicate events.
- Cách đo correctness, lag, CPU, memory, temp I/O và latency.
- Kế hoạch đối soát summary với base tables.

---

## 38. Checklist tối ưu báo cáo PostgreSQL

| Câu hỏi | Cách đánh giá |
| --- | --- |
| Grain mỗi bảng là gì? | PK và mối quan hệ 1:1, 1:N, N:M |
| Grain đầu ra là gì? | Các grouping keys tối thiểu |
| Metric đã định nghĩa rõ? | Paid order value, capture, refund, net |
| Có nguy cơ JOIN fan-out? | COUNT rows per key sau JOIN |
| SUM có đang nhân tiền? | Đối chiếu với order-level value |
| Có dùng DISTINCT để che sai grain? | Không sửa SUM bằng SUM(DISTINCT amount) |
| Có thể bỏ JOIN không cần? | Giảm scan/intermediate rows |
| Có thể pre-aggregate child? | Một hàng/order trước JOIN |
| WHERE là phạm vi chung? | Lọc hàng trước aggregate |
| HAVING chỉ lọc nhóm? | Đừng tráo thành WHERE nếu đổi semantics |
| FILTER riêng từng metric? | Tránh WHERE loại status cần đếm |
| COUNT(*) / COUNT(col) đúng? | NULL và LEFT JOIN |
| SUM có cần COALESCE? | Phân biệt không dữ liệu và 0 |
| AOV có trọng số? | Giữ sum và count |
| Distinct có bị cộng sai? | Không cộng các tập chồng lấn |
| Có timezone nghiệp vụ? | Mốc ngày theo timezone chính xác |
| Date range có half-open? | >= start, < end |
| WHERE có sargable? | So trực tiếp cột index phù hợp |
| Có index hỗ trợ filter? | B-tree, partial, covering |
| Index có tăng chi phí ghi không? | HOT/WAL/disk tradeoffs |
| Có BRIN phù hợp? | Correlation theo physical page |
| Có partition pruning? | Filter theo partition key |
| HashAggregate hay GroupAggregate? | EXPLAIN plan và số nhóm |
| Có spill ra disk? | Temp I/O, batches, sort method |
| work_mem có tác động concurrency? | Nhiều nodes/workers/queries |
| Có dùng parallel workers? | Đo throughput lẫn latency |
| Statistics mới? | ANALYZE, extended stats khi cần |
| CTE có đang cản pushdown? | Materialized vs inline |
| LATERAL có lặp quá nhiều lần? | Rows outer và index inner |
| Window dùng grain đã aggregate? | Giảm số hàng sort/window |
| Có ngày/region thiếu? | Generate_series + LEFT JOIN dimension |
| GROUPING SETS phù hợp? | Nhiều cấp summary, cân nhắc cardinality |
| Có report gọi nhiều lần? | Materialized view/cache/summary |
| Có freshness contract? | REFRESH/lag/đối soát |
| Incremental summary có idempotent? | Event key, delta, ordering |
| Có read replica lag? | RPO/consistency và route đọc |
| Có RLS/tenant scope? | Bảo vệ dữ liệu đúng quyền |
| Có benchmark trước/sau? | Correctness, buffers, temp, latency |
| Có đo khi concurrency thật? | CPU/I/O/P95 và throughput |
| Có truy vấn trọng điểm nào quá tốn tổng thời gian? | Calls × mean_exec_time, pg_stat_statements |

## Kết luận

**Tối ưu tổng hợp, lọc có điều kiện và truy vấn báo cáo** trong PostgreSQL không chỉ là tạo thêm index hay thay `SUM(CASE...)` bằng `FILTER`. Cốt lõi là thiết kế **đúng grain và phạm vi dữ liệu**, rồi giảm số hàng phải đọc/JOIN/group theo cách PostgreSQL có thể thực thi hiệu quả.

Những nguyên tắc quan trọng:

1. **Định nghĩa metric trước khi tối ưu.** Order value, tiền đã thu và tiền hoàn là ba chỉ số có nguồn và thời điểm khác nhau.
2. **Phân biệt WHERE, HAVING và FILTER.** WHERE giới hạn input chung, HAVING lọc kết quả nhóm, FILTER dùng điều kiện riêng cho mỗi aggregate.
3. **Tránh JOIN fan-out.** Khi JOIN nhiều bảng một-nhiều, tổng hợp từng bảng con về grain phù hợp trước khi JOIN; không dùng SUM(DISTINCT amount) để chữa số tiền bị nhân.
4. **Chú ý COUNT DISTINCT và trung bình có trọng số.** Chúng không tự cộng dồn giữa các nhóm chồng lấn.
5. **Lọc thời gian bằng half-open range, đúng timezone** và so sánh trực tiếp cột indexed khi có thể.
6. **Chọn index theo workload.** B-tree, partial, covering, BRIN và partition pruning có mục đích khác nhau, đều cần đo.
7. **Đọc EXPLAIN thực tế.** HashAggregate, GroupAggregate, Sort, parallel plan, temp I/O và estimate sai cho biết bottleneck ở đâu.
8. **Đừng mặc định thêm RAM là tối ưu.** Giảm row explosion, lọc và group sớm thường quan trọng hơn việc tăng work_mem.
9. **Materialized view/summary phù hợp báo cáo lặp lại**, nhưng cần hợp đồng độ tươi dữ liệu, refresh, idempotency và reconciliation.
10. **Kiểm tra tính nhất quán snapshot, quyền truy cập và replication lag** trước khi công bố dashboard.

Một báo cáo được tối ưu tốt là báo cáo vừa **đúng nghĩa nghiệp vụ, đúng số liệu, đúng phạm vi thời gian và quyền truy cập**, vừa có chi phí CPU, RAM, I/O và độ trễ được hiểu rõ. Khi đó PostgreSQL có thể phục vụ cả truy vấn vận hành lẫn dashboard phân tích mà không cần đánh đổi tính đúng chỉ để lấy tốc độ.

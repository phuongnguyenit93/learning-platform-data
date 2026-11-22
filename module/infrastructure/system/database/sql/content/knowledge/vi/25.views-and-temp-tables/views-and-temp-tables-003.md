# View lồng nhau và khả năng truy vết logic

Một báo cáo SQL có thể trông rất ngắn:

```sql
SELECT region, month_start, net_revenue, mom_pct
FROM lab_v_region_monthly_trend
ORDER BY region, month_start;
```

Nhưng `lab_v_region_monthly_trend` có thể không đọc trực tiếp bảng đơn hàng. Nó dùng một view tổng hợp, view tổng hợp lại dùng một view đã trừ hoàn tiền, còn view đó dùng một view lọc đơn hợp lệ. Khi một chỉ số trên dashboard sai, câu hỏi quan trọng không chỉ là **“view cuối cùng viết SQL gì?”** mà còn là:

> **“Giá trị này đi qua những lớp biến đổi nào, được tính từ những dòng gốc nào, và điều kiện nào có thể khiến nó xuất hiện, biến mất hoặc bị nhân đôi?”**

Bài học **“View lồng nhau và khả năng truy vết logic”**, thuộc chương **View và bảng trung gian** của module **Database SQL**, giải thích cách tổ chức các view phụ thuộc nhau mà vẫn có khả năng lần theo logic, kiểm chứng nguồn gốc chỉ số, đánh giá tác động thay đổi schema và tránh che giấu lỗi nghiệp vụ sau nhiều lớp truy vấn.

Ta dùng **PostgreSQL** để xây dựng ví dụ chạy được, từ các bảng tạm tới bốn lớp view. Sau đó thực hành cả hai hướng truy vết:

- **Backward lineage**: từ ô kết quả báo cáo → view cuối → view trung gian → bảng và dòng nguồn.
- **Forward impact**: từ một bảng/cột/điều kiện thay đổi → những view và báo cáo có thể bị ảnh hưởng.

Ngoài ra, bài phân biệt view thông thường với materialized view, CTE và bảng trung gian; giới thiệu cách đọc `pg_get_viewdef`, `pg_rewrite`/`pg_depend`, sơ đồ phụ thuộc, kế hoạch thực thi, quyền truy cập và các tình huống sửa view ở hệ thống lớn.

## 1. View là gì? “Lồng nhau” nghĩa là gì?

**View** là một đối tượng database có tên, biểu diễn một truy vấn. Với **view thông thường** trong PostgreSQL, database lưu **định nghĩa truy vấn**, chứ không lưu sẵn từng dòng kết quả riêng của view như một bảng thông thường.

Ví dụ:

```sql
CREATE VIEW active_customers AS
SELECT customer_id, customer_name
FROM customers
WHERE is_active = TRUE;
```

Sau đó:

```sql
SELECT customer_id, customer_name
FROM active_customers;
```

trông giống truy vấn bảng, nhưng `active_customers` được xác định bởi `SELECT` phía sau định nghĩa view.

**View lồng nhau** (*nested views*, *view-on-view*) là một view tham chiếu đến một hoặc nhiều view khác:

```sql
CREATE VIEW customer_names AS
SELECT customer_id, customer_name
FROM active_customers;
```

Ở đây `customer_names` phụ thuộc `active_customers`, còn `active_customers` phụ thuộc `customers`.

```text
customer_names (VIEW)
       │
       ▼
active_customers (VIEW)
       │
       ▼
customers (TABLE)
```

### 1.1. Vì sao người ta xây nhiều tầng view?

Vì mỗi tầng có thể giải quyết **một trách nhiệm logic**:

| Tầng | Trách nhiệm ví dụ | Câu hỏi cần trả lời |
|---|---|---|
| Bảng nguồn | Lưu sự kiện, khách hàng, giao dịch | Dòng dữ liệu thực tế ở đâu? |
| View lọc | Chọn các dòng đủ điều kiện | Vì sao dòng này được giữ hoặc bị loại? |
| View chuẩn hóa | Chuyển đơn vị, gộp hoàn tiền, xử lý `NULL` | Cột đầu ra được tính thế nào? |
| View tổng hợp | Nhóm theo vùng/tháng, tính chỉ số | Một dòng đại diện cho nhóm nào? |
| View trình bày | So sánh kỳ, đổi tên cột, dựng KPI | Báo cáo cuối hiển thị điều gì? |

Khi các tầng rõ trách nhiệm, mã SQL có thể dễ bảo trì hơn một truy vấn khổng lồ. Nhưng khi tầng quá nhiều, tên gọi mơ hồ hoặc điều kiện ẩn rải rác, việc truy vết ngược có thể trở nên khó khăn.

### 1.2. View thông thường không đương nhiên là bảng được lưu vật lý

Trong PostgreSQL, câu:

```sql
SELECT * FROM view_a;
```

không hàm ý database đọc một “bản sao đã tính sẵn” của `view_a`. Bộ thực thi thường mở rộng/viết lại định nghĩa và tối ưu kế hoạch truy vấn. SQL có thể được đẩy điều kiện lọc xuống nguồn khi hợp lệ, hoặc áp các bước xử lý trung gian theo kế hoạch; không nên suy luận mỗi view là một lượt quét độc lập.

**Materialized view** là khái niệm khác: nó lưu một kết quả đã tính và phải được làm mới theo cơ chế riêng. Ta sẽ so sánh ở mục sau.

## 2. Hai loại truy vết: logic nguồn gốc và phụ thuộc đối tượng

Từ “truy vết” có ít nhất hai cấp độ:

**Truy vết đối tượng (*object dependency lineage*)**

```text
view_report
   → view_monthly
       → view_order_net
           → view_paid_orders
               → orders
               → customers
           → refunds
```

Loại này trả lời: **view A phụ thuộc bảng/view nào?** Nó quan trọng khi đổi schema, tìm nơi chịu ảnh hưởng và lập kế hoạch migration.

**Truy vết mức dòng/cột (*data/column lineage*)**

```text
report.net_revenue = 420
    = SUM(order_net.net_amount)
    = (300 - 80) + (200 - 0)
    = 2 đơn hàng + 2 khoản hoàn tiền của một đơn
```

Loại này trả lời: **giá trị cụ thể đến từ những dòng và phép biến đổi nào?** Nó quan trọng khi giải thích báo cáo, đối soát kế toán, điều tra số liệu sai.

### 2.1. Bảng phân biệt

| Câu hỏi | Truy vết đối tượng | Truy vết dữ liệu |
|---|---|---|
| View nào đọc bảng `orders`? | Có | Không phải trọng tâm |
| Nếu đổi cột `amount`, báo cáo nào ảnh hưởng? | Có | Bổ trợ |
| Vì sao July South bằng 420? | Chỉ tìm được đường phụ thuộc | Cần các dòng, bộ lọc và công thức |
| Một dòng bị loại ở đâu? | Không đủ | Cần xem `WHERE`, `JOIN`, `HAVING` ở từng tầng |
| Có bị nhân dòng sau `JOIN`? | Không đủ | Cần so độ hạt và số dòng |
| Có thể tự động dựng đồ thị? | Thường có thể từ catalog | Chỉ một phần; cần hiểu SQL và nghiệp vụ |

**Catalog dependency** không tự cung cấp đầy đủ câu trả lời về cách một giá trị được tính. Nó biết “có phụ thuộc” nhưng không luôn biết ý nghĩa nghiệp vụ của `SUM`, `CASE`, thời điểm, hàm tùy biến hay dữ liệu ngoài.

## 3. Đọc sơ đồ nhiều tầng trước khi viết SQL

Trong bài thực hành, báo cáo doanh thu thuần được tổ chức:

```text
                       ┌──────────────────────┐
                       │ lab_customers (TABLE)│
                       └──────────┬───────────┘
                                  │
┌────────────────────────┐        │
│ lab_orders (TABLE)     ├────────┤
└────────────────────────┘        ▼
                     ┌────────────────────────────┐
                     │ lab_v_paid_orders (VIEW)   │
                     │ chỉ đơn PAID + vùng + tháng│
                     └──────────────┬─────────────┘
                                    │
┌────────────────────────┐          │
│ lab_refunds (TABLE)    ├──────────┤
└────────────────────────┘          ▼
                     ┌────────────────────────────┐
                     │ lab_v_order_net (VIEW)     │
                     │ tổng refund mỗi đơn, net   │
                     └──────────────┬─────────────┘
                                    │
                                    ▼
                     ┌────────────────────────────┐
                     │ lab_v_region_monthly       │
                     │ (VIEW): SUM theo vùng/tháng│
                     └──────────────┬─────────────┘
                                    │
                                    ▼
                     ┌────────────────────────────┐
                     │ lab_v_region_monthly_trend │
                     │ (VIEW): so kỳ liền trước   │
                     └──────────────┬─────────────┘
                                    │
                                    ▼
                         Dashboard / API / SELECT
```

Đọc sơ đồ từ **trên xuống** là đường đi của dữ liệu. Đọc từ **dưới lên** là quá trình điều tra “chỉ số dashboard đến từ đâu?”.

### 3.1. Khái niệm “độ hạt” (*grain*)

Trước mỗi tầng, phải biết **một dòng là gì**:

| Đối tượng | Một dòng đại diện cho |
|---|---|
| `lab_orders` | Một đơn hàng |
| `lab_refunds` | Một sự kiện hoàn tiền |
| `lab_v_paid_orders` | Một đơn hàng đủ điều kiện `PAID` |
| `lab_v_order_net` | Một đơn `PAID`, kèm **tổng** hoàn tiền của đơn |
| `lab_v_region_monthly` | Một cặp `(region, month_start)` |
| `lab_v_region_monthly_trend` | Một cặp `(region, month_start)`, thêm số kỳ trước |

Nếu hiểu sai độ hạt, một `JOIN` có thể nhân dòng rồi khiến `SUM` báo cáo sai. Đây là một nguyên nhân phổ biến khiến view lồng nhau khó truy vết.

## 4. Chuẩn bị dữ liệu mẫu PostgreSQL

Hãy mở một phiên thử nghiệm PostgreSQL mới. Toàn bộ bảng và view chính của bài được tạo bằng `TEMP`, không đụng các bảng nghiệp vụ thật.

### 4.1. Bảng khách hàng, đơn hàng và sự kiện hoàn tiền

```sql
CREATE TEMP TABLE lab_customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL,
    region TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TEMP TABLE lab_orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES lab_customers(customer_id),
    ordered_at TIMESTAMPTZ NOT NULL,
    order_status TEXT NOT NULL
        CHECK (order_status IN ('PAID', 'PENDING', 'REFUNDED')),
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0)
);

CREATE TEMP TABLE lab_refunds (
    refund_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL
        REFERENCES lab_orders(order_id),
    refund_amount NUMERIC(12, 2) NOT NULL
        CHECK (refund_amount > 0)
);
```

Trong mô hình này, **bảng khách hàng không phải bảng doanh thu**; nó chỉ cung cấp thuộc tính vùng. Sự kiện hoàn tiền nằm ở bảng riêng và có thể có **nhiều sự kiện cho cùng một đơn**.

### 4.2. Chèn dữ liệu

```sql
INSERT INTO lab_customers
    (customer_id, customer_name, region, is_active)
VALUES
    (1, 'An',   'North', TRUE),
    (2, 'Bình', 'North', TRUE),
    (3, 'Chi',  'South', TRUE),
    (4, 'Dũng', 'South', TRUE),
    (5, 'Hà',   'North', FALSE);

INSERT INTO lab_orders
    (order_id, customer_id, ordered_at, order_status, amount)
VALUES
    (101, 1, TIMESTAMPTZ '2026-07-03 09:00:00+07', 'PAID',      500),
    (102, 1, TIMESTAMPTZ '2026-07-05 09:00:00+07', 'PENDING',   200),
    (103, 2, TIMESTAMPTZ '2026-07-06 09:00:00+07', 'PAID',      700),
    (104, 3, TIMESTAMPTZ '2026-07-10 09:00:00+07', 'PAID',      300),
    (105, 4, TIMESTAMPTZ '2026-08-01 09:00:00+07', 'PAID',      600),
    (106, 2, TIMESTAMPTZ '2026-08-02 09:00:00+07', 'REFUNDED',  100),
    (107, 3, TIMESTAMPTZ '2026-07-18 09:00:00+07', 'PAID',      200),
    (108, 1, TIMESTAMPTZ '2026-08-05 09:00:00+07', 'PAID',      400),
    (109, 2, TIMESTAMPTZ '2026-08-12 09:00:00+07', 'PAID',      300),
    (110, 4, TIMESTAMPTZ '2026-10-01 09:00:00+07', 'PAID',      900);

INSERT INTO lab_refunds
    (refund_id, order_id, refund_amount)
VALUES
    (1, 103, 100),
    (2, 104,  50),
    (3, 104,  30),
    (4, 108,  25),
    (5, 110, 100),
    (6, 106,  20);
```

Các đơn `PAID`: `101, 103, 104, 105, 107, 108, 109, 110` (**8 đơn**). Đơn `102` đang `PENDING`; đơn `106` mang trạng thái `REFUNDED`, nên **không tham gia chỉ số mẫu khi view đầu tiên chỉ chọn `PAID`**.

> **Quy tắc nghiệp vụ của bài:** “Giá trị thuần của các đơn hiện có trạng thái `PAID`, tính theo tháng đặt hàng tại `Asia/Ho_Chi_Minh`, bằng giá trị đơn trừ tổng các sự kiện hoàn tiền được lưu.” Đây là chỉ số **minh họa**; không đồng nghĩa tự động với doanh thu kế toán hay giá trị thuần thực tế của mọi hệ thống. Nếu `REFUNDED` là trạng thái của một đơn đã thanh toán và cần tính doanh thu trừ hoàn tiền, cách lọc trạng thái thực sẽ phải được xác định lại.

### 4.3. Xem dữ liệu gốc

```sql
SELECT order_id, customer_id, order_status, amount
FROM lab_orders
ORDER BY order_id;

SELECT order_id, COUNT(*) AS refund_events,
       SUM(refund_amount) AS total_refunded
FROM lab_refunds
GROUP BY order_id
ORDER BY order_id;
```

Với đơn `104`, bảng hoàn tiền có **2 dòng**: `50` và `30`; tổng hoàn là `80`. Nếu nối đơn `104` với hoàn tiền mà không tổng hợp trước, thông tin **giá trị đơn 300** sẽ xuất hiện **hai lần** trong kết quả join. Ta sẽ chủ động xử lý vấn đề này ở tầng view thứ hai.

## 5. Tầng 1: view lọc đơn hợp lệ và gắn khóa kỳ

Mỗi dòng của tầng 1 vẫn đại diện cho **một đơn hàng**, nhưng được bổ sung vùng và tháng.

```sql
CREATE TEMP VIEW lab_v_paid_orders AS
SELECT
    o.order_id,
    o.customer_id,
    c.customer_name,
    c.region,
    DATE_TRUNC(
        'month',
        o.ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )::date AS month_start,
    o.ordered_at,
    o.amount AS gross_amount
FROM lab_orders AS o
JOIN lab_customers AS c
    ON c.customer_id = o.customer_id
WHERE o.order_status = 'PAID';
```

Thử đọc:

```sql
SELECT order_id, region, month_start, gross_amount
FROM lab_v_paid_orders
ORDER BY order_id;
```

Kết quả dự kiến:

| order_id | region | month_start | gross_amount |
|---:|---|---|---:|
| 101 | North | 2026-07-01 | 500 |
| 103 | North | 2026-07-01 | 700 |
| 104 | South | 2026-07-01 | 300 |
| 105 | South | 2026-08-01 | 600 |
| 107 | South | 2026-07-01 | 200 |
| 108 | North | 2026-08-01 | 400 |
| 109 | North | 2026-08-01 | 300 |
| 110 | South | 2026-10-01 | 900 |

### 5.1. Những quyết định đã bị “ẩn” vào tầng 1

View này có ba quyết định logic:

1. `WHERE o.order_status = 'PAID'`: chỉ lấy đơn `PAID`; đơn `PENDING`, `REFUNDED` bị loại.
2. `JOIN lab_customers`: lấy `region` từ bảng khách hàng theo khóa `customer_id`.
3. `DATE_TRUNC` sau `AT TIME ZONE`: gom thời điểm vào **tháng theo giờ Việt Nam**, không mặc nhiên theo múi giờ phiên database.

Khi báo cáo thiếu một đơn, **tầng 1** là nơi đầu tiên kiểm tra: đơn có `PAID` không, khách hàng có khớp khóa ngoại không, và nó được gán vào tháng/vùng nào?

### 5.2. Độ hạt và số dòng

Vì `lab_orders.order_id` là khóa chính, `lab_customers.customer_id` là khóa chính, `JOIN` một khách hàng cho mỗi đơn được phép tồn tại và view không dùng `GROUP BY`, tầng 1 giữ **một dòng trên mỗi đơn `PAID`**.

```sql
SELECT
    COUNT(*) AS row_count,
    COUNT(DISTINCT order_id) AS distinct_orders
FROM lab_v_paid_orders;
-- 8 và 8.
```

Nếu trong hệ thống thật một `JOIN` sang bảng thuộc tính có **nhiều dòng một khách**, số dòng có thể tăng. Tên view “paid orders” không tự bảo đảm một dòng mỗi đơn; phải hiểu khóa và quan hệ.

### 5.3. Vì sao không lọc `c.is_active = TRUE`?

Một khách hàng hiện không hoạt động vẫn có thể có đơn lịch sử hợp lệ. Thêm `c.is_active = TRUE` vào view doanh thu có thể **làm biến mất doanh thu lịch sử** chỉ vì tài khoản đã bị vô hiệu sau này.

Nếu nghiệp vụ thực sự yêu cầu “doanh thu của khách đang hoạt động”, cần ghi rõ điều đó trong định nghĩa chỉ số và phân biệt **trạng thái hiện tại** với **trạng thái tại thời điểm đặt hàng**.

## 6. Tầng 2: view chuẩn hóa giá trị thuần từng đơn

Tầng 2 sử dụng tầng 1 và bảng sự kiện hoàn tiền. Một đơn có thể có nhiều sự kiện hoàn, vì vậy ta phải **tổng hợp hoàn tiền về một dòng mỗi `order_id`** trước khi nối.

```sql
CREATE TEMP VIEW lab_v_order_net AS
WITH refund_totals AS (
    SELECT
        order_id,
        SUM(refund_amount) AS refunded_amount
    FROM lab_refunds
    GROUP BY order_id
)
SELECT
    p.order_id,
    p.customer_id,
    p.customer_name,
    p.region,
    p.month_start,
    p.ordered_at,
    p.gross_amount,
    COALESCE(r.refunded_amount, 0::numeric) AS refunded_amount,
    p.gross_amount
        - COALESCE(r.refunded_amount, 0::numeric) AS net_amount
FROM lab_v_paid_orders AS p
LEFT JOIN refund_totals AS r
    ON r.order_id = p.order_id;
```

### 6.1. Trách nhiệm của tầng 2

- **Không** quyết định đơn nào là `PAID`: tầng 1 đã đảm nhiệm.
- **Có** quyết định cách tính số hoàn: `SUM` mọi sự kiện hoàn theo `order_id`.
- **Có** quyết định khi không có sự kiện hoàn: dùng **0** qua `COALESCE`.
- **Có** quyết định giá trị thuần: `net_amount = gross_amount - refunded_amount`.
- **Giữ** độ hạt một dòng trên mỗi đơn `PAID`, miễn là `refund_totals` có đúng một dòng mỗi `order_id`.

### 6.2. Kết quả cụ thể

```sql
SELECT
    order_id, region, month_start,
    gross_amount, refunded_amount, net_amount
FROM lab_v_order_net
ORDER BY order_id;
```

| order_id | region | month | gross | refunded | net |
|---:|---|---|---:|---:|---:|
| 101 | North | 2026-07 | 500 | 0 | 500 |
| 103 | North | 2026-07 | 700 | 100 | 600 |
| 104 | South | 2026-07 | 300 | 80 | 220 |
| 105 | South | 2026-08 | 600 | 0 | 600 |
| 107 | South | 2026-07 | 200 | 0 | 200 |
| 108 | North | 2026-08 | 400 | 25 | 375 |
| 109 | North | 2026-08 | 300 | 0 | 300 |
| 110 | South | 2026-10 | 900 | 100 | 800 |

### 6.3. Lần ngược giá trị `net_amount = 220` của đơn 104

```text
lab_v_order_net.net_amount của order 104
      = gross_amount - refunded_amount
      = 300 - (50 + 30)
      = 220

gross_amount 300 → lab_orders(order_id=104)
refund 50       → lab_refunds(refund_id=2, order_id=104)
refund 30       → lab_refunds(refund_id=3, order_id=104)
region South    → lab_customers(customer_id=3)
month July      → lab_orders.ordered_at + Asia/Ho_Chi_Minh
```

Đây là **truy vết mức giá trị**, không chỉ sơ đồ bảng-view.

## 7. Bẫy nhân dòng khi nối bảng một–nhiều

Đây là lỗi cực kỳ phổ biến trong view nhiều tầng. Nếu bỏ qua CTE `refund_totals` và nối trực tiếp:

```sql
-- Minh họa logic sai khi muốn SUM(gross_amount) sau join.
SELECT
    p.order_id,
    p.gross_amount,
    r.refund_amount
FROM lab_v_paid_orders AS p
LEFT JOIN lab_refunds AS r
    ON r.order_id = p.order_id
WHERE p.order_id = 104
ORDER BY r.refund_id;
```

Kết quả:

| order_id | gross_amount | refund_amount |
|---:|---:|---:|
| 104 | 300 | 50 |
| 104 | 300 | 30 |

Nếu viết tiếp:

```sql
SELECT
    p.order_id,
    SUM(p.gross_amount) AS wrong_gross,
    SUM(r.refund_amount) AS refund_total
FROM lab_v_paid_orders AS p
LEFT JOIN lab_refunds AS r
    ON r.order_id = p.order_id
WHERE p.order_id = 104
GROUP BY p.order_id;
-- wrong_gross = 600; refund_total = 80.
```

Tổng hoàn `80` đúng, nhưng `gross=600` sai vì **300 bị lặp hai lần**. Một dashboard tiếp tục lấy `SUM(wrong_gross - refund_total)` có thể báo sai mà không có lỗi SQL.

### 7.1. Phân biệt nguồn lỗi

| Dấu hiệu | Nguyên nhân có thể |
|---|---|
| Tổng giá trị đơn tăng bất thường | Join một đơn với nhiều chi tiết/refund |
| `COUNT(*)` lớn hơn `COUNT(DISTINCT order_id)` | Độ hạt đã chuyển từ “một đơn” sang “một đơn × sự kiện” |
| `SUM(DISTINCT amount)` có vẻ sửa được một số ca | **Không phải** giải pháp tổng quát; hai đơn khác nhau có cùng số tiền sẽ bị gộp |
| Lỗi chỉ xuất hiện ở vài đơn | Chỉ các đơn có nhiều dòng con bị nhân |
| View cuối có kết quả sai nhưng view đầu đúng | Kiểm tra lần lượt nơi bắt đầu join và aggregate |

**Cách sửa bền vững:** xác định **độ hạt mục tiêu**, tổng hợp bảng nhiều phía về đúng khóa trước khi join, kiểm tra tính duy nhất của khóa trung gian.

## 8. Tầng 3: view tổng hợp theo vùng và tháng

Tầng 3 nâng độ hạt từ **một đơn** lên **một cặp vùng–tháng**:

```sql
CREATE TEMP VIEW lab_v_region_monthly AS
SELECT
    region,
    month_start,
    COUNT(*) AS paid_orders,
    SUM(gross_amount) AS gross_revenue,
    SUM(refunded_amount) AS refunded_amount,
    SUM(net_amount) AS net_revenue
FROM lab_v_order_net
GROUP BY region, month_start;
```

Xem kết quả:

```sql
SELECT
    region, month_start, paid_orders,
    gross_revenue, refunded_amount, net_revenue
FROM lab_v_region_monthly
ORDER BY region, month_start;
```

Kết quả dự kiến:

| region | month_start | paid_orders | gross_revenue | refunded_amount | net_revenue |
|---|---|---:|---:|---:|---:|
| North | 2026-07-01 | 2 | 1200 | 100 | 1100 |
| North | 2026-08-01 | 2 | 700 | 25 | 675 |
| South | 2026-07-01 | 2 | 500 | 80 | 420 |
| South | 2026-08-01 | 1 | 600 | 0 | 600 |
| South | 2026-10-01 | 1 | 900 | 100 | 800 |

### 8.1. Ý nghĩa từng cột

`paid_orders` là **số dòng đơn PAID** trong nhóm, không phải số khách duy nhất.

`gross_revenue` là `SUM(gross_amount)` của các đơn được giữ từ tầng 1.

`refunded_amount` là `SUM` những **tổng hoàn tiền theo từng đơn** ở tầng 2, không phải `SUM` sự kiện hoàn trên một phép join chưa chuẩn hóa.

`net_revenue` bằng:

```text
SUM(net_amount)
= SUM(gross_amount - refunded_amount)
= gross_revenue - refunded_amount
```

Trong ví dụ các cột đều là `NUMERIC` không `NULL` ở mỗi dòng đơn. Với hệ thực có giá trị thiếu, cần định nghĩa `NULL` có nghĩa gì; không tự giả định công thức cộng/trừ vẫn giống.

### 8.2. Truy vết `South / July / net_revenue = 420`

```text
lab_v_region_monthly
  region = South
  month_start = 2026-07-01
  net_revenue = 420
             │
             ▼
SUM(net_amount) của 2 dòng lab_v_order_net
  order 104: gross 300 - refund (50+30) = 220
  order 107: gross 200 - refund 0       = 200
             │
             ▼
                          220 + 200 = 420
```

Để xác nhận từng dòng:

```sql
SELECT
    order_id, customer_id, region, month_start,
    gross_amount, refunded_amount, net_amount
FROM lab_v_order_net
WHERE region = 'South'
  AND month_start = DATE '2026-07-01'
ORDER BY order_id;
```

### 8.3. Một cặp vùng–tháng không có đơn thì sao?

`GROUP BY` trên các dòng thực tế **không tự tạo nhóm rỗng**. Chẳng hạn North tháng 10 không có đơn PAID nên không có dòng `('North','2026-10-01')` trong view này.

Nếu báo cáo phải hiển thị **0** cho mọi tháng hợp lệ, cần một **bảng lịch kỳ (*calendar spine*)** kết hợp danh mục vùng và trạng thái chất lượng dữ liệu. Không nên cố giải quyết bằng `LAG()` trên chuỗi thiếu tháng.

## 9. Tầng 4: view so sánh tháng với kỳ trước

Tầng cuối sẽ lấy doanh thu tháng trước **nếu đó là tháng lịch liền trước**. Cần cẩn thận: `LAG()` lấy **dòng đứng trước**, không tự bảo đảm đó là **tháng trước** nếu chuỗi thiếu tháng.

```sql
CREATE TEMP VIEW lab_v_region_monthly_trend AS
WITH ordered_months AS (
    SELECT
        m.region,
        m.month_start,
        m.paid_orders,
        m.gross_revenue,
        m.refunded_amount,
        m.net_revenue,
        LAG(m.month_start) OVER (
            PARTITION BY m.region
            ORDER BY m.month_start
        ) AS previous_observed_month,
        LAG(m.net_revenue) OVER (
            PARTITION BY m.region
            ORDER BY m.month_start
        ) AS previous_observed_net
    FROM lab_v_region_monthly AS m
)
SELECT
    region,
    month_start,
    paid_orders,
    gross_revenue,
    refunded_amount,
    net_revenue,
    previous_observed_month,
    CASE
        WHEN previous_observed_month =
             (month_start - INTERVAL '1 month')::date
        THEN previous_observed_net
        ELSE NULL::numeric
    END AS previous_calendar_net,
    CASE
        WHEN previous_observed_month =
             (month_start - INTERVAL '1 month')::date
        THEN net_revenue - previous_observed_net
        ELSE NULL::numeric
    END AS mom_change,
    CASE
        WHEN previous_observed_month =
             (month_start - INTERVAL '1 month')::date
         AND previous_observed_net <> 0
        THEN ROUND(
            100.0 * (net_revenue - previous_observed_net)
            / previous_observed_net,
            2
        )
        ELSE NULL::numeric
    END AS mom_pct
FROM ordered_months;
```

Xem báo cáo:

```sql
SELECT
    region, month_start, net_revenue,
    previous_observed_month, previous_calendar_net,
    mom_change, mom_pct
FROM lab_v_region_monthly_trend
ORDER BY region, month_start;
```

Kết quả dự kiến:

| region | month | net | previous observed | previous calendar net | MoM change | MoM % |
|---|---|---:|---|---:|---:|---:|
| North | 2026-07 | 1100 | `NULL` | `NULL` | `NULL` | `NULL` |
| North | 2026-08 | 675 | 2026-07 | 1100 | -425 | -38.64 |
| South | 2026-07 | 420 | `NULL` | `NULL` | `NULL` | `NULL` |
| South | 2026-08 | 600 | 2026-07 | 420 | +180 | +42.86 |
| South | 2026-10 | 800 | 2026-08 | `NULL` | `NULL` | `NULL` |

### 9.1. Vì sao October South có `previous_calendar_net = NULL`?

South không có dòng tháng 9 trong view tổng hợp. `LAG` nhìn thấy dòng trước đó là **tháng 8**, nhưng tháng trước theo lịch của tháng 10 là **tháng 9**.

```text
South:
2026-07 → net 420
2026-08 → net 600
2026-09 → không có dòng
2026-10 → net 800

LAG tại tháng 10 → tháng 8 (dòng trước)
MoM theo lịch    → tháng 9 (thiếu)
```

View cuối chủ động kiểm tra:

```sql
previous_observed_month =
    (month_start - INTERVAL '1 month')::date
```

Nếu không đúng, `mom_change` và `mom_pct` là `NULL`, tránh **gắn nhãn “so tháng trước” cho phép so tháng 10 với tháng 8**.

### 9.2. `NULL` ở đây không nhất thiết có nghĩa doanh thu tháng 9 bằng 0

Cần phân biệt:

- Tháng 9 đã chốt dữ liệu và **không có đơn PAID** → nếu metric được định nghĩa là tổng giao dịch, có thể điền **0** bằng lịch tháng.
- Tháng 9 **chưa được nạp/không đủ dữ liệu** → phải giữ trạng thái **chưa biết**.
- View tổng hợp hiện tại chỉ có các nhóm phát sinh, chưa có thông tin về tính đầy đủ dữ liệu → không thể tự coi nhóm thiếu là 0.

Muốn tính MoM chính xác qua mọi tháng, thiết kế thêm lịch tháng và trạng thái kỳ, rồi tính `LAG` trên **một dòng đầy đủ cho mỗi cặp vùng–tháng**.

### 9.3. Vì sao không đặt `ORDER BY` ngoài ngay trong view cuối?

Ta để consumer quyết định cách trình bày:

```sql
SELECT *
FROM lab_v_region_monthly_trend
ORDER BY region, month_start;
```

Thứ tự trong `OVER (ORDER BY month_start)` quyết định **hàng xóm để tính `LAG`**, còn thứ tự của kết quả cuối cần `ORDER BY` ở câu `SELECT` của người dùng. Một view không tự bảo đảm mọi người đọc sẽ thấy dòng theo thứ tự mong muốn nếu họ không sắp ở truy vấn ngoài.

## 10. Đọc chuỗi phụ thuộc một cách có hệ thống

Sau khi chạy bốn câu `CREATE TEMP VIEW`, chuỗi đối tượng là:

```text
lab_v_region_monthly_trend
            │
            ▼
lab_v_region_monthly
            │
            ▼
lab_v_order_net ───────────→ lab_refunds
            │
            ▼
lab_v_paid_orders ─────────→ lab_customers
            │
            ▼
        lab_orders
```

Các mũi tên ở đây có nghĩa **“định nghĩa bên trái đọc/tham chiếu đối tượng bên phải”**. Chúng không phải cam kết optimizer sẽ thực thi lần lượt từng tầng bằng các bảng trung gian vật lý.

### 10.1. Một thay đổi ở tầng nào ảnh hưởng cột nào?

| Thay đổi | Cột/kết quả có thể ảnh hưởng |
|---|---|
| Sửa `lab_orders.order_status` từ `PAID` sang `PENDING` | Đơn bị loại từ tầng 1; mọi tổng sau đó có thể đổi |
| Sửa `lab_customers.region` | Đơn có thể chuyển nhóm vùng; tổng ở hai vùng đổi |
| Sửa `lab_orders.amount` | `gross_amount`, `net_amount`, mọi tổng và MoM liên quan đổi |
| Thêm một `lab_refunds` cho đơn PAID | `refunded_amount`, `net_amount`, chỉ số theo vùng/tháng đổi |
| Thay đổi bộ lọc `PAID` trong tầng 1 | Số đơn và tổng từ tầng 2 trở lên có thể đổi |
| Đổi công thức `net_amount` tầng 2 | `net_revenue` tầng 3 và MoM tầng 4 đổi |
| Đổi tiêu chí nhóm tầng 3 | Độ hạt, số dòng và cửa sổ tầng 4 có thể đổi |
| Đổi `PARTITION BY`/`ORDER BY` tầng 4 | MoM có thể ghép sai vùng/kỳ dù tổng tầng 3 vẫn đúng |

**Dependency graph** giúp khoanh vùng đường bị ảnh hưởng, còn **công thức và dữ liệu ở từng tầng** giúp biết chính xác tác động.

## 11. Truy vết ngược một giá trị từ dashboard

Giả sử người dùng hỏi:

> “Vì sao South tháng 7/2026 có doanh thu thuần 420, chứ không phải 500?”

Quy trình chẩn đoán nên đi **từ ngoài vào trong**.

### Bước 1 — Xác nhận giá trị ở view cuối

```sql
SELECT region, month_start, gross_revenue,
       refunded_amount, net_revenue
FROM lab_v_region_monthly_trend
WHERE region = 'South'
  AND month_start = DATE '2026-07-01';
-- gross=500, refund=80, net=420.
```

### Bước 2 — Kiểm tra view tổng hợp trước đó

```sql
SELECT region, month_start, paid_orders,
       gross_revenue, refunded_amount, net_revenue
FROM lab_v_region_monthly
WHERE region = 'South'
  AND month_start = DATE '2026-07-01';
-- paid_orders=2, gross=500, refund=80, net=420.
```

Nếu tầng 3 đã là 420, không cần nghi ngờ `LAG` ở tầng 4 để giải thích giá trị **net của tháng**; `LAG` chỉ tính cột so kỳ.

### Bước 3 — Xem từng đơn sau chuẩn hóa

```sql
SELECT order_id, gross_amount,
       refunded_amount, net_amount
FROM lab_v_order_net
WHERE region = 'South'
  AND month_start = DATE '2026-07-01'
ORDER BY order_id;
-- 104: 300 - 80 = 220
-- 107: 200 -  0 = 200
```

### Bước 4 — Kiểm tra sự kiện hoàn tiền nguồn

```sql
SELECT refund_id, order_id, refund_amount
FROM lab_refunds
WHERE order_id IN (104, 107)
ORDER BY order_id, refund_id;
-- Refund 2: 50 cho order 104
-- Refund 3: 30 cho order 104
```

### Bước 5 — Ghi lại cách tính

```text
South, July 2026
  order 104: 300 - 50 - 30 = 220
  order 107: 200            = 200
  total net                 = 420
```

Đó là một chuỗi truy vết **có khả năng giải thích**: xác định được cả công thức lẫn **dòng nguồn**.

## 12. Truy vết xuôi khi một dòng nguồn thay đổi

Giả sử một người sửa `lab_refunds.refund_amount` của `refund_id=3` từ 30 thành 40. Đường ảnh hưởng về mặt logic:

```text
lab_refunds.refund_id=3
      │ +10 refund
      ▼
lab_v_order_net.order_id=104
      │ net giảm từ 220 xuống 210
      ▼
lab_v_region_monthly(South, July)
      │ net giảm từ 420 xuống 410
      ▼
lab_v_region_monthly_trend
      ├── South July net = 410
      └── South August MoM đổi vì baseline July đổi
```

Để thử mà không lưu dữ liệu:

```sql
BEGIN;

UPDATE lab_refunds
SET refund_amount = 40
WHERE refund_id = 3
RETURNING refund_id, order_id, refund_amount;

SELECT region, month_start, net_revenue, mom_change, mom_pct
FROM lab_v_region_monthly_trend
WHERE region = 'South'
ORDER BY month_start;

ROLLBACK;
```

Trong transaction, một view thông thường đọc dữ liệu nguồn theo ngữ cảnh giao dịch nên có thể phản ánh thay đổi chưa commit của chính transaction. Sau `ROLLBACK`, giá trị trở lại như cũ trong dữ liệu mẫu.

**Hiệu ứng lan truyền:** một thay đổi ở tháng 7 không chỉ đổi **tháng 7**, mà còn có thể đổi **MoM tháng 8**. Điều này là quan hệ phụ thuộc ở **mức giá trị kỳ trước**, không chỉ phụ thuộc view-to-view.

## 13. Đọc định nghĩa của một view từ catalog

Một hệ thống lâu năm có thể có hàng trăm view và nhiều người đã rời dự án. Không nên chỉ dựa vào tên `v_report` để đoán SQL bên trong.

### 13.1. `pg_get_viewdef`

PostgreSQL có thể hiển thị câu truy vấn tạo view:

```sql
SELECT pg_get_viewdef(
    'pg_temp.lab_v_region_monthly_trend'::regclass,
    true
) AS view_sql;
```

`pg_temp` là tên schema đặc biệt để tham chiếu **schema tạm hiện tại** trong PostgreSQL. Vì các view của bài được tạo `TEMP`, dùng `pg_temp` giúp tìm đúng view trong phiên thực hành.

`true` yêu cầu định dạng đầu ra dễ đọc hơn ở mức nhất định; định dạng hiển thị có thể khác SQL nguồn được nhập ban đầu. Đây là **định nghĩa hiện được database lưu**, không nhất thiết giữ nguyên comment hoặc cách căn lề gốc.

### 13.2. Liệt kê view tạm và định nghĩa

```sql
SELECT
    schemaname,
    viewname,
    definition
FROM pg_views
WHERE schemaname = (
    SELECT nspname
    FROM pg_namespace
    WHERE oid = pg_my_temp_schema()
)
ORDER BY viewname;
```

`pg_views` hiển thị thông tin view thông thường. Trong môi trường thật, lọc theo schema ứng dụng, ví dụ `reporting`, thay vì quét danh sách mọi schema.

### 13.3. `information_schema.views`

Cách tiếp cận có tính tiêu chuẩn hơn:

```sql
SELECT
    table_schema,
    table_name,
    view_definition
FROM information_schema.views
WHERE table_schema = (
    SELECT nspname
    FROM pg_namespace
    WHERE oid = pg_my_temp_schema()
)
ORDER BY table_name;
```

`information_schema` hữu ích cho truy vấn metadata phổ biến giữa các DBMS, nhưng **không cung cấp toàn bộ thông tin phụ thuộc hay mọi tùy chọn PostgreSQL riêng**. Nội dung `view_definition` cũng chịu giới hạn hiển thị/quyền theo hệ.

### 13.4. Tìm cột đầu ra

```sql
SELECT
    table_name,
    column_name,
    ordinal_position,
    data_type
FROM information_schema.columns
WHERE table_schema = (
    SELECT nspname
    FROM pg_namespace
    WHERE oid = pg_my_temp_schema()
)
  AND table_name LIKE 'lab_v_%'
ORDER BY table_name, ordinal_position;
```

Truy vấn metadata có thể được công cụ/role giới hạn theo quyền. Nó giúp biết **hợp đồng cột đầu ra**, nhưng không tự giải thích `net_revenue` đến từ công thức nào.

## 14. Truy vết phụ thuộc trực tiếp bằng `pg_rewrite` và `pg_depend`

Trong PostgreSQL, thông tin phụ thuộc của view liên quan tới **quy tắc viết lại truy vấn** (*rewrite rule*), thường là rule `_RETURN`. Chỉ dò bảng `pg_class` theo tên view mà không xét `pg_rewrite`/`pg_depend` sẽ bỏ qua cấu trúc quan trọng.

Truy vấn sau tìm **cạnh phụ thuộc trực tiếp** của các view tạm trong bài:

```sql
SELECT DISTINCT
    view_ns.nspname AS view_schema,
    view_rel.relname AS view_name,
    ref_ns.nspname AS referenced_schema,
    ref_rel.relname AS referenced_object,
    CASE ref_rel.relkind
        WHEN 'r' THEN 'table'
        WHEN 'p' THEN 'partitioned table'
        WHEN 'v' THEN 'view'
        WHEN 'm' THEN 'materialized view'
        ELSE ref_rel.relkind::text
    END AS referenced_kind
FROM pg_rewrite AS rw
JOIN pg_class AS view_rel
    ON view_rel.oid = rw.ev_class
JOIN pg_namespace AS view_ns
    ON view_ns.oid = view_rel.relnamespace
JOIN pg_depend AS dep
    ON dep.classid = 'pg_rewrite'::regclass
   AND dep.objid = rw.oid
   AND dep.refclassid = 'pg_class'::regclass
   AND dep.deptype = 'n'
JOIN pg_class AS ref_rel
    ON ref_rel.oid = dep.refobjid
JOIN pg_namespace AS ref_ns
    ON ref_ns.oid = ref_rel.relnamespace
WHERE rw.rulename = '_RETURN'
  AND view_rel.relkind = 'v'
  AND view_ns.oid = pg_my_temp_schema()
  AND ref_rel.oid <> view_rel.oid
ORDER BY view_name, referenced_object;
```

### 14.1. Ý nghĩa bảng hệ thống

| Catalog | Vai trò |
|---|---|
| `pg_class` | Đối tượng quan hệ: bảng, view, materialized view... |
| `pg_namespace` | Schema của đối tượng |
| `pg_rewrite` | Quy tắc rewrite; view được biểu diễn bằng rule truy vấn |
| `pg_depend` | Ghi nhận phụ thuộc giữa đối tượng/thành phần catalog |
| `pg_get_viewdef` | Tái tạo định nghĩa truy vấn của view |

`dep.refobjid` giúp xác định quan hệ **được tham chiếu**. `DISTINCT` gom những phụ thuộc có thể phát sinh nhiều dòng do từng cột hay biểu thức thành **một cạnh ở mức đối tượng**.

### 14.2. Dạng kết quả mong đợi

```text
lab_v_paid_orders          → lab_orders
lab_v_paid_orders          → lab_customers
lab_v_order_net            → lab_v_paid_orders
lab_v_order_net            → lab_refunds
lab_v_region_monthly       → lab_v_order_net
lab_v_region_monthly_trend → lab_v_region_monthly
```

Những cạnh này là **phụ thuộc trực tiếp**. Ví dụ `lab_v_region_monthly_trend` không trực tiếp tham chiếu `lab_orders` trong SQL định nghĩa của nó, nhưng **phụ thuộc gián tiếp** theo chuỗi.

### 14.3. Catalog không phải bộ giải thích nghiệp vụ

Truy vấn phụ thuộc trên có những giới hạn:

- Nó dựng **quan hệ giữa đối tượng**, không tự sinh công thức giải thích giá trị 420.
- Không tự phát hiện mọi dữ liệu ngoài database, hàm gọi HTTP, truy vấn động trong ứng dụng hoặc pipeline ETL.
- Khi view gọi hàm SQL/PLpgSQL, phụ thuộc đến **bảng truy vấn bên trong hàm** có thể không biểu diễn thành những cạnh bảng-view đơn giản như một `FROM` tĩnh.
- Một view có thể không phụ thuộc một bảng trong `FROM` nhưng có **phụ thuộc tới function/type/collation** khác.
- Kết quả catalog phụ thuộc phiên bản PostgreSQL, quyền quan sát và loại đối tượng.

Vì vậy, dùng catalog để **khoanh vùng**; dùng định nghĩa SQL, schema, thông tin nghiệp vụ và dữ liệu để **giải thích**.

## 15. Dùng recursive CTE để lần ngược toàn bộ các tầng

Với hàng chục view lồng nhau, đọc từng định nghĩa thủ công rất mất thời gian. Ta có thể **đi đệ quy trên đồ thị phụ thuộc**.

Ví dụ sau bắt đầu từ `lab_v_region_monthly_trend` và lần theo các quan hệ được tham chiếu:

```sql
WITH RECURSIVE
edges AS (
    SELECT DISTINCT
        rw.ev_class AS from_oid,
        dep.refobjid AS to_oid
    FROM pg_rewrite AS rw
    JOIN pg_depend AS dep
        ON dep.classid = 'pg_rewrite'::regclass
       AND dep.objid = rw.oid
       AND dep.refclassid = 'pg_class'::regclass
       AND dep.deptype = 'n'
    WHERE rw.rulename = '_RETURN'
      AND rw.ev_class <> dep.refobjid
),
walk AS (
    SELECT
        'pg_temp.lab_v_region_monthly_trend'::regclass::oid
            AS object_oid,
        0 AS depth,
        ARRAY[
            'pg_temp.lab_v_region_monthly_trend'::regclass::oid
        ] AS visited

    UNION ALL

    SELECT
        e.to_oid,
        w.depth + 1,
        w.visited || e.to_oid
    FROM walk AS w
    JOIN edges AS e
        ON e.from_oid = w.object_oid
    WHERE NOT e.to_oid = ANY(w.visited)
)
SELECT
    w.depth,
    REPEAT('  ', w.depth)
        || FORMAT('%I.%I', n.nspname, c.relname) AS object_name,
    CASE c.relkind
        WHEN 'r' THEN 'table'
        WHEN 'p' THEN 'partitioned table'
        WHEN 'v' THEN 'view'
        WHEN 'm' THEN 'materialized view'
        ELSE c.relkind::text
    END AS object_kind
FROM walk AS w
JOIN pg_class AS c
    ON c.oid = w.object_oid
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
ORDER BY w.depth, object_name;
```

### 15.1. Cách đọc

`depth = 0`: chính view báo cáo.

`depth = 1`: những đối tượng nó trực tiếp dùng, ở đây là `lab_v_region_monthly`.

`depth = 2`: đối tượng được dùng bởi tầng 1, ở đây `lab_v_order_net`.

Tiếp tục đến khi gặp bảng nguồn. Một đối tượng có thể xuất hiện **trên nhiều đường đi**, vì vậy kết quả đệ quy không nhất thiết là một danh sách không trùng tuyệt đối.

### 15.2. Vì sao có `visited`?

```sql
WHERE NOT e.to_oid = ANY(w.visited)
```

giúp tránh quay lại **một OID đã có trên chính đường truy vết đó**, phòng vòng lặp trong quá trình duyệt các quan hệ phụ thuộc có cấu trúc phức tạp. Các chuỗi view thông thường được PostgreSQL kiểm soát phụ thuộc, nhưng công cụ dựng đồ thị vẫn nên có cơ chế giới hạn đường đi.

### 15.3. `depth` không phải thứ tự vật lý database thực thi

Đệ quy này đi trên **cấu trúc định nghĩa**, không đo được:

- Có bao nhiêu lần quét bảng thật.
- Phép join nào chạy trước.
- Sort/aggregate có thực sự materialize hay không.
- Thời gian hoặc số trang dữ liệu bị đọc.

Muốn biết hiệu năng phải xem kế hoạch truy vấn bằng `EXPLAIN`.

### 15.4. Truy vết xuôi (*impact analysis*)

`edges` ở trên có ý nghĩa:

```text
from_oid = view phụ thuộc
to_oid   = đối tượng được tham chiếu
```

Muốn biết những view nào **phụ thuộc vào một bảng nguồn**, cần **đảo chiều duyệt**:

```sql
-- Ý tưởng logic:
-- Bắt đầu từ OID bảng nguồn.
-- Ở mỗi bước, tìm edges.to_oid = current_object_oid,
-- lấy edges.from_oid là view đang phụ thuộc.
```

Có thể viết recursive CTE tương tự, đổi điều kiện join thành:

```sql
JOIN edges AS e
    ON e.to_oid = w.object_oid
```

và bước tiếp là `e.from_oid`. Đừng dùng nguyên hướng duyệt ngược khi cần tìm **báo cáo chịu ảnh hưởng** từ một bảng.

## 16. Truy vết ở mức cột: không chỉ biết view đọc bảng nào

Giả sử có các cột:

```text
lab_orders.amount
      ↓ đổi tên
lab_v_paid_orders.gross_amount
      ↓ giữ nguyên
lab_v_order_net.gross_amount
      ↓ SUM
lab_v_region_monthly.gross_revenue
      ↓ chuyển tiếp
lab_v_region_monthly_trend.gross_revenue
```

Đây là **column lineage**. Cũng có một đường khác:

```text
lab_refunds.refund_amount
      ↓ SUM theo order_id
lab_v_order_net.refunded_amount
      ↓ SUM theo (region, month_start)
lab_v_region_monthly.refunded_amount
      ↓ net = gross - refund
lab_v_region_monthly_trend.net_revenue
```

### 16.1. `refobjsubid` trong catalog

Trong `pg_depend`, phụ thuộc quan hệ có thể ghi cụ thể **số thứ tự cột** qua `refobjsubid`. Các thông tin đó có thể hỗ trợ phân tích một view tham chiếu **cột nguồn nào**.

Tuy nhiên, phụ thuộc cột trong catalog **không phải mapping biểu thức đầu-ra hoàn chỉnh**. Ví dụ một view có:

```sql
CASE
    WHEN status = 'PAID' THEN amount
    ELSE 0
END AS paid_amount
```

catalog có thể cho biết view dùng `status` và `amount`, nhưng để giải thích chính xác điều kiện và nhánh `CASE` tạo cột `paid_amount`, cần đọc/parse biểu thức SQL.

### 16.2. Một cột đầu ra có nhiều nguồn

`lab_v_order_net.net_amount` phụ thuộc cả:

- `lab_orders.amount` thông qua `gross_amount`.
- `lab_refunds.refund_amount` thông qua `SUM` và `COALESCE`.

Hơn nữa, **dòng nào góp vào cột đó** phụ thuộc:

- `order_status='PAID'`.
- Khóa nối `lab_orders.customer_id = lab_customers.customer_id`.
- Khóa nối hoàn tiền theo `order_id`.
- Kỳ được tính từ `ordered_at`.

Do đó, column lineage cần ghi cả **công thức, bộ lọc, join và đơn vị/độ hạt**, không chỉ danh sách tên cột.

## 17. Điều kiện lọc ở mỗi tầng có thể thay đổi ý nghĩa báo cáo

Giả sử có yêu cầu “chỉ hiển thị South”. Có hai cách với hai ý nghĩa khác nhau:

**Cách A — lọc kết quả tổng hợp ở ngoài:**

```sql
SELECT *
FROM lab_v_region_monthly
WHERE region = 'South';
```

Chỉ các dòng South được hiển thị. Logic tổng hợp của view vẫn được định nghĩa trên mọi vùng.

**Cách B — sửa view tầng 1 để chỉ lấy South:**

```sql
-- Minh họa ý tưởng, không chạy đè lên view thực hành:
-- WHERE o.order_status='PAID' AND c.region='South'
```

Nếu tầng 1 chỉ còn South thì **tất cả view phụ thuộc** không còn dữ liệu North, không chỉ một báo cáo cụ thể.

### 17.1. Filter sớm có thể đúng hoặc sai

Việc đẩy điều kiện lọc vào tầng nguồn có thể:

- Giảm lượng dữ liệu xử lý.
- Làm rõ một **tập dữ liệu chuẩn hóa**.
- Hoặc vô tình thay đổi chỉ số dùng chung bởi các báo cáo khác.

Nếu một view được dùng lại ở nhiều nơi, **thay đổi `WHERE` của view thấp** có phạm vi ảnh hưởng rộng hơn thêm `WHERE` ở một truy vấn consumer.

### 17.2. Lọc trước và sau `GROUP BY` khác nhau

Muốn “tổng doanh thu của những đơn từ khách hàng đang hoạt động”, ta phải quyết định bộ lọc hoạt động:

- Ở thời điểm đặt hàng?
- Ở thời điểm chạy báo cáo?
- Hay hoàn toàn không liên quan đến doanh thu lịch sử?

Với dữ liệu sự kiện có trạng thái thay đổi theo thời gian, một view lồng nhau chỉ dùng `customers.is_active` **hiện tại** có thể làm báo cáo tháng trước tự thay đổi khi khách bị khóa hôm nay.

Một view không bảo đảm cách hiểu “đúng theo lịch sử” nếu nguồn không lưu trạng thái tại mốc cần xem.

## 18. `LEFT JOIN`, `NULL` và các điều kiện ẩn

Trong tầng 2:

```sql
FROM lab_v_paid_orders AS p
LEFT JOIN refund_totals AS r
    ON r.order_id = p.order_id
```

`LEFT JOIN` giữ những đơn không có hoàn tiền; phần `r.refunded_amount` sẽ `NULL` rồi được đổi thành 0.

### 18.1. Một điều kiện sai có thể biến `LEFT JOIN` thành tương đương `INNER JOIN`

Ví dụ:

```sql
-- Minh họa nguy cơ:
SELECT p.order_id, r.refunded_amount
FROM lab_v_paid_orders AS p
LEFT JOIN (
    SELECT order_id, SUM(refund_amount) AS refunded_amount
    FROM lab_refunds
    GROUP BY order_id
) AS r
    ON r.order_id = p.order_id
WHERE r.refunded_amount > 0;
```

Điều kiện `WHERE r.refunded_amount > 0` loại mọi đơn không có hoàn tiền, vì với chúng `r.refunded_amount IS NULL`. Kết quả trở thành **chỉ những đơn có hoàn tiền**, dù cú pháp dùng `LEFT JOIN`.

Nếu view này được dùng để tính doanh thu tổng, các đơn không hoàn có thể **biến mất**. Đây là lỗi lồng view rất khó nhìn thấy ở dashboard cuối.

### 18.2. `COALESCE` phải có ý nghĩa nghiệp vụ

Trong bài, không có sự kiện hoàn tiền đồng nghĩa **tổng hoàn tiền bằng 0** đối với đơn PAID đó, nên:

```sql
COALESCE(r.refunded_amount, 0::numeric)
```

là quy tắc hợp lý.

Nhưng nếu dữ liệu hoàn tiền **chưa nạp đủ**, `NULL` không có nghĩa 0. Khi này cần metadata về **độ đầy đủ dữ liệu**, thay vì để `COALESCE` che lỗi pipeline.

### 18.3. `NULL` trong phép tổng hợp

`SUM(column)` bỏ qua các giá trị `NULL` và trả `NULL` nếu không có giá trị khác `NULL` trong nhóm đầu vào. `COUNT(*)` đếm dòng, còn `COUNT(column)` chỉ đếm giá trị **không `NULL`**.

Một view trung gian biến `NULL` thành 0 hoặc loại dòng trước aggregate sẽ thay đổi kết quả ở view trên. Truy vết chính xác phải biết **ở tầng nào** việc đó xảy ra.

## 19. Tại sao `SELECT *` gây khó quản lý view lồng nhau?

Một view có thể được tạo như sau:

```sql
CREATE VIEW v_next AS
SELECT *
FROM v_previous;
```

Trong PostgreSQL, danh sách cột `*` được phân giải ở thời điểm định nghĩa view. Khi thêm cột mới vào bảng/view nguồn, không nên mặc định **cột mới sẽ tự xuyên qua mọi lớp view đã tạo**.

### 19.1. Rủi ro của wildcard

- Không rõ view công khai những cột nào.
- Thứ tự cột có thể là một phần của hợp đồng với consumer.
- Khi đọc định nghĩa, khó biết cột nào thật sự cần.
- Cột dữ liệu nhạy cảm có thể bị đưa ra tầng trên khi tạo mới view nếu dùng `*` không kiểm soát.
- Thay đổi schema có thể đòi tái tạo view phụ thuộc theo thứ tự chính xác.

**Thực hành tốt:** khai báo cột đầu ra tường minh:

```sql
CREATE VIEW v_order_public AS
SELECT
    order_id,
    customer_id,
    amount
FROM orders;
```

Điều này giúp view có **hợp đồng cột** rõ ràng và làm column lineage dễ đọc hơn.

### 19.2. Đổi tên cột là thay đổi hợp đồng

Nếu tầng 2 đổi `net_amount` thành `revenue_after_refund`, các view trên tham chiếu `net_amount` có thể cần được cập nhật. Tên dễ hiểu hơn là một cải tiến, nhưng không phải lúc nào cũng là thay đổi tương thích ngược.

Với hệ dùng chung, cân nhắc:

1. Tạo cột mới nhưng tạm giữ cột cũ trong giai đoạn chuyển tiếp nếu phù hợp.
2. Cập nhật các view phụ thuộc và consumer theo kế hoạch.
3. Kiểm chứng cả logic lẫn truy vấn gọi.
4. Chỉ bỏ tên cũ sau khi các phụ thuộc đã được di chuyển.

## 20. Thay đổi view: `CREATE OR REPLACE`, `DROP` và phụ thuộc

Trong PostgreSQL, `CREATE OR REPLACE VIEW` có thể thay đổi **câu SELECT định nghĩa view** trong phạm vi những ràng buộc của cấu trúc cột đầu ra.

### 20.1. `CREATE OR REPLACE VIEW` có giới hạn hợp đồng cột

Khi thay view hiện có, PostgreSQL yêu cầu danh sách cột đầu ra hiện hữu phải giữ **tên, thứ tự và kiểu dữ liệu** tương ứng; có thể thêm **cột mới ở cuối** trong các điều kiện được hỗ trợ. Không thể tùy tiện đổi tên, đổi kiểu hoặc bỏ cột cũ bằng `OR REPLACE` như một migration không tương thích.

Ví dụ thay **quy tắc chọn đơn** của `lab_v_paid_orders` nhưng giữ nguyên tất cả cột, kiểu và thứ tự có thể phù hợp với `OR REPLACE`. Tuy nhiên, **các view phía trên sẽ chịu ảnh hưởng logic** ngay khi đọc view nguồn mới.

```sql
-- Chỉ minh họa ý tưởng; KHÔNG chạy để tránh đổi dữ liệu thực hành:
-- CREATE OR REPLACE VIEW lab_v_paid_orders AS
-- SELECT ... (cùng các cột cũ)
-- FROM ...
-- WHERE ... (logic mới);
```

### 20.2. `DROP VIEW` có thể bị chặn bởi dependency

Trong chuỗi bài học, nếu thử:

```sql
-- KHÔNG chạy trong mạch bài học:
DROP VIEW lab_v_paid_orders;
```

PostgreSQL sẽ không tự động cho xóa một view đang được view khác phụ thuộc mà không xử lý phụ thuộc.

### 20.3. Nguy cơ `CASCADE`

```sql
-- RẤT NGUY HIỂM khi chạy trên hệ thật; KHÔNG chạy:
DROP VIEW lab_v_paid_orders CASCADE;
```

`CASCADE` có thể **xóa các đối tượng phụ thuộc**, bao gồm những view ở tầng trên. Trên hệ báo cáo thật, điều này có thể làm đứt API/dashboard hoặc các đối tượng mà người vận hành không hề dự định xóa.

Đừng dùng `CASCADE` chỉ để “làm cho lệnh chạy được”. Trước khi đổi hoặc xóa view, phải lập **đồ thị phụ thuộc và kế hoạch migration**.

### 20.4. Thay đổi bảng gốc cũng ảnh hưởng view

Nếu một view dùng `lab_orders.amount`, lệnh bỏ cột `amount` ở bảng nguồn sẽ gặp quy tắc phụ thuộc của PostgreSQL. Một lệnh `DROP COLUMN ... CASCADE` có thể tác động những đối tượng phụ thuộc xa hơn.

Nên xem trước **backward/forward lineage**, thiết kế migration theo thứ tự, giữ tên hoặc thêm cột chuyển tiếp nếu consumer còn sử dụng.

## 21. Quản lý phiên bản và hợp đồng của view

View thường được dùng như một **API dữ liệu**. Ví dụ:

```text
reporting.v_orders_paid_v1
reporting.v_orders_paid_v2
reporting.v_revenue_monthly_v1
reporting.v_revenue_monthly_v2
```

Nếu thay đổi logic ảnh hưởng ý nghĩa chỉ số, tạo một view phiên bản mới có thể an toàn hơn sửa âm thầm view đang được nhiều đội sử dụng.

### 21.1. Những thay đổi được xem là “breaking”

Không chỉ đổi tên cột mới có thể phá hợp đồng. Các thay đổi sau cũng đáng chú ý:

- Từ **một dòng mỗi đơn** thành **một dòng mỗi đơn × sự kiện hoàn**.
- Thay `INNER JOIN` bằng `LEFT JOIN` hoặc ngược lại.
- Thêm điều kiện `WHERE` loại một nhóm nghiệp vụ.
- Thay `gross_revenue` thành `net_revenue` nhưng giữ tên cột cũ.
- Đổi thời gian nhóm từ UTC sang `Asia/Ho_Chi_Minh`.
- Chuyển đơn vị tiền từ VND sang **nghìn VND**.
- Đổi cách coi trạng thái `REFUNDED`/`CANCELLED`/`PAID`.
- Bỏ việc tạo đủ tháng lịch và khiến MoM lùi về “dòng có dữ liệu gần nhất”.

Một query vẫn chạy được **không có nghĩa người dùng cuối vẫn nhận đúng chỉ số như trước**.

### 21.2. Metadata nên có

| Thuộc tính | Ví dụ |
|---|---|
| `view_name` | `reporting.v_region_monthly` |
| `business_owner` | Nhóm phụ trách định nghĩa doanh thu |
| `technical_owner` | Nhóm dữ liệu/DBA |
| `grain` | Một dòng cho mỗi `(region, month_start)` |
| `input_sources` | `v_order_net` |
| `output_columns` | `paid_orders`, `gross_revenue`, `net_revenue` |
| `filter_rules` | Chỉ đơn `PAID` theo định nghĩa thống nhất |
| `time_zone` | `Asia/Ho_Chi_Minh` |
| `currency/unit` | Một đơn vị tiền tệ xác định |
| `freshness` | Phụ thuộc pipeline nguồn hoặc refresh |
| `data_quality` | Trạng thái hoàn tất của kỳ |
| `change_log` | Phiên bản logic, thời điểm đổi, lý do |
| `consumers` | Dashboard, API, job |

Một số metadata được SQL thể hiện trực tiếp; một số cần catalog/documentation ở ngoài SQL. Mục tiêu là để người mới không phải suy đoán ý nghĩa cột chỉ từ tên.

## 22. Quyền truy cập và an toàn khi view lồng nhau

View có thể được dùng để cung cấp một tập cột/dòng có kiểm soát cho người đọc. Nhưng **view không tự là hàng rào bảo mật tuyệt đối**.

### 22.1. Ai cần quyền trên bảng gốc?

Trong PostgreSQL, hành vi quyền của view chịu ảnh hưởng **chủ sở hữu view**, cấu hình và phiên bản. Với view thông thường, truy cập các quan hệ nguồn thường được kiểm tra theo **quyền của owner view**; còn với tùy chọn **`security_invoker`** trong các phiên bản hỗ trợ (PostgreSQL 15+), quyền trên quan hệ nguồn được kiểm tra theo **người gọi**.

Không suy ra rằng cấp `SELECT` trên view luôn an toàn để ẩn mọi dữ liệu. Cần thiết kế:

- Những cột nào view thực sự trả ra.
- Những dòng nào có thể được xem.
- Ai sở hữu view và bảng.
- Row-Level Security (RLS) có được áp dụng đúng ngữ cảnh không.
- Các hàm được gọi trong biểu thức có hành vi và quyền gì.

### 22.2. View nhiều tầng làm quyền phức tạp hơn

```text
Role báo cáo → v_dashboard → v_monthly → v_orders → orders
```

Một lần thay owner, `security_invoker`, quyền trên view/bảng hoặc RLS ở một tầng có thể đổi khả năng truy cập của người dùng ở tầng cuối. **Lineage về quyền** không chỉ là lineage về dữ liệu.

### 22.3. `security_barrier` và predicate pushdown

PostgreSQL có tùy chọn `security_barrier` cho view nhằm thay đổi một số quy tắc tối ưu liên quan tới thứ tự đánh giá các điều kiện có thể rò rỉ dữ liệu. Nó có ích trong một số mô hình bảo mật, nhưng **không phải** thay thế cho RLS, quyền role, kiểm soát hàm và chính sách truy cập toàn hệ.

Các quyết định bảo mật nên được kiểm chứng theo tài liệu phiên bản PostgreSQL và mô hình quyền thực tế. Không coi một `WHERE tenant_id=...` trong view là đủ nếu đầu vào tenant có thể bị người dùng điều khiển tùy ý.

### 22.4. Truy vết logic cần biết cả chính sách truy cập

Khi hai người dùng chạy cùng `SELECT` trên cùng tên view nhưng thấy số dòng khác nhau, phải kiểm tra:

- RLS có lọc theo identity/role không?
- View có tham chiếu `current_user`, `session_user` hoặc cấu hình session không?
- Có function phụ thuộc ngữ cảnh người gọi không?
- Có `security_invoker` hay owner khác nhau không?
- Có sự khác biệt thời gian/snapshot hoặc dữ liệu đã thay đổi giữa hai lần chạy không?

Không vội kết luận view bị lỗi chỉ vì hai người nhận kết quả khác.

## 23. Nested view có thể cập nhật được không?

**Không phải view nào cũng cho `INSERT`, `UPDATE`, `DELETE`.** Trong PostgreSQL, một số view đơn giản có thể **tự động cập nhật** thông qua bảng nguồn; các view có aggregate, `DISTINCT`, nhiều cấu trúc join phức tạp hoặc phép tính không phù hợp thường không tự động updatable theo quy tắc tương ứng.

Ví dụ đơn giản (giả định tạo trên bảng tạm khách hàng):

```sql
CREATE TEMP VIEW lab_v_north_customers AS
SELECT customer_id, customer_name, region
FROM lab_customers
WHERE region = 'North'
WITH CHECK OPTION;
```

Trong các điều kiện hỗ trợ, đây là một view đơn giản trên **một bảng**, có thể cập nhật qua view. `WITH CHECK OPTION` yêu cầu thay đổi qua view vẫn thỏa điều kiện của view theo quy tắc áp dụng.

```sql
BEGIN;

UPDATE lab_v_north_customers
SET customer_name = 'An Updated'
WHERE customer_id = 1
RETURNING customer_id, customer_name, region;

ROLLBACK;
```

### 23.1. Nested view và `CHECK OPTION`

Có thể xây một view đơn giản khác dựa trên `lab_v_north_customers`:

```sql
CREATE TEMP VIEW lab_v_north_customer_ids AS
SELECT customer_id, customer_name, region
FROM lab_v_north_customers
WHERE customer_id > 0
WITH CASCADED CHECK OPTION;
```

`LOCAL` và `CASCADED` có ý nghĩa liên quan tới **những điều kiện của view hiện tại và view bên dưới** khi thao tác qua chuỗi view tự động cập nhật, với các giới hạn riêng nếu gặp tầng có `INSTEAD OF` trigger/rule.

Trong thực hành, không được mặc định thêm một view đơn giản lên một view tổng hợp như `lab_v_region_monthly` sẽ tạo ra đường cập nhật ngược về từng đơn hàng. Một dòng tổng hợp có thể đại diện cho nhiều đơn, nên database không có một cách duy nhất để hiểu “sửa `net_revenue` thành 500” là phải sửa đơn hàng nào.

### 23.2. Rủi ro `INSTEAD OF` trigger/rule

PostgreSQL có thể dùng trigger/rule thích hợp để thực thi DML qua một số view không tự cập nhật. Khi đó, **SQL hiển thị của view không còn đủ để hiểu tác động ghi**: phải truy vết **trigger/rule**, bảng đích, quyền và transaction.

Với view báo cáo thuần đọc, thường nên cấp quyền phù hợp để không có đường ghi ngoài dự kiến.

## 24. View thông thường so với materialized view

Đây là điểm quan trọng vì chữ “view” xuất hiện ở cả hai loại.

| Khía cạnh | View thông thường | Materialized view |
|---|---|---|
| Định nghĩa | Lưu câu truy vấn | Lưu định nghĩa truy vấn |
| Dữ liệu kết quả | Tính theo truy vấn lúc đọc, theo ngữ cảnh transaction | **Lưu kết quả vật lý** đã tính |
| Tính mới | Phụ thuộc dữ liệu nguồn và snapshot lúc query | Phụ thuộc lần **refresh** gần nhất |
| Bảo trì | Không có thao tác refresh định kỳ riêng | Cần `REFRESH MATERIALIZED VIEW` hoặc cơ chế làm mới |
| Chỉ mục | Thường tạo trên bảng nguồn | Có thể tạo chỉ mục trên materialized view |
| Lineage | View → bảng/view nguồn | Materialized view → định nghĩa nguồn **và thời điểm snapshot** |
| Nguy cơ | Truy vấn phức tạp có thể chậm | Kết quả có thể **stale** khi nguồn đã thay đổi |

### 24.1. Ví dụ materialized view trên view tổng hợp

Trong một môi trường thử riêng, có thể tạo:

```sql
CREATE MATERIALIZED VIEW lab_mv_region_monthly AS
SELECT
    region,
    month_start,
    paid_orders,
    gross_revenue,
    refunded_amount,
    net_revenue
FROM lab_v_region_monthly;
```

Tuy nhiên, vì các view chính trong bài tham chiếu **bảng tạm**, việc tạo materialized view thường trực dựa trên chúng không phải mô hình vận hành phù hợp cho người dùng khác và các phiên khác. **Đoạn trên chỉ mang tính minh họa khái niệm; để thực hành thực tế, hãy dựng bảng/view nguồn dùng chung trong một schema thử nghiệm riêng rồi tạo materialized view dựa trên nguồn phù hợp.**

Làm mới:

```sql
REFRESH MATERIALIZED VIEW lab_mv_region_monthly;
```

Lệnh refresh cập nhật snapshot của materialized view theo cơ chế PostgreSQL. Nó không tự chạy chỉ vì `lab_orders` vừa có đơn mới.

### 24.2. Truy vết phải thêm “thời điểm cập nhật”

Nếu dashboard đọc materialized view, người dùng cần biết:

- Nó đang lấy giá trị được tính từ lần refresh nào?
- Dữ liệu nguồn đã hoàn tất đến mốc nào?
- Có refresh thất bại hoặc bị trì hoãn không?
- Có nhiều materialized view lồng nhau cần refresh theo **thứ tự phụ thuộc** không?

Hai báo cáo đọc cùng schema có thể khác nhau nếu một bên đọc view thường, một bên đọc materialized view chưa được làm mới.

### 24.3. `EXPLAIN` không biến view thường thành materialized view

Trong plan của một câu truy vấn, optimizer có thể tạo bước `Materialize` hoặc materialization tạm thời vì lý do thực thi. Điều đó **không có nghĩa** SQL object ban đầu là `MATERIALIZED VIEW` và có dữ liệu được lưu bền vững qua các lần chạy.

## 25. View lồng nhau so với CTE và bảng trung gian

Ba cách thường mô tả pipeline SQL:

**A. View lồng nhau:**

```sql
CREATE VIEW v_a AS SELECT ... FROM base_table;
CREATE VIEW v_b AS SELECT ... FROM v_a;
SELECT ... FROM v_b;
```

**B. CTE trong một câu truy vấn:**

```sql
WITH a AS (
    SELECT ... FROM base_table
),
b AS (
    SELECT ... FROM a
)
SELECT ... FROM b;
```

**C. Bảng trung gian/snapshot:**

```sql
CREATE TABLE stage_a AS SELECT ... FROM base_table;
CREATE TABLE stage_b AS SELECT ... FROM stage_a;
SELECT ... FROM stage_b;
```

### 25.1. Bảng so sánh

| Tiêu chí | Nested views | CTE | Bảng trung gian |
|---|---|---|---|
| Khả năng dùng lại | Cao qua nhiều câu truy vấn | Thường chỉ trong một câu SQL | Cao nếu bảng được duy trì |
| Định nghĩa logic lưu trong DB | Có | Không như một object view độc lập | Dữ liệu bảng được lưu; truy vấn tạo có thể không còn |
| Được cấp quyền độc lập | Có | Theo câu query và quan hệ nguồn | Có |
| Trạng thái dữ liệu | Thường đọc nguồn khi truy vấn | Thường là xử lý trong truy vấn | Dữ liệu vật lý tại lần nạp/cập nhật |
| Truy vết phụ thuộc từ catalog | Có thể theo view | Không có object CTE độc lập lâu dài | Cần metadata pipeline, không tự suy ra từ bảng |
| Hiệu năng | Tùy planner, SQL và nguồn | Tùy planner và tùy `MATERIALIZED`/`NOT MATERIALIZED` | Có chi phí ghi/làm mới và storage |
| Rủi ro stale | Không tự stale do cache vật lý của view thường | Theo snapshot query | Có thể stale nếu không nạp mới |

### 25.2. Khi nào view lồng nhau phù hợp?

- Logic dùng lại ở nhiều báo cáo/API.
- Cần một hợp đồng cột ổn định có owner.
- Muốn hạn chế lặp các bộ lọc/chuyển đổi nghiệp vụ.
- Có quy trình quản lý phiên bản và đo lường tác động thay đổi.
- Chuỗi tầng ngắn, rõ độ hạt và dễ theo dõi.

### 25.3. Khi nào nên cân nhắc CTE?

- Logic chỉ phục vụ một báo cáo đơn lẻ.
- Muốn nhìn toàn bộ phép biến đổi trong **một file SQL**.
- Tránh tạo nhiều object chỉ dùng một lần.
- Muốn tổ chức các bước của một truy vấn cụ thể mà không mở rộng API schema.

Trong PostgreSQL hiện đại, CTE không đồng nghĩa luôn được materialize thành bảng tạm; optimizer có thể inline hoặc materialize theo tính chất câu truy vấn và tùy chọn.

### 25.4. Khi nào bảng trung gian có ích?

- ETL chạy theo lô và cần đối soát snapshot tại một thời điểm.
- Logic phức tạp, việc tính lại mỗi query quá tốn kém.
- Cần giữ dữ liệu đầu vào/bản chụp để tái hiện báo cáo đã công bố.
- Phải tách các khâu nhập, chuẩn hóa, xác nhận, công bố.

Nhược điểm: phải quản lý **thời điểm nạp, dữ liệu cũ/mới, khóa, idempotency, lỗi giữa các bước**. Một bảng trung gian không tự giải thích nguồn gốc của nó nếu không có metadata pipeline.

## 26. Hiệu năng: planner có thể nhìn xuyên qua nhiều view

Nhiều người tưởng:

```text
SELECT v4
  → thực thi toàn v3 thành bảng
  → thực thi toàn v2 thành bảng
  → thực thi toàn v1 thành bảng
  → rồi mới lọc
```

Đó **không phải mô hình mặc định bắt buộc** của PostgreSQL đối với view thường. Bộ rewrite và optimizer có thể biến truy vấn qua view thành một kế hoạch gồm các phép scan, join, aggregate, window và filter theo cách tối ưu.

### 26.1. Xem kế hoạch thực thi

```sql
EXPLAIN (VERBOSE, COSTS OFF)
SELECT
    region, month_start, net_revenue
FROM lab_v_region_monthly_trend
WHERE region = 'South'
ORDER BY month_start;
```

Tùy phiên bản PostgreSQL, thống kê, kích thước dữ liệu và tùy chọn planner, kế hoạch có thể gồm:

- `Seq Scan` hoặc `Index Scan` các bảng nguồn.
- `Hash Join`, `Nested Loop`, `Merge Join`.
- `HashAggregate`/`GroupAggregate` để tổng hợp.
- `WindowAgg` cho `LAG`.
- `Sort` cho các khóa phân vùng và sắp xếp.

**Không có yêu cầu mọi tên view phải xuất hiện thành node riêng trong plan.** Việc không thấy `lab_v_paid_orders` dưới dạng một node không có nghĩa optimizer bỏ qua điều kiện lọc của view.

### 26.2. Vì sao view lồng nhau vẫn có thể chậm?

Các nguyên nhân điển hình:

1. Bảng nguồn rất lớn, thiếu chỉ mục hoặc lọc yếu.
2. Join làm tăng đột biến số dòng.
3. Aggregate/window đòi sort và bộ nhớ lớn.
4. Hàm tốn kém hoặc không thể tối ưu/đẩy xuống.
5. Điều kiện được áp sau aggregate/window khi không thể chuyển lên sớm mà giữ đúng ngữ nghĩa.
6. Security barrier hoặc rào cản tối ưu theo cấu trúc logic.
7. Truy vấn đọc **nhiều lần** cùng logic qua các nhánh khác nhau.
8. Bản thân định nghĩa view chứa nhiều lớp điều kiện/mối nối không cần thiết.

Không nên gộp hoặc xóa tầng view chỉ vì “nhiều tầng chắc chắn chậm”. Hãy xem kế hoạch thực tế và độ hạt dữ liệu.

### 26.3. `EXPLAIN ANALYZE` cần thận trọng

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT ...
FROM lab_v_region_monthly_trend;
```

Trên truy vấn `SELECT` phù hợp, `ANALYZE` **thực thi truy vấn thật** để đo. Với `INSERT`, `UPDATE`, `DELETE`, nó cũng thực thi thao tác thay đổi dữ liệu; muốn đo thử phải dùng transaction và rollback thích hợp. Không chạy `EXPLAIN ANALYZE` trên câu DML production mà không kiểm soát tác động.

### 26.4. Khóa join và chỉ mục

Trong bài:

- `lab_orders.customer_id` nối `lab_customers.customer_id`.
- `lab_refunds.order_id` được tổng hợp theo đơn và nối với `lab_v_paid_orders.order_id`.

Trên dữ liệu lớn, chỉ mục có thể hữu ích cho cột lọc/khóa join:

```sql
-- Ví dụ xem xét trên schema thử, không bắt buộc cho vài dòng mẫu.
CREATE INDEX idx_lab_orders_status_customer
    ON lab_orders (order_status, customer_id);

CREATE INDEX idx_lab_refunds_order_id
    ON lab_refunds (order_id);
```

Nhưng thứ tự cột index và quyết định dùng index phải dựa trên truy vấn thật, tính chọn lọc và kế hoạch thực thi. Trên bảng vài dòng, PostgreSQL có thể quét tuần tự và đó là lựa chọn bình thường.

## 27. Vòng phụ thuộc và cách thiết kế đồ thị dễ hiểu

Một chuỗi view thông thường cần có quan hệ phụ thuộc có thể giải quyết:

```text
v_a → table
v_b → v_a
v_c → v_b
```

Nếu bạn cố thiết kế:

```text
v_a → v_b
v_b → v_a
```

thì đó là **phụ thuộc vòng**, không phải “lồng nhau sâu hơn”. PostgreSQL có các ràng buộc đối tượng và quy tắc riêng cho `WITH RECURSIVE`; không nên cố tạo vòng giữa các view để mô hình một thuật toán đệ quy.

### 27.1. View đệ quy là khái niệm khác

`WITH RECURSIVE` trong SQL dùng để tính quan hệ có tính lặp, ví dụ cây danh mục hoặc cấp bậc nhân viên. Nó **không** đồng nghĩa với một đồ thị view mà các object tham chiếu lẫn nhau.

Đệ quy để **duyệt metadata dependency** ở mục 15 cũng khác với việc định nghĩa một **recursive view** trên dữ liệu nghiệp vụ.

### 27.2. Giới hạn độ sâu hợp lý

Không có một số tầng tối ưu áp dụng cho mọi hệ. Nhưng nếu muốn giải thích một chỉ số mà phải đọc 15 view, mỗi view chỉ đổi tên một cột hoặc đặt một `SELECT *`, chuỗi đó khó bảo trì.

Có thể cân nhắc gộp những tầng **không tạo ra hợp đồng hoặc trách nhiệm logic độc lập**, đồng thời giữ những tầng thực sự quan trọng như:

- Chuẩn hóa quyền và dữ liệu nhạy cảm.
- Lọc dữ liệu hợp lệ.
- Chuẩn hóa một–nhiều về đúng độ hạt.
- Tính chỉ số nghiệp vụ.
- Tổng hợp và trình bày.

Mục đích là **dễ truy vết và tái sử dụng**, không phải có nhiều hay ít view theo một con số cố định.

## 28. Những tình huống làm logic biến đổi âm thầm

### 28.1. Dữ liệu nguồn thay đổi sau khi báo cáo đã được công bố

View thường đọc dữ liệu nguồn theo snapshot và quyền truy vấn hiện tại. Nếu một khoản hoàn tiền tháng 7 được chèn bổ sung vào tháng 9, chạy lại cùng câu `SELECT` có thể cho **doanh thu July khác trước**.

Nếu cần tái hiện báo cáo “đã công bố ngày 1/8”, chỉ có định nghĩa view không đủ. Cần có **snapshot dữ liệu**, `as_of`, phiên bản logic và chính sách ghi nhận dữ liệu bổ sung.

### 28.2. Thay đổi hàm dùng trong view

Một view có thể gọi hàm:

```sql
SELECT normalize_region(region)
FROM some_table;
```

Nếu nội dung hàm `normalize_region` được thay đổi, kết quả view có thể đổi mà câu định nghĩa `SELECT` trông không khác. Phân tích lineage cần biết **hàm phụ thuộc** và phiên bản logic của nó, không chỉ bảng/view.

### 28.3. Phụ thuộc cấu hình session

Một view dùng `CURRENT_DATE`, `CURRENT_TIMESTAMP`, `current_setting(...)`, các quy tắc collation hoặc chuyển múi giờ theo phiên có thể cho kết quả khác theo **thời điểm chạy hoặc ngữ cảnh session**.

Nếu dashboard có số liệu thay đổi “không rõ lý do”, kiểm tra:

- Dữ liệu thực tế có đổi không?
- View định nghĩa có đổi không?
- Hàm hoặc cấu hình session có đổi không?
- Múi giờ của kết nối có khác không?
- Có RLS hay điều kiện theo role không?

### 28.4. Dùng `CURRENT_DATE` trong view báo cáo

```sql
CREATE VIEW v_recent_orders AS
SELECT *
FROM orders
WHERE ordered_at >= CURRENT_DATE - INTERVAL '30 days';
```

Ngay cả khi bảng nguồn không đổi, tập kết quả có thể **dịch theo ngày chạy**. Muốn báo cáo tái hiện được, thường nên nhận **mốc `as_of`** từ truy vấn/chương trình hoặc lưu snapshot đã chốt.

### 28.5. `ORDER BY` ở view dưới

Không nên dựa vào thứ tự vô tình được giữ khi view dưới có `ORDER BY`. Với báo cáo cuối, `ORDER BY` của câu ngoài mới thể hiện thứ tự kết quả cần bảo đảm. Với việc chọn “một dòng mới nhất”, phải có `ROW_NUMBER`, `DISTINCT ON` hoặc logic chọn dòng cùng khóa phân xử phù hợp, không chỉ dựa vào view nguồn đã được sắp.

## 29. Mẫu điều tra lỗi view theo tầng

Khi nhận phản ánh “số South tháng 7 sai”, có thể dùng khung sau:

```text
1. Ghi nhận kết quả bị nghi sai:
   view cuối, region, month_start, metric, thời điểm đọc.

2. Xác định định nghĩa hiện tại:
   pg_get_viewdef(view cuối).

3. Dựng đường phụ thuộc:
   view cuối → view tổng hợp → view đơn → bảng nguồn.

4. Kiểm tra độ hạt từng tầng:
   một dòng mỗi nhóm? một dòng mỗi đơn? có bị nhân join?

5. Kiểm tra cột nguồn và công thức:
   gross, refund, net; WHERE, JOIN, GROUP BY, window.

6. Đối chiếu dữ liệu gốc:
   order_id, refund_id, trạng thái, vùng, timestamp.

7. Kiểm tra snapshot và môi trường:
   dữ liệu/logic có đổi? role/RLS/timezone? refresh?

8. Kết luận:
   lỗi nguồn, lỗi lọc, lỗi join, lỗi aggregate, lỗi kỳ,
   quyền hoặc thay đổi định nghĩa.
```

### 29.1. Tập câu SQL chẩn đoán nhanh

```sql
-- Tầng cuối:
SELECT *
FROM lab_v_region_monthly_trend
WHERE region = 'South'
  AND month_start = DATE '2026-07-01';

-- Tầng tổng hợp:
SELECT *
FROM lab_v_region_monthly
WHERE region = 'South'
  AND month_start = DATE '2026-07-01';

-- Tầng đơn thuần:
SELECT order_id, gross_amount, refunded_amount, net_amount
FROM lab_v_order_net
WHERE region = 'South'
  AND month_start = DATE '2026-07-01'
ORDER BY order_id;

-- Bảng nguồn hoàn tiền:
SELECT refund_id, order_id, refund_amount
FROM lab_refunds
WHERE order_id IN (104, 107)
ORDER BY refund_id;
```

Đây là phương pháp **giảm dần phạm vi**, không phải mỗi lần điều tra lại viết một query 200 dòng rồi tìm lỗi trong toàn bộ.

### 29.2. Tại sao ghi lại `query_id` hoặc version có ích?

Trong hệ có nhiều triển khai, cùng tên view có thể mang logic khác nhau giữa staging/production hoặc trước/sau migration. Khi log lỗi:

```text
database / schema
view_name
view_definition_version
metric_name
grain / business_timezone
filters / as_of
observed_value
expected_value
query_execution_time
```

thì đội dữ liệu có thể tái hiện tình huống đáng tin hơn.

## 30. Bài tập tự luyện

Các bài dưới đây dùng **trạng thái dữ liệu sau mục 4 và bốn view ở mục 5–9**. Mỗi bài nên thực hiện trong một phiên thử riêng hoặc bọc `BEGIN ... ROLLBACK` nếu thay đổi dữ liệu. Mục tiêu không chỉ là viết SQL chạy được, mà là **giải thích được đường phụ thuộc và phạm vi ảnh hưởng**.

### Bài 1 — Xác định các tầng

Liệt kê bốn view của bài theo thứ tự từ bảng nguồn tới dashboard. Mỗi view có độ hạt gì? Tầng nào thay đổi độ hạt từ một đơn thành một vùng–tháng?

### Bài 2 — Đếm đơn hợp lệ

Viết `SELECT` trên `lab_v_paid_orders` để đếm các đơn theo vùng. Vì sao đơn 102 và 106 không xuất hiện?

### Bài 3 — Truy vết đơn 104

Giải thích vì sao `lab_v_order_net.net_amount` của đơn 104 bằng `220`. Nêu các khóa chính ở bảng nguồn cần kiểm tra.

### Bài 4 — Bẫy nhân dòng

Hãy chạy `lab_v_paid_orders LEFT JOIN lab_refunds` cho đơn 104. Có bao nhiêu dòng? Nếu `SUM(p.gross_amount)` trực tiếp sau join, kết quả sai là bao nhiêu?

### Bài 5 — Tổng July North

Tính `gross_revenue`, `refunded_amount`, `net_revenue`, `paid_orders` của North tháng 7/2026 từ các đơn nguồn.

### Bài 6 — Tổng July South

Tính doanh thu thuần của South tháng 7 bằng hai đơn 104 và 107. Viết câu SQL kiểm tra từ view tầng 2.

### Bài 7 — Tại sao October không có MoM?

Trong `lab_v_region_monthly_trend`, South tháng 10 có `previous_observed_month` là tháng nào? Vì sao `previous_calendar_net`, `mom_change`, `mom_pct` đều `NULL`?

### Bài 8 — Truy vết xuôi thay đổi refund

Nếu `refund_id=3` tăng từ 30 lên 40, doanh thu thuần của South tháng 7 đổi thành bao nhiêu? MoM South tháng 8 đổi theo hướng nào?

### Bài 9 — Dựng danh sách phụ thuộc trực tiếp

Viết hoặc dùng truy vấn `pg_rewrite`/`pg_depend` để tìm view nào trực tiếp đọc `lab_v_order_net`, và `lab_v_order_net` trực tiếp đọc những quan hệ nào.

### Bài 10 — Truy vết ngược từ tầng cuối

Dùng recursive CTE bắt đầu ở `lab_v_region_monthly_trend`. Phân biệt `depth=0` và các mức bên dưới. Vì sao kết quả từ catalog không tự cho công thức `420 = 220 + 200`?

### Bài 11 — Phân tích cột

Vẽ đường phụ thuộc của cột `net_revenue` cuối cùng tới `lab_orders.amount` và `lab_refunds.refund_amount`. Có phải chỉ một cột nguồn không?

### Bài 12 — Điều kiện lọc thay đổi

Nếu sửa `lab_v_paid_orders` từ `WHERE order_status='PAID'` sang `WHERE order_status IN ('PAID','REFUNDED')`, những view nào có thể bị ảnh hưởng? Vì sao đây là thay đổi logic nghiệp vụ, không chỉ sửa hiệu năng?

### Bài 13 — View làm mất đơn không hoàn

Trong tầng 2, nếu thêm `WHERE r.refunded_amount > 0` sau `LEFT JOIN`, điều gì xảy ra với đơn 101 và 107? Vì sao tổng doanh thu bị sai?

### Bài 14 — `SELECT *`

Một view được tạo bằng `SELECT * FROM lab_v_order_net`. Nếu view nguồn được bổ sung cột `tax_amount`, bạn có thể mặc nhiên tin cột đó xuất hiện ngay ở view con không? Giải thích.

### Bài 15 — Dự đoán tác động `DROP`

Vì sao `DROP VIEW lab_v_paid_orders` có thể bị từ chối? Tại sao không nên thêm `CASCADE` chỉ để lệnh chạy?

### Bài 16 — Tìm định nghĩa view

Viết câu PostgreSQL lấy định nghĩa `lab_v_region_monthly` trong phiên tạm. Phân biệt việc **xem SQL định nghĩa** với **xem execution plan**.

### Bài 17 — Materialized view chưa refresh

Một materialized view lưu doanh thu tháng 7. Có sự kiện hoàn tiền bổ sung ở bảng nguồn nhưng job refresh chưa chạy. Kết quả materialized view có tự đổi ngay không? Muốn truy vết đúng cần thêm metadata gì?

### Bài 18 — View hay CTE?

Bạn có một truy vấn phân tích chỉ dùng trong một báo cáo một lần. Khi nào CTE có thể phù hợp hơn tạo ba view mới? Khi nào tái sử dụng nhiều báo cáo khiến view có lợi?

### Bài 19 — Quyền truy cập và view

Một user có quyền `SELECT` trên view cuối nhưng không trên bảng gốc. Có thể kết luận user sẽ luôn bị từ chối khi đọc view không? Nêu các yếu tố PostgreSQL cần kiểm tra.

### Bài 20 — Updatable view

Vì sao một view `SELECT customer_id, name FROM customers WHERE ...` có thể tự động cập nhật trong các điều kiện phù hợp, trong khi view `SELECT region, SUM(net) ... GROUP BY region` thường không tự động cho phép sửa từng dòng nguồn?

### Bài 21 — Theo dõi thay đổi thời điểm và múi giờ

Nếu đội báo cáo đổi tháng từ giờ Việt Nam sang UTC ở tầng 1, báo cáo tầng 3 có thể khác ở những đơn nào? Vì sao thay đổi này có thể ảnh hưởng cả MoM tầng 4?

### Bài 22 — Thiết kế tài liệu cho một view mới

Giả sử `v_customer_monthly_spend` trả mỗi khách và tháng một dòng. Hãy ghi các thông tin tối thiểu để người khác truy vết được cột `monthly_spend`: độ hạt, nguồn, bộ lọc, công thức, múi giờ, đơn vị, chất lượng dữ liệu và owner.

### Bài 23 — Phân tích đường phụ thuộc xuôi

Nếu bảng `lab_refunds` bị đổi cấu trúc cột `refund_amount`, những view nào phải được xem xét? Vì sao catalog chỉ xác định đường ảnh hưởng chứ không tự chứng minh mọi giá trị thay đổi như thế nào?

### Bài 24 — `EXPLAIN` và nhiều view

Một bạn cho rằng “bốn view chắc chắn tạo bốn bảng tạm rồi mới trả kết quả”. Nhận định này có đúng với view thông thường PostgreSQL không? Dùng công cụ nào để kiểm tra kế hoạch thực thi?

### Bài 25 — Một tháng không có dữ liệu

Trong báo cáo tháng của South, thiếu tháng 9/2026. Có thể dùng `COALESCE` để tự biến nó thành 0 rồi tính MoM không? Cần thêm thông tin hoặc cấu trúc nào?

### Bài 26 — Quy trình điều tra

Dashboard báo South tháng 7 là 500, nhưng yêu cầu nghiệp vụ tính doanh thu sau hoàn tiền. Hãy mô tả các bước lần ngược từ view báo cáo tới các đơn và sự kiện hoàn tiền để xác định chỗ sai.

<details>
<summary>Gợi ý đáp án và lời giải</summary>

**Bài 1:** Chuỗi `lab_v_paid_orders` (một đơn PAID) → `lab_v_order_net` (một đơn PAID đã trừ hoàn) → `lab_v_region_monthly` (một vùng–tháng) → `lab_v_region_monthly_trend` (một vùng–tháng có so kỳ). Tầng 3 là nơi `GROUP BY` làm đổi độ hạt.

**Bài 2:**

```sql
SELECT region, COUNT(*) AS paid_orders
FROM lab_v_paid_orders
GROUP BY region
ORDER BY region;
-- North=4, South=4.
```

Đơn 102 là `PENDING`, 106 là `REFUNDED`, nên bị `WHERE order_status='PAID'` loại ở tầng 1.

**Bài 3:** Đơn 104 có `lab_orders.amount=300`, hai sự kiện refund `refund_id=2` giá trị 50 và `refund_id=3` giá trị 30; `net=300-(50+30)=220`. Truy vết `lab_orders.order_id=104`, `lab_refunds.order_id=104`, `lab_customers.customer_id=3` để xác định South.

**Bài 4:** Hai dòng vì đơn 104 có hai sự kiện hoàn. Nếu tổng `p.gross_amount` sau join, `300+300=600` là sai; phải tổng refund theo đơn trước khi nối.

**Bài 5:** North July có đơn 101 (`500`, không hoàn) và 103 (`700`, hoàn 100). `paid_orders=2`, `gross=1200`, `refund=100`, `net=1100`.

**Bài 6:** South July có đơn 104 net 220 và 107 net 200, tổng **420**.

```sql
SELECT SUM(net_amount) AS net_revenue
FROM lab_v_order_net
WHERE region = 'South'
  AND month_start = DATE '2026-07-01';
```

**Bài 7:** `previous_observed_month = 2026-08-01`, vì không có dòng tháng 9. Nhưng tháng lịch liền trước October phải là September, nên điều kiện khoảng cách một tháng không thỏa và các cột MoM trả `NULL`.

**Bài 8:** Refund của đơn 104 tăng thêm 10, net đơn 104 giảm từ 220 xuống 210; South July giảm từ 420 xuống **410**. South August vẫn 600, nên MoM tuyệt đối của August tăng từ `600-420=180` lên `600-410=190`; tỷ lệ MoM cũng thay đổi vì baseline giảm.

**Bài 9:** `lab_v_region_monthly` trực tiếp đọc `lab_v_order_net`. `lab_v_order_net` trực tiếp đọc `lab_v_paid_orders` và `lab_refunds`. Có thể chạy SQL phụ thuộc ở mục 14.

**Bài 10:** `depth=0` là chính `lab_v_region_monthly_trend`; các mức sâu hơn là view/bảng được nó dùng trực tiếp hoặc gián tiếp. Catalog chỉ ghi đường phụ thuộc, không tự suy ra các phép `SUM`, join và dòng nguồn; cần SQL và dữ liệu.

**Bài 11:** `net_revenue` phụ thuộc `lab_v_order_net.net_amount`, trong đó `gross_amount` từ `lab_orders.amount`, `refunded_amount` từ `SUM(lab_refunds.refund_amount)`; có **hai nguồn tiền** và các điều kiện lọc/join/thời gian liên quan.

**Bài 12:** Tất cả các view phụ thuộc từ tầng 2 tới tầng 4 có thể đổi. Đơn 106 có thể xuất hiện; chính sách tính đơn hoàn toàn đã đổi, nên cần phiên bản/duyệt metric, không xem là tối ưu truy vấn thuần túy.

**Bài 13:** Các đơn không có refund như 101 và 107 bị loại do `WHERE r.refunded_amount>0` không nhận `NULL`. Tổng doanh thu chỉ còn các đơn có hoàn, sai nếu chỉ số yêu cầu **tất cả đơn PAID**.

**Bài 14:** Không. Với PostgreSQL, `SELECT *` trong định nghĩa view được mở rộng khi tạo; thay đổi thêm cột ở nguồn không mặc nhiên truyền cột mới qua các view đã tồn tại. Cần cập nhật hợp đồng view.

**Bài 15:** `lab_v_order_net` phụ thuộc `lab_v_paid_orders`, rồi các tầng tiếp tục phụ thuộc. `DROP VIEW` không xử lý các phụ thuộc có thể bị từ chối; `CASCADE` có thể xóa cả các view liên quan, gây hỏng dashboard/API.

**Bài 16:**

```sql
SELECT pg_get_viewdef(
    'pg_temp.lab_v_region_monthly'::regclass,
    true
);
```

Nó trả SQL định nghĩa. `EXPLAIN SELECT ... FROM lab_v_region_monthly` trả kế hoạch thực thi được optimizer lựa chọn cho truy vấn cụ thể.

**Bài 17:** Không. Materialized view giữ snapshot cho tới khi refresh phù hợp; cần thời điểm refresh, mốc dữ liệu nguồn, trạng thái refresh, phiên bản logic và phụ thuộc materialized view khác nếu có.

**Bài 18:** CTE hữu ích khi logic chỉ thuộc một truy vấn và muốn giảm object lâu dài. View hữu ích khi nhiều consumer cùng dùng một hợp đồng logic được quản lý, cấp quyền và versioning.

**Bài 19:** Không thể kết luận tự động. Với PostgreSQL, cần biết owner, quyền trên view/bảng, `security_invoker` nếu có, RLS, các function và role/phiên thực tế.

**Bài 20:** View đơn giản ánh xạ dòng và cột tới một bảng nên có thể có đường DML tự động. View tổng hợp gộp nhiều dòng thành một nhóm; không có cách cập nhật duy nhất một dòng tổng để biết phải sửa các dòng nguồn nào.

**Bài 21:** Các đơn gần ranh giới đầu/cuối tháng theo UTC vs UTC+7 có thể chuyển tháng. Điều đó làm thay `GROUP BY` tầng 3 và các giá trị/baseline MoM tầng 4.

**Bài 22:** Ghi: mỗi dòng `(customer_id, month_start)`; nguồn bảng/view; điều kiện trạng thái; công thức `monthly_spend`; `AT TIME ZONE`; đơn vị tiền; cách xử lý refund/NULL; freshness/complete; business và technical owner; consumer và version.

**Bài 23:** Cần xem `lab_v_order_net` (trực tiếp dùng refund), `lab_v_region_monthly` và `lab_v_region_monthly_trend` (gián tiếp). Catalog giúp tìm object phụ thuộc; tác động giá trị phụ thuộc biểu thức, dữ liệu và cách đổi schema.

**Bài 24:** Không. PostgreSQL thường mở rộng định nghĩa của view thường và tối ưu kế hoạch. Dùng `EXPLAIN`/`EXPLAIN (VERBOSE, COSTS OFF)` để xem các bước thực tế; không giả định một bảng trung gian vật lý cho mỗi view.

**Bài 25:** Không thể tự coi thiếu kỳ là 0 nếu chưa biết nó đã được nạp đủ. Cần calendar spine theo vùng–tháng và trạng thái kỳ đầy đủ, rồi chỉ điền 0 khi nghiệp vụ xác nhận kỳ hoàn tất không phát sinh.

**Bài 26:** Đọc số 500 ở view cuối, đối chiếu view tổng hợp, xuống `lab_v_order_net` để xem net 220+200, rồi xuống refund events 50+30 của order 104. Nếu dashboard hiển thị 500 thì có thể nó đang lấy `gross_revenue` thay vì `net_revenue`, hoặc tầng trừ hoàn tiền bị bỏ/sai. Cần kiểm tra cột được consumer chọn và định nghĩa view đang triển khai.

</details>

## 31. Checklist thiết kế view dễ truy vết

Trước khi công bố một view mới hoặc sửa một view dùng chung, hãy trả lời:

1. **Một dòng đầu ra đại diện cho gì?** Có khóa logic xác định độ hạt không?
2. **Nguồn trực tiếp là gì?** Bảng/view nào, khóa nối nào?
3. **Những điều kiện lọc nào?** Có làm mất nhóm nghiệp vụ không?
4. **Công thức cột tính toán là gì?** `SUM`, `CASE`, `COALESCE`, quy tắc làm tròn?
5. **Có phép join một–nhiều không?** Có nguy cơ nhân dòng?
6. **`NULL` nghĩa là gì?** Không phát sinh, chưa biết, không áp dụng hay dữ liệu lỗi?
7. **Thời gian và đơn vị đo có rõ không?** Múi giờ, mốc kỳ, tiền tệ, độ chính xác?
8. **View có phụ thuộc các view khác không?** Có thể truy vết backward/forward từ catalog?
9. **Khi thay đổi logic, consumer nào ảnh hưởng?** Có cần version mới hay migration?
10. **Quyền và RLS có đúng không?** Tránh công bố cột/dòng nhạy cảm ngoài chủ đích.
11. **Có materialized view hoặc bảng trung gian không?** Dữ liệu có thể cũ tới mốc nào?
12. **Có thể giải thích một ô kết quả cụ thể không?** Truy được về dòng nguồn và công thức?
13. **Có kế hoạch quan sát hiệu năng không?** `EXPLAIN` và chỉ mục phù hợp?
14. **Có tài liệu người sở hữu và thay đổi không?** Business owner, technical owner, version, changelog?

### 31.1. Ba câu SQL cần nhớ

```sql
-- A. Đọc định nghĩa view hiện có trong phiên PostgreSQL.
SELECT pg_get_viewdef(
    'pg_temp.lab_v_region_monthly_trend'::regclass,
    true
);
```

```sql
-- B. Truy vết mức giá trị của một ô tổng hợp:
-- từ nhóm vùng–tháng xuống từng đơn đã tính net.
SELECT order_id, gross_amount, refunded_amount, net_amount
FROM lab_v_order_net
WHERE region = 'South'
  AND month_start = DATE '2026-07-01'
ORDER BY order_id;
```

```sql
-- C. Xem cách optimizer thực hiện truy vấn qua nhiều view.
EXPLAIN (VERBOSE, COSTS OFF)
SELECT region, month_start, net_revenue
FROM lab_v_region_monthly_trend
ORDER BY region, month_start;
```

## 32. Kết luận

**View lồng nhau** giúp tổ chức SQL thành nhiều lớp rõ trách nhiệm: lọc dữ liệu hợp lệ, chuẩn hóa ở đúng độ hạt, tổng hợp chỉ số và trình bày báo cáo. Tuy nhiên, **mỗi tầng là một hợp đồng logic có thể ảnh hưởng toàn chuỗi**. Một điều kiện `WHERE` ở view thấp, một phép join nhân dòng, một `COALESCE` che dữ liệu thiếu hoặc một thay đổi múi giờ đều có thể làm số cuối cùng sai dù tất cả câu SQL vẫn chạy.

**Khả năng truy vết logic** phải tồn tại ở cả hai chiều:

- **Từ kết quả về nguồn:** biết số liệu được tính từ những dòng nào, qua các phép lọc, nối, tổng hợp và công thức gì.
- **Từ nguồn ra kết quả:** biết bảng, cột, view, dashboard và người dùng nào có thể bị ảnh hưởng khi dữ liệu hoặc logic thay đổi.

Ba nguyên tắc quan trọng nhất:

1. **Mỗi view nên có trách nhiệm, độ hạt và hợp đồng cột rõ ràng**; không dùng nhiều tầng để che giấu nguồn dữ liệu.
2. **Catalog giúp dựng sơ đồ phụ thuộc, nhưng không thay thế việc hiểu SQL và đối chiếu dòng nguồn**; truy vết giá trị cụ thể cần cả dữ liệu và công thức.
3. **Thay đổi một view dùng chung là thay đổi API dữ liệu**: phải xem các phụ thuộc phía trên, quyền, trạng thái dữ liệu, tính mới, khả năng tương thích và kế hoạch triển khai.

Khi có thể đi từ `net_revenue = 420` trên dashboard ngược về **hai đơn hàng, hai sự kiện hoàn tiền, bộ lọc `PAID`, khóa vùng–tháng và phép tính `300 - 50 - 30 + 200`**, bạn đã biến một chuỗi view lồng nhau từ “hộp đen SQL” thành một hệ thống dữ liệu **có thể giải thích, kiểm chứng và bảo trì**.

# So sánh kỳ hiện tại với kỳ trước

Một trong những mẫu truy vấn SQL được sử dụng nhiều nhất trong báo cáo là **so sánh chỉ số của kỳ hiện tại với kỳ liền trước**: doanh số tháng này cao hay thấp hơn tháng trước, số đơn tuần này thay đổi bao nhiêu so với tuần trước, lượng người dùng hoạt động hôm nay tăng hay giảm so với hôm qua. Trong phân tích kinh doanh, các cách so sánh phổ biến có tên **MoM** (*month over month*), **WoW** (*week over week*), **DoD** (*day over day*), **QoQ** (*quarter over quarter*) và **YoY** (*year over year*).

Đây không chỉ là bài toán trừ hai con số. Truy vấn đúng còn phải xác định **thế nào là một kỳ**, **kỳ trước là kỳ nào**, **có đủ dữ liệu hay không**, **cách xử lý kỳ không phát sinh**, **ý nghĩa phần trăm thay đổi** và **có đang so hai khoảng thời gian tương đương hay không**.

Bài học thuộc chương **Mẫu truy vấn** của module **Database SQL**. Nội dung dùng **PostgreSQL** làm môi trường chạy ví dụ, nhưng cách phân tích yêu cầu áp dụng cho các hệ SQL khác. Ta sẽ xây dựng một báo cáo từ dữ liệu chi tiết đến chỉ số theo kỳ, rồi thực hiện so sánh bằng `LAG()`, tự nối bảng tổng hợp theo khóa thời gian, lịch tháng đầy đủ, và các kỹ thuật phù hợp cho từng bài toán.

## 1. Hiểu chính xác yêu cầu “kỳ hiện tại so với kỳ trước”

Giả sử doanh số đơn hàng đã thanh toán được tổng hợp theo tháng:

| Tháng | Giá trị đơn `PAID` (nghìn VND) |
|---|---:|
| 2026-01 | 1.000 |
| 2026-02 | 1.200 |
| 2026-03 | 900 |
| 2026-04 | 0 |
| 2026-05 | 1.500 |
| 2026-06 | 1.600 |
| 2026-07 | 1.250 |

Với tháng 7/2026:

- **Kỳ hiện tại** là tháng 7, giá trị **1.250** nghìn VND.
- **Kỳ trước** là tháng 6, giá trị **1.600** nghìn VND.
- **Chênh lệch tuyệt đối** là `1250 - 1600 = -350` nghìn VND.
- **Tỷ lệ thay đổi** là `(1250 - 1600) / 1600 × 100% = -21,875%`, thường hiển thị **-21,88%**.

Câu tiếng Việt “giảm 350 nghìn đồng so với tháng trước” và “giảm khoảng 21,88%” nói về **hai đơn vị đo khác nhau** nhưng cùng một phép so sánh.

### 1.1. Các cách hiểu khác nhau của “kỳ trước”

| Yêu cầu | Kỳ hiện tại | Kỳ dùng để đối chiếu |
|---|---|---|
| DoD | Một ngày lịch | Ngày lịch liền trước |
| WoW | Một tuần theo quy ước lịch | Tuần liền trước |
| MoM | Một tháng lịch | Tháng liền trước |
| QoQ | Một quý lịch | Quý liền trước |
| YoY | Một tháng/quý/năm | **Cùng kỳ năm trước** |
| MTD so với MTD tháng trước | Từ đầu tháng tới một mốc cắt | Từ đầu tháng trước tới **mốc tương ứng** |
| 7 ngày gần nhất so với 7 ngày trước đó | Khoảng 7 ngày trượt | Khoảng 7 ngày trượt liền trước, không chồng lấn |

**“Tháng trước” khác “cùng tháng năm trước”.** Tháng 7/2026 có tháng trước là **6/2026**, nhưng cùng tháng năm trước là **7/2025**. SQL cần phản ánh đúng mốc đối chiếu mà báo cáo yêu cầu.

### 1.2. Chốt bốn yếu tố trước khi viết SQL

1. **Chỉ số (*metric*)**: đếm đơn hàng, tổng giá trị, doanh thu thuần, số khách duy nhất, tỷ lệ chuyển đổi hay số dư?
2. **Lịch kỳ (*period calendar*)**: ngày/tháng theo UTC hay theo múi giờ doanh nghiệp, tuần bắt đầu thứ Hai hay Chủ nhật, quý lịch hay quý tài chính?
3. **Cấp độ phân tích (*grain*)**: toàn công ty, theo khu vực, theo sản phẩm, theo kênh bán hay theo nhân viên?
4. **Quy tắc đối chiếu**: kỳ liền trước theo lịch, dòng có dữ liệu gần nhất, cùng kỳ năm trước hay khoảng thời gian đã trôi qua tương đương?

Không xác định bốn yếu tố này thì một câu SQL chạy hợp lệ vẫn có thể tạo một báo cáo sai.

## 2. Công thức chênh lệch và tỷ lệ thay đổi

Gọi:

- \(C\): giá trị chỉ số của kỳ hiện tại (*current period*).
- \(P\): giá trị chỉ số của kỳ trước (*previous period*).

**Chênh lệch tuyệt đối**:

\[
\Delta = C-P
\]

**Tỷ lệ thay đổi tương đối** khi \(P \ne 0\):

\[
\mathrm{ChangePct} = \frac{C-P}{P}\times 100\%
\]

Ví dụ tháng 2 so với tháng 1:

```text
C = 1200
P = 1000
Δ = 1200 - 1000 = +200 nghìn VND
% thay đổi = 200 / 1000 × 100 = +20%
```

Tháng 3 so với tháng 2:

```text
C = 900
P = 1200
Δ = -300 nghìn VND
% thay đổi = -300 / 1200 × 100 = -25%
```

### 2.1. Phần trăm thay đổi không phải chênh lệch phần trăm điểm

Với chỉ số là **tỷ lệ**, chẳng hạn tỷ lệ chuyển đổi tăng từ **5%** lên **7%**:

- **Chênh lệch điểm phần trăm**: `7% - 5% = +2 điểm phần trăm` (*percentage points*).
- **Thay đổi tương đối**: `(7% - 5%) / 5% × 100 = +40%`.

Không được nói “tăng 2%” khi đang muốn diễn đạt **+2 điểm phần trăm**. Khi xây dựng dashboard, nhãn cột nên chỉ rõ đơn vị.

### 2.2. Mẫu tính an toàn trong PostgreSQL

```sql
SELECT
    1250::numeric AS current_value,
    1600::numeric AS previous_value,
    1250::numeric - 1600::numeric AS absolute_change,
    ROUND(
        100.0 * (1250::numeric - 1600::numeric)
        / NULLIF(1600::numeric, 0),
        2
    ) AS change_pct;
```

`NULLIF(previous_value, 0)` trả `NULL` khi mẫu số bằng 0, giúp phép chia không gây lỗi chia cho 0. Ở đây `ROUND(..., 2)` làm tròn **phần trăm theo đơn vị `%`**, ví dụ `-21.88`, không phải giá trị tỷ lệ `-0.2188`.

**Quan trọng:** khi kỳ trước bằng 0, tỷ lệ thay đổi thông thường **không xác định**. Tránh tự gán `100%` hay `0%` nếu nghiệp vụ chưa có quy ước rõ.

## 3. Dữ liệu mẫu: đơn hàng theo nhiều tháng

Ta dùng bảng `period_lab_orders`. Mỗi dòng đại diện cho **một đơn hàng**, có ngày đặt hàng, khu vực, trạng thái và giá trị.

| Cột | Ý nghĩa |
|---|---|
| `order_id` | Khóa chính, duy nhất mỗi đơn |
| `ordered_at` | Thời điểm đặt đơn kiểu `TIMESTAMPTZ` |
| `region` | Khu vực `North` hoặc `South` |
| `status` | `PAID`, `PENDING`, `CANCELLED` |
| `amount_k_vnd` | Giá trị đơn tính bằng **nghìn VND**, kiểu số chính xác |

Trong toàn bài, **chỉ số mẫu** là:

> **Tổng giá trị của những đơn hiện có `status = 'PAID'`, phân theo tháng đặt hàng tại múi giờ `Asia/Ho_Chi_Minh`.**

Đây là **chỉ số giá trị đơn đã thanh toán theo tháng đặt hàng**, không tự động đồng nghĩa **doanh thu kế toán đã ghi nhận**. Hệ thống thực có thể phải xét thời điểm thanh toán, hoàn tiền, thuế, chiết khấu và thay đổi trạng thái theo thời gian.

### 3.1. Script tạo bảng tạm PostgreSQL

Chạy trong kết nối thực hành riêng:

```sql
CREATE TEMP TABLE period_lab_orders (
    order_id INTEGER PRIMARY KEY,
    ordered_at TIMESTAMPTZ NOT NULL,
    region TEXT NOT NULL,
    status TEXT NOT NULL,
    amount_k_vnd NUMERIC(12, 2) NOT NULL
);

INSERT INTO period_lab_orders
    (order_id, ordered_at, region, status, amount_k_vnd)
VALUES
    (1,  TIMESTAMPTZ '2025-05-05 09:00+07', 'North', 'PAID',       250),
    (2,  TIMESTAMPTZ '2025-05-20 09:00+07', 'South', 'PAID',       250),
    (3,  TIMESTAMPTZ '2025-06-10 09:00+07', 'North', 'PAID',       300),
    (4,  TIMESTAMPTZ '2025-06-25 09:00+07', 'South', 'PAID',       500),
    (5,  TIMESTAMPTZ '2025-07-05 09:00+07', 'North', 'PAID',       400),
    (6,  TIMESTAMPTZ '2025-07-24 09:00+07', 'South', 'PAID',       500),

    (7,  TIMESTAMPTZ '2026-01-05 09:00+07', 'North', 'PAID',       600),
    (8,  TIMESTAMPTZ '2026-01-25 09:00+07', 'South', 'PAID',       400),
    (9,  TIMESTAMPTZ '2026-02-06 09:00+07', 'North', 'PAID',       700),
    (10, TIMESTAMPTZ '2026-02-21 09:00+07', 'South', 'PAID',       500),
    (11, TIMESTAMPTZ '2026-03-06 09:00+07', 'North', 'PAID',       400),
    (12, TIMESTAMPTZ '2026-03-22 09:00+07', 'South', 'PAID',       500),

    -- Tháng 4 không có đơn PAID: chỉ có một đơn CANCELLED.
    (13, TIMESTAMPTZ '2026-04-15 09:00+07', 'North', 'CANCELLED', 600),

    (14, TIMESTAMPTZ '2026-05-05 09:00+07', 'North', 'PAID',      1000),
    (15, TIMESTAMPTZ '2026-05-18 09:00+07', 'South', 'PAID',       500),
    (16, TIMESTAMPTZ '2026-06-05 09:00+07', 'North', 'PAID',      1000),
    (17, TIMESTAMPTZ '2026-06-25 09:00+07', 'South', 'PAID',       600),
    (18, TIMESTAMPTZ '2026-07-05 09:00+07', 'North', 'PAID',       700),
    (19, TIMESTAMPTZ '2026-07-24 09:00+07', 'South', 'PAID',       550),

    -- Hai đơn không PAID: không tính vào chỉ số báo cáo.
    (20, TIMESTAMPTZ '2026-07-10 09:00+07', 'South', 'PENDING',   300),
    (21, TIMESTAMPTZ '2026-06-10 09:00+07', 'North', 'CANCELLED', 400);

SELECT order_id, ordered_at, region, status, amount_k_vnd
FROM period_lab_orders
ORDER BY order_id;
```

Các mốc thời gian mẫu ghi rõ `+07`. PostgreSQL lưu `TIMESTAMPTZ` như những thời điểm xác định và có thể hiển thị theo múi giờ phiên. Khi tổng hợp theo **ngày/tháng Việt Nam**, ta sẽ chuyển sang `Asia/Ho_Chi_Minh` trong biểu thức tạo khóa kỳ.

### 3.2. Bảng tổng hợp dự kiến

Các **đơn `PAID`** tạo ra tổng theo tháng:

| Kỳ | North | South | Tổng (nghìn VND) |
|---|---:|---:|---:|
| 2025-05 | 250 | 250 | 500 |
| 2025-06 | 300 | 500 | 800 |
| 2025-07 | 400 | 500 | 900 |
| 2026-01 | 600 | 400 | 1.000 |
| 2026-02 | 700 | 500 | 1.200 |
| 2026-03 | 400 | 500 | 900 |
| 2026-04 | — | — | **0** nếu kỳ đã hoàn tất và không có đơn `PAID` |
| 2026-05 | 1.000 | 500 | 1.500 |
| 2026-06 | 1.000 | 600 | 1.600 |
| 2026-07 | 700 | 550 | 1.250 |

Chú ý **tháng 4 không có dòng `PAID`**, nên truy vấn `GROUP BY` trực tiếp trên đơn `PAID` sẽ **không tự tạo một dòng tháng 4**. Đây là nguyên nhân gây lỗi khi dùng `LAG()` cho “tháng trước”.

Trong dữ liệu thực, **không có đơn** và **chưa nạp dữ liệu** là hai trạng thái khác nhau. Ví dụ tháng 4 của bài được **giả định đã hoàn tất, dữ liệu đầy đủ, nhưng không có đơn `PAID`**, nên ta chủ động biểu diễn nó bằng 0 khi tạo lịch kỳ.

## 4. Tạo khóa kỳ đúng: ngày đầu tháng tại múi giờ nghiệp vụ

Trong PostgreSQL, có thể lấy **đầu tháng** bằng `DATE_TRUNC('month', ...)`.

```sql
SELECT
    order_id,
    ordered_at,
    DATE_TRUNC(
        'month',
        ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )::date AS month_start
FROM period_lab_orders
WHERE status = 'PAID'
ORDER BY order_id;
```

Phân tích:

1. `ordered_at` là `TIMESTAMPTZ`, một thời điểm thật.
2. `AT TIME ZONE 'Asia/Ho_Chi_Minh'` cho biết **ngày giờ địa phương tại Việt Nam** của thời điểm đó, dưới dạng `TIMESTAMP` không kèm múi giờ.
3. `DATE_TRUNC('month', ...)` chuyển mọi ngày giờ thuộc cùng tháng về **đầu tháng**.
4. `::date` nhận `DATE` làm khóa kỳ dễ nhóm, nối và hiển thị.

Vì vậy, các đơn đặt ngày 5/6 và 25/6 đều có `month_start = DATE '2026-06-01'`.

### 4.1. Tại sao không chỉ lấy số tháng?

```sql
EXTRACT(MONTH FROM ordered_at)
```

chỉ cho số từ 1 đến 12. Nếu nhóm theo biểu thức này, tháng 7/2025 và tháng 7/2026 sẽ bị **gộp chung thành một nhóm**, làm sai báo cáo theo kỳ.

Khóa `month_start` chứa **cả năm và tháng**, nên `2025-07-01` và `2026-07-01` là hai khóa khác nhau. Một phương án khác là nhóm đồng thời theo `EXTRACT(YEAR ...)` và `EXTRACT(MONTH ...)`.

### 4.2. “Một tháng” khác 30 ngày

Nếu so tháng 3 với tháng 2, không thể trừ `INTERVAL '30 days'` để luôn ra đầu tháng trước. Tháng có 28, 29, 30 hoặc 31 ngày.

Khi khóa kỳ luôn là **ngày đầu tháng**, có thể dịch theo lịch:

```sql
SELECT
    DATE '2026-07-01' AS current_month,
    (DATE '2026-07-01' - INTERVAL '1 month')::date AS previous_month,
    (DATE '2026-07-01' - INTERVAL '1 year')::date AS same_month_last_year;
-- 2026-07-01, 2026-06-01, 2025-07-01.
```

Việc chuẩn hóa khóa về **đầu tháng** cũng tránh bẫy cộng/trừ tháng từ ngày 29, 30, 31 khi tháng đích ngắn hơn.

## 5. Bước thứ nhất: tổng hợp dữ liệu chi tiết theo kỳ

Trước khi tính chênh lệch, ta cần **một dòng mỗi kỳ**.

```sql
SELECT
    DATE_TRUNC(
        'month',
        ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )::date AS month_start,
    COUNT(*) AS paid_order_count,
    SUM(amount_k_vnd) AS paid_value_k_vnd
FROM period_lab_orders
WHERE status = 'PAID'
GROUP BY
    DATE_TRUNC(
        'month',
        ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )::date
ORDER BY month_start;
```

Truy vấn trả **những tháng thực sự có đơn `PAID`**. Trong dữ liệu mẫu sẽ có các tháng 5, 6, 7/2025 và 1, 2, 3, 5, 6, 7/2026, nhưng **không có tháng 4/2026**.

`COUNT(*)` đếm **số đơn `PAID`**, còn `SUM(amount_k_vnd)` là tổng giá trị của chúng. Đơn `CANCELLED` và `PENDING` đã được lọc bởi `WHERE status = 'PAID'`.

### 5.1. Vì sao phải tổng hợp trước khi `LAG`?

`LAG()` làm việc trên **các dòng đầu vào của cửa sổ**. Nếu gọi nó trực tiếp trên bảng đơn:

```sql
SELECT
    order_id,
    ordered_at,
    amount_k_vnd,
    LAG(amount_k_vnd) OVER (ORDER BY ordered_at) AS previous_order_amount
FROM period_lab_orders;
```

thì kết quả là **giá trị của đơn trước**, không phải **doanh số tháng trước**. Độ hạt đầu vào là **một đơn hàng**, nên “dòng trước” có nghĩa “đơn trước”.

Muốn so theo tháng, trước tiên phải `GROUP BY` để nhận **một dòng tháng**, rồi mới dùng `LAG()` trên kết quả theo tháng.

## 6. `LAG()`: lấy giá trị của dòng đứng trước

Hàm cửa sổ `LAG()` cho phép đọc giá trị của một dòng **trước dòng hiện tại** theo thứ tự trong `OVER`.

Cú pháp thường dùng:

```sql
LAG(value_expression, offset, default_value)
OVER (
    PARTITION BY group_key
    ORDER BY period_key
)
```

| Thành phần | Ý nghĩa |
|---|---|
| `value_expression` | Giá trị muốn lấy từ dòng trước, ví dụ `paid_value_k_vnd` |
| `offset` | Số dòng lùi lại; mặc định **1** |
| `default_value` | Giá trị thay khi không có dòng ở vị trí lùi; mặc định `NULL` |
| `PARTITION BY` | Phạm vi độc lập, ví dụ từng khu vực |
| `ORDER BY` | Thứ tự xác định dòng nào là “trước”; thường là ngày đầu kỳ |

Ví dụ tối giản:

```sql
WITH monthly AS (
    SELECT
        DATE_TRUNC(
            'month',
            ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        )::date AS month_start,
        SUM(amount_k_vnd) AS paid_value_k_vnd
    FROM period_lab_orders
    WHERE status = 'PAID'
      AND ordered_at >= (
          TIMESTAMP '2026-01-01 00:00:00'
          AT TIME ZONE 'Asia/Ho_Chi_Minh'
      )
      AND ordered_at < (
          TIMESTAMP '2026-08-01 00:00:00'
          AT TIME ZONE 'Asia/Ho_Chi_Minh'
      )
    GROUP BY 1
)
SELECT
    month_start,
    paid_value_k_vnd,
    LAG(paid_value_k_vnd) OVER (
        ORDER BY month_start
    ) AS previous_visible_month_value
FROM monthly
ORDER BY month_start;
```

Trong kết quả **chưa điền tháng trống**, tháng 3/2026 đứng ngay trước **tháng 5/2026**. Vì vậy:

```text
2026-01 → 1000 → LAG NULL
2026-02 → 1200 → LAG 1000
2026-03 →  900 → LAG 1200
2026-05 → 1500 → LAG  900  ← không phải tháng 4!
2026-06 → 1600 → LAG 1500
2026-07 → 1250 → LAG 1600
```

**`LAG()` biết “dòng trước”, không tự biết “tháng trước theo lịch”.** Nếu dữ liệu bỏ qua tháng 4, `LAG` lấy tháng 3. Một truy vấn có vẻ rất hợp lý có thể báo sai rằng tháng 5 tăng `1500 - 900 = 600` so với “tháng trước”; thật ra nó đang so **tháng 5 với tháng 3**.

Đây là bẫy quan trọng nhất của mẫu truy vấn so sánh kỳ.

## 7. Tạo đủ lịch kỳ (*calendar spine*) trước khi dùng `LAG`

Khi yêu cầu thật sự là **so với tháng liền trước theo lịch**, một giải pháp đáng tin cậy là tạo **đủ các tháng trong phạm vi báo cáo**, rồi nối tổng dữ liệu vào lịch đó.

PostgreSQL có hàm `generate_series()`:

```sql
SELECT g.month_ts::date AS month_start
FROM generate_series(
    TIMESTAMP '2026-01-01 00:00:00',
    TIMESTAMP '2026-07-01 00:00:00',
    INTERVAL '1 month'
) AS g(month_ts)
ORDER BY month_start;
```

Kết quả có **7 dòng**: từ ngày đầu tháng 1 tới ngày đầu tháng 7, **bao gồm cả hai đầu** của `generate_series`.

### 7.1. Nối lịch với tổng theo tháng

```sql
WITH months AS (
    SELECT g.month_ts::date AS month_start
    FROM generate_series(
        TIMESTAMP '2026-01-01 00:00:00',
        TIMESTAMP '2026-07-01 00:00:00',
        INTERVAL '1 month'
    ) AS g(month_ts)
),
paid_monthly AS (
    SELECT
        DATE_TRUNC(
            'month',
            ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        )::date AS month_start,
        SUM(amount_k_vnd) AS paid_value_k_vnd,
        COUNT(*) AS paid_orders
    FROM period_lab_orders
    WHERE status = 'PAID'
      AND ordered_at >= (
          TIMESTAMP '2026-01-01'
          AT TIME ZONE 'Asia/Ho_Chi_Minh'
      )
      AND ordered_at < (
          TIMESTAMP '2026-08-01'
          AT TIME ZONE 'Asia/Ho_Chi_Minh'
      )
    GROUP BY 1
)
SELECT
    m.month_start,
    COALESCE(p.paid_value_k_vnd, 0::numeric) AS paid_value_k_vnd,
    COALESCE(p.paid_orders, 0) AS paid_order_count,
    (p.month_start IS NULL) AS no_paid_rows
FROM months AS m
LEFT JOIN paid_monthly AS p
    ON p.month_start = m.month_start
ORDER BY m.month_start;
```

`months` là **bảng lịch tháng**. `paid_monthly` là **số liệu thực tế chỉ ở những tháng có đơn**. `LEFT JOIN` giữ **mọi tháng trong lịch**, nên tháng 4 vẫn có một dòng.

Ở tháng 4:

- `p.month_start IS NULL` là `TRUE`, thể hiện **không có nhóm `PAID` khớp**.
- `COALESCE(p.paid_value_k_vnd, 0)` biểu diễn giá trị bằng **0 theo quy tắc bài thực hành**.
- `paid_order_count` bằng **0**.

**Không dùng `COALESCE` một cách mù quáng.** Nếu tháng 4 chưa được nạp dữ liệu, thay `NULL` thành 0 sẽ khiến báo cáo kết luận “doanh số bằng 0” trong khi thực chất là “chưa biết”. Trong hệ thống thực, nên có **trạng thái hoàn tất dữ liệu của kỳ** hoặc một bảng lịch kỳ có `is_closed` / `is_complete` để quyết định có được coi trống là 0 không.

### 7.2. Vì sao cần khoảng thời gian nửa mở?

Trong `paid_monthly`:

```sql
ordered_at >= start_of_january
AND ordered_at < start_of_august
```

Phạm vi `[đầu tháng 1, đầu tháng 8)` gồm **toàn bộ các thời điểm trong tháng 1–7**, không phải đoán “giây cuối” của tháng 7. Cách này đúng với các cột có phần giây và phù hợp với chỉ mục trên `ordered_at`.

Hai biên đã được diễn giải theo **múi giờ Việt Nam**, thay vì phụ thuộc múi giờ kết nối.

## 8. Mẫu hoàn chỉnh: MoM với `LAG()` và tỷ lệ thay đổi

Ta kết hợp ba bước:

```text
Đơn hàng chi tiết
      ↓ GROUP BY tháng
Tổng giá trị ở những tháng có đơn PAID
      ↓ LEFT JOIN lịch đầy đủ
Một dòng cho mọi tháng, tháng trống được ghi 0 khi hợp lệ
      ↓ LAG(1) OVER (ORDER BY month_start)
Giá trị của tháng trước
      ↓ current - previous, % thay đổi
Báo cáo MoM
```

### 8.1. Câu SQL chạy được

```sql
WITH months AS (
    SELECT g.month_ts::date AS month_start
    FROM generate_series(
        TIMESTAMP '2026-01-01',
        TIMESTAMP '2026-07-01',
        INTERVAL '1 month'
    ) AS g(month_ts)
),
monthly_paid AS (
    SELECT
        DATE_TRUNC(
            'month',
            ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        )::date AS month_start,
        SUM(amount_k_vnd) AS paid_value_k_vnd
    FROM period_lab_orders
    WHERE status = 'PAID'
      AND ordered_at >= (
          TIMESTAMP '2026-01-01'
          AT TIME ZONE 'Asia/Ho_Chi_Minh'
      )
      AND ordered_at < (
          TIMESTAMP '2026-08-01'
          AT TIME ZONE 'Asia/Ho_Chi_Minh'
      )
    GROUP BY 1
),
filled AS (
    SELECT
        m.month_start,
        COALESCE(p.paid_value_k_vnd, 0::numeric)
            AS current_paid_value,
        (p.month_start IS NULL) AS no_paid_rows
    FROM months AS m
    LEFT JOIN monthly_paid AS p
        ON p.month_start = m.month_start
),
with_previous AS (
    SELECT
        month_start,
        current_paid_value,
        no_paid_rows,
        LAG(current_paid_value) OVER (
            ORDER BY month_start
        ) AS previous_paid_value
    FROM filled
)
SELECT
    month_start,
    current_paid_value,
    previous_paid_value,
    current_paid_value - previous_paid_value AS change_k_vnd,
    ROUND(
        100.0 * (current_paid_value - previous_paid_value)
        / NULLIF(previous_paid_value, 0),
        2
    ) AS change_pct,
    no_paid_rows
FROM with_previous
ORDER BY month_start;
```

### 8.2. Kết quả dự kiến

| Tháng | Hiện tại | Tháng trước | Chênh lệch | Thay đổi (%) | Không có `PAID`? |
|---|---:|---:|---:|---:|---|
| 2026-01 | 1.000 | `NULL` | `NULL` | `NULL` | Không |
| 2026-02 | 1.200 | 1.000 | +200 | +20,00 | Không |
| 2026-03 | 900 | 1.200 | -300 | -25,00 | Không |
| 2026-04 | 0 | 900 | -900 | -100,00 | Có |
| 2026-05 | 1.500 | 0 | +1.500 | `NULL` | Không |
| 2026-06 | 1.600 | 1.500 | +100 | +6,67 | Không |
| 2026-07 | 1.250 | 1.600 | -350 | -21,88 | Không |

Mọi giá trị tiền đều tính bằng **nghìn VND**.

### 8.3. Hai trường hợp `NULL` trong báo cáo có ý nghĩa khác nhau

**Tháng 1:** không có **tháng 12/2025** bên trong khoảng lịch 1–7/2026 đang dùng để `LAG`. Bởi vậy `previous_paid_value = NULL`. Không thể kết luận tháng 1 tăng từ 0 nếu chưa có dữ liệu tháng 12 hoặc chưa quy định rằng tháng đó là 0.

**Tháng 5:** kỳ trước tháng 4 đã được mô hình hóa bằng **0**, nên chênh lệch tuyệt đối là `+1500`, nhưng **phần trăm thay đổi không xác định** do mẫu số bằng 0. Không gọi đó là “tăng 100%”.

Hai lý do cùng đưa `change_pct` về `NULL`, nhưng chúng cần **nhãn trạng thái khác nhau** trong dashboard:

```text
Không có kỳ đối chiếu → Không đủ dữ liệu để tính MoM.
Kỳ đối chiếu = 0     → Có mức tăng tuyệt đối; tỷ lệ % không xác định.
```

### 8.4. Tại sao không ghi `LAG(current_paid_value, 1, 0)`?

PostgreSQL cho phép:

```sql
LAG(current_paid_value, 1, 0) OVER (ORDER BY month_start)
```

Tham số `0` là **giá trị mặc định khi không có dòng trước**. Nhưng khi tháng 1 là dòng đầu tiên trong báo cáo, 0 sẽ khiến nó trông như đang được so với tháng 12 có giá trị 0, dù chưa có thông tin đó.

**Chỉ dùng mặc định 0 khi nghiệp vụ thực sự xác nhận một kỳ trước không tồn tại phải coi là 0.** Trong các báo cáo biến động, giữ `NULL` cho kỳ thiếu đối chiếu thường an toàn hơn.

## 9. So sánh bằng tự `JOIN` theo khóa kỳ

`LAG` rất tiện khi chuỗi tháng **liền mạch**. Một cách khác là nối bảng tổng hợp với **chính nó** thông qua khóa kỳ trước, không phụ thuộc việc tháng có xuất hiện trong kết quả hay không.

```sql
WITH monthly AS (
    SELECT
        DATE_TRUNC(
            'month',
            ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        )::date AS month_start,
        SUM(amount_k_vnd) AS paid_value_k_vnd
    FROM period_lab_orders
    WHERE status = 'PAID'
    GROUP BY 1
)
SELECT
    cur.month_start,
    cur.paid_value_k_vnd AS current_value,
    prev.paid_value_k_vnd AS previous_value,
    cur.paid_value_k_vnd - prev.paid_value_k_vnd AS change_value
FROM monthly AS cur
LEFT JOIN monthly AS prev
    ON prev.month_start = (
        cur.month_start - INTERVAL '1 month'
    )::date
WHERE cur.month_start >= DATE '2026-01-01'
  AND cur.month_start < DATE '2026-08-01'
ORDER BY cur.month_start;
```

Với tháng 5, biểu thức:

```sql
prev.month_start = DATE '2026-04-01'
```

không tìm thấy dòng ở `monthly` vì tháng 4 không có đơn `PAID`, nên `previous_value = NULL`. Truy vấn **không lỡ lấy tháng 3**, khác với `LAG` trên chuỗi thiếu tháng.

### 9.1. `JOIN` theo tháng không tự biến tháng trống thành 0

Cách tự `JOIN` xác định đúng **kỳ theo lịch**, nhưng nếu tháng trước không có dòng, giá trị đối chiếu vẫn `NULL`.

Nếu bài toán có quy ước tháng 4 đã chốt và không có đơn thì phải tính 0, hãy:

- Tạo lịch đầy đủ như mục 7 rồi nối dữ liệu vào, hoặc
- Dùng bảng dimension/snapshot tháng có trạng thái đầy đủ dữ liệu và giá trị 0 đã được xác nhận.

**Không nên coi `COALESCE(prev.paid_value_k_vnd, 0)` là luôn đúng**, vì tháng thiếu do chưa nạp dữ liệu không phải tháng doanh số bằng 0.

### 9.2. Chọn `LAG` hay `JOIN` theo khóa kỳ?

| Tiêu chí | `LAG()` | `JOIN` theo tháng trước |
|---|---|---|
| Cách diễn đạt | Lấy dòng trước trong thứ tự | Nối đúng khóa tháng liền trước |
| Nếu thiếu một tháng trong chuỗi | Có thể lấy nhầm tháng xa hơn | Không khớp, thường trả `NULL` |
| Nếu đã có lịch đầy đủ | Rất thuận tiện | Cũng chính xác |
| Nếu cần đối chiếu cách 12 tháng | `LAG(12)` trên lịch đủ tháng | `JOIN` với `month_start - INTERVAL '1 year'` |
| Khi có nhiều chiều phân tích | Dùng `PARTITION BY` | Nối theo cả khóa kỳ và chiều |
| Khi cần nhiều loại kỳ đối chiếu | Có thể dùng nhiều `LAG` | Có thể nối nhiều bản tổng hợp |

Hai phương án đều hợp lệ khi được xây dựng đúng. Điều quan trọng là **định nghĩa kỳ trước theo lịch**, không chỉ chọn hàm có cú pháp ngắn.

## 10. So sánh theo khu vực: `PARTITION BY`

Yêu cầu: “Mỗi khu vực có biến động MoM riêng.”

Không thể dùng:

```sql
LAG(paid_value_k_vnd) OVER (ORDER BY month_start)
```

trên dữ liệu **mỗi tháng có nhiều khu vực**, vì dòng trước có thể thuộc **khu vực khác** hoặc cùng tháng. Cần:

```sql
LAG(paid_value_k_vnd) OVER (
    PARTITION BY region
    ORDER BY month_start
)
```

`PARTITION BY region` làm `LAG` hoạt động **độc lập cho North và South**.

### 10.1. Tạo đầy đủ tổ hợp tháng × khu vực

Nếu một khu vực không có đơn trong một tháng, nó cũng cần một dòng **0 được xác nhận** khi so với tháng liền trước. Có thể tạo lưới thời gian và khu vực:

```sql
WITH
months AS (
    SELECT g.month_ts::date AS month_start
    FROM generate_series(
        TIMESTAMP '2026-03-01',
        TIMESTAMP '2026-05-01',
        INTERVAL '1 month'
    ) AS g(month_ts)
),
regions AS (
    SELECT DISTINCT region
    FROM period_lab_orders
),
monthly AS (
    SELECT
        region,
        DATE_TRUNC(
            'month',
            ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        )::date AS month_start,
        SUM(amount_k_vnd) AS paid_value_k_vnd
    FROM period_lab_orders
    WHERE status = 'PAID'
    GROUP BY region, 2
),
complete_grid AS (
    SELECT
        r.region,
        m.month_start,
        COALESCE(p.paid_value_k_vnd, 0::numeric) AS current_value
    FROM regions AS r
    CROSS JOIN months AS m
    LEFT JOIN monthly AS p
        ON p.region = r.region
       AND p.month_start = m.month_start
),
with_previous AS (
    SELECT
        region,
        month_start,
        current_value,
        LAG(current_value) OVER (
            PARTITION BY region
            ORDER BY month_start
        ) AS previous_value
    FROM complete_grid
)
SELECT
    region,
    month_start,
    current_value,
    previous_value,
    current_value - previous_value AS change_value,
    ROUND(
        100.0 * (current_value - previous_value)
        / NULLIF(previous_value, 0),
        2
    ) AS change_pct
FROM with_previous
ORDER BY region, month_start;
```

Kết quả về giá trị:

| Khu vực | Tháng | Hiện tại | Trước | Chênh lệch |
|---|---|---:|---:|---:|
| North | 2026-03 | 400 | `NULL` | `NULL` |
| North | 2026-04 | 0 | 400 | -400 |
| North | 2026-05 | 1.000 | 0 | +1.000 |
| South | 2026-03 | 500 | `NULL` | `NULL` |
| South | 2026-04 | 0 | 500 | -500 |
| South | 2026-05 | 500 | 0 | +500 |

Ở ví dụ này `regions` được lấy từ các dòng hiện có. Nếu một khu vực hợp lệ **chưa từng có đơn nào**, nó sẽ **không xuất hiện trong `SELECT DISTINCT region`**. Muốn báo cáo đủ danh mục, hãy dùng bảng `regions` chính thức hoặc danh sách khu vực do nghiệp vụ quản lý.

### 10.2. Khóa phân vùng có thể gồm nhiều cột

Nếu mỗi dòng kỳ là một tổ hợp `(region, channel, month_start)`:

```sql
LAG(paid_value_k_vnd) OVER (
    PARTITION BY region, channel
    ORDER BY month_start
)
```

Khi tạo lịch đầy đủ, phải tạo **đủ các tổ hợp chiều cần báo cáo** và tháng phù hợp, không chỉ một lịch chung rồi bỏ qua khu vực/kênh.

Tuy nhiên, `CROSS JOIN` nhiều danh mục lớn có thể tạo lưới rất nhiều dòng. Cần xác định chỉ những tổ hợp được phép hoặc thực sự cần theo nghiệp vụ, tránh tạo tổ hợp vô nghĩa.

## 11. Lọc trước hay sau `LAG`?

Vì `LAG` đọc những dòng hiện có **ở đầu vào của cửa sổ**, vị trí đặt điều kiện lọc ảnh hưởng kỳ đối chiếu.

Giả sử đã có bảng `monthly_complete` chứa đầy đủ 7 tháng 2026 và giá trị của chúng.

### 11.1. Lọc từ tháng 2 trước khi tính `LAG`

```sql
-- Minh họa nếu monthly_complete đã được tạo:
SELECT
    month_start,
    paid_value_k_vnd,
    LAG(paid_value_k_vnd) OVER (
        ORDER BY month_start
    ) AS previous_value
FROM monthly_complete
WHERE month_start >= DATE '2026-02-01';
```

Tháng 1 bị loại **trước khi `LAG` tính**, nên tháng 2 không còn dòng tháng 1 để đối chiếu: `previous_value = NULL`.

### 11.2. Tính `LAG` trước rồi lọc kết quả

```sql
WITH compared AS (
    SELECT
        month_start,
        paid_value_k_vnd,
        LAG(paid_value_k_vnd) OVER (
            ORDER BY month_start
        ) AS previous_value
    FROM monthly_complete
)
SELECT *
FROM compared
WHERE month_start >= DATE '2026-02-01'
ORDER BY month_start;
```

Tháng 2 giữ `previous_value` của tháng 1, bởi tháng 1 vẫn nằm trong tập được dùng để tính `LAG`.

**Cách thực hành:** nếu người dùng muốn xem báo cáo từ tháng 2 nhưng vẫn cần so tháng 2 với tháng 1, phải đưa **đủ kỳ đối chiếu** vào giai đoạn tính cửa sổ, rồi mới lọc **phạm vi hiển thị** ở truy vấn ngoài.

Lưu ý: `monthly_complete` chỉ là tên quan hệ minh họa trong mục này; muốn chạy độc lập, thay nó bằng CTE `filled` từ mẫu truy vấn mục 8 hoặc một bảng tổng hợp tháng thật.

## 12. So sánh cùng kỳ năm trước — YoY

MoM dùng tháng liền trước. YoY của một tháng dùng **cùng tháng ở năm trước**.

Ví dụ:

```text
Tháng 7/2025:  900 nghìn VND
Tháng 7/2026: 1250 nghìn VND

Chênh lệch YoY = 1250 - 900 = +350 nghìn VND
Tỷ lệ YoY       = 350 / 900 × 100 = +38,89%
```

### 12.1. Dùng `JOIN` theo khóa cùng tháng năm trước

```sql
WITH monthly AS (
    SELECT
        DATE_TRUNC(
            'month',
            ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        )::date AS month_start,
        SUM(amount_k_vnd) AS paid_value_k_vnd
    FROM period_lab_orders
    WHERE status = 'PAID'
    GROUP BY 1
)
SELECT
    cur.month_start AS current_month,
    cur.paid_value_k_vnd AS current_value,
    prev.paid_value_k_vnd AS same_month_last_year,
    cur.paid_value_k_vnd - prev.paid_value_k_vnd AS yoy_change,
    ROUND(
        100.0 * (cur.paid_value_k_vnd - prev.paid_value_k_vnd)
        / NULLIF(prev.paid_value_k_vnd, 0),
        2
    ) AS yoy_pct
FROM monthly AS cur
LEFT JOIN monthly AS prev
    ON prev.month_start = (
        cur.month_start - INTERVAL '1 year'
    )::date
WHERE cur.month_start = DATE '2026-07-01';
```

Kết quả là `2026-07-01, 1250, 900, +350, +38.89`.

### 12.2. Vì sao `LAG(12)` không phải lúc nào cũng là YoY?

Nếu có **một dòng cho mọi tháng**, được sắp đúng thời gian, thì:

```sql
LAG(paid_value_k_vnd, 12) OVER (
    ORDER BY month_start
)
```

lấy giá trị **12 dòng tháng trước**, tương ứng cùng tháng năm trước. Nhưng nếu thiếu bất kỳ tháng nào, 12 **dòng** có thể không bằng 12 **tháng lịch**.

Với chuỗi dữ liệu mẫu thiếu nhiều tháng trong nửa cuối năm 2025 và tháng 4/2026, `LAG(12)` trên các nhóm có dữ liệu **không thể thay thế nối theo khóa `month_start - INTERVAL '1 year'`**.

Để dùng `LAG(12)`, cần có lịch tháng **liền mạch**, đồng thời xử lý đúng các kỳ thiếu dữ liệu/không đủ điều kiện báo cáo.

### 12.3. YoY theo khu vực

Muốn so July North năm 2026 với July North năm 2025, điều kiện `JOIN` phải gồm cả **khu vực**:

```sql
ON prev.region = cur.region
AND prev.month_start = (
    cur.month_start - INTERVAL '1 year'
)::date
```

Không có điều kiện `prev.region = cur.region`, một dòng hiện tại có thể nối với **nhiều khu vực ở năm trước**, gây nhân dòng và đối chiếu sai.

Với dữ liệu mẫu tháng 7:

| Khu vực | 7/2025 | 7/2026 | Chênh lệch | YoY (%) |
|---|---:|---:|---:|---:|
| North | 400 | 700 | +300 | +75,00 |
| South | 500 | 550 | +50 | +10,00 |
| **Tổng** | **900** | **1.250** | **+350** | **+38,89** |

Phần trăm tổng **không** bằng trung bình đơn giản của 75% và 10%. Nó phải được tính từ **tổng chênh lệch chia tổng kỳ gốc**: `350 / 900 ≈ 38,89%`.

## 13. Tháng đang chạy: đừng so một phần tháng với cả tháng trước

Giả sử báo cáo được chốt theo **các ngày hoàn tất đến hết 15/07/2026**. Mốc loại trừ là:

```text
2026-07-16 00:00:00 theo giờ Việt Nam.
```

Kỳ hiện tại là:

```text
[2026-07-01 00:00, 2026-07-16 00:00)
```

tức 15 ngày từ 1/7 đến hết 15/7.

Nếu đem **15 ngày đầu tháng 7** so với **toàn bộ 30 ngày tháng 6**, kết luận “tháng 7 giảm mạnh” sẽ không công bằng: tháng 7 chưa có đủ số ngày.

### 13.1. MTD so với kỳ tương ứng tháng trước

Ta so:

```text
Kỳ hiện tại: [2026-07-01 00:00, 2026-07-16 00:00)
Kỳ trước:   [2026-06-01 00:00, 2026-06-16 00:00)
```

Hai phạm vi đều có **15 ngày lịch đã hoàn tất**.

Trong dữ liệu mẫu:

- Tháng 7 từ 1–15/7: đơn North ngày 5/7, giá trị **700**.
- Tháng 6 từ 1–15/6: đơn North ngày 5/6, giá trị **1000**.
- Các đơn ngày 24/7 và 25/6 nằm ngoài phạm vi MTD được chọn.

Kết quả: `700 - 1000 = -300`, tỷ lệ **-30,00%**.

### 13.2. Câu SQL MTD với mốc cố định

```sql
WITH boundaries AS (
    SELECT
        (
            TIMESTAMP '2026-07-01 00:00:00'
            AT TIME ZONE 'Asia/Ho_Chi_Minh'
        ) AS current_start,
        (
            TIMESTAMP '2026-07-16 00:00:00'
            AT TIME ZONE 'Asia/Ho_Chi_Minh'
        ) AS current_end,
        (
            TIMESTAMP '2026-06-01 00:00:00'
            AT TIME ZONE 'Asia/Ho_Chi_Minh'
        ) AS previous_start,
        (
            TIMESTAMP '2026-06-16 00:00:00'
            AT TIME ZONE 'Asia/Ho_Chi_Minh'
        ) AS previous_end
),
totals AS (
    SELECT
        COALESCE(
            SUM(o.amount_k_vnd) FILTER (
                WHERE o.ordered_at >= b.current_start
                  AND o.ordered_at < b.current_end
            ),
            0::numeric
        ) AS current_mtd,
        COALESCE(
            SUM(o.amount_k_vnd) FILTER (
                WHERE o.ordered_at >= b.previous_start
                  AND o.ordered_at < b.previous_end
            ),
            0::numeric
        ) AS previous_mtd
    FROM boundaries AS b
    LEFT JOIN period_lab_orders AS o
        ON o.status = 'PAID'
       AND (
            (
                o.ordered_at >= b.current_start
                AND o.ordered_at < b.current_end
            )
            OR (
                o.ordered_at >= b.previous_start
                AND o.ordered_at < b.previous_end
            )
       )
)
SELECT
    current_mtd,
    previous_mtd,
    current_mtd - previous_mtd AS change_k_vnd,
    ROUND(
        100.0 * (current_mtd - previous_mtd)
        / NULLIF(previous_mtd, 0),
        2
    ) AS change_pct
FROM totals;
-- 700 | 1000 | -300 | -30.00
```

`FILTER (WHERE ...)` bên trong `SUM` là cú pháp PostgreSQL để tính **nhiều đại lượng có điều kiện trong cùng truy vấn**. Ở một hệ không hỗ trợ `FILTER`, có thể dùng `SUM(CASE WHEN condition THEN amount ELSE 0 END)` với quy tắc `NULL` phù hợp.

### 13.3. Nếu cần đúng một ngày giờ “tính đến hiện tại”

Trong hệ thống thực, mốc cắt có thể được truyền bằng tham số `:as_of`. Nhưng “tính đến thời điểm này” cần xác định:

- Dữ liệu có độ trễ đồng bộ không? Có phải chốt đến hết **ngày hôm qua** thay vì đến giây hiện tại không?
- So với tháng trước đến **cùng ngày trong tháng**, **cùng số ngày đã hoàn tất**, hay **cùng số giây đã trôi qua**?
- Nếu tháng trước ngắn hơn, ngày 30/31 không tồn tại thì quy tắc cắt là gì?
- Khi múi giờ có giờ mùa hè, một ngày địa phương có thể không bằng chính xác 24 giờ.

Ví dụ sử dụng mốc cố định giúp kết quả **lặp lại được** và tránh phụ thuộc giờ chạy của máy. Trong sản phẩm thật, hãy lưu/ghi rõ `as_of` hoặc `data_watermark`.

## 14. So sánh “toàn tháng” và “tháng đến ngày” trả hai câu khác nhau

Với dữ liệu mẫu:

| Cách so | Kỳ hiện tại | Kỳ trước | Chênh lệch | % |
|---|---:|---:|---:|---:|
| **Toàn tháng 7** vs **toàn tháng 6** | 1.250 | 1.600 | -350 | -21,88 |
| **1–15/7** vs **1–15/6** | 700 | 1.000 | -300 | -30,00 |

Cả hai cách đều có thể hữu ích, nhưng **không được dùng lẫn**.

Nếu bảng báo cáo được xem vào ngày 16/7 mà ngày 24/7 chưa thực sự xảy ra, “tổng tháng 7 = 1.250” chỉ có thể xuất hiện từ dữ liệu **giả định đã hoàn thiện** hoặc một bản chụp dữ liệu sau này. Không được coi nó là số MTD đã biết tại ngày 16/7.

Trong bài thực hành, tất cả dữ liệu được chèn sẵn để minh họa cả **toàn tháng** và **đoạn tháng**. Khi dùng báo cáo vận hành, cần tách rõ **thời điểm giả lập để so sánh** và **thời điểm dữ liệu hiện có**.

### 14.1. Kỳ hoàn tất (*closed period*) so với kỳ chưa hoàn tất

Một dashboard đáng tin nên ghi hoặc suy ra được:

```text
period_start
period_end_exclusive
is_complete
as_of_timestamp
metric_value
comparison_period_start
comparison_metric_value
```

Nếu kỳ đang mở, ta có thể hiển thị **MTD/QTD/YTD** hoặc đánh dấu **provisional**. Không nên tự khẳng định “tháng này giảm so tháng trước” khi hai kỳ chưa cùng mức hoàn tất.

## 15. So sánh theo ngày, tuần và quý

Mẫu tổng quát không thay đổi: xác định **khóa kỳ**, tổng hợp chỉ số, tạo đủ lịch nếu cần, rồi lấy kỳ trước.

### 15.1. So theo ngày — DoD

```sql
SELECT
    (ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS day_start,
    COUNT(*) AS paid_orders,
    SUM(amount_k_vnd) AS paid_value_k_vnd
FROM period_lab_orders
WHERE status = 'PAID'
GROUP BY 1
ORDER BY day_start;
```

Để so **hôm nay với hôm qua** chính xác, tạo đủ từng ngày từ một **lịch ngày** hoặc `generate_series(..., INTERVAL '1 day')` rồi dùng `LAG` trên lịch đã điền. Nếu chỉ có các ngày phát sinh đơn, “dòng ngày trước” có thể là **ngày có đơn gần nhất**, không phải hôm qua.

### 15.2. So theo tuần — WoW

PostgreSQL:

```sql
SELECT
    DATE_TRUNC(
        'week',
        ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )::date AS week_start,
    SUM(amount_k_vnd) AS paid_value_k_vnd
FROM period_lab_orders
WHERE status = 'PAID'
GROUP BY 1
ORDER BY week_start;
```

Trong PostgreSQL, `DATE_TRUNC('week', ...)` dùng đầu tuần **thứ Hai**. Không phải doanh nghiệp nào cũng chọn thứ Hai là đầu tuần; một số dùng Chủ nhật hoặc **tuần tài chính** riêng.

**Lỗi dễ gặp:** nhóm theo số tuần (`EXTRACT(WEEK ...)`) mà không kết hợp **năm tuần** phù hợp có thể trộn các năm, đặc biệt quanh ranh giới năm. Khóa `week_start` là một ngày cụ thể và thường dễ xử lý hơn.

### 15.3. So theo quý — QoQ

```sql
SELECT
    DATE_TRUNC(
        'quarter',
        ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )::date AS quarter_start,
    SUM(amount_k_vnd) AS paid_value_k_vnd
FROM period_lab_orders
WHERE status = 'PAID'
  AND ordered_at >= (
      TIMESTAMP '2026-01-01'
      AT TIME ZONE 'Asia/Ho_Chi_Minh'
  )
GROUP BY 1
ORDER BY quarter_start;
```

Trong dữ liệu mẫu:

- **Q1/2026**: tháng 1 + 2 + 3 = `1000 + 1200 + 900 = 3100`.
- **Q2/2026**: tháng 4 + 5 + 6 = `0 + 1500 + 1600 = 3100`.
- **Q3/2026**: mới có tháng 7 trong dữ liệu ví dụ, `1250`; **không đủ quý** để so toàn quý.

Q2 so với Q1 có chênh lệch `0` và tỷ lệ `0%` theo số liệu mẫu. Nhưng việc so Q3 đang dở với Q2 đủ quý sẽ gây hiểu nhầm nếu không ghi rõ mốc chốt.

### 15.4. Kỳ trượt không phải kỳ lịch

“7 ngày gần nhất” không phải lúc nào cũng là “tuần này”, bởi khoảng 7 ngày có thể bắt đầu giữa tuần. Khi đó, có thể so hai **khoảng nửa mở liền kề**:

```text
Hiện tại: [as_of - INTERVAL '7 days', as_of)
Trước đó: [as_of - INTERVAL '14 days', as_of - INTERVAL '7 days')
```

Nếu báo cáo nói “tuần này vs tuần trước”, nên sử dụng **ranh giới tuần lịch** đã thỏa thuận, không thay bằng hai khoảng 7×24 giờ mà không kiểm tra yêu cầu.

## 16. Những tỷ lệ và đại lượng không cộng được qua kỳ

Không phải mọi chỉ số đều có thể tính theo cách **`SUM` từng ngày rồi cộng thành tháng**.

### 16.1. Đếm số khách duy nhất

Giả sử một khách đặt hàng vào cả ngày 1 và ngày 2:

```text
Ngày 1: khách A, B → 2 khách duy nhất
Ngày 2: khách A, C → 2 khách duy nhất
Toàn 2 ngày: A, B, C → 3 khách duy nhất, không phải 4
```

Muốn so **số khách duy nhất mỗi tháng**, phải tính từ các đơn/dòng sự kiện của **toàn tháng**:

```sql
-- Giả định bảng thực tế có customer_id.
SELECT
    DATE_TRUNC(
        'month',
        ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )::date AS month_start,
    COUNT(DISTINCT customer_id) AS unique_customers
FROM orders_with_customer
WHERE status = 'PAID'
GROUP BY 1;
```

Không lấy tổng các số `COUNT(DISTINCT customer_id)` theo ngày rồi xem là số khách duy nhất của tháng. Bảng `orders_with_customer` là **schema minh họa** chưa tạo trong script bài học.

### 16.2. Tỷ lệ chuyển đổi cần tính từ tử số và mẫu số

Giả sử kỳ hiện tại:

```text
120 đơn / 2000 lượt truy cập = 6%
```

Kỳ trước:

```text
100 đơn / 2000 lượt truy cập = 5%
```

Chênh lệch là **+1 điểm phần trăm**, thay đổi tương đối là **+20%**.

Nếu có nhiều ngày, không nên tính **trung bình đơn giản của tỷ lệ chuyển đổi ngày** khi lượng truy cập các ngày khác nhau:

```text
Tỷ lệ kỳ = SUM(số chuyển đổi) / SUM(số lượt đủ điều kiện)
```

Rồi mới so hai tỷ lệ kỳ. Đây là **tỷ lệ có trọng số theo mẫu số**, không phải `AVG(daily_conversion_rate)` một cách mặc định.

### 16.3. Số dư là chỉ số thời điểm, không phải dòng chảy

Doanh số/đơn hàng là **chỉ số dòng chảy** (*flow*), thường được tổng hợp bằng `SUM` qua kỳ. Nhưng **số dư tài khoản, lượng tồn kho cuối kỳ** là **chỉ số trạng thái tại thời điểm** (*stock/snapshot*).

Không dùng:

```text
Số dư cuối tháng = SUM(số dư từng ngày)
```

vì sẽ cộng nhiều lần cùng một trạng thái. Cần xác định **snapshot tại thời điểm kết thúc kỳ**, hoặc bản ghi hợp lệ cuối cùng trước mốc chốt, rồi so snapshot của hai kỳ:

```sql
-- Ví dụ schema giả định account_snapshots(account_id, snapshot_at,
--                                           snapshot_id, balance).
WITH chosen AS (
    SELECT
        account_id,
        DATE_TRUNC('month', snapshot_at)::date AS month_start,
        balance,
        ROW_NUMBER() OVER (
            PARTITION BY account_id, DATE_TRUNC('month', snapshot_at)::date
            ORDER BY snapshot_at DESC, snapshot_id DESC
        ) AS rn
    FROM account_snapshots
)
SELECT
    account_id,
    month_start,
    balance AS end_of_month_balance,
    LAG(balance) OVER (
        PARTITION BY account_id
        ORDER BY month_start
    ) AS previous_snapshot_balance
FROM chosen
WHERE rn = 1;
```

Ví dụ này minh họa kỹ thuật chọn **snapshot cuối cùng có sẵn trong mỗi tháng**. Trong vận hành thực, cần kiểm tra snapshot có **đủ sát mốc kết thúc tháng**, đúng múi giờ và chất lượng dữ liệu hay không; nếu thiếu tháng, `LAG` vẫn có thể so nhầm snapshot của tháng xa hơn.

## 17. Kỳ trước bằng 0 hoặc giá trị âm

### 17.1. Từ 0 lên số dương

```text
Previous = 0
Current  = 1500
Absolute change = +1500
Relative change = (1500 - 0) / 0 → không xác định
```

Không kết luận **+100%**. `100%` tăng từ 100 lên 200, hoặc từ 150 lên 300, nhưng **không biểu diễn một phép chia cho 0**.

Với ứng dụng hiển thị, có thể báo:

```text
Kỳ trước: 0
Kỳ hiện tại: 1.500 nghìn VND
Biến động: +1.500 nghìn VND
Tỷ lệ: N/A (kỳ gốc bằng 0)
```

### 17.2. Từ số dương về 0

```text
Previous = 900
Current  = 0
Absolute change = -900
Relative change = -100%
```

Đây là trường hợp phần trăm xác định, khác hoàn toàn từ 0 lên số dương.

### 17.3. Nếu giá trị kỳ gốc âm?

Các chỉ số như **lợi nhuận ròng**, **dòng tiền thuần** hoặc **số dư điều chỉnh** có thể âm. Công thức:

\[
\frac{C-P}{P}\times100\%
\]

có thể cho dấu phần trăm khó diễn giải khi \(P<0\).

Ví dụ lợi nhuận từ `-100` lên `+50`:

```text
Chênh lệch tuyệt đối: +150
Theo (C-P)/P:         -150%
```

Số `-150%` nhìn giống giảm, trong khi thực tế lợi nhuận **được cải thiện từ lỗ sang lãi**. Một số hệ thống chọn chia cho `ABS(P)` để thể hiện hướng thay đổi:

```sql
SELECT
    (50::numeric - (-100::numeric)) AS absolute_change,
    100.0 * (50::numeric - (-100::numeric))
        / NULLIF(ABS(-100::numeric), 0) AS relative_to_absolute_base;
-- +150; +150%.
```

Nhưng đây là **một định nghĩa tỷ lệ khác**, không phải phép thay thế im lặng cho công thức MoM chuẩn. Với chỉ số có thể âm, hãy công bố phương pháp tính, cách gắn nhãn “cải thiện/suy giảm” và các trường hợp đổi dấu.

## 18. `NULL` khác 0, kỳ thiếu khác kỳ đã đóng

Ba tình huống có thể cùng không có giá trị hiện diện trong truy vấn chi tiết, nhưng ý nghĩa hoàn toàn khác:

| Trạng thái | Ví dụ | Nên biểu diễn |
|---|---|---|
| **Kỳ đã hoàn tất, không phát sinh** | Tháng 4/2026 không có đơn `PAID` | **0**, nếu chỉ số là tổng giao dịch và xác nhận đầy đủ |
| **Kỳ chưa được nạp hoặc bị mất dữ liệu** | Pipeline của tháng 4 lỗi | **Chưa biết** (`NULL` hoặc trạng thái riêng), không phải 0 |
| **Chưa có kỳ đối chiếu trong phạm vi phân tích** | Dòng tháng 1, dữ liệu so không có tháng 12 trước đó | **Không có baseline**, để `NULL` |

Giả sử bảng tổng hợp vận hành có:

```text
period_metrics(
    period_start,
    paid_value,
    data_status      -- OPEN / COMPLETE / FAILED / MISSING
)
```

Có thể quy ước:

```sql
CASE
    WHEN data_status = 'COMPLETE'
         AND paid_value IS NULL THEN 0
    WHEN data_status = 'COMPLETE'
         THEN paid_value
    ELSE NULL
END AS reportable_value
```

Nhưng điều này chỉ đúng nếu `NULL` trong một kỳ `COMPLETE` thực sự có nghĩa “không có giao dịch”, chứ không phải dữ liệu bị thiếu ở cấp dòng. Đây là **quy tắc nghiệp vụ và chất lượng dữ liệu** cần đặc tả, không phải tính năng mà `COALESCE` tự quyết định.

### 18.1. Thêm cột trạng thái so sánh

Một báo cáo dễ sử dụng hơn khi có `comparison_status`:

```sql
CASE
    WHEN previous_value IS NULL THEN 'NO_BASELINE'
    WHEN previous_value = 0 THEN 'ZERO_BASELINE'
    WHEN current_value IS NULL THEN 'CURRENT_NOT_AVAILABLE'
    ELSE 'COMPARABLE'
END AS comparison_status
```

Đây chỉ là **ví dụ thứ tự ưu tiên**, cần điều chỉnh nếu cả hai kỳ đều thiếu hoặc nếu cần báo lỗi dữ liệu trước “không có baseline”.

Quan trọng là **không thay tất cả `NULL` thành 0** rồi làm một phép chia khiến người xem tin rằng mọi kỳ đều đủ dữ liệu.

## 19. So sánh hai kỳ bằng `CASE` hoặc `FILTER` khi chỉ cần một dòng kết quả

Nếu dashboard chỉ yêu cầu **một chỉ số hiện tại** và **một chỉ số kỳ trước**, không nhất thiết phải tổng hợp hàng loạt tháng rồi dùng `LAG`.

### 19.1. Tổng hợp có điều kiện

Ví dụ so **toàn tháng 7** và **toàn tháng 6** bằng `FILTER` trong PostgreSQL:

```sql
WITH sums AS (
    SELECT
        COALESCE(
            SUM(amount_k_vnd) FILTER (
                WHERE ordered_at >= (
                    TIMESTAMP '2026-07-01'
                    AT TIME ZONE 'Asia/Ho_Chi_Minh'
                )
                AND ordered_at < (
                    TIMESTAMP '2026-08-01'
                    AT TIME ZONE 'Asia/Ho_Chi_Minh'
                )
            ), 0::numeric
        ) AS current_value,
        COALESCE(
            SUM(amount_k_vnd) FILTER (
                WHERE ordered_at >= (
                    TIMESTAMP '2026-06-01'
                    AT TIME ZONE 'Asia/Ho_Chi_Minh'
                )
                AND ordered_at < (
                    TIMESTAMP '2026-07-01'
                    AT TIME ZONE 'Asia/Ho_Chi_Minh'
                )
            ), 0::numeric
        ) AS previous_value
    FROM period_lab_orders
    WHERE status = 'PAID'
      AND ordered_at >= (
          TIMESTAMP '2026-06-01'
          AT TIME ZONE 'Asia/Ho_Chi_Minh'
      )
      AND ordered_at < (
          TIMESTAMP '2026-08-01'
          AT TIME ZONE 'Asia/Ho_Chi_Minh'
      )
)
SELECT
    current_value,
    previous_value,
    current_value - previous_value AS change_k_vnd,
    ROUND(
        100.0 * (current_value - previous_value)
        / NULLIF(previous_value, 0),
        2
    ) AS change_pct
FROM sums;
-- 1250 | 1600 | -350 | -21.88
```

Phạm vi ở `WHERE` đầu vào giới hạn scan vào hai tháng; từng `FILTER` định nghĩa đóng góp cho mỗi đại lượng. Với bảng lớn, điều kiện trực tiếp trên `ordered_at` có thể giúp sử dụng chỉ mục nếu kế hoạch tối ưu thấy phù hợp.

### 19.2. Tương đương với `SUM(CASE WHEN ...)`

Ở hệ không hỗ trợ `FILTER`:

```sql
SUM(
    CASE
        WHEN ordered_at >= current_start
         AND ordered_at < current_end
        THEN amount_k_vnd
        ELSE 0
    END
) AS current_value
```

Đây là đoạn biểu thức cần đặt trong truy vấn có các mốc `current_start`, `current_end` đã được khai báo bằng CTE, tham số hoặc cột của bảng `boundaries`.

**Chọn cách nào?**

- Muốn **bảng xu hướng nhiều tháng**: nhóm theo kỳ rồi dùng `LAG` hoặc `JOIN` theo khóa kỳ.
- Muốn **một thẻ KPI của hai khoảng xác định**: `SUM(...) FILTER` hoặc `SUM(CASE...)` thường gọn.
- Muốn **khoảng so sánh phức tạp**, có nhiều chiều và quy tắc đầy đủ dữ liệu: cân nhắc bảng lịch/snapshot và các CTE có tên rõ nghĩa.

## 20. So sánh năm nay so với năm trước khi kỳ chưa hoàn tất

YoY cũng có thể rơi vào bẫy **kỳ hiện tại mới diễn ra một phần**.

Ví dụ khi xem báo cáo ngày 16/7/2026, có ít nhất hai câu hỏi khác nhau:

1. **Toàn tháng 7/2026 so với toàn tháng 7/2025** — chỉ hợp lý khi tháng 7/2026 đã hoàn tất hoặc dùng dự báo có gắn nhãn.
2. **Từ 1/7 tới hết 15/7/2026 so với 1/7 tới hết 15/7/2025** — so khoảng MTD cùng số ngày đã hoàn tất.

Với dữ liệu mẫu:

```text
1–15/7/2026: 700
1–15/7/2025: 400
Δ = +300
YoY MTD = +75%
```

Trong khi **toàn tháng 7** là `1250` so `900`, tương đương `+38,89%`.

Số liệu hai kiểu đều đúng với dữ liệu bài học, nhưng so **hai phạm vi khác nhau**.

### 20.1. Ngày 29/02 và tháng ngắn

Nếu kỳ MTD kết thúc sau ngày 28/2 trong năm nhuận nhưng năm đối chiếu không nhuận, quy tắc “cùng số ngày lịch đã trôi qua” không thể chỉ thay **năm** của một ngày mà không xét lịch.

Các lựa chọn có thể là:

- So **cùng ngày trong tháng** nếu ngày đó tồn tại ở hai năm.
- So **cùng số ngày đã hoàn tất**, có điều chỉnh cho tháng ngắn hơn.
- So **cùng tỷ lệ ngày của kỳ**, ví dụ 50% số ngày tháng.
- So **cùng thứ trong tuần**, nếu nhịp kinh doanh theo thứ mạnh.

Không có một quy tắc tự động đúng cho mọi báo cáo. Khi xử lý ngày 29/2 hoặc lịch tài chính 4-4-5, nên dùng bảng lịch kinh doanh có trường xác định **kỳ so sánh tương ứng**.

### 20.2. Hiệu ứng số ngày và ngày trong tuần

Doanh số tháng 2 thường không thể so theo số ngày như tháng 3 nếu không xét độ dài tháng. So **tổng doanh số** MoM vẫn là một chỉ số hợp lệ, nhưng kết luận về **năng suất bán hàng mỗi ngày** cần thêm chỉ số như:

```text
Doanh số trung bình mỗi ngày lịch
    = doanh số cả tháng / số ngày lịch tháng đó
```

hoặc **mỗi ngày làm việc**, nếu doanh nghiệp có lịch nghỉ/làm việc. Không tự thay số ngày làm việc bằng `EXTRACT(DAY FROM month_end)`; muốn bỏ cuối tuần, lễ Tết và lịch chi nhánh cần một **bảng lịch làm việc**.

## 21. So sánh kỳ theo lịch tài chính, không chỉ lịch dương

Nhiều doanh nghiệp dùng:

- Quý tài chính bắt đầu ở tháng khác tháng 1.
- Tuần bắt đầu vào Chủ nhật.
- Lịch 4-4-5 tuần cho các kỳ báo cáo.
- Kỳ khuyến mãi hay kỳ học bắt đầu/kết thúc vào ngày tùy ý.

Khi đó:

```sql
DATE_TRUNC('month', ordered_at ...)
```

không còn đủ để xác định mọi “kỳ nghiệp vụ”. Một cách thiết kế là bảng `reporting_calendar`:

```text
calendar_date
period_id
period_sequence
period_start
period_end_exclusive
fiscal_year
fiscal_quarter
is_closed
comparison_period_id
```

Khi tổng hợp theo `period_id`, có thể nối với **`comparison_period_id`** hoặc dùng `period_sequence - 1` để xác định kỳ tương ứng theo định nghĩa của doanh nghiệp.

```sql
-- Pseudocode SQL: các bảng reporting_calendar / period_metrics
-- là schema minh họa, chưa được tạo trong script thực hành.
SELECT
    cur.period_id,
    cur.metric_value AS current_value,
    prev.metric_value AS previous_value
FROM period_metrics AS cur
JOIN reporting_periods AS p
    ON p.period_id = cur.period_id
LEFT JOIN period_metrics AS prev
    ON prev.period_id = p.comparison_period_id;
```

Đây là cách tổng quát hơn “trừ đúng một tháng”, bởi chính bảng kỳ được kiểm soát quyết định **kỳ đối chiếu**.

## 22. Khi dữ liệu lịch sử thay đổi sau khi chốt báo cáo

Một báo cáo MoM có thể thay đổi dù tháng hiện tại không có đơn mới nếu dữ liệu quá khứ bị sửa.

Ví dụ:

- Đơn tháng 6 từng là `PAID`, sau đó bị hoàn tiền.
- Đơn tháng 5 được nạp muộn vào ngày chạy báo cáo tháng 7.
- Một bản ghi bị sửa `ordered_at` hoặc `region`, chuyển từ nhóm này sang nhóm khác.
- Bộ phận kế toán thay đổi quy tắc ghi nhận doanh số.

Khi đó, cùng câu SQL chạy ở hai thời điểm có thể tạo **hai số liệu “tháng trước” khác nhau**.

### 22.1. Chỉ số “trạng thái hiện tại của dữ liệu” vs “bản chụp tại ngày chốt”

Có hai mô hình hợp lệ:

1. **Recomputed history**: mỗi lần báo cáo tính lại toàn bộ lịch sử từ trạng thái dữ liệu hiện tại. Dễ phản ánh sửa lỗi, nhưng số cũ có thể thay đổi.
2. **Frozen snapshot**: lưu số liệu đã chốt tại một `as_of` / `snapshot_version`, kèm trạng thái/phương pháp. Dễ tái tạo báo cáo đã công bố, nhưng cần quy trình sửa hồi tố.

Nếu cần giải thích “vì sao tháng trước hôm nay khác báo cáo tháng trước đã gửi”, phải biết mô hình được chọn. `LAG` hay `JOIN` tự chúng **không giải quyết** vấn đề dữ liệu thay đổi sau khi chốt.

### 22.2. Giữ metadata khi xuất báo cáo

Nên có tối thiểu:

```text
metric_name
metric_definition_version
period_start / period_end_exclusive
comparison_period_start / comparison_period_end_exclusive
business_timezone
as_of / data_watermark
is_complete
current_value
previous_value
absolute_change
change_pct
```

Không nhất thiết mọi trường đều hiện trong biểu đồ; nhưng một hệ thống phân tích tốt cần có cách truy nguyên chúng để giải thích các con số.

## 23. Hiệu năng của truy vấn so sánh kỳ

Với lượng dữ liệu lớn, chi phí lớn thường nằm ở việc **đọc và tổng hợp dữ liệu chi tiết**, không phải chỉ ở việc lấy `LAG()` trên vài chục dòng tháng đã nhóm.

### 23.1. Lọc thời gian bằng hai mốc trên cột gốc

Nếu có chỉ mục B-tree trên `ordered_at`, điều kiện:

```sql
WHERE ordered_at >= (
    TIMESTAMP '2026-01-01'
    AT TIME ZONE 'Asia/Ho_Chi_Minh'
)
AND ordered_at < (
    TIMESTAMP '2026-08-01'
    AT TIME ZONE 'Asia/Ho_Chi_Minh'
)
```

giữ cột `ordered_at` nguyên kiểu và có thể giúp truy vấn tận dụng quét theo khoảng.

Ngược lại:

```sql
WHERE DATE_TRUNC(
    'month',
    ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
) = TIMESTAMP '2026-07-01'
```

tính biểu thức trên cột cho từng dòng; chỉ mục thông thường trên `ordered_at` không nhất thiết trực tiếp giúp lọc biểu thức đó. Có thể có chỉ mục biểu thức hoặc tối ưu đặc biệt tùy hệ, nhưng mẫu **khoảng nửa mở** thường dễ sử dụng và diễn đạt rõ hơn.

### 23.2. Chỉ mục và phân vùng dữ liệu

Trên bảng thật, có thể xem xét:

```sql
CREATE INDEX idx_period_lab_orders_status_time
ON period_lab_orders (status, ordered_at);
```

Đây là ví dụ chỉ mục cho truy vấn thường lọc theo `status` và thời gian. Với bảng tạm vài chục dòng, database có thể chọn quét bảng dù chỉ mục tồn tại; không nên xem đó là bằng chứng truy vấn sai.

Trên dữ liệu rất lớn, thiết kế còn có thể dùng **partitioning theo thời gian**, **materialized view** hoặc **bảng tổng hợp theo kỳ**. Việc chọn phụ thuộc cập nhật dữ liệu, độ trễ cho phép và số lượng chiều báo cáo.

### 23.3. Tổng hợp một lần, so nhiều kỳ

Thay vì chạy lại `SUM(amount)` cho từng tháng trong ứng dụng, có thể:

1. Tổng hợp toàn bộ tháng cần quan sát bằng một `GROUP BY`.
2. Tạo lịch đầy đủ nếu cần.
3. Tính các `LAG` hoặc JOIN trên dữ liệu đã tổng hợp.

Ví dụ sau khi có lịch tháng liên tục:

```sql
SELECT
    month_start,
    paid_value_k_vnd,
    LAG(paid_value_k_vnd, 1) OVER (
        ORDER BY month_start
    ) AS previous_month_value,
    LAG(paid_value_k_vnd, 12) OVER (
        ORDER BY month_start
    ) AS same_month_previous_year_value
FROM monthly_complete
ORDER BY month_start;
```

Ở đây `monthly_complete` là bảng/CTE minh họa phải có **một dòng đúng cho mỗi tháng** và có đủ 12 tháng lịch sử để `LAG(12)` có ý nghĩa YoY.

### 23.4. Không tối ưu bằng cách thay đổi câu hỏi

Thay MoM bằng “so với dòng có dữ liệu gần nhất” có thể khiến SQL ngắn hơn, nhưng là **sai ngữ nghĩa** khi tháng trước không phát sinh. Tương tự, thay MTD 15 ngày bằng toàn tháng trước chỉ vì dễ lọc sẽ tạo một phép so không tương xứng.

**Đúng định nghĩa kỳ và chất lượng dữ liệu trước, tối ưu thực thi sau.**

## 24. Khác biệt khi dùng hệ quản trị SQL khác

Ý tưởng **tạo khóa kỳ → tổng hợp → lấy kỳ đối chiếu → tính chênh lệch** có tính phổ quát. Nhưng cú pháp cho từng bước thay đổi.

| Nhu cầu | PostgreSQL | SQL Server | MySQL 8+ | SQLite hiện đại |
|---|---|---|---|---|
| Khóa đầu tháng | `DATE_TRUNC('month', ts)` | Dùng `DATETRUNC(month, ts)` ở phiên bản hỗ trợ hoặc biểu thức `DATEFROMPARTS` | `DATE_FORMAT(ts, '%Y-%m-01')` và chuyển kiểu phù hợp | `date(ts, 'start of month')` |
| Tháng trước | `period - INTERVAL '1 month'` | `DATEADD(month, -1, period)` | `DATE_SUB(period, INTERVAL 1 MONTH)` | `date(period, '-1 month')`, cần kiểm tra ngày cuối tháng |
| Lấy giá trị dòng trước | `LAG(...) OVER (...)` | `LAG(...) OVER (...)` | `LAG(...) OVER (...)` | `LAG(...) OVER (...)` |
| Tạo lịch các tháng | `generate_series` với timestamp | Bảng lịch, CTE đệ quy, hoặc hàm tạo chuỗi ở bản hỗ trợ | Bảng lịch hoặc CTE đệ quy | Bảng lịch hoặc CTE đệ quy |
| Tổng có điều kiện | `SUM(x) FILTER (WHERE...)` | `SUM(CASE WHEN ... THEN x ELSE 0 END)` | `SUM(CASE WHEN ... THEN x ELSE 0 END)` | Có `FILTER` trong các bản hỗ trợ |
| Múi giờ | `AT TIME ZONE` với IANA zone name | Cơ chế `AT TIME ZONE` và tên vùng theo nền tảng | `CONVERT_TZ` với dữ liệu múi giờ được cấu hình | Cần quy tắc chuyển đổi phía ứng dụng/nguồn dữ liệu phù hợp |

**Không chuyển nguyên văn cú pháp múi giờ giữa các hệ.** Tên vùng, kiểu timestamp, quy tắc DST và cách suy kiểu có thể khác; cần kiểm thử ngày gần nửa đêm và vùng thời gian của doanh nghiệp.

### 24.1. Một mẫu MySQL 8+ với `LAG`

Giả sử bảng `monthly_metrics(month_start DATE, paid_value DECIMAL(12,2))` đã có **đầy đủ các tháng**:

```sql
SELECT
    month_start,
    paid_value,
    LAG(paid_value) OVER (
        ORDER BY month_start
    ) AS previous_value
FROM monthly_metrics
ORDER BY month_start;
```

Hàm `LAG` tương tự PostgreSQL. Nhưng việc tạo lịch tháng đầy đủ, chuyển múi giờ, ép kiểu của `DECIMAL` và xử lý kỳ hoàn tất cần cấu trúc phù hợp MySQL.

### 24.2. SQL Server với `DATEADD`

Nếu bảng `monthly_metrics` có `period_start DATE`:

```sql
SELECT
    cur.period_start,
    cur.paid_value AS current_value,
    prev.paid_value AS previous_value
FROM monthly_metrics AS cur
LEFT JOIN monthly_metrics AS prev
    ON prev.period_start = DATEADD(month, -1, cur.period_start);
```

Với kỳ đầu tháng, việc trừ một tháng tránh bẫy ngày 31 khi tìm kỳ trước. Khi dùng phiên bản hỗ trợ `DATETRUNC`, cũng có thể chuẩn hóa khóa kỳ ngay trong bước tổng hợp.

### 24.3. SQLite và việc tạo lịch

SQLite hỗ trợ các hàm cửa sổ như `LAG` ở phiên bản hiện đại, nhưng cơ chế ngày giờ khác PostgreSQL. Với `month_start` là chuỗi ngày chuẩn ISO dạng `YYYY-MM-01`, có thể tìm tháng trước qua:

```sql
date(month_start, '-1 month')
```

Khi giá trị luôn là **ngày đầu tháng**, quy tắc điều chỉnh ngày cuối tháng không ảnh hưởng phép trừ như với ngày 29/30/31. Cần nhất quán định dạng `YYYY-MM-DD` và múi giờ dữ liệu đã được chuẩn hóa.

## 25. Những lỗi phổ biến khi so sánh kỳ

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng `LAG` trực tiếp trên từng đơn | So với **đơn trước**, không phải kỳ trước | Tổng hợp đúng một dòng mỗi kỳ trước |
| Dùng `LAG` trên các tháng có dữ liệu | Khi thiếu tháng, lấy **tháng có dữ liệu gần nhất** | Tạo calendar spine hoặc `JOIN` theo khóa kỳ |
| Quên `PARTITION BY region` | Trộn kỳ của khu vực khác | `LAG` theo từng chiều báo cáo |
| `GROUP BY EXTRACT(MONTH...)` | Trộn cùng tháng của nhiều năm | Dùng ngày đầu tháng hoặc cả năm/tháng |
| Gắn `0` cho mọi kỳ không có dòng | Che lỗi chưa nạp dữ liệu | Phân biệt kỳ complete/unknown |
| Dùng `LAG(...,1,0)` để “đỡ NULL” | Kỳ đầu bị hiểu nhầm có baseline 0 | Giữ `NULL` nếu không có kỳ đối chiếu |
| Tính `(C-P)/P` với `P=0` | Chia cho 0, hoặc ép tỷ lệ sai | Dùng `NULLIF`, hiển thị N/A theo quy tắc |
| Gọi tăng từ 0 lên 1500 là “+100%” | Sai định nghĩa phần trăm | Báo +1500 tuyệt đối, % không xác định |
| So MTD 15 ngày với tháng trước đủ 30 ngày | Hai mẫu thời gian không tương xứng | So hai khoảng đã trôi qua tương đương |
| So quý đang chạy với quý đã đóng | Dễ suy ra giảm giả | Dùng QTD tương ứng hoặc nhãn provisional |
| Dùng `LAG(12)` khi lịch thiếu tháng | Không phải cùng kỳ năm trước | Lịch liền mạch hoặc JOIN trừ một năm |
| Quên khu vực trong JOIN YoY | Nhân dòng và ghép sai nhóm | JOIN bằng cả khóa khu vực và tháng |
| Dùng thời điểm UTC để nhóm tháng Việt Nam | Đơn gần nửa đêm rơi sai tháng | Chuyển `TIMESTAMPTZ` sang múi giờ nghiệp vụ |
| Dùng `BETWEEN` tới 23:59:59 | Bỏ bản ghi có phần giây | Dùng `[period_start, next_start)` |
| Tính trung bình % của vùng để ra % toàn công ty | Không tính trọng số theo mẫu số | Tính lại từ tổng C và tổng P |
| Cộng `COUNT(DISTINCT customer_id)` từng ngày thành tháng | Đếm trùng khách xuất hiện nhiều ngày | Tính distinct trên toàn kỳ |
| Cộng số dư snapshot từng ngày thành tháng | Cộng lặp trạng thái | Chọn snapshot tại mốc kỳ |
| Chọn `WHERE` sau khi `LAG` mà không xét logic | Có thể lọc sai phạm vi baseline | Tách bước tính kỳ và bước hiển thị |
| Thêm chỉ mục mà chưa chốt định nghĩa kỳ | Nhanh nhưng trả kết quả sai | Chốt metric và lịch trước |
| Không lưu mốc `as_of` | Không tái tạo được kết quả lịch sử | Ghi data watermark hoặc snapshot version |

## 26. Thực hành có hướng dẫn

Hãy chạy script mục 3 trước khi thực hiện các bài nhỏ sau.

### 26.1. Bài thực hành A — Lấy đúng giá trị toàn tháng 7 và tháng 6

```sql
SELECT
    DATE_TRUNC(
        'month',
        ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )::date AS month_start,
    SUM(amount_k_vnd) AS paid_value_k_vnd
FROM period_lab_orders
WHERE status = 'PAID'
  AND ordered_at >= (
      TIMESTAMP '2026-06-01' AT TIME ZONE 'Asia/Ho_Chi_Minh'
  )
  AND ordered_at < (
      TIMESTAMP '2026-08-01' AT TIME ZONE 'Asia/Ho_Chi_Minh'
  )
GROUP BY 1
ORDER BY month_start;
```

Kết quả:

```text
2026-06-01 → 1600
2026-07-01 → 1250
```

Các đơn `PENDING` tháng 7 và `CANCELLED` tháng 6 không được cộng.

### 26.2. Bài thực hành B — Dùng `LAG` cho hai tháng

```sql
WITH monthly AS (
    SELECT
        DATE_TRUNC(
            'month',
            ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        )::date AS month_start,
        SUM(amount_k_vnd) AS paid_value_k_vnd
    FROM period_lab_orders
    WHERE status = 'PAID'
      AND ordered_at >= (
          TIMESTAMP '2026-06-01' AT TIME ZONE 'Asia/Ho_Chi_Minh'
      )
      AND ordered_at < (
          TIMESTAMP '2026-08-01' AT TIME ZONE 'Asia/Ho_Chi_Minh'
      )
    GROUP BY 1
)
SELECT
    month_start,
    paid_value_k_vnd,
    LAG(paid_value_k_vnd) OVER (
        ORDER BY month_start
    ) AS previous_value
FROM monthly
ORDER BY month_start;
```

Vì có đủ cả tháng 6 và 7, dòng tháng 7 lấy chính xác `previous_value = 1600`.

### 26.3. Bài thực hành C — Làm lộ lỗi bỏ tháng 4

```sql
WITH monthly AS (
    SELECT
        DATE_TRUNC(
            'month',
            ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        )::date AS month_start,
        SUM(amount_k_vnd) AS paid_value_k_vnd
    FROM period_lab_orders
    WHERE status = 'PAID'
      AND ordered_at >= (
          TIMESTAMP '2026-01-01' AT TIME ZONE 'Asia/Ho_Chi_Minh'
      )
      AND ordered_at < (
          TIMESTAMP '2026-08-01' AT TIME ZONE 'Asia/Ho_Chi_Minh'
      )
    GROUP BY 1
)
SELECT
    month_start,
    paid_value_k_vnd,
    LAG(paid_value_k_vnd) OVER (
        ORDER BY month_start
    ) AS previous_visible_month
FROM monthly
ORDER BY month_start;
```

Hãy quan sát: dòng tháng 5 có `previous_visible_month = 900` của **tháng 3**, không phải tháng 4. Quay lại mẫu đầy đủ ở mục 8 để thấy khi có lịch tháng 4, `previous_paid_value` của tháng 5 sẽ là **0**.

### 26.4. Bài thực hành D — So YoY tháng 7

Chạy câu tự `JOIN` ở mục 12.1. Kỳ hiện tại `2026-07-01`, kỳ đối chiếu `2025-07-01`, lần lượt **1250** và **900**. Kết quả **+350**, **+38,89%**.

### 26.5. Bài thực hành E — So MTD 15 ngày

Chạy câu `FILTER` ở mục 13.2. Kết quả là:

```text
current_mtd = 700
previous_mtd = 1000
change_k_vnd = -300
change_pct = -30.00
```

Đổi kỳ trước thành toàn bộ tháng 6 sẽ cho kết quả khác, nhưng không còn là so **hai khoảng 15 ngày đã hoàn tất**.

## 27. Bài tập tự luyện

Mọi bài tính trên dữ liệu `period_lab_orders` ở mục 3. Với mỗi bài, trước khi viết SQL hãy xác định **mỗi dòng kết quả đại diện cho gì** và **kỳ đối chiếu chính xác là khoảng nào**.

### Bài 1 — Từ dữ liệu chi tiết đến tháng

Viết câu SQL tính `paid_value_k_vnd` theo từng tháng tại `Asia/Ho_Chi_Minh`, chỉ tính `status='PAID'`. Vì sao tháng 4/2026 không xuất hiện nếu chỉ `GROUP BY` trên dữ liệu nguồn?

### Bài 2 — Đọc số liệu MoM

Tính chênh lệch tuyệt đối và phần trăm của tháng 2/2026 so với tháng 1/2026; sau đó tháng 3 so với tháng 2. Nêu đơn vị của kết quả.

### Bài 3 — Bẫy tháng trống

Dùng `LAG()` trên các nhóm `PAID` từ tháng 1 đến 7/2026 **mà không tạo lịch tháng**. Tháng nào bị so sai với “tháng trước theo lịch”? Nó đang so với tháng nào?

### Bài 4 — Tạo lịch kỳ

Viết CTE `months` bằng `generate_series()` để có đủ **7 tháng** từ tháng 1 đến tháng 7/2026. Dùng `LEFT JOIN` vào bảng tổng hợp tháng và biểu diễn tháng hoàn tất không có đơn bằng 0.

### Bài 5 — Kỳ gốc 0

Tháng 4 có giá trị 0, tháng 5 có 1500. Chênh lệch tuyệt đối là bao nhiêu? Vì sao không được nói “tăng 100%”? Viết biểu thức SQL xử lý mẫu số bằng 0.

### Bài 6 — Lấy đúng tháng trước bằng `JOIN`

Viết truy vấn tự `JOIN` bảng tổng hợp tháng theo:

```text
prev.month_start = current.month_start - 1 tháng lịch
```

Ở tháng 5, nếu tháng 4 không có dòng trong bảng tổng hợp, `previous_value` nên là gì trước khi áp dụng chính sách điền 0?

### Bài 7 — So theo khu vực

Viết `LAG` theo từng khu vực. Nếu tháng 6 North có 1000, tháng 7 North có 700; tháng 6 South có 600, tháng 7 South có 550, hãy tính chênh lệch của từng khu vực.

### Bài 8 — YoY tháng 7

Viết truy vấn lấy tổng `PAID` tháng 7/2026 so với tháng 7/2025 bằng khóa **ngày đầu tháng**. Tính chênh lệch và phần trăm YoY.

### Bài 9 — YoY từng khu vực

Tính YoY tháng 7 theo North và South. Vì sao phải đưa `region` vào điều kiện nối với kỳ năm trước?

### Bài 10 — MTD tại ngày 16/7

Giả sử mốc chốt là **00:00 ngày 16/7/2026** tại Việt Nam. So 1–15/7 với **1–15/6**. Dùng khoảng nửa mở và dự đoán các tổng, chênh lệch và tỷ lệ.

### Bài 11 — Lọc làm mất baseline

Vì sao câu truy vấn có `WHERE month_start >= '2026-02-01'` ở **cùng cấp** với `LAG` có thể làm tháng 2 nhận `NULL` thay vì 1000? Hãy viết cách dùng CTE để giữ dữ liệu tháng 1 cho giai đoạn tính toán rồi chỉ hiển thị từ tháng 2.

### Bài 12 — Quý đang chạy

Dựa trên dữ liệu mẫu, tính tổng Q1 và Q2/2026. Có nên so trực tiếp số Q3 (mới có tháng 7) với Q2 đủ ba tháng để kết luận tăng/giảm quý? Vì sao?

### Bài 13 — Tỷ lệ chuyển đổi

Kỳ trước có 100 đơn từ 2000 lượt, kỳ hiện tại có 120 đơn từ 2000 lượt. Tính tỷ lệ của mỗi kỳ, chênh lệch **điểm phần trăm** và thay đổi **tương đối**.

### Bài 14 — Giá trị thiếu và số 0

Hai tình huống: (A) tháng 4 đã đóng dữ liệu, không có đơn `PAID`; (B) tháng 4 có sự cố nạp dữ liệu nên không biết số đơn. Trong mỗi tình huống có nên ghi `0` cho `paid_value_k_vnd` không? Vì sao?

### Bài 15 — Chỉ số trạng thái cuối tháng

Bạn được yêu cầu so “tồn kho cuối tháng” với “tồn kho cuối tháng trước”. Vì sao không dùng `SUM(stock_balance)` trên các snapshot trong tháng? Hãy mô tả cách chọn một snapshot hợp lệ của từng tháng rồi so.

<details>
<summary>Gợi ý đáp án và lời giải</summary>

**Bài 1:** Nhóm theo `DATE_TRUNC('month', ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date`, lọc `PAID`, rồi dùng `SUM(amount_k_vnd)`. Tháng 4 không xuất hiện vì không có dòng `PAID`; `GROUP BY` chỉ tạo nhóm từ những khóa thực sự có ở đầu vào.

```sql
SELECT
    DATE_TRUNC(
        'month',
        ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )::date AS month_start,
    SUM(amount_k_vnd) AS paid_value_k_vnd
FROM period_lab_orders
WHERE status = 'PAID'
GROUP BY 1
ORDER BY month_start;
```

**Bài 2:** Tháng 2 so tháng 1 là `1200-1000=+200` nghìn VND, `+20%`. Tháng 3 so tháng 2 là `900-1200=-300` nghìn VND, `-25%`.

**Bài 3:** Tháng **5** bị lấy kỳ so sánh là **tháng 3** (`900`) vì tháng 4 không có nhóm `PAID`. Dữ liệu cần thêm dòng tháng 4 (0 nếu đã hoàn tất) hoặc dùng JOIN vào khóa tháng trước, giữ `NULL` khi chưa có giá trị.

**Bài 4:** CTE lịch:

```sql
WITH months AS (
    SELECT g.month_ts::date AS month_start
    FROM generate_series(
        TIMESTAMP '2026-01-01',
        TIMESTAMP '2026-07-01',
        INTERVAL '1 month'
    ) AS g(month_ts)
),
monthly AS (
    SELECT
        DATE_TRUNC(
            'month',
            ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        )::date AS month_start,
        SUM(amount_k_vnd) AS paid_value
    FROM period_lab_orders
    WHERE status = 'PAID'
    GROUP BY 1
)
SELECT
    m.month_start,
    COALESCE(x.paid_value, 0::numeric) AS paid_value
FROM months AS m
LEFT JOIN monthly AS x ON x.month_start = m.month_start
ORDER BY m.month_start;
```

Trong bài mẫu, tháng 4 có giá trị 0 theo giả định kỳ đã hoàn tất.

**Bài 5:** Chênh lệch tuyệt đối `+1500` nghìn VND. Tỷ lệ `(1500-0)/0` không xác định:

```sql
ROUND(
    100.0 * (current_value - previous_value)
    / NULLIF(previous_value, 0),
    2
)
```

**Bài 6:** Nối `prev.month_start = (cur.month_start - INTERVAL '1 month')::date`. Nếu bảng tổng hợp không có tháng 4, `previous_value` của tháng 5 là **`NULL`**, không được lấy tháng 3. Quy tắc biến `NULL` thành 0 phải dựa vào trạng thái dữ liệu tháng 4.

**Bài 7:** Cửa sổ:

```sql
LAG(paid_value_k_vnd) OVER (
    PARTITION BY region
    ORDER BY month_start
)
```

North: `700-1000=-300`, tương đương `-30%`. South: `550-600=-50`, tương đương khoảng `-8,33%`.

**Bài 8:** Tháng 7/2026 có `1250`; tháng 7/2025 có `900`. Chênh lệch `+350`, YoY `+38,89%`. Dùng:

```sql
prev.month_start = (
    cur.month_start - INTERVAL '1 year'
)::date
```

trên CTE tổng hợp `monthly` như mục 12.

**Bài 9:** North: `700` so `400`, tăng `+300` hay `+75%`. South: `550` so `500`, tăng `+50` hay `+10%`. Phải nối cả `region` lẫn `month_start`; nếu chỉ nối tháng, North tháng 7/2026 có thể bị ghép cả North và South tháng 7/2025.

**Bài 10:** Dùng `[2026-07-01,2026-07-16)` và `[2026-06-01,2026-06-16)` tại Việt Nam. Kết quả hiện tại `700`, kỳ trước `1000`, chênh lệch `-300`, tỷ lệ `-30%`.

**Bài 11:** `WHERE` loại tháng 1 trước khi tính hàm cửa sổ, nên tháng 2 không có dòng trước. Cách đúng:

```sql
WITH compared AS (
    SELECT
        month_start,
        paid_value_k_vnd,
        LAG(paid_value_k_vnd) OVER (
            ORDER BY month_start
        ) AS previous_value
    FROM monthly_complete
)
SELECT *
FROM compared
WHERE month_start >= DATE '2026-02-01'
ORDER BY month_start;
```

`monthly_complete` là bảng hoặc CTE lịch tháng đã điền, chứa cả tháng 1 trước khi lọc hiển thị.

**Bài 12:** Q1 = `1000+1200+900=3100`; Q2 = `0+1500+1600=3100`, nên QoQ Q2 so Q1 là `0%`. Q3 có mới tháng 7 trong dữ liệu và **chưa đủ quý**, nên không dùng nó để kết luận về tăng/giảm **quý đầy đủ**.

**Bài 13:** Kỳ trước `100/2000=5%`; hiện tại `120/2000=6%`. Tăng **1 điểm phần trăm** và tăng **20% tương đối** từ tỷ lệ gốc 5%.

**Bài 14:** (A) có thể ghi **0** khi kỳ đã xác nhận hoàn tất và không có đơn `PAID`; (B) phải giữ **chưa biết/NULL**, không thể coi lỗi nạp dữ liệu là giá trị 0.

**Bài 15:** Tồn kho là trạng thái tại một mốc, cộng các snapshot sẽ đếm lặp cùng hàng tồn. Cần chọn **snapshot hợp lệ cuối cùng trước mốc chốt của kỳ**, có quy tắc xử lý thiếu snapshot và thời gian, sau đó đối chiếu với snapshot cuối kỳ trước bằng `LAG` trên lịch đầy đủ hoặc `JOIN` theo khóa kỳ.

</details>

## 28. Mẫu truy vấn tham chiếu và nguyên tắc kết thúc

Mẫu tư duy cho **MoM**:

```text
1. Chốt metric, timezone, grain, kỳ đóng/mở.
2. Tổng hợp dữ liệu chi tiết thành một dòng mỗi (chiều, tháng).
3. Tạo đủ các tháng (và tổ hợp chiều) cần so sánh.
4. Chỉ chuyển NULL thành 0 khi xác nhận kỳ đủ dữ liệu.
5. Dùng LAG(1) PARTITION BY chiều ORDER BY tháng
   hoặc JOIN vào khóa (tháng - 1 month).
6. Δ = current - previous.
7. % = 100 × Δ / NULLIF(previous, 0).
8. Ghi rõ baseline, trạng thái kỳ và mốc chốt trong kết quả.
```

Mẫu tư duy cho **YoY**:

```text
1. Cùng định nghĩa metric và chiều phân tích như kỳ hiện tại.
2. Đối chiếu với khóa kỳ - 1 year, hoặc LAG(12) khi lịch tháng đủ.
3. Đảm bảo hai kỳ có mức hoàn tất tương đương.
4. Phân biệt toàn kỳ với YTD/MTD/QTD.
5. Xử lý kỳ thiếu, baseline 0, mùa vụ và chênh lệch độ dài kỳ.
```

**Ba quy tắc quan trọng nhất:**

1. **`LAG` lấy dòng trước; muốn đúng “kỳ lịch trước” phải bảo đảm lịch liền mạch hoặc JOIN theo khóa kỳ.**
2. **0 khác `NULL`: kỳ hoàn tất không phát sinh có thể là 0, còn kỳ thiếu dữ liệu phải giữ trạng thái chưa biết.**
3. **So sánh chỉ có ý nghĩa khi hai kỳ có cùng định nghĩa chỉ số, cùng cấp độ phân tích và phạm vi thời gian phù hợp.**

Khi thực hiện đủ ba quy tắc đó, mẫu truy vấn “kỳ hiện tại so với kỳ trước” trở thành một công cụ phân tích đáng tin cậy: không chỉ hiển thị mức tăng/giảm, mà còn cho biết **tăng/giảm so với cái gì**, **tính từ những dữ liệu nào**, và **trong điều kiện so sánh nào**.

# Bù ngày thiếu bằng bảng lịch và kết nối ngoài

Một báo cáo doanh thu theo ngày thường được viết bằng `GROUP BY`. Nhưng nếu một ngày **không có giao dịch**, kết quả tổng hợp sẽ **không có hàng cho ngày ấy**. Biểu đồ có thể bỏ qua ngày trống, phép tính trung bình trượt có thể hiểu sai “ba ngày gần nhất” thành “ba ngày có hoạt động gần nhất”, và bảng theo dõi có thể tạo cảm giác dữ liệu bị mất.

Để báo cáo hiển thị **đầy đủ mọi ngày trong một khoảng**, ta cần chủ động tạo một tập ngày chuẩn — thường gọi là **bảng lịch** (*calendar table*, *date dimension*) hoặc **date spine** — rồi dùng **kết nối ngoài trái** (`LEFT JOIN`) từ lịch sang dữ liệu đã tổng hợp.

Bài học thuộc chương **Mẫu truy vấn** của Database SQL. Các ví dụ chính sử dụng **PostgreSQL**, với bộ dữ liệu đủ để phân biệt ba tình huống rất khác nhau:

1. Ngày thực sự **không có giao dịch nào**.
2. Ngày **có giao dịch**, nhưng không có giao dịch đạt điều kiện báo cáo, chẳng hạn `status = 'paid'`.
3. Ngày **có giao dịch paid**, nhưng số tiền chưa được ghi nhận và mang `NULL`.

Cách bù ngày đúng không chỉ cần tạo ra một hàng cho mỗi ngày: nó còn phải giữ **đúng ý nghĩa của số 0, giá trị thiếu, bộ lọc, cấp tổng hợp và múi giờ**.

## 1. Vì sao GROUP BY tự bỏ qua ngày không có dữ liệu?

Giả sử có bảng:

| Ngày | Doanh thu |
| --- | ---: |
| 01/06 | 100 |
| 01/06 | 50 |
| 02/06 | 70 |
| 04/06 | 60 |

Câu:

```sql
SELECT sold_on, SUM(amount) AS revenue
FROM sales
GROUP BY sold_on
ORDER BY sold_on;
```

trả:

| Ngày | Doanh thu |
| --- | ---: |
| 01/06 | 150 |
| 02/06 | 70 |
| 04/06 | 60 |

Ngày **03/06 không xuất hiện** vì không có hàng đầu vào nào mang ngày đó. `GROUP BY` chỉ tạo nhóm cho các giá trị thực sự gặp trong dữ liệu.

Nếu yêu cầu là “hiển thị từ 01/06 đến 04/06, kể cả ngày không bán hàng”, báo cáo mong muốn phải có:

| Ngày | Doanh thu |
| --- | ---: |
| 01/06 | 150 |
| 02/06 | 70 |
| 03/06 | 0 |
| 04/06 | 60 |

Giải pháp không phải thêm `COALESCE` vào `SUM` của truy vấn cũ: **COALESCE không thể tạo ra một hàng chưa từng tồn tại**.

Ta phải có một tập nguồn chứa đủ bốn ngày rồi nối dữ liệu doanh thu vào tập đó:

```text
Bảng lịch (đầy đủ ngày)               Tổng giao dịch (ngày có dữ liệu)
01/06                                01/06 → 150
02/06                                02/06 →  70
03/06                                04/06 →  60
04/06

           LEFT JOIN theo ngày
                     ↓
01/06 → 150
02/06 →  70
03/06 → không có hàng khớp → 0 theo quy tắc hiển thị
04/06 →  60
```

**Bảng lịch phải nằm bên trái của `LEFT JOIN`** nếu mục tiêu là giữ mọi ngày trong lịch.

## 2. Ý tưởng tổng quát của mẫu truy vấn

Mẫu bù ngày có ba bước:

1. **Tạo lịch đầy đủ:** một hàng cho mỗi ngày yêu cầu.
2. **Tổng hợp bảng sự kiện đúng cấp:** một hàng cho mỗi ngày (hoặc mỗi ngày–khu vực–kênh) mà có dữ liệu.
3. **LEFT JOIN từ lịch sang kết quả tổng hợp:** bảo toàn tất cả ngày, sau đó chuyển các trường hợp “không có dữ liệu” thành cách hiển thị thích hợp.

Cấu trúc:

```sql
WITH daily_fact AS (
    SELECT event_date, SUM(value) AS daily_value
    FROM fact_table
    WHERE ...
    GROUP BY event_date
)
SELECT
    cal.calendar_date,
    COALESCE(f.daily_value, 0) AS daily_value
FROM calendar_table AS cal
LEFT JOIN daily_fact AS f
    ON f.event_date = cal.calendar_date
WHERE cal.calendar_date >= :start_date
  AND cal.calendar_date <  :end_exclusive
ORDER BY cal.calendar_date;
```

Đây là **mẫu khái niệm**: `fact_table`, `calendar_table` và các tham số có tên chưa phải bảng/biến thực tế trong bộ ví dụ bên dưới.

Trong ví dụ đơn giản, `COALESCE(f.daily_value,0)` phù hợp nếu `NULL` chỉ xuất phát từ **không có hàng khớp**. Nhưng nếu một ngày có giao dịch với `amount = NULL`, phép `SUM(amount)` cũng có thể trả `NULL` vì **chưa biết số tiền**, không phải vì không có giao dịch.

Bài học sẽ xây dựng một phiên bản nhận biết được hai tình huống đó.

## 3. Chuẩn bị dữ liệu thực hành PostgreSQL

Ta dùng hai bảng tạm: bảng giao dịch `demo_orders_254` và bảng lịch `demo_calendar_254`. Mốc ngày cố định giúp kết quả có thể kiểm chứng bằng tay bất kể thời gian chạy bài.

### 3.1. Tạo bảng giao dịch

```sql
CREATE TEMP TABLE demo_orders_254 (
    order_id    INTEGER PRIMARY KEY,
    ordered_on  DATE NOT NULL,
    region      TEXT NOT NULL,
    channel     TEXT NOT NULL,
    status      TEXT NOT NULL
        CHECK (status IN ('paid', 'pending', 'cancelled')),
    amount      NUMERIC(12, 2),
    CHECK (amount IS NULL OR amount >= 0)
);

INSERT INTO demo_orders_254
    (order_id, ordered_on, region, channel, status, amount)
VALUES
    ( 1, DATE '2025-06-01', 'North', 'Online', 'paid',      100.00),
    ( 2, DATE '2025-06-01', 'North', 'Online', 'paid',       50.00),
    ( 3, DATE '2025-06-01', 'South', 'Store',  'paid',       80.00),
    ( 4, DATE '2025-06-02', 'North', 'Store',  'paid',       70.00),
    ( 5, DATE '2025-06-02', 'South', 'Online', 'paid',      120.00),
    ( 6, DATE '2025-06-03', 'North', 'Online', 'pending',   200.00),
    ( 7, DATE '2025-06-03', 'South', 'Store',  'cancelled',  90.00),
    ( 8, DATE '2025-06-04', 'North', 'Online', 'paid',       60.00),
    ( 9, DATE '2025-06-04', 'South', 'Online', 'paid',       40.00),
    (10, DATE '2025-06-04', 'South', 'Store',  'paid',       30.00),
    (11, DATE '2025-06-05', 'North', 'Online', 'paid',         NULL),
    (12, DATE '2025-06-06', 'South', 'Store',  'paid',      110.00),
    (13, DATE '2025-06-06', 'North', 'Store',  'paid',       90.00),
    (14, DATE '2025-06-07', 'North', 'Online', 'paid',      130.00),
    (15, DATE '2025-06-07', 'South', 'Online', 'paid',       70.00);
```

Giải thích ba trường hợp quan trọng:

- **03/06:** có đơn `pending` và `cancelled`, nhưng **không có đơn paid**.
- **05/06:** có một đơn `paid`, nhưng `amount IS NULL` — tiền **chưa biết**, không thể tự khẳng định bằng 0.
- **08/06:** không có đơn nào trong bảng nguồn.

Ngoài ra, 01/06 và 04/06 có nhiều giao dịch trong cùng ngày, để quan sát lỗi nhân hàng nếu nối lịch trực tiếp vào bảng giao dịch.

### 3.2. Tính tổng từ bảng giao dịch trước

```sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_orders,
    COUNT(amount) FILTER (WHERE status = 'paid')
        AS paid_orders_with_known_amount,
    SUM(amount) FILTER (WHERE status = 'paid')
        AS known_paid_revenue
FROM demo_orders_254;
```

Kết quả:

| `all_orders` | `paid_orders` | `paid_orders_with_known_amount` | `known_paid_revenue` |
| ---: | ---: | ---: | ---: |
| 15 | 13 | 12 | 950 |

Doanh thu đã biết của các đơn paid:

```text
01/06: 100 + 50 + 80 = 230
02/06: 70 + 120      = 190
03/06: không có paid
04/06: 60 + 40 + 30  = 130
05/06: một đơn paid có amount NULL
06/06: 110 + 90      = 200
07/06: 130 + 70      = 200
08/06: không có đơn
---------------------------
Tổng amount đã biết  = 950
```

Do `SUM` bỏ qua `NULL`, tổng 950 là **tổng những khoản đã biết**, không bảo đảm là tổng doanh thu cuối cùng nếu giá trị 05/06 sau này được bổ sung.

### 3.3. Tạo bảng lịch từ 01/06 đến 08/06

```sql
CREATE TEMP TABLE demo_calendar_254 (
    calendar_date DATE PRIMARY KEY,
    iso_weekday   SMALLINT NOT NULL,
    is_weekend    BOOLEAN NOT NULL
);

INSERT INTO demo_calendar_254
    (calendar_date, iso_weekday, is_weekend)
SELECT
    g.day_ts::date AS calendar_date,
    EXTRACT(ISODOW FROM g.day_ts)::smallint AS iso_weekday,
    EXTRACT(ISODOW FROM g.day_ts) IN (6, 7) AS is_weekend
FROM generate_series(
    TIMESTAMP '2025-06-01 00:00:00',
    TIMESTAMP '2025-06-08 00:00:00',
    INTERVAL '1 day'
) AS g(day_ts);
```

Kiểm tra trực quan bảng lịch:

```sql
SELECT calendar_date, iso_weekday, is_weekend
FROM demo_calendar_254
ORDER BY calendar_date;
```

Bảng lịch có **8 hàng**, bất kể dữ liệu giao dịch có hay không. `ISODOW` trong PostgreSQL quy ước thứ Hai là 1, thứ Bảy là 6, Chủ nhật là 7.

| `calendar_date` | `iso_weekday` | `is_weekend` |
| --- | ---: | --- |
| 2025-06-01 | 7 | true |
| 2025-06-02 | 1 | false |
| 2025-06-03 | 2 | false |
| 2025-06-04 | 3 | false |
| 2025-06-05 | 4 | false |
| 2025-06-06 | 5 | false |
| 2025-06-07 | 6 | true |
| 2025-06-08 | 7 | true |

Một bảng lịch cho hệ thống thực tế thường có nhiều năm, một hàng trên mỗi ngày, và có thêm thông tin về tuần, tháng, quý, năm tài chính hoặc lịch làm việc. Bảng tạm này chỉ đủ để học mẫu bù ngày.

## 4. Xem vấn đề: GROUP BY chỉ tạo những ngày có paid

```sql
SELECT
    ordered_on,
    COUNT(*) AS paid_orders,
    COUNT(amount) AS known_amounts,
    SUM(amount) AS revenue
FROM demo_orders_254
WHERE status = 'paid'
GROUP BY ordered_on
ORDER BY ordered_on;
```

Kết quả:

| Ngày | `paid_orders` | `known_amounts` | `revenue` |
| --- | ---: | ---: | ---: |
| 01/06 | 3 | 3 | 230 |
| 02/06 | 2 | 2 | 190 |
| 04/06 | 3 | 3 | 130 |
| 05/06 | 1 | 0 | `NULL` |
| 06/06 | 2 | 2 | 200 |
| 07/06 | 2 | 2 | 200 |

Có **6 hàng ngày**. Hai ngày **03/06** và **08/06** không xuất hiện.

Lưu ý: 05/06 **có hàng**, nhưng `SUM(amount)` trả `NULL` vì mọi giá trị amount của nhóm đều `NULL`. Nếu không phân biệt tình huống này với ngày không có đơn, báo cáo dễ đưa ra kết luận sai.

## 5. Mẫu chuẩn: tổng hợp trước, LEFT JOIN với lịch sau

Đây là cách viết chính:

```sql
WITH daily_paid AS (
    SELECT
        ordered_on,
        COUNT(*) AS paid_orders,
        COUNT(amount) AS known_amounts,
        SUM(amount) AS revenue
    FROM demo_orders_254
    WHERE status = 'paid'
    GROUP BY ordered_on
)
SELECT
    c.calendar_date,
    COALESCE(d.paid_orders, 0) AS paid_orders,
    COALESCE(d.known_amounts, 0) AS known_amounts,
    CASE
        WHEN d.ordered_on IS NULL THEN 0::numeric
        ELSE d.revenue
    END AS revenue
FROM demo_calendar_254 AS c
LEFT JOIN daily_paid AS d
    ON d.ordered_on = c.calendar_date
ORDER BY c.calendar_date;
```

Kết quả có **đầy đủ tám ngày**:

| Ngày | `paid_orders` | `known_amounts` | `revenue` |
| --- | ---: | ---: | ---: |
| 01/06 | 3 | 3 | 230 |
| 02/06 | 2 | 2 | 190 |
| 03/06 | 0 | 0 | 0 |
| 04/06 | 3 | 3 | 130 |
| 05/06 | 1 | 0 | `NULL` |
| 06/06 | 2 | 2 | 200 |
| 07/06 | 2 | 2 | 200 |
| 08/06 | 0 | 0 | 0 |

### 5.1. Vì sao lịch đứng bên trái?

```sql
FROM demo_calendar_254 AS c
LEFT JOIN daily_paid AS d
    ON d.ordered_on = c.calendar_date
```

`LEFT JOIN` bảo toàn **tất cả hàng bên trái**. Ngày 03/06 và 08/06 vẫn tồn tại vì chúng là hàng của `c`; các cột từ `d` trở thành `NULL` khi không có ngày paid khớp.

Nếu đảo thứ tự:

```sql
FROM daily_paid AS d
LEFT JOIN demo_calendar_254 AS c
    ON c.calendar_date = d.ordered_on
```

thì bên được bảo toàn là `daily_paid` — bảng chỉ có sáu ngày. Hai ngày còn thiếu vẫn không được tạo ra.

### 5.2. Vì sao tổng hợp giao dịch trước khi nối?

Ta muốn **một hàng trên mỗi ngày**. `daily_paid` đã có đúng một hàng cho từng `ordered_on` có giao dịch paid. Khi nối với lịch có khóa chính theo ngày, mỗi ngày lịch khớp **tối đa một hàng tổng**.

Điều đó giúp:

- Tránh sinh nhiều dòng báo cáo trên cùng một ngày.
- Đặt mọi aggregate (`COUNT`, `SUM`, `AVG`) ở đúng cấp hạt (*grain*).
- Giữ logic lọc paid tập trung trong một CTE.
- Phân biệt rõ ngày không có nhóm nào với ngày có nhóm nhưng giá trị `NULL`.

Có thể `LEFT JOIN` trực tiếp bảng giao dịch rồi `GROUP BY` ngày lịch, nhưng phải kiểm soát cẩn thận số hàng mở rộng, cách đếm và các phép nối phát sinh. Mẫu **tổng hợp trước – nối sau** thường dễ đọc và dễ mở rộng hơn.

### 5.3. CASE xử lý NULL khác COALESCE ở đâu?

Câu phổ biến:

```sql
COALESCE(d.revenue, 0) AS revenue
```

sẽ hiển thị **0 ở cả ba tình huống**:

- 03/06 không có đơn paid.
- 05/06 có đơn paid nhưng số tiền `NULL`.
- 08/06 không có đơn nào.

Trong dữ liệu mẫu, điều đó sẽ **xóa mất dấu hiệu thiếu số tiền của đơn 11**.

Vì vậy, phiên bản chính dùng:

```sql
CASE
    WHEN d.ordered_on IS NULL THEN 0::numeric
    ELSE d.revenue
END
```

Nếu **không có hàng tổng hợp khớp**, trả 0. Nếu **có hàng tổng hợp**, giữ nguyên `SUM(amount)`, kể cả khi nó là `NULL`. Khi nghiệp vụ xác nhận mọi amount paid luôn `NOT NULL` hoặc quy ước thiếu amount bằng 0, `COALESCE` đơn giản có thể chấp nhận được.

## 6. COUNT(*) trong LEFT JOIN: bẫy một hàng giả

Giả sử bỏ qua bước tổng hợp trước và nối trực tiếp lịch với đơn paid:

```sql
SELECT
    c.calendar_date,
    COUNT(*) AS joined_rows,
    COUNT(o.order_id) AS paid_orders,
    COUNT(o.amount) AS known_amounts,
    SUM(o.amount) AS paid_revenue
FROM demo_calendar_254 AS c
LEFT JOIN demo_orders_254 AS o
    ON o.ordered_on = c.calendar_date
   AND o.status = 'paid'
GROUP BY c.calendar_date
ORDER BY c.calendar_date;
```

Ở ngày không có đơn paid như 03/06 hoặc 08/06:

- `LEFT JOIN` vẫn tạo **một hàng đầu ra** chứa ngày lịch, còn mọi cột `o` là `NULL`.
- `COUNT(*)` đếm hàng đó nên trả **1**.
- `COUNT(o.order_id)` trả **0** vì `o.order_id` không có giá trị.
- `COUNT(o.amount)` trả **0**.
- `SUM(o.amount)` trả `NULL`.

Ví dụ:

| Ngày | `COUNT(*)` | `COUNT(o.order_id)` | `COUNT(o.amount)` |
| --- | ---: | ---: | ---: |
| 01/06 | 3 | 3 | 3 |
| 03/06 | 1 | 0 | 0 |
| 05/06 | 1 | 1 | 0 |
| 08/06 | 1 | 0 | 0 |

**Không dùng `COUNT(*)` sau `LEFT JOIN` để đếm bản ghi phía phải**, vì nó cũng đếm hàng mở rộng không khớp. Hãy đếm một cột bên phải **chắc chắn không `NULL` trên hàng thật**, thường là khóa chính `o.order_id`.

Nếu đã tổng hợp trước bằng CTE rồi nối, có thể dùng `COALESCE(d.paid_orders,0)`, vì `paid_orders` là số đếm đã tính trong bảng sự kiện và `NULL` của nó là dấu hiệu không có nhóm khớp.

## 7. Bẫy đặt bộ lọc ở WHERE sau LEFT JOIN

Một lỗi điển hình:

```sql
-- SAI nếu mục tiêu là giữ mọi ngày lịch:
SELECT
    c.calendar_date,
    COUNT(o.order_id) AS paid_orders
FROM demo_calendar_254 AS c
LEFT JOIN demo_orders_254 AS o
    ON o.ordered_on = c.calendar_date
WHERE o.status = 'paid'
GROUP BY c.calendar_date
ORDER BY c.calendar_date;
```

Điều kiện:

```sql
WHERE o.status = 'paid'
```

được áp dụng **sau phép nối**. Với ngày không có hàng phải khớp, `o.status` là `NULL`, nên điều kiện không đúng và ngày bị loại.

Thậm chí ngày 03/06 có đơn nhưng chỉ có `pending`/`cancelled` cũng bị loại. Kết quả quay về sáu ngày, mất mục tiêu bù ngày.

### 7.1. Cách sửa A: đặt bộ lọc bản ghi phải trong ON

```sql
SELECT
    c.calendar_date,
    COUNT(o.order_id) AS paid_orders,
    SUM(o.amount) AS paid_revenue
FROM demo_calendar_254 AS c
LEFT JOIN demo_orders_254 AS o
    ON o.ordered_on = c.calendar_date
   AND o.status = 'paid'
GROUP BY c.calendar_date
ORDER BY c.calendar_date;
```

`ON` quyết định hàng bên phải nào được xem là **khớp**, còn `LEFT JOIN` vẫn giữ mọi ngày bên trái. Sau đó có thể áp dụng quy tắc hiển thị 0/`NULL`.

### 7.2. Cách sửa B: lọc và tổng hợp bảng phải trước

```sql
WITH paid_by_day AS (
    SELECT
        ordered_on,
        COUNT(*) AS paid_orders,
        SUM(amount) AS revenue
    FROM demo_orders_254
    WHERE status = 'paid'
    GROUP BY ordered_on
)
SELECT
    c.calendar_date,
    COALESCE(p.paid_orders, 0) AS paid_orders,
    CASE
        WHEN p.ordered_on IS NULL THEN 0::numeric
        ELSE p.revenue
    END AS revenue
FROM demo_calendar_254 AS c
LEFT JOIN paid_by_day AS p
    ON p.ordered_on = c.calendar_date
ORDER BY c.calendar_date;
```

Đây là mẫu được ưu tiên trong các báo cáo có nhiều chỉ số: mỗi bước có **một trách nhiệm rõ ràng**.

### 7.3. Có nên dùng WHERE o.status='paid' OR o.order_id IS NULL?

Không nên coi đây là cách sửa tổng quát:

```sql
-- Dễ sai khi ngày có đơn không paid nhưng không có đơn paid:
WHERE o.status = 'paid'
   OR o.order_id IS NULL
```

Với ngày 03/06, phép `LEFT JOIN` theo **ngày** đã tìm thấy hai đơn thật (pending và cancelled), nên **không có hàng mở rộng NULL**. Cả hai hàng thật đều bị `WHERE` loại, khiến 03/06 vẫn biến mất.

Cách chắc chắn là xác định “đơn paid khớp” ngay trong `ON` hoặc trước khi nối.

## 8. Phân biệt bốn khái niệm: ngày trống, đơn không paid, tiền chưa biết và tiền bằng 0

Một bảng báo cáo tốt cần mô tả rõ ý nghĩa của từng giá trị:

| Trường hợp | Có đơn trong bảng nguồn? | Có đơn paid? | `SUM(amount)` paid | Cách diễn giải |
| --- | --- | --- | --- | --- |
| 03/06 | Có | Không | `NULL` nếu chỉ aggregate paid trên ngày này không có nhóm | Ngày có hoạt động nhưng doanh thu paid bằng 0 theo quy ước |
| 05/06 | Có | Có, một đơn | `NULL` | Có giao dịch paid nhưng số tiền chưa biết |
| 08/06 | Không | Không | Không có nhóm | Ngày không có giao dịch; có thể hiển thị doanh thu 0 |
| Ngày có giao dịch paid `amount = 0` | Có | Có | 0 | Doanh thu thực sự được ghi nhận là 0 |

`NULL` không mặc định bằng 0 trong SQL:

- `NULL` có thể nghĩa là giá trị **chưa biết**, không có dữ liệu hoặc không áp dụng.
- `0` là một **giá trị số xác định**.
- “Không có hàng” là vấn đề về **sự tồn tại của bản ghi**, chưa phải một giá trị số.

### 8.1. Mẫu bảo toàn thông tin đầy đủ hơn

Muốn biết một ngày có **bất kỳ đơn nào**, có bao nhiêu đơn paid và bao nhiêu đơn paid có amount được ghi nhận, hãy tổng hợp **toàn bộ trạng thái**:

```sql
WITH daily_all AS (
    SELECT
        ordered_on,
        COUNT(*) AS all_orders,
        COUNT(*) FILTER (
            WHERE status = 'paid'
        ) AS paid_orders,
        COUNT(amount) FILTER (
            WHERE status = 'paid'
        ) AS known_amounts,
        SUM(amount) FILTER (
            WHERE status = 'paid'
        ) AS paid_revenue
    FROM demo_orders_254
    GROUP BY ordered_on
)
SELECT
    c.calendar_date,
    COALESCE(d.all_orders, 0) AS all_orders,
    COALESCE(d.paid_orders, 0) AS paid_orders,
    COALESCE(d.known_amounts, 0) AS known_amounts,
    CASE
        WHEN COALESCE(d.paid_orders, 0) = 0
            THEN 0::numeric
        ELSE d.paid_revenue
    END AS paid_revenue
FROM demo_calendar_254 AS c
LEFT JOIN daily_all AS d
    ON d.ordered_on = c.calendar_date
ORDER BY c.calendar_date;
```

Kết quả:

| Ngày | Mọi đơn | Đơn paid | Paid có amount đã biết | Doanh thu paid |
| --- | ---: | ---: | ---: | ---: |
| 01/06 | 3 | 3 | 3 | 230 |
| 02/06 | 2 | 2 | 2 | 190 |
| 03/06 | 2 | 0 | 0 | 0 |
| 04/06 | 3 | 3 | 3 | 130 |
| 05/06 | 1 | 1 | 0 | `NULL` |
| 06/06 | 2 | 2 | 2 | 200 |
| 07/06 | 2 | 2 | 2 | 200 |
| 08/06 | 0 | 0 | 0 | 0 |

Mẫu này cho phép phân biệt rõ:

- 03/06: **có hai đơn**, nhưng không có paid.
- 08/06: **không có đơn nào**.
- 05/06: **có một đơn paid chưa biết amount**.

### 8.2. Gắn thêm cờ dữ liệu thiếu

```sql
WITH daily_all AS (
    SELECT
        ordered_on,
        COUNT(*) FILTER (WHERE status = 'paid') AS paid_orders,
        COUNT(amount) FILTER (WHERE status = 'paid') AS known_amounts,
        SUM(amount) FILTER (WHERE status = 'paid') AS paid_revenue
    FROM demo_orders_254
    GROUP BY ordered_on
)
SELECT
    c.calendar_date,
    COALESCE(d.paid_orders, 0) AS paid_orders,
    COALESCE(d.known_amounts, 0) AS known_amounts,
    COALESCE(d.paid_orders, 0)
       > COALESCE(d.known_amounts, 0) AS has_unknown_paid_amount,
    CASE
        WHEN COALESCE(d.paid_orders, 0) = 0
            THEN 0::numeric
        ELSE d.paid_revenue
    END AS paid_revenue
FROM demo_calendar_254 AS c
LEFT JOIN daily_all AS d
    ON d.ordered_on = c.calendar_date
ORDER BY c.calendar_date;
```

`has_unknown_paid_amount` chỉ `TRUE` ở ngày **05/06** trong bộ dữ liệu. Trên hệ thống thật, cờ chất lượng dữ liệu giúp dashboard không hiển thị một giá trị chưa hoàn chỉnh như doanh thu 0 chắc chắn.

## 9. Tạo lịch ngay trong truy vấn bằng generate_series

Không nhất thiết phải tạo bảng lịch vật lý. PostgreSQL có `generate_series` để sinh một dãy giá trị:

```sql
SELECT g.day_ts::date AS calendar_date
FROM generate_series(
    TIMESTAMP '2025-06-01',
    TIMESTAMP '2025-06-08',
    INTERVAL '1 day'
) AS g(day_ts)
ORDER BY calendar_date;
```

Kết quả là tám ngày từ 01/06 tới 08/06, **bao gồm cả hai đầu**.

Có thể dùng một CTE làm date spine:

```sql
WITH
date_spine AS (
    SELECT g.day_ts::date AS calendar_date
    FROM generate_series(
        TIMESTAMP '2025-06-01',
        TIMESTAMP '2025-06-08',
        INTERVAL '1 day'
    ) AS g(day_ts)
),
daily_paid AS (
    SELECT
        ordered_on,
        COUNT(*) AS paid_orders,
        SUM(amount) AS revenue
    FROM demo_orders_254
    WHERE status = 'paid'
    GROUP BY ordered_on
)
SELECT
    d.calendar_date,
    COALESCE(f.paid_orders, 0) AS paid_orders,
    CASE
        WHEN f.ordered_on IS NULL THEN 0::numeric
        ELSE f.revenue
    END AS revenue
FROM date_spine AS d
LEFT JOIN daily_paid AS f
    ON f.ordered_on = d.calendar_date
ORDER BY d.calendar_date;
```

Kết quả giống phần 5, không cần bảng `demo_calendar_254`.

### 9.1. Chọn bảng lịch vật lý hay sinh lịch động?

| Cách làm | Ưu điểm | Khi phù hợp |
| --- | --- | --- |
| **Bảng lịch lưu sẵn** | Tái sử dụng; có thể lưu tháng, kỳ tài chính, ngày nghỉ, ngày làm việc, nhãn hiển thị | Báo cáo và BI dùng chung quy tắc lịch |
| **CTE `generate_series`** | Ngắn; không cần quản lý bảng; phạm vi linh hoạt | Truy vấn ad hoc, dashboard đơn giản, test SQL |
| **CTE đệ quy sinh ngày** | Khả dụng ở DBMS không có `generate_series` tương đương | Hệ quản trị hỗ trợ recursive CTE |
| **Bảng số/tally table** | Tạo tập ngày qua cộng chỉ số vào ngày gốc | Hệ thống dùng bảng số có sẵn hoặc giới hạn recursive CTE |

Chọn theo nhu cầu. Với tổ chức có **lịch tài chính**, lịch vận hành hoặc nhiều quốc gia có ngày nghỉ khác nhau, một bảng calendar dimension được quản trị tập trung thường giúp bảo đảm quy tắc nhất quán.

### 9.2. Tạo lịch theo tham số bắt đầu và kết thúc

```sql
WITH params AS (
    SELECT
        DATE '2025-06-01' AS start_date,
        DATE '2025-06-08' AS end_date
)
SELECT g.day_ts::date AS calendar_date
FROM params AS p
CROSS JOIN LATERAL generate_series(
    p.start_date::timestamp,
    p.end_date::timestamp,
    INTERVAL '1 day'
) AS g(day_ts)
ORDER BY calendar_date;
```

Với bước dương một ngày, nếu `start_date > end_date`, `generate_series` không sinh hàng. Trong ứng dụng, nên xác thực khoảng ngày trước để phân biệt **phạm vi rỗng có chủ đích** với **tham số nhập sai**.

Số ngày sinh được có thể lớn; cần giới hạn khoảng thời gian hợp lý ở API để tránh một yêu cầu vô tình tạo lịch hàng trăm năm rồi nhân với nhiều chiều báo cáo.

## 10. Quy tắc ranh giới ngày: khoảng đóng trái, mở phải

Với bảng đã có cột kiểu `DATE`, có thể lọc:

```sql
WHERE ordered_on >= DATE '2025-06-01'
  AND ordered_on <  DATE '2025-06-09'
```

Khoảng này chứa **01/06 đến hết 08/06**.

Hình minh họa:

```text
2025-06-01                                   2025-06-09
    [---------------------------------------------)
    bao gồm điểm bắt đầu                 loại điểm kết thúc
```

Nếu muốn báo cáo từ ngày A tới ngày B **bao gồm B**, có thể dùng `>= A` và `< B + 1 day` khi kiểu và nghiệp vụ cho phép. Cách nửa mở này đặc biệt hữu ích với `TIMESTAMP` có phần lẻ giây, vì không cần đoán “thời điểm cuối ngày” chính xác là `23:59:59` hay `23:59:59.999999`.

### 10.1. Lọc dữ liệu trong phạm vi của lịch

```sql
WITH daily_paid AS (
    SELECT ordered_on, SUM(amount) AS revenue
    FROM demo_orders_254
    WHERE status = 'paid'
      AND ordered_on >= DATE '2025-06-01'
      AND ordered_on <  DATE '2025-06-09'
    GROUP BY ordered_on
)
SELECT
    c.calendar_date,
    CASE
        WHEN d.ordered_on IS NULL THEN 0::numeric
        ELSE d.revenue
    END AS revenue
FROM demo_calendar_254 AS c
LEFT JOIN daily_paid AS d
    ON d.ordered_on = c.calendar_date
WHERE c.calendar_date >= DATE '2025-06-01'
  AND c.calendar_date <  DATE '2025-06-09'
ORDER BY c.calendar_date;
```

Các bộ lọc ngày ở **calendar** xác định những ngày cần hiển thị. Các bộ lọc trên **fact** giới hạn số hàng cần tổng hợp, có thể giúp hiệu năng nếu được đặt đúng. Không dùng bộ lọc fact sau `LEFT JOIN` theo cách làm mất những ngày lịch không có hàng khớp.

### 10.2. Tránh ép TIMESTAMP thành DATE trong điều kiện lọc khi không cần

Giả sử bảng thực tế có `ordered_at TIMESTAMP`. Cách viết:

```sql
WHERE ordered_at::date = DATE '2025-06-01'
```

thường đặt một phép biến đổi lên cột thời gian; có thể khiến truy vấn khó dùng index thời gian thông thường hơn so với:

```sql
WHERE ordered_at >= TIMESTAMP '2025-06-01 00:00:00'
  AND ordered_at <  TIMESTAMP '2025-06-02 00:00:00'
```

Việc sử dụng index thực tế phụ thuộc optimizer và index được tạo, nhưng điều kiện khoảng thời gian trên cột gốc thường là điểm khởi đầu tốt. Sau khi lọc, có thể chuyển `ordered_at` sang ngày trong phần `SELECT/GROUP BY` theo ngữ nghĩa thời gian cần dùng.

## 11. Dữ liệu TIMESTAMPTZ và múi giờ nghiệp vụ

Nếu sự kiện được lưu dưới dạng `TIMESTAMPTZ` (mốc thời gian tuyệt đối), một “ngày” phải gắn với **múi giờ báo cáo**. Cùng một sự kiện có thể nằm vào ngày 31/05 theo UTC nhưng sang ngày 01/06 theo giờ Việt Nam.

Ví dụ:

```sql
SELECT
    TIMESTAMPTZ '2025-05-31 18:00:00+00'
        AT TIME ZONE 'UTC' AS utc_local_time,
    TIMESTAMPTZ '2025-05-31 18:00:00+00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh' AS vietnam_local_time;
```

Kết quả về ý nghĩa:

| Múi giờ | Ngày giờ |
| --- | --- |
| UTC | 2025-05-31 18:00 |
| Asia/Ho_Chi_Minh | 2025-06-01 01:00 |

Nếu báo cáo tính theo ngày Việt Nam, sự kiện này phải được đưa vào **01/06**, không phải 31/05.

### 11.1. Dữ liệu mẫu với thời điểm tuyệt đối

```sql
CREATE TEMP TABLE demo_events_tz_254 (
    event_id    INTEGER PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL,
    amount      NUMERIC(12, 2) NOT NULL
);

INSERT INTO demo_events_tz_254
    (event_id, occurred_at, amount)
VALUES
    (1, TIMESTAMPTZ '2025-05-31 18:00:00+00', 10),
    (2, TIMESTAMPTZ '2025-06-01 16:30:00+00', 20),
    (3, TIMESTAMPTZ '2025-06-01 17:30:00+00', 30);
```

Theo giờ Việt Nam:

- Event 1: **01/06 01:00**.
- Event 2: **01/06 23:30**.
- Event 3: **02/06 00:30**.

### 11.2. Lọc bằng ranh giới địa phương chuyển thành thời điểm tuyệt đối

```sql
WITH daily_local AS (
    SELECT
        (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
            AS local_date,
        SUM(amount) AS revenue
    FROM demo_events_tz_254
    WHERE occurred_at >= (
        TIMESTAMP '2025-06-01 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
      AND occurred_at < (
        TIMESTAMP '2025-06-09 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
    GROUP BY
        (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
)
SELECT
    c.calendar_date,
    COALESCE(d.revenue, 0::numeric) AS revenue
FROM demo_calendar_254 AS c
LEFT JOIN daily_local AS d
    ON d.local_date = c.calendar_date
ORDER BY c.calendar_date;
```

Kết quả:

| Ngày theo giờ Việt Nam | Tổng tiền |
| --- | ---: |
| 01/06 | 30 |
| 02/06 | 30 |
| 03/06–08/06 | 0 mỗi ngày |

Đầu vào `demo_events_tz_254.amount` được khai báo `NOT NULL`, nên trong ví dụ này có thể dùng `COALESCE(d.revenue,0)` để hiển thị 0 cho ngày không có sự kiện mà không làm mất thông tin số tiền chưa biết.

### 11.3. Vì sao không dùng timezone mặc định của kết nối?

Nếu chỉ viết:

```sql
occurred_at::date
```

trong PostgreSQL, ngày tạo ra có thể phụ thuộc **múi giờ phiên**. Hai phiên cùng đọc một `TIMESTAMPTZ` có thể phân sự kiện vào các ngày khác nhau nếu timezone khác.

Đặt múi giờ nghiệp vụ tường minh:

```sql
(occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
```

giúp báo cáo nhất quán. Đối với báo cáo toàn cầu, có thể phải có **mỗi người dùng hoặc mỗi khu vực một timezone**; lúc đó không thể dùng một khoảng UTC cố định cho mọi vùng mà vẫn gọi đó là cùng “ngày địa phương”.

### 11.4. Ngày lịch và DST

Ở những khu vực có thay đổi giờ mùa hè (*daylight saving time*), một ngày địa phương có thể dài **23 hoặc 25 giờ thực**. Vì thế, với dữ liệu `TIMESTAMPTZ`, nên dựng ranh giới **nửa đêm địa phương** của từng ngày rồi chuyển sang mốc thời gian tuyệt đối, thay vì giả định mọi ngày đều đúng 24 giờ UTC.

Ví dụ trong bài dùng `Asia/Ho_Chi_Minh`, nơi không có đổi giờ mùa hè hiện đại, nhưng ứng dụng nhiều quốc gia phải xét quy tắc địa phương và phiên bản dữ liệu múi giờ.

## 12. Bù ngày theo nhiều chiều: khu vực × kênh bán

Một báo cáo chỉ theo ngày có **8 hàng**. Nhưng một dashboard có thể cần một hàng cho **mỗi ngày, mỗi khu vực và mỗi kênh**:

```text
8 ngày × 2 khu vực × 2 kênh = 32 hàng
```

Nếu chỉ `GROUP BY ordered_on, region, channel` trên bảng giao dịch, những tổ hợp **không có đơn** vẫn biến mất. Chỉ nối theo ngày là chưa đủ nếu muốn bù cả các tổ hợp chiều.

Ta cần một **lưới dữ liệu đầy đủ** (*scaffold, dense grid*):

```text
Tập ngày      ×      Tập khu vực      ×      Tập kênh
8 hàng               North, South            Online, Store
                       ↓ CROSS JOIN
                 32 bộ khóa ngày–vùng–kênh
                       ↓ LEFT JOIN
                 Tổng hợp paid đúng ba khóa
```

### 12.1. Tạo lưới bằng CROSS JOIN

```sql
WITH
regions(region) AS (
    VALUES ('North'::text), ('South'::text)
),
channels(channel) AS (
    VALUES ('Online'::text), ('Store'::text)
),
grid AS (
    SELECT
        c.calendar_date,
        r.region,
        h.channel
    FROM demo_calendar_254 AS c
    CROSS JOIN regions AS r
    CROSS JOIN channels AS h
)
SELECT *
FROM grid
ORDER BY calendar_date, region, channel;
```

Lưới có đúng **32 hàng**. Nó chứa cả các cặp không có dữ liệu ngày hôm đó như **North–Store ngày 01/06** hoặc **South–Online ngày 06/06**.

### 12.2. Tổng hợp rồi LEFT JOIN theo đầy đủ ba khóa

```sql
WITH
regions(region) AS (
    VALUES ('North'::text), ('South'::text)
),
channels(channel) AS (
    VALUES ('Online'::text), ('Store'::text)
),
grid AS (
    SELECT c.calendar_date, r.region, h.channel
    FROM demo_calendar_254 AS c
    CROSS JOIN regions AS r
    CROSS JOIN channels AS h
),
daily_paid AS (
    SELECT
        ordered_on,
        region,
        channel,
        COUNT(*) AS paid_orders,
        COUNT(amount) AS known_amounts,
        SUM(amount) AS revenue
    FROM demo_orders_254
    WHERE status = 'paid'
    GROUP BY ordered_on, region, channel
)
SELECT
    g.calendar_date,
    g.region,
    g.channel,
    COALESCE(d.paid_orders, 0) AS paid_orders,
    COALESCE(d.known_amounts, 0) AS known_amounts,
    CASE
        WHEN d.ordered_on IS NULL THEN 0::numeric
        ELSE d.revenue
    END AS revenue
FROM grid AS g
LEFT JOIN daily_paid AS d
    ON d.ordered_on = g.calendar_date
   AND d.region = g.region
   AND d.channel = g.channel
ORDER BY g.calendar_date, g.region, g.channel;
```

Truy vấn dùng **đủ ba điều kiện nối**. Nếu bỏ `d.region = g.region` hoặc `d.channel = g.channel`, dữ liệu của nhóm này có thể được gắn nhầm sang nhóm khác hoặc nhân lên.

### 12.3. Đọc kết quả một số ngày

| Ngày | Khu vực | Kênh | Paid orders | Doanh thu |
| --- | --- | --- | ---: | ---: |
| 01/06 | North | Online | 2 | 150 |
| 01/06 | North | Store | 0 | 0 |
| 01/06 | South | Online | 0 | 0 |
| 01/06 | South | Store | 1 | 80 |
| 03/06 | North | Online | 0 | 0 |
| 03/06 | North | Store | 0 | 0 |
| 03/06 | South | Online | 0 | 0 |
| 03/06 | South | Store | 0 | 0 |
| 05/06 | North | Online | 1 | `NULL` |
| 05/06 | North | Store | 0 | 0 |
| 06/06 | North | Store | 1 | 90 |
| 06/06 | South | Store | 1 | 110 |
| 07/06 | North | Online | 1 | 130 |
| 07/06 | South | Online | 1 | 70 |

### 12.4. Đối soát tổng theo các chiều

Tổng tiền paid đã biết theo cặp:

| Khu vực | Kênh | Tổng số tiền đã biết |
| --- | --- | ---: |
| North | Online | 340 |
| North | Store | 160 |
| South | Online | 230 |
| South | Store | 220 |
| **Tổng** | | **950** |

Các phép đối soát:

```text
North: 340 + 160 = 500
South: 230 + 220 = 450
Online: 340 + 230 = 570
Store: 160 + 220 = 380

Toàn bộ: 500 + 450 = 570 + 380 = 950
```

Khi cộng, `SUM` bỏ qua giá trị `NULL` ngày 05/06. Báo cáo nên kèm số đơn có amount chưa biết để tránh diễn giải tổng 950 là tổng hoàn chỉnh.

## 13. Không phải lúc nào cũng nên tạo mọi tổ hợp chiều

`CROSS JOIN` tạo tích Descartes: số hàng tăng theo **tích số lượng giá trị mỗi chiều**.

Ví dụ:

```text
365 ngày × 100 khu vực × 50 kênh × 500 sản phẩm
= 912.500.000 tổ hợp
```

Nếu dashboard không thực sự cần gần một tỷ hàng, tạo lưới như vậy là lãng phí lớn.

### 13.1. Dùng tập cặp hợp lệ thay vì toàn bộ CROSS JOIN

Giả sử chỉ những cặp vùng–kênh đã được đăng ký hoạt động mới cần hiện diện. Một bảng danh mục cặp:

```sql
CREATE TEMP TABLE demo_active_region_channels_254 (
    region  TEXT NOT NULL,
    channel TEXT NOT NULL,
    PRIMARY KEY (region, channel)
);

INSERT INTO demo_active_region_channels_254
    (region, channel)
VALUES
    ('North', 'Online'),
    ('North', 'Store'),
    ('South', 'Online'),
    ('South', 'Store');
```

Sau đó tạo lưới:

```sql
SELECT
    c.calendar_date,
    rc.region,
    rc.channel
FROM demo_calendar_254 AS c
CROSS JOIN demo_active_region_channels_254 AS rc
ORDER BY c.calendar_date, rc.region, rc.channel;
```

Trong ví dụ vẫn có 32 hàng, nhưng hệ thống thực tế có thể chỉ giữ **những tổ hợp được phép và có ý nghĩa**. Không được lấy `SELECT DISTINCT region,channel FROM fact` thay cho bảng danh mục nếu cần hiển thị cả những tổ hợp chưa từng phát sinh giao dịch.

### 13.2. Cặp chỉ hoạt động trong một khoảng thời gian

Một cửa hàng có thể khai trương ngày 05/06. Không nên mặc định doanh thu của cửa hàng trước khi mở là “0 do không bán” nếu báo cáo muốn phân biệt **chưa vận hành** với **đã vận hành nhưng không có đơn**.

Bảng danh mục thực tế có thể chứa:

```text
(region, channel, active_from, active_to)
```

Khi tạo lưới, chỉ lấy các ngày thuộc khoảng hoạt động. Ví dụ về điều kiện khái niệm:

```sql
ON c.calendar_date >= rc.active_from
AND (
    rc.active_to IS NULL
    OR c.calendar_date < rc.active_to
)
```

Quy ước `active_to` **loại trừ** ngày kết thúc phải được ghi rõ. “Không có hàng vì chưa hoạt động” và “có hàng giá trị 0 vì không bán” là hai trạng thái nghiệp vụ khác nhau.

### 13.3. Có cần bù mọi sản phẩm không?

Nếu hệ thống có 100.000 sản phẩm, một báo cáo 365 ngày × sản phẩm có thể tạo 36,5 triệu hàng, ngay cả khi chỉ vài nghìn sản phẩm từng được bán.

Cân nhắc:

- Chỉ tạo sản phẩm thuộc danh mục đang theo dõi.
- Giới hạn những sản phẩm hoạt động trong kỳ.
- Bù ngày sau khi người dùng lọc một nhóm sản phẩm cụ thể.
- Tổng hợp trước ở cấp ngày–nhóm sản phẩm thay vì ngày–SKU nếu báo cáo chỉ cần cấp nhóm.
- Trả dữ liệu thưa (*sparse*) cho biểu đồ khi giao diện có thể tự diễn giải 0 theo lịch rõ ràng.

Bù ngày là một **quyết định về grain của báo cáo**, không phải mệnh lệnh tạo mọi tổ hợp có thể tưởng tượng.

## 14. Tạo một bảng lịch chuẩn dùng nhiều lần

Trong hệ thống phân tích, bảng lịch lưu sẵn có thể được xây dựng trước với khóa ngày và các thuộc tính:

```sql
-- Ví dụ cấu trúc đơn giản, dùng khi thiết kế schema thật:
CREATE TABLE dim_calendar (
    calendar_date DATE PRIMARY KEY,
    calendar_year INTEGER NOT NULL,
    calendar_month INTEGER NOT NULL,
    iso_weekday INTEGER NOT NULL,
    is_weekend BOOLEAN NOT NULL
);
```

Có thể thêm những trường được quản trị theo chính sách:

- `iso_week`, `iso_year` để báo cáo theo tuần ISO.
- `quarter`, `month_start`, `week_start`.
- `fiscal_year`, `fiscal_period` theo lịch tài chính của doanh nghiệp.
- `is_business_day`, `is_public_holiday` theo quốc gia/khu vực.
- `business_day_number_in_month` hoặc `prior_business_day` cho nghiệp vụ ngân hàng.
- Nhãn tháng, thứ, kỳ báo cáo cho BI.

Các trường **ngày nghỉ**, **năm tài chính** và **ngày làm việc** không thể luôn suy ra từ phép cộng ngày đơn giản; chúng cần dữ liệu và quy tắc được phê duyệt.

### 14.1. Một hàng cho một ngày

Khóa chính `calendar_date` bảo đảm không có hai hàng lịch trùng ngày:

```sql
CREATE TABLE dim_calendar (
    calendar_date DATE PRIMARY KEY,
    ...
);
```

Nếu bảng lịch có hai hàng cho cùng ngày, một `LEFT JOIN` có thể nhân đôi tổng tiền ngày đó. Vì vậy, tính duy nhất của ngày lịch là điều kiện nền tảng của mô hình.

### 14.2. Lịch phải bao phủ toàn bộ khoảng truy vấn

Nếu người dùng yêu cầu tới 31/12 nhưng bảng lịch chỉ có dữ liệu đến 30/11, kết quả vẫn thiếu các ngày tháng 12 — lần này lỗi nằm ở **lịch**, không phải bảng fact.

Trong vận hành, có thể thiết kế công việc mở rộng lịch theo năm, kiểm tra phạm vi tối thiểu/tối đa và giám sát số ngày bị thiếu trong calendar dimension. Một bảng lịch đủ rộng và đúng quy tắc cần được coi như một phần tài sản dữ liệu chung.

## 15. Bù ngày xong mới tính tổng lũy kế hoặc trung bình trượt

Một lợi ích quan trọng của date spine là cho phép window function chạy trên **một hàng mỗi ngày**, kể cả ngày trống.

Trước tiên, tạo chuỗi đã bù ngày rồi mới tính:

```sql
WITH daily_paid AS (
    SELECT
        ordered_on,
        COUNT(*) AS paid_orders,
        SUM(amount) AS revenue
    FROM demo_orders_254
    WHERE status = 'paid'
    GROUP BY ordered_on
),
filled_days AS (
    SELECT
        c.calendar_date,
        COALESCE(d.paid_orders, 0) AS paid_orders,
        CASE
            WHEN d.ordered_on IS NULL THEN 0::numeric
            ELSE d.revenue
        END AS revenue
    FROM demo_calendar_254 AS c
    LEFT JOIN daily_paid AS d
      ON d.ordered_on = c.calendar_date
)
SELECT
    calendar_date,
    paid_orders,
    revenue,
    SUM(revenue) OVER (
        ORDER BY calendar_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_known_revenue,
    ROUND(
        AVG(revenue) OVER (
            ORDER BY calendar_date
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ),
        2
    ) AS avg_recent_3_calendar_days
FROM filled_days
ORDER BY calendar_date;
```

Kết quả:

| Ngày | Doanh thu | Lũy kế phần đã biết | AVG tối đa 3 ngày lịch gần nhất |
| --- | ---: | ---: | ---: |
| 01/06 | 230 | 230 | 230.00 |
| 02/06 | 190 | 420 | 210.00 |
| 03/06 | 0 | 420 | 140.00 |
| 04/06 | 130 | 550 | 106.67 |
| 05/06 | `NULL` | 550 | 65.00 |
| 06/06 | 200 | 750 | 165.00 |
| 07/06 | 200 | 950 | 200.00 |
| 08/06 | 0 | 950 | 133.33 |

Giải thích một số hàng:

- 03/06, ba ngày đầu: `(230+190+0)/3 = 140`.
- 04/06, ba ngày 02–04/06: `(190+0+130)/3 ≈ 106.67`.
- 05/06, ba ngày 03–05/06 chứa `[0,130,NULL]`; `AVG` bỏ qua `NULL` nên trả `130/2 = 65`.
- 06/06, ba ngày 04–06/06 chứa `[130,NULL,200]` nên `AVG = 330/2 = 165`.
- 08/06, ba ngày 06–08/06 chứa `[200,200,0]` nên `AVG ≈ 133.33`.

**Cảnh báo ngữ nghĩa:** `SUM` và `AVG` ở đây bỏ qua `NULL` của ngày 05/06. Chúng mô tả **phần doanh thu đã biết**, không chứng minh một tổng chắc chắn đầy đủ.

### 15.1. Cờ số liệu chưa hoàn chỉnh trong lũy kế

Nếu cần biết lũy kế đã gặp ngày có số tiền không xác định chưa:

```sql
WITH daily_paid AS (
    SELECT ordered_on, COUNT(*) AS paid_orders,
           SUM(amount) AS revenue
    FROM demo_orders_254
    WHERE status = 'paid'
    GROUP BY ordered_on
),
filled AS (
    SELECT
        c.calendar_date,
        CASE
            WHEN d.ordered_on IS NULL THEN 0::numeric
            ELSE d.revenue
        END AS revenue
    FROM demo_calendar_254 AS c
    LEFT JOIN daily_paid AS d
      ON d.ordered_on = c.calendar_date
)
SELECT
    calendar_date,
    SUM(revenue) OVER (
        ORDER BY calendar_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS known_running_total,
    COUNT(*) FILTER (
        WHERE revenue IS NULL
    ) OVER (
        ORDER BY calendar_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS unknown_days_so_far
FROM filled
ORDER BY calendar_date;
```

`unknown_days_so_far` bằng **0** tới 04/06 và bằng **1** từ 05/06 trở đi. Người đọc có thể được cảnh báo rằng tổng lũy kế sau đó chưa đầy đủ.

### 15.2. Có cần chính xác “ba ngày” ở đầu chuỗi?

`ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` tại 01/06 chỉ có **một hàng**, tại 02/06 có **hai hàng**. Vì vậy `AVG` chia cho 1 hoặc 2 ở đầu kỳ.

Nếu nghiệp vụ bắt buộc **đủ ba ngày** mới hiển thị trung bình, cần thêm điều kiện kiểm tra số ngày trong frame và quy tắc xử lý `NULL`, hoặc tạo thêm hai ngày trước ngày hiển thị để cửa sổ có đủ lịch sử.

Bù ngày trong **khoảng hiển thị** chưa chắc đã đủ dữ liệu nền cho những chỉ số cần quá khứ trước đầu kỳ.

## 16. Đếm ngày có hoạt động, ngày không có paid và tỷ lệ hoạt động

Sau khi tạo dãy ngày đầy đủ, ta có thể đếm số ngày thay vì chỉ số giao dịch.

### 16.1. Hai loại “ngày trống” cần phân biệt

Dùng `daily_all` ở phần 8:

```sql
WITH daily_all AS (
    SELECT
        ordered_on,
        COUNT(*) AS all_orders,
        COUNT(*) FILTER (WHERE status = 'paid') AS paid_orders
    FROM demo_orders_254
    GROUP BY ordered_on
),
filled AS (
    SELECT
        c.calendar_date,
        COALESCE(d.all_orders, 0) AS all_orders,
        COALESCE(d.paid_orders, 0) AS paid_orders
    FROM demo_calendar_254 AS c
    LEFT JOIN daily_all AS d
      ON d.ordered_on = c.calendar_date
)
SELECT
    COUNT(*) AS calendar_days,
    COUNT(*) FILTER (WHERE all_orders = 0) AS days_without_any_order,
    COUNT(*) FILTER (WHERE paid_orders = 0) AS days_without_paid_order,
    COUNT(*) FILTER (WHERE paid_orders > 0) AS days_with_paid_order
FROM filled;
```

Kết quả:

| Calendar days | Không có đơn nào | Không có đơn paid | Có đơn paid |
| ---: | ---: | ---: | ---: |
| 8 | 1 | 2 | 6 |

Ngày 08/06 là ngày **không có đơn nào**. Ngày 03/06 và 08/06 là hai ngày **không có đơn paid**. Sáu ngày còn lại có ít nhất một paid, dù 05/06 có amount chưa biết.

### 16.2. Tỷ lệ ngày có ít nhất một đơn paid

```sql
WITH daily_paid AS (
    SELECT ordered_on, COUNT(*) AS paid_orders
    FROM demo_orders_254
    WHERE status = 'paid'
    GROUP BY ordered_on
)
SELECT
    COUNT(*) AS days_in_period,
    COUNT(d.ordered_on) AS days_with_paid_orders,
    ROUND(
        100.0 * COUNT(d.ordered_on)
        / NULLIF(COUNT(*), 0),
        2
    ) AS paid_day_rate_pct
FROM demo_calendar_254 AS c
LEFT JOIN daily_paid AS d
    ON d.ordered_on = c.calendar_date;
```

Kết quả: có **6 ngày paid trên 8 ngày**, tỷ lệ **75.00%**.

Nếu dùng bảng nguồn không bù ngày, đếm số ngày từ dữ liệu paid chỉ thấy sáu ngày và không tự biết **mẫu số phải là tám**. Đây là một trong những lý do date spine quan trọng khi tính KPI theo số ngày.

### 16.3. Ngày làm việc hay ngày lịch?

Bảng `demo_calendar_254` có `is_weekend`, nên một báo cáo có thể chỉ xét ngày làm việc:

```sql
SELECT calendar_date
FROM demo_calendar_254
WHERE NOT is_weekend
ORDER BY calendar_date;
```

Trong ví dụ, các ngày làm việc theo quy tắc “thứ Hai tới thứ Sáu” là **02/06–06/06**, tổng cộng năm ngày.

Tuy nhiên, “ngày làm việc” ở một doanh nghiệp không luôn đồng nghĩa “không phải cuối tuần”: có ngày lễ, nghỉ bù, ca vận hành và lịch quốc gia. Với báo cáo thực tế, hãy dùng calendar dimension phản ánh đúng **lịch nghiệp vụ**, không chỉ `EXTRACT(ISODOW)`.

## 17. Tìm chính xác những ngày thiếu dữ liệu

Đôi khi yêu cầu không phải bù số 0 để vẽ biểu đồ, mà là **liệt kê những ngày chưa có bản ghi** để kiểm tra hệ thống nhập liệu.

### 17.1. Ngày không có bất kỳ giao dịch nào

```sql
SELECT c.calendar_date
FROM demo_calendar_254 AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM demo_orders_254 AS o
    WHERE o.ordered_on = c.calendar_date
)
ORDER BY c.calendar_date;
```

Kết quả: **08/06**.

`NOT EXISTS` ở đây diễn đạt **phản kết nối**: tìm các ngày lịch không có hàng giao dịch nào tương ứng.

### 17.2. Ngày không có giao dịch paid

```sql
SELECT c.calendar_date
FROM demo_calendar_254 AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM demo_orders_254 AS o
    WHERE o.ordered_on = c.calendar_date
      AND o.status = 'paid'
)
ORDER BY c.calendar_date;
```

Kết quả: **03/06 và 08/06**.

Ngày 03/06 vẫn có đơn pending/cancelled nhưng thỏa yêu cầu “không có paid”. Đây là một câu hỏi khác với “không có giao dịch nào”.

### 17.3. Ngày có paid nhưng mọi amount đều thiếu

```sql
SELECT
    ordered_on,
    COUNT(*) AS paid_orders,
    COUNT(amount) AS known_amounts
FROM demo_orders_254
WHERE status = 'paid'
GROUP BY ordered_on
HAVING COUNT(*) > 0
   AND COUNT(amount) = 0
ORDER BY ordered_on;
```

Kết quả: **05/06**.

Truy vấn này không cần bảng lịch vì nó tìm những **nhóm ngày có giao dịch paid thật**, nhưng không có amount nào đã biết. Tách loại lỗi dữ liệu này khỏi ngày không có giao dịch giúp xác định chính xác nguyên nhân.

### 17.4. LEFT JOIN ... IS NULL thay cho NOT EXISTS

```sql
SELECT c.calendar_date
FROM demo_calendar_254 AS c
LEFT JOIN demo_orders_254 AS o
    ON o.ordered_on = c.calendar_date
   AND o.status = 'paid'
WHERE o.order_id IS NULL
ORDER BY c.calendar_date;
```

Câu trên cũng trả **03/06 và 08/06**. `o.order_id` là khóa chính, bảo đảm không `NULL` ở hàng đơn thật; vì vậy `IS NULL` là dấu hiệu không có hàng phải khớp.

Khi chỉ muốn danh sách ngày thiếu, `NOT EXISTS` thường diễn đạt ý định trực tiếp. Khi muốn hiển thị **mọi ngày kèm các chỉ số**, `LEFT JOIN` phù hợp hơn.

## 18. Không tạo ngày từ chính bảng cần bù

Một cách làm dễ sai là lấy:

```sql
SELECT DISTINCT ordered_on
FROM demo_orders_254;
```

rồi dùng danh sách đó làm “lịch”. Danh sách sẽ **không có 08/06**, vì ngày này vốn không có giao dịch. Nếu chỉ lấy đơn paid, danh sách còn **mất cả 03/06**.

Tập dùng làm date spine phải đến từ một **nguồn độc lập**:

- Bảng lịch đầy đủ.
- `generate_series` trên hai đầu mốc.
- Recursive CTE được giới hạn.
- Tally table hoặc bảng ngày chuẩn của hệ thống.

**Không thể kỳ vọng một danh sách ngày sinh từ dữ liệu thưa sẽ tự chứa những ngày mà dữ liệu thưa không có.**

### 18.1. MIN(date) và MAX(date) có thể bỏ các ngày biên

Một thủ thuật là:

```sql
SELECT MIN(ordered_on), MAX(ordered_on)
FROM demo_orders_254;
```

Trong dữ liệu mẫu: min là 01/06, max là 07/06. Nếu tự sinh lịch giữa min và max, vẫn **mất 08/06**, mặc dù báo cáo yêu cầu tới ngày đó.

Hai đầu của date spine phải xuất phát từ **tham số kỳ báo cáo**, không tự suy ra từ lần có giao dịch đầu/cuối, trừ khi nghiệp vụ thực sự muốn phạm vi dữ liệu quan sát được.

### 18.2. Ngày tương lai có nên tự bù bằng 0?

Nếu báo cáo tháng đang chạy, việc sinh lịch tới cuối tháng sẽ tạo những ngày **chưa xảy ra**. Hiển thị doanh thu tương lai bằng 0 có thể làm giảm sai tỷ lệ trung bình ngày hoặc chuyển đổi KPI.

Nên làm rõ:

- Báo cáo chỉ tới **ngày đã kết thúc** hay tới **ngày hiện tại**?
- Các ngày tương lai được **ẩn**, **hiển thị riêng như chưa tới kỳ**, hay thực sự tính là 0?
- Múi giờ nào xác định “ngày hôm nay”?
- Dữ liệu có độ trễ nhập khiến ngày đã qua nhưng chưa hoàn chỉnh không?

Một cách là dùng cột `report_date` hoặc `as_of_date` làm tham số được xác định tại thời điểm chạy báo cáo, thay vì mặc định toàn bộ lịch tương lai là không bán hàng.

## 19. Tránh nhân số tiền khi kết nối nhiều bảng

Dù đã có bảng lịch đầy đủ, số tiền có thể sai nếu phía sự kiện bị **nhân hàng** bởi các phép nối trước khi tổng hợp.

Giả sử bảng đơn có một hàng trên mỗi đơn, còn bảng chi tiết có ba dòng sản phẩm của cùng đơn. Nếu viết:

```sql
-- Ví dụ cấu trúc, không có bảng order_items trong dataset mẫu:
SELECT
    o.ordered_on,
    SUM(o.amount) AS wrong_revenue
FROM orders AS o
JOIN order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY o.ordered_on;
```

một `o.amount` đại diện **tổng tiền của đơn** có thể bị cộng **ba lần** khi đơn có ba dòng chi tiết. Sau đó `LEFT JOIN` với lịch vẫn trả đủ ngày, nhưng doanh thu đã sai.

Cách thiết kế đúng tùy grain:

- Nếu `o.amount` là tổng tiền của một đơn, tổng hợp từ **một hàng trên mỗi đơn** mà không nhân nó qua bảng chi tiết.
- Nếu doanh thu được tính từ dòng sản phẩm, dùng `SUM(oi.line_amount)` trên grain dòng sản phẩm phù hợp, và bảo đảm mỗi dòng có quan hệ đúng.
- Nếu cần điều kiện “đơn có sản phẩm X”, có thể dùng `EXISTS` để lọc đơn mà không nhân hàng đơn theo số dòng khớp.
- Nếu phải JOIN, kiểm soát khóa và số hàng sau phép nối trước khi cộng.

### 19.1. Hai chiều khác nhau có thể tạo tổng chồng lấp

Nếu một đơn được gán đồng thời cho hai chiến dịch marketing, nối đơn vào bảng chiến dịch rồi tổng hợp theo chiến dịch sẽ làm số tiền của đơn có thể xuất hiện trong **hai nhóm**. Đây có thể là ý nghĩa mong muốn nếu báo cáo “doanh thu có liên quan đến từng chiến dịch”, nhưng **không** có nghĩa tổng doanh thu theo mọi chiến dịch phải bằng tổng tiền đơn.

Bù ngày không sửa được lỗi định nghĩa phép đo. Trước tiên phải xác định **mỗi hàng đại diện cho gì**, sau đó mới dựng lịch.

## 20. Khi số liệu theo tháng, tuần hoặc giờ

Date spine là một dạng cụ thể của **scaffold theo trục thời gian**. Cùng ý tưởng áp dụng cho tuần, tháng hoặc giờ, nhưng ranh giới và quy tắc bù phải rõ ràng.

### 20.1. Tháng: sinh đầu tháng

Trong PostgreSQL:

```sql
SELECT g.month_start::date AS month_start
FROM generate_series(
    TIMESTAMP '2025-01-01',
    TIMESTAMP '2025-12-01',
    INTERVAL '1 month'
) AS g(month_start)
ORDER BY month_start;
```

Kết quả có 12 mốc đầu tháng. Có thể tổng hợp giao dịch theo:

```sql
DATE_TRUNC('month', ordered_on::timestamp)::date
```

rồi nối với `month_start` của spine.

Để tránh những tình huống cộng tháng từ ngày 29, 30 hoặc 31 làm đổi ngày không như mong đợi, khi tạo monthly spine nên dùng **đầu tháng** làm điểm xuất phát.

### 20.2. Tuần: phải định nghĩa đầu tuần và năm tuần

PostgreSQL có thể dùng `DATE_TRUNC('week', timestamp)` cho mốc đầu tuần theo quy tắc mà hệ quản trị áp dụng. Nhưng báo cáo nghiệp vụ có thể dùng tuần bắt đầu Chủ nhật hoặc tuần tài chính riêng.

Nếu một dashboard dùng **ISO week**, cần xử lý cả **năm ISO**, vì tuần ISO ở đầu tháng 1 có thể thuộc ISO year trước. Một calendar dimension chuẩn thường giảm nhầm lẫn so với ghép số tuần với năm lịch đơn giản.

### 20.3. Giờ: nhiều vấn đề về múi giờ và DST hơn

Sinh hàng theo từng giờ UTC thường đơn giản hơn, nhưng khi hiển thị theo giờ địa phương:

- Một ngày có DST bắt đầu có thể **thiếu một giờ địa phương**.
- Một ngày DST kết thúc có thể **lặp một nhãn giờ địa phương**.
- Nhãn `2025-... 01:00` không đủ xác định thời điểm nếu giờ đó xảy ra hai lần ở hai offset khác nhau.

Với báo cáo giờ, cần lưu khóa thời điểm tuyệt đối hoặc khóa bao gồm múi giờ/offset đủ rõ. Không nên tái sử dụng máy móc kỹ thuật `DATE` cho cửa sổ theo giờ mà bỏ qua vấn đề này.

## 21. Cách viết tương đương trên các hệ quản trị SQL

Ý tưởng **lịch đầy đủ + `LEFT JOIN` với aggregate theo ngày** dùng được rộng rãi, nhưng cách **sinh lịch** khác nhau theo DBMS.

### 21.1. PostgreSQL: generate_series

```sql
WITH date_spine AS (
    SELECT g.day_ts::date AS calendar_date
    FROM generate_series(
        TIMESTAMP '2025-06-01',
        TIMESTAMP '2025-06-08',
        INTERVAL '1 day'
    ) AS g(day_ts)
)
SELECT calendar_date
FROM date_spine
ORDER BY calendar_date;
```

Đây là cách ngắn gọn trong PostgreSQL. Với lịch lưu sẵn, thay CTE bằng bảng calendar dimension.

### 21.2. SQL Server: recursive CTE

```sql
-- SQL Server:
WITH date_spine(calendar_date) AS (
    SELECT CONVERT(date, '2025-06-01')

    UNION ALL

    SELECT DATEADD(day, 1, calendar_date)
    FROM date_spine
    WHERE calendar_date < CONVERT(date, '2025-06-08')
)
SELECT calendar_date
FROM date_spine
ORDER BY calendar_date
OPTION (MAXRECURSION 100);
```

SQL Server dùng `WITH` cho CTE đệ quy, không cần từ khóa `RECURSIVE`. `OPTION (MAXRECURSION 100)` là lớp giới hạn bảo vệ; không thay thế điều kiện dừng trong CTE. Khoảng rất dài có thể cần ngưỡng khác hoặc dùng một bảng ngày/tally table đã được tối ưu.

### 21.3. MySQL 8.0+: recursive CTE

```sql
-- MySQL 8.0+:
WITH RECURSIVE date_spine AS (
    SELECT DATE('2025-06-01') AS calendar_date

    UNION ALL

    SELECT DATE_ADD(calendar_date, INTERVAL 1 DAY)
    FROM date_spine
    WHERE calendar_date < DATE('2025-06-08')
)
SELECT calendar_date
FROM date_spine
ORDER BY calendar_date;
```

MySQL có cấu hình giới hạn số lần đệ quy như `cte_max_recursion_depth`; khoảng sinh ngày dài phải xét phiên bản và cấu hình.

### 21.4. SQLite: recursive CTE

```sql
-- SQLite:
WITH RECURSIVE date_spine(calendar_date) AS (
    VALUES ('2025-06-01')

    UNION ALL

    SELECT date(calendar_date, '+1 day')
    FROM date_spine
    WHERE calendar_date < '2025-06-08'
)
SELECT calendar_date
FROM date_spine
ORDER BY calendar_date;
```

SQLite lưu biểu diễn ngày linh hoạt hơn các DBMS có kiểu `DATE` chuyên dụng. Trong ví dụ, ngày dạng chuỗi ISO `YYYY-MM-DD` giúp thứ tự từ điển tương ứng thứ tự ngày; cần quản lý định dạng thống nhất.

### 21.5. Oracle Database: CONNECT BY

```sql
-- Oracle Database:
SELECT DATE '2025-06-01' + LEVEL - 1 AS calendar_date
FROM dual
CONNECT BY LEVEL <= 8
ORDER BY calendar_date;
```

`LEVEL` bắt đầu ở 1; cộng `LEVEL - 1` tạo các ngày từ 01/06 đến 08/06. Đây là một cách của Oracle; hệ thống dùng lịch vật lý hoặc recursive subquery factoring cũng có thể phù hợp.

### 21.6. So sánh nhanh

| Hệ quản trị | Cách sinh lịch thường dùng | Điều cần kiểm tra |
| --- | --- | --- |
| PostgreSQL | `generate_series`, calendar table | Kiểu `timestamp/timestamptz`, timezone, interval |
| SQL Server | Recursive CTE, tally/numbers table, calendar dimension | `MAXRECURSION`, kiểu date/datetime |
| MySQL 8.0+ | `WITH RECURSIVE`, calendar dimension | Ngưỡng recursion, cú pháp `DATE_ADD` |
| SQLite | Recursive CTE, bảng ngày | Biểu diễn ngày ISO, giới hạn CTE |
| Oracle | `CONNECT BY LEVEL`, recursive subquery factoring, bảng ngày | Cú pháp `DATE`/`TIMESTAMP` và định dạng |
| Kho dữ liệu phân tích | Calendar dimension hoặc hàm sinh mảng/chuỗi ngày | Hàm cụ thể phụ thuộc engine, chi phí mở rộng |

**Không nên đổi toàn bộ cú pháp PostgreSQL sang một hệ khác mà không kiểm tra**, đặc biệt ở phần ép kiểu ngày, timezone, recursive CTE và `FILTER (WHERE ...)` trên aggregate. Phần cốt lõi `LEFT JOIN calendar → daily aggregate` vẫn là mô hình chung.

## 22. Hiệu năng: lọc đúng phạm vi, tổng hợp đúng grain, hạn chế lưới

### 22.1. Chỉ tổng hợp đúng khoảng thời gian cần dùng

Đối với bảng nhiều triệu giao dịch:

```sql
WITH daily_paid AS (
    SELECT ordered_on, SUM(amount) AS revenue
    FROM demo_orders_254
    WHERE status = 'paid'
      AND ordered_on >= DATE '2025-06-01'
      AND ordered_on <  DATE '2025-06-09'
    GROUP BY ordered_on
)
SELECT ...
```

Bộ lọc thời gian có thể giảm số hàng được đưa vào `GROUP BY`. Khi dùng cột `TIMESTAMP`, nên lọc bằng khoảng thời gian rõ ràng, tránh áp dụng hàm lên cột trong `WHERE` nếu không cần.

### 22.2. Index cho bảng lịch và bảng fact

Khóa chính:

```sql
calendar_date DATE PRIMARY KEY
```

bảo đảm một hàng mỗi ngày và thường đi kèm index phù hợp.

Với bảng giao dịch lớn được lọc theo ngày và trạng thái, một index có thể xem xét:

```sql
CREATE INDEX idx_demo_orders_254_date_status
ON demo_orders_254 (ordered_on, status);
```

Hoặc nếu các truy vấn chủ yếu dùng `status='paid'` trong PostgreSQL:

```sql
CREATE INDEX idx_demo_orders_254_paid_date
ON demo_orders_254 (ordered_on)
WHERE status = 'paid';
```

Tùy truy vấn và phân bố, index theo `(status, ordered_on)` cũng có thể thích hợp. Không có một thứ tự index luôn tối ưu cho mọi bộ lọc. Trên bảng mẫu 15 hàng, quét tuần tự có thể rẻ hơn; cần xem kế hoạch thực thi trên khối lượng gần production.

### 22.3. EXPLAIN trên truy vấn bù ngày

```sql
EXPLAIN (ANALYZE, BUFFERS)
WITH daily_paid AS (
    SELECT ordered_on, SUM(amount) AS revenue
    FROM demo_orders_254
    WHERE status = 'paid'
    GROUP BY ordered_on
)
SELECT c.calendar_date, d.revenue
FROM demo_calendar_254 AS c
LEFT JOIN daily_paid AS d
    ON d.ordered_on = c.calendar_date
ORDER BY c.calendar_date;
```

Trong PostgreSQL, kế hoạch có thể có bước aggregate và một phương án join như hash join hoặc nested loop, phụ thuộc thống kê. `EXPLAIN ANALYZE` **thực sự chạy** truy vấn đọc để thu số liệu thời gian; khi dùng trên hệ thống production phải cân nhắc tải.

### 22.4. Ước lượng số hàng trước khi dựng lưới

Tính nhanh:

```text
Số hàng date spine đơn = số ngày

Số hàng ngày × vùng × kênh
= số ngày × số vùng × số kênh

Nếu chỉ dùng cặp hợp lệ:
= số ngày × số cặp hợp lệ
```

Nếu vùng/kênh có ngày bắt đầu hoặc kết thúc hoạt động, số hàng thực sẽ nhỏ hơn tích đầy đủ. Cần ước tính trước thay vì vô tình đưa hàng chục triệu hàng rỗng lên dashboard.

### 22.5. Bảng tổng hợp ngày có thể được lưu trước

Nếu nhiều dashboard cùng tính doanh thu ngày từ hàng trăm triệu giao dịch, có thể duy trì bảng summary ở grain:

```text
(order_date, region, channel) → paid_orders, known_amounts, revenue
```

Sau đó `LEFT JOIN` bảng lịch hoặc lưới với summary.

Cần quản lý **giao dịch nhập trễ, thay đổi trạng thái, hủy đơn, hoàn tiền và số tiền chưa biết được bổ sung**. Bảng tổng hợp lưu trước có thể trở nên cũ nếu chỉ cộng thêm đơn mới mà không xử lý sửa/xóa dữ liệu nguồn.

## 23. Những lỗi thường gặp

| Lỗi | Vì sao sai | Cách đúng |
| --- | --- | --- |
| `GROUP BY date` rồi `COALESCE(SUM(...),0)` và mong có đủ ngày | COALESCE không tạo hàng chưa có | Tạo lịch độc lập rồi `LEFT JOIN` |
| Sinh lịch từ `SELECT DISTINCT date FROM fact` | Ngày thiếu vốn không có trong fact | Dùng calendar dimension hoặc generate_series |
| Dùng `MIN(date)`/`MAX(date)` của fact làm ranh giới mặc định | Có thể bỏ ngày đầu/cuối kỳ chưa có dữ liệu | Lấy đầu/cuối từ yêu cầu báo cáo |
| Đặt bảng fact bên trái của `LEFT JOIN` | Bên được bảo toàn là tập dữ liệu thưa | Đặt lịch bên trái |
| Đặt `fact.status='paid'` ở `WHERE` sau `LEFT JOIN` | Loại những hàng lịch không có paid | Lọc trong `ON` hoặc aggregate CTE trước |
| Dùng `WHERE status='paid' OR fact_id IS NULL` sau join fact thô | Ngày chỉ có pending/cancelled không có hàng NULL mở rộng | Lọc paid trước khi nối |
| Dùng `COUNT(*)` sau `LEFT JOIN` để đếm đơn | Một ngày không khớp vẫn có một hàng mở rộng | `COUNT(fact.order_id)` hoặc count ở CTE |
| `COALESCE(SUM(amount),0)` mọi trường hợp | Biến ngày có paid nhưng amount thiếu thành số 0 | Phân biệt không có nhóm với nhóm có amount `NULL` |
| Nối lịch vào bảng chi tiết nhiều dòng rồi `SUM(order.amount)` | Nhân tổng tiền theo số dòng chi tiết | Tổng hợp trên đúng grain trước |
| Chỉ join theo ngày cho báo cáo ngày–khu vực–kênh | Các chiều có thể bị nhân hoặc gắn sai | Nối theo tất cả khóa grain |
| CROSS JOIN mọi chiều không giới hạn | Số hàng bằng tích các giá trị, có thể rất lớn | Chọn phạm vi và cặp hoạt động |
| Dùng `ROWS 2 PRECEDING` trên bảng ngày không liên tục và gọi là “ba ngày lịch” | Thực ra chọn ba ngày **có hàng** | Bù lịch trước rồi mới dùng ROWS |
| Bù ngày tương lai bằng 0 vô điều kiện | Ngày chưa tới bị hiểu là ngày không bán | Thêm tham số as-of/trạng thái kỳ |
| Nhóm `timestamptz::date` không xác định timezone | Ngày có thể thay đổi theo timezone phiên | Dùng múi giờ nghiệp vụ tường minh |
| Dùng `BETWEEN ... 23:59:59` cho timestamp | Bỏ sự kiện có phần lẻ giây cuối ngày | Dùng khoảng nửa mở `>= start AND < next_day` |
| Cho rằng ngày không có fact nghĩa là doanh thu thực 0 | Có thể dữ liệu nhập trễ hoặc quy trình lỗi | Dùng cờ độ hoàn chỉnh, kiểm soát chất lượng |
| Bảng lịch có trùng ngày | LEFT JOIN nhân bản số liệu | Khóa duy nhất trên calendar_date |

## 24. Bài tập thực hành kèm đáp án

Các bài sử dụng hai bảng `demo_orders_254` và `demo_calendar_254`, trừ khi ghi rõ dữ liệu khác. Mỗi câu hỏi nên được dự đoán bằng tay trước khi chạy.

### Bài 1 — GROUP BY tạo bao nhiêu hàng ngày?

```sql
SELECT ordered_on, COUNT(*) AS paid_orders
FROM demo_orders_254
WHERE status = 'paid'
GROUP BY ordered_on
ORDER BY ordered_on;
```

**Đáp án:** **6 hàng ngày**, tương ứng 01, 02, 04, 05, 06, 07/06. Ngày 03 và 08/06 không có đơn paid nên không có nhóm.

### Bài 2 — Calendar có bao nhiêu ngày?

```sql
SELECT COUNT(*) FROM demo_calendar_254;
```

**Đáp án:** **8** ngày, từ 01/06 tới 08/06.

### Bài 3 — Hai ngày không có paid

```sql
SELECT c.calendar_date
FROM demo_calendar_254 AS c
WHERE NOT EXISTS (
    SELECT 1 FROM demo_orders_254 AS o
    WHERE o.ordered_on = c.calendar_date
      AND o.status = 'paid'
)
ORDER BY c.calendar_date;
```

**Đáp án:** **03/06 và 08/06**.

### Bài 4 — Ngày không có bất kỳ đơn nào

Thay điều kiện `NOT EXISTS` ở bài 3 bằng điều kiện chỉ nối theo ngày, không lọc status.

**Đáp án:** Chỉ **08/06**. Ngày 03/06 có hai đơn không paid.

### Bài 5 — Tại sao COUNT(*) sau LEFT JOIN cho 1 ở ngày trống?

```sql
SELECT
    c.calendar_date,
    COUNT(*) AS joined_rows,
    COUNT(o.order_id) AS actual_paid_orders
FROM demo_calendar_254 AS c
LEFT JOIN demo_orders_254 AS o
    ON o.ordered_on = c.calendar_date
   AND o.status = 'paid'
GROUP BY c.calendar_date
ORDER BY c.calendar_date;
```

**Đáp án:** 03/06 và 08/06 có `joined_rows=1` nhưng `actual_paid_orders=0`. `COUNT(*)` đếm hàng ngày lịch có các cột phía đơn là `NULL`; `COUNT(o.order_id)` chỉ đếm đơn thật.

### Bài 6 — 05/06 có phải ngày doanh thu 0 chắc chắn không?

**Đáp án:** Không. Ngày 05/06 có đơn paid `order_id=11` nhưng `amount=NULL`. `SUM(amount)` cho nhóm đó trả `NULL`. Nếu `COALESCE` thành 0, báo cáo có thể che dấu việc thiếu số tiền.

### Bài 7 — Điền ngày thiếu nhưng giữ thông tin amount chưa biết

**Đáp án gợi ý:**

```sql
WITH daily_paid AS (
    SELECT ordered_on, COUNT(*) AS paid_orders,
           SUM(amount) AS revenue
    FROM demo_orders_254
    WHERE status = 'paid'
    GROUP BY ordered_on
)
SELECT
    c.calendar_date,
    COALESCE(d.paid_orders, 0) AS paid_orders,
    CASE
        WHEN d.ordered_on IS NULL THEN 0::numeric
        ELSE d.revenue
    END AS revenue
FROM demo_calendar_254 AS c
LEFT JOIN daily_paid AS d
    ON d.ordered_on = c.calendar_date
ORDER BY c.calendar_date;
```

03/06 và 08/06 được điền 0; 05/06 giữ `NULL`.

### Bài 8 — Tính tổng doanh thu đã biết

Dựa trên bảng ngày đã bù, giá trị `SUM(revenue)` là bao nhiêu?

**Đáp án:** **950**, vì `SUM` bỏ qua `NULL` 05/06. Đây là tổng tiền đã biết, không phải khẳng định mọi số tiền paid đã đầy đủ.

### Bài 9 — Bù ngày theo vùng và kênh

Có 8 ngày, hai khu vực North/South và hai kênh Online/Store. Tạo đầy đủ mọi tổ hợp sẽ có bao nhiêu hàng?

**Đáp án:** `8 × 2 × 2 = 32` hàng. Cần tạo tập ngày × vùng × kênh, sau đó `LEFT JOIN` aggregate theo cả ba khóa.

### Bài 10 — Tổng theo bốn cặp vùng–kênh

**Đáp án:**

| Nhóm | Tổng amount paid đã biết |
| --- | ---: |
| North–Online | 340 |
| North–Store | 160 |
| South–Online | 230 |
| South–Store | 220 |

Tổng bốn nhóm là **950**. North–Online còn một đơn paid thiếu amount ngày 05/06.

### Bài 11 — Trung bình ba ngày lịch tại 04/06

Từ bảng đã bù, ba ngày 02/06, 03/06 và 04/06 có doanh thu `190,0,130`.

**Đáp án:** `(190+0+130)/3 ≈ 106.67`. Nếu dùng bảng tổng hợp chưa bù, ba **hàng có paid gần nhất** trước/tới 04/06 sẽ là ngày 01, 02, 04 với giá trị 230,190,130 — một chỉ số khác.

### Bài 12 — Trung bình ba ngày lịch tại 05/06

Dữ liệu ba ngày 03,04,05/06 là `[0,130,NULL]`.

**Đáp án:** `AVG(revenue) = (0+130)/2 = 65` theo ngữ nghĩa SQL bỏ `NULL`. Không tự chia cho 3 hoặc đổi `NULL` thành 0 khi chưa có quy tắc dữ liệu.

### Bài 13 — Tỷ lệ ngày có paid

Trong tám ngày lịch có bao nhiêu ngày có ít nhất một đơn paid và tỷ lệ là bao nhiêu?

**Đáp án:** **6 ngày**, chiếm `6/8 × 100 = 75%`.

### Bài 14 — Ngày thiếu nếu chỉ lấy MIN/MAX của giao dịch

```sql
SELECT MIN(ordered_on), MAX(ordered_on)
FROM demo_orders_254;
```

**Đáp án:** Min **01/06**, max **07/06**. Nếu dùng khoảng này làm lịch, sẽ bỏ **08/06**, dù kỳ báo cáo yêu cầu tới ngày đó.

### Bài 15 — Bộ lọc WHERE sau LEFT JOIN

Tại sao câu này không trả đủ tám ngày?

```sql
SELECT c.calendar_date, COUNT(o.order_id)
FROM demo_calendar_254 AS c
LEFT JOIN demo_orders_254 AS o
    ON o.ordered_on = c.calendar_date
WHERE o.status = 'paid'
GROUP BY c.calendar_date;
```

**Đáp án:** Điều kiện `WHERE` loại các hàng không paid và các hàng mở rộng `NULL`, làm 03/06 và 08/06 biến mất. Chuyển `o.status='paid'` vào `ON` hoặc lọc/tổng hợp fact trước rồi LEFT JOIN.

### Bài 16 — Ngày theo múi giờ Việt Nam

Một sự kiện có `occurred_at = 2025-05-31 18:00:00+00` thuộc ngày nào tại `Asia/Ho_Chi_Minh`?

**Đáp án:** **01/06/2025**, lúc 01:00 theo giờ Việt Nam. Vì vậy nhóm theo ngày UTC và nhóm theo ngày Việt Nam có thể cho kết quả khác nhau.

### Bài 17 — Ngày không có đơn và ngày chưa hoạt động

Một cửa hàng mới khai trương ngày 05/06 nhưng lưới báo cáo tạo các hàng từ 01/06. Có nên mặc định bốn ngày 01–04/06 là “cửa hàng hoạt động nhưng doanh thu 0” không?

**Đáp án:** Không, nếu nghiệp vụ cần phân biệt trạng thái **chưa hoạt động**. Nên giới hạn ngày–cửa hàng theo khoảng hiệu lực, hoặc trả một trạng thái riêng; chỉ bù 0 cho những ngày thuộc phạm vi hoạt động mà không có doanh thu.

### Bài 18 — Tổng lũy kế và cờ dữ liệu thiếu

Từ 01–08/06, tổng lũy kế doanh thu paid **đã biết** ở ngày 08/06 là bao nhiêu? Có được coi là đầy đủ không?

**Đáp án:** **950**, nhưng **chưa thể khẳng định đầy đủ** vì có một đơn paid ngày 05/06 chưa biết amount. Cần đi kèm cờ hoặc số lượng giá trị chưa biết.

## 25. Checklist triển khai mẫu bù ngày

Trước khi viết một báo cáo hoàn chỉnh, hãy xác định:

1. **Khoảng ngày cần hiển thị:** từ ngày nào đến ngày nào, có bao gồm ngày cuối không, có ngày tương lai không?
2. **Múi giờ nghiệp vụ:** ngày UTC, ngày Việt Nam hay ngày theo từng khách/cửa hàng?
3. **Grain của báo cáo:** một hàng/ngày, ngày–khu vực, ngày–sản phẩm hay ngày–khu vực–kênh?
4. **Bảng lịch đến từ đâu:** calendar dimension hay date spine sinh theo tham số?
5. **Lịch có đủ ngày và không trùng không:** cần khóa duy nhất và phạm vi được bảo trì.
6. **Bảng fact đã tổng hợp đúng grain chưa:** tránh nhân đơn qua các phép nối một-nhiều.
7. **LEFT JOIN giữ đúng phía chưa:** lịch hoặc lưới đầy đủ phải ở phía cần bảo toàn.
8. **Điều kiện trạng thái nằm ở đâu:** lọc bên phải trong `ON` hoặc trong CTE tổng hợp, không vô tình xóa ngày qua `WHERE` sau join.
9. **Đang đếm hàng nào:** `COUNT(*)` sau outer join có thể đếm hàng mở rộng; `COUNT(fact_id)` đếm bản ghi thật.
10. **NULL có ý nghĩa gì:** không có đơn, không có paid, amount chưa biết và số 0 thật không giống nhau.
11. **Các chiều có tổ hợp hợp lệ nào:** dùng bảng chiều/cặp hoạt động, tránh `CROSS JOIN` tạo quá nhiều hàng vô nghĩa.
12. **Phép tính tiếp theo dựa vào ngày lịch hay ngày có hoạt động:** bù ngày trước khi tính moving average/rolling count nếu yêu cầu là ngày lịch.
13. **Nguồn có dữ liệu nhập trễ không:** một ngày chưa thấy fact có thể là kỳ chưa hoàn tất, không chắc chắn là 0.
14. **Đã đối chiếu tổng với bảng nguồn chưa:** tổng amount đã biết, số đơn paid và số amount chưa biết cần nhất quán ở các cấp.
15. **Đã xét kích thước và index chưa:** giới hạn khoảng thời gian, giữ điều kiện lọc dùng được index và đo kế hoạch trên dữ liệu phù hợp.

Kết luận: **Bảng lịch tạo ra những ngày cần có; `LEFT JOIN` bảo toàn chúng; bảng tổng hợp cung cấp giá trị cho những ngày có dữ liệu.** Khi đặt đúng cấp tổng hợp, bộ lọc và quy tắc `NULL`/0, bạn sẽ có một chuỗi ngày đầy đủ để vẽ biểu đồ, tính chỉ số lũy kế, đo tỷ lệ hoạt động và phát hiện ngày thiếu mà không làm sai ý nghĩa dữ liệu nguồn.


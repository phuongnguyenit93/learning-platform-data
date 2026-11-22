# Xây dựng báo cáo thời gian với các khoảng không có dữ liệu trong PostgreSQL

## 1. Vấn đề: dữ liệu không phát sinh thì báo cáo vẫn cần hiện mốc thời gian

Một hệ thống bán hàng lưu các đơn hàng vào PostgreSQL. Khi chạy truy vấn:

```sql
SELECT
    (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS local_day,
    COUNT(*) AS total_orders
FROM time_report_lab.orders
GROUP BY (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
ORDER BY local_day;
```

PostgreSQL chỉ tạo nhóm cho **những ngày thực sự có hàng** trong bảng. Nếu ngày 02/10 không phát sinh đơn, kết quả **không có dòng ngày 02/10**.

Đối với báo cáo, biểu đồ và API dashboard, đây là một vấn đề:

```text
Kết quả GROUP BY trực tiếp

Ngày        Số đơn
2026-10-01  2
2026-10-03  2
2026-10-04  1
2026-10-05  1

Ngày 02/10 không xuất hiện
           |
           v
Biểu đồ có thể hiển thị trục thời gian không đều,
hoặc ứng dụng hiểu nhầm không có ngày đó.
```

Báo cáo đúng cho một dải ngày đầy đủ thường phải là:

```text
Ngày        Số đơn
2026-10-01  2
2026-10-02  0  <-- mốc được điền thêm
2026-10-03  2
2026-10-04  1
2026-10-05  1
```

Đây là kỹ thuật **lấp khoảng trống thời gian** (*gap filling*, *densifying a time series*) trong SQL.

Trong PostgreSQL, cách tiếp cận phổ biến là:

1. Xác định **phạm vi báo cáo**, đơn vị thời gian và múi giờ.
2. Tạo **trục thời gian đầy đủ** (*calendar spine*) bằng `generate_series` hoặc bảng lịch.
3. Tổng hợp dữ liệu phát sinh theo cùng đơn vị thời gian.
4. **LEFT JOIN từ trục thời gian sang dữ liệu tổng hợp** để giữ cả mốc không có sự kiện.
5. Dùng `COALESCE` cho những số liệu mà về mặt nghiệp vụ cần hiển thị là 0.
6. Sắp xếp theo mốc thời gian và kiểm tra cả các ngày đầu, cuối, ngày không có hàng.

> **Nguyên tắc cốt lõi:** không thể yêu cầu `GROUP BY` tự tạo các nhóm chưa tồn tại trong dữ liệu gốc. Muốn giữ các mốc không có sự kiện, cần có **một nguồn mốc thời gian độc lập** để JOIN.

Bài học áp dụng cho doanh thu ngày, số đơn hàng, lượt truy cập, số giao dịch, lịch vận hành, dữ liệu cảm biến và các báo cáo theo giờ/tuần/tháng.

## 2. Xác định ý nghĩa của một mốc thời gian trước khi viết SQL

Trước khi dùng `generate_series`, cần trả lời bốn câu hỏi:

- **Khoảng báo cáo:** từ ngày nào đến ngày nào? Ngày cuối có được tính không?
- **Đơn vị (bucket):** mỗi 15 phút, một giờ, một ngày, một tuần hay một tháng?
- **Múi giờ:** ngày của khách hàng ở Việt Nam, ngày UTC hay ngày của một quốc gia khác?
- **Số liệu:** tổng đơn, đơn thanh toán, doanh thu, số người dùng duy nhất, tỷ lệ hoàn thành?

Ví dụ báo cáo:

```text
Phạm vi:    từ 2026-10-01 đến trước 2026-10-15
Bucket:     một ngày lịch
Múi giờ:    Asia/Ho_Chi_Minh
Metric 1:   số đơn có mọi trạng thái
Metric 2:   số đơn PAID
Metric 3:   tổng tiền của đơn PAID
Trục ngày:  2026-10-01 ... 2026-10-14 (14 hàng)
```

Định nghĩa này chính xác hơn câu “báo cáo hai tuần đầu tháng 10” vì nó xác định ranh giới và thời điểm cắt dữ liệu.

### 2.1. Dùng khoảng nửa mở `[start, end)`

Trong SQL, biểu diễn một khoảng báo cáo bằng:

```sql
WHERE occurred_at >= :start_instant
  AND occurred_at <  :end_instant
```

Tức là **bao gồm mốc bắt đầu** và **loại trừ mốc kết thúc**.

Ví dụ lấy toàn bộ ngày 01 đến hết ngày 14/10 theo giờ Việt Nam:

```sql
WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND occurred_at <  TIMESTAMPTZ '2026-10-15 00:00:00+07'
```

Ưu điểm:

- Không phải đoán “giây cuối ngày” hay phần microsecond.
- Hai khoảng liền nhau như `[01/10,15/10)` và `[15/10,01/11)` không chồng lấn.
- Phù hợp điều kiện phạm vi trên index `occurred_at`.
- Giúp tránh đếm hai lần sự kiện nằm đúng trên ranh giới.

### 2.2. Ngày không có đơn khác ngày chưa nạp dữ liệu

Một ngày xuất hiện số 0 có thể có nhiều ý nghĩa:

1. Hệ thống hoạt động bình thường và **thật sự không có đơn**.
2. Có đơn nhưng **không có đơn PAID**, nên số đơn thanh toán bằng 0.
3. Có đơn PAID với **giá trị tiền bằng 0**.
4. Pipeline bị lỗi và **dữ liệu chưa được nạp đầy đủ**.

Kỹ thuật gap filling giải quyết **hình dạng trục thời gian**, chứ **không chứng minh pipeline đã đủ dữ liệu**. Nếu chất lượng dữ liệu cần phân biệt, báo cáo phải có thêm trạng thái hoàn tất/độ bao phủ dữ liệu, không tự đổi mọi “chưa biết” thành 0.

## 3. Chuẩn bị bộ dữ liệu thử nghiệm

Các câu lệnh sau tạo schema và bảng dùng riêng cho bài thực hành. Chỉ chạy trên database thử nghiệm có quyền `CREATE`/`INSERT`, không sửa dữ liệu production.

### 3.1. Bảng kênh bán hàng

```sql
CREATE SCHEMA IF NOT EXISTS time_report_lab;

CREATE TABLE time_report_lab.channels (
    channel_code text PRIMARY KEY,
    channel_label text NOT NULL
);

INSERT INTO time_report_lab.channels (channel_code, channel_label)
VALUES
    ('web',     'Website'),
    ('app',     'Ứng dụng'),
    ('partner', 'Đối tác');
```

Có ba kênh, nhưng trong dữ liệu mẫu **không có đơn nào từ kênh `partner`**. Chúng ta sẽ dùng điều đó để minh họa báo cáo hai chiều ngày × kênh.

### 3.2. Bảng đơn hàng

```sql
CREATE TABLE time_report_lab.orders (
    order_id bigint PRIMARY KEY,
    occurred_at timestamptz NOT NULL,
    channel_code text NOT NULL
        REFERENCES time_report_lab.channels(channel_code),
    status text NOT NULL
        CHECK (status IN ('PAID', 'PENDING', 'CANCELLED')),
    amount numeric(12,2) NOT NULL
        CHECK (amount >= 0)
);

CREATE INDEX idx_orders_occurred_at
ON time_report_lab.orders (occurred_at);
```

Giải thích:

| Cột | Ý nghĩa |
| --- | --- |
| `order_id` | Mã đơn duy nhất |
| `occurred_at` | Thời điểm ghi nhận đơn, có ngữ nghĩa múi giờ |
| `channel_code` | Kênh phát sinh đơn |
| `status` | `PAID`, `PENDING` hoặc `CANCELLED` |
| `amount` | Giá trị đơn; doanh thu trong bài chỉ tính `PAID` |

Dùng `timestamptz` vì sự kiện xảy ra tại một **thời điểm**. Cách trình bày giờ có thể đổi theo `TimeZone` của phiên PostgreSQL, nhưng ý nghĩa thời điểm vẫn được giữ.

### 3.3. Nạp các đơn mẫu, cố ý để trống nhiều ngày

```sql
INSERT INTO time_report_lab.orders
    (order_id, occurred_at, channel_code, status, amount)
VALUES
    (1001, TIMESTAMPTZ '2026-10-01 09:15:00+07', 'web', 'PAID',      120.00),
    (1002, TIMESTAMPTZ '2026-10-01 20:30:00+07', 'app', 'PAID',       80.00),
    (1003, TIMESTAMPTZ '2026-10-03 10:00:00+07', 'web', 'PAID',       90.00),
    (1004, TIMESTAMPTZ '2026-10-03 12:00:00+07', 'app', 'CANCELLED', 200.00),
    (1005, TIMESTAMPTZ '2026-10-04 15:45:00+07', 'web', 'PAID',        0.00),
    (1006, TIMESTAMPTZ '2026-10-05 08:00:00+07', 'app', 'PAID',      150.00),
    (1007, TIMESTAMPTZ '2026-10-08 23:59:00+07', 'web', 'PAID',      300.00),
    (1008, TIMESTAMPTZ '2026-10-10 06:20:00+07', 'app', 'PENDING',   250.00),
    (1009, TIMESTAMPTZ '2026-10-10 19:10:00+07', 'app', 'PAID',       60.00),
    (1010, TIMESTAMPTZ '2026-10-12 10:00:00+07', 'web', 'PAID',       75.00),
    (1011, TIMESTAMPTZ '2026-10-15 00:00:00+07', 'web', 'PAID',      999.00),
    (1012, TIMESTAMPTZ '2026-09-30 23:59:00+07', 'web', 'PAID',       33.00);
```

Hai đơn 1011 và 1012 **cố ý nằm ngoài** khoảng `[2026-10-01, 2026-10-15)`. Chúng giúp kiểm tra việc lọc đúng hai biên.

Trong 14 ngày được chọn có:

- **10 đơn** thuộc mọi trạng thái.
- **8 đơn PAID**.
- **1 đơn CANCELLED** và **1 đơn PENDING**.
- **875.00** tổng tiền của đơn PAID.
- Một số ngày hoàn toàn không có đơn.
- Ngày 04/10 có **một đơn PAID với amount = 0**, khác với ngày không có đơn nào.

Nếu chạy lại nguyên `INSERT` sau khi đã nạp, khóa chính sẽ gây lỗi. Chọn môi trường thử nghiệm mới hoặc làm sạch dữ liệu bài học có chủ đích.

## 4. Vì sao `GROUP BY date` tự nhiên bỏ những ngày rỗng?

### 4.1. Truy vấn chỉ đọc dữ liệu thực tế

```sql
SELECT
    (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS local_day,
    COUNT(*) AS total_orders
FROM time_report_lab.orders
WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND occurred_at <  TIMESTAMPTZ '2026-10-15 00:00:00+07'
GROUP BY
    (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
ORDER BY local_day;
```

Kết quả:

| local_day | total_orders |
| --- | ---: |
| 2026-10-01 | 2 |
| 2026-10-03 | 2 |
| 2026-10-04 | 1 |
| 2026-10-05 | 1 |
| 2026-10-08 | 1 |
| 2026-10-10 | 2 |
| 2026-10-12 | 1 |

Thiếu các ngày 02, 06, 07, 09, 11, 13 và 14/10.

`GROUP BY` chia **những hàng đang tồn tại** thành nhóm. Nếu không có hàng của ngày 02/10, PostgreSQL không có gì để nhóm theo ngày đó.

### 4.2. `COALESCE(COUNT(*), 0)` không tự sinh ngày thiếu

Thử:

```sql
SELECT
    (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS local_day,
    COALESCE(COUNT(*), 0) AS total_orders
FROM time_report_lab.orders
WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND occurred_at <  TIMESTAMPTZ '2026-10-15 00:00:00+07'
GROUP BY
    (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
ORDER BY local_day;
```

Truy vấn vẫn chỉ có bảy ngày. `COALESCE` biến một **giá trị NULL** thành giá trị khác, nhưng **không tự tạo thêm hàng không tồn tại**.

Đây là sai lầm quan trọng cần tránh:

> Muốn lấp ngày thiếu, phải tạo **các hàng ngày thiếu** trước. `COALESCE` chỉ nên được dùng **sau khi calendar đã LEFT JOIN** với dữ liệu.

## 5. `generate_series`: tạo trục ngày liên tục

PostgreSQL có hàm set-returning `generate_series` để tạo một chuỗi giá trị.

### 5.1. Tạo dãy số

```sql
SELECT n
FROM generate_series(0, 6) AS s(n);
```

Kết quả:

```text
0
1
2
3
4
5
6
```

Hai đầu **được bao gồm** nếu dãy bước đi đến đầu cuối. Với bước mặc định 1, `generate_series(0, 6)` tạo bảy hàng.

### 5.2. Tạo 14 ngày bằng phép cộng ngày và số nguyên

```sql
SELECT
    DATE '2026-10-01' + n AS local_day
FROM generate_series(0, 13) AS s(n)
ORDER BY local_day;
```

Kết quả gồm các ngày từ `2026-10-01` đến `2026-10-14`, đủ 14 hàng.

Phép `date + integer` cộng một **số ngày lịch**, không cộng một số giây cố định vào `timestamptz`.

### 5.3. Tạo series timestamp với interval

Có thể viết:

```sql
SELECT
    day_start::date AS local_day
FROM generate_series(
    TIMESTAMP '2026-10-01 00:00:00',
    TIMESTAMP '2026-10-14 00:00:00',
    INTERVAL '1 day'
) AS s(day_start)
ORDER BY local_day;
```

Cách này cũng tạo các mốc đầu ngày. Chúng là `timestamp without time zone`, hữu ích như các **mốc ngày lịch cục bộ** khi chưa chuyển sang thời điểm tuyệt đối.

Ở những tình huống cần chắc chắn về hàm overload, viết tường minh `TIMESTAMP` hoặc `TIMESTAMPTZ` thay vì dựa vào việc PostgreSQL tự suy đoán khi truyền hai literal `DATE` và một `INTERVAL`.

### 5.4. Chú ý tính bao gồm của cận cuối

`generate_series` có thể **bao gồm giá trị stop**. Nếu khoảng báo cáo dùng cận cuối loại trừ `2026-10-15`, không tạo lịch đến `2026-10-15`.

Hai cách rõ ràng:

```sql
-- Cách 1: số nguyên dựa trên độ dài khoảng.
SELECT DATE '2026-10-01' + n AS local_day
FROM generate_series(
    0,
    DATE '2026-10-15' - DATE '2026-10-01' - 1
) AS s(n);

-- Cách 2: stop là ngày cuối muốn hiển thị.
SELECT gs::date AS local_day
FROM generate_series(
    TIMESTAMP '2026-10-01',
    TIMESTAMP '2026-10-14',
    INTERVAL '1 day'
) AS s(gs);
```

Với khoảng không có ngày nào, như start = end, `generate_series(0, -1)` với bước mặc định dương tạo **0 hàng**. Nếu start lớn hơn end, nên coi đó là input không hợp lệ để kiểm tra ở ứng dụng hoặc quy trình tạo báo cáo.

## 6. Công thức chuẩn: calendar + dữ liệu tổng hợp + LEFT JOIN

Đây là mẫu quan trọng nhất của bài.

### 6.1. Bước 1: tạo calendar

```sql
WITH calendar AS (
    SELECT
        DATE '2026-10-01' + n AS local_day
    FROM generate_series(0, 13) AS s(n)
)
SELECT local_day
FROM calendar
ORDER BY local_day;
```

Calendar có **14 dòng**, bất kể có bao nhiêu đơn hàng.

### 6.2. Bước 2: tổng hợp các đơn theo ngày địa phương

```sql
SELECT
    (o.occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS local_day,
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (WHERE o.status = 'PAID')
        AS paid_orders,
    SUM(o.amount) FILTER (WHERE o.status = 'PAID')
        AS paid_revenue
FROM time_report_lab.orders AS o
WHERE o.occurred_at >=
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND o.occurred_at <
      TIMESTAMPTZ '2026-10-15 00:00:00+07'
GROUP BY
    (o.occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date;
```

Bảng tổng hợp này vẫn chỉ chứa **những ngày có đơn**. Nhưng giờ mỗi ngày có đúng một hàng, thuận tiện để ghép với calendar.

### 6.3. Bước 3: LEFT JOIN để lấp ngày rỗng

```sql
WITH
calendar AS (
    SELECT
        DATE '2026-10-01' + n AS local_day
    FROM generate_series(0, 13) AS s(n)
),
daily_fact AS (
    SELECT
        (o.occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
            AS local_day,
        COUNT(*) AS total_orders,
        COUNT(*) FILTER (WHERE o.status = 'PAID')
            AS paid_orders,
        SUM(o.amount) FILTER (WHERE o.status = 'PAID')
            AS paid_revenue
    FROM time_report_lab.orders AS o
    WHERE o.occurred_at >=
          TIMESTAMPTZ '2026-10-01 00:00:00+07'
      AND o.occurred_at <
          TIMESTAMPTZ '2026-10-15 00:00:00+07'
    GROUP BY
        (o.occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
)
SELECT
    c.local_day,
    COALESCE(f.total_orders, 0) AS total_orders,
    COALESCE(f.paid_orders, 0) AS paid_orders,
    COALESCE(f.paid_revenue, 0::numeric) AS paid_revenue
FROM calendar AS c
LEFT JOIN daily_fact AS f
    ON f.local_day = c.local_day
ORDER BY c.local_day;
```

**Kết quả mong đợi:**

| local_day | total_orders | paid_orders | paid_revenue |
| --- | ---: | ---: | ---: |
| 2026-10-01 | 2 | 2 | 200.00 |
| 2026-10-02 | 0 | 0 | 0 |
| 2026-10-03 | 2 | 1 | 90.00 |
| 2026-10-04 | 1 | 1 | 0.00 |
| 2026-10-05 | 1 | 1 | 150.00 |
| 2026-10-06 | 0 | 0 | 0 |
| 2026-10-07 | 0 | 0 | 0 |
| 2026-10-08 | 1 | 1 | 300.00 |
| 2026-10-09 | 0 | 0 | 0 |
| 2026-10-10 | 2 | 1 | 60.00 |
| 2026-10-11 | 0 | 0 | 0 |
| 2026-10-12 | 1 | 1 | 75.00 |
| 2026-10-13 | 0 | 0 | 0 |
| 2026-10-14 | 0 | 0 | 0 |

Có thể thấy **14 hàng cho 14 ngày**, kể cả ngày không có đơn.

### 6.4. Vai trò của từng thành phần

```text
generate_series
       |
       v
calendar: mọi ngày
       |
       | LEFT JOIN theo local_day
       v
daily_fact: chỉ những ngày có đơn
       |
       v
COALESCE số liệu NULL thành 0
       |
       v
ORDER BY local_day
       |
       v
Chuỗi thời gian liên tục cho biểu đồ/API
```

- `calendar` là **bảng điều khiển độ đầy đủ của trục thời gian**.
- `daily_fact` chứa các **giá trị đã tính từ dữ liệu**.
- `LEFT JOIN` giữ mọi ngày bên trái.
- `COALESCE` định dạng số liệu trống thành 0 **nếu metric có nghĩa 0**.
- `ORDER BY` đảm bảo thứ tự hiển thị.

Đây là mẫu nên ưu tiên khi báo cáo có nhiều chỉ số, nhiều điều kiện và khối lượng dữ liệu lớn: tổng hợp dữ liệu trước, JOIN calendar sau.

## 7. Vì sao `LEFT JOIN` phải bắt đầu từ calendar?

Nhìn hai truy vấn:

```sql
-- Đúng: giữ toàn bộ calendar.
FROM calendar AS c
LEFT JOIN daily_fact AS f
    ON f.local_day = c.local_day
```

và:

```sql
-- Không phù hợp để giữ tất cả ngày:
FROM daily_fact AS f
LEFT JOIN calendar AS c
    ON c.local_day = f.local_day
```

Với truy vấn thứ hai, bảng bên trái là `daily_fact` chỉ có ngày phát sinh sự kiện. `LEFT JOIN` **không thể tự thêm** những ngày chỉ có ở bảng calendar bên phải, nên ngày rỗng vẫn bị mất.

**Quy tắc:** phía **trái** của `LEFT JOIN` phải là tập các mốc/bộ tổ hợp mà bạn muốn bảo đảm xuất hiện trong kết quả.

Nếu muốn giữ cả hai phía một cách đặc biệt, `FULL JOIN` tồn tại, nhưng cho bài toán báo cáo trên một lịch đã xác định, `calendar LEFT JOIN fact` thường diễn đạt mục tiêu rõ và đơn giản hơn.

## 8. `COUNT(*)` là cái bẫy khi LEFT JOIN trực tiếp

Nhiều người muốn viết ngắn bằng cách JOIN calendar **thẳng** đến bảng đơn hàng:

```sql
WITH calendar AS (
    SELECT DATE '2026-10-01' + n AS local_day
    FROM generate_series(0, 13) AS s(n)
)
SELECT
    c.local_day,
    COUNT(*) AS total_orders
FROM calendar AS c
LEFT JOIN time_report_lab.orders AS o
    ON o.occurred_at >=
       (c.local_day::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
   AND o.occurred_at <
       ((c.local_day + 1)::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
GROUP BY c.local_day
ORDER BY c.local_day;
```

Với ngày 02/10 không có đơn, LEFT JOIN vẫn sinh **một hàng đại diện cho ngày 02/10** với mọi cột `o` là NULL.

`COUNT(*)` đếm **hàng kết quả JOIN**, không đếm đơn có thật. Vì vậy, ngày rỗng có thể bị báo sai thành **1 đơn**.

### 8.1. Sửa bằng `COUNT(o.order_id)`

```sql
WITH calendar AS (
    SELECT DATE '2026-10-01' + n AS local_day
    FROM generate_series(0, 13) AS s(n)
)
SELECT
    c.local_day,
    COUNT(o.order_id) AS total_orders,
    COUNT(o.order_id) FILTER (
        WHERE o.status = 'PAID'
    ) AS paid_orders,
    COALESCE(
        SUM(o.amount) FILTER (WHERE o.status = 'PAID'),
        0::numeric
    ) AS paid_revenue
FROM calendar AS c
LEFT JOIN time_report_lab.orders AS o
    ON o.occurred_at >=
       (c.local_day::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
   AND o.occurred_at <
       ((c.local_day + 1)::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
GROUP BY c.local_day
ORDER BY c.local_day;
```

`COUNT(o.order_id)` chỉ đếm những hàng có `order_id` khác NULL. Vì `order_id` là khóa chính của bảng nguồn, nó không thể NULL ở đơn thật, nên ngày không khớp có số đếm **0**.

Đây là dạng **JOIN rồi tổng hợp**. Nó hữu ích với báo cáo nhỏ hoặc truy vấn ad hoc; với lượng sự kiện lớn, dạng **tổng hợp trước rồi JOIN** ở phần 6 thường dễ kiểm soát khối lượng hơn.

### 8.2. `COUNT(*) FILTER` và `COUNT(column) FILTER`

Nếu viết:

```sql
COUNT(*) FILTER (WHERE o.status = 'PAID')
```

hàng mở rộng của LEFT JOIN không có `o.status = 'PAID'`, nên nó không được đếm; kết quả 0 là đúng cho số đơn PAID.

Tuy vậy, khi đếm **toàn bộ đơn**, cách rõ nhất là `COUNT(o.order_id)`, không phải `COUNT(*)`. Có thể dùng `COUNT(*) FILTER (WHERE o.order_id IS NOT NULL)` nhưng thường dài hơn mà không thêm giá trị.

## 9. `SUM`, `AVG` và ý nghĩa của giá trị 0

Các hàm tổng hợp không có cùng quy tắc với tập rỗng:

| Hàm | Trên tập hàng không có giá trị phù hợp |
| --- | --- |
| `COUNT(...)` | 0 |
| `SUM(...)` | NULL |
| `AVG(...)` | NULL |
| `MIN(...)` | NULL |
| `MAX(...)` | NULL |

Khi calendar LEFT JOIN một ngày không có đơn, biểu thức:

```sql
SUM(o.amount)
```

không có giá trị số tiền thực để cộng, nên trả NULL. Nếu “doanh thu ngày không có đơn” được định nghĩa là 0, có thể chuyển:

```sql
COALESCE(SUM(o.amount), 0::numeric)
```

### 9.1. Không tự thay `AVG` thiếu dữ liệu bằng 0

Giả sử bạn muốn báo cáo **giá trị trung bình của đơn PAID**:

```sql
AVG(o.amount) FILTER (WHERE o.status = 'PAID')
```

Với ngày không có đơn PAID, kết quả là NULL. Đó có thể là diễn đạt đúng: **không có quan sát để tính trung bình**.

Nếu viết:

```sql
COALESCE(
    AVG(o.amount) FILTER (WHERE o.status = 'PAID'),
    0::numeric
)
```

bạn đã gán **trung bình bằng 0** cho ngày không có mẫu. Điều này có thể làm người xem hiểu sai rằng có một số đo thực sự bằng 0.

Phân biệt:

| Trường hợp | Số đơn PAID | Doanh thu PAID | Trung bình đơn PAID |
| --- | ---: | ---: | --- |
| Ngày không có đơn nào | 0 | 0 theo quy ước | **NULL** |
| Ngày chỉ có CANCELLED/PENDING | 0 | 0 theo quy ước | **NULL** |
| Ngày có 1 đơn PAID, số tiền 0 | 1 | 0 | **0** |
| Ngày có 2 đơn PAID, 120 và 80 | 2 | 200 | **100** |

Điều kiện “không có quan sát” và “có quan sát giá trị 0” **không giống nhau**.

### 9.2. Ví dụ giữ NULL có chủ đích cho trung bình

```sql
WITH calendar AS (
    SELECT DATE '2026-10-01' + n AS local_day
    FROM generate_series(0, 13) AS s(n)
)
SELECT
    c.local_day,
    COUNT(o.order_id) FILTER (WHERE o.status = 'PAID')
        AS paid_orders,
    COALESCE(
        SUM(o.amount) FILTER (WHERE o.status = 'PAID'),
        0::numeric
    ) AS revenue,
    AVG(o.amount) FILTER (WHERE o.status = 'PAID')
        AS average_paid_order
FROM calendar AS c
LEFT JOIN time_report_lab.orders AS o
    ON o.occurred_at >=
       (c.local_day::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
   AND o.occurred_at <
       ((c.local_day + 1)::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
GROUP BY c.local_day
ORDER BY c.local_day;
```

Ngày 04/10 có trung bình đơn PAID **0**, trong khi ngày 02/10 có trung bình **NULL**. Đây là ví dụ tiêu biểu cho lý do không nên chuyển mọi ô trống thành 0.

## 10. Dùng `FILTER` để tính nhiều chỉ số trong cùng lượt tổng hợp

PostgreSQL cho phép thêm `FILTER (WHERE ...)` sau từng aggregate:

```sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders,
    COUNT(*) FILTER (WHERE status = 'PENDING') AS pending_orders,
    COUNT(*) FILTER (WHERE status = 'CANCELLED') AS cancelled_orders,
    SUM(amount) FILTER (WHERE status = 'PAID') AS revenue
FROM time_report_lab.orders
WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND occurred_at <  TIMESTAMPTZ '2026-10-15 00:00:00+07';
```

Kết quả mong đợi:

| all_orders | paid_orders | pending_orders | cancelled_orders | revenue |
| ---: | ---: | ---: | ---: | ---: |
| 10 | 8 | 1 | 1 | 875.00 |

`FILTER` diễn đạt rõ số liệu nào cần điều kiện nào.

Một cách viết tương đương về ý định trong nhiều trường hợp là `SUM(CASE WHEN ... THEN ... ELSE 0 END)`:

```sql
SELECT
    SUM(
        CASE WHEN status = 'PAID'
             THEN amount
             ELSE 0::numeric
        END
    ) AS revenue
FROM time_report_lab.orders;
```

Nhưng với báo cáo nhiều điều kiện, `FILTER` thường dễ đọc hơn. Lưu ý câu CASE trên **không tự lọc phạm vi ngày**; trong ví dụ đầy đủ phải thêm `WHERE occurred_at >= ... AND occurred_at < ...` nếu chỉ muốn một giai đoạn.

### 10.1. Không đặt `WHERE status = 'PAID'` sai chỗ sau LEFT JOIN

Sai cho báo cáo cần giữ ngày rỗng:

```sql
WITH calendar AS (
    SELECT DATE '2026-10-01' + n AS local_day
    FROM generate_series(0, 13) AS s(n)
)
SELECT
    c.local_day,
    COUNT(o.order_id) AS paid_orders
FROM calendar AS c
LEFT JOIN time_report_lab.orders AS o
    ON o.occurred_at >=
       (c.local_day::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
   AND o.occurred_at <
       ((c.local_day + 1)::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
WHERE o.status = 'PAID'
GROUP BY c.local_day
ORDER BY c.local_day;
```

`WHERE o.status = 'PAID'` loại cả những hàng calendar không khớp, vì `o.status` của chúng là NULL, khiến kết quả **mất ngày rỗng**.

Sửa bằng một trong hai cách:

- Đặt `o.status = 'PAID'` **trong điều kiện `ON`** nếu chỉ cần JOIN đơn PAID.
- Giữ JOIN mọi đơn và dùng `COUNT(o.order_id) FILTER (WHERE o.status = 'PAID')` nếu cần nhiều metric theo trạng thái.

### 10.2. Đặt điều kiện trong `ON` khi chỉ cần PAID

```sql
WITH calendar AS (
    SELECT DATE '2026-10-01' + n AS local_day
    FROM generate_series(0, 13) AS s(n)
)
SELECT
    c.local_day,
    COUNT(o.order_id) AS paid_orders
FROM calendar AS c
LEFT JOIN time_report_lab.orders AS o
    ON o.occurred_at >=
       (c.local_day::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
   AND o.occurred_at <
       ((c.local_day + 1)::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
   AND o.status = 'PAID'
GROUP BY c.local_day
ORDER BY c.local_day;
```

Mọi ngày được giữ; chỉ các đơn PAID được ghép vào mỗi ngày. Đây là mẫu đúng nếu chỉ quan tâm số đơn thanh toán.

**Quy tắc với OUTER JOIN:** điều kiện ở `ON` quyết định hàng nguồn nào được ghép; điều kiện ở `WHERE` lọc kết quả JOIN, có thể làm mất hàng lịch cần giữ.

## 11. Phân biệt hai chiến lược tổng hợp theo ngày

Có hai cấu trúc thường dùng.

### 11.1. Cách A — JOIN từng ngày theo khoảng timestamp rồi tổng hợp

```text
Calendar (14 ngày)
         |
         +-- LEFT JOIN orders theo [day_start, next_day_start)
         |
         +-- GROUP BY local_day
         |
         +-- COUNT / SUM / AVG
```

Ưu điểm:

- Câu SQL tương đối trực tiếp.
- Dùng được điều kiện thời gian trên `orders.occurred_at` theo khoảng.
- Dễ mở rộng khi chỉ có vài ngày và cần vài chỉ số.

Điều cần cân nhắc: khi nhiều bucket hoặc nhiều dimension, có thể tạo nhiều phép nối hoặc xử lý nhiều hàng nguồn trước khi GROUP BY.

### 11.2. Cách B — Lọc và GROUP BY dữ liệu trước, sau đó LEFT JOIN calendar

```text
orders (được lọc khoảng thời gian)
         |
         +-- GROUP BY local_day
         v
daily_fact (mỗi ngày có tối đa 1 hàng)
         |
calendar +-- LEFT JOIN daily_fact
         |
         +-- COALESCE
         v
Báo cáo đủ 14 ngày
```

Ưu điểm:

- Tách rõ **tính toán metric** và **lấp mốc còn thiếu**.
- Một hàng tổng hợp mỗi bucket giúp JOIN calendar đơn giản.
- Thường dễ mở rộng sang nhiều metric, nhóm, báo cáo API hoặc materialized summary.

Cả hai cách **đều đúng** nếu viết điều kiện và aggregate chính xác. Không mặc định cách nào luôn nhanh hơn mà chưa xem dữ liệu, thống kê và `EXPLAIN`.

## 12. Trục thời gian có tham số ngày bắt đầu và kết thúc

Không nên hardcode 14 ngày cho một báo cáo tái sử dụng.

### 12.1. Mẫu động với `bounds` và `generate_series`

```sql
WITH
bounds AS (
    SELECT
        DATE '2026-10-01' AS start_day,
        DATE '2026-10-15' AS end_day
),
calendar AS (
    SELECT
        b.start_day + n AS local_day
    FROM bounds AS b
    CROSS JOIN LATERAL generate_series(
        0,
        b.end_day - b.start_day - 1
    ) AS s(n)
)
SELECT local_day
FROM calendar
ORDER BY local_day;
```

`end_day` là **ngày đầu tiên không thuộc báo cáo**. Vì hai `DATE` trừ nhau ra số ngày nguyên, dạng này không phải tính số giây rồi chia 86.400.

### 12.2. Mẫu hoàn chỉnh dùng thời gian và múi giờ có tên

```sql
WITH
params AS (
    SELECT
        DATE '2026-10-01' AS start_day,
        DATE '2026-10-15' AS end_day,
        'Asia/Ho_Chi_Minh'::text AS report_timezone
),
calendar AS (
    SELECT
        p.start_day + n AS local_day
    FROM params AS p
    CROSS JOIN LATERAL generate_series(
        0,
        p.end_day - p.start_day - 1
    ) AS s(n)
),
daily_fact AS (
    SELECT
        (o.occurred_at AT TIME ZONE p.report_timezone)::date
            AS local_day,
        COUNT(*) AS total_orders,
        COUNT(*) FILTER (WHERE o.status = 'PAID')
            AS paid_orders,
        SUM(o.amount) FILTER (WHERE o.status = 'PAID')
            AS paid_revenue
    FROM time_report_lab.orders AS o
    CROSS JOIN params AS p
    WHERE o.occurred_at >=
          (p.start_day::timestamp AT TIME ZONE p.report_timezone)
      AND o.occurred_at <
          (p.end_day::timestamp AT TIME ZONE p.report_timezone)
    GROUP BY
        (o.occurred_at AT TIME ZONE p.report_timezone)::date
)
SELECT
    c.local_day,
    COALESCE(f.total_orders, 0) AS total_orders,
    COALESCE(f.paid_orders, 0) AS paid_orders,
    COALESCE(f.paid_revenue, 0::numeric) AS paid_revenue
FROM calendar AS c
LEFT JOIN daily_fact AS f
    ON f.local_day = c.local_day
ORDER BY c.local_day;
```

Cấu trúc này giúp mọi bộ phận cùng dùng một hợp đồng:

- `start_day`: ngày đầu, **bao gồm**.
- `end_day`: ngày cuối loại trừ.
- `report_timezone`: timezone của ngày lịch.
- `calendar`: mọi ngày cần hiển thị.
- `daily_fact`: dữ liệu đã tổng hợp và giới hạn theo đúng khoảng.
- `LEFT JOIN` và `COALESCE`: lấp số liệu rỗng theo quy tắc.

### 12.3. Tham số hóa trong ứng dụng

Ứng dụng có thể dùng prepared statement hoặc query parameter:

```sql
-- Phác họa sử dụng tham số theo giao thức PostgreSQL:
WITH params AS (
    SELECT
        $1::date AS start_day,
        $2::date AS end_day,
        $3::text AS report_timezone
)
SELECT ...
```

Đoạn `SELECT ...` là phác họa, không phải câu SQL thực thi độc lập. Với JDBC, có thể dùng placeholder `?` và bind bằng kiểu phù hợp.

Không nối chuỗi giá trị ngày hoặc timezone do người dùng nhập thẳng vào SQL. Kiểm tra:

- `start_day < end_day`.
- Khoảng tối đa được phép xuất báo cáo.
- Timezone hợp lệ, theo danh sách được hệ thống chấp nhận.
- Quyền truy cập dữ liệu theo người dùng/tenant.

Ngay cả một câu SQL tổng hợp đúng vẫn có thể làm server bận nếu yêu cầu một dải thời gian quá lớn không giới hạn.

## 13. Múi giờ: phải phân biệt thời điểm tuyệt đối và ngày lịch

Trong PostgreSQL:

- `timestamptz` biểu diễn **thời điểm**; hiển thị phụ thuộc timezone của session.
- `timestamp without time zone` biểu diễn **ngày giờ không gắn timezone**.
- `date` là **ngày lịch**; không chứa giờ hay timezone.

Cùng một thời điểm tuyệt đối có thể rơi vào **ngày khác nhau** ở hai timezone.

### 13.1. Ví dụ một thời điểm có hai ngày địa phương

```sql
SELECT
    TIMESTAMPTZ '2026-10-01 00:30:00+07'
        AT TIME ZONE 'Asia/Ho_Chi_Minh' AS vietnam_local,
    TIMESTAMPTZ '2026-10-01 00:30:00+07'
        AT TIME ZONE 'UTC' AS utc_local;
```

Theo giờ Việt Nam là 00:30 ngày 01/10. Tương ứng theo UTC là 17:30 **ngày 30/09**.

Nếu GROUP BY:

```sql
(occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
```

thì bucket theo ngày Việt Nam. Nếu GROUP BY:

```sql
(occurred_at AT TIME ZONE 'UTC')::date
```

thì bucket theo ngày UTC. Hai báo cáo có thể khác, dù đều đọc cùng hàng và đều đúng theo phạm vi của mình.

### 13.2. Không để session timezone quyết định ngày ngầm định

Nếu viết:

```sql
occurred_at::date
```

với `occurred_at timestamptz`, giá trị ngày phụ thuộc thiết lập `TimeZone` của session. Một connection chạy UTC, connection khác chạy `Asia/Ho_Chi_Minh` có thể phân nhóm khác nhau ở vùng ranh giới ngày.

Để báo cáo nhất quán, thường nên dùng:

```sql
(occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
```

và dùng mốc thời gian cùng timezone khi lọc.

### 13.3. Dùng tên timezone thay cho offset cố định khi có DST

Ở Việt Nam, `Asia/Ho_Chi_Minh` là lựa chọn rõ nghĩa khi báo cáo theo giờ Việt Nam. Với những khu vực có thay đổi giờ mùa hè, **offset không cố định suốt năm**.

Không nên dùng một offset như `-05` cho mọi ngày của New York, vì vào mùa hè offset có thể khác.

Thay vào đó, dùng tên IANA:

```sql
occurred_at AT TIME ZONE 'America/New_York'
```

và xác định đầu mỗi ngày địa phương bằng cách chuyển `date::timestamp AT TIME ZONE 'America/New_York'` sang `timestamptz`.

## 14. DST: một ngày không phải lúc nào cũng dài 24 giờ

Đây là điểm rất quan trọng nếu báo cáo theo ngày ở những timezone có đổi giờ mùa hè (*Daylight Saving Time*, DST).

### 14.1. Ví dụ New York trong tháng 3/2026

Ngày 08/03/2026 ở New York là ngày chuyển sang giờ mùa hè, nên có **23 giờ tuyệt đối** giữa hai mốc nửa đêm địa phương liên tiếp.

Có thể quan sát bằng PostgreSQL:

```sql
WITH days AS (
    SELECT
        DATE '2026-03-07' + n AS local_day
    FROM generate_series(0, 3) AS s(n)
)
SELECT
    local_day,
    local_day::timestamp
        AT TIME ZONE 'America/New_York' AS start_instant,
    (local_day + 1)::timestamp
        AT TIME ZONE 'America/New_York' AS end_instant,
    EXTRACT(EPOCH FROM (
        ((local_day + 1)::timestamp
            AT TIME ZONE 'America/New_York')
        -
        (local_day::timestamp
            AT TIME ZONE 'America/New_York')
    )) / 3600 AS elapsed_hours
FROM days
ORDER BY local_day;
```

Ở ngày chuyển giờ, `elapsed_hours` là 23. Với ngày chuyển ngược vào mùa thu, có thể có **25 giờ**.

### 14.2. Sai lầm: cộng cố định 24 giờ cho mọi ngày địa phương

Nếu dùng:

```sql
start_instant + INTERVAL '24 hours'
```

để tính cuối ngày địa phương ở vùng DST, kết quả có thể **không phải nửa đêm của ngày kế tiếp**.

Mẫu bền vững hơn:

```sql
(day::timestamp AT TIME ZONE 'America/New_York')
```

cho đầu ngày và:

```sql
((day + 1)::timestamp AT TIME ZONE 'America/New_York')
```

cho đầu ngày kế tiếp.

**Dãy ngày lịch** có thể tăng bằng `date + 1`, còn ranh giới thời điểm lấy từ timezone đúng. Không ép mọi ngày thành 86.400 giây.

### 14.3. Báo cáo theo giờ vào ngày DST

Khi đổi giờ:

- Có thể có một giờ địa phương **không xuất hiện**.
- Có thể có một giờ địa phương **xuất hiện hai lần** với offset khác nhau.

Nếu trục biểu đồ chỉ dùng nhãn giờ “01:00”, bạn có thể vô tình gộp hai thời điểm khác nhau. Để tránh, hãy dùng **mốc `timestamptz` duy nhất làm khóa bucket**, và hiển thị thêm offset/timezone trong nhãn khi cần.

Một báo cáo theo **giờ tuyệt đối** và báo cáo theo **giờ trên đồng hồ địa phương** có thể yêu cầu xử lý khác nhau. Hãy chọn một quy ước trước khi viết SQL.

## 15. Báo cáo theo giờ: tạo khoảng 15 phút hoặc một giờ

`generate_series` cũng tạo dãy `timestamptz`:

```sql
SELECT bucket_start
FROM generate_series(
    TIMESTAMPTZ '2026-10-01 00:00:00+07',
    TIMESTAMPTZ '2026-10-01 03:00:00+07',
    INTERVAL '1 hour'
) AS s(bucket_start)
ORDER BY bucket_start;
```

Dãy trên **bao gồm 03:00**, nên có bốn mốc: 00:00, 01:00, 02:00 và 03:00.

Nếu báo cáo là `[00:00, 03:00)` theo các bucket một giờ, chỉ cần **ba mốc** 00:00, 01:00, 02:00. Có thể tạo mốc bằng số nguyên:

```sql
SELECT
    TIMESTAMPTZ '2026-10-01 00:00:00+07'
        + n * INTERVAL '1 hour' AS bucket_start
FROM generate_series(0, 2) AS s(n)
ORDER BY bucket_start;
```

### 15.1. LEFT JOIN theo mốc đầu và cuối bucket

```sql
WITH hourly AS (
    SELECT
        TIMESTAMPTZ '2026-10-01 00:00:00+07'
            + n * INTERVAL '1 hour' AS bucket_start
    FROM generate_series(0, 23) AS s(n)
)
SELECT
    h.bucket_start,
    COUNT(o.order_id) AS total_orders
FROM hourly AS h
LEFT JOIN time_report_lab.orders AS o
    ON o.occurred_at >= h.bucket_start
   AND o.occurred_at <  h.bucket_start + INTERVAL '1 hour'
GROUP BY h.bucket_start
ORDER BY h.bucket_start;
```

Truy vấn có 24 bucket giờ tuyệt đối, mỗi giờ một hàng. Với ngày Việt Nam 01/10 không có DST, đây cũng là 24 giờ đồng hồ địa phương.

Nếu áp dụng cho ngày DST của một timezone khác, hãy xác định rõ đó là **24 giờ tuyệt đối** hay **toàn bộ một ngày lịch địa phương**, vì hai yêu cầu có thể không trùng nhau.

### 15.2. Dùng `date_bin` cho bucket cố định

PostgreSQL hiện đại có `date_bin` (từ PostgreSQL 14) để gán timestamp vào bucket có độ rộng cố định theo một mốc origin.

```sql
SELECT
    o.order_id,
    o.occurred_at,
    date_bin(
        INTERVAL '15 minutes',
        o.occurred_at,
        TIMESTAMPTZ '2026-10-01 00:00:00+07'
    ) AS bucket_start
FROM time_report_lab.orders AS o
ORDER BY o.occurred_at;
```

Ý nghĩa:

- `INTERVAL '15 minutes'`: độ rộng bucket.
- `occurred_at`: thời điểm sự kiện.
- `origin`: mốc căn chỉnh các bucket.

Ví dụ sự kiện lúc 09:17 thuộc bucket bắt đầu lúc 09:15 theo hệ mốc phù hợp.

**Lưu ý:** `date_bin` không được thiết kế để dùng stride có **tháng hoặc đơn vị lớn hơn** vì độ dài tháng thay đổi. Với tháng/quý/năm, dùng `date_trunc` hoặc logic ngày lịch.

### 15.3. Gap filling với `date_bin`

```sql
WITH
buckets AS (
    SELECT
        TIMESTAMPTZ '2026-10-01 09:00:00+07'
            + n * INTERVAL '15 minutes' AS bucket_start
    FROM generate_series(0, 7) AS s(n)
),
fact AS (
    SELECT
        date_bin(
            INTERVAL '15 minutes',
            occurred_at,
            TIMESTAMPTZ '2026-10-01 09:00:00+07'
        ) AS bucket_start,
        COUNT(*) AS total_orders
    FROM time_report_lab.orders
    WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 09:00:00+07'
      AND occurred_at <  TIMESTAMPTZ '2026-10-01 11:00:00+07'
    GROUP BY 1
)
SELECT
    b.bucket_start,
    COALESCE(f.total_orders, 0) AS total_orders
FROM buckets AS b
LEFT JOIN fact AS f
    ON f.bucket_start = b.bucket_start
ORDER BY b.bucket_start;
```

Mốc cuối loại trừ là 11:00, nên 8 bucket 15 phút bắt đầu từ 09:00 đến 10:45 được tạo. Sự kiện 09:15 nằm trong bucket 09:15; các mốc còn lại vẫn được hiển thị với 0 khi không có đơn.

## 16. Báo cáo theo tuần: đừng chỉ dùng số tuần

Trong PostgreSQL, `date_trunc('week', ...)` thường làm tròn về **đầu tuần ISO (thứ Hai)**.

```sql
SELECT
    date_trunc(
        'week',
        TIMESTAMP '2026-10-01 12:00:00'
    )::date AS week_start;
```

Ngày 01/10/2026 nằm trong tuần bắt đầu **2026-09-28**.

### 16.1. Tạo đủ các tuần báo cáo

```sql
SELECT
    week_start::date AS week_start
FROM generate_series(
    TIMESTAMP '2026-09-28',
    TIMESTAMP '2026-10-26',
    INTERVAL '1 week'
) AS s(week_start)
ORDER BY week_start;
```

Các mốc là ngày thứ Hai: 28/09, 05/10, 12/10, 19/10 và 26/10.

### 16.2. Nhóm sự kiện theo tuần địa phương

```sql
SELECT
    date_trunc(
        'week',
        o.occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )::date AS week_start,
    COUNT(*) AS total_orders
FROM time_report_lab.orders AS o
WHERE o.occurred_at >= TIMESTAMPTZ '2026-09-28 00:00:00+07'
  AND o.occurred_at <  TIMESTAMPTZ '2026-11-02 00:00:00+07'
GROUP BY 1
ORDER BY week_start;
```

Truy vấn chỉ có tuần phát sinh đơn. Muốn thêm tuần rỗng, tiếp tục dùng **weekly_calendar LEFT JOIN weekly_fact**, giống báo cáo ngày.

### 16.3. Vì sao không dùng duy nhất `EXTRACT(WEEK ...)` làm khóa?

```sql
EXTRACT(WEEK FROM occurred_at)
```

trả số tuần, nhưng **không đủ phân biệt năm**. Tuần số 1 tồn tại ở nhiều năm.

Đối với ISO week, dùng ít nhất:

```sql
EXTRACT(ISOYEAR FROM local_timestamp),
EXTRACT(WEEK FROM local_timestamp)
```

hoặc dùng **ngày đầu tuần** `date_trunc('week', local_timestamp)::date` làm khóa bucket. Khóa đầu tuần thường giúp JOIN calendar đơn giản hơn.

### 16.4. Tuần đầu/cuối năm không luôn thuộc năm dương lịch của ngày đó

Ngày cuối tháng 12 có thể thuộc **ISO week 1 của năm ISO kế tiếp**. Vì vậy, ghép `EXTRACT(YEAR ...)` với `EXTRACT(WEEK ...)` có thể làm sai định danh tuần. Nếu muốn nhãn tuần ISO, có thể dùng:

```sql
SELECT
    to_char(
        TIMESTAMP '2026-12-31',
        'IYYY-"W"IW'
    ) AS iso_week_label;
```

Đây là cách diễn đạt ý nghĩa của tuần ISO mà không nhầm năm lịch và năm ISO.

## 17. Báo cáo theo tháng: độ dài tháng không cố định

Tháng 2 có 28 hoặc 29 ngày, các tháng khác có 30 hoặc 31 ngày. Do đó, **không dùng `INTERVAL '30 days'` để tạo một lịch theo tháng**.

### 17.1. Tạo dãy tháng từ ngày đầu tháng

```sql
SELECT
    month_start::date AS month_start
FROM generate_series(
    TIMESTAMP '2026-07-01',
    TIMESTAMP '2026-12-01',
    INTERVAL '1 month'
) AS s(month_start)
ORDER BY month_start;
```

Kết quả gồm đầu các tháng 7, 8, 9, 10, 11 và 12.

### 17.2. Nhóm đơn theo tháng địa phương

```sql
SELECT
    date_trunc(
        'month',
        o.occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )::date AS month_start,
    COUNT(*) AS total_orders,
    SUM(o.amount) FILTER (WHERE o.status = 'PAID')
        AS paid_revenue
FROM time_report_lab.orders AS o
WHERE o.occurred_at >= TIMESTAMPTZ '2026-07-01 00:00:00+07'
  AND o.occurred_at <  TIMESTAMPTZ '2027-01-01 00:00:00+07'
GROUP BY 1
ORDER BY month_start;
```

### 17.3. Lấp các tháng không phát sinh

```sql
WITH
calendar AS (
    SELECT
        s.month_start::date AS month_start
    FROM generate_series(
        TIMESTAMP '2026-07-01',
        TIMESTAMP '2026-12-01',
        INTERVAL '1 month'
    ) AS s(month_start)
),
monthly_fact AS (
    SELECT
        date_trunc(
            'month',
            o.occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        )::date AS month_start,
        COUNT(*) AS total_orders,
        SUM(o.amount) FILTER (WHERE o.status = 'PAID')
            AS paid_revenue
    FROM time_report_lab.orders AS o
    WHERE o.occurred_at >= TIMESTAMPTZ '2026-07-01 00:00:00+07'
      AND o.occurred_at <  TIMESTAMPTZ '2027-01-01 00:00:00+07'
    GROUP BY 1
)
SELECT
    c.month_start,
    COALESCE(f.total_orders, 0) AS total_orders,
    COALESCE(f.paid_revenue, 0::numeric) AS paid_revenue
FROM calendar AS c
LEFT JOIN monthly_fact AS f
    ON f.month_start = c.month_start
ORDER BY c.month_start;
```

Với dữ liệu mẫu:

- Tháng 7 và 8 không có đơn → 0.
- Tháng 9 có **đơn 1012** nằm ngoài khoảng báo cáo ngày chính nhưng nằm trong báo cáo tháng.
- Tháng 10 có cả **đơn 1011 ngày 15/10** vì báo cáo tháng gồm toàn bộ tháng 10.
- Tháng 11 và 12 không có đơn → 0.

Kết quả minh họa theo mẫu này:

| month_start | total_orders | paid_revenue |
| --- | ---: | ---: |
| 2026-07-01 | 0 | 0 |
| 2026-08-01 | 0 | 0 |
| 2026-09-01 | 1 | 33.00 |
| 2026-10-01 | 11 | 1874.00 |
| 2026-11-01 | 0 | 0 |
| 2026-12-01 | 0 | 0 |

Tháng 10 có 10 đơn trong nửa đầu tháng và thêm đơn 1011 ở ngày 15/10; tổng doanh thu PAID là `875 + 999 = 1874`.

### 17.4. Mốc tháng phải được căn từ đầu tháng

Nếu bắt đầu `generate_series` bằng `2026-01-31` rồi tăng `INTERVAL '1 month'`, PostgreSQL phải điều chỉnh các ngày vượt số ngày của tháng sau; dãy có thể không đại diện **đầu tháng** như mong muốn.

Một báo cáo theo tháng nên tạo mốc từ `date_trunc('month', start_timestamp)` hoặc ngày 01 rõ ràng, rồi tăng tháng.

## 18. Ngày + kênh: lấp cả những tổ hợp không xuất hiện

Báo cáo doanh thu theo ngày và kênh cần **một hàng cho mọi cặp ngày × kênh**, kể cả:

- Một ngày không có đơn nào.
- Một ngày có đơn `web` nhưng không có `app`.
- Kênh `partner` không có đơn trong **toàn bộ** giai đoạn.

Chỉ `GROUP BY day, channel_code` sẽ bỏ các tổ hợp không xuất hiện.

### 18.1. Tạo khung ngày × kênh bằng `CROSS JOIN`

```sql
WITH calendar AS (
    SELECT DATE '2026-10-01' + n AS local_day
    FROM generate_series(0, 13) AS s(n)
)
SELECT
    c.local_day,
    ch.channel_code,
    ch.channel_label
FROM calendar AS c
CROSS JOIN time_report_lab.channels AS ch
ORDER BY c.local_day, ch.channel_code;
```

Có 14 ngày × 3 kênh = **42 hàng**. Đây là khung tất cả tổ hợp cần hiển thị.

### 18.2. Tổng hợp theo hai chiều rồi LEFT JOIN

```sql
WITH
calendar AS (
    SELECT DATE '2026-10-01' + n AS local_day
    FROM generate_series(0, 13) AS s(n)
),
grid AS (
    SELECT
        c.local_day,
        ch.channel_code,
        ch.channel_label
    FROM calendar AS c
    CROSS JOIN time_report_lab.channels AS ch
),
daily_channel_fact AS (
    SELECT
        (o.occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
            AS local_day,
        o.channel_code,
        COUNT(*) AS total_orders,
        COUNT(*) FILTER (WHERE o.status = 'PAID')
            AS paid_orders,
        SUM(o.amount) FILTER (WHERE o.status = 'PAID')
            AS paid_revenue
    FROM time_report_lab.orders AS o
    WHERE o.occurred_at >=
          TIMESTAMPTZ '2026-10-01 00:00:00+07'
      AND o.occurred_at <
          TIMESTAMPTZ '2026-10-15 00:00:00+07'
    GROUP BY
        (o.occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date,
        o.channel_code
)
SELECT
    g.local_day,
    g.channel_code,
    g.channel_label,
    COALESCE(f.total_orders, 0) AS total_orders,
    COALESCE(f.paid_orders, 0) AS paid_orders,
    COALESCE(f.paid_revenue, 0::numeric) AS paid_revenue
FROM grid AS g
LEFT JOIN daily_channel_fact AS f
    ON f.local_day = g.local_day
   AND f.channel_code = g.channel_code
ORDER BY g.local_day, g.channel_code;
```

Kết quả có đầy đủ 42 hàng. Ví dụ ngày 01/10:

| local_day | channel_code | total_orders | paid_orders | paid_revenue |
| --- | --- | ---: | ---: | ---: |
| 2026-10-01 | app | 1 | 1 | 80.00 |
| 2026-10-01 | partner | 0 | 0 | 0 |
| 2026-10-01 | web | 1 | 1 | 120.00 |

Ngày 02/10 có cả ba kênh đều 0. Kênh `partner` vẫn xuất hiện ở **mọi ngày**, dù không có đơn nào.

### 18.3. Vì sao cần bảng dimension hoặc danh sách kênh độc lập?

Nếu tạo tập kênh bằng:

```sql
SELECT DISTINCT channel_code
FROM time_report_lab.orders
WHERE occurred_at >= ...
  AND occurred_at < ...;
```

thì kênh `partner` **không xuất hiện**, vì không có đơn trong kỳ. Khi đó khung ngày × kênh cũng thiếu toàn bộ kênh partner.

Nếu mục tiêu là hiển thị **tất cả kênh đang được kinh doanh**, hãy lấy danh sách từ **bảng dimension** như `channels`, không phải từ dữ liệu sự kiện của riêng kỳ đang báo cáo.

### 18.4. Chú ý tổ hợp quá lớn

Nếu bạn CROSS JOIN:

```text
365 ngày
× 1.000 chi nhánh
× 100 sản phẩm
= 36.500.000 tổ hợp
```

thì chỉ riêng khung đã có hàng chục triệu hàng, chưa tính dữ liệu nguồn.

Giải pháp có thể gồm:

- Chỉ chọn những dimension thật sự cần.
- Xây lưới theo chi nhánh đang hoạt động trong giai đoạn.
- Phân trang/theo nhóm, không trả toàn bộ tổ hợp.
- Dùng bảng tổng hợp định kỳ hoặc materialized view.
- Chỉ tạo calendar ở độ phân giải phù hợp với dashboard.

**Gap filling không có nghĩa phải tạo mọi tổ hợp có thể tồn tại trong mọi chiều**.

## 19. Ngày không có dữ liệu: tìm khoảng trống để cảnh báo

Ngoài hiển thị số 0, đôi khi bạn cần liệt kê **những ngày không có bản ghi nào**, ví dụ phát hiện ngày chưa có hoạt động hoặc ngày nguồn dữ liệu ngừng cập nhật.

### 19.1. Lấy những ngày hoàn toàn không có đơn

```sql
WITH
calendar AS (
    SELECT DATE '2026-10-01' + n AS local_day
    FROM generate_series(0, 13) AS s(n)
),
daily_fact AS (
    SELECT
        (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
            AS local_day,
        COUNT(*) AS total_orders
    FROM time_report_lab.orders
    WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
      AND occurred_at <  TIMESTAMPTZ '2026-10-15 00:00:00+07'
    GROUP BY 1
)
SELECT c.local_day
FROM calendar AS c
LEFT JOIN daily_fact AS f
    ON f.local_day = c.local_day
WHERE f.local_day IS NULL
ORDER BY c.local_day;
```

Kết quả:

```text
2026-10-02
2026-10-06
2026-10-07
2026-10-09
2026-10-11
2026-10-13
2026-10-14
```

`f.local_day IS NULL` ở đây nhận biết **không có hàng tổng hợp cho ngày đó**. Điều này khác:

```sql
WHERE f.total_orders = 0
```

Vì ngày vắng mặt có `f.total_orders = NULL` trước khi COALESCE, điều kiện `= 0` không chọn được nó.

### 19.2. `NOT EXISTS` thay cho LEFT JOIN

Một cách khác:

```sql
WITH calendar AS (
    SELECT DATE '2026-10-01' + n AS local_day
    FROM generate_series(0, 13) AS s(n)
)
SELECT c.local_day
FROM calendar AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM time_report_lab.orders AS o
    WHERE o.occurred_at >=
          (c.local_day::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
      AND o.occurred_at <
          ((c.local_day + 1)::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
)
ORDER BY c.local_day;
```

`NOT EXISTS` diễn đạt trực tiếp “không có đơn trong ngày này”. PostgreSQL có thể chọn kế hoạch khác tùy số ngày, index và dữ liệu nguồn.

### 19.3. Tìm những ngày không có đơn PAID

Một ngày có đơn PENDING hoặc CANCELLED nhưng không có PAID **không phải** ngày trống hoàn toàn.

Ví dụ, trong dữ liệu mẫu ngày 03/10 có PAID và CANCELLED; ngày 10/10 có PAID và PENDING. Nếu muốn phát hiện các ngày **không có đơn PAID**, dùng:

```sql
WITH calendar AS (
    SELECT DATE '2026-10-01' + n AS local_day
    FROM generate_series(0, 13) AS s(n)
)
SELECT c.local_day
FROM calendar AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM time_report_lab.orders AS o
    WHERE o.status = 'PAID'
      AND o.occurred_at >=
          (c.local_day::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
      AND o.occurred_at <
          ((c.local_day + 1)::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
)
ORDER BY c.local_day;
```

Với mẫu này, các ngày không có đơn PAID trùng các ngày không có đơn nào vì ngày có PENDING/CANCELLED đều đồng thời có ít nhất một đơn PAID. Trong dữ liệu thật, hai danh sách có thể khác nhau.

## 20. Phát hiện các chuỗi ngày trống liên tiếp

Nếu một hệ thống không có dữ liệu nhiều ngày liên tiếp, bạn có thể muốn biết **đợt gián đoạn** kéo dài từ ngày nào đến ngày nào.

### 20.1. Trước tiên đánh dấu mỗi ngày có dữ liệu hay không

```sql
WITH
calendar AS (
    SELECT DATE '2026-10-01' + n AS local_day
    FROM generate_series(0, 13) AS s(n)
),
daily_fact AS (
    SELECT
        (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
            AS local_day,
        COUNT(*) AS total_orders
    FROM time_report_lab.orders
    WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
      AND occurred_at <  TIMESTAMPTZ '2026-10-15 00:00:00+07'
    GROUP BY 1
)
SELECT
    c.local_day,
    (f.local_day IS NULL) AS is_empty
FROM calendar AS c
LEFT JOIN daily_fact AS f USING (local_day)
ORDER BY c.local_day;
```

Dãy `is_empty` cho biết những ngày nào không có hàng nguồn.

### 20.2. Gom những ngày rỗng liên tiếp bằng window function

Một kỹ thuật là lấy số thứ tự của ngày rỗng rồi trừ đi số thứ tự ngày lịch tương ứng (hoặc dùng phép biến đổi tương đương) để tạo khóa cho mỗi **chuỗi liên tiếp**.

```sql
WITH
calendar AS (
    SELECT DATE '2026-10-01' + n AS local_day
    FROM generate_series(0, 13) AS s(n)
),
present_days AS (
    SELECT DISTINCT
        (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
            AS local_day
    FROM time_report_lab.orders
    WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
      AND occurred_at <  TIMESTAMPTZ '2026-10-15 00:00:00+07'
),
empty_days AS (
    SELECT c.local_day
    FROM calendar AS c
    LEFT JOIN present_days AS p USING (local_day)
    WHERE p.local_day IS NULL
),
numbered AS (
    SELECT
        local_day,
        local_day
          - ROW_NUMBER() OVER (ORDER BY local_day)::integer
          AS streak_key
    FROM empty_days
)
SELECT
    MIN(local_day) AS empty_from,
    MAX(local_day) AS empty_through,
    COUNT(*) AS empty_days_count
FROM numbered
GROUP BY streak_key
ORDER BY empty_from;
```

Ở PostgreSQL, `date - integer` trả một ngày mới; trong một chuỗi ngày liên tiếp, `local_day - row_number` giữ nguyên khóa.

Với dữ liệu mẫu, kết quả:

| empty_from | empty_through | empty_days_count |
| --- | --- | ---: |
| 2026-10-02 | 2026-10-02 | 1 |
| 2026-10-06 | 2026-10-07 | 2 |
| 2026-10-09 | 2026-10-09 | 1 |
| 2026-10-11 | 2026-10-11 | 1 |
| 2026-10-13 | 2026-10-14 | 2 |

Kỹ thuật này hữu ích để phát hiện “không có sự kiện ba ngày liên tiếp” hoặc “pipeline không cập nhật nhiều ngày”, nhưng phải phân biệt **ngừng phát sinh nghiệp vụ** với **ngừng nạp dữ liệu** trước khi phát cảnh báo vận hành.

## 21. Lũy kế, trung bình trượt và so sánh kỳ trước

Sau khi đã tạo **một hàng cho mỗi ngày**, những hàm cửa sổ (*window functions*) trở nên dễ dùng hơn.

### 21.1. Doanh thu lũy kế

```sql
WITH
calendar AS (
    SELECT DATE '2026-10-01' + n AS local_day
    FROM generate_series(0, 13) AS s(n)
),
daily_fact AS (
    SELECT
        (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
            AS local_day,
        COALESCE(
            SUM(amount) FILTER (WHERE status = 'PAID'),
            0::numeric
        ) AS paid_revenue
    FROM time_report_lab.orders
    WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
      AND occurred_at <  TIMESTAMPTZ '2026-10-15 00:00:00+07'
    GROUP BY 1
),
filled AS (
    SELECT
        c.local_day,
        COALESCE(f.paid_revenue, 0::numeric) AS paid_revenue
    FROM calendar AS c
    LEFT JOIN daily_fact AS f USING (local_day)
)
SELECT
    local_day,
    paid_revenue,
    SUM(paid_revenue) OVER (
        ORDER BY local_day
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_revenue
FROM filled
ORDER BY local_day;
```

Những ngày doanh thu bằng 0 vẫn xuất hiện; tổng lũy kế giữ nguyên qua những ngày đó.

### 21.2. Trung bình trượt bảy ngày

Nếu `filled` đã có **đủ ngày liên tiếp**, có thể tính:

```sql
SELECT
    local_day,
    paid_revenue,
    AVG(paid_revenue) OVER (
        ORDER BY local_day
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS moving_avg_7_rows
FROM filled
ORDER BY local_day;
```

Vì mỗi hàng ứng với đúng một ngày, `ROWS BETWEEN 6 PRECEDING ...` là một cửa sổ **tối đa bảy ngày lịch** trong dãy.

Nếu chỉ bắt đầu tạo calendar ở ngày đầu báo cáo, những ngày đầu chưa có đủ sáu ngày trước đó, nên trung bình được tính trên số hàng đang sẵn có, không nhất thiết là đúng “trung bình bảy ngày đầy đủ”.

Muốn mỗi ngày luôn có đủ bảy ngày làm mẫu (kể cả trước ngày đầu hiển thị), hãy:

1. Tạo/đọc dữ liệu từ **sáu ngày trước** start_day.
2. Lấp lịch cho cả khoảng mở rộng.
3. Tính cửa sổ.
4. Lọc về khoảng muốn hiển thị **ở truy vấn ngoài**.

Nếu lọc ngày trước khi tính window, các hàng quá khứ cần cho moving average đã bị loại.

### 21.3. So với ngày trước bằng `LAG`

```sql
SELECT
    local_day,
    paid_revenue,
    LAG(paid_revenue) OVER (
        ORDER BY local_day
    ) AS previous_day_revenue
FROM filled
ORDER BY local_day;
```

Nếu chỉ chạy `LAG` trên `daily_fact` có ngày phát sinh, “hàng trước” có thể là **vài ngày trước** chứ không phải **ngày hôm qua**. Lấp calendar trước giúp `LAG` có ý nghĩa chính xác theo ngày.

### 21.4. Tỷ lệ tăng trưởng và mẫu số 0

```sql
WITH with_previous AS (
    SELECT
        local_day,
        paid_revenue,
        LAG(paid_revenue) OVER (
            ORDER BY local_day
        ) AS previous_day_revenue
    FROM filled
)
SELECT
    local_day,
    paid_revenue,
    previous_day_revenue,
    round(
        100 * (paid_revenue - previous_day_revenue)
        / NULLIF(previous_day_revenue, 0),
        2
    ) AS growth_percent
FROM with_previous
ORDER BY local_day;
```

Nếu doanh thu ngày trước bằng 0, phép tính phần trăm tăng trưởng theo công thức đó **không xác định**; `NULLIF(...,0)` giúp trả NULL thay vì lỗi chia cho 0.

Đừng tự thay kết quả không xác định thành 100% hay 0% nếu chưa có quy tắc báo cáo rõ ràng.

## 22. Phân biệt số 0 thật với dữ liệu chưa hoàn tất

Báo cáo gap filling thường hiển thị 0 cho ngày không có sự kiện, nhưng điều đó chỉ đúng khi dữ liệu nguồn **đã được xác nhận hoàn tất** đến ngày đang xét.

### 22.1. Ví dụ ngày bị lỗi pipeline

Giả sử ngày 06/10 không có đơn trong database. Có hai kịch bản:

- Kịch bản A: hệ thống hoạt động và không có khách nào đặt đơn → 0 là đúng.
- Kịch bản B: tiến trình ETL bị lỗi, đơn trong ngày chưa được chuyển vào database → 0 là **chưa được xác minh**.

Nếu dashboard hiển thị 0 ở cả hai kịch bản, người xem có thể kết luận sai rằng doanh thu bằng 0.

### 22.2. Bổ sung bảng theo dõi độ bao phủ dữ liệu

Một mô hình minh họa:

```sql
CREATE TABLE time_report_lab.ingestion_days (
    local_day date PRIMARY KEY,
    is_complete boolean NOT NULL,
    checked_at timestamptz NOT NULL DEFAULT now()
);
```

Sau khi quy trình nạp dữ liệu xác nhận một ngày đã đủ dữ liệu, nó ghi:

```sql
INSERT INTO time_report_lab.ingestion_days
    (local_day, is_complete)
VALUES
    (DATE '2026-10-01', TRUE),
    (DATE '2026-10-02', TRUE),
    (DATE '2026-10-03', TRUE),
    (DATE '2026-10-06', FALSE);
```

Ý nghĩa:

- `TRUE`: pipeline xác nhận ngày đã hoàn tất.
- `FALSE`: ngày đã được kiểm tra nhưng **chưa đủ**.
- Không có hàng: **chưa biết trạng thái**.

### 22.3. Không vội điền 0 ở ngày chưa hoàn tất

Giả sử đã có CTE `calendar` và `daily_fact` từ các ví dụ trước, có thể thêm trạng thái:

```sql
SELECT
    c.local_day,
    q.is_complete,
    CASE
        WHEN q.is_complete IS TRUE
        THEN COALESCE(f.total_orders, 0)
        ELSE NULL
    END AS verified_total_orders
FROM calendar AS c
LEFT JOIN daily_fact AS f
    ON f.local_day = c.local_day
LEFT JOIN time_report_lab.ingestion_days AS q
    ON q.local_day = c.local_day
ORDER BY c.local_day;
```

Đây là mẫu **chỉ để minh họa cấu trúc**, cần đặt trong truy vấn có khai báo hai CTE `calendar` và `daily_fact` tương ứng.

- Ngày được xác nhận hoàn tất và không có đơn → hiển thị 0.
- Ngày chưa hoàn tất hoặc chưa biết → hiển thị NULL/chưa xác minh.

Sự khác biệt này rất quan trọng với dashboard tài chính, SLA, quan sát dữ liệu và cảnh báo hoạt động.

### 22.4. Dữ liệu ngày hiện tại thường chưa hoàn tất

Nếu báo cáo chạy lúc 10:00 sáng, ngày hôm nay mới có dữ liệu của một phần ngày. Việc so sánh tổng hôm nay với tổng cả ngày hôm qua thường gây hiểu nhầm.

Có thể chọn một trong các chính sách:

- Chỉ hiển thị những **ngày đã khép lại**.
- Hiển thị ngày hiện tại nhưng gắn nhãn **partial/in progress**.
- So sánh cùng một khoảng giờ trong ngày ở hai kỳ.
- Dùng watermark/ingestion completeness để xác định vùng dữ liệu đã đáng tin.

Đừng coi `CURRENT_DATE` là một ngày đã hoàn tất chỉ vì đã có một số sự kiện.

## 23. Bảng lịch vật lý và `generate_series`: chọn cách nào?

`generate_series` rất tiện cho báo cáo theo yêu cầu. Tuy nhiên, một **bảng calendar dimension** có thể phù hợp khi doanh nghiệp cần nhiều thông tin lịch.

### 23.1. `generate_series` khi nào đủ?

Dùng khi:

- Chỉ cần trục ngày/giờ/tuần/tháng đơn giản.
- Khoảng báo cáo có độ dài vừa phải.
- Không có quy tắc lịch phức tạp.
- Muốn viết SQL tự chứa, dễ tái sử dụng.

```sql
SELECT DATE '2026-10-01' + n AS local_day
FROM generate_series(0, 13) AS s(n);
```

### 23.2. Bảng lịch khi cần lịch nghiệp vụ

Một bảng lịch có thể lưu:

```sql
CREATE TABLE time_report_lab.calendar_days (
    local_day date PRIMARY KEY,
    is_weekend boolean NOT NULL,
    is_business_day boolean NOT NULL,
    fiscal_year integer,
    fiscal_period integer
);
```

Một hệ thống có thể nạp trước nhiều năm dữ liệu lịch, bao gồm ngày nghỉ, ngày làm việc, tuần tài chính, kỳ kế toán, lịch của từng thị trường.

Khi đó:

```sql
SELECT local_day
FROM time_report_lab.calendar_days
WHERE local_day >= DATE '2026-10-01'
  AND local_day < DATE '2026-10-15'
ORDER BY local_day;
```

cung cấp một trục lịch có sẵn thuộc tính nghiệp vụ.

**Chú ý:** `is_weekend` không đồng nghĩa `is_business_day = FALSE` trong mọi quốc gia/doanh nghiệp; ngày nghỉ lễ và lịch làm việc cần nguồn dữ liệu được quản trị. Bảng ví dụ chưa được nạp, nên truy vấn sẽ chưa trả ngày nào cho đến khi có dữ liệu lịch.

### 23.3. Báo cáo ngày làm việc

Nếu đã có calendar dimension đúng dữ liệu:

```sql
SELECT local_day
FROM time_report_lab.calendar_days
WHERE local_day >= DATE '2026-10-01'
  AND local_day <  DATE '2026-10-15'
  AND is_business_day = TRUE
ORDER BY local_day;
```

Dùng tập ngày làm việc đó làm phía trái `LEFT JOIN`. Lúc này báo cáo **cố ý bỏ cuối tuần/ngày nghỉ**; đó là quy tắc khác với báo cáo **mọi ngày**.

Nên thống nhất định nghĩa trước khi người dùng đối chiếu các dashboard khác nhau.

## 24. Tối ưu hiệu năng cho dữ liệu lớn

Kỹ thuật lấp khoảng trống không có nghĩa phải đọc toàn bộ bảng sự kiện cho mọi lần tạo báo cáo.

### 24.1. Lọc theo phạm vi thời gian trực tiếp trên cột

Ưu tiên:

```sql
WHERE o.occurred_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND o.occurred_at <  TIMESTAMPTZ '2026-10-15 00:00:00+07'
```

thay vì chỉ dùng:

```sql
WHERE (o.occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
      BETWEEN DATE '2026-10-01' AND DATE '2026-10-14'
```

Biểu thức chuyển timezone/cast trên cột có thể làm một B-tree index thông thường của `occurred_at` khó dùng như điều kiện phạm vi trực tiếp.

Mẫu thường phù hợp:

1. Xác định `start_instant` và `end_instant` bằng cách chuyển **ngày địa phương** sang thời điểm tương ứng.
2. Lọc bảng nguồn bằng `occurred_at >= start_instant AND occurred_at < end_instant`.
3. Sau khi đã lọc, tạo khóa nhóm `(occurred_at AT TIME ZONE timezone)::date`.

Đây là cách giữ cả **đúng ngữ nghĩa ngày** và khả năng tận dụng **index theo timestamp**.

### 24.2. Index trên thời điểm và dimension

Trong bộ mẫu:

```sql
CREATE INDEX idx_orders_occurred_channel
ON time_report_lab.orders (occurred_at, channel_code);
```

Index này là **ứng viên**, không phải yêu cầu bắt buộc. Tùy workload, index `(channel_code, occurred_at)` cũng có thể phù hợp khi query luôn lọc một channel cụ thể trước rồi mới giới hạn thời gian.

Không thể quyết định thứ tự index tối ưu chỉ bằng nhìn tên cột. Cần xem điều kiện, độ chọn lọc, cách sắp xếp, số hàng, kích thước bảng, chi phí ghi và `EXPLAIN`.

### 24.3. Partial index cho đơn PAID

Nếu báo cáo thường xuyên chỉ đọc đơn PAID:

```sql
CREATE INDEX idx_orders_paid_time
ON time_report_lab.orders (occurred_at)
WHERE status = 'PAID';
```

Index này chỉ chứa những đơn PAID. PostgreSQL có thể sử dụng nếu điều kiện query phù hợp với predicate và cost model cho thấy lợi ích.

Không phải mọi query chứa `FILTER (WHERE status = 'PAID')` đều chắc chắn dùng partial index trên PAID, vì `FILTER` của aggregate không đồng nghĩa với `WHERE status = 'PAID'` loại mọi đơn khác ngay từ đầu. Nếu chỉ cần doanh thu PAID, cân nhắc đưa điều kiện `status = 'PAID'` vào **WHERE của dữ liệu nguồn** khi ngữ nghĩa cho phép.

### 24.4. Pre-aggregate trước khi tạo lưới dimension lớn

Với dữ liệu nhiều triệu sự kiện và báo cáo 365 ngày × 100 kênh, thường không muốn tạo một bảng JOIN trung gian bằng cách ghép từng ngày-kênh với mọi sự kiện rồi mới tính tổng.

Mẫu `daily_channel_fact`:

```text
Nhiều triệu đơn
    |
    v
GROUP BY day, channel
    |
    v
Tối đa vài chục nghìn nhóm có dữ liệu
    |
    v
LEFT JOIN với calendar × channel grid
    |
    v
Đủ nhóm có/không có dữ liệu
```

Giúp tách việc **quét và tổng hợp fact** khỏi việc **điền chiều báo cáo**. Dù vậy, optimizer có thể biến đổi kế hoạch; cần quan sát thực tế thay vì cam kết một sơ đồ luôn nhanh hơn.

### 24.5. Partitioning theo thời gian

Với bảng sự kiện rất lớn, PostgreSQL hỗ trợ partitioning theo phạm vi thời gian. Ví dụ ý tưởng:

```sql
CREATE TABLE time_report_lab.large_events (
    event_id bigint NOT NULL,
    occurred_at timestamptz NOT NULL,
    payload jsonb
) PARTITION BY RANGE (occurred_at);
```

Còn cần tạo các partition cụ thể trước khi chèn dữ liệu. Không được coi đoạn trên là một hệ thống partitioning đã hoàn chỉnh.

Khi truy vấn lọc theo khoảng thời gian đúng trên partition key, PostgreSQL có thể **partition prune** để tránh đọc các partition ngoài khoảng. Nhưng partitioning có chi phí quản trị và không thay thế index/đo lường.

### 24.6. Bảng tổng hợp định kỳ

Nếu cùng một dashboard phải đọc hàng trăm triệu sự kiện rất nhiều lần, có thể lưu bảng tổng hợp:

```sql
CREATE TABLE time_report_lab.daily_order_summary (
    local_day date NOT NULL,
    channel_code text NOT NULL,
    total_orders bigint NOT NULL,
    paid_orders bigint NOT NULL,
    paid_revenue numeric(18,2) NOT NULL,
    PRIMARY KEY (local_day, channel_code)
);
```

Một job có thể tính/điền dữ liệu summary đã được xác minh rồi dashboard `LEFT JOIN` calendar sang summary, thay vì tính lại dữ liệu gốc mỗi lần.

Nhưng cần giải quyết:

- Retry và idempotency.
- Sự kiện đến muộn hoặc trạng thái đơn bị cập nhật.
- Tính nhất quán giữa bảng nguồn và bảng summary.
- Khi nào một ngày được coi đã hoàn tất.
- Khả năng rebuild summary từ dữ liệu nguồn.
- Múi giờ mà `local_day` đại diện.

Đừng chỉ lưu số tổng mà không lưu đủ thông tin để hiểu định nghĩa metric.

## 25. Dùng `EXPLAIN` để quan sát kế hoạch

Ví dụ:

```sql
EXPLAIN
WITH calendar AS (
    SELECT DATE '2026-10-01' + n AS local_day
    FROM generate_series(0, 13) AS s(n)
)
SELECT
    c.local_day,
    COUNT(o.order_id)
FROM calendar AS c
LEFT JOIN time_report_lab.orders AS o
    ON o.occurred_at >=
       (c.local_day::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
   AND o.occurred_at <
       ((c.local_day + 1)::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
GROUP BY c.local_day
ORDER BY c.local_day;
```

Tùy kích thước dữ liệu, PostgreSQL có thể dùng:

- `Function Scan` cho `generate_series`.
- `Seq Scan`, `Index Scan` hoặc `Bitmap Index Scan` để đọc fact.
- `Nested Loop`, `Hash Join` hoặc các kiểu join phù hợp.
- `HashAggregate` hoặc `GroupAggregate` để tổng hợp.
- `Sort` nếu cần sắp xếp kết quả.

Bảng ví dụ chỉ có 12 sự kiện, nên `Seq Scan` có thể hợp lý hơn index; không dùng nó để kết luận cấu hình cho bảng nhiều triệu hàng.

`EXPLAIN (ANALYZE, BUFFERS)` còn thực thi query để ghi nhận thời gian và I/O, có ích khi đo trên môi trường phù hợp. Với lệnh ghi dữ liệu, `EXPLAIN ANALYZE` vẫn có thể gây side effect; trong bài ta chủ yếu đo SELECT.

## 26. Những lỗi thường gặp khi báo cáo thời gian có ngày rỗng

| Lỗi | Triệu chứng | Hướng xử lý |
| --- | --- | --- |
| Chỉ dùng `GROUP BY day` | Ngày không có sự kiện biến mất | Tạo calendar và LEFT JOIN |
| Chỉ thêm `COALESCE(COUNT(*),0)` vào GROUP BY fact | Vẫn thiếu hàng ngày | COALESCE không tự tạo nhóm |
| Đặt fact bên trái LEFT JOIN | Calendar không lấp được ngày trống | Calendar phải là phía được giữ |
| `COUNT(*)` sau LEFT JOIN trực tiếp | Ngày trống bị đếm 1 | `COUNT(fact.pk)` |
| `WHERE fact.status = ...` sau LEFT JOIN | Các ngày rỗng bị loại | Dùng `ON` hoặc `FILTER`/lọc CTE trước JOIN |
| Quên `COALESCE(SUM(...),0)` | Ngày thiếu cho doanh thu NULL | Áp dụng 0 khi đúng nghĩa metric |
| COALESCE mọi AVG thành 0 | Lẫn không có mẫu với trung bình bằng 0 | Giữ AVG NULL khi không có quan sát |
| Dùng `BETWEEN start AND end_day 00:00` | Mất dữ liệu phần lớn ngày cuối | Dùng khoảng nửa mở |
| Tạo `generate_series` đến `end_day` loại trừ | Thừa một ngày cuối | Stop ở end-1 hoặc dùng số bucket |
| GROUP BY `occurred_at::date` không quản lý timezone | Báo cáo đổi theo session timezone | Chỉ định timezone nghiệp vụ |
| Dùng 24 giờ cố định cho ngày ở vùng DST | Lệch ranh giới hoặc bỏ/nhân giờ | Dùng nửa đêm địa phương qua tên timezone |
| Dùng ngày UTC nhưng nhãn theo Việt Nam | Tổng ngày và nhãn không khớp | Dùng cùng quy tắc timezone |
| Sinh tháng bằng 30 ngày | Lệch tháng | Dùng `INTERVAL '1 month'` và mốc đầu tháng |
| Dùng mỗi `week_number` làm khóa | Gộp tuần khác năm | Dùng week_start hoặc ISOYEAR+WEEK |
| Tạo danh sách kênh bằng DISTINCT fact | Kênh hoàn toàn không có dữ liệu biến mất | Dùng bảng dimension độc lập |
| CROSS JOIN quá nhiều chiều | Số tổ hợp tăng cực lớn | Giới hạn dimension và độ phân giải |
| `LAG` trước khi gap fill | “Kỳ trước” thực ra là ngày có dữ liệu gần nhất | Lấp lịch trước rồi tính window |
| Rolling 7 ngày nhưng không có 6 ngày lịch sử | Đầu kỳ lấy trung bình thiếu mẫu | Đọc thêm ngày trước rồi mới lọc hiển thị |
| Mặc định mọi ô thiếu là 0 | Che sự cố ingest/pipeline | Kết hợp coverage/watermark |
| Ngày hiện tại chưa hoàn tất vẫn so cả ngày | Nhầm số liệu partial thành suy giảm | Gắn nhãn partial hoặc so sánh cùng giờ |
| Cast `occurred_at::date` trong WHERE | Có thể hạn chế index thường | Lọc trực tiếp theo khoảng timestamp |
| Đếm DISTINCT user sau khi JOIN fact nhiều chiều | Tổng có thể bị nhân | Kiểm soát cardinality trước aggregate |
| Không `ORDER BY` | Biểu đồ nhận các ngày xáo trộn | ORDER BY bucket rõ ràng |

## 27. Bài tập thực hành

Tất cả bài tập dùng dữ liệu `time_report_lab.orders` và `time_report_lab.channels` trong bài, trừ khi có ghi rõ.

### Bài 1. Vì sao ngày 02/10 không có trong GROUP BY?

```sql
SELECT
    (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS local_day,
    COUNT(*)
FROM time_report_lab.orders
GROUP BY 1
ORDER BY 1;
```

**Đáp án:** không có hàng nguồn nào thuộc ngày 02/10 theo timezone đó. `GROUP BY` không tự tạo nhóm khi không có hàng.

### Bài 2. Tạo đủ 14 ngày từ 01/10 đến 14/10

```sql
SELECT DATE '2026-10-01' + n AS local_day
FROM generate_series(0, 13) AS s(n)
ORDER BY local_day;
```

**Đáp án:** đúng 14 ngày, bao gồm 01/10 và 14/10, không có 15/10.

### Bài 3. Tạo ngày theo biến `start_day` và `end_day` loại trừ

```sql
WITH bounds AS (
    SELECT
        DATE '2026-10-01' AS start_day,
        DATE '2026-10-15' AS end_day
)
SELECT b.start_day + n AS local_day
FROM bounds AS b
CROSS JOIN LATERAL generate_series(
    0,
    b.end_day - b.start_day - 1
) AS s(n)
ORDER BY local_day;
```

**Đáp án:** 14 ngày; dùng hiệu hai ngày để tính số bucket.

### Bài 4. Ngày nào hoàn toàn không có đơn?

Dùng `calendar LEFT JOIN daily_fact` rồi lọc `f.local_day IS NULL`.

**Đáp án:** 02, 06, 07, 09, 11, 13 và 14/10/2026.

### Bài 5. Tại sao `COUNT(*)` sau LEFT JOIN lại báo 1 ở ngày rỗng?

**Đáp án:** LEFT JOIN vẫn tạo một hàng NULL-extended cho mỗi ngày không khớp. `COUNT(*)` đếm hàng đó. Dùng `COUNT(o.order_id)` để đếm đơn thật.

### Bài 6. Tính tổng doanh thu PAID 14 ngày

```sql
SELECT
    COALESCE(SUM(amount), 0::numeric) AS paid_revenue
FROM time_report_lab.orders
WHERE status = 'PAID'
  AND occurred_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND occurred_at <  TIMESTAMPTZ '2026-10-15 00:00:00+07';
```

**Đáp án:** `875.00`. Hai đơn ngoài khoảng và các đơn PENDING/CANCELLED không được cộng.

### Bài 7. Ngày 04/10 có revenue 0, có phải ngày rỗng không?

**Đáp án:** không. Ngày 04/10 có một đơn PAID có `amount = 0`. Metric doanh thu bằng 0 nhưng **paid_orders = 1**.

### Bài 8. Vì sao `WHERE o.status='PAID'` sau LEFT JOIN gây mất ngày?

**Đáp án:** ngày không khớp có `o.status NULL`; điều kiện ở WHERE không TRUE nên bị loại. Di chuyển điều kiện vào `ON` hoặc dùng `FILTER` trong aggregate.

### Bài 9. Khi nào không nên điền 0 cho `AVG`?

**Đáp án:** nếu không có đơn PAID nào trong ngày, average order value **không xác định**, nên giữ NULL hoặc trạng thái thiếu dữ liệu. Ngày có một đơn PAID bằng 0 thì trung bình mới là 0.

### Bài 10. Xây dựng báo cáo ngày × kênh, bao gồm kênh partner

**Gợi ý:** tạo calendar, `CROSS JOIN time_report_lab.channels` rồi LEFT JOIN daily aggregate theo cả `local_day` và `channel_code`.

**Đáp án:** 14 ngày × 3 kênh = **42 hàng**; partner có số liệu 0 ở toàn bộ 14 ngày.

### Bài 11. Báo cáo theo tháng từ tháng 7 đến tháng 12/2026

```sql
SELECT gs::date AS month_start
FROM generate_series(
    TIMESTAMP '2026-07-01',
    TIMESTAMP '2026-12-01',
    INTERVAL '1 month'
) AS s(gs);
```

**Đáp án:** sáu mốc đầu tháng. Để hiển thị số liệu 0, LEFT JOIN với aggregate theo `date_trunc('month', ...)::date`.

### Bài 12. Vì sao không dùng `INTERVAL '30 days'` để tạo tháng?

**Đáp án:** tháng lịch có độ dài khác nhau. Dùng các mốc đầu tháng và `INTERVAL '1 month'`.

### Bài 13. Vì sao `date_trunc('week', ...)` hữu ích hơn chỉ `EXTRACT(WEEK ...)`?

**Đáp án:** khóa ngày đầu tuần mang cả thông tin ngày-năm, không trộn các tuần cùng số ở những năm khác nhau. Với ISO week number, phải ghép cùng `ISOYEAR`.

### Bài 14. Lọc dữ liệu đến hết ngày 14/10 đúng cách

```sql
WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND occurred_at < TIMESTAMPTZ '2026-10-15 00:00:00+07'
```

**Đáp án:** bao gồm các thời điểm trong ngày 14/10 và loại đơn 1011 tại đúng 00:00 ngày 15/10.

### Bài 15. Có nên dùng `occurred_at::date` khi dashboard chạy ở nhiều timezone?

**Đáp án:** không nếu ngày báo cáo phải cố định theo timezone nghiệp vụ, vì `timestamptz::date` phụ thuộc `TimeZone` của session. Hãy dùng `(occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date` hoặc timezone theo hợp đồng API.

### Bài 16. Ngày DST chỉ có 23 giờ có phá calendar theo ngày không?

**Đáp án:** calendar theo `date + 1` vẫn tạo đúng **một hàng cho mỗi ngày lịch**. Tuy nhiên, phạm vi thời điểm của mỗi ngày phải tính bằng hai nửa đêm địa phương theo timezone tương ứng, không tự giả định 24 giờ tuyệt đối.

### Bài 17. Tại sao `LAG(revenue)` trên ngày có dữ liệu không phải lúc nào cũng là “hôm qua”?

**Đáp án:** nó trả hàng trước đó trong tập đang có. Nếu thiếu ngày 02/10, “hàng trước” của ngày 03/10 là ngày 01/10. Cần lấp calendar trước khi dùng LAG để so ngày liền kề.

### Bài 18. Tính trung bình trượt bảy ngày đầu kỳ cần thêm dữ liệu gì?

**Đáp án:** muốn có đủ bảy ngày ở ngày đầu báo cáo phải đọc **sáu ngày trước đó**, lấp đầy calendar cho cả khoảng mở rộng, tính window rồi mới lọc phần muốn hiển thị.

### Bài 19. Làm thế nào phân biệt “không có giao dịch” và “ETL chưa xong”?

**Đáp án:** dùng metadata như ingestion watermark, bảng `ingestion_days` hoặc trạng thái hoàn tất của mỗi nguồn/ngày; chỉ điền 0 sau khi dữ liệu được xác nhận đủ, còn ngày chưa đủ giữ NULL hoặc nhãn incomplete.

### Bài 20. Khi nào nên dùng bảng summary thay vì quét fact trực tiếp?

**Đáp án:** khi dashboard lặp đi lặp lại các tổng hợp trên khối dữ liệu rất lớn, nhưng cần thiết kế cập nhật dữ liệu muộn, idempotency, kiểm soát tính đúng và khả năng rebuild. Calendar vẫn có thể LEFT JOIN vào summary để điền bucket trống.

## 28. Checklist trước khi đưa báo cáo thời gian vào production

| Câu hỏi | Cần xác nhận |
| --- | --- |
| Trục báo cáo có đủ mốc không? | Số hàng mong đợi bằng số bucket |
| Khoảng thời gian là `[start,end)`? | Không bỏ sót hoặc đếm đôi ranh giới |
| Bucket là ngày/tuần/tháng/giờ? | Phù hợp người dùng cuối |
| Timezone nào xác định ngày? | Cùng timezone ở filter và group |
| Dữ liệu có ngày DST không? | Không gán mọi ngày bằng 24 giờ |
| `generate_series` có thừa stop? | Dãy mốc đúng cận cuối loại trừ |
| Có calendar độc lập không? | GROUP BY fact không tự sinh mốc rỗng |
| Calendar có ở phía trái LEFT JOIN? | Giữ mốc thiếu dữ liệu |
| Aggregate có dùng `COUNT(fact.pk)` khi JOIN trực tiếp? | Tránh ngày 0 bị đếm thành 1 |
| Điều kiện status có ở đúng nơi? | WHERE sau LEFT JOIN có thể loại ngày rỗng |
| Giá trị nào chuyển NULL thành 0? | SUM/COUNT khác AVG/ratio |
| Có cần hiện dữ liệu chưa hoàn tất? | Tách incomplete/unknown khỏi zero |
| Báo cáo nhiều channel/chi nhánh? | Grid có đủ dimension hợp lệ |
| Grid có quá lớn không? | Cân nhắc giới hạn nhóm/độ phân giải |
| Có dữ liệu đến muộn không? | Cơ chế cập nhật summary và watermark |
| Có bao gồm ngày hiện tại? | Gắn nhãn partial hoặc loại trừ |
| Query dùng index thời gian? | Điều kiện range trên cột gốc |
| Có ORDER BY ổn định? | Biểu đồ nhận đúng thứ tự |
| Có kiểm tra tổng đối chiếu? | Tổng bucket bằng tổng phạm vi nguồn |
| Có giới hạn request báo cáo? | Tránh dải hàng triệu bucket |
| Có test kỳ đặc biệt? | Tháng 2, năm nhuận, tuần ISO, DST, năm mới |

## 29. Tổng kết

Để xây dựng báo cáo PostgreSQL có **các khoảng thời gian không phát sinh dữ liệu**, cần tách rõ **trục thời gian mong muốn** và **những dữ liệu thực sự có trong bảng**.

Các nguyên tắc quan trọng:

1. **`GROUP BY` không tự tạo ngày không có dữ liệu.** Nó chỉ nhóm những hàng đang tồn tại.
2. **`generate_series` hoặc bảng calendar** tạo đủ trục ngày/giờ/tuần/tháng, kể cả mốc không có sự kiện.
3. **LEFT JOIN từ calendar sang fact** giữ tất cả mốc. Đừng đặt fact ở phía trái nếu mục tiêu là lấp ngày thiếu.
4. **`COALESCE` chỉ điền giá trị, không tạo hàng.** Dùng nó sau LEFT JOIN và chỉ khi 0 có ý nghĩa đúng cho metric.
5. **`COUNT(*)` sau LEFT JOIN trực tiếp có thể đếm sai.** Đếm khóa fact không NULL như `COUNT(order_id)`.
6. **`FILTER` và điều kiện `ON`** giúp tính metric theo trạng thái mà không vô tình lọc mất ngày rỗng bằng `WHERE`.
7. **Khoảng nửa mở `[start,end)`** giúp xử lý đúng biên, đặc biệt với timestamp có độ chính xác cao.
8. **Timezone quyết định ngày lịch.** Dùng cùng quy tắc timezone để lọc và gom bucket; chú ý những ngày DST có 23 hoặc 25 giờ.
9. **Tuần/tháng cần mốc lịch đúng**: dùng `date_trunc`, đầu tuần ISO, đầu tháng; không giả định tháng dài 30 ngày.
10. **Báo cáo nhiều chiều** cần calendar × dimension độc lập trước khi LEFT JOIN aggregate; nếu lấy dimension chỉ từ fact, những nhóm vắng mặt hoàn toàn vẫn bị thiếu.
11. **Window function** như `LAG` hoặc rolling average nên chạy sau khi lấp lịch nếu muốn so sánh các ngày liên tiếp.
12. **Không có dữ liệu chưa chắc là 0.** Nếu ETL chưa hoàn tất, phải phân biệt bằng trạng thái hoàn tất/watermark.
13. **Hiệu năng** đến từ lọc theo range trên timestamp, index đúng, tổng hợp sớm khi thích hợp và giới hạn số bucket/chiều của báo cáo.

Mẫu dễ nhớ nhất:

```sql
WITH
calendar AS (
    -- Sinh tất cả mốc mong muốn.
    SELECT ...
),
fact_summary AS (
    -- Tổng hợp dữ liệu thật theo đúng bucket/timezone.
    SELECT ...
)
SELECT
    c.bucket,
    COALESCE(f.count_metric, 0) AS count_metric
FROM calendar AS c
LEFT JOIN fact_summary AS f
    ON f.bucket = c.bucket
ORDER BY c.bucket;
```

Đây là **khung tư duy** chứ không phải lệnh SQL thực thi nguyên xi: thay dấu `...` bằng các biểu thức và bảng phù hợp như những truy vấn hoàn chỉnh ở các phần trên.

Khi trục thời gian được tạo độc lập, bạn có thể thể hiện chính xác cả **ngày có nhiều sự kiện**, **ngày có số đo thật bằng 0** và **ngày hoàn toàn không có sự kiện**. Kết hợp thêm metadata về độ hoàn tất dữ liệu, báo cáo sẽ không chỉ đẹp và liên tục trên biểu đồ, mà còn phản ánh trung thực trạng thái vận hành của hệ thống.

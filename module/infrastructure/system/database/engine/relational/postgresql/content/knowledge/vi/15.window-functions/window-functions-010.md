# Bài toán nhóm liên tiếp, top N mỗi nhóm và khử trùng lặp

Trong một cơ sở dữ liệu quan hệ, `GROUP BY` thông thường gom các hàng có cùng giá trị khóa thành một nhóm, nhưng nhiều bài toán thực tế cần hiểu thêm **thứ tự của các hàng bên trong từng nhóm**. Chẳng hạn:

- Một người dùng hoạt động **ba ngày liên tiếp**, nghỉ một ngày, rồi hoạt động thêm hai ngày. Cần tìm từng chuỗi ngày liên tục và độ dài của chuỗi.
- Một thiết bị phát trạng thái `READY → READY → ERROR → ERROR → READY`. Cần tìm **ba đoạn trạng thái liên tiếp**, không phải gom tất cả `READY` vào một nhóm.
- Mỗi khách hàng có hàng nghìn đơn hàng. Cần lấy **ba đơn mới nhất cho mỗi khách**, không phải ba đơn mới nhất của toàn hệ thống.
- Dữ liệu được nạp nhiều lần từ API có các bản ghi trùng `(tenant_id, event_key)`. Cần giữ bản **mới nhận nhất**, có quy tắc phá hòa rõ ràng, và tránh tái phát trùng lặp khi ghi đồng thời.

Những bài toán này là ứng dụng quan trọng của **hàm cửa sổ** (*window functions*) trong PostgreSQL. Khác `GROUP BY`, hàm cửa sổ có thể tính số thứ tự, xếp hạng, giá trị hàng trước hoặc tổng tích lũy **mà không làm mất ngay các hàng chi tiết**. Sau đó, một lớp truy vấn bên ngoài lọc hoặc tổng hợp theo kết quả đã tính.

Bài học tập trung vào ba họ kỹ thuật:

1. **Gaps and islands (khoảng trống và chuỗi liên tiếp):** đánh dấu khi một chuỗi bị ngắt bằng `LAG()`, hoặc biến hiệu giữa khóa liên tiếp và `ROW_NUMBER()` thành khóa nhóm.
2. **Top N mỗi nhóm:** sử dụng `ROW_NUMBER()`, `RANK()`, `DENSE_RANK()`, `DISTINCT ON` và `LATERAL` để chọn đúng số hàng hoặc giữ các trường hợp đồng hạng.
3. **Khử trùng lặp (deduplication):** định nghĩa thế nào là “trùng”, chọn bản ghi đại diện bằng thứ tự có thể giải thích được, rồi xử lý dữ liệu an toàn và bảo vệ khóa duy nhất.

> **Phạm vi:** SQL minh họa được viết cho PostgreSQL hiện đại. Hãy chạy phần tạo bảng và các lệnh xóa/cập nhật trong **database lab**, không trên dữ liệu production. Bài cung cấp cả các câu truy vấn đọc và ví dụ thao tác xóa để học cách thiết kế; lệnh xóa chỉ nên thực hiện sau khi xem trước tập bản ghi bị ảnh hưởng và có kế hoạch phục hồi.

## 1. Ôn lại hàm cửa sổ: PARTITION BY và ORDER BY

Một hàm cửa sổ được dùng với mệnh đề `OVER`:

```sql
function_name(...) OVER (
    PARTITION BY partition_key
    ORDER BY sort_key
)
```

Ý nghĩa:

| Thành phần | Công dụng |
|---|---|
| `PARTITION BY` | Chia những hàng đầu vào thành các **phân vùng tính toán** độc lập. |
| `ORDER BY` trong `OVER` | Định nghĩa thứ tự logic các hàng bên trong mỗi phân vùng. |
| `ROW_NUMBER()` | Đánh số 1, 2, 3, ... cho từng hàng trong mỗi phân vùng. |
| `RANK()` | Xếp hạng với các hàng đồng hạng và có khoảng nhảy sau nhóm đồng hạng. |
| `DENSE_RANK()` | Xếp hạng với đồng hạng nhưng không có khoảng nhảy hạng. |
| `LAG(expression)` | Đọc giá trị của hàng trước đó trong thứ tự của cửa sổ. |
| `LEAD(expression)` | Đọc giá trị của hàng sau đó. |
| `SUM(...) OVER (...)` | Có thể tạo tổng tích lũy để đánh số các đoạn liên tiếp. |

Ví dụ:

```sql
SELECT
    o.customer_id,
    o.order_id,
    o.placed_at,
    ROW_NUMBER() OVER (
        PARTITION BY o.customer_id
        ORDER BY o.placed_at DESC, o.order_id DESC
    ) AS order_position
FROM lesson_window_cases.orders AS o;
```

Tại mỗi khách hàng, hàng có `placed_at` mới nhất nhận `order_position = 1`. Nếu cùng thời điểm, `order_id DESC` là **khóa phụ phá hòa**. Nếu bỏ `PARTITION BY`, PostgreSQL sẽ đánh số trên **toàn bộ tập kết quả**, không khởi động lại ở mỗi khách.

### ORDER BY của window khác ORDER BY cuối truy vấn

```sql
SELECT
    customer_id,
    order_id,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY placed_at DESC, order_id DESC
    ) AS rn
FROM lesson_window_cases.orders
ORDER BY customer_id, rn;
```

- `ORDER BY` **trong `OVER`** quyết định hàng nhận `rn = 1`, `rn = 2`...
- `ORDER BY` **cuối truy vấn** quyết định cách hiển thị các hàng kết quả.

Hai thứ tự thường được chọn cho nhất quán, nhưng chúng có **mục đích khác nhau**. Kết quả cuối **không có thứ tự được bảo đảm** nếu thiếu `ORDER BY` ở tầng kết quả.

## 2. Chuẩn bị dữ liệu thực hành

Ta tạo schema riêng và bốn nhóm dữ liệu: khách hàng–đơn hàng, hoạt động theo ngày, thay đổi trạng thái thiết bị, và sự kiện nhận trùng.

```sql
CREATE SCHEMA IF NOT EXISTS lesson_window_cases;

CREATE TABLE lesson_window_cases.customers (
    customer_id BIGINT PRIMARY KEY,
    customer_name TEXT NOT NULL
);

CREATE TABLE lesson_window_cases.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES lesson_window_cases.customers(customer_id),
    placed_at TIMESTAMPTZ NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL
        CHECK (total_amount >= 0),
    status TEXT NOT NULL
        CHECK (status IN ('PAID', 'PENDING', 'CANCELLED'))
);

CREATE TABLE lesson_window_cases.daily_activity (
    activity_id BIGINT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    activity_date DATE NOT NULL,
    action_name TEXT NOT NULL
);

CREATE TABLE lesson_window_cases.device_states (
    state_id BIGINT PRIMARY KEY,
    device_id BIGINT NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL,
    state_name TEXT NOT NULL
);

CREATE TABLE lesson_window_cases.raw_events (
    event_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    event_key TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);
```

### 2.1. Khách hàng và đơn hàng

```sql
INSERT INTO lesson_window_cases.customers(customer_id, customer_name)
VALUES
    (1, 'An'),
    (2, 'Bình'),
    (3, 'Chi'),
    (4, 'Dung');

INSERT INTO lesson_window_cases.orders(
    order_id, customer_id, placed_at, total_amount, status
)
VALUES
    (1001, 1, TIMESTAMPTZ '2026-11-01 09:00:00+07',
        350000, 'PAID'),
    (1002, 1, TIMESTAMPTZ '2026-11-03 10:00:00+07',
        900000, 'PAID'),
    (1003, 1, TIMESTAMPTZ '2026-11-03 10:00:00+07',
        900000, 'PENDING'),
    (1004, 1, TIMESTAMPTZ '2026-11-05 12:00:00+07',
        250000, 'PAID'),
    (2001, 2, TIMESTAMPTZ '2026-11-02 08:00:00+07',
        1000000, 'PAID'),
    (2002, 2, TIMESTAMPTZ '2026-11-04 09:00:00+07',
        1000000, 'PAID'),
    (2003, 2, TIMESTAMPTZ '2026-11-04 14:00:00+07',
        400000, 'PENDING'),
    (3001, 3, TIMESTAMPTZ '2026-11-06 08:00:00+07',
        600000, 'PAID');
```

Đặc điểm:

- **An:** bốn đơn, có **hai đơn đồng hạng giá trị 900.000** và **hai đơn cùng thời điểm** `2026-11-03 10:00+07`.
- **Bình:** ba đơn, hai đơn có giá trị 1.000.000 nhưng thời điểm khác nhau.
- **Chi:** một đơn.
- **Dung:** chưa có đơn, giúp kiểm tra sự khác nhau giữa `INNER JOIN` và `LEFT JOIN LATERAL`.

### 2.2. Hoạt động theo ngày có cả bản ghi trùng ngày

```sql
INSERT INTO lesson_window_cases.daily_activity(
    activity_id, user_id, activity_date, action_name
)
VALUES
    (1, 1, DATE '2026-11-01', 'login'),
    (2, 1, DATE '2026-11-01', 'open_page'),
    (3, 1, DATE '2026-11-02', 'login'),
    (4, 1, DATE '2026-11-03', 'login'),
    (5, 1, DATE '2026-11-05', 'login'),
    (6, 1, DATE '2026-11-06', 'upload'),
    (7, 1, DATE '2026-11-09', 'login'),
    (8, 2, DATE '2026-11-01', 'login'),
    (9, 2, DATE '2026-11-03', 'login'),
    (10, 2, DATE '2026-11-04', 'login'),
    (11, 2, DATE '2026-11-05', 'upload');
```

Với người dùng 1:

```text
01  02  03  04  05  06  07  08  09/11
 ●───●───●    ·   ●───●    ·   ·   ●
 └─ 3 ngày ─┘      └ 2 ngày ┘        └1┘
```

Ngày 01/11 có **hai event**, nhưng chỉ tính là **một ngày hoạt động** khi mục tiêu là đếm streak theo ngày.

### 2.3. Chuỗi trạng thái thiết bị

```sql
INSERT INTO lesson_window_cases.device_states(
    state_id, device_id, changed_at, state_name
)
VALUES
    (1, 10, TIMESTAMPTZ '2026-11-14 09:00:00+07', 'READY'),
    (2, 10, TIMESTAMPTZ '2026-11-14 09:05:00+07', 'READY'),
    (3, 10, TIMESTAMPTZ '2026-11-14 09:10:00+07', 'ERROR'),
    (4, 10, TIMESTAMPTZ '2026-11-14 09:20:00+07', 'ERROR'),
    (5, 10, TIMESTAMPTZ '2026-11-14 09:25:00+07', 'READY'),
    (6, 20, TIMESTAMPTZ '2026-11-14 08:00:00+07', 'OFFLINE'),
    (7, 20, TIMESTAMPTZ '2026-11-14 08:30:00+07', 'READY');
```

### 2.4. Sự kiện bị nhận trùng

```sql
INSERT INTO lesson_window_cases.raw_events(
    event_id, tenant_id, event_key, received_at, payload
)
VALUES
    (5001, 1, 'evt-A',
        TIMESTAMPTZ '2026-11-10 09:00:00+07',
        '{"version":1}'::jsonb),
    (5002, 1, 'evt-A',
        TIMESTAMPTZ '2026-11-11 09:00:00+07',
        '{"version":2}'::jsonb),
    (5003, 1, 'evt-A',
        TIMESTAMPTZ '2026-11-11 09:00:00+07',
        '{"version":3}'::jsonb),
    (5004, 1, 'evt-B',
        TIMESTAMPTZ '2026-11-12 10:00:00+07',
        '{"version":1}'::jsonb),
    (6001, 2, 'evt-A',
        TIMESTAMPTZ '2026-11-12 11:00:00+07',
        '{"version":1}'::jsonb),
    (6002, 2, 'evt-C',
        TIMESTAMPTZ '2026-11-12 11:10:00+07',
        '{"version":1}'::jsonb),
    (6003, 2, 'evt-C',
        TIMESTAMPTZ '2026-11-13 11:10:00+07',
        '{"version":2}'::jsonb);
```

Ở `tenant_id = 1`, key `evt-A` có ba bản ghi; hai bản mới nhất **cùng `received_at`**, nên cần `event_id` làm tiêu chí phá hòa. `tenant_id = 2` cũng có `evt-A`, nhưng đó là **một khóa nghiệp vụ khác** nếu đơn vị duy nhất là cặp `(tenant_id, event_key)`.

## 3. Vì sao GROUP BY đơn thuần không tìm được nhóm liên tiếp?

Đặt câu hỏi: “Thiết bị 10 có bao nhiêu **đoạn READY liên tiếp**?”

Nếu chạy:

```sql
SELECT
    device_id,
    state_name,
    COUNT(*) AS observations
FROM lesson_window_cases.device_states
GROUP BY device_id, state_name
ORDER BY device_id, state_name;
```

Thiết bị 10 có ba quan sát `READY`, nhưng chúng không thuộc **một đoạn liên tục**:

```text
09:00 READY
09:05 READY
---------------- chuyển trạng thái
09:10 ERROR
09:20 ERROR
---------------- chuyển trạng thái
09:25 READY
```

`GROUP BY (device_id, state_name)` gộp cả ba quan sát `READY` vào một nhóm, làm mất thông tin có đoạn `ERROR` ở giữa. Để tìm đúng **runs**, cần biết **khi nào trạng thái thay đổi theo thứ tự thời gian**.

Điểm mấu chốt của bài toán nhóm liên tiếp:

> Hai hàng có giá trị giống nhau **không nhất thiết thuộc cùng một đoạn** nếu giữa chúng có sự gián đoạn theo thứ tự nghiệp vụ.

Đó là lý do phải dùng `ORDER BY` trong window trước khi đặt nhãn nhóm.

## 4. Gaps and islands: hai khái niệm nền tảng

**Island** là một dãy các hàng tạo thành một chuỗi liên tiếp theo quy tắc xác định. **Gap** là chỗ gián đoạn giữa các chuỗi.

Đối với ngày hoạt động:

```text
01 02 03 [04 không hoạt động] 05 06 [07 08 không] 09
└ Island A ┘                   └ B ┘                 └ C ┘
```

Nhưng “liên tiếp” có thể mang nhiều ý nghĩa:

- Các ngày lịch liền nhau: `current_date = previous_date + 1`.
- Các ngày làm việc liền nhau, bỏ cuối tuần và ngày nghỉ.
- Các bản ghi số thứ tự tăng đúng một đơn vị.
- Các lần đo cách nhau **không quá 30 phút**.
- Các dòng có **cùng trạng thái** đứng cạnh nhau.
- Các khoảng thời gian **giao nhau hoặc kề nhau**.

Không tồn tại một công thức duy nhất phù hợp mọi trường hợp. Bạn phải định nghĩa rõ **khóa phân vùng**, **khóa sắp xếp** và **quy tắc đánh dấu gián đoạn**.

## 5. Kỹ thuật 1: ngày liên tiếp bằng ROW_NUMBER và phép trừ

Với một tập **ngày duy nhất cho mỗi user**, nếu các ngày tăng từng ngày và số thứ tự tăng từng đơn vị, thì:

```text
Ngày        ROW_NUMBER   Ngày - ROW_NUMBER ngày
01/11       1            31/10
02/11       2            31/10
03/11       3            31/10
05/11       4            01/11  ← khóa đổi do khoảng trống
06/11       5            01/11
09/11       6            03/11  ← khóa đổi lần nữa
```

Trong PostgreSQL, phép `date - integer` trả về ngày lùi số ngày tương ứng. Đây là cách tạo **khóa đảo** cho mỗi island.

### Bước 1 — Loại bản ghi trùng ngày

```sql
WITH active_days AS (
    SELECT DISTINCT user_id, activity_date
    FROM lesson_window_cases.daily_activity
)
SELECT user_id, activity_date
FROM active_days
ORDER BY user_id, activity_date;
```

Vì người dùng 1 có hai action vào 01/11, `DISTINCT` là cần thiết nếu yêu cầu **streak theo ngày**, không phải streak theo từng event.

### Bước 2 — Đánh số ngày theo từng người

```sql
WITH active_days AS (
    SELECT DISTINCT user_id, activity_date
    FROM lesson_window_cases.daily_activity
)
SELECT
    user_id,
    activity_date,
    ROW_NUMBER() OVER (
        PARTITION BY user_id
        ORDER BY activity_date
    ) AS rn
FROM active_days
ORDER BY user_id, activity_date;
```

`PARTITION BY user_id` giúp mỗi người có dãy số bắt đầu lại từ 1. Vì mỗi user chỉ còn một hàng cho mỗi ngày, `ORDER BY activity_date` đã xác định thứ tự đầy đủ trong phân vùng.

### Bước 3 — Tạo khóa island

```sql
WITH active_days AS (
    SELECT DISTINCT user_id, activity_date
    FROM lesson_window_cases.daily_activity
),
numbered AS (
    SELECT
        user_id,
        activity_date,
        ROW_NUMBER() OVER (
            PARTITION BY user_id
            ORDER BY activity_date
        ) AS rn
    FROM active_days
)
SELECT
    user_id,
    activity_date,
    rn,
    activity_date - rn::integer AS island_key
FROM numbered
ORDER BY user_id, activity_date;
```

Với chuỗi các ngày thật sự liên tiếp, `activity_date` và `rn` đều tăng một đơn vị, nên hiệu giữ nguyên. Khi bỏ qua một ngày, hiệu thay đổi và đánh dấu island mới.

### Bước 4 — Tổng hợp các island

```sql
WITH active_days AS (
    SELECT DISTINCT user_id, activity_date
    FROM lesson_window_cases.daily_activity
),
numbered AS (
    SELECT
        user_id,
        activity_date,
        activity_date
          - ROW_NUMBER() OVER (
                PARTITION BY user_id
                ORDER BY activity_date
            )::integer AS island_key
    FROM active_days
)
SELECT
    user_id,
    MIN(activity_date) AS streak_start,
    MAX(activity_date) AS streak_end,
    COUNT(*) AS days_in_streak
FROM numbered
GROUP BY user_id, island_key
ORDER BY user_id, streak_start;
```

Kết quả dự kiến:

| user_id | streak_start | streak_end | days_in_streak |
|---:|---|---|---:|
| 1 | 2026-11-01 | 2026-11-03 | 3 |
| 1 | 2026-11-05 | 2026-11-06 | 2 |
| 1 | 2026-11-09 | 2026-11-09 | 1 |
| 2 | 2026-11-01 | 2026-11-01 | 1 |
| 2 | 2026-11-03 | 2026-11-05 | 3 |

Đây là mẫu **row-number difference** rất gọn, phù hợp khi liên tiếp có nghĩa **tăng chính xác một đơn vị** theo ngày/số nguyên.

### Giới hạn của kỹ thuật này

1. Phải **loại trùng** theo khóa cần xét trước khi đánh số. Nếu có hai event cùng ngày, `rn` tăng nhưng ngày không tăng, làm sai nhóm.
2. Nó giả định mỗi bước liên tiếp là **một ngày lịch** hoặc một đơn vị khóa có phép toán tương ứng.
3. `ROW_NUMBER()` trả `bigint`; ví dụ ép sang `integer` để dùng toán tử `date - integer`. Với dữ liệu cực lớn, phải xét giới hạn ép kiểu.
4. Không dùng trực tiếp công thức này để tính **ngày làm việc liên tiếp** nếu cuối tuần/ngày nghỉ được bỏ qua.
5. Đừng áp dụng máy móc cho timestamp có khoảng thời gian biến thiên hoặc timezone/DST.

## 6. Kỹ thuật 2: dùng LAG để phát hiện ngày bị gián đoạn

`LAG(value)` trả giá trị của **hàng trước trong thứ tự cửa sổ**.

Đầu tiên:

```sql
WITH active_days AS (
    SELECT DISTINCT user_id, activity_date
    FROM lesson_window_cases.daily_activity
)
SELECT
    user_id,
    activity_date,
    LAG(activity_date) OVER (
        PARTITION BY user_id
        ORDER BY activity_date
    ) AS previous_day
FROM active_days
ORDER BY user_id, activity_date;
```

Với người dùng 1:

```text
activity_date  previous_day
2026-11-01     NULL
2026-11-02     2026-11-01
2026-11-03     2026-11-02
2026-11-05     2026-11-03  ← thiếu 04/11
2026-11-06     2026-11-05
2026-11-09     2026-11-06  ← thiếu 07-08/11
```

### Đánh dấu đầu một island

Một ngày là **đầu island** khi:

- Nó là hàng đầu tiên (`previous_day IS NULL`), hoặc
- Nó **không bằng** `previous_day + 1`.

```sql
WITH active_days AS (
    SELECT DISTINCT user_id, activity_date
    FROM lesson_window_cases.daily_activity
),
with_previous AS (
    SELECT
        user_id,
        activity_date,
        LAG(activity_date) OVER (
            PARTITION BY user_id
            ORDER BY activity_date
        ) AS previous_day
    FROM active_days
)
SELECT
    user_id,
    activity_date,
    previous_day,
    CASE
        WHEN previous_day IS NULL
          OR activity_date <> previous_day + 1
        THEN 1
        ELSE 0
    END AS starts_new_island
FROM with_previous
ORDER BY user_id, activity_date;
```

### Tạo số island bằng SUM tích lũy

Mỗi khi gặp một mốc bắt đầu mới, cộng 1 vào tổng tích lũy:

```sql
WITH active_days AS (
    SELECT DISTINCT user_id, activity_date
    FROM lesson_window_cases.daily_activity
),
with_previous AS (
    SELECT
        user_id,
        activity_date,
        LAG(activity_date) OVER (
            PARTITION BY user_id
            ORDER BY activity_date
        ) AS previous_day
    FROM active_days
),
marked AS (
    SELECT
        user_id,
        activity_date,
        CASE
            WHEN previous_day IS NULL
              OR activity_date <> previous_day + 1
            THEN 1
            ELSE 0
        END AS new_group_flag
    FROM with_previous
),
labeled AS (
    SELECT
        user_id,
        activity_date,
        SUM(new_group_flag) OVER (
            PARTITION BY user_id
            ORDER BY activity_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS island_id
    FROM marked
)
SELECT
    user_id,
    island_id,
    MIN(activity_date) AS streak_start,
    MAX(activity_date) AS streak_end,
    COUNT(*) AS days_in_streak
FROM labeled
GROUP BY user_id, island_id
ORDER BY user_id, streak_start;
```

Kết quả về chuỗi liên tục giống kỹ thuật `ROW_NUMBER` phía trên, nhưng cách `LAG + SUM` linh hoạt hơn: điều kiện tạo nhóm mới có thể được thay bằng quy tắc nghiệp vụ bất kỳ.

### Vì sao ghi rõ ROWS frame?

Với aggregate window có `ORDER BY`, PostgreSQL có các quy tắc window frame mặc định, thường liên quan tới **peer rows** (các hàng bằng nhau theo sort key). Viết:

```sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

để diễn đạt trực tiếp **cộng theo từng hàng**. Ngoài ra, cần có sort key xác định để tránh thứ tự các hàng đồng giá trị bị mơ hồ. Trong ví dụ đã `DISTINCT` theo ngày, nên mỗi ngày trong một user chỉ còn một hàng.

## 7. Chọn kỹ thuật gaps-and-islands nào?

| Tiêu chí | `ROW_NUMBER` và khóa hiệu | `LAG`, đánh dấu, `SUM` |
|---|---|---|
| Liên tiếp nghĩa là +1 ngày/số | Rất ngắn gọn. | Hoạt động tốt nhưng nhiều bước. |
| Có điều kiện khoảng cách tối đa | Khó diễn đạt trực tiếp. | Phù hợp vì đổi điều kiện tại mốc chuyển. |
| Chuỗi trạng thái giống nhau | Cần kỹ thuật xếp hạng đặc thù. | Rất tự nhiên với `LAG(status)`. |
| Cho phép dữ liệu trùng khóa thứ tự | Phải xử lý trước. | Phải xác định sort key/tie-breaker. |
| Cần giải thích vì sao nhóm mới | Khóa hiệu ngầm thể hiện gap. | Cờ `new_group_flag` giải thích trực tiếp. |
| Cần định nghĩa ngày làm việc | Phải ánh xạ lên số thứ tự lịch kinh doanh. | Có thể so ngày hiện tại với ngày làm việc trước đó. |

Không cần cố dùng một kỹ thuật cho mọi thứ. Chọn **công thức đơn giản nhất diễn đạt đúng định nghĩa “liên tiếp”**.

## 8. Nhóm các đoạn trạng thái liên tiếp bằng LAG

Với bảng `device_states`, mỗi thiết bị có chuỗi trạng thái theo thời điểm.

```sql
WITH ordered AS (
    SELECT
        device_id,
        state_id,
        changed_at,
        state_name,
        LAG(state_name) OVER (
            PARTITION BY device_id
            ORDER BY changed_at, state_id
        ) AS previous_state
    FROM lesson_window_cases.device_states
),
marked AS (
    SELECT
        *,
        CASE
            WHEN state_name IS DISTINCT FROM previous_state
            THEN 1
            ELSE 0
        END AS starts_new_run
    FROM ordered
),
labeled AS (
    SELECT
        *,
        SUM(starts_new_run) OVER (
            PARTITION BY device_id
            ORDER BY changed_at, state_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS run_id
    FROM marked
)
SELECT
    device_id,
    run_id,
    state_name,
    MIN(changed_at) AS first_observed_at,
    MAX(changed_at) AS last_observed_at,
    COUNT(*) AS observation_count
FROM labeled
GROUP BY device_id, run_id, state_name
ORDER BY device_id, first_observed_at;
```

Với device 10:

| run_id | state_name | observation_count |
|---:|---|---:|
| 1 | READY | 2 |
| 2 | ERROR | 2 |
| 3 | READY | 1 |

**Tại sao dùng `state_id` trong `ORDER BY`?** Nếu hai hàng có cùng `changed_at`, thứ tự thời gian một mình chưa đủ để quyết định hàng nào đứng trước. `state_id` tạo **tie-breaker** trong bộ dữ liệu mẫu.

### Tính đúng thời lượng trạng thái là bài toán khác

`MIN(changed_at)` và `MAX(changed_at)` chỉ cho **thời điểm quan sát đầu/cuối của từng run**, không tự chứng minh trạng thái kéo dài bao lâu. Nếu dữ liệu là các **sự kiện chuyển trạng thái**, khoảng hiệu lực có thể kết thúc khi **sự kiện của run kế tiếp** xuất hiện.

Muốn tính thời lượng, cần định nghĩa rõ:

- Mốc nào là **thời điểm trạng thái bắt đầu**.
- Có phải mỗi hàng là **quan sát lặp lại** hay chỉ sự kiện thay đổi.
- Khi không có sự kiện kế tiếp, kết thúc là `NULL`, `now()` hay theo cửa sổ báo cáo.
- Nếu có sự kiện đến muộn, trạng thái lịch sử có được điều chỉnh không.

Không lấy `MAX - MIN` của những quan sát lặp lại làm toàn bộ thời lượng hoạt động nếu không có bằng chứng nghiệp vụ.

## 9. Dùng LAG với trạng thái có thể NULL

Hàm `LAG(state_name)` của hàng đầu tiên trả SQL `NULL` theo mặc định. Nếu `state_name` cũng có thể thật sự là `NULL`, cần **phân biệt hàng đầu với một trạng thái null**.

Với schema lab, `state_name TEXT NOT NULL` nên:

```sql
state_name IS DISTINCT FROM previous_state
```

đủ để đánh dấu hàng đầu như một thay đổi, vì `state_name` không null và `previous_state` của hàng đầu null.

Nếu status nullable, có thể dùng thêm `ROW_NUMBER()` để nhận biết hàng đầu:

```sql
WITH ordered AS (
    SELECT
        device_id,
        state_id,
        changed_at,
        state_name,
        ROW_NUMBER() OVER (
            PARTITION BY device_id
            ORDER BY changed_at, state_id
        ) AS rn,
        LAG(state_name) OVER (
            PARTITION BY device_id
            ORDER BY changed_at, state_id
        ) AS previous_state
    FROM lesson_window_cases.device_states
)
SELECT
    *,
    CASE
        WHEN rn = 1
          OR state_name IS DISTINCT FROM previous_state
        THEN 1
        ELSE 0
    END AS starts_new_run
FROM ordered;
```

Với cách này, một chuỗi `NULL, NULL` được coi cùng một trạng thái **nếu nghiệp vụ định nghĩa null là một loại trạng thái hợp lệ**. Nếu null nghĩa là thiếu dữ liệu và phải ngắt chuỗi, cần điều kiện khác.

## 10. Sessionization: nhóm sự kiện cách nhau không quá N phút

Một cách dùng rất thực tế của gaps-and-islands là phân chia **phiên hoạt động**. Ví dụ, một người dùng có các event lúc 10:00, 10:10, 10:40, 11:20 và 11:35.

Quy tắc: **bắt đầu session mới nếu khoảng cách giữa hai sự kiện liên tiếp lớn hơn 30 phút**.

```text
10:00 ──10:10 ──────10:40       11:20 ──11:35
   │       │          │           │       │
   └─ 10' ─┘── 30' ───┘           └─15' ──┘

Session 1                     Session 2
          gap 40 phút > 30
```

Tạo ví dụ bằng CTE `VALUES`:

```sql
WITH events(event_id, user_id, event_at) AS (
    VALUES
        (1, 7, TIMESTAMPTZ '2026-11-14 10:00:00+07'),
        (2, 7, TIMESTAMPTZ '2026-11-14 10:10:00+07'),
        (3, 7, TIMESTAMPTZ '2026-11-14 10:40:00+07'),
        (4, 7, TIMESTAMPTZ '2026-11-14 11:20:00+07'),
        (5, 7, TIMESTAMPTZ '2026-11-14 11:35:00+07')
),
with_previous AS (
    SELECT
        *,
        LAG(event_at) OVER (
            PARTITION BY user_id
            ORDER BY event_at, event_id
        ) AS previous_event_at
    FROM events
),
marked AS (
    SELECT
        *,
        CASE
            WHEN previous_event_at IS NULL
              OR event_at > previous_event_at + INTERVAL '30 minutes'
            THEN 1
            ELSE 0
        END AS starts_new_session
    FROM with_previous
),
labeled AS (
    SELECT
        *,
        SUM(starts_new_session) OVER (
            PARTITION BY user_id
            ORDER BY event_at, event_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS session_no
    FROM marked
)
SELECT
    user_id,
    session_no,
    MIN(event_at) AS session_start,
    MAX(event_at) AS session_last_event,
    COUNT(*) AS event_count
FROM labeled
GROUP BY user_id, session_no
ORDER BY user_id, session_start;
```

Kết quả: session 1 có **3 event**, session 2 có **2 event**.

### So sánh với thời điểm đầu session là sai quy tắc

Quy tắc ở đây so khoảng cách với **event ngay trước**, không phải so với event đầu tiên của session. Ví dụ 10:00, 10:25, 10:50 có thể cùng session do hai khoảng 25 phút, dù event cuối cách event đầu 50 phút.

### Ranh giới bằng đúng ngưỡng

Do điều kiện là:

```sql
event_at > previous_event_at + INTERVAL '30 minutes'
```

hai event cách **đúng 30 phút** vẫn thuộc cùng session. Nếu nghiệp vụ quy định khoảng cách **từ 30 phút trở lên** là session mới, thay `>` bằng `>=`.

## 11. Nhóm ngày làm việc liên tiếp

Câu “người dùng hoạt động 5 ngày liên tiếp” có thể mang hai nghĩa:

1. **5 ngày lịch**: thứ Sáu đến thứ Hai có hai ngày nghỉ ở giữa, nên không liên tiếp.
2. **5 ngày làm việc**: thứ Sáu đến thứ Hai có thể được coi nối tiếp nếu lịch loại cuối tuần.

Với nghiệp vụ ngày làm việc, cần bảng calendar riêng, ví dụ:

```text
business_calendar
calendar_date  is_business_day  business_day_no
2026-11-13    true             101
2026-11-14    false            NULL
2026-11-15    false            NULL
2026-11-16    true             102
```

Đây là **sơ đồ ý tưởng**, không phải dữ liệu được tạo trong schema lab. Cột `business_day_no` là một dãy số tăng một đơn vị cho mỗi ngày làm việc.

Sau khi join hoạt động với lịch và loại ngày nghỉ, kỹ thuật `business_day_no - ROW_NUMBER()` có thể nhóm các ngày làm việc nối tiếp. Đừng dùng `date - row_number` trực tiếp rồi mong PostgreSQL tự bỏ thứ Bảy, Chủ nhật hoặc lịch nghỉ của công ty.

Một giải pháp khác dùng `LAG` để so ngày hoạt động hiện tại với **ngày làm việc kế tiếp của ngày trước** theo calendar, rồi đánh dấu island.

## 12. Nhiều hàng cùng sort key: peer rows và thứ tự xác định

Khi viết:

```sql
ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY placed_at DESC
)
```

nếu hai đơn có cùng `placed_at`, PostgreSQL **không được yêu cầu** chọn đơn nào nhận số 1, số 2. Chúng là **peer rows** theo khóa sắp xếp ấy.

Để quyết định duy nhất:

```sql
ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY placed_at DESC, order_id DESC
)
```

`order_id` là khóa chính nên mỗi hàng trong phân vùng phân biệt được.

### Vì sao ảnh hưởng đến dedup?

Khi giữ `rn = 1` rồi xóa `rn > 1`, nếu không có tie-breaker, **bản ghi được giữ có thể không được xác định bởi nghiệp vụ**. Không nên xóa dữ liệu chỉ dựa vào `ORDER BY received_at DESC` khi nhiều hàng cùng `received_at`.

### Cẩn thận NULL trong khóa sort

Với cột nullable, quyết định trước:

```sql
ORDER BY processed_at DESC NULLS LAST, record_id DESC
```

Trong PostgreSQL, mặc định vị trí null phụ thuộc hướng `ASC`/`DESC`; viết `NULLS FIRST` hoặc `NULLS LAST` rõ ràng giúp tránh chọn một bản ghi chưa có timestamp làm bản ghi “mới nhất”.

## 13. Top N toàn hệ thống khác top N mỗi nhóm

Truy vấn:

```sql
SELECT order_id, customer_id, placed_at
FROM lesson_window_cases.orders
ORDER BY placed_at DESC, order_id DESC
LIMIT 2;
```

chỉ trả **hai đơn mới nhất trên toàn hệ thống**.

Nếu cần **hai đơn mới nhất của mỗi khách hàng**, ta cần tính thứ tự **riêng từng customer_id**:

```sql
WITH ranked_orders AS (
    SELECT
        o.*,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.placed_at DESC, o.order_id DESC
        ) AS rn
    FROM lesson_window_cases.orders AS o
)
SELECT
    customer_id,
    order_id,
    placed_at,
    total_amount,
    rn
FROM ranked_orders
WHERE rn <= 2
ORDER BY customer_id, rn;
```

Kết quả về ID:

| customer_id | rn | order_id | Giải thích |
|---:|---:|---:|---|
| 1 | 1 | 1004 | Ngày 05/11, mới nhất của An. |
| 1 | 2 | 1003 | Cùng timestamp với 1002 nhưng ID lớn hơn. |
| 2 | 1 | 2003 | Ngày 04/11 lúc 14:00. |
| 2 | 2 | 2002 | Ngày 04/11 lúc 09:00. |
| 3 | 1 | 3001 | Chi chỉ có một đơn. |

Khách **Dung** không có đơn nên không xuất hiện trong truy vấn lấy nguồn từ `orders`.

### Vì sao phải bọc CTE/subquery?

Trong cùng query block, PostgreSQL không cho phép dùng kết quả window function trực tiếp ở `WHERE` như:

```sql
-- Không hợp lệ:
SELECT *
FROM lesson_window_cases.orders
WHERE ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY placed_at DESC
) <= 2;
```

Hàm cửa sổ được tính ở giai đoạn logic sau `WHERE`, nên cần **CTE hoặc derived table** để xuất `rn` thành một cột nguồn của query ngoài:

```sql
SELECT *
FROM (
    SELECT
        o.*,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY placed_at DESC, order_id DESC
        ) AS rn
    FROM lesson_window_cases.orders AS o
) AS ranked
WHERE ranked.rn <= 2;
```

`QUALIFY` xuất hiện trong một số hệ SQL khác nhưng không nên giả định có thể sử dụng trực tiếp trong môi trường PostgreSQL của bài này. Mẫu CTE/subquery vẫn là cách diễn đạt rõ ràng và phổ biến.

## 14. ROW_NUMBER, RANK và DENSE_RANK khác nhau thế nào?

Giả sử có dãy giá trị từ cao xuống thấp:

```text
900   900   500   300
```

Kết quả xếp hạng:

| total_amount | ROW_NUMBER | RANK | DENSE_RANK |
|---:|---:|---:|---:|
| 900 | 1 | 1 | 1 |
| 900 | 2 | 1 | 1 |
| 500 | 3 | 3 | 2 |
| 300 | 4 | 4 | 3 |

- **`ROW_NUMBER()`:** mỗi hàng một số thứ tự, kể cả đồng giá trị. Muốn ổn định phải có tie-breaker.
- **`RANK()`:** các hàng đồng hạng nhận cùng rank; hạng sau có **khoảng nhảy**.
- **`DENSE_RANK()`:** các hàng đồng hạng nhận cùng rank; hạng sau **không nhảy**.

Minh họa trên khách An:

```sql
SELECT
    customer_id,
    order_id,
    total_amount,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY total_amount DESC, order_id DESC
    ) AS row_no,
    RANK() OVER (
        PARTITION BY customer_id
        ORDER BY total_amount DESC
    ) AS amount_rank,
    DENSE_RANK() OVER (
        PARTITION BY customer_id
        ORDER BY total_amount DESC
    ) AS amount_dense_rank
FROM lesson_window_cases.orders
WHERE customer_id = 1
ORDER BY total_amount DESC, order_id DESC;
```

**Điểm rất dễ sai:** `RANK()`/`DENSE_RANK()` xác định đồng hạng dựa trên **toàn bộ `ORDER BY` của chính hàm ấy**. Nếu bạn thêm `order_id` (duy nhất) vào `ORDER BY` của `RANK()`, hai đơn cùng `total_amount` sẽ không còn là đồng hạng trong window đó.

Do vậy, khi muốn **giữ các đơn đồng hạng theo giá tiền**, dùng `ORDER BY total_amount DESC` trong `RANK()`, còn khi muốn **chọn đúng một hàng** thì dùng `ROW_NUMBER()` với khóa phụ.

## 15. “Top 2” có ít nhất ba nghĩa

Với giá trị của An là `900, 900, 350, 250`:

### Cách A — Đúng hai hàng

```sql
WITH ranked AS (
    SELECT
        o.*,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY total_amount DESC, order_id DESC
        ) AS rn
    FROM lesson_window_cases.orders AS o
)
SELECT customer_id, order_id, total_amount
FROM ranked
WHERE rn <= 2
ORDER BY customer_id, rn;
```

Mỗi nhóm có **tối đa 2 hàng**. Đồng giá trị vẫn phải lựa chọn đúng số hàng theo tie-breaker.

### Cách B — Hai vị trí xếp hạng đầu, giữ đồng hạng

```sql
WITH ranked AS (
    SELECT
        o.*,
        RANK() OVER (
            PARTITION BY customer_id
            ORDER BY total_amount DESC
        ) AS rnk
    FROM lesson_window_cases.orders AS o
)
SELECT customer_id, order_id, total_amount, rnk
FROM ranked
WHERE rnk <= 2
ORDER BY customer_id, rnk, order_id;
```

An có hai đơn giá 900 cùng rank 1; giá 350 có rank 3, nên **không xuất hiện**. Đây là “top 2 vị trí với đồng hạng”, không phải “hai mức giá khác nhau”.

### Cách C — Hai mức giá trị cao nhất, giữ tất cả hàng đồng mức

```sql
WITH ranked AS (
    SELECT
        o.*,
        DENSE_RANK() OVER (
            PARTITION BY customer_id
            ORDER BY total_amount DESC
        ) AS drnk
    FROM lesson_window_cases.orders AS o
)
SELECT customer_id, order_id, total_amount, drnk
FROM ranked
WHERE drnk <= 2
ORDER BY customer_id, drnk, order_id;
```

An có **ba hàng**: hai đơn giá 900 và một đơn giá 350. Đây là “hai mức giá cao nhất”, không phải “hai đơn cao nhất”.

**Không dùng ba hàm thay thế cho nhau chỉ vì đều có chữ rank hoặc number.** Cần hỏi yêu cầu nghiệp vụ có cho phép **trả nhiều hơn N hàng khi đồng hạng** không, và đồng hạng theo **những cột nào**.

## 16. FETCH FIRST ... WITH TIES

PostgreSQL ở các phiên bản hỗ trợ cú pháp này cho phép giữ thêm các hàng đồng hạng ở ranh giới của truy vấn `ORDER BY`:

```sql
SELECT
    order_id,
    total_amount
FROM lesson_window_cases.orders
WHERE customer_id = 1
ORDER BY total_amount DESC
FETCH FIRST 2 ROWS WITH TIES;
```

Câu trên chọn **hai vị trí đầu** theo `total_amount DESC` và giữ những hàng đồng hạng với hàng cuối cùng được chọn. Với giá 900, 900, 350, 250, kết quả có hai hàng 900.

Nếu chỉ `FETCH FIRST 1 ROW WITH TIES`, cả hai đơn 900 sẽ được trả.

### Vì sao không thêm ID vào ORDER BY nếu cần WITH TIES theo giá?

Nếu viết:

```sql
ORDER BY total_amount DESC, order_id DESC
FETCH FIRST 1 ROW WITH TIES
```

thì `order_id` khác nhau khiến hai hàng **không còn bằng nhau theo toàn bộ khóa sort**. Bạn sẽ chỉ nhận một hàng, dù cùng giá.

Hãy phân biệt:

- Thứ tự quyết định **đồng hạng** phải dựa trên khóa nghiệp vụ.
- Thứ tự hiển thị cuối có thể sắp tiếp theo ID trong **truy vấn ngoài** nếu cần.

`FETCH ... WITH TIES` trên cả bảng không tự trở thành **top N per group**; để áp dụng riêng từng khách, có thể dùng `LATERAL`.

## 17. Top N cho mỗi nhóm bằng LEFT JOIN LATERAL

Nếu mỗi khách cần **hai đơn mới nhất** và vẫn giữ khách không có đơn:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    recent.order_id,
    recent.placed_at,
    recent.total_amount
FROM lesson_window_cases.customers AS c
LEFT JOIN LATERAL (
    SELECT
        o.order_id,
        o.placed_at,
        o.total_amount
    FROM lesson_window_cases.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.placed_at DESC, o.order_id DESC
    LIMIT 2
) AS recent ON TRUE
ORDER BY
    c.customer_id,
    recent.placed_at DESC NULLS LAST,
    recent.order_id DESC NULLS LAST;
```

`LATERAL` cho phép truy vấn con bên phải dùng `c.customer_id` của hàng khách hiện tại. Với dữ liệu mẫu:

- An → hai đơn 1004, 1003.
- Bình → hai đơn 2003, 2002.
- Chi → một đơn 3001.
- Dung → **một hàng** với các cột `recent.* = NULL`.

### CROSS JOIN LATERAL hay LEFT JOIN LATERAL?

`CROSS JOIN LATERAL` loại khách mà truy vấn bên phải trả 0 hàng. `LEFT JOIN LATERAL ... ON TRUE` giữ khách và tạo cột bên phải null, phù hợp báo cáo cần **mọi khách hàng**.

### Dùng top N WITH TIES trong LATERAL

Khi yêu cầu là hai vị trí giá trị cao nhất với đồng hạng:

```sql
SELECT
    c.customer_id,
    t.order_id,
    t.total_amount
FROM lesson_window_cases.customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id, o.total_amount
    FROM lesson_window_cases.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.total_amount DESC
    FETCH FIRST 2 ROWS WITH TIES
) AS t ON TRUE
ORDER BY c.customer_id, t.total_amount DESC NULLS LAST, t.order_id;
```

Nếu muốn **hai mức giá khác nhau**, `DENSE_RANK() <= 2` là biểu thức rõ hơn; `FETCH ... WITH TIES` chỉ mở rộng theo ranh giới của N **hàng**, không phải N mức phân biệt.

## 18. ROW_NUMBER hay LATERAL cho top N?

Hai cách đều hợp lệ nhưng hình dạng workload khác nhau.

| Tiêu chí | `ROW_NUMBER` + CTE | `LATERAL` với `ORDER BY ... LIMIT N` |
|---|---|---|
| Có nhiều khách, cần top N cho **toàn bộ** khách | Tự nhiên, set-based. | Cũng được nhưng có thể chạy lookup cho rất nhiều khách. |
| Chỉ một tập nhỏ khách sau filter | Có thể phải cân nhắc lượng hàng xếp hạng. | Có thể tận dụng index để đọc N hàng của mỗi khách. |
| Muốn giữ khách không có đơn | Cần `LEFT JOIN` kết quả đã xếp hạng về customers. | `LEFT JOIN LATERAL` trực tiếp rõ ràng. |
| Muốn tính thêm rank/dense rank | Dễ kết hợp nhiều window functions. | Có thể dùng query khác nhưng không luôn thuận tiện. |
| Index phù hợp | Hỗ trợ sắp theo partition/order key. | Hỗ trợ tìm theo customer và top-N nhanh. |
| Hiệu năng | Tùy số hàng, thống kê, filter và planner. | Tùy số khách bên trái, N và index. |

**Không có quy tắc “LATERAL luôn nhanh hơn window function”**. Dùng `EXPLAIN (ANALYZE, BUFFERS)` trên dữ liệu thật để quyết định, đặc biệt khi customer count rất lớn.

## 19. Top 1 mỗi nhóm bằng DISTINCT ON

PostgreSQL có cú pháp **`DISTINCT ON`** — một cách ngắn gọn để giữ **một hàng đầu tiên theo thứ tự xác định** cho mỗi nhóm giá trị.

```sql
SELECT DISTINCT ON (o.customer_id)
    o.customer_id,
    o.order_id,
    o.placed_at,
    o.total_amount
FROM lesson_window_cases.orders AS o
ORDER BY
    o.customer_id,
    o.placed_at DESC,
    o.order_id DESC;
```

Mỗi `customer_id` giữ hàng đầu tiên theo thứ tự:

1. Nhóm theo customer_id.
2. Trong mỗi nhóm, `placed_at` mới nhất đứng đầu.
3. Nếu thời điểm bằng nhau, `order_id` lớn hơn đứng đầu.

Kết quả: An 1004, Bình 2003, Chi 3001.

### Cú pháp quan trọng của DISTINCT ON

Với `DISTINCT ON (customer_id)`, những biểu thức đầu bên trái của `ORDER BY` phải tương ứng với những biểu thức của `DISTINCT ON` theo quy tắc PostgreSQL.

Không viết:

```sql
-- Sai quy tắc DISTINCT ON:
SELECT DISTINCT ON (customer_id)
    customer_id, order_id
FROM lesson_window_cases.orders
ORDER BY placed_at DESC, customer_id;
```

Sửa bằng:

```sql
SELECT DISTINCT ON (customer_id)
    customer_id, order_id, placed_at
FROM lesson_window_cases.orders
ORDER BY customer_id, placed_at DESC, order_id DESC;
```

### Sắp kết quả cuối theo thời gian toàn hệ thống

Sau khi chọn một đơn cho mỗi khách, muốn sắp các khách theo đơn mới nhất:

```sql
SELECT *
FROM (
    SELECT DISTINCT ON (customer_id)
        customer_id, order_id, placed_at
    FROM lesson_window_cases.orders
    ORDER BY customer_id, placed_at DESC, order_id DESC
) AS latest_per_customer
ORDER BY placed_at DESC, order_id DESC;
```

Phân biệt **thứ tự chọn đại diện trong subquery** với **thứ tự hiển thị ở query ngoài**.

### DISTINCT ON không phải SQL chuẩn phổ quát

`DISTINCT ON` là khả năng đặc trưng của PostgreSQL. Nếu cần SQL dễ chuyển sang nhiều hệ quản trị, `ROW_NUMBER()` với CTE/subquery thường là lựa chọn dễ di chuyển hơn.

## 20. Top 1 và xử lý đồng hạng

`DISTINCT ON` và `ROW_NUMBER() = 1` luôn chọn **tối đa một hàng** cho mỗi nhóm sau khi áp dụng thứ tự, trong khi `RANK() = 1` hoặc `DENSE_RANK() = 1` có thể trả **nhiều hàng đồng hạng**.

Ví dụ “đơn có **giá trị cao nhất** của mỗi khách”:

```sql
WITH ranked AS (
    SELECT
        o.*,
        RANK() OVER (
            PARTITION BY customer_id
            ORDER BY total_amount DESC
        ) AS amount_rank
    FROM lesson_window_cases.orders AS o
)
SELECT customer_id, order_id, total_amount
FROM ranked
WHERE amount_rank = 1
ORDER BY customer_id, order_id;
```

An có **hai đơn đồng giá 900.000**, nên query trả cả 1002 và 1003. Nếu yêu cầu một đơn đại diện, cần quy tắc phụ như `placed_at DESC, order_id DESC` và `ROW_NUMBER` hoặc `DISTINCT ON`.

Đừng nhầm “đơn đắt nhất” với “một trong những đơn đắt nhất” hoặc “đơn mới nhất”. Từ **“nhất”** trong câu hỏi nghiệp vụ phải được giải nghĩa thành một hoặc nhiều khóa sắp xếp chính xác.

## 21. Lọc trạng thái trước hay sau khi tính top N?

Đây là một khác biệt rất quan trọng.

### Yêu cầu A — Hai đơn PAID mới nhất của mỗi khách

Phải **lọc PAID trước** khi xếp hạng:

```sql
WITH ranked AS (
    SELECT
        o.*,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY placed_at DESC, order_id DESC
        ) AS rn
    FROM lesson_window_cases.orders AS o
    WHERE o.status = 'PAID'
)
SELECT customer_id, order_id, status, rn
FROM ranked
WHERE rn <= 2
ORDER BY customer_id, rn;
```

### Yêu cầu B — Hai đơn mới nhất bất kể trạng thái, sau đó chỉ hiển thị PAID

Phải **xếp hạng tất cả rồi lọc PAID ở ngoài**:

```sql
WITH ranked AS (
    SELECT
        o.*,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY placed_at DESC, order_id DESC
        ) AS rn
    FROM lesson_window_cases.orders AS o
)
SELECT customer_id, order_id, status, rn
FROM ranked
WHERE rn <= 2
  AND status = 'PAID'
ORDER BY customer_id, rn;
```

Hai yêu cầu này **không tương đương**. Với An, hai đơn mới nhất là 1004 (PAID) và 1003 (PENDING). Yêu cầu B chỉ trả 1004, còn yêu cầu A có thể trả 1004 và 1002.

Đây là khác biệt giữa **lọc trước khi xếp hạng** và **lọc sau khi xếp hạng**, không chỉ là cách viết SQL.

## 22. Top N kết hợp aggregate JSON

Một API thường muốn mỗi khách có **một hàng** kèm danh sách N đơn mới nhất dạng JSON.

```sql
WITH ranked AS (
    SELECT
        o.*,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.placed_at DESC, o.order_id DESC
        ) AS rn
    FROM lesson_window_cases.orders AS o
),
top_orders AS (
    SELECT *
    FROM ranked
    WHERE rn <= 2
)
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'order_id', t.order_id,
                'total_amount', t.total_amount,
                'status', t.status
            )
            ORDER BY t.rn
        ) FILTER (WHERE t.order_id IS NOT NULL),
        '[]'::jsonb
    ) AS recent_orders
FROM lesson_window_cases.customers AS c
LEFT JOIN top_orders AS t
  ON t.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Lưu ý:

- `ROW_NUMBER` quyết định **những đơn thuộc top N**.
- `jsonb_agg(... ORDER BY t.rn)` quyết định **thứ tự phần tử trong JSON array**.
- `FILTER` loại hàng null-extended do `LEFT JOIN` với khách không có đơn.
- `COALESCE` trả `[]` thay cho SQL `NULL` ở khách Dung.

Không trông cậy vào `ORDER BY` trong window để tự duy trì thứ tự JSON array nếu `jsonb_agg` không có `ORDER BY` của riêng nó.

## 23. “Khử trùng lặp” cần định nghĩa bản ghi trùng trước

Hai hàng có thể giống nhau ở một vài cột nhưng vẫn là **hai sự kiện hợp lệ khác nhau**. Ví dụ:

- Hai đơn cùng giá trị 900.000 của An **không phải cùng một đơn** nếu `order_id` khác.
- Hai hoạt động cùng ngày **có thể được gom thành một ngày** khi thống kê streak, nhưng không nên xóa event nếu chúng là hai hành động thật.
- Hai bản ghi cùng `tenant_id, event_key` từ nguồn đồng bộ **có thể là cùng sự kiện** được nhận lại nhiều lần.

Trước khi viết `ROW_NUMBER() OVER (PARTITION BY ...)`, phải trả lời:

1. **Khóa nghiệp vụ nào xác định trùng?** `(tenant_id,event_key)`, email chuẩn hóa, ID ngoại hệ thống, hay tổ hợp nhiều cột?
2. **Dữ liệu có cần chuẩn hóa** trước khi so sánh (trim, lower, format, timezone)?
3. Khi hai bản ghi trùng, **giữ bản nào**: mới nhận nhất, mới cập nhật nhất, có độ tin cậy cao nhất hay đã được xác nhận?
4. Nếu tiêu chí chính hòa nhau, **khóa phá hòa** là gì?
5. Các bản ghi trùng có cần **lưu audit lịch sử** hay được phép xóa vật lý?

Không có câu trả lời cho các câu hỏi này, thao tác “xóa trùng” có thể xóa dữ liệu hợp lệ.

## 24. Phát hiện các nhóm bị trùng

Với bảng `raw_events`, quy tắc nghiệp vụ là một sự kiện duy nhất cho mỗi `(tenant_id, event_key)`.

Tìm các nhóm có nhiều bản ghi:

```sql
SELECT
    tenant_id,
    event_key,
    COUNT(*) AS duplicate_count
FROM lesson_window_cases.raw_events
GROUP BY tenant_id, event_key
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC, tenant_id, event_key;
```

Kết quả dự kiến:

| tenant_id | event_key | duplicate_count |
|---:|---|---:|
| 1 | evt-A | 3 |
| 2 | evt-C | 2 |

`HAVING COUNT(*) > 1` cho biết **nhóm bị trùng**, nhưng chưa quyết định **hàng nào nên giữ**.

### Đếm số bản ghi dư thừa

```sql
WITH duplicates AS (
    SELECT
        tenant_id,
        event_key,
        COUNT(*) AS cnt
    FROM lesson_window_cases.raw_events
    GROUP BY tenant_id, event_key
    HAVING COUNT(*) > 1
)
SELECT SUM(cnt - 1) AS extra_rows
FROM duplicates;
```

Với dữ liệu lab, có **3 bản ghi dư thừa** (hai trong nhóm tenant 1 / evt-A và một trong tenant 2 / evt-C). Nếu không có nhóm trùng, `SUM` trên tập rỗng trả SQL `NULL`; có thể `COALESCE(..., 0)` nếu báo cáo cần số 0.

## 25. Khử trùng theo ROW_NUMBER: giữ bản mới nhất

Định nghĩa bản cần giữ:

> Với mỗi `(tenant_id, event_key)`, giữ hàng có `received_at` lớn nhất. Nếu bằng nhau, giữ hàng có `event_id` lớn nhất.

Câu truy vấn:

```sql
WITH ranked_events AS (
    SELECT
        e.*,
        ROW_NUMBER() OVER (
            PARTITION BY e.tenant_id, e.event_key
            ORDER BY e.received_at DESC, e.event_id DESC
        ) AS rn
    FROM lesson_window_cases.raw_events AS e
)
SELECT
    tenant_id,
    event_key,
    event_id,
    received_at,
    payload
FROM ranked_events
WHERE rn = 1
ORDER BY tenant_id, event_key;
```

Kết quả đại diện:

| tenant_id | event_key | event_id giữ lại |
|---:|---|---:|
| 1 | evt-A | 5003 |
| 1 | evt-B | 5004 |
| 2 | evt-A | 6001 |
| 2 | evt-C | 6003 |

**Vì sao 5003 chứ không phải 5002?** Chúng có cùng `received_at`, nhưng `event_id = 5003` lớn hơn, tạo một thứ tự toàn phần theo quy tắc được chọn.

### Khóa phá hòa không tự chứng minh “mới hơn” về mặt nghiệp vụ

`event_id DESC` chỉ là quy tắc chọn **ổn định** trong bộ dữ liệu mẫu. Nếu ID do hệ phân tán tạo, số lớn hơn **không nhất thiết là sự kiện xảy ra sau**. Nếu yêu cầu giữ dữ liệu mới nhất theo **version nguồn**, phải dùng version/sequence authoritative của nguồn, không đơn giản dùng ID tự tăng trong database đích.

## 26. Khử trùng bằng DISTINCT ON trong PostgreSQL

Cùng kết quả đại diện có thể viết gọn:

```sql
SELECT DISTINCT ON (tenant_id, event_key)
    tenant_id,
    event_key,
    event_id,
    received_at,
    payload
FROM lesson_window_cases.raw_events
ORDER BY
    tenant_id,
    event_key,
    received_at DESC,
    event_id DESC;
```

`DISTINCT ON (tenant_id, event_key)` giữ **một hàng đầu tiên** trong mỗi nhóm, theo thứ tự `ORDER BY` được cung cấp.

### So sánh DISTINCT ON với ROW_NUMBER

| Đặc điểm | `DISTINCT ON` | `ROW_NUMBER` |
|---|---|---|
| Lấy đúng một hàng/nhóm | Rất gọn. | Có thêm CTE/subquery nhưng rõ ý nghĩa số thứ tự. |
| Lấy top N với N lớn hơn 1 | Không trực tiếp. | `rn <= N` phù hợp. |
| Giữ tất cả hàng đồng hạng | Không. | Dùng `RANK/DENSE_RANK` khi cần. |
| Dễ chuyển hệ quản trị khác | PostgreSQL-specific. | Window function phổ biến hơn. |
| Dùng để xem hàng dư cần xóa | Không tự cung cấp mọi `rn > 1`. | Thuận tiện. |
| Quy tắc phá hòa | Cần `ORDER BY` đủ rõ. | Cần `ORDER BY` trong `OVER` đủ rõ. |

Không có công thức tuyệt đối rằng một cách luôn nhanh hơn cách kia; planner, index và khối lượng dữ liệu quyết định.

## 27. DISTINCT thông thường không giống chọn một bản ghi đại diện

`SELECT DISTINCT tenant_id, event_key` chỉ trả **các tổ hợp khóa khác nhau**:

```sql
SELECT DISTINCT tenant_id, event_key
FROM lesson_window_cases.raw_events
ORDER BY tenant_id, event_key;
```

Nhưng nếu thêm payload hoặc `received_at`:

```sql
SELECT DISTINCT tenant_id, event_key, received_at, payload
FROM lesson_window_cases.raw_events;
```

thì nhiều hàng trùng khóa nghiệp vụ vẫn xuất hiện vì payload/timestamp khác nhau. `DISTINCT` phân biệt theo **toàn bộ biểu thức được chọn**, không tự hiểu key nào là danh tính nghiệp vụ.

Muốn một hàng đầy đủ **theo quy tắc mới nhất**, cần `ROW_NUMBER`/`DISTINCT ON` hoặc giải pháp tương đương có định nghĩa thứ tự.

### Không dùng MIN/MAX rồi chọn những cột không liên quan

Ví dụ:

```sql
SELECT tenant_id, event_key, MAX(received_at)
FROM lesson_window_cases.raw_events
GROUP BY tenant_id, event_key;
```

trả timestamp mới nhất nhưng **không chỉ ra duy nhất payload thuộc hàng nào** nếu nhiều event cùng timestamp. Join trở lại bảng bằng `received_at = MAX(...)` có thể trả nhiều hàng. `ROW_NUMBER` với tie-breaker giải quyết bài toán chọn đại diện rõ ràng.

## 28. Xem trước các hàng sẽ xóa

Nếu dữ liệu thật sự có lỗi nhân bản và được phép làm sạch, bước đầu tiên là **SELECT kiểm tra**:

```sql
WITH ranked_events AS (
    SELECT
        e.event_id,
        e.tenant_id,
        e.event_key,
        e.received_at,
        ROW_NUMBER() OVER (
            PARTITION BY e.tenant_id, e.event_key
            ORDER BY e.received_at DESC, e.event_id DESC
        ) AS rn
    FROM lesson_window_cases.raw_events AS e
)
SELECT
    event_id,
    tenant_id,
    event_key,
    received_at,
    rn
FROM ranked_events
WHERE rn > 1
ORDER BY tenant_id, event_key, rn;
```

Trong lab, tập này gồm 5002, 5001 và 6002, còn 5003/5004/6001/6003 được giữ.

### Những việc cần xác nhận trước khi xóa

- Có được xóa vật lý hay phải giữ **audit/source history**?
- Có khóa ngoại từ bảng khác tới `event_id` sẽ bị xóa không?
- Bản được giữ có thực sự là bản authoritative?
- Có batch nạp dữ liệu mới đang chạy không?
- Có backup/khả năng rollback không?
- Có cần làm sạch theo từng tenant/batch để tránh khóa bảng quá lâu không?

Đếm trùng và xem trước những hàng dự kiến bị xóa là việc khác với thực hiện `DELETE`.

## 29. Xóa trùng bằng CTE và DELETE ... USING

Ví dụ **chỉ dùng trong database lab**, hoặc sau khi được phê duyệt với kế hoạch transaction phù hợp:

```sql
BEGIN;

WITH ranked_events AS (
    SELECT
        e.event_id,
        ROW_NUMBER() OVER (
            PARTITION BY e.tenant_id, e.event_key
            ORDER BY e.received_at DESC, e.event_id DESC
        ) AS rn
    FROM lesson_window_cases.raw_events AS e
)
DELETE FROM lesson_window_cases.raw_events AS e
USING ranked_events AS r
WHERE e.event_id = r.event_id
  AND r.rn > 1
RETURNING
    e.event_id,
    e.tenant_id,
    e.event_key,
    e.received_at;

-- Trong lab: dùng ROLLBACK để không thay đổi dữ liệu mẫu,
-- hoặc COMMIT chỉ sau khi được phép và xác nhận kết quả.
ROLLBACK;
```

Ý nghĩa:

1. CTE tính số thứ tự của từng hàng trong mỗi khóa nghiệp vụ.
2. Giữ `rn = 1`, chọn các ID có `rn > 1`.
3. `DELETE ... USING` liên kết hàng bảng gốc qua **`event_id` khóa chính**.
4. `RETURNING` hiển thị những hàng đã bị tác động trong transaction.
5. `ROLLBACK` trong ví dụ hoàn nguyên thao tác để không phá dữ liệu lab.

### Vì sao không dùng DELETE WHERE received_at < MAX(...)?

Nếu hai bản có **timestamp mới nhất bằng nhau**, cả hai có thể sống sót. Nếu xóa theo ID lớn/nhỏ không được thống nhất, có thể giữ sai payload. `ROW_NUMBER` với khóa phá hòa biểu diễn đầy đủ quy tắc “giữ đúng một”.

### Caution: snapshot không khóa mọi cạnh tranh

CTE xếp hạng và `DELETE` trong một transaction không tự ngăn **một ingestion worker khác chèn thêm bản trùng** trong lúc hoặc ngay sau thao tác. Để chống tái phát, phải áp dụng **ràng buộc duy nhất** và thiết kế đường ghi idempotent.

## 30. Ngăn trùng tái phát bằng UNIQUE

Sau khi đã làm sạch và xác nhận dữ liệu nguồn, nếu quy tắc là **mỗi tenant và event_key chỉ có một hàng trong bảng canonical**, có thể thêm:

```sql
ALTER TABLE lesson_window_cases.raw_events
ADD CONSTRAINT uq_raw_events_tenant_key
UNIQUE (tenant_id, event_key);
```

**Lệnh này sẽ thất bại nếu chạy trước khi dữ liệu trùng thực sự được xóa**. Trong phần trước ta dùng `ROLLBACK` nên dữ liệu lab vẫn trùng; muốn thử `UNIQUE` thành công, cần làm sạch có chủ đích trong một lab riêng rồi mới chạy lệnh.

### Nhưng bảng raw_events có nên UNIQUE không?

Tên `raw_events` gợi ý dữ liệu **raw log có thể cố ý giữ mọi lần nhận**. Khi cần audit hoặc tái chạy pipeline, **không nên xóa các lần nhận raw**. Thiết kế thường tách:

```text
raw_events (append-only, lưu mọi lần nhận)
        │
        │ deduplicate và chọn bản canonical
        ▼
canonical_events (UNIQUE tenant_id, event_key)
        │
        ▼
downstream reporting / business logic
```

Trong mô hình ấy, `UNIQUE` đặt ở **bảng canonical**, còn `raw_events` vẫn được phép chứa các lần gửi lặp vì có ý nghĩa kiểm toán. Chọn mô hình theo yêu cầu lưu trữ trước khi thay đổi dữ liệu.

### Khóa nghiệp vụ có thể NULL

`GROUP BY`/`PARTITION BY` đặt các khóa null theo ngữ nghĩa nhóm của SQL, nhưng **UNIQUE` thông thường trong PostgreSQL cho phép nhiều hàng có null ở một cột khóa. Trên các phiên bản có hỗ trợ, `UNIQUE NULLS NOT DISTINCT` cho phép đổi ngữ nghĩa nếu null cần được coi là trùng.

Schema lab dùng `tenant_id NOT NULL` và `event_key NOT NULL`, nên ví dụ không gặp trường hợp này. Với schema khác, phải quyết định rõ null nghĩa là “không biết ID” hay “một giá trị khóa thật”.

## 31. UPSERT/idempotency khi nhận sự kiện lặp

Khi bảng canonical có ràng buộc:

```sql
CREATE TABLE lesson_window_cases.canonical_events (
    tenant_id BIGINT NOT NULL,
    event_key TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    PRIMARY KEY (tenant_id, event_key)
);
```

Bạn có thể ghi theo nguyên tắc **“chỉ cập nhật nếu sự kiện mới đến có received_at lớn hơn”**:

```sql
INSERT INTO lesson_window_cases.canonical_events AS c (
    tenant_id, event_key, received_at, payload
)
VALUES (
    1,
    'evt-A',
    TIMESTAMPTZ '2026-11-13 09:00:00+07',
    '{"version":4}'::jsonb
)
ON CONFLICT (tenant_id, event_key)
DO UPDATE SET
    received_at = EXCLUDED.received_at,
    payload = EXCLUDED.payload
WHERE EXCLUDED.received_at > c.received_at;
```

Ý nghĩa:

- Nếu key chưa có, chèn hàng mới.
- Nếu key đã có và timestamp mới **lớn hơn**, cập nhật.
- Nếu timestamp bằng hoặc cũ hơn, không ghi đè theo điều kiện `WHERE`.

Ở đây **timestamp bằng nhau không được cập nhật**, khác quy tắc giữ `event_id` lớn nhất trong ví dụ xóa trùng. Với hệ thống thật phải thống nhất quy tắc phá hòa theo **nguồn dữ liệu authoritative**, ví dụ `source_sequence`, `source_version` hoặc một ID được bảo đảm có thứ tự.

Đối với writer đồng thời, PostgreSQL kiểm tra conflict trên unique index và xử lý upsert theo khóa; điều đó an toàn hơn chiến lược “SELECT xem đã tồn tại chưa, rồi INSERT” dễ bị race.

**Không đồng nhất “nhận sau” với “xảy ra sau”.** `received_at` là thời điểm database/consumer nhận dữ liệu, khác `occurred_at` hay version sự kiện từ nguồn.

## 32. Dedup và NULL, chữ hoa/thường, khoảng trắng

Định nghĩa trùng thường phải xét chuẩn hóa dữ liệu. Với email:

```text
"An@Example.Com"
"an@example.com"
" an@example.com "
```

Ba chuỗi khác nhau về ký tự nhưng ứng dụng có thể muốn coi là cùng một khóa theo chính sách email của mình.

Một truy vấn minh họa:

```sql
WITH source(email) AS (
    VALUES
        ('An@Example.Com'),
        ('an@example.com'),
        (' an@example.com ')
),
normalized AS (
    SELECT
        email,
        lower(btrim(email)) AS normalized_email
    FROM source
)
SELECT
    email,
    normalized_email,
    ROW_NUMBER() OVER (
        PARTITION BY normalized_email
        ORDER BY email
    ) AS rn
FROM normalized;
```

Đây chỉ là một ví dụ về **chuẩn hóa chuỗi**. Quy tắc email production có thể phức tạp hơn, chịu collation, Unicode normalization, định danh domain và chính sách nghiệp vụ.

### Tránh việc so sánh “trông giống nhau” nhưng phá dữ liệu thật

Không nên tùy tiện `lower`/`trim` mọi khóa:

- Mã sản phẩm có thể phân biệt chữ hoa.
- External ID có thể có khoảng trắng là một phần hợp lệ.
- Unicode/collation có quy tắc phức tạp.
- Hai bản ghi cùng tên không chắc là cùng thực thể.

Khóa của `PARTITION BY` phải phản ánh **quy tắc định danh đã được xác nhận**, không chỉ là một thủ thuật SQL.

## 33. Dedup và “bản ghi đến muộn”

Trong dữ liệu sự kiện, có nhiều mốc thời gian:

| Mốc | Ý nghĩa |
|---|---|
| `occurred_at` | Khi sự kiện thực xảy ra ở nguồn. |
| `produced_at` | Khi nguồn tạo message. |
| `received_at` | Khi hệ thống đích nhận message. |
| `processed_at` | Khi pipeline xử lý message. |
| `source_version` | Thứ tự phiên bản/số sequence từ nguồn, nếu có. |

Nếu mục tiêu là **sự kiện có trạng thái mới nhất của entity**, có thể cần `source_version DESC` hơn `received_at DESC`. Nếu mục tiêu là **bản payload mới nhất được nhận**, `received_at DESC` phù hợp.

Ví dụ hai message:

```text
source version 10 ── được nhận 10:05
source version  9 ── được nhận 10:10 (đến muộn)
```

Nếu lấy `MAX(received_at)`, bạn giữ version 9 dù nguồn đã có version 10. Hãy định nghĩa **tính mới nhất theo nguồn** thay vì mặc định theo giờ nhận.

### Không dùng “timestamp lớn nhất” như khóa duy nhất bảo vệ trùng

Hai event từ nhiều producer có thể có cùng timestamp, clock skew hoặc precision khác nhau. Cần key nghiệp vụ/sequence đáng tin, và nếu đồng hạng cần quy tắc rõ.

## 34. Window frame: ROWS và RANGE khi tính nhóm liên tiếp

Các hàm xếp hạng như `ROW_NUMBER`/`RANK`/`DENSE_RANK` sử dụng thứ tự của partition và không bị thay đổi ý nghĩa xếp hạng bởi window frame theo cách aggregate tích lũy bị tác động.

Nhưng với:

```sql
SUM(starts_new_run) OVER (
    PARTITION BY device_id
    ORDER BY changed_at
)
```

PostgreSQL mặc định có **frame** theo quy tắc liên quan các hàng đồng thứ tự (peers), không phải luôn cộng tuần tự từng hàng. Khi cần đánh số island theo từng event, nên viết:

```sql
SUM(starts_new_run) OVER (
    PARTITION BY device_id
    ORDER BY changed_at, state_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

Điều này làm rõ hai thứ:

1. Có **thứ tự xác định** cho mỗi event bằng `state_id`.
2. Tổng tích lũy dùng **tất cả hàng trước và hàng hiện tại** theo thứ tự ấy.

### Không tự dùng RANGE cho “30 phút trước”

`RANGE BETWEEN INTERVAL '30 minutes' PRECEDING AND CURRENT ROW` là một **window frame theo giá trị sort key**, không phải cách tự động tách session theo quy tắc mỗi event cách event ngay trước tối đa 30 phút. Bài toán sessionization cần `LAG`, cờ chuyển và tổng tích lũy hoặc một cơ chế tương đương.

## 35. Dùng LEAD để tìm mốc kết thúc của đoạn

`LEAD(value)` trả giá trị từ **hàng tiếp theo** trong thứ tự của window. Với sự kiện chuyển trạng thái, nó giúp xác định thời điểm sự kiện tiếp theo:

```sql
SELECT
    device_id,
    state_id,
    changed_at AS valid_from,
    LEAD(changed_at) OVER (
        PARTITION BY device_id
        ORDER BY changed_at, state_id
    ) AS next_event_at,
    state_name
FROM lesson_window_cases.device_states
ORDER BY device_id, changed_at, state_id;
```

Nếu mỗi hàng là **một sự kiện làm trạng thái bắt đầu hiệu lực**, ta có thể mô tả khoảng `[valid_from, next_event_at)` cho mỗi sự kiện (với điều kiện timestamp/order đúng).

**Tuy nhiên**, dữ liệu lab có hai quan sát `READY` liên tiếp; nếu mỗi hàng chỉ là một lần **quan sát** chứ không phải thay đổi trạng thái, khoảng hiệu lực nên được suy ra theo mô hình khác. Không suy luận sai về độ dài trạng thái từ việc có hai event cùng tên.

### Sự kiện cuối không có mốc sau

`LEAD` trả SQL `NULL` ở hàng cuối mỗi partition. Nếu cần khoảng **không giới hạn phía trên** có thể dùng `tstzrange(valid_from, NULL, '[)')` trong một mô hình lịch sử phù hợp, nhưng không nên tự biến thành `now()` trừ khi báo cáo yêu cầu cắt ở thời điểm hiện tại.

## 36. Index hỗ trợ top-N và dedup

Window function là logic truy vấn; hiệu năng còn phụ thuộc **lượng dữ liệu, phép lọc, thứ tự và chỉ mục**.

### Index cho top N đơn mới nhất theo khách

```sql
CREATE INDEX ix_orders_customer_recent
ON lesson_window_cases.orders (
    customer_id,
    placed_at DESC,
    order_id DESC
);
```

Index này phù hợp với:

```sql
WHERE customer_id = ?
ORDER BY placed_at DESC, order_id DESC
LIMIT 2
```

và có thể hỗ trợ các plan window theo cùng partition/order key. Nhưng **không bảo đảm planner luôn dùng index**, nhất là với bảng nhỏ hoặc khi truy vấn cần đọc gần như mọi hàng.

### Index cho dedup theo khóa và thứ tự mới nhất

```sql
CREATE INDEX ix_events_group_latest
ON lesson_window_cases.raw_events (
    tenant_id,
    event_key,
    received_at DESC,
    event_id DESC
);
```

Nó có thể hỗ trợ tìm nhóm và sắp thứ tự theo những cột dùng trong `ROW_NUMBER`/`DISTINCT ON`.

### Index không thay thế UNIQUE

Index B-tree không unique chỉ hỗ trợ tìm kiếm; nó **không cấm** hai hàng cùng `(tenant_id,event_key)`. Nếu bất biến là duy nhất, cần **unique constraint/index** phù hợp trên bảng canonical.

### Chi phí ghi và dung lượng

Mỗi index tăng chi phí INSERT/UPDATE/DELETE, WAL và dung lượng. Không tạo cùng lúc nhiều index gần như trùng nhau chỉ vì chúng xuất hiện trong ví dụ. Đo workload thật và kiểm tra index do constraint đã có trước khi thêm index khác.

## 37. EXPLAIN ANALYZE cho window function

Ví dụ:

```sql
EXPLAIN (ANALYZE, BUFFERS)
WITH ranked AS (
    SELECT
        o.order_id,
        o.customer_id,
        o.placed_at,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.placed_at DESC, o.order_id DESC
        ) AS rn
    FROM lesson_window_cases.orders AS o
)
SELECT *
FROM ranked
WHERE rn <= 2;
```

Khi đọc kế hoạch, hãy quan sát:

- `WindowAgg` hoặc các node liên quan tới window.
- Có `Sort`/`Incremental Sort` hay scan theo index phù hợp hay không.
- Estimated rows so với actual rows.
- Số hàng nguồn trước và sau lọc `rn <= 2`.
- Buffer hits/reads và thời gian thực thi.

`EXPLAIN (ANALYZE, BUFFERS)` **thực sự chạy truy vấn**, nên trong bài dùng câu `SELECT`. Khi phân tích câu `DELETE`, cần transaction/rollback và hiểu rõ tác động trước khi chạy explain analyze.

### Window function không tự đảm bảo “chỉ đọc N hàng mỗi partition”

Một số kế hoạch có thể tối ưu điều kiện xếp hạng, nhưng không được giả định `ROW_NUMBER() <= 2` đồng nghĩa PostgreSQL chỉ cần đọc đúng hai hàng đầu của mỗi partition. Với hàng triệu hàng và vài nhóm rất lớn, chi phí sort/scan vẫn cần cân nhắc.

`LATERAL` với `LIMIT N` và index `(partition_key, sort_key DESC)` có thể có lợi khi số nhóm bên trái nhỏ; hãy đo thay vì khẳng định.

## 38. Những lỗi thường gặp

### 38.1. Không loại trùng trước khi tính streak theo ngày

Hai action cùng một ngày làm `ROW_NUMBER` tăng hai lần nhưng ngày không tăng, khiến `date - rn` đổi khóa island sai. Dùng `SELECT DISTINCT user_id, activity_date` hoặc nhóm về đúng grain.

### 38.2. GROUP BY status cho rằng đó là nhóm liên tiếp

`READY → ERROR → READY` phải là ba run, không phải một nhóm READY và một nhóm ERROR. Dùng `LAG` và running SUM.

### 38.3. Thiếu PARTITION BY

Không có `PARTITION BY customer_id`, `ROW_NUMBER` chỉ trả top N **toàn cục**, không phải top N mỗi khách.

### 38.4. Thiếu khóa phá hòa

Hai hàng có cùng timestamp có thể đổi thứ tự theo plan. Khi cần chọn đại diện/xóa trùng, thêm khóa unique vào `ORDER BY`.

### 38.5. Dùng RANK với khóa unique rồi thắc mắc vì sao không có đồng hạng

`RANK() OVER (ORDER BY amount DESC, order_id DESC)` xem hai hàng cùng amount nhưng khác ID là khác peer. Để giữ đồng hạng theo amount, chỉ sắp `amount` trong rank window.

### 38.6. Dùng DENSE_RANK <= N mà mong đúng N hàng

`DENSE_RANK` chọn N mức giá trị; một mức có thể chứa nhiều hàng. Muốn tối đa N hàng, dùng `ROW_NUMBER`.

### 38.7. Dùng LIMIT N rồi nghĩ đó là top N mỗi khách

`LIMIT N` ngoài không áp dụng riêng mỗi `customer_id`. Dùng window hoặc `LATERAL`.

### 38.8. Gọi window function ở WHERE

Hàm window không hợp lệ trực tiếp ở `WHERE`/`HAVING` của cùng query block. Tính trong CTE rồi lọc ở query ngoài.

### 38.9. Đặt filter sai tầng

“Top 2 PAID” và “top 2 bất kỳ, rồi giữ PAID” khác nhau. Xác định filtering stage trước khi viết SQL.

### 38.10. DISTINCT toàn bộ cột thay cho dedup theo key

`SELECT DISTINCT *` chỉ loại hàng giống toàn bộ cột; payload/ingestion timestamp khác nhau vẫn là nhiều hàng. Dùng khóa nghiệp vụ trong `PARTITION BY` hoặc `DISTINCT ON`.

### 38.11. Lấy MAX timestamp rồi join lại và vẫn có hai bản ghi

Hai hàng cùng timestamp tối đa có thể cùng khớp. Dùng tie-breaker cùng `ROW_NUMBER`/`DISTINCT ON`.

### 38.12. Xóa trùng trực tiếp mà không xem trước

Không chạy `DELETE` phá hủy dữ liệu khi chưa xác nhận khóa trùng, bản giữ, foreign keys, audit, backup và concurrency.

### 38.13. Làm sạch xong nhưng không chặn tái phát

Nếu pipeline tiếp tục insert cùng key và không có unique constraint/upsert, dữ liệu có thể trùng lại ngay. Thiết kế bảng canonical và bất biến ngay ở tầng ghi.

### 38.14. Dùng received_at thay cho source_version

Một message đến muộn có thể mang version cũ. Chọn “mới nhất” theo **ngữ nghĩa nghiệp vụ**, không mặc định theo đồng hồ nhận.

### 38.15. Dùng ngày lịch để tính ngày làm việc liên tiếp

Thứ Sáu và thứ Hai không sát nhau theo calendar day; muốn ngày làm việc liên tiếp phải dùng business calendar.

### 38.16. Lấy COUNT(*) sau LEFT JOIN và tưởng đó là số bản ghi con

Hàng cha không có bản ghi con vẫn có một hàng null-extended; `COUNT(*)` có thể là 1. Dùng `COUNT(child.primary_key)` khi đếm bản ghi con.

### 38.17. Tin vào ORDER BY bên trong window để sắp JSON array

Aggregate `jsonb_agg` cần `ORDER BY` **trong aggregate** để xác định thứ tự phần tử. Window order chỉ tạo `rn`/rank.

### 38.18. Giả định NOW() là thứ tự nhận sự kiện ở mức từng hàng

`now()` thường là thời điểm bắt đầu transaction, nhiều hàng có thể cùng giá trị. Cần tie-breaker/version key phù hợp nếu muốn chọn một bản.

### 38.19. Không phân biệt READ COMMITTED snapshot với bất biến dữ liệu

Một câu SELECT dedup là ảnh chụp dữ liệu thấy được theo transaction isolation; nó không tự khóa các insert tương lai. Dùng constraint và giao thức ghi đúng.

### 38.20. Tối ưu theo bảng lab vài dòng

Trên bảng nhỏ, sequential scan là bình thường. Không kết luận chỉ mục bị hỏng chỉ vì planner không dùng index của ví dụ.

## 39. SQL và JDBC: áp dụng top N trong API

Với Java/JDBC, có thể truyền N và customer filter qua `PreparedStatement`:

```java
String sql = """
    WITH ranked AS (
        SELECT
            o.order_id,
            o.customer_id,
            o.placed_at,
            o.total_amount,
            ROW_NUMBER() OVER (
                PARTITION BY o.customer_id
                ORDER BY o.placed_at DESC, o.order_id DESC
            ) AS rn
        FROM lesson_window_cases.orders AS o
        WHERE o.customer_id = ?
    )
    SELECT order_id, customer_id, placed_at, total_amount
    FROM ranked
    WHERE rn <= ?
    ORDER BY rn
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 1L);
    ps.setInt(2, 3);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long orderId = rs.getLong("order_id");
            long customerId = rs.getLong("customer_id");
            java.sql.Timestamp placedAt = rs.getTimestamp("placed_at");
            java.math.BigDecimal amount = rs.getBigDecimal("total_amount");
            // Ánh xạ vào DTO phù hợp, giữ thứ tự đã yêu cầu.
        }
    }
}
```

Ví dụ giả định `connection` tồn tại và code nằm trong một phương thức có xử lý `SQLException`. Khi xử lý `timestamptz` ở ứng dụng hiện đại, có thể dùng mapping phù hợp như `OffsetDateTime` theo hỗ trợ của JDBC driver/framework thay vì ép timestamp thành chuỗi theo múi giờ tùy ý.

### Giới hạn N từ request

Không cho client yêu cầu N tùy ý rất lớn. Ứng dụng nên validate `1 <= N <= MAX_ALLOWED` theo chính sách API. Placeholder `?` truyền **giá trị** chứ không phải tên cột của `ORDER BY`; nếu cho chọn sort field động, phải map từ whitelist nội bộ.

### Tính đúng thứ tự khi phân trang

Một API dùng `LIMIT/OFFSET` hoặc xếp hạng cần **thứ tự xác định**. Nếu thiếu tie-breaker, những đơn cùng timestamp có thể xuất hiện ở nhiều trang hoặc bị bỏ sót qua các lần đọc. Với dữ liệu ghi liên tục, **keyset pagination** hoặc snapshot/consistency policy phù hợp có thể ổn định hơn offset.

## 40. Quy trình giải bài toán nhóm liên tiếp và top N

### Với nhóm liên tiếp

1. Xác định **đơn vị hàng**: event, ngày duy nhất, trạng thái hay khoảng thời gian.
2. Xác định **partition key**: user, device, tenant hoặc entity.
3. Định nghĩa **thứ tự đầy đủ**, có tie-breaker khi cần.
4. Định nghĩa **ranh giới**: chênh một ngày, quá 30 phút, đổi trạng thái...
5. Chọn `ROW_NUMBER` difference hoặc `LAG` + cờ bắt đầu nhóm.
6. Dùng running `SUM` để gán group ID nếu chọn cách LAG.
7. `GROUP BY` group ID để tính min/max/count.
8. Chỉ tính “thời lượng” khi quy tắc sự kiện và thời gian cho phép.

### Với top N mỗi nhóm

1. Xác định **N hàng** hay **N hạng/mức giá trị**.
2. Xác định filter áp dụng **trước hay sau xếp hạng**.
3. Xác định sort key và tie-breaker.
4. Dùng `ROW_NUMBER` cho tối đa N hàng; `RANK`/`DENSE_RANK` nếu cần đồng hạng.
5. Cân nhắc `DISTINCT ON` cho top 1 hoặc `LATERAL` cho top N có index phù hợp.
6. Nếu ghép với bảng cha, quyết định có giữ entity không có hàng con hay không.
7. Đo hiệu năng và kết quả trên dữ liệu chứa tie/null.

### Với khử trùng lặp

1. Xác định **khóa nghiệp vụ** và cách chuẩn hóa.
2. Xác định **bản đại diện** theo version/timestamp/priority.
3. Thêm sort key phá hòa duy nhất, được nghiệp vụ chấp nhận.
4. `SELECT` xem nhóm trùng và những hàng bị loại.
5. Quyết định **giữ raw audit** hay xóa vật lý.
6. Dùng transaction có thể rollback khi thực hiện cleanup.
7. Áp dụng unique constraint/idempotent write tại bảng canonical.
8. Theo dõi số duplicate mới và chính sách xử lý late events.

## 41. Bài tập thực hành

### Bài 1 — Tính số thứ tự mỗi khách

Dùng `ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY placed_at DESC, order_id DESC)`. Giải thích tại sao 1003 đứng trước 1002 khi hai đơn cùng thời điểm, và vì sao `ROW_NUMBER` không thể dùng trực tiếp ở `WHERE` của cùng query block.

### Bài 2 — Top 2 đơn mỗi khách

Viết CTE lấy tối đa hai đơn mới nhất mỗi khách. So sánh kết quả với `ORDER BY placed_at DESC LIMIT 2` áp dụng toàn bộ bảng.

### Bài 3 — Giữ cả khách không có đơn

Viết `LEFT JOIN LATERAL` từ `customers` sang `orders` để lấy hai đơn mới nhất. Kiểm tra khách Dung có xuất hiện không, và những cột đơn có giá trị nào.

### Bài 4 — Top 2 PAID

Viết hai truy vấn:

1. Top 2 đơn `PAID` mới nhất trên mỗi khách.
2. Top 2 đơn mới nhất bất kể trạng thái, sau đó chỉ hiển thị `PAID`.

Giải thích vì sao hai truy vấn có thể khác kết quả ở khách An.

### Bài 5 — ROW_NUMBER, RANK và DENSE_RANK

Trên các đơn của An, tính ba hàm xếp hạng theo `total_amount DESC`. Với `ROW_NUMBER` thêm `order_id DESC` để phá hòa. Ghi kết quả của hai đơn cùng giá 900.000 và đơn giá 350.000.

### Bài 6 — Hai hạng đầu hay hai mức giá đầu?

Viết hai truy vấn theo giá trị đơn:

- `RANK() <= 2`.
- `DENSE_RANK() <= 2`.

Giải thích vì sao khách An nhận số hàng khác nhau ở hai phương pháp.

### Bài 7 — Top 1 với DISTINCT ON

Viết `DISTINCT ON (customer_id)` để lấy đơn mới nhất cho mỗi khách, với `ORDER BY customer_id, placed_at DESC, order_id DESC`. Sau đó bọc query để sắp các hàng kết quả theo `placed_at DESC` toàn cục.

### Bài 8 — Ngày hoạt động không trùng

Từ `daily_activity`, tạo tập `DISTINCT (user_id, activity_date)`. Giải thích tại sao phải loại trùng ngày 01/11 của user 1 trước khi tính chuỗi ngày liên tiếp.

### Bài 9 — ROW_NUMBER difference

Tính `activity_date - rn::integer` và nhóm theo `user_id, island_key` để trả `MIN(date)`, `MAX(date)`, `COUNT(*)`. Kiểm tra user 1 có ba island: 3, 2 và 1 ngày.

### Bài 10 — LAG và running SUM

Giải lại bài 9 bằng `LAG(activity_date)`, cờ bắt đầu island và `SUM(flag) OVER (... ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)`. So sánh khả năng mở rộng khi quy tắc gap thay đổi.

### Bài 11 — Chạy chuỗi trạng thái

Với `device_states`, tìm từng run `READY`/`ERROR` theo `device_id, changed_at, state_id`. Tại sao không thể chỉ `GROUP BY device_id, state_name`?

### Bài 12 — Sessionization theo 30 phút

Tạo tập event người dùng lúc 10:00, 10:10, 10:40, 11:20, 11:35. Dùng `LAG` xác định session khi gap **lớn hơn** 30 phút. Thử sửa quy tắc thành gap **từ** 30 phút trở lên và so sánh kết quả.

### Bài 13 — Ngày làm việc liên tiếp

Đề xuất bảng `business_calendar(calendar_date, is_business_day, business_day_no)`. Dùng số ngày làm việc tăng liên tục để tính streak bỏ qua cuối tuần; giải thích vì sao `date - ROW_NUMBER` theo ngày lịch không đủ.

### Bài 14 — Tìm nhóm trùng trong raw_events

Dùng `GROUP BY tenant_id, event_key HAVING COUNT(*) > 1` để tìm những key lặp. Dự đoán số bản ghi dư và giải thích vì sao `tenant_id` là phần của khóa.

### Bài 15 — Chọn bản ghi đại diện

Viết `ROW_NUMBER() OVER (PARTITION BY tenant_id, event_key ORDER BY received_at DESC, event_id DESC)`. Liệt kê ID được giữ cho các key `evt-A`/`evt-C`. Tại sao thiếu `event_id` khiến lựa chọn ở tenant 1 / evt-A bị thiếu rõ ràng?

### Bài 16 — So sánh DISTINCT và DISTINCT ON

Giải thích vì sao `SELECT DISTINCT tenant_id,event_key,received_at,payload` không đảm bảo một hàng trên mỗi khóa. Viết lại bằng `DISTINCT ON (tenant_id,event_key)` với thứ tự chọn đại diện chính xác.

### Bài 17 — Xem trước khi xóa

Viết truy vấn **chỉ SELECT** những hàng `rn > 1` từ `raw_events`. Sau đó mô tả cách dùng `DELETE ... USING` với khóa chính `event_id`, `RETURNING` và transaction có thể rollback. Không xóa dữ liệu ngoài lab.

### Bài 18 — Chống trùng tái phát

Đề xuất schema `canonical_events` với `UNIQUE(tenant_id,event_key)` và cách ghi `ON CONFLICT ... DO UPDATE` chỉ khi source version mới hơn. Tại sao chỉ chạy cleanup một lần là chưa đủ?

### Bài 19 — NULL và key nghiệp vụ

Nếu `event_key` được phép `NULL`, hãy so sánh:

- `PARTITION BY tenant_id,event_key`.
- `UNIQUE(tenant_id,event_key)` mặc định.
- `UNIQUE NULLS NOT DISTINCT` ở PostgreSQL có hỗ trợ.

Giải thích khi nào null nên được coi là trùng.

### Bài 20 — Chọn index

Đề xuất index cho truy vấn top 3 đơn mới nhất theo khách và index hỗ trợ dedup theo `tenant_id, event_key, received_at, event_id`. Nêu vì sao index không unique không thay thế unique constraint.

### Bài 21 — JSON top N có thứ tự

Trả một hàng mỗi khách với `jsonb_agg` gồm hai đơn mới nhất. Đơn trong JSON array phải được sắp theo `rn`; khách Dung nhận `[]`. Giải thích vai trò của `FILTER` và `COALESCE` khi `LEFT JOIN`.

### Bài 22 — Đo execution plan

Chạy `EXPLAIN (ANALYZE, BUFFERS)` trên top N bằng window và bằng `LEFT JOIN LATERAL` trong lab. So sánh scan/index, sort, số hàng và thời gian. Vì sao không thể kết luận cách nào nhanh hơn chỉ dựa vào bảng mẫu vài dòng?

### Bài 23 — Bản ghi đến muộn

Giả sử source version 10 được nhận 10:05 và source version 9 được nhận 10:10. Nếu nghiệp vụ cần version mới nhất, khóa `ORDER BY` trong dedup phải là gì? Vì sao `received_at DESC` sai mục tiêu?

### Bài 24 — Thêm điều kiện nghiệp vụ

Một người dùng có 10 ngày hoạt động liên tiếp nhưng ngày 5/11 là ngày nghỉ công ty. Hãy thiết kế quy tắc để giữ hay tách streak tùy chính sách: **calendar day streak** hoặc **business day streak**. Không dùng cùng một kết quả cho hai định nghĩa khác nhau.

## Kết luận

Ba bài toán **nhóm liên tiếp**, **top N mỗi nhóm** và **khử trùng lặp** đều dựa trên một nguyên tắc chung: **định nghĩa chính xác phân vùng, thứ tự và ý nghĩa của từng hàng**. `GROUP BY` trả lời “những hàng có cùng khóa là nhóm nào”; hàm cửa sổ bổ sung “hàng nào đứng trước, thứ mấy, đồng hạng nào, hoặc ranh giới nhóm ở đâu”.

Với **gaps-and-islands**, kỹ thuật `ROW_NUMBER` difference phù hợp dãy ngày/số tăng đúng một đơn vị, còn `LAG` kết hợp cờ chuyển và `SUM(...) OVER (ROWS ...)` phù hợp các quy tắc phức tạp như chuyển trạng thái hoặc session gap 30 phút. Phải loại trùng nếu đơn vị cần đếm là **ngày duy nhất**, và phải xác định đúng ranh giới giờ, ngày làm việc hoặc thứ tự sự kiện.

Với **top N mỗi nhóm**, dùng `ROW_NUMBER() <= N` khi cần tối đa N hàng; `RANK` để giữ đồng hạng theo vị trí xếp hạng; `DENSE_RANK` để lấy N mức giá trị; `DISTINCT ON` cho một đại diện/nhóm và `LATERAL` khi cần top N theo từng hàng cha. `ORDER BY` phải có tie-breaker nếu một hàng được chọn hoặc xóa theo thứ tự, và filter trước/sau xếp hạng phải phản ánh đúng câu hỏi nghiệp vụ.

Với **khử trùng lặp**, `ROW_NUMBER` hay `DISTINCT ON` chỉ là công cụ thực hiện. Quyết định quan trọng hơn là **khóa nào định nghĩa trùng, bản nào authoritative, có cần giữ audit không và làm sao ngăn tái phát**. Hãy xem trước `rn > 1`, xóa có transaction trong trường hợp thực sự cần, rồi dùng unique constraint và giao thức ghi idempotent cho dữ liệu canonical. Khi kết hợp đúng ngữ nghĩa, thứ tự và quản lý đồng thời, các hàm cửa sổ giúp PostgreSQL xử lý những bài toán phân tích và làm sạch dữ liệu phức tạp một cách rõ ràng, nhất quán và có thể tối ưu.

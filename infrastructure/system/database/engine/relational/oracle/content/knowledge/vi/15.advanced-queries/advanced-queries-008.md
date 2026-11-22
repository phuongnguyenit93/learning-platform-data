# Xử lý khoảng trống, dãy liên tiếp và dữ liệu thiếu kỳ trong Oracle

## 1. Vì sao phải tìm khoảng trống và dãy liên tiếp?

Một hệ thống có thể cần tìm những ngày khách hàng không phát sinh giao dịch, tháng nào một tài khoản không có dữ liệu báo cáo, những số thứ tự bị thiếu trong một dãy, hoặc các khoảng thời gian mà trạng thái thiết bị liên tục ở cùng một giá trị. Đây là các bài toán **gaps and islands** (khoảng trống và các đoạn liên tiếp) thường gặp trong truy vấn nâng cao.

Ví dụ, một tài khoản có dữ liệu theo ngày:

| Ngày | Có giao dịch? |
|---|---|
| 01/11 | Có |
| 02/11 | Có |
| 03/11 | Có |
| 04/11 | Không |
| 05/11 | Không |
| 06/11 | Có |
| 07/11 | Có |

Ta có thể cần trả lời hai câu hỏi khác nhau:

- **Khoảng trống (gap):** ngày 04/11 đến 05/11 không có giao dịch.
- **Đoạn liên tiếp (island):** 01/11–03/11 là một đoạn; 06/11–07/11 là đoạn tiếp theo.

Trong Oracle, có thể giải quyết bằng các hàm analytic như `LAG`, `LEAD`, `ROW_NUMBER`, `SUM OVER`, kết hợp với lịch ngày/tháng được sinh bằng `CONNECT BY LEVEL`, bảng calendar dimension, `NOT EXISTS` hoặc outer join.

Bài học thuộc chương **Truy vấn nâng cao**, trình bày cách xác định đúng khoảng dữ liệu cần xét, phát hiện khoảng trống giữa các bản ghi, gom nhóm các giá trị liên tiếp, tìm kỳ bị thiếu trong báo cáo định kỳ và tránh nhầm dữ liệu NULL với một kỳ hoàn toàn không có hàng.

## 2. Xác định hạt dữ liệu và phạm vi trước khi truy vấn

Trước khi viết SQL, hãy xác định ba điều:

1. **Đối tượng nào có chuỗi dữ liệu?** Ví dụ: mỗi khách hàng, tài khoản, thiết bị, nhân viên hay chi nhánh.
2. **Đơn vị liên tiếp là gì?** Ngày lịch, ngày làm việc, tháng, quý, số thứ tự hay timestamp.
3. **Phạm vi bắt đầu và kết thúc ở đâu?** Một khoảng cố định, vòng đời tài khoản, thời gian thiết bị hoạt động hay kỳ báo cáo.

Giả sử bảng `daily_activity` có một hàng cho mỗi tài khoản và mỗi ngày:

```text
account_id | activity_date | amount
-----------+---------------+-------
10         | 2026-11-01    | 100
10         | 2026-11-02    | 50
10         | 2026-11-05    | 80
20         | 2026-11-01    | 40
20         | 2026-11-03    | 20
```

Nếu cần tìm ngày thiếu theo từng tài khoản, phải phân vùng theo `account_id`. Nếu chỉ sắp xếp `activity_date` toàn bảng, một ngày của tài khoản 10 có thể bị so sánh nhầm với ngày của tài khoản 20.

Ngoài ra, cần quyết định một ngày có được phép có nhiều hàng hay không. Nếu bảng lưu từng giao dịch, nhiều giao dịch trong một ngày là bình thường; trước khi tìm dãy ngày liên tiếp, thường phải chuẩn hóa về một hàng cho mỗi tài khoản/ngày bằng `DISTINCT` hoặc `GROUP BY`.

## 3. Phân biệt kỳ không có hàng, hàng có measure NULL và giá trị 0

Ba trạng thái sau mang ý nghĩa khác nhau:

| Trạng thái | Ví dụ | Ý nghĩa |
|---|---|---|
| Không có hàng | Không có bản ghi tháng 11 cho tài khoản | Kỳ không có bản ghi theo nguồn dữ liệu |
| Có hàng, measure NULL | Có bản ghi tháng 11 nhưng `amount IS NULL` | Kỳ có bản ghi, giá trị đo lường chưa được ghi nhận |
| Có hàng, measure bằng 0 | `amount = 0` | Kỳ đã được ghi nhận với giá trị bằng không |

Ví dụ:

```sql
SELECT account_id,
       COUNT(*) AS row_count,
       COUNT(amount) AS amount_count,
       SUM(amount) AS total_amount
FROM monthly_activity
GROUP BY account_id;
```

- `COUNT(*)` đếm hàng, kể cả khi `amount` NULL.
- `COUNT(amount)` chỉ đếm hàng có amount khác NULL.
- `SUM(amount)` bỏ qua measure NULL; nếu không có giá trị non-NULL, tổng có thể là NULL.

Khi tìm kỳ thiếu, hãy kiểm tra **sự tồn tại của hàng** bằng khóa của bảng fact, không dùng `amount IS NULL` làm đại diện cho “không có kỳ”. Nếu thay NULL bằng 0 quá sớm bằng `NVL`, báo cáo có thể không còn phân biệt được “không ghi nhận” và “đã ghi nhận bằng 0”.

## 4. Phát hiện khoảng trống giữa hai ngày bằng LAG

`LAG` lấy giá trị của hàng đứng trước trong thứ tự của một nhóm. Đây là cách trực tiếp để phát hiện hai ngày quan sát liên tiếp cách nhau hơn một ngày.

### 4.1. Chuẩn hóa về một hàng mỗi tài khoản/ngày

Nếu bảng có nhiều giao dịch mỗi ngày:

```sql
WITH activity_days AS (
    SELECT DISTINCT
           account_id,
           TRUNC(activity_date) AS activity_day
    FROM daily_activity
    WHERE activity_date IS NOT NULL
)
SELECT account_id, activity_day
FROM activity_days
ORDER BY account_id, activity_day;
```

`TRUNC(activity_date)` đưa giá trị về đầu ngày. Chỉ làm vậy khi đơn vị nghiệp vụ là **ngày lịch**; nếu cần phân tích theo giờ hoặc phút, không được loại bỏ phần thời gian.

### 4.2. Tìm khoảng trống nằm giữa hai ngày có dữ liệu

```sql
WITH activity_days AS (
    SELECT DISTINCT
           account_id,
           TRUNC(activity_date) AS activity_day
    FROM daily_activity
    WHERE activity_date IS NOT NULL
),
ordered_days AS (
    SELECT account_id,
           activity_day,
           LAG(activity_day) OVER (
               PARTITION BY account_id
               ORDER BY activity_day
           ) AS previous_day
    FROM activity_days
)
SELECT account_id,
       previous_day + 1 AS gap_start,
       activity_day - 1 AS gap_end,
       activity_day - previous_day - 1 AS missing_day_count
FROM ordered_days
WHERE previous_day IS NOT NULL
  AND activity_day > previous_day + 1
ORDER BY account_id, gap_start;
```

Giải thích:

- `PARTITION BY account_id` tạo một chuỗi riêng cho từng tài khoản.
- `ORDER BY activity_day` sắp xếp ngày trong chuỗi.
- `LAG(activity_day)` lấy ngày quan sát ngay trước đó.
- Nếu ngày hiện tại lớn hơn ngày trước cộng một, tồn tại ít nhất một ngày bị thiếu.
- `gap_start` là ngày sau ngày trước; `gap_end` là ngày trước ngày hiện tại.

Với dữ liệu mẫu, tài khoản 10 có khoảng trống 03/11–04/11? Hãy xét chính xác các ngày: ngày có dữ liệu là 01, 02 và 05, nên khoảng trống là 03/11–04/11. Tài khoản 20 có 01 và 03, nên thiếu 02/11.

**Giới hạn của cách LAG:** nó chỉ tìm khoảng trống **nằm giữa hai ngày có dữ liệu**. Nó không biết ngày nào cần có trước bản ghi đầu tiên hoặc sau bản ghi cuối cùng. Muốn phát hiện khoảng trống ở hai đầu, phải có phạm vi kỳ dự kiến hoặc bảng calendar.

### 4.3. Dùng LEAD để nhìn từ đầu khoảng trống

`LEAD` lấy giá trị ở hàng sau. Cùng bài toán có thể viết:

```sql
WITH activity_days AS (
    SELECT DISTINCT account_id,
           TRUNC(activity_date) AS activity_day
    FROM daily_activity
    WHERE activity_date IS NOT NULL
),
neighbors AS (
    SELECT account_id,
           activity_day,
           LEAD(activity_day) OVER (
               PARTITION BY account_id
               ORDER BY activity_day
           ) AS next_day
    FROM activity_days
)
SELECT account_id,
       activity_day + 1 AS gap_start,
       next_day - 1 AS gap_end,
       next_day - activity_day - 1 AS missing_day_count
FROM neighbors
WHERE next_day > activity_day + 1
ORDER BY account_id, gap_start;
```

`LAG` và `LEAD` đều phù hợp; chọn hướng nào giúp cách đọc tự nhiên hơn. Kết quả là khoảng ngày thiếu giữa hai hàng đã quan sát.

## 5. Phát hiện khoảng trống trong dãy số

Bài toán không chỉ dành cho ngày tháng. Với một dãy số thứ tự đã có:

```text
1, 2, 3, 7, 8, 12
```

ta muốn tìm các đoạn thiếu `4–6` và `9–11`.

### 5.1. Dùng LAG trên dãy số

```sql
WITH ordered_values AS (
    SELECT DISTINCT sequence_no,
           LAG(sequence_no) OVER (
               ORDER BY sequence_no
           ) AS previous_no
    FROM sequence_data
    WHERE sequence_no IS NOT NULL
)
SELECT previous_no + 1 AS missing_start,
       sequence_no - 1 AS missing_end,
       sequence_no - previous_no - 1 AS missing_count
FROM ordered_values
WHERE previous_no IS NOT NULL
  AND sequence_no > previous_no + 1
ORDER BY missing_start;
```

### 5.2. Dùng LEAD

```sql
WITH ordered_values AS (
    SELECT DISTINCT sequence_no,
           LEAD(sequence_no) OVER (
               ORDER BY sequence_no
           ) AS next_no
    FROM sequence_data
    WHERE sequence_no IS NOT NULL
)
SELECT sequence_no + 1 AS missing_start,
       next_no - 1 AS missing_end,
       next_no - sequence_no - 1 AS missing_count
FROM ordered_values
WHERE next_no > sequence_no + 1
ORDER BY missing_start;
```

`DISTINCT` giúp loại giá trị lặp trước khi tính khoảng trống. Nếu số thứ tự là một cột nghiệp vụ được quy định tăng liên tục, kỹ thuật này có ý nghĩa. Nhưng **không được mặc định mọi ID Oracle đều phải liên tiếp**.

### 5.3. Sequence và identity không bảo đảm ID liên tục

Oracle sequence được thiết kế để cấp giá trị duy nhất, không phải để tạo dãy không có khoảng trống. Các trường hợp sau có thể làm số đã cấp không xuất hiện trong bảng:

- Transaction lấy `NEXTVAL` rồi rollback.
- Sequence dùng `CACHE`, database dừng bất thường hoặc cache bị mất.
- Nhiều session lấy số đồng thời.
- Ứng dụng lấy số nhưng không insert.
- Dữ liệu bị xóa sau khi tạo.

Vì vậy, thấy ID 100 rồi đến 105 **không chứng minh** bản ghi 101–104 bị mất. Chỉ tìm khoảng trống ID nếu nghiệp vụ thực sự định nghĩa dãy số đó phải liên tục, chẳng hạn số kỳ báo cáo hoặc số thứ tự trong một quy trình có kiểm soát riêng.

## 6. Gom các giá trị liên tiếp thành từng đoạn (islands)

Khi đã có danh sách ngày hoạt động, ta thường muốn gom những ngày liên tục thành một đoạn thay vì chỉ liệt kê từng ngày.

### 6.1. Kỹ thuật ROW_NUMBER trừ ngày

Giả sử một tài khoản có ngày:

```text
01/11, 02/11, 03/11, 06/11, 07/11, 10/11
```

Đánh số hàng:

| activity_day | rn | activity_day - rn |
|---|---:|---|
| 01/11 | 1 | 31/10 |
| 02/11 | 2 | 31/10 |
| 03/11 | 3 | 31/10 |
| 06/11 | 4 | 02/11 |
| 07/11 | 5 | 02/11 |
| 10/11 | 6 | 04/11 |

Trong một đoạn liên tiếp, ngày tăng một và `rn` cũng tăng một, nên `activity_day - rn` không đổi. Khi có khoảng trống, giá trị nhóm thay đổi.

### 6.2. SQL tìm các đoạn ngày liên tiếp

```sql
WITH activity_days AS (
    SELECT DISTINCT
           account_id,
           TRUNC(activity_date) AS activity_day
    FROM daily_activity
    WHERE activity_date IS NOT NULL
),
numbered AS (
    SELECT account_id,
           activity_day,
           ROW_NUMBER() OVER (
               PARTITION BY account_id
               ORDER BY activity_day
           ) AS rn
    FROM activity_days
),
islands AS (
    SELECT account_id,
           activity_day,
           activity_day - rn AS island_key
    FROM numbered
)
SELECT account_id,
       MIN(activity_day) AS island_start,
       MAX(activity_day) AS island_end,
       COUNT(*) AS consecutive_days
FROM islands
GROUP BY account_id, island_key
ORDER BY account_id, island_start;
```

Kết quả trả một hàng cho mỗi đoạn ngày liên tiếp. `COUNT(*)` là số ngày vì CTE `activity_days` đã đảm bảo mỗi tài khoản/ngày chỉ có một hàng.

### 6.3. Vì sao phải DISTINCT trước ROW_NUMBER?

Nếu dữ liệu nguồn có hai giao dịch cùng một ngày, ví dụ:

```text
01/11
01/11
02/11
03/11
```

`ROW_NUMBER` trên dữ liệu gốc đánh số cả hai hàng 01/11. Phép trừ ngày với số thứ tự sẽ không còn giữ một khóa nhóm ổn định cho dãy ngày. Nếu mục tiêu là các **ngày lịch có phát sinh ít nhất một giao dịch**, phải khử trùng theo tài khoản/ngày trước.

Nếu mục tiêu lại là các giao dịch liên tiếp theo thời điểm, không được khử trùng; khi đó cần một khóa thứ tự riêng như `transaction_id` hoặc timestamp có tie-breaker và định nghĩa rõ thế nào là “liên tiếp”.

## 7. Gom dãy số nguyên liên tiếp

Kỹ thuật islands cũng áp dụng cho dãy số nguyên:

```text
101, 102, 103, 110, 111, 115
```

Trong mỗi đoạn, `sequence_no - ROW_NUMBER()` là hằng số:

```sql
WITH numbered AS (
    SELECT sequence_no,
           ROW_NUMBER() OVER (
               ORDER BY sequence_no
           ) AS rn
    FROM (
        SELECT DISTINCT sequence_no
        FROM sequence_data
        WHERE sequence_no IS NOT NULL
    )
),
islands AS (
    SELECT sequence_no,
           sequence_no - rn AS island_key
    FROM numbered
)
SELECT MIN(sequence_no) AS range_start,
       MAX(sequence_no) AS range_end,
       COUNT(*) AS values_in_range
FROM islands
GROUP BY island_key
ORDER BY range_start;
```

Nếu số thứ tự được phân vùng theo một đối tượng, ví dụ `account_id`, phải thêm `PARTITION BY account_id` vào `ROW_NUMBER` và đưa `account_id` vào khóa nhóm:

```sql
ROW_NUMBER() OVER (
    PARTITION BY account_id
    ORDER BY sequence_no
)
```

Không trộn các dãy của nhiều đối tượng trong một phép đánh số toàn cục.

## 8. Gom các tháng liên tiếp

Đối với tháng, không nên trừ ngày bằng một số cố định như 30. Tháng có 28, 29, 30 hoặc 31 ngày. Hãy chuẩn hóa về ngày đầu tháng rồi dùng `ADD_MONTHS`.

### 8.1. Tạo danh sách tháng đã có dữ liệu

```sql
WITH activity_months AS (
    SELECT DISTINCT
           account_id,
           TRUNC(activity_date, 'MM') AS month_start
    FROM daily_activity
    WHERE activity_date IS NOT NULL
),
numbered AS (
    SELECT account_id,
           month_start,
           ROW_NUMBER() OVER (
               PARTITION BY account_id
               ORDER BY month_start
           ) AS rn
    FROM activity_months
),
islands AS (
    SELECT account_id,
           month_start,
           ADD_MONTHS(month_start, -rn) AS island_key
    FROM numbered
)
SELECT account_id,
       MIN(month_start) AS first_month,
       MAX(month_start) AS last_month,
       COUNT(*) AS consecutive_months
FROM islands
GROUP BY account_id, island_key
ORDER BY account_id, first_month;
```

`TRUNC(date, 'MM')` đưa mọi ngày trong cùng tháng về ngày đầu tháng. `ADD_MONTHS(month_start, -rn)` dịch lùi theo số thứ tự; trong một dãy tháng liên tiếp, khóa nhóm giữ nguyên.

### 8.2. Lưu ý về tháng tài chính

Nếu kỳ báo cáo là tháng tài chính không bắt đầu vào ngày 1, quý tài chính hoặc kỳ 4-4-5, không nên tự suy ra bằng `TRUNC(date,'MM')`. Hãy dùng bảng calendar dimension có `period_id`, `period_start`, `period_end` và thứ tự kỳ. Sau đó áp dụng kỹ thuật islands trên `period_sequence` của bảng lịch.

## 9. Sinh lịch ngày bằng CONNECT BY LEVEL

Muốn tìm kỳ thiếu, trước hết cần biết **những kỳ nào đáng lẽ phải tồn tại**. Một cách sinh dãy ngày nhanh trong Oracle là `CONNECT BY LEVEL`.

### 9.1. Sinh từng ngày trong khoảng

Giả sử `:p_start_date` và `:p_end_date` là bind variable kiểu DATE:

```sql
SELECT TRUNC(:p_start_date) + LEVEL - 1 AS calendar_day
FROM dual
CONNECT BY LEVEL <=
       TRUNC(:p_end_date) - TRUNC(:p_start_date) + 1;
```

Ví dụ nếu bắt đầu ngày 01/11/2026 và kết thúc 05/11/2026, truy vấn sinh ra năm ngày, bao gồm cả hai đầu.

`LEVEL` bắt đầu từ 1. Phép cộng số nguyên vào DATE dịch ngày theo số ngày tương ứng.

Nếu `:p_end_date` trước `:p_start_date`, biểu thức giới hạn không dương và không có ngày nào được sinh. Trong ứng dụng, nên kiểm tra khoảng đầu vào để phản hồi rõ thay vì để báo cáo rỗng khó giải thích.

### 9.2. Sinh lịch tháng

```sql
SELECT ADD_MONTHS(TRUNC(:p_start_date, 'MM'), LEVEL - 1)
       AS month_start
FROM dual
CONNECT BY LEVEL <=
       MONTHS_BETWEEN(
           TRUNC(:p_end_date, 'MM'),
           TRUNC(:p_start_date, 'MM')
       ) + 1;
```

Hai mốc được chuẩn hóa về đầu tháng trước khi gọi `MONTHS_BETWEEN`, nên số tháng trong khoảng là số nguyên nếu khoảng hợp lệ.

### 9.3. Khi nào nên dùng bảng calendar thay vì sinh lịch tức thời?

`CONNECT BY LEVEL` phù hợp cho khoảng ngày/tháng đơn giản. Một bảng calendar dimension dùng chung tốt hơn khi cần:

- Ngày làm việc, cuối tuần và ngày nghỉ lễ.
- Kỳ tài chính, tuần ISO hoặc lịch 4-4-5.
- Ngày bắt đầu/kết thúc kỳ theo quy ước nghiệp vụ.
- Mã thứ tự kỳ ổn định để tìm chuỗi liên tiếp.
- Nhiều báo cáo dùng chung cùng một định nghĩa lịch.

Calendar dimension còn giúp phân biệt ngày lịch tồn tại với ngày doanh nghiệp thực sự hoạt động.

## 10. Tìm các ngày không có dữ liệu bằng anti-join

Sau khi sinh lịch, so sánh lịch dự kiến với những ngày đã có trong bảng fact.

### 10.1. NOT EXISTS

```sql
WITH calendar_days AS (
    SELECT TRUNC(:p_start_date) + LEVEL - 1 AS calendar_day
    FROM dual
    CONNECT BY LEVEL <=
           TRUNC(:p_end_date) - TRUNC(:p_start_date) + 1
),
activity_days AS (
    SELECT DISTINCT TRUNC(activity_date) AS activity_day
    FROM daily_activity
    WHERE activity_date >= TRUNC(:p_start_date)
      AND activity_date <  TRUNC(:p_end_date) + 1
)
SELECT c.calendar_day AS missing_day
FROM calendar_days c
WHERE NOT EXISTS (
    SELECT 1
    FROM activity_days a
    WHERE a.activity_day = c.calendar_day
)
ORDER BY c.calendar_day;
```

`NOT EXISTS` trả ngày trong calendar mà không có ngày tương ứng trong nguồn dữ liệu. Đây là cách trực tiếp để tìm kỳ thiếu.

### 10.2. LEFT JOIN ... IS NULL

Có thể viết anti-join bằng outer join:

```sql
WITH calendar_days AS (
    SELECT TRUNC(:p_start_date) + LEVEL - 1 AS calendar_day
    FROM dual
    CONNECT BY LEVEL <=
           TRUNC(:p_end_date) - TRUNC(:p_start_date) + 1
),
activity_days AS (
    SELECT DISTINCT TRUNC(activity_date) AS activity_day
    FROM daily_activity
    WHERE activity_date >= TRUNC(:p_start_date)
      AND activity_date <  TRUNC(:p_end_date) + 1
)
SELECT c.calendar_day AS missing_day
FROM calendar_days c
LEFT JOIN activity_days a
  ON a.activity_day = c.calendar_day
WHERE a.activity_day IS NULL
ORDER BY c.calendar_day;
```

`activity_day` trong CTE là ngày được chuẩn hóa và chỉ chứa giá trị non-NULL vì đã lọc nguồn. Vì vậy, `a.activity_day IS NULL` xác định phía phải không match.

`NOT EXISTS` thường dễ đọc khi chỉ cần kiểm tra không tồn tại. LEFT JOIN hữu ích nếu muốn hiển thị cả kỳ có và không có dữ liệu.

### 10.3. Dùng MINUS để lấy tập kỳ thiếu

Với hai tập cùng kiểu và cùng số cột, có thể dùng:

```sql
WITH calendar_days AS (
    SELECT TRUNC(:p_start_date) + LEVEL - 1 AS calendar_day
    FROM dual
    CONNECT BY LEVEL <=
           TRUNC(:p_end_date) - TRUNC(:p_start_date) + 1
),
activity_days AS (
    SELECT DISTINCT TRUNC(activity_date) AS activity_day
    FROM daily_activity
    WHERE activity_date >= TRUNC(:p_start_date)
      AND activity_date <  TRUNC(:p_end_date) + 1
)
SELECT calendar_day
FROM calendar_days
MINUS
SELECT activity_day
FROM activity_days;
```

`MINUS` trả những ngày có trong lịch nhưng không có trong tập ngày hoạt động. Hai nhánh phải tương thích số cột và kiểu dữ liệu.

## 11. Tìm kỳ thiếu theo từng tài khoản

Một báo cáo toàn cục chỉ cho biết ngày nào không có dữ liệu ở bất kỳ tài khoản nào. Nhiều trường hợp cần biết **từng tài khoản thiếu kỳ nào**.

### 11.1. Tạo tổ hợp tài khoản × kỳ dự kiến

```sql
WITH calendar_months AS (
    SELECT ADD_MONTHS(TRUNC(:p_start_date, 'MM'), LEVEL - 1)
           AS month_start
    FROM dual
    CONNECT BY LEVEL <=
           MONTHS_BETWEEN(
               TRUNC(:p_end_date, 'MM'),
               TRUNC(:p_start_date, 'MM')
           ) + 1
),
expected_periods AS (
    SELECT a.account_id,
           m.month_start
    FROM accounts a
    CROSS JOIN calendar_months m
),
actual_periods AS (
    SELECT DISTINCT
           account_id,
           TRUNC(activity_date, 'MM') AS month_start
    FROM monthly_activity
    WHERE activity_date >= TRUNC(:p_start_date, 'MM')
      AND activity_date <  ADD_MONTHS(TRUNC(:p_end_date, 'MM'), 1)
)
SELECT e.account_id,
       e.month_start AS missing_month
FROM expected_periods e
WHERE NOT EXISTS (
    SELECT 1
    FROM actual_periods a
    WHERE a.account_id = e.account_id
      AND a.month_start = e.month_start
)
ORDER BY e.account_id, e.month_start;
```

`CROSS JOIN` tạo mọi tổ hợp tài khoản và tháng trong phạm vi. `NOT EXISTS` loại những tổ hợp đã có dữ liệu, còn lại là kỳ thiếu.

**Lưu ý:** ví dụ này giả định mọi tài khoản trong `ACCOUNTS` đều phải có dữ liệu trong toàn bộ khoảng báo cáo. Nếu tài khoản chỉ có nghĩa vụ báo cáo từ ngày mở đến ngày đóng, cần giới hạn `expected_periods` theo vòng đời tài khoản.

### 11.2. Chỉ xét kỳ trong thời gian tài khoản hoạt động

Giả sử bảng `accounts` có `opened_at` và `closed_at`, trong đó `closed_at` có thể NULL nếu còn hoạt động:

```sql
WITH calendar_months AS (
    SELECT ADD_MONTHS(TRUNC(:p_start_date, 'MM'), LEVEL - 1)
           AS month_start
    FROM dual
    CONNECT BY LEVEL <=
           MONTHS_BETWEEN(
               TRUNC(:p_end_date, 'MM'),
               TRUNC(:p_start_date, 'MM')
           ) + 1
),
expected_periods AS (
    SELECT a.account_id,
           m.month_start
    FROM accounts a
    JOIN calendar_months m
      ON m.month_start >= TRUNC(a.opened_at, 'MM')
     AND m.month_start <= TRUNC(
             LEAST(NVL(a.closed_at, :p_end_date), :p_end_date),
             'MM'
         )
),
actual_periods AS (
    SELECT DISTINCT
           account_id,
           TRUNC(activity_date, 'MM') AS month_start
    FROM monthly_activity
    WHERE activity_date >= TRUNC(:p_start_date, 'MM')
      AND activity_date <  ADD_MONTHS(TRUNC(:p_end_date, 'MM'), 1)
)
SELECT e.account_id,
       e.month_start AS missing_month
FROM expected_periods e
WHERE NOT EXISTS (
    SELECT 1
    FROM actual_periods a
    WHERE a.account_id = e.account_id
      AND a.month_start = e.month_start
)
ORDER BY e.account_id, e.month_start;
```

Đoạn ví dụ giả định `opened_at` không NULL và kỳ tháng được xem là phải báo cáo nếu tháng đó giao với khoảng tài khoản hoạt động theo quy tắc nghiệp vụ. Nếu tài khoản mở hoặc đóng giữa tháng mà chỉ cần báo cáo khi hoạt động đủ cả tháng, điều kiện phải thay đổi. Nếu chỉ yêu cầu dữ liệu trong phần ngày hoạt động của tháng, cần định nghĩa quy tắc riêng.

Đặc biệt, ví dụ dùng `LEAST` để giới hạn ngày đóng ở cuối phạm vi báo cáo. Nếu `closed_at` có thể trước `opened_at` do dữ liệu lỗi, hãy kiểm tra/loại những bản ghi đó ở bước chuẩn hóa.

### 11.3. Vì sao CROSS JOIN có thể tạo quá nhiều hàng?

Nếu có 1 triệu tài khoản và 120 tháng, `CROSS JOIN` có thể tạo tới 120 triệu tổ hợp trước khi lọc. Trong thực tế:

- Giới hạn danh sách tài khoản cần kiểm tra.
- Giới hạn phạm vi tháng.
- Chỉ sinh kỳ trong thời gian tài khoản có nghĩa vụ báo cáo.
- Dùng calendar dimension đã được chuẩn hóa.
- Kiểm tra execution plan và thống kê.

Không tạo toàn bộ tổ hợp nếu nghiệp vụ chỉ cần một tập con.

## 12. Báo cáo đầy đủ các kỳ: có dữ liệu, thiếu hàng hay measure NULL?

Đôi khi báo cáo cần hiển thị mọi tháng và gắn trạng thái thay vì chỉ liệt kê tháng thiếu:

```sql
WITH calendar_months AS (
    SELECT ADD_MONTHS(TRUNC(:p_start_date, 'MM'), LEVEL - 1)
           AS month_start
    FROM dual
    CONNECT BY LEVEL <=
           MONTHS_BETWEEN(
               TRUNC(:p_end_date, 'MM'),
               TRUNC(:p_start_date, 'MM')
           ) + 1
),
actual_months AS (
    SELECT account_id,
           TRUNC(activity_date, 'MM') AS month_start,
           COUNT(*) AS source_rows,
           COUNT(amount) AS amount_rows,
           SUM(amount) AS total_amount
    FROM monthly_activity
    WHERE activity_date >= TRUNC(:p_start_date, 'MM')
      AND activity_date <  ADD_MONTHS(TRUNC(:p_end_date, 'MM'), 1)
    GROUP BY account_id, TRUNC(activity_date, 'MM')
)
SELECT c.month_start,
       a.source_rows,
       a.amount_rows,
       a.total_amount,
       CASE
           WHEN a.source_rows IS NULL THEN 'MISSING_PERIOD'
           WHEN a.amount_rows = 0 THEN 'PRESENT_AMOUNT_NULL'
           WHEN a.total_amount = 0 THEN 'PRESENT_ZERO'
           ELSE 'PRESENT_WITH_VALUE'
       END AS period_status
FROM calendar_months c
LEFT JOIN actual_months a
  ON a.month_start = c.month_start
WHERE :p_account_id IS NOT NULL
  AND (a.account_id = :p_account_id OR a.account_id IS NULL)
ORDER BY c.month_start;
```

Truy vấn minh họa trạng thái theo một tài khoản; cách lọc tham số có thể viết gọn hơn bằng cách đưa `:p_account_id` vào CTE `actual_months` hoặc dùng điều kiện ở nguồn. Điều cốt yếu là:

- `a.source_rows IS NULL`: không có nhóm dữ liệu cho tháng.
- `source_rows > 0` và `amount_rows = 0`: có hàng nhưng tất cả amount NULL.
- `total_amount = 0`: tổng các giá trị amount đã ghi nhận bằng 0; cần lưu ý các giá trị dương/âm có thể triệt tiêu nhau.

Không dùng `NVL(total_amount, 0)` trước khi phân loại nếu cần phân biệt kỳ thiếu với kỳ có giá trị NULL. Hãy xác định trạng thái trước rồi mới chọn cách hiển thị.

## 13. Dùng bảng calendar dimension cho ngày làm việc

Ngày liên tiếp không phải lúc nào cũng là ngày lịch liên tiếp. Ví dụ, hệ thống chỉ kỳ vọng dữ liệu vào ngày làm việc; cuối tuần và ngày lễ không phải khoảng trống.

Một bảng lịch có thể có cấu trúc:

```sql
CREATE TABLE dim_calendar (
    calendar_date DATE PRIMARY KEY,
    is_business_day CHAR(1) NOT NULL,
    business_day_seq NUMBER,
    month_start DATE NOT NULL,
    fiscal_period_id VARCHAR2(20)
);
```

`business_day_seq` là số thứ tự liên tục chỉ tăng ở ngày làm việc; ngày nghỉ có thể để NULL. `month_start` và `fiscal_period_id` giúp nhóm theo kỳ chuẩn của doanh nghiệp.

### 13.1. Tìm ngày làm việc thiếu dữ liệu

```sql
SELECT c.calendar_date AS missing_business_day
FROM dim_calendar c
WHERE c.is_business_day = 'Y'
  AND c.calendar_date >= :p_start_date
  AND c.calendar_date <  :p_end_date + 1
  AND NOT EXISTS (
      SELECT 1
      FROM daily_activity a
      WHERE a.activity_date >= c.calendar_date
        AND a.activity_date <  c.calendar_date + 1
  )
ORDER BY c.calendar_date;
```

Điều kiện theo khoảng nửa mở tìm mọi timestamp trong ngày và có thể tận dụng index trên `activity_date` tốt hơn việc áp `TRUNC(activity_date)` lên cột trong điều kiện tương quan.

### 13.2. Tìm chuỗi ngày làm việc liên tiếp

Với ngày làm việc, không dùng phép trừ ngày lịch để phát hiện liên tiếp, vì thứ sáu và thứ hai có khoảng cách ba ngày nhưng là hai ngày làm việc kế tiếp.

Dùng thứ tự ngày làm việc trong calendar:

```sql
WITH observed_business_days AS (
    SELECT DISTINCT
           a.account_id,
           c.business_day_seq,
           c.calendar_date
    FROM daily_activity a
    JOIN dim_calendar c
      ON a.activity_date >= c.calendar_date
     AND a.activity_date <  c.calendar_date + 1
    WHERE c.is_business_day = 'Y'
      AND c.business_day_seq IS NOT NULL
),
numbered AS (
    SELECT account_id,
           business_day_seq,
           calendar_date,
           ROW_NUMBER() OVER (
               PARTITION BY account_id
               ORDER BY business_day_seq
           ) AS rn
    FROM observed_business_days
),
islands AS (
    SELECT account_id,
           business_day_seq,
           calendar_date,
           business_day_seq - rn AS island_key
    FROM numbered
)
SELECT account_id,
       MIN(calendar_date) AS first_business_day,
       MAX(calendar_date) AS last_business_day,
       COUNT(*) AS consecutive_business_days
FROM islands
GROUP BY account_id, island_key
ORDER BY account_id, first_business_day;
```

`business_day_seq` tăng một qua hai ngày làm việc liên tiếp, bất kể có bao nhiêu ngày nghỉ ở giữa. Đây là ví dụ cho thấy định nghĩa lịch thuộc nghiệp vụ, không chỉ thuộc hàm ngày giờ.

## 14. Dãy liên tiếp của trạng thái hoặc giá trị

Gaps and islands cũng có thể áp dụng cho các hàng liên tiếp có cùng trạng thái, ví dụ thiết bị liên tục ở trạng thái `RUNNING`, nhân viên giữ cùng cấp bậc hoặc một đơn hàng có các lần chuyển trạng thái.

### 14.1. Đánh dấu nơi bắt đầu một đoạn mới

Giả sử `device_events` có `device_id`, `event_time`, `status`, `event_id`. Mỗi khi trạng thái thay đổi, bắt đầu một đoạn mới:

```sql
WITH ordered_events AS (
    SELECT device_id,
           event_id,
           event_time,
           status,
           LAG(status) OVER (
               PARTITION BY device_id
               ORDER BY event_time, event_id
           ) AS previous_status
    FROM device_events
),
marked_events AS (
    SELECT device_id,
           event_id,
           event_time,
           status,
           CASE
               WHEN previous_status = status
                 OR (previous_status IS NULL AND status IS NULL)
               THEN 0
               ELSE 1
           END AS starts_new_group
    FROM ordered_events
),
grouped_events AS (
    SELECT device_id,
           event_id,
           event_time,
           status,
           SUM(starts_new_group) OVER (
               PARTITION BY device_id
               ORDER BY event_time, event_id
               ROWS UNBOUNDED PRECEDING
           ) AS group_id
    FROM marked_events
)
SELECT device_id,
       status,
       MIN(event_time) AS group_start,
       MAX(event_time) AS group_end,
       COUNT(*) AS event_count
FROM grouped_events
GROUP BY device_id, status, group_id
ORDER BY device_id, group_start;
```

Giải thích:

1. `LAG` lấy trạng thái trước đó trong từng thiết bị.
2. Nếu trạng thái khác, đánh dấu `starts_new_group = 1`.
3. Tổng lũy kế các cờ đánh dấu tạo mã nhóm.
4. Gom theo thiết bị và mã nhóm để lấy đầu/cuối đoạn.

Điều kiện `previous_status IS NULL AND status IS NULL` xử lý hai trạng thái NULL liên tiếp như cùng một trạng thái. Nếu nghiệp vụ xem NULL là “không xác định” và muốn mỗi lần NULL tạo một đoạn riêng, hãy thay quy tắc này.

`event_id` được dùng làm tie-breaker khi nhiều sự kiện có cùng `event_time`. Một thứ tự xác định giúp `LAG` và các đoạn liên tiếp có kết quả ổn định.

### 14.2. Đoạn liên tiếp của cùng một trạng thái không đồng nghĩa với khoảng thời gian liên tục

Ví dụ hai sự kiện `RUNNING` cách nhau ba ngày có thể vẫn thuộc cùng một đoạn nếu chỉ xét các hàng kề nhau có trạng thái giống nhau. Nếu nghiệp vụ yêu cầu trạng thái phải được ghi nhận liên tục theo từng phút hoặc không có khoảng trống vượt ngưỡng, phải bổ sung kiểm tra khoảng cách thời gian:

```sql
event_time - previous_event_time <= INTERVAL '5' MINUTE
```

với kiểu timestamp và quy tắc khoảng thời gian phù hợp. Phân đoạn theo **thay đổi giá trị** và phân đoạn theo **khoảng thời gian không bị gián đoạn** là hai bài toán khác nhau.

## 15. Xử lý timestamp và ranh giới kỳ

### 15.1. Ngày lịch so với thời điểm

Nếu cột `event_time` là TIMESTAMP, nhiều hàng có thể xuất hiện trong cùng ngày. Chỉ dùng `TRUNC(event_time)` khi mục tiêu là gom về ngày lịch.

Để lọc dữ liệu trong một ngày, ưu tiên:

```sql
WHERE event_time >= TIMESTAMP '2026-11-14 00:00:00'
  AND event_time <  TIMESTAMP '2026-11-15 00:00:00'
```

Khoảng nửa mở `[đầu ngày, đầu ngày kế tiếp)` tránh bỏ sót các giá trị như `23:59:59.999999`.

### 15.2. Không dùng cận cuối 23:59:59

Với `TIMESTAMP(6)`, thời điểm `23:59:59.500000` lớn hơn `23:59:59`. Điều kiện:

```sql
WHERE event_time BETWEEN
      TIMESTAMP '2026-11-14 00:00:00'
  AND TIMESTAMP '2026-11-14 23:59:59'
```

có thể bỏ sót phần lẻ giây ở cuối ngày. Dùng cận trên exclusive:

```sql
WHERE event_time >= TIMESTAMP '2026-11-14 00:00:00'
  AND event_time <  TIMESTAMP '2026-11-15 00:00:00'
```

### 15.3. Timestamp có timezone

Khi dữ liệu đến từ nhiều múi giờ, “ngày 14/11” cần gắn với timezone nghiệp vụ nào đó. Một ngày địa phương ở vùng có thay đổi DST không nhất thiết kéo dài đúng 24 giờ tuyệt đối.

Nếu báo cáo theo ngày địa phương của khách hàng:

- Xác định timezone/region của khách hàng.
- Tạo ranh giới đầu ngày và đầu ngày kế tiếp trong timezone đó.
- So sánh timestamp theo mốc tương ứng.

Không lấy timestamp UTC, `TRUNC` tùy tiện rồi giả định đó là ngày địa phương của mọi tài khoản.

## 16. Dùng MATCH_RECOGNIZE cho bài toán mẫu hàng nâng cao

Oracle hỗ trợ `MATCH_RECOGNIZE` để nhận diện mẫu hàng trong một chuỗi đã sắp xếp. Đây là công cụ nâng cao, hữu ích khi mẫu không chỉ là các ngày cách nhau một đơn vị hoặc trạng thái giống nhau đơn giản.

Ví dụ khung cú pháp:

```sql
SELECT *
FROM daily_activity
MATCH_RECOGNIZE (
    PARTITION BY account_id
    ORDER BY activity_date
    MEASURES
        FIRST(a.activity_date) AS island_start,
        LAST(a.activity_date) AS island_end,
        COUNT(*) AS day_count
    ONE ROW PER MATCH
    PATTERN (a b*)
    DEFINE
        b AS b.activity_date = PREV(b.activity_date) + 1
);
```

Đây là minh họa cú pháp nhận diện chuỗi; khi áp dụng cho dữ liệu thực tế cần xác định cách tham chiếu hàng trước, xử lý ngày trùng, điểm bắt đầu và phân vùng. Với bài toán gaps-and-islands cơ bản, `ROW_NUMBER` hoặc `LAG` thường dễ đọc và dễ bảo trì hơn.

`MATCH_RECOGNIZE` có từ Oracle Database 12c Release 1. Nếu hệ thống cũ hơn hoặc đội ngũ chưa quen pattern matching, analytic functions là lựa chọn phổ biến hơn.

## 17. Hiệu năng và cách tránh truy vấn tạo quá nhiều dữ liệu

### 17.1. Giới hạn phạm vi ngày càng sớm càng tốt

Tránh quét toàn bộ lịch sử khi chỉ cần một kỳ báo cáo:

```sql
WHERE activity_date >= :p_start_date
  AND activity_date <  :p_end_date
```

Đặt điều kiện range trực tiếp lên cột thời gian giúp Oracle có cơ hội sử dụng index phù hợp. Nếu áp `TRUNC(activity_date)` trong WHERE, index thông thường có thể khó được sử dụng theo cách mong muốn, trừ khi có function-based index phù hợp.

### 17.2. Dùng DISTINCT hoặc GROUP BY đúng grain

Nếu nguồn là bảng giao dịch, hàng triệu giao dịch có thể rút về vài nghìn tổ hợp tài khoản/ngày bằng:

```sql
SELECT account_id,
       TRUNC(activity_date) AS activity_day
FROM daily_activity
WHERE activity_date >= :p_start_date
  AND activity_date <  :p_end_date
GROUP BY account_id, TRUNC(activity_date);
```

Việc khử trùng phải đúng với câu hỏi nghiệp vụ. Không dùng DISTINCT để che dữ liệu trùng đáng lẽ phải được phát hiện như lỗi.

### 17.3. Index theo khóa phân vùng và thời gian

Với truy vấn thường xuyên tìm hoạt động theo tài khoản và ngày, index có thể được cân nhắc:

```sql
CREATE INDEX ix_daily_activity_account_date
ON daily_activity (account_id, activity_date);
```

Thứ tự cột phụ thuộc điều kiện lọc, độ chọn lọc và các truy vấn khác. Không có một index tối ưu cho mọi workload.

### 17.4. Tránh tạo Cartesian product quá lớn

`accounts CROSS JOIN calendar_months` có số hàng bằng số tài khoản nhân số tháng. Hãy:

- Lọc tài khoản trước.
- Giới hạn kỳ báo cáo.
- Chỉ tạo kỳ trong thời gian đối tượng hoạt động.
- Cân nhắc calendar table có phạm vi hợp lý.
- Dùng `NOT EXISTS` với khóa tương quan có index phù hợp.

### 17.5. Kiểm tra execution plan

Trong môi trường có quyền phù hợp:

```sql
EXPLAIN PLAN FOR
SELECT calendar_date
FROM dim_calendar c
WHERE c.is_business_day = 'Y'
  AND NOT EXISTS (
      SELECT 1
      FROM daily_activity a
      WHERE a.activity_date >= c.calendar_date
        AND a.activity_date < c.calendar_date + 1
  );

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` cho biết kế hoạch dự kiến. Khi được phép, hãy xem thống kê thực thi thực tế và đo trên khối lượng dữ liệu gần production; không kết luận hiệu năng chỉ từ cú pháp.

## 18. Những lỗi và nhầm lẫn thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| LAG phát hiện khoảng trống sai giữa các tài khoản | Quên `PARTITION BY entity_id` | Phân vùng theo đối tượng |
| Dãy ngày bị chia thành nhiều đoạn sai | Có nhiều hàng trong cùng ngày | Chuẩn hóa grain bằng DISTINCT/GROUP BY trước |
| Không tìm thấy ngày thiếu ở đầu/cuối phạm vi | LAG chỉ so sánh hai hàng quan sát | Sinh calendar và anti-join |
| Báo cáo cho rằng measure NULL là kỳ thiếu | Kiểm tra `amount IS NULL` thay vì sự tồn tại của hàng | Kiểm tra khóa fact hoặc `COUNT(*)` |
| ID có khoảng trống bị xem là mất dữ liệu | Sequence/identity không bảo đảm liên tục | Chỉ kiểm tra gap nếu nghiệp vụ quy định dãy liên tục |
| Thứ sáu và thứ hai bị coi là có gap | Dùng ngày lịch thay cho lịch làm việc | Dùng calendar dimension và business-day sequence |
| Đoạn liên tiếp sai khi có ngày trùng | ROW_NUMBER chạy trên hàng trùng | Deduplicate theo grain trước |
| Top-N/gap thay đổi giữa lần chạy | ORDER BY không xác định duy nhất | Thêm khóa tie-breaker |
| Bỏ sót timestamp cuối ngày | Dùng `23:59:59` làm cận cuối | Dùng khoảng nửa mở |
| CROSS JOIN sinh quá nhiều hàng | Không giới hạn đối tượng/kỳ | Lọc phạm vi và thời gian hoạt động |
| Kết quả lệch ngày theo timezone | Cắt timestamp không theo timezone nghiệp vụ | Xác định vùng thời gian và ranh giới ngày |

### Quy trình suy luận

1. Xác định hạt dữ liệu: một hàng đại diện cho sự kiện, ngày, tháng hay lần thay đổi trạng thái?
2. Khử trùng hoặc tổng hợp nếu bài toán cần một hàng cho mỗi kỳ.
3. Phân vùng theo từng đối tượng độc lập.
4. Xác định dãy liên tiếp theo ngày lịch, ngày làm việc, tháng hay số thứ tự.
5. Dùng LAG/LEAD để tìm gap giữa quan sát; dùng calendar để tìm kỳ thiếu trong toàn phạm vi.
6. Dùng ROW_NUMBER để tạo nhóm islands cho dãy tăng đều.
7. Phân biệt không có hàng với hàng có measure NULL hoặc bằng 0.
8. Kiểm tra ranh giới đầu/cuối, timestamp, timezone và hiệu năng.

## 19. Bài thực hành tổng hợp

Các lệnh tạo bảng và chèn dữ liệu dưới đây chỉ dành cho schema thực hành có quyền phù hợp. Không dùng bảng production hoặc chạy lệnh dọn dữ liệu trên đối tượng dùng chung.

### Bước 1. Tạo bảng hoạt động theo ngày

```sql
CREATE TABLE demo_daily_activity (
    account_id NUMBER NOT NULL,
    activity_date DATE NOT NULL,
    amount NUMBER(12, 2)
);
```

### Bước 2. Chèn dữ liệu có khoảng trống và giá trị NULL

```sql
INSERT INTO demo_daily_activity VALUES (10, DATE '2026-11-01', 100);
INSERT INTO demo_daily_activity VALUES (10, DATE '2026-11-02', 50);
INSERT INTO demo_daily_activity VALUES (10, DATE '2026-11-05', 80);
INSERT INTO demo_daily_activity VALUES (10, DATE '2026-11-06', NULL);
INSERT INTO demo_daily_activity VALUES (20, DATE '2026-11-01', 40);
INSERT INTO demo_daily_activity VALUES (20, DATE '2026-11-03', 20);

COMMIT;
```

Tài khoản 10 có dữ liệu ngày 01, 02, 05 và 06; tài khoản 20 có dữ liệu ngày 01 và 03. Hàng ngày 06 của tài khoản 10 có amount NULL nhưng **ngày đó vẫn có bản ghi**.

### Bước 3. Tìm khoảng trống giữa các ngày

```sql
WITH days AS (
    SELECT DISTINCT account_id,
           TRUNC(activity_date) AS activity_day
    FROM demo_daily_activity
),
ordered_days AS (
    SELECT account_id,
           activity_day,
           LAG(activity_day) OVER (
               PARTITION BY account_id
               ORDER BY activity_day
           ) AS previous_day
    FROM days
)
SELECT account_id,
       previous_day + 1 AS gap_start,
       activity_day - 1 AS gap_end
FROM ordered_days
WHERE previous_day IS NOT NULL
  AND activity_day > previous_day + 1
ORDER BY account_id, gap_start;
```

Kết quả mong đợi: tài khoản 10 thiếu ngày 03–04; tài khoản 20 thiếu ngày 02.

### Bước 4. Gom các ngày liên tiếp

```sql
WITH days AS (
    SELECT DISTINCT account_id,
           TRUNC(activity_date) AS activity_day
    FROM demo_daily_activity
),
numbered AS (
    SELECT account_id,
           activity_day,
           ROW_NUMBER() OVER (
               PARTITION BY account_id
               ORDER BY activity_day
           ) AS rn
    FROM days
),
islands AS (
    SELECT account_id,
           activity_day,
           activity_day - rn AS island_key
    FROM numbered
)
SELECT account_id,
       MIN(activity_day) AS island_start,
       MAX(activity_day) AS island_end,
       COUNT(*) AS day_count
FROM islands
GROUP BY account_id, island_key
ORDER BY account_id, island_start;
```

Tài khoản 10 có hai đoạn: 01–02 và 05–06. Tài khoản 20 có hai đoạn riêng: ngày 01 và ngày 03.

### Bước 5. Sinh lịch ngày và tìm ngày thiếu cho một tài khoản

```sql
WITH calendar_days AS (
    SELECT DATE '2026-11-01' + LEVEL - 1 AS calendar_day
    FROM dual
    CONNECT BY LEVEL <= 6
)
SELECT c.calendar_day
FROM calendar_days c
WHERE NOT EXISTS (
    SELECT 1
    FROM demo_daily_activity a
    WHERE a.account_id = 10
      AND a.activity_date >= c.calendar_day
      AND a.activity_date <  c.calendar_day + 1
)
ORDER BY c.calendar_day;
```

Kết quả mong đợi: ngày 03 và 04/11. Ngày 06 không được xem là thiếu dù amount NULL.

### Bước 6. Phân biệt hàng thiếu và measure NULL

```sql
SELECT account_id,
       COUNT(*) AS recorded_days,
       COUNT(amount) AS days_with_amount,
       SUM(amount) AS total_amount
FROM demo_daily_activity
GROUP BY account_id
ORDER BY account_id;
```

Đối chiếu số hàng và số measure khác NULL. Tài khoản 10 có bốn ngày ghi nhận nhưng chỉ ba ngày có amount.

### Bước 7. Dọn bảng thực hành

Chỉ sau khi xác nhận đây là bảng do bạn tạo và không cần giữ dữ liệu:

```sql
DROP TABLE demo_daily_activity PURGE;
```

`DROP TABLE ... PURGE` xóa bảng và dữ liệu, bỏ qua recycle bin theo hành vi lệnh; đây là DDL có commit ngầm. Không chạy trên bảng nghiệp vụ.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Bài toán gaps-and-islands cần xác định điều gì trước khi viết SQL?

**Trả lời:** Hạt dữ liệu, đối tượng cần phân vùng, đơn vị liên tiếp và phạm vi kỳ dự kiến.

**Câu 2.** `LAG` thường được dùng để làm gì khi tìm khoảng trống?

**Trả lời:** Lấy giá trị ở hàng trước để so sánh với giá trị hiện tại và phát hiện khoảng cách lớn hơn một đơn vị.

**Câu 3.** Vì sao LAG trên ngày quan sát không phát hiện được khoảng trống trước ngày đầu tiên?

**Trả lời:** Không có hàng trước để so sánh. Cần biết phạm vi dự kiến và sinh calendar hoặc dùng bảng lịch.

**Câu 4.** Vì sao phải dùng `PARTITION BY account_id`?

**Trả lời:** Mỗi tài khoản có một chuỗi riêng; không được so sánh ngày giữa hai tài khoản khác nhau.

**Câu 5.** Kỹ thuật `date - ROW_NUMBER()` dùng để làm gì?

**Trả lời:** Tạo khóa nhóm không đổi trong một dãy ngày liên tiếp; khi có gap, khóa nhóm thay đổi.

**Câu 6.** Trước khi tìm islands theo ngày, tại sao có thể cần `DISTINCT`?

**Trả lời:** Nguồn giao dịch có thể có nhiều hàng cùng ngày. Nếu mục tiêu là ngày có hoạt động, cần một hàng mỗi đối tượng/ngày trước khi đánh số.

**Câu 7.** Có thể dùng phép trừ ngày để tìm các tháng liên tiếp không?

**Trả lời:** Không nên trừ một số ngày cố định. Chuẩn hóa về đầu tháng rồi dùng `ADD_MONTHS`, hoặc dùng thứ tự kỳ trong calendar dimension.

**Câu 8.** Vì sao ID Oracle sequence có thể có khoảng trống hợp lệ?

**Trả lời:** Rollback, cache, cạnh tranh giữa session, lỗi ứng dụng và xóa dữ liệu đều có thể khiến số đã cấp không xuất hiện trong bảng.

**Câu 9.** Làm sao tìm các kỳ không có hàng?

**Trả lời:** Sinh tập kỳ dự kiến rồi dùng `NOT EXISTS`, `LEFT JOIN ... IS NULL` hoặc `MINUS` để tìm kỳ không có trong dữ liệu thực tế.

**Câu 10.** Có hàng nhưng amount NULL có phải kỳ thiếu không?

**Trả lời:** Không. Hàng đã tồn tại; chỉ measure chưa được ghi nhận. Cần phân biệt với kỳ hoàn toàn không có hàng.

**Câu 11.** Tại sao ngày thứ sáu và thứ hai có thể là hai ngày làm việc liên tiếp?

**Trả lời:** Cuối tuần không phải ngày làm việc. Cần dùng calendar dimension và business-day sequence thay vì khoảng cách ngày lịch.

**Câu 12.** Vì sao dùng cận `< ngày kế tiếp` khi lọc timestamp?

**Trả lời:** Để bao gồm mọi phần lẻ giây trong ngày và tránh bỏ sót thời điểm sau 23:59:59.

**Câu 13.** `OUTER JOIN` hay `NOT EXISTS` có thể dùng để tìm kỳ thiếu không?

**Trả lời:** Có. Cả hai đều có thể diễn đạt anti-join; `NOT EXISTS` thường rõ ràng khi chỉ cần kiểm tra không tồn tại.

**Câu 14.** Một `CROSS JOIN` tài khoản × tháng có rủi ro gì?

**Trả lời:** Có thể tạo số hàng rất lớn. Cần giới hạn đối tượng, kỳ báo cáo và thời gian hoạt động trước khi tạo tổ hợp.

## 21. Quy tắc ghi nhớ

| Nhu cầu | Kỹ thuật phù hợp |
|---|---|
| Tìm khoảng trống giữa hai ngày có dữ liệu | `LAG` hoặc `LEAD` |
| Tìm đoạn ngày liên tiếp | `ROW_NUMBER` và khóa `date - rn` |
| Tìm đoạn số nguyên liên tiếp | `ROW_NUMBER` và khóa `value - rn` |
| Tìm đoạn tháng liên tiếp | `ADD_MONTHS(month_start, -rn)` |
| Tìm ngày thiếu trong một phạm vi | Calendar + `NOT EXISTS` |
| Tìm tháng thiếu theo từng tài khoản | Account × calendar periods + anti-join |
| Chỉ xét kỳ trong vòng đời đối tượng | Giới hạn calendar theo ngày mở/đóng |
| Ngày làm việc liên tiếp | Calendar dimension + `business_day_seq` |
| Gom các hàng có cùng trạng thái liên tiếp | `LAG` + cờ bắt đầu nhóm + `SUM OVER` |
| Tìm mẫu hàng phức tạp | Cân nhắc `MATCH_RECOGNIZE` |
| Phân biệt hàng thiếu và measure NULL | Kiểm tra khóa hàng, `COUNT(*)`, `COUNT(measure)` |

## 22. Kết luận

Xử lý khoảng trống và dãy liên tiếp trong Oracle bắt đầu bằng việc xác định đúng **đối tượng, hạt dữ liệu, đơn vị kỳ và phạm vi dự kiến**. `LAG`/`LEAD` giúp so sánh các hàng lân cận để tìm khoảng trống nằm giữa những lần quan sát; `ROW_NUMBER` kết hợp khóa ngày trừ số thứ tự hoặc giá trị trừ số thứ tự giúp gom các đoạn liên tiếp. Với tháng, hãy dùng `ADD_MONTHS` hoặc thứ tự kỳ thay vì giả định mọi tháng có cùng số ngày.

Muốn tìm cả kỳ bị thiếu ở đầu, cuối hoặc trong toàn bộ phạm vi, hãy tạo tập kỳ dự kiến bằng `CONNECT BY LEVEL` hoặc calendar dimension, sau đó dùng `NOT EXISTS`, `LEFT JOIN ... IS NULL` hoặc `MINUS` để đối chiếu dữ liệu thực tế. Khi báo cáo theo từng tài khoản, chỉ tạo các kỳ mà tài khoản thực sự có nghĩa vụ ghi nhận. Khi xét ngày làm việc, dùng lịch nghiệp vụ thay vì ngày lịch thuần.

Cuối cùng, **không có hàng**, **có hàng nhưng measure NULL** và **có giá trị bằng 0** là ba trạng thái khác nhau. Sequence ID cũng không mặc định phải liên tục. Phân biệt đúng các trường hợp này giúp báo cáo phát hiện thiếu dữ liệu chính xác, tránh cảnh báo sai và tạo được truy vấn vừa rõ nghĩa vừa có khả năng mở rộng.

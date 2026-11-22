# Cộng trừ ngày giờ, khoảng thời gian và chênh lệch thời gian

Ngày giờ xuất hiện trong hầu hết các hệ thống dữ liệu: thời điểm khách đặt hàng, hạn thanh toán, thời gian xử lý một yêu cầu hỗ trợ, tuổi của một tài khoản, lịch giao hàng hay tổng thời gian thiết bị ngừng hoạt động. SQL cho phép **cộng hoặc trừ một khoảng thời gian**, **tính chênh lệch giữa hai mốc** và **trích xuất thành phần ngày giờ** ngay trong truy vấn.

Tuy nhiên, câu “thêm một ngày” có thể mang hai ý nghĩa khác nhau: *ngày mai lúc cùng giờ địa phương* hoặc *đúng 24 giờ sau*. “Một tháng” không có độ dài cố định, còn “chênh lệch hai thời điểm” có thể cần tính theo **giây thực tế**, **ngày lịch** hoặc **số lần vượt qua ranh giới ngày**. Chọn nhầm phép tính thường gây lỗi ở cuối tháng, năm nhuận, gần nửa đêm và khi múi giờ thay đổi theo giờ mùa hè.

Bài học thuộc chương **Biểu thức và hàm** của Database SQL, hướng dẫn cách xác định đúng kiểu dữ liệu và ngữ nghĩa trước khi thực hiện phép cộng trừ. **PostgreSQL** là hệ quản trị dùng cho phần thực hành chính; cú pháp MySQL, SQL Server và SQLite được đối chiếu riêng vì phép toán thời gian không hoàn toàn giống nhau giữa các hệ.

## 1. Ba câu hỏi phải làm rõ trước khi tính toán

Với mọi yêu cầu có ngày giờ, nên trả lời ba câu hỏi:

1. **Giá trị đang biểu diễn điều gì?** Một ngày trên lịch (`DATE`), một giờ trên đồng hồ (`TIME`), một ngày giờ địa phương (`TIMESTAMP`) hay một thời điểm xác định trên trục thời gian (`TIMESTAMPTZ`)?
2. **Khoảng cần cộng/trừ có ý nghĩa gì?** Số ngày theo lịch, số tháng theo lịch, đúng N giờ/phút/giây, hay số **ngày làm việc** theo lịch doanh nghiệp?
3. **Kết quả mong muốn ở đơn vị nào?** Một ngày/hạn mới, một khoảng `INTERVAL`, tổng số giây, số ngày nguyên, hay số tháng/năm theo lịch?

Ví dụ cùng một thời điểm bắt đầu nhưng nhiều yêu cầu khác nhau:

| Yêu cầu | Cách hiểu cần chọn | Phép tính phù hợp |
|---|---|---|
| “Hết hạn đúng 48 giờ sau khi tạo” | 48 giờ thực tế | Thời điểm tạo `+ INTERVAL '48 hours'` |
| “Hẹn lại sau 7 ngày” | Cần xác nhận là 7 ngày lịch hay 168 giờ | Ngày lịch `+ 7` hoặc thời điểm `+ INTERVAL '168 hours'` |
| “Thanh toán vào cùng ngày của tháng sau” | Phép toán theo tháng dương lịch | Ngày hoặc thời điểm `+ INTERVAL '1 month'`, có quy tắc cuối tháng |
| “Mất bao lâu để đóng yêu cầu?” | Khoảng giữa hai mốc kết thúc và bắt đầu | `closed_at - opened_at` |
| “Có bao nhiêu đơn trong ngày 01/06 tại Việt Nam?” | Biên ngày theo múi giờ Việt Nam | Hai mốc nửa đêm địa phương, lọc bằng `>=` và `<` |
| “Thêm 3 ngày làm việc” | Bỏ cuối tuần/ngày nghỉ theo lịch công ty | Lịch làm việc và quy tắc nghiệp vụ, không chỉ `INTERVAL '3 days'` |

Từ khóa quan trọng nhất là **ngữ nghĩa**: SQL có thể tính toán chính xác theo quy tắc của nó, nhưng truy vấn vẫn sai nếu quy tắc đó khác nhu cầu nghiệp vụ.

## 2. Phân biệt các kiểu dữ liệu thời gian

PostgreSQL có những kiểu thường gặp sau:

| Kiểu | Ví dụ | Ý nghĩa |
|---|---|---|
| `DATE` | `DATE '2026-06-01'` | Một ngày theo lịch, không có giờ |
| `TIME WITHOUT TIME ZONE` | `TIME '09:30:00'` | Giờ trong ngày, không kèm ngày và vùng |
| `TIMESTAMP WITHOUT TIME ZONE` | `TIMESTAMP '2026-06-01 09:30:00'` | Ngày giờ trên đồng hồ, chưa tự xác định múi giờ |
| `TIMESTAMP WITH TIME ZONE` (`TIMESTAMPTZ`) | `TIMESTAMPTZ '2026-06-01 09:30:00+07'` | Một thời điểm xác định; hiển thị theo múi giờ phiên |
| `INTERVAL` | `INTERVAL '2 days 3 hours'` | Một khoảng để cộng/trừ hoặc biểu diễn chênh lệch thời gian |

**Không nên nhầm kiểu `TIMESTAMP` trong PostgreSQL với `TIMESTAMPTZ`.** Dòng `2026-06-01 09:30:00` không có múi giờ có thể xảy ra ở nhiều thời điểm thực khác nhau tại các khu vực. Một giá trị `TIMESTAMPTZ` được xác định bằng mốc và thông tin độ lệch/múi giờ khi nhập; PostgreSQL có thể hiển thị nó khác giờ theo `TimeZone` của phiên.

```sql
-- PostgreSQL: kiểm tra kiểu thực tế của biểu thức.
SELECT
    pg_typeof(DATE '2026-06-01') AS date_type,
    pg_typeof(TIMESTAMP '2026-06-01 09:30') AS timestamp_type,
    pg_typeof(TIMESTAMPTZ '2026-06-01 09:30+07') AS instant_type,
    pg_typeof(INTERVAL '2 days') AS interval_type;
```

Hàm `pg_typeof()` thuộc PostgreSQL. Với hệ khác, tên kiểu và cách diễn giải giá trị thời gian có thể khác, nên ví dụ chuyển đổi cần điều chỉnh theo nền tảng.

### 2.1. Thời điểm và giờ địa phương

Xét cùng một thời điểm:

```text
2026-06-01 09:00:00+07  tại Asia/Ho_Chi_Minh
             │
             └── cùng thời điểm ── 2026-06-01 02:00:00+00 tại UTC
```

Hai biểu diễn khác nhau **không có nghĩa hai sự kiện khác nhau**. Khi tính thời gian đã trôi qua giữa các sự kiện thực tế, nên sử dụng các thời điểm nhất quán. Khi tính “thứ Hai tuần tới lúc 09:00 tại một địa điểm”, cần giữ ngữ nghĩa ngày giờ địa phương và múi giờ nghiệp vụ.

### 2.2. `INTERVAL` không phải một thời điểm

`DATE` hay `TIMESTAMPTZ` biểu diễn **mốc**, trong khi `INTERVAL` biểu diễn **độ dời/khoảng**.

```sql
SELECT
    INTERVAL '2 days'             AS two_days,
    INTERVAL '3 hours 15 minutes' AS work_duration,
    INTERVAL '1 month'            AS one_calendar_month;
```

Không thể hỏi `INTERVAL '1 month'` tương đương **chính xác bao nhiêu giây trong mọi tình huống**, vì tháng có 28, 29, 30 hoặc 31 ngày. Với thời điểm có múi giờ, “1 ngày theo lịch” cũng có thể khác “24 giờ đã trôi qua” ở vùng có giờ mùa hè.

## 3. Cộng trừ ngày (`DATE`)

### 3.1. Cộng hoặc trừ số ngày nguyên

Trong PostgreSQL, `DATE + INTEGER` trả về một `DATE`:

```sql
SELECT
    DATE '2026-06-01' + 7 AS one_week_later,
    DATE '2026-06-01' - 3 AS three_days_earlier;
```

Kết quả lần lượt là `2026-06-08` và `2026-05-29`. Đây là phép dịch **số ngày theo lịch**, phù hợp với câu hỏi như “hạn sau bảy ngày lịch”.

```sql
SELECT DATE '2026-12-31' + 1 AS next_date;
-- 2027-01-01.
```

PostgreSQL xử lý chuyển tháng và năm trong phép toán lịch; không cần tự viết quy tắc số ngày từng tháng.

### 3.2. Cộng `INTERVAL` vào `DATE`

```sql
SELECT
    DATE '2026-06-01' + INTERVAL '2 days'   AS after_two_days,
    DATE '2026-06-01' + INTERVAL '3 hours'  AS after_three_hours;
```

Trong PostgreSQL, khi cộng `INTERVAL` vào `DATE`, kết quả thường có kiểu **`TIMESTAMP`**, bởi một khoảng có thể bao gồm giờ/phút/giây. Ví dụ thứ hai có giá trị `2026-06-01 03:00:00`, tính từ đầu ngày. Do đó:

- Dùng `date_col + 7` nếu muốn thêm **bảy ngày và tiếp tục nhận `DATE`**.
- Dùng `date_col + INTERVAL '7 days'` nếu cần làm việc dưới dạng thời điểm ngày giờ.
- Nếu cần `DATE` sau khi cộng `INTERVAL`, có thể ép lại kiểu một cách có chủ đích: `CAST(... AS DATE)`.

```sql
SELECT CAST(
    DATE '2026-06-01' + INTERVAL '1 month'
    AS DATE
) AS next_month_date;
-- 2026-07-01.
```

Lựa chọn kiểu kết quả phải theo ý nghĩa cột đích. Nếu cột hạn thanh toán chỉ lưu ngày, chuyển đổi về `DATE` là hợp lý; nếu hạn có cả thời điểm chính xác, không nên bỏ phần giờ.

### 3.3. Năm nhuận và ngày 29/02

```sql
SELECT
    DATE '2024-02-28' + 1 AS leap_year_next_day,
    DATE '2025-02-28' + 1 AS common_year_next_day;
```

Trong năm nhuận 2024, ngày sau `28/02` là `29/02`; trong năm thường 2025, ngày sau `28/02` là `01/03`. Kiểu ngày của database giúp tránh việc tự giả định mỗi tháng có số ngày cố định.

### 3.4. Chênh lệch hai giá trị `DATE`

Trong PostgreSQL:

```sql
SELECT DATE '2026-06-10' - DATE '2026-06-01' AS days_between;
-- 9, kiểu INTEGER.
```

`DATE - DATE` trả về **số ngày nguyên giữa hai ngày**, không tính ngày bắt đầu như một ngày đã trôi qua. Từ 1/6 đến đầu ngày 10/6 là 9 ngày.

Nếu một báo cáo nghiệp vụ muốn **đếm số ngày trên lịch có tham gia, bao gồm cả hai ngày đầu và cuối**, quy tắc khác:

```sql
SELECT (DATE '2026-06-10' - DATE '2026-06-01') + 1
       AS inclusive_calendar_day_count;
-- 10 ngày lịch.
```

Không nên cộng `+1` vô điều kiện: nhiều bài toán như “số ngày chậm thanh toán” hoặc “khoảng đã trôi qua” không dùng cách đếm bao gồm hai đầu.

## 4. Cộng trừ `TIMESTAMP` với `INTERVAL`

### 4.1. Cộng giờ, phút, giây

Với `TIMESTAMP` không kèm múi giờ:

```sql
SELECT
    TIMESTAMP '2026-06-01 09:30:00' + INTERVAL '2 hours'
        AS after_two_hours,
    TIMESTAMP '2026-06-01 09:30:00' + INTERVAL '45 minutes'
        AS after_forty_five_minutes,
    TIMESTAMP '2026-06-01 09:30:00' - INTERVAL '90 seconds'
        AS ninety_seconds_earlier;
```

Kết quả:

| Biểu thức | Kết quả |
|---|---|
| `09:30 + 2 hours` | `2026-06-01 11:30:00` |
| `09:30 + 45 minutes` | `2026-06-01 10:15:00` |
| `09:30 - 90 seconds` | `2026-06-01 09:28:30` |

Một `INTERVAL` có thể gồm nhiều thành phần:

```sql
SELECT TIMESTAMP '2026-06-01 09:30:00'
       + INTERVAL '1 day 2 hours 15 minutes' AS shifted_time;
-- 2026-06-02 11:45:00.
```

Trong PostgreSQL, `INTERVAL '90 minutes'` là cách biểu diễn hợp lệ; các hệ quản trị khác có thể dùng hàm thêm thời gian như `DATEADD` hoặc `DATE_ADD`.

### 4.2. Trừ khoảng thời gian

```sql
SELECT TIMESTAMP '2026-06-02 08:00:00'
       - INTERVAL '12 hours' AS previous_evening;
-- 2026-06-01 20:00:00.
```

Đây là phép dịch mốc thời gian về quá khứ. Nếu nguồn là `TIMESTAMP` không có múi giờ, SQL không thể tự biết một khoảng giờ địa phương nào đó có bị bỏ qua do chuyển giờ mùa hè hay không; ta chỉ đang tính trên các giá trị ngày giờ không gắn vùng.

### 4.3. Khoảng âm

```sql
SELECT
    TIMESTAMP '2026-06-01 09:00:00'
        + INTERVAL '-2 hours' AS two_hours_before,
    TIMESTAMP '2026-06-01 09:00:00'
        - INTERVAL '2 hours' AS also_before;
```

Hai phép tính tương đương cho ví dụ đơn giản. Khoảng âm cũng có thể xuất hiện khi **kết thúc trước khi bắt đầu**, một trạng thái cần phân biệt rõ với thời gian xử lý hợp lệ.

## 5. Chênh lệch giữa hai mốc `TIMESTAMP`

### 5.1. Lấy thời điểm kết thúc trừ thời điểm bắt đầu

Trong PostgreSQL, `TIMESTAMP - TIMESTAMP` trả về `INTERVAL`:

```sql
SELECT
    TIMESTAMP '2026-06-01 11:45:30'
    - TIMESTAMP '2026-06-01 09:15:00'
    AS processing_duration;
-- 02:30:30.
```

Đọc là “thời gian kết thúc trừ thời gian bắt đầu”, nên kết quả có **2 giờ 30 phút 30 giây**.

```sql
SELECT
    TIMESTAMP '2026-06-03 01:00:00'
    - TIMESTAMP '2026-06-02 23:30:00'
    AS overnight_duration;
-- 01:30:00.
```

Phép trừ hai giá trị có **cả ngày và giờ** xử lý được trường hợp qua nửa đêm. Nếu chỉ dùng phần `TIME`, có thể thu được kết quả âm hoặc sai bối cảnh, vì không biết hai giá trị thuộc những ngày khác nhau.

### 5.2. Khi chỉ có `TIME`, cần biết ngày đi kèm

```sql
SELECT TIME '01:00:00' - TIME '23:30:00' AS clock_difference;
-- -22:30:00 trong PostgreSQL nếu xét hai giờ cùng một ngày.
```

Nếu nhân viên bắt đầu ca lúc 23:30 và kết thúc lúc 01:00 **ngày hôm sau**, phải lưu ngày bắt đầu và ngày kết thúc hoặc có quy tắc rõ ràng rằng ca xuyên đêm. Cơ sở dữ liệu không thể suy từ hai giá trị giờ đơn lẻ rằng một mốc thuộc ngày mai.

**Mô hình dữ liệu tốt:** lưu `started_at` và `finished_at` bằng kiểu thời gian chứa ngày; không cố suy diễn thời lượng từ hai cột `TIME` thiếu thông tin ngày.

### 5.3. Khoảng âm và dữ liệu sai thứ tự

```sql
SELECT
    TIMESTAMP '2026-06-01 08:00:00'
    - TIMESTAMP '2026-06-01 10:00:00'
    AS unexpected_duration;
-- -02:00:00.
```

Kết quả âm có thể hợp lệ trong phép toán lịch, nhưng đối với dữ liệu “thời gian xử lý ticket” thì thường báo hiệu **thứ tự mốc sai** hoặc dữ liệu nhập không hợp lệ. Có thể kiểm tra trước khi tính:

```sql
SELECT
    ticket_id,
    opened_at,
    closed_at,
    CASE
        WHEN closed_at IS NULL THEN 'OPEN'
        WHEN closed_at < opened_at THEN 'INVALID_ORDER'
        ELSE 'CLOSED'
    END AS record_state
FROM support_tickets;
```

Truy vấn giả định bảng `support_tickets` có các cột tương ứng. Không nên tự dùng `ABS(closed_at - opened_at)` để biến khoảng âm thành dương nếu chưa xử lý nguyên nhân, vì như vậy có thể che lỗi nguồn dữ liệu.

## 6. `INTERVAL` và đơn vị: thành phần khác tổng thời gian

Một giá trị `INTERVAL` có thể mang các thành phần tháng, ngày và thời gian nhỏ hơn ngày. Đặc biệt trong PostgreSQL, tháng và ngày có ý nghĩa lịch, nên không phải lúc nào cũng đổi chúng thành một số giây duy nhất mà giữ nguyên ngữ nghĩa.

### 6.1. Trích xuất thành phần bằng `EXTRACT`

```sql
SELECT
    EXTRACT(HOUR FROM INTERVAL '1 day 2 hours 30 minutes') AS hour_component,
    EXTRACT(MINUTE FROM INTERVAL '1 day 2 hours 30 minutes') AS minute_component,
    EXTRACT(DAY FROM INTERVAL '1 day 2 hours 30 minutes') AS day_component;
```

Kết quả lần lượt là **2**, **30**, **1**. `EXTRACT(HOUR FROM duration)` hỏi **thành phần giờ**, không phải tổng số giờ của cả khoảng. Một khoảng dài 1 ngày 2 giờ có 26 giờ nếu ta quy ước ngày ở đây là 24 giờ, nhưng thành phần `HOUR` vẫn chỉ là 2.

### 6.2. Tổng số giây của chênh lệch giữa hai thời điểm

Trong PostgreSQL, có thể lấy số giây từ phép trừ hai `TIMESTAMPTZ`:

```sql
SELECT EXTRACT(
    EPOCH FROM (
        TIMESTAMPTZ '2026-06-01 11:45:30+00'
        - TIMESTAMPTZ '2026-06-01 09:15:00+00'
    )
) AS elapsed_seconds;
-- 9030 giây.
```

9030 giây = 2 giờ × 3600 + 30 phút × 60 + 30 giây. Cách này hữu ích cho đo thời lượng xử lý, thống kê SLA hoặc tính trung bình theo giây.

Đổi số giây sang số phút hoặc giờ:

```sql
WITH durations AS (
    SELECT
        TIMESTAMPTZ '2026-06-01 11:45:30+00'
        - TIMESTAMPTZ '2026-06-01 09:15:00+00'
        AS elapsed
)
SELECT
    EXTRACT(EPOCH FROM elapsed) AS seconds_total,
    EXTRACT(EPOCH FROM elapsed) / 60 AS minutes_total,
    EXTRACT(EPOCH FROM elapsed) / 3600 AS hours_total
FROM durations;
```

Kết quả là **9030 giây**, **150.5 phút**, **2.508333… giờ**. Nếu ứng dụng cần số nguyên phút, phải nói rõ muốn **làm tròn**, **cắt phần lẻ** hay **làm tròn lên**; không nên dùng ép kiểu ngẫu nhiên vì cách xử lý phần lẻ khác nhau giữa các hệ quản trị.

### 6.3. Không đổi “một tháng” thành số giây bằng mặc định

```sql
SELECT
    DATE '2026-02-01' + INTERVAL '1 month' AS after_february,
    DATE '2026-07-01' + INTERVAL '1 month' AS after_july;
```

Khoảng từ 1/2 đến 1/3/2026 là **28 ngày**, trong khi từ 1/7 đến 1/8/2026 là **31 ngày**. Cả hai đều là “thêm một tháng lịch”.

Một số hàm trích xuất `EPOCH` từ `INTERVAL` có quy ước quy đổi phần tháng thành số ngày xấp xỉ để biểu diễn dưới dạng giây. Giá trị đó **không thể thay thế phép tính thực tế giữa hai thời điểm cụ thể** khi nhu cầu là thời lượng chính xác. Hãy cộng tháng vào một mốc cụ thể trước, rồi tính chênh lệch giữa các mốc nếu cần số giây thực tế.

## 7. Cộng tháng và năm: xử lý cuối tháng, năm nhuận

### 7.1. Một tháng không phải 30 ngày

```sql
SELECT
    DATE '2026-01-15' + INTERVAL '1 month' AS plus_one_month,
    DATE '2026-01-15' + INTERVAL '30 days' AS plus_thirty_days;
```

Kết quả lần lượt là `2026-02-15 00:00:00` và `2026-02-14 00:00:00`. **“Một tháng”** khác **“ba mươi ngày”**.

### 7.2. Ngày cuối tháng có thể bị điều chỉnh

```sql
SELECT
    DATE '2026-01-31' + INTERVAL '1 month' AS after_one_month,
    DATE '2024-01-31' + INTERVAL '1 month' AS leap_year_case;
```

Trong PostgreSQL, các kết quả là `2026-02-28 00:00:00` và `2024-02-29 00:00:00`. Khi ngày 31 không tồn tại trong tháng đích, phép cộng tháng theo lịch điều chỉnh về ngày cuối phù hợp của tháng đích.

Nếu nghiệp vụ thực sự muốn **“ngày cuối cùng của tháng kế tiếp”**, cần diễn đạt quy tắc đó tường minh, không chỉ cộng một tháng vào bất kỳ ngày nào:

```sql
-- Lấy ngày cuối của tháng kế tiếp so với ngày 15/01/2026.
SELECT CAST(
    DATE_TRUNC('month', DATE '2026-01-15')
    + INTERVAL '2 months'
    - INTERVAL '1 day'
    AS DATE
) AS last_day_of_next_month;
-- 2026-02-28.
```

`DATE_TRUNC` là hàm PostgreSQL quen thuộc. Ở hệ khác có thể cần hàm xác định cuối tháng riêng như `LAST_DAY` hay `EOMONTH`.

### 7.3. Cộng từng bước có thể khác cộng khoảng tổng hợp

Với các tháng có độ dài khác nhau, thứ tự phép cộng có thể quan trọng:

```sql
SELECT
    (
        DATE '2026-01-30' + INTERVAL '1 month'
    ) + INTERVAL '1 day' AS month_then_day,
    (
        DATE '2026-01-30' + INTERVAL '1 day'
    ) + INTERVAL '1 month' AS day_then_month;
```

Theo quy tắc PostgreSQL, `month_then_day` cho **2026-03-01 00:00:00**, còn `day_then_month` cho **2026-02-28 00:00:00**. Bởi “ngày 30/1 + một tháng” phải điều chỉnh khi tháng 2 không có ngày 30, rồi mới thêm một ngày.

**Không nên mặc định cộng các thành phần lịch có tính giao hoán** như cộng số học thông thường. Khi thiết kế lịch trả góp/hạn định kỳ, cần xác định quy tắc neo ngày:

- Luôn là **ngày 15** hằng tháng.
- Luôn là **ngày cuối tháng**.
- Hay thêm **một tháng vào ngày kỳ trước**, chấp nhận điều chỉnh ngày theo từng bước.

Ba quy tắc có thể tạo chuỗi kỳ hạn khác nhau dù cùng câu mô tả mơ hồ “mỗi tháng một lần”.

### 7.4. Cộng một năm quanh ngày 29/02

```sql
SELECT DATE '2024-02-29' + INTERVAL '1 year' AS next_year;
-- PostgreSQL: 2025-02-28 00:00:00.
```

Với dữ liệu như kỷ niệm, sinh nhật hoặc ngày gia hạn, việc chọn 28/2 hay 1/3 trong năm không nhuận là **quy tắc nghiệp vụ**; không có một đáp án tự động đúng cho mọi sản phẩm.

## 8. Chênh lệch theo năm và tháng: `AGE` khác thời lượng đã trôi qua

### 8.1. `AGE` biểu diễn chênh lệch lịch

PostgreSQL có hàm `AGE()`:

```sql
SELECT AGE(
    TIMESTAMP '2026-06-15 00:00:00',
    TIMESTAMP '2024-04-10 00:00:00'
) AS calendar_age;
-- 2 years 2 mons 5 days.
```

`AGE(later, earlier)` diễn đạt khoảng theo **năm, tháng, ngày** phù hợp với các câu hỏi như “đã qua bao nhiêu năm, tháng, ngày theo lịch”. Nó khác với một số giây cố định.

```sql
SELECT
    AGE(
        TIMESTAMP '2026-06-15',
        TIMESTAMP '2024-04-10'
    ) AS calendar_difference,
    TIMESTAMP '2026-06-15'
        - TIMESTAMP '2024-04-10'
        AS elapsed_interval;
```

Hai giá trị đều thuộc họ `INTERVAL` nhưng biểu diễn chênh lệch theo mục đích khác nhau: `AGE` nhấn mạnh thành phần **năm/tháng lịch**, còn phép trừ timestamp biểu diễn số ngày/giờ trôi qua giữa hai giá trị ngày giờ.

### 8.2. Tính “số tuổi” cần quy tắc cụ thể

Với ngày sinh hợp lệ, một cách tính **số năm lịch tròn** trong PostgreSQL:

```sql
SELECT EXTRACT(
    YEAR FROM AGE(DATE '2026-11-14', DATE '2000-12-20')
) AS completed_years;
-- 25.
```

Người sinh ngày 20/12/2000 tại ngày 14/11/2026 **chưa tới sinh nhật 26 tuổi**, nên kết quả là 25. Không thể chỉ lấy `2026 - 2000 = 26` rồi coi đó là tuổi theo số năm tròn.

Ngày 29/02 và quy tắc xác định “sinh nhật” trong năm không nhuận có thể cần đặc tả pháp lý/nghiệp vụ riêng. Hàm `AGE` là một cơ sở tính toán, nhưng bản thân câu SQL không tự quy định mọi trường hợp luật tuổi.

### 8.3. “Chênh lệch tháng” có nhiều định nghĩa

Giữa `2026-01-31` và `2026-02-01`:

- Số **ranh giới tháng lịch** đi qua là 1.
- Số **tháng đầy đủ** đã trôi qua gần như bằng 0.
- Thời lượng thực tế chỉ là 1 ngày.

Vì vậy, không nên viết “số tháng chênh lệch” mà không định nghĩa đó là số kỳ lịch, số tháng tròn hay số tháng theo tỷ lệ. Ví dụ PostgreSQL đếm **số thứ tự tháng lịch**:

```sql
SELECT
    (
        EXTRACT(YEAR FROM DATE '2026-02-01')
      - EXTRACT(YEAR FROM DATE '2026-01-31')
    ) * 12
    + (
        EXTRACT(MONTH FROM DATE '2026-02-01')
      - EXTRACT(MONTH FROM DATE '2026-01-31')
    ) AS calendar_month_boundary_difference;
-- 1.
```

Kết quả **không** có nghĩa là đã trôi qua đủ một tháng. Nó chỉ là chênh lệch giữa các chỉ số `(năm, tháng)`.

## 9. Múi giờ và giờ mùa hè: “một ngày” có thể khác “24 giờ”

### 9.1. Với `TIMESTAMPTZ`, thời điểm phải được hiểu theo vùng

Khi tính chênh lệch giữa các thời điểm thực, có thể dùng hai giá trị `TIMESTAMPTZ` đã xác định độ lệch:

```sql
SELECT EXTRACT(
    EPOCH FROM (
        TIMESTAMPTZ '2026-06-01 10:00:00+07'
        - TIMESTAMPTZ '2026-06-01 08:00:00+07'
    )
) / 3600 AS hours_elapsed;
-- 2 giờ.
```

Một thời điểm có thể hiển thị với múi giờ khác sau `SET TIME ZONE`, nhưng phép trừ hai **thời điểm đã xác định** vẫn phản ánh thời lượng giữa chúng.

### 9.2. Thay đổi giờ mùa hè làm xuất hiện ngày 23 hoặc 25 giờ

Ví dụ PostgreSQL với vùng `America/New_York`: ngày 08/03/2026 là ngày chuyển sang giờ mùa hè ở New York. Khi cộng **một ngày lịch** tới 12:00 ngày trước đó, giờ địa phương vẫn là 12:00; nhưng chỉ có **23 giờ thực tế** trôi qua.

```sql
SET TIME ZONE 'America/New_York';

SELECT
    TIMESTAMPTZ '2026-03-07 12:00:00-05'
        + INTERVAL '1 day' AS next_calendar_day,
    TIMESTAMPTZ '2026-03-07 12:00:00-05'
        + INTERVAL '24 hours' AS exactly_24_hours_later;
```

Kết quả theo múi giờ New York:

| Biểu thức | Kết quả |
|---|---|
| `+ INTERVAL '1 day'` | `2026-03-08 12:00:00-04` |
| `+ INTERVAL '24 hours'` | `2026-03-08 13:00:00-04` |

Vì chuyển từ `-05` sang `-04`, **cùng giờ địa phương ngày mai** đến sớm hơn 1 giờ thực tế. Nếu SLA yêu cầu “đúng 24 giờ”, dùng phép cộng theo **giờ thực tế**. Nếu lịch hẹn là “ngày mai cùng giờ tại New York”, cần phép cộng **ngày theo lịch địa phương** và múi giờ đúng.

```sql
RESET TIME ZONE;
```

`RESET TIME ZONE` đưa tham số về mặc định của phiên, không nhất thiết là UTC.

### 9.3. Quy tắc DST không áp dụng giống nhau ở mọi nơi

`Asia/Ho_Chi_Minh` hiện dùng UTC+07 trong các ngày ví dụ, không có bước chuyển giờ mùa hè như New York. Tuy nhiên, **không nên giả định mọi khu vực hoặc mọi mốc lịch sử đều có 24 giờ cho một ngày địa phương**.

Khi người dùng chọn lịch ở một vùng, hãy lưu **tên vùng IANA** (ví dụ `Asia/Ho_Chi_Minh` hoặc `America/New_York`) nếu phải áp dụng quy tắc thời gian của vùng đó. Chỉ lưu độ lệch `+07:00` hoặc `-05:00` không đủ để biểu diễn tất cả thay đổi theo mùa và lịch sử.

### 9.4. Lọc đúng “ngày ở Việt Nam” bằng khoảng nửa mở

Giả sử bảng `events` có cột `occurred_at TIMESTAMPTZ`. Để lấy các sự kiện trong ngày **01/06/2026 theo lịch Việt Nam**, dùng:

```sql
SELECT event_id, occurred_at
FROM events
WHERE occurred_at >= (
    TIMESTAMP '2026-06-01 00:00:00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh'
)
AND occurred_at < (
    TIMESTAMP '2026-06-02 00:00:00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh'
);
```

Hai biên là **đầu ngày địa phương** được chuyển thành thời điểm. Việc dùng `[start, next_start)` lấy mọi giây trong ngày, kể cả phần giây gần nửa đêm, và không lấy mốc bắt đầu ngày kế tiếp.

Không nên viết:

```sql
-- Không diễn đạt đủ cả ngày khi cột có giờ:
-- WHERE occurred_at BETWEEN DATE '2026-06-01'
--                       AND DATE '2026-06-01';
```

Với cột lưu thời điểm, hai giá trị ngày bằng nhau không bao phủ mọi giờ của ngày. Khi có múi giờ, cách diễn giải hai biên của `DATE` còn có thể phụ thuộc phiên. Điều kiện khoảng nửa mở với múi giờ được chỉ rõ giúp tránh cả hai nhầm lẫn.

## 10. Ngày hiện tại, thời gian hiện tại và thời điểm đo

Trong PostgreSQL:

```sql
SELECT
    CURRENT_DATE AS today_in_session,
    CURRENT_TIMESTAMP AS transaction_time,
    NOW() AS also_transaction_time,
    STATEMENT_TIMESTAMP() AS statement_started_at,
    CLOCK_TIMESTAMP() AS wall_clock_time;
```

Những giá trị này không hoàn toàn giống nhau về thời điểm đánh giá:

| Biểu thức PostgreSQL | Ý nghĩa |
|---|---|
| `CURRENT_DATE` | Ngày lịch của phiên, phụ thuộc múi giờ hiện tại |
| `CURRENT_TIMESTAMP`, `NOW()` | Thời điểm bắt đầu giao dịch hiện tại; ổn định trong cùng giao dịch |
| `STATEMENT_TIMESTAMP()` | Thời điểm bắt đầu câu lệnh hiện tại |
| `CLOCK_TIMESTAMP()` | Thời gian đồng hồ tại lúc gọi; có thể thay đổi ngay trong một câu SQL |

### 10.1. Tính tuổi dữ liệu

Ví dụ muốn tìm đơn được tạo **hơn 24 giờ trước**:

```sql
SELECT order_id, created_at
FROM orders
WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '24 hours';
```

Giả định `created_at` là `TIMESTAMPTZ`. Việc dùng `CURRENT_TIMESTAMP` giúp có một mốc nhất quán trong giao dịch, nhưng thời gian “hiện tại” ở đây là **thời điểm bắt đầu giao dịch**, không phải đồng hồ đang chạy từng giây. Nếu giao dịch mở rất lâu, mốc này có thể cũ so với thời gian thực.

Với một quy trình đo độ trễ thực tế từng giây, ứng dụng hoặc PostgreSQL có thể cần mốc đồng hồ mới hơn như `CLOCK_TIMESTAMP()`. Đó là lựa chọn theo mục đích đo lường, không phải quy tắc “luôn thay NOW bằng CLOCK_TIMESTAMP”.

### 10.2. Đo thời gian thực thi câu SQL khác tính thời lượng nghiệp vụ

`CLOCK_TIMESTAMP()` có thể giúp quan sát thời gian đồng hồ giữa các lần gọi, nhưng đo hiệu năng truy vấn bằng SQL thủ công không đáng tin cậy bằng công cụ truy vết và `EXPLAIN ANALYZE` khi cần hiệu năng thực thi. Đồng thời, thời lượng đo từ đồng hồ hệ thống có thể bị ảnh hưởng bởi điều chỉnh đồng hồ. Với đo đạc ở ứng dụng, đồng hồ **monotonic** thường phù hợp hơn để đo khoảng trôi qua; kiểu SQL `TIMESTAMPTZ` phục vụ lưu mốc sự kiện và phân tích thời gian ở cơ sở dữ liệu.

## 11. Tính SLA, thời gian xử lý và hạn trả lời

Giả sử hệ thống hỗ trợ khách hàng cần biết một yêu cầu mất bao lâu để xử lý và có quá hạn không.

### 11.1. Dữ liệu ví dụ

Một bảng `support_tickets` có:

| ticket_id | opened_at | closed_at | Ý nghĩa |
|---:|---|---|---|
| 1 | 2026-06-01 09:00 | 2026-06-01 10:30 | Đóng sau 90 phút |
| 2 | 2026-06-02 23:30 | 2026-06-03 01:00 | Đóng sau 90 phút, qua nửa đêm |
| 3 | 2026-06-03 08:15 | `NULL` | Đang mở |
| 4 | 2026-06-04 16:00 | 2026-06-05 16:00 | Đóng sau 24 giờ |
| 5 | 2026-06-05 10:00 | 2026-06-05 10:00 | Đóng ngay, chênh lệch 0 |

Trong bài thử này, `opened_at` và `closed_at` là `TIMESTAMP` không kèm múi giờ và được hiểu cùng một hệ quy chiếu giờ địa phương **không có chuyển DST trong dữ liệu mẫu**. Hệ thống thật cần chọn `TIMESTAMPTZ` nếu các cột lưu **thời điểm sự kiện xác định**.

### 11.2. Chênh lệch của ticket đã đóng

```sql
SELECT
    ticket_id,
    opened_at,
    closed_at,
    closed_at - opened_at AS processing_interval,
    EXTRACT(EPOCH FROM closed_at - opened_at) / 60
        AS processing_minutes
FROM support_tickets
WHERE closed_at IS NOT NULL
ORDER BY ticket_id;
```

Kết quả phút tương ứng các ticket đã đóng: `1 → 90`, `2 → 90`, `4 → 1440`, `5 → 0`.

Phép trừ `closed_at - opened_at` trả `INTERVAL`; `EXTRACT(EPOCH FROM ...) / 60` chuyển sang **phút**. Không lấy `EXTRACT(MINUTE FROM ...)` nếu muốn tổng phút, bởi thành phần phút của khoảng `1 day` là 0 trong khi tổng phút là 1440.

### 11.3. Xử lý ticket chưa đóng

Nếu `closed_at IS NULL`, phép trừ:

```sql
SELECT closed_at - opened_at
FROM support_tickets
WHERE ticket_id = 3;
```

sẽ trả `NULL`, bởi không có mốc kết thúc. **Không nên tự coi `NULL` là thời lượng 0.**

Nếu muốn tính **thời gian đã mở tính tới hiện tại**, cần một yêu cầu khác:

```sql
-- Ví dụ ý tưởng khi opened_at là TIMESTAMPTZ trong hệ thống thật:
SELECT
    ticket_id,
    EXTRACT(EPOCH FROM CURRENT_TIMESTAMP - opened_at) / 60
        AS minutes_open_so_far
FROM support_tickets
WHERE closed_at IS NULL;
```

Thời gian đã mở tăng theo thời điểm truy vấn, còn **thời gian xử lý đã hoàn tất** chỉ có ý nghĩa khi có thời điểm đóng. Đừng gom hai chỉ số vào một cột mà không ghi rõ định nghĩa.

### 11.4. SLA “trong 2 giờ” và SLA “trước cuối ngày”

Đối với SLA đúng 2 giờ từ mốc bắt đầu:

```sql
SELECT
    ticket_id,
    opened_at,
    opened_at + INTERVAL '2 hours' AS due_at
FROM support_tickets;
```

Nếu SLA yêu cầu đóng trước “cuối ngày kế tiếp theo giờ Việt Nam”, đó là **quy tắc ngày lịch**: cần xác định ngày địa phương, ngày kế tiếp và mốc kết thúc theo vùng. Không thể suy một thời điểm chính xác từ cụm “cuối ngày” nếu chưa quy định có lấy đúng 00:00 ngày sau hay không. Thường định nghĩa “trước đầu ngày thứ hai tiếp theo” với biên trên loại trừ để tránh đoán giây cuối cùng.

Nếu SLA dựa trên **giờ làm việc** (ví dụ 08:00–17:00 từ thứ Hai tới thứ Sáu, nghỉ lễ), `+ INTERVAL '8 hours'` không phù hợp. Phải dùng lịch làm việc, bảng ngày nghỉ và quy tắc cắt khoảng theo ca.

## 12. Phân biệt ngày lịch, giờ thực tế và ngày làm việc

Ba phép tính cùng dùng từ “ngày” nhưng có thể cho ba đáp án:

| Kiểu thời lượng | Định nghĩa | Công cụ SQL thường dùng |
|---|---|---|
| **Ngày lịch** | Dịch từ một ngày trên lịch sang ngày khác | `DATE + n`, `INTERVAL 'n days'` trong ngữ cảnh lịch |
| **Giờ đã trôi qua** | Số giây giữa hai thời điểm thực | Trừ hai `TIMESTAMPTZ`, đổi bằng `EXTRACT(EPOCH)` |
| **Ngày/giờ làm việc** | Chỉ tính khoảng được doanh nghiệp cho là làm việc | Bảng lịch và phép nối/lọc/tổng hợp theo ca, ngày nghỉ |

### 12.1. Ví dụ cuối tuần

Ngày thứ Sáu `2026-06-05` cộng 3 **ngày lịch**:

```sql
SELECT DATE '2026-06-05' + 3 AS three_calendar_days_later;
-- 2026-06-08, thứ Hai.
```

Nhưng “3 **ngày làm việc** sau thứ Sáu” (nếu không làm thứ Bảy, Chủ nhật và không có ngày nghỉ khác) thường là **thứ Tư, 10/06/2026** khi quy tắc là không đếm ngày bắt đầu. SQL chỉ cộng 3 vào kiểu `DATE` không có đủ thông tin về lịch làm việc để suy kết quả này.

Một thiết kế thực tế là bảng `business_calendar(calendar_date DATE, is_workday BOOLEAN, ...)` và có thể thêm thông tin vùng, ca làm việc, ngày nghỉ theo bộ phận.

### 12.2. Tách ngày hoàn thành khỏi thời lượng

“Đơn hoàn thành trong 2 ngày” có thể nghĩa là:

- Thời lượng nhỏ hơn hoặc bằng **48 giờ thực tế**.
- Hoàn thành **trước 00:00 của ngày thứ ba** theo múi giờ nghiệp vụ.
- Hoàn thành trong **hai ngày làm việc**.

Không nên đưa cả ba yêu cầu vào một điều kiện `closed_at - opened_at <= INTERVAL '2 days'` mà không chốt rõ hợp đồng. Điều kiện đó chỉ đúng khi mô hình thời gian và ý nghĩa khoảng phù hợp với quy tắc đã chọn.

## 13. Làm tròn, cắt phần lẻ và đếm theo ranh giới

### 13.1. Thời lượng 90 giây là mấy phút?

Nếu yêu cầu **phút thực tế**, kết quả là `1.5`:

```sql
SELECT EXTRACT(EPOCH FROM INTERVAL '90 seconds') / 60
       AS exact_minutes;
-- 1.5.
```

Nếu hợp đồng tính phí quy định **mỗi phút bắt đầu được tính trọn một phút**, có thể làm tròn lên:

```sql
SELECT CEIL(
    EXTRACT(EPOCH FROM INTERVAL '90 seconds') / 60
) AS billed_minutes;
-- 2.
```

Nếu chỉ muốn số phút tròn đã trôi qua, có thể dùng `FLOOR(...)` khi thời lượng không âm:

```sql
SELECT FLOOR(
    EXTRACT(EPOCH FROM INTERVAL '90 seconds') / 60
) AS whole_minutes;
-- 1.
```

Quy tắc `CEIL`, `FLOOR` và `ROUND` khác nhau ở ranh giới và với giá trị âm; dùng chúng phải theo đặc tả tính phí hoặc đo lường.

### 13.2. Số ngày chuyển lịch khác tổng ngày trôi qua

Ví dụ:

```sql
SELECT
    DATE '2026-06-02' - DATE '2026-06-01' AS date_boundary_days,
    EXTRACT(EPOCH FROM (
        TIMESTAMP '2026-06-02 00:00:00'
        - TIMESTAMP '2026-06-01 23:59:59'
    )) AS seconds_elapsed;
```

Chênh lệch ngày lịch là **1 ngày**, còn thời lượng giữa hai timestamp là **1 giây**. Hai con số cùng đúng vì trả lời **hai câu hỏi khác nhau**.

Với kiểu có múi giờ, việc lấy `DATE` từ `TIMESTAMPTZ` còn phải xác định ngày theo vùng nào.

## 14. Tạo chuỗi ngày để tổng hợp và phát hiện ngày không có dữ liệu

PostgreSQL hỗ trợ `generate_series()` để tạo các mốc ngày/giờ. Ví dụ hiển thị toàn bộ ngày từ 1/6 đến 7/6/2026, kể cả ngày không có đơn:

```sql
SELECT
    CAST(day_value AS DATE) AS report_date
FROM generate_series(
    TIMESTAMP '2026-06-01 00:00:00',
    TIMESTAMP '2026-06-07 00:00:00',
    INTERVAL '1 day'
) AS calendar_days(day_value)
ORDER BY report_date;
```

Truy vấn trả về **7 ngày**, bao gồm hai biên của `generate_series` trong ví dụ này. Đây là điểm cần phân biệt: **`generate_series` nhận biên cuối bao gồm**, trong khi nhiều điều kiện lọc dữ liệu thời gian nên dùng biên cuối **loại trừ**.

Muốn kết hợp dữ liệu đơn hàng theo ngày, có thể dùng khoảng nửa mở cho từng ngày được sinh:

```sql
WITH days AS (
    SELECT day_value
    FROM generate_series(
        TIMESTAMP '2026-06-01 00:00:00',
        TIMESTAMP '2026-06-07 00:00:00',
        INTERVAL '1 day'
    ) AS generated(day_value)
)
SELECT
    CAST(d.day_value AS DATE) AS report_date,
    COUNT(o.order_id) AS order_count
FROM days AS d
LEFT JOIN orders AS o
    ON o.created_at >= d.day_value
   AND o.created_at < d.day_value + INTERVAL '1 day'
GROUP BY d.day_value
ORDER BY d.day_value;
```

Ví dụ này giả định `orders.created_at` là `TIMESTAMP` không có múi giờ. Với `TIMESTAMPTZ`, phải định nghĩa ngày báo cáo ở vùng nào và dựng mốc đầu từng ngày ở vùng đó. `LEFT JOIN` giữ được những ngày không có đơn; `COUNT(o.order_id)` đếm 0 khi không có dòng phù hợp, trong khi `COUNT(*)` có thể đếm cả dòng giữ lại do `LEFT JOIN`.

## 15. Khác biệt giữa PostgreSQL, MySQL, SQL Server và SQLite

Phép cộng/trừ thời gian là một trong những phần SQL có khác biệt cú pháp đáng kể giữa hệ quản trị.

| Nhu cầu | PostgreSQL | MySQL | SQL Server | SQLite |
|---|---|---|---|---|
| Cộng 7 ngày vào ngày | `DATE '2026-06-01' + 7` | `DATE_ADD('2026-06-01', INTERVAL 7 DAY)` | `DATEADD(day, 7, CAST('2026-06-01' AS date))` | `date('2026-06-01', '+7 days')` |
| Cộng 2 giờ vào ngày giờ | `ts + INTERVAL '2 hours'` | `DATE_ADD(ts, INTERVAL 2 HOUR)` | `DATEADD(hour, 2, ts)` | `datetime(ts, '+2 hours')` |
| Hiệu ngày lịch | `date_b - date_a` | `DATEDIFF(date_b, date_a)` | `DATEDIFF(day, date_a, date_b)` | `julianday(date_b) - julianday(date_a)` |
| Chênh lệch theo đơn vị | `EXTRACT(EPOCH FROM end_ts - start_ts)` cho giây | `TIMESTAMPDIFF(SECOND, start_ts, end_ts)` | `DATEDIFF_BIG(second, start_ts, end_ts)` | `(julianday(end_ts) - julianday(start_ts)) * 86400` |
| Cộng theo tháng | `date + INTERVAL '1 month'` | `DATE_ADD(date, INTERVAL 1 MONTH)` | `DATEADD(month, 1, date)` | `date(date_value, '+1 month')` nhưng quy tắc cuối tháng cần kiểm tra |

**Cẩn thận với khác biệt về ngữ nghĩa, không chỉ tên hàm.**

### 15.1. MySQL: `DATE_ADD`, `DATE_SUB`, `DATEDIFF`, `TIMESTAMPDIFF`

```sql
-- MySQL:
SELECT DATE_ADD('2026-06-01 09:30:00', INTERVAL 2 HOUR)
       AS two_hours_later;

SELECT DATE_SUB('2026-06-01', INTERVAL 7 DAY)
       AS seven_days_earlier;

SELECT DATEDIFF('2026-06-10', '2026-06-01')
       AS calendar_days;
-- 9.

SELECT TIMESTAMPDIFF(
    MINUTE,
    '2026-06-01 09:00:00',
    '2026-06-01 10:30:00'
) AS minutes_between;
-- 90.
```

`DATEDIFF()` trong MySQL trả **chênh lệch ngày giữa phần ngày** của hai giá trị và không tính chi tiết phần giờ. `TIMESTAMPDIFF(unit, start, end)` tính chênh lệch theo đơn vị được yêu cầu, thường trả số nguyên theo đơn vị đó. Khi cần độ chính xác giây hoặc phần nhỏ hơn, chọn đơn vị và kiểu dữ liệu phù hợp.

### 15.2. SQL Server: `DATEADD` và `DATEDIFF` đếm ranh giới

```sql
-- SQL Server:
SELECT DATEADD(day, 7, CAST('2026-06-01' AS date))
       AS seven_days_later;

SELECT DATEDIFF(
    day,
    '2026-06-01T23:59:59',
    '2026-06-02T00:00:00'
) AS days_crossed;
-- 1.
```

Trong SQL Server, `DATEDIFF(day, start, end)` đếm **số ranh giới ngày đã đi qua**, không phải số ngày 24 giờ đầy đủ. Ở ví dụ trên chỉ có **1 giây** trôi qua nhưng đã vượt qua ranh giới nửa đêm một lần, nên `DATEDIFF(day,...) = 1`.

Nếu cần chênh lệch giây, chọn `DATEDIFF(second, ...)` hoặc `DATEDIFF_BIG` cho phạm vi lớn; vẫn phải hiểu đó là phép **đếm ranh giới của đơn vị được chọn**. Với thời lượng độ chính xác cao, cần chọn kiểu như `datetime2`/`datetimeoffset` và đơn vị phù hợp.

### 15.3. SQLite: modifier và `julianday`

SQLite không có cùng hệ kiểu thời gian riêng biệt như PostgreSQL; ngày giờ thường được biểu diễn qua TEXT/REAL/INTEGER và các hàm ngày giờ.

```sql
-- SQLite:
SELECT date('2026-06-01', '+7 days') AS seven_days_later;

SELECT datetime('2026-06-01 09:30:00', '+2 hours')
       AS two_hours_later;

SELECT julianday('2026-06-10') - julianday('2026-06-01')
       AS days_between;
-- 9.0.
```

Phép trừ `julianday` dùng số thực nên có thể mang sai số làm tròn ở mức rất nhỏ khi tính đơn vị giây. Nếu dùng Unix epoch để tính giây, cần biết độ chính xác và phiên bản SQLite; không nên mặc định chuỗi ngày giờ và các hàm của SQLite hoạt động y hệt kiểu `TIMESTAMPTZ` của PostgreSQL.

Đặc biệt, **quy tắc dịch tháng ở cuối tháng có thể khác** giữa SQLite và PostgreSQL. Khi chuyển từ hệ quản trị này sang hệ khác, cần kiểm thử ngày 29/02, ngày 30/31 và kỳ hạn cuối tháng.

## 16. Hiệu năng: lọc trực tiếp cột thời gian bằng mốc phù hợp

### 16.1. Đừng chuyển mọi dòng sang `DATE` nếu chỉ cần một khoảng ngày

Giả sử bảng `orders` có cột `created_at TIMESTAMP` và chỉ mục B-tree trên cột đó:

```sql
-- Có thể khiến chỉ mục thông thường khó được tận dụng trực tiếp:
SELECT order_id
FROM orders
WHERE CAST(created_at AS DATE) = DATE '2026-06-01';
```

Có thể diễn đạt cùng khoảng ngày trên kiểu `TIMESTAMP` không có múi giờ bằng:

```sql
SELECT order_id
FROM orders
WHERE created_at >= TIMESTAMP '2026-06-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-06-02 00:00:00';
```

Cách thứ hai giữ cột nguyên kiểu và dùng hai biên rõ ràng. Khi có chỉ mục thông thường trên `created_at`, bộ tối ưu thường có nhiều cơ hội chọn quét phạm vi phù hợp. Không nên kết luận mọi cast trên cột đều chậm; một số hệ hỗ trợ chỉ mục biểu thức hoặc tối ưu đặc biệt.

### 16.2. “Cũ hơn 24 giờ” nên so với mốc

Thay vì chuyển từng dòng sang tuổi rồi so sánh:

```sql
-- Diễn đạt được ý nghĩa, nhưng đặt biểu thức tính trên cột:
SELECT order_id
FROM orders
WHERE CURRENT_TIMESTAMP - created_at > INTERVAL '24 hours';
```

nếu `created_at` là `TIMESTAMPTZ`, có thể viết:

```sql
SELECT order_id
FROM orders
WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '24 hours';
```

Biểu thức ở phía phải của so sánh là mốc thời gian cần đối chiếu; cột giữ nguyên để thuận tiện sử dụng chỉ mục. Điều kiện này biểu diễn “cũ hơn 24 giờ thực tế”. Nếu yêu cầu là “trước ngày hôm qua theo lịch địa phương”, hãy tính mốc đầu ngày theo vùng nghiệp vụ, không thay bằng 24 giờ một cách máy móc.

### 16.3. Tính toán và chỉ mục không thay thế định nghĩa nghiệp vụ

`EXPLAIN` hoặc `EXPLAIN ANALYZE` giúp xem kế hoạch và chi phí truy vấn, nhưng chỉ nên tối ưu sau khi định nghĩa rõ **tháng/ngày/giờ thực tế/ngày làm việc**. Một truy vấn chạy rất nhanh nhưng so sai biên hoặc sai múi giờ vẫn không đáp ứng yêu cầu.

## 17. Lỗi thường gặp và cách sửa

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| “Thêm 1 tháng” không đúng bằng “cộng 30 ngày” | Tháng có độ dài thay đổi | Dùng phép toán lịch khi nghiệp vụ nói theo tháng |
| Hạn từ 31/1 sang tháng 2 thành 28/2 | Tháng đích không có ngày 31 | Định nghĩa quy tắc ngày cuối tháng hoặc ngày neo |
| Cộng 1 ngày khác cộng 24 giờ ở một số nơi | Chuyển giờ mùa hè | Phân biệt ngày địa phương với giờ trôi qua |
| Trừ hai cột `TIME` qua nửa đêm cho khoảng âm lớn | Thiếu thông tin ngày | Lưu ngày và giờ bắt đầu/kết thúc |
| `EXTRACT(MINUTE FROM duration)` ra 30 khi thời lượng là 2h30 | Đang lấy thành phần phút, không phải tổng phút | `EXTRACT(EPOCH FROM duration) / 60` |
| Ngày chênh 1 nhưng thời lượng chỉ 1 giây | Đang đếm ranh giới ngày thay vì giây trôi qua | Chọn đúng đơn vị/định nghĩa |
| `closed_at - opened_at` là `NULL` | Chưa có mốc đóng | Phân biệt ticket đang mở với ticket đã đóng |
| Thời lượng âm bị “sửa” bằng `ABS()` | Dữ liệu mốc có thể sai thứ tự | Kiểm tra hợp lệ trước khi tính |
| Lọc cả tháng bằng `BETWEEN` đến 23:59:59 | Bỏ phần giây nhỏ hơn giây | Dùng khoảng nửa mở tới đầu tháng sau |
| `NOW()` không tăng trong một giao dịch dài | PostgreSQL cố định mốc ở lúc bắt đầu giao dịch | Xác định có cần `STATEMENT_TIMESTAMP()`/`CLOCK_TIMESTAMP()` |
| Dùng `DATE + 3` để cộng ba ngày làm việc | Không biết lịch nghỉ và ca làm việc | Dùng bảng lịch làm việc có quy tắc rõ |
| SQL chuyển hệ chạy sai ở `DATEDIFF` | Khác thứ tự tham số và cách đếm ranh giới | Kiểm tra tài liệu hệ đích và ví dụ biên |
| Bản báo cáo theo ngày khác giữa các kết nối | Múi giờ phiên khác | Chốt múi giờ nghiệp vụ, chuyển hai biên rõ ràng |

## 18. Thực hành trên PostgreSQL với bảng tạm

Có thể chạy toàn bộ đoạn khởi tạo dưới đây trên một database thử nghiệm bằng PostgreSQL. Bảng `temporal_lab_tickets` là **bảng tạm**, tự xóa khi phiên kết thúc.

```sql
CREATE TEMP TABLE temporal_lab_tickets (
    ticket_id INTEGER PRIMARY KEY,
    opened_at TIMESTAMP NOT NULL,
    closed_at TIMESTAMP NULL,
    ticket_status VARCHAR(20) NOT NULL
);

INSERT INTO temporal_lab_tickets
    (ticket_id, opened_at, closed_at, ticket_status)
VALUES
    (1, TIMESTAMP '2026-06-01 09:00:00',
        TIMESTAMP '2026-06-01 10:30:00', 'CLOSED'),
    (2, TIMESTAMP '2026-06-02 23:30:00',
        TIMESTAMP '2026-06-03 01:00:00', 'CLOSED'),
    (3, TIMESTAMP '2026-06-03 08:15:00',
        NULL, 'OPEN'),
    (4, TIMESTAMP '2026-06-04 16:00:00',
        TIMESTAMP '2026-06-05 16:00:00', 'CLOSED'),
    (5, TIMESTAMP '2026-06-05 10:00:00',
        TIMESTAMP '2026-06-05 10:00:00', 'CLOSED');

-- Xem chênh lệch giữa các mốc.
SELECT
    ticket_id,
    opened_at,
    closed_at,
    closed_at - opened_at AS duration_interval
FROM temporal_lab_tickets
ORDER BY ticket_id;

-- Chuyển khoảng thành tổng số phút với các ticket đã đóng.
SELECT
    ticket_id,
    EXTRACT(EPOCH FROM closed_at - opened_at) / 60
        AS processing_minutes
FROM temporal_lab_tickets
WHERE closed_at IS NOT NULL
ORDER BY ticket_id;

-- Chỉ chọn ticket xử lý quá 2 giờ thực tế.
SELECT ticket_id, opened_at, closed_at
FROM temporal_lab_tickets
WHERE closed_at IS NOT NULL
  AND closed_at - opened_at > INTERVAL '2 hours'
ORDER BY ticket_id;

-- Xem hạn SLA 2 giờ từ lúc mở.
SELECT
    ticket_id,
    opened_at,
    opened_at + INTERVAL '2 hours' AS due_at
FROM temporal_lab_tickets
ORDER BY ticket_id;
```

Trong dữ liệu mẫu, ticket **4** mất 24 giờ và là ticket đã đóng duy nhất vượt quá 2 giờ. Ticket **3** chưa có `closed_at`, nên không được tự coi là ticket đã đóng đúng hạn hoặc quá hạn; cần thêm quy tắc đánh giá thời gian đã mở tính tới một mốc tham chiếu nếu muốn đo SLA cho các ticket đang mở.

### 18.1. Tổng hợp thời lượng

```sql
SELECT
    COUNT(*) AS closed_ticket_count,
    SUM(EXTRACT(EPOCH FROM closed_at - opened_at)) / 60
        AS total_minutes,
    AVG(EXTRACT(EPOCH FROM closed_at - opened_at)) / 60
        AS avg_minutes
FROM temporal_lab_tickets
WHERE closed_at IS NOT NULL;
```

Có **4 ticket đã đóng**. Tổng thời lượng là `90 + 90 + 1440 + 0 = 1620 phút`; trung bình là **405 phút/ticket**. Đơn vị của từng biểu thức được ghi rõ để tránh nhầm “thành phần phút” với “tổng phút”.

### 18.2. Đếm ticket mở theo ngày lịch

Với cột `opened_at TIMESTAMP` của bài:

```sql
SELECT
    CAST(opened_at AS DATE) AS opened_date,
    COUNT(*) AS number_of_tickets
FROM temporal_lab_tickets
GROUP BY CAST(opened_at AS DATE)
ORDER BY opened_date;
```

Mỗi ngày từ 1/6 đến 5/6 có một ticket. Ví dụ này thể hiện phép **gom nhóm theo ngày**; nếu muốn lọc một ngày trên bảng lớn có chỉ mục `opened_at`, thường cân nhắc so sánh hai mốc `>=` và `<` thay vì ép kiểu từng dòng trong `WHERE`.

## 19. Bài tập tự luyện

Hãy dự đoán kiểu dữ liệu, đơn vị và kết quả trước khi chạy các truy vấn. Bài dùng PostgreSQL và bảng tạm ở mục 18.

### Bài 1 — Ngày lịch

Tính:

```sql
SELECT
    DATE '2026-06-01' + 10 AS after_ten_days,
    DATE '2026-06-15' - DATE '2026-06-01' AS day_difference;
```

Kết quả là ngày nào và bao nhiêu ngày? Vì sao số ngày chênh lệch không cần `INTERVAL`?

### Bài 2 — Cộng 90 phút

Một cuộc hẹn bắt đầu `2026-06-01 23:15:00` và kéo dài 90 phút. Viết câu SQL tính thời điểm kết thúc. Cuộc hẹn kết thúc vào ngày nào?

### Bài 3 — Tính tổng phút thay vì thành phần phút

Cho `INTERVAL '1 day 2 hours 30 minutes'`. So sánh `EXTRACT(MINUTE FROM ...)` với `EXTRACT(EPOCH FROM ...)/60`. Vì sao hai số không giống nhau?

### Bài 4 — Ngày cuối tháng

Trong PostgreSQL, `DATE '2026-01-31' + INTERVAL '1 month'` trả ngày nào? Nếu yêu cầu là **cuối tháng kế tiếp** tính từ bất kỳ ngày nào của tháng 1, hãy viết một biểu thức dùng `DATE_TRUNC`.

### Bài 5 — Năm nhuận

Tính:

```sql
SELECT
    DATE '2024-02-28' + 1 AS leap_result,
    DATE '2025-02-28' + 1 AS normal_result;
```

Giải thích khác biệt.

### Bài 6 — Ticket quá SLA

Với bảng `temporal_lab_tickets`, viết truy vấn liệt kê `ticket_id`, chênh lệch phút cho những ticket đã đóng **quá 120 phút**. Dự đoán kết quả.

### Bài 7 — Lọc tháng bằng khoảng nửa mở

Giả sử `created_at TIMESTAMP` lưu cả phần giây nhỏ hơn giây. Viết điều kiện lấy toàn bộ tháng 6/2026 mà không dùng `23:59:59`.

### Bài 8 — DST và phép cộng khác nhau

Với `TIMESTAMPTZ '2026-03-07 12:00:00-05'` ở New York, phân biệt kết quả của `+ INTERVAL '1 day'` và `+ INTERVAL '24 hours'` khi phiên dùng `America/New_York`. Kết quả nào thích hợp cho cuộc hẹn “ngày mai lúc 12 giờ địa phương”, kết quả nào thích hợp cho SLA 24 giờ?

### Bài 9 — Phân biệt hai định nghĩa tháng

Giữa `DATE '2026-01-31'` và `DATE '2026-02-01'`, số **ranh giới tháng** đã vượt qua là bao nhiêu? Số **ngày thực tế** giữa hai ngày là bao nhiêu? Vì sao không thể lấy một con số thay cho cả hai?

### Bài 10 — Phân trang báo cáo theo ngày và múi giờ

Bảng `events(event_id, occurred_at TIMESTAMPTZ)` cần báo cáo sự kiện trong ngày 01/06/2026 ở Việt Nam. Viết câu SQL lọc bằng hai mốc theo `Asia/Ho_Chi_Minh`. Nêu vì sao `CAST(occurred_at AS DATE) = DATE '2026-06-01'` có thể đổi kết quả khi múi giờ phiên thay đổi.

<details>
<summary>Gợi ý lời giải</summary>

**Bài 1:** `2026-06-11` và `14` ngày. Trong PostgreSQL, `DATE + INTEGER` giữ kiểu `DATE`; `DATE - DATE` cho số ngày nguyên kiểu `INTEGER`.

**Bài 2:**

```sql
SELECT TIMESTAMP '2026-06-01 23:15:00'
       + INTERVAL '90 minutes' AS appointment_end;
-- 2026-06-02 00:45:00.
```

**Bài 3:** `EXTRACT(MINUTE ...)` chỉ cho **30**, còn tổng thời lượng theo phút là `(24 + 2) * 60 + 30 = 1590` phút:

```sql
SELECT
    EXTRACT(MINUTE FROM INTERVAL '1 day 2 hours 30 minutes')
        AS minute_component,
    EXTRACT(EPOCH FROM INTERVAL '1 day 2 hours 30 minutes') / 60
        AS total_minutes;
```

Trong khoảng ví dụ không có tháng và không gắn DST, phép quy đổi ngày sang 24 giờ phục vụ mục đích minh họa.

**Bài 4:** Ngày `2026-02-28` (dưới dạng `TIMESTAMP` khi cộng `INTERVAL` với `DATE`). Để lấy **cuối tháng kế tiếp** từ một ngày trong tháng 1:

```sql
SELECT CAST(
    DATE_TRUNC('month', DATE '2026-01-15')
    + INTERVAL '2 months'
    - INTERVAL '1 day'
    AS DATE
) AS next_month_end;
```

**Bài 5:** Năm 2024 có 29/02; năm 2025 không có, nên lần lượt ra `2024-02-29` và `2025-03-01`.

**Bài 6:**

```sql
SELECT
    ticket_id,
    EXTRACT(EPOCH FROM closed_at - opened_at) / 60
        AS duration_minutes
FROM temporal_lab_tickets
WHERE closed_at IS NOT NULL
  AND closed_at - opened_at > INTERVAL '120 minutes'
ORDER BY ticket_id;
-- Ticket 4, 1440 phút.
```

**Bài 7:**

```sql
WHERE created_at >= TIMESTAMP '2026-06-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-07-01 00:00:00'
```

**Bài 8:** `+ 1 day` cho `2026-03-08 12:00:00-04`, còn `+ 24 hours` cho `2026-03-08 13:00:00-04`. Một ngày lịch phù hợp lịch hẹn cùng giờ địa phương; 24 giờ phù hợp thời lượng SLA đúng 24 giờ.

**Bài 9:** Vượt qua **1 ranh giới tháng** nhưng chỉ có **1 ngày** giữa hai ngày. Nếu câu hỏi là “đủ một tháng chưa”, đáp án lại khác; phải chọn định nghĩa nghiệp vụ.

**Bài 10:**

```sql
SELECT event_id, occurred_at
FROM events
WHERE occurred_at >= (
    TIMESTAMP '2026-06-01 00:00:00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh'
)
AND occurred_at < (
    TIMESTAMP '2026-06-02 00:00:00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh'
);
```

Ép `TIMESTAMPTZ` thành `DATE` không chỉ rõ khu vực dùng để xác định ngày nên phụ thuộc múi giờ phiên; cặp mốc địa phương chuyển thành thời điểm rõ nghĩa hơn.

</details>

## 20. Quy trình tự kiểm tra một biểu thức ngày giờ

Trước khi đưa phép cộng trừ thời gian vào ứng dụng hoặc báo cáo, hãy diễn giải truy vấn bằng lời:

1. **Nguồn:** cột là `DATE`, `TIMESTAMP`, `TIMESTAMPTZ` hay một chuỗi cần parse?
2. **Mục tiêu:** cần ngày hạn, thời điểm hạn, khoảng `INTERVAL`, tổng giây, ngày lịch hay tháng lịch?
3. **Quy tắc cộng/trừ:** “1 day” có nghĩa ngày mai cùng giờ tại vùng hay 24 giờ thực tế? “1 month” xử lý cuối tháng ra sao?
4. **Múi giờ:** việc tính ngày địa phương có dùng đúng vùng IANA và các biên ngày được chuyển đúng không?
5. **Dữ liệu thiếu/lỗi:** xử lý `NULL`, kết thúc trước bắt đầu, giờ xuyên đêm và dữ liệu sai định dạng thế nào?
6. **Đơn vị kết quả:** `EXTRACT(HOUR/MINUTE)` là **thành phần**, hay cần tổng giờ/phút qua `EPOCH`?
7. **Hiệu năng:** có thể so sánh trực tiếp cột với mốc đúng kiểu thay cho việc tính hàm trên từng dòng không?

Hãy đặc biệt nhớ ba mẫu PostgreSQL:

```sql
-- Thêm ngày theo lịch, vẫn trả DATE.
SELECT DATE '2026-06-01' + 7;

-- Tính thời lượng thực tế giữa hai thời điểm, theo giây.
SELECT EXTRACT(EPOCH FROM (
    TIMESTAMPTZ '2026-06-01 11:00:00+07'
    - TIMESTAMPTZ '2026-06-01 09:00:00+07'
));

-- Lọc một ngày với biên đầu bao gồm, biên kế tiếp loại trừ.
SELECT event_id
FROM events
WHERE occurred_at >= (
    TIMESTAMP '2026-06-01' AT TIME ZONE 'Asia/Ho_Chi_Minh'
)
AND occurred_at < (
    TIMESTAMP '2026-06-02' AT TIME ZONE 'Asia/Ho_Chi_Minh'
);
```

**Cộng trừ ngày giờ trong SQL luôn có hai phần: phép toán và ý nghĩa của phép toán.** Khi xác định đúng kiểu dữ liệu, đơn vị, múi giờ và quy tắc về khoảng lịch, ta có thể tính thời lượng, hạn xử lý và báo cáo theo kỳ một cách có thể giải thích và kiểm chứng.

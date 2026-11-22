# Hàm ngày tháng: ADD_MONTHS, MONTHS_BETWEEN, LAST_DAY và EXTRACT trong Oracle Database

Các ứng dụng thường cần tính ngày đến hạn, xác định cuối tháng, tính khoảng cách theo tháng hoặc lấy năm/tháng/ngày/giờ từ một giá trị datetime. Oracle Database cung cấp nhiều hàm ngày giờ; bốn hàm nền tảng cần hiểu rõ là **`ADD_MONTHS`, `MONTHS_BETWEEN`, `LAST_DAY` và `EXTRACT`**.

Các hàm giải quyết những bài toán khác nhau:

- **`ADD_MONTHS`** cộng hoặc trừ số tháng theo lịch.
- **`MONTHS_BETWEEN`** tính số tháng giữa hai ngày, có thể trả phần thập phân theo quy tắc Oracle.
- **`LAST_DAY`** tìm ngày cuối của tháng chứa một ngày đầu vào.
- **`EXTRACT`** lấy một trường cụ thể từ biểu thức datetime hoặc interval.

Điều quan trọng là phân biệt **tháng theo lịch** với một khoảng thời gian cố định như 30 ngày, **ngày cuối tháng** với ngày có số thứ tự giống nhau, và **thành phần của một datetime** với khoảng thời gian đã trôi qua. Các hàm này cũng chịu ảnh hưởng của kiểu dữ liệu đầu vào và một số thiết lập NLS, nên cần viết SQL tường minh thay vì dựa vào định dạng mặc định của session.

## 1. Kiểu dữ liệu ngày giờ Oracle cần nhận diện

Trước khi sử dụng hàm, cần biết cột đang lưu loại dữ liệu nào:

| Kiểu dữ liệu | Thành phần lưu | Time zone? | Ví dụ |
|---|---|---|---|
| `DATE` | Năm, tháng, ngày, giờ, phút, giây | Không | Ngày tạo đơn ở độ chính xác giây |
| `TIMESTAMP(p)` | Như DATE, thêm phần giây lẻ | Không | Thời điểm có độ chính xác microsecond |
| `TIMESTAMP(p) WITH TIME ZONE` | Timestamp cùng offset/region phù hợp | Có | Sự kiện xảy ra ở nhiều múi giờ |
| `TIMESTAMP(p) WITH LOCAL TIME ZONE` | Giá trị chuẩn hóa theo database time zone và hiển thị theo session time zone | Không giữ region nguồn | Thời điểm hiển thị theo vùng của người dùng |
| `INTERVAL YEAR TO MONTH` | Khoảng thời gian tính theo năm/tháng | Không | Thời hạn hợp đồng 1 năm 3 tháng |
| `INTERVAL DAY TO SECOND` | Khoảng thời gian theo ngày/giờ/phút/giây | Không | Thời lượng xử lý 2 ngày 3 giờ |

`DATE` của Oracle **có cả giờ, phút và giây**; nó không chỉ lưu ngày như một số kiểu DATE ở hệ thống khác. Tuy nhiên, DATE không lưu phần giây lẻ và không chứa timezone. Khi cần lưu fractional seconds hoặc thời điểm gắn múi giờ, chọn kiểu TIMESTAMP tương ứng.

### 1.1. Dùng literal và format mask rõ ràng

Oracle hỗ trợ ANSI date literal:

```sql
DATE '2024-02-29'
```

Đây là cách tạo ngày cố định không phụ thuộc `NLS_DATE_FORMAT` của session. Với timestamp:

```sql
TIMESTAMP '2024-02-29 14:30:15.123456'
```

Với chuỗi ngày giờ do người dùng hoặc file gửi đến, dùng format mask tường minh:

```sql
SELECT TO_DATE('2024-02-29', 'FXYYYY-MM-DD') AS date_value,
       TO_TIMESTAMP(
           '2024-02-29 14:30:15.123456',
           'FXYYYY-MM-DD HH24:MI:SS.FF6'
       ) AS timestamp_value
FROM dual;
```

`FX` yêu cầu cách khớp định dạng chặt chẽ hơn. Khi chuyển dữ liệu số/ngày từ chuỗi, hãy quy định format và NLS rõ ràng; đừng để môi trường máy chạy quyết định cách hiểu `02/03/2024` là ngày 2 tháng 3 hay ngày 3 tháng 2.

## 2. ADD_MONTHS — cộng hoặc trừ tháng theo lịch

### 2.1. Cú pháp

```sql
ADD_MONTHS(date, integer)
```

- `date` là ngày đầu vào.
- `integer` là số tháng cần cộng; số âm dùng để lùi về các tháng trước.
- Hàm trả về kiểu **`DATE`**, bất kể kiểu dữ liệu đầu vào là gì.

Ví dụ:

```sql
SELECT ADD_MONTHS(DATE '2024-01-15', 1) AS next_month,
       ADD_MONTHS(DATE '2024-01-15', -2) AS two_months_before,
       ADD_MONTHS(DATE '2024-01-15', 12) AS next_year
FROM dual;
```

Kết quả theo lịch Gregorian:

| NEXT_MONTH | TWO_MONTHS_BEFORE | NEXT_YEAR |
|---|---|---|
| 15-FEB-2024 | 15-NOV-2023 | 15-JAN-2025 |

Phần hiển thị cụ thể còn phụ thuộc định dạng ngày của client; giá trị DATE bên trong không phải chuỗi đã định dạng.

### 2.2. Quy tắc ngày cuối tháng

Đây là quy tắc quan trọng nhất của `ADD_MONTHS`:

**Nếu ngày đầu vào là ngày cuối cùng của tháng, hoặc tháng đích không có ngày mang cùng số thứ tự, Oracle trả về ngày cuối cùng của tháng đích.**

Ví dụ trong năm nhuận 2024:

```sql
SELECT ADD_MONTHS(DATE '2024-01-31', 1) AS jan31_plus_1,
       ADD_MONTHS(DATE '2024-01-30', 1) AS jan30_plus_1,
       ADD_MONTHS(DATE '2024-02-29', 1) AS feb29_plus_1,
       ADD_MONTHS(DATE '2024-03-31', -1) AS mar31_minus_1
FROM dual;
```

| Biểu thức | Kết quả | Vì sao? |
|---|---|---|
| 31/01/2024 + 1 tháng | 29/02/2024 | Ngày đầu vào là ngày cuối tháng; tháng đích kết thúc ngày 29 |
| 30/01/2024 + 1 tháng | 29/02/2024 | Tháng 2 không có ngày 30 |
| 29/02/2024 + 1 tháng | 31/03/2024 | Ngày đầu vào là ngày cuối tháng 2 |
| 31/03/2024 - 1 tháng | 29/02/2024 | Tháng đích không có ngày 31 |

Điểm dễ ngạc nhiên: `ADD_MONTHS(DATE '2024-02-29', 1)` là ngày 31/03, không phải 29/03, vì 29/02 là ngày cuối tháng.

### 2.3. Cộng tháng liên tiếp không luôn giống cộng một lần

Quy tắc cuối tháng khiến phép tính theo chuỗi có thể cho kết quả khác phép tính trực tiếp:

```sql
SELECT ADD_MONTHS(
           ADD_MONTHS(DATE '2024-01-30', 1),
           1
       ) AS add_twice,
       ADD_MONTHS(DATE '2024-01-30', 2) AS add_two_once
FROM dual;
```

Kết quả:

| ADD_TWICE | ADD_TWO_ONCE |
|---|---|
| 31-MAR-2024 | 30-MAR-2024 |

Giải thích:

1. 30/01 + 1 tháng = 29/02 vì tháng 2 không có ngày 30.
2. 29/02 là ngày cuối tháng, nên cộng tiếp 1 tháng = 31/03.
3. Tính trực tiếp 30/01 + 2 tháng = 30/03 vì tháng 3 có ngày 30 và ngày đầu vào 30/01 không phải ngày cuối tháng.

Do đó, khi thiết kế lịch thanh toán định kỳ, cần xác định quy tắc nghiệp vụ: mỗi kỳ tính từ **ngày đến hạn kỳ trước**, từ **ngày gốc**, hay luôn là **ngày cuối tháng**. Ba chính sách có thể cho kết quả khác nhau.

### 2.4. Ngày đến hạn theo tháng

Giả sử hợp đồng bắt đầu ngày 31/01/2024 và mỗi tháng cần đến hạn vào ngày cuối tháng:

```sql
SELECT LAST_DAY(DATE '2024-01-31') AS first_due_date,
       LAST_DAY(ADD_MONTHS(DATE '2024-01-31', 1)) AS second_due_date,
       LAST_DAY(ADD_MONTHS(DATE '2024-01-31', 2)) AS third_due_date
FROM dual;
```

Kết quả lần lượt là 31/01, 29/02 và 31/03. Cách này thể hiện rõ chính sách “ngày cuối tháng” thay vì dựa vào việc ngày gốc tình cờ là 31.

Nếu chính sách là “ngày 15 hàng tháng”, dùng `ADD_MONTHS` từ ngày gốc phù hợp:

```sql
SELECT ADD_MONTHS(DATE '2024-01-15', 1) AS due_feb,
       ADD_MONTHS(DATE '2024-01-15', 2) AS due_mar,
       ADD_MONTHS(DATE '2024-01-15', 3) AS due_apr
FROM dual;
```

### 2.5. ADD_MONTHS không phải cộng số ngày cố định

Một tháng lịch có thể dài 28, 29, 30 hoặc 31 ngày. Vì vậy:

```sql
SELECT DATE '2024-03-01' + 30 AS plus_30_days,
       ADD_MONTHS(DATE '2024-03-01', 1) AS plus_1_calendar_month
FROM dual;
```

Hai biểu thức không mang cùng ý nghĩa. Nếu cần “sau 30 ngày”, cộng số ngày. Nếu cần “cùng ngày tháng tiếp theo”, dùng `ADD_MONTHS` và xử lý quy tắc cuối tháng.

Đối với `TIMESTAMP`, `ADD_MONTHS` trả về `DATE`, nên có thể làm mất fractional seconds và timezone semantics khi Oracle chuyển kiểu đầu vào. Nếu cần giữ timestamp hoặc timezone, hãy thiết kế phép tính bằng kiểu/interval thích hợp và kiểm tra rõ cách chuyển đổi.

### 2.6. NLS_CALENDAR ảnh hưởng ADD_MONTHS

Định nghĩa tháng của `ADD_MONTHS` dựa trên tham số session `NLS_CALENDAR`. Ví dụ trên giả định lịch Gregorian. Có thể xem thiết lập:

```sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN ('NLS_CALENDAR', 'NLS_DATE_FORMAT')
ORDER BY parameter;
```

Trong môi trường cần lịch Gregorian, session có thể được cấu hình:

```sql
ALTER SESSION SET NLS_CALENDAR = 'GREGORIAN';
```

Không tùy tiện đổi `NLS_CALENDAR` trên connection pool dùng chung; session có thể được tái sử dụng bởi request khác. Với hệ thống đa lịch (ví dụ lịch Persian), cần xác định lịch nghiệp vụ và kiểm thử riêng thay vì mặc định mọi tháng đều theo Gregorian.

## 3. MONTHS_BETWEEN — tính khoảng cách theo tháng

### 3.1. Cú pháp và chiều kết quả

```sql
MONTHS_BETWEEN(date1, date2)
```

Hàm trả về kiểu `NUMBER`:

- Nếu `date1` sau `date2`, kết quả thường dương.
- Nếu `date1` trước `date2`, kết quả thường âm.
- Nếu hai ngày thỏa điều kiện cùng ngày trong tháng hoặc đều là ngày cuối tháng, kết quả là số nguyên.
- Các trường hợp còn lại có phần thập phân được tính dựa trên tháng quy ước 31 ngày và xét thành phần thời gian.

Ví dụ:

```sql
SELECT MONTHS_BETWEEN(
           DATE '2024-03-15',
           DATE '2024-02-15'
       ) AS whole_month,
       MONTHS_BETWEEN(
           DATE '2024-02-15',
           DATE '2024-03-15'
       ) AS negative_month,
       MONTHS_BETWEEN(
           DATE '2024-03-31',
           DATE '2024-02-29'
       ) AS both_month_ends
FROM dual;
```

Kết quả lần lượt là `1`, `-1` và `1`. Hai ngày cuối tháng 31/03 và 29/02 được coi là tương ứng đúng một tháng theo quy tắc hàm.

### 3.2. Vì sao có phần thập phân?

Ví dụ:

```sql
SELECT MONTHS_BETWEEN(
           DATE '2024-03-15',
           DATE '2024-02-01'
       ) AS month_difference
FROM dual;
```

Hai ngày không cùng ngày trong tháng và không đồng thời là ngày cuối tháng. Phần nguyên là 1 tháng; phần chênh lệch ngày là 14 ngày trên cơ sở 31 ngày:

\[
1 + \frac{14}{31} \approx 1.451612903
\]

Đây **không phải** số ngày chia cho 30, cũng không phải một quy ước “tháng thực tế” dùng số ngày của tháng 2 hoặc tháng 3. Oracle dùng cơ sở 31 ngày cho phần thập phân trong trường hợp này.

### 3.3. Thành phần giờ có thể ảnh hưởng kết quả

Khi hai ngày không cùng ngày trong tháng và không đồng thời là ngày cuối tháng, thành phần giờ/phút/giây cũng được xét trong phần thập phân.

Ví dụ:

```sql
SELECT MONTHS_BETWEEN(
           TO_DATE('2024-03-15 12:00:00', 'YYYY-MM-DD HH24:MI:SS'),
           TO_DATE('2024-02-01 00:00:00', 'YYYY-MM-DD HH24:MI:SS')
       ) AS with_time,
       MONTHS_BETWEEN(
           DATE '2024-03-15',
           DATE '2024-02-01'
       ) AS midnight_values
FROM dual;
```

Trường hợp đầu có thêm nửa ngày trong phần chênh lệch, nên giá trị là:

\[
1 + \frac{14.5}{31} \approx 1.467741935
\]

Một trường hợp đặc biệt cần nhớ: nếu hai ngày **cùng số ngày trong tháng**, Oracle trả số tháng nguyên ngay cả khi thành phần giờ khác nhau. Ví dụ 15/03 lúc 23:00 và 15/02 lúc 01:00 vẫn cho 1 tháng theo quy tắc này.

### 3.4. So sánh các trường hợp

| DATE1 | DATE2 | Kết quả | Lý do |
|---|---|---:|---|
| 15/03/2024 | 15/02/2024 | 1 | Cùng ngày trong tháng |
| 31/03/2024 | 29/02/2024 | 1 | Cả hai là ngày cuối tháng |
| 15/03/2024 | 01/02/2024 | ≈ 1.451613 | Khác ngày, phần lẻ dựa trên 31 ngày |
| 15/02/2024 | 15/03/2024 | -1 | Đảo thứ tự đối số |
| 30/03/2024 | 29/02/2024 | ≈ 1.032258 | Không cùng ngày và 30/03 không phải cuối tháng |

### 3.5. MONTHS_BETWEEN không phải phép đo thời lượng chính xác

Nếu mục tiêu là “đã trôi qua bao nhiêu giây?” hoặc “dịch vụ chạy bao nhiêu giờ?”, không dùng `MONTHS_BETWEEN`. Kết quả phần lẻ theo quy ước 31 ngày không phải phép đo duration vật lý.

Với DATE, phép trừ hai ngày trả số ngày:

```sql
SELECT DATE '2024-03-02' - DATE '2024-03-01' AS elapsed_days
FROM dual;
```

Với TIMESTAMP, phép trừ trả `INTERVAL DAY TO SECOND`:

```sql
SELECT TIMESTAMP '2024-03-02 03:00:00'
       - TIMESTAMP '2024-03-01 01:30:00' AS elapsed_interval
FROM dual;
```

Kết quả interval thể hiện 1 ngày 1 giờ 30 phút. Đây là ngữ nghĩa phù hợp để tính thời lượng thực; còn `MONTHS_BETWEEN` phù hợp khi nghiệp vụ thật sự định nghĩa khoảng cách theo tháng lịch của Oracle.

### 3.6. NLS_CALENDAR ảnh hưởng MONTHS_BETWEEN

`MONTHS_BETWEEN` sử dụng lịch được xác định bởi `NLS_CALENDAR`. Khi kết quả được dùng cho hợp đồng, lãi suất, tuổi hoặc thời hạn, phải thống nhất calendar. Nếu nghiệp vụ Gregorian, đảm bảo session/application dùng Gregorian; không để một connection được đổi sang lịch khác rồi tái sử dụng mà không khôi phục.

## 4. LAST_DAY — tìm ngày cuối tháng

### 4.1. Cú pháp

```sql
LAST_DAY(date)
```

Hàm trả kiểu `DATE`, xác định ngày cuối cùng của tháng chứa `date` theo `NLS_CALENDAR`.

Ví dụ:

```sql
SELECT LAST_DAY(DATE '2024-02-01') AS february_2024,
       LAST_DAY(DATE '2023-02-01') AS february_2023,
       LAST_DAY(DATE '2024-04-15') AS april_2024
FROM dual;
```

| Biểu thức | Kết quả ngày |
|---|---|
| LAST_DAY(01/02/2024) | 29/02/2024 |
| LAST_DAY(01/02/2023) | 28/02/2023 |
| LAST_DAY(15/04/2024) | 30/04/2024 |

Hàm rất hữu ích cho báo cáo cuối tháng, chốt sổ, thời hạn thanh toán và xác định ranh giới một kỳ.

### 4.2. Kết hợp LAST_DAY và ADD_MONTHS

Tìm ngày cuối tháng kế tiếp:

```sql
SELECT LAST_DAY(ADD_MONTHS(DATE '2024-02-10', 1))
       AS next_month_end
FROM dual;
```

Tìm ngày đầu tháng kế tiếp có thể dùng:

```sql
SELECT LAST_DAY(DATE '2024-02-10') + 1 AS next_month_start
FROM dual;
```

Nếu cần tạo dãy kỳ tháng từ một ngày gốc, hãy xác định có muốn “ngày cố định” hay “ngày cuối tháng”. Ví dụ:

```sql
SELECT ADD_MONTHS(DATE '2024-01-15', 1) AS fixed_day_rule,
       LAST_DAY(ADD_MONTHS(DATE '2024-01-15', 1)) AS month_end_rule
FROM dual;
```

Kết quả là 15/02 và 29/02. Hai chính sách khác nhau dù cùng bắt đầu từ một ngày.

### 4.3. Tìm khoảng thời gian của một tháng

Một cách phổ biến để lọc toàn bộ bản ghi trong tháng là xác định:

- đầu tháng (inclusive);
- đầu tháng kế tiếp (exclusive).

Ví dụ với cột `created_at DATE`:

```sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= DATE '2024-02-01'
  AND created_at <  DATE '2024-03-01';
```

Điều kiện này bao gồm mọi thời điểm trong ngày 29/02/2024, kể cả 23:59:59. Nó tránh phải đoán giá trị “cuối ngày” như `23:59:59` hoặc làm mất phần giây nếu cột là TIMESTAMP.

Tính ranh giới động:

```sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= TRUNC(:month_date, 'MM')
  AND created_at <  ADD_MONTHS(TRUNC(:month_date, 'MM'), 1);
```

`TRUNC(date, 'MM')` đưa ngày về đầu tháng theo lịch Gregorian của hàm TRUNC; `ADD_MONTHS` chịu ảnh hưởng `NLS_CALENDAR`. Với hệ thống chạy calendar không phải Gregorian, cần chọn quy tắc lịch nhất quán thay vì ghép hai hàm một cách mặc định. Trong hệ thống nghiệp vụ Gregorian, giữ `NLS_CALENDAR='GREGORIAN'` là lựa chọn dễ kiểm soát.

### 4.4. LAST_DAY và điều kiện WHERE

Có thể viết:

```sql
WHERE LAST_DAY(created_at) = DATE '2024-02-29'
```

nhưng hàm đang bọc cột `created_at`. B-tree index thông thường trên cột có thể không được sử dụng cho phép so sánh theo cách mong muốn. Viết theo range thường thân thiện hơn với index:

```sql
WHERE created_at >= DATE '2024-02-01'
  AND created_at <  DATE '2024-03-01'
```

Nếu nghiệp vụ thật sự cần truy vấn theo biểu thức `LAST_DAY(created_at)` lặp lại thường xuyên, có thể đánh giá function-based index, nhưng phải cân nhắc storage và chi phí DML.

### 4.5. LAST_DAY trả DATE

Giống `ADD_MONTHS`, `LAST_DAY` luôn trả `DATE`. Khi đầu vào là TIMESTAMP hoặc TSTZ, không nên giả định fractional seconds hoặc timezone được giữ nguyên. Nếu cần biểu diễn một mốc thời gian có timezone, hãy chuyển đổi tường minh và lưu theo kiểu phù hợp.

## 5. EXTRACT — lấy một trường từ datetime hoặc interval

### 5.1. Cú pháp

```sql
EXTRACT(field FROM expression)
```

`field` là trường cần lấy; `expression` là biểu thức datetime hoặc interval phù hợp. Các trường datetime thường gặp:

- `YEAR`, `MONTH`, `DAY`.
- `HOUR`, `MINUTE`, `SECOND`.
- `TIMEZONE_HOUR`, `TIMEZONE_MINUTE`.
- `TIMEZONE_REGION`, `TIMEZONE_ABBR` trong ngữ cảnh timestamp có timezone phù hợp.

Ví dụ:

```sql
SELECT EXTRACT(YEAR FROM DATE '2024-02-29') AS event_year,
       EXTRACT(MONTH FROM DATE '2024-02-29') AS event_month,
       EXTRACT(DAY FROM DATE '2024-02-29') AS event_day
FROM dual;
```

Kết quả là năm 2024, tháng 2 và ngày 29.

### 5.2. EXTRACT với DATE và TIMESTAMP

Oracle xử lý `DATE` theo ngữ nghĩa ANSI DATE trong `EXTRACT`, vì vậy các trường hợp hợp lệ là `YEAR`, `MONTH` và `DAY`. Nếu cần lấy giờ/phút/giây từ một cột DATE, hãy chuyển rõ sang TIMESTAMP:

```sql
SELECT EXTRACT(HOUR FROM CAST(
           TO_DATE('2024-02-29 14:35:42', 'YYYY-MM-DD HH24:MI:SS')
           AS TIMESTAMP
       )) AS hour_part,
       EXTRACT(MINUTE FROM CAST(
           TO_DATE('2024-02-29 14:35:42', 'YYYY-MM-DD HH24:MI:SS')
           AS TIMESTAMP
       )) AS minute_part,
       EXTRACT(SECOND FROM CAST(
           TO_DATE('2024-02-29 14:35:42', 'YYYY-MM-DD HH24:MI:SS')
           AS TIMESTAMP
       )) AS second_part
FROM dual;
```

Với TIMESTAMP:

```sql
SELECT EXTRACT(YEAR FROM created_ts) AS event_year,
       EXTRACT(MONTH FROM created_ts) AS event_month,
       EXTRACT(DAY FROM created_ts) AS event_day,
       EXTRACT(HOUR FROM created_ts) AS event_hour,
       EXTRACT(MINUTE FROM created_ts) AS event_minute,
       EXTRACT(SECOND FROM created_ts) AS event_second
FROM event_log;
```

`EXTRACT(SECOND ...)` có thể bao gồm phần thập phân của giây theo độ chính xác timestamp.

### 5.3. EXTRACT với TIMESTAMP WITH TIME ZONE

Đối với TSTZ, có thể lấy trường timezone:

```sql
WITH sample_data AS (
    SELECT TO_TIMESTAMP_TZ(
               '2024-07-01 08:30:15 America/New_York',
               'YYYY-MM-DD HH24:MI:SS TZR'
           ) AS event_ts
    FROM dual
)
SELECT EXTRACT(TIMEZONE_HOUR FROM event_ts) AS tz_hour,
       EXTRACT(TIMEZONE_MINUTE FROM event_ts) AS tz_minute,
       EXTRACT(TIMEZONE_REGION FROM event_ts) AS tz_region,
       EXTRACT(TIMEZONE_ABBR FROM event_ts) AS tz_abbr
FROM sample_data;
```

Với ví dụ ngày tháng 7 ở New York, offset là UTC−04:00 và abbreviation là EDT theo quy tắc timezone data đang dùng. Nếu timestamp chỉ được tạo từ offset số `-04:00` mà không có region, Oracle có thể không xác định được một tên region cụ thể; `TIMEZONE_REGION` có thể trả `UNKNOWN`.

Một điểm quan trọng: khi `EXTRACT` lấy các trường lịch như YEAR/MONTH/DAY/HOUR từ một giá trị **TIMESTAMP WITH TIME ZONE**, Oracle diễn giải giá trị datetime theo UTC. Nếu cần hiển thị thành phần giờ địa phương của một region, hãy chuyển sang region trước rồi định dạng/ép về TIMESTAMP không timezone một cách tường minh:

```sql
WITH sample_data AS (
    SELECT TO_TIMESTAMP_TZ(
               '2024-07-01 08:30:15 America/New_York',
               'YYYY-MM-DD HH24:MI:SS TZR'
           ) AS event_ts
    FROM dual
),
local_value AS (
    SELECT CAST(
               event_ts AT TIME ZONE 'America/New_York'
               AS TIMESTAMP
           ) AS ny_local_ts
    FROM sample_data
)
SELECT EXTRACT(YEAR FROM ny_local_ts) AS local_year,
       EXTRACT(MONTH FROM ny_local_ts) AS local_month,
       EXTRACT(DAY FROM ny_local_ts) AS local_day,
       EXTRACT(HOUR FROM ny_local_ts) AS local_hour
FROM local_value;
```

`AT TIME ZONE` đổi cách biểu diễn cùng một instant sang vùng được chỉ định; `CAST(... AS TIMESTAMP)` bỏ phần timezone sau khi đã chọn vùng địa phương để lấy các thành phần lịch. Nếu chỉ cần hiển thị, `TO_CHAR(event_ts AT TIME ZONE region, format)` thường trực tiếp và dễ đọc hơn.

### 5.4. EXTRACT với INTERVAL

`EXTRACT` còn lấy trường từ interval:

```sql
SELECT EXTRACT(YEAR FROM INTERVAL '2-3' YEAR TO MONTH) AS years_part,
       EXTRACT(MONTH FROM INTERVAL '2-3' YEAR TO MONTH) AS months_part,
       EXTRACT(DAY FROM INTERVAL '5 04:30:15' DAY TO SECOND) AS days_part,
       EXTRACT(HOUR FROM INTERVAL '5 04:30:15' DAY TO SECOND) AS hours_part,
       EXTRACT(MINUTE FROM INTERVAL '5 04:30:15' DAY TO SECOND) AS minutes_part,
       EXTRACT(SECOND FROM INTERVAL '5 04:30:15' DAY TO SECOND) AS seconds_part
FROM dual;
```

`INTERVAL '2-3' YEAR TO MONTH` biểu diễn 2 năm 3 tháng. `INTERVAL '5 04:30:15' DAY TO SECOND` biểu diễn 5 ngày 4 giờ 30 phút 15 giây.

Khi trích trường từ interval, kết quả là **thành phần trong đơn vị tương ứng**, không phải tổng duration đã đổi về một đơn vị lớn hơn. Ví dụ interval 5 ngày 4 giờ có `EXTRACT(HOUR ...)` bằng 4, không phải 124. Nếu cần tổng số giờ, phải cộng thành phần ngày nhân 24 với giờ và các phần nhỏ hơn.

### 5.5. EXTRACT không thay thế TO_CHAR

`EXTRACT` trả một trường dữ liệu để tính toán/so sánh; `TO_CHAR` chuyển datetime thành chuỗi theo format mask. Ví dụ:

```sql
SELECT EXTRACT(MONTH FROM DATE '2024-02-29') AS month_number,
       TO_CHAR(DATE '2024-02-29', 'MON') AS month_label
FROM dual;
```

`MONTH_NUMBER` là số 2; `MONTH_LABEL` là chuỗi tên tháng theo ngôn ngữ định dạng hiện hành hoặc format model được chỉ định. Khi cần nhãn tháng tiếng Việt/Anh, kiểm soát `NLS_DATE_LANGUAGE` thay vì phụ thuộc mặc định của session.

## 6. NLS_CALENDAR và các hàm tháng

Ba hàm `ADD_MONTHS`, `MONTHS_BETWEEN` và `LAST_DAY` sử dụng quy tắc lịch được xác định bởi tham số session `NLS_CALENDAR`. Trong khi đó, `EXTRACT` áp dụng ngữ nghĩa lịch Gregorian cho các trường datetime; không nên cho rằng đổi `NLS_CALENDAR` làm thay đổi ý nghĩa trường được trích.

Kiểm tra:

```sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_CALENDAR',
    'NLS_DATE_FORMAT',
    'NLS_DATE_LANGUAGE'
)
ORDER BY parameter;
```

Nếu nghiệp vụ dùng lịch Gregorian:

```sql
ALTER SESSION SET NLS_CALENDAR = 'GREGORIAN';
```

Tham số session ảnh hưởng các câu lệnh tiếp theo trong session hiện tại. Trong connection pool, thay đổi bằng `ALTER SESSION` có thể tồn tại khi connection được trả về pool; cần đặt lại hoặc khởi tạo session theo chính sách nhất quán.

### 6.1. NLS_DATE_FORMAT không thay đổi giá trị DATE

Ví dụ:

```sql
ALTER SESSION SET NLS_DATE_FORMAT = 'DD-MON-YYYY';
SELECT DATE '2024-02-29' AS date_value FROM dual;

ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY/MM/DD';
SELECT DATE '2024-02-29' AS date_value FROM dual;
```

Hai câu truy vấn trả cùng một giá trị DATE; chỉ cách hiển thị mặc định thay đổi. Để định dạng rõ trong báo cáo:

```sql
SELECT TO_CHAR(
           DATE '2024-02-29',
           'YYYY-MM-DD',
           'NLS_DATE_LANGUAGE=American'
       ) AS iso_date
FROM dual;
```

`NLS_DATE_FORMAT` không phải timezone, và `NLS_DATE_LANGUAGE` không phải lịch tháng. Đừng dùng một tham số NLS để giải quyết vấn đề thuộc một khái niệm khác.

## 7. Kết hợp bốn hàm trong bài toán nghiệp vụ

### 7.1. Tính kỳ thanh toán hàng tháng

Giả sử hợp đồng bắt đầu ngày 31/01/2024 và quy định **ngày đến hạn là ngày cuối tháng**:

```sql
WITH months AS (
    SELECT LEVEL AS month_no
    FROM dual
    CONNECT BY LEVEL <= 6
)
SELECT month_no,
       LAST_DAY(
           ADD_MONTHS(DATE '2024-01-31', month_no - 1)
       ) AS due_date
FROM months
ORDER BY month_no;
```

Kết quả ngày đến hạn lần lượt là 31/01, 29/02, 31/03, 30/04, 31/05 và 30/06/2024. Câu SQL thể hiện rõ quy tắc “cuối tháng” cho từng kỳ.

Nếu quy định hợp đồng là “ngày 30 hàng tháng nếu có, nếu không thì ngày cuối tháng”, logic cần được định nghĩa riêng. Không suy ra quy tắc đó chỉ từ `ADD_MONTHS`.

### 7.2. Tính tháng thâm niên

Giả sử cần báo cáo số tháng giữa ngày vào làm và ngày hiện tại:

```sql
SELECT employee_id,
       hire_date,
       MONTHS_BETWEEN(TRUNC(SYSDATE), hire_date) AS months_worked
FROM employees;
```

Giá trị có thể là số thập phân. Nếu báo cáo chỉ cần số tháng nguyên theo chính sách nhân sự, cần quyết định cách làm tròn:

```sql
SELECT employee_id,
       FLOOR(
           MONTHS_BETWEEN(TRUNC(SYSDATE), hire_date)
       ) AS completed_months
FROM employees;
```

`FLOOR` là ví dụ chính sách lấy phần tháng hoàn thành theo giá trị hàm. Với quyền lợi nhân sự hoặc lãi suất, cần kiểm tra định nghĩa nghiệp vụ, đặc biệt trường hợp ngày cuối tháng và thời điểm trong ngày. Không coi `MONTHS_BETWEEN` là bộ tính tuổi hoặc thời hạn hợp đồng phù hợp cho mọi quy định.

### 7.3. Báo cáo theo tháng và EXTRACT

Lấy năm/tháng để nhóm:

```sql
SELECT EXTRACT(YEAR FROM created_at) AS order_year,
       EXTRACT(MONTH FROM created_at) AS order_month,
       COUNT(*) AS order_count,
       SUM(order_amount) AS total_amount
FROM orders
GROUP BY EXTRACT(YEAR FROM created_at),
         EXTRACT(MONTH FROM created_at)
ORDER BY order_year, order_month;
```

Đây là cách dễ hiểu nhưng có thể phải tính biểu thức trên nhiều hàng. Với bảng lớn, nên cân nhắc cột ngày được chuẩn hóa, partition theo thời gian hoặc cách nhóm phù hợp với workload và index. Nếu cột là TSTZ, cần xác định báo cáo nhóm theo UTC hay theo một region nghiệp vụ trước khi trích YEAR/MONTH.

### 7.4. Xác định cuối tháng bằng EXTRACT và LAST_DAY

Có thể so sánh một ngày với kết quả `LAST_DAY`:

```sql
SELECT invoice_id,
       invoice_date,
       CASE
           WHEN TRUNC(invoice_date) = TRUNC(LAST_DAY(invoice_date))
           THEN 'MONTH_END'
           ELSE 'NOT_MONTH_END'
       END AS month_end_flag
FROM invoices;
```

`TRUNC` loại bỏ phần thời gian để so sánh ngày. Nếu chỉ so sánh DATE có cả giờ, một hóa đơn vào 15:00 ngày cuối tháng sẽ khác DATE nửa đêm dù cùng ngày; đó là lý do cần quy định so sánh date-only hay datetime đầy đủ.

## 8. Thiết kế điều kiện lọc thời gian thân thiện với index

### 8.1. Tránh bọc cột trong hàm nếu có thể dùng range

Giả sử có index trên `orders.created_at`. Cách viết:

```sql
SELECT order_id, created_at
FROM orders
WHERE EXTRACT(YEAR FROM created_at) = 2024
  AND EXTRACT(MONTH FROM created_at) = 2;
```

đang áp dụng hàm lên cột. Optimizer có thể không sử dụng B-tree index thông thường theo cách mong muốn. Với khoảng Gregorian tháng 2/2024, có thể viết:

```sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= DATE '2024-02-01'
  AND created_at <  DATE '2024-03-01';
```

Range condition thường dễ tận dụng index hơn và bao phủ cả phần giờ trong ngày cuối tháng.

### 8.2. Tránh so sánh bằng ngày có thành phần giờ không rõ

Nếu cột `created_at` có giá trị `2024-02-29 16:45:00`, điều kiện:

```sql
WHERE created_at = DATE '2024-02-29'
```

không khớp vì literal ở nửa đêm. Nếu cần toàn bộ ngày 29/02:

```sql
WHERE created_at >= DATE '2024-02-29'
  AND created_at <  DATE '2024-03-01'
```

Đây là mẫu half-open range (bao gồm đầu, không bao gồm cuối), tránh tạo mốc `23:59:59` và hoạt động tốt hơn với timestamp có fractional seconds.

### 8.3. Khi nào function-based index phù hợp?

Nếu truy vấn theo một biểu thức cụ thể lặp lại thường xuyên và không thể viết lại thành range hợp lý, có thể đánh giá function-based index:

```sql
CREATE INDEX ix_orders_created_month
ON orders (
    EXTRACT(YEAR FROM created_at),
    EXTRACT(MONTH FROM created_at)
);
```

Sau đó truy vấn cùng biểu thức có thể sử dụng index nếu optimizer thấy có lợi. Cần đánh giá:

- DDL/function expression có hợp lệ với kiểu cột và phiên bản không?
- Statistics của bảng/index có được thu thập phù hợp không?
- Tỷ lệ dữ liệu theo từng tháng có đủ chọn lọc không?
- Chi phí duy trì index khi insert/update có chấp nhận được không?

Không tạo function-based index chỉ vì một truy vấn viết chưa tối ưu. Với báo cáo theo thời gian trên bảng rất lớn, partitioning, range scan hoặc summary/materialized view có thể phù hợp hơn.

## 9. DATE, TIMESTAMP và INTERVAL: chọn phép tính đúng

### 9.1. Cộng số ngày với DATE

Oracle cho phép cộng/trừ số với DATE theo đơn vị ngày:

```sql
SELECT DATE '2024-03-01' + 7 AS after_seven_days,
       DATE '2024-03-01' - 1 AS previous_day
FROM dual;
```

Một ngày tương ứng 1; nửa ngày tương ứng 0.5. Đây là phép toán theo ngày, không phải phép cộng tháng.

### 9.2. INTERVAL cho thời lượng rõ ràng

Với TIMESTAMP, dùng interval:

```sql
SELECT TIMESTAMP '2024-03-01 10:00:00'
           + INTERVAL '2' DAY AS after_two_days,
       TIMESTAMP '2024-03-01 10:00:00'
           + INTERVAL '3' HOUR AS after_three_hours
FROM dual;
```

`INTERVAL YEAR TO MONTH` biểu diễn khoảng năm/tháng, còn `INTERVAL DAY TO SECOND` biểu diễn khoảng ngày/giờ/phút/giây. Không đồng nhất tháng lịch với một số ngày cố định; hãy thử các trường hợp ngày 29/30/31 theo đúng quy tắc nghiệp vụ trước khi chọn phép toán.

### 9.3. EXTRACT interval là thành phần, không phải tổng

Ví dụ thời lượng:

```sql
WITH elapsed AS (
    SELECT TIMESTAMP '2024-03-03 04:30:15'
           - TIMESTAMP '2024-03-01 01:00:00' AS diff
    FROM dual
)
SELECT EXTRACT(DAY FROM diff) AS days_part,
       EXTRACT(HOUR FROM diff) AS hours_part,
       EXTRACT(MINUTE FROM diff) AS minutes_part,
       EXTRACT(SECOND FROM diff) AS seconds_part,
       EXTRACT(DAY FROM diff) * 24
         + EXTRACT(HOUR FROM diff) AS total_hours
FROM elapsed;
```

Kết quả là 2 ngày, 3 giờ, 30 phút, 15 giây; tổng giờ là 51. Nếu chỉ đọc `EXTRACT(HOUR FROM diff)`, bạn nhận 3 chứ không phải 51.

## 10. Xử lý timezone: EXTRACT không thay thế chuyển đổi vùng giờ

Các hàm tháng `ADD_MONTHS`/`LAST_DAY` trả DATE và không giữ timezone. `MONTHS_BETWEEN` tính theo calendar/NLS, không phải duration UTC. Khi làm việc với TSTZ, phải quyết định đang muốn tính theo:

- **Ngày/tháng địa phương** của một region, ví dụ ngày thanh toán tại New York;
- **Instant UTC** trên timeline chung;
- **Ngày/tháng session** theo `SESSIONTIMEZONE`;
- **Calendar nghiệp vụ** do hệ thống quy định.

Ví dụ lấy ngày địa phương New York từ một instant:

```sql
WITH event_data AS (
    SELECT TO_TIMESTAMP_TZ(
               '2024-07-01 12:30:00 +00:00',
               'YYYY-MM-DD HH24:MI:SS TZH:TZM'
           ) AS event_ts
    FROM dual
)
SELECT TO_CHAR(
           event_ts AT TIME ZONE 'America/New_York',
           'YYYY-MM-DD HH24:MI:SS TZR TZH:TZM'
       ) AS new_york_display
FROM event_data;
```

Nếu muốn lọc sự kiện theo tháng địa phương, hãy tính ranh giới đầu tháng và đầu tháng kế tiếp trong region đó, chuyển cả hai sang instant rồi so sánh với cột TSTZ. Không dùng `EXTRACT(MONTH FROM event_ts)` một cách máy móc nếu ý định là tháng địa phương; với TSTZ, các trường lịch của EXTRACT được chuẩn hóa theo UTC.

Với hệ thống có DST, một ngày địa phương có thể dài 23 hoặc 25 giờ. Vì vậy “một ngày lịch” không luôn bằng 24 giờ thực. Dùng timezone region để xác định biên ngày địa phương, sau đó chuyển sang instant; đừng cộng 24 giờ để đại diện cho ngày kế tiếp tại mọi vùng.

## 11. Java/JDBC: bind đúng kiểu dữ liệu

Trong Java, các kiểu `java.time` giúp biểu đạt rõ ngữ nghĩa:

| Java type | Ý nghĩa | Oracle thường dùng |
|---|---|---|
| `LocalDate` | Ngày lịch không có giờ | `DATE` khi quy ước chỉ ngày; chú ý DATE Oracle vẫn có giờ |
| `LocalDateTime` | Ngày giờ không có timezone | `TIMESTAMP` hoặc `DATE` theo độ chính xác |
| `Instant` | Thời điểm tuyệt đối | Có thể chuyển sang UTC TSTZ theo driver/framework |
| `OffsetDateTime` | Ngày giờ cùng offset | `TIMESTAMP WITH TIME ZONE` |
| `ZonedDateTime` | Ngày giờ cùng ZoneId và quy tắc DST | Xử lý ở Java; lưu region riêng nếu cần bảo toàn ZoneId |
| `Duration` | Thời lượng theo giây/nano | `INTERVAL DAY TO SECOND` hoặc số đơn vị đã quy ước |
| `Period` | Khoảng năm/tháng/ngày lịch | Xử lý calendar; không đồng nhất với Duration |

Ví dụ JDBC 4.2 dùng bind parameter:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.time.LocalDate;

public final class BillingRepository {
    public static void insertDueDate(
            Connection connection,
            long invoiceId,
            LocalDate dueDate
    ) throws Exception {
        String sql =
            "INSERT INTO invoice_schedule(invoice_id, due_date) VALUES (?, ?)";

        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, invoiceId);
            ps.setObject(2, dueDate);
            ps.executeUpdate();
        }
    }
}
```

Đoạn ví dụ giả định driver Oracle/JDBC đang dùng hỗ trợ ánh xạ `LocalDate` phù hợp và cột `DUE_DATE` được thiết kế theo quy ước ngày. Với Oracle DATE, nếu cần bảo đảm giờ là nửa đêm, phải kiểm tra cách bind và schema; nếu cột có ngữ nghĩa chỉ ngày, có thể chuẩn hóa ở ứng dụng hoặc constraint.

### 11.1. Không dùng chuỗi để tính ngày trong Java rồi nối SQL

Tránh:

```java
String sql = "SELECT * FROM orders WHERE created_at >= '"
        + userDate + "'";
```

Thay bằng bind parameter có kiểu:

```java
String sql = "SELECT order_id FROM orders WHERE created_at >= ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setObject(1, LocalDate.of(2024, 2, 1));
}
```

Kiểu Java và kiểu Oracle cần được thống nhất trong hợp đồng repository. Với TSTZ, dùng `OffsetDateTime`/API được driver hỗ trợ; không chuyển về `LocalDateTime` rồi hy vọng database tự biết timezone ban đầu.

### 11.2. ADD_MONTHS ở Oracle hay Period ở Java?

Java `LocalDate.plusMonths(1)` và Oracle `ADD_MONTHS(date, 1)` có thể khác nhau ở quy tắc cuối tháng. Ví dụ `LocalDate.of(2024, 1, 31).plusMonths(1)` thường trả 29/02/2024; Oracle cũng trả ngày cuối tháng 2. Nhưng khi lặp nhiều kỳ, cần thống nhất có tính từ ngày gốc hay ngày kỳ trước. Không chia đôi quy tắc tính tháng ở Java và SQL nếu chưa có test chung.

## 12. Những lỗi thường gặp và cách xử lý

| Hiện tượng / lỗi | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Kết quả ADD_MONTHS khác kỳ vọng ở ngày 29/30/31 | Quy tắc ngày cuối tháng hoặc tháng đích ngắn hơn | Kiểm tra ngày gốc, ngày cuối tháng và NLS_CALENDAR |
| Cộng tháng nhiều lần lệch một ngày so với cộng một lần | Kết quả trung gian trở thành ngày cuối tháng | Quy định tính từ ngày gốc hay kỳ trước |
| MONTHS_BETWEEN trả số lẻ bất ngờ | Không cùng ngày trong tháng, không cùng là ngày cuối tháng; cơ sở 31 ngày | Kiểm tra cả ngày và thời gian của hai đối số |
| MONTHS_BETWEEN trả số nguyên dù giờ khác nhau | Hai đối số cùng số ngày trong tháng hoặc đều là ngày cuối tháng | Đây là quy tắc hàm, không phải bỏ sót thời gian |
| LAST_DAY khác kết quả mong đợi | NLS_CALENDAR hoặc hiểu sai lịch Gregorian | Kiểm tra session parameter và yêu cầu lịch |
| EXTRACT(HOUR FROM date_col) lỗi | DATE không hỗ trợ trích HOUR theo ngữ nghĩa ANSI của EXTRACT | CAST DATE sang TIMESTAMP trước |
| EXTRACT trên TSTZ ra tháng/ngày khác giờ địa phương | Trường datetime được chuẩn hóa theo UTC | Chuyển sang region trước khi lấy local calendar fields |
| Điều kiện theo tháng bỏ sót hàng cuối ngày | So sánh bằng DATE ở nửa đêm hoặc dùng end-of-day sai | Dùng range inclusive đầu, exclusive đầu tháng sau |
| Kết quả khác giữa SQL Developer và ứng dụng | NLS/session timezone hoặc kiểu bind khác nhau | Kiểm tra session parameters và JDBC types |
| ADD_MONTHS/LAST_DAY làm mất phần giây lẻ | Hàm trả DATE | Dùng TIMESTAMP/INTERVAL nếu cần fractional seconds |
| Lịch chạy lệch khi DST | Dùng offset cố định hoặc cộng 24 giờ thay ngày lịch | Dùng region timezone và tính biên ngày theo địa phương |
| Index không được dùng khi lọc EXTRACT/LAST_DAY | Hàm bao quanh cột | Viết range predicate hoặc đánh giá function-based index |

### 12.1. ORA-018xx và dữ liệu ngày không hợp lệ

Các lỗi parse/format ngày có thể gặp trong nhóm `ORA-018xx`, ví dụ:

- `ORA-01830`: format model kết thúc trước khi toàn bộ input được chuyển đổi.
- `ORA-01843`: tháng không hợp lệ.
- `ORA-01847`: ngày trong tháng không hợp lệ.
- `ORA-01861`: literal không khớp format string.

Khi gặp lỗi, kiểm tra chuỗi đầu vào, format mask, NLS và kiểu đích. Không sửa bằng cách đổi `NLS_DATE_FORMAT` toàn hệ thống để làm một file nhập liệu chạy được; dùng `TO_DATE`/`TO_TIMESTAMP` với format mask đúng cho nguồn.

## 13. Bài thực hành tổng hợp

Thực hiện trong schema lab riêng. Các câu `CREATE TABLE` và `INSERT` tạo dữ liệu thử; nếu đã có bảng cùng tên, dùng schema sạch hoặc tên khác.

### Bước 1 — Tạo bảng hợp đồng

```sql
CREATE TABLE contract_lab (
    contract_id NUMBER(10) CONSTRAINT pk_contract_lab PRIMARY KEY,
    start_date  DATE NOT NULL,
    term_months NUMBER(3) NOT NULL,
    CONSTRAINT ck_contract_lab_term CHECK (term_months > 0)
);

INSERT INTO contract_lab VALUES (1, DATE '2024-01-31', 6);
INSERT INTO contract_lab VALUES (2, DATE '2024-02-15', 12);
INSERT INTO contract_lab VALUES (3, DATE '2024-02-29', 1);
COMMIT;
```

### Bước 2 — Tính ngày hết hạn theo ADD_MONTHS

```sql
SELECT contract_id,
       start_date,
       term_months,
       ADD_MONTHS(start_date, term_months) AS expiry_date
FROM contract_lab
ORDER BY contract_id;
```

Ghi nhận hợp đồng bắt đầu ngày cuối tháng có thể kết thúc vào ngày cuối tháng tương ứng. Xác định xem đó có đúng chính sách hợp đồng của dự án hay không.

### Bước 3 — Tính ngày cuối tháng

```sql
SELECT contract_id,
       start_date,
       LAST_DAY(start_date) AS start_month_end,
       LAST_DAY(ADD_MONTHS(start_date, term_months)) AS expiry_month_end
FROM contract_lab
ORDER BY contract_id;
```

### Bước 4 — Tính số tháng giữa hai mốc

```sql
SELECT contract_id,
       MONTHS_BETWEEN(
           ADD_MONTHS(start_date, term_months),
           start_date
       ) AS months_between_result
FROM contract_lab
ORDER BY contract_id;
```

So sánh kết quả với `TERM_MONTHS`. Nếu có kết quả không phải số nguyên, phân tích điều kiện cùng ngày trong tháng/ngày cuối tháng.

### Bước 5 — Trích trường ngày tháng

```sql
SELECT contract_id,
       EXTRACT(YEAR FROM start_date) AS start_year,
       EXTRACT(MONTH FROM start_date) AS start_month,
       EXTRACT(DAY FROM start_date) AS start_day
FROM contract_lab
ORDER BY contract_id;
```

Thử lấy HOUR trực tiếp từ DATE để quan sát quy tắc kiểu dữ liệu; sau đó CAST sang TIMESTAMP nếu cần thành phần giờ.

### Bước 6 — Tính khoảng thời gian chính xác

```sql
WITH period_data AS (
    SELECT TIMESTAMP '2024-02-01 08:00:00' AS start_ts,
           TIMESTAMP '2024-03-01 10:30:15' AS end_ts
    FROM dual
)
SELECT end_ts - start_ts AS elapsed_interval,
       EXTRACT(DAY FROM end_ts - start_ts) AS days_part,
       EXTRACT(HOUR FROM end_ts - start_ts) AS hours_part,
       EXTRACT(MINUTE FROM end_ts - start_ts) AS minutes_part,
       EXTRACT(SECOND FROM end_ts - start_ts) AS seconds_part
FROM period_data;
```

Giải thích vì sao đây là duration interval, còn `MONTHS_BETWEEN` là số tháng theo quy tắc calendar của Oracle.

### Bước 7 — Kiểm tra NLS_CALENDAR

```sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter = 'NLS_CALENDAR';
```

Ghi nhận giá trị trong lab. Nếu có quyền và môi trường hỗ trợ lịch khác, DBA có thể tạo một session lab riêng để so sánh; không đổi NLS_CALENDAR của pool production.

### Bước 8 — Tối ưu điều kiện theo tháng

Với bảng có index trên ngày tạo, viết hai truy vấn:

```sql
-- Biểu thức hàm trên cột:
SELECT COUNT(*)
FROM contract_lab
WHERE EXTRACT(YEAR FROM start_date) = 2024
  AND EXTRACT(MONTH FROM start_date) = 2;

-- Range predicate:
SELECT COUNT(*)
FROM contract_lab
WHERE start_date >= DATE '2024-02-01'
  AND start_date <  DATE '2024-03-01';
```

So sánh ý nghĩa và execution plan trên dữ liệu đủ lớn. Hai câu lệnh có thể cho cùng số hàng trong giả định calendar Gregorian, nhưng range predicate thường thuận lợi hơn cho index thường.

## 14. Checklist khi chọn hàm

| Nhu cầu | Hàm nên cân nhắc | Câu hỏi cần xác nhận |
|---|---|---|
| Tính ngày kỳ tiếp theo theo tháng lịch | `ADD_MONTHS` | Có giữ ngày trong tháng hay luôn về cuối tháng? |
| Tính số tháng giữa hai mốc | `MONTHS_BETWEEN` | Có chấp nhận phần thập phân theo cơ sở 31 ngày không? |
| Tìm ngày cuối tháng | `LAST_DAY` | NLS_CALENDAR có đúng lịch nghiệp vụ không? |
| Lấy năm/tháng/ngày/giờ | `EXTRACT` | Đầu vào là DATE, TIMESTAMP, TSTZ hay INTERVAL? |
| Lọc mọi bản ghi trong một tháng | Range predicate với đầu tháng và đầu tháng sau | Cột có index? Cần timezone địa phương hay UTC? |
| Tính thời lượng giờ/phút/giây | Trừ TIMESTAMP và dùng INTERVAL | Cần duration thực hay số tháng lịch? |
| Hiển thị tên tháng/ngày | `TO_CHAR` với format/NLS rõ | Ngôn ngữ hiển thị nào? |
| Lịch theo vùng có DST | TSTZ + timezone region, tính biên theo địa phương | Gap/overlap và quy tắc chuyển vùng ra sao? |

## 15. Câu hỏi tự kiểm tra

1. `ADD_MONTHS` trả về kiểu dữ liệu gì? Nếu truyền TIMESTAMP có fractional seconds thì cần lưu ý gì?
2. Vì sao `ADD_MONTHS(DATE '2024-02-29', 1)` trả ngày cuối tháng 3?
3. Tại sao cộng một tháng hai lần có thể khác cộng hai tháng một lần?
4. `MONTHS_BETWEEN(date1, date2)` có dấu dương/âm theo thứ tự đối số thế nào?
5. Khi nào `MONTHS_BETWEEN` trả số nguyên? Khi nào nó tính phần thập phân dựa trên 31 ngày?
6. Vì sao `MONTHS_BETWEEN` không phù hợp để đo chính xác số giờ hoặc số ngày đã trôi qua?
7. `LAST_DAY` dùng lịch nào và tham số NLS nào ảnh hưởng kết quả?
8. Vì sao lọc `WHERE LAST_DAY(created_at)=...` có thể không tận dụng index thông thường tốt bằng range predicate?
9. Những trường nào có thể trích từ DATE bằng `EXTRACT`? Muốn lấy giờ từ DATE cần làm gì?
10. `EXTRACT` trên TSTZ xử lý các trường datetime theo UTC ra sao? Khi cần giờ địa phương nên làm gì?
11. `EXTRACT(HOUR FROM interval)` có phải tổng số giờ của interval không?
12. `NLS_DATE_FORMAT` khác `NLS_CALENDAR` thế nào?
13. Khi tính một ngày lịch kế tiếp ở vùng có DST, vì sao không nên luôn cộng đúng 24 giờ?
14. Trong Java, `LocalDate`, `LocalDateTime`, `OffsetDateTime` và `Instant` đại diện những khái niệm khác nhau nào?
15. Làm thế nào lọc trọn một tháng mà không bỏ sót fractional seconds ở cuối tháng?

Hãy nhớ cách chọn hàm theo ngữ nghĩa: **`ADD_MONTHS` cho tháng lịch; `MONTHS_BETWEEN` cho khoảng cách tháng theo quy tắc Oracle; `LAST_DAY` cho biên cuối tháng; `EXTRACT` cho một trường của datetime/interval**. Khi viết ứng dụng thật, luôn kiểm tra kiểu dữ liệu, NLS_CALENDAR, timezone, phần thời gian trong ngày và execution plan. Các chi tiết này quyết định phép tính có phản ánh đúng chính sách nghiệp vụ hay không.

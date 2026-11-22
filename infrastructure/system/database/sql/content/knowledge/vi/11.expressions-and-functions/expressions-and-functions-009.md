# Trích xuất thành phần ngày giờ bằng EXTRACT hoặc hàm tương đương

Trong **Database SQL**, dữ liệu thời gian thường chứa nhiều thông tin trong một giá trị: năm, tháng, ngày, giờ, phút, giây và đôi khi cả múi giờ. Khi cần thống kê doanh thu theo tháng, lọc các sự kiện xảy ra vào buổi sáng, tổng hợp đơn hàng theo năm hoặc xác định ngày trong tuần, ta cần **trích xuất một thành phần của giá trị ngày giờ**.

SQL có cú pháp quen thuộc `EXTRACT(field FROM expression)`. Tuy nhiên, không phải mọi hệ quản trị cơ sở dữ liệu (DBMS) hỗ trợ cùng tên trường, kiểu ngày giờ hay cú pháp. PostgreSQL và MySQL/MariaDB có `EXTRACT`; SQL Server thường sử dụng `DATEPART`; SQLite thường dùng `strftime`; Oracle có `EXTRACT` nhưng phân biệt rõ những trường có thể lấy từ `DATE` và `TIMESTAMP`.

Bài học giải thích ý nghĩa các thành phần thời gian, cách dùng `EXTRACT` và hàm tương đương, các vấn đề hay bị bỏ qua như **tuần ISO**, **múi giờ**, **giá trị NULL**, **độ chính xác giây**, cũng như cách lọc dữ liệu theo khoảng ngày để tận dụng chỉ mục.

## 1. Giá trị ngày giờ và thành phần được trích xuất

Một giá trị như:

```text
2026-04-05 14:27:36.250
YYYY-MM-DD HH:mm:ss.fff
```

có các thành phần:

| Thành phần | Giá trị ví dụ | Ý nghĩa |
| --- | ---: | --- |
| `YEAR` | 2026 | Năm |
| `MONTH` | 4 | Tháng, thường từ 1 đến 12 |
| `DAY` | 5 | Ngày trong tháng, thường từ 1 đến 28/29/30/31 |
| `HOUR` | 14 | Giờ trong ngày của thời điểm biểu diễn, thường 0–23 |
| `MINUTE` | 27 | Phút trong giờ, thường 0–59 |
| `SECOND` | 36.250 | Giây trong phút, có thể bao gồm phần thập phân |

Cần phân biệt **trích xuất thành phần** và **định dạng văn bản**:

- Trích xuất tháng từ `2026-04-05` cho giá trị số `4`, phù hợp để phân nhóm hoặc so sánh.
- Định dạng tháng thành `'04'` cho chuỗi văn bản có số 0 phía trước, phù hợp hiển thị.
- Trích xuất ngày bằng `DAY` cho số `5`, **không phải** giá trị ngày đầy đủ `2026-04-05`.
- Trích xuất giờ cho số `14`, **không phải** một giá trị `TIME` hoàn chỉnh.

Mọi ví dụ về giờ cần hiểu trong bối cảnh **kiểu dữ liệu và múi giờ** đang dùng. Cùng một thời điểm tuyệt đối có thể có giờ/ngày khác nhau khi biểu diễn theo UTC và theo Việt Nam.

## 2. DATE, TIME, TIMESTAMP và TIMESTAMP WITH TIME ZONE

Trước khi dùng `EXTRACT`, cần biết kiểu của biểu thức đầu vào.

| Kiểu khái niệm | Lưu/biểu diễn gì? | Những thành phần thường có ý nghĩa |
| --- | --- | --- |
| `DATE` | Một ngày lịch | Năm, tháng, ngày |
| `TIME` | Một giờ trong ngày | Giờ, phút, giây |
| `TIMESTAMP` hoặc `DATETIME` không kèm múi giờ | Ngày và giờ địa phương/giờ quy ước, chưa tự nói lên múi giờ | Năm, tháng, ngày, giờ, phút, giây |
| `TIMESTAMP WITH TIME ZONE` hoặc kiểu mang thông tin offset/instant | Thời điểm có ngữ nghĩa múi giờ hoặc độ lệch; cách lưu tùy DBMS | Các thành phần của **cách biểu diễn thời điểm theo một múi giờ** |
| `INTERVAL` hoặc khoảng thời gian | Một độ dài/khoảng cách giữa các thời điểm | Ngày, giờ, phút, giây; đôi khi năm, tháng tùy loại interval |

Tên và chi tiết kiểu dữ liệu khác nhau giữa hệ quản trị. Ví dụ, trong **PostgreSQL**, `TIMESTAMP` không kèm múi giờ là một ngày giờ “naive”; `TIMESTAMPTZ` biểu diễn một instant và được hiển thị theo múi giờ của phiên làm việc. Trong **MySQL**, `TIMESTAMP` và `DATETIME` có khác biệt về chuyển đổi múi giờ; trong **SQL Server**, `DATETIMEOFFSET` chứa thông tin offset; trong **SQLite**, giá trị thời gian thường được lưu qua TEXT, REAL hoặc INTEGER cùng quy ước định dạng.

Không suy diễn rằng **mọi cột tên `created_at` đều được lưu theo UTC**. Hãy xem kiểu cột, cấu hình kết nối và chính sách ứng dụng.

### Một giá trị DATE không tự chứa giờ

Trong PostgreSQL:

```sql
SELECT EXTRACT(YEAR FROM DATE '2026-04-05') AS year_value,
       EXTRACT(MONTH FROM DATE '2026-04-05') AS month_value,
       EXTRACT(DAY FROM DATE '2026-04-05') AS day_value;
```

Kết quả là `2026`, `4`, `5`. Nếu muốn trích xuất **giờ trong ngày**, dùng một biểu thức kiểu `TIME` hoặc `TIMESTAMP` phù hợp:

```sql
SELECT EXTRACT(HOUR FROM TIME '14:27:36.250') AS hour_value,
       EXTRACT(MINUTE FROM TIME '14:27:36.250') AS minute_value,
       EXTRACT(SECOND FROM TIME '14:27:36.250') AS second_value;
```

Trên PostgreSQL, `SECOND` trong ví dụ có thể là `36.250000` hoặc hiển thị số thập phân tương đương tùy client. **Phần lẻ của giây có thể được giữ lại**; đừng mặc nhiên ép `SECOND` về số nguyên nếu bài toán cần phần mili giây/vi giây.

## 3. Cú pháp EXTRACT trong SQL

Dạng tổng quát:

```sql
EXTRACT(field FROM datetime_expression)
```

Trong đó:

- `field` là **tên thành phần ngày giờ** được DBMS nhận biết, ví dụ `YEAR`, `MONTH`, `DAY`, `HOUR`, `MINUTE`, `SECOND`.
- `datetime_expression` là biểu thức ngày giờ hoặc khoảng thời gian hợp lệ.
- Kết quả thường là **giá trị số**, nhưng kiểu chính xác và số chữ số thập phân tùy DBMS, trường trích xuất và kiểu đầu vào.

Các ví dụ **PostgreSQL** sau có thể chạy độc lập:

```sql
SELECT
    EXTRACT(YEAR   FROM TIMESTAMP '2026-04-05 14:27:36.250') AS year_value,
    EXTRACT(MONTH  FROM TIMESTAMP '2026-04-05 14:27:36.250') AS month_value,
    EXTRACT(DAY    FROM TIMESTAMP '2026-04-05 14:27:36.250') AS day_value,
    EXTRACT(HOUR   FROM TIMESTAMP '2026-04-05 14:27:36.250') AS hour_value,
    EXTRACT(MINUTE FROM TIMESTAMP '2026-04-05 14:27:36.250') AS minute_value,
    EXTRACT(SECOND FROM TIMESTAMP '2026-04-05 14:27:36.250') AS second_value;
```

Kết quả theo thứ tự là năm `2026`, tháng `4`, ngày `5`, giờ `14`, phút `27`, giây `36.250`.

Trong câu `SELECT`, nên đặt alias rõ nghĩa:

```sql
SELECT
    order_id,
    created_at,
    EXTRACT(YEAR FROM created_at) AS order_year,
    EXTRACT(MONTH FROM created_at) AS order_month
FROM orders;
```

Tên `order_year` chỉ là tên **cột kết quả**, không tạo cột mới trong bảng và không làm thay đổi dữ liệu `created_at`.

### EXTRACT trả thành phần, không làm tròn về đầu ngày/tháng

Giả sử:

```sql
SELECT
    EXTRACT(MONTH FROM TIMESTAMP '2026-04-05 14:27:36') AS month_number,
    DATE_TRUNC('month', TIMESTAMP '2026-04-05 14:27:36') AS month_start;
```

Trong PostgreSQL:

- `EXTRACT(MONTH ...)` trả số `4`.
- `DATE_TRUNC('month', ...)` trả một **giá trị ngày giờ ở đầu tháng**, ở đây `2026-04-01 00:00:00`.

Đây là hai thao tác khác nhau. `EXTRACT` phù hợp để lấy một trường; `DATE_TRUNC` phù hợp khi cần một **mốc thời gian đại diện cho nhóm** ở một độ hạt nhất định.

## 4. Các thành phần ít hiển nhiên: quý, tuần và ngày trong tuần

Một số hệ hỗ trợ trích xuất thêm:

| Thành phần | Ý nghĩa điển hình | Lưu ý |
| --- | --- | --- |
| `QUARTER` | Quý 1–4 | Không phải DBMS nào hỗ trợ trực tiếp trong `EXTRACT` |
| `WEEK` | Số tuần trong năm | Phải xác định quy ước bắt đầu tuần và tuần đầu năm |
| `DOW` | Ngày trong tuần | Quy ước số khác nhau giữa các DBMS |
| `ISODOW` | Ngày ISO trong tuần | ISO thường quy ước thứ Hai = 1, Chủ nhật = 7 |
| `ISOYEAR` | Năm ISO của tuần | Có thể khác năm lịch `YEAR` ở ranh giới năm |
| `DOY` | Thứ tự ngày trong năm | Có thể là 1–365 hoặc 1–366 |
| `EPOCH` | Số giây tương ứng epoch hoặc tổng số giây của interval | Ý nghĩa phụ thuộc loại biểu thức |

Trong **PostgreSQL**:

```sql
SELECT
    EXTRACT(QUARTER FROM DATE '2026-04-05') AS quarter_value,
    EXTRACT(DOY FROM DATE '2026-04-05') AS day_of_year,
    EXTRACT(DOW FROM DATE '2026-04-05') AS day_of_week,
    EXTRACT(ISODOW FROM DATE '2026-04-05') AS iso_day_of_week,
    EXTRACT(WEEK FROM DATE '2026-04-05') AS iso_week_number,
    EXTRACT(ISOYEAR FROM DATE '2026-04-05') AS iso_week_year;
```

**PostgreSQL `DOW`** trả Chủ nhật = 0, thứ Hai = 1, ..., thứ Bảy = 6. Trong khi đó **`ISODOW`** trả thứ Hai = 1, ..., Chủ nhật = 7. Hai quy ước không thể dùng lẫn nếu xây dựng lịch hoặc báo cáo theo tuần.

### Tuần ISO có thể thuộc năm khác năm lịch

Ngày **01/01/2021** là thứ Sáu, thuộc **tuần ISO 53 của năm ISO 2020**:

```sql
-- PostgreSQL:
SELECT
    EXTRACT(YEAR FROM DATE '2021-01-01') AS calendar_year,
    EXTRACT(ISOYEAR FROM DATE '2021-01-01') AS iso_year,
    EXTRACT(WEEK FROM DATE '2021-01-01') AS iso_week;
```

Kết quả:

| `calendar_year` | `iso_year` | `iso_week` |
| ---: | ---: | ---: |
| 2021 | 2020 | 53 |

Nếu làm báo cáo tuần bằng `EXTRACT(YEAR ...)` kết hợp `EXTRACT(WEEK ...)` trong PostgreSQL, nhóm tuần ở ranh giới năm có thể bị **gắn sai năm**. Khi dùng tuần ISO, hãy nhóm theo **`ISOYEAR` + `WEEK`**.

**Không áp dụng trực tiếp quy ước này cho mọi DBMS.** MySQL có nhiều chế độ đánh số tuần, SQL Server có `WEEK` và `ISO_WEEK` với quy tắc khác nhau, SQLite và Oracle có cơ chế định dạng/tham số riêng. Trước khi so sánh báo cáo giữa các hệ, cần ghi chính xác **tuần bắt đầu ngày nào** và **năm của tuần được xác định ra sao**.

## 5. DATEPART và các hàm tương đương trong các DBMS

Cùng một yêu cầu “lấy tháng từ ngày lập đơn hàng” có thể được viết theo các dialect khác nhau.

| Hệ quản trị | Lấy năm | Lấy tháng | Lấy ngày | Lấy giờ |
| --- | --- | --- | --- | --- |
| **PostgreSQL** | `EXTRACT(YEAR FROM ts)` | `EXTRACT(MONTH FROM ts)` | `EXTRACT(DAY FROM ts)` | `EXTRACT(HOUR FROM ts)` |
| **MySQL / MariaDB** | `YEAR(ts)` hoặc `EXTRACT(YEAR FROM ts)` | `MONTH(ts)` | `DAYOFMONTH(ts)` | `HOUR(ts)` |
| **SQL Server** | `YEAR(ts)` hoặc `DATEPART(year, ts)` | `MONTH(ts)` | `DAY(ts)` | `DATEPART(hour, ts)` |
| **SQLite** | `CAST(strftime('%Y', ts) AS INTEGER)` | `CAST(strftime('%m', ts) AS INTEGER)` | `CAST(strftime('%d', ts) AS INTEGER)` | `CAST(strftime('%H', ts) AS INTEGER)` |
| **Oracle Database** | `EXTRACT(YEAR FROM dt)` | `EXTRACT(MONTH FROM dt)` | `EXTRACT(DAY FROM dt)` | `EXTRACT(HOUR FROM CAST(dt AS TIMESTAMP))` |

Ở bảng trên, `ts` là một biểu thức ngày giờ hợp lệ trong hệ đang dùng; `dt` là biểu thức kiểu `DATE` hoặc kiểu phù hợp. Tên hàm không đủ để quyết định có thể chạy mọi ví dụ trên tất cả phiên bản hoặc mọi kiểu cột.

### PostgreSQL

PostgreSQL hỗ trợ `EXTRACT` theo cú pháp quen thuộc, đồng thời có hàm `date_part`:

```sql
SELECT
    EXTRACT(YEAR FROM TIMESTAMP '2026-04-05 14:27:36') AS year_value,
    DATE_PART('month', TIMESTAMP '2026-04-05 14:27:36') AS month_value;
```

Lưu ý: kiểu kết quả của `EXTRACT` và `date_part` có thể khác nhau (trên PostgreSQL hiện đại `EXTRACT` thường trả `numeric`, còn `date_part` trả `double precision`). Khi trích xuất để làm nhãn hoặc giao tiếp với ứng dụng, có thể `CAST` về kiểu số phù hợp nếu cần; không ép mất phần lẻ của giây.

### MySQL và MariaDB

Hai hệ hỗ trợ `YEAR()`, `MONTH()`, `DAYOFMONTH()`, `HOUR()`, `MINUTE()`, `SECOND()` và cú pháp `EXTRACT` cho nhiều thành phần:

```sql
-- MySQL / MariaDB:
SELECT
    YEAR('2026-04-05 14:27:36') AS year_value,
    MONTH('2026-04-05 14:27:36') AS month_value,
    DAYOFMONTH('2026-04-05 14:27:36') AS day_value,
    HOUR('2026-04-05 14:27:36') AS hour_value,
    MINUTE('2026-04-05 14:27:36') AS minute_value,
    SECOND('2026-04-05 14:27:36') AS second_value;

SELECT EXTRACT(YEAR FROM '2026-04-05 14:27:36') AS extracted_year;
```

Trong ứng dụng thật, nên dùng cột kiểu ngày giờ hoặc giá trị được bind đúng kiểu thay vì phụ thuộc vào khả năng chuyển đổi tự động của chuỗi. Khi lấy **microsecond**, MySQL/MariaDB có hàm `MICROSECOND()`. Đừng mặc nhiên suy luận `SECOND()` phải mang phần thập phân như `EXTRACT(SECOND FROM ...)` trên PostgreSQL.

**Ngày trong tuần:** MySQL `DAYOFWEEK()` dùng Chủ nhật = 1, thứ Bảy = 7; `WEEKDAY()` dùng thứ Hai = 0, Chủ nhật = 6. Đây là hai cách đánh số khác nhau trong cùng một DBMS. Hàm `WEEK()` còn chịu ảnh hưởng chế độ tuần; nếu báo cáo dùng tuần ISO, phải chọn cách tính phù hợp và đi kèm năm tuần đúng.

### SQL Server

T-SQL dùng `DATEPART(part, expression)` để trả về một giá trị nguyên của thành phần thời gian:

```sql
-- SQL Server:
SELECT
    DATEPART(year, CAST('2026-04-05T14:27:36' AS datetime2)) AS year_value,
    DATEPART(month, CAST('2026-04-05T14:27:36' AS datetime2)) AS month_value,
    DATEPART(day, CAST('2026-04-05T14:27:36' AS datetime2)) AS day_value,
    DATEPART(hour, CAST('2026-04-05T14:27:36' AS datetime2)) AS hour_value,
    DATEPART(minute, CAST('2026-04-05T14:27:36' AS datetime2)) AS minute_value,
    DATEPART(second, CAST('2026-04-05T14:27:36' AS datetime2)) AS second_value;
```

T-SQL còn có các hàm thuận tiện:

```sql
-- SQL Server:
SELECT
    YEAR(CAST('2026-04-05' AS date)) AS year_value,
    MONTH(CAST('2026-04-05' AS date)) AS month_value,
    DAY(CAST('2026-04-05' AS date)) AS day_value;
```

Với `DATEPART(weekday, ...)`, số trả về phụ thuộc `SET DATEFIRST`. Để biết cài đặt của phiên SQL Server:

```sql
SELECT @@DATEFIRST AS first_day_of_week;
```

SQL Server có `DATEPART(iso_week, ...)` để lấy tuần ISO. Khi cần **năm ISO**, không giả định có trường `iso_year` tương đương PostgreSQL; hãy thiết kế phép tính/cột lịch theo đúng quy tắc ISO và kiểm tra ngày giáp năm.

### SQLite

SQLite không có một kiểu ngày giờ lưu trữ chuyên biệt bắt buộc cho mọi cột như một số DBMS server. Các hàm ngày giờ có thể làm việc với **time-value** hợp lệ, chẳng hạn chuỗi ISO-8601, Julian day hoặc Unix timestamp khi có modifier phù hợp.

`strftime(format, time-value, ...)` thường trả **văn bản (TEXT)**:

```sql
-- SQLite:
SELECT
    strftime('%Y', '2026-04-05 14:27:36') AS year_text,
    strftime('%m', '2026-04-05 14:27:36') AS month_text,
    strftime('%d', '2026-04-05 14:27:36') AS day_text,
    strftime('%H', '2026-04-05 14:27:36') AS hour_text,
    strftime('%M', '2026-04-05 14:27:36') AS minute_text,
    strftime('%S', '2026-04-05 14:27:36') AS second_text;
```

Kết quả văn bản có thể là `'2026'`, `'04'`, `'05'`, `'14'`, `'27'`, `'36'`. Nếu cần kiểu số để so sánh/tính toán, ép kiểu rõ ràng:

```sql
SELECT
    CAST(strftime('%Y', '2026-04-05 14:27:36') AS INTEGER) AS year_number,
    CAST(strftime('%m', '2026-04-05 14:27:36') AS INTEGER) AS month_number;
```

`strftime('%w', value)` trong SQLite cho ngày trong tuần với Chủ nhật = 0, thứ Bảy = 6. Với dữ liệu lưu dạng **Unix timestamp số nguyên**, phải dùng modifier như `'unixepoch'` đúng theo quy ước lưu trữ:

```sql
-- SQLite: chỉ dùng 'unixepoch' nếu cột chứa số giây Unix hợp lệ.
SELECT strftime('%Y', 1712327256, 'unixepoch') AS year_from_epoch;
```

Không truyền bừa Unix timestamp theo **mili giây** vào hàm mong **giây**. Nếu giá trị của SQLite không được phân tích thành ngày hợp lệ, hàm ngày giờ có thể trả `NULL`.

### Oracle Database

Oracle hỗ trợ `EXTRACT` với các trường như `YEAR`, `MONTH`, `DAY` từ `DATE`:

```sql
-- Oracle Database:
SELECT
    EXTRACT(YEAR FROM DATE '2026-04-05') AS year_value,
    EXTRACT(MONTH FROM DATE '2026-04-05') AS month_value,
    EXTRACT(DAY FROM DATE '2026-04-05') AS day_value
FROM DUAL;
```

**Điểm dễ nhầm:** dù `DATE` của Oracle lưu cả thành phần giờ/phút/giây, `EXTRACT` xử lý kiểu `DATE` như **ANSI DATE** khi xét các trường được phép; `EXTRACT(HOUR FROM date_column)` không phải cách đúng để lấy giờ từ cột Oracle `DATE`. Hãy ép sang `TIMESTAMP` trước:

```sql
-- Oracle Database:
SELECT
    EXTRACT(HOUR FROM CAST(SYSDATE AS TIMESTAMP)) AS hour_value,
    EXTRACT(MINUTE FROM CAST(SYSDATE AS TIMESTAMP)) AS minute_value
FROM DUAL;
```

Hoặc dùng `TO_CHAR` để định dạng trường thời gian:

```sql
-- Oracle: TO_CHAR trả văn bản; có thể TO_NUMBER nếu cần số.
SELECT
    TO_CHAR(SYSDATE, 'HH24') AS hour_text,
    TO_CHAR(SYSDATE, 'MI') AS minute_text,
    TO_CHAR(SYSDATE, 'SS') AS second_text
FROM DUAL;
```

`SYSDATE` là giờ hiện tại theo ngữ nghĩa server Oracle nên kết quả **không cố định**. Khi muốn ví dụ lặp lại được, nên sử dụng literal `TIMESTAMP '2026-04-05 14:27:36'` hoặc giá trị cố định.

### Kết quả có cùng ý nghĩa nhưng không cùng kiểu

Hàm `strftime('%m', ...)` của SQLite trả `TEXT` như `'04'`; `MONTH()` của MySQL hay `DATEPART(month, ...)` của SQL Server thường trả số nguyên `4`. Khi chuyển kết quả sang ứng dụng:

- Đừng dựa vào chuỗi `'04'` để làm phép cộng như số.
- Đừng dựa vào số `4` để hiển thị tháng `04` nếu chưa áp dụng định dạng.
- Đừng dùng `DATEPART(second, ...)` của SQL Server để biểu diễn tổng số giây tính từ một mốc: đó là **giây trong phút**, không phải khoảng thời gian đã trôi qua.

## 6. Trích xuất năm/tháng để lọc và nhóm dữ liệu

Giả sử bảng `orders` có cột `created_at` kiểu `TIMESTAMP` và `total_amount`. Để lấy **đơn hàng thuộc tháng 4 năm 2026**, có thể diễn đạt trực tiếp ý định bằng hai thành phần:

```sql
-- PostgreSQL:
SELECT order_id, created_at, total_amount
FROM orders
WHERE EXTRACT(YEAR FROM created_at) = 2026
  AND EXTRACT(MONTH FROM created_at) = 4;
```

Điều kiện `MONTH = 4` **một mình** sẽ khớp tháng 4 của **mọi năm**, không phải riêng năm 2026. Khi xây dựng bộ lọc theo tháng, luôn xác định có cần thêm điều kiện năm hay không.

### Nhóm theo năm và tháng

```sql
-- PostgreSQL:
SELECT
    EXTRACT(YEAR FROM created_at)::int AS order_year,
    EXTRACT(MONTH FROM created_at)::int AS order_month,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_revenue
FROM orders
GROUP BY
    EXTRACT(YEAR FROM created_at),
    EXTRACT(MONTH FROM created_at)
ORDER BY order_year, order_month;
```

Cú pháp `::int` là ép kiểu của PostgreSQL; nếu cần viết cách tổng quát hơn, dùng `CAST(EXTRACT(YEAR FROM created_at) AS INTEGER)`.

**Tại sao phải nhóm cả năm và tháng?** `GROUP BY EXTRACT(MONTH FROM created_at)` sẽ gộp **tháng 4 năm 2025** và **tháng 4 năm 2026** vào cùng một nhóm tháng 4. Điều đó chỉ đúng nếu chủ đích là so sánh mọi tháng 4 qua nhiều năm, không phải báo cáo doanh thu từng tháng của từng năm.

### Nhóm theo đầu tháng thay cho cặp năm/tháng

Trong PostgreSQL, có thể dùng:

```sql
SELECT
    DATE_TRUNC('month', created_at) AS month_start,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_revenue
FROM orders
GROUP BY DATE_TRUNC('month', created_at)
ORDER BY month_start;
```

`DATE_TRUNC('month', ...)` trả mốc thời gian đầu tháng, ví dụ `2026-04-01 00:00:00`, nên **không cần ghép năm và tháng thủ công**. Nhưng đây là hàm khác `EXTRACT`, trả kiểu ngày giờ thay vì một thành phần số.

Nếu báo cáo của hệ cần dữ liệu xuất ra theo múi giờ người dùng, hãy xác định **múi giờ áp dụng cho nhóm ngày/tháng** trước khi dùng một trong hai cách: một giao dịch gần nửa đêm UTC có thể thuộc ngày/tháng khác tại Việt Nam.

## 7. Vì sao lọc bằng khoảng thời gian thường hiệu quả hơn lọc EXTRACT?

Viết `EXTRACT(YEAR FROM created_at) = 2026` trong `WHERE` dễ đọc, nhưng một hàm bao quanh cột có thể khiến **chỉ mục B-tree thông thường trên chính `created_at`** khó được dùng làm điều kiện tìm phạm vi trực tiếp, tùy DBMS và execution plan.

Để lọc **toàn bộ tháng 4 năm 2026**, thường nên dùng khoảng nửa kín:

```sql
-- PostgreSQL: cột created_at là TIMESTAMP WITHOUT TIME ZONE.
SELECT order_id, created_at, total_amount
FROM orders
WHERE created_at >= TIMESTAMP '2026-04-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-05-01 00:00:00';
```

Điều kiện ở trên có ưu điểm:

- Không phải trích xuất năm/tháng cho mọi giá trị để biết có thuộc khoảng hay không.
- Có thể phù hợp với B-tree index trên `created_at`, tùy dữ liệu và kế hoạch của DBMS.
- Bao trọn mọi thời điểm trong tháng 4, kể cả phần giây thập phân.
- Không vô tình lấy cả `2026-05-01 00:00:00`.
- Dễ mở rộng thành khoảng thời gian bất kỳ.

Không nên tự viết cuối khoảng là `2026-04-30 23:59:59`, vì giá trị như `23:59:59.250` hoặc `23:59:59.999999` có thể bị bỏ sót, và độ chính xác tối đa của timestamp khác nhau theo DBMS. Dùng **`>= start` và `< next_start`** an toàn hơn cho kiểu dữ liệu có thời gian.

### Lọc một ngày

```sql
-- PostgreSQL, dữ liệu lưu ngày giờ local theo quy ước đã biết:
SELECT *
FROM orders
WHERE created_at >= TIMESTAMP '2026-04-05 00:00:00'
  AND created_at <  TIMESTAMP '2026-04-06 00:00:00';
```

Điều kiện đó thường phù hợp hơn việc bắt DBMS chuyển mọi `created_at` về ngày trong `WHERE`. Nếu cột là kiểu `DATE` (không chứa giờ), có thể so sánh trực tiếp bằng `DATE '2026-04-05'`. Nếu cột lưu instant theo múi giờ, mốc đầu/ngày kế tiếp phải được xác định **theo múi giờ nghiệp vụ** và đổi thành instant đúng cách.

### Index biểu thức vẫn có thể tồn tại

Một số DBMS hỗ trợ **expression index**, computed/generated column hoặc index chức năng. Khi một truy vấn thường xuyên lọc theo `EXTRACT(YEAR ...)`, hệ thống có thể thiết kế cấu trúc dữ liệu hỗ trợ biểu thức đó. Nhưng việc thêm index còn ảnh hưởng tốc độ ghi, bộ nhớ và cách quản trị. Mặc định nên bắt đầu bằng **lọc khoảng trên cột thời gian gốc**, sau đó quan sát `EXPLAIN`/execution plan trên dữ liệu thực tế để quyết định có cần giải pháp khác không.

## 8. Múi giờ: cùng một thời điểm, ngày/tháng/giờ có thể khác nhau

Giả sử một sự kiện xảy ra lúc **23:30 UTC ngày 31/12/2025**. Tại Việt Nam (UTC+07:00 vào thời điểm này), đó là **06:30 ngày 01/01/2026**. Vì vậy:

| Múi giờ dùng để biểu diễn | Ngày giờ địa phương | Năm trích xuất |
| --- | --- | ---: |
| UTC | 2025-12-31 23:30 | 2025 |
| Asia/Ho_Chi_Minh | 2026-01-01 06:30 | 2026 |

Cả hai là **một instant**. Nếu báo cáo thống kê theo năm tại Việt Nam, số liệu có thể khác báo cáo nhóm theo năm UTC, đặc biệt ở các sự kiện gần nửa đêm, đầu tháng và đầu năm.

### PostgreSQL với TIMESTAMPTZ

Trong PostgreSQL, `EXTRACT` trên `TIMESTAMPTZ` thường sử dụng **múi giờ của phiên kết nối** để xác định các trường lịch như năm, tháng, ngày và giờ. Có thể biểu diễn rõ múi giờ muốn dùng bằng `AT TIME ZONE`:

```sql
-- PostgreSQL: cùng một instant, hai cách biểu diễn theo múi giờ.
SELECT
    EXTRACT(YEAR FROM (
        TIMESTAMPTZ '2025-12-31 23:30:00+00'
            AT TIME ZONE 'UTC'
    )) AS year_utc,
    EXTRACT(YEAR FROM (
        TIMESTAMPTZ '2025-12-31 23:30:00+00'
            AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )) AS year_vietnam,
    EXTRACT(HOUR FROM (
        TIMESTAMPTZ '2025-12-31 23:30:00+00'
            AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )) AS hour_vietnam;
```

Kết quả theo ví dụ: `year_utc = 2025`, `year_vietnam = 2026` và `hour_vietnam = 6`.

Nếu viết trực tiếp:

```sql
-- PostgreSQL: kết quả HOUR phụ thuộc TimeZone của phiên.
SELECT EXTRACT(HOUR FROM TIMESTAMPTZ '2026-01-01 00:30:00+00');

SHOW TimeZone;
```

thì không nên chép một kết quả giờ cố định vào tài liệu mà không ghi múi giờ phiên. `AT TIME ZONE` cần được hiểu đúng theo **kiểu đầu vào**: với PostgreSQL, áp dụng vào `TIMESTAMPTZ` tạo biểu diễn giờ địa phương kiểu timestamp; áp dụng vào timestamp **không múi giờ** lại diễn giải giờ đó theo zone chỉ định để tạo instant.

### Múi giờ và daylight saving time (DST)

Nhiều khu vực có thay đổi độ lệch UTC theo mùa (DST). Một ngày lịch địa phương có thể dài **23 hoặc 25 giờ**, và một số thời điểm địa phương có thể không tồn tại hoặc xuất hiện hai lần. Vì thế, khi lọc báo cáo theo “ngày địa phương”:

1. Xác định múi giờ nghiệp vụ theo **tên vùng**, ví dụ `Asia/Ho_Chi_Minh` hoặc một vùng IANA khác được hệ hỗ trợ.
2. Tính **đầu ngày địa phương** và **đầu ngày kế tiếp trong cùng vùng**.
3. Chuyển hai mốc sang instant theo cách engine/ứng dụng hỗ trợ.
4. Lọc bằng `>= start_instant` và `< next_start_instant`.

Không mặc định một ngày luôn bằng `24 * 60 * 60` giây nếu nghiệp vụ dùng ngày lịch ở vùng có DST. Cũng không mặc định một offset cố định như `+07:00` phù hợp với **mọi vùng và mọi thời kỳ**.

### TIMESTAMP không múi giờ không tự biến thành UTC

Một cột `TIMESTAMP WITHOUT TIME ZONE` chứa `2026-01-01 00:30:00` không tự nói đó là 00:30 UTC hay 00:30 giờ Việt Nam. Ứng dụng phải có **quy ước lưu trữ**. Lấy `EXTRACT(HOUR FROM value)` từ cột đó chỉ cho phần giờ đã được lưu, không chứng minh gì về instant thực tế nếu thiếu thông tin múi giờ.

## 9. SECOND, mili giây, micro giây và thời gian đã trôi qua

Trích xuất `SECOND` cho biết **thành phần giây trong phút**, thường gồm phần thập phân nếu kiểu dữ liệu hỗ trợ. Nó **không** đồng nghĩa với “số giây tính từ đầu ngày” hay “tổng số giây giữa hai thời điểm”.

Ví dụ PostgreSQL:

```sql
SELECT
    EXTRACT(HOUR FROM TIMESTAMP '2026-04-05 14:27:36.250') AS hh,
    EXTRACT(MINUTE FROM TIMESTAMP '2026-04-05 14:27:36.250') AS mm,
    EXTRACT(SECOND FROM TIMESTAMP '2026-04-05 14:27:36.250') AS ss;
```

Kết quả là `14`, `27`, `36.250`. Nếu ứng dụng làm tròn hoặc ép `SECOND` về `INTEGER`, có thể mất dữ liệu phần lẻ.

### Khoảng thời gian khác một trường thời gian

Trong PostgreSQL:

```sql
SELECT
    EXTRACT(MINUTE FROM INTERVAL '2 hours 30 minutes') AS minute_component,
    EXTRACT(EPOCH FROM INTERVAL '2 hours 30 minutes') / 60 AS total_minutes;
```

`minute_component` là `30`, còn `total_minutes` là `150`. `EXTRACT(MINUTE FROM interval)` **không** tự quy đổi cả hai giờ thành phút.

Nếu muốn tính số phút đã trôi qua giữa hai timestamp trên PostgreSQL:

```sql
SELECT
    EXTRACT(EPOCH FROM (
        TIMESTAMP '2026-04-05 16:57:36'
        - TIMESTAMP '2026-04-05 14:27:36'
    )) / 60 AS elapsed_minutes;
```

Ví dụ trên trả `150` phút. Khi hai giá trị là thời điểm có múi giờ, cần dùng kiểu/biểu thức phản ánh instant phù hợp; hiệu số giữa hai giờ địa phương ngây thơ có thể khác thời gian thực đã trôi qua ở vùng có DST.

**EPOCH trong PostgreSQL:** khi trích xuất từ một `TIMESTAMPTZ`, giá trị liên quan đến số giây từ mốc Unix; khi trích xuất từ `INTERVAL`, nó thể hiện tổng độ dài interval theo giây theo quy tắc engine. Không đánh đồng `EXTRACT(EPOCH FROM timestamp)` với `EXTRACT(SECOND FROM timestamp)`.

## 10. NULL và giá trị ngày giờ không hợp lệ

Trong nhiều DBMS, `EXTRACT` hoặc hàm lấy thành phần thời gian trả `NULL` khi đầu vào là `NULL`:

```sql
-- PostgreSQL:
SELECT
    EXTRACT(YEAR FROM CAST(NULL AS TIMESTAMP)) AS year_missing,
    EXTRACT(MONTH FROM CAST(NULL AS DATE)) AS month_missing;
```

Hai giá trị đều `NULL`. Khi lọc:

```sql
SELECT order_id
FROM orders
WHERE EXTRACT(YEAR FROM paid_at) = 2026;
```

các dòng có `paid_at IS NULL` không được chọn vì điều kiện so sánh cho `UNKNOWN`, không phải `TRUE`.

Nếu muốn phân nhóm cả trạng thái chưa thanh toán, có thể dùng `CASE`:

```sql
-- PostgreSQL:
SELECT
    CASE
        WHEN paid_at IS NULL THEN 'Chưa thanh toán'
        ELSE CAST(EXTRACT(YEAR FROM paid_at) AS text)
    END AS payment_year_label,
    COUNT(*) AS order_count
FROM orders
GROUP BY
    CASE
        WHEN paid_at IS NULL THEN 'Chưa thanh toán'
        ELSE CAST(EXTRACT(YEAR FROM paid_at) AS text)
    END
ORDER BY payment_year_label;
```

Việc `CAST` sang văn bản ở ví dụ này chỉ nhằm tạo **nhãn báo cáo**, không làm năm trở thành một thuộc tính chuỗi bắt buộc trong dữ liệu gốc.

### Đầu vào sai định dạng không nhất thiết biến thành NULL

Ví dụ `'2026-02-30'` không phải một ngày lịch hợp lệ. Khi đưa chuỗi này vào hàm ngày giờ:

- Một số DBMS/kiểu chuyển đổi sẽ **báo lỗi**.
- Một số hàm/engine có thể **trả NULL**.
- Một số hệ có cấu hình hoặc hành vi đặc biệt cho giá trị zero-date, ngày thiếu hoặc chuyển kiểu.

Không xem mọi lỗi parse ngày là cùng một quy tắc SQL. Khi cần độ tin cậy, lưu dữ liệu trong **kiểu ngày giờ chuyên dụng** mà DBMS hỗ trợ, kiểm tra input ở ranh giới ứng dụng và dùng phép chuyển kiểu rõ ràng.

Nếu bảng lưu ngày dưới dạng **văn bản tùy ý**, `EXTRACT` trên cột đó có thể cần `CAST`; kết quả phụ thuộc format và cấu hình phiên. Đừng dựa vào cách diễn giải mơ hồ như `'04/05/2026'` (là 4 tháng 5 hay 5 tháng 4?) khi chưa xác định chuẩn nhập.

## 11. Thực hành PostgreSQL: tạo dữ liệu và trích xuất thành phần

Ví dụ này dành cho **PostgreSQL**, chạy trong database thực hành. Tạo bảng `sql_extract_lab` riêng; nếu đã có bảng trùng tên, dùng schema/bảng khác. Cột `occurred_at` cố ý sử dụng `TIMESTAMP WITHOUT TIME ZONE` để các câu kiểm tra thành phần giờ **không phụ thuộc múi giờ phiên**.

### 11.1. Tạo bảng mẫu

```sql
CREATE TABLE sql_extract_lab (
    event_id    INTEGER PRIMARY KEY,
    occurred_at TIMESTAMP NOT NULL,
    paid_at     TIMESTAMP,
    amount      NUMERIC(12, 2) NOT NULL
);

INSERT INTO sql_extract_lab (event_id, occurred_at, paid_at, amount)
VALUES
    (1, TIMESTAMP '2025-12-31 23:45:12.500', NULL,                                150.00),
    (2, TIMESTAMP '2026-01-01 00:05:08.250', TIMESTAMP '2026-01-01 00:15:00',     200.00),
    (3, TIMESTAMP '2026-01-04 09:30:00',     NULL,                                 75.00),
    (4, TIMESTAMP '2026-02-28 23:59:59',     TIMESTAMP '2026-03-01 00:00:01',      40.00),
    (5, TIMESTAMP '2026-03-01 12:10:00',     TIMESTAMP '2026-03-02 09:00:00',     300.00),
    (6, TIMESTAMP '2026-12-31 20:45:00',     NULL,                                 20.00),
    (7, TIMESTAMP '2027-01-01 01:00:00',     NULL,                                 99.00);
```

`occurred_at` là thời điểm sự kiện theo **quy ước giờ đã lưu trong bảng thử**. Vì đây là `TIMESTAMP` không chứa múi giờ, ví dụ không khẳng định những giá trị đó là UTC hay giờ một vùng cụ thể. `paid_at` có thể thiếu, nhằm minh họa `NULL`.

### 11.2. Lấy năm, tháng, ngày, giờ, phút, giây

```sql
SELECT
    event_id,
    occurred_at,
    EXTRACT(YEAR FROM occurred_at)::int AS event_year,
    EXTRACT(MONTH FROM occurred_at)::int AS event_month,
    EXTRACT(DAY FROM occurred_at)::int AS event_day,
    EXTRACT(HOUR FROM occurred_at)::int AS event_hour,
    EXTRACT(MINUTE FROM occurred_at)::int AS event_minute,
    EXTRACT(SECOND FROM occurred_at) AS event_second
FROM sql_extract_lab
ORDER BY event_id;
```

Dòng `event_id = 1` có `event_year = 2025`, `event_month = 12`, `event_day = 31`, `event_hour = 23`, `event_minute = 45` và `event_second = 12.500`. Dòng `event_id = 2` có `event_second = 8.250`.

**Lưu ý:** `EXTRACT(SECOND)` vẫn có phần thập phân; việc ép `::int` chỉ áp dụng cho các trường muốn biểu diễn như số nguyên.

### 11.3. Lọc sự kiện trong một tháng bằng EXTRACT

```sql
SELECT event_id, occurred_at, amount
FROM sql_extract_lab
WHERE EXTRACT(YEAR FROM occurred_at) = 2026
  AND EXTRACT(MONTH FROM occurred_at) = 1
ORDER BY occurred_at, event_id;
```

Kết quả là `event_id = 2` và `3`. Nếu bỏ điều kiện năm, bạn đang lọc **mọi tháng 1** trong tập dữ liệu, gồm cả các năm khác.

Cách dùng khoảng thời gian tương đương với dữ liệu mẫu và thuận lợi cho chỉ mục thông thường:

```sql
SELECT event_id, occurred_at, amount
FROM sql_extract_lab
WHERE occurred_at >= TIMESTAMP '2026-01-01 00:00:00'
  AND occurred_at <  TIMESTAMP '2026-02-01 00:00:00'
ORDER BY occurred_at, event_id;
```

### 11.4. Thống kê theo năm và tháng

```sql
SELECT
    EXTRACT(YEAR FROM occurred_at)::int AS event_year,
    EXTRACT(MONTH FROM occurred_at)::int AS event_month,
    COUNT(*) AS event_count,
    SUM(amount) AS total_amount
FROM sql_extract_lab
GROUP BY
    EXTRACT(YEAR FROM occurred_at),
    EXTRACT(MONTH FROM occurred_at)
ORDER BY event_year, event_month;
```

Kết quả kỳ vọng:

| Năm | Tháng | Số sự kiện | Tổng tiền |
| ---: | ---: | ---: | ---: |
| 2025 | 12 | 1 | 150.00 |
| 2026 | 1 | 2 | 275.00 |
| 2026 | 2 | 1 | 40.00 |
| 2026 | 3 | 1 | 300.00 |
| 2026 | 12 | 1 | 20.00 |
| 2027 | 1 | 1 | 99.00 |

`GROUP BY MONTH` một mình sẽ gộp dòng tháng 1 năm 2026 với tháng 1 năm 2027, nên không phản ánh báo cáo **từng tháng của từng năm**.

### 11.5. Lọc theo giờ trong ngày

```sql
-- Ví dụ: sự kiện xảy ra từ 09:00 đến trước 12:00,
-- bất kể ngày, theo giờ đang được lưu trong TIMESTAMP.
SELECT event_id, occurred_at, amount
FROM sql_extract_lab
WHERE EXTRACT(HOUR FROM occurred_at) >= 9
  AND EXTRACT(HOUR FROM occurred_at) < 12
ORDER BY occurred_at, event_id;
```

Với dữ liệu mẫu, `event_id = 3` được chọn. Điều kiện `HOUR >= 9 AND HOUR < 12` lấy mọi thời điểm trong các giờ 9, 10, 11; đó **không** phải điều kiện cho một ngày cụ thể. Nếu cột là `TIMESTAMPTZ` và yêu cầu là “giờ làm việc tại Việt Nam”, cần đổi sang giờ địa phương trước khi `EXTRACT(HOUR ...)`.

### 11.6. Ngày trong tuần và tuần ISO

```sql
SELECT
    event_id,
    occurred_at::date AS event_date,
    EXTRACT(DOW FROM occurred_at)::int AS dow_sunday_zero,
    EXTRACT(ISODOW FROM occurred_at)::int AS iso_monday_one,
    EXTRACT(ISOYEAR FROM occurred_at)::int AS iso_year,
    EXTRACT(WEEK FROM occurred_at)::int AS iso_week
FROM sql_extract_lab
ORDER BY event_id;
```

Dòng `2026-01-04` là **Chủ nhật**, nên PostgreSQL trả `DOW = 0` và `ISODOW = 7`. Việc ghép `ISOYEAR` và `WEEK` có thể quan trọng ở ranh giới tháng 12/tháng 1 khi nhóm theo tuần.

### 11.7. NULL khi chưa thanh toán

```sql
SELECT
    event_id,
    paid_at,
    EXTRACT(YEAR FROM paid_at) AS paid_year,
    CASE
        WHEN paid_at IS NULL THEN 'Chưa thanh toán'
        ELSE 'Đã thanh toán'
    END AS payment_status
FROM sql_extract_lab
ORDER BY event_id;
```

Các dòng có `paid_at IS NULL` trả `paid_year = NULL`. Không biến giá trị thiếu thành “năm 0” hay “năm hiện tại”, vì đó không phải thông tin đã được ghi nhận.

### 11.8. Khoảng thời gian từ lúc tạo tới lúc thanh toán

```sql
SELECT
    event_id,
    occurred_at,
    paid_at,
    EXTRACT(EPOCH FROM (paid_at - occurred_at)) / 60
        AS minutes_until_paid
FROM sql_extract_lab
WHERE paid_at IS NOT NULL
ORDER BY event_id;
```

Với `event_id = 2`, khoảng thời gian từ `00:05:08.250` đến `00:15:00` là khoảng **9 phút 51,75 giây**, tức `9,8625` phút. Dòng `event_id = 4` có khoảng cách **2 giây** dù hai timestamp thuộc **hai ngày lịch khác nhau**. Đây là ví dụ cho thấy trích xuất riêng `DAY`, `HOUR` hoặc `MINUTE` không thể thay phép **tính khoảng thời gian đã trôi qua**.

### 11.9. Kiểm tra kế hoạch lọc ngày khi có index

Nếu muốn quan sát kế hoạch dùng index trên cột thời gian:

```sql
CREATE INDEX ix_sql_extract_lab_occurred_at
ON sql_extract_lab (occurred_at);

EXPLAIN
SELECT event_id, occurred_at
FROM sql_extract_lab
WHERE occurred_at >= TIMESTAMP '2026-01-01 00:00:00'
  AND occurred_at <  TIMESTAMP '2027-01-01 00:00:00';
```

Bảng minh họa quá nhỏ, nên PostgreSQL **có thể chọn sequential scan** dù đã tạo index. Đó là lựa chọn của bộ tối ưu dựa trên chi phí hiện tại. Không dùng kết quả từ bảy dòng để khẳng định index có ích hay vô ích trên bảng nghiệp vụ lớn.

### 11.10. Dọn bảng thử

```sql
-- Chỉ xóa bảng thực hành do chính bạn tạo:
DROP TABLE sql_extract_lab;
```

Chỉ chạy khi không cần tiếp tục làm các bài tập bên dưới. Không chạy `DROP TABLE` trên bảng dùng chung hoặc bảng nghiệp vụ.

## 12. Kết hợp EXTRACT với điều kiện nghiệp vụ

### Thống kê theo quý

PostgreSQL có `EXTRACT(QUARTER FROM ...)`:

```sql
SELECT
    EXTRACT(YEAR FROM occurred_at)::int AS event_year,
    EXTRACT(QUARTER FROM occurred_at)::int AS event_quarter,
    COUNT(*) AS event_count
FROM sql_extract_lab
GROUP BY
    EXTRACT(YEAR FROM occurred_at),
    EXTRACT(QUARTER FROM occurred_at)
ORDER BY event_year, event_quarter;
```

Nếu đã xóa bảng ở mục 11.10, hãy tạo lại bảng mẫu trước khi chạy. Tên `QUARTER` và khả năng dùng trực tiếp trong `EXTRACT` khác theo DBMS; trên SQL Server thường dùng `DATEPART(quarter, ts)`, trên MySQL có `QUARTER(ts)`.

### Đếm đơn hàng theo giờ trong ngày

```sql
SELECT
    EXTRACT(HOUR FROM occurred_at)::int AS hour_of_day,
    COUNT(*) AS event_count
FROM sql_extract_lab
GROUP BY EXTRACT(HOUR FROM occurred_at)
ORDER BY hour_of_day;
```

Báo cáo này gộp **cùng giờ của tất cả ngày**: 09:00 ngày 1 và 09:00 ngày 2 vào chung nhóm giờ 9. Đó là điều đúng khi phân tích “sự kiện thường xảy ra vào khung giờ nào”, nhưng không đúng nếu cần từng giờ của **từng ngày cụ thể**. Trường hợp sau cần nhóm thêm ngày hoặc dùng `DATE_TRUNC('hour', occurred_at)` trên PostgreSQL.

### Phân nhóm theo thứ trong tuần

```sql
-- PostgreSQL:
SELECT
    EXTRACT(ISODOW FROM occurred_at)::int AS iso_weekday,
    COUNT(*) AS event_count
FROM sql_extract_lab
GROUP BY EXTRACT(ISODOW FROM occurred_at)
ORDER BY iso_weekday;
```

Kết quả `1` đến `7` là thứ Hai đến Chủ nhật. Nếu dùng `DOW`, Chủ nhật lại được đánh số `0`. Khi xuất dữ liệu cho UI hoặc API, hãy đặt tên cột/phần giải thích rõ quy ước để không hiển thị sai thứ.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `EXTRACT(MONTH)` cho số `4` nhưng UI muốn `04` | Trích xuất thành phần số khác định dạng văn bản | Định dạng ở tầng hiển thị hoặc dùng hàm format phù hợp |
| Báo cáo `GROUP BY MONTH` gộp nhiều năm | Thiếu thành phần năm trong khóa nhóm | Nhóm theo năm + tháng hoặc mốc đầu tháng |
| Số tuần “thuộc sai năm” | Dùng năm lịch với tuần ISO | Ghép `ISOYEAR` với `WEEK` khi báo cáo ISO |
| Ngày trong tuần sai một đơn vị | Trộn `DOW`, `ISODOW`, `DAYOFWEEK`, `WEEKDAY`, `DATEPART(weekday)` | Ghi rõ quy ước đánh số từng hàm/DBMS |
| Giờ khác giữa hai kết nối | `TIMESTAMPTZ` hiển thị theo múi giờ phiên | Xác định múi giờ đích trước khi trích xuất |
| Sự kiện cuối tháng UTC rơi sang tháng mới | Báo cáo dùng múi giờ địa phương | Dùng ranh giới tháng theo múi giờ nghiệp vụ |
| `EXTRACT(HOUR FROM date_col)` lỗi trong Oracle | Oracle `DATE` có quy tắc trường EXTRACT riêng | `CAST(date_col AS TIMESTAMP)` hoặc `TO_CHAR(..., 'HH24')` |
| `strftime('%m', ...)` là `'04'`, không phải số 4 | SQLite trả văn bản | `CAST(... AS INTEGER)` nếu cần số |
| Đầu vào ngày sai trả lỗi hoặc `NULL` | Chuỗi ngày không hợp lệ/không được parser nhận | Kiểm tra input và chuyển sang kiểu ngày giờ đúng |
| Trích `MINUTE` từ interval 2h30 trả 30, không phải 150 | Lấy thành phần phút thay vì tổng thời lượng | Tính hiệu thời gian và đổi sang tổng giây/phút |
| Lọc `EXTRACT(YEAR FROM column)` trên bảng lớn chậm | Hàm trên cột có thể hạn chế index range scan | Dùng khoảng `>= start AND < next_start`, xem execution plan |
| `WHERE EXTRACT(YEAR FROM paid_at)=2026` bỏ dòng chưa trả tiền | `NULL` khiến điều kiện là UNKNOWN | Dùng `IS NULL` nếu nghiệp vụ cần bao gồm |
| Kết quả thay đổi giữa PostgreSQL và SQL Server | Khác dialect, trường trích xuất, múi giờ và kiểu kết quả | Ghi rõ DBMS + phiên bản + kiểu cột + cấu hình liên quan |

### Ba câu hỏi cần xác định trước một báo cáo thời gian

1. **Độ hạt của báo cáo** là năm, tháng, ngày, giờ hay tuần?
2. **Múi giờ áp dụng** là UTC, giờ địa phương nào hay dữ liệu không có múi giờ?
3. **Kết quả cần kiểu số hay nhãn hiển thị**? Ví dụ số tháng `4`, chuỗi `'04'` hoặc mốc thời gian `2026-04-01 00:00:00`.

Nếu không xác định ba điều này, một truy vấn `EXTRACT` đúng cú pháp vẫn có thể tạo ra báo cáo sai nghiệp vụ.

## 14. Bài tập vận dụng

### Bài 1 — Xác định thành phần

Cho timestamp `2026-12-31 23:59:58.750`. Trên PostgreSQL, hãy viết `SELECT` trích xuất `YEAR`, `MONTH`, `DAY`, `HOUR`, `MINUTE` và `SECOND`. Kết quả của `SECOND` khác gì nếu ép thành số nguyên?

### Bài 2 — Lọc tháng 4 năm 2026

Bảng `orders` có `order_id` và `created_at` kiểu `TIMESTAMP WITHOUT TIME ZONE`. Viết hai cách lọc các đơn hàng trong tháng 4 năm 2026:

1. Dùng `EXTRACT(YEAR)` và `EXTRACT(MONTH)`.
2. Dùng khoảng thời gian nửa kín thuận lợi cho chỉ mục.

Giải thích vì sao không nên dùng điều kiện cuối tháng là `<= '2026-04-30 23:59:59'`.

### Bài 3 — Thống kê theo năm và tháng

Cho dữ liệu `2025-04-10`, `2026-04-05`, `2026-05-01`. Vì sao `GROUP BY EXTRACT(MONTH FROM created_at)` chỉ tạo hai nhóm thay vì ba nhóm? Viết khóa nhóm đầy đủ.

### Bài 4 — Tuần ISO và năm lịch

Với ngày `2021-01-01`, hãy xác định `EXTRACT(YEAR)`, `EXTRACT(ISOYEAR)` và `EXTRACT(WEEK)` của PostgreSQL. Nếu một bảng thống kê nhóm theo `YEAR` + `WEEK`, vấn đề có thể xuất hiện là gì?

### Bài 5 — Ngày trong tuần đa DBMS

Giả sử ngày xét là một Chủ nhật. So sánh các kết quả thông dụng:

- PostgreSQL `DOW` và `ISODOW`.
- MySQL `DAYOFWEEK` và `WEEKDAY`.
- SQLite `strftime('%w', ...)`.

Vì sao không nên gán trực tiếp tất cả những con số này cho cùng một enum ngày trong tuần ở ứng dụng?

### Bài 6 — Chuyển truy vấn sang SQL Server và SQLite

Chuyển ý nghĩa “lấy năm, tháng và giờ của `created_at`” từ PostgreSQL:

```sql
SELECT
    EXTRACT(YEAR FROM created_at),
    EXTRACT(MONTH FROM created_at),
    EXTRACT(HOUR FROM created_at)
FROM events;
```

sang SQL Server và SQLite. Với SQLite, nếu ứng dụng cần số nguyên thay vì văn bản, cần bổ sung gì?

### Bài 7 — Múi giờ và ranh giới năm

Một sự kiện xảy ra tại `2025-12-31 23:30:00+00`. Năm của nó theo UTC là gì, theo `Asia/Ho_Chi_Minh` là gì? Viết truy vấn PostgreSQL dùng `AT TIME ZONE` để kiểm tra cả hai kết quả.

### Bài 8 — Thành phần thời gian khác tổng thời gian

Một khoảng thời gian dài 2 giờ 30 phút. Trên PostgreSQL, `EXTRACT(MINUTE FROM interval)` trả bao nhiêu? Viết cách lấy **tổng số phút**.

### Gợi ý đáp án

1. `EXTRACT(YEAR FROM ts) = 2026`, `MONTH = 12`, `DAY = 31`, `HOUR = 23`, `MINUTE = 59`, `SECOND = 58.750`. Nếu `CAST` sang `INTEGER`, phần thập phân không còn được giữ nguyên; cần chú ý quy tắc chuyển kiểu của DBMS nếu làm tròn/ép kiểu.
2. `EXTRACT(YEAR FROM created_at)=2026 AND EXTRACT(MONTH FROM created_at)=4`; hoặc `created_at >= TIMESTAMP '2026-04-01' AND created_at < TIMESTAMP '2026-05-01'`. Mốc `23:59:59` bỏ qua các thời điểm có phần giây sau nó.
3. Hai giá trị tháng `4` của hai năm bị gộp; cần `GROUP BY EXTRACT(YEAR FROM created_at), EXTRACT(MONTH FROM created_at)` hoặc nhóm theo đầu tháng.
4. Năm lịch `2021`, năm ISO `2020`, tuần ISO `53`. Ghép năm lịch với tuần ISO có thể gắn tuần đó vào năm sai.
5. PostgreSQL `DOW=0`, `ISODOW=7`; MySQL `DAYOFWEEK=1`, `WEEKDAY=6`; SQLite `%w='0'`. Các hàm khác cả gốc đánh số và đôi khi kiểu kết quả.
6. SQL Server: `DATEPART(year, created_at)`, `DATEPART(month, created_at)`, `DATEPART(hour, created_at)`. SQLite: `strftime('%Y', created_at)`, `strftime('%m', created_at)`, `strftime('%H', created_at)`; bọc `CAST(... AS INTEGER)` nếu cần số.
7. UTC thuộc năm `2025`; giờ Việt Nam là `06:30 ngày 01/01/2026` nên năm `2026`. Dùng `EXTRACT(YEAR FROM (TIMESTAMPTZ '2025-12-31 23:30:00+00' AT TIME ZONE 'UTC'))` và thay `'UTC'` bằng `'Asia/Ho_Chi_Minh'`.
8. `EXTRACT(MINUTE FROM INTERVAL '2 hours 30 minutes') = 30`; tổng phút là `EXTRACT(EPOCH FROM INTERVAL '2 hours 30 minutes') / 60 = 150`.

Điểm cốt lõi là: **`EXTRACT` lấy một phần của giá trị ngày giờ, không mặc nhiên trả về một ngày, một khoảng thời gian hoặc một nhãn đã định dạng**. Để viết truy vấn thời gian chính xác, cần biết kiểu cột, cách đánh số tuần/ngày, múi giờ, độ chính xác giây và DBMS đang dùng. Khi lọc các mốc ngày giờ liên tiếp trên bảng lớn, hãy cân nhắc khoảng thời gian nửa kín để vừa rõ ranh giới vừa tạo điều kiện cho chỉ mục hoạt động hiệu quả.

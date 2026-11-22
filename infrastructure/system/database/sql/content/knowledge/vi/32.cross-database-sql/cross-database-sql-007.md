# Ngày giờ, múi giờ và phép tính khoảng thời gian

Trong **Database SQL**, ngày giờ xuất hiện ở đơn hàng, thanh toán, lịch hẹn, log hệ thống, giao dịch tài chính, thời hạn hợp đồng và báo cáo theo ngày. Một cột trông đơn giản như `created_at` có thể chứa những ý nghĩa rất khác nhau: ngày lịch, giờ trên đồng hồ địa phương, một thời điểm duy nhất trên dòng thời gian hoặc thời lượng đã trôi qua.

Nhầm lẫn giữa các khái niệm này có thể làm báo cáo sai ngày, lịch hẹn lệch giờ, thời hạn hết sớm/muộn hoặc tính SLA không chính xác. Bài học tập trung vào **kiểu dữ liệu, múi giờ, quy đổi và phép tính khoảng thời gian trong SQL đa hệ quản trị**. PostgreSQL được dùng làm ví dụ chính, sau đó so sánh SQL Server, Oracle, MySQL/MariaDB và SQLite.

## 1. Trước tiên hãy xác định ý nghĩa của dữ liệu

Các khái niệm cần phân biệt:

- **Ngày lịch (date):** ngày 14 tháng 11 năm 2026, không nhất thiết gắn với một thời điểm cụ thể.
- **Giờ trong ngày (time of day):** 09:30, chưa nói thuộc ngày nào hay múi giờ nào.
- **Thời điểm (instant):** một điểm duy nhất trên dòng thời gian, có thể biểu diễn bằng UTC hoặc offset.
- **Giờ địa phương (local wall time):** 09:30 tại một địa điểm, phụ thuộc quy tắc múi giờ của nơi đó.
- **Khoảng thời gian (duration):** lượng thời gian đã trôi qua, ví dụ 90 phút.
- **Khoảng lịch (calendar interval):** một ngày, một tháng hoặc một năm theo lịch; độ dài thực tế có thể khác nhau.

| Nghiệp vụ | Ý nghĩa | Mô hình phù hợp |
| --- | --- | --- |
| Ngày sinh | Ngày lịch | DATE |
| Cửa hàng mở lúc 09:00 | Giờ địa phương trong ngày | TIME + zone của cửa hàng |
| Thanh toán được xác nhận | Instant | Timestamp có timezone hoặc quy ước UTC rõ |
| Cuộc hẹn 10:00 tại Hà Nội | Local datetime + zone ID | Local timestamp + zone ID, có thể thêm instant đã giải quyết |
| Job chạy sau 15 phút | Duration | Interval hoặc số giây/millisecond |
| Hợp đồng hết hạn sau 1 tháng | Calendar arithmetic | Ngày/thời điểm + quy tắc cộng tháng |

Hãy hỏi: **nếu hai người ở hai quốc gia nhìn giá trị này, họ có phải nhìn cùng một con số giờ không?** Với instant, giờ hiển thị có thể khác; với giờ mở cửa của cửa hàng, 09:00 thường giữ nguyên theo địa điểm; với ngày sinh, không được tự đổi ngày theo timezone của người xem.

## 2. DATE, TIME, TIMESTAMP và kiểu có timezone

Các DBMS có tên kiểu khác nhau, nhưng ý nghĩa thường gặp:

| Khái niệm | Nội dung |
| --- | --- |
| DATE | Năm, tháng, ngày; Oracle DATE còn lưu giờ/phút/giây |
| TIME | Giờ, phút, giây, có thể có phần lẻ |
| TIMESTAMP | Ngày và giờ, thường không chứa thông tin múi giờ |
| TIMESTAMP WITH TIME ZONE | Thời điểm có thông tin offset/zone theo semantics của DBMS |
| TIMESTAMP WITH LOCAL TIME ZONE | Một số DBMS chuẩn hóa khi lưu và hiển thị theo timezone session |
| INTERVAL / duration | Khoảng thời gian hoặc khoảng lịch |

Không thể nhìn chữ TIMESTAMP rồi kết luận hai DBMS lưu và chuyển đổi giống nhau:

- PostgreSQL phân biệt `timestamp without time zone` và `timestamp with time zone`.
- SQL Server có `datetime2` và `datetimeoffset`.
- Oracle có `DATE`, `TIMESTAMP`, `TIMESTAMP WITH TIME ZONE` và `TIMESTAMP WITH LOCAL TIME ZONE`.
- MySQL có `DATETIME` và `TIMESTAMP` với hành vi timezone khác nhau.
- SQLite không có kiểu ngày giờ native riêng; thường dùng TEXT, REAL hoặc INTEGER.

Chọn kiểu dựa trên ý nghĩa nghiệp vụ, không dựa trên tên gọi quen thuộc.

## 3. Instant, offset và time zone là ba khái niệm khác nhau

### 3.1. Instant

Instant là một thời điểm duy nhất trên dòng thời gian. Cùng một instant có thể hiển thị:

```text
UTC:          2026-11-14 02:30
UTC+07:       2026-11-14 09:30
UTC-05:       2026-11-13 21:30
```

Giá trị instant không đổi; cách hiển thị thay đổi.

### 3.2. Offset

Offset là độ lệch so với UTC tại một thời điểm, ví dụ `+07:00`, `-05:00` hoặc `+05:30`. Nó mô tả phép quy đổi tại thời điểm đó, không mô tả toàn bộ quy tắc lịch sử và tương lai của một vùng địa lý.

### 3.3. Time zone ID

Tên như `Asia/Ho_Chi_Minh`, `Europe/Paris` hoặc `America/New_York` tham chiếu tới bộ quy tắc thời gian của một khu vực. Các quy tắc có thể thay đổi theo lịch sử và quyết định pháp lý.

Hai địa điểm có thể cùng offset hiện tại nhưng khác quy tắc vào một ngày khác. Vì vậy `+07:00` không hoàn toàn tương đương `Asia/Ho_Chi_Minh`. Nếu nghiệp vụ cần lịch địa phương trong tương lai hoặc lặp lại hàng tuần, hãy lưu zone ID phù hợp, không chỉ offset hiện tại.

## 4. UTC và ISO 8601

UTC là mốc thời gian tham chiếu phổ biến để trao đổi instant. Một số biểu diễn ISO 8601:

```text
Ngày:                  2026-11-14
Local datetime:        2026-11-14T09:30:00
Có offset:             2026-11-14T09:30:00+07:00
UTC:                   2026-11-14T02:30:00Z
```

`Z` biểu thị UTC. Offset `+07:00` cho biết giờ địa phương nhanh hơn UTC 7 giờ. Hai timestamp có offset khác nhau ở ví dụ trên biểu diễn cùng một instant.

Không dùng chuỗi mơ hồ như `03/04/2026`, vì tùy locale có thể là ngày 3 tháng 4 hoặc ngày 4 tháng 3. Ưu tiên ISO 8601 và tham số typed từ driver.

**Lưu ý:** `TIMESTAMP WITHOUT TIME ZONE` không tự trở thành UTC chỉ vì chuỗi đầu vào kết thúc bằng Z. Trong PostgreSQL, khi ép vào kiểu timestamp without time zone, thông tin zone có thể bị bỏ qua. Hãy chọn kiểu và phép chuyển đổi rõ ràng.

## 5. Lưu instant hay giờ địa phương?

**Lưu instant khi sự kiện đã xảy ra:** thanh toán được xác nhận, request được nhận, email được gửi, người dùng nhấn nút hoặc giao dịch được ghi nhận. Đây là một điểm cụ thể trên dòng thời gian.

**Lưu local datetime khi ý nghĩa gắn với đồng hồ địa phương:** cửa hàng mở lúc 09:00, lịch học lúc 07:30, cuộc hẹn lúc 10:00 tại một địa điểm hoặc job định kỳ chạy 08:00 giờ địa phương.

Với lịch hẹn tương lai, có thể cần lưu:
- Local date/time mà người dùng đã chọn.
- Time zone ID của địa điểm.
- Instant đã giải quyết theo bộ quy tắc hiện tại (nếu đã tính).
- Chính sách khi quy tắc múi giờ thay đổi.

Nếu chỉ lưu instant, sau thay đổi luật giờ địa phương, lịch có thể không còn hiển thị đúng giờ người dùng mong muốn. Nếu chỉ lưu local time mà không có zone, không thể xác định instant duy nhất.

## 6. Daylight Saving Time (DST)

Một số vùng thay đổi đồng hồ theo mùa. Khi bắt đầu giờ mùa hè, đồng hồ có thể nhảy từ 01:59:59 lên 03:00:00, khiến khoảng 02:00–02:59 **không tồn tại**. Khi kết thúc giờ mùa hè, đồng hồ lùi lại, khiến một khoảng giờ xuất hiện **hai lần**.

```text
Bắt đầu DST:
01:59:59 -> 03:00:00
02:30 không tồn tại

Kết thúc DST:
01:59:59 -> 01:00:00
01:30 xuất hiện hai lần
```

Có hai trường hợp:

- **Nonexistent local time:** giờ địa phương người dùng nhập không tồn tại trong ngày đó.
- **Ambiguous local time:** cùng một local datetime có thể tương ứng với hai instant khác nhau.

Khi nhận lịch hẹn, ứng dụng cần chính sách: từ chối giờ không tồn tại; chuyển theo quy tắc đã công bố; hoặc yêu cầu người dùng chọn occurrence/offset khi giờ xuất hiện hai lần. Không để phép parse ngầm quyết định một cuộc hẹn quan trọng mà không biết chính sách DBMS.

Tại Việt Nam hiện không có chuyển đổi DST theo mùa trong quy tắc hiện hành, nhưng hệ thống có thể phục vụ người dùng ở nhiều vùng nên vẫn cần hiểu sự khác biệt này.

## 7. IANA timezone và tên timezone theo nhà cung cấp

Nhiều hệ thống dùng IANA Time Zone Database (tzdb) với tên như `Asia/Ho_Chi_Minh` và `America/Los_Angeles`. Một số DBMS dùng tên theo hệ điều hành hoặc nhà cung cấp:

- SQL Server trên Windows thường dùng tên Windows time zone như `SE Asia Standard Time`.
- Oracle có danh sách timezone region riêng.
- PostgreSQL thường dùng tên IANA khi môi trường có tzdata.
- MySQL cần bảng timezone được nạp để xử lý tên zone.
- SQLite built-in date/time functions không cung cấp bộ IANA zone database đầy đủ cho truy vấn tùy ý.

Không giả định tên `Asia/Ho_Chi_Minh` chạy nguyên văn ở mọi DBMS. Hệ đa DBMS có thể duy trì mapping giữa zone ID chuẩn của sản phẩm và tên mà DBMS mục tiêu chấp nhận.

Cập nhật tzdata có thể thay đổi kết quả quy đổi cho ngày tương lai. Hệ thống đặt lịch dài hạn cần chính sách cập nhật và tính lại lịch theo yêu cầu nghiệp vụ.

## 8. PostgreSQL: kiểu ngày giờ

PostgreSQL hỗ trợ:

| Kiểu | Ý nghĩa |
| --- | --- |
| `date` | Ngày lịch |
| `time` / `time without time zone` | Giờ trong ngày, không có zone |
| `time with time zone` (`timetz`) | Giờ kèm offset; ít phù hợp để lưu lịch địa phương dài hạn |
| `timestamp` / `timestamp without time zone` | Ngày + giờ địa phương, không gắn zone |
| `timestamptz` | Alias của timestamp with time zone; biểu diễn instant |
| `interval` | Khoảng thời gian/khoảng lịch |

PostgreSQL timestamp có độ chính xác tối đa tới microsecond (6 chữ số phần lẻ giây); có thể khai báo precision thấp hơn như `timestamp(3)`.

### 8.1. TIMESTAMP WITHOUT TIME ZONE

```sql
CREATE TABLE local_appointments (
    appointment_id BIGINT PRIMARY KEY,
    local_start TIMESTAMP NOT NULL,
    zone_name TEXT NOT NULL
);
```

`local_start` chỉ lưu con số ngày giờ trên đồng hồ. `zone_name` là dữ liệu riêng cần được xác thực theo danh sách zone mà ứng dụng hỗ trợ.

Không đặt tên cột `created_at_utc` cho kiểu timestamp without time zone nếu hệ thống không có quy ước ép buộc mọi giá trị luôn là UTC; tên đó dễ khiến người đọc hiểu nhầm kiểu dữ liệu có timezone.

### 8.2. TIMESTAMP WITH TIME ZONE

```sql
CREATE TABLE payment_events (
    payment_id BIGINT PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL
);
```

PostgreSQL lưu instant đã được chuẩn hóa; **không lưu nguyên tên múi giờ gốc** mà caller nhập. Khi đọc, giá trị được hiển thị theo setting `TimeZone` của session.

Hai input sau biểu diễn cùng một instant:

```sql
SELECT
    TIMESTAMPTZ '2026-11-14 02:30:00+00',
    TIMESTAMPTZ '2026-11-14 09:30:00+07';
```

Nếu cần biết người dùng chọn zone nào, lưu thêm zone ID. `timestamptz` một mình không đủ để khôi phục lựa chọn ban đầu `Asia/Ho_Chi_Minh` so với một zone khác đang cùng offset.

## 9. PostgreSQL: AT TIME ZONE

`AT TIME ZONE` có hai hướng chuyển đổi tùy kiểu đầu vào.

### 9.1. Local timestamp thành instant

```sql
SELECT
    TIMESTAMP '2026-11-14 09:30:00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh' AS instant_value;
```

Ý nghĩa: coi 09:30 là giờ trên đồng hồ của vùng `Asia/Ho_Chi_Minh`, rồi xác định instant tương ứng. Kết quả là `timestamptz`.

### 9.2. Instant thành local timestamp

```sql
SELECT
    TIMESTAMPTZ '2026-11-14 02:30:00+00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh' AS local_value;
```

Kết quả là timestamp without time zone biểu diễn giờ địa phương tại vùng đó.

| Kiểu bên trái | Kết quả | Ý nghĩa |
| --- | --- | --- |
| timestamp without time zone | timestamptz | Diễn giải local time theo zone để tạo instant |
| timestamptz | timestamp without time zone | Hiển thị instant theo giờ địa phương zone |

Không đọc ngược hai hướng này. Một bên gắn ý nghĩa zone vào local datetime; bên kia chuyển instant sang đồng hồ địa phương.

## 10. PostgreSQL: TimeZone session ảnh hưởng hiển thị

Kiểm tra session:

```sql
SHOW TimeZone;
```

Thay đổi:

```sql
SET TIME ZONE 'UTC';
SET TIME ZONE 'Asia/Ho_Chi_Minh';
```

Đọc cùng một `timestamptz` dưới hai session có thể thấy hai giờ khác nhau, nhưng instant không đổi.

```sql
SELECT TIMESTAMPTZ '2026-11-14 02:30:00+00' AS event_time;
SET TIME ZONE 'Asia/Ho_Chi_Minh';
SELECT TIMESTAMPTZ '2026-11-14 02:30:00+00' AS event_time;
```

Để API nhất quán, quy định rõ session timezone hoặc format kết quả có offset/UTC. Không để connection pool trả dữ liệu theo session setting không được kiểm soát.

## 11. PostgreSQL: CURRENT_TIMESTAMP, now() và clock_timestamp()

Các hàm “thời điểm hiện tại” khác nhau:

| Hàm | Ý nghĩa |
| --- | --- |
| `CURRENT_TIMESTAMP` | Thời điểm bắt đầu transaction |
| `now()` | Đồng nghĩa transaction timestamp |
| `transaction_timestamp()` | Thời điểm bắt đầu transaction |
| `statement_timestamp()` | Thời điểm bắt đầu câu lệnh hiện tại |
| `clock_timestamp()` | Đồng hồ thực tại lúc hàm được gọi; có thể thay đổi trong cùng statement |

Ví dụ:

```sql
BEGIN;

SELECT
    CURRENT_TIMESTAMP AS transaction_time,
    statement_timestamp() AS statement_time,
    clock_timestamp() AS wall_clock_time;

SELECT pg_sleep(1);

SELECT
    CURRENT_TIMESTAMP AS transaction_time,
    statement_timestamp() AS second_statement_time,
    clock_timestamp() AS later_wall_clock_time;

COMMIT;
```

Hai lần `CURRENT_TIMESTAMP` trong cùng transaction giống nhau. `clock_timestamp()` có thể khác vì thời gian thực đã trôi qua.

Chọn theo mục đích: thời điểm transaction cho các bản ghi cùng giao dịch; statement timestamp để ghi mốc câu lệnh; clock timestamp để đọc đồng hồ thực tại lúc gọi. Đo duration trong ứng dụng nên cân nhắc monotonic clock vì đồng hồ hệ thống có thể được điều chỉnh.

## 12. PostgreSQL: phép cộng/trừ cơ bản

```sql
SELECT DATE '2026-11-14' + 7 AS next_week;
SELECT DATE '2026-11-14' - 3 AS three_days_before;

SELECT
    TIMESTAMP '2026-11-14 09:00:00'
    + INTERVAL '90 minutes' AS later_time;

SELECT
    TIMESTAMP '2026-11-14 10:30:00'
    - TIMESTAMP '2026-11-14 09:00:00' AS elapsed_interval;
```

Các phép toán:

- DATE + integer → DATE.
- DATE - integer → DATE.
- TIMESTAMP + INTERVAL → TIMESTAMP.
- TIMESTAMP - TIMESTAMP → INTERVAL.

Với hai instant `timestamptz`, phép trừ trả khoảng thời gian đã trôi qua giữa hai instant. Với hai timestamp without time zone, phép trừ chỉ tính chênh lệch các con số local datetime; nếu chúng thuộc zone khác nhau hoặc qua DST mà không có zone, kết quả có thể không phản ánh elapsed time thực.

## 13. INTERVAL: ngày lịch khác 24 giờ

PostgreSQL `interval` có thể chứa thành phần tháng, ngày và thời gian:

```sql
SELECT
    INTERVAL '1 year 2 months 3 days 04:05:06',
    INTERVAL '90 minutes',
    INTERVAL '24 hours';
```

Một ngày lịch không phải lúc nào cũng có đúng 24 giờ thực ở vùng có DST. Với `timestamptz`, cộng `INTERVAL '1 day'` có thể giữ nguyên giờ địa phương của ngày kế tiếp; cộng `INTERVAL '24 hours'` là cộng 24 giờ đã trôi qua. Hai kết quả có thể khác nhau khi vượt qua ngày chuyển DST.

Ví dụ minh họa ở vùng có DST:

```sql
SET TIME ZONE 'America/New_York';

SELECT
    TIMESTAMPTZ '2026-03-07 12:00:00 America/New_York'
        + INTERVAL '1 day' AS same_local_time_next_day,
    TIMESTAMPTZ '2026-03-07 12:00:00 America/New_York'
        + INTERVAL '24 hours' AS exactly_24_hours_later;
```

Hãy thử với ngày chuyển DST thực tế theo tzdata của môi trường; lịch chuyển không giống nhau giữa các vùng và năm. Tại Việt Nam hiện không có DST theo mùa, nhưng hệ thống đa quốc gia vẫn phải xử lý.

## 14. Khoảng lịch và duration thực

Hai yêu cầu khác nhau:

- “Sau 1 tháng kể từ 31/01 là ngày nào?” là phép toán lịch. Tháng kế tiếp không có ngày 31; DBMS áp dụng quy tắc cuối tháng.
- “Sau đúng 30 × 24 giờ kể từ instant này” là duration cố định, không phụ thuộc độ dài tháng hay ngày lịch.

Ví dụ:

```sql
-- PostgreSQL: phép cộng theo tháng lịch
SELECT DATE '2024-01-31' + INTERVAL '1 month';

-- Duration cố định 720 giờ
SELECT TIMESTAMPTZ '2024-01-31 09:00:00+00'
       + INTERVAL '720 hours';
```

Không thay `1 month` bằng 30 ngày nếu nghiệp vụ là hạn theo tháng. Hợp đồng “đến hết ngày cuối tháng kế tiếp” khác subscription “30 ngày sau khi kích hoạt”.

## 15. EXTRACT và DATE_PART

Dùng `EXTRACT` để lấy thành phần ngày giờ:

```sql
SELECT
    EXTRACT(YEAR FROM TIMESTAMP '2026-11-14 09:30:45') AS year_part,
    EXTRACT(MONTH FROM TIMESTAMP '2026-11-14 09:30:45') AS month_part,
    EXTRACT(DAY FROM TIMESTAMP '2026-11-14 09:30:45') AS day_part,
    EXTRACT(HOUR FROM TIMESTAMP '2026-11-14 09:30:45') AS hour_part,
    EXTRACT(MINUTE FROM TIMESTAMP '2026-11-14 09:30:45') AS minute_part,
    EXTRACT(SECOND FROM TIMESTAMP '2026-11-14 09:30:45') AS second_part;
```

`date_part('field', source)` là dạng hàm tiện dụng trong PostgreSQL, trả kiểu số dấu phẩy động. Có thể lấy epoch cho khoảng elapsed:

```sql
SELECT EXTRACT(
    EPOCH FROM (
        TIMESTAMPTZ '2026-11-14 03:00:00+00'
        - TIMESTAMPTZ '2026-11-14 02:30:00+00'
    )
) AS elapsed_seconds;
```

Kết quả là 1800 giây. Không coi tháng trong một interval lịch là một lượng giây cố định; độ dài tháng không cố định.

## 16. Tuổi, số tháng và số ngày

Không có một định nghĩa duy nhất cho “số năm giữa hai ngày”:

- Chia số ngày cho 365 chỉ là xấp xỉ.
- Chia cho 365.25 cũng là xấp xỉ, không phải tuổi lịch chính xác.
- Tuổi theo lịch cần xét tháng/ngày sinh và ngày tham chiếu.
- Số tháng trọn vẹn khác với số lần đi qua ranh giới tháng.

PostgreSQL `age()` trả interval dạng lịch:

```sql
SELECT age(
    DATE '2026-11-14',
    DATE '2000-11-20'
) AS calendar_age;
```

Nếu cần số ngày đã trôi qua, trừ DATE:

```sql
SELECT DATE '2026-11-14' - DATE '2026-11-01' AS day_count;
```

Nếu cần elapsed hours/minutes, trừ hai instant rồi lấy epoch/đơn vị phù hợp. Ghi rõ là **ngày lịch**, **tháng trọn vẹn**, hay **thời gian thực đã trôi qua**.

## 17. Đầu tháng và cuối tháng

PostgreSQL dùng `date_trunc`:

```sql
SELECT date_trunc(
    'month',
    TIMESTAMP '2026-11-14 09:30:00'
) AS month_start;
```

Ngày đầu tháng kế tiếp:

```sql
SELECT
    (date_trunc('month', DATE '2026-11-14')
     + INTERVAL '1 month')::date AS next_month_start;
```

Ngày cuối tháng:

```sql
SELECT
    (date_trunc('month', DATE '2026-11-14')
     + INTERVAL '1 month'
     - INTERVAL '1 day')::date AS month_end;
```

Khi tính cho timestamp có timezone, phải xác định đầu tháng theo múi giờ nào trước khi chuyển thành instant.

## 18. Lọc timestamp theo ngày: khoảng nửa mở

Một cách thường gặp:

```sql
WHERE created_at::date = DATE '2026-11-14'
```

Phép ép kiểu trên cột có thể làm index B-tree trên `created_at` khó được sử dụng trực tiếp, tùy DBMS và expression index.

Cách thường tốt hơn là khoảng **nửa mở**:

```sql
WHERE created_at >= TIMESTAMPTZ '2026-11-14 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-11-15 00:00:00+00'
```

Đầu khoảng được tính, cuối khoảng không tính. Cách này không phụ thuộc timestamp có precision giây, millisecond hay microsecond.

Không dùng `BETWEEN start AND '23:59:59'` cho cả ngày; giá trị `23:59:59.500000` sẽ bị bỏ sót. Khoảng `[start, next_start)` nối tiếp không chồng lấn.

## 19. Lọc một ngày địa phương trong PostgreSQL

Giả sử `created_at` là `timestamptz`, báo cáo cần sự kiện thuộc ngày 14/11/2026 tại `Asia/Ho_Chi_Minh`. Tạo hai mốc đầu ngày địa phương liên tiếp rồi chuyển mỗi mốc thành instant:

```sql
WITH bounds AS (
    SELECT
        (DATE '2026-11-14'::timestamp
            AT TIME ZONE 'Asia/Ho_Chi_Minh') AS start_at,
        ((DATE '2026-11-14' + 1)::timestamp
            AT TIME ZONE 'Asia/Ho_Chi_Minh') AS end_at
)
SELECT e.*
FROM app.events AS e
CROSS JOIN bounds AS b
WHERE e.created_at >= b.start_at
  AND e.created_at <  b.end_at;
```

Điểm quan trọng:

- DATE + 1 tăng một ngày lịch.
- Hai local midnight được chuyển riêng sang timestamptz.
- Nếu vùng có DST, khoảng instant của một ngày địa phương có thể dài 23 hoặc 25 giờ.
- Không cộng cố định 24 giờ vào instant đầu ngày nếu yêu cầu là cả ngày lịch ở vùng có DST.

Điều kiện trên cột giữ nguyên dạng range, giúp index timestamp có cơ hội được sử dụng.

## 20. Sargability và index thời gian

Với bảng sự kiện lớn:

```sql
CREATE INDEX ix_events_created_at
ON app.events(created_at);
```

Truy vấn khoảng:

```sql
SELECT event_id, created_at
FROM app.events
WHERE created_at >= $1
  AND created_at < $2
ORDER BY created_at;
```

có thể dùng index range scan/index scan tùy selectivity và kế hoạch. Nếu ép kiểu cột trong WHERE, index thông thường có thể không được dùng trực tiếp. Nếu cần truy vấn theo biểu thức ngày, xem xét expression index hoặc cột ngày địa phương đã được định nghĩa rõ.

Không mặc định index luôn được chọn: nếu khoảng thời gian bao phủ phần lớn bảng, sequential scan có thể rẻ hơn. Dùng EXPLAIN trên dữ liệu đại diện.

## 21. SLA và thời gian xử lý

Một SLA có thể định nghĩa:

- Thời gian thực đã trôi qua giữa lúc nhận và lúc xử lý.
- Thời gian làm việc, không tính cuối tuần/ngày nghỉ.
- Thời gian theo giờ địa phương của khách.
- Thời hạn 2 ngày lịch.
- Thời hạn 48 giờ thực.

Đây là các quy tắc khác nhau.

Elapsed duration:

```sql
SELECT
    EXTRACT(EPOCH FROM (finished_at - started_at))
        AS elapsed_seconds
FROM app.jobs;
```

Với SLA theo giờ làm việc, phép trừ timestamp đơn giản không đủ. Cần lịch làm việc, ngày nghỉ, múi giờ, ca làm và chính sách ngày lễ; có thể cần bảng calendar/business_hours và phép tính phần giao nhau với các khoảng làm việc.

Không dùng `DATEDIFF(day, start, end)` hoặc phép trừ DATE để đo SLA theo giây nếu nghiệp vụ đòi elapsed time chính xác.

## 22. Lịch lặp: lưu giờ địa phương và zone ID

Một lịch như “mỗi ngày lúc 08:30 tại Paris” không nên chỉ lưu instant của lần chạy đầu. Cấu trúc gợi ý:

```sql
CREATE TABLE scheduled_jobs (
    job_id BIGINT PRIMARY KEY,
    local_time TIME NOT NULL,
    zone_name TEXT NOT NULL,
    start_date DATE NOT NULL,
    recurrence_rule TEXT NOT NULL
);
```

`recurrence_rule` có thể được chuẩn hóa thành cột ngày trong tuần, chu kỳ hoặc biểu thức lịch theo thiết kế sản phẩm. Không tự tạo ngôn ngữ lịch tự do nếu chỉ cần các lựa chọn cố định.

Khi đến ngày chạy:

1. Xác định local date theo lịch.
2. Ghép local date với local_time.
3. Diễn giải theo zone_name.
4. Xử lý giờ không tồn tại/ambiguous theo chính sách.
5. Tạo instant cho lần chạy.
6. Lưu trạng thái/idempotency để không chạy trùng.

Nếu người dùng đổi zone hoặc quy tắc vùng đổi, hệ thống phải quyết định giữ giờ địa phương hay giữ instant đã lên lịch.

## 23. MySQL/MariaDB: DATE, TIME, DATETIME và TIMESTAMP

Các kiểu thường gặp:

| Kiểu | Ý nghĩa |
| --- | --- |
| `DATE` | Ngày lịch |
| `TIME` | Giờ hoặc giá trị dạng thời lượng, có thể âm/vượt 24 giờ theo giới hạn kiểu |
| `DATETIME` | Ngày giờ không tự chuyển đổi theo session timezone |
| `TIMESTAMP` | Chuyển đổi giữa session time zone và UTC khi lưu/đọc theo semantics MySQL |
| `YEAR` | Kiểu năm riêng, ít dùng hơn trong mô hình tổng quát |

`DATETIME` thường phù hợp với local datetime cần giữ nguyên con số đồng hồ. `TIMESTAMP` thường dùng cho instant, nhưng cần quản lý session time zone và miền giá trị theo phiên bản.

MySQL/MariaDB hỗ trợ fractional seconds tới microsecond (precision tối đa 6) cho các kiểu temporal tương ứng.

### 23.1. Session time zone

```sql
SELECT @@session.time_zone, @@global.time_zone;
SET time_zone = '+00:00';
```

`TIMESTAMP` được chuyển đổi theo session time zone khi ghi/đọc; `DATETIME` không tự chuyển đổi tương tự. Vì vậy hai cột có cùng chuỗi hiển thị trong một session vẫn có semantics khác.

### 23.2. Chuyển đổi và phép tính

Các hàm thường dùng:

- `UTC_TIMESTAMP()`: thời điểm UTC hiện tại.
- `NOW()` / `CURRENT_TIMESTAMP`: thời điểm hiện tại theo session.
- `CONVERT_TZ(dt, from_tz, to_tz)`: chuyển datetime giữa zone.
- `DATE_ADD` / `DATE_SUB`: cộng/trừ khoảng lịch.
- `TIMESTAMPDIFF(unit, start, end)`: chênh lệch theo đơn vị.
- `DATEDIFF(date1, date2)`: chênh lệch ngày, bỏ phần giờ.

```sql
SELECT
    UTC_TIMESTAMP() AS utc_now,
    NOW() AS session_now,
    CONVERT_TZ(
        '2026-11-14 02:30:00',
        '+00:00',
        '+07:00'
    ) AS vietnam_local;

SELECT TIMESTAMPDIFF(
    MINUTE,
    '2026-11-14 09:00:00',
    '2026-11-14 10:30:00'
) AS elapsed_minutes;

SELECT DATEDIFF(
    '2026-11-15 01:00:00',
    '2026-11-14 23:00:00'
) AS calendar_day_difference;
```

Với tên zone như `Asia/Ho_Chi_Minh`, bảng timezone của MySQL phải được nạp/cập nhật; nếu thiếu, `CONVERT_TZ` có thể trả NULL. `TIMESTAMPDIFF` trả số nguyên theo đơn vị và phần lẻ nhỏ hơn có thể bị bỏ. MariaDB có tính năng tương tự nhưng cần kiểm tra phiên bản/engine.

## 24. SQL Server: kiểu ngày giờ

SQL Server có:

| Kiểu | Ý nghĩa |
| --- | --- |
| `date` | Ngày lịch |
| `time(n)` | Giờ trong ngày |
| `datetime2(n)` | Ngày + giờ, không chứa offset |
| `datetimeoffset(n)` | Ngày + giờ kèm offset |
| `datetime` | Kiểu cũ, precision và cách làm tròn hạn chế hơn |
| `smalldatetime` | Kiểu cũ, precision phút |

Với ứng dụng mới, thường xem xét `date`, `time`, `datetime2` hoặc `datetimeoffset` thay cho `datetime` cũ nếu phù hợp.

`datetimeoffset` giữ offset cùng giá trị ngày giờ và xác định instant, nhưng **không giữ tên zone vùng** như `America/New_York`. Nếu cần quy tắc địa lý cho lịch tương lai, lưu zone ID riêng theo quy ước ứng dụng.

### 24.1. Hàm thời gian hiện tại

```sql
SELECT
    GETDATE() AS server_local_datetime,
    SYSDATETIME() AS high_precision_local_datetime,
    SYSDATETIMEOFFSET() AS server_datetime_with_offset,
    GETUTCDATE() AS utc_datetime,
    SYSUTCDATETIME() AS high_precision_utc;
```

Các hàm local phụ thuộc môi trường server; hàm UTC trả thời điểm UTC. Chọn theo nơi đặt mốc và precision cần thiết.

### 24.2. AT TIME ZONE

SQL Server dùng tên zone theo Windows time zone database:

```sql
DECLARE @localTime datetime2 = '2026-11-14T09:30:00';

SELECT
    @localTime AT TIME ZONE 'SE Asia Standard Time'
        AS vietnam_datetimeoffset;
```

Một instant có offset có thể chuyển sang zone khác:

```sql
DECLARE @event datetimeoffset =
    '2026-11-14T02:30:00+00:00';

SELECT
    @event AT TIME ZONE 'SE Asia Standard Time'
        AS local_event;
```

Tra cứu tên zone:

```sql
SELECT name, current_utc_offset, is_currently_dst
FROM sys.time_zone_info;
```

Tên Windows không nhất thiết trùng IANA ID. `AT TIME ZONE` áp dụng quy tắc zone, gồm xử lý khoảng DST bị thiếu/trùng theo semantics SQL Server. Với lịch quan trọng, kiểm thử các ngày chuyển DST.

## 25. SQL Server: DATEADD, DATEDIFF và DATEDIFF_BIG

Cộng thời gian:

```sql
SELECT DATEADD(day, 7, CAST('2026-11-14' AS date)) AS next_week;

SELECT DATEADD(month, 1, CAST('2024-01-31' AS date))
    AS next_month;
```

Tính chênh lệch:

```sql
SELECT DATEDIFF(
    minute,
    '2026-11-14T09:00:00',
    '2026-11-14T10:30:00'
) AS minute_boundaries;

SELECT DATEDIFF_BIG(
    second,
    '2026-11-14T09:00:00',
    '2026-11-14T10:30:00'
) AS second_boundaries;
```

**DATEDIFF đếm ranh giới đơn vị đã đi qua**, không phải luôn là phép đo duration chính xác theo đơn vị với phần lẻ. Hai timestamp cách nhau một phần rất nhỏ nhưng vượt qua ranh giới phút có thể cho kết quả 1 phút.

`DATEDIFF_BIG` mở rộng phạm vi số nguyên, không đổi nguyên tắc đếm ranh giới. Chọn đơn vị đủ nhỏ và precision phù hợp nếu cần elapsed time.

## 26. Oracle: DATE, TIMESTAMP và timezone

Oracle có điểm khác biệt dễ nhầm: kiểu `DATE` **lưu năm, tháng, ngày, giờ, phút và giây**, không chỉ ngày lịch.

| Kiểu | Ý nghĩa |
| --- | --- |
| `DATE` | Ngày và giờ tới giây, không timezone |
| `TIMESTAMP(p)` | Ngày giờ có fractional seconds |
| `TIMESTAMP WITH TIME ZONE` | Timestamp có timezone/offset hoặc region |
| `TIMESTAMP WITH LOCAL TIME ZONE` | Chuẩn hóa khi lưu và hiển thị theo session timezone |
| `INTERVAL YEAR TO MONTH` | Khoảng năm/tháng |
| `INTERVAL DAY TO SECOND` | Khoảng ngày/giờ/phút/giây |

Ví dụ:

```sql
CREATE TABLE events (
    event_id NUMBER PRIMARY KEY,
    event_date DATE NOT NULL,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL
);
```

Nếu dùng Oracle DATE cho ngày sinh thuần, quy ước phần giờ luôn midnight và kiểm soát ở ứng dụng/constraint. Không mặc định Oracle DATE chỉ có ngày.

### 26.1. Hàm thời gian hiện tại

```sql
SELECT
    SYSDATE,
    SYSTIMESTAMP,
    CURRENT_DATE,
    CURRENT_TIMESTAMP,
    LOCALTIMESTAMP,
    DBTIMEZONE,
    SESSIONTIMEZONE
FROM dual;
```

Khái quát:

- `SYSDATE`: ngày giờ theo đồng hồ hệ điều hành database server, kiểu DATE.
- `SYSTIMESTAMP`: timestamp có fractional seconds và timezone server.
- `CURRENT_DATE`: ngày giờ theo session time zone, kiểu DATE.
- `CURRENT_TIMESTAMP`: timestamp theo session time zone.
- `LOCALTIMESTAMP`: timestamp local theo session, không giữ zone trong kết quả.
- `DBTIMEZONE`: database time zone.
- `SESSIONTIMEZONE`: session time zone.

Đừng coi các hàm này là cùng một giá trị trong mọi session.

### 26.2. FROM_TZ, AT TIME ZONE và INTERVAL

```sql
SELECT FROM_TZ(
    TIMESTAMP '2026-11-14 09:30:00',
    'Asia/Ho_Chi_Minh'
) AS zoned_value
FROM dual;

SELECT
    FROM_TZ(
        TIMESTAMP '2026-11-14 02:30:00',
        '+00:00'
    ) AT TIME ZONE 'Asia/Ho_Chi_Minh' AS local_value
FROM dual;
```

Oracle có thể cộng DATE theo số ngày:

```sql
SELECT
    DATE '2026-11-14' + 7 AS next_week,
    DATE '2026-11-14' - DATE '2026-11-01' AS days_between
FROM dual;
```

Với TIMESTAMP và INTERVAL:

```sql
SELECT
    TIMESTAMP '2026-11-14 09:00:00'
        + INTERVAL '90' MINUTE AS later_time,
    NUMTODSINTERVAL(90, 'MINUTE') AS ninety_minutes,
    NUMTOYMINTERVAL(2, 'MONTH') AS two_months
FROM dual;
```

`ADD_MONTHS` áp dụng quy tắc cuối tháng của Oracle; `MONTHS_BETWEEN` có semantics riêng và có thể trả tháng lẻ. Không dùng nó thay “số tháng trọn vẹn” nếu hợp đồng nghiệp vụ yêu cầu định nghĩa khác.

## 27. SQLite: không có kiểu ngày giờ native riêng

SQLite có các storage class chính NULL, INTEGER, REAL, TEXT và BLOB. Ngày giờ thường dùng một trong ba representation:

1. **TEXT:** chuỗi ISO 8601, ví dụ `2026-11-14 09:30:00`.
2. **REAL:** Julian day number.
3. **INTEGER:** Unix epoch, thường tính theo giây.

Ví dụ:

```sql
CREATE TABLE events (
    event_id INTEGER PRIMARY KEY,
    occurred_at TEXT NOT NULL
);

CREATE TABLE event_epochs (
    event_id INTEGER PRIMARY KEY,
    occurred_at_epoch INTEGER NOT NULL
);
```

Phải thống nhất representation trong cùng cột. Không trộn local text, UTC text, Unix seconds và Unix milliseconds mà không có metadata đơn vị.

### 27.1. Hàm date/time

| Hàm | Kết quả |
| --- | --- |
| `date(...)` | Ngày dạng YYYY-MM-DD |
| `time(...)` | Giờ dạng HH:MM:SS |
| `datetime(...)` | Ngày + giờ dạng text |
| `julianday(...)` | Số thực Julian day |
| `unixepoch(...)` | Unix timestamp số giây |
| `strftime(format, ...)` | Format/trích thành phần |

```sql
SELECT
    date('2026-11-14') AS date_value,
    time('2026-11-14 09:30:00') AS time_value,
    datetime('2026-11-14 09:30:00', '+90 minutes')
        AS later_time,
    unixepoch('2026-11-14 09:30:00') AS epoch_seconds;

SELECT
    julianday('2026-11-14')
    - julianday('2026-11-01') AS day_difference;
```

`julianday` trả số thực theo ngày. Với duration cần chính xác cao, cân nhắc epoch integer theo đơn vị đã quy định và kiểm soát overflow/precision.

### 27.2. Timezone và giới hạn

SQLite có modifier như `utc`, `localtime`, `unixepoch` và offset trong chuỗi. Tuy nhiên built-in functions **không phải engine IANA timezone đầy đủ** để chuyển tùy ý giữa mọi region.

- `localtime` dựa vào timezone local của môi trường chạy SQLite.
- Offset trong chuỗi có thể được xử lý khi parse.
- Không kỳ vọng cú pháp `AT TIME ZONE 'Asia/Ho_Chi_Minh'` như PostgreSQL.
- Nếu cần lịch vùng, DST và quy tắc lịch sử, dùng thư viện timezone ở ứng dụng hoặc extension được quản lý rõ.

## 28. So sánh nhanh các DBMS

| Chủ đề | PostgreSQL | SQL Server | Oracle | MySQL/MariaDB | SQLite |
| --- | --- | --- | --- | --- | --- |
| Ngày lịch | `date` | `date` | `DATE` (có giờ tới giây) | `DATE` | TEXT/INTEGER/REAL |
| Giờ trong ngày | `time` | `time` | Dùng TIMESTAMP/DATE theo thiết kế | `TIME` (cũng có thể là duration) | TEXT/representation |
| Local datetime | `timestamp` | `datetime2` | `TIMESTAMP` hoặc `DATE` | `DATETIME` | TEXT/representation |
| Instant có offset | `timestamptz` | `datetimeoffset` | `TIMESTAMP WITH TIME ZONE` | `TIMESTAMP` theo session timezone | Thường UTC text/epoch |
| Session timezone | `TimeZone` | Theo kiểu và AT TIME ZONE | `SESSIONTIMEZONE` | `time_zone` | Không tương đương |
| Cộng khoảng | `INTERVAL` | `DATEADD` | INTERVAL/DATE arithmetic | `DATE_ADD` | Modifier |
| Chênh lệch | Trừ, `EXTRACT EPOCH` | `DATEDIFF[_BIG]` | Trừ, interval, `MONTHS_BETWEEN` | `TIMESTAMPDIFF`, `DATEDIFF` | `julianday`, `unixepoch` |

Bảng chỉ so sánh ý tưởng và hàm thường dùng, không khẳng định cú pháp hay mọi trường hợp biên tương đương. Phiên bản, session settings và timezone database đều ảnh hưởng kết quả.

## 29. DATEDIFF không có cùng semantics ở mọi DBMS

Tên hàm giống nhau không có nghĩa kết quả giống nhau:

- SQL Server `DATEDIFF` đếm số ranh giới của đơn vị đã đi qua.
- MySQL `DATEDIFF` bỏ phần giờ và tính chênh lệch ngày; `TIMESTAMPDIFF` có đơn vị rõ và trả số nguyên.
- PostgreSQL thường dùng phép trừ, `age()` và `EXTRACT`.
- Oracle có phép trừ DATE trả số ngày dạng số, interval cho timestamp và `MONTHS_BETWEEN`.
- SQLite dùng `julianday()`/`unixepoch()`.

Ví dụ hai timestamp chỉ cách nhau 0,2 giây nhưng qua nửa đêm:

```text
2026-11-14 23:59:59.900
2026-11-15 00:00:00.100
```

Elapsed time chỉ 0,2 giây, nhưng ngày lịch đã đổi. Một hàm đếm ranh giới ngày có thể trả 1. Khi chuyển DBMS, phải chuyển **định nghĩa nghiệp vụ**, không chỉ đổi tên hàm.

## 30. Precision, làm tròn và đồng hồ

Kiểu ngày giờ có precision khác nhau:

- PostgreSQL timestamp tối đa microseconds.
- SQL Server `datetime2` hỗ trợ precision tới 7 chữ số phần lẻ giây.
- Oracle TIMESTAMP hỗ trợ fractional seconds theo precision khai báo.
- MySQL/MariaDB temporal hỗ trợ tối đa 6 chữ số phần lẻ.
- SQLite phụ thuộc representation và hàm xử lý.

Nguồn có thể gửi nanoseconds trong khi cột chỉ lưu milliseconds; driver có thể làm tròn/cắt phần lẻ; đồng hồ nhiều máy có thể lệch nhau. Hai sự kiện khác nhau có thể có timestamp bằng nhau.

Nếu cần thứ tự sự kiện duy nhất, đừng chỉ dựa timestamp; dùng ID/sequence/log offset hoặc tie-breaker. Timestamp không tự bảo đảm thứ tự commit tuyệt đối giữa nhiều máy.

## 31. Format hiển thị khác với lưu trữ

PostgreSQL:

```sql
SELECT to_char(
    TIMESTAMP '2026-11-14 09:30:00',
    'DD/MM/YYYY HH24:MI:SS'
);
```

`to_char` tạo chuỗi hiển thị. Không lưu kết quả đó làm giá trị temporal chính nếu còn cần so sánh, tính toán và index.

Các DBMS khác có hàm riêng: SQL Server `FORMAT`, Oracle `TO_CHAR`, MySQL `DATE_FORMAT`, SQLite `strftime`. Quy tắc:

- Lưu bằng kiểu temporal/representation chuẩn.
- Truyền tham số có kiểu từ driver.
- Chỉ format ở lớp trình bày hoặc ranh giới báo cáo.
- Không parse ngày mơ hồ phụ thuộc locale.
- Dùng ISO 8601 khi trao đổi giữa hệ thống.

## 32. NULL trong dữ liệu thời gian

NULL có thể có nhiều ý nghĩa: chưa biết thời điểm, không áp dụng, chưa xác nhận, chưa kết thúc hoặc thiếu dữ liệu từ nguồn. Không thay NULL bằng `1970-01-01` hay `1900-01-01` nếu không có quy tắc nghiệp vụ rõ; sentinel date có thể bị hiểu thành sự kiện thật.

Ví dụ sự kiện đang mở:

```sql
CREATE TABLE subscriptions (
    subscription_id BIGINT PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    CHECK (ended_at IS NULL OR ended_at >= started_at)
);
```

`ended_at IS NULL` nghĩa là chưa có thời điểm kết thúc theo hợp đồng. Để lọc subscription còn hiệu lực tại mốc tham chiếu, có thể dùng:

```sql
started_at <= :as_of
AND (ended_at IS NULL OR ended_at > :as_of)
```

Cần định nghĩa rõ đầu/cuối khoảng có inclusive hay exclusive.

## 33. Khoảng thời gian chồng lấn

Với khoảng nửa mở `[start, end)`, hai khoảng A và B chồng nhau khi:

```text
A.start < B.end
AND
B.start < A.end
```

SQL:

```sql
SELECT a.booking_id, b.booking_id
FROM bookings AS a
JOIN bookings AS b
  ON a.booking_id < b.booking_id
 AND a.start_at < b.end_at
 AND b.start_at < a.end_at;
```

Booking kết thúc lúc 10:00 và booking tiếp theo bắt đầu đúng 10:00 không bị coi là chồng lấn. PostgreSQL có thể dùng range type và exclusion constraint để bảo vệ một số quy tắc không chồng lấn. Nếu chỉ SELECT kiểm tra trước INSERT, nhiều transaction đồng thời vẫn có thể tạo race condition; cần constraint/khóa/isolation phù hợp.

## 34. Thời gian làm việc và ngày nghỉ

Quy tắc “xử lý trong 8 giờ làm việc” khác “xử lý trong 8 giờ liên tục”. Ví dụ lịch làm việc:

- Thứ Hai–Thứ Sáu.
- 08:30–12:00 và 13:00–17:30.
- Không tính ngày lễ.
- Zone theo địa điểm của bộ phận xử lý.

Có thể cần bảng `business_calendars`, `business_calendar_days`, `business_hours` và `holidays`. Khi tính SLA, chia khoảng sự kiện thành phần giao với các khoảng làm việc rồi cộng thời lượng giao nhau. Phép trừ timestamp đơn giản sẽ tính cả đêm, cuối tuần và giờ nghỉ.

Nếu quy tắc lịch phức tạp, đóng gói logic ở service/domain layer hoặc hàm được kiểm thử kỹ, thay vì cố viết một biểu thức SQL ngắn khó kiểm chứng.

## 35. Schema thực hành PostgreSQL

Tạo schema học tập `sql405` để thử instant, local schedule và duration. Chỉ chạy trong database thử nghiệm:

```sql
CREATE SCHEMA sql405;

CREATE TABLE sql405.event_log (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_type TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    source_zone TEXT,
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_sql405_event_log_occurred
ON sql405.event_log(occurred_at);

CREATE TABLE sql405.appointments (
    appointment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    local_start TIMESTAMP NOT NULL,
    zone_name TEXT NOT NULL,
    resolved_start TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'SCHEDULED'
        CHECK (status IN ('SCHEDULED', 'CANCELLED', 'DONE'))
);

CREATE TABLE sql405.job_runs (
    run_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    CHECK (finished_at IS NULL OR finished_at >= started_at)
);
```

Ý nghĩa:

- `event_log.occurred_at`: instant của sự kiện.
- `source_zone`: zone nguồn nếu cần biết nơi tạo sự kiện.
- `received_at`: thời điểm database nhận/ghi bản ghi.
- `appointments.local_start` + `zone_name`: ý định giờ địa phương.
- `resolved_start`: instant đã được giải quyết theo zone và chính sách.
- `job_runs.started_at`/`finished_at`: mốc bắt đầu/kết thúc; finish NULL nghĩa job chưa hoàn tất.

Hệ thật có thể cần danh mục timezone ID, trạng thái giải quyết DST, version tzdata và khóa idempotency.

## 36. Chèn và chuyển đổi dữ liệu thử nghiệm

### 36.1. Ghi instant

```sql
INSERT INTO sql405.event_log (
    event_type, occurred_at, source_zone
)
VALUES (
    'PAYMENT_CONFIRMED',
    TIMESTAMPTZ '2026-11-14 09:30:00+07',
    'Asia/Ho_Chi_Minh'
)
RETURNING event_id, occurred_at;
```

Giá trị lưu là instant. `source_zone` là thông tin nghiệp vụ bổ sung; PostgreSQL không tự suy ra nó từ timestamptz.

### 36.2. So sánh cùng instant

```sql
SELECT
    TIMESTAMPTZ '2026-11-14 09:30:00+07'
    =
    TIMESTAMPTZ '2026-11-14 02:30:00+00'
    AS same_instant;
```

Kết quả TRUE.

### 36.3. Lưu lịch hẹn địa phương

```sql
INSERT INTO sql405.appointments (
    local_start, zone_name, resolved_start
)
VALUES (
    TIMESTAMP '2026-11-15 10:00:00',
    'Asia/Ho_Chi_Minh',
    TIMESTAMP '2026-11-15 10:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
)
RETURNING *;
```

Local datetime giữ ý định “10:00 giờ địa phương”; resolved_start lưu instant theo zone. Với vùng có DST, cần kiểm tra ambiguous/nonexistent local time trước khi ghi theo chính sách ứng dụng.

### 36.4. Tính duration job

```sql
INSERT INTO sql405.job_runs (started_at, finished_at)
VALUES (
    TIMESTAMPTZ '2026-11-14 02:00:00+00',
    TIMESTAMPTZ '2026-11-14 02:03:45+00'
);

SELECT
    run_id,
    finished_at - started_at AS elapsed_interval,
    EXTRACT(EPOCH FROM (finished_at - started_at))
        AS elapsed_seconds
FROM sql405.job_runs;
```

Kỳ vọng 225 giây. Nếu job chưa xong và `finished_at` NULL, không tính duration hoàn chỉnh; có thể đo tới mốc tham chiếu bằng `COALESCE(finished_at, clock_timestamp())` theo hợp đồng báo cáo.

## 37. Báo cáo theo ngày địa phương và index

Truy vấn event của ngày 14/11/2026 tại Việt Nam:

```sql
WITH bounds AS (
    SELECT
        (DATE '2026-11-14'::timestamp
            AT TIME ZONE 'Asia/Ho_Chi_Minh') AS start_at,
        ((DATE '2026-11-14' + 1)::timestamp
            AT TIME ZONE 'Asia/Ho_Chi_Minh') AS end_at
)
SELECT e.event_id, e.event_type, e.occurred_at
FROM sql405.event_log AS e
CROSS JOIN bounds AS b
WHERE e.occurred_at >= b.start_at
  AND e.occurred_at < b.end_at
ORDER BY e.occurred_at;
```

Câu truy vấn lọc trực tiếp trên `occurred_at`, tận dụng khả năng dùng index range. Có thể kiểm tra kế hoạch:

```sql
EXPLAIN (ANALYZE, BUFFERS)
WITH bounds AS (
    SELECT
        (DATE '2026-11-14'::timestamp
            AT TIME ZONE 'Asia/Ho_Chi_Minh') AS start_at,
        ((DATE '2026-11-14' + 1)::timestamp
            AT TIME ZONE 'Asia/Ho_Chi_Minh') AS end_at
)
SELECT event_id
FROM sql405.event_log AS e
CROSS JOIN bounds AS b
WHERE e.occurred_at >= b.start_at
  AND e.occurred_at < b.end_at;
```

Bảng lab ít dòng nên planner có thể chọn sequential scan. Điều đó không chứng minh index vô ích; cần dữ liệu đủ lớn và selectivity đại diện.

## 38. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| Lưu instant vào timestamp không timezone mà không quy ước | Không biết giờ thuộc zone nào | Dùng kiểu instant hoặc quy ước UTC rõ |
| Lưu offset thay zone ID cho lịch lặp | Không theo quy tắc DST tương lai | Lưu zone ID và local schedule |
| Coi một ngày bằng 24 giờ | Lệch khi qua DST | Phân biệt ngày lịch và elapsed duration |
| Coi một tháng bằng 30 ngày | Sai hạn hợp đồng/tháng | Dùng phép cộng tháng lịch |
| Dùng BETWEEN với cuối ngày 23:59:59 | Bỏ sót phần lẻ giây | Khoảng nửa mở |
| CAST cột timestamp trong WHERE | Có thể giảm khả năng dùng index | Tính boundary rồi lọc cột trực tiếp |
| Dùng DATEDIFF đo elapsed time | Đếm ranh giới theo semantics DBMS | Trừ hai instant hoặc đo duration rõ |
| Dùng Oracle DATE như date-only | Phần giờ vẫn có thể tồn tại | Enforce midnight hoặc chọn model khác |
| Dùng MySQL DATETIME như instant | Không tự chuyển timezone session | Chọn TIMESTAMP/UTC convention |
| Trộn TEXT/epoch seconds/epoch milliseconds trong SQLite | Tính sai đơn vị | Một representation nhất quán |
| Chỉ lưu timestamptz nhưng cần biết zone người dùng | Không khôi phục zone gốc | Lưu zone ID riêng |
| Dùng timestamp làm khóa duy nhất | Có thể trùng hoặc sai thứ tự | ID/sequence/tie-breaker |
| Dùng phép trừ cho SLA ngày làm việc | Tính cả đêm/ngày nghỉ | Calendar/business-hours model |

## 39. Kiểm thử ngày giờ và múi giờ

Bộ test cần bao phủ:

1. Cuối năm chuyển sang đầu năm.
2. Ngày cuối tháng và tháng 2 năm nhuận.
3. Cộng một tháng từ ngày 29, 30, 31.
4. Timestamp đúng nửa đêm.
5. Hai sự kiện có timestamp bằng nhau.
6. Ngày bắt đầu/kết thúc DST.
7. Giờ địa phương không tồn tại và xuất hiện hai lần.
8. Offset có phút lẻ như `+05:30`.
9. Cùng instant với hai offset khác nhau.
10. Session timezone thay đổi.
11. Transaction kéo dài khi dùng CURRENT_TIMESTAMP.
12. Fractional seconds ở precision đầu vào và cột đích.
13. NULL start/end.
14. Khoảng thời gian bằng nhau, liền kề và chồng lấn.
15. Ngày lễ/giờ làm việc theo zone.
16. Tzdata update làm thay đổi lịch tương lai.
17. Driver serialize/deserialize đúng kiểu.
18. Chuyển DBMS không làm mất zone/precision.

Đặc biệt, kiểm thử ngày chuyển DST của zone thật, dùng timezone database được cập nhật và ghi lại zone ID/version khi kết quả phụ thuộc vào quy tắc đó.

## 40. Bài tập thực hành

### Bài 1 — Phân loại dữ liệu

Chọn DATE, TIME, local timestamp hay instant cho: ngày sinh; cửa hàng mở lúc 08:00; thời điểm thanh toán xác nhận; cuộc hẹn 09:30 tại địa điểm cụ thể; thời lượng job 12 phút. Giải thích vì sao một cột timestamp không đại diện tốt cho tất cả.

### Bài 2 — Instant tương đương

Hai giá trị `2026-11-14 09:30:00+07` và `2026-11-14 02:30:00+00` có cùng instant không? Viết phép so sánh PostgreSQL.

### Bài 3 — AT TIME ZONE

Giải thích kiểu kết quả của:

```sql
TIMESTAMP '2026-11-14 09:30:00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh'

TIMESTAMPTZ '2026-11-14 02:30:00+00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh'
```

### Bài 4 — Current timestamp

Trong transaction PostgreSQL có hai SELECT cách nhau 5 giây, so sánh CURRENT_TIMESTAMP, statement_timestamp() và clock_timestamp(). Hàm nào giữ nguyên trong transaction?

### Bài 5 — Duration và calendar

Vì sao cộng INTERVAL '1 day' có thể khác INTERVAL '24 hours' khi cộng vào timestamptz ở vùng có DST?

### Bài 6 — Tháng lịch

Ngày 31/01/2024 cộng một tháng có nhất thiết thành ngày 30/02 không? Vì sao cần quy tắc cuối tháng?

### Bài 7 — Lọc ngày UTC

Viết điều kiện lấy toàn bộ event ngày 14/11/2026 bằng khoảng nửa mở. Vì sao tránh BETWEEN 00:00 và 23:59:59?

### Bài 8 — Ngày địa phương

Viết PostgreSQL query lấy sự kiện ngày 14/11/2026 tại Asia/Ho_Chi_Minh với occurred_at TIMESTAMPTZ.

### Bài 9 — Index

Vì sao WHERE occurred_at::date = DATE '2026-11-14' có thể không tận dụng index timestamp như điều kiện range? Nêu cách thay thế.

### Bài 10 — Oracle DATE

Vì sao Oracle DATE không tương đương PostgreSQL DATE? Khi dùng Oracle DATE cho ngày sinh, cần quy ước gì?

### Bài 11 — SQL Server DATEDIFF

Vì sao hai timestamp chỉ cách nhau 0,2 giây nhưng qua nửa đêm có thể cho DATEDIFF(day, ...) = 1?

### Bài 12 — MySQL TIMESTAMP và DATETIME

So sánh chuyển đổi timezone của TIMESTAMP và DATETIME. Khi nào nên dùng từng loại?

### Bài 13 — SQLite

Nêu ba representation ngày giờ SQLite và hàm tính chênh lệch ngày dựa trên julianday.

### Bài 14 — Lịch lặp

Một job chạy 08:30 mỗi ngày theo giờ địa phương New York. Nên lưu những trường nào? Vì sao không chỉ lưu instant UTC cho lần đầu?

### Bài 15 — DST ambiguous

Người dùng đặt cuộc hẹn 01:30 vào ngày đồng hồ lùi một giờ. Vì sao có thể có hai instant? Hệ thống nên áp dụng chính sách gì?

### Bài 16 — SLA ngày làm việc

SLA là 8 giờ làm việc, thứ Hai–thứ Sáu 08:30–17:30, nghỉ trưa 12:00–13:00. Vì sao phép trừ hai timestamp không đủ? Cần dữ liệu gì?

### Bài 17 — Khoảng chồng lấn

Viết điều kiện để hai khoảng nửa mở [start, end) chồng lấn. Vì sao hai booking liền kề không bị coi là chồng lấn?

### Bài 18 — Chuyển DBMS

Khi chuyển PostgreSQL sang SQL Server, nêu ít nhất bốn điểm cần xem lại về kiểu timestamp, timezone, DATEDIFF và precision.

## 41. Gợi ý đáp án

**Bài 1.** Ngày sinh dùng DATE; giờ mở cửa dùng TIME cùng zone cửa hàng; thanh toán dùng instant; cuộc hẹn dùng local datetime + zone ID và có thể thêm instant đã giải quyết; thời lượng dùng interval hoặc số đơn vị chuẩn. Mỗi loại mang semantics khác nhau.

**Bài 2.** Có cùng instant:

```sql
SELECT
    TIMESTAMPTZ '2026-11-14 09:30:00+07'
    =
    TIMESTAMPTZ '2026-11-14 02:30:00+00';
```

Kết quả TRUE.

**Bài 3.** Vế đầu nhận timestamp không zone, diễn giải theo Asia/Ho_Chi_Minh và trả timestamptz. Vế hai nhận instant và trả timestamp không zone biểu diễn giờ địa phương trong zone.

**Bài 4.** CURRENT_TIMESTAMP/now() giữ mốc bắt đầu transaction; statement_timestamp() thay theo statement; clock_timestamp() phản ánh đồng hồ lúc gọi.

**Bài 5.** Một ngày lịch giữ giờ địa phương ở ngày kế tiếp, còn 24 giờ là duration cố định. Khi DST làm ngày dài 23 hoặc 25 giờ, kết quả instant có thể khác.

**Bài 6.** Không. DBMS áp dụng quy tắc tháng lịch, thường điều chỉnh về ngày cuối tháng đích khi ngày tương ứng không tồn tại.

**Bài 7.**

```sql
WHERE occurred_at >= TIMESTAMPTZ '2026-11-14 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-11-15 00:00:00+00'
```

Khoảng nửa mở không phụ thuộc precision và không bỏ sót phần lẻ giây.

**Bài 8.**

```sql
WITH bounds AS (
    SELECT
        (DATE '2026-11-14'::timestamp
            AT TIME ZONE 'Asia/Ho_Chi_Minh') AS start_at,
        ((DATE '2026-11-14' + 1)::timestamp
            AT TIME ZONE 'Asia/Ho_Chi_Minh') AS end_at
)
SELECT e.*
FROM app.events AS e
CROSS JOIN bounds AS b
WHERE e.occurred_at >= b.start_at
  AND e.occurred_at < b.end_at;
```

**Bài 9.** CAST/hàm trên cột có thể khiến index thông thường khó dùng trực tiếp. Tính start/end trước rồi so sánh cột với hai bound.

**Bài 10.** Oracle DATE lưu cả giờ, phút, giây; PostgreSQL DATE chỉ là ngày lịch. Với ngày sinh, quy ước giờ luôn midnight hoặc enforce bằng constraint/ứng dụng.

**Bài 11.** DATEDIFF SQL Server đếm ranh giới ngày đã đi qua, không đo elapsed 24 giờ. Qua nửa đêm là số ranh giới ngày tăng 1.

**Bài 12.** MySQL TIMESTAMP chuyển đổi theo session timezone và UTC khi lưu/đọc; DATETIME giữ ngày giờ như nhập, không tự chuyển tương tự. TIMESTAMP phù hợp instant theo chính sách session; DATETIME phù hợp local datetime hoặc quy ước đã xác định.

**Bài 13.** TEXT ISO 8601, REAL Julian day, INTEGER Unix epoch. Ví dụ:

```sql
SELECT julianday('2026-11-14') - julianday('2026-11-01');
```

**Bài 14.** Lưu local_time 08:30, zone ID America/New_York, recurrence rule và start date; có thể lưu resolved instant lần kế tiếp. Instant đầu không đại diện tất cả lần chạy tương lai khi DST đổi.

**Bài 15.** Khi đồng hồ lùi, cùng local time xuất hiện hai lần với hai offset khác nhau. Yêu cầu chọn occurrence/offset hoặc áp dụng chính sách công bố rõ.

**Bài 16.** Phép trừ tính cả đêm, cuối tuần và giờ nghỉ. Cần calendar, zone, ngày làm việc, khoảng giờ làm, ngày lễ và quy tắc bắt đầu/kết thúc ngoài giờ.

**Bài 17.**

```sql
a.start_at < b.end_at
AND b.start_at < a.end_at
```

Nếu A kết thúc đúng lúc B bắt đầu, một điều kiện strict < không thỏa, nên hai khoảng liền kề không chồng lấn.

**Bài 18.** Xem lại timestamp without/with zone sang datetime2/datetimeoffset; tên IANA so với Windows zone; semantics AT TIME ZONE; DATEDIFF đếm boundary; precision datetime2; cách driver truyền offset; quy tắc DST và session timezone.

## 42. Dọn dữ liệu thực hành

Sau khi hoàn thành và xác nhận schema `sql405` chỉ chứa đối tượng của bài học, có thể xóa trong database thử nghiệm:

```sql
-- PostgreSQL: chỉ chạy trong database học tập đã xác nhận.
DROP SCHEMA sql405 CASCADE;
```

Lệnh này xóa các bảng, index và đối tượng phụ thuộc theo quy tắc PostgreSQL. Không chạy trên schema dùng chung hoặc production khi chưa kiểm tra dependency.

## 43. Kết luận

Thiết kế thời gian đúng bắt đầu từ việc phân biệt **ngày lịch, giờ địa phương, instant và duration**. Dùng DATE cho ngày lịch; TIME cho giờ trong ngày; kiểu timestamp phù hợp với local datetime hoặc instant; lưu zone ID riêng khi cần quy tắc địa lý; dùng interval hoặc số đơn vị chuẩn cho duration theo định nghĩa rõ ràng.

Khi tính toán, phân biệt **ngày lịch với 24 giờ**, **tháng lịch với 30 ngày**, **số ranh giới đơn vị với elapsed time**, và **giờ hiển thị với instant**. Với truy vấn theo ngày, ưu tiên khoảng nửa mở `[start, next_start)`; khi báo cáo theo ngày địa phương, chuyển hai ranh giới lịch địa phương thành instant theo zone. Điều này vừa đúng semantics vừa giúp index trên timestamp có thể được sử dụng.

Mỗi DBMS có kiểu và hàm riêng: PostgreSQL `timestamptz`/`AT TIME ZONE`/`INTERVAL`; SQL Server `datetime2`/`datetimeoffset`/`DATEADD`/`DATEDIFF`; Oracle `DATE`/`TIMESTAMP WITH TIME ZONE`/`INTERVAL`; MySQL/MariaDB `DATETIME`/`TIMESTAMP`/`CONVERT_TZ`; SQLite TEXT/REAL/INTEGER và date functions. Khi chuyển hệ, giữ nguyên **định nghĩa nghiệp vụ** và kiểm thử DST, precision, session timezone, ngày cuối tháng và ranh giới khoảng thay vì chỉ thay tên hàm SQL.

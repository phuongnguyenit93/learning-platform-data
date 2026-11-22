# Hàm thời gian, date_trunc, extract và chuyển múi giờ trong PostgreSQL

## 1. Mục tiêu và bài toán thực tế

Thời gian xuất hiện ở hầu hết hệ thống: lúc đơn hàng được tạo, phiên đăng nhập bắt đầu, giao dịch thanh toán thành công, thời điểm khóa sổ, lịch hẹn, thời hạn xử lý và dữ liệu báo cáo theo ngày/tháng. Những bài toán tưởng như đơn giản có thể sai nếu nhầm **mốc thời gian tuyệt đối**, **giờ địa phương** và **ngày trên lịch**.

Ví dụ một giao dịch xảy ra lúc:

~~~text
UTC:             2026-11-13 17:30:00+00
Việt Nam (UTC+7): 2026-11-14 00:30:00+07
~~~

Đây là **cùng một thời điểm**, nhưng thuộc **hai ngày khác nhau** tùy múi giờ báo cáo. Nếu hệ thống thống kê số giao dịch ngày 14/11 theo lịch Việt Nam nhưng lấy ngày UTC, một phần doanh số có thể bị tính sang ngày khác.

Trong PostgreSQL, nhóm công cụ cần nắm gồm:

- **Kiểu dữ liệu** `date`, `time`, `timestamp`, `timestamptz`, `interval`.
- **Thời điểm hiện tại:** `CURRENT_DATE`, `CURRENT_TIMESTAMP`, `now()`, `statement_timestamp()`, `clock_timestamp()`.
- **Cắt thời gian về mốc lịch:** `date_trunc`.
- **Lấy thành phần và thông tin lịch:** `EXTRACT`, `date_part`.
- **Chuyển múi giờ:** `AT TIME ZONE`, `timezone(...)`, tham số phiên `TimeZone`.
- **Các thao tác bổ trợ:** cộng/trừ `INTERVAL`, `age`, `generate_series`, `date_bin`, `to_char`.

Sau bài học, bạn có thể:

1. Phân biệt `timestamp without time zone` và `timestamp with time zone`, biết chọn kiểu lưu trữ đúng.
2. Dùng `date_trunc` để nhóm theo giờ/ngày/tuần/tháng/quý/năm.
3. Dùng `EXTRACT` để lấy năm, tháng, thứ, tuần ISO và epoch.
4. Chuyển đúng giữa **mốc tuyệt đối** và **giờ địa phương** bằng `AT TIME ZONE`.
5. Xây dựng báo cáo theo **ngày địa phương**, kể cả nơi có đổi giờ mùa hè (DST).
6. Lọc theo khoảng thời gian có khả năng tận dụng index B-tree.
7. Tránh lỗi do mặc định session timezone, cast sai kiểu, ngày cuối tháng và tuần ISO.
8. Thực hành các truy vấn với dữ liệu mẫu và giải bài tập.

> Các lệnh tạo/nạp dữ liệu chỉ chạy ở database thực hành được phép. Với production, luôn xác định múi giờ nghiệp vụ, quy tắc báo cáo và chi phí truy vấn trước khi thay đổi SQL, schema hoặc index.

---

## 2. Phân biệt thời điểm, giờ địa phương và khoảng thời gian

Ba khái niệm cần tách biệt:

1. **Instant (thời điểm):** một điểm trên trục thời gian chung, ví dụ `2026-11-13 17:30:00 UTC`.
2. **Local date-time (ngày-giờ địa phương):** cách đọc lịch/đồng hồ ở một vùng, ví dụ `2026-11-14 00:30:00` tại Việt Nam.
3. **Duration/interval (khoảng thời gian):** phần thời gian chênh giữa các mốc hoặc một khoảng lịch như một tháng, một ngày.

Cùng một instant có thể có nhiều cách hiển thị:

~~~text
                         CÙNG MỘT INSTANT
                         2026-11-13 17:30 UTC
                                |
          +---------------------+---------------------+
          |                     |                     |
          v                     v                     v
        UTC                 Việt Nam             New York
   13/11 17:30             14/11 00:30      Ngày/giờ theo quy tắc
                                             múi giờ ở thời điểm đó
~~~

**Một ngày trên lịch địa phương không phải lúc nào dài đúng 24 giờ**, đặc biệt ở những vùng có DST. Vì vậy phải quyết định liệu nghiệp vụ đang hỏi "24 giờ vừa qua" hay "ngày hôm qua theo lịch New York".

## 3. Kiểu dữ liệu thời gian PostgreSQL

| Kiểu | Ví dụ | Ý nghĩa chính |
|---|---|---|
| `DATE` | `2026-11-14` | Ngày lịch, không chứa giờ |
| `TIME WITHOUT TIME ZONE` | `09:30:00` | Giờ trên đồng hồ, không gắn ngày/múi giờ |
| `TIME WITH TIME ZONE` / `TIMETZ` | `09:30:00+07` | Giờ và offset, thường không phù hợp cho lịch hẹn theo vùng vì thiếu ngày |
| `TIMESTAMP WITHOUT TIME ZONE` | `2026-11-14 09:30:00` | Ngày-giờ thuần, không xác định múi giờ |
| `TIMESTAMP WITH TIME ZONE` / `TIMESTAMPTZ` | `2026-11-14 09:30:00+07` | Một thời điểm tuyệt đối được diễn giải từ input có zone/offset |
| `INTERVAL` | `2 days 3 hours` | Một lượng thời gian/lịch có thể gồm tháng, ngày và phần giờ |

### 3.1. TIMESTAMP không tự mang múi giờ

~~~sql
SELECT TIMESTAMP '2026-11-14 09:30:00' AS local_datetime;
~~~

Kiểu trả về là `timestamp without time zone`. Giá trị `09:30` chưa nói "09:30 ở Hà Nội", "09:30 UTC" hay "09:30 ở New York".

Một lỗi nguy hiểm:

~~~sql
SELECT TIMESTAMP '2026-11-14 09:30:00+07';
~~~

Vì đã khai báo **TIMESTAMP không có múi giờ**, phần offset trong chuỗi đầu vào không được dùng để chuyển instant theo ý định mà nhiều người tưởng. Nếu đầu vào chứa offset và bạn muốn lưu **một instant**, cần khai báo `TIMESTAMPTZ` đúng kiểu.

### 3.2. TIMESTAMPTZ thể hiện một instant

~~~sql
SELECT TIMESTAMPTZ '2026-11-14 09:30:00+07' AS instant_value;
~~~

Mốc đó tương ứng:

~~~text
2026-11-14 02:30:00+00 (UTC)
2026-11-14 09:30:00+07 (Việt Nam)
~~~

PostgreSQL chuẩn hóa `timestamptz` để biểu diễn instant; **không giữ nguyên tên múi giờ/offset gốc của người gửi** như một thuộc tính của giá trị. Khi đọc, PostgreSQL trình bày instant theo **TimeZone của phiên**, hoặc theo phép chuyển múi giờ được chỉ định.

Ví dụ:

~~~sql
BEGIN;
SET LOCAL TimeZone = 'UTC';

SELECT TIMESTAMPTZ '2026-11-14 09:30:00+07' AS instant_value;

ROLLBACK;
~~~

Trong phiên đang hiển thị UTC, kết quả thể hiện khoảng `02:30+00`. Cùng instant đó có thể hiển thị `09:30+07` trong phiên dùng `Asia/Ho_Chi_Minh`.

### 3.3. Nên dùng kiểu nào?

- `created_at`, `paid_at`, `last_login_at`, `event_occurred_at`: thường dùng **TIMESTAMPTZ**, vì chúng mô tả một instant.
- `birth_date`, `holiday_date`: **DATE**, không cần instant hay offset.
- `store_opens_at` kiểu "mỗi ngày mở lúc 09:00 theo giờ địa phương": có thể dùng **TIME**, nhưng cần biết vùng hoặc địa điểm áp dụng.
- `appointment_local` khi người dùng đặt 09:30 vào một ngày tương lai: cần giữ **ngày-giờ địa phương và tên múi giờ** hoặc bảo đảm có thể tái dựng ý định lịch hẹn khi quy tắc DST thay đổi.
- `duration`, `billing_period`: cần phân biệt **khoảng thời gian thực** và **khoảng lịch**, thường dùng INTERVAL kèm quy tắc rõ.

Không chọn `timestamp` chỉ vì tên ngắn hơn `timestamptz`. Hãy hỏi: "Dữ liệu biểu diễn một **instant** hay một **giờ trên lịch không gắn zone**?"

### 3.4. TIMETZ không thay thế tên vùng

`TIME WITH TIME ZONE` lưu giờ và offset, nhưng thiếu ngày để xác định DST của một vùng tên như `America/New_York` tại các ngày khác nhau. Lịch hẹn lặp theo vùng cần **tên vùng IANA** và ngày áp dụng, không chỉ một offset `-05:00` cố định.

---

## 4. Cấu hình TimeZone của phiên và cách xem

~~~sql
SHOW TIME ZONE;
~~~

Hoặc:

~~~sql
SELECT current_setting('TimeZone') AS session_timezone;
~~~

Trong lab có thể đổi timezone chỉ trong một transaction:

~~~sql
BEGIN;
SET LOCAL TimeZone = 'Asia/Ho_Chi_Minh';

SELECT
    current_setting('TimeZone') AS timezone_name,
    TIMESTAMPTZ '2026-11-14 02:30:00+00' AS instant_value;

ROLLBACK;
~~~

Kết quả instant được hiển thị theo `Asia/Ho_Chi_Minh`, tương ứng `09:30+07`.

Một phiên dùng timezone khác **không làm thay đổi instant đã lưu**; nó chỉ thay đổi cách hiển thị và một số phép toán lịch, ví dụ:

- Cast `timestamptz` sang `date` hoặc `timestamp`.
- `date_trunc('day', value_timestamptz)` khi không ghi rõ timezone.
- `EXTRACT(hour FROM value_timestamptz)`.
- `CURRENT_DATE`.

**Connection pool:** không dựa vào việc một request trước đã SET timezone rồi session được tái sử dụng. Cần có chính sách session nhất quán hoặc đặt tên timezone tường minh trong truy vấn để tránh rò rỉ cấu hình giữa các request.

### 4.1. UTC và offset cố định không đồng nghĩa tên múi giờ

`UTC` là một hệ quy chiếu thời gian. Một offset như `+07:00` là chênh lệch **tại một thời điểm**, còn tên `Asia/Ho_Chi_Minh` là vùng với quy tắc thời gian theo cơ sở dữ liệu múi giờ IANA.

Với các vùng có DST, ví dụ `America/New_York`, offset có thể thay đổi theo ngày. Vì vậy không áp dụng `-05:00` cố định cho mọi thời điểm ở New York.

---

## 5. Các hàm lấy thời điểm hiện tại

### 5.1. CURRENT_TIMESTAMP, now và transaction_timestamp

~~~sql
SELECT
    CURRENT_TIMESTAMP AS current_ts,
    now() AS now_ts,
    transaction_timestamp() AS transaction_ts;
~~~

Trong PostgreSQL, ba biểu thức trên biểu diễn **thời điểm bắt đầu transaction hiện tại**. Chúng không chạy lại đồng hồ sau mỗi hàng được xử lý.

Ví dụ:

~~~sql
BEGIN;

SELECT now() AS first_read;

-- Nếu có thao tác xử lý trong transaction...

SELECT now() AS second_read;

ROLLBACK;
~~~

Hai kết quả `now()` trong cùng transaction có cùng giá trị, không phải hai thời điểm đọc khác nhau.

Đây là đặc điểm hữu ích cho audit: nhiều hàng được tạo trong một transaction có thể dùng chung timestamp nhất quán.

### 5.2. statement_timestamp

~~~sql
SELECT statement_timestamp();
~~~

Hàm này lấy **thời điểm bắt đầu câu lệnh SQL hiện tại**. Trong một transaction có nhiều statement, giá trị có thể thay đổi giữa các statement, không cố định theo đầu transaction như `now()`.

### 5.3. clock_timestamp

~~~sql
SELECT clock_timestamp();
~~~

Hàm này đọc đồng hồ thực tế tại thời điểm gọi. Nó có thể **thay đổi ngay trong cùng một statement**, đặc biệt trong truy vấn chạy lâu.

| Biểu thức | Mốc thời gian |
|---|---|
| `now()` | Đầu transaction |
| `CURRENT_TIMESTAMP` | Đầu transaction |
| `transaction_timestamp()` | Đầu transaction |
| `statement_timestamp()` | Đầu statement |
| `clock_timestamp()` | Đồng hồ tại thời điểm gọi |

Khi tạo `created_at DEFAULT now()`, transaction timestamp thường là lựa chọn tự nhiên. Khi đo **thời gian thực trôi qua** trong một thao tác, có thể cần `clock_timestamp()`, nhưng phải dùng công cụ đo phù hợp và không hiểu nhầm thời gian transaction.

### 5.4. CURRENT_DATE và LOCALTIMESTAMP

~~~sql
SELECT
    CURRENT_DATE AS today,
    CURRENT_TIME AS current_time_with_zone,
    LOCALTIMESTAMP AS local_datetime,
    LOCALTIME AS local_clock_time;
~~~

- `CURRENT_DATE` là ngày theo lịch **TimeZone của phiên** ở thời điểm tham chiếu transaction.
- `LOCALTIMESTAMP` là `timestamp without time zone` của giờ địa phương theo phiên.
- `LOCALTIME` là `time without time zone`.
- `CURRENT_TIME` mang timezone offset theo semantics của kiểu time with time zone.

Khi gọi API, không truyền một `LOCALTIMESTAMP` như instant UTC nếu chưa gắn timezone đúng.

### 5.5. Giá trị hiện tại có độ chính xác tùy chọn

PostgreSQL có cú pháp như:

~~~sql
SELECT CURRENT_TIMESTAMP(3) AS current_ts_milliseconds;
~~~

Tham số precision kiểm soát số chữ số phần giây được hiển thị/làm tròn theo kiểu, không thay đổi quy tắc transaction timestamp.

---

## 6. Tạo bộ dữ liệu có mốc UTC và giờ Việt Nam

Tạo bảng sự kiện:

~~~sql
CREATE SCHEMA IF NOT EXISTS time_lab;

CREATE TABLE time_lab.events (
    event_id BIGINT PRIMARY KEY,
    event_type TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    amount NUMERIC(12,2) NOT NULL DEFAULT 0
        CHECK (amount >= 0),
    notes TEXT
);
~~~

Nạp tám sự kiện có thời gian rõ UTC:

~~~sql
INSERT INTO time_lab.events
    (event_id, event_type, occurred_at, amount, notes)
VALUES
    (1, 'purchase', TIMESTAMPTZ '2026-11-13 16:59:00+00',
        100, '23:59 ngày 13 tại Việt Nam'),
    (2, 'purchase', TIMESTAMPTZ '2026-11-13 17:00:00+00',
        200, '00:00 ngày 14 tại Việt Nam'),
    (3, 'purchase', TIMESTAMPTZ '2026-11-14 00:30:00+00',
        300, '07:30 ngày 14 tại Việt Nam'),
    (4, 'refund', TIMESTAMPTZ '2026-11-14 12:10:00+00',
        150, '19:10 ngày 14 tại Việt Nam'),
    (5, 'purchase', TIMESTAMPTZ '2026-11-14 17:00:00+00',
        500, '00:00 ngày 15 tại Việt Nam'),
    (6, 'purchase', TIMESTAMPTZ '2026-10-31 17:00:00+00',
        600, '00:00 ngày 01/11 tại Việt Nam'),
    (7, 'purchase', TIMESTAMPTZ '2026-12-31 16:59:00+00',
        700, '23:59 ngày 31/12 tại Việt Nam'),
    (8, 'purchase', TIMESTAMPTZ '2026-12-31 17:00:00+00',
        800, '00:00 ngày 01/01/2027 tại Việt Nam');
~~~

Chỉ nạp một lần trên bảng trống của lab, vì `event_id` là primary key.

Kiểm tra:

~~~sql
SELECT COUNT(*) AS total_events
FROM time_lab.events;
~~~

Kỳ vọng **8** dòng.

### 6.1. Cùng một instant, hai giờ địa phương

~~~sql
SELECT
    event_id,
    occurred_at AT TIME ZONE 'UTC' AS utc_clock,
    occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh' AS vn_clock
FROM time_lab.events
WHERE event_id IN (1, 2, 3, 5)
ORDER BY event_id;
~~~

| event_id | utc_clock | vn_clock |
|---:|---|---|
| 1 | 2026-11-13 16:59 | 2026-11-13 23:59 |
| 2 | 2026-11-13 17:00 | 2026-11-14 00:00 |
| 3 | 2026-11-14 00:30 | 2026-11-14 07:30 |
| 5 | 2026-11-14 17:00 | 2026-11-15 00:00 |

Kết quả `AT TIME ZONE` khi đầu vào là `timestamptz` có kiểu `timestamp without time zone`: một **giờ địa phương được biểu diễn bằng các thành phần lịch/đồng hồ**, không còn là instant kèm timezone ở chính giá trị trả về.

---

## 7. Hàm date_trunc: cắt đến đầu đơn vị thời gian

`date_trunc` cắt các thành phần nhỏ hơn đơn vị được chọn về mốc đầu đơn vị tương ứng:

~~~sql
date_trunc('unit', temporal_value)
~~~

Ví dụ trên timestamp không có timezone:

~~~sql
SELECT
    date_trunc('hour',   TIMESTAMP '2026-11-14 15:42:37.123') AS by_hour,
    date_trunc('day',    TIMESTAMP '2026-11-14 15:42:37.123') AS by_day,
    date_trunc('month',  TIMESTAMP '2026-11-14 15:42:37.123') AS by_month,
    date_trunc('year',   TIMESTAMP '2026-11-14 15:42:37.123') AS by_year;
~~~

Kết quả ý nghĩa:

| Đơn vị | Mốc trả về |
|---|---|
| hour | 2026-11-14 15:00:00 |
| day | 2026-11-14 00:00:00 |
| month | 2026-11-01 00:00:00 |
| year | 2026-01-01 00:00:00 |

### 7.1. Các đơn vị thường dùng

| `unit` | Ý nghĩa |
|---|---|
| `minute` | Đầu phút |
| `hour` | Đầu giờ |
| `day` | Đầu ngày |
| `week` | Đầu tuần, theo quy tắc tuần của PostgreSQL (thứ Hai) |
| `month` | Ngày đầu tháng, 00:00 |
| `quarter` | Đầu quý theo lịch |
| `year` | Ngày 01/01, 00:00 |
| `decade`, `century`, `millennium` | Mốc đầu các nhóm năm lớn |

PostgreSQL còn hỗ trợ các đơn vị phần giây hoặc đơn vị thích hợp khác tùy kiểu đối số. Không phải đơn vị nào cũng áp dụng ý nghĩa giống nhau cho `timestamp` và `interval`.

### 7.2. Cắt theo tuần

~~~sql
SELECT
    date_trunc('week', TIMESTAMP '2026-11-14 15:42:37')
        AS week_begin;
~~~

Ngày 14/11/2026 là thứ Bảy; kết quả đầu tuần là **thứ Hai 09/11/2026 00:00:00**.

Không tự coi `date_trunc('week',...)` là "bảy ngày trước" hoặc "tuần bắt đầu Chủ nhật". Nếu nghiệp vụ dùng tuần Chủ nhật hoặc lịch tài chính riêng, phải xây logic cụ thể.

### 7.3. Đầu quý

~~~sql
SELECT
    date_trunc('quarter', TIMESTAMP '2026-11-14 15:42:37')
        AS quarter_begin;
~~~

Kết quả là **2026-10-01 00:00:00** (đầu quý IV).

### 7.4. Phân biệt date_trunc và ROUND

`date_trunc('hour', '15:42')` cho **15:00**, không làm tròn thành 16:00 vì số phút lớn hơn 30. Đây là **truncation** theo mốc lịch, không phải phép làm tròn gần nhất.

### 7.5. date_trunc nhận kiểu nào?

Các trường hợp quan trọng:

- `date_trunc(text, timestamp)` → `timestamp`.
- `date_trunc(text, timestamptz)` → `timestamptz`.
- `date_trunc(text, interval)` → `interval` cho các trường hợp hỗ trợ.

Đối với `date_trunc('day', DATE '2026-11-14')`, PostgreSQL có thể ép DATE sang kiểu thời gian thích hợp. Nếu muốn hợp đồng kiểu rõ ràng, dùng cast tường minh trong câu SQL hoặc giữ DATE khi không cần timestamp.

---

## 8. date_trunc với TIMESTAMPTZ: phải hiểu timezone

Đây là điểm dễ sai nhất của báo cáo theo ngày.

### 8.1. Không chỉ cắt UTC khi người dùng muốn ngày địa phương

Giả sử instant:

~~~text
2026-11-13 17:30:00+00
~~~

Ở Việt Nam instant đó là:

~~~text
2026-11-14 00:30:00+07
~~~

Vì vậy **đầu ngày 14/11 theo lịch Việt Nam** là:

~~~text
2026-11-14 00:00:00+07
= 2026-11-13 17:00:00+00
~~~

Trong khi đầu **ngày UTC** của instant gốc là:

~~~text
2026-11-13 00:00:00+00
~~~

Đây là hai mốc hoàn toàn khác nhau.

### 8.2. date_trunc hai tham số dùng timezone của phiên

~~~sql
BEGIN;
SET LOCAL TimeZone = 'Asia/Ho_Chi_Minh';

SELECT date_trunc(
    'day',
    TIMESTAMPTZ '2026-11-13 17:30:00+00'
) AS beginning_of_local_day;

ROLLBACK;
~~~

Kết quả biểu diễn đầu ngày Việt Nam ở kiểu `timestamptz`. Nếu đổi session TimeZone sang UTC, cùng một câu `date_trunc('day',...)` có thể cắt theo **ngày UTC** thay vì ngày Việt Nam.

Do đó, với ứng dụng phục vụ nhiều timezone, đừng dùng mặc định session khi cần kết quả độc lập cấu hình phiên.

### 8.3. date_trunc có tham số timezone tường minh

PostgreSQL hỗ trợ dạng ba tham số cho `timestamptz`:

~~~sql
SELECT
    date_trunc(
        'day',
        TIMESTAMPTZ '2026-11-13 17:30:00+00',
        'Asia/Ho_Chi_Minh'
    ) AS local_midnight_instant;
~~~

Kết quả là **instant** đầu ngày ở Việt Nam, tương ứng **2026-11-13 17:00:00+00** khi hiển thị theo UTC.

Tham số thứ ba giúp xác định vùng dùng để cắt **mà không cần SET TimeZone của phiên**. Chú ý kết quả vẫn là `timestamptz`: khi SELECT, cách hiển thị offset vẫn tùy session.

### 8.4. Cắt local timestamp rồi chuyển ngược

Một cách tương đương về mục tiêu nhóm theo lịch địa phương:

~~~sql
SELECT
    date_trunc(
        'day',
        TIMESTAMPTZ '2026-11-13 17:30:00+00'
            AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AS local_day_start_clock;
~~~

Kết quả là `timestamp without time zone` có dạng **2026-11-14 00:00:00**. Để xác định instant của mốc local đó:

~~~sql
SELECT
    date_trunc(
        'day',
        TIMESTAMPTZ '2026-11-13 17:30:00+00'
            AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AT TIME ZONE 'Asia/Ho_Chi_Minh'
        AS local_midnight_instant;
~~~

Với mốc nửa đêm tại Việt Nam, đây là cách diễn đạt rõ. Ở vùng có giờ địa phương **mơ hồ hoặc không tồn tại** do DST, việc gắn timezone cho một local timestamp có thể cần quy tắc nghiệp vụ bổ sung.

---

## 9. Báo cáo GROUP BY theo ngày, tháng, quý

### 9.1. Tổng giao dịch theo ngày UTC

~~~sql
SELECT
    date_trunc('day', occurred_at, 'UTC') AS utc_day_start,
    COUNT(*) AS event_count,
    SUM(amount) AS total_amount
FROM time_lab.events
GROUP BY date_trunc('day', occurred_at, 'UTC')
ORDER BY utc_day_start;
~~~

`utc_day_start` là `timestamptz` chỉ instant bắt đầu ngày UTC. Khi hiển thị trên session khác UTC, chuỗi thời gian có thể mang offset địa phương dù nhóm vẫn được cắt theo UTC.

### 9.2. Tổng sự kiện theo ngày Việt Nam

Nếu muốn nhãn **DATE** dễ đọc:

~~~sql
SELECT
    (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS local_day,
    COUNT(*) AS event_count,
    SUM(amount) AS total_amount
FROM time_lab.events
GROUP BY
    (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
ORDER BY local_day;
~~~

Trong dữ liệu mẫu:

| local_day | event_count |
|---|---:|
| 2026-11-01 | 1 |
| 2026-11-13 | 1 |
| 2026-11-14 | 3 |
| 2026-11-15 | 1 |
| 2026-12-31 | 1 |
| 2027-01-01 | 1 |

Giải thích: event 2, 3 và 4 cùng nằm trong **ngày 14/11 tại Việt Nam**. Event 1 thuộc 13/11, còn event 5 thuộc 15/11.

### 9.3. Theo tháng địa phương

~~~sql
SELECT
    date_trunc(
        'month',
        occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AS local_month_start,
    COUNT(*) AS event_count
FROM time_lab.events
GROUP BY local_month_start
ORDER BY local_month_start;
~~~

`local_month_start` có kiểu `timestamp without time zone`, ví dụ `2026-11-01 00:00:00`. Dữ liệu mẫu có sáu event thuộc tháng 11/2026 theo lịch Việt Nam (ID 1,2,3,4,5,6), một trong tháng 12/2026 và một trong tháng 01/2027.

### 9.4. Theo quý/năm

~~~sql
SELECT
    date_trunc(
        'quarter',
        occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AS quarter_start,
    COUNT(*) AS event_count
FROM time_lab.events
GROUP BY quarter_start
ORDER BY quarter_start;
~~~

Chỉ cần thay `'quarter'` bằng `'year'` để nhóm theo năm. Nếu muốn nhóm theo vùng cố định và giữ kiểu instant, có thể dùng dạng ba tham số `date_trunc('quarter', occurred_at, 'Asia/Ho_Chi_Minh')`.

### 9.5. Những tháng không có sự kiện

`GROUP BY` chỉ tạo nhóm **có ít nhất một hàng**. Nếu dashboard cần hiển thị cả tháng trống với COUNT=0, cần dựng **calendar series** rồi LEFT JOIN aggregate, sẽ trình bày ở phần sau.

---

## 10. Hàm EXTRACT: lấy thành phần của ngày giờ

Cú pháp:

~~~sql
EXTRACT(field FROM temporal_value)
~~~

Ví dụ:

~~~sql
SELECT
    EXTRACT(YEAR FROM TIMESTAMP '2026-11-14 15:42:37') AS yr,
    EXTRACT(MONTH FROM TIMESTAMP '2026-11-14 15:42:37') AS mon,
    EXTRACT(DAY FROM TIMESTAMP '2026-11-14 15:42:37') AS dy,
    EXTRACT(HOUR FROM TIMESTAMP '2026-11-14 15:42:37') AS hr,
    EXTRACT(MINUTE FROM TIMESTAMP '2026-11-14 15:42:37') AS mn,
    EXTRACT(SECOND FROM TIMESTAMP '2026-11-14 15:42:37') AS sec;
~~~

Giá trị lần lượt: **2026, 11, 14, 15, 42, 37**.

### 10.1. DATE_TRUNC và EXTRACT khác nhau

| Câu lệnh | Kết quả | Kiểu ý nghĩa |
|---|---|---|
| `date_trunc('month', ts)` | `2026-11-01 00:00:00` | Mốc đầu tháng |
| `EXTRACT(MONTH FROM ts)` | `11` | Số tháng trong năm, không có năm |
| `date_trunc('hour', ts)` | `2026-11-14 15:00:00` | Mốc đầu giờ |
| `EXTRACT(HOUR FROM ts)` | `15` | Số giờ trong ngày |

Một sai lầm lớn:

~~~sql
SELECT EXTRACT(MONTH FROM occurred_at) AS month_no,
       COUNT(*)
FROM time_lab.events
GROUP BY month_no;
~~~

Câu này gom **tháng 11 của mọi năm** vào cùng nhóm. Nếu dữ liệu có nhiều năm, cần thêm `EXTRACT(YEAR ...)` hoặc dùng `date_trunc('month', ...)` để phân biệt năm và tháng.

### 10.2. EXTRACT và date_part

PostgreSQL có hai cách diễn đạt:

~~~sql
SELECT
    EXTRACT(YEAR FROM TIMESTAMP '2026-11-14 15:42:37') AS year_extracted,
    date_part('year', TIMESTAMP '2026-11-14 15:42:37') AS year_part;
~~~

Chúng diễn đạt việc lấy một thành phần thời gian nhưng có đặc tính kiểu trả về khác nhau: `EXTRACT` trả kiểu `numeric` trong PostgreSQL hiện đại, còn `date_part` trả `double precision`. Khi schema hoặc ứng dụng cần số nguyên, hãy cast tường minh nếu phù hợp:

~~~sql
SELECT EXTRACT(YEAR FROM CURRENT_DATE)::integer AS this_year;
~~~

Không ép mọi field sang integer vì `SECOND` có thể chứa phần thập phân.

### 10.3. EXTRACT với interval

~~~sql
SELECT
    EXTRACT(DAY FROM INTERVAL '2 days 03:04:05') AS d,
    EXTRACT(HOUR FROM INTERVAL '2 days 03:04:05') AS h,
    EXTRACT(MINUTE FROM INTERVAL '2 days 03:04:05') AS m;
~~~

Cho các thành phần **2 ngày, 3 giờ, 4 phút**. Khi interval có tháng/ngày/giờ, cần phân biệt **thành phần** với tổng số giây hoặc tổng số giờ; không coi `EXTRACT(HOUR FROM interval)` luôn là tổng giờ của interval.

---

## 11. Thứ trong tuần, tuần ISO và năm ISO

### 11.1. DOW so với ISODOW

PostgreSQL hỗ trợ:

- `EXTRACT(DOW FROM ts)`: Chủ nhật **0**, thứ Hai **1**, ... thứ Bảy **6**.
- `EXTRACT(ISODOW FROM ts)`: thứ Hai **1**, ... Chủ nhật **7**.

~~~sql
SELECT
    EXTRACT(DOW FROM DATE '2026-11-14') AS day_of_week,
    EXTRACT(ISODOW FROM DATE '2026-11-14') AS iso_day_of_week;
~~~

Ngày 14/11/2026 là thứ Bảy, cả hai đều trả **6**.

Với Chủ nhật:

~~~sql
SELECT
    EXTRACT(DOW FROM DATE '2026-11-15') AS dow,
    EXTRACT(ISODOW FROM DATE '2026-11-15') AS isodow;
~~~

`dow` = **0**, `isodow` = **7**. Chọn hàm theo cách đánh số ngày của ứng dụng.

### 11.2. WEEK trong PostgreSQL dùng tuần ISO

ISO week bắt đầu **thứ Hai**, và tuần ISO thứ nhất là tuần chứa ngày 4/1 (tương đương tuần chứa thứ Năm đầu tiên của năm).

~~~sql
SELECT
    EXTRACT(YEAR FROM DATE '2021-01-01') AS calendar_year,
    EXTRACT(ISOYEAR FROM DATE '2021-01-01') AS iso_year,
    EXTRACT(WEEK FROM DATE '2021-01-01') AS iso_week;
~~~

Ngày 01/01/2021 có:

~~~text
calendar_year = 2021
iso_year      = 2020
iso_week      = 53
~~~

Vì thuộc **tuần ISO 53 của năm ISO 2020**.

### 11.3. Đừng ghép YEAR với WEEK một cách máy móc

~~~sql
SELECT
    EXTRACT(YEAR FROM some_date) AS yr,
    EXTRACT(WEEK FROM some_date) AS wk
FROM some_table;
~~~

Nếu nhóm dữ liệu theo "năm-tuần ISO", dùng **ISOYEAR + WEEK**:

~~~sql
SELECT
    EXTRACT(ISOYEAR FROM occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::integer
        AS iso_year,
    EXTRACT(WEEK FROM occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::integer
        AS iso_week,
    COUNT(*) AS event_count
FROM time_lab.events
GROUP BY iso_year, iso_week
ORDER BY iso_year, iso_week;
~~~

Hoặc nhóm theo `date_trunc('week', local_timestamp)` để có một mốc bắt đầu tuần duy nhất. Đừng chỉ dùng `WEEK` nếu dữ liệu trải nhiều năm.

### 11.4. Tháng và quý

~~~sql
SELECT
    EXTRACT(QUARTER FROM DATE '2026-11-14') AS quarter_no,
    EXTRACT(DOY FROM DATE '2026-11-14') AS day_of_year;
~~~

`QUARTER` trả **4**. `DOY` là thứ tự ngày trong năm, chịu ảnh hưởng năm nhuận.

---

## 12. EXTRACT(EPOCH): biểu diễn thời điểm bằng giây

### 12.1. Epoch của một instant

~~~sql
SELECT EXTRACT(
    EPOCH FROM TIMESTAMPTZ '1970-01-01 00:00:00+00'
) AS epoch_zero;
~~~

Kết quả **0**.

Với `timestamptz`, EPOCH là số giây tính từ mốc Unix epoch theo UTC, thường được sử dụng khi trao đổi timestamp dưới dạng số.

~~~sql
SELECT
    event_id,
    EXTRACT(EPOCH FROM occurred_at) AS epoch_seconds
FROM time_lab.events
ORDER BY event_id;
~~~

### 12.2. Đổi epoch thành TIMESTAMPTZ

~~~sql
SELECT to_timestamp(0) AS epoch_as_timestamptz;
~~~

`to_timestamp(double precision)` nhận số giây Unix epoch và trả một `timestamptz`. Khi SELECT, offset hiển thị phụ thuộc TimeZone phiên.

### 12.3. Cẩn thận với epoch của timestamp không timezone

`EXTRACT(EPOCH FROM timestamp without time zone)` dựa trên các thành phần ngày-giờ danh nghĩa, **không gắn múi giờ để định vị instant như với timestamptz**.

Không làm thế này khi cột thực chất là giờ Việt Nam:

~~~sql
-- Không được coi đây là Unix epoch của instant giờ Việt Nam nếu chưa gắn zone.
SELECT EXTRACT(EPOCH FROM TIMESTAMP '2026-11-14 09:30:00');
~~~

Cách rõ nghĩa:

~~~sql
SELECT EXTRACT(
    EPOCH FROM (
        TIMESTAMP '2026-11-14 09:30:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
) AS epoch_of_vn_instant;
~~~

Đặt dấu `AT TIME ZONE` trước `EXTRACT(EPOCH)` để biến local time thành instant đúng.

### 12.4. Tính thời lượng giây giữa hai instant

~~~sql
SELECT EXTRACT(
    EPOCH FROM (
        TIMESTAMPTZ '2026-11-14 11:00:00+00'
        - TIMESTAMPTZ '2026-11-14 10:30:00+00'
    )
) AS elapsed_seconds;
~~~

Kết quả **1800** giây. Đây là **30 phút thực trôi qua**, không phải nhóm theo lịch.

---

## 13. AT TIME ZONE: hai chiều hoàn toàn khác nhau

Đây là quy tắc phải nhớ:

| Đầu vào | Cú pháp | Kiểu trả về | Ý nghĩa |
|---|---|---|---|
| `timestamp without time zone` | `local_ts AT TIME ZONE 'Zone'` | `timestamptz` | Diễn giải local timestamp như thời gian ở Zone, tạo instant |
| `timestamptz` | `instant_ts AT TIME ZONE 'Zone'` | `timestamp without time zone` | Hiển thị instant dưới dạng đồng hồ/lịch của Zone |

### 13.1. Timestamp → TIMESTAMPTZ (gắn ý nghĩa vùng)

~~~sql
SELECT
    TIMESTAMP '2026-11-14 09:30:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh' AS instant_value;
~~~

Ý nghĩa: **09:30 ngày 14/11 ở Việt Nam** là instant tương đương **02:30 UTC** cùng ngày.

Truy vấn không chỉ "đổi cách hiển thị", mà **diễn giải một giá trị không gắn zone thành một instant**.

### 13.2. TIMESTAMPTZ → timestamp (xem giờ theo vùng)

~~~sql
SELECT
    TIMESTAMPTZ '2026-11-14 02:30:00+00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh' AS vn_clock;
~~~

Kết quả: **2026-11-14 09:30:00**, kiểu `timestamp without time zone`.

### 13.3. Nhìn cùng instant ở nhiều vùng

~~~sql
SELECT
    TIMESTAMPTZ '2026-11-14 02:30:00+00'
        AT TIME ZONE 'UTC' AS utc_clock,
    TIMESTAMPTZ '2026-11-14 02:30:00+00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh' AS vn_clock,
    TIMESTAMPTZ '2026-11-14 02:30:00+00'
        AT TIME ZONE 'America/New_York' AS ny_clock;
~~~

Các cột đều biểu diễn **cùng một instant**, nhưng ngày/giờ địa phương có thể khác. Offset New York phụ thuộc thời điểm và quy tắc DST, nên không hardcode offset của New York quanh năm.

### 13.4. timezone() là dạng hàm tương đương thường gặp

~~~sql
SELECT
    timezone('Asia/Ho_Chi_Minh',
        TIMESTAMPTZ '2026-11-14 02:30:00+00') AS vn_clock;
~~~

Với đối số `timestamptz`, nó thể hiện cùng mục tiêu như `AT TIME ZONE` để lấy local timestamp. Nên ưu tiên cách viết rõ cho người đọc và nhất quán trong dự án.

### 13.5. Đừng CAST trước rồi mới mong giữ instant

Một lỗi:

~~~sql
SELECT occurred_at::timestamp
FROM time_lab.events;
~~~

Cast này chuyển instant thành local timestamp **theo session TimeZone hiện tại**. Sau đó một phiên khác có thể gắn timezone sai cho local value và làm lệch instant.

Nếu muốn hiển thị giờ Việt Nam, hãy ghi rõ:

~~~sql
SELECT occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
FROM time_lab.events;
~~~

---

## 14. Daylight Saving Time (DST): ngày lịch khác 24 giờ

Việt Nam hiện sử dụng UTC+7 không đổi giờ mùa hè, nhưng nhiều vùng như New York có DST. Đây là một nguyên nhân phổ biến gây sai báo cáo ngày.

### 14.1. Vào ngày bắt đầu DST, đồng hồ có thể nhảy qua một giờ

Ở New York, ngày chuyển sang giờ mùa hè trong năm 2026 là **08/03/2026**. Một khoảng chuyển tiếp:

~~~text
UTC                  New York local
2026-03-08 06:59Z  → 2026-03-08 01:59
2026-03-08 07:01Z  → 2026-03-08 03:01
~~~

Giờ địa phương `02:00–02:59` của ngày đó **không tồn tại** trong quy tắc chuyển tiếp tương ứng.

Thử với instant UTC cụ thể:

~~~sql
SELECT
    TIMESTAMPTZ '2026-03-08 06:59:00+00'
        AT TIME ZONE 'America/New_York' AS before_jump,
    TIMESTAMPTZ '2026-03-08 07:01:00+00'
        AT TIME ZONE 'America/New_York' AS after_jump;
~~~

### 14.2. Ngày local có thể dài 23 hoặc 25 giờ

Lấy hai đầu ngày New York:

~~~sql
SELECT
    (
        TIMESTAMP '2026-03-09 00:00:00'
        AT TIME ZONE 'America/New_York'
    ) - (
        TIMESTAMP '2026-03-08 00:00:00'
        AT TIME ZONE 'America/New_York'
    ) AS actual_elapsed;
~~~

Kết quả khoảng **23 giờ** vì ngày 08/03/2026 có bước nhảy DST.

Ngược lại, ngày quay về giờ tiêu chuẩn trong một vùng có DST có thể dài **25 giờ**. Do đó:

- **24 giờ vừa qua:** khoảng elapsed time, có thể dùng `now() - interval '24 hours'`.
- **Ngày hôm qua theo lịch địa phương:** hai mốc nửa đêm địa phương liên tiếp, không được giả định luôn cách nhau 24 giờ.

### 14.3. Giờ địa phương có thể mơ hồ

Khi đồng hồ quay ngược, một local time như `01:30` có thể xảy ra **hai lần** với hai offset khác nhau. Nếu chỉ lưu `TIMESTAMP '... 01:30'` và tên vùng, cần chính sách chọn lần nào khi khôi phục instant. Nếu giờ đó là lịch hẹn quan trọng, có thể cần lưu offset/instant đã chọn hoặc quy tắc xử lý ambiguous time.

### 14.4. Luôn ưu tiên tên vùng IANA khi là lịch theo vùng

Nếu nghiệp vụ nói "ngày ở New York", dùng `'America/New_York'`, không luôn trừ 5 giờ. Nếu nghiệp vụ nói "ngày ở Việt Nam", dùng `'Asia/Ho_Chi_Minh'`. Offset chỉ mô tả chênh lệch tại một thời điểm, không phải toàn bộ lịch sử/quy tắc vùng.

---

## 15. Lọc dữ liệu theo ngày địa phương đúng và tối ưu

Yêu cầu: lấy **mọi event trong ngày 14/11/2026 theo lịch Việt Nam**, kể cả mili giây/micro giây cuối ngày.

### 15.1. Không nên dùng BETWEEN với hai đầu giờ cố định

Ví dụ dễ sai:

~~~sql
WHERE occurred_at BETWEEN
    TIMESTAMPTZ '2026-11-14 00:00:00+07'
    AND TIMESTAMPTZ '2026-11-14 23:59:59+07'
~~~

`BETWEEN` bao gồm **cả hai đầu**, nhưng vẫn bỏ sót dữ liệu ở `23:59:59.123456` hoặc các phần giây khác sau 23:59:59. Đặt "ngày kết thúc + 23:59:59.999..." là một cách làm phụ thuộc precision và rất dễ hỏng.

### 15.2. Dùng khoảng nửa mở [start, next_start)

~~~sql
SELECT event_id, occurred_at, event_type, amount
FROM time_lab.events
WHERE occurred_at >= (
        TIMESTAMP '2026-11-14 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
  AND occurred_at < (
        TIMESTAMP '2026-11-15 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
ORDER BY occurred_at, event_id;
~~~

Kết quả gồm **event 2, 3, 4**.

Mẫu điều kiện:

~~~text
occurred_at >= local_midnight_start_as_instant
AND occurred_at < local_next_midnight_as_instant
~~~

Cách này:

- Không bỏ sót phần giây cuối ngày.
- Không tính trùng dòng ở mốc nửa đêm tiếp theo.
- Đúng với ngày 23/25 giờ trong vùng có DST.
- Có khả năng dùng **B-tree index trên cột occurred_at** khi planner thấy có lợi.

### 15.3. Vì sao thường tránh CAST trên cột ở WHERE?

Truy vấn đơn giản:

~~~sql
SELECT *
FROM time_lab.events
WHERE (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
      = DATE '2026-11-14';
~~~

vẫn có thể cho **kết quả đúng**. Nhưng nó áp dụng biểu thức lên mỗi giá trị cột; một B-tree index thông thường trên `occurred_at` không nhất thiết hỗ trợ trực tiếp điều kiện dạng ấy như một range scan.

Nếu có index:

~~~sql
CREATE INDEX ix_events_occurred_at
ON time_lab.events (occurred_at);
~~~

thì điều kiện theo khoảng `occurred_at >= start AND occurred_at < end` thường là cách tự nhiên cho index. Không nên tự thêm expression index phức tạp trước khi có bằng chứng workload.

### 15.4. Khoảng ngày New York qua DST

~~~sql
SELECT *
FROM time_lab.events
WHERE occurred_at >= (
        TIMESTAMP '2026-03-08 00:00:00'
        AT TIME ZONE 'America/New_York'
    )
  AND occurred_at < (
        TIMESTAMP '2026-03-09 00:00:00'
        AT TIME ZONE 'America/New_York'
    );
~~~

Hai mốc được xác định riêng theo **ngày lịch New York**, nên xử lý đúng khoảng 23 giờ của ngày đổi DST. Không lấy mốc đầu rồi cộng cứng 24 giờ nếu nghiệp vụ đang hỏi **một ngày địa phương**.

### 15.5. Tính mốc từ tham số DATE

Trong ứng dụng, dùng parameter binding, ví dụ `:local_day` có kiểu DATE:

~~~sql
SELECT event_id, occurred_at
FROM time_lab.events
WHERE occurred_at >= (
        :local_day::date::timestamp
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
  AND occurred_at < (
        (:local_day::date + 1)::timestamp
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
ORDER BY occurred_at, event_id;
~~~

Đây là SQL minh họa kiểu placeholder; cú pháp binding cụ thể phụ thuộc driver/ORM. Không nội suy giá trị người dùng trực tiếp thành chuỗi SQL.

---

## 16. date_trunc và EXTRACT trong điều kiện GROUP BY

### 16.1. Lọc theo tháng thay vì EXTRACT(MONTH)

Câu dễ sai:

~~~sql
SELECT *
FROM time_lab.events
WHERE EXTRACT(MONTH FROM occurred_at) = 11;
~~~

Nếu phiên có timezone khác, tháng được lấy có thể khác ở mốc gần ranh giới; và câu này lấy **tháng 11 của mọi năm**.

Đúng hơn nếu yêu cầu là **tháng 11/2026 tại Việt Nam**:

~~~sql
SELECT *
FROM time_lab.events
WHERE occurred_at >= (
        TIMESTAMP '2026-11-01 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
  AND occurred_at < (
        TIMESTAMP '2026-12-01 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
ORDER BY occurred_at;
~~~

Lọc theo khoảng thường rõ và phù hợp index hơn so với điều kiện áp `EXTRACT` lên từng hàng.

### 16.2. GROUP BY bằng DATE_TRUNC

~~~sql
SELECT
    date_trunc(
        'month',
        occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AS month_local,
    COUNT(*) AS cnt
FROM time_lab.events
GROUP BY month_local
ORDER BY month_local;
~~~

Khác với:

~~~sql
SELECT EXTRACT(MONTH FROM occurred_at) AS mon,
       COUNT(*)
FROM time_lab.events
GROUP BY mon;
~~~

Vế thứ hai vừa có thể phụ thuộc session timezone, vừa gộp tháng cùng số của các **năm khác nhau**.

### 16.3. EXTRACT cho phân tích theo giờ địa phương

Ví dụ muốn biết số event theo **giờ trong ngày** ở Việt Nam, bỏ qua ngày:

~~~sql
SELECT
    EXTRACT(
        HOUR FROM occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )::integer AS local_hour,
    COUNT(*) AS cnt
FROM time_lab.events
GROUP BY local_hour
ORDER BY local_hour;
~~~

Kết quả có tối đa 24 nhóm giờ theo đồng hồ, 0 đến 23. Đây là **phân bố giờ**, không phải chuỗi thời gian theo giờ liên tiếp.

---

## 17. Cộng/trừ ngày, timestamp và interval

### 17.1. Cộng số ngày vào DATE

~~~sql
SELECT
    DATE '2026-11-14' + 1 AS next_day,
    DATE '2026-11-14' - 7 AS week_ago;
~~~

`DATE + integer` dịch số **ngày lịch**. Hai DATE trừ nhau trả số ngày:

~~~sql
SELECT DATE '2026-11-21' - DATE '2026-11-14' AS days_between;
~~~

Kết quả **7**.

### 17.2. Timestamp cộng interval

~~~sql
SELECT
    TIMESTAMP '2026-11-14 09:00:00'
        + INTERVAL '90 minutes' AS plus_90_minutes,
    TIMESTAMP '2026-11-14 09:00:00'
        + INTERVAL '2 days 3 hours' AS plus_interval;
~~~

Các biểu thức trả timestamp sau khi cộng khoảng tương ứng.

### 17.3. Một tháng không phải luôn 30 ngày

~~~sql
SELECT
    DATE '2026-01-31' + INTERVAL '1 month' AS next_month;
~~~

Theo quy tắc lịch, kết quả rơi vào **28/02/2026**, không phải tự cộng cố định 30 hoặc 31 ngày.

Các bài toán billing "chu kỳ một tháng", "tháng sau cùng ngày" hoặc "tháng sau cuối tháng" có thể có quy tắc khác nhau. Không dùng duy nhất `interval '30 days'` để đại diện cho **một tháng lịch** nếu nghiệp vụ cần lịch.

### 17.4. Khoảng "1 day" và "24 hours" khi có DST

Với `timestamptz` ở vùng có DST, cộng `INTERVAL '1 day'` thường vận hành theo **ngày lịch địa phương**, trong khi `INTERVAL '24 hours'` diễn đạt **24 giờ thực**, có thể dẫn đến giờ địa phương khác quanh lần đổi DST.

Không tự giả định hai khoảng trên luôn bằng nhau về kết quả với `timestamptz`. Cần dùng timezone đúng khi tính kỳ hạn theo lịch.

### 17.5. age cho chênh lệch có tính lịch

~~~sql
SELECT age(
    TIMESTAMP '2026-11-14',
    TIMESTAMP '2024-11-14'
) AS calendar_age;
~~~

`age` trả một `interval` có thể chứa **năm/tháng/ngày** theo quy tắc lịch, khác với `EXTRACT(EPOCH FROM (end-start))` là thời lượng giây thực. Không dùng tuổi theo epoch chia 365.25 khi nghiệp vụ cần tuổi theo ngày sinh và quy định lịch cụ thể.

---

## 18. generate_series để tạo lịch và lấp ngày trống

`GROUP BY` không tạo nhóm cho những ngày không có dữ liệu. Dashboard có thể cần hiển thị cả ngày trống với `count = 0`.

### 18.1. Sinh dãy ngày

~~~sql
SELECT d::date AS report_day
FROM generate_series(
    DATE '2026-11-13'::timestamp,
    DATE '2026-11-17'::timestamp,
    INTERVAL '1 day'
) AS g(d)
ORDER BY report_day;
~~~

Kết quả ngày 13, 14, 15, 16, 17/11.

### 18.2. LEFT JOIN thống kê theo ngày

~~~sql
WITH calendar AS (
    SELECT d::date AS local_day
    FROM generate_series(
        DATE '2026-11-13'::timestamp,
        DATE '2026-11-17'::timestamp,
        INTERVAL '1 day'
    ) AS g(d)
),
daily AS (
    SELECT
        (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS local_day,
        COUNT(*) AS cnt,
        SUM(amount) AS total_amount
    FROM time_lab.events
    GROUP BY local_day
)
SELECT
    c.local_day,
    COALESCE(d.cnt, 0) AS event_count,
    COALESCE(d.total_amount, 0) AS total_amount
FROM calendar AS c
LEFT JOIN daily AS d
  ON d.local_day = c.local_day
ORDER BY c.local_day;
~~~

Những ngày không có event sẽ xuất hiện với `0`.

### 18.3. Cẩn thận với generate_series trên timestamptz và DST

Nếu sinh dãy thời điểm qua vùng có DST, phải xác định đang muốn:

- Mỗi **24 giờ thực**,
- Hay **mỗi nửa đêm theo lịch địa phương**.

Hai yêu cầu khác nhau vào ngày đổi giờ. Với lịch ngày của địa phương, một cách rõ ràng là sinh `DATE/timestamp local` rồi chuyển từng mốc bằng `AT TIME ZONE` tương ứng.

---

## 19. date_bin: gom thành các khung thời gian cố định

`date_trunc` phù hợp những mốc lịch như đầu phút, giờ, ngày, tháng. Khi muốn bucket **15 phút**, **5 phút** hoặc một stride cố định với origin riêng, PostgreSQL có `date_bin`:

~~~sql
SELECT date_bin(
    INTERVAL '15 minutes',
    TIMESTAMP '2026-11-14 10:37:42',
    TIMESTAMP '2000-01-01 00:00:00'
) AS bucket_start;
~~~

Kết quả **2026-11-14 10:30:00**.

### 19.1. Cú pháp và ý nghĩa

~~~text
date_bin(stride, source_timestamp, origin_timestamp)
~~~

- `stride`: kích thước khung cố định, lớn hơn 0.
- `source`: timestamp cần gom.
- `origin`: mốc chuẩn để căn biên các bucket.

`date_bin` hữu ích cho biểu đồ theo 5, 15, 30 phút hoặc các nhóm thời gian cố định khác. PostgreSQL hỗ trợ từ phiên bản **14**; nếu vận hành phiên bản cũ hơn, cần phương án thay thế.

### 19.2. Không dùng stride chứa tháng/năm

`date_bin` không cho phép stride chứa đơn vị **tháng hoặc lớn hơn** vì độ dài tháng không cố định. Muốn bucket theo **tháng lịch**, dùng `date_trunc('month', ...)` hoặc logic lịch cụ thể.

### 19.3. Bucketing 15 phút của các instant

~~~sql
SELECT
    date_bin(
        INTERVAL '15 minutes',
        occurred_at,
        TIMESTAMPTZ '2000-01-01 00:00:00+00'
    ) AS bucket_utc,
    COUNT(*) AS event_count
FROM time_lab.events
GROUP BY bucket_utc
ORDER BY bucket_utc;
~~~

`bucket_utc` là các mốc instant cách nhau 15 phút tính từ origin UTC. Nếu cần hiển thị giờ Việt Nam, có thể lấy `bucket_utc AT TIME ZONE 'Asia/Ho_Chi_Minh'` ở tầng ngoài.

### 19.4. date_bin khác date_trunc

- `date_trunc('day', instant, 'America/New_York')` đi đến đầu **ngày lịch New York**; ngày có thể dài 23/25 giờ.
- `date_bin(interval '24 hours', instant, origin)` đi theo các khung **24 giờ tuyệt đối** tính từ origin.

Không thay chúng cho nhau khi yêu cầu là bucket theo **lịch địa phương**.

---

## 20. Định dạng và parse dữ liệu thời gian

### 20.1. to_char cho đầu ra hiển thị

~~~sql
SELECT
    to_char(
        TIMESTAMPTZ '2026-11-14 02:30:00+00'
            AT TIME ZONE 'Asia/Ho_Chi_Minh',
        'YYYY-MM-DD HH24:MI:SS'
    ) AS vn_display;
~~~

Kết quả chuỗi: `2026-11-14 09:30:00`.

`to_char` tạo **TEXT**, không phải DATE/TIMESTAMP. Không dùng chuỗi đã format làm dữ liệu thời gian gốc để tiếp tục tính toán nếu còn giữ được kiểu thời gian.

### 20.2. Format để hiển thị, không phải để GROUP BY lâu dài

Ví dụ:

~~~sql
SELECT
    to_char(
        occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh',
        'YYYY-MM'
    ) AS month_label,
    COUNT(*) AS cnt
FROM time_lab.events
GROUP BY month_label
ORDER BY month_label;
~~~

Có thể hữu ích cho báo cáo đơn giản, nhưng `month_label` là text. Trong hệ thống phức tạp nên nhóm theo `date_trunc('month',...)` hoặc DATE, rồi định dạng **sau cùng**. Điều này hạn chế phụ thuộc format/collation và dễ thao tác theo khoảng thời gian hơn.

### 20.3. to_date, to_timestamp và cast

~~~sql
SELECT to_date('14/11/2026', 'DD/MM/YYYY') AS parsed_date;
~~~

`to_date` phân tích chuỗi thành DATE theo format chỉ định. `to_timestamp(text,text)` hỗ trợ parse timestamp theo mẫu, nhưng **khác** `to_timestamp(double precision)` dùng Unix epoch.

Với dữ liệu ISO 8601 có offset:

~~~sql
SELECT TIMESTAMPTZ '2026-11-14T09:30:00+07:00';
~~~

Ưu tiên truyền tham số có kiểu qua driver thay vì nội suy các chuỗi input. Khi parse từ text, kiểm tra tính hợp lệ, timezone, định dạng và chính sách dữ liệu lỗi.

### 20.4. Tên ngày và collation

`to_char` có mẫu cho ngày trong tuần và tên tháng; output có thể chịu ảnh hưởng locale/cấu hình phù hợp. Nếu nghiệp vụ cần i18n, thường nên giữ ngày dạng cấu trúc trong API rồi để tầng trình bày định dạng theo locale người dùng.

---

## 21. Index và EXPLAIN với các hàm thời gian

### 21.1. Index cơ bản trên TIMESTAMPTZ

~~~sql
CREATE INDEX ix_events_occurred_at_for_search
ON time_lab.events (occurred_at);
~~~

Đây là index minh họa trong lab. Trên bảng vài dòng PostgreSQL có thể chọn `Seq Scan` vì đọc cả bảng rất rẻ; điều đó không có nghĩa index không tồn tại.

Truy vấn phù hợp cho range scan:

~~~sql
SELECT event_id, occurred_at
FROM time_lab.events
WHERE occurred_at >= TIMESTAMPTZ '2026-11-13 17:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-11-14 17:00:00+00'
ORDER BY occurred_at, event_id;
~~~

### 21.2. Hàm trên cột có thể cản trở index thường

~~~sql
SELECT *
FROM time_lab.events
WHERE date_trunc('day', occurred_at, 'UTC')
    = TIMESTAMPTZ '2026-11-14 00:00:00+00';
~~~

Điều kiện này có thể đúng về mặt logic nhưng PostgreSQL không nhất thiết biến nó về range scan trên index B-tree `occurred_at`. Viết range theo mốc đầu/cuối ngày thường đơn giản và có cơ hội sử dụng index hơn.

### 21.3. Expression index cần chú ý tính bất biến

Không phải mọi biểu thức ngày giờ đều được dùng làm **expression index** hoặc generated column. Ví dụ `date_trunc('day', timestamptz)` dạng phụ thuộc session timezone có thể **không đủ tính bất biến** cho expression index; PostgreSQL yêu cầu hàm trong biểu thức index có tính chất thích hợp.

Thay vì cố tạo index trên một biểu thức phụ thuộc timezone mặc định, ưu tiên index trên instant `occurred_at` và lọc bằng hai **mốc timestamptz tường minh**. Khi một biểu thức là workload chính, cần thiết kế cách xác định zone và tính bất biến trước khi cân nhắc index riêng.

### 21.4. EXPLAIN trên truy vấn lọc ngày

~~~sql
EXPLAIN
SELECT event_id, occurred_at
FROM time_lab.events
WHERE occurred_at >= (
        TIMESTAMP '2026-11-14'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
  AND occurred_at < (
        TIMESTAMP '2026-11-15'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    );
~~~

Xem planner chọn:

- `Seq Scan`, `Index Scan`, `Bitmap Index Scan`, hoặc kế hoạch khác.
- Số rows ước lượng.
- Index condition hoặc filter.
- Chi phí và tỷ lệ dữ liệu phù hợp.

Muốn đo thực thi:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, occurred_at
FROM time_lab.events
WHERE occurred_at >= TIMESTAMPTZ '2026-11-13 17:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-11-14 17:00:00+00';
~~~

`ANALYZE` chạy query thật. Chỉ đo trên dữ liệu và môi trường phù hợp; trên production bảng lớn có thể tốn I/O/CPU ngay cả khi SELECT.

### 21.5. B-tree, BRIN và bảng sự kiện lớn

Với bảng log/time-series rất lớn mà dữ liệu `occurred_at` có tương quan tốt với thứ tự lưu vật lý, `BRIN` có thể là một lựa chọn index nhỏ và hiệu quả cho range scan rộng. `B-tree` thường mạnh với điều kiện chọn lọc và ORDER BY. Chọn theo workload, phân bố dữ liệu, tỷ lệ cập nhật và kết quả `EXPLAIN`; không có một loại index tối ưu mọi tình huống.

---

## 22. Những trường hợp biên cần chủ động quyết định

### 22.1. Ngày sinh khác thời điểm sinh

Nếu chỉ cần biết khách sinh ngày nào, dùng `DATE`. Nếu cần sự kiện sinh diễn ra tại một instant cụ thể, cần thêm thông tin timezone/instant phù hợp. Chuyển DATE thành TIMESTAMPTZ tùy session một cách vô thức sẽ tạo mốc thời gian không có trong nghiệp vụ.

### 22.2. Hạn thanh toán theo ngày địa phương

"Thanh toán trước hết ngày 14/11 tại Việt Nam" thường tương đương khoảng thời gian trước **00:00 ngày 15/11 giờ Việt Nam**, không phải trước `2026-11-14 23:59:59 UTC`.

### 22.3. Lịch hẹn lặp theo giờ địa phương

"Mỗi thứ Hai lúc 09:00 New York" không phải một instant cố định lặp sau đúng `7 × 24 giờ` quanh DST. Cần lịch theo timezone IANA, quy tắc ngày nghỉ/giờ không tồn tại/mơ hồ và cách xác định instant từng lần hẹn.

### 22.4. Lưu UTC không có nghĩa báo cáo phải theo ngày UTC

Lưu `timestamptz` như instant giúp trao đổi và so sánh chính xác. Nhưng ngày báo cáo cần **chuyển sang lịch của khách/đơn vị kinh doanh trước khi gom nhóm**.

### 22.5. Timestamp thiếu offset từ client

Chuỗi `2026-11-14 09:30` là local timestamp mơ hồ nếu không nói timezone. Khi API nhận input này:

- Đòi client gửi offset hoặc tên timezone theo hợp đồng.
- Hoặc có timezone đã được xác định rõ từ tổ chức/người dùng.
- Không tự hiểu đó là UTC chỉ vì server đặt UTC.

### 22.6. Đừng so sánh ngày bằng text format

Chuỗi `DD/MM/YYYY` không tự sắp theo thứ tự thời gian khi so từ trái sang phải. Giữ dữ liệu kiểu DATE/TIMESTAMP, chỉ `to_char` ở tầng trình bày.

---

## 23. Bảng tra cứu nhanh

| Nhu cầu | Cách viết thường dùng | Lưu ý |
|---|---|---|
| Thời điểm bắt đầu transaction | `now()` hoặc `CURRENT_TIMESTAMP` | Không thay đổi trong cùng transaction |
| Thời điểm bắt đầu statement | `statement_timestamp()` | Có thể khác giữa các statement |
| Đồng hồ hiện tại khi thực thi | `clock_timestamp()` | Có thể đổi trong cùng statement |
| Ngày theo timezone phiên | `CURRENT_DATE` | Phụ thuộc session |
| Cắt timestamp về đầu tháng | `date_trunc('month', ts)` | Trả timestamp/timestamptz tùy input |
| Cắt timestamptz theo vùng | `date_trunc('day', ts, 'Asia/Ho_Chi_Minh')` | Trả một instant đầu ngày local |
| Lấy năm | `EXTRACT(YEAR FROM ts)` | Chỉ thành phần năm |
| Lấy tuần ISO | `EXTRACT(WEEK FROM ts)` | Nên kèm ISOYEAR |
| Thứ Hai = 1, Chủ nhật = 7 | `EXTRACT(ISODOW FROM ts)` | Khác DOW vào Chủ nhật |
| Timestamp local → instant | `local_ts AT TIME ZONE 'Zone'` | Trả timestamptz |
| Instant → local clock | `instant_ts AT TIME ZONE 'Zone'` | Trả timestamp |
| Lấy Unix epoch | `EXTRACT(EPOCH FROM instant_ts)` | Trả số giây |
| Epoch → timestamptz | `to_timestamp(seconds)` | Hiển thị theo session |
| Lọc trọn ngày local | `ts >= start AND ts < next_start` | Hai mốc chuyển từ local midnight sang instant |
| Tạo dãy ngày | `generate_series(start, stop, interval '1 day')` | Xác định dùng DATE/local hay instant |
| Gom 15 phút cố định | `date_bin(interval '15 minutes', ts, origin)` | Không hỗ trợ stride theo tháng |
| Hiển thị thời gian | `to_char(ts, format)` | Trả TEXT, không đổi nguồn dữ liệu |

---

## 24. Quy trình làm việc với thời gian

~~~mermaid
flowchart TD
    A["Xác định dữ liệu là instant hay giờ địa phương"] --> B{"Cần lưu instant?"}
    B -- "Có" --> C["TIMESTAMPTZ"]
    B -- "Không" --> D["DATE / TIME / TIMESTAMP đúng nghĩa"]
    C --> E["Chốt timezone của báo cáo/người dùng"]
    D --> E
    E --> F{"Cần nhóm theo lịch?"}
    F -- "Có" --> G["date_trunc / EXTRACT / local DATE"]
    F -- "Không" --> H["Lọc/so instant và INTERVAL"]
    G --> I["Xử lý ranh giới ngày và DST"]
    H --> I
    I --> J["Dùng khoảng nửa mở cho WHERE"]
    J --> K["Kiểm thử biên nửa đêm, tháng, năm, DST"]
    K --> L["EXPLAIN và tối ưu theo workload"]
~~~

Checklist khi review một truy vấn thời gian:

1. Cột là `timestamp` hay `timestamptz`? Có bị ép kiểu ngầm không?
2. Timezone của nguồn dữ liệu là gì? Timezone của báo cáo là gì?
3. `CURRENT_DATE`/`date_trunc` có vô tình phụ thuộc timezone session không?
4. Bài toán hỏi **instant**, **thời lượng 24h**, hay **ngày trên lịch**?
5. Có giá trị nằm sát **00:00**, cuối tháng, cuối năm hay DST không?
6. Nếu dùng tuần, đã ghép `ISOYEAR` với `WEEK` chưa?
7. Nếu GROUP BY tháng, đã giữ **năm** trong khóa chưa?
8. Filter có dùng biên nửa mở `>= start AND < next_start` không?
9. Có áp function lên cột lọc làm khó tận dụng index không?
10. Thời điểm sử dụng trong code là transaction start, statement start hay wall clock?

---

## 25. Những lỗi thường gặp và cách khắc phục

### Lỗi 1 — Coi TIMESTAMP không timezone là UTC

`TIMESTAMP '2026-11-14 09:30'` không tự mang zone. Nếu đó là giờ Việt Nam, cần gắn `AT TIME ZONE 'Asia/Ho_Chi_Minh'` để tạo instant.

### Lỗi 2 — Tin rằng TIMESTAMPTZ lưu nguyên tên timezone đầu vào

Giá trị biểu diễn instant, không bảo tồn tên vùng mà client nhập. Nếu cần biết người dùng đã chọn `Asia/Ho_Chi_Minh`, lưu riêng trường zone name.

### Lỗi 3 — Dùng date_trunc theo session thay vì zone nghiệp vụ

`date_trunc('day', occurred_at)` trên timestamptz phụ thuộc `TimeZone` của phiên. Dùng tham số timezone tường minh hoặc chuyển sang local timestamp theo vùng trước khi nhóm.

### Lỗi 4 — Dùng EXTRACT(MONTH) nhưng quên năm

Tháng 11/2025 và 11/2026 bị gộp chung. Dùng `date_trunc('month',...)` hoặc kết hợp YEAR và MONTH.

### Lỗi 5 — Ghép YEAR với WEEK ISO

Các ngày đầu/cuối năm có thể thuộc ISOYEAR khác calendar YEAR. Dùng `EXTRACT(ISOYEAR)` cùng `EXTRACT(WEEK)`.

### Lỗi 6 — Coi DOW và ISODOW giống nhau

Chủ nhật là 0 ở DOW nhưng 7 ở ISODOW. Chọn đúng quy tắc đánh số thứ.

### Lỗi 7 — Dùng BETWEEN 00:00 và 23:59:59

Bỏ sót phần giây cuối ngày. Dùng khoảng nửa mở đến **00:00 ngày kế tiếp**.

### Lỗi 8 — Cộng cứng 24 giờ để lấy cuối ngày local

Ngày DST có thể chỉ 23 hoặc tới 25 giờ. Chuyển riêng hai mốc nửa đêm local thành instant.

### Lỗi 9 — Chuyển instant sang timestamp rồi lại hiểu như instant

`timestamptz AT TIME ZONE 'Zone'` trả **timestamp không zone**. Đừng gửi giá trị đó như UTC nếu chưa gắn lại zone đúng.

### Lỗi 10 — Hiểu now() là đồng hồ thay đổi mỗi dòng

`now()` cố định tại đầu transaction; dùng `clock_timestamp()` khi thực sự cần đồng hồ tại thời điểm gọi.

### Lỗi 11 — Nghĩ một tháng luôn 30 ngày

`interval '1 month'` theo lịch, còn 30 ngày là một số ngày cố định. Cần chính sách với cuối tháng/năm nhuận.

### Lỗi 12 — GROUP BY date_trunc rồi nghĩ ngày không có giao dịch sẽ hiện COUNT=0

GROUP BY chỉ có nhóm với dữ liệu. Dùng calendar series và LEFT JOIN để lấp khoảng trống.

### Lỗi 13 — Định dạng text quá sớm

`to_char` trả TEXT, không phải instant. Giữ kiểu ngày giờ để tính toán, định dạng ở tầng ngoài cùng.

### Lỗi 14 — Lọc bằng cast trên cột khi index theo instant

`occurred_at::date = ...` có thể phụ thuộc timezone và không dùng trực tiếp index range như mong đợi. Dùng hai cận instant.

### Lỗi 15 — Dùng date_bin cho tháng lịch

`date_bin` dùng stride cố định và không chấp nhận tháng/năm. Dùng `date_trunc('month')`.

### Lỗi 16 — Chỉ lưu offset cố định cho lịch lặp ở nơi có DST

`-05:00` không đại diện New York trong cả năm. Lưu tên vùng IANA và quy tắc xử lý local time mơ hồ.

### Lỗi 17 — Test chỉ trên giờ giữa trưa

Những lỗi timezone thường chỉ xuất hiện sát **00:00**, ngày đổi DST, cuối tháng, đầu năm. Cần bổ sung ca kiểm thử biên.

### Lỗi 18 — Không xác định snapshot khi so báo cáo chạy nhiều lần

Số liệu giữa các query có thể khác do giao dịch mới hoặc timezone khác của session. Chốt mốc thời gian, timezone và phạm vi dữ liệu trước khi đối soát.

---

## 26. Bài tập thực hành

Các bài từ 1 đến 18 dùng `time_lab.events` hoặc hằng thời gian cho sẵn, trừ khi ghi chú khác.

### Bài 1 — Nhận diện kiểu

Chọn kiểu PostgreSQL phù hợp cho ngày sinh, giờ mở cửa hằng ngày, instant thanh toán, giờ hẹn 09:00 theo lịch New York và thời lượng xử lý.

### Bài 2 — Session TimeZone

Viết SQL xem `TimeZone` của phiên. Đặt tạm `Asia/Ho_Chi_Minh` trong transaction rồi xem một giá trị `timestamptz` có offset UTC.

### Bài 3 — Thời điểm hiện tại

Phân biệt `now()`, `transaction_timestamp()`, `statement_timestamp()`, `clock_timestamp()` khi một transaction có nhiều câu SQL.

### Bài 4 — date_trunc

Cắt `TIMESTAMP '2026-11-14 15:42:37'` về đầu giờ, đầu ngày, đầu tháng, đầu quý và đầu năm.

### Bài 5 — Đầu tuần

Viết truy vấn tìm đầu tuần của ngày 14/11/2026. Tuần PostgreSQL bắt đầu thứ mấy?

### Bài 6 — EXTRACT

Lấy YEAR, MONTH, DAY, HOUR từ `TIMESTAMP '2026-11-14 15:42:37'`.

### Bài 7 — DOW và ISODOW

Cho ngày Chủ nhật 15/11/2026, DOW và ISODOW bằng bao nhiêu?

### Bài 8 — ISO week

Ngày 01/01/2021 thuộc calendar year, ISO year, ISO week nào? Vì sao không nên GROUP BY YEAR + WEEK nếu muốn nhóm ISO?

### Bài 9 — UTC sang giờ Việt Nam

Chuyển `TIMESTAMPTZ '2026-11-14 02:30:00+00'` sang timestamp đồng hồ Việt Nam.

### Bài 10 — Giờ Việt Nam sang instant

Biến `TIMESTAMP '2026-11-14 09:30:00'` (được biết là giờ Việt Nam) thành timestamptz.

### Bài 11 — Phân tích dạng kết quả

`AT TIME ZONE` trả kiểu gì nếu đầu vào là timestamp? Nếu đầu vào là timestamptz?

### Bài 12 — Báo cáo ngày 14/11 ở Việt Nam

Viết truy vấn đếm event của `2026-11-14` theo lịch Việt Nam. Kết quả bao nhiêu?

### Bài 13 — Lọc theo ngày bằng range

Viết `WHERE` gồm hai cận cho **ngày 14/11 tại Việt Nam**, không bỏ sót microseconds và không lấy sự kiện đúng 00:00 ngày 15.

### Bài 14 — GROUP BY tháng

Viết truy vấn đếm số sự kiện theo tháng địa phương Việt Nam và phân biệt 2026 với 2027.

### Bài 15 — Phân tích theo giờ

Viết SQL đếm event theo giờ đồng hồ `0..23` ở Việt Nam, không chia theo ngày cụ thể.

### Bài 16 — Epoch

Lấy Unix epoch của một timestamptz. Vì sao không nên dùng EXTRACT(EPOCH FROM timestamp không zone) như instant UTC?

### Bài 17 — Chênh 30 phút

Viết biểu thức số giây giữa 10:30 UTC và 11:00 UTC trong cùng ngày. Kết quả?

### Bài 18 — DST

Vì sao ngày 08/03/2026 ở New York không dài 24 giờ? Viết SQL tính chênh lệch giữa hai mốc nửa đêm của ngày đó.

### Bài 19 — Tháng lịch

`DATE '2026-01-31' + INTERVAL '1 month'` là ngày nào? Vì sao `INTERVAL '30 days'` không tương đương?

### Bài 20 — Calendar series

Sinh các ngày 13–17/11/2026, LEFT JOIN thống kê ngày Việt Nam của event để hiện cả ngày 16 và 17 với count 0.

### Bài 21 — date_bin

Gom `TIMESTAMP '2026-11-14 10:37:42'` theo khung 15 phút, origin đầu năm 2000. Kết quả mốc nào?

### Bài 22 — Index

Giả sử có index B-tree trên `occurred_at`. Vì sao điều kiện range thường thuận lợi hơn `occurred_at::date = DATE '2026-11-14'`?

### Bài 23 — Định dạng

Hiển thị instant `2026-11-14 02:30 UTC` thành chuỗi `YYYY-MM-DD HH24:MI:SS` ở Việt Nam. Kết quả của `to_char` có kiểu gì?

### Bài 24 — Cảnh báo timezone

Một API nhận chuỗi `2026-11-14 09:30` không kèm offset. Nêu ít nhất ba điều phải làm rõ trước khi lưu.

---

## 27. Gợi ý lời giải

### Bài 1

Ngày sinh: `DATE`. Giờ mở cửa: `TIME` kèm vùng của cửa hàng theo ngữ cảnh. Instant thanh toán: `TIMESTAMPTZ`. Lịch hẹn New York: cần local date-time, tên vùng IANA và chính sách ambiguous/missing times, có thể lưu thêm instant đã chốt. Thời lượng: `INTERVAL` hoặc số giây rõ nghĩa.

### Bài 2

~~~sql
SHOW TIME ZONE;

BEGIN;
SET LOCAL TimeZone = 'Asia/Ho_Chi_Minh';
SELECT TIMESTAMPTZ '2026-11-14 02:30:00+00';
ROLLBACK;
~~~

Instant được hiển thị khoảng `09:30+07` trong transaction.

### Bài 3

`now()`, `CURRENT_TIMESTAMP` và `transaction_timestamp()` giữ đầu transaction. `statement_timestamp()` lấy đầu mỗi statement. `clock_timestamp()` đọc đồng hồ tại thời điểm gọi và có thể thay đổi trong một statement.

### Bài 4

~~~sql
SELECT
    date_trunc('hour', TIMESTAMP '2026-11-14 15:42:37'),
    date_trunc('day', TIMESTAMP '2026-11-14 15:42:37'),
    date_trunc('month', TIMESTAMP '2026-11-14 15:42:37'),
    date_trunc('quarter', TIMESTAMP '2026-11-14 15:42:37'),
    date_trunc('year', TIMESTAMP '2026-11-14 15:42:37');
~~~

Kết quả tương ứng `15:00` ngày 14, `00:00` ngày 14, đầu tháng 11, đầu quý IV (`01/10`) và `01/01/2026`.

### Bài 5

~~~sql
SELECT date_trunc('week', TIMESTAMP '2026-11-14') AS week_begin;
~~~

`2026-11-09 00:00:00`, thứ Hai.

### Bài 6

~~~sql
SELECT
    EXTRACT(YEAR FROM TIMESTAMP '2026-11-14 15:42:37'),
    EXTRACT(MONTH FROM TIMESTAMP '2026-11-14 15:42:37'),
    EXTRACT(DAY FROM TIMESTAMP '2026-11-14 15:42:37'),
    EXTRACT(HOUR FROM TIMESTAMP '2026-11-14 15:42:37');
~~~

Lần lượt **2026, 11, 14, 15**.

### Bài 7

~~~sql
SELECT
    EXTRACT(DOW FROM DATE '2026-11-15'),
    EXTRACT(ISODOW FROM DATE '2026-11-15');
~~~

**0** và **7**.

### Bài 8

~~~sql
SELECT
    EXTRACT(YEAR FROM DATE '2021-01-01'),
    EXTRACT(ISOYEAR FROM DATE '2021-01-01'),
    EXTRACT(WEEK FROM DATE '2021-01-01');
~~~

Calendar year **2021**, ISOYEAR **2020**, WEEK **53**. Năm ISO khác calendar year gần ranh giới tuần/năm.

### Bài 9

~~~sql
SELECT TIMESTAMPTZ '2026-11-14 02:30:00+00'
       AT TIME ZONE 'Asia/Ho_Chi_Minh';
~~~

`2026-11-14 09:30:00`, kiểu timestamp without time zone.

### Bài 10

~~~sql
SELECT TIMESTAMP '2026-11-14 09:30:00'
       AT TIME ZONE 'Asia/Ho_Chi_Minh';
~~~

Timestamptz tương đương instant `2026-11-14 02:30:00+00`.

### Bài 11

Timestamp không timezone `AT TIME ZONE` trả **timestamptz**; timestamptz `AT TIME ZONE` trả **timestamp without time zone**.

### Bài 12

~~~sql
SELECT COUNT(*) AS events_on_nov14_vn
FROM time_lab.events
WHERE (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
      = DATE '2026-11-14';
~~~

**3 sự kiện**, ID 2, 3 và 4. Đây là cách kiểm tra ý nghĩa, còn để tận dụng index thường nên dùng khoảng như bài 13.

### Bài 13

~~~sql
SELECT event_id, occurred_at
FROM time_lab.events
WHERE occurred_at >= (
        TIMESTAMP '2026-11-14 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
  AND occurred_at < (
        TIMESTAMP '2026-11-15 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
ORDER BY occurred_at;
~~~

Đầu bao gồm, cuối loại trừ, không mất phần giây cuối.

### Bài 14

~~~sql
SELECT
    date_trunc(
        'month',
        occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AS month_local,
    COUNT(*) AS cnt
FROM time_lab.events
GROUP BY month_local
ORDER BY month_local;
~~~

Mốc đầu tháng chứa cả năm, không gộp tháng 01/2026 và 01/2027.

### Bài 15

~~~sql
SELECT
    EXTRACT(HOUR FROM occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')
        ::integer AS local_hour,
    COUNT(*) AS cnt
FROM time_lab.events
GROUP BY local_hour
ORDER BY local_hour;
~~~

### Bài 16

~~~sql
SELECT EXTRACT(
    EPOCH FROM TIMESTAMPTZ '2026-11-14 02:30:00+00'
);
~~~

Epoch của timestamp không zone chưa định nghĩa instant ở vùng nào; muốn đúng, gắn zone trước.

### Bài 17

~~~sql
SELECT EXTRACT(
    EPOCH FROM (
        TIMESTAMPTZ '2026-11-14 11:00:00+00'
        - TIMESTAMPTZ '2026-11-14 10:30:00+00'
    )
) AS seconds_elapsed;
~~~

**1800 giây**.

### Bài 18

Ngày chuyển sang DST ở New York nhảy qua một giờ đồng hồ, nên thời gian thực giữa hai nửa đêm chỉ **23 giờ**:

~~~sql
SELECT
    (TIMESTAMP '2026-03-09 00:00:00'
        AT TIME ZONE 'America/New_York')
    -
    (TIMESTAMP '2026-03-08 00:00:00'
        AT TIME ZONE 'America/New_York') AS elapsed;
~~~

### Bài 19

`DATE '2026-01-31' + INTERVAL '1 month'` → **2026-02-28 00:00:00**. Một tháng theo lịch không có số ngày cố định; cộng 30 ngày sẽ ra mốc khác.

### Bài 20

~~~sql
WITH calendar AS (
    SELECT d::date AS local_day
    FROM generate_series(
        TIMESTAMP '2026-11-13',
        TIMESTAMP '2026-11-17',
        INTERVAL '1 day'
    ) AS g(d)
),
daily AS (
    SELECT
        (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS local_day,
        COUNT(*) AS cnt
    FROM time_lab.events
    GROUP BY local_day
)
SELECT c.local_day, COALESCE(d.cnt,0) AS event_count
FROM calendar AS c
LEFT JOIN daily AS d ON d.local_day = c.local_day
ORDER BY c.local_day;
~~~

Ngày 16 và 17 sẽ có `0`.

### Bài 21

~~~sql
SELECT date_bin(
    INTERVAL '15 minutes',
    TIMESTAMP '2026-11-14 10:37:42',
    TIMESTAMP '2000-01-01'
);
~~~

`2026-11-14 10:30:00`.

### Bài 22

Điều kiện `occurred_at >= :start_instant AND occurred_at < :end_instant` trực tiếp so cột với hai cận phù hợp B-tree, trong khi `occurred_at::date` phụ thuộc session timezone và là biểu thức trên cột, khó dùng index thường trực tiếp hơn.

### Bài 23

~~~sql
SELECT to_char(
    TIMESTAMPTZ '2026-11-14 02:30:00+00'
      AT TIME ZONE 'Asia/Ho_Chi_Minh',
    'YYYY-MM-DD HH24:MI:SS'
);
~~~

Chuỗi `2026-11-14 09:30:00`, kiểu **TEXT**.

### Bài 24

Cần xác định: đây là giờ ở **vùng nào**, người dùng muốn lưu **instant hay local appointment**, có offset/zone nào được cung cấp hoặc mặc định rõ ràng, có khả năng xảy ra DST missing/ambiguous không và cần giữ tên vùng/offset gốc không. Không tự hiểu chuỗi thiếu zone là UTC.

---

## 28. Tổng kết

**Đúng thời gian trong PostgreSQL bắt đầu từ đúng ngữ nghĩa**: `DATE` cho ngày lịch, `TIMESTAMP` cho local date-time chưa gắn vùng, `TIMESTAMPTZ` cho instant, `INTERVAL` cho khoảng thời gian/lịch.

- `date_trunc` cho mốc đầu **giờ/ngày/tuần/tháng/quý/năm**; khi đầu vào là timestamptz, phải kiểm soát timezone dùng để cắt.
- `EXTRACT` lấy **thành phần** như năm, tháng, giờ, ISODOW, ISOYEAR, WEEK, EPOCH; không tự đồng nghĩa một mốc ngày đầy đủ.
- `AT TIME ZONE` có **hai chiều**: timestamp không zone → timestamptz để gắn vùng, và timestamptz → timestamp để xem đồng hồ địa phương.
- `now()` là thời điểm đầu transaction; `statement_timestamp()` là đầu statement; `clock_timestamp()` là đồng hồ lúc gọi.
- Với **báo cáo theo ngày địa phương**, lọc bằng khoảng `>= đầu ngày local và < đầu ngày kế tiếp local` đã chuyển thành instant, không dùng ngày UTC hoặc cộng cố định 24 giờ ở vùng có DST.
- Khi truy vấn bảng lớn, ưu tiên index trên instant và range predicate rõ nghĩa; dùng `EXPLAIN` trước khi thêm expression indexes hoặc thay cấu hình bộ nhớ.

Quy trình có thể áp dụng cho mọi hệ thống: **xác định instant hay lịch → chọn kiểu thời gian → xác định timezone nghiệp vụ → xử lý DST/biên ngày → dùng date_trunc/extract đúng mục tiêu → lọc bằng khoảng nửa mở → kiểm chứng trên dữ liệu sát mốc thời gian → đo truy vấn thực tế**.

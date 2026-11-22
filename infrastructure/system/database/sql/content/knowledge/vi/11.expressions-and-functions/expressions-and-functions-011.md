# Chuyển múi giờ, cắt mốc thời gian và định dạng ngày giờ

## 1. Ba thao tác giống nhau ở bề ngoài nhưng khác mục đích

Trong SQL, dữ liệu thời gian thường được dùng để trả lời những câu hỏi rất khác nhau:

- **Chuyển múi giờ:** Một sự kiện xảy ra lúc nào trên đồng hồ địa phương của người xem? Ví dụ một sự kiện tại `2026-11-14 01:10 UTC` sẽ tương ứng `08:10` cùng ngày ở Việt Nam.
- **Cắt mốc thời gian (truncation / bucketing):** Sự kiện thuộc **giờ, ngày, tuần, tháng** nào để thống kê? Ví dụ mọi sự kiện từ `08:00:00` đến trước `09:00:00` cùng thuộc nhóm giờ `08:00`.
- **Định dạng ngày giờ:** Giá trị sẽ được **trình bày** dưới dạng chuỗi nào? Ví dụ `2026-11-14 08:10:00` thành `14/11/2026 08:10`.

Đây là ba quyết định độc lập: **múi giờ dùng để diễn giải**, **độ chi tiết dùng để nhóm/lọc**, và **chuỗi dùng để hiển thị**.

~~~text
Thời điểm thực tế của sự kiện (instant)
                 │
                 ▼
   Diễn giải theo múi giờ cần xem
     Asia/Ho_Chi_Minh / UTC / ...
                 │
           ┌─────┴──────┐
           ▼            ▼
   Cắt theo ngày/giờ    Định dạng cho người đọc
   để nhóm/lọc         "14/11/2026 08:10"
           │            │
           ▼            ▼
     Giá trị thời gian  Chuỗi văn bản
     có ý nghĩa nhóm   dùng để trình bày
~~~

**Đừng nhầm một chuỗi đã định dạng với một giá trị ngày giờ có kiểu**. Sau khi chuyển bằng hàm tạo văn bản, việc so sánh và sắp xếp có thể chuyển thành so sánh chuỗi, ảnh hưởng kết quả và khả năng tối ưu hóa.

Bài học dùng **PostgreSQL** cho các ví dụ SQL chạy xuyên suốt vì hỗ trợ rõ `TIMESTAMPTZ`, `AT TIME ZONE`, `DATE_TRUNC` và `TO_CHAR`. Nguyên tắc vẫn có thể áp dụng trên các DBMS khác, nhưng cú pháp và quy tắc của từng hệ không hoàn toàn tương đương.

## 2. Phân biệt kiểu DATE, TIME, TIMESTAMP và thời điểm có múi giờ

| Kiểu/khái niệm | Diễn giải | Ví dụ | Điều cần nhớ |
| --- | --- | --- | --- |
| `DATE` | Một **ngày lịch** | `2026-11-14` | Không tự chứa giờ hoặc múi giờ |
| `TIME` | **Giờ trong ngày** | `08:10:00` | Không chứa ngày; không đủ để xác định một thời điểm toàn cầu |
| `TIMESTAMP WITHOUT TIME ZONE` | Ngày và giờ theo **đồng hồ địa phương**, chưa gắn múi giờ | `2026-11-14 08:10:00` | Không tự biết `08:10` là giờ của Việt Nam, London hay New York |
| `TIMESTAMP WITH TIME ZONE` / PostgreSQL `TIMESTAMPTZ` | Một **thời điểm thực tế** (instant) có thể hiển thị theo nhiều vùng giờ | `2026-11-14 01:10:00+00` | PostgreSQL không lưu riêng tên múi giờ gốc trong giá trị này |
| **Time zone ID** | Bộ quy tắc vùng giờ theo địa danh, có thể có thay đổi lịch sử và DST | `Asia/Ho_Chi_Minh`, `America/New_York` | Khác với một offset cố định |
| **UTC offset** | Chênh lệch cụ thể so với UTC tại một thời điểm | `+07:00`, `-05:00` | Chỉ nói độ lệch, không mô tả toàn bộ lịch thay đổi của múi giờ |

Trong PostgreSQL, `TIMESTAMPTZ` xác định một **instant**. DBMS chuẩn hóa biểu diễn nội bộ để so sánh các thời điểm và hiển thị giá trị theo múi giờ của session khi xuất ra. Giá trị `TIMESTAMPTZ` **không giữ lại tên vùng giờ mà người dùng đã nhập**.

Ví dụ hai literal sau biểu diễn cùng một thời điểm:

~~~sql
SELECT
    TIMESTAMPTZ '2026-11-14 08:10:00+07:00'
      = TIMESTAMPTZ '2026-11-14 01:10:00+00:00'
        AS same_instant;
-- TRUE
~~~

Còn hai `TIMESTAMP WITHOUT TIME ZONE` khác nhau về giờ đồng hồ:

~~~sql
SELECT
    TIMESTAMP '2026-11-14 08:10:00'
      = TIMESTAMP '2026-11-14 01:10:00'
        AS same_wall_clock;
-- FALSE
~~~

Nếu không biết vùng giờ đi kèm, không thể khẳng định hai giá trị timestamp không múi giờ có cùng instant hay không.

### Lỗi tinh vi khi khai báo literal

PostgreSQL quyết định kiểu theo từ khóa `TIMESTAMP` / `TIMESTAMPTZ`, **không chỉ dựa vào dấu offset trong chuỗi**:

~~~sql
-- Có thông tin offset vì literal mang kiểu TIMESTAMPTZ:
SELECT TIMESTAMPTZ '2026-11-14 08:10:00+07:00';

-- Kiểu TIMESTAMP không múi giờ: offset trong literal bị bỏ qua
-- theo cách phân tích của PostgreSQL cho kiểu này.
SELECT TIMESTAMP '2026-11-14 08:10:00+07:00';
~~~

Do đó không nên nghĩ chỉ cần nối `+07:00` vào chuỗi `TIMESTAMP` là dữ liệu sẽ trở thành thời điểm tuyệt đối.

Trong ứng dụng, hãy chọn kiểu theo ý nghĩa: ngày sinh thường là `DATE`; giờ mở cửa lặp lại có thể là `TIME` cộng vùng giờ/lịch phù hợp; thời điểm tạo đơn hàng hoặc phát sinh sự kiện thường cần biểu diễn **instant** rõ ràng.

## 3. Dữ liệu mẫu: log sự kiện đi qua ranh giới ngày Việt Nam

Tạo bảng với timestamp có múi giờ trong PostgreSQL:

~~~sql
CREATE TABLE app_events (
    event_id    BIGINT PRIMARY KEY,
    event_name  VARCHAR(100) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL
);

INSERT INTO app_events (event_id, event_name, occurred_at)
VALUES
    (1, 'Truoc ngay VN',  TIMESTAMPTZ '2026-11-13 16:59:00+00'),
    (2, 'Qua nua dem',   TIMESTAMPTZ '2026-11-13 17:30:00+00'),
    (3, 'Buoi sang A',   TIMESTAMPTZ '2026-11-14 01:10:00+00'),
    (4, 'Cuoi ngay VN',  TIMESTAMPTZ '2026-11-14 16:55:00+00'),
    (5, 'Sang ngay moi', TIMESTAMPTZ '2026-11-14 17:05:00+00'),
    (6, 'Ngay ke tiep',  TIMESTAMPTZ '2026-11-15 03:00:00+00'),
    (7, 'Buoi sang B',   TIMESTAMPTZ '2026-11-14 01:45:00+00');
~~~

Để xem đồng thời instant dưới dạng UTC và giờ địa phương Việt Nam, hãy chuyển tường minh theo vùng giờ:

~~~sql
SELECT
    event_id,
    event_name,
    occurred_at AT TIME ZONE 'UTC' AS utc_clock,
    occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh' AS vn_clock
FROM app_events
ORDER BY event_id;
~~~

Kết quả theo đồng hồ ở từng vùng giờ:

| ID | Tên sự kiện | Đồng hồ UTC | Đồng hồ Việt Nam |
| ---: | --- | --- | --- |
| 1 | Truoc ngay VN | 2026-11-13 16:59 | 2026-11-13 23:59 |
| 2 | Qua nua dem | 2026-11-13 17:30 | 2026-11-14 00:30 |
| 3 | Buoi sang A | 2026-11-14 01:10 | 2026-11-14 08:10 |
| 4 | Cuoi ngay VN | 2026-11-14 16:55 | 2026-11-14 23:55 |
| 5 | Sang ngay moi | 2026-11-14 17:05 | 2026-11-15 00:05 |
| 6 | Ngay ke tiep | 2026-11-15 03:00 | 2026-11-15 10:00 |
| 7 | Buoi sang B | 2026-11-14 01:45 | 2026-11-14 08:45 |

Tại thời điểm các sự kiện mẫu, `Asia/Ho_Chi_Minh` có độ lệch `UTC+07:00`. Vì vậy thời điểm `2026-11-13 17:30 UTC` đã sang **00:30 ngày 14/11** theo đồng hồ Việt Nam.

Ở truy vấn trên, hai cột `utc_clock` và `vn_clock` là **timestamp không múi giờ được tạo ra để xem đồng hồ của từng vùng**. Chúng không còn tự mang thông tin vùng giờ sau phép `AT TIME ZONE` theo cách dùng này. Để tiếp tục lưu và so sánh instant, hãy giữ `occurred_at` kiểu `TIMESTAMPTZ`.

## 4. Chuyển múi giờ bằng AT TIME ZONE trong PostgreSQL

### 4.1. Từ instant đến đồng hồ địa phương

Khi toán hạng bên trái là `TIMESTAMPTZ`:

~~~sql
<timestamptz_expression> AT TIME ZONE '<zone_name>'
~~~

kết quả là **`TIMESTAMP WITHOUT TIME ZONE`**, hiển thị mặt đồng hồ tương ứng ở vùng được yêu cầu.

Ví dụ:

~~~sql
SELECT
    TIMESTAMPTZ '2026-11-14 01:10:00+00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
        AS local_time;
-- 2026-11-14 08:10:00
~~~

Tương tự, cùng instant này có thể được xem theo `UTC` hoặc vùng giờ khác:

~~~sql
SELECT
    occurred_at,
    occurred_at AT TIME ZONE 'UTC' AS utc_time,
    occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh' AS vietnam_time,
    occurred_at AT TIME ZONE 'America/New_York' AS new_york_time
FROM app_events
WHERE event_id = 3;
~~~

Ba cột đồng hồ là ba cách nhìn **cùng một instant**. Kết quả ở New York phụ thuộc quy tắc múi giờ của ngày sự kiện, không được suy bằng cách cộng/trừ một offset mặc định cho cả năm.

### 4.2. Từ đồng hồ địa phương đến instant

Khi toán hạng bên trái là `TIMESTAMP WITHOUT TIME ZONE`:

~~~sql
<timestamp_without_tz_expression> AT TIME ZONE '<zone_name>'
~~~

PostgreSQL **giải thích đồng hồ bên trái thuộc vùng giờ đã nêu**, rồi tạo ra `TIMESTAMPTZ` (một instant).

Ví dụ người dùng đăng ký cuộc hẹn lúc `08:10` ngày `14/11/2026` tại Việt Nam:

~~~sql
SELECT
    (
        TIMESTAMP '2026-11-14 08:10:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AT TIME ZONE 'UTC' AS instant_in_utc;
-- 2026-11-14 01:10:00
~~~

Hai lần `AT TIME ZONE` thực hiện hai hướng khác nhau:

1. `TIMESTAMP 08:10` + vùng `Asia/Ho_Chi_Minh` → **instant**.
2. Instant vừa xác định + vùng `UTC` → giá trị **đồng hồ UTC** để quan sát.

Nếu thay vùng của bước đầu bằng `UTC`, ý nghĩa instant sẽ khác **7 giờ** trong ví dụ này. Vì vậy phải biết dữ liệu đầu vào là **giờ địa phương ở đâu**, không tự cho mọi `TIMESTAMP` là UTC.

### 4.3. Hai cách dùng cùng tên dễ bị nhầm

| Đầu vào PostgreSQL | Biểu thức | Kiểu kết quả | Ý nghĩa |
| --- | --- | --- | --- |
| `TIMESTAMPTZ` | `instant AT TIME ZONE 'Asia/Ho_Chi_Minh'` | `TIMESTAMP` không múi giờ | Xem đồng hồ tại Việt Nam của instant |
| `TIMESTAMP` không múi giờ | `local_clock AT TIME ZONE 'Asia/Ho_Chi_Minh'` | `TIMESTAMPTZ` | Diễn giải đồng hồ này thuộc Việt Nam và xác định instant |

`AT TIME ZONE` **không phải** lúc nào cũng “đổi offset rồi giữ nguyên kiểu”. Kiểu toán hạng quyết định hướng chuyển.

### 4.4. Session time zone ảnh hưởng kết quả hiển thị

PostgreSQL có tham số session `TimeZone`. Khi truy vấn trực tiếp một `TIMESTAMPTZ`, cách hiển thị (và một số phép lấy thành phần/cắt mốc) phụ thuộc múi giờ session:

~~~sql
SHOW TIME ZONE;

SELECT occurred_at
FROM app_events
WHERE event_id = 3;
~~~

Cùng một instant có thể xuất hiện với `+00` hoặc `+07` tùy cấu hình session. Vì vậy, trong API hoặc báo cáo cần vùng giờ cụ thể, nên **chỉ rõ vùng giờ trong truy vấn/logic trình bày** thay vì tin rằng mọi kết nối đều dùng cùng một thiết lập.

Trong connection pool, thay đổi múi giờ session mà không khôi phục trạng thái có thể ảnh hưởng request khác dùng lại kết nối. Tạo phép chuyển tường minh thường dễ kiểm soát hơn phụ thuộc cấu hình session ngầm.

## 5. Múi giờ theo địa danh khác offset cố định

`+07:00` nói rằng một đồng hồ đang nhanh hơn UTC 7 giờ **tại một instant**. `Asia/Ho_Chi_Minh` là tên vùng giờ theo cơ sở dữ liệu múi giờ (IANA), có các quy tắc lịch sử. Những nơi áp dụng **daylight saving time (DST)** có thể chuyển offset theo mùa:

~~~text
UTC instant
    |
    +--> Asia/Ho_Chi_Minh  (quy tắc vùng giờ tại ngày đó)
    |
    +--> America/New_York (có thể -05:00 hoặc -04:00 tùy ngày)
    |
    +--> Europe/Berlin    (có thể +01:00 hoặc +02:00 tùy ngày)
~~~

Không nên dùng `-05:00` như tên thay thế cố định cho `America/New_York` khi ứng dụng có dữ liệu qua nhiều tháng hoặc năm. Trên những ngày chuyển DST, một ngày địa phương có thể dài **23 giờ hoặc 25 giờ**, không phải lúc nào cũng 24 giờ.

Có hai vấn đề khi nhập **giờ đồng hồ địa phương** tại vùng có DST:

- **Giờ không tồn tại:** khi đồng hồ nhảy từ khoảng 02:00 lên 03:00, một số mốc trong khoảng 02:00–02:59 không xảy ra ở vùng đó.
- **Giờ lặp lại:** khi đồng hồ lùi một giờ, một giá trị như 01:30 có thể tương ứng **hai instant** khác nhau.

Ví dụ ở `America/New_York` trong năm 2026, ngày chuyển sang DST vào mùa xuân có khoảng giờ bị bỏ qua; ngày kết thúc DST vào mùa thu có khoảng giờ lặp. Nếu ứng dụng chỉ nhận `2026-11-01 01:30` và `America/New_York` mà không có thêm quy tắc/chỉ báo offset, ý nghĩa instant có thể **không duy nhất**. DBMS có thể áp dụng quy tắc mặc định để chọn một cách diễn giải, nhưng đó chưa chắc là ý người dùng.

Khi đặt lịch tương lai cho một múi giờ có DST, nên lưu đủ **ngày giờ địa phương, tên vùng giờ và quyết định xử lý giờ mơ hồ/không tồn tại** nếu nghiệp vụ yêu cầu. Khi sự kiện đã thực sự xảy ra, lưu **instant** giúp sắp xếp và so sánh chính xác. Đừng tự cộng `INTERVAL '7 hours'` hay `INTERVAL '24 hours'` để thay thế hoàn toàn việc chuyển múi giờ theo vùng.

## 6. Cắt mốc thời gian bằng DATE_TRUNC

**Cắt mốc (truncation)** đưa một ngày giờ về **đầu đơn vị thời gian** được chọn, chẳng hạn đầu giờ, đầu ngày, đầu tháng. Điều này thường dùng để nhóm dữ liệu vào các khoảng thời gian:

~~~text
2026-11-14 08:10:27
       │         │
       │         └── Cắt theo phút → 2026-11-14 08:10:00
       ├──────────── Cắt theo giờ  → 2026-11-14 08:00:00
       └──────────── Cắt theo ngày → 2026-11-14 00:00:00
                     Cắt theo tháng→ 2026-11-01 00:00:00
~~~

Trong PostgreSQL:

~~~sql
SELECT
    DATE_TRUNC('minute', TIMESTAMP '2026-11-14 08:10:27') AS minute_start,
    DATE_TRUNC('hour',   TIMESTAMP '2026-11-14 08:10:27') AS hour_start,
    DATE_TRUNC('day',    TIMESTAMP '2026-11-14 08:10:27') AS day_start,
    DATE_TRUNC('month',  TIMESTAMP '2026-11-14 08:10:27') AS month_start;
~~~

`DATE_TRUNC` là một **hàm trên giá trị thời gian**, khác với `TO_CHAR` chuyển thành chuỗi. Với `TIMESTAMP` không múi giờ, kết quả của ví dụ trên vẫn là timestamp không múi giờ.

### 6.1. Cắt sau khi xác định vùng giờ địa phương

Muốn nhóm sự kiện theo **giờ ở Việt Nam**, hãy đổi instant thành đồng hồ Việt Nam trước rồi cắt theo giờ:

~~~sql
SELECT
    DATE_TRUNC(
        'hour',
        occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AS vn_hour,
    COUNT(*) AS event_count
FROM app_events
GROUP BY vn_hour
ORDER BY vn_hour;
~~~

Kết quả gồm các nhóm:

| Giờ địa phương (đầu giờ) | event_count |
| --- | ---: |
| 2026-11-13 23:00:00 | 1 |
| 2026-11-14 00:00:00 | 1 |
| 2026-11-14 08:00:00 | 2 |
| 2026-11-14 23:00:00 | 1 |
| 2026-11-15 00:00:00 | 1 |
| 2026-11-15 10:00:00 | 1 |

Hai sự kiện ID 3 (`08:10`) và ID 7 (`08:45`) cùng thuộc bucket `08:00` ngày 14/11.

Cột `vn_hour` là **nhãn timestamp không múi giờ của giờ địa phương**. Đối với vùng có DST, một bucket đồng hồ lặp lại (ví dụ `01:00` của ngày lùi giờ) có thể đại diện cho **hai giờ thực tế khác nhau** nếu chỉ nhóm theo timestamp đồng hồ. Nếu nghiệp vụ cần phân biệt hai bucket đó, hãy dùng **instant đầu bucket** hoặc thêm thông tin offset/vùng giờ, không chỉ dùng nhãn giờ hiển thị.

### 6.2. Nhóm theo ngày địa phương

Để đếm số sự kiện theo **ngày ở Việt Nam**:

~~~sql
SELECT
    (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
        AS vn_date,
    COUNT(*) AS event_count
FROM app_events
GROUP BY vn_date
ORDER BY vn_date;
~~~

Kết quả:

| vn_date | event_count |
| --- | ---: |
| 2026-11-13 | 1 |
| 2026-11-14 | 4 |
| 2026-11-15 | 2 |

Ở đây `::DATE` là cú pháp ép kiểu PostgreSQL. Viết đầy đủ bằng `CAST(... AS DATE)` cũng có thể dùng:

~~~sql
SELECT
    CAST(
        occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        AS DATE
    ) AS vn_date,
    COUNT(*) AS event_count
FROM app_events
GROUP BY
    CAST(
        occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        AS DATE
    )
ORDER BY vn_date;
~~~

Cách này nhóm theo **ngày lịch**, không yêu cầu biến ngày thành chuỗi `DD/MM/YYYY`.

### 6.3. DATE_TRUNC trên TIMESTAMPTZ và vùng giờ

Trong PostgreSQL, cắt trực tiếp `TIMESTAMPTZ` theo ngày/giờ mà **không chỉ rõ vùng giờ** có thể dựa vào múi giờ session. Nếu cần bucket theo Việt Nam, có thể dùng cú pháp ba đối số của PostgreSQL:

~~~sql
SELECT
    DATE_TRUNC(
        'day',
        occurred_at,
        'Asia/Ho_Chi_Minh'
    ) AS vn_day_start_instant
FROM app_events
ORDER BY event_id;
~~~

Hàm trên trả **`TIMESTAMPTZ`**, tức **instant tương ứng với đầu ngày địa phương Việt Nam** của từng sự kiện. Cách hiển thị instant này vẫn tùy múi giờ session. Điều này khác với:

~~~sql
DATE_TRUNC(
    'day',
    occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
)
~~~

Biểu thức thứ hai tạo **`TIMESTAMP WITHOUT TIME ZONE`** mang giá trị đồng hồ `00:00` của ngày địa phương. Hai kết quả có ý nghĩa liên quan nhưng **khác kiểu**: một là instant, một là mốc đồng hồ địa phương.

### 6.4. Cắt theo tuần và tháng

~~~sql
SELECT
    DATE_TRUNC(
        'week',
        occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AS vn_week_start,
    DATE_TRUNC(
        'month',
        occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AS vn_month_start
FROM app_events
ORDER BY event_id;
~~~

PostgreSQL dùng **thứ Hai** làm đầu tuần khi cắt theo `week`. Quy ước tuần đầu năm và cách đặt nhãn năm-tuần cần chú ý: ISO week có thể bắt đầu từ cuối năm dương lịch trước hoặc kéo sang đầu năm kế tiếp. Nếu tạo nhãn tuần theo ISO, cần kết hợp đúng **ISO year** và **ISO week**, không ghép tùy tiện năm dương lịch với số tuần ISO.

Đối với thống kê theo tháng, bucket tốt thường là giá trị **đầu tháng có kiểu thời gian** hoặc một cặp năm/tháng rõ nghĩa. Tránh lấy `'11/2026'` làm khóa sắp xếp nếu sau này so sánh qua nhiều năm.

## 7. Lọc toàn bộ ngày địa phương: dùng khoảng nửa mở

Một yêu cầu thường gặp là: “Lấy mọi sự kiện xảy ra trong **ngày 14/11/2026 theo giờ Việt Nam**”.

Cách dễ đọc nhưng có thể ảnh hưởng việc sử dụng chỉ mục thông thường trên `occurred_at` là biến đổi **cột** trong `WHERE`:

~~~sql
SELECT event_id, event_name
FROM app_events
WHERE
    (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
    = DATE '2026-11-14'
ORDER BY occurred_at, event_id;
~~~

Kết quả sẽ có ID **2, 3, 7, 4**, theo thời điểm tăng dần.

Với dữ liệu nhiều, một cách thường thuận lợi hơn cho bộ tối ưu là **tính hai đầu mút ngày địa phương thành instant**, rồi so sánh trực tiếp với cột `TIMESTAMPTZ`:

~~~sql
SELECT event_id, event_name, occurred_at
FROM app_events
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

Hai ranh giới ở Việt Nam tương ứng:

| Ranh giới | Theo đồng hồ VN | Instant theo UTC |
| --- | --- | --- |
| Bắt đầu, **gồm cả** | 2026-11-14 00:00:00 | 2026-11-13 17:00:00+00 |
| Kết thúc, **không gồm** | 2026-11-15 00:00:00 | 2026-11-14 17:00:00+00 |

Mẫu lọc là **khoảng nửa mở** `[start, end)`:

~~~text
Bắt đầu ngày 14 VN                      Bắt đầu ngày 15 VN
       |                                        |
       v                                        v
       [----------------------------------------)
        Tất cả instant thuộc ngày 14 Việt Nam
~~~

Ưu điểm:

- Không phải đoán “thời điểm cuối ngày” là `23:59:59`, `23:59:59.999` hay có độ chính xác microsecond.
- Sự kiện đúng mốc đầu ngày kế tiếp không bị tính vào ngày trước.
- Các khoảng liên tiếp không chồng lấn và không để lại khe hở.
- Điều kiện so sánh trực tiếp cột `occurred_at` có thể được tối ưu tốt với **B-tree index** phù hợp.

### Vì sao không dùng BETWEEN cho một ngày?

~~~sql
-- Dễ bỏ sót sự kiện ở cuối ngày:
WHERE occurred_at BETWEEN
      TIMESTAMPTZ '2026-11-13 17:00:00+00'
  AND TIMESTAMPTZ '2026-11-14 16:59:59+00'
~~~

`BETWEEN` gồm **cả hai đầu mút**. Nếu hệ lưu phần lẻ giây, sự kiện lúc `16:59:59.500+00` không nằm trong khoảng kết thúc lúc `16:59:59`. Nếu đặt đầu mút là `17:00:00+00` và dùng `BETWEEN`, lại tính cả sự kiện đúng nửa đêm ngày 15. Mẫu `>= start AND < end` tránh cả hai vấn đề.

### Ranh giới ngày địa phương không nhất thiết cách nhau 24 giờ UTC

Với `Asia/Ho_Chi_Minh` trong ví dụ hiện tại, ngày 14/11/2026 có hai ranh giới cách nhau 24 giờ. Nhưng ở vùng có DST, ngày chuyển giờ có thể dài 23 hoặc 25 giờ.

Do đó để lọc một ngày địa phương ở `America/New_York`, hãy xác định:

~~~sql
-- Hai MIDNIGHT địa phương riêng biệt,
-- rồi chuyển mỗi mốc sang instant.
WHERE occurred_at >= (
        TIMESTAMP '2026-03-08 00:00:00'
        AT TIME ZONE 'America/New_York'
    )
  AND occurred_at < (
        TIMESTAMP '2026-03-09 00:00:00'
        AT TIME ZONE 'America/New_York'
    )
~~~

Đừng luôn lấy instant đầu ngày rồi cộng **24 giờ tuyệt đối** để ra cuối ngày địa phương. “Ngày kế tiếp” là thao tác **trên lịch địa phương** trước khi chuyển sang instant.

### Chỉ mục cho truy vấn theo thời gian

~~~sql
CREATE INDEX idx_app_events_occurred_at
ON app_events (occurred_at);
~~~

Bộ tối ưu có thể sử dụng chỉ mục này cho khoảng thời gian trên cột `occurred_at`. Điều kiện `WHERE (occurred_at AT TIME ZONE ...)::DATE = ...` có thể cần expression index hoặc kế hoạch khác; hiệu năng phụ thuộc DBMS và phân bố dữ liệu. Với bảng chỉ bảy hàng, quét toàn bảng vẫn có thể là kế hoạch tốt nhất. Khi dữ liệu lớn, hãy dùng `EXPLAIN` và phép đo thực tế.

## 8. Định dạng ngày giờ bằng TO_CHAR

Sau khi đã chọn múi giờ và tính toán xong, ta mới quyết định **cách hiển thị**.

Trong PostgreSQL, `TO_CHAR(timestamp_expression, pattern)` trả **TEXT**:

~~~sql
SELECT
    event_id,
    TO_CHAR(
        occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh',
        'DD/MM/YYYY HH24:MI'
    ) AS vn_display_time
FROM app_events
ORDER BY occurred_at, event_id;
~~~

Ví dụ ID 3 sẽ hiển thị `14/11/2026 08:10`; ID 5 là `15/11/2026 00:05`.

### Các ký hiệu định dạng thường dùng trong PostgreSQL

| Token | Nghĩa | Ví dụ |
| --- | --- | --- |
| `YYYY` | Năm bốn chữ số | `2026` |
| `MM` | Tháng hai chữ số | `11` |
| `DD` | Ngày trong tháng hai chữ số | `14` |
| `HH24` | Giờ theo 24 giờ | `08`, `23` |
| `HH12` | Giờ theo 12 giờ | `08`, `11` |
| `MI` | Phút | `10` |
| `SS` | Giây | `27` |
| `MS` | Mili giây | `123` |
| `US` | Micro giây | `123456` |
| `Mon`, `Month` | Tên tháng dạng viết tắt/đầy đủ | Tùy quy tắc ngôn ngữ đầu ra |
| `FM` | Modifier để bớt padding ở các mẫu áp dụng | `FMMonth` |

Ví dụ:

~~~sql
SELECT
    TO_CHAR(
        TIMESTAMP '2026-11-14 08:10:27',
        'YYYY-MM-DD HH24:MI:SS'
    ) AS iso_like_text,
    TO_CHAR(
        TIMESTAMP '2026-11-14 08:10:27',
        'DD/MM/YYYY HH24:MI'
    ) AS vi_display_text;
~~~

Kết quả:

| iso_like_text | vi_display_text |
| --- | --- |
| 2026-11-14 08:10:27 | 14/11/2026 08:10 |

Chú ý: `MI` nghĩa là **phút**, còn `MM` nghĩa là **tháng**. Không thể tự thay token theo quy tắc của Java hay JavaScript, vì mỗi hệ có ngôn ngữ pattern riêng.

### Định dạng phải đi sau chuyển múi giờ

Nếu format trực tiếp `TIMESTAMPTZ`:

~~~sql
SELECT TO_CHAR(
    occurred_at,
    'DD/MM/YYYY HH24:MI'
) AS display_time
FROM app_events;
~~~

kết quả phụ thuộc **múi giờ session PostgreSQL**. Nếu yêu cầu rõ “giờ Việt Nam”, viết tường minh:

~~~sql
SELECT TO_CHAR(
    occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh',
    'DD/MM/YYYY HH24:MI'
) AS display_time_vn
FROM app_events;
~~~

Lúc này chuỗi cho biết **giờ đồng hồ Việt Nam** nhưng không tự chứa offset hoặc tên vùng giờ. Nếu người dùng cần phân biệt múi giờ, phải thêm nhãn chính xác ở giao diện hoặc dùng biểu diễn ISO 8601 có offset.

### Đừng dùng chuỗi định dạng làm khóa sắp xếp ngày

~~~sql
-- Câu truy vấn dễ tạo thứ tự sai khi xét qua tháng/năm:
SELECT
    TO_CHAR(occurred_at, 'DD/MM/YYYY') AS display_date
FROM app_events
ORDER BY display_date;
~~~

`ORDER BY display_date` ở đây sắp theo **văn bản**. Chuỗi `02/12/2026` có thể đứng trước `14/11/2026` theo thứ tự từ điển, dù ngày 02/12 nằm sau tháng 11.

Muốn sắp theo instant:

~~~sql
SELECT
    event_id,
    TO_CHAR(
        occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh',
        'DD/MM/YYYY HH24:MI'
    ) AS display_time
FROM app_events
ORDER BY occurred_at ASC, event_id ASC;
~~~

Hoặc muốn sắp theo ngày địa phương:

~~~sql
ORDER BY (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE,
         occurred_at,
         event_id;
~~~

Chuỗi được dùng để hiển thị; phép so sánh ngày giờ vẫn dựa trên **giá trị thời gian có kiểu**.

## 9. Định dạng ở database hay ở ứng dụng?

Các ứng dụng nhiều người dùng thường có những quy tắc khác nhau về ngôn ngữ và múi giờ. Vì vậy nên tách:

| Lớp | Vai trò thông thường | Ví dụ |
| --- | --- | --- |
| Database | Lưu instant/ngày với kiểu phù hợp; lọc, nhóm, tổng hợp | `TIMESTAMPTZ`, `DATE_TRUNC`, khoảng `[start,end)` |
| Service/API | Xác định thời điểm, vùng giờ cần dùng, hợp đồng dữ liệu | ISO 8601 có `Z`/offset; mã múi giờ IANA |
| UI/báo cáo | Chọn ngôn ngữ, cách in ngày và giờ, hiển thị tên vùng | `14/11/2026 08:10` cho người Việt |

Ví dụ API có thể trả:

~~~json
{
  "eventId": 3,
  "occurredAt": "2026-11-14T01:10:00Z",
  "displayTimeZone": "Asia/Ho_Chi_Minh"
}
~~~

Client nhận một **instant** rõ ràng, rồi hiển thị trong vùng giờ người dùng đã chọn. Nếu trả sẵn `"14/11/2026 08:10"` mà không nêu vùng giờ, consumer khác có thể hiểu sai hoặc không chuyển được sang vùng giờ khác.

Với Java:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

Instant eventInstant = Instant.parse("2026-11-14T01:10:00Z");
ZoneId viewerZone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime local = eventInstant.atZone(viewerZone);

DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("dd/MM/uuuu HH:mm", Locale.forLanguageTag("vi-VN"));

String label = local.format(formatter);
// "14/11/2026 08:10"
~~~

Ở đây:

- `Instant` biểu diễn thời điểm toàn cầu.
- `ZoneId` biểu diễn vùng giờ.
- `ZonedDateTime` diễn giải instant theo vùng giờ đó.
- `DateTimeFormatter` tạo văn bản trình bày.

Trong JavaScript hiện đại, định dạng có thể dùng `Intl.DateTimeFormat` và `timeZone` tường minh:

~~~javascript
const instant = new Date("2026-11-14T01:10:00Z");

const formatter = new Intl.DateTimeFormat("vi-VN", {
  timeZone: "Asia/Ho_Chi_Minh",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23"
});

const displayText = formatter.format(instant);
// Giá trị trình bày theo vi-VN và múi giờ Việt Nam.
~~~

Hình thức dấu phân tách, khoảng trắng và thứ tự ký tự có thể phụ thuộc implementation locale; đừng dùng văn bản UI đã format làm khóa dữ liệu hoặc để so sánh chính xác.

Trong JDBC, một cột PostgreSQL `TIMESTAMPTZ` có thể được truy xuất bằng `OffsetDateTime` theo khả năng của driver; sau đó chuyển thành `Instant` rồi format theo `ZoneId` phù hợp. Với `TIMESTAMP WITHOUT TIME ZONE`, `LocalDateTime` thường phản ánh đúng việc **chưa biết vùng giờ**. Không ép `LocalDateTime` thành instant bằng cách tự giả định múi giờ của máy chủ.

## 10. Các hệ quản trị không dùng cùng một cú pháp

Nguyên lý phải thống nhất, còn cách chuyển vùng giờ, cắt mốc và định dạng thay đổi theo **SQL dialect**.

| Hệ quản trị | Chuyển múi giờ | Cắt mốc/nhóm thời gian | Định dạng văn bản |
| --- | --- | --- | --- |
| PostgreSQL | `AT TIME ZONE`; `timezone(...)` | `DATE_TRUNC`, `EXTRACT`, cast `DATE` | `TO_CHAR` |
| MySQL/MariaDB | `CONVERT_TZ(datetime, from_tz, to_tz)` | `DATE(...)`, `YEAR(...)`, `MONTH(...)`, biểu thức theo đơn vị | `DATE_FORMAT` |
| SQL Server | `AT TIME ZONE` với tên vùng Windows | `DATETRUNC` trên các phiên bản hỗ trợ (SQL Server 2022+), hoặc `DATEADD`/`DATEDIFF` theo nhu cầu | `FORMAT`/`CONVERT`, với semantics riêng |
| Oracle | `FROM_TZ`, `AT TIME ZONE` và các kiểu thời gian tương ứng | `TRUNC` đối với ngày/timestamp, các hàm lịch | `TO_CHAR` |
| SQLite | Không có engine múi giờ IANA đầy đủ tương đương PostgreSQL; các modifier như `'localtime'` có giới hạn | `date`, `strftime` và modifier thời gian | `strftime`, hàm date/time |

### Ví dụ MySQL: cột DATETIME được quy ước lưu đồng hồ UTC

~~~sql
-- Giả sử occurred_at_utc là DATETIME lưu giá trị đồng hồ UTC,
-- KHÔNG phải TIMESTAMP được session tự chuyển đổi.
SELECT
    event_id,
    CONVERT_TZ(
        occurred_at_utc,
        '+00:00',
        'Asia/Ho_Chi_Minh'
    ) AS vn_local_clock
FROM app_events;
~~~

Để nhóm theo ngày Việt Nam:

~~~sql
SELECT
    DATE(
        CONVERT_TZ(
            occurred_at_utc,
            '+00:00',
            'Asia/Ho_Chi_Minh'
        )
    ) AS vn_date,
    COUNT(*) AS event_count
FROM app_events
GROUP BY vn_date
ORDER BY vn_date;
~~~

MySQL cần **cấu hình dữ liệu bảng múi giờ** phù hợp để dùng tên vùng như `Asia/Ho_Chi_Minh`; nếu thiếu dữ liệu múi giờ, `CONVERT_TZ` với tên vùng có thể trả `NULL`. Cột MySQL `TIMESTAMP` có cơ chế tự chuyển giữa UTC và múi giờ session khác với `DATETIME`, nên không được áp dụng lại `CONVERT_TZ` như ví dụ trên mà chưa xác định rõ ý nghĩa/kiểu dữ liệu gốc, tránh **chuyển múi giờ hai lần**.

### Ví dụ SQL Server: tên vùng giờ Windows

SQL Server dùng `AT TIME ZONE` với định danh vùng giờ của hệ sinh thái Windows:

~~~sql
SELECT
    (
        CAST('2026-11-14T01:10:00' AS datetime2)
        AT TIME ZONE 'UTC'
    ) AT TIME ZONE 'SE Asia Standard Time' AS vietnam_time;
~~~

Trong ví dụ, `datetime2` đầu vào được **xác định là đồng hồ UTC**; bước thứ nhất gắn vùng UTC, bước sau chuyển instant sang vùng thường đại diện giờ Việt Nam trong Windows. `SE Asia Standard Time` là **tên vùng Windows**, không phải tên IANA `Asia/Ho_Chi_Minh` mà PostgreSQL dùng.

### SQLite và việc chuyển vùng giờ

SQLite có các hàm `date`, `time`, `datetime` và `strftime`, nhưng không cung cấp đầy đủ chức năng chuyển theo mọi tên vùng IANA và lịch sử DST như các hệ có cơ sở dữ liệu vùng giờ chuyên dụng. Modifier `'localtime'` phụ thuộc múi giờ/cấu hình môi trường chạy, không tự cung cấp phép chuyển bất kỳ từ một tên vùng IANA này sang tên khác.

Nếu ứng dụng SQLite phải hiển thị theo nhiều vùng giờ, cách thường dễ kiểm soát là lưu instant theo hợp đồng rõ ràng và dùng thư viện múi giờ của ứng dụng để chuyển/format.

**Không tự đồng nhất** `TIMESTAMP`, `DATETIME`, `TIMESTAMPTZ` hay `datetimeoffset` giữa các DBMS. Hãy kiểm tra kiểu gốc, session time zone, khả năng lưu offset/tên vùng, và các phiên bản hỗ trợ tính năng trước khi chuyển code SQL.

## 11. Current time và bộ lọc ngày hôm nay

Một số biểu thức rất quen thuộc:

~~~sql
SELECT
    CURRENT_DATE,
    CURRENT_TIMESTAMP;
~~~

Trong PostgreSQL:

- `CURRENT_DATE` được suy từ ngày hiện tại theo múi giờ session.
- `CURRENT_TIMESTAMP`/`NOW()` biểu diễn timestamp gắn với **thời điểm bắt đầu transaction** theo ngữ nghĩa PostgreSQL; nhiều lần đọc trong cùng transaction có thể cho cùng giá trị.
- `CLOCK_TIMESTAMP()` phản ánh thời gian đồng hồ thực khi hàm được gọi.

Các DBMS khác có quy tắc riêng cho hàm thời gian hiện tại. Đừng dùng tên hàm như một bảo đảm nó luôn thay đổi sau mỗi câu lệnh hoặc mỗi hàng.

Nếu muốn “ngày hôm nay theo người dùng ở Việt Nam”, đừng mặc định `CURRENT_DATE` của kết nối ở UTC là đúng:

~~~sql
SELECT
    (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
        AS today_in_vietnam;
~~~

Khi muốn lọc sự kiện cho **ngày Việt Nam hiện tại** theo ranh giới địa phương, có thể lấy ngày địa phương rồi chuyển hai mốc nửa đêm sang instant. Với báo cáo dùng dữ liệu lịch sử, tốt hơn hết là truyền ngày mong muốn như tham số từ ứng dụng thay vì phụ thuộc thời gian hệ thống lúc thực thi.

Phân biệt “**trong 24 giờ vừa qua**” với “**trong ngày lịch hôm nay**”:

- `occurred_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours'` là khoảng 24 giờ trượt từ thời điểm hiện tại.
- “Từ nửa đêm ngày hôm nay ở vùng giờ X đến trước nửa đêm ngày mai” là khoảng ngày lịch địa phương, có thể không bằng 24 giờ ở vùng có DST.

Hai truy vấn phục vụ yêu cầu nghiệp vụ khác nhau.

## 12. Các lỗi phổ biến với ngày giờ

| Cách làm dễ sai | Vì sao sai hoặc rủi ro | Cách tiếp cận |
| --- | --- | --- |
| Xem `TIMESTAMP` không múi giờ là UTC mặc định | Kiểu này không tự lưu vùng giờ | Quy định rõ ngữ nghĩa cột; lưu instant nếu cần |
| Dùng offset `-05:00` cho mọi ngày ở New York | DST và lịch sử vùng giờ có thể đổi offset | Dùng `America/New_York` theo ngày |
| Đổi múi giờ bằng cộng cố định `INTERVAL '7 hours'` trong mọi ngữ cảnh | Không mô tả đầy đủ vùng giờ/DST | Dùng phép chuyển vùng có quy tắc |
| Dùng `DATE(occurred_at)` để lọc ngày Việt Nam trên session UTC | Ngày có thể bị lệch quanh nửa đêm | Chuyển sang vùng Việt Nam hoặc tính ranh giới |
| Dùng `BETWEEN start AND '23:59:59'` | Bỏ sót phần lẻ giây cuối ngày | Dùng `>= start AND < next_start` |
| Tính cuối ngày địa phương bằng cách cộng 24 giờ UTC | Ngày có DST có thể dài 23/25 giờ | Tính từng nửa đêm địa phương rồi chuyển |
| Chuyển `TO_CHAR` trước khi `ORDER BY` | Sắp xếp theo chuỗi, có thể sai thứ tự lịch | Sắp theo timestamp/date thật |
| Nhóm theo `TO_CHAR(..., 'DD/MM/YYYY')` | Khóa nhóm là text, phụ thuộc format | Dùng `DATE`/`DATE_TRUNC` cho nhóm |
| Gắn vùng giờ cho timestamp đã có instant, hoặc chuyển hai lần | Có thể làm lệch instant | Phân biệt rõ kiểu đầu vào và hướng chuyển |
| Dùng tên vùng ở PostgreSQL y hệt trong SQL Server | Tên IANA và Windows không đồng nhất | Ánh xạ/kiểm tra tên vùng theo DBMS |
| Dùng timestamp đã làm tròn đến phút trong API cursor | Có thể mất chính xác ranh giới | Dùng biểu diễn round-trip được |
| Lấy timestamp local của giờ DST lặp mà không xử lý mơ hồ | Một đồng hồ local có thể ứng với hai instant | Lưu offset/instant hoặc quy tắc disambiguation |
| Tự mặc định ngày `03/04/2026` là 3/4 ở mọi nơi | Định dạng ngày vùng miền có thể khác | Trao đổi dữ liệu theo ISO/hợp đồng rõ ràng |
| Nghĩ `CURRENT_DATE` là cùng một ngày trên mọi kết nối | Phụ thuộc múi giờ của session và thời điểm truy vấn | Chỉ rõ vùng giờ hoặc truyền ngày vào |
| Nghĩ `DATE_TRUNC` trả text | Giá trị cắt mốc là kiểu thời gian, khác hàm format | Tách bucket và chuỗi hiển thị |

## 13. Bài tập thực hành

Sử dụng bảng `app_events` ở mục 3, không thay đổi dữ liệu. Nếu hệ SQL đang dùng không phải PostgreSQL, hãy thay cú pháp cho đúng dialect và kiểu cột đã chọn.

### Bài 1 — Đổi instant sang giờ Việt Nam

Sự kiện ID 3 có `occurred_at = 2026-11-14 01:10:00+00`. Đồng hồ Việt Nam là mấy giờ? Viết câu SQL.

**Đáp án:** `08:10:00` ngày `14/11/2026`.

~~~sql
SELECT
    occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        AS vietnam_clock
FROM app_events
WHERE event_id = 3;
~~~

### Bài 2 — Chuyển giờ địa phương trở lại UTC

Một ứng dụng nhận cuộc hẹn `2026-11-14 09:00:00` theo đồng hồ `Asia/Ho_Chi_Minh`. Hãy xác định instant theo UTC.

~~~sql
SELECT (
    TIMESTAMP '2026-11-14 09:00:00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh'
) AT TIME ZONE 'UTC' AS utc_clock;
~~~

**Đáp án:** `2026-11-14 02:00:00` theo đồng hồ UTC.

### Bài 3 — Nhóm theo ngày địa phương

Đếm số sự kiện theo ngày Việt Nam, sắp ngày tăng dần.

~~~sql
SELECT
    (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
        AS vn_date,
    COUNT(*) AS event_count
FROM app_events
GROUP BY vn_date
ORDER BY vn_date;
~~~

**Đáp án:** ngày 13/11 có 1 sự kiện, ngày 14/11 có 4 sự kiện, ngày 15/11 có 2 sự kiện.

### Bài 4 — Tìm đúng các sự kiện trong ngày 14/11 Việt Nam

Viết điều kiện nửa mở chỉ lọc ngày `2026-11-14` theo Việt Nam mà không ép kiểu trực tiếp cột `occurred_at`.

~~~sql
SELECT event_id, event_name
FROM app_events
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

**Đáp án:** ID `2, 3, 7, 4`. ID 1 vẫn thuộc ngày 13 ở Việt Nam, ID 5 đã bước sang ngày 15.

### Bài 5 — Cắt theo giờ

Có bao nhiêu sự kiện thuộc bucket `2026-11-14 08:00:00` theo giờ Việt Nam?

~~~sql
SELECT COUNT(*) AS event_count
FROM app_events
WHERE DATE_TRUNC(
    'hour',
    occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
) = TIMESTAMP '2026-11-14 08:00:00';
~~~

**Đáp án:** `2` (ID 3 và 7). Khi dữ liệu lớn và có chỉ mục trên `occurred_at`, cũng có thể tính khoảng ranh giới giờ địa phương rồi lọc trực tiếp theo instant.

### Bài 6 — Phân biệt DATE_TRUNC và TO_CHAR

Hai biểu thức khác nhau ở điều gì?

~~~sql
SELECT
    DATE_TRUNC(
        'day',
        occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AS vn_day_bucket,
    TO_CHAR(
        occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh',
        'DD/MM/YYYY'
    ) AS vn_day_label
FROM app_events
WHERE event_id = 3;
~~~

**Đáp án:** `vn_day_bucket` là `TIMESTAMP` không múi giờ tại `2026-11-14 00:00:00`; `vn_day_label` là **TEXT** `'14/11/2026'`. Bucket dùng cho các phép thời gian, label dùng để hiển thị.

### Bài 7 — Chọn cách lọc một ngày ở New York

Một người muốn xem toàn bộ sự kiện trong ngày địa phương bắt đầu vào `2026-03-08` tại `America/New_York`. Hai phương án:

A. Lấy instant lúc nửa đêm đầu ngày, cộng chính xác 24 giờ để có cuối ngày.

B. Tạo hai timestamp đồng hồ tại nửa đêm `2026-03-08` và `2026-03-09` ở `America/New_York`, chuyển cả hai thành instant và lọc `>= start AND < end`.

**Đáp án:** B. Ngày chuyển sang DST có thể dài **23 giờ**, nên A có thể lấy lẫn thời gian của ngày địa phương tiếp theo.

### Bài 8 — Vì sao định dạng sớm có thể gây sai thứ tự?

Chọn câu SQL tốt hơn để trả các sự kiện theo thời gian thực tăng dần, kèm nhãn ngày Việt Nam:

~~~sql
-- Cách A
SELECT event_id,
       TO_CHAR(
           occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh',
           'DD/MM/YYYY HH24:MI'
       ) AS display_time
FROM app_events
ORDER BY display_time;

-- Cách B
SELECT event_id,
       TO_CHAR(
           occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh',
           'DD/MM/YYYY HH24:MI'
       ) AS display_time
FROM app_events
ORDER BY occurred_at, event_id;
~~~

**Đáp án:** B. `display_time` là text theo định dạng `DD/MM/YYYY`; thứ tự chuỗi có thể khác thứ tự thời gian thật. `occurred_at` giữ kiểu instant và `event_id` giúp kết quả ổn định khi trùng thời điểm.

### Bài 9 — Phân biệt ý nghĩa hai chiều của AT TIME ZONE

Cho:

~~~sql
SELECT
    TIMESTAMP '2026-11-14 08:10:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh' AS a,
    TIMESTAMPTZ '2026-11-14 01:10:00+00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh' AS b;
~~~

**Đáp án:** `a` có kiểu `TIMESTAMPTZ`, là instant tương ứng đồng hồ Việt Nam `08:10`; `b` có kiểu `TIMESTAMP WITHOUT TIME ZONE`, mang giá trị đồng hồ `08:10` khi xem instant UTC ở Việt Nam. Dù hiển thị có thể trông giống nhau, **kiểu và ý nghĩa của hai kết quả khác nhau**.

## 14. Kết luận

Khi xử lý ngày giờ trong SQL, hãy thực hiện theo trình tự ý nghĩa:

1. **Xác định kiểu và nguồn sự thật thời gian:** ngày lịch, giờ địa phương hay instant.
2. **Chọn vùng giờ cần diễn giải:** sử dụng vùng IANA/Windows đúng với DBMS, không tự giả định offset cố định cho những nơi có DST.
3. **Lọc và nhóm bằng giá trị thời gian có kiểu:** dùng `DATE_TRUNC`/ép `DATE` theo mục đích, và khoảng `[start, end)` để lọc trọn một ngày địa phương.
4. **Định dạng ở điểm cuối:** dùng `TO_CHAR` cho báo cáo SQL dành cho người đọc, hoặc formatter của ứng dụng/UI khi hỗ trợ nhiều locale.
5. **Giữ khả năng chuyển hệ:** kiểm tra dialect, phiên bản, cấu hình timezone, độ chính xác timestamp và quy tắc chuyển DST.

**Chuyển múi giờ** quyết định cách nhìn một thời điểm; **cắt mốc thời gian** quyết định ranh giới phân nhóm/lọc; **định dạng ngày giờ** quyết định cách người dùng đọc giá trị. Tách ba quyết định này giúp thống kê đúng ngày địa phương, tránh sai dữ liệu quanh nửa đêm và giữ hệ thống dễ bảo trì.

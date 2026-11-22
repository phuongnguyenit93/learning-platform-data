# interval, phép tính thời gian và múi giờ trong PostgreSQL

Một hệ thống đặt lịch cần biết cuộc hẹn bắt đầu lúc nào và kéo dài bao lâu. Một hệ thống thanh toán cần cộng thêm một tháng vào ngày đến hạn. Một báo cáo bán hàng cần tổng hợp đơn hàng theo **ngày địa phương của cửa hàng** dù database lưu giao dịch từ nhiều quốc gia. Ba bài toán đều liên quan đến thời gian, nhưng **“một ngày”, “24 giờ”, “một tháng” và “một mốc thời gian tuyệt đối” không phải lúc nào cũng có cùng ý nghĩa**.

PostgreSQL có hệ thống kiểu dữ liệu và phép toán thời gian khá phong phú: `DATE`, `TIME`, `TIMESTAMP`, `TIMESTAMPTZ` và đặc biệt là **`INTERVAL`**. Hiểu đúng chúng giúp tránh các lỗi khó phát hiện như lịch hẹn lệch một giờ khi chuyển sang giờ mùa hè (DST), tính sai kỳ hạn thanh toán vào ngày cuối tháng, hoặc báo cáo một đơn hàng vào nhầm ngày.

Bài học này tập trung vào:

- Cách chọn kiểu dữ liệu cho **ngày**, **giờ địa phương**, **mốc thời gian** và **khoảng thời gian**.
- Cách khai báo, lưu trữ, cộng/trừ, so sánh và hiển thị `INTERVAL`.
- Sự khác nhau giữa thời lượng thực tế và phép tính theo lịch.
- Vai trò của `TimeZone`, `AT TIME ZONE` và cơ sở dữ liệu múi giờ IANA.
- Tác động của DST lên phép cộng ngày/giờ, định kỳ và lọc dữ liệu.
- Các mẫu truy vấn thực tế: thời gian xử lý, báo cáo theo ngày, khung giờ và lịch hẹn.

Các ví dụ dùng cú pháp PostgreSQL hiện đại. Người học có thể chạy những truy vấn `SELECT` trên một database thực hành; phần tạo bảng nằm riêng và được chú thích. Kết quả hiển thị của `TIMESTAMPTZ` **phụ thuộc cấu hình múi giờ của phiên**, vì vậy các ví dụ có kiểm soát `TimeZone` khi điều đó ảnh hưởng đáp án.

## 1. Bốn câu hỏi phải trả lời trước khi chọn kiểu

Thời gian trong ứng dụng thường thuộc bốn nhóm khác nhau:

| Câu hỏi nghiệp vụ | Ví dụ | Kiểu PostgreSQL thường phù hợp |
| --- | --- | --- |
| **Ngày nào** trên lịch? | Ngày sinh, ngày nghỉ, ngày hóa đơn | `DATE` |
| **Mấy giờ trên đồng hồ**, chưa gắn một ngày? | Cửa hàng mở lúc 09:00 mỗi ngày | `TIME WITHOUT TIME ZONE` |
| **Ngày giờ địa phương** nhưng chưa xác định múi giờ? | Lịch hiển thị “2026-11-14 09:00” tại văn phòng | `TIMESTAMP WITHOUT TIME ZONE`, kèm tên múi giờ riêng nếu cần chuyển thành mốc tuyệt đối |
| **Mốc thời gian thực tế** mà sự kiện đã xảy ra? | Giao dịch tạo lúc nào, token hết hạn khi nào | `TIMESTAMP WITH TIME ZONE` / `TIMESTAMPTZ` |
| **Khoảng cách hoặc quy tắc cộng thời gian**? | Sau 90 phút, sau 7 ngày, thêm 1 tháng | `INTERVAL` |

**Không tồn tại một kiểu duy nhất phù hợp với mọi bài toán.** Một ngày sinh không cần chính xác tới múi giờ; ngược lại, sự kiện đã diễn ra trên hệ thống phân tán cần một mốc thời gian có thể so sánh giữa các quốc gia.

### 1.1. Những kiểu dữ liệu cơ bản

~~~sql
SELECT
    DATE '2026-11-14'                           AS a_date,
    TIME '09:30:00'                             AS a_time,
    TIMESTAMP '2026-11-14 09:30:00'             AS local_datetime,
    TIMESTAMPTZ '2026-11-14 09:30:00+07'        AS an_instant,
    INTERVAL '1 day 2 hours 30 minutes'         AS a_duration;
~~~

Đây là những **type-qualified literals**, trong đó tên kiểu đứng trước chuỗi giá trị. Viết rõ kiểu giúp tránh nhầm lẫn do phép ép kiểu ngầm định.

### 1.2. TIMESTAMP không đồng nghĩa TIMESTAMPTZ

Trong PostgreSQL:

- `TIMESTAMP` là cách viết ngắn của **`TIMESTAMP WITHOUT TIME ZONE`**. Nó biểu diễn ngày và giờ dạng “đồng hồ”, **không tự xác định một thời điểm tuyệt đối**.
- `TIMESTAMPTZ` là cách viết ngắn của **`TIMESTAMP WITH TIME ZONE`**. Nó biểu diễn **một thời điểm tuyệt đối**; PostgreSQL chuẩn hóa thông tin mốc thời gian trong lưu trữ và chuyển đổi cách hiển thị theo múi giờ phiên.
- `TIMESTAMPTZ` **không lưu nguyên tên múi giờ IANA hoặc offset mà người dùng nhập** cùng từng giá trị. Nếu ứng dụng cần biết cuộc hẹn thuộc `America/New_York` hay `Asia/Ho_Chi_Minh`, phải lưu tên múi giờ trong một cột/đối tượng riêng.

Ví dụ hai chuỗi cùng biểu diễn một mốc thực tế:

~~~sql
SELECT
    TIMESTAMPTZ '2026-11-14 10:00:00+07'
    =
    TIMESTAMPTZ '2026-11-14 03:00:00+00'
    AS same_instant;
-- true
~~~

Vì 10:00 ở UTC+07 là 03:00 UTC, hai giá trị `TIMESTAMPTZ` bằng nhau về mốc thời gian, dù cách biểu diễn khác.

Một bẫy đáng chú ý:

~~~sql
SELECT
    TIMESTAMP '2026-11-14 10:00:00+07'
        AS local_timestamp;
~~~

Do đã chỉ định kiểu **`TIMESTAMP WITHOUT TIME ZONE`**, phần chỉ múi giờ trong literal không biến nó thành `TIMESTAMPTZ`. Đừng trông chờ `+07` được lưu như metadata của giá trị này. Nếu cần mốc tuyệt đối, hãy dùng `TIMESTAMPTZ` hoặc chuyển đổi tường minh với `AT TIME ZONE`.

### 1.3. TIME WITH TIME ZONE có nên dùng không?

PostgreSQL cũng hỗ trợ `TIME WITH TIME ZONE` (viết tắt `TIMETZ`), nhưng loại này thường **không phải lựa chọn tốt cho lịch hẹn dài hạn**. Quy tắc lệch UTC của nhiều khu vực thay đổi theo ngày do DST hoặc thay đổi chính sách, trong khi `TIME` độc lập với ngày không đủ thông tin để xác định một offset đúng cho mọi ngày.

Đối với lịch “mỗi thứ Hai 09:00 tại New York”, thường nên lưu **giờ địa phương + thứ/ngày + tên múi giờ IANA**, rồi xác định mốc `TIMESTAMPTZ` cho từng lần diễn ra. Không cố giải quyết lịch tái diễn bằng một giá trị `TIMETZ` duy nhất.

## 2. INTERVAL là gì?

`INTERVAL` biểu diễn một **khoảng thời gian** dùng trong các phép tính ngày giờ. Ta có thể khai báo khoảng chứa năm, tháng, tuần, ngày, giờ, phút, giây:

~~~sql
SELECT
    INTERVAL '2 years 3 months'       AS calendar_span,
    INTERVAL '1 week 2 days'         AS several_days,
    INTERVAL '4 hours 30 minutes'    AS elapsed_time,
    INTERVAL '1 day 01:02:03.5'      AS mixed_interval,
    INTERVAL '-45 minutes'           AS negative_interval;
~~~

Trong nhiều tình huống, `INTERVAL` giống “duration”, nhưng quan trọng là nó có thể mang **thành phần lịch** như tháng, không đơn giản là một số giây.

### 2.1. Cấu trúc lưu trữ: tháng, ngày và microsecond

PostgreSQL lưu giá trị interval về cơ bản trong ba nhóm thành phần:

1. **Months:** năm/tháng sau khi quy về đơn vị tháng.
2. **Days:** ngày, gồm các đơn vị được chuyển đổi phù hợp như tuần.
3. **Microseconds:** phần thời gian nhỏ hơn ngày, biểu diễn giờ/phút/giây và phần lẻ.

~~~text
INTERVAL '1 month 2 days 03:04:05'
              |
              +-- months = 1
              +-- days = 2
              +-- time = 03:04:05
~~~

Đây là mô hình quan trọng bởi **tháng không có số ngày cố định**, còn một ngày theo lịch địa phương có thể không tương đương 24 giờ tại nơi có DST.

Ví dụ:

~~~sql
SELECT
    INTERVAL '1 month' AS one_month,
    INTERVAL '30 days' AS thirty_days,
    INTERVAL '720 hours' AS seven_hundred_twenty_hours;
~~~

Ba interval có thể được quy đổi tương đương khi PostgreSQL **so sánh hoặc tính toán trong một số ngữ cảnh**, nhưng **không thể tùy ý thay thế trong phép cộng với mọi ngày giờ**. Cộng 1 tháng vào 31/01 khác hoàn toàn ý định cộng 30 ngày trong nhiều năm.

### 2.2. Các cách tạo INTERVAL

**Literal trực tiếp:**

~~~sql
SELECT
    INTERVAL '90 minutes' AS a,
    INTERVAL '1 hour 30 minutes' AS b,
    INTERVAL '2 days -3 hours' AS c;
~~~

**Ép kiểu từ chuỗi:**

~~~sql
SELECT '15 minutes'::interval AS reminder_offset;
~~~

Chỉ ép kiểu văn bản từ đầu vào không đáng tin cậy nếu chưa xác thực ý nghĩa và giới hạn nghiệp vụ. PostgreSQL sẽ parse interval theo cú pháp được hỗ trợ, nhưng ứng dụng vẫn phải quyết định giá trị âm, cực lớn, tháng hay giờ có hợp lệ không.

**Hàm `make_interval` với tham số có tên:**

~~~sql
SELECT
    make_interval(days => 2, hours => 3, mins => 15)
        AS shipping_window,
    make_interval(months => 1) AS billing_cycle,
    make_interval(secs => 1.5) AS fractional_seconds;
~~~

`make_interval` hữu ích khi ứng dụng nhận từng thành phần số riêng. Không cần ghép chuỗi như `'2 days 3 hours'` nếu đã có tham số nguyên/real rõ ràng.

**Cú pháp ISO 8601:**

~~~sql
SELECT INTERVAL 'P1DT2H30M' AS iso_duration;
~~~

Ở đây `P` bắt đầu khoảng thời gian; `D` là ngày; `T` chuyển sang phần giờ/phút/giây; `H` là giờ, `M` trong phần sau `T` là phút. Khi trao đổi chuỗi interval với hệ thống khác, phải thống nhất phiên bản/cú pháp và ngữ nghĩa của thành phần tháng/ngày.

### 2.3. INTERVAL có thể âm

~~~sql
SELECT
    INTERVAL '-3 days' AS minus_three_days,
    TIMESTAMP '2026-11-14 10:00'
        + INTERVAL '-2 hours' AS two_hours_before,
    -INTERVAL '15 minutes' AS negative_fifteen_minutes;
~~~

Interval âm có ích cho thao tác lùi mốc, nhưng một nghiệp vụ “thời lượng xử lý” thường không nên âm. Nếu lưu thời lượng trong bảng, nên có ràng buộc phù hợp, ví dụ:

~~~sql
-- Minh họa ý tưởng ràng buộc trên một cột INTERVAL.
-- duration INTERVAL NOT NULL CHECK (duration > INTERVAL '0 seconds')
~~~

Khi kiểm tra interval có nhiều thành phần tháng/ngày/giờ, cần hiểu quy tắc so sánh của PostgreSQL; với lịch nghiệp vụ phức tạp, đôi khi cần kiểm tra thêm các thành phần hoặc kết quả sau khi áp vào mốc cụ thể.

## 3. Phép cộng và phép trừ ngày giờ

Các phép toán thông dụng:

| Biểu thức | Kiểu kết quả thường gặp | Ví dụ |
| --- | --- | --- |
| `date + integer` | `date` | Thêm một số ngày lịch |
| `date - date` | `integer` | Số ngày giữa hai ngày |
| `date + interval` | `timestamp without time zone` | Ngày cộng một khoảng có thể gồm giờ |
| `timestamp + interval` | `timestamp` | Cộng lịch/giờ vào ngày giờ địa phương |
| `timestamptz + interval` | `timestamptz` | Cộng khoảng vào mốc thời gian, có tác động của múi giờ |
| `timestamp - timestamp` | `interval` | Khoảng giữa hai ngày giờ không có timezone |
| `timestamptz - timestamptz` | `interval` | Khoảng thực tế giữa hai mốc tuyệt đối |
| `interval * numeric` | `interval` | Nhân khoảng thời gian với hệ số |

### 3.1. Ngày cộng ngày

~~~sql
SELECT
    DATE '2026-11-14' + 7 AS next_week,
    DATE '2026-11-14' - 7 AS previous_week,
    DATE '2026-11-14' - DATE '2026-11-01'
        AS elapsed_calendar_days;
~~~

Kết quả `elapsed_calendar_days` là **13**, một số nguyên. Đây là hiệu giữa hai giá trị ngày thuần túy, chưa áp dụng quy tắc múi giờ/DST.

### 3.2. Cộng giờ/phút vào timestamp

~~~sql
SELECT
    TIMESTAMP '2026-11-14 09:00'
        + INTERVAL '1 hour 30 minutes'
        AS appointment_end,
    TIMESTAMP '2026-11-14 09:00'
        - INTERVAL '45 minutes'
        AS reminder_at;
~~~

Với timestamp không có múi giờ, phép toán xử lý ngày giờ theo lịch như một giá trị địa phương. Nếu đó là cuộc hẹn có thể diễn ra tại khu vực đổi DST, cần biết múi giờ thực tế để chuyển thành mốc đáng tin cậy.

### 3.3. Lấy hiệu giữa hai timestamp

~~~sql
SELECT
    TIMESTAMP '2026-11-14 11:45'
    -
    TIMESTAMP '2026-11-14 09:15'
    AS processing_duration;
-- 02:30:00
~~~

Đây là phép tính trên hai ngày giờ “naive” cùng quy ước. Để đo thời gian thực tế trôi qua giữa hai sự kiện ở các múi giờ hoặc trong một vùng có DST, nên dùng **hai giá trị `TIMESTAMPTZ`**:

~~~sql
SELECT
    TIMESTAMPTZ '2026-11-14 11:45+07'
    -
    TIMESTAMPTZ '2026-11-14 09:15+07'
    AS actual_elapsed;
-- 02:30:00
~~~

### 3.4. Nhân và chia INTERVAL

~~~sql
SELECT
    INTERVAL '15 minutes' * 4 AS total_break,
    INTERVAL '3 hours' / 2 AS half_shift,
    INTERVAL '2 days' + INTERVAL '5 hours'
        AS combined_interval;
~~~

Hãy phân biệt **nhân thời lượng cố định** với **nhân một chu kỳ theo lịch**. Ví dụ `INTERVAL '1 month' * 12` biểu diễn 12 tháng, nhưng không có nghĩa mọi chu kỳ “1 tháng” luôn là số giây giống nhau.

## 4. Tháng và năm là khoảng lịch, không phải số giây cố định

Một tháng có 28, 29, 30 hoặc 31 ngày. Cộng một tháng vào ngày cuối tháng cần tuân theo quy tắc ngày lịch chứ không đơn giản cộng 30 × 24 giờ.

~~~sql
SELECT
    DATE '2024-01-31'
        + INTERVAL '1 month' AS leap_year_case,
    DATE '2025-01-31'
        + INTERVAL '1 month' AS ordinary_year_case,
    DATE '2024-01-31'
        + INTERVAL '30 days' AS thirty_day_case;
~~~

Các kết quả điển hình:

| Biểu thức | Kết quả |
| --- | --- |
| `2024-01-31 + 1 month` | `2024-02-29 00:00:00` |
| `2025-01-31 + 1 month` | `2025-02-28 00:00:00` |
| `2024-01-31 + 30 days` | `2024-03-01 00:00:00` |

PostgreSQL điều chỉnh ngày trong tháng khi cộng tháng vào một ngày như 31/01 mà tháng mới không có ngày 31. Nhưng **không nên coi phép lặp cộng tháng là một định nghĩa chuẩn duy nhất cho mọi quy tắc thanh toán**.

### 4.1. Cộng nhiều tháng không luôn giống cộng lặp từng tháng

Ví dụ một chương trình tính chu kỳ bằng cách:

~~~sql
SELECT
    DATE '2024-01-31' + INTERVAL '2 months'
        AS direct_two_months,
    (DATE '2024-01-31' + INTERVAL '1 month')
        + INTERVAL '1 month'
        AS two_successive_steps;
~~~

Đối với ngày gần cuối tháng, hai cách **có thể cho ngày khác nhau** vì bước cộng tháng đầu đã điều chỉnh ngày. Đây là vấn đề rất quan trọng nếu “ngày đến hạn” phải luôn là **ngày cuối tháng** hoặc là “ngày số 31 nếu tồn tại”.

Một hệ thống hóa đơn nên định nghĩa nghiệp vụ rõ ràng:

- “Sau đúng 30 ngày” → khoảng ngày/ngày giờ tương ứng.
- “Sau một tháng theo lịch từ mốc gốc” → dùng phép cộng tháng theo quy tắc xác định.
- “Ngày cuối cùng của tháng sau” → tính ngày đầu tháng kế tiếp rồi xác định ngày cuối tháng theo công thức riêng.
- “Mỗi ngày 15 hàng tháng” → lưu ngày neo là 15, không suy ra bằng cách liên tục cộng tháng từ một kết quả đã bị điều chỉnh.

### 4.2. Tính ngày cuối tháng

~~~sql
SELECT
    (
        date_trunc(
            'month',
            DATE '2026-11-14'::timestamp
        )
        + INTERVAL '1 month'
        - INTERVAL '1 day'
    )::date AS last_day_of_month;
-- 2026-11-30
~~~

Công thức đưa ngày về đầu tháng, tiến một tháng rồi lùi một ngày. Khi áp dụng cho hóa đơn, cần quyết định có dùng múi giờ của người dùng/cửa hàng hay chỉ làm việc với `DATE` như một ngày lịch thuần túy.

## 5. Hàm age(): chênh lệch biểu diễn theo lịch

PostgreSQL có hàm `age` để trả về khoảng chênh lệch có ý nghĩa **năm, tháng, ngày** thay vì đơn thuần là số giây:

~~~sql
SELECT
    age(
        TIMESTAMP '2026-11-14 00:00',
        TIMESTAMP '2000-07-10 00:00'
    ) AS calendar_age;
~~~

Giá trị biểu diễn sẽ có thành phần năm, tháng, ngày. `age(a, b)` là hiệu theo **đơn vị lịch**; còn `a - b` đối với hai timestamp trả interval mô tả chênh lệch của hai giá trị ngày giờ. Hai cách có thể biểu diễn khác nhau dù bắt đầu từ cùng hai mốc.

### 5.1. Tính số tuổi theo năm đã hoàn thành

~~~sql
SELECT
    EXTRACT(
        YEAR FROM age(
            DATE '2026-11-14',
            DATE '2000-07-10'
        )
    ) AS completed_years;
-- 26
~~~

Trong bảng khách hàng, tuổi thường được **tính từ `DATE` ngày sinh** khi cần, không nhất thiết lưu một cột `age` cố định sẽ nhanh chóng lỗi thời. Quy tắc cho người sinh ngày 29/02 trong năm không nhuận có thể khác nhau theo pháp luật hoặc nghiệp vụ, nên phải được định nghĩa rõ ở ứng dụng.

### 5.2. age() không phải đồng hồ đo thời gian thực tế

Nếu cần đo:

- Tổng số giây xử lý một API.
- Độ trễ giữa lúc gửi và nhận sự kiện.
- Thời gian kết nối mất bao lâu.

hãy dùng hiệu của các **mốc tuyệt đối** và quy đổi ra số giây. `age` phù hợp hơn khi diễn đạt **tuổi, thâm niên, chênh lệch tháng/năm theo lịch**.

## 6. EXTRACT, date_part và quy đổi sang giây

Để lấy thành phần của một timestamp hoặc interval:

~~~sql
SELECT
    EXTRACT(YEAR FROM TIMESTAMP '2026-11-14 09:30') AS yy,
    EXTRACT(MONTH FROM TIMESTAMP '2026-11-14 09:30') AS mm,
    EXTRACT(DAY FROM TIMESTAMP '2026-11-14 09:30') AS dd,
    EXTRACT(HOUR FROM INTERVAL '2 days 03:45:20') AS hh,
    EXTRACT(MINUTE FROM INTERVAL '2 days 03:45:20') AS mi;
~~~

`date_part('hour', value)` có chức năng trích xuất thành phần tương tự trong nhiều trường hợp; `EXTRACT` gần chuẩn SQL hơn. Khi cần hiện số “tổng phút”, **không nên chỉ lấy thành phần `MINUTE`**, vì `2 hours 15 minutes` có thành phần phút là 15 nhưng tổng phút là 135.

### 6.1. Đo thời gian thực tế bằng EPOCH

Đối với hai `TIMESTAMPTZ`:

~~~sql
SELECT
    EXTRACT(
        EPOCH FROM (
            TIMESTAMPTZ '2026-11-14 10:02:30+07'
            -
            TIMESTAMPTZ '2026-11-14 10:00:00+07'
        )
    ) AS elapsed_seconds;
-- 150
~~~

`EXTRACT(EPOCH FROM interval)` phù hợp với khoảng được tạo bởi hiệu **hai mốc tuyệt đối**, vì nó phản ánh khoảng thời gian thực tế trôi qua. Với interval có **months** hoặc những thành phần lịch phức tạp, PostgreSQL dùng các quy ước để tính hoặc so sánh mà không thể biến một tháng cụ thể thành số giây đúng cho mọi ngày neo. Không dùng `EPOCH` của `INTERVAL '1 month'` làm quy tắc “số giây của một tháng” trong lịch thanh toán.

### 6.2. Epoch của timestamptz khác timestamp không timezone

~~~sql
SELECT
    EXTRACT(
        EPOCH FROM TIMESTAMPTZ '1970-01-01 00:00:00+00'
    ) AS unix_epoch_zero;
-- 0
~~~

Đối với `TIMESTAMPTZ`, epoch gắn với mốc UTC. Đối với `TIMESTAMP WITHOUT TIME ZONE`, PostgreSQL tính epoch theo ngày giờ danh nghĩa **không áp dụng quy tắc offset/DST**. Do đó, không nên ép một local timestamp không rõ múi giờ thành “Unix time” rồi dùng như một mốc UTC đã xác thực.

### 6.3. Ngày trong tuần và ISO week

~~~sql
SELECT
    EXTRACT(DOW FROM DATE '2026-11-14') AS day_of_week,
    EXTRACT(ISODOW FROM DATE '2026-11-14') AS iso_day_of_week,
    EXTRACT(WEEK FROM DATE '2026-11-14') AS iso_week,
    EXTRACT(ISOYEAR FROM DATE '2026-11-14') AS iso_year;
~~~

`DOW` dùng Chủ nhật = 0, còn `ISODOW` dùng thứ Hai = 1 đến Chủ nhật = 7. Tuần ISO có thể thuộc **ISO year khác năm lịch** ở sát đầu/cuối năm. Khi tổng hợp doanh số theo tuần, nên lưu cả `ISOYEAR` và `WEEK`, không chỉ số tuần.

## 7. Làm đẹp và chuẩn hóa INTERVAL

Một interval có thể chứa các thành phần không được tự chuyển đổi ngay thành đơn vị lớn hơn. PostgreSQL có những hàm tiện dụng:

~~~sql
SELECT
    justify_hours(INTERVAL '48 hours') AS hours_to_days,
    justify_days(INTERVAL '30 days') AS days_to_months,
    justify_interval(INTERVAL '30 days 48 hours')
        AS normalized_display;
~~~

- `justify_hours` dùng quy ước 24 giờ → 1 ngày.
- `justify_days` dùng quy ước 30 ngày → 1 tháng.
- `justify_interval` kết hợp các điều chỉnh tương ứng và một số quy tắc dấu.

**Các hàm này chuyển đổi theo quy ước để chuẩn hóa cách biểu diễn, không chứng minh một tháng theo lịch luôn là 30 ngày hoặc một ngày địa phương luôn 24 giờ.**

### 7.1. Định dạng intervalstyle

PostgreSQL hỗ trợ nhiều cách hiển thị interval, ví dụ `postgres`, `postgres_verbose`, `sql_standard` và `iso_8601`:

~~~sql
SHOW intervalstyle;

SET intervalstyle = 'iso_8601';

SELECT INTERVAL '2 days 3 hours 4 minutes' AS example_interval;

RESET intervalstyle;
~~~

`SET` trong ví dụ chỉ thay đổi thiết lập của **session hiện tại**, không cập nhật cấu hình toàn server. Khi một ứng dụng trao đổi dữ liệu qua JSON hoặc nhiều ngôn ngữ lập trình, nên ưu tiên **kiểu dữ liệu có hợp đồng rõ ràng** và parse theo định dạng thỏa thuận, không dựa vào giao diện hiển thị mặc định của từng client.

### 7.2. INTERVAL có độ chính xác phần giây

~~~sql
SELECT
    INTERVAL '1.234567 seconds' AS microsecond_example,
    INTERVAL(2) '1.234567 seconds' AS rounded_to_2_digits;
~~~

PostgreSQL lưu độ chính xác thời gian của interval ở mức microsecond trong mô hình thông thường; cách hiển thị có thể làm tròn phần giây khi khai báo precision. Đừng suy ra một interval lưu chính xác tùy ý hàng trăm chữ số thập phân chỉ vì nó được nhập từ chuỗi.

## 8. Múi giờ trong PostgreSQL: TimeZone, offset và tên vùng

Một **offset** như `+07:00` mô tả chênh lệch so với UTC **tại một mốc cụ thể**. Còn tên vùng như `Asia/Ho_Chi_Minh` hoặc `America/New_York` gắn với **bộ quy tắc múi giờ theo ngày và lịch sử** do cơ sở dữ liệu IANA time zone cung cấp.

Ví dụ:

~~~text
2026-11-14 10:00 +07:00
        |
        v
2026-11-14 03:00 UTC
~~~

Một tên vùng có thể có các offset khác nhau vào mùa đông/mùa hè. Vì vậy, **không dùng offset hiện tại để dự đoán mọi ngày trong năm** ở khu vực có DST.

### 8.1. Kiểm tra múi giờ phiên

~~~sql
SHOW TimeZone;

SELECT
    current_setting('TimeZone') AS session_zone,
    CURRENT_TIMESTAMP AS timestamp_in_session_zone;
~~~

`TimeZone` ảnh hưởng cách `TIMESTAMPTZ` được **hiển thị**, cách chuyển đổi giữa ngày giờ địa phương và mốc tuyệt đối khi thiếu offset tường minh, và một số phép toán theo lịch.

### 8.2. Đổi múi giờ trong session

~~~sql
SET TIME ZONE 'Asia/Ho_Chi_Minh';

SELECT TIMESTAMPTZ '2026-11-14 03:00:00+00'
    AS displayed_in_vietnam;

SET TIME ZONE 'UTC';

SELECT TIMESTAMPTZ '2026-11-14 03:00:00+00'
    AS displayed_in_utc;

RESET TIME ZONE;
~~~

Hai lần `SELECT` phản ánh **cùng một instant**, nhưng cách hiển thị khác. `RESET TIME ZONE` đưa phiên về thiết lập theo các lớp cấu hình đang có hiệu lực; nó không nhất thiết bằng UTC.

Đừng dùng thay đổi `TimeZone` ở session để “chỉnh lại dữ liệu” đang lưu trong cột `TIMESTAMPTZ`. Một phép hiển thị khác không có nghĩa những transaction lịch sử đã bị dịch chuyển thời điểm.

### 8.3. Danh sách tên vùng có sẵn

~~~sql
SELECT
    name,
    abbrev,
    utc_offset,
    is_dst
FROM pg_timezone_names
WHERE name IN ('Asia/Ho_Chi_Minh', 'America/New_York', 'UTC')
ORDER BY name;
~~~

`pg_timezone_names` hiển thị các tên vùng mà server nhận biết, cùng offset/DST **tại thời điểm đánh giá hiện tại**. Offset hiển thị trong view không phải quy tắc vĩnh viễn cho mọi ngày. Nếu cần kiểm tra offset của **mốc lịch sử/tương lai**, hãy chuyển đổi mốc cụ thể bằng tên vùng thay vì đọc một offset từ view rồi áp vào toàn bộ năm.

### 8.4. Vì sao nên dùng tên IANA thay cho viết tắt?

Một số viết tắt như `PST`, `EST` hoặc `CST` có thể gây mơ hồ hoặc phản ánh offset cố định theo quy tắc giải mã cụ thể. `America/New_York` mô tả vùng có lịch sử chuyển đổi DST; `Asia/Ho_Chi_Minh` mô tả quy tắc của vùng đó.

Đối với ứng dụng đa quốc gia, nên lưu tên vùng từ danh sách được cho phép. Khi tính lịch trong tương lai, thư viện múi giờ có thể được cập nhật do luật địa phương thay đổi; lịch định kỳ quan trọng cần chính sách cập nhật/diễn giải phù hợp.

## 9. AT TIME ZONE: hai hướng chuyển đổi đối xứng nhưng khác kiểu

Toán tử `AT TIME ZONE` là thành phần cốt lõi của PostgreSQL khi xử lý múi giờ. **Kết quả phụ thuộc vào kiểu của biểu thức đầu vào**, không chỉ câu lệnh trông giống nhau.

| Đầu vào | Biểu thức | Kết quả |
| --- | --- | --- |
| `TIMESTAMP WITHOUT TIME ZONE` | `local_time AT TIME ZONE 'Region/City'` | `TIMESTAMPTZ` — diễn giải đồng hồ địa phương trong múi giờ đó để xác định instant |
| `TIMESTAMPTZ` | `instant AT TIME ZONE 'Region/City'` | `TIMESTAMP WITHOUT TIME ZONE` — hiển thị instant theo đồng hồ địa phương của vùng |

### 9.1. Từ giờ địa phương sang mốc tuyệt đối

Giả sử khách đặt lịch lúc **09:00 ngày 14/11/2026 ở Việt Nam**:

~~~sql
SELECT
    TIMESTAMP '2026-11-14 09:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
        AS appointment_instant;
~~~

Kết quả có kiểu `TIMESTAMPTZ`, đại diện cho **02:00 UTC**. Nó có thể được hiển thị là `2026-11-14 09:00:00+07` nếu phiên đang đặt múi giờ Việt Nam, hoặc `2026-11-14 02:00:00+00` nếu phiên ở UTC.

### 9.2. Từ mốc tuyệt đối sang giờ địa phương

~~~sql
SELECT
    TIMESTAMPTZ '2026-11-14 02:00:00+00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
        AS vietnam_wall_clock;
-- 2026-11-14 09:00:00 (TIMESTAMP WITHOUT TIME ZONE)
~~~

Đây là phép chuyển đổi để hiển thị/nhóm dữ liệu theo **đồng hồ của một địa phương**, không thay đổi instant gốc.

### 9.3. Kết hợp hai chiều để hiểu ngữ nghĩa

~~~sql
SELECT
    pg_typeof(
        TIMESTAMP '2026-11-14 09:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AS local_to_instant_type,
    pg_typeof(
        TIMESTAMPTZ '2026-11-14 02:00+00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AS instant_to_local_type;
~~~

Bạn sẽ thấy hai kiểu kết quả là **timestamp with time zone** và **timestamp without time zone**. Đây là lý do nên kiểm tra type khi viết query có nhiều phép `AT TIME ZONE`, đặc biệt khi truyền kết quả sang JDBC.

### 9.4. timezone() là dạng hàm tương ứng

~~~sql
SELECT
    timezone(
        'Asia/Ho_Chi_Minh',
        TIMESTAMPTZ '2026-11-14 02:00:00+00'
    ) AS vietnam_local_datetime;
~~~

Hàm `timezone(zone, value)` có thể biểu diễn cùng phép chuyển đổi trong nhiều ngữ cảnh. Tuy nhiên, kiểu kết quả vẫn phụ thuộc kiểu đầu vào; không dùng tên hàm để đoán nó luôn trả `TIMESTAMPTZ`.

## 10. DST: vì sao 1 day có thể khác 24 hours?

**Daylight Saving Time (DST)** là việc một số khu vực điều chỉnh đồng hồ theo mùa. Khi chuyển sang giờ mùa hè, đồng hồ có thể nhảy qua một giờ; khi quay lại giờ chuẩn, một khoảng giờ địa phương có thể xuất hiện hai lần.

Đây là nơi `INTERVAL '1 day'` và `INTERVAL '24 hours'` bộc lộ ngữ nghĩa khác nhau khi cộng vào `TIMESTAMPTZ` trong một vùng có DST.

### 10.1. Ví dụ qua ngày bắt đầu DST ở New York

Tại khu vực `America/New_York`, ngày **08/03/2026** là ngày chuyển sang giờ mùa hè. Chạy:

~~~sql
SET TIME ZONE 'America/New_York';

WITH example AS (
    SELECT TIMESTAMPTZ '2026-03-07 12:00:00-05' AS start_at
)
SELECT
    start_at,
    start_at + INTERVAL '1 day' AS next_calendar_day,
    start_at + INTERVAL '24 hours' AS after_24_hours
FROM example;

RESET TIME ZONE;
~~~

Kết quả quan trọng:

| Giá trị | Giờ địa phương New York |
| --- | --- |
| Bắt đầu | `2026-03-07 12:00:00-05` |
| Cộng `1 day` | `2026-03-08 12:00:00-04` |
| Cộng `24 hours` | `2026-03-08 13:00:00-04` |

**Cộng một ngày theo lịch giữ mốc 12:00 của ngày tiếp theo**, trong khi cộng 24 giờ đảm bảo đúng 24 giờ thời gian thực trôi qua. Do múi giờ đổi từ `-05` sang `-04`, khoảng thực giữa hai lần 12:00 chỉ là 23 giờ.

### 10.2. Đo lại bằng phép trừ hai instant

~~~sql
SET TIME ZONE 'America/New_York';

WITH t AS (
    SELECT TIMESTAMPTZ '2026-03-07 12:00:00-05' AS start_at
)
SELECT
    EXTRACT(
        EPOCH FROM (
            (start_at + INTERVAL '1 day') - start_at
        )
    ) / 3600 AS hours_for_calendar_day,
    EXTRACT(
        EPOCH FROM (
            (start_at + INTERVAL '24 hours') - start_at
        )
    ) / 3600 AS hours_for_fixed_duration
FROM t;

RESET TIME ZONE;
~~~

Kết quả tương ứng là **23 giờ** và **24 giờ**.

Ở một ngày mùa thu khi đồng hồ lùi một giờ, khoảng từ một giờ địa phương đến **cùng giờ địa phương ngày hôm sau** có thể là **25 giờ**. Do đó, một ngày lịch địa phương không có độ dài giây cố định cho mọi vùng/ngày.

### 10.3. Vì sao ví dụ ở Việt Nam thường không thấy lỗi DST?

Múi giờ `Asia/Ho_Chi_Minh` trong các ngày hiện đại thường không chuyển DST như New York. Vì thế nhiều phép cộng `1 day` và `24 hours` trông giống nhau trong dữ liệu Việt Nam. Điều đó **không chứng minh hai khái niệm tương đương**: khi ứng dụng mở rộng sang thị trường khác hoặc phân tích mốc lịch sử, sự khác biệt sẽ xuất hiện.

### 10.4. Giờ địa phương bị lặp khi chuyển DST

Khi chuyển từ DST về giờ chuẩn, một giá trị như **01:30** có thể xảy ra hai lần. Ví dụ tại New York ngày 01/11/2026:

~~~sql
SELECT
    TIMESTAMPTZ '2026-11-01 01:30:00-04'
        AT TIME ZONE 'America/New_York'
        AS first_wall_clock,
    TIMESTAMPTZ '2026-11-01 01:30:00-05'
        AT TIME ZONE 'America/New_York'
        AS second_wall_clock,
    (
        TIMESTAMPTZ '2026-11-01 01:30:00-05'
        -
        TIMESTAMPTZ '2026-11-01 01:30:00-04'
    ) AS elapsed_between_instants;
~~~

Hai cột đầu có thể **cùng hiển thị 01:30:00**, nhưng hai instant thực tế cách nhau **1 giờ**. Vì thế một local timestamp **không có offset hoặc quy tắc xử lý trường hợp mơ hồ** không luôn đủ để xác định chính xác sự kiện đã xảy ra.

### 10.5. Giờ không tồn tại khi đồng hồ nhảy tới

Ở thời điểm bắt đầu DST, một số local time nằm trong khoảng bị bỏ qua và **không thực sự tồn tại** trên đồng hồ khu vực đó. PostgreSQL có những quy tắc giải quyết đầu vào mơ hồ/không tồn tại, nhưng ứng dụng đặt lịch không nên chỉ chấp nhận âm thầm bất kỳ giờ địa phương nào rồi cho rằng ý định của người dùng đã được bảo toàn.

Với lịch hẹn quan trọng:

1. Lưu **ngày giờ địa phương mà người dùng lựa chọn**.
2. Lưu **tên múi giờ IANA** của địa điểm.
3. Xác định và kiểm tra các thời điểm mơ hồ/không tồn tại theo chính sách sản phẩm.
4. Khi đã chốt mốc, lưu `TIMESTAMPTZ` để thực thi và so sánh.
5. Nếu cần audit, lưu cả offset hoặc thông tin lựa chọn của người dùng ở thời điểm xác nhận.

## 11. CURRENT_TIMESTAMP, now(), statement_timestamp() và clock_timestamp()

PostgreSQL có nhiều cách lấy “thời gian hiện tại”, nhưng chúng **không cùng ý nghĩa trong một transaction dài**.

| Biểu thức | Ý nghĩa |
| --- | --- |
| `CURRENT_TIMESTAMP` | Thời điểm bắt đầu transaction hiện tại, kiểu `TIMESTAMPTZ` |
| `now()` | Tương đương `transaction_timestamp()` |
| `transaction_timestamp()` | Thời điểm bắt đầu transaction |
| `statement_timestamp()` | Thời điểm bắt đầu câu lệnh hiện tại |
| `clock_timestamp()` | Thời gian đồng hồ thực tế tại lúc gọi, có thể thay đổi trong cùng một statement |
| `CURRENT_DATE` | Ngày hiện tại tính từ thời điểm transaction trong múi giờ phiên |

Ví dụ:

~~~sql
BEGIN;

SELECT
    CURRENT_TIMESTAMP AS tx_start,
    now() AS same_tx_start,
    statement_timestamp() AS statement_start,
    clock_timestamp() AS current_wall_clock;

-- Sau một khoảng thời gian, tiếp tục chạy:
SELECT
    now() AS still_tx_start,
    statement_timestamp() AS new_statement_start,
    clock_timestamp() AS current_wall_clock;

ROLLBACK;
~~~

Trong cùng transaction, `now()` ổn định, phù hợp việc tất cả dòng được tạo trong một nghiệp vụ có timestamp nhất quán. `clock_timestamp()` có thể dùng khi cần xem đồng hồ thực tế, nhưng **thời gian đồng hồ hệ thống không phải lúc nào cũng đơn điệu** nếu hệ điều hành đồng bộ/chỉnh giờ. Với đo hiệu năng độ chính xác cao trong ứng dụng, thường nên dùng đồng hồ monotonic của nền tảng khi phù hợp.

### 11.1. DEFAULT now() cho thời điểm tạo

~~~sql
-- Một cột thường gặp:
-- created_at TIMESTAMPTZ NOT NULL DEFAULT now()
~~~

Default này lấy transaction start time khi được đánh giá. Nếu transaction kéo dài, `created_at` không nhất thiết trùng thời điểm server thực sự hoàn tất commit. Khi nghiệp vụ cần thời điểm nhận event bên ngoài, cần xác định rõ mốc được đo và nguồn đồng hồ.

## 12. date_trunc(): làm tròn về đầu đơn vị thời gian

`date_trunc` đưa timestamp về đầu một đơn vị như giờ, ngày, tuần, tháng hoặc năm:

~~~sql
SELECT
    date_trunc(
        'hour',
        TIMESTAMP '2026-11-14 09:47:32'
    ) AS hour_start,
    date_trunc(
        'day',
        TIMESTAMP '2026-11-14 09:47:32'
    ) AS day_start,
    date_trunc(
        'month',
        TIMESTAMP '2026-11-14 09:47:32'
    ) AS month_start;
~~~

Kết quả lần lượt là 09:00, 00:00 cùng ngày và 00:00 ngày đầu tháng.

### 12.1. Khi áp dụng cho timestamptz, múi giờ quan trọng

~~~sql
SET TIME ZONE 'Asia/Ho_Chi_Minh';

SELECT date_trunc(
    'day',
    TIMESTAMPTZ '2026-11-14 03:30:00+00'
) AS start_of_local_day;

RESET TIME ZONE;
~~~

Đây là **nửa đêm theo múi giờ phiên** khi cắt đến mức ngày. Nếu session chạy ở UTC, kết quả nửa đêm và việc phân loại ngày có thể khác.

Trong các phiên bản PostgreSQL hỗ trợ đối số múi giờ thứ ba cho `date_trunc` với `TIMESTAMPTZ`, ta có thể ghi rõ vùng:

~~~sql
SELECT date_trunc(
    'day',
    TIMESTAMPTZ '2026-11-14 03:30:00+00',
    'Asia/Ho_Chi_Minh'
) AS local_day_start_instant;
~~~

Kết quả vẫn là kiểu `TIMESTAMPTZ`, biểu diễn **instant nửa đêm Việt Nam**, dù phiên có thể hiển thị nó ở offset khác.

### 12.2. Tổng hợp theo tháng địa phương

Giả sử bảng `payments` có cột `paid_at TIMESTAMPTZ`:

~~~sql
SELECT
    date_trunc(
        'month',
        paid_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )::date AS local_month_start,
    COUNT(*) AS payment_count,
    SUM(amount) AS total_amount
FROM payments
GROUP BY local_month_start
ORDER BY local_month_start;
~~~

Đây là ví dụ **giả định bảng `payments` tồn tại**; không phải truy vấn chạy được trên database trống. Nó chuyển instant sang giờ Việt Nam rồi lấy tháng địa phương. Một transaction gần ranh giới UTC có thể thuộc tháng khác khi nhóm theo ngày giờ của Việt Nam.

## 13. date_bin(): chia thời gian thành những ô cố định

Từ PostgreSQL 14, `date_bin(stride, source, origin)` hỗ trợ nhóm timestamp/timestamptz theo **bước cố định**, ví dụ 5 phút, 15 phút hoặc 1 giờ.

~~~sql
SELECT
    date_bin(
        INTERVAL '15 minutes',
        TIMESTAMPTZ '2026-11-14 09:37:20+07',
        TIMESTAMPTZ '2026-11-14 00:00:00+00'
    ) AS quarter_hour_bucket;
~~~

`origin` xác định mốc căn lưới để chia ô. Khi áp dụng nhiều nguồn dữ liệu, cần dùng **một origin thống nhất** để tránh các bucket lệch nhau.

### 13.1. Khác với date_trunc ở điểm nào?

- `date_trunc('hour', value)` cắt về đầu giờ theo hệ thống ngày/giờ.
- `date_bin('15 minutes', value, origin)` căn theo **bước 15 phút tính từ origin**.
- `date_bin` không chấp nhận stride có tháng hoặc đơn vị lớn hơn, vì tháng không phải thời lượng cố định.

Ví dụ không hợp lệ:

~~~sql
-- Không chạy: date_bin không cho stride gồm đơn vị tháng.
-- SELECT date_bin(
--     INTERVAL '1 month',
--     now(),
--     TIMESTAMPTZ '2026-01-01 00:00:00+00'
-- );
~~~

Để nhóm theo tháng lịch, sử dụng `date_trunc('month', ...)` với quy tắc múi giờ được định nghĩa.

## 14. generate_series(): tạo dãy ngày và giờ

`generate_series` rất hữu ích để tạo lịch, điền các ngày chưa có dữ liệu khi làm báo cáo và mô phỏng mốc lặp.

### 14.1. Tạo dãy ngày liên tiếp

~~~sql
SELECT
    day_start::date AS calendar_date
FROM generate_series(
    TIMESTAMP '2026-11-01 00:00:00',
    TIMESTAMP '2026-11-07 00:00:00',
    INTERVAL '1 day'
) AS g(day_start)
ORDER BY calendar_date;
~~~

Kết quả có **7 ngày** từ 01/11 tới 07/11, do `generate_series` có thể bao gồm cả mốc cuối khi bước đi tới đúng mốc đó.

### 14.2. Tạo nhiều ô thời gian 30 phút

~~~sql
SELECT
    slot_start,
    slot_start + INTERVAL '30 minutes' AS slot_end
FROM generate_series(
    TIMESTAMP '2026-11-14 09:00',
    TIMESTAMP '2026-11-14 11:00',
    INTERVAL '30 minutes'
) AS slots(slot_start);
~~~

Truy vấn minh họa tạo những slot bắt đầu lúc 09:00, 09:30, 10:00, 10:30 và 11:00. Nếu khung mở cửa kết thúc **đúng 11:00 và không cho slot bắt đầu tại 11:00**, cần chỉnh mốc cuối thành 10:30 hoặc lọc `slot_end <= closing_time` với mô hình đúng.

### 14.3. Lặp “09:00 mỗi ngày” theo giờ địa phương

Khi có DST, không nên cứ cộng `INTERVAL '24 hours'` vào instant trước để tạo lịch “mỗi ngày lúc 09:00”. Nên tạo **ngày địa phương**, kết hợp giờ địa phương rồi chuyển sang instant theo tên vùng:

~~~sql
SELECT
    day_start::date AS local_date,
    (
        day_start::date + TIME '09:00:00'
    ) AT TIME ZONE 'America/New_York' AS appointment_instant
FROM generate_series(
    TIMESTAMP '2026-03-07 00:00:00',
    TIMESTAMP '2026-03-10 00:00:00',
    INTERVAL '1 day'
) AS g(day_start)
ORDER BY local_date;
~~~

Giờ địa phương luôn là **09:00**, nhưng instant UTC sẽ thay đổi tương ứng khi vùng chuyển từ `-05` sang `-04`. Đây là cách mô hình gần với ý định nghiệp vụ của một lịch định kỳ theo đồng hồ.

Với giờ nằm trong vùng mơ hồ/không tồn tại do DST, cần thêm chính sách nghiệp vụ như đã nói ở mục 10; `AT TIME ZONE` một mình không giải quyết toàn bộ yêu cầu chọn đúng lần xuất hiện của giờ địa phương.

## 15. Lọc dữ liệu theo ngày địa phương: dùng khoảng nửa mở

Giả sử có bảng:

~~~sql
-- Ví dụ schema giả định:
-- events(event_id BIGINT, occurred_at TIMESTAMPTZ, ...)
~~~

Ứng dụng cần tìm các sự kiện **trong ngày 14/11/2026 theo lịch Việt Nam**. Không nên làm:

~~~sql
-- Không dùng nếu business_date phải độc lập với TimeZone session:
-- WHERE occurred_at::date = DATE '2026-11-14'
~~~

Với `TIMESTAMPTZ`, phép cast `::date` phụ thuộc múi giờ phiên. Một ứng dụng chạy connection pool ở UTC sẽ khác một phiên `psql` đang dùng giờ Việt Nam.

### 15.1. Mẫu điều kiện đúng với instant boundaries

~~~sql
SELECT *
FROM events
WHERE occurred_at >= (
    TIMESTAMP '2026-11-14 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
)
AND occurred_at < (
    TIMESTAMP '2026-11-15 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
);
~~~

Điều kiện `[start, end)` **bao gồm đầu, loại trừ cuối** giúp:

- Không đếm đôi sự kiện đúng 00:00 của ngày tiếp theo.
- Không phải tìm “mili giây cuối cùng của ngày”.
- Làm việc với độ chính xác microsecond của PostgreSQL.
- Cho planner cơ hội dùng index trên cột `occurred_at` khi phù hợp.

Nếu có index B-tree trên `events(occurred_at)`, so sánh cột gốc với hai `TIMESTAMPTZ` thường thuận tiện hơn cho việc dùng index so với áp hàm lên từng dòng `occurred_at::date`, dù quyết định thực tế vẫn do planner và thống kê.

### 15.2. Ngày ở vùng DST có thể ngắn hoặc dài hơn 24 giờ

Với ngày 08/03/2026 ở New York:

~~~sql
SELECT
    EXTRACT(EPOCH FROM (
        (
            TIMESTAMP '2026-03-09 00:00:00'
                AT TIME ZONE 'America/New_York'
        )
        -
        (
            TIMESTAMP '2026-03-08 00:00:00'
                AT TIME ZONE 'America/New_York'
        )
    )) / 3600 AS local_day_hours;
-- 23
~~~

Vì vậy, nếu muốn “toàn bộ ngày địa phương”, **không lấy instant đầu ngày rồi cộng cứng 24 giờ**. Hãy chuyển đổi **hai ranh giới ngày địa phương** sang instant độc lập. Cách đó cũng phù hợp ngày có 25 giờ.

### 15.3. Báo cáo nhiều cửa hàng ở nhiều múi giờ

Với một bảng cửa hàng lưu `zone_name` (ví dụ `Asia/Ho_Chi_Minh` hoặc `America/New_York`), báo cáo có thể tính local date theo từng cửa hàng:

~~~sql
-- Giả định orders(ordered_at, store_id) và stores(store_id, zone_name)
SELECT
    s.store_id,
    (o.ordered_at AT TIME ZONE s.zone_name)::date
        AS store_local_date,
    COUNT(*) AS orders_count
FROM orders AS o
JOIN stores AS s
    ON s.store_id = o.store_id
GROUP BY
    s.store_id,
    (o.ordered_at AT TIME ZONE s.zone_name)::date
ORDER BY s.store_id, store_local_date;
~~~

Đây là ví dụ **giả định cấu trúc bảng**; trong database thực, cần làm rõ tên vùng lưu có hợp lệ không, chính sách lịch sử theo địa điểm và ảnh hưởng hiệu năng khi nhóm trên nhiều dòng.

## 16. Thiết kế lịch hẹn: lưu instant và tên múi giờ

Một mô hình lịch hẹn thường cần hai thông tin khác nhau:

1. **Mốc thực tế để kích hoạt xử lý, phát thông báo, tính thời gian trôi qua:** `TIMESTAMPTZ`.
2. **Ngữ cảnh địa phương để hiển thị và tái lập ý định người dùng:** tên múi giờ IANA và đôi khi local date/time gốc.

### 16.1. Ví dụ bảng thực hành

Chỉ thực hiện phần DDL sau trên **database lab** mà bạn có quyền tạo schema:

~~~sql
CREATE SCHEMA IF NOT EXISTS temporal_lab;

CREATE TABLE temporal_lab.allowed_zones (
    zone_name TEXT PRIMARY KEY
);

INSERT INTO temporal_lab.allowed_zones (zone_name)
VALUES
    ('Asia/Ho_Chi_Minh'),
    ('America/New_York')
ON CONFLICT (zone_name) DO NOTHING;

CREATE TABLE temporal_lab.appointments (
    appointment_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    subject TEXT NOT NULL,
    zone_name TEXT NOT NULL
        REFERENCES temporal_lab.allowed_zones(zone_name),
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT appointments_positive_window
        CHECK (ends_at > starts_at)
);
~~~

`allowed_zones` là một **whitelist đơn giản cho bài thực hành**, không phải tập hợp toàn bộ timezone IANA; cần xác minh tên với `pg_timezone_names` khi thiết kế hệ thống thực. PostgreSQL không cho dùng subquery trực tiếp trong `CHECK` để tra một bảng timezone cho mỗi hàng; khóa ngoại hoặc validation trong ứng dụng là những cách phù hợp khi có danh sách vùng được phép.

### 16.2. Thêm một lịch hẹn ở Việt Nam

~~~sql
INSERT INTO temporal_lab.appointments
    (subject, zone_name, starts_at, ends_at)
VALUES (
    'Tư vấn PostgreSQL',
    'Asia/Ho_Chi_Minh',
    TIMESTAMP '2026-11-14 09:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh',
    (
        TIMESTAMP '2026-11-14 09:00'
            AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) + INTERVAL '90 minutes'
);
~~~

`starts_at` và `ends_at` lưu instant. Khi cần hiển thị theo múi giờ gốc của lịch hẹn:

~~~sql
SELECT
    appointment_id,
    subject,
    zone_name,
    starts_at AT TIME ZONE zone_name AS local_start,
    ends_at AT TIME ZONE zone_name AS local_end,
    EXTRACT(EPOCH FROM ends_at - starts_at) / 60
        AS elapsed_minutes
FROM temporal_lab.appointments
ORDER BY appointment_id;
~~~

Với dòng ví dụ, thời lượng là **90 phút**, đồng hồ địa phương bắt đầu **09:00** và kết thúc **10:30**.

### 16.3. Vì sao không chỉ lưu một cột local timestamp?

~~~text
local_start = 2026-11-01 01:30:00
~~~

Ở New York vào ngày chuyển khỏi DST, chuỗi này có thể chỉ đến **hai instant khác nhau**. Nếu chỉ lưu một `TIMESTAMP WITHOUT TIME ZONE`, hệ thống không đủ dữ kiện để biết cuộc hẹn thuộc lần 01:30 nào.

Ngược lại, chỉ lưu `TIMESTAMPTZ` mà không lưu tên vùng có thể đủ cho một sự kiện đã xảy ra, nhưng không đủ để biết **vùng địa phương mà khách hàng dự kiến sử dụng** cho các lịch tái diễn hoặc khi quy tắc múi giờ tương lai thay đổi.

### 16.4. Không nhầm thời lượng sự kiện với chu kỳ tái diễn

- “Cuộc hẹn **kéo dài 90 phút**” → độ dài thực tế `INTERVAL '90 minutes'`.
- “Cuộc hẹn lặp **mỗi ngày lúc 09:00** ở New York” → lặp theo **local date + local time + zone**, rồi chuyển thành từng instant.
- “Gia hạn **1 tháng theo lịch**” → cộng tháng theo chính sách ngày đến hạn, không dùng 30 × 24 giờ một cách máy móc.

Những đối tượng này có thể cùng dùng `INTERVAL` tại một số bước, nhưng ngữ nghĩa nghiệp vụ vẫn khác nhau.

## 17. Các ràng buộc thời gian trong schema PostgreSQL

Nếu lưu hai mốc `starts_at` và `ends_at`, ràng buộc cơ bản:

~~~sql
CHECK (ends_at > starts_at)
~~~

có thể ngăn lịch hẹn kết thúc trước khi bắt đầu. Nhưng cần nhớ:

- Khai báo `NOT NULL` riêng cho hai mốc. Với một điều kiện `CHECK` trả `UNKNOWN` do `NULL`, PostgreSQL không tự xem là vi phạm CHECK.
- `CHECK` trên một hàng **không tự ngăn hai lịch hẹn ở hai hàng khác nhau bị chồng nhau**.
- Nếu muốn ngăn đặt trùng tài nguyên (phòng, nhân viên), có thể cân nhắc range type `tstzrange` và exclusion constraint trong thiết kế phù hợp.

### 17.1. Range type cho khoảng thời gian

~~~sql
SELECT
    tstzrange(
        TIMESTAMPTZ '2026-11-14 09:00+07',
        TIMESTAMPTZ '2026-11-14 10:30+07',
        '[)'
    ) AS booking_window;
~~~

`'[)'` nghĩa là **bao gồm đầu, loại trừ cuối**, tương tự điều kiện lọc nửa mở. Hai cuộc hẹn `09:00–10:00` và `10:00–11:00` có thể nối tiếp mà không chồng nhau nếu dùng cùng quy tắc ranh giới.

PostgreSQL có toán tử range overlap `&&`:

~~~sql
SELECT
    tstzrange(
        TIMESTAMPTZ '2026-11-14 09:00+07',
        TIMESTAMPTZ '2026-11-14 10:00+07',
        '[)'
    )
    &&
    tstzrange(
        TIMESTAMPTZ '2026-11-14 09:30+07',
        TIMESTAMPTZ '2026-11-14 10:30+07',
        '[)'
    ) AS overlaps;
-- true
~~~

Để bảo vệ khỏi đặt trùng **khi nhiều transaction đồng thời**, việc chỉ kiểm tra bằng `SELECT` trước `INSERT` không đủ. Một exclusion constraint phù hợp hoặc cơ chế khóa/transaction được thiết kế đúng mới có thể đảm bảo quy tắc ở tầng database. Đây là phần mở rộng ngoài phạm vi chính của bài.

## 18. Java/JDBC: tránh mất ý nghĩa múi giờ khi trao đổi dữ liệu

Khi ứng dụng Java làm việc với PostgreSQL, cần phân biệt rõ:

| Nghiệp vụ | Kiểu Java thường phù hợp | Kiểu PostgreSQL |
| --- | --- | --- |
| Ngày sinh hoặc ngày nghỉ | `LocalDate` | `DATE` |
| Giờ địa phương không có ngày | `LocalTime` | `TIME WITHOUT TIME ZONE` |
| Ngày giờ địa phương | `LocalDateTime` | `TIMESTAMP WITHOUT TIME ZONE` |
| Mốc thời gian đã xác định | `OffsetDateTime` hoặc `Instant` theo cách driver/API hỗ trợ | `TIMESTAMPTZ` |
| Tên múi giờ | `ZoneId`, lưu chuỗi vùng | `TEXT`/`VARCHAR` có validation |
| Thời lượng cố định | `Duration` | `INTERVAL` hoặc số giây/microsecond có quy tắc rõ |
| Khoảng theo lịch gồm năm/tháng | `Period` | Có thể mô hình bằng thành phần lịch hoặc `INTERVAL` theo quy ước nghiệp vụ |

PostgreSQL JDBC hỗ trợ cách ánh xạ Java Time qua JDBC 4.2, trong đó `OffsetDateTime` thường là biểu diễn hợp lý cho `TIMESTAMPTZ`. Cách dùng `Instant` trực tiếp có thể phụ thuộc API/phiên bản driver; không nên mặc định mọi driver tự hiểu một `Instant` khi gọi `setObject` mà không kiểm tra hợp đồng.

### 18.1. Ví dụ dùng OffsetDateTime cho TIMESTAMPTZ

~~~java
OffsetDateTime start =
    OffsetDateTime.parse("2026-11-14T09:00:00+07:00");

try (PreparedStatement ps = con.prepareStatement(
        "INSERT INTO temporal_lab.appointments " +
        "(subject, zone_name, starts_at, ends_at) " +
        "VALUES (?, ?, ?, ?)")) {

    ps.setString(1, "Hẹn tư vấn");
    ps.setString(2, "Asia/Ho_Chi_Minh");
    ps.setObject(3, start);
    ps.setObject(4, start.plusMinutes(90));
    ps.executeUpdate();
}
~~~

Đoạn code giả định `con` là một JDBC `Connection` hợp lệ và schema đã tạo. Trong hệ thống thật, cần transaction boundary, xử lý exception, validation zone và quyền kết nối phù hợp.

### 18.2. Vì sao LocalDateTime không tự xác định instant?

~~~java
LocalDateTime local =
    LocalDateTime.of(2026, 11, 14, 9, 0);
~~~

Giá trị này **không có múi giờ**. Muốn xác định instant dựa trên vùng:

~~~java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime zoned = local.atZone(zone);
Instant instant = zoned.toInstant();
~~~

Với vùng có DST, `atZone` của Java áp dụng các quy tắc xử lý local time mơ hồ/không tồn tại của Java. Cần thống nhất chính sách với logic PostgreSQL, đặc biệt khi lịch ở thời điểm đổi DST.

### 18.3. Duration và Period không giống nhau

~~~java
Duration ninetyMinutes = Duration.ofMinutes(90);
Period oneCalendarMonth = Period.ofMonths(1);
~~~

`Duration` phản ánh thời lượng theo đơn vị thời gian cố định; `Period` phản ánh số năm/tháng/ngày theo lịch. Việc PostgreSQL gói các thành phần vào `INTERVAL` không có nghĩa mọi ngôn ngữ lập trình cũng biểu diễn chúng trong một kiểu với đúng cùng quy tắc.

Khi thiết kế API, phải thỏa thuận rõ đầu vào là **elapsed duration** hay **calendar interval**. Ví dụ `"P1M"` là một tháng trong ISO 8601, khác `"PT1M"` là một phút.

## 19. Hiệu năng khi truy vấn và lưu dữ liệu thời gian

Các truy vấn thời gian thường chạy trên bảng lớn nên cần xét cách sử dụng index:

### 19.1. Ưu tiên range trên cột gốc cho lọc theo thời điểm

Giả sử bảng giao dịch có:

~~~sql
-- Ví dụ bảng đã tồn tại:
-- CREATE INDEX idx_events_occurred_at ON events(occurred_at);
~~~

Lọc theo khoảng:

~~~sql
SELECT *
FROM events
WHERE occurred_at >= TIMESTAMPTZ '2026-11-14 00:00:00+07'
  AND occurred_at <  TIMESTAMPTZ '2026-11-15 00:00:00+07';
~~~

Với biểu thức này, planner có thể xét index B-tree theo `occurred_at` nếu chọn lọc và dữ liệu phù hợp. Ngược lại:

~~~sql
-- Diễn giải phụ thuộc TimeZone của session
SELECT *
FROM events
WHERE occurred_at::date = DATE '2026-11-14';
~~~

không cùng ý nghĩa nếu session không ở múi giờ nghiệp vụ, và phép cast trên mỗi dòng có thể khiến một index thông thường trên cột gốc khó được sử dụng trực tiếp hơn.

Index biểu thức có thể giúp một số kiểu truy vấn, nhưng với nhiều zone thay đổi theo từng cửa hàng, việc cố tạo index cho mọi phép chuyển đổi giờ địa phương không phải lúc nào cũng hợp lý. Cần đo `EXPLAIN (ANALYZE, BUFFERS)` trên môi trường phù hợp.

### 19.2. Bản ghi thời gian và múi giờ nên tách nghĩa

Một hệ thống phân tán thường có quy ước:

~~~text
occurred_at  TIMESTAMPTZ  -- mốc sự kiện
zone_name    TEXT         -- địa phương dùng để hiển thị hoặc tính lịch
business_day DATE         -- ngày nghiệp vụ nếu được chốt theo quy tắc riêng
~~~

Không nên trộn các ý nghĩa trên vào một cột `VARCHAR` chứa chuỗi ngày giờ mơ hồ. Với nghiệp vụ cần báo cáo thường xuyên theo `business_day` đã được xác định, việc lưu thêm ngày nghiệp vụ có thể hữu ích, nhưng cần quy tắc cập nhật và nhất quán khi timezone/nguồn dữ liệu đổi.

### 19.3. Chênh lệch giữa sự kiện và ngày báo cáo

Một đơn hàng:

~~~text
occurred_at = 2026-11-13 18:30:00 UTC
~~~

có thể là:

~~~text
2026-11-14 01:30:00 ở Asia/Ho_Chi_Minh
~~~

Do đó, báo cáo tổng hợp theo **ngày UTC 13/11** sẽ khác báo cáo theo **ngày bán hàng Việt Nam 14/11**. Cả hai đều có thể đúng nếu yêu cầu nghiệp vụ xác định rõ ngày của hệ quy chiếu nào.

## 20. Lỗi phổ biến khi dùng INTERVAL và múi giờ

| Hiểu nhầm | Điều đúng cần nhớ |
| --- | --- |
| “`TIMESTAMP` luôn là thời điểm UTC” | `TIMESTAMP WITHOUT TIME ZONE` không tự chứa offset hay instant |
| “`TIMESTAMPTZ` giữ nguyên tên timezone được nhập” | Nó lưu mốc tuyệt đối; tên vùng cần lưu riêng nếu muốn bảo toàn |
| “`1 month` là 30 ngày chính xác” | Tháng theo lịch có số ngày khác nhau |
| “`1 day` luôn bằng `24 hours` khi cộng vào timestamptz” | Qua DST, ngày lịch địa phương có thể dài 23 hoặc 25 giờ |
| “Cộng một tháng hai lần luôn giống cộng hai tháng trực tiếp” | Điều chỉnh ngày cuối tháng có thể làm hai cách khác nhau |
| “`EXTRACT(MINUTE FROM interval)` cho tổng phút” | Nó trích thành phần phút, không cộng toàn bộ giờ/ngày thành phút |
| “`age(a,b)` thích hợp đo latency” | `age` mô tả chênh lệch theo lịch; đo latency bằng hiệu hai instant |
| “`now()` luôn cập nhật sau mỗi statement trong một transaction” | `now()` cố định tại transaction start |
| “Đổi `SET TIME ZONE` sẽ làm thay đổi thời điểm đã lưu” | Nó thay cách hiển thị/diễn giải, không viết lại instant |
| “Offset `-05` là timezone New York quanh năm” | New York có DST, offset thay đổi theo ngày |
| “Local time `01:30` luôn xác định một instant duy nhất” | Ở thời điểm đồng hồ lùi, giờ địa phương có thể lặp |
| “Ngày địa phương luôn là 86.400 giây” | Qua DST, có ngày 23 hoặc 25 giờ |
| “`BETWEEN start AND end` phù hợp hai ngày liên tiếp” | Hai đầu đều bao gồm, dễ đếm đôi mốc cuối; thường dùng `>=` và `<` |
| “`occurred_at::date` độc lập với timezone” | Với `TIMESTAMPTZ` nó phụ thuộc `TimeZone` session |
| “`date_bin` có thể dùng stride một tháng” | Stride chứa tháng hoặc đơn vị lớn hơn không được hỗ trợ |
| “Giữ mỗi local datetime đủ cho lịch quốc tế” | Cần vùng IANA và quy tắc DST; lưu instant khi đã chốt sự kiện |
| “`CHECK (end > start)` ngăn hai cuộc hẹn trùng nhau” | Nó chỉ kiểm tra từng hàng, không ngăn overlap giữa các hàng |
| “`INTERVAL` trong PostgreSQL luôn ánh xạ một-một sang Java Duration” | Interval có months/days/time, trong Java cần phân biệt Duration và Period |

## 21. Bài thực hành tổng hợp

### Bài 1 — Phân biệt kiểu bằng pg_typeof

Chạy:

~~~sql
SELECT
    pg_typeof(DATE '2026-11-14') AS date_type,
    pg_typeof(TIMESTAMP '2026-11-14 09:00')
        AS timestamp_type,
    pg_typeof(TIMESTAMPTZ '2026-11-14 09:00+07')
        AS instant_type,
    pg_typeof(INTERVAL '90 minutes')
        AS interval_type;
~~~

**Câu hỏi:** kiểu nào lưu một mốc thời gian tuyệt đối? Kiểu nào chỉ là ngày lịch, và kiểu nào diễn tả độ dài?

### Bài 2 — Cộng tháng ngày cuối kỳ

Tính và giải thích:

~~~sql
SELECT
    DATE '2024-01-31' + INTERVAL '1 month' AS a,
    DATE '2024-01-31' + INTERVAL '30 days' AS b,
    DATE '2025-01-31' + INTERVAL '1 month' AS c;
~~~

**Gợi ý:** a là ngày 29/02/2024; b là ngày 01/03/2024; c là ngày 28/02/2025. Dùng ví dụ để nêu vì sao “sau một tháng” phải có chính sách lịch rõ ràng.

### Bài 3 — Lấy tổng số phút xử lý

Hai instant:

~~~text
2026-11-14 09:00:00+07
2026-11-14 10:20:30+07
~~~

Viết truy vấn trả số phút thực tế:

~~~sql
SELECT
    EXTRACT(EPOCH FROM (
        TIMESTAMPTZ '2026-11-14 10:20:30+07'
        -
        TIMESTAMPTZ '2026-11-14 09:00:00+07'
    )) / 60 AS duration_minutes;
~~~

**Đáp án:** 80,5 phút.

### Bài 4 — Chuyển đồng hồ Việt Nam sang UTC

Ngày 14/11/2026 lúc 09:00 ở `Asia/Ho_Chi_Minh` tương ứng mốc UTC nào? Dùng:

~~~sql
SELECT
    (
        TIMESTAMP '2026-11-14 09:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AT TIME ZONE 'UTC' AS utc_wall_clock;
~~~

**Đáp án:** 02:00 UTC cùng ngày. Cột kết quả là `TIMESTAMP WITHOUT TIME ZONE` hiển thị đồng hồ UTC; instant trung gian là `TIMESTAMPTZ`.

### Bài 5 — Chênh lệch DST

Chạy ví dụ ở mục 10 với `America/New_York` qua ngày 08/03/2026. Giải thích vì sao `start_at + INTERVAL '1 day'` cho 12:00 địa phương nhưng `start_at + INTERVAL '24 hours'` cho 13:00.

**Gợi ý:** offset thay đổi từ `-05` sang `-04`; thời gian thực từ trưa hôm trước tới trưa hôm sau chỉ là 23 giờ.

### Bài 6 — Lọc một ngày địa phương bằng khoảng nửa mở

Viết hai ranh giới `TIMESTAMPTZ` để truy vấn mọi sự kiện của **ngày 08/03/2026 tại New York**:

~~~sql
SELECT
    TIMESTAMP '2026-03-08 00:00'
        AT TIME ZONE 'America/New_York'
        AS lower_bound,
    TIMESTAMP '2026-03-09 00:00'
        AT TIME ZONE 'America/New_York'
        AS upper_bound;
~~~

**Câu hỏi:** vì sao không lấy `lower_bound + INTERVAL '24 hours'` làm upper bound? Hai mốc thực tế cách nhau bao nhiêu giờ?

**Gợi ý:** 23 giờ do DST.

### Bài 7 — Lập lịch 09:00 mỗi ngày

Với vùng `America/New_York`, tạo lịch 09:00 cho các ngày 07–10/03/2026 bằng `generate_series` theo **ngày địa phương**, sau đó chuyển từng ngày/giờ bằng `AT TIME ZONE`. Dự đoán vì sao giờ UTC thay đổi sau ngày bắt đầu DST.

### Bài 8 — Ràng buộc lịch hẹn

Tạo bảng lab có `starts_at` và `ends_at` là `TIMESTAMPTZ NOT NULL`, `CHECK (ends_at > starts_at)`. Thử chèn một cuộc hẹn kết thúc trước khi bắt đầu và quan sát lỗi ràng buộc. Đặt câu hỏi: nếu hai cuộc hẹn có thời gian chồng nhau ở hai hàng khác nhau, CHECK đơn giản này có chặn được không?

**Đáp án:** không; cần kiểm tra logic nhiều hàng, đồng thời có thể dùng exclusion constraint với range type trong thiết kế phù hợp.

### Bài 9 — date_bin và nhóm 15 phút

Cho các event tại 09:02, 09:17, 09:29 và 09:45 trong cùng ngày/múi giờ. Dùng `date_bin('15 minutes', ..., origin)` để nhóm vào ô 09:00, 09:15, 09:15 và 09:45 tương ứng. Hãy giải thích vì sao origin phải được xác định nhất quán.

### Bài 10 — Chọn kiểu khi thiết kế API

Một ứng dụng có các trường:

~~~text
birth_date
daily_open_time
store_time_zone
order_created_at
appointment_starts_at
appointment_duration
next_billing_month
~~~

Hãy chọn kiểu PostgreSQL và cách biểu diễn Java phù hợp. Chỉ ra trường nào là **ngày**, trường nào là **đồng hồ địa phương**, trường nào là **instant**, và trường nào là **quy tắc khoảng thời gian theo lịch**. Không gộp mọi trường thành chuỗi định dạng không rõ múi giờ.

## 22. Gợi ý quy trình rà soát logic thời gian trong ứng dụng thật

Khi một API có dấu hiệu trả ngày giờ sai, có thể theo trình tự:

1. **Xác nhận kiểu cột:** dùng `information_schema.columns` hoặc `\d` của `psql` xem `TIMESTAMP` hay `TIMESTAMPTZ`.
2. **Xác nhận đầu vào:** chuỗi có offset hay tên zone không? Parse bằng Java Time theo kiểu nào?
3. **Xác nhận `TimeZone` session:** chạy `SHOW TimeZone` trên **connection thực đang gây lỗi**.
4. **Xác nhận ý nghĩa nghiệp vụ:** một tháng lịch, một ngày địa phương hay 24 giờ thực tế?
5. **Kiểm tra DST:** nếu sự kiện ở vùng đổi giờ, kiểm tra thời điểm mơ hồ/không tồn tại.
6. **So sánh instant UTC:** chuyển mốc `TIMESTAMPTZ` sang UTC để điều tra lỗi biểu diễn.
7. **Xem truy vấn lọc ngày:** có ép `::date` phụ thuộc timezone hoặc dùng `BETWEEN` ở hai đầu không?
8. **Xác định nơi tạo dữ liệu:** dùng `now()` tại transaction start, đồng hồ của client hay timestamp từ dịch vụ khác?
9. **Thử trên mốc biên:** cuối tháng, 29/02, ranh giới UTC/local day, thời điểm chuyển DST và dữ liệu lịch sử.
10. **Chọn cách sửa có thể kiểm chứng:** sửa kiểu/API/truy vấn theo ý nghĩa, không tự ý cộng/trừ số giờ cố định để “chỉnh lệch múi giờ”.

Đây là quy trình điều tra, không phải phép biến đổi tự động phù hợp cho mọi database. Với cột lịch sử lưu sai kiểu hoặc từng nhập local timestamp như UTC, cần có kế hoạch migration dữ liệu được kiểm thử thay vì `UPDATE` hàng loạt theo một offset đoán trước.

## 23. Tài liệu PostgreSQL chính thức

Các tài liệu sau có thể dùng để đối chiếu hành vi theo phiên bản PostgreSQL đang triển khai:

- [Date/Time Types](https://www.postgresql.org/docs/current/datatype-datetime.html): `DATE`, `TIME`, `TIMESTAMP`, `TIMESTAMPTZ`, `INTERVAL`, cấu trúc và cú pháp giá trị.
- [Date/Time Functions and Operators](https://www.postgresql.org/docs/current/functions-datetime.html): cộng trừ, `age`, `EXTRACT`, `date_trunc`, `date_bin`, `AT TIME ZONE` và các hàm hiện tại.
- [Date/Time Input Interpretation](https://www.postgresql.org/docs/current/datetime-input-rules.html): giải thích cách PostgreSQL đọc literal có/không có múi giờ và xử lý thời gian.
- [Date/Time Output](https://www.postgresql.org/docs/current/datatype-datetime.html): cách định dạng, `DateStyle` và `IntervalStyle`.
- [Time Zones](https://www.postgresql.org/docs/current/datetime-config-files.html): dữ liệu vùng giờ, cách cấu hình và diễn giải tên vùng theo tài liệu phiên bản.

Đường dẫn `/docs/current/` chỉ tới phiên bản ổn định hiện hành. Khi dùng một instance PostgreSQL với major version cụ thể, hãy đối chiếu tài liệu của **đúng phiên bản đó**, nhất là những hàm hoặc dạng quá tải mới được bổ sung ở các bản khác nhau.

## 24. Tổng kết

Trong PostgreSQL, **`INTERVAL` không chỉ là một số giây**: nó có các thành phần **tháng, ngày và phần thời gian** để biểu diễn cả phép tính theo lịch lẫn thời lượng. Chính vì thế, cộng một tháng, cộng một ngày lịch và cộng 24 giờ có thể dẫn đến các kết quả khác nhau.

**`TIMESTAMP WITHOUT TIME ZONE`** biểu diễn ngày giờ theo đồng hồ chưa gắn instant; **`TIMESTAMPTZ`** biểu diễn một mốc tuyệt đối và được hiển thị theo múi giờ phiên. Toán tử **`AT TIME ZONE`** nối hai thế giới này: từ local datetime + vùng sang instant, hoặc từ instant sang đồng hồ địa phương. Ở những vùng có DST, cần đặc biệt phân biệt **khoảng lịch** với **thời gian thực trôi qua**.

Khi lập lịch, báo cáo hay tính thời hạn, hãy xác định **ý nghĩa nghiệp vụ** trước rồi mới chọn kiểu và phép toán. Các mẫu đáng nhớ gồm `EXTRACT(EPOCH FROM end_at - start_at)` cho thời gian thực, `date_trunc` cho ranh giới lịch, `date_bin` cho lưới thời gian cố định, `generate_series` cho dãy ngày, và điều kiện **`>= start AND < end`** cho khoảng lọc nửa mở. Nắm vững những nguyên tắc này giúp dữ liệu thời gian chính xác, truy vấn nhất quán và ứng dụng có thể mở rộng qua nhiều múi giờ mà không dựa vào các giả định sai về số giờ trong một ngày hay số ngày trong một tháng.

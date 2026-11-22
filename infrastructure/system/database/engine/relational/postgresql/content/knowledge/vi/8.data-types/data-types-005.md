# date, time, timestamp và timestamp with time zone trong PostgreSQL

Khi xây dựng một hệ thống bán hàng, đặt lịch hoặc theo dõi sự kiện, chúng ta thường lưu nhiều dạng thông tin liên quan đến thời gian: **ngày sinh**, **giờ mở cửa**, **ngày giờ dự kiến của cuộc hẹn** và **thời điểm thanh toán thực sự xảy ra**. Chúng có thể được hiển thị dưới dạng những chuỗi rất giống nhau, nhưng không mang cùng ngữ nghĩa. Nhầm lẫn giữa chúng có thể khiến dữ liệu bị lệch giờ khi ứng dụng chuyển môi trường, giao dịch bị tính vào sai ngày báo cáo hoặc lịch hẹn thay đổi ngoài ý muốn khi múi giờ có giờ mùa hè.

PostgreSQL cung cấp bốn kiểu cốt lõi để mô hình hóa các nhu cầu đó:

- **`DATE`**: một ngày trên lịch, không có giờ hoặc múi giờ.
- **`TIME WITHOUT TIME ZONE`**, viết ngắn `TIME`: một giờ trên đồng hồ, không có ngày.
- **`TIMESTAMP WITHOUT TIME ZONE`**, viết ngắn `TIMESTAMP`: ngày và giờ, nhưng chưa xác định múi giờ.
- **`TIMESTAMP WITH TIME ZONE`**, thường viết `TIMESTAMPTZ`: một **thời điểm tuyệt đối** có thể hiển thị ở nhiều múi giờ khác nhau.

Bài học thuộc chương **Kiểu dữ liệu** của module PostgreSQL. Chúng ta sẽ tìm hiểu cách chọn kiểu đúng, cách PostgreSQL xử lý offset và múi giờ, toán tử `AT TIME ZONE`, thời gian hiện tại, tính khoảng thời gian, truy vấn theo ngày địa phương, chỉ mục, quy tắc daylight saving time và tích hợp Java/JDBC.

## 1. Chọn kiểu theo ý nghĩa nghiệp vụ

Trước khi tạo cột, hãy hỏi: giá trị này mô tả **ngày**, **giờ trong ngày**, **ngày giờ trên đồng hồ** hay **một khoảnh khắc đã được xác định**?

| Dữ liệu | Kiểu nên cân nhắc | Lý do |
|---|---|---|
| Ngày sinh 14/11/1995 | `DATE` | Ngày sinh không thay đổi theo múi giờ người xem |
| Ngày chốt sổ 30/11/2026 | `DATE` | Đây là nhãn ngày theo quy tắc nghiệp vụ |
| Giờ mở cửa 09:00 hằng ngày | `TIME` | Chỉ có giờ, chưa có ngày và instant |
| Lịch dự kiến 09:30 ngày 14/11/2026 ở Hà Nội | `TIMESTAMP` kết hợp timezone ID | Phải biết nơi áp dụng để chuyển thành instant |
| Thanh toán thành công lúc 02:30 UTC | `TIMESTAMPTZ` | Là một mốc thời gian tuyệt đối |
| Thời điểm ghi audit log | `TIMESTAMPTZ` | Phải so sánh được giữa các hệ thống |
| Cuộc gọi dài 90 phút | `INTERVAL` hoặc số giây | Đây là duration, không phải giờ trên đồng hồ |

Một chuỗi như `2026-11-14 09:30:00` **chưa đủ để xác định một instant**. Đó có thể là giờ địa phương ở Việt Nam, Tokyo, New York hoặc chỉ là giá trị chưa được gắn timezone.

### 1.1. Một bài toán đặt lịch

Giả sử khách muốn đặt cuộc hẹn tại Việt Nam lúc 09:30 ngày 14/11/2026:

~~~text
Ngày lịch:           2026-11-14
Giờ địa phương:      09:30
Timezone địa điểm:   Asia/Ho_Chi_Minh
Instant tương ứng:   2026-11-14 02:30 UTC
~~~

Nếu chỉ lưu `DATE`, chúng ta mất giờ. Nếu chỉ lưu `TIME`, chúng ta mất ngày. Nếu chỉ lưu `TIMESTAMP`, chúng ta có giờ nhưng thiếu timezone cần thiết để xác định instant. Nếu lưu `TIMESTAMPTZ`, PostgreSQL biết instant nhưng **không tự lưu tên timezone gốc** mà khách đã chọn.

Vì thế, một hệ thống lịch hẹn có thể cần lưu **local date-time**, **IANA timezone ID** và **instant** dưới những cột mang nhiệm vụ khác nhau.

## 2. Cú pháp khai báo và tên viết tắt

~~~sql
CREATE TABLE temporal_basics (
    event_day DATE,
    opening_clock TIME,
    planned_local TIMESTAMP,
    occurred_at TIMESTAMP WITH TIME ZONE
);
~~~

Các cách viết tương đương:

~~~sql
-- Không kèm timezone.
TIME WITHOUT TIME ZONE
TIME

TIMESTAMP WITHOUT TIME ZONE
TIMESTAMP

-- Có timezone.
TIMESTAMP WITH TIME ZONE
TIMESTAMPTZ
~~~

Cần nhớ kỹ: **`TIMESTAMP` không có nghĩa là `TIMESTAMPTZ`**. PostgreSQL mặc định timestamp không có timezone nếu không ghi phần `WITH TIME ZONE`.

### 2.1. Precision của phần giây

PostgreSQL hỗ trợ precision phần giây từ **0 đến 6**:

~~~sql
CREATE TABLE temporal_precision (
    a TIME(0),
    b TIME(3),
    c TIME(6),
    d TIMESTAMP(3),
    e TIMESTAMPTZ(6)
);
~~~

| Kiểu | Mức chi tiết mong muốn |
|---|---|
| `TIME(0)` | Tới giây |
| `TIME(3)` | Tới millisecond |
| `TIME(6)` | Tới microsecond |
| `TIMESTAMP(0)` | Ngày giờ không có phần giây lẻ |
| `TIMESTAMPTZ(6)` | Instant tới microsecond |

Nếu không chỉ định precision, PostgreSQL có thể lưu phần giây tới độ chính xác microsecond của hệ thống. Khi đổi sang precision nhỏ hơn, phần giây có thể được làm tròn. Đừng giả định làm tròn hoặc định dạng đầu ra có cùng hành vi ở mọi thư viện ứng dụng.

### 2.2. Kích thước lưu trữ

Trong PostgreSQL hiện đại thông dụng, `DATE` có kích thước giá trị cơ bản **4 byte**, còn `TIME`, `TIMESTAMP` và `TIMESTAMPTZ` thường là **8 byte**. Đây không phải tổng kích thước hàng trên đĩa, vì hàng còn có overhead, NULL bitmap, index và các cấu trúc khác.

## 3. DATE: một ngày trên lịch

Ví dụ:

~~~sql
SELECT DATE '2026-11-14' AS business_date;
~~~

`DATE` chỉ có năm, tháng, ngày. Nó không lưu giờ, offset hay tên timezone. Lưu ngày sinh:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name TEXT NOT NULL,
    birth_date DATE
);

INSERT INTO customers (full_name, birth_date)
VALUES ('An', DATE '1995-11-14');
~~~

Ngày sinh vẫn là `1995-11-14` dù người đọc ở Việt Nam hay Canada. Đây là lý do không nên dùng một instant vào lúc 00:00 ở một timezone để thay thế mọi giá trị date-only.

### 3.1. DATE và ngày nghiệp vụ

Giả sử một giao dịch xảy ra lúc 00:30 UTC. Ở California, nó có thể vẫn thuộc **ngày hôm trước** trên lịch địa phương; tại Việt Nam thì đã sang ngày mới.

Nếu báo cáo yêu cầu “ngày doanh thu theo giờ Việt Nam”, hãy xác định ngày từ instant bằng timezone Việt Nam:

~~~sql
SELECT (
    TIMESTAMPTZ '2026-11-14 00:30:00+00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh'
)::DATE AS vietnam_business_date;
~~~

Cột `DATE` phù hợp để **lưu kết quả ngày nghiệp vụ đã xác định**, nhưng PostgreSQL không thể tự suy ra timezone hay ngày cut-off mà doanh nghiệp muốn nếu bạn không quy định.

### 3.2. Kiểm tra ngày hợp lệ

~~~sql
SELECT DATE '2024-02-29';
~~~

Ngày 29/02/2024 hợp lệ vì 2024 là năm nhuận. Ngược lại:

~~~sql
-- Ngày này không hợp lệ:
-- SELECT DATE '2026-02-29';
~~~

PostgreSQL kiểm tra tính hợp lệ của giá trị lịch, nhưng những quy tắc như “ngày giao hàng phải sau ngày đặt” cần constraint hoặc logic ứng dụng tương ứng.

## 4. TIME: giờ trên đồng hồ, không phải duration

Ví dụ:

~~~sql
SELECT
    TIME '09:00:00' AS opens_at,
    TIME '17:30:00' AS closes_at,
    TIME(3) '09:15:30.125' AS precise_clock;
~~~

Một bảng mô tả giờ mở cửa:

~~~sql
CREATE TABLE office_hours (
    office_id BIGINT NOT NULL,
    iso_weekday SMALLINT NOT NULL
        CHECK (iso_weekday BETWEEN 1 AND 7),
    opens_at TIME NOT NULL,
    closes_at TIME NOT NULL,
    PRIMARY KEY (office_id, iso_weekday)
);
~~~

Ở đây `opens_at = '09:00'` có nghĩa **mở cửa lúc 09:00 trên đồng hồ địa phương của chi nhánh**. Chỉ có giá trị đó chưa đủ để biết instant theo UTC.

### 4.1. TIME không lưu ngày

Nếu khách đặt cuộc hẹn lúc 09:00, chỉ lưu `TIME '09:00'` sẽ không cho biết khách hẹn vào thứ Hai nào hoặc tháng nào.

Một lịch lặp hằng tuần có thể dùng `iso_weekday` + `TIME` + timezone ID. Một cuộc hẹn đã được xác định nên có ngày hoặc instant cụ thể.

### 4.2. TIME không phải thời lượng

~~~sql
SELECT TIME '02:30:00';
~~~

Biểu thức trên là “02:30 trên đồng hồ”, **không** có nghĩa “mất 2 giờ 30 phút”. Duration nên là:

~~~sql
SELECT INTERVAL '2 hours 30 minutes';
~~~

Hoặc số giây/millisecond nếu dữ liệu đo đạc yêu cầu đơn vị cố định.

### 4.3. Ca qua nửa đêm

Giả sử:

~~~text
opens_at  = 22:00
closes_at = 02:00
~~~

Ca làm việc kết thúc vào ngày kế tiếp. Điều kiện `closes_at > opens_at` sẽ sai dù lịch hoàn toàn hợp lệ. Thiết kế cần quy tắc “qua ngày”, ngày đóng hoặc dữ liệu lịch theo khoảng thời gian.

### 4.4. TIME WITH TIME ZONE

PostgreSQL có kiểu `TIME WITH TIME ZONE` (biệt danh `timetz`), nhưng nó không phải lựa chọn lý tưởng cho lịch địa phương ở nhiều vùng vì **không có ngày** để xác định quy tắc daylight saving time.

Một UTC offset là chênh lệch theo thời điểm, không thay thế IANA timezone ID của địa điểm. Với lịch hằng ngày, thường dùng `TIME` và lưu timezone địa lý ở cột khác.

## 5. TIMESTAMP WITHOUT TIME ZONE: ngày giờ chưa gắn vùng

Khai báo:

~~~sql
SELECT TIMESTAMP '2026-11-14 09:30:00';
~~~

Kiểu này lưu các thành phần:

~~~text
Year    = 2026
Month   = 11
Day     = 14
Hour    = 09
Minute  = 30
Second  = 00
~~~

Nó **không ghi offset +07, không giữ tên Asia/Ho_Chi_Minh và không biểu diễn sẵn một instant tuyệt đối**.

### 5.1. Không mặc định là timezone server

Một lỗi phổ biến là đọc `TIMESTAMP` như “giờ địa phương của máy chủ”. Thực chất, giá trị `TIMESTAMP '2026-11-14 09:30'` không gắn timezone. PostgreSQL chỉ dùng timezone khi có một **phép chuyển đổi hoặc so sánh** đòi hỏi diễn giải nó thành instant.

### 5.2. Trường hợp dùng

- Ngày giờ người dùng chọn trong một địa điểm cụ thể.
- Lịch dự kiến được biểu diễn theo giờ đồng hồ địa phương.
- Dữ liệu nhập từ hệ thống legacy theo quy ước timezone đã biết.
- Những trường hợp muốn giữ nguyên thành phần ngày giờ khi người dùng đổi session TimeZone.

Ví dụ:

~~~sql
CREATE TABLE meeting_plans (
    meeting_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    planned_local TIMESTAMP NOT NULL,
    timezone_name TEXT NOT NULL
);
~~~

Nếu `planned_local = '2026-11-14 09:30'` và `timezone_name = 'Asia/Ho_Chi_Minh'`, hai trường cùng nhau đủ để xác định quy tắc diễn giải thời điểm trong trường hợp không mơ hồ.

### 5.3. TIMESTAMP không chứng minh giờ địa phương đã từng tồn tại

Ở những vùng có DST, một ngày có thể không có mốc 02:30 vì đồng hồ nhảy từ 01:59 lên 03:00, hoặc 01:30 có thể xuất hiện hai lần khi đồng hồ quay lùi. `TIMESTAMP` vẫn có thể chứa những thành phần lịch đó; **chính việc gắn timezone để tạo instant mới làm lộ vấn đề**.

## 6. TIMESTAMP WITH TIME ZONE: instant

`TIMESTAMP WITH TIME ZONE` hay `TIMESTAMPTZ` biểu diễn một thời điểm tuyệt đối:

~~~sql
SELECT TIMESTAMPTZ '2026-11-14 09:30:00+07';
~~~

Giờ Việt Nam 09:30 ở offset +07 tương ứng **02:30 UTC**.

~~~sql
SELECT
    TIMESTAMPTZ '2026-11-14 09:30:00+07'
    = TIMESTAMPTZ '2026-11-14 02:30:00+00'
    AS same_instant;
~~~

Kết quả là `true`. PostgreSQL so sánh các instant, không chỉ so chuỗi hiển thị.

### 6.1. Timestamptz có giữ timezone gốc không?

**Không.** PostgreSQL lưu giá trị biểu diễn instant theo mốc thời gian chuẩn hóa; nó không giữ riêng tên timezone như `Asia/Ho_Chi_Minh` hoặc offset `+07` mà người dùng nhập.

Ví dụ hai khách gửi:

~~~text
2026-11-14 09:30+07
2026-11-14 11:30+09
~~~

Hai giá trị cùng là 02:30 UTC. Nếu chỉ lưu `timestamptz`, không thể biết khách ban đầu nhập bằng offset nào.

Muốn giữ timezone được chọn, thêm cột:

~~~sql
timezone_name TEXT NOT NULL
~~~

### 6.2. Những cột nên dùng timestamptz

- `created_at`, `updated_at`.
- `paid_at`, `shipped_at`.
- `received_at` của message/event.
- `audit_occurred_at`.
- Thời điểm bắt đầu/kết thúc cuộc hẹn đã được xác định.
- Mốc thời gian cần so sánh giữa nhiều quốc gia.

Nếu câu hỏi là **“sự kiện thực sự diễn ra lúc nào?”**, `timestamptz` thường phù hợp nhất.

## 7. TimeZone của session và cách hiển thị

Kiểm tra timezone của kết nối PostgreSQL hiện tại:

~~~sql
SHOW TIME ZONE;
~~~

Trong môi trường thử nghiệm:

~~~sql
SET TIME ZONE 'UTC';

SELECT TIMESTAMPTZ '2026-11-14 09:30:00+07'
    AS shown_in_utc;
~~~

Instant sẽ được hiển thị theo UTC, về mặt ý nghĩa là `2026-11-14 02:30:00+00`.

~~~sql
SET TIME ZONE 'Asia/Ho_Chi_Minh';

SELECT TIMESTAMPTZ '2026-11-14 09:30:00+07'
    AS shown_in_vietnam;
~~~

Cùng instant có thể hiển thị `2026-11-14 09:30:00+07`.

Trả về timezone trước đó của session:

~~~sql
RESET TIME ZONE;
~~~

### 7.1. Đổi TimeZone không đổi instant đã lưu

~~~text
Instant: 2026-11-14 02:30 UTC

UTC session:            02:30+00
Asia/Ho_Chi_Minh:       09:30+07
Asia/Tokyo:             11:30+09
~~~

Ba cách hiển thị vẫn mô tả **một instant**.

### 7.2. Ép kiểu từ timestamp không timezone có thể phụ thuộc session

~~~sql
SET TIME ZONE 'UTC';

SELECT TIMESTAMP '2026-11-14 09:30:00'::TIMESTAMPTZ;
~~~

Với session UTC, giá trị được diễn giải là 09:30 UTC.

Nếu session dùng `Asia/Ho_Chi_Minh`, cùng phép ép kiểu sẽ diễn giải 09:30 là giờ Việt Nam, tương ứng 02:30 UTC.

**Không chuyển kiểu mơ hồ nếu đã biết timezone nguồn.** Hãy dùng `AT TIME ZONE` với tên vùng rõ ràng.

### 7.3. Connection pooling

Một ứng dụng có thể tái sử dụng connection giữa nhiều request. Nếu request trước đổi session timezone mà pool không reset state, request sau có thể đọc/cast dữ liệu dưới ngữ cảnh khác.

Do đó:

- Quản lý session timezone theo hợp đồng kết nối.
- Cân nhắc chuẩn hóa timezone session về `UTC`.
- Dùng `AT TIME ZONE` rõ ràng cho quy tắc báo cáo.
- Không phụ thuộc timezone hiện hành khi chuyển legacy timestamp có nguồn cố định.

## 8. Bẫy: timestamp literal chứa offset

Trong PostgreSQL, kiểu literal được xác định trước khi nội dung chuỗi được diễn giải. Vì vậy:

~~~sql
SET TIME ZONE 'UTC';

SELECT
    TIMESTAMP '2026-11-14 09:30:00+07' AS local_value,
    TIMESTAMPTZ '2026-11-14 09:30:00+07' AS absolute_value;
~~~

Hai biểu thức **khác nhau**:

| Biểu thức | Ngữ nghĩa |
|---|---|
| `TIMESTAMP '2026-11-14 09:30+07'` | Giá trị timestamp không timezone; offset không làm nó trở thành instant |
| `TIMESTAMPTZ '2026-11-14 09:30+07'` | Instant 02:30 UTC, hiển thị theo TimeZone của session |

Nói cách khác, **viết `+07` trong nội dung không tự chuyển kiểu `TIMESTAMP` thành `TIMESTAMPTZ`**.

### 8.1. Nếu timestamptz input không có offset

~~~sql
SET TIME ZONE 'Asia/Ho_Chi_Minh';

SELECT TIMESTAMPTZ '2026-11-14 09:30:00';
~~~

PostgreSQL diễn giải “09:30” theo **session TimeZone**. Nếu cùng chuỗi được nhập ở session UTC, instant sẽ khác.

Với event thực tế, nên gửi giá trị kèm offset hoặc UTC rõ ràng.

### 8.2. ISO 8601 và JSON API

Những biểu diễn thường dễ hiểu cho instant:

~~~text
2026-11-14T02:30:00Z
2026-11-14T09:30:00+07:00
~~~

Ở ranh giới API, parse về kiểu dữ liệu có ngữ nghĩa instant/offset rồi truyền typed parameter. Tránh bỏ offset trước khi lưu vào database.

## 9. DateStyle: tránh chuỗi ngày mơ hồ

PostgreSQL có tham số:

~~~sql
SHOW DateStyle;
~~~

Một chuỗi như `11/12/2026` có thể bị hiểu là 11 tháng 12 hoặc 12 tháng 11 trong những thiết lập khác nhau.

Ưu tiên ISO:

~~~sql
SELECT DATE '2026-11-14';
SELECT TIMESTAMP '2026-11-14 09:30:00';
SELECT TIMESTAMPTZ '2026-11-14 09:30:00+07';
~~~

Khi ứng dụng dùng JDBC, truyền `LocalDate`, `LocalDateTime` hoặc `OffsetDateTime` như những tham số kiểu đúng sẽ ít mơ hồ hơn việc ghép chuỗi theo locale.

### 9.1. Không lưu thời điểm bằng TEXT chỉ để dễ hiển thị

~~~sql
CREATE TABLE bad_events (
    occurred_at TEXT NOT NULL
);
~~~

Các chuỗi `2026-11-14T09:30:00+07:00` và `2026-11-14T02:30:00Z` biểu diễn cùng instant, nhưng không phải cùng chuỗi.

Nếu ứng dụng cần so sánh, sắp xếp, tính khoảng thời gian và dùng index, kiểu `timestamptz` diễn đạt ý nghĩa tốt hơn. `TEXT` phù hợp khi mục đích thực sự là lưu nguyên đầu vào chưa chuẩn hóa.

## 10. AT TIME ZONE: toán tử hai chiều

Toán tử `AT TIME ZONE` rất quan trọng vì **kiểu đầu vào quyết định kiểu đầu ra**.

| Đầu vào | Phép toán | Đầu ra |
|---|---|---|
| `timestamp without time zone` | `value AT TIME ZONE zone` | `timestamptz` — diễn giải local time thành instant |
| `timestamptz` | `value AT TIME ZONE zone` | `timestamp` — ngày giờ trên đồng hồ tại zone |

### 10.1. Từ ngày giờ Việt Nam sang instant

~~~sql
SET TIME ZONE 'UTC';

SELECT TIMESTAMP '2026-11-14 09:30:00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh'
    AS actual_instant;
~~~

Bước diễn giải:

1. Nhận local timestamp 09:30 ngày 14/11/2026.
2. Áp dụng timezone `Asia/Ho_Chi_Minh`.
3. Đổi thành instant 02:30 UTC.
4. Vì session UTC, kết quả có thể hiển thị 02:30+00.

### 10.2. Từ instant sang giờ địa phương

~~~sql
SELECT
    TIMESTAMPTZ '2026-11-14 02:30:00+00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh'
    AS vietnam_clock;
~~~

Kết quả kiểu timestamp không timezone là `2026-11-14 09:30:00`.

### 10.3. Hiển thị cùng instant ở nhiều quốc gia

~~~sql
SELECT
    TIMESTAMPTZ '2026-11-14 02:30:00+00'
        AT TIME ZONE 'UTC' AS utc_clock,
    TIMESTAMPTZ '2026-11-14 02:30:00+00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh' AS vn_clock,
    TIMESTAMPTZ '2026-11-14 02:30:00+00'
        AT TIME ZONE 'Asia/Tokyo' AS tokyo_clock;
~~~

| UTC | Việt Nam | Tokyo |
|---|---|---|
| 02:30 | 09:30 | 11:30 |

Các kết quả biểu diễn **cùng một sự kiện**.

### 10.4. Phân biệt gắn timezone với hiển thị theo timezone

~~~sql
-- Local wall-clock time -> instant.
SELECT TIMESTAMP '2026-11-14 09:30:00'
       AT TIME ZONE 'Asia/Ho_Chi_Minh';

-- Instant -> local wall-clock time.
SELECT TIMESTAMPTZ '2026-11-14 02:30:00+00'
       AT TIME ZONE 'Asia/Ho_Chi_Minh';
~~~

Hai câu có vẻ gần giống nhau nhưng phép biến đổi đi theo **hai chiều ngược nhau**. Đây là kiến thức cần hiểu qua kiểu dữ liệu, không chỉ học thuộc chuỗi SQL.

## 11. UTC offset khác IANA timezone ID

Offset như `+07:00` chỉ biểu thị độ lệch so với UTC ở một thời điểm. Một IANA timezone ID như `Asia/Ho_Chi_Minh`, `Asia/Tokyo` hoặc `America/New_York` gắn với các quy tắc vùng địa lý theo thời gian.

| Giá trị | Ví dụ | Mang ý nghĩa gì? |
|---|---|---|
| Offset | `+07:00` | Lệch UTC 7 giờ |
| Timezone ID | `America/New_York` | Bộ quy tắc timezone theo lịch |
| Instant | `2026-11-14T02:30:00Z` | Mốc thời gian tuyệt đối |
| Local timestamp | `2026-11-14 09:30` | Thành phần ngày giờ, chưa chỉ rõ instant |

Nếu cần lập lịch mỗi thứ Hai lúc 09:00 ở New York, chỉ lưu offset hiện tại là không đủ cho tương lai vì offset có thể thay đổi theo mùa. Lưu **IANA timezone ID** để áp dụng quy tắc tương ứng từng ngày.

### 11.1. Không phải mọi timezone đều có DST

`Asia/Ho_Chi_Minh` trong giai đoạn hiện đại không thay đổi giờ mùa hè như nhiều vùng Bắc Mỹ. Nhưng ứng dụng toàn cầu không nên coi mọi nơi luôn có cùng offset quanh năm.

## 12. Giờ mùa hè: giờ không tồn tại và giờ trùng

Trong các vùng có daylight saving time (DST), đồng hồ có thể đổi vào một số ngày.

### 12.1. Đồng hồ nhảy tiến

Một khoảng giờ địa phương có thể không tồn tại:

~~~text
01:59:59
03:00:00  <- đồng hồ nhảy tới đây
~~~

Khi đó, một lịch hẹn tại “02:30” trong khoảng bị bỏ qua **không tương ứng với một instant thực sự**.

### 12.2. Đồng hồ quay lùi

Một khoảng như 01:00–01:59 có thể xuất hiện **hai lần** với hai UTC offsets khác nhau. Vì vậy `timestamp '... 01:30'` cộng timezone ID vẫn có thể còn mơ hồ.

### 12.3. Cần chính sách nghiệp vụ

PostgreSQL có quy tắc xử lý local time thiếu/trùng khi chuyển đổi, nhưng ứng dụng lịch hẹn nên quyết định rõ:

- Có từ chối giờ không tồn tại không?
- Có cho chọn giữa lần 01:30 thứ nhất và thứ hai không?
- Có lưu offset khách đã xác nhận không?
- Lịch lặp dùng “giờ địa phương ngày kế tiếp” hay “sau đúng 24 giờ”?

Không nên để một quy tắc chọn mặc định của thư viện/database vô tình quyết định lịch hẹn của khách.

## 13. Các hàm thời điểm hiện tại

PostgreSQL có nhiều hàm tương tự “thời gian hiện tại”, nhưng mốc được dùng có thể khác nhau:

~~~sql
SELECT
    CURRENT_TIMESTAMP AS transaction_time,
    now() AS now_value,
    transaction_timestamp() AS transaction_started_at,
    statement_timestamp() AS statement_started_at,
    clock_timestamp() AS wall_clock_now;
~~~

| Hàm/biểu thức | Mốc |
|---|---|
| `CURRENT_TIMESTAMP` | Đầu transaction |
| `now()` | Tương đương transaction_timestamp |
| `transaction_timestamp()` | Đầu transaction |
| `statement_timestamp()` | Đầu statement |
| `clock_timestamp()` | Đồng hồ thực tại thời điểm gọi |

### 13.1. now() không tiến lên liên tục trong cùng transaction

~~~sql
BEGIN;

SELECT now() AS at_transaction_start;
SELECT pg_sleep(1);
SELECT now() AS same_transaction_time,
       clock_timestamp() AS later_wall_clock;

COMMIT;
~~~

Trong cùng transaction, hai lần `now()` có cùng thời điểm bắt đầu transaction. `clock_timestamp()` có thể khác vì đọc đồng hồ lúc gọi.

`pg_sleep(1)` chỉ dùng để minh họa ở môi trường thử nghiệm, không nên giữ transaction ngủ trên hệ thống đang phục vụ tải thật.

### 13.2. CURRENT_DATE, CURRENT_TIME và LOCALTIME

~~~sql
SELECT
    CURRENT_DATE,
    CURRENT_TIME,
    LOCALTIME,
    LOCALTIMESTAMP;
~~~

- `CURRENT_DATE` trả kiểu `date`.
- `CURRENT_TIME` trả giờ có ngữ nghĩa timezone theo kiểu tương ứng.
- `LOCALTIME` trả giờ địa phương không gắn timezone.
- `LOCALTIMESTAMP` trả ngày giờ địa phương không timezone.

Các giá trị hiện tại này chịu ngữ cảnh transaction và session timezone; đừng hoán đổi chúng chỉ vì khi in ra trông gần giống nhau.

### 13.3. DEFAULT cho audit

~~~sql
CREATE TABLE audit_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_type TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

`created_at` ở đây là thời điểm bắt đầu transaction theo cơ chế của `CURRENT_TIMESTAMP`, **không nhất thiết là thời điểm commit**. Nếu nghiệp vụ yêu cầu thời điểm thực tại lúc thực hiện mỗi bước, cần cân nhắc `statement_timestamp()`, `clock_timestamp()` hoặc nguồn thời gian khác tùy mục tiêu.

## 14. Cộng trừ DATE và TIMESTAMP

### 14.1. DATE cộng số ngày

~~~sql
SELECT
    DATE '2026-11-14' + 7 AS next_week,
    DATE '2026-11-14' - 7 AS previous_week;
~~~

Cộng/trừ số nguyên với `DATE` có thể được dùng để dịch số ngày lịch.

### 14.2. Hiệu hai DATE

~~~sql
SELECT
    DATE '2026-11-14' - DATE '2026-11-01'
    AS days_between;
~~~

Kết quả là `13` ngày. Không dùng phép chia số ngày cho 365 để xác định tuổi chính xác ở mọi trường hợp năm nhuận.

### 14.3. Timestamp cộng duration

~~~sql
SELECT
    TIMESTAMP '2026-11-14 09:30:00'
        + INTERVAL '90 minutes' AS planned_end;

SELECT
    TIMESTAMPTZ '2026-11-14 09:30:00+07'
        + INTERVAL '2 hours' AS instant_end;
~~~

`TIMESTAMP + INTERVAL` vẫn tạo ngày giờ không timezone; `TIMESTAMPTZ + INTERVAL` tạo instant mới.

### 14.4. Hiệu hai instant

~~~sql
SELECT
    TIMESTAMPTZ '2026-11-14 11:00:00+07'
    - TIMESTAMPTZ '2026-11-14 09:30:00+07'
    AS elapsed_time;
~~~

Kết quả là một `INTERVAL` 1 giờ 30 phút. Đây là thời lượng giữa hai sự kiện, khác với một giá trị `TIME` trên đồng hồ.

## 15. INTERVAL và lịch

~~~sql
SELECT
    INTERVAL '3 days' AS three_days,
    INTERVAL '2 hours 15 minutes' AS duration,
    INTERVAL '1 month' AS calendar_month;
~~~

`INTERVAL '1 month'` không phải lúc nào cũng tương đương 30 ngày. Độ dài tháng thay đổi, và phép cộng theo tháng phải theo quy tắc lịch.

### 15.1. Một ngày không luôn bằng 24 giờ ở nơi có DST

~~~sql
SET TIME ZONE 'America/New_York';

SELECT
    TIMESTAMPTZ '2026-03-07 12:00:00-05'
        + INTERVAL '1 day' AS same_clock_next_day,
    TIMESTAMPTZ '2026-03-07 12:00:00-05'
        + INTERVAL '24 hours' AS after_24_hours;
~~~

Khi qua kỳ chuyển giờ mùa hè, hai biểu thức **có thể khác giờ đồng hồ địa phương**:

- `1 day` biểu diễn bước qua một ngày theo lịch địa phương.
- `24 hours` biểu diễn số giờ thực trôi qua.

Nếu cần lịch “12:00 ngày hôm sau” tại địa điểm, phải hiểu quy tắc lịch. Nếu cần timer “sau đúng 24 giờ”, phải dùng thời lượng.

~~~sql
RESET TIME ZONE;
~~~

### 15.2. age() cho chênh lệch theo lịch

~~~sql
SELECT age(
    TIMESTAMP '2026-11-14 09:00:00',
    TIMESTAMP '2025-10-01 09:00:00'
);
~~~

`age()` tạo khoảng thời gian với thành phần tháng/năm theo lịch. Khi cần số giây thực trôi qua, nên làm việc với hai instants và phép trừ tương ứng.

## 16. So sánh thời gian và chuyển kiểu ngầm

### 16.1. So sánh hai instant

~~~sql
SELECT
    TIMESTAMPTZ '2026-11-14 09:00:00+07'
    = TIMESTAMPTZ '2026-11-14 02:00:00+00'
    AS same_instant;
~~~

Kết quả là `true`.

### 16.2. So sánh hai local timestamps

~~~sql
SELECT
    TIMESTAMP '2026-11-14 09:00:00'
    < TIMESTAMP '2026-11-14 10:00:00'
    AS earlier_local;
~~~

Phép so sánh dựa trên thành phần ngày giờ, không tự gắn timezone.

### 16.3. Trộn timestamp và timestamptz

~~~sql
SELECT
    TIMESTAMP '2026-11-14 09:00:00'
    = TIMESTAMPTZ '2026-11-14 09:00:00+07';
~~~

Khi hai kiểu được so sánh, PostgreSQL cần diễn giải giá trị không timezone theo quy tắc của session, nên kết quả có thể phụ thuộc `TimeZone`.

Cách rõ hơn khi biết địa điểm:

~~~sql
SELECT
    (
        TIMESTAMP '2026-11-14 09:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) = TIMESTAMPTZ '2026-11-14 02:00:00+00'
    AS same_instant;
~~~

### 16.4. CAST timestamptz sang date

~~~sql
SET TIME ZONE 'UTC';

SELECT (
    TIMESTAMPTZ '2026-11-14 00:30:00+00'
)::DATE;
~~~

Cùng instant ở một timezone thuộc Mỹ có thể là **ngày 13/11**. Vì thế, cast `timestamptz::date` phụ thuộc TimeZone của session; ngày báo cáo cần được xác định theo timezone nghiệp vụ.

## 17. Truy vấn cả một ngày bằng half-open interval

Nếu muốn lấy mọi sự kiện thuộc một ngày, cách rõ ràng là dùng khoảng:

~~~text
[start_instant, end_instant)
~~~

Tức bao gồm mốc đầu, không bao gồm mốc cuối.

### 17.1. Ví dụ ngày UTC

~~~sql
CREATE TABLE sample_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL
);

SELECT event_id, occurred_at
FROM sample_events
WHERE occurred_at >= TIMESTAMPTZ '2026-11-14 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-11-15 00:00:00+00';
~~~

Mọi instant trong ngày 14/11 theo UTC đều nằm trong khoảng, kể cả các giá trị có phần giây rất nhỏ ở cuối ngày.

### 17.2. Vì sao BETWEEN 00:00 và 23:59:59 có thể thiếu?

~~~sql
-- Không bao phủ mọi microsecond cuối ngày.
SELECT event_id
FROM sample_events
WHERE occurred_at BETWEEN
    TIMESTAMPTZ '2026-11-14 00:00:00+00'
    AND TIMESTAMPTZ '2026-11-14 23:59:59+00';
~~~

`BETWEEN` gồm cả hai đầu mút, nhưng mốc cuối tại 23:59:59 không bao gồm 23:59:59.000001 trở đi. Khoảng half-open tới **00:00 ngày kế tiếp** tránh phụ thuộc precision.

### 17.3. Lọc ngày Việt Nam

~~~sql
SELECT event_id, occurred_at
FROM sample_events
WHERE occurred_at >= (
        TIMESTAMP '2026-11-14 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
      )
  AND occurred_at < (
        TIMESTAMP '2026-11-15 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
      );
~~~

Hai đầu mút được xác định từ **hai mốc nửa đêm địa phương** rồi đổi sang instants. Cách làm này vẫn đúng về mặt nguyên tắc tại các vùng có ngày 23/25 giờ do DST.

### 17.4. Đừng lấy đầu ngày + 24 giờ cho mọi timezone

Một ngày địa phương có DST có thể không dài đúng 24 giờ. Muốn lấy ngày địa phương tiếp theo, hãy tính **ngày tiếp theo trên lịch tại vùng đó** rồi chuyển đầu ngày thành instant tương ứng.

## 18. Index trên cột thời gian

PostgreSQL có thể tạo B-tree index cho `DATE`, `TIME`, `TIMESTAMP` và `TIMESTAMPTZ`.

~~~sql
CREATE INDEX idx_sample_events_occurred_at
ON sample_events (occurred_at);
~~~

Điều kiện range trực tiếp:

~~~sql
SELECT event_id
FROM sample_events
WHERE occurred_at >= TIMESTAMPTZ '2026-11-14 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-11-15 00:00:00+00';
~~~

thường thuận tiện cho planner khi có index trên `occurred_at`.

### 18.1. Cẩn thận với phép chuyển đổi ngay trên cột

~~~sql
SELECT event_id
FROM sample_events
WHERE occurred_at::DATE = DATE '2026-11-14';
~~~

Câu này ép toàn bộ giá trị theo session timezone và làm điều kiện thành biểu thức trên cột. Một index B-tree thông thường trên `occurred_at` không tự động mang lại khả năng sử dụng giống một range condition trực tiếp.

Với bảng lớn, thường nên tính hai instant biên ở phía tham số rồi viết:

~~~sql
WHERE occurred_at >= :start_instant
  AND occurred_at <  :end_instant
~~~

Hai placeholder trên là cách mô tả tham số ứng dụng, không phải SQL có thể chạy nguyên văn trong mọi công cụ truy vấn. Trong JDBC, dùng `?</BT> và bind giá trị typed.

### 18.2. Index không bảo đảm luôn được dùng

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id
FROM sample_events
WHERE occurred_at >= TIMESTAMPTZ '2026-11-14 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-11-15 00:00:00+00';
~~~

Trên bảng rất nhỏ, PostgreSQL có thể chọn sequential scan. `EXPLAIN (ANALYZE)` **thực sự chạy truy vấn**, nên cần cẩn thận với DML trong môi trường thật.

## 19. DATE_TRUNC và EXTRACT

### 19.1. date_trunc

~~~sql
SELECT
    date_trunc(
        'hour',
        TIMESTAMP '2026-11-14 09:42:35.123456'
    ) AS hour_bucket,
    date_trunc(
        'day',
        TIMESTAMP '2026-11-14 09:42:35.123456'
    ) AS day_bucket,
    date_trunc(
        'month',
        TIMESTAMP '2026-11-14 09:42:35.123456'
    ) AS month_bucket;
~~~

Ý nghĩa kết quả:

~~~text
hour_bucket  = 2026-11-14 09:00:00
day_bucket   = 2026-11-14 00:00:00
month_bucket = 2026-11-01 00:00:00
~~~

Với `timestamp` không timezone, đây là các mốc theo thành phần ngày giờ. Với `timestamptz`, việc cắt theo ngày/tháng cần hiểu timezone áp dụng, vì đầu ngày địa phương có thể khác đầu ngày UTC.

### 19.2. EXTRACT

~~~sql
SELECT
    EXTRACT(YEAR FROM DATE '2026-11-14') AS year_num,
    EXTRACT(MONTH FROM DATE '2026-11-14') AS month_num,
    EXTRACT(DAY FROM DATE '2026-11-14') AS day_num,
    EXTRACT(HOUR FROM TIME '09:42:35') AS hour_num,
    EXTRACT(MINUTE FROM TIME '09:42:35') AS minute_num;
~~~

Nếu nhóm theo tháng của nhiều năm, đừng chỉ dùng `EXTRACT(MONTH ...)` vì tháng 11/2025 và tháng 11/2026 có thể bị gộp. Có thể nhóm theo `date_trunc('month', ...)` hoặc đồng thời year + month.

### 19.3. Ngày trong tuần

~~~sql
SELECT
    EXTRACT(DOW FROM DATE '2026-11-14') AS day_of_week,
    EXTRACT(ISODOW FROM DATE '2026-11-14') AS iso_weekday;
~~~

- `DOW`: Chủ nhật thường là 0.
- `ISODOW`: thứ Hai là 1, Chủ nhật là 7.

Nếu mô hình lịch lặp, cần ghi rõ hệ thống dùng quy ước nào.

## 20. GROUP BY theo ngày nghiệp vụ

Giả sử bảng thanh toán:

~~~sql
CREATE TABLE payments (
    payment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    paid_at TIMESTAMPTZ NOT NULL,
    amount NUMERIC(14, 2) NOT NULL
);
~~~

Báo cáo doanh thu theo ngày tại Việt Nam:

~~~sql
SELECT
    (paid_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
        AS business_date,
    COUNT(*) AS payment_count,
    SUM(amount) AS total_amount
FROM payments
GROUP BY
    (paid_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
ORDER BY business_date;
~~~

Các bước:

1. `paid_at` là instant.
2. `AT TIME ZONE</BT> biến nó thành ngày giờ địa phương tại Việt Nam.
3. `::DATE` lấy ngày lịch.
4. `GROUP BY` gom theo ngày nghiệp vụ.

### 20.1. Vì sao GROUP BY paid_at::date dễ sai?

~~~sql
SELECT paid_at::DATE, COUNT(*)
FROM payments
GROUP BY paid_at::DATE;
~~~

Phép cast phụ thuộc session TimeZone. Nếu job báo cáo chạy ở UTC trong khi doanh thu phải tính theo Việt Nam, các giao dịch gần nửa đêm có thể thuộc ngày khác.

### 20.2. Bucket theo tháng địa phương

~~~sql
SELECT
    date_trunc(
        'month',
        paid_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AS local_month,
    COUNT(*) AS payment_count
FROM payments
GROUP BY
    date_trunc(
        'month',
        paid_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
ORDER BY local_month;
~~~

Mốc đầu tháng ở đây là `timestamp without time zone` đại diện cho đồng hồ địa phương. Nếu API cần instant của đầu tháng, phải gắn lại timezone theo quy tắc nghiệp vụ.

## 21. TO_CHAR chỉ là định dạng đầu ra

~~~sql
SELECT
    TO_CHAR(
        TIMESTAMP '2026-11-14 09:30:45',
        'YYYY-MM-DD HH24:MI:SS'
    ) AS formatted_timestamp,
    TO_CHAR(
        DATE '2026-11-14',
        'DD/MM/YYYY'
    ) AS formatted_date;
~~~

Kết quả:

~~~text
2026-11-14 09:30:45
14/11/2026
~~~

`TO_CHAR` trả **văn bản**, không còn là kiểu ngày giờ để tính toán và lập index trực tiếp theo semantics thời gian.

Với ứng dụng nhiều locale, nên lưu giá trị typed trong database rồi định dạng ở tầng trình bày theo ngôn ngữ/ngữ cảnh người dùng.

### 21.1. Khi cần đọc chuỗi thành ngày

PostgreSQL có `TO_DATE`, `TO_TIMESTAMP` và các parser ngày giờ. Nhưng khi có thể, ưu tiên typed parameter để tránh DateStyle hoặc định dạng nhập mơ hồ.

## 22. Tạo giá trị bằng make_date, make_time và make_timestamptz

~~~sql
SELECT make_date(2026, 11, 14) AS d;

SELECT make_time(9, 30, 15.5) AS t;

SELECT make_timestamp(
    2026, 11, 14, 9, 30, 0
) AS local_ts;

SELECT make_timestamptz(
    2026, 11, 14, 9, 30, 0,
    'Asia/Ho_Chi_Minh'
) AS instant;
~~~

Các constructor này hữu ích khi ứng dụng có năm/tháng/ngày/giờ dưới dạng các trường riêng. Tuy nhiên, việc biến local time thành instant tại vùng có DST vẫn cần xử lý chính sách giờ không tồn tại hoặc mơ hồ.

## 23. Giá trị đặc biệt infinity

PostgreSQL hỗ trợ `infinity` và `-infinity` cho một số kiểu như `DATE` và hai loại `TIMESTAMP`:

~~~sql
SELECT
    DATE 'infinity' AS unlimited_end,
    TIMESTAMPTZ '-infinity' AS unlimited_start;
~~~

Có thể kiểm tra:

~~~sql
SELECT
    isfinite(DATE '2026-11-14') AS finite_day,
    isfinite(DATE 'infinity') AS infinite_day;
~~~

Những giá trị đặc biệt này hữu ích trong một số mô hình khoảng hiệu lực mở, nhưng **không phải driver, JSON serializer hoặc BI tool nào cũng biểu diễn chúng giống nhau**.

Đừng dùng `infinity` để thay `NULL` nếu chưa xác định rõ semantics và khả năng tích hợp. “Chưa biết ngày kết thúc” và “không bao giờ kết thúc” có thể là hai trạng thái nghiệp vụ khác nhau.

## 24. Lab: tạo bảng cho bốn kiểu thời gian

Thực hành dưới đây dành cho **database PostgreSQL thử nghiệm** có quyền tạo schema. Không chạy trên production. Nếu schema `temporal_lab` đã tồn tại, chọn tên khác hoặc database lab mới để tránh xung đột.

### 24.1. Tạo schema và bảng

~~~sql
CREATE SCHEMA temporal_lab;

CREATE TABLE temporal_lab.time_examples (
    example_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    business_day DATE NOT NULL,
    opening_time TIME(0) NOT NULL,
    local_start TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
    occurred_at TIMESTAMP(0) WITH TIME ZONE NOT NULL,
    timezone_name TEXT NOT NULL
);
~~~

### 24.2. Chèn giá trị

~~~sql
INSERT INTO temporal_lab.time_examples (
    business_day,
    opening_time,
    local_start,
    occurred_at,
    timezone_name
)
VALUES (
    DATE '2026-11-14',
    TIME '09:00:00',
    TIMESTAMP '2026-11-14 09:30:00',
    TIMESTAMPTZ '2026-11-14 09:30:00+07',
    'Asia/Ho_Chi_Minh'
);
~~~

Trong hàng vừa tạo:

- `business_day` là nhãn ngày lịch.
- `opening_time` là giờ trong ngày.
- `local_start` là wall-clock time chưa tự gắn timezone.
- `occurred_at` là instant tương ứng.
- `timezone_name` lưu tên vùng liên quan.

### 24.3. Xem khi session là UTC

~~~sql
SET TIME ZONE 'UTC';

SELECT
    business_day,
    opening_time,
    local_start,
    occurred_at,
    occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        AS local_from_instant
FROM temporal_lab.time_examples;
~~~

Dự kiến:

- `business_day` vẫn là 14/11/2026.
- `opening_time` vẫn là 09:00.
- `local_start` vẫn là 09:30.
- `occurred_at` hiển thị 02:30+00.
- `local_from_instant` trả 09:30.

### 24.4. Đổi session timezone

~~~sql
SET TIME ZONE 'Asia/Tokyo';

SELECT occurred_at
FROM temporal_lab.time_examples;

RESET TIME ZONE;
~~~

Instant không đổi, nhưng cách hiển thị theo Tokyo tương đương 11:30+09.

## 25. Lab: lịch hẹn có timezone địa điểm

~~~sql
CREATE TABLE temporal_lab.appointments (
    appointment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_code TEXT NOT NULL,
    local_start TIMESTAMP NOT NULL,
    timezone_name TEXT NOT NULL,
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_appointment_duration
        CHECK (ends_at > starts_at),
    CONSTRAINT chk_appointment_zone_nonempty
        CHECK (btrim(timezone_name) <> '')
);
~~~

Thêm lịch hẹn:

~~~sql
INSERT INTO temporal_lab.appointments (
    customer_code,
    local_start,
    timezone_name,
    starts_at,
    ends_at
)
VALUES (
    'CUST-001',
    TIMESTAMP '2026-11-14 09:30:00',
    'Asia/Ho_Chi_Minh',
    TIMESTAMP '2026-11-14 09:30:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh',
    TIMESTAMP '2026-11-14 10:30:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
);
~~~

### 25.1. Vì sao lưu cả local và instant?

Nếu nghiệp vụ cần giữ đúng lựa chọn ban đầu của khách **09:30 tại Việt Nam**, `local_start + timezone_name` ghi lại quy tắc đó. `starts_at` cho phép truy vấn và nhắc lịch theo instant.

Đây là **dữ liệu dư thừa có chủ đích**; nếu ứng dụng cho sửa giờ hoặc timezone, cần cập nhật instant tương ứng. Một hệ thống khác có thể chọn lưu chỉ instant + timezone nếu các yêu cầu thay đổi lịch cho phép. Không có mô hình duy nhất đúng cho mọi tình huống.

### 25.2. CHECK chuỗi không rỗng không xác nhận timezone hợp lệ

`CHECK (btrim(timezone_name) <> '')` chỉ chặn chuỗi trống. Nó không chứng minh chuỗi là IANA timezone ID tồn tại.

Có thể tham khảo danh sách timezone mà server hỗ trợ:

~~~sql
SELECT name, utc_offset, is_dst
FROM pg_timezone_names
WHERE name LIKE 'Asia/%'
ORDER BY name
LIMIT 20;
~~~

Thông tin offset/DST được trình bày tại thời điểm quan sát; để xác định lịch tương lai phải áp dụng quy tắc timezone cho **ngày cụ thể**. Một ứng dụng nên validate timezone ID ở đầu vào và có chính sách khi timezone database được cập nhật.

### 25.3. Lọc lịch hẹn ngày Việt Nam

~~~sql
CREATE INDEX idx_appointments_starts_at
ON temporal_lab.appointments (starts_at);

SELECT
    appointment_id,
    customer_code,
    starts_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        AS local_start_display
FROM temporal_lab.appointments
WHERE starts_at >= (
        TIMESTAMP '2026-11-14 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
      )
  AND starts_at < (
        TIMESTAMP '2026-11-15 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
      )
ORDER BY starts_at;
~~~

Đây là cách lọc đúng ngày địa phương thông qua hai instant biên, phù hợp với index trên cột `starts_at` khi optimizer thấy hiệu quả.

## 26. Java/JDBC: ánh xạ kiểu dữ liệu

Các kiểu `java.time` thể hiện semantics tốt hơn việc dùng một lớp thời gian cho mọi cột.

| PostgreSQL | Java phù hợp | Ý nghĩa |
|---|---|---|
| `DATE` | `LocalDate` | Ngày lịch |
| `TIME WITHOUT TIME ZONE` | `LocalTime` | Giờ trên đồng hồ |
| `TIMESTAMP WITHOUT TIME ZONE` | `LocalDateTime` | Local date-time |
| `TIMESTAMP WITH TIME ZONE` | `OffsetDateTime` qua pgJDBC, có thể chuyển thành `Instant` | Instant |

### 26.1. Đọc từ ResultSet

~~~java
import java.sql.ResultSet;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.OffsetDateTime;

// rs là ResultSet đã có hàng hiện tại.
LocalDate day = rs.getObject("business_day", LocalDate.class);
LocalTime opening = rs.getObject("opening_time", LocalTime.class);
LocalDateTime localStart =
        rs.getObject("local_start", LocalDateTime.class);
OffsetDateTime occurred =
        rs.getObject("occurred_at", OffsetDateTime.class);

Instant instant = occurred.toInstant();
~~~

Với pgJDBC phù hợp, đọc timestamptz bằng `OffsetDateTime` thường trả offset UTC. Driver không có cách khôi phục offset/timezone gốc từ một cột timestamptz vốn chỉ chứa instant.

### 26.2. Ghi bằng PreparedStatement

~~~java
import java.sql.PreparedStatement;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

PreparedStatement ps = connection.prepareStatement("""
    INSERT INTO temporal_lab.time_examples
      (business_day, opening_time, local_start, occurred_at, timezone_name)
    VALUES (?, ?, ?, ?, ?)
    """);

ps.setObject(1, LocalDate.of(2026, 11, 14));
ps.setObject(2, LocalTime.of(9, 0));
ps.setObject(3, LocalDateTime.of(2026, 11, 14, 9, 30));
ps.setObject(
    4,
    OffsetDateTime.of(
        2026, 11, 14, 9, 30, 0, 0,
        ZoneOffset.ofHours(7)
    )
);
ps.setString(5, "Asia/Ho_Chi_Minh");
ps.executeUpdate();
~~~

Ví dụ giả định `connection` đã mở và driver PostgreSQL JDBC hiện đại có trong classpath. Trong code ứng dụng thật, đóng `PreparedStatement` bằng try-with-resources và quản lý transaction phù hợp.

### 26.3. LocalDateTime không có instant

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.Instant;

LocalDateTime local =
        LocalDateTime.of(2026, 11, 14, 9, 30);

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
Instant instant = local.atZone(zone).toInstant();
~~~

`LocalDateTime` tự nó không mang timezone. Khi đổi sang `Instant` phải chọn một `ZoneId` hoặc offset; nếu vùng có DST thì cần kiểm soát các trường hợp giờ không tồn tại/trùng.

### 26.4. Legacy java.sql.Timestamp

`java.sql.Timestamp` vẫn tồn tại và được nhiều framework sử dụng. Nhưng khi thiết kế API mới, các kiểu `java.time` giúp diễn đạt “local date-time” và “instant” rõ ràng hơn. Phải kiểm tra cách driver và framework xử lý timezone khi đọc/ghi, không chỉ nhìn kiểu Java.

## 27. Migration từ timestamp sang timestamptz

Một hệ thống legacy có thể dùng:

~~~sql
created_at TIMESTAMP WITHOUT TIME ZONE
~~~

trong khi ứng dụng thực tế luôn ghi **giờ Việt Nam**. Khi chuyển sang instant, cần gắn timezone nguồn đúng.

### 27.1. Chuyển kiểu có USING rõ ràng

Nếu đã xác nhận mọi hàng là local timestamp của Việt Nam:

~~~sql
ALTER TABLE legacy_events
ALTER COLUMN created_at TYPE TIMESTAMPTZ
USING created_at AT TIME ZONE 'Asia/Ho_Chi_Minh';
~~~

Đây là ví dụ migration, không chạy nếu bảng không tồn tại hoặc chưa xác minh dữ liệu.

Nếu dữ liệu legacy được ghi dưới dạng **UTC nhưng không có timezone**, cần dùng `AT TIME ZONE 'UTC'`, không tự mặc định là Việt Nam.

### 27.2. Không thể phục hồi timezone đã mất bằng phép cast

Giả sử hai hàng legacy:

~~~text
2026-11-14 09:30 (giờ Việt Nam)
2026-11-14 09:30 (giờ Tokyo)
~~~

Nếu không có trường chỉ địa điểm/nguồn, hai hàng có cùng giá trị timestamp nhưng tương ứng hai instants khác nhau. PostgreSQL **không thể tự đoán** timezone đã mất.

Cần kiểm kê nguồn dữ liệu, phân loại theo tenant/địa điểm khi có, giải quyết các hàng mơ hồ và thống nhất chính sách trước migration.

### 27.3. DDL có thể đắt

`ALTER COLUMN TYPE` có thể liên quan tới rewrite, lock và cập nhật index tùy trường hợp. Với bảng lớn, cần kế hoạch triển khai, backup, kiểm thử, đánh giá downtime và rollback.

### 27.4. Thay đổi API và báo cáo

Sau migration, cần rà soát:

- JDBC/ORM mapping.
- JSON serialization và dữ liệu từ ứng dụng cũ.
- Điều kiện lọc ngày theo timezone.
- Các báo cáo `GROUP BY</BT>.
- View, function, trigger phụ thuộc.
- Index và biểu thức cast.
- Cách người dùng nhập/hiển thị lịch hẹn.
- Dữ liệu test quanh nửa đêm và DST.

Migration thành công về DDL không có nghĩa các báo cáo đã đúng ngày nghiệp vụ.

## 28. Các hiểu lầm phổ biến

### 28.1. “TIMESTAMP tự hiểu là giờ server”

Sai. Nó không mang timezone; phép ép sang timestamptz mới phải diễn giải theo ngữ cảnh.

### 28.2. “TIMESTAMPTZ giữ tên Asia/Ho_Chi_Minh”

Sai. Nó giữ instant. Nếu cần timezone ID, lưu riêng.

### 28.3. “Chỉ cần viết +07 trong TIMESTAMP literal”

Sai. `TIMESTAMP` vẫn là timestamp không timezone; hãy chỉ rõ `TIMESTAMPTZ` khi muốn instant.

### 28.4. “Mọi dữ liệu thời gian nên dùng TIMESTAMPTZ”

Không. Ngày sinh cần `DATE`, giờ mở cửa có thể là `TIME`, lịch dự kiến có thể dùng `TIMESTAMP` cùng timezone ID.

### 28.5. “TIME là thời lượng”

Không. `TIME` là giờ đồng hồ; duration là `INTERVAL` hoặc đại lượng có đơn vị khác.

### 28.6. “Mọi ngày địa phương dài 24 giờ”

Không đúng ở nơi có DST. Dùng biên ngày địa phương chuyển riêng thành instants.

### 28.7. “BETWEEN đầu ngày và 23:59:59 đủ mọi event”

Không bao phủ các microsecond sau 23:59:59. Dùng half-open interval tới đầu ngày tiếp theo.

### 28.8. “occurred_at::date là ngày nghiệp vụ ở mọi môi trường”

Không. Cast phụ thuộc TimeZone của session. Gắn timezone nghiệp vụ rõ ràng.

### 28.9. “1 day luôn bằng 24 hours”

Không khi tính theo lịch địa phương có DST. Phân biệt ngày lịch với khoảng giờ tuyệt đối.

### 28.10. “now() đổi mỗi lần gọi trong transaction”

Không. `now()` gắn với transaction start; `clock_timestamp()` đọc đồng hồ thực.

### 28.11. “Có index là mọi query thời gian tự nhanh”

Không. Planner chọn kế hoạch theo thống kê/chi phí; điều kiện expression trên cột có thể không tận dụng index đơn giản như range predicate.

### 28.12. “Đổi kiểu timestamp sang timestamptz khôi phục timezone cũ”

Không. Nếu dữ liệu cũ không có ngữ cảnh timezone, thông tin đó đã bị mất.

### 28.13. “Timezone session luôn là timezone người dùng web”

Không. Nó là cấu hình kết nối PostgreSQL; ứng dụng phải kiểm soát hoặc dùng timezone rõ trong SQL.

## 29. Quy trình thiết kế cột thời gian

Trước khi thêm cột mới, hãy trả lời:

1. Giá trị là date-only, time-only, local date-time hay instant?
2. Nếu là local date-time, nó thuộc timezone nào?
3. Nếu cần lịch lặp, có DST, ngày nghỉ hoặc ca qua nửa đêm không?
4. Nếu là instant, hệ thống đầu vào có truyền UTC/offset rõ không?
5. Có cần giữ offset/timezone người dùng đã chọn không?
6. Precision cần đến giây, millisecond hay microsecond?
7. Thời điểm mặc định nên là transaction start hay thời gian thực tại lúc gọi?
8. Báo cáo theo ngày ở timezone nào?
9. Truy vấn quan trọng có dùng range predicate và index không?
10. Có cần constraint như `ends_at > starts_at`?
11. Có dữ liệu legacy cần phân loại timezone không?
12. Driver, API, BI và hệ thống ngoài có hỗ trợ biểu diễn đặc biệt không?
13. Có test quanh cuối tháng, năm nhuận, nửa đêm và DST không?

## 30. Bài tập thực hành

### Bài 1 — Ngày sinh

Lưu ngày sinh `1995-11-14` bằng kiểu nào? Vì sao không nên dùng timestamptz?

**Gợi ý:** `DATE`, vì ngày sinh không phải instant và không được đổi theo timezone người xem.

### Bài 2 — Giờ mở cửa

Chi nhánh mở 09:00 hằng thứ Hai. Chọn `TIME` hay `TIMESTAMPTZ`?

**Gợi ý:** `TIME` cùng thứ trong tuần và timezone của chi nhánh.

### Bài 3 — TIMESTAMP có offset

Dự đoán khác biệt giữa:

~~~sql
SELECT
    TIMESTAMP '2026-11-14 09:30+07',
    TIMESTAMPTZ '2026-11-14 09:30+07';
~~~

**Gợi ý:** Biểu thức đầu không mang instant; biểu thức thứ hai tương ứng 02:30 UTC.

### Bài 4 — Giờ Việt Nam sang UTC instant

~~~sql
SELECT TIMESTAMP '2026-11-14 09:30'
       AT TIME ZONE 'Asia/Ho_Chi_Minh';
~~~

Hãy giải thích kiểu và ý nghĩa kết quả.

**Gợi ý:** Kết quả là `timestamptz`, một instant.

### Bài 5 — Instant sang local timestamp

~~~sql
SELECT TIMESTAMPTZ '2026-11-14 02:30+00'
       AT TIME ZONE 'Asia/Ho_Chi_Minh';
~~~

**Gợi ý:** Kết quả là local timestamp 09:30 không kèm timezone.

### Bài 6 — Tính ngày doanh thu Việt Nam

Một giao dịch ở `2026-11-14 00:30 UTC`. Viết biểu thức lấy đúng ngày theo giờ Việt Nam.

**Đáp án gợi ý:**

~~~sql
SELECT (
    TIMESTAMPTZ '2026-11-14 00:30+00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh'
)::DATE;
~~~

### Bài 7 — Lọc ngày trọn vẹn

Viết điều kiện lấy mọi event trong ngày 14/11/2026 UTC, kể cả giá trị cuối ngày có microsecond.

~~~sql
WHERE occurred_at >= TIMESTAMPTZ '2026-11-14 00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-11-15 00:00+00'
~~~

### Bài 8 — Một ngày lịch và 24 giờ

Vì sao `INTERVAL '1 day'` và `INTERVAL '24 hours'` có thể khác nhau ở New York khi đổi DST?

**Gợi ý:** Ngày địa phương có thể dài 23 hoặc 25 giờ, còn 24 hours là thời lượng tuyệt đối.

### Bài 9 — now() trong transaction

Nếu transaction kéo dài 10 giây, hai lần gọi `now()` có khác nhau không? Cần hàm nào để đọc đồng hồ lúc gọi?

**Gợi ý:** Cùng transaction start; dùng `clock_timestamp()`.

### Bài 10 — Migration

Cột `created_at TIMESTAMP` chứa giờ Việt Nam. Điền phần `USING` để chuyển sang timestamptz.

~~~sql
USING created_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
~~~

Chỉ dùng khi dữ liệu đã được xác minh có cùng timezone nguồn.

### Bài 11 — Local time bị trùng

Lịch hẹn 01:30 tại vùng có DST vào ngày quay lùi có thể tương ứng bao nhiêu instant?

**Gợi ý:** Có thể hai; cần chính sách chọn offset/lần xuất hiện cụ thể.

### Bài 12 — Java mapping

Ghép `DATE`, `TIME`, `TIMESTAMP`, `TIMESTAMPTZ` với `LocalDate`, `LocalTime`, `LocalDateTime`, `OffsetDateTime`.

**Gợi ý:** Theo ngữ nghĩa ngày, giờ, local date-time và instant.

### Bài 13 — Duration

Tính khoảng thời gian giữa 09:30+07 và 11:00+07 cùng ngày:

~~~sql
SELECT
    TIMESTAMPTZ '2026-11-14 11:00+07'
    - TIMESTAMPTZ '2026-11-14 09:30+07';
~~~

**Gợi ý:** Kết quả là interval 1 giờ 30 phút.

### Bài 14 — Index

Vì sao range predicate trên `occurred_at` thường phù hợp với index B-tree hơn điều kiện `occurred_at::date = ...`?

**Gợi ý:** Điều kiện đầu so sánh trực tiếp giá trị cột; điều kiện thứ hai áp dụng phép biến đổi theo session timezone.

### Bài 15 — Hai mô hình khác nhau

Thiết kế lịch “09:00 thứ Hai tại New York” và log “sự kiện diễn ra lúc 14:00 UTC” có thể dùng cùng một cột `TIME` không?

**Gợi ý:** Không; lịch lặp cần giờ địa phương + timezone + quy tắc tuần, còn event log cần instant.

## 31. Bảng ghi nhớ nhanh

| Câu hỏi | Đáp án |
|---|---|
| Ngày sinh? | `DATE` |
| Giờ mở cửa hằng ngày? | `TIME` |
| Ngày giờ địa phương dự kiến? | `TIMESTAMP` cùng timezone ID khi cần |
| Sự kiện đã diễn ra lúc nào? | `TIMESTAMPTZ` |
| TIMESTAMP mặc định có timezone? | Không |
| Timestamptz giữ timezone gốc? | Không |
| Timestamptz hiển thị theo session TimeZone? | Có |
| Local timestamp sang instant? | `timestamp AT TIME ZONE zone` |
| Instant sang giờ địa phương? | `timestamptz AT TIME ZONE zone` |
| Duration? | `INTERVAL` hoặc hiệu hai instants |
| Ngày địa phương luôn 24 giờ? | Không khi có DST |
| Lọc trọn ngày? | Khoảng half-open `[start, next_start)` |
| Ngày báo cáo Việt Nam? | `(instant AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE` |
| now() là thời điểm nào? | Bắt đầu transaction |
| Đồng hồ thực lúc gọi? | `clock_timestamp()` |
| Java type cho DATE? | `LocalDate` |
| Java type cho TIME? | `LocalTime` |
| Java type cho TIMESTAMP? | `LocalDateTime` |
| Java type cho TIMESTAMPTZ? | `OffsetDateTime` qua pgJDBC |
| Legacy timestamp cần chuyển kiểu? | Xác định timezone nguồn và dùng `AT TIME ZONE` |
| Có thể suy ra timezone đã mất? | Không nếu thiếu dữ liệu nguồn |

---

## Kết luận

**`DATE`**, **`TIME`**, **`TIMESTAMP WITHOUT TIME ZONE`** và **`TIMESTAMP WITH TIME ZONE`** không phải bốn cách ghi khác nhau của cùng một giá trị. Chúng biểu diễn **ngày lịch**, **giờ đồng hồ**, **ngày giờ địa phương** và **thời điểm tuyệt đối**. Chọn đúng kiểu là quyết định về nghiệp vụ và tính chính xác của dữ liệu, không đơn thuần là chi tiết cú pháp.

Điểm quan trọng nhất: `timestamptz` quản lý instant nhưng **không giữ timezone gốc**; session `TimeZone` ảnh hưởng cách hiển thị và một số phép cast. `AT TIME ZONE` giúp chuyển hai chiều giữa local timestamp và instant, nhưng những lịch hẹn ở vùng có DST còn cần chính sách cho giờ không tồn tại hoặc bị trùng. Khi lọc theo ngày địa phương, nên tính hai biên tại timezone nghiệp vụ rồi dùng khoảng half-open để không bỏ sót phần giây và tận dụng index phù hợp.

Khi mô hình lưu trữ, truy vấn, API và Java/JDBC cùng sử dụng **đúng ngữ nghĩa ngày giờ**, PostgreSQL có thể xử lý dữ liệu thời gian một cách đáng tin cậy ngay cả khi ứng dụng mở rộng qua nhiều khu vực, nhiều múi giờ và nhiều hệ thống liên quan.

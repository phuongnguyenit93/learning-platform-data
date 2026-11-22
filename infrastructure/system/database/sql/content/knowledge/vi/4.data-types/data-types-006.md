# Ngày, giờ, dấu thời gian và khoảng thời gian trong SQL

Cơ sở dữ liệu thường cần lưu ngày sinh, ngày thanh toán, giờ mở cửa, thời điểm khách hàng đặt hàng, hạn xử lý, thời lượng cuộc họp hoặc khoảng cách giữa hai sự kiện. Các giá trị này đều liên quan đến thời gian nhưng **không có cùng ý nghĩa**. Việc chọn sai kiểu dữ liệu có thể dẫn đến kết quả lọc sai ngày, tính thiếu giờ hoặc hiển thị lệch múi giờ.

Bài học này phân biệt bốn nhóm dữ liệu thời gian: **ngày (DATE)**, **giờ (TIME)**, **dấu thời gian (TIMESTAMP/DATETIME)** và **khoảng thời gian (INTERVAL/duration)**. Ví dụ thực hành sử dụng **PostgreSQL**; các phần đối chiếu nêu những điểm cần chú ý khi chuyển sang MySQL, SQL Server và SQLite.

## 1. Bốn câu hỏi cần trả lời trước khi chọn kiểu dữ liệu

| Thông tin cần lưu | Câu hỏi mà giá trị trả lời | Ví dụ | Kiểu thường phù hợp |
|---|---|---|---|
| Ngày sinh, ngày nghỉ lễ | **Ngày nào** trên lịch? | `2026-11-14` | `DATE` |
| Giờ cửa hàng bắt đầu phục vụ | **Mấy giờ** trong ngày? | `09:30:00` | `TIME` |
| Thời điểm một giao dịch xảy ra | **Sự kiện diễn ra khi nào** trên dòng thời gian? | `2026-11-14T09:30:00+07:00` | Kiểu timestamp có ý thức về múi giờ, tùy DBMS |
| Thời lượng cuộc họp | **Kéo dài bao lâu**? | 1 giờ 45 phút | `INTERVAL` hoặc số lượng đơn vị thời gian thích hợp |

Điểm quan trọng nhất là phân biệt:

- **Ngày/giờ trên lịch địa phương (civil time):** Ví dụ “họp lúc 09:00 ngày 14/11 tại Hà Nội”. Dữ liệu này mô tả cách con người đọc đồng hồ và lịch ở một địa phương.
- **Thời điểm tuyệt đối (instant):** Ví dụ “hệ thống nhận đơn lúc 02:00 UTC”. Sự kiện đó có thể được hiển thị thành 09:00 ở Việt Nam nhưng vẫn là **cùng một thời điểm**.
- **Thời lượng (duration):** Ví dụ “90 phút”, khác với một ngày/tháng trên lịch. Đặc biệt, “1 tháng” không luôn bằng “30 ngày”, và ngày địa phương không phải lúc nào cũng dài đúng 24 giờ tại nơi có đổi giờ mùa hè.

Hãy lựa chọn kiểu theo **ngữ nghĩa nghiệp vụ**, thay vì chỉ theo hình dạng chuỗi nhập từ giao diện.

## 2. Biểu diễn ngày giờ trong SQL

### 2.1. Chuẩn hóa định dạng để tránh nhập nhằng

Dạng quen thuộc, dễ trao đổi giữa hệ thống là:

| Giá trị | Dạng nên ưu tiên | Ví dụ |
|---|---|---|
| Ngày | `YYYY-MM-DD` | `2026-11-14` |
| Giờ | `HH:MM:SS` | `09:30:00` |
| Ngày + giờ | `YYYY-MM-DD HH:MM:SS` | `2026-11-14 09:30:00` |
| Ngày + giờ + độ lệch UTC | ISO 8601 với `Z` hoặc `±HH:MM` | `2026-11-14T09:30:00+07:00` |
| Giờ có phần lẻ giây | `HH:MM:SS.fff` | `09:30:00.125` |

Dạng `14/11/2026` dễ hiểu với người Việt nhưng có thể bị hiểu sai bởi máy hoặc ứng dụng dùng quy ước tháng/ngày/năm. Khi gửi dữ liệu đến DBMS, nên dùng **tham số truy vấn có kiểu dữ liệu phù hợp**; với ví dụ SQL viết tay, ưu tiên định dạng `YYYY-MM-DD`.

Trong PostgreSQL, có thể tạo giá trị bằng literal có chỉ rõ kiểu:

```sql
SELECT
    DATE '2026-11-14' AS event_date,
    TIME '09:30:00' AS local_time,
    TIMESTAMP '2026-11-14 09:30:00' AS local_datetime,
    TIMESTAMPTZ '2026-11-14 09:30:00+07' AS event_instant;
```

`DATE`, `TIME`, `TIMESTAMP` và `TIMESTAMPTZ` có vai trò khác nhau. Đặc biệt, `TIMESTAMPTZ` là tên viết tắt của `TIMESTAMP WITH TIME ZONE` trong PostgreSQL; khả năng dùng cú pháp này ở DBMS khác cần kiểm tra riêng.

### 2.2. Giá trị ngày giờ vẫn phải hợp lệ

Một ngày có thể được biểu diễn giống một chuỗi văn bản, nhưng kiểu `DATE` không chấp nhận mọi chuỗi:

```sql
SELECT DATE '2024-02-29'; -- Năm nhuận: hợp lệ.
```

```sql
-- Ví dụ không hợp lệ: năm 2025 không có ngày 29 tháng 2.
SELECT DATE '2025-02-29';
```

Khi một ngày không hợp lệ, DBMS thường báo lỗi thay vì lưu vào cột ngày đúng kiểu. Việc dùng cột văn bản như `VARCHAR` có thể làm mất các kiểm tra giá trị và chức năng tính toán ngày giờ, vì vậy không nên lưu thời điểm dưới dạng chuỗi chỉ để dễ hiển thị.

## 3. DATE: ngày trên lịch, không chứa giờ

Kiểu `DATE` biểu diễn **một ngày theo lịch** mà không mang thông tin giờ, phút, giây hay múi giờ riêng. Một số tình huống phù hợp:

- Ngày sinh và ngày kỷ niệm.
- Ngày bắt đầu một học kỳ.
- Ngày nghỉ lễ theo một vùng hoặc quốc gia đã xác định.
- “Ngày thanh toán” theo chính sách nghiệp vụ, khi không cần lưu chính xác giây thực hiện.

Ví dụ bảng ngày nghỉ:

```sql
CREATE TABLE holidays (
    holiday_date DATE PRIMARY KEY,
    holiday_name VARCHAR(100) NOT NULL
);

INSERT INTO holidays (holiday_date, holiday_name)
VALUES (DATE '2026-11-14', 'Ngày thực hành SQL');

SELECT holiday_date, holiday_name
FROM holidays
WHERE holiday_date = DATE '2026-11-14';
```

Khi ghi `DATE '2026-11-14'`, ta không nói “đúng 00:00 UTC”, mà đang biểu diễn **ngày 14/11/2026 trên lịch**. Nếu cần biểu diễn thời điểm ngày đó bắt đầu tại một địa phương, phải biết thêm **múi giờ của địa phương**.

### 3.1. Tính toán với ngày

Trong PostgreSQL:

```sql
SELECT
    DATE '2026-11-14' + 7 AS seven_days_later,
    DATE '2026-11-21' - DATE '2026-11-14' AS day_difference;
```

Phép cộng số nguyên vào `DATE` của PostgreSQL dịch ngày tương ứng số ngày; phép trừ hai giá trị `DATE` trả số ngày chênh lệch. Đối với “cộng một tháng”, không nên thay bằng cộng cố định 30 ngày vì các tháng có độ dài khác nhau.

## 4. TIME: thời gian trong ngày, không gắn một ngày cụ thể

`TIME WITHOUT TIME ZONE`, thường viết `TIME`, mô tả **giờ, phút, giây trong một ngày**:

```sql
SELECT
    TIME '08:00:00' AS opening_time,
    TIME '17:30:00' AS closing_time;
```

Ví dụ giờ làm việc theo ngày trong tuần:

```sql
CREATE TABLE office_hours (
    weekday_number SMALLINT PRIMARY KEY
        CHECK (weekday_number BETWEEN 1 AND 7),
    opens_at TIME NOT NULL,
    closes_at TIME NOT NULL,
    CHECK (closes_at > opens_at)
);

INSERT INTO office_hours (weekday_number, opens_at, closes_at)
VALUES
    (1, TIME '08:00:00', TIME '17:30:00'),
    (2, TIME '08:00:00', TIME '17:30:00');
```

Giả định trong ví dụ: số `1` là thứ Hai, số `7` là Chủ nhật. Bảng áp dụng cho ca làm việc **kết thúc trong cùng ngày**; `CHECK (closes_at > opens_at)` không phù hợp cho ca qua nửa đêm, chẳng hạn 22:00 đến 06:00 hôm sau. Với ca qua ngày, cần biểu diễn ngày kết thúc hoặc quy tắc kéo dài sang ngày tiếp theo.

**Không dùng riêng `TIME` để lưu thời điểm chính xác một sự kiện**, vì `09:30` không cho biết là ngày nào và địa phương nào. Một số DBMS có kiểu `TIME WITH TIME ZONE`, nhưng thiếu ngày khiến việc áp dụng quy tắc thay đổi múi giờ theo mùa khó xác định; vì thế nó không thay thế tốt cho kiểu lưu một sự kiện thực tế.

**Lưu ý MySQL:** kiểu `TIME` của MySQL còn có thể lưu giá trị khoảng thời gian và giá trị âm, ngoài giờ trên đồng hồ 24 giờ; hành vi này khác với trực giác về `TIME` trong PostgreSQL. Hãy đọc ngữ nghĩa kiểu dữ liệu của đúng DBMS trước khi dùng `TIME` làm duration.

## 5. TIMESTAMP/DATETIME: kết hợp ngày và giờ

Một giá trị `2026-11-14 09:30:00` vừa có ngày vừa có giờ. Tuy nhiên, phải phân biệt **thời gian địa phương chưa gắn múi giờ** và **thời điểm có thể quy đổi giữa các múi giờ**.

### 5.1. TIMESTAMP WITHOUT TIME ZONE

Trong PostgreSQL, `TIMESTAMP` không kèm `WITH TIME ZONE` thường được hiểu là `TIMESTAMP WITHOUT TIME ZONE`:

```sql
SELECT TIMESTAMP '2026-11-14 09:30:00' AS appointment_wall_time;
```

Giá trị này chứa năm, tháng, ngày, giờ, phút, giây, nhưng **không chỉ rõ địa phương hay độ lệch UTC**. Nó thích hợp khi hệ thống cần lưu “09:30 theo đồng hồ địa phương” cùng một trường khác mô tả địa phương hoặc múi giờ, hoặc khi toàn bộ ngữ cảnh đã xác định rõ khu vực.

Ví dụ, lịch học “mọi thứ Hai lúc 09:00 tại `Asia/Ho_Chi_Minh`” là một quy tắc thời gian địa phương. Nếu chỉ lưu một `TIMESTAMP` thì chưa đủ để biểu diễn toàn bộ quy tắc lặp và khu vực; thường cần thêm tên múi giờ và quy tắc lặp.

Trong PostgreSQL, đừng cho rằng chuỗi chứa `+07` sẽ khiến kiểu `TIMESTAMP WITHOUT TIME ZONE` tự trở thành có múi giờ:

```sql
-- PostgreSQL: kiểu literal đã được xác định là TIMESTAMP không múi giờ.
-- Phần độ lệch +07 trong nội dung nhập không làm đổi kiểu kết quả.
SELECT TIMESTAMP '2026-11-14 09:30:00+07';
```

Muốn lưu một instant, phải chọn đúng **kiểu dữ liệu và cách chuyển đổi**.

### 5.2. TIMESTAMP WITH TIME ZONE / TIMESTAMPTZ

Trong PostgreSQL, `TIMESTAMPTZ` thể hiện **một thời điểm có thể đối chiếu trên dòng thời gian chung**:

```sql
SELECT
    TIMESTAMPTZ '2026-11-14 09:30:00+07' AS vietnam_time,
    TIMESTAMPTZ '2026-11-14 02:30:00+00' AS utc_time;
```

Hai giá trị trong ví dụ đại diện cho **cùng một instant**: 09:30 ở UTC+07 bằng 02:30 ở UTC.

PostgreSQL chuẩn hóa giá trị `TIMESTAMPTZ` theo dòng thời gian và hiển thị theo **múi giờ của phiên làm việc**. Nó **không lưu nguyên văn tên múi giờ/độ lệch ban đầu** bên trong giá trị. Vì vậy, có thể thấy cách hiển thị khác nhau khi hai phiên kết nối có thiết lập múi giờ khác nhau dù dữ liệu thực chất không đổi.

Ví dụ trong PostgreSQL:

```sql
SET TIME ZONE 'UTC';

SELECT TIMESTAMPTZ '2026-11-14 09:30:00+07' AS event_time;
-- Hiển thị theo UTC: 2026-11-14 02:30:00+00.

SET TIME ZONE 'Asia/Ho_Chi_Minh';

SELECT TIMESTAMPTZ '2026-11-14 09:30:00+07' AS event_time;
-- Hiển thị theo UTC+07: 2026-11-14 09:30:00+07.
```

Lệnh `SET TIME ZONE` thay đổi thiết lập phiên thực thi SQL; nó không viết lại các thời điểm đã lưu. Nếu ứng dụng cần giữ **tên khu vực gốc**, chẳng hạn `Asia/Ho_Chi_Minh` hay `America/New_York`, hãy lưu riêng tên múi giờ bên cạnh instant.

### 5.3. Một múi giờ không chỉ là một độ lệch UTC

- `+07:00` là **độ lệch cố định** so với UTC tại một thời điểm.
- `Asia/Ho_Chi_Minh` là **tên múi giờ vùng** theo cơ sở dữ liệu múi giờ; có các quy tắc lịch sử, chính sách địa phương.
- `America/New_York` là ví dụ nơi độ lệch so với UTC có thể đổi theo mùa, nên không thể giả định luôn là `-05:00` hoặc luôn là `-04:00`.

Khi một khu vực có **đổi giờ mùa hè (daylight saving time, DST)**, có thể tồn tại một giờ địa phương **không xảy ra** khi đồng hồ nhảy về phía trước, hoặc một giờ **xảy ra hai lần** khi đồng hồ lùi. Chuỗi “01:30” hoặc “02:30” theo giờ địa phương khi đó có thể thiếu ngữ cảnh hoặc mơ hồ nếu không có ngày và quy tắc khu vực.

Nếu một cuộc hẹn diễn ra vào tương lai theo giờ địa phương, thường cần lưu cả **múi giờ theo tên vùng** để diễn giải và cập nhật chính sách múi giờ, thay vì chỉ lưu độ lệch hiện tại.

### 5.4. TIMESTAMP khác Unix timestamp

Từ “timestamp” đôi khi cũng được dùng cho **Unix epoch time**, thường là số giây hoặc mili giây tính từ mốc 1970-01-01 00:00:00 UTC. Đây là một **cách mã hóa thời điểm bằng số**, không đồng nghĩa với kiểu `TIMESTAMP` của SQL.

Ví dụ một số API dùng số `epoch_millis`, còn DBMS dùng kiểu `TIMESTAMPTZ`. Khi trao đổi dữ liệu, phải xác định số đó là **giây hay mili giây**; nhầm đơn vị có thể tạo thời điểm sai rất xa.

## 6. INTERVAL: khoảng thời gian và phép cộng/trừ

`INTERVAL` trong PostgreSQL mô tả một lượng thời gian có thể bao gồm **tháng, ngày và thành phần giờ/phút/giây**. Nó khác `DATE` và `TIMESTAMP` vì **không phải một mốc thời gian**.

Ví dụ:

```sql
SELECT
    INTERVAL '2 hours 30 minutes' AS meeting_duration,
    INTERVAL '7 days' AS one_week,
    INTERVAL '1 month' AS calendar_month;
```

### 6.1. Cộng hoặc trừ khoảng thời gian

```sql
SELECT
    TIMESTAMP '2026-11-14 09:00:00'
        + INTERVAL '90 minutes' AS meeting_ends_at;

SELECT
    TIMESTAMP '2026-11-14 10:30:00'
        - TIMESTAMP '2026-11-14 09:00:00' AS elapsed_time;
```

Kết quả của ví dụ đầu là 10:30 cùng ngày. Ví dụ sau trả khoảng thời gian 1 giờ 30 phút trong PostgreSQL.

Tính thời điểm hết hạn:

```sql
SELECT
    TIMESTAMPTZ '2026-11-14 09:00:00+07'
        + INTERVAL '48 hours' AS expires_at;
```

Khi viết “hết hạn sau đúng 48 giờ”, đây là **thời lượng đã trôi qua**. Nếu yêu cầu nghiệp vụ là “đến cùng giờ ngày thứ hai kế tiếp theo lịch địa phương”, cần xem xét ý nghĩa **ngày lịch và múi giờ**, đặc biệt ở nơi có DST.

### 6.2. “Một tháng” không bằng “30 ngày”

Số ngày trong tháng thay đổi. Ví dụ trên PostgreSQL:

```sql
SELECT
    DATE '2024-01-31' + INTERVAL '1 month' AS plus_one_month,
    DATE '2024-01-31' + INTERVAL '30 days' AS plus_thirty_days;
```

Do tháng 2/2024 có 29 ngày, cộng một **tháng lịch** sẽ điều chỉnh về ngày cuối hợp lệ của tháng 2; cộng **30 ngày** tiến theo số ngày cố định và cho kết quả khác. Cộng một năm cũng có thể khác cộng 365 ngày nếu có năm nhuận.

Tương tự, ở múi giờ có DST, cộng `INTERVAL '1 day'` theo **ngày lịch địa phương** và cộng `INTERVAL '24 hours'` theo **24 giờ thực** có thể đưa đến hai mốc thời gian khác nhau trong PostgreSQL khi đi qua ngày đổi giờ. Hãy xác định nghiệp vụ cần “cùng giờ ngày kế tiếp” hay “đúng 24 giờ sau”.

### 6.3. Khoảng thời gian dùng để tính tuổi

“Tuổi theo năm/tháng/ngày trên lịch” khác “số giây đã sống”. Trong PostgreSQL, có hàm `age` để tính theo thành phần lịch:

```sql
SELECT age(DATE '2026-11-14', DATE '2000-05-20') AS calendar_age;
```

Không dùng phép trừ ngày rồi chia cố định cho `365` để tính tuổi theo quy tắc pháp lý/nghiệp vụ, vì năm nhuận và ngày kỷ niệm sinh có thể làm kết quả khác nhau.

## 7. Thực hành với bảng sự kiện trong PostgreSQL

Để lưu những sự kiện có thời điểm bắt đầu và kết thúc thật sự, ta dùng `TIMESTAMPTZ`. Ví dụ dưới đây giả định tài khoản có quyền tạo bảng trong cơ sở dữ liệu thực hành.

### 7.1. Tạo bảng

```sql
CREATE TABLE events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_name VARCHAR(150) NOT NULL,
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    CHECK (ends_at > starts_at)
);
```

Mỗi sự kiện gồm tên, thời điểm bắt đầu và kết thúc. Ràng buộc `CHECK` ngăn nhập giờ kết thúc không muộn hơn giờ bắt đầu. Dùng `TIMESTAMPTZ` giúp việc so sánh hai thời điểm không phụ thuộc vào cách chúng được hiển thị cho người dùng.

### 7.2. Thêm dữ liệu

```sql
INSERT INTO events (event_name, starts_at, ends_at)
VALUES
    (
        'Họp nhóm SQL',
        TIMESTAMPTZ '2026-11-14 09:00:00+07',
        TIMESTAMPTZ '2026-11-14 10:30:00+07'
    ),
    (
        'Trao đổi với nhóm ở UTC',
        TIMESTAMPTZ '2026-11-14 03:00:00+00',
        TIMESTAMPTZ '2026-11-14 04:00:00+00'
    );
```

Sự kiện thứ hai bắt đầu lúc **10:00 ở Việt Nam**, dù giá trị nhập ban đầu là **03:00 UTC**. Hai sự kiện có thể diễn ra chồng thời gian.

### 7.3. Hiển thị theo múi giờ Việt Nam và tính thời lượng

```sql
SELECT
    event_id,
    event_name,
    starts_at AT TIME ZONE 'Asia/Ho_Chi_Minh' AS local_start,
    ends_at AT TIME ZONE 'Asia/Ho_Chi_Minh' AS local_end,
    ends_at - starts_at AS duration
FROM events
ORDER BY starts_at;
```

Trong PostgreSQL, áp dụng `AT TIME ZONE 'Asia/Ho_Chi_Minh'` cho giá trị `TIMESTAMPTZ` tạo ra **giá trị ngày giờ địa phương không kèm múi giờ** để hiển thị hoặc nhóm dữ liệu. Các cột `starts_at` và `ends_at` bên dưới vẫn là instant có thể đối chiếu tuyệt đối.

Cũng có thể tính số phút bằng giây chênh lệch:

```sql
SELECT
    event_name,
    EXTRACT(EPOCH FROM (ends_at - starts_at)) / 60 AS duration_minutes
FROM events
ORDER BY event_id;
```

Với dữ liệu mẫu, thời lượng tương ứng là **90 phút** và **60 phút**.

### 7.4. Tìm sự kiện trong một khoảng ngày địa phương

Yêu cầu: tìm các sự kiện bắt đầu trong **tháng 11/2026 theo giờ Việt Nam**.

```sql
SELECT
    event_id,
    event_name,
    starts_at
FROM events
WHERE starts_at >= TIMESTAMPTZ '2026-11-01 00:00:00+07'
  AND starts_at <  TIMESTAMPTZ '2026-12-01 00:00:00+07'
ORDER BY starts_at;
```

Điều kiện này áp dụng khoảng **nửa mở**: lấy mọi thời điểm từ đầu tháng 11, **không lấy** thời điểm đúng đầu tháng 12. Cách viết này thường đáng tin cậy hơn:

```sql
-- Không khuyến khích: bỏ sót dữ liệu có phần lẻ giây sau 23:59:59.
WHERE starts_at BETWEEN
    TIMESTAMPTZ '2026-11-01 00:00:00+07'
    AND TIMESTAMPTZ '2026-11-30 23:59:59+07'
```

Với ứng dụng đa quốc gia, hai mốc bắt đầu/kết thúc nên được tạo theo **múi giờ nghiệp vụ cần lọc**, rồi chuyển thành instant để so sánh. Khi một khu vực có DST, không nên giả định đầu tháng ở cùng một độ lệch UTC cố định.

Một lợi ích khác: điều kiện so sánh **trực tiếp trên cột** `starts_at` thường thuận lợi cho việc dùng chỉ mục B-tree hơn biểu thức chuyển đổi trên từng giá trị như `starts_at::date`; tối ưu cụ thể vẫn phụ thuộc kế hoạch truy vấn và chỉ mục thực tế.

### 7.5. Nhóm theo ngày địa phương

```sql
SELECT
    (starts_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS local_date,
    COUNT(*) AS event_count
FROM events
GROUP BY (starts_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
ORDER BY local_date;
```

Cùng một instant có thể rơi vào **ngày UTC khác ngày Việt Nam**. Chẳng hạn `2026-11-14 00:30:00+07` tương đương `2026-11-13 17:30:00+00`. Vì vậy, nhóm `TIMESTAMPTZ` theo ngày mà không xác định múi giờ nghiệp vụ có thể tạo báo cáo không như mong muốn.

## 8. Hàm ngày giờ thường gặp

Đa số DBMS cung cấp hàm lấy thời gian hiện tại, trích xuất thành phần và cộng trừ ngày giờ; nhưng tên hàm và chi tiết hoạt động khác nhau.

### 8.1. Lấy ngày giờ hiện tại

Ví dụ PostgreSQL:

```sql
SELECT
    CURRENT_DATE AS today,
    CURRENT_TIME AS current_clock_with_zone,
    CURRENT_TIMESTAMP AS current_instant,
    LOCALTIMESTAMP AS local_datetime;
```

- `CURRENT_DATE` trả về ngày hiện tại theo **múi giờ phiên**.
- `CURRENT_TIME` trong PostgreSQL là giờ hiện tại với thông tin độ lệch múi giờ.
- `CURRENT_TIMESTAMP` là thời điểm hiện tại dưới dạng `TIMESTAMPTZ`.
- `LOCALTIMESTAMP` là ngày giờ theo phiên, nhưng **không mang múi giờ** trong kiểu trả về.

Trong PostgreSQL, `CURRENT_TIMESTAMP` và `now()` phản ánh **thời điểm bắt đầu giao dịch hiện tại**. Nếu cần đọc đồng hồ thực đang tiến trong một giao dịch dài, PostgreSQL có `clock_timestamp()`:

```sql
SELECT
    now() AS transaction_start_time,
    clock_timestamp() AS current_wall_clock;
```

Không giả định các hàm “current time” của mọi DBMS có cùng quy tắc cố định thời gian theo giao dịch.

### 8.2. Trích xuất năm, tháng, ngày, giờ

```sql
SELECT
    EXTRACT(YEAR FROM TIMESTAMP '2026-11-14 09:30:45') AS year_value,
    EXTRACT(MONTH FROM TIMESTAMP '2026-11-14 09:30:45') AS month_value,
    EXTRACT(DAY FROM TIMESTAMP '2026-11-14 09:30:45') AS day_value,
    EXTRACT(HOUR FROM TIMESTAMP '2026-11-14 09:30:45') AS hour_value;
```

Kết quả tương ứng: năm `2026`, tháng `11`, ngày `14`, giờ `9`.

Có thể dùng `DATE_TRUNC` để đưa ngày giờ về đầu một đơn vị trong PostgreSQL:

```sql
SELECT DATE_TRUNC(
    'month',
    TIMESTAMP '2026-11-14 09:30:45'
) AS month_start;
```

Kết quả là `2026-11-01 00:00:00` dưới dạng `TIMESTAMP`.

### 8.3. Chuyển đổi kiểu và định dạng khi xuất dữ liệu

Ví dụ PostgreSQL:

```sql
SELECT
    CAST('2026-11-14' AS DATE) AS parsed_date,
    CAST(TIMESTAMP '2026-11-14 09:30:45' AS DATE) AS only_date;
```

Khi cần hiển thị theo định dạng giao diện, PostgreSQL có `TO_CHAR`:

```sql
SELECT TO_CHAR(
    TIMESTAMP '2026-11-14 09:30:45',
    'DD/MM/YYYY HH24:MI'
) AS display_value;
```

Giá trị hiển thị sẽ là chuỗi `14/11/2026 09:30`; **kiểu của kết quả là văn bản**, không phải `TIMESTAMP`. Trong ứng dụng thực tế, việc định dạng theo ngôn ngữ người dùng thường được làm ở lớp trình bày, còn database giữ giá trị ngày giờ có kiểu thích hợp.

### 8.4. Chuyển giữa ngày giờ địa phương và instant

`AT TIME ZONE` trong PostgreSQL có **hai hướng biến đổi** tùy kiểu dữ liệu đầu vào:

```sql
-- Từ giờ địa phương đã biết vùng sang instant.
SELECT
    TIMESTAMP '2026-11-14 09:30:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh' AS event_instant;

-- Từ instant sang ngày giờ địa phương để hiển thị.
SELECT
    TIMESTAMPTZ '2026-11-14 02:30:00+00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh' AS local_datetime;
```

Câu đầu **diễn giải** 09:30 là giờ địa phương Việt Nam và trả `TIMESTAMPTZ`. Câu sau **hiển thị** instant 02:30 UTC thành ngày giờ địa phương 09:30 và trả `TIMESTAMP WITHOUT TIME ZONE`. Đừng đảo hai hướng này khi xử lý lịch hẹn.

## 9. Khác biệt quan trọng giữa các hệ quản trị

Mặc dù ý niệm ngày, giờ và instant gần giống nhau, **tên kiểu dữ liệu và cách chuyển múi giờ không giống nhau**.

| DBMS | Ngày | Giờ trong ngày | Ngày + giờ / instant | Tính toán khoảng thời gian |
|---|---|---|---|---|
| PostgreSQL | `DATE` | `TIME` | `TIMESTAMP` không múi giờ, `TIMESTAMPTZ` cho instant | Có kiểu `INTERVAL` và phép cộng/trừ trực tiếp |
| MySQL | `DATE` | `TIME` (còn dùng cho duration) | `DATETIME` và `TIMESTAMP` có ngữ nghĩa khác nhau về timezone | `DATE_ADD`, `DATE_SUB`, biểu thức `INTERVAL n DAY`…; không có kiểu cột `INTERVAL` tổng quát tương đương PostgreSQL |
| SQL Server | `date` | `time` | `datetime2`, `datetimeoffset` | `DATEADD`, `DATEDIFF` và các biến thể |
| SQLite | Không có storage class riêng cho ngày | Không có storage class riêng cho giờ | Thường biểu diễn bằng `TEXT`, `REAL` hoặc `INTEGER` theo quy ước | `date()`, `time()`, `datetime()`, `julianday()`, `strftime()` với các modifier |

### 9.1. MySQL: phân biệt DATETIME và TIMESTAMP

Trong MySQL, `DATETIME` thường biểu diễn giá trị ngày giờ **không tự chuyển theo múi giờ phiên** như kiểu `TIMESTAMP`. Còn `TIMESTAMP` được MySQL chuyển đổi từ múi giờ phiên sang UTC khi lưu và từ UTC sang múi giờ phiên khi đọc. Hai kiểu còn có **phạm vi ngày hỗ trợ khác nhau**, tùy phiên bản và độ chính xác cấu hình.

Ví dụ cộng bảy ngày trong MySQL:

```sql
SELECT DATE_ADD('2026-11-14', INTERVAL 7 DAY) AS next_week;
```

Không tự giả định MySQL `TIMESTAMP` có cùng phạm vi và hành vi như PostgreSQL `TIMESTAMPTZ`.

### 9.2. SQL Server: TIMESTAMP không có nghĩa ngày giờ

Trong SQL Server, tên kiểu dữ liệu `timestamp` (tương đương `rowversion`) **không lưu ngày hoặc giờ**. Đây là giá trị nhị phân dùng để đánh dấu phiên bản dữ liệu của hàng, không thể dùng làm thời điểm giao dịch.

Với dữ liệu ngày giờ, SQL Server thường dùng:

- `date` cho ngày;
- `time` cho giờ;
- `datetime2` cho ngày giờ không kèm offset;
- `datetimeoffset` cho ngày giờ đi kèm độ lệch UTC.

Ví dụ:

```sql
SELECT
    DATEADD(day, 7, CAST('2026-11-14' AS date)) AS next_week,
    DATEDIFF(day, CAST('2026-11-14' AS date),
                  CAST('2026-11-21' AS date)) AS days_between;
```

`DATEDIFF` của SQL Server đếm **số ranh giới của đơn vị được chỉ định** đã đi qua, không đơn giản luôn là thời lượng thực chia cho số giây của đơn vị. Ví dụ, `DATEDIFF(day, ...)` có thể trả về 1 cho hai thời điểm chỉ cách nhau một vài giây nhưng nằm ở hai ngày khác nhau.

### 9.3. SQLite: ngày giờ thường nằm trong các biểu diễn thông dụng

SQLite không cung cấp kiểu lưu trữ ngày giờ chuyên biệt giống PostgreSQL. Dữ liệu thời gian thường được lưu dưới một trong các dạng: chuỗi ISO 8601 trong `TEXT`, số Julian day trong `REAL`, hoặc Unix timestamp trong `INTEGER`.

Ví dụ:

```sql
SELECT
    date('2026-11-14', '+7 days') AS next_week,
    datetime('2026-11-14 09:00:00', '+90 minutes') AS meeting_end;
```

Khi dùng SQLite, cần **quy định rõ một chuẩn lưu trữ nhất quán** cho từng cột; nếu trộn nhiều định dạng trong một cột văn bản, việc sắp xếp và lọc theo thứ tự thời gian có thể sai.

### 9.4. Không chỉ khác tên hàm

Ngoài tên kiểu và hàm, các DBMS còn khác nhau ở:

- Phạm vi năm và độ chính xác phần lẻ giây.
- Cách làm tròn/cắt phần lẻ giây và quy tắc chuyển kiểu.
- Quy tắc khi nhập chuỗi không có timezone.
- Cách xử lý daylight saving time và múi giờ phiên.
- Khả năng lưu `INTERVAL` làm kiểu cột và cách cộng ngày/tháng.
- Quy tắc hiển thị/định dạng ở driver, terminal và phần mềm GUI.

Khi chuyển SQL giữa các DBMS, hãy kiểm tra **ngữ nghĩa của kiểu dữ liệu**, không chỉ sửa tên hàm để câu lệnh chạy được.

## 10. Thiết kế dữ liệu thời gian phù hợp nghiệp vụ

Một số lựa chọn điển hình:

| Yêu cầu | Thiết kế thường phù hợp | Vì sao |
|---|---|---|
| Sinh nhật nhân viên | `DATE` | Không cần giờ hay instant |
| Giờ mở cửa hàng ngày | `TIME` + thông tin ngày trong tuần/chi nhánh | Mô tả giờ đồng hồ địa phương |
| Đơn hàng được tạo vào lúc nào | `TIMESTAMPTZ` (PostgreSQL) | Cần so sánh sự kiện trên dòng thời gian |
| Cuộc hẹn diễn ra lúc 09:00 tại một khu vực | Instant đã xác định + tên múi giờ khu vực nếu cần giữ quy tắc địa phương | Vừa xác định được thời điểm vừa tái dựng ý định giờ địa phương |
| Lịch lặp “thứ Hai hàng tuần lúc 09:00” | Ngày trong tuần + `TIME` + tên múi giờ + quy tắc lặp | Một timestamp cố định không mô tả cả chuỗi sự kiện |
| Thời gian xử lý tính bằng mili giây | Số mili giây hoặc interval, theo nhu cầu | Đại diện cho thời lượng, không phải ngày giờ |
| Kỳ báo cáo theo tháng | Ngày bắt đầu + ngày kết thúc loại trừ, cùng timezone nghiệp vụ | Tránh nhập nhằng ranh giới và phần lẻ giây |

### 10.1. Độ chính xác và giá trị NULL

Một số kiểu timestamp hỗ trợ phần lẻ giây, ví dụ PostgreSQL:

```sql
CREATE TABLE sensor_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    measured_at TIMESTAMPTZ(3) NOT NULL,
    recorded_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
```

`TIMESTAMPTZ(3)` trong PostgreSQL chỉ định độ chính xác đến **mili giây**. Các hệ quản trị khác có thể dùng phạm vi precision khác hoặc quy tắc làm tròn khác. Chỉ chọn độ chính xác cần thiết cho nghiệp vụ.

Nếu một thời điểm chưa biết hoặc chưa xảy ra, hãy cân nhắc `NULL` thay vì gán ngày giả định như `1900-01-01`. Kiểm tra `NULL` bằng:

```sql
SELECT *
FROM sensor_events
WHERE recorded_at IS NULL;
```

Vì `recorded_at` ở ví dụ được khai báo có `DEFAULT` nhưng không có `NOT NULL`, ứng dụng vẫn có thể chủ động ghi `NULL`. Trường hợp muốn bắt buộc có giá trị, thêm ràng buộc `NOT NULL` theo yêu cầu.

### 10.2. Một số thói quen giúp tránh lỗi

1. **Giữ instant ở kiểu có ngữ nghĩa rõ ràng.** Với PostgreSQL, thường dùng `TIMESTAMPTZ` cho thời điểm giao dịch, sự kiện hoặc log.
2. **Giữ ngày lịch là `DATE`.** Không tự biến ngày sinh thành 00:00 UTC nếu không có lý do nghiệp vụ.
3. **Biết múi giờ của dữ liệu đầu vào.** Chuỗi `2026-11-14 09:30:00` chưa đủ cho việc quy đổi thành instant nếu không biết đó là giờ ở đâu.
4. **Đặt ranh giới thời gian theo khoảng nửa mở.** Dùng `>=` đầu kỳ và `<` đầu kỳ kế tiếp khi lọc theo ngày/tháng.
5. **Không dùng ngày dưới dạng chuỗi để tính toán.** Hãy chuyển sang kiểu ngày giờ rồi mới cộng, trừ hoặc so sánh.
6. **Phân biệt thời lượng thực và đơn vị lịch.** “24 giờ sau”, “ngày mai lúc 09:00” và “cộng một tháng” là những quy tắc khác nhau.
7. **Kiểm tra múi giờ phiên và driver.** Dữ liệu lưu đúng vẫn có thể được hiển thị lệch giờ nếu ứng dụng giả định sai timezone.
8. **Không tự ghép dữ liệu ngày giờ vào câu SQL trong ứng dụng.** Dùng tham số có kiểu phù hợp để hạn chế lỗi định dạng, chuyển kiểu và SQL injection.

## 11. Bài tập tự kiểm tra

### Bài 1: Chọn kiểu dữ liệu

Với mỗi trường sau, hãy chọn kiểu dữ liệu PostgreSQL phù hợp nhất:

- `birth_date`: ngày sinh.
- `daily_opening_time`: giờ mở cửa thông thường.
- `payment_confirmed_at`: thời điểm xác nhận thanh toán.
- `processing_duration`: thời gian xử lý một yêu cầu.

**Gợi ý đáp án:** lần lượt là `DATE`, `TIME`, `TIMESTAMPTZ` và `INTERVAL` (hoặc số mili giây nếu quy ước lưu duration của hệ thống như vậy).

### Bài 2: Hai chuỗi có cùng instant không?

```text
2026-11-14 09:00:00+07:00
2026-11-14 02:00:00+00:00
```

**Đáp án:** Có. Cả hai đều ứng với 02:00 UTC. Độ lệch UTC chỉ làm thay đổi cách biểu diễn giờ đồng hồ của cùng một thời điểm.

### Bài 3: Tìm sự kiện trong một ngày theo giờ Việt Nam

Viết truy vấn PostgreSQL lấy sự kiện bắt đầu vào **ngày 14/11/2026 theo giờ Việt Nam**.

**Một lời giải:**

```sql
SELECT
    event_id,
    event_name,
    starts_at
FROM events
WHERE starts_at >= TIMESTAMPTZ '2026-11-14 00:00:00+07'
  AND starts_at <  TIMESTAMPTZ '2026-11-15 00:00:00+07'
ORDER BY starts_at;
```

Khi chuyển bài này sang múi giờ thay đổi theo mùa, hãy xây dựng hai ranh giới theo tên vùng và ngày lịch tương ứng.

### Bài 4: Tính thời lượng

Viết câu SQL PostgreSQL tính số phút giữa 09:15 và 10:45 cùng ngày 14/11/2026.

```sql
SELECT EXTRACT(
    EPOCH FROM (
        TIMESTAMP '2026-11-14 10:45:00'
        - TIMESTAMP '2026-11-14 09:15:00'
    )
) / 60 AS minutes_elapsed;
```

**Đáp án:** `90` phút.

### Bài 5: Vì sao chỉ lưu offset có thể chưa đủ?

Một nhóm định lên lịch làm việc lúc 09:00 mỗi thứ Hai theo giờ New York cho cả năm tới. Nếu chỉ lưu offset `-05:00`, điều gì có thể sai?

**Đáp án:** New York có những giai đoạn dùng offset `-04:00`. Offset cố định không biểu diễn đúng quy tắc múi giờ qua các mùa. Nên giữ **tên vùng** `America/New_York` và quy tắc lịch theo giờ địa phương, rồi tính instant cho từng buổi theo quy tắc vùng tại ngày xảy ra sự kiện.

## 12. Những điểm cần ghi nhớ

- `DATE` lưu **ngày**, `TIME` lưu **giờ đồng hồ**, timestamp/datetime lưu **ngày kết hợp giờ**, còn interval/duration lưu **khoảng thời gian**.
- `TIMESTAMP WITHOUT TIME ZONE` chỉ là giá trị ngày giờ địa phương; nó **không tự cho biết instant**. Trong PostgreSQL, `TIMESTAMPTZ` phù hợp hơn để lưu thời điểm tuyệt đối.
- Múi giờ theo **tên khu vực** khác với **độ lệch UTC**. Khi nghiệp vụ liên quan đến lịch tương lai hoặc giờ địa phương, cần giữ đủ ngữ cảnh để xử lý các thay đổi quy tắc múi giờ.
- Tính toán **ngày/tháng theo lịch** có thể khác tính **giờ/phút/giây đã trôi qua**.
- Dùng dạng ngày giờ rõ ràng, tham số truy vấn có kiểu đúng và khoảng lọc **[bắt đầu, kết thúc)** để giảm lỗi dữ liệu và ranh giới thời gian.
- Tên kiểu và cú pháp biến đổi ngày giờ phụ thuộc DBMS. Đặc biệt, `timestamp` của **SQL Server là `rowversion`, không phải kiểu lưu thời điểm**.

Khi thiết kế một cột thời gian, hãy trả lời chính xác ba câu hỏi: **dữ liệu là ngày lịch, giờ địa phương hay instant; có cần biết múi giờ không; và các phép cộng/trừ mong muốn là theo lịch hay theo thời lượng thực?** Những câu trả lời đó quyết định kiểu dữ liệu và câu truy vấn phù hợp.


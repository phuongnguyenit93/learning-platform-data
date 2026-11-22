# generate_series để dựng lịch và dữ liệu mẫu trong PostgreSQL

## 1. Tại sao cần sinh dãy trong một truy vấn SQL?

Trong ứng dụng thực tế, đôi khi ta cần những hàng **chưa tồn tại trong bảng dữ liệu**:

- Báo cáo doanh số từng ngày phải hiện cả ngày **không có giao dịch** với tổng bằng 0.
- Lịch đặt phòng cần hiển thị các khung giờ 30 phút từ 09:00 đến 17:00.
- Bảng điều khiển cần đủ 12 tháng của năm, ngay cả khi một vài tháng chưa có dữ liệu.
- Công cụ thử nghiệm cần tạo 100 người dùng, 1.000 đơn hàng hoặc các bản ghi có ngày giờ có quy luật.
- Một nhiệm vụ lặp lại cần sinh ra từng ngày làm việc trong một khoảng.
- Mỗi nhân viên có ngày bắt đầu/kết thúc khác nhau, cần mở rộng mỗi khoảng thành các hàng ngày riêng biệt.

PostgreSQL cung cấp hàm **`generate_series`** để sinh một **tập hợp giá trị** (*set-returning function*, SRF). Ta có thể dùng tập hợp này trong `FROM` và ghép với bảng thật như một nguồn dữ liệu thông thường.

Ví dụ đơn giản:

```sql
SELECT n
FROM generate_series(1, 5) AS g(n);
```

Kết quả:

| n |
|---:|
| 1 |
| 2 |
| 3 |
| 4 |
| 5 |

Không cần tạo bảng chứa sẵn các số từ 1 đến 5. Đây là các hàng sinh ra **khi truy vấn thực thi**.

### Mục tiêu bài học

Sau bài này, bạn có thể:

1. Sử dụng các phiên bản `generate_series` cho số nguyên, số thập phân và thời điểm.
2. Hiểu đầu mút **bao gồm điểm cuối**, bước nhảy, dãy giảm, dãy rỗng và các trường hợp lỗi.
3. Tạo lịch theo ngày, tuần, tháng, quý và khung giờ.
4. Phân biệt kiểu `date`, `timestamp` và `timestamptz` khi sinh lịch.
5. Xử lý múi giờ, daylight saving time (DST) và ranh giới ngày địa phương.
6. Kết hợp dãy sinh với `CROSS JOIN`, `LEFT JOIN` và `LATERAL`.
7. Lấp các ngày hoặc khoảng thời gian không có dữ liệu trong báo cáo.
8. Sinh dữ liệu mẫu có cấu trúc, có thể tái tạo và không quá tải database.
9. Tránh lỗi off-by-one, nhân số hàng ngoài ý muốn, bước nhảy sai hướng và lọc `WHERE` khiến ngày trống biến mất.
10. Biết khi nào nên dùng dãy sinh động và khi nào cần một bảng calendar được duy trì lâu dài.

## 2. Cú pháp và các kiểu đầu vào

Cách gọi khái quát:

```text
generate_series(start, stop [, step])
```

Ý nghĩa:

| Tham số | Vai trò |
|---|---|
| `start` | Giá trị đầu của dãy |
| `stop` | Giới hạn cuối của dãy, **được bao gồm nếu bước nhảy chạm tới** |
| `step` | Độ tăng/giảm mỗi lần; với số nguyên thường mặc định là 1 |

Một số chữ ký thường dùng:

| Loại dãy | Cách gọi | Giá trị trả về |
|---|---|---|
| Số nguyên | `generate_series(integer, integer [, integer])` | `integer` |
| Số nguyên lớn | `generate_series(bigint, bigint [, bigint])` | `bigint` |
| Số thập phân chính xác | `generate_series(numeric, numeric, numeric)` | `numeric` |
| Ngày giờ không có múi giờ | `generate_series(timestamp, timestamp, interval)` | `timestamp` |
| Thời điểm có múi giờ | `generate_series(timestamptz, timestamptz, interval)` | `timestamptz` |
| Thời điểm với tên múi giờ tường minh | `generate_series(timestamptz, timestamptz, interval, text)` | `timestamptz` |

**Lưu ý phiên bản:** dạng bốn đối số có tên vùng múi giờ tường minh được hỗ trợ trong PostgreSQL 16 trở lên. Với bản cũ, dùng dạng ba đối số và quản lý múi giờ của session, hoặc tạo lịch ngày địa phương rồi chuyển đổi tường minh.

Có thể kiểm tra phiên bản môi trường:

```sql
SHOW server_version;
```

### 2.1. Một ví dụ dãy tăng

```sql
SELECT value
FROM generate_series(2, 10, 2) AS s(value);
```

Kết quả:

```text
2
4
6
8
10
```

Giá trị 10 được sinh ra vì dãy bắt đầu ở 2 và liên tục tăng 2, vừa chạm tới `stop = 10`.

### 2.2. Một ví dụ dãy không chạm giới hạn cuối

```sql
SELECT value
FROM generate_series(2, 11, 2) AS s(value);
```

Kết quả vẫn là:

```text
2
4
6
8
10
```

Không có 11 vì 11 không nằm trên dãy bước nhảy 2 bắt đầu từ 2.

### 2.3. Biệt danh cột rất quan trọng

Có thể viết:

```sql
SELECT *
FROM generate_series(1, 3);
```

Nhưng trong code ứng dụng và tài liệu nên đặt alias rõ:

```sql
SELECT g.n
FROM generate_series(1, 3) AS g(n);
```

Khi kết hợp nhiều bảng, `g.n` dễ nhận diện hơn cột tên mặc định do hàm sinh ra.

## 3. Quy tắc bao gồm cả hai đầu mút

`generate_series` thường tạo giá trị đầu tiên `start` và tiếp tục từng bước cho tới khi vượt `stop` theo hướng đi. Nếu chuỗi giá trị chạm đúng `stop` thì **giá trị cuối cũng xuất hiện**.

```sql
SELECT n
FROM generate_series(1, 1) AS g(n);
```

Kết quả: **một hàng**, n = 1.

```sql
SELECT n
FROM generate_series(1, 3) AS g(n);
```

Kết quả: 1, 2, 3, **không phải chỉ 1 và 2**.

Điều này dễ gây lỗi khi yêu cầu là:

> “Tạo lịch từ ngày bắt đầu tới **trước** ngày kết thúc.”

Khi cần khoảng nửa mở `[start, end)`, phải điều chỉnh giới hạn hoặc lọc tường minh. Phần 7 sẽ minh họa cách làm an toàn với ngày.

### 3.1. Một truy vấn minh họa rõ số hàng

```sql
SELECT COUNT(*) AS generated_rows
FROM generate_series(1, 10) AS g(n);
```

Kết quả: **10 hàng**, không phải 9.

Đặc điểm này áp dụng cho dãy số và dãy thời gian: điểm cuối chỉ xuất hiện nếu các bước nhảy thực sự đưa dãy tới điểm đó.

## 4. Bước nhảy dương, âm, bằng 0 và NULL

### 4.1. Dãy tăng

```sql
SELECT n
FROM generate_series(1, 9, 2) AS g(n);
```

Kết quả: 1, 3, 5, 7, 9.

### 4.2. Dãy giảm

```sql
SELECT n
FROM generate_series(10, 1, -3) AS g(n);
```

Kết quả: 10, 7, 4, 1.

`step` âm có ý nghĩa khi đi từ giá trị lớn xuống giá trị nhỏ.

### 4.3. Bước sai hướng trả dãy rỗng

```sql
SELECT n
FROM generate_series(5, 1, 1) AS g(n);
```

Không có hàng nào, vì đang yêu cầu đi từ 5 xuống 1 nhưng bước lại dương.

Tương tự:

```sql
SELECT n
FROM generate_series(1, 5, -1) AS g(n);
```

cũng không có hàng.

Một dãy rỗng không phải là một hàng chứa số 0 hoặc một hàng chứa NULL: **nó thực sự không tạo hàng**.

### 4.4. Bước bằng 0 là lỗi

```sql
-- Ví dụ để nhận diện lỗi; không cần chạy trong giao dịch quan trọng.
SELECT n
FROM generate_series(1, 5, 0) AS g(n);
```

PostgreSQL báo lỗi vì bước nhảy bằng 0 không làm dãy tiến về giới hạn kết thúc.

Nếu step đến từ input của người dùng hoặc bảng cấu hình, cần **kiểm tra step khác 0** trước khi gọi.

### 4.5. Đối số NULL không tạo dãy giá trị

```sql
SELECT n
FROM generate_series(NULL::integer, 5, 1) AS g(n);
```

Thông thường kết quả là **0 hàng**, vì đầu vào cần thiết là NULL. Đừng nhầm “không có hàng” với “có một hàng NULL”.

Trong truy vấn thực tế, điều này ảnh hưởng rõ khi dùng `CROSS JOIN LATERAL` hoặc `LEFT JOIN LATERAL`: một nguồn sinh 0 hàng có thể làm biến mất hàng cha ở CROSS JOIN, trong khi LEFT JOIN bảo toàn hàng cha.

## 5. Sinh số thập phân với numeric

Không chỉ tạo số nguyên, PostgreSQL còn hỗ trợ `numeric`:

```sql
SELECT x
FROM generate_series(
    0.0::numeric,
    1.0::numeric,
    0.2::numeric
) AS g(x);
```

Kết quả:

```text
0.0
0.2
0.4
0.6
0.8
1.0
```

Dùng `numeric` phù hợp khi cần giá trị thập phân chính xác theo một bước xác định, ví dụ dãy mức giá, mức chiết khấu hoặc tham số thử nghiệm.

Không nên mặc định các phép tính dấu phẩy động `real`/`double precision` có cùng ngữ nghĩa chính xác thập phân như `numeric`. Nếu dữ liệu liên quan tiền tệ hoặc kiểm soát đầu mút, hãy chọn kiểu rõ ràng.

### 5.1. Dãy giảm numeric

```sql
SELECT x
FROM generate_series(
    1.0::numeric,
    0.0::numeric,
    -0.25::numeric
) AS g(x);
```

Kết quả: 1.00, 0.75, 0.50, 0.25, 0.00 theo định dạng hiển thị phù hợp.

### 5.2. Tạo bước từ số nguyên thường dễ kiểm soát hơn

Nếu muốn sinh các giá trị trăm nghìn đồng từ 100.000 tới 500.000:

```sql
SELECT n * 100000 AS price
FROM generate_series(1, 5) AS g(n);
```

Khi đơn vị bước đã là số nguyên, cách nhân từ dãy integer thường đơn giản hơn việc đưa mọi thứ sang numeric.

## 6. Sinh ngày: vì sao dùng DATE cộng số nguyên?

Nhiều người thử:

```sql
-- Không phải chữ ký generate_series(date, date, interval) chuyên biệt.
-- SELECT * FROM generate_series(DATE '2026-11-14',
--                               DATE '2026-11-20',
--                               INTERVAL '1 day');
```

PostgreSQL có các overload ngày giờ kiểu `timestamp`/`timestamptz`, không có một overload date-to-date độc lập nhận số bước là số ngày. Trong các ngữ cảnh PostgreSQL có thể **ép kiểu** giá trị date để tìm overload thích hợp, nhưng kết quả sẽ thuộc kiểu timestamp phù hợp, không mặc nhiên là kiểu `date`.

Khi chỉ cần **ngày lịch**, cách đơn giản và minh bạch là tạo một dãy số nguyên rồi cộng vào `date`:

```sql
SELECT
    DATE '2026-11-14' + g.n AS calendar_day
FROM generate_series(0, 6) AS g(n)
ORDER BY calendar_day;
```

Kết quả:

| calendar_day |
|---|
| 2026-11-14 |
| 2026-11-15 |
| 2026-11-16 |
| 2026-11-17 |
| 2026-11-18 |
| 2026-11-19 |
| 2026-11-20 |

Với PostgreSQL:

- `date + integer` tạo một ngày cách ngày gốc một số **ngày lịch**.
- Dãy số bắt đầu ở 0 để hàng đầu tiên chính là ngày bắt đầu.
- Bảy ngày từ 14 đến 20 (bao gồm hai đầu) cần các offset 0, 1, ..., 6.

### 6.1. Dùng CTE để đặt tên nguồn lịch

```sql
WITH calendar AS (
    SELECT DATE '2026-11-14' + n AS day
    FROM generate_series(0, 6) AS g(n)
)
SELECT day
FROM calendar
ORDER BY day;
```

Đây là mẫu cơ bản sẽ dùng khi nối lịch với dữ liệu giao dịch thật.

## 7. Tạo khoảng ngày nửa mở [start_date, end_exclusive)

Trong thiết kế API và truy vấn thời gian, ranh giới nửa mở thường dễ kiểm soát:

```text
[start_date, end_exclusive)
```

Ví dụ từ ngày 14/11 đến **trước** 20/11 có các ngày 14, 15, 16, 17, 18, 19: tổng cộng 6 ngày.

Có thể viết:

```sql
WITH bounds AS (
    SELECT
        DATE '2026-11-14' AS start_date,
        DATE '2026-11-20' AS end_exclusive
)
SELECT
    b.start_date + g.n AS day
FROM bounds AS b
CROSS JOIN LATERAL generate_series(
    0,
    b.end_exclusive - b.start_date - 1
) AS g(n)
ORDER BY day;
```

Ở đây:

- Phép trừ hai giá trị `date` trả về số ngày dạng integer.
- Nếu khoảng dài 6 ngày thì cận trên của offset là `6 - 1 = 5`.
- Dãy từ 0 đến 5 tạo đúng sáu ngày.
- Khi `start_date = end_exclusive`, cận trên là -1, dãy `generate_series(0,-1)` rỗng — đúng với khoảng thời gian rỗng.
- Khi end trước start, dãy cũng rỗng với bước mặc định dương. Ứng dụng vẫn nên **kiểm tra/không chấp nhận khoảng nhập sai** theo nghiệp vụ.

### 7.1. Vì sao không luôn trừ một mili-giây ở cuối?

Với dữ liệu thời điểm, các độ chính xác có thể khác nhau, và một timestamp có thể chứa phần giây thập phân. Việc lấy `end - interval '1 millisecond'` có thể bỏ sót hoặc tạo giới hạn khó hiểu nếu bước nhảy không khớp.

Tốt hơn là:

```sql
WHERE event_time >= lower_boundary
  AND event_time < upper_boundary
```

và khi sinh bucket, dùng ranh giới nửa mở rõ ràng.

## 8. Sinh dãy timestamp bằng INTERVAL

Nếu cần các mốc trong cùng một ngày:

```sql
SELECT slot_start
FROM generate_series(
    TIMESTAMP '2026-11-16 09:00:00',
    TIMESTAMP '2026-11-16 12:00:00',
    INTERVAL '30 minutes'
) AS g(slot_start)
ORDER BY slot_start;
```

Các giá trị:

```text
09:00
09:30
10:00
10:30
11:00
11:30
12:00
```

**Lưu ý:** 12:00 xuất hiện vì `generate_series` bao gồm điểm cuối nếu bước nhảy chạm tới. Nếu 12:00 là **thời điểm đóng cửa**, thường không nên tạo một slot mới bắt đầu lúc 12:00.

### 8.1. Sinh các slot 30 phút từ 09:00 tới trước 12:00

```sql
SELECT
    g.slot_start,
    g.slot_start + INTERVAL '30 minutes' AS slot_end
FROM generate_series(
    TIMESTAMP '2026-11-16 09:00:00',
    TIMESTAMP '2026-11-16 11:30:00',
    INTERVAL '30 minutes'
) AS g(slot_start)
ORDER BY g.slot_start;
```

Kết quả có **6 slot**:

| slot_start | slot_end |
|---|---|
| 09:00 | 09:30 |
| 09:30 | 10:00 |
| 10:00 | 10:30 |
| 10:30 | 11:00 |
| 11:00 | 11:30 |
| 11:30 | 12:00 |

Mỗi slot có thể hiểu là một khoảng nửa mở `[slot_start, slot_end)`, nên hai slot liên tiếp không chồng lấn.

### 8.2. Tạo cột range cho từng slot

```sql
SELECT
    g.slot_start,
    tsrange(
        g.slot_start,
        g.slot_start + INTERVAL '30 minutes',
        '[)'
    ) AS slot_period
FROM generate_series(
    TIMESTAMP '2026-11-16 09:00:00',
    TIMESTAMP '2026-11-16 11:30:00',
    INTERVAL '30 minutes'
) AS g(slot_start)
ORDER BY g.slot_start;
```

Kết quả `slot_period` có kiểu `tsrange` vì đây là `timestamp without time zone`. Nếu ứng dụng cần đặt lịch theo thời điểm thật và có nhiều múi giờ, nên cân nhắc `tstzrange` và quy tắc chuyển đổi múi giờ phù hợp.

## 9. Hiểu DATE, TIMESTAMP và TIMESTAMPTZ khi dựng lịch

Ba kiểu này biểu diễn ba ý nghĩa khác nhau:

| Kiểu | Biểu diễn | Ví dụ |
|---|---|---|
| `date` | Một ngày lịch, chưa có giờ | 2026-11-16 |
| `timestamp` | Ngày và giờ địa phương, không tự mang múi giờ | 2026-11-16 09:00 |
| `timestamptz` | Một thời điểm thực tế, hiển thị theo timezone của session | 2026-11-16 09:00+07 |

### 9.1. Sinh giờ địa phương bằng timestamp

```sql
SELECT slot_start
FROM generate_series(
    TIMESTAMP '2026-11-16 09:00',
    TIMESTAMP '2026-11-16 11:00',
    INTERVAL '1 hour'
) AS g(slot_start);
```

Các mốc 09:00, 10:00, 11:00 chưa tự gắn một tên vùng múi giờ. Phù hợp cho lịch hiển thị **giờ trên đồng hồ** nếu ngữ nghĩa múi giờ được quản lý riêng.

### 9.2. Sinh những thời điểm có offset

```sql
SELECT tick_at
FROM generate_series(
    TIMESTAMPTZ '2026-11-16 09:00:00+07',
    TIMESTAMPTZ '2026-11-16 11:00:00+07',
    INTERVAL '1 hour'
) AS g(tick_at);
```

Các hàng là các giá trị `timestamptz`. Nếu session đang dùng UTC, PostgreSQL có thể hiển thị tương ứng 02:00, 03:00, 04:00+00; nếu session dùng `Asia/Ho_Chi_Minh`, hiển thị 09:00, 10:00, 11:00+07. Đây là **cùng các thời điểm**, không phải dữ liệu khác nhau.

### 9.3. Kiểm tra múi giờ session

```sql
SHOW TimeZone;
```

Đối với dạng ba tham số trên `timestamptz`, cách xử lý bước theo ngày lịch có thể chịu ảnh hưởng múi giờ hiện hành, đặc biệt ở vùng có DST. Để có lịch theo tên vùng tường minh, PostgreSQL 16+ có dạng bốn tham số.

## 10. Dựng lịch qua Daylight Saving Time (DST)

Một số vùng, như `America/New_York`, thay đổi offset theo mùa. Vì thế:

- Một ngày địa phương có thể dài **23, 24 hoặc 25 giờ thực tế**.
- “Sang ngày tiếp theo lúc 00:00 địa phương” không nhất thiết là cộng chính xác 24 giờ UTC.
- Nếu ứng dụng xây lịch theo giờ địa phương, cần dùng **tên vùng múi giờ**, không chỉ một offset cố định.

### 10.1. Sinh từng nửa đêm địa phương với tên vùng (PostgreSQL 16+)

Ví dụ quanh giai đoạn chuyển sang giờ mùa hè tại New York năm 2025:

```sql
SELECT
    g.tick_at AS absolute_instant,
    g.tick_at AT TIME ZONE 'America/New_York'
        AS local_clock
FROM generate_series(
    TIMESTAMPTZ '2025-03-08 00:00:00-05',
    TIMESTAMPTZ '2025-03-11 00:00:00-04',
    INTERVAL '1 day',
    'America/New_York'
) AS g(tick_at)
ORDER BY g.tick_at;
```

Các mốc giờ địa phương mong đợi đều là **00:00** ngày 08, 09, 10, 11 tháng 3. Nhưng khoảng cách **theo thời gian tuyệt đối** giữa một số mốc có thể không bằng 24 giờ khi có chuyển đổi DST.

Tham số thứ tư xác định vùng múi giờ dùng cho tính toán bước ngày giờ. Đây là phần có ý nghĩa trong lịch theo múi giờ cụ thể, không chỉ là bộ lọc định dạng hiển thị.

### 10.2. Nếu phiên bản không hỗ trợ tham số múi giờ thứ tư

Một chiến lược rõ ràng là tạo **các ngày địa phương** rồi chuyển từng ngày sang instant theo tên vùng:

```sql
SELECT
    d.day AS local_date,
    d.day::timestamp
        AT TIME ZONE 'America/New_York'
        AS local_midnight_instant
FROM (
    SELECT DATE '2025-03-08' + n AS day
    FROM generate_series(0, 3) AS g(n)
) AS d
ORDER BY d.day;
```

Cách này tạo ngày bằng phép toán calendar (DATE + integer), rồi định nghĩa mốc nửa đêm theo vùng. Trong các tình huống có DST phức tạp, giờ địa phương nào đó có thể không tồn tại hoặc lặp lại; cần chính sách xử lý riêng khi dựng những giờ khác 00:00.

### 10.3. Tránh tự cộng 24 giờ nếu nghiệp vụ là “mỗi ngày địa phương”

Quy tắc:

> “Gửi báo cáo lúc 09:00 hàng ngày theo giờ New York”

khác:

> “Cứ mỗi 24 giờ gửi báo cáo một lần”.

Câu thứ nhất theo lịch địa phương và quy tắc DST; câu thứ hai theo khoảng thời gian tuyệt đối. Một chuỗi `INTERVAL '24 hours'` không tự thể hiện toàn bộ quy tắc lịch địa phương trong mọi vùng.

### 10.4. Ngày Việt Nam không có DST có cần quan tâm?

Với `Asia/Ho_Chi_Minh`, offset hiện hành phổ biến là +07 và không áp dụng DST như New York. Nhưng ứng dụng dùng toàn cầu vẫn cần mô hình timezone đúng; việc một thị trường không đổi giờ mùa hè không làm tất cả hệ thống khác an toàn nếu dùng offset cố định.

## 11. Sinh lịch của một tuần

Giả sử cần mọi ngày từ **thứ Hai đến Chủ nhật** của tuần chứa ngày 18/11/2026.

Trong PostgreSQL, `date_trunc('week', timestamp)` lấy mốc bắt đầu tuần theo cách xác định của PostgreSQL (thứ Hai trong ngữ cảnh sử dụng phổ biến).

```sql
WITH monday AS (
    SELECT date_trunc(
        'week',
        TIMESTAMP '2026-11-18 12:00:00'
    )::date AS week_start
)
SELECT
    m.week_start + g.n AS day,
    g.n + 1 AS iso_day_number
FROM monday AS m
CROSS JOIN generate_series(0, 6) AS g(n)
ORDER BY day;
```

Kết quả có bảy ngày từ **2026-11-16 (thứ Hai)** đến **2026-11-22 (Chủ nhật)**.

### 11.1. Lấy thứ tự ngày ISO

```sql
WITH calendar AS (
    SELECT DATE '2026-11-16' + n AS day
    FROM generate_series(0, 6) AS g(n)
)
SELECT
    day,
    EXTRACT(ISODOW FROM day)::integer AS iso_weekday
FROM calendar
ORDER BY day;
```

Theo ISO:

- Thứ Hai = 1.
- Thứ Ba = 2.
- ...
- Chủ nhật = 7.

Đây là cách tiện lợi khi muốn loại thứ Bảy và Chủ nhật.

### 11.2. Sinh chỉ các ngày thứ Hai đến thứ Sáu

```sql
WITH calendar AS (
    SELECT DATE '2026-11-16' + n AS day
    FROM generate_series(0, 6) AS g(n)
)
SELECT day
FROM calendar
WHERE EXTRACT(ISODOW FROM day) BETWEEN 1 AND 5
ORDER BY day;
```

Kết quả: 16, 17, 18, 19, 20/11/2026.

**Lưu ý:** “ngày trong tuần” chưa chắc là “ngày làm việc” của mọi quốc gia/tổ chức. Ngày lễ, lịch làm cuối tuần, ca đêm và chính sách doanh nghiệp có thể khác. Phần 14 sẽ kết hợp bảng ngày nghỉ thực tế.

## 12. Sinh lịch theo tháng và quý

### 12.1. Mốc đầu các tháng

```sql
SELECT
    m.month_start::date AS month_start
FROM generate_series(
    TIMESTAMP '2026-01-01 00:00:00',
    TIMESTAMP '2026-06-01 00:00:00',
    INTERVAL '1 month'
) AS m(month_start)
ORDER BY month_start;
```

Kết quả:

```text
2026-01-01
2026-02-01
2026-03-01
2026-04-01
2026-05-01
2026-06-01
```

Tổng cộng 6 tháng.

### 12.2. Biên kết thúc của từng tháng

```sql
SELECT
    m.month_start::date AS month_start,
    (m.month_start + INTERVAL '1 month')::date
        AS next_month_start,
    (m.month_start + INTERVAL '1 month')::date
        - m.month_start::date AS days_in_month
FROM generate_series(
    TIMESTAMP '2026-01-01',
    TIMESTAMP '2026-06-01',
    INTERVAL '1 month'
) AS m(month_start)
ORDER BY m.month_start;
```

Ta có thể dùng khoảng nửa mở:

```text
[month_start, next_month_start)
```

để lọc mọi ngày/thời điểm thuộc tháng mà không cần tìm “giây cuối cùng” của tháng.

### 12.3. Sinh theo quý

```sql
SELECT q.quarter_start::date
FROM generate_series(
    TIMESTAMP '2026-01-01',
    TIMESTAMP '2026-10-01',
    INTERVAL '3 months'
) AS q(quarter_start)
ORDER BY q.quarter_start;
```

Kết quả: 01/01, 01/04, 01/07, 01/10.

### 12.4. Cẩn trọng khi cộng tháng từ ngày 29, 30 hoặc 31

Các tháng có độ dài khác nhau. Nếu bắt đầu tại ngày 31 rồi liên tục cộng `INTERVAL '1 month'`, quy tắc điều chỉnh ngày của PostgreSQL có thể tạo các mốc không giống kỳ vọng “ngày cuối tháng” của nghiệp vụ.

Để tạo **các mốc đầu tháng**, hãy bắt đầu từ ngày 1 hoặc chuẩn hóa bằng `date_trunc('month', ...)`. Để tạo ngày cuối tháng, tính từ **đầu tháng tiếp theo trừ một ngày**, thay vì cố tăng tuần tự từ ngày 31.

## 13. Tạo lịch khung giờ cho hệ thống đặt hẹn

Giả sử một phòng cho đặt từ 09:00 đến 17:00, mỗi slot 30 phút.

### 13.1. Dùng dãy timestamp

```sql
SELECT
    s.slot_start,
    s.slot_start + INTERVAL '30 minutes' AS slot_end
FROM generate_series(
    TIMESTAMP '2026-11-16 09:00:00',
    TIMESTAMP '2026-11-16 16:30:00',
    INTERVAL '30 minutes'
) AS s(slot_start)
ORDER BY s.slot_start;
```

Kết quả có **16 slot**, slot cuối là `[16:30,17:00)`.

### 13.2. Dùng dãy số để dựng slot

Một cách khác không cần tự nhập mốc 16:30:

```sql
SELECT
    TIMESTAMP '2026-11-16 09:00:00'
        + g.n * INTERVAL '30 minutes' AS slot_start,
    TIMESTAMP '2026-11-16 09:00:00'
        + (g.n + 1) * INTERVAL '30 minutes' AS slot_end
FROM generate_series(0, 15) AS g(n)
ORDER BY g.n;
```

Mẫu này thuận tiện khi biết số slot cần tạo. Với `n = 0`, slot đầu [09:00,09:30); với `n = 15`, slot cuối [16:30,17:00).

### 13.3. Kết hợp ngày và giờ thành lịch tuần

```sql
WITH workdays AS (
    SELECT DATE '2026-11-16' + d.n AS workday
    FROM generate_series(0, 4) AS d(n)
)
SELECT
    w.workday,
    w.workday::timestamp
        + (TIME '09:00' - TIME '00:00')
        + s.n * INTERVAL '30 minutes' AS slot_start
FROM workdays AS w
CROSS JOIN generate_series(0, 15) AS s(n)
ORDER BY w.workday, s.n;
```

Câu trên dùng biểu thức ngày giờ để tạo 16 slot bắt đầu mỗi ngày trong năm ngày làm việc. Một cách dễ đọc hơn trong SQL ứng dụng là:

```sql
WITH workdays AS (
    SELECT DATE '2026-11-16' + d.n AS workday
    FROM generate_series(0, 4) AS d(n)
)
SELECT
    w.workday,
    w.workday::timestamp
        + INTERVAL '9 hours'
        + s.n * INTERVAL '30 minutes' AS slot_start,
    w.workday::timestamp
        + INTERVAL '9 hours'
        + (s.n + 1) * INTERVAL '30 minutes' AS slot_end
FROM workdays AS w
CROSS JOIN generate_series(0, 15) AS s(n)
ORDER BY w.workday, s.n;
```

Hai bảng nguồn tạo **5 × 16 = 80 slot**.

Đây là cách hữu ích để tạo UI lịch trống, nhưng các slot chỉ là **khung thời gian ứng viên**. Muốn biết slot nào thật sự khả dụng, phải ghép với dữ liệu đặt lịch, lịch nghỉ, quyền sử dụng và quy tắc ngăn chồng lấn.

### 13.4. Mốc giờ và múi giờ trong hệ thống đặt hẹn

Ở các ví dụ trên, `slot_start`/`slot_end` là kiểu `timestamp without time zone`. Nếu cần một thời điểm toàn cầu, chuyển chúng theo **tên vùng**:

```sql
SELECT
    TIMESTAMP '2026-11-16 09:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
        AS instant_of_local_9am;
```

Không giả định 09:00 của người dùng ở hai vùng múi giờ là cùng một thời điểm.

## 14. Tạo ngày làm việc, loại thứ Bảy/Chủ nhật và ngày lễ

Dãy sinh có thể được lọc bằng các quy tắc nghiệp vụ.

### 14.1. Bảng ngày nghỉ của tổ chức

Trong database lab:

```sql
CREATE SCHEMA IF NOT EXISTS series_lab;

CREATE TABLE series_lab.holidays (
    holiday_date date PRIMARY KEY,
    description text NOT NULL
);

INSERT INTO series_lab.holidays(holiday_date, description)
VALUES (
    DATE '2026-11-17',
    'Ngày nghỉ giả định của đơn vị để thực hành'
);
```

Đây là **ngày nghỉ giả định**, không phải khẳng định ngày 17/11 là ngày nghỉ chính thức ở Việt Nam hoặc nơi khác.

### 14.2. Sinh lịch làm việc trong tuần

```sql
WITH calendar AS (
    SELECT DATE '2026-11-16' + n AS day
    FROM generate_series(0, 6) AS g(n)
)
SELECT
    c.day
FROM calendar AS c
LEFT JOIN series_lab.holidays AS h
    ON h.holiday_date = c.day
WHERE EXTRACT(ISODOW FROM c.day) BETWEEN 1 AND 5
  AND h.holiday_date IS NULL
ORDER BY c.day;
```

Kết quả theo dữ liệu lab:

```text
2026-11-16
2026-11-18
2026-11-19
2026-11-20
```

Quy trình:

1. Sinh bảy ngày theo lịch.
2. Chỉ giữ ngày có ISO weekday từ 1 đến 5.
3. `LEFT JOIN` bảng ngày nghỉ.
4. Chỉ giữ ngày không có hàng ngày nghỉ khớp.

### 14.3. Phân biệt cuối tuần và ngày nghỉ

Nếu doanh nghiệp làm việc cả thứ Bảy, điều kiện `ISODOW BETWEEN 1 AND 5` không còn đúng. Một bảng calendar nghiệp vụ có thể cần các cột như `is_working_day`, `work_shift`, `region_code` và quy tắc theo tổ chức.

`generate_series` tạo **khung ngày cơ sở**, không tự biết lịch nghỉ lễ, ngày bù hoặc ca làm đặc biệt của từng nơi.

## 15. Lấp ngày không có giao dịch bằng LEFT JOIN

Đây là một trong những ứng dụng thực tế quan trọng nhất của `generate_series`.

Giả sử bảng doanh số chỉ có hàng vào những ngày phát sinh giao dịch:

```text
2026-11-14: 2 giao dịch
2026-11-15: không có giao dịch
2026-11-16: 1 giao dịch
2026-11-17: không có giao dịch
2026-11-18: 2 giao dịch
2026-11-19: không có giao dịch
2026-11-20: không có giao dịch
```

Nếu chỉ `GROUP BY sold_on` trên bảng giao dịch, các ngày trống **không xuất hiện**. Biểu đồ có thể hiểu nhầm rằng dữ liệu bị thiếu hoặc bỏ qua một ngày.

### 15.1. Bảng doanh số mẫu

Trong schema lab đã tạo:

```sql
CREATE TABLE series_lab.sales (
    sale_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sold_on date NOT NULL,
    amount numeric(12,2) NOT NULL CHECK (amount >= 0)
);

INSERT INTO series_lab.sales(sold_on, amount)
VALUES
    (DATE '2026-11-14', 500.00),
    (DATE '2026-11-14', 200.00),
    (DATE '2026-11-16', 700.00),
    (DATE '2026-11-18', 100.00),
    (DATE '2026-11-18', 150.00);
```

### 15.2. Chỉ GROUP BY sẽ bỏ qua ngày trống

```sql
SELECT
    sold_on,
    COUNT(*) AS sale_count,
    SUM(amount) AS revenue
FROM series_lab.sales
GROUP BY sold_on
ORDER BY sold_on;
```

Kết quả chỉ có ba ngày:

| sold_on | sale_count | revenue |
|---|---:|---:|
| 2026-11-14 | 2 | 700.00 |
| 2026-11-16 | 1 | 700.00 |
| 2026-11-18 | 2 | 250.00 |

Không có 15, 17, 19, 20/11.

### 15.3. Sinh lịch rồi LEFT JOIN doanh số

```sql
WITH calendar AS (
    SELECT DATE '2026-11-14' + n AS day
    FROM generate_series(0, 6) AS g(n)
)
SELECT
    c.day,
    COUNT(s.sale_id) AS sale_count,
    COALESCE(SUM(s.amount), 0) AS revenue
FROM calendar AS c
LEFT JOIN series_lab.sales AS s
    ON s.sold_on = c.day
GROUP BY c.day
ORDER BY c.day;
```

Kết quả đầy đủ:

| day | sale_count | revenue |
|---|---:|---:|
| 2026-11-14 | 2 | 700.00 |
| 2026-11-15 | 0 | 0 |
| 2026-11-16 | 1 | 700.00 |
| 2026-11-17 | 0 | 0 |
| 2026-11-18 | 2 | 250.00 |
| 2026-11-19 | 0 | 0 |
| 2026-11-20 | 0 | 0 |

Vì sao hoạt động?

- `calendar` **luôn có bảy ngày**.
- `LEFT JOIN` bảo toàn mỗi ngày của calendar.
- Nếu ngày đó không có giao dịch, các cột `s.*` trở thành NULL.
- `COUNT(s.sale_id)` trả 0 vì `sale_id` là khóa NOT NULL của hàng giao dịch thật.
- `SUM(s.amount)` trên nhóm không có giá trị giao dịch thực tế trả NULL; `COALESCE(...,0)` hiển thị thành 0.

### 15.4. Bẫy COUNT(*) trong báo cáo ngày trống

Nếu thay:

```sql
COUNT(s.sale_id)
```

bằng:

```sql
COUNT(*)
```

thì ngày không có doanh số vẫn có **một hàng NULL mở rộng** của LEFT JOIN, nên `COUNT(*)` có thể trả **1**, không phải 0.

Nguyên tắc: đếm cột khóa không NULL của bảng bên phải khi muốn đếm những bản ghi thật sự khớp.

## 16. Đặt điều kiện trong ON hay WHERE khi ghép lịch

Giả sử muốn báo cáo doanh số từng ngày nhưng chỉ tính những giao dịch có `amount >= 200`. Ta vẫn muốn **mọi ngày xuất hiện**, kể cả ngày không có giao dịch đạt ngưỡng.

Cách đúng thường là:

```sql
WITH calendar AS (
    SELECT DATE '2026-11-14' + n AS day
    FROM generate_series(0, 6) AS g(n)
)
SELECT
    c.day,
    COUNT(s.sale_id) AS qualifying_sales,
    COALESCE(SUM(s.amount), 0) AS qualifying_revenue
FROM calendar AS c
LEFT JOIN series_lab.sales AS s
    ON s.sold_on = c.day
   AND s.amount >= 200
GROUP BY c.day
ORDER BY c.day;
```

Điều kiện `s.amount >= 200` ở `ON` quyết định **giao dịch nào được ghép**, còn các ngày vẫn được giữ.

### 16.1. Nếu đặt ở WHERE sẽ ra sao?

```sql
WITH calendar AS (
    SELECT DATE '2026-11-14' + n AS day
    FROM generate_series(0, 6) AS g(n)
)
SELECT
    c.day,
    COUNT(s.sale_id) AS qualifying_sales
FROM calendar AS c
LEFT JOIN series_lab.sales AS s
    ON s.sold_on = c.day
WHERE s.amount >= 200
GROUP BY c.day
ORDER BY c.day;
```

Các ngày không có giao dịch đạt ngưỡng sẽ **biến mất**, bởi `NULL >= 200` không TRUE.

Một ngày có giao dịch nhưng toàn giao dịch dưới ngưỡng cũng bị loại; nó không được tự thay bằng một hàng NULL sau khi `WHERE` lọc, vì phép JOIN đã hoàn thành trước đó theo ngữ nghĩa logic.

### 16.2. Cách khác: tổng hợp có FILTER

Nếu cần đồng thời **tổng số giao dịch** và **số giao dịch đạt ngưỡng**, dùng `FILTER`:

```sql
WITH calendar AS (
    SELECT DATE '2026-11-14' + n AS day
    FROM generate_series(0, 6) AS g(n)
)
SELECT
    c.day,
    COUNT(s.sale_id) AS all_sales,
    COUNT(s.sale_id)
      FILTER (WHERE s.amount >= 200) AS qualifying_sales
FROM calendar AS c
LEFT JOIN series_lab.sales AS s
    ON s.sold_on = c.day
GROUP BY c.day
ORDER BY c.day;
```

Bộ lọc của aggregate không loại cả ngày khỏi báo cáo.

## 17. Lấp khoảng thời gian có TIMESTAMPTZ mà vẫn dùng được index

Với hệ thống thực tế, sự kiện thường lưu dưới dạng:

```text
event_id | occurred_at (timestamptz)
```

Muốn báo cáo theo **ngày địa phương**, cần xác định vùng múi giờ của nghiệp vụ. Không nên tự ép `occurred_at::date` mà bỏ qua việc session có thể có `TimeZone` khác nhau.

### 17.1. Bảng sự kiện mẫu

```sql
CREATE TABLE series_lab.events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at timestamptz NOT NULL,
    event_type text NOT NULL
);

INSERT INTO series_lab.events(occurred_at, event_type)
VALUES
    (TIMESTAMPTZ '2026-11-14 23:30:00+07', 'login'),
    (TIMESTAMPTZ '2026-11-15 00:15:00+07', 'login'),
    (TIMESTAMPTZ '2026-11-15 12:00:00+07', 'purchase'),
    (TIMESTAMPTZ '2026-11-17 09:00:00+07', 'login');
```

### 17.2. Dùng ranh giới ngày địa phương để LEFT JOIN

```sql
WITH calendar AS (
    SELECT DATE '2026-11-14' + n AS local_day
    FROM generate_series(0, 4) AS g(n)
)
SELECT
    c.local_day,
    COUNT(e.event_id) AS event_count
FROM calendar AS c
LEFT JOIN series_lab.events AS e
    ON e.occurred_at >= (
        c.local_day::timestamp
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
   AND e.occurred_at < (
        (c.local_day + 1)::timestamp
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
GROUP BY c.local_day
ORDER BY c.local_day;
```

Kết quả theo dữ liệu mẫu:

| local_day | event_count |
|---|---:|
| 2026-11-14 | 1 |
| 2026-11-15 | 2 |
| 2026-11-16 | 0 |
| 2026-11-17 | 1 |
| 2026-11-18 | 0 |

Ưu điểm của hai điều kiện:

```sql
e.occurred_at >= day_start_instant
AND e.occurred_at < next_day_start_instant
```

là ranh giới rõ và thường thuận lợi cho index B-tree trên cột `occurred_at` khi kế hoạch truy vấn phù hợp.

### 17.3. Vì sao không cố định một ngày = 24 giờ UTC?

Ở vùng có DST, hai nửa đêm địa phương liên tiếp có thể cách nhau 23 hoặc 25 giờ tuyệt đối. Tính **đầu ngày hiện tại** và **đầu ngày tiếp theo** bằng tên vùng giúp biểu diễn đúng tập thời điểm của ngày địa phương, thay vì lấy đầu ngày rồi luôn cộng chính xác 24 giờ tuyệt đối.

### 17.4. Index cho sự kiện thời gian

Trong lab có thể tạo:

```sql
CREATE INDEX idx_series_lab_events_occurred_at
ON series_lab.events(occurred_at);
```

Không phải mọi truy vấn đều dùng index khi bảng chỉ có vài hàng. Để đánh giá đúng cần `EXPLAIN` và workload đại diện.

## 18. Sinh từng giờ và điền bucket không có sự kiện

Giả sử muốn thống kê sự kiện theo từng giờ từ 09:00 đến trước 13:00 theo giờ Việt Nam trong một ngày cụ thể.

### 18.1. Sinh các mốc giờ

```sql
WITH hours AS (
    SELECT
        TIMESTAMPTZ '2026-11-17 09:00:00+07'
          + n * INTERVAL '1 hour' AS hour_start
    FROM generate_series(0, 3) AS g(n)
)
SELECT
    hour_start,
    hour_start + INTERVAL '1 hour' AS hour_end
FROM hours
ORDER BY hour_start;
```

Tạo bốn khoảng:

```text
[09:00,10:00)
[10:00,11:00)
[11:00,12:00)
[12:00,13:00)
```

### 18.2. Ghép từng bucket với sự kiện

```sql
WITH hours AS (
    SELECT
        TIMESTAMPTZ '2026-11-17 09:00:00+07'
          + n * INTERVAL '1 hour' AS hour_start
    FROM generate_series(0, 3) AS g(n)
)
SELECT
    h.hour_start,
    COUNT(e.event_id) AS event_count
FROM hours AS h
LEFT JOIN series_lab.events AS e
    ON e.occurred_at >= h.hour_start
   AND e.occurred_at < h.hour_start + INTERVAL '1 hour'
GROUP BY h.hour_start
ORDER BY h.hour_start;
```

Các bucket trống vẫn được trả ra với `event_count = 0`. Với dữ liệu sample, bucket đầu có một event 09:00, các bucket sau không có event.

### 18.3. Bước thời gian phải phù hợp mục tiêu

Nếu chỉ cần mốc mỗi giờ, sinh từng phút rồi tổng hợp sẽ tạo nhiều hàng trung gian không cần thiết. Hãy dùng bước nhảy tương ứng với độ phân giải báo cáo: 1 ngày, 1 giờ, 15 phút hoặc 30 phút.

Nếu cần một khung thời gian có hàng triệu bucket, việc sinh tất cả trực tiếp trong một request sẽ tốn CPU/bộ nhớ và truyền dữ liệu; hãy giới hạn khoảng truy vấn và cân nhắc bảng tổng hợp được tính trước.

## 19. LATERAL: sinh dãy riêng cho mỗi hàng của một bảng

`generate_series` không chỉ nhận hằng số. Nó có thể nhận **giá trị từ một hàng đang được xử lý**.

Giả sử mỗi nhân viên có thời gian được phân công làm một nhiệm vụ:

| employee_id | start_date | end_date |
|---:|---|---|
| 1 | 2026-11-14 | 2026-11-16 |
| 2 | 2026-11-18 | 2026-11-19 |

Muốn mở rộng thành:

```text
employee 1 -> 14, 15, 16
employee 2 -> 18, 19
```

### 19.1. Tạo bảng công việc mẫu

```sql
CREATE TABLE series_lab.assignments (
    assignment_id bigint PRIMARY KEY,
    employee_id bigint NOT NULL,
    start_date date NOT NULL,
    end_date date NOT NULL,
    CHECK (end_date >= start_date)
);

INSERT INTO series_lab.assignments
    (assignment_id, employee_id, start_date, end_date)
VALUES
    (1, 1, DATE '2026-11-14', DATE '2026-11-16'),
    (2, 2, DATE '2026-11-18', DATE '2026-11-19');
```

### 19.2. CROSS JOIN LATERAL

```sql
SELECT
    a.assignment_id,
    a.employee_id,
    a.start_date + g.n AS assigned_day
FROM series_lab.assignments AS a
CROSS JOIN LATERAL generate_series(
    0,
    a.end_date - a.start_date
) AS g(n)
ORDER BY a.assignment_id, assigned_day;
```

Kết quả:

| assignment_id | employee_id | assigned_day |
|---:|---:|---|
| 1 | 1 | 2026-11-14 |
| 1 | 1 | 2026-11-15 |
| 1 | 1 | 2026-11-16 |
| 2 | 2 | 2026-11-18 |
| 2 | 2 | 2026-11-19 |

### 19.3. Vì sao cần LATERAL?

`LATERAL` cho phép hàm/nguồn nằm bên phải tham chiếu các cột của nguồn bên trái. Ở ví dụ này, hai đối số của `generate_series` phụ thuộc **từng hàng assignments**:

```sql
a.start_date
a.end_date
```

Với các hàm trong `FROM`, PostgreSQL cho phép tham chiếu cột từ nguồn trước ngay cả khi từ khóa `LATERAL` được lược bỏ trong một số trường hợp. Nhưng viết tường minh `CROSS JOIN LATERAL` thường giúp người đọc nhận ra rằng **mỗi hàng cha sinh một dãy riêng**.

### 19.4. LATERAL không biến mỗi hàng cha thành một hàng duy nhất

Assignment 1 sinh ba ngày nên xuất hiện **ba hàng**; assignment 2 sinh hai ngày nên xuất hiện **hai hàng**.

Nếu kết quả cần “một hàng mỗi assignment”, phải dùng aggregate hoặc xây dựng mảng JSON/ARRAY tương ứng, thay vì chỉ CROSS JOIN LATERAL rồi giả định số hàng không đổi.

## 20. CROSS JOIN LATERAL và LEFT JOIN LATERAL khác nhau khi dãy rỗng

Khi cột đầu/cuối của một hàng không tạo ra giá trị nào, `CROSS JOIN LATERAL` **không trả hàng cha đó**.

Trong một báo cáo, đôi khi vẫn cần giữ tất cả đối tượng, kể cả đối tượng không có khoảng thời gian hợp lệ để sinh lịch.

### 20.1. Dữ liệu minh họa bằng VALUES

```sql
WITH tasks(task_id, start_date, end_date) AS (
    VALUES
        (1, DATE '2026-11-14', DATE '2026-11-16'),
        (2, DATE '2026-11-20', DATE '2026-11-19')
)
SELECT
    t.task_id,
    t.start_date + g.n AS day
FROM tasks AS t
CROSS JOIN LATERAL generate_series(
    0,
    t.end_date - t.start_date
) AS g(n)
ORDER BY t.task_id, day;
```

Task 2 có end trước start, khiến `generate_series(0,-1)` tạo **0 hàng**. CROSS JOIN LATERAL loại task 2 khỏi kết quả.

### 20.2. LEFT JOIN LATERAL để giữ task

```sql
WITH tasks(task_id, start_date, end_date) AS (
    VALUES
        (1, DATE '2026-11-14', DATE '2026-11-16'),
        (2, DATE '2026-11-20', DATE '2026-11-19')
)
SELECT
    t.task_id,
    t.start_date + g.n AS day
FROM tasks AS t
LEFT JOIN LATERAL generate_series(
    0,
    t.end_date - t.start_date
) AS g(n) ON TRUE
ORDER BY t.task_id, day NULLS LAST;
```

Lần này task 2 vẫn xuất hiện **một hàng với day NULL**, bởi LEFT JOIN bảo toàn hàng trái.

**Điểm cần nhớ:** đây là ví dụ cố ý có khoảng sai để giải thích hình thức JOIN. Trong schema production, `CHECK(end_date >= start_date)` thường nên ngăn dữ liệu bất hợp lệ khi bài toán không cho phép khoảng rỗng/ngược.

### 20.3. Đếm ngày từ LEFT JOIN LATERAL

```sql
WITH tasks(task_id, start_date, end_date) AS (
    VALUES
        (1, DATE '2026-11-14', DATE '2026-11-16'),
        (2, DATE '2026-11-20', DATE '2026-11-19')
)
SELECT
    t.task_id,
    COUNT(g.n) AS generated_days
FROM tasks AS t
LEFT JOIN LATERAL generate_series(
    0,
    t.end_date - t.start_date
) AS g(n) ON TRUE
GROUP BY t.task_id
ORDER BY t.task_id;
```

Kết quả:

```text
task_id=1 -> generated_days=3
task_id=2 -> generated_days=0
```

Không dùng `COUNT(*)` nếu muốn task 2 có số 0, vì hàng NULL mở rộng vẫn được COUNT(*) đếm thành 1.

## 21. CROSS JOIN để tạo tổ hợp lịch × tài nguyên

Giả sử có 3 phòng và muốn dựng lịch cho 7 ngày. Ta có thể tạo **tất cả cặp (phòng, ngày)**:

```sql
WITH rooms(room_id) AS (
    VALUES (101), (102), (103)
),
calendar AS (
    SELECT DATE '2026-11-14' + g.n AS day
    FROM generate_series(0, 6) AS g(n)
)
SELECT
    r.room_id,
    c.day
FROM rooms AS r
CROSS JOIN calendar AS c
ORDER BY r.room_id, c.day;
```

Kết quả gồm **21 hàng**: mỗi phòng có bảy ngày.

Đây là công cụ rất hữu ích để tạo skeleton của báo cáo:

```text
Resource × Calendar × Slot
```

Nhưng số hàng tăng theo **tích số lượng phần tử**. Nếu tạo một ma trận rất lớn giữa nhiều phòng, nhiều ngày và nhiều khung giờ, truy vấn có thể sinh ra hàng triệu hàng trước khi kết hợp dữ liệu thật.

### 21.1. Ghép với bảng availability/booking

Ví dụ dạng khuôn mẫu:

```sql
WITH rooms(room_id) AS (
    VALUES (101), (102)
),
calendar AS (
    SELECT DATE '2026-11-14' + n AS day
    FROM generate_series(0, 6) AS g(n)
)
SELECT
    r.room_id,
    c.day,
    COUNT(b.booking_id) AS bookings
FROM rooms AS r
CROSS JOIN calendar AS c
LEFT JOIN room_bookings AS b
    ON b.room_id = r.room_id
   AND b.booking_date = c.day
GROUP BY r.room_id, c.day
ORDER BY r.room_id, c.day;
```

Bảng `room_bookings` ở đây là **khuôn mẫu**, chưa được tạo trong lab. Với bảng thật, cần thiết kế khóa ngoại, index, timezone, status và giới hạn ngày theo nghiệp vụ.

Mục tiêu của cách viết là:

1. Dựng đủ mọi cặp phòng/ngày bằng CROSS JOIN.
2. LEFT JOIN sự kiện thật để giữ những cặp chưa có booking.
3. Dùng COUNT trên khóa của booking để đếm chính xác số bản ghi.

## 22. WITH ORDINALITY: giữ số thứ tự hàng được sinh ra

`generate_series` tự trả giá trị, nhưng đôi khi ta cần cả **vị trí thứ mấy trong kết quả**.

```sql
SELECT
    s.value,
    s.ordinality
FROM generate_series(10, 20, 5)
WITH ORDINALITY AS s(value, ordinality)
ORDER BY s.ordinality;
```

Kết quả:

| value | ordinality |
|---:|---:|
| 10 | 1 |
| 15 | 2 |
| 20 | 3 |

`ordinality` là thứ tự hàng được sinh ra, bắt đầu từ **1**, không phải giá trị của dãy hoặc hiệu số so với start.

### 22.1. Khi nào hữu ích?

- Đánh số một chuỗi khung giờ trong ngày.
- Tạo `sequence_no` trong dữ liệu mô phỏng.
- Liên kết phần tử với thứ tự hiển thị.
- Tạo mốc bắt đầu từ số 0 nhưng muốn thứ tự trình bày bắt đầu từ 1.

Ví dụ:

```sql
SELECT
    s.ordinality AS slot_number,
    TIMESTAMP '2026-11-16 09:00'
      + (s.ordinality - 1) * INTERVAL '30 minutes' AS slot_start
FROM generate_series(0, 5)
WITH ORDINALITY AS s(n, ordinality)
ORDER BY slot_number;
```

Trong ví dụ này `ordinality` tăng từ 1 đến 6, còn `n` tăng từ 0 đến 5. Cả hai mô tả cùng thứ tự nhưng có **gốc chỉ số khác nhau**.

## 23. Sinh dữ liệu mẫu có cấu trúc bằng INSERT ... SELECT

Một cách sử dụng phổ biến là sinh hàng loạt dữ liệu lab để thử giao diện, truy vấn, index và xử lý phân trang.

### 23.1. Tạo bảng tài khoản demo

```sql
CREATE TABLE series_lab.demo_accounts (
    account_id integer PRIMARY KEY,
    team_id integer NOT NULL,
    display_name text NOT NULL,
    created_at timestamptz NOT NULL
);
```

### 23.2. Sinh 100 tài khoản theo quy luật cố định

```sql
INSERT INTO series_lab.demo_accounts(
    account_id,
    team_id,
    display_name,
    created_at
)
SELECT
    g.n AS account_id,
    (g.n % 5) + 1 AS team_id,
    format(
        'demo_user_%s',
        lpad(g.n::text, 4, '0')
    ) AS display_name,
    TIMESTAMPTZ '2026-11-14 00:00:00+07'
        + g.n * INTERVAL '5 minutes' AS created_at
FROM generate_series(1, 100) AS g(n);
```

Ý nghĩa:

- `g.n` tạo ID từ 1 tới 100.
- `g.n % 5` tạo số dư 0–4, cộng 1 thành team 1–5.
- `lpad` thêm số 0 phía trước tên demo, ví dụ `demo_user_0001`.
- `created_at` tăng từng bước 5 phút.
- Dữ liệu sinh theo quy luật **có thể tái tạo**, thuận lợi khi so sánh kết quả test.

Kiểm tra:

```sql
SELECT
    COUNT(*) AS total_accounts,
    MIN(account_id) AS first_id,
    MAX(account_id) AS last_id,
    COUNT(DISTINCT team_id) AS team_count
FROM series_lab.demo_accounts;
```

Kết quả dự kiến trong bảng lab mới: tổng 100, ID đầu 1, ID cuối 100, có 5 team.

### 23.3. Thận trọng khi chạy INSERT nhiều lần

Chạy lại câu INSERT này trên bảng đã chứa các ID 1–100 sẽ gặp **lỗi khóa chính trùng**. Đó là hành vi đúng của constraint, không phải generate_series sinh sai.

Có thể dùng `ON CONFLICT` nếu kịch bản test thực sự yêu cầu idempotent insert:

```sql
INSERT INTO series_lab.demo_accounts(
    account_id, team_id, display_name, created_at
)
SELECT
    g.n,
    (g.n % 5) + 1,
    format('demo_user_%s', lpad(g.n::text, 4, '0')),
    TIMESTAMPTZ '2026-11-14 00:00:00+07'
      + g.n * INTERVAL '5 minutes'
FROM generate_series(1, 100) AS g(n)
ON CONFLICT (account_id) DO NOTHING;
```

Nhưng `DO NOTHING` **không sửa** các hàng demo đã có với giá trị khác mong muốn. Nếu cần test lặp lại chính xác, thiết kế quy trình reset hoặc upsert dữ liệu lab có kiểm soát.

### 23.4. Không tạo ID tùy tiện trên bảng production

Trong hệ thống có sequence/identity tự động, việc chèn ID cố định có thể xung đột với ID hiện có hoặc làm lệch kế hoạch phân phối ID. Mẫu trên chỉ dành cho **bảng lab mới**. Với bảng production, ưu tiên cơ chế ID của schema và quy trình tạo dữ liệu kiểm thử ở môi trường tách biệt.

## 24. Tạo dữ liệu mẫu liên quan bằng CROSS JOIN và LATERAL

Muốn sinh nhiều bài đăng hoặc nhiệm vụ cho từng tài khoản demo, không cần viết 100 câu INSERT.

### 24.1. Bảng nhiệm vụ mẫu

```sql
CREATE TABLE series_lab.demo_tasks (
    task_id bigint PRIMARY KEY,
    account_id integer NOT NULL
        REFERENCES series_lab.demo_accounts(account_id),
    task_number integer NOT NULL,
    task_title text NOT NULL,
    created_at timestamptz NOT NULL,
    UNIQUE (account_id, task_number)
);
```

### 24.2. Mỗi tài khoản có 3 nhiệm vụ

```sql
INSERT INTO series_lab.demo_tasks(
    task_id,
    account_id,
    task_number,
    task_title,
    created_at
)
SELECT
    a.account_id::bigint * 10 + g.n AS task_id,
    a.account_id,
    g.n,
    format('Task %s of account %s', g.n, a.account_id),
    a.created_at + g.n * INTERVAL '1 hour'
FROM series_lab.demo_accounts AS a
CROSS JOIN generate_series(1, 3) AS g(n);
```

Nếu bảng accounts lab có 100 tài khoản, câu này tạo **300 nhiệm vụ**.

Tại sao ID được tính bằng `account_id * 10 + task_number`?

- Với mỗi account ID 1–100 và task_number 1–3, các ID được phân biệt trong mẫu hiện tại.
- Đây **không phải chiến lược cấp ID tổng quát** khi task_number có thể tăng vượt 9 hoặc account ID có giá trị khác dự kiến.
- Trong hệ thống thật, nên dùng khóa tự sinh hoặc cơ chế ID đã thiết kế, không phụ thuộc công thức giả định.

### 24.3. Số nhiệm vụ khác nhau theo tài khoản

Giả sử muốn mỗi tài khoản có từ 1 đến 4 nhiệm vụ, theo một quy tắc deterministic:

```sql
SELECT
    a.account_id,
    g.task_number
FROM series_lab.demo_accounts AS a
CROSS JOIN LATERAL generate_series(
    1,
    (a.account_id % 4) + 1
) AS g(task_number)
ORDER BY a.account_id, g.task_number;
```

Mỗi account sinh một số lượng khác nhau nhưng có thể tái tạo từ `account_id`.

**LATERAL** hữu ích vì `stop` phụ thuộc một giá trị của từng hàng account. Một lần nữa, cần giới hạn đầu vào để không vô tình sinh quá nhiều bản ghi.

## 25. Có nên dùng random() để tạo dữ liệu mẫu?

`random()` có thể hữu ích để thử phân bố dữ liệu, nhưng không giống dữ liệu sinh deterministic.

Ví dụ:

```sql
SELECT
    g.n AS sample_id,
    floor(random() * 100)::integer AS score
FROM generate_series(1, 10) AS g(n);
```

Điểm cần biết:

- `random()` sinh giá trị giả ngẫu nhiên cho từng lần gọi; kết quả có thể khác giữa các lần chạy.
- `floor(random() * 100)::integer` thường tạo giá trị từ 0 đến 99.
- Mẫu ngẫu nhiên có thể **trùng giá trị**; không dùng random đơn giản làm khóa chính nếu cần bảo đảm duy nhất.
- Việc thử lỗi và tái hiện dữ liệu khó hơn nếu mọi lần chạy sinh bộ dữ liệu khác.

### 25.1. Nếu muốn kết quả có thể lặp lại

PostgreSQL hỗ trợ `setseed()` để đặt seed cho bộ sinh ngẫu nhiên dùng bởi một số hàm như `random()` trong session:

```sql
-- Thực hành trong session lab riêng.
SELECT setseed(0.42);

SELECT
    n,
    random() AS pseudo_random_value
FROM generate_series(1, 5) AS g(n)
ORDER BY n;
```

Tuy nhiên:

- Seed ảnh hưởng trạng thái sinh ngẫu nhiên của connection/session, nên cần kiểm soát khi dùng connection pool.
- Khi truy vấn có nhiều nhánh hoặc thay đổi kế hoạch thực thi, **không nên phụ thuộc** vào việc từng hàng luôn nhận cùng một giá trị random ở mọi cách viết truy vấn.
- Nếu cần dữ liệu **tái tạo chính xác theo khóa hàng**, thường dùng quy luật deterministic hoặc công cụ tạo fixture có seed được quản lý rõ ràng.

Một bộ fixture ổn định rất quan trọng khi kiểm tra regression và so sánh hiệu năng.

## 26. Tạo bộ dữ liệu cho kiểm thử thống kê

`generate_series` có thể sinh các nhóm có phân bố kiểm soát, giúp kiểm tra các trường hợp:

- Nhóm có 0 giao dịch.
- Nhóm có 1 giao dịch.
- Nhóm có nhiều giao dịch.
- Khoảng thời gian có ngày trống xen kẽ.
- Số lượng hàng lớn hơn nhiều so với dữ liệu phát triển hằng ngày.

Ví dụ sinh 20 hàng với nhóm 1–4 và giá trị đơn giản:

```sql
WITH demo AS (
    SELECT
        n AS record_id,
        (n % 4) + 1 AS group_id,
        n * 10 AS amount
    FROM generate_series(1, 20) AS g(n)
)
SELECT
    group_id,
    COUNT(*) AS row_count,
    SUM(amount) AS total_amount
FROM demo
GROUP BY group_id
ORDER BY group_id;
```

Không cần tạo bảng thật nếu mục tiêu chỉ là thực hành các phép `GROUP BY`/`SUM`.

### 26.1. Test phép JOIN bằng các nhóm giả

```sql
WITH groups(group_id) AS (
    VALUES (1), (2), (3), (4), (5)
),
records AS (
    SELECT
        n AS record_id,
        (n % 4) + 1 AS group_id
    FROM generate_series(1, 20) AS g(n)
)
SELECT
    g.group_id,
    COUNT(r.record_id) AS records_count
FROM groups AS g
LEFT JOIN records AS r
    ON r.group_id = g.group_id
GROUP BY g.group_id
ORDER BY g.group_id;
```

Ở đây các bản ghi demo chỉ thuộc nhóm 1–4; nhóm 5 vẫn được hiển thị với count = 0. Đây là cách rất nhanh để thực hành **gap filling** mà không cần chèn dữ liệu vào database.

## 27. Tạo lịch theo tháng và ghép với dữ liệu tổng hợp

Giả sử cần **đủ 12 tháng của năm 2026**, kể cả tháng không có doanh số.

### 27.1. Sinh 12 mốc đầu tháng

```sql
WITH months AS (
    SELECT
        m.month_start::date AS month_start,
        (m.month_start + INTERVAL '1 month')::date
            AS next_month_start
    FROM generate_series(
        TIMESTAMP '2026-01-01',
        TIMESTAMP '2026-12-01',
        INTERVAL '1 month'
    ) AS m(month_start)
)
SELECT *
FROM months
ORDER BY month_start;
```

Có đúng **12 hàng**, một hàng cho mỗi tháng.

### 27.2. LEFT JOIN doanh số theo ranh giới tháng

```sql
WITH months AS (
    SELECT
        m.month_start::date AS month_start,
        (m.month_start + INTERVAL '1 month')::date
            AS next_month_start
    FROM generate_series(
        TIMESTAMP '2026-01-01',
        TIMESTAMP '2026-12-01',
        INTERVAL '1 month'
    ) AS m(month_start)
)
SELECT
    mo.month_start,
    COUNT(s.sale_id) AS sale_count,
    COALESCE(SUM(s.amount), 0) AS revenue
FROM months AS mo
LEFT JOIN series_lab.sales AS s
    ON s.sold_on >= mo.month_start
   AND s.sold_on < mo.next_month_start
GROUP BY mo.month_start
ORDER BY mo.month_start;
```

Với dữ liệu sales ở phần 15, chỉ **tháng 11** có giao dịch, các tháng còn lại xuất hiện với giá trị 0.

Điểm quan trọng:

- So sánh với **đầu tháng và đầu tháng tiếp theo**, không dựa vào số ngày cố định của tháng.
- Đặt điều kiện ở `ON` để giữ tháng không có giao dịch.
- Ưu tiên range predicate trên cột ngày nếu muốn tận dụng index thích hợp, thay vì ép từng hàng thành chuỗi tháng.
- Có thể dùng `GROUP BY date_trunc('month',...)` trong nguồn dữ liệu riêng rồi LEFT JOIN với lịch, tùy hiệu năng và thiết kế.

## 28. Sinh dãy trong hàm hoặc view tái sử dụng

Một ứng dụng có thể lặp đi lặp lại logic tạo calendar. Có thể đóng gói thành hàm SQL nếu cần, với phạm vi rõ ràng.

### 28.1. Hàm tạo ngày nửa mở

Trong database lab:

```sql
CREATE FUNCTION series_lab.calendar_days(
    p_start date,
    p_end_exclusive date
)
RETURNS TABLE(day date)
LANGUAGE sql
STABLE
AS $$
    SELECT p_start + g.n AS day
    FROM generate_series(
        0,
        p_end_exclusive - p_start - 1
    ) AS g(n)
    ORDER BY day
$$;
```

Gọi:

```sql
SELECT *
FROM series_lab.calendar_days(
    DATE '2026-11-14',
    DATE '2026-11-20'
);
```

Kết quả có sáu ngày: 14–19/11.

### 28.2. Những điều cần lưu ý

- Hàm ví dụ trả **0 hàng** với khoảng rỗng hoặc end trước start, không phát lỗi nghiệp vụ.
- Nếu API yêu cầu từ chối khoảng sai, cần validation ngoài hàm hoặc thay đổi thiết kế hàm với logic báo lỗi phù hợp.
- Hàm này không biết ngày nghỉ, timezone, ca làm việc hay lịch nghỉ đặc biệt.
- Nếu tạo hàm trong môi trường chia sẻ, cần quản lý quyền `EXECUTE`, quyền schema và lifecycle migration.
- Không tạo hàm thật chỉ để dùng một lần; CTE thông thường có thể đủ rõ.

Trong SQL, loại hàm này cung cấp một **nguồn tập hợp** có thể kết hợp với các bảng khác theo yêu cầu truy vấn.

## 29. Khi nào cần bảng calendar được lưu lâu dài?

`generate_series` tạo dãy **theo yêu cầu**. Còn một **date dimension/calendar table** lưu thông tin ngày tháng đã được chuẩn bị.

### 29.1. Dãy sinh động

Phù hợp khi:

- Chỉ cần danh sách ngày liên tiếp trong một khoảng nhỏ hoặc vừa.
- Tạo bucket cho một request báo cáo.
- Dựng khung giờ với bước đơn giản.
- Sinh dữ liệu kiểm thử hoặc biểu diễn chu kỳ nhanh.
- Không cần metadata lịch phức tạp.

### 29.2. Bảng calendar thường trực

Phù hợp khi mỗi ngày có nhiều thuộc tính nghiệp vụ:

```text
calendar_date
iso_week
iso_year
fiscal_quarter
is_public_holiday
is_working_day
region_code
shift_type
business_opening_hours
```

Ví dụ một công ty hoạt động tại nhiều quốc gia có lịch nghỉ lễ, tuần tài chính và ngày bù riêng. Sinh ngày thô bằng `generate_series` vẫn hữu ích để **nạp bảng calendar ban đầu**, nhưng sau đó các thuộc tính nghiệp vụ cần được quản lý theo dữ liệu chuẩn.

### 29.3. So sánh

| Tiêu chí | generate_series | Bảng calendar |
|---|---|---|
| Cần lưu bảng trước? | Không | Có |
| Ngày liên tiếp đơn giản | Rất tiện | Tiện |
| Ngày lễ theo khu vực | Cần JOIN dữ liệu khác | Có thể tích hợp |
| Năm tài chính đặc thù | Cần logic hoặc JOIN | Có thể lưu sẵn |
| Kiểm soát lịch vận hành | Logic query | Quản trị dữ liệu có cấu trúc |
| Sinh dữ liệu thử nhanh | Rất phù hợp | Không phải mục tiêu chính |
| Dùng chung giữa nhiều báo cáo phức tạp | Dễ lặp logic | Thuận lợi khi được quản lý chuẩn |

Một phương án kết hợp thực tế là: **calendar dimension lưu chính sách lịch**, còn `generate_series` dựng những dãy ngắn cần thiết hoặc tạo dữ liệu ban đầu cho dimension.

## 30. Hiệu năng và giới hạn của generate_series

### 30.1. generate_series không miễn phí

Dù không đọc bảng vật lý, hàm vẫn phải **sinh từng hàng**. Nếu bạn yêu cầu hàng triệu hoặc hàng tỷ giá trị, hệ thống phải xử lý lượng dữ liệu tương ứng.

Một ví dụ kiểm tra quy mô nhỏ trong lab:

```sql
SELECT COUNT(*)
FROM generate_series(1, 100000) AS g(n);
```

Dù cuối cùng chỉ trả một số COUNT, PostgreSQL vẫn phải xử lý tập hợp giá trị ở mức cần thiết cho phép tổng hợp.

### 30.2. CROSS JOIN làm tăng cardinality theo tích

Nếu một truy vấn kết hợp:

- 10.000 tài nguyên.
- 365 ngày.
- 48 slot mỗi ngày.

số cặp ứng viên sẽ rất lớn. Đừng dựng ma trận đầy đủ chỉ để sau đó `WHERE resource_id = ...` hoặc giới hạn phạm vi rất hẹp.

Hãy:

1. Lọc danh sách tài nguyên **trước** khi CROSS JOIN.
2. Giới hạn ngày cần hiển thị trước khi sinh.
3. Chọn bước thời gian đúng độ phân giải yêu cầu.
4. Aggregate ở mức phù hợp và chỉ lấy cột cần thiết.
5. Giới hạn số ngày/slot mà người dùng có thể yêu cầu.
6. Xem actual row counts khi phân tích `EXPLAIN`.

### 30.3. Đọc kế hoạch với EXPLAIN

```sql
EXPLAIN
SELECT n
FROM generate_series(1, 1000) AS g(n)
WHERE n % 2 = 0;
```

PostgreSQL có thể hiển thị một `Function Scan` cho nguồn `generate_series`, cùng bước filter phù hợp.

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM generate_series(1, 10000) AS g(n);
```

`EXPLAIN ANALYZE` **thực sự thực thi truy vấn**. Ví dụ này là SELECT lab tương đối đơn giản, nhưng với những câu `INSERT ... SELECT generate_series(...)` hoặc `UPDATE`, `EXPLAIN ANALYZE` cũng có thể thực hiện thay đổi dữ liệu; không chạy trên hệ thống thật khi chưa có biện pháp kiểm soát.

### 30.4. Lưu ý thống kê và ước lượng hàng

Optimizer cần ước lượng số hàng từ hàm và các nguồn join. Một biểu thức có bounds cố định thường dễ ước lượng hơn biểu thức động phức tạp, nhưng kế hoạch thực tế còn phụ thuộc phiên bản, parameter, thống kê bảng và cardinality.

Khi kết hợp một dãy sinh với bảng lớn, việc có index trên cột thời gian/khóa ghép thường quan trọng hơn việc cố làm dãy SQL ngắn đi vài ký tự.

### 30.5. Đừng dùng generate_series làm chiến lược phân trang hàng tỷ bản ghi

Hàm sinh số thứ tự rất tiện cho thử nghiệm, nhưng nếu mục tiêu là đọc dữ liệu production có sẵn theo trang, hãy dùng khóa và điều kiện truy vấn phù hợp. Việc sinh một dãy cực lớn rồi join để phân trang không thay thế thiết kế index hoặc keyset pagination.

## 31. Những lỗi thường gặp

### Lỗi 1. Không nhớ stop là cận bao gồm

`generate_series(0, 10)` tạo **11 giá trị**. Khi cần 10 giá trị bắt đầu từ 0, dùng `generate_series(0,9)`.

### Lỗi 2. Chọn bước sai chiều

`generate_series(10,1,1)` trả dãy rỗng. Muốn giảm phải dùng bước âm.

### Lỗi 3. Dùng step = 0

PostgreSQL báo lỗi. Cần validation input.

### Lỗi 4. Nhầm dãy rỗng với một hàng NULL

`generate_series(1,0)` không tạo hàng. `CROSS JOIN LATERAL` với dãy rỗng làm mất hàng cha; `LEFT JOIN LATERAL` bảo toàn hàng cha bằng hàng NULL mở rộng.

### Lỗi 5. Sinh ngày bằng timestamp mà không xem kiểu dữ liệu

Khi dùng `generate_series(timestamp, timestamp, interval)`, kết quả là timestamp; nếu muốn ngày lịch, cast `::date` hoặc dùng `DATE + integer` rõ ràng.

### Lỗi 6. Cộng 24 giờ để thể hiện mọi ngày địa phương

Ở vùng có DST, một ngày có thể không dài 24 giờ tuyệt đối. Dùng tên vùng và hai ranh giới ngày địa phương khi nghiệp vụ cần “mỗi ngày”.

### Lỗi 7. Quên ranh giới nửa mở

Sinh slot từ 09:00 tới **17:00** với bước 30 phút tạo cả slot bắt đầu 17:00. Nếu 17:00 là giờ đóng cửa, cận mốc bắt đầu cuối phải là **16:30**.

### Lỗi 8. Không chuẩn hóa mốc đầu khi sinh tháng

Cộng từng tháng từ ngày 31 dễ có kết quả không như ý. Sinh từ **ngày đầu tháng** rồi xác định đầu tháng kế tiếp.

### Lỗi 9. Chỉ GROUP BY bảng giao dịch

Những ngày không có giao dịch sẽ không xuất hiện. Dựng calendar từ generate_series rồi LEFT JOIN.

### Lỗi 10. Đặt bộ lọc giao dịch trong WHERE

Điều kiện `WHERE s.status='PAID'` sau LEFT JOIN có thể loại ngày trống. Nếu muốn giữ mọi ngày, đặt điều kiện trong ON hoặc dùng `FILTER` cho aggregate.

### Lỗi 11. Dùng COUNT(*) trên ngày trống

LEFT JOIN vẫn có một hàng null-extended cho ngày không có giao dịch. Dùng `COUNT(s.sale_id)` để số đếm bằng 0.

### Lỗi 12. Quên rằng CROSS JOIN nhân số hàng

Kết hợp hàng nghìn khách hàng với nhiều năm × các khung giờ có thể tạo khối lượng dữ liệu rất lớn.

### Lỗi 13. Dùng timestamp không múi giờ cho lịch đa quốc gia

`timestamp` không tự mang vùng thời gian. Khi làm việc với thời điểm xác định, cân nhắc `timestamptz` và chuyển đổi từ giờ địa phương theo tên vùng.

### Lỗi 14. Dùng random() làm ID không kiểm soát

Các giá trị random có thể trùng, khó tái tạo. Với dữ liệu mẫu cần ID duy nhất, dùng dãy `generate_series` hoặc cơ chế identity/UUID phù hợp.

### Lỗi 15. Tạo dữ liệu mẫu ngay trên bảng production

`INSERT ... SELECT generate_series(...)` có thể tạo rất nhiều bản ghi, va chạm ID, kích hoạt trigger và phát sinh WAL. Chỉ chạy trong môi trường được phép và giới hạn số hàng.

### Lỗi 16. Giả định mọi nhiệm vụ phải có hàng ở mọi ngày

Khi một assignment có end trước start hoặc đầu vào NULL, dãy tương ứng rỗng. Cần làm rõ liệu muốn **loại hàng cha** hay **giữ hàng cha với ngày NULL**.

### Lỗi 17. Lấy dữ liệu ngày lễ từ chính generate_series

Hàm chỉ biết số/ngày liên tiếp, không biết chính sách ngày nghỉ của từng tổ chức. Cần bảng ngày lễ/giờ làm hoặc nguồn dữ liệu nghiệp vụ đáng tin cậy.

### Lỗi 18. Sinh thứ tự mà không đặt ORDER BY khi trình bày

Dù giá trị dãy được sinh theo thứ tự mong muốn, truy vấn SQL kết hợp join/aggregate không bảo đảm thứ tự cuối nếu thiếu `ORDER BY`. Dùng `ORDER BY day` hoặc `ORDER BY ordinality` khi đầu ra cần ổn định.

## 32. Bài tập thực hành có lời giải

### Bài 1. Sinh các số 1, 4, 7, 10

```sql
SELECT n
FROM generate_series(1, 10, 3) AS g(n);
```

Đáp án: 1, 4, 7, 10.

### Bài 2. Sinh năm số giảm dần 10, 8, 6, 4, 2

```sql
SELECT n
FROM generate_series(10, 2, -2) AS g(n);
```

Bước âm làm dãy đi đúng hướng.

### Bài 3. Sinh bảy ngày từ 14/11/2026

```sql
SELECT DATE '2026-11-14' + n AS day
FROM generate_series(0, 6) AS g(n)
ORDER BY day;
```

Đáp án: từ 14 tới 20/11, bao gồm hai đầu.

### Bài 4. Sinh từ 14/11 tới trước 20/11

```sql
SELECT DATE '2026-11-14' + n AS day
FROM generate_series(
    0,
    DATE '2026-11-20' - DATE '2026-11-14' - 1
) AS g(n);
```

Đáp án: 14, 15, 16, 17, 18, 19/11.

### Bài 5. Dãy timestamp 15 phút trong một giờ

Yêu cầu sinh các mốc 09:00, 09:15, 09:30 và 09:45, không sinh mốc 10:00.

```sql
SELECT t
FROM generate_series(
    TIMESTAMP '2026-11-16 09:00',
    TIMESTAMP '2026-11-16 09:45',
    INTERVAL '15 minutes'
) AS g(t);
```

Đáp án: 4 hàng.

### Bài 6. Lấy các ngày thứ Hai đến thứ Sáu trong tuần 16/11

```sql
WITH dates AS (
    SELECT DATE '2026-11-16' + n AS day
    FROM generate_series(0, 6) AS g(n)
)
SELECT day
FROM dates
WHERE EXTRACT(ISODOW FROM day) BETWEEN 1 AND 5
ORDER BY day;
```

Đáp án: 16–20/11/2026.

### Bài 7. Vì sao GROUP BY sales không trả ngày 15/11?

Vì không có hàng nào mang `sold_on = '2026-11-15'`. `GROUP BY` không tự tạo nhóm từ dữ liệu vắng mặt.

Lời giải: tạo calendar bằng generate_series, LEFT JOIN với sales và dùng `COUNT(s.sale_id)` để nhận số 0.

### Bài 8. Lấp các ngày trống bằng doanh thu bằng 0

```sql
WITH calendar AS (
    SELECT DATE '2026-11-14' + n AS day
    FROM generate_series(0, 6) AS g(n)
)
SELECT
    c.day,
    COALESCE(SUM(s.amount), 0) AS revenue
FROM calendar AS c
LEFT JOIN series_lab.sales AS s
    ON s.sold_on = c.day
GROUP BY c.day
ORDER BY c.day;
```

Đáp án: ngày 15, 17, 19, 20 có doanh thu 0 theo dữ liệu lab.

### Bài 9. Vì sao COUNT(*) sai trên ngày không có giao dịch?

Vì LEFT JOIN vẫn tạo một hàng với `s.sale_id NULL` cho ngày trống, và COUNT(*) đếm cả hàng đó.

Lời giải: `COUNT(s.sale_id)`.

### Bài 10. Giữ mọi ngày nhưng chỉ tính doanh số từ 200 trở lên

```sql
WITH calendar AS (
    SELECT DATE '2026-11-14' + n AS day
    FROM generate_series(0, 6) AS g(n)
)
SELECT c.day, COUNT(s.sale_id) AS qualifying_count
FROM calendar AS c
LEFT JOIN series_lab.sales AS s
    ON s.sold_on = c.day
   AND s.amount >= 200
GROUP BY c.day
ORDER BY c.day;
```

Điều kiện nằm trong ON, nên các ngày không có giao dịch đạt ngưỡng vẫn hiện với số 0.

### Bài 11. Sinh một dãy 1–100 rồi chia thành 5 nhóm

```sql
SELECT
    n,
    (n % 5) + 1 AS group_id
FROM generate_series(1, 100) AS g(n);
```

Tạo 100 hàng, group_id nằm trong 1–5.

### Bài 12. Mở rộng ngày của từng assignment

```sql
SELECT
    a.assignment_id,
    a.start_date + g.n AS assigned_day
FROM series_lab.assignments AS a
CROSS JOIN LATERAL generate_series(
    0,
    a.end_date - a.start_date
) AS g(n)
ORDER BY a.assignment_id, assigned_day;
```

Đáp án: assignment 1 có ngày 14,15,16; assignment 2 có ngày 18,19.

### Bài 13. Nếu một assignment không có ngày nào được sinh, CROSS JOIN sẽ ra sao?

Nó không tạo hàng cho assignment ấy. Nếu cần bảo toàn, dùng:

```sql
LEFT JOIN LATERAL generate_series(...) AS g(n) ON TRUE
```

và xử lý giá trị NULL của n/ngày.

### Bài 14. Tạo ma trận ba phòng × bảy ngày

```sql
WITH rooms(room_id) AS (
    VALUES (101), (102), (103)
),
days AS (
    SELECT DATE '2026-11-14' + n AS day
    FROM generate_series(0, 6) AS g(n)
)
SELECT *
FROM rooms CROSS JOIN days
ORDER BY room_id, day;
```

Đáp án: 21 cặp.

### Bài 15. Sinh 12 tháng năm 2026

```sql
SELECT month_start::date
FROM generate_series(
    TIMESTAMP '2026-01-01',
    TIMESTAMP '2026-12-01',
    INTERVAL '1 month'
) AS g(month_start);
```

Đáp án: 12 mốc đầu tháng.

### Bài 16. Giải thích khác biệt giữa ngày theo lịch và 24 giờ

Cần một email lúc 09:00 mỗi ngày tại vùng có DST.

Lời giải: tạo ngày địa phương, kết hợp giờ 09:00 và tên vùng (hoặc dùng overload timezone-aware phù hợp trên PostgreSQL 16+), thay vì giả định cứ cộng chính xác 24 giờ UTC là luôn đạt 09:00 tại địa phương.

### Bài 17. Tạo dữ liệu 10 tài khoản deterministic

```sql
SELECT
    n AS user_id,
    format('user_%s', lpad(n::text, 3, '0')) AS user_name,
    DATE '2026-11-14' + (n - 1) AS created_day
FROM generate_series(1, 10) AS g(n)
ORDER BY user_id;
```

Đáp án: 10 hàng, tên từ user_001 đến user_010, ngày từ 14 đến 23/11/2026.

### Bài 18. Vì sao không nên JOIN mọi resource với mọi slot trong một năm?

Vì số hàng trung gian là tích số resource × ngày × slot. Có thể tạo lượng dữ liệu lớn, ảnh hưởng CPU/bộ nhớ và tốc độ phản hồi. Cần giới hạn resource, khoảng ngày và độ phân giải trước khi mở rộng.

## 33. Bảng ghi nhớ nhanh

| Mục tiêu | Cú pháp gợi ý | Ghi chú |
|---|---|---|
| Số nguyên từ 1 tới 5 | `generate_series(1,5)` | Bao gồm 5 |
| Số chẵn 2–10 | `generate_series(2,10,2)` | Bước 2 |
| Dãy giảm | `generate_series(10,1,-3)` | Bước âm |
| Dãy rỗng theo hướng sai | `generate_series(5,1,1)` | Không trả hàng |
| Bước 0 | `generate_series(1,5,0)` | Lỗi |
| Dãy numeric | `generate_series(0::numeric,1::numeric,0.2::numeric)` | Chính xác thập phân |
| Bảy ngày liên tiếp | `DATE '2026-11-14' + n` với n = 0..6 | Đầu ra date |
| Ngày nửa mở | n = 0..`end_date - start_date - 1` | Tránh dư ngày cuối |
| Timestamp theo giờ | `generate_series(start_ts, stop_ts, INTERVAL '1 hour')` | Hai biên có thể được tính |
| Dãy theo vùng timezone | Dạng bốn đối số trên PostgreSQL 16+ | Dùng tên vùng |
| Slot 30 phút | `generate_series(start, last_start, '30 minutes')` | Không tạo slot bắt đầu lúc đóng cửa |
| Bắt đầu tuần | `date_trunc('week', timestamp)` | Thường là thứ Hai |
| Ngày trong tuần ISO | `EXTRACT(ISODOW FROM day)` | Thứ Hai 1, Chủ nhật 7 |
| Đầu các tháng | `generate_series(first_month, last_month, '1 month')` | Bắt đầu từ ngày 1 |
| Tháng nửa mở | `[month_start, next_month_start)` | Không cần số ngày cố định |
| Lịch + doanh số | Calendar `LEFT JOIN sales` | Giữ ngày trống |
| Đếm ngày trống = 0 | `COUNT(s.sale_id)` | Không dùng COUNT(*) |
| Tổng doanh thu ngày trống | `COALESCE(SUM(s.amount),0)` | Xác định ngữ nghĩa NULL/0 |
| Lọc giao dịch mà giữ ngày | Predicate giao dịch ở `ON` | Tránh xóa hàng calendar |
| Tạo ngày theo từng assignment | `CROSS JOIN LATERAL generate_series(...)` | Mỗi hàng cha một dãy |
| Giữ assignment không có ngày | `LEFT JOIN LATERAL ... ON TRUE` | Trả hàng NULL mở rộng |
| Tạo ma trận resource × calendar | `CROSS JOIN` | Số hàng nhân theo tích |
| Đánh số hàng sinh ra | `WITH ORDINALITY` | Ordinality từ 1 |
| Sinh dữ liệu mẫu | `INSERT ... SELECT ... FROM generate_series(...)` | Chỉ trong lab được phép |
| Test không ghi dữ liệu | CTE + SELECT từ generate_series | Không tạo bảng thật |
| Xem kế hoạch | `EXPLAIN SELECT ...` | Có thể thấy Function Scan |

## 34. Tổng kết

`generate_series` là một trong những công cụ PostgreSQL hữu ích nhất để biến yêu cầu về **khoảng giá trị** thành **các hàng SQL** có thể join, lọc, tổng hợp và đưa vào câu INSERT.

Ba nhóm ứng dụng quan trọng:

**Một — Dựng lịch:** sinh ngày từ `DATE + integer`, mốc giờ từ `generate_series(timestamp, ..., interval)`, đầu tháng từ bước `INTERVAL '1 month'`, hoặc thời điểm theo vùng bằng `timestamptz` cùng tên timezone thích hợp.

**Hai — Lấp khoảng trống:** sinh calendar trước, dùng `LEFT JOIN` với dữ liệu thật, sau đó dùng `COUNT(pk_bảng_phải)` và `COALESCE(SUM(...),0)` để những ngày không có giao dịch vẫn xuất hiện chính xác với số 0.

**Ba — Tạo dữ liệu mẫu:** dùng dãy số làm ID hoặc số thứ tự, kết hợp phép toán số học, ngày giờ, `CROSS JOIN` và `LATERAL` để tạo các tập dữ liệu có quy luật, dễ lặp lại và phục vụ kiểm thử.

Các nguyên tắc cần nhớ nhất:

1. `stop` **được bao gồm** nếu bước nhảy chạm tới. Khi cần khoảng nửa mở, phải xử lý ranh giới rõ ràng.
2. Bước nhảy phải khác 0 và đúng hướng; dãy không phù hợp trả **0 hàng**.
3. Sinh ngày theo lịch khác với sinh thời điểm với bước nhảy cố định. Ở vùng có DST, cần dùng **tên vùng múi giờ** và ranh giới ngày địa phương.
4. `CROSS JOIN` có thể nhân rất lớn số hàng; `LATERAL` tạo dãy riêng cho mỗi hàng; `LEFT JOIN LATERAL` giữ hàng cha khi dãy rỗng.
5. Điều kiện giao dịch trong `WHERE` có thể loại ngày trống của báo cáo; đặt điều kiện ở `ON` hoặc dùng `FILTER` khi muốn giữ mọi ngày.
6. Dữ liệu demo cần có giới hạn và không được tạo tùy tiện trong production. Dữ liệu deterministic thường dễ kiểm thử và đối chiếu hơn dữ liệu random.
7. Khi quy tắc ngày làm việc, nghỉ lễ hoặc năm tài chính phức tạp, hãy kết hợp `generate_series` với **bảng calendar nghiệp vụ** thay vì cho rằng hàm tự hiểu các chính sách đó.

Với tư duy **“sinh đủ khung thời gian hoặc tập ứng viên trước, sau đó ghép dữ liệu thực tế”**, bạn có thể xây dựng lịch, biểu đồ và bộ dữ liệu kiểm thử PostgreSQL vừa gọn vừa chính xác, kể cả khi không có hàng dữ liệu trong một vài ngày hoặc khoảng thời gian.


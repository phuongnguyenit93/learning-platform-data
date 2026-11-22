# Lọc dữ liệu ngày giờ bằng khoảng thời gian trong SQL

Khi làm việc với cơ sở dữ liệu, bạn thường phải trả lời những câu hỏi như: “Đơn hàng nào được tạo trong ngày 14/11?”, “Có bao nhiêu giao dịch trong tháng này?”, “Sự kiện nào diễn ra trong 24 giờ gần nhất?” hoặc “Những bản ghi nào nằm giữa hai mốc thời gian?”. Tất cả đều là **bài toán lọc dữ liệu theo khoảng thời gian**.

Điều cần chú ý là một khoảng thời gian có **mốc bắt đầu**, **mốc kết thúc**, **quy tắc lấy hay bỏ các mốc biên**, và đôi khi là **múi giờ**. Nếu hiểu sai một trong những yếu tố này, truy vấn có thể bỏ sót bản ghi tại cuối ngày, đếm trùng bản ghi giữa hai kỳ hoặc lấy nhầm dữ liệu của một ngày khác.

Bài học sử dụng **PostgreSQL** để minh họa cú pháp thực hành, đồng thời chỉ ra những điểm cần điều chỉnh khi dùng MySQL, SQL Server hoặc SQLite. Chủ đề chính là cách viết điều kiện `WHERE` để **lọc theo khoảng ngày giờ chính xác và dễ tối ưu hóa**.

## 1. Khoảng thời gian: bắt đầu, kết thúc và tính bao hàm

Một khoảng thời gian cần xác định rõ các ranh giới của nó:

| Cách biểu diễn toán học | Điều kiện SQL | Ý nghĩa |
|---|---|---|
| `[start, end]` | `value >= start AND value <= end` | Lấy cả hai đầu mút |
| `[start, end)` | `value >= start AND value < end` | Lấy đầu, bỏ cuối |
| `(start, end]` | `value > start AND value <= end` | Bỏ đầu, lấy cuối |
| `(start, end)` | `value > start AND value < end` | Bỏ cả hai đầu |

Ký hiệu dấu ngoặc vuông `[`/`]` nghĩa là **bao gồm**, còn dấu ngoặc tròn `(`/`)` nghĩa là **không bao gồm** mốc đó.

Trong rất nhiều truy vấn báo cáo, lựa chọn tốt nhất là **khoảng nửa mở `[start, end)`**:

```sql
WHERE created_at >= :start_time
  AND created_at <  :end_time
```

Các tên `:start_time` và `:end_time` là **ký hiệu tham số minh họa**, không phải cú pháp literal được mọi DBMS chấp nhận. Trong chương trình thực tế, API/driver thay thế chúng bằng các tham số có kiểu thời gian tương ứng.

### Vì sao khoảng nửa mở hữu ích?

Giả sử chia dữ liệu thành các ngày liên tiếp:

```text
Ngày 14/11                          Ngày 15/11
00:00 -------------------- 00:00 -------------------- 00:00
       [Ngày 14/11)                       [Ngày 15/11)
       >= 14/11 00:00                     >= 15/11 00:00
       <  15/11 00:00                     <  16/11 00:00
```

Với cách chia `[start, end)`, một bản ghi nằm **chính xác lúc 00:00 ngày 15/11** chỉ thuộc kỳ ngày 15, không bị đếm trong ngày 14. Hai khoảng kế tiếp **không chồng lấp và không tạo khe hở tại ranh giới**.

Quy tắc này cũng phù hợp khi lọc đến phần lẻ giây: không cần đoán giá trị “cuối ngày” là `23:59:59`, `23:59:59.999` hay `23:59:59.999999`.

## 2. Chuẩn bị bảng dữ liệu thực hành

Trong PostgreSQL, tạo một bảng mô phỏng nhật ký sự kiện. Chỉ chạy các lệnh tạo bảng và thêm dữ liệu một lần trong **cơ sở dữ liệu thực hành**.

```sql
CREATE TABLE lesson120_events (
    event_id INTEGER PRIMARY KEY,
    event_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ,
    due_on DATE
);

INSERT INTO lesson120_events (
    event_id,
    event_name,
    created_at,
    due_on
)
VALUES
    (
        1,
        'Trước ngày 14',
        TIMESTAMPTZ '2026-11-13 23:59:59+07',
        DATE '2026-11-13'
    ),
    (
        2,
        'Đúng đầu ngày 14',
        TIMESTAMPTZ '2026-11-14 00:00:00+07',
        DATE '2026-11-14'
    ),
    (
        3,
        'Buổi sáng ngày 14',
        TIMESTAMPTZ '2026-11-14 09:15:30.125+07',
        DATE '2026-11-14'
    ),
    (
        4,
        'Sát cuối ngày 14',
        TIMESTAMPTZ '2026-11-14 23:59:59.999999+07',
        DATE '2026-11-14'
    ),
    (
        5,
        'Đúng đầu ngày 15',
        TIMESTAMPTZ '2026-11-15 00:00:00+07',
        DATE '2026-11-15'
    ),
    (
        6,
        'Chưa có thời điểm',
        NULL,
        NULL
    ),
    (
        7,
        'Buổi sáng ngày 15',
        TIMESTAMPTZ '2026-11-15 10:00:00+07',
        DATE '2026-11-15'
    );
```

Giải thích hai cột ngày giờ:

- `created_at TIMESTAMPTZ` lưu **thời điểm xảy ra sự kiện**, có thể so sánh trên dòng thời gian chung dù hai client dùng múi giờ khác nhau.
- `due_on DATE` lưu **ngày theo lịch**, không chứa giờ, phút hay múi giờ riêng.

Dữ liệu trên sử dụng độ lệch `+07` để đại diện cho thời gian Việt Nam trong các ngày ví dụ. Bạn có thể xem giá trị `TIMESTAMPTZ` theo múi giờ Việt Nam bằng:

```sql
SELECT
    event_id,
    event_name,
    created_at AT TIME ZONE 'Asia/Ho_Chi_Minh' AS vietnam_local_time,
    due_on
FROM lesson120_events
ORDER BY event_id;
```

Kết quả sắp xếp theo `event_id` giúp đối chiếu các tình huống tại **đầu ngày**, **cuối ngày**, **ngày tiếp theo** và **giá trị NULL**.

## 3. Lọc một ngày khi cột là DATE

Đối với kiểu `DATE`, nếu muốn tìm đúng ngày 14/11/2026, dùng phép so sánh bằng:

```sql
SELECT
    event_id,
    event_name,
    due_on
FROM lesson120_events
WHERE due_on = DATE '2026-11-14'
ORDER BY event_id;
```

Với dữ liệu mẫu, kết quả là các sự kiện **2, 3 và 4**.

Vì `DATE` không chứa giờ, hai điều kiện sau cũng diễn đạt ngày này:

```sql
WHERE due_on >= DATE '2026-11-14'
  AND due_on <  DATE '2026-11-15'
```

Nhưng khi chỉ cần kiểm tra **một ngày cụ thể của một cột DATE**, phép bằng `= DATE '...'` dễ đọc hơn. Khoảng nửa mở rất hữu ích khi cần lọc **nhiều ngày, một tháng, một quý hoặc một năm**:

```sql
-- Các ngày từ 14/11 đến hết 20/11/2026.
SELECT event_id, event_name, due_on
FROM lesson120_events
WHERE due_on >= DATE '2026-11-14'
  AND due_on <  DATE '2026-11-21'
ORDER BY due_on, event_id;
```

Có thể dùng `BETWEEN DATE '2026-11-14' AND DATE '2026-11-20'` cho cùng tập **DATE** này vì `BETWEEN` bao gồm cả hai đầu. Điều cần phân biệt là kiểu `DATE` và kiểu có cả **giờ trong ngày**.

## 4. Lọc một ngày khi cột là TIMESTAMP hoặc TIMESTAMPTZ

Với cột chứa cả ngày và giờ, điều kiện `created_at = DATE '2026-11-14'` **không lấy tất cả thời điểm trong ngày**: phép so sánh/ngầm chuyển kiểu thường tương ứng với một mốc **đầu ngày** theo ngữ cảnh, nên bỏ sót nhiều bản ghi sau 00:00.

Cách diễn đạt rõ ràng là tạo khoảng từ **đầu ngày cần lấy** đến **đầu ngày tiếp theo**, loại trừ mốc kết thúc.

### 4.1. Khoảng nửa mở cho ngày 14/11 theo giờ Việt Nam

```sql
SELECT
    event_id,
    event_name,
    created_at AT TIME ZONE 'Asia/Ho_Chi_Minh' AS vietnam_local_time
FROM lesson120_events
WHERE created_at >= TIMESTAMPTZ '2026-11-14 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-11-15 00:00:00+07'
ORDER BY created_at;
```

Kết quả:

| event_id | event_name | Giờ Việt Nam |
|---|---|---|
| 2 | Đúng đầu ngày 14 | 2026-11-14 00:00:00 |
| 3 | Buổi sáng ngày 14 | 2026-11-14 09:15:30.125 |
| 4 | Sát cuối ngày 14 | 2026-11-14 23:59:59.999999 |

Vì sao:

- Sự kiện **1** ở trước `start` nên bị loại.
- Sự kiện **2** đúng `start` nên **được lấy**.
- Sự kiện **4** có phần lẻ giây nhưng vẫn nhỏ hơn `end` nên **được lấy**.
- Sự kiện **5** đúng `end` nên **không được lấy**.
- Sự kiện **6** có `created_at IS NULL`, phép so sánh trả `UNKNOWN` nên không được lấy.
- Sự kiện **7** ở sau `end` nên không được lấy.

Đây là cách lọc ngày có thể áp dụng cho dữ liệu timestamp độ chính xác đến giây, mili giây hay micro giây mà không phải đoán “thời điểm cuối cùng còn nằm trong ngày”.

### 4.2. Đừng dùng 23:59:59 làm cuối ngày

Một cách dễ gây thiếu dữ liệu là:

```sql
-- Không khuyến khích khi cột có phần lẻ giây.
SELECT event_id, event_name
FROM lesson120_events
WHERE created_at BETWEEN
      TIMESTAMPTZ '2026-11-14 00:00:00+07'
  AND TIMESTAMPTZ '2026-11-14 23:59:59+07';
```

`BETWEEN` bao gồm mốc kết thúc, nhưng **mốc cuối ở đây chỉ là 23:59:59.000000**. Sự kiện 4 xảy ra lúc `23:59:59.999999` nên bị bỏ sót.

Cũng không nên sửa bằng một giá trị giả định như `23:59:59.999`: hệ quản trị hoặc cột có thể lưu chính xác đến micro giây/nanosecond hoặc làm tròn theo quy tắc khác. Cách chắc chắn về ý nghĩa là dùng **đầu ngày hôm sau và toán tử `<`**.

### 4.3. Vì sao BETWEEN thường không phù hợp với các kỳ tiếp nối?

Cú pháp:

```sql
WHERE created_at BETWEEN :start_time AND :end_time
```

về ý nghĩa tương đương:

```sql
WHERE created_at >= :start_time
  AND created_at <= :end_time
```

Tức là **bao gồm cả hai đầu**. Nếu báo cáo ngày 14 và ngày 15 đều dùng `BETWEEN` với mốc `15/11 00:00` làm đầu/cuối chung, một sự kiện đúng mốc đó có thể xuất hiện **trong cả hai báo cáo**.

Hãy chọn `BETWEEN` khi nghiệp vụ thực sự yêu cầu **bao gồm cả mốc kết thúc**, chẳng hạn kiểm tra một khoảng giá trị số hoặc mốc thời gian kết thúc đã được xác định rõ. Để chia dữ liệu theo ngày/tháng và cộng gộp báo cáo, thông thường ưu tiên `>= start AND < end`.

## 5. Lọc nhiều ngày, tháng, quý và năm

Nguyên tắc nửa mở mở rộng tự nhiên cho mọi kỳ lịch.

### 5.1. Khoảng nhiều ngày

Muốn lấy mọi sự kiện từ đầu ngày 14/11 đến **hết ngày 16/11** theo giờ Việt Nam:

```sql
SELECT event_id, event_name, created_at
FROM lesson120_events
WHERE created_at >= TIMESTAMPTZ '2026-11-14 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-11-17 00:00:00+07'
ORDER BY created_at;
```

Tại sao mốc cuối là `17/11 00:00`? Bởi vì cần **bao gồm toàn bộ ngày 16/11**, rồi loại trừ thời điểm bắt đầu ngày 17/11.

### 5.2. Một tháng

Lọc **tháng 11/2026** theo giờ Việt Nam:

```sql
SELECT event_id, event_name, created_at
FROM lesson120_events
WHERE created_at >= TIMESTAMPTZ '2026-11-01 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-12-01 00:00:00+07'
ORDER BY created_at;
```

Không cần xác định ngày cuối tháng có 28, 29, 30 hay 31 ngày; chỉ cần tính **đầu tháng tiếp theo**.

### 5.3. Một quý

Lọc **quý IV/2026**:

```sql
SELECT event_id, event_name, created_at
FROM lesson120_events
WHERE created_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2027-01-01 00:00:00+07'
ORDER BY created_at;
```

### 5.4. Một năm

Lọc **năm 2026**:

```sql
SELECT event_id, event_name, created_at
FROM lesson120_events
WHERE created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2027-01-01 00:00:00+07'
ORDER BY created_at;
```

Nguyên tắc “đầu kỳ hiện tại đến đầu kỳ kế tiếp” giúp truy vấn ít phụ thuộc vào độ chính xác phần lẻ giây và độ dài của mỗi kỳ.

## 6. Lọc theo giờ trong một ngày

Giả sử muốn tìm các sự kiện **từ 09:00 đến trước 10:00 ngày 14/11** theo giờ Việt Nam:

```sql
SELECT event_id, event_name, created_at
FROM lesson120_events
WHERE created_at >= TIMESTAMPTZ '2026-11-14 09:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-11-14 10:00:00+07'
ORDER BY created_at;
```

Với dữ liệu mẫu, chỉ sự kiện **3** nằm trong khoảng.

Nếu chỉ muốn lọc **giờ trong ngày mà không quan tâm ngày nào**, cần nói rõ đó là một bài toán khác. Ví dụ PostgreSQL:

```sql
SELECT
    event_id,
    event_name
FROM lesson120_events
WHERE (created_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::time
          >= TIME '09:00:00'
  AND (created_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::time
          <  TIME '10:00:00'
ORDER BY event_id;
```

Cách thứ hai tìm sự kiện ở khoảng **09:00–10:00 của mọi ngày** theo múi giờ Việt Nam. Nó phải chuyển đổi thời gian từng hàng để kiểm tra phần `TIME`, nên có thể kém thuận lợi cho chỉ mục thông thường trên `created_at`. Nếu bài toán thực tế đã biết **một ngày cụ thể**, điều kiện trực tiếp trên timestamp bằng hai ranh giới thường rõ ràng và dễ tối ưu hơn.

### 6.1. Ca giờ qua nửa đêm

Với yêu cầu “từ 22:00 ngày 14/11 đến trước 06:00 ngày 15/11”, hãy viết **hai thời điểm đầy đủ**:

```sql
WHERE created_at >= TIMESTAMPTZ '2026-11-14 22:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-11-15 06:00:00+07'
```

Không thể biểu diễn đúng một khoảng băng qua ngày chỉ bằng điều kiện thông thường `time >= '22:00' AND time < '06:00'`, vì không có giờ đồng hồ nào đồng thời lớn hơn 22:00 và nhỏ hơn 06:00 trong cùng một ngày. Nếu thật sự muốn tìm **mọi ca đêm lặp lại qua các ngày**, cần dùng điều kiện `OR` trên giờ địa phương hoặc mô hình lịch ca phù hợp.

## 7. Múi giờ quyết định ranh giới của một “ngày”

Câu hỏi “tìm dữ liệu trong ngày 14/11” chưa hoàn chỉnh nếu cột lưu một **thời điểm tuyệt đối** và người dùng ở nhiều múi giờ.

Ví dụ sự kiện xảy ra lúc:

```text
2026-11-14 00:30:00+07  (giờ Việt Nam)
2026-11-13 17:30:00+00  (giờ UTC)
```

Đó là **cùng một instant**, nhưng thuộc **hai ngày theo lịch khác nhau**. Báo cáo ngày theo UTC có thể xếp nó vào **13/11**, còn báo cáo theo giờ Việt Nam xếp vào **14/11**.

### 7.1. So sánh TIMESTAMPTZ bằng mốc có offset rõ ràng

Truy vấn trong phần 4 dùng:

```sql
WHERE created_at >= TIMESTAMPTZ '2026-11-14 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-11-15 00:00:00+07'
```

Hai mốc này tương đương:

```sql
WHERE created_at >= TIMESTAMPTZ '2026-11-13 17:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-11-14 17:00:00+00'
```

Với `TIMESTAMPTZ` của PostgreSQL, phép so sánh giữa các giá trị có offset khác nhau được thực hiện theo **thời điểm tương ứng**, không phải so theo chuỗi ký tự hiển thị.

### 7.2. Múi giờ khu vực và độ lệch UTC khác nhau

- `+07:00` là **độ lệch cố định** so với UTC.
- `Asia/Ho_Chi_Minh` là **tên vùng múi giờ** có quy tắc thời gian theo địa phương.
- `America/New_York` có thể dùng `-05:00` hoặc `-04:00` tùy thời điểm vì có quy tắc đổi giờ mùa hè (DST).

Khi lọc **ngày lịch của một vùng**, nên xây dựng hai mốc từ **ngày địa phương + tên vùng múi giờ**, đặc biệt ở nơi có đổi giờ mùa hè. Ví dụ PostgreSQL tìm sự kiện xảy ra **ngày 08/03/2026 theo giờ New York**:

```sql
SELECT *
FROM lesson120_events
WHERE created_at >= (
          TIMESTAMP '2026-03-08 00:00:00'
          AT TIME ZONE 'America/New_York'
      )
  AND created_at < (
          TIMESTAMP '2026-03-09 00:00:00'
          AT TIME ZONE 'America/New_York'
      );
```

Ở New York, ngày 08/03/2026 là ngày chuyển sang giờ mùa hè, nên khoảng từ **nửa đêm địa phương đến nửa đêm địa phương tiếp theo chỉ kéo dài 23 giờ thực**. Việc cộng cố định `24 hours` vào mốc đầu sẽ không diễn đạt đúng kỳ **một ngày địa phương** đó.

### 7.3. Không dựa vào timezone phiên một cách vô thức

Ví dụ PostgreSQL:

```sql
WHERE created_at::date = DATE '2026-11-14'
```

Khi ép `TIMESTAMPTZ` sang `DATE` trong PostgreSQL, ngày được xác định theo **thiết lập múi giờ của phiên làm việc**. Nếu client kết nối có timezone khác, tập kết quả có thể thay đổi.

Nếu nghiệp vụ là **ngày Việt Nam**, phải xác định rõ `Asia/Ho_Chi_Minh` hoặc mốc UTC tương ứng, thay vì giả định máy chủ và ứng dụng luôn dùng một timezone cố định.

## 8. Cửa sổ thời gian động: hôm nay, N ngày và N giờ gần nhất

Báo cáo thường cần khoảng thời gian **phụ thuộc vào thời điểm chạy truy vấn**. Khi đó phải phân biệt “**ngày theo lịch**” với “**số giờ đã trôi qua**”.

### 8.1. Hôm nay theo múi giờ của phiên PostgreSQL

Nếu đã xác nhận timezone của phiên là timezone nghiệp vụ, có thể viết:

```sql
SELECT event_id, event_name, created_at
FROM lesson120_events
WHERE created_at >= CURRENT_DATE
  AND created_at <  CURRENT_DATE + 1
ORDER BY created_at;
```

Trong PostgreSQL, khi so sánh với `TIMESTAMPTZ`, các mốc ngày được diễn giải theo **timezone của phiên**. Nếu ứng dụng dùng UTC nhưng báo cáo yêu cầu ngày Việt Nam, không dùng cách này mà chưa chuẩn hóa timezone hoặc tạo mốc theo vùng.

Để tránh phụ thuộc vào timezone phiên khi chọn **hôm nay ở Việt Nam**, có thể tạo ranh giới trực tiếp bằng tên vùng:

```sql
WITH local_day AS (
    SELECT
        (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
            AS business_date
)
SELECT
    e.event_id,
    e.event_name,
    e.created_at
FROM lesson120_events AS e
CROSS JOIN local_day AS d
WHERE e.created_at >= (
          d.business_date::timestamp
          AT TIME ZONE 'Asia/Ho_Chi_Minh'
      )
  AND e.created_at < (
          (d.business_date + 1)::timestamp
          AT TIME ZONE 'Asia/Ho_Chi_Minh'
      )
ORDER BY e.created_at;
```

`CURRENT_TIMESTAMP` xác định mốc thời gian hiện tại theo ngữ nghĩa của PostgreSQL; `AT TIME ZONE` đổi instant sang ngày giờ địa phương, rồi chuyển **đầu ngày địa phương** trở lại instant để lọc. Với báo cáo chạy định kỳ, cũng có thể tính sẵn các ranh giới này trong ứng dụng và truyền vào SQL qua tham số.

### 8.2. 24 giờ gần nhất

Đây là cửa sổ **thời lượng**, không phụ thuộc ranh giới nửa đêm:

```sql
SELECT event_id, event_name, created_at
FROM lesson120_events
WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
  AND created_at <  CURRENT_TIMESTAMP
ORDER BY created_at;
```

Ví dụ nếu truy vấn chạy lúc 10:00, nó tìm dữ liệu từ 10:00 hôm trước đến trước 10:00 hiện tại, chứ không phải toàn bộ “hôm qua” hoặc “hôm nay”.

PostgreSQL `CURRENT_TIMESTAMP` phản ánh **thời điểm bắt đầu giao dịch hiện tại**. Nếu có giao dịch kéo dài, giá trị này không cập nhật liên tục theo đồng hồ. Trường hợp yêu cầu ranh giới dựa trên thời gian thực đúng lúc thực thi, PostgreSQL có `clock_timestamp()`; để hai mốc dùng đúng cùng một “now”, tính một mốc một lần trong ứng dụng hoặc trong truy vấn theo cách phù hợp.

### 8.3. Bảy ngày lịch gần đây, bao gồm hôm nay

Nếu cần **7 ngày lịch** (hôm nay và 6 ngày trước) theo timezone của phiên:

```sql
SELECT event_id, event_name, created_at
FROM lesson120_events
WHERE created_at >= CURRENT_DATE - 6
  AND created_at <  CURRENT_DATE + 1
ORDER BY created_at;
```

Cửa sổ này khác với:

```sql
WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '7 days'
  AND created_at <  CURRENT_TIMESTAMP
```

Câu thứ hai dựa trên thời điểm hiện tại, không căn theo đầu/cuối ngày. Ở vùng có DST, **7 ngày lịch** và **168 giờ thực** còn có thể khác nhau về độ dài. Hãy dùng đúng ngữ nghĩa báo cáo đang cần.

### 8.4. Tháng hiện tại

Trong PostgreSQL, với timezone phiên được thiết lập đúng theo nghiệp vụ:

```sql
SELECT event_id, event_name, created_at
FROM lesson120_events
WHERE created_at >= DATE_TRUNC('month', CURRENT_TIMESTAMP)
  AND created_at <  DATE_TRUNC('month', CURRENT_TIMESTAMP)
                   + INTERVAL '1 month'
ORDER BY created_at;
```

Hàm `DATE_TRUNC` đưa mốc hiện tại về **đầu tháng**. Cộng `INTERVAL '1 month'` tạo đầu tháng tiếp theo. Với báo cáo cho một vùng timezone cụ thể độc lập với phiên, ứng dụng nên sinh **hai mốc theo lịch của vùng đó** rồi truyền vào `WHERE`.

## 9. Truy vấn khoảng thời gian và giá trị NULL

Các phép so sánh thông thường với `NULL` không cho `TRUE`, vì vậy điều kiện khoảng tự loại các bản ghi thiếu thời điểm:

```sql
SELECT event_id, event_name
FROM lesson120_events
WHERE created_at >= TIMESTAMPTZ '2026-11-14 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-11-15 00:00:00+07';
```

Sự kiện **6** có `created_at = NULL` nên không xuất hiện. Nếu báo cáo yêu cầu thêm những bản ghi chưa xác định thời gian, phải biểu đạt **một cách tường minh**:

```sql
SELECT event_id, event_name, created_at
FROM lesson120_events
WHERE (
       created_at >= TIMESTAMPTZ '2026-11-14 00:00:00+07'
   AND created_at <  TIMESTAMPTZ '2026-11-15 00:00:00+07'
)
OR created_at IS NULL
ORDER BY event_id;
```

Hãy đặt dấu ngoặc quanh phần phạm vi để điều kiện `OR created_at IS NULL` không làm thay đổi logic khi kết hợp thêm các điều kiện khác. Chỉ lấy `NULL` khi định nghĩa báo cáo thực sự yêu cầu; “chưa có thời điểm” thường không thể được phân vào một ngày cụ thể.

## 10. Kết hợp khoảng thời gian với những điều kiện khác

Ví dụ bảng giao dịch thực tế có cột trạng thái `status`. Khi muốn lấy đơn hàng **đã hoàn tất trong tháng 11**, kết hợp bộ lọc ngày với `AND`:

```sql
-- Ví dụ minh họa nếu đã có bảng orders(created_at, status, ...).
SELECT order_id, created_at, status
FROM orders
WHERE status = 'COMPLETED'
  AND created_at >= TIMESTAMPTZ '2026-11-01 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-12-01 00:00:00+07'
ORDER BY created_at, order_id;
```

Hai điều kiện ranh giới phải **cùng áp dụng cho một hàng**. Nếu thêm lựa chọn nhiều trạng thái, dùng dấu ngoặc rõ ràng:

```sql
SELECT order_id, created_at, status
FROM orders
WHERE status IN ('COMPLETED', 'PAID')
  AND created_at >= TIMESTAMPTZ '2026-11-01 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-12-01 00:00:00+07';
```

Không viết như sau nếu không muốn vô tình lấy mọi đơn `PAID` ngoài khoảng tháng 11:

```sql
-- Sai khi ý định là cả COMPLETED và PAID phải nằm trong tháng.
WHERE status = 'COMPLETED'
   OR status = 'PAID'
  AND created_at >= TIMESTAMPTZ '2026-11-01 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-12-01 00:00:00+07'
```

Vì `AND` có độ ưu tiên cao hơn `OR`, đoạn trên có thể lấy **mọi đơn `COMPLETED` bất kể ngày giờ**. Cần gom trạng thái bằng `IN` hoặc dấu ngoặc.

## 11. So sánh với khoảng dữ liệu `[valid_from, valid_to)`

Ngoài “thời điểm tạo nằm trong một kỳ”, còn có bài toán **một bản ghi có hiệu lực trong một khoảng thời gian**. Ví dụ bảng đăng ký có hai cột:

- `valid_from`: thời điểm bắt đầu hiệu lực, lấy cả mốc này.
- `valid_to`: thời điểm kết thúc hiệu lực, không lấy mốc này; có thể là `NULL` nếu chưa có ngày kết thúc.

### 11.1. Kiểm tra có hiệu lực tại một thời điểm

Giả sử `subscriptions(valid_from, valid_to, ...)` đã tồn tại:

```sql
SELECT subscription_id, valid_from, valid_to
FROM subscriptions
WHERE valid_from <= TIMESTAMPTZ '2026-11-14 10:00:00+07'
  AND (
       valid_to > TIMESTAMPTZ '2026-11-14 10:00:00+07'
       OR valid_to IS NULL
  );
```

Điều kiện này lấy hợp đồng đã bắt đầu, chưa kết thúc tại thời điểm yêu cầu. Nếu `valid_to` **không bao gồm** mốc kết thúc, hợp đồng kết thúc đúng 10:00 sẽ không còn hiệu lực tại 10:00.

### 11.2. Tìm các khoảng có giao nhau

Giả sử cần tìm mọi khoảng hiệu lực giao với kỳ truy vấn `[query_start, query_end)`. Với cả hai khoảng đều nửa mở và có độ dài dương, điều kiện chồng lấp điển hình là:

```text
record_start < query_end
AND record_end > query_start
```

Ví dụ SQL:

```sql
SELECT subscription_id, valid_from, valid_to
FROM subscriptions
WHERE valid_from < TIMESTAMPTZ '2026-12-01 00:00:00+07'
  AND (
       valid_to > TIMESTAMPTZ '2026-11-01 00:00:00+07'
       OR valid_to IS NULL
  );
```

Một hợp đồng bắt đầu đúng **đầu tháng 12** không chồng lấp tháng 11; một hợp đồng kết thúc đúng **đầu tháng 11** cũng không chồng lấp. Đây là bài toán **giao nhau của hai khoảng**, khác với lọc một **thời điểm** thuộc khoảng.

PostgreSQL còn có **range types** như `tstzrange` và toán tử chồng lấp `&&`:

```sql
SELECT
    tstzrange(
        TIMESTAMPTZ '2026-11-14 08:00:00+07',
        TIMESTAMPTZ '2026-11-14 10:00:00+07',
        '[)'
    )
    &&
    tstzrange(
        TIMESTAMPTZ '2026-11-14 09:00:00+07',
        TIMESTAMPTZ '2026-11-14 11:00:00+07',
        '[)'
    ) AS periods_overlap;
```

Kết quả là `TRUE` vì hai khoảng chồng lên nhau từ 09:00 đến trước 10:00. Cú pháp range là **đặc thù PostgreSQL**, không phải SQL phổ quát. Để học phần lọc `WHERE` cơ bản, điều kiện so sánh hai đầu mút vẫn là nền tảng.

## 12. Hiệu năng: lọc trực tiếp trên cột thời gian

Với bảng nhiều hàng, truy vấn khoảng thời gian thường được hưởng lợi từ chỉ mục khi DBMS có thể so sánh **trực tiếp cột với hai giá trị biên**.

Ví dụ PostgreSQL:

```sql
CREATE INDEX lesson120_events_created_at_idx
    ON lesson120_events (created_at);
```

Bộ lọc:

```sql
SELECT event_id, event_name
FROM lesson120_events
WHERE created_at >= TIMESTAMPTZ '2026-11-14 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-11-15 00:00:00+07';
```

có thể sử dụng chỉ mục B-tree trên `created_at` khi thích hợp. Tuy nhiên, bảng ví dụ chỉ có 7 hàng, nên optimizer có thể chọn quét bảng; điều này bình thường.

### 12.1. Hạn chế bọc cột trong hàm khi mục tiêu là lọc khoảng

Ví dụ PostgreSQL:

```sql
-- Dễ đọc nhưng có thể khó dùng index thông thường trên created_at.
WHERE (created_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
          = DATE '2026-11-14'
```

Câu này **chuyển đổi giá trị của từng hàng** thành ngày Việt Nam rồi mới so sánh. Với chỉ mục thông thường trên `created_at`, DBMS có thể không dùng được chỉ mục theo cách tối ưu như phép lọc trực tiếp.

Thay thế thông dụng:

```sql
WHERE created_at >= TIMESTAMPTZ '2026-11-14 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-11-15 00:00:00+07'
```

Hãy tính hoặc truyền **hai ranh giới dưới đúng kiểu dữ liệu** rồi giữ biểu thức cột đơn giản. Một số DBMS hỗ trợ **expression index** hoặc **computed/generated column được lập chỉ mục** để tối ưu những trường hợp phải nhóm/lọc theo ngày địa phương; nhưng thiết kế đó cần xem workload và ràng buộc về tính ổn định của biểu thức timezone.

### 12.2. Ép kiểu tham số thay vì ép kiểu hàng loạt trên cột

Nếu cột là `TIMESTAMPTZ`, hãy truyền tham số có ngữ nghĩa timestamp kèm timezone/instant. Tránh ép cột sang chuỗi để so:

```sql
-- Không nên: thay đổi ý nghĩa so sánh và có thể làm mất lợi thế index.
WHERE TO_CHAR(created_at, 'YYYY-MM-DD') = '2026-11-14'
```

Cách này còn phụ thuộc ngữ cảnh múi giờ và biến kiểu thời gian thành văn bản. Với điều kiện `WHERE`, so sánh **giá trị thời gian với giá trị thời gian** thường là lựa chọn đúng.

### 12.3. Dùng EXPLAIN theo đúng môi trường

Trong PostgreSQL:

```sql
EXPLAIN
SELECT event_id, event_name
FROM lesson120_events
WHERE created_at >= TIMESTAMPTZ '2026-11-14 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-11-15 00:00:00+07';
```

`EXPLAIN` cho biết kế hoạch optimizer dự kiến; kết quả phụ thuộc kích thước bảng, thống kê và chỉ mục. `EXPLAIN ANALYZE` còn **thực thi câu lệnh để đo thời gian thực**, vì vậy chỉ dùng khi biết truy vấn an toàn và phù hợp môi trường.

## 13. Truyền khoảng thời gian từ ứng dụng Java

Trong ứng dụng, thường nhận ngày bắt đầu/kết thúc từ giao diện. Thay vì ghép ngày giờ vào chuỗi SQL, hãy dùng **prepared statement**.

Giả sử người dùng chọn ngày **14/11/2026 theo giờ Việt Nam**. Ứng dụng có thể tính:

- `start` = bắt đầu ngày 14/11 tại `Asia/Ho_Chi_Minh`.
- `end` = bắt đầu ngày 15/11 tại `Asia/Ho_Chi_Minh`.

Sau đó truyền hai giá trị kiểu thời gian vào truy vấn `[start, end)`.

Ví dụ Java với JDBC và PostgreSQL (giả định `Connection conn` đã có):

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneId;

public class EventFilter {
    public static void queryDay(Connection conn) throws SQLException {
        LocalDate selectedDay = LocalDate.of(2026, 11, 14);
        ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");

        // atStartOfDay(zone) xét quy tắc timezone của từng ngày.
        OffsetDateTime start = selectedDay
                .atStartOfDay(businessZone)
                .toOffsetDateTime();

        OffsetDateTime end = selectedDay
                .plusDays(1)
                .atStartOfDay(businessZone)
                .toOffsetDateTime();

        String sql = """
                SELECT event_id, event_name, created_at
                FROM lesson120_events
                WHERE created_at >= ?
                  AND created_at <  ?
                ORDER BY created_at
                """;

        try (PreparedStatement statement = conn.prepareStatement(sql)) {
            statement.setObject(1, start);
            statement.setObject(2, end);

            try (ResultSet results = statement.executeQuery()) {
                while (results.next()) {
                    System.out.println(results.getInt("event_id")
                            + ": " + results.getString("event_name"));
                }
            }
        }
    }
}
```

Ví dụ dùng Java text block (`"""`, Java 15+) và driver JDBC PostgreSQL có hỗ trợ `OffsetDateTime` cho cột `TIMESTAMPTZ`. Với cơ sở dữ liệu/driver khác, kiểu tham số JDBC phù hợp có thể là `LocalDateTime`, `Timestamp` hoặc kiểu riêng của nhà cung cấp; hãy kiểm tra API của driver.

**Vì sao tính `end` bằng `selectedDay.plusDays(1).atStartOfDay(zone)`?** Vì đây là **đầu ngày địa phương kế tiếp**, không phải luôn `start.plusHours(24)` ở những khu vực có đổi giờ mùa hè. Cách tính giúp diễn đạt đúng yêu cầu “toàn bộ ngày theo lịch của người dùng”.

Với cột SQL kiểu `DATE`, có thể truyền `LocalDate`:

```java
LocalDate selectedDay = LocalDate.of(2026, 11, 14);

try (PreparedStatement statement = conn.prepareStatement(
        "SELECT event_id FROM lesson120_events WHERE due_on = ?")) {
    statement.setObject(1, selectedDay);
    // Gọi executeQuery() và xử lý ResultSet như ví dụ trên.
}
```

Prepared statement cũng giúp tránh lỗi định dạng ngày khác nhau giữa máy khách và DBMS, đồng thời giảm nguy cơ SQL injection do nối trực tiếp dữ liệu từ giao diện.

## 14. Điểm khác nhau giữa PostgreSQL, MySQL, SQL Server và SQLite

Cú pháp cơ bản `>=`, `<`, `AND`, `BETWEEN` và `WHERE` đều quen thuộc, nhưng **kiểu thời gian và cách diễn giải timezone khác nhau**.

| DBMS | Kiểu ngày giờ thường dùng | Lưu ý khi lọc khoảng |
|---|---|---|
| PostgreSQL | `DATE`, `TIMESTAMP`, `TIMESTAMPTZ` | `TIMESTAMPTZ` là instant; timezone phiên ảnh hưởng hiển thị/chuyển `::date` |
| MySQL/MariaDB | `DATE`, `DATETIME`, `TIMESTAMP` | `TIMESTAMP` có chuyển đổi theo timezone phiên; `DATETIME` không tự biểu diễn instant như PostgreSQL `TIMESTAMPTZ` |
| SQL Server | `date`, `datetime2`, `datetimeoffset` | `datetimeoffset` có offset, `datetime2` không kèm offset; `timestamp` là `rowversion`, không phải ngày giờ |
| SQLite | Thường lưu `TEXT`, `INTEGER` hoặc `REAL` theo quy ước | Phải thống nhất cách lưu và so sánh; chuỗi có offset khác nhau không nên so từ điển như instant |

### 14.1. MySQL: lọc DATETIME theo khoảng

Giả sử cột `created_at` là `DATETIME` được quy ước lưu giờ địa phương Việt Nam:

```sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= '2026-11-14 00:00:00'
  AND created_at <  '2026-11-15 00:00:00';
```

Nếu cột dùng `TIMESTAMP`, việc diễn giải và hiển thị liên quan đến **múi giờ của session MySQL**; hãy chuẩn hóa hai ranh giới và timezone ứng dụng để tránh lệch kỳ. Không tự xem `DATETIME` và `TIMESTAMP` là hai tên gọi cho cùng một kiểu.

MySQL có `DATE_ADD` để tính mốc kế tiếp:

```sql
-- Ví dụ mốc cuối bằng đầu ngày hôm sau.
SELECT DATE_ADD('2026-11-14', INTERVAL 1 DAY);
```

### 14.2. SQL Server: datetime2 và datetimeoffset

Với cột `created_at` kiểu `datetime2` mang quy ước giờ địa phương:

```sql
SELECT order_id, created_at
FROM dbo.orders
WHERE created_at >= '2026-11-14T00:00:00'
  AND created_at <  '2026-11-15T00:00:00';
```

Nếu dữ liệu là instant với `datetimeoffset`, hãy tạo mốc kiểu có offset rõ ràng và dùng các phép chuyển đổi phù hợp:

```sql
SELECT order_id, created_at
FROM dbo.orders
WHERE created_at >= CAST('2026-11-14T00:00:00+07:00' AS datetimeoffset)
  AND created_at <  CAST('2026-11-15T00:00:00+07:00' AS datetimeoffset);
```

SQL Server có `DATEADD`, `DATEDIFF` và `AT TIME ZONE` để xử lý các ranh giới và múi giờ. Đừng dùng kiểu dữ liệu `timestamp` của SQL Server để lưu ngày giờ: nó là tên cũ của `rowversion`.

### 14.3. SQLite: chuẩn hóa dữ liệu trước khi so sánh

SQLite không có kiểu storage class chuyên biệt cho ngày giờ. Nếu ứng dụng lưu timestamp dưới dạng **chuỗi UTC theo một định dạng cố định** như `YYYY-MM-DD HH:MM:SS`, điều kiện so sánh chuỗi theo định dạng thống nhất có thể phản ánh thứ tự thời gian:

```sql
SELECT event_id, created_at
FROM events
WHERE created_at >= '2026-11-13 17:00:00'
  AND created_at <  '2026-11-14 17:00:00';
```

Hai mốc trên là UTC tương ứng với ngày 14/11 ở Việt Nam. Điều kiện có ý nghĩa **chỉ khi mọi giá trị `created_at` trong cột cùng được lưu chuẩn UTC, cùng định dạng và cùng quy ước độ chính xác**. Nếu trộn chuỗi có timezone offset khác nhau, chuỗi khác độ dài hoặc timestamp số với chuỗi, việc so sánh từ điển có thể sai.

SQLite cũng có các hàm `date()`, `datetime()`, `julianday()`, `unixepoch()` để biến đổi giá trị thời gian. Nhưng việc áp dụng hàm trên từng hàng vẫn có thể ảnh hưởng tới cách dùng chỉ mục thông thường.

## 15. Những lỗi thường gặp khi lọc dữ liệu ngày giờ

### Lỗi 1: Dùng BETWEEN đến 23:59:59

```sql
WHERE created_at BETWEEN '2026-11-14 00:00:00'
                     AND '2026-11-14 23:59:59'
```

Với cột có phần lẻ giây, các sự kiện sau `23:59:59.000000` có thể bị loại. Chọn **đầu ngày hôm sau với `<`**.

### Lỗi 2: Dùng bằng một ngày cho cột có giờ

```sql
-- Không biểu diễn “toàn bộ ngày” nếu created_at chứa cả giờ.
WHERE created_at = DATE '2026-11-14'
```

Điều kiện bằng không bao phủ các thời điểm từ `00:00:00` đến trước `00:00:00` ngày tiếp theo. Cần lọc bằng ranh giới.

### Lỗi 3: So sánh ngày theo múi giờ máy chủ, nhưng báo cáo dùng múi giờ khác

```sql
-- Kết quả phụ thuộc timezone phiên PostgreSQL.
WHERE created_at::date = DATE '2026-11-14'
```

Cần xác định timezone nghiệp vụ rồi tính hai đầu mút thành instant để so sánh.

### Lỗi 4: Nhầm “24 giờ gần nhất” với “hôm nay”

- “24 giờ gần nhất” bắt đầu từ **thời điểm hiện tại trừ 24 giờ**.
- “Hôm nay” bắt đầu từ **00:00 của ngày địa phương hiện tại** và kết thúc ở **00:00 ngày tiếp theo**.

Hai khoảng chỉ hiếm khi trùng nhau. Đừng thay cái này bằng cái kia.

### Lỗi 5: Dùng dấu `<=` ở cuối hai kỳ liên tiếp

```sql
-- Kỳ 1 lấy cả mốc 15/11 00:00.
WHERE created_at >= :day_14_start
  AND created_at <= :day_15_start
```

Nếu kỳ 2 cũng dùng `>= :day_15_start`, bản ghi đúng ranh giới sẽ bị đếm **hai lần**. Dùng `< :day_15_start` cho kỳ 1.

### Lỗi 6: Bọc cột trong hàm rồi kỳ vọng luôn dùng chỉ mục

```sql
WHERE DATE(created_at) = '2026-11-14'
```

Ngoài vấn đề timezone/ngữ nghĩa tùy DBMS, cách bọc cột trong hàm có thể làm chỉ mục thông thường ít hữu ích. Nếu lọc theo một ngày cụ thể, ưu tiên điều kiện **trực tiếp trên cột với hai mốc có kiểu tương thích**.

### Lỗi 7: Bỏ quên giá trị NULL hoặc dấu ngoặc khi ghép điều kiện

`NULL` không thỏa phép so sánh khoảng; `OR created_at IS NULL` phải được thêm **chủ đích**. Khi kết hợp `AND` và `OR`, luôn đặt ngoặc để diễn đạt đúng nhóm điều kiện.

### Lỗi 8: Giả định một ngày luôn đúng 24 giờ

Ở những vùng có DST, khoảng từ nửa đêm địa phương đến nửa đêm tiếp theo có thể kéo dài **23 hoặc 25 giờ**. Khi lọc theo ngày địa phương, tạo hai mốc theo **tên múi giờ và ngày lịch**, thay vì luôn cộng 24 giờ vào đầu kỳ.

### Lỗi 9: Không thống nhất kiểu dữ liệu của tham số

So sánh `TIMESTAMPTZ` với chuỗi ngày giờ không có offset có thể khiến DBMS diễn giải theo timezone phiên. Hãy truyền tham số `OffsetDateTime`/instant thích hợp hoặc ép kiểu rõ ràng theo DBMS, thay vì để hệ thống tự đoán ý nghĩa dữ liệu.

## 16. Bài tập thực hành có lời giải

Các bài sau sử dụng bảng `lesson120_events` đã tạo ở phần 2. Tự dự đoán kết quả trước khi xem đáp án.

### Bài 1: Lọc sự kiện ngày 14/11 theo giờ Việt Nam

**Yêu cầu:** Trả về `event_id`, `event_name` của các sự kiện có `created_at` trong ngày 14/11/2026 theo giờ Việt Nam.

```sql
SELECT event_id, event_name
FROM lesson120_events
WHERE created_at >= TIMESTAMPTZ '2026-11-14 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-11-15 00:00:00+07'
ORDER BY event_id;
```

**Đáp án:** các `event_id` là **2, 3, 4**.

### Bài 2: Tìm sự kiện trong khoảng 09:00–10:00

**Yêu cầu:** Lấy sự kiện xảy ra từ 09:00 đến trước 10:00 ngày 14/11, theo giờ Việt Nam.

```sql
SELECT event_id, event_name
FROM lesson120_events
WHERE created_at >= TIMESTAMPTZ '2026-11-14 09:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-11-14 10:00:00+07';
```

**Đáp án:** chỉ sự kiện **3**.

### Bài 3: Lọc theo DATE

**Yêu cầu:** Chọn những sự kiện có `due_on` từ ngày 14/11 đến hết 15/11.

```sql
SELECT event_id, event_name, due_on
FROM lesson120_events
WHERE due_on >= DATE '2026-11-14'
  AND due_on <  DATE '2026-11-16'
ORDER BY due_on, event_id;
```

**Đáp án:** `event_id` là **2, 3, 4, 5, 7**. Sự kiện **6** có `due_on NULL` nên không xuất hiện.

### Bài 4: Phát hiện lỗ hổng của BETWEEN

**Yêu cầu:** Vì sao truy vấn dưới đây không lấy sự kiện 4?

```sql
SELECT event_id
FROM lesson120_events
WHERE created_at BETWEEN
      TIMESTAMPTZ '2026-11-14 00:00:00+07'
  AND TIMESTAMPTZ '2026-11-14 23:59:59+07';
```

**Đáp án:** sự kiện 4 xảy ra lúc `23:59:59.999999+07`, lớn hơn giới hạn trên `23:59:59+07`. Sửa mốc cuối thành **đầu ngày 15/11** và dùng `<`:

```sql
WHERE created_at >= TIMESTAMPTZ '2026-11-14 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-11-15 00:00:00+07'
```

### Bài 5: Lọc theo giờ UTC thay cho giờ Việt Nam

**Yêu cầu:** Viết lại khoảng ngày 14/11 theo giờ Việt Nam dưới dạng **hai mốc UTC**.

```sql
SELECT event_id, event_name
FROM lesson120_events
WHERE created_at >= TIMESTAMPTZ '2026-11-13 17:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-11-14 17:00:00+00'
ORDER BY event_id;
```

**Đáp án:** vẫn là **2, 3, 4** vì hai khoảng mô tả đúng cùng tập instant.

### Bài 6: Đếm số sự kiện có thời điểm và sự kiện thiếu thời điểm

```sql
SELECT
    COUNT(*) AS all_rows,
    COUNT(created_at) AS rows_with_created_at,
    COUNT(*) - COUNT(created_at) AS rows_missing_created_at
FROM lesson120_events;
```

**Đáp án:** `all_rows = 7`; `rows_with_created_at = 6`; `rows_missing_created_at = 1`. Bộ lọc thời gian bình thường không tự đưa sự kiện thiếu ngày giờ vào một kỳ.

### Bài 7: Tìm khoảng giao nhau

Có khoảng hiệu lực `[2026-11-14 08:00, 2026-11-14 10:00)` và khoảng truy vấn `[2026-11-14 10:00, 2026-11-14 12:00)`, cùng timezone. Hai khoảng có giao nhau không?

**Đáp án:** **Không**. Mốc 10:00 là **đầu khoảng thứ hai** nhưng đã bị **loại trừ khỏi khoảng thứ nhất**. Điều kiện chồng lấp `record_start < query_end AND record_end > query_start` trả sai khi `record_end = query_start`.

### Bài 8: Cửa sổ 24 giờ so với ngày lịch

Một báo cáo được chạy lúc 10:00 ngày 15/11 ở Việt Nam.

1. “24 giờ gần nhất” bắt đầu lúc nào?
2. “Toàn bộ ngày 14/11” bắt đầu và kết thúc lúc nào?
3. Vì sao chúng không giống nhau?

**Đáp án:**

1. Từ **10:00 ngày 14/11** đến trước **10:00 ngày 15/11**.
2. Từ **00:00 ngày 14/11** đến trước **00:00 ngày 15/11**.
3. Cửa sổ đầu có độ dài theo **thời lượng tính từ thời điểm chạy**; cửa sổ sau theo **ranh giới ngày trên lịch**.

### Bài 9: Kết hợp điều kiện trạng thái

Giả sử thêm cột `status` cho bảng đơn hàng. Yêu cầu: lấy đơn ở trạng thái `PAID` hoặc `COMPLETED` **trong tháng 11/2026** theo giờ Việt Nam.

```sql
SELECT order_id, status, created_at
FROM orders
WHERE status IN ('PAID', 'COMPLETED')
  AND created_at >= TIMESTAMPTZ '2026-11-01 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-12-01 00:00:00+07';
```

**Giải thích:** hai bộ lọc trạng thái và khoảng thời gian phải cùng đúng; tránh ghép `OR` lỏng lẻo khiến một trạng thái bị lấy ở mọi ngày. Đây là ví dụ trên bảng `orders` giả định của hệ thống, không thuộc dữ liệu mẫu `lesson120_events`.

## 17. Bảng đối chiếu nhanh

| Mục tiêu | Cách viết phù hợp | Điều cần chú ý |
|---|---|---|
| Tìm đúng một ngày của cột `DATE` | `due_on = DATE '2026-11-14'` | `DATE` không có giờ |
| Tìm toàn bộ ngày trên cột timestamp | `created_at >= start AND created_at < next_day_start` | Tính đầu ngày theo đúng timezone |
| Lấy toàn bộ tháng | `>= first_day AND < first_day_of_next_month` | Không cần đoán giờ cuối tháng |
| Tìm 24 giờ đã trôi qua | `>= now - 24 hours AND < now` | Khác ngày lịch |
| Tìm 7 ngày lịch gồm hôm nay | `>= today - 6 days AND < tomorrow` | Phụ thuộc timezone/ngày nghiệp vụ |
| Lấy thời điểm đúng một mốc | `created_at = exact_timestamp` | Không tương đương lấy cả ngày |
| Tìm bản ghi thiếu thời điểm | `created_at IS NULL` | `WHERE created_at >= ...` không lấy NULL |
| Tìm khoảng hiệu lực giao với kỳ báo cáo | `valid_from < query_end AND (valid_to > query_start OR valid_to IS NULL)` | Hai khoảng được quy ước là `[start, end)` |
| Giúp bộ lọc dùng chỉ mục thời gian | So sánh trực tiếp cột với hai biên | Tránh bọc cột trong hàm khi không cần |

**Nguyên tắc quan trọng nhất:** với cột có cả ngày và giờ, hãy xác định **mốc bắt đầu thuộc khoảng**, **mốc kết thúc không thuộc khoảng** và **múi giờ mà một ngày được định nghĩa**. Sau đó viết `WHERE timestamp_column >= start AND timestamp_column < end` với hai tham số thời gian có kiểu phù hợp. Cách này giúp việc lọc theo ngày, giờ, tuần, tháng và các kỳ liên tiếp rõ ràng, ít sai ranh giới và thường thuận lợi cho việc tối ưu hóa truy vấn.


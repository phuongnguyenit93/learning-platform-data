# Phân biệt ngày lịch, giờ trong ngày, khoảng thời gian và thời điểm

Một đơn hàng có ngày giao dự kiến, một cửa hàng có giờ mở cửa, một phiên đăng nhập có thời điểm bắt đầu và một báo cáo cần tính số phút xử lý. Các giá trị này đều liên quan đến ngày giờ nhưng mang ý nghĩa khác nhau. Nếu dùng một kiểu dữ liệu cho tất cả, ứng dụng có thể tính sai thời lượng, lệch giờ khi đổi múi giờ hoặc không thể phân biệt hai thời điểm xảy ra trong một lần chuyển giờ mùa hè.

Trong module **DATABASE_MYSQL**, xử lý ngày giờ đúng là nền tảng cho nghiệp vụ đơn hàng, lịch hẹn, thanh toán, báo cáo và vận hành. Bài học này phân biệt ngày lịch, giờ trong ngày, khoảng thời gian và thời điểm; sau đó liên hệ chúng với các kiểu `DATE`, `TIME`, `DATETIME`, `TIMESTAMP`, múi giờ và Java/JDBC.

## 1. Bốn ý nghĩa khác nhau của dữ liệu ngày giờ

Trước khi chọn kiểu SQL, hãy xác định dữ liệu đại diện cho điều gì:

| Ý nghĩa | Mô tả | Ví dụ nghiệp vụ | Kiểu MySQL thường dùng |
|---|---|---|---|
| Ngày lịch (calendar date) | Một ngày trên lịch, không nhất thiết gắn với giờ hoặc múi giờ | Ngày sinh, ngày ký hợp đồng, ngày nghỉ | `DATE` |
| Giờ trong ngày (time of day) | Vị trí trên đồng hồ trong một ngày | Cửa hàng mở lúc 08:30, cuộc hẹn lúc 14:00 | `TIME` nếu chỉ cần giờ/phút/giây |
| Khoảng thời gian (duration) | Lượng thời gian đã trôi qua giữa hai mốc | Một tác vụ chạy 90 phút, thời gian xử lý đơn | Số nguyên theo đơn vị đã chọn, hoặc `TIME` cho khoảng ngắn phù hợp |
| Thời điểm (instant) | Một điểm xác định trên dòng thời gian, có thể quy đổi sang UTC | Đơn hàng được tạo lúc nào, giao dịch thanh toán xảy ra lúc nào | Thường dùng `TIMESTAMP` theo quy ước múi giờ rõ ràng |

Ngoài ra, một **khoảng ngày/giờ** trong truy vấn thường được biểu diễn bằng hai mốc bắt đầu và kết thúc, ví dụ từ đầu ngày 10 đến đầu ngày 11. Nó không phải một kiểu dữ liệu riêng; đó là một điều kiện phạm vi trên `DATE`, `DATETIME` hoặc `TIMESTAMP`.

Ví dụ:

- Ngày sinh `1995-04-18` là ngày lịch. Không cần chuyển ngày sinh sang UTC.
- Cửa hàng mở lúc `08:30:00` là giờ trong ngày. Mỗi ngày cửa hàng có thể mở cùng giờ đó.
- Một tác vụ chạy `5400` giây là duration. Nó không phải thời điểm `01:30:00` sau nửa đêm.
- Một thanh toán xảy ra tại `2026-11-19T02:15:30Z` là instant. Máy chủ ở Việt Nam có thể hiển thị nó thành `09:15:30` theo UTC+07:00.

## 2. Các kiểu ngày giờ trong MySQL

MySQL có các kiểu temporal chính sau:

| Kiểu | Lưu ý nghĩa | Miền giá trị thường gặp | Có tự chuyển theo time zone? |
|---|---|---|---|
| `DATE` | Ngày lịch: năm, tháng, ngày | `1000-01-01` đến `9999-12-31` | Không |
| `TIME` | Giờ/phút/giây hoặc lượng thời gian | `-838:59:59` đến `838:59:59` | Không |
| `DATETIME` | Ngày và giờ theo lịch, không gắn múi giờ | `1000-01-01 00:00:00` đến `9999-12-31 23:59:59` | Không |
| `TIMESTAMP` | Thời điểm được quy đổi qua UTC khi ghi/đọc | `1970-01-01 00:00:01` UTC đến `2038-01-19 03:14:07` UTC trong MySQL 8.0 | Có, theo session time zone |

Các kiểu `TIME`, `DATETIME` và `TIMESTAMP` hỗ trợ phần giây lẻ với độ chính xác từ 0 đến 6 chữ số, ví dụ `DATETIME(3)` lưu đến mili giây và `DATETIME(6)` lưu đến micro giây. Nếu không chỉ định precision, mặc định là 0.

### `DATE` — ngày lịch

Dùng `DATE` khi chỉ quan tâm ngày, không quan tâm thời điểm trong ngày:

```sql
CREATE TABLE employees (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name VARCHAR(150) NOT NULL,
    birth_date DATE,
    contract_date DATE NOT NULL,
    PRIMARY KEY (id)
);
```

Không nên lưu ngày sinh dưới dạng `DATETIME` rồi gán `00:00:00` nếu nghiệp vụ không có ý nghĩa về giờ. `DATE` thể hiện rõ ý nghĩa và tránh phát sinh xử lý múi giờ không cần thiết.

### `TIME` — giờ trong ngày hoặc lượng thời gian

`TIME` thường được dùng cho giờ mở cửa, giờ đóng cửa hoặc một mốc giờ lặp lại mỗi ngày:

```sql
CREATE TABLE store_hours (
    store_id BIGINT UNSIGNED NOT NULL,
    opens_at TIME NOT NULL,
    closes_at TIME NOT NULL,
    PRIMARY KEY (store_id)
);
```

MySQL `TIME` có miền giá trị rộng hơn 24 giờ và có thể âm, nên nó cũng có thể biểu diễn duration ngắn. Ví dụ `TIME '36:00:00'` là 36 giờ, không phải 12 giờ trưa ngày hôm sau. Không dùng `TIME` làm instant vì nó không có ngày và múi giờ.

### `DATETIME` — ngày giờ theo lịch

`DATETIME` lưu ngày và giờ như được cung cấp, không tự chuyển theo múi giờ session:

```sql
CREATE TABLE appointments (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    starts_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id)
);
```

Kiểu này phù hợp cho một lịch hẹn được xác định theo giờ địa phương của cơ sở, nếu ứng dụng đồng thời lưu hoặc biết múi giờ áp dụng. Ví dụ, lịch hẹn lúc 09:00 tại Thành phố Hồ Chí Minh vẫn là 09:00 địa phương dù người xem lịch đang ở một quốc gia khác.

Vì `DATETIME` không giữ offset hoặc tên múi giờ, nếu cần diễn giải một lịch hẹn theo vùng địa lý, hãy lưu thêm zone ID như `Asia/Ho_Chi_Minh` ở cột riêng hoặc metadata phù hợp.

### `TIMESTAMP` — thời điểm

`TIMESTAMP` biểu diễn một thời điểm. Khi ghi, MySQL chuyển giá trị từ múi giờ session sang UTC để lưu; khi đọc, MySQL chuyển từ UTC sang múi giờ session hiện tại. Vì vậy cùng một giá trị có thể hiển thị khác nhau trong hai session có `time_zone` khác nhau.

```sql
CREATE TABLE payments (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    amount DECIMAL(15,2) NOT NULL,
    paid_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id)
);
```

Đây là lựa chọn thường gặp cho `created_at`, `updated_at` hoặc thời điểm thanh toán, khi hệ thống có quy ước múi giờ nhất quán. Cần nhớ `TIMESTAMP` có miền năm hẹp hơn `DATETIME`; nếu nghiệp vụ cần ngày ngoài miền của `TIMESTAMP`, hãy cân nhắc `DATETIME` và quy ước lưu UTC rõ ràng.

## 3. `DATETIME` khác `TIMESTAMP` ở đâu?

Hai kiểu này có cùng hình thức hiển thị phổ biến `YYYY-MM-DD HH:MM:SS`, nhưng ý nghĩa và hành vi khác nhau:

| Tiêu chí | `DATETIME` | `TIMESTAMP` |
|---|---|---|
| Ý nghĩa | Ngày giờ trên lịch | Một instant trên dòng thời gian |
| Chuyển đổi theo `time_zone` session | Không | Có khi ghi và đọc |
| Lưu offset hoặc tên múi giờ | Không | Không lưu nguyên tên/offset; lưu instant theo cơ chế UTC |
| Miền năm | 1000 đến 9999 | `1970-01-01 00:00:01` UTC đến `2038-01-19 03:14:07` UTC trong MySQL 8.0 |
| Dùng cho | Giờ hẹn địa phương, giờ làm việc theo lịch | Thời điểm tạo bản ghi, thanh toán, sự kiện hệ thống |

Ví dụ với `DATETIME`:

```sql
SET time_zone = '+00:00';
SELECT CAST('2026-11-19 09:00:00' AS DATETIME) AS local_schedule;

SET time_zone = '+07:00';
SELECT CAST('2026-11-19 09:00:00' AS DATETIME) AS local_schedule;
```

Giá trị `DATETIME` vẫn là `2026-11-19 09:00:00` ở cả hai session. MySQL không tự cộng hoặc trừ 7 giờ cho `DATETIME`.

Ví dụ với `TIMESTAMP`:

```sql
CREATE TEMPORARY TABLE timestamp_demo (
    event_at TIMESTAMP NOT NULL
);

SET time_zone = '+00:00';
INSERT INTO timestamp_demo VALUES ('2026-11-19 02:00:00');
SELECT event_at FROM timestamp_demo;

SET time_zone = '+07:00';
SELECT event_at FROM timestamp_demo;
```

Giá trị đọc ở session UTC+07:00 sẽ hiển thị `2026-11-19 09:00:00`, vì cùng instant được quy đổi sang múi giờ session. Ví dụ này dùng bảng tạm để có thể chạy trong một session thử nghiệm mà không tạo bảng nghiệp vụ lâu dài.

## 4. Múi giờ của MySQL

MySQL có nhiều thiết lập múi giờ:

| Biến | Ý nghĩa |
|---|---|
| `system_time_zone` | Múi giờ hệ điều hành mà máy chủ nhận diện khi khởi động |
| `time_zone` cấp GLOBAL | Mặc định được dùng cho session mới |
| `time_zone` cấp SESSION | Múi giờ của kết nối hiện tại; ảnh hưởng chuyển đổi `TIMESTAMP` và các hàm ngày giờ liên quan |

Kiểm tra:

```sql
SELECT
    @@global.time_zone AS global_time_zone,
    @@session.time_zone AS session_time_zone,
    @@system_time_zone AS system_time_zone,
    NOW() AS session_now,
    UTC_TIMESTAMP() AS utc_now;
```

Giá trị `SYSTEM` trong `time_zone` nghĩa là session dùng múi giờ hệ thống. Để ứng dụng xử lý thời điểm nhất quán, một quy ước phổ biến là đặt session MySQL ở UTC:

```sql
SET time_zone = '+00:00';
```

Offset `+00:00` không cần bảng múi giờ. Nếu dùng tên vùng như `Asia/Ho_Chi_Minh`, máy chủ cần có timezone tables được nạp và cập nhật. Tên vùng địa lý có quy tắc lịch sử và có thể thay đổi theo dữ liệu IANA; offset cố định như `+07:00` không mang thông tin quy tắc DST hoặc thay đổi pháp lý trong tương lai.

`SET GLOBAL time_zone` chỉ đặt mặc định cho kết nối mới, không thay đổi session đang tồn tại. Với connection pool, mỗi connection có session riêng; cần cấu hình timezone khi tạo/khởi tạo connection hoặc thiết lập trong quy trình cấp connection của pool.

## 5. Giờ mùa hè (DST) và giờ địa phương không duy nhất

Một số vùng địa lý điều chỉnh đồng hồ theo Daylight Saving Time (DST). Khi chuyển sang giờ mùa hè, một số giờ địa phương có thể không tồn tại; khi quay về giờ chuẩn, một khoảng giờ có thể xuất hiện hai lần.

Ví dụ minh họa tại một vùng có DST:

- Khi đồng hồ nhảy từ 01:59 lên 03:00, giờ địa phương `02:30` không tồn tại trong ngày đó.
- Khi đồng hồ lùi từ 02:00 về 01:00, giờ địa phương `01:30` có thể tương ứng với hai instant khác nhau.

Một `DATETIME` đơn lẻ như `2026-11-01 01:30:00` không thể nói nó thuộc lần 01:30 nào nếu vùng đó lặp giờ. Để lưu lịch hẹn địa phương trong vùng có DST, nên lưu giờ địa phương cùng tên vùng IANA và quy tắc xử lý trường hợp giờ không tồn tại/trùng lặp. Để lưu một sự kiện đã thực sự xảy ra, hãy lưu instant theo UTC, chẳng hạn `TIMESTAMP` với session UTC hoặc `DATETIME` theo quy ước UTC rõ ràng.

Đừng chỉ lưu `-05:00` hoặc `+07:00` nếu nghiệp vụ cần biết vùng địa lý. Offset chỉ mô tả độ lệch tại một thời điểm; `America/New_York` hoặc `Asia/Ho_Chi_Minh` mô tả vùng với bộ quy tắc thời gian tương ứng.

## 6. Duration và phép toán ngày giờ

Duration là lượng thời gian trôi qua giữa hai instant. Có thể tính từ hai mốc bằng SQL:

```sql
SELECT TIMESTAMPDIFF(SECOND,
    '2026-11-19 09:00:00',
    '2026-11-19 10:30:00') AS elapsed_seconds;
```

Kết quả là `5400` giây. `TIMESTAMPDIFF(unit, start, end)` trả số đơn vị nguyên theo unit được yêu cầu; nếu chọn `MINUTE`, phần giây lẻ không đủ một phút sẽ bị bỏ qua.

Các hàm thường dùng:

| Hàm | Công dụng | Ví dụ |
|---|---|---|
| `DATEDIFF(end, start)` | Chênh lệch ngày lịch, bỏ qua phần giờ | `DATEDIFF('2026-11-20','2026-11-19')` trả `1` |
| `TIMEDIFF(expr1, expr2)` | Hiệu giữa hai giá trị giờ/ngày giờ tương thích, trả `TIME` | `TIMEDIFF('10:30:00','09:00:00')` trả `01:30:00` |
| `TIMESTAMPDIFF(unit, start, end)` | Chênh lệch theo đơn vị chỉ định | `TIMESTAMPDIFF(MINUTE, start, end)` |
| `TIMESTAMPADD(unit, amount, datetime)` | Cộng một lượng thời gian vào mốc | `TIMESTAMPADD(DAY, 7, CURRENT_DATE())` |
| `DATE_ADD(date, INTERVAL expr unit)` | Cộng khoảng thời gian | `DATE_ADD(CURRENT_DATE(), INTERVAL 1 MONTH)` |

`INTERVAL` trong biểu thức như `INTERVAL 7 DAY` không phải một kiểu cột để lưu duration tùy ý. Nó là cú pháp mô tả lượng cần cộng/trừ với một giá trị temporal.

### Nên lưu duration bằng gì?

- Với duration ngắn, có giới hạn rõ và phù hợp miền `TIME`, có thể dùng `TIME` hoặc `TIME(3)`.
- Với thời lượng dài, thời gian tích lũy hoặc cần đơn vị chính xác, thường dùng số nguyên như `BIGINT` lưu milliseconds/microseconds/seconds theo một quy ước rõ ràng.
- Với thời lượng có phần thập phân hoặc cần quy đổi đơn vị, có thể dùng `DECIMAL` theo đơn vị nghiệp vụ.

Ví dụ lưu thời lượng tác vụ bằng milliseconds:

```sql
CREATE TABLE job_runs (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    started_at TIMESTAMP(6) NOT NULL,
    duration_ms BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (id)
);
```

Không dùng `TIMESTAMP` để lưu duration vì timestamp là một điểm trên dòng thời gian. Cũng không dùng `TIME` cho duration hàng tháng hoặc hàng năm vì tháng và năm có độ dài thay đổi.

## 7. Truy vấn theo khoảng thời gian và sử dụng index

Khi lọc các bản ghi theo ngày, nên dùng khoảng nửa mở: bao gồm thời điểm bắt đầu và loại trừ thời điểm kết thúc. Ví dụ, lấy toàn bộ đơn hàng trong ngày 19/11/2026:

```sql
SELECT id, created_at, total_amount
FROM orders
WHERE created_at >= '2026-11-19 00:00:00'
  AND created_at <  '2026-11-20 00:00:00';
```

Điều kiện `>= start AND < next_start` tránh phải đoán giá trị cuối ngày như `23:59:59.999999`, đồng thời hoạt động tốt với độ chính xác fractional seconds khác nhau.

Nếu có index trên `created_at`, cách lọc trực tiếp theo khoảng thường cho phép MySQL dùng range scan. Tránh bọc cột index trong hàm nếu không cần:

```sql
-- Thường khó tận dụng index trên created_at hiệu quả
SELECT *
FROM orders
WHERE DATE(created_at) = '2026-11-19';

-- Dùng khoảng thời gian nửa mở
SELECT *
FROM orders
WHERE created_at >= '2026-11-19 00:00:00'
  AND created_at <  '2026-11-20 00:00:00';
```

Nếu cột là `TIMESTAMP`, hai mốc literal được diễn giải theo `time_zone` session. Khi tính báo cáo theo ngày địa phương, hãy chuyển ranh giới ngày địa phương sang đúng instant bắt đầu/kết thúc theo vùng múi giờ, rồi truy vấn bằng các mốc đó. Không mặc định một ngày ở mọi vùng luôn dài đúng 24 giờ khi có DST.

## 8. Định dạng và phân tích ngày giờ

Định dạng ISO phổ biến giúp tránh nhầm ngày/tháng:

- Ngày: `YYYY-MM-DD`, ví dụ `2026-11-19`.
- Ngày giờ: `YYYY-MM-DD HH:MM:SS`, ví dụ `2026-11-19 09:15:30`.
- Instant dạng ISO 8601 có offset: `2026-11-19T02:15:30Z` hoặc `2026-11-19T09:15:30+07:00`.

Trong SQL, có thể định dạng kết quả bằng `DATE_FORMAT()`:

```sql
SELECT DATE_FORMAT(created_at, '%Y-%m-%d %H:%i:%s') AS created_text
FROM orders;
```

`%i` là phút; `%m` là tháng. Đây là chi tiết dễ nhầm vì trong `DATE_FORMAT`, `%M` là tên tháng, `%i` mới là phút.

Nếu cần phân tích một chuỗi theo định dạng đã biết, dùng `STR_TO_DATE()`:

```sql
SELECT STR_TO_DATE('19/11/2026 09:15:30', '%d/%m/%Y %H:%i:%s');
```

Không dựa vào định dạng ngày mơ hồ như `03/04/2026` vì có thể được hiểu là ngày 3 tháng 4 hoặc ngày 4 tháng 3. Ở tầng ứng dụng, dùng kiểu temporal và bind parameter qua JDBC thay vì ghép chuỗi ngày giờ vào SQL.

## 9. Ngày giờ hiện tại và giá trị mặc định

MySQL cung cấp các hàm lấy ngày giờ hiện tại:

| Hàm | Kết quả |
|---|---|
| `CURRENT_DATE()` / `CURDATE()` | Ngày hiện tại theo session time zone |
| `CURRENT_TIME()` / `CURTIME()` | Giờ hiện tại theo session time zone |
| `NOW()` / `CURRENT_TIMESTAMP()` | Ngày giờ hiện tại theo session time zone |
| `UTC_DATE()` | Ngày hiện tại theo UTC |
| `UTC_TIME()` | Giờ hiện tại theo UTC |
| `UTC_TIMESTAMP()` | Ngày giờ hiện tại theo UTC |

Ví dụ tạo thời điểm tự động khi thêm bản ghi:

```sql
CREATE TABLE audit_events (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_type VARCHAR(80) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id)
);
```

`NOW()` và `CURRENT_TIMESTAMP()` trong một câu lệnh thường trả cùng thời điểm tại lúc câu lệnh bắt đầu. Kết quả `TIMESTAMP` khi hiển thị vẫn phụ thuộc session time zone. Nếu cần log UTC nhất quán, hãy đặt session ở UTC và kiểm tra điều đó trên các connection của ứng dụng.

## 10. Ánh xạ kiểu ngày giờ từ Java sang MySQL

Java Time API có các kiểu riêng cho từng ý nghĩa. Chọn kiểu Java theo đúng ý nghĩa của cột:

| Ý nghĩa | Java | MySQL thường dùng |
|---|---|---|
| Ngày lịch | `LocalDate` | `DATE` |
| Giờ trong ngày | `LocalTime` | `TIME` |
| Ngày giờ địa phương không kèm múi giờ | `LocalDateTime` | `DATETIME` |
| Thời điểm tuyệt đối | `Instant` | `TIMESTAMP` theo quy ước UTC |
| Khoảng thời gian | `Duration` | Số nguyên theo đơn vị hoặc `TIME` nếu nằm trong miền phù hợp |
| Múi giờ địa lý | `ZoneId` | Lưu thêm chuỗi zone ID, ví dụ `Asia/Ho_Chi_Minh` |

Ví dụ với entity Java:

```java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;

public class Appointment {
    private LocalDate appointmentDate;
    private LocalTime startsAt;
    private LocalDateTime localStartsAt;
}
```

Với thời điểm sự kiện, dùng `Instant` để giữ nghĩa tuyệt đối:

```java
import java.time.Instant;

public class PaymentEvent {
    private Instant paidAt;
}
```

Khi dùng JDBC, `LocalDate`, `LocalTime` và `LocalDateTime` có thể bind bằng `setObject()` với MySQL Connector/J hỗ trợ JDBC 4.2. Với `Instant`, hãy chuyển đổi qua `Timestamp` và dùng UTC nhất quán giữa driver và session:

```java
Instant eventTime = Instant.now();
Calendar utc = Calendar.getInstance(TimeZone.getTimeZone("UTC"));

try (PreparedStatement statement = connection.prepareStatement(
        "INSERT INTO audit_events (event_type, created_at) VALUES (?, ?)")) {
    statement.setString(1, "PAYMENT_RECEIVED");
    statement.setTimestamp(2, Timestamp.from(eventTime), utc);
    statement.executeUpdate();
}
```

Ví dụ cần import `java.sql.PreparedStatement`, `java.sql.Timestamp`, `java.util.Calendar`, `java.util.TimeZone` và `java.time.Instant`. Hãy cấu hình session MySQL theo UTC hoặc cấu hình Connector/J một cách nhất quán; `Calendar` giúp JDBC diễn giải giá trị timestamp theo múi giờ được chỉ định. Khi đọc lại, sử dụng `getTimestamp(column, utc).toInstant()` để khôi phục instant.

Đối với lịch hẹn tương lai theo vùng địa lý, không chỉ lưu `LocalDateTime` rồi giả định đó là instant. Hãy lưu giờ địa phương cùng `ZoneId`, sau đó xác định instant theo quy tắc vùng tại thời điểm áp dụng. Quy tắc DST có thể làm giờ địa phương bị thiếu hoặc lặp.

## 11. Kiểm soát dữ liệu ngày giờ không hợp lệ

MySQL có thể xử lý ngày không hợp lệ khác nhau tùy `sql_mode`. Chế độ strict thường giúp từ chối giá trị không hợp lệ thay vì âm thầm điều chỉnh hoặc chấp nhận ngày zero trong một số cấu hình.

Kiểm tra:

```sql
SELECT @@SESSION.sql_mode;
```

Các giá trị như `2026-02-30`, `2026-13-01` hoặc ngày zero `0000-00-00` không nên được dùng làm dữ liệu nghiệp vụ hợp lệ. Hãy kiểm tra đầu vào ở Java và dựa vào SQL mode phù hợp để database từ chối dữ liệu sai. Không dùng ngày zero thay cho `NULL`: `NULL` thể hiện chưa biết hoặc không có giá trị, còn ngày zero là một giá trị đặc biệt có hành vi phụ thuộc cấu hình.

Với dữ liệu nhập từ file hoặc hệ thống cũ, hãy xác định định dạng, timezone và tính hợp lệ trước khi import. Không tự động diễn giải một timestamp thiếu offset là UTC hoặc giờ địa phương nếu nguồn dữ liệu không nói rõ.

## 12. Bài tập thực hành

Thực hiện trên database thử nghiệm:

1. Tạo bảng nhân viên với `birth_date DATE`, bảng lịch cửa hàng với `opens_at TIME`, bảng lịch hẹn với `starts_at DATETIME` và bảng sự kiện với `created_at TIMESTAMP`.
2. Chạy `SELECT @@session.time_zone, NOW(), UTC_TIMESTAMP()` khi session dùng `+00:00`, sau đó đổi sang `+07:00` và so sánh.
3. Lưu cùng một giá trị vào `DATETIME` và `TIMESTAMP`, đọc lại ở hai session có múi giờ khác nhau; giải thích vì sao chỉ `TIMESTAMP` đổi cách hiển thị.
4. Tính duration giữa hai mốc bằng `TIMESTAMPDIFF(SECOND, start, end)`; so sánh với `DATEDIFF()` và `TIMEDIFF()`.
5. Viết truy vấn lấy đơn hàng trong một ngày bằng điều kiện `>= start AND < next_start`, sau đó xem kế hoạch với `EXPLAIN` khi cột có index.
6. Kết nối bằng Java, ánh xạ `LocalDate`, `LocalTime`, `LocalDateTime` và `Instant`; xác minh giá trị trước và sau khi lưu.
7. Mô tả cách lưu một lịch hẹn định kỳ tại vùng có DST bằng giờ địa phương và `ZoneId`, đồng thời giải thích vì sao `DATETIME` đơn lẻ không đủ.

Bạn hoàn thành bài khi phân biệt được ngày lịch, giờ trong ngày, duration và instant; chọn đúng `DATE`, `TIME`, `DATETIME` hoặc `TIMESTAMP`; hiểu tác động của session time zone; và truyền ngày giờ qua Java/JDBC mà không làm mất ý nghĩa. Luôn bắt đầu từ ý nghĩa nghiệp vụ rồi mới chọn kiểu dữ liệu và quy ước múi giờ.

# connectionTimeZone, preserveInstants và đồng bộ múi giờ JDBC

Khi ứng dụng Java kết nối MySQL qua Connector/J, một giá trị thời gian có thể đi qua nhiều lớp múi giờ: JVM, cấu hình của Connector/J, múi giờ session MySQL và kiểu cột lưu trữ. Nếu các lớp này không được hiểu rõ, cùng một `Timestamp` có thể hiển thị thành giờ khác nhau giữa ứng dụng và SQL client; dữ liệu ghi vào `TIMESTAMP` có thể bị lệch giờ; còn truy vấn chạy qua connection pool có thể nhận session time zone không như mong đợi.

Connector/J cung cấp các thuộc tính `connectionTimeZone`, `preserveInstants` và `forceConnectionTimeZoneToSession` để điều khiển cách driver diễn giải thời gian và đồng bộ session. Chúng giải quyết những phần khác nhau của bài toán. Cần kết hợp chúng với hiểu biết về `TIMESTAMP`, `DATETIME`, Java time API và cấu hình `time_zone` của MySQL.

## 1. Múi giờ xuất hiện ở những lớp nào?

Một kết nối JDBC có ít nhất bốn khái niệm thời gian cần phân biệt:

| Lớp | Nguồn cấu hình | Vai trò |
|---|---|---|
| JVM default time zone | `user.timezone`, OS/container hoặc `TimeZone.setDefault()` | Múi giờ mặc định mà code Java và một số API cũ sử dụng |
| Connector/J connection time zone | Thuộc tính `connectionTimeZone` | Múi giờ driver dùng khi chuyển đổi giá trị thời gian giữa Java và MySQL |
| MySQL session time zone | `@@session.time_zone` | Quy tắc MySQL dùng khi đọc/ghi `TIMESTAMP` và thực thi các hàm thời gian phụ thuộc session |
| MySQL server/system time zone | `@@global.time_zone`, `@@system_time_zone` | Mặc định cho session mới và múi giờ hệ điều hành mà server nhận diện |

Các lớp này có thể trùng nhau, nhưng không tự động luôn trùng. Ví dụ JVM chạy ở `Asia/Ho_Chi_Minh`, MySQL session dùng `SYSTEM` theo UTC trên máy chủ, còn ứng dụng muốn quy ước tất cả instant theo UTC. Nếu không cấu hình rõ, việc chuyển đổi có thể dựa trên các mặc định khác nhau.

Trước khi sửa lỗi, cần xác định dữ liệu đang biểu diễn điều gì:

- **Instant:** một thời điểm tuyệt đối trên dòng thời gian, ví dụ thời điểm thanh toán đã được xác nhận. Giá trị này không đổi khi người dùng ở múi giờ khác.
- **Local date-time:** giờ trên đồng hồ tại một địa điểm, ví dụ cửa hàng mở cửa lúc 09:00 giờ địa phương. Nó không tự xác định được instant nếu thiếu múi giờ.
- **Date hoặc time thuần:** ngày sinh, ngày kế toán hoặc giờ mở cửa, không nhất thiết gắn với một instant.

Đừng chọn kiểu Java hoặc kiểu SQL chỉ vì tên của chúng giống nhau. Hãy chọn theo ý nghĩa nghiệp vụ rồi mới cấu hình driver.

## 2. TIMESTAMP và DATETIME của MySQL khác nhau thế nào?

Hai kiểu này thường gây nhầm lẫn nhất:

| Kiểu MySQL | Cách lưu và đọc | Phù hợp với |
|---|---|---|
| `TIMESTAMP` | MySQL chuyển giá trị từ session time zone sang UTC khi lưu và từ UTC về session time zone khi đọc; cột không lưu tên múi giờ gốc | Instant như thời điểm tạo đơn, thanh toán, nhận sự kiện |
| `DATETIME` | Lưu các thành phần ngày/giờ như được cung cấp; MySQL không tự chuyển đổi theo session time zone | Giờ địa phương, lịch hẹn hoặc thời điểm wall-clock cần giữ nguyên |
| `DATE` | Chỉ lưu ngày | Ngày sinh, ngày hóa đơn, ngày nghỉ |
| `TIME` | Lưu giá trị thời gian/độ dài theo ngữ nghĩa kiểu `TIME`, không phải instant có múi giờ | Giờ trong ngày hoặc khoảng thời lượng theo quy ước ứng dụng |

Ví dụ:

```sql
CREATE TABLE event_log (
  event_id BIGINT PRIMARY KEY,
  occurred_at TIMESTAMP(6) NOT NULL,
  store_local_time DATETIME(6) NOT NULL,
  business_date DATE NOT NULL
);
```

`occurred_at` biểu diễn instant. `store_local_time` giữ các thành phần giờ địa phương tại cửa hàng; nếu cần chuyển nó thành instant, ứng dụng phải biết múi giờ của cửa hàng tại thời điểm đó. `business_date` chỉ là ngày nghiệp vụ.

MySQL `TIMESTAMP` không lưu offset hoặc tên múi giờ ban đầu. Khi đọc, kết quả được biểu diễn theo session time zone hiện tại. Vì vậy, hai session có múi giờ khác nhau có thể nhìn thấy chuỗi giờ khác nhau nhưng cùng chỉ tới một instant. `DATETIME` không tự động thực hiện phép chuyển đổi đó.

`TIMESTAMP` có phạm vi giá trị hẹp hơn `DATETIME` (trong các bản MySQL hiện hành, giới hạn trên truyền thống của `TIMESTAMP` là năm 2038). Cả `TIMESTAMP` và `DATETIME` hỗ trợ fractional seconds tối đa sáu chữ số; cần chọn precision phù hợp với độ chính xác nguồn và cách ứng dụng xử lý nano/micro giây.

## 3. connectionTimeZone điều khiển múi giờ của Connector/J

`connectionTimeZone` là thuộc tính Connector/J để xác định múi giờ driver dùng cho chuyển đổi temporal value. Thuộc tính này được giới thiệu trong Connector/J 8.0.23. Các giá trị thường dùng:

- `LOCAL`: dùng múi giờ mặc định của JVM. Đây là giá trị mặc định.
- `SERVER`: yêu cầu driver xác định múi giờ của MySQL server.
- Một timezone ID hợp lệ, ví dụ `UTC`, `Asia/Ho_Chi_Minh` hoặc `America/New_York`.

Ví dụ URL JDBC chỉ định UTC:

```text
jdbc:mysql://db.example.internal:3306/orders?connectionTimeZone=UTC
```

Đặt `connectionTimeZone=UTC` làm cho driver sử dụng UTC trong logic chuyển đổi. Tuy nhiên, riêng thuộc tính này **không tự thay đổi** `@@session.time_zone` của MySQL. Session có thể tiếp tục dùng `SYSTEM`, `+07:00` hoặc một giá trị khác theo cấu hình server hay lệnh session trước đó.

Giá trị `SERVER` hữu ích khi muốn driver dựa vào múi giờ server thay vì JVM. Tuy nhiên, môi trường có nhiều máy chủ, replica hoặc container với cấu hình hệ điều hành khác nhau cần kiểm tra kỹ. Múi giờ hệ thống dạng viết tắt hoặc cấu hình DST không nhất quán có thể gây khó hiểu. Với ứng dụng cần quy ước ổn định, một timezone ID rõ ràng như `UTC` thường dễ vận hành hơn.

> `serverTimezone` là tên thuộc tính cũ được giữ làm alias tương thích cho `connectionTimeZone` trong các phiên bản Connector/J tương ứng. Với cấu hình mới, dùng `connectionTimeZone` và tránh khai báo cả hai với giá trị khác nhau.

## 4. forceConnectionTimeZoneToSession đồng bộ session MySQL

`forceConnectionTimeZoneToSession` điều khiển việc Connector/J có đặt múi giờ session MySQL theo `connectionTimeZone` hay không. Mặc định là `false`.

Khi đặt `true`, driver yêu cầu session sử dụng múi giờ đã cấu hình. Ví dụ:

```text
jdbc:mysql://db.example.internal:3306/orders?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true
```

Sau khi kết nối, kiểm tra từ chính connection đó:

```sql
SELECT
  @@session.time_zone,
  @@global.time_zone,
  @@system_time_zone,
  NOW(),
  UTC_TIMESTAMP();
```

Nếu session dùng UTC, `NOW()` và `UTC_TIMESTAMP()` thường hiển thị cùng thời điểm với cùng giá trị giờ; nếu session dùng múi giờ khác, `NOW()` trả giờ theo session còn `UTC_TIMESTAMP()` trả giờ UTC.

Đặt session time zone ảnh hưởng nhiều hơn việc chuyển `Timestamp`: nó cũng ảnh hưởng `NOW()`, `CURRENT_TIMESTAMP`, cách MySQL diễn giải literal khi ghi vào `TIMESTAMP`, và một số hàm ngày/giờ phụ thuộc session. Vì thế, bật `forceConnectionTimeZoneToSession` là một quyết định về quy ước thời gian của toàn bộ session. Không bật một cách tùy tiện nếu ứng dụng hoặc các câu SQL hiện có đang phụ thuộc vào giờ địa phương của server.

Nếu `forceConnectionTimeZoneToSession=true` và driver đặt tên múi giờ như `Asia/Ho_Chi_Minh` vào session, MySQL cần timezone tables được nạp và cập nhật. Nếu server báo `Unknown or incorrect time zone`, kiểm tra timezone tables. Dùng offset cố định như `+00:00` không cần tra cứu quy tắc DST, nhưng offset cố định không thể biểu diễn quy tắc thay đổi theo mùa của một vùng địa lý.

## 5. preserveInstants và ý nghĩa của instant

`preserveInstants` được giới thiệu trong Connector/J 8.0.23 và mặc định là `true` trong các phiên bản có thuộc tính này. Nó điều khiển cách driver cố gắng giữ nguyên instant khi chuyển đổi các kiểu Java đại diện cho thời điểm tuyệt đối sang/ra kiểu thời gian MySQL.

Khi `preserveInstants=true`, Connector/J dùng `connectionTimeZone` trong quá trình chuyển đổi instant-based value. Mục tiêu là cùng một instant được giữ nguyên dù JVM hoặc MySQL session đang dùng múi giờ khác. Thuộc tính này đặc biệt quan trọng với `java.sql.Timestamp` và các API JDBC biểu diễn thời điểm.

Khi `preserveInstants=false`, driver không áp dụng cơ chế bảo toàn instant theo `connectionTimeZone` và dùng hành vi chuyển đổi tương thích legacy, vốn có thể phụ thuộc vào múi giờ mặc định của JVM. Kết quả có thể khác nếu JVM, connection time zone và session time zone không trùng nhau. Không đổi sang `false` chỉ để làm một màn hình hiển thị khớp trong môi trường phát triển; hãy xác định cột đang lưu instant hay local date-time trước.

Ví dụ JDBC:

```java
Instant instant = Instant.parse("2026-11-19T08:30:00Z");
Timestamp timestamp = Timestamp.from(instant);

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO event_log (event_id, occurred_at) VALUES (?, ?)")) {
    ps.setLong(1, 1001L);
    ps.setTimestamp(2, timestamp);
    ps.executeUpdate();
}
```

`Instant` biểu diễn thời điểm tuyệt đối; `Timestamp.from()` chuyển nó thành JDBC `Timestamp`. Với cấu hình UTC nhất quán và `preserveInstants=true`, ứng dụng có thể lưu và đọc lại instant mà không phụ thuộc múi giờ hiển thị của JVM.

`preserveInstants` không làm cho `DATETIME` tự có thông tin múi giờ. Nếu lưu instant vào `DATETIME`, ứng dụng và driver phải thống nhất quy ước chuyển đổi, ví dụ luôn ghi các thành phần UTC và luôn diễn giải chúng là UTC khi đọc. Nếu nghiệp vụ cần lưu giờ địa phương, dùng `LocalDateTime` và giữ nguyên wall-clock value thay vì ép nó thành instant.

## 6. Phân biệt Java time API với java.sql.Timestamp

Các kiểu Java biểu diễn ý nghĩa thời gian khác nhau:

| Kiểu Java | Ý nghĩa | Kiểu SQL thường phù hợp |
|---|---|---|
| `Instant` | Một điểm tuyệt đối trên timeline theo UTC | `TIMESTAMP` hoặc quy ước UTC rõ ràng trong `DATETIME` |
| `java.sql.Timestamp` | Kiểu JDBC mang giá trị thời điểm, có phần nano giây | Thường dùng với `TIMESTAMP`; kiểm tra quy tắc chuyển đổi của Connector/J |
| `LocalDateTime` | Ngày và giờ trên đồng hồ, không có offset/time zone | `DATETIME` |
| `LocalDate` | Ngày thuần | `DATE` |
| `LocalTime` | Giờ thuần, không có ngày/múi giờ | `TIME` |
| `OffsetDateTime` / `ZonedDateTime` | Ngày giờ gắn offset hoặc timezone | MySQL không có kiểu cột lưu đầy đủ zone ID; cần chuẩn hóa hoặc lưu thêm zone riêng |

Connector/J hỗ trợ các kiểu Java 8 date/time theo phiên bản và phương thức JDBC cụ thể. Kiểm tra tài liệu của phiên bản driver đang dùng trước khi gọi `setObject()` hoặc `getObject()` với `OffsetDateTime` hay `ZonedDateTime`; không giả định MySQL `TIMESTAMP` lưu được offset/zone gốc.

Ví dụ lưu giờ địa phương:

```java
LocalDateTime appointment = LocalDateTime.of(2026, 11, 20, 9, 0);

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO appointments (appointment_id, local_start) VALUES (?, ?)")) {
    ps.setLong(1, 501L);
    ps.setObject(2, appointment);
    ps.executeUpdate();
}
```

Cột `local_start` nên là `DATETIME`, vì lịch hẹn được định nghĩa là 09:00 giờ địa phương. Nếu cần xác định instant thực tế, lưu thêm zone ID của địa điểm, ví dụ `Asia/Ho_Chi_Minh`, hoặc lưu instant đã được tính từ local date-time và zone theo quy tắc nghiệp vụ.

Không chuyển `LocalDateTime` thành `Timestamp` bằng cách ngầm dùng `ZoneId.systemDefault()` nếu giá trị nguồn vốn không có múi giờ. Việc đó tự thêm một giả định có thể sai khi ứng dụng chạy ở container hoặc region khác.

## 7. Cấu hình JDBC URL khuyến nghị

Với hệ thống cần lưu instant và thống nhất mọi session theo UTC, cấu hình có thể là:

```text
jdbc:mysql://db.example.internal:3306/orders?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true&preserveInstants=true
```

Ý nghĩa:

- `connectionTimeZone=UTC`: driver dùng UTC khi chuyển đổi temporal value.
- `forceConnectionTimeZoneToSession=true`: yêu cầu MySQL session dùng UTC.
- `preserveInstants=true`: giữ instant khi chuyển đổi các kiểu Java biểu diễn thời điểm.

Nếu không muốn thay đổi session time zone vì ứng dụng cần `NOW()` theo giờ địa phương của server, có thể đặt `forceConnectionTimeZoneToSession=false` hoặc bỏ thuộc tính này. Khi đó, phải hiểu session time zone hiện tại và kiểm thử chuyển đổi giữa connection time zone với session time zone.

Với Connector/J dùng `Properties` thay vì URL:

```java
Properties props = new Properties();
props.setProperty("user", "orders_app");
props.setProperty("password", "<read-from-secret-manager>");
props.setProperty("connectionTimeZone", "UTC");
props.setProperty("forceConnectionTimeZoneToSession", "true");
props.setProperty("preserveInstants", "true");

Connection connection = DriverManager.getConnection(jdbcUrl, props);
```

Mật khẩu trong ví dụ là placeholder; ứng dụng cần lấy secret từ kho quản lý bí mật. Cấu hình TLS như CA, xác minh hostname và chế độ SSL cũng cần được thiết lập riêng theo chính sách kết nối. Múi giờ UTC không thay thế mã hóa TLS.

## 8. Kiểm tra trạng thái múi giờ từ JDBC và MySQL

Khi điều tra lệch giờ, thu thập cả phía JVM lẫn MySQL trên cùng một kết nối.

Trong Java:

```java
System.out.println("JVM zone: " + ZoneId.systemDefault());
System.out.println("Instant now: " + Instant.now());
System.out.println("Local date-time: " + LocalDateTime.now());
```

Trong MySQL:

```sql
SELECT
  @@global.time_zone AS global_time_zone,
  @@session.time_zone AS session_time_zone,
  @@system_time_zone AS system_time_zone,
  NOW(6) AS session_now,
  UTC_TIMESTAMP(6) AS utc_now,
  TIMESTAMPDIFF(SECOND, UTC_TIMESTAMP(), NOW()) AS session_offset_seconds;
```

Chạy truy vấn trên từng connection lấy từ pool, không chỉ trên một connection quản trị riêng. Nếu một số connection có `@@session.time_zone` khác, có thể có code khởi tạo session hoặc tác vụ trước đó đã thay đổi session state.

Kiểm tra round trip với một instant cố định:

```sql
CREATE TABLE timezone_probe (
  probe_id BIGINT PRIMARY KEY,
  instant_value TIMESTAMP(6) NOT NULL,
  wall_clock_value DATETIME(6) NOT NULL
);
```

Chọn một instant đã biết, ghi vào `instant_value` bằng `Timestamp` và ghi `wall_clock_value` theo quy ước UTC hoặc giờ địa phương đã xác định. Đọc lại từ cùng connection và một connection có session time zone khác. Với `TIMESTAMP`, chuỗi hiển thị có thể khác nhưng instant phải giống nhau. Với `DATETIME`, các thành phần giờ phải giữ nguyên như đã lưu; driver không thể tự biết đó là UTC hay giờ địa phương nếu hợp đồng dữ liệu không nói rõ.

## 9. Daylight Saving Time và timezone database

Các timezone ID như `America/New_York` hoặc `Europe/Berlin` có quy tắc DST. Một giờ địa phương có thể xuất hiện hai lần khi đồng hồ lùi, hoặc không tồn tại khi đồng hồ tiến. Vì vậy, một `LocalDateTime` như 01:30 vào ngày chuyển DST có thể tương ứng với hai instant hoặc không tương ứng với instant nào.

Nếu nghiệp vụ cần lịch hẹn ở một vùng địa lý, lưu cả local date-time và zone ID; khi tính instant, áp dụng chính sách rõ ràng cho thời điểm ambiguous hoặc nonexistent. Không dùng offset hiện tại của vùng để tính cho một ngày trong tương lai nếu quy tắc DST có thể thay đổi.

JVM sử dụng timezone database đi kèm JDK/OS; MySQL dùng timezone tables của server khi xử lý tên múi giờ. Hai bộ dữ liệu có thể khác phiên bản. Điều này có thể khiến Java và MySQL tính offset khác nhau ở một số ngày lịch sử hoặc tương lai.

Khuyến nghị:

- Dùng UTC cho timestamp sự kiện và trao đổi dữ liệu giữa dịch vụ.
- Dùng IANA zone ID cho lịch địa phương, không chỉ lưu một offset cố định.
- Cập nhật JDK timezone data và MySQL timezone tables theo quy trình vận hành.
- Kiểm tra các thời điểm chuyển DST trong bộ kiểm thử, nhất là lịch đặt chỗ và thanh toán định kỳ.
- Tránh dùng các chữ viết tắt múi giờ mơ hồ như `CST`; dùng `Asia/Shanghai`, `America/Chicago` hoặc zone ID chính xác theo nghiệp vụ.

## 10. Connection pool và session time zone

`time_zone` là biến session. Khi một connection được trả về pool, session state có thể vẫn tồn tại cho lần mượn tiếp theo nếu pool không reset hoặc ứng dụng không khởi tạo lại.

Ví dụ rủi ro:

1. Request A chạy `SET time_zone = '+07:00'` trên connection lấy từ pool.
2. Connection được trả về pool mà không reset session.
3. Request B mượn đúng connection đó và giả định session đang dùng UTC.
4. Các phép tính `NOW()` hoặc ghi `TIMESTAMP` của request B có thể khác kỳ vọng.

Để tránh lỗi:

- Đặt `connectionTimeZone` và `forceConnectionTimeZoneToSession` nhất quán trong cấu hình datasource.
- Không thay `time_zone` tùy tiện trong request; nếu bắt buộc, khôi phục giá trị ban đầu trước khi trả connection.
- Dùng connection initialization SQL hoặc hook của pool để xác minh/đặt session state khi tạo connection mới.
- Bật cơ chế reset connection state của pool nếu được hỗ trợ và kiểm thử hành vi với Connector/J.
- Thêm health check định kỳ đọc `@@session.time_zone` từ các connection thực tế trong pool.

Đặt `SET GLOBAL time_zone` chỉ thay đổi mặc định cho session mới; nó không tự cập nhật mọi session đang mở. Tương tự, đổi JDBC URL không tự sửa những connection đã được pool tạo trước đó; cần recycle pool theo quy trình triển khai.

## 11. Calendar overload và API JDBC cũ

JDBC cung cấp overload cho phép truyền `Calendar` khi đọc hoặc ghi `Timestamp`/`Date`/`Time`. Calendar xác định múi giờ dùng cho thao tác cụ thể:

```java
Calendar utcCalendar = Calendar.getInstance(TimeZone.getTimeZone("UTC"));

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO event_log (event_id, occurred_at) VALUES (?, ?)")) {
    ps.setLong(1, 1002L);
    ps.setTimestamp(2, timestamp, utcCalendar);
    ps.executeUpdate();
}
```

Khi đọc:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT occurred_at FROM event_log WHERE event_id = ?")) {
    ps.setLong(1, 1002L);
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            Timestamp value = rs.getTimestamp(1, utcCalendar);
            Instant instant = value.toInstant();
        }
    }
}
```

Calendar overload hữu ích khi tích hợp code legacy hoặc cần quy định múi giờ cho một thao tác riêng. Tuy nhiên, trộn Calendar UTC với một connection có cấu hình múi giờ khác mà không có quy ước thống nhất dễ tạo hai lớp chuyển đổi. Với ứng dụng mới, ưu tiên cấu hình Connector/J nhất quán và dùng Java time API theo đúng ngữ nghĩa dữ liệu.

## 12. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
|---|---|---|
| Thời gian lệch đúng số giờ của múi giờ | JVM, connection time zone và session time zone khác nhau | In `ZoneId.systemDefault()`, truy vấn `@@session.time_zone`; đặt cấu hình rõ ràng |
| Ghi đúng nhưng đọc lệch giờ | `TIMESTAMP` được chuyển theo session zone khi đọc, driver chuyển đổi theo connection zone | Kiểm tra `preserveInstants`, `connectionTimeZone` và session zone trên cùng connection |
| `DATETIME` thay đổi sau khi đọc qua driver | Code dùng kiểu instant-based hoặc quy ước chuyển đổi không nhất quán | Dùng `LocalDateTime` cho wall-clock và thống nhất quy tắc UTC nếu lưu instant trong DATETIME |
| Chỉ một số connection trong pool lệch | Session state không được reset hoặc connection initialization khác nhau | Kiểm tra `@@session.time_zone` trên nhiều connection; reset/recycle pool |
| `Unknown or incorrect time zone` | MySQL thiếu timezone tables hoặc zone ID không hợp lệ | Nạp/cập nhật timezone tables hoặc dùng zone ID hợp lệ; thử fixed offset nếu phù hợp |
| Sai giờ quanh ngày chuyển DST | Local time ambiguous/nonexistent hoặc tzdb Java/MySQL khác nhau | Lưu zone ID, xác định chính sách DST và đồng bộ timezone database |
| Lỗi khi kết nối mới sau nâng cấp driver | Thuộc tính timezone đổi tên/phiên bản hoặc driver cũ không hỗ trợ property | Kiểm tra Connector/J version; dùng property được hỗ trợ, không dựa vào cấu hình legacy |
| Mất phần microsecond | Precision cột hoặc mapping không khớp | Chọn `TIMESTAMP(6)`/`DATETIME(6)` khi cần và kiểm thử round trip |

Khi xử lý, không cộng/trừ một số giờ cố định trong SQL hoặc Java để che lệch giờ. Cách đó có thể đúng ở một mùa nhưng sai khi DST thay đổi hoặc khi connection được chuyển sang vùng khác.

## 13. Kế hoạch kiểm thử trước production

Kiểm thử cần bao phủ cả cấu hình lẫn dữ liệu:

1. Ghi nhận Connector/J version, JDK version, JVM default zone, MySQL version và timezone tables.
2. Chạy với `connectionTimeZone=UTC`, `forceConnectionTimeZoneToSession=true`, `preserveInstants=true` trên staging.
3. Mở connection mới và xác minh `@@session.time_zone` thực sự là UTC.
4. Round trip một `Instant` cố định qua `TIMESTAMP(6)` và xác nhận `toInstant()` bằng giá trị ban đầu.
5. Round trip một `LocalDateTime` qua `DATETIME(6)` và xác nhận các thành phần giờ không đổi.
6. Kiểm tra `NOW()`, `UTC_TIMESTAMP()`, `CURRENT_TIMESTAMP` và default timestamp của bảng.
7. Lặp lại với JVM chạy ở timezone khác để phát hiện phụ thuộc ngầm vào `ZoneId.systemDefault()`.
8. Kiểm tra DST với một ngày giờ trước/sau thời điểm chuyển đổi tại vùng nghiệp vụ.
9. Mượn nhiều connection từ pool và xác nhận `@@session.time_zone` không thay đổi giữa các request.
10. Kiểm tra microsecond, giá trị null, giá trị biên và dữ liệu cũ đã lưu theo quy ước trước đây.

Không đổi cấu hình timezone của production trước khi biết dữ liệu lịch sử đang lưu theo instant hay local time. Nếu dữ liệu cũ đã bị ghi theo một quy ước không nhất quán, cần lập kế hoạch phân loại và chuyển đổi dữ liệu riêng; thay JDBC URL không tự sửa các giá trị đã lưu sai.

## 14. Tình huống thực hành

Một ứng dụng đặt hàng Java chạy trong container UTC+7, MySQL server chạy UTC và có nhiều replica. Ứng dụng ghi thời điểm thanh toán vào `TIMESTAMP`, đồng thời lưu giờ hẹn giao hàng theo giờ địa phương của cửa hàng vào `DATETIME`. Một số request đọc lại dữ liệu từ connection pool và thấy giờ thanh toán lệch bảy tiếng.

**Bước 1 — Xác định ngữ nghĩa.** `paid_at` là instant nên dùng `TIMESTAMP(6)`; `delivery_local_time` là giờ địa phương nên dùng `DATETIME(6)` và lưu thêm zone ID của cửa hàng nếu cần tính instant.

**Bước 2 — Đồng bộ instant.** Cấu hình datasource:

```text
jdbc:mysql://db.example.internal:3306/orders?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true&preserveInstants=true
```

**Bước 3 — Xác minh session.** Mượn connection từ pool, chạy `SELECT @@session.time_zone, NOW(6), UTC_TIMESTAMP(6)` và xác nhận session dùng UTC. Kiểm tra nhiều connection, không chỉ một connection kiểm thử.

**Bước 4 — Sửa mapping Java.** Dùng `Instant` hoặc `Timestamp.from(instant)` cho `paid_at`. Dùng `LocalDateTime` cho `delivery_local_time`; không chuyển local time thành instant nếu chưa áp dụng zone ID của cửa hàng.

**Bước 5 — Kiểm thử round trip.** Ghi instant đã biết vào `paid_at`, đọc lại bằng `getTimestamp(...).toInstant()` và so sánh. Ghi `LocalDateTime` vào `delivery_local_time`, đọc lại bằng `getObject(..., LocalDateTime.class)` nếu phiên bản driver hỗ trợ và so sánh các thành phần.

**Bước 6 — Triển khai pool.** Recycle connection pool sau khi thay URL, bảo đảm connection cũ không còn được tái sử dụng và không có request nào tự đặt lại session timezone.

Với dữ liệu lịch sử, kiểm tra nguồn gốc từng trường. Nếu `paid_at` trước đây được ghi khi session dùng UTC+7 nhưng ứng dụng hiểu là UTC, có thể cần chuyển dữ liệu theo phạm vi và thời điểm bị ảnh hưởng; không áp dụng `DATE_SUB` hàng loạt khi chưa đối soát.

## 15. Checklist trước khi đưa vào production

- [ ] Đã xác định trường nào là instant, local date-time, date thuần hoặc time thuần.
- [ ] Đã chọn kiểu SQL phù hợp giữa `TIMESTAMP`, `DATETIME`, `DATE` và `TIME`.
- [ ] Đã ghi nhận Connector/J version, JDK timezone và MySQL timezone configuration.
- [ ] Đã đặt `connectionTimeZone` rõ ràng thay vì phụ thuộc ngầm vào JVM mặc định.
- [ ] Đã quyết định có cần `forceConnectionTimeZoneToSession=true` hay không.
- [ ] Đã hiểu và kiểm thử `preserveInstants` với kiểu Java/JDBC thực tế.
- [ ] Đã xác minh `@@session.time_zone` trên các connection lấy từ pool.
- [ ] Đã kiểm tra timezone tables nếu sử dụng IANA zone ID ở MySQL.
- [ ] Đã kiểm thử DST, local time ambiguous/nonexistent và sự khác nhau của timezone database.
- [ ] Đã kiểm thử round trip với `TIMESTAMP(6)` và `DATETIME(6)`.
- [ ] Đã kiểm tra Calendar overload hoặc API legacy không tạo thêm lớp chuyển đổi ngoài dự kiến.
- [ ] Đã đánh giá dữ liệu lịch sử trước khi đổi cấu hình và có kế hoạch chuyển đổi riêng nếu cần.

Đồng bộ múi giờ JDBC không chỉ là đặt server về UTC. `connectionTimeZone` xác định múi giờ driver dùng khi chuyển đổi, `forceConnectionTimeZoneToSession` đồng bộ session MySQL, còn `preserveInstants` giúp giữ nguyên thời điểm tuyệt đối qua quá trình chuyển đổi. Kết hợp đúng ba thuộc tính với lựa chọn `TIMESTAMP`/`DATETIME` theo ngữ nghĩa nghiệp vụ, kiểm tra session của connection pool và thử nghiệm DST sẽ giúp ứng dụng Java lưu và đọc thời gian nhất quán giữa JVM và MySQL.

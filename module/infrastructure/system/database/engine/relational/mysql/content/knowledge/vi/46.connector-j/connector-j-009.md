# Ánh xạ DATE/TIME/DATETIME/TIMESTAMP và các kiểu java.time

Khi ứng dụng Java đọc hoặc ghi cột thời gian trong MySQL, cần phân biệt ngày lịch, giờ trong ngày, thời điểm trên dòng thời gian và thời gian địa phương. Bốn kiểu SQL DATE, TIME, DATETIME và TIMESTAMP có ý nghĩa khác nhau; các lớp java.time như LocalDate, LocalTime, LocalDateTime và Instant cũng biểu diễn những khái niệm khác nhau. Nếu chọn sai kiểu hoặc để múi giờ của JVM, JDBC session và MySQL không thống nhất, ứng dụng có thể lưu đúng một giá trị nhưng đọc ra một thời điểm khác.

MySQL Connector/J hỗ trợ ánh xạ JDBC 4.2 với các kiểu java.time. Việc ánh xạ phải dựa trên ý nghĩa nghiệp vụ của cột, phiên bản Connector/J thực tế và chính sách timezone của kết nối. Bài học này tập trung vào cách chọn kiểu, đọc/ghi qua JDBC, cấu hình múi giờ, giữ độ chính xác microsecond và kiểm thử các trường hợp biên.

## 1. Phân biệt ý nghĩa của bốn kiểu thời gian MySQL

| Kiểu MySQL | Ý nghĩa dữ liệu | Có chuyển đổi theo timezone khi lưu/đọc? | Kiểu java.time thường dùng |
|---|---|---|---|
| DATE | Một ngày lịch, không có giờ | Không | LocalDate |
| TIME | Giờ trong ngày hoặc một khoảng thời lượng có dấu | Không | LocalTime nếu dữ liệu thật sự là giờ trong ngày |
| DATETIME | Ngày và giờ địa phương, không gắn múi giờ | Không | LocalDateTime |
| TIMESTAMP | Một thời điểm được chuyển đổi theo timezone của session | Có; MySQL chuyển giữa session timezone và UTC khi lưu/đọc | LocalDateTime qua JDBC; dùng chính sách chuyển đổi rõ ràng nếu ứng dụng làm việc với Instant |

Không nên chọn cột chỉ theo tên lớp Java. Hãy hỏi dữ liệu biểu diễn điều gì:

- Ngày sinh hoặc ngày hóa đơn: ngày lịch, thường là DATE và LocalDate.
- Giờ cửa hàng mở cửa: giờ trong ngày, thường là TIME và LocalTime.
- Lịch hẹn lúc 09:30 tại một địa điểm: thời gian địa phương, thường là DATETIME và LocalDateTime; nếu cần xử lý múi giờ và DST, lưu thêm zone ID.
- Thời điểm một giao dịch được ghi nhận trên toàn hệ thống: một instant, thường dùng TIMESTAMP với quy ước lưu/đọc UTC được kiểm soát.
- Thời lượng xử lý 27 giờ: một khoảng thời gian, không phải giờ trên đồng hồ; nên cân nhắc lưu số giây hoặc microsecond bằng BIGINT thay vì ép vào LocalTime.

## 2. DATE và LocalDate

MySQL DATE lưu năm, tháng, ngày, không có giờ hoặc timezone. Kiểu Java tương ứng tự nhiên là java.time.LocalDate.

Ví dụ schema:

~~~sql
CREATE TABLE employee (
  employee_id BIGINT PRIMARY KEY,
  birth_date DATE,
  hire_date DATE NOT NULL
);
~~~

Đọc bằng Connector/J:

~~~java
LocalDate birthDate =
    resultSet.getObject("birth_date", LocalDate.class);

LocalDate hireDate =
    resultSet.getObject("hire_date", LocalDate.class);
~~~

Ghi bằng PreparedStatement:

~~~java
String sql = """
    INSERT INTO employee (employee_id, birth_date, hire_date)
    VALUES (?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, employeeId);
    ps.setObject(2, birthDate);
    ps.setObject(3, LocalDate.now());
    ps.executeUpdate();
}
~~~

LocalDate không có giờ và không có timezone, nên không cần chuyển qua Instant để lưu một ngày lịch. Tránh chuyển DATE thành java.util.Date hoặc Instant nếu nghiệp vụ chỉ cần ngày: phép chuyển có thể thêm một timezone và làm ngày bị lùi hoặc tiến một ngày khi hiển thị ở vùng khác.

Khi ngày có thể chưa biết, dùng SQL NULL và kiểm tra null trong Java. Với getObject trả về kiểu tham chiếu, giá trị SQL NULL thường được biểu diễn bằng Java null.

## 3. TIME và LocalTime: giờ trong ngày khác thời lượng

MySQL TIME có thể lưu giá trị âm và thời lượng vượt quá 24 giờ; phạm vi của kiểu này lớn hơn một giờ trên đồng hồ. Do đó, TIME không phải lúc nào cũng tương đương LocalTime.

### 3.1. Khi TIME biểu diễn giờ trong ngày

Nếu cột chỉ chứa giờ từ 00:00 đến trước 24:00, không âm, có thể ánh xạ sang LocalTime:

~~~sql
CREATE TABLE store_hours (
  store_id BIGINT NOT NULL,
  opens_at TIME(6) NOT NULL,
  closes_at TIME(6) NOT NULL,
  PRIMARY KEY (store_id)
);
~~~

~~~java
LocalTime opensAt =
    resultSet.getObject("opens_at", LocalTime.class);

LocalTime closesAt =
    resultSet.getObject("closes_at", LocalTime.class);

ps.setObject(1, LocalTime.of(8, 30));
ps.setObject(2, LocalTime.of(21, 0));
~~~

LocalTime phù hợp với giờ trên đồng hồ, ví dụ 08:30 hoặc 21:00. Nó không thể biểu diễn -01:30 hoặc 27:15. Nếu dữ liệu hiện có có các giá trị như vậy, không đọc thẳng thành LocalTime và giả định kết quả vẫn giữ nguyên.

### 3.2. Khi TIME biểu diễn thời lượng

Nếu TIME được dùng để biểu diễn thời lượng, ví dụ thời gian xử lý, thời gian chờ hoặc độ lệch, hãy xác định rõ phạm vi và cách chuyển đổi. MySQL TIME có giới hạn khoảng 838 giờ 59 phút 59 giây, trong khi một số nghiệp vụ có thể cần thời lượng dài hơn.

Với dữ liệu thời lượng có thể vượt 24 giờ, âm hoặc cần tính toán chính xác, một thiết kế thường dễ kiểm soát hơn là lưu số giây hoặc microsecond:

~~~sql
CREATE TABLE job_run (
  job_id BIGINT PRIMARY KEY,
  elapsed_microseconds BIGINT NOT NULL
);
~~~

Trong Java có thể chuyển đổi rõ ràng:

~~~java
Duration elapsed =
    Duration.ofNanos(elapsedMicroseconds * 1_000L);

long storedMicros = elapsed.toNanos() / 1_000L;
ps.setLong(1, storedMicros);
~~~

Ví dụ trên giả định giá trị microsecond nằm trong phạm vi không gây tràn khi nhân. Với thời lượng rất lớn, dùng phép tính có kiểm tra tràn hoặc giữ giá trị microsecond trong kiểu số nguyên phù hợp. Nếu bắt buộc lưu duration trong cột TIME, hãy xác minh cách Connector/J của đúng phiên bản chuyển đổi kiểu đó; có thể đọc chuỗi TIME và tự phân tích theo quy ước đã định nghĩa. Không giả định driver có thể ánh xạ mọi giá trị TIME sang LocalTime hoặc Duration mà không mất thông tin.

## 4. DATETIME và LocalDateTime

MySQL DATETIME lưu trực tiếp các trường năm, tháng, ngày, giờ, phút, giây và phần microsecond nếu có. Nó không lưu timezone và MySQL không tự chuyển đổi DATETIME theo time_zone của session.

Kiểu Java tương ứng là LocalDateTime:

~~~sql
CREATE TABLE appointment (
  appointment_id BIGINT PRIMARY KEY,
  scheduled_at DATETIME(6) NOT NULL,
  location_zone_id VARCHAR(64) NOT NULL
);
~~~

~~~java
LocalDateTime scheduledAt =
    resultSet.getObject("scheduled_at", LocalDateTime.class);

ps.setObject(1, LocalDateTime.of(2026, 11, 20, 9, 30, 0, 123_000_000));
~~~

LocalDateTime biểu diễn ngày và giờ trên đồng hồ nhưng không xác định được đó là thời điểm nào trên dòng thời gian nếu thiếu timezone. Ví dụ, 2026-11-20 09:30 tại Thành phố Hồ Chí Minh và 2026-11-20 09:30 tại Tokyo là hai thời điểm khác nhau.

Với lịch hẹn gắn với địa điểm, lưu DATETIME cùng zone ID, ví dụ Asia/Ho_Chi_Minh. Khi cần tính instant, ứng dụng kết hợp LocalDateTime với ZoneId để tạo ZonedDateTime hoặc Instant. Cách này cũng giúp xử lý quy tắc giờ mùa hè (DST) tại địa điểm có áp dụng.

## 5. TIMESTAMP và chính sách timezone

MySQL TIMESTAMP biểu diễn một thời điểm. Khi ghi, MySQL chuyển giá trị từ timezone của session sang UTC để lưu; khi đọc, MySQL chuyển từ UTC sang timezone của session. Bản thân cột không lưu tên múi giờ hoặc offset gốc.

Trong JDBC 4.2, kiểu thường dùng để đọc TIMESTAMP qua getObject là LocalDateTime. Điều này có nghĩa giá trị trả về là các trường ngày/giờ được trình bày trong timezone mà kết nối đang sử dụng; nó không tự mang theo zone ID.

~~~sql
CREATE TABLE audit_event (
  event_id BIGINT PRIMARY KEY,
  occurred_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
);
~~~

~~~java
LocalDateTime occurredAt =
    resultSet.getObject("occurred_at", LocalDateTime.class);
~~~

Nếu nghiệp vụ Java làm việc với Instant, hãy định nghĩa một quy ước rõ ràng, chẳng hạn mọi session MySQL dùng UTC. Khi đó chuyển đổi Instant sang LocalDateTime theo UTC trước khi ghi và diễn giải LocalDateTime đọc được theo UTC:

~~~java
Instant eventInstant = Instant.now();
LocalDateTime utcValue =
    LocalDateTime.ofInstant(eventInstant, ZoneOffset.UTC);

ps.setObject(1, utcValue);

LocalDateTime storedUtc =
    resultSet.getObject("occurred_at", LocalDateTime.class);
Instant readInstant =
    storedUtc.toInstant(ZoneOffset.UTC);
~~~

Ví dụ chỉ đúng khi kết nối thực sự dùng timezone UTC và cấu hình Connector/J không áp dụng một quy tắc chuyển đổi khác với quy ước đó. Phải kiểm tra session timezone sau khi lấy connection từ pool và kiểm thử với phiên bản driver thực tế.

Không dùng LocalDateTime.now() theo timezone mặc định của JVM để ghi vào TIMESTAMP rồi giả định MySQL biết múi giờ đó. LocalDateTime không chứa offset; nếu ứng dụng cần biểu diễn một instant, hãy chuyển đổi từ Instant với zone đã chọn một cách tường minh.

## 6. JDBC 4.2 và các API java.time trong Connector/J

Connector/J hiện đại hỗ trợ đọc/ghi các kiểu java.time qua ResultSet.getObject và PreparedStatement.setObject. Những ánh xạ thông dụng:

| Kiểu SQL | Đọc bằng | Ghi bằng |
|---|---|---|
| DATE | getObject(column, LocalDate.class) | setObject(index, LocalDate) |
| TIME (giờ trong ngày) | getObject(column, LocalTime.class) | setObject(index, LocalTime) |
| DATETIME | getObject(column, LocalDateTime.class) | setObject(index, LocalDateTime) |
| TIMESTAMP | getObject(column, LocalDateTime.class) theo timezone session | setObject(index, LocalDateTime) theo chính sách timezone đã thống nhất |

Ví dụ một câu truy vấn hoàn chỉnh:

~~~java
String sql = """
    SELECT birth_date, opens_at, scheduled_at, occurred_at
    FROM event_sample
    WHERE event_id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, eventId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            LocalDate birthDate =
                rs.getObject("birth_date", LocalDate.class);
            LocalTime opensAt =
                rs.getObject("opens_at", LocalTime.class);
            LocalDateTime scheduledAt =
                rs.getObject("scheduled_at", LocalDateTime.class);
            LocalDateTime occurredAt =
                rs.getObject("occurred_at", LocalDateTime.class);
        }
    }
}
~~~

Các lớp java.sql.Date, java.sql.Time và java.sql.Timestamp vẫn thường xuất hiện trong ứng dụng JDBC cũ. Chúng là kiểu legacy và có quy tắc chuyển đổi khác nhau; Timestamp còn có thể tương tác với timezone khi chuyển sang hoặc từ kiểu Java khác. Khi hiện đại hóa, nên chuẩn hóa cách đọc/ghi theo java.time và tránh trộn API cũ với API mới trong cùng một đường dữ liệu nếu chưa kiểm thử.

Nếu cần dùng API legacy, các overload như getTimestamp(column, calendar) hoặc setTimestamp(index, timestamp, calendar) cho phép chỉ định Calendar timezone. Đây là cách kiểm soát rõ hơn so với phụ thuộc timezone mặc định của JVM, nhưng vẫn cần kiểm thử cùng preserveInstants và các thuộc tính Connector/J của phiên bản đang chạy.

## 7. Cấu hình timezone cho Connector/J và MySQL session

Có ba lớp timezone cần phân biệt:

1. JVM default timezone: timezone mặc định của tiến trình Java.
2. Connector/J connection timezone: timezone driver sử dụng trong quá trình chuyển đổi giá trị thời gian.
3. MySQL session time_zone: timezone áp dụng cho các hàm và chuyển đổi TIMESTAMP của phiên kết nối.

Kiểm tra trên một connection thực tế:

~~~sql
SELECT
  @@global.time_zone AS global_time_zone,
  @@session.time_zone AS session_time_zone,
  @@system_time_zone AS system_time_zone,
  NOW(6) AS session_now,
  UTC_TIMESTAMP(6) AS utc_now;
~~~

NOW() và CURRENT_TIMESTAMP trả về thời gian theo session timezone. UTC_TIMESTAMP() trả về UTC. Nếu các giá trị này không phù hợp với quy ước ứng dụng, hãy sửa cấu hình thay vì cộng/trừ giờ trong từng câu SQL.

Connector/J có các connection properties liên quan đến thời gian như:

| Thuộc tính | Vai trò cần hiểu |
|---|---|
| connectionTimeZone | Múi giờ driver dùng khi chuyển đổi các giá trị thời gian |
| forceConnectionTimeZoneToSession | Yêu cầu driver đặt timezone đã chọn cho MySQL session |
| preserveInstants | Điều khiển cách bảo toàn instant khi chuyển đổi các giá trị thời gian |
| treatMysqlDatetimeAsTimestamp | Ảnh hưởng cách driver diễn giải DATETIME trong một số chuyển đổi |

Tên, kiểu giá trị, default và hành vi của thuộc tính có thể thay đổi theo phiên bản Connector/J. Đọc tài liệu của đúng artifact đang dùng trước khi đưa vào cấu hình. Không sao chép URL của một phiên bản driver khác rồi giả định mọi thuộc tính có cùng hành vi.

Nếu toàn hệ thống thống nhất UTC, một cấu hình có thể chỉ định:

~~~properties
spring.datasource.url=jdbc:mysql://mysql.internal.example:3306/appdb?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true
~~~

Đây là ví dụ chính sách, không phải cấu hình bắt buộc cho mọi ứng dụng. Xác nhận thuộc tính được hỗ trợ trong phiên bản Connector/J, kiểm tra @@session.time_zone sau khi tạo connection và bảo đảm pool áp dụng cấu hình cho mọi connection mới.

Với HikariCP, có thể dùng connectionInitSql để đặt session state nếu chính sách triển khai yêu cầu:

~~~yaml
spring:
  datasource:
    hikari:
      connection-init-sql: SET time_zone = '+00:00'
~~~

Không đặt session timezone ở một connection rồi giả định các connection khác trong pool cũng được cập nhật. Mỗi physical connection mới cần được khởi tạo nhất quán. Nếu ứng dụng thay đổi timezone trong một request, phải khôi phục session state trước khi trả connection về pool.

## 8. Độ chính xác fractional seconds

MySQL hỗ trợ phần giây với precision từ 0 đến 6 cho TIME, DATETIME và TIMESTAMP:

| Khai báo | Độ chính xác |
|---|---|
| DATETIME hoặc DATETIME(0) | Giây |
| DATETIME(3) | Millisecond |
| DATETIME(6) | Microsecond |
| TIMESTAMP(6) | Microsecond |
| TIME(6) | Microsecond |

Java LocalTime và LocalDateTime hỗ trợ nanosecond, nhưng MySQL chỉ lưu tối đa microsecond. Nếu ghi giá trị có nanosecond, phần dưới microsecond sẽ không thể được lưu đầy đủ. Hành vi làm tròn hoặc cắt phần dư phụ thuộc kiểu cột, SQL mode và cách chuyển đổi; không tự giả định mọi đường ghi đều giống nhau.

Ví dụ cột microsecond:

~~~sql
CREATE TABLE measurement (
  measurement_id BIGINT PRIMARY KEY,
  measured_at DATETIME(6) NOT NULL
);
~~~

~~~java
LocalDateTime measuredAt =
    LocalDateTime.of(2026, 11, 19, 10, 15, 30, 123_456_000);
ps.setObject(1, measuredAt);
~~~

Khi so sánh thời gian sau khi ghi, hãy chuẩn hóa độ chính xác về microsecond. Nếu hệ thống yêu cầu millisecond, dùng cột (3) và quy định rõ cách làm tròn. Đừng dùng equality trên LocalDateTime nanosecond khi giá trị trong database đã bị giảm precision.

## 9. DST, timezone địa phương và lịch hẹn

DST có thể tạo ra giờ địa phương không tồn tại hoặc xuất hiện hai lần. Ví dụ, khi đồng hồ chuyển sang giờ mùa hè, một khoảng giờ có thể bị bỏ qua; khi chuyển về giờ chuẩn, một khoảng giờ có thể lặp lại.

LocalDateTime không thể tự phân biệt hai lần xuất hiện của cùng một giờ địa phương. Khi nghiệp vụ cần lưu lịch hẹn tại địa điểm có DST, nên lưu:

- Local date-time mà người dùng chọn.
- Zone ID như Europe/Berlin hoặc America/New_York.
- Chính sách xử lý giờ không tồn tại hoặc bị lặp.
- Instant đã được xác định sau khi áp dụng quy tắc timezone, nếu cần lịch sử bất biến.

Ví dụ:

~~~java
LocalDateTime localAppointment =
    LocalDateTime.of(2026, 10, 25, 2, 30);
ZoneId zone = ZoneId.of("Europe/Berlin");

List<ZoneOffset> validOffsets =
    zone.getRules().getValidOffsets(localAppointment);

if (validOffsets.isEmpty()) {
    throw new IllegalArgumentException(
        "Giờ địa phương không tồn tại do chuyển DST");
}

if (validOffsets.size() > 1) {
    // Yêu cầu nghiệp vụ chọn offset sớm hoặc muộn.
}
~~~

Không lưu tên timezone chỉ trong cấu hình máy chủ rồi bỏ qua zone ID của từng sự kiện. Một lịch hẹn có thể cần giữ nguyên giờ địa phương ngay cả khi quy tắc DST của địa điểm thay đổi trong tương lai.

## 10. Các trường hợp dữ liệu đặc biệt

Khi thiết kế schema và kiểm thử, chú ý:

- SQL NULL: khác với giá trị thời gian mặc định; dùng nullable rõ ràng và kiểm tra null trong Java.
- Zero date: các giá trị như 0000-00-00 hoặc ngày không hợp lệ phụ thuộc SQL mode và cấu hình driver. Nên làm sạch dữ liệu và tránh dựa vào hành vi chuyển zero date thành null.
- Giá trị biên: kiểm tra phạm vi DATE, DATETIME, TIMESTAMP và TIME của phiên bản MySQL.
- Fractional seconds: thử precision 0, 3 và 6; xác minh làm tròn/cắt phần dư.
- Leap day: thử ngày 29/02 ở năm nhuận.
- Timezone offset: thử session UTC và session khác UTC để xác nhận TIMESTAMP chuyển đổi đúng quy ước.
- DST: thử giờ bị bỏ qua và giờ xuất hiện hai lần ở vùng có DST.
- Negative/long TIME: không ánh xạ sang LocalTime nếu giá trị không nằm trong miền giờ trong ngày.
- Connection pool: kiểm tra session timezone trên connection mới, connection tái sử dụng và sau reconnect.

zeroDateTimeBehavior là một thuộc tính Connector/J có liên quan đến việc xử lý zero date trong một số phiên bản. Hãy kiểm tra tài liệu driver đang dùng và quyết định chính sách rõ ràng; không dùng tùy chọn này để che dữ liệu ngày tháng không hợp lệ mà chưa điều tra nguồn phát sinh.

## 11. Lỗi ánh xạ thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Thời điểm đọc ra lệch vài giờ | Session timezone, JVM timezone hoặc Connector/J conversion không thống nhất | Kiểm tra @@session.time_zone, thuộc tính driver và quy ước UTC |
| Ngày bị lùi hoặc tiến một ngày | DATE bị chuyển qua instant/timezone không cần thiết | Dùng LocalDate trực tiếp |
| DATETIME thay đổi khi đổi timezone session | Ứng dụng hoặc driver đang diễn giải DATETIME như timestamp | Dùng LocalDateTime và kiểm tra treatMysqlDatetimeAsTimestamp |
| TIME bị lỗi khi đọc thành LocalTime | Giá trị âm hoặc vượt 24 giờ | Xem TIME là duration; đọc/parse theo quy ước hoặc lưu số microsecond |
| Mất phần microsecond | Cột precision thấp hoặc Java/JDBC chuyển qua kiểu chỉ có millisecond | Dùng (6) và API java.time; kiểm tra round-trip |
| Kết quả khác giữa các connection pool member | Session state không được khởi tạo đồng nhất | Thiết lập timezone cho từng physical connection và kiểm tra lại |
| Lỗi zero date | Dữ liệu cũ không hợp lệ hoặc SQL mode/driver xử lý nghiêm hơn | Làm sạch dữ liệu và định nghĩa chính sách zero date |

Khi điều tra, ghi lại cùng lúc giá trị SQL, kiểu Java nhận được, timezone JVM, timezone session, phiên bản Connector/J và các connection properties liên quan. Chỉ nhìn chuỗi thời gian in ra log thường không đủ để xác định lớp nào đã chuyển đổi.

## 12. Bộ kiểm thử round-trip

Một bài kiểm thử ánh xạ nên ghi dữ liệu qua PreparedStatement, đọc lại qua ResultSet và so sánh theo đúng semantics:

1. DATE: so sánh LocalDate trực tiếp.
2. TIME dùng như giờ đồng hồ: so sánh LocalTime trong miền 00:00–23:59:59.999999.
3. TIME dùng như duration: kiểm tra cả giá trị âm và trên 24 giờ theo cách parse đã định nghĩa.
4. DATETIME: so sánh LocalDateTime không gắn timezone.
5. TIMESTAMP: so sánh Instant sau khi quy đổi theo timezone session đã chốt.
6. Precision: chuẩn hóa nanosecond về microsecond trước khi so sánh.
7. NULL và zero date: xác minh chính sách rõ ràng.
8. Pool/reconnect: chạy lại kiểm thử trên nhiều physical connection và sau khi kết nối được tạo mới.

Ví dụ truy vấn kiểm tra session:

~~~sql
SELECT
  @@session.time_zone,
  NOW(6),
  UTC_TIMESTAMP(6),
  CURRENT_TIMESTAMP(6);
~~~

Kết quả cần được lưu cùng test report để phát hiện thay đổi cấu hình giữa các môi trường.

## 13. Câu hỏi tự kiểm tra

1. Vì sao DATE ánh xạ tự nhiên sang LocalDate mà không cần timezone?
2. MySQL TIME có thể lưu giá trị nào mà LocalTime không thể biểu diễn?
3. DATETIME và TIMESTAMP khác nhau thế nào khi session timezone thay đổi?
4. Vì sao MySQL TIMESTAMP không lưu tên timezone hoặc offset gốc?
5. Nếu ứng dụng dùng Instant nhưng JDBC trả LocalDateTime, cần quy ước chuyển đổi nào?
6. Connector/J connectionTimeZone và MySQL session time_zone có vai trò gì khác nhau?
7. Vì sao Java nanosecond không đồng nghĩa MySQL lưu được nanosecond?
8. Khi lưu lịch hẹn ở vùng có DST, vì sao cần lưu ZoneId hoặc chính sách offset?

Ánh xạ thời gian chính xác bắt đầu từ semantics của dữ liệu. Dùng LocalDate cho ngày lịch, LocalTime cho giờ đồng hồ, LocalDateTime cho thời gian địa phương và một quy ước timezone rõ ràng cho instant. Kết hợp lựa chọn kiểu với cấu hình Connector/J, session timezone và kiểm thử round-trip sẽ giúp ứng dụng tránh lỗi lệch giờ, mất precision và diễn giải sai dữ liệu.

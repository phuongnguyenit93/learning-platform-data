# Tích hợp dữ liệu ngày giờ với JDBC trong Java

## 1. Mục tiêu và phạm vi

Ứng dụng thường phải lưu ngày sinh, ngày lập hóa đơn, thời điểm tạo đơn, lịch hẹn theo múi giờ, thời hạn thanh toán hoặc thời điểm một sự kiện xảy ra. Khi đưa dữ liệu thời gian qua JDBC, câu hỏi quan trọng là **giá trị đó biểu diễn ngày lịch, giờ địa phương hay một thời điểm tuyệt đối**. Chọn sai kiểu Java hoặc kiểu SQL có thể làm mất offset, lệch ngày khi qua múi giờ, sai ranh giới truy vấn hoặc mất phần nano giây.

Bài thuộc chủ đề **Thực hành** và tập trung vào việc đưa giá trị ngày giờ giữa domain Java và database bằng JDBC. Java cung cấp API **java.time** từ Java 8 và JDBC 4.2 bổ sung mapping cho nhiều kiểu thời gian hiện đại. Trong code mới, nên dùng các kiểu **LocalDate, LocalTime, LocalDateTime, OffsetTime, OffsetDateTime, Instant và ZoneId**, kết hợp **PreparedStatement.setObject** và **ResultSet.getObject(column, Type.class)** khi JDBC driver hỗ trợ mapping tương ứng. Các API java.time và JDBC 4.2 mapping được trình bày ở đây vẫn được duy trì trên JDK hiện đại.

Bài học dùng **Java 17+**, biên dịch ví dụ bằng **javac --release 17**; các chương trình minh họa độc lập được kiểm tra trên **OpenJDK 24.0.2**. Phần JDBC thực tế cần một database và driver tương thích; mapping cụ thể còn phụ thuộc driver/database, nên phải kiểm thử trên đúng hệ thống triển khai.

Sau bài học, bạn có thể:

1. Phân biệt SQL DATE, TIME, TIMESTAMP, TIME WITH TIME ZONE và TIMESTAMP WITH TIME ZONE.
2. Chọn đúng Java type cho ngày lịch, giờ địa phương, timestamp không zone và thời điểm có offset.
3. Bind tham số ngày giờ bằng PreparedStatement.setObject và đọc bằng ResultSet.getObject có kiểu.
4. Chuyển Instant sang OffsetDateTime UTC khi cần lưu một thời điểm tuyệt đối.
5. Hiểu vì sao LocalDateTime không thể tự xác định một Instant.
6. Lưu ZoneId riêng khi nghiệp vụ cần tái dựng giờ địa phương hoặc lịch định kỳ.
7. Tính khoảng ngày theo ZoneId và truy vấn theo khoảng nửa mở [start, end).
8. Xử lý DST gap/overlap, ranh giới nửa đêm và ngày có 23/25 giờ.
9. Hiểu precision của database timestamp và tránh kỳ vọng nano giây luôn được giữ nguyên.
10. Dùng transaction, PreparedStatement, try-with-resources và connection pool đúng vòng đời.
11. Kiểm thử mapping trên database/driver thực tế, bao gồm timezone session, DST và dữ liệu biên.
12. Tránh phụ thuộc default timezone hoặc cách chuyển đổi ngầm của môi trường.

## 2. Chọn kiểu dữ liệu theo ý nghĩa nghiệp vụ

Trước khi viết SQL, hãy trả lời dữ liệu cần lưu là gì:

- **Ngày trên lịch**: ngày sinh, ngày nghỉ, ngày lập hóa đơn — không cần múi giờ.
- **Giờ trên đồng hồ địa phương**: giờ mở cửa hằng ngày — không cần một thời điểm tuyệt đối.
- **Ngày và giờ địa phương**: giờ hẹn chưa gắn zone — cần bổ sung ZoneId trước khi biến thành Instant.
- **Thời điểm tuyệt đối**: thời điểm tạo giao dịch hoặc nhận sự kiện — cần lưu một điểm duy nhất trên timeline.
- **Lịch dân sự theo vùng**: họp lúc 09:00 mỗi thứ Hai ở Paris — cần giờ địa phương, ZoneId và quy tắc lặp.

### Bảng mapping thường dùng theo JDBC 4.2

| SQL type | Java type phù hợp | Ý nghĩa |
|---|---|---|
| DATE | LocalDate | Ngày lịch, không có giờ |
| TIME | LocalTime | Giờ địa phương, không có ngày/zone |
| TIMESTAMP | LocalDateTime | Ngày + giờ địa phương, không mang offset |
| TIME WITH TIME ZONE | OffsetTime | Giờ + UTC offset |
| TIMESTAMP WITH TIME ZONE | OffsetDateTime | Ngày giờ + UTC offset |
| Thời điểm tuyệt đối trong ứng dụng | Instant | Một điểm duy nhất trên timeline; chuyển sang OffsetDateTime UTC khi cần JDBC mapping portable |

Bảng trên mô tả mapping JDBC 4.2 chuẩn. **Driver và database phải hỗ trợ SQL type tương ứng**; một số hệ thống không triển khai đầy đủ TIME WITH TIME ZONE hoặc có semantics riêng cho TIMESTAMP WITH TIME ZONE. Hãy kiểm tra tài liệu driver, metadata và integration test trên đúng database.

### DATE không phải timestamp lúc nửa đêm

SQL DATE biểu diễn ngày lịch. Không tự chuyển LocalDate thành LocalDateTime ở 00:00 để ghi DATE; làm vậy thêm thông tin không thuộc ý nghĩa cột. Khi đọc DATE, dùng LocalDate. **Ngoại lệ quan trọng theo database:** Oracle Database DATE còn lưu giờ, phút và giây. Nếu cột Oracle DATE đang chứa thành phần thời gian, đọc nó thành LocalDate sẽ làm mất thông tin; phải kiểm tra mapping của Oracle JDBC driver và dùng kiểu giữ đủ phần thời gian, hoặc chuẩn hóa schema theo nghĩa dữ liệu. Không giả định mọi database triển khai DATE giống nhau.

### TIMESTAMP không có nghĩa là Instant

SQL TIMESTAMP (không WITH TIME ZONE) biểu diễn trường ngày giờ như 2025-01-31 09:00:00, không xác định múi giờ. JDBC mapping tương ứng là LocalDateTime. Nếu cột này thực tế đang được ứng dụng quy ước là UTC, đó là **quy ước của hệ thống**, không phải thuộc tính được lưu trong SQL TIMESTAMP; phải ghi rõ và kiểm soát mọi writer/reader.

### TIMESTAMP WITH TIME ZONE cũng không lưu ZoneId đầy đủ

OffsetDateTime mang offset như -05:00 hoặc +07:00. Nó không lưu quy tắc vùng IANA như America/New_York, cũng không ghi lại toàn bộ lịch sử DST. Nhiều database chuẩn hóa giá trị về thời điểm hoặc UTC và không giữ offset ban đầu; hành vi cụ thể phụ thuộc database.

Nếu cần hiển thị hoặc tính lịch tương lai theo vùng gốc, lưu thêm **ZoneId** trong một cột riêng. Không kỳ vọng TIMESTAMP WITH TIME ZONE một mình tái dựng được America/New_York.

## 3. Java time types và cách chuyển đổi an toàn

### LocalDate

Dùng cho ngày không có giờ và zone:

~~~java
LocalDate birthday = LocalDate.of(1995, 7, 20);
~~~

Mapping SQL DATE thường là PreparedStatement.setObject(index, birthday) và ResultSet.getObject(column, LocalDate.class).

### LocalTime

Dùng cho giờ địa phương không gắn ngày:

~~~java
LocalTime opening = LocalTime.of(9, 30);
~~~

Mapping SQL TIME. Một giờ như 01:30 có thể xảy ra hai lần trong ngày DST overlap; nếu cần một thời điểm thực, phải có thêm ngày và ZoneId.

### LocalDateTime

Dùng khi SQL TIMESTAMP chỉ lưu trường ngày giờ, ví dụ giờ đặt lịch chưa xác định zone:

~~~java
LocalDateTime appointment = LocalDateTime.of(2025, 3, 8, 9, 0);
~~~

Không gọi appointment.toInstant() vì LocalDateTime không có toInstant không tham số; phải cung cấp ZoneOffset hoặc ZoneId và xử lý gap/overlap. LocalDateTime không nên được dùng thay Instant cho cột đại diện thời điểm toàn cầu.

### OffsetDateTime và Instant

OffsetDateTime chứa local date-time cùng offset:

~~~java
OffsetDateTime value =
        OffsetDateTime.of(2025, 1, 31, 9, 0, 0, 0, ZoneOffset.UTC);
Instant instant = value.toInstant();
~~~

Nếu nghiệp vụ bắt đầu từ Instant, có thể tạo OffsetDateTime UTC bằng instant.atOffset(ZoneOffset.UTC) để bind vào SQL TIMESTAMP WITH TIME ZONE khi driver hỗ trợ. Khi đọc OffsetDateTime, dùng toInstant() nếu ứng dụng cần thời điểm tuyệt đối.

### ZoneId phải được lưu riêng khi cần

ZoneId.of("Asia/Ho_Chi_Minh") là định danh quy tắc vùng. Không ép ZoneId thành ZoneOffset cố định nếu cần áp dụng quy tắc địa phương qua thời gian. Nếu lịch hẹn được xác định bởi giờ địa phương, lưu các thành phần cần thiết như LocalDateTime + ZoneId, đồng thời lưu Instant/offset đã xác nhận nếu cần audit hoặc tái dựng chính xác lần xảy ra.
## 4. JDBC 4.2: bind và đọc kiểu java.time

JDBC 4.2 bổ sung mapping chuẩn cho nhiều kiểu java.time. Khi driver hỗ trợ, có thể truyền trực tiếp đối tượng ngày giờ vào PreparedStatement và yêu cầu ResultSet trả đúng Java type.

~~~java
// ps là PreparedStatement; rs là ResultSet.
ps.setObject(1, LocalDate.of(2025, 1, 31));
ps.setObject(2, LocalTime.of(9, 30));
ps.setObject(3, LocalDateTime.of(2025, 1, 31, 9, 30));
ps.setObject(4, OffsetDateTime.now(ZoneOffset.UTC));

LocalDate date = rs.getObject("event_date", LocalDate.class);
LocalTime time = rs.getObject("event_time", LocalTime.class);
LocalDateTime local = rs.getObject("local_stamp", LocalDateTime.class);
OffsetDateTime occurred = rs.getObject(
        "occurred_at", OffsetDateTime.class);
~~~

### Vì sao dùng getObject(column, Type.class)?

Nó yêu cầu JDBC driver trả dữ liệu dưới Java type mong muốn, tránh chuyển qua chuỗi rồi parse thủ công. Nếu driver không hỗ trợ conversion đó, lời gọi có thể ném SQLException hoặc SQLFeatureNotSupportedException. Hãy kiểm tra driver thực tế và dùng phiên bản hỗ trợ JDBC 4.2 trở lên.

### Không bind ngày giờ bằng chuỗi định dạng tùy ý

Không truyền chuỗi như 31/01/2025 09:30 vào cột timestamp. Chuỗi đó phụ thuộc format, locale và quy tắc parse của database/session. Hãy bind typed value bằng setObject; chỉ dùng chuỗi nếu schema/protocol thật sự định nghĩa cột là text và có format machine-readable cụ thể.

### Mapping không tự động làm mọi driver giống nhau

JDBC 4.2 chuẩn hóa API và type mapping, nhưng database có thể không có SQL type tương ứng hoặc driver có giới hạn. Ví dụ TIME WITH TIME ZONE không được mọi database hỗ trợ theo cùng cách. Đọc tài liệu driver, kiểm tra metadata và viết integration test trên đúng database/driver đang chạy.

## 5. Ví dụ tích hợp: ghi và đọc dữ liệu ngày giờ

Một schema minh họa có thể chứa:

~~~sql
CREATE TABLE appointment_record (
    appointment_id BIGINT PRIMARY KEY,
    event_date DATE NOT NULL,
    local_start TIME NOT NULL,
    local_appointment TIMESTAMP NOT NULL,
    occurred_at TIMESTAMP WITH TIME ZONE,
    zone_id VARCHAR(64) NOT NULL
);
~~~

DDL có thể cần điều chỉnh theo database. Ý nghĩa từng cột:

- event_date lưu ngày lịch, mapping LocalDate.
- local_start lưu giờ địa phương, mapping LocalTime.
- local_appointment lưu trường ngày giờ địa phương không zone, mapping LocalDateTime.
- occurred_at lưu thời điểm đã xác định với offset, mapping OffsetDateTime.
- zone_id lưu IANA ZoneId riêng, ví dụ Asia/Ho_Chi_Minh hoặc America/New_York.

~~~java
import java.sql.*;
import java.time.*;

public final class AppointmentRepository {
    public void insert(Connection connection, long id,
                       LocalDate eventDate, LocalTime localStart,
                       LocalDateTime localAppointment,
                       Instant occurredAt, ZoneId zoneId)
            throws SQLException {
        String sql = "INSERT INTO appointment_record "
                + "(appointment_id, event_date, local_start, "
                + "local_appointment, occurred_at, zone_id) "
                + "VALUES (?, ?, ?, ?, ?, ?)";

        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, id);
            ps.setObject(2, eventDate);
            ps.setObject(3, localStart);
            ps.setObject(4, localAppointment);
            ps.setObject(5, occurredAt.atOffset(ZoneOffset.UTC));
            ps.setString(6, zoneId.getId());
            ps.executeUpdate();
        }
    }
}
~~~

Đây là class repository để biên dịch; khi chạy cần Connection được tạo từ driver/database tương thích. Cột occurred_at được bind bằng OffsetDateTime UTC. Nếu database không hỗ trợ TIMESTAMP WITH TIME ZONE hoặc driver không hỗ trợ mapping, hãy chọn schema và adapter theo tài liệu database/driver; không âm thầm đổi sang LocalDateTime mà bỏ mất semantics của instant.

Đọc dữ liệu bằng typed getObject:

~~~java
String sql = "SELECT event_date, local_start, local_appointment, "
        + "occurred_at, zone_id FROM appointment_record "
        + "WHERE appointment_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, id);
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            LocalDate date = rs.getObject("event_date", LocalDate.class);
            LocalTime time = rs.getObject("local_start", LocalTime.class);
            LocalDateTime local = rs.getObject(
                    "local_appointment", LocalDateTime.class);
            OffsetDateTime timestamp = rs.getObject(
                    "occurred_at", OffsetDateTime.class);
            ZoneId zone = ZoneId.of(rs.getString("zone_id"));
            Instant occurredInstant =
                    timestamp == null ? null : timestamp.toInstant();
        }
    }
}
~~~

Nếu occurred_at cho phép NULL, getObject trả null khi SQL NULL. Không gọi toInstant trước khi kiểm tra null. Nếu cột NOT NULL, schema và domain model cần phản ánh ràng buộc đó.

### Lưu ZoneId dưới dạng chuỗi có kiểm soát

ZoneId.getId() trả ID, ví dụ Asia/Ho_Chi_Minh. Khi đọc, ZoneId.of(id) có thể ném DateTimeException nếu ID không hợp lệ hoặc không có trong runtime. Với dữ liệu ngoài hệ thống, validate theo allowlist vùng được sản phẩm chấp nhận. Nếu cần giữ raw ID cũ trong audit, lưu ID cùng policy migration; không tự thay bằng offset cố định.

## 6. Chuyển Instant thành giá trị JDBC có offset

Instant biểu diễn một thời điểm duy nhất, còn JDBC 4.2 mapping tiêu chuẩn cho TIMESTAMP WITH TIME ZONE là OffsetDateTime. Chuyển đổi UTC rõ ràng:

~~~java
Instant instant = Instant.parse("2025-01-31T23:30:00Z");
OffsetDateTime jdbcValue = instant.atOffset(ZoneOffset.UTC);
Instant restored = jdbcValue.toInstant();
~~~

Việc chọn UTC tạo representation nhất quán khi bind/read; database có thể chuẩn hóa offset khi lưu. Nếu nghiệp vụ cần offset gốc hoặc ZoneId gốc để hiển thị, lưu riêng thông tin đó. Đừng suy luận offset gốc từ một OffsetDateTime được đọc lại sau khi database đã normalize.

### OffsetDateTime không giống ZonedDateTime

OffsetDateTime mang offset cụ thể. ZonedDateTime mang ZoneId và offset được áp dụng theo quy tắc vùng. JDBC 4.2 chuẩn hóa mapping cho OffsetDateTime ở TIMESTAMP WITH TIME ZONE; không nên mặc định driver sẽ bind ZonedDateTime trực tiếp.

Nếu cần ghi lịch địa phương theo vùng, lưu ZoneId trong cột riêng hoặc trong bảng lịch. Khi đọc, dùng OffsetDateTime.toInstant() cho thời điểm đã xác định và ZoneId.of(zoneIdString) để khôi phục quy tắc vùng theo policy ứng dụng.

## 7. Precision của SQL timestamp và nano giây

java.time có độ phân giải nanosecond. Database và driver có thể lưu ít chữ số phần giây hơn. Một cột timestamp có precision 6 chỉ giữ tới microsecond; dữ liệu có nano giây thấp hơn có thể bị truncate hoặc round theo database.

~~~java
Instant value = Instant.parse("2025-01-31T23:30:42.123456789Z");
Instant micros = value.truncatedTo(ChronoUnit.MICROS);
~~~

Đây chỉ là phép chuẩn hóa truncate minh họa. Database thực tế có thể làm tròn, cắt hoặc từ chối precision vượt quá scale của cột; hãy đọc tài liệu SQL type và driver. Không áp dụng truncate thủ công nếu hợp đồng yêu cầu rounding hoặc giữ nguyên precision.

### Test round-trip đúng cách

- Chọn schema precision đã biết.
- Ghi giá trị có phần nano giây ở các vị trí biên.
- Đọc lại bằng typed getObject.
- So sánh theo precision mà database cam kết.
- Kiểm tra timestamp ở sát ranh giới truy vấn.
- Không assert equality tới nanosecond nếu cột chỉ giữ microsecond.

### Không tự thêm precision bằng cách chuyển sang String

Format Instant thành chuỗi 9 chữ số nano rồi ghi vào VARCHAR không biến cột đó thành timestamp có semantics. Bạn mất phép so sánh thời gian, index, arithmetic và type validation của database. Chỉ lưu text khi schema/protocol chủ đích là text.
## 8. Tính ranh giới ngày để truy vấn JDBC

Một truy vấn báo cáo theo ngày địa phương nên tính hai mốc bằng LocalDate và ZoneId, rồi bind thành hai tham số:

~~~java
LocalDate date = LocalDate.of(2024, 3, 10);
ZoneId zone = ZoneId.of("America/New_York");

Instant start = date.atStartOfDay(zone).toInstant();
Instant end = date.plusDays(1).atStartOfDay(zone).toInstant();

OffsetDateTime from = start.atOffset(ZoneOffset.UTC);
OffsetDateTime until = end.atOffset(ZoneOffset.UTC);
~~~

SQL nên dùng khoảng nửa mở:

~~~sql
SELECT event_id, occurred_at
FROM event_log
WHERE occurred_at >= ?
  AND occurred_at < ?
ORDER BY occurred_at
~~~

Bind from vào tham số thứ nhất và until vào tham số thứ hai bằng setObject. Cách này tránh tạo giá trị cuối ngày kiểu 23:59:59.999999, vốn phụ thuộc precision của database.

### Vì sao không cộng 24 giờ?

Ngày địa phương có thể dài 23 hoặc 25 giờ khi chuyển DST. Đầu ngày kế tiếp phải tính từ LocalDate.plusDays(1) và atStartOfDay(zone), không phải start.plus(Duration.ofHours(24)).

### Nếu cột là TIMESTAMP không có zone?

Nếu hệ thống quy ước cột TIMESTAMP lưu UTC nhưng không có zone, cần chuyển cả hai Instant sang LocalDateTime theo UTC trước khi bind:

~~~java
LocalDateTime fromUtc =
        LocalDateTime.ofInstant(start, ZoneOffset.UTC);
LocalDateTime untilUtc =
        LocalDateTime.ofInstant(end, ZoneOffset.UTC);
~~~

Quy ước “TIMESTAMP không zone luôn chứa UTC” phải được ghi rõ trong schema/documentation và tuân thủ bởi mọi ứng dụng ghi dữ liệu. Không bind LocalDateTime theo zone máy chủ rồi kỳ vọng database tự biết nó là UTC.

### Index và điều kiện truy vấn

Ưu tiên điều kiện so sánh trực tiếp trên cột timestamp bằng hai tham số. Tránh bọc cột trong hàm chuyển đổi ngày ở WHERE nếu không cần, vì có thể làm giảm khả năng dùng index và khiến kết quả phụ thuộc timezone session. Hãy kiểm tra execution plan trên database thật.

## 9. Ví dụ Java hoàn chỉnh 1 — tính tham số truy vấn ngày có DST

Tạo file **JdbcDayWindowDemo.java**:

~~~java
import java.time.*;

public class JdbcDayWindowDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 3, 10);
        ZoneId zone = ZoneId.of("America/New_York");
        Instant start = date.atStartOfDay(zone).toInstant();
        Instant end = date.plusDays(1).atStartOfDay(zone).toInstant();
        OffsetDateTime from = start.atOffset(ZoneOffset.UTC);
        OffsetDateTime until = end.atOffset(ZoneOffset.UTC);

        System.out.println("from=" + from);
        System.out.println("until=" + until);
        System.out.println("elapsedHours="
                + Duration.between(start, end).toHours());
        System.out.println("sql=occurred_at >= ? AND occurred_at < ?");
    }
}
~~~

Chạy:

~~~text
javac --release 17 JdbcDayWindowDemo.java
java JdbcDayWindowDemo
~~~

Stdout trên OpenJDK 24.0.2:

~~~text
from=2024-03-10T05:00Z
until=2024-03-11T04:00Z
elapsedHours=23
sql=occurred_at >= ? AND occurred_at < ?
~~~

**Phân tích:** Mốc UTC đầu ngày New York là 05:00Z, còn đầu ngày kế tiếp là 04:00Z do offset chuyển từ -05:00 sang -04:00. Khoảng truy vấn dài 23 giờ, đúng một ngày lịch địa phương.

## 10. Transaction, Connection và vòng đời resource

Một repository thường nhận Connection từ tầng quản lý transaction hoặc DataSource. Quy tắc quan trọng:

- Dùng PreparedStatement cho câu lệnh có tham số; không ghép dữ liệu người dùng vào SQL string.
- Dùng try-with-resources cho PreparedStatement và ResultSet để giải phóng resource.
- Connection do pool cấp nên được đóng bằng close khi hoàn thành; pool thường trả connection về pool thay vì đóng socket vật lý.
- Không giữ connection trong lúc chờ người dùng, gọi HTTP hoặc thực hiện tác vụ dài không liên quan database.
- Transaction boundary nên do service/use-case sở hữu nếu một nghiệp vụ gồm nhiều thao tác repository.
- Nếu repository nhận Connection từ caller, không tự commit/rollback transaction của caller.
- Nếu method tự mở transaction, cần setAutoCommit(false), commit khi thành công và rollback khi thất bại; xử lý rollback exception và restore trạng thái phù hợp.

### Ví dụ transaction do service quản lý

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        repository.insert(connection, appointment);
        auditRepository.insert(connection, auditEvent);
        connection.commit();
    } catch (SQLException | RuntimeException ex) {
        connection.rollback();
        throw ex;
    }
}
~~~

Đây là mảnh code minh họa. Trong ứng dụng dùng transaction manager/framework, để framework quản lý commit/rollback và không tự lồng transaction thủ công ngoài policy.

### PreparedStatement typed values và SQL NULL

Nếu một timestamp có thể null, không bind chuỗi "null". Dùng:

~~~java
if (occurredAt == null) {
    ps.setNull(5, Types.TIMESTAMP_WITH_TIMEZONE);
} else {
    ps.setObject(5, occurredAt.atOffset(ZoneOffset.UTC));
}
~~~

SQL type constant cần tương ứng kiểu cột và được driver/database hỗ trợ. Nếu SQL NULL được trả về qua getObject(column, Type.class), kết quả là null; kiểm tra trước khi gọi method trên đối tượng.

## 11. Timezone session và cấu hình database

Các database/driver có thể có timezone session hoặc cấu hình connection ảnh hưởng đến cách parse/hiển thị timestamp. Một số SQL type không mang timezone nhưng driver có thể phải dùng timezone cấu hình để chuyển sang/ra kiểu Java trong các đường chuyển đổi nhất định.

Để tránh kết quả thay đổi theo host:

1. Quy định rõ semantics từng cột: local timestamp, UTC convention hay timestamp có offset.
2. Bind Java temporal type thay vì string literal phụ thuộc locale/session.
3. Dùng Instant/OffsetDateTime cho thời điểm tuyệt đối; LocalDateTime cho trường ngày giờ không zone.
4. Cấu hình timezone session nhất quán theo khuyến nghị driver/database.
5. Kiểm thử khi JVM timezone và database session timezone khác nhau.
6. Kiểm thử giá trị gần nửa đêm UTC và nửa đêm địa phương.
7. Lưu ZoneId riêng nếu cần quy tắc vùng thay đổi theo DST.

### Đừng để timezone mặc định quyết định nghiệp vụ

Một ứng dụng chạy trong container UTC nhưng database session ở America/Los_Angeles có thể làm dữ liệu local timestamp bị hiểu khác nhau nếu driver chuyển đổi ngầm. Không dựa vào máy developer có cùng timezone với production. Tạo integration test cố ý đặt JVM và DB session ở hai zone khác nhau để phát hiện conversion ngầm.

### Database lưu timestamp with time zone có giữ nguyên region không?

Thông thường không. SQL type có thể lưu offset hoặc chuẩn hóa instant, nhưng ZoneId như Europe/Paris là một định danh quy tắc riêng. Nếu cần tái dựng lịch theo quy tắc vùng, hãy lưu ID trong cột riêng và kiểm tra dữ liệu ID khi đọc.

## 12. Ví dụ Java hoàn chỉnh 2 — chuyển Instant sang OffsetDateTime UTC

Tạo file **JdbcInstantMappingDemo.java**:

~~~java
import java.time.*;

public class JdbcInstantMappingDemo {
    public static void main(String[] args) {
        Instant event = Instant.parse("2025-01-31T23:30:00Z");
        OffsetDateTime jdbcValue = event.atOffset(ZoneOffset.UTC);
        Instant restored = jdbcValue.toInstant();
        ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");

        System.out.println("instant=" + event);
        System.out.println("jdbcValue=" + jdbcValue);
        System.out.println("restored=" + restored);
        System.out.println("sameInstant=" + event.equals(restored));
        System.out.println("businessLocal="
                + event.atZone(businessZone));
        System.out.println("storedZoneId=" + businessZone.getId());
    }
}
~~~

Chạy:

~~~text
javac --release 17 JdbcInstantMappingDemo.java
java JdbcInstantMappingDemo
~~~

Stdout trên OpenJDK 24.0.2:

~~~text
instant=2025-01-31T23:30:00Z
jdbcValue=2025-01-31T23:30Z
restored=2025-01-31T23:30:00Z
sameInstant=true
businessLocal=2025-02-01T06:30+07:00[Asia/Ho_Chi_Minh]
storedZoneId=Asia/Ho_Chi_Minh
~~~

**Giải thích:** OffsetDateTime UTC là representation dùng để bind thời điểm tuyệt đối. ZoneId nghiệp vụ được lưu riêng; cùng Instant có thể hiển thị thành ngày 01/02 tại Việt Nam dù ở UTC vẫn là ngày 31/01.

## 13. SQL NULL và JDBC type

Khi một tham số ngày giờ có thể null, driver cần biết SQL type của giá trị null. Dùng setNull với JDBC type tương ứng:

~~~java
ps.setNull(1, Types.DATE);
ps.setNull(2, Types.TIME);
ps.setNull(3, Types.TIMESTAMP);
ps.setNull(4, Types.TIMESTAMP_WITH_TIMEZONE);
~~~

Các hằng số TIME_WITH_TIMEZONE và TIMESTAMP_WITH_TIMEZONE thuộc JDBC 4.2. Database/driver vẫn phải hỗ trợ kiểu SQL tương ứng. Nếu một database không có kiểu timestamp with time zone, phải chọn mô hình lưu trữ thay thế có semantics được quy định rõ.

Với giá trị không null, dùng setObject với Java type phù hợp. Không truyền String "NULL", và không dùng setObject(index, null) mà không có SQL type khi driver không thể suy ra kiểu tham số.

### Đọc SQL NULL

getObject(column, LocalDate.class) trả null nếu SQL value là NULL. Đối với primitive như getLong, JDBC dùng wasNull() để phân biệt SQL NULL với số 0; temporal object mapping không cần primitive sentinel như vậy.

### Null và NOT NULL phải thống nhất với domain

Nếu domain yêu cầu occurredAt luôn có giá trị, hãy ràng buộc cột NOT NULL và validate trước khi ghi. Nếu null có ý nghĩa “chưa xảy ra” hoặc “không xác định”, mô hình hóa rõ trong domain; đừng dùng Instant.EPOCH hoặc một ngày giả làm sentinel.

## 14. TIME WITH TIME ZONE và lịch lặp

OffsetTime biểu diễn giờ cùng offset, ví dụ 09:00+07:00. Nhưng giờ mở cửa 09:00 tại một cửa hàng ở New York không nên được lưu chỉ bằng OffsetTime, vì offset của vùng có thể thay đổi theo DST.

Với lịch mở cửa hằng ngày, mô hình phù hợp thường là:

- LocalTime: giờ địa phương, ví dụ 09:00.
- ZoneId: vùng áp dụng, ví dụ America/New_York.
- Ngày trong tuần hoặc quy tắc recurrence.
- Policy gap/overlap nếu giờ lặp rơi vào thời điểm DST bất thường.

Với một cuộc hẹn đã được xác nhận vào một ngày cụ thể, có thể lưu LocalDateTime + ZoneId để giữ ý định dân sự và lưu Instant/offset đã được xác định để giữ thời điểm chính xác. Cách lưu nào là nguồn chính phải theo quy tắc nghiệp vụ: lịch tương lai có thể cần áp dụng tzdb mới, còn giao dịch đã xảy ra cần giữ Instant đã ghi nhận.

## 15. Ví dụ Java hoàn chỉnh 3 — nhận diện mapping JDBC 4.2

Tạo file **JdbcTemporalMappingDemo.java**:

~~~java
import java.sql.JDBCType;
import java.time.*;

public class JdbcTemporalMappingDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2025, 1, 31);
        LocalTime time = LocalTime.of(9, 30);
        LocalDateTime local = LocalDateTime.of(date, time);
        Instant instant = Instant.parse("2025-01-31T09:30:00Z");
        OffsetDateTime offset = instant.atOffset(ZoneOffset.UTC);

        System.out.println("DATE=" + JDBCType.DATE.getName()
                + " -> LocalDate");
        System.out.println("TIME=" + JDBCType.TIME.getName()
                + " -> LocalTime");
        System.out.println("TIMESTAMP=" + JDBCType.TIMESTAMP.getName()
                + " -> LocalDateTime");
        System.out.println("TIME_TZ="
                + JDBCType.TIME_WITH_TIMEZONE.getName()
                + " -> OffsetTime");
        System.out.println("TIMESTAMP_TZ="
                + JDBCType.TIMESTAMP_WITH_TIMEZONE.getName()
                + " -> OffsetDateTime");
        System.out.println("date=" + date);
        System.out.println("time=" + time);
        System.out.println("localTimestamp=" + local);
        System.out.println("offsetTimestamp=" + offset);
        System.out.println("instantRoundTrip=" + offset.toInstant().equals(instant));
    }
}
~~~

Chạy:

~~~text
javac --release 17 JdbcTemporalMappingDemo.java
java JdbcTemporalMappingDemo
~~~

Stdout trên OpenJDK 24.0.2:

~~~text
DATE=DATE -> LocalDate
TIME=TIME -> LocalTime
TIMESTAMP=TIMESTAMP -> LocalDateTime
TIME_TZ=TIME_WITH_TIMEZONE -> OffsetTime
TIMESTAMP_TZ=TIMESTAMP_WITH_TIMEZONE -> OffsetDateTime
date=2025-01-31
time=09:30
localTimestamp=2025-01-31T09:30
offsetTimestamp=2025-01-31T09:30Z
instantRoundTrip=true
~~~

Đây là demo về Java type và JDBCType constants, không thay thế integration test của driver. Việc driver có thể bind/đọc từng SQL type phải được xác minh với database thật.

## 16. Ví dụ Java hoàn chỉnh 4 — kiểm soát precision microsecond

Tạo file **JdbcPrecisionDemo.java**:

~~~java
import java.time.Instant;
import java.time.temporal.ChronoUnit;

public class JdbcPrecisionDemo {
    public static void main(String[] args) {
        Instant original =
                Instant.parse("2025-01-31T23:30:42.123456789Z");
        Instant truncated = original.truncatedTo(ChronoUnit.MICROS);
        System.out.println("original=" + original);
        System.out.println("truncatedToMicros=" + truncated);
        System.out.println("nanos=" + truncated.getNano());
        System.out.println("lostNanos="
                + (original.getNano() - truncated.getNano()));
    }
}
~~~

Chạy:

~~~text
javac --release 17 JdbcPrecisionDemo.java
java JdbcPrecisionDemo
~~~

Stdout:

~~~text
original=2025-01-31T23:30:42.123456789Z
truncatedToMicros=2025-01-31T23:30:42.123456Z
nanos=123456000
lostNanos=789
~~~

Ví dụ mô phỏng truncate tới microsecond. Đây **không phải cam kết mọi database đều truncate**; có database làm tròn hoặc xử lý theo precision khai báo. Chỉ áp dụng quy tắc normalize khi schema/driver contract đã được xác định.

## 17. Ví dụ Java hoàn chỉnh 5 — chuyển lịch địa phương qua DST

Tạo file **JdbcAppointmentZoneDemo.java**:

~~~java
import java.time.*;
import java.time.zone.ZoneRules;
import java.util.List;

public class JdbcAppointmentZoneDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        ZoneRules rules = zone.getRules();

        LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);
        List<ZoneOffset> gapOffsets = rules.getValidOffsets(gap);
        System.out.println("gapOffsetCount=" + gapOffsets.size());

        LocalDateTime overlap = LocalDateTime.of(2024, 11, 3, 1, 30);
        List<ZoneOffset> offsets = rules.getValidOffsets(overlap);
        ZonedDateTime first = ZonedDateTime.of(overlap, zone);
        ZonedDateTime second = first.withLaterOffsetAtOverlap();
        System.out.println("overlapOffsets=" + offsets);
        System.out.println("firstInstant=" + first.toInstant());
        System.out.println("secondInstant=" + second.toInstant());
        System.out.println("zoneId=" + zone.getId());
    }
}
~~~

Chạy:

~~~text
javac --release 17 JdbcAppointmentZoneDemo.java
java JdbcAppointmentZoneDemo
~~~

Stdout trên OpenJDK 24.0.2:

~~~text
gapOffsetCount=0
overlapOffsets=[-04:00, -05:00]
firstInstant=2024-11-03T05:30:00Z
secondInstant=2024-11-03T06:30:00Z
zoneId=America/New_York
~~~

**Ứng dụng với JDBC:** Lịch địa phương có thể cần lưu local date-time, ZoneId và lựa chọn offset/Instant đã xác nhận. Hai lần 01:30 trong overlap là hai thời điểm khác nhau; chỉ lưu TIMESTAMP không zone sẽ không đủ để phân biệt nếu không có policy bổ sung.

## 18. Kiểm thử integration với đúng database và driver

Compile thành công chỉ chứng minh code dùng đúng API Java. Nó **không chứng minh driver có thể round-trip kiểu ngày giờ**. Để xác nhận tích hợp, cần chạy test với database engine và driver sẽ triển khai.

### Ghi nhận phiên bản môi trường

DatabaseMetaData cung cấp thông tin về database, driver và mức JDBC mà driver khai báo:

~~~java
DatabaseMetaData meta = connection.getMetaData();
System.out.println(meta.getDatabaseProductName());
System.out.println(meta.getDatabaseProductVersion());
System.out.println(meta.getDriverName());
System.out.println(meta.getDriverVersion());
System.out.println(meta.getJDBCMajorVersion() + "."
        + meta.getJDBCMinorVersion());
~~~

Thông tin này hữu ích để chẩn đoán. Tuy nhiên, driver khai báo JDBC 4.2 **không thay thế** việc test mapping cụ thể cho DATE, TIME, TIMESTAMP hoặc TIMESTAMP WITH TIME ZONE.

### Kiểm tra kiểu cột và precision

ResultSetMetaData có thể giúp xác nhận schema mà query trả về:

~~~java
ResultSetMetaData columns = resultSet.getMetaData();
int sqlType = columns.getColumnType(1);
String typeName = columns.getColumnTypeName(1);
int precision = columns.getPrecision(1);
int scale = columns.getScale(1);
~~~

Kết hợp metadata với tài liệu database để hiểu type thật, scale và precision. Tên SQL type trong metadata có thể là tên dialect riêng, không nhất thiết giống hệt tên trong DDL portable.

### Integration test nên thực hiện

1. Tạo bảng tạm hoặc schema riêng với DATE, TIME, TIMESTAMP và type có timezone mà database hỗ trợ.
2. Insert LocalDate, LocalTime, LocalDateTime và OffsetDateTime bằng setObject.
3. Read lại bằng getObject có Type.class.
4. So sánh giá trị theo precision của cột.
5. Test SQL NULL và NOT NULL.
6. Test Instant ngay trước/sau nửa đêm theo ZoneId nghiệp vụ.
7. Test DST gap và overlap nếu lưu lịch địa phương.
8. Đổi JVM timezone và database session timezone để phát hiện conversion ngầm.
9. Test rollback để chắc dữ liệu thời gian và các bảng liên quan cùng tuân theo transaction.
10. Chạy lại với đúng phiên bản driver/database production.

Dùng Testcontainers hoặc môi trường integration riêng nếu dự án có hạ tầng phù hợp. H2/SQLite có thể tiện cho test nhanh, nhưng **không chứng minh semantics giống PostgreSQL, Oracle, SQL Server hay MySQL**.

### Không chỉ test setObject thành công

Một số driver có thể chấp nhận parameter nhưng normalize/truncate/convert khác mong muốn. Test cần đọc lại giá trị, kiểm tra type, offset/instant, precision và truy vấn ranh giới. Thành công ở executeUpdate một mình chưa đủ.

## 19. Ví dụ Java hoàn chỉnh 6 — cùng Instant ở nhiều vùng

Tạo file **JdbcSessionZoneDemo.java**:

~~~java
import java.time.*;

public class JdbcSessionZoneDemo {
    public static void main(String[] args) {
        Instant stored = Instant.parse("2025-01-31T23:30:00Z");
        OffsetDateTime jdbcValue = stored.atOffset(ZoneOffset.UTC);
        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
        ZoneId newYork = ZoneId.of("America/New_York");

        System.out.println("jdbcUtc=" + jdbcValue);
        System.out.println("vietnam=" + stored.atZone(vietnam));
        System.out.println("newYork=" + stored.atZone(newYork));
        System.out.println("sameInstant="
                + stored.equals(jdbcValue.toInstant()));
    }
}
~~~

Chạy:

~~~text
javac --release 17 JdbcSessionZoneDemo.java
java JdbcSessionZoneDemo
~~~

Stdout trên OpenJDK 24.0.2:

~~~text
jdbcUtc=2025-01-31T23:30Z
vietnam=2025-02-01T06:30+07:00[Asia/Ho_Chi_Minh]
newYork=2025-01-31T18:30-05:00[America/New_York]
sameInstant=true
~~~

Một Instant duy nhất có thể hiển thị thành ngày khác nhau ở các vùng. Khi lưu thời điểm tuyệt đối, hãy giữ Instant/OffsetDateTime; chỉ chuyển sang ZoneId của người dùng ở lớp hiển thị hoặc khi áp dụng quy tắc lịch địa phương.

## 20. Cấu hình driver, SQL dialect và khả năng hỗ trợ

### JDBC version và driver version

JDBC 4.2 bổ sung mapping java.time, nhưng cần driver đủ mới và có triển khai. Đừng chỉ kiểm tra JDK version; kiểm tra:

- Driver version và JDBC major/minor version.
- Database product/version.
- SQL type có tồn tại trong database hay không.
- Driver có hỗ trợ setObject/getObject cho Java type cụ thể không.
- Hành vi khi NULL, precision, timezone session và conversion.

### SQL dialect khác nhau

Một schema minh họa dùng DATE, TIME, TIMESTAMP và TIMESTAMP WITH TIME ZONE. Database thực tế có thể:

- Dùng tên kiểu riêng cho timestamp có timezone.
- Không hỗ trợ TIME WITH TIME ZONE.
- Có precision phần giây mặc định khác nhau.
- Chuẩn hóa timestamp về UTC.
- Có quy tắc session timezone ảnh hưởng conversion.
- Có giới hạn khác nhau về offset hoặc timezone region.

Đặt DDL trong migration theo dialect của database. Đừng copy nguyên schema minh họa vào mọi hệ thống mà không xác minh.

### Driver không hỗ trợ mapping trực tiếp

Nếu driver cũ hoặc database thiếu type, lựa chọn adapter phải được xác định theo tài liệu driver và schema. Có thể cần một biểu diễn tương thích, nhưng phải bảo toàn semantics: ví dụ lưu Instant theo quy ước UTC có tài liệu rõ, hoặc lưu epoch seconds/nanos trong các cột số nếu đó là thiết kế schema chủ đích. Không chuyển sang chuỗi localized hoặc LocalDateTime không zone một cách ngầm định.

**Không viết fallback tự động thử type này, lỗi thì đổi sang type khác trong production** nếu không bảo đảm dữ liệu giữ nguyên ý nghĩa. Hãy chọn chiến lược schema/mapping trước, version hóa migration và kiểm thử tương thích.

## 21. Null, exception và lỗi chuyển đổi

Các lỗi có thể xuất hiện ở nhiều giai đoạn:

| Giai đoạn | Lỗi thường gặp | Cách xử lý |
|---|---|---|
| setObject | SQLException / SQLFeatureNotSupportedException | Kiểm tra mapping driver và SQL type |
| setNull | SQL type không được hỗ trợ | Dùng type tương ứng với schema |
| executeUpdate | ConstraintViolation/SQLException | Kiểm tra NOT NULL, range, precision và transaction |
| getObject(type) | SQLException hoặc conversion không hỗ trợ | Kiểm tra type driver trả và tài liệu driver |
| ZoneId.of | DateTimeException | Validate zone ID theo policy |
| LocalDateTime chuyển sang zone | Gap/overlap | Kiểm tra ZoneRules và policy nghiệp vụ |
| Timestamp precision | Giá trị bị round/truncate | Test theo scale của cột |

### Không nuốt SQLException

Ghi log có ngữ cảnh (operation, table, driver/database version, parameter type), nhưng tránh log dữ liệu cá nhân nhạy cảm. Ném exception lên tầng xử lý phù hợp hoặc chuyển thành lỗi domain rõ ràng. Không bắt SQLException rồi trả thành công với timestamp mặc định.

### Không nhầm lỗi driver với lỗi dữ liệu nghiệp vụ

- SQLFeatureNotSupportedException có thể báo một feature không được driver hỗ trợ.
- SQLDataException có thể báo lỗi dữ liệu/conversion.
- DateTimeException có thể phát sinh khi parse/resolve zone.
- Constraint violation là lỗi schema/ràng buộc.

Phân loại nguyên nhân để biết cần nâng driver, sửa schema, validate input hay thay đổi policy; đừng tự retry vô hạn một lỗi mapping cố định.

## 22. Lưu trữ lịch hẹn và sự kiện: chọn mô hình đúng

### Sự kiện đã xảy ra

Ví dụ payment captured lúc một thời điểm duy nhất:

- Lưu Instant hoặc OffsetDateTime UTC vào cột timestamp có semantics thời điểm.
- Có thể lưu ZoneId/offset dùng để hiển thị nếu audit cần biết ngữ cảnh.
- Không chỉ lưu LocalDateTime vì giá trị đó có thể mơ hồ khi đổi DST.

### Lịch hẹn một lần theo giờ địa phương

Ví dụ người dùng chọn 09:00 ngày 20/05 tại Paris:

- Lưu LocalDateTime.
- Lưu ZoneId Europe/Paris.
- Resolve sang Instant theo ZoneRules và policy gap/overlap.
- Lưu Instant đã xác nhận để thực thi chính xác.
- Nếu lịch được chỉnh sửa khi luật vùng thay đổi, xác định rõ dùng local wall time hay Instant đã xác nhận làm nguồn chính.

### Lịch lặp theo giờ dân sự

Ví dụ 09:00 mỗi thứ Hai tại New York:

- Lưu LocalTime, recurrence rule và ZoneId America/New_York.
- Tạo từng lần chạy dựa trên ngày địa phương và ZoneRules tại ngày đó.
- Xác định policy khi giờ 09:00 rơi vào gap/overlap (nếu vùng có chuyển đổi vào thời điểm đó).
- Không thay ZoneId bằng một offset cố định.

### Ngày sinh hoặc ngày hiệu lực chỉ theo lịch

Dùng LocalDate/SQL DATE. Không thêm 00:00 UTC vì điều đó có thể làm lệch ngày khi hiển thị ở vùng khác.

## 23. Những lỗi thường gặp

### 23.1. Lưu mọi thứ vào TIMESTAMP

Ngày sinh, giờ mở cửa và thời điểm giao dịch có semantics khác nhau. Chọn SQL type và Java type theo ý nghĩa dữ liệu.

### 23.2. Nghĩ SQL TIMESTAMP mặc định là UTC

TIMESTAMP không mang zone. Nếu ứng dụng quy ước UTC, phải ghi rõ và đảm bảo mọi reader/writer cùng thực hiện.

### 23.3. Dùng LocalDateTime cho một thời điểm toàn cầu

LocalDateTime không có offset/zone. Dùng Instant hoặc OffsetDateTime cho một thời điểm xác định.

### 23.4. Mong TIMESTAMP WITH TIME ZONE lưu ZoneId

OffsetDateTime chỉ có offset. Lưu ZoneId riêng nếu cần tái dựng quy tắc vùng.

### 23.5. Bind ngày giờ bằng String

Chuỗi phụ thuộc format và session settings. Dùng setObject với typed value khi driver hỗ trợ.

### 23.6. Dùng getString rồi parse cho mọi temporal column

Bạn tự gánh format, locale, offset và precision. Ưu tiên getObject(column, Type.class) theo JDBC 4.2.

### 23.7. Cho rằng mọi driver hỗ trợ TIME WITH TIME ZONE

SQL type và mapping không đồng đều giữa database. Kiểm tra driver/database cụ thể.

### 23.8. Coi Instant là JDBC type chuẩn trực tiếp

JDBC 4.2 mapping tiêu chuẩn cho TIMESTAMP WITH TIME ZONE là OffsetDateTime. Chuyển Instant sang OffsetDateTime UTC khi cần mapping portable.

### 23.9. Bỏ mất zone gốc sau khi đọc timestamp

Database có thể normalize offset. Lưu ZoneId riêng nếu nghiệp vụ cần hiển thị hoặc lịch dân sự.

### 23.10. Cộng 24 giờ để lấy đầu ngày mai

DST có thể tạo ngày 23/25 giờ. Tính ngày kế tiếp bằng LocalDate.plusDays(1).atStartOfDay(zone).

### 23.11. Dùng LocalDateTime để truy vấn timestamp UTC mà không chuyển zone

LocalDateTime không có zone. Chuyển Instant sang UTC LocalDateTime theo quy ước cột hoặc dùng OffsetDateTime cho cột có timezone.

### 23.12. Query cuối ngày bằng 23:59:59.999999

Precision database khác nhau. Dùng khoảng [start,end) với đầu ngày kế tiếp là end exclusive.

### 23.13. Bỏ qua precision của database

Nano giây có thể bị truncate/round. Kiểm tra scale cột và assert theo precision được cam kết.

### 23.14. Nghĩ executeUpdate thành công chứng minh round-trip đúng

Driver có thể chuyển đổi hoặc normalize. Đọc lại và so sánh theo semantics/precision.

### 23.15. Để default timezone của JVM quyết định dữ liệu

Container và database có thể dùng zone khác nhau. Truyền ZoneId/OffsetDateTime rõ và kiểm thử session timezone.

### 23.16. Lưu giờ lịch lặp chỉ bằng TIME WITH TIME ZONE

Không có ngày nên không thể áp dụng đầy đủ DST rule của một vùng. Lưu LocalTime + ZoneId + recurrence.

### 23.17. Tự commit trong repository khi caller quản lý transaction

Điều này phá vỡ transaction bao quanh nhiều thao tác. Quy định transaction boundary ở tầng service/use-case.

### 23.18. Không đóng PreparedStatement/ResultSet

Dùng try-with-resources. Connection do pool cấp được trả về pool khi close theo contract pool.

### 23.19. Dùng connection mới cho mỗi câu lệnh mà không quản lý pool

Connection establishment đắt và có thể làm cạn tài nguyên. Dùng DataSource/connection pool được cấu hình và quản lý bởi ứng dụng.

### 23.20. Chỉ test trên H2 rồi kết luận production database tương tự

Dialect, timezone, precision và driver mapping có thể khác. Test integration trên đúng database/driver production.

## 24. Checklist trước khi tích hợp ngày giờ với JDBC

- Mỗi cột đã được phân loại là ngày lịch, giờ địa phương, local timestamp hay instant chưa?
- SQL DATE có map sang LocalDate không?
- SQL TIME có map sang LocalTime không?
- SQL TIMESTAMP có map sang LocalDateTime và được document semantics không?
- TIMESTAMP WITH TIME ZONE có được map sang OffsetDateTime nếu driver hỗ trợ không?
- Instant có được chuyển sang OffsetDateTime UTC rõ ràng khi bind không?
- ZoneId có được lưu riêng nếu nghiệp vụ cần tái dựng vùng không?
- Có kiểm tra driver/database hỗ trợ đúng mapping JDBC 4.2 không?
- Dùng setObject/getObject typed thay vì string parsing khi có thể không?
- SQL NULL có bind bằng SQL type tương ứng không?
- Cột timestamp có precision/scale được xác định chưa?
- Round-trip có được test theo precision thực tế không?
- Ranh giới ngày có được tính theo ZoneId nghiệp vụ và khoảng [start,end) không?
- Có test ngày 23/25 giờ, DST gap/overlap và nửa đêm không?
- JVM timezone và DB session timezone có được kiểm thử độc lập không?
- PreparedStatement/ResultSet/Connection có lifecycle rõ ràng không?
- Transaction boundary có do một tầng chịu trách nhiệm không?
- Query có bind parameters và giữ khả năng dùng index không?
- Có integration test trên đúng database/driver production không?
- Có ghi nhận phiên bản JDK, driver và database trong test report không?

## 25. Bài tập tự kiểm tra

**Câu 1.** SQL DATE nên map sang Java type nào?

*Đáp án:* LocalDate, vì nó chỉ biểu diễn ngày lịch.

**Câu 2.** SQL TIMESTAMP không WITH TIME ZONE tương ứng kiểu Java nào trong JDBC 4.2?

*Đáp án:* LocalDateTime; nó không tự mang offset hoặc zone.

**Câu 3.** JDBC 4.2 mapping tiêu chuẩn cho TIMESTAMP WITH TIME ZONE là gì?

*Đáp án:* OffsetDateTime. Driver/database vẫn cần hỗ trợ type đó.

**Câu 4.** Có nên giả định Instant được JDBC 4.2 map trực tiếp vào mọi driver không?

*Đáp án:* Không. Chuyển Instant sang OffsetDateTime UTC cho mapping portable hơn.

**Câu 5.** Vì sao OffsetDateTime không thay thế ZoneId?

*Đáp án:* OffsetDateTime chỉ lưu offset cụ thể; ZoneId chứa quy tắc vùng thay đổi theo thời gian.

**Câu 6.** Cách bind LocalDate vào PreparedStatement hiện đại là gì?

*Đáp án:* setObject(index, localDate), nếu driver hỗ trợ JDBC 4.2 mapping.

**Câu 7.** Cách đọc DATE thành LocalDate là gì?

*Đáp án:* ResultSet.getObject(column, LocalDate.class).

**Câu 8.** Vì sao không dùng chuỗi 31/01/2025 09:30 để bind timestamp?

*Đáp án:* Nó phụ thuộc format/locale/session; typed setObject rõ kiểu và tránh parse mơ hồ.

**Câu 9.** Làm sao truy vấn mọi sự kiện trong một ngày New York có DST?

*Đáp án:* Tính start bằng date.atStartOfDay(zone), end bằng date.plusDays(1).atStartOfDay(zone), chuyển sang Instant/OffsetDateTime và dùng start <= value < end.

**Câu 10.** Vì sao ngày có thể dài 23 hoặc 25 giờ?

*Đáp án:* DST làm offset thay đổi trong ngày; ngày địa phương không luôn bằng 24 giờ elapsed.

**Câu 11.** Database có nhất thiết giữ nano giây không?

*Đáp án:* Không. Precision phụ thuộc kiểu cột, database và driver; test theo scale đã khai báo.

**Câu 12.** Khi SQL value là NULL, getObject(column, LocalDate.class) trả gì?

*Đáp án:* null; kiểm tra trước khi gọi method trên kết quả.

**Câu 13.** Vì sao cần setNull với JDBC type cụ thể?

*Đáp án:* Driver cần biết kiểu SQL của parameter null, nhất là khi không thể suy luận từ Java object.

**Câu 14.** Có thể chỉ lưu LocalDateTime cho một lịch hẹn toàn cầu không?

*Đáp án:* Không đủ nếu cần xác định Instant; phải bổ sung ZoneId/offset và policy gap/overlap.

**Câu 15.** Vì sao test trên H2 chưa đủ cho PostgreSQL/Oracle production?

*Đáp án:* SQL dialect, timezone, precision và JDBC driver mapping có thể khác nhau.

**Câu 16.** Khi nào cần lưu ZoneId trong cột riêng?

*Đáp án:* Khi cần tái dựng giờ địa phương, hiển thị theo vùng hoặc tính lịch dân sự qua DST.

**Câu 17.** Ai nên quản lý commit/rollback khi nhiều repository thuộc cùng một use case?

*Đáp án:* Tầng service/use-case hoặc transaction manager; repository dùng Connection được truyền vào và không tự commit transaction của caller.

## 26. Tài liệu chính thức còn được duy trì

- Oracle Java SE 25 — **java.sql.PreparedStatement**: setObject, setNull và parameter binding: https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/PreparedStatement.html
- Oracle Java SE 25 — **java.sql.ResultSet**: getObject(column, Class<T>) và SQL NULL: https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/ResultSet.html
- Oracle Java SE 25 — **java.sql.JDBCType**: SQL type constants trong JDBC: https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/JDBCType.html
- Oracle Java SE 25 — **java.sql.DatabaseMetaData**: driver, database version và metadata: https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/DatabaseMetaData.html
- Oracle Java SE 25 — **java.sql.ResultSetMetaData**: SQL type, precision và scale của cột: https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/ResultSetMetaData.html
- Microsoft — **JDBC 4.2 compliance**: ví dụ driver công bố mapping Java 8 date/time và SQL type mới: https://learn.microsoft.com/en-us/sql/connect/jdbc/jdbc-4-2-compliance-for-the-jdbc-driver?view=sql-server-ver17
- Oracle — **JDBC Reference Information**: lưu ý Oracle DATE có phần thời gian và mapping theo driver: https://docs.oracle.com/en/database/oracle/oracle-database/26/jjdbc/JDBC-reference-information.html
- Oracle Java SE 25 — **java.time.LocalDate**: ngày lịch và chuyển đổi zone: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/LocalDate.html
- Oracle Java SE 25 — **java.time.OffsetDateTime**: ngày giờ có offset và chuyển sang Instant: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/OffsetDateTime.html
- Oracle Java SE 25 — **java.time.ZoneId**: ID vùng và quy tắc timezone: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/ZoneId.html
- Oracle Java SE 25 — **java.time.zone.ZoneRules**: gap, overlap và valid offsets: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/zone/ZoneRules.html
- Oracle — **JDBC 4.2 Specification**: mapping các kiểu Java 8 date/time: https://jcp.org/en/jsr/detail?id=221
- PostgreSQL — **Date/Time Types**: semantics date/time/timestamp và timezone: https://www.postgresql.org/docs/current/datatype-datetime.html
- MySQL — **Date and Time Data Types**: precision và timezone behavior: https://dev.mysql.com/doc/refman/8.4/en/date-and-time-types.html

**Kết luận:** Tích hợp ngày giờ với JDBC bắt đầu từ việc chọn đúng semantics: LocalDate cho ngày, LocalTime cho giờ địa phương, LocalDateTime cho timestamp không zone, OffsetDateTime cho timestamp có offset và Instant cho thời điểm tuyệt đối trong domain. JDBC 4.2 hỗ trợ typed setObject/getObject, nhưng driver/database quyết định khả năng mapping và precision thực tế. Lưu ZoneId riêng khi cần lịch dân sự, tính ranh giới ngày theo vùng và dùng khoảng [start,end). Kiểm thử round-trip trên đúng database/driver, với DST, timezone session, NULL và precision; không dựa vào chuỗi localized hoặc default timezone.
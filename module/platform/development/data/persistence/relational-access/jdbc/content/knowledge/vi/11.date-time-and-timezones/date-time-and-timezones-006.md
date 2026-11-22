# Làm việc với java.sql.Date, Time và Timestamp trong mã cũ

Nhiều ứng dụng Java truy cập cơ sở dữ liệu quan hệ qua **JDBC** đã được viết trước khi API `java.time` ra đời. Trong DAO và repository của các ứng dụng đó, bạn thường gặp `java.sql.Date`, `java.sql.Time`, `java.sql.Timestamp` cùng các phương thức `PreparedStatement#setDate`, `setTime`, `setTimestamp` và `ResultSet#getDate`, `getTime`, `getTimestamp`. Hiểu rõ những lớp này giúp bảo trì hệ thống, sửa lỗi lệch ngày giờ và từng bước nâng cấp sang Java hiện đại mà không làm sai dữ liệu đang lưu.

Bài học tập trung vào **API ngày giờ cũ của JDBC**, ý nghĩa của chúng khi ánh xạ với các kiểu SQL, điểm khác biệt so với `java.util.Date` và `java.time`, ảnh hưởng của múi giờ và độ chính xác, cũng như cách cải tiến code cũ an toàn. Các ví dụ dùng `DataSource`, `PreparedStatement` và `ResultSet` để minh họa SQL tham số hóa, CRUD và quản lý kết nối bằng API chuẩn JDBC.

## 1. Hiểu đúng ngữ nghĩa trước khi đọc mã

| Kiểu cột SQL | Lớp JDBC cũ | Dữ liệu nghiệp vụ | Kiểu Java hiện đại |
|---|---|---|---|
| `DATE` | `java.sql.Date` | Ngày trên lịch, như ngày sinh hoặc ngày hiệu lực | `LocalDate` |
| `TIME` (không múi giờ) | `java.sql.Time` | Giờ trong ngày, như giờ mở cửa | `LocalTime` |
| `TIMESTAMP` (không múi giờ) | `java.sql.Timestamp` | Ngày và giờ địa phương, như lịch hẹn tại chi nhánh | `LocalDateTime` |
| Thời điểm tuyệt đối | Thường gặp `java.sql.Timestamp` trong mã cũ | Một sự kiện đã xảy ra tại thời điểm duy nhất | `Instant`; `OffsetDateTime` nếu kiểu SQL thích hợp |

Ba lớp `java.sql.Date`, `java.sql.Time`, `java.sql.Timestamp` đều kế thừa từ `java.util.Date`, nhưng không có nghĩa chúng biểu diễn thông tin như nhau:

- `java.sql.Date` chỉ có ý nghĩa **ngày** khi làm việc với SQL `DATE`. Phần giờ nội bộ không phải giờ nghiệp vụ.
- `java.sql.Time` chỉ có ý nghĩa **giờ trong ngày** khi làm việc với SQL `TIME`. Phần ngày nội bộ không phải ngày nghiệp vụ.
- `java.sql.Timestamp` giữ thông tin ngày giờ và phần giây lẻ; bản thân tên `Timestamp` **không khẳng định giá trị SQL có múi giờ**.

Các lớp cũ sử dụng biểu diễn có liên quan đến mili giây tính từ mốc epoch, nên việc xây dựng hoặc diễn giải giá trị có thể chịu tác động từ múi giờ của JVM hoặc driver. Ngược lại, một cột SQL `DATE` thường không có khái niệm thời điểm, còn cột `TIMESTAMP WITHOUT TIME ZONE` chỉ giữ các trường ngày giờ, không giữ tên vùng giờ.

### Phân biệt `java.util.Date` và `java.sql.Date`

Trong dự án cũ, đọc đúng phần `import` là rất quan trọng:

```java
import java.util.Date;

Date utilDate = new Date(); // Có ý nghĩa mốc thời gian kiểu cũ

// SQL DATE là kiểu khác:
java.sql.Date sqlDate = java.sql.Date.valueOf("2026-11-17");
```

`PreparedStatement#setDate` yêu cầu `java.sql.Date`, không nhận trực tiếp `java.util.Date`. Khi cả hai loại xuất hiện trong cùng tệp, nên viết tên lớp đầy đủ để tránh hiểu nhầm. Không chuyển ngày sinh thành một `Instant` chỉ vì `java.sql.Date` có `getTime()`.

## 2. Các phương thức JDBC thường gặp

| Thao tác | API trên JDBC | Kiểu Java |
|---|---|---|
| Ghi cột `DATE` | `ps.setDate(index, value)` | `java.sql.Date` |
| Đọc cột `DATE` | `rs.getDate(column)` | `java.sql.Date` hoặc `null` |
| Ghi cột `TIME` | `ps.setTime(index, value)` | `java.sql.Time` |
| Đọc cột `TIME` | `rs.getTime(column)` | `java.sql.Time` hoặc `null` |
| Ghi cột `TIMESTAMP` | `ps.setTimestamp(index, value)` | `java.sql.Timestamp` |
| Đọc cột `TIMESTAMP` | `rs.getTimestamp(column)` | `java.sql.Timestamp` hoặc `null` |
| Chọn múi giờ cho phép chuyển đổi cũ | Các overload có thêm `Calendar` | `Calendar` cung cấp ngữ cảnh vùng giờ |

Chỉ số tham số trong `PreparedStatement` bắt đầu từ **1**. Khi đọc `ResultSet`, có thể dùng tên cột hoặc vị trí cột. Getter trả `null` nếu ô SQL là `NULL`, vì vậy phải kiểm tra trước khi gọi các phương thức chuyển đổi.

### Tạo đối tượng bằng factory

```java
import java.sql.Date;
import java.sql.Time;
import java.sql.Timestamp;

Date serviceDay = Date.valueOf("2026-11-17");
Time opensAt = Time.valueOf("08:30:00");
Timestamp appointment = Timestamp.valueOf("2026-11-17 09:15:30.123456");

System.out.println(serviceDay);  // 2026-11-17
System.out.println(opensAt);     // 08:30:00
System.out.println(appointment); // Ngày giờ có phần giây lẻ
```

Các phương thức `valueOf(String)` nhận định dạng theo quy định API, không phải chuỗi tùy ý như `17/11/2026`. Nếu chuỗi từ giao diện người dùng có định dạng khác, cần parse theo quy tắc nghiệp vụ trước, không nối chuỗi đó trực tiếp vào câu SQL.

## 3. Ví dụ DAO: sử dụng `Date`, `Time`, `Timestamp` để CRUD

Giả sử cơ sở dữ liệu có bảng lịch phục vụ:

```sql
CREATE TABLE legacy_schedule (
    id BIGINT PRIMARY KEY,
    service_day DATE NOT NULL,
    opening_time TIME NOT NULL,
    appointment_local TIMESTAMP NOT NULL
);
```

`service_day` là ngày theo lịch, `opening_time` là giờ trong ngày và `appointment_local` là ngày/giờ địa phương của cơ sở. SQL minh họa kiểu dữ liệu thường gặp; cú pháp và độ chính xác chi tiết cần xác minh trên DBMS đang dùng.

DAO sau nhận đầu vào ở dạng `java.time` nhưng dùng API JDBC legacy tại ranh giới dữ liệu. Đây là phương án chuyển tiếp khi hệ thống chưa thể đổi driver:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.Date;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Time;
import java.sql.Timestamp;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;

public final class LegacyScheduleDao {
    private final DataSource dataSource;

    public LegacyScheduleDao(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void create(long id,
                       LocalDate serviceDay,
                       LocalTime openingTime,
                       LocalDateTime appointmentLocal) throws SQLException {
        String sql = "INSERT INTO legacy_schedule "
                + "(id, service_day, opening_time, appointment_local) "
                + "VALUES (?, ?, ?, ?)";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, id);
            ps.setDate(2, Date.valueOf(serviceDay));
            ps.setTime(3, Time.valueOf(openingTime));
            ps.setTimestamp(4, Timestamp.valueOf(appointmentLocal));
            ps.executeUpdate();
        }
    }

    public LocalDateTime findAppointment(long id) throws SQLException {
        String sql =
                "SELECT appointment_local FROM legacy_schedule WHERE id = ?";
        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, id);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return null; // Không có bản ghi
                }
                Timestamp saved = rs.getTimestamp("appointment_local");
                return saved == null ? null : saved.toLocalDateTime();
            }
        }
    }

    public int updateOpeningTime(long id, LocalTime newTime)
            throws SQLException {
        String sql =
                "UPDATE legacy_schedule SET opening_time = ? WHERE id = ?";
        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setTime(1, Time.valueOf(newTime));
            ps.setLong(2, id);
            return ps.executeUpdate();
        }
    }

    public int delete(long id) throws SQLException {
        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(
                     "DELETE FROM legacy_schedule WHERE id = ?")) {
            ps.setLong(1, id);
            return ps.executeUpdate();
        }
    }
}
```

Ưu điểm của ví dụ:

- `?` và các phương thức `set...` truyền giá trị tham số theo kiểu, không phải tự định dạng chuỗi SQL.
- `try-with-resources` đóng `ResultSet`, `PreparedStatement` và `Connection`, giúp trả kết nối về pool nếu `DataSource` có pooling.
- Chuyển đổi sang kiểu `java.time` gần ranh giới JDBC; tầng nghiệp vụ không phải truyền đối tượng mutable `java.sql.*`.

**Giới hạn của API cũ:** `Time.valueOf(LocalTime)` không phải đường truyền bảo toàn phần giây lẻ có độ chính xác cao. `Timestamp.valueOf(LocalDateTime)` có thể phụ thuộc múi giờ mặc định khi ánh xạ sang biểu diễn cũ. Nếu một nghiệp vụ ghi đồng thời nhiều bảng, cần giữ các lệnh trong cùng một `Connection` và transaction; việc chọn kiểu ngày giờ không thay thế `commit`/`rollback`.

## 4. Chuyển đổi an toàn sang `java.time`

Nên phân biệt **chuyển đổi theo ngày/giờ địa phương** với **chuyển đổi theo thời điểm tuyệt đối**.

### 4.1. Ngày, giờ và ngày-giờ địa phương

```java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;

LocalDate day = LocalDate.of(2026, 11, 17);
java.sql.Date sqlDay = java.sql.Date.valueOf(day);
LocalDate restoredDay = sqlDay.toLocalDate();

LocalTime opens = LocalTime.of(8, 30, 15);
java.sql.Time sqlClock = java.sql.Time.valueOf(opens);
LocalTime restoredClock = sqlClock.toLocalTime();

LocalDateTime local = LocalDateTime.of(2026, 11, 17, 9, 15);
java.sql.Timestamp sqlLocal = java.sql.Timestamp.valueOf(local);
LocalDateTime restoredLocal = sqlLocal.toLocalDateTime();
```

`LocalDate`, `LocalTime` và `LocalDateTime` không chứa độ lệch UTC hoặc mã múi giờ. Các chuyển đổi trên phù hợp với cột SQL **không múi giờ** theo ngữ nghĩa tương ứng. Tuy nhiên, vì đối tượng cũ có biểu diễn liên quan epoch, cần kiểm chứng thực tế khi máy chủ hoặc driver thay đổi vùng giờ.

Không dùng `java.sql.Date.toInstant()` hoặc `java.sql.Time.toInstant()`:

```java
java.sql.Date onlyDate = java.sql.Date.valueOf("2026-11-17");
java.sql.Time onlyTime = java.sql.Time.valueOf("08:30:00");

// Hai lời gọi dưới đây sẽ ném UnsupportedOperationException:
// onlyDate.toInstant();
// onlyTime.toInstant();
```

Ngày sinh hoặc giờ mở cửa không xác định một thời điểm trên dòng thời gian, nên cố suy ra `Instant` từ một trong hai giá trị đó là sai ngữ nghĩa.

### 4.2. Cùng lớp `Timestamp`, hai cách chuyển đổi khác nhau

```java
import java.sql.Timestamp;
import java.time.Instant;
import java.time.LocalDateTime;

// Trường hợp nghiệp vụ có một thời điểm tuyệt đối:
Instant happened = Instant.parse("2026-11-17T02:15:00Z");
Timestamp forInstant = Timestamp.from(happened);
Instant recoveredInstant = forInstant.toInstant();

// Trường hợp nghiệp vụ có ngày/giờ địa phương:
LocalDateTime planned = LocalDateTime.of(2026, 11, 17, 9, 15);
Timestamp forLocal = Timestamp.valueOf(planned);
LocalDateTime recoveredLocal = forLocal.toLocalDateTime();
```

`Timestamp.from(Instant)`/`toInstant()` bảo toàn ý nghĩa một mốc thời gian **trong đối tượng Java**. `Timestamp.valueOf(LocalDateTime)`/`toLocalDateTime()` phục vụ ngày/giờ địa phương. Khi ghi qua JDBC, ý nghĩa thực tế vẫn phụ thuộc kiểu cột SQL và quy tắc chuyển đổi của driver. Không dùng hai cặp trên lẫn lộn để “sửa lệch múi giờ”.

Nếu lịch hẹn là 09:15 tại một địa điểm, trước hết phải biết vùng giờ địa điểm mới quy ra thời điểm:

```java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;

LocalDateTime appointmentLocal = LocalDateTime.of(2026, 11, 17, 9, 15);
ZoneId branchZone = ZoneId.of("Asia/Ho_Chi_Minh");
Instant appointmentInstant =
        appointmentLocal.atZone(branchZone).toInstant();
```

Với vùng có thay đổi giờ mùa hè (DST), một giờ địa phương có thể bị lặp hoặc không tồn tại. `atZone` có cách xử lý mặc định, nhưng ứng dụng đặt lịch nên xác định chính sách cho các trường hợp này thay vì dựa vào giả định rằng mọi ngày đều có 24 giờ.

## 5. Vì sao mã cũ có thể lệch ngày giờ khi đổi server?

Xét đoạn:

```java
Timestamp value = Timestamp.valueOf("2026-11-17 09:15:00");
ps.setTimestamp(1, value);
```

`Timestamp` của Java có biểu diễn theo epoch, còn SQL `TIMESTAMP` **không múi giờ** thường lưu các trường ngày, giờ. Driver phải diễn giải một biểu diễn thành biểu diễn còn lại. Với overload không nhận `Calendar`, trình điều khiển có thể sử dụng múi giờ mặc định của JVM hoặc các thiết lập liên quan. Nếu JVM đổi từ `Asia/Ho_Chi_Minh` sang UTC, hoặc múi giờ phiên CSDL đổi, cùng dữ liệu có thể bị ánh xạ khác khi ghi và đọc.

JDBC cũ cung cấp overload nhận `Calendar` để chỉ định vùng giờ cho phép chuyển đổi:

```java
import java.sql.Timestamp;
import java.util.Calendar;
import java.util.TimeZone;

// Giả định eventInstant là Instant đã xác định:
Calendar utcWrite = Calendar.getInstance(TimeZone.getTimeZone("UTC"));
ps.setTimestamp(1, Timestamp.from(eventInstant), utcWrite);

Calendar utcRead = Calendar.getInstance(TimeZone.getTimeZone("UTC"));
Timestamp restored = rs.getTimestamp("occurred_at", utcRead);
```

Ví dụ trên chỉ phù hợp nếu hệ thống **chủ động quy ước cột `TIMESTAMP` không múi giờ lưu dạng UTC** cho sự kiện có ý nghĩa thời điểm và kiểm chứng driver dùng `Calendar` như mong đợi. Cần nhất quán cả khi ghi và đọc. `Calendar` không làm cột SQL lưu được `ZoneId` và không biến `Timestamp` thành đối tượng có vùng giờ.

Các overload `setDate(..., Calendar)`, `setTime(..., Calendar)`, `getDate(..., Calendar)` và `getTime(..., Calendar)` cũng tồn tại. Chúng là cơ chế hỗ trợ chuyển đổi của API cũ, **không có nghĩa cột `DATE` hoặc `TIME` không múi giờ tự lưu múi giờ**. Không tự đặt UTC cho ngày sinh hoặc giờ mở cửa chỉ vì UTC thích hợp với log sự kiện.

### Một số khác biệt DBMS cần nhận diện

| Hệ quản trị / cột | Điều quan trọng khi bảo trì JDBC |
|---|---|
| PostgreSQL `TIMESTAMP WITHOUT TIME ZONE` | Ngày/giờ địa phương; không lưu tên vùng giờ. |
| PostgreSQL `TIMESTAMP WITH TIME ZONE` (`timestamptz`) | Lưu một thời điểm, giá trị hiển thị liên quan múi giờ phiên, không giữ nguyên tên vùng giờ đầu vào. |
| MySQL `DATETIME` | Thường lưu giá trị ngày/giờ địa phương. |
| MySQL `TIMESTAMP` | Có chuyển đổi theo múi giờ phiên; không đồng nhất với `TIMESTAMP` không múi giờ trên mọi DBMS. |
| SQL Server, Oracle và các driver khác | Kiểu cột và ánh xạ khác nhau; tra tài liệu đúng phiên bản driver đang triển khai. |

Khi gặp lỗi “chạy máy dev đúng nhưng server lệch giờ”, hãy kiểm tra kiểu cột, cách tạo `Timestamp`, múi giờ JVM, múi giờ phiên CSDL và cấu hình driver trước khi sửa code. Không cộng hoặc trừ cứng `7 giờ`: độ lệch UTC của một địa điểm có thể thay đổi theo thời gian.

## 6. Độ chính xác phần giây và các bẫy kế thừa

### `Timestamp` có nanosecond riêng

`java.sql.Timestamp` lưu phần giây lẻ tới nanosecond trong đối tượng Java:

```java
import java.sql.Timestamp;

Timestamp ts = Timestamp.valueOf("2026-11-17 09:15:30.123456789");
System.out.println(ts.getNanos()); // 123456789

ts.setNanos(987654321);
System.out.println(ts.toLocalDateTime().getNano()); // 987654321
```

`getTime()` trả mili giây theo epoch (bao gồm phần mili giây từ `getNanos()`), nên **không thể một mình giữ toàn bộ chín chữ số phần giây**. Độ chính xác thật khi lưu còn phụ thuộc độ chính xác của cột SQL, ví dụ `TIMESTAMP(3)` hoặc `TIMESTAMP(6)`, và cách làm tròn/cắt của DBMS. Giá trị Java có phần lẻ nanosecond không có nghĩa SQL sẽ bảo toàn nó.

### `Timestamp.equals` và mutable objects

```java
Timestamp first = Timestamp.valueOf("2026-11-17 09:15:30.123");
Timestamp second = Timestamp.valueOf("2026-11-17 09:15:30.123");
System.out.println(first.equals(second)); // true

second.setNanos(124000000);
System.out.println(first.equals(second)); // false
```

`Timestamp` kế thừa `java.util.Date` nhưng có quy tắc `equals` riêng; so sánh đối tượng `Timestamp` với `java.util.Date` có thể **không đối xứng**. Cả `java.sql.Date`, `Time`, `Timestamp` đều thuộc nhóm API mutable. Không dùng những đối tượng có thể thay đổi này làm khóa `Map` hoặc phần tử `Set` nếu sau đó còn chỉnh sửa chúng. Với mục đích so sánh rõ ràng, chuyển sang `Instant` (thời điểm) hoặc `LocalDateTime` (giờ địa phương) tùy ngữ nghĩa.

### `TIME` và thời lượng không giống nhau

`TIME '01:30:00'` là **giờ 01:30 trên đồng hồ**, không phải **thời lượng 90 phút**. Với nghiệp vụ tính thời lượng, dùng `Duration` trong Java và chọn cách lưu phù hợp như số giây hoặc số phút; không lưu duration trong cột `TIME` chỉ vì hình thức giống nhau.

## 7. Dữ liệu `NULL` và truy vấn theo khoảng

JDBC trả về `null` nếu cột `DATE`, `TIME` hoặc `TIMESTAMP` là SQL `NULL`:

```java
java.sql.Date dbBirthday = rs.getDate("birthday");
LocalDate birthday =
        dbBirthday == null ? null : dbBirthday.toLocalDate();

java.sql.Timestamp dbEvent = rs.getTimestamp("processed_at");
Instant processedAt =
        dbEvent == null ? null : dbEvent.toInstant();
```

Ở ví dụ thứ hai, cột `processed_at` phải được hệ thống định nghĩa rõ là **thời điểm tuyệt đối** với quy tắc chuyển đổi phù hợp; chỉ gọi `toInstant()` không đủ chứng minh dữ liệu đã được lưu đúng. Để ghi `NULL`, dùng:

```java
import java.sql.Types;

ps.setNull(1, Types.DATE);
ps.setNull(2, Types.TIME);
ps.setNull(3, Types.TIMESTAMP);
```

Không tự thay `NULL` bằng ngày `1970-01-01`, giờ `00:00:00` hay giá trị sentinel khác nếu nghiệp vụ không định nghĩa rõ. Sentinel khiến dữ liệu thật và dữ liệu thiếu khó phân biệt.

Khi lọc một ngày trên cột `TIMESTAMP` không múi giờ, nên dùng **khoảng nửa mở** `[đầu ngày, đầu ngày kế tiếp)`, tránh tự đoán “cuối ngày” ở độ chính xác 3, 6 hay 9 chữ số:

```java
LocalDate queryDay = LocalDate.of(2026, 11, 17);
LocalDateTime start = queryDay.atStartOfDay();
LocalDateTime end = queryDay.plusDays(1).atStartOfDay();

String sql = "SELECT id FROM legacy_schedule "
        + "WHERE appointment_local >= ? AND appointment_local < ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setTimestamp(1, Timestamp.valueOf(start));
    ps.setTimestamp(2, Timestamp.valueOf(end));
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("id"));
        }
    }
}
```

Đây là truy vấn trên **ngày/giờ địa phương**. Nếu dữ liệu lưu một thời điểm tuyệt đối nhưng cần báo cáo theo ngày tại một vùng giờ, phải quy đổi cả hai ranh giới ngày của vùng đó sang thời điểm tương ứng trước khi truy vấn; không mặc định ngày có 24 giờ ở vùng áp dụng DST.

## 8. Cải tiến mã cũ dần sang JDBC 4.2

Không cần thay toàn bộ ứng dụng một lần. Một lộ trình hợp lý:

1. **Kiểm kê ý nghĩa cột**: ngày, giờ, ngày-giờ địa phương hay thời điểm; xác nhận vùng giờ/độ chính xác theo schema và quy ước hiện tại.
2. **Đổi domain/DTO sang `java.time`**: giữ `LocalDate`, `LocalTime`, `LocalDateTime`, `Instant` là kiểu bất biến; đặt chuyển đổi `java.sql.*` trong DAO cũ.
3. **Chuyển từng truy vấn** từ `setDate`, `setTime`, `setTimestamp` sang `setObject`, từ getter cũ sang `getObject(column, Class<T>)` nếu driver hỗ trợ JDBC 4.2.
4. **Kiểm thử dữ liệu đã tồn tại**: đừng thay đổi diễn giải múi giờ cho hàng triệu bản ghi chỉ bằng việc đổi kiểu Java; migration kiểu cột/quy ước UTC cần được thiết kế riêng.
5. **Kiểm tra INSERT → SELECT** trên DBMS/driver triển khai, đặc biệt với múi giờ JVM khác nhau và phần giây lẻ.

| Cột | Cách cũ | Cách hiện đại khi driver hỗ trợ |
|---|---|---|
| Ghi `DATE` | `ps.setDate(1, Date.valueOf(day))` | `ps.setObject(1, day)` |
| Đọc `DATE` | `rs.getDate("day").toLocalDate()` (sau kiểm tra null) | `rs.getObject("day", LocalDate.class)` |
| Ghi `TIME` | `ps.setTime(1, Time.valueOf(clock))` | `ps.setObject(1, clock)` |
| Đọc `TIME` | `rs.getTime("clock").toLocalTime()` (sau kiểm tra null) | `rs.getObject("clock", LocalTime.class)` |
| Ghi `TIMESTAMP` không múi giờ | `ps.setTimestamp(1, Timestamp.valueOf(local))` | `ps.setObject(1, local)` |
| Đọc `TIMESTAMP` | `rs.getTimestamp("local").toLocalDateTime()` (sau kiểm tra null) | `rs.getObject("local", LocalDateTime.class)` |

Ví dụ trực tiếp với `java.time`:

```java
// JDBC 4.2+ khi driver hỗ trợ:
LocalDate day = LocalDate.of(2026, 11, 17);
LocalTime clock = LocalTime.of(8, 30);
LocalDateTime local = LocalDateTime.of(2026, 11, 17, 9, 15);

ps.setObject(1, day);
ps.setObject(2, clock);
ps.setObject(3, local);

LocalDate dayBack = rs.getObject("service_day", LocalDate.class);
LocalTime clockBack = rs.getObject("opening_time", LocalTime.class);
LocalDateTime localBack =
        rs.getObject("appointment_local", LocalDateTime.class);
```

Đây là các lệnh minh họa cách bind và đọc trên `PreparedStatement`/`ResultSet` đã được tạo đúng ngữ cảnh. Nếu cột cần lưu một **instant**, nhiều driver JDBC 4.2 có thể ánh xạ `TIMESTAMP WITH TIME ZONE` với `OffsetDateTime`:

```java
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

OffsetDateTime outgoing = Instant.now().atOffset(ZoneOffset.UTC);
ps.setObject(1, outgoing);

OffsetDateTime incoming =
        rs.getObject("occurred_at", OffsetDateTime.class);
Instant actual = incoming == null ? null : incoming.toInstant();
```

Không mặc định `TIMESTAMP WITH TIME ZONE` giữ nguyên *tên vùng giờ* hoặc offset đầu vào; nếu hệ thống cần biết lịch hẹn được đặt theo vùng giờ nào, lưu `ZoneId` (chuỗi như `Asia/Ho_Chi_Minh`) riêng.

## 9. Tình huống bảo trì: lịch hẹn lệch giờ sau khi chuyển máy chủ

Giả sử hệ thống lưu `2026-11-17 09:15:00` trong cột `TIMESTAMP` không múi giờ, nhưng code cũ làm:

```java
Timestamp dbValue = rs.getTimestamp("appointment_local");
Instant converted = dbValue.toInstant();
```

Trên một JVM dùng `Asia/Ho_Chi_Minh` và JVM khác dùng UTC, việc diễn giải các trường ngày giờ SQL thông qua `Timestamp` có thể tạo hai giá trị `Instant` khác nhau. Nếu ứng dụng tiếp tục chuyển `Instant` về múi giờ người dùng để hiển thị, lịch hẹn bị lệch.

Cách sửa phụ thuộc ngữ nghĩa:

- **“09:15 tại chi nhánh”**: giữ `LocalDateTime`; lưu mã vùng giờ của chi nhánh nếu cần tính `Instant` để gửi thông báo.
- **“Giao dịch xảy ra lúc nào?”**: dùng `Instant`; xác định kiểu cột, quy ước UTC hoặc cách dùng kiểu SQL có offset và kiểm tra driver.
- **“Ngày sinh / ngày hiệu lực?”**: dùng `LocalDate`; không ép thành `Timestamp` hoặc chuyển qua `Instant`.

Không có công thức cộng/trừ múi giờ cố định áp dụng đúng cho cả ba.

## 10. Bảng kiểm bảo trì và bài thực hành

| Câu hỏi cần trả lời | Lý do |
|---|---|
| Cột thực tế là `DATE`, `TIME`, `TIMESTAMP`, `DATETIME` hay loại có vùng giờ? | Tên gần giống nhau có thể mang ngữ nghĩa khác nhau. |
| Cột chứa thời điểm hay giờ địa phương? | Quyết định có nên gọi `toInstant()` hay `toLocalDateTime()`. |
| Có dùng overload `Calendar` không? | Múi giờ chuyển đổi có thể bị phụ thuộc môi trường. |
| Getter có thể trả `null` không? | Tránh `NullPointerException`, sentinel sai nghiệp vụ. |
| Cột lưu bao nhiêu chữ số phần giây? | Tránh mất micro/nanosecond và so sánh nhầm. |
| Có so sánh `Timestamp` với `java.util.Date`? | `equals` giữa hai lớp có đặc thù do kế thừa. |
| Có thử trên đúng bản driver, CSDL và cấu hình triển khai? | API giống nhau không bảo đảm hành vi ánh xạ giống nhau. |

Thực hành trên database thử nghiệm:

1. Tạo bảng có cột `birthday DATE`, `opening_time TIME`, `created_at TIMESTAMP`. Viết DAO ghi/đọc bằng ba cặp `setDate/getDate`, `setTime/getTime`, `setTimestamp/getTimestamp`.
2. Đưa kết quả đọc sang `LocalDate`, `LocalTime`, `LocalDateTime`, kiểm tra `null` và so sánh theo kiểu Java thay vì theo chuỗi.
3. Ghi `Timestamp.valueOf("2026-11-17 09:15:30.123456789")`, đọc lại và so sánh `getNanos()`; giải thích nếu DBMS chỉ giữ mili giây hoặc micro giây.
4. Với cột biểu diễn thời điểm theo quy ước UTC, thử overload có `Calendar` UTC ở cả ghi và đọc. Thực hiện với JVM ở hai múi giờ khác nhau để kiểm chứng quy ước.
5. Nếu driver hỗ trợ JDBC 4.2, thay từng cặp getter/setter bằng `getObject(..., Class<T>)`/`setObject(...)` và kiểm tra kết quả tương đương.

**Điều cần nhớ:** `java.sql.Date`, `Time` và `Timestamp` là các công cụ tương thích của JDBC, không phải mô hình ngày giờ lý tưởng cho nghiệp vụ. Hãy xác định ngữ nghĩa dữ liệu trước, giữ chuyển đổi trong tầng truy cập dữ liệu, truyền tham số bằng `PreparedStatement` và ưu tiên các kiểu bất biến của `java.time` khi có thể. Nhờ vậy, mã cũ vẫn hoạt động ổn định trong quá trình nâng cấp driver, schema và ứng dụng Java.

# Ánh xạ DATE, TIME và TIMESTAMP theo ngữ nghĩa dữ liệu

Khi làm việc với cơ sở dữ liệu quan hệ qua **JDBC**, chọn kiểu ngày giờ không chỉ là chọn cách hiển thị `dd/MM/yyyy` hay `HH:mm:ss`. Kiểu dữ liệu quyết định **thông tin nào được lưu**, thông tin nào bị mất và liệu hai hệ thống ở hai múi giờ có hiểu cùng một giá trị hay không. `PreparedStatement` và `ResultSet` giúp truyền, nhận các giá trị đã có kiểu; phần quan trọng nhất là chọn đúng cặp kiểu **SQL ↔ Java** theo ý nghĩa nghiệp vụ.

Trong bài này, ta phân biệt ba kiểu phổ biến `DATE`, `TIME`, `TIMESTAMP`, sử dụng API `java.time` với JDBC 4.2 trở lên và xem khi nào cần đến `TIMESTAMP WITH TIME ZONE` hoặc lưu thêm mã vùng giờ. Các ví dụ dùng `DataSource` để lấy kết nối, câu lệnh SQL tham số hóa và `try-with-resources` để đóng tài nguyên đúng cách.

## 1. Một giá trị ngày giờ có thể mang những ý nghĩa khác nhau

Hãy xét bốn thông tin:

- **Ngày sinh** của khách hàng: `2000-04-12`. Ta quan tâm ngày trên lịch, không cần giờ hay múi giờ.
- **Giờ mở cửa hằng ngày**: `08:30`. Ta quan tâm giờ trên đồng hồ, chưa xác định ngày cụ thể.
- **Lịch hẹn theo giờ địa phương**: `2026-12-24 09:15` tại Thành phố Hồ Chí Minh. Ta có ngày và giờ, nhưng cần biết vùng giờ của địa điểm để xác định thời điểm toàn cầu.
- **Thời điểm giao dịch xảy ra**: `2026-12-24T02:15:00Z`. Ta cần xác định một *thời điểm duy nhất* trên dòng thời gian, bất kể người xem ở đâu.

Không nên ép tất cả các tình huống trên vào `TIMESTAMP`. Làm vậy dễ khiến chương trình tự gán giờ `00:00:00`, phụ thuộc múi giờ mặc định của máy chủ hoặc diễn giải nhầm một giờ địa phương thành một thời điểm tuyệt đối.

| Ý nghĩa dữ liệu | Kiểu SQL phù hợp | Kiểu Java nên dùng | Có ngày? | Có giờ? | Tự xác định thời điểm tuyệt đối? |
|---|---|---|---|---|---|
| Ngày trên lịch, ví dụ ngày sinh | `DATE` | `LocalDate` | Có | Không | Không |
| Giờ trên đồng hồ, ví dụ giờ mở cửa | `TIME` (không múi giờ) | `LocalTime` | Không | Có | Không |
| Ngày + giờ địa phương, ví dụ lịch hẹn | `TIMESTAMP` (không múi giờ) | `LocalDateTime` | Có | Có | Không |
| Thời điểm có thông tin độ lệch UTC | `TIMESTAMP WITH TIME ZONE` nếu hệ CSDL hỗ trợ | `OffsetDateTime` | Có | Có | Có, sau khi quy đổi về `Instant` |

> **Quy tắc cốt lõi:** `LocalDateTime` **không** chứa múi giờ hay độ lệch UTC. Hai giá trị `2026-12-24T09:15` giống hệt nhau ở Hà Nội và Paris chỉ cùng *giờ trên đồng hồ*, không cùng *thời điểm*.

## 2. `DATE` ↔ `LocalDate`: chỉ có ngày trên lịch

`DATE` phù hợp với ngày sinh, ngày cấp chứng chỉ, ngày hết hạn theo lịch hoặc ngày bắt đầu áp dụng chính sách. Với JDBC 4.2 và driver có hỗ trợ, ánh xạ trực tiếp sang `java.time.LocalDate`:

```java
import java.time.LocalDate;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

LocalDate birthday = LocalDate.of(2000, 4, 12);

// Ghi vào cột DATE:
ps.setObject(1, birthday);

// Đọc từ cột DATE:
LocalDate savedBirthday = rs.getObject("birthday", LocalDate.class);
```

`LocalDate` không có giờ, độ lệch UTC hay `ZoneId`. Do đó, không có lý do nghiệp vụ để chuyển ngày sinh thành `Instant` hoặc cộng/trừ giờ khi người dùng thay đổi múi giờ. Nếu giao diện cần hiển thị `12/04/2000`, hãy định dạng **sau khi đọc**, chẳng hạn bằng `DateTimeFormatter`; định dạng hiển thị không quyết định kiểu cột hay cách bind tham số JDBC.

Trong SQL, ví dụ:

```sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    birthday DATE
);
```

Đừng dùng `TIMESTAMP` cho ngày sinh rồi lưu `00:00:00`: giá trị giả định đó có thể bị chuyển ngày khi một hệ thống khác diễn giải nó theo múi giờ riêng.

## 3. `TIME` ↔ `LocalTime`: giờ trong một ngày

`TIME` không có thông tin ngày, phù hợp với giờ mở cửa, giờ bắt đầu ca trực cố định hoặc mốc giờ lặp lại hằng ngày. JDBC 4.2 ánh xạ kiểu `TIME` không múi giờ với `LocalTime`:

```java
import java.time.LocalTime;

LocalTime openingTime = LocalTime.of(8, 30);
ps.setObject(1, openingTime); // Cột TIME

LocalTime savedOpeningTime = rs.getObject("opening_time", LocalTime.class);
```

`08:30` tự nó chưa nói được đó là `08:30` ở Việt Nam hay ở châu Âu. Nếu lịch mở cửa thuộc một chi nhánh cụ thể, vùng giờ thường nằm ở dữ liệu của **chi nhánh**, không nằm trong `LocalTime`.

Hai điểm dễ bỏ sót:

1. Khoảng giờ `22:00–02:00` **đi qua nửa đêm**. Chỉ so sánh `endTime.isAfter(startTime)` sẽ cho kết quả sai nếu nghiệp vụ cho phép ca làm qua ngày.
2. `TIME` biểu diễn *giờ trong ngày*, không phải độ dài. Một thời lượng `90 phút` nên dùng `Duration` trong Java và chọn cách lưu phù hợp như số giây/phút; không lưu nó như `TIME '01:30:00'`.

Một số CSDL có `TIME WITH TIME ZONE`, nhưng mức hỗ trợ và ý nghĩa giữa các hệ quản trị khác nhau. Đừng mặc định mọi cột `TIME` đều giữ hoặc tự áp dụng múi giờ.

## 4. `TIMESTAMP` ↔ `LocalDateTime`: ngày và giờ **không có múi giờ**

`TIMESTAMP` theo nghĩa SQL thông thường (*timestamp without time zone*) lưu ngày + giờ, ví dụ `2026-12-24 09:15:00`. Trong Java, kiểu tương ứng là `LocalDateTime`:

```java
import java.time.LocalDateTime;

LocalDateTime appointmentLocal =
        LocalDateTime.of(2026, 12, 24, 9, 15);

ps.setObject(1, appointmentLocal); // Cột TIMESTAMP không múi giờ

LocalDateTime savedLocal =
        rs.getObject("appointment_local", LocalDateTime.class);
```

Kiểu này phù hợp khi nghiệp vụ định nghĩa ngày giờ theo *đồng hồ tại một địa điểm*: lịch học lúc 09:15 tại văn phòng, giờ hẹn của cơ sở dịch vụ, giờ bắt đầu một chương trình truyền hình theo địa phương. Tuy nhiên, nếu cần đổi sang một `Instant`, phải biết vùng giờ của địa điểm đó và quy tắc xử lý thời gian chuyển mùa nếu có.

Chỉ có `LocalDateTime` thì không thể biết `2026-12-24 09:15` tương ứng UTC mấy giờ. `LocalDateTime.now()` cũng chỉ trả về giờ địa phương của môi trường đang chạy, không có thông tin vùng giờ được giữ lại trong đối tượng.

### Ví dụ JDBC hoàn chỉnh: lưu và đọc đúng ba kiểu

Giả sử hệ thống JDBC quản lý ngày phục vụ, giờ mở cửa và lịch hẹn tại một chi nhánh. Với SQL được CSDL hỗ trợ:

```sql
CREATE TABLE service_schedule (
    id BIGINT PRIMARY KEY,
    service_day DATE NOT NULL,
    opening_time TIME NOT NULL,
    appointment_local TIMESTAMP NOT NULL,
    zone_id VARCHAR(64) NOT NULL
);
```

`zone_id` giữ **mã vùng giờ IANA** của chi nhánh, ví dụ `Asia/Ho_Chi_Minh`. Đây là dữ liệu riêng, vì cột `TIMESTAMP` không tự chứa mã vùng giờ.

Đoạn Java sau giả định ứng dụng đã cấu hình `javax.sql.DataSource dataSource`. Việc sử dụng tham số `?` giúp JDBC bind giá trị theo kiểu, không phải tự ghép chuỗi hoặc tự định dạng ngày giờ để tạo SQL:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;

// dataSource do tầng cấu hình ứng dụng cung cấp.
LocalDate serviceDay = LocalDate.of(2026, 12, 24);
LocalTime openingTime = LocalTime.of(8, 30);
LocalDateTime appointmentLocal =
        LocalDateTime.of(2026, 12, 24, 9, 15);
String zoneId = "Asia/Ho_Chi_Minh";

String insertSql = "INSERT INTO service_schedule "
        + "(id, service_day, opening_time, appointment_local, zone_id) "
        + "VALUES (?, ?, ?, ?, ?)";

try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(insertSql)) {
    ps.setLong(1, 1001L);
    ps.setObject(2, serviceDay);       // DATE -> LocalDate
    ps.setObject(3, openingTime);      // TIME -> LocalTime
    ps.setObject(4, appointmentLocal); // TIMESTAMP -> LocalDateTime
    ps.setString(5, zoneId);          // Vùng giờ lưu riêng
    ps.executeUpdate();
}

String selectSql = "SELECT service_day, opening_time, "
        + "appointment_local, zone_id FROM service_schedule WHERE id = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(selectSql)) {
    ps.setLong(1, 1001L);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            LocalDate day = rs.getObject("service_day", LocalDate.class);
            LocalTime opens = rs.getObject("opening_time", LocalTime.class);
            LocalDateTime local =
                    rs.getObject("appointment_local", LocalDateTime.class);
            ZoneId zone = ZoneId.of(rs.getString("zone_id"));

            System.out.println("Ngày phục vụ: " + day);
            System.out.println("Mở cửa: " + opens);
            System.out.println("Lịch hẹn: " + local + " tại " + zone);
        }
    }
}
```

Với JDBC, truy vấn và thời điểm commit là vấn đề riêng. Nếu ghi nhiều bảng cần thành công hoặc thất bại cùng nhau, dùng transaction qua `Connection`; việc chọn đúng kiểu ngày giờ không thay thế quản lý transaction.

## 5. Khi dữ liệu biểu diễn một *thời điểm*, dùng gì?

Một sự kiện như "thanh toán được xác nhận" cần được sắp xếp và so sánh trên cùng một dòng thời gian. Trong Java, `Instant` thể hiện chính xác nhu cầu này. Khi CSDL và driver hỗ trợ `TIMESTAMP WITH TIME ZONE`, JDBC 4.2 chuẩn hóa ánh xạ với `OffsetDateTime`:

```sql
-- Cú pháp và cách lưu thực tế cần kiểm tra theo hệ quản trị CSDL.
CREATE TABLE audit_event (
    id BIGINT PRIMARY KEY,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL
);
```

```java
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

Instant occurredAt = Instant.now();
OffsetDateTime utcValue = occurredAt.atOffset(ZoneOffset.UTC);

// PreparedStatement của câu INSERT, cột đích là TIMESTAMP WITH TIME ZONE:
ps.setObject(1, utcValue);

// ResultSet của câu SELECT:
OffsetDateTime dbValue =
        rs.getObject("occurred_at", OffsetDateTime.class);
Instant sameInstant = dbValue.toInstant();
```

`OffsetDateTime` chứa độ lệch với UTC (ví dụ `+07:00`), đủ để suy ra một `Instant`. Nhưng **độ lệch UTC không phải vùng giờ**: `+07:00` không mang toàn bộ quy tắc lịch sử hoặc chuyển giờ của `Asia/Ho_Chi_Minh`. Nhiều CSDL chỉ lưu một thời điểm đã chuẩn hóa và có thể trả về độ lệch khác độ lệch ban đầu; đừng giả định cột `TIMESTAMP WITH TIME ZONE` giữ nguyên offset hoặc tên vùng giờ mà người dùng nhập.

Nếu nghiệp vụ cần biết *người dùng đã chọn vùng giờ nào*, lưu thêm cột `zone_id` như `Europe/Paris` hay `Asia/Ho_Chi_Minh`. Với lịch hẹn tương lai, thường cần lưu cả `LocalDateTime` dự kiến và `ZoneId` để quy tắc giờ địa phương vẫn rõ ràng. Khi cần phát thông báo hoặc thực thi tại một thời điểm cụ thể, ứng dụng giải quyết cặp này thành `Instant` theo chính sách nghiệp vụ.

### Chuyển giờ địa phương thành thời điểm thực tế

Trong vùng có đổi giờ mùa hè (DST), cùng một `LocalDateTime` có thể không tồn tại hoặc xảy ra hai lần. Có thể kiểm tra trước khi quy đổi:

```java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;

LocalDateTime chosenLocal = LocalDateTime.of(2026, 10, 25, 2, 30);
ZoneId branchZone = ZoneId.of("Europe/Paris");
List<ZoneOffset> validOffsets =
        branchZone.getRules().getValidOffsets(chosenLocal);

if (validOffsets.isEmpty()) {
    throw new IllegalArgumentException("Giờ địa phương không tồn tại do DST");
}
if (validOffsets.size() > 1) {
    throw new IllegalArgumentException("Giờ địa phương bị lặp: phải chọn offset");
}

Instant appointmentInstant =
        chosenLocal.atOffset(validOffsets.get(0)).toInstant();
```

Quy tắc kiểm tra này cố ý từ chối các giờ không rõ ràng. Ứng dụng thực tế có thể cho người dùng chọn một trong hai độ lệch khi giờ bị lặp, hoặc đề xuất giờ khác khi giờ không tồn tại. `LocalDateTime.atZone(zone)` có quy tắc tự giải quyết trường hợp DST; chỉ nên dùng mặc định đó nếu chính sách nghiệp vụ chấp nhận.

## 6. Hỗ trợ của từng CSDL và driver JDBC

Tên cột giống nhau không đảm bảo các hệ quản trị có cùng hành vi:

| Hệ quản trị / loại cột | Điểm cần lưu ý |
|---|---|
| PostgreSQL `DATE`, `TIME`, `TIMESTAMP WITHOUT TIME ZONE` | Phân biệt rõ ngày, giờ và ngày-giờ địa phương; bộ kiểu `LocalDate`, `LocalTime`, `LocalDateTime` tương ứng về ngữ nghĩa. |
| PostgreSQL `TIMESTAMP WITH TIME ZONE` (`timestamptz`) | Lưu một thời điểm, không giữ nguyên tên múi giờ đã nhập; hiển thị giá trị chịu ảnh hưởng của thiết lập múi giờ phiên. |
| MySQL `DATETIME` | Lưu giá trị ngày-giờ địa phương, thường phù hợp với ngữ nghĩa `LocalDateTime` hơn `Instant`. |
| MySQL `TIMESTAMP` | Có cơ chế chuyển đổi dựa trên múi giờ phiên khi ghi/đọc; không nên mặc định xem như `TIMESTAMP` không múi giờ của mọi hệ quản trị. |
| Các driver JDBC khác | Không phải driver nào cũng hỗ trợ đầy đủ `setObject(java.time...)` và `getObject(..., Class<T>)`, hoặc cùng độ chính xác phần giây. |

Các ví dụ SQL trong bài minh họa kiểu chuẩn và không bảo đảm chạy nguyên xi trên mọi hệ CSDL. Khi chọn driver, hãy kiểm tra phiên bản JDBC, kiểu SQL cụ thể, vùng giờ phiên và hành vi chuyển đổi được tài liệu của hệ quản trị xác nhận. Đặc biệt cần xác minh nếu dùng kiểu có chữ `TIMESTAMP` vì tên này có thể đại diện hai ngữ nghĩa khác nhau giữa các hệ.

## 7. API cũ `java.sql.Date`, `Time`, `Timestamp` và các vấn đề dễ gặp

Trước JDBC 4.2, chương trình thường sử dụng các lớp `java.sql.*`:

| Cột SQL | Kiểu cũ | Cách chuyển đổi rõ ràng với `java.time` |
|---|---|---|
| `DATE` | `java.sql.Date` | `Date.valueOf(localDate)`; `sqlDate.toLocalDate()` |
| `TIME` | `java.sql.Time` | `Time.valueOf(localTime)`; `sqlTime.toLocalTime()` |
| `TIMESTAMP` | `java.sql.Timestamp` | `Timestamp.valueOf(localDateTime)`; `sqlTimestamp.toLocalDateTime()` |

Ví dụ với driver chưa hỗ trợ ánh xạ `LocalDate` trực tiếp:

```java
LocalDate date = LocalDate.of(2026, 12, 24);
ps.setDate(1, java.sql.Date.valueOf(date));

java.sql.Date fromDb = rs.getDate("service_day");
LocalDate restored = (fromDb == null) ? null : fromDb.toLocalDate();
```

Các API cũ có di sản biểu diễn dựa trên mili giây và có thể liên quan đến múi giờ mặc định hoặc cách driver chuyển đổi. `java.sql.Time` còn không phải lựa chọn phù hợp nếu cần bảo toàn phần giây lẻ độ chính xác cao. Vì vậy, với driver hỗ trợ chuẩn JDBC 4.2, nên bind/đọc bằng `java.time` và kiểm tra thực tế khả năng *round-trip* của CSDL.

Khi gặp API `setTimestamp(..., Calendar)` hay `getTimestamp(..., Calendar)`, hãy hiểu rằng `Calendar` chỉ cung cấp ngữ cảnh múi giờ cho một số phép chuyển đổi cũ; nó **không biến** một cột `TIMESTAMP` không múi giờ thành kiểu dữ liệu chứa `ZoneId`.

### Giá trị `NULL`

`ResultSet.getObject("service_day", LocalDate.class)` trả về `null` nếu ô SQL là `NULL`. Khi bind một giá trị null có kiểu xác định, có thể dùng:

```java
import java.sql.Types;

ps.setNull(1, Types.DATE);
ps.setNull(2, Types.TIME);
ps.setNull(3, Types.TIMESTAMP);
```

Các cột `NOT NULL` trong ví dụ `service_schedule` đòi hỏi giá trị không null. Việc kiểm soát `NULL` là quyết định của schema và nghiệp vụ; đừng tự thay bằng ngày `1970-01-01` hoặc giờ `00:00` nếu chúng không thực sự có nghĩa.

## 8. Độ chính xác, truy vấn và tính nhất quán

`LocalTime` và `LocalDateTime` có thể chứa nanosecond, nhưng cột SQL và driver có thể chỉ giữ đến độ chính xác giây hoặc một số chữ số thập phân. Ví dụ một giá trị có đuôi `.123456789` có thể bị làm tròn hoặc cắt khi đi qua cột `TIMESTAMP(3)` chỉ lưu mili giây. Cú pháp xác định độ chính xác như `TIME(p)` và `TIMESTAMP(p)` còn phụ thuộc hệ quản trị.

Khi lọc theo khoảng thời gian, ưu tiên khoảng **nửa mở** `[start, end)` để tránh phải tự dựng thời điểm cuối ngày với phần giây tối đa:

```java
LocalDate day = LocalDate.of(2026, 12, 24);
LocalDateTime start = day.atStartOfDay();
LocalDateTime end = day.plusDays(1).atStartOfDay();

String sql = "SELECT id FROM service_schedule "
        + "WHERE appointment_local >= ? AND appointment_local < ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setObject(1, start);
    ps.setObject(2, end);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("id"));
        }
    }
}
```

Đoạn truy vấn này lọc theo **ngày địa phương được lưu trong cột `appointment_local`**. Nếu cột chứa *thời điểm tuyệt đối*, phải xác định ngày theo vùng giờ cần báo cáo, rồi chuyển **cả hai ranh giới ngày** thành các `Instant` tương ứng trước khi truy vấn; không mặc định mỗi ngày tại mọi vùng giờ đều có đúng 24 giờ vì DST.

Khi cần tái hiện lỗi chênh ngày hoặc lệch giờ, hãy kiểm tra đồng thời: `ZoneId.systemDefault()` của JVM, múi giờ phiên kết nối CSDL, kiểu cột thực tế, phiên bản driver và quy tắc chuyển đổi được driver áp dụng. Không nên sửa bằng cách cộng cố định `7 giờ` trong ứng dụng: một độ lệch UTC không thay thế được `ZoneId`, đặc biệt ở vùng có lịch sử đổi giờ.

## 9. Lỗi phổ biến và cách tránh

| Cách làm có vấn đề | Vì sao sai hoặc rủi ro | Cách xử lý |
|---|---|---|
| Lưu ngày sinh vào `TIMESTAMP` | Tạo giờ giả, dễ chuyển ngày nếu bị hiểu theo vùng giờ khác. | `DATE` ↔ `LocalDate`. |
| Dùng `TIME` để lưu thời lượng | Giờ trên đồng hồ khác độ dài thời gian. | `Duration` ở Java; lưu số giây/phút hoặc kiểu duration được hỗ trợ. |
| Xem `LocalDateTime` là thời điểm UTC | Không có offset hay vùng giờ, không xác định được `Instant`. | Lưu thêm `ZoneId` cho giờ địa phương, hoặc dùng kiểu lưu thời điểm. |
| Dùng `TIMESTAMP WITH TIME ZONE` và trông chờ giữ tên vùng `Asia/Ho_Chi_Minh` | Kiểu này có thể chỉ lưu thời điểm đã chuẩn hóa. | Cần tên vùng thì lưu `zone_id` riêng. |
| Nối chuỗi SQL như `... VALUES ('" + date + "')` | Phụ thuộc định dạng literal, dễ lỗi và không dùng được bind tham số an toàn. | `PreparedStatement#setObject(...)`. |
| Đổi ngày giờ sang `String` rồi parse lại tại mỗi tầng | Dễ phụ thuộc locale/định dạng và vô tình mất phần giây. | Giữ `LocalDate`, `LocalTime`, `LocalDateTime` hoặc `OffsetDateTime` xuyên qua tầng truy cập dữ liệu. |
| Giả định tất cả driver có cùng hành vi `TIMESTAMP` | CSDL có quy tắc múi giờ và precision khác nhau. | Test với đúng driver, schema, cấu hình phiên trong môi trường triển khai. |

## 10. Thực hành kiểm chứng với JDBC

Khi xây dựng repository/DAO, hãy kiểm tra thực tế một chu trình **ghi → đọc → so sánh** trên đúng CSDL sẽ dùng. Nên chọn dữ liệu thử phản ánh ý nghĩa nghiệp vụ thay vì chỉ thử `now()`:

1. **`DATE`:** ngày thường và ngày nhuận như `2024-02-29`; đọc lại bằng `LocalDate` phải giữ nguyên ngày, kể cả khi môi trường ứng dụng chạy ở múi giờ khác.
2. **`TIME`:** giờ `00:00`, `23:59:59` và giờ có phần giây lẻ nếu schema hỗ trợ; xác định rõ precision mong đợi.
3. **`TIMESTAMP`:** `2026-12-24T09:15` phải được đọc lại đúng giờ địa phương đã lưu, không tự trừ/cộng độ lệch UTC.
4. **Thời điểm tuyệt đối:** cùng `Instant` ghi với những offset khác nhau, nếu hệ CSDL lưu *instant* thì so sánh theo `toInstant()` thay vì so sánh chuỗi hoặc mong offset nguyên bản.
5. **DST:** với chi nhánh dùng vùng giờ có thay đổi giờ mùa hè, thử một giờ bị lặp và một giờ không tồn tại, rồi kiểm tra ứng dụng xử lý đúng chính sách.
6. **`NULL` và phần giây:** xác nhận quy tắc xử lý thiếu dữ liệu, làm tròn và cắt precision của driver/schema.

Khi cần kiểm tra một lớp chuyển đổi cụ thể, có thể phát biểu tiêu chí bằng Java:

```java
LocalDate expectedDate = LocalDate.of(2024, 2, 29);
// Sau khi INSERT rồi SELECT qua đúng JDBC driver:
LocalDate actualDate = rs.getObject("service_day", LocalDate.class);
if (!expectedDate.equals(actualDate)) {
    throw new AssertionError("DATE không round-trip đúng");
}
```

Đây là mảnh kiểm chứng đặt bên trong một `ResultSet` đã được mở và trỏ đến bản ghi thử; nó không thay cho một bài test tích hợp đầy đủ.

## 11. Chọn kiểu trước khi viết SQL

Đặt câu hỏi **"Giá trị này là ngày, giờ trên đồng hồ, lịch hẹn địa phương hay một thời điểm tuyệt đối?"** trước khi chọn kiểu cột:

```text
Chỉ là ngày trên lịch?             -> DATE                  -> LocalDate
Chỉ là giờ trong một ngày?         -> TIME                  -> LocalTime
Ngày + giờ theo đồng hồ địa phương?-> TIMESTAMP             -> LocalDateTime
    Cần biết địa điểm/múi giờ?     -> Lưu thêm zone_id       -> ZoneId
Một thời điểm duy nhất?            -> Kiểu SQL lưu instant  -> OffsetDateTime / Instant
    Có TIMESTAMP WITH TIME ZONE?   -> Dùng sau khi xác minh hành vi driver
```

Trong JDBC, `setObject()` và `getObject(..., Class<T>)` giúp giữ ý nghĩa của kiểu `java.time` rõ ràng; `PreparedStatement` xử lý giá trị tham số và `ResultSet` trả dữ liệu đã có kiểu. Sự đúng đắn cuối cùng vẫn phụ thuộc vào **schema**, **hành vi của CSDL/driver** và **quy tắc múi giờ của nghiệp vụ**. Khi ba yếu tố này nhất quán, ứng dụng Java có thể xử lý ngày giờ mà không cần quy đổi hoặc định dạng tùy tiện trong tầng truy cập dữ liệu.

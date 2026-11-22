# Ảnh hưởng của múi giờ JVM, phiên kết nối và máy chủ trong JDBC

Một ứng dụng Java kết nối cơ sở dữ liệu quan hệ qua JDBC có thể chạy ổn trên máy phát triển nhưng lệch vài giờ khi triển khai lên server hoặc container khác. Ngay cả khi ứng dụng và database cùng lưu một thời điểm, công cụ quản trị SQL và chương trình Java có thể hiển thị hai giá trị khác nhau. Muốn xử lý đúng cần phân biệt **múi giờ mặc định của JVM**, **múi giờ của phiên kết nối database** và **múi giờ/cấu hình của máy chủ cơ sở dữ liệu**.

Bài này thuộc phần *Ngày giờ và múi giờ* của JDBC, áp dụng trực tiếp cho thao tác `PreparedStatement`, `ResultSet`, `DataSource`, quản lý kết nối và truy vấn SQL. Các ví dụ SQL chính dùng **PostgreSQL** để thấy rõ ba lớp cấu hình; phần riêng nêu khác biệt quan trọng của **MySQL**. Với DBMS và JDBC driver khác, cần kiểm tra tài liệu và phép thử thực tế trước khi áp dụng nguyên xi.

## 1. Ba lớp múi giờ không đồng nghĩa

| Lớp | Nằm ở đâu? | Có thể chi phối điều gì? | Cách kiểm tra điển hình |
|---|---|---|---|
| **Múi giờ mặc định của JVM** | Tiến trình Java chạy ứng dụng | `ZoneId.systemDefault()`, `LocalDateTime.now()`, `LocalDate.now()`; có thể ảnh hưởng ánh xạ ngày giờ của JDBC API cũ tùy driver | `ZoneId.systemDefault()`, `TimeZone.getDefault()` |
| **Múi giờ phiên kết nối DB** | Kết nối vật lý/SQL session do JDBC driver mở | Cách DB diễn giải chuỗi/ngày giờ thiếu offset khi ép sang kiểu có múi giờ; cách hiển thị một số kết quả truy vấn và tính ngày hiện tại | PostgreSQL: `SHOW TIME ZONE` hoặc `current_setting('TimeZone')` |
| **Múi giờ mặc định của DB server** | Cấu hình hệ quản trị database, có thể kế thừa cấu hình hệ điều hành | Giá trị mặc định cho phiên mới và một số phép tính/chuyển đổi do DB thực hiện; tùy hệ quản trị | Xem cấu hình DB, giá trị mặc định và cấu hình phiên thực tế |

**Múi giờ máy chủ** còn dễ bị hiểu thành **đồng hồ máy chủ**. Đây là hai thứ khác nhau:

- *Múi giờ* quyết định cách biểu diễn giờ địa phương và áp dụng quy tắc DST (giờ mùa hè) ở vùng có sử dụng.
- *Đồng hồ hệ thống* xác định thời gian thực mà máy đang cho là hiện tại. Nếu đồng hồ ứng dụng và DB không đồng bộ, `Instant.now()` ở JVM và hàm thời gian hiện tại của DB có thể chênh lệch ngay cả khi cả hai dùng UTC.

Cần tránh suy luận “server chạy UTC thì mọi timestamp trong database đều là UTC”. Ý nghĩa của cột, kiểu dữ liệu và phép chuyển đổi vẫn quyết định kết quả.

### Cùng một ứng dụng, ba lớp có thể khác nhau

Giả sử:

- JVM chạy với `user.timezone=Asia/Ho_Chi_Minh`.
- Một JDBC connection đang có phiên PostgreSQL `TimeZone=UTC`.
- Database server được cấu hình mặc định `TimeZone=Europe/Paris`.

Ba cấu hình này có thể cùng tồn tại. Một lệnh `SET TIME ZONE` chỉ đổi phiên kết nối hiện tại; nó không đổi múi giờ JVM và không sửa cấu hình mặc định của server. Ngược lại, đổi `-Duser.timezone` không đảm bảo đổi múi giờ phiên database: driver, thiết lập đăng nhập và lệnh SQL có thể đặt phiên theo giá trị khác.

## 2. Phân biệt “thời điểm tuyệt đối” và “ngày giờ địa phương”

Ba lớp cấu hình chỉ trở nên rõ khi đặt câu hỏi: trường dữ liệu đang lưu **một thời điểm duy nhất** hay **con số trên lịch/đồng hồ tại một vùng**?

- `Instant` là một thời điểm tuyệt đối trên dòng thời gian, không lưu tên múi giờ địa lý; `2026-07-01T02:00:00Z` ở UTC chính là 09:00 tại Việt Nam.
- `LocalDateTime` là ngày và giờ không mang offset/múi giờ; `2026-07-01T09:00` **chưa xác định** thời điểm tuyệt đối.
- `OffsetDateTime` gồm ngày giờ và offset, xác định được một thời điểm; thường dùng để trao đổi với `TIMESTAMP WITH TIME ZONE` qua JDBC 4.2.
- `ZonedDateTime` gồm ngày giờ và `ZoneId` cùng quy tắc múi giờ của vùng; hữu ích cho lịch hẹn tương lai, đặc biệt ở vùng có DST.

Ngữ nghĩa của kiểu cột SQL cũng quan trọng:

| PostgreSQL | Ý nghĩa | Phản ứng điển hình khi đổi múi giờ phiên |
|---|---|---|
| `DATE` | Một ngày theo lịch | Giá trị thuần ngày vẫn là ngày đó; các phép chuyển đổi từ một thời điểm sang ngày có thể phụ thuộc phiên |
| `TIME WITHOUT TIME ZONE` | Một giờ địa phương | Giá trị thuần giờ không tự dịch sang giờ khác |
| `TIMESTAMP WITHOUT TIME ZONE` (viết tắt `TIMESTAMP`) | Ngày giờ địa phương, **không** có offset | Giá trị trường giữ nguyên khi chỉ đổi múi giờ phiên |
| `TIMESTAMP WITH TIME ZONE` (PostgreSQL: `TIMESTAMPTZ`) | Một thời điểm tuyệt đối; DB không giữ nguyên tên vùng đầu vào | Cùng một thời điểm có thể hiển thị với giờ địa phương/offset khác khi đổi phiên |

PostgreSQL lưu `TIMESTAMPTZ` theo thời điểm đã chuẩn hóa; **không lưu nguyên tên vùng hoặc nhất thiết giữ nguyên offset đã nhập**. Nếu cần nhớ cuộc hẹn diễn ra tại `Europe/Paris`, hãy lưu thêm mã `ZoneId`. Không nên suy rộng cách hiện thực này cho tất cả sản phẩm SQL chỉ vì chúng cùng có cụm `WITH TIME ZONE`.

## 3. Múi giờ mặc định của JVM ảnh hưởng Java như thế nào?

Java có thể lấy múi giờ mặc định của tiến trình:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class JvmZoneDemo {
    public static void main(String[] args) {
        System.out.println(ZoneId.systemDefault());
        System.out.println(LocalDate.now());
        System.out.println(LocalDateTime.now());

        Instant instant = Instant.parse("2026-07-01T02:00:00Z");
        ZonedDateTime display = instant.atZone(ZoneId.systemDefault());

        System.out.println(instant);
        System.out.println(display);
    }
}
```

Có thể khởi động hai tiến trình Java với hai cấu hình khác nhau:

```bash
java -Duser.timezone=UTC JvmZoneDemo
java -Duser.timezone=Asia/Ho_Chi_Minh JvmZoneDemo
```

Với cùng `Instant.parse("2026-07-01T02:00:00Z")`, giá trị `instant` không đổi; phần `display` lần lượt là khoảng 02:00 UTC và 09:00 tại Việt Nam. Các lời gọi `now()` phụ thuộc thời điểm thực chạy, nên không nên so sánh chuỗi đầu ra của hai tiến trình rồi kết luận đồng hồ bị lệch.

Đặc biệt:

- `Instant.now()` lấy thời điểm hiện tại từ đồng hồ hệ thống; **múi giờ mặc định không làm dịch thời điểm đó**.
- `LocalDateTime.now()` và `LocalDate.now()` dùng múi giờ mặc định để biểu diễn ngày/giờ tại thời điểm gọi.
- `LocalDateTime.ofInstant(instant, zone)` cần `zone` tường minh; đây là lựa chọn an toàn khi nghiệp vụ biết vùng.
- `ZoneId.systemDefault()` không nên dùng để suy đoán vùng của người dùng, cửa hàng hoặc lịch hẹn chỉ vì ứng dụng đang chạy trên một máy cụ thể.

### Tại sao API JDBC cũ dễ gây hiểu nhầm?

`java.sql.Timestamp` chứa thông tin thời điểm dưới dạng cấu trúc kế thừa từ `java.util.Date`, nhưng kiểu SQL `TIMESTAMP WITHOUT TIME ZONE` lại là ngày giờ không có offset. Khi dùng `PreparedStatement.setTimestamp(...)` hoặc `ResultSet.getTimestamp(...)`, driver có thể phải chuyển giữa hai ngữ nghĩa này bằng một múi giờ mặc định hoặc `Calendar` truyền vào. Tùy driver, cột, phiên kết nối và cách gọi API, thay đổi múi giờ JVM có thể làm thay đổi giá trị diễn giải hoặc phần giờ hiển thị.

Với JDBC 4.2, ưu tiên ánh xạ có chủ đích:

```java
// Cột TIMESTAMP WITHOUT TIME ZONE
ps.setObject(1, localDateTime);
LocalDateTime local = rs.getObject("local_time", LocalDateTime.class);

// Cột TIMESTAMP WITH TIME ZONE trên driver hỗ trợ
ps.setObject(2, instant.atOffset(java.time.ZoneOffset.UTC));
java.time.OffsetDateTime offsetTime =
        rs.getObject("event_time", java.time.OffsetDateTime.class);
Instant restored = offsetTime.toInstant();
```

Đây là các đoạn minh họa *bên trong* phương thức đang có `PreparedStatement ps` và `ResultSet rs` phù hợp, không phải chương trình độc lập. Ánh xạ `OffsetDateTime` tới kiểu SQL có múi giờ cần kiểm tra với driver/DB cụ thể; JDBC không bảo đảm mọi driver trực tiếp nhận `Instant` qua `setObject`.

## 4. Phiên kết nối PostgreSQL quyết định việc diễn giải và hiển thị

Phần này có thể chạy trong công cụ SQL kết nối PostgreSQL để quan sát kết quả. Ta ghi đồng thời:

1. Một thời điểm thực tế: **09:00 ngày 01/07/2026 ở Việt Nam = 02:00 UTC**.
2. Một ngày giờ địa phương thuần túy: **09:00 ngày 01/07/2026**, chưa có vùng.

```sql
CREATE TEMP TABLE tz_demo (
    id            INTEGER PRIMARY KEY,
    occurred_at   TIMESTAMPTZ NOT NULL,
    scheduled_at  TIMESTAMP WITHOUT TIME ZONE NOT NULL
);

SET TIME ZONE 'UTC';

INSERT INTO tz_demo (id, occurred_at, scheduled_at)
VALUES (
    1,
    TIMESTAMPTZ '2026-07-01 09:00:00+07:00',
    TIMESTAMP '2026-07-01 09:00:00'
);

SHOW TIME ZONE;

SELECT occurred_at, scheduled_at FROM tz_demo WHERE id = 1;
-- occurred_at: 2026-07-01 02:00:00+00
-- scheduled_at: 2026-07-01 09:00:00

SET TIME ZONE 'Asia/Ho_Chi_Minh';

SHOW TIME ZONE;

SELECT occurred_at, scheduled_at FROM tz_demo WHERE id = 1;
-- occurred_at: 2026-07-01 09:00:00+07
-- scheduled_at: 2026-07-01 09:00:00
```

**Giá trị `occurred_at` là cùng một thời điểm ở cả hai lần truy vấn.** PostgreSQL chỉ đổi cách biểu diễn giờ và offset khi kết xuất `TIMESTAMPTZ`. `scheduled_at` không đổi vì kiểu `TIMESTAMP WITHOUT TIME ZONE` không chứa thông tin để tự đổi sang vùng khác.

### Nguy cơ khi gửi giá trị thiếu offset vào cột `TIMESTAMPTZ`

Thử trên chính phiên đó:

```sql
SET TIME ZONE 'UTC';

SELECT '2026-07-01 09:00:00'::timestamptz;
-- Tương ứng 2026-07-01T09:00:00Z

SET TIME ZONE 'Asia/Ho_Chi_Minh';

SELECT '2026-07-01 09:00:00'::timestamptz;
-- Tương ứng 2026-07-01T02:00:00Z
```

Vẫn cùng chuỗi đầu vào, nhưng **hai thời điểm tuyệt đối khác nhau đến bảy giờ**: vì thiếu offset, database phải diễn giải ngày giờ trong múi giờ phiên.

Ngay cả cách ghi literal cũng quan trọng:

```sql
-- Có offset và nêu rõ kiểu thời điểm:
SELECT TIMESTAMPTZ '2026-07-01 09:00:00+07:00';

-- Kiểu không có múi giờ: PostgreSQL bỏ qua thông tin offset này
SELECT TIMESTAMP '2026-07-01 09:00:00+07:00';
```

Không nên dùng chuỗi không offset cho một sự kiện tuyệt đối rồi trông chờ phiên SQL tự đoán đúng. Dùng `OffsetDateTime`/`Instant` được chuyển đổi tường minh và tham số hóa qua `PreparedStatement` để tránh lỗi và tránh nối chuỗi SQL.

### Vì sao `CURRENT_DATE` có thể khác `LocalDate.now()`?

Giả sử cùng một thời điểm thực là 00:30 ngày 01/01/2027 tại Việt Nam, tương ứng 17:30 ngày 31/12/2026 UTC:

- JVM dùng `Asia/Ho_Chi_Minh`: `LocalDate.now()` là ngày 01/01/2027.
- Phiên PostgreSQL dùng `UTC`: `CURRENT_DATE` là ngày 31/12/2026.

Cả hai đều hợp lý theo **múi giờ đang dùng**. Vì vậy nên quy định rõ nguồn tạo “ngày hôm nay”: ngày theo vùng nghiệp vụ, theo phiên DB hay theo UTC.

Với PostgreSQL, `CURRENT_TIMESTAMP` trả về thời điểm bắt đầu transaction theo kiểu `TIMESTAMPTZ`; còn `clock_timestamp()` trả thời điểm thực tại lúc gọi. Hai hàm có thể khác nhau trong transaction dài **dù không có lỗi múi giờ**. Không nên quy chênh lệch giữa chúng cho cấu hình zone.

## 5. Múi giờ máy chủ: mặc định, phiên và đồng hồ

Múi giờ **mặc định** của DB server có thể đóng vai trò khởi tạo cấu hình cho các phiên, nhưng phiên thực tế có thể nhận giá trị khác từ cấu hình database, role/user, tham số kết nối, driver hoặc lệnh SQL sau khi đăng nhập. Vì vậy, nếu đang sửa lỗi lệch giờ, hãy đo **giá trị của đúng connection đang truy vấn**:

```sql
-- PostgreSQL
SHOW TIME ZONE;

SELECT current_setting('TimeZone') AS session_zone,
       CURRENT_TIMESTAMP           AS transaction_time,
       clock_timestamp()           AS wall_clock_time;
```

Một máy chủ database chạy trong container có timezone hệ điều hành là UTC cũng **không** chứng minh mọi phiên PostgreSQL là UTC. Tương tự, đổi `TimeZone` của một phiên không đổi đồng hồ hệ thống và không đổi toàn bộ phiên khác.

Khi cần dùng timestamp do database tự sinh, phân biệt:

- `DEFAULT CURRENT_TIMESTAMP` trên cột có múi giờ của PostgreSQL biểu thị thời điểm transaction theo đồng hồ phía DB; khi đọc giá trị hiển thị sẽ theo múi giờ phiên.
- `DEFAULT CURRENT_TIMESTAMP` trên cột `TIMESTAMP WITHOUT TIME ZONE` có thể khiến PostgreSQL chuyển thời điểm sang *giờ địa phương của phiên* rồi bỏ offset khi ép sang cột. Ý nghĩa và cách diễn giải cột về sau phụ thuộc quy ước ứng dụng.
- `Instant.now()` từ JVM lấy đồng hồ phía ứng dụng; chênh lệch với giá trị DB có thể do thời điểm lấy mẫu, transaction bắt đầu trước đó hoặc đồng hồ các máy lệch nhau.

Nếu ứng dụng cần audit đồng nhất, hãy quyết định **nguồn thời gian chuẩn** (ứng dụng hay DB), dùng kiểu cột phản ánh được thời điểm và duy trì đồng bộ đồng hồ qua hạ tầng. Việc chọn UTC làm múi giờ hiển thị không thể tự khắc phục đồng hồ sai.

## 6. JDBC thực tế: tách dữ liệu thời điểm khỏi lịch địa phương

Ví dụ PostgreSQL sau lưu dấu thời gian phát sinh sự kiện và lịch hẹn theo vùng khác nhau:

```sql
CREATE TABLE event_times (
    id                 BIGINT PRIMARY KEY,
    occurred_at        TIMESTAMPTZ NOT NULL,
    appointment_local  TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    appointment_zone   VARCHAR(64) NOT NULL
);
```

Dùng `Instant` cho `occurred_at` và `LocalDateTime` cùng mã vùng cho lịch hẹn; JDBC nhận thông tin chuyển đổi rõ ràng:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;

public class EventTimeDao {
    public static void insert(
            Connection conn,
            long id,
            Instant occurredAt,
            LocalDateTime appointmentLocal,
            ZoneId appointmentZone) throws SQLException {

        String sql = "INSERT INTO event_times " +
                "(id, occurred_at, appointment_local, appointment_zone) " +
                "VALUES (?, ?, ?, ?)";

        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setLong(1, id);
            ps.setObject(2, occurredAt.atOffset(ZoneOffset.UTC));
            ps.setObject(3, appointmentLocal);
            ps.setString(4, appointmentZone.getId());
            ps.executeUpdate();
        }
    }

    public static void read(Connection conn, long id) throws SQLException {
        String sql = "SELECT occurred_at, appointment_local, " +
                     "appointment_zone FROM event_times WHERE id = ?";

        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setLong(1, id);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException("Không thấy sự kiện id=" + id);
                }

                OffsetDateTime stored =
                        rs.getObject("occurred_at", OffsetDateTime.class);
                Instant occurredAt = stored.toInstant();

                LocalDateTime appointmentLocal =
                        rs.getObject("appointment_local", LocalDateTime.class);
                ZoneId appointmentZone =
                        ZoneId.of(rs.getString("appointment_zone"));

                System.out.println("Thời điểm: " + occurredAt);
                System.out.println("Lịch hẹn: " +
                        appointmentLocal + " tại " + appointmentZone);
            }
        }
    }
}
```

Lý do thiết kế:

- `OffsetDateTime` với offset `UTC` tương ứng ánh xạ `TIMESTAMPTZ` thường được hỗ trợ bởi PostgreSQL JDBC. Khi đọc dùng `toInstant()` để so sánh theo thời điểm, bất kể cách hiển thị giờ địa phương.
- `LocalDateTime` ánh xạ đến `TIMESTAMP WITHOUT TIME ZONE` và không cần múi giờ JVM để “điền” offset.
- `ZoneId` được lưu riêng vì `TIMESTAMPTZ` không ghi nhớ `Asia/Ho_Chi_Minh` hay `Europe/Paris` là vùng gốc.
- Không tự chuyển lịch hẹn thành một `Instant` cho đến khi nghiệp vụ đã xác nhận múi giờ và quy tắc xử lý DST của cuộc hẹn.

Nếu trường hợp nghiệp vụ quy ước cột `TIMESTAMP WITHOUT TIME ZONE` luôn chứa *giờ UTC*, cần chuyển đổi hai chiều một cách tường minh, thay vì truyền `Instant` trực tiếp cho driver rồi dựa vào cấu hình ngầm:

```java
LocalDateTime toDatabaseUtc =
        LocalDateTime.ofInstant(occurredAt, ZoneOffset.UTC);
ps.setObject(1, toDatabaseUtc);

// Khi đọc lại cùng cột timestamp không múi giờ:
LocalDateTime utcFromDatabase =
        rs.getObject("occurred_at_utc", LocalDateTime.class);
Instant recovered = utcFromDatabase.toInstant(ZoneOffset.UTC);
```

Các dòng này minh họa một **quy ước riêng cho cột**; chúng không áp dụng cho cột `TIMESTAMPTZ` trong ví dụ `event_times` ở trên. Nếu hệ thống chọn quy ước UTC cho kiểu không có múi giờ, mọi thành phần ghi/đọc phải tuân thủ đúng quy ước đó.

## 7. Đặt múi giờ phiên trên JDBC connection một cách kiểm soát

Với PostgreSQL, có thể đặt và kiểm tra múi giờ của **connection hiện tại**:

```java
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

public static String configurePostgresSessionUtc(
        Connection connection) throws SQLException {

    try (Statement st = connection.createStatement()) {
        st.execute("SET TIME ZONE 'UTC'");

        try (ResultSet rs = st.executeQuery(
                "SELECT current_setting('TimeZone')")) {
            rs.next();
            return rs.getString(1);
        }
    }
}
```

Đoạn trên là phương thức thành viên của một lớp Java có thể biên dịch khi đặt trong lớp đó; `Connection` do bên gọi cấp và quản lý. Câu lệnh `SET TIME ZONE` tác động lên session này, **không đổi** `ZoneId.systemDefault()`.

Trong ứng dụng dùng `DataSource`/connection pool, cần đặc biệt chú ý:

1. Nhiều `Connection` logic có thể được cấp từ các kết nối vật lý khác nhau. Thiết lập phiên trên một kết nối không tự lan sang kết nối khác.
2. Khi trả kết nối về pool, các thay đổi trạng thái phiên có thể còn tồn tại hoặc được pool/driver khôi phục tùy cấu hình. Một request có thể vô tình dùng múi giờ của request trước nếu thiếu chiến lược reset.
3. Nếu toàn bộ ứng dụng dùng UTC trong phiên, cấu hình **khởi tạo session nhất quán cho mọi kết nối vật lý**, rồi xác minh trên các kết nối lấy từ pool. Nếu cần đổi tạm theo transaction trên PostgreSQL, cân nhắc `SET LOCAL TIME ZONE ...` trong transaction phù hợp để giới hạn phạm vi.
4. Không ghép trực tiếp múi giờ từ input vào lệnh `SET` vì đó là SQL động. Chỉ sử dụng các mã vùng đã kiểm tra hoặc cấu hình cố định; dùng `ZoneId.of(...)` để xác thực tên vùng ở phía Java.

Cần nhớ driver cũng có thể thiết lập tham số phiên khi tạo kết nối hoặc có tùy chọn chuyển đổi thời gian riêng. Không thể nhìn mỗi timezone máy chạy JVM hay DB server để kết luận chính xác timezone phiên hiện tại.

## 8. MySQL có cách xử lý riêng: `TIMESTAMP` và `DATETIME`

MySQL không dùng tên kiểu cột giống PostgreSQL cho mọi trường hợp. Về ngữ nghĩa thông dụng:

- `DATETIME` lưu ngày giờ dưới dạng giá trị lịch, không có chuyển đổi tự động theo múi giờ phiên khi ghi/đọc.
- `TIMESTAMP` được MySQL chuyển từ múi giờ **phiên** sang UTC để lưu và từ UTC sang múi giờ phiên khi đọc. Do đó cùng dữ liệu `TIMESTAMP` có thể hiển thị khác nhau ở các phiên khác nhau.

Các truy vấn giúp kiểm tra cấu hình:

```sql
-- MySQL
SELECT @@global.time_zone  AS global_zone,
       @@session.time_zone AS session_zone,
       @@system_time_zone  AS system_zone;

SET time_zone = '+00:00'; -- Chỉ phiên kết nối hiện tại

SELECT @@session.time_zone, NOW(), UTC_TIMESTAMP();
```

`@@system_time_zone` phản ánh timezone hệ thống mà MySQL nhận biết; nó không nhất thiết là timezone đang áp dụng cho session khi `@@session.time_zone` hoặc cấu hình global có giá trị khác. `NOW()` thể hiện thời gian theo phiên, còn `UTC_TIMESTAMP()` thể hiện thời gian UTC.

MySQL Connector/J còn có các thuộc tính liên quan chuyển đổi thời gian (chẳng hạn `connectionTimeZone`, `preserveInstants`, `forceConnectionTimeZoneToSession` ở các phiên bản có hỗ trợ). Chúng **không tương đương** với `-Duser.timezone` hoặc câu `SET time_zone` trong mọi cấu hình. Phải kiểm tra phiên bản driver và các giá trị mặc định của driver đang dùng trước khi khẳng định kết quả. Không tự áp dụng SQL `SET TIME ZONE` của PostgreSQL cho MySQL, hoặc hiểu `TIMESTAMP` của MySQL như `TIMESTAMP WITHOUT TIME ZONE` của PostgreSQL.

## 9. Tác động lên transaction, truy vấn khoảng thời gian và DST

### 9.1. Lọc khoảng thời gian theo thời điểm thực

Với cột `TIMESTAMPTZ`, truy vấn “các sự kiện xảy ra trong ngày 01/07/2026 tại Việt Nam” phải chuyển **ranh giới ngày ở Việt Nam** thành hai `Instant` trước khi query. Không nên gửi hai chuỗi `2026-07-01 00:00` và `2026-07-02 00:00` vào cột có múi giờ rồi trông chờ session tự chọn vùng.

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;

ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate targetDay = LocalDate.of(2026, 7, 1);

Instant fromInclusive =
        targetDay.atStartOfDay(businessZone).toInstant();
Instant toExclusive =
        targetDay.plusDays(1).atStartOfDay(businessZone).toInstant();

String sql = "SELECT id FROM event_times " +
             "WHERE occurred_at >= ? AND occurred_at < ?";
try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setObject(1, fromInclusive.atOffset(ZoneOffset.UTC));
    ps.setObject(2, toExclusive.atOffset(ZoneOffset.UTC));
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("id"));
        }
    }
}
```

Cách dùng khoảng **[đầu ngày, đầu ngày kế tiếp)** vừa tránh vấn đề giây cuối cùng/độ chính xác phần giây, vừa hoạt động với những ngày chỉ có 23 hoặc 25 giờ do DST. `atStartOfDay(zone)` xác định thời điểm bắt đầu ngày hợp lệ theo quy tắc vùng, không giả định mọi ngày luôn có 24 giờ.

### 9.2. Lịch hẹn theo giờ địa phương có thể nhập nhằng

Ví dụ `2026-11-01 01:30` tại `America/New_York` nằm trong khoảng đồng hồ được chỉnh lùi; giờ này có hai offset hợp lệ. Nếu chỉ lưu `LocalDateTime` rồi gán tùy tiện timezone mặc định JVM, hệ thống có thể chọn sai một trong hai thời điểm.

Có thể kiểm tra trước khi chốt lịch hẹn:

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;

LocalDateTime local = LocalDateTime.of(2026, 11, 1, 1, 30);
ZoneId zone = ZoneId.of("America/New_York");

List<ZoneOffset> candidates =
        zone.getRules().getValidOffsets(local);

if (candidates.size() == 0) {
    throw new IllegalArgumentException("Giờ địa phương không tồn tại");
}
if (candidates.size() > 1) {
    throw new IllegalArgumentException("Giờ địa phương nhập nhằng");
}
```

Đây là kiểm tra trước khi chuyển đổi lịch thành thời điểm. Hai cấu hình timezone JVM/DB giống nhau cũng không thay thế được quyết định nghiệp vụ khi gặp gap hoặc overlap của DST.

## 10. Ma trận chẩn đoán khi bị lệch giờ

| Triệu chứng | Nơi cần kiểm tra trước | Cách xử lý |
|---|---|---|
| `LocalDateTime.now()` trên app lệch giờ so với người dùng | `ZoneId.systemDefault()`, vùng thực của người dùng | Dùng `ZoneId` nghiệp vụ tường minh khi tạo ngày giờ địa phương |
| `CURRENT_DATE` từ DB khác ngày trên ứng dụng | Múi giờ phiên và JVM, thời điểm thực đang gần nửa đêm | Chọn rõ nguồn xác định “ngày hôm nay” |
| Một `TIMESTAMPTZ` hiển thị khác nhau trong hai SQL clients | `SHOW TIME ZONE` trên từng phiên | So sánh `Instant`/UTC, không so chuỗi hiển thị |
| Cùng chuỗi ngày giờ không offset đưa vào `TIMESTAMPTZ` tạo hai thời điểm khác nhau | Múi giờ phiên lúc insert/ép kiểu | Truyền giá trị có offset, tham số SQL kiểu phù hợp |
| Cột `TIMESTAMP WITHOUT TIME ZONE` đọc qua API cũ lệch giờ | `getTimestamp`/`setTimestamp`, JVM zone, driver | Dùng `LocalDateTime` và `getObject`/`setObject`, xác định quy ước cột |
| Lỗi chỉ xuất hiện khi lấy lại connection từ pool | Cấu hình phiên sau khi borrow/return | Đặt hoặc reset session thống nhất, đo giá trị của connection thực |
| Ứng dụng và DB cùng UTC nhưng thời gian “hiện tại” khác nhau | Đồng hồ hệ điều hành, đồng bộ thời gian, transaction start | Đồng bộ clock, chọn một nguồn thời gian đáng tin cậy |
| Lịch hẹn đổi giờ khi đến ngày DST | `ZoneId` và quy tắc gap/overlap | Giữ lịch địa phương kèm zone; quy định chính sách xử lý DST |

### Bài kiểm thử tích hợp nhỏ có giá trị lớn

Trên chính driver/DBMS của dự án, nên kiểm tra các tình huống sau:

1. Ghi `Instant.parse("2026-07-01T02:00:00Z")` vào cột biểu diễn thời điểm, đọc lại và khẳng định `expected.equals(actual)` theo `Instant`; không so chuỗi offset.
2. Trên hai connection có session timezone khác nhau (`UTC` và `Asia/Ho_Chi_Minh`), bảo đảm giá trị thời điểm đọc ra không đổi; trong SQL có thể hiển thị giờ khác.
3. Đọc/ghi một `LocalDateTime.of(2026, 7, 1, 9, 0)` qua cột không có timezone và xác nhận phần ngày giờ không tự thay đổi vì đổi session.
4. Chạy ứng dụng với hai cấu hình `-Duser.timezone` khác nhau; kiểm tra ánh xạ JDBC đã chọn không vô tình phụ thuộc mặc định JVM.
5. Kiểm tra connection lấy từ pool sau khi một request đã đổi timezone phiên; xác nhận trạng thái phiên đáp ứng cấu hình chuẩn.
6. Kiểm tra ngày có DST và độ chính xác phần giây của cột (millisecond/microsecond/nanosecond tùy DB) để tránh khẳng định equality vượt quá độ chính xác DB lưu được.

Mỗi phép thử phải ghi nhận **kiểu cột**, **phiên bản driver**, **múi giờ JVM**, **múi giờ session**, **giá trị Java trước/sau**, thay vì chỉ chụp màn hình SQL client.

## 11. Nguyên tắc thiết kế bền vững

1. Với sự kiện đã xảy ra, thể hiện trong Java bằng `Instant`; chọn cột có ngữ nghĩa thời điểm và ánh xạ JDBC rõ ràng, thường thông qua `OffsetDateTime` khi hệ quản trị/driver hỗ trợ.
2. Với lịch hẹn, giờ mở cửa hay ngày sinh, giữ `LocalDateTime`, `LocalTime` hoặc `LocalDate` theo đúng nghiệp vụ; lưu mã `ZoneId` riêng nếu lịch gắn với vùng địa lý.
3. Đừng dựa vào timezone mặc định JVM để chuyển đổi dữ liệu của người dùng; truyền `ZoneId` hoặc `ZoneOffset` đúng yêu cầu.
4. Đo múi giờ **session trên chính JDBC connection** vì cấu hình server, driver và connection pool có thể khác giả định.
5. Phân biệt **thời gian biểu diễn** với **đồng hồ thực**; UTC giúp chuẩn hóa cách diễn giải nhưng không tự đồng bộ hai máy.
6. Dùng `PreparedStatement` với kiểu `java.time` phù hợp; kiểm thử round-trip và các trường hợp DST trên DBMS/driver ứng dụng thật sự sử dụng.

Một hệ thống JDBC đáng tin cậy không cần ép mọi ngày giờ thành UTC. Điều cần thiết là xác định chính xác trường nào đại diện **thời điểm tuyệt đối**, trường nào đại diện **giờ lịch địa phương**, và mỗi lớp JVM, session, DB server đang tham gia vào phép chuyển đổi nào.

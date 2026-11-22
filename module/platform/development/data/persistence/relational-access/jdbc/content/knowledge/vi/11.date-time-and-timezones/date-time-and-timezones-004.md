# Sử dụng OffsetTime và OffsetDateTime khi driver hỗ trợ

Trong ứng dụng Java truy cập cơ sở dữ liệu quan hệ qua **JDBC**, dữ liệu ngày giờ có thể biểu thị **thời điểm xảy ra một sự kiện**, **giờ trong ngày** hoặc **lịch hẹn theo múi giờ địa lý**. Chọn nhầm kiểu dữ liệu có thể làm mất thông tin offset, dịch giờ khi đọc lại, hoặc tạo lỗi khi chuyển giữa môi trường phát triển và máy chủ.

Bài thuộc chương **Ngày giờ và múi giờ** của JDBC, tập trung vào hai kiểu của `java.time`:

- `OffsetDateTime`: ngày, giờ và **độ lệch so với UTC** (ví dụ `2026-11-17T10:00:00+07:00`).
- `OffsetTime`: giờ trong ngày và **độ lệch so với UTC**, **không có ngày** (ví dụ `17:30:00+07:00`).

Từ **JDBC 4.2**, API hỗ trợ làm việc với `java.time` bằng `PreparedStatement.setObject(...)` và `ResultSet.getObject(..., Class<T>)`. Hai kiểu SQL tương ứng là `TIMESTAMP WITH TIME ZONE` và `TIME WITH TIME ZONE`. Tuy nhiên, **driver và hệ quản trị cơ sở dữ liệu (DBMS) phải thực sự hỗ trợ** cả kiểu SQL lẫn cách chuyển đổi Java; phiên bản JDBC mới không tự biến một DBMS thiếu kiểu dữ liệu thành có hỗ trợ.

## 1. Chọn đúng mô hình thời gian

| Ý nghĩa cần lưu | Kiểu Java phù hợp | Kiểu SQL gợi ý nếu được hỗ trợ |
| --- | --- | --- |
| Ngày giờ có offset, biểu diễn được một thời điểm thực | `OffsetDateTime` | `TIMESTAMP WITH TIME ZONE` |
| Giờ trong ngày có offset cố định, chưa xác định ngày | `OffsetTime` | `TIME WITH TIME ZONE` |
| Ngày giờ địa phương, chưa gắn offset hay zone | `LocalDateTime` | `TIMESTAMP` hoặc `TIMESTAMP WITHOUT TIME ZONE` |
| Giờ địa phương không có offset | `LocalTime` | `TIME` hoặc `TIME WITHOUT TIME ZONE` |
| Một thời điểm tuyệt đối để so sánh, sắp xếp, tính khoảng cách | `Instant` | Cần quy ước lưu trữ/ánh xạ của hệ thống; không có ánh xạ `Instant` → SQL phổ quát được đảm bảo trên mọi driver |
| Lịch theo quy tắc địa lý, ví dụ 09:00 mỗi ngày tại Berlin | `LocalTime` kết hợp `ZoneId` (và ngày cụ thể khi tính thời điểm) | Thường lưu giờ địa phương và ID múi giờ ở hai cột |

**Offset không đồng nghĩa với múi giờ địa lý.** `+07:00` là độ lệch cố định so với UTC; `Asia/Ho_Chi_Minh` là một `ZoneId` có quy tắc thời gian của khu vực. `Europe/Berlin` có thể ứng với `+01:00` hoặc `+02:00` tùy thời điểm. Vì vậy, `OffsetDateTime` cho biết một thời điểm và offset được ghi nhận nhưng **không tự chứa toàn bộ quy tắc đổi giờ theo mùa**; `OffsetTime` còn thiếu cả ngày.

### Hai cách biểu diễn cùng một thời điểm

```java
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

OffsetDateTime inPlusSeven =
        OffsetDateTime.parse("2026-11-17T10:00:00+07:00");
OffsetDateTime inMinusFive =
        inPlusSeven.withOffsetSameInstant(ZoneOffset.ofHours(-5));

System.out.println(inPlusSeven);          // 2026-11-17T10:00+07:00
System.out.println(inMinusFive);          // 2026-11-16T22:00-05:00
System.out.println(inPlusSeven.isEqual(inMinusFive)); // true
System.out.println(inPlusSeven.equals(inMinusFive));  // false
System.out.println(inPlusSeven.toInstant());          // 2026-11-17T03:00:00Z
```

`isEqual` so sánh **thời điểm thực**, còn `equals` so sánh cả biểu diễn ngày giờ và offset. Khi kiểm tra dữ liệu lấy lại từ cơ sở dữ liệu, nếu yêu cầu là **không đổi thời điểm**, hãy so sánh `toInstant()`; nếu yêu cầu là **giữ nguyên offset nhập ban đầu**, cần kiểm tra riêng offset và xem DBMS có lưu giữ nó hay không.

### OffsetTime không tạo thành một thời điểm hoàn chỉnh

```java
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.OffsetTime;

OffsetTime cutoff = OffsetTime.parse("17:30:00+07:00");

// Chỉ khi gắn thêm ngày, giá trị mới xác định được một thời điểm.
OffsetDateTime onDate = cutoff.atDate(LocalDate.of(2026, 11, 17));
System.out.println(onDate.toInstant()); // 2026-11-17T10:30:00Z
```

Không thể gọi `toInstant()` trực tiếp trên `OffsetTime` vì không có ngày. Đối với lịch lặp “09:00 mỗi ngày theo giờ Paris”, chỉ lưu `09:00+01:00` sẽ sai vào giai đoạn Paris dùng offset `+02:00`; nên lưu `LocalTime` và `Europe/Paris`, rồi tính offset theo **ngày thực tế**.

## 2. Hai kiểu SQL và giới hạn hỗ trợ

JDBC 4.2 định nghĩa các mã loại dữ liệu sau:

| Java | SQL chuẩn | Hằng JDBC |
| --- | --- | --- |
| `OffsetTime` | `TIME WITH TIME ZONE` | `java.sql.Types.TIME_WITH_TIMEZONE`; `JDBCType.TIME_WITH_TIMEZONE` |
| `OffsetDateTime` | `TIMESTAMP WITH TIME ZONE` | `java.sql.Types.TIMESTAMP_WITH_TIMEZONE`; `JDBCType.TIMESTAMP_WITH_TIMEZONE` |

Không phải mọi cơ sở dữ liệu đều triển khai hai kiểu SQL này. Ngoài ra, cách lưu trữ và trả dữ liệu có thể khác nhau:

- Hệ quản trị có thể **chuẩn hóa timestamp về một offset khác** (thường là UTC) trong lúc vẫn giữ nguyên thời điểm thực; đọc lại bằng `OffsetDateTime` có thể cho offset khác ban đầu.
- Độ chính xác phần thập phân của giây tùy kiểu cột và DBMS, ví dụ lưu được đến microsecond nhưng đối tượng Java có nanosecond.
- Việc xử lý `TIME WITH TIME ZONE`, đặc biệt ý nghĩa so sánh giờ khi không có ngày, có thể phụ thuộc DBMS; đừng giả định mọi driver đều hỗ trợ `OffsetTime`.
- Một số DBMS dùng tên kiểu SQL hoặc cú pháp riêng. Một cột tên `TIMESTAMP` không có nghĩa nó có cùng ngữ nghĩa với `TIMESTAMP WITH TIME ZONE`.

Ví dụ, PostgreSQL dùng `timestamptz` cho `TIMESTAMP WITH TIME ZONE` và chuẩn hóa các giá trị thành thời điểm, không giữ lại offset nhập gốc như một thuộc tính riêng. Các DBMS khác có thể có ngữ nghĩa khác. Vì thế, hãy kiểm tra phiên bản **DBMS + driver + loại cột cụ thể**, không suy luận chỉ từ tên phương thức JDBC.

Một lược đồ minh họa theo cú pháp SQL chuẩn là:

```sql
CREATE TABLE schedule_samples (
    id BIGINT PRIMARY KEY,
    planned_at TIMESTAMP WITH TIME ZONE NOT NULL,
    daily_cutoff TIME WITH TIME ZONE NOT NULL
);
```

**Điều kiện tiên quyết:** DBMS đang dùng phải chấp nhận hai kiểu trên. Với cơ sở dữ liệu không hỗ trợ `TIME WITH TIME ZONE`, không thể sử dụng nguyên lược đồ này chỉ bằng cách nâng cấp driver; phải đổi thiết kế cột phù hợp với nhu cầu nghiệp vụ.

## 3. Ghi dữ liệu bằng PreparedStatement.setObject

Với JDBC 4.2 và driver hỗ trợ ánh xạ kiểu, có thể truyền trực tiếp `OffsetDateTime` và `OffsetTime` làm tham số SQL, không cần chuyển thành chuỗi tự định dạng:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.time.OffsetTime;
import java.util.Objects;
import javax.sql.DataSource;

public final class ScheduleRepository {
    private final DataSource dataSource;

    public ScheduleRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public void insert(long id, OffsetDateTime plannedAt, OffsetTime cutoff)
            throws SQLException {
        Objects.requireNonNull(plannedAt, "plannedAt");
        Objects.requireNonNull(cutoff, "cutoff");

        String sql = "INSERT INTO schedule_samples "
                + "(id, planned_at, daily_cutoff) VALUES (?, ?, ?)";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);
            statement.setObject(2, plannedAt);
            statement.setObject(3, cutoff);
            statement.executeUpdate();
        }
    }
}
```

Gọi `setObject` với đối tượng `java.time` cho phép driver tự ánh xạ đến loại SQL thích hợp. Đây là **SQL tham số hóa** nên không phải nối chuỗi thời gian vào SQL, giảm lỗi cú pháp/escaping và tránh SQL injection do ghép đầu vào. `try-with-resources` bảo đảm đóng `PreparedStatement` và `Connection`; nếu dùng connection pool, thao tác `close()` của kết nối thường trả nó về pool.

Với một số driver, có thể truyền rõ kiểu SQL đích:

```java
import java.sql.JDBCType;

statement.setObject(2, plannedAt, JDBCType.TIMESTAMP_WITH_TIMEZONE);
statement.setObject(3, cutoff, JDBCType.TIME_WITH_TIMEZONE);
```

Đây là **đoạn thay thế** cho hai lệnh `setObject` tương ứng bên trong phương thức `insert`, không phải đoạn chạy độc lập. Overload nhận `SQLType` được đưa vào JDBC 4.2 nhưng driver có thể không hỗ trợ đầy đủ; **chỉ định kiểu đích không giải quyết được việc DBMS thiếu kiểu SQL**.

Không nên tự động đổi sang `setTimestamp(...)` hoặc `setTime(...)` để “chữa lỗi” vì các kiểu `java.sql.Timestamp` và `java.sql.Time` không mang offset gốc như `OffsetDateTime` và `OffsetTime`. Việc chuyển đổi qua múi giờ JVM, session DB hoặc `Calendar` phải có quy ước rõ ràng nếu dùng API đời cũ.

## 4. Đọc dữ liệu bằng ResultSet.getObject

Sử dụng overload nhận `Class<T>` để yêu cầu kết quả đúng kiểu Java mong muốn:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.time.OffsetTime;
import javax.sql.DataSource;

public final class ScheduleReader {
    public static void printOne(DataSource dataSource, long id)
            throws SQLException {
        String sql = "SELECT planned_at, daily_cutoff "
                + "FROM schedule_samples WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);

            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) {
                    throw new SQLException("Không tìm thấy lịch có id = " + id);
                }

                OffsetDateTime planned =
                        result.getObject("planned_at", OffsetDateTime.class);
                OffsetTime cutoff =
                        result.getObject("daily_cutoff", OffsetTime.class);

                System.out.println("Thời điểm UTC: " + planned.toInstant());
                System.out.println("Giờ chốt: " + cutoff);
            }
        }
    }
}
```

Nếu các cột có thể `NULL`, `getObject("...", OffsetDateTime.class)` hoặc `getObject("...", OffsetTime.class)` có thể trả về `null`; hãy kiểm tra trước khi gọi `toInstant()` hoặc xử lý tiếp. Lược đồ minh họa sử dụng `NOT NULL` nên ví dụ trên không cần nhánh này.

Đừng dựa vào `ResultSet.getString(...)` rồi phân tích chuỗi bằng một định dạng tự đoán: cách biểu diễn ngày giờ từ cơ sở dữ liệu khác nhau theo DBMS, session và driver. Khi typed `getObject` không được hỗ trợ, chọn phương án tương thích đã được kiểm chứng cho hệ đang sử dụng.

## 5. Kiểm tra driver hỗ trợ trước khi triển khai

Cần xác minh **ba lớp độc lập**:

1. **Kiểu cột:** DBMS chấp nhận `TIME WITH TIME ZONE` và/hoặc `TIMESTAMP WITH TIME ZONE` theo lược đồ đang triển khai.
2. **Ghi:** driver chuyển được giá trị `OffsetTime`/`OffsetDateTime` từ `PreparedStatement.setObject` sang đúng kiểu cột.
3. **Đọc:** driver hỗ trợ `ResultSet.getObject(column, OffsetTime.class)`/`OffsetDateTime.class` mà không làm sai ngữ nghĩa cần bảo toàn.

Có thể xem thông tin loại dữ liệu do driver công bố:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.Types;
import javax.sql.DataSource;

try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData meta = connection.getMetaData();
    try (ResultSet types = meta.getTypeInfo()) {
        while (types.next()) {
            int sqlType = types.getInt("DATA_TYPE");
            if (sqlType == Types.TIME_WITH_TIMEZONE
                    || sqlType == Types.TIMESTAMP_WITH_TIMEZONE) {
                System.out.printf("%s: SQL type %d%n",
                        types.getString("TYPE_NAME"), sqlType);
            }
        }
    }
}
```

**Lưu ý:** kết quả `DatabaseMetaData.getTypeInfo()` chỉ là **dấu hiệu** loại dữ liệu driver công bố; nó không chứng minh `setObject`/`getObject` hỗ trợ từng lớp Java hoặc bảo toàn offset theo mong muốn. Kết luận chắc chắn cần **thử ghi → đọc** trên phiên bản driver và DBMS mà dự án sẽ triển khai.

### Thử nghiệm round-trip có ý nghĩa

Giả sử bản ghi đã được ghi bằng ví dụ ở phần 3. Bên trong khối đọc `ResultSet` sau khi `result.next()` trả về `true`, có thể kiểm tra:

```java
import java.time.OffsetDateTime;

OffsetDateTime input =
        OffsetDateTime.parse("2026-11-17T10:00:00+07:00");
OffsetDateTime output =
        result.getObject("planned_at", OffsetDateTime.class);

// Bất biến thường quan trọng nhất cho mốc sự kiện:
if (!input.toInstant().equals(output.toInstant())) {
    throw new IllegalStateException("Đã thay đổi thời điểm lưu trữ");
}

// Chỉ yêu cầu so sánh này nếu nghiệp vụ cần giữ nguyên offset nhập:
boolean originalOffsetPreserved =
        input.getOffset().equals(output.getOffset());
```

Đây là **đoạn mã đặt trong khối đọc kết quả**, nơi biến `result` là `ResultSet` đã có hàng dữ liệu. Khi thử nghiệm, dùng các giá trị có độ chính xác đúng với kiểu cột; kiểm tra cả phần thập phân giây nếu ứng dụng cần nanosecond hoặc microsecond.

Nên thử tối thiểu những trường hợp sau:

| Dữ liệu kiểm tra | Mục đích |
| --- | --- |
| `2026-11-17T10:00:00+07:00` | Đường đi ghi/đọc cơ bản. |
| `2026-11-16T22:00:00-05:00` | Cùng instant với hàng trên nhưng offset khác; phát hiện chuẩn hóa offset. |
| `2026-11-17T00:15:00+14:00` | Dịch ngày khi quy về UTC. |
| `2026-11-17T10:00:00.123456+07:00` | Kiểm tra độ chính xác phần thập phân giây. |
| `17:30:00+07:00` ở cột `TIME WITH TIME ZONE` | Xác minh driver có đọc/ghi được `OffsetTime` và bảo toàn ý nghĩa giờ/offset. |

Trường hợp cùng instant với offset khác nên được ghi thành **hai bản ghi khác nhau** hoặc thử độc lập với một cột; không cần đòi DBMS phải trả lại cả hai offset ban đầu. Đặc biệt, đối với kiểu `TIME WITH TIME ZONE`, đừng dùng so sánh giữa hai giá trị để suy ra thứ tự **thời điểm tuyệt đối** khi chưa có ngày.

## 6. Khi nào dùng OffsetDateTime, khi nào tránh OffsetTime?

### Dùng OffsetDateTime cho thời điểm đã xác định

Phù hợp khi API trả về một dấu thời gian kèm offset, ví dụ “giao dịch nhận lúc `2026-11-17T10:00:00+07:00`”. Sau khi lưu bằng `TIMESTAMP WITH TIME ZONE`, thường nên dùng `toInstant()` để so sánh thời điểm và tính thời lượng; chỉ dùng offset đã lưu nếu đặc tả DBMS bảo đảm nó được giữ nguyên.

Nếu hiển thị cho người dùng theo một khu vực địa lý, hãy chuyển thời điểm sang `ZoneId` tại bước trình bày:

```java
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

OffsetDateTime stored =
        OffsetDateTime.parse("2026-11-17T10:00:00+07:00");
ZonedDateTime berlin =
        stored.atZoneSameInstant(ZoneId.of("Europe/Berlin"));

System.out.println(berlin); // 2026-11-17T04:00+01:00[Europe/Berlin]
```

`atZoneSameInstant` giữ nguyên thời điểm; Java áp dụng quy tắc của múi giờ Berlin tại ngày đã cho. Tránh lấy offset cố định `+01:00` rồi áp dụng cho mọi ngày trong năm nếu nghiệp vụ theo giờ địa phương của Berlin.

### Chỉ dùng OffsetTime khi thật sự cần giờ trong ngày với offset cố định

`OffsetTime` hữu ích với giờ cố định theo UTC offset, ví dụ “khung xử lý theo `+07:00`”. Nó **không phù hợp để biểu diễn thời điểm đã xảy ra** vì thiếu ngày, và thường **không phù hợp cho lịch theo múi giờ địa lý có đổi giờ mùa**.

Với lịch lặp “09:00 giờ Berlin vào mỗi ngày làm việc”, mô hình an toàn hơn là:

```java
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

LocalTime localTime = LocalTime.of(9, 0);
ZoneId zone = ZoneId.of("Europe/Berlin");

ZonedDateTime summer = localTime.atDate(LocalDate.of(2026, 7, 1))
        .atZone(zone); // 2026-07-01T09:00+02:00[Europe/Berlin]
ZonedDateTime winter = localTime.atDate(LocalDate.of(2026, 12, 1))
        .atZone(zone); // 2026-12-01T09:00+01:00[Europe/Berlin]
```

Lưu `LocalTime` (ví dụ cột `TIME`) và `ZoneId.getId()` (ví dụ cột `VARCHAR`). Khi lập lịch vào một ngày cụ thể, dùng quy tắc zone để tạo `ZonedDateTime`; tại giờ chuyển mùa, còn phải có chính sách xử lý giờ địa phương bị trùng hoặc không tồn tại.

## 7. Nếu driver hoặc DBMS không hỗ trợ

Không nên mặc định dùng `TIMESTAMP WITHOUT TIME ZONE` để lưu trực tiếp `OffsetDateTime`, bởi cột đó **không mang thông tin offset** và cách driver chuyển đổi có thể phụ thuộc cấu hình. Các phương án thay thế phải xuất phát từ **dữ liệu nghiệp vụ thật sự cần giữ**:

| Yêu cầu | Phương án lưu trữ có thể cân nhắc | Điều cần quy định |
| --- | --- | --- |
| Chỉ cần thời điểm tuyệt đối | Lưu số giây Unix (và phần nano nếu cần) bằng cột số; hoặc lưu timestamp UTC theo hợp đồng ứng dụng/DB rõ ràng. | Độ chính xác, giới hạn số, quy ước UTC, cách đọc/ghi và phạm vi kiểm thử. |
| Cần thời điểm và offset người dùng đã gửi | Lưu thời điểm tuyệt đối **cùng cột offset** riêng (ví dụ tổng số giây offset). | Khôi phục biểu diễn; không nhầm offset với zone địa lý. |
| Cần giờ trong ngày và offset cố định | Lưu `LocalTime` + offset giây riêng. | Không xem đó là một instant khi chưa có ngày. |
| Cần lịch địa phương theo quy tắc khu vực | Lưu ngày/giờ địa phương cùng `ZoneId` như `Asia/Ho_Chi_Minh` hoặc `Europe/Berlin`. | Chính sách khi DST gây giờ không tồn tại hoặc bị lặp. |

Ví dụ xây lại `OffsetTime` từ hai cột `TIME` và `INTEGER`, khi driver hỗ trợ `LocalTime`:

```java
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalTime;
import java.time.OffsetTime;
import java.time.ZoneOffset;

// Trong khối đang xử lý một hàng ResultSet:
LocalTime local = rs.getObject("local_time", LocalTime.class);
int offsetSeconds = rs.getInt("offset_seconds");
if (rs.wasNull()) {
    throw new SQLException("Thiếu offset_seconds");
}
OffsetTime cutoff = OffsetTime.of(
        local, ZoneOffset.ofTotalSeconds(offsetSeconds));
```

Đoạn này giả định `rs` là `ResultSet` đã có bản ghi và cột `local_time` không `NULL`. Khi ghi, có thể dùng `cutoff.toLocalTime()` và `cutoff.getOffset().getTotalSeconds()` vào hai tham số của `PreparedStatement`. Đây là thiết kế lược đồ thay thế có chủ ý, **không phải cách JDBC tự ánh xạ một cột `TIME WITH TIME ZONE`**.

## 8. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| DBMS báo sai cú pháp khi tạo `TIME WITH TIME ZONE` | DBMS không hỗ trợ kiểu SQL hoặc cú pháp khác. | Đối chiếu tài liệu DBMS, đổi lược đồ theo khả năng thực tế. |
| `SQLException` hoặc `SQLFeatureNotSupportedException` khi `setObject`/`getObject` | Driver hoặc tổ hợp Java class/SQL type không được hỗ trợ. | Kiểm tra driver/version, loại cột và thử round-trip; dùng ánh xạ thay thế có chủ đích nếu cần. |
| Đọc lại `OffsetDateTime` thành `Z`/`+00:00` | DBMS/driver chuẩn hóa offset. | So sánh `toInstant()`; lưu offset gốc riêng nếu nghiệp vụ cần. |
| Giờ khác nhau giữa máy lập trình và máy chủ | Đường chuyển đổi dựa vào zone mặc định JVM/session hoặc dùng API không mang offset. | Ưu tiên typed `java.time`; đặt hợp đồng timezone rõ ràng, thử với cấu hình khác nhau. |
| Mất chữ số thập phân giây | Độ chính xác kiểu SQL thấp hơn giá trị Java. | Chọn precision phù hợp, xác định quy tắc làm tròn/cắt và kiểm thử. |
| Lịch “09:00 Berlin” lệch một giờ sau chuyển mùa | Chỉ lưu offset cố định và thiếu `ZoneId`. | Lưu `LocalTime + ZoneId` và tính theo ngày cụ thể. |
| Tưởng đổi `OffsetDateTime` sang offset khác là đổi thời điểm | Nhầm biểu diễn giờ địa phương với instant. | Dùng `withOffsetSameInstant` hoặc `atZoneSameInstant` khi muốn giữ thời điểm. |

Khi debug, hãy ghi nhận **kiểu cột thực tế, phiên bản driver, kiểu Java đầu vào, giá trị `toInstant()` và offset đọc lại**. Không chỉ so sánh chuỗi ngày giờ hiển thị: hai chuỗi có thể khác nhau nhưng cùng đại diện một thời điểm.

## 9. Bài thực hành tự kiểm tra

Bạn triển khai API đặt lịch và gặp ba tình huống:

1. Cuộc họp một lần diễn ra lúc `2026-11-17T10:00:00+07:00`. DBMS hỗ trợ `TIMESTAMP WITH TIME ZONE`, nhưng khi đọc trả về `2026-11-17T03:00:00Z`. Dữ liệu có bị sai không? Cần kiểm tra bằng phương thức nào?
2. Hệ thống phải chạy tác vụ “09:00 sáng mỗi ngày tại Berlin”. Có nên lưu `OffsetTime.parse("09:00:00+01:00")` rồi dùng cả năm không? Nên lưu những thông tin gì?
3. Driver trả `SQLFeatureNotSupportedException` khi gọi `getObject("daily_cutoff", OffsetTime.class)`. Việc cột có tên `TIME WITH TIME ZONE` có đủ để kết luận chương trình bắt buộc phải chạy không? Bạn sẽ xác minh và chọn phương án nào?

**Đáp án định hướng:** (1) Hai giá trị chỉ khác offset biểu diễn, nhưng cùng instant; dùng `toInstant()` để kiểm tra. (2) Không: Berlin đổi offset theo mùa; lưu `LocalTime` cùng `ZoneId("Europe/Berlin")`, xác định ngày và chính sách DST khi lập lịch. (3) Không: khả năng của DBMS và driver là hai điều kiện khác nhau; kiểm tra phiên bản, đọc/ghi thử, hoặc dùng lược đồ thay thế lưu giờ địa phương + offset nếu yêu cầu nghiệp vụ cho phép.

**Ghi nhớ:** `OffsetDateTime` kết hợp tốt với `TIMESTAMP WITH TIME ZONE` khi driver hỗ trợ và ứng dụng quan tâm thời điểm tuyệt đối; `OffsetTime` chỉ có ý nghĩa khi cần giờ trong ngày kèm offset và DBMS/driver hỗ trợ `TIME WITH TIME ZONE`. Cả hai **không thay thế `ZoneId`** cho lịch theo quy tắc múi giờ địa lý. Hãy xác minh round-trip trên đúng môi trường triển khai và xác định rõ cần bảo toàn **instant, offset hay giờ địa phương** trước khi chọn kiểu lưu trữ.

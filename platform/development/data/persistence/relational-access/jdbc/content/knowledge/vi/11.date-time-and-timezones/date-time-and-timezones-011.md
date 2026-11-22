# Thiết kế quy ước lưu và truy vấn thời gian nhất quán

Trong ứng dụng Java dùng **JDBC** để truy cập cơ sở dữ liệu quan hệ, lỗi thời gian thường không nằm ở câu SQL phức tạp mà ở một giả định ngầm: hai hệ thống cùng hiểu một giá trị `2026-11-17 09:00:00` theo cùng một cách. Khi máy ứng dụng, máy cơ sở dữ liệu và người dùng ở các múi giờ khác nhau, giả định này có thể làm lịch hẹn lệch giờ, báo cáo sai ngày hoặc dữ liệu bị dịch thêm một lần khi đọc lại.

Mục tiêu của bài học là thiết kế **hợp đồng thời gian xuyên suốt** từ nghiệp vụ, kiểu `java.time`, cột SQL, tham số `PreparedStatement`, kết quả `ResultSet` đến câu truy vấn và kiểm thử. Các ví dụ có thể sử dụng `DataSource` để lấy kết nối, SQL tham số hóa và transaction theo đúng các API chuẩn của JDBC. Phần SQL minh họa chi tiết dùng **PostgreSQL**; khi chuyển sang hệ quản trị khác cần kiểm tra lại kiểu cột và hành vi driver như giải thích ở cuối bài.

## 1. Bốn ý nghĩa khác nhau của một giá trị thời gian

Trước khi chọn kiểu dữ liệu hoặc API, phải xác định **giá trị đó có nghĩa gì trong nghiệp vụ**.

| Ý nghĩa | Ví dụ | Kiểu Java nên dùng | Cách lưu phù hợp |
| --- | --- | --- | --- |
| **Thời điểm tuyệt đối** (instant): một sự kiện đã hoặc sẽ xảy ra tại một điểm xác định trên dòng thời gian | Thanh toán hoàn tất, phiên đăng nhập được tạo, thời điểm giao hàng đã chốt | `Instant` | Cột lưu được instant, ví dụ `TIMESTAMP WITH TIME ZONE` trên PostgreSQL |
| **Ngày theo lịch** (calendar date): ngày có ý nghĩa độc lập với giờ | Ngày sinh, ngày nghỉ, ngày kế toán | `LocalDate` | `DATE` |
| **Ngày giờ địa phương** (wall-clock datetime): con số trên đồng hồ tại một địa điểm, chưa đủ để xác định instant | Khách đặt lịch lúc 09:00 tại văn phòng Hà Nội | `LocalDateTime` cùng `ZoneId` | `TIMESTAMP WITHOUT TIME ZONE` + cột mã vùng thời gian; có thể lưu thêm instant đã phân giải |
| **Quy tắc lặp theo giờ địa phương** | Gửi nhắc việc lúc 08:00 mỗi sáng ở New York | `LocalTime`, `ZoneId` và quy tắc lặp | `TIME WITHOUT TIME ZONE` + mã vùng và quy tắc lịch; tính instant cho từng lần chạy |

Ví dụ `2026-11-17 09:00` tại `Asia/Ho_Chi_Minh` tương ứng với instant `2026-11-17T02:00:00Z`. Ký tự `Z` biểu thị độ lệch UTC bằng 0. Hai cách viết chỉ cùng một thời điểm, nhưng `09:00` **không tự nó xác định** thời điểm nếu thiếu múi giờ hoặc offset.

Phân biệt ba khái niệm:

- **UTC** là chuẩn tham chiếu thời gian. Một `Instant` biểu thị điểm trên dòng thời gian, không mang múi giờ trình bày.
- **Offset** là độ lệch tại một thời điểm, chẳng hạn `+07:00` hoặc `-04:00`. `OffsetDateTime` mang ngày giờ và offset cụ thể.
- **Zone ID** là vùng có lịch sử và quy tắc chuyển giờ, chẳng hạn `Asia/Ho_Chi_Minh` hoặc `America/New_York`. `ZonedDateTime` kết hợp ngày giờ, vùng và quy tắc của vùng tại thời điểm đó.

Không thay `America/New_York` bằng `-05:00` trong dữ liệu đặt lịch dài hạn: mùa hè ở New York có thể dùng `-04:00`. Offset chỉ nói độ lệch ở **một lần** cụ thể; Zone ID cho phép tìm quy tắc của các lần khác.

## 2. Đặt ra một hợp đồng thời gian cho từng trường

Một quy ước rõ ràng nên trả lời được các câu hỏi sau trước khi tạo bảng:

1. **Ý nghĩa**: trường này là instant, ngày theo lịch, giờ địa phương hay quy tắc lặp?
2. **Nguồn giá trị**: máy chủ ứng dụng, cơ sở dữ liệu, thiết bị người dùng hay hệ thống ngoài cấp thời gian? Đồng hồ nào có thẩm quyền?
3. **Vùng để hiển thị và tính lịch**: dùng vùng của người dùng, chi nhánh hay một vùng nghiệp vụ cố định? Vùng này được lưu ở đâu?
4. **Độ chính xác**: giây, mili giây hay micro giây? Có yêu cầu giữ nanosecond của Java không?
5. **Cách xử lý ngoại lệ lịch**: khi đổi giờ mùa hè tạo ra giờ không tồn tại hoặc trùng giờ, chọn chính sách nào?
6. **Hợp đồng truy vấn**: khoảng thời gian là `[từ, đến)` hay bao gồm cả hai đầu? Một “ngày” được tính theo vùng nào?

Quy ước đề xuất cho đa số ứng dụng:

- Sự kiện và mốc kiểm toán (`created_at`, `paid_at`, `expires_at`) có nghĩa là **instant**; lưu thống nhất và truyền qua API dưới dạng ISO 8601 có `Z` hoặc offset xác định. Khi xuất UTC, ví dụ `2026-11-17T02:00:00Z`.
- Thông tin “người dùng muốn 09:00 tại địa điểm X” phải giữ **giờ địa phương + Zone ID**; có thể lưu instant đã phân giải để lên lịch và tìm kiếm hiệu quả.
- Ngày thuần túy (`birth_date`, `business_date`) dùng `DATE`; không chuyển thành midnight UTC chỉ để hợp thức hóa một cột timestamp.
- Trong code, tên `...At` thường chỉ instant, `...Date` chỉ ngày, `...Local` chỉ giờ địa phương, `...ZoneId` chỉ vùng. Tên gọi là gợi ý, nhưng **định nghĩa trường trong hợp đồng dữ liệu mới là chuẩn**.
- Chọn một quy tắc duy nhất cho thời điểm hệ thống: ví dụ `created_at` sinh ở DB bằng `CURRENT_TIMESTAMP`, còn `occurred_at` do dịch vụ phát sinh sự kiện cung cấp. Không trộn lẫn rồi kỳ vọng chúng luôn bằng nhau; đồng hồ giữa các máy có sai lệch.

### Mẫu hợp đồng dữ liệu

| Trường | Ý nghĩa | Quy ước lưu và truy vấn |
| --- | --- | --- |
| `created_at` | Instant do cơ sở dữ liệu ghi khi tạo | `TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP`; so sánh theo instant |
| `starts_at` | Instant đã tính cho một lịch hẹn cụ thể | `TIMESTAMPTZ NOT NULL`; tìm kiếm bằng khoảng instant |
| `starts_local` | Giờ khách hàng đã chọn trên đồng hồ địa phương | `TIMESTAMP WITHOUT TIME ZONE NOT NULL`; không tự quy đổi vùng |
| `zone_id` | Vùng dùng để hiểu `starts_local` | Chuỗi IANA như `Asia/Ho_Chi_Minh`; kiểm tra bằng `ZoneId.of(...)` |
| `birth_date` | Ngày sinh độc lập với vùng | `DATE`; ánh xạ trực tiếp `LocalDate` |

Khi lưu **cả** `starts_local`, `zone_id` và `starts_at`, hãy ghi rõ nguồn sự thật. Chẳng hạn lịch hẹn tương lai có thể coi `starts_local + zone_id` là yêu cầu của khách, còn `starts_at` là kết quả tính tại lúc đặt. Nếu cơ sở dữ liệu quy tắc múi giờ (tzdb) được cập nhật, cần quyết định có tính lại instant của lịch hẹn tương lai hay giữ instant đã chốt. Mỗi thay đổi phải cập nhật các cột liên quan trong **cùng transaction**, tránh trạng thái mâu thuẫn.

## 3. Ánh xạ `java.time` và kiểu SQL qua JDBC

JDBC 4.2 hỗ trợ `setObject`/`getObject` cho nhiều kiểu trong `java.time`. Tuy nhiên **các driver không hỗ trợ hoàn toàn giống nhau**, đặc biệt với `Instant`, `OffsetDateTime` và các kiểu “with time zone”. Chọn cách ánh xạ theo cơ sở dữ liệu và kiểm thử trên **driver thật**.

| Java | Kiểu SQL thường gặp | Ý nghĩa và lưu ý |
| --- | --- | --- |
| `LocalDate` | `DATE` | Không có giờ hay múi giờ |
| `LocalTime` | `TIME WITHOUT TIME ZONE` | Giờ trong ngày, không phải thời điểm tuyệt đối |
| `LocalDateTime` | `TIMESTAMP WITHOUT TIME ZONE` | Chỉ gồm các thành phần lịch; không có offset |
| `OffsetDateTime` | `TIMESTAMP WITH TIME ZONE` nếu driver hỗ trợ | Có offset để xác định instant; DB có thể không lưu offset gốc |
| `Instant` | Lưu qua biểu diễn driver hỗ trợ, ví dụ `OffsetDateTime` ở UTC | Không mặc định `PreparedStatement.setObject(index, instant)` chạy trên mọi driver |
| `ZoneId` | `VARCHAR`/`TEXT` | Lưu mã IANA; không phải kiểu thời điểm của SQL |

**Điểm dễ nhầm nhất:** `TIMESTAMP WITH TIME ZONE` không có nghĩa là luôn lưu tên múi giờ của người dùng.

- **PostgreSQL**: `TIMESTAMPTZ` lưu một instant; khi hiển thị qua SQL, giá trị được diễn đạt theo `TimeZone` của session. Tên vùng và offset gốc **không được giữ lại** trong cột. `TIMESTAMP WITHOUT TIME ZONE` giữ các thành phần ngày giờ và không gắn múi giờ.
- **MySQL**: `TIMESTAMP` có chuyển đổi liên quan đến múi giờ của session khi ghi/đọc, còn `DATETIME` giữ các thành phần ngày giờ. Phạm vi giá trị của `TIMESTAMP` và cấu hình múi giờ phải được xem xét theo phiên bản máy chủ/driver.
- **SQL Server**: `datetimeoffset` lưu ngày giờ cùng offset, nhưng offset đó không thay thế được tên vùng và quy tắc đổi giờ trong tương lai.
- **SQLite**: thường chọn cách lưu theo chuỗi ISO 8601 chuẩn hóa, số epoch hoặc quy ước ứng dụng; cần thống nhất cả định dạng lẫn cách phân giải khi đọc.

Không giả định driver của DB A sẽ xử lý `setTimestamp`, `getTimestamp` hoặc `setObject` giống DB B. Những ví dụ tiếp theo dùng **PostgreSQL với driver JDBC tương thích**; tại đây `OffsetDateTime` là đường đi rõ ràng để đọc/ghi `TIMESTAMPTZ`.

## 4. Thiết kế schema minh bạch

Ví dụ, hệ thống quản lý lịch hẹn cần vừa tìm kiếm cuộc hẹn theo thời điểm thực tế, vừa giữ nguyên lựa chọn giờ địa phương của khách.

```sql
-- PostgreSQL
CREATE TABLE appointments (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    starts_at    TIMESTAMP WITH TIME ZONE NOT NULL,
    starts_local TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    zone_id      VARCHAR(64) NOT NULL,
    created_at   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_appointments_starts_at
    ON appointments (starts_at);
```

Ở đây:

- `starts_at` và `created_at` dùng để sắp xếp, lọc theo dòng thời gian.
- `starts_local` và `zone_id` ghi lại mong muốn đặt lịch. Cơ sở dữ liệu không tự kiểm chứng một chuỗi là Zone ID hợp lệ; tầng Java phải xác thực.
- Index trên `starts_at` phục vụ điều kiện so sánh trực tiếp. Nếu thường lọc lịch theo ngày ghi trên đồng hồ ở **mỗi** vùng, có thể cần thêm index `(zone_id, starts_local)`; đó là truy vấn khác với lọc theo ngày của một vùng đã biết.
- `CURRENT_TIMESTAMP` được DB cấp; trong PostgreSQL giá trị này cố định theo thời điểm bắt đầu transaction. Nếu cần thời điểm đồng hồ tại từng lệnh, phải chọn chính sách khác một cách có chủ đích.

Nếu nghiệp vụ chỉ cần log thời điểm phát sinh, chỉ cần **một** cột kiểu `TIMESTAMPTZ`; không tạo các cột `local` và `zone_id` cho mọi bảng một cách máy móc. Nếu nghiệp vụ cần đặt lịch **lặp**, không thể thay thế “08:00 mỗi ngày tại vùng X” bằng một instant cố định. Hãy lưu quy tắc và tính các lần xảy ra riêng biệt.

## 5. Ghi, đọc và phân giải thời gian bằng `PreparedStatement`

Ví dụ sau dùng `DataSource` lấy `Connection`, gửi tham số đúng kiểu và đóng tài nguyên với `try-with-resources`. Với PostgreSQL, lưu instant dưới dạng `OffsetDateTime` có offset UTC, sau đó đọc lại và chuyển sang `Instant`. Hàm `resolveStrict` xử lý rõ các trường hợp đổi giờ mùa hè.

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
import java.time.ZonedDateTime;
import java.util.List;
import javax.sql.DataSource;

public final class AppointmentJdbc {
    private AppointmentJdbc() {}

    // requestedOffset = null chỉ được phép khi giờ địa phương là duy nhất.
    public static Instant resolveStrict(
            LocalDateTime local, ZoneId zone, ZoneOffset requestedOffset) {
        List<ZoneOffset> valid = zone.getRules().getValidOffsets(local);
        if (valid.isEmpty()) {
            throw new IllegalArgumentException(
                    "Giờ địa phương không tồn tại trong vùng: " + local);
        }
        if (valid.size() > 1 && requestedOffset == null) {
            throw new IllegalArgumentException(
                    "Giờ địa phương bị lặp; cần chọn offset: " + local);
        }
        ZoneOffset selected = requestedOffset == null
                ? valid.get(0) : requestedOffset;
        if (!valid.contains(selected)) {
            throw new IllegalArgumentException("Offset không hợp lệ cho giờ đã chọn");
        }
        return ZonedDateTime.ofStrict(local, selected, zone).toInstant();
    }

    public static void insert(
            DataSource dataSource,
            LocalDateTime local,
            ZoneId zone,
            ZoneOffset requestedOffset) throws SQLException {
        Instant start = resolveStrict(local, zone, requestedOffset);
        String sql = "INSERT INTO appointments " +
                "(starts_at, starts_local, zone_id) VALUES (?, ?, ?)";
        try (Connection con = dataSource.getConnection();
             PreparedStatement ps = con.prepareStatement(sql)) {
            ps.setObject(1, OffsetDateTime.ofInstant(start, ZoneOffset.UTC));
            ps.setObject(2, local);
            ps.setString(3, zone.getId());
            ps.executeUpdate();
        }
    }

    public static Instant loadStartInstant(
            DataSource dataSource, long id) throws SQLException {
        String sql = "SELECT starts_at FROM appointments WHERE id = ?";
        try (Connection con = dataSource.getConnection();
             PreparedStatement ps = con.prepareStatement(sql)) {
            ps.setLong(1, id);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException("Không tìm thấy lịch hẹn: " + id);
                }
                OffsetDateTime value =
                        rs.getObject("starts_at", OffsetDateTime.class);
                return value.toInstant();
            }
        }
    }
}
```

Cách gọi với giờ không nhập nhằng:

```java
LocalDateTime local = LocalDateTime.of(2026, 11, 18, 9, 0);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
AppointmentJdbc.insert(dataSource, local, zone, null);
// Mốc đã lưu là 2026-11-18T02:00:00Z.
```

Khi cần đọc đủ ý định đặt lịch, truy vấn thêm `starts_local` bằng `rs.getObject("starts_local", LocalDateTime.class)` và `zone_id` bằng `rs.getString("zone_id")`; sau đó dùng `ZoneId.of(...)` để kiểm tra vùng. Không ép `LocalDateTime` từ DB thành `Instant` bằng múi giờ mặc định của JVM.

Một số driver cung cấp overload `setTimestamp(index, timestamp, utcCalendar)` và `getTimestamp(column, utcCalendar)` để chỉ định cách diễn giải timestamp khi dùng API `java.sql.Timestamp`. Chúng hữu ích với mã cũ nhưng cần kiểm thử cụ thể theo DB, kiểu cột và driver. Với API mới, nên ưu tiên kiểu `java.time` khớp ngữ nghĩa như ví dụ.

## 6. Truy vấn theo ngày địa phương bằng khoảng instant

Yêu cầu: “Lấy tất cả cuộc hẹn diễn ra trong **ngày 17/11/2026 tại TP.HCM**.” Đây không phải ngày UTC, và một ngày địa phương không nhất thiết dài 24 giờ ở mọi vùng.

Quy trình đúng khi đã biết vùng cần xét:

1. Tạo `LocalDate` cho ngày người dùng hỏi và `ZoneId` của nghiệp vụ.
2. Tính **đầu ngày** và **đầu ngày kế tiếp** trong vùng đó.
3. Chuyển hai ranh giới thành `Instant` rồi truy vấn `[start, end)`: từ bắt đầu **bao gồm**, đến kết thúc **không bao gồm**.

```java
import java.sql.*;
import java.time.*;
import javax.sql.DataSource;

public static void printAppointmentsOnDay(
        DataSource dataSource, LocalDate day, ZoneId zone)
        throws SQLException {
    Instant from = day.atStartOfDay(zone).toInstant();
    Instant until = day.plusDays(1).atStartOfDay(zone).toInstant();

    String sql = "SELECT id, starts_at FROM appointments " +
                 "WHERE starts_at >= ? AND starts_at < ? " +
                 "ORDER BY starts_at, id";

    try (Connection con = dataSource.getConnection();
         PreparedStatement ps = con.prepareStatement(sql)) {
        ps.setObject(1, OffsetDateTime.ofInstant(from, ZoneOffset.UTC));
        ps.setObject(2, OffsetDateTime.ofInstant(until, ZoneOffset.UTC));
        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                long id = rs.getLong("id");
                Instant at = rs.getObject(
                        "starts_at", OffsetDateTime.class).toInstant();
                System.out.println(id + " | " + at.atZone(zone));
            }
        }
    }
}
```

Đoạn trên là **phương thức minh họa** cần đặt trong một lớp Java; các `import` nằm ở đầu file. Với ngày `2026-11-17` tại `Asia/Ho_Chi_Minh`, khoảng UTC là:

```text
from  = 2026-11-16T17:00:00Z (bao gồm)
until = 2026-11-17T17:00:00Z (không bao gồm)
```

Lưu ý quan trọng:

- Không dùng `BETWEEN start AND end` nếu mục tiêu là khoảng `[start, end)`: `BETWEEN` bao gồm cả hai đầu, dễ đếm trùng sự kiện đúng tại midnight của ngày hôm sau.
- Không đặt điểm cuối là `23:59:59.999`. Độ chính xác cột SQL có thể là micro giây, khiến một số bản ghi sau mốc `.999` bị bỏ sót.
- Tránh `WHERE DATE(starts_at) = ?` cho truy vấn chính: việc chuyển sang ngày có thể phụ thuộc vùng của session PostgreSQL và việc bọc hàm quanh cột có thể làm mất lợi thế index thông thường. Hãy tính biên trong Java và so sánh trực tiếp với `starts_at`.
- Ngày ở vùng có chuyển DST có thể dài 23 hoặc 25 giờ. `day.plusDays(1).atStartOfDay(zone)` phản ánh quy tắc của vùng; **không** lấy `from.plus(Duration.ofHours(24))`.
- Nếu câu hỏi là “lịch hẹn có **ngày địa phương đã đăng ký** là X tại chính chi nhánh của từng lịch hẹn”, đó là truy vấn theo `starts_local` và có thể theo `zone_id`, không phải một khoảng instant của một vùng cố định. Cần phân biệt hai yêu cầu ngay trong đặc tả.

## 7. Giờ không tồn tại và giờ bị lặp khi đổi DST

`LocalDateTime` + `ZoneId` **không phải lúc nào cũng đủ** để có đúng một `Instant`. Thư viện `java.time` cho phép kiểm tra danh sách offset hợp lệ tại giờ địa phương bằng `zone.getRules().getValidOffsets(local)`.

| Tình huống tại `America/New_York` | Offset hợp lệ | Ý nghĩa |
| --- | --- | --- |
| `2026-03-08 02:30` | Không có | Đồng hồ nhảy qua khoảng 02:00–03:00; 02:30 **không tồn tại** |
| `2026-11-01 01:30` | `-04:00` và `-05:00` | Đồng hồ lùi lại; 01:30 xảy ra **hai lần**, hai instant cách nhau 1 giờ |
| `2026-11-17 09:00` | Một offset | Có thể xác định một instant |

Trong ví dụ `resolveStrict`:

- Trường hợp không có offset: từ chối đầu vào để người dùng chọn giờ khác. Ứng dụng khác có thể chọn chính sách tự đẩy lên giờ hợp lệ tiếp theo, nhưng phải ghi rõ và kiểm thử.
- Trường hợp có hai offset: yêu cầu chỉ rõ offset nào được chọn hoặc áp dụng một quy tắc nghiệp vụ có thể giải thích và tái hiện. Hàm minh họa từ chối khi chưa được chọn.
- Trường hợp có một offset: dùng `ZonedDateTime.ofStrict` để kiểm tra sự tương thích giữa giờ địa phương, offset và vùng.

Với lịch lặp, hãy giữ quy tắc “08:00 mỗi ngày ở `America/New_York`” dưới dạng `LocalTime` + `ZoneId` + thông tin tần suất, rồi tính riêng từng kỳ. Nếu chỉ lưu một instant và cộng `Duration.ofDays(1)` cho các kỳ sau, thời điểm trên đồng hồ có thể chuyển thành 07:00 hoặc 09:00 khi đổi DST.

Quy tắc vùng thời gian thay đổi theo quyết định của các quốc gia. Hệ thống chạy lâu năm cần quy trình cập nhật tzdb của JDK, cập nhật dữ liệu múi giờ trên DB nếu có sử dụng và kiểm tra lại các lịch tương lai; ghi rõ lịch nào được phép tính lại instant.

## 8. Làm cho cơ sở dữ liệu, driver và ứng dụng nhất quán

Ngay cả khi đã chọn kiểu cột đúng, còn các nguồn sai lệch sau:

| Nguồn sai lệch | Cách kiểm soát |
| --- | --- |
| Múi giờ mặc định của JVM hoặc container | Không dùng mặc định ngầm khi chuyển giữa `LocalDateTime` và instant; truyền `ZoneId` rõ ràng |
| `TimeZone` của phiên kết nối DB | Cấu hình nhất quán cho connection pool; với PostgreSQL có thể dùng UTC khi hiển thị và vận hành, nhưng nhớ `TIMESTAMPTZ` vẫn chỉ lưu instant |
| Driver JDBC và SQL dialect | Chạy kiểm thử ghi–đọc bằng **cùng** bản driver, DB và kiểu cột thực tế trong production |
| Chuỗi ngày giờ không ghi offset | API yêu cầu định dạng có `Z`/offset cho instant; dữ liệu ngày giờ địa phương đi kèm Zone ID |
| Độ chính xác khác nhau | Quy ước mức chính xác và kiểm tra hành vi làm tròn/cắt của DB; không mặc định nanosecond của `Instant` được lưu nguyên vẹn |
| Nhiều đồng hồ sinh timestamp | Quy định DB hay ứng dụng làm nguồn cho từng trường; đồng bộ đồng hồ, dùng `Clock` truyền vào code cần kiểm thử |

Trong PostgreSQL có thể kiểm tra múi giờ phiên SQL bằng:

```sql
SHOW TIME ZONE;

-- Lệnh này tác động đến cách phiên hiện tại hiển thị/diễn giải thời gian.
SET TIME ZONE 'UTC';
```

Với connection pool, không coi việc chạy `SET TIME ZONE` trên **một** connection là cấu hình toàn ứng dụng. Cần cấu hình mỗi connection được cấp hoặc thiết lập phía DB một cách thích hợp, đặc biệt nếu nhiều người dùng cùng chia sẻ pool. Cũng không dùng thiết lập session để thay cho dữ liệu `zone_id` của nghiệp vụ.

Giá trị `Instant` trong Java có độ chính xác đến nanosecond, còn `TIMESTAMPTZ` của PostgreSQL thường lưu đến microsecond. Nếu nghiệp vụ cần đối chiếu chính xác sau khi ghi–đọc, hãy chọn chính sách chuẩn hóa, ví dụ cắt về microsecond ở biên ghi bằng `instant.truncatedTo(ChronoUnit.MICROS)`, đồng thời kiểm thử DB có làm tròn hay không. Không so sánh các timestamp bằng chuỗi trình bày hoặc giả định độ chính xác không giới hạn.

## 9. Những lỗi thiết kế thường gặp

| Cách làm dễ lỗi | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Lưu mọi thứ thành `VARCHAR` hay timestamp “không vùng” | Chuyển đổi và sắp xếp phụ thuộc định dạng/quy ước không được bảo vệ | Dùng kiểu SQL mang đúng nghĩa, hợp đồng serialize rõ ràng |
| Lưu `LocalDateTime.now()` vào cột được hiểu là UTC | Giờ địa phương của máy có thể bị coi thành UTC và lệch nhiều giờ | Dùng `Instant.now(clock)` cho instant; chuyển qua binding có offset rõ ràng |
| Dùng offset cố định thay Zone ID cho lịch tương lai | Sai khi vùng đổi DST hoặc quy định quốc gia | Lưu Zone ID IANA và giờ địa phương đã chọn |
| Đọc `TIMESTAMP WITHOUT TIME ZONE` rồi gán múi giờ mặc định máy | Kết quả đổi khi deploy sang máy khác | Khôi phục bằng vùng nghiệp vụ được lưu rõ ràng |
| Lấy ngày bằng cách chuyển instant sang UTC rồi `toLocalDate()` | Người dùng ở các vùng thấy ngày không đúng ý nghĩa nghiệp vụ | Chuyển bằng `instant.atZone(businessZone).toLocalDate()` |
| Truy vấn đến `23:59:59.999` | Bỏ sót bản ghi có độ chính xác cao hơn | Dùng khoảng nửa mở `[start, nextStart)` |
| Xây SQL bằng nối chuỗi timestamp | Nguy cơ lỗi parse, locale và SQL injection | Dùng `PreparedStatement` với tham số có kiểu |
| Dùng `java.util.Date`/`java.sql.Timestamp` tùy tiện | Dễ lẫn instant và ngày giờ địa phương; conversion phụ thuộc môi trường | Ưu tiên `java.time` và kiểm tra binding driver |
| Giả định timestamp đủ đảm bảo thứ tự tuyệt đối | Hai bản ghi có thể trùng timestamp do độ chính xác hoặc nhiều nguồn ghi | Thêm khóa định danh/sequence nếu cần thứ tự xác định |

Một ví dụ SQL không nên dùng cho truy vấn theo ngày của vùng đã biết:

```sql
-- Kết quả phụ thuộc ngữ cảnh chuyển ngày và dễ cản trở index.
SELECT * FROM appointments
WHERE DATE(starts_at) = DATE '2026-11-17';
```

Nên dùng khoảng instant do ứng dụng tính, binding bằng `PreparedStatement` như mục 6.

## 10. Kiểm thử hợp đồng thời gian

Kiểm thử bằng driver và DB thật có giá trị cao hơn chỉ mock `ResultSet`, vì phần khó thường nằm trong chuyển đổi kiểu JDBC và cấu hình phiên. Một bộ kiểm tra nên bao gồm:

1. **Round-trip**: lưu `OffsetDateTime` UTC vào `TIMESTAMPTZ`, đọc qua `getObject(..., OffsetDateTime.class)`, so sánh `toInstant()` sau khi tính đến độ chính xác DB.
2. **Thay đổi vùng máy và session**: cùng một instant phải trả về cùng `Instant` dù JVM chạy ở UTC hay `Asia/Ho_Chi_Minh`, hoặc session DB hiển thị ở vùng khác.
3. **Ranh giới ngày**: dữ liệu đúng tại `from` phải được lấy, đúng tại `until` phải bị loại. Kiểm tra các ngày 23/25 giờ tại vùng có DST.
4. **DST gap/overlap**: giờ không tồn tại phải đi theo chính sách đã định; giờ trùng phải xác định offset được chọn.
5. **Độ chính xác**: các giá trị có phần microsecond/nanosecond phải được xử lý nhất quán; không viết assertion bình đẳng tuyệt đối vượt quá độ phân giải DB.
6. **Transaction**: khi đổi lịch hẹn, `starts_at`, `starts_local` và `zone_id` phải cùng được cập nhật hoặc rollback; cố tình gây lỗi giữa thao tác để kiểm chứng tính nhất quán.
7. **Lịch tương lai sau thay đổi quy tắc múi giờ**: xác nhận hệ thống giữ giờ địa phương hay giữ instant theo chính sách đã tài liệu hóa.

Ví dụ tự kiểm tra chiều dài ngày theo quy tắc múi giờ:

```java
ZoneId newYork = ZoneId.of("America/New_York");

LocalDate spring = LocalDate.of(2026, 3, 8);
long springHours = Duration.between(
        spring.atStartOfDay(newYork).toInstant(),
        spring.plusDays(1).atStartOfDay(newYork).toInstant()).toHours();
// springHours == 23

LocalDate autumn = LocalDate.of(2026, 11, 1);
long autumnHours = Duration.between(
        autumn.atStartOfDay(newYork).toInstant(),
        autumn.plusDays(1).atStartOfDay(newYork).toInstant()).toHours();
// autumnHours == 25
```

Đây cũng là lý do `LocalDate` và `ZoneId` nên được đưa vào hàm truy vấn theo ngày ngay từ đầu, thay vì nhận một chuỗi ngày rồi tự cộng 86.400 giây.

## 11. Bài tập áp dụng

Một hệ thống cần lưu:

- Thời điểm khách bấm nút đặt lịch.
- Lịch hẹn 09:00 tại `Asia/Ho_Chi_Minh` vào ngày 18/11/2026.
- Quy tắc gửi thông báo lúc 08:00 mỗi ngày theo vùng của khách.
- Ngày sinh của khách.

Hãy chọn các cột SQL, kiểu Java, nguồn giá trị và điều kiện truy vấn phù hợp. Một thiết kế tham khảo:

| Dữ liệu | Java và SQL | Quy ước |
| --- | --- | --- |
| Bấm nút đặt lịch | `Instant` → `TIMESTAMPTZ` | Instant UTC; nêu rõ do server hay DB ghi nhận |
| Lịch hẹn 09:00 | `LocalDateTime + ZoneId` → `starts_local + zone_id`; thêm instant `starts_at` | Xác thực DST, ghi atomically, quyết định quy tắc cập nhật lịch tương lai |
| Thông báo mỗi ngày 08:00 | `LocalTime + ZoneId` + thông tin lặp | Không biểu diễn lịch lặp bằng một instant duy nhất; tính từng lần chạy |
| Ngày sinh | `LocalDate` → `DATE` | Không tạo offset/múi giờ giả |

Khi triển khai một bảng hoặc API thời gian mới, hãy tự hỏi: **“Giá trị này là một thời điểm trên dòng thời gian, một ngày theo lịch, hay một giờ trên đồng hồ ở một vùng?”** Nếu câu trả lời được ghi trong schema, code, hợp đồng API và test thì JDBC chỉ còn nhiệm vụ truyền đúng giá trị giữa các lớp, không phải đoán ý nghĩa của nó.

# Toàn cảnh java.time và các API ngày giờ cũ trong Java

> Phạm vi: Java Core, nhóm **Tổng quan**. Bài học này giúp chọn đúng kiểu dữ liệu ngày giờ, hiểu múi giờ và dòng thời gian, dùng API **java.time** từ Java 8 (ví dụ chạy với Java 17+), đồng thời nhận diện và chuyển đổi các API cũ khi bảo trì hệ thống.

## 1. Vì sao Java có nhiều API ngày giờ?

Một giá trị “ngày giờ” có thể trả lời các câu hỏi khác nhau:

- **Ngày theo lịch**: sinh nhật 24/10, ngày đáo hạn, ngày nghỉ; chưa cần xác định một thời điểm toàn cầu.
- **Giờ theo đồng hồ địa phương**: cửa hàng mở 08:30; riêng con số này không cho biết ngày hay múi giờ.
- **Ngày và giờ địa phương**: cuộc họp lúc 09:00 ngày 25/10/2026; cần biết diễn ra ở đâu mới quy ra thời điểm thực.
- **Một thời điểm thực trên dòng thời gian**: lúc một sự kiện được ghi nhận, có thể so sánh và sắp xếp dù các máy ở múi giờ khác nhau.
- **Khoảng thời gian trôi qua**: 90 phút hoặc 3600 giây; khác với “một tháng lịch” vì số ngày mỗi tháng khác nhau.

Các API ban đầu như **java.util.Date**, **Calendar** và **SimpleDateFormat** phát triển qua nhiều phiên bản, có thiết kế dễ gây nhầm lẫn, trạng thái có thể thay đổi và nhiều quy ước bất tiện. **java.time**, ra đời trong Java 8 theo JSR-310 và tiếp tục có trong Java 17+, tách các khái niệm thành kiểu riêng, phần lớn lớp là bất biến (immutable) và an toàn khi dùng chung giữa các luồng.

### Ba khái niệm nền tảng

1. **Instant**: mốc trên dòng thời gian UTC, ví dụ 2026-10-24T10:15:30Z. Chữ Z biểu thị offset UTC+00:00. Instant tự nó không chứa múi giờ địa phương.
2. **Offset**: độ lệch so với UTC ở một thời điểm, ví dụ +07:00. Offset chỉ là độ lệch, không chứa quy tắc chuyển giờ theo mùa hay lịch sử của khu vực.
3. **Time zone (ZoneId)**: vùng chứa tập quy tắc offset theo thời gian, ví dụ **Asia/Ho_Chi_Minh** hoặc **America/New_York**. Một ZoneId có thể dùng offset khác nhau ở những ngày khác nhau.

Cùng một Instant 2026-10-24T10:15:30Z được hiển thị tại TP.HCM là 17:15:30 ngày 24/10/2026. Đổi múi giờ hiển thị **không làm đổi Instant**. Trái lại, chuỗi “24/10/2026 17:15” đơn thuần chưa đủ xác định duy nhất một Instant nếu không cung cấp offset hoặc vùng thời gian và giải quyết các trường hợp giờ mùa hè.

## 2. Bản đồ các kiểu java.time: chọn đúng kiểu

| Kiểu | Ý nghĩa | Tình huống thích hợp | Điều không chứa |
| --- | --- | --- | --- |
| **LocalDate** | Năm, tháng, ngày theo lịch ISO | Sinh nhật, ngày đến hạn, ngày giao hàng | Giờ, offset, zone |
| **LocalTime** | Giờ, phút, giây, nano | Giờ mở cửa, giờ báo thức theo lịch | Ngày, offset, zone |
| **LocalDateTime** | Ngày + giờ địa phương | Giờ hẹn tại địa điểm đã biết; dữ liệu SQL TIMESTAMP không có zone | Offset, zone; không tự là Instant |
| **Instant** | Một mốc trên dòng thời gian | Timestamp tạo/sửa bản ghi, sự kiện, log, token hết hạn | Giờ địa phương, zone |
| **OffsetDateTime** | LocalDateTime + UTC offset | Trao đổi thời điểm có offset qua API | Quy tắc vùng như America/New_York |
| **ZonedDateTime** | Ngày giờ + ZoneId và offset đã xác định | Cuộc họp theo vùng, tính lịch qua DST | Không phải một quy tắc lặp lịch tự thân |
| **ZoneId** | Định danh và quy tắc múi giờ | Hiển thị theo khu vực người dùng, lịch hẹn | Không phải timestamp |
| **ZoneOffset** | Offset cố định như +07:00 | Giao thức có offset, quy đổi UTC | Không chứa lịch sử DST của vùng |
| **Duration** | Thời lượng dựa trên giây/nano | Timeout, thời gian chạy, khoảng cách giữa hai Instant | Tháng/năm lịch |
| **Period** | Số năm/tháng/ngày theo lịch | Cộng một tháng, tuổi theo ngày, kỳ hạn lịch | Giờ/phút/giây thực trôi qua |
| **YearMonth**, **MonthDay** | Tháng-năm; ngày-tháng | Kỳ báo cáo tháng; ngày kỷ niệm lặp hằng năm | Thông tin còn lại |
| **Clock** | Nguồn thời gian có thể thay thế | Lấy giờ hiện tại trong logic nghiệp vụ và kiểm thử | Không phải ngày giờ lưu trữ |
| **DateTimeFormatter** | Quy tắc parse/format | Định dạng đầu vào/đầu ra, API, giao diện | Không lưu thời điểm |

**Quy tắc chọn nhanh:**

- Cần lưu **sự kiện đã xảy ra lúc nào**: ưu tiên **Instant**; đổi sang **ZonedDateTime** ở biên hiển thị.
- Cần lưu **ngày nghiệp vụ** (không gắn giờ): **LocalDate**.
- Cần lưu **cuộc hẹn 09:00 mỗi ngày tại một vùng**: lưu **LocalTime** + **ZoneId** (và quy tắc ngày lặp); khi đến một ngày cụ thể mới tạo thời điểm.
- Cần gửi **ngày giờ kèm offset**: **OffsetDateTime** hoặc chuỗi ISO 8601 có offset; muốn tái dựng đúng vùng lịch hẹn, lưu thêm **ZoneId**.
- **LocalDateTime** thích hợp để mô tả giờ trên lịch địa phương, nhưng không phù hợp nếu định dùng nó như timestamp toàn cầu.

## 3. Khởi tạo, biến đổi, so sánh

Các factory method giúp code diễn đạt rõ ý:

~~~java
LocalDate date = LocalDate.of(2026, 10, 24);
LocalTime time = LocalTime.of(9, 30);
LocalDateTime meeting = LocalDateTime.of(date, time);
Instant timestamp = Instant.parse("2026-10-24T10:15:30Z");
ZoneId region = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime inVietnam = timestamp.atZone(region);
OffsetDateTime withOffset = inVietnam.toOffsetDateTime();
~~~

Đây là **đoạn trích minh họa**: muốn biên dịch riêng cần đặt trong phương thức và import các lớp từ java.time.

- **plusDays**, **minusWeeks**, **plusMonths**, **withDayOfMonth** trả về **đối tượng mới**, không sửa bản gốc. Nếu gọi date.plusDays(1) mà không gán hoặc sử dụng kết quả, date không đổi.
- **isBefore**, **isAfter**, **isEqual** so sánh các giá trị phù hợp; **equals** của ZonedDateTime còn xét thông tin ngày giờ/zone. Để so **cùng thời điểm toàn cầu** từ hai ZonedDateTime khác vùng, dùng **toInstant().equals(...)** hoặc **isEqual(...)**.
- **plusMonths(1)** theo tháng lịch: 31/01/2026 cộng một tháng thành 28/02/2026, không phải cộng số giây của 30 ngày.
- **TemporalAdjusters.lastDayOfMonth()** và các adjuster khác giúp biểu diễn chính sách lịch mà không tự đếm ngày tháng.

Không tự chuyển LocalDateTime thành Instant bằng cách coi nó mặc nhiên ở UTC. Phải có **ZoneId/ZoneOffset** do nghiệp vụ xác định, ví dụ **meeting.atZone(region).toInstant()**; tại ranh giới giờ mùa hè, cần xem xét thêm các quy tắc ở mục 6.

## 4. Ví dụ Java 17+ chạy độc lập

Tạo tệp **DateTimeOverview.java**:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.time.temporal.TemporalAdjusters;

public class DateTimeOverview {
    public static void main(String[] args) {
        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
        Clock fixedClock = Clock.fixed(
                Instant.parse("2026-10-24T00:00:00Z"), vietnam);

        LocalDate today = LocalDate.now(fixedClock);
        LocalDate dueDate = today.plusMonths(1)
                .with(TemporalAdjusters.lastDayOfMonth());

        Instant event = Instant.parse("2026-10-24T10:15:30Z");
        ZonedDateTime localEvent = event.atZone(vietnam);
        DateTimeFormatter display =
                DateTimeFormatter.ofPattern("dd/MM/uuuu HH:mm VV");

        DateTimeFormatter strictDate =
                DateTimeFormatter.ofPattern("dd/MM/uuuu")
                        .withResolverStyle(ResolverStyle.STRICT);
        LocalDate parsed = LocalDate.parse("31/12/2026", strictDate);

        long elapsedMinutes = Duration.between(
                event, event.plusSeconds(5_400)).toMinutes();

        System.out.println("Hôm nay: " + today);
        System.out.println("Hạn: " + dueDate);
        System.out.println("Giờ địa phương: " + localEvent.format(display));
        System.out.println("Ngày đọc: " + parsed);
        System.out.println("Phút trôi qua: " + elapsedMinutes);
    }
}
~~~

Biên dịch/chạy với JDK 17+ (terminal có hỗ trợ UTF-8 để hiển thị tiếng Việt):

~~~bash
javac -encoding UTF-8 DateTimeOverview.java
java DateTimeOverview
~~~

Kết quả chuẩn:

~~~text
Hôm nay: 2026-10-24
Hạn: 2026-11-30
Giờ địa phương: 24/10/2026 17:15 Asia/Ho_Chi_Minh
Ngày đọc: 2026-12-31
Phút trôi qua: 90
~~~

Vì sử dụng **Clock.fixed**, đầu ra không phụ thuộc vào ngày chạy hay đồng hồ máy. Giờ 10:15Z chuyển thành 17:15 theo vùng Việt Nam; ngày đến hạn là ngày cuối tháng tiếp theo. **Duration** đo 5400 giây = 90 phút; **LocalDate** và **Period** phù hợp hơn khi đề bài tính theo lịch.

## 5. Parse, format và xác thực dữ liệu

**DateTimeFormatter** bất biến và thread-safe; có thể dùng lại như hằng số. Ưu tiên ISO 8601 ở ranh giới hệ thống:

- **DateTimeFormatter.ISO_LOCAL_DATE** cho 2026-10-24.
- **DateTimeFormatter.ISO_INSTANT** cho 2026-10-24T10:15:30Z.
- **DateTimeFormatter.ISO_OFFSET_DATE_TIME** cho chuỗi mang offset, ví dụ 2026-10-24T17:15:30+07:00.
- Mẫu tùy chỉnh, như **dd/MM/uuuu**, phục vụ cách hiển thị cho người dùng. Có thể chỉ định Locale khi dùng tên tháng hoặc thứ.

Các ký hiệu rất dễ lẫn:

| Pattern | Ý nghĩa | Lỗi thường gặp |
| --- | --- | --- |
| **uuuu** | Năm proleptic theo hệ ISO | Khi parse STRICT dữ liệu thường dùng uuuu thay vì yyyy (year-of-era) thiếu era |
| **MM** | Tháng | **mm** là phút |
| **dd** | Ngày trong tháng | **DD** là ngày trong năm |
| **HH** | Giờ 0–23 | **hh** là giờ 1–12, cần AM/PM |
| **XXX** | Offset theo dạng +07:00 | Offset không thay thế ZoneId vùng |
| **VV** | ZoneId | Chỉ format khi giá trị có zone phù hợp |

Khi nhận ngày từ người dùng, xác định rõ pattern/Locale, parse với **ResolverStyle.STRICT** khi cần từ chối ngày không tồn tại (như 31/02), xử lý **DateTimeParseException**, và báo lỗi trường nhập. Không suy ra timezone của dữ liệu chỉ từ định dạng văn bản. Nếu API truyền timestamp, yêu cầu chuỗi có Z hoặc offset và parse về Instant/OffsetDateTime.

## 6. Time zone, DST và hai loại phép cộng khác nhau

Múi giờ theo vùng phụ thuộc bộ quy tắc lịch sử (tzdb), trong khi offset chỉ là một số. Đặc biệt tại vùng có **daylight saving time (DST)**:

- **Gap**: có những giờ địa phương không tồn tại vì đồng hồ nhảy tiến. Ví dụ ở **America/New_York**, 02:30 ngày 08/03/2026 rơi vào khoảng nhảy giờ. Khi giải LocalDateTime bằng **atZone**, Java thường đẩy giờ không hợp lệ tiến qua gap.
- **Overlap**: có giờ địa phương xuất hiện hai lần khi đồng hồ lùi. Ví dụ 01:30 ngày 01/11/2026 tại New York ứng với hai offset; atZone thông thường chọn offset sớm hơn theo quy tắc mặc định. Nếu yêu cầu phân biệt tuyệt đối, phải cung cấp offset/Instant hoặc kiểm tra **ZoneRules.getValidOffsets(localDateTime)** và xử lý lựa chọn.
- **Một ngày lịch không luôn bằng 24 giờ thực**. **plusDays(1)** của ZonedDateTime tuân theo lịch địa phương; **plusHours(24)** dịch 24 giờ trên timeline. Qua ngày bắt đầu DST, hai kết quả có thể chênh một giờ trên đồng hồ.

Minh họa độc lập, các lệnh sau giả sử đặt trong một phương thức và đã import java.time:

~~~java
ZoneId newYork = ZoneId.of("America/New_York");
ZonedDateTime noon = ZonedDateTime.of(
        2026, 3, 7, 12, 0, 0, 0, newYork);
System.out.println(noon.plusDays(1));
// 2026-03-08T12:00-04:00[America/New_York]
System.out.println(noon.plusHours(24));
// 2026-03-08T13:00-04:00[America/New_York]
~~~

Đối với lịch lặp theo giờ địa phương, lưu **giờ + vùng + quy tắc lặp**; tính lần diễn ra tiếp theo dựa trên ngày và xử lý gap/overlap theo chính sách nghiệp vụ. Không cố định +07:00/+01:00 cho những vùng có quy tắc chuyển đổi theo thời gian. Luôn kiểm thử những ngày chuyển giờ của các vùng thực sự hỗ trợ.

## 7. Duration, Period và phép tính ngày

**Duration** biểu diễn giây và nano, thường áp dụng giữa hai Instant (hoặc kiểu temporal phù hợp). **Period** biểu diễn năm/tháng/ngày theo lịch, thường áp dụng giữa LocalDate.

~~~java
Instant start = Instant.parse("2026-10-24T00:00:00Z");
Instant end = start.plusSeconds(3_600);
Duration elapsed = Duration.between(start, end); // PT1H

LocalDate birth = LocalDate.of(2000, 10, 24);
LocalDate reference = LocalDate.of(2026, 10, 24);
Period age = Period.between(birth, reference);     // P26Y
~~~

Đây là các đoạn trích có thể đưa vào phương thức sau khi import java.time.

Nếu hỏi **bao nhiêu ngày trọn theo lịch** giữa hai ngày, dùng **ChronoUnit.DAYS.between(date1, date2)**. Nếu hỏi **bao nhiêu giờ đã trôi qua** giữa hai thời điểm, dùng **Duration.between(instant1, instant2)**. **Period.getDays()** chỉ trả thành phần *ngày* của Period (không phải tổng số ngày gồm năm và tháng): ví dụ khoảng 1 tháng 6 ngày có getDays() là 6.

Nên định nghĩa rõ quy tắc biên của khoảng thời gian. Với khoảng sự kiện, dạng **[start, end)** (bao gồm đầu, loại trừ cuối) thường giúp các khoảng liên tiếp không chồng biên; kiểm tra **!time.isBefore(start) && time.isBefore(end)** cho Instant.

## 8. API cũ: lịch sử, giới hạn và cách đối chiếu

| API cũ | Thực chất / vấn đề | Tương ứng hiện đại |
| --- | --- | --- |
| **java.util.Date** | Gắn với một mốc thời gian chính xác đến millisecond; mutable; **toString()** hiển thị theo zone mặc định của máy, không có nghĩa Date “lưu timezone” | **Instant** |
| **java.util.Calendar**, **GregorianCalendar** | Quản lý các trường ngày-giờ + TimeZone; mutable, nhiều quy tắc ngầm; **Calendar.JANUARY = 0** | **ZonedDateTime** / **LocalDate** tùy nhu cầu |
| **java.text.SimpleDateFormat** | Parse/format dựa trên pattern, **mutable và không thread-safe**; mặc định có thể parse lenient | **DateTimeFormatter** |
| **java.sql.Date** | Đại diện SQL DATE (ngày, không thời gian) | **LocalDate** |
| **java.sql.Time** | Đại diện SQL TIME (giờ, không ngày) | **LocalTime** |
| **java.sql.Timestamp** | Timestamp JDBC có phần nano; ngữ nghĩa timezone phụ thuộc kiểu SQL/driver | **LocalDateTime**, **Instant** hoặc **OffsetDateTime** tùy cột và hợp đồng |
| **System.currentTimeMillis()** | Số millisecond từ Unix epoch; tiện ở API hệ thống nhưng dễ mất ngữ nghĩa kiểu | **Instant.now(clock)** |

**Lưu ý thực tế với Calendar:** tháng của Calendar là 0–11, còn LocalDate dùng tháng 1–12. Lấy trường **Calendar.HOUR** (12 giờ) khác với **Calendar.HOUR_OF_DAY** (24 giờ); Calendar và SimpleDateFormat có cấu hình lenient và trạng thái thay đổi. Tránh để nhiều luồng dùng chung một instance SimpleDateFormat.

**Joda-Time** từng được dùng phổ biến trước Java 8. Với code mới trên Java 17+, ưu tiên java.time; với dự án cũ, chuyển từng ranh giới chức năng và xác nhận lại timezone, phép cộng ngày, format, quy tắc parse thay vì thay thế tên lớp máy móc.

### Chuyển đổi khi tích hợp với thư viện cũ

Những đoạn trích sau giả sử đã import java.time.*, java.util.Date, java.util.GregorianCalendar và java.sql.Timestamp; đặt chúng trong một phương thức:

~~~java
Instant instant = Instant.parse("2026-10-24T10:15:30Z");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

// java.util.Date lưu thời điểm, độ chính xác millisecond.
Date oldDate = Date.from(instant);
Instant backToInstant = oldDate.toInstant();

// GregorianCalendar giữ zone của đối tượng.
GregorianCalendar oldCalendar =
        GregorianCalendar.from(instant.atZone(zone));
ZonedDateTime restored = oldCalendar.toZonedDateTime();

// SQL DATE và TIME mang ý nghĩa ngày/giờ địa phương.
java.sql.Date sqlDate =
        java.sql.Date.valueOf(LocalDate.of(2026, 10, 24));
LocalDate fromSqlDate = sqlDate.toLocalDate();

java.sql.Time sqlTime =
        java.sql.Time.valueOf(LocalTime.of(9, 30));
LocalTime fromSqlTime = sqlTime.toLocalTime();

// Timestamp hỗ trợ đổi qua Instant; kiểm tra mapping DB/driver.
Timestamp sqlTimestamp = Timestamp.from(instant);
Instant fromTimestamp = sqlTimestamp.toInstant();
~~~

Phân biệt **java.util.Date** với **java.sql.Date** trong import. Đặc biệt, **java.sql.Date.toInstant()** và **java.sql.Time.toInstant()** **ném UnsupportedOperationException**: chúng không có đủ phần thời gian/ngày để tự xác định một Instant; hãy dùng **toLocalDate()** / **toLocalTime()** và chỉ gắn zone/date khi nghiệp vụ thật sự có thông tin đó. Chuyển từ java.time sang kiểu cũ có thể mất độ chính xác nano khi đích chỉ lưu millisecond.

Không dùng **new Date().getYear()**, **getMonth()**, **getDate()** và các constructor Date cũ: phần lớn đã deprecated và có các quy ước lệch (năm tính từ 1900, tháng bắt đầu bằng 0). Không dùng **SimpleDateFormat** làm trường static chia sẻ giữa nhiều thread; thay bằng **DateTimeFormatter**.

## 9. Tương tác với database, REST và hệ thống khác

**Thiết kế theo ngữ nghĩa dữ liệu trước khi chọn kiểu SQL**:

- Ngày sinh/ngày làm việc: SQL **DATE** ↔ **LocalDate**.
- Giờ mở cửa không phụ thuộc ngày: SQL **TIME** ↔ **LocalTime**.
- Ngày giờ tường minh không offset: SQL **TIMESTAMP** (without time zone) thường ↔ **LocalDateTime**, nhưng phải định nghĩa ý nghĩa ở ứng dụng.
- Timestamp sự kiện toàn cầu: ứng dụng dùng **Instant**; ở database chọn kiểu có ngữ nghĩa UTC/timezone rõ ràng, và xác minh driver, database, session zone. JDBC 4.2 hỗ trợ nhiều kiểu java.time; hỗ trợ **Instant**, **OffsetDateTime**, và cách xử lý SQL TIMESTAMP WITH TIME ZONE có thể khác nhau theo driver/database. Không giả định mọi database đều lưu ZoneId khu vực.

Đối với REST/JSON, thống nhất hợp đồng như **2026-10-24T10:15:30Z** cho sự kiện hoặc **2026-10-24** cho ngày thuần. Ghi rõ timezone trong API nếu gửi local date-time; tránh chuỗi mơ hồ **24/10/26 10:15**. Khi cần tái hiện lịch hẹn theo vùng, lưu **ZoneId** riêng vì offset ở ngày hôm nay có thể khác offset ngày diễn ra.

Múi giờ mặc định của JVM (**ZoneId.systemDefault()**) có thể đổi theo máy chủ/container/cấu hình. Chỉ dùng khi hệ thống chủ đích dựa trên môi trường; nếu logic cần vùng cụ thể, nhận ZoneId từ cấu hình/hợp đồng. Các quy tắc tzdb có thể được cập nhật qua JDK, nên ứng dụng lịch lâu dài cần chính sách khi chính phủ thay đổi luật giờ.

## 10. Thiết kế code dễ kiểm thử

Tránh gọi **Instant.now()**, **LocalDate.now()** rải rác trong logic khiến unit test phụ thuộc lúc chạy. Truyền **Clock** từ bên ngoài:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

public class ExpiryPolicy {
    private final Clock clock;

    public ExpiryPolicy(Clock clock) {
        this.clock = clock;
    }

    public boolean expired(Instant deadline) {
        return !Instant.now(clock).isBefore(deadline);
    }

    public LocalDate businessToday(ZoneId zone) {
        return LocalDate.now(clock.withZone(zone));
    }
}
~~~

Đây là **lớp biên dịch được** khi lưu thành ExpiryPolicy.java. Trong production có thể inject **Clock.systemUTC()**; trong unit test dùng **Clock.fixed(Instant.parse("2026-10-24T00:00:00Z"), ZoneId.of("UTC"))**. Nhờ vậy các phép tính ngày hôm nay và thời điểm hết hạn có thể tái lập chính xác. Với thời gian đo hiệu năng (elapsed monotonic time) ở một tiến trình, cân nhắc **System.nanoTime()** để đo khoảng chênh; nó không đại diện cho timestamp có thể lưu/trao đổi.

## 11. Những lỗi phổ biến cần tránh

1. **Dùng LocalDateTime làm timestamp UTC**: nó thiếu zone/offset, nên hai hệ thống có thể hiểu thành hai Instant khác nhau.
2. **Lưu giờ 09:00 như Instant để mô tả lịch lặp**: sau thay đổi DST, 09:00 theo đồng hồ địa phương có thể thành 08:00/10:00. Lưu quy tắc lịch + ZoneId.
3. **Trộn Period với Duration**: một ngày lịch qua chuyển DST có thể dài 23/25 giờ; một tháng không có số giây cố định.
4. **Dựa vào timezone mặc định** khi format/parse/log hoặc đổi từ LocalDateTime sang Instant.
5. **Nhầm MM và mm; yyyy và uuuu; HH và hh**, nhất là khi parse strict hoặc dùng năm trước Công nguyên.
6. **Nhầm java.util.Date và java.sql.Date**: tên giống nhau nhưng ý nghĩa và hỗ trợ toInstant khác nhau.
7. **Dùng SimpleDateFormat trong nhiều thread** hoặc giữ Calendar mutable dùng chung.
8. **Giả định offset cố định đại diện cho mọi vùng** hoặc không kiểm thử gap/overlap.
9. **So sánh chuỗi ngày giờ** thay vì parse thành kiểu dữ liệu phù hợp (đặc biệt khi thứ tự ngày/tháng tùy locale).
10. **Giữ nguyên nano khi đi qua Date/millisecond hoặc database** dù tầng lưu trữ đã mất độ chính xác.

## 12. Cách ra quyết định khi bảo trì hệ thống

Đối với từng trường dữ liệu, trả lời theo thứ tự:

1. Dữ liệu là **ngày trên lịch**, **giờ địa phương**, **ngày giờ địa phương**, **thời điểm toàn cầu**, hay **khoảng thời gian**?
2. Có cần **ZoneId khu vực** hay chỉ offset? Nếu lịch hẹn lặp, phải áp dụng quy tắc DST ra sao?
3. Khi serialise qua JSON/SQL, hợp đồng dữ liệu có giữ được nghĩa gốc không? Cột SQL/driver có ánh xạ phù hợp không?
4. Các phép tính cần theo **lịch** (Period, plusDays) hay theo **giây thực** (Duration, Instant)?
5. Test đã khóa **Clock**, timezone, các ngày cuối tháng, năm nhuận và các ca gap/overlap chưa?

### Tự luyện tập

- **Ngày sinh**: chọn LocalDate, không chọn Instant vì sinh nhật không phải một thời điểm UTC.
- **Thời điểm thanh toán thành công**: chọn Instant; format theo ZoneId ở màn hình người dùng.
- **Lịch chạy lúc 09:00 hằng ngày tại New York**: lưu LocalTime 09:00 + ZoneId America/New_York + quy tắc lặp; xác định từng Instant của lần chạy.
- **Timeout 30 giây**: dùng Duration.ofSeconds(30), không dùng Period.
- **Đọc dữ liệu java.util.Date cũ**: dùng toInstant() rồi chọn zone để hiển thị; đừng gán thẳng toString() vào API như chuỗi chuẩn.
- **Đọc java.sql.Date**: dùng toLocalDate(), không gọi toInstant().

## Tài liệu tham khảo

- [Oracle Java SE 17 — java.time package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html): mô hình Instant, LocalDate, LocalDateTime, ZonedDateTime.
- [Oracle Java SE 17 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html): pattern, resolver và tính thread-safe.
- [Oracle Java SE 17 — ZonedDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html): quy tắc zone và phép toán qua DST.
- [Oracle Java SE 17 — java.sql.Date](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Date.html): ánh xạ DATE và giới hạn của toInstant().

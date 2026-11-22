# Tách phần ngày và phần giờ từ LocalDateTime trong Java

`LocalDateTime` biểu diễn **ngày và giờ địa phương trong cùng một giá trị**, chẳng hạn `2025-04-09T14:30:45.123456789`. Khi một nghiệp vụ chỉ cần **ngày trên lịch** hoặc chỉ cần **giờ trên đồng hồ**, Java cung cấp hai thao tác trực tiếp:

~~~java
LocalDate date = dateTime.toLocalDate();
LocalTime time = dateTime.toLocalTime();
~~~

Kết quả là hai đối tượng độc lập về kiểu và ý nghĩa: `LocalDate` chứa năm–tháng–ngày; `LocalTime` chứa giờ–phút–giây–nanosecond trong giây. Cả ba kiểu đều thuộc `java.time`, bất biến và không chứa múi giờ hoặc offset UTC.

## 1. Hiểu dữ liệu trước khi tách

Ví dụ đầu vào:

~~~text
2025-04-09T14:30:45.123456789
└─ ngày ─┘ └───── giờ ───────┘
~~~

Trong cú pháp ISO-8601, `T` phân tách phần ngày và phần giờ. Từ giá trị này:

| Thành phần | Kiểu Java | Kết quả |
| --- | --- | --- |
| Ngày đầy đủ | `LocalDate` | `2025-04-09` |
| Giờ đầy đủ | `LocalTime` | `14:30:45.123456789` |
| Năm | `int` | `2025` |
| Tháng | `int` | `4` |
| Ngày trong tháng | `int` | `9` |
| Giờ trong ngày | `int` | `14` |
| Phút | `int` | `30` |
| Giây | `int` | `45` |
| Nanosecond trong giây | `int` | `123456789` |

Điểm quan trọng: `LocalDateTime` **không có `ZoneId`, `ZoneOffset` hoặc `Instant` bên trong**. Vì thế, thao tác tách ngày và giờ **không làm chuyển múi giờ** và không xác nhận dữ liệu đang ở UTC. Nó chỉ lấy hai phần đã có sẵn trong cùng một ngày–giờ địa phương.

## 2. Dùng toLocalDate() và toLocalTime()

Đây là cách rõ ràng nhất khi muốn tách theo kiểu dữ liệu:

~~~java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;

LocalDateTime dateTime =
        LocalDateTime.parse("2025-04-09T14:30:45.123456789");

LocalDate date = dateTime.toLocalDate();
LocalTime time = dateTime.toLocalTime();

// date = 2025-04-09
// time = 14:30:45.123456789
~~~

`toLocalDate()` chỉ lấy phần ngày mà không thay đổi `dateTime`. Tương tự, `toLocalTime()` giữ nguyên giờ, phút, giây và độ chính xác nanosecond hiện có. Không có bước làm tròn, cắt bớt phần lẻ hoặc tự động đổi vùng.

Sau khi tách, sử dụng API phù hợp với ý nghĩa từng phần:

~~~java
int year = date.getYear();        // 2025
int month = date.getMonthValue(); // 4
int day = date.getDayOfMonth();   // 9

int hour = time.getHour();        // 14
int minute = time.getMinute();    // 30
int second = time.getSecond();    // 45
int nano = time.getNano();        // 123456789
~~~

Sự khác biệt là `toLocalDate()` trả về **một đối tượng ngày** có thể xử lý như một giá trị lịch độc lập, còn `getDayOfMonth()` chỉ trả về **một trường số nguyên**, không đủ để xác định ngày. Tương tự, `toLocalTime()` trả về giờ đầy đủ, khác với `getHour()` chỉ trả một số 0–23.

Nếu cần phân loại đơn hàng theo **ngày lập**, dùng `toLocalDate()`; nếu cần kiểm tra đơn được lập **trước 17:00 trong ngày**, dùng `toLocalTime()`. Khi phân loại dựa trên một múi giờ cụ thể, phải bảo đảm dữ liệu đã được hiểu theo múi giờ nghiệp vụ trước khi tách.

## 3. Ví dụ Java 17+ hoàn chỉnh và kết quả chính xác

Lưu thành tệp `LocalDateTimeSplitDemo.java`:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import java.util.Locale;

public class LocalDateTimeSplitDemo {
    public static void main(String[] args) {
        LocalDateTime original =
                LocalDateTime.parse("2025-04-09T14:30:45.123456789");

        LocalDate date = original.toLocalDate();
        LocalTime time = original.toLocalTime();

        System.out.println("original=" + original);
        System.out.println("date=" + date);
        System.out.println("time=" + time);
        System.out.println("parts=" + date.getYear()
                + "/" + date.getMonthValue()
                + "/" + date.getDayOfMonth());
        System.out.println("clock=" + time.getHour()
                + ":" + time.getMinute()
                + ":" + time.getSecond()
                + " nanos=" + time.getNano());

        LocalDateTime recombined = LocalDateTime.of(date, time);
        System.out.println("recombine=" + recombined);
        System.out.println("same="
                + original.equals(date.atTime(time)));
        System.out.println("midnight=" + date.atStartOfDay());
        System.out.println("noon=" + date.atTime(12, 0));

        DateTimeFormatter display = DateTimeFormatter.ofPattern(
                "dd/MM/uuuu HH:mm:ss.SSS", Locale.ROOT);
        System.out.println("display=" + original.format(display));
        System.out.println("trunc="
                + original.truncatedTo(ChronoUnit.MINUTES));

        LocalDateTime acrossMidnight =
                LocalDateTime.of(2025, 4, 9, 23, 59).plusMinutes(2);
        System.out.println("across=" + acrossMidnight);

        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        ZonedDateTime withZone = original.atZone(zone);
        Instant instant = withZone.toInstant();
        System.out.println("withZone=" + withZone);
        System.out.println("instant=" + instant);
        System.out.println("recovered="
                + instant.atZone(zone).toLocalDateTime());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac LocalDateTimeSplitDemo.java
java LocalDateTimeSplitDemo
~~~

Kết quả với dữ liệu cố định trong chương trình:

~~~text
original=2025-04-09T14:30:45.123456789
date=2025-04-09
time=14:30:45.123456789
parts=2025/4/9
clock=14:30:45 nanos=123456789
recombine=2025-04-09T14:30:45.123456789
same=true
midnight=2025-04-09T00:00
noon=2025-04-09T12:00
display=09/04/2025 14:30:45.123
trunc=2025-04-09T14:30
across=2025-04-10T00:01
withZone=2025-04-09T14:30:45.123456789+07:00[Asia/Ho_Chi_Minh]
instant=2025-04-09T07:30:45.123456789Z
recovered=2025-04-09T14:30:45.123456789
~~~

Kết quả `same=true` chứng minh rằng tách thành `LocalDate` và `LocalTime` rồi ghép lại **không mất thông tin ngày, giờ hay nanosecond** của `LocalDateTime`. Dòng `display` chỉ in ba chữ số phần lẻ theo mẫu và không làm thay đổi đối tượng gốc; dòng `trunc` cố ý tạo đối tượng mới đã bỏ giây và phần lẻ. Những dòng `withZone` và `instant` mô tả thao tác **bổ sung ngữ cảnh vùng giờ**, chứ không phải hệ quả tự động của việc tách.

## 4. Khi chỉ cần các trường số, có thể đọc trực tiếp

Nếu nghiệp vụ chỉ cần một số nguyên và không cần đối tượng `LocalDate`/`LocalTime` riêng, `LocalDateTime` đã hỗ trợ các getter trực tiếp:

~~~java
LocalDateTime value =
        LocalDateTime.of(2025, 4, 9, 14, 30, 45, 123_456_789);

int year = value.getYear();          // 2025
int month = value.getMonthValue();   // 4
int day = value.getDayOfMonth();     // 9
int hour = value.getHour();          // 14
int minute = value.getMinute();      // 30
int second = value.getSecond();      // 45
int nano = value.getNano();          // 123456789
~~~

Hai cách đọc dưới đây có kết quả số bằng nhau:

~~~java
int directHour = value.getHour();
int hourFromTime = value.toLocalTime().getHour();

int directDay = value.getDayOfMonth();
int dayFromDate = value.toLocalDate().getDayOfMonth();
~~~

Chọn `toLocalDate()` khi cần **ngày đầy đủ** cho tính toán lịch, so sánh ngày, ngày nghỉ hay truy vấn theo ngày. Chọn `toLocalTime()` khi cần **giờ đầy đủ** để so sánh giờ làm việc hoặc định dạng thời gian. Chọn getter trực tiếp khi chỉ muốn hiển thị hoặc kiểm tra một thành phần.

Cần phân biệt `getDayOfMonth()` với `getDayOfYear()` và `getDayOfWeek()`: chúng lần lượt là ngày trong tháng, thứ tự ngày trong năm và thứ trong tuần, không thể thay thế cho nhau.

## 5. Ghép lại ngày và giờ: LocalDateTime.of, atTime và atDate

Sau khi tách, có ba cách thường gặp để ghép lại:

~~~java
LocalDate date = LocalDate.of(2025, 4, 9);
LocalTime time = LocalTime.of(14, 30, 45, 123_456_789);

LocalDateTime a = LocalDateTime.of(date, time);
LocalDateTime b = date.atTime(time);
LocalDateTime c = time.atDate(date);

// a.equals(b) && b.equals(c) là true
~~~

- `LocalDateTime.of(date, time)` thể hiện trực tiếp ý định ghép hai thành phần.
- `date.atTime(time)` thuận tiện khi luồng xử lý bắt đầu từ một ngày.
- `time.atDate(date)` thuận tiện khi luồng xử lý bắt đầu từ một giờ.

Các giá trị trả về vẫn là `LocalDateTime` **không có zone**. Nếu hai thành phần đến từ các nguồn khác nhau, phải bảo đảm chúng thuộc cùng một **ngữ cảnh nghiệp vụ**. Ghép “ngày UTC” với “giờ Việt Nam” mà không chuyển đổi trước sẽ tạo giá trị trông hợp lệ nhưng sai nghĩa.

Để cố ý đặt giờ cho một ngày:

~~~java
LocalDate date = LocalDate.of(2025, 4, 9);
LocalDateTime begin = date.atStartOfDay(); // 2025-04-09T00:00
LocalDateTime noon = date.atTime(12, 0);  // 2025-04-09T12:00
~~~

`date.atStartOfDay()` không có tham số trả về **LocalDateTime** tại 00:00, **chưa phải instant theo UTC**. Phương thức `date.atStartOfDay(ZoneId)` là overload khác, trả về `ZonedDateTime` dựa trên quy tắc vùng giờ, cần phân biệt rõ hai kết quả này.

## 6. Thay đổi riêng ngày hoặc riêng giờ mà giữ thành phần còn lại

Các kiểu thời gian trong `java.time` là immutable, nên mọi phép đổi đều tạo giá trị mới. Để giữ nguyên giờ nhưng thay ngày:

~~~java
LocalDateTime original =
        LocalDateTime.parse("2025-04-09T14:30:45.123456789");
LocalDate replacementDate = LocalDate.of(2025, 4, 10);
LocalDateTime changedDate =
        LocalDateTime.of(replacementDate, original.toLocalTime());
// 2025-04-10T14:30:45.123456789
~~~

Để giữ ngày nhưng đổi giờ:

~~~java
LocalTime replacementTime = LocalTime.of(9, 0);
LocalDateTime changedTime =
        LocalDateTime.of(original.toLocalDate(), replacementTime);
// 2025-04-09T09:00
~~~

Một số trường hợp chỉ cần `withYear`, `withMonth`, `withDayOfMonth`, `withHour` hoặc `withMinute`:

~~~java
LocalDateTime atNine = original.withHour(9).withMinute(0);
// 2025-04-09T09:00:45.123456789
~~~

Lưu ý: `withHour(9).withMinute(0)` **giữ nguyên giây và nanosecond** của `original`, khác với việc ghép `LocalTime.of(9, 0)` (mặc định giây và nanosecond bằng 0). Khi muốn thay hẳn “giờ họp lúc 09:00 đúng”, nên ghép với một `LocalTime` rõ ràng hoặc đặt lại giây và phần lẻ.

Nếu cộng thêm thời gian đi qua nửa đêm, `LocalDateTime` sẽ thay đổi cả ngày:

~~~java
LocalDateTime nearMidnight =
        LocalDateTime.of(2025, 4, 9, 23, 59);
LocalDateTime later = nearMidnight.plusMinutes(2);
// 2025-04-10T00:01
~~~

Trong ví dụ này, tách `nearMidnight` trước và cộng `2` phút **chỉ trên `LocalTime`** sẽ cho `00:01` nhưng mất thông tin sang ngày 10/04. Hãy làm phép toán trên `LocalDateTime` nếu khoảng thời gian có thể đổi ngày.

## 7. Định dạng và phân tích ngày giờ tách biệt

`LocalDateTime.parse(...)` theo mặc định nhận dạng ISO-8601 có phần ngày, `T` và phần giờ, chẳng hạn:

~~~java
LocalDateTime dateTime =
        LocalDateTime.parse("2025-04-09T14:30:45.123456789");
LocalDate date = dateTime.toLocalDate();
LocalTime time = dateTime.toLocalTime();

String dateText = date.toString(); // "2025-04-09"
String timeText = time.toString(); // "14:30:45.123456789"
~~~

Có thể đọc hai chuỗi riêng rồi ghép:

~~~java
LocalDate parsedDate = LocalDate.parse("2025-04-09");
LocalTime parsedTime = LocalTime.parse("14:30:45.123456789");
LocalDateTime recombined =
        LocalDateTime.of(parsedDate, parsedTime);
~~~

Để hiển thị theo `dd/MM/uuuu HH:mm:ss`:

~~~java
DateTimeFormatter formatter = DateTimeFormatter.ofPattern(
        "dd/MM/uuuu HH:mm:ss");
String text = dateTime.format(formatter);
// "09/04/2025 14:30:45"
~~~

Nếu formatter chỉ có mẫu đến giây, phần nanosecond **không được in ra**. Điều này không xóa phần lẻ của `dateTime`. Tuy nhiên, nếu bạn **parse lại chuỗi đã bỏ phần lẻ**, đối tượng mới sẽ có nanosecond = 0, tức đã mất độ chính xác qua quá trình chuyển đổi chuỗi.

Trong pattern:

| Ký hiệu | Ý nghĩa | Cần chú ý |
| --- | --- | --- |
| `uuuu` | Năm theo lịch proleptic ISO | Thường thích hợp hơn `YYYY` khi muốn năm lịch |
| `MM` | Tháng | Khác `mm` (phút) |
| `dd` | Ngày trong tháng | Khác `DD` (ngày trong năm) |
| `HH` | Giờ 24 giờ | Khác `hh` (giờ 12 giờ) |
| `mm` | Phút | Chữ thường |
| `ss` | Giây | Chữ thường |
| `SSS` | Ba chữ số phần lẻ giây | In mili giây bằng cách lấy ba chữ số đầu |

Không nên tách chuỗi thủ công bằng `substring(0, 10)` hoặc `split("T")` làm cơ chế xử lý dữ liệu chính. Cách đó dễ sai khi định dạng thay đổi hoặc đầu vào không hợp lệ; parse bằng `LocalDateTime.parse` rồi gọi `toLocalDate()/toLocalTime()` cung cấp kiểu dữ liệu và xác thực ngày giờ phù hợp.

## 8. Tách ngày giờ không tự chuyển đổi múi giờ

Đây là ranh giới quan trọng nhất khi ứng dụng lấy dữ liệu từ API, database hoặc các vùng khác nhau. Giá trị sau:

~~~text
2025-04-09T14:30:45
~~~

chưa cho biết đó là 14:30 ở Việt Nam hay London. `LocalDateTime.toLocalDate()` trả `2025-04-09` trong cả hai cách hiểu; nhưng **hai thời điểm thực tế** sẽ khác nhau nếu bạn gắn zone khác nhau.

Nếu dữ liệu vốn là một instant và muốn lấy ngày/giờ **ở Việt Nam**, trước tiên chuyển instant sang vùng đó:

~~~java
Instant occurredAt =
        Instant.parse("2025-04-09T07:30:45.123456789Z");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

LocalDateTime local =
        occurredAt.atZone(zone).toLocalDateTime();
LocalDate date = local.toLocalDate();
LocalTime time = local.toLocalTime();
// date = 2025-04-09
// time = 14:30:45.123456789
~~~

Ngược lại, nếu `LocalDateTime` đã được nghiệp vụ xác định là giờ Việt Nam, bạn mới có đủ thông tin để gắn vùng và đổi sang instant:

~~~java
LocalDateTime local =
        LocalDateTime.parse("2025-04-09T14:30:45.123456789");
ZonedDateTime zoned =
        local.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
Instant instant = zoned.toInstant();
// 2025-04-09T07:30:45.123456789Z
~~~

**Không được tự gắn `ZoneOffset.UTC` hay ký hiệu `Z`** cho một `LocalDateTime` chỉ vì muốn “lưu UTC”: làm thế sẽ thay đổi ý nghĩa thời điểm nếu giờ gốc thực ra là giờ địa phương.

Với vùng có DST, một ngày–giờ địa phương có thể không tồn tại hoặc xuất hiện hai lần. Ví dụ, `2025-11-02T01:30` ở `America/New_York` có thể ứng với hai offset khác nhau. `atZone(zone)` có quy tắc giải quyết mặc định; nếu nghiệp vụ cần xác định chính xác lựa chọn, hãy kiểm tra `zone.getRules().getValidOffsets(local)` và chọn chính sách rõ ràng. Tách riêng thành `LocalDate` và `LocalTime` **không xử lý được sự mơ hồ DST**.

## 9. Ứng dụng trong dữ liệu và nghiệp vụ

### Trường hợp 1: nhóm sự kiện theo ngày

Nếu mỗi giá trị `LocalDateTime` đã đại diện đúng cho giờ địa phương của nghiệp vụ, hãy nhóm theo ngày:

~~~java
Map<LocalDate, List<LocalDateTime>> byDay =
        events.stream().collect(
                java.util.stream.Collectors.groupingBy(
                        LocalDateTime::toLocalDate));
~~~

Đoạn trên là mã minh họa trong một phương thức với biến `events` kiểu `List<LocalDateTime>` và import `java.util.*`; đây **không phải chương trình độc lập**. Kết quả nhóm theo **ngày của các giá trị LocalDateTime đầu vào**. Nếu `events` là các instant từ nhiều múi giờ, hãy đổi từng instant sang cùng vùng cần báo cáo trước khi nhóm.

### Trường hợp 2: kiểm tra giờ vận hành trong ngày

~~~java
LocalTime workStart = LocalTime.of(9, 0);
LocalTime workEnd = LocalTime.of(17, 0);

LocalTime eventTime = dateTime.toLocalTime();
boolean inBusinessHours =
        !eventTime.isBefore(workStart)
                && eventTime.isBefore(workEnd);
~~~

Đây là khoảng nửa kín **[09:00, 17:00)**: đúng 09:00 được tính, đúng 17:00 không được tính. Biểu thức phù hợp cho ca làm việc **không qua nửa đêm**. Nếu ca làm qua nửa đêm, phải thay đổi logic hoặc sử dụng cả ngày và giờ. Trước khi kiểm tra, cũng cần xác nhận `dateTime` đang là giờ địa phương của đơn vị vận hành.

### Trường hợp 3: giữ riêng date và time cho biểu mẫu

Giao diện người dùng có thể cung cấp ô ngày và ô giờ độc lập:

~~~java
LocalDate inputDate = LocalDate.parse("2025-04-09");
LocalTime inputTime = LocalTime.parse("14:30");

LocalDateTime appointment = inputDate.atTime(inputTime);
// 2025-04-09T14:30
~~~

Nếu dữ liệu đại diện cho cuộc hẹn trong một thành phố, ứng dụng còn cần biết `ZoneId` của thành phố khi định lịch hoặc gửi thông báo. `LocalDateTime` chỉ mang ngày giờ người dùng chọn.

### Trường hợp 4: DTO hoặc cơ sở dữ liệu

Một DTO có thể tách các trường để UI dễ xử lý:

~~~java
public record AppointmentInput(
        LocalDate date,
        LocalTime time,
        String zoneId
) {}
~~~

Đây là khai báo record minh họa và cần import các kiểu `java.time`; không phải chương trình chạy độc lập. Khi xử lý dữ liệu, ứng dụng cần validate ngày, giờ và `zoneId`, sau đó kết hợp theo chính sách DST. Nếu chỉ muốn lưu một giá trị ngày–giờ địa phương, có thể dùng `LocalDateTime`, nhưng không nên giả định kiểu `TIMESTAMP` trong cơ sở dữ liệu luôn có ngữ nghĩa zone giống nhau ở mọi hệ quản trị/driver.

## 10. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Cho rằng `toLocalDate()` trả timestamp lúc 00:00 | Ngày không có giờ hay instant | Dùng `LocalDate` như ngày lịch, gắn giờ/zone khi thật cần |
| Cho rằng `toLocalTime()` giữ lại ngày | Mất thông tin ngày khi đưa qua nửa đêm | Dùng `LocalDateTime` cho phép tính có thể đổi ngày |
| Dùng `getDayOfMonth()` thay cho `toLocalDate()` | Chỉ giữ số ngày 1–31, mất năm và tháng | Dùng `toLocalDate()` |
| Dùng `getHour()` thay cho `toLocalTime()` | Mất phút, giây và nano giây | Dùng `toLocalTime()` |
| Tách bằng `substring` rồi parse tự chế | Sai định dạng, khó kiểm tra dữ liệu | Parse thành kiểu ngày giờ trước rồi tách |
| Nghĩ tách phần ngày/giờ là chuyển timezone | Dữ liệu bị hiểu nhầm về UTC | Chuyển `Instant` sang `ZoneId` trước nếu cần ngày/giờ một vùng |
| Format với `SSS` rồi parse lại, tưởng vẫn giữ nano giây | Độ chính xác bị mất qua chuỗi | Truyền kiểu dữ liệu đầy đủ hoặc format đủ chữ số |
| Ghép ngày và giờ lấy từ hai vùng khác nhau | Tạo `LocalDateTime` hợp lệ về cú pháp nhưng sai nghiệp vụ | Chuẩn hóa cùng ngữ cảnh trước khi ghép |
| Dùng `LocalDateTime.now()` trong unit test cần kết quả cố định | Phụ thuộc thời gian và zone của môi trường | Cấp `Clock` phù hợp, kiểm thử trên mốc cố định |
| Giả định một ngày giờ địa phương luôn ánh xạ một instant | DST có thể tạo gap hoặc overlap | Xác định zone và quy tắc xử lý DST |

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Với `LocalDateTime.parse("2025-04-09T14:30:45.123456789")`, kết quả `toLocalDate()` và `toLocalTime()` là gì?

**Đáp án:** `2025-04-09` và `14:30:45.123456789`. Không tự thêm offset hoặc múi giờ.

**Câu 2.** Ghép kết quả hai lời gọi trên bằng `LocalDateTime.of(date, time)` có mất nanosecond không?

**Đáp án:** Không. `LocalTime` giữ đầy đủ phần lẻ nanosecond nên ghép lại tái tạo chính xác ngày giờ ban đầu, miễn các thành phần chưa bị sửa đổi.

**Câu 3.** Vì sao `date.atStartOfDay()` chưa phải timestamp UTC?

**Đáp án:** Lời gọi này trả `LocalDateTime` tại `00:00`, không chứa zone. Muốn có một thời điểm UTC phải xác định vùng thích hợp, chẳng hạn `date.atStartOfDay(zone).toInstant()`.

**Câu 4.** `2025-04-09T23:59` cộng hai phút cho ra ngày nào và giờ nào?

**Đáp án:** `2025-04-10T00:01`. Nếu chỉ tính bằng `LocalTime`, thông tin sang ngày 10/04 sẽ không còn.

**Câu 5.** Khi có một `Instant` từ API và cần nhóm theo ngày Việt Nam, nên làm bước nào trước khi `toLocalDate()`?

**Đáp án:** Chuyển instant sang `Asia/Ho_Chi_Minh` bằng `instant.atZone(zone)` rồi lấy ngày. Ngày UTC và ngày Việt Nam có thể khác nhau vào cùng một thời điểm.

**Ghi nhớ:** `toLocalDate()` lấy **ngày**, `toLocalTime()` lấy **giờ**, và `LocalDateTime.of(date, time)` hoặc `date.atTime(time)` ghép chúng lại **không thay đổi vùng giờ**. Chỉ khi có thông tin về `ZoneId`/offset mới xác định được vị trí của ngày–giờ ấy trên trục thời gian UTC.
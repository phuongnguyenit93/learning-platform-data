# Tránh dùng chuỗi day period làm định dạng trao đổi dữ liệu ổn định

Java 16 bổ sung ký hiệu mẫu `B` trong `DateTimeFormatter` để định dạng *day period* theo ngôn ngữ và quy tắc locale, chẳng hạn cách diễn đạt “buổi sáng”, “buổi chiều” hoặc “buổi tối”. Đây là công cụ hữu ích cho giao diện người dùng. Tuy nhiên, chuỗi day period là văn bản hiển thị phụ thuộc locale và dữ liệu ngôn ngữ; nó không phải định dạng trao đổi thời gian ổn định giữa các hệ thống.

Không lưu hoặc truyền chuỗi như `in the morning`, `buổi sáng` hay `at night` làm giá trị thời gian chuẩn. Những chuỗi này không xác định chính xác giờ, ngày, múi giờ hoặc một thời điểm duy nhất. Để trao đổi dữ liệu, hãy dùng các kiểu `java.time` và định dạng ISO-8601 phù hợp: `LocalTime` cho giờ địa phương, `Instant` cho thời điểm UTC, `OffsetDateTime` cho thời điểm kèm offset, hoặc `ZonedDateTime` khi cần cả múi giờ vùng. `DateTimeFormatter.ISO_ZONED_DATE_TIME` là dạng ISO mở rộng của Java có thêm `ZoneId` trong dấu ngoặc vuông. Nếu nghiệp vụ thật sự có khái niệm “ca sáng”, hãy định nghĩa mã và ranh giới thời gian của nghiệp vụ một cách tường minh.

## 1. Day period là nhãn hiển thị theo locale

Trong `DateTimeFormatter`, ký hiệu mẫu `B` biểu diễn day period. Khác với `a` thường biểu diễn AM/PM, `B` hỗ trợ cách chia thời gian linh hoạt hơn theo quy tắc locale. Tùy ngôn ngữ và thời điểm trong ngày, văn bản có thể được diễn đạt như buổi sáng, buổi chiều, buổi tối, ban đêm hoặc một cách gọi đặc biệt cho khoảng giữa ngày.

Ví dụ định dạng giờ để hiển thị cho người dùng:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

class DayPeriodDisplay {
    static String formatForUser(LocalTime time, Locale locale) {
        DateTimeFormatter formatter = DateTimeFormatter.ofPattern("h:mm B", locale);
        return time.format(formatter);
    }

    public static void main(String[] args) {
        LocalTime time = LocalTime.of(9, 30);

        System.out.println(formatForUser(time, Locale.US));
        System.out.println(formatForUser(time, Locale.forLanguageTag("vi-VN")));
    }
}
```

Hai lời gọi có thể tạo ra cách diễn đạt khác nhau vì locale khác nhau. Cách viết cụ thể cũng phụ thuộc dữ liệu locale mà JDK sử dụng. Vì vậy, hãy tạo chuỗi `B` ở lớp hiển thị, gần nơi biết ngôn ngữ người dùng; không xem nó là một mã dữ liệu dùng chung giữa client, server, database và hệ thống tích hợp.

## 2. Vì sao chuỗi day period không phải dữ liệu thời gian chuẩn?

Một nhãn như “buổi sáng” không mang đủ thông tin để xác định một thời điểm:

- **Không xác định chính xác giờ:** “buổi sáng” có thể chỉ một khoảng thời gian rộng, không cho biết 08:15 hay 11:45.
- **Phụ thuộc locale:** ngôn ngữ khác nhau có cách chia và cách gọi day period khác nhau.
- **Không phải quy tắc toàn cầu:** ranh giới giữa các period có thể khác theo locale và dữ liệu văn hóa.
- **Không chứa ngày:** một nhãn day period không cho biết ngày nào.
- **Không chứa múi giờ hoặc offset:** cùng một giờ địa phương có thể tương ứng với các thời điểm UTC khác nhau.
- **Không phù hợp để round-trip:** từ nhãn hiển thị không thể khôi phục chắc chắn giờ ban đầu.

Ví dụ, nếu database lưu chuỗi `buổi sáng`, một dịch vụ khác không thể suy ra chính xác thời điểm cần gửi thông báo. Nếu sau này giao diện đổi locale sang tiếng Anh, chuỗi cũ cũng không thể được dùng trực tiếp như một nhãn tiếng Anh.

Ngay cả khi mọi hệ thống hiện tại cùng dùng một ngôn ngữ, việc lưu văn bản hiển thị vẫn tạo ra hợp đồng mong manh: thay đổi cách dịch hoặc dữ liệu locale có thể làm giá trị không còn nhận diện được.

## 3. Dùng `LocalTime` và ISO local time khi chỉ trao đổi giờ trên đồng hồ

Nếu dữ liệu chỉ là giờ trong ngày, không gắn với ngày hoặc múi giờ, dùng `LocalTime`. Có thể định dạng và parse bằng `DateTimeFormatter.ISO_LOCAL_TIME`:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;

class LocalTimeExchange {
    static String encode(LocalTime time) {
        return DateTimeFormatter.ISO_LOCAL_TIME.format(time);
    }

    static LocalTime decode(String value) {
        return LocalTime.parse(value, DateTimeFormatter.ISO_LOCAL_TIME);
    }

    public static void main(String[] args) {
        LocalTime original = LocalTime.of(9, 30);
        String wireValue = encode(original);
        LocalTime restored = decode(wireValue);

        System.out.println(wireValue);
        System.out.println(original.equals(restored)); // true
    }
}
```

ISO local time biểu diễn các thành phần giờ, phút, giây và phần giây khi có. Nó không chứa ngày hoặc múi giờ. Đây là lựa chọn đúng cho dữ liệu như “cửa hàng mở lúc 09:30 theo giờ địa phương”, miễn là hợp đồng đã xác định rõ giờ thuộc múi giờ nào ở lớp nghiệp vụ.

Không dùng `LocalTime` một mình cho một sự kiện cần xác định thời điểm toàn cầu. `09:30` tại hai múi giờ khác nhau là hai thời điểm khác nhau.

## 4. Dùng `Instant` khi cần một thời điểm UTC duy nhất

Nếu dữ liệu mô tả một sự kiện đã xảy ra hoặc một thời điểm tuyệt đối, dùng `Instant`. Đây là điểm trên dòng thời gian UTC và có thể trao đổi bằng định dạng ISO-8601 kết thúc bằng `Z`:

```java
import java.time.Instant;
import java.time.format.DateTimeFormatter;

class InstantExchange {
    static String encode(Instant instant) {
        return DateTimeFormatter.ISO_INSTANT.format(instant);
    }

    static Instant decode(String value) {
        return Instant.parse(value);
    }

    public static void main(String[] args) {
        Instant eventTime = Instant.parse("2026-11-27T02:30:00Z");
        String wireValue = encode(eventTime);

        System.out.println(wireValue);
        System.out.println(decode(wireValue).equals(eventTime)); // true
    }
}
```

`Instant` phù hợp cho timestamp log, thời điểm tạo giao dịch, thời điểm nhận sự kiện hoặc dữ liệu đồng bộ giữa các hệ thống. Nếu giao diện cần hiển thị theo múi giờ của người dùng, hãy chuyển `Instant` sang `ZonedDateTime` tại lớp trình bày rồi mới định dạng bằng locale tương ứng.

## 5. Dùng `OffsetDateTime` hoặc `ZonedDateTime` khi cần ngữ cảnh múi giờ

Chọn kiểu dữ liệu dựa trên thông tin múi giờ mà hợp đồng cần bảo toàn:

| Kiểu | Thông tin biểu diễn | Dùng khi |
| --- | --- | --- |
| `LocalTime` | Giờ trên đồng hồ, không ngày và không zone | Giờ mở cửa hoặc giờ hẹn lặp lại khi zone được quản lý riêng. |
| `OffsetTime` | Giờ trên đồng hồ kèm offset UTC, không ngày và không region zone | Dữ liệu giờ có offset nhưng không cần quy tắc lịch sử/tương lai của vùng. |
| `Instant` | Một thời điểm tuyệt đối trên UTC timeline | Timestamp sự kiện hoặc đồng bộ hệ thống. |
| `OffsetDateTime` | Ngày giờ kèm offset UTC | Timestamp cần bảo toàn offset đã gửi. |
| `ZonedDateTime` | Ngày giờ, offset và `ZoneId` | Lịch hẹn hoặc sự kiện cần giữ múi giờ vùng như `Asia/Ho_Chi_Minh`. |

Ví dụ trao đổi một timestamp có offset:

```java
import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;

class OffsetDateTimeExchange {
    public static void main(String[] args) {
        OffsetDateTime sentAt = OffsetDateTime.parse(
            "2026-11-27T09:30:00+07:00",
            DateTimeFormatter.ISO_OFFSET_DATE_TIME
        );

        String wireValue = sentAt.format(DateTimeFormatter.ISO_OFFSET_DATE_TIME);
        OffsetDateTime restored = OffsetDateTime.parse(
            wireValue, DateTimeFormatter.ISO_OFFSET_DATE_TIME
        );

        System.out.println(restored.equals(sentAt)); // true
    }
}
```

Offset `+07:00` xác định quan hệ với UTC tại timestamp đó, nhưng không nói rõ vùng địa lý hoặc quy tắc thay đổi giờ của vùng. Nếu cần giữ danh tính vùng, dùng `ZonedDateTime`:

```java
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;

class ZonedDateTimeExchange {
    public static void main(String[] args) {
        ZonedDateTime appointment = ZonedDateTime.parse(
            "2026-11-27T09:30:00+07:00[Asia/Ho_Chi_Minh]",
            DateTimeFormatter.ISO_ZONED_DATE_TIME
        );

        String wireValue = appointment.format(DateTimeFormatter.ISO_ZONED_DATE_TIME);
        ZonedDateTime restored = ZonedDateTime.parse(
            wireValue, DateTimeFormatter.ISO_ZONED_DATE_TIME
        );

        System.out.println(restored.getZone()); // Asia/Ho_Chi_Minh
        System.out.println(restored.equals(appointment)); // true
    }
}
```

`ZoneId` giữ danh tính vùng theo cơ sở dữ liệu múi giờ của nền tảng. Với lịch trong tương lai, quy tắc múi giờ có thể được cập nhật theo thay đổi pháp luật; hệ thống cần quyết định lưu ý định giờ địa phương theo vùng hay lưu một instant đã chốt. Nếu lịch lặp lại đi qua thời điểm đổi giờ mùa hè ở các vùng có áp dụng DST, hãy định nghĩa rõ cách xử lý giờ không tồn tại hoặc giờ xuất hiện hai lần.

## 6. Lưu lịch lặp lại bằng giờ và `ZoneId`, không bằng nhãn day period

Giả sử một cửa hàng mở cửa mỗi ngày từ 09:00 đến 17:00 theo giờ địa phương. Dữ liệu nên lưu hai mốc giờ và múi giờ:

```java
import java.time.LocalTime;
import java.time.ZoneId;

record BusinessHours(LocalTime opensAt, LocalTime closesAt, ZoneId zone) {}

class BusinessHoursExample {
    public static void main(String[] args) {
        BusinessHours hours = new BusinessHours(
            LocalTime.of(9, 0),
            LocalTime.of(17, 0),
            ZoneId.of("Asia/Ho_Chi_Minh")
        );

        System.out.println(hours.opensAt());
        System.out.println(hours.zone());
    }
}
```

Một hợp đồng JSON tương ứng có thể biểu diễn bằng các trường có cấu trúc:

```json
{
  "opensAt": "09:00:00",
  "closesAt": "17:00:00",
  "zone": "Asia/Ho_Chi_Minh"
}
```

Các giá trị này cho hệ thống nhận đủ thông tin để hiểu giờ địa phương và vùng áp dụng. Khi hiển thị, ứng dụng có thể tạo chuỗi day period theo locale người xem. Nếu lịch có thể qua nửa đêm, hãy định nghĩa rõ quy tắc ngày kết thúc; nếu lịch gắn với ngày cụ thể, kết hợp `LocalDate`, `LocalTime` và `ZoneId` để xác định thời điểm.

## 7. Nếu nghiệp vụ cần khái niệm “ca sáng”, hãy định nghĩa mã nghiệp vụ riêng

Đôi khi ứng dụng không chỉ cần một nhãn giao diện mà thực sự có khái niệm miền nghiệp vụ như ca sáng, ca chiều hoặc ca đêm. Trong trường hợp đó, đừng lấy chuỗi do `DateTimeFormatter` sinh ra làm mã chuẩn. Hãy định nghĩa enum hoặc mã ổn định của ứng dụng, đồng thời mô tả ranh giới thời gian:

```java
enum WorkShift {
    MORNING("MORNING"),
    AFTERNOON("AFTERNOON"),
    NIGHT("NIGHT");

    private final String code;

    WorkShift(String code) {
        this.code = code;
    }

    String code() {
        return code;
    }
}
```

Hợp đồng có thể gửi mã `MORNING` thay vì gửi nhãn đã dịch như `buổi sáng`. Nếu enum được tuần tự hóa để trao đổi hoặc lưu trữ lâu dài, hãy dùng mã tường minh như `code()`; không dùng `ordinal()` vì thứ tự khai báo enum có thể thay đổi. Enum chỉ là mã phân loại; hệ thống vẫn cần quy tắc xác định giờ bắt đầu, giờ kết thúc, ngày áp dụng và múi giờ. Các quy tắc đó nên nằm trong cấu hình hoặc dữ liệu nghiệp vụ có version rõ ràng.

Ví dụ, nếu ứng dụng quy định ca sáng là 06:00–12:00 tại một cơ sở cụ thể, hãy lưu hai mốc `LocalTime` cùng `ZoneId`. Không dựa vào ranh giới “morning” của CLDR để quyết định chấm công, tính lương hoặc quyền truy cập.

## 8. Không parse chuỗi day period để khôi phục thời gian

Pattern `B` phục vụ định dạng văn bản theo locale. Không thiết kế giao thức như sau:

```text
{
  "appointmentTime": "9:30 in the morning"
}
```

Một hệ thống khác không thể biết chính xác chuỗi này được tạo bởi locale nào, có nghĩa chính xác là mấy giờ trong ngày nào, hay quy tắc day period nào đã được áp dụng. Việc parse còn phụ thuộc locale và dữ liệu ngôn ngữ; ngay cả parse thành công cũng không khôi phục được thông tin không có trong chuỗi.

Giao thức nên gửi giá trị chuẩn:

```json
{
  "appointmentTime": "2026-11-27T09:30:00+07:00",
  "timeZone": "Asia/Ho_Chi_Minh"
}
```

Nếu chỉ là giờ lặp lại hàng ngày, có thể gửi `"09:30:00"` cùng `timeZone`. Nếu là một sự kiện đã chốt tại một thời điểm tuyệt đối, ưu tiên timestamp UTC như `"2026-11-27T02:30:00Z"`.

## 9. Tách lớp dữ liệu và lớp trình bày

Một thiết kế ổn định giữ giá trị thời gian chuẩn trong domain/API và chỉ tạo day period ở giao diện:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

class AppointmentView {
    static String displayTime(LocalTime time, Locale userLocale) {
        return time.format(DateTimeFormatter.ofPattern("h:mm B", userLocale));
    }
}
```

Luồng xử lý có thể hình dung như sau:

```text
Giá trị thời gian chuẩn
LocalTime / Instant / OffsetDateTime / ZonedDateTime
                 |
                 v
       API, database, message
       ISO-8601 / cấu trúc có kiểu
                 |
                 v
          Lớp trình bày
      chọn Locale của người dùng
                 |
                 v
       DateTimeFormatter với B
                 |
                 v
       Nhãn day period đã dịch
```

Cách tách này cho phép thay đổi ngôn ngữ giao diện mà không phải di chuyển hoặc chuyển đổi dữ liệu đã lưu. Nó cũng giúp client và server trao đổi giá trị có ngữ nghĩa rõ ràng.

## 10. Chọn kiểu dữ liệu theo mục đích

| Nhu cầu | Kiểu/định dạng nên dùng | Tránh dùng |
| --- | --- | --- |
| Hiển thị “buổi sáng”, “buổi chiều” theo ngôn ngữ người dùng | `DateTimeFormatter` với pattern `B` và `Locale` phù hợp | Lưu nhãn đã format làm giá trị chuẩn. |
| Trao đổi giờ mở cửa 09:30 | `LocalTime` và ISO local time | Chuỗi “9:30 in the morning”. |
| Trao đổi timestamp sự kiện | `Instant` và ISO instant UTC | Day period hoặc giờ địa phương không kèm zone. |
| Trao đổi timestamp có offset | `OffsetDateTime` và ISO offset date-time | Tự ghép chuỗi ngày giờ và nhãn locale. |
| Giữ múi giờ vùng cho lịch hẹn | `ZonedDateTime` và formatter ISO zoned date-time của Java (có phần mở rộng `ZoneId`) | Chỉ lưu offset nếu cần quy tắc vùng. |
| Biểu diễn ca làm việc của doanh nghiệp | Enum/mã nghiệp vụ cùng giờ bắt đầu, kết thúc và `ZoneId` | Dùng day period của CLDR làm quy tắc chấm công. |

## 11. Những điểm cần nhớ

- `B` là pattern day period của `DateTimeFormatter`, hữu ích để hiển thị theo locale.
- Day period là nhãn văn bản, không xác định duy nhất giờ hoặc thời điểm.
- Văn bản có thể khác theo locale và dữ liệu locale; không dùng nó làm protocol token ổn định.
- Dùng `LocalTime` cho giờ địa phương, `Instant` cho thời điểm UTC, `OffsetDateTime` cho timestamp có offset và `ZonedDateTime` khi cần `ZoneId`.
- Lịch lặp lại theo vùng thường cần giờ địa phương và `ZoneId`; lịch nghiệp vụ cần ranh giới được định nghĩa rõ.
- Nếu có khái niệm “ca sáng” trong domain, dùng mã nghiệp vụ ổn định và quy tắc thời gian riêng.
- Chỉ định dạng day period ở lớp trình bày, sau khi đã chọn locale của người dùng.

Hãy giữ dữ liệu thời gian ở dạng có cấu trúc và có ngữ nghĩa rõ ràng; dùng day period để giúp con người đọc thời gian theo ngôn ngữ của họ. Việc tách hai mục đích này giúp dữ liệu trao đổi ổn định qua các hệ thống, locale và phiên bản JDK.

## Tài liệu tham khảo

- [DateTimeFormatter – Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [DateTimeFormatter – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [LocalTime – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/LocalTime.html)
- [Instant – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html)
- [ZonedDateTime – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZonedDateTime.html)
- [DateTimeFormatter pattern letters and ISO formatters – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatter.html)

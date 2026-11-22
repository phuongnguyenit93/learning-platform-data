# LocalDate, LocalTime, LocalDateTime và các kiểu có múi giờ — định dạng thời gian trong Spring Framework

## 1. Mục tiêu và nguyên tắc quan trọng nhất

Dữ liệu ngày giờ trong Java/Spring phải trả lời **hai câu hỏi khác nhau**:

1. Chuỗi có hình thức nào khi người dùng nhập hoặc khi ứng dụng in ra? Đây là **format/parse**.
2. Giá trị biểu diễn ngày lịch, giờ trên đồng hồ, hay **một thời điểm xác định trên trục thời gian toàn cầu**? Đây là **ngữ nghĩa của kiểu dữ liệu và múi giờ**.

`java.time` (Java 8+, dùng tốt trên Java 17+) cung cấp các kiểu bất biến, an toàn khi chia sẻ giữa luồng. Spring Framework dùng `ConversionService` và `Formatter` để bind dữ liệu dạng chuỗi từ query parameter, path variable và form vào các kiểu này. Hãy chọn **đúng kiểu Java trước**, rồi mới chọn `@DateTimeFormat` hoặc `DateTimeFormatter`.

**Quy tắc xuyên suốt:** `LocalDateTime` không chứa thông tin múi giờ/offset; đổi kiểu hiển thị không thể tự xác định nó là thời điểm UTC nào. Khi cần một *instant* có ý nghĩa toàn cầu, phải có offset hoặc quy tắc `ZoneId`.

## 2. Bản đồ các kiểu `java.time`

| Kiểu | Có gì? | Có đủ thông tin để xác định một thời điểm? | Ví dụ |
| --- | --- | --- | --- |
| `LocalDate` | Ngày theo lịch, không có giờ | Không | `2026-11-05` |
| `LocalTime` | Giờ/phút/giây, không có ngày | Không | `09:30:00` |
| `LocalDateTime` | Ngày + giờ địa phương | Không | `2026-11-05T09:30:00` |
| `OffsetTime` | Giờ trong ngày + offset cố định | Không, vì thiếu ngày | `09:30:00+07:00` |
| `OffsetDateTime` | Ngày + giờ + offset UTC | Có | `2026-11-05T09:30:00+07:00` |
| `ZonedDateTime` | Ngày + giờ + vùng múi giờ cùng offset áp dụng | Có | `2026-11-05T09:30:00+07:00[Asia/Ho_Chi_Minh]` |
| `Instant` | Thời điểm tuyệt đối trên trục UTC | Có | `2026-11-05T02:30:00Z` |
| `ZoneId` | Định danh vùng/rules múi giờ | Không phải ngày giờ | `Asia/Ho_Chi_Minh` |
| `ZoneOffset` | Độ lệch cố định so với UTC | Không phải ngày giờ | `+07:00` |

**Khác biệt cần nhớ:**

- `LocalDate` phù hợp ngày sinh, ngày báo cáo, ngày nghỉ; tự thân không có khái niệm "00:00 UTC".
- `LocalTime` phù hợp giờ mở cửa lặp lại hằng ngày; phải đi kèm ngày và vùng nếu muốn chuyển thành thời điểm.
- `LocalDateTime` phù hợp ý định "họp 09:30 ngày 05/11 tại địa phương" nhưng muốn xác định instant phải biết *địa phương nào*.
- `OffsetDateTime` giữ chênh lệch UTC tại thời điểm được biểu diễn, nhưng offset cố định không chứa quy tắc chuyển giờ mùa hè của một khu vực.
- `ZonedDateTime` giữ `ZoneId` vùng như `Europe/Paris`, từ đó áp dụng quy tắc lịch sử/DST; dạng chuỗi chứa `[Europe/Paris]` là phần mở rộng ISO của Java.
- `Instant` phù hợp dấu thời gian sự kiện, log, thời điểm phát sinh giao dịch và so sánh thứ tự tuyệt đối.

`Z` trong chuỗi như `2026-11-05T02:30:00Z` nghĩa là offset UTC `+00:00`. `Asia/Ho_Chi_Minh` là **zone ID**, còn `+07:00` là **offset**; không nên dùng hai khái niệm thay thế cho nhau khi lập lịch ở nơi có DST.

## 3. Parse và format bằng `DateTimeFormatter`

**Parse**: `String → java.time`. **Format**: `java.time → String`. Các formatter bất biến và an toàn khi tái sử dụng; khác với `SimpleDateFormat` cũ có trạng thái mutable.

Các formatter có sẵn (không cần tự tạo pattern):

| Formatter | Giá trị thích hợp | Chuỗi mẫu |
| --- | --- | --- |
| `ISO_LOCAL_DATE` | `LocalDate` | `2026-11-05` |
| `ISO_LOCAL_TIME` | `LocalTime` | `09:30:00` |
| `ISO_LOCAL_DATE_TIME` | `LocalDateTime` | `2026-11-05T09:30:00` |
| `ISO_OFFSET_TIME` | `OffsetTime` | `09:30:00+07:00` |
| `ISO_OFFSET_DATE_TIME` | `OffsetDateTime` | `2026-11-05T09:30:00+07:00` |
| `ISO_ZONED_DATE_TIME` | `ZonedDateTime` | `2026-11-05T09:30:00+07:00[Asia/Ho_Chi_Minh]` |
| `ISO_INSTANT` | `Instant` | `2026-11-05T02:30:00Z` |

Lưu ý: các formatter ISO của Java có thể cho phép lược bỏ giây/phần thập phân khi không cần; chuỗi trong bảng là ví dụ hợp lệ, **không phải khẳng định mọi lần format đều giữ đúng số ký tự**.

Với format tự chọn, các ký hiệu hay dùng:

| Ký hiệu | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `uuuu` | Năm theo lịch ISO/proleptic year | `2026` |
| `yyyy` | Năm của kỷ nguyên (year-of-era) | `2026` |
| `MM`, `dd` | Tháng, ngày 2 chữ số | `11`, `05` |
| `HH`, `mm`, `ss` | Giờ 0–23, phút, giây | `09:30:00` |
| `h`, `a` | Giờ 1–12 và AM/PM | `9 AM` |
| `SSS` | Mili giây | `123` |
| `XXX` | Offset theo dạng `+07:00` hoặc `Z` | `+07:00` |
| `VV` | `ZoneId` vùng | `Asia/Ho_Chi_Minh` |
| `'T'` | Chữ T nguyên văn, ngăn cách ngày/giờ | `2026-11-05T09:30` |

`MM` là **tháng**, `mm` là **phút**; `HH` là giờ 24h, `hh` là giờ 12h. Không dùng `YYYY` (week-based-year) thay cho `yyyy`/`uuuu` trong dữ liệu ngày lịch. Với `DateTimeFormatter` ở chế độ `ResolverStyle.STRICT`, dùng `uuuu` cho năm ISO để tránh phụ thuộc vào era của `yyyy`.

### Ví dụ Java 17+ hoàn chỉnh

Lưu thành `JavaTimeFormatsDemo.java`:

```java
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class JavaTimeFormatsDemo {
    public static void main(String[] args) {
        LocalDate day = LocalDate.parse("2026-11-05");
        LocalTime time = LocalTime.parse("09:30");
        LocalDateTime local = LocalDateTime.of(day, time);

        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        ZonedDateTime zoned = local.atZone(zone);
        OffsetDateTime offset = OffsetDateTime.parse(
                "2026-11-05T09:30:00+07:00");

        DateTimeFormatter display = DateTimeFormatter.ofPattern(
                "dd/MM/uuuu HH:mm", Locale.forLanguageTag("vi-VN"));
        DateTimeFormatter wire = DateTimeFormatter.ofPattern(
                "uuuu-MM-dd'T'HH:mm:ssXXX");

        System.out.println("LocalDate = " + day);
        System.out.println("LocalTime = " + time);
        System.out.println("LocalDateTime = " + local);
        System.out.println("OffsetDateTime = " + wire.format(offset));
        System.out.println("ZonedDateTime = " + zoned);
        System.out.println("Instant = " + offset.toInstant());
        System.out.println("Hien thi = " + display.format(zoned));

        DateTimeFormatter strictDate = DateTimeFormatter
                .ofPattern("dd/MM/uuuu")
                .withResolverStyle(ResolverStyle.STRICT);
        try {
            LocalDate.parse("31/02/2026", strictDate);
        } catch (DateTimeParseException ex) {
            System.out.println("Ngay khong hop le: bi tu choi");
        }
    }
}
```

Chạy:

```bash
javac JavaTimeFormatsDemo.java
java JavaTimeFormatsDemo
```

Kết quả:

```text
LocalDate = 2026-11-05
LocalTime = 09:30
LocalDateTime = 2026-11-05T09:30
OffsetDateTime = 2026-11-05T09:30:00+07:00
ZonedDateTime = 2026-11-05T09:30+07:00[Asia/Ho_Chi_Minh]
Instant = 2026-11-05T02:30:00Z
Hien thi = 05/11/2026 09:30
Ngay khong hop le: bi tu choi
```

`display` chỉ tạo chuỗi phục vụ người đọc, **không chuyển instant sang giờ khác**. `offset.toInstant()` mới quy đổi sang thời điểm UTC. Formatters là immutable nên có thể giữ trong `static final` và dùng chung an toàn.

## 4. Offset, zone ID, instant và việc đổi múi giờ

Giả sử cuộc hẹn được nhập `2026-11-05T09:30:00+07:00`. Vì đã biết offset, đây là `2026-11-05T02:30:00Z`. Nếu hiển thị **cùng thời điểm** cho Paris vào ngày đó, giờ địa phương là `03:30` theo offset `+01:00`.

```java
OffsetDateTime appointment =
        OffsetDateTime.parse("2026-11-05T09:30:00+07:00");
Instant instant = appointment.toInstant();

ZonedDateTime inParis =
        instant.atZone(ZoneId.of("Europe/Paris"));
ZonedDateTime inSaigon =
        instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
```

Đây là **đoạn trích minh họa**, cần các import `java.time.*` và đặt trong phương thức hoặc khối khởi tạo. `inParis` và `inSaigon` khác giờ hiển thị nhưng `toInstant()` bằng nhau.

Đặc biệt:

- `withZoneSameInstant(otherZone)`: đổi giờ hiển thị theo zone mới, **giữ nguyên instant**.
- `withZoneSameLocal(otherZone)`: cố giữ giờ trên đồng hồ, **có thể thay đổi instant**; zone mới cũng có thể điều chỉnh giờ do DST.
- `LocalDateTime.atZone(zone)`: **gán một zone với các quy tắc của nó**, không phải đổi từ UTC; phải bảo đảm zone nhập là đúng.
- `ZoneId.systemDefault()` phụ thuộc cấu hình máy chạy; tránh dựa vào nó khi giao tiếp API hoặc lưu lịch qua nhiều máy chủ.
- `Locale` quy định ngôn ngữ/ký hiệu trình bày; `ZoneId` quy định offset áp dụng theo vị trí và thời điểm. Hai thứ là độc lập.

Khi nghiệp vụ là một thời điểm đã xảy ra, lưu `Instant` hoặc timestamp với ý nghĩa UTC. Khi nghiệp vụ là lịch hẹn tương lai theo giờ địa phương, thường cần lưu **local date-time + zone ID vùng** (và chính sách xử lý DST); khi cần xác nhận một instant duy nhất, lưu cả instant đã tính hoặc offset được lựa chọn. Một offset cố định `+01:00` không mô tả đầy đủ lịch sử/quy tắc tương lai của `Europe/Paris`.

## 5. Spring MVC bind chuỗi sang `java.time` bằng `@DateTimeFormat`

Trong Spring MVC, `@RequestParam`, `@PathVariable` và các field được bind từ form qua `WebDataBinder` có thể dùng `@DateTimeFormat`; annotation khai báo **cách parse và in giá trị**.

Tùy kiểu dữ liệu, nên chọn như sau:

- `LocalDate`: `@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)` khi input ISO `yyyy-MM-dd`.
- `LocalTime`: `@DateTimeFormat(pattern = "HH:mm")` khi UI gửi `09:30`.
- `LocalDateTime`: `@DateTimeFormat(pattern = "yyyy-MM-dd'T'HH:mm")` khi UI gửi `2026-11-05T09:30`.
- `OffsetDateTime` hoặc `ZonedDateTime`: dùng `@DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)` khi client gửi date-time ISO có offset, và với `ZonedDateTime` có thể gửi thêm region ID trong ngoặc vuông theo biểu diễn Java.
- `Instant`: ưu tiên thỏa thuận chuỗi chuẩn UTC như `2026-11-05T02:30:00Z` và kiểm tra cách hệ thống bind; có thể parse rõ ràng bằng `Instant.parse` nếu thiết kế endpoint cần kiểm soát format.

**Ví dụ lớp controller Spring MVC**: file `EventQueryController.java` sau hợp lệ trong ứng dụng Spring có `spring-webmvc` và cấu hình MVC; không phải chương trình Java thuần có `main`.

```java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.OffsetDateTime;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class EventQueryController {
    @GetMapping("/events/preview")
    public String preview(
            @RequestParam("day")
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
            LocalDate day,

            @RequestParam("time")
            @DateTimeFormat(pattern = "HH:mm")
            LocalTime time,

            @RequestParam("local")
            @DateTimeFormat(pattern = "yyyy-MM-dd'T'HH:mm")
            LocalDateTime local,

            @RequestParam("at")
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
            OffsetDateTime at) {

        return day + " | " + time + " | " + local
                + " | " + at.toInstant();
    }
}
```

Ví dụ HTTP GET tới ứng dụng đã chạy (ký tự `+` trong offset phải URL-encode thành `%2B`):

```text
/events/preview?day=2026-11-05&time=09%3A30&local=2026-11-05T09%3A30&at=2026-11-05T09%3A30%3A00%2B07%3A00
```

Phần body từ phương thức (khi request được bind thành công):

```text
2026-11-05 | 09:30 | 2026-11-05T09:30 | 2026-11-05T02:30:00Z
```

Các query/form parameter ở ví dụ này là **bốn giá trị độc lập**; `local` không tự trở thành instant. `at` xác định instant vì chuỗi có offset. Trên HTTP, dấu `+` không escape trong `application/x-www-form-urlencoded` có thể bị giải mã thành khoảng trắng, gây lỗi parse.

### Model bind từ HTML form

Ví dụ form có ba field kiểu date/time/datetime-local:

```html
<input type="date" name="day">
<input type="time" name="time">
<input type="datetime-local" name="local">
```

Khi submit, trình duyệt thường gửi các dạng `yyyy-MM-dd`, `HH:mm` (có thể có giây) và `yyyy-MM-ddTHH:mm`. **`datetime-local` không gửi offset hoặc zone**. Backend phải nhận thêm zone do nghiệp vụ xác định, chẳng hạn một trường `zoneId` là `Asia/Ho_Chi_Minh`, hoặc lấy từ cấu hình sự kiện; không tự giả định đó là giờ UTC.

Một field trong form model có thể khai báo:

```java
@DateTimeFormat(pattern = "yyyy-MM-dd'T'HH:mm")
private LocalDateTime local;
```

Đây là **đoạn field minh họa**, cần đặt trong một model với import `java.time.LocalDateTime` và `org.springframework.format.annotation.DateTimeFormat` cùng cơ chế truy cập thuộc tính phù hợp (getter/setter hoặc binding constructor).

## 6. `@DateTimeFormat`: `iso`, `pattern`, `style`, `fallbackPatterns`

`@DateTimeFormat` có ba cách khai báo format chính:

| Thuộc tính | Ý nghĩa | Dùng khi |
| --- | --- | --- |
| `iso` | Mẫu ISO qua `ISO.DATE`, `ISO.TIME`, `ISO.DATE_TIME` | Hợp đồng API ổn định |
| `pattern` | Pattern được kiểm soát, ví dụ `dd/MM/yyyy` | Form/UI có format xác định |
| `style` | Format theo locale/JDK, ví dụ `"S-"` cho ngày ngắn | Giao diện thích ứng ngôn ngữ |

Nếu khai báo nhiều thuộc tính, `pattern` được ưu tiên hơn `iso`, còn `iso` được ưu tiên hơn `style`. Nên **chỉ khai báo một** theo mục đích. `fallbackPatterns` là các format bổ sung khi **parse** thất bại; khi **in**, Spring vẫn dùng format chính.

Ví dụ nhận ngày ISO đồng thời hỗ trợ input ngày cũ từ người dùng:

```java
@DateTimeFormat(
        iso = DateTimeFormat.ISO.DATE,
        fallbackPatterns = {"dd/MM/yyyy", "d/M/yyyy"})
private LocalDate day;
```

Đây là **đoạn field minh họa** trong một bean có import phù hợp. Ví dụ `05/11/2026` có thể được parse từ fallback, còn hiển thị chuẩn vẫn theo ISO là `2026-11-05`. Không dùng nhiều format đầu vào mà thiếu quy tắc rõ ràng, vì `05/11/2026` có thể bị hiểu là 5/11 hoặc 11/5 ở các hệ thống khác nhau.

**Lưu ý JDK 20+**: style format dựa vào CLDR/locale có thể đổi cách biểu diễn khoảng trắng, AM/PM và ngày giờ giữa các bản JDK. Spring khuyến nghị ưu tiên ISO hoặc pattern do ứng dụng kiểm soát, và chỉ dùng fallback khi cần tương thích đầu vào cũ.

Trong Javadoc của `@DateTimeFormat`, quy tắc time zone áp dụng cho `java.util.Date` kiểu legacy: với `iso`, formatter dùng UTC; với `style`/`pattern`, dùng default time zone của JVM. **Không diễn giải câu đó thành "mọi LocalDateTime có UTC"**: `LocalDateTime` không mang zone. Với `ZonedDateTime`/`OffsetDateTime`, chuỗi có offset hoặc vùng cần phản ánh đúng nghiệp vụ.

## 7. Cấu hình định dạng toàn cục trong Spring

Khi nhiều field cần một quy ước chung, có thể cấu hình `FormattingConversionService` thay vì lặp cùng pattern khắp nơi. `DateTimeFormatterRegistrar` đăng ký formatter cho các kiểu `java.time`, ví dụ:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.format.datetime.standard.DateTimeFormatterRegistrar;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class DateTimeMvcConfiguration implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        DateTimeFormatterRegistrar registrar =
                new DateTimeFormatterRegistrar();
        registrar.setUseIsoFormat(true);
        registrar.registerFormatters(registry);
    }
}
```

Đây là **lớp cấu hình Spring MVC**, cần các dependency và khởi động application context tương ứng; không chạy bằng `java DateTimeMvcConfiguration`. `setUseIsoFormat(true)` chọn định dạng ISO chuẩn thay cho style mặc định của registrar. Việc có cần cấu hình này hay không phụ thuộc vào phiên bản Spring, cấu hình MVC và các formatter đã đăng ký sẵn; **đừng đăng ký trùng chỉ vì một ví dụ hướng dẫn**. Với field có hợp đồng cụ thể, khai báo `@DateTimeFormat` tại field/parameter thường dễ đọc hơn.

`DateTimeFormatterRegistrar` cũng hỗ trợ `setDateFormatter(...)`, `setTimeFormatter(...)` và `setDateTimeFormatter(...)` khi thật sự cần một formatter cụ thể. Không ép tất cả các kiểu date/time vào một pattern vốn yêu cầu trường mà kiểu đó không có: ví dụ `LocalDate` không có giờ, `LocalDateTime` không có offset.

## 8. DST: local date-time có thể không tồn tại hoặc tồn tại hai lần

Quy tắc daylight saving time (DST) của một `ZoneId` làm phép gán `LocalDateTime → ZonedDateTime` không luôn một-một:

- **Normal**: một offset hợp lệ.
- **Gap** (đồng hồ nhảy tới trước): **không offset hợp lệ** cho một số giờ địa phương.
- **Overlap** (đồng hồ lùi lại): **hai offset hợp lệ** cho cùng giờ địa phương.

Ví dụ với `Europe/Paris` năm 2026, 02:30 ngày **29/03/2026** rơi vào *gap*; 02:30 ngày **25/10/2026** rơi vào *overlap*. `atZone` có hành vi mặc định: điều chỉnh giờ bị gap về sau; với overlap chọn offset sớm hơn trong hai offset hợp lệ. Nếu nghiệp vụ đặt lịch cần tính chính xác, phải kiểm tra và có quy tắc xử lý rõ ràng, **không âm thầm chấp nhận lựa chọn mặc định**.

Ví dụ hoàn chỉnh `DstRulesDemo.java`, Java 17+:

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.zone.ZoneRules;

public class DstRulesDemo {
    public static void main(String[] args) {
        ZoneId paris = ZoneId.of("Europe/Paris");
        ZoneRules rules = paris.getRules();

        LocalDateTime gap =
                LocalDateTime.of(2026, 3, 29, 2, 30);
        System.out.println("Gap offsets: " + rules.getValidOffsets(gap));
        System.out.println("Gap atZone: " + gap.atZone(paris));

        LocalDateTime overlap =
                LocalDateTime.of(2026, 10, 25, 2, 30);
        System.out.println("Overlap offsets: "
                + rules.getValidOffsets(overlap));

        ZonedDateTime earlier = overlap.atZone(paris);
        ZonedDateTime later = earlier.withLaterOffsetAtOverlap();
        System.out.println("Earlier instant: " + earlier.toInstant());
        System.out.println("Later instant: " + later.toInstant());
    }
}
```

```bash
javac DstRulesDemo.java
java DstRulesDemo
```

```text
Gap offsets: []
Gap atZone: 2026-03-29T03:30+02:00[Europe/Paris]
Overlap offsets: [+02:00, +01:00]
Earlier instant: 2026-10-25T00:30:00Z
Later instant: 2026-10-25T01:30:00Z
```

Tại overlap, hai kết quả cách nhau **đúng một giờ** dù đều là `02:30` trên đồng hồ ở Paris. Vì thế không thể suy một instant chính xác từ `LocalDateTime` cùng `ZoneId` mà thiếu chính sách với trường hợp hai offset.

Ví dụ quyết định từ chối thời gian mơ hồ trong nghiệp vụ:

```java
var valid = zone.getRules().getValidOffsets(localDateTime);
if (valid.size() != 1) {
    throw new IllegalArgumentException(
            "Local date-time is ambiguous or invalid in this zone");
}
Instant instant = ZonedDateTime
        .ofStrict(localDateTime, valid.get(0), zone)
        .toInstant();
```

Đây là **đoạn trích minh họa**: `zone` là `ZoneId` hợp lệ, `localDateTime` là `LocalDateTime`; cần import các kiểu `java.time`. Tùy nghiệp vụ, thay vì từ chối overlap có thể hỏi người dùng chọn offset `+02:00` hoặc `+01:00`; với gap có thể đề nghị giờ khác.

## 9. Bind query/form khác với JSON `@RequestBody`

Đây là lỗi cấu hình rất thường gặp:

- `@DateTimeFormat` làm việc trong **Spring formatting/conversion khi bind chuỗi** (query param, path, form/model).
- JSON `@RequestBody` thường do **Jackson `HttpMessageConverter`** xử lý; annotation `@DateTimeFormat` không phải bộ điều khiển chuẩn của JSON serializer/deserializer.
- Với Jackson, kiểu `java.time` cần hỗ trợ Java Time module, thường được Spring Boot cấu hình khi dependency tương ứng hiện diện. Format JSON được quyết định bởi Jackson và cấu hình/annotation của Jackson như `@JsonFormat`, không phải tự động bởi field formatter MVC.

Ví dụ JSON truyền thời điểm có offset:

```json
{
  "name": "Daily sync",
  "day": "2026-11-05",
  "localTime": "09:30:00",
  "startsAt": "2026-11-05T09:30:00+07:00"
}
```

Trong DTO, dùng `LocalDate`, `LocalTime` và `OffsetDateTime` tương ứng khi hợp đồng API có đúng ngữ nghĩa này. Nếu client gửi `"2026-11-05T09:30:00"` mà DTO muốn `OffsetDateTime`, **thiếu offset** là dữ liệu không đủ. Không tự thêm `Z` vào cuối chuỗi trừ khi hệ thống đã thực sự xác định giờ đó là UTC.

Ví dụ một cấu hình hiển thị JSON riêng của Jackson (đoạn field, không phải lớp độc lập):

```java
@com.fasterxml.jackson.annotation.JsonFormat(
        pattern = "yyyy-MM-dd'T'HH:mm:ssXXX")
private OffsetDateTime startsAt;
```

Đối với hệ thống dùng REST, cần thống nhất quy tắc JSON, query, form và database theo **cùng hợp đồng ngày giờ**; có thể cùng dạng ISO nhưng không có nghĩa các tầng dùng cùng annotation.

## 10. Quy trình thiết kế điển hình: người dùng chọn ngày, giờ và vùng

Giả sử ứng dụng đặt lịch cho một chi nhánh tại Paris. Form gửi:

```text
date=2026-10-25
time=02:30
zoneId=Europe/Paris
```

**Quy trình đúng về mặt dữ liệu:**

1. Bind `date` vào `LocalDate`, `time` vào `LocalTime`, `zoneId` thành `ZoneId` (hoặc tra từ chi nhánh đã được xác thực).
2. Tạo `LocalDateTime.of(date, time)`. **Chưa có instant**.
3. Dùng `zone.getRules().getValidOffsets(local)` để kiểm tra DST. Với ví dụ trên, có **hai** offset hợp lệ.
4. Áp dụng chính sách: yêu cầu lựa chọn, từ chối giờ mơ hồ hoặc chọn một offset theo thỏa thuận sản phẩm. Sau khi chọn, dùng `ZonedDateTime.ofStrict(local, chosenOffset, zone).toInstant()`.
5. Lưu instant đã xác định để xử lý thời điểm thực thi; giữ zone ID và local time nếu phải tái hiện mục đích/lịch theo giờ địa phương. Khi hiển thị cho người dùng ở nơi khác, chuyển instant qua `atZone(viewerZone)`.

Nếu hệ thống lên lịch **mỗi thứ Hai lúc 09:30 theo giờ Paris** trong nhiều tháng, chỉ lưu instant lặp lại cộng thêm 7 × 24 giờ có thể không giữ nguyên 09:30 khi đổi DST. Đó là lịch định kỳ theo **wall-clock time**, nên cần quy tắc `LocalTime` + `ZoneId` + lịch ngày, rồi tính từng instant theo ngày tương ứng.

## 11. Lỗi phổ biến và cách phòng tránh

| Lỗi | Vì sao sai | Hướng giải quyết |
| --- | --- | --- |
| Dùng `LocalDateTime` làm timestamp toàn cầu | Không có offset/zone để suy instant | Chọn `Instant`/`OffsetDateTime` hoặc kết hợp `ZoneId` theo nghiệp vụ |
| Gán ngầm `ZoneId.systemDefault()` | Kết quả đổi theo máy chủ/container | Dùng zone rõ ràng từ hợp đồng hoặc cấu hình |
| Xem `+07:00` là vùng `Asia/Ho_Chi_Minh` | Offset cố định không có quy tắc lịch sử/DST | Giữ `ZoneId` vùng nếu lịch cần tuân quy tắc địa phương |
| Đổi zone bằng `withZoneSameLocal` khi muốn cùng instant | Có thể đổi ý nghĩa thời điểm | Dùng `withZoneSameInstant` |
| Viết `YYYY-MM-dd` hoặc nhầm `MM`/`mm` | Sinh dữ liệu sai gần chuyển năm hoặc lẫn tháng/phút | Dùng `uuuu`/`yyyy` và đúng token |
| Quên URL-encode dấu `+` | `+07:00` có thể thành ` 07:00` | Encode `%2B` |
| Mong `@DateTimeFormat` định dạng JSON | JSON do converter/Jackson phụ trách | Đặt quy ước ở lớp JSON đúng nơi |
| Tin `datetime-local` có timezone | Control này chỉ truyền giờ địa phương | Truyền thêm vùng múi giờ |
| Bỏ qua DST gap/overlap | Giờ có thể không tồn tại hoặc có hai instant | Kiểm tra `ZoneRules.getValidOffsets` |
| Dùng `SimpleDateFormat` dùng chung giữa luồng | Formatter cũ có trạng thái mutable | Dùng `DateTimeFormatter` bất biến |
| Parse "31/02" mà không kiểm tra | Dữ liệu không hợp lệ | Parser strict, kiểm thử trường hợp lỗi |
| Phụ thuộc default `style` theo locale/JDK | Kết quả có thể thay đổi theo CLDR/JDK | Ưu tiên ISO hoặc pattern được kiểm soát |

Trong MVC, input sai kiểu thường dẫn đến lỗi binding/`typeMismatch` hoặc phản hồi HTTP 400 (tùy chữ ký endpoint và cơ chế xử lý ngoại lệ). Với `@ModelAttribute`, dùng `BindingResult` đúng vị trí để đọc lỗi field; với JSON, lỗi parse xảy ra trong HTTP message converter. Không xử lý lỗi bằng cách âm thầm chọn một timezone khác.

## 12. Kiểm thử thiết thực

Nên có ít nhất các tình huống sau cho phần format và bind:

1. `LocalDate`: ngày hợp lệ `2024-02-29` và ngày sai `2025-02-29`.
2. `LocalTime`: `09:30` so với `9:30 PM`, bảo đảm pattern đúng kiểu 24h/12h.
3. `LocalDateTime`: input `2026-11-05T09:30` không bị chuyển ngầm sang UTC.
4. `OffsetDateTime`: `2026-11-05T09:30+07:00` và `2026-11-05T02:30Z` phải tạo **cùng instant**.
5. `ZonedDateTime`: test zone `Europe/Paris` tại gap và overlap; trong trường hợp overlap không tự đoán offset theo ý người dùng.
6. MVC query: xác thực annotation `@DateTimeFormat`, ký tự `+` được percent-encode; input sai trả lỗi phù hợp.
7. JSON body: xác thực module Jackson và định dạng mong muốn, độc lập với cấu hình format query/form.
8. Nhiều zone, locale và môi trường: không dựa vào timezone của máy chạy; sử dụng `Clock.fixed(...)` khi cần test liên quan đến "bây giờ".

**Tự kiểm tra:** Nếu form gửi `2026-11-05T09:30`, có thể lập tức lưu `Instant.parse("2026-11-05T09:30Z")` không? **Không.** Không có bằng chứng `09:30` là UTC; phải biết zone/offset và chính sách nghiệp vụ trước. Nếu form gửi `2026-11-05T09:30+07:00` thì có thể đổi thành `Instant` — vì offset đã xác định thời điểm.

## Tài liệu tham khảo

- Spring Framework Reference — Field Formatting: https://docs.spring.io/spring-framework/reference/core/validation/format.html
- Spring Framework Reference — Configuring a Global Date and Time Format: https://docs.spring.io/spring-framework/reference/core/validation/format-configuring-formatting-globaldatetimeformat.html
- Spring Framework API — `DateTimeFormat`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/annotation/DateTimeFormat.html
- Spring Framework API — `DateTimeFormatterRegistrar`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/datetime/standard/DateTimeFormatterRegistrar.html
- Spring Framework wiki — Date and Time Formatting with JDK 20 and higher: https://github.com/spring-projects/spring-framework/wiki/Date-and-Time-Formatting-with-JDK-20-and-higher
- Java SE API — `DateTimeFormatter`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html
- Java SE API — `ZonedDateTime`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html

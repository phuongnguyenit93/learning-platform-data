# Các gói `java.time`, `java.time.temporal`, `java.time.format`, `java.time.zone` và `java.time.chrono`

## 1. Mục tiêu và bản đồ tổng quan

Java 8 giới thiệu **Date and Time API (JSR 310)** trong module `java.base`, thay thế phần lớn việc phải dùng `java.util.Date`, `Calendar`, `SimpleDateFormat` cho code mới. Trong Java 17+, bộ API được tổ chức thành **một gói chính** `java.time` và **bốn gói con** mà bài này cần nắm: `temporal`, `format`, `zone`, `chrono`. Chúng giải quyết những lớp vấn đề khác nhau, nhưng phối hợp qua các interface và kiểu dữ liệu nhất quán.

Sau bài học, bạn có thể:

1. Xác định gói cần import khi xử lý ngày, giờ, khoảng thời gian, timezone, định dạng hay hệ lịch phi ISO.
2. Giải thích cách `LocalDate`/`ZonedDateTime` dùng `TemporalField`, `TemporalUnit`, `TemporalAdjuster`, `DateTimeFormatter`, `ZoneRules` và `Chronology`.
3. Đọc được ví dụ kết hợp cả năm gói, chọn đúng API cho bài toán thực tế, xử lý các trường hợp biên DST và lỗi định dạng.
4. Phân biệt **múi giờ** (quy tắc offset/DST) với **hệ lịch** (cách biểu diễn năm/tháng/ngày, ví dụ ISO hay Nhật Bản).

Sơ đồ trách nhiệm:

```text
java.base
└── java.time                 → Các kiểu ngày, giờ, instant, duration, zone ID
    ├── temporal              → Field, unit, query, phép điều chỉnh thời gian
    ├── format                → Parse, format, locale, pattern, resolver style
    ├── zone                  → Quy tắc offset, các lần chuyển giờ và tzdb
    └── chrono                → Các hệ lịch khác ISO, era và ngày lịch tương ứng
```

| Gói | Trả lời câu hỏi | API thường dùng | Điểm phân biệt |
| --- | --- | --- | --- |
| `java.time` | “Dữ liệu ngày giờ của tôi là loại gì?” | `LocalDate`, `LocalTime`, `LocalDateTime`, `Instant`, `ZonedDateTime`, `ZoneId`, `Period`, `Duration`, `Clock` | Mô hình dữ liệu và phép toán cấp cao |
| `java.time.temporal` | “Lấy trường nào, tính theo đơn vị nào, chỉnh ngày theo quy tắc gì?” | `ChronoField`, `ChronoUnit`, `TemporalAdjusters`, `WeekFields`, `TemporalQueries` | Tầng field/unit/query/adjuster dùng chung |
| `java.time.format` | “Đọc/hiển thị chuỗi ngày giờ thế nào?” | `DateTimeFormatter`, `DateTimeFormatterBuilder`, `FormatStyle`, `ResolverStyle`, `TextStyle` | Parsing, in chuỗi, ngôn ngữ và chế độ xác thực |
| `java.time.zone` | “Tại vùng này, ngày giờ địa phương hợp lệ với những offset nào?” | `ZoneRules`, `ZoneOffsetTransition`, `ZoneOffsetTransitionRule`, `ZoneRulesProvider` | Quy tắc và lịch sử chuyển offset, gap/overlap |
| `java.time.chrono` | “Biểu diễn cùng ngày bằng hệ lịch nào?” | `Chronology`, `ChronoLocalDate`, `JapaneseDate`, `ThaiBuddhistDate`, `HijrahDate` | Lịch phi ISO, niên hiệu và biểu diễn theo văn hóa |

**Lưu ý về import:** `import java.time.*;` **không** import các lớp trong `java.time.temporal`, `java.time.format`, `java.time.zone` hay `java.time.chrono`. Java chỉ import những kiểu trực tiếp thuộc package được nêu. Cần import từng package con hoặc lớp cụ thể.

## 2. Gói `java.time` — mô hình chính, nên học đầu tiên

`java.time` cung cấp kiểu dữ liệu phù hợp với ngữ nghĩa của sự kiện, thay vì gói mọi thứ trong một kiểu “date”.

| Kiểu | Mang thông tin | Ví dụ sử dụng | Lưu ý |
| --- | --- | --- | --- |
| `LocalDate` | Năm-tháng-ngày theo lịch ISO, không có giờ/offset | Ngày sinh, ngày hết hạn theo lịch | Không thể xác định `Instant` chỉ từ một ngày |
| `LocalTime` | Giờ-phút-giây-nano trong ngày, không có ngày/múi giờ | Giờ cửa hàng mở cửa | `09:00` không tự xác định nơi nào |
| `LocalDateTime` | Ngày và giờ địa phương | 09:30 ngày họp tại một văn phòng | Chưa đủ để biết một mốc UTC duy nhất |
| `Instant` | Một thời điểm tuyệt đối trên dòng thời gian | Timestamp giao dịch, log | Thường là lựa chọn tốt để lưu event đã xảy ra |
| `OffsetDateTime` | Ngày giờ và offset như `+07:00` | Payload API kèm offset | Offset không chứa quy tắc DST theo vùng |
| `ZonedDateTime` | Ngày giờ, `ZoneId` và offset đã giải quyết | Cuộc họp trong `Europe/Paris` | Giải quyết theo quy tắc vùng được cung cấp bởi tzdb |
| `ZoneId` / `ZoneOffset` | ID vùng / độ lệch so với UTC | `Asia/Ho_Chi_Minh` / `+07:00` | Vùng có thể đổi offset theo lịch sử |
| `Duration` / `Period` | Khoảng giây-nano / khoảng năm-tháng-ngày | Timeout / hạn theo tháng | Không hoán đổi khi cần đúng nghĩa ngày lịch |
| `Year`, `YearMonth`, `MonthDay` | Phần ngày theo cấu trúc có ý nghĩa | Kỳ báo cáo tháng, sinh nhật lặp | Tránh tự chèn ngày/tháng giả |
| `DayOfWeek`, `Month` | Enum cho thứ và tháng | Quy tắc chỉ ngày trong tuần | Có thể dùng với `TemporalAdjusters` |
| `Clock` | Nguồn thời gian và múi giờ tùy chọn | Service phụ thuộc “bây giờ” | Tiêm `Clock.fixed` để kiểm thử |

Ví dụ thao tác thuần `java.time`:

```java
import java.time.LocalDate;
import java.time.Period;

LocalDate ordered = LocalDate.of(2026, 10, 24);
LocalDate delivered = ordered.plusDays(5);
Period window = Period.between(ordered, delivered);
```

Đây là **đoạn minh họa** đặt bên trong method/class, không phải file Java độc lập. Kết quả `delivered` là `2026-10-29`; `window` là period 5 ngày. `ordered` không thay đổi do API sử dụng immutable objects. `LocalDate` dùng lịch ISO (Gregorian kéo dài về quá khứ), không “biết” giờ mùa hè.

Chuyển đổi quan trọng:

```java
import java.time.*;

Instant instant = Instant.parse("2026-10-24T02:30:00Z");
ZonedDateTime hcm = instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
LocalDate localCalendarDate = hcm.toLocalDate();
Instant roundTrip = hcm.toInstant();
```

Ở đây `hcm` hiển thị 09:30 ngày 24/10/2026 tại TP.HCM; `roundTrip.equals(instant)` là `true`. `toLocalDate()` chỉ giữ **ngày theo vùng đã chọn**, có thể khác ngày UTC của `instant`. Nếu đầu vào chỉ là `LocalDateTime`, bạn phải biết `ZoneId` và chính sách xử lý DST trước khi tạo mốc chính xác.

## 3. Gói `java.time.temporal` — field, unit và quy tắc điều chỉnh

Gói này bổ sung khả năng hỏi/sửa các trường thời gian và phép tính tổng quát. API sử dụng các interface trừu tượng; khi mới học, hãy ưu tiên lớp tiện ích có sẵn rồi tìm đến interface khi thực sự cần khái quát hóa.

### 3.1. Các interface nền tảng

- `TemporalAccessor`: cung cấp **đọc** các trường thông qua `isSupported(TemporalField)`, `get(...)`, `getLong(...)` và `query(...)`. Không hứa có phép toán cộng/sửa. `DayOfWeek` và một số giá trị khác có thể được đọc theo cách này.
- `Temporal`: mở rộng `TemporalAccessor` để hỗ trợ `with(field, value)` và `plus/minus(unit)`; các kiểu cụ thể vẫn trả giá trị mới, không mutate tại chỗ.
- `TemporalField`: mô tả **một trường** như ngày trong tháng, giờ trong ngày. Enum hay dùng là `ChronoField`.
- `TemporalUnit`: mô tả **một đơn vị** như ngày, tuần, phút. Enum hay dùng là `ChronoUnit`.
- `TemporalAmount`: lượng thời gian dùng với `plus(TemporalAmount)` như `Period` hoặc `Duration`.
- `TemporalAdjuster`: hàm điều chỉnh thời gian theo một quy tắc; factory có sẵn ở `TemporalAdjusters`.
- `TemporalQuery<R>`: chiến lược trích thông tin từ `TemporalAccessor`; nhiều query có sẵn trong `TemporalQueries`.

Không phải kiểu nào cũng hỗ trợ mọi field/unit: `LocalDate` không chứa `HOUR_OF_DAY`; `LocalTime` không chứa `DAY_OF_MONTH`. Kiểm tra `isSupported` hoặc sử dụng method đặc thù trước khi truy vấn theo field. `get(...)` trả `int` và có thể không phù hợp với giá trị lớn; `getLong(...)` dùng khi cần `long`.

### 3.2. Field khác unit

`ChronoField.DAY_OF_MONTH` là **vị trí ngày trong tháng** (1–28/29/30/31). `ChronoUnit.DAYS` là **đơn vị đếm thời lượng/ngày theo kiểu temporal**; hai đối tượng giải quyết câu hỏi khác nhau.

```java
import java.time.LocalDate;
import java.time.temporal.ChronoField;
import java.time.temporal.ChronoUnit;

LocalDate d = LocalDate.of(2026, 10, 24);
int day = d.get(ChronoField.DAY_OF_MONTH); // 24
LocalDate revised = d.with(ChronoField.DAY_OF_MONTH, 1); // 2026-10-01
long days = ChronoUnit.DAYS.between(d, LocalDate.of(2026, 10, 31)); // 7
```

Trong ứng dụng đơn giản, `d.getDayOfMonth()`, `d.withDayOfMonth(1)` và `d.until(end, ChronoUnit.DAYS)` thường dễ đọc hơn. `ChronoField`/`ChronoUnit` hữu ích khi field/unit được chọn động hoặc code phải làm việc với nhiều loại `Temporal`.

### 3.3. `TemporalAdjusters` và `WeekFields`

`TemporalAdjusters` có các quy tắc phổ biến: `firstDayOfMonth()`, `lastDayOfMonth()`, `firstDayOfNextMonth()`, `next(DayOfWeek.MONDAY)`, `nextOrSame(...)`, `firstInMonth(...)`, `lastInMonth(...)` và `dayOfWeekInMonth(...)`.

```java
import java.time.*;
import java.time.temporal.*;

LocalDate d = LocalDate.of(2026, 10, 24);
LocalDate firstMonday =
    d.with(TemporalAdjusters.firstInMonth(DayOfWeek.MONDAY)); // 2026-10-05
LocalDate nextMonday =
    d.with(TemporalAdjusters.next(DayOfWeek.MONDAY)); // 2026-10-26
```

Điểm phân biệt: `next(MONDAY)` **luôn tiến đến thứ Hai tiếp theo** ngay cả khi ngày ban đầu là thứ Hai; `nextOrSame(MONDAY)` giữ nguyên nếu đã trùng thứ.

`WeekFields` cho phép định nghĩa tuần bắt đầu vào thứ nào và tuần đầu năm cần tối thiểu mấy ngày; ví dụ `WeekFields.ISO` bắt đầu thứ Hai, yêu cầu ít nhất 4 ngày trong tuần đầu. `WeekFields.of(Locale)` phụ thuộc quy ước vùng. **Tuần của năm** có thể chuyển sang week-based-year khác ở sát ngày 01/01, không nên dùng “năm của tuần” như năm dương lịch thông thường.

`IsoFields` cung cấp các trường ISO nâng cao như `QUARTER_OF_YEAR`, `WEEK_OF_WEEK_BASED_YEAR` và `WEEK_BASED_YEAR`; `JulianFields` phục vụ hệ đếm ngày Julian/modified Julian, dành cho tích hợp chuyên biệt.

### 3.4. `TemporalQueries` và lỗi thiếu trường

`TemporalQueries.zone()`, `offset()`, `localDate()`, `localTime()`, `precision()` cho phép trích thông tin có sẵn; nhiều query trả `null` nếu input không chứa dữ liệu phù hợp. Đừng tự suy diễn timezone chỉ từ `LocalDateTime`.

Một số phép gọi có thể ném `UnsupportedTemporalTypeException`. Ví dụ truy cập `ChronoField.HOUR_OF_DAY` trên `LocalDate` là vô nghĩa; dùng `isSupported(...)` để bảo vệ nếu input có kiểu không xác định.

## 4. Gói `java.time.format` — đổi giữa đối tượng và văn bản

Gói này chứa logic chuyển chuỗi qua lại đối tượng ngày giờ. `DateTimeFormatter` là điểm bắt đầu; `DateTimeFormatterBuilder` dùng để ghép các thành phần tùy biến/phần tùy chọn. Formatter có thể được tái sử dụng vì immutable và thread-safe.

### 4.1. Chuẩn mặc định và pattern

Khi dữ liệu truyền giữa hệ thống, ưu tiên `DateTimeFormatter.ISO_LOCAL_DATE`, `ISO_INSTANT`, `ISO_OFFSET_DATE_TIME` hoặc `ISO_ZONED_DATE_TIME` tương ứng với **ngữ nghĩa trường**, không chỉ kiểu chuỗi nhìn đẹp.

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

DateTimeFormatter strict = DateTimeFormatter
    .ofPattern("dd/MM/uuuu", Locale.ROOT)
    .withResolverStyle(ResolverStyle.STRICT);

LocalDate d = LocalDate.parse("31/12/2026", strict); // 2026-12-31
String out = d.format(strict);                        // "31/12/2026"
```

Đây là **snippet trong một method**, không phải chương trình hoàn chỉnh. Khi nhận `31/02/2026`, `LocalDate.parse(..., strict)` ném `DateTimeParseException`. Nếu chỉ dùng formatter tạo từ `ofPattern(...)`, resolver style mặc định là `SMART`; vì thế phải chọn `STRICT` khi đòi hỏi khước từ mọi ngày không hợp lệ. `DateTimeFormatter.ISO_LOCAL_DATE` đã dùng strict theo đặc tả JDK.

| Ký tự pattern | Ý nghĩa | Lỗi thường gặp |
| --- | --- | --- |
| `u` / `uuuu` | Proleptic year theo lịch | Phân biệt với `y`: year-of-era |
| `M` / `MM` | Tháng | `mm` là phút |
| `d` / `dd` | Ngày trong tháng | `D` là ngày trong năm |
| `H` / `HH` | Giờ 0–23 | `h` là giờ 1–12 và cần AM/PM khi parse |
| `m` / `mm` | Phút | Không nhầm `M` |
| `s` / `ss` | Giây | Không nhầm `S` là phần thập phân của giây |
| `X` / `XXX` | UTC offset với ký hiệu `Z` cho offset 0 | Không phải ID vùng |
| `V` / `VV` | Zone ID (pattern thực tế dùng `VV`) | Cần dữ liệu mang `ZoneId` |
| `Y` / `YYYY` | Week-based-year | Có thể lệch năm ở cuối/đầu năm |

Không ghép `LocalDate` với pattern yêu cầu giờ, offset hay zone khi nó không mang các trường đó: formatter có thể ném `UnsupportedTemporalTypeException`. Khi ứng dụng cần hiển thị tên tháng theo ngôn ngữ, truyền `Locale` một cách minh bạch, ví dụ `Locale.forLanguageTag("vi-VN")`, và cân nhắc `FormatStyle.SHORT/MEDIUM/LONG/FULL` bằng `DateTimeFormatter.ofLocalizedDate(...)`.

### 4.2. Formatter và TemporalAccessor

Đọc chuỗi bằng `formatter.parse(text)` tạo `TemporalAccessor`, nhưng không phải chuỗi nào cũng đủ thông tin cho mọi kiểu. Nên dùng `LocalDate.parse(text, formatter)` hoặc `ZonedDateTime.parse(text, formatter)` khi kiểu kỳ vọng đã rõ. Có thể dùng `formatter.parse(text, LocalDate::from)` để lấy đúng kiểu mong muốn.

`ResolverStyle.STRICT` kiểm tra chặt khi giải quyết các trường thành ngày; `SMART` có thể thực hiện điều chỉnh trong một số tình huống; `LENIENT` chấp nhận phép cộng dồn các trường theo quy tắc nới lỏng. Không nhầm **kiểm tra ngày hợp lệ** với **kiểm tra giờ địa phương có tồn tại trong múi giờ vùng hay không**: trường hợp thứ hai thuộc `java.time.zone`.

`DateTimeFormatterBuilder` thường dùng khi giao thức có đoạn tùy chọn, format ghép nhiều field hoặc cần chế độ parse linh hoạt. Đừng sử dụng builder khi constant ISO hay pattern đơn giản đã đủ.

## 5. Gói `java.time.zone` — quy tắc offset và DST

**`ZoneId` nằm trong `java.time`, còn quy tắc của nó nằm trong `java.time.zone`.** Một `ZoneId` thường tham chiếu tới cơ sở dữ liệu quy tắc vùng (tzdb). Thời điểm UTC và giờ địa phương không đồng nghĩa; offset còn có thể thay đổi do Daylight Saving Time (DST) hoặc thay đổi pháp lý.

- `ZoneRules`: mô tả offset hợp lệ theo thời điểm hoặc theo local date-time. Lấy qua `zone.getRules()`.
- `ZoneOffsetTransition`: thông tin cụ thể cho một lần chuyển offset, có `isGap()`, `isOverlap()`, `getOffsetBefore()`, `getOffsetAfter()`, `getDateTimeBefore()`, `getDateTimeAfter()`.
- `ZoneOffsetTransitionRule`: quy tắc tạo các transition lặp lại (thường liên quan đổi mùa); là API nâng cao.
- `ZoneRulesProvider`: cung cấp danh sách zone và rules cho runtime; thường **không cần gọi trực tiếp trong business code**. Khác phiên bản tzdb/JDK có thể cho quy tắc lịch sử hoặc tương lai khác nhau.
- `ZoneRulesException`: lỗi liên quan đến zone rules không có hoặc không khả dụng.

### 5.1. Gap và overlap — phân biệt bằng `getValidOffsets`

Khi người dùng nhập giờ hẹn `LocalDateTime local` tại một `ZoneId zone`:

```java
import java.time.*;
import java.time.zone.ZoneRules;
import java.util.List;

ZoneId zone = ZoneId.of("America/New_York");
LocalDateTime local = LocalDateTime.of(2026, 11, 1, 1, 30);
ZoneRules rules = zone.getRules();
List<ZoneOffset> offsets = rules.getValidOffsets(local);

if (offsets.isEmpty()) {
    // Gap: giờ địa phương không tồn tại, cần chính sách xử lý.
} else if (offsets.size() == 2) {
    // Overlap: cùng giờ địa phương xuất hiện hai lần.
} else {
    // Thông thường có đúng một offset hợp lệ.
}
```

Snippet trên dùng Java 17 và giả định chạy **bên trong method**; các nhánh chỉ minh họa hướng xử lý nghiệp vụ.

- **Gap:** New York ngày 08/03/2026 chuyển từ `-05:00` sang `-04:00`, vì thế **02:30** không tồn tại; `getValidOffsets(...)` trả danh sách rỗng. `local.atZone(zone)` mặc định dời thời gian tới 03:30, nên với booking quan trọng phải cân nhắc từ chối trước.
- **Overlap:** New York ngày 01/11/2026 có **01:30** hai lần; danh sách có hai offset (`-04:00` và `-05:00`). `local.atZone(zone)` mặc định ưu tiên offset sớm hơn; để chọn lần thứ hai có thể gọi `withLaterOffsetAtOverlap()`.
- **Trường hợp thường:** danh sách có một offset. Nếu bạn đã chọn offset hợp lệ, `ZonedDateTime.ofStrict(local, selectedOffset, zone)` giúp kiểm tra tính nhất quán và từ chối offset không hợp lệ.

Khi `getValidOffsets(local)` trả 0 hoặc 2, đừng âm thầm lấy offset tùy ý cho giao dịch tài chính/đặt lịch; quy tắc chọn phải thuộc yêu cầu nghiệp vụ. `zone.getRules().getTransition(local)` trả thông tin transition cho gap/overlap; thường là `null` ở thời điểm bình thường.

### 5.2. Mốc tuyệt đối và bản hiển thị

Một `Instant` duy nhất có thể hiển thị theo các vùng khác nhau:

```java
import java.time.*;

Instant event = Instant.parse("2026-07-01T12:00:00Z");
ZonedDateTime hcm = event.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
ZonedDateTime ny = event.atZone(ZoneId.of("America/New_York"));
boolean sameInstant = hcm.toInstant().equals(ny.toInstant()); // true
```

Vào mốc minh họa này, HCM là **19:00 +07:00**, New York là **08:00 -04:00**. Không dùng `ZoneOffset.of("-05:00")` thay `America/New_York` cho lịch mùa hè/đông, vì offset đơn lẻ không có lịch thay đổi.

Để chuyển `ZonedDateTime` giữa hai vùng mà vẫn giữ mốc sự kiện, dùng `withZoneSameInstant`; `withZoneSameLocal` giữ số giờ địa phương và **có thể đổi mốc thực**.

## 6. Gói `java.time.chrono` — hệ lịch ngoài ISO

**Chronology là hệ lịch, không phải timezone.** ISO 8601/Gregorian là lịch mặc định của phần lớn kiểu `java.time`. Các hệ lịch khác có cách đếm năm/niên hiệu, có thể có cấu trúc lịch riêng. `java.time.chrono` cung cấp abstraction khi cần hiển thị/nhập ngày theo văn hóa.

| API | Trách nhiệm | Ghi chú |
| --- | --- | --- |
| `Chronology` | Xác định hệ lịch; tạo ngày của hệ đó | `Chronology.of(id)`, `Chronology.from(temporal)` |
| `ChronoLocalDate` | Ngày thuộc một chronology | Giao diện lịch trung lập; khác `LocalDate` ISO |
| `ChronoLocalDateTime<D>` | Ngày giờ địa phương trong chronology | Dùng khi UI xử lý hệ lịch khác |
| `ChronoZonedDateTime<D>` | Ngày giờ có múi giờ trong chronology | Cần cả lịch và quy tắc timezone |
| `Era` / `ChronoPeriod` | Niên hiệu / khoảng theo lịch đã chọn | Đừng trộn period của các chronology |
| `IsoChronology` | Hệ ISO mặc định | `IsoChronology.INSTANCE` |
| `JapaneseChronology` / `JapaneseDate` | Hệ lịch Nhật với niên hiệu | Ví dụ thời Reiwa |
| `ThaiBuddhistChronology` / `ThaiBuddhistDate` | Phật lịch Thái | Cách đánh số năm khác ISO |
| `MinguoChronology` / `MinguoDate` | Lịch Dân Quốc | Cách đánh số năm khác |
| `HijrahChronology` / `HijrahDate` | Hệ lịch Hijrah | Cần lưu ý giới hạn, phiên bản dữ liệu lịch |

Ví dụ làm việc với cùng một **ngày** trong hai lịch:

```java
import java.time.LocalDate;
import java.time.chrono.JapaneseDate;
import java.time.chrono.JapaneseChronology;

LocalDate iso = LocalDate.of(2026, 10, 24);
JapaneseDate jp = JapaneseDate.from(iso);
LocalDate sameIsoDay = LocalDate.from(jp);
String chronologyId = JapaneseChronology.INSTANCE.getId(); // "Japanese"
```

`jp` biểu diễn ngày theo hệ Nhật Bản và niên hiệu tương ứng; `sameIsoDay` vẫn là `2026-10-24`. Ở đây `JapaneseDate` và `LocalDate` nói về **cùng một ngày trên dòng lịch**, không liên quan việc đổi giờ hoặc offset.

Lưu ý thiết kế từ tài liệu JDK: nên dùng các kiểu ISO (`LocalDate`, `Instant`...) cho mô hình lõi, ranh giới lưu trữ và truyền mạng **khi có thể**; dùng `chrono` chủ yếu khi cần nhập/hiển thị lịch địa phương. Đưa `ChronoLocalDate` làm kiểu chung khắp tầng nghiệp vụ dễ tăng độ phức tạp và dẫn đến phép toán/so sánh sai khi trộn các chronology. Không suy luận rằng lịch Hijrah luôn có cùng kết quả giữa mọi runtime/dữ liệu; xác minh hỗ trợ và phạm vi ngày của hệ lịch cụ thể.

**Phân biệt qua ví dụ:** “Cuộc họp ở Tokyo lúc 09:00 theo vùng `Asia/Tokyo`” là bài toán **`zone`**; “Hiển thị ngày đó theo niên hiệu Reiwa” là bài toán **`chrono`**; “Hiển thị thành chuỗi tiếng Nhật” là bài toán **`format`**. Một ứng dụng có thể dùng cả ba việc độc lập.

## 7. Chương trình Java 17+ kết hợp đủ năm gói

Tạo một file **`TimePackagesDemo.java`**. Mã dưới đây tự chạy và dùng lần lượt kiểu ngày gốc, adjuster/unit, parse strict, zone rules và chronology:

```java
import java.time.*;
import java.time.chrono.JapaneseChronology;
import java.time.chrono.JapaneseDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.time.temporal.ChronoUnit;
import java.time.temporal.TemporalAdjusters;
import java.time.zone.ZoneRules;
import java.util.Locale;

public class TimePackagesDemo {
    public static void main(String[] args) {
        LocalDate base = LocalDate.of(2026, 10, 24);
        LocalDate firstMonday =
                base.with(TemporalAdjusters.firstInMonth(DayOfWeek.MONDAY));
        long remaining = ChronoUnit.DAYS.between(base, LocalDate.of(2026, 10, 31));

        DateTimeFormatter strictDate = DateTimeFormatter
                .ofPattern("dd/MM/uuuu", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
        LocalDate parsed = LocalDate.parse("31/12/2026", strictDate);

        ZoneId ny = ZoneId.of("America/New_York");
        ZoneRules rules = ny.getRules();
        LocalDateTime gap = LocalDateTime.of(2026, 3, 8, 2, 30);
        LocalDateTime overlap = LocalDateTime.of(2026, 11, 1, 1, 30);

        JapaneseDate japanese = JapaneseDate.from(base);

        System.out.println("Ngay goc: " + base);
        System.out.println("Thu hai dau thang: " + firstMonday);
        System.out.println("So ngay den cuoi thang: " + remaining);
        System.out.println("Parse: " + parsed);
        System.out.println("Offset hop le (gap): " + rules.getValidOffsets(gap).size());
        System.out.println("Offset hop le (overlap): " +
                rules.getValidOffsets(overlap).size());
        System.out.println("Chronology: " + JapaneseChronology.INSTANCE.getId());
        System.out.println("Ngay ISO tu JapaneseDate: " + LocalDate.from(japanese));
    }
}
```

Chạy trong thư mục chứa file bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 TimePackagesDemo.java
java TimePackagesDemo
```

Stdout tương ứng với ví dụ (các quy tắc vùng New York đúng theo dữ liệu tzdb cho năm 2026):

```text
Ngay goc: 2026-10-24
Thu hai dau thang: 2026-10-05
So ngay den cuoi thang: 7
Parse: 2026-12-31
Offset hop le (gap): 0
Offset hop le (overlap): 2
Chronology: Japanese
Ngay ISO tu JapaneseDate: 2026-10-24
```

**Giải thích từng phần:**

1. `LocalDate.of(...)` thuộc **`java.time`** tạo ngày ISO. Ngày 24/10/2026 được giữ nguyên; toán tử `with` tạo ngày mới cho thứ Hai đầu tháng.
2. `TemporalAdjusters.firstInMonth(...)` và `ChronoUnit.DAYS.between(...)` thuộc **`java.time.temporal`**. Thứ Hai đầu tháng 10/2026 là ngày 05/10; từ ngày 24 tới 31 còn 7 ngày.
3. `DateTimeFormatter` và `ResolverStyle.STRICT` thuộc **`java.time.format`**. Chuỗi kiểu Việt Nam `31/12/2026` được parse ra `LocalDate` và hiển thị mặc định ISO là `2026-12-31`.
4. `ZoneRules` thuộc **`java.time.zone`**; `ZoneId` và `LocalDateTime` thuộc **`java.time`**. Lần chuyển DST tháng 3 có 0 offset hợp lệ; lần lặp giờ tháng 11 có 2.
5. `JapaneseDate`, `JapaneseChronology` thuộc **`java.time.chrono`**. Chuyển từ ISO sang ngày theo hệ Nhật không đổi ngày thực; khi quay về `LocalDate` cho ra ngày ban đầu.

Cách kiểm tra thí nghiệm: đổi `base` sang `2026-02-28`, so sánh adjuster và số ngày; đổi `ny` sang `Asia/Ho_Chi_Minh` rồi quan sát `getValidOffsets` ở hai giờ ví dụ, với các giờ hợp lệ ở TP.HCM thông thường kết quả là 1; thêm `LocalDate.parse("31/02/2026", strictDate)` và bắt `DateTimeParseException`.

## 8. Cách các gói phối hợp trong thiết kế thực tế

### 8.1. Luồng nhận lịch hẹn từ người dùng

Ví dụ người tổ chức chọn `01/11/2026 01:30` tại New York (giờ bị trùng). Quy trình nên rõ nghĩa:

1. **`format`:** parse chuỗi ngày và giờ thành `LocalDateTime` với pattern, locale và resolver style thích hợp.
2. **`time`:** lấy `ZoneId.of("America/New_York")` từ địa điểm/lựa chọn thực của người tổ chức; không suy ra zone từ ngôn ngữ giao diện.
3. **`zone`:** hỏi `zone.getRules().getValidOffsets(local)`. Nếu 0, báo giờ không tồn tại; nếu 2, yêu cầu chọn lần thứ nhất/thứ hai; nếu 1, dùng offset duy nhất.
4. **`time`:** chuyển về `Instant` để lưu một mốc họp duy nhất; khi hiển thị cho người tham dự, áp dụng vùng họ cần.
5. **`temporal`:** khi tính thời lượng thực, dùng `Duration.between(startInstant, endInstant)` hoặc `ChronoUnit.MINUTES.between(...)` với hai instant. Khi cần “thứ Hai đầu tháng”, dùng `TemporalAdjusters` trên ngày lịch phù hợp.
6. **`chrono` (nếu cần):** định dạng cùng ngày theo hệ lịch Nhật/Thái ở tầng UI; không sửa nghĩa `Instant` đã được lưu.

Trong hệ thống có lịch lặp (“mỗi thứ Hai 09:00 tại New York”), lưu **quy tắc theo local time, `ZoneId` và luật lặp**; một timestamp UTC duy nhất không thể mô tả toàn bộ sự kiện tương lai vì offset mùa đông/mùa hè có thể khác. Khi lưu audit/tracking event, ưu tiên `Instant` hoặc timestamp có offset rõ ràng.

### 8.2. Luồng trả dữ liệu API

- Sự kiện tuyệt đối: chuỗi ISO chứa `Z` hoặc offset, ví dụ `2026-10-24T02:30:00Z`; ở Java map về `Instant`.
- Ngày độc lập với múi giờ: `2026-10-24`; map về `LocalDate`.
- Giờ hẹn địa phương: cần cả chuỗi local date-time và **IANA zone ID**, ví dụ `2026-11-01T01:30:00` + `America/New_York`; ở overlap cần thêm sự lựa chọn offset hoặc giải pháp nhập liệu rõ ràng.
- Khi dùng SQL/JDBC/ORM, xác nhận hành vi driver/hệ quản trị: kiểu `TIMESTAMP WITH TIME ZONE` ở nhiều DB không bảo toàn chính xác tên `ZoneId` được cung cấp, nên lưu vùng riêng nếu nghiệp vụ cần.

### 8.3. Kiểm thử theo ranh giới của từng gói

| Gói | Kiểm thử có ích |
| --- | --- |
| `time` | Cuối tháng, 29/02, qua năm, `Period` khác `Duration`; dùng `Clock.fixed` khi đọc “bây giờ” |
| `temporal` | Ngày đầu/cuối tháng, `next` khác `nextOrSame`, week-based-year sát đầu năm |
| `format` | Ngày hợp lệ/sai, ISO, pattern nghiêm ngặt, locale, ký tự `MM`/`mm` |
| `zone` | Gap 08/03/2026 và overlap 01/11/2026 tại New York; timezone rules/JDK được kiểm soát ở môi trường kiểm thử |
| `chrono` | ISO ↔ Japanese/ThaiBuddhist round trip, niên hiệu và biên thời gian được hệ lịch hỗ trợ |

Test liên quan `now()` cần nguồn thời gian được tiêm (`Clock.fixed(...)`), không dựa đồng hồ CI hoặc `ZoneId.systemDefault()`. Các giá trị test nên gắn một `ZoneId` tường minh. Cơ sở dữ liệu tzdb có thể được cập nhật theo phiên bản JDK nên kết quả lịch DST trong tương lai phụ thuộc rules hiện có.

## 9. Quy tắc chọn package theo nhu cầu và lỗi dễ mắc

| Nhu cầu | Nên bắt đầu từ | Dấu hiệu chọn sai |
| --- | --- | --- |
| Tính hạn sau 3 ngày lịch | `java.time.LocalDate.plusDays` | Cộng milliseconds hoặc `Duration` vào mốc bất kỳ |
| Tính elapsed time của một tác vụ | `java.time.Instant` + `Duration` | Trừ giờ địa phương qua DST |
| Tìm thứ Hai đầu tháng | `java.time.temporal.TemporalAdjusters` | Tự viết nhiều vòng lặp xử lý thứ |
| Đọc ngày theo `dd/MM/uuuu` | `java.time.format.DateTimeFormatter` | Dùng `SimpleDateFormat` chia sẻ giữa thread |
| Phát hiện 02:30 không tồn tại | `java.time.zone.ZoneRules` | Tin rằng mọi `LocalDateTime` có offset duy nhất |
| Hiển thị ngày theo lịch Nhật | `java.time.chrono.JapaneseDate` | Nghĩ chỉ thay `ZoneId` là đổi được hệ lịch |
| Dịch tên tháng theo ngôn ngữ | `java.time.format` + `Locale` | Dùng `Chronology` để thay văn bản locale |
| Gửi lịch họp cho người ở vùng khác | `Instant` + `ZoneId` | Lưu string giờ không zone/offset |

**Những lỗi cần nhớ:**

- Nhầm **`temporal` với `chrono`**: `ChronoUnit` và `ChronoField` **nằm trong `java.time.temporal`** dù tên bắt đầu bằng “Chrono”; `Chronology` và `ChronoLocalDate` mới thuộc `java.time.chrono`.
- Nhầm **`ZoneId` với `ZoneRules`**: `ZoneId` ở `java.time`; `ZoneRules` ở `java.time.zone`. Người dùng ứng dụng thường chọn ZoneId, business code tra rules khi cần xác thực.
- Nhầm **vùng với offset**: `America/New_York` có quy tắc thay đổi; `-05:00` là một offset cố định.
- Nhầm **lịch với múi giờ**: chuyển `JapaneseDate` không chuyển thời điểm theo UTC; chuyển `Instant` sang vùng không đổi chronology mặc định.
- Dùng `LocalDateTime.now()` trong business/test nhưng không định nghĩa zone; kết quả phụ thuộc timezone hệ thống, khiến test khó tái lập.
- Dùng formatter `YYYY-MM-dd` cho ngày lịch thông thường; `YYYY` là **năm theo tuần**, không phải năm lịch. Dùng `uuuu-MM-dd` hoặc formatter ISO chuẩn.
- Gọi `date.plusDays(1)` mà không gán biến; đối tượng `java.time` immutable.
- Dùng `ChronoUnit.DAYS` trên một temporal không hỗ trợ hoặc đòi ngày lịch đối với đại lượng thực theo giây; cần kiểm tra kiểu input và mục đích nghiệp vụ.
- Dùng `ChronoLocalDate` cho toàn bộ domain không có yêu cầu lịch phi ISO; khiến API lưu trữ và kiểm tra tính nhất quán phức tạp hơn cần thiết.
- Import `java.time.*` rồi kỳ vọng các class từ bốn package con đều có sẵn; cần import cụ thể.

## 10. Bài tập củng cố và tiêu chí đạt

**Bài tập 1 — Gắn tên package:** Xác định gói của `LocalDate`, `ChronoUnit`, `DateTimeFormatter`, `ZoneRules`, `JapaneseChronology`. Đáp án theo thứ tự: `time`, `temporal`, `format`, `zone`, `chrono`. Giải thích vì sao `ChronoUnit` không nằm trong `chrono`.

**Bài tập 2 — Ngày làm việc:** Cho `LocalDate.of(2026, 10, 24)`; tìm `TemporalAdjusters.next(DayOfWeek.MONDAY)` và `firstDayOfNextMonth()`. Kết quả phải là **26/10/2026** và **01/11/2026**. Chứng minh ngày gốc không thay đổi.

**Bài tập 3 — Parse strict:** Parse `29/02/2028` thành công, `29/02/2026` thất bại bằng formatter `dd/MM/uuuu` + `ResolverStyle.STRICT`. Phân biệt lỗi syntax với ngày không hợp lệ, bắt `DateTimeParseException` ở ranh giới đầu vào.

**Bài tập 4 — DST:** Hỏi `ZoneRules.getValidOffsets(...)` cho New York lúc `2026-03-08 02:30` và `2026-11-01 01:30`. Viết hàm trả trạng thái `GAP`, `NORMAL` hoặc `OVERLAP` theo số offset; không tự chọn khi overlap.

**Bài tập 5 — Chuyển chronology:** Tạo `JapaneseDate.from(LocalDate.of(2026, 10, 24))`, đọc `JapaneseChronology.INSTANCE.getId()`, đổi ngược về `LocalDate` và assert cùng ngày ISO. Nêu vì sao đây không phải chuyển múi giờ.

**Bài tập 6 — Thiết kế ứng dụng:** Người dùng đặt lịch hẹn bằng chuỗi `dd/MM/uuuu HH:mm`, `ZoneId` và chọn ưu tiên offset khi overlap. Phác thảo các bước parse → xác minh `ZoneRules` → xác định `ZonedDateTime` → lưu `Instant` → hiển thị theo vùng; chỉ dùng `chrono` nếu UI cần lịch phi ISO.

**Bạn đã đạt bài học khi** có thể vẽ lại sơ đồ năm gói, chọn gói đúng cho sáu bài tập, chạy ví dụ đầy đủ đúng kết quả và giải thích được sự khác biệt giữa **field/unit**, **format**, **zone rules** và **chronology**.

## Tài liệu JDK 17 chính thức

- [`java.time`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html)
- [`java.time.temporal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/package-summary.html)
- [`java.time.format`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/package-summary.html)
- [`java.time.zone`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/package-summary.html)
- [`java.time.chrono`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/chrono/package-summary.html)

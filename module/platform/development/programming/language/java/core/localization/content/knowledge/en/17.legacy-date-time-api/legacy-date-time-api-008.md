# Di chuyển mã bản địa hóa từ API ngày giờ cũ sang java.time

## 1. Vì sao cần chuyển đổi?

Java có hai họ API ngày giờ thường gặp trong ứng dụng đa ngôn ngữ:

- **Họ cũ**: `java.util.Date`, `java.util.Calendar`, `java.util.TimeZone`, `java.text.DateFormat` và `java.text.SimpleDateFormat`.
- **Họ hiện đại** (Java 8+, nên dùng trên Java 17+): `java.time.Instant`, `LocalDate`, `LocalTime`, `LocalDateTime`, `ZonedDateTime`, `OffsetDateTime`, `YearMonth`, `ZoneId` và `java.time.format.DateTimeFormatter`.

Động cơ không chỉ là viết ít mã hơn. Các đối tượng như `SimpleDateFormat` và `Calendar` có trạng thái thay đổi; `SimpleDateFormat` **không an toàn để chia sẻ giữa các luồng** khi không đồng bộ. Ngược lại, phần lớn kiểu giá trị `java.time` và `DateTimeFormatter` **bất biến và thread-safe**, đồng thời tách rõ thời điểm tuyệt đối, ngày địa phương, giờ địa phương, múi giờ và quy ước hiển thị.

Nhưng một phép “tìm-thay” từ `SimpleDateFormat` sang `DateTimeFormatter` có thể gây lỗi vì **các ký tự mẫu không hoàn toàn tương đương** và **ý nghĩa của đối tượng nguồn có thể khác**.

**Mục tiêu của bài:** chuyển đúng kiểu dữ liệu, locale, timezone, pattern, parsing và quy tắc kiểm thử mà không làm thay đổi ý nghĩa ngày giờ.

### Trước và sau

~~~java
// Kiểu cũ: có thể dùng locale/timezone ngầm nếu không chỉ định.
SimpleDateFormat old =
        new SimpleDateFormat("dd MMMM yyyy HH:mm", Locale.US);
old.setTimeZone(TimeZone.getTimeZone("UTC"));
String textOld = old.format(legacyDate);

// Kiểu mới: formatter bất biến, locale và zone rõ ràng.
DateTimeFormatter modern = DateTimeFormatter
        .ofPattern("dd MMMM uuuu HH:mm", Locale.US)
        .withZone(ZoneId.of("UTC"));
String textNew = modern.format(instant);
~~~

Đây là các **mảnh mã minh họa trong phương thức**. Biến `legacyDate` kiểu `Date` và `instant` kiểu `Instant` phải cùng đại diện một thời điểm; cần import `java.text.SimpleDateFormat`, `java.util.Date`, `java.util.Locale`, `java.util.TimeZone`, `java.time.Instant`, `java.time.ZoneId` và `java.time.format.DateTimeFormatter`.

Điều quan trọng hơn cú pháp: **timezone được chỉ định giống nhau, locale giống nhau, đối tượng ngày giờ có cùng nghĩa**. Nếu không, kết quả khác nhau chưa chắc do formatter.

## 2. Chọn đúng kiểu java.time trước khi thay formatter

Bước đầu tiên là trả lời: *dữ liệu đang lưu là một thời điểm tuyệt đối hay chỉ là ngày/giờ địa phương?*

| Dữ liệu/kiểu cũ | Kiểu java.time thường phù hợp | Ý nghĩa |
| --- | --- | --- |
| `Date` đại diện thời điểm UTC trên trục thời gian | `Instant` | Một thời điểm tuyệt đối, không lưu locale và timezone |
| `Calendar` với timezone | `ZonedDateTime` hoặc `Instant` + `ZoneId` | Giá trị và quy tắc giờ địa phương theo múi giờ |
| Ngày sinh/ngày thanh toán không có giờ | `LocalDate` | Ngày theo lịch, không phải thời điểm |
| Giờ mở cửa cố định trong ngày | `LocalTime` | Giờ và phút, không có ngày/zone |
| Lịch hẹn “9:00 ngày 5/3” chưa gắn zone | `LocalDateTime` | Ngày giờ địa phương, chưa xác định thời điểm tuyệt đối |
| Thời điểm với độ lệch UTC cụ thể | `OffsetDateTime` | Giờ + UTC offset; không chứa toàn bộ quy tắc chuyển DST |
| Lịch hẹn tại một múi giờ địa lý | `ZonedDateTime` | Ngày giờ + `ZoneId` như `Europe/Berlin` |
| Tên tháng và năm trong bộ lọc | `YearMonth` | Năm và tháng, không có ngày |
| `TimeZone` | `ZoneId` | Nhận diện múi giờ/qui tắc địa phương |
| `DateFormat`/`SimpleDateFormat` | `DateTimeFormatter` | Định dạng/phân tích các kiểu thời gian hiện đại |

**Không tự động thay mọi `Date` bằng `LocalDateTime`.** `Date` mang một thời điểm, còn `LocalDateTime` không có zone. Chuyển `Date` thành `LocalDateTime` cần xác định **zone**; bỏ qua zone có thể làm sai giờ hoặc thậm chí sai ngày.

Ngược lại, một trường “ngày sinh” vốn chỉ có `2025-03-05` thường nên là `LocalDate`, không nên ép nó thành `Instant` tại nửa đêm UTC một cách tùy tiện.

### Locale không phải TimeZone

- `Locale.forLanguageTag("vi-VN")`: chọn ngôn ngữ/vùng để định dạng tên tháng, dấu phân tách, bố cục ngày.
- `ZoneId.of("Asia/Ho_Chi_Minh")`: chọn quy tắc giờ địa phương.
- `Instant.parse("2025-03-05T10:15:30Z")`: chọn **thời điểm**.

Cùng một `Instant` có thể hiển thị giờ khác nhau ở Việt Nam và Mỹ; cùng một `ZoneId` vẫn có thể hiển thị bố cục ngày khác nhau cho hai `Locale`.

## 3. Chuyển đổi Date, Calendar và TimeZone có kiểm soát

### 3.1. Date ↔ Instant

~~~java
Date legacy = Date.from(
        Instant.parse("2025-03-05T10:15:30Z")
);
Instant modern = legacy.toInstant();

Date backToLegacy = Date.from(modern);
~~~

Đoạn trên là mảnh mã trong method, cần import `java.util.Date` và `java.time.Instant`.

- `Date.toInstant()` giữ cùng **thời điểm**.
- `Date.from(instant)` tạo đối tượng dùng cho API cũ.
- `Date` không chứa timezone hiển thị. `Date.toString()` có thể dùng múi giờ mặc định của JVM khi tạo chuỗi, nhưng điều đó **không** biến timezone thành thuộc tính của đối tượng `Date`.

### 3.2. Calendar → ZonedDateTime/Instant

Với `GregorianCalendar`, Java cung cấp `toZonedDateTime()`:

~~~java
GregorianCalendar legacyCalendar =
        new GregorianCalendar(
                TimeZone.getTimeZone("Asia/Ho_Chi_Minh"),
                Locale.forLanguageTag("vi-VN")
        );
legacyCalendar.setTimeInMillis(
        Instant.parse("2025-03-05T10:15:30Z").toEpochMilli()
);

ZonedDateTime zoned = legacyCalendar.toZonedDateTime();
Instant instant = legacyCalendar.toInstant();
~~~

Đây là mảnh mã trong method, cần import `java.util.GregorianCalendar`, `java.util.TimeZone`, `java.util.Locale`, `java.time.ZonedDateTime` và `java.time.Instant`.

**Lưu ý:** `Calendar` có thể đại diện các hệ lịch khác nhau, không nhất thiết là `GregorianCalendar`. Không cast bừa mọi `Calendar` thành `GregorianCalendar`; cần biết chronology và mục tiêu chuyển đổi. Nếu chỉ cần **thời điểm**, `calendar.toInstant()` giúp tránh suy diễn sai calendar fields. Nếu cần giữ múi giờ, kiểm tra `calendar.getTimeZone().toZoneId()` và chuyển đổi phù hợp.

### 3.3. TimeZone ↔ ZoneId

~~~java
TimeZone oldZone =
        TimeZone.getTimeZone("Asia/Ho_Chi_Minh");
ZoneId zone = oldZone.toZoneId();

TimeZone backwardCompatible = TimeZone.getTimeZone(zone);
~~~

Đây là mảnh mã trong method, cần import `java.util.TimeZone` và `java.time.ZoneId`.

**Cảnh báo quan trọng:** `TimeZone.getTimeZone("Bad/Zone")` có thể **âm thầm fallback về GMT** nếu ID không hợp lệ. Ngược lại, `ZoneId.of("Bad/Zone")` ném ngoại lệ do ID không hợp lệ. Khi di trú, cần quyết định: bắt lỗi để phát hiện cấu hình sai hay duy trì fallback có chủ đích. Không viết code giả định cách xử lý ID sai của hai API giống nhau.

### 3.4. GregorianCalendar và tháng 0-based

Trong `Calendar`, `Calendar.JANUARY` có giá trị `0`, còn `Calendar.MARCH` có giá trị `2`. Trong `java.time`, tháng của `LocalDate.of(year, month, day)` nhận **1–12**, và `Month.MARCH.getValue() == 3`.

~~~java
int oldMonthZeroBased = Calendar.MARCH; // 2
int newMonthOneBased = Month.MARCH.getValue(); // 3
~~~

Đây là mảnh mã trong method, cần import `java.util.Calendar` và `java.time.Month`. Đừng chuyển trực tiếp `calendar.get(Calendar.MONTH)` sang tham số thứ hai của `LocalDate.of` nếu chưa `+1`, hoặc tốt hơn hãy chuyển qua các bridge API phù hợp.

## 4. DateFormat/SimpleDateFormat → DateTimeFormatter: thay mẫu nhưng đừng thay nghĩa

### Các lời gọi thông dụng

| API cũ | Hướng chuyển java.time | Ghi chú |
| --- | --- | --- |
| `new SimpleDateFormat(pattern, locale)` | `DateTimeFormatter.ofPattern(patternNew, locale)` | Cần **review pattern**, không copy nguyên vô điều kiện |
| `DateFormat.getDateInstance(style, locale)` | `DateTimeFormatter.ofLocalizedDate(formatStyle).withLocale(locale)` | Hai họ API có thể tạo chuỗi không hoàn toàn giống |
| `DateFormat.getTimeInstance(style, locale)` | `DateTimeFormatter.ofLocalizedTime(formatStyle).withLocale(locale)` | Xem kiểu thời gian và zone |
| `DateFormat.getDateTimeInstance(dateStyle, timeStyle, locale)` | `DateTimeFormatter.ofLocalizedDateTime(dateStyleNew,timeStyleNew).withLocale(locale)` | Mapping style và CLDR cần kiểm thử |
| `simple.setTimeZone(timeZone)` | `formatter.withZone(zoneId)` hoặc chuyển `Instant.atZone(...)` | Lựa chọn đúng phụ thuộc kiểu đầu vào |
| `simple.setLenient(false)` | `formatter.withResolverStyle(ResolverStyle.STRICT)` | **Không tương đương hoàn toàn**, cần kiểm thử parse và pattern |
| `SimpleDateFormat.format(Date)` | `DateTimeFormatter.format(TemporalAccessor)` | Chuyển nguồn thành `Instant`/`LocalDate`/`ZonedDateTime` |
| `SimpleDateFormat.parse(text)` | `LocalDate.parse`, `ZonedDateTime.parse` hoặc `formatter.parse` | Chọn kiểu đầu ra có nghĩa nghiệp vụ |

`DateFormat` dùng các mức như `SHORT`, `MEDIUM`, `LONG`, `FULL`; `java.time.format.FormatStyle` có các tên tương ứng. Tuy nhiên, chúng không được bảo đảm tạo **chuỗi giống nhau từng ký tự** giữa hai họ API hoặc các provider.

Nếu product cần giữ y hệt chuỗi cũ vì hợp đồng giao tiếp, cần cố định pattern và chính sách dữ liệu; tốt hơn là tách **giao thức máy** khỏi **chuỗi UI theo locale**.

## 5. Ví dụ đầy đủ: cùng Instant, Locale và ZoneId cho hai API

Lưu `LegacyVsModernDemo.java`:

~~~java
import java.text.SimpleDateFormat;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

public class LegacyVsModernDemo {
    public static void main(String[] args) {
        Instant instant = Instant.parse("2025-03-05T10:15:30Z");
        Locale locale = Locale.US;
        ZoneId zone = ZoneId.of("UTC");

        Date legacyValue = Date.from(instant);
        SimpleDateFormat oldFormatter =
                new SimpleDateFormat("dd MMMM yyyy HH:mm z", locale);
        oldFormatter.setTimeZone(TimeZone.getTimeZone(zone));

        DateTimeFormatter newFormatter = DateTimeFormatter
                .ofPattern("dd MMMM uuuu HH:mm z", locale)
                .withZone(zone);

        System.out.println("Old: "
                + oldFormatter.format(legacyValue));
        System.out.println("New: "
                + newFormatter.format(instant));
        System.out.println("Same instant: "
                + legacyValue.toInstant().equals(instant));
    }
}
~~~

Biên dịch/chạy trên JDK 17+:

~~~bash
javac -encoding UTF-8 LegacyVsModernDemo.java
java LegacyVsModernDemo
~~~

Kết quả trên JDK với dữ liệu tên tháng en-US thông dụng:

~~~text
Old: 05 March 2025 10:15 UTC
New: 05 March 2025 10:15 UTC
Same instant: true
~~~

**Vì sao dùng `uuuu` thay `yyyy` trong formatter mới?** `java.time` phân biệt *proleptic year* (`u`) và *year-of-era* (`y`). Với ngày hiện đại theo ISO trong ví dụ này, cả hai thường in `2025`. Nhưng khi parse nghiêm ngặt hoặc xử lý thời kỳ trước Công nguyên, sự khác biệt có ý nghĩa. Phải review pattern trước khi migration.

**Vì sao chỉ định `withZone(UTC)`?** `Instant` là thời điểm không có timezone địa phương. Muốn in `HH:mm` và tên zone, formatter cần zone. Nếu bỏ `withZone` nhưng vẫn dùng một pattern yêu cầu các trường ngày giờ từ `Instant`, có thể bị `UnsupportedTemporalTypeException`.

### Cùng một Instant, đổi zone là đổi giờ hiển thị

~~~java
Instant instant = Instant.parse("2025-03-05T10:15:30Z");

String vietnam = DateTimeFormatter
        .ofPattern("uuuu-MM-dd HH:mm", Locale.US)
        .withZone(ZoneId.of("Asia/Ho_Chi_Minh"))
        .format(instant);
~~~

Đây là mảnh mã trong method, cần import `java.time.Instant`, `java.time.ZoneId`, `java.time.format.DateTimeFormatter` và `java.util.Locale`. `vietnam` bằng `"2025-03-05 17:15"` theo quy tắc múi giờ Việt Nam cho ngày này. Thời điểm không đổi, chỉ cách xem tại địa phương khác nhau.

## 6. LocalizedDate/Time: chuyển định dạng theo locale, không chỉ copy pattern

Ứng dụng đa ngôn ngữ thường nên để locale quyết định thứ tự ngày-tháng-năm và cách viết tên tháng thay vì áp một mẫu cố định cho mọi vùng.

Trong API cũ:

~~~java
DateFormat old = DateFormat.getDateInstance(
        DateFormat.LONG, Locale.US
);
String text = old.format(new Date());
~~~

Đoạn trên là mảnh mã trong method, cần import `java.text.DateFormat`, `java.util.Locale`, `java.util.Date`. Dùng `new Date()` ở đây chỉ minh họa cú pháp, **không** dùng làm expected output test vì thời gian chạy thay đổi.

Trong `java.time`, dùng ngày cố định:

~~~java
LocalDate day = LocalDate.of(2025, 3, 5);

DateTimeFormatter usLong = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.LONG)
        .withLocale(Locale.US);

String shown = day.format(usLong);
~~~

Đoạn trên cần import `java.time.LocalDate`, `java.time.format.DateTimeFormatter`, `java.time.format.FormatStyle` và `java.util.Locale`. Với dữ liệu locale en-US phổ biến, `shown` là `"March 5, 2025"`.

### Ví dụ hoàn chỉnh

Tạo `LocalizedStyleDemo.java`:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class LocalizedStyleDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2025, 3, 5);

        for (Locale locale : new Locale[] {
                Locale.US, Locale.GERMANY
        }) {
            DateTimeFormatter formatter = DateTimeFormatter
                    .ofLocalizedDate(FormatStyle.LONG)
                    .withLocale(locale);

            System.out.println(locale.toLanguageTag()
                    + ": " + date.format(formatter));
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 LocalizedStyleDemo.java
java LocalizedStyleDemo
~~~

Đầu ra điển hình:

~~~text
en-US: March 5, 2025
de-DE: 5. März 2025
~~~

Trong ví dụ, `DateTimeFormatter` là **immutable**. Lời gọi `withLocale` tạo formatter có cấu hình locale mới, **không** sửa đối tượng formatter gốc. Cần lưu ý đầu ra chính xác (dấu, chữ hoa, khoảng trắng) có thể khác với `DateFormat` cũ nếu phiên bản JDK hoặc dữ liệu locale/provider khác.

## 7. Pattern cần review kỹ: không phải ký tự nào cũng tương đương

Đây là nhóm lỗi thường gặp khi “copy nguyên pattern” từ `SimpleDateFormat` sang `DateTimeFormatter`.

| Chức năng | `SimpleDateFormat` cũ | `DateTimeFormatter` mới | Điểm cần chú ý |
| --- | --- | --- | --- |
| Năm theo kỷ nguyên | `y` / `yyyy` | `y` / `yyyy` | Mới có `u` cho *proleptic year*, thường chọn `uuuu` khi parse strict ngày ISO |
| Năm ISO/proleptic | Không dùng `u` cho năm | `u` / `uuuu` | **`u` trong SimpleDateFormat là số thứ tự ngày trong tuần** |
| Năm tính theo tuần | `Y` | `Y` | Có thể khác năm lịch ở cuối/đầu năm; không dùng thay `yyyy`/`uuuu` |
| Tháng | `M` / `MM` / `MMM` / `MMMM` | Tương tự | Dạng văn bản còn phụ thuộc locale |
| Tên tháng đứng độc lập | `L` | `L` | Hữu ích trong tiêu đề lịch ở ngôn ngữ có biến cách |
| Ngày của tháng | `d` | `d` | Thường cùng nghĩa |
| Ngày của năm | `D` | `D` | Khác `d` |
| Giờ 24h | `H` | `H` | 0–23 |
| Giờ 12h | `h` | `h` | Thường kết hợp `a` (AM/PM) |
| Phút | `m` | `m` | `mm` là phút, `MM` là tháng |
| Giây | `s` | `s` | Cùng vai trò |
| Milli/fraction | `S` (milli-of-second) | `S` (*fraction-of-second*) | **Không copy tùy ý width của S**, phải xét precision |
| Múi giờ dạng chữ | `z` | `z` | Tên hiển thị tùy locale và provider |
| Offset UTC | `Z`, `X` | `Z`, `X`, `x`, `O` | Hành vi biểu diễn số 0/colon/offset phải kiểm thử |
| Thứ trong tuần | `E` | `E` | Có thể phụ thuộc cách đánh số tuần/locale |
| Dấu nháy trong pattern | `'...'` | `'...'` | Literal cần escape đúng khi có dấu nháy đơn |

### 7.1. Bẫy nghiêm trọng: `u` trong hai API có ý nghĩa khác nhau

Trong `SimpleDateFormat`, ký hiệu `u` là **số thứ tự ngày trong tuần (1–7)**, không phải năm. Trong `DateTimeFormatter`, `u` là **proleptic year**. Vì vậy một pattern cũ có `u` không thể được chuyển nguyên sang API mới.

Ngược lại, chuyển `"yyyy-MM-dd"` sang `"uuuu-MM-dd"` trong java.time thường là lựa chọn tốt cho ngày ISO khi parse strict (để có trường `YEAR` rõ ràng). Nhưng phải kiểm thử các năm trước Công nguyên hoặc chronology đặc biệt nếu ứng dụng có.

### 7.2. Bẫy `Y` và `y`/`u`

`Y` là **week-based-year**, phụ thuộc quy ước tuần của locale; ở sát ngày đầu/cuối năm, nó có thể khác năm dương lịch. Với định dạng ngày dân sự ISO, nên dùng `uuuu-MM-dd` hoặc formatter ISO chuẩn thay vì `YYYY-MM-dd`.

### 7.3. Bẫy `S`: milliseconds so với fraction

`SimpleDateFormat` xem `S` là **millisecond** có giá trị 0–999, số lượng ký tự kiểm soát cách padding theo định dạng số. `DateTimeFormatter` xem `S` là **phần thập phân của giây**, với số ký tự quyết định độ chính xác (tối đa 9 chữ số cho nanoseconds). Ví dụ `SSS` thường biểu diễn mili-giây ba chữ số trong tình huống thông dụng, nhưng `S`/`SS` khi parse/format có thể có ý nghĩa khác với API cũ. Đừng đổi pattern fractional seconds tự động chỉ bằng tìm-thay.

Nếu lưu timestamp cho giao tiếp máy, ưu tiên ISO-8601 hoặc formatter được định nghĩa rõ theo giao thức thay vì trông chờ default pattern từ locale.

### 7.4. `M` và `L` ở ngôn ngữ có dạng tháng độc lập

Khi tên tháng xuất hiện trong một ngày đầy đủ, dùng `MMMM` theo ngữ cảnh; khi in riêng tên tháng trong header lịch, `LLLL` có thể tạo dạng ngữ pháp phù hợp hơn. Ví dụ `ru-RU` với dữ liệu CLDR thông dụng có dạng `марта` trong ngày, nhưng `март` khi tháng đứng độc lập. Nếu pattern cũ từng ép một tên tháng cố định, hãy xem lại vị trí sử dụng ở UI.

## 8. Parsing: chuyển từ DateFormat.parse sang java.time mà không đánh mất validation

API cũ có thể viết:

~~~java
SimpleDateFormat parser =
        new SimpleDateFormat("yyyy-MM-dd", Locale.ROOT);
parser.setLenient(false);
parser.setTimeZone(TimeZone.getTimeZone("UTC"));
Date parsed = parser.parse("2025-03-05");
~~~

Đây là mảnh mã trong method cần xử lý `ParseException`, import `java.text.SimpleDateFormat`, `java.util.Locale`, `java.util.TimeZone` và `java.util.Date`. Một ngày không có giờ khi parse ra `Date` phải được ánh xạ đến **một thời điểm**, nên timezone dùng khi parse có ảnh hưởng.

Nếu bản chất dữ liệu chỉ là ngày, java.time cho phép diễn đạt rõ hơn:

~~~java
DateTimeFormatter parser = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);

LocalDate parsed = LocalDate.parse("2025-03-05", parser);
~~~

Đoạn trên cần import `java.time.LocalDate`, `java.time.format.DateTimeFormatter`, `java.time.format.ResolverStyle` và `java.util.Locale`. `LocalDate` không tự áp một timezone, vì dữ liệu nhập chỉ có ngày.

### ResolverStyle của DateTimeFormatter

- `ResolverStyle.STRICT`: kiểm tra nghiêm ngặt việc resolve trường thành ngày/giờ hợp lệ.
- `ResolverStyle.SMART`: có thể điều chỉnh một số trường hợp ngày không hợp lệ theo quy tắc API; đây là mặc định của formatter tạo từ pattern.
- `ResolverStyle.LENIENT`: cho phép tính toán linh hoạt, ví dụ tràn số ngày/tháng thành ngày khác.

**`SimpleDateFormat.setLenient(false)` và `ResolverStyle.STRICT` không phải một phép thay thế hoàn toàn tương đương**. Parser mới còn có các giai đoạn phân tích trường và resolve trường; quy tắc input có thể khác. Cần có test cho dữ liệu thực tế.

### Vì sao strict thường dùng `uuuu`?

Trong `java.time`, `yyyy` là **year-of-era** và khi chỉ có `yyyy-MM-dd` nhưng không có era, formatter ở chế độ strict có thể chưa resolve thành `LocalDate` như mong muốn. `uuuu` cung cấp trường proleptic year trực tiếp cho các ngày ISO đơn giản.

### Ví dụ Java 17+ kiểm tra ngày hợp lệ và không hợp lệ

Lưu `StrictDateParseDemo.java`:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class StrictDateParseDemo {
    public static void main(String[] args) {
        DateTimeFormatter strict = DateTimeFormatter
                .ofPattern("uuuu-MM-dd", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);

        for (String input : new String[]{
                "2025-03-05", "2025-02-30"
        }) {
            try {
                LocalDate value = LocalDate.parse(input, strict);
                System.out.println(input + " => " + value);
            } catch (DateTimeParseException ex) {
                System.out.println(input + " => invalid");
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 StrictDateParseDemo.java
java StrictDateParseDemo
~~~

Kết quả:

~~~text
2025-03-05 => 2025-03-05
2025-02-30 => invalid
~~~

Hàm `LocalDate.parse` với formatter này kiểm tra input theo pattern và resolve; nếu cần nhận dấu, ký tự Unicode hoặc cách viết ngày theo locale đặc biệt, hãy thiết kế pattern/locale/validation cho biểu mẫu. Đừng dùng `LocalDate.parse` mặc định để đoán tùy ý mọi cách viết ngày trên thế giới.

### Kiểm tra chuỗi dư với API cũ

`SimpleDateFormat.parse(String)` có thể chấp nhận tiền tố hợp lệ rồi bỏ qua ký tự dư. Nếu code cũ chỉ kiểm tra “parse không ném exception”, đầu vào có thể lọt qua. Khi di trú, coi đây là cơ hội thiết kế validation rõ ràng.

Với legacy parser, `ParsePosition` cho biết phần đã tiêu thụ:

~~~java
ParsePosition pos = new ParsePosition(0);
Date value = parser.parse(input, pos);

if (value == null || pos.getIndex() != input.length()) {
    throw new IllegalArgumentException("Invalid date input");
}
~~~

Đây là mảnh mã trong method, yêu cầu `parser` là `SimpleDateFormat` và `input` là chuỗi cần phân tích, import `java.text.ParsePosition` và `java.util.Date`. Kiểm tra này **không** thay thế validation về lịch, timezone hoặc quy tắc nghiệp vụ.

## 9. DST: không tự gán timezone cho LocalDateTime rồi nghĩ thời điểm luôn duy nhất

Đây là một rủi ro lớn khi chuyển từ `Calendar`/`Date` sang `java.time`.

Ví dụ trong khu vực có daylight saving time (DST), một giờ địa phương có thể:

- **Không tồn tại** tại thời điểm đồng hồ nhảy tới (*gap*).
- **Xuất hiện hai lần** khi đồng hồ lùi lại (*overlap*).

`LocalDateTime.of(...)` chỉ mô tả ngày giờ trên đồng hồ; bản thân nó không bảo đảm đó là một thời điểm duy nhất. Khi gắn `ZoneId` để tạo `ZonedDateTime`, Java phải áp dụng các quy tắc DST và có lựa chọn mặc định đối với gap/overlap.

Nếu hệ thống lưu sự kiện dưới dạng timestamp tuyệt đối, dùng `Instant`. Nếu hệ thống lưu lịch hẹn “9 giờ sáng theo lịch địa phương tại Berlin”, có thể cần giữ cả `LocalDateTime`, `ZoneId` và quy tắc xử lý DST được xác định rõ.

### Chuyển Instant sang giờ địa phương

~~~java
Instant instant = Instant.parse("2025-03-05T10:15:30Z");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime viewed = instant.atZone(zone);
LocalDate localDate = viewed.toLocalDate();
LocalTime localTime = viewed.toLocalTime();
~~~

Đây là mảnh mã trong method, cần import `java.time.Instant`, `java.time.ZoneId`, `java.time.ZonedDateTime`, `java.time.LocalDate`, `java.time.LocalTime`.

Đổi `Instant` sang giờ địa phương là xác định; nhưng đổi một `LocalDateTime` bất kỳ sang `Instant` có thể cần xử lý gap/overlap rõ ràng nếu ứng dụng đòi hỏi độ chính xác cao.

**Không dùng `ZoneId.systemDefault()` vô tình trong code chạy trên server nhiều người dùng** nếu zone của giao dịch/người dùng đã biết. Cấu hình mặc định của máy chủ là một lựa chọn môi trường, không nhất thiết là timezone đúng của dữ liệu.

## 10. Locale mặc định và định dạng theo ngôn ngữ

`SimpleDateFormat` và `DateFormat` có các constructor/factory sử dụng locale mặc định của JVM nếu không truyền tường minh. Ở `java.time`, hãy mang theo `Locale` từ ngữ cảnh người nhận.

~~~java
Locale viewer = Locale.forLanguageTag("vi-VN");
DateTimeFormatter formatter = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.LONG)
        .withLocale(viewer);
~~~

Đây là mảnh mã trong method, cần import `java.util.Locale`, `java.time.format.DateTimeFormatter`, `java.time.format.FormatStyle`.

Lợi ích khi truyền locale rõ ràng:

1. Một server phục vụ đồng thời người dùng Việt, Đức và Mỹ mà không phải gọi `Locale.setDefault` theo request.
2. Unit test ít phụ thuộc locale máy phát triển hoặc CI.
3. Mỗi formatter thể hiện chính xác quy ước của người xem.
4. Locale và zone được quản lý **riêng**.

**Chú ý:** `DateTimeFormatter` của java.time không tự nhận tất cả quy tắc từ `Locale`. Nếu chuỗi hiển thị một `Instant`, bạn vẫn cần cung cấp zone. Nếu ứng dụng hỗ trợ lịch khác ISO, cần cân nhắc `Chronology`, Unicode locale extensions và khả năng hỗ trợ của formatter. Chỉ đổi locale không tự động thay chronology, timezone hoặc currency.

### Trường hợp tháng có cách viết phụ thuộc ngữ cảnh

Ở một số ngôn ngữ, tháng có dạng theo ngữ cảnh và dạng tên độc lập. Pattern `MMMM` cho tháng theo ngữ cảnh; `LLLL` cho dạng đứng độc lập, ví dụ tiêu đề tháng trên calendar. Khi di trú code có tên tháng bản địa hóa, đừng chỉ so kết quả tiếng Anh; kiểm thử `ru-RU` hoặc `pl-PL` nếu có trong sản phẩm.

## 11. Thread safety, trạng thái và hiệu năng

### SimpleDateFormat cũ

`SimpleDateFormat` có thể thay đổi pattern, timezone, calendar, leniency. Nó **không được đồng bộ hóa nội bộ để dùng chia sẻ an toàn**. Dùng một static instance chung cho mọi request là một nguồn lỗi cạnh tranh dữ liệu và đôi khi khó tái hiện.

~~~java
// Không an toàn nếu nhiều thread cùng dùng/chỉnh instance này.
private static final SimpleDateFormat SHARED =
        new SimpleDateFormat("yyyy-MM-dd", Locale.US);
~~~

Đây là mảnh khai báo field trong class, cần import `java.text.SimpleDateFormat` và `java.util.Locale`.

### DateTimeFormatter mới

`DateTimeFormatter` **bất biến và thread-safe**. Có thể tạo trước và dùng lại nếu locale/zone/pattern **phù hợp cùng mục đích**:

~~~java
private static final DateTimeFormatter ISO_DAY =
        DateTimeFormatter
                .ofPattern("uuuu-MM-dd", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
~~~

Đây là mảnh khai báo field trong class, cần import `java.time.format.DateTimeFormatter`, `java.time.format.ResolverStyle` và `java.util.Locale`.

**Điểm cần tách biệt:** `withLocale`, `withZone`, `withChronology`, `withDecimalStyle` trả formatter được cấu hình tương ứng, không sửa instance gốc. Tuy nhiên, cache formatter cho từng user có thể làm tăng số lượng đối tượng nếu thiết kế không kiểm soát; chỉ cache những tổ hợp thực sự được sử dụng.

Các kiểu `LocalDate`, `Instant`, `ZonedDateTime` cũng bất biến, thuận tiện cho code nhiều luồng.

## 12. Những điểm khác nhau dễ làm vỡ kiểm thử hoặc nghiệp vụ

| Tình huống | Sai lầm khi migration | Cách làm đúng |
| --- | --- | --- |
| `Date` chứa thời điểm | Thay bằng `LocalDateTime` mà không dùng zone | Chuyển `Date.toInstant()`, rồi dùng zone nếu cần |
| Mã cũ dùng timezone server | Chạy môi trường khác thấy lệch ngày/giờ | Chỉ định `ZoneId` từ yêu cầu/ứng dụng |
| Pattern cũ có `u` | Copy sang java.time và nghĩ vẫn là ngày trong tuần | Review toàn bộ ký tự pattern, nhất là `u` |
| Pattern cũ có `YYYY` | Coi là năm lịch | Phân biệt week-based-year với `uuuu` |
| Pattern cũ có `S` | Copy số lượng `S` không xét precision | Kiểm tra khác biệt millisecond/fraction |
| Formatter parse cũ lenient | Chuyển API mới rồi không test input bất thường | Chọn `ResolverStyle` và test case thực tế |
| Mẫu `yyyy` parse STRICT | Không resolve thành LocalDate vì thiếu era | Cân nhắc `uuuu-MM-dd` với ISO chronology |
| Dùng `getLocalizedDate` bằng pattern cố định | Bỏ qua thứ tự ngày/tháng của locale | Dùng `ofLocalizedDate`/`ofLocalizedDateTime` |
| Locale đúng nhưng giờ sai | Bỏ quên timezone | Quản lý locale và zone độc lập |
| `Calendar.MONTH` | Giữ tháng 0-based trong `LocalDate.of` | Chuyển sang tháng 1–12 |
| Tên tháng có biến cách | Dùng `MMMM` cho nhãn tháng độc lập | Dùng `LLLL` khi ngữ cảnh phù hợp |
| Dùng chung `SimpleDateFormat` đa luồng | Kết quả sai ngẫu nhiên | Thay bằng `DateTimeFormatter` hoặc cô lập formatter cũ |
| So output exact trên các JDK khác nhau | Test hỏng vì dữ liệu CLDR/provider khác | Cố định môi trường hoặc kiểm tra semantics |
| Chuỗi UI dùng làm dữ liệu API | Lỗi parse giữa các locale | Dùng ISO-8601/kiểu dữ liệu máy |
| Thay ngày giờ mà bỏ quy tắc DST | Lịch hẹn lệch thời điểm | Định nghĩa chính sách cho gap/overlap |

## 13. Kiểu ngày giờ trong dữ liệu, database và JSON

Khi di trú, không nên giải quyết vấn đề chỉ ở giao diện hiển thị. Cần rà soát **hợp đồng dữ liệu đầu vào/đầu ra**:

- **Ngày không có giờ**: dùng `LocalDate`, biểu diễn ISO `2025-03-05` khi trao đổi máy.
- **Thời điểm tuyệt đối**: dùng `Instant` với ISO-8601 như `2025-03-05T10:15:30Z`.
- **Ngày giờ có offset**: dùng `OffsetDateTime` nếu offset là một phần của dữ liệu.
- **Sự kiện gắn vùng có DST**: có thể dùng `ZonedDateTime` hoặc lưu `Instant` + `ZoneId` tùy nghiệp vụ.
- **Ngày tháng trong nội dung UI**: format vào phút hiển thị với locale và zone được chỉ định, không dùng chuỗi UI làm khóa truyền dữ liệu.

### JDBC và các kiểu java.sql

Trong hệ thống cũ, có thể gặp `java.sql.Date` hoặc `java.sql.Timestamp`:

~~~java
java.sql.Date legacySqlDate =
        java.sql.Date.valueOf("2025-03-05");
LocalDate date = legacySqlDate.toLocalDate();

java.sql.Timestamp legacyTimestamp =
        java.sql.Timestamp.from(
                Instant.parse("2025-03-05T10:15:30Z")
        );
Instant instant = legacyTimestamp.toInstant();
~~~

Đây là mảnh mã trong method, cần import `java.time.LocalDate` và `java.time.Instant`.

**Chú ý:** `java.sql.Date` đại diện khái niệm ngày của SQL, không nên coi nó giống một timestamp UTC. Đối với JDBC/ORM, cách mapping `DATE`/`TIME`/`TIMESTAMP`/`TIMESTAMP WITH TIME ZONE` tùy driver và database. Không giả định tất cả cột `TIMESTAMP` chứa timezone hoặc có thể convert sang `Instant` mà không có quy tắc. Kiểm tra mapping và schema thực tế trước khi di trú.

Đối với JSON, cấu hình thư viện serialize/deserialize `java.time` có thể cần module/adapter tùy thư viện. Không mặc định `DateTimeFormatter` quyết định mọi cách JSON được sinh ra; formatter trong UI và serializer là hai tầng khác nhau.

## 14. Kế hoạch di trú theo từng bước

Một lộ trình an toàn:

1. **Kiểm kê:** tìm những vị trí dùng `Date`, `Calendar`, `DateFormat`, `SimpleDateFormat`, `TimeZone`; xác định chúng xử lý dữ liệu nghiệp vụ hay chỉ trình bày.
2. **Phân loại kiểu:** thời điểm, ngày, giờ, tháng/năm hay lịch hẹn có zone. Chọn `Instant`/`LocalDate`/`ZonedDateTime`... đúng ngữ nghĩa.
3. **Xác định locale/zone:** đọc từ hồ sơ, yêu cầu, hợp đồng dữ liệu hoặc cấu hình chính thức; tránh ngầm phụ thuộc JVM.
4. **Review pattern:** đối chiếu các ký tự `u`, `y`, `Y`, `S`, `M`/`L`, `X`/`Z` và dấu literal; không copy mù quáng.
5. **Tách parser khỏi formatter:** định nghĩa cách hiển thị cho người dùng và cách parse input, rõ mức nghiêm ngặt.
6. **Kiểm thử đối chiếu:** cùng input, cùng locale, cùng zone; kiểm tra semantics trước, sau đó những chuỗi bắt buộc phải giống exact.
7. **Kiểm thử ngày biên:** cuối năm, năm nhuận, các ngày sai như 30/2, chuyển DST, zone offset, ngày trước Công nguyên nếu có.
8. **Kiểm thử Unicode/CLDR:** tên tháng, AM/PM, ký tự phân cách và cách viết của locale được hỗ trợ.
9. **Di trú từng tầng:** tạo bridge ở ranh giới API cũ, chuyển domain model và service, rồi cuối cùng loại bỏ formatter cũ.
10. **Giám sát và dọn dẹp:** tránh giữ hai cơ chế định dạng có default khác nhau lâu dài; ghi nhận khác biệt có chủ đích trong test và tài liệu.

### Ranh giới thích hợp khi hệ thống chưa thể đổi hết

~~~text
Legacy API / Database
        |
        v
Chuyển đổi ở boundary
Date -> Instant
Calendar -> ZonedDateTime
java.sql.Date -> LocalDate
        |
        v
Domain và service dùng java.time
        |
        +------> Formatter cho UI
        |        Locale + ZoneId tường minh
        |
        +------> Serializer cho API
                 ISO-8601 / schema xác định
~~~

Không nên vừa truyền `Date` vừa truyền `LocalDateTime` lẫn lộn trong domain nếu hai biến mang ý nghĩa khác nhau mà không được ghi rõ. Mục tiêu là **một mô hình thời gian nhất quán**, không chỉ đổi tên lớp.

## 15. Bài tập thực hành

1. Tạo `Date` từ `Instant.parse("2025-03-05T10:15:30Z")`, rồi format bằng `SimpleDateFormat` và `DateTimeFormatter` tại UTC với `Locale.US`. So sánh đầu ra và giải thích vì sao cần `withZone`.
2. Thay `DateFormat.getDateInstance(DateFormat.LONG, Locale.US)` bằng formatter `java.time` phù hợp, thử trên `LocalDate.of(2025,3,5)`.
3. Chuyển một `GregorianCalendar` theo `Asia/Ho_Chi_Minh` thành `ZonedDateTime`, đối chiếu `toInstant()` và giờ địa phương.
4. Viết hai formatter theo `Locale.US` và `Locale.GERMANY` cho cùng ngày. Tại sao không cần gọi `Locale.setDefault`?
5. Giải thích vì sao pattern `"uuuu-MM-dd"` trong `DateTimeFormatter` không có nghĩa giống `"uuuu-MM-dd"` trong `SimpleDateFormat`.
6. Parse `2025-02-30` với `ResolverStyle.STRICT` và `ResolverStyle.SMART`. Kiểm tra kết quả để biết vì sao migration có thể thay đổi logic nhập liệu.
7. Một ứng dụng dùng `Calendar.MONTH` để truyền vào `LocalDate.of`. Hãy tìm lỗi off-by-one khi chuyển tháng Ba.
8. Trong lịch tiếng Nga, thử `"d MMMM uuuu"` và `"LLLL uuuu"`. Trường hợp nào dùng cho ngày đầy đủ, trường hợp nào dùng cho header tháng?
9. Hệ thống nhận thời điểm lịch hẹn ở `Europe/Berlin` gần thời điểm DST. Hãy xác định dữ liệu nào cần lưu để không mơ hồ và kiểm thử các trường hợp giờ bị lặp hoặc không tồn tại.
10. Nếu một bài test so chuỗi ngày theo locale thất bại sau nâng JDK, hãy phân biệt thay đổi CLDR/provider với thay đổi semantic của dữ liệu.
11. Chuyển một cột SQL DATE sang `LocalDate` và một cột timestamp thời điểm sang `Instant`; giải thích vì sao hai phép chuyển không nên dùng cùng một phương pháp timezone.

**Ghi nhớ:** Di trú từ `Date`/`Calendar`/`SimpleDateFormat` sang `java.time` là thay đổi **mô hình thời gian lẫn cách định dạng**, không chỉ thay tên API. Hãy giữ riêng **Instant/LocalDate/ZonedDateTime**, **Locale** và **ZoneId**; review lại pattern `u/y/Y/S/M/L`; xác thực input bằng `ResolverStyle` phù hợp; ưu tiên `DateTimeFormatter` bất biến thay cho `SimpleDateFormat` mutable. Kiểm thử trên dữ liệu cố định, các ngày biên, locale thực tế và timezone/DST để tránh thay đổi hành vi ngoài ý muốn.

### Tài liệu tham khảo

- [Java SE 17 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html) — pattern, localized styles, locale, zone và tính bất biến.
- [Java SE 17 — ResolverStyle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/ResolverStyle.html) — STRICT, SMART và LENIENT khi parse.
- [Java SE 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html) — thời điểm tuyệt đối và chuyển đổi từ `Date`.
- [Java SE 17 — ZonedDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html) — zone và quy tắc DST.
- [Java SE 17 — SimpleDateFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/SimpleDateFormat.html) — API cũ, pattern và an toàn đa luồng.
- [Java SE 17 — GregorianCalendar](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/GregorianCalendar.html) — chuyển sang `ZonedDateTime`.
- [Java SE 17 — LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html) — ngày không chứa giờ hoặc timezone.
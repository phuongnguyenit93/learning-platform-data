# Phân biệt `DateTimeFormatter.localizedBy(Locale)` với `withLocale(Locale)` trong Java 10+

## 1. Hai phương thức cùng nhận `Locale` nhưng có hợp đồng khác nhau

Khi xử lý ngày giờ cho người dùng ở nhiều quốc gia, ứng dụng thường cần thay đổi ngôn ngữ tên tháng/thứ, mẫu định dạng, hệ lịch, hệ chữ số và múi giờ. Trong `java.time.format.DateTimeFormatter` có hai phương thức rất dễ bị nhầm:

```java
DateTimeFormatter a = formatter.withLocale(locale);
DateTimeFormatter b = formatter.localizedBy(locale);
```

Đây là đoạn mã minh họa **trong một phương thức**, với `formatter` và `locale` đã được khai báo đúng kiểu.

**Khác biệt cốt lõi:**

- **`withLocale(locale)`:** trả về formatter mới có **Locale dùng để tra cứu phần văn bản hoặc mẫu định dạng được bản địa hóa**. Nó lưu locale được truyền vào mà **không tự cấu hình chronology (hệ lịch), time zone và decimal style từ Unicode locale extensions**.
- **`localizedBy(locale)`:** cũng trả về formatter mới dùng Locale ấy, **đồng thời áp dụng các giá trị bản địa hóa phù hợp cho calendar/chronology, numbering/decimal style, region và time zone**. Các giá trị này có thể **ghi đè cấu hình đã tồn tại** trên formatter.

`DateTimeFormatter.localizedBy(Locale)` được giới thiệu ở **Java 10** và **vẫn áp dụng trong Java hiện đại**; `withLocale(Locale)` có từ Java 8 và vẫn được sử dụng.

Hai phương thức đều **không sửa formatter gốc** vì `DateTimeFormatter` là immutable. Tuy nhiên, chúng không phải hai cách viết tương đương của cùng một phép biến đổi cấu hình.

## 2. Bảng so sánh nhanh

| Thuộc tính | `withLocale(Locale)` | `localizedBy(Locale)` |
| --- | --- | --- |
| Đặt `Locale` cho formatter | Có | Có |
| Ảnh hưởng tên tháng/thứ và mẫu localized text/pattern | Có, khi formatter dùng thông tin đó | Có, khi formatter dùng thông tin đó |
| Tự áp dụng Unicode calendar `u-ca-...` vào `getChronology()` | **Không** | **Có**, nếu extension được hỗ trợ |
| Tự áp dụng Unicode numbering `u-nu-...` vào `getDecimalStyle()` | **Không** | **Có**, nếu extension được hỗ trợ |
| Tự áp dụng Unicode timezone `u-tz-...` vào `getZone()` | **Không** | **Có**, nếu extension được hỗ trợ |
| Dùng region `u-rg-...` khi suy ra calendar/numbering | Không chủ động thay các override theo extension | Có thể dùng region override theo hợp đồng |
| Thay `DecimalStyle` theo Locale thông thường | Không; giữ decimal style formatter đang có | Có thể tạo decimal style bản địa hóa |
| Có thể ghi đè chronology/zone/decimal style đã set trước | Không, chỉ vì đổi Locale | **Có**, tùy extension và locale |
| Thứ tự gọi với `withChronology`, `withZone`, `withDecimalStyle` | Chỉ đặt locale; ít gây bất ngờ về các override khác | **Quan trọng**: cấu hình ở lời gọi sau có thể thắng |
| Sửa chính instance gốc | Không | Không |
| Có từ | Java 8 | **Java 10** |

Không nên đơn giản hóa rằng `withLocale` “chỉ thay ngôn ngữ” và `localizedBy` “thay tất cả mọi thứ trong mọi trường hợp”. **Formatter có được thay phần nào còn phụ thuộc vào locale, Unicode extensions, dữ liệu provider và kiểu formatter đang được dùng.** Điểm khác nhau nằm ở **hợp đồng áp dụng các override**, không phải một lời hứa mọi trường luôn đổi.

## 3. Bối cảnh: `Locale` và Unicode locale extensions

`java.util.Locale` mang thông tin ngôn ngữ, script, region, variant và extension. Với ngày giờ, các extension Unicode quan trọng gồm:

| Extension trong BCP 47 | Ý nghĩa | Ảnh hưởng có thể có ở `localizedBy` |
| --- | --- | --- |
| `u-ca-buddhist` | Hệ lịch Buddhist | Chọn chronology phù hợp, ví dụ `ThaiBuddhistChronology` |
| `u-ca-japanese` | Hệ lịch Nhật | Chọn chronology Japanese nếu được hỗ trợ |
| `u-nu-thai` | Hệ chữ số Thai | Cấu hình `DecimalStyle`/numbering system |
| `u-nu-latn` | Hệ chữ số Latin | Cấu hình biểu diễn chữ số kiểu Latin khi hỗ trợ |
| `u-tz-usnyc` | Time zone identifier cho New York | Có thể đặt `America/New_York` làm zone override |
| `u-rg-gbzzzz` | Region override cho Anh | Có thể ảnh hưởng cách suy ra lịch/cách biểu diễn số theo vùng |

Ví dụ tạo locale từ tag:

```java
Locale buddhist = Locale.forLanguageTag(
        "th-TH-u-ca-buddhist");
Locale thaiDigits = Locale.forLanguageTag(
        "en-US-u-nu-thai");
Locale newYork = Locale.forLanguageTag(
        "en-US-u-tz-usnyc");
```

Đây là các câu lệnh trong một phương thức, cần import `java.util.Locale`.

**Cách đọc:** bản thân `Locale` lưu/diễn đạt một **yêu cầu về quy ước bản địa hóa**. Nó **không tự làm thay đổi** một `DateTimeFormatter` đã có. Cần gọi API của formatter để gắn locale và quyết định có áp dụng extension đến chronology, zone, decimal style hay không.

`Locale.forLanguageTag` chỉ phân tích một **tag BCP 47**; nó không tự bảo đảm mọi giá trị extension đều được formatter, CLDR provider hoặc phiên bản JDK hỗ trợ. Với nguồn config không tin cậy, cũng cần xác thực tag bằng Builder hoặc cơ chế validation phù hợp trước khi dùng.

## 4. `withLocale(Locale)`: đổi locale để chọn văn bản và mẫu

Một formatter có thể được tạo bằng **mẫu localized date**:

```java
DateTimeFormatter formatter =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG);

DateTimeFormatter vietnamese = formatter.withLocale(
        Locale.forLanguageTag("vi-VN"));

DateTimeFormatter english = formatter.withLocale(
        Locale.US);
```

Đây là ví dụ trong một phương thức; cần import `DateTimeFormatter`, `FormatStyle` và `Locale`.

Khi format `LocalDate`, tên tháng và mẫu được chọn dựa trên locale tương ứng, ví dụ thứ tự ngày–tháng–năm, cách hiển thị tháng bằng chữ. Vì dữ liệu locale có thể khác giữa JDK/provider, **không nên hardcode một output ngôn ngữ cụ thể** trong test chạy trên nhiều môi trường nếu không cố định phiên bản dữ liệu.

`withLocale` cũng có hiệu lực với formatter được xây bằng `DateTimeFormatter.ofPattern("d MMM uuuu")`: token `MMM` lấy tên tháng theo Locale. Tuy nhiên, một **mẫu cố định** như `"uuuu-MM-dd"` không tự đổi thứ tự trường chỉ vì `withLocale(Locale.FRANCE)`.

**Điều `withLocale` không làm:** nếu locale mang `u-ca-buddhist` hoặc `u-tz-usnyc`, nó **không tự gán** giá trị ấy cho `getChronology()` hoặc `getZone()`; tương tự `u-nu-thai` không tự thay `DecimalStyle`. Theo Javadoc, extension có thể được sử dụng về sau trong **text processing**, nhưng không bị chuyển thẳng thành các override nói trên.

Điều này hữu ích khi ứng dụng đã cố ý giữ **ISO chronology**, **UTC zone**, hoặc **một decimal style đã chuẩn hóa**, chỉ muốn thay phần text/mẫu được bản địa hóa.

## 5. `localizedBy(Locale)`: áp dụng cấu hình bản địa hóa sâu hơn

Chữ ký API:

```java
public DateTimeFormatter localizedBy(Locale locale)
```

Phương thức có từ **Java 10**. Javadoc mô tả đây là bản sao của formatter có các giá trị bản địa hóa từ **locale, calendar, region, decimal style và/hoặc timezone**, có thể **supersede** các giá trị trong formatter hiện tại.

Ví dụ cơ bản:

```java
var base = DateTimeFormatter.ofPattern("uuuu-MM-dd")
        .withChronology(IsoChronology.INSTANCE);

var locale = Locale.forLanguageTag("th-TH-u-ca-buddhist");

var with = base.withLocale(locale);
var localized = base.localizedBy(locale);

// with.getChronology().getId()      -> "ISO"
// localized.getChronology().getId() -> "ThaiBuddhist"
```

Đoạn minh họa cần import `DateTimeFormatter`, `IsoChronology` và `Locale`.

**Tại sao khác nhau?**

- `base` đã đặt chronology rõ ràng là `IsoChronology`.
- `withLocale` giữ chronology ISO đó, dù locale có `u-ca-buddhist`.
- `localizedBy` nhận yêu cầu calendar trong Unicode extension, **ghi đè** chronology thành Thai Buddhist.

Khi dùng `LocalDate.of(2024, 2, 3)`:

```java
LocalDate date = LocalDate.of(2024, 2, 3);

System.out.println(with.format(date));
// 2024-02-03

System.out.println(localized.format(date));
// 2567-02-03
```

Đầu ra trên đã được kiểm chứng trong ví dụ Java chạy ở phần 12. Năm khác nhau do **cách diễn giải hệ lịch**: cùng ngày ISO 2024-02-03 được biểu diễn thành năm 2567 theo hệ lịch Buddhist. **Không phải dữ liệu ngày trong `LocalDate` bị sửa**.

Đây là khác biệt về **ngữ nghĩa ngày giờ**, không đơn thuần là dịch tên tháng.

## 6. Ví dụ Unicode `ca`: lịch có thể thay đổi

`DateTimeFormatter` có các phương thức liên quan:

- `getChronology()`: trả chronology override hiện tại, hoặc `null` khi không có.
- `withChronology(Chronology)`: tạo formatter mới đặt chronology override.
- `withLocale(Locale)`: đặt locale, không tự đặt chronology theo `u-ca`.
- `localizedBy(Locale)`: có thể đặt chronology từ Unicode calendar extension.

Với calendar Buddhist:

```java
var locale = Locale.forLanguageTag("th-TH-u-ca-buddhist");

var original = DateTimeFormatter.ofPattern("uuuu-MM-dd")
        .withChronology(IsoChronology.INSTANCE);

var one = original.withLocale(locale);
var two = original.localizedBy(locale);

System.out.println(one.getChronology().getId()); // ISO
System.out.println(two.getChronology().getId()); // ThaiBuddhist
```

**Không nhầm chronology với Locale:**

- Locale `th-TH` là lựa chọn ngôn ngữ và vùng.
- Extension `u-ca-buddhist` yêu cầu hệ lịch Buddhist.
- Chronology là một đối tượng `java.time.chrono.Chronology` xác định cách diễn giải trường ngày theo lịch.
- Việc format hoặc parse một ngày khi có chronology override có thể ảnh hưởng trường năm, era, tháng… và kết quả chuyển đổi.

**Lưu ý test:** không nên chỉ assert chuỗi tên tháng, vì localized text phụ thuộc provider. Kiểm tra `getChronology()` và các trường quan trọng giúp phân biệt đúng hành vi hai phương thức. Nếu định dạng nghiệp vụ buộc dùng ISO/Gregorian, hãy đặt `withChronology(IsoChronology.INSTANCE)` ở bước **sau** `localizedBy`, hoặc sử dụng `withLocale` nếu chỉ cần text.

## 7. Ví dụ Unicode `nu`: hệ chữ số và `DecimalStyle`

`DecimalStyle` chứa những ký hiệu cần thiết để formatter xử lý số, gồm **zero digit**, dấu âm/dương và dấu thập phân. `DateTimeFormatter.getDecimalStyle()` cho biết decimal style hiện tại.

Với tag:

```java
var thaiDigits = Locale.forLanguageTag(
        "en-US-u-nu-thai");

var base = DateTimeFormatter.ofPattern("uuuu")
        .withDecimalStyle(DecimalStyle.STANDARD);

var with = base.withLocale(thaiDigits);
var localized = base.localizedBy(thaiDigits);

System.out.println(
        Integer.toHexString(with.getDecimalStyle().getZeroDigit()));
// 30  => U+0030 (ASCII digit 0)

System.out.println(
        Integer.toHexString(localized.getDecimalStyle().getZeroDigit()));
// e50 => U+0E50 (Thai digit ๐)
```

Đây là đoạn minh họa trong phương thức; import `DateTimeFormatter`, `DecimalStyle`, `Locale`.

**Giải thích:**

- `withLocale` không thay `DecimalStyle.STANDARD` đang có; zero digit là `'0'`, mã Unicode `U+0030`.
- `localizedBy` áp dụng numbering system theo `u-nu-thai`; zero digit trở thành ký tự Thai `U+0E50` trên JDK có dữ liệu hỗ trợ.
- Các chữ số thể hiện khi format và cách parser nhận chữ số có thể khác theo decimal style.

Đối với formatter đã cần một bộ số cố định, ví dụ format ký hiệu kỹ thuật hoặc dữ liệu trao đổi máy–máy, hãy xác định rõ **có nên cho extension `nu` thay đổi cách biểu diễn hay không**.

Cũng lưu ý: `localizedBy` có thể thay `DecimalStyle` theo **locale thông thường** ngay cả khi không có `u-nu`. Ví dụ `Locale.FRANCE` thường có dấu thập phân dạng dấu phẩy. Trong kiểm chứng Java 24, `withLocale(Locale.FRANCE)` giữ `getDecimalStyle().getDecimalSeparator()` là `U+002E` (dấu chấm của style ban đầu), còn `localizedBy(Locale.FRANCE)` đặt `U+002C` (dấu phẩy).

**Không khẳng định mọi locale đều thay zero digit:** nhiều locale dùng cùng chữ số ASCII. Hãy kiểm tra đúng thuộc tính cần thiết, không chỉ nhìn output một ngày cụ thể.

## 8. Ví dụ Unicode `tz`: thay time zone

Một formatter có thể được đặt time zone tường minh qua `withZone(ZoneId)`. Nếu chỉ đổi Locale bằng `withLocale`, time zone override đó **không đổi**. Nhưng `localizedBy` có thể đọc `u-tz-...` và thay zone.

```java
var locale = Locale.forLanguageTag(
        "en-US-u-tz-usnyc");

var base = DateTimeFormatter
        .ofPattern("uuuu-MM-dd HH:mm")
        .withZone(ZoneId.of("UTC"));

var with = base.withLocale(locale);
var localized = base.localizedBy(locale);

System.out.println(with.getZone().getId());
// UTC

System.out.println(localized.getZone().getId());
// America/New_York
```

Với instant cố định:

```java
Instant instant = Instant.parse("2024-01-01T00:00:00Z");

System.out.println(with.format(instant));
// 2024-01-01 00:00

System.out.println(localized.format(instant));
// 2023-12-31 19:00
```

Đoạn cần import `Instant`, `ZoneId`, `DateTimeFormatter` và `Locale`. Ví dụ đã được kiểm chứng trên JDK 24 với tag `tz-usnyc` được hỗ trợ, trỏ tới `America/New_York`. Do tháng 1 là mùa đông ở New York, UTC-05:00 nên instant `00:00Z` tương ứng `19:00` ngày hôm trước.

**Không nhầm zone với offset cố định:** `ZoneId.of("America/New_York")` mang quy tắc zone và daylight saving theo dữ liệu tzdb, trong khi một `ZoneOffset` cụ thể chỉ là offset. Việc format phải dựa vào một temporal có **thông tin instant hoặc đủ thông tin vùng/giờ**, và có thể cần zone override. Ví dụ dùng `Instant` vì nó biểu diễn một điểm trên trục thời gian rõ ràng.

Khi ứng dụng yêu cầu **luôn UTC** cho log hoặc định dạng máy–máy, không nên để Unicode `tz` vô tình ghi đè zone đã cố định. Với trường hợp này, dùng `withLocale`, hoặc đặt lại `withZone(UTC)` **sau** `localizedBy`.

## 9. Unicode `rg` và thứ tự ưu tiên `ca`/`nu`

Extension `rg` là **region override** trong Unicode locale keywords, chẳng hạn `u-rg-gbzzzz` có nghĩa chọn region GB cho những mục đích hỗ trợ override theo vùng.

Javadoc `localizedBy` nói rõ rằng khi locale mang các extension `ca`, `nu`, `rg` và/hoặc `tz`, chronology, numbering system hoặc time zone có thể được đặt dựa trên những extension ấy. Nếu cả `ca` và `rg` đều được cung cấp:

- **`ca` ưu tiên** so với giá trị chronology có thể được suy ra ngầm từ `rg`.
- Tương tự **`nu` ưu tiên** so với numbering system có thể suy ra ngầm từ `rg`.

Không nên tự viết logic “region luôn thắng calendar” hoặc “thấy `rg` thì bắt buộc thay ZoneId” mà không đọc hợp đồng API. `rg` biểu diễn một override theo vùng; các trường cụ thể phụ thuộc cách bản địa hóa được áp dụng.

Ví dụ dùng để **kiểm tra ngữ nghĩa** chứ không hardcode output từng provider:

```java
Locale locale = Locale.forLanguageTag(
        "en-US-u-ca-buddhist-nu-thai-rg-gbzzzz");

DateTimeFormatter f =
        DateTimeFormatter.ofPattern("uuuu-MM-dd")
                .localizedBy(locale);

// Kiểm tra chronology/decimal style theo phần hỗ trợ thực tế:
// f.getChronology(), f.getDecimalStyle()
```

Với những yêu cầu nghiệp vụ phải có một lịch hay hệ chữ số cụ thể, hãy **test trực tiếp các thuộc tính của formatter** và đặt override tường minh ở bước cuối thay vì ngầm phụ thuộc vào cấu hình vùng.

## 10. Thứ tự gọi phương thức là một phần thiết kế

Đây là điểm khác biệt Javadoc nêu trực tiếp: với `localizedBy`, **thứ tự chaining với những phương thức `withXXXX()` khác có thể tạo ra formatter khác nhau**.

Ví dụ time zone:

```java
var tz = Locale.forLanguageTag("en-US-u-tz-usnyc");

var base = DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm");

var localeLast = base
        .withZone(ZoneId.of("UTC"))
        .localizedBy(tz);

var zoneLast = base
        .localizedBy(tz)
        .withZone(ZoneId.of("UTC"));

// localeLast.getZone() -> America/New_York
// zoneLast.getZone()   -> UTC
```

Thứ tự này phản ánh **quy tắc override**:

- Gọi `withZone(UTC)` rồi `localizedBy(tz)`: extension `tz` có thể thay zone thành New York.
- Gọi `localizedBy(tz)` rồi `withZone(UTC)`: yêu cầu zone tường minh ở **lời gọi sau** thắng.
- Gọi `withLocale(tz)` lên formatter đã có UTC: vẫn giữ UTC vì `withLocale` không áp dụng extension thành zone override.

Tương tự với chronology:

```java
var ca = Locale.forLanguageTag("th-TH-u-ca-buddhist");

var chronologyLast =
        DateTimeFormatter.ofPattern("uuuu-MM-dd")
                .localizedBy(ca)
                .withChronology(IsoChronology.INSTANCE);

// chronologyLast.getChronology().getId() -> ISO
```

Và DecimalStyle:

```java
var nu = Locale.forLanguageTag("en-US-u-nu-thai");

var decimalLast = DateTimeFormatter.ofPattern("uuuu")
        .localizedBy(nu)
        .withDecimalStyle(DecimalStyle.STANDARD);

// decimalLast.getDecimalStyle().getZeroDigit() == '0'
```

**Gợi ý thiết kế:** bắt đầu từ một formatter template ổn định, chọn locale, rồi **áp dụng các override bắt buộc của nghiệp vụ ở bước cuối**. Cách này tránh sự khác biệt khó giải thích khi refactor thứ tự các lệnh chaining.

## 11. Khi nào chọn `withLocale` và khi nào chọn `localizedBy`?

| Nhu cầu thực tế | Lựa chọn | Lý do |
| --- | --- | --- |
| Chỉ đổi tên tháng/thứ hoặc mẫu ngày theo ngôn ngữ | `withLocale(locale)` | Giữ chronology, zone, decimal style đã cố định |
| Formatter log phải luôn ISO + UTC nhưng nhãn tháng có thể bản địa hóa | `withLocale(locale)` cùng override ISO/UTC tường minh | Extension của Locale không tự thay các override quan trọng |
| Ứng dụng cần tôn trọng `u-ca-buddhist` của người dùng | `localizedBy(locale)` | Có thể áp dụng chronology tương ứng |
| Ứng dụng cần tôn trọng `u-nu-thai` | `localizedBy(locale)` | Có thể áp dụng numbering/decimal style |
| Ứng dụng cần tôn trọng timezone trong `u-tz-...` | `localizedBy(locale)` | Có thể áp dụng zone theo extension |
| Muốn localized decimal separator theo Locale | `localizedBy(locale)` | Có thể thay DecimalStyle theo locale |
| Format dữ liệu trao đổi cố định, không phụ thuộc tùy chọn locale | Định dạng ISO/chuẩn thích hợp, override rõ ràng; thường không cần `localizedBy` | Tránh biến đổi chronology/zone/numbering ngoài ý định |
| Có yêu cầu vừa tôn trọng locale vừa ép UTC hoặc ISO | `localizedBy(locale)` rồi `withZone(UTC)` / `withChronology(ISO)` | Override nghiệp vụ ở cuối |

**Không lấy `getLocale()` làm bằng chứng duy nhất rằng `localizedBy` đã khác `withLocale`:** cả hai đều có thể trả cùng Locale, trong khi `getChronology()`, `getZone()` và `getDecimalStyle()` khác nhau. Khi debug một formatter, cần kiểm tra tất cả những trường có liên quan tới định dạng đang gặp lỗi.

## 12. Chương trình Java 17+ hoàn chỉnh: kiểm tra trực tiếp từng thuộc tính

Tạo tệp `DateTimeFormatterLocaleDemo.java`:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.chrono.IsoChronology;
import java.time.format.DateTimeFormatter;
import java.time.format.DecimalStyle;
import java.util.Locale;

public class DateTimeFormatterLocaleDemo {

    static String chronology(DateTimeFormatter f) {
        return f.getChronology() == null
                ? "none"
                : f.getChronology().getId();
    }

    static String zone(DateTimeFormatter f) {
        return f.getZone() == null
                ? "none"
                : f.getZone().getId();
    }

    static String point(char c) {
        return String.format(
                Locale.ROOT, "U+%04X", (int) c);
    }

    static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        // 1. Calendar extension: ISO vs Thai Buddhist
        var date = LocalDate.of(2024, 2, 3);
        var thaiCalendar = Locale.forLanguageTag(
                "th-TH-u-ca-buddhist");

        var dateBase = DateTimeFormatter
                .ofPattern("uuuu-MM-dd")
                .withChronology(IsoChronology.INSTANCE);

        var dateWith = dateBase.withLocale(thaiCalendar);
        var dateLocalized = dateBase.localizedBy(thaiCalendar);

        System.out.println("calendar.with="
                + chronology(dateWith));
        System.out.println("calendar.localized="
                + chronology(dateLocalized));
        System.out.println("calendar.base="
                + chronology(dateBase));
        System.out.println("date.with="
                + dateWith.format(date));
        System.out.println("date.localized="
                + dateLocalized.format(date));

        check("ISO".equals(chronology(dateWith)),
                "withLocale changed chronology");
        check("ThaiBuddhist".equals(chronology(dateLocalized)),
                "localizedBy failed chronology");

        // 2. Numbering system extension and decimal style
        var thaiNumbering = Locale.forLanguageTag(
                "en-US-u-nu-thai");

        var digitsBase = DateTimeFormatter
                .ofPattern("uuuu")
                .withDecimalStyle(DecimalStyle.STANDARD);

        var digitsWith = digitsBase.withLocale(thaiNumbering);
        var digitsLocalized = digitsBase.localizedBy(thaiNumbering);

        System.out.println("digits.with.zero="
                + point(digitsWith.getDecimalStyle().getZeroDigit()));
        System.out.println("digits.localized.zero="
                + point(digitsLocalized.getDecimalStyle().getZeroDigit()));
        System.out.println("digits.explicitLast.zero="
                + point(digitsLocalized
                        .withDecimalStyle(DecimalStyle.STANDARD)
                        .getDecimalStyle().getZeroDigit()));

        check(digitsWith.getDecimalStyle().getZeroDigit() == '0',
                "withLocale changed digits");
        check(digitsLocalized.getDecimalStyle().getZeroDigit()
                        == '\u0E50',
                "localizedBy failed Thai numbering");

        // 3. Locale alone may affect decimal separator
        var frenchWith = DateTimeFormatter
                .ofPattern("uuuu-MM-dd")
                .withLocale(Locale.FRANCE);

        var frenchLocalized = DateTimeFormatter
                .ofPattern("uuuu-MM-dd")
                .localizedBy(Locale.FRANCE);

        System.out.println("fr.with.separator="
                + point(frenchWith.getDecimalStyle()
                        .getDecimalSeparator()));
        System.out.println("fr.localized.separator="
                + point(frenchLocalized.getDecimalStyle()
                        .getDecimalSeparator()));

        // 4. Time zone extension and order of overrides
        var newYork = Locale.forLanguageTag(
                "en-US-u-tz-usnyc");

        var clockBase = DateTimeFormatter
                .ofPattern("uuuu-MM-dd HH:mm")
                .withZone(ZoneId.of("UTC"));

        var clockWith = clockBase.withLocale(newYork);
        var clockLocalized = clockBase.localizedBy(newYork);
        var clockExplicitLast = clockBase.localizedBy(newYork)
                .withZone(ZoneId.of("UTC"));

        var instant = Instant.parse(
                "2024-01-01T00:00:00Z");

        System.out.println("zone.with=" + zone(clockWith));
        System.out.println("zone.localized="
                + zone(clockLocalized));
        System.out.println("zone.explicitLast="
                + zone(clockExplicitLast));
        System.out.println("time.with="
                + clockWith.format(instant));
        System.out.println("time.localized="
                + clockLocalized.format(instant));
        System.out.println("base.zone=" + zone(clockBase));

        check("UTC".equals(zone(clockWith)),
                "withLocale changed zone");
        check("America/New_York".equals(zone(clockLocalized)),
                "localizedBy failed timezone");
        check("UTC".equals(zone(clockExplicitLast)),
                "explicit zone did not win");
        check("UTC".equals(zone(clockBase)),
                "original formatter was mutated");

        System.out.println("tests=PASS");
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac DateTimeFormatterLocaleDemo.java
java DateTimeFormatterLocaleDemo
```

Output đã kiểm chứng với Java 24 và bộ dữ liệu locale/time zone hỗ trợ các tag trong ví dụ:

```text
calendar.with=ISO
calendar.localized=ThaiBuddhist
calendar.base=ISO
date.with=2024-02-03
date.localized=2567-02-03
digits.with.zero=U+0030
digits.localized.zero=U+0E50
digits.explicitLast.zero=U+0030
fr.with.separator=U+002E
fr.localized.separator=U+002C
zone.with=UTC
zone.localized=America/New_York
zone.explicitLast=UTC
time.with=2024-01-01 00:00
time.localized=2023-12-31 19:00
base.zone=UTC
tests=PASS
```

**Diễn giải:**

1. `calendar.with=ISO` so với `calendar.localized=ThaiBuddhist` xác nhận sự khác nhau về chronology khi locale có `u-ca-buddhist`.
2. `date.with` và `date.localized` khác nhau về năm, dù cùng `LocalDate` đầu vào; đây là kết quả do hệ lịch, không phải vì đổi timezone.
3. `digits.with.zero=U+0030` (chữ số `0` ASCII) so với `digits.localized.zero=U+0E50` (chữ số Thai `๐`) xác nhận khác biệt `DecimalStyle`.
4. `digits.explicitLast.zero=U+0030` chứng minh một `withDecimalStyle(STANDARD)` ở bước sau có thể áp đặt lại ký hiệu số.
5. `fr.with.separator` và `fr.localized.separator` minh họa việc localizedBy cũng bản địa hóa `DecimalStyle` theo locale không có `u-nu`.
6. `zone.with=UTC` so với `zone.localized=America/New_York` chứng minh `u-tz-usnyc` được áp dụng bởi localizedBy.
7. `zone.explicitLast=UTC` cho thấy `withZone(UTC)` gọi sau cùng thắng yêu cầu timezone từ locale.
8. `base.zone=UTC` và `calendar.base=ISO` chứng minh các phương thức trả về formatter mới, **không sửa instance gốc**.
9. `tests=PASS` chỉ được in khi các assertion quan trọng qua được.

Chương trình sử dụng `point(...)` để in mã Unicode theo ASCII, tránh việc kết quả test phụ thuộc khả năng hiển thị chữ số Thai trên terminal. Sự sẵn có và cách ánh xạ một số extension `u-tz`, `u-nu` có thể phụ thuộc dữ liệu JDK/provider; với sản phẩm cần portable trên nhiều bản JDK, hãy kiểm tra các locale/extension thực sự được hỗ trợ và có fallback phù hợp.

## 13. Viết unit test: so sánh state trước, output localized sau

Một test tốt cần chỉ ra **hợp đồng riêng của từng phương thức**, không chỉ so sánh chuỗi format có thể phụ thuộc dữ liệu locale.

Ví dụ theo JUnit Jupiter, khi dự án đã có dependency phù hợp:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.time.ZoneId;
import java.time.chrono.IsoChronology;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import org.junit.jupiter.api.Test;

class DateTimeFormatterLocaleTest {

    @Test
    void withLocaleKeepsExplicitChronology() {
        var base = DateTimeFormatter.ofPattern("uuuu-MM-dd")
                .withChronology(IsoChronology.INSTANCE);
        var locale = Locale.forLanguageTag(
                "th-TH-u-ca-buddhist");

        var result = base.withLocale(locale);

        assertEquals("ISO", result.getChronology().getId());
        assertEquals("ISO", base.getChronology().getId());
        assertEquals(locale, result.getLocale());
    }

    @Test
    void localizedByAppliesCalendarExtension() {
        var base = DateTimeFormatter.ofPattern("uuuu-MM-dd")
                .withChronology(IsoChronology.INSTANCE);

        var result = base.localizedBy(
                Locale.forLanguageTag("th-TH-u-ca-buddhist"));

        assertEquals("ThaiBuddhist",
                result.getChronology().getId());
    }

    @Test
    void explicitZoneAfterLocalizedByWins() {
        var base = DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm")
                .withZone(ZoneId.of("UTC"));
        var locale = Locale.forLanguageTag(
                "en-US-u-tz-usnyc");

        var applied = base.localizedBy(locale);
        var overridden = applied.withZone(ZoneId.of("UTC"));

        assertEquals("America/New_York",
                applied.getZone().getId());
        assertEquals("UTC", overridden.getZone().getId());
        assertEquals("UTC", base.getZone().getId());
    }
}
```

Đây là tệp minh họa cho **JUnit Jupiter**, cần thư viện và test runner; không chạy trực tiếp bằng `java DateTimeFormatterLocaleTest`. Ví dụ minh họa dùng `assertEquals` trên state và tránh ràng buộc với chính tả tên tháng do provider cung cấp.

Ngoài test state, nếu ứng dụng có yêu cầu chuỗi hiển thị cụ thể, nên chạy integration/formatting test trên môi trường **cố định phiên bản JDK và dữ liệu locale**, hoặc chỉ kiểm tra những thuộc tính định dạng thật sự được quy định bởi ứng dụng. Khi nâng cấp JDK, đừng coi thay đổi bản dịch tên tháng của CLDR là lỗi business logic nếu sản phẩm không cam kết chuỗi đó.

## 14. Phân biệt Locale, Chronology, ZoneId và DecimalStyle

Các khái niệm này bổ sung cho nhau nhưng **không đồng nhất**:

| Đối tượng | Quy định gì? | Ví dụ |
| --- | --- | --- |
| `Locale` | Ngôn ngữ, region, script, extensions, tùy chọn bản địa hóa | `vi-VN`, `th-TH-u-ca-buddhist` |
| `Chronology` | Cách biểu diễn các trường ngày theo hệ lịch | ISO, ThaiBuddhist, Japanese |
| `ZoneId` | Múi giờ/luật chuyển đổi thời gian trên trục instant | `UTC`, `America/New_York` |
| `DecimalStyle` | Chữ số 0, dấu thập phân, dấu âm/dương dùng khi định dạng/phân tích | ASCII `0`, Thai `๐`, `.`, `,` |
| `DateTimeFormatter` | Quy tắc parse/format và các override được chọn | Pattern `uuuu-MM-dd HH:mm` |

Một `Locale` có thể đề xuất chronology hoặc zone qua extension, nhưng phải gọi API formatter phù hợp và xác minh support. Một DateTimeFormatter có thể sử dụng một locale cho **text** và vẫn giữ chronology ISO, zone UTC cho **ngữ nghĩa**.

Nếu dữ liệu đã là `Instant`, đổi zone có thể thay ngày/giờ địa phương hiển thị nhưng **không đổi instant**. Nếu dữ liệu là `LocalDate`, đổi chronology có thể đổi hệ năm/era được format mà không sửa ngày ISO được lưu trong biến.

Vì vậy, **đổi locale không đồng nghĩa đổi time zone**, và **đổi chronology không đồng nghĩa thay dữ liệu gốc**.

## 15. Lưu ý khi parse: không chỉ ảnh hưởng lúc in ngày

`DateTimeFormatter` dùng cùng cấu hình khi **format và parse**. Do đó:

- `withLocale` có thể tác động việc nhận tên tháng/thứ hoặc mẫu localized.
- `localizedBy` có thể tác động thêm cách hiểu lịch, chữ số, zone và ký hiệu số qua các override.
- `withChronology` có thể ảnh hưởng cách một bộ trường được giải quyết thành ngày theo chronology.
- `withZone` có thể cung cấp zone override cho kết quả parse hoặc việc diễn giải temporal theo hợp đồng cụ thể.
- `withDecimalStyle` ảnh hưởng các ký hiệu số được parser nhận.

Không nên parse một chuỗi ngày nghiệp vụ định dạng theo ISO bằng formatter vừa `localizedBy` với calendar/numbering không do bạn kiểm soát, rồi mặc định kết quả sẽ giống parser ISO bất kể locale.

Ví dụ khi nhận giao thức máy–máy cố định `2024-02-03`:

```java
LocalDate date = LocalDate.parse(
        "2024-02-03",
        DateTimeFormatter.ISO_LOCAL_DATE);
```

Sử dụng ISO formatter có hợp đồng rõ ràng phù hợp hơn là suy ra định dạng giao thức từ Locale mặc định của server. Dùng `localizedBy` khi **người dùng/định dạng dữ liệu thật sự yêu cầu** hỗ trợ lịch hoặc hệ chữ số khác.

Với tài nguyên người dùng, hãy xác nhận vùng định dạng và cách parse là đối xứng; không tự động lấy locale của browser rồi áp vào giá trị được lưu ở dạng chuẩn machine-readable.

## 16. An toàn luồng và tác động với ứng dụng nhiều người dùng

`DateTimeFormatter` là immutable, có thể dùng lại giữa nhiều luồng nếu cấu hình của formatter đã hoàn chỉnh. Gọi `withLocale` hoặc `localizedBy` sẽ tạo một formatter **dựa trên formatter gốc**, không thay đổi nó.

Ví dụ:

```java
private static final DateTimeFormatter BASE =
        DateTimeFormatter.ofPattern("uuuu-MM-dd");

static String display(LocalDate date, Locale locale) {
    DateTimeFormatter perRequest = BASE.withLocale(locale);
    return perRequest.format(date);
}
```

Đây là đoạn khai báo trường và phương thức **trong một lớp**; cần import `LocalDate`, `Locale` và `DateTimeFormatter`.

Với ứng dụng web có nhiều request:

1. Lấy locale thuộc **request/user cụ thể**.
2. Xác thực locale và extension được phép theo nhu cầu sản phẩm.
3. Tạo formatter phù hợp với request bằng `withLocale` hoặc `localizedBy`.
4. Áp dụng chronology/zone/decimal style bắt buộc của nghiệp vụ theo thứ tự rõ ràng.
5. Dùng formatter hoàn chỉnh để format/parse; không thay `Locale.setDefault(...)` toàn JVM cho từng request.

**Không sử dụng `Locale.getDefault()` như một proxy chắc chắn cho locale của mọi người dùng.** Default locale phụ thuộc môi trường chạy và không nhất thiết phản ánh sở thích của user. Việc thay default locale trên JVM có thể ảnh hưởng đến các thành phần khác.

Cũng cần lưu ý timezone được dùng từ locale extension không luôn là **múi giờ thực tế của thiết bị/người dùng**. Thông tin tz cần được thu thập và xác nhận riêng nếu bài toán quản lý giờ làm việc, giao dịch hoặc lịch hẹn dựa vào múi giờ người dùng.

## 17. Những hiểu nhầm thường gặp

| Hiểu nhầm | Vì sao sai? | Cách tiếp cận phù hợp |
| --- | --- | --- |
| “`localizedBy` chỉ là tên khác của `withLocale`.” | `localizedBy` có thể thay chronology, zone và decimal style | Xem extension và các override có sẵn |
| “`withLocale` sẽ tự áp dụng `u-ca-buddhist` thành `ThaiBuddhistChronology`.” | Javadoc nói nó chỉ lưu locale; không set chronology từ extension | Dùng `localizedBy` khi muốn áp dụng calendar |
| “`withLocale` luôn giữ đúng chuỗi format cũ.” | Text/pattern localized có thể thay theo locale | Phân biệt text với state chronology/zone |
| “`localizedBy` luôn đổi mọi trường.” | Phụ thuộc locale/extension/provider, một số giá trị có thể không đổi | Kiểm tra `getChronology/getZone/getDecimalStyle` |
| “Đặt `withZone(UTC)` trước `localizedBy` thì UTC luôn thắng.” | `u-tz` có thể ghi đè zone | Đặt `withZone(UTC)` **sau** nếu UTC là bắt buộc |
| “`Locale.FRANCE` trong `withLocale` tự thay dấu thập phân của DecimalStyle.” | `withLocale` không tự áp dụng decimal style mới | Dùng `localizedBy` hoặc `withDecimalStyle` đúng mục đích |
| “`u-nu-thai` làm mọi thư viện in chữ số Thai.” | Support extension thuộc formatter/provider cụ thể | Test tính năng và hỗ trợ fallback |
| “Chronology ThaiBuddhist nghĩa `LocalDate` đầu vào đã bị thay.” | Formatter chỉ chọn cách diễn giải/hiển thị ngày | Giữ dữ liệu ISO, kiểm tra formatter override |
| “`withLocale` sửa formatter gốc cho mọi request.” | `DateTimeFormatter` immutable | Dùng formatter per request, base dùng lại an toàn |
| “Locale quyết định chính xác múi giờ người dùng.” | Region/language không xác định timezone; `u-tz` chỉ là tag tùy chọn | Dùng ZoneId do nghiệp vụ/user xác nhận |
| “Unit test nên assert nguyên chuỗi tên tháng trên mọi JDK.” | CLDR/provider có thể thay đổi | Assert state/hợp đồng hoặc pin dữ liệu môi trường |
| “`localizedBy` sẽ xử lý thay cho validator BCP 47.” | Locale được parse trước; support extension không đồng nghĩa valid business policy | Validate tag và allowed options riêng |
| “Dùng `withLocale` trên `ISO_LOCAL_DATE` sẽ tự đổi thành định dạng địa phương.” | Pattern của ISO formatter được cố định | Dùng `ofLocalizedDate` khi cần mẫu theo vùng |
| “`getLocale()` giống nhau thì hai formatter tương đương.” | Chronology, zone, decimal style có thể khác | Kiểm tra các thuộc tính override |

## 18. Bài tập tự kiểm tra

### Câu 1: lịch nào được áp dụng?

```java
var ca = Locale.forLanguageTag("th-TH-u-ca-buddhist");
var base = DateTimeFormatter.ofPattern("uuuu-MM-dd")
        .withChronology(IsoChronology.INSTANCE);

var a = base.withLocale(ca);
var b = base.localizedBy(ca);
```

**Hỏi:** `a.getChronology()` và `b.getChronology()` có cùng lịch không?

**Đáp án:** Không. `a` giữ `ISO`, còn `b` có thể nhận `ThaiBuddhist` từ `u-ca-buddhist`. Hai formatter có cùng Locale nhưng chronology override khác nhau.

### Câu 2: đổi múi giờ theo thứ tự chaining

```java
var tz = Locale.forLanguageTag("en-US-u-tz-usnyc");
var a = DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm")
        .withZone(ZoneId.of("UTC"))
        .localizedBy(tz);

var b = DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm")
        .localizedBy(tz)
        .withZone(ZoneId.of("UTC"));
```

**Hỏi:** Vì sao `a` và `b` có thể có zone khác nhau?

**Đáp án:** `localizedBy(tz)` có thể áp dụng zone New York từ `u-tz-usnyc`, ghi đè UTC đã set trước; `withZone(UTC)` gọi sau cùng trên `b` ép lại UTC. Khi một ràng buộc nghiệp vụ là bắt buộc, cần đặt nó ở bước cấu hình cuối.

### Câu 3: số Thai và decimal style

```java
var digits = Locale.forLanguageTag("en-US-u-nu-thai");
var base = DateTimeFormatter.ofPattern("uuuu")
        .withDecimalStyle(DecimalStyle.STANDARD);

var a = base.withLocale(digits);
var b = base.localizedBy(digits);
```

**Hỏi:** Zero digit của `a` và `b` có thể khác không?

**Đáp án:** Có. `a` giữ `U+0030` từ STANDARD, còn `b` có thể dùng `U+0E50` (Thai digit zero) theo extension khi JDK hỗ trợ.

### Câu 4: cùng locale, output text có giống nhau?

```java
var base = DateTimeFormatter.ofPattern("d MMM uuuu");
var a = base.withLocale(Locale.FRANCE);
var b = base.localizedBy(Locale.FRANCE);
```

**Hỏi:** Có nên kết luận hai formatter chắc chắn hoàn toàn giống nhau ở mọi thuộc tính chỉ vì cùng Locale?

**Đáp án:** Không. Cả hai có thể cùng lookup tên tháng tiếng Pháp, nhưng `localizedBy` còn có thể thay `DecimalStyle` theo locale, trong khi `withLocale` giữ style đang có. Cần kiểm tra state và yêu cầu format/parse.

### Câu 5: ứng dụng cần format log ISO/UTC

**Hỏi:** Một bộ formatter log luôn cần UTC, ISO chronology và chữ số ASCII. Nếu phải cho phép thay locale cho phần text, nên làm gì?

**Đáp án:** Có thể dùng `withLocale` cho phần text và giữ override ISO/UTC/`DecimalStyle.STANDARD`. Nếu nhất thiết sử dụng `localizedBy`, đặt `withChronology(ISO)`, `withZone(UTC)` và `withDecimalStyle(STANDARD)` sau cùng, đồng thời test hợp đồng log.

### Câu 6: DateTimeFormatter immutable

**Hỏi:** Gọi `base.localizedBy(locale)` có đổi `base` không?

**Đáp án:** Không. Cả `localizedBy` và `withLocale` trả về formatter dựa trên instance cũ; instance gốc bất biến. Có thể dùng `base` làm template chung, rồi tạo formatter per request.

## 19. Checklist thiết kế formatter cho ứng dụng

1. **Cần đổi text/pattern hay cả calendar/numbering/zone?** Đây là câu hỏi quyết định hai phương thức.
2. **Đầu vào Locale có extension `ca`, `nu`, `rg`, `tz` không?** Nếu có, xác định có được phép ảnh hưởng lịch/chữ số/múi giờ hay không.
3. **Có yêu cầu ISO/Gregorian hoặc UTC bắt buộc?** Đặt `withChronology`/`withZone` sau cùng nếu dùng `localizedBy`.
4. **Cần dấu chữ số/decimal style cố định?** Dùng `withDecimalStyle` rõ ràng.
5. **Formatter dùng mẫu localized hay pattern cố định?** `withLocale` không tự đổi pattern cố định thành style locale.
6. **Có parse dữ liệu máy–máy theo định dạng ISO?** Dùng formatter chuẩn hóa thích hợp, tránh extension tác động ngoài dự định.
7. **Có test tên tháng/chữ số cho nhiều JDK/provider?** Ưu tiên assertion về state/hợp đồng; pin môi trường khi cần exact string.
8. **Có đọc locale từ user/header?** Validate tag, hỗ trợ region/extension và fallback; không dùng default JVM như sở thích mọi người.
9. **Có formatter base dùng chung?** Giữ base immutable, tạo formatter mới cho request; không đụng default locale toàn tiến trình.
10. **Thứ tự chaining đã được xem xét?** `localizedBy` có thể ghi đè override đã cấu hình trước nó.
11. **Có phân biệt ZoneId với offset và Instant với LocalDate không?** Đổi zone ảnh hưởng cách hiển thị instant, không phải đổi thời điểm thật.
12. **Đã kiểm tra `getLocale` cùng `getChronology`, `getZone` và `getDecimalStyle` khi debug?** Cùng locale không đảm bảo cùng định dạng/ngữ nghĩa.

## Kết luận

`withLocale(Locale)` và `localizedBy(Locale)` **đều đổi locale của một `DateTimeFormatter` bất biến**, nhưng **không có cùng độ sâu bản địa hóa**.

- **`withLocale`:** dùng locale cho **localized text/pattern**, không tự áp dụng Unicode locale extensions để ghi đè chronology, zone và decimal style.
- **`localizedBy` (Java 10+):** có thể dùng `ca`, `nu`, `rg`, `tz` và các dữ liệu locale để đặt thêm **calendar, numbering/decimal style và timezone**, bao gồm việc ghi đè các giá trị có sẵn.

Khi yêu cầu là **ngữ nghĩa ngày giờ cố định**, đặc biệt ISO chronology và UTC zone, cần giữ các override rõ ràng. Khi yêu cầu là **tôn trọng tùy chọn lịch/chữ số/múi giờ của người dùng**, `localizedBy` có vai trò phù hợp hơn. Kiểm tra thứ tự chaining và test trực tiếp state của formatter để tránh những lỗi bản địa hóa khó phát hiện.

## Tài liệu tham khảo chính thức

- [Java SE 26 — `DateTimeFormatter.localizedBy(Locale)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatter.html#localizedBy(java.util.Locale)): bổ sung từ Java 10, nêu rõ xử lý `ca`/`nu`/`rg`/`tz` và cảnh báo thứ tự chaining.
- [Java SE 26 — `DateTimeFormatter.withLocale(Locale)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatter.html#withLocale(java.util.Locale)): đặt locale phục vụ text/pattern, không tự set chronology/zone/decimal style từ extension.
- [Java SE 26 — `DecimalStyle`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DecimalStyle.html): zero digit và các ký hiệu số bản địa hóa.
- [Java SE 26 — `Locale`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.html): BCP 47 locale tags và Unicode extensions.
- [Java SE 26 — `Chronology`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/chrono/Chronology.html): lịch và cơ chế xử lý các ngày ngoài ISO.
- [Java SE 26 — `ZoneId`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZoneId.html): múi giờ và quy tắc vùng.
- [Unicode LDML — Unicode Locale Extensions](https://unicode.org/reports/tr35/): định nghĩa các key như `ca`, `nu`, `rg`, `tz` và dữ liệu bản địa hóa.

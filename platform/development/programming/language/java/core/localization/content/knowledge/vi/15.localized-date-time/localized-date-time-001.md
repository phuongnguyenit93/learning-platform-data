# DateTimeFormatter với locale tường minh trong Java

## 1. Tại sao phải chọn Locale khi định dạng ngày giờ?

Cùng một ngày `2026-10-28` có thể được người dùng các vùng đọc dưới những cách biểu đạt khác nhau:

- Tiếng Anh Mỹ: **Wednesday, 28 October 2026**.
- Tiếng Việt: **Thứ Tư, 28 tháng 10 2026**.
- Tiếng Pháp: **mercredi, 28 octobre 2026**.

Cả ba câu mô tả **cùng một ngày**, nhưng tên thứ, tên tháng, cách viết hoa, thứ tự thành phần và dấu câu có thể khác nhau. Nếu Java tự ghép `day + " October " + year`, thông điệp sẽ phụ thuộc ngôn ngữ viết trong code, khó dùng cho người đọc quốc tế.

Java 8+ cung cấp `java.time.format.DateTimeFormatter` để định dạng và phân tích (*parse*) ngày/giờ. API hỗ trợ chọn **`Locale` tường minh** ngay khi tạo formatter hoặc tạo bản sao với `withLocale(locale)`. Trong ứng dụng chạy Java 17+, đây là hướng tiếp cận ưu tiên cho các kiểu ngày giờ của `java.time`.

**Mục tiêu:** biết dùng `DateTimeFormatter.ofPattern(pattern, locale)`, `DateTimeFormatter.ofLocalizedDate(style).withLocale(locale)`, `LocalDate.parse(text, formatter)`; hiểu cách locale ảnh hưởng văn bản, vì sao **locale không phải múi giờ**, cách viết chương trình có kết quả tái lập, và cách tránh phụ thuộc `Locale.getDefault()` của máy chủ.

## 2. Phân biệt ba lớp thông tin

Một ứng dụng có thể cần ba thông tin riêng biệt:

| Khái niệm | Ví dụ | Quyết định điều gì? |
| --- | --- | --- |
| Ngày/giờ cần biểu diễn | `LocalDate.of(2026, 10, 28)` | Giá trị lịch: ngày, tháng, năm |
| Locale của người xem | `Locale.forLanguageTag("vi-VN")` | Ngôn ngữ tên tháng, tên thứ, quy tắc định dạng bản địa |
| Múi giờ của người xem | `ZoneId.of("Asia/Ho_Chi_Minh")` | Cách quy đổi một thời điểm toàn cầu thành giờ địa phương |

Không dùng `Locale` như một `ZoneId`. Chọn `vi-VN` **không tự động quy đổi một `Instant` sang múi giờ Việt Nam**. Tương tự, chọn `Asia/Ho_Chi_Minh` không có nghĩa phần chữ trong câu phải được viết bằng tiếng Việt.

Cũng không nên đồng nhất locale với một định dạng API bất biến:

- **Ngày hiển thị cho người dùng** cần formatter gắn locale và yêu cầu sản phẩm.
- **Ngày dùng làm dữ liệu trao đổi** thường dùng ISO 8601 hoặc định dạng được giao thức quy định; không phụ thuộc ngôn ngữ người xem.
- **Ngày/giờ trong log hoặc sự kiện** thường cần kèm offset/zone và cách biểu diễn không mơ hồ.

Trong Java hiện đại, thường dùng `LocalDate` cho ngày không có giờ, `LocalTime` cho giờ không có ngày, `LocalDateTime` cho ngày và giờ **không chứa vùng giờ**, `ZonedDateTime` khi cần vùng giờ, `OffsetDateTime` khi có offset, và `Instant` cho một thời điểm trên trục UTC.

## 3. API và cú pháp thiết yếu

### 3.1. Formatter từ pattern cùng Locale

```java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("EEEE, d MMMM uuuu", Locale.US);
```

Pattern gồm những thành phần:

- `EEEE`: tên thứ dạng đầy đủ, ví dụ `Wednesday`.
- `d`: ngày trong tháng, ví dụ `28`.
- `MMMM`: tên tháng dạng đầy đủ, ví dụ `October`.
- `uuuu`: năm lịch theo trường proleptic year (*year*, bao gồm năm 0 trong hệ lịch ISO).
- Dấu phẩy, dấu cách là literal của pattern.

Khi gọi `formatter.format(date)`, tên thứ/tháng được lấy từ dữ liệu locale, không phải từ một chuỗi tiếng Anh cứng. Pattern `EEEE, d MMMM uuuu` **vẫn cố định thứ tự và dấu câu**, vì đó là do lập trình viên đặt. Nếu muốn để hệ thống chọn kiểu ngày tự nhiên cho locale, nên dùng các formatter localized styles ở phần sau.

### 3.2. Tạo bản sao cho locale khác

```java
DateTimeFormatter english =
        DateTimeFormatter.ofPattern("EEEE, d MMMM uuuu", Locale.US);

DateTimeFormatter vietnamese =
        english.withLocale(Locale.forLanguageTag("vi-VN"));
```

`withLocale(...)` **trả về một formatter mới**, không sửa object `english`. `DateTimeFormatter` là lớp **immutable và thread-safe**. Điều này rất hữu ích trong web service có nhiều người dùng với locale khác nhau.

### 3.3. Formatter theo độ dài bản địa hóa

```java
DateTimeFormatter localized =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                .withLocale(Locale.US);
```

Thay vì tự ghi thứ tự `d MMMM uuuu`, `ofLocalizedDate` dùng quy tắc độ dài của từng locale; `withLocale` xác định locale dùng khi format.

`FormatStyle` có các giá trị `FULL`, `LONG`, `MEDIUM`, `SHORT`. Chúng biểu thị **mức chi tiết**, không bảo đảm cùng một pattern giữa các locale. Ví dụ `LONG` ở Mỹ có thể dùng `October 28, 2026`, trong khi một locale khác có thể đặt ngày trước tháng.

### 3.4. Parse bằng đúng formatter

```java
LocalDate parsed = LocalDate.parse(text, formatter);
```

Khi pattern chứa tên tháng bằng chữ, locale phải phù hợp với ngôn ngữ chuỗi đầu vào. Khi pattern chỉ gồm số và dấu phân cách, locale có thể ít hiển thị tác động hơn, nhưng resolver style, DecimalStyle và hệ lịch vẫn cần được cân nhắc.

## 4. Ví dụ hoàn chỉnh Java 17+: một ngày, ba locale

Tạo file `ExplicitLocaleDemo.java`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class ExplicitLocaleDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 10, 28);

        DateTimeFormatter base =
                DateTimeFormatter.ofPattern(
                        "EEEE, d MMMM uuuu", Locale.US);

        Locale vietnamese = Locale.forLanguageTag("vi-VN");
        DateTimeFormatter vi = base.withLocale(vietnamese);
        DateTimeFormatter fr = base.withLocale(Locale.FRANCE);

        System.out.println("US: " + base.format(date));
        System.out.println("VI: " + vi.format(date));
        System.out.println("FR: " + fr.format(date));
    }
}
```

Biên dịch bằng Java 17+ (lưu tệp UTF-8):

```bash
javac -encoding UTF-8 ExplicitLocaleDemo.java
java ExplicitLocaleDemo
```

Stdout được kiểm tra với dữ liệu locale của OpenJDK 24:

```text
US: Wednesday, 28 October 2026
VI: Thứ Tư, 28 tháng 10 2026
FR: mercredi, 28 octobre 2026
```

Để ý những đặc điểm:

1. `LocalDate` và giá trị ngày **không đổi**.
2. `base` vẫn dùng `Locale.US`; `withLocale` không đổi formatter ban đầu.
3. Tên thứ và tên tháng thay đổi theo locale; **thứ tự các trường vẫn như pattern cố định**.
4. Với dữ liệu CLDR/JDK khác, chi tiết viết hoa/tên tháng có thể hơi khác. Không dùng output tên thứ/tháng của một phiên bản JDK làm hợp đồng cố định cho mọi bản JDK.

Đây là một ví dụ **định dạng có locale tường minh**, khác với:

```java
DateTimeFormatter.ofPattern("EEEE, d MMMM uuuu")
```

Overload không truyền locale dùng locale mặc định thích hợp tại thời điểm tạo formatter, do đó có nguy cơ tạo chuỗi khác nhau giữa máy phát triển và máy chủ.

## 5. `ofLocalizedDate` để dùng bố cục ngày bản địa tự nhiên

Nếu mục tiêu là “hiển thị ngày theo văn phong người dùng”, không phải “bắt buộc một bố cục của nhà phát triển”, hãy ưu tiên localized style:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class LocalizedDateStyleDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 10, 28);

        DateTimeFormatter us =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                        .withLocale(Locale.US);

        DateTimeFormatter vi =
                us.withLocale(Locale.forLanguageTag("vi-VN"));

        System.out.println("US: " + us.format(date));
        System.out.println("VI: " + vi.format(date));
    }
}
```

Lưu thành `LocalizedDateStyleDemo.java` rồi chạy:

```bash
javac -encoding UTF-8 LocalizedDateStyleDemo.java
java LocalizedDateStyleDemo
```

Stdout minh họa đã kiểm tra trên OpenJDK 24:

```text
US: October 28, 2026
VI: 28 tháng 10, 2026
```

Với `ofLocalizedDate`, đầu ra là một **bố cục do dữ liệu locale chọn**, không chỉ là thay tên các trường trong pattern do code viết. Điều này khác với `ofPattern("MMMM d, uuuu", Locale.FRANCE)`: dù `MMMM` được dịch, thứ tự `tháng → ngày → năm` vẫn do programmer áp đặt.

Các factory khác:

| API | Dữ liệu đầu vào phù hợp | Ghi chú |
| --- | --- | --- |
| `ofLocalizedDate(style)` | `LocalDate` | Ngày không có giờ |
| `ofLocalizedTime(style)` | `LocalTime` hoặc temporal có trường giờ thích hợp | Với một số style (ví dụ FULL/LONG), có thể cần dữ liệu vùng giờ |
| `ofLocalizedDateTime(style)` | `LocalDateTime` hoặc temporal phù hợp | Chi tiết cần theo formatter style |
| `ofLocalizedDateTime(dateStyle, timeStyle)` | temporal có đủ trường ngày và giờ | Cho phép mức chi tiết ngày/giờ khác nhau |

**Cảnh báo:** không phải mọi `FormatStyle` thời gian đều format được một `LocalTime` không có múi giờ, đặc biệt nếu dữ liệu locale dùng tên vùng giờ. Phải chọn kiểu temporal phù hợp với các trường mà formatter yêu cầu.

## 6. Cách truyền Locale trong ứng dụng nhiều request

Nhiều hệ thống có nguồn locale từ tài khoản, cookie cấu hình hoặc `Accept-Language`. Dù đầu vào từ đâu, nên:

1. Giới hạn/chọn locale thực sự được sản phẩm hỗ trợ.
2. Chuyển thành `Locale` bằng `Locale.forLanguageTag(tag)` hoặc đối tượng `Locale` có sẵn.
3. Truyền locale vào formatter hoặc `withLocale`.
4. Không thay locale mặc định toàn JVM để phục vụ từng request.

Ví dụ một phương thức **độc lập** có thể đặt trong class `DateView`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public final class DateView {
    private DateView() {}

    public static String display(LocalDate date, Locale locale) {
        if (date == null || locale == null) {
            throw new IllegalArgumentException(
                    "date and locale must not be null");
        }
        DateTimeFormatter formatter =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                        .withLocale(locale);
        return formatter.format(date);
    }
}
```

Lưu thành `DateView.java` và biên dịch:

```bash
javac -encoding UTF-8 DateView.java
```

Đây là **utility class** có thể biên dịch, không có `main`, nên lệnh `java DateView` không phải bước chạy chương trình. Code gọi `DateView.display(date, requestLocale)` trong controller/service có trách nhiệm chọn locale phù hợp.

Không viết trong controller:

```java
Locale.setDefault(requestLocale);
String text = DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
        .format(date);
```

Đây là **mã minh họa cách làm cần tránh**: `Locale.setDefault` thay trạng thái dùng chung ở mức JVM; các request đồng thời có thể ảnh hưởng nhau, cũng như các thư viện khác sử dụng default locale.

`DateTimeFormatter` immutable cho phép dùng lại một formatter base, rồi gọi `withLocale` để lấy bản phù hợp cho mỗi ngôn ngữ. Với API có overload `ofPattern(pattern, locale)`, truyền locale trực tiếp cũng rõ ý định.

## 7. Locale không tự đổi múi giờ: ví dụ Instant và ZoneId

`Instant` là một thời điểm trên trục thời gian UTC, không tự giữ “10:30 ở Việt Nam” hoặc “03:30 ở UTC” dưới dạng biểu diễn người dùng. Để format giờ theo múi giờ cụ thể, cần `ZoneId`, `ZonedDateTime` hoặc formatter có `withZone`.

Chương trình độc lập:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class TimeZoneDisplayDemo {
    public static void main(String[] args) {
        Instant instant = Instant.parse("2026-10-28T03:30:00Z");

        DateTimeFormatter base =
                DateTimeFormatter.ofPattern(
                        "uuuu-MM-dd HH:mm VV", Locale.US);

        DateTimeFormatter utc =
                base.withZone(ZoneId.of("UTC"));
        DateTimeFormatter vietnam =
                base.withZone(ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println("UTC: " + utc.format(instant));
        System.out.println("VN: " + vietnam.format(instant));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 TimeZoneDisplayDemo.java
java TimeZoneDisplayDemo
```

Stdout:

```text
UTC: 2026-10-28 03:30 UTC
VN: 2026-10-28 10:30 Asia/Ho_Chi_Minh
```

**Bản chất:** `Instant` vẫn giữ cùng thời điểm; `withZone` chọn cách diễn đạt thời gian theo vùng. `withLocale` không có nhiệm vụ quy đổi offset. Pattern dùng `VV` để in **ID vùng giờ**; nếu dùng tên vùng giờ như `zzzz`, từ ngữ có thể thay đổi theo locale/data provider.

Nếu một formatter chỉ có `"HH:mm"` mà format trực tiếp `Instant` **không cung cấp zone**, nó có thể ném `UnsupportedTemporalTypeException` do chưa đủ các trường hour/minute trong temporal. Cách đúng là tạo formatter có zone (`withZone`) hoặc chuyển `instant.atZone(zoneId)` rồi format `ZonedDateTime`.

Trong giao diện quốc tế, locale và time zone cần là **hai lựa chọn độc lập**. Một người nói tiếng Việt đang ở Paris có thể muốn tên tháng tiếng Việt và giờ theo `Europe/Paris`; dùng `Locale.forLanguageTag("vi-VN")` với `ZoneId.of("Europe/Paris")` là hợp lệ.

## 8. Phân tích chuỗi chứa tên tháng: phải dùng đúng ngôn ngữ

Định dạng và parse là hai chiều của cùng một hợp đồng về pattern và locale. Ví dụ chuỗi tiếng Pháp `"28 octobre 2026"` cần formatter đọc tên tháng `octobre` bằng locale tiếng Pháp:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class ParseFrenchDateDemo {
    public static void main(String[] args) {
        DateTimeFormatter french =
                DateTimeFormatter.ofPattern(
                        "d MMMM uuuu", Locale.FRANCE);

        LocalDate date = LocalDate.parse(
                "28 octobre 2026", french);

        System.out.println(date);
        System.out.println(french.format(date));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ParseFrenchDateDemo.java
java ParseFrenchDateDemo
```

Stdout:

```text
2026-10-28
28 octobre 2026
```

Nếu dùng cùng pattern nhưng `Locale.US`, parser sẽ không nhận ra `octobre` như `October` trong trường hợp thông thường và ném `DateTimeParseException`.

Khi parse chuỗi người dùng nhập, cần biết:

- Chuỗi có ngôn ngữ gì? Nếu chứa tên tháng bằng chữ, phải biết locale của chuỗi.
- Pattern có phù hợp cấu trúc người dùng nhập không?
- Resolver style có chấp nhận hoặc điều chỉnh ngày không hợp lệ không?
- Chuỗi có chứa vùng/offset không? Nếu không, không thể tự suy ra một thời điểm UTC duy nhất.
- Với đầu vào tự do nhiều ngôn ngữ, một formatter duy nhất thường không đủ. Nên hạn chế định dạng nhập hoặc dùng bộ nhận dạng có kiểm soát và thông báo lỗi rõ ràng.

**Không lấy DateTimeFormatter để tự dịch một chuỗi tùy ý.** Nếu có `"28 octobre 2026"`, đúng hướng là parse thành `LocalDate` với formatter Pháp, sau đó format cùng `LocalDate` với formatter Việt; không thay nguyên từ `octobre` bằng `tháng 10` trên chuỗi.

## 9. ResolverStyle: không lẫn lỗi ngày không hợp lệ với lỗi locale

Mặc định `DateTimeFormatter.ofPattern` dùng resolver style `SMART`. Với một số dữ liệu ngày không hợp lệ, `SMART` có thể điều chỉnh ngày vào ngày cuối tháng. Nếu ứng dụng bắt buộc nhập đúng ngày thực tế, cấu hình `ResolverStyle.STRICT` là lựa chọn rõ ràng.

Ví dụ chạy độc lập:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class StrictDateParseDemo {
    public static void main(String[] args) {
        DateTimeFormatter strict =
                DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.US)
                        .withResolverStyle(ResolverStyle.STRICT);

        System.out.println(
                LocalDate.parse("28/10/2026", strict));

        try {
            LocalDate.parse("31/02/2026", strict);
        } catch (DateTimeParseException error) {
            System.out.println("Invalid date");
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 StrictDateParseDemo.java
java StrictDateParseDemo
```

Stdout:

```text
2026-10-28
Invalid date
```

Để parse năm theo kiểu strict khi làm việc với lịch ISO thông dụng, nên dùng `uuuu` thay vì `yyyy` nếu muốn có trường proleptic year và không muốn rơi vào vấn đề `year-of-era` thiếu thông tin về era. Dù vậy, `uuuu` có semantics khác `yyyy` ở những năm trước công nguyên, cần chọn theo mô hình dữ liệu.

**Phân biệt:** `Locale` quyết định các tên và quy ước bản địa; `ResolverStyle` quyết định cách hợp thức hóa các trường ngày/giờ khi parse. Hai chính sách độc lập.

## 10. Các ký tự pattern dễ nhầm lẫn

Một số ký tự được dùng thường xuyên:

| Ký tự | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `u` / `uuuu` | Năm theo proleptic year | Thường phù hợp khi parse strict trong ISO |
| `y` / `yyyy` | Year of era | Có thể cần era trong strict parsing |
| `M`, `MM` | Tháng dạng số | Một hoặc hai chữ số tùy pattern |
| `MMM`, `MMMM` | Tên tháng rút gọn/đầy đủ | Phụ thuộc locale |
| `L` | Tháng ở dạng stand-alone | Có thể khác dạng dùng trong câu ở một số ngôn ngữ |
| `d`, `dd` | Ngày của tháng | `dd` yêu cầu hai chữ số |
| `E`, `EEEE` | Tên thứ trong tuần | Phụ thuộc locale |
| `H`, `HH` | Giờ 0–23 | Không nhầm với `h` (1–12) |
| `h` | Giờ theo đồng hồ 12 giờ | Thường dùng kèm `a` (AM/PM) |
| `m` | Phút | Khác `M` là tháng |
| `s` | Giây | Không nhầm đơn vị giây khi parse |
| `X`, `XXX` | UTC offset theo kiểu ISO | Khác ID time zone |
| `V`, `VV` | ID múi giờ | `VV` là pattern thông dụng cho ID |
| `z`, `zzzz` | Tên múi giờ | Phụ thuộc locale/data provider |

**Lưu ý `YYYY` viết hoa:** trong `DateTimeFormatter`, `Y` là *week-based-year*, **không phải năm lịch thông thường**. Dùng `YYYY-MM-dd` có thể tạo năm trông sai ở ngày sát đầu/cuối năm. Với ngày lịch ISO, dùng `uuuu-MM-dd` hoặc formatter ISO chuyên dụng.

Trong pattern, dấu nháy đơn dùng để quote chữ literal. Ví dụ `"d 'tháng' M uuuu"` in từ `tháng` đúng nghĩa literal, nhưng chỉ phù hợp khi sản phẩm cố định lời văn đó cho một ngôn ngữ. Nếu muốn tên tháng bản địa hóa theo nhiều locale, dùng `MMMM` hoặc localized style.

## 11. Không phải mọi formatter đều phụ thuộc locale

Nhiều formatter có pattern chỉ toàn số có thể cho chuỗi giống nhau giữa locale khác nhau, ví dụ:

```java
DateTimeFormatter format =
        DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.FRANCE);
```

Nếu `LocalDate` là `2026-10-28`, kết quả thường vẫn `2026-10-28`: không có tên tháng/thứ để dịch, và formatter mặc định từ `ofPattern` có `DecimalStyle.STANDARD` trừ khi được điều chỉnh. Điều đó không có nghĩa locale vô dụng: khi đổi sang `MMMM`, `EEEE`, các localized patterns hoặc chronology có kiểm soát, khác biệt mới lộ rõ.

Các formatter như `DateTimeFormatter.ISO_LOCAL_DATE` được thiết kế cho biểu diễn ISO ổn định và thường thích hợp cho dữ liệu kỹ thuật. Không nên dùng tên tháng đã bản địa hóa làm khóa của JSON hoặc định danh ngày trong dữ liệu.

**DecimalStyle và chữ số:** `withLocale` không đồng nghĩa tự chuyển các chữ số sang hệ chữ số mong muốn. Khi cần thay hệ chữ số, xem `DecimalStyle` và `withDecimalStyle`; phải kiểm tra dữ liệu locale/JDK tương ứng. Đây là một khía cạnh khác với dịch tên tháng.

## 12. Tác động của Locale tới đối tượng formatter

`DateTimeFormatter` bất biến: các lời gọi sau tạo formatter mới:

```java
DateTimeFormatter fr = base.withLocale(Locale.FRANCE);
DateTimeFormatter zoned = fr.withZone(ZoneId.of("Europe/Paris"));
DateTimeFormatter strict = fr.withResolverStyle(
        ResolverStyle.STRICT);
```

Đây là **đoạn minh họa**, giả định có biến `base` kiểu `DateTimeFormatter` và import tương ứng. Không tự động sửa `base`, `fr` hoặc request khác. Vì formatter là immutable/thread-safe, có thể cache các formatter base hoặc các formatter đã chọn đúng locale/zone, miễn cache key phản ánh mọi thuộc tính quan trọng.

Nếu hệ thống có nhiều vùng và nhiều định dạng, có thể dùng một service chuyên trách tạo formatter:

```java
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public final class DateTimeView {
    private DateTimeView() {}

    public static String displayDate(
            LocalDate date, Locale locale) {
        DateTimeFormatter formatter =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                        .withLocale(locale);
        return formatter.format(date);
    }

    public static String displayInstant(
            java.time.Instant instant, Locale locale,
            ZoneId zone) {
        DateTimeFormatter formatter =
                DateTimeFormatter.ofLocalizedDateTime(
                        FormatStyle.MEDIUM)
                        .withLocale(locale)
                        .withZone(zone);
        return formatter.format(instant);
    }
}
```

Lưu vào `DateTimeView.java` và chạy `javac -encoding UTF-8 DateTimeView.java`. Đây là **utility class biên dịch được nhưng không có main**, không phải ví dụ tự in stdout. Trong dự án thực tế nên kiểm tra null, xác định chính sách locale/timezone được phép và kiểu dữ liệu đầu vào.

Với ứng dụng phục vụ nhiều khách hàng, điều quan trọng không phải tạo formatter mới ở mỗi nơi bằng mọi giá, mà là **không để việc chọn locale/timezone của một người dùng làm thay đổi global state** của người dùng khác.

## 13. Các lỗi phổ biến

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng `ofPattern(pattern)` không truyền locale | Phụ thuộc default locale của JVM | Dùng `ofPattern(pattern, locale)` |
| Dùng cùng một pattern US cho mọi ngôn ngữ | Tên tháng được dịch nhưng thứ tự trường cứng | Dùng `ofLocalizedDate(style)` khi cần bố cục bản địa |
| Dùng `Locale.setDefault` trong request | Thay trạng thái chung, có thể ảnh hưởng request khác | Truyền locale tường minh |
| Tưởng locale tự thay múi giờ | Giờ hiển thị lệch so với người dùng | Truyền `ZoneId` riêng |
| Format `Instant` bằng `"HH:mm"` nhưng không có zone | Có thể thiếu trường thời gian | `withZone` hoặc `instant.atZone(zone)` |
| Parse tên tháng Pháp bằng Locale.US | Không nhận dạng được văn bản | Dùng locale đúng với input |
| Dùng `YYYY` thay `uuuu` | Năm theo tuần có thể sai tại ranh giới năm | Dùng pattern năm lịch thích hợp |
| Parse ngày nhập sai với SMART mặc định | Có thể tự điều chỉnh ngày | `ResolverStyle.STRICT` khi nghiệp vụ yêu cầu |
| Dùng `yyyy` mà không nghĩ đến era khi STRICT | Có thể không dựng được `LocalDate` | Dùng `uuuu` nếu phù hợp lịch ISO |
| Dùng text theo locale làm dữ liệu API | API thay đổi khi server/ngôn ngữ thay đổi | Dùng ISO hoặc định dạng giao thức cố định |
| Giả định output localized style bất biến | Khác biệt theo CLDR/JDK/provider | Test trên môi trường đích |
| Nhầm `withLocale` với `withDecimalStyle` | Chữ số có thể không đổi như dự tính | Chọn DecimalStyle khi cần hệ chữ số |
| Format thông điệp thời gian bằng nối chuỗi | Sai trật tự, dấu câu/ngôn ngữ | Dùng formatter và bộ thông điệp bản địa hóa thích hợp |

`DateTimeFormatter` không xử lý tất cả công việc i18n. Nếu câu gồm văn bản tự nhiên như “Đơn hàng sẽ giao vào {ngày}”, dùng resource message hoàn chỉnh và đưa ngày đã format vào placeholder ở vị trí phù hợp; đừng nối prefix/suffix từ nhiều fragment cố định.

## 14. Checklist kiểm thử

Với các chức năng hiển thị ngày/giờ bản địa, tối thiểu nên kiểm tra:

1. **Locale tường minh:** cùng `LocalDate` hiển thị tên tháng/thứ phù hợp với `en-US`, `vi-VN`, `fr-FR`.
2. **Thứ tự thành phần:** với `FormatStyle.LONG`, bố cục của các locale có thể khác; không cố định kỳ vọng từ pattern của locale khác.
3. **Bất biến formatter:** `base.withLocale(locale)` không thay đổi kết quả format của `base`.
4. **Múi giờ:** cùng `Instant`, so sánh `UTC` với `Asia/Ho_Chi_Minh`; xác minh thời điểm không đổi.
5. **Đầu vào có tháng chữ:** parse tiếng Pháp bằng `Locale.FRANCE`, kiểm tra lỗi với locale khác.
6. **Strict parsing:** `28/10/2026` hợp lệ, `31/02/2026` phải báo lỗi trong `STRICT`.
7. **Ranh giới năm:** kiểm tra các ngày sát 1/1 và 31/12 nếu có pattern chứa năm, tránh nhầm `Y` và `u`.
8. **Dữ liệu thiếu zone:** bảo đảm `Instant` được format cùng vùng cụ thể, `LocalDateTime` không bị diễn giải thành UTC một cách ngẫu nhiên.
9. **Dữ liệu kỹ thuật:** serialized dates tuân theo format của API, không phải output localized UI.
10. **Dữ liệu bản địa hóa:** output có thể bị ảnh hưởng bản JDK/CLDR, nên cần kiểm thử đúng runtime/locale data được triển khai.
11. **Đa luồng:** không gọi `Locale.setDefault` theo request; formatter immutable có thể tái sử dụng có kiểm soát.

### Bài tập tự thực hành

- Viết formatter `DateTimeFormatter.ofPattern("EEEE, d MMMM uuuu", Locale.GERMANY)`, format `LocalDate.of(2026, 10, 28)` và so sánh tên tháng với bản `Locale.FRANCE`.
- Thay `FormatStyle.LONG` bằng `FULL` và `SHORT` trong ví dụ phần 5; kiểm tra cách viết ngày và xem kết quả có phụ thuộc provider không.
- Thử parse `"28 octobre 2026"` bằng formatter `Locale.US`; bắt và giải thích `DateTimeParseException`.
- Tạo một `Instant` cố định rồi format cho UTC, `Asia/Ho_Chi_Minh` và `Europe/Paris`; kiểm chứng sự khác biệt do múi giờ chứ không do locale.
- Viết test với `ResolverStyle.STRICT` cho `29/02/2024` (hợp lệ) và `29/02/2025` (không hợp lệ).
- Thiết kế trường dữ liệu `deliveryTime` cho API: quyết định dùng `Instant`/`OffsetDateTime` và chuẩn ISO, sau đó render cho người dùng ở tầng UI theo locale/timezone.

## 15. Kết luận

**`DateTimeFormatter` + `Locale` tường minh** giúp Java thể hiện tên thứ/tháng và kiểu trình bày đúng cho người đọc, không phụ thuộc ngẫu nhiên vào cấu hình locale mặc định của máy chủ.

Hãy ghi nhớ ba quyết định độc lập: **giá trị thời gian** (`LocalDate`, `Instant`, `ZonedDateTime`…), **locale hiển thị** (`Locale`) và **múi giờ** (`ZoneId`). Dùng `ofLocalizedDate(...).withLocale(locale)` khi muốn bố cục ngày phù hợp locale, dùng `ofPattern(..., locale)` khi có yêu cầu mẫu cụ thể, và dùng `ResolverStyle.STRICT` khi parse đầu vào bắt buộc có ngày hợp lệ. Với API và storage, giữ format kỹ thuật rõ ràng thay vì dùng chuỗi ngày đã dịch.

## Tài liệu tham khảo chính thức

- [Oracle Java 21 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Oracle Java 21 — FormatStyle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/FormatStyle.html)
- [Oracle Java 21 — ResolverStyle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/ResolverStyle.html)
- [Oracle Java 21 — Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html)
- [Oracle Java 21 — ZoneId](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZoneId.html)

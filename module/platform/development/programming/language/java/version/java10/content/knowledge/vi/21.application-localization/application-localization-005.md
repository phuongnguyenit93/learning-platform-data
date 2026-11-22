# DateTimeFormatter.localizedBy(Locale) — áp dụng Locale và Unicode extensions khi định dạng ngày giờ (Java 10+)

## 1. Khái niệm và điều cần phân biệt

`java.time.format.DateTimeFormatter.localizedBy(Locale locale)` là phương thức **được bổ sung từ Java 10**, vẫn là API chuẩn trong các phiên bản Java hiện đại. Nó trả về **một bộ định dạng mới** có các giá trị địa phương hóa được áp dụng theo `Locale`, bao gồm các thông tin liên quan tới **lịch**, **hệ chữ số**, **quy tắc vùng** và **múi giờ** khi locale chứa các Unicode extension được hỗ trợ.

Chữ ký API:

~~~java
public DateTimeFormatter localizedBy(Locale locale)
~~~

Đây là chữ ký phương thức trong thư viện, **không phải** một hàm cần tự viết. `locale` không được `null`.

Có hai yêu cầu ứng dụng dễ bị nhầm:

1. **Thay ngôn ngữ hiển thị** (tên tháng, tên ngày, cách chọn mẫu bản địa): thường dùng `withLocale(locale)` hoặc tạo formatter theo locale.
2. **Áp dụng cả những thiết lập do Unicode extensions trong locale yêu cầu** — chẳng hạn `ca=buddhist`, `nu=thai`, `tz=usnyc`: dùng `localizedBy(locale)`.

Ví dụ ngắn:

~~~java
import java.time.format.DateTimeFormatter;
import java.util.Locale;

// Đặt trong một phương thức:
DateTimeFormatter base =
        DateTimeFormatter.ofPattern("uuuu-MM-dd");

Locale thaiLocale = Locale.forLanguageTag(
        "th-TH-u-ca-buddhist-nu-thai");

DateTimeFormatter localized = base.localizedBy(thaiLocale);
~~~

Trong ví dụ, bộ định dạng được tạo ra có thể áp dụng **niên đại của lịch Phật giáo Thái** và **chữ số Thái**, thay vì chỉ thay nhãn ngôn ngữ. `base` **không bị sửa**.

**Tóm tắt chính xác theo Javadoc:**

- `localizedBy(locale)` tạo một bản sao cấu hình formatter.
- Nó dùng locale khi tra cứu dữ liệu văn bản/mẫu địa phương hóa.
- Nó có thể ghi đè chronology, decimal style và zone theo các Unicode locale extension `ca`, `nu`, `rg`, `tz`.
- Khi vừa có `ca` và `rg`, **`ca` được ưu tiên** quyết định lịch; đối với hệ chữ số, `nu` cũng ưu tiên giá trị ngầm định từ `rg`.
- Thứ tự gọi `localizedBy` so với `withZone`, `withChronology`, `withDecimalStyle`... **có thể thay đổi kết quả**.
- Cấu hình formatter mới **không** làm thay đổi đối tượng formatter ban đầu.

## 2. Unicode Locale Extension là gì?

Một thẻ ngôn ngữ theo chuẩn **BCP 47** có thể chứa phần **`-u-`** mô tả các ưu tiên bản địa hóa:

~~~text
th-TH-u-ca-buddhist-nu-thai-tz-usnyc
~~~

Diễn giải:

| Thành phần | Ý nghĩa |
| --- | --- |
| `th` | Ngôn ngữ Thái |
| `TH` | Vùng Thái Lan |
| `u` | Bắt đầu Unicode locale extension |
| `ca-buddhist` | Yêu cầu hệ lịch `buddhist` |
| `nu-thai` | Yêu cầu hệ số/chữ số `thai` |
| `tz-usnyc` | Yêu cầu múi giờ theo Unicode type `usnyc` |

Các khóa mà `DateTimeFormatter.localizedBy` đề cập rõ trong Javadoc:

| Khóa | Chủ đề | Cách tác động trong formatter |
| --- | --- | --- |
| `ca` | Calendar | Chọn chronology của lịch được yêu cầu, nếu được hỗ trợ |
| `nu` | Numbering system | Chọn quy tắc chữ số/`DecimalStyle` phù hợp |
| `rg` | Region override | Yêu cầu quy tắc vùng khác cho dữ liệu locale phù hợp; có thể tác động lựa chọn mặc định |
| `tz` | Time zone | Chọn múi giờ override tương ứng khi được nhận diện |

**`tz-usnyc` không phải một chuỗi IANA `America/New_York` đặt trực tiếp trong BCP 47.** `usnyc` là Unicode time-zone type, được JDK ánh xạ sang một `ZoneId` như `America/New_York`.

Thẻ BCP 47 **không thể được ghép tùy tiện từ mọi chuỗi không có kiểm tra**. Khi nhận tag từ cấu hình/người dùng, hãy phân tích và xác thực lựa chọn mà nghiệp vụ hỗ trợ. Không giả định mọi mã lịch, hệ số hoặc múi giờ đều tồn tại trên mọi JDK/provider.

### Tạo và kiểm tra Locale

~~~java
import java.util.Locale;

// Đặt trong phương thức:
Locale requested = Locale.forLanguageTag(
        "th-TH-u-ca-buddhist-nu-thai-tz-usnyc");

System.out.println(requested.getLanguage()); // th
System.out.println(requested.getCountry());  // TH
System.out.println(requested.getUnicodeLocaleType("ca")); // buddhist
System.out.println(requested.getUnicodeLocaleType("nu")); // thai
System.out.println(requested.getUnicodeLocaleType("tz")); // usnyc
~~~

`Locale.forLanguageTag` phân tích tag; `getUnicodeLocaleType(key)` đọc một giá trị extension hoặc trả `null` nếu không có khóa đó.

Khi thông tin đến từ các trường riêng, dùng builder:

~~~java
Locale requested = new Locale.Builder()
        .setLanguage("th")
        .setRegion("TH")
        .setUnicodeLocaleKeyword("ca", "buddhist")
        .setUnicodeLocaleKeyword("nu", "thai")
        .setUnicodeLocaleKeyword("tz", "usnyc")
        .build();
~~~

Các API `Locale.Builder` và `Locale.forLanguageTag` đã có từ trước Java 10 và tiếp tục phù hợp hiện nay. Builder giúp kiểm tra tính hợp lệ cú pháp của tag; ứng dụng vẫn phải xác thực các giá trị nghiệp vụ được phép.

## 3. Sự khác biệt quan trọng: `withLocale` và `localizedBy`

Đây là trọng tâm bài học.

### `withLocale(Locale)`

Javadoc mô tả `withLocale` là tạo bản sao formatter với **locale mới**. Nó lưu locale như được truyền vào và dùng locale đó khi tra cứu những phần cần địa phương hóa, chẳng hạn tên tháng hoặc pattern bản địa. Nếu locale có Unicode extensions, chúng **có thể được dùng về sau trong quá trình xử lý văn bản**, nhưng `withLocale` **không chủ động đặt chronology, override zone và decimal style từ các extension** theo cách `localizedBy` làm.

~~~java
DateTimeFormatter onlyLocale = base.withLocale(requested);
~~~

Khi chỉ cần đổi từ tên tháng tiếng Anh sang tiếng Pháp cho một pattern có chữ tháng, `withLocale(Locale.FRANCE)` thường là lựa chọn đủ rõ ràng.

### `localizedBy(Locale)`

~~~java
DateTimeFormatter fullyLocalized =
        base.localizedBy(requested);
~~~

Phương thức này **có thêm bước áp dụng các thông số từ locale/Unicode extension**. Trong ví dụ `ca=buddhist`, `nu=thai` và `tz=usnyc`, các thành phần chronology, decimal style, zone có thể khác cấu hình formatter cũ.

| Hành vi | `withLocale(locale)` | `localizedBy(locale)` |
| --- | --- | --- |
| Trả về formatter, không sửa bản gốc | Có | Có |
| Đổi locale dùng tra cứu tên tháng/mẫu | Có | Có |
| Lưu locale và Unicode extensions | Có | Có |
| Chủ động áp dụng `ca` vào chronology | Không theo quy tắc riêng của `withLocale` | Có khi được hỗ trợ |
| Chủ động áp dụng `nu` vào decimal style | Không theo quy tắc riêng của `withLocale` | Có khi được hỗ trợ |
| Chủ động áp dụng `tz` vào zone override | Không theo quy tắc riêng của `withLocale` | Có khi được hỗ trợ |
| Kết quả có thể phụ thuộc thứ tự xâu chuỗi với `withZone`/... | Không có cùng kiểu ghi đè từ extensions | **Có** |

**Không được kết luận quá mức rằng `withLocale` hoàn toàn “bỏ qua extensions”.** Tài liệu nói extensions có thể được dùng ở các bước tra cứu văn bản. Sự khác biệt cốt lõi là `localizedBy` **áp dụng chúng vào những thuộc tính nội tại của formatter**.

## 4. Lịch `ca`: thay chronology chứ không tự đổi một thời điểm thực

Ví dụ một ngày ISO:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

LocalDate date = LocalDate.of(2024, 1, 2);

DateTimeFormatter base =
        DateTimeFormatter.ofPattern("uuuu-MM-dd");

DateTimeFormatter buddhist = base.localizedBy(
        Locale.forLanguageTag("en-US-u-ca-buddhist"));

System.out.println(base.format(date));      // 2024-01-02
System.out.println(buddhist.format(date));  // 2567-01-02
~~~

Lịch `ThaiBuddhistChronology` đếm năm theo kỷ nguyên Phật giáo Thái, nên cùng một ngày tương ứng có năm **2567** thay vì năm **2024** trong ví dụ này. **Không phải ngày thực tế bị đẩy thêm 543 năm**; thay đổi là **cách biểu diễn theo hệ lịch** của cùng ngày.

Chú ý chọn ký hiệu pattern:

- `uuuu` là năm kéo dài (*proleptic year*) trong hệ lịch đang dùng.
- `yyyy` là năm theo kỷ nguyên (*year of era*); để hiểu hoàn toàn dữ liệu có trước công nguyên hoặc các hệ lịch có nhiều era, có thể cần thêm ký hiệu era `G`.
- `MM` và `dd` là tháng và ngày; tùy chronology, không nên đoán mọi lịch đều có cùng cấu trúc tháng/era như ISO.

Có thể quan sát chronology của formatter:

~~~java
System.out.println(
        buddhist.getChronology().getId()); // ThaiBuddhist
~~~

Trong những pattern đã có chronology/zone override, `localizedBy` có thể **ghi đè cấu hình cũ** bằng các giá trị từ locale. Nếu nghiệp vụ bắt buộc lưu ISO calendar, hãy lựa chọn locale không có `ca` khác ISO hoặc đặt chronology rõ ràng **sau** bước địa phương hóa khi phù hợp.

## 5. Hệ chữ số `nu`: một code point không phải luôn chữ số Latin

Với một locale yêu cầu hệ chữ số Thái:

~~~java
import java.time.format.DateTimeFormatter;
import java.util.Locale;

DateTimeFormatter digits = DateTimeFormatter
        .ofPattern("uuuu-MM-dd")
        .localizedBy(
                Locale.forLanguageTag("en-US-u-nu-thai"));
~~~

Formatter được địa phương hóa có thể dùng chữ số Thái, ví dụ các ký tự:

~~~text
Latin : 0 1 2 3 4 5 6 7 8 9
Thai  : ๐ ๑ ๒ ๓ ๔ ๕ ๖ ๗ ๘ ๙
~~~

`DecimalStyle` chứa các quy tắc biểu diễn số như **zero digit**, positive/negative sign và decimal separator. Khi `nu=thai` được hỗ trợ, có thể kiểm tra zero digit:

~~~java
char zero = digits.getDecimalStyle().getZeroDigit();

System.out.println(
        String.format(Locale.ROOT, "U+%04X", (int) zero));
// U+0E50
~~~

Trong ví dụ, `U+0E50` là chữ số `๐`.

**Không nhầm định dạng với thay đổi dữ liệu số:** ngày tháng trong `LocalDate` vẫn là các giá trị thời gian, không phải chuỗi Unicode đã được lưu bằng chữ số Thái. `DateTimeFormatter` biến đổi cách **hiển thị/phân tích chuỗi**. Khi định dạng lại bằng formatter khác, có thể nhận chữ số Latin.

### Không cố định mọi bộ ký hiệu Unicode trong kiểm thử xuyên môi trường

Locale data và provider có thể thay đổi qua JDK. Khi kiểm thử **một loại numbering được hỗ trợ trong môi trường kiểm soát**, có thể đối chiếu zero digit. Khi muốn kiểm thử ở nhiều phiên bản/provider, ưu tiên xác nhận **`getDecimalStyle()`, Locale và các giá trị được thỏa thuận** thay vì bắt mọi chuỗi hiển thị có chính xác cùng dấu cách/định dạng.

## 6. Múi giờ `tz`: chuyển đổi khi có instant để quy đổi

Với thẻ `-u-tz-usnyc`:

~~~java
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

DateTimeFormatter base = DateTimeFormatter
        .ofPattern("uuuu-MM-dd HH:mm VV")
        .withZone(ZoneId.of("UTC"));

DateTimeFormatter ny = base.localizedBy(
        Locale.forLanguageTag("en-US-u-tz-usnyc"));

System.out.println(ny.getZone());
// America/New_York (với dữ liệu JDK được kiểm thử)
~~~

`getZone()` cho biết zone override mà formatter đang dùng. Nó không thay đổi `ZoneId.systemDefault()` hay múi giờ toàn JVM.

Để thấy khác biệt thời gian, cần một **instant cụ thể**:

~~~java
import java.time.Instant;

Instant moment = Instant.parse("2024-01-02T12:34:56Z");

System.out.println(base.format(moment));
// 2024-01-02 12:34 UTC

System.out.println(ny.format(moment));
// 2024-01-02 07:34 America/New_York
~~~

Ngày 2/1/2024, New York đang dùng offset UTC-05, vì vậy cùng một instant được biểu diễn là `07:34` tại New York. **Đây là việc chuyển đổi cách trình bày theo múi giờ**, không có nghĩa instant gốc đã thay đổi.

Khi định dạng một `LocalDateTime` không có thông tin offset hoặc instant, không thể tự suy ra một mốc thời gian tuyệt đối duy nhất chỉ nhờ `Locale`. Vì vậy nếu ứng dụng muốn chuyển thời điểm từ UTC sang múi giờ khác, hãy làm việc với `Instant`/`ZonedDateTime` phù hợp, không xem `LocalDateTime` là đủ để xác định offset.

**Đặc biệt quan trọng:** giá trị `tz` trong Unicode language tag không phải cú pháp bất kỳ của `ZoneId.of`; ví dụ `usnyc` ánh xạ theo dữ liệu Unicode timezone. Đối với những timezone không có Unicode type phù hợp, có thể chỉ định rõ `ZoneId` bằng `withZone(ZoneId)`.

## 7. Region override `rg` và thứ tự ưu tiên giữa các extension

Khóa Unicode `rg` cung cấp một **region override** để dịch vụ locale có thể chọn quy tắc vùng thay thế. Ví dụ:

~~~text
en-US-u-rg-gbzzzz
~~~

Trong `rg=gbzzzz`, `GB` biểu thị vùng cần áp dụng, còn `zzzz` là hậu tố định dạng của Unicode region override. Nó **không có nghĩa** ngôn ngữ gốc của locale đã đổi sang tiếng Anh Anh; `getCountry()` vẫn có thể là `US`.

`DateTimeFormatter.localizedBy` có xét `rg` theo hợp đồng API khi chọn các giá trị địa phương hóa thích hợp. Nhưng không được mặc định rằng **mọi formatter, pattern tự viết hoặc mọi extension khác** đều đổi rõ ràng ngay khi có `rg`; hiệu ứng phụ thuộc kiểu định dạng và dữ liệu locale được dùng.

Khi **cả `ca` và `rg` được chỉ định**, Javadoc nói rõ:

- **`ca` ưu tiên** lựa chọn chronology so với chronology ngầm định từ `rg`.
- **`nu` ưu tiên** hệ chữ số so với numbering system ngầm định từ `rg`.

Ví dụ:

~~~java
Locale complex = Locale.forLanguageTag(
        "en-US-u-ca-buddhist-nu-thai-rg-gbzzzz");

DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("uuuu-MM-dd")
                .localizedBy(complex);
~~~

Ý định được thể hiện: nếu có quy tắc vùng GB ảnh hưởng các lựa chọn mặc định, các yêu cầu `ca=buddhist` và `nu=thai` vẫn được ưu tiên cho lịch và numbering system tương ứng.

Không được nhầm `rg` với `tz`: region override không thay thế cho việc chọn một `ZoneId` cụ thể với quy tắc giờ mùa hè và lịch sử offset.

## 8. Thứ tự gọi phương thức là một phần của thiết kế

Javadoc nhấn mạnh rằng, khác với `withLocale`, **`localizedBy` có thể tạo kết quả khác nhau tùy thứ tự xâu chuỗi với các phương thức `withXXXX()` khác**.

Xem ví dụ xác định múi giờ cuối cùng:

~~~java
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

DateTimeFormatter base =
        DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm")
                .withZone(ZoneId.of("UTC"));

Locale newYork = Locale.forLanguageTag(
        "en-US-u-tz-usnyc");

// Bước cuối cùng là withZone(UTC).
DateTimeFormatter zoneLast = base
        .localizedBy(newYork)
        .withZone(ZoneId.of("UTC"));

// Bước cuối cùng là localizedBy(locale có tz).
DateTimeFormatter localeLast = base
        .withZone(ZoneId.of("UTC"))
        .localizedBy(newYork);

System.out.println(zoneLast.getZone());   // UTC
System.out.println(localeLast.getZone()); // America/New_York
~~~

**Đọc từ trái sang phải:** phương thức nào đặt lại thuộc tính sau thì có thể thắng đối với chính thuộc tính đó. Nếu muốn locale quyết định múi giờ, thường gọi `localizedBy` **sau** khi tạo formatter cơ sở. Nếu muốn cưỡng chế zone do nghiệp vụ chỉ định, gọi `withZone` **sau** `localizedBy`.

Tương tự, với chronology:

~~~java
DateTimeFormatter thai =
        base.localizedBy(
                Locale.forLanguageTag("en-US-u-ca-buddhist"));

// Cưỡng chế lịch ISO sau khi xử lý yêu cầu ca:
DateTimeFormatter forcedIso =
        thai.withChronology(
                java.time.chrono.IsoChronology.INSTANCE);
~~~

Và với kiểu chữ số:

~~~java
DateTimeFormatter thaiDigits =
        base.localizedBy(Locale.forLanguageTag("en-US-u-nu-thai"));

// Ghi đè decimal style sau cùng nếu muốn Latin digits:
DateTimeFormatter latinDigits =
        thaiDigits.withDecimalStyle(
                java.time.format.DecimalStyle.STANDARD);
~~~

Đây là các **phương thức biến đổi formatter** theo kiểu trả về đối tượng mới; không có thao tác “sửa tại chỗ”.

### Quy tắc có thể áp dụng trong ứng dụng

Xác định ưu tiên cấu hình **một lần** rồi thống nhất thứ tự:

1. Chọn formatter/pattern cơ sở.
2. Áp dụng locale và extensions theo yêu cầu người dùng nếu cho phép.
3. Áp dụng những override bắt buộc của hệ thống sau cùng (`withZone`, `withChronology`, `withDecimalStyle` khi thích hợp).
4. Kiểm tra cấu hình cuối bằng `getLocale()`, `getZone()`, `getChronology()`, `getDecimalStyle()`, và kiểm thử format/parse.

Tránh dùng thứ tự xâu chuỗi ngẫu nhiên giữa các module. Sự thay đổi nhỏ về thứ tự gọi có thể làm ứng dụng hiển thị khác lịch hoặc múi giờ dù dữ liệu ngày giờ đầu vào vẫn giữ nguyên.

## 9. `localizedBy` có thay pattern đã viết hay tự “dịch” toàn bộ chuỗi không?

Cần phân biệt **pattern cố định** với **mẫu định dạng địa phương hóa**.

### Pattern tự viết

~~~java
DateTimeFormatter fixedPattern =
        DateTimeFormatter.ofPattern("uuuu-MM-dd");

DateTimeFormatter french =
        fixedPattern.localizedBy(Locale.FRANCE);
~~~

Pattern có thứ tự trường `năm-tháng-ngày` cố định; `localizedBy(Locale.FRANCE)` **không tự biến chữ pattern `uuuu-MM-dd` thành `dd/MM/uuuu`** chỉ vì locale là Pháp. Tuy nhiên nếu pattern dùng chữ tên tháng (ví dụ `MMMM`), tên tháng có thể được tra cứu theo ngôn ngữ locale.

### Formatter theo `FormatStyle`

~~~java
import java.time.format.FormatStyle;

DateTimeFormatter localizedDate =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                .localizedBy(Locale.FRANCE);
~~~

Với formatter thuộc nhóm `ofLocalizedDate`/`ofLocalizedDateTime`, **mẫu bản địa** được chọn theo locale trong quá trình định dạng. Đây là cách phù hợp khi mục tiêu là ngày hiển thị theo quy ước văn hóa chứ không phải một pattern kỹ thuật cố định.

Không hardcode kết quả có dấu câu/khoảng trắng cụ thể cho mọi provider, bởi dữ liệu CLDR có thể thay đổi giữa các phiên bản JDK. Nếu yêu cầu định dạng máy-đọc ổn định, hãy dùng formatter chuẩn ISO hoặc pattern kỹ thuật rõ ràng và không phụ thuộc locale.

### Các formatter ISO có nên thay bằng localizedBy?

`DateTimeFormatter.ISO_LOCAL_DATE`, `ISO_INSTANT` và các hằng ISO khác được thiết kế cho dạng biểu diễn chuẩn. Nếu cần chuỗi ISO để trao đổi dữ liệu giữa hệ thống, **không nên dùng `localizedBy` với calendar khác chỉ để “trang trí” chuỗi ISO**. Giữ định dạng trao đổi ổn định, và tạo formatter riêng phục vụ giao diện người dùng.

## 10. Ảnh hưởng khi định dạng và phân tích ngược (*parse*)

Một formatter có chronology, decimal style và zone override có thể ảnh hưởng **cả format và parse**. Ví dụ với lịch Phật giáo Thái và chữ số Thái:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

DateTimeFormatter thai = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", Locale.US)
        .localizedBy(
                Locale.forLanguageTag(
                        "en-US-u-ca-buddhist-nu-thai"));

LocalDate date = LocalDate.of(2024, 1, 2);
String text = thai.format(date);

System.out.println(text); // ๒๕๖๗-๐๑-๐๒
System.out.println(LocalDate.parse(text, thai)); // 2024-01-02
~~~

Tại sao `LocalDate.parse` lại trả ngày ISO 2024?

- Lúc **format**, ngày ISO đầu vào được biểu diễn theo chronology `ThaiBuddhist` với năm **2567**.
- Lúc **parse**, formatter đọc chữ số Thái và diễn giải năm/ngày theo chronology yêu cầu.
- `LocalDate.parse` trả về kiểu **`LocalDate` theo ISO**, tức ngày tương đương trong ISO là `2024-01-02`.

Đừng mặc định mọi chuỗi từ một hệ lịch đều có thể parse thành `LocalDate`. Một pattern không đủ trường để tạo ngày, dữ liệu không hợp lệ, hoặc chronology không hỗ trợ chuyển đổi mong muốn có thể gây `DateTimeParseException` hoặc ngoại lệ phù hợp.

Nếu ứng dụng cần giữ đối tượng ngày của một hệ lịch cụ thể, có thể dùng API `java.time.chrono` như `ThaiBuddhistDate` hoặc truy vấn chronology phù hợp thay vì ép mọi trường hợp về `LocalDate`.

### Parse không có nghĩa là tự suy ra instant

Nếu chuỗi chỉ chứa ngày giờ địa phương và không có đủ vùng/offset/zone, không thể luôn xác định **một Instant duy nhất**. Để parse thành `Instant` hoặc `ZonedDateTime`, cần pattern, formatter và input cung cấp đủ thông tin theo hợp đồng. `localizedBy` không phải trình đoán múi giờ từ mọi văn bản.

## 11. Chương trình Java đầy đủ và kết quả có thể kiểm chứng

Lưu đoạn sau thành **`LocalizedByLocaleDemo.java`**. Ví dụ dùng những API có từ Java 10 hoặc sớm hơn và chạy bằng **JDK 17+**.

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.chrono.IsoChronology;
import java.time.format.DateTimeFormatter;
import java.time.format.DecimalStyle;
import java.util.Locale;

public class LocalizedByLocaleDemo {
    public static void main(String[] args) {
        Locale requested = Locale.forLanguageTag(
                "th-TH-u-ca-buddhist-nu-thai-tz-usnyc");

        DateTimeFormatter base =
                DateTimeFormatter
                        .ofPattern("uuuu-MM-dd HH:mm VV", Locale.US)
                        .withChronology(IsoChronology.INSTANCE)
                        .withDecimalStyle(DecimalStyle.STANDARD)
                        .withZone(ZoneId.of("UTC"));

        DateTimeFormatter localized = base.localizedBy(requested);
        DateTimeFormatter onlyLocale = base.withLocale(requested);

        Instant instant =
                Instant.parse("2024-01-02T12:34:56Z");

        System.out.println(
                "baseTag=" + base.getLocale().toLanguageTag());
        System.out.println(
                "requestedTag=" + requested.toLanguageTag());
        System.out.println(
                "calendarKey=" + requested.getUnicodeLocaleType("ca"));
        System.out.println(
                "numbersKey=" + requested.getUnicodeLocaleType("nu"));
        System.out.println(
                "zoneKey=" + requested.getUnicodeLocaleType("tz"));

        System.out.println("localizedChrono="
                + localized.getChronology().getId());
        System.out.println("withLocaleChrono="
                + onlyLocale.getChronology().getId());

        System.out.println("localizedZero="
                + String.format(Locale.ROOT, "U+%04X",
                        (int) localized.getDecimalStyle().getZeroDigit()));
        System.out.println("withLocaleZero="
                + String.format(Locale.ROOT, "U+%04X",
                        (int) onlyLocale.getDecimalStyle().getZeroDigit()));

        System.out.println("localizedZone=" + localized.getZone());
        System.out.println("withLocaleZone=" + onlyLocale.getZone());

        System.out.println("localizedText=" + localized.format(instant));
        System.out.println("withLocaleText=" + onlyLocale.format(instant));
        System.out.println("originalText=" + base.format(instant));

        System.out.println("zoneLast="
                + base.localizedBy(requested)
                        .withZone(ZoneId.of("UTC")).getZone());
        System.out.println("localeLast="
                + base.withZone(ZoneId.of("UTC"))
                        .localizedBy(requested).getZone());

        DateTimeFormatter dateFormatter =
                DateTimeFormatter
                        .ofPattern("uuuu-MM-dd", Locale.US)
                        .localizedBy(
                                Locale.forLanguageTag(
                                        "en-US-u-ca-buddhist-nu-thai"));

        String thaiText =
                dateFormatter.format(LocalDate.of(2024, 1, 2));

        System.out.println("thaiDate=" + thaiText);
        System.out.println("parsedISO="
                + LocalDate.parse(thaiText, dateFormatter));

        System.out.println("baseStillUTC="
                + base.getZone().equals(ZoneId.of("UTC")));

        try {
            base.localizedBy(null);
        } catch (NullPointerException ex) {
            System.out.println("nullLocale=NPE");
        }
    }
}
~~~

Biên dịch và chạy (đặt encoding UTF-8 để hiển thị chữ số Thái trong nguồn theo đúng ý muốn):

~~~bash
javac -encoding UTF-8 LocalizedByLocaleDemo.java
java LocalizedByLocaleDemo
~~~

**`stdout` đã được kiểm thử trên JDK 24 với locale data mặc định:**

~~~text
baseTag=en-US
requestedTag=th-TH-u-ca-buddhist-nu-thai-tz-usnyc
calendarKey=buddhist
numbersKey=thai
zoneKey=usnyc
localizedChrono=ThaiBuddhist
withLocaleChrono=ISO
localizedZero=U+0E50
withLocaleZero=U+0030
localizedZone=America/New_York
withLocaleZone=UTC
localizedText=๒๕๖๗-๐๑-๐๒ ๐๗:๓๔ America/New_York
withLocaleText=2024-01-02 12:34 UTC
originalText=2024-01-02 12:34 UTC
zoneLast=UTC
localeLast=America/New_York
thaiDate=๒๕๖๗-๐๑-๐๒
parsedISO=2024-01-02
baseStillUTC=true
nullLocale=NPE
~~~

Cách hiểu từng nhóm kết quả:

1. **`requestedTag` và `calendarKey`/`numbersKey`/`zoneKey`** chứng minh locale giữ các Unicode extensions.
2. **`localizedChrono=ThaiBuddhist`** đối lập **`withLocaleChrono=ISO`**: `localizedBy` đã áp dụng `ca`; `withLocale` ở ví dụ giữ chronology ISO có sẵn.
3. **`localizedZero=U+0E50`** đối lập **`withLocaleZero=U+0030`**: `nu=thai` đã được áp dụng vào `DecimalStyle`.
4. **`localizedZone=America/New_York`** đối lập **`withLocaleZone=UTC`**: `tz=usnyc` đã thay zone override trong formatter địa phương hóa.
5. **`localizedText`** dùng năm Phật giáo, chữ số Thái và giờ New York cho cùng instant được formatter gốc in theo ISO/UTC.
6. **`zoneLast=UTC`** so với **`localeLast=America/New_York`** chỉ ra thứ tự xâu chuỗi có thể quyết định giá trị override cuối.
7. **`thaiDate`** và **`parsedISO`** mô tả thao tác format/parse với chronology khác ISO và chuyển đổi trở lại `LocalDate`.
8. **`baseStillUTC=true`** xác nhận `localizedBy` không sửa đối tượng formatter ban đầu.
9. **`nullLocale=NPE`** xác nhận đối số locale không được null.

Không lấy việc một console cụ thể không hiển thị chữ số Thái để kết luận formatter trả về chữ số Latin: điều đó có thể là giới hạn font/encoding khi xuất ra console. Các dòng kiểm tra `getZeroDigit` và mã Unicode là cách kiểm chứng cấu hình rõ ràng hơn.

## 12. Bất biến, an toàn đồng thời và tái sử dụng formatter

`DateTimeFormatter` được thiết kế **immutable** và **thread-safe**. Mọi phương thức `withLocale`, `localizedBy`, `withZone`, `withChronology`, `withDecimalStyle` trả về cấu hình formatter thay thế mà không sửa đối tượng gốc.

Ví dụ:

~~~java
DateTimeFormatter base = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", Locale.US);

DateTimeFormatter a = base.localizedBy(Locale.FRANCE);
DateTimeFormatter b = base.localizedBy(Locale.JAPAN);
~~~

Có thể tái sử dụng các formatter đã tạo trong nhiều luồng để format/parse theo cấu hình tương ứng. **Không cần khóa từng lần gọi `format`** trên cùng `DateTimeFormatter` bất biến chỉ vì nhiều luồng đọc chung.

Tuy nhiên:

- **`Locale.setDefault(...)`** tác động thiết lập mặc định dùng bởi các API không nhận locale tường minh; tránh thay đổi mặc định JVM trong ứng dụng nhiều người dùng chỉ để hiển thị một request.
- Nếu cache formatter theo locale, **khóa cache phải phân biệt đủ các extensions** và những override còn lại; cache chỉ theo `getLanguage()` có thể đưa nhầm formatter lịch/zone/chữ số.
- Nếu dữ liệu timezone hoặc locale provider thay đổi khi cập nhật JDK, kết quả hiển thị có thể khác; cần kiểm thử theo các yêu cầu cụ thể của ứng dụng.
- Formatter bất biến không đồng nghĩa dữ liệu đầu vào đã được kiểm tra: parse vẫn có thể ném `DateTimeParseException` cho text không hợp lệ.

### Nên tạo formatter theo request như thế nào?

Giữ một formatter cơ sở tái sử dụng và áp dụng locale riêng cho người dùng:

~~~java
private static final DateTimeFormatter BASE =
        DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm VV")
                .withZone(ZoneId.of("UTC"));

// Trong phương thức xử lý một request:
DateTimeFormatter requestFormatter =
        BASE.localizedBy(userLocale);
~~~

Đây là **mảnh mã minh họa nằm trong một lớp**, với biến `userLocale` cần được ứng dụng xác định. Nếu muốn **bắt buộc giữ UTC** bất kể extension `tz` của người dùng, cần viết:

~~~java
DateTimeFormatter requestFormatter =
        BASE.localizedBy(userLocale)
                .withZone(ZoneId.of("UTC"));
~~~

Với nhiều người dùng, **không sửa `Locale` mặc định toàn tiến trình** rồi hy vọng formatter tùy người dùng được cấu hình đúng.

## 13. Những lỗi thường gặp

| Hiểu nhầm | Giải thích và cách sửa |
| --- | --- |
| “`localizedBy` là tên khác của `withLocale`.” | Không. Nó còn có thể áp dụng chronology, decimal style và zone từ Unicode extensions. |
| “Thêm `u-ca-buddhist` chỉ dịch tên tháng.” | Nó có thể chọn `ThaiBuddhistChronology` và thay năm được trình bày. |
| “`u-nu-thai` sửa nội dung `LocalDate` thành chuỗi Thái.” | Không. Nó thay cách biểu diễn/phân tích chữ số qua formatter. |
| “`u-tz-usnyc` là một `ZoneId` Java có thể truyền thẳng vào `ZoneId.of`.” | Đó là Unicode timezone type; JDK ánh xạ nó sang timezone phù hợp. |
| “`localizedBy` sửa `base` tại chỗ.” | Không. Formatter bất biến, trả về đối tượng formatter mới/cấu hình mới. |
| “Gọi `withZone` rồi `localizedBy` luôn giống thứ tự ngược lại.” | Không. Bước sau có thể ghi đè giá trị của bước trước. |
| “Đổi zone sẽ tự quy đổi mọi `LocalDateTime` thành instant đúng.” | `LocalDateTime` không chứa zone/offset để nhận biết một thời điểm duy nhất. |
| “`localizedBy(Locale.FRANCE)` luôn đổi `uuuu-MM-dd` thành `dd/MM/uuuu`.” | Pattern cố định không tự biến thành pattern vùng; muốn mẫu bản địa dùng `ofLocalizedDate(...)`. |
| “`withLocale` luôn bỏ qua mọi Unicode extension.” | Javadoc cho phép extensions được dùng về sau khi xử lý văn bản, nhưng không chủ động đặt chronology/zone/decimal style như `localizedBy`. |
| “Có thể dựa vào format text y hệt trên mọi JDK.” | Mẫu locale, text và timezone data có thể khác theo provider và phiên bản JDK. |
| “Lịch Phật giáo tăng thời điểm lên 543 năm.” | Đây là đổi hệ lịch biểu diễn cùng một ngày, không phải thay instant thực. |
| “Formatter chỉ làm việc theo hướng format, không liên quan parse.” | Chronology/numbering/zone còn có thể ảnh hưởng phân tích chuỗi. |
| “Có thể đưa `null` cho locale để lấy mặc định.” | `localizedBy(null)` không hợp lệ, gây `NullPointerException`. |

## 14. Cách lựa chọn API phù hợp trong ứng dụng

**Trường hợp A — hiển thị tên tháng theo ngôn ngữ**, không thay lịch/zone:

~~~java
DateTimeFormatter fmt =
        DateTimeFormatter.ofPattern("dd MMMM uuuu")
                .withLocale(Locale.FRANCE);
~~~

Hợp lý khi bạn chỉ cần tên tháng tiếng Pháp và giữ các thuộc tính override đang có.

**Trường hợp B — người dùng có BCP 47 tag mang lịch, chữ số, timezone:**

~~~java
DateTimeFormatter fmt =
        DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm VV")
                .localizedBy(Locale.forLanguageTag(
                        "th-TH-u-ca-buddhist-nu-thai-tz-usnyc"));
~~~

Hợp lý khi ứng dụng **thực sự hỗ trợ** các extension được chỉ định và muốn formatter tuân theo chúng.

**Trường hợp C — lưu log, dữ liệu truyền API, khóa so sánh** cần chuẩn ngày giờ ISO thống nhất:

~~~java
String value = DateTimeFormatter.ISO_INSTANT.format(
        Instant.parse("2024-01-02T12:34:56Z"));
~~~

Không tự áp dụng lịch/ngôn ngữ của người dùng lên chuỗi máy đọc. Khi log dữ liệu ngày giờ, dùng ISO/UTC hay định dạng giao thức do hệ thống thống nhất.

**Trường hợp D — UI cần mẫu ngày ngắn hoặc dài của địa phương:**

~~~java
DateTimeFormatter fmt =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                .localizedBy(Locale.FRANCE);
~~~

Chọn formatter theo `FormatStyle` thay vì cố đoán mọi thứ tự trường/ngôn ngữ bằng một pattern cứng.

**Trường hợp E — phải giữ zone do nghiệp vụ yêu cầu dù locale có `tz`:**

~~~java
DateTimeFormatter fmt =
        DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm VV")
                .localizedBy(requestedLocale)
                .withZone(ZoneId.of("UTC"));
~~~

Gọi `withZone` sau `localizedBy` để làm rõ ưu tiên cuối cùng.

## 15. Bài tập tự kiểm tra

### Bài 1 — Đọc cấu trúc tag

Thẻ `th-TH-u-ca-buddhist-nu-thai-tz-usnyc` có những khóa nào?

**Đáp án:** `ca=buddhist` yêu cầu lịch Phật giáo, `nu=thai` yêu cầu hệ chữ số Thái, `tz=usnyc` yêu cầu múi giờ tương ứng New York. Ngôn ngữ vẫn `th`, vùng cơ sở vẫn `TH`.

### Bài 2 — Khác biệt `withLocale` và `localizedBy`

Cho formatter ban đầu có chronology ISO và zone UTC. Thẻ locale có `ca=buddhist`, `nu=thai`, `tz=usnyc`. Phương thức nào chủ động áp dụng những extension đó lên chronology, decimal style và zone?

**Đáp án:** `localizedBy(locale)`. `withLocale(locale)` lưu locale cho tra cứu văn bản/mẫu và không chủ động thiết lập ba thuộc tính đó từ extensions theo hợp đồng riêng của nó.

### Bài 3 — Thứ tự override

~~~java
var ny = Locale.forLanguageTag("en-US-u-tz-usnyc");

var f1 = DateTimeFormatter.ISO_DATE_TIME
        .localizedBy(ny)
        .withZone(ZoneId.of("UTC"));

var f2 = DateTimeFormatter.ISO_DATE_TIME
        .withZone(ZoneId.of("UTC"))
        .localizedBy(ny);
~~~

`getZone()` của mỗi formatter là gì trong JDK hỗ trợ `tz=usnyc`?

**Đáp án:** `f1` dùng `UTC`; `f2` dùng `America/New_York`. Bước cuối tương ứng ghi đè zone.

### Bài 4 — LocalDate và hai lịch

`LocalDate.of(2024,1,2)` được định dạng bằng `uuuu-MM-dd` kèm `u-ca-buddhist` có thể cho năm bao nhiêu?

**Đáp án:** `2567` trong lịch Phật giáo Thái cho cùng ngày ISO 2024-01-02. Đây là đổi cách biểu diễn lịch, không dịch chuyển instant.

### Bài 5 — Chữ số Thái

Nếu `getDecimalStyle().getZeroDigit()` trả về ký tự `๐`, Unicode code point nào tương ứng?

**Đáp án:** `U+0E50`; đó là chữ số 0 Thái. Nó không phải ký tự Latin `0`, có code point `U+0030`.

### Bài 6 — Parse lịch khác ISO

Một formatter đã địa phương hóa theo `ca=buddhist` và `nu=thai` in `๒๕๖๗-๐๑-๐๒`. Khi dùng `LocalDate.parse(text, formatter)`, ngày ISO tương đương là gì?

**Đáp án:** `2024-01-02` trong ví dụ. Formatter parse theo chronology, sau đó `LocalDate` biểu diễn ngày tương đương trong hệ ISO.

### Bài 7 — Pattern và mẫu bản địa

Bạn đang dùng `ofPattern("uuuu-MM-dd")` rồi gọi `localizedBy(Locale.FRANCE)`. Có chắc pattern được đổi sang `dd/MM/uuuu` không?

**Đáp án:** Không. `ofPattern` tạo format theo pattern đã chỉ định. Nếu muốn thứ tự trường/mẫu theo locale, dùng `ofLocalizedDate(FormatStyle...)` và gắn locale phù hợp.

### Bài 8 — Phần nào được bảo vệ trong môi trường nhiều luồng?

Có thể dùng chung một `DateTimeFormatter` đã tạo qua `localizedBy` cho nhiều luồng không?

**Đáp án:** Có, `DateTimeFormatter` là immutable và thread-safe. Nhưng phải đảm bảo mỗi request lấy đúng formatter được cấu hình theo locale của mình và không để locale mặc định toàn JVM bị thay đổi tùy tiện.

## 16. Kết luận

- **`DateTimeFormatter.localizedBy(Locale)` có từ Java 10 và vẫn hiện hành.**
- Nó không chỉ lưu locale: còn có thể **áp dụng `ca`, `nu`, `rg`, `tz`** để lựa chọn chronology, numbering/decimal style và zone theo hợp đồng API.
- **`withLocale` khác `localizedBy`**: `withLocale` không chủ động chuyển các Unicode extension thành các override formatter, dù extension vẫn có thể liên quan đến xử lý văn bản.
- **Thứ tự xâu chuỗi quan trọng**: `withZone`/`withChronology`/`withDecimalStyle` sau `localizedBy` có thể ghi đè những giá trị vừa được locale thiết lập, và ngược lại.
- **Lịch, chữ số và múi giờ là những khía cạnh khác nhau**. Đổi cách trình bày không đồng nghĩa đổi instant gốc.
- Khi parse/format, phải xác định rõ **ngày giờ đầu vào có phải instant hay chỉ local date-time**, pattern có đủ trường không, và đầu ra mong muốn là UI locale-specific hay dữ liệu trao đổi ISO.
- `DateTimeFormatter` bất biến, an toàn khi chia sẻ giữa luồng sau khi cấu hình; không sửa formatter gốc khi gọi `localizedBy`.

### Tài liệu chính thức

1. [Java SE 26 — DateTimeFormatter.localizedBy(Locale)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatter.html#localizedBy(java.util.Locale)) — chức năng, `ca/nu/rg/tz`, thứ tự ưu tiên, khác biệt với `withLocale`, `Since: 10`.
2. [Java SE 26 — DateTimeFormatter.withLocale(Locale)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatter.html#withLocale(java.util.Locale)) — locale cho tra cứu văn bản/mẫu, extensions và immutable formatter.
3. [Java SE 26 — DateTimeFormatter, Predefined/Localized Formatters](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatter.html) — pattern, `FormatStyle`, parse/format, thread safety.
4. [Java SE 26 — Locale and Unicode locale extensions](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.html) — BCP 47, `getUnicodeLocaleType`, `Locale.Builder`.
5. [Java SE 26 — DecimalStyle](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DecimalStyle.html) — zero digit, dấu và ký tự số địa phương.
6. [Java SE 26 — ThaiBuddhistChronology](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/chrono/ThaiBuddhistChronology.html) — hệ lịch Phật giáo Thái.
7. [OpenJDK JEP 314 — Additional Unicode Language-Tag Extensions](https://openjdk.org/jeps/314) — mở rộng xử lý Unicode language-tag extensions trong Java 10.

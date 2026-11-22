# Phối hợp các khóa `ca`, `nu`, `rg` và `tz` trong Java Locale

*Chủ đề: Java 10 — Locale trong ứng dụng. Nội dung tập trung vào cách dùng **đồng thời** các Unicode locale extension `ca`, `nu`, `rg` và `tz`, cách chúng ảnh hưởng đến formatter hiện đại, thứ tự ưu tiên, giới hạn hỗ trợ, kiểm thử, cùng những sai lầm thường gặp. Các ví dụ được biên dịch với Java 17 và chỉ sử dụng API vẫn áp dụng trên JDK hiện nay.*

## 1. Bài toán: một Locale có thể mang nhiều lựa chọn khác nhau

Giả sử người dùng muốn:

- Tên ngày/tháng bằng **tiếng Anh**, thay vì cần đổi ngôn ngữ giao diện.
- Hiển thị ngày theo **lịch Phật giáo Thái Lan** (*Buddhist calendar*).
- Hiển thị chữ số theo **hệ số Ả Rập-Indic**.
- Áp dụng một số **quy ước vùng Anh (GB)** dù locale cơ sở là `en-US`.
- Định dạng thời điểm theo **múi giờ Los Angeles**.

Bốn yêu cầu sau cùng không phải một khái niệm duy nhất. Trong Java, ta có thể biểu diễn bằng một **BCP 47 language tag có Unicode locale extension**:

~~~text
en-US-u-ca-buddhist-nu-arab-rg-gbzzzz-tz-uslax
~~~

Tạo đối tượng:

~~~java
Locale options = Locale.forLanguageTag(
        "en-US-u-ca-buddhist-nu-arab-rg-gbzzzz-tz-uslax");
~~~

Trong tag này:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `en` | Ngôn ngữ cơ sở | Tiếng Anh |
| `US` | Vùng cơ sở của Locale | Hoa Kỳ |
| `u` | Mở đầu nhóm Unicode locale extension | `-u-` |
| `ca-buddhist` | Calendar type | Lịch Buddhist |
| `nu-arab` | Numbering system | Chữ số Arabic-Indic |
| `rg-gbzzzz` | Region override | Dùng quy ước vùng GB ở API hỗ trợ |
| `tz-uslax` | Time-zone type | Định danh Unicode tương ứng vùng Los Angeles |

Đây là **một Locale**, nhưng mỗi key có một chức năng khác. Không phải cả bốn key đều đổi cùng một giá trị, và không phải mọi API Java sử dụng đủ bốn.

**Nguyên tắc:** Locale vừa là tập metadata vừa là **yêu cầu đối với dịch vụ i18n**. Việc một key được lưu trong tag không tự bảo đảm mọi formatter phải hiểu và áp dụng key đó.

## 2. Bối cảnh Java 10 và phạm vi hiện hành

Java đã hỗ trợ BCP 47 và Unicode locale extension từ trước Java 10. Hai key cơ bản:

- `ca` — calendar type.
- `nu` — numbering system.

Đã có hỗ trợ ở các API quốc tế hóa trước Java 10. **JEP 314, phát hành cùng Java 10**, tăng hỗ trợ thêm các key:

- `cu` — currency type.
- `fw` — first day of week.
- `rg` — region override.
- `tz` — time zone.

Đề bài này tập trung vào **phối hợp `ca`, `nu`, `rg` và `tz`**: hai key có từ trước kết hợp với hai extension được mở rộng hỗ trợ trong Java 10.

Một API đặc biệt quan trọng là:

~~~java
DateTimeFormatter.localizedBy(Locale locale)
~~~

Phương thức có từ **Java 10** này cho phép áp dụng locale cùng những extension hỗ trợ để cập nhật các thiết lập có liên quan như **chronology**, **numbering/decimal style**, **region** và **time zone**. Khác với phương thức `withLocale(locale)` vốn chủ yếu đặt locale phục vụ text và pattern được bản địa hóa.

Các API cốt lõi như `Locale.forLanguageTag`, `Locale.Builder`, `DateTimeFormatter.localizedBy`, `WeekFields.of`, `Currency.getInstance`, `NumberFormat`, `Chronology` và `ZoneId` vẫn hữu dụng trên Java 17+; đây không phải bài về API đã lỗi thời.

## 3. Quy tắc biểu diễn Unicode locale extension

### 3.1. Dấu `-u-` và cặp key–type

Định dạng khái quát:

~~~text
language[-Script][-REGION]-u-key-type[-key-type...]
~~~

Ví dụ:

~~~text
en-US-u-ca-buddhist
en-US-u-nu-arab
en-US-u-rg-gbzzzz
en-US-u-tz-uslax
en-US-u-ca-buddhist-nu-arab-rg-gbzzzz-tz-uslax
~~~

Trong nhóm này, `ca`, `nu`, `rg` và `tz` là các key hai ký tự; phần theo sau là type tương ứng.

- Không tự tạo chuỗi `ca=buddhist,nu=arab` rồi đưa vào `Locale.forLanguageTag` với kỳ vọng được hiểu là BCP 47.
- Không tự đặt type không tồn tại, sau đó cho rằng mọi formatter phải thực hiện đúng ý nghĩa bạn dự định.
- Không dùng lẫn `rg-gbzzzz` và `rg-gb`: với region override cần dạng type được đặc tả cho vùng tương ứng.
- Không dùng `tz-America/Los_Angeles` trong language tag: dấu gạch chéo và tên IANA trực tiếp **không phải** type Unicode `tz` phù hợp. Ví dụ hợp lệ ở đây dùng `tz-uslax`.

Có thể dùng `Locale.forLanguageTag` để parse tag chuẩn hóa:

~~~java
Locale locale = Locale.forLanguageTag(
        "en-US-u-ca-buddhist-nu-arab-rg-gbzzzz-tz-uslax");

System.out.println(locale.toLanguageTag());
// en-US-u-ca-buddhist-nu-arab-rg-gbzzzz-tz-uslax
~~~

Kết quả `toLanguageTag()` có thể **chuẩn hóa thứ tự hoặc kiểu viết** của các thành phần tag; khi so sánh các locale dùng `Locale.equals` hoặc các giá trị có ý nghĩa, đừng gắn logic vào thứ tự gõ ban đầu của key.

### 3.2. Đọc từng key đã parse

~~~java
System.out.println(locale.getUnicodeLocaleType("ca")); // buddhist
System.out.println(locale.getUnicodeLocaleType("nu")); // arab
System.out.println(locale.getUnicodeLocaleType("rg")); // gbzzzz
System.out.println(locale.getUnicodeLocaleType("tz")); // uslax
~~~

`getUnicodeLocaleType(key)` trả type đã lưu với key tương ứng hoặc `null` nếu key không có. **Đọc được type không đồng nghĩa formatter hỗ trợ type đó.** Ứng dụng cần kiểm tra API đích cùng tập calendar/numbering/time-zone type thực sự hỗ trợ.

### 3.3. Tạo bằng `Locale.Builder`

Khi xây động từ các lựa chọn cấu hình đã được kiểm tra:

~~~java
Locale options = new Locale.Builder()
        .setLanguage("en")
        .setRegion("US")
        .setUnicodeLocaleKeyword("ca", "buddhist")
        .setUnicodeLocaleKeyword("nu", "arab")
        .setUnicodeLocaleKeyword("rg", "gbzzzz")
        .setUnicodeLocaleKeyword("tz", "uslax")
        .build();
~~~

`Locale.Builder` giúp kiểm tra **cú pháp** tốt hơn so với việc ghép string tùy ý, nhưng bản thân nó **không phải registry xác nhận mọi type sẽ được mọi provider hỗ trợ**. Nếu ứng dụng nhận tùy chọn người dùng từ API, vẫn cần danh sách các giá trị hợp lệ cho sản phẩm.

### 3.4. Không cần thay JVM default Locale

~~~java
// Nên làm:
var formatter = DateTimeFormatter
        .ofLocalizedDateTime(FormatStyle.SHORT)
        .localizedBy(options);
~~~

Không nên gọi `Locale.setDefault(...)` mỗi request để thay ca/nu/rg/tz cho người dùng hiện tại: default locale là trạng thái **cấp tiến trình** và dễ gây xung đột giữa các request. Chuyển `Locale` như một tham số hoặc cấu hình của formatter bất biến sẽ rõ và an toàn hơn.

## 4. `ca` — calendar type là quy tắc lịch, không phải múi giờ

### 4.1. Ý nghĩa

`ca` (*calendar*) chỉ định hệ lịch, ví dụ:

~~~text
en-US-u-ca-buddhist
en-US-u-ca-japanese
en-US-u-ca-gregory
~~~

- `buddhist`: hệ lịch Phật giáo Thái Lan.
- `japanese`: lịch Nhật với era.
- `gregory`: lịch Gregorian, thường tương ứng ISO chronology trong java.time.

Không có nghĩa mọi tên calendar từ CLDR đều có một implementation `Chronology` trong JDK. Hãy xem các chronology mà phiên bản/runtime đang hỗ trợ; `java.time.chrono.Chronology` và những chronology cụ thể có contract riêng.

Trong ví dụ đã kiểm chứng:

~~~java
Locale calendarLocale =
        Locale.forLanguageTag("en-US-u-ca-buddhist");

var formatter = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.LONG)
        .localizedBy(calendarLocale);

System.out.println(formatter.getChronology().getId());
// ThaiBuddhist
~~~

`DateTimeFormatter.localizedBy` kết hợp locale và calendar extension để tạo formatter dùng `ThaiBuddhistChronology` ở nơi phù hợp. `getChronology()` cho biết chronology override của formatter.

### 4.2. Chuyển cùng ngày thực tế sang chronology khác

Ví dụ cùng ngày theo ISO:

~~~java
LocalDate iso = LocalDate.of(2026, 11, 7);

var buddhistChronology = formatter.getChronology();
var buddhistDate = buddhistChronology.date(iso);

System.out.println(iso.getYear()); // 2026
System.out.println(buddhistDate.get(ChronoField.YEAR)); // 2569
~~~

Đoạn này dùng `LocalDate`, `ChronoField` và một formatter đã `localizedBy` ở ví dụ trước. **Cả hai biểu diễn cùng ngày trong dòng thời gian**, nhưng thuộc hai hệ lịch có số năm khác nhau.

**Sai lầm quan trọng:** Đừng gọi `ThaiBuddhistChronology.date(2026,11,7)` rồi nghĩ đây là “chuyển ngày ISO 2026 sang Buddhist”. Overload nhận số nguyên năm/tháng/ngày hiểu **2026 là năm trong chính chronology ấy**. Muốn chuyển cùng ngày ISO, dùng `chronology.date(isoDate)` hoặc chuyển dựa trên epoch day/temporal thích hợp.

### 4.3. `ca` không chọn vùng thời gian

`ca=buddhist` có thể thay cách biểu diễn năm/lịch, nhưng không tự đặt múi giờ. Khi hiển thị **một Instant**, cần xác định zone riêng qua `ZoneId` hoặc extension `tz` nếu API có hỗ trợ. Calendar và time zone là hai khía cạnh khác nhau.

## 5. `nu` — hệ chữ số và DecimalStyle, không đổi giá trị toán học

### 5.1. Ý nghĩa

`nu` (*numbering system*) được dùng để chọn tập ký hiệu chữ số hoặc quy tắc biểu diễn số ở những dịch vụ có hỗ trợ:

~~~text
en-US-u-nu-latn
en-US-u-nu-arab
en-US-u-nu-thai
~~~

- `latn` thường biểu thị chữ số Latin `0–9`.
- `arab` biểu thị hệ chữ số Arabic-Indic.
- `thai` có thể được các dịch vụ hỗ trợ như hệ chữ số Thái.

Ở Java, `DateTimeFormatter` sử dụng `DecimalStyle` cho các ký hiệu chữ số và dấu phân cách số phù hợp. Ví dụ:

~~~java
Locale digitsLocale = Locale.forLanguageTag("en-US-u-nu-arab");

var formatter = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.SHORT)
        .localizedBy(digitsLocale);

char zero = formatter.getDecimalStyle().getZeroDigit();

System.out.println(Integer.toHexString(zero)); // 660
~~~

`0x0660` là code point Unicode của Arabic-Indic Digit Zero (U+0660). Một `nu` phù hợp sẽ khiến phần số của chuỗi ngày được format dùng hệ số tương ứng trên runtime hỗ trợ.

### 5.2. Giá trị số không đổi

~~~java
String formatted = NumberFormat
        .getNumberInstance(digitsLocale)
        .format(1234.5);
~~~

Dữ liệu số Java vẫn là giá trị `1234.5`. Chỉ cách hiển thị (ký hiệu chữ số và có thể các dấu) thay đổi. Đối với số trong protocol hoặc các field lưu trữ máy đọc, không nên dùng chuỗi localized để thay cho dữ liệu số gốc.

Trong JDK kiểm thử, chữ số đầu tiên của chuỗi `NumberFormat` với `en-US-u-nu-arab` là code point `U+0661`, khác `U+0031` của chữ số Latin `1`.

### 5.3. Không nhầm chữ số với ngôn ngữ

`en-US-u-nu-arab` vẫn có:

~~~java
locale.getLanguage(); // "en"
locale.getCountry();  // "US"
~~~

Ứng dụng có thể hiển thị ngày/tháng bằng tiếng Anh nhưng phần chữ số là Arabic-Indic. `nu` không dịch nội dung văn bản tùy ý sang tiếng Ả Rập.

**Kiểm thử đúng:** dùng `getDecimalStyle().getZeroDigit()`, mã Unicode hoặc dữ liệu locale chính thức; không chỉ so sánh screenshot, vì font có thể render glyph khác nhau.

## 6. `rg` — ghi đè vùng quy ước, không đổi trường Country

### 6.1. Ngữ nghĩa

`rg` là **region override**. Nó hướng dẫn một số API lấy quy ước văn hóa/định dạng theo vùng khác với vùng cơ sở của Locale.

Ví dụ:

~~~java
Locale regionOverride =
        Locale.forLanguageTag("en-US-u-rg-gbzzzz");

System.out.println(regionOverride.getLanguage()); // en
System.out.println(regionOverride.getCountry());  // US
~~~

Hai thành phần cơ sở **vẫn là en và US**. Nhưng dịch vụ có hỗ trợ `rg` có thể áp dụng **quy ước GB** cho những khía cạnh được quy định.

Trong thử nghiệm:

~~~java
System.out.println(
        Currency.getInstance(regionOverride).getCurrencyCode());
// GBP
~~~

`Currency.getInstance(locale)` ở đây dùng region override để lấy mã tiền tệ mặc định theo vùng GB, mặc dù `getCountry()` vẫn trả `US`.

**Không nhầm:** đây không phải phép đổi tỷ giá USD sang GBP. Trong giao dịch thực tế, mã tiền tệ phải đến từ dữ liệu nghiệp vụ hoặc một lựa chọn được người dùng xác nhận, không tự suy luận giá trị thanh toán chỉ từ locale.

### 6.2. Region override ảnh hưởng cả quy tắc tuần

~~~java
Locale base = Locale.forLanguageTag("en-US");
Locale withRegion = Locale.forLanguageTag("en-US-u-rg-gbzzzz");

System.out.println(WeekFields.of(base).getFirstDayOfWeek());
// SUNDAY trên JDK kiểm thử

System.out.println(WeekFields.of(withRegion).getFirstDayOfWeek());
// MONDAY trên JDK kiểm thử
~~~

Tuy nhiên, `WeekFields` còn có Unicode key `fw` dành riêng cho ngày đầu tuần. Nếu cả `rg` và `fw` xuất hiện, phải kiểm tra quy tắc ưu tiên của service; không giả định một key luôn ghi đè mọi lựa chọn khác.

Ở bài này, ta chỉ phối hợp bốn key `ca`, `nu`, `rg` và `tz`, nên ví dụ chọn region override mà không thêm `fw` để tách quan hệ dễ quan sát.

### 6.3. `rg` không xác định địa điểm thật

Locale `en-US-u-rg-gbzzzz` **không** cho biết người dùng đang ở Anh, sử dụng luật thuế Anh hay có địa chỉ giao hàng ở Anh. Nó chỉ là lựa chọn format locale.

Không dùng `rg` thay cho dữ liệu địa lý, tư cách cư trú, phân vùng pháp lý, tax region hay trạng thái quyền hạn. Đó là những trường dữ liệu cần nguồn xác thực riêng.

## 7. `tz` — mã múi giờ Unicode, không phải trực tiếp IANA ZoneId

### 7.1. Cách biểu diễn

~~~text
en-US-u-tz-uslax
~~~

`uslax` là một **Unicode time-zone type** trong language tag; trên JDK hỗ trợ, nó tương ứng với vùng múi giờ **America/Los_Angeles**.

Không viết:

~~~text
en-US-u-tz-America/Los_Angeles
~~~

Đó không phải BCP 47 Unicode locale extension phù hợp. Với code Java xử lý thời gian thông thường, có thể và thường nên dùng trực tiếp:

~~~java
ZoneId zone = ZoneId.of("America/Los_Angeles");
~~~

Còn `tz` thích hợp khi nhận các **tùy chọn i18n đã được mã hóa trong Locale**, và một service có thể áp dụng lựa chọn ấy.

### 7.2. Tác động khi dùng `localizedBy`

~~~java
Locale timeLocale =
        Locale.forLanguageTag("en-US-u-tz-uslax");

var formatter = DateTimeFormatter
        .ofLocalizedDateTime(FormatStyle.SHORT)
        .localizedBy(timeLocale);

System.out.println(formatter.getZone());
// America/Los_Angeles trên JDK kiểm thử
~~~

Múi giờ ảnh hưởng **giờ địa phương được hiển thị cho một thời điểm**. Nó không thay đổi chính `Instant` đang được lưu.

Ví dụ `Instant.parse("2026-11-07T12:00:00Z")` vẫn là cùng một thời điểm dù ta format tại UTC, Los Angeles hay Việt Nam. Có thể hiển thị ngày/giờ khác nhau sau quy đổi zone.

### 7.3. `tz` không có nghĩa đổi TimeZone mặc định toàn JVM

Chỉ vì một Locale chứa `tz=uslax` không có nghĩa JVM, các thread, database connection hay toàn bộ chương trình tự đổi time zone mặc định sang Los Angeles. Formatter chỉ áp dụng extension ở API thực sự có hỗ trợ.

Với một hệ thống lưu giao dịch, lịch hẹn hay timestamp, nên lưu `Instant` hoặc kiểu thời gian phù hợp và một `ZoneId` riêng khi cần xác định local time. Không suy zone từ mỗi `Locale.getCountry()`: một vùng quốc gia có thể có nhiều múi giờ.

## 8. Phối hợp bốn key trên cùng một Locale

Ta xét:

~~~java
Locale options = Locale.forLanguageTag(
        "en-US-u-ca-buddhist-nu-arab-rg-gbzzzz-tz-uslax");
~~~

Kỳ vọng ở các API được hỗ trợ:

| Thành phần | Lựa chọn | Ảnh hưởng cụ thể |
| --- | --- | --- |
| Language | `en` | Tên tháng/ngày và nhãn được bản địa hóa có thể dùng tiếng Anh |
| Base region | `US` | Vẫn trả bởi `getCountry()` |
| `ca=buddhist` | Lịch Buddhist | `DateTimeFormatter.localizedBy` dùng chronology Buddhist |
| `nu=arab` | Chữ số Arabic-Indic | `DecimalStyle`/`NumberFormat` dùng chữ số Arabic-Indic |
| `rg=gbzzzz` | Quy ước vùng GB | Các dịch vụ có hỗ trợ region override có thể dùng GB, ví dụ Currency/WeekFields |
| `tz=uslax` | Los Angeles | Formatter có hỗ trợ chọn zone `America/Los_Angeles` |

Điểm cốt lõi: chúng thay đổi **những lớp hiển thị khác nhau**.

- Lịch quyết định cấu trúc/số năm khi biểu diễn ngày.
- Numbering system quyết định cách viết chữ số.
- Region override định hướng dữ liệu locale cho một số quy ước vùng.
- Time zone quyết định cách ánh xạ một thời điểm sang ngày/giờ địa phương.
- Language của locale cơ sở vẫn phục vụ nội dung ngôn ngữ có liên quan, không bị tự động chuyển thành ngôn ngữ khác.

### 8.1. Thứ tự ưu tiên khi `ca` hoặc `nu` cùng có mặt với `rg`

Javadoc `DateTimeFormatter.localizedBy` nêu quy tắc cụ thể:

- Nếu **`ca` và `rg`** cùng được chỉ định, chronology từ **`ca` được ưu tiên** hơn chronology ngầm suy ra theo `rg`.
- Nếu **`nu` và `rg`** cùng được chỉ định, numbering system từ **`nu` được ưu tiên** hơn numbering system ngầm suy ra theo `rg`.

Vì vậy, `rg=gbzzzz` không xóa các lựa chọn rõ ràng `ca=buddhist` và `nu=arab`. Thử nghiệm cho thấy chronology vẫn là `ThaiBuddhist` và zero digit là U+0660.

Điều này **không** có nghĩa `ca` hay `nu` luôn chi phối **mọi** khía cạnh khác. Chúng chỉ ưu tiên trong những phần mà mỗi key có ý nghĩa. `rg` vẫn có thể ảnh hưởng Currency, quy tắc tuần và định dạng vùng; `tz` vẫn đặt zone khi được hỗ trợ.

### 8.2. Mô hình thứ tự xử lý dễ hiểu

~~~text
Locale cơ sở: en-US
  |
  +-- ca=buddhist ------> Chronology: ThaiBuddhist
  |
  +-- nu=arab ----------> DecimalStyle: Arabic-Indic digits
  |
  +-- rg=gbzzzz --------> Quy ước vùng GB ở API có hỗ trợ
  |
  +-- tz=uslax ---------> Zone: America/Los_Angeles
  |
  v
DateTimeFormatter.localizedBy(options)
  |
  +-- formatter chronology/decimal style/zone đã chọn
  +-- định dạng cùng một Instant theo các quy ước đó
~~~

Sơ đồ này thể hiện **các trách nhiệm**, không phải lời cam kết về thứ tự các hàm nội bộ của JVM.

## 9. `withLocale` khác `localizedBy` như thế nào?

Đây là điểm dễ sai khi phối hợp nhiều key.

### 9.1. `withLocale(locale)`

~~~java
var template = DateTimeFormatter
        .ofLocalizedDateTime(FormatStyle.LONG)
        .withZone(ZoneId.of("UTC"));

var byLocale = template.withLocale(options);
~~~

`withLocale` tạo một formatter mới với locale để tra cứu localized text/pattern. Nó **không tự động áp dụng tất cả `ca`/`nu`/`tz` thành chronology/decimalStyle/zone overrides**.

Trong ví dụ đã kiểm thử:

~~~text
withLocale chronology = ISO
withLocale zone = UTC
withLocale zero digit = U+30
~~~

Không nên phát biểu `withLocale` hoàn toàn “bỏ qua Unicode extensions”: tài liệu cho biết các extension vẫn có thể được dùng khi tra cứu text/localized pattern. Nhưng nó **không làm các override chronology, zone và decimal style tương ứng** như `localizedBy`.

### 9.2. `localizedBy(locale)` — API từ Java 10

~~~java
var localized = template.localizedBy(options);
~~~

Trên JDK thử nghiệm:

~~~text
localizedBy chronology = ThaiBuddhist
localizedBy zone = America/Los_Angeles
localizedBy zero digit = U+660
~~~

`localizedBy` không chỉ đổi language của nhãn. Nó áp dụng các lựa chọn calendar/region/numbering/time zone ở những phần formatter hỗ trợ và **có thể thay thế các thiết lập trước đó**.

### 9.3. Formatter gốc không bị sửa

`DateTimeFormatter` là bất biến:

~~~java
var original = DateTimeFormatter
        .ofLocalizedDateTime(FormatStyle.LONG)
        .withZone(ZoneId.of("UTC"));

var changed = original.localizedBy(options);

// original vẫn giữ ISO chronology và zone UTC.
// changed có thể dùng ThaiBuddhist chronology và zone Los Angeles.
~~~

Không cần lock khi tái sử dụng các instance `DateTimeFormatter` bất biến trong nhiều luồng, nhưng không nên mutate global locale settings per request. Từng request chọn hoặc cache formatter theo **đúng bộ cấu hình locale/zone** của nó.

## 10. Thứ tự gọi `localizedBy` và `withXxx` có thể thay đổi kết quả

`DateTimeFormatter.localizedBy` có thể **ghi đè** chronology, numbering và zone được thiết lập trước. Vì vậy thứ tự chaining có ý nghĩa.

### 10.1. Đặt zone trước rồi áp dụng Locale

~~~java
var formatter = DateTimeFormatter
        .ofLocalizedDateTime(FormatStyle.SHORT)
        .withZone(ZoneId.of("UTC"))
        .localizedBy(options);

System.out.println(formatter.getZone());
// America/Los_Angeles
~~~

`tz=uslax` được áp dụng ở bước `localizedBy` sau và đã thay đổi zone.

### 10.2. Áp dụng Locale rồi đặt zone riêng

~~~java
var formatter = DateTimeFormatter
        .ofLocalizedDateTime(FormatStyle.SHORT)
        .localizedBy(options)
        .withZone(ZoneId.of("UTC"));

System.out.println(formatter.getZone()); // UTC
~~~

Bây giờ `withZone(UTC)` được gọi **sau cùng**, nên quyết định zone cuối cùng của formatter.

Đây là điểm quan trọng khi một người dùng có locale chứa `tz`, nhưng nghiệp vụ muốn **format tất cả dữ liệu của một báo cáo theo UTC**: phải áp dụng zone riêng như một lựa chọn có chủ đích và kiểm thử thứ tự các lệnh.

### 10.3. Tương tự với chronology

~~~java
var isoFormatter = DateTimeFormatter
        .ofLocalizedDateTime(FormatStyle.SHORT)
        .localizedBy(options)
        .withChronology(IsoChronology.INSTANCE);
~~~

Dòng `withChronology(IsoChronology.INSTANCE)` sau cùng ghi đè chronology được chọn theo `ca=buddhist`; kết quả `getChronology().getId()` trở lại `ISO`.

Không nên dùng `localizedBy` sau khi đã đặt các override khác rồi giả định các override đó luôn thắng. Muốn một quy tắc rõ ràng: xác định **nguồn quyết định cuối** cho lịch, chữ số và múi giờ, sau đó cấu hình formatter theo thứ tự có chủ đích.

## 11. Chương trình Java 17+ hoàn chỉnh, có output đã kiểm chứng

Chương trình sau dùng **một tag chứa đồng thời `ca`, `nu`, `rg`, `tz`**, kiểm tra từng khía cạnh qua API có ý nghĩa, so sánh `withLocale` với `localizedBy`, kiểm tra ưu tiên khi override và dùng cùng ngày ISO để lấy năm theo lịch Buddhist.

~~~java
// File: LocaleExtensionCombinationDemo.java
import java.text.NumberFormat;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.chrono.IsoChronology;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.time.temporal.ChronoField;
import java.time.temporal.WeekFields;
import java.util.Currency;
import java.util.Locale;

public class LocaleExtensionCombinationDemo {
    public static void main(String[] args) {
        Locale base = Locale.forLanguageTag("en-US");
        Locale options = Locale.forLanguageTag(
                "en-US-u-ca-buddhist-nu-arab-rg-gbzzzz-tz-uslax");

        System.out.println("tag = " + options.toLanguageTag());
        System.out.println("language = " + options.getLanguage());
        System.out.println("country = " + options.getCountry());
        for (String key : new String[] {"ca", "nu", "rg", "tz"}) {
            System.out.println(key + " = " + options.getUnicodeLocaleType(key));
        }

        System.out.println("base currency = "
                + Currency.getInstance(base).getCurrencyCode());
        System.out.println("region-override currency = "
                + Currency.getInstance(options).getCurrencyCode());
        System.out.println("base first day = "
                + WeekFields.of(base).getFirstDayOfWeek());
        System.out.println("override first day = "
                + WeekFields.of(options).getFirstDayOfWeek());

        var template = DateTimeFormatter
                .ofLocalizedDateTime(FormatStyle.LONG)
                .withZone(ZoneId.of("UTC"));
        var byLocale = template.withLocale(options);
        var localized = template.localizedBy(options);

        System.out.println("withLocale chronology = "
                + byLocale.getChronology().getId());
        System.out.println("withLocale zone = " + byLocale.getZone());
        System.out.println("withLocale zero digit = U+"
                + Integer.toHexString(byLocale.getDecimalStyle().getZeroDigit()));
        System.out.println("localizedBy chronology = "
                + localized.getChronology().getId());
        System.out.println("localizedBy zone = " + localized.getZone());
        System.out.println("localizedBy zero digit = U+"
                + Integer.toHexString(localized.getDecimalStyle().getZeroDigit()));
        System.out.println("original chronology = "
                + template.getChronology().getId());
        System.out.println("original zone = " + template.getZone());

        String number = NumberFormat.getNumberInstance(options).format(1234.5);
        System.out.println("number first digit = U+"
                + Integer.toHexString(number.codePointAt(0)));

        var date = LocalDate.of(2026, 11, 7);
        System.out.println("ISO year = " + date.getYear());
        System.out.println("Buddhist same date year = "
                + localized.getChronology().date(date).get(ChronoField.YEAR));

        var instantFormatter = DateTimeFormatter
                .ofLocalizedDateTime(FormatStyle.SHORT)
                .localizedBy(options);
        System.out.println("instant formatter zone = "
                + instantFormatter.getZone());
        System.out.println("instant has formatted digits = "
                + instantFormatter.format(Instant.parse("2026-11-07T12:00:00Z"))
                        .codePoints().anyMatch(Character::isDigit));

        System.out.println("localized then explicit zone = "
                + localized.withZone(ZoneId.of("UTC")).getZone());
        System.out.println("localized then explicit chronology = "
                + localized.withChronology(IsoChronology.INSTANCE)
                        .getChronology().getId());
        System.out.println("explicit zone then localized = "
                + template.localizedBy(options).getZone());

        var built = new Locale.Builder()
                .setLanguage("en")
                .setRegion("US")
                .setUnicodeLocaleKeyword("ca", "buddhist")
                .setUnicodeLocaleKeyword("nu", "arab")
                .setUnicodeLocaleKeyword("rg", "gbzzzz")
                .setUnicodeLocaleKeyword("tz", "uslax")
                .build();

        System.out.println("builder equals parsed = " + built.equals(options));
        System.out.println("base unchanged = " + base.toLanguageTag());
    }
}
~~~

Chạy trên JDK 17 trở lên:

~~~bash
javac --release 17 LocaleExtensionCombinationDemo.java
java LocaleExtensionCombinationDemo
~~~

**Stdout đã kiểm chứng với JDK 24**:

~~~text
tag = en-US-u-ca-buddhist-nu-arab-rg-gbzzzz-tz-uslax
language = en
country = US
ca = buddhist
nu = arab
rg = gbzzzz
tz = uslax
base currency = USD
region-override currency = GBP
base first day = SUNDAY
override first day = MONDAY
withLocale chronology = ISO
withLocale zone = UTC
withLocale zero digit = U+30
localizedBy chronology = ThaiBuddhist
localizedBy zone = America/Los_Angeles
localizedBy zero digit = U+660
original chronology = ISO
original zone = UTC
number first digit = U+661
ISO year = 2026
Buddhist same date year = 2569
instant formatter zone = America/Los_Angeles
instant has formatted digits = true
localized then explicit zone = UTC
localized then explicit chronology = ISO
explicit zone then localized = America/Los_Angeles
builder equals parsed = true
base unchanged = en-US
~~~

### 11.1. Phân tích chi tiết

**Khối 1 — Parse tag:** `getLanguage` là `en`, `getCountry` là `US`, còn `getUnicodeLocaleType` đọc đúng bốn type. Các extension không sửa trường language/country cơ sở.

**Khối 2 — Region override:** `Currency.getInstance(base)` chọn USD; `Currency.getInstance(options)` chọn GBP do `rg=gbzzzz` trên JDK thử. Tương tự, `WeekFields` chọn Monday cho vùng GB trong khi base US là Sunday. Những quan sát này giúp thấy `rg` có hiệu lực **đồng thời với các key khác**.

**Khối 3 — Locale và chronology:** `withLocale(options)` giữ chronology/zone/decimal style đã được xác định trên template, còn `localizedBy(options)` áp dụng Buddhist, Los Angeles và chữ số Arabic-Indic. `original chronology`/`original zone` xác nhận formatter gốc không bị mutate.

**Khối 4 — Chữ số:** `number first digit = U+661` là code point của Arabic-Indic Digit One (U+0661) trong chuỗi `NumberFormat`. `localizedBy zero digit = U+660` là Arabic-Indic Digit Zero. Không in trực tiếp số có glyph khác nhau để tránh phụ thuộc font console.

**Khối 5 — Lịch:** một `LocalDate` ISO có năm 2026, nhưng khi chuyển **cùng ngày** sang chronology Buddhist, số năm là 2569. Đó là **hai cách biểu diễn cùng một ngày**, không phải dữ liệu đầu vào bị cộng vô điều kiện 543 trong mọi lịch.

**Khối 6 — Zone:** `localizedBy` chọn zone Los Angeles. Chương trình format một `Instant` có thật và chỉ kiểm tra có chữ số trong output, tránh gắn tài liệu vào một localized date/time pattern cụ thể có thể đổi theo dữ liệu locale.

**Khối 7 — Thứ tự override:** gọi `withZone(UTC)` hoặc `withChronology(ISO)` sau `localizedBy` thay đổi một lựa chọn cụ thể. Khi `localizedBy` đến sau `withZone`, `tz=uslax` lấy lại zone LA.

**Khối 8 — Builder:** hai cách khởi tạo cùng biểu diễn một locale. Chương trình không thay đổi default JVM và không gán giá trị locale vào bất kỳ trạng thái dùng chung nào.

### 11.2. Giới hạn của stdout

Kết quả được xác minh với JDK 24 có dữ liệu locale phù hợp; các mã chronology, zone và code point là những quan sát cụ thể. Một runtime đóng gói tối giản, cấu hình locale provider khác hoặc bộ dữ liệu CLDR được nâng cấp có thể làm **chi tiết hiển thị** khác nhau. Trong production, test bộ runtime mà hệ thống thực sự dùng; không cố định toàn bộ chuỗi đã bản địa hóa như một protocol vĩnh viễn.

## 12. `rg`, `ca`, `nu` và `tz` không thay thế thông tin nghiệp vụ riêng

Có ba lớp cần phân biệt rõ:

| Dữ liệu | Dùng để làm gì? | Không được nhầm với |
| --- | --- | --- |
| `Locale` với Unicode extensions | Quy ước hiển thị và những lựa chọn i18n | Quốc tịch, địa điểm thật, quyền truy cập |
| `ZoneId`/`Instant` | Thời gian có ý nghĩa chính xác | Tên quốc gia hoặc ngôn ngữ UI |
| `Currency`/amount | Loại tiền và giá trị giao dịch | `rg` hoặc `cu` chỉ để mặc định hiển thị |
| `Chronology`/`LocalDate` | Hệ lịch và ngày lịch | Timestamp cụ thể khi không có time zone |
| `NumberFormat`/`DecimalStyle` | Quy tắc biểu diễn số | Giá trị số Java hoặc format của JSON number |

Ví dụ một người dùng chọn hiển thị lịch Buddhist, chữ số Arabic-Indic và region override GB; giao dịch của họ vẫn có thể có:

~~~text
amount = 100.00
currency = USD
instant = 2026-11-07T12:00:00Z
business time zone = Asia/Ho_Chi_Minh
~~~

Các trường này không tự thay đổi chỉ vì form đang hiển thị `en-US-u-ca-buddhist-nu-arab-rg-gbzzzz-tz-uslax`. Nếu hệ thống dùng `tz=uslax` để **hiển thị** báo cáo, đó là lựa chọn presentation. Muốn đổi múi giờ nghiệp vụ của lịch hẹn, phải có chính sách riêng, không suy từ cú pháp Locale.

### 12.1. Không dùng calendar type để lưu ngày chuẩn

Một ứng dụng có thể lưu ngày dưới dạng `LocalDate` ISO hoặc một mô hình ngày theo chronology cần thiết, rồi chuyển sang lịch khác **khi hiển thị**. Không ghi chuỗi ngày Buddhist đã bản địa hóa vào một field mà parser bên khác kỳ vọng ISO-8601.

Khi cần truyền thời điểm giữa các service, nên dùng `Instant` hoặc định dạng thời gian chuẩn có zone/offset rõ ràng. Định dạng theo `ca/nu/tz` phục vụ người dùng cuối, không phải giao thức thay thế dữ liệu thời gian chuẩn.

### 12.2. Không để `nu` đổi representation của API số máy-máy

Một chuỗi số có Arabic-Indic digits không nhất thiết được mọi parser của JSON, CSV hoặc giao thức nội bộ chấp nhận. Nếu API yêu cầu JSON number, hãy dùng serializer chuẩn; để `NumberFormat` phục vụ UI và báo cáo dành cho con người.

### 12.3. Không dùng `rg` để xác minh vùng pháp lý

`rg=gbzzzz` là **quy tắc vùng của một formatter**. Nó không chứng minh người dùng cư trú tại GB, chịu thuế GB hay được phép xem một nội dung bị giới hạn vùng. Dùng nguồn dữ liệu pháp lý/xác thực tương ứng, tránh lấy locale làm điều kiện authorization.

## 13. Kiểm tra support: parse hợp lệ khác với áp dụng được extension

Các hàm xây/parse `Locale` có thể giữ các key/type trong language tag, nhưng:

- Một calendar type có thể không có chronology tương ứng trong Java runtime.
- Một numbering system type có thể không được formatter/provider hiểu.
- Một region override có thể không được một API cụ thể dùng để chọn rule.
- Một Unicode time-zone type có thể không ánh xạ được tới zone mà runtime hỗ trợ.
- Dữ liệu tên tháng, quy tắc vùng và pattern ngày/giờ có thể phụ thuộc provider.

Vì thế, **đọc lại các thuộc tính thực sự được áp dụng trên formatter**:

~~~java
var formatter = DateTimeFormatter
        .ofLocalizedDateTime(FormatStyle.SHORT)
        .localizedBy(options);

var chronology = formatter.getChronology();
var digits = formatter.getDecimalStyle().getZeroDigit();
var zone = formatter.getZone();
~~~

Không chỉ kiểm tra:

~~~java
options.getUnicodeLocaleType("ca") != null
~~~

Biểu thức trên chỉ chứng minh key được lưu, **không** chứng minh chronology đã được chọn.

Trong hệ thống có ràng buộc mạnh, nên kiểm tra tại cấu hình ứng dụng:

~~~java
if (!"ThaiBuddhist".equals(chronology.getId())) {
    throw new IllegalStateException("Required chronology unavailable");
}
~~~

Đoạn này minh họa chính sách **khi hệ thống yêu cầu cụ thể lịch Buddhist**; nếu chính sách chấp nhận fallback, thay vì ném lỗi hãy dùng một lựa chọn dự phòng rõ ràng và thông báo phù hợp. Không tự giả định tất cả locale đều được hỗ trợ như nhau.

## 14. Các API liên quan và trách nhiệm của mỗi API

| API | Vai trò chính | Key liên quan trong bối cảnh này |
| --- | --- | --- |
| `Locale.forLanguageTag` | Parse language tag/Unicode extensions | Lưu `ca`, `nu`, `rg`, `tz` |
| `Locale.getUnicodeLocaleType` | Đọc type của key | Bất kỳ key Unicode có trong tag |
| `Locale.Builder.setUnicodeLocaleKeyword` | Tạo tag theo cấu trúc | Các key được truyền |
| `DateTimeFormatter.localizedBy` | Áp dụng localization và các override thích hợp | `ca`, `nu`, `rg`, `tz` |
| `DateTimeFormatter.withLocale` | Thay locale dùng cho text/pattern | Không tự áp dụng đầy đủ chronology/zone/decimal style overrides |
| `DateTimeFormatter.withChronology` | Chọn chronology tường minh | Có thể ghi đè kết quả từ `ca` nếu gọi sau |
| `DateTimeFormatter.withDecimalStyle` | Chọn decimal symbols tường minh | Có thể ghi đè kết quả từ `nu` nếu gọi sau |
| `DateTimeFormatter.withZone` | Chọn ZoneId tường minh | Có thể ghi đè kết quả từ `tz` nếu gọi sau |
| `NumberFormat.getNumberInstance(locale)` | Định dạng số theo locale | `nu` và `rg` khi được hỗ trợ |
| `DecimalStyle.of(locale)` | Ký hiệu số cho java.time formatter | `nu` và `rg` khi được hỗ trợ |
| `Currency.getInstance(locale)` | Mã tiền tệ mặc định theo locale | `rg` (và key `cu` nếu có) |
| `WeekFields.of(locale)` | Quy tắc tuần | `rg` (và key `fw` nếu có) |
| `Chronology.ofLocale(locale)` | Tra cứu chronology có hỗ trợ | `ca` khi tương ứng chronology được hỗ trợ |
| `ZoneId.of(...)` | Chọn IANA ZoneId rõ ràng | Không cần Unicode `tz` để dùng |

**Không phải mọi method đều áp dụng mọi key.** JEP 314 liệt kê rõ các API được mở rộng với từng key. Việc dùng một API không được liệt kê không mặc nhiên có nghĩa nó hiểu toàn bộ Unicode locale extensions.

### 14.1. Tập trung vào `java.time` hiện đại

Bài học dùng `java.time` vì mô hình `Instant`, `LocalDate`, `ZoneId`, `Chronology` và `DateTimeFormatter` giúp tách thời điểm, ngày lịch, múi giờ và hiển thị. Các API i18n `java.text` và `java.util.Currency` vẫn có ích ở tình huống tương ứng, nhưng đừng dùng kiểu ngày/giờ cũ chỉ vì một ví dụ lịch sử khi `java.time` đáp ứng yêu cầu hiện tại tốt hơn.

## 15. Thiết kế UI nhiều lựa chọn

Một cấu hình mẫu cho application:

~~~java
record PresentationOptions(
        Locale uiLocale,
        Locale dateTimeLocale,
        ZoneId businessZone,
        Currency transactionCurrency
) {
    PresentationOptions {
        Objects.requireNonNull(uiLocale);
        Objects.requireNonNull(dateTimeLocale);
        Objects.requireNonNull(businessZone);
        Objects.requireNonNull(transactionCurrency);
    }
}
~~~

Đây là **đoạn mã minh họa**, cần import `Locale`, `ZoneId`, `Currency`, `Objects`; đặt nó trong một lớp/nguồn Java riêng theo thiết kế dự án. Vì toàn bộ thành phần ở đây là value-like object thích hợp, record giúp cấu hình dễ kiểm tra hơn; không nên xem record là deep-immutable với mọi kiểu field có thể thêm sau này.

Sử dụng:

~~~java
var prefs = new PresentationOptions(
        Locale.forLanguageTag("vi-VN"),
        Locale.forLanguageTag(
                "en-US-u-ca-buddhist-nu-arab-rg-gbzzzz-tz-uslax"),
        ZoneId.of("Asia/Ho_Chi_Minh"),
        Currency.getInstance("USD")
);
~~~

Bốn field giải quyết **bốn lớp**:

1. `uiLocale=vi-VN` chọn ngôn ngữ tài nguyên UI. Language của formatter cho ngày vẫn có thể là `en`.
2. `dateTimeLocale` chứa các extension biểu diễn ngày/số/vùng/zone theo cấu hình.
3. `businessZone` là múi giờ riêng dùng cho tính toán/lịch hẹn khi doanh nghiệp yêu cầu; nó có thể khác `tz` trong locale.
4. `transactionCurrency` ghi đơn vị tiền thực tế của dữ liệu giao dịch; nó có thể khác currency mặc định gợi ý bởi `rg`.

Một quy tắc rõ ràng cần xác định: **khi presentation locale có `tz` nhưng businessZone có giá trị khác, nguồn nào thắng khi format báo cáo?** Nếu người dùng xem thời gian theo zone locale thì dùng `localizedBy`; nếu ứng dụng bắt buộc zone nghiệp vụ, hãy gọi `withZone(prefs.businessZone())` **sau** `localizedBy`. Điều này tránh một sai lầm tinh vi do thứ tự chaining.

### 15.1. Không tự đổi default `Locale` trong server

Tránh:

~~~java
Locale.setDefault(localeForCurrentUser);
~~~

trên mỗi HTTP request. `Locale.setDefault` ảnh hưởng **toàn JVM**, không phải chỉ một request. Các request chạy song song có thể ảnh hưởng lẫn nhau. Truyền locale/zone trực tiếp vào formatter hoặc lấy từ immutable per-user preferences.

### 15.2. Không dùng một chuỗi locale làm nguồn duy nhất cho mọi thứ

Có thể lưu tag `"en-US-u-ca-buddhist-nu-arab-rg-gbzzzz-tz-uslax"` để ghi nhớ lựa chọn giao diện thời gian. Nhưng về mô hình, time zone giao dịch và currency vẫn cần được lưu rõ theo nhu cầu nghiệp vụ. Một tag i18n không thay thế thiết kế domain data.

## 16. Trường hợp bất đồng bộ, caching và tính bất biến

`Locale`, `DateTimeFormatter` và `ZoneId` có mô hình giá trị phù hợp cho việc chia sẻ khi được tạo xong. Không cần tạo lại formatter trong mọi vòng lặp chỉ để đổi một ký tự; có thể cache theo **đúng key cấu hình**.

Tuy nhiên, key của cache phải phản ánh toàn bộ thông tin làm thay đổi output:

- Language và region của locale cơ sở.
- Extension `ca`, `nu`, `rg` và `tz`.
- Style hoặc pattern của `DateTimeFormatter`.
- Các override `withZone`/`withChronology`/`withDecimalStyle` được áp dụng sau cùng.
- Những chính sách nghiệp vụ khác nếu cần.

**Không cache chung** cho `en-US` và `en-US-u-ca-buddhist-nu-arab-rg-gbzzzz-tz-uslax` chỉ vì `getLanguage()` đều là `en`. Hai formatter có thể cho khác chronology, ký hiệu số, region pattern và time zone.

Nếu JDK/CLDR data thay đổi khi nâng cấp runtime, kết quả trình bày có thể đổi; không giữ các snapshot định dạng trong database như giá trị giao thức nếu yêu cầu hệ thống là có thể tính toán/đọc trở lại ổn định.

## 17. Những bẫy phổ biến khi phối hợp key

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Một locale chỉ chứa được một Unicode key.” | Có thể kết hợp nhiều key sau `-u-`. |
| “Có `ca`, `nu`, `rg`, `tz` thì mọi API Java hiểu cả bốn.” | Mỗi API/provider áp dụng các key phù hợp theo hợp đồng. |
| “`ca=buddhist` tự đổi Instant đang lưu.” | Không; nó thay cách biểu diễn ngày trong chronology được chọn. |
| “Ngày ISO 2026 được chuyển sang Buddhist bằng `date(2026,11,7)`.” | Sai; overload số nguyên hiểu năm trong chronology đích. Chuyển từ cùng `LocalDate`. |
| “`nu=arab` làm giá trị `1234.5` thành số khác.” | Không; nó thay ký hiệu hiển thị, không sửa giá trị toán học. |
| “`rg=gbzzzz` làm `getCountry()` trở thành GB.” | Không; country cơ sở vẫn US. |
| “`rg` chứng minh người dùng ở GB.” | Không; region override là lựa chọn format locale. |
| “`tz=uslax` là một IANA ZoneId có thể đưa thẳng vào `ZoneId.of`.” | Không; Unicode type và IANA ID có cách đặt tên khác. |
| “Locale tự chọn múi giờ chính xác chỉ nhờ country.” | Không; vùng địa lý có thể có nhiều zone. |
| “`withLocale` và `localizedBy` luôn giống nhau.” | Không; `localizedBy` áp dụng chronology/decimal style/zone khi hỗ trợ. |
| “Đặt `withZone(UTC)` trước `localizedBy` là zone cuối không đổi.” | `localizedBy` sau đó có thể áp dụng `tz` và thay zone. |
| “Nếu `rg` tồn tại, `ca` và `nu` đều bị bỏ qua.” | Ngược lại: `ca`/`nu` tường minh ưu tiên trong phần tương ứng so với giá trị ngầm từ `rg`. |
| “Locale.format number trả mã số chuẩn lưu trong JSON.” | Format hiển thị không phải serializer JSON hoặc giá trị số chuẩn. |
| “Tạo Locale có tag hợp cú pháp chắc chắn áp dụng đúng extension.” | Cần kiểm tra service/provider và giá trị hiệu lực. |
| “Muốn UI tiếng Việt thì các format locale phải đều là vi-VN.” | Có thể chọn ngôn ngữ UI và các quy ước format độc lập. |
| “`DateTimeFormatter` bị sửa tại chỗ bởi `localizedBy`.” | Nó bất biến; các method trả formatter khác. |
| “Một Formatter có thể được cache chỉ theo `getLanguage()`.” | Sai khi các extension/region/zone làm thay đổi cách hiển thị. |
| “`tz` thay đổi timezone default toàn JVM.” | Không; nó áp dụng ở những API i18n có hỗ trợ. |
| “Currency lấy từ `rg` đã là đơn vị tiền giao dịch.” | Chỉ là gợi ý/quy ước; dữ liệu nghiệp vụ quyết định currency thực. |

## 18. Bài tập có đáp án

### Bài 1 — Đọc tag phức hợp

~~~java
Locale loc = Locale.forLanguageTag(
        "en-US-u-ca-buddhist-nu-arab-rg-gbzzzz-tz-uslax");
~~~

**Hỏi:** `loc.getLanguage()` và `loc.getCountry()` là gì?

**Đáp án:** `en` và `US`. Bốn Unicode extensions là metadata bổ sung, không tự thay đổi hai trường cơ sở.

### Bài 2 — Đọc key

~~~java
loc.getUnicodeLocaleType("nu")
~~~

**Đáp án:** `"arab"`. Đây là type được lưu, không phải số Ả Rập đã format.

### Bài 3 — Chọn lịch

~~~java
var formatter = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.LONG)
        .localizedBy(loc);
~~~

**Đáp án:** Trên runtime hỗ trợ `ca=buddhist`, `getChronology().getId()` là `ThaiBuddhist`.

### Bài 4 — Chuyển cùng ngày ISO

~~~java
LocalDate iso = LocalDate.of(2026, 11, 7);
var buddhist = formatter.getChronology().date(iso);
~~~

**Đáp án:** Với lịch Thai Buddhist, `buddhist.get(ChronoField.YEAR)` là `2569`. Không dùng `date(2026,11,7)` để biểu diễn “chuyển từ ISO” vì tham số năm đó được diễn giải theo chronology đích.

### Bài 5 — Chữ số

`getDecimalStyle().getZeroDigit()` trả U+0660. Chữ số này từ extension nào?

**Đáp án:** `nu=arab`. Nó ảnh hưởng ký hiệu số ở formatter hỗ trợ, không thay language `en`.

### Bài 6 — Region override

~~~java
Locale loc = Locale.forLanguageTag("en-US-u-rg-gbzzzz");
~~~

**Hỏi:** `loc.getCountry()` có phải `GB` không?

**Đáp án:** Không, vẫn `US`. Nhưng `Currency.getInstance(loc)` có thể chọn GBP dựa `rg` ở runtime hỗ trợ.

### Bài 7 — Priority giữa `ca` và `rg`

Locale gồm cả `ca=buddhist` và `rg=gbzzzz`. Chronology theo cái nào?

**Đáp án:** `DateTimeFormatter.localizedBy` ưu tiên chronology từ `ca` tường minh hơn chronology ngầm từ `rg`.

### Bài 8 — Priority giữa `nu` và `rg`

Locale gồm cả `nu=arab` và `rg=gbzzzz`. Numbering system theo cái nào?

**Đáp án:** `localizedBy` ưu tiên numbering system được chỉ định bởi `nu` trong phần tương ứng; region override vẫn có thể ảnh hưởng các quy tắc vùng khác.

### Bài 9 — Zone

~~~java
Locale loc = Locale.forLanguageTag("en-US-u-tz-uslax");
var f = DateTimeFormatter
        .ofLocalizedDateTime(FormatStyle.SHORT)
        .localizedBy(loc);
~~~

**Đáp án:** Trên JDK thử, `f.getZone()` là `America/Los_Angeles`. Đây là zone của formatter, không thay default JVM time zone.

### Bài 10 — Chaining order

~~~java
var a = template.withZone(ZoneId.of("UTC")).localizedBy(loc);
var b = template.localizedBy(loc).withZone(ZoneId.of("UTC"));
~~~

Với `loc` chứa `tz=uslax`, **đáp án:** `a` có thể có zone Los Angeles, còn `b` có zone UTC do lệnh `withZone` sau cùng.

### Bài 11 — `withLocale`

Cùng một template, tại sao `withLocale(loc)` và `localizedBy(loc)` có thể khác nhau?

**Đáp án:** `withLocale` chủ yếu lưu locale cho text/pattern, còn `localizedBy` còn có thể áp dụng chronology, decimal style và zone từ Unicode extensions. Không coi hai method là alias.

### Bài 12 — Currency

`rg` chọn GBP, nhưng giao dịch lưu `currency="USD"`. Khi thanh toán, có được tự chuyển giá trị số sang GBP không?

**Đáp án:** Không. Currency trong locale là quy ước/gợi ý; chuyển tiền phải dùng quy tắc nghiệp vụ/tỷ giá minh bạch và dữ liệu tiền thực của giao dịch.

### Bài 13 — Giao thức dữ liệu

Một API nhận ISO date, JSON number và UTC instant. Có nên gửi kết quả formatter Buddhist/Arabic numerals làm field máy đọc không?

**Đáp án:** Không, trừ khi giao thức quy định rõ như vậy. Giữ dữ liệu tiêu chuẩn; chỉ dùng extension cho phần hiển thị theo người đọc.

### Bài 14 — Test ở JDK khác

Một test hardcode cả chuỗi tên tháng/tên múi giờ và bị sai khi nâng cấp CLDR. Có thể viết test tốt hơn thế nào?

**Đáp án:** Kiểm tra chronology, `ZoneId`, code point chữ số và các invariant nghiệp vụ thay vì đóng băng mọi chuỗi dịch. Nếu cần snapshot UI chính xác, chạy test trên provider/runtime cố định đã công bố và có chính sách cập nhật ảnh chụp.

### Bài 15 — Dùng sai type `tz`

Đưa `en-US-u-tz-America/Los_Angeles` vào `Locale.forLanguageTag` và kỳ vọng có zone LA. Vì sao sai?

**Đáp án:** Unicode locale type không phải cú pháp IANA ZoneId. Dùng type đã được quy định như `uslax` hoặc giữ `ZoneId.of("America/Los_Angeles")` như cấu hình riêng.

### Bài 16 — Parse nhưng provider không áp dụng

`getUnicodeLocaleType("ca")` trả giá trị mong đợi, nhưng formatter không có chronology mong đợi. Vì sao?

**Đáp án:** Parse tag và runtime support là hai tầng khác nhau. Kiểm tra Javadoc, `Chronology` được hỗ trợ, loại formatter, locale provider và fallback. Không giả định việc lưu type buộc mọi formatter phải áp dụng.

## 19. Checklist code review

- [ ] Language tag có cú pháp BCP 47 hợp lệ và có `-u-` khi dùng Unicode keys không?
- [ ] Đã phân biệt language/region cơ sở với `rg` region override chưa?
- [ ] `ca` có tương ứng một chronology được JDK hỗ trợ không?
- [ ] Nếu chuyển ngày ISO sang calendar khác, có dùng đúng API chuyển cùng ngày thay vì nhập lại năm cũ không?
- [ ] `nu` có tác động đến formatter thực sự dùng để hiển thị số/ngày chưa?
- [ ] Có kiểm tra ký hiệu chữ số bằng `DecimalStyle`/code point thay vì chỉ nhìn font không?
- [ ] `rg` có được dùng như quy tắc vùng, không như quốc gia xác thực hoặc dữ liệu thuế không?
- [ ] `tz` có đúng Unicode time-zone type, không nhầm với IANA ID không?
- [ ] Có phân biệt zone định dạng với múi giờ nghiệp vụ của một timestamp không?
- [ ] Có dùng `localizedBy` khi cần áp dụng ca/nu/rg/tz, không chỉ `withLocale` không?
- [ ] Có xác định thứ tự `localizedBy` với `withZone`, `withChronology` và `withDecimalStyle` không?
- [ ] Nếu cả `ca` và `rg` có mặt, đã áp dụng precedence của `ca` theo Javadoc chưa?
- [ ] Nếu cả `nu` và `rg` có mặt, đã áp dụng precedence của `nu` theo Javadoc chưa?
- [ ] Có kiểm tra các values hiệu lực `getChronology`, `getDecimalStyle`, `getZone` không?
- [ ] Có kiểm tra runtime locale provider/CLDR support và fallback khi không được hỗ trợ không?
- [ ] Có tránh `Locale.setDefault` mỗi HTTP request không?
- [ ] Có giữ các dữ liệu giao dịch như currency, số tiền, Instant và business ZoneId riêng không?
- [ ] Có tránh localized number/date text trong các field API máy-máy yêu cầu định dạng chuẩn không?
- [ ] Có không dùng locale làm bằng chứng vị trí địa lý, quốc tịch hoặc quyền truy cập không?
- [ ] Có test kết hợp bốn key trên cùng một Locale, không chỉ test từng key riêng không?
- [ ] Có lưu đúng key của cache formatter theo toàn bộ Locale/zone/chronology không?
- [ ] Có test một Instant ở hai zone và một LocalDate ở hai chronology để tránh nhầm về chuyển đổi không?

## 20. Tài liệu chính thức vẫn áp dụng

- [JEP 314 — Additional Unicode Language-Tag Extensions (Java 10)](https://openjdk.org/jeps/314): tài liệu gốc về việc mở rộng `cu`, `fw`, `rg`, `tz` và danh sách API chịu ảnh hưởng. `ca`/`nu` đã được hỗ trợ từ trước.
- [Java SE 25 API — `DateTimeFormatter`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeFormatter.html): chi tiết `localizedBy(Locale)` (Since: 10), `withLocale`, ưu tiên `ca/nu` với `rg`, chronology, decimal style và zone.
- [Java SE 17 API — `DateTimeFormatter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html): xác nhận API dùng được với `--release 17`, gồm `localizedBy`.
- [Java SE API — `Locale`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Locale.html): BCP 47/Unicode locale extensions, `getUnicodeLocaleType`, `forLanguageTag` và `Locale.Builder`.
- [Java SE API — `NumberFormat`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/NumberFormat.html): support `nu`/`rg`, giới hạn theo locale provider.
- [Java SE API — `DecimalStyle`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DecimalStyle.html): ký hiệu chữ số phù hợp locale/number system.
- [Java SE API — `Chronology`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/chrono/Chronology.html): calendar systems, `ofLocale` và chuyển đổi ngày.
- [Java SE API — `ThaiBuddhistChronology`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/chrono/ThaiBuddhistChronology.html): hệ lịch Buddhist và cách biểu diễn năm.
- [Java SE API — `WeekFields`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/temporal/WeekFields.html): quy tắc tuần và region override.
- [Java SE API — `Currency`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Currency.html): tác động của region override đối với currency default khi được hỗ trợ.
- [Java SE API — `ZoneId`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/ZoneId.html): IANA time zone và cách sử dụng rõ ràng trong xử lý thời điểm.
- [Unicode LDML / UTS #35](https://unicode.org/reports/tr35/): định nghĩa các Unicode locale key/type và cách ứng dụng quốc tế hóa diễn giải chúng.
- [BCP 47 — RFC 5646](https://www.rfc-editor.org/rfc/rfc5646.html): quy tắc language tag.

**Tổng kết:** Có thể phối hợp `ca=buddhist`, `nu=arab`, `rg=gbzzzz` và `tz=uslax` trong cùng một BCP 47 `Locale`. Java 10 bổ sung `DateTimeFormatter.localizedBy(locale)` và hỗ trợ thêm các extension liên quan để formatter áp dụng chronology, chữ số, vùng quy ước và zone khi phù hợp. **`ca` và `nu` tường minh được ưu tiên** trong phần tương ứng trước giá trị ngầm từ `rg`. **Thứ tự gọi `localizedBy` và `withZone/withChronology` quan trọng**. Locale dùng cho presentation không thay thế các dữ liệu nghiệp vụ như Instant, ZoneId, mã tiền tệ hoặc địa chỉ thực.
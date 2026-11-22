# Java 10 – Locale trong ứng dụng: Ảnh hưởng đến chronology, DecimalStyle và ZoneId

> **Phạm vi:** Java 10 → **Locale trong ứng dụng** → **Ảnh hưởng đến chronology, DecimalStyle và ZoneId**. Trọng tâm là `DateTimeFormatter.localizedBy(Locale)`, bổ sung từ Java 10, và cách các Unicode locale extensions `ca` (calendar), `nu` (numbering system), `rg` (region override), `tz` (time zone) tác động đến bộ định dạng ngày giờ. Nội dung chỉ bao gồm kiến thức còn áp dụng trên Java 17+ và các JDK hiện đại. Chương trình cuối bài đã được biên dịch bằng `javac --release 17` và chạy kiểm chứng.

## 1. Mục tiêu và kết luận cốt lõi

Sau bài học, bạn có thể:

1. Phân biệt bốn khía cạnh **Locale, Chronology, DecimalStyle, ZoneId** trong xử lý ngày giờ.
2. Hiểu rõ `DateTimeFormatter.withLocale(locale)` khác `DateTimeFormatter.localizedBy(locale)` từ Java 10 như thế nào.
3. Dùng Unicode locale extension `ca` để chọn hệ lịch như Japanese/Thai Buddhist, và hiểu khi nào vẫn nên lưu dữ liệu theo ISO.
4. Dùng `nu` để chọn hệ chữ số (Latin, Thai, Arabic-Indic) thông qua `DecimalStyle`, không nhầm với định dạng tiền tệ/số thập phân của `NumberFormat`.
5. Dùng `tz` như gợi ý múi giờ cho formatter; phân biệt mã Unicode ngắn như `usnyc` với ID IANA `America/New_York`.
6. Hiểu `rg` ảnh hưởng quy tắc theo vùng và cách `ca`/`nu` có ưu tiên đối với phần cùng loại.
7. Biết vì sao thứ tự gọi `localizedBy` và `withChronology`/`withDecimalStyle`/`withZone` có thể làm thay đổi kết quả.
8. Giải thích việc định dạng `Instant` dưới một `ZoneId` khác không làm thay đổi chính `Instant`; và `Locale` không tự đặt múi giờ của hệ thống.
9. Dùng `Chronology.ofLocale`, `DecimalStyle.of`, `DateTimeFormatter.getChronology()`, `getDecimalStyle()`, `getZone()` để kiểm tra hiệu lực.
10. Quản lý input locale không tin cậy, lỗi calendar chưa được hỗ trợ, và các phụ thuộc dữ liệu CLDR/tzdb.
11. Thiết kế API cho nhiều user/tenant bằng formatter immutable, locale tường minh, múi giờ tường minh và kiểm thử đúng hợp đồng.
12. Chạy ví dụ Java 17+ có output xác định cho những hành vi quan trọng.

**Thông điệp chính:** `Locale` là tập lựa chọn ngôn ngữ/vùng và các tùy chọn mở rộng, còn **Chronology, DecimalStyle và ZoneId là các thành phần vận hành độc lập**. Chỉ lưu `Locale` trong formatter bằng `withLocale` **không** đồng nghĩa đã áp các override `ca`/`nu`/`tz`. Nếu muốn những lựa chọn đó tham gia vào trạng thái formatter, dùng **`localizedBy(locale)`** hoặc các method `withChronology`, `withDecimalStyle`, `withZone` một cách tường minh.

## 2. Bốn thành phần khác nhau, không nên đánh đồng

| Thành phần | Vai trò | Ví dụ / API |
| --- | --- | --- |
| `Locale` | Ngôn ngữ, vùng và Unicode locale keywords dùng để địa phương hóa cách hiển thị | `Locale.forLanguageTag("en-US-u-ca-japanese")` |
| `Chronology` | Hệ lịch dùng để diễn giải/hiển thị năm, tháng, ngày và era | `IsoChronology`, `JapaneseChronology`, `ThaiBuddhistChronology` |
| `DecimalStyle` | Bộ ký hiệu chữ số 0–9, dấu dương/âm và dấu thập phân cho **date/time formatting** | `DecimalStyle.of(locale).getZeroDigit()` |
| `ZoneId` | Quy tắc múi giờ khi chuyển `Instant` sang ngày giờ địa phương | `ZoneId.of("America/New_York")` |

Một date-time formatter có các trạng thái liên quan:

~~~java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm VV", Locale.US);

Locale locale = formatter.getLocale();
Chronology chronology = formatter.getChronology(); // Có thể null
DecimalStyle decimalStyle = formatter.getDecimalStyle();
ZoneId zone = formatter.getZone();                  // Có thể null
~~~

Đây là **đoạn minh họa trong phương thức đã import các class tương ứng**, không phải chương trình độc lập. Với formatter `ofPattern` thông thường, `getChronology()` và `getZone()` có thể là `null` vì không có **override**. Điều đó **không có nghĩa** một `LocalDate` truyền vào thiếu chronology; bản thân LocalDate có hệ lịch ISO.

**Phân biệt quan trọng:**

- Đổi **ngôn ngữ hiển thị**: tên tháng/ngày, localized pattern, era name có thể thay.
- Đổi **chronology**: cách biểu diễn era/năm và diễn giải ngày có thể thay.
- Đổi **decimal style**: hình dạng các chữ số trong kết quả date/time có thể thay.
- Đổi **zone**: cùng một instant có thể hiện thành ngày/giờ và đôi khi **ngày** khác.

Bốn thay đổi này liên quan nhưng **không đồng nghĩa**. Một user có thể muốn giao diện tiếng Anh, chữ số Thai, Japanese calendar và múi giờ New York. `Locale` với nhiều extension có thể diễn đạt một phần sở thích; ứng dụng vẫn phải thiết kế hợp đồng dữ liệu tường minh.

## 3. Cú pháp Unicode locale extensions liên quan

BCP 47 hỗ trợ phần `-u-` để thêm các Unicode locale key/type. Ví dụ:

~~~text
en-US-u-ca-japanese-nu-thai-tz-usnyc
│  │  │ │        │  │    │  └── usnyc: Unicode time-zone type
│  │  │ │        │  │    └───── tz: time-zone preference
│  │  │ │        │  └────────── thai: numbering system
│  │  │ │        └───────────── nu: numbering-system key
│  │  │ └────────────────────── japanese: calendar type
│  │  └──────────────────────── ca: calendar key
│  └─────────────────────────── u: Unicode locale extension
└────────────────────────────── en-US: ngôn ngữ và vùng cơ sở
~~~

Mỗi key có nghĩa khác nhau:

| Key | Ví dụ | Ảnh hưởng chính |
| --- | --- | --- |
| `ca` | `ca-japanese` | Chọn chronology khi được API hỗ trợ |
| `nu` | `nu-thai`, `nu-arab`, `nu-latn` | Hệ chữ số/ký hiệu số |
| `rg` | `rg-gbzzzz` | Ghi đè vùng dùng trong một số quy tắc locale |
| `tz` | `tz-usnyc` | Ánh xạ vùng múi giờ cho formatter hỗ trợ |
| `fw` | `fw-mon` | Ngày đầu tuần; thuộc phạm vi `WeekFields`, không trực tiếp thay ba override đang xét |

Với Java:

~~~java
var locale = Locale.forLanguageTag(
        "en-US-u-ca-japanese-nu-thai-tz-usnyc");

System.out.println(locale.getUnicodeLocaleType("ca")); // japanese
System.out.println(locale.getUnicodeLocaleType("nu")); // thai
System.out.println(locale.getUnicodeLocaleType("tz")); // usnyc
~~~

Mã `tz-usnyc` **không phải** cùng cú pháp với `ZoneId.of("America/New_York")`. Java thực hiện ánh xạ Unicode time-zone type sang một ZoneId được nhận diện khi API liên quan yêu cầu. Không ghép/đổi chuỗi bằng cách tự suy đoán tên IANA time zone.

### 3.1. Java 10 thực sự bổ sung gì?

Các khóa Unicode `ca` và `nu` đã có hỗ trợ trước Java 10 trong những phần Java liên quan. Java 10 bổ sung mức hỗ trợ của các khóa như `cu`, `fw`, `rg` và `tz`, đồng thời bổ sung **`DateTimeFormatter.localizedBy(Locale)`** để lấy cả các giá trị locale calendar/region/decimal style/time-zone vào formatter.

Vì vậy, trọng tâm của bài không phải “Java 10 tạo ra Chronology hoặc ZoneId”, mà là **Java 10 làm cho việc áp những lựa chọn Locale lên formatter rõ ràng hơn**. Các API `java.time` này vẫn được dùng và duy trì trên JDK hiện đại.

## 4. `withLocale(locale)` khác `localizedBy(locale)`

Đây là sự khác biệt dễ bị bỏ sót nhất.

~~~java
var locale = Locale.forLanguageTag(
        "en-US-u-ca-japanese-nu-thai-tz-usnyc");

var base = DateTimeFormatter.ofPattern(
        "uuuu-MM-dd HH:mm VV", Locale.US);

var textOnly = base.withLocale(locale);
var fullyLocalized = base.localizedBy(locale);
~~~

### 4.1. `withLocale` làm gì?

`withLocale(locale)` trả **formatter mới** với locale dùng để tra cứu những phần cần địa phương hóa như tên tháng, tên thứ, era text hoặc localized pattern. Theo Javadoc, Locale được giữ theo cách truyền vào, **không xử lý thêm để tự cài đặt override chronology/timezone/decimal style từ Unicode extensions**. Những extension có thể vẫn được dùng **về sau trong xử lý văn bản** tùy API.

Với `base` ở trên, trên JDK đã kiểm thử:

~~~text
withLocale-chronology=none
withLocale-zero=U+0030
withLocale-zone=none
~~~

Ở đây `none` nghĩa là `getChronology()` hoặc `getZone()` trả `null`, chứ không phải formatter không thể hiển thị bất kỳ ngày nào. `U+0030` là ký tự `'0'` ASCII.

### 4.2. `localizedBy` làm gì?

`localizedBy(locale)` có từ **Java 10**; Javadoc mô tả nó trả formatter mới với các giá trị địa phương hóa của locale, calendar, region, decimal style và/hoặc time-zone, có thể **ghi đè giá trị đã nằm trong formatter**.

Với Locale kết hợp cùng lúc `ca-japanese`, `nu-thai` và `tz-usnyc`:

~~~text
localized-chronology=Japanese
localized-zero=U+0E50
localized-zone=America/New_York
~~~

- `ca-japanese` → chronology là `JapaneseChronology`.
- `nu-thai` → số 0 của `DecimalStyle` là Thai digit zero `U+0E50`.
- `tz-usnyc` → múi giờ từ Unicode type được ánh xạ thành `America/New_York`.

**Cả hai phương thức đều trả formatter mới và không sửa formatter ban đầu** vì `DateTimeFormatter` immutable và thread-safe theo API.

### 4.3. Bảng so sánh chọn method

| Nhu cầu | `withLocale` | `localizedBy` |
| --- | --- | --- |
| Chỉ chọn tên tháng/thứ và localized pattern | Phù hợp | Phù hợp, nhưng còn có thể áp override khác |
| Muốn `ca` điều khiển chronology | Không tự cài override | **Có thể áp** |
| Muốn `nu` điều khiển DecimalStyle | Không tự cài override | **Có thể áp** |
| Muốn `tz` điều khiển ZoneId | Không tự cài override | **Có thể áp** |
| Muốn giữ nguyên explicit `withZone(UTC)` đang có | Tránh tự ghi đè zone | Cần kiểm tra thứ tự gọi vì có thể thay |
| Cần kiểm soát chronology/zone theo luật nghiệp vụ | Dùng thêm các `withXxx` cụ thể | Có thể localizedBy rồi chốt lại withXxx |
| Tính bất biến/thread safety của formatter | Có | Có |

Không có quy tắc “luôn dùng localizedBy bất kể ngữ cảnh”. Nếu ứng dụng cần giữ timezone do user chọn ở profile riêng hoặc giữ chronology ISO trong dữ liệu kỹ thuật, thứ tự và kiểu override phải được quyết định có chủ đích.

## 5. `ca` ảnh hưởng đến `Chronology` ra sao?

`java.time.chrono.Chronology` biểu diễn **hệ lịch**; các implementation được hỗ trợ trong Java tiêu chuẩn gồm ISO, Japanese, Thai Buddhist, Minguo và Hijrah (tùy type cụ thể).

Lấy chronology trực tiếp từ Locale:

~~~java
import java.time.chrono.Chronology;
import java.util.Locale;

var iso = Chronology.ofLocale(Locale.forLanguageTag("en-US"));
var japanese = Chronology.ofLocale(
        Locale.forLanguageTag("en-US-u-ca-japanese"));
var buddhist = Chronology.ofLocale(
        Locale.forLanguageTag("th-TH-u-ca-buddhist"));
~~~

Trên JDK đã kiểm thử:

~~~text
ofLocale-th-TH=ISO
ofLocale-japanese=Japanese
ofLocale-buddhist=ThaiBuddhist
~~~

Điểm cần nhấn mạnh:

- `Chronology.ofLocale` thường trả `IsoChronology` nếu không có Unicode keyword `ca`.
- `th-TH` **không tự yêu cầu** Thai Buddhist Chronology; muốn nó, hãy dùng `th-TH-u-ca-buddhist`.
- `ca-japanese` chọn Japanese Chronology nhưng **không làm thay đổi `Instant`** hoặc lưu trữ ISO epoch day.
- Chọn chronology khác có thể ảnh hưởng cách biểu diễn era/năm khi format hoặc cách diễn giải date fields khi parse.
- Nếu type calendar đã chỉ định không được Java runtime hỗ trợ, `Chronology.ofLocale` có thể ném `DateTimeException`; không tự nghĩ mọi giá trị CLDR đều có implementation `java.time.chrono` trong JDK.

### 5.1. Ví dụ Nhật Bản: một ngày, một cách ghi era khác

~~~java
var date = java.time.LocalDate.of(2024, 1, 2);
var jpLocale = Locale.forLanguageTag("en-US-u-ca-japanese");

var fmt = java.time.format.DateTimeFormatter
        .ofPattern("G y", Locale.US)
        .localizedBy(jpLocale);

System.out.println(fmt.format(date)); // Reiwa 6 trên JDK đã thử
~~~

`G` là era, `y` là **year-of-era**. Đừng dùng `uuuu` và mặc định rằng nó biểu diễn “năm thứ sáu của Reiwa”; `uuuu` có ngữ nghĩa proleptic year, khác `y`. Sự khác nhau quan trọng khi ứng dụng dùng Nhật lịch, Thai Buddhist date, v.v.

**Tính đúng đắn của domain:** Một người chọn lịch hiển thị Nhật Bản **không có nghĩa** tất cả timestamp trong database cần đổi cách lưu. Java khuyến nghị dùng ISO date-time cho các lớp nghiệp vụ phổ biến, sau đó chuyển/format sang chronology thích hợp ở ranh giới hiển thị hoặc interop có hợp đồng rõ.

### 5.2. Chronology và parsing

Khi formatter có override chronology:

- Trong lúc format, date có thể được chuyển sang chronology override.
- Trong lúc parse, các trường ngày có thể được diễn giải theo chronology override nếu văn bản không chứa chronology riêng được parse trực tiếp và các quy tắc resolve áp dụng.
- Cần xử lý era/năm trong pattern cho đúng, nhất là hệ lịch có nhiều era.
- Không giả định mọi chuỗi ngày theo một chronology sẽ parse an toàn thành ISO `LocalDate` mà không kiểm tra ý nghĩa và giới hạn.

Nếu cần làm việc thực sự với ngày của một hệ lịch không phải ISO, xem `ChronoLocalDate` và class date cụ thể; nếu chỉ hiển thị ngày ISO theo sở thích user, thường giữ `LocalDate` và dùng formatter với chronology override là phù hợp hơn.

### 5.3. Calendar type không hợp lệ hoặc không hỗ trợ

~~~java
try {
    Chronology.ofLocale(
            Locale.forLanguageTag("en-US-u-ca-xyz"));
} catch (java.time.DateTimeException expected) {
    System.out.println("unknown-calendar=rejected");
}
~~~

Tạo một `Locale` bằng `forLanguageTag` **không chứng minh** mọi Unicode keyword type của nó có thực thể tương ứng trong Java. Khi nhận input từ API/user profile, validate calendar choices theo allowlist và xử lý `DateTimeException` ở boundary.

## 6. `nu` ảnh hưởng `DecimalStyle` ra sao?

`java.time.format.DecimalStyle` là **bộ ký hiệu số dành cho date/time formatting và parsing**, không phải tất cả luật về số trong ứng dụng.

Các thuộc tính tiêu biểu:

- `getZeroDigit()`: ký tự đại diện số 0; các số 1–9 suy ra từ bộ chữ số được dùng.
- `getPositiveSign()` và `getNegativeSign()`: dấu dương/âm.
- `getDecimalSeparator()`: ký hiệu dấu thập phân cho những thành phần date-time liên quan.
- Các phương thức `withZeroDigit(...)`, `withPositiveSign(...)`, `withNegativeSign(...)`, `withDecimalSeparator(...)` cho phép tạo style mới; `DecimalStyle` immutable và thread-safe.

### 6.1. Ví dụ `nu-thai`, `nu-latn`, `nu-arab`

~~~java
var thai = java.time.format.DecimalStyle.of(
        Locale.forLanguageTag("en-US-u-nu-thai"));
var latin = java.time.format.DecimalStyle.of(
        Locale.forLanguageTag("en-US-u-nu-latn"));
var arabic = java.time.format.DecimalStyle.of(
        Locale.forLanguageTag("en-US-u-nu-arab"));
~~~

Trong JDK đã kiểm thử:

| Locale numbering key | Ký tự zero | Code point |
| --- | --- | --- |
| `nu-thai` | Thai digit zero `๐` | `U+0E50` |
| `nu-latn` | ASCII zero `0` | `U+0030` |
| `nu-arab` | Arabic-Indic digit zero `٠` | `U+0660` |

Dữ liệu locale có thể được nâng cấp cùng JDK/provider. Với explicit, phổ biến và được hỗ trợ như các mã trên, behavior này đáng tin hơn suy ra chữ số mặc định chỉ từ tên ngôn ngữ.

### 6.2. Khác biệt trong `DateTimeFormatter`

~~~java
var locale = Locale.forLanguageTag("en-US-u-nu-thai");
var date = java.time.LocalDate.of(2024, 1, 2);
var base = java.time.format.DateTimeFormatter.ofPattern(
        "uuuu-MM-dd", Locale.US);

var textOnly = base.withLocale(locale);
var localized = base.localizedBy(locale);

System.out.println(textOnly.format(date)); // 2024-01-02
// localized.format(date) sử dụng chữ số Thai cho những numeric fields
~~~

Ở đây `withLocale` không tự thay `DecimalStyle`, nên các numeric fields trong formatter trên vẫn dùng ký hiệu số của style cũ. `localizedBy` lấy numbering system có từ `nu` vào formatter. Trong ví dụ chính, chương trình dùng so sánh String chứa các Unicode escape để in `localized-thai-digits=true` mà không phụ thuộc cách console hiển thị chữ số Thai.

### 6.3. `DecimalStyle` không thay thế `NumberFormat`

Khi cần định dạng **tiền tệ, phân nhóm hàng nghìn, phần trăm, số thập phân theo locale**, thường dùng `java.text.NumberFormat` hoặc một thư viện số chuyên biệt, không dùng `DecimalStyle` của `DateTimeFormatter` như bộ format tài chính.

`DecimalStyle.getDecimalSeparator()` chỉ là ký hiệu được datetime formatter dùng theo các trường phù hợp; nó **không** tự quy định grouping, rounding mode cho tiền tệ hay cách viết `NaN`. Đây là hai phạm vi API khác nhau.

### 6.4. Parse phải thống nhất kiểu chữ số

Một formatter được cấu hình để format bằng Thai digits có thể cần cùng `DecimalStyle` để parse input dùng Thai digits. Không định dạng một kiểu rồi parse với style khác mà không thiết kế rõ. Với dữ liệu máy-máy, thông thường nên giữ dạng ISO/ASCII cố định và chỉ dùng local digits ở UI.

## 7. `tz` ảnh hưởng đến `ZoneId` của formatter

`tz` là Unicode time-zone extension. Ví dụ `en-US-u-tz-usnyc` dùng type `usnyc`, được JDK đã kiểm thử ánh xạ sang `America/New_York` khi `DateTimeFormatter.localizedBy` xử lý.

~~~java
var nyLocale = Locale.forLanguageTag("en-US-u-tz-usnyc");
var fmt = java.time.format.DateTimeFormatter
        .ofPattern("uuuu-MM-dd HH:mm VV", Locale.US)
        .localizedBy(nyLocale);

System.out.println(fmt.getZone()); // America/New_York
~~~

**Phân biệt:**

- `tz-usnyc`: Unicode locale type trong BCP 47 tag.
- `America/New_York`: ZoneId chuẩn IANA/tzdb do Java sử dụng.
- `ZoneId.of("UTC")`: ZoneId tường minh.
- `ZoneId.systemDefault()`: zone mặc định của JVM/OS hoặc cấu hình runtime; tạo một Locale có `tz` **không tự thay đổi** giá trị global này.

`Locale` không có API công khai đơn giản kiểu `locale.getZoneId()` bảo đảm ánh xạ mọi mã `tz`. Khi cần ZoneId cho lịch tác vụ, điều khiển giao dịch hoặc chuyển Instant, hãy ưu tiên lưu **ZoneId tường minh** trong user profile và dùng `ZoneId.of(id)`. `tz` hữu ích khi tiêu chuẩn giao tiếp/trình bày ngày giờ của ứng dụng dựa trên Unicode locale extensions.

### 7.1. Cùng `Instant`, ngày giờ hiển thị khác nhau

~~~java
var instant = java.time.Instant.parse("2024-01-01T00:00:00Z");

var fmt = java.time.format.DateTimeFormatter
        .ofPattern("uuuu-MM-dd HH:mm VV", Locale.US);

System.out.println(fmt.localizedBy(
        Locale.forLanguageTag("en-US-u-tz-usnyc"))
        .format(instant));
// 2023-12-31 19:00 America/New_York

System.out.println(fmt.withZone(java.time.ZoneId.of("UTC"))
        .format(instant));
// 2024-01-01 00:00 UTC
~~~

Cả hai kết quả biểu diễn **cùng một instant**. New York chậm hơn UTC năm giờ tại thời điểm ví dụ (1/1/2024), nên local date tại New York vẫn là 31/12/2023. Chuyển múi giờ khi hiển thị không sửa `Instant` ban đầu.

Nếu input là `LocalDateTime` **không có timezone/offset**, việc áp `withZone` không tương đương “biết chắc instant gốc” nếu không có quy tắc diễn giải local time và DST. Khi chuyển local date-time thành instant, cần zone và chiến lược giải quyết overlap/gap DST ở nghiệp vụ.

### 7.2. Không có zone thì format Instant với pattern ngày/giờ có thể lỗi

~~~java
var fmt = DateTimeFormatter.ofPattern(
        "uuuu-MM-dd HH:mm VV", Locale.US);

// fmt.format(Instant.now());
// Có thể ném UnsupportedTemporalTypeException vì Instant không chứa
// trực tiếp các calendar fields/zone mà pattern đòi hỏi.
~~~

Phương án đúng:

~~~java
var display = fmt.withZone(ZoneId.of("UTC"));
String text = display.format(java.time.Instant.parse(
        "2024-01-01T00:00:00Z"));
~~~

`localizedBy` với `tz` phù hợp cũng có thể gắn zone cho formatter. Tuy nhiên **không nên dựa vào zone ngẫu nhiên từ input không đáng tin** khi ứng dụng phải bảo đảm timezone của báo cáo, hóa đơn, sự kiện hoặc tác vụ định kỳ.

### 7.3. Mã `tz` và DST

Không tự coi một time zone là một offset cố định. `America/New_York` có các quy tắc offset khác nhau tùy thời gian do daylight-saving time và dữ liệu tzdb. Dùng `ZoneId`/`ZoneRules`; không tự gán “New York luôn là UTC-5”.

Khi lịch tác vụ theo local time, một giờ có thể lặp hoặc không tồn tại khi chuyển DST. `Locale` và `tz` chỉ là cách chọn zone; chính sách xử lý gap/overlap phải được định nghĩa riêng.

## 8. `rg`: region override và quan hệ ưu tiên với `ca`/`nu`

Unicode keyword `rg` cho phép gợi ý region dùng trong một số quy tắc địa phương hóa mà không sửa language/region gốc của Locale. Ví dụ:

~~~java
var locale = Locale.forLanguageTag(
        "en-US-u-rg-gbzzzz");
~~~

Trong `DateTimeFormatter.localizedBy`:

- `rg` có thể ảnh hưởng các giá trị locale dựa trên vùng, trong đó có calendar hoặc numbering rules mặc định.
- Nếu có cả `ca` và `rg`, **`ca` có ưu tiên đối với chronology** so với giá trị ngầm suy ra từ `rg`.
- Nếu có cả `nu` và `rg`, **`nu` có ưu tiên đối với numbering system/DecimalStyle** so với giá trị ngầm suy ra từ `rg`.
- `rg` không có nghĩa nó ghi đè timezone `tz` đã chọn; chúng là các lựa chọn khác nhau.
- Vì dữ liệu locale do CLDR/provider cung cấp có thể thay đổi, tránh viết test bắt buộc mọi vùng luôn có chính xác một style mặc định trừ khi business đã cố định điều đó.

**Ví dụ về ý nghĩa:** Một ứng dụng giao diện tiếng Anh vùng US với `rg-gbzzzz` có thể yêu cầu một số quy tắc theo GB, nhưng người dùng đồng thời có thể dùng `ca-japanese` và `nu-thai`; hai override explicit này có ưu tiên trong chính phạm vi của chúng.

Không có lý do để xây một bảng hard-code `if (locale.getCountry().equals("TH")) ...` rồi bỏ qua `ca`/`nu`/`rg`. Với date-time formatting, ưu tiên các factory/formatter chuyên biệt của JDK theo hợp đồng công khai.

## 9. Thứ tự chaining: `localizedBy` có thể ghi đè `withXxx`

Javadoc Java 17 nói rõ: **khác `withLocale`**, kết quả của `localizedBy` có thể phụ thuộc thứ tự gọi cùng các method `withXxx`.

### 9.1. Múi giờ: phương thức gọi sau quyết định override cuối

~~~java
var base = DateTimeFormatter.ofPattern(
        "uuuu-MM-dd HH:mm VV", Locale.US);
var nyLocale = Locale.forLanguageTag("en-US-u-tz-usnyc");

var a = base.withZone(ZoneId.of("UTC"))
            .localizedBy(nyLocale);
var b = base.localizedBy(nyLocale)
            .withZone(ZoneId.of("UTC"));

System.out.println(a.getZone()); // America/New_York
System.out.println(b.getZone()); // UTC
~~~

Ở `a`, `localizedBy` xử lý `tz` sau và thay zone cũ. Ở `b`, `withZone(UTC)` chạy cuối nên **UTC thắng**. Nếu ứng dụng có rule “hóa đơn luôn hiển thị UTC”, hãy đặt explicit `withZone(UTC)` **sau** bước tùy biến locale.

### 9.2. Chronology: `ca` và `withChronology`

~~~java
var japanese = Locale.forLanguageTag("en-US-u-ca-japanese");
var base = DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.US);

var a = base.withChronology(IsoChronology.INSTANCE)
            .localizedBy(japanese);
var b = base.localizedBy(japanese)
            .withChronology(IsoChronology.INSTANCE);

System.out.println(a.getChronology().getId()); // Japanese
System.out.println(b.getChronology().getId()); // ISO
~~~

Nếu business yêu cầu tính/lưu ngày theo ISO, bạn có thể cho locale quyết định tên tháng/ngày nhưng chủ động chốt `IsoChronology.INSTANCE` bằng `withChronology` ở cuối hoặc sử dụng `withLocale` khi không muốn auto-derive chronology.

### 9.3. DecimalStyle: `nu` và `withDecimalStyle`

~~~java
var thai = Locale.forLanguageTag("en-US-u-nu-thai");
var base = DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.US);

var a = base.withDecimalStyle(DecimalStyle.STANDARD)
            .localizedBy(thai);
var b = base.localizedBy(thai)
            .withDecimalStyle(DecimalStyle.STANDARD);
~~~

- `a.getDecimalStyle().getZeroDigit()` → `U+0E50` (Thai digit zero) trên JDK thử.
- `b.getDecimalStyle().getZeroDigit()` → `U+0030` (ASCII zero).

**Quy tắc vận hành dễ nhớ:** Nếu muốn để **locale** ưu tiên, gọi `localizedBy(locale)` ở cuối chuỗi tùy biến; nếu muốn **chính sách ứng dụng** ưu tiên, gọi `localizedBy(locale)` trước rồi chốt các `withChronology/withDecimalStyle/withZone` mong muốn ở cuối. Tuy nhiên cần kiểm tra mọi override có liên quan, không chỉ một.

## 10. `LocalDate`, `LocalDateTime`, `Instant` và hệ lịch

Làm rõ bốn loại dữ liệu giúp tránh việc “đổi locale” làm hỏng nghiệp vụ.

| Kiểu | Bản chất | Điều cần lưu ý |
| --- | --- | --- |
| `LocalDate` | Ngày ISO không kèm múi giờ | Format với chronology khác có thể đổi cách hiển thị era/năm; object không bị biến đổi |
| `LocalDateTime` | Ngày giờ địa phương, không có offset/zone | Không biết chắc Instant cho đến khi chọn ZoneId và xử lý quy tắc zone |
| `Instant` | Một thời điểm trên UTC time-line | Chuyển sang zone mới để hiển thị, không sửa thời điểm |
| `ZonedDateTime` | Date-time + ZoneId và offset theo quy tắc zone | `withZoneSameInstant` giữ nguyên instant; `withZoneSameLocal` có ngữ nghĩa khác |
| `ChronoLocalDate` | Ngày thuộc một chronology cụ thể | Cần dùng thận trọng với domain và calendar conversion |

Một người dùng có thể yêu cầu Japanese calendar nhưng hệ thống vẫn lưu `Instant` và ISO `LocalDate` trong các API nội bộ. Điều này giảm rủi ro khi cộng ngày, so sánh và trao đổi liên dịch vụ. Chuyển sang chronology địa phương khi hiển thị là lớp **representation**; khi domain thật sự dùng calendar khác, cần thiết kế loại dữ liệu và phép toán riêng.

### 10.1. Khi phải lưu ngày giờ cho sự kiện

- Với sự kiện đã xảy ra, nên lưu `Instant` hoặc timestamp có offset/zone theo schema rõ.
- Với “hẹn 09:00 theo giờ địa phương vào thứ Hai”, cần timezone `ZoneId` và quy tắc local scheduling; một Instant cố định hiện tại không đủ để biểu diễn recurrence tương lai.
- Với ngày sinh/đáo hạn chỉ có date, thường dùng `LocalDate` và quy định chronology đầu vào/đầu ra.
- Tránh lưu chuỗi đã được format bằng Thai digits/Japanese era như định dạng máy-máy duy nhất nếu không có metadata chronology/zone và parser tương ứng.

### 10.2. `Locale` không phải múi giờ

~~~java
Locale l = Locale.forLanguageTag("en-US-u-tz-usnyc");
ZoneId z = ZoneId.of("America/New_York");
~~~

`l` là lựa chọn locale có Unicode preference; `z` là mã zone cụ thể. Việc tạo `l` không gọi `TimeZone.setDefault` và không tự biến `ZoneId.systemDefault()` thành New York.

Nếu hệ thống có trường userTimeZone riêng (thường là IANA ID), hãy ưu tiên nó khi tính toán dữ liệu nghiệp vụ; dùng `tz` nếu giao thức/formatter đã quy định rõ việc lấy zone từ locale.

## 11. Tạo và validate Locale đúng cách

### 11.1. Dùng `forLanguageTag` với BCP 47

~~~java
Locale displayLocale = Locale.forLanguageTag(
        "en-US-u-ca-japanese-nu-thai-tz-usnyc");

String calendar = displayLocale.getUnicodeLocaleType("ca");
String numbers = displayLocale.getUnicodeLocaleType("nu");
String zoneType = displayLocale.getUnicodeLocaleType("tz");
~~~

`Locale` có thể mang các Unicode keywords mà các service cụ thể **không hỗ trợ**. Việc parser nhận một tag không chứng minh calendar/numbering/time-zone type đó khả dụng trong mọi runtime.

### 11.2. Dùng `Locale.Builder` nếu thay từng keyword

~~~java
Locale configured = new Locale.Builder()
        .setLocale(Locale.US)
        .setUnicodeLocaleKeyword("ca", "japanese")
        .setUnicodeLocaleKeyword("nu", "thai")
        .setUnicodeLocaleKeyword("tz", "usnyc")
        .build();
~~~

`Locale.Builder` kiểm tra cú pháp BCP 47 phù hợp, nhưng không bắt buộc xác nhận mọi type **được hỗ trợ về ngữ nghĩa**. Có thể xóa một keyword bằng `setUnicodeLocaleKeyword("ca", null)`.

Nếu nhận user input như `"ca=xyz"`, nên:

1. Giới hạn độ dài của tag hoặc từng type.
2. Parse/validate cú pháp bằng công cụ thích hợp.
3. Kiểm tra allowlist các calendar/numbering/zone được sản phẩm hỗ trợ.
4. Chuyển thành Chronology/DecimalStyle/ZoneId và bắt các lỗi chuyển đổi ở boundary.
5. Nếu key bắt buộc nhưng không hỗ trợ, từ chối rõ ràng thay vì âm thầm fallback sang hệ lịch khác làm hỏng ý nghĩa nghiệp vụ.

### 11.3. Không suy luận được ZoneId IANA từ mọi chuỗi tùy ý

Một giá trị `tz-usnyc` đúng chuẩn Unicode có thể được Java ánh xạ thành `America/New_York`, nhưng tên IANA `America/New_York` **không** phải Unicode locale type hợp lệ để tự nhét nguyên văn vào `tz`. Đừng tự thay slash bằng dấu gạch hoặc tách chữ để “đổi loại” khi không có bảng ánh xạ chính thức.

Nếu hệ thống đã nhận IANA zone ID, dùng `ZoneId.of(userZoneId)` với validation tường minh thay vì vòng qua Locale. Với các ứng dụng web thông thường, việc lưu tách `Locale` và `ZoneId` trong user preferences thường rõ hợp đồng hơn.

## 12. Thiết kế API theo user/tenant: không thay đổi global defaults

`DateTimeFormatter` immutable và thread-safe, nên có thể lưu những formatter cố định/chung. Nhưng với user preferences riêng:

~~~java
static DateTimeFormatter userDateTimeFormatter(
        Locale locale, ZoneId zone) {
    return DateTimeFormatter
            .ofPattern("uuuu-MM-dd HH:mm", Locale.ROOT)
            .localizedBy(locale)
            .withZone(zone);
}
~~~

Đây là **phương thức minh họa**, giả định `locale` và `zone` được validate, không `null`. Chú ý thứ tự: `localizedBy(locale)` áp các rule lịch/chữ số đã chọn, sau đó `withZone(zone)` bảo đảm **ZoneId đã xác thực của user** có ưu tiên hơn `tz` có thể nằm trong locale.

Nếu business cần ISO chronology và ASCII digits cho output máy-máy:

~~~java
static DateTimeFormatter machineFormatter(ZoneId zone) {
    return DateTimeFormatter
            .ofPattern("uuuu-MM-dd'T'HH:mm:ssXXX", Locale.ROOT)
            .withChronology(IsoChronology.INSTANCE)
            .withDecimalStyle(DecimalStyle.STANDARD)
            .withZone(zone);
}
~~~

Đây cũng là method minh họa; trong nhiều giao thức machine-to-machine hãy dùng trực tiếp `DateTimeFormatter.ISO_OFFSET_DATE_TIME`/`ISO_INSTANT` thay vì tự đặt pattern, tùy contract.

**Không gọi `Locale.setDefault`, `TimeZone.setDefault` hoặc thay system properties cho từng request** trong web server multi-tenant. Các thay đổi global có thể ảnh hưởng request khác và làm test khó tái hiện. Truyền `Locale`/`ZoneId` rõ ràng qua ranh giới API.

### 12.1. Không cache mỗi user bằng formatter mutable

`DateTimeFormatter` là immutable, nhưng **đối tượng chứa cấu hình Locale/ZoneId theo user** có thể đổi khi user cập nhật profile. Cache formatter theo key đầy đủ, có chính sách invalidation, hoặc dựng formatter theo yêu cầu nếu chi phí chấp nhận được. Không giữ một formatter global được “sửa tiếp” theo request — các `withXxx` trả instance mới, không mutate instance cũ.

### 12.2. Mở rộng theo bối cảnh khác nhau

- **UI:** có thể cho người dùng chọn calendar, digits và timezone.
- **Log/metrics:** thường dùng chuẩn ổn định như ISO UTC, không lấy locale người dùng để định dạng dữ liệu kỹ thuật.
- **Billing:** ZoneId, local cutoff, currency và calendar rules phải do domain quyết định, không tự suy ra từ country/locale.
- **Lịch sự kiện:** timezone và chronology phục vụ hiển thị không nhất thiết là calendar logic tính recurrence.
- **API response:** cần mô tả format, zone, calendar/era và numbering ở schema/metadata nếu chấp nhận nhiều cách biểu diễn.

## 13. Ví dụ Java 17+ hoàn chỉnh đã biên dịch và chạy

Ví dụ sử dụng các API Java SE còn hiệu lực và in các giá trị có ý nghĩa kỹ thuật:

- So sánh `withLocale` với `localizedBy`.
- Chứng minh `ca-japanese`, `nu-thai`, `tz-usnyc` được ánh xạ vào formatter.
- Phân biệt `Chronology.ofLocale(th-TH)` với explicit `ca-buddhist`.
- Kiểm tra chữ số Thai/Latin/Arabic bằng Unicode code point để không cần terminal hỗ trợ font.
- Định dạng một `Instant` trong New York và UTC.
- Chứng minh thứ tự method chaining thay chronology/decimal style/zone.
- Dùng ngày 2024-01-02 để minh họa era Nhật Bản và ISO LocalDate.
- Xử lý unsupported calendar type.

Lưu đúng tên **`LocaleFormatterExtensionsDemo.java`**:

~~~java
import java.time.DateTimeException;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.chrono.Chronology;
import java.time.chrono.IsoChronology;
import java.time.format.DateTimeFormatter;
import java.time.format.DecimalStyle;
import java.util.Locale;

public class LocaleFormatterExtensionsDemo {
    static String chrono(DateTimeFormatter formatter) {
        return formatter.getChronology() == null ? "none"
                : formatter.getChronology().getId();
    }

    static String zone(DateTimeFormatter formatter) {
        return formatter.getZone() == null ? "none"
                : formatter.getZone().getId();
    }

    static String hex(char digit) {
        return String.format(Locale.ROOT, "U+%04X", (int) digit);
    }

    public static void main(String[] args) {
        var japanese = Locale.forLanguageTag("en-US-u-ca-japanese");
        var thaiNumbers = Locale.forLanguageTag("en-US-u-nu-thai");
        var newYork = Locale.forLanguageTag("en-US-u-tz-usnyc");
        var combined = Locale.forLanguageTag(
                "en-US-u-ca-japanese-nu-thai-tz-usnyc");

        var base = DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm VV", Locale.US);
        var textOnly = base.withLocale(combined);
        var full = base.localizedBy(combined);

        System.out.println("locale-tag=" + combined.toLanguageTag());
        System.out.println("ca-key=" + combined.getUnicodeLocaleType("ca"));
        System.out.println("nu-key=" + combined.getUnicodeLocaleType("nu"));
        System.out.println("tz-key=" + combined.getUnicodeLocaleType("tz"));
        System.out.println("base-chronology=" + chrono(base));
        System.out.println("withLocale-chronology=" + chrono(textOnly));
        System.out.println("localized-chronology=" + chrono(full));
        System.out.println("withLocale-zero=" +
                hex(textOnly.getDecimalStyle().getZeroDigit()));
        System.out.println("localized-zero=" +
                hex(full.getDecimalStyle().getZeroDigit()));
        System.out.println("withLocale-zone=" + zone(textOnly));
        System.out.println("localized-zone=" + zone(full));

        System.out.println("ofLocale-th-TH=" +
                Chronology.ofLocale(Locale.forLanguageTag("th-TH")).getId());
        System.out.println("ofLocale-japanese=" +
                Chronology.ofLocale(japanese).getId());
        System.out.println("ofLocale-buddhist=" +
                Chronology.ofLocale(Locale.forLanguageTag(
                        "th-TH-u-ca-buddhist")).getId());

        var numericBase = DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.US);
        var date = LocalDate.of(2024, 1, 2);
        var numericTextOnly = numericBase.withLocale(thaiNumbers);
        var numericLocalized = numericBase.localizedBy(thaiNumbers);
        System.out.println("withLocale-numbers=" +
                numericTextOnly.format(date));
        System.out.println("localized-thai-digits=" +
                numericLocalized.format(date).equals("\u0E52\u0E50\u0E52\u0E54-\u0E50\u0E51-\u0E50\u0E52"));
        System.out.println("decimal-thai=" + hex(
                DecimalStyle.of(thaiNumbers).getZeroDigit()));
        System.out.println("decimal-latin=" + hex(
                DecimalStyle.of(Locale.forLanguageTag(
                        "en-US-u-nu-latn")).getZeroDigit()));
        System.out.println("decimal-arab=" + hex(
                DecimalStyle.of(Locale.forLanguageTag(
                        "en-US-u-nu-arab")).getZeroDigit()));

        var instant = Instant.parse("2024-01-01T00:00:00Z");
        var timeFormatter = DateTimeFormatter.ofPattern(
                "uuuu-MM-dd HH:mm VV", Locale.US);
        System.out.println("time-n-y=" +
                timeFormatter.localizedBy(newYork).format(instant));
        System.out.println("time-utc=" +
                timeFormatter.withZone(ZoneId.of("UTC")).format(instant));
        System.out.println("instant-unchanged=" + instant.toString());

        var zoneBefore = timeFormatter.withZone(ZoneId.of("UTC"))
                .localizedBy(newYork);
        var zoneAfter = timeFormatter.localizedBy(newYork)
                .withZone(ZoneId.of("UTC"));
        System.out.println("localized-last-zone=" + zone(zoneBefore));
        System.out.println("withZone-last-zone=" + zone(zoneAfter));

        var caBefore = numericBase.withChronology(IsoChronology.INSTANCE)
                .localizedBy(japanese);
        var caAfter = numericBase.localizedBy(japanese)
                .withChronology(IsoChronology.INSTANCE);
        System.out.println("localized-last-ca=" + chrono(caBefore));
        System.out.println("withChronology-last-ca=" + chrono(caAfter));

        var decimalBefore = numericBase
                .withDecimalStyle(DecimalStyle.STANDARD)
                .localizedBy(thaiNumbers);
        var decimalAfter = numericBase.localizedBy(thaiNumbers)
                .withDecimalStyle(DecimalStyle.STANDARD);
        System.out.println("localized-last-zero=" +
                hex(decimalBefore.getDecimalStyle().getZeroDigit()));
        System.out.println("withDecimalStyle-last-zero=" +
                hex(decimalAfter.getDecimalStyle().getZeroDigit()));

        System.out.println("japanese-era-year=" +
                DateTimeFormatter.ofPattern("G y", Locale.US)
                        .localizedBy(japanese).format(date));
        System.out.println("iso-date-unchanged=" + date);

        try {
            Chronology.ofLocale(Locale.forLanguageTag("en-US-u-ca-xyz"));
        } catch (DateTimeException expected) {
            System.out.println("unknown-calendar=rejected");
        }

        System.out.println("locale-not-global=" +
                !Locale.getDefault().equals(combined));
    }
}
~~~

Lệnh kiểm chứng trên JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 LocaleFormatterExtensionsDemo.java
java LocaleFormatterExtensionsDemo
~~~

**Stdout chính xác trên môi trường JDK đã thử:**

~~~text
locale-tag=en-US-u-ca-japanese-nu-thai-tz-usnyc
ca-key=japanese
nu-key=thai
tz-key=usnyc
base-chronology=none
withLocale-chronology=none
localized-chronology=Japanese
withLocale-zero=U+0030
localized-zero=U+0E50
withLocale-zone=none
localized-zone=America/New_York
ofLocale-th-TH=ISO
ofLocale-japanese=Japanese
ofLocale-buddhist=ThaiBuddhist
withLocale-numbers=2024-01-02
localized-thai-digits=true
decimal-thai=U+0E50
decimal-latin=U+0030
decimal-arab=U+0660
time-n-y=2023-12-31 19:00 America/New_York
time-utc=2024-01-01 00:00 UTC
instant-unchanged=2024-01-01T00:00:00Z
localized-last-zone=America/New_York
withZone-last-zone=UTC
localized-last-ca=Japanese
withChronology-last-ca=ISO
localized-last-zero=U+0E50
withDecimalStyle-last-zero=U+0030
japanese-era-year=Reiwa 6
iso-date-unchanged=2024-01-02
unknown-calendar=rejected
locale-not-global=true
~~~

**Chú thích về độ ổn định:** Hầu hết dòng kiểm tra explicit `ca/nu/tz` và các override đã được xác minh theo API trên môi trường thử. Tên era `Reiwa`/dữ liệu địa phương hóa và ánh xạ timezone phụ thuộc bộ dữ liệu locale/tzdb của JDK; ví dụ lấy trong môi trường đã thử. Dòng cuối `locale-not-global=true` chỉ phản ánh **default locale của môi trường đã thử không bằng tag tùy biến**; đó không phải assert có giá trị trên mọi hệ thống và không cần đưa vào cross-JDK unit test. Chương trình không thay global Locale.

## 14. Giải thích output theo nhóm

### 14.1. Locale và Unicode keyword

~~~text
locale-tag=en-US-u-ca-japanese-nu-thai-tz-usnyc
ca-key=japanese
nu-key=thai
tz-key=usnyc
~~~

`Locale.forLanguageTag` nhận một tag có ba keyword. `getUnicodeLocaleType` trả lại đúng loại được gắn vào Locale. **Lưu tag không có nghĩa tự động đổi mọi service**; phải sử dụng các API nhận biết những extension ấy.

### 14.2. `withLocale` đối chiếu `localizedBy`

~~~text
base-chronology=none
withLocale-chronology=none
localized-chronology=Japanese
withLocale-zero=U+0030
localized-zero=U+0E50
withLocale-zone=none
localized-zone=America/New_York
~~~

Formatter tạo từ `ofPattern(..., Locale.US)` chưa có override Chronology/ZoneId. `withLocale` giữ nguyên trạng thái override; `localizedBy` áp các lựa chọn Unicode `ca/nu/tz`. Đây là khác biệt trọng tâm của Java 10.

### 14.3. Calendar và numbering

~~~text
ofLocale-th-TH=ISO
ofLocale-japanese=Japanese
ofLocale-buddhist=ThaiBuddhist
withLocale-numbers=2024-01-02
localized-thai-digits=true
decimal-thai=U+0E50
decimal-latin=U+0030
decimal-arab=U+0660
~~~

`Chronology.ofLocale` cần explicit calendar type cho các hệ lịch không phải ISO trong các trường hợp này. `DecimalStyle.of` với `nu` giúp chọn ký hiệu zero; `localizedBy` có thể áp nó cho numeric fields của date-time formatter.

### 14.4. ZoneId và Instant

~~~text
time-n-y=2023-12-31 19:00 America/New_York
time-utc=2024-01-01 00:00 UTC
instant-unchanged=2024-01-01T00:00:00Z
~~~

Một Instant duy nhất được format theo hai zone khác nhau. Zone thay đổi cách biểu diễn thời gian địa phương, **không thay bản thân instant**.

### 14.5. Thứ tự chaining

~~~text
localized-last-zone=America/New_York
withZone-last-zone=UTC
localized-last-ca=Japanese
withChronology-last-ca=ISO
localized-last-zero=U+0E50
withDecimalStyle-last-zero=U+0030
~~~

Phương thức ghi đè nào được gọi sau có thể quyết định trạng thái cuối của formatter. Đây là lý do code review cần kiểm tra **thứ tự method chain**, không chỉ sự có mặt của `localizedBy`/`withZone`.

### 14.6. Era, dữ liệu gốc và lỗi

~~~text
japanese-era-year=Reiwa 6
iso-date-unchanged=2024-01-02
unknown-calendar=rejected
~~~

Chuyển presentation sang Japanese chronology không mutate `LocalDate` ISO. Một calendar type không có implementation được `Chronology.ofLocale` hỗ trợ phải được bắt/validate ở boundary.

## 15. Các bẫy khi format/parse ngày giờ quốc tế hóa

### 15.1. Coi năm hiển thị theo chronology là năm ISO

Khi pattern có `G y`, kết quả có thể là **era + year-of-era**, không giống ISO year `uuuu`. Đừng parse chuỗi `Reiwa 6` bằng một formatter ISO thuần rồi kỳ vọng nhận năm 2024. Muốn hỗ trợ nhiều lịch, chọn chronology và pattern có đầy đủ era/month/day tương ứng.

### 15.2. Coi `nu-thai` thay đổi dữ liệu số của `LocalDate`

`LocalDate.of(2024,1,2)` vẫn biểu diễn ngày ISO 2024-01-02. `nu-thai` ảnh hưởng **glyphs dùng trong format/parse** khi DecimalStyle thích hợp, không tự biến ngày thành một loại LocalDate khác hoặc thay `getYear()`.

### 15.3. Coi `tz` tự xác định giờ của một `LocalDateTime`

`LocalDateTime` thiếu offset và zone. Nếu muốn biến nó thành Instant, phải chọn ZoneId và xét DST. Một ngữ cảnh locale có `tz` chỉ là gợi ý để formatter có thể áp zone; không thay đổi thực thể date-time đầu vào.

### 15.4. Nhầm date-time format với numeric/currency format

`DecimalStyle` là phần của `java.time.format`; khi tạo hóa đơn, số tiền, tỷ lệ phần trăm, cần API/format chuyên dụng và chính sách rounding/precision. Không truyền DateTimeFormatter vào bài toán tiền tệ.

### 15.5. Dùng formatter có override vô tình khi parse dữ liệu máy

Nếu một API machine-readable yêu cầu ISO 8601 với chữ số Latin, việc dùng formatter theo Locale người dùng có thể thay digits, calendar và zone trong output hoặc parsing. Nên dùng `DateTimeFormatter.ISO_INSTANT`, `ISO_LOCAL_DATE` hoặc formatter chuẩn kỹ thuật có contract explicit thay vì formatter UI.

### 15.6. Dựa quá nhiều vào default locale

Dữ liệu CLDR và quy tắc timezone được nâng cấp qua JDK; default locale cũng phụ thuộc môi trường. Nếu hệ thống cần số liệu tài chính hoặc báo cáo được tái lập chính xác, lưu metadata về zone, chronology, calendar rule và dùng explicit IDs thay vì chỉ dựa locale mặc định của server.

## 16. Xử lý lỗi và input không tin cậy

| Trường hợp | Rủi ro | Biện pháp |
| --- | --- | --- |
| `ca` không được hỗ trợ | `Chronology.ofLocale` có thể ném `DateTimeException` | Allowlist và xử lý lỗi tại API boundary |
| `nu` lạ | Có thể fallback/không đạt kỳ vọng | Validate numbering system mà sản phẩm chấp nhận |
| `tz` không thể map như mong muốn | Formatter không có zone hoặc zone khác | Dùng ZoneId IANA đã validate cho nghiệp vụ |
| Tag sai cú pháp | Locale parser/builder có thể sửa/rút bớt hoặc ném lỗi tùy API | Dùng Builder/validation có kiểm soát |
| `Locale`/`ZoneId` là null | Các factory/override có thể ném `NullPointerException` | Validate ở ranh giới |
| Format `Instant` với pattern calendar không zone | `DateTimeException`/`UnsupportedTemporalTypeException` | Gắn `withZone` hoặc dùng temporal có zone |
| Parse Thai digits với DecimalStyle ASCII | Lỗi parse hoặc diễn giải không như mong muốn | Dùng đúng formatter/DecimalStyle |
| Xử lý `LocalDateTime` ở DST gap/overlap | Giờ không tồn tại/trùng | Chọn ZoneId và policy rõ |
| Hard-code tên era/zone display | Khác dữ liệu CLDR và locale | Test invariant, không ép text nếu không kiểm soát |
| Mutate Locale default giữa nhiều request | Race/ảnh hưởng user khác | Truyền Locale tường minh |
| Override sai thứ tự | Zone/chronology/digits cuối bị thay | Chốt explicit `withXxx` ở cuối |
| Lưu chuỗi UI làm canonical time | Không ổn định khi đổi preferences | Lưu Instant/LocalDate theo schema và format khi đọc |

Nếu hệ thống có trường UTC timestamp và người dùng chọn `ca-japanese`, `nu-thai`, `tz-usnyc`, các bước thường nên là: xác thực Instant → lấy config/locale đã validate → dựng formatter UI → chuyển/format → escape theo UI context. Không cho input locale trực tiếp thay đổi logic đồng bộ thời gian hoặc cơ chế tính phí.

## 17. Bảng quyết định API cho từng mục tiêu

| Mục tiêu | API phù hợp | Điều không được suy ra |
| --- | --- | --- |
| Chỉ đổi ngôn ngữ tên tháng/thứ | `withLocale(locale)` | Không tự set chronology/zone/DecimalStyle |
| Dùng Unicode `ca/nu/tz/rg` cho formatter | `localizedBy(locale)` | Không cần tự mutate LocalDate/Instant |
| Chọn lịch Nhật theo Locale | `Chronology.ofLocale(locale)` hoặc `localizedBy` | Không phải mọi type calendar đều hỗ trợ |
| Chọn Thai digits cho date-time | `DecimalStyle.of(locale)` hoặc `localizedBy` | Không tự format tiền tệ/nhóm nghìn |
| Chọn múi giờ business có ID rõ | `withZone(ZoneId.of(id))` | Không suy zone chỉ từ quốc gia |
| Format một Instant theo zone user | `formatter.withZone(zone).format(instant)` | Instant không đổi |
| Đầu ra ISO 8601 ổn định | `ISO_INSTANT`, `ISO_LOCAL_DATE`, explicit zone | Không áp locale UI vào dữ liệu máy |
| Muốn ưu tiên Locale override | Gọi `localizedBy(locale)` sau overrides cũ | Phải hiểu key được JDK hỗ trợ |
| Muốn ưu tiên policy của ứng dụng | `localizedBy(locale)` rồi `withXxx` | Order gọi method có ý nghĩa |
| Đánh giá input locale chưa tin cậy | Parser/Builder + allowlist + try/catch | BCP47 syntax không xác nhận semantic support |
| Xử lý lịch làm việc | Work calendar/holiday data riêng | `ca`/`tz` không quyết định ngày nghỉ |

## 18. Bài tập tự kiểm tra có đáp án

**Bài 1.** `withLocale(en-US-u-ca-japanese)` có tự đặt `JapaneseChronology` vào một `DateTimeFormatter.ofPattern` ban đầu chưa có chronology override không?

**Đáp án:** Không. Theo Javadoc, `withLocale` chỉ lưu locale để tra cứu hiển thị; dùng `localizedBy` hoặc `withChronology` để đặt chronology override.

**Bài 2.** Java 10 thêm method quan trọng nào giúp áp ca/nu/tz lên formatter?

**Đáp án:** `DateTimeFormatter.localizedBy(Locale)`, `Since: 10`.

**Bài 3.** `Chronology.ofLocale(Locale.forLanguageTag("th-TH"))` trên ví dụ trả gì?

**Đáp án:** `ISO`. Không có explicit `ca` thì phương thức thường trả ISO chronology.

**Bài 4.** Muốn Thai Buddhist Chronology qua Locale, dùng tag gì?

**Đáp án:** Ví dụ `th-TH-u-ca-buddhist`; `Chronology.ofLocale` trả `ThaiBuddhist` khi runtime hỗ trợ.

**Bài 5.** `ca-japanese` có biến `LocalDate` lưu sẵn thành object khác không?

**Đáp án:** Không. Nó có thể thay cách formatter chuyển/diễn giải date; object `LocalDate` không bị mutate.

**Bài 6.** `DecimalStyle` phục vụ bài toán nào?

**Đáp án:** Ký hiệu chữ số/dấu dương/âm/dấu thập phân cho date-time formatting/parsing; không phải bộ xử lý tổng quát cho money/percentage.

**Bài 7.** `nu-thai` cho zero digit code point gì trong demo?

**Đáp án:** `U+0E50`.

**Bài 8.** `nu-latn` cho zero digit gì?

**Đáp án:** `U+0030`, ASCII `0`.

**Bài 9.** `nu-arab` cho zero digit gì trong demo?

**Đáp án:** `U+0660`, Arabic-Indic zero.

**Bài 10.** `tz-usnyc` tương ứng ZoneId nào ở JDK đã kiểm chứng?

**Đáp án:** `America/New_York`.

**Bài 11.** Có thể gọi `ZoneId.of("usnyc")` như cách trực tiếp biến Unicode type thành ZoneId không?

**Đáp án:** Không được mặc định. `usnyc` là Unicode locale type, còn ID chuẩn dùng trong ZoneId thường là `America/New_York`; cần ánh xạ hợp lệ.

**Bài 12.** Một Instant `2024-01-01T00:00:00Z` khi format tại New York có ngày gì trong demo?

**Đáp án:** `2023-12-31 19:00` theo `America/New_York` tại thời điểm đó. Instant ban đầu không đổi.

**Bài 13.** Muốn timezone UTC thắng `tz-usnyc` thì order nào hợp lý?

**Đáp án:** `formatter.localizedBy(locale).withZone(ZoneId.of("UTC"))`.

**Bài 14.** Muốn ISO chronology thắng `ca-japanese` thì làm sao?

**Đáp án:** `formatter.localizedBy(locale).withChronology(IsoChronology.INSTANCE)`.

**Bài 15.** Muốn ASCII digits thắng `nu-thai` trong formatter thì làm sao?

**Đáp án:** `formatter.localizedBy(locale).withDecimalStyle(DecimalStyle.STANDARD)`.

**Bài 16.** Nếu có cả `ca` và `rg`, giá trị nào ưu tiên cho chronology?

**Đáp án:** `ca` explicit ưu tiên hơn chronology ngầm suy từ `rg` theo Javadoc `localizedBy`.

**Bài 17.** Nếu có cả `nu` và `rg`, giá trị nào ưu tiên cho numbering system?

**Đáp án:** `nu` explicit ưu tiên so với numbering ngầm từ `rg`.

**Bài 18.** `Locale.forLanguageTag("en-US-u-ca-xyz")` có bảo đảm có Chronology hợp lệ không?

**Đáp án:** Không. Parser chấp nhận cấu trúc tag không đồng nghĩa runtime có calendar đó; `Chronology.ofLocale` có thể ném `DateTimeException`.

**Bài 19.** Có nên đổi `Locale.setDefault` cho mỗi request nếu nhiều user chọn các lịch khác nhau không?

**Đáp án:** Không. Hãy truyền locale/zone theo user/request, tránh tác động default toàn JVM.

**Bài 20.** Cần lưu timestamp để hệ thống khác đọc không phụ thuộc locale, chọn gì?

**Đáp án:** Dùng Instant/ISO UTC (hoặc format ISO có offset và schema rõ), không lưu duy nhất một chuỗi date-time đã localized theo sở thích người dùng.

**Bài 21.** Vì sao `G y` trong Japanese calendar có thể khác `uuuu`?

**Đáp án:** `G` là era, `y` là year-of-era; `uuuu` là proleptic-year. Chọn pattern theo ý nghĩa dữ liệu, không mặc định mọi “năm” đều giống nhau.

**Bài 22.** Một `LocalDateTime` và `Locale` với `tz` có đủ để xác định chắc Instant cho lịch hẹn vào ngày DST chuyển mùa không?

**Đáp án:** Cần một ZoneId đã xác thực và chính sách xử lý local time bị lặp/khuyết. `LocalDateTime` bản thân không chứa offset/zone; Locale chỉ là lựa chọn địa phương hóa.

## 19. Checklist áp dụng trong dự án thực tế

1. **Bạn đang xử lý hiển thị hay nghiệp vụ?** Chọn Locale cho UI; chọn chronology/zone explicit khi nghiệp vụ đòi tính toán chính xác.
2. **Có cần chỉ đổi tên tháng/thứ?** Nếu có, `withLocale` đủ; đừng tự áp calendar/zone ngoài ý muốn.
3. **Có cần Unicode `ca`/`nu`/`tz` không?** Nếu có, cân nhắc `localizedBy` từ Java 10.
4. **Có `rg` không?** Đã hiểu thứ tự ưu tiên `ca`/`nu` đối với giá trị ngầm theo vùng?
5. **Chronology có được JDK hỗ trợ không?** Có validate calendar type?
6. **Hệ chữ số có đúng yêu cầu UI không?** Đã kiểm tra `DecimalStyle.of(locale)` và format/parse?
7. **ZoneId có ý nghĩa nghiệp vụ không?** Có lưu explicit IANA ID thay vì suy từ country?
8. **Thứ tự method chaining có rõ ràng không?** Override nào cần thắng hãy đặt sau `localizedBy`.
9. **Đầu vào là Instant, LocalDateTime hay LocalDate?** Chúng có vùng thời gian/ngữ nghĩa khác nhau.
10. **Có dùng `DateTimeFormatter` immutable và tạo theo profile thay vì sửa global defaults không?**
11. **Có dữ liệu Unicode/era/time-zone name cần kiểm thử cùng JDK/CLDR target không?**
12. **Có cần dữ liệu máy-máy format ISO cố định, không chịu ảnh hưởng profile locale không?**
13. **Có kiểm tra unsupported type/invalid tag/NullPointerException/DateTimeException không?**
14. **Có bảo đảm parser sử dụng cùng chronology/decimal style/zone với input không?**
15. **Có cần version timezone database (tzdb) hay calendar rules khi tái lập báo cáo quá khứ không?**
16. **Unit test có so sánh trạng thái `getChronology()/getDecimalStyle()/getZone()` thay vì chỉ dựa chuỗi hiển thị theo một bản dữ liệu locale không?**
17. **Các request nhiều user có giữ Locale/ZoneId độc lập với nhau không?**
18. **Có phân biệt format display với business calendar, working days, holidays, billing cutoff và scheduling không?**

## 20. Tài liệu tham khảo chính thức còn áp dụng

1. [Java SE 17 – DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html): `withLocale`, `localizedBy` (Since 10), `withChronology`, `withDecimalStyle`, `withZone` và `getXxx`; thứ tự chaining.
2. [Java SE 26 – DateTimeFormatter](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatter.html): xác nhận mô hình `localizedBy` còn được duy trì trong tài liệu JDK hiện đại.
3. [Java SE 17 – Chronology](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/chrono/Chronology.html): `ofLocale`, key `ca`, ISO default và calendar unsupported error.
4. [Java SE 17 – DecimalStyle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DecimalStyle.html): `of(Locale)` với `nu`/`rg`, `getZeroDigit`, signs và decimal separator.
5. [Java SE 17 – Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): BCP 47 Unicode extension, `getUnicodeLocaleType` và lưu ý về service support.
6. [Java SE 17 – Locale.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.Builder.html): `setUnicodeLocaleKeyword` và validation cú pháp.
7. [Java SE 17 – ZoneId](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html): IANA zone ID, quy tắc zone và xử lý time zone.
8. [Java SE 17 – Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): time-line và các thời điểm không phụ thuộc Locale.
9. [Oracle – Internationalization Enhancements in JDK 10](https://docs.oracle.com/javase/10/intl/internationalization-enhancements-jdk-10.htm): Unicode locale keys bổ sung trong Java 10 như `rg`/`tz`.
10. [Unicode LDML – UTS #35](https://www.unicode.org/reports/tr35/): các key/type Unicode locale và dữ liệu địa phương hóa.
11. [Unicode CLDR – BCP47 timezone types](https://github.com/unicode-org/cldr/blob/main/common/bcp47/timezone.xml): các type múi giờ dùng trong Unicode locale extensions.

**Kết luận:** Để dùng Unicode locale extensions ảnh hưởng đến calendar, chữ số và múi giờ khi format ngày giờ, Java 10 đưa ra **`DateTimeFormatter.localizedBy(locale)`**. `withLocale(locale)` không tự thiết lập những override này. `ca` có thể chọn `Chronology`, `nu` có thể chọn `DecimalStyle` và `tz` có thể đặt `ZoneId` cho formatter; `rg` còn ảnh hưởng quy tắc theo vùng, với `ca`/`nu` explicit được ưu tiên. Hãy luôn phân biệt các tùy chọn **hiển thị** với **dữ liệu thời gian nghiệp vụ**, kiểm soát thứ tự `withXxx`, không sửa global defaults theo từng user và giữ định dạng máy-máy theo hợp đồng ISO/ZoneId rõ ràng.

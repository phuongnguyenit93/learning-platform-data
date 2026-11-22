# Phân biệt khóa được lưu trong `Locale` với API thực sự sử dụng khóa đó

*Chủ đề cha: Mở rộng Locale, Java 10. Nội dung giải thích sự khác biệt giữa việc lưu một khóa Unicode locale extension trong `java.util.Locale` và việc lớp API tiêu thụ khóa ấy để thay đổi hành vi bản địa hóa. Các ví dụ chạy với Java 17 trở lên; chỉ sử dụng kiến thức vẫn áp dụng trong Java hiện đại.*

## 1. Ý chính: có khóa trong `Locale` chưa phải có hành vi

Một BCP 47 language tag có thể mang Unicode extension `-u-`:

```text
en-US-u-ca-japanese-nu-thai
```

Nó biểu diễn một Locale với ngôn ngữ Anh, vùng Hoa Kỳ và các đề nghị bổ sung:

- `ca=japanese`: kiểu lịch Nhật.
- `nu=thai`: hệ chữ số Thái.

`Locale` lưu và đọc lại được chúng:

```java
var locale = java.util.Locale.forLanguageTag(
        "en-US-u-ca-japanese-nu-thai");

System.out.println(locale.getUnicodeLocaleType("ca")); // japanese
System.out.println(locale.getUnicodeLocaleType("nu")); // thai
```

Tuy nhiên, **không thể suy ra mọi phương thức nhận `Locale` sẽ tự sử dụng cả hai khóa**. `Locale` là nơi lưu ngôn ngữ, vùng và sở thích bản địa hóa; hành vi là trách nhiệm của từng **consumer API**, chẳng hạn `Currency`, `WeekFields`, `Chronology`, `NumberFormat` hoặc `DateTimeFormatter`.

Ví dụ:

- `Locale.getUnicodeLocaleType("ca")` chỉ trả lại `"japanese"`.
- `Chronology.ofLocale(locale)` có thể chọn chronology Nhật theo `ca`.
- `DateTimeFormatter.withLocale(locale)` lưu Locale để tra cứu dữ liệu bản địa hóa nhưng không tự áp tất cả extension thành chronology, zone, decimal style.
- `DateTimeFormatter.localizedBy(locale)` (Java 10+) được thiết kế để áp dụng những thông tin extension như `ca`, `nu`, `rg`, `tz` vào formatter.
- `Currency.getInstance(locale)` có hợp đồng xem xét `cu`, `rg`.
- `WeekFields.of(locale)` có hợp đồng xem xét `fw`, `rg`.

**Nguyên tắc học:** luôn tách câu hỏi **“Locale đang lưu gì?”** khỏi câu hỏi **“API tôi gọi thực sự dùng gì?”**.

## 2. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Đọc cấu trúc Unicode BCP 47 `-u-`.
2. Dùng `Locale.forLanguageTag`, `Locale.Builder.setUnicodeLocaleKeyword`, `getUnicodeLocaleKeys`, `getUnicodeLocaleType`.
3. Phân biệt Unicode keys như `ca`/`nu` với singleton extension keys `u`/`x`.
4. Hiểu vì sao một key/type hợp cú pháp nhưng chưa chắc được runtime hoặc formatter hỗ trợ.
5. Biết các consumer quan trọng của `ca`, `nu`, `cu`, `fw`, `rg`, `tz`.
6. So sánh `DateTimeFormatter.withLocale` và `localizedBy` qua code và stdout.
7. Phân biệt giá trị type rỗng `""` với một key không hiện diện (trả `null`).
8. Tránh sai lầm khi xử lý các khóa `co`, `hc`, `kn`, `zz`.
9. Thiết kế kiểm thử đúng tầng, xử lý fallback, provider và dữ liệu locale.

## 3. Hai cấp key khác nhau trong BCP 47

```text
en-US-u-ca-japanese-nu-thai
|  |  | |  |       |  |
|  |  | |  |       |  +-- type của nu
|  |  | |  |       +----- Unicode key nu
|  |  | |  +------------- type của ca
|  |  | +---------------- Unicode key ca
|  |  +------------------ extension singleton u
|  +--------------------- region US
+------------------------ language en
```

Ở cấp ngoài, `Locale.getExtensionKeys()` trả các extension singleton dài một ký tự, chẳng hạn `u` (Unicode locale extension) và `x` (private use). Bên trong phần `u`, `Locale.getUnicodeLocaleKeys()` mới trả các keyword như `ca`, `nu`.

| API | Kết quả |
| --- | --- |
| `getLanguage()` | Mã ngôn ngữ của Locale |
| `getCountry()` | Vùng/country cơ sở của Locale |
| `getExtension(Locale.UNICODE_LOCALE_EXTENSION)` | Chuỗi nội dung extension `u` |
| `getUnicodeLocaleKeys()` | Tập Unicode keys hai ký tự, ví dụ `ca`, `nu` |
| `getUnicodeLocaleType("ca")` | Type của `ca` hoặc `null` nếu không có |
| `getExtensionKeys()` | Tập singleton extensions như `u` và `x` |
| `getExtension(Locale.PRIVATE_USE_EXTENSION)` | Nội dung extension private-use `x` |
| `toLanguageTag()` | Biểu diễn BCP 47 của Locale |

**Không dùng `getUnicodeLocaleType("u")` để hỏi phần `u`.** Một Unicode key phải có đúng hai ký tự chữ/số; `u` là extension singleton ở cấp khác.

### 3.1. Key có type rỗng khác key không tồn tại

```java
var l = java.util.Locale.forLanguageTag("en-US-u-kn");

System.out.println(l.getUnicodeLocaleType("kn").isEmpty()); // true
System.out.println(l.getUnicodeLocaleType("cu") == null);    // true
```

`kn` hiện diện nhưng type rỗng `""`. `cu` không được khai báo nên `getUnicodeLocaleType("cu")` trả `null`. Truyền tên key sai cú pháp, ví dụ `"z"`, có thể ném `IllegalArgumentException`; truyền `null` có thể ném `NullPointerException`.

## 4. Ví dụ chạy được: `Locale` lưu được cả khóa không có consumer bảo đảm

Tạo **`LocaleStorageDemo.java`**:

```java
import java.util.Locale;
import java.util.TreeSet;

public class LocaleStorageDemo {
    public static void main(String[] args) {
        var locale = Locale.forLanguageTag(
                "en-US-u-ca-japanese-nu-thai-zz-abc");

        System.out.println("tag=" + locale.toLanguageTag());
        System.out.println("country=" + locale.getCountry());
        System.out.println("unicode=" + locale.getExtension(
                Locale.UNICODE_LOCALE_EXTENSION));
        System.out.println("keys="
                + new TreeSet<>(locale.getUnicodeLocaleKeys()));
        System.out.println("ca=" + locale.getUnicodeLocaleType("ca"));
        System.out.println("nu=" + locale.getUnicodeLocaleType("nu"));
        System.out.println("zz=" + locale.getUnicodeLocaleType("zz"));
        System.out.println("missing="
                + (locale.getUnicodeLocaleType("cu") == null));

        var flag = Locale.forLanguageTag("en-US-u-kn");
        System.out.println("flagEmpty="
                + flag.getUnicodeLocaleType("kn").isEmpty());
    }
}
```

Chạy:

```bash
javac --release 17 LocaleStorageDemo.java
java LocaleStorageDemo
```

Stdout:

```text
tag=en-US-u-ca-japanese-nu-thai-zz-abc
country=US
unicode=ca-japanese-nu-thai-zz-abc
keys=[ca, nu, zz]
ca=japanese
nu=thai
zz=abc
missing=true
flagEmpty=true
```

`Locale` đã lưu được `zz=abc`, mặc dù code không biết consumer Java nào sẽ thực hiện một ý nghĩa cụ thể cho nó. `zz` gồm hai chữ và `abc` hợp cú pháp type, nhưng **không có quy tắc rằng mọi cặp key/type hợp cú pháp đều thay đổi hành vi các API**.

`TreeSet` được dùng chỉ để in thứ tự key ổn định; không nên dựa vào iteration order của tập do `getUnicodeLocaleKeys()` trả về. `getCountry()` vẫn là `US`: các extension không tự ghi đè field country cơ sở.

**Kết luận ở đây mới là “đã lưu và đọc lại được”**, chưa phải “formatter đã xử lý”.

## 5. Mối liên hệ với Java 10: JEP 314

`Locale` đã hiểu cú pháp BCP 47/Unicode locale extensions từ Java 7. Java 10 đáng chú ý vì **JEP 314: Additional Unicode Language-Tag Extensions** đưa thêm các khóa vào **các dịch vụ Java thật sự sử dụng chúng**:

- `cu` — currency type.
- `fw` — first day of week.
- `rg` — region override.
- `tz` — time zone.

`ca` (calendar) và `nu` (numbering system) đã có hỗ trợ trong các API liên quan trước Java 10. Ngoài ra, Java 10 bổ sung `DateTimeFormatter.localizedBy(Locale)` để áp các quy tắc bản địa hóa gồm calendar, numbering, region và timezone theo hợp đồng.

Điểm học quan trọng nhất **không phải lịch sử ngày ra đời của cú pháp `-u-`**, mà là phân biệt tính năng *lưu tag* và tính năng *tiêu thụ extension*.

### 5.1. Bảng key và consumer tiêu biểu

| Unicode key | Ý nghĩa | Consumer có hợp đồng liên quan | Không suy diễn |
| --- | --- | --- | --- |
| `ca` | Calendar type | `Chronology.ofLocale`, `DateFormat`, `DateTimeFormatter.localizedBy` | Mọi `withLocale` tự đổi chronology |
| `nu` | Numbering system | `NumberFormat`, `DecimalStyle.of`, `DateTimeFormatter.localizedBy` | `Integer.toString` đổi chữ số |
| `cu` | Currency type | `Currency.getInstance(Locale)` | Toàn bộ API tiền tệ tự đổi đơn vị giao dịch |
| `fw` | First day of week | `WeekFields.of(Locale)`, `Calendar` liên quan | Ngày của `LocalDate` tự đổi |
| `rg` | Region override | Một số API `Currency`, `NumberFormat`, `WeekFields` và formatter | `locale.getCountry()` tự đổi |
| `tz` | Time zone | `DateTimeFormatter.localizedBy`, một số factory `DateFormat` | `ZoneId.systemDefault()` tự đổi |
| `co` | Collation type | Tùy Collator/provider và type hỗ trợ | Mọi `Collator` hỗ trợ mọi `co` |
| `hc` | Hour cycle | Có thể biểu diễn trong Locale | Mọi pattern thời gian sẽ tự dùng `hc` |
| `kn` | Numeric collation | Có thể lưu flag | `String.compareTo` biết sắp số |
| `zz` | Khóa ví dụ hợp cú pháp | `Locale` lưu/đọc lại | Java bắt buộc có một consumer cho khóa này |

**Giới hạn:** Javadoc của `Locale` nói rõ các service locale-sensitive trong một Java runtime có thể không hỗ trợ mọi key/type của Unicode LDML. Hợp đồng của từng method mới xác định chuyện gì thực sự xảy ra.

## 6. `cu`: giá trị nằm trong Locale, Currency mới dùng nó

```java
var locale = java.util.Locale.forLanguageTag(
        "en-US-u-cu-eur");

System.out.println(locale.getCountry()); // US
System.out.println(locale.getUnicodeLocaleType("cu")); // eur
System.out.println(
        java.util.Currency.getInstance(locale).getCurrencyCode());
// EUR
```

Dòng `getUnicodeLocaleType` chỉ **đọc cấu hình**. `Currency.getInstance(Locale)` **áp dụng** `cu` và trả đối tượng Currency EUR. `getCountry()` vẫn là US: extension không tự biến Locale cơ sở thành locale của châu Âu.

Nếu có cả `cu` và `rg`, Javadoc của `Currency.getInstance` quy định `cu` tường minh ưu tiên tiền tệ suy ra từ `rg`. Nhưng đây là **quy tắc của Currency**, không phải ưu tiên chung có thể áp cho mọi API.

Ứng dụng tính tiền phải lưu số tiền, ISO currency code và quy tắc chuyển đổi theo nghiệp vụ; một `Locale` có `cu=eur` không tự đổi dữ liệu giao dịch từ USD thành EUR. Trình bày tiền tệ và tính toán giá trị là hai vấn đề khác nhau.

## 7. `fw`: API xác định tuần mới áp dụng ngày đầu tuần

```java
var mondayLocale = java.util.Locale.forLanguageTag(
        "en-US-u-fw-mon");

System.out.println(
        java.time.temporal.WeekFields.of(mondayLocale)
                .getFirstDayOfWeek());
// MONDAY
```

`WeekFields.of(Locale)` được tài liệu hóa là xử lý `fw` và `rg`. Nếu cả hai có mặt, `fw` tường minh được ưu tiên so với quy tắc ngày đầu tuần suy ra từ vùng. `java.util.Calendar` cũng có các API áp ngày đầu tuần theo Locale.

Không có nghĩa `LocalDate.getDayOfWeek()` thay ý nghĩa: ngày thứ hai vẫn là `DayOfWeek.MONDAY`. `fw` thay đổi **quy ước tính tuần** trong những consumer có hỗ trợ, chứ không sửa ngày hoặc enum.

## 8. `rg`: region override không sửa field country cơ sở

```java
var region = java.util.Locale.forLanguageTag(
        "en-US-u-rg-gbzzzz");

System.out.println(region.getCountry()); // US
System.out.println(region.getUnicodeLocaleType("rg")); // gbzzzz
System.out.println(
        java.util.Currency.getInstance(region).getCurrencyCode());
// GBP
```

`getCountry()` vẫn US vì đó là vùng cơ sở của Locale. Nhưng consumer Currency hiểu `rg=gbzzzz` và lấy GBP theo vùng được override.

Nhiều dịch vụ khác có thể xét `rg` để chọn dữ liệu địa phương hóa, nhưng không nên lập trình dựa vào việc `getCountry()` đổi hoặc tự cắt chuỗi tag để thay `US` thành `GB`. **Base region** và **region override** là hai thông tin riêng.

```java
var combined = java.util.Locale.forLanguageTag(
        "en-US-u-fw-mon-rg-gbzzzz");

System.out.println(
        java.time.temporal.WeekFields.of(combined)
                .getFirstDayOfWeek());
// MONDAY
```

Khi tính ngày đầu tuần, `WeekFields` tiêu thụ `fw=mon` tường minh, không cần lấy mặc định từ region override.

## 9. `tz`: lưu mã múi giờ không làm thay đổi mặc định JVM

```java
var zoneLocale = java.util.Locale.forLanguageTag(
        "en-US-u-tz-usnyc");

System.out.println(zoneLocale.getUnicodeLocaleType("tz"));
// usnyc
```

Lời gọi trên chỉ trả type Unicode timezone. Nó không tự gọi `TimeZone.setDefault` hay thay `ZoneId.systemDefault()`. Consumer `DateTimeFormatter.localizedBy(zoneLocale)` là một nơi JDK có thể áp `tz` để chọn override zone. Trong ví dụ đã kiểm thử, `tz-usnyc` ánh xạ tới `America/New_York`.

Khi hệ thống yêu cầu zone bắt buộc cho nghiệp vụ (như thời điểm thanh toán, lịch chạy job, log kiểm toán), nên giữ `ZoneId` hoặc chính sách zone riêng thay vì trông chờ mọi API đọc một Locale và tự suy ra đúng zone.

## 10. `ca` và `nu`: Calendar và chữ số

### 10.1. Calendar type `ca`

```java
var japanese = java.util.Locale.forLanguageTag(
        "ja-JP-u-ca-japanese");

System.out.println(japanese.getUnicodeLocaleType("ca"));
// japanese

System.out.println(
        java.time.chrono.Chronology.ofLocale(japanese).getId());
// Japanese
```

Dòng thứ nhất đọc metadata; dòng thứ hai gọi consumer `Chronology` để chọn lịch Nhật. Không phải mọi `LocalDate` của ứng dụng tự đổi thành `JapaneseDate` khi bạn tạo Locale.

### 10.2. Numbering system `nu`

```java
var thai = java.util.Locale.forLanguageTag(
        "th-TH-u-nu-thai");

System.out.println(thai.getUnicodeLocaleType("nu"));
// thai

var number = java.text.NumberFormat.getIntegerInstance(thai);
var formatted = number.format(123);
```

`NumberFormat` được tài liệu hóa xét `nu`/`rg`. `DecimalStyle.of(thai)` cũng có thể chọn chữ số phù hợp và `DateTimeFormatter.localizedBy(thai)` có thể áp hệ chữ số đó.

Nhưng `Integer.toString(123)` hoặc `System.out.println(123)` không có tham số Locale, nên không tự đổi `123` sang chữ số Thái. **Dữ liệu số và cách định dạng là hai tầng**.

Khi test numbering, hãy kiểm tra `DecimalStyle.getZeroDigit()` hoặc kết quả formatter thực tế, không chỉ `getUnicodeLocaleType("nu")`. Dữ liệu CLDR/locale-provider của runtime cũng có thể ảnh hưởng các chi tiết định dạng.

## 11. `withLocale` so với `localizedBy`: cùng Locale, khác hiệu lực

Đây là ví dụ quan trọng nhất về câu hỏi của bài.

**`DateTimeFormatter.withLocale(locale)`:** trả formatter mới, dùng Locale cho các yếu tố như tên tháng hoặc localized pattern, nhưng **không tự xử lý toàn bộ key thành override chronology, zone, decimal style**.

**`DateTimeFormatter.localizedBy(locale)`:** có từ Java 10, trả formatter mới với những giá trị bản địa hóa phù hợp, có thể áp `ca`, `nu`, `rg`, `tz` vào các thuộc tính đặc thù của formatter.

### 11.1. Chương trình hoàn chỉnh: `LocaleConsumersDemo.java`

```java
import java.time.chrono.Chronology;
import java.time.format.DateTimeFormatter;
import java.time.temporal.WeekFields;
import java.util.Currency;
import java.util.Locale;

public class LocaleConsumersDemo {
    public static void main(String[] args) {
        var currencyLocale =
                Locale.forLanguageTag("en-US-u-cu-eur");
        var weekLocale =
                Locale.forLanguageTag("en-US-u-fw-mon");
        var japanese =
                Locale.forLanguageTag("ja-JP-u-ca-japanese");

        System.out.println("currency="
                + Currency.getInstance(currencyLocale).getCurrencyCode());
        System.out.println("firstDay="
                + WeekFields.of(weekLocale).getFirstDayOfWeek());
        System.out.println("chronology="
                + Chronology.ofLocale(japanese).getId());

        var formatter = DateTimeFormatter.ofPattern("G y-MM-dd");
        var with = formatter.withLocale(japanese);
        var localized = formatter.localizedBy(japanese);

        System.out.println("withLocaleChronology="
                + with.getChronology());
        System.out.println("localizedByChronology="
                + localized.getChronology().getId());
    }
}
```

Chạy:

```bash
javac --release 17 LocaleConsumersDemo.java
java LocaleConsumersDemo
```

Stdout:

```text
currency=EUR
firstDay=MONDAY
chronology=Japanese
withLocaleChronology=null
localizedByChronology=Japanese
```

`DateTimeFormatter.ofPattern("G y-MM-dd")` ban đầu không có override chronology. `withLocale(japanese)` giữ Locale nhưng không gán chronology, nên getter là `null`. `localizedBy(japanese)` tiêu thụ `ca=japanese` và đặt chronology `Japanese`.

**Không kết luận từ `formatter.getLocale()` rằng mọi key đã có hiệu lực.** Khi cần chứng minh calendar đã áp, hỏi `formatter.getChronology()`; khi cần kiểm tra zone, hỏi `getZone()`; với hệ chữ số, hỏi `getDecimalStyle()`.

### 11.2. Thứ tự gọi các method override quan trọng

```java
// Đoạn minh họa trong method:
var japanese = java.util.Locale.forLanguageTag(
        "ja-JP-u-ca-japanese");

var formatter = java.time.format.DateTimeFormatter
        .ofPattern("G y")
        .localizedBy(japanese)
        .withChronology(
                java.time.chrono.IsoChronology.INSTANCE);
```

Ở đây `withChronology` được gọi sau và đặt ISO chronology. Nếu đảo thứ tự, `localizedBy` có thể áp calendar của Locale. Vì vậy không gọi `withLocale`, `localizedBy`, `withZone` hoặc `withChronology` tùy tiện rồi mong ý nghĩa không đổi.

## 12. Chương trình hoàn chỉnh: region, zone và chữ số

Tạo **`RegionAndZoneDemo.java`**:

```java
import java.time.format.DateTimeFormatter;
import java.time.format.DecimalStyle;
import java.time.temporal.WeekFields;
import java.util.Currency;
import java.util.Locale;

public class RegionAndZoneDemo {
    public static void main(String[] args) {
        var region = Locale.forLanguageTag(
                "en-US-u-rg-gbzzzz");
        var combined = Locale.forLanguageTag(
                "en-US-u-fw-mon-rg-gbzzzz");
        var zone = Locale.forLanguageTag(
                "en-US-u-tz-usnyc");

        System.out.println("baseCountry=" + region.getCountry());
        System.out.println("regionKey="
                + region.getUnicodeLocaleType("rg"));
        System.out.println("regionalCurrency="
                + Currency.getInstance(region).getCurrencyCode());
        System.out.println("firstDayOverride="
                + WeekFields.of(combined).getFirstDayOfWeek());

        var formatter = DateTimeFormatter.ofPattern("uuuu-MM-dd")
                .localizedBy(zone);
        System.out.println("zoneFromExtension=" + formatter.getZone());

        var thai = Locale.forLanguageTag("th-TH-u-nu-thai");
        System.out.println("zeroDigit="
                + (DecimalStyle.of(thai).getZeroDigit()
                   == '\u0E50'));
        System.out.println("localizedZeroDigit="
                + (DateTimeFormatter.ofPattern("yyyy")
                        .localizedBy(thai)
                        .getDecimalStyle().getZeroDigit()
                   == '\u0E50'));
    }
}
```

Chạy:

```bash
javac --release 17 RegionAndZoneDemo.java
java RegionAndZoneDemo
```

Stdout trên JDK có dữ liệu locale tương ứng (đã kiểm thử):

```text
baseCountry=US
regionKey=gbzzzz
regionalCurrency=GBP
firstDayOverride=MONDAY
zoneFromExtension=America/New_York
zeroDigit=true
localizedZeroDigit=true
```

Các giá trị getter cho thấy consumer thực sự dùng các extension: Currency chọn GBP dù Locale country vẫn US, WeekFields xét `fw`, DateTimeFormatter xét `tz`, DecimalStyle xét `nu`. Tuy vậy, dữ liệu locale/timezone của JDK hoặc runtime image `jlink` có thể khác; với sản phẩm cần chính xác, kiểm thử trên môi trường triển khai thật.

## 13. `Locale.Builder` nhận key hợp cú pháp không bảo đảm tiêu thụ

```java
var locale = new java.util.Locale.Builder()
        .setLanguage("en")
        .setRegion("US")
        .setUnicodeLocaleKeyword("zz", "abc")
        .build();
```

`Locale.Builder.setUnicodeLocaleKeyword` kiểm tra dạng key/type, chuẩn hóa chữ thường và lưu. Nó **không** kiểm tra tất cả dịch vụ Java đã có hành vi cho `zz` hay `abc`. Khi `type == null`, Builder xóa keyword; khi type là `""`, có thể biểu diễn key có mặt nhưng không có type.

Nếu key sai dạng, ví dụ `"z"` chỉ một ký tự, Builder ném `IllformedLocaleException`. Đây là lỗi **cú pháp**; khác với một key/type hợp cú pháp nhưng không được API cụ thể hỗ trợ.

### 13.1. Chương trình hoàn chỉnh: `BuilderStorageDemo.java`

```java
import java.util.Currency;
import java.util.IllformedLocaleException;
import java.util.Locale;
import java.util.TreeSet;

public class BuilderStorageDemo {
    public static void main(String[] args) {
        var config = new Locale.Builder()
                .setLanguage("en")
                .setRegion("US")
                .setUnicodeLocaleKeyword("zz", "abc")
                .build();

        System.out.println("stored="
                + config.getUnicodeLocaleType("zz"));
        System.out.println("unchangedCurrency="
                + Currency.getInstance(config).getCurrencyCode());

        var langTag = Locale.forLanguageTag(
                "en-US-u-ca-japanese-x-demo");

        System.out.println("extensionKeys="
                + new TreeSet<>(langTag.getExtensionKeys()));
        System.out.println("privateUse="
                + langTag.getExtension(Locale.PRIVATE_USE_EXTENSION));

        try {
            new Locale.Builder()
                    .setUnicodeLocaleKeyword("z", "abc");
        } catch (IllformedLocaleException ex) {
            System.out.println("invalidKey="
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Chạy:

```bash
javac --release 17 BuilderStorageDemo.java
java BuilderStorageDemo
```

Stdout:

```text
stored=abc
unchangedCurrency=USD
extensionKeys=[u, x]
privateUse=demo
invalidKey=IllformedLocaleException
```

`stored=abc` chứng minh metadata lưu đúng. `unchangedCurrency=USD` cho thấy trong tình huống này consumer Currency không thay đổi hành vi chỉ vì có `zz`. `getExtensionKeys()` chứa `u`/`x` ở cấp ngoài; `ca` là Unicode key bên trong `u`. `privateUse=demo` cũng không đồng nghĩa key định dạng nào đã được dùng.

### 13.2. Validate language tag nhận từ bên ngoài

`Locale.forLanguageTag(String)` có quy tắc lenient khi gặp một tag ill-formed, có thể bỏ các phần không hợp lệ. Nếu cần báo lỗi ngay khi config không đúng cú pháp, cân nhắc:

```java
// Đoạn minh họa trong method với inputTag đã được khai báo:
var strict = new java.util.Locale.Builder()
        .setLanguageTag(inputTag)
        .build();
```

Builder có thể ném `IllformedLocaleException`. Dù strict validation thành công, bạn **vẫn chưa** biết các consumer có thực hiện key/type trong tag hay không.

## 14. Các khóa khác: đừng suy diễn theo Unicode LDML

Unicode LDML còn nhiều key như:

- `co`: loại collation.
- `kn`: numeric collation.
- `kf`: ưu tiên chữ hoa/chữ thường trong collation.
- `hc`: sở thích chu kỳ giờ.
- `ms`: hệ đo lường.
- `cf`: dạng biểu diễn currency.

Locale có thể biểu diễn nhiều key/type đúng cú pháp; nhưng điều đó không khiến:

- `String.compareTo` tự xử lý `co` hoặc `kn`.
- Mọi `Collator` trên mọi JDK/provider hỗ trợ mọi type `co`.
- `DateTimeFormatter.ofPattern("HH:mm")` tự đổi thành 12 giờ chỉ nhờ `hc=h12`.
- Mọi thư viện bên thứ ba có tham số Locale áp toàn bộ keys giống nhau.

Nếu sản phẩm cần quy tắc collation cụ thể, hãy xem tài liệu `Collator` và locale provider (hoặc thư viện có hợp đồng rõ), sau đó test chuỗi cần sắp xếp. Không biến một giá trị metadata thành lời hứa về thứ tự sort mà code chưa hiện thực.

## 15. Dữ liệu locale/provider và tính portable

Hành vi định dạng còn phụ thuộc:

- Phiên bản JDK và dữ liệu CLDR.
- Locale data provider/Service Provider Interface.
- Runtime image được tối giản, chẳng hạn bằng `jlink`.
- Giá trị type cụ thể có được hỗ trợ hay không.
- Các option ghi đè của formatter, ví dụ `withZone`, `withChronology`, `withDecimalStyle`.
- Thứ tự gọi `localizedBy` và các `withXxx`.

Vì vậy, dù Javadoc nói consumer hiểu một key, không có nghĩa mọi JDK/runtime có sẵn dữ liệu cho mọi locale/type do người dùng nghĩ ra. Hãy kiểm thử **runtime phát hành**, giữ fallback rõ ràng khi metadata hoặc yêu cầu định dạng không được hỗ trợ.

Không khuyến nghị sửa default Locale toàn JVM chỉ để hiển thị một người dùng:

```java
var userPreference = java.util.Locale.forLanguageTag(
        "en-US-u-nu-thai");
```

Tạo `userPreference` **không đổi** `Locale.getDefault()`. Muốn áp sở thích này, hãy truyền nó đến consumer thích hợp. Thay default toàn tiến trình có thể ảnh hưởng chức năng/thread khác.

## 16. Kiểm thử hai tầng: metadata và consumer

**Tầng A — metadata có được giữ?**

```java
var locale = java.util.Locale.forLanguageTag(
        "en-US-u-cu-eur");

if (!"eur".equals(locale.getUnicodeLocaleType("cu"))) {
    throw new AssertionError("Locale did not keep cu");
}
```

**Tầng B — consumer thực thi?**

```java
var currency = java.util.Currency.getInstance(locale);

if (!"EUR".equals(currency.getCurrencyCode())) {
    throw new AssertionError("Currency did not apply cu");
}
```

Hai đoạn chỉ minh họa trong method, không phải file độc lập. Chỉ qua tầng A thì UI có thể vẫn định dạng sai; tầng B mới chứng minh method cụ thể đã áp giá trị. Ngoài Currency, có thể kiểm:

- `WeekFields.of(locale).getFirstDayOfWeek()`.
- `Chronology.ofLocale(locale).getId()`.
- `DateTimeFormatter.getChronology()`, `getZone()`, `getDecimalStyle()` sau `localizedBy`.
- Giá trị format của `NumberFormat` theo một tập test phù hợp dữ liệu locale hiện có.

Khi không cần kiểm tra chính biểu tượng tiền tệ hoặc tên tháng, tránh assert cứng chuỗi output phụ thuộc CLDR. Những getter rõ thuộc tính thường dễ bảo trì hơn. Nếu chuỗi output là hợp đồng sản phẩm, hãy chọn chính sách kiểm thử snapshot tương ứng version.

## 17. Lỗi hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “`Locale` lưu `ca` nên mọi formatter dùng calendar ấy.” | Metadata không buộc consumer tự áp; `withLocale` khác `localizedBy` |
| “Java 10 mới hỗ trợ cú pháp `-u-`.” | Cú pháp đã có trước; Java 10 mở rộng API tiêu thụ |
| “Builder chấp nhận key thì JDK có hàm xử lý.” | Builder xác minh well-formed, không bảo đảm semantics |
| “`getUnicodeLocaleKeys()` có thứ tự cố định.” | Không dựa vào thứ tự Set; dùng TreeSet để in |
| “`getExtensionKeys()` trả `ca`, `nu`.” | Nó trả singleton như `u`/`x` |
| “Key có type rỗng là vắng mặt.” | Type `""` khác `null` |
| “`rg` tự đổi `Locale.getCountry()`.” | Base country không đổi, consumer xét region override |
| “`cu` biến số tiền USD thành EUR.” | Localization không thực hiện chuyển đổi tỷ giá nghiệp vụ |
| “`fw` đổi ngày của LocalDate.” | WeekFields/Calendar dùng quy tắc đầu tuần |
| “`tz` đổi múi giờ mặc định JVM.” | Không; consumer/ZoneId config tường minh |
| “`nu` làm `Integer.toString` tự dùng chữ số Thái.” | Không; dùng formatter có hỗ trợ |
| “`withLocale` giống `localizedBy`.” | `localizedBy` áp thêm chronology/decimal/zone theo extension |
| “Mọi `co`/`hc` type đều được mọi JDK hỗ trợ.” | Không; xem tài liệu consumer và provider |
| “Tag parse được là format chắc chắn đúng.” | Parse, lưu, tiêu thụ, render là các bước riêng |
| “Một ảnh chụp format đúng trên JDK A bảo đảm JDK B giống hệt.” | Locale data có thể khác phiên bản/provider |

## 18. Bài tập có đáp án

### Bài 1 — Currency

```java
var l = java.util.Locale.forLanguageTag("en-US-u-cu-eur");
System.out.println(l.getUnicodeLocaleType("cu"));
System.out.println(
        java.util.Currency.getInstance(l).getCurrencyCode());
```

**Đáp án:** `eur` rồi `EUR`. Dòng đầu là metadata; dòng sau là consumer.

### Bài 2 — Key lạ

```java
var l = java.util.Locale.forLanguageTag("en-US-u-zz-abc");
System.out.println(l.getUnicodeLocaleType("zz"));
```

**Đáp án:** `abc`, nhưng không chứng minh một formatter nào sẽ hiểu `zz`.

### Bài 3 — Region override

```java
var l = java.util.Locale.forLanguageTag(
        "en-US-u-rg-gbzzzz");
```

**Đáp án:** `l.getCountry()` vẫn `US`; `Currency.getInstance(l)` có thể dùng `rg` để lấy GBP như ví dụ. Không tự sửa country field.

### Bài 4 — `withLocale` hay `localizedBy`?

```java
var l = java.util.Locale.forLanguageTag(
        "ja-JP-u-ca-japanese");
var f = java.time.format.DateTimeFormatter
        .ofPattern("G y")
        .withLocale(l);
```

**Đáp án:** `f.getLocale()` có `ca=japanese`, nhưng `f.getChronology()` vẫn `null` trong ví dụ. Nếu muốn áp lịch, dùng `localizedBy(l)` hoặc `withChronology(...)` theo thiết kế.

### Bài 5 — First day of week

```java
var monday = java.util.Locale.forLanguageTag(
        "en-US-u-fw-mon");
```

**Đáp án:** `WeekFields.of(monday).getFirstDayOfWeek()` trả `MONDAY`. Không thay `LocalDate.getDayOfWeek()`.

### Bài 6 — Unicode keys và extension keys

```java
var l = java.util.Locale.forLanguageTag(
        "en-US-u-ca-japanese-x-demo");
```

**Đáp án:** `getExtensionKeys()` trả tập gồm `u`, `x`, còn `getUnicodeLocaleKeys()` gồm `ca`. `x-demo` là private-use.

### Bài 7 — Type rỗng

```java
var l = java.util.Locale.forLanguageTag("en-US-u-kn");
```

**Đáp án:** `getUnicodeLocaleType("kn")` là `""`, không phải `null`. Với `"cu"` không khai báo, kết quả là `null`.

### Bài 8 — Key `hc`

Tạo `Locale.Builder().setUnicodeLocaleKeyword("hc","h23")`. Điều đó đã bảo đảm mọi formatter dùng 24 giờ?

**Đáp án:** chưa. Builder lưu key/type hợp cú pháp, còn API định dạng phải có hợp đồng hỗ trợ `hc`. Với yêu cầu bắt buộc, chọn format cụ thể.

### Bài 9 — Test metadata có đủ không?

`getUnicodeLocaleType("cu")` trả `eur`. Có thể kết luận màn hình đã dùng Euro chưa?

**Đáp án:** không. Cần gọi consumer Currency/formatter thật và kiểm tra output.

### Bài 10 — Múi giờ

`Locale.forLanguageTag("en-US-u-tz-usnyc")` có đổi `ZoneId.systemDefault()` không?

**Đáp án:** không; chỉ tạo Locale chứa preference. `DateTimeFormatter.localizedBy` có thể áp extension, hoặc code dùng `ZoneId` tường minh.

## 19. Checklist ứng dụng

1. Xác định bạn đang kiểm tra **metadata** hay **hành vi**.
2. Xác nhận key tồn tại bằng `getUnicodeLocaleType` khi cần.
3. Đọc Javadoc của **consumer cụ thể**.
4. Phân biệt `u`/`x` (extension singleton) với `ca`/`nu` (Unicode keys).
5. Phân biệt type rỗng và key không có.
6. Validate BCP 47 tag ở ranh giới input khi cần.
7. Không suy từ Builder rằng một cặp key/type đã có feature.
8. Dùng `withLocale` hay `localizedBy` đúng mục đích.
9. Kiểm tra chronology/zone/decimal style của formatter khi quan trọng.
10. Xác định Currency và region override theo hợp đồng.
11. Với `fw`, dùng WeekFields/Calendar có hỗ trợ.
12. Với `co`, `hc`, `kn`, đọc docs provider, không đoán.
13. Có fallback nếu runtime không hỗ trợ type/locale data.
14. Không sửa default Locale toàn tiến trình chỉ vì cấu hình một user.
15. Tách currency/zone/instant của nghiệp vụ khỏi lựa chọn hiển thị.
16. Test ít nhất hai tầng: tag được lưu và consumer đã dùng.
17. Không đóng đinh output CLDR khi phiên bản dữ liệu có thể thay đổi.
18. Test trên JDK/runtime image sẽ triển khai.

**Kết luận:** Unicode locale extension trong `Locale` là **dữ liệu sở thích được lưu**. Các hàm đọc metadata không thực hiện định dạng. Java 10 (JEP 314) đưa thêm các khóa `cu`, `fw`, `rg`, `tz` vào nhiều consumer liên quan và cung cấp `DateTimeFormatter.localizedBy`. Muốn tính năng i18n đúng, cần **chọn API có hỗ trợ, xác minh hành vi trên runtime và xử lý key/type chưa hỗ trợ theo một chính sách rõ ràng**.

### Tài liệu chính thức

- [Locale — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html)
- [Locale.Builder — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.Builder.html)
- [JEP 314 — Additional Unicode Language-Tag Extensions](https://openjdk.org/jeps/314)
- [DateTimeFormatter — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Currency — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Currency.html)
- [WeekFields — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/WeekFields.html)
- [NumberFormat — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html)
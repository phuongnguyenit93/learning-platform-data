# Locale SPI: Kiểm thử tính nhất quán của số và tên hiển thị trong Java

## 1. Mục tiêu và tình huống thực tế

Khi ứng dụng Java phục vụ nhiều ngôn ngữ, **cùng một `Locale`** có thể được dùng cho hai loại kết quả khác nhau:

1. **Biểu diễn số**: số thập phân, dấu phân nhóm, dấu thập phân, tiền tệ, phần trăm, và cách parse từ text trở lại số.
2. **Tên hiển thị**: tên ngôn ngữ, quốc gia/vùng, script, variant, và tên đầy đủ của locale hiển thị cho người dùng.

Trong JDK hiện đại, những dữ liệu này thường lấy từ **CLDR**. Java cũng cho phép cài đặt **Locale Service Provider Interface (Locale SPI)** để cung cấp quy tắc riêng theo locale. Nếu cấu hình hoặc đóng gói không nhất quán, một UI có thể lấy cách format số từ provider A nhưng tên ngôn ngữ lại từ provider B hoặc CLDR, khiến một bộ kiểm thử đơn lẻ tưởng đã thành công nhưng trải nghiệm thực tế lại pha trộn.

**Bài này trả lời:** Làm sao kiểm tra những **number formats** và **localized display names** có đi qua đúng nguồn dữ liệu locale theo chính sách ứng dụng; làm sao phân biệt “SPI đã cài” với “SPI đã được JDK chọn”; và làm sao thiết kế tests bền vững khi JDK/CLDR được nâng cấp?

Ví dụ cụ thể cài hai providers:

- `java.text.spi.NumberFormatProvider`: định dạng số cho locale thử nghiệm `zz-ZZ` theo mẫu `12_345~67` (dấu nhóm `_`, dấu thập phân `~`).
- `java.util.spi.LocaleNameProvider`: hiển thị tên `vi` và `VN` bằng các chuỗi sentinel `Lang-vi`, `Region-VN` khi **display locale** là `zz-ZZ`.

Đây là **locale tổng hợp chỉ dùng cho test**, không phải một locale tự nhiên mà người dùng nên chọn. Việc sử dụng sentinel giúp test chứng minh chính xác **provider nào** được chọn, thay vì so sánh cứng những bản dịch CLDR có thể thay đổi theo release.

Một chương trình Java 17+ với hai provider implementation, hai service files và runner chạy trong **hai JVM riêng** đã được kiểm thử trên OpenJDK 24: mode `SPI,CLDR` có **14/14 assertions PASS** khi chạy từ class directory và từ JAR; mode `CLDR` có **7/7 assertions PASS** và cố ý không dùng các sentinel của SPI.

### Sau bài học, bạn có thể

- Phân biệt `LocaleServiceProvider`, `NumberFormatProvider`, `LocaleNameProvider` và các SPI liên quan.
- Hiểu `java.locale.providers=SPI,CLDR`, thứ tự chọn provider, default `CLDR` và lý do không chỉnh property sau khi khởi tạo.
- Đăng ký SPI trên **classpath** bằng `META-INF/services`, đóng gói JAR và xác nhận service visible.
- Phân biệt **locale của nội dung** với **locale dùng để hiển thị tên**, cùng hai category `Locale.Category.FORMAT` và `Locale.Category.DISPLAY`.
- Kiểm thử number format **và parse**, các factory number/integer/currency/percent, display language/country/name, fallback khi locale không hỗ trợ.
- Chẩn đoán hiện tượng mixed provider, thiếu service descriptor, chưa bật SPI, phụ thuộc CLDR hoặc sai separators tiền tệ.
- Viết tests theo **hợp đồng dữ liệu sản phẩm**, không ép cách format của toàn bộ JDK/CLDR phải mãi mãi giống một phiên bản.

## 2. Locale SPI là gì và vì sao còn quan trọng?

`java.util.spi.LocaleServiceProvider` là superclass cho các provider của dịch vụ locale-sensitive trong `java.text` và `java.util`. Nó cung cấp **tập locales mà provider hỗ trợ** và hỗ trợ xác định một locale cụ thể có được provider phục vụ hay không.

Các SPI liên quan:

| SPI | Dữ liệu/dịch vụ chịu trách nhiệm | API người dùng quan sát |
| --- | --- | --- |
| `NumberFormatProvider` | Tạo number, integer, currency, percent formatters | `NumberFormat.getNumberInstance(locale)` và các factory liên quan |
| `DecimalFormatSymbolsProvider` | Decimal/grouping/percent/monetary symbols | `DecimalFormatSymbols.getInstance(locale)` |
| `LocaleNameProvider` | Tên ngôn ngữ, vùng, script, variant, một số Unicode extension names | `Locale#getDisplayLanguage(displayLocale)`, `getDisplayCountry(...)`, `getDisplayName(...)` |
| `CurrencyNameProvider` | Tên và ký hiệu tiền tệ theo locale | `Currency#getDisplayName(locale)`, `getSymbol(locale)` |
| `DateFormatProvider` | Date/time formatter factories | `DateFormat.getDateInstance(..., locale)` |
| `DateFormatSymbolsProvider` | Ký hiệu tháng, ngày, era... | `DateFormatSymbols.getInstance(locale)` |
| `CalendarNameProvider` | Tên calendar fields | Các API calendar display names |
| `TimeZoneNameProvider` | Tên múi giờ | `TimeZone.getDisplayName(...)` |
| `CollatorProvider` | Collation cho thứ tự text | `Collator.getInstance(locale)` |
| `BreakIteratorProvider` | Phân đoạn text | `BreakIterator.getWordInstance(locale)` |

**Không phải một provider duy nhất kiểm soát toàn bộ i18n.** Ví dụ `NumberFormatProvider` không tự đổi tên `Locale.getDisplayLanguage(...)`; cần `LocaleNameProvider` cho tên đó. Ngược lại, một `LocaleNameProvider` không làm thay đổi grouping separator của `NumberFormat`.

`NumberFormatProvider` tạo **formatter instances**. `DecimalFormatSymbolsProvider` quản lý **symbol data** được lấy từ factories của `DecimalFormatSymbols`. Chúng là **hai hợp đồng SPI khác nhau**. Một implementation có thể tạo `DecimalFormatSymbols` thủ công như demo, nhưng điều đó **không biến** provider đó thành `DecimalFormatSymbolsProvider`.

### Java hiện đại: CLDR là mặc định

Theo Java SE 26 Javadoc, giá trị mặc định của `java.locale.providers` tương đương:

```text
java.locale.providers=CLDR
```

Khi ứng dụng muốn các classpath Locale SPIs được dùng, **phải bật `SPI` tường minh**, ví dụ:

```bash
java '-Djava.locale.providers=SPI,CLDR' -cp app.jar demo.app.LocaleConsistencyDemo spi
```

Cấu hình này nói: **ưu tiên SPI, nếu không có dịch vụ/locale phù hợp thì xét CLDR**. Dùng `CLDR,SPI` có ý nghĩa khác khi cả hai hỗ trợ locale; không giả định custom SPI luôn được ưu tiên chỉ vì service file tồn tại.

`HOST` là một provider tùy hệ điều hành/JDK implementation, không phải mọi môi trường đều có. `JRE`/`COMPAT` từng mang dữ liệu locale tương thích cũ, **đã bị loại khỏi JDK 23 trở lên**: không nên dùng chúng để khắc phục những khác biệt format trong dự án mới.

**Không sửa `java.locale.providers` bằng `System.setProperty(...)` giữa lúc chương trình đang chạy** rồi mong tất cả formatter đang tồn tại hoặc runtime lookup đổi ngay. Theo hợp đồng, thứ tự providers được đọc và cache khi `LocaleServiceProvider` khởi tạo; đặt property trên **java launcher** và tạo một **JVM mới** cho mỗi cấu hình cần test.

Nguồn chính thức: [LocaleServiceProvider Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/spi/LocaleServiceProvider.html); [JDK 26 Supported Locales](https://www.oracle.com/java/technologies/javase/jdk26-supported-locales.html).

## 3. Ba điều dễ bị nhầm: locale input, locale display, provider source

Hãy tách ít nhất ba biến:

1. **Content locale:** Ví dụ object `Locale.forLanguageTag("vi-VN")` mô tả ngôn ngữ/vùng đang được nêu tên.
2. **Display locale:** Ngôn ngữ/vùng mà **người xem** muốn dùng để đọc tên của content locale. Ví dụ `Locale.ENGLISH` cho ra tên tiếng Anh “Vietnamese”, “Vietnam”.
3. **Provider source:** CLDR, SPI hoặc HOST được JDK chọn để thực thi một dịch vụ locale-sensitive cụ thể.

Ví dụ:

```java
Locale subject = Locale.forLanguageTag("vi-VN");
Locale displayLocale = Locale.ENGLISH;

String language = subject.getDisplayLanguage(displayLocale);
String country = subject.getDisplayCountry(displayLocale);
String composed = subject.getDisplayName(displayLocale);
```

Ở đây `subject` là **ngôn ngữ đang được mô tả**; `displayLocale` là **ngôn ngữ được dùng cho nhãn hiển thị**. Nếu truyền nhầm `subject` làm display locale, UI có thể hiển thị tên tiếng Việt thay vì tiếng Anh.

Với formatting:

```java
Locale formatLocale = Locale.forLanguageTag("vi-VN");
NumberFormat numbers = NumberFormat.getNumberInstance(formatLocale);
String text = numbers.format(12345.67);
```

Đó là **format locale** cho số, không nhất thiết trùng display locale của tên. Một app tài chính có thể cố ý dùng:
- `Locale.US` cho formatting amounts theo hợp đồng của CSV hoặc backend.
- `Locale.forLanguageTag("vi-VN")` cho labels người dùng.

Đây **không phải bug** nếu đã có policy. “Nhất quán” không có nghĩa buộc format và display locale luôn là cùng object; nó có nghĩa **mọi thành phần tuân thủ cùng chính sách lựa chọn locale/provider đã định**.

### Hai category default locale

`Locale` có:

```java
Locale formatDefault =
        Locale.getDefault(Locale.Category.FORMAT);
Locale displayDefault =
        Locale.getDefault(Locale.Category.DISPLAY);
```

Các factory không có locale explicit có thể dùng những defaults khác nhau: `NumberFormat.getNumberInstance()` dùng **FORMAT**, còn `Locale#getDisplayLanguage()` không tham số dùng **DISPLAY**.

Trong ứng dụng cần kết quả lặp lại trên CI hoặc backend đa người dùng, **truyền explicit locale** cho từng API thay vì ngầm phụ thuộc environment default. Test nên ghi/khẳng định cả hai categories nếu kiến trúc thật dựa vào default locale.

## 4. Cách Locale SPI lookup hoạt động

Một luồng đơn giản hóa:

```text
Ứng dụng gọi NumberFormat.getNumberInstance(locale)
                      │
                      ▼
     JDK đọc thứ tự locale providers (startup)
                      │
              SPI, CLDR, ...
                      │
       ┌──────────────┴──────────────┐
       ▼                             ▼
 SPI provider phù hợp?          Nếu không có
       │                             │
       ▼                             ▼
 NumberFormatProvider         CLDR / candidate fallback
   getNumberInstance                  │
       │                              │
       └──────────────┬───────────────┘
                      ▼
               NumberFormat instance

Ứng dụng gọi someLocale.getDisplayLanguage(displayLocale)
                      │
                      ▼
           LocaleNameProvider / CLDR
                      │
                      ▼
                Display name text
```

Chọn nhà cung cấp **theo dịch vụ**. Provider cho số và provider cho tên có thể độc lập: nếu bạn chỉ đăng ký `NumberFormatProvider`, `Locale#getDisplayLanguage` không tự được custom.

Tầng `LocaleServiceProvider` có:

```java
Locale[] getAvailableLocales();
boolean isSupportedLocale(Locale locale);
```

`getAvailableLocales` là hợp đồng công bố tập locale được hỗ trợ. `isSupportedLocale` có default behavior xét locale, thường không xét Unicode locale extensions khi dùng mặc định. Nếu cần chính sách khác với extensions như `u-nu-latn`, có thể phải override theo Javadoc.

**Khi provider không hỗ trợ locale**, Java có thể thử candidate locale/parent rồi fallback theo order. `LocaleNameProvider` còn có quyền trả `null` cho một **tên cụ thể không biết dịch**, ngay cả khi nó hỗ trợ display locale. Vì vậy “LocaleNameProvider có mặt” **không** có nghĩa mọi language/country/script/variant đều được custom.

### Dịch vụ được công bố, không tự chạy tùy tiện

Một class kế thừa `NumberFormatProvider` nhưng chỉ được compile vào JAR **chưa đủ**. Trong classpath deployment cần có file `META-INF/services/java.text.spi.NumberFormatProvider` chứa tên implementation. Với `LocaleNameProvider` cần một descriptor riêng.

Ngoài ra, dù `ServiceLoader` thấy implementation, `java.locale.providers=CLDR` vẫn có thể làm JDK **không chọn SPI**. Đây là nội dung trọng tâm trong integration test.

## 5. NumberFormatProvider và hợp đồng số

`java.text.spi.NumberFormatProvider` cung cấp các factories:

- `getNumberInstance(Locale)`: số thông thường.
- `getIntegerInstance(Locale)`: số nguyên.
- `getCurrencyInstance(Locale)`: dạng tiền tệ.
- `getPercentInstance(Locale)`: phần trăm.
- `getCompactNumberInstance(Locale, NumberFormat.Style)`: API cho compact numbers, với implementation/default behavior riêng cần test nếu sản phẩm sử dụng.

Trong demo, các factories trả `DecimalFormat` đã được cấu hình bằng `DecimalFormatSymbols` cụ thể. Chọn locale synthetic `zz-ZZ` nhằm tạo **expected output độc lập CLDR**:

```text
12345.67 → 12_345~67
1200     → 1_200
0.25     → 25%
```

Lưu ý: đây là **định dạng thử nghiệm**, không phải mô tả đúng chuẩn ngôn ngữ của quốc gia thực tế nào. Vì vậy người học có thể kiểm tra “provider đã được chọn” mà không gắn golden output vào một locale CLDR có thể thay đổi.

### Format khác Parse

`NumberFormat.format(...)` chuyển số thành text; `NumberFormat.parse(...)` chuyển text về `Number`. Hai phương thức có thể hoạt động khác nhau trên malformed input, trailing content, grouping, decimals và strictness.

`parse(String)` không nên được dùng như một phép kiểm tra **toàn bộ input luôn hợp lệ** nếu không có xác nhận đã tiêu thụ hết ký tự. Trong test:

```java
NumberFormat fmt = NumberFormat.getNumberInstance(locale);
String output = fmt.format(12345.67);

ParsePosition position = new ParsePosition(0);
Number parsed = fmt.parse(output, position);

boolean complete =
        parsed != null
        && position.getIndex() == output.length();
```

Đoạn này minh họa ở trong method có `locale`, imports `NumberFormat`, `ParsePosition`. Khi parse số thực, có thể so bằng tolerance nếu input dùng `double` và format có rounding. Đối với tiền, dùng `BigDecimal`/cấu hình parse chính xác theo domain; **không** dùng phép so double rồi kết luận giá trị tiền chính xác.

### Currency symbols có hai cặp separator

Một chi tiết đặc biệt quan trọng được kiểm thử: `DecimalFormatSymbols` chứa **grouping/decimal separators thường**, và còn chứa **monetaryGroupingSeparator/monetaryDecimalSeparator** dành cho currency pattern.

```java
DecimalFormatSymbols symbols =
        DecimalFormatSymbols.getInstance(Locale.ROOT);

symbols.setGroupingSeparator('_');
symbols.setDecimalSeparator('~');

// Cũng phải set riêng cho currency:
symbols.setMonetaryGroupingSeparator('_');
symbols.setMonetaryDecimalSeparator('~');
```

Nếu chỉ set hai symbol thường, `new DecimalFormat("¤#,##0.00", symbols)` vẫn có thể dùng dấu `,` và `.` cho phần tiền tệ. Đây không phải lỗi NumberFormat SPI mà là **hợp đồng có hai nhóm separators khác nhau**. API `setMonetaryGroupingSeparator` có từ Java 15 nên ví dụ dùng được với `--release 17`.

### CurrencyNameProvider là lớp khác

`NumberFormat.getCurrencyInstance(locale)` có thể hiển thị monetary amount, nhưng tên/symbol cho currency cụ thể còn liên quan đến `Currency`, `CurrencyNameProvider` và currency rules. Khi format tiền trong production, hãy xác định ISO 4217 currency code rõ (chẳng hạn `Currency.getInstance("VND")`), không đoán currency chỉ từ locale. Locale synthetic `zz-ZZ` của demo không thuộc một quốc gia tiền tệ thực tế; symbol `¤` dùng ở đây chỉ minh họa factory behavior.

## 6. LocaleNameProvider và hợp đồng tên hiển thị

`java.util.spi.LocaleNameProvider` có các method:

| Method | Ví dụ query | Ý nghĩa |
| --- | --- | --- |
| `getDisplayLanguage(languageCode, displayLocale)` | `"vi"` + `zz-ZZ` | Tên ngôn ngữ viết theo display locale |
| `getDisplayCountry(countryCode, displayLocale)` | `"VN"` + `zz-ZZ` | Tên vùng/quốc gia theo display locale |
| `getDisplayScript(scriptCode, displayLocale)` | `"Latn"` + `zz-ZZ` | Tên script theo display locale |
| `getDisplayVariant(variant, displayLocale)` | Variant code + `zz-ZZ` | Tên variant |
| `getDisplayUnicodeExtensionKey(...)` | Unicode locale extension | Tên extension key khi có hỗ trợ |
| `getDisplayUnicodeExtensionType(...)` | Unicode locale extension type | Tên extension type khi có hỗ trợ |

Hai method **abstract bắt buộc** `getDisplayLanguage` và `getDisplayCountry` (cùng `getDisplayVariant`) cần được hiện thực. Một số method khác có default implementation trả `null`. Provider có thể trả `null` cho name không có; điều đó không đồng nghĩa toàn bộ locale không được hỗ trợ.

**Tránh nhầm chiều tham số**:

```java
Locale subject = Locale.forLanguageTag("vi-VN");
Locale displayLocale = Locale.forLanguageTag("zz-ZZ");

String language = subject.getDisplayLanguage(displayLocale);
String country = subject.getDisplayCountry(displayLocale);
```

Runtime có thể gọi implementation với:
- `languageCode="vi", locale=zz-ZZ`.
- `countryCode="VN", locale=zz-ZZ`.

`displayLocale` không phải language đang được đặt tên. Nếu UI cần “Việt Nam” bằng tiếng Việt thì chọn display locale tiếng Việt, còn nếu cần “Vietnam” bằng tiếng Anh thì chọn display locale tiếng Anh; không nhất thiết trùng content locale.

### Tên ghép `getDisplayName`

`subject.getDisplayName(displayLocale)` ghép các tên language/script/country/variant và extension thành một nhãn. Dấu ngoặc, dấu phẩy hoặc punctuation có thể chịu ảnh hưởng locale data. Vì vậy test production nên kiểm tra **các thành phần ý nghĩa**, không hard-code mọi punctuation khi sản phẩm không quy định chính xác layout.

Demo dùng:

```java
subject.getDisplayName(displayLocale).contains("Lang-vi")
&& subject.getDisplayName(displayLocale).contains("Region-VN")
```

để chứng minh cả hai tên từ provider đã góp vào tên ghép, nhưng không đóng đinh separator của composed label.

## 7. Dự án Java 17+: hai provider và một test runner

Một layout classpath không cần Maven/Gradle:

```text
locale-spi-demo/
├── src/
│   └── demo/
│       ├── spi/
│       │   ├── TestNumberProvider.java
│       │   └── TestNameProvider.java
│       └── app/
│           └── LocaleConsistencyDemo.java
├── resources/
│   └── META-INF/
│       └── services/
│           ├── java.text.spi.NumberFormatProvider
│           └── java.util.spi.LocaleNameProvider
└── build/
    ├── classes/
    └── locale-spi-demo.jar
```

**Quan trọng:** Hai file trong `META-INF/services` là các **service descriptor text files**, không phải Java classes. File name là **fully qualified service type**, nội dung là **fully qualified concrete implementation class name**. Các file phải được đưa vào **classpath root của directory hoặc JAR**, không đặt dưới package `demo`.

Cả ba source files sau là **độc lập khi ghép đúng project** và đã được biên dịch thực tế bằng Java 17 target. Implementation cố ý nhỏ để tập trung vào lookup và test; provider sản xuất cần validate locale/code inputs và bao quát đầy đủ các tên/format mà sản phẩm tuyên bố hỗ trợ.

### 7.1. `src/demo/spi/TestNumberProvider.java`

```java
package demo.spi;

import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.text.spi.NumberFormatProvider;
import java.util.Locale;

public final class TestNumberProvider extends NumberFormatProvider {
    public static final Locale DEMO =
            Locale.forLanguageTag("zz-ZZ");

    @Override
    public Locale[] getAvailableLocales() {
        return new Locale[] { DEMO };
    }

    private static NumberFormat format(String pattern) {
        DecimalFormatSymbols x =
                DecimalFormatSymbols.getInstance(Locale.ROOT);

        x.setGroupingSeparator('_');
        x.setDecimalSeparator('~');
        x.setMonetaryGroupingSeparator('_');
        x.setMonetaryDecimalSeparator('~');
        x.setPercent('%');

        return new DecimalFormat(pattern, x);
    }

    @Override
    public NumberFormat getNumberInstance(Locale locale) {
        return format("#,##0.00");
    }

    @Override
    public NumberFormat getIntegerInstance(Locale locale) {
        NumberFormat f = format("#,##0");
        f.setParseIntegerOnly(true);
        return f;
    }

    @Override
    public NumberFormat getCurrencyInstance(Locale locale) {
        return format("\u00A4#,##0.00");
    }

    @Override
    public NumberFormat getPercentInstance(Locale locale) {
        return format("#,##0%");
    }
}
```

**Cách hoạt động:**

1. `DEMO` là locale `zz-ZZ` tổng hợp, giúp test custom provider dễ nhận diện.
2. `getAvailableLocales` chỉ công bố một locale. Trong ứng dụng production, hãy công bố chính xác các locales đã hỗ trợ.
3. `DecimalFormatSymbols.getInstance(Locale.ROOT)` lấy symbols nền ổn định và **chủ động override** các ký tự cần test.
4. Dùng cả `setMonetaryGroupingSeparator` và `setMonetaryDecimalSeparator` vì currency pattern có quy tắc separators riêng.
5. Các factory methods trả `NumberFormat` mới mỗi lần thay vì chia sẻ một instance mutable.
6. `\u00A4` trong pattern là Unicode **CURRENCY SIGN** (¤), ký tự đánh dấu vị trí currency trong `DecimalFormat` pattern. Nó không là một đơn vị tiền tệ thực tế.
7. `getIntegerInstance` đặt `parseIntegerOnly(true)` để mô phỏng semantics integer parsing trong fixture.
8. Các methods ở đây được JDK gọi qua SPI. Để làm provider tổng quát, cần thêm checks cho `null`/unsupported locale đúng contract, và quyết định cách thực thi compact formats.

**Đừng copy những dấu `_` và `~` này làm format chính thức cho Việt Nam**. Chúng chỉ là sentinel dễ phát hiện trong test.

### 7.2. `src/demo/spi/TestNameProvider.java`

```java
package demo.spi;

import java.util.Locale;
import java.util.spi.LocaleNameProvider;

public final class TestNameProvider extends LocaleNameProvider {

    @Override
    public Locale[] getAvailableLocales() {
        return new Locale[] { TestNumberProvider.DEMO };
    }

    @Override
    public String getDisplayLanguage(
            String code, Locale displayLocale) {
        return "Lang-" + code;
    }

    @Override
    public String getDisplayCountry(
            String code, Locale displayLocale) {
        return "Region-" + code;
    }

    @Override
    public String getDisplayVariant(
            String code, Locale displayLocale) {
        return "Variant-" + code;
    }

    @Override
    public String getDisplayScript(
            String code, Locale displayLocale) {
        return "Script-" + code;
    }
}
```

**Vì sao dùng các prefix `Lang-`, `Region-`?**

- Nó khiến test không phụ thuộc một bản dịch thật do CLDR hiện hành cung cấp.
- Nó chứng minh method nào được gọi mà không cần đoán ngôn ngữ tự nhiên.
- Nếu output vẫn là `Vietnamese`, `Vietnam`, có thể JDK đang dùng CLDR thay vì custom provider.
- Nó cho phép kiểm tra number provider và name provider **được chọn cùng nhau** khi cấu hình `SPI,CLDR`.

Implementation này minh họa một **test double**. Provider thực tế cần trả tên có nghĩa, chỉ nhận mã hợp lệ, tôn trọng `displayLocale` và có thể trả `null` cho name chưa được dịch để JDK thực hiện lookup/fallback. Không được để tiếng Anh kiểu `Lang-vi` vào UI production.

### 7.3. `resources/META-INF/services/java.text.spi.NumberFormatProvider`

Nội dung file (một dòng):

```text
demo.spi.TestNumberProvider
```

### 7.4. `resources/META-INF/services/java.util.spi.LocaleNameProvider`

Nội dung file:

```text
demo.spi.TestNameProvider
```

Hai files cần là plain text UTF-8; không viết JSON/XML, không thêm dấu ngoặc hay relative class path. Tên service file phân biệt package `java.text.spi` với `java.util.spi`.

Trong JAR, class loader phải thấy:

```text
META-INF/services/java.text.spi.NumberFormatProvider
META-INF/services/java.util.spi.LocaleNameProvider
demo/spi/TestNumberProvider.class
demo/spi/TestNameProvider.class
demo/app/LocaleConsistencyDemo.class
```

Nếu quên descriptors, source vẫn compile nhưng `ServiceLoader` và JDK locale SPI selection sẽ không tự tìm được các provider đó theo cách classpath tiêu chuẩn.

### 7.5. `src/demo/app/LocaleConsistencyDemo.java`

```java
package demo.app;

import demo.spi.TestNumberProvider;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.text.spi.NumberFormatProvider;
import java.util.Locale;
import java.util.ServiceLoader;
import java.util.spi.LocaleNameProvider;

public final class LocaleConsistencyDemo {
    private static int passed;

    private static void check(String label, boolean ok) {
        if (!ok) {
            throw new AssertionError("FAIL " + label);
        }
        System.out.println("PASS " + label);
        passed++;
    }

    public static void main(String[] args) {
        if (args.length != 1 ||
                (!args[0].equals("spi")
                && !args[0].equals("cldr"))) {
            throw new IllegalArgumentException(
                    "mode must be spi or cldr");
        }

        boolean spi = args[0].equals("spi");
        Locale custom = TestNumberProvider.DEMO;
        Locale subject = Locale.forLanguageTag("vi-VN");

        NumberFormat fmt =
                NumberFormat.getNumberInstance(custom);
        String text = fmt.format(12345.67);

        String language = subject.getDisplayLanguage(custom);
        String country = subject.getDisplayCountry(custom);

        check("explicit-locale",
                custom.toLanguageTag().equals("zz-ZZ"));

        check("service-number-installed",
                ServiceLoader.load(NumberFormatProvider.class)
                        .stream().anyMatch(p ->
                                p.type().getName().equals(
                                        "demo.spi.TestNumberProvider")));

        check("service-name-installed",
                ServiceLoader.load(LocaleNameProvider.class)
                        .stream().anyMatch(p ->
                                p.type().getName().equals(
                                        "demo.spi.TestNameProvider")));

        check("number-provider-selected",
                text.equals("12_345~67") == spi);

        check("name-provider-selected",
                (language.equals("Lang-vi")
                && country.equals("Region-VN")) == spi);

        if (spi) {
            ParsePosition pos = new ParsePosition(0);
            Number parsed = fmt.parse(text, pos);

            check("number-roundtrip",
                    parsed != null
                    && Math.abs(parsed.doubleValue() - 12345.67) < 1e-9
                    && pos.getIndex() == text.length());

            check("display-language",
                    language.equals("Lang-vi"));

            check("display-country",
                    country.equals("Region-VN"));

            check("display-name-composed",
                    subject.getDisplayName(custom)
                            .contains("Lang-vi")
                    && subject.getDisplayName(custom)
                            .contains("Region-VN"));

            check("integer-format",
                    NumberFormat.getIntegerInstance(custom)
                            .format(1200).equals("1_200"));

            check("currency-monetary-separators",
                    NumberFormat.getCurrencyInstance(custom)
                            .format(1234.5).contains("1_234~50"));

            check("percent-format",
                    NumberFormat.getPercentInstance(custom)
                            .format(0.25).equals("25%"));

            check("cldr-plain-fallback",
                    !NumberFormat.getNumberInstance(Locale.US)
                            .format(12345.67)
                            .equals("12_345~67"));

            check("default-categories-not-used",
                    !Locale.getDefault(Locale.Category.FORMAT)
                            .equals(custom)
                    && !Locale.getDefault(Locale.Category.DISPLAY)
                            .equals(custom));

        } else {
            check("cldr-number-no-spi",
                    !text.equals("12_345~67"));

            check("cldr-name-no-spi",
                    !language.equals("Lang-vi")
                    && !country.equals("Region-VN"));
        }

        System.out.println("mode=" + args[0]);
        System.out.println("number=" + text);
        System.out.println("language=" + language);
        System.out.println("country=" + country);
        System.out.println("passed=" + passed);
    }
}
```

**Cấu trúc test có chủ đích:**

- `ServiceLoader.load(...).stream()` kiểm tra **đã cài** đúng hai implementation trong classpath/JAR.
- `number-provider-selected` và `name-provider-selected` kiểm tra **JDK thực sự chọn** chúng qua API public.
- Tách mode `spi` và `cldr` không phải thay property trong một JVM, mà để test runner biết cấu hình JVM nào đã được launcher tạo.
- `ParsePosition` xác minh parser đọc **toàn bộ formatted text**, không chỉ tiền tố.
- `getDisplayName` chỉ kiểm tra các thành phần sentinel vì composed name punctuation có thể thay đổi.
- Currency test chỉ kiểm tra phần ký tự số giả lập; không giả định locale `zz-ZZ` có currency code hợp pháp.
- `Locale.US` dùng để chứng minh khi provider synthetic không hỗ trợ locale thật, JDK vẫn có fallback (thông qua CLDR).
- Không hard-code kết quả `Vietnamese` hay `Vietnam` trong assertion của CLDR-only mode, tránh coupling quá chặt với phiên bản CLDR.

### 7.6. Giải thích các assertions “nhất quán”

| Kiểm thử | Điều được bảo vệ |
| --- | --- |
| `service-number-installed` / `service-name-installed` | Provider files và classes được đóng gói, có thể discover |
| `number-provider-selected` | NumberFormat chọn đúng nguồn theo cấu hình JVM |
| `name-provider-selected` | Locale display names chọn nguồn theo cùng cấu hình |
| `number-roundtrip` | Formatter/parser nhất quán về giá trị và consume toàn bộ text |
| `display-language` / `display-country` | Hai thành phần tên không pha với CLDR |
| `display-name-composed` | Tên ghép bao gồm những thành phần được provider cung cấp |
| `integer-format` | Factory integer trả định dạng theo custom locale |
| `currency-monetary-separators` | Currency formatter dùng **monetary** decimal/grouping symbols |
| `percent-format` | `0.25` được thể hiện dạng phần trăm theo provider |
| `cldr-plain-fallback` | Locale không được custom hỗ trợ không nhận sentinel |
| `default-categories-not-used` | Test chọn explicit custom locale, không ngầm dùng defaults |
| `cldr-number-no-spi` / `cldr-name-no-spi` | Installed providers không bị chọn khi cấu hình chỉ CLDR |

**Đừng chỉ chạy `ServiceLoader` rồi kết luận tích hợp đúng.** Nó chứng minh JAR service declarations hợp lệ, nhưng không chứng minh JDK đang chọn SPI làm nguồn locale data.

## 8. Biên dịch, copy service descriptors và chạy (Linux/macOS)

Đặt terminal ở folder `locale-spi-demo`. Tạo output folder, compile cả ba Java files, rồi copy `META-INF` vào classpath root:

```bash
mkdir -p build/classes

javac --release 17 -encoding UTF-8 \
  -d build/classes \
  src/demo/spi/TestNumberProvider.java \
  src/demo/spi/TestNameProvider.java \
  src/demo/app/LocaleConsistencyDemo.java

cp -R resources/META-INF build/classes/

java '-Djava.locale.providers=SPI,CLDR' \
  -cp build/classes \
  demo.app.LocaleConsistencyDemo spi

java '-Djava.locale.providers=CLDR' \
  -cp build/classes \
  demo.app.LocaleConsistencyDemo cldr
```

**Tại sao phải copy?** `javac` không tự copy plain text service configuration files. Nếu thiếu `META-INF/services`, provider classes có thể có mặt nhưng JDK **không** đăng ký chúng là service providers.

**Tại sao chạy hai lần?** `java.locale.providers` được đọc lúc JDK locale services khởi tạo. Thử thay `System.setProperty(...)` trong cùng test process có thể không thay đổi provider selection. Mỗi command `java` khởi động một JVM mới với startup property khác nhau.

## 9. Lệnh tương đương trên Windows PowerShell

```powershell
New-Item -ItemType Directory -Path build/classes -Force |
    Out-Null

javac --release 17 -encoding UTF-8 -d build/classes src/demo/spi/TestNumberProvider.java src/demo/spi/TestNameProvider.java src/demo/app/LocaleConsistencyDemo.java

Copy-Item -LiteralPath resources/META-INF -Destination build/classes -Recurse

java '-Djava.locale.providers=SPI,CLDR' -cp build/classes demo.app.LocaleConsistencyDemo spi

java '-Djava.locale.providers=CLDR' -cp build/classes demo.app.LocaleConsistencyDemo cldr
```

Trong Windows PowerShell 5.1, đặt toàn bộ `-Djava.locale.providers=...` trong dấu nháy đơn để tránh phân tách bất ngờ. Dấu `,` trong property là thứ tự providers trong JVM, **không phải** dấu phân cách các classpath entries.

Nếu cần đặt nhiều JAR trong `-cp`, dùng `;` trên Windows và `:` trên Linux/macOS.

## 10. Stdout đã xác minh thực tế

### 10.1. Với `-Djava.locale.providers=SPI,CLDR`

Chương trình trên OpenJDK 24 in:

```text
PASS explicit-locale
PASS service-number-installed
PASS service-name-installed
PASS number-provider-selected
PASS name-provider-selected
PASS number-roundtrip
PASS display-language
PASS display-country
PASS display-name-composed
PASS integer-format
PASS currency-monetary-separators
PASS percent-format
PASS cldr-plain-fallback
PASS default-categories-not-used
mode=spi
number=12_345~67
language=Lang-vi
country=Region-VN
passed=14
```

**Đọc kết quả:** number format và tên hiển thị đều đến từ custom SPI; vì đã bật thứ tự `SPI,CLDR`, JDK chọn provider cho `zz-ZZ` và dùng fallback CLDR cho một locale khác mà provider không hỗ trợ.

### 10.2. Với `-Djava.locale.providers=CLDR`

Cùng JAR/classes và cùng hai service files, nhưng process khởi động với only CLDR, output trên OpenJDK 24:

```text
PASS explicit-locale
PASS service-number-installed
PASS service-name-installed
PASS number-provider-selected
PASS name-provider-selected
PASS cldr-number-no-spi
PASS cldr-name-no-spi
mode=cldr
number=12,345.67
language=Vietnamese
country=Vietnam
passed=7
```

**Lưu ý quan trọng:** Ba dòng `number=12,345.67`, `language=Vietnamese` và `country=Vietnam` là **quan sát trên môi trường thử nghiệm OpenJDK 24**, không phải một golden test bắt buộc với mọi JDK/CLDR/version/locale. Các assertions của mode `cldr` **chỉ yêu cầu không lấy sentinel**. Java 26 dùng phiên bản CLDR mới hơn Java 24; bản dịch và dấu phân nhóm có thể đổi theo thời gian.

`ServiceLoader` vẫn tìm thấy providers trong mode CLDR-only, nhưng public locale APIs không chọn chúng. Đây là minh chứng rõ nhất cho sự khác biệt **installed vs selected**.

## 11. Đóng gói JAR và kiểm thử lại artifact

Sau khi có `build/classes` chứa class files **và** `META-INF/services`:

```bash
jar --create --file build/locale-spi-demo.jar \
  -C build/classes .

jar --list --file build/locale-spi-demo.jar
```

Trong JAR cần có tối thiểu:

```text
demo/spi/TestNumberProvider.class
demo/spi/TestNameProvider.class
demo/app/LocaleConsistencyDemo.class
META-INF/services/java.text.spi.NumberFormatProvider
META-INF/services/java.util.spi.LocaleNameProvider
```

`jar --list` có thể có manifest/thư mục entries khác; đừng assert thứ tự. Kiểm tra service files **nằm đúng root**, không bị plugin shade đổi đường dẫn.

Chạy artifact đã package:

```bash
java '-Djava.locale.providers=SPI,CLDR' \
  -cp build/locale-spi-demo.jar \
  demo.app.LocaleConsistencyDemo spi
```

Kết quả đã kiểm thử: **14/14 PASS**, stdout giống phần 10.1. Không cần extract JAR ra filesystem. Test với JAR giúp phát hiện lỗi thường bị che khi chạy từ IDE: service resources thiếu trong final build output.

Trên Windows PowerShell:

```powershell
jar --create --file build/locale-spi-demo.jar -C build/classes .

java '-Djava.locale.providers=SPI,CLDR' -cp build/locale-spi-demo.jar demo.app.LocaleConsistencyDemo spi
```

**`java -cp ... MainClass` không đòi `Main-Class` trong manifest**. Lệnh `java -jar` thì có yêu cầu manifest riêng; demo cố ý dùng `-cp` để mô tả classpath lookup rõ ràng.

## 12. Vì sao cần cả NumberFormatProvider và LocaleNameProvider?

Giả sử ứng dụng tự cài `TestNumberProvider` và bỏ `TestNameProvider`. JDK vẫn có thể format theo sentinel `12_345~67` khi `SPI` ưu tiên, nhưng:

```java
subject.getDisplayLanguage(custom);
subject.getDisplayCountry(custom);
```

không được provider tên của bạn xử lý. Runtime có thể dùng CLDR/locale fallback, hoặc các tên thay thế của hệ thống.

Đây là tình trạng **mixed-provider**: một phần UI dùng dữ liệu custom, phần khác dùng CLDR. Nó không phải bug nội tại của JDK, nhưng có thể là **vi phạm yêu cầu sản phẩm** nếu bạn muốn bộ locale synthetic/custom được cung cấp đồng bộ.

Nếu ứng dụng chỉ cần quy tắc số riêng nhưng tên hiển thị vẫn theo CLDR, mixed-provider **có thể hoàn toàn hợp lệ**. Test nên mô tả chính sách:

```text
Policy A — ứng dụng custom locale:
NumberFormat -> SPI bắt buộc
Locale display name -> SPI bắt buộc

Policy B — ứng dụng chỉ sửa số:
NumberFormat -> SPI bắt buộc
Locale display name -> CLDR được phép

Policy C — không custom:
NumberFormat -> CLDR
Locale display name -> CLDR
```

“Nhất quán” là **đúng chính sách**, không phải cùng tên vendor cho mọi service bất kể mục đích.

### Provider nào còn phải xem xét?

Nếu sản phẩm format nhiều thứ, kiểm tra thêm:

- `DecimalFormatSymbolsProvider`: các symbols nếu ứng dụng gọi factory đó trực tiếp.
- `CurrencyNameProvider`: tên và ký hiệu tiền tệ hiển thị.
- `DateFormatProvider`, `DateFormatSymbolsProvider`: date/time.
- `CalendarNameProvider`, `TimeZoneNameProvider`: calendar/time zone names.
- `CollatorProvider`: sort names theo locale.
- `BreakIteratorProvider`: phân đoạn từ/câu.

Chỉ test một nhóm number/display names không chứng minh toàn bộ date/currency/collation stack đã thống nhất.

## 13. Tên hiển thị có thể fallback theo từng thành phần

Khi hỏi:

```java
Locale subject = Locale.forLanguageTag("vi-Latn-VN");
String label = subject.getDisplayName(displayLocale);
```

`getDisplayName` có thể kết hợp **language + script + country**. Một provider có thể biết display language nhưng không biết display script. Javadoc cho phép name provider trả `null` cho một item không dịch được; runtime có thể thử provider/locale fallback theo quy tắc.

Hãy test **từng thành phần**:

```java
String l = subject.getDisplayLanguage(displayLocale);
String s = subject.getDisplayScript(displayLocale);
String c = subject.getDisplayCountry(displayLocale);
String all = subject.getDisplayName(displayLocale);
```

Đây là đoạn minh họa, với `displayLocale` đã được xác định. Đừng chỉ assert `all.startsWith(...)` nếu nghiệp vụ cần chính xác **country** hoặc **script**. Các tên có thể dùng punctuation/locale grammar khác, nên test punctuation chỉ khi đó là yêu cầu UX.

### Language code và region code không phải “display name”

`subject.getLanguage()` thường trả code như `vi`. `subject.getCountry()` trả region như `VN`. `getDisplayLanguage(displayLocale)` và `getDisplayCountry(displayLocale)` trả **tên dành cho người dùng**, có thể khác theo provider và display locale.

Không sử dụng `getDisplayName` làm khóa dữ liệu ổn định trong DB hoặc API. Tên hiển thị có thể thay theo JDK/CLDR, locale hoặc chính sách dịch. Lưu định danh bằng `Locale.toLanguageTag()`/language tag đã chuẩn hóa theo contract.

## 14. Chọn explicit locale: FORMAT và DISPLAY categories

Một UI có thể hiển thị amount theo `Locale.Category.FORMAT` nhưng nhãn ngôn ngữ theo `Locale.Category.DISPLAY`. Hai default categories có thể được cấu hình độc lập.

```java
Locale f = Locale.getDefault(Locale.Category.FORMAT);
Locale d = Locale.getDefault(Locale.Category.DISPLAY);

NumberFormat amount = NumberFormat.getNumberInstance(f);
String name = Locale.FRANCE.getDisplayCountry(d);
```

Không nên viết:

```java
NumberFormat fmt = NumberFormat.getNumberInstance();
String label = Locale.FRANCE.getDisplayName();
```

rồi mặc định output sẽ giống nhau giữa developer laptop, Windows service và CI Linux. Những overload không tham số dùng defaults của runtime. Nếu yêu cầu là một canonical report, xuất file hay giao thức API cố định, truyền `Locale` tường minh ở cả hai bên.

### Bài kiểm tra consistency theo chính sách sản phẩm

Ví dụ policy của UI:
- Labels hiển thị theo `displayLocale` do profile người dùng chọn.
- Amount theo `formatLocale` do profile người dùng chọn.
- Tất cả custom locales phải được cả hai SPI hỗ trợ nếu đã bật feature flag.
- Với locale khác, fallback sang CLDR theo JVM config.

Test cần dùng **cùng cấu hình** xuyên suốt một request. Nhưng khi `formatLocale != displayLocale` là policy có chủ đích, test **không được coi đó là fail**.

## 15. Tính nhất quán của Format – Parse – Display

Một formatter được chọn đúng chưa đủ để khẳng định UI hoạt động đúng. Với một input amount `12345.67`, hãy test ba chiều:

1. **Format**: `format(12345.67)` trả sentinel dự kiến `12_345~67`.
2. **Parse**: `parse("12_345~67", pos)` trả số tương đương, và `pos.getIndex() == text.length()`.
3. **Display names**: locale name labels cho user thực sự đi qua provider mong muốn, không bị thay từ CLDR bất ngờ.

Đừng hiểu round-trip là yêu cầu **format rồi parse mọi BigDecimal cho ra cùng precision**. Format có thể làm tròn, cắt fraction digits, group digits, hoặc thêm ký hiệu tiền tệ. Hợp đồng test phải chỉ ra precision và rounding policy.

### Test inputs thường có giá trị

| Nhóm | Input | Điều cần kiểm tra |
| --- | --- | --- |
| Zero | `0` | Không có grouping không cần thiết |
| Negative | `-1234.5` | Dấu âm và separators phù hợp |
| Large | `123456789.25` | Grouping nhiều cấp ổn định |
| Fractions | `0.25` | Number vs percent factory có semantics khác |
| Currency | `1234.50` | Monetary separators, ISO currency policy |
| Boundary rounding | `1.005` hoặc BigDecimal variant | Rounding mode/precision rõ |
| Parse valid | `12_345~67` | Giá trị và full input consumption |
| Parse trailing | `12_345~67xyz` | Nếu strict input, phải reject tail |
| Parse wrong separator | `12,345.67` trong custom locale | Không im lặng nhận giá trị không mong muốn |
| Locale not supported by SPI | `Locale.US` | Fallback theo policy, không dùng custom sentinel |
| Display language | `vi` theo display locale custom | Dùng `Lang-vi` khi SPI được chọn |
| Display country | `VN` theo display locale custom | Dùng `Region-VN` khi SPI được chọn |
| Combined name | `vi-VN` | Chứa cả hai thành phần, punctuation không bị hard-code vô lý |

### ParsePosition rất quan trọng

Một số number parsers có thể phân tích **tiền tố hợp lệ** rồi dừng ở ký tự đầu tiên không hợp lệ. Nếu ứng dụng cần strict ingestion, phải xác nhận `ParsePosition.getIndex()` đã đến **cuối toàn bộ chuỗi**; đồng thời kiểm tra `parsed != null` và error index nếu cần.

Với API phiên bản mới hỗ trợ strict parsing settings, đối chiếu Javadoc của Java target. Demo biên dịch `--release 17` nên dùng phương pháp `ParsePosition` tương thích từ lâu, không dựa API mới hơn Java 17.

### Thread safety

`NumberFormat`/`DecimalFormat` là đối tượng **mutable**, không nên được dùng chung không đồng bộ giữa các request threads. Các factory của provider trong demo trả object mới theo invocation; người gọi cần có ownership rõ. Cũng không đổi `Locale.setDefault` theo từng request vì tác động toàn JVM.

## 16. Cấu hình providers phải theo từng JVM, không đổi giữa chừng

`LocaleServiceProvider` đọc/cache cấu hình provider order. Để so hai cấu hình:

```bash
# JVM thứ nhất:
java '-Djava.locale.providers=SPI,CLDR' \
  -cp build/classes demo.app.LocaleConsistencyDemo spi

# JVM thứ hai:
java '-Djava.locale.providers=CLDR' \
  -cp build/classes demo.app.LocaleConsistencyDemo cldr
```

Nếu bạn dùng JUnit trong cùng một JVM, chỉ làm:

```java
System.setProperty("java.locale.providers", "SPI,CLDR");
runTestA();

System.setProperty("java.locale.providers", "CLDR");
runTestB();
```

thì **không có bảo đảm** service lookup sẽ thay đổi như mong muốn vì provider configuration đã được cache. Cách đúng là:

- Dùng **test JVM forks** (Maven Surefire forks, Gradle forked test workers hoặc `ProcessBuilder`).
- Truyền `-Djava.locale.providers` ngay khi JVM khởi động.
- Mỗi fork chỉ có một provider configuration.
- Verify startup property và provider selection bằng output thực tế.

Nếu product có plugin provider được nạp động, câu chuyện phức tạp hơn: cần xem class loader visibility và JDK lookup scope. Không giả định một JAR mới được thêm vào filesystem là provider mới sẽ xuất hiện ngay trong JVM đang chạy.

## 17. Classpath, ServiceLoader và đóng gói providers

### 17.1. Provider class khác service file

Trong dự án:

```text
demo/spi/TestNumberProvider.class
META-INF/services/java.text.spi.NumberFormatProvider
```

Cả hai cần có mặt. Nếu class có nhưng descriptor thiếu, `ServiceLoader` có thể không tìm provider. Nếu descriptor có nhưng implementation class không load được, có thể có `ServiceConfigurationError` khi discovery.

Descriptor phải chứa **tên class đầy đủ**, một class name mỗi dòng. File dùng UTF-8, có thể có comments theo service provider configuration syntax. Lỗi package spelling, đổi tên class nhưng chưa cập nhật descriptor hoặc shading JAR sai đều dẫn đến lỗi runtime.

### 17.2. Phải quan sát provider có được chọn

Chạy:

```java
boolean installed = ServiceLoader.load(
        NumberFormatProvider.class).stream()
        .anyMatch(x -> x.type().getName().equals(
                "demo.spi.TestNumberProvider"));
```

Đây là đoạn minh họa, nằm trong method với imports thích hợp. Nó chứng minh provider **discoverable**, nhưng không chứng minh `NumberFormat.getNumberInstance(...)` đang thực sự dùng nó.

Tiếp theo test output sentinel:

```java
boolean chosen = NumberFormat
        .getNumberInstance(Locale.forLanguageTag("zz-ZZ"))
        .format(12345.67)
        .equals("12_345~67");
```

Một service có thể được cài **và** discovery thành công nhưng chưa được chọn do `java.locale.providers=CLDR`. Demo mode `cldr` chứng minh chính xác trường hợp này.

### 17.3. Classpath vs module path

Locale service providers có thể được triển khai trên **application classpath** hoặc **module path**:

- **Classpath**: dùng `META-INF/services/<fully.qualified.Service>`.
- **Named module**: dùng `provides ... with ...` trong `module-info.java`, bảo đảm provider nhìn thấy bởi system class loader/module resolution theo tài liệu `LocaleServiceProvider`.

Ví dụ module descriptor **minh họa, không phải phần chạy của demo classpath**:

```java
module demo.locale.spi {
    provides java.text.spi.NumberFormatProvider
        with demo.spi.TestNumberProvider;
    provides java.util.spi.LocaleNameProvider
        with demo.spi.TestNameProvider;
}
```

Khi chuyển sang JPMS, cấu hình module path và module resolution phải đúng. Đừng chỉ copy META-INF/services của classpath và giả định nó là cơ chế duy nhất cho một named module. Đồng thời, cần bảo đảm JVM vẫn bật `SPI` trong `java.locale.providers` khi muốn dùng custom providers.

### 17.4. Provider visibility và class loader

Tài liệu yêu cầu providers nhìn thấy qua **system class loader** để locale-sensitive service lookup có thể phát hiện. Các frameworks dùng plugin class loaders, child-first loaders hoặc custom module layers có thể có visibility khác với `ServiceLoader.load(...)` do application tự chạy.

Trước khi debug “JDK không gọi provider”, hãy xác minh:

1. Provider class load được từ runtime context.
2. Service descriptor được đóng gói đúng.
3. Class loader nhìn thấy file.
4. JVM property có `SPI` với thứ tự thích hợp.
5. `getAvailableLocales` thực sự bao gồm locale mong muốn.
6. Provider method trả đối tượng/name có nghĩa và không ném lỗi.
7. Nếu dùng JPMS, module với `provides` đã được resolve.

Đừng sửa system-level locale properties giữa runtime để vá lỗi khi artifact thiếu service descriptor.

## 18. CLDR có thể đổi khi nâng JDK

JDK dùng CLDR data từ Unicode Consortium. Một số chi tiết punctuation, localized names, grouping, currency symbols, number patterns và parse behavior có thể thay đổi khi phiên bản CLDR nâng cấp.

Javadoc `LocaleServiceProvider` Java SE 26 công bố mapping ví dụ:
- JDK 24 dùng **CLDR 46**.
- JDK 25 dùng **CLDR 47**.
- JDK 26 dùng **CLDR 48**.

Dữ liệu CLDR có thể được cập nhật ngay cả khi Java APIs không thay đổi. Vì vậy test:

```java
assertEquals("Vietnamese", subject.getDisplayLanguage(Locale.ENGLISH));
```

có thể hợp lý nếu sản phẩm yêu cầu đúng English label theo một bản dữ liệu đã pin, nhưng không phải lựa chọn tốt nhất nếu bạn muốn kiểm tra “có support locale” chung trên mọi JDK và provider.

Để test bền vững:

- Với **custom SPI**, dùng sentinel output ổn định do chính bạn sở hữu; assert chính xác.
- Với **CLDR**, assert những bất biến nghiệp vụ/tính hợp lệ, hoặc pin JDK+CLDR version cho golden snapshots.
- Khi nâng JDK, review thay đổi CLDR quan trọng thay vì cố dùng `COMPAT/JRE` đã bị loại từ JDK 23.
- Phân biệt **format output** với **parse rules**: nếu parse một persisted string tạo từ JDK cũ, test migration theo dữ liệu thật và format mới.
- Nếu nghiệp vụ buộc có byte-for-byte format ổn định, cân nhắc một `DecimalFormat` có pattern/symbols được định nghĩa tường minh hoặc một dữ liệu locale provider do ứng dụng quản lý.

Đừng dùng `Locale.ROOT` như “cách tự động cố định tất cả localizations” nếu yêu cầu là hiển thị ngôn ngữ thực tế cho user. ROOT có giá trị làm neutral locale, nhưng không thay thế chính sách locale và nguồn dữ liệu.

## 19. Kiểm thử consistency trong CI và Maven/Gradle

### 19.1. Ma trận tối thiểu

| Môi trường | Startup providers | Test phải chứng minh |
| --- | --- | --- |
| Directory classpath | `SPI,CLDR` | Custom number + name được chọn; 14 PASS |
| Directory classpath | `CLDR` | Hai providers vẫn installed nhưng **không** được chọn; 7 PASS |
| Packaged JAR | `SPI,CLDR` | Service descriptors còn nguyên, 14 PASS |
| JAR thiếu `META-INF/services` | `SPI,CLDR` | Discovery fail hoặc không có custom selection, không báo “pass” |
| Sai provider order | `CLDR,SPI` | Kết quả theo priority và locale coverage; không giả định SPI thắng |
| Locale không được provider hỗ trợ | `SPI,CLDR` | Fallback hợp lệ sang CLDR |
| Named module | `SPI,CLDR` | `provides` và module resolution đúng |
| JDK upgrade | `SPI,CLDR` và `CLDR` | Custom golden không đổi; CLDR snapshots được review |
| Wrong display locale | Bất kỳ | Label hiển thị theo display locale, không nhầm subject |
| FORMAT vs DISPLAY defaults | Bất kỳ | Không có dependence ngầm khi đã truyền explicit locale |
| Number parse | Custom SPI | Round-trip có tolerance và full consumption |
| Currency | Custom SPI | Monetary separators độc lập và đúng policy |
| Concurrency | Bất kỳ | Formatter instances không bị chia sẻ mutable ngoài ý muốn |

### 19.2. Test forked JVM

Nếu dùng build tool, tạo hai JVM forks khác nhau với system property:

```text
test-spi:
  JVM option: -Djava.locale.providers=SPI,CLDR
  args: spi

test-cldr:
  JVM option: -Djava.locale.providers=CLDR
  args: cldr
```

Đây là **mô tả test matrix**, không phải YAML của một build tool cụ thể. Trong Maven Surefire/Gradle Test, cấu hình fork options của đúng test task/worker. Không đặt property cho Maven daemon/Gradle daemon rồi mặc định test worker nhận cùng environment nếu build tool chạy processes khác.

**Quan trọng:** Một lượt test đang chạy trên JDK 24 và dùng Java 17 target **không chứng minh** cùng bytes/CLDR English labels là bắt buộc ở JDK 26. Test provider policy và sentinel, không hard-code những thứ không thuộc contract của bạn.

## 20. Kiểm tra tên, định dạng và parse theo input không đáng tin cậy

Số đưa vào từ người dùng có thể dùng dấu `,`, `.`, khoảng trắng thường hay narrow no-break space tùy locale. Kết quả hiển thị còn có thể dùng digits khác hệ số thập phân. Không được parse một số localized bằng cách đơn giản:

```java
Double.parseDouble(userInput);
```

trong khi UI đang hiển thị hoặc yêu cầu nhập số theo `NumberFormat` khác chuẩn Java floating-point literal. Ngược lại, đừng gửi `NumberFormat.format(...)` làm dạng dữ liệu machine-readable cho protocol/JSON nếu contract yêu cầu số chuẩn độc lập locale.

**Quy tắc:**

- **UI:** format/parse theo locale và policy.
- **JSON/API numeric field:** serialize dạng số theo contract của protocol, không dùng localized grouping.
- **DB numeric:** lưu giá trị số hoặc decimal chính xác, không lưu string đã format chỉ để tính toán.
- **Localized display names:** lưu language tags/codes ổn định, render names khi hiển thị.
- **Security input:** giới hạn độ dài, phát hiện trailing characters, làm rõ dấu âm, separators, special values và giới hạn range.

Không dùng `String.replace(",", "")` hay `replace("~", ".")` tùy tiện cho mọi locale. Một ký tự có thể mang ý nghĩa khác theo ngôn ngữ; nếu bạn tự thay chuỗi mà không validate, dữ liệu có thể bị hiểu sai.

## 21. Các lỗi thường gặp

**Lỗi 1 — Có implementation nhưng không có `META-INF/services`.**  
Class có trong JAR chưa đủ. Thêm service descriptor với tên service type chính xác và tên class implementation.

**Lỗi 2 — Có service descriptor nhưng không bật SPI.**  
Default Java SE 26 là `CLDR`. Bật `-Djava.locale.providers=SPI,CLDR` tại startup nếu muốn chọn providers.

**Lỗi 3 — Tin rằng `ServiceLoader` nhìn thấy provider nghĩa JDK dùng provider.**  
Discovery khác selection; phải kiểm tra output của `NumberFormat` và `Locale.getDisplay...`.

**Lỗi 4 — Chỉ cài `NumberFormatProvider`, quên `LocaleNameProvider`.**  
Số có thể từ SPI nhưng tên hiển thị từ CLDR; test cần phát hiện khi policy muốn đồng bộ.

**Lỗi 5 — Nhầm `NumberFormatProvider` với `DecimalFormatSymbolsProvider`.**  
Một SPI tạo formatters; SPI kia tạo symbol objects. Test riêng nếu app gọi cả hai đường.

**Lỗi 6 — Set `setGroupingSeparator` và `setDecimalSeparator` rồi nghĩ currency chắc chắn theo.**  
Currency pattern dùng **monetaryGroupingSeparator/monetaryDecimalSeparator** riêng; set cả hai.

**Lỗi 7 — Truyền ngược subject và display locale.**  
`subject.getDisplayLanguage(displayLocale)` nói tên của `subject` theo ngôn ngữ của người xem; không phải format subject theo chính nó trừ khi bạn chủ ý.

**Lỗi 8 — Coi `Locale.getDisplayName()` là khóa định danh.**  
Tên có thể thay theo display locale, provider hoặc CLDR. Lưu language tag/codes ổn định.

**Lỗi 9 — Không phân biệt `Locale.Category.FORMAT` và `DISPLAY`.**  
Các overload không có locale argument có thể dùng hai default categories khác nhau.

**Lỗi 10 — Đổi `java.locale.providers` bằng `System.setProperty` giữa hai tests.**  
Thứ tự providers có cache; fork JVM mới với startup property.

**Lỗi 11 — Dùng `COMPAT`/`JRE` để đòi format cũ trên JDK 26.**  
Legacy provider data bị loại ở JDK 23. Dùng CLDR, explicit pattern hoặc custom SPI đúng contract.

**Lỗi 12 — Assert nguyên văn English display name của CLDR mãi mãi.**  
CLDR data thay theo JDK. Chỉ pin golden khi pin data/JDK version hoặc UX contract yêu cầu.

**Lỗi 13 — Không kiểm tra parse đã tiêu thụ hết input.**  
`NumberFormat.parse` có thể đọc prefix. Dùng `ParsePosition` và kiểm tra index đến cuối.

**Lỗi 14 — Dùng `double` như nơi lưu tiền chính xác.**  
`double` có sai số nhị phân; dùng `BigDecimal`/precision policy cho tiền, format bằng `NumberFormat` khi hiển thị.

**Lỗi 15 — Không kiểm tra fallback khi custom locale không có.**  
Khi SPI không hỗ trợ, JDK có thể dùng candidate locale/CLDR. Test case thật ngoài tập `getAvailableLocales`.

**Lỗi 16 — Quên đóng gói service descriptors khi shading/fat-JAR.**  
Build plugin có thể ghi đè `META-INF/services`. Kiểm tra contents của artifact cuối và test run từ JAR.

**Lỗi 17 — Dùng một `NumberFormat` mutable chung mọi threads.**  
Không mặc định thread-safe. Tạo hoặc clone formatter theo request, kiểm tra concurrency.

**Lỗi 18 — Coi `getDisplayName` cần có punctuation cố định trên mọi locale.**  
Các thành phần và separator có thể localize. Test các thành phần trừ khi UX contract quy định layout.

**Lỗi 19 — Coi một locale SPI phải cung cấp mọi name kể cả chưa có dịch.**  
Name provider có thể trả `null` cho name chưa biết; fallback là hợp đồng của framework. Test coverage của những names cần thiết.

**Lỗi 20 — Quên policy khi FORMAT và DISPLAY khác nhau.**  
Số và nhãn không nhất thiết phải dùng cùng locale. Nhất quán là bám **chính sách đã được thiết kế**, không phải ép mọi thứ về một locale.

## 22. Tự kiểm tra kiến thức

**1. `java.locale.providers` mặc định trên Java SE 26 là gì?**  
`CLDR`. Nếu cần custom locale SPI trên classpath, bật `SPI` tường minh.

**2. `NumberFormatProvider` có tự đổi `Locale.getDisplayCountry` không?**  
Không. Tên country thuộc `LocaleNameProvider`.

**3. `ServiceLoader` tìm thấy provider thì JDK chắc chắn chọn nó chứ?**  
Không. Provider order và locale coverage quyết định selection.

**4. Cấu hình nào ưu tiên SPI rồi fallback CLDR?**  
`-Djava.locale.providers=SPI,CLDR`, đưa vào JVM startup.

**5. Vì sao không đổi property này giữa hai JUnit tests trong một JVM?**  
Provider order được đọc và cache; phải fork JVM.

**6. Tại sao demo dùng `zz-ZZ` thay vì một locale thật?**  
Đó là sentinel synthetic locale, giúp test source selection mà không phụ thuộc golden CLDR của quốc gia thật.

**7. `subject.getDisplayLanguage(displayLocale)` hiển thị tên của locale nào?**  
Tên ngôn ngữ **của subject**, viết theo **displayLocale**.

**8. Tại sao currency formatter trong demo phải gọi hai setter monetary?**  
Monetary grouping/decimal separators có thể khác ordinary number separators.

**9. Làm sao xác minh parse đã đọc toàn bộ `"12_345~67"`?**  
Kiểm tra parsed value và `ParsePosition.getIndex() == text.length()`.

**10. Hai service files trong demo tên gì?**  
`META-INF/services/java.text.spi.NumberFormatProvider` và `META-INF/services/java.util.spi.LocaleNameProvider`.

**11. Cài providers trên named module dùng cách gì?**  
Dùng `provides ... with ...` trong `module-info.java` và bảo đảm module được resolve, thay vì chỉ dựa classpath descriptors.

**12. Có thể dùng `COMPAT`/`JRE` để khôi phục legacy data trên JDK 26 không?**  
Không. Dữ liệu legacy đó đã bị loại từ JDK 23.

**13. Tại sao CLDR-only mode vẫn PASS service-installed tests?**  
Vì service discovery vẫn thấy provider classes; nhưng JDK không chọn chúng khi cấu hình chỉ CLDR.

**14. Nếu format locale của amount là `en-US` nhưng display locale của tên là `vi-VN`, có tự động coi là lỗi không?**  
Không, nếu đây là policy của ứng dụng.

**15. Vì sao không nên dùng localized display name làm DB primary key?**  
Tên có thể thay theo locale, CLDR và provider. Dùng language tag/code ổn định.

## Tài liệu chính thức đang được duy trì

- [Oracle Java SE 26 — `LocaleServiceProvider`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/spi/LocaleServiceProvider.html): provider order, `java.locale.providers`, default CLDR, SPI classpath/module deployment, fallback và caching.
- [Oracle Java SE 26 — `NumberFormatProvider`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/spi/NumberFormatProvider.html): number/integer/currency/percent factories và contract của provider.
- [Oracle Java SE 26 — `LocaleNameProvider`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/spi/LocaleNameProvider.html): language/region/script/variant names, trả `null` cho tên không biết và rules của display locale.
- [Oracle Java SE 26 — `Locale`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.html): `FORMAT`/`DISPLAY` categories, language tags và `getDisplay...` methods.
- [Oracle Java SE 26 — `NumberFormat`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/NumberFormat.html): locale-aware formatting/parsing, currency/percent/integer/number methods.
- [Oracle Java SE 26 — `DecimalFormatSymbols`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/DecimalFormatSymbols.html): normal vs monetary decimal/grouping separators.
- [Oracle Java SE 26 — `DecimalFormat`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/DecimalFormat.html): localized decimal patterns và parsing.
- [Oracle Java SE 26 — `ServiceLoader`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html): provider declarations, discovery, modules và services.
- [Oracle JDK 26 Supported Locales](https://www.oracle.com/java/technologies/javase/jdk26-supported-locales.html): provider categories và phiên bản CLDR được JDK tích hợp.
- [Oracle JDK Migration Guide — `JRE`/`COMPAT` removed](https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html): hướng migration từ dữ liệu legacy sang CLDR hoặc custom provider.

**Ghi nhớ:** Locale SPI không chỉ là việc cài một JAR. Để **số và tên hiển thị nhất quán**, phải xác định content/display/format locale, kiểm tra từng loại SPI có đúng service descriptor, bật `SPI` tại JVM startup, và quan sát **các API locale-sensitive thật sự** chứ không chỉ `ServiceLoader`. So custom sentinel chính xác; kiểm tra CLDR theo policy và phiên bản dữ liệu, không ép mọi bản Java mãi giữ một bản dịch hay punctuation.

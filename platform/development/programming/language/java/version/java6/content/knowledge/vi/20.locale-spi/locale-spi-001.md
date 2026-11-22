# LocaleServiceProvider và bổ sung dữ liệu bản địa hóa trong Java 17+

## 1. Locale SPI là gì?

Java có nhiều API **nhạy theo locale** như định dạng số, tiền tệ, ngày giờ, tên ngôn ngữ, tên vùng, múi giờ và thứ tự so sánh chuỗi. Mặc định, JDK hiện đại dùng phần lớn dữ liệu bản địa hóa từ **Unicode CLDR**. Ví dụ:

```java
Locale locale = Locale.forLanguageTag("vi-VN");
NumberFormat numberFormat = NumberFormat.getNumberInstance(locale);
String display = numberFormat.format(12345.67);
```

Đây là **snippet** trong method có import `java.util.Locale` và `java.text.NumberFormat`; không cố định chuỗi output vì dữ liệu CLDR có thể thay đổi theo JDK version.

Nếu một sản phẩm cần **bổ sung locale chưa có dữ liệu phù hợp** hoặc dùng quy tắc định dạng riêng, Java cung cấp **Locale Service Provider Interface (Locale SPI)**. Các providers có thể tham gia vào đường chọn của những factory chuẩn, chẳng hạn `NumberFormat.getNumberInstance(locale)`. Code application không cần trực tiếp khởi tạo một class provider cụ thể.

**`java.util.spi.LocaleServiceProvider`** là lớp cơ sở abstract. Ứng dụng phải triển khai một **concrete service type**, ví dụ `java.text.spi.NumberFormatProvider` hoặc `java.util.spi.LocaleNameProvider`; không đăng ký abstract superclass làm một service chung.

Bài này hướng dẫn:
- Phân biệt `Locale`, dữ liệu CLDR, `LocaleServiceProvider`, `ServiceLoader` và `ResourceBundle`.
- Hiểu `getAvailableLocales`, `isSupportedLocale` và locale extensions.
- Đăng ký provider bằng `META-INF/services` hoặc `provides` trong JPMS.
- Ưu tiên provider thông qua `-Djava.locale.providers=SPI,CLDR`.
- Chạy ví dụ Java 17+ có provider tùy chỉnh và stdout đã kiểm tra.
- Tránh phụ thuộc `COMPAT/JRE`, vì dữ liệu đó đã bị loại từ JDK 23.

## 2. Kiến trúc chọn dữ liệu bản địa hóa

```text
Ứng dụng
   |
   +-- NumberFormat.getNumberInstance(Locale)
                       |
              JDK locale provider lookup
                       |
             java.locale.providers order
                /                 \
             SPI                  CLDR
              |                    |
     NumberFormatProvider     Dữ liệu JDK
              |                    |
              +---------+----------+
                        |
                 NumberFormat object
                        |
                    format(...)
```

| Thành phần | Có chức năng | Không có chức năng |
| --- | --- | --- |
| `Locale` | Định danh ngôn ngữ/script/region/variant/extensions. | Không chứa bản dịch hoặc formatter. |
| CLDR | Dữ liệu bản địa hóa chuẩn của JDK. | Không giải quyết mọi quy tắc đặc thù của sản phẩm. |
| `LocaleServiceProvider` | Hợp đồng nền cho providers locale-sensitive. | Không tự cung cấp mọi loại dịch vụ. |
| `NumberFormatProvider` | Tạo number/integer/currency/percent formatters. | Không dịch tất cả message của ứng dụng. |
| `ServiceLoader` | Tìm concrete providers đã đăng ký. | Không bảo đảm JDK factory sẽ ưu tiên SPI. |
| `java.locale.providers` | Đặt thứ tự `SPI`, `CLDR` và các nguồn thích hợp. | Không tạo provider khi chưa có implementation. |
| `ResourceBundle` | Tra cứu key/value theo locale. | Không tự tùy biến `NumberFormat`. |

**Tìm thấy implementation ≠ chọn implementation.** Trong một dự án, `ServiceLoader` có thể thấy provider nhưng factory vẫn sử dụng CLDR do cấu hình `java.locale.providers` hoặc locale không được cung cấp.

## 3. Các concrete Locale SPI được hỗ trợ

Các subclass phổ biến của `LocaleServiceProvider`:

| Service type | Package | Vai trò |
| --- | --- | --- |
| `NumberFormatProvider` | `java.text.spi` | Số thường, số nguyên, tiền tệ, phần trăm, compact number. |
| `DecimalFormatSymbolsProvider` | `java.text.spi` | Ký hiệu chữ số, nhóm số, dấu thập phân, currency symbols. |
| `DateFormatProvider` | `java.text.spi` | Date/time formats theo locale. |
| `DateFormatSymbolsProvider` | `java.text.spi` | Tên tháng/ngày/era và date symbols. |
| `BreakIteratorProvider` | `java.text.spi` | Phân đoạn từ, câu, ký tự. |
| `CollatorProvider` | `java.text.spi` | So sánh/sắp xếp chuỗi theo locale. |
| `CalendarDataProvider` | `java.util.spi` | Ngày bắt đầu tuần, số ngày tối thiểu của tuần đầu. |
| `CalendarNameProvider` | `java.util.spi` | Tên đơn vị lịch. |
| `CurrencyNameProvider` | `java.util.spi` | Tên và ký hiệu tiền tệ theo ngôn ngữ. |
| `LocaleNameProvider` | `java.util.spi` | Tên ngôn ngữ, quốc gia, script/variant. |
| `TimeZoneNameProvider` | `java.util.spi` | Tên múi giờ bản địa hóa. |

Mỗi service có hợp đồng riêng. Nếu muốn `NumberFormat.getNumberInstance` dùng implementation của bạn thì cần tạo subclass **`NumberFormatProvider`** và đăng ký **`java.text.spi.NumberFormatProvider`**. File service của `LocaleNameProvider` không cung cấp number formatter và ngược lại.

**Không lẫn với `java.util.spi.ResourceBundleProvider`:** đây là SPI phục vụ ResourceBundle trong JPMS, không phải concrete subclass của `LocaleServiceProvider`.

## 4. Hợp đồng getAvailableLocales và isSupportedLocale

`LocaleServiceProvider` có hai API quan trọng:

```java
public abstract Locale[] getAvailableLocales();
public boolean isSupportedLocale(Locale locale);
```

Đây là **chữ ký minh họa**, không phải class standalone. Method `isSupportedLocale` có implementation mặc định.

### 4.1. getAvailableLocales

Provider công bố **chỉ những locale mà nó thực sự phục vụ**. Ví dụ:

```java
private static final Locale CUSTOM =
        Locale.forLanguageTag("qaa-QZ");

@Override
public Locale[] getAvailableLocales() {
    return new Locale[] { CUSTOM };
}
```

Đây là snippet trong subclass `NumberFormatProvider`. Việc trả array mới tránh caller sửa internal state. Theo hợp đồng API, danh sách không nên chứa nhiều locale chỉ khác Unicode extensions.

`qaa-QZ` là **locale tổng hợp dùng để kiểm thử**, không phải một bộ quy tắc tài chính/văn hóa chuẩn của quốc gia thật. Chọn tag này giúp phân biệt custom output với dữ liệu CLDR có sẵn.

### 4.2. isSupportedLocale

Mặc định, `isSupportedLocale` so requested locale với `getAvailableLocales()` nhưng **bỏ qua extensions**. Với extension yêu cầu numbering system khác, provider có thể cần xét riêng:

```java
@Override
public boolean isSupportedLocale(Locale locale) {
    if (!CUSTOM.stripExtensions()
            .equals(locale.stripExtensions())) {
        return false;
    }
    String numbering = locale.getUnicodeLocaleType("nu");
    return numbering == null || numbering.equals("latn");
}
```

Đây là snippet **tùy chọn**, không nằm trong bản runnable phía dưới. Nó minh họa một policy chỉ nhận numbering system mặc định/Latin. Nếu provider tuyên bố hỗ trợ extension, formatter trả về phải phản ánh đúng extension đó; nếu không, nên từ chối bằng `isSupportedLocale`.

### 4.3. Fallback

JDK có cơ chế thử locale candidates nếu requested locale không được phục vụ, tương tự một số nguyên tắc tra cứu của `ResourceBundle`. Với provider trả localized names như `LocaleNameProvider`, một request tên cụ thể có thể trả `null` để lookup thử tiếp. Với provider tạo đối tượng như `NumberFormatProvider`, phải tuân theo contract trả formatter và ngoại lệ phù hợp; không trả null tùy tiện.

## 5. Đăng ký SPI trên classpath

Khi chạy classpath/unnamed module, có file text **UTF-8**:

```text
META-INF/services/java.text.spi.NumberFormatProvider
```

Nội dung:

```text
demo.spi.CustomNumberFormatProvider
```

**Filename là tên service type**, content là fully qualified class implementation. Provider class phải load được, dependencies có mặt, constructor hợp lệ và resource file phải được đóng gói vào **runtime classpath root**.

Vị trí thường dùng trong Gradle/Maven: `src/main/resources/META-INF/services/java.text.spi.NumberFormatProvider`. Nếu đóng fat/shadow JAR có nhiều service files, cần **merge** thay vì ghi đè để không làm mất providers.

**Chỉ đóng provider JAR vào classpath không đủ** để nó được factory ưu tiên. Với Java hiện đại, phải khai báo `SPI` trong provider ordering khi startup JVM.

## 6. java.locale.providers và thay đổi JDK 23+

Khởi động JVM:

```bash
java -Djava.locale.providers=SPI,CLDR -cp out demo.app.Main
```

- `SPI`: tìm locale providers do application cài trước.
- `CLDR`: dùng dữ liệu locale chuẩn của JDK nếu provider không đáp ứng.
- `HOST`: provider phản ánh một số cài đặt OS, chỉ tồn tại khi JDK/OS hỗ trợ.
- `COMPAT` và `JRE`: bộ dữ liệu legacy đã **bị loại từ JDK 23**. Trên JDK 25 không nên dựa vào hai giá trị này.

**Property cần được truyền ngay lúc khởi động.** Runtime đọc/cached cấu hình provider order trong quá trình khởi tạo. Gọi `System.setProperty("java.locale.providers", "...")` sau khi subsystem locale đã chạy có thể không thay đổi thứ tự.

CLDR có thể thay đổi giữa các JDK releases, nên nếu format/parse là contract dữ liệu, cần regression-test trên những JDK thực mà production chạy. Locale SPI không tự pin Unicode/CLDR data version.

## 7. Ví dụ Java 17+ đầy đủ: custom NumberFormatProvider

Demo sử dụng locale `qaa-QZ` với ký hiệu nhân tạo:
- `_` dùng cho phân nhóm hàng nghìn.
- `:` dùng làm dấu thập phân.
- Dấu nhóm/thập phân của tiền tệ cũng lần lượt `_` và `:`.
- Ký hiệu tiền tệ thử nghiệm `USD`.
- Kiểu format cho number, integer, currency và percent.

Đây là **định dạng thử nghiệm có thể nhận ra**, không phải khuyến nghị hiển thị tiền thật ở bất kỳ quốc gia nào.

### 7.1. Cấu trúc thư mục

```text
locale-spi-demo/
  src/
    demo/
      spi/
        CustomNumberFormatProvider.java
      app/
        Main.java
  resources/
    META-INF/
      services/
        java.text.spi.NumberFormatProvider
```

Không cần `module-info.java` cho ví dụ classpath này.

### 7.2. File src/demo/spi/CustomNumberFormatProvider.java

```java
package demo.spi;

import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.text.spi.NumberFormatProvider;
import java.util.Locale;

public final class CustomNumberFormatProvider
        extends NumberFormatProvider {

    private static final Locale CUSTOM =
            Locale.forLanguageTag("qaa-QZ");

    public CustomNumberFormatProvider() {
    }

    @Override
    public Locale[] getAvailableLocales() {
        return new Locale[] { CUSTOM };
    }

    private static DecimalFormat format(
            Locale locale, String pattern) {

        if (!CUSTOM.stripExtensions()
                .equals(locale.stripExtensions())) {
            throw new IllegalArgumentException(
                    "Unsupported locale: " + locale);
        }

        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(Locale.ROOT);
        symbols.setInternationalCurrencySymbol("USD");
        symbols.setCurrencySymbol("USD");
        symbols.setGroupingSeparator('_');
        symbols.setDecimalSeparator(':');
        symbols.setMonetaryGroupingSeparator('_');
        symbols.setMonetaryDecimalSeparator(':');

        DecimalFormat value = new DecimalFormat(pattern, symbols);
        value.setRoundingMode(RoundingMode.HALF_EVEN);
        return value;
    }

    @Override
    public NumberFormat getNumberInstance(Locale locale) {
        return format(locale, "#,##0.00");
    }

    @Override
    public NumberFormat getIntegerInstance(Locale locale) {
        DecimalFormat value = format(locale, "#,##0");
        value.setParseIntegerOnly(true);
        return value;
    }

    @Override
    public NumberFormat getCurrencyInstance(Locale locale) {
        return format(locale, "\u00A4 #,##0.00");
    }

    @Override
    public NumberFormat getPercentInstance(Locale locale) {
        return format(locale, "#,##0%");
    }
}
```

Giải thích:
- `NumberFormatProvider` kế thừa `LocaleServiceProvider` và có bốn abstract methods nêu trên.
- `getAvailableLocales` công bố một locale mà implementation phục vụ.
- `DecimalFormatSymbols` điều chỉnh normal separators **và** monetary separators; monetary API hiện có ở Java 17+.
- `\u00A4` trong Java pattern là ký tự placeholder tiền tệ, ở đây hiển thị `USD`.
- Mỗi lần tạo formatter mới, tránh chia sẻ `DecimalFormat` mutable giữa threads.
- `getIntegerInstance` đặt `setParseIntegerOnly(true)` và rounding `HALF_EVEN`.
- Không gọi `NumberFormat.getNumberInstance(CUSTOM)` ngay trong chính provider, tránh recursion qua factory SPI.

### 7.3. File resources/META-INF/services/java.text.spi.NumberFormatProvider

```text
demo.spi.CustomNumberFormatProvider
```

Đây là file UTF-8 với **một dòng** tên concrete provider, không phải Java source.

### 7.4. File src/demo/app/Main.java

```java
package demo.app;

import java.text.NumberFormat;
import java.text.spi.NumberFormatProvider;
import java.util.Arrays;
import java.util.Locale;
import java.util.ServiceLoader;

public final class Main {

    public static void main(String[] args) {
        Locale custom = Locale.forLanguageTag("qaa-QZ");

        boolean found = ServiceLoader.load(
                NumberFormatProvider.class).stream()
                .anyMatch(provider ->
                        provider.type().getName().equals(
                                "demo.spi.CustomNumberFormatProvider"));

        System.out.println("spiDiscovered=" + found);
        System.out.println("locale=" + custom.toLanguageTag());

        boolean available = Arrays.asList(
                NumberFormat.getAvailableLocales())
                .contains(custom);
        System.out.println("supported=" + available);

        System.out.println("number="
                + NumberFormat.getNumberInstance(custom)
                        .format(12345.67));
        System.out.println("integer="
                + NumberFormat.getIntegerInstance(custom)
                        .format(12345.67));
        System.out.println("currency="
                + NumberFormat.getCurrencyInstance(custom)
                        .format(12345.67));
        System.out.println("percent="
                + NumberFormat.getPercentInstance(custom)
                        .format(0.25));
    }
}
```

`Main` không import concrete `CustomNumberFormatProvider`; nó gọi JDK factory. `ServiceLoader` chỉ dùng để xác nhận registration, không phải thay cho factory.

### 7.5. Biên dịch và chạy trên Linux/macOS

Từ thư mục `locale-spi-demo`:

```bash
mkdir -p out/META-INF/services
javac -encoding UTF-8 -d out src/demo/spi/CustomNumberFormatProvider.java src/demo/app/Main.java
cp resources/META-INF/services/java.text.spi.NumberFormatProvider out/META-INF/services/
java -Djava.locale.providers=SPI,CLDR -cp out demo.app.Main
```

`javac -d out` chỉ tạo class files, không tự copy service resource. Do đó bước `cp` đảm bảo service descriptor nằm đúng classpath root.

### 7.6. Lệnh PowerShell

```powershell
New-Item -ItemType Directory -Force out/META-INF/services | Out-Null
javac -encoding UTF-8 -d out src/demo/spi/CustomNumberFormatProvider.java src/demo/app/Main.java
Copy-Item resources/META-INF/services/java.text.spi.NumberFormatProvider out/META-INF/services/
java '-Djava.locale.providers=SPI,CLDR' -cp out demo.app.Main
```

Đây là cú pháp PowerShell. Với cmd.exe, sử dụng quy tắc tham số riêng của Command Prompt.

### 7.7. Stdout chính xác đã kiểm tra bằng JDK

```text
spiDiscovered=true
locale=qaa-QZ
supported=true
number=12_345:67
integer=12_346
currency=USD 12_345:67
percent=25%
```

Kết quả đã được kiểm tra bằng cách biên dịch Java, đặt đúng `META-INF/services` và khởi động với `SPI,CLDR`. Các dòng cho thấy:
1. `spiDiscovered=true`: ServiceLoader nhìn thấy implementation.
2. `locale=qaa-QZ`: JVM nhận tag thử nghiệm.
3. `supported=true`: JDK công bố locale này ở `NumberFormat.getAvailableLocales()` khi SPI được tích hợp.
4. `number=12_345:67`: dùng custom grouping/decimal separators.
5. `integer=12_346`: format integer với HALF_EVEN rounding.
6. `currency=USD 12_345:67`: monetary separators và symbol riêng của ví dụ.
7. `percent=25%`: format tỷ lệ 0.25 thành phần trăm.

Để nhận biết lỗi, hãy chạy lại **không có startup property `SPI,CLDR`**. `ServiceLoader` có thể vẫn tìm được provider nhưng factory có thể dùng CLDR, thể hiện ở output không còn ký hiệu riêng.

## 8. Vì sao provider được phát hiện mà không được chọn?

| Kiểm tra | Chứng minh | Không chứng minh |
| --- | --- | --- |
| `ServiceLoader.load(NumberFormatProvider.class)` tìm thấy class | Descriptor và class có thể load được. | JDK factory ưu tiên class đó. |
| `getAvailableLocales` có `qaa-QZ` | Provider công bố locale. | Mọi locale-sensitive service đều được hỗ trợ. |
| `-Djava.locale.providers=SPI,CLDR` | SPI được yêu cầu xét trước CLDR. | Provider class/JAR thực sự đã được đóng gói. |
| `NumberFormat.getNumberInstance` cho `12_345:67` | Custom formatting được chọn. | Currency/compact/date/timezone đều đúng nếu chưa test. |

Cần kiểm tra **cả registration lẫn factory output**. Nếu một locale đã có trong CLDR (`en-US`, `vi-VN`), muốn custom override phải chọn thứ tự provider rõ ràng và regression-test. Không đặt SPI toàn cục nếu chỉ một màn hình cần pattern đặc biệt; trong trường hợp hẹp, một `DecimalFormat` cục bộ có thể đơn giản hơn.

## 9. NumberFormatProvider và compact number format

Bốn abstract methods của `NumberFormatProvider`: `getNumberInstance`, `getIntegerInstance`, `getCurrencyInstance`, `getPercentInstance`.

JDK 12+ còn có:

```java
NumberFormat compact = NumberFormat.getCompactNumberInstance(
        Locale.US, NumberFormat.Style.SHORT);
```

Provider tương ứng có `getCompactNumberInstance(Locale, NumberFormat.Style)`, nhưng **default implementation có thể ném `UnsupportedOperationException`**. Bản demo không gọi compact. Nếu sản phẩm thật cần compact, cần override method này và trả formatter rút gọn đúng nghĩa (SHORT/LONG), kiểm tra số lớn/nhỏ, số âm, rounding và locale data. Trả `DecimalFormat` thông thường rồi gọi là compact là không đủ.

## 10. JPMS: provider trong named module

Đối với module path, dùng `provides` trong `module-info.java`:

```java
module demo.locale.provider {
    provides java.text.spi.NumberFormatProvider
            with demo.spi.CustomNumberFormatProvider;
}
```

Đây là **module descriptor snippet**, không phải project đầy đủ runnable. `java.base` được đọc ngầm định. Provider module phải được resolve/visible, đôi khi cần `--add-modules demo.locale.provider` theo cách launch.

Nếu application module **trực tiếp gọi `ServiceLoader.load(NumberFormatProvider.class)`** như demo, application module cũng khai báo:

```java
module demo.locale.app {
    uses java.text.spi.NumberFormatProvider;
}
```

Để chạy thật, còn cần cấu trúc source module, module path, provider class và runtime configuration đầy đủ. JDK documentation nhấn mạnh locale-sensitive providers phải visible với **system class loader**. Không tin rằng nạp JAR bằng classloader plugin biệt lập bất kỳ sẽ tự động đổi factory của JVM.

Trong named module, `provides` là cách công bố chuẩn; file `META-INF/services` chủ yếu dành cho classpath. Không trộn classpath/module path tùy tiện.

## 11. Gradle/Maven: cài provider lúc runtime

Trong Gradle Groovy DSL, nếu app không import concrete class:

```groovy
dependencies {
    runtimeOnly project(':locale-spi')
}

application {
    mainClass = 'demo.app.Main'
    applicationDefaultJvmArgs =
            ['-Djava.locale.providers=SPI,CLDR']
}
```

Đây là **snippet**, giả định settings.gradle đã khai báo modules, plugins và toolchain phù hợp. Provider project cần đặt service descriptor tại `src/main/resources/META-INF/services/java.text.spi.NumberFormatProvider` để được đóng JAR.

Với Maven cũng phải bảo đảm JAR nằm trên **runtime classpath**, service file có mặt và property được truyền ở launcher/container. Nếu build fat/shadow JAR, **merge các service files** khi đóng nhiều providers; ghi đè file có thể làm mất implementation.

**Không nhầm `annotationProcessor` trong Gradle với Locale SPI:** annotation processing chạy trong lúc compile, còn locale providers được JDK sử dụng **ở runtime**.

## 12. LocaleServiceProvider khác ResourceBundle

| Công cụ | Mục đích |
| --- | --- |
| `LocaleServiceProvider` và subclasses | Thêm dịch vụ như `NumberFormat`, tên locale/múi giờ, Collator, DateFormat. |
| `ResourceBundle` | Dịch thông điệp/tên nhãn của sản phẩm bằng key và locale. |
| `ResourceBundle.Control` | Tùy biến nguồn/candidate locale/cache của ResourceBundle trên unnamed module. |
| `java.util.spi.ResourceBundleProvider` | SPI cung cấp bundles trong kiến trúc JPMS. |
| CLDR trong JDK | Dữ liệu locale chuẩn cho phần lớn APIs. |

`NumberFormatProvider` **không tự tạo** `bundle.getString("welcome")`, và file `Messages_vi.properties` **không tự đổi** formatter tiền tệ của `NumberFormat`. Hãy dùng đúng API theo loại dữ liệu cần mở rộng.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách giải quyết |
| --- | --- | --- |
| `spiDiscovered=false` | Thiếu service file hoặc sai path/FQCN, JAR bị thiếu resource. | Kiểm tra `META-INF/services` trong classpath/JAR. |
| `ServiceConfigurationError` | Provider không load được hoặc constructor/dependency lỗi. | Xem root cause, classpath, constructor. |
| `spiDiscovered=true` nhưng factory không dùng SPI | Provider order thiếu `SPI` hoặc locale khác. | Truyền `-Djava.locale.providers=SPI,CLDR` khi JVM launch. |
| `getAvailableLocales` không có tag | Implementation công bố sai hoặc runtime không xét provider. | Kiểm tra return array, descriptor và provider order. |
| Currency separator khác number separator | API tiền tệ có monetary separators riêng. | Cấu hình `setMonetaryGroupingSeparator` và `setMonetaryDecimalSeparator`. |
| `isSupportedLocale` trả false | Base locale/script/region/extensions khác. | Kiểm tra `Locale.toLanguageTag`, extension policy. |
| Compact format lỗi | Provider chưa hỗ trợ compact method. | Override đúng nếu sản phẩm cần compact. |
| `System.setProperty` không tác dụng | Provider order đã được cached. | Đặt system property ở JVM startup. |
| `COMPAT` không tác dụng ở JDK25 | Dữ liệu legacy đã bị loại từ JDK 23. | Dùng CLDR/SPI. |
| App chạy classpath nhưng lỗi module path | Thiếu `provides`, `uses` hoặc module chưa resolve. | Cấu hình module graph và service visibility. |
| Fat JAR mất provider | Merge resource sai, service file bị ghi đè. | Merge `META-INF/services` có kiểm chứng. |
| Format sai khi nhiều threads | Dùng chung formatter mutable. | Tạo formatter mới mỗi lần hoặc đồng bộ đúng. |

## 14. Bảo mật, hiệu năng và chất lượng

- **Provider là Java code thực thi:** chỉ cài từ nguồn tin cậy, review dependencies và quyền chạy.
- **Đừng đổi global locale data nếu không cần:** một provider có thể ảnh hưởng nhiều modules/formatters của ứng dụng.
- **`DecimalFormat` có mutable state**, không tự thread-safe. Demo trả formatter mới mỗi factory call.
- **Tiền tệ cần dữ liệu đúng và kiểu số chính xác:** `BigDecimal` và `Currency` phù hợp hơn chuỗi đã format cho phép tính tiền.
- **Tôn trọng extensions:** không tuyên bố locale support khi không đáp ứng numbering system hoặc script cần thiết.
- **Không đưa thông tin nhạy cảm vào logs** khi debug formatter/provider.
- **Locale text vẫn cần escaping theo output context** nếu dùng trong HTML, XML hoặc SQL; SPI không thay thế bảo vệ injection.
- **Test JDK/CLDR phiên bản mục tiêu:** cùng API không bảo đảm mọi dữ liệu hiển thị giống nhau ở mọi release.
- **Kiểm tra artifact:** compile thành công nhưng thiếu service resource có thể làm SPI vô dụng.
- **Cân nhắc bảo toàn behavior:** khi đổi provider order trên dữ liệu đã lưu, regression-test parsing/formatting và các quy tắc nghiệp vụ.

## 15. Bài tập và câu hỏi ôn tập

**Bài tập 1.** Chạy demo với `SPI,CLDR` rồi chạy không có option. Kiểm tra `spiDiscovered` và định dạng số; giải thích sự khác nhau giữa discovery và factory selection.

**Bài tập 2.** Override `isSupportedLocale` để hỗ trợ một Unicode numbering extension cụ thể; viết test cho trường hợp không hỗ trợ.

**Bài tập 3.** Đóng provider JAR bằng Gradle, bảo đảm file `META-INF/services` nằm trong JAR; chạy qua dependency runtimeOnly.

**Bài tập 4.** Viết `LocaleNameProvider` cho một locale tổng hợp, so sánh cách trả localized names với formatter objects.

**Bài tập 5.** Chuyển provider sang JPMS named module có `provides`, thêm `uses` nếu app gọi `ServiceLoader` trực tiếp và test trên module path.

**Câu 1:** `LocaleServiceProvider` và `NumberFormatProvider` khác nhau thế nào?

**Đáp án:** Cái đầu là abstract superclass; cái sau là concrete service type cho number formats và có các methods bắt buộc.

**Câu 2:** Có nên đăng ký `java.util.spi.LocaleServiceProvider` trong service filename khi cần NumberFormat không?

**Đáp án:** Không. Phải dùng `java.text.spi.NumberFormatProvider` làm tên service và implementation phù hợp.

**Câu 3:** `getAvailableLocales` có thể liệt kê mọi locale dù chỉ hỗ trợ một không?

**Đáp án:** Không nên. Chỉ trả các locale provider có dữ liệu/behavior đúng.

**Câu 4:** Vì sao `ServiceLoader` tìm thấy provider chưa chứng minh factory JDK dùng nó?

**Đáp án:** JDK còn chọn provider theo cấu hình `java.locale.providers` và locale/service support.

**Câu 5:** Vì sao không dùng `COMPAT/JRE` trên JDK25?

**Đáp án:** Legacy locale data đã bị loại từ JDK 23, nên phải dùng CLDR và/hoặc SPI hiện hành.

**Câu 6:** Locale SPI có dịch messages của `ResourceBundle` không?

**Đáp án:** Không. Đây là hai cơ chế khác nhau.

**Câu 7:** `NumberFormatProvider` tự hỗ trợ compact number format không?

**Đáp án:** Không mặc định. Compact method có contract riêng; default có thể ném `UnsupportedOperationException`.

## 16. Checklist triển khai

1. Chọn **đúng service type**, không đăng ký abstract superclass.
2. `getAvailableLocales` chỉ liệt kê locale thực sự hỗ trợ.
3. `isSupportedLocale` xử lý extensions nếu cần.
4. Đăng ký `META-INF/services` cho classpath hoặc `provides` cho named module.
5. Đặt `-Djava.locale.providers=SPI,CLDR` ở JVM launch khi muốn SPI trước CLDR.
6. Không dựa vào `COMPAT/JRE` đã lỗi thời/bị loại.
7. Kiểm tra cả `ServiceLoader` discovery và public factory output.
8. Đóng gói service file trong runtime artifact, merge đúng ở fat JAR.
9. Không chia sẻ `DecimalFormat` mutable thiếu đồng bộ.
10. Regression-test trên JDK/CLDR version triển khai.
11. Không nhầm Locale SPI với ResourceBundle/ResourceBundleProvider.
12. Nếu chỉ cần format cục bộ, cân nhắc `DecimalFormat` trực tiếp thay global SPI.

## 17. Nguồn tài liệu chính thức

- [Java SE 17 — LocaleServiceProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/LocaleServiceProvider.html): class cơ sở, locale support, classpath SPI registration.
- [Java SE 25 — LocaleServiceProvider](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/spi/LocaleServiceProvider.html): provider order, CLDR/SPI/HOST, modules.
- [Java SE 17 — NumberFormatProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/spi/NumberFormatProvider.html): các methods và compact formatting.
- [Java SE 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html): factory/parse/format và thread safety.
- [Java SE 17 — DecimalFormatSymbols](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormatSymbols.html): normal/monetary separators.
- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): classpath/module service discovery.
- [JDK 23 Release Notes — Legacy Locale Data Removal](https://www.oracle.com/java/technologies/javase/23-relnote-issues.html): COMPAT/JRE removed.

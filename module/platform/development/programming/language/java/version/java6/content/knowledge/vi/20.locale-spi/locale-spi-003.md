# DecimalFormatSymbolsProvider và bộ ký hiệu định dạng số trong Java Locale SPI

`java.text.spi.DecimalFormatSymbolsProvider` là **Service Provider Interface (SPI)** cho phép ứng dụng hoặc thư viện cung cấp bộ ký hiệu định dạng số cho những `Locale` được hỗ trợ. Những bộ ký hiệu này nằm trong đối tượng `java.text.DecimalFormatSymbols`: dấu thập phân, dấu phân nhóm, chữ số 0, dấu trừ, phần trăm, phần nghìn, biểu diễn infinity/NaN và ký hiệu tiền tệ.

API `DecimalFormatSymbolsProvider` xuất hiện từ Java 6, **vẫn còn áp dụng ở Java 17+ và JDK hiện hành**. Đây là một dạng mở rộng dữ liệu locale, không phải cách tạo formatter mới hay phương pháp thay thế toàn bộ tính toán số. Trên JDK hiện đại, **CLDR là nguồn dữ liệu locale mặc định**; muốn JVM phát hiện và sử dụng provider từ ứng dụng, phải đăng ký service đúng và **cấu hình `SPI` trong `java.locale.providers`**.

Bài này trình bày đầy đủ:

- `DecimalFormatSymbolsProvider` khác `DecimalFormatSymbols` và `DecimalFormat` như thế nào.
- `getAvailableLocales`, `isSupportedLocale`, `getInstance(Locale)` và contract của provider.
- Những ký hiệu quan trọng và ảnh hưởng tới format/parse.
- Cách đóng gói service descriptor `META-INF/services`, chọn thứ tự `SPI`/`CLDR`.
- Ví dụ **Java 17+ biên dịch, chạy và được xác minh thực tế** trên JDK 24.
- Cách tránh recursion khi provider tự gọi `DecimalFormatSymbols.getInstance`.
- Unicode numbering systems, ứng dụng đa luồng, JPMS, tiền tệ, parsing và các lỗi thường gặp.

## 1. Ba abstraction cần phân biệt

| API | Vai trò | Cách dùng |
| --- | --- | --- |
| `DecimalFormatSymbols` | Đối tượng mutable chứa **ký hiệu** cho định dạng số. | `DecimalFormatSymbols.getInstance(locale)`, các getter/setter cho separators. |
| `DecimalFormatSymbolsProvider` | Factory **SPI** trả bộ symbols cho locale mà nhà cung cấp khai báo hỗ trợ. | Viết subclass, đăng ký trong `META-INF/services` hoặc JPMS `provides`. |
| `DecimalFormat` | Formatter/parser sử dụng pattern, rounding, grouping và symbols. | `new DecimalFormat("#,##0.00", symbols)`. |
| `NumberFormat` | API nền cho định dạng số, phần trăm, tiền tệ. | `NumberFormat.getNumberInstance(locale)` hoặc các factory khác. |
| `NumberFormatProvider` | Một **SPI riêng** cho những instance `NumberFormat`. | Không mặc nhiên bị thay thế bởi `DecimalFormatSymbolsProvider`. |

Một cách hình dung:

```text
Locale zz-ZZ hoặc en-US
          |
          v
DecimalFormatSymbols.getInstance(locale)
          |
          v
Locale providers: SPI / CLDR / HOST
          |
          v
DecimalFormatSymbols { decimal=':', grouping='|' }
          |
          v
new DecimalFormat("#,##0.00", symbols)
          |
          v
      "12|345:67"
```

Đây là sơ đồ ý tưởng, không phải trace được Java API bảo đảm. Kết quả thực tế chịu ảnh hưởng bởi locale, thứ tự các provider sources, supported locales, Unicode extensions và formatter.

**Cần lưu ý:** `DecimalFormatSymbolsProvider` là **abstract class**, mặc dù được gọi là “service provider interface”. Nó kế thừa `java.util.spi.LocaleServiceProvider` trong `java.base`; không cần dependency ngoài JDK.

## 2. Những ký hiệu do DecimalFormatSymbols chứa

| Method | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `getDecimalSeparator()`, `setDecimalSeparator(char)` | Ký hiệu ngăn phần nguyên/phần thập phân. | `'.'` hoặc `','` |
| `getGroupingSeparator()`, `setGroupingSeparator(char)` | Ký hiệu phân nhóm chữ số. | `','`, khoảng trắng, `'|'` trong demo |
| `getZeroDigit()`, `setZeroDigit(char)` | Chữ số 0 của hệ chữ số localized phù hợp. | `'0'` |
| `getMinusSign()`, `setMinusSign(char)` | Dấu âm. | `'-'` |
| `getPercent()`, `setPercent(char)` | Ký hiệu phần trăm. | `'%'` |
| `getPerMill()`, `setPerMill(char)` | Ký hiệu phần nghìn. | `'‰'` |
| `getInfinity()`, `setInfinity(String)` | Chuỗi biểu diễn infinity. | `"∞"` |
| `getNaN()`, `setNaN(String)` | Chuỗi biểu diễn not-a-number. | `"NaN"` |
| `getDigit()`, `setDigit(char)` | Ký hiệu digit placeholder trong localized pattern. | `'#'` |
| `getPatternSeparator()`, `setPatternSeparator(char)` | Ngăn cách subpattern dương/âm trong localized pattern. | `';'` |
| `getMonetaryDecimalSeparator()`, `setMonetaryDecimalSeparator(char)` | Ký hiệu thập phân trong định dạng tiền tệ. | Có thể khác dấu thường |
| `getMonetaryGroupingSeparator()`, `setMonetaryGroupingSeparator(char)` | Ký hiệu phân nhóm trong định dạng tiền tệ. | Có thể khác dấu thường |
| `getCurrencySymbol()`, `setCurrencySymbol(String)` | Ký hiệu tiền tệ hiển thị. | `"$"` |
| `getInternationalCurrencySymbol()`, `setInternationalCurrencySymbol(String)` | Mã tiền tệ quốc tế. | `"USD"` |
| `getExponentSeparator()`, `setExponentSeparator(String)` | Ký hiệu exponent cho scientific notation. | `"E"` |

**Symbols không bao gồm mọi quy tắc:** `DecimalFormat` còn định nghĩa pattern, số chữ số thập phân, rounding mode, grouping size, prefixes/suffixes và parsing behavior. Một locale provider trả đúng dấu nhóm không có nghĩa ứng dụng đã có đúng **currency rules**, **numeric precision** hoặc **định dạng cho mục đích tính toán tài chính**.

### 2.1. Pattern và ký hiệu đầu ra khác nhau

```java
// Mảnh code trong method, đã có Locale locale và import phù hợp:
DecimalFormatSymbols symbols = DecimalFormatSymbols.getInstance(locale);
DecimalFormat formatter = new DecimalFormat("#,##0.00", symbols);
String value = formatter.format(12345.67);
```

Pattern `"#,##0.00"` được dùng theo **cú pháp non-localized**: dấu `','` và `'.'` trong pattern là ký hiệu cấu trúc. Nếu symbols chứa `grouping='|'` và `decimal=':'`, output là `"12|345:67"`. **Không cần và không được tự ý đổi pattern thành `"#|##0:00"`** khi dùng constructor `DecimalFormat(String, DecimalFormatSymbols)`.

Phân biệt `applyPattern` (non-localized) với `applyLocalizedPattern` (đọc ký hiệu pattern theo locale), và phân biệt pattern placeholders với ký hiệu được in. Ví dụ `'#'` trong pattern là “digit optional”, không phải ký tự muốn xuất hiện trong kết quả.

### 2.2. Dữ liệu biểu diễn không phải dữ liệu tính toán

`"12|345:67"` là **text localized**, không phải một `double` hay `BigDecimal`. Không lưu text localized làm giá trị số nguồn nếu dữ liệu phải dùng tiếp trong nhiều môi trường; giữ số ở một kiểu dữ liệu phù hợp và format khi hiển thị.

Đối với tiền tệ, dùng `BigDecimal` cùng currency/rounding policy, không dựa vào việc symbol có vẻ đẹp để quyết định precision. Dấu thập phân cho tiền tệ có thể khác dấu thông thường; provider nên thiết lập các ký hiệu monetary tương ứng khi có yêu cầu.

## 3. Hợp đồng Java của DecimalFormatSymbolsProvider

Class cần được khai báo:

```java
public final class MyProvider extends DecimalFormatSymbolsProvider {
    // getAvailableLocales() và getInstance(Locale)
}
```

Đây là skeleton minh họa; chưa đầy đủ import hoặc method implementation. Provider phải là class concrete có thể được runtime tải và khởi tạo theo quy tắc ServiceLoader/module.

### 3.1. `getAvailableLocales()`

```java
@Override
public Locale[] getAvailableLocales() {
    return new Locale[] {
        Locale.forLanguageTag("zz-ZZ"),
        Locale.US
    };
}
```

- Method trả array các locale provider tuyên bố có dữ liệu.
- Nên trả array mới hoặc bản sao thay vì cho bên ngoài sửa shared mutable array.
- Không quảng cáo locale không thể phục vụ đúng.
- Không dùng `null` thay array hoặc đặt `null` vào các phần tử.
- `zz-ZZ` trong bài là **locale giả lập** để chứng minh cơ chế SPI, không phải chuẩn trình bày số của một quốc gia.
- `Locale.US` được thêm chỉ để kiểm tra **ưu tiên giữa SPI và CLDR** cho locale JDK vốn đã hỗ trợ.

`DecimalFormatSymbols.getAvailableLocales()` có thể trả tập locale từ nhiều nguồn đã được runtime kích hoạt. Danh sách này **không chứng minh** provider nào đang thực sự được chọn cho từng locale.

### 3.2. `getInstance(Locale locale)`

```java
@Override
public DecimalFormatSymbols getInstance(Locale locale) {
    Objects.requireNonNull(locale, "locale");
    if (!isSupportedLocale(locale)) {
        throw new IllegalArgumentException("Unsupported locale: " + locale);
    }
    DecimalFormatSymbols symbols =
            DecimalFormatSymbols.getInstance(Locale.ROOT);
    symbols.setGroupingSeparator('|');
    symbols.setDecimalSeparator(':');
    return symbols;
}
```

Đây là đoạn bên trong provider, cần import `DecimalFormatSymbols`, `Objects` và `Locale`. Phương thức phải:

1. Nhận `Locale` yêu cầu.
2. Trả về một **`DecimalFormatSymbols` mới** cho locale mà provider khai báo hỗ trợ.
3. Ném `NullPointerException` khi tham số `locale` null.
4. Ném `IllegalArgumentException` khi locale yêu cầu không nằm trong các locale được provider hỗ trợ.
5. Không trả `null` hoặc sử dụng một singleton `DecimalFormatSymbols` mutable chung cho mọi caller.
6. Tôn trọng Unicode locale extensions theo chính sách dữ liệu mà provider tuyên bố.

### 3.3. Cảnh báo recursive provider lookup

Khi `SPI` ưu tiên và provider có `Locale.US` trong `getAvailableLocales()`, gọi bên trong:

```java
// Anti-pattern khi provider cũng hỗ trợ Locale.US:
DecimalFormatSymbols symbols =
        DecimalFormatSymbols.getInstance(Locale.US);
```

có thể khiến runtime gọi lại **chính provider**, dẫn tới recursive lookup/stack overflow. Trong demo, provider dùng `DecimalFormatSymbols.getInstance(Locale.ROOT)`: `Locale.ROOT` **không nằm trong tập được provider demo hỗ trợ**, nên baseline được lấy từ nguồn khác, không gọi lại cùng nhánh.

Với production, tốt hơn có một nguồn dữ liệu baseline độc lập, xác định rõ locale nào được hỗ trợ, và test recursion. Đừng sửa bằng cách bắt `StackOverflowError`; hãy sửa thiết kế lookup.

### 3.4. `isSupportedLocale(Locale)`

`LocaleServiceProvider` có implementation mặc định của `isSupportedLocale(locale)` dựa trên `getAvailableLocales()`. Khi kiểm tra mặc định, **Unicode locale extensions bị bỏ qua**, nhưng yêu cầu thực tế có thể chứa `-u-nu-...` nhằm chỉ định numbering system.

Nếu muốn phân biệt extension như `u-nu-latn` và `u-nu-arab`, provider phải có chính sách tương thích rõ và có thể override `isSupportedLocale`. Chỉ kiểm tra `locale.getLanguage()` rồi mặc nhiên trả bộ ký hiệu giống nhau cho mọi numbering system có thể cho kết quả sai.

## 4. Nguồn dữ liệu locale và property java.locale.providers

Các nguồn trong JDK hiện hành:

| Provider type | Vai trò | Khi sử dụng |
| --- | --- | --- |
| `CLDR` | Dữ liệu locale chuẩn trong JDK lấy từ Unicode CLDR. | Mặc định trên JDK mới. |
| `SPI` | Các Locale Service Provider cài bởi ứng dụng/thư viện. | Cần được thêm vào provider order để dùng custom SPI. |
| `HOST` | Dữ liệu theo cấu hình locale của hệ điều hành, nếu implementation có hỗ trợ. | Chỉ chọn có chủ đích, không bảo đảm giống nhau giữa các OS. |

`java.locale.providers` là JVM system property được **đọc và cache khi cơ sở locale service khởi tạo**:

```text
-Djava.locale.providers=SPI,CLDR
```

Ưu tiên SPI, sau đó CLDR nếu không có provider phù hợp. Ngược lại:

```text
-Djava.locale.providers=CLDR,SPI
```

Ưu tiên CLDR cho những locale được CLDR hỗ trợ; SPI được xét theo fallback/availability phù hợp.

**Quan trọng:**

- Mặc định của Java hiện đại tương đương `CLDR`; không nên mong custom service provider trên classpath tự thay kết quả khi bạn chưa bật `SPI`.
- Đặt `-Djava.locale.providers=...` ở **lệnh khởi động JVM**, không trông chờ `System.setProperty(...)` giữa chừng sẽ thay cấu hình đã được cached.
- **Không dùng `COMPAT`/`JRE` legacy locale-data providers trong giải pháp mới**; các dữ liệu legacy đó đã bị loại khỏi JDK hiện hành.
- Cấu hình provider order ảnh hưởng nhiều loại locale-sensitive services, không chỉ một lần gọi riêng.
- Mỗi SPI là một service riêng. `DecimalFormatSymbolsProvider` và `NumberFormatProvider` không hoán đổi cho nhau.
- CLDR version đi kèm JDK có thể thay đổi hành vi khi nâng runtime, vì vậy cần test locales chính thức mà sản phẩm sử dụng.

## 5. Ví dụ chạy thật Java 17+: tạo, đăng ký và kiểm chứng provider

Bài thực hành dùng **hai class** và **một service configuration file**. Không cần thư viện ngoài JDK.

**Mục tiêu:** tạo một provider hỗ trợ `zz-ZZ` và `en-US`; dùng ký hiệu giả lập `grouping='|'`, `decimal=':'`. Sau đó chạy hai lệnh với thứ tự providers khác nhau để xem hiệu ứng.

### 5.1. Cấu trúc dự án

```text
locale-spi-demo/
  provider-src/
    demo/
      spi/
        CustomSymbolsProvider.java
  app-src/
    demo/
      LocaleSpiDemo.java
  build/                         (tạo khi chạy lệnh)
    provider/
      demo/spi/CustomSymbolsProvider.class
      META-INF/services/java.text.spi.DecimalFormatSymbolsProvider
    app/
      demo/LocaleSpiDemo.class
```

`build/provider` và `build/app` dùng để tách provider implementation khỏi application class. File cấu hình ServiceLoader nằm **trong output của provider**.

### 5.2. `provider-src/demo/spi/CustomSymbolsProvider.java`

```java
package demo.spi;

import java.text.DecimalFormatSymbols;
import java.text.spi.DecimalFormatSymbolsProvider;
import java.util.Locale;
import java.util.Objects;

public final class CustomSymbolsProvider extends DecimalFormatSymbolsProvider {
    private static final Locale CUSTOM = Locale.forLanguageTag("zz-ZZ");

    @Override
    public Locale[] getAvailableLocales() {
        return new Locale[] {CUSTOM, Locale.US};
    }

    @Override
    public DecimalFormatSymbols getInstance(Locale locale) {
        Objects.requireNonNull(locale, "locale");
        if (!isSupportedLocale(locale)) {
            throw new IllegalArgumentException("Unsupported locale: " + locale);
        }
        DecimalFormatSymbols symbols = DecimalFormatSymbols.getInstance(Locale.ROOT);
        symbols.setGroupingSeparator('|');
        symbols.setDecimalSeparator(':');
        symbols.setMonetaryGroupingSeparator('|');
        symbols.setMonetaryDecimalSeparator(':');
        return symbols;
    }
}
```

Bốn điểm cần quan sát:

1. Provider **extends `DecimalFormatSymbolsProvider`**, không extends `DecimalFormatSymbols`.
2. `getAvailableLocales` khai báo cả locale giả lập và locale có sẵn ở CLDR.
3. `getInstance` kiểm tra locale rồi trả **symbols instance mới**.
4. `Locale.ROOT` được dùng làm baseline để **không đệ quy** qua provider cho `Locale.US` mà chính provider này hỗ trợ.

Trong sản phẩm thực, mỗi locale cần bộ ký hiệu hợp chuẩn. Các ký tự `'|'`/`':'` ở đây chỉ phục vụ kiểm tra SPI lookup và không nên đưa thẳng vào giao diện người dùng.

### 5.3. `app-src/demo/LocaleSpiDemo.java`

```java
package demo;

import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public final class LocaleSpiDemo {
    private static void show(String label, Locale locale) {
        DecimalFormatSymbols symbols = DecimalFormatSymbols.getInstance(locale);
        System.out.println(label + ".symbols=" +
                symbols.getGroupingSeparator() + symbols.getDecimalSeparator());
        DecimalFormat format = new DecimalFormat("#,##0.00", symbols);
        System.out.println(label + ".formatted=" + format.format(12345.67));
    }

    public static void main(String[] args) {
        show("custom", Locale.forLanguageTag("zz-ZZ"));
        show("enUS", Locale.US);
    }
}
```

Tại sao tạo `DecimalFormat` trực tiếp? Vì bài đang test **`DecimalFormatSymbolsProvider`**. `NumberFormat.getNumberInstance(locale)` có thể đi qua factory/source riêng, nên không nên dùng nó rồi mặc nhiên cho rằng mọi ký hiệu lấy từ provider custom này.

### 5.4. Đăng ký `META-INF/services`

Tạo file ở chính xác:

```text
build/provider/META-INF/services/java.text.spi.DecimalFormatSymbolsProvider
```

Nội dung **UTF-8** (một dòng):

```text
demo.spi.CustomSymbolsProvider
```

Tên file phải là **fully qualified service type name**, trong file liệt kê **fully qualified implementation class name**. Không thêm đuôi `.txt`, không viết sai thành `javax.text.spi`, và bảo đảm file xuất hiện đúng vị trí trong classpath/provider JAR.

### 5.5. Lệnh chạy Bash (Linux/macOS)

Từ thư mục dự án:

```bash
mkdir -p build/provider/META-INF/services build/app
javac --release 17 -d build/provider provider-src/demo/spi/CustomSymbolsProvider.java
printf 'demo.spi.CustomSymbolsProvider\n' > build/provider/META-INF/services/java.text.spi.DecimalFormatSymbolsProvider
javac --release 17 -d build/app app-src/demo/LocaleSpiDemo.java

java -Djava.locale.providers=SPI,CLDR -cp "build/provider:build/app" demo.LocaleSpiDemo
java -Djava.locale.providers=CLDR,SPI -cp "build/provider:build/app" demo.LocaleSpiDemo
```

Ở Linux/macOS, ký tự `:` phân tách hai classpath entries. `-D...` phải được đặt trước tên class main để JVM nhận làm system property.

### 5.6. PowerShell (Windows)

```powershell
New-Item -ItemType Directory -Force build/provider,build/app,build/provider/META-INF/services | Out-Null
javac --release 17 -d build/provider provider-src/demo/spi/CustomSymbolsProvider.java

$utf8 = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText("build/provider/META-INF/services/java.text.spi.DecimalFormatSymbolsProvider", "demo.spi.CustomSymbolsProvider" + [Environment]::NewLine, $utf8)

javac --release 17 -d build/app app-src/demo/LocaleSpiDemo.java

java '-Djava.locale.providers=SPI,CLDR' -cp 'build/provider;build/app' demo.LocaleSpiDemo
java '-Djava.locale.providers=CLDR,SPI' -cp 'build/provider;build/app' demo.LocaleSpiDemo
```

Trên Windows, classpath dùng `;`. `UTF8Encoding($false)` ở ví dụ PowerShell tạo file service **không BOM**, tránh ký tự ẩn trước tên class.

### 5.7. Kết quả kiểm chứng thực tế

Đã biên dịch bằng `javac --release 17` và chạy với JDK 24 trên Windows, sử dụng đúng SPI registration và hai JVM riêng.

**Với `SPI,CLDR`:**

```text
custom.symbols=|:
custom.formatted=12|345:67
enUS.symbols=|:
enUS.formatted=12|345:67
```

**Với `CLDR,SPI`:**

```text
custom.symbols=|:
custom.formatted=12|345:67
enUS.symbols=,.
enUS.formatted=12,345.67
```

Diễn giải:

- `SPI,CLDR`: provider custom được chọn trước cho cả `zz-ZZ` và `en-US`.
- `CLDR,SPI`: trong JDK 24 thử nghiệm, CLDR cung cấp bộ ký hiệu chuẩn cho `en-US`, còn locale synthetic `zz-ZZ` tiếp tục được SPI xử lý.
- Đây là **output từ thực thi có kiểm chứng**, không chỉ dự đoán từ tài liệu.
- CLDR và danh sách locale có thể phát triển theo JDK; hãy kiểm thử với runtime mục tiêu thay vì hứa tuyệt đối rằng mọi locale synthetic sẽ luôn thuộc SPI.

**Kết luận:** phải có đủ code provider, service descriptor, runtime classpath và provider order phù hợp. Có một trong bốn chưa đủ để biết chắc service đã được sử dụng.

## 6. Vì sao không nên nhầm các factory SPI?

`java.text.spi.DecimalFormatSymbolsProvider` cung cấp **ký hiệu**. `java.text.spi.NumberFormatProvider` cung cấp **các number formatter instances**, là một extension point khác.

Do đó:

```java
// Kiểm tra provider symbols mà ứng dụng đã đăng ký:
DecimalFormatSymbols symbols = DecimalFormatSymbols.getInstance(locale);
DecimalFormat custom = new DecimalFormat("#,##0.00", symbols);
```

không đồng nghĩa với:

```java
// Đường factory của NumberFormat, có thể dùng nguồn/provider khác:
NumberFormat number = NumberFormat.getNumberInstance(locale);
```

Cả hai là mảnh code minh họa, cần imports và `locale` đã được cấp. Không viết test chỉ gọi `NumberFormat.getNumberInstance` rồi kết luận `DecimalFormatSymbolsProvider` không hoạt động; hãy test API `DecimalFormatSymbols.getInstance` trước.

Khi có yêu cầu chỉ thay bộ ký hiệu ở **một màn hình**, một `DecimalFormatSymbols` cấu hình thủ công và truyền vào `DecimalFormat` thường đơn giản hơn cài một provider toàn ứng dụng. SPI phù hợp khi bạn có **nguồn locale data thực sự**, cần thống nhất các call sites, quản lý nhiều locales và kiểm soát provider lookup.

## 7. Unicode locale extensions và numbering system

Locale còn có thể chứa **BCP 47 Unicode extensions**. Ví dụ:

```java
// Mảnh Java 17+, cần import java.util.Locale:
Locale arabicDigits = Locale.forLanguageTag("ar-u-nu-arab");
Locale latinDigits = Locale.forLanguageTag("ar-u-nu-latn");
```

`nu` yêu cầu một **numbering system** cụ thể. Vì vậy cùng ngôn ngữ `ar` có thể cần những chữ số hoặc ký hiệu khác nhau tùy extension.

`LocaleServiceProvider.isSupportedLocale` mặc định **bỏ qua extensions trong phép kiểm tra**. Nếu provider chọn symbols chỉ theo `locale.getLanguage()`, nó có thể trả kết quả sai với hệ chữ số được yêu cầu.

Khi triển khai thật:

1. Xác định extensions nào provider có khả năng hỗ trợ.
2. Đọc `locale.getUnicodeLocaleType("nu")` khi `nu` có ý nghĩa với dữ liệu.
3. Chỉ quảng cáo `getAvailableLocales` khi thực sự có coverage tương ứng.
4. Cân nhắc override `isSupportedLocale` nếu cần phân biệt extensions cụ thể.
5. Chọn symbols, zero digit và separators phù hợp với numbering system.
6. Kiểm thử cả **format lẫn parse**, vì một chuỗi có thể hiển thị đẹp nhưng không parse được nhất quán.

`DecimalFormatSymbols.setZeroDigit(char)` được dùng khi hệ chữ số có dãy tương ứng; không phải mọi hệ số học của thế giới có thể quy về mười `char` liên tiếp. Với requirement phức tạp, cần xem giới hạn formatter và thư viện hỗ trợ phù hợp.

## 8. Formatting và parsing phải được kiểm tra riêng

Nếu app hiển thị `"12|345:67"` bằng provider mẫu, **`Double.parseDouble("12|345:67")` sẽ không hiểu nó** như số theo locale. `Double.parseDouble` dùng cú pháp số chuẩn không tùy biến theo locale; giá trị formatted nên được parse bằng một formatter được cấu hình symbols tương ứng, nếu nghiệp vụ thật sự cần nhận số localized.

Mẫu kiểm tra parser đọc hết input:

```java
// Mảnh code tích hợp; cần import java.text.ParsePosition,
// java.text.DecimalFormat và java.text.DecimalFormatSymbols.
DecimalFormatSymbols symbols = DecimalFormatSymbols.getInstance(locale);
DecimalFormat format = new DecimalFormat("#,##0.00", symbols);
format.setParseBigDecimal(true);

String input = "12|345:67";
ParsePosition position = new ParsePosition(0);
Number parsed = format.parse(input, position);
if (parsed == null || position.getIndex() != input.length()) {
    throw new IllegalArgumentException("Invalid localized number");
}
```

Điều này kiểm tra **có nhận toàn bộ chuỗi hay không**, nhưng chưa tự đảm bảo grouping strictness hay tính hợp lệ nghiệp vụ. Nếu parser được cấu hình lenient, nó có thể chấp nhận những chuỗi không theo đúng bố cục bạn muốn. Trên JDK mới có thêm API điều khiển parsing strictness; nếu hệ hỗ trợ Java 17, hãy viết validation phù hợp phiên bản mục tiêu.

Bộ symbols phải được thiết kế để không gây nhầm lẫn, ví dụ dấu grouping và decimal **khác nhau**. Percent, per-mille, currency symbol, negative prefix/suffix và zero digit cũng cần test.

Với dữ liệu machine-to-machine, hãy dùng JSON numeric/BigDecimal hay giao thức có cú pháp xác định, **không dùng output localized** như giá trị lưu trữ hoặc khóa định danh.

## 9. Cài provider trên module path

Trên classpath, provider được đăng ký bằng `META-INF/services` như ví dụ. Trên **JPMS module path**, có thể dùng `module-info.java` với `provides`:

```java
// module-info.java minh họa cho provider module:
module demo.symbols.provider {
    provides java.text.spi.DecimalFormatSymbolsProvider
        with demo.spi.CustomSymbolsProvider;
}
```

Đoạn này là **module descriptor minh họa**, chưa phải một dự án module chạy độc lập. Provider implementation phải có class đúng tên/visibility, module phải được runtime resolve và nhận diện theo service loading, và ứng dụng vẫn phải chọn nguồn `SPI` trong `java.locale.providers` khi muốn dùng SPI.

**Không nhầm `ServiceLoader` với locale service lookup:** `ServiceLoader.load(DecimalFormatSymbolsProvider.class)` có thể tìm thấy implementation, nhưng `DecimalFormatSymbols.getInstance(locale)` còn chịu điều kiện provider order và locale support. Việc service class tồn tại không bảo đảm nó được chọn.

Không cần patch module `java.base` hay sửa các class JDK để cài một provider.

## 10. Thiết kế provider an toàn và dễ bảo trì

### 10.1. Trả object mới, không chia sẻ DecimalFormatSymbols mutable

`DecimalFormatSymbols` có setter và là mutable object. Một provider trả static singleton dùng chung có thể khiến một caller sửa separators và gây hiệu ứng bất ngờ trên caller khác.

```java
// Anti-pattern minh họa: không sử dụng trong production.
private static final DecimalFormatSymbols SHARED =
        DecimalFormatSymbols.getInstance(Locale.ROOT);

@Override
public DecimalFormatSymbols getInstance(Locale locale) {
    return SHARED;
}
```

Mảnh này chưa phải class độc lập. Provider đúng contract cần trả **instance mới**, hoặc clone dữ liệu nền phù hợp trong mọi lần gọi, và kiểm tra locale yêu cầu.

### 10.2. Không dùng DecimalFormat static chung giữa các threads

`DecimalFormat` mutable, không được đảm bảo thread-safe nếu chia sẻ cùng instance có thay đổi trạng thái. Trong ứng dụng web nhiều luồng, nên tạo formatter cho mỗi operation/request, hoặc đồng bộ nếu thật sự dùng chung. Không thay symbols của formatter mà một thread khác đang sử dụng.

### 10.3. Tránh hiệu năng bất định và tác dụng phụ

`getInstance(locale)` có thể được gọi nhiều lần. Nếu implementation liên tục tải dữ liệu từ network/file mà không có cache hoặc timeout thích hợp, formatting một con số có thể trở thành thao tác chậm, dễ lỗi I/O hoặc gây DoS nội bộ.

Thiết kế nên:

- Dùng dữ liệu locale có nguồn đáng tin cậy và được kiểm thử.
- Cache **immutable data**, không cache rồi trả cùng mutable symbols instance.
- Có policy rõ cho update/version của locale data.
- Trả lỗi khi dữ liệu không phù hợp thay vì đoán và format sai.
- Không log giá trị tiền tệ/cấu hình nhạy cảm trong lỗi và traces.
- Đảm bảo symbols của một locale ổn định đủ để parser/formatter thống nhất.

### 10.4. Locale data và phiên bản JDK

JDK có thể cập nhật CLDR data khi nâng phiên bản, khiến separators, currency symbols hay locale coverage thay đổi. Ứng dụng phải test trên JDK deploy thực tế, và phân biệt output **được bảo đảm bởi custom provider** với output **phụ thuộc CLDR/OS**.

**Không dùng `COMPAT`/`JRE` locale-data sources lỗi thời** làm giải pháp mới. Trên JDK hiện hành các legacy providers đó đã bị loại bỏ; dùng CLDR/SPI/HOST theo tài liệu hiện tại.

## 11. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Giải pháp |
| --- | --- | --- |
| Custom provider không có hiệu lực | JVM mặc định dùng CLDR; `SPI` không được bật. | Khởi chạy `-Djava.locale.providers=SPI,CLDR`. |
| App thấy service qua `ServiceLoader` nhưng symbols không đổi | Locale data lookup chọn CLDR trước hoặc locale unsupported. | Kiểm tra property và `getAvailableLocales`. |
| `ServiceConfigurationError` khi load | Tên service file/class sai, provider class không truy cập được, constructor sai. | Kiểm tra classpath, descriptor UTF-8, tên đầy đủ. |
| File nằm sai vị trí trong JAR | `META-INF/services` không được đóng gói đúng. | Kiểm tra `jar tf provider.jar` và build resources. |
| Provider trả `null` | Vi phạm contract `getInstance`, caller không có symbols hợp lệ. | Trả instance mới hoặc báo lỗi cụ thể. |
| `IllegalArgumentException` khi gọi provider trực tiếp | Locale ngoài tập supported. | Kiểm tra `isSupportedLocale`/`getAvailableLocales`. |
| Vòng đệ quy / `StackOverflowError` | Provider lấy baseline từ `getInstance` cho locale chính nó cung cấp. | Lấy baseline độc lập hoặc locale không do provider phục vụ. |
| Thay property giữa runtime nhưng output không đổi | Provider order đã được cache. | Đặt property trên launcher `java -D...`. |
| `en-US` vẫn dùng dấu thông thường dù provider có `en-US` | `CLDR` đứng trước `SPI`. | Kiểm tra thứ tự nguồn, không nhầm đăng ký với ưu tiên. |
| Tự sửa `"#,##0.00"` thành `"#|##0:00"` | Nhầm pattern syntax với output symbols. | Giữ non-localized pattern và cấu hình symbols. |
| `NumberFormat.getNumberInstance` không cho kết quả như kỳ vọng | `NumberFormatProvider` là SPI riêng. | Tạo `DecimalFormat` trực tiếp hoặc thiết kế đúng provider cần thiết. |
| Parsing chấp nhận một prefix số | Parser lenient hoặc chưa kiểm tra hết input. | Dùng `ParsePosition` và validation/strict policy. |
| Decimal/grouping separators trùng nhau | Parser không phân biệt các thành phần. | Chọn ký hiệu khác nhau, test round trip. |
| Locale `-u-nu-` bị bỏ qua | Provider chỉ kiểm tra base locale. | Tôn trọng extension numbering systems. |
| Currency format khác number format | Monetary separators và currency settings riêng. | Kiểm tra và test cả monetary symbols. |
| Shared `DecimalFormat` có kết quả thất thường | Chia sẻ formatter mutable giữa threads. | Mỗi request dùng formatter riêng. |
| Sau khi nâng JDK, snapshot test đổi | CLDR version và locale data thay đổi. | Có regression tests và pin JDK trong triển khai. |
| Provider module không được nhìn thấy | Thiếu `provides`, module chưa resolve hoặc thiếu classpath/module path. | Kiểm tra module descriptor và service discovery. |

## 12. Checklist khi triển khai

1. Có thật sự cần provider ở mức JVM hay chỉ cần symbols riêng một nơi?
2. Provider kế thừa đúng `java.text.spi.DecimalFormatSymbolsProvider`?
3. `getAvailableLocales()` chỉ liệt kê locales được hỗ trợ có thực?
4. `getInstance` kiểm tra null/unsupported locale, trả symbols instance **mới**?
5. Provider tránh recursive lookup khi dựng baseline?
6. Decimal/group separators hợp lệ, khác nhau và không gây parsing ambiguity?
7. Đã cấu hình monetary separators, currency metadata, zero digit và signs tương ứng nếu cần?
8. Đã xét `-u-nu-`/Unicode locale extensions trong input?
9. Đã tạo đúng `META-INF/services/java.text.spi.DecimalFormatSymbolsProvider` UTF-8?
10. Service descriptor và implementation class nằm trên đúng classpath hoặc module path?
11. Đã đặt `java.locale.providers` trên **JVM launcher**, có `SPI` ở vị trí mong muốn?
12. Đã test locale synthetic chỉ do SPI hỗ trợ và locale sẵn có ở CLDR?
13. Đã test trực tiếp `DecimalFormatSymbols.getInstance` thay vì suy luận từ `NumberFormatProvider`?
14. Đã phân biệt non-localized pattern và localized symbols?
15. Format lẫn parse có round-trip được trên dữ liệu mẫu, kể cả negative/percent/currency?
16. Đã tránh dùng localized display strings làm dữ liệu tài chính hoặc protocol?
17. Formatter và symbols mutable có được dùng đúng trong môi trường nhiều threads?
18. Đã kiểm thử khác biệt JDK/CLDR versions và bố trí test regression?
19. Không dựa vào các nguồn locale legacy đã bị loại bỏ?

## 13. Bài tập thực hành

**Bài A — Đổi provider order.** Chạy `SPI,CLDR` và `CLDR,SPI` từ ví dụ, ghi lại bốn dòng output của mỗi lệnh. Giải thích vì sao `en-US` đổi nguồn còn `zz-ZZ` vẫn dùng SPI trong JDK thử nghiệm.

**Bài B — Không có SPI.** Chạy app mà không đặt `-Djava.locale.providers`. Dự đoán tác động của cấu hình CLDR mặc định; đừng sửa code bằng cách gọi trực tiếp `new CustomSymbolsProvider()` vì như vậy không còn kiểm tra discovery.

**Bài C — Đổi supported locales.** Bỏ `Locale.US` trong `getAvailableLocales`. Chạy lại `SPI,CLDR` và quan sát `en-US` còn do custom provider phục vụ không. Kiểm tra `getInstance` phải từ chối locale unsupported.

**Bài D — Symbols khác.** Đổi dấu nhóm thành dấu cách và dấu thập phân thành `','`. Chạy `DecimalFormat("#,##0.00", symbols)` với số mẫu; không thay pattern syntax.

**Bài E — Parsing.** Dùng `ParsePosition` để kiểm tra toàn bộ `"12|345:67"` được parse. Thêm phần đuôi không phải số; xác nhận policy reject khi chưa tiêu thụ hết input.

**Bài F — Unicode extension.** Xem xét `ar-u-nu-arab` và `ar-u-nu-latn`. Viết policy phân biệt numbering systems, và kiểm tra ý nghĩa của `isSupportedLocale` mặc định.

**Bài G — JPMS.** Viết provider module sử dụng `provides ... with ...`, chạy từ module path với `SPI`, và so sánh với classpath service registration.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `DecimalFormatSymbolsProvider` và `DecimalFormatSymbols` khác nhau như thế nào?

**Đáp án:** Provider là SPI factory theo locale; `DecimalFormatSymbols` là một object dữ liệu mutable được formatter sử dụng.

**Câu 2.** Có provider trong JAR, tại sao `en-US` vẫn dùng CLDR?

**Đáp án:** Provider order quyết định ưu tiên. Mặc định là CLDR; cần đưa `SPI` vào `java.locale.providers` và chọn thứ tự nếu muốn custom provider thắng.

**Câu 3.** File `META-INF/services` tên class nào?

**Đáp án:** Fully qualified service type name là `java.text.spi.DecimalFormatSymbolsProvider`, còn nội dung file chứa implementation name `demo.spi.CustomSymbolsProvider`.

**Câu 4.** Vì sao provider demo lấy baseline từ `Locale.ROOT`?

**Đáp án:** Vì nó không khai báo hỗ trợ ROOT; lấy symbols cho locale provider hỗ trợ (như en-US) khi SPI ưu tiên có thể gọi lại chính provider và tạo vòng đệ quy.

**Câu 5.** Có nên trả singleton `DecimalFormatSymbols` mutable?

**Đáp án:** Không. Hợp đồng `getInstance` yêu cầu instance mới; reuse cùng object có thể khiến các caller thay đổi ký hiệu của nhau.

**Câu 6.** Khi symbol decimal là `':'` và grouping là `'|'`, có phải đổi pattern thành `"#|##0:00"` không?

**Đáp án:** Không. `DecimalFormat` dùng cú pháp non-localized `"#,##0.00"` rồi áp dụng symbols cho output.

**Câu 7.** `NumberFormat.getNumberInstance(locale)` có bắt buộc dùng `DecimalFormatSymbolsProvider` không?

**Đáp án:** Không nên giả định. `NumberFormatProvider` và quá trình tạo formatter là một SPI/factory path riêng; hãy kiểm chứng đúng đường code ứng dụng sử dụng.

**Câu 8.** Nếu locale có Unicode extension `u-nu` thì sao?

**Đáp án:** Extension có thể yêu cầu numbering system khác. Provider cần xử lý hoặc có policy từ chối/không hỗ trợ rõ ràng, không tự bỏ qua rồi trả ký hiệu sai.

## 15. Tài liệu chính thức hiện hành

- [DecimalFormatSymbolsProvider — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/spi/DecimalFormatSymbolsProvider.html): class SPI, `getInstance`, locale coverage.
- [LocaleServiceProvider — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/spi/LocaleServiceProvider.html): packaging, supported locales, Unicode extensions, provider order và property `java.locale.providers`.
- [DecimalFormatSymbols — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/DecimalFormatSymbols.html): các ký hiệu số/tiền tệ.
- [DecimalFormat — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/DecimalFormat.html): pattern, localized symbols, formatting/parsing.
- [NumberFormatProvider — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/spi/NumberFormatProvider.html): SPI cung cấp number formatter.
- [Locale — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.html): BCP 47/Unicode extensions.
- [JDK 26 Supported Locales](https://www.oracle.com/java/technologies/javase/jdk26-supported-locales.html): CLDR, SPI, HOST, và tình trạng locale providers legacy.
- [ServiceLoader — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html): đăng ký/cung cấp service implementation.

**Ghi nhớ:** `DecimalFormatSymbolsProvider` cung cấp **bộ ký hiệu** định dạng số, không phải bản thân formatter. Phải khai báo supported locales, trả instance mới, đăng ký service, và **bật `SPI` trong provider order lúc JVM khởi chạy**. Bộ ký hiệu hiển thị và pattern syntax là hai lớp khác nhau; định dạng số cho UI cũng khác dữ liệu numeric cho tính toán. Những quy tắc này vẫn là kiến thức Java hiện hành, không phụ thuộc các locale-data providers legacy.

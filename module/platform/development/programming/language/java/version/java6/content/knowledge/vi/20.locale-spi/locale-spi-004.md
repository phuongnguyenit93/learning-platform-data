# LocaleNameProvider và tên hiển thị ngôn ngữ, quốc gia

## 1. Vì sao có LocaleNameProvider?

Một ứng dụng đa ngôn ngữ có thể lưu mã locale theo chuẩn BCP 47, ví dụ `vi-VN`, `fr-FR` hay `en-US`. Nhưng khi hiển thị danh sách ngôn ngữ/quốc gia cho người dùng, ứng dụng thường muốn tên dễ đọc, không phải chỉ mã.

~~~text
Locale đích:     fr-FR
Mã ngôn ngữ:     fr
Mã vùng:         FR

Hiển thị bằng tiếng Anh (en-US):
    language -> French
    country  -> France

Hiển thị bằng tiếng Pháp (fr-FR):
    language -> français
    country  -> France
~~~

`java.util.Locale` đã có các phương thức `getDisplayLanguage(Locale)`, `getDisplayCountry(Locale)`, `getDisplayScript(Locale)` và `getDisplayVariant(Locale)` cho nhu cầu này. Java thường cung cấp dữ liệu tên locale từ **CLDR (Common Locale Data Repository)**.

Tuy nhiên có khi sản phẩm cần **tên hiển thị tùy biến**, chẳng hạn:

- Tên ngôn ngữ/vùng trong một bộ từ điển nghiệp vụ.
- Một mã thử nghiệm, mã nội bộ hợp lệ về mặt cấu trúc, nhưng không có display name trong locale data chuẩn.
- Tên vùng hay tên biến thể dùng riêng cho một giao diện sản phẩm.
- Cung cấp thêm dữ liệu cho những locale hiển thị chưa được JDK hỗ trợ đủ.
- Điều chỉnh cách ứng dụng gắn nhãn language/region trong khi vẫn sử dụng API `Locale.getDisplay...` chuẩn.

Java cung cấp **`java.util.spi.LocaleNameProvider`** (một subclass của `java.util.spi.LocaleServiceProvider`) để có thể bổ sung tên hiển thị ngôn ngữ, quốc gia/khu vực, biến thể, script và một số Unicode locale extensions.

**Điều quan trọng của bài học:** đây là **SPI cho tên hiển thị của mã locale**, không phải cơ chế dịch các câu văn/nút bấm thông thường; không thay cho `ResourceBundle`. API `LocaleNameProvider` đã có từ Java 6 và **vẫn còn áp dụng trong Java SE 26**. Ví dụ chính dùng JDK 17+ để tránh kiến thức hoặc cấu hình đã lỗi thời.

## 2. Hai đối tượng Locale có vai trò khác nhau

Xét:

~~~java
Locale target = Locale.forLanguageTag("fr-FR");
Locale displayLocale = Locale.forLanguageTag("en-US");

String name = target.getDisplayLanguage(displayLocale);
~~~

Đây là **đoạn trích**, giả định `import java.util.Locale;`.

- `target` là **locale đang được mô tả**. Nó có mã ngôn ngữ `fr` và mã khu vực `FR`.
- `displayLocale` là **ngôn ngữ/locale người đọc muốn thấy tên hiển thị**, ở đây `en-US`.
- `name` thường là `"French"` theo dữ liệu tiếng Anh của JDK, nhưng dữ liệu localized name có thể khác giữa JDK/CLDR versions hoặc do SPI tùy biến.

Trong `LocaleNameProvider`:

~~~java
String getDisplayLanguage(String languageCode, Locale locale)
String getDisplayCountry(String countryCode, Locale locale)
~~~

`languageCode` và `countryCode` là mã **cần đặt tên**; tham số `locale` lại là **locale dùng để trình bày tên**.

Ví dụ nếu caller yêu cầu tên tiếng Anh của một mã tiếng Việt:

~~~text
languageCode="vi"  -> tên hiển thị, ví dụ "Vietnamese"
locale=en-US       -> tên được trình bày bằng tiếng Anh
~~~

**Không nhầm** `locale` trong callback với `Locale` đang được mô tả. Nếu provider cần đọc dictionary trong database, thường nên tra theo cặp `(displayLocale, code)`, không tra theo code ngôn ngữ của target một cách đơn lẻ.

### 2.1. Ngôn ngữ, script, vùng và variant

Một `Locale` có thể chứa:

| Thành phần | Ví dụ | API lấy mã |
| --- | --- | --- |
| Language | `vi`, `fr`, `en` | `getLanguage()` |
| Script | `Latn`, `Cyrl` | `getScript()` |
| Region/country | `VN`, `FR`, `US`; có thể là mã UN M.49 ba chữ số | `getCountry()` |
| Variant | Một nhãn variant hợp lệ theo quy tắc Locale/BCP 47 | `getVariant()` |
| Unicode locale extensions | Ví dụ khóa `nu` và giá trị hệ chữ số | `getUnicodeLocaleKeys()`, `getUnicodeLocaleType(key)` |

Các phương thức `Locale.getDisplay...` trả **tên hiển thị** khi có dữ liệu phù hợp; nếu không có, API có các cơ chế fallback, có thể đến tên tiếng Anh hoặc mã gốc. Vì vậy một caller không nên mặc định “mọi tên đã được dịch đầy đủ sang ngôn ngữ yêu cầu”.

### 2.2. getDisplayName() tổng hợp các thành phần

`Locale.getDisplayName(displayLocale)` ghép các display names của language, script, country, variant và một số extensions thành một tên tổng hợp. Kết quả có thể chứa dấu ngoặc, dấu phẩy và cách phân tách tùy dữ liệu locale. Hãy **test các thành phần riêng** khi kiểm thử một `LocaleNameProvider`, thay vì chỉ so sánh cả chuỗi `getDisplayName` theo một layout cố định trên mọi JDK.

## 3. API chính của LocaleNameProvider

`LocaleNameProvider` là **abstract class**:

~~~java
public abstract class LocaleNameProvider extends LocaleServiceProvider {
    public abstract String getDisplayLanguage(String languageCode, Locale locale);
    public abstract String getDisplayCountry(String countryCode, Locale locale);
    public abstract String getDisplayVariant(String variant, Locale locale);
    public String getDisplayScript(String scriptCode, Locale locale);
    public String getDisplayUnicodeExtensionKey(String key, Locale locale);
    public String getDisplayUnicodeExtensionType(String type, String key, Locale locale);
}
~~~

Đây là **phác thảo chữ ký các phương thức để học**, không phải class Java đầy đủ để dán và chạy. Các phương thức `getDisplayScript` và Unicode extension methods đã có default implementation trả `null`, còn các phương thức ngôn ngữ, quốc gia, variant phải được triển khai ở subclass cụ thể.

| Method | Input chính | Dữ liệu trả về |
| --- | --- | --- |
| `getDisplayLanguage(String, Locale)` | Mã language như `"qzz"` và display locale | Tên ngôn ngữ đã localized hoặc `null` nếu provider không có |
| `getDisplayCountry(String, Locale)` | Mã region như `"ZZ"` và display locale | Tên quốc gia/khu vực hoặc `null` |
| `getDisplayVariant(String, Locale)` | Mã variant và display locale | Tên variant hoặc `null` |
| `getDisplayScript(String, Locale)` | Script code Title Case như `"Qaaa"` và display locale | Tên script hoặc `null`; default implementation trả `null` |
| `getDisplayUnicodeExtensionKey(String, Locale)` | Unicode extension key và display locale | Tên khóa localized hoặc `null`; API từ Java 10 |
| `getDisplayUnicodeExtensionType(String, String, Locale)` | Extension type, key và display locale | Tên type localized hoặc `null`; API từ Java 10 |
| `getAvailableLocales()` *(kế thừa)* | Không có | Các **display locales** mà provider có thể hỗ trợ |
| `isSupportedLocale(Locale)` *(kế thừa)* | Một display locale | Provider có hỗ trợ locale này hay không |

Một số phương thức `getDisplay...` yêu cầu input code đúng cấu trúc, không `null`, và yêu cầu display locale nằm trong tập được công bố là hỗ trợ. Khi gọi trực tiếp API provider không đúng hợp đồng, có thể có `NullPointerException` hoặc `IllegalArgumentException` theo Javadoc.

### 3.1. getAvailableLocales nói về locale của bản dịch tên

Giả sử provider có thể đặt tên cho mã language `qzz` bằng tiếng Anh-Mỹ, nhưng không có bản dịch sang tiếng Pháp. Khi ấy:

~~~java
@Override
public Locale[] getAvailableLocales() {
    return new Locale[] { Locale.US };
}
~~~

Điều này nghĩa **provider cung cấp display names cho locale `en-US`**, **không** nghĩa provider chỉ được cung cấp tên của ngôn ngữ “English”. Nó vẫn có thể đặt tên cho `qzz`, `vi`, `de`... bằng tiếng Anh nếu có dữ liệu.

Đây là nhầm lẫn phổ biến: `getAvailableLocales()` **không phải danh sách mã ngôn ngữ cần hiển thị**. Phạm vi của nó là những locale mà provider **có thể sử dụng để dịch tên**.

Trong ví dụ, chỉ công bố `Locale.US` để test có kết quả ổn định. Với production, mỗi display locale trả về nên thực sự có dictionary/truy vấn hỗ trợ. Không trả hàng trăm locales nếu thực tế chỉ có data cho một locale.

### 3.2. isSupportedLocale và extensions

`LocaleServiceProvider.isSupportedLocale(locale)` mặc định kiểm tra locale có trong `getAvailableLocales`, **bỏ qua extensions** khi so sánh. Nếu việc hỗ trợ có phụ thuộc Unicode extension (ví dụ chính sách riêng cho một extension), provider có thể override `isSupportedLocale`.

Không override tùy tiện chỉ để luôn trả `true`: khi đó Java có thể gọi callback cho display locales mà provider không thực sự có dữ liệu, khiến fallback kém rõ ràng.

### 3.3. Return null khi không có tên

Với **provider cung cấp display names**, `return null` là một kết quả **hợp lệ** khi không có tên cho mã và display locale được yêu cầu. Framework có thể thử provider/locale fallback khác. **Không tự dịch mọi mã không biết thành chuỗi rỗng**: `""` là một giá trị String được trả, khác với `null` báo chưa có tên.

Trong bài test, callback cho mã `qzx` trả `null`. `Locale.getDisplayLanguage(Locale.US)` của mã đó fallback cuối cùng sang chính code `qzx`. Điều này minh họa sự khác nhau giữa:

- **Lời gọi callback trực tiếp:** provider có thể trả `null`.
- **API người dùng `Locale`:** áp dụng cơ chế tìm kiếm/fallback để trả display text cuối cùng.

### 3.4. Country là region code

`getDisplayCountry` nhận mã khu vực theo BCP 47: thông thường là **hai chữ Latin viết hoa** như `US`, `FR`, `VN`, hoặc **ba chữ số** của UN M.49 trong các trường hợp phù hợp. Nó không nhận một tên như `"United States"` làm country code.

`getDisplayLanguage` nhận language code chữ thường; `getDisplayScript` nhận script code bốn chữ cái dạng Title Case như `Latn`; variant theo biểu diễn của `Locale`.

**Không chuyển country/language code về chữ hoa/thường tùy ý ở phía caller khi đã có `Locale`.** Sử dụng `target.getLanguage()`, `target.getCountry()`, `target.getScript()` để lấy dạng chuẩn từ `Locale`, và để JDK gọi callback như thiết kế.

## 4. Dữ liệu locale đi qua CLDR, SPI, HOST thế nào?

Java hiện đại có các nguồn locale data (provider adapters) chính:

| Tên | Vai trò |
| --- | --- |
| `CLDR` | Dữ liệu locale chuẩn được JDK cung cấp, dựa trên Unicode CLDR |
| `SPI` | Các provider Java triển khai `LocaleServiceProvider`, bao gồm `LocaleNameProvider` |
| `HOST` | Dữ liệu settings của hệ điều hành khi JDK và nền tảng hỗ trợ |

**Từ JDK hiện đại, CLDR là default.** Trong Java SE 26, mặc định tương đương cấu hình `CLDR`. Để một provider của ứng dụng được chọn trên **classpath**, bạn cần thêm `SPI` vào thứ tự tại **lúc JVM khởi động**:

~~~text
-Djava.locale.providers=SPI,CLDR
~~~

Với cấu hình đó, Java thử SPI trước; nếu SPI không có tên phù hợp, Java có thể dùng dữ liệu CLDR. Nếu cấu hình `CLDR,SPI`, dữ liệu CLDR có thể được ưu tiên trước với những display locales/name mà CLDR đã hỗ trợ.

**Không dùng ví dụ cấu hình cũ như `JRE,SPI` hay `COMPAT`**: provider adapter COMPAT/JRE cũ đã bị loại bỏ trong JDK hiện đại; hãy theo tài liệu của JDK đang chạy.

### 4.1. Đặt property ở launcher, không dựa vào System.setProperty

Thứ tự locale providers được JVM đọc và cache khi hệ thống locale service khởi tạo. Do đó:

~~~bash
java '-Djava.locale.providers=SPI,CLDR' -cp out demo.LocaleNamesDemo
~~~

là cách xác định lựa chọn trước khi chương trình chạy. Không coi:

~~~java
System.setProperty("java.locale.providers", "SPI,CLDR");
~~~

là cách đổi provider order đáng tin **sau khi JVM đã khởi tạo locale services**. Đây là **đoạn minh họa cảnh báo**, không phải hướng dẫn bật SPI ở runtime. Thử nghiệm nên đặt `-D...` ở dòng lệnh của một **JVM mới**.

### 4.2. CLDR và kết quả hiển thị có thể thay đổi

JDK có thể nâng phiên bản CLDR khi phát hành. Các tên language/country theo localization data vì thế có thể thay đổi cách viết hoặc cách trình bày theo thời gian. **Không hard-code assertion “French luôn phải viết y hệt một chuỗi”** cho mọi phiên bản JDK và locale.

Với test provider của bài này, chọn **mã thử nghiệm riêng** và giá trị custom do ta kiểm soát, sau đó assert đúng những giá trị đó. Các tên chuẩn của CLDR chỉ được dùng làm fallback, không phải hợp đồng nội dung cố định của một application provider.

### 4.3. Locale fallback khi thiếu dữ liệu

Nếu một provider chỉ hỗ trợ display locale `en-US`, yêu cầu hiển thị bằng `en-US` có thể dùng provider. Nếu caller yêu cầu `en-GB` và provider không khai báo hỗ trợ, JDK có thể xét các candidate locales và data sources khác; khi đó **không bảo đảm** sẽ dùng exact entry của `en-US`.

Nếu muốn hỗ trợ nhiều biến thể tiếng Anh một cách chủ ý, đưa các display locales tương ứng vào `getAvailableLocales` (hoặc override `isSupportedLocale` với contract phù hợp). Đừng hy vọng framework tự xem mọi locale có language `en` là giống `en-US`.

## 5. Đăng ký LocaleNameProvider trên classpath

Đối với dự án classpath/unnamed module, Java dùng file Service Provider Configuration:

~~~text
META-INF/services/java.util.spi.LocaleNameProvider
~~~

Nội dung file là **tên class provider đầy đủ**, mỗi dòng một tên:

~~~text
demo.spi.CustomLocaleNames
~~~

File là **UTF-8 text**. Provider class phải là implementation hợp lệ, có khả năng được ServiceLoader khởi tạo, và nằm trên classpath của JVM cùng với resource `META-INF/services/...`.

Sơ đồ:

~~~text
Application
    |
    v
Locale.getDisplayLanguage(Locale.US)
    |
    v
Java locale service resolution
    |
    +--> SPI (nếu được bật và ưu tiên)
    |     |
    |     +--> META-INF/services/java.util.spi.LocaleNameProvider
    |     |     |
    |     |     +--> demo.spi.CustomLocaleNames
    |     |
    |     +--> getAvailableLocales()
    |     +--> getDisplayLanguage("qzz", Locale.US)
    |
    +--> CLDR fallback khi cần
    |
    v
Localized display name
~~~

**Hai điều kiện cùng cần:** file service cấu hình **đúng** và JVM **được bật SPI**. Có file `META-INF/services` không đủ nếu chạy JDK hiện đại mặc định chỉ dùng `CLDR`.

## 6. Code Java 17+ hoàn chỉnh: provider tên hiển thị riêng

Để kiểm thử rõ ràng, ta sử dụng mã **giả lập phục vụ bài học**:

- Language `qzz`: mã ba chữ cái trong vùng được dùng cho mục đích thử nghiệm/private use, ở đây đặt tên “Example Language”.
- Country/region `ZZ`: mã vùng giả lập, đặt tên “Example Territory”.
- Script `Qaaa`: mã script thử nghiệm, đặt tên “Example Script”.
- Variant `CUSTOM`: biến thể ví dụ, đặt tên “Custom Edition”.
- **Display locale**: `en-US`, tức `Locale.US`.

Đừng hiểu các tên “Example...” là tên chính thức của quốc gia/ngôn ngữ hay bản dịch CLDR. Chúng được chọn để **nhận biết chắc chắn SPI của ứng dụng đã được gọi**, không vô tình dựa vào dữ liệu JDK.

### 6.1. Cấu trúc dự án

~~~text
locale-name-demo/
├── src/
│   └── demo/
│       ├── LocaleNamesDemo.java
│       └── spi/
│           └── CustomLocaleNames.java
└── out/
    ├── demo/... (.class sau khi biên dịch)
    └── META-INF/
        └── services/
            └── java.util.spi.LocaleNameProvider
~~~

Chỉ cần JDK 17+, không cần Maven, Gradle hay dependency ngoài. Tạo service file trong `out` để dễ chạy trực tiếp; với JAR production phải đóng gói file ấy vào bên trong JAR.

### 6.2. File src/demo/spi/CustomLocaleNames.java

~~~java
package demo.spi;

import java.util.Locale;
import java.util.spi.LocaleNameProvider;

public final class CustomLocaleNames extends LocaleNameProvider {
    private static final Locale DISPLAY = Locale.US;

    @Override
    public Locale[] getAvailableLocales() {
        return new Locale[] { DISPLAY };
    }

    @Override
    public String getDisplayLanguage(String code, Locale inLocale) {
        return DISPLAY.equals(inLocale) && "qzz".equals(code)
                ? "Example Language" : null;
    }

    @Override
    public String getDisplayCountry(String code, Locale inLocale) {
        return DISPLAY.equals(inLocale) && "ZZ".equals(code)
                ? "Example Territory" : null;
    }

    @Override
    public String getDisplayVariant(String code, Locale inLocale) {
        return DISPLAY.equals(inLocale) && "CUSTOM".equals(code)
                ? "Custom Edition" : null;
    }

    @Override
    public String getDisplayScript(String code, Locale inLocale) {
        return DISPLAY.equals(inLocale) && "Qaaa".equals(code)
                ? "Example Script" : null;
    }
}
~~~

**Các điểm quan trọng:**

1. `public final class` có public no-arg constructor ngầm định vì không khai báo constructor khác, phù hợp cho service instantiation trên classpath.
2. `extends LocaleNameProvider`, không implement `LocaleNameProvider` như interface (nó là abstract class).
3. `getAvailableLocales()` trả mảng mới chứa `Locale.US`. Không khai báo `Locale.FRANCE` vì provider không có tên tiếng Pháp.
4. Các callback kiểm tra **display locale** trước khi trả tên cho code được biết.
5. Không có dữ liệu thì trả **`null`**, cho phép Java thử nguồn/candidate khác.
6. `getDisplayScript(...)` không bắt buộc phải override vì có default trả `null`; ví dụ override để chứng minh có thể tùy biến script.
7. Không sử dụng mutable static Map hay state giữa requests; provider có thể được dùng đồng thời trong ứng dụng.

Trong ứng dụng thật, thay các điều kiện code bằng **immutable lookup table hoặc repository snapshot** theo `(display locale, code)`. Tên ngôn ngữ/quốc gia không phải mật khẩu, nhưng dữ liệu do người quản trị nhập vẫn phải được kiểm tra phù hợp trước khi render vào HTML hoặc log.

### 6.3. File src/demo/LocaleNamesDemo.java

~~~java
package demo;

import demo.spi.CustomLocaleNames;
import java.util.Locale;
import java.util.ServiceLoader;
import java.util.spi.LocaleNameProvider;

public final class LocaleNamesDemo {
    static void check(boolean condition, String description) {
        if (!condition) throw new AssertionError(description);
    }

    public static void main(String[] args) {
        Locale display = Locale.US;
        Locale target = Locale.forLanguageTag("qzz-Qaaa-ZZ-CUSTOM");
        LocaleNameProvider provider = ServiceLoader.load(LocaleNameProvider.class)
                .findFirst().orElseThrow();

        check(provider instanceof CustomLocaleNames, "service not discovered");
        System.out.println("service-found=true");
        check(provider.isSupportedLocale(display), "en-US not supported");
        check(!provider.isSupportedLocale(Locale.FRANCE), "fr-FR unexpectedly supported");
        System.out.println("en-US-supported=true");
        System.out.println("fr-FR-supported=false");

        String lang = target.getDisplayLanguage(display);
        String country = target.getDisplayCountry(display);
        String script = target.getDisplayScript(display);
        String variant = target.getDisplayVariant(display);
        System.out.println("language=" + lang);
        System.out.println("country=" + country);
        System.out.println("script=" + script);
        System.out.println("variant=" + variant);

        check("Example Language".equals(lang), "wrong language");
        check("Example Territory".equals(country), "wrong country");
        check("Example Script".equals(script), "wrong script");
        check("Custom Edition".equals(variant), "wrong variant");

        check(provider.getDisplayLanguage("qzx", display) == null,
                "expected null for an unknown name");
        check("qzx".equals(Locale.forLanguageTag("qzx").getDisplayLanguage(display)),
                "fallback-to-code mismatch");
        System.out.println("unknown-provider=null");
        System.out.println("unknown-locale=qzx");
        System.out.println("tests=PASS");
    }
}
~~~

**Phân biệt hai kiểu kiểm tra** trong file:

- `ServiceLoader.load(LocaleNameProvider.class).findFirst()` xác minh **service registration** trong fixture (chỉ có một provider trong classpath demo). Không dựa vào thứ tự `findFirst` nếu hệ thống có nhiều providers cùng loại.
- `target.getDisplayLanguage(display)`, `getDisplayCountry`, `getDisplayScript`, `getDisplayVariant` xác minh **Java Locale API thực sự sử dụng provider**, không chỉ xác minh có thể khởi tạo provider bằng constructor.

Một service có thể được ServiceLoader phát hiện nhưng **không bao giờ được `Locale` ưu tiên** nếu `java.locale.providers` không bật `SPI`, provider không hỗ trợ display locale, hoặc nguồn CLDR có ưu tiên cao hơn. Vì thế test thứ hai là bắt buộc để chứng minh tích hợp thật.

## 7. Biên dịch và chạy ứng dụng classpath

### 7.1. Linux/macOS (Bash)

Ở thư mục `locale-name-demo` có `src`:

~~~bash
mkdir -p out/META-INF/services
javac -encoding UTF-8 --release 17 -d out src/demo/spi/CustomLocaleNames.java src/demo/LocaleNamesDemo.java
printf 'demo.spi.CustomLocaleNames\n' > out/META-INF/services/java.util.spi.LocaleNameProvider
java '-Djava.locale.providers=SPI,CLDR' -cp out demo.LocaleNamesDemo
~~~

### 7.2. Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force 'out/META-INF/services' | Out-Null
javac -encoding UTF-8 --release 17 -d out src/demo/spi/CustomLocaleNames.java src/demo/LocaleNamesDemo.java
$serviceFile = 'out/META-INF/services/java.util.spi.LocaleNameProvider'
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($serviceFile, 'demo.spi.CustomLocaleNames' + [Environment]::NewLine, $utf8NoBom)
java '-Djava.locale.providers=SPI,CLDR' -cp out demo.LocaleNamesDemo
~~~

**Lưu ý UTF-8:** Service provider configuration file phải được ghi theo UTF-8. PowerShell phiên bản cũ có thể thêm BOM khi dùng một số lệnh ghi text; trong ví dụ dùng `UTF8Encoding($false)` để ghi **UTF-8 không BOM** tránh tình huống class name có ký tự BOM đầu dòng gây lỗi service discovery.

**Lưu ý tham số trên Windows PowerShell:** đặt nguyên tùy chọn `-Djava.locale.providers=SPI,CLDR` trong dấu nháy đơn để trình shell chuyển nguyên một argument cho Java launcher. Từ `-D...` phải nằm **trước tên class** trong lệnh `java`.

### 7.3. Kết quả được kiểm chứng

Chương trình đã **biên dịch/chạy thành công bằng OpenJDK 24 với `--release 17`**. Stdout chính xác:

~~~text
service-found=true
en-US-supported=true
fr-FR-supported=false
language=Example Language
country=Example Territory
script=Example Script
variant=Custom Edition
unknown-provider=null
unknown-locale=qzx
tests=PASS
~~~

Chạy test trên một JVM mới với `java.locale.providers=SPI,CLDR`; nếu không bật SPI mà chỉ dùng cấu hình default CLDR, các assertions về “Example Language” có thể thất bại, đúng như điều kiện thử nghiệm muốn phát hiện.

### 7.4. Tại sao unknown-locale=qzx?

`provider.getDisplayLanguage("qzx", Locale.US)` trả `null` vì provider không biết mã ấy. Khi gọi `Locale.forLanguageTag("qzx").getDisplayLanguage(Locale.US)`, hệ thống thử các nguồn dữ liệu locale và cuối cùng dùng mã `qzx` làm fallback nếu không có tên khác.

Khi thiết kế UI, không nên giả định mọi mã có display name thân thiện. Có thể biểu diễn mã chưa biết như `"qzx"`, đánh dấu chưa được dịch, hoặc đưa vào workflow quản lý bản dịch. Không chuyển `null` trả từ provider thành một tên sai hay một exception chỉ để “bắt buộc phải có chuỗi”.

## 8. Triển khai LocaleNameProvider trong named modules (JPMS)

Ngoài classpath, Java hiện đại hỗ trợ đăng ký locale-sensitive SPI bằng `module-info.java`. Trong một **named module chứa provider**, khai báo:

~~~java
module demo.names {
    provides java.util.spi.LocaleNameProvider with demo.names.CustomLocaleNames;
}
~~~

Không cần file `META-INF/services` để đăng ký provider trong trường hợp này. JVM phải **resolve provider module** và áp dụng provider-order có `SPI`; ví dụ dưới đây dùng `--add-modules demo.names` khi chạy để bảo đảm module provider có mặt trong module graph.

**Đừng nhầm** loại SPI này với `java.util.spi.ResourceBundleProvider`: ResourceBundleProvider dùng cho **bundle messages** của named modules, còn LocaleNameProvider là một **locale-sensitive name provider** được Java Locale APIs gọi khi cần tên hiển thị.

### 8.1. Cấu trúc hai named modules

~~~text
locale-module-demo/
└── src/
    ├── demo.names/
    │   ├── module-info.java
    │   └── demo/
    │       └── names/
    │           └── CustomLocaleNames.java
    └── demo.app/
        ├── module-info.java
        └── demo/
            └── app/
                └── App.java
~~~

### 8.2. Source của provider module

Tệp `src/demo.names/module-info.java`:

~~~java
module demo.names {
    provides java.util.spi.LocaleNameProvider with demo.names.CustomLocaleNames;
}
~~~

Tệp `src/demo.names/demo/names/CustomLocaleNames.java`:

~~~java
package demo.names;

import java.util.Locale;
import java.util.spi.LocaleNameProvider;

public final class CustomLocaleNames extends LocaleNameProvider {
    @Override
    public Locale[] getAvailableLocales() {
        return new Locale[]{Locale.US};
    }

    @Override
    public String getDisplayLanguage(String code, Locale inLocale) {
        return Locale.US.equals(inLocale) && "qzz".equals(code)
                ? "Example Language" : null;
    }

    @Override
    public String getDisplayCountry(String code, Locale inLocale) {
        return Locale.US.equals(inLocale) && "ZZ".equals(code)
                ? "Example Territory" : null;
    }

    @Override
    public String getDisplayVariant(String code, Locale inLocale) {
        return null;
    }
}
~~~

Khác với classpath demo đầy đủ, provider module nhỏ này chỉ cung cấp tên language/country. `getDisplayVariant` là abstract nên vẫn phải override; không có tên variant, nó trả `null`. `getDisplayScript` không bắt buộc implement vì đã có default implementation.

Provider class không nhất thiết export package ra bên ngoài nếu nó chỉ được cung cấp qua service `provides`. Việc đăng ký phải trỏ tới class provider hợp lệ. `module-info.java` dùng fully-qualified name chuẩn xác và được compiler kiểm tra.

### 8.3. Caller module và ứng dụng

Tệp `src/demo.app/module-info.java`:

~~~java
module demo.app {}
~~~

Tệp `src/demo.app/demo/app/App.java`:

~~~java
package demo.app;

import java.util.Locale;

public final class App {
    public static void main(String[] args) {
        Locale target = Locale.forLanguageTag("qzz-ZZ");
        String language = target.getDisplayLanguage(Locale.US);
        String country = target.getDisplayCountry(Locale.US);

        System.out.println("module-language=" + language);
        System.out.println("module-country=" + country);

        if (!"Example Language".equals(language)
                || !"Example Territory".equals(country)) {
            throw new AssertionError("module provider not used");
        }
        System.out.println("module-test=PASS");
    }
}
~~~

Ứng dụng dùng API `Locale` bình thường, không tự gọi `ServiceLoader` trong module consumer. Đây là cách Java locale subsystem dùng providers để tăng dữ liệu tên hiển thị. `demo.app` không cần import provider implementation hay export package provider.

### 8.4. Biên dịch và chạy named modules

Ở thư mục `locale-module-demo`, tạo `out` nếu cần:

~~~bash
mkdir -p out
~~~

hoặc PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
~~~

Lệnh biên dịch hai modules:

~~~bash
javac -encoding UTF-8 --release 17 -d out --module-source-path src src/demo.names/module-info.java src/demo.names/demo/names/CustomLocaleNames.java src/demo.app/module-info.java src/demo.app/demo/app/App.java
~~~

Lệnh chạy:

~~~bash
java '-Djava.locale.providers=SPI,CLDR' --module-path out --add-modules demo.names -m demo.app/demo.app.App
~~~

**Stdout chính xác** đã kiểm thử bằng OpenJDK 24 (`--release 17`):

~~~text
module-language=Example Language
module-country=Example Territory
module-test=PASS
~~~

Trong production, service binding và module resolution có thể được điều phối bằng module dependencies/service configuration. Ví dụ dùng `--add-modules` là một cách **tường minh** bảo đảm module provider đã được resolve, giúp người học tránh lỗi “compile thành công nhưng locale SPI không được tìm thấy ở runtime”.

## 9. Khi nào cần LocaleNameProvider thay vì cơ chế khác?

| Yêu cầu | API phù hợp |
| --- | --- |
| Chuyển mã `fr` thành tên “French” theo display locale | `Locale.getDisplayLanguage`, mở rộng bằng `LocaleNameProvider` khi cần |
| Chuyển mã `FR` thành tên vùng theo display locale | `Locale.getDisplayCountry`, mở rộng bằng `LocaleNameProvider` khi cần |
| Hiển thị full label gồm language, script, country, variant | `Locale.getDisplayName(displayLocale)` |
| Dịch câu giao diện như `button.save=Save` | `ResourceBundle`, `MessageFormat` và localization catalog |
| Định dạng ngày, số, tiền tệ theo locale | `DateTimeFormatter`, `NumberFormat` và locale data tương ứng |
| Tạo display name của currency hay time zone | `CurrencyNameProvider`, `TimeZoneNameProvider` nếu thực sự cần tùy biến SPI |
| So sánh/sắp xếp chuỗi theo quy tắc ngôn ngữ | `Collator`; không dùng LocaleNameProvider |
| Hiển thị danh sách tên quốc gia chuẩn | Thường chỉ cần `Locale` + dữ liệu CLDR/JDK; không cần custom provider |

### 9.1. Tên hiển thị không phải danh sách locale được hỗ trợ của ứng dụng

Việc `Locale.getAvailableLocales()` hoặc `LocaleNameProvider.getAvailableLocales()` có một locale **không có nghĩa UI của bạn đã được dịch đầy đủ cho locale đó**. Một provider có thể đặt tên cho một mã language/region mà ứng dụng chưa có ResourceBundle, formatters, văn bản trợ giúp hoặc hỗ trợ pháp lý tương ứng.

Danh sách “Ngôn ngữ ứng dụng cho phép người dùng chọn” nên đến từ **cấu hình hỗ trợ ngôn ngữ của sản phẩm**, không tự suy từ mọi locale có sẵn trong JVM. LocaleNameProvider là lớp **đặt tên để hiển thị**, không quyết định product localization coverage.

### 9.2. Không nên override CLDR chỉ vì muốn đổi một label

Nếu chỉ một dropdown cần nhãn tùy biến (ví dụ tên marketing ngắn hơn), một map label ở tầng UI có thể dễ kiểm soát hơn một SPI toàn JVM. `LocaleNameProvider` thích hợp khi muốn tích hợp nhất quán với **chính các phương thức `Locale.getDisplay...`** trên toàn ứng dụng/JVM.

Locale SPI là một phần của chính sách xử lý locale **toàn JVM**, vì thế thay data source priority có thể ảnh hưởng code khác chạy trong cùng tiến trình. Cần xem xét tác động trước khi đặt `-Djava.locale.providers=SPI,CLDR` ở môi trường production.

### 9.3. Tên quốc gia phụ thuộc chính sách ngôn ngữ và pháp lý

Tên vùng/địa danh có thể được CLDR cập nhật, và những tổ chức khác nhau có yêu cầu văn bản, quy chuẩn và chính sách quốc tế hóa riêng. Khi tùy biến, cần **quyết định nguồn dữ liệu có trách nhiệm**, versioning, kiểm tra yêu cầu pháp lý và cách cập nhật. Không xem display name là ISO identifier bất biến.

Để trao đổi dữ liệu giữa service, hãy lưu **BCP 47 tag và mã chuẩn phù hợp**, không lưu chuỗi đã localized như “Example Territory” làm khóa chính để join.

## 10. Thiết kế provider cho dữ liệu thực

Ví dụ nhỏ dùng nhánh `if` theo code. Với nhiều display locales và nhiều tên, có thể cấu trúc dữ liệu dạng:

~~~text
translations[displayLocaleTag][componentType][code] = localizedName

translations["en-US"]["language"]["qzz"] = "Example Language"
translations["en-US"]["region"]["ZZ"]   = "Example Territory"
translations["en-US"]["script"]["Qaaa"]  = "Example Script"
translations["en-US"]["variant"]["CUSTOM"] = "Custom Edition"
~~~

**Đây là phác thảo cấu trúc dữ liệu**, không phải cú pháp Java chạy được. Trong production, có thể dùng immutable Map, database snapshot hoặc localization data file đã parse.

### 10.1. Thread safety

Provider có thể được gọi từ nhiều thread. Không để `getDisplayLanguage` hay `getDisplayCountry` sửa một `HashMap` chung không đồng bộ. Tốt hơn: nạp một snapshot bất biến khi khởi tạo, rồi callback chỉ lookup. Nếu dữ liệu phải thay đổi khi chạy, dùng atomic replace snapshot với versioning rõ và kiểm thử concurrency.

### 10.2. Hiệu năng và I/O

Một màn hình chứa hàng trăm địa danh có thể gọi `Locale.getDisplayCountry` nhiều lần. Nếu mỗi callback truy vấn DB/HTTP, UI có thể chậm hoặc phụ thuộc mạng bất ổn. Nên **prefetch/cache** dữ liệu theo display locale và version, có timeout nếu phải gọi dịch vụ ngoài và fallback khi dữ liệu thiếu.

LocaleNameProvider không tự cung cấp cache TTL như `ResourceBundle.Control`. Đừng giả định việc thay một file trên disk sẽ lập tức làm các kết quả `Locale.getDisplay...` đã được JDK cache thay đổi. Tùy yêu cầu hot reload, có thể cần thiết kế nguồn dữ liệu/application display-name service riêng, thay vì dựa vào refresh không được công bố của runtime locale cache.

### 10.3. Validate và chuẩn hóa mã

Cần phân biệt **mã BCP 47** với **display string**:

- `languageCode`: mã language thường là chữ thường.
- `countryCode`: mã region hai chữ hoa hoặc ba chữ số.
- `scriptCode`: thường bốn chữ kiểu Title Case.
- `variant`: theo quy tắc `Locale`/BCP 47 và ứng dụng.

Không dùng một tên đã localized để suy ra mã quốc gia duy nhất nếu có thể có alias/đổi tên theo thời gian. Khi nhận input bên ngoài, nên parse bằng `Locale.forLanguageTag` hoặc `Locale.Builder` theo yêu cầu validation, sau đó dùng `getLanguage/getCountry/getScript` để lấy mã theo API thay vì tự tách chuỗi bằng `split("-")` không xét extensions.

### 10.4. Trả null hợp lý khi chưa có translation

Tập mã ngôn ngữ/quốc gia và các extension lớn, thay đổi theo thời gian. **Provider cho tên được phép trả null** dù display locale được công bố hỗ trợ. Đó là cách để Java thử data source/locale khác. Nếu sản phẩm cần độ phủ 100% cho dropdown của chính mình, hãy test một tập mã **được sản phẩm hỗ trợ**, không ép provider trả placeholder rỗng cho mọi mã chưa biết.

### 10.5. Logging và quan sát

Trong môi trường có nhiều data sources, lỗi SPI thường biểu hiện bằng **fallback về tên CLDR hoặc mã gốc**, không nhất thiết ném exception. Nên có integration test xác nhận một vài tên marker do provider cung cấp, giống ví dụ “Example Language”.

Không log dữ liệu nhạy cảm hoặc giả định mọi getDisplay... call đều xuất phát từ UI của bạn. Hệ thống khác trong JVM có thể yêu cầu tên locale khi tạo báo cáo/log.

## 11. Kiểm thử đầy đủ cho LocaleNameProvider

Bộ test nên phân tầng:

| Trường hợp | Cách kiểm tra |
| --- | --- |
| Provider class biên dịch trên JDK mục tiêu | `javac --release 17` |
| SPI classpath được đăng ký | Resource `META-INF/services/java.util.spi.LocaleNameProvider` được tìm thấy |
| Provider thật sự được Locale API chọn | Chạy JVM mới với `-Djava.locale.providers=SPI,CLDR` và gọi `Locale.getDisplay...` |
| Đúng display locale | `Locale.US` supported, `Locale.FRANCE` không |
| Language display name | `qzz` được gán tên custom |
| Region/country display name | `ZZ` được gán tên custom |
| Script/variant | `Qaaa`, `CUSTOM` được gán tên custom |
| Unknown name | Callback trả `null` và API `Locale` fallback phù hợp |
| Named-module resolution | `module-info.java provides`, module-path/`--add-modules` |
| Không phụ thuộc global default locale | Truyền display locale **tường minh** |
| Runtime không bật SPI | Test đối chứng không được khẳng định marker custom xuất hiện |
| Nhiều providers cùng loại | Xác định quy tắc ưu tiên/dữ liệu, không phụ thuộc `ServiceLoader.findFirst()` khi có nhiều service |
| Bảo mật và concurrency | Snapshot bất biến, không query mạng vô hạn trong callback |
| Phiên bản JDK/CLDR khác | Assert code markers của ứng dụng, không hardcode bản dịch CLDR biến động |

**Lưu ý về chạy test:** `java.locale.providers` là property được xử lý ở thời điểm khởi tạo locale subsystem. Nếu một test runner đã gọi `Locale.getDisplayLanguage` trước khi bạn `System.setProperty`, thứ tự provider có thể đã được cache. Hãy dùng **một JVM con mới** trong integration test hoặc cấu hình JVM options cho toàn bộ test task ngay từ đầu.

### 11.1. Unit test và integration test

**Unit test** có thể tạo một `new CustomLocaleNames()` và gọi `getDisplayLanguage("qzz", Locale.US)` trực tiếp, kiểm tra null, validation, data mappings. Nhưng nó **không chứng minh service registration đúng**.

**Integration test** phải kiểm tra từ API `Locale` đến provider trong JVM có SPI được bật. Bộ test ở phần 7 làm cả hai: xác nhận `ServiceLoader` thấy provider và `Locale.getDisplay...` trả marker custom. Với module, bộ test ở phần 8 xác nhận đăng ký `provides` hoạt động.

### 11.2. Không nên assert kết quả CLDR theo từng ký tự

Ví dụ code `Locale.FRANCE.getDisplayCountry(Locale.US)` thường trả tên vùng theo data tiếng Anh, nhưng văn bản CLDR có thể thay đổi theo version, đặc biệt những địa danh. Nếu test behavior chuẩn của JDK, hãy assert đầu ra hợp lệ/không rỗng hoặc ghi rõ toolchain/version trong fixture; với data do chính mình cung cấp, có thể assert exact string.

## 12. Những lỗi phổ biến

| Hiện tượng | Nguyên nhân cần kiểm tra | Giải pháp |
| --- | --- | --- |
| Code biên dịch nhưng tên custom không xuất hiện | Chưa bật `SPI`, default JDK dùng `CLDR` | Đặt `-Djava.locale.providers=SPI,CLDR` ở JVM launcher |
| `ServiceLoader` không thấy provider | Sai tên file service hoặc file không nằm trong classpath/JAR | Dùng đúng `META-INF/services/java.util.spi.LocaleNameProvider` |
| `ServiceConfigurationError` | Tên class sai, provider không công khai/không khởi tạo được, file BOM | Kiểm tra UTF-8 service file và public no-arg class |
| Tên language đúng nhưng tên country không đúng | Callback kiểm tra sai mã region hoặc chưa implement | So `getDisplayCountry("ZZ", Locale.US)` và mã target |
| Provider trả tên cho display locale khác | Nhầm `target locale` và `display locale` | Nhớ callback `locale` là **ngôn ngữ để hiển thị tên** |
| `getAvailableLocales` chỉ liệt kê target `qzz` | Hiểu sai supported locales | Trả display locale (ví dụ `Locale.US`), không phải mã cần đặt tên |
| `getDisplayName` khác chuỗi dự kiến | Cách ghép/phân tách theo locale/JDK | Test `getDisplayLanguage/Country/Script/Variant` riêng |
| `getDisplayLanguage` trả mã gốc | Không có tên từ SPI/CLDR và API fallback | Nếu cần tên sản phẩm, bổ sung dữ liệu và test coverage |
| SPI hoạt động trong classpath nhưng không trong named module | Chỉ dùng `META-INF/services` và module chưa resolve | Khai báo `provides` trong module-info, bảo đảm module được resolve |
| `System.setProperty` không thay thứ tự như mong đợi | Locale provider order đã được cache | Đặt property khi khởi động JVM |
| Bản dịch country khác nhau giữa hai JDK | CLDR version khác | Ghim toolchain/test policy; không hardcode CLDR text |
| Một UI chậm vì gọi tên locale nhiều lần | Callback truy vấn DB/HTTP | Cache snapshot, prefetch, tránh I/O mỗi lookup |
| Tên hiển thị bị dùng làm primary key | Localized labels không phải mã ổn định | Lưu language tag/region code, hiển thị tên riêng |
| Gọi `LocaleNameProvider` để dịch mọi câu văn | Nhầm SPI display name với message localization | Dùng `ResourceBundle` cho message strings |
| Cấu hình `JRE,COMPAT` được copy từ tài liệu cũ | Locale adapter legacy đã bị loại bỏ | Dùng `SPI,CLDR` hoặc policy còn được hỗ trợ |
| Kết quả kiểm thử phụ thuộc locale hệ thống | Dùng overload không truyền display locale | Truyền `Locale.US` hoặc display locale được test tường minh |

## 13. Câu hỏi tự đánh giá

**Câu 1.** `LocaleNameProvider` dùng để dịch câu “Save changes” trong một app nhiều ngôn ngữ phải không?

**Đáp án:** Không. Nó cung cấp tên hiển thị của language/region/script/variant codes. Câu UI tự do nên đặt trong `ResourceBundle` hoặc localization catalog phù hợp.

**Câu 2.** Khi gọi `getDisplayLanguage("qzz", Locale.US)`, hai tham số có nghĩa gì?

**Đáp án:** `qzz` là **language code cần đặt tên**; `Locale.US` là **display locale dùng để viết tên**, ở đây dùng tiếng Anh-Mỹ.

**Câu 3.** `getAvailableLocales()` phải trả `Locale.forLanguageTag("qzz")` để đặt tên qzz không?

**Đáp án:** Không. Nó phải công bố **display locale** có dữ liệu như `Locale.US`; provider sau đó có thể trả tên cho nhiều target codes.

**Câu 4.** Khi provider không biết tên một mã, nên trả gì?

**Đáp án:** `null` để báo chưa có localized name và cho phép fallback. Không nên trả `""` để giả vờ có bản dịch.

**Câu 5.** Thêm `META-INF/services/...` có đủ để Java 26 dùng SPI trên classpath không?

**Đáp án:** Không. JDK hiện đại mặc định dùng CLDR; phải có `SPI` trong property `java.locale.providers` tại JVM startup.

**Câu 6.** Có thể đổi provider order bằng `System.setProperty` sau khi app đã gọi các locale services không?

**Đáp án:** Không đáng tin vì thứ tự có thể đã được đọc/cache. Dùng JVM command-line option trước khi khởi chạy.

**Câu 7.** `getDisplayScript(...)` có bắt buộc override không?

**Đáp án:** Không. Nó có default implementation trả `null`; muốn cung cấp tên script tùy biến thì override. `getDisplayLanguage`, `getDisplayCountry` và `getDisplayVariant` là abstract.

**Câu 8.** Trong named module, đăng ký provider thế nào?

**Đáp án:** Dùng `provides java.util.spi.LocaleNameProvider with ...` trong `module-info.java`, bảo đảm module được resolve, và bật SPI trong provider order. Không cần dùng file `META-INF/services` thay `provides`.

**Câu 9.** Có nên lấy `getDisplayName()` làm key database không?

**Đáp án:** Không. Tên localized có thể thay đổi theo display locale, CLDR version và chính sách sản phẩm. Dùng BCP 47 language tag hoặc mã chuẩn làm dữ liệu định danh.

### Bài tập thực hành

1. Bổ sung display locale `Locale.FRANCE` vào provider và cung cấp tên tiếng Pháp cho `qzz`, `ZZ`; viết test hai display locales.
2. Cho `getDisplayLanguage` trả `null` với mã chưa biết, kiểm tra fallback của `Locale.getDisplayLanguage`; không hardcode tên CLDR của mã khác.
3. Thêm một mã region ba chữ số UN M.49 (chỉ chọn mã hợp lệ theo đặc tả) rồi viết test callback và Locale API.
4. Viết unit test đảm bảo `getAvailableLocales()` không có `null` và không lặp locale chỉ khác extensions.
5. Đóng gói provider vào JAR, kiểm tra file `META-INF/services/java.util.spi.LocaleNameProvider` thực sự nằm trong JAR.
6. Chạy cùng code với `java.locale.providers=CLDR,SPI` và `SPI,CLDR`; ghi lại khác biệt, giải thích tính ưu tiên.
7. Thực hành triển khai provider riêng bằng named module và kiểm tra ảnh hưởng của việc bỏ `--add-modules demo.names`.
8. Thiết kế dictionary `(displayLocale, languageCode/regionCode) -> name`, triển khai snapshot bất biến và kiểm thử nhiều threads lookup.

## 14. Tài liệu chính thức hiện hành

- [Java SE 26 — LocaleNameProvider](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/spi/LocaleNameProvider.html): class, API language, country, script, variant và Unicode extensions.
- [Java SE 26 — LocaleServiceProvider](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/spi/LocaleServiceProvider.html): `getAvailableLocales`, `isSupportedLocale`, service registration, `SPI/CLDR/HOST` và JVM property.
- [Java SE 26 — Locale](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.html): `getDisplayLanguage/Country/Script/Variant/Name`, BCP 47 tag và default DISPLAY locale.
- [Java SE 17 — LocaleNameProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/LocaleNameProvider.html): đối chiếu API cho bài lab `--release 17`.
- [Java SE 26 — ServiceLoader](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html): file provider configuration và Java module services.
- [Oracle JDK 26 Supported Locales](https://www.oracle.com/java/technologies/javase/jdk26-supported-locales.html): CLDR và danh sách locale data providers hiện hành.
- [Java SE 26 — Internationalization Guide](https://docs.oracle.com/en/java/javase/26/intl/): khái niệm quốc tế hóa, providers và locale data.
- [IETF BCP 47 — RFC 5646](https://www.rfc-editor.org/rfc/rfc5646): ngôn ngữ, script, region và cú pháp language tag.

**Ghi nhớ:** `LocaleNameProvider` cung cấp **localized display names cho mã language/region/script/variant**, với `locale` callback là **ngôn ngữ cần hiển thị tên**. Trên classpath cần service file **và** bật `SPI`; với named module dùng `provides` và bảo đảm module được resolve. Dùng `getAvailableLocales` cho display locales được hỗ trợ, trả `null` khi không có tên, và giữ `CLDR` làm fallback hợp lý. Đây là API được hỗ trợ trong Java hiện đại, nhưng chỉ nên tùy biến khi yêu cầu sản phẩm thật sự cần thay/bổ sung dữ liệu tên hiển thị.

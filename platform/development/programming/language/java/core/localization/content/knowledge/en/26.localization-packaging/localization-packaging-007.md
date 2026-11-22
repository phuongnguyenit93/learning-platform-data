# LocaleServiceProvider và các SPI cho tên hoặc định dạng trong Java

Khi ứng dụng Java cần hỗ trợ một locale chưa được JDK cung cấp đầy đủ hoặc cần **mở rộng cách hiển thị tên và định dạng** theo quy tắc riêng, chỉ tạo thêm `Locale` chưa đủ. Java có cơ chế **locale-sensitive Service Provider Interface (SPI)**: ứng dụng hoặc thư viện có thể cung cấp một triển khai được runtime phát hiện, để một số API chuẩn trong `java.text` và `java.util` có thêm khả năng xử lý locale.

Lớp gốc là **`java.util.spi.LocaleServiceProvider`**. Các SPI cụ thể như `LocaleNameProvider`, `CurrencyNameProvider`, `NumberFormatProvider` và `DateFormatProvider` cho phép bổ sung **tên hiển thị** hoặc **đối tượng định dạng** cho các locale thích hợp. Cơ chế này liên quan tới đóng gói, phát hiện dịch vụ và lựa chọn thứ tự nhà cung cấp; nó **không phải** một hệ thống tự dịch thông điệp của toàn ứng dụng.

Bài học thuộc chủ đề **Đóng gói và mở rộng** trong Java Core localization. Nội dung dùng Java 17+ để giải thích cơ chế provider, cách đăng ký qua `META-INF/services` hoặc `module-info.java`, một ví dụ `NumberFormatProvider` có thể chạy, một ví dụ `LocaleNameProvider` cho tên, các giới hạn quan trọng, lỗi thường gặp và kế hoạch kiểm thử.

## 1. Từ Locale đến nhà cung cấp dữ liệu locale

`Locale` chủ yếu đóng vai trò **định danh**. Ví dụ:

~~~java
Locale locale = Locale.forLanguageTag("en-US");
~~~

Đoạn này cho biết yêu cầu về ngôn ngữ/vùng, chứ không tự chứa toàn bộ dữ liệu mẫu số, tên ngôn ngữ hay cách viết ngày. Khi gọi:

~~~java
NumberFormat f = NumberFormat.getNumberInstance(locale);
String display = f.format(1234.5);
~~~

Java cần một triển khai dịch vụ định dạng và dữ liệu locale thích hợp. Phần lớn ứng dụng sử dụng **dữ liệu tích hợp JDK** (ví dụ CLDR), nhưng một số dịch vụ có thể được bổ sung bằng **provider riêng**.

Một luồng khái niệm:

~~~text
Ứng dụng gọi NumberFormat.getNumberInstance(locale)
                         |
                         v
           Locale-sensitive service lookup
                         |
         +---------------+---------------+
         |                               |
   Provider JDK (CLDR...)       Provider bên ngoài (SPI)
         |                               |
         +---------------+---------------+
                         |
                         v
              NumberFormat phù hợp
                         |
                         v
                 Chuỗi hiển thị
~~~

Thứ tự ưu tiên của các nguồn được cấu hình qua `java.locale.providers`. Kết quả còn phụ thuộc dịch vụ, locale thực sự được provider hỗ trợ, runtime đang chạy và các quy tắc fallback.

### SPI trong bài này là gì?

**SPI (Service Provider Interface)** là một hợp đồng để bên thứ ba cung cấp triển khai dịch vụ. Với localization, đây là **các abstract class cụ thể** có chung lớp cha `LocaleServiceProvider`. Nhà phát triển tạo lớp con, hiện thực những phương thức bắt buộc và đóng gói để Java có thể phát hiện.

Khái niệm “provider” dễ bị dùng lẫn cho hai cấp:

- **Nhóm provider dữ liệu** trong thứ tự `java.locale.providers`: `CLDR`, `SPI`, `HOST` và một số nhóm legacy theo phiên bản.
- **Lớp provider cụ thể** của ứng dụng: ví dụ `demo.CustomNumberProvider extends NumberFormatProvider`.

`SPI` trong chuỗi cấu hình là **một nhóm tìm kiếm provider**, không phải tên lớp Java mà bạn viết.

## 2. Lớp gốc LocaleServiceProvider có nhiệm vụ gì?

`java.util.spi.LocaleServiceProvider` là abstract class cha của các locale-sensitive SPI. Hai phương thức quan trọng:

~~~java
public abstract Locale[] getAvailableLocales();

public boolean isSupportedLocale(Locale locale);
~~~

Đoạn trên là **chữ ký API minh họa**, không phải lớp có thể chạy độc lập.

- `getAvailableLocales()` trả danh sách locale mà provider **thực sự có thể cung cấp** dữ liệu hoặc đối tượng. Đừng khai báo mọi locale rồi chỉ hỗ trợ một số.
- `isSupportedLocale(locale)` xác định một locale có được hỗ trợ không. Triển khai mặc định so sánh với danh sách `getAvailableLocales()` sau khi **bỏ qua locale extensions**.
- Nếu provider cần phân biệt Unicode locale extension, chẳng hạn numbering system trong `en-US-u-nu-thai`, nên **override `isSupportedLocale`** và định nghĩa rõ phần mở rộng nào được hỗ trợ.

Ví dụ:

~~~java
Locale requested =
        Locale.forLanguageTag("en-XZ-u-nu-latn");
~~~

Với một provider khai báo `en-XZ`, cách kiểm tra mặc định có thể coi request mang extension là được hỗ trợ vì chỉ so locale sau khi bỏ extensions. Nhưng điều đó **không bảo đảm** implementation formatter của bạn thực sự tôn trọng extension `nu`. Nếu chưa xử lý được numbering system mà lại chấp nhận, output có thể khác mong đợi người dùng. Hãy hạn chế phạm vi được công bố hoặc hiện thực logic tương ứng.

**Không lưu trạng thái request toàn cục trong provider.** Provider có thể được runtime tái sử dụng và các phương thức được gọi bởi nhiều luồng. Mỗi lần trả `NumberFormat` nên tạo instance phù hợp; `NumberFormat`/`DecimalFormat` là các đối tượng có trạng thái thay đổi được, không tự an toàn cho mọi thao tác đồng thời.

## 3. Các SPI cho tên hiển thị và định dạng

Không nên tạo một lớp kế thừa trực tiếp `LocaleServiceProvider` và mong Java tự biết dùng nó cho mọi việc. Cần chọn **subclass SPI đúng dịch vụ**.

| SPI cụ thể | Package | Chức năng chính |
| --- | --- | --- |
| `LocaleNameProvider` | `java.util.spi` | Tên hiển thị của ngôn ngữ, vùng, variant, script hoặc các extension được hỗ trợ |
| `CurrencyNameProvider` | `java.util.spi` | Ký hiệu/tên hiển thị tiền tệ theo locale |
| `TimeZoneNameProvider` | `java.util.spi` | Tên hiển thị vùng giờ |
| `CalendarNameProvider` | `java.util.spi` | Tên trường lịch như tháng, thứ và era ở những ngữ cảnh API tương ứng |
| `CalendarDataProvider` | `java.util.spi` | Thông tin lịch như ngày đầu tuần và số ngày tối thiểu của tuần đầu năm |
| `NumberFormatProvider` | `java.text.spi` | Tạo formatter số, phần trăm, số nguyên và tiền |
| `DecimalFormatSymbolsProvider` | `java.text.spi` | Ký hiệu dấu thập phân, phân nhóm và dữ liệu của `DecimalFormatSymbols` |
| `DateFormatProvider` | `java.text.spi` | Tạo `DateFormat` theo locale/style |
| `DateFormatSymbolsProvider` | `java.text.spi` | Ký hiệu/tên dùng trong `DateFormatSymbols` |
| `BreakIteratorProvider` | `java.text.spi` | Tạo bộ phân đoạn văn bản theo locale |
| `CollatorProvider` | `java.text.spi` | Tạo bộ so sánh/sắp xếp theo locale |

Đây là các **subclass hiện diện trong API Java SE 17**, không phải lời cam kết mỗi SPI đều được mọi runtime sử dụng cho mọi lớp Java thời gian hoặc mọi service Unicode hiện đại.

### Tên khác với formatter

- `LocaleNameProvider` trả **`String` tên được bản địa hóa**, ví dụ tên của mã ngôn ngữ `fr` trong ngôn ngữ hiển thị `en-XZ`.
- `CurrencyNameProvider` trả **tên/ký hiệu tiền**, không quy đổi tỷ giá.
- `NumberFormatProvider` trả **`NumberFormat` để định dạng số**, không trả bản dịch của một nhãn UI.
- `DateFormatProvider` là SPI thuộc hệ `java.text.DateFormat`, không nên tự suy ra nó thay thế tất cả hành vi `java.time.format.DateTimeFormatter`.

Nếu muốn dịch `button.save=Save` thành `Lưu`, đó là trách nhiệm nội dung ứng dụng, thường dùng `ResourceBundle` hoặc hệ thống l10n riêng; `LocaleNameProvider` không phải engine dịch mọi câu.

## 4. Cơ chế lựa chọn: CLDR, SPI, COMPAT, HOST

JDK có cơ chế ưu tiên nhóm nhà cung cấp bằng system property **`java.locale.providers`**. Trên Java 17, các tên được tài liệu đề cập gồm:

| Giá trị | Ý nghĩa |
| --- | --- |
| `CLDR` | Dữ liệu bản địa hóa dựa trên Unicode CLDR mà JDK tích hợp |
| `SPI` | Các provider do ứng dụng/thư viện đăng ký theo `LocaleServiceProvider` |
| `COMPAT` | Dữ liệu locale tương thích nhiều hành vi JDK 8 trước đây |
| `JRE` | Bí danh legacy của `COMPAT` trong các bản còn hỗ trợ |
| `HOST` | Một số thiết lập locale của hệ điều hành, tùy runtime/nền tảng |

**Trên JDK 17**, thứ tự mặc định tương đương `CLDR,COMPAT`. Muốn nhà cung cấp classpath của bạn được tìm, cần **đưa `SPI` vào property khi JVM khởi động**, ví dụ:

~~~bash
java -Djava.locale.providers=SPI,CLDR,COMPAT -cp out demo.ProviderDemo
~~~

Ở đây `SPI` được thử trước `CLDR` và `COMPAT` cho dịch vụ/locale có provider phù hợp. Nếu không có triển khai phù hợp, runtime tra nhà cung cấp tiếp theo, rồi các locale fallback theo thuật toán của API.

**Quan trọng:** `java.locale.providers` chỉ được đọc khi runtime khởi động. Gọi `System.setProperty("java.locale.providers","SPI,CLDR")` sau khi ứng dụng đã chạy **không đổi lại thứ tự lookup**.

### Chú ý khi nâng JDK

- Từ **JDK 9**, CLDR được ưu tiên mặc định (JEP 252).
- **JDK 17** còn dữ liệu legacy `COMPAT/JRE`.
- Trong **JDK 23 trở lên**, dữ liệu locale legacy `COMPAT/JRE` đã bị loại bỏ. Đặt các tên ấy trong property không khôi phục bộ dữ liệu cũ.
- Provider `SPI` vẫn là một hướng mở rộng có thể dùng khi đáp ứng hợp đồng và điều kiện đóng gói của runtime.

Đừng dùng `COMPAT` như chiến lược dài hạn cho ứng dụng chuẩn bị nâng Java. Nếu phụ thuộc format cũ, cần migration rõ: custom formatter cụ thể hoặc SPI được thiết kế/kiểm thử.

### Có phải SPI luôn thắng CLDR?

**Không.** Thứ tự provider mới là yếu tố quyết định. Nếu đặt `CLDR,SPI`, dữ liệu CLDR có thể được chọn trước cho một dịch vụ/locale đã hỗ trợ. Nếu muốn thử provider tùy chỉnh trước, đặt `SPI,CLDR` (hoặc thứ tự tương ứng với runtime).

Ngay cả với `SPI` đứng đầu, provider chỉ được gọi khi **dịch vụ SPI tương ứng được yêu cầu**, locale được hỗ trợ và provider đã được phát hiện/đăng ký. Nếu lớp của bạn không nằm trên classpath/module path đúng cách hoặc service descriptor sai, Java vẫn có thể dùng formatter chuẩn mà không báo lỗi hiển thị rõ ràng.

## 5. Đăng ký một provider cho classpath

Với ứng dụng **classpath** (non-modular), đăng ký bằng Java service provider configuration file:

~~~text
META-INF/services/<tên đầy đủ của SPI>
~~~

Nếu triển khai `NumberFormatProvider`, đường dẫn tài nguyên cần đúng:

~~~text
META-INF/services/java.text.spi.NumberFormatProvider
~~~

Trong file (UTF-8), mỗi dòng là **tên đầy đủ của lớp triển khai concrete**, ví dụ:

~~~text
demo.CustomNumberProvider
~~~

Đây là nội dung của file cấu hình, **không phải lệnh shell**. Tên file phải là tên SPI, không phải tên của lớp triển khai. Kết quả đóng gói cần chứa cả class `demo.CustomNumberProvider` và descriptor ở vị trí `META-INF/services/...` có thể đọc được.

Lớp triển khai phải được loader truy cập, không còn abstract và có constructor phù hợp để cơ chế dịch vụ tạo instance. Nếu cấu hình chỉ tới class không tồn tại, không truy cập được hoặc không đúng subtype, lookup có thể gây lỗi nạp dịch vụ.

### Cấu trúc thư mục mẫu

~~~text
project/
  src/
    demo/
      CustomNumberProvider.java
      ProviderDemo.java
  resources/
    META-INF/
      services/
        java.text.spi.NumberFormatProvider
~~~

Không đặt descriptor nhầm trong `src/demo` hoặc dưới tên `LocaleServiceProvider`. API sẽ tìm **SPI cụ thể**, chẳng hạn `java.text.spi.NumberFormatProvider`.

### Còn ứng dụng Java module (JPMS)?

Nếu triển khai được đóng gói trong **named module**, có thể khai báo provider bằng `provides ... with ...`:

~~~java
module demo.locale.provider {
    provides java.text.spi.NumberFormatProvider
        with demo.CustomNumberProvider;
}
~~~

Đây là **đoạn `module-info.java` minh họa**, cần tích hợp với cấu trúc project/module phù hợp. Có thể phải đảm bảo provider module được resolved vào module graph ở lúc chạy; chỉ đặt file JAR tùy ý trên module path không đảm bảo service được chọn trong mọi cách launch. Với classpath, `META-INF/services` là cơ chế rõ ràng nhất cho ví dụ ở phần tiếp theo.

Đừng lẫn `uses`/`provides` của JPMS với `java.locale.providers`: một bên là **cấu hình phát hiện lớp dịch vụ**, bên kia là **thứ tự nhóm nhà cung cấp locale** khi JVM thực hiện locale-sensitive lookup.

## 6. Ví dụ Java 17: viết NumberFormatProvider tùy chỉnh

Ta sẽ tạo một locale **chỉ dùng để minh họa** là `en-XZ`, rồi định nghĩa kiểu in số:

~~~text
Giá trị:          1234.5
Định dạng demo:   1_234~50
~~~

Dấu `_` là dấu phân nhóm và `~` là dấu thập phân trong ví dụ; chúng **không phải quy ước CLDR chính thức của một quốc gia**. Mục đích là nhìn được provider đã được dùng.

### 6.1. File src/demo/CustomNumberProvider.java

~~~java
package demo;

import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.text.spi.NumberFormatProvider;
import java.util.Locale;

public final class CustomNumberProvider extends NumberFormatProvider {
    private static final Locale DEMO =
            Locale.forLanguageTag("en-XZ");

    public CustomNumberProvider() {
    }

    @Override
    public Locale[] getAvailableLocales() {
        return new Locale[] { DEMO };
    }

    private static void check(Locale locale) {
        if (!DEMO.equals(locale.stripExtensions())) {
            throw new IllegalArgumentException("Unsupported locale");
        }
    }

    private static DecimalFormat format(String pattern) {
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(Locale.US);
        symbols.setGroupingSeparator('_');
        symbols.setDecimalSeparator('~');
        return new DecimalFormat(pattern, symbols);
    }

    @Override
    public NumberFormat getNumberInstance(Locale locale) {
        check(locale);
        return format("#,##0.00");
    }

    @Override
    public NumberFormat getIntegerInstance(Locale locale) {
        check(locale);
        DecimalFormat formatter = format("#,##0");
        formatter.setParseIntegerOnly(true);
        formatter.setRoundingMode(RoundingMode.HALF_EVEN);
        return formatter;
    }

    @Override
    public NumberFormat getCurrencyInstance(Locale locale) {
        check(locale);
        return format("¤ #,##0.00");
    }

    @Override
    public NumberFormat getPercentInstance(Locale locale) {
        check(locale);
        return format("#,##0%");
    }
}
~~~

**Giải thích thiết kế:**

1. `getAvailableLocales()` công bố đúng một locale thử nghiệm.
2. `check` từ chối locale ngoài phạm vi. Nó bỏ qua extension giống phép kiểm tra mặc định, **chưa hiện thực numbering system tùy biến**; đây là một giới hạn được công khai.
3. `format` tạo `DecimalFormatSymbols` dựa trên `Locale.US`, rồi đặt dấu nhóm/thập phân riêng. Nó **không gọi `NumberFormat.getNumberInstance(DEMO)`** bên trong chính provider, tránh vòng đệ quy tra cứu lại chính SPI.
4. Mỗi method tạo formatter mới. `DecimalFormat` có state nên cách này dễ kiểm soát hơn dùng chung một instance có thể bị request khác sửa.
5. Cả bốn method abstract của `NumberFormatProvider` được hiện thực: number, integer, currency, percent.
6. `getCompactNumberInstance(locale, style)` trong Java 17 không phải method abstract bắt buộc; triển khai mặc định của nó ném `UnsupportedOperationException`. Muốn hỗ trợ compact formatting bằng SPI này, phải đánh giá/override thêm method ấy.

**Giới hạn cố ý:** formatter tiền trong ví dụ chỉ thể hiện cách định dạng; chưa mô hình hóa currency code/rounding policy của từng giao dịch, ký hiệu tiền khác locale, parse nghiêm ngặt và chuẩn nghiệp vụ. Không dùng trực tiếp provider minh họa để thanh toán thật.

### 6.2. File src/demo/ProviderDemo.java

~~~java
package demo;

import java.text.NumberFormat;
import java.util.Locale;

public final class ProviderDemo {
    public static void main(String[] args) {
        Locale demo = Locale.forLanguageTag("en-XZ");
        CustomNumberProvider direct = new CustomNumberProvider();

        System.out.println("Locale: "
                + direct.getAvailableLocales()[0].toLanguageTag());
        System.out.println("Supported: "
                + direct.isSupportedLocale(demo));
        System.out.println("Unsupported: "
                + direct.isSupportedLocale(Locale.US));

        String directNumber =
                direct.getNumberInstance(demo).format(1234.5);
        System.out.println("Direct number: " + directNumber);

        NumberFormat viaFactory = NumberFormat.getNumberInstance(demo);
        String factoryNumber = viaFactory.format(1234.5);
        System.out.println("Factory used SPI: "
                + directNumber.equals(factoryNumber));
    }
}
~~~

Hai điều cần phân biệt:

- `new CustomNumberProvider().getNumberInstance(demo)` **gọi trực tiếp object Java**; nó có thể chạy **dù chưa đăng ký service**.
- `NumberFormat.getNumberInstance(demo)` **đi qua locale provider lookup của runtime**. Nó chỉ chọn provider ứng dụng khi đã đăng ký đúng và thứ tự provider/locale cho phép.

### 6.3. File resource đăng ký

Tạo đúng file:

~~~text
resources/META-INF/services/java.text.spi.NumberFormatProvider
~~~

Nội dung file:

~~~text
demo.CustomNumberProvider
~~~

### 6.4. Biên dịch và chạy (JDK 17+)

Ví dụ cho shell Bash trên macOS/Linux:

~~~bash
mkdir -p out/META-INF/services
javac --release 17 -encoding UTF-8 -d out \
  src/demo/CustomNumberProvider.java \
  src/demo/ProviderDemo.java
cp resources/META-INF/services/java.text.spi.NumberFormatProvider \
  out/META-INF/services/

java -Djava.locale.providers=SPI,CLDR -cp out demo.ProviderDemo
~~~

Với PowerShell trên Windows, bước tạo/thao tác resource tương ứng:

~~~powershell
New-Item -ItemType Directory -Force out/META-INF/services | Out-Null
javac --release 17 -encoding UTF-8 -d out src/demo/CustomNumberProvider.java src/demo/ProviderDemo.java
Copy-Item resources/META-INF/services/java.text.spi.NumberFormatProvider out/META-INF/services/
java -Djava.locale.providers=SPI,CLDR -cp out demo.ProviderDemo
~~~

Đây là **hướng dẫn tự tạo dự án ví dụ**, không yêu cầu bất kỳ file hay thư viện ngoài Java 17. `out` là thư mục classpath chứa class biên dịch và cả resource service descriptor.

### 6.5. Kết quả mong đợi khi SPI đã được đăng ký và ưu tiên

~~~text
Locale: en-XZ
Supported: true
Unsupported: false
Direct number: 1_234~50
Factory used SPI: true
~~~

Các giá trị của `getAvailableLocales`, `isSupportedLocale` và formatter được gọi **trực tiếp** đã được thử trên JDK: `en-XZ`, `true`, `false` và `1_234~50`. Dòng `Factory used SPI: true` là kỳ vọng của đường **ServiceLoader/locale lookup** khi classpath có descriptor và JVM khởi động với `SPI,CLDR` đúng như hướng dẫn; nếu nhận `false`, kiểm tra file descriptor, classpath, startup property, provider locale và runtime.

Để thấy sự khác biệt, có thể khởi động không có `SPI`:

~~~bash
java -Djava.locale.providers=CLDR -cp out demo.ProviderDemo
~~~

Đường gọi **trực tiếp** sẽ vẫn tạo kiểu định dạng demo, nhưng đường gọi `NumberFormat.getNumberInstance` dùng nhà cung cấp khác; không nên hứa chính xác chuỗi fallback nếu CLDR/runtime thay phiên bản.

### Vì sao phải chọn một locale riêng?

Một SPI dùng `Locale.US` chẳng hạn có thể không được chọn nếu `CLDR` đứng trước. Locale demo `en-XZ` giúp tránh hiểu nhầm về thứ tự/provider và minh họa hỗ trợ bổ sung. Tuy nhiên, cũng nên nhớ `en-XZ` **không phải vùng/chuẩn trình bày cần dùng trong production**; dữ liệu thật phải dựa vào locale/nhu cầu hợp lệ và đã được phê duyệt.

## 7. Ví dụ SPI cho tên: LocaleNameProvider

Nhóm SPI cho **tên** trả chuỗi văn bản, khác với nhóm SPI định dạng trả formatter.

`LocaleNameProvider` trong `java.util.spi` có các phương thức bắt buộc như:

~~~java
public String getDisplayLanguage(String languageCode, Locale locale);
public String getDisplayCountry(String countryCode, Locale locale);
public String getDisplayVariant(String variant, Locale locale);
~~~

Đây là **chữ ký minh họa**. Các phương thức khác như `getDisplayScript` có triển khai mặc định trong API và có thể override khi muốn hỗ trợ tên script.

**Phân biệt hai đầu vào:**

- `languageCode` / `countryCode` là **mã đối tượng cần đặt tên**.
- `locale` là **ngôn ngữ/vùng dùng để hiển thị tên ấy**.

Ví dụ: để lấy tên của tiếng Pháp khi hiển thị bằng tiếng Anh, đối tượng cần đặt tên là mã `fr` còn locale hiển thị có thể là `en-US`. Không đảo ngược hai ý nghĩa.

Một provider minh họa:

~~~java
package demo;

import java.util.Locale;
import java.util.spi.LocaleNameProvider;

public final class CustomLocaleNames extends LocaleNameProvider {
    private static final Locale TARGET =
            Locale.forLanguageTag("en-XZ");

    public CustomLocaleNames() {
    }

    @Override
    public Locale[] getAvailableLocales() {
        return new Locale[] { TARGET };
    }

    @Override
    public String getDisplayLanguage(
            String languageCode, Locale locale) {
        if (!isSupportedLocale(locale)) {
            throw new IllegalArgumentException("Unsupported locale");
        }
        return "fr".equals(languageCode) ? "French (custom)" : null;
    }

    @Override
    public String getDisplayCountry(
            String countryCode, Locale locale) {
        return null;
    }

    @Override
    public String getDisplayVariant(
            String variant, Locale locale) {
        return null;
    }
}
~~~

Đây là **lớp bổ sung minh họa**, không phải chương trình có `main` độc lập. Gọi trực tiếp:

~~~java
CustomLocaleNames names = new CustomLocaleNames();
Locale displayLocale = Locale.forLanguageTag("en-XZ");

System.out.println(names.getDisplayLanguage("fr", displayLocale));
// French (custom)
System.out.println(names.getDisplayLanguage("de", displayLocale) == null);
// true
~~~

Hai kết quả gọi trực tiếp trên đã được kiểm thử với Java. Việc trả `null` ở một phương thức **tên hiển thị** là cách báo không có bản dịch cho mã đó; cơ chế locale service lookup có thể tiếp tục tìm nguồn hoặc fallback. **Không** áp suy luận “provider formatter cũng có thể tùy tiện trả `null`” cho nhóm object formatter như `NumberFormatProvider`.

Để đăng ký `CustomLocaleNames` trên classpath, dùng **file service riêng**:

~~~text
META-INF/services/java.util.spi.LocaleNameProvider
~~~

Nội dung:

~~~text
demo.CustomLocaleNames
~~~

Sau đó gọi API chuẩn như:

~~~java
String shown = Locale.FRENCH.getDisplayLanguage(
        Locale.forLanguageTag("en-XZ"));
~~~

Nếu `SPI` đã được đăng ký, ưu tiên và locale được provider hỗ trợ, API có thể dùng tên từ provider trước khi fallback sang nguồn khác. Không dự đoán rằng cách gọi trực tiếp và cách lookup sẽ giống nhau nếu chưa kiểm tra **descriptor + property + runtime**.

### Những SPI tên khác

- `CurrencyNameProvider`: tên hoặc ký hiệu tiền theo locale; không chuyển đổi tỷ giá.
- `TimeZoneNameProvider`: tên trình bày timezone; không thay đổi `ZoneRules` hay suy vị trí của người dùng.
- `CalendarNameProvider`: tên các thành phần lịch cho API phù hợp; không dịch văn bản ứng dụng.

Việc `LocaleNameProvider` hỗ trợ một tên không có nghĩa nó tự bổ sung dữ liệu vào mọi `ResourceBundle` do sản phẩm tạo.

## 8. Provider cho định dạng: lựa chọn API nào?

Nếu cần mở rộng định dạng, chọn đúng cấp dữ liệu:

| Nhu cầu | Lựa chọn |
| --- | --- |
| Thay quy tắc tạo toàn bộ formatter số | `NumberFormatProvider` |
| Chỉ thay bộ ký hiệu của `DecimalFormatSymbols` | `DecimalFormatSymbolsProvider` |
| Cung cấp `DateFormat` cho locale mới | `DateFormatProvider` |
| Cung cấp tên tháng/thứ/era trong `DateFormatSymbols` | `DateFormatSymbolsProvider` |
| Cung cấp tên currency riêng | `CurrencyNameProvider` |
| Cung cấp tên language/country trong API `Locale` | `LocaleNameProvider` |
| Bổ sung cách so sánh/sắp xếp cho một locale | `CollatorProvider` |
| Bổ sung thuật toán phân đoạn văn bản | `BreakIteratorProvider` |

Không có một `LocaleServiceProvider` “vạn năng” tự phân phối mọi kết quả theo `getAvailableLocales`. Các SPI là những hợp đồng riêng cho từng nhóm dịch vụ.

### NumberFormatProvider không đồng nghĩa DecimalFormatSymbolsProvider

Hai SPI này khác vai trò. `DecimalFormatSymbolsProvider` cung cấp ký hiệu để các formatter dùng theo cơ chế tương ứng; `NumberFormatProvider` tạo toàn bộ `NumberFormat` và có thể tự chọn pattern, parse và cách định dạng.

Khi hiện thực formatter số, cần kiểm tra:

- phân nhóm/thập phân;
- số âm, số rất lớn, số thực và `BigDecimal`;
- phần trăm (thường nhân 100 khi hiển thị, tùy formatter);
- số nguyên và rounding;
- tiền tệ, mã tiền, fraction digits;
- parsing, `ParsePosition` và trường hợp input chỉ được parse một phần;
- thread safety của formatter mutable;
- Unicode numbering system extensions nếu ứng dụng tuyên bố hỗ trợ.

Cung cấp một formatter có thể in chuỗi demo **không có nghĩa đủ tiêu chuẩn cho xử lý thanh toán hay đọc input nghiệp vụ**. Dữ liệu số chuẩn nên được lưu tách khỏi cách hiển thị theo locale.

## 9. Fallback và những tình huống dễ bất ngờ

Cơ chế lookup locale có thể xem các ứng viên ít cụ thể hơn khi locale yêu cầu không có dịch vụ, ví dụ một locale có vùng/variant/extension, sau đó về locale ngôn ngữ hoặc root theo quy tắc runtime.

Cần hiểu các nguyên tắc:

1. **Lookup theo dịch vụ:** provider cho tên không tự biến thành provider format.
2. **Provider order:** `SPI,CLDR` khác `CLDR,SPI` nếu hai nhóm có dữ liệu cho cùng dịch vụ/locale.
3. **Locale support:** `getAvailableLocales()` và `isSupportedLocale` phải thể hiện hỗ trợ thật, không khai báo bừa.
4. **Extensions:** triển khai `isSupportedLocale` mặc định bỏ qua extensions; muốn xử lý cụ thể phải override.
5. **Tên trả null:** name provider có thể trả `null` và để lookup tiếp tục; object formatter phải thực hiện theo hợp đồng phương thức, không coi `null` là fallback chuẩn.
6. **Classpath/module path:** class provider và đăng ký service phải nằm trong runtime; đóng gói sai khiến factory dùng provider khác.
7. **Khởi động:** `java.locale.providers` được đọc khi JVM bắt đầu, không đổi sau request.
8. **Dữ liệu JDK thay đổi:** nâng JDK/CLDR có thể đổi output hoặc tính khả dụng của provider.

Nếu dự án dùng `jlink` tạo runtime image nhỏ, kiểm tra các module/dữ liệu locale và khả năng phát hiện service thực tế trong image. Một build chạy thành công trên JDK đầy đủ không tự đảm bảo đóng gói production giữ đúng provider.

## 10. SPI không phải một hệ thống dịch toàn bộ ứng dụng

Giả sử sản phẩm có thông điệp:

~~~properties
# messages_vi.properties
button.save=Lưu
cart.empty=Giỏ hàng chưa có sản phẩm.
~~~

Đó là **tài nguyên ứng dụng**, thường được tìm qua `ResourceBundle` hoặc framework dịch của sản phẩm. Không nên viết `LocaleNameProvider` để thay thế toàn bộ các khóa `button.save` hay `cart.empty`.

Phân biệt:

- **LocaleServiceProvider:** mở rộng một số dịch vụ chuẩn liên quan tới tên/formatter.
- **ResourceBundle:** quản lý bundle theo locale của ứng dụng và các thông điệp/nhãn cụ thể.
- **ResourceBundleProvider / ResourceBundleControlProvider:** là những SPI khác liên quan đến cơ chế tìm/tải resource bundles; không đồng nghĩa `LocaleServiceProvider`.
- **ICU4J / thư viện i18n:** có thể cung cấp khả năng riêng như plural/select nâng cao, locale data/formatting theo thư viện.
- **CLDR:** là nguồn dữ liệu/quy tắc locale; không phải thư viện dịch đoạn văn tự động.

Trong Java 17, `java.text.MessageFormat` không tự hiểu cú pháp ICU plural/select chỉ vì runtime dùng dữ liệu CLDR. Nếu cần biến đổi ngữ pháp theo số nhiều hoặc giống/dạng cách ở nhiều ngôn ngữ, phải chọn engine phù hợp và có bản dịch câu đầy đủ.

## 11. Tránh đệ quy trong chính provider

Một lỗi nguy hiểm khi hiện thực `NumberFormatProvider`:

~~~java
@Override
public NumberFormat getNumberInstance(Locale locale) {
    return NumberFormat.getNumberInstance(locale); // Có thể tra lại chính SPI!
}
~~~

Đây là đoạn **phản ví dụ**, không dùng trong production. Nếu provider đã được chọn cho locale đó và tự gọi lại factory tương ứng, nó có thể đi qua lookup và được chọn lại, gây **đệ quy không kết thúc/StackOverflowError**.

Trong ví dụ đúng, `CustomNumberProvider` xây `DecimalFormat` trực tiếp với `DecimalFormatSymbols` của `Locale.US` rồi thay ký hiệu. Nếu muốn delegate sang provider khác, phải chọn đường đi **không quay lại chính provider** và kiểm soát fallback. Dùng một locale khác cũng cần xét provider khác được cấu hình và khả năng truy hồi vòng; không suy luận tùy tiện.

Một lỗi khác là trả về **một `NumberFormat` dùng chung** cho tất cả request. `DecimalFormat` mutable, có các setter như `setGroupingUsed` và `setMaximumFractionDigits`. Nếu khách hàng sửa formatter nhận từ factory, yêu cầu tiếp theo có thể bị ảnh hưởng nếu cùng chia sẻ instance. Provider nên tạo object mới hoặc thiết kế defensive copy thích hợp.

## 12. Kiểm thử SPI có hệ thống

Đừng chỉ kiểm tra `new CustomNumberProvider()`: cách đó **bỏ qua** descriptor, classpath, ServiceLoader và lựa chọn provider runtime. Cần cả **unit test trực tiếp** lẫn **integration test qua API chuẩn**.

| Tầng kiểm thử | Ví dụ | Kết quả cần kiểm tra |
| --- | --- | --- |
| Unit provider | `getAvailableLocales()` | Locale hỗ trợ đúng, không trả thừa |
| Unit hỗ trợ locale | `isSupportedLocale(en-XZ)` | Trả true |
| Unit từ chối locale | `isSupportedLocale(en-US)` | Trả false nếu không hỗ trợ |
| Unit formatter | `getNumberInstance(en-XZ).format(1234.5)` | Trả `1_234~50` |
| Unit metadata | `getIntegerInstance`, `getCurrencyInstance` | Object hợp lệ, các chính sách đúng |
| Service discovery | File `META-INF/services/...` | Provider được runtime phát hiện |
| Integration factory | `NumberFormat.getNumberInstance(en-XZ)` | Dùng custom provider khi SPI đứng đầu |
| Provider order | `SPI,CLDR` so với `CLDR,SPI` | Hành vi có thể khác theo locale được hỗ trợ |
| Name provider | `Locale.FRENCH.getDisplayLanguage(en-XZ)` | Chọn tên từ provider khi được đăng ký |
| Name fallback | Provider tên trả `null` | Không crash, fallback đúng |
| Unicode extensions | `en-XZ-u-nu-thai` | Chấp nhận/từ chối có chủ đích |
| JVM startup | Property set trước launch | Thứ tự thực tế có hiệu lực |
| Packaging | JAR, classpath, module path, jlink | Tài nguyên service và class có mặt |
| Production migration | Nâng JDK, thay CLDR | Không đổi output quan trọng không kiểm soát |
| Đa luồng | Nhiều formatter gọi đồng thời | Không dùng chung mutable instance sai |

### Checklist chẩn đoán khi factory không dùng SPI

1. Đã chạy `java -Djava.locale.providers=SPI,CLDR ...` từ đầu process chưa?
2. Service file có **đúng tên SPI** (không phải tên lớp triển khai) chưa?
3. Descriptor UTF-8 có đúng **fully qualified class name** của concrete provider không?
4. Provider class có nằm trên classpath/module graph và có thể được loader truy cập không?
5. Provider có public constructor/điều kiện khởi tạo hợp lệ không?
6. Provider có công bố locale yêu cầu trong `getAvailableLocales` không?
7. `isSupportedLocale` có trả true theo hợp đồng không?
8. Có provider khác đứng trước và đã hỗ trợ dịch vụ/locale ấy không?
9. Đang gọi đúng API tiêu thụ loại SPI hay chỉ gọi trực tiếp provider?
10. Có lặp lookup ngay trong provider, dẫn tới đệ quy hoặc lỗi nạp không?

Khi nghi ngờ, ghi rõ **JDK vendor/version**, `java.locale.providers` ngay lúc khởi động, tên locale, đường dẫn JAR/module và output integration test. Không suy ra việc provider đã được sử dụng chỉ vì class biên dịch thành công.

## 13. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Khắc phục |
| --- | --- | --- |
| Coi `LocaleServiceProvider` tự động xử lý mọi locale | Không biết dịch vụ cụ thể để gọi | Kế thừa SPI đúng loại |
| Chỉ tạo class mà không đăng ký service | Factory không tìm thấy provider | `META-INF/services` hoặc JPMS `provides` |
| Đặt service file theo tên concrete class | ServiceLoader bỏ qua cấu hình | Dùng tên đầy đủ của SPI |
| Quên `SPI` trong `java.locale.providers` trên JDK17 | Provider classpath không được ưu tiên/tra | Đặt startup property phù hợp |
| Đặt property sau khi JVM đã khởi động | Không đổi thứ tự locale lookup | Đặt trong lệnh launch |
| Nghĩ SPI luôn thắng CLDR | Thứ tự provider có thể ngược | Cấu hình và test đúng order |
| Khai báo tất cả locale khi chỉ hỗ trợ một | Format sai hoặc lỗi bất ngờ | Danh sách hỗ trợ chính xác |
| Bỏ qua Unicode extensions | Chọn locale có numbering system không hỗ trợ | Override `isSupportedLocale` khi cần |
| Gọi factory giống loại bên trong chính provider | Đệ quy lookup | Xây formatter trực tiếp/delegate an toàn |
| Trả chung DecimalFormat mutable | Race condition/đổi config giữa request | Trả formatter mới |
| Nghĩ name provider và format provider giống nhau | Sai contract về `String`/`NumberFormat` | Tách từng SPI |
| Trả `null` cho formatter không có hỗ trợ | Có thể vi phạm hợp đồng object | Chỉ hỗ trợ locale thật, trả object hợp lệ |
| Coi SPI tên là dịch các thông báo sản phẩm | Các key UI vẫn không có nội dung | ResourceBundle hoặc hệ dịch ứng dụng |
| Dùng SPI thời gian `java.text` để giả định override mọi `java.time` API | Không có bảo đảm như vậy | Kiểm tra từng API/dịch vụ |
| Dựa vào `COMPAT` trên JDK23+ | Legacy data đã bị loại bỏ | Chuyển CLDR hoặc provider riêng |
| Chỉ test gọi provider trực tiếp | Không phát hiện lỗi đóng gói | Integration test qua API JDK |

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `LocaleServiceProvider` có phải một class chỉ cần new lên là toàn bộ định dạng JDK tự thay đổi không?

**Đáp án:** Không. Cần kế thừa SPI cụ thể, hiện thực các phương thức theo contract, đăng ký dịch vụ và cấu hình lookup phù hợp.

**Câu 2.** Trong ví dụ `NumberFormatProvider`, vì sao không gọi `NumberFormat.getNumberInstance(demoLocale)` bên trong chính `getNumberInstance`?

**Đáp án:** Đường factory có thể chọn lại cùng provider, tạo đệ quy. Ví dụ xây `DecimalFormat` trực tiếp với symbols được kiểm soát.

**Câu 3.** `LocaleNameProvider.getDisplayLanguage("fr", locale)` có hai đối số nhằm mục đích gì?

**Đáp án:** `"fr"` là mã ngôn ngữ muốn lấy tên; `locale` là ngôn ngữ/vùng dùng để viết tên hiển thị ấy.

**Câu 4.** Vì sao unit test `new CustomNumberProvider()` thành công nhưng `NumberFormat.getNumberInstance(locale)` vẫn không dùng formatter demo?

**Đáp án:** Gọi trực tiếp không kiểm tra đăng ký/lookup. Cần descriptor đúng, classpath/module đúng và `java.locale.providers` phù hợp khi launch.

**Câu 5.** Nếu một provider tên không có tên được yêu cầu, nó có được trả `null` không?

**Đáp án:** Với các provider trả **tên hiển thị** như `LocaleNameProvider`, trả `null` cho tên chưa có là hành vi được phép và lookup có thể fallback. Không khái quát hóa cho các provider trả formatter object.

**Câu 6.** Thứ tự `SPI,CLDR` và `CLDR,SPI` có giống nhau không?

**Đáp án:** Không. Nếu cả hai nguồn có dữ liệu cho một dịch vụ/locale, nguồn được ưu tiên trước có thể quyết định kết quả.

**Bài tập thực hành:** Đổi locale thử nghiệm và pattern của `CustomNumberProvider`, thêm test `getIntegerInstance` và `getPercentInstance`. Đăng ký class bằng descriptor, chạy với `SPI,CLDR` và `CLDR,SPI`, so sánh kết quả qua API factory. Viết thêm một `LocaleNameProvider` trả tên cho vài mã ngôn ngữ; thử name lookup với locale hỗ trợ và locale không hỗ trợ. Cuối cùng, mô tả cách đóng gói cả hai provider trong một JAR mà vẫn có **hai service descriptors riêng**.

## 15. Tài liệu chính thức

- [LocaleServiceProvider — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/LocaleServiceProvider.html): danh sách SPI, `getAvailableLocales`, `isSupportedLocale`, packaging và `java.locale.providers`.
- [NumberFormatProvider — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/spi/NumberFormatProvider.html): bốn phương thức tạo formatter và `getCompactNumberInstance`.
- [LocaleNameProvider — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/LocaleNameProvider.html): tên ngôn ngữ, quốc gia, variant, script.
- [CurrencyNameProvider — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/CurrencyNameProvider.html): SPI cho tên/ký hiệu tiền.
- [DateFormatProvider — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/spi/DateFormatProvider.html): SPI định dạng ngày theo `java.text`.
- [ServiceLoader — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): cơ chế phát hiện service classpath/module.
- [JEP 252 — Use CLDR Locale Data by Default](https://openjdk.org/jeps/252): cấu hình provider và dữ liệu CLDR.
- [Oracle JDK 17 Supported Locales](https://www.oracle.com/java/technologies/javase/jdk17-suported-locales.html): CLDR, COMPAT, SPI, HOST trong JDK 17.
- [JDK 23 migration — removed COMPAT/JRE](https://docs.oracle.com/en/java/javase/23/migrate/removed-tools-and-components.html): thay đổi khi nâng JDK.

**Ghi nhớ:** `LocaleServiceProvider` là nền tảng của các SPI bản địa hóa, nhưng **phải chọn đúng provider cho đúng dịch vụ**, khai báo locale hỗ trợ chính xác, đăng ký class và điều chỉnh thứ tự `java.locale.providers` khi khởi động. Nhà cung cấp tên như `LocaleNameProvider` trả chuỗi bản địa hóa; nhà cung cấp định dạng như `NumberFormatProvider` trả formatter. SPI mở rộng một số API Java Core, **không tự dịch nội dung ứng dụng**, không thay quy tắc tiền tệ/ngữ pháp nghiệp vụ và không được dùng thay cho kiểm thử locale thực tế.

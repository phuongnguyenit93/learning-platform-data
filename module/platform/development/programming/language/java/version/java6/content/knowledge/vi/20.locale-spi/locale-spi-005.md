# Locale SPI: Đăng ký provider qua cơ chế SPI trong Java hiện đại

## 1. Mục tiêu: đăng ký thành công khác với được runtime ưu tiên sử dụng

Java cung cấp các API phụ thuộc ngôn ngữ/vùng như `Locale.getDisplayLanguage`, `NumberFormat`, `DateFormat`, `Collator` và `BreakIterator`. JDK mặc định có dữ liệu locale của riêng mình, hiện nay chủ yếu theo **Unicode Common Locale Data Repository (CLDR)**. Khi ứng dụng cần tên ngôn ngữ đặc thù, dữ liệu cho locale mới hoặc formatter riêng, có thể triển khai **Locale Service Provider Interface (Locale SPI)**.

Có **hai bước độc lập**:

1. **Đăng ký/discovery:** JDK có thể tìm class provider do ứng dụng cung cấp qua `META-INF/services` trên classpath hoặc `provides ... with ...` của JPMS module.
2. **Chọn nguồn dữ liệu:** các API locale của JDK quyết định có ưu tiên **SPI** hơn nguồn **CLDR** hoặc nguồn khác không. Trên JDK hiện đại, mặc định là `CLDR`; nếu muốn custom Locale SPI được ưu tiên, thường cần đặt **trước lúc JVM khởi động**:

~~~bash
java -Djava.locale.providers=SPI,CLDR ...
~~~

**Điểm hay sai:** Thấy `ServiceLoader.load(...)` tìm được provider không có nghĩa `Locale.getDisplayLanguage(...)` sẽ gọi nó khi cấu hình vẫn ưu tiên CLDR. Bài này phân biệt rõ **provider visible** và **provider used**.

Hai cách đăng ký hiện hành trong Java 17+:

- **JAR/classpath:** tệp `META-INF/services/<fully.qualified.ServiceType>` chứa tên class implementation.
- **JPMS/explicit named module:** `module-info.java` có `provides <ServiceType> with <ImplementationType>;`, và provider module được resolve trong module graph.

Bài dùng một ví dụ tự chạy bằng Java 17+ và đã đối chiếu kết quả với OpenJDK 24.0.2. Nội dung không khuyến nghị cách đóng gói lỗi thời như Java Extension Mechanism hoặc cấu hình `JRE/COMPAT` locale data đã bị loại bỏ ở JDK 23.

## 2. Các khái niệm không được đánh đồng

| Khái niệm | Vai trò trong ứng dụng |
| --- | --- |
| `Locale` | Mô tả language, script, country/region, variant và extensions |
| `LocaleServiceProvider` | Abstract superclass của các Locale SPI cụ thể; có `getAvailableLocales`, `isSupportedLocale` |
| `LocaleNameProvider` | Một Locale SPI cụ thể, trả tên hiển thị ngôn ngữ/quốc gia/variant/script |
| `java.text.spi.NumberFormatProvider` | Provider cho các formatter số theo locale |
| **Implementation** | Một concrete Java class, ví dụ `demo.spi.QaaLocaleNameProvider` |
| **Service type** | Tên chính xác JDK tìm, ví dụ `java.util.spi.LocaleNameProvider` |
| **Service descriptor** | File `META-INF/services/java.util.spi.LocaleNameProvider` bên trong JAR classpath |
| `module-info.java` | Đăng ký named module bằng `provides java.util.spi.LocaleNameProvider with ...` |
| `ServiceLoader` | API chung tìm providers theo service type; hữu ích để chẩn đoán discovery |
| `java.locale.providers` | Cấu hình thứ tự nguồn locale data cho các JDK locale-sensitive APIs |
| `CLDR` | Nguồn locale data mặc định của JDK hiện đại |
| `SPI` | Nguồn locale data từ các providers implement những Locale SPIs cụ thể |

**Phải đăng ký đúng service type.** Ví dụ provider kế thừa `LocaleNameProvider` thì tên file **không** phải `META-INF/services/java.util.spi.LocaleServiceProvider`. `LocaleServiceProvider` là lớp cha, không phải service được các API tên ngôn ngữ yêu cầu trong ví dụ này.

Tương tự, nếu viết `java.text.spi.NumberFormatProvider`, file service phải tên `META-INF/services/java.text.spi.NumberFormatProvider`. Những SPIs dùng chung cú pháp ServiceLoader nhưng có **hợp đồng implement khác nhau**.

### Phân biệt locale cần gọi tên với locale dùng để hiển thị

Phương thức của `LocaleNameProvider`:

~~~java
String getDisplayLanguage(String languageCode, Locale locale)
~~~

- `languageCode` là **mã ngôn ngữ muốn lấy tên**, ví dụ `"qaa"`.
- `locale` là **locale người dùng muốn xem tên đó bằng ngôn ngữ nào**, ví dụ `en-US`.

Khi provider cung cấp tên tiếng Anh cho mã `qaa`, `getAvailableLocales()` cần khai báo **display locale** `en-US`, không phải nhất thiết khai báo `qaa`. Đây là lỗi ngữ nghĩa thường làm một provider “đã đăng ký” nhưng không được gọi.

`qaa` nằm trong dải mã ISO 639 dành cho **local/private use**; dùng ở đây làm dữ liệu thử dễ phân biệt. Không tự đưa tên thử nghiệm này vào danh mục ngôn ngữ công khai của sản phẩm.

## 3. Hợp đồng implement `LocaleNameProvider`

`java.util.spi.LocaleNameProvider` là abstract class, kế thừa `LocaleServiceProvider`. Ví dụ nhỏ cần:

1. Một public concrete class, không abstract, với **public no-argument constructor** khi dùng service configuration trên classpath.
2. `Locale[] getAvailableLocales()` liệt kê các display locales mà provider hỗ trợ.
3. `String getDisplayLanguage(String languageCode, Locale locale)` trả tên phù hợp hoặc `null` nếu không có.
4. `getDisplayCountry(...)` và `getDisplayVariant(...)` được implement vì là abstract methods.
5. Không tự trả một tên không đúng cho mọi languageCode: provider name methods được phép trả `null` để runtime tiếp tục fallback.
6. Khi hỗ trợ script hoặc Unicode extension display names, override những method tương ứng theo API hiện hành; chúng có default implementation nên **không bắt buộc** với ví dụ nhỏ.

`LocaleServiceProvider.isSupportedLocale` mặc định kiểm tra trong danh sách `getAvailableLocales()` và thông thường bỏ qua locale extensions. Nếu extension là một phần điều kiện hỗ trợ của implementation, override `isSupportedLocale` đúng hợp đồng, có test cho cả extension-supported và unsupported.

Đừng trả danh sách tất cả locales chỉ để “provider luôn được chọn” nếu dữ liệu chỉ có cho một số locales. Việc `getAvailableLocales` công bố quá rộng trong khi methods trả `null` ở gần như mọi trường hợp khiến hệ thống khó chẩn đoán và phụ thuộc fallback không cần thiết.

## 4. Classpath registration: `META-INF/services`

Giả sử project có cấu trúc:

~~~text
locale-spi-demo/
├── src/
│   └── demo/
│       ├── spi/QaaLocaleNameProvider.java
│       └── app/LocaleSpiDemo.java
├── provider-classes/                      (build tạo)
├── app-classes/                           (build tạo)
└── locale-provider.jar                    (build tạo)
~~~

Sau compile và packaging, **bên trong `locale-provider.jar`** cần có ít nhất:

~~~text
demo/spi/QaaLocaleNameProvider.class
META-INF/services/java.util.spi.LocaleNameProvider
~~~

Nội dung chính xác của service descriptor, một dòng UTF-8:

~~~text
demo.spi.QaaLocaleNameProvider
~~~

Hợp đồng của `ServiceLoader`:

- Tên **file** bằng fully qualified name của **service**, không phải implementation.
- Nội dung gồm fully qualified names của **provider implementation**, mỗi class một dòng.
- Descriptor được mã hóa **UTF-8**; có thể có dòng trắng, khoảng trắng/tab bao quanh tên và comment `#`.
- Duplicate provider names bị bỏ qua theo hợp đồng; đừng cố tạo thứ tự ưu tiên runtime từ thứ tự lặp lại cùng tên trong descriptor.
- Provider implementation phải load được, tương thích service type và có constructor phù hợp; dependency của provider cũng phải ở class/module path truy cập được.
- Tệp phải nằm **bên trong JAR** tại đúng `META-INF/services/...`, không phải một file cạnh JAR trên đĩa.

Với Maven/Gradle, thường đưa descriptor vào `src/main/resources/META-INF/services/java.util.spi.LocaleNameProvider` rồi để build đóng gói. Với ví dụ thủ công bên dưới, tạo file **sau khi biên dịch provider**, rồi gọi `jar`.

Đừng sử dụng service descriptor kiểu Annotation Processor (`javax.annotation.processing.Processor`), `java.util.spi.ResourceBundleProvider` hay một service tùy ý như tên thay thế cho LocaleNameProvider.

## 5. Chương trình Java 17+ đầy đủ, không cần thư viện thứ ba

Ví dụ có hai source files: provider và một app quan sát kết quả. App test **hai hiện tượng**: direct `ServiceLoader` có nhìn thấy implementation không, và `Locale.getDisplayLanguage` đang lấy dữ liệu từ CLDR hay SPI.

### 5.1. `src/demo/spi/QaaLocaleNameProvider.java`

~~~java
package demo.spi;

import java.util.Locale;
import java.util.spi.LocaleNameProvider;

public final class QaaLocaleNameProvider extends LocaleNameProvider {
    private static final Locale DISPLAY = Locale.forLanguageTag("en-US");

    public QaaLocaleNameProvider() {}

    @Override
    public Locale[] getAvailableLocales() {
        return new Locale[] { DISPLAY };
    }

    @Override
    public String getDisplayLanguage(String languageCode, Locale locale) {
        if ("qaa".equals(languageCode) && DISPLAY.equals(locale)) {
            return "Demo language QAA";
        }
        return null;
    }

    @Override
    public String getDisplayCountry(String countryCode, Locale locale) {
        return null;
    }

    @Override
    public String getDisplayVariant(String variant, Locale locale) {
        return null;
    }
}
~~~

**Giải thích:**

- `DISPLAY` là locale `en-US` dùng để hiển thị **tên ngôn ngữ bằng tiếng Anh**.
- `getAvailableLocales()` liệt kê đúng locale do provider hỗ trợ; không liệt kê `qaa` vì `qaa` là mã cần được gọi tên.
- Provider trả tên được định nghĩa riêng `Demo language QAA` cho một yêu cầu duy nhất; với tên khác trả `null`.
- No-arg constructor được khai báo `public` để tương thích cơ chế classpath provider instantiation.
- `Locale.forLanguageTag("en-US")` có trên Java 17, tránh dùng `new Locale(...)` đã deprecated ở những bản Java mới.
- Các method này có thể được gọi từ nhiều thread trong ứng dụng; demo stateless, không tạo biến trạng thái mutable hoặc IO.

### 5.2. `src/demo/app/LocaleSpiDemo.java`

~~~java
package demo.app;

import java.util.Locale;
import java.util.ServiceLoader;
import java.util.spi.LocaleNameProvider;

public final class LocaleSpiDemo {
    public static void main(String[] args) {
        Locale display = Locale.forLanguageTag("en-US");
        Locale language = Locale.forLanguageTag("qaa");

        long providerCount = ServiceLoader.load(LocaleNameProvider.class)
                .stream()
                .filter(p -> p.type().getName()
                        .equals("demo.spi.QaaLocaleNameProvider"))
                .count();

        System.out.println("registered provider visible: " + (providerCount == 1));
        System.out.println("display name: " + language.getDisplayLanguage(display));
    }
}
~~~

`ServiceLoader.load(LocaleNameProvider.class)` dùng service discovery thông thường. `stream().filter(...).count()` tìm provider type theo tên đã biết; `ServiceLoader.Provider.type()` có thể được dùng mà không nhất thiết khởi tạo instance. Nếu descriptor sai, service loading có thể gặp `ServiceConfigurationError`.

Lời gọi `language.getDisplayLanguage(display)` là phép thử **API locale thực sự**. Nó có thể lấy dữ liệu theo CLDR hoặc provider tùy runtime preference. Cả hai phép thử phải được quan sát riêng; một `true` của `registered provider visible` chưa chứng minh thứ tự `java.locale.providers` đúng.

## 6. Build và chạy ở classpath: kiểm chứng hai trường hợp

Các lệnh sau dùng **Bash/Linux/macOS** hoặc shell có lệnh POSIX tương ứng, chạy tại thư mục `locale-spi-demo` có hai file từ phần 5.

### 6.1. Biên dịch provider, đặt service descriptor, đóng JAR

~~~bash
mkdir -p provider-classes/META-INF/services app-classes

javac --release 17 \
  -d provider-classes \
  src/demo/spi/QaaLocaleNameProvider.java

printf '%s\n' 'demo.spi.QaaLocaleNameProvider' \
  > provider-classes/META-INF/services/java.util.spi.LocaleNameProvider

jar --create --file locale-provider.jar -C provider-classes .

javac --release 17 \
  -d app-classes \
  src/demo/app/LocaleSpiDemo.java
~~~

**Vì sao theo thứ tự này?** Provider class phải tồn tại, descriptor phải được copy vào đúng output directory rồi mới đóng JAR. `LocaleSpiDemo` không cần import provider implementation; app compile độc lập trên API chuẩn, phù hợp nguyên tắc service consumer không phụ thuộc implementation.

Có thể kiểm tra JAR:

~~~bash
jar --list --file locale-provider.jar
~~~

Các mục quan trọng phải nhìn thấy:

~~~text
demo/spi/QaaLocaleNameProvider.class
META-INF/services/java.util.spi.LocaleNameProvider
~~~

Đây chỉ là **hai mục cần hiện diện**, không phải stdout đầy đủ của lệnh liệt kê JAR; còn có manifest và folder entries.

### 6.2. Mặc định CLDR: provider vẫn được ServiceLoader nhìn thấy

~~~bash
java -cp app-classes:locale-provider.jar demo.app.LocaleSpiDemo
~~~

Stdout **đã kiểm thử trên OpenJDK 24.0.2**:

~~~text
registered provider visible: true
display name: qaa
~~~

Với JDK này, `ServiceLoader` nhìn thấy provider vì JAR/descriptor đúng. Nhưng `Locale.getDisplayLanguage` vẫn dùng CLDR mặc định trong thử nghiệm; tên chưa có dữ liệu được trả như code `qaa`. Đừng coi output `qaa` là một “lỗi đăng ký”.

### 6.3. Bật `SPI,CLDR`: Locale API chọn custom provider

~~~bash
java -Djava.locale.providers=SPI,CLDR \
  -cp app-classes:locale-provider.jar \
  demo.app.LocaleSpiDemo
~~~

Stdout **đã kiểm thử trên OpenJDK 24.0.2**:

~~~text
registered provider visible: true
display name: Demo language QAA
~~~

Lúc này `SPI` được ưu tiên trước `CLDR`. Provider trả tên cho `qaa` trong `en-US` nên kết quả đến từ implementation của ta. Nếu provider không có giá trị hoặc trả `null`, runtime có thể fallback qua CLDR hoặc candidate locale/provider khác theo API.

Đường dẫn classpath khác nhau theo hệ điều hành. Ví dụ chạy với **PowerShell/Windows**, lệnh một dòng:

~~~powershell
java '-Djava.locale.providers=SPI,CLDR' -cp 'app-classes;locale-provider.jar' demo.app.LocaleSpiDemo
~~~

Trên Windows, `;` là classpath separator; trên Linux/macOS dùng `:`. `-Djava.locale.providers` phải đứng như một **JVM option trước tên main class**, không phải argument truyền cho `main(String[])`.

**Giới hạn đầu ra mong đợi:** Ba phép thử đã chạy trên JDK 24.0.2 với `--release 17`. Giá trị CLDR trả về khi không có custom provider có thể khác trên một JDK/CLDR phiên bản khác; kết quả `Demo language QAA` là dấu hiệu do chính provider demo tạo ra.

## 7. JPMS: đăng ký bằng `provides ... with ...`

Với Java Platform Module System (Java 9+), provider ở **explicit named module** không cần file service descriptor của classpath. Thay vào đó khai báo service trong `module-info.java`.

Tạo file `module-src/demo.locale.spi/module-info.java`:

~~~java
module demo.locale.spi {
    provides java.util.spi.LocaleNameProvider
            with demo.spi.QaaLocaleNameProvider;
}
~~~

Đây là **module descriptor hoàn chỉnh** cho ví dụ provider. `java.base` được read ngầm, nên không cần `requires java.base`. Package implementation `demo.spi` không cần `exports` chỉ để ServiceLoader tạo instance qua `provides`.

Bố cục file:

~~~text
module-src/
└── demo.locale.spi/
    ├── module-info.java
    └── demo/spi/QaaLocaleNameProvider.java
~~~

Copy **nguyên nội dung** provider từ phần 5.1 sang module source rồi build:

~~~bash
mkdir -p module-src/demo.locale.spi/demo/spi module-classes
cp src/demo/spi/QaaLocaleNameProvider.java \
  module-src/demo.locale.spi/demo/spi/QaaLocaleNameProvider.java

javac --release 17 \
  -d module-classes \
  module-src/demo.locale.spi/module-info.java \
  module-src/demo.locale.spi/demo/spi/QaaLocaleNameProvider.java

jar --create --file locale-provider-module.jar -C module-classes .
~~~

Dùng application `demo.app.LocaleSpiDemo` **trên classpath**, provider **trên module path**, và resolve provider module:

~~~bash
java -Djava.locale.providers=SPI,CLDR \
  --module-path locale-provider-module.jar \
  --add-modules demo.locale.spi \
  -cp app-classes \
  demo.app.LocaleSpiDemo
~~~

Stdout **đã kiểm thử trên OpenJDK 24.0.2**:

~~~text
registered provider visible: true
display name: Demo language QAA
~~~

### Vì sao thêm `--add-modules`?

Đặt JAR trên `--module-path` chưa chứng minh module provider được **resolved vào module graph** cho phép thử. `--add-modules demo.locale.spi` buộc resolve module này. Một ứng dụng modular thực sự có thể được resolve qua cơ chế module/service binding thích hợp khác; điều quan trọng là **provider module phải có trong graph runtime**.

Nếu ứng dụng cũng là một **named module** và trực tiếp gọi `ServiceLoader.load(LocaleNameProvider.class)`, descriptor của consumer cần `uses`:

~~~java
module demo.locale.app {
    uses java.util.spi.LocaleNameProvider;
}
~~~

Đây là **đoạn module descriptor minh họa cho consumer**, không đặt chung với `module-info.java` của provider. `uses` nghĩa là module **yêu cầu service**; `provides ... with ...` nghĩa là module **cung cấp provider**. Nếu service thuộc module khác, consumer phải có module readability thích hợp; ở ví dụ này `LocaleNameProvider` thuộc `java.base`.

**Lưu ý:** Một named module không nhất thiết phải export package provider implementation. ServiceLoader có thể tạo provider dựa trên `provides` mà không yêu cầu consumer được truy cập class đó qua import thông thường.

## 8. Chính sách `java.locale.providers` trong Java 17+

Javadoc của `LocaleServiceProvider` định nghĩa một property chọn **thứ tự nguồn locale data**:

~~~text
java.locale.providers=SPI,CLDR
~~~

| Giá trị | Mục đích |
| --- | --- |
| `SPI` | Các Locale Service Provider implementations do ứng dụng cài đặt |
| `CLDR` | Dữ liệu Unicode CLDR do JDK cung cấp |
| `HOST` | Cấu hình locale của hệ điều hành nếu JDK/platform có hỗ trợ |
| Không set property | Mặc định tương đương `CLDR` theo JDK hiện hành |

`SPI,CLDR` ưu tiên SPI trước; `CLDR,SPI` ưu tiên CLDR trước ở những service/locale có dữ liệu tương ứng. Đừng coi thứ tự trong service descriptor là cách thay thế property này: descriptor quyết định **provider có được phát hiện không**, còn property quyết định **nguồn nào có cơ hội được hỏi trước**.

### Phải cấu hình tại JVM startup

JDK đọc và cache thứ tự locale providers khi subsystem được khởi tạo. Hãy dùng:

~~~bash
java -Djava.locale.providers=SPI,CLDR -cp app-classes:locale-provider.jar demo.app.LocaleSpiDemo
~~~

Không dựa vào lời gọi:

~~~java
System.setProperty("java.locale.providers", "SPI,CLDR");
~~~

**sau khi chương trình đã chạy** để mong runtime tái khởi tạo locale provider pool. System property có thể đã được đọc/cached, nên setting muộn **không bảo đảm hiệu lực**. Để so sánh hành vi giữa hai chính sách, chạy **hai JVM processes riêng**.

### JDK 23+ loại bỏ dữ liệu locale legacy

JDK 23 loại bỏ `JRE`/`COMPAT` locale data. Không dùng `-Djava.locale.providers=JRE,SPI` như một cách hiện đại để nhận dữ liệu của JDK 8 trước đây. Nếu hệ thống từng phụ thuộc legacy formatting, hãy kiểm thử lại dưới CLDR và, khi có nhu cầu thật, viết formatter/policy riêng hoặc provider SPI được kiểm soát.

Dữ liệu CLDR thay đổi theo các phiên bản JDK; output như tên ngôn ngữ, ký hiệu số, định dạng ngày/tháng có thể khác qua một lần upgrade. Với các hệ thống đòi hỏi output ổn định, cần test vectors theo runtime/locale policy thay vì so sánh toàn bộ chuỗi format một cách mù quáng xuyên version.

## 9. Các Locale SPI cụ thể và tên service file

| SPI cụ thể | Dữ liệu/capability cung cấp | File đăng ký khi dùng classpath |
| --- | --- | --- |
| `java.util.spi.LocaleNameProvider` | Localized language/country/script/variant names | `META-INF/services/java.util.spi.LocaleNameProvider` |
| `java.util.spi.CurrencyNameProvider` | Tên hoặc ký hiệu tiền tệ | `META-INF/services/java.util.spi.CurrencyNameProvider` |
| `java.util.spi.TimeZoneNameProvider` | Localized time-zone names | `META-INF/services/java.util.spi.TimeZoneNameProvider` |
| `java.text.spi.NumberFormatProvider` | NumberFormat locale-specific instances | `META-INF/services/java.text.spi.NumberFormatProvider` |
| `java.text.spi.DateFormatProvider` | DateFormat locale-specific instances | `META-INF/services/java.text.spi.DateFormatProvider` |
| `java.text.spi.DecimalFormatSymbolsProvider` | Decimal formatting symbols | `META-INF/services/java.text.spi.DecimalFormatSymbolsProvider` |
| `java.text.spi.DateFormatSymbolsProvider` | Date/time formatting symbols | `META-INF/services/java.text.spi.DateFormatSymbolsProvider` |
| `java.text.spi.CollatorProvider` | So sánh/sắp xếp chuỗi theo locale | `META-INF/services/java.text.spi.CollatorProvider` |
| `java.text.spi.BreakIteratorProvider` | Phân đoạn từ/câu theo locale | `META-INF/services/java.text.spi.BreakIteratorProvider` |

`NumberFormatProvider`, `DateFormatProvider`, `CollatorProvider` và các subclasses khác có **abstract methods khác nhau**; không lấy code của `LocaleNameProvider` rồi chỉ thay tên class để mong nó biên dịch. Xem đúng Javadoc khi triển khai.

### `ResourceBundleProvider` không phải Locale SPI

`java.util.spi.ResourceBundleProvider` là SPI cho resource bundle services, đặc biệt hữu ích trong JPMS. Nó **không phải subclass của `LocaleServiceProvider`**. Việc đăng ký `ResourceBundleProvider` có quy tắc module/provider phù hợp với resource bundles, và **không** được kích hoạt chỉ nhờ đổi `java.locale.providers` thành `SPI,CLDR`.

Tương tự, một annotation processor có service `javax.annotation.processing.Processor`. Chúng đều có thể dùng ServiceLoader hoặc module provides, nhưng mỗi service có **consumer và activation contract riêng**.

## 10. Phân biệt `ServiceLoader` trực tiếp với Locale API

### Test A: provider có visible không?

~~~java
long providerCount = ServiceLoader.load(LocaleNameProvider.class)
        .stream()
        .filter(p -> p.type().getName()
                .equals("demo.spi.QaaLocaleNameProvider"))
        .count();
System.out.println("registered provider visible: " + (providerCount == 1));
~~~

Đây là đoạn nằm trong app đầy đủ. Khi trả `true`, provider type có thể được khám phá bởi service loader dùng ở caller. Nếu vẫn không có output custom khi gọi `Locale.getDisplayLanguage`, không vội kết luận descriptor sai.

**Lưu ý ClassLoader:** `LocaleServiceProvider` documentation yêu cầu locale providers có thể được **system class loader nhìn thấy**. `ServiceLoader.load(service, customChildLoader)` có thể tìm thấy một provider trong child loader do ứng dụng tạo, nhưng không có nghĩa các factory locale của JDK tự tìm mọi child loader. Đừng coi service lookup theo một custom loader là bằng chứng provider đã được hệ thống locale tích hợp.

### Test B: Locale API có chọn provider không?

~~~java
Locale display = Locale.forLanguageTag("en-US");
Locale language = Locale.forLanguageTag("qaa");
System.out.println(language.getDisplayLanguage(display));
~~~

Đây là đoạn minh họa. Khi chạy đúng example JAR với `SPI,CLDR`, tên custom là `Demo language QAA`. Nếu Test A `true` nhưng Test B vẫn `qaa` hoặc kết quả CLDR khác, kiểm tra:

1. Có `-Djava.locale.providers=SPI,CLDR` **trước main class** khi JVM khởi động không?
2. `getAvailableLocales` có chứa **display locale `en-US`**, không nhầm với language code `qaa`?
3. `getDisplayLanguage("qaa", en-US)` có trả custom string khác `null` không?
4. Provider có thực sự ở system-loader-visible classpath hoặc resolved module path không?
5. Có một provider khác hoặc CLDR được ưu tiên do policy khác không?
6. Source app có gọi đúng API thuộc `LocaleNameProvider` thay vì một service SPI khác không?
7. JDK/CLDR version, locale extensions và fallback policy có khác điều kiện test không?

Nếu provider trả `null` cho một tên, fallback là **hành vi hợp lệ**. Một Locale SPI provider không cần cung cấp tên cho mọi code tồn tại trên thế giới.

### `ServiceLoader.reload()` không phải global locale reload

`ServiceLoader.reload()` xóa cache providers của **chính ServiceLoader instance** mà bạn đang quản lý. Nó không buộc JDK đọc lại `java.locale.providers`, không đổi thứ tự CLDR/SPI sau khởi tạo, và không bảo đảm toàn bộ locale service caches của JVM được làm mới. Không xây hot deployment dựa trên giả định gọi `reload()` là đủ.

## 11. Thực hành theo lifecycle đúng với hệ thống production

### Classpath và module boundaries

Provider JAR cần có trong phạm vi mà JDK có thể nhìn thấy khi khởi động. Nếu dùng plugin riêng với child ClassLoader và thay JAR giữa các requests, không thể mặc định các JDK locale factories sẽ thay provider cùng nó. Trong nhiều hệ thống, **đổi provider locale là thay đổi cấu hình cấp process**, vì provider preference được đọc/cached và dữ liệu có thể được cache trong runtime.

Nếu sản phẩm phải cung cấp các tên/dữ liệu khác nhau theo tenant trên từng request, có thể dùng **abstraction ứng dụng tự quản lý theo tenant** hoặc ResourceBundle đúng scope thay vì dựa vào `java.locale.providers` như một router thay đổi động theo request.

### Những trường hợp lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy provider | Descriptor thiếu, sai đường dẫn hoặc tên service | Kiểm tra `jar --list` và tên file trong `META-INF/services` |
| `ServiceConfigurationError` | Provider class không load được, thiếu dependency, constructor sai hoặc service type không phù hợp | Kiểm tra implementation + dependency và thông tin lỗi |
| ServiceLoader thấy provider nhưng output vẫn CLDR | Mặc định chỉ `CLDR` | Dùng `SPI,CLDR` tại JVM startup |
| SPI được bật nhưng không có giá trị custom | Display locale không nằm trong `getAvailableLocales` hoặc method trả `null` | Kiểm tra mã language và display locale |
| Build module nhưng service vẫn không visible | Quên `provides` hoặc module chưa resolved | Kiểm tra `module-info.java`, `--module-path`, `--add-modules` |
| Named consumer dùng ServiceLoader bị lỗi | Chưa khai báo `uses` | Thêm `uses <service>;` vào module descriptor consumer |
| Chỉ đặt service descriptor của classpath vào explicit module | Đăng ký không theo mô hình JPMS được yêu cầu | Dùng `provides ... with ...` |
| Cập nhật property trong main không tác động | JDK đã cache provider preference | Đặt `-Djava.locale.providers` trước startup, thử trong JVM mới |
| Chạy trên JDK 23+ nhưng dùng `COMPAT/JRE` | Legacy provider đã bị loại bỏ | Dựa vào CLDR/SPI/HOST hiện hành |
| Chỉ giữ một bản locale trong test | Không thấy lỗi fallback và sự khác nhau của providers | Kiểm thử input có/không có custom value và nhiều display locales |
| JDK nâng cấp cho tên khác | CLDR data thay đổi | Pin toolchain khi cần, chạy compatibility tests |
| Trộn `Locale.getDefault()` vào test | Test không tái lập giữa máy | Truyền `Locale.forLanguageTag` rõ ràng |

### An toàn

Locale provider là **Java code chạy trong tiến trình JVM**, không phải một file dữ liệu vô hại. Lệnh gọi tưởng chỉ đọc tên ngôn ngữ có thể làm JDK khởi tạo provider và chạy method do provider implement. Vì vậy:

- Chỉ chấp nhận JAR/module provider và dependencies từ nguồn đáng tin cậy, kiểm tra version/artifact provenance.
- Hạn chế side effects, network/file IO và blocking operations trong provider methods; chúng có thể được gọi trên đường xử lý request quan trọng.
- Thiết kế stateless hoặc thread-safe nếu nhiều thread dùng locale services song song.
- Không giả định ClassLoader riêng tự tạo thành sandbox quyền file/network/process.
- Đặt policy cho locale codes, display locales, supported extensions, fallback và output format, test qua toolchain được hỗ trợ.
- Không log thông tin bí mật hoặc dữ liệu đầu vào không kiểm soát từ yêu cầu external.
- Với formatting số và ngày phục vụ nghiệp vụ, kiểm soát riêng timezone, rounding, parsing policy và CLDR version; provider đăng ký đúng **không tự đảm bảo correctness** cho mọi ngữ cảnh.

## 12. Checklist trước khi phát hành

1. Chọn đúng **service type cụ thể** như `LocaleNameProvider` hay `NumberFormatProvider`; không đăng ký nhầm `LocaleServiceProvider` superclass.
2. Provider class public concrete, public no-arg constructor khi dùng classpath, các abstract methods được implement đầy đủ.
3. `getAvailableLocales()` phản ánh **display locales** thực sự hỗ trợ; các missing names trả `null` để fallback.
4. Classpath JAR có đúng `META-INF/services/<service>` với UTF-8 và tên implementation chính xác.
5. Explicit named module dùng đúng `provides ... with ...`; module hiện diện trong resolved runtime graph.
6. Application named module chỉ dùng direct ServiceLoader khi đã có `uses` thích hợp.
7. JVM khởi động với thứ tự provider mong muốn, thường `-Djava.locale.providers=SPI,CLDR`.
8. Không gọi `System.setProperty` muộn để mong thay thứ tự đã cached.
9. Kiểm tra **service discovery** và **API locale result** bằng hai assertions riêng.
10. Test provider returns `null`, các locales không hỗ trợ, trường hợp CLDR fallback.
11. Test JDK/platform version cần hỗ trợ, đặc biệt khác biệt dữ liệu CLDR và việc `COMPAT` không còn từ JDK 23.
12. Có kế hoạch restart/rollback nếu thay provider; không coi `ServiceLoader.reload` là global reset.
13. Audit dependency security và runtime permissions của Java provider code.

## 13. Câu hỏi tự kiểm tra

1. **File SPI cho `QaaLocaleNameProvider` tên gì?** `META-INF/services/java.util.spi.LocaleNameProvider`.
2. **Service descriptor chứa tên service hay implementation?** File name là service; file content là tên implementation.
3. **Chỉ JAR trên classpath thì Locale API dùng SPI trước không?** Không; mặc định CLDR, cần cấu hình thứ tự nếu muốn ưu tiên.
4. **`getDisplayLanguage("qaa", en-US)` gồm hai loại locale gì?** `qaa` là ngôn ngữ cần đặt tên; `en-US` là locale hiển thị.
5. **Vì sao `ServiceLoader` có thể báo true nhưng display name vẫn `qaa`?** Discovery thành công, nhưng API chưa chọn SPI làm nguồn dữ liệu.
6. **Nếu provider không có tên cho code đó, trả gì?** `null` để fallback.
7. **Cách đăng ký trong JPMS named module?** `provides java.util.spi.LocaleNameProvider with demo.spi.QaaLocaleNameProvider;`.
8. **Module consumer trực tiếp gọi `ServiceLoader` cần gì?** `uses` cho service đó.
9. **`--module-path` khác `--add-modules`?** Cái đầu cung cấp module candidates, cái sau yêu cầu resolve module đã nêu.
10. **Có cần `exports demo.spi;` trong provider module chỉ để ServiceLoader load không?** Không.
11. **Vì sao `System.setProperty("java.locale.providers", ...)` lúc runtime không đáng tin?** Thứ tự có thể đã bị JDK đọc/cached.
12. **JDK 23+ còn dùng `COMPAT` locale provider theo kiểu legacy không?** Không.
13. **`ServiceLoader.reload()` có đổi global preference của locale runtime không?** Không.
14. **`ResourceBundleProvider` có cùng cơ chế preference `java.locale.providers` với `LocaleNameProvider` không?** Không, đó là service có hợp đồng riêng.

## 14. Tài liệu API chính thức còn áp dụng

- [Java SE 25 — LocaleServiceProvider](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/spi/LocaleServiceProvider.html): packaging classpath/module, `getAvailableLocales` và thứ tự `SPI/CLDR/HOST`.
- [Java SE 25 — LocaleNameProvider](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/spi/LocaleNameProvider.html): display language, country, variant, script và fallback.
- [Java SE 25 — ServiceLoader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.html): service descriptor, `uses/provides`, provider loading và `reload`.
- [Java SE 25 — Locale](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Locale.html): `forLanguageTag` và display-name APIs.
- [Java SE 25 — java.text.spi](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/spi/package-summary.html): locale-sensitive formatter, Collator, BreakIterator providers.
- [Java SE 25 — java.util.spi](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/spi/package-summary.html): các locale service interfaces và phân biệt `ResourceBundleProvider`.
- [Oracle JDK 23 Release Notes — Removal of Legacy Locale Data](https://www.oracle.com/java/technologies/javase/23-relnote-issues.html): `JRE/COMPAT` đã bị loại bỏ.
- [JEP 252 — Use CLDR Locale Data by Default](https://openjdk.org/jeps/252): hướng chuyển sang CLDR và các lưu ý tương thích.

**Kết luận:** **Đăng ký** làm cho provider discoverable; **`java.locale.providers`** xác định độ ưu tiên nguồn dữ liệu; **hợp đồng SPI của từng method và `getAvailableLocales()`** quyết định provider có dữ liệu cho yêu cầu hay không. Kiểm thử cả classpath lẫn JPMS, so sánh direct `ServiceLoader` với kết quả Locale API thật, tránh các cấu hình locale legacy đã bị xóa.
# ResourceBundle.Control: ứng viên, định dạng và thời gian sống trong Java

## 1. ResourceBundle.Control điều khiển những gì?

Trong Java, `ResourceBundle` chọn bản dịch và tài nguyên theo `Locale`. Nếu ứng dụng có các tệp như:

~~~text
Messages.properties
Messages_fr.properties
Messages_fr_CA.properties
~~~

thì `ResourceBundle.getBundle("Messages", Locale.CANADA_FRENCH)` có thể tìm tài nguyên cho tiếng Pháp tại Canada và kế thừa các khóa từ tài nguyên tổng quát hơn.

`java.util.ResourceBundle.Control` là lớp lồng `ResourceBundle.Control`, cho phép thay đổi chính sách **tìm**, **chọn định dạng**, **tải**, **fallback** và **cache** của một bundle khi gọi overload `ResourceBundle.getBundle` có tham số `Control`.

Các câu hỏi chính:

1. **Ứng viên (candidate locales):** tìm `fr_CA`, `fr`, rồi root theo thứ tự nào?
2. **Định dạng (formats):** thử bundle dạng class `.class` trước hay dạng file `.properties` trước; có cho phép nguồn `.xml` không?
3. **Thời gian sống (TTL):** khi nào bundle trong cache phải được kiểm tra lại? Hết TTL có đồng nghĩa tải mới không?
4. **Fallback:** không tìm được candidate theo locale yêu cầu thì có thử default locale của JVM không?
5. **Tải lại (reload):** ai quyết định nguồn đã thay đổi và cần tạo instance mới?

**Giới hạn quan trọng ngay từ đầu:** `ResourceBundle.Control` được thiết kế cho ứng dụng chạy trên **classpath / unnamed module**. Khi code gọi overload `ResourceBundle.getBundle(..., Control)` **từ named module**, Java 9+ ném `UnsupportedOperationException`. Với ứng dụng Java Modules (JPMS), nên xem `java.util.spi.ResourceBundleProvider` và cơ chế provider thay vì xây giải pháp mới dựa trên `Control`.

Phần lớn ví dụ trong bài là **Java 17+ chạy trên classpath**, không có `module-info.java`. Đây là điều kiện cần để hiểu đúng hành vi và chạy các chương trình minh họa.

## 2. Bản đồ API ResourceBundle.Control

| Phương thức/hằng | Vai trò | Điều cần nhớ |
| --- | --- | --- |
| `getCandidateLocales(baseName, locale)` | Sinh danh sách locale ứng viên theo thứ tự ưu tiên | Danh sách càng đầu càng cụ thể; thường kết thúc bằng `Locale.ROOT` |
| `getFormats(baseName)` | Trả thứ tự định dạng bundle được phép tải | Mặc định class trước, properties sau |
| `getFallbackLocale(baseName, locale)` | Chọn một locale khác để tìm tiếp khi chưa có kết quả | Mặc định có thể dùng JVM default locale |
| `newBundle(baseName, locale, format, loader, reload)` | Tạo bundle cụ thể từ class/file hoặc nguồn tùy chỉnh | `reload` phản ánh nhánh tải lại |
| `getTimeToLive(baseName, locale)` | Quyết định TTL của cache theo millis hoặc hằng sentinel | Hết hạn thường dẫn đến `needsReload` |
| `needsReload(..., bundle, loadTime)` | Xác định bundle hết TTL có thật sự cần tải lại | Mặc định kiểm tra thời điểm sửa nguồn khi làm được |
| `toBundleName(baseName, locale)` | Đổi base name + locale thành tên bundle | Ví dụ `Messages_fr_CA` |
| `toResourceName(bundleName, suffix)` | Đổi tên bundle thành đường dẫn resource | Ví dụ `com/example/Messages_fr.properties` |
| `FORMAT_DEFAULT` | `["java.class","java.properties"]` | Thứ tự class → properties |
| `FORMAT_CLASS` | Chỉ `["java.class"]` | Bỏ qua file properties |
| `FORMAT_PROPERTIES` | Chỉ `["java.properties"]` | Bỏ qua class bundle |
| `TTL_DONT_CACHE` | Không đưa bundle vào cache | Không đồng nghĩa TTL bằng 0 |
| `TTL_NO_EXPIRATION_CONTROL` | Cache mà không có kiểm soát hết hạn | Giá trị mặc định của `getTimeToLive` |

Đối tượng `Control` hợp tác với `ResourceBundle.getBundle`, chứ không phải “bundle chứa key/value”. `Control` chủ yếu quyết định **cách tìm và cách sống của bundle**, còn bản dịch thực tế nằm trong `PropertyResourceBundle`, `ListResourceBundle` hoặc bundle tùy chỉnh.

## 3. getCandidateLocales: thứ tự từ cụ thể đến tổng quát

Với locale `fr-CA`, danh sách ứng viên mặc định thông thường là:

~~~text
fr-CA → fr → ROOT
~~~

Với base name `Messages`, tên các resource được suy ra:

~~~text
Messages_fr_CA.properties
Messages_fr.properties
Messages.properties
~~~

**Thứ tự candidate không phải thứ tự khóa được đọc:** bộ nạp trước tiên xác định các bundle có thể tồn tại, rồi xây chuỗi parent thích hợp. Khi gọi `getString(key)`, nếu khóa không có trong bundle cụ thể, nó có thể được tìm từ parent.

### Ví dụ 1 — In candidate locales và định dạng

Tạo `CandidatePolicyDemo.java`:

~~~java
import java.util.List;
import java.util.Locale;
import java.util.ResourceBundle;
import java.util.stream.Collectors;

public class CandidatePolicyDemo {
    static String describe(List<Locale> locales) {
        return locales.stream()
                .map(locale -> locale.equals(Locale.ROOT)
                        ? "ROOT" : locale.toLanguageTag())
                .collect(Collectors.joining(" -> "));
    }

    public static void main(String[] args) {
        ResourceBundle.Control control =
                ResourceBundle.Control.getControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES);

        Locale frenchCanada = Locale.forLanguageTag("fr-CA");
        Locale serbianLatin =
                Locale.forLanguageTag("sr-Latn-RS");

        System.out.println("Formats: "
                + control.getFormats("Messages"));
        System.out.println("fr-CA: " + describe(
                control.getCandidateLocales(
                        "Messages", frenchCanada)));
        System.out.println("sr-Latn-RS: " + describe(
                control.getCandidateLocales(
                        "Messages", serbianLatin)));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 CandidatePolicyDemo.java
java CandidatePolicyDemo
~~~

Đầu ra đã kiểm chứng trên JDK hiện đại:

~~~text
Formats: [java.properties]
fr-CA: fr-CA -> fr -> ROOT
sr-Latn-RS: sr-Latn-RS -> sr-Latn -> sr-RS -> sr -> ROOT
~~~

### Đọc kết quả

- `fr-CA`: thử vùng Canada trước, sau đó tiếng Pháp chung, cuối cùng bundle root.
- `sr-Latn-RS`: locale có **script Latin** và vùng Serbia nên Java có nhiều bước hơn. Đây là lý do không tự viết thuật toán bằng cách xóa phần cuối thẻ BCP 47 một cách ngây thơ.
- `Locale.ROOT` đại diện cho bundle không suffix: `Messages.properties`.
- Có các trường hợp đặc biệt trong Javadoc như tiếng Trung (`zh` với script `Hans`/`Hant` dựa trên vùng) và các mã ngôn ngữ lịch sử. **Không tự giả định mọi candidate chain luôn chỉ gồm language-country-root**.

Trong chương trình, `getControl(FORMAT_PROPERTIES)` chỉ chọn **định dạng properties**, không làm mất quy tắc sinh candidate locale mặc định.

## 4. Candidate chain khác fallback locale

Hai khái niệm rất dễ nhầm:

**Candidate chain** là chuỗi biến thể từ locale được yêu cầu, ví dụ:

~~~text
Yêu cầu: fr-CA
Candidates: fr-CA -> fr -> ROOT
~~~

**Fallback locale** là **một locale yêu cầu khác** mà `getBundle` có thể dùng để tìm tiếp khi các candidate liên quan không tạo được bundle kết quả theo điều kiện tìm kiếm; implementation mặc định thường thử default locale của JVM nếu khác locale vừa tìm.

Ví dụ giả định default locale của JVM là `en-US`:

~~~text
Yêu cầu: ja-JP
  candidates: ja-JP -> ja -> ROOT
Nếu không có bản dịch thích hợp theo nhánh yêu cầu,
  có thể tìm fallback locale en-US
  rồi candidates: en-US -> en -> ROOT
Sau cùng có thể dùng root nếu có
~~~

**Lưu ý về thuật toán chính xác:** root bundle có vai trò đặc biệt trong quá trình chọn kết quả; không nên diễn giải sơ đồ trên là một vòng lặp “luôn trả root ngay ở bước thứ ba rồi chắc chắn không thử default locale”. Javadoc `ResourceBundle.getBundle` có thuật toán tìm kiếm và lựa chọn root/default cụ thể. Sơ đồ nhằm phân biệt hai **nguồn ứng viên**, không mô tả mọi tình huống parent chain.

### getNoFallbackControl không có nghĩa không có parent

~~~java
ResourceBundle.Control control =
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);
~~~

Đây là **mảnh mã trong method**, cần import `java.util.ResourceBundle`.

`getNoFallbackControl` khiến `getFallbackLocale` trả `null`: không tự thử một locale fallback bổ sung như default locale. Nhưng danh sách **candidate theo locale gốc** vẫn có `fr-CA`, `fr` và `Locale.ROOT`. Do đó, parent/root của cùng chuỗi candidate **vẫn hoạt động**.

Điều này đặc biệt quan trọng khi kiểm thử: “không fallback” trong API ở đây không phải “chỉ được đọc chính xác một file `Messages_fr_CA.properties`”. Nếu muốn không có cả parent root, phải thiết kế candidate chain hoặc chính sách tra khóa khác, và hiểu nguy cơ làm mất tài nguyên tổng quát.

## 5. Ví dụ 2 — Nạp bundle và kế thừa khóa theo candidate

Tạo bốn tệp trong **cùng một thư mục classpath**, ví dụ thư mục `bundle-demo`:

~~~text
bundle-demo/
  BundleLookupDemo.java
  Messages.properties
  Messages_fr.properties
  Messages_fr_CA.properties
~~~

Nội dung `Messages.properties`:

~~~properties
app=Base app
origin=root
~~~

Nội dung `Messages_fr.properties`:

~~~properties
greeting=Bonjour
~~~

Nội dung `Messages_fr_CA.properties`:

~~~properties
region=CA
~~~

Tạo `BundleLookupDemo.java`:

~~~java
import java.util.Locale;
import java.util.ResourceBundle;

public class BundleLookupDemo {
    public static void main(String[] args) {
        Locale requested = Locale.CANADA_FRENCH;

        ResourceBundle.Control control =
                ResourceBundle.Control.getNoFallbackControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES);

        ResourceBundle bundle = ResourceBundle.getBundle(
                "Messages", requested, control);

        System.out.println("Resolved: "
                + bundle.getLocale().toLanguageTag());
        System.out.println("Region: "
                + bundle.getString("region"));
        System.out.println("Greeting: "
                + bundle.getString("greeting"));
        System.out.println("App: " + bundle.getString("app"));
        System.out.println("Fallback locale: "
                + control.getFallbackLocale("Messages", requested));
    }
}
~~~

Từ thư mục `bundle-demo`, biên dịch/chạy trên classpath:

~~~bash
javac -encoding UTF-8 BundleLookupDemo.java
java -cp . BundleLookupDemo
~~~

Kết quả:

~~~text
Resolved: fr-CA
Region: CA
Greeting: Bonjour
App: Base app
Fallback locale: null
~~~

### Phân tích parent chain

- `region` có trong `Messages_fr_CA.properties`.
- `greeting` không có ở mức `fr_CA` nhưng lấy từ `Messages_fr.properties`.
- `app` không có ở hai bundle trên nên lấy từ `Messages.properties`.
- `getFallbackLocale == null` không chặn **kế thừa khóa từ parent** trong cùng candidate chain.

Nếu file `Messages_fr_CA.properties` không tồn tại, kết quả có thể chọn `fr` làm locale của bundle; nếu khóa không có ở bất kỳ bundle/parent nào, `getString` ném `MissingResourceException`. Điều đó khác với trường hợp **không tìm được bundle nào** cho base name: `getBundle` có thể ném `MissingResourceException` từ bước nạp.

## 6. getFormats: class, properties và định dạng tùy chỉnh

Mặc định, `Control.FORMAT_DEFAULT` gồm:

~~~text
[java.class, java.properties]
~~~

Với mỗi candidate locale, Java có thể thử class-based resource trước, rồi properties. Các format có tên `java.class` và `java.properties` là định dạng được JDK định nghĩa, không phải tên extension file theo đúng nghĩa trong mọi tình huống.

| Cấu hình | Ý nghĩa |
| --- | --- |
| `FORMAT_DEFAULT` | Thử class `ListResourceBundle` trước, rồi `.properties` |
| `FORMAT_CLASS` | Chỉ bundle dạng class |
| `FORMAT_PROPERTIES` | Chỉ bundle dạng `.properties` |
| `getControl(FORMAT_PROPERTIES)` | Factory tạo Control sẵn có cho properties-only |
| Override `getFormats` | Cần khi định dạng khác, như `xml` |

Ví dụ:

~~~java
ResourceBundle.Control propertiesOnly =
        ResourceBundle.Control.getControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);

ResourceBundle bundle = ResourceBundle.getBundle(
        "Messages", Locale.FRENCH, propertiesOnly);
~~~

Đây là **mảnh mã trong method**, cần import `ResourceBundle` và `Locale`.

### Cảnh báo format order và cache

`ResourceBundle` có **cache**, vì vậy nếu lần đầu tìm cùng base name/class loader bằng control chỉ cho `java.class`, một lần gọi sau dùng control chỉ cho `java.properties` không được bảo đảm “tự quên” bundle class trước đó. Javadoc nhấn mạnh rằng **danh sách formats và candidates phải nhất quán giữa các lời gọi cho cùng base bundle** để tránh kết quả ngoài ý muốn.

Các giá trị trả từ `getFormats` phải không rỗng, không chứa các format chưa được xử lý và **không bị mutate sau khi trả về**. Các format tùy chỉnh không được dùng tiền tố `"java."`, vì phần đó được Java dành riêng.

### Định dạng tùy chỉnh phải có newBundle phù hợp

Chỉ viết:

~~~java
@Override
public List<String> getFormats(String baseName) {
    return List.of("xml");
}
~~~

là **mảnh mã trong subclass của Control**, không đủ để đọc XML. Bạn còn phải override `newBundle` để biết resource name, giải mã, parse file và tạo một `ResourceBundle`. Nếu không, implementation mặc định của `newBundle` có thể ném `IllegalArgumentException` khi gặp format lạ.

## 7. Ví dụ 3 — ResourceBundle từ XML bằng Control riêng

`java.util.Properties.loadFromXML(InputStream)` hỗ trợ format XML dành cho properties. Ví dụ này dùng nó làm nguồn dữ liệu rồi cung cấp một `ResourceBundle` với `handleGetObject` và `getKeys`.

Chuẩn bị:

~~~text
xml-demo/
  XmlControlDemo.java
  Messages.xml
~~~

Nội dung `Messages.xml` (UTF-8):

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE properties SYSTEM "http://java.sun.com/dtd/properties.dtd">
<properties>
    <entry key="hello">Hello XML</entry>
</properties>
~~~

Tạo `XmlControlDemo.java`:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.net.URLConnection;
import java.util.Collections;
import java.util.Enumeration;
import java.util.List;
import java.util.Locale;
import java.util.Properties;
import java.util.ResourceBundle;

public class XmlControlDemo {
    static class XmlControl extends ResourceBundle.Control {
        @Override
        public List<String> getFormats(String baseName) {
            return List.of("xml");
        }

        @Override
        public ResourceBundle newBundle(
                String baseName, Locale locale, String format,
                ClassLoader loader, boolean reload) throws IOException {

            if (!"xml".equals(format)) {
                return null;
            }

            String bundleName = toBundleName(baseName, locale);
            String path = toResourceName(bundleName, "xml");

            InputStream stream;
            if (reload) {
                URL url = loader.getResource(path);
                if (url == null) {
                    return null;
                }
                URLConnection connection = url.openConnection();
                connection.setUseCaches(false);
                stream = connection.getInputStream();
            } else {
                stream = loader.getResourceAsStream(path);
            }

            if (stream == null) {
                return null;
            }

            Properties properties = new Properties();
            try (stream) {
                properties.loadFromXML(stream);
            }

            return new ResourceBundle() {
                @Override
                protected Object handleGetObject(String key) {
                    return properties.getProperty(key);
                }

                @Override
                public Enumeration<String> getKeys() {
                    return Collections.enumeration(
                            properties.stringPropertyNames());
                }
            };
        }
    }

    public static void main(String[] args) {
        XmlControl control = new XmlControl();
        ResourceBundle bundle = ResourceBundle.getBundle(
                "Messages", Locale.US, control);

        System.out.println("Formats: "
                + control.getFormats("Messages"));
        System.out.println("Hello: "
                + bundle.getString("hello"));
    }
}
~~~

Biên dịch/chạy từ thư mục `xml-demo`:

~~~bash
javac -encoding UTF-8 XmlControlDemo.java
java -cp . XmlControlDemo
~~~

Kết quả đã kiểm tra:

~~~text
Formats: [xml]
Hello: Hello XML
~~~

### Tại sao ví dụ xử lý reload riêng?

Nếu `reload == true`, ví dụ dùng `ClassLoader.getResource` → `URLConnection`, sau đó `setUseCaches(false)` trước khi mở stream. Điều này giúp tránh **cache tầng URL/connection** khi `ResourceBundle` yêu cầu tải lại. Nếu chỉ gọi `getResourceAsStream` ở nhánh reload, một số provider/file system có thể trả dữ liệu đã cache ở tầng thấp hơn.

Đây là ví dụ **để học cơ chế**, chưa phải giải pháp reload XML production-ready cho mọi nguồn dữ liệu. Trong ứng dụng thực, phải kiểm tra:

- Chính sách bảo vệ tài nguyên không đáng tin, kích cỡ và giới hạn parse.
- Encoding/định dạng XML, lỗi I/O và quyền truy cập.
- Behavior của ClassLoader, JAR, URLConnection, cache bên ngoài.
- Phần mềm chạy trên **unnamed module**.
- Thread safety của `Control` khi chia sẻ giữa nhiều request.
- Việc nguồn cần được version/reload có thể phù hợp với hệ cấu hình riêng hơn là custom ResourceBundle.

Không dùng `Properties.load(InputStream)` để đọc XML. `loadFromXML` là API XML riêng, với đặc tả format properties XML.

## 8. TTL của ResourceBundle.Control là gì?

`ResourceBundle` cache bundle để tránh đọc tài nguyên lặp lại. `Control.getTimeToLive(baseName, locale)` quyết định **mức thời gian bundle đã nạp có thể ở cache mà chưa cần kiểm tra lại nguồn**.

Giá trị trả về:

| Giá trị TTL | Ý nghĩa | Hành vi |
| --- | --- | --- |
| `TTL_NO_EXPIRATION_CONTROL` (`-2`) | Không kiểm soát hết hạn | Mặc định; bundle có thể tiếp tục ở cache |
| `TTL_DONT_CACHE` (`-1`) | Không lưu bundle vào cache | Mỗi lần cần có thể phải nạp mới |
| `0` | Bundle hết TTL ngay, phải xét xác thực lại khi truy xuất cache | **Không tự bảo đảm reload** |
| `N > 0` | `N` millisecond có thể dùng cache trước khi kiểm tra | Khi hết hạn, gọi `needsReload` để quyết định |
| Âm khác hai sentinel | Giá trị không hợp lệ | Không trả các giá trị này |

**Không nhầm:** `getTimeToLive` không phải thời gian “sống tối đa của object Java” và không bắt buộc huỷ mọi reference đến bundle cũ. Nó chỉ điều khiển cách `ResourceBundle.getBundle` sử dụng cache và xác thực lại khi truy xuất.

Nếu một biến đã giữ `ResourceBundle old = ...`, thay đổi file resource và tải bundle mới **không** làm `old.getString(...)` tự chuyển sang dữ liệu mới. Bundle cũ vẫn là object được tham chiếu.

### TTL mặc định và giá trị mẫu

~~~java
ResourceBundle.Control control =
        ResourceBundle.Control.getControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);

long defaultTtl = control.getTimeToLive(
        "Messages", Locale.FRENCH);
// TTL_NO_EXPIRATION_CONTROL

long neverCache = ResourceBundle.Control.TTL_DONT_CACHE;
// -1

long noExpiration =
        ResourceBundle.Control.TTL_NO_EXPIRATION_CONTROL;
// -2
~~~

Đây là **mảnh mã trong method**, cần import `java.util.ResourceBundle` và `java.util.Locale`.

Ngay cả `TTL_NO_EXPIRATION_CONTROL` cũng **không bảo đảm cache tồn tại vĩnh viễn trong bộ nhớ**: implementation có thể loại entry do điều kiện bộ nhớ/cache. “Không hết hạn theo TTL” khác “không bao giờ bị loại”.

## 9. needsReload: hết TTL là kiểm tra, không mặc nhiên đọc lại

Khi một cache entry đã quá TTL, cơ chế mặc định của `ResourceBundle.getBundle` thường hỏi:

~~~java
boolean changed = control.needsReload(
        baseName, locale, format, loader, bundle, loadTime);
~~~

Đây là **mảnh mã mô tả chữ ký**; các biến được cung cấp trong callback, không phải lời gọi ứng dụng thông thường.

- Nếu `needsReload(...)` trả **true**, entry cũ có thể bị loại và bundle mới được tải.
- Nếu trả **false**, entry được giữ và thời gian kiểm tra TTL được cập nhật theo chính sách.
- Implementation mặc định cố kiểm tra **thời điểm sửa của tài nguyên nguồn** so với thời gian load. Với URL/JAR/resource loader tùy chỉnh, metadata cập nhật không phải lúc nào cũng đủ đáng tin để phát hiện mọi thay đổi.

Vì vậy, dùng TTL `0` mà không hiểu `needsReload` có thể khiến lập trình viên nghĩ file luôn được nạp lại. Thực tế, mặc định `needsReload` có thể trả false nếu thời điểm sửa không thay đổi hoặc không được phát hiện.

### Callback phải sử dụng thông tin nhất quán

`needsReload` nhận `format`, `locale`, `loader`, `bundle` và `loadTime`. Khi custom `newBundle`, bạn phải bảo đảm đường dẫn nguồn và cách kiểm tra thay đổi phù hợp; nếu `newBundle` đọc từ API HTTP hoặc database nhưng `needsReload` vẫn chỉ kiểm tra last-modified của một file giả định, TTL có thể không phản ánh dữ liệu thật.

Để demo cơ chế rõ ràng, phần tiếp theo làm một `Control` chủ động trả `true` khi đến bước kiểm tra TTL, rồi đếm số lần tải.

## 10. Ví dụ 4 — TTL 0 và needsReload bằng một bundle trong bộ nhớ

Ví dụ này không cần file resource, giúp loại ảnh hưởng của đồng hồ file system, cache JAR và thời điểm sửa resource. Đối tượng `Control` tạo `ListResourceBundle` mới trong `newBundle`, đồng thời đếm số lượt tải.

Tạo `TtlReloadDemo.java`:

~~~java
import java.util.List;
import java.util.ListResourceBundle;
import java.util.Locale;
import java.util.ResourceBundle;

public class TtlReloadDemo {
    static class CountingControl extends ResourceBundle.Control {
        private int loads;
        private int checks;

        @Override
        public List<String> getFormats(String baseName) {
            return FORMAT_PROPERTIES;
        }

        @Override
        public List<Locale> getCandidateLocales(
                String baseName, Locale locale) {
            return locale.equals(Locale.ROOT)
                    ? List.of(Locale.ROOT)
                    : List.of(locale, Locale.ROOT);
        }

        @Override
        public Locale getFallbackLocale(
                String baseName, Locale locale) {
            return null;
        }

        @Override
        public long getTimeToLive(
                String baseName, Locale locale) {
            return 0;
        }

        @Override
        public boolean needsReload(
                String baseName, Locale locale, String format,
                ClassLoader loader, ResourceBundle bundle,
                long loadTime) {
            checks++;
            return true;
        }

        @Override
        public ResourceBundle newBundle(
                String baseName, Locale locale, String format,
                ClassLoader loader, boolean reload) {
            if (!locale.equals(Locale.ENGLISH)) {
                return null;
            }

            int version = ++loads;
            return new ListResourceBundle() {
                @Override
                protected Object[][] getContents() {
                    return new Object[][] {
                            {"version", Integer.toString(version)}
                    };
                }
            };
        }
    }

    public static void main(String[] args) {
        CountingControl control = new CountingControl();
        ClassLoader loader =
                TtlReloadDemo.class.getClassLoader();

        ResourceBundle first = ResourceBundle.getBundle(
                "VirtualDemoBundle", Locale.ENGLISH, loader, control);
        ResourceBundle second = ResourceBundle.getBundle(
                "VirtualDemoBundle", Locale.ENGLISH, loader, control);

        System.out.println("First: "
                + first.getString("version"));
        System.out.println("Second: "
                + second.getString("version"));
        System.out.println("Same object: " + (first == second));
        System.out.println("Loads: " + control.loads);
        System.out.println("Reload checks: " + control.checks);
    }
}
~~~

Biên dịch và chạy trên classpath:

~~~bash
javac -encoding UTF-8 TtlReloadDemo.java
java -cp . TtlReloadDemo
~~~

Kết quả đã kiểm tra:

~~~text
First: 1
Second: 2
Same object: false
Loads: 2
Reload checks: 1
~~~

### Giải thích từng bước

1. Lần gọi đầu nạp bundle `en`, biến `loads` tăng lên `1`. Không có file ngoài vì `newBundle` tự tạo bundle.
2. `getTimeToLive == 0` khiến instance đã cache hết hạn ngay ở thời điểm truy xuất tiếp.
3. Lần gọi sau kiểm tra cache, `needsReload(...)` trả `true`, nên `newBundle` tạo một instance khác với `version = 2`.
4. Kết quả `first == second` bằng false, nhưng đối tượng `first` vẫn tồn tại và còn chứa giá trị `1`.
5. `Reload checks == 1` chứng minh **bước kiểm tra** đã chạy trong kịch bản.

**Không suy rằng TTL 0 luôn cho cùng kết quả này.** Nếu `needsReload` trả false, bộ nạp có thể tiếp tục dùng instance cũ. `TTL_DONT_CACHE` lại là một chính sách **khác**: không lưu entry vào cache ngay từ đầu.

Ví dụ này chạy theo hành vi của JDK thông dụng trên unnamed module; trong ứng dụng có concurrent calls hoặc nhiều class loader, số callback/timing có thể khác. Không dùng bộ đếm mutable chưa đồng bộ của ví dụ làm Control toàn cục trong server. Với production, cần thread-safety rõ.

## 11. TTL_DONT_CACHE khác TTL = 0 như thế nào?

### TTL_DONT_CACHE

`TTL_DONT_CACHE` cho biết bundle mới **không được thêm vào cache**. Vì vậy khi tìm cùng một bundle lần sau, runtime không có cache entry của lần trước để hỏi `needsReload` theo nhánh expired.

Thích hợp trong một số trường hợp:

- Tài nguyên rất nhỏ và phải nạp lại thường xuyên.
- Test muốn tránh cache gây tác động đến kịch bản.
- Thử nghiệm một nguồn bundle thay đổi nhanh.

Nhược điểm: có thể làm tăng I/O, tạo nhiều object, thậm chí lặp lại **tra cứu không tồn tại**. Không dùng cho mọi bundle chỉ vì muốn code “luôn mới” mà chưa đo hiệu năng.

### TTL = 0

`0` cho phép cache nhưng bắt buộc **kiểm tra điều kiện reload** mỗi lần truy xuất cache. Tính mới phụ thuộc `needsReload`. Có thể ít tải dữ liệu lại hơn `TTL_DONT_CACHE` nếu nguồn không đổi, nhưng tốn chi phí kiểm tra.

### TTL > 0

Một TTL dương như `5_000L` có nghĩa tối đa khoảng 5 giây cache có thể được dùng **không cần kiểm tra nguồn** trong điều kiện cache còn tồn tại. Khi hết hạn, mới xét reload.

Đây **không phải cam kết độ trễ cập nhật tối đa 5 giây tuyệt đối** cho toàn hệ thống: các tầng cache khác, reference cũ, tính khả dụng của nguồn, sự chậm trễ tại file system hay deployment đều có thể ảnh hưởng dữ liệu người dùng thấy.

### TTL_NO_EXPIRATION_CONTROL

Đây là mặc định `-2`. Bundle cache không có vòng kiểm tra hết hạn của Control. Một bundle đã nạp có thể vẫn được dùng sau khi file thay đổi cho đến khi cache bị loại, `clearCache`, môi trường reload class loader, hoặc cơ chế khác làm nạp lại.

## 12. clearCache: xoá cache không sửa nội dung bundle cũ

Java hỗ trợ:

~~~java
ResourceBundle.clearCache();
~~~

và:

~~~java
ResourceBundle.clearCache(loader);
~~~

Đây là **các mảnh mã minh họa trong method**; bản thứ hai cần biến `loader` kiểu `ClassLoader`.

- `clearCache()` xóa cache thuộc phạm vi class loader được API xác định đối với caller.
- `clearCache(ClassLoader)` xóa cache gắn với class loader chỉ định.
- Cache scope và lookup trong môi trường class loader/container/module phức tạp cần xem tài liệu overload đang gọi.
- Xóa cache không làm mọi biến `ResourceBundle` đã trao cho mã khác tự đổi nội dung.
- Nếu nguồn file/JAR/resource bị cache ở tầng khác, xóa cache `ResourceBundle` chưa chắc đủ để thấy byte mới.

**Đừng gọi `clearCache()` liên tục trong request production để “ép cập nhật”** nếu chỉ muốn kiểm soát TTL. Việc xóa cache rộng có thể ảnh hưởng hiệu năng hoặc các bundle khác cùng class loader. Hãy định nghĩa policy cho đúng nguồn, chọn TTL/needsReload phù hợp và quản lý version/deployment khi cần.

### Negative caching

Lookup không có bundle cho một locale cũng có thể được cache (dưới dạng kết quả không tìm thấy) để tránh tra cứu lặp. Điều này quan trọng khi bạn **thêm file mới** trong runtime: không chỉ entry bundle cũ, mà cả cache của việc “không tìm thấy” có thể làm cho việc hiển thị cập nhật chậm. Cần cân nhắc TTL, clearCache đúng scope và class loader.

## 13. getCandidateLocales tùy chỉnh: không thay theo cảm tính

Bạn có thể override để thay thứ tự/loại locale ứng viên:

~~~java
@Override
public List<Locale> getCandidateLocales(
        String baseName, Locale locale) {
    if (locale.equals(Locale.ROOT)) {
        return List.of(Locale.ROOT);
    }
    return super.getCandidateLocales(baseName, locale);
}
~~~

Đây là **mảnh mã trong subclass của `ResourceBundle.Control`**, cần import `java.util.List` và `java.util.Locale`.

Ví dụ này giữ behavior mặc định nhưng nhắc rằng **Locale.ROOT phải được xử lý đúng**. Nếu muốn dùng chuỗi ứng viên theo thiết kế riêng, cần:

- Trả danh sách locale **không null**, không chứa phần tử null.
- Duy trì thứ tự cụ thể → tổng quát theo yêu cầu nghiệp vụ.
- Quyết định có cần `Locale.ROOT` ở cuối chuỗi parent không.
- Không thay đổi danh sách đã trả trong lúc `getBundle` xử lý.
- Bảo đảm getFormats/getCandidateLocales **nhất quán giữa các lần gọi** cho cùng base bundle, đặc biệt khi có cache.
- Tránh chuỗi fallback lặp vô hạn hoặc candidate không tạo ra được tên resource như dự kiến.
- Kiểm tra các locale có script và biến thể đặc biệt, đừng áp logic “chỉ cắt country” cho mọi thẻ.

### Không thay candidate để giải quyết thiếu translation key

Nếu `Messages_fr_CA.properties` không có một key nhưng `Messages_fr.properties` có, parent chain đã cung cấp hành vi kế thừa hữu ích. Đừng bỏ `fr` hoặc ROOT khỏi candidate chỉ vì muốn “bản dịch Canada độc lập”, trừ khi product chủ đích không cho fallback key và chấp nhận ném lỗi hoặc có chính sách khác.

## 14. getFallbackLocale tùy chỉnh và sai lầm phổ biến

Mặc định, Control có thể trả default locale của JVM khi target locale khác default locale. Trong ứng dụng server nhiều người dùng, default locale thường là cấu hình server, **không phải ngôn ngữ người xem**. Điều này có thể làm kết quả bất ngờ khi thiếu bản dịch.

Một cách ngăn fallback **sang default locale**:

~~~java
ResourceBundle.Control noDefaultFallback =
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);
~~~

Nếu cần chính sách cụ thể hơn, có thể override:

~~~java
@Override
public Locale getFallbackLocale(
        String baseName, Locale target) {
    return null;
}
~~~

Đây là **mảnh mã trong subclass của `Control`**, cần import `java.util.Locale`.

**Phân biệt lần nữa:**

- `getFallbackLocale() == null`: không tìm thêm một locale fallback khác.
- `getCandidateLocales()` vẫn có thể sinh các locale cha và `ROOT`.
- `getString(key)` vẫn có thể kế thừa giá trị từ **parent bundle**.
- Khi không có bundle nào cho base name, `getBundle` vẫn có thể ném `MissingResourceException`.

Nếu ứng dụng cần ngôn ngữ mặc định business là tiếng Anh, hãy quản lý chính sách ngôn ngữ ở tầng gọi hoặc provider một cách rõ ràng, thay vì trông đợi default locale JVM là bất biến trên mọi máy.

## 15. ResourceBundle.Control và Java Modules (JPMS)

Đây là giới hạn rất quan trọng trong Java 9+:

**`ResourceBundle.Control` không được hỗ trợ khi gọi overload có Control từ code trong named module.** Việc gọi:

~~~java
ResourceBundle.getBundle(
        "Messages", requestedLocale, customControl);
~~~

từ một **named module** sẽ ném `UnsupportedOperationException` theo Javadoc. Việc thêm `requires java.base` hoặc sửa classpath một cách máy móc không phải là giải pháp hỗ trợ đầy đủ.

### Hướng phù hợp khi dùng named modules

Dùng cơ chế `java.util.spi.ResourceBundleProvider`, với quy ước provider theo base name và các khai báo module `uses`/`provides` theo tài liệu, để hỗ trợ bundle trong module khác và định dạng không tiêu chuẩn.

Khái quát:

~~~text
Classpath / unnamed module:
  ResourceBundle.getBundle(baseName, locale, Control)
  -> được hỗ trợ

Named module:
  ResourceBundle.getBundle(...) theo cơ chế module/provider
  -> dùng ResourceBundleProvider khi cần mở rộng
  -> overload nhận Control không được hỗ trợ
~~~

`ResourceBundleControlProvider` là một SPI khác có thể tác động Control trong trường hợp phù hợp, nhưng **bị bỏ qua trong named modules**. Đừng nhầm nó với `ResourceBundleProvider` dùng cho cơ chế module.

Không cố viết một demo named-module dùng `Control` rồi coi `UnsupportedOperationException` là “thiếu quyền module”. Đây là một hạn chế API có chủ đích.

## 16. Cache, class loader, nhiều luồng và triển khai thực tế

Trong server, một số yếu tố có thể khiến quan sát cache khác với bài tập console:

**Class loader.** Cùng base name nhưng class loader khác nhau có thể nhận bộ resource khác hoặc cache scope khác. Với application server hoặc plugin system, cần hiểu class loader đang tải bundles.

**Caller module.** Trong JPMS, các overload khác nhau có đường tìm kiếm khác nhau. Không áp dụng suy luận về `Control` của classpath cho mọi named module.

**Consistency.** Không trả `getFormats` hoặc `getCandidateLocales` phụ thuộc ngẫu nhiên vào trạng thái request, thời gian hoặc user hiện tại rồi dùng chung base name và cache. Javadoc cảnh báo kết quả có thể không như mong đợi.

**Thread safety.** `ResourceBundle.getBundle` không đồng bộ hóa việc gọi callback của `Control` tùy chỉnh. Vì thế nếu Control được chia sẻ giữa nhiều luồng, các hàm `getFormats`, `getCandidateLocales`, `newBundle`, `needsReload`, `getTimeToLive` phải an toàn khi gọi song song. Ví dụ `TtlReloadDemo` dùng biến đếm mutable chỉ để học và chạy đơn luồng.

**Chi phí tải.** Cấu hình TTL quá ngắn và reload source qua network có thể làm tăng latency hoặc tải hệ thống. Với tài nguyên deployed cùng JAR và chỉ đổi mỗi release, để cache mặc định và thay class loader/restart khi release có thể đơn giản, ổn định hơn.

**Nguồn được version.** Nếu cần cập nhật bản dịch live từ database/remote config, hãy xác định version, ETag, lastModified, invalidate cache và quan hệ consistency. `Control` là cơ chế mở rộng resource lookup, **không tự giải quyết toàn bộ distributed cache**.

## 17. Xử lý lỗi và kiểm thử

| Tình huống | Biểu hiện | Cách kiểm tra |
| --- | --- | --- |
| Base name sai | `MissingResourceException` khi getBundle | Kiểm tra package, resource path, classpath |
| Thiếu key | `MissingResourceException` từ getString | Kiểm tra khóa trong parent chain |
| Thử `FORMAT_CLASS` khi chỉ có .properties | Không tìm file cần thiết | Chọn `FORMAT_PROPERTIES` |
| Đổi formats giữa các lần gọi | Cache có thể giữ instance kiểu cũ | Duy trì policy nhất quán, kiểm thử cache scope |
| `getCandidateLocales` trả null | Vi phạm hợp đồng Control | Trả danh sách hợp lệ |
| `getFormats` trả danh sách rỗng | Vi phạm hợp đồng Control | Có ít nhất một format hợp lệ |
| Khai báo format tùy chỉnh nhưng không override `newBundle` | `IllegalArgumentException`/không tải được | Cung cấp loader cho format mới |
| Không hiểu fallback locale và parent | Thấy resource root dù đã “tắt fallback” | Phân biệt getFallbackLocale với candidate chain |
| TTL=0 nhưng file không reload | `needsReload` trả false hoặc metadata không cho thấy thay đổi | Kiểm tra callback và nguồn dữ liệu |
| Dùng `TTL_DONT_CACHE` cho mọi bundle | Nhiều I/O, lookup lặp, chậm | Đo chi phí, chọn TTL hợp lý |
| Reload nguồn trong JAR không nhận bản cập nhật | URL/ClassLoader hoặc cache tầng thấp | Kiểm tra class loader, connection cache, deployment |
| Giữ reference bundle cũ | Giá trị không thay đổi dù lần getBundle mới | Lấy instance mới ở điểm thích hợp |
| Dùng Control trong named module | `UnsupportedOperationException` | Chuyển sang `ResourceBundleProvider` |
| Code custom Control không thread-safe | Race condition khi server nhiều luồng | Control bất biến hoặc đồng bộ thích hợp |
| Tệp properties UTF-8 sai byte | Bundle không nạp đúng Unicode | Kiểm tra Java 9+ PropertyResourceBundle và charset |

### Checklist QA trước khi dùng production

1. Xác định ứng dụng dùng **classpath/unnamed module** hay **named module**.
2. Xác định base name, package và class loader dùng thực tế.
3. Kiểm thử candidate locale có language/country/script, gồm `Locale.ROOT`.
4. Kiểm thử thứ tự `FORMAT_DEFAULT`, `FORMAT_CLASS`, `FORMAT_PROPERTIES`.
5. Kiểm thử getNoFallbackControl **vẫn cho phép parent root**.
6. Kiểm thử key lấy từ bundle cụ thể và key lấy từ parent.
7. Nếu dùng custom format, kiểm tra `newBundle` ở cả `reload=false` và `reload=true`.
8. Nếu TTL dương hoặc 0, kiểm tra thời điểm gọi `needsReload` và dữ liệu có thật sự thay đổi.
9. Kiểm tra `clearCache` không thay đổi reference đã giữ.
10. Kiểm thử cache khi tài nguyên không tồn tại rồi được bổ sung.
11. Kiểm thử nhiều luồng và các class loader khác nhau nếu ứng dụng có tính chất đó.
12. Đối chiếu hành vi với Oracle Javadoc trên JDK đang triển khai, không chỉ dựa trên một bài viết cũ.

## 18. Bài tập thực hành

1. Với `fr-CA`, hãy dùng `getCandidateLocales` in chain. Giải thích vì sao `Messages.properties` có thể là parent của `Messages_fr.properties`.
2. Với `sr-Latn-RS`, giải thích vì sao danh sách có cả `sr-Latn` và `sr-RS` trước `sr`.
3. Tạo ba file `Messages.properties`, `Messages_fr.properties` và `Messages_fr_CA.properties`. Cho mỗi file chứa một key riêng, kiểm tra `getString` lấy đúng parent.
4. Dùng `getNoFallbackControl(FORMAT_PROPERTIES)` và thay đổi default locale của JVM trong test riêng. Vì sao `Messages.properties` vẫn có thể được đọc?
5. Tạo class bundle và properties bundle có cùng tên. Khi dùng `FORMAT_DEFAULT`, điều gì quyết định ưu tiên? Dùng `FORMAT_PROPERTIES` có giải quyết nhu cầu của bạn không?
6. Thay đổi ví dụ XML để dùng `Messages_fr.xml` và `Messages.xml`. Kiểm tra parent chain và giải thích vai trò `toBundleName`/`toResourceName`.
7. Trong `TtlReloadDemo`, thay `getTimeToLive` từ `0` thành `TTL_DONT_CACHE`. Quan sát số lần gọi `needsReload` và `newBundle`.
8. Trong `TtlReloadDemo`, giữ TTL=0 nhưng trả `false` từ `needsReload`. Giải thích vì sao lần gọi thứ hai không nhất thiết tạo version mới.
9. Khi một file properties thay đổi lúc runtime, tại sao `ResourceBundle.clearCache()` có thể chưa đủ nếu ClassLoader/URL cache đang giữ dữ liệu?
10. Vì sao `ResourceBundle.Control` không phù hợp khi code gọi overload có Control từ named module? Hướng mở rộng nào thay thế?
11. Thiết kế một chính sách reload bản dịch từ database: xác định version, TTL, needsReload, thread-safety và hành vi khi nguồn tạm thời không khả dụng.
12. Viết test bảo đảm các gọi `getBundle` khác nhau cho cùng base name sử dụng format/candidate policy nhất quán.

**Ghi nhớ:** `ResourceBundle.Control` quyết định **ứng viên locale**, **định dạng bundle**, **fallback locale** và **TTL/cache/reload** trong các ứng dụng classpath. `getCandidateLocales` tạo chain từ cụ thể tới tổng quát; `getFormats` quyết định class/properties/custom format; `getFallbackLocale` khác **kế thừa khóa qua parent**. `TTL_DONT_CACHE` là không cache, `TTL_NO_EXPIRATION_CONTROL` là cache không hết hạn theo TTL, còn TTL 0/dương chỉ dẫn đến kiểm tra `needsReload` khi entry hết hạn. Với **named modules**, không dùng overload `getBundle(..., Control)`; xem `ResourceBundleProvider`. Đừng tự thay đổi policy tùy request hoặc bỏ qua cache/class loader khi kiểm thử.

### Tài liệu tham khảo

- [Java SE 17 — ResourceBundle.Control](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.Control.html) — `getCandidateLocales`, `getFormats`, `getFallbackLocale`, `getTimeToLive`, `needsReload`, `newBundle` và cache.
- [Java SE 17 — ResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html) — thuật toán tìm bundle, parent, cache, clearCache, classloader và module.
- [Java SE 17 — ResourceBundleProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/ResourceBundleProvider.html) — SPI thay thế cho mở rộng trong named modules.
- [Java SE 17 — PropertyResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PropertyResourceBundle.html) — bundle từ file properties và encoding.
- [Java SE 17 — Properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Properties.html) — `loadFromXML` dùng trong ví dụ định dạng XML.
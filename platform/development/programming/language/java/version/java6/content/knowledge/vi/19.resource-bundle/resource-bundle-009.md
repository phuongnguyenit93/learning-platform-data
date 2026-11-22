# Kiểm thử thiếu bundle, fallback và thay đổi tài nguyên trong ResourceBundle

## 1. Mục tiêu của bài học

Một ứng dụng Java dùng `java.util.ResourceBundle` thường hoạt động đúng trong môi trường phát triển vì các file `Messages.properties` đã có sẵn. Nhưng khi phát hành sang server, đóng gói JAR/module, đổi locale hoặc cập nhật bản dịch lúc đang chạy, những lỗi khó thấy có thể xuất hiện:

- Không tìm thấy **toàn bộ bundle family** do sai tên, sai classpath hoặc thiếu tài nguyên đã đóng gói.
- Có bundle nhưng **thiếu một key** ở locale và tất cả parent bundles.
- Yêu cầu locale `fr-CA` nhưng thực tế được chọn `fr` hoặc locale mặc định `en`; nội dung không đúng như sản phẩm dự kiến.
- Bundle đã tải được giữ trong **cache**, nên sửa file trên đĩa không khiến lần gọi `getBundle(...)` kế tiếp tự thấy bản dịch mới.
- Bổ sung file cho một locale từng thiếu nhưng chương trình vẫn nhìn thấy root/fallback cũ do cache.
- Gọi `ResourceBundle.clearCache(...)` rồi tưởng mọi object `ResourceBundle` cũ đang được ứng dụng giữ tham chiếu đã tự thay giá trị.

Bài này đi từ **thiết kế test cases**, **dùng `MissingResourceException`**, **xác minh thứ tự fallback** đến **kiểm thử thay đổi tài nguyên và cache**. Ví dụ sử dụng **Java 17+**, chỉ có API Java SE vẫn áp dụng hiện nay, tạo tài nguyên thử nghiệm trong **thư mục tạm** và dọn dẹp sau khi chạy.

Bốn câu hỏi cần kiểm chứng riêng biệt:

1. **Có bundle không?** `ResourceBundle.getBundle(...)` có trả một object hay ném `MissingResourceException`?
2. **Bundle nào được chọn?** `bundle.getLocale()` trả locale thực tế nào?
3. **Key lấy từ đâu?** `bundle.getString(key)` có lấy từ bundle hiện tại/parent chain hay ném exception?
4. **Khi file thay đổi, bao giờ nhìn thấy bản mới?** Lệnh `getBundle(...)` có trả instance đã cache, instance tải lại hay một object cũ mà code vẫn giữ?

Các khía cạnh này độc lập; một test chỉ kiểm tra “không ném exception” là chưa đủ để chứng minh fallback đúng.

## 2. Mô hình tìm bundle và tra key

Một family `Messages` có thể có:

~~~text
Messages.properties             root bundle (Locale.ROOT)
Messages_en.properties          tiếng Anh chung
Messages_fr.properties          tiếng Pháp chung
Messages_fr_CA.properties       tiếng Pháp tại Canada
~~~

Giả sử JVM default là `en-US`. Khi gọi:

~~~java
ResourceBundle bundle = ResourceBundle.getBundle(
        "Messages", Locale.CANADA_FRENCH);
~~~

Đây là **snippet bên trong chương trình** với các import `java.util.ResourceBundle` và `java.util.Locale`.

Java thực hiện tìm bundle theo các candidate locales của requested locale. Nếu có `Messages_fr_CA`, bundle ấy được chọn và có thể nối parent theo hướng:

~~~text
Messages_fr_CA
       |
       v
Messages_fr
       |
       v
Messages (root)
~~~

Nếu một key không có ở `fr-CA`, `getString(...)` tìm qua `fr` rồi root. **Không tự nhảy sang `Messages_en`** chỉ vì JVM default là tiếng Anh.

Ngược lại, nếu requested locale là `de-DE` và hoàn toàn không có localized bundle tiếng Đức, cơ chế tìm bundle mặc định có thể thử **JVM default locale `en-US`** trước khi dùng root. Khi có `Messages_en.properties`, kết quả có thể là bundle `en`.

Sơ đồ tách hai kiểu fallback:

~~~text
A. Chọn bundle:
 requested locale: de-DE
       |
       +--> de-DE? không
       +--> de?    không
       +--> root?  có, giữ làm dự phòng
       +--> JVM default en-US?
                    |
                    +--> en-US? không
                    +--> en?    có --> chọn en

B. Tra key SAU khi đã chọn bundle fr-CA:
  getString("title")
       |
       +--> fr-CA có key?  không
       +--> fr có key?     không
       +--> root có key?   không
       +--> MissingResourceException
  (KHÔNG tìm tiếp trong en)
~~~

**Phải kiểm thử cả fallback lúc chọn bundle và fallback theo key.** Một kết quả `bundle.getLocale() == fr-CA` chỉ cho biết **bundle được chọn**, không có nghĩa mọi key lấy trực tiếp từ file `Messages_fr_CA.properties`.

## 3. Kiểu lỗi cần phân loại

| Tình huống | Lời gọi có thể lỗi | Kết quả/ngoại lệ |
| --- | --- | --- |
| Sai base name hoặc không có bundle phù hợp | `ResourceBundle.getBundle("AbsentMessages", ...)` | `MissingResourceException` |
| Family tồn tại nhưng thiếu key trong tất cả parent | `bundle.getString("unknown.key")` | `MissingResourceException` |
| Locale vùng thiếu nhưng bản ngôn ngữ chung có | `getBundle("Messages", Locale.CANADA_FRENCH)` | Có thể chọn `fr`, **không phải lỗi** |
| Không có localized bundle của target, có default locale bundle | `getBundle("Messages", Locale.GERMANY)` | Có thể chọn `en` khi default là `en-US` |
| Không có target, tắt fallback sang default nhưng có root | `getBundle(..., getNoFallbackControl(...))` | Chọn root bundle |
| Cùng tên key tồn tại ở child và parent | `bundle.getString("greeting")` | Giá trị ở child được ưu tiên |
| File property thay đổi khi bundle vẫn cache | `getBundle(...)` lần kế tiếp | Có thể vẫn nhận giá trị cũ |
| File mới bổ sung cho locale từng thiếu | `getBundle(...)` lần kế tiếp | Có thể vẫn nhận kết quả fallback cache trước đó |
| Cache đã xóa, nhưng giữ reference bundle cũ | `oldBundle.getString("key")` | Object cũ **không tự cập nhật** |

`MissingResourceException` có thể xuất hiện ở **hai giai đoạn** khác nhau. Trong test, nên tách khối `getBundle(...)` khỏi `getString(...)` để biết lỗi do không tìm được family hay do thiếu key.

Ví dụ xử lý lỗi một key tùy chọn:

~~~java
static String getOrMissing(ResourceBundle bundle, String key) {
    try {
        return bundle.getString(key);
    } catch (MissingResourceException e) {
        return "<missing>";
    }
}
~~~

Đây là **snippet thuộc một class** với import `java.util.ResourceBundle` và `MissingResourceException`; nó không thay đổi chính sách của Java. Chuỗi `<missing>` là **placeholder do ứng dụng lựa chọn**, không phải giá trị mặc định của `ResourceBundle`.

Với key **bắt buộc** (ví dụ thông báo lỗi bảo mật hoặc nhãn thiết yếu), thường nên để test thất bại khi thiếu key, thay vì nuốt lỗi và trả chuỗi rỗng.

## 4. Xác định chính xác kết quả mong đợi của fallback

Một test tốt phải biết **resource files nào được cung cấp** và **JVM default locale nào được dùng**.

Với dữ liệu:

~~~properties
# Messages.properties (root)
greeting=Root hello
shared=Root shared
~~~

~~~properties
# Messages_fr.properties
greeting=Bonjour
~~~

~~~properties
# Messages_fr_CA.properties
region=Quebec
~~~

~~~properties
# Messages_en.properties
greeting=Hello
only_en=English only
~~~

Các assertion quan trọng là:

| Requested locale | Điều kiện | Expected `getLocale()` | Expected lookup |
| --- | --- | --- | --- |
| `fr-CA` | Có `fr-CA` và `fr` | `fr-CA` | `region=Quebec` từ child |
| `fr-CA` | Key `greeting` không có ở child | `fr-CA` | `Bonjour` từ parent `fr` |
| `fr-CA` | Key `shared` chỉ có ở root | `fr-CA` | `Root shared` từ root |
| `fr-CA` | `only_en` chỉ có trong `en` | `fr-CA` | **Thiếu key**, dù JVM default `en-US` |
| `fr-FR` | Không có `fr-FR`, có `fr` | `fr` | `Bonjour` |
| `de-DE` | Không có `de`, default `en-US` | `en` với lookup mặc định | `Hello` |
| `de-DE` | Không có `de`, tắt fallback sang default | `Locale.ROOT` | `Root hello` |
| `es-ES` | Chưa có `es`, tắt default fallback | `Locale.ROOT` | Root bundle |
| `es-ES` | Vừa bổ sung `Messages_es` và reload | `es` | `Hola` |

Các cặp kết quả nên được kiểm tra bằng **`getLocale()` và `getString(key)`**, không chỉ bằng tên file mà developer dự đoán compiler sẽ chọn.

### 4.1. `Locale.ROOT` khác `Locale.ENGLISH`

`Messages.properties` là **root bundle**, ứng với `Locale.ROOT`; `Messages_en.properties` ứng với `en`. Hai bundle này có thể tồn tại độc lập, có giá trị khác nhau và được chọn ở những giai đoạn khác nhau.

Nếu product baseline là tiếng Anh, có thể đưa giá trị tiếng Anh đầy đủ vào root và để các bundle locale-specific override. Nhưng **root không tự đồng nghĩa tiếng Anh** — đó là quyết định nội dung do team sản phẩm đưa ra.

### 4.2. Hiểu đúng `getNoFallbackControl`

Trên **classpath/unnamed module**, ta có thể tạo:

~~~java
ResourceBundle.Control noDefault =
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);

ResourceBundle result = ResourceBundle.getBundle(
        "Messages", Locale.GERMANY, loader, noDefault);
~~~

Đây là **snippet** với `loader` đã cấu hình để tìm `Messages*.properties`.

Control này **ngăn bước thử JVM default locale** khi target không có localized bundle. Nó **không** tắt các candidate `de-DE → de → root` và không tắt parent-chain lookup. Trong bộ test trên, nếu không có tiếng Đức nhưng có root, nó chọn root.

**Giới hạn quan trọng:** Các overload `ResourceBundle.getBundle(...)` nhận `ResourceBundle.Control` không được hỗ trợ khi caller nằm trong **named module**; Java ném `UnsupportedOperationException`. Với JPMS, dùng `getBundle(...)` theo module, `ResourceBundleProvider` và chính sách fallback ở tầng ứng dụng. Demo bên dưới chạy trên **classpath** để chủ ý kiểm thử Control.

## 5. Cache: vì sao sửa file không đồng nghĩa reload?

`ResourceBundle.getBundle(...)` **cache kết quả theo cơ chế của Java**, dựa trên thông tin như base name, locale và class loader/module context. Default `ResourceBundle.Control` sử dụng `TTL_NO_EXPIRATION_CONTROL`: nếu một bundle đã nằm trong cache theo đường tải tương ứng và chưa bị thu hồi/xóa, việc gọi lại thường dùng instance cũ mà không chủ động kiểm tra file vừa thay đổi.

Điều này áp dụng cả:

- **Bundle tồn tại:** đổi `LiveMessages.properties` từ `message=v1` sang `message=v2` nhưng lookup có thể tiếp tục nhận `v1`.
- **Bundle chưa tồn tại:** nếu `Messages_es.properties` chưa có, loader có thể cache một **kết quả vắng mặt (negative lookup)** hoặc kết quả fallback root. Tạo file `Messages_es.properties` rồi gọi lại có thể vẫn chưa nhìn thấy tiếng Tây Ban Nha.

Hành vi của demo được kiểm chứng thực tế:

~~~text
Before file edit: v1
After edit, cached: v1
After clearCache: v2
Old reference: v1
Before adding es: root
After adding es, cached: root
After adding es, refreshed: es
es greeting: Hola
~~~

Đừng diễn giải rằng cache làm *mọi* thay đổi file bị giữ vô hạn trong mọi hoàn cảnh: class loader, reference reachability, TTL và quy tắc reload có thể khác nhau. Bài test này **cố định trường hợp phổ biến**: cùng loader, property bundles trên file URL, default cache, không sử dụng TTL reload tự động.

### 5.1. `ResourceBundle.clearCache(ClassLoader)`

API:

~~~java
ResourceBundle.clearCache(loader);
~~~

xóa các mục cache của `ResourceBundle` liên quan đến class loader chỉ định. Lần `getBundle(...)` tiếp theo **có cơ hội tải lại** từ tài nguyên hiện tại.

**Không nhầm với việc sửa mọi object đã được trả về trước đó.**

~~~text
ResourceBundle old = getBundle(...)   -> old.message = v1

Sửa file LiveMessages.properties     -> file.message = v2

getBundle(...) trước clearCache      -> cached.message = v1

clearCache(loader)

ResourceBundle fresh = getBundle(...) -> fresh.message = v2

old.getString("message")              -> v1 (vẫn là object cũ)
~~~

Một dịch vụ muốn hot reload **phải thay reference đang dùng**, ví dụ cập nhật snapshot/supplier lưu bundle mới theo một cơ chế thread-safe, thay vì chỉ xóa cache.

### 5.2. `clearCache()` không tham số

`ResourceBundle.clearCache()` có phạm vi cache gắn với **caller module** theo JavaDoc hiện hành; nó không phải một lệnh đảm bảo “xóa mọi bundle trong mọi module và class loader của toàn JVM”.

Trong test có custom `URLClassLoader`, dùng **`clearCache(loader)`** để xóa đúng các bundle được tải bởi loader đó. Dùng phương thức này giúp test không đụng vào resource bundles không liên quan của những thành phần khác trong tiến trình.

### 5.3. TTL và chiến lược reload tự động

`ResourceBundle.Control` trên classpath/unnamed module cho phép thiết kế cách cache hoạt động bằng:

- `getTimeToLive(baseName, locale)`: giá trị TTL cho bundle trong cache.
- `needsReload(baseName, locale, format, loader, bundle, loadTime)`: quyết định có reload khi mục cache đã hết TTL.
- `TTL_NO_EXPIRATION_CONTROL`: không tự hết hạn do TTL theo chế độ mặc định.
- `TTL_DONT_CACHE`: không giữ instance trong cache theo cách thông thường.

Điểm tinh tế: **hết TTL không tự khẳng định file đã thay đổi**; `needsReload(...)` được tham vấn theo hợp đồng khi mục cache hết hạn. Không nên dùng TTL cực thấp hoặc `TTL_DONT_CACHE` trong production chỉ để tránh thiết kế một cơ chế cập nhật tài nguyên rõ ràng, vì có thể phát sinh overhead I/O.

Khi resource nằm trong JAR/module hoặc được đóng gói bất biến, cách an toàn thường là **redeploy/version lại artifact**. Sửa trực tiếp JAR đang được sử dụng và gọi `clearCache` không phải một giao thức hot reload đáng tin cậy, nhất là khi class loader và URL connection còn có cache riêng.

## 6. Phân lập test để không phụ thuộc máy phát triển

Các test `ResourceBundle` dễ bị “xanh giả” hoặc “đỏ giả” vì đang đọc từ classpath/module path của máy chạy CI thay vì file fixture mong đợi.

Nguyên tắc:

1. **Tạo bộ fixture riêng** trong thư mục tạm có quyền đọc/ghi. Không sửa file bundle thật của ứng dụng đang chạy.
2. **Sử dụng base name riêng hoặc class loader riêng** để hạn chế cache và trùng tên với resource khác.
3. Dùng `URLClassLoader` trỏ tới fixture và truyền thẳng loader vào `getBundle(...)`. Trong test minh họa, parent loader là `null` để không vô tình lấy `Messages.properties` từ classpath ứng dụng.
4. **Thiết lập default locale có kiểm soát** nếu test phụ thuộc vào fallback sang default; lưu giá trị cũ và restore bằng `finally`.
5. **Không cho các test thay `Locale.setDefault(...)` chạy song song không phối hợp**, vì default locale là trạng thái toàn JVM.
6. Phân tách các case có và không có `Control`: để tránh cache lookup trước ảnh hưởng case sau, xóa cache cho loader trước khi thay đổi chiến lược fallback.
7. Khi thay file, kiểm tra trực tiếp kỳ vọng “cũ trước clearCache, mới sau clearCache” thay vì giả định hệ điều hành tự báo thay đổi cho `ResourceBundle`.
8. Đóng `URLClassLoader` sau test, xóa thư mục tạm và restore global state. Trên Windows, file có thể khó xóa nếu JAR/loader vẫn đang mở, vì vậy thứ tự đóng loader trước cleanup rất quan trọng.

Một test integration chạy qua classpath thực của artifact cũng cần thiết, nhưng **test phân lập bằng folder riêng** giúp xác định lỗi trong quy tắc fallback mà không bị can thiệp bởi resource do thư viện khác cung cấp.

## 7. Ví dụ Java 17+ hoàn chỉnh: tạo resource, kiểm thử lỗi/fallback/cache và dọn dẹp

Ví dụ **`BundleTestingDemo.java`** dưới đây có đầy đủ `main`. Nó tự tạo các file `Messages*.properties` và `LiveMessages.properties` trong một thư mục tạm, sau đó dùng `URLClassLoader` để đọc mà không yêu cầu người học chuẩn bị thêm các tệp nguồn.

Những việc sẽ được kiểm chứng trong một lần chạy:

- `fr-CA` lấy key từ ba cấp `fr-CA`, `fr` và root.
- Key `only_en` có trong tiếng Anh **không** xuất hiện ở nhánh `fr-CA`.
- `de-DE` fallback tới JVM default `en-US` và chọn `en` với lookup mặc định.
- `de-DE` chọn root với `getNoFallbackControl(...)`.
- Base name không tồn tại bị nhận diện bằng `MissingResourceException`.
- Key không tồn tại bị nhận diện bằng `MissingResourceException`.
- Sửa `LiveMessages.properties` vẫn nhận bản cũ trước `clearCache(loader)`.
- Sau xóa cache, bundle tải mới nhận `v2`; reference cũ vẫn giữ `v1`.
- Bổ sung `Messages_es.properties` sau lần lookup thất bại vẫn thấy root cho tới khi clear cache, sau đó chọn `es` và thông điệp `Hola`.

### 7.1. Toàn bộ source của `BundleTestingDemo.java`

~~~java
import java.io.IOException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.Locale;
import java.util.MissingResourceException;
import java.util.ResourceBundle;
import java.util.stream.Stream;

public class BundleTestingDemo {
    private static final ResourceBundle.Control NO_DEFAULT =
            ResourceBundle.Control.getNoFallbackControl(
                    ResourceBundle.Control.FORMAT_PROPERTIES);

    private static void write(Path folder, String file, String contents)
            throws IOException {
        Files.writeString(folder.resolve(file), contents, StandardCharsets.UTF_8);
    }

    private static String label(Locale locale) {
        return Locale.ROOT.equals(locale) ? "root" : locale.toLanguageTag();
    }

    private static String getOrMissing(ResourceBundle bundle, String key) {
        try {
            return bundle.getString(key);
        } catch (MissingResourceException e) {
            return "<missing>";
        }
    }

    public static void main(String[] args) throws Exception {
        Locale previous = Locale.getDefault();
        Path folder = Files.createTempDirectory("resource-bundle-demo-");
        try {
            write(folder, "Messages.properties",
                    "greeting=Root hello\nshared=Root shared\n");
            write(folder, "Messages_fr.properties", "greeting=Bonjour\n");
            write(folder, "Messages_fr_CA.properties", "region=Quebec\n");
            write(folder, "Messages_en.properties",
                    "greeting=Hello\nonly_en=English only\n");
            write(folder, "LiveMessages.properties", "message=v1\n");

            try (URLClassLoader loader = new URLClassLoader(
                    new URL[] {folder.toUri().toURL()}, null)) {
                Locale.setDefault(Locale.US);

                ResourceBundle french = ResourceBundle.getBundle(
                        "Messages", Locale.CANADA_FRENCH, loader, NO_DEFAULT);
                System.out.println("fr-CA selected: "
                        + label(french.getLocale()));
                System.out.println("fr-CA region: "
                        + french.getString("region"));
                System.out.println("fr-CA greeting: "
                        + french.getString("greeting"));
                System.out.println("fr-CA shared: "
                        + french.getString("shared"));
                System.out.println("fr-CA only_en: "
                        + getOrMissing(french, "only_en"));

                ResourceBundle germanDefault = ResourceBundle.getBundle(
                        "Messages", Locale.GERMANY, loader);
                System.out.println("de-DE default fallback: "
                        + label(germanDefault.getLocale()));

                ResourceBundle.clearCache(loader);
                ResourceBundle germanStrict = ResourceBundle.getBundle(
                        "Messages", Locale.GERMANY, loader, NO_DEFAULT);
                System.out.println("de-DE no default fallback: "
                        + label(germanStrict.getLocale()));

                try {
                    ResourceBundle.getBundle(
                            "AbsentMessages", Locale.ROOT, loader, NO_DEFAULT);
                    throw new AssertionError("Missing base unexpectedly loaded");
                } catch (MissingResourceException e) {
                    System.out.println("Missing bundle: detected");
                }
                System.out.println("Missing key: "
                        + getOrMissing(french, "does_not_exist"));

                ResourceBundle old = ResourceBundle.getBundle(
                        "LiveMessages", Locale.ROOT, loader, NO_DEFAULT);
                System.out.println("Before file edit: "
                        + old.getString("message"));

                write(folder, "LiveMessages.properties", "message=v2\n");
                ResourceBundle cached = ResourceBundle.getBundle(
                        "LiveMessages", Locale.ROOT, loader, NO_DEFAULT);
                System.out.println("After edit, cached: "
                        + cached.getString("message"));

                ResourceBundle.clearCache(loader);
                ResourceBundle refreshed = ResourceBundle.getBundle(
                        "LiveMessages", Locale.ROOT, loader, NO_DEFAULT);
                System.out.println("After clearCache: "
                        + refreshed.getString("message"));
                System.out.println("Old reference: "
                        + old.getString("message"));

                Locale spanish = Locale.forLanguageTag("es-ES");
                ResourceBundle missingSpanish = ResourceBundle.getBundle(
                        "Messages", spanish, loader, NO_DEFAULT);
                System.out.println("Before adding es: "
                        + label(missingSpanish.getLocale()));

                write(folder, "Messages_es.properties", "greeting=Hola\n");
                ResourceBundle stillCached = ResourceBundle.getBundle(
                        "Messages", spanish, loader, NO_DEFAULT);
                System.out.println("After adding es, cached: "
                        + label(stillCached.getLocale()));

                ResourceBundle.clearCache(loader);
                ResourceBundle nowSpanish = ResourceBundle.getBundle(
                        "Messages", spanish, loader, NO_DEFAULT);
                System.out.println("After adding es, refreshed: "
                        + label(nowSpanish.getLocale()));
                System.out.println("es greeting: "
                        + nowSpanish.getString("greeting"));
            }
        } finally {
            Locale.setDefault(previous);
            try (Stream<Path> paths = Files.walk(folder)) {
                for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }
}
~~~

**Lưu ý về thiết kế chương trình:**

- `write(...)` dùng `Files.writeString` với `UTF-8`. Mỗi lần ghi lại một tên file cụ thể, nội dung file được thay bằng phiên bản mới theo hành vi mặc định của API.
- `URLClassLoader` dùng folder URL riêng cho fixture. Parent là `null`, tránh tìm thấy file `Messages*.properties` tình cờ có trên classpath của ứng dụng mẫu.
- `Locale.setDefault(Locale.US)` chỉ để khiến test fallback `de-DE` có kết quả ổn định; `finally` restore locale cũ. **Đừng dùng kỹ thuật thay default toàn JVM cho từng request trong server nhiều người dùng.**
- `ResourceBundle.clearCache(loader)` giữa hai test `de-DE` khiến test default-control và no-default-control không ảnh hưởng nhau qua cache.
- `getOrMissing(...)` cho phép demo tiếp tục chạy sau test một key thiếu; với key bắt buộc, một test thực tế nên assert rằng exception được ném.
- Thư mục tạm được xóa bằng `Files.walk(...)` sau khi `URLClassLoader` đã đóng; stream cũng được đóng bởi `try-with-resources`.
- `Comparator.reverseOrder()` bảo đảm các file con được xóa trước thư mục cha.
- Không ghi đè resource thật nào của dự án và không thay đổi classpath của JVM đang chạy ngoài custom loader được tạo.
- Code sử dụng `Stream.toList()`, `Files.writeString` và `Locale.forLanguageTag`, tất cả đều chạy được với `--release 17`.

### 7.2. Biên dịch và chạy

Lưu chính xác nội dung trên thành file `BundleTestingDemo.java` rồi chạy trong thư mục chứa file:

~~~sh
javac --release 17 BundleTestingDemo.java
java BundleTestingDemo
~~~

**Stdout chính xác** (đã biên dịch bằng JDK 24 với `--release 17` và chạy thành công):

~~~text
fr-CA selected: fr-CA
fr-CA region: Quebec
fr-CA greeting: Bonjour
fr-CA shared: Root shared
fr-CA only_en: <missing>
de-DE default fallback: en
de-DE no default fallback: root
Missing bundle: detected
Missing key: <missing>
Before file edit: v1
After edit, cached: v1
After clearCache: v2
Old reference: v1
Before adding es: root
After adding es, cached: root
After adding es, refreshed: es
es greeting: Hola
~~~

**Những gì kết quả chứng minh:**

- Các dòng `fr-CA` cho thấy parent-chain fallback theo key diễn ra đúng; `only_en` vẫn thiếu vì tiếng Anh không nằm trong parent chain.
- Dòng `de-DE default fallback: en` là **fallback khi chọn bundle** sang JVM default locale.
- Dòng `de-DE no default fallback: root` cho thấy Control thay đổi chính sách fallback sang default nhưng **không** loại bỏ root.
- Hai dòng `Missing...` phân biệt **missing bundle family** với **missing key**.
- Dòng `After edit, cached: v1` cho thấy sửa file không tự invalidate cache trong fixture.
- Dòng `After clearCache: v2` chứng minh lookup mới có thể lấy nội dung file cập nhật.
- Dòng `Old reference: v1` chứng minh xóa cache **không mutate object cũ**.
- Những dòng `es` cho thấy một locale trước đây chưa có file vẫn có thể bị “kẹt” ở kết quả fallback cache cho đến khi cache được làm mới.

**Phạm vi xác minh:** ví dụ dùng property files trên URL dạng file trong thư mục tạm, classpath/unnamed module và `ResourceBundle.Control`. Đừng suy diễn mọi bộ đóng gói JAR/module hoặc mọi custom provider có cùng cơ chế cập nhật khi file trên đĩa bị thay trực tiếp.

## 8. Thiết kế các automated tests chuyên biệt

Trong bộ test thật, nên chia nhóm để khi thất bại biết rõ nguyên nhân.

### 8.1. Missing bundle test

**Given:** một base name chưa từng tồn tại trong fixture, ví dụ `AbsentMessages`, và không có root/candidate bundle nào.

**When:** gọi `ResourceBundle.getBundle("AbsentMessages", Locale.ROOT, loader, NO_DEFAULT)`.

**Then:** kỳ vọng **`MissingResourceException`**.

Không viết test chỉ kiểm tra returned value là `null`: `getBundle(...)` không dùng `null` làm kết quả “không tìm thấy” ở trường hợp này.

Khi dùng JUnit 5, cách assert tương ứng là `assertThrows(MissingResourceException.class, () -> ResourceBundle.getBundle(...))`, nhưng muốn chạy snippet đó phải có JUnit dependency. Ví dụ chính không cần thư viện test bên ngoài và thực hiện kiểm tra bằng `try/catch`.

### 8.2. Missing key test

**Given:** family `Messages` có thể tải thành công nhưng key `does_not_exist` không có ở bundle hiện tại hoặc tất cả parent.

**When:** `french.getString("does_not_exist")`.

**Then:** ném `MissingResourceException`.

Một test riêng cần bảo đảm **bundle không bị thiếu** để có thể kết luận lỗi này đến từ key lookup. Không nên bắt cùng một exception rồi gắn nhãn sai nguyên nhân.

### 8.3. Fallback locale test

**Given:** default locale `en-US`, chỉ có `Messages_en.properties` và root cho các ngôn ngữ liên quan, không có bản tiếng Đức.

**When:** `getBundle("Messages", Locale.GERMANY, loader)`.

**Then:** với chính fixture này, `getLocale()` là `en`.

Thêm case thứ hai có no-default Control: `getLocale()` là `Locale.ROOT`. Nếu test chỉ kiểm tra `getString("greeting")` mà root/en tình cờ có cùng message, nó sẽ **bỏ sót lỗi chọn nhầm bundle**; do đó phải assert cả locale thực tế.

### 8.4. Parent key test

**Given:** `fr-CA` chứa `region`, `fr` chứa `greeting` và root chứa `shared`.

**Then:** lần lượt nhận `Quebec`, `Bonjour` và `Root shared`. Đồng thời xác nhận key `only_en` vẫn missing ngay cả khi default locale là tiếng Anh.

Nhóm này đặc biệt quan trọng để phát hiện lỗi logic “key thiếu → dùng default locale” do team tự viết ngoài `ResourceBundle`.

### 8.5. Cached file-change test

**Given:** tải `LiveMessages.properties` phiên bản `v1` rồi sửa file thành `v2`.

**When:** gọi `getBundle(...)` lại với **cùng base name, loader và Control** trước khi xóa cache.

**Then:** fixture demo cho kết quả `v1`.

Sau `ResourceBundle.clearCache(loader)` và gọi lại, **expect `v2`**. Đồng thời giữ một reference đến bundle cũ và xác minh reference ấy vẫn trả `v1`.

Với ứng dụng hot reload thật, test nên thêm case thay reference đang dùng: nếu ứng dụng chỉ clear cache mà một service giữ `static final ResourceBundle` cũ, thì message vẫn không đổi.

### 8.6. Added-resource test

**Given:** `es-ES` ban đầu không có localized bundle, với no-default Control nên root được chọn.

**When:** tạo file `Messages_es.properties` sau lần lookup đầu.

**Then:** trước clearCache, fixture cho kết quả root cũ; sau clearCache, lookup mới chọn `es`, value `Hola`.

Một số lỗi i18n chỉ xuất hiện khi **thêm locale mới ở deployment**. Test này cho thấy có khác biệt giữa “đã tạo file” và “cache/loader thực sự nhìn thấy file mới”.

## 9. Tính độc lập và thứ tự chạy test

### 9.1. Tránh test dùng chung trạng thái global

`Locale.setDefault(...)` làm thay đổi trạng thái chung của **toàn JVM**, không phải chỉ thread hiện tại. Một integration test thay default locale trong khi test khác chạy song song có thể làm hành vi fallback của test kia thay đổi.

Vì vậy:

- Nếu cần sửa default locale trong test, ghi lại `Locale previous = Locale.getDefault()` và restore trong `finally`.
- Không cho những test phụ thuộc default locale chạy song song trừ khi có cơ chế đồng bộ tại mức toàn process/test suite.
- Khi có thể, truyền requested locale trực tiếp vào `getBundle(...)` và dùng no-default policy phù hợp với sản phẩm để giảm phụ thuộc môi trường.
- Đối với CI nhiều worker, mỗi test process nên có tài nguyên riêng. Tránh dùng chung một thư mục fixture và sửa file của nhau.

### 9.2. Tách test theo base name hoặc class loader

Vì `ResourceBundle` có cache, hai test gọi cùng base name và loader có thể ảnh hưởng nhau. Những chiến lược phù hợp:

- Tạo **URLClassLoader mới cho mỗi nhóm test**, đóng sau khi hoàn thành.
- Dùng base name riêng cho từng fixture (`Messages`, `LiveMessages`...).
- Gọi `ResourceBundle.clearCache(loader)` đúng thời điểm trong test cần thay đổi nội dung.
- Không dựa vào thứ tự chạy test của framework. Nếu một test cần được thiết lập trước, hãy **tạo fixture trong setup của chính test**, không “ăn theo” side effect của test khác.

Lưu ý rằng instance `ResourceBundle` đã tạo trước vẫn có thể được caller giữ; dùng loader mới không xóa object cũ khỏi biến trong code. Cả loader và bundle references phải có ownership/lifecycle rõ ràng.

### 9.3. Assert dữ liệu, không dựa vào lời mô tả console

Với bài tập, stdout của demo giúp quan sát trực tiếp. Trong automated test, nên assert rõ:

~~~java
if (!"Bonjour".equals(french.getString("greeting"))) {
    throw new AssertionError("Wrong parent fallback");
}
~~~

Đây là **snippet bên trong `main` của demo** sau khi biến `french` đã được khởi tạo; không phải một chương trình độc lập. Test nên fail nhanh, có thông báo gắn với hành vi đang kiểm chứng.

Với nguồn dịch lớn, thiết kế thêm một bước **coverage audit**: liệt kê key của root baseline, kiểm tra các locale có file được đóng gói, phát hiện key sai chính tả hoặc key mồ côi, và phân biệt “giá trị lấy từ bản dịch trực tiếp” với “giá trị được thừa kế”.

`bundle.containsKey(key)` và `bundle.keySet()` có thể bao gồm **inherited keys**, vì thế chúng **không đủ** để xác nhận mỗi locale đã dịch trực tiếp 100% key.

## 10. Kiểm thử thay đổi tài nguyên khi triển khai thật

### 10.1. File-based local development

Khi resource bundle nằm ở thư mục classpath và ứng dụng được thiết kế hot reload, ta có thể xây một service quản lý:

1. Phát hiện thay đổi resource qua build/redeploy signal hoặc một cơ chế watch do ứng dụng sở hữu.
2. Kiểm tra file mới hợp lệ, encoding đúng, key bắt buộc đầy đủ.
3. Invalidate cache **đúng class loader** hoặc tạo loader/version mới theo thiết kế.
4. Lấy bundle mới qua `getBundle(...)`.
5. Chuyển **reference/snapshot** của service sang bundle mới một cách thread-safe.
6. Giữ bản cũ cho những request đang xử lý nếu cần consistency, rồi giải phóng tham chiếu khi chúng hoàn tất.

Đừng chỉ gọi `clearCache(loader)` rồi dừng ở bước 3. Nếu một handler đã lưu `ResourceBundle` vào field, nó có thể tiếp tục trả text cũ đến khi field được cập nhật.

### 10.2. JAR hoặc immutable artifact

Trong nhiều ứng dụng production, file `.properties` nằm **bên trong JAR/WAR hoặc module image**. Chỉnh sửa trực tiếp archive đang được JVM sử dụng thường không phải cách cập nhật đáng tin cậy, và một số kết quả còn chịu cache của loader/JAR URL connection.

Phương án đơn giản, dễ kiểm thử:

- Đóng gói bundle vào một artifact versioned.
- Trong CI, chạy fallback tests và kiểm tra resource packaging.
- Triển khai artifact mới, restart/redeploy hoặc tạo class loader/module layer mới phù hợp.
- Xác nhận những instance mới nhìn thấy key và locale mới.
- Không giả định `clearCache` có thể giúp JVM “nhìn xuyên” vào một JAR đã được thay thế trên đĩa.

### 10.3. Named modules (JPMS)

Các overload nhận `ResourceBundle.Control`, như `getBundle(baseName, locale, loader, control)`, ném `UnsupportedOperationException` khi được gọi từ **named module**. Demo sử dụng classpath/unnamed module nên hợp lệ.

Trong named modules:

- Sử dụng các overload `getBundle(...)` hỗ trợ module, đặc biệt `getBundle(baseName, locale, module)` khi muốn chỉ định module.
- Tìm hiểu `ResourceBundleProvider` hoặc service provider và quy tắc tài nguyên được đóng gói/encapsulated trong module.
- Test cụ thể khả năng nhìn thấy resource qua module boundaries, không chỉ qua custom URLClassLoader.
- Nếu cần chính sách fallback nghiệp vụ khác mặc định, triển khai ở service/application layer thay vì copy nguyên mẫu `Control` của classpath.

Module-aware loading có quy tắc cache, visibility và provider riêng; một test classpath thành công **không chứng minh** đóng gói modular cũng đúng.

## 11. Kiểm tra resource packaging, encoding và tên file

Một file tồn tại trong repository chưa có nghĩa nó được đóng vào bản deploy. Tình huống thường gặp:

- `src/main/resources/Messages_fr.properties` có ở project nhưng không xuất hiện trong JAR sau build.
- Code gọi `getBundle("com.example.Messages")` trong khi file nằm ở package/path khác.
- Tên `Messages_fr_CA.properties` bị viết sai chữ hoa/thường hoặc viết dấu gạch nối `fr-CA` thay cho quy ước bundle suffix tương ứng.
- Build process lọc resource và vô tình thay charset hoặc nội dung `\\uXXXX`.
- Chỉ có `Messages_en.properties`, nhưng team tưởng root bundle đã chứa đầy đủ key cho mọi ngôn ngữ.
- Named module không cấp quyền/visibility cần thiết cho package chứa resource.

Test packaging tối thiểu nên:

1. Kiểm tra artifact/JAR có các file expected đúng path.
2. Đọc resource từ **artifact đã build**, không chỉ từ `src/main/resources` trong IDE.
3. Assert key bắt buộc, các dấu tiếng Việt và ký tự đặc biệt không bị mojibake.
4. Assert fallback với ít nhất hai locale: một đã hỗ trợ đầy đủ và một chưa có bản dịch.
5. Assert `bundle.getLocale()` và nội dung key, không chỉ kiểm tra `getBundle(...)` không ném exception.

Trên Java 17+, `PropertyResourceBundle` đọc `.properties` theo UTF-8 mặc định (với hành vi decoding compatibility theo JavaDoc). Đừng nhầm điều đó với tất cả overload của `java.util.Properties.load(...)` có cùng encoding; các API có quy tắc riêng.

## 12. Thiếu key khi không muốn fallback: thiết kế fail-fast

Một ứng dụng không phải lúc nào cũng muốn fallback im lặng. Ví dụ một hệ thống quản trị bản dịch có thể yêu cầu mọi locale đã “published” phải hoàn chỉnh.

### 12.1. Chặn locale không hỗ trợ

Trước khi gọi `ResourceBundle.getBundle(...)`, product có thể có danh sách:

~~~text
supportedLocales = [en, fr, fr-CA, vi]
requested = de-DE
selectedByProduct = en
~~~

Đây là **dữ liệu minh họa**, không phải hành vi tự động của `ResourceBundle`. Product tự quyết định `de-DE` không được hỗ trợ và chọn `en`; thay vì phụ thuộc JVM default trên từng server, nó truyền explicit locale cho lookup.

Nhưng nếu ngôn ngữ `fr-CA` tồn tại mà thiếu key, `getBundle` không tự động nói “locale không hoàn chỉnh”. Cần có coverage audit hoặc chính sách lookup nghiêm ngặt.

### 12.2. Chặn key thiếu

Một cách đơn giản ở tầng application:

~~~java
static String required(ResourceBundle bundle, String key) {
    return bundle.getString(key); // ném MissingResourceException nếu không có
}
~~~

Đây là **snippet trong class**, không cần bắt lỗi nếu policy yêu cầu fail-fast. Với optional key, có thể trả placeholder sau khi catch `MissingResourceException` như demo. Với localization QA, nên phân biệt optional và required keys bằng metadata/schema của sản phẩm.

Nếu cần biết một key có được dịch **trực tiếp** ở locale cụ thể hay không, `containsKey(...)` và `keySet()` trên final bundle có thể bị parent chain che khuất. Cần audit file/nguồn translation tương ứng, không dựa vào chúng để đếm coverage.

### 12.3. Fallback mặc định không phải security policy

Không lấy locale của request như căn cứ cấp quyền hoặc xác thực. `ResourceBundle` dùng để chọn nội dung hiển thị; nếu có một thông báo lỗi ở locale khác, quyền truy cập của user không được thay đổi.

Đối với dữ liệu do bên ngoài cung cấp, nên chọn **từ danh sách locales được hỗ trợ** thay vì tự ghép một đường dẫn file không được kiểm soát từ input. Base name/resource loading có ngữ nghĩa riêng; giới hạn miền dữ liệu giúp giảm lỗi đóng gói và hành vi không mong muốn.

## 13. Quản lý trạng thái khi reload nhiều thread

Một server có thể cùng lúc có:

- Thread A đang dùng `ResourceBundle old` với `message=v1`.
- Thread B phát hiện tài nguyên mới, gọi `clearCache(loader)` và lấy `ResourceBundle fresh` với `message=v2`.
- Thread C vẫn giữ một bản tham chiếu cũ từ request trước.

**Clear cache không đồng nghĩa mọi thread chuyển sang cùng message version.** Nếu sản phẩm yêu cầu nhất quán, dùng một tầng `MessageCatalog` hoặc snapshot immutable có version:

~~~text
MessageCatalog current -> snapshot v1

Tải và validate snapshot v2
          |
          v
AtomicReference.set(snapshot v2)

Request mới -> v2
Request đang xử lý -> giữ v1 đến khi hoàn tất
~~~

Đây là **sơ đồ thiết kế**, không phải API tự sinh của `ResourceBundle`. Không nhất thiết mọi ứng dụng đều cần hot reload; với bản dịch nằm trong JAR bất biến, deploy/restart thường đơn giản hơn.

Nếu dùng in-memory cache cho các `ResourceBundle` của nhiều locale, nhớ tính đến:

- Resource cache của JVM **và** cache của ứng dụng là hai tầng khác nhau.
- Một `clearCache(loader)` không tự xóa entry trong `Map<Locale,ResourceBundle>` do chính ứng dụng nắm.
- Cache của JSP/UI framework, template compiler, search index hoặc CDN có thể có lifecycle khác.
- Khi thêm một locale, các negative lookup cache cũng có thể phải được invalidated/reindexed.
- Luồng reload nên kiểm tra completeness trước khi publish snapshot mới, tránh để người dùng thấy bundle bị cập nhật một nửa.

## 14. Danh sách test cases tối thiểu cho CI

| Test | Fixture / điều kiện | Assertion |
| --- | --- | --- |
| Bundle family absent | `AbsentMessages` không có file | `getBundle` ném `MissingResourceException` |
| Key absent | `does_not_exist` không có ở child/parent | `getString` ném `MissingResourceException` |
| Locale cụ thể | `fr-CA` có riêng file | `getLocale() == fr-CA` |
| Fallback sang language | `fr-FR` không có, `fr` có | `getLocale() == fr` |
| Child key override | `fr-CA` có `region` | `region=Quebec` |
| Parent key fallback | `fr-CA` không có `greeting`, `fr` có | `greeting=Bonjour` |
| Root key fallback | `shared` chỉ ở root | `shared=Root shared` |
| Không crossover key | `only_en` chỉ ở `en` | `fr-CA` **không** tự lấy key từ `en` |
| Default-locale fallback | `de-DE` vắng, default `en-US` | lookup mặc định chọn `en` |
| No-default fallback | Cùng dữ liệu, `NO_DEFAULT` | chọn root |
| Modify file | `LiveMessages` v1 rồi viết v2 | trước clear cache vẫn có thể đọc v1 |
| Refresh cache | `clearCache(loader)` rồi tải lại | bundle mới đọc v2 |
| Old reference | giữ object v1 từ trước | object cũ vẫn trả v1 |
| Add locale file | bổ sung `Messages_es` sau negative lookup | trước clear cache còn root; sau clear cache chọn `es` |
| Unicode content | Resource UTF-8 có chữ Việt có dấu | không lỗi encoding |
| Packaged artifact | chạy trên JAR/module thật | file/path/visibility đúng |
| Concurrent tests | đổi global locale ở test độc lập | không gây race/ảnh hưởng test khác |

Không nhất thiết dồn tất cả vào một unit test lớn. Chia thành unit tests cho contract, integration tests cho file/classloader, và packaging tests trên artifact deploy để khoanh vùng lỗi.

## 15. Những lỗi phổ biến khi kiểm thử `ResourceBundle`

1. **Nhầm missing bundle với missing key.** Hai đường có thể cùng ném `MissingResourceException` nhưng xảy ra ở những lời gọi khác nhau; tách test để biết nguyên nhân.
2. **Chỉ assert text, không assert selected locale.** Nếu root và bản dịch tình cờ giống nhau, test vẫn xanh dù chọn sai bundle.
3. **Cho rằng JVM default locale sẽ giải quyết mọi missing key.** Default fallback thuộc **bước tìm bundle**, không tự nhảy sang ngôn ngữ khác trong per-key lookup của bundle đã chọn.
4. **Tưởng `getNoFallbackControl(...)` loại bỏ parent lookup.** Nó ngăn fallback tới JVM default, còn candidate/root và parent chain vẫn tồn tại.
5. **Giữ cache xuyên các test và dựa vào thứ tự chạy.** Dùng loader riêng, base name riêng hoặc clearCache đúng thời điểm.
6. **Sửa file và kỳ vọng `getBundle(...)` luôn đọc lại.** Cache mặc định có thể trả instance cũ; test cần nhận biết chính sách cache/TTL.
7. **Gọi `clearCache(loader)` nhưng vẫn dùng reference cũ.** Lookup mới mới có cơ hội đọc bản cập nhật; object cũ không tự đổi dữ liệu.
8. **Tạo locale file mới nhưng không làm mới negative cache.** Bundle của locale mới có thể chưa được phát hiện.
9. **Đổi `Locale.setDefault(...)` giữa các test song song.** Đây là global JVM state, gây flaky test.
10. **Quên đóng `URLClassLoader` khi test file/JAR.** Có thể giữ handle hoặc resource, nhất là trên Windows.
11. **Chỉ test file trong source tree, không test JAR thật.** Resource có thể bị thiếu sau build hoặc sai đường dẫn.
12. **Copy ví dụ `Control` vào named module.** Overload nhận Control không hỗ trợ named-module caller và có thể ném `UnsupportedOperationException`.
13. **Dùng `containsKey` để kết luận locale đã dịch trực tiếp key.** Nó bao gồm cả inherited keys từ parent chain.
14. **Tự bỏ exception và trả chuỗi rỗng cho key bắt buộc.** Lỗi bản dịch bị che khuất; cần policy optional/required rõ ràng.
15. **Chỉnh sửa JAR đang chạy rồi kỳ vọng reload bằng `clearCache`.** Đây không phải giao thức hot reload đáng tin cậy của application server.

## 16. Bài tập và câu hỏi tự kiểm tra

**Câu 1.** Một file `Messages_fr_CA.properties` tồn tại nhưng không có key `submit.label`; file `Messages_fr.properties` có key đó. Kết quả?

**Đáp:** `getString("submit.label")` tìm theo parent chain và trả giá trị từ `fr`. `getLocale()` của bundle chính vẫn là `fr-CA`.

**Câu 2.** JVM default `en-US`; `Messages_fr_CA` đã được chọn nhưng key `only_en` chỉ nằm ở `Messages_en`. Có tự chuyển sang tiếng Anh không?

**Đáp:** Không. Fallback sang default locale được dùng khi **chọn bundle phù hợp target** trong trường hợp không tìm được localized bundle; một key thiếu trong bundle đã chọn chỉ được tìm theo **parent chain** của bundle đó.

**Câu 3.** `ResourceBundle.getBundle("AbsentMessages", Locale.ROOT, loader, NO_DEFAULT)` trả `null` không?

**Đáp:** Không. Khi không tìm thấy family phù hợp, nó ném `MissingResourceException`. Test nên xác minh exception đó, không so kết quả với `null`.

**Câu 4.** Vì sao sau khi sửa `LiveMessages.properties` thành v2, code vẫn đọc v1?

**Đáp:** `ResourceBundle` có cache; lệnh `getBundle(...)` có thể trả instance đã load trước khi sửa file. Cần cơ chế reload theo policy: invalidate cache, lấy bundle mới và cập nhật reference ứng dụng.

**Câu 5.** Sau `ResourceBundle.clearCache(loader)`, biến `old` trỏ đến bundle v1 có tự trả v2 không?

**Đáp:** Không. `clearCache` tác động tới **cache lookup**, không mutate object đang được tham chiếu. Tạo/lấy bundle mới rồi thay reference nếu muốn dùng v2.

**Câu 6.** Đã tạo `Messages_es.properties` mới nhưng `getBundle(...)` vẫn chọn root; bước test tiếp theo?

**Đáp:** Xác minh đường dẫn resource thực sự thuộc class loader, sau đó invalidate cache đúng loader và thử lookup mới. Nếu vẫn root, kiểm tra tên file, classpath/JAR/module visibility, encoding và control policy.

**Câu 7.** `getNoFallbackControl(...)` có khiến `fr-CA` không thể dùng key từ `fr` hoặc root không?

**Đáp:** Không. Nó không tắt **parent-key lookup**; chỉ ngăn fallback sang JVM default khi chọn bundle.

**Câu 8.** Tại sao một test đổi `Locale.setDefault(Locale.US)` cần `finally` và không nên chạy song song tùy tiện?

**Đáp:** Vì default locale là trạng thái toàn JVM; test khác có thể bị ảnh hưởng và trở nên không ổn định. `finally` restore giá trị cũ ngay cả khi test ném exception.

**Câu 9.** Có thể kiểm thử 100% bản dịch locale bằng `bundle.keySet()` không?

**Đáp:** Không. `keySet()` và `containsKey()` tính cả inherited keys. Kiểm tra completeness cần so các **source bundles riêng** với bộ key baseline, không chỉ tra bundle cuối cùng đã fallback.

**Câu 10.** Test classpath thành công có chứng minh named-module deployment sẽ hoạt động với cùng `ResourceBundle.Control` không?

**Đáp:** Không. Overload nhận `Control` không hỗ trợ named-module caller. Cần kiểm thử đường module/resource provider thích hợp và lựa chọn fallback policy tại application layer.

**Ghi nhớ:** Hãy kiểm thử `ResourceBundle` theo **bốn tầng rõ ràng**: (1) bundle family có tồn tại, (2) locale nào được chọn, (3) key đến từ child/parent hay bị thiếu, (4) resource/cached instance thay đổi ra sao khi deploy file mới. Dùng fixture và class loader riêng để tránh test không ổn định; tách cache invalidation khỏi quản lý reference đang được ứng dụng giữ. Đây là những kỹ thuật Java SE hiện hành cho i18n và localization testing.

### Tài liệu chính thức

- [Oracle Java SE 26 — ResourceBundle](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ResourceBundle.html): lookup strategy, fallback, cache, `clearCache`, named modules.
- [Oracle Java SE 26 — ResourceBundle.Control](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ResourceBundle.Control.html): candidates, `getNoFallbackControl`, TTL và `needsReload`.
- [Oracle Java SE 26 — Locale](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.html): `Locale.ROOT`, default locale, BCP 47 language tags.
- [Oracle Java SE 26 — PropertyResourceBundle](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/PropertyResourceBundle.html): đọc resource từ file `.properties`.
- [Oracle Java SE 26 — ResourceBundleProvider](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/spi/ResourceBundleProvider.html): provider khi sử dụng resource bundles với named modules.

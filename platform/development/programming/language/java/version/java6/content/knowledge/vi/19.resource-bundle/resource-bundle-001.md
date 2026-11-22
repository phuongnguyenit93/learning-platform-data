# ResourceBundle.Control và tùy biến tải tài nguyên trong Java 17+

## 1. Tại sao cần ResourceBundle.Control?

`java.util.ResourceBundle` là API chuẩn của Java để lấy thông điệp, nhãn giao diện và cấu hình theo `Locale`. Ví dụ, một ứng dụng đa ngôn ngữ có thể dùng các tài nguyên `Messages.properties`, `Messages_vi.properties` hoặc `Messages_vi_VN.properties` rồi truy vấn:

```java
ResourceBundle b = ResourceBundle.getBundle(
        "i18n.Messages", Locale.forLanguageTag("vi-VN"));
String greeting = b.getString("greeting");
```

Đây là **snippet** trong method có import `java.util.ResourceBundle` và `java.util.Locale`. Với quy ước file classpath chuẩn, base name `i18n.Messages` tương ứng với thư mục `i18n/` và tập file cùng tên.

**`ResourceBundle.Control`** cho phép tùy chỉnh cách `ResourceBundle.getBundle` chọn định dạng, tạo tên resource, thử các locale, fallback, tải bundle và quyết định thời gian cache. Các trường hợp dùng thực tế:
- Chỉ cho phép resource `.properties` và bỏ qua class-based bundles.
- Không tự fallback sang `Locale` mặc định trên server.
- Dùng một quy tắc tìm locale khác cho ứng dụng.
- Nạp resource từ XML, nguồn dữ liệu nội bộ hoặc một định dạng tùy chỉnh.
- Kiểm soát TTL và reload khi tài nguyên thay đổi trong quá trình chạy.

**Giới hạn rất quan trọng ở Java hiện đại:** `ResourceBundle.Control` vẫn là API được hỗ trợ **cho ứng dụng chạy trong unnamed module/classpath**. Tuy nhiên, **overload `ResourceBundle.getBundle(..., Control)` không được hỗ trợ khi lời gọi được thực hiện từ named module**, và sẽ ném `UnsupportedOperationException`. Với kiến trúc JPMS named modules, hãy dùng **`ResourceBundleProvider`**, `AbstractResourceBundleProvider` hoặc lookup module-aware, không coi `Control` là phương án xuyên mọi kiểu đóng gói.

Bài tập trung vào hành vi Java 17+ còn áp dụng hiện nay. Bạn sẽ học:
1. Quy trình tìm bundle và các callback của `Control`.
2. Khác biệt giữa candidate locales, fallback locale và parent fallback key.
3. Các cách chọn format và tự nạp nguồn dữ liệu.
4. TTL, `needsReload`, clear cache và vấn đề đa luồng.
5. Một **chương trình Java chạy được** tự tạo bundle từ `Map` trong RAM.
6. Hạn chế trong named modules và hướng dùng `ResourceBundleProvider`.
7. Lỗi phổ biến, kiểm thử và cách tổ chức tài nguyên production.

## 2. ResourceBundle.getBundle phối hợp với Control như thế nào?

Hình dung quy trình classpath/unnamed module:

```text
getBundle(baseName, requestedLocale, loader, control)
                             |
                       kiểm tra cache
                             |
                  control.getFormats(...)
                             |
           control.getCandidateLocales(...)
                             |
       thử từng (candidate locale, resource format)
                             |
              control.newBundle(..., reload)
                             |
                chọn các bundle tìm thấy
                             |
            tạo parent chain cho fallback key
                             |
             nếu cần, getFallbackLocale(...)
                             |
                  trả ResourceBundle
                             |
                  bundle.getString(key)
                             |
            key hiện tại hoặc parent bundle
```

Đây là **sơ đồ khái niệm**, không phải thứ tự gọi callback tuyệt đối trong mọi tình huống. Cache, bundle sẵn có, root bundle, fallback default locale và các lựa chọn của Control quyết định những callback nào được thực thi. Lệnh gọi khi có cache hit có thể không phải tải lại resource.

Thành phần chính:

| Thành phần | Vai trò |
| --- | --- |
| `baseName` | Tên logic của họ bundle, ví dụ `i18n.Messages`. |
| `Locale` | Ngôn ngữ/script/quốc gia/variant được yêu cầu; ví dụ `vi-VN`. |
| `ClassLoader` | Ngữ cảnh tìm classes/resources trong classpath. |
| `Control` | Policy định dạng, locale candidates, fallback, loading và cache. |
| `ResourceBundle` | Object tra cứu key, có thể dùng parent bundle cho key thiếu. |

**Hai loại fallback khác nhau:**
- `getFallbackLocale(...)`: chọn **locale khác để tìm** nếu không tìm được bundle thích hợp ở locale đã yêu cầu, thường liên quan `Locale.getDefault()`.
- **Parent key fallback**: trong một bundle tiếng Việt, nếu key `color` thiếu thì có thể lấy từ parent root `Messages.properties`.

Vì vậy, “không fallback sang default locale” **không đồng nghĩa** “cấm root bundle” hoặc “cấm kế thừa key từ parent”.

## 3. Các callback quan trọng của ResourceBundle.Control

| Callback | Trách nhiệm | Khi nên override |
| --- | --- | --- |
| `getFormats(String baseName)` | Trả danh sách format được thử theo thứ tự. | Chọn properties-only, class-only hoặc custom format. |
| `getCandidateLocales(String baseName, Locale locale)` | Trả chuỗi locale ứng viên để tìm bundle. | Có chính sách phân tầng locale khác mặc định. |
| `getFallbackLocale(String baseName, Locale locale)` | Đề xuất locale tiếp theo sau khi tìm không thành công. | Tắt fallback sang default JVM locale. |
| `newBundle(String, Locale, String, ClassLoader, boolean)` | Tạo/nạp một ResourceBundle cho locale và format. | Nạp XML, dữ liệu trong RAM, resource riêng. |
| `getTimeToLive(String, Locale)` | Chọn TTL cache. | Muốn kiểm soát độ mới tài nguyên. |
| `needsReload(...)` | Sau khi TTL hết, quyết định có tải lại hay không. | Kiểm tra version, last-modified, ETag… |
| `toBundleName(String, Locale)` | Tạo tên bundle từ base name và locale. | Quy ước đặt tên không chuẩn. |
| `toResourceName(String, String)` | Tạo đường dẫn resource từ bundle name và suffix. | **Final method**, chỉ gọi, không override. |

**Formats mặc định**:
- `ResourceBundle.Control.FORMAT_DEFAULT`: `"java.class"` trước `"java.properties"`.
- `FORMAT_CLASS`: chỉ `"java.class"`.
- `FORMAT_PROPERTIES`: chỉ `"java.properties"`.

Không sử dụng prefix `"java."` cho format tự tạo vì được Java dành riêng. Danh sách formats trả về nên có phần tử hợp lệ, ổn định giữa các lần lookup cùng họ bundle.

## 4. Chọn properties-only không cần subclass Control

Nếu chỉ cần ép `ResourceBundle` tra cứu file `.properties`:

```java
ResourceBundle.Control onlyProperties =
        ResourceBundle.Control.getControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);

ResourceBundle b = ResourceBundle.getBundle(
        "i18n.Messages",
        Locale.forLanguageTag("vi-VN"),
        onlyProperties);
```

Đây là snippet chạy trong **unnamed module** và giả định có resource tương ứng trên classpath. `getControl(FORMAT_PROPERTIES)` là factory method sẵn có, trả Control dùng chung phù hợp. Nó vẫn áp dụng quy tắc fallback thông thường.

Nếu muốn **chặn việc tự chuyển sang default JVM Locale** khi thiếu bundle ngôn ngữ yêu cầu:

```java
ResourceBundle.Control noDefaultLocaleFallback =
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);

ResourceBundle b = ResourceBundle.getBundle(
        "i18n.Messages",
        Locale.forLanguageTag("vi-VN"),
        noDefaultLocaleFallback);
```

**Đừng hiểu nhầm tên:** `getNoFallbackControl` khiến `getFallbackLocale` trả `null`, tức không tìm sang locale mặc định của JVM. Nó **không tự loại `Locale.ROOT` khỏi danh sách candidate locales**, cũng không cấm key inheritance từ root bundle khi đã có parent chain.

### 4.1. Ví dụ thư mục resources

```text
src/main/resources/
  i18n/
    Messages.properties
    Messages_vi.properties
    Messages_vi_VN.properties
    Messages_en_US.properties
```

Ví dụ `Messages.properties`:

```properties
greeting=Hello
color=Color
```

Ví dụ `Messages_vi.properties`:

```properties
greeting=Xin chào
```

Trong một build classpath thông thường, các file trên được đóng vào classpath output hoặc JAR. Khi lookup `vi-VN` mà bundle `vi` có `greeting` nhưng không có `color`, code có thể lấy `color=Color` từ root `Messages.properties`.

**Java 17+ hỗ trợ properties UTF-8** thông qua `PropertyResourceBundle` mặc định. Nếu `PropertyResourceBundle(InputStream)` gặp byte sequence không hợp lệ theo UTF-8, API còn có cơ chế thử lại ISO-8859-1 theo policy mặc định. Đừng dạy việc bắt buộc chuyển mọi dấu tiếng Việt sang `\\uXXXX` hoặc tự override loader chỉ để đọc UTF-8 như một workaround của Java rất cũ. Khi yêu cầu encoding nghiêm ngặt, kiểm soát file encoding và có thể dùng system property `java.util.PropertyResourceBundle.encoding` theo API.

## 5. Candidate locales và thứ tự tra cứu

Với `Locale.forLanguageTag("vi-VN")`, một danh sách locale ứng viên điển hình là:

```text
vi_VN
vi
Locale.ROOT
```

Đối với base name `i18n.Messages`, chúng tương ứng với `Messages_vi_VN`, `Messages_vi` và `Messages`. Nếu ứng dụng chỉ có `Messages_vi.properties` và `Messages.properties`, ResourceBundle vẫn có thể tìm ra tiếng Việt và dựng parent chain.

Bạn có thể quan sát danh sách qua:

```java
ResourceBundle.Control c =
        ResourceBundle.Control.getControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);
List<Locale> candidates = c.getCandidateLocales(
        "i18n.Messages", Locale.forLanguageTag("vi-VN"));
```

Đây là snippet có import `java.util.List`, `Locale` và `ResourceBundle`. Với script/variant/đặc điểm đặc biệt của `Locale`, danh sách có thể dài và phức tạp hơn; không tự cố định quy tắc ba phần tử cho mọi locale.

Nếu cần override `getCandidateLocales`:
- Tuân thủ contract của API và trả danh sách ổn định cho cùng base/locale.
- Xem lại cả root fallback và `getFallbackLocale`.
- Không tạo chu trình fallback hoặc danh sách không hợp lệ.
- Kiểm tra cache khi thay đổi policy.
- Ưu tiên một policy rõ ràng được test trên `vi-VN`, `en-US`, `Locale.ROOT` và locale thiếu tài nguyên.

Để kiểm soát **độ đầy đủ bản dịch**, một quy trình test coverage cho toàn bộ keys thường dễ duy trì hơn việc vô hiệu hóa parent bundles không có kế hoạch.

## 6. Chương trình Java 17+ chạy được: Control tự tạo bundle trong RAM

Ví dụ **độc lập một file**, không cần tạo resource files, không dùng thư viện ngoài JDK. Nó sử dụng:
- `getFormats` trả custom format `"memory"`.
- `newBundle` tạo bundle từ map khi có dữ liệu cho root, `vi` hoặc `en-US`.
- `getFallbackLocale` trả `null`, không fallback sang default JVM Locale.
- `getTimeToLive` trả `TTL_DONT_CACHE` để phép thử không phụ thuộc bản cache cũ.
- `ResourceBundle.getBundle` dùng candidate locales và parent key lookup.

Khi yêu cầu `vi-VN`, `newBundle` không có mục dữ liệu dành riêng cho `vi-VN`, vì vậy chọn `vi`. Đối với key `color` thiếu ở `vi`, parent root cung cấp `Color`.

### 6.1. File BundleControlDemo.java

```java
import java.util.Collections;
import java.util.Enumeration;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.ResourceBundle;
import java.util.Set;

public final class BundleControlDemo {

    private static final String BASE = "demo.Messages";

    private static final class MapBundle extends ResourceBundle {
        private final Map<String, Object> values;

        MapBundle(Map<String, Object> values) {
            this.values = Map.copyOf(values);
        }

        @Override
        protected Object handleGetObject(String key) {
            return values.get(key);
        }

        @Override
        public Enumeration<String> getKeys() {
            Set<String> keys = new LinkedHashSet<>(values.keySet());
            if (parent != null) {
                keys.addAll(parent.keySet());
            }
            return Collections.enumeration(keys);
        }
    }

    // Chỉ dùng cho lookup classpath/unnamed module.
    private static final class MemoryControl
            extends ResourceBundle.Control {

        @Override
        public List<String> getFormats(String baseName) {
            return List.of("memory");
        }

        @Override
        public Locale getFallbackLocale(
                String baseName, Locale locale) {
            return null;
        }

        @Override
        public long getTimeToLive(
                String baseName, Locale locale) {
            return TTL_DONT_CACHE;
        }

        @Override
        public ResourceBundle newBundle(
                String baseName,
                Locale locale,
                String format,
                ClassLoader loader,
                boolean reload) {

            if (!BASE.equals(baseName) || !"memory".equals(format)) {
                return null;
            }

            if (Locale.ROOT.equals(locale)) {
                return new MapBundle(Map.of(
                        "greeting", "Hello",
                        "color", "Color"));
            }

            if (Locale.forLanguageTag("vi").equals(locale)) {
                return new MapBundle(Map.of(
                        "greeting", "Xin ch\u00e0o"));
            }

            if (Locale.US.equals(locale)) {
                return new MapBundle(Map.of(
                        "greeting", "Howdy"));
            }

            return null;
        }
    }

    public static void main(String[] args) {
        MemoryControl control = new MemoryControl();
        ClassLoader loader = BundleControlDemo.class.getClassLoader();

        ResourceBundle vi = ResourceBundle.getBundle(
                BASE, Locale.forLanguageTag("vi-VN"),
                loader, control);

        ResourceBundle us = ResourceBundle.getBundle(
                BASE, Locale.US,
                loader, control);

        System.out.println("viLocale="
                + vi.getLocale().toLanguageTag());
        System.out.println("viGreeting="
                + vi.getString("greeting"));
        System.out.println("viColor="
                + vi.getString("color"));
        System.out.println("usLocale="
                + us.getLocale().toLanguageTag());
        System.out.println("usGreeting="
                + us.getString("greeting"));
        System.out.println("usColor="
                + us.getString("color"));
        System.out.println("formats="
                + control.getFormats(BASE));
        System.out.println("candidates="
                + control.getCandidateLocales(
                        BASE, Locale.forLanguageTag("vi-VN"))
                        .size());
    }
}
```

### 6.2. Lệnh chạy và stdout chính xác

Lưu file bằng UTF-8. Dùng JDK 17 trở lên và **không thêm `module-info.java`**:

```bash
javac -encoding UTF-8 BundleControlDemo.java
java -cp . BundleControlDemo
```

Stdout của chương trình, đã kiểm tra bằng JDK hiện đại:

```text
viLocale=vi
viGreeting=Xin chào
viColor=Color
usLocale=en-US
usGreeting=Howdy
usColor=Color
formats=[memory]
candidates=3
```

Giải thích:
1. Requested `vi-VN` không có bundle trực tiếp, nên `ResourceBundle` tìm tiếp `vi`, vì thế `viLocale=vi`.
2. `vi` có key `greeting` và trả `Xin chào`; thiếu key `color` nên tra parent root và trả `Color`.
3. `en-US` có riêng greeting `Howdy`, còn `color` cũng đến từ root.
4. `getFormats` trả `"memory"`; JDK không biết cách nạp nó, nhưng `newBundle` được override để tạo `ResourceBundle`.
5. `getCandidateLocales` mặc định với `vi-VN` có ba candidate: `vi-VN`, `vi` và root.
6. `TTL_DONT_CACHE` phù hợp demo, nhưng production thường nên cache để giảm chi phí.

**Chú ý:** code trên minh họa callback và lookup, không khuyến nghị hard-code bản dịch thật trong source. `newBundle` bỏ qua `loader`/`reload` vì chỉ đọc map bất biến; nếu thực tế đọc file/URL/database, cần xử lý I/O, caching, lỗi và nguồn tài nguyên đáng tin theo hợp đồng API.

## 7. Tùy biến định dạng qua getFormats và newBundle

`getFormats` định nghĩa các loại bundle mà `ResourceBundle` sẽ thử. Với định dạng riêng, ví dụ XML:

```java
@Override
public List<String> getFormats(String baseName) {
    return List.of("xml");
}
```

Đây là snippet **trong subclass `ResourceBundle.Control`**. Đặt `"xml"` chỉ định một nhãn format; **không có nghĩa Java tự biết đọc XML thành ResourceBundle**. Bạn phải override `newBundle` để tìm file, parse dữ liệu rồi trả ResourceBundle.

Để tạo đường dẫn resource trong `newBundle`:

```java
String bundleName = toBundleName(baseName, locale);
String resourcePath = toResourceName(bundleName, "xml");
```

Đây là snippet có `baseName` và `locale` hợp lệ trong subclass. Ví dụ `demo.Messages` + `vi-VN` dẫn đến `demo/Messages_vi_VN.xml` theo naming mặc định.

- `toBundleName` có thể override để đổi quy ước tên.
- `toResourceName` là **final**, không thể override.
- Các format bắt đầu bằng `"java."` được dành riêng, không dùng cho định dạng tùy chọn.

Ví dụ phần **đọc XML** bên trong `newBundle`:

```java
String path = toResourceName(
        toBundleName(baseName, locale), "xml");

try (InputStream in = loader.getResourceAsStream(path)) {
    if (in == null) {
        return null;
    }

    Properties properties = new Properties();
    properties.loadFromXML(in);

    // Dùng properties để tạo subclass ResourceBundle,
    // chẳng hạn một Map-backed ResourceBundle hợp lệ.
}
```

Đây **không phải phương thức hoàn chỉnh có thể biên dịch độc lập**: nó cần khai báo import `java.io.InputStream`, `java.util.Properties`, xử lý `IOException` và thêm bước chuyển đổi dữ liệu thành ResourceBundle. Đoạn mã cho thấy cách dùng classloader resource và `try-with-resources` để đóng stream.

**Khi resource thật không tồn tại**, `newBundle` trả `null`. Nhưng nếu có lỗi đọc/parse không mong đợi, đừng lặng lẽ trả `null` như thể đây là locale không có bản dịch; hãy báo lỗi bằng exception phù hợp.

Nếu `reload == true` và loader đang lấy URL, cân nhắc `URLConnection.setUseCaches(false)` để tránh cache ngầm của connection khi cần tải nội dung mới. Đừng dựng file path hoặc URL trực tiếp từ input người dùng không tin cậy mà không có validation và authorization.

### 7.1. UTF-8 properties trong Java hiện đại

`PropertyResourceBundle` trên Java 17 **mặc định giải mã input stream theo UTF-8**; nếu không hợp lệ, API có fallback ISO-8859-1 trừ khi runtime được cấu hình theo cách cố định encoding. Ngoài ra, constructor `PropertyResourceBundle(Reader)` cho phép caller chủ động cung cấp một reader đã chọn charset. Vì vậy, **không cần một custom Control chỉ để hỗ trợ tiếng Việt UTF-8 trong properties**.

## 8. Cache, TTL, needsReload và clearCache

ResourceBundle giữ cache theo chính sách của `getBundle`/Control. Các lựa chọn quan trọng:

| TTL | Ý nghĩa | Hệ quả |
| --- | --- | --- |
| `TTL_NO_EXPIRATION_CONTROL` | Không áp dụng kiểm tra hết hạn TTL theo Control. | Phù hợp resources tĩnh, không đảm bảo giữ mãi trong cache vì JVM vẫn có thể thu hồi. |
| `TTL_DONT_CACHE` | Không cache loaded bundles trong ResourceBundle. | Thích hợp test, có thể tốn I/O/CPU nếu dùng production. |
| `0` | Bundle được xem là hết hạn và phải được kiểm tra khi tra cứu. | Có thể phải gọi `needsReload` nhiều lần. |
| Số dương như `5_000L` | TTL tính bằng mili giây. | Khi hết hạn sẽ kiểm tra có cần reload. |

Chỉ cần override:

```java
@Override
public long getTimeToLive(String baseName, Locale locale) {
    return 5_000L;
}
```

Đây là snippet subclass `Control`. **TTL 5 giây không đồng nghĩa bundle chắc chắn được nạp lại đúng 5 giây sau**. Khi cache entry hết hạn và có lookup tiếp theo, `needsReload` quyết định có phải reload từ nguồn không. Nếu trả false, entry có thể tiếp tục dùng với thời hạn TTL mới; nếu true, cache entry bị loại và `newBundle` được gọi để nạp mới.

`needsReload` mặc định kiểm tra thông tin thay đổi của source theo hợp đồng thích hợp, chẳng hạn last-modified với tài nguyên file. Với nguồn custom như database hoặc remote config, có thể phải override theo version, ETag hoặc timestamp của nguồn để xác định stale data.

**Xóa cache thủ công**:

```java
ResourceBundle.clearCache();
ResourceBundle.clearCache(loader);
```

Đây là snippet có biến `loader` kiểu `ClassLoader` được cấp trong ngữ cảnh ứng dụng. Cache clear không làm những object `ResourceBundle` mà component khác **đang giữ reference** tự cập nhật giá trị; component phải thực hiện lookup lại nếu muốn dữ liệu mới.

Không gọi `clearCache` cho mỗi request một cách vô điều kiện, cũng không dùng `TTL_DONT_CACHE` cho toàn bộ bản dịch tĩnh nếu không có yêu cầu cụ thể.

## 9. Control và cache: ba vấn đề dễ nhầm

### 9.1. Cache có thể làm newBundle không được gọi

Khi `getBundle` tìm thấy bundle chưa hết hạn trong cache, nó có thể trả lại ngay. Nếu đặt log vào `newBundle` mà không thấy log trong lần gọi sau, đó **không chứng minh code bị bỏ qua**; có thể cache đang hoạt động đúng.

### 9.2. Đừng thay format policy giữa các lần lookup

Theo API, tập `getFormats` và `getCandidateLocales` cho cùng base bundle nên **ổn định** trong các lời gọi tương ứng. Một lần lookup đầu dùng class-based bundle, lần sau đổi sang properties-only nhưng vẫn dùng cùng base/loader/cache có thể nhận kết quả bất ngờ từ cache.

Để kiểm thử hai policy:
- Giữ base/loader và cache cách ly giữa các test.
- Hoặc chủ động `clearCache` đúng phạm vi.
- Không thay các callback theo từng request trong một hệ thống production mà bỏ qua cache behavior.
- Nếu thực sự có hai nguồn tách biệt, dùng base name/loader riêng hoặc một contract policy ổn định.

### 9.3. Thread safety

`ResourceBundle.getBundle` không tự đồng bộ các callback `Control`. Nếu cùng một instance `Control` được nhiều thread dùng đồng thời, implementation phải **thread-safe**. Ưu tiên stateless/immutable control và source dữ liệu có concurrency policy rõ ràng; tránh trả live mutable `List` hoặc chia sẻ `HashMap` không đồng bộ.

## 10. Giới hạn JPMS: Control không dùng trong named module

Trong Java 9+ và JDK hiện đại, named modules có hệ thống resource loading và service provider riêng. **Gọi overload `ResourceBundle.getBundle(..., ResourceBundle.Control)` từ code thuộc named module gây `UnsupportedOperationException`.** Đây là điều khoản API chứ không phải cấu hình classpath sai có thể sửa bằng cách thêm option bất kỳ.

Khi viết ứng dụng named module:
- Dùng `ResourceBundle.getBundle(...)` theo đường lookup module-aware khi chỉ cần resource thông thường.
- Nếu cần tùy biến nguồn/tìm bundle qua service provider, dùng **`java.util.spi.ResourceBundleProvider`**.
- `ResourceBundleControlProvider` SPI được dùng để tùy biến default loading phía classpath, nhưng **các provider này bị bỏ qua trong named modules**.
- Xem xét package/module visibility và module resource encapsulation; không giả định resource trong module path có cùng hành vi với classpath.

### 10.1. ResourceBundleProvider và quy ước service type

Với base name `com.example.app.Messages`, service interface theo chuẩn đặt tên:

```java
// File: com/example/app/spi/MessagesProvider.java
package com.example.app.spi;

import java.util.spi.ResourceBundleProvider;

public interface MessagesProvider extends ResourceBundleProvider {
}
```

Đây là snippet service interface; package `spi` là subpackage được quy ước theo base name.

Trong consumer module:

```java
module com.example.app {
    uses com.example.app.spi.MessagesProvider;
}
```

Trong provider module:

```java
module com.example.messages.vi {
    requires com.example.app;
    provides com.example.app.spi.MessagesProvider
            with com.example.messages.vi.VietnameseProvider;
}
```

Các module descriptors là **snippets minh họa**, **chưa phải dự án runnable**. Cần tạo class `VietnameseProvider` triển khai service interface và trả ResourceBundle qua `getBundle(String baseName, Locale locale)`, bảo đảm service interface ở module được export thích hợp và provider module được resolve. Không tạo split packages giữa các named modules.

Có thể kế thừa `AbstractResourceBundleProvider` để tận dụng hỗ trợ nạp class/properties và tùy chỉnh bundle name hoặc locale phục vụ. Đây là hướng hiện hành cho bài toán provider trong JPMS, **không phải `Control` trên module path**.

## 11. ClassLoader, baseName và cách đóng gói resource

Với ứng dụng classpath, cấu trúc thường là:

```text
src/main/resources/i18n/Messages.properties
src/main/resources/i18n/Messages_vi.properties
src/main/resources/i18n/Messages_en_US.properties
```

Maven/Gradle Java plugin thường đưa tài nguyên từ `src/main/resources` vào classpath output/JAR theo cấu hình build. Dự án thực tế vẫn phải xác nhận JAR chứa đúng paths, không dựa vào IDE có thể thấy file mà artifact production lại thiếu.

Ví dụ dùng classloader được chọn rõ ràng:

```java
Locale locale = Locale.forLanguageTag("vi-VN");
ClassLoader loader = MyApplication.class.getClassLoader();

ResourceBundle.Control ctrl =
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);

ResourceBundle b = ResourceBundle.getBundle(
        "i18n.Messages", locale, loader, ctrl);
```

Đây là snippet; `MyApplication` là class của **ứng dụng bạn tự định nghĩa**, và phải có các file resource tương ứng. Nó không phải ví dụ standalone. Nếu dùng plugin classloader hoặc thread context classloader, xác định rõ ownership và cấu hình loader thay vì tự đoán.

Trong hệ thống plugin/hot reload, `ResourceBundle` cache gắn với loader có thể giữ trạng thái/tài nguyên cũ. Hãy quản lý vòng đời loader và cache; dọn đúng loader khi module/plugin được thay, tránh rò rỉ tài nguyên hoặc bundle stale.

## 12. Lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `MissingResourceException` từ `getBundle` | Base name sai, resource không được đóng gói, loader/module không nhìn thấy hoặc không có bundle phù hợp. | Kiểm tra tên, locale candidates, file trong JAR và classloader/module path. |
| `MissingResourceException` từ `getString(key)` | Bundle tồn tại nhưng key không có ở bundle hiện tại/parent. | Bổ sung key, test coverage bản dịch. |
| `UnsupportedOperationException` khi truyền `Control` | Caller đang ở **named module**. | Dùng module-aware lookup và `ResourceBundleProvider`. |
| `getNoFallbackControl` vẫn trả key từ root | Nó tắt default-locale fallback chứ không tắt parent root. | Hiểu candidates/parent chain. |
| `IllegalArgumentException` do custom Control | Formats/candidate locales vi phạm hợp đồng. | Trả danh sách hợp lệ, ổn định và test các locale. |
| `newBundle` không chạy trong lần gọi sau | Cache hit. | Kiểm tra TTL/clear cache và đúng lookup scope. |
| Resource thay đổi nhưng kết quả chưa đổi | TTL chưa hết, `needsReload` false hoặc cache tầng khác. | Rà soát TTL, reload và cache source. |
| `FORMAT_PROPERTIES` nhưng vẫn thấy class bundle | Bundle class đã có trong cache từ policy khác. | Giữ format policy cố định, cách ly test/cache. |
| Dữ liệu tiếng Việt bị lỗi dấu | Encoding sai ở file/build/loader custom. | Dùng UTF-8 và hiểu PropertyResourceBundle behavior Java 17+. |
| Custom `"xml"` không tải file | Chỉ khai báo `getFormats` mà chưa override `newBundle`. | Viết loader/parser cho format mới. |
| Lỗi đa luồng khi nhiều locale truy cập | Control/cache mutable không thread-safe. | Immutable state và concurrency control. |
| Bundle hot reload nhưng object cũ không đổi | Component vẫn giữ reference cũ. | Tra cứu lại bundle khi cần nhận bản mới. |
| Tìm file sai vị trí | Base name không khớp thư mục resource hoặc classloader khác. | Kiểm tra `ClassLoader.getResource(...)`, JAR entries và loader scope. |

## 13. Lưu ý bảo mật và hiệu năng

- Không xây resource URL/path trực tiếp từ dữ liệu không tin cậy; áp dụng validation/allowlist cho base name, locale và format.
- Với `newBundle` đọc file/network, dùng `try-with-resources`, timeout và xử lý lỗi rõ; không nhầm “resource không tồn tại” với “I/O bị lỗi”.
- Không đưa secret/API token hoặc toàn bộ nội dung nguồn tài nguyên vào logs.
- Text lấy từ ResourceBundle vẫn phải được **HTML-escape hoặc xử lý output encoding theo context** khi đưa ra trình duyệt; nó không tự chống XSS/SQL injection.
- Chú ý chi phí `TTL_DONT_CACHE` với nguồn chậm; dùng cache policy phù hợp thay vì mỗi lần đều request mạng.
- Với resource custom nhiều thread, đảm bảo đồng bộ, tránh mutable state không kiểm soát.
- Chỉ tải resource/provider từ nguồn đáng tin: class-based ResourceBundle hoặc custom loader có thể thực thi Java code với quyền tiến trình.
- Nếu sản phẩm yêu cầu thay đổi bản dịch động, thiết kế version và cơ chế invalidation thay vì dựa vào sửa file trên ổ đĩa mà không kiểm tra cache.

## 14. Bài tập tự kiểm tra

**Câu 1.** Khi nào nên chọn `ResourceBundle.Control.getControl(FORMAT_PROPERTIES)`?

**Đáp án:** Khi ứng dụng unnamed module/classpath chỉ muốn nạp bundle từ `.properties` thay vì tìm class bundle trước. Không cần viết subclass.

**Câu 2.** `getNoFallbackControl` có cấm root bundle không?

**Đáp án:** Không. Nó chặn fallback sang `Locale` mặc định của JVM; root candidate và parent chain vẫn có thể hoạt động.

**Câu 3.** Vì sao ví dụ `vi-VN` cho `viLocale=vi` nhưng `viColor=Color`?

**Đáp án:** Không có bundle `vi-VN`, nên chọn bundle `vi`; key `color` thiếu được kế thừa từ parent root.

**Câu 4.** Tại sao trả `List.of("xml")` ở `getFormats` chưa đủ đọc XML?

**Đáp án:** Vì `newBundle` phải cung cấp cách nạp, parse và tạo ResourceBundle cho format `"xml"`.

**Câu 5.** TTL 5.000 ms có bảo đảm tải bundle mới ngay sau 5 giây không?

**Đáp án:** Không. TTL hết hạn khiến `getBundle` kiểm tra cache khi có lookup; `needsReload` quyết định có tải lại hay không.

**Câu 6.** Dùng `getBundle(..., Control)` trong named module sẽ như thế nào?

**Đáp án:** Ném `UnsupportedOperationException` theo API hiện hành. Dùng `ResourceBundleProvider` hoặc module-aware lookup.

**Câu 7.** Trên Java 17, có bắt buộc mã hóa dấu tiếng Việt dạng `\\uXXXX` trong property files không?

**Đáp án:** Không. `PropertyResourceBundle` hỗ trợ UTF-8 mặc định; cần bảo đảm file và pipeline build sử dụng charset đúng.

**Câu 8.** Vì sao không nên thay `getFormats` tùy ý giữa các request của cùng baseName?

**Đáp án:** Vì ResourceBundle cache có thể trả bundle nạp từ policy cũ; API đòi hỏi callback policy nhất quán cho cùng họ bundle.

## 15. Checklist áp dụng

1. Xác định **classpath/unnamed module** hay **JPMS named module** trước khi chọn API.
2. Ưu tiên `ResourceBundle.getBundle(...)` mặc định cho nhu cầu chuẩn; chỉ thêm Control khi có yêu cầu thực.
3. Chọn `getControl(FORMAT_PROPERTIES)`/`getNoFallbackControl(...)` cho nhu cầu đơn giản, không vội viết subclass.
4. Khi làm custom format, trả tên format hợp lệ ở `getFormats` và tạo bundle trong `newBundle`.
5. Tách biệt candidate locales, default locale fallback và parent key inheritance.
6. Đặt TTL/reload policy rõ; đừng coi cache expiry là tự refresh nội dung chắc chắn.
7. Không đổi formats/candidates theo request mà bỏ qua cache; Custom Control phải thread-safe.
8. Đọc resource đúng classloader/module và xác nhận đóng gói trong artifact thực tế.
9. Với named modules dùng `ResourceBundleProvider` và module service declarations thích hợp.
10. Kiểm thử locale missing, key missing, caching, reload, encoding, concurrency và security.

## 16. Tài liệu chính thức hiện còn áp dụng

- [Java SE 17 — ResourceBundle.Control](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.Control.html): API callbacks, cache và hạn chế named module.
- [Java SE 17 — ResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html): lookup, candidates, parent chain và clearCache.
- [Java SE 17 — PropertyResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PropertyResourceBundle.html): UTF-8 properties và encoding policy.
- [Java SE 17 — ResourceBundleProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/ResourceBundleProvider.html): service-provider API cho named modules.
- [Java SE 17 — AbstractResourceBundleProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/AbstractResourceBundleProvider.html): triển khai helper cho provider.
- [Java SE 25 — ResourceBundle.Control](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ResourceBundle.Control.html): xác nhận giới hạn và API còn hiện hành trong JDK hiện đại.

# Tạo ResourceBundle từ nguồn tùy biến

## 1. Khi nào phải tạo bundle từ nguồn riêng?

Trong Java, `java.util.ResourceBundle` là cơ chế tiêu chuẩn để lấy thông điệp, nhãn UI, cấu hình hiển thị hoặc nội dung được quốc tế hóa dựa trên `Locale`. Nhiều chương trình chỉ cần các bundle được đóng gói sẵn, chẳng hạn `messages.properties` và `messages_vi.properties` nằm trên classpath. Tuy nhiên có những trường hợp dữ liệu dịch **không nằm trong resource thông thường của ứng dụng**:

- Nguồn dịch nằm ở **một thư mục bên ngoài file JAR**, để nhóm nội dung cập nhật mà không build lại ứng dụng.
- Bản dịch nằm trong **database, kho cấu hình tập trung, hệ thống quản trị nội dung (CMS)** hoặc dịch vụ từ xa.
- Dữ liệu có **định dạng riêng** (JSON, XML, key-value, dữ liệu đã được giải mã và xác thực) thay vì những file `.properties` tiêu chuẩn.
- Ứng dụng cần **chiến lược locale fallback hoặc cache/refresh có chủ đích**.
- Các bundle nằm trong **named modules** của Java Platform Module System (JPMS), không thể dùng nguyên cách tùy biến chỉ dành cho classpath.

API `ResourceBundle` vẫn là lựa chọn hợp lệ trong Java hiện đại. Điều quan trọng là **chọn đúng cơ chế mở rộng** theo cách đóng gói ứng dụng.

| Bối cảnh | Cơ chế được hỗ trợ | Lưu ý |
| --- | --- | --- |
| File `.properties` đóng trong classpath hoặc module | `ResourceBundle.getBundle(...)` mặc định | Không tự tạo loader nếu không cần |
| Dữ liệu nằm trong đối tượng Java cố định | `ListResourceBundle` hoặc subclass `ResourceBundle` | Khai báo nội dung bằng code |
| Nguồn/định dạng tùy biến, ứng dụng chạy trên **classpath (unnamed module)** | `ResourceBundle.Control`: `getFormats`, `newBundle`, TTL, fallback | API vẫn hoạt động, nhưng **không hỗ trợ Control overload từ named module** |
| Nguồn tùy biến cho **named modules** | `java.util.spi.ResourceBundleProvider` qua `uses`/`provides` | Hướng phù hợp cho ứng dụng modular |
| Dữ liệu thay đổi liên tục, có SLA mạng và transaction | Xây loader/repository riêng, kết hợp bundle/provider nếu phù hợp | Thiết kế cache, timeout, bảo mật và versioning |

**Mục tiêu bài này:** tự tạo một `ResourceBundle` có dữ liệu từ **file UTF-8 bên ngoài classpath**, dùng `ResourceBundle.Control` cho ứng dụng classpath; sau đó xây ví dụ **named module** dùng `ResourceBundleProvider` — cách tiếp cận hiện đại khi triển khai JPMS. Các ví dụ chạy bằng **Java 17+**, không dựa vào API obsolete/legacy.

## 2. ResourceBundle hoạt động như thế nào?

Giả sử code gọi:

~~~java
ResourceBundle bundle =
        ResourceBundle.getBundle("demo.messages", Locale.forLanguageTag("vi-VN"));
~~~

Đây là **đoạn trích**, cần `import java.util.*;` và có resource bundle trên đường tìm kiếm mặc định. Java có thể tìm các biến thể tên tương ứng với locale, ví dụ:

~~~text
Base name = demo.messages
Target    = vi-VN

Thứ tự candidate điển hình:
  demo.messages_vi_VN
  demo.messages_vi
  demo.messages             (root)

Key "greeting" có thể lấy từ demo.messages_vi
Key "shared" có thể lấy từ root khi locale con không khai báo
~~~

Tùy trường hợp, mặc định còn có fallback sang `Locale.getDefault()`. Không được nhầm:

- **Candidate locale chain:** thứ tự biến thể locale được tìm cho một target.
- **Parent bundle chain:** bundle `vi` kế thừa các key bị thiếu từ bundle root.
- **Default-locale fallback:** thử ngôn ngữ mặc định của JVM khi không tìm thấy bundle theo target trong những điều kiện do thuật toán quy định.
- **Cache:** sau khi load, `ResourceBundle.getBundle(...)` thường có thể trả lại bundle đã được cache thay vì đọc nguồn mỗi lần.

Khi **custom source**, trách nhiệm của ứng dụng là quyết định cách ánh xạ base name/locale sang dữ liệu thật, cách xử lý key vắng mặt, cách cập nhật cache và cách xử lý lỗi nguồn.

### 2.1. getString, getObject, getKeys, getLocale

| API | Ý nghĩa |
| --- | --- |
| `ResourceBundle.getBundle(baseName, locale, control)` | Gọi thuật toán tìm bundle với custom `Control` trên classpath |
| `getString("greeting")` | Tìm key trong bundle và parent chain, trả chuỗi |
| `getObject("key")` | Lấy object; value không bắt buộc là String |
| `containsKey("key")` | Kiểm tra key trong bundle/parent chain |
| `keySet()` | Tập key từ bundle và parent chain |
| `getKeys()` | Enumeration các key của bundle, bao gồm parent |
| `getLocale()` | **Locale thực sự của bundle được chọn**, có thể khác target |
| `MissingResourceException` | Khi không có bundle phù hợp hoặc không tìm thấy key |

Ví dụ gọi `Locale.forLanguageTag("fr-FR")` có thể nhận root bundle nếu không có bản dịch tiếng Pháp và chính sách cho phép root. Khi đó `getLocale()` của kết quả là `Locale.ROOT`, **không nhất thiết là `fr-FR`**.

### 2.2. Dữ liệu tùy biến không buộc phải là file .properties

Bạn có thể tạo subclass `ResourceBundle` chứa `Map<String, String>` rồi cấp dữ liệu Map từ file, database hoặc API. ResourceBundle không quan tâm bản dịch đi qua cơ chế nào **trước khi** đến bundle; nó cung cấp một giao diện tra cứu thống nhất cho code sử dụng.

Dù vậy, nếu dữ liệu bản chất chỉ là tệp `.properties` đóng trong JAR, nên dùng `PropertyResourceBundle`/loader mặc định. Customization có chi phí bảo trì: phải xử lý các quy tắc locale, I/O, cache, thread safety và lỗi.

## 3. Thiết kế cho nguồn tùy biến ngoài JAR

Ví dụ thực hành chính sẽ dùng:

~~~text
Ứng dụng chạy trên classpath
            |
            v
ResourceBundle.getBundle("demo.messages", requestedLocale, DiskControl)
            |
            v
ResourceBundle.Control
   - getFormats()       -> chỉ định "app.utf8txt"
   - newBundle()        -> đọc file bên ngoài classpath
   - getTimeToLive()    -> TTL_DONT_CACHE để thử cập nhật
   - getFallbackLocale()-> null: không fallback JVM default
            |
            v
ResourceBundle subclass: DataBundle(Map)
   - handleGetObject()
   - handleKeySet()
   - getKeys()
            |
            v
directory/
  demo/messages.txt         <- root
  demo/messages_vi.txt      <- tiếng Việt
  demo/messages_en.txt      <- tiếng Anh
            |
            v
Application gọi getString(key) và nhận locale/parent fallback
~~~

Ở đây extension `.txt` chỉ là **convention của ví dụ**: các file vẫn chứa cú pháp `key=value` mà `java.util.Properties.load(Reader)` hiểu. Chúng không nằm trong classpath; `DiskControl` đọc chúng từ một thư mục ngoài bằng `java.nio.file.Files`.

**Vì sao chọn cách này?** Nó cho phép tập trung vào `ResourceBundle.Control`, `newBundle` và fallback/TTL mà không cần bổ sung parser JSON hay database client. Sau khi hiểu API, thay loader đọc file bằng repository/API client với cơ chế cache/timeout rõ ràng sẽ đơn giản hơn.

## 4. Bốn callback quan trọng của ResourceBundle.Control

### 4.1. getFormats(String baseName)

`getFormats` khai báo **những format mà bộ tìm kiếm sẽ thử**. Giá trị chuẩn gồm `"java.class"` và `"java.properties"`. Format tự đặt nên dùng tên **không bắt đầu bằng `"java."`**, vì tiền tố ấy dành riêng cho các format tương lai của nền tảng.

Ví dụ:

~~~java
@Override
public List<String> getFormats(String baseName) {
    return List.of("app.utf8txt");
}
~~~

Đây là **đoạn phương thức trong `DiskControl`**, không phải class độc lập. `"app.utf8txt"` chỉ là nhãn để `newBundle` biết cách diễn giải nguồn. Nó không yêu cầu file thực tế có đuôi `.utf8txt`.

Danh sách format và candidate locales nên **nhất quán cho cùng baseName giữa các lần gọi**. Nếu một lần cấu hình format A rồi lần sau format B với cache cũ, kết quả có thể gây ngạc nhiên.

### 4.2. newBundle(baseName, locale, format, loader, reload)

`newBundle` nhận target **candidate locale**, format và class loader; trả:

- Một `ResourceBundle` khi có nguồn phù hợp.
- `null` khi **không có bundle cho candidate ấy**, để cơ chế tìm kiếm tiếp tục thử locale khác.
- Có thể ném `IOException`, `IllegalAccessException` hoặc `InstantiationException` theo contract khi load thất bại.

Với nguồn file ngoài, logic là:

~~~text
baseName = demo.messages
locale   = vi-VN
          |
          v
Control.toBundleName(...) = demo.messages_vi_VN
          |
          v
Control.toResourceName(..., "txt") = demo/messages_vi_VN.txt
          |
          v
Không tồn tại => newBundle() trả null
          |
          v
Thử candidate locale vi
          |
          v
File demo/messages_vi.txt tồn tại => tạo DataBundle
          |
          v
File root demo/messages.txt => parent bundle
~~~

**`reload` có ý nghĩa khi thực hiện kiểm soát cache và reloading.** Với loader dựa trên `ClassLoader.getResource`/`URLConnection`, khi `reload=true` nên chú ý cache của URLConnection. Trong demo chúng ta dùng `Files.newBufferedReader` trực tiếp và chính sách `TTL_DONT_CACHE`, nên mỗi lần `getBundle` lại có thể mở file mới; việc bỏ qua cờ `reload` trong loader minh họa không có nghĩa cờ này vô dụng ở mọi implementation.

### 4.3. getTimeToLive(baseName, locale)

Cache là phần thiết yếu khi nguồn dữ liệu có I/O. Một số giá trị:

| Giá trị | Ý nghĩa |
| --- | --- |
| `TTL_NO_EXPIRATION_CONTROL` | Không tự hết hạn dựa trên TTL (mặc định) |
| `TTL_DONT_CACHE` | Không lưu bundle trong cache; tác vụ lấy bundle sau có thể tải lại từ nguồn |
| Số mili giây không âm | Cài thời gian sống hữu hạn, sau đó cơ chế cache kiểm tra cần reload hay không |

`TTL_DONT_CACHE` phù hợp với **demo nhỏ muốn chứng minh dữ liệu vừa sửa được nhìn thấy ở lần lấy bundle tiếp theo**. Nó không phải lựa chọn tối ưu cho dịch vụ production: có thể gây đọc file/database/network lặp lại liên tục.

Nếu dùng TTL dương, cần hiểu `needsReload(...)`: sau khi TTL hết, JVM có thể kiểm tra xem nguồn có đổi hay chưa rồi mới gọi `newBundle` lần nữa. TTL hết hạn **không đồng nghĩa luôn tải lại**. Với nguồn database/HTTP, nên thiết kế logic version/ETag/lastModified và cache ở tầng phù hợp, tránh gọi mạng blocking trên đường truy cập UI.

### 4.4. getFallbackLocale(baseName, locale)

Mặc định, ResourceBundle có thể thử `Locale.getDefault()` khi không tìm được bundle cho target theo những điều kiện nhất định. Demo override:

~~~java
@Override
public Locale getFallbackLocale(String baseName, Locale locale) {
    return null;
}
~~~

Điều này **tắt fallback đến default locale của JVM**, giúp test ổn định giữa máy có default locale khác nhau.

Nó **không tắt chuỗi candidate locales** và cũng **không tắt parent bundle**. Trong ví dụ, `vi-VN` vẫn lùi về `vi` và có thể kế thừa key từ root. Với `fr-FR`, khi chỉ root bundle tồn tại, kết quả vẫn có thể là root.

### 4.5. getCandidateLocales và toBundleName

Không cần override `getCandidateLocales` để có những locale thông dụng. Control mặc định đã biết cách tạo danh sách candidate từ language/script/region/variant. Chỉ thay khi có requirement đặc biệt, vì việc bỏ candidate hoặc đảo thứ tự tùy tiện có thể thay đổi fallback ngoài mong muốn.

`toBundleName` và `toResourceName` là các helper chính thức, tránh tự nối chuỗi đường dẫn với quy tắc không tương thích. Khi nguồn được chứa trong directory bên ngoài, nên đưa đường dẫn tương đối trả về qua `Path.resolve(...)` rồi xác thực nó nằm trong **thư mục đã cho phép**.

## 5. ResourceBundle subclass đọc Map

Một subclass trực tiếp của `ResourceBundle` cần cung cấp thao tác tìm đối tượng theo key và enumeration các key. Ví dụ:

~~~java
static final class DataBundle extends ResourceBundle {
    private final Map<String, String> entries;

    DataBundle(Map<String, String> entries) {
        this.entries = Map.copyOf(entries);
    }

    @Override
    protected Object handleGetObject(String key) {
        return entries.get(key);
    }

    @Override
    protected Set<String> handleKeySet() {
        return entries.keySet();
    }

    @Override
    public Enumeration<String> getKeys() {
        return Collections.enumeration(keySet());
    }
}
~~~

**Đoạn này nằm trong class `CustomBundleDemo` ở phần 6**, nên có thể sử dụng imports của file đó.

- `handleGetObject` chỉ tìm ở **bundle hiện tại**. Khi trả `null`, `ResourceBundle` có thể kiểm tra parent.
- `handleKeySet` trả tập key cục bộ. Phương thức `keySet()` của `ResourceBundle` sẽ hợp nhất key cục bộ với parent.
- `getKeys()` dùng `Collections.enumeration(keySet())` nên liệt kê được cả key ở parent.
- `Map.copyOf(...)` tạo snapshot bất biến, hữu ích cho thread safety: một bundle được công bố sẽ không bị Map bên ngoài sửa giữa các lần `getString`.
- `getString` do `ResourceBundle` cung cấp. Không cần override; nó lấy object rồi ép kiểu chuỗi.
- Nếu key không tồn tại ở bundle lẫn parent, `getString` ném `MissingResourceException`.

Lưu ý: dữ liệu được cung cấp qua Map là **snapshot tại thời điểm load**. Thay file hoặc database bên ngoài **không tự sửa instance bundle cũ**; phải có chiến lược gọi `getBundle` và cache/refresh rõ ràng.

## 6. Ví dụ hoàn chỉnh Java 17+: bundle từ file ngoài classpath

Tạo file duy nhất `CustomBundleDemo.java`, nội dung bên dưới **biên dịch và chạy độc lập**. Nó tự tạo các tệp input tạm để không phụ thuộc đường dẫn máy người học.

~~~java
import java.io.IOException;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.stream.Stream;

public final class CustomBundleDemo {
    static final class DataBundle extends ResourceBundle {
        private final Map<String, String> entries;

        DataBundle(Map<String, String> entries) {
            this.entries = Map.copyOf(entries);
        }

        @Override
        protected Object handleGetObject(String key) {
            return entries.get(key);
        }

        @Override
        protected Set<String> handleKeySet() {
            return entries.keySet();
        }

        @Override
        public Enumeration<String> getKeys() {
            return Collections.enumeration(keySet());
        }
    }

    static final class DiskControl extends ResourceBundle.Control {
        private final Path directory;

        DiskControl(Path directory) {
            this.directory = directory.toAbsolutePath().normalize();
        }

        @Override
        public List<String> getFormats(String baseName) {
            return List.of("app.utf8txt");
        }

        @Override
        public Locale getFallbackLocale(String baseName, Locale locale) {
            return null;
        }

        @Override
        public long getTimeToLive(String baseName, Locale locale) {
            return TTL_DONT_CACHE;
        }

        @Override
        public ResourceBundle newBundle(String baseName, Locale locale,
                String format, ClassLoader loader, boolean reload) throws IOException {
            if (!"app.utf8txt".equals(format) || !"demo.messages".equals(baseName)) {
                return null;
            }
            String relative = toResourceName(toBundleName(baseName, locale), "txt");
            Path file = directory.resolve(relative).normalize();
            if (!file.startsWith(directory)) {
                throw new IOException("Path escaped allowed bundle directory");
            }
            if (!Files.isRegularFile(file)) {
                return null;
            }
            Properties props = new Properties();
            try (Reader reader = Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                props.load(reader);
            }
            Map<String, String> values = new HashMap<>();
            for (String key : props.stringPropertyNames()) {
                values.put(key, props.getProperty(key));
            }
            return new DataBundle(values);
        }
    }

    static void require(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("app-bundles-");
        try {
            Path demo = directory.resolve("demo");
            Files.createDirectories(demo);
            Files.writeString(demo.resolve("messages.txt"),
                    "greeting=Hello\nshared=from-root\n", StandardCharsets.UTF_8);
            Files.writeString(demo.resolve("messages_vi.txt"),
                    "greeting=Xin chào\n", StandardCharsets.UTF_8);
            Files.writeString(demo.resolve("messages_en.txt"),
                    "greeting=Hi\n", StandardCharsets.UTF_8);

            ResourceBundle.Control control = new DiskControl(directory);
            ResourceBundle vi = ResourceBundle.getBundle("demo.messages",
                    Locale.forLanguageTag("vi-VN"), control);
            require("Xin chào".equals(vi.getString("greeting")), "vi greeting");
            require("from-root".equals(vi.getString("shared")), "parent fallback");
            require(vi.getLocale().equals(Locale.forLanguageTag("vi")), "vi candidate");
            System.out.println("vi=" + vi.getString("greeting"));
            System.out.println("vi-parent=" + vi.getString("shared"));
            System.out.println("resolved-locale=" + vi.getLocale().toLanguageTag());

            ResourceBundle en = ResourceBundle.getBundle("demo.messages",
                    Locale.forLanguageTag("en-US"), control);
            require("Hi".equals(en.getString("greeting")), "en greeting");
            System.out.println("en=" + en.getString("greeting"));

            ResourceBundle fr = ResourceBundle.getBundle("demo.messages",
                    Locale.forLanguageTag("fr-FR"), control);
            require("Hello".equals(fr.getString("greeting")), "root fallback");
            System.out.println("fr-root=" + fr.getString("greeting"));

            Files.writeString(demo.resolve("messages_vi.txt"),
                    "greeting=Chào mới\n", StandardCharsets.UTF_8);
            ResourceBundle updated = ResourceBundle.getBundle("demo.messages",
                    Locale.forLanguageTag("vi-VN"), control);
            require("Chào mới".equals(updated.getString("greeting")), "reload");
            System.out.println("updated=" + updated.getString("greeting"));

            try {
                updated.getString("not-found");
                throw new AssertionError("expected MissingResourceException");
            } catch (MissingResourceException expected) {
                System.out.println("unknown-key=MissingResourceException");
            }
            System.out.println("tests=PASS");
        } finally {
            try (Stream<Path> paths = Files.walk(directory)) {
                for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }
}
~~~

### 6.1. Chạy ví dụ

Tại thư mục chứa `CustomBundleDemo.java`, với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 --release 17 CustomBundleDemo.java
java CustomBundleDemo
~~~

**Stdout chính xác** đã được biên dịch/chạy trên OpenJDK 24 với `--release 17`:

~~~text
vi=Xin chào
vi-parent=from-root
resolved-locale=vi
en=Hi
fr-root=Hello
updated=Chào mới
unknown-key=MissingResourceException
tests=PASS
~~~

Chương trình tự tạo thư mục tạm bằng `Files.createTempDirectory`, đọc ba file UTF-8 rồi dọn chúng ở `finally`, không thay đổi source repository. Các `require(...)` đóng vai trò assertions: nếu kết quả locale, parent, reload hay ngoại lệ không đúng, chương trình ném `AssertionError` thay vì âm thầm báo PASS.

### 6.2. Vì sao getLocale() trả vi chứ không phải vi-VN?

Target là `vi-VN`, nhưng không có `messages_vi_VN.txt`. `DiskControl.newBundle` trả `null` cho candidate ấy, cho thuật toán tiếp tục tìm `messages_vi.txt`. Vì vậy bundle được chọn có locale `vi`, và:

~~~text
resolved-locale=vi
~~~

**`Locale yêu cầu` khác `Locale tìm thấy`.** Một ứng dụng ghi log hoặc hiển thị trạng thái locale phải hiểu khác biệt này.

### 6.3. Vì sao key shared đọc được trong vi?

File `messages_vi.txt` chỉ có `greeting`. File root `messages.txt` có `shared`. `ResourceBundle.getBundle` tạo parent chain, vì vậy:

~~~text
vi-parent=from-root
~~~

Đó là **fallback key đến parent**, không phải việc `DiskControl.getFallbackLocale` đổi sang default locale của JVM. Hai cơ chế khác nhau.

### 6.4. Vì sao fr-FR lấy được Hello?

Vì có root `messages.txt` nên ngay cả khi không có `messages_fr_FR.txt` hoặc `messages_fr.txt`, loader có thể sử dụng root. Demo đã tắt default-locale fallback bằng `getFallbackLocale(...)=null`; **không tắt root candidate**.

### 6.5. Vì sao sửa file vi rồi getBundle lại thấy giá trị mới?

`DiskControl.getTimeToLive` trả `TTL_DONT_CACHE`. Lời gọi `ResourceBundle.getBundle` mới nạp các source từ disk thay vì chỉ trả cached bundle cũ:

~~~text
updated=Chào mới
~~~

**Đừng nhầm**: biến `vi` được lấy trước khi sửa file vẫn giữ snapshot `Xin chào`. Để thấy nội dung mới, ví dụ tạo biến `updated` qua một lần `getBundle` tiếp theo.

Với ứng dụng thật truy cập translation hàng nghìn lần mỗi giây, nên chọn cache/TTL phù hợp thay vì tắt cache vô điều kiện.

### 6.6. Vì sao missing key ném exception?

`updated.getString("not-found")` không có key ở bundle `vi` và root. API ném `MissingResourceException`. Demo bắt **đúng exception được mong đợi** và in:

~~~text
unknown-key=MissingResourceException
~~~

Không nên dùng `catch (Exception)` để thay mọi lỗi bằng chuỗi rỗng, vì có thể che giấu lỗi I/O, lỗi parser hoặc key thiếu trong triển khai. Trong UI production, có thể dùng một chính sách hiển thị placeholder rõ và logging/metrics phù hợp.

## 7. Đọc dữ liệu ngoài classpath một cách an toàn

Trong ví dụ, file được tạo theo naming convention chuẩn:

~~~text
tmp-directory/
└── demo/
    ├── messages.txt
    ├── messages_vi.txt
    └── messages_en.txt
~~~

`toBundleName(baseName, locale)` xây tên bản dịch từ baseName và locale candidate. `toResourceName(..., "txt")` biến dấu chấm của package thành separator và thêm extension `.txt`. `Files.newBufferedReader(path, StandardCharsets.UTF_8)` mở file **với charset rõ ràng**, `Properties.load(Reader)` đọc cú pháp key-value rồi chuyển vào `DataBundle`.

### 7.1. UTF-8 và Properties

`Properties.load(Reader)` xử lý **chuỗi ký tự đã giải mã** từ `Reader`. Vì demo dùng `Files.newBufferedReader(..., UTF_8)`, giá trị `Xin chào` được đọc đúng trên JDK 17+ mà không phụ thuộc default charset.

Đừng nhầm với overload `Properties.load(InputStream)`, vốn có quy tắc encoding khác (ISO-8859-1 theo contract). Nếu bạn có byte UTF-8 và muốn dùng `Properties` như một parser, hãy dùng `Reader` với `StandardCharsets.UTF_8` để hành vi có chủ đích.

Tuy ví dụ đặt extension `.txt`, nội dung vẫn dùng grammar của `Properties`; không gọi đây là một JSON parser. Nếu nguồn là JSON, dùng parser JSON an toàn, có kiểm tra schema, rồi đưa `Map` kết quả vào cùng `DataBundle`. Không tự viết parser JSON bằng `String.split(...)` cho dữ liệu có escape/Unicode phức tạp.

### 7.2. Whitelist và path traversal

Demo chỉ cho phép đúng base name `"demo.messages"` và format `"app.utf8txt"`. Nó còn resolve + normalize đường dẫn rồi kiểm tra `file.startsWith(directory)` để tránh việc tạo path `..` vượt ra ngoài thư mục cấu hình.

**Giới hạn của kiểm tra minh họa:** `Path.normalize()/startsWith()` là kiểm tra cú pháp, **không tự chống symbolic-link escape, race condition hoặc thay đổi filesystem giữa kiểm tra và mở file**. Ở production, chỉ chấp nhận directory/filename từ cấu hình tin cậy, quản lý quyền file, không cho attacker thay symlink, cân nhắc `toRealPath`/secure-directory operations nếu threat model đòi hỏi.

Không cho người dùng truyền một baseName hay file path tùy ý từ HTTP request vào loader rồi truy cập filesystem theo nguyên trạng. Mặc dù ResourceBundle vốn dành cho localization, loader tùy biến là **mã có quyền I/O thực sự** trong tiến trình.

### 7.3. Xử lý file thiếu và file lỗi khác nhau

- **Không có bundle cho candidate:** `newBundle` trả `null` để thuật toán tiếp tục tìm candidate khác.
- **Có file nhưng đọc lỗi hoặc format không hợp lệ:** về thiết kế, cần báo lỗi rõ (ví dụ `IOException` từ `newBundle`), thu diagnostics/metrics và tránh âm thầm coi dữ liệu hỏng là một bản dịch hợp lệ.
- **Không có bundle nào kể cả root:** `ResourceBundle.getBundle(...)` có thể ném `MissingResourceException`.
- **Có bundle nhưng thiếu key cả ở parent:** `getString(...)` ném `MissingResourceException`.

Khi tích hợp I/O từ database/network, phải quyết định nếu nguồn bị outage thì fail-fast, phục vụ snapshot cũ (*stale-on-error*) hay fallback có kiểm soát. API ResourceBundle không tự quyết định SLA, retry hay circuit breaker thay ứng dụng.

## 8. Cache, refresh và chi phí của nguồn tùy biến

### 8.1. Default caching

`ResourceBundle.getBundle` thường cache bundle instances theo baseName, locale, class loader/module context và các quy tắc tương ứng. Nếu external source thay đổi, **việc gọi lại getBundle không nhất thiết đọc file mới** khi cache mặc định còn hợp lệ.

Các cách kiểm soát:

- `getTimeToLive`: đặt TTL. `TTL_NO_EXPIRATION_CONTROL` là không đặt hạn hữu hạn; `TTL_DONT_CACHE` là không cache.
- `needsReload`: cho biết bundle cần tải lại khi TTL đã hết, ví dụ dựa trên file last-modified hoặc resource version.
- `ResourceBundle.clearCache()` / overload có `ClassLoader`: xóa cache trong phạm vi được mô tả bởi API; tránh xem đây là thao tác cập nhật riêng một key.
- **Cache riêng ở repository/service**: hữu ích cho DB/HTTP với batch fetch, asynchronous refresh, circuit breaker và metric.

Trong production, `TTL_DONT_CACHE` có thể biến **mỗi lần lấy bundle** thành nhiều lượt truy cập disk/DB/network cho các candidate locales. Nếu ứng dụng gọi `getBundle` cho từng UI label, chi phí càng đáng chú ý. Tổ chức một nơi lấy/cached bundle theo request/UI view có thể hữu ích, nhưng phải có cơ chế invalidation phù hợp.

### 8.2. getTimeToLive dương không đồng nghĩa reload mỗi lần hết hạn

Khi một cached bundle hết TTL, hệ thống có thể gọi `needsReload(...)` để quyết định source có thay đổi không. Nếu không cần reload, cache có thể tiếp tục dùng bundle cũ theo contract. Vì vậy nếu dữ liệu lấy từ HTTP/DB, `needsReload` phải dùng tiêu chí thay đổi **thực sự đáng tin** (version, ETag, lastModified phù hợp), thay vì luôn giả định “TTL hết = data mới”.

Phải kiểm thử trạng thái **file thiếu**, **file mới xuất hiện**, **file bị xóa**, **cập nhật đồng thời** và **negative caching**. ResourceBundle có thể cache cả dấu hiệu “bundle không tồn tại” theo quy tắc TTL; ví dụ dữ liệu vừa được dịch mới có thể không xuất hiện ngay nếu chưa hết hạn cache.

### 8.3. Thread safety và tính nguyên tử của snapshot

`ResourceBundle` có thể được truy cập đồng thời. `DataBundle` trong demo dùng `Map.copyOf` để giữ data bất biến sau khi tạo. `DiskControl` giữ `Path` bất biến và không lưu trạng thái mutable giữa các lần callback nên phù hợp với truy cập đồng thời ở mức ví dụ.

**Hợp đồng quan trọng:** nếu `Control` của bạn có fields mutable như HTTP client state, cache Maps hoặc counters, implementation phải thread-safe. API `ResourceBundle.getBundle` **không đồng bộ hóa mọi lời gọi callback của custom Control** cho bạn.

Với database/HTTP, hãy tạo snapshot nhất quán: không để một bundle load nửa dữ liệu phiên bản A, nửa phiên bản B. Dùng versioned snapshot, transaction phù hợp hoặc atomic replacement. Nếu reload thất bại, không thay bản dịch tốt trước đó bằng Map rỗng trừ khi có chính sách rõ ràng.

## 9. Ranh giới lớn từ Java 9+: named modules không dùng Control như classpath

**Điểm rất quan trọng khi học API này ở Java hiện đại:**

`ResourceBundle.Control` vẫn được hỗ trợ **cho caller chạy trong unnamed module/classpath**, như ví dụ `CustomBundleDemo` ở trên. Nhưng khi **caller thuộc named module**, các overload `ResourceBundle.getBundle(..., ResourceBundle.Control)` **không được hỗ trợ** và có thể ném `UnsupportedOperationException`. Không chuyển nguyên ví dụ Control vào `module-info.java` và giả định nó sẽ hoạt động.

Đối với named modules, Java cung cấp **`java.util.spi.ResourceBundleProvider`**. Đây không phải một API lỗi thời thay cho ResourceBundle; đó là cách mở rộng đúng khi dùng JPMS.

| Mục | Unnamed module / classpath | Named module |
| --- | --- | --- |
| Nguồn tùy biến | `ResourceBundle.Control.newBundle` | `ResourceBundleProvider.getBundle` |
| Chọn địa điểm tìm | `getFormats`/`toBundleName`/`newBundle` | Code provider hoặc `AbstractResourceBundleProvider` |
| Công bố loader | Truyền `control` vào `getBundle` | `module-info.java` dùng `uses` và `provides` |
| Có thể đọc file/DB/API tùy biến? | Có, do Control triển khai | Có, do provider triển khai |
| Cache/fallback | TTL/callbacks của Control | Thiết kế theo hợp đồng provider và ResourceBundle được dùng |
| Tránh nhầm lẫn | Không dùng Control overload trong caller named module | Không dùng `ResourceBundleControlProvider` để thay `ResourceBundleProvider` |

`ResourceBundleControlProvider` là một SPI khác, dùng để cung cấp Control cho một số `getBundle` overload không truyền Control ở ứng dụng classpath; **nó bị bỏ qua trong named modules**. Đừng nhầm hai interfaces này.

## 10. Ví dụ named module hoàn chỉnh với ResourceBundleProvider

Ví dụ này sử dụng một **provider in-memory** để tập trung vào đăng ký service và lookup trong named module. Sau đó bạn có thể thay phần xây `ListResourceBundle` bằng code đọc từ file/DB; xem mục 11.

Cấu trúc dự án:

~~~text
module-demo/
└── src/
    └── app.i18n/
        ├── module-info.java
        └── demo/
            ├── Main.java
            ├── spi/
            │   └── MessagesProvider.java
            └── internal/
                └── EnvMessagesProvider.java
~~~

### 10.1. module-info.java

Tệp `src/app.i18n/module-info.java`:

~~~java
module app.i18n {
    uses demo.spi.MessagesProvider;
    provides demo.spi.MessagesProvider with demo.internal.EnvMessagesProvider;
}
~~~

`uses` chỉ ra caller module tiêu thụ service, `provides` đăng ký implementation. Ở đây cả consumer và provider ở **cùng named module** cho ví dụ đơn giản. Trong ứng dụng lớn có thể tách module định nghĩa SPI, provider module và consumer module với `requires`/visibility phù hợp.

### 10.2. Tạo SPI có tên theo convention

Tệp `src/app.i18n/demo/spi/MessagesProvider.java`:

~~~java
package demo.spi;

public interface MessagesProvider extends java.util.spi.ResourceBundleProvider {}
~~~

Theo contract `ResourceBundleProvider`, khi base name là `demo.Messages`, kiểu SPI được mong đợi có tên `demo.spi.MessagesProvider` — **package của base name + ".spi." + tên đơn giản + "Provider"**. Nên tuân thủ đúng tên này, không đặt service interface tùy ý rồi kỳ vọng `ResourceBundle.getBundle` tự tìm thấy.

### 10.3. Cung cấp ResourceBundle bằng provider

Tệp `src/app.i18n/demo/internal/EnvMessagesProvider.java`:

~~~java
package demo.internal;

import demo.spi.MessagesProvider;
import java.util.*;

public final class EnvMessagesProvider implements MessagesProvider {
    public ResourceBundle getBundle(String baseName, Locale locale) {
        if (!"demo.Messages".equals(baseName)) return null;

        if (Locale.forLanguageTag("vi").equals(locale)) {
            return new ListResourceBundle() {
                protected Object[][] getContents() {
                    return new Object[][]{{"greeting", "Xin chào"}};
                }
            };
        }

        if (Locale.ROOT.equals(locale)) {
            return new ListResourceBundle() {
                protected Object[][] getContents() {
                    return new Object[][]{{"greeting", "Hello"}};
                }
            };
        }
        return null;
    }
}
~~~

Provider trả `null` cho locale candidate nó không cung cấp; ResourceBundle lookup có thể tiếp tục với candidates khác. Class được đăng ký trong `module-info.java`, không cần caller tự gọi constructor.

Ví dụ provider trả một `ListResourceBundle` nhỏ; **đây không phải loader đọc file ngoài**. Mục tiêu của ví dụ thứ hai là chứng minh cấu hình JPMS thay vì cố sử dụng `Control` sai môi trường. Để đưa dữ liệu từ nguồn tùy biến thật, thay nguồn của `getContents` bằng repository snapshot đã kiểm soát, hoặc trả về `DataBundle` phù hợp trong provider.

### 10.4. Caller dùng getBundle mà không truyền Control

Tệp `src/app.i18n/demo/Main.java`:

~~~java
package demo;

import java.util.*;

public final class Main {
    public static void main(String[] args) {
        ResourceBundle vi = ResourceBundle.getBundle("demo.Messages",
                Locale.forLanguageTag("vi-VN"));
        System.out.println("named-vi=" + vi.getString("greeting"));

        ResourceBundle fr = ResourceBundle.getBundle("demo.Messages",
                Locale.forLanguageTag("fr-FR"));
        System.out.println("named-fr-root=" + fr.getString("greeting"));
    }
}
~~~

Các class trên **chạy được** trên Java 17+ và không cần dependency ngoài. Khác với ví dụ `CustomBundleDemo`, caller này **không truyền `ResourceBundle.Control`**.

### 10.5. Biên dịch và chạy named module

Đứng tại thư mục `module-demo`.

Linux/macOS Bash:

~~~bash
mkdir -p out
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
~~~

Sau đó chạy `javac` với module source path và chỉ rõ cả bốn files:

~~~bash
javac -encoding UTF-8 --release 17 -d out --module-source-path src src/app.i18n/module-info.java src/app.i18n/demo/spi/MessagesProvider.java src/app.i18n/demo/internal/EnvMessagesProvider.java src/app.i18n/demo/Main.java
java --module-path out -m app.i18n/demo.Main
~~~

**Stdout chính xác**, đã được biên dịch/chạy trên OpenJDK 24 với `--release 17`:

~~~text
named-vi=Xin chào
named-fr-root=Hello
~~~

Caller yêu cầu `vi-VN` nhưng provider chỉ cung cấp `vi` và `ROOT`, nên nhận `Xin chào`. Caller yêu cầu `fr-FR` nhưng không có tiếng Pháp, nên rơi về root `Hello`.

**Quan trọng:** ví dụ này dùng provider để bảo đảm tên service, `uses`/`provides` và lookup đúng trong JPMS. Nếu dự án hiện đang chạy trên classpath, không bắt buộc phải chuyển sang named module chỉ để đọc external translation; lựa chọn dựa trên kiến trúc triển khai thực tế.

## 11. Đưa database, JSON hoặc API vào bundle

Khi thay nguồn đĩa bằng nguồn khác, phần giao diện `ResourceBundle` không thay đổi. Có thể hình dung pipeline:

~~~text
Locale + baseName
      |
      v
Custom Control (classpath) hoặc ResourceBundleProvider (module)
      |
      v
Repository.load(locale)
      |
      +--> file JSON/XML
      +--> database query
      +--> configuration service/HTTP API
      +--> in-memory snapshot
      |
      v
Validate schema + normalize data + immutable Map
      |
      v
DataBundle -> getString(key)
~~~

### 11.1. Database

Một repository có thể truy vấn bảng:

| bundle_name | locale_tag | key | value | version |
| --- | --- | --- | --- | --- |
| demo.messages | vi | greeting | Xin chào | 7 |
| demo.messages | en | greeting | Hi | 4 |
| demo.messages | root | shared | from-root | 2 |

Đây là **bảng minh họa schema**, không cần tạo database để chạy demo.

Nên dùng **parameterized queries**, connection pool, timeout, batch fetch toàn bộ locale snapshot và transaction consistency; không query database **mỗi lần** gọi `handleGetObject`. Nếu `handleGetObject` có side effects hoặc làm I/O, một thao tác lấy key có thể gây nhiều roundtrips và khó kiểm soát độ trễ.

Thực hành tốt: provider/control lấy dữ liệu một lần theo baseName + candidate locale, tạo **Map snapshot** rồi đưa vào `DataBundle`. Với nhiều request đồng thời cần bảo đảm cache và snapshot thread-safe.

### 11.2. JSON/XML

Khi đọc JSON hay XML, dùng parser phù hợp và bảo vệ trước dữ liệu không tin cậy, giới hạn kích thước file, depth và số key. Parser XML cần cấu hình **ngăn external entity/XXE** theo API parser được chọn. Dùng `Properties.loadFromXML` cũng là lựa chọn có format riêng khi nguồn là XML properties đúng định dạng được hỗ trợ.

Tuy nhiên **không được ép JSON tùy ý vào `Properties.load(Reader)`** như trong demo: code đó chỉ hiểu grammar properties. Sau parse, chuyển key/value thành Map và kiểm tra tất cả key là string, value có kiểu đúng và không rỗng nếu nghiệp vụ quy định.

### 11.3. HTTP/CMS

Remote service cần:

- Connection/read timeouts; không để một prompt UI bị block vô hạn do network.
- Cache version/ETag; TTL và stale-on-error policy rõ ràng.
- Retry có giới hạn và backoff; không nhân request vô hạn khi lỗi.
- TLS/certificate validation, authentication, secrets handling, authorization.
- Bảo vệ dữ liệu translated text trước injection ở bước **rendering** (HTML, SQL, log format), vì nội dung dịch cũng có thể do nguồn ngoài cung cấp.
- Versioned snapshots để tránh nửa nội dung locale version A và nửa version B.

Nếu không cần giao diện `ResourceBundle`, một typed localization service riêng cũng có thể phù hợp hơn. Không buộc mọi nguồn dữ liệu động phải đi qua `ResourceBundle` bằng mọi giá.

## 12. Những điểm tinh tế khi thiết kế fallback

### 12.1. Fallback locale không giống parent fallback

Trong demo chính, `getFallbackLocale(...) == null` nghĩa **không thử locale mặc định của JVM** nếu target không tìm được. Nhưng root `messages.txt` vẫn có thể tham gia candidate chain, và key `shared` vẫn đến từ parent bundle.

Nếu muốn chính sách “thiếu tiếng Việt thì hiện tiếng Anh” thay vì root, có thể thiết kế fallback riêng, nhưng phải quyết định **ở cấp bundle** hay **ở cấp key**. Tránh việc mỗi màn hình/locale ngầm dùng một logic khác nhau mà người dùng không thể dự đoán.

### 12.2. Missing locale và missing key là hai loại lỗi

- **Missing locale variant:** `newBundle` trả `null` cho candidate ấy; Java thử candidate khác.
- **Missing key:** bundle tìm thấy nhưng key không tồn tại; Java thử parent keys rồi ném `MissingResourceException` nếu không tìm được.
- **Missing all bundles:** `ResourceBundle.getBundle` ném `MissingResourceException` ở factory step.

Đừng kiểm tra `getLocale() == requestedLocale` như điều kiện thành công tuyệt đối, vì một fallback hợp lệ có thể trả locale cha. Với nội dung yêu cầu đúng ngôn ngữ không được fallback, hãy xây policy kiểm tra `getLocale()` có nằm trong tập locales được cho phép hay không.

### 12.3. Mỗi key có thể đến từ nhiều nguồn trong parent chain

Một bundle `vi` chỉ override `greeting`, còn `shared` đến từ root. Đây là thiết kế phổ biến giúp giảm trùng lặp chuỗi dịch, nhưng có thể khiến UI hiển thị **trộn ngôn ngữ** nếu thiếu keys. Trong production, nên có kiểm thử completeness per locale hoặc cảnh báo khi fallback dùng cho key user-facing quan trọng.

### 12.4. Key enumeration có tính cả parent

Nếu tự subclass `ResourceBundle` mà chỉ liệt kê Map cục bộ trong `getKeys()`, các chương trình gọi `getKeys` hoặc `keySet` có thể bỏ sót key được kế thừa. Mẫu dùng `getKeys() = Collections.enumeration(keySet())` kết hợp override `handleKeySet()` như `DataBundle` sẽ bao gồm parent keys theo contract.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách kiểm tra/sửa |
| --- | --- | --- |
| `MissingResourceException` dù file tồn tại | Sai baseName/locale/path hoặc cấu hình loader | In/tracing tên resource từ `toBundleName/toResourceName`, kiểm tra actual directory |
| Bundle không thấy file ngoài JAR | Loader mặc định chỉ tìm classpath/module resources | Dùng Control.newBundle (classpath) hoặc provider (module) |
| `Control` ném `UnsupportedOperationException` | Gọi overload có Control từ **named module** | Chuyển sang `ResourceBundleProvider` và `uses/provides` |
| File tiếng Việt bị lỗi encoding | Dùng sai overload parser hoặc charset không xác định | `Files.newBufferedReader(..., UTF_8)` + `Properties.load(Reader)` |
| Sau khi sửa file vẫn đọc text cũ | ResourceBundle cache còn hiệu lực hoặc instance cũ được giữ | Xem TTL/needsReload/clearCache; lấy instance mới |
| Thay đổi file mà mỗi request chậm | `TTL_DONT_CACHE` trong production, quá nhiều I/O | Thiết kế TTL hợp lý và cache snapshots |
| Dữ liệu tiếng Pháp nhận tiếng Anh/root | Fallback/candidate policy cho phép | Kiểm tra `getLocale()`, giới hạn fallback theo nghiệp vụ |
| Key thiếu dù locale hợp lệ | Key vắng mặt cả trong local và parent | Báo `MissingResourceException` đúng; completeness tests |
| `getKeys()` thiếu parent keys | Subclass chỉ duyệt Map local | Dùng `keySet()` kết hợp `handleKeySet()` như ví dụ |
| JSON loader không đọc được file | Dùng `Properties.load` cho JSON không cùng grammar | Dùng JSON parser đúng |
| Dữ liệu hiện ngôn ngữ bất nhất giữa requests | Nguồn thay đổi nhiều lần hoặc cache snapshot không nhất quán | Versioning, atomic snapshot, cache update đồng bộ |
| Hai processor/service ghi translation trùng key | Conflict trong dữ liệu nguồn | Validation unique keys và quy tắc precedence |
| `newBundle` làm treo UI | I/O remote/blocking trong bundle lookup | Timeout, caching, prefetch và asynchronous refresh |
| Tên đường dẫn vượt thư mục cho phép | BaseName/locale/path bị xây từ dữ liệu không tin cậy | Whitelist, resolve/normalize, filesystem permissions, symlink rules |
| Test pass trên máy dev nhưng fail trong CI | Mặc định locale hoặc file path khác | Temp directory, explicit Locale, tắt default fallback trong fixture |
| Named module không thấy provider | Sai SPI naming convention, thiếu `uses`/`provides` | Kiểm tra `module-info.java`, service type name và module path |

## 14. Checklist kiểm thử ResourceBundle từ nguồn tùy biến

Một test tốt không chỉ kiểm tra một `getString` thành công:

1. **Locale gần nhất:** target `vi-VN` chọn `vi` khi không có `vi_VN`.
2. **Parent fallback:** key không có trong `vi` lấy được từ root.
3. **Không có locale cụ thể:** `fr-FR` rơi về root nếu được phép.
4. **No default-locale fallback:** dùng `getFallbackLocale(...)=null` để test không phụ thuộc máy CI.
5. **Hot update:** thay dữ liệu và assert một lần `getBundle` mới thấy cập nhật theo TTL.
6. **Old snapshot:** instance bundle lấy trước cập nhật không nhất thiết tự đổi.
7. **Missing key:** xác nhận `MissingResourceException`; không âm thầm trả `""`.
8. **Missing all resources:** xác nhận factory ném `MissingResourceException` khi không có root/locale phù hợp.
9. **Unicode UTF-8:** ký tự tiếng Việt và dấu hiển thị đúng.
10. **Thread safety:** nhiều threads lookup cùng snapshot không gây data race hoặc Map bị thay ngầm.
11. **Source outage:** file/DB/HTTP unavailable, timeout, retry và stale/fail policy rõ.
12. **JPMS smoke test:** compile/run named module và service provider thay vì giả định Control luôn dùng được.
13. **Security:** đường dẫn, giới hạn số key/kích thước, schema và quyền file.
14. **Performance:** đo lượng I/O thực tế khi cache hết TTL.

Trong demo chính, các assertions tự động kiểm tra mục (1)–(5), (7) và một số kết quả liên quan; bài named module kiểm tra cơ chế (12). Những mục còn lại là test mở rộng cho hệ thống thực, không ngầm khẳng định đã được demo kiểm tra toàn bộ.

## 15. Câu hỏi tự đánh giá

**Câu 1.** Tại sao không đơn giản gọi `ResourceBundle.getBundle(...)` mặc định để đọc file trong thư mục cấu hình ngoài JAR?

**Đáp án:** Loader mặc định tìm resource bundle class/properties theo classpath/module search strategy; nó không tự biết một thư mục ngoài, tên file và định dạng tùy biến của bạn. Cần tích hợp loader hợp lệ hoặc repository/provider.

**Câu 2.** `ResourceBundle.Control.newBundle` trả `null` có luôn nghĩa ứng dụng lỗi không?

**Đáp án:** Không. Nó thường có nghĩa bundle **không tồn tại cho một candidate locale/format**, cho phép Java thử locale khác. Lỗi nguồn hiện hữu nhưng bị hỏng nên được phân biệt rõ.

**Câu 3.** `getFallbackLocale(...) == null` có khiến `vi-VN` không dùng được `vi` và root nữa không?

**Đáp án:** Không. Nó tắt thử **default JVM locale**, không tắt candidate/parent chain.

**Câu 4.** Vì sao `vi.getString("shared")` trả `from-root`?

**Đáp án:** `vi` chỉ có key `greeting`, còn root có `shared`. Khi key không tìm thấy trong locale bundle, ResourceBundle tìm đến parent.

**Câu 5.** `getBundle` đã trả một bundle, vì sao `getLocale()` có thể là `vi` trong khi yêu cầu `vi-VN`?

**Đáp án:** Vì không có bundle cụ thể `vi-VN`, nên chọn candidate `vi`; `getLocale()` cho biết locale **thực sự được chọn**.

**Câu 6.** Vì sao trong demo cập nhật file xong phải gọi `getBundle` lần nữa?

**Đáp án:** Bundle cũ là snapshot bất biến; `TTL_DONT_CACHE` khiến lần lookup mới đọc file mới, không sửa instance đã có.

**Câu 7.** Tại sao không dùng `TTL_DONT_CACHE` trong mọi ứng dụng dịch từ database?

**Đáp án:** Mỗi lần lấy bundle có thể gây nhiều database queries/remote calls, tạo latency và tải. Production nên có caching và refresh phù hợp.

**Câu 8.** Ứng dụng đã chuyển sang JPMS named module có thể tiếp tục gọi `getBundle(baseName, locale, control)` không?

**Đáp án:** Không. Các overload có `ResourceBundle.Control` không hỗ trợ caller named module; dùng `ResourceBundleProvider` với service registration.

**Câu 9.** `ResourceBundleProvider` thay thế việc dùng `ResourceBundle` hoàn toàn phải không?

**Đáp án:** Không. Nó là **cơ chế cung cấp ResourceBundle** cho modular lookup; consumer vẫn gọi `ResourceBundle.getBundle(...)` và `getString(...)`.

**Câu 10.** Vì sao `Properties.load(InputStream)` không tương đương `Properties.load(Reader)` với file UTF-8?

**Đáp án:** Hai overload có quy tắc diễn giải bytes khác nhau. Để kiểm soát UTF-8, demo tạo `Reader` từ `Files.newBufferedReader(..., StandardCharsets.UTF_8)` rồi gọi `load(Reader)`.

### Bài tập thực hành

1. Thêm file `messages_vi_VN.txt` với `greeting=Chào Việt Nam`; kiểm tra `getLocale()==vi-VN` khi target `vi-VN`.
2. Bỏ file root; yêu cầu `fr-FR` và kiểm tra `MissingResourceException` (giữ `getFallbackLocale==null`).
3. Thêm key `onlyEn` trong `messages_en.txt`; xác nhận `vi` **không** đọc được key này nếu không được fallback sang default locale.
4. Chuyển `TTL_DONT_CACHE` thành TTL dương và triển khai `needsReload` dựa trên file modification/version, viết test cập nhật không quá nhanh để tránh filesystem timestamp granularity.
5. Viết `JsonControl` hoặc named-module provider có repository đọc JSON đúng schema, tạo `DataBundle` bất biến.
6. Thêm test khi file UTF-8 chứa dấu tiếng Việt, escape `\u` và dòng tiếp nối theo cú pháp Properties.
7. Thử caller named module sử dụng overload có Control trong một bài test riêng; xác nhận `UnsupportedOperationException`, sau đó chuyển sang SPI hợp lệ.
8. Thiết kế bảng translation DB gồm base name, locale tag, key, text, version; xây test cho snapshot atomic và cache invalidation.

## 16. Tài liệu chính thức hiện hành

- [Java SE 26 — ResourceBundle](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ResourceBundle.html): lookup, locale fallback, parent chain, cache và ranh giới named modules.
- [Java SE 26 — ResourceBundle.Control](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ResourceBundle.Control.html): `newBundle`, `getFormats`, `getCandidateLocales`, `getTimeToLive`, `needsReload` và cách tùy biến.
- [Java SE 26 — ResourceBundleProvider](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/spi/ResourceBundleProvider.html): SPI cho named modules, naming convention và `uses`/`provides`.
- [Java SE 26 — AbstractResourceBundleProvider](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/spi/AbstractResourceBundleProvider.html): lớp cơ sở hỗ trợ provider cho resources ở module.
- [Java SE 26 — ListResourceBundle](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ListResourceBundle.html): lưu key/value trong Java class.
- [Java SE 26 — PropertyResourceBundle](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/PropertyResourceBundle.html): bundle dạng properties.
- [Java SE 26 — Properties](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Properties.html): `load(Reader)` và cú pháp key/value.
- [Java SE 26 — Locale](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.html): locale tags, language/region và default locale.
- [Java SE 26 — Files](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html): file I/O UTF-8, thư mục tạm và stream.
- [Java SE 26 — ServiceLoader](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html): cơ chế provider cho modules.

**Ghi nhớ:** `ResourceBundle` là **giao diện lấy thông điệp theo locale**, còn cách tạo bundle tùy nguồn có thể là `Control` trên **classpath/unnamed module** hoặc `ResourceBundleProvider` trong **named module**. Giữ parent/fallback rõ ràng, hiểu cache và snapshot, đọc text UTF-8 đúng charset, kiểm soát quyền nguồn, và kiểm thử các trường hợp missing key, refresh, locale fallback. Cả hai hướng trong bài đều sử dụng **API còn được hỗ trợ ở Java hiện đại**.

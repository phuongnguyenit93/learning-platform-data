# Thay cấu hình phụ thuộc implementation bằng hợp đồng được hỗ trợ (Java 11+)

## 1. Định hướng: kiểm chứng API, không chỉ kiểm chứng chương trình có chạy

Trong Java, một ứng dụng có thể biên dịch và chạy trên một phiên bản JVM, nhưng hỏng sau bản cập nhật JDK, đổi vendor, chuyển hệ điều hành hoặc cập nhật thư viện. Một nguồn rủi ro thường gặp là **phụ thuộc vào chi tiết triển khai** — class nội bộ, private field, đường dẫn runtime, tên provider, JVM flags không được cam kết, hoặc tên class implementation được lấy từ config.

Đề bài “**Thay cấu hình phụ thuộc implementation bằng hợp đồng được hỗ trợ**” yêu cầu một thay đổi mang tính kiến trúc: mô tả **hành vi cần thiết** trong cấu hình và mã của ứng dụng, rồi hiện thực hành vi đó thông qua **public API/SPI được tài liệu hóa**, thay vì cố định một cơ chế nội bộ chỉ đúng với một JDK.

Ví dụ:
- Cần encode Base64 → `java.util.Base64`, không dùng lớp `sun.misc` cũ.
- Cần kết nối HTTP với timeout cụ thể → `java.net.http.HttpClient`, không khởi tạo một class nội bộ của client.
- Cần SHA-256 → `MessageDigest.getInstance("SHA-256")`, không phụ thuộc nhà cung cấp `"SUN"` khi không có yêu cầu đặc biệt.
- Cần charset cho dữ liệu → `StandardCharsets.UTF_8`, không đoán platform default.
- Cần một provider/strategy tùy biến → public interface + `ServiceLoader`, không reflection vào private class.
- Cần xác nhận tương thích Java 11 → `javac --release 11`, `jdeps --jdk-internals`, `jdeprscan` và tests.

Các nguyên tắc này vẫn còn áp dụng trên JDK hiện đại. Bài không đề xuất các API nội bộ/legacy làm cách giải quyết lâu dài.

### Mục tiêu

Sau bài học, bạn sẽ có khả năng:
1. Phân loại một dependency là standard Java SE API, documented JDK API, supported SPI, vendor contract, hay implementation detail.
2. Tìm “ý định nghiệp vụ” phía sau một option hoặc tên class nội bộ.
3. Thiết kế schema cấu hình có tên/đơn vị/default/giới hạn và lỗi được công bố.
4. Thay code theo public factory/interface, không dựa vào tên class hoặc private field.
5. Kiểm thử positive/negative cases và khả năng chạy nhiều JDK/vận hành.
6. Hiểu giới hạn của các lệnh mở module (`--add-opens`/`--add-exports`) và `jdeps`.
7. Chạy được hai chương trình Java 11: public-contract configuration và ServiceLoader SPI.

## 2. Hợp đồng được hỗ trợ là gì?

**Contract** là giao ước về tên, kiểu, hành vi, lỗi, giới hạn, định dạng dữ liệu và phiên bản hỗ trợ do bên sở hữu API/config công bố. Từ “hỗ trợ” không có nghĩa implementation luôn giống nhau; nó nghĩa người dùng có thể dựa vào **hành vi được cam kết** trong phạm vi phiên bản/nhà cung cấp đã xác định.

| Loại | Ví dụ Java 11 | Bản chất cam kết |
| --- | --- | --- |
| Java SE standard API | `java.nio.file.Files`, `java.util.Base64`, `java.time.Duration` | Contract được chuẩn hóa ở Java SE và Javadoc |
| Public JDK API | `java.net.http.HttpClient`, `jdk.jfr` | Tài liệu công khai nêu chức năng; phải xác định runtime/module hỗ trợ |
| Standard SPI | `ServiceLoader`, Java Security provider framework | Interface và quy tắc provider discovery được công bố |
| Library API | Public API của một thư viện đang duy trì | Contract theo docs/version và support policy của thư viện |
| Application config | `http.connectTimeoutMillis=1500` | Đội ứng dụng sở hữu schema, validation, default và migration |
| Vendor-specific documented option | Một số JVM flags/setting hiệu năng | Có thể được hỗ trợ trong runtime/version đã nêu; không portable mặc định |
| Implementation private/internal | `jdk.internal.*`, private JDK fields | Không được coi là ứng dụng-facing compatibility contract |

**Không đánh giá chỉ bằng package prefix.** Một số `com.sun.*` là JDK-specific APIs có tài liệu; một số class `public` vẫn là internal hoặc không được export qua module boundary. Phải đọc API docs/module metadata và xác nhận scope. Ngược lại, code reflection được chạy thành công hôm nay không có nghĩa private fields được đảm bảo tồn tại ngày mai.

### 2.1. Cam kết về hành vi, không về concrete class

`HttpClient.newBuilder().build()` trả một `HttpClient` có những API và behavior được công bố. Concrete class mà một JDK chọn dùng không phải điều client code cần biết. Test nên xác nhận timeout, redirect policy hoặc response thực, không viết:

```java
// PHẢN VÍ DỤ - mã minh họa, phụ thuộc implementation:
boolean correct = client.getClass().getName()
        .equals("jdk.internal.net.http.HttpClientImpl");
```

Một bản cập nhật có thể thay tên class mà vẫn giữ nguyên contract, khiến test kiểu này thất bại không cần thiết.

### 2.2. API công khai cũng có giới hạn

Dùng public APIs không xóa được lỗi input hoặc môi trường: `IOException`, `NoSuchAlgorithmException`, `IllegalArgumentException`, `ServiceConfigurationError`, khác biệt provider/filesystem, network issues. Thiết kế đúng phải bám **preconditions, error behavior và documentation**. “Không phụ thuộc implementation” không đồng nghĩa “không cần testing”.

## 3. Những dấu hiệu của cấu hình dễ vỡ

| Dấu hiệu | Phụ thuộc gì? | Cách xác minh |
| --- | --- | --- |
| `impl.class=jdk.internal....` | Tên class private của JDK | Xác định public factory/interface thực sự cần |
| `Class.forName("sun....")` | Runtime implementation package | Tìm documented API/SPI |
| `Field.setAccessible(true)` vào Java core | Nội bộ/layout, module openness | Sử dụng getter/method public đúng mục tiêu |
| `--add-opens` không rõ lý do | Deep reflection vào internals | Rà dependency, owner và migration path |
| `--add-exports` | Truy cập package không được export bình thường | Thay bằng public API, coi flag là workaround |
| `digest.provider=SUN` | Provider cụ thể | Dùng JCA algorithm selection nếu policy cho phép |
| `sun.*`/`jdk.*` system property chưa được tài liệu hóa | Hidden implementation switch | Xác nhận hỗ trợ ở JDK/vendor target; tránh như app contract |
| `http.clientImpl=...` | Class network engine | `HttpClient` builder + public options |
| Test so `getClass().getName()` | Concrete factory result | Test output và semantics |
| Đường dẫn cố định vào `java.home` hoặc runtime JARs | Layout bản phân phối JDK | Dùng public resource/process/file API |
| Nhiều cờ `-XX` lấy từ diễn đàn cũ | Vendor/release-dependent tuning | Đọc docs của JVM, đo và rollback |

**Không phải mọi cờ `-XX` đều sai.** Một số là documented runtime options. Sai là biến các cờ/đường dẫn ấy thành yêu cầu portable cho mọi JVM mà không có support matrix.

### 3.1. Phụ thuộc ẩn ngoài imports

Không chỉ tìm `import sun.*`. Kiểm tra:
- Dynamic reflection, `MethodHandles.privateLookupIn`, private member access.
- Class name lưu trong properties/YAML/JSON/env var.
- Dependencies đã biên dịch, shaded/multi-release JARs.
- Build scripts/launcher config, Java agents, JNI/native code.
- `META-INF/services` và resource packaging.
- Vendor-specific security providers/keystores.
- Test assert internal implementation details.
- Cấu hình encoding/locale/timezone/OS paths mặc định.

Kết quả `jdeps` không thay thế việc tìm class names được xây động bằng string hoặc cấu hình.

## 4. Mô hình chuyển đổi: ý định → hợp đồng → implementation ẩn

```text
Cấu hình cũ (dễ vỡ)
  internal.class = jdk.internal...
  digest.provider = SUN
  timeout = 1500
  reflect.privateField = ...

              |
       Xác định nhu cầu
              |
              v

Cấu hình ứng dụng mới (ổn định về ý nghĩa)
  digest.algorithm = SHA-256
  storage.charset = UTF-8
  http.connectTimeoutMillis = 1500
  http.redirects = NEVER

              |
       Typed parsing/validation
              |
              v

API/SPI công khai
  MessageDigest.getInstance(algorithm)
  Files.* / StandardCharsets.UTF_8
  HttpClient.newBuilder()
  ServiceLoader<Formatter>
```

Hợp đồng phải đáp ứng:
- **Tên config diễn đạt hành vi**, không chỉ vị trí field/class.
- **Đơn vị và phạm vi** rõ: timeout connect khác request timeout; ms khác s.
- **Giá trị hợp lệ** được giới hạn, default công bố.
- **Lỗi có chính sách**: reject, fallback hay warning tùy rủi ro.
- **Versioning**: mô tả migration key cũ → mới.
- **Bảo mật**: không log credentials, không arbitrary class loading từ input không tin cậy.
- **Quan sát**: xác minh effective settings bằng API, không in private implementation class.

### 4.1. Ví dụ timeout

`http.timeout=1500` mơ hồ. Trong Java 11 `HttpClient`:
- `connectTimeout(Duration)`: timeout cho việc thiết lập kết nối.
- `HttpRequest.Builder.timeout(Duration)`: timeout dành cho một request.

Không tự coi connect timeout 1,5 giây là deadline cho mọi attempt/retry trong service. Nếu yêu cầu nghiệp vụ là tổng deadline thì cần một contract khác, có thời gian và cách hủy/retry phù hợp.

### 4.2. Config allowlist

Một schema có thể nhận đúng bốn khóa:

```properties
storage.charset=UTF-8
digest.algorithm=SHA-256
http.connectTimeoutMillis=1500
http.redirects=NEVER
```

Nếu đọc thêm `jdk.internal.http.impl=SomeImpl` từ input, chương trình có thể **từ chối** vì khóa ngoài contract. Đây là key giả định do bài tạo, **không khẳng định JVM có một system property thật như vậy**.

Với hệ thống cần nhiều phiên bản config, nên có schema version và deprecation window; đừng âm thầm bỏ key cũ rồi đổi hành vi không thông báo.

## 5. Những thay thế API nên ưu tiên

### 5.1. Base64

`sun.misc.BASE64Encoder` là ví dụ điển hình của phụ thuộc nội bộ không nên dùng. API công khai:

```java
String encoded = Base64.getUrlEncoder().withoutPadding()
        .encodeToString("Java 11".getBytes(StandardCharsets.UTF_8));
String decoded = new String(
        Base64.getUrlDecoder().decode(encoded),
        StandardCharsets.UTF_8);
```

Đoạn trên chỉ là **mảnh mã** trong phương thức, cần imports. `Base64` có Basic, URL-safe và MIME encoders. Chọn đúng **wire format**: thay một encoder cũ bằng URL-safe không padding có thể làm khác dữ liệu đã lưu, nên cần golden tests cho backward compatibility.

### 5.2. Files và charset

```java
String text = Files.readString(path, StandardCharsets.UTF_8);
Files.writeString(path, text, StandardCharsets.UTF_8);
```

Đây là mảnh mã với `Path path` và xử lý `IOException` phù hợp. `Files.readString/writeString` tồn tại từ Java 11. Không cần gọi lớp file system nội bộ hoặc đoán encoding từ OS.

**Không tuyên bố mọi API no-charset đều phụ thuộc platform.** Ví dụ `Files.newBufferedReader(Path)` trong Java 11 dùng UTF-8 theo contract. Quan trọng là xác định encoding theo **API cụ thể**, thay vì suy từ implementation hoặc default mọi nơi.

Nếu dữ liệu legacy được mã hóa bằng charset khác, phải xây migration đọc/ghi rõ ràng; việc chỉ đổi sang UTF-8 có thể làm dữ liệu cũ giải mã sai.

### 5.3. JCA và MessageDigest

```java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
byte[] result = digest.digest(
        "hello".getBytes(StandardCharsets.UTF_8));
```

`MessageDigest.getInstance("SHA-256")` sử dụng cơ chế security provider discovery được Java công bố. Không buộc `"SUN"` nếu không có yêu cầu compliance/hardware. SHA-256 là thuật toán chuẩn theo contract, dữ liệu digest không thay đổi vì concrete provider class khác.

Trong môi trường FIPS/HSM có thể cần provider cụ thể. Khi đó hãy dùng **public JCA API với provider được phê duyệt**, document version/registration/policy và fail closed khi không đáp ứng. “Portable” không phải lý do bỏ ràng buộc bảo mật.

**SHA-256 thuần không phải giải pháp password storage.** Demo chỉ kiểm chứng digest bytes của một test string.

### 5.4. HttpClient public builder

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofMillis(1500))
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();
```

Đây là mảnh mã cần imports. Không phụ thuộc lớp HTTP concrete, internal connection pools hay các private flags. Contract của HTTP/2 là **version preference**; nếu thật sự gửi request phải xem `HttpResponse.version()` để biết phiên bản được dùng, không dựa tên implementation.

### 5.5. String internals

Phụ thuộc vào private field `String.value` hoặc byte layout bên trong JDK không phải contract. Để lấy bytes theo encoding, dùng `String.getBytes(StandardCharsets.UTF_8)`. Để xử lý UTF-16 units, dùng `charAt` hoặc `toCharArray()`; để xử lý code points, dùng `codePoints()`.

`String.length()` trả số **UTF-16 code units**, không phải số Unicode code points. Thay internals bằng public API vẫn đòi hỏi hiểu đúng semantics Unicode.

## 6. SPI và ServiceLoader: mở rộng bằng interface

Khi cần thay thế implementation, một public **service interface** và `ServiceLoader` thường là công cụ đúng:
- Consumer chỉ import service API.
- Provider class triển khai interface và được đăng ký bằng resource hoặc JPMS module declaration.
- Không dùng `Class.forName` để đoán tên private JDK class trong business code.
- Provider discovery/instantiation theo contract `ServiceLoader`.
- Khi có nhiều providers, phải định nghĩa **selection policy** chứ không mặc nhiên tin thứ tự.

### 6.1. Ví dụ nhiều file runnable trên Java 11

Tạo:

```text
src/lesson/api/Formatter.java
src/lesson/api/ServiceConsumer.java
src/lesson/impl/UpperFormatter.java
out/META-INF/services/lesson.api.Formatter
```

**`src/lesson/api/Formatter.java`**

```java
package lesson.api;
public interface Formatter {
    String render(String value);
}
```

**`src/lesson/impl/UpperFormatter.java`**

```java
package lesson.impl;
import java.util.Locale;
import lesson.api.Formatter;
public final class UpperFormatter implements Formatter {
    public UpperFormatter() {}
    public String render(String value) {
        return value.toUpperCase(Locale.ROOT);
    }
}
```

**`src/lesson/api/ServiceConsumer.java`**

```java
package lesson.api;
import java.util.ServiceLoader;
public final class ServiceConsumer {
    public static void main(String[] args) {
        Formatter formatter = ServiceLoader.load(Formatter.class)
                .findFirst().orElseThrow(
                        () -> new IllegalStateException("No formatter provider"));
        System.out.println("spiResult=" + formatter.render("portable"));
        System.out.println("usesPublicInterface=true");
    }
}
```

**Nội dung `out/META-INF/services/lesson.api.Formatter`** (một dòng):

```text
lesson.impl.UpperFormatter
```

Lệnh **Unix/macOS shell** minh họa đặt metadata rồi biên dịch:

```bash
mkdir -p out/META-INF/services
printf 'lesson.impl.UpperFormatter\n' > out/META-INF/services/lesson.api.Formatter
javac -encoding UTF-8 --release 11 -d out \
  src/lesson/api/Formatter.java \
  src/lesson/api/ServiceConsumer.java \
  src/lesson/impl/UpperFormatter.java
java -cp out lesson.api.ServiceConsumer
```

Trên Windows dùng lệnh tạo file tương đương và chạy `javac` với các path phù hợp, không sao chép `mkdir -p` hay `printf` nếu dùng PowerShell.

**Stdout đã kiểm chứng trên JDK 24 với `--release 11`:**

```text
spiResult=PORTABLE
usesPublicInterface=true
```

`ServiceLoader.findFirst()` có trên Java 11. Trong production, khi có nhiều providers, `findFirst` không phải chính sách chọn provider business đủ an toàn. Hãy công bố id/capability và xử lý xung đột, provider errors, trust boundary.

**Lưu ý quan trọng:** lớp `lesson.impl.UpperFormatter` nằm trong `META-INF/services` không vi phạm nguyên tắc: đây là registration metadata **theo hợp đồng SPI**, do provider owner cung cấp. Điểm cần tránh là business code tự đoán tên **implementation private của JDK/framework** mà không có contract.

### 6.2. Named modules dùng uses/provides

Trong JPMS, service consumer module dùng `uses lesson.api.Formatter;`; provider module dùng `provides lesson.api.Formatter with lesson.impl.UpperFormatter;` cùng `requires` tới API module. Cần `exports` package API đúng mức.

Đây là **nguyên tắc module-info** chứ không phải file độc lập trong ví dụ classpath. Không trộn cơ chế resource classpath với named-module packaging mà không kiểm tra build.

### 6.3. Failure modes của SPI

`ServiceConfigurationError` có thể xảy ra khi provider class không load được, resource format sai, dependencies thiếu hoặc provider không hợp lệ. Nếu service bắt buộc, nên fail-fast với lỗi rõ. Nếu optional, có thể xác định documented fallback. Không che lỗi provider bằng cách bắt mọi `Throwable` rồi tiếp tục một cách im lặng.

## 7. Chương trình Java 11 chính: cấu hình theo hợp đồng

`SupportedContractDemo.java` minh họa:
- Load UTF-8 properties bằng `Files.newBufferedReader(path, UTF_8)` và `Properties.load(Reader)`.
- Chỉ nhận bốn keys có ý nghĩa công khai.
- Từ chối key nội bộ giả lập và timeout không hợp lệ.
- Map timeout và redirect policy sang `HttpClient` public builder.
- Dùng `MessageDigest` với thuật toán SHA-256 thay vì provider name.
- Round-trip Base64 URL-safe với UTF-8.
- Không gửi request ra Internet và xóa file config **tạm** sau test.

### 7.1. Mã nguồn SupportedContractDemo.java

```java
import java.io.IOException;
import java.io.Reader;
import java.net.http.HttpClient;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.Base64;
import java.util.Properties;
import java.util.Set;

public final class SupportedContractDemo {
    private static final Set<String> ALLOWED = Set.of(
            "storage.charset", "digest.algorithm",
            "http.connectTimeoutMillis", "http.redirects");

    private static final class Settings {
        final Charset charset;
        final String digestAlgorithm;
        final int connectTimeoutMillis;
        final HttpClient.Redirect redirects;

        Settings(Charset charset, String digestAlgorithm,
                 int connectTimeoutMillis, HttpClient.Redirect redirects) {
            this.charset = charset;
            this.digestAlgorithm = digestAlgorithm;
            this.connectTimeoutMillis = connectTimeoutMillis;
            this.redirects = redirects;
        }

        static Settings from(Properties properties) {
            if (!ALLOWED.containsAll(properties.stringPropertyNames())) {
                throw new IllegalArgumentException("Unknown config key");
            }
            if (!"UTF-8".equals(properties.getProperty("storage.charset"))) {
                throw new IllegalArgumentException("Unsupported charset policy");
            }
            if (!"SHA-256".equals(properties.getProperty("digest.algorithm"))) {
                throw new IllegalArgumentException("Unsupported digest policy");
            }
            String rawTimeout =
                    properties.getProperty("http.connectTimeoutMillis");
            int timeout;
            try {
                timeout = Integer.parseInt(rawTimeout);
            } catch (NumberFormatException e) {
                throw new IllegalArgumentException("Invalid timeout", e);
            }
            if (timeout < 1 || timeout > 60000) {
                throw new IllegalArgumentException("Timeout out of policy");
            }
            if (!"NEVER".equals(properties.getProperty("http.redirects"))) {
                throw new IllegalArgumentException("Unsupported redirect policy");
            }
            return new Settings(StandardCharsets.UTF_8, "SHA-256",
                    timeout, HttpClient.Redirect.NEVER);
        }
    }

    private static String hex(byte[] data) {
        StringBuilder result = new StringBuilder(data.length * 2);
        for (byte b : data) {
            int value = b & 0xff;
            result.append(Character.forDigit(value >>> 4, 16));
            result.append(Character.forDigit(value & 0x0f, 16));
        }
        return result.toString();
    }

    public static void main(String[] args) throws Exception {
        Path temporaryConfig =
                Files.createTempFile("supported-contract-", ".properties");
        try {
            String text = "storage.charset=UTF-8\n"
                    + "digest.algorithm=SHA-256\n"
                    + "http.connectTimeoutMillis=1500\n"
                    + "http.redirects=NEVER\n";
            Files.writeString(temporaryConfig, text, StandardCharsets.UTF_8);

            Properties properties = new Properties();
            try (Reader reader = Files.newBufferedReader(
                    temporaryConfig, StandardCharsets.UTF_8)) {
                properties.load(reader);
            }
            Settings settings = Settings.from(properties);

            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofMillis(
                            settings.connectTimeoutMillis))
                    .followRedirects(settings.redirects)
                    .build();

            MessageDigest digest =
                    MessageDigest.getInstance(settings.digestAlgorithm);
            String sha256 =
                    hex(digest.digest("hello".getBytes(settings.charset)));

            String sample = "Java 11 - UTF8";
            String encoded = Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(sample.getBytes(settings.charset));
            String decoded = new String(
                    Base64.getUrlDecoder().decode(encoded), settings.charset);

            Properties unknown = new Properties();
            unknown.putAll(properties);
            unknown.setProperty("jdk.internal.http.impl", "SomeImpl");
            boolean unknownImplKeyRejected = false;
            try {
                Settings.from(unknown);
            } catch (IllegalArgumentException expected) {
                unknownImplKeyRejected = true;
            }

            Properties invalid = new Properties();
            invalid.putAll(properties);
            invalid.setProperty("http.connectTimeoutMillis", "0");
            boolean invalidTimeoutRejected = false;
            try {
                Settings.from(invalid);
            } catch (IllegalArgumentException expected) {
                invalidTimeoutRejected = true;
            }

            System.out.println("charset=" + settings.charset.name());
            System.out.println("timeoutMillis=" +
                    client.connectTimeout().orElseThrow().toMillis());
            System.out.println("redirects=" + client.followRedirects());
            System.out.println("sha256Hello=" + sha256);
            System.out.println("base64RoundTrip=" + sample.equals(decoded));
            System.out.println("unknownImplKeyRejected=" +
                    unknownImplKeyRejected);
            System.out.println("invalidTimeoutRejected=" +
                    invalidTimeoutRejected);
            System.out.println("implementationClassPinned=false");
        } finally {
            Files.deleteIfExists(temporaryConfig);
        }
    }
}
```

### 7.2. Biên dịch và stdout

```bash
javac -encoding UTF-8 --release 11 SupportedContractDemo.java
java SupportedContractDemo
```

**Stdout thực tế, biên dịch mức Java 11 và chạy trên JDK 24:**

```text
charset=UTF-8
timeoutMillis=1500
redirects=NEVER
sha256Hello=2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824
base64RoundTrip=true
unknownImplKeyRejected=true
invalidTimeoutRejected=true
implementationClassPinned=false
```

### 7.3. Diễn giải chính xác

- `charset=UTF-8`: app chọn charset chuẩn thay vì đoán platform.
- `timeoutMillis=1500`: public `HttpClient.connectTimeout` phản ánh cấu hình; client đã tạo nhưng không gửi network request.
- `redirects=NEVER`: enum public giữ chính sách điều hướng.
- `sha256Hello=...`: digest SHA-256 deterministic của UTF-8 bytes `"hello"`; không test provider class name.
- `base64RoundTrip=true`: URL-safe Base64 encoder/decoder khôi phục đầu vào.
- `unknownImplKeyRejected=true`: schema từ chối khóa `jdk.internal.http.impl` **giả lập**, không khẳng định JVM có property này.
- `invalidTimeoutRejected=true`: policy của demo chặn timeout 0 ngoài khoảng 1–60.000 ms. Đây là **application policy**, không là contract chung về mọi timeout Java.
- `implementationClassPinned=false`: dòng output cố ý mô tả thiết kế demo; không phải công cụ quét code tự động.

Trong demo `Properties.load(Reader)` được cấp reader UTF-8. `Properties.load(InputStream)` có encoding semantics khác; không xem hai overload giống nhau với text Unicode. File config ở đây là **temp file** do demo tạo và xóa, không áp dụng cách xóa đó với config production.

### 7.4. Hạn chế phạm vi

Demo không thử TLS/network, không kiểm tra một file config có secrets, không xây schema migration, không thử nhiều JDK vendor và không chứng minh security/compliance. Dù toàn bộ output PASS, vẫn phải test môi trường triển khai thực tế.

## 8. Kiểm chứng API bằng các công cụ Java 11

### 8.1. Biên dịch với --release

```bash
javac -encoding UTF-8 --release 11 SupportedContractDemo.java
```

`--release 11` kiểm tra cả **source/target release và API surface** tương ứng, hạn chế trường hợp dùng API sau Java 11 mà không nhận ra. Chỉ `-source 11 -target 11` không tương đương vì chưa giới hạn API platform theo target release.

`--release 11` không đảm bảo dependency ngoài JDK tương thích runtime, provider được cài hoặc quyền filesystem đúng. Cần test runtime sau compile.

### 8.2. Phát hiện tham chiếu JDK internals

```bash
jdeps --jdk-internals my-application.jar
```

Lệnh tìm class-level dependencies tới JDK internal APIs. Với JAR nhiều release có thể cần `--multi-release 11`, kết hợp classpath/module path để resolver thấy dependencies.

Trong kiểm thử của bài:
- `jdeps --jdk-internals SupportedContractDemo.class` không phát hiện JDK internal references ở **main class được quét**.
- `jdeps --list-deps SupportedContractDemo.class` liệt kê các module `java.base` và `java.net.http`.
- Ví dụ SPI classpath test `jdeps --jdk-internals out` không thấy báo cáo internals.

Đây là kết quả **phân tích tĩnh trong phạm vi input đã đưa**. Nó không chứng minh mọi reflection từ string, JNI/native code, runtime config hay toàn bộ third-party libraries sạch.

### 8.3. Quét Java SE deprecated API

```bash
jdeprscan --release 11 my-application.jar
```

`jdeprscan` giúp xác định Java SE APIs deprecated trong compiled classes/JAR. Nó không phải scanner API nội bộ toàn diện, cũng không rà deprecated của third-party libraries. `@Deprecated` không tự động đồng nghĩa đã bị xóa hoặc không còn hoạt động trong target release; phải đọc docs và `forRemoval` khi có.

Ngược lại, một internal API không đánh dấu deprecated vẫn có thể **không được hỗ trợ** cho application.

### 8.4. CI và compatibility matrix

Một pipeline tốt có:
1. Compile cho Java 11 bằng `--release 11` hoặc build tool equivalent.
2. `jdeps --jdk-internals` trên artifact và dependencies phù hợp.
3. `jdeprscan`/deprecation review, cùng static search reflection/config.
4. Tests positive/negative của config schema.
5. Golden tests để bảo toàn wire formats/dữ liệu legacy.
6. Runtime smoke/integration tests trên JDK 11 mục tiêu và JDK hiện đại được hỗ trợ, theo vendor/OS/container.
7. Security tests (provider, credentials, TLS) và load tests khi thay timeout/GC/network.
8. Kiểm tra startup flags, module opens, support docs, changelog và rollback plan.

Không cần tuyên bố “mọi vendor/OS đều được hỗ trợ” nếu chưa kiểm thử chúng. Nên nêu **compatibility matrix có phạm vi** và test trên phạm vi đó.

## 9. Encapsulation và flags: tạm vượt ranh giới không phải contract

Từ JDK 9, module system áp dụng ranh giới package exports/opens. Những thư viện reflection vào non-public JDK fields có thể gặp vấn đề khi nâng JDK. Trên JDK 17+, JEP 403 đã mạnh hóa encapsulation mặc định cho nhiều JDK internals; deep reflection không được mở có thể ném `InaccessibleObjectException`.

- `--add-exports` cho phép truy cập bổ sung tới một package theo cơ chế export.
- `--add-opens` mở một package cho deep reflective access tới non-public members trong phạm vi chỉ định.
- Chúng có thể dùng **tạm thời** cho dependency chưa được nâng cấp, nhưng không biến internal class thành public supported API.
- `--illegal-access` từng là một tùy chọn migration cho JDK 9–16; **không còn hiệu lực giải quyết access trên JDK 17+**. Không giới thiệu như cách sửa hiện hành.

Một anti-pattern minh họa:

```java
// PHẢN VÍ DỤ — đoạn không độc lập, cố tình không dùng production:
Field backing = String.class.getDeclaredField("value");
backing.setAccessible(true);
Object bytes = backing.get("sample");
```

Không nên phụ thuộc layout private của `String`. Thay bằng public operation đúng mục tiêu: `getBytes(UTF_8)`, `toCharArray()`, `codePoints()`. Khi dùng `String.length()` nhớ nó đo UTF-16 code units, không trực tiếp là số Unicode code points.

Nếu bắt buộc dùng flag tạm:
- Nêu tên dependency gây yêu cầu.
- Mở đúng package/consumer cần thiết, không mở toàn bộ theo thói quen.
- Có owner/issue/deadline, test trên JDK hiện tại và version nâng kế tiếp.
- Lập kế hoạch nâng library hoặc loại access nội bộ.
- Không mô tả cờ là compatibility guarantee lâu dài.

## 10. Khi vendor-specific config là một lựa chọn hợp lệ

Không phải mọi dự án đều cần chạy trên mọi Java distribution. Có nhu cầu riêng như GC tuning, HSM/FIPS providers, hardware-accelerated crypto hay JVM diagnostics được vendor công bố.

Trong trường hợp đó:
1. Chỉ dùng documented flags/APIs trong runtime support matrix.
2. Tách vendor adapter hoặc deployment profile khỏi business code.
3. Version-gate các option, xác minh startup và effective settings.
4. Monitor CPU/latency/throughput/security, không áp dụng mù quáng.
5. Giữ rollback hoặc alternate supported implementation.
6. Không bỏ kiểm soát security provider nếu compliance yêu cầu.
7. Phân biệt “hỗ trợ trong JVM này” với “chuẩn Java SE”.

**Portable không phải từ chối mọi vendor feature; portable là minh bạch hợp đồng và phạm vi.**

## 11. Migration an toàn: giữ nghĩa, không chỉ giữ syntax

### 11.1. Tìm mọi nơi dùng key cũ

Ví dụ một cấu hình **giả định, không phải API thật**:

```properties
http.implementationClass=jdk.internal.example.Client
http.timeout=1500
digest.provider=SUN
```

Từ đây không biết `http.timeout` là connect hay request timeout, đơn vị ms hay s, và provider pin có yêu cầu bảo mật hay không.

Hướng thay:

```properties
http.connectTimeoutMillis=1500
http.redirects=NEVER
digest.algorithm=SHA-256
storage.charset=UTF-8
```

Trước khi triển khai, phải trả lời:
- Cấu hình cũ trong môi trường thực tế có behavior gì?
- Timeout mới có thay đổi scope/đơn vị không?
- Base64 alphabet/padding và text encoding có thay đổi dữ liệu/wire format không?
- Provider pin có liên quan FIPS/HSM không?
- Có consumer nào còn đọc key cũ?
- Một thay đổi có cần dual-read hoặc schema version không?

### 11.2. Quy trình từng bước

1. Inventory application/JAR/startup flags/config.
2. Xác định owner và contract thực của từng dependency.
3. Ghi expected behavior và negative cases.
4. Thiết kế schema với validation/error policy.
5. Thay bằng public API/SPI tại một adapter boundary.
6. Viết golden tests dữ liệu, API contract tests, integration tests.
7. Kiểm tra `jdeps` và runtime versions, scan reflection.
8. Triển khai staged/canary, theo dõi errors/latency.
9. Xóa key/flag workaround sau khi hết consumer, có rollback rõ.

**Không** đổi code và xoá key cũ mà không có test nếu cấu hình là dữ liệu lâu dài hoặc có hệ thống vận hành chưa cập nhật.

### 11.3. Fail-fast hay fallback?

Không có câu trả lời tuyệt đối:
- **Secret/crypto/TLS/cert/provider requirements:** thường ưu tiên fail closed khi thiếu chính sách bắt buộc; không tự hạ xuống thuật toán yếu.
- **Optional formatter/plugin:** có thể có fallback public được tài liệu hóa.
- **Timeout:** không nên silently thay `1500ms` thành timeout khác mà không có cảnh báo/approval.
- **Unknown key:** có thể reject để phát hiện lỗi sớm, hoặc log migration warning theo schema version; không chuyển raw unknown keys xuống implementation.

## 12. Triệu chứng và cách sửa

| Triệu chứng | Nguyên nhân thường gặp | Hành động |
| --- | --- | --- |
| `InaccessibleObjectException` sau nâng JDK | Reflection vào non-public JDK internals | Nâng library hoặc public API replacement; flags chỉ tạm |
| `IllegalAccessError` | Package không được export | Loại internal dependency |
| `ClassNotFoundException` tên impl từ config | Hardcoded implementation bị đổi/mất | Public interface/factory/SPI |
| `ServiceConfigurationError` | Sai resource provider hoặc thiếu dependency | Kiểm tra `META-INF/services`/modules/constructor |
| Provider `SUN` không tồn tại | Pin provider theo vendor | Algorithm selection theo JCA hoặc đúng compliance policy |
| `NoSuchAlgorithmException` | Algorithm không khả dụng | Dùng tên chuẩn, kiểm tra policy; tránh fallback nguy hiểm |
| Unicode bị lỗi sau migration | Encoding cũ/default charset | Golden tests và decode/migration theo schema |
| Timeout thay đổi dù API đổi thành công | Sai đơn vị/phạm vi connect vs request | Định nghĩa và test deadline chính xác |
| `jdeps` sạch nhưng runtime reflection lỗi | Dynamic config/reflective access | Review strings/flags/dependencies, runtime test |
| `jdeprscan` sạch nhưng internals vẫn có | Công cụ có mục tiêu khác | Kết hợp `jdeps --jdk-internals` |
| Java 11 runtime không có API | Compile dùng JDK mới không dùng `--release` | Build target + chạy thật Java 11 |
| Test fail chỉ vì provider/client class name | Assert implementation | Test behavior qua public API |
| JVM flag không còn hiệu lực | Unsupported/removed/changed flag | Xác minh docs vendor/JDK và staged rollout |

## 13. Checklist review kiến trúc và CI

**Hợp đồng**
- [ ] Bên sở hữu API/option là ai, phạm vi version nào?
- [ ] Có Javadoc/official docs hoặc support policy không?
- [ ] Đây là Java SE API, documented JDK API, SPI hay vendor-specific option?
- [ ] Đã nêu kiểu dữ liệu, precondition, exception và behavior rõ?
- [ ] Có tránh reflection vào private JDK fields và import internal packages không?

**Cấu hình**
- [ ] Tên khóa nói lên nhu cầu, không nhắc implementation class.
- [ ] Có đơn vị ms/bytes, enum/charset và default rõ.
- [ ] Parser validation với negative tests.
- [ ] Không log secret/proxy credentials hoặc raw config.
- [ ] Có kế hoạch schema migration/golden data tests.
- [ ] Vendor overrides có compatibility matrix.

**Kiểm chứng**
- [ ] `javac --release 11` pass.
- [ ] `jdeps --jdk-internals` chạy trên toàn artifact.
- [ ] `jdeprscan`/deprecation review được thực hiện.
- [ ] Dynamic reflection, dependency JARs, native/config paths đã được rà.
- [ ] Các tests chạy trên JDK 11 và runtime được support.
- [ ] Có kiểm chứng wire format, security provider và HTTP behavior.
- [ ] Mọi `--add-opens` tạm thời có owner/deadline.
- [ ] Rollback, monitoring và vận hành có hướng dẫn.

## 14. Bài tập có đáp án

**Câu 1.** Một class Java `public` có luôn là supported API?

**Đáp án:** Không. Cần kiểm tra module exports, tài liệu và support contract; internal class public không tự là API cho ứng dụng.

**Câu 2.** Vì sao không dùng `sun.misc.BASE64Encoder` trong code Java 11 mới?

**Đáp án:** Đó là dependency JDK internal/legacy; dùng `java.util.Base64` với format đúng.

**Câu 3.** Nên pin `MessageDigest` vào provider `SUN` không?

**Đáp án:** Không theo mặc định. Dùng `getInstance("SHA-256")` khi không có ràng buộc compliance, provider discovery thuộc Java Security API.

**Câu 4.** `ServiceLoader` có xóa hoàn toàn tên implementation không?

**Đáp án:** Không: provider registration chứa tên implementation theo SPI packaging contract. Business code không hardcode class nội bộ.

**Câu 5.** Nhiều providers, `findFirst()` có chọn đúng business strategy không?

**Đáp án:** Không bảo đảm. Cần contract selection rõ, tránh phụ thuộc thứ tự.

**Câu 6.** `--add-opens` sửa được tính ổn định của private JDK fields?

**Đáp án:** Không. Nó chỉ mở reflective access trong phạm vi flag; private layout vẫn có thể đổi.

**Câu 7.** `--illegal-access=permit` có còn là cách sửa trên JDK 17+?

**Đáp án:** Không, option này không còn hiệu lực mở internals.

**Câu 8.** `jdeps --jdk-internals` rỗng có chứng minh tuyệt đối không dùng internals?

**Đáp án:** Không. Reflection/config động và thư viện ngoài phạm vi phân tích có thể bị bỏ qua.

**Câu 9.** `jdeprscan` khác `jdeps` thế nào?

**Đáp án:** `jdeprscan` tìm Java SE deprecated APIs; `jdeps --jdk-internals` tìm static JDK internal dependencies.

**Câu 10.** Vì sao `--release 11` quan trọng?

**Đáp án:** Giới hạn source/target và Java SE API surface theo 11, tránh vô tình dùng API chỉ có ở JDK mới.

**Câu 11.** `http.timeout=1500` có thiếu gì?

**Đáp án:** Thiếu đơn vị và scope (connect/request/overall); cần schema rõ.

**Câu 12.** Có nên log toàn bộ config để debug lỗi provider?

**Đáp án:** Không; config có thể chứa secret, nên chỉ log key/status an toàn.

**Câu 13.** `Properties.load(InputStream)` và UTF-8 Reader giống hệt nhau?

**Đáp án:** Không. Phải hiểu encoding contract, dùng Reader được cấu hình charset khi cần UTF-8.

**Câu 14.** Vì sao test nên xét `client.connectTimeout()` thay vì `client.getClass().getName()`?

**Đáp án:** Timeout thuộc public contract; tên concrete class là implementation detail.

**Câu 15.** Có thể đổi basic Base64 sang URL-safe không padding mà không test migration?

**Đáp án:** Không. Wire format và dữ liệu cũ có thể khác.

**Câu 16.** SHA-256 của demo có phù hợp lưu password không?

**Đáp án:** Không. Đây là digest kiểm thử; password storage cần password hashing chuyên dụng và chính sách bảo mật.

**Câu 17.** Khi nào vendor-specific option hợp lệ?

**Đáp án:** Khi được document và kiểm thử theo JVM/version cụ thể; cô lập trong deployment profile.

**Câu 18.** Build pass trên JDK 24 có chứng minh chạy Java 11 không?

**Đáp án:** Không. Cần `--release 11` và test runtime Java 11 thật, cùng dependencies.

**Câu 19.** Thư viện buộc `--add-opens` thì nên làm gì?

**Đáp án:** Xác định owner/dependency, nâng hoặc thay thư viện, tạo kế hoạch loại flag; không coi là giải pháp vĩnh viễn.

**Câu 20.** Mục tiêu của bài “thay config implementation bằng contract” là gì?

**Đáp án:** Tách nhu cầu và behavior được công bố khỏi chi tiết runtime, làm cấu hình kiểm chứng được, quản lý tương thích rõ ràng và tránh hỏng sau thay JVM/provider.

## 15. Tổng kết và tài liệu chính thức

**Các nguyên tắc cần nhớ:**
- Không đồng nhất “đang chạy được” với “được hỗ trợ lâu dài”.
- Mô tả behavior trong app-owned config, có tên/đơn vị/validation/error policy.
- Dùng Java SE/public documented API và SPI, không phụ thuộc class/field nội bộ.
- Không tự động pin provider hoặc đoán implementation; nhưng vẫn tôn trọng yêu cầu vendor/security hợp lệ.
- `--add-opens`/`--add-exports` có thể là workaround tạm; không biến internal API thành public contract.
- `javac --release 11`, `jdeps` và `jdeprscan` chỉ là một phần của kiểm chứng; phải có runtime/behavioral tests.
- Ví dụ Java 11 thực tế đã qua compile/run và JDK internal dependency inspection.

**Nguồn chính thức còn áp dụng:**
- [Oracle Java SE 11 — jdeps](https://docs.oracle.com/en/java/javase/11/tools/jdeps.html).
- [Oracle Java SE 11 — jdeprscan](https://docs.oracle.com/en/java/javase/11/tools/jdeprscan.html).
- [Oracle Java SE 11 — javac](https://docs.oracle.com/en/java/javase/11/tools/javac.html).
- [Oracle Java SE 11 — ServiceLoader](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/ServiceLoader.html).
- [Oracle Java SE 11 — MessageDigest](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/security/MessageDigest.html).
- [Oracle Java SE 11 — Java Cryptographic Service Providers](https://docs.oracle.com/en/java/javase/11/security/oracle-providers.html).
- [Oracle Java SE 11 — Files](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Files.html).
- [Oracle Java SE 11 — StandardCharsets](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/charset/StandardCharsets.html).
- [Oracle Java SE 11 — Base64](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/Base64.html).
- [Oracle Java SE 11 — HttpClient](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html).
- [Oracle Java SE 11 — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html).
- [Oracle Java SE 11 — Properties](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/Properties.html).
- [Oracle Java SE 11 — Runtime.Version](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Runtime.Version.html).
- [Oracle Java SE 11 — Migration Guide](https://docs.oracle.com/en/java/javase/11/migrate/index.html).
- [Oracle JDK 17 — Strong Encapsulation and Migration](https://docs.oracle.com/en/java/javase/17/migrate/migrating-jdk-8-later-jdk-releases.html).
- [OpenJDK — JEP 403: Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403).
- [OpenJDK — JEP 261: Module System](https://openjdk.org/jeps/261).
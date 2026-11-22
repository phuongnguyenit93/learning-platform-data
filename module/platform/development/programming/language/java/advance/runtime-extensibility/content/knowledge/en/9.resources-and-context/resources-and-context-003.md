# Đọc cấu hình riêng của plugin mà không phụ thuộc thư mục làm việc

## 1. Vấn đề: cùng một plugin nhưng chạy từ thư mục khác lại đọc sai cấu hình

Trong một hệ thống Java có thể mở rộng bằng plugin, mỗi plugin thường cần cấu hình riêng: chế độ xử lý, endpoint, mức giới hạn, tên profile, bộ ánh xạ, tên file dữ liệu hoặc những tùy chọn tính năng. Một lỗi phổ biến là đọc cấu hình bằng đường dẫn tương đối như:

```java
// Phản ví dụ: phụ thuộc vào current working directory (CWD).
Path file = Path.of("config", "greeting.properties");
Properties properties = new Properties();
try (Reader reader = Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
    properties.load(reader);
}
```

Đây là **đoạn minh họa không độc lập** (cần import, xử lý ngoại lệ và nơi chứa cấu hình). `Path.of("config", ...)` tạo đường dẫn **tương đối**; `Files.newBufferedReader` giải quyết nó theo thư mục làm việc của tiến trình, thường được biểu diễn bởi `System.getProperty("user.dir")`. Khi khởi động ứng dụng bằng terminal ở thư mục khác, qua IDE, Windows Service, systemd, Docker, scheduler hoặc script triển khai, đường dẫn ấy có thể trỏ tới vị trí khác và gây thiếu cấu hình hoặc, nguy hiểm hơn, đọc nhầm file cùng tên.

Để đọc cấu hình **không phụ thuộc thư mục làm việc**, hãy xác định rõ **nguồn và gốc đường dẫn**. Hai mô hình phổ biến:

1. **Cấu hình mặc định được đóng gói trong JAR của plugin**: đọc qua API resource của class/module bằng `getResourceAsStream`, không qua file path tương đối.
2. **Cấu hình bên ngoài có thể thay đổi sau triển khai**: host cung cấp **đường dẫn tuyệt đối tới thư mục cấu hình của từng plugin**, plugin dùng `Path.resolve` để lấy file con.

Hai cách có thể kết hợp thành một chính sách: **đọc defaults trong JAR → áp dụng overrides bên ngoài → validate → kích hoạt**. Mô hình này giúp plugin chạy giống nhau dù điểm khởi động của tiến trình thay đổi.

> Phân biệt: “không phụ thuộc CWD” không đồng nghĩa “không phụ thuộc bất kỳ đường dẫn nào”. Cấu hình bên ngoài vẫn phải có gốc xác định (CLI, biến môi trường được quản trị, config root, volume mount…), và host nên truyền gốc đã kiểm tra bằng đường dẫn tuyệt đối.

## 2. Ba loại vị trí dễ bị nhầm lẫn

| Khái niệm | Ví dụ | Ý nghĩa và rủi ro |
| --- | --- | --- |
| **Current working directory** | `user.dir`, `Path.of(".")`, `new File("settings.yml")` | Vị trí mà tiến trình được khởi động; thay đổi theo cách chạy, không nhất thiết là nơi chứa JAR |
| **Classpath/module resource** | `/plugins/greeting/default.properties` | Tài nguyên được đóng gói hoặc cung cấp qua cơ chế class/module loading; có thể nằm **bên trong JAR** |
| **External configuration directory** | `/etc/myapp/plugins/greeting` hoặc `C:\apps\myapp\config\greeting` | Vị trí cấu hình do người triển khai/host quyết định; đọc bằng NIO `Path` sau khi đã có gốc tuyệt đối |

Một số vị trí khác cũng cần phân biệt:

- **Thư mục chứa JAR**: vị trí vật lý của artifact triển khai, không tự động là CWD, và không mặc nhiên là nơi nên chứa cấu hình ghi được.
- **`user.home`**: thư mục người dùng chạy tiến trình; không thích hợp làm quy ước ngầm cho nhiều dịch vụ hoặc nhiều tài khoản.
- **`java.class.path`**: tập mục classpath, không phải thư mục cấu hình; có thể chứa nhiều JAR/thư mục hoặc bị thay đổi bởi launcher.
- **Temporary directory**: `java.io.tmpdir` dành cho file tạm, không phải nguồn cấu hình bền vững.

Ví dụ, nếu host chạy từ `C:\work` nhưng JAR đặt tại `C:\apps\host\lib\plugin.jar`, thì `Path.of("config/plugin.properties")` **không** tự tìm tới `C:\apps\host\lib\config`. Nó phụ thuộc vào điểm chạy, trừ khi đã được giải quyết thành absolute path từ một gốc khác.

## 3. Cấu hình đóng gói trong plugin JAR: dùng resource API

### 3.1. Định vị resource theo class sở hữu plugin

Giả sử provider ở `com.example.plugins.greeting.GreetingPlugin` và JAR có cấu trúc:

```text
greeting-plugin.jar
├── com/example/plugins/greeting/GreetingPlugin.class
├── META-INF/services/com.example.api.Plugin
└── plugins/greeting/default.properties
```

Plugin đọc cấu hình mặc định bằng:

```java
String resourceName = "/plugins/greeting/default.properties";
try (InputStream input =
         GreetingPlugin.class.getResourceAsStream(resourceName)) {
    if (input == null) {
        throw new IllegalStateException(
            "Thiếu resource trong JAR: " + resourceName);
    }
    // Đọc input ở đây.
}
```

Đây là đoạn minh họa. `Class.getResourceAsStream("/...")` tìm resource từ **gốc của resource namespace**, theo cơ chế class/module loader gắn với class. Nó hoạt động khi plugin được đóng trong JAR mà không cần biết file JAR đang ở thư mục nào hoặc tiến trình được khởi động từ đâu.

**Lưu ý các dạng tên resource:**

| API | Tên truyền vào | Cách diễn giải |
| --- | --- | --- |
| `GreetingPlugin.class.getResourceAsStream("/plugins/greeting/default.properties")` | Có `/` đầu | Bắt đầu ở gốc resource namespace |
| `GreetingPlugin.class.getResourceAsStream("default.properties")` | Không `/` đầu | Tương đối với package của `GreetingPlugin` |
| `GreetingPlugin.class.getClassLoader().getResourceAsStream("plugins/greeting/default.properties")` | Không `/` đầu | Bắt đầu ở gốc class-loader resource namespace |

Với `ClassLoader.getResourceAsStream`, **không đặt `/` đầu**; giá trị `"/plugins/..."` thường không khớp tên resource chuẩn. Với `Class.getResourceAsStream`, sử dụng dấu `/` đầu nếu muốn ổn định khi sau này đổi package của implementation.

Nên đặt resource trong **namespace riêng theo plugin ID**, chẳng hạn `plugins/greeting/default.properties`, để tránh đụng tên `config.properties` giữa các JAR. Việc class loader có thể nhìn thấy resource từ nhiều JAR, và parent delegation có thể ảnh hưởng kết quả, nên resource name phải đủ đặc thù; với host/plugin loader phức tạp, cần xác định chính sách phân giải resource.

### 3.2. Không chuyển tài nguyên trong JAR thành `Path` một cách máy móc

Một lỗi phổ biến:

```java
// Phản ví dụ: chỉ có thể chạy trong một số cách đóng gói.
URL url = GreetingPlugin.class.getResource(
    "/plugins/greeting/default.properties");
Path file = Path.of(url.toURI());
```

Nếu resource ở một thư mục trên filesystem, URL có thể mang scheme `file:` và chuyển sang `Path` được. Khi resource nằm **trong JAR**, URL có thể là `jar:file:...!/plugins/greeting/default.properties`. Chuyển trực tiếp qua `Path.of(URI)` có thể ném `FileSystemNotFoundException` hoặc không hoạt động nếu chưa có filesystem provider phù hợp.

Đối với việc **đọc nội dung**, `getResourceAsStream` phù hợp và gọn hơn nhiều. Nếu thật sự cần một file vật lý vì thư viện downstream chỉ nhận `Path`, hãy cân nhắc API nhận `InputStream` trước; nếu bắt buộc, copy resource vào vị trí tạm do host quản lý và dọn sau khi sử dụng. Không giả định JAR đã giải nén hoặc resource có thể ghi.

### 3.3. Class loader nào đang tìm resource?

Trong ứng dụng SPI, host có thể dùng:

```java
ServiceLoader<Plugin> services =
    ServiceLoader.load(Plugin.class, pluginClassLoader);
```

`pluginClassLoader` là loader được host chọn cho plugin (đoạn này là minh họa). Nếu plugin đọc `GreetingPlugin.class.getResourceAsStream(...)`, nó dùng **ngữ cảnh định nghĩa của class triển khai**; điều này rõ ràng hơn việc lấy bừa context class loader của thread.

Tránh phụ thuộc vô điều kiện vào:

```java
Thread.currentThread()
    .getContextClassLoader()
    .getResourceAsStream("plugins/greeting/default.properties");
```

TCCL có thể thay đổi theo host, framework, thread pool hoặc executor, và có thể không nhìn thấy JAR của plugin. Nếu cần đổi TCCL theo yêu cầu framework, host phải khôi phục loader cũ trong `finally` sau khi thực hiện thao tác.

Với **named modules (JPMS)**, resource visibility có thể chịu quy tắc module encapsulation; nếu đang ở bên trong chính module sở hữu tài nguyên, có thể dùng `Class.getResourceAsStream` hoặc `Module.getResourceAsStream` phù hợp. Không dựa vào giả định rằng class loader bất kỳ có quyền đọc tất cả resource của module.

### 3.4. Cấu hình trong JAR nên đóng vai trò gì?

Nó phù hợp với **defaults ổn định**, schema, template nhỏ, file ánh xạ mặc định hoặc dữ liệu phiên bản đi cùng code. Nó không phù hợp với mật khẩu thực, khóa bí mật, cấu hình riêng từng môi trường hoặc file cần chỉnh sửa ngay trên máy triển khai.

File trong JAR được xem như tài nguyên *read-only* của phiên bản plugin. Nếu muốn cập nhật cấu hình thường xuyên mà không build lại artifact, hãy bổ sung lớp cấu hình bên ngoài.

## 4. Cấu hình bên ngoài: host cấp đường dẫn tuyệt đối theo plugin ID

### 4.1. Tạo gốc cấu hình có chủ sở hữu rõ ràng

Thay vì để plugin tự suy đoán CWD, host quyết định một `configRoot` từ CLI/launcher hoặc hệ thống cấu hình đã được quản trị:

```java
Path root = Path.of(configRootFromLauncher);
if (!root.isAbsolute()) {
    throw new IllegalArgumentException(
        "Config root phải là đường dẫn tuyệt đối");
}
root = root.normalize();
```

Đây là đoạn minh họa; `configRootFromLauncher` phải đến từ cấu hình host đã xác thực. **Chỉ gọi `toAbsolutePath()` trên chuỗi tương đối vẫn khiến kết quả phụ thuộc CWD**. Cách chắc chắn khi yêu cầu độc lập CWD là **đòi hỏi path đầu vào đã tuyệt đối**, hoặc thiết lập một quy ước gốc ổn định khác từ lúc triển khai.

Ví dụ cấu trúc:

```text
config-root/
├── greeting/
│   └── greeting.properties
├── exporter/
│   └── exporter.properties
└── reporting/
    └── reporting.properties
```

Host chọn `greeting` dựa trên một plugin ID đã được kiểm tra, sau đó truyền `configRoot.resolve("greeting")` vào plugin. Plugin chỉ biết **thư mục cấu hình riêng của nó**, không cần quan tâm host đang chạy từ thư mục nào hoặc cấu hình của plugin khác đặt ở đâu.

Một contract có thể định nghĩa:

```java
public interface Plugin {
    String id();
    void start(Path pluginConfigDir) throws IOException;
    void stop();
}
```

Đây là ví dụ API rút gọn; các phương thức nghiệp vụ có thể bổ sung tùy chức năng. Trong ứng dụng lớn, thay `Path` bằng `PluginContext` hoặc `ConfigSource` chỉ cấp những khả năng truy cập cần thiết và dễ kiểm thử hơn.

### 4.2. Xác thực định danh và đường dẫn

Nếu `id()` do plugin cung cấp, không nên dùng trực tiếp để ghép đường dẫn khi chưa kiểm tra:

```java
String id = plugin.id();
if (!id.matches("[a-z][a-z0-9-]*")) {
    throw new IllegalArgumentException("Plugin ID không hợp lệ: " + id);
}
Path pluginDir = root.resolve(id).normalize();
if (!pluginDir.startsWith(root)) {
    throw new SecurityException("Plugin config path vượt ngoài config root");
}
```

Nhờ giới hạn ID về ký tự đơn giản, plugin không thể cung cấp giá trị như `../../other-plugin` làm tên thư mục. `normalize()` và `startsWith(root)` kiểm tra **đường dẫn từ vựng**; **không đủ để chống symbolic link/junction** trỏ ra ngoài. Nếu plugin hoặc nguồn cấu hình là không tin cậy, host cần thêm chính sách kiểm soát quyền filesystem, symlink, sở hữu thư mục và kiểm tra đường dẫn thực khi phù hợp. Không dùng class loader làm ranh giới bảo mật.

Nếu cấu hình chỉ để đọc, nên cấp quyền filesystem **read-only** cho tiến trình/plugin theo mức có thể triển khai. Không log nguyên văn secret hoặc đường dẫn nhạy cảm trong lỗi.

### 4.3. Tải file cấu hình bằng NIO và UTF-8

Khi đã có `pluginConfigDir` là absolute path, plugin đọc:

```java
Path file = pluginConfigDir.resolve("greeting.properties");
Properties properties = new Properties();
try (Reader reader =
         Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
    properties.load(reader);
}
```

Đoạn minh họa cần import `java.nio.file.*`, `java.io.*`, `java.nio.charset.StandardCharsets` và `java.util.Properties`; nơi gọi phải xử lý `IOException`.

Vì `pluginConfigDir` đã là absolute path nên `resolve("greeting.properties")` cũng cho một path không phụ thuộc CWD. `Files.newBufferedReader` mở file ngoài theo đường dẫn thật, khác với `getResourceAsStream` tìm tài nguyên trong classpath/JAR.

**Encoding rất quan trọng:** `Properties.load(InputStream)` quy định byte theo ISO-8859-1 với escape cho Unicode; nếu file chứa tiếng Việt UTF-8, hãy dùng `Properties.load(Reader)` với `InputStreamReader(..., StandardCharsets.UTF_8)` hoặc `Files.newBufferedReader(..., UTF_8)`. Trên Windows PowerShell 5.1, một số cách lưu UTF-8 có thể thêm BOM; nên ghi file UTF-8 **không BOM** vì BOM đầu file có thể trở thành một phần của tên key khi `Properties.load(Reader)` xử lý.

### 4.4. File không tồn tại: mặc định hay báo lỗi?

Khi external config là **tùy chọn** (chỉ override defaults trong JAR), chỉ nên bỏ qua lỗi **file không tồn tại**, còn lỗi không đọc được thì phải nổi lên:

```java
try (Reader reader = Files.newBufferedReader(
        overrideFile, StandardCharsets.UTF_8)) {
    properties.load(reader);
} catch (NoSuchFileException missing) {
    // Cho phép thiếu file override; dùng defaults đã đọc từ JAR.
}
```

Đây là đoạn minh họa trong một phương thức có `throws IOException`. `AccessDeniedException`, lỗi I/O, lỗi nội dung hoặc đường dẫn là directory không nên bị chuyển thành “không có override”. Đừng dùng `catch (Exception)` rồi mặc định bỏ qua; cách đó che lỗi cấu hình và gây khác biệt khó truy vết giữa môi trường.

Nếu external config là **bắt buộc**, hãy để `IOException` có nguyên nhân rõ ràng và không kích hoạt plugin. Với cấu hình tùy chọn, điều kiện fallback phải được ghi trong contract và log ở mức phù hợp.

## 5. Thứ tự ưu tiên cấu hình và vòng đời

Một mô hình dễ dự đoán:

```text
[plugin JAR]
    /plugins/greeting/default.properties
                    │
                    ▼
           Properties defaults
                    │
                    ▼
[external pluginConfigDir]/greeting.properties  (nếu có)
                    │
                    ▼
             Áp dụng override
                    │
                    ▼
           Validate key & value
                    │
                    ▼
            STARTED / ACTIVE
```

Nếu cả hai nguồn cùng có key `prefix`, file ngoài thắng theo quy ước của host/plugin. Nếu file ngoài không tồn tại và là tùy chọn, giữ default. Nếu key quan trọng còn thiếu hoặc không hợp lệ, **thất bại ở lúc khởi động** với thông báo rõ thay vì đợi đến request đầu tiên mới lỗi.

Những quy tắc nên định nghĩa cụ thể:

- **Precedence:** defaults JAR → external file → (nếu có) overrides từ môi trường/CLI/secret store; quy tắc này phải được công bố nhất quán.
- **Validation:** kiểu dữ liệu, dải giá trị, schema/version, key bắt buộc, key không biết, đường dẫn con và endpoint hợp lệ. Không suy đoán default cho tùy chọn bắt buộc.
- **Lifecycle:** đọc cấu hình tại `start()`; tạo cấu hình bất biến sau validate; chỉ nhận request khi readiness thành công.
- **Reload:** nếu cần đọc lại file, manager phải thiết kế reload/swap có đồng bộ, tránh thay `Properties` đang được request khác sử dụng. Với đa số plugin nhỏ, khởi động lại plugin là đơn giản và an toàn hơn.
- **Ownership:** plugin chịu trách nhiệm đóng stream/watcher do mình mở; host sở hữu config root, chính sách quyền và mapping plugin ID → thư mục.
- **Isolation:** mỗi plugin chỉ biết namespace và đường dẫn riêng; không vô tình đọc hoặc ghi config của plugin khác.

Lưu ý **tài nguyên trong JAR và file ngoài có mục đích khác nhau**: resource đi theo *phiên bản code*, còn external config đi theo *môi trường và instance*. Không cố tìm một thư mục ghi được thông qua `getResource(...)` rồi chỉnh file nằm trong JAR.

## 6. Ví dụ Java 17+ hoàn chỉnh: defaults trong JAR và file override riêng

Ví dụ này sử dụng Java SPI để phát hiện một plugin `greeting`. **Host nhận đường dẫn tuyệt đối** tới config root và truyền thư mục con của plugin vào `start`. Plugin đọc `default.properties` đóng gói trong chính JAR của nó, rồi dùng `greeting.properties` bên ngoài làm override nếu file tồn tại. Chạy Java từ thư mục bất kỳ vẫn cho cùng kết quả khi giữ nguyên classpath và config root tuyệt đối.

Không cần Maven/Gradle; các lệnh dưới đây dành cho Windows PowerShell và JDK 17+.

### 6.1. Cấu trúc thư mục ví dụ

```text
demo/
├── src/
│   └── app/
│       ├── api/
│       │   └── Plugin.java
│       ├── host/
│       │   └── Main.java
│       └── plugin/
│           └── GreetingPlugin.java
├── resources/
│   ├── META-INF/
│   │   └── services/
│   │       └── app.api.Plugin
│   └── plugins/
│       └── greeting/
│           └── default.properties
└── build/                       # Tạo khi biên dịch
```

### 6.2. Hợp đồng do host cung cấp

**`src/app/api/Plugin.java`**

```java
package app.api;

import java.io.IOException;
import java.nio.file.Path;

public interface Plugin {
    String id();
    void start(Path pluginConfigDir) throws IOException;
    String greet(String person);
    void stop();
}
```

API truyền `Path` được host quyết định; provider không dùng `Path.of("config/...")` hay `user.dir` để tìm external config. Interface `start` được phép ném `IOException` để báo lỗi đọc cấu hình trước khi plugin nhận request.

### 6.3. Cài đặt plugin: hai tầng cấu hình

**`src/app/plugin/GreetingPlugin.java`**

```java
package app.plugin;

import app.api.Plugin;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.util.Properties;

public final class GreetingPlugin implements Plugin {
    private static final String DEFAULT_RESOURCE =
        "/plugins/greeting/default.properties";

    private String prefix;

    @Override
    public String id() {
        return "greeting";
    }

    @Override
    public void start(Path pluginConfigDir) throws IOException {
        if (prefix != null) {
            throw new IllegalStateException("Plugin already started");
        }
        if (!pluginConfigDir.isAbsolute()) {
            throw new IllegalArgumentException(
                "pluginConfigDir must be absolute");
        }

        Properties settings = new Properties();

        // 1. Resource bundled inside this plugin's JAR.
        InputStream bundled =
            GreetingPlugin.class.getResourceAsStream(DEFAULT_RESOURCE);
        if (bundled == null) {
            throw new IOException(
                "Missing bundled config: " + DEFAULT_RESOURCE);
        }
        try (Reader reader = new InputStreamReader(
                bundled, StandardCharsets.UTF_8)) {
            settings.load(reader);
        }

        // 2. Optional external override under a host-supplied folder.
        Path external = pluginConfigDir.resolve("greeting.properties");
        try (Reader reader = Files.newBufferedReader(
                external, StandardCharsets.UTF_8)) {
            settings.load(reader); // Keys in override replace defaults.
        } catch (NoSuchFileException missing) {
            // Optional: no override, so keep bundled defaults.
        }

        // 3. Validate before publishing the active state.
        String configured = settings.getProperty("prefix");
        if (configured == null || configured.isBlank()) {
            throw new IllegalStateException(
                "Missing/blank config key: prefix");
        }

        this.prefix = configured;
    }

    @Override
    public String greet(String person) {
        if (prefix == null) {
            throw new IllegalStateException("Plugin not started");
        }
        return prefix + ", " + person + "!";
    }

    @Override
    public void stop() {
        prefix = null; // Cleanup đơn giản cho demo.
    }
}
```

Giải thích:

- `GreetingPlugin.class.getResourceAsStream(...)` đọc mặc định từ resource JAR; **không phụ thuộc CWD**.
- `pluginConfigDir.resolve("greeting.properties")` đọc external config tại thư mục đã được host cấp; **không phụ thuộc CWD** vì dir được yêu cầu tuyệt đối.
- `Properties.load(Reader)` dùng UTF-8, nên `prefix` có thể chứa tiếng Việt trực tiếp.
- Chỉ bắt `NoSuchFileException`: thiếu override là hợp lệ; lỗi quyền truy cập hoặc I/O vẫn làm `start` thất bại.
- `prefix` chỉ được gán sau khi đọc/validate xong. `greet` từ chối chạy trước `start`. `stop` an toàn khi gọi lại.
- Mã này dùng một instance tuần tự; nếu phục vụ nhiều thread hoặc hot reload, cần đồng bộ và snapshot immutable cho config, không dùng trường `prefix` không bảo vệ như một giải pháp concurrency production.

### 6.4. Host chọn plugin và truyền config directory

**`src/app/host/Main.java`**

```java
package app.host;

import app.api.Plugin;
import java.nio.file.Path;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "Usage: Main <absolute-config-root>");
        }

        Path root = Path.of(args[0]);
        if (!root.isAbsolute()) {
            throw new IllegalArgumentException(
                "Config root must be absolute: " + root);
        }
        root = root.normalize();

        Plugin plugin = ServiceLoader.load(Plugin.class)
            .findFirst()
            .orElseThrow(() -> new IllegalStateException(
                "No Plugin provider found"));

        String pluginId = plugin.id();
        if (!pluginId.matches("[a-z][a-z0-9-]*")) {
            throw new IllegalArgumentException(
                "Invalid plugin ID: " + pluginId);
        }

        Path pluginDir = root.resolve(pluginId).normalize();
        if (!pluginDir.startsWith(root)) {
            throw new SecurityException(
                "Plugin config directory escapes root");
        }

        // Plugin lifecycle belongs to host, not ServiceLoader.
        try {
            plugin.start(pluginDir);
            System.out.println(plugin.greet("Java"));
        } finally {
            plugin.stop();
        }
    }
}
```

Ở đây có đúng **một** provider trong demo, nên `findFirst()` cho lựa chọn dễ hiểu. Trong hệ thống có nhiều provider, host cần chọn theo ID/capability/version một cách tường minh, không phụ thuộc vào thứ tự `ServiceLoader`.

Host yêu cầu **đường dẫn config root tuyệt đối**. Nó không tự dùng `Path.of(".")`, `user.dir` hoặc `toAbsolutePath()` trên một đường dẫn tương đối để đoán thư mục gốc. Khi cần triển khai dưới service manager, launcher/container cung cấp tham số absolute path phù hợp với môi trường.

Lưu ý `startsWith(root)` là kiểm tra từ vựng; đường dẫn qua symlink/junction và quyền filesystem cần chính sách bảo vệ bổ sung khi plugin hoặc config root không đáng tin cậy.

### 6.5. Resource đi cùng JAR

**`resources/META-INF/services/app.api.Plugin`**

```text
app.plugin.GreetingPlugin
```

Đây là service descriptor giúp `ServiceLoader` khám phá provider. Nội dung có đúng tên đầy đủ của class triển khai.

**`resources/plugins/greeting/default.properties`**

```properties
prefix=Xin chào
```

Lưu file dưới dạng UTF-8 **không BOM**. Vì code dùng `Properties.load(Reader)`, giá trị tiếng Việt được đọc đúng. Hai tệp này sẽ được đóng cùng class implementation vào **JAR của plugin**, không nằm trong build output của host.

### 6.6. Biên dịch và đóng gói trên PowerShell

Tại thư mục `demo`, có JDK 17+ trong `PATH`:

```powershell
New-Item -ItemType Directory -Force build/host, build/provider | Out-Null

# Host chỉ chứa API và Main.
javac -encoding UTF-8 -d build/host src/app/api/Plugin.java src/app/host/Main.java

# Plugin được compile riêng nhưng tham chiếu API của host.
javac -encoding UTF-8 -cp build/host -d build/provider src/app/plugin/GreetingPlugin.java

# Đóng implementation, META-INF/services và resource defaults vào một JAR.
jar --create --file build/greeting-plugin.jar -C build/provider . -C resources .

# Tạo các đường dẫn tuyệt đối trước khi chạy.
$projectRoot = (Get-Location).Path
$hostClasses = Join-Path $projectRoot "build/host"
$providerJar = Join-Path $projectRoot "build/greeting-plugin.jar"
$configRoot = Join-Path $projectRoot "config"

# Chưa tạo external override. Plugin dùng defaults trong JAR.
java -cp "$hostClasses;$providerJar" app.host.Main "$configRoot"
```

**Stdout chính xác của lệnh chạy cuối:**

```text
Xin chào, Java!
```

Không có thư mục `config/greeting` vẫn hợp lệ: override là tùy chọn. Cấu hình mặc định đã được tìm thấy qua resource trong JAR.

Có thể kiểm tra resource đã được đóng vào JAR bằng:

```powershell
jar --list --file build/greeting-plugin.jar
```

Trong danh sách phải có ít nhất:

```text
app/plugin/GreetingPlugin.class
META-INF/services/app.api.Plugin
plugins/greeting/default.properties
```

Đây là **những đường dẫn cần có trong danh sách**, không phải toàn bộ stdout của `jar --list`, vì JAR có thể có thêm manifest/thư mục và thứ tự liệt kê.

### 6.7. Thêm cấu hình bên ngoài cho đúng plugin

Tạo file `config/greeting/greeting.properties`. Dùng .NET API để ghi UTF-8 **không BOM** một cách nhất quán cả trên Windows PowerShell 5.1:

```powershell
$pluginConfigDir = Join-Path $configRoot "greeting"
New-Item -ItemType Directory -Force $pluginConfigDir | Out-Null

$overrideFile = Join-Path $pluginConfigDir "greeting.properties"
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText(
    $overrideFile, "prefix=Chào từ cấu hình ngoài", $utf8NoBom)

java -cp "$hostClasses;$providerJar" app.host.Main "$configRoot"
```

**Stdout chính xác:**

```text
Chào từ cấu hình ngoài, Java!
```

Vì `settings.load(reader)` lần thứ hai ghi đè key `prefix`, external config thay thế giá trị mặc định trong JAR.

### 6.8. Đổi CWD rồi chạy lại

Giữ nguyên **absolute paths** của host classes, provider JAR và config root đã tạo ở trên, sau đó chuyển sang `build` trước khi gọi Java:

```powershell
Push-Location (Join-Path $projectRoot "build")
try {
    java -cp "$hostClasses;$providerJar" app.host.Main "$configRoot"
} finally {
    Pop-Location
}
```

**Stdout vẫn là:**

```text
Chào từ cấu hình ngoài, Java!
```

Tại lần chạy này CWD đã thay đổi, nhưng host vẫn dùng `$configRoot` là **đường dẫn tuyệt đối**, còn plugin tìm default resource theo JAR và external override theo thư mục do host truyền. Nếu dùng `Path.of("config/greeting/greeting.properties")` trong plugin, đường dẫn sẽ tương đối với `build` và có thể không còn tìm thấy file.

Để kiểm tra tình huống không có override sau đó, xóa riêng file `config/greeting/greeting.properties` hoặc đổi sang một config root absolute khác không có override: chương trình lại in `Xin chào, Java!`. Không cần thay JAR.

### 6.9. Những gì ví dụ có và chưa có

Ví dụ chứng minh **ba nguyên tắc chính**: resource API cho cấu hình đóng gói, external path tuyệt đối do host cấp, và precedence defaults → override. Đây là ví dụ SPI ở classpath, có một instance và không có sự cạnh tranh đồng thời.

Khi đưa vào hệ thống plugin động hoàn chỉnh, cần thêm class loader riêng/module layer khi phù hợp, policy lựa chọn provider, giới hạn quyền đọc config, version/schema, dependency resolution, lifecycle state machine, giám sát lỗi và cơ chế reload an toàn. Nếu cần config riêng theo tenant hoặc theo instance plugin, host có thể cấp một namespace cho từng instance thay vì chỉ plugin ID.

## 7. Cấu hình, secrets và namespace trong ứng dụng thật

### 7.1. Cấu hình theo môi trường

Một chính sách nguồn có thể là:

```text
default config in plugin.jar
          │
          ▼
external config directory per plugin
          │
          ▼
explicit overrides via host/environment (if supported)
          │
          ▼
secret provider / injected credentials (if needed)
          │
          ▼
validated immutable Config snapshot
```

Cần phân biệt **giá trị mặc định**, **cấu hình triển khai**, **secret** và **trạng thái đang chạy**:

- Defaults trong JAR dễ kiểm soát cùng version code, phù hợp với thay đổi ít.
- External config được quản trị riêng theo môi trường, có thể trên volume mount hoặc vị trí tập trung đã được cấp quyền.
- Secret nên lấy qua secret manager hoặc cơ chế cấp credential an toàn; không nhúng password/token vào JAR hoặc log.
- Sau khi validate, plugin nên giữ **snapshot cấu hình có kiểu dữ liệu rõ ràng** thay vì liên tục đọc file theo mỗi request.

### 7.2. Xử lý path được nêu trong file cấu hình

Cấu hình có thể chứa một đường dẫn thứ cấp, ví dụ `cachePath=data/cache`. Phải công bố **nó tương đối với gốc nào**. Nếu muốn tương đối với thư mục plugin, làm rõ:

```java
Path cache = pluginConfigDir.resolve(
    properties.getProperty("cachePath", "data/cache")).normalize();
```

Đây là đoạn minh họa. Nếu cho phép key tùy ý từ người dùng, cần kiểm tra `cache.startsWith(pluginConfigDir)`, quyền truy cập, symlink/junction và ranh giới thực của filesystem khi có yêu cầu bảo mật. Một path **tuyệt đối** trong file config có thể làm `resolve` trả path ngoài gốc; đừng bỏ qua kiểm tra.

**Không** giải quyết path thứ cấp một cách ngầm định so với CWD. Nếu muốn path nằm ngoài thư mục cấu hình, phải có quy tắc, allowlist hoặc quyền riêng do host cấp.

### 7.3. Test được mà không cần thay CWD

Thiết kế tốt cho phép test provider qua thư mục cấu hình độc lập:

```java
Path isolatedConfig = tempDirectory.resolve("greeting");
plugin.start(isolatedConfig);
```

Đây là đoạn minh họa trong test có `tempDirectory` được tạo bởi `@TempDir` hoặc `Files.createTempDirectory`; code test phải tạo file override trước nếu muốn kiểm tra precedence. Cũng cần kiểm tra:

- Có defaults, không có override → dùng giá trị trong JAR.
- Có override hợp lệ → ghi đè đúng key.
- Override có UTF-8 → ký tự tiếng Việt đúng.
- File override sai cú pháp/key hoặc không đọc được → báo lỗi có ý nghĩa.
- Chạy từ CWD khác nhau với cùng absolute config root → kết quả giống nhau.
- Hai plugin với config dir khác nhau → không đọc nhầm namespace.
- Đường dẫn chứa `..`, absolute override hoặc symlink → tuân thủ chính sách truy cập.
- Đọc tài nguyên khi plugin được đóng **trong JAR**, không chỉ khi IDE chạy class từ thư mục.

## 8. Lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| IDE chạy được, service không thấy file | Code dùng `Path.of("config/...")` dựa CWD | Truyền absolute config root từ launcher/host |
| Resource có trong source tree nhưng `getResourceAsStream` trả `null` | Chưa copy resource vào JAR/classpath, sai đường dẫn hoặc chữ hoa/thường | Kiểm tra nội dung JAR và tên resource |
| `Class.getResourceAsStream("...")` không thấy nhưng có `/` thì thấy | Không có `/` là đường dẫn tương đối package | Dùng đường dẫn gốc `"/plugins/id/..."` |
| `ClassLoader.getResourceAsStream("/...")` trả `null` | API ClassLoader dùng tên resource không có slash đầu | Bỏ `/` với `ClassLoader` |
| Chạy trong JAR gây lỗi khi ép URL thành `Path` | Resource có URI `jar:`, không phải file thông thường | Đọc bằng `InputStream` |
| Đã đổi CWD nhưng kết quả đổi theo | Một tầng của config/path phụ vẫn dùng đường dẫn tương đối | Audit toàn bộ path, bao gồm file include, cache, log, template |
| File tiếng Việt bị lỗi dấu hoặc không tìm thấy key | Dùng `Properties.load(InputStream)` cho UTF-8, hoặc file có BOM | Dùng UTF-8 Reader và lưu không BOM |
| Plugin A đọc cấu hình plugin B | Dùng tên resource chung/đường dẫn chung, hoặc TCCL sai | Namespace theo plugin ID, host cấp dir riêng |
| File override thiếu và plugin không khởi động | Contract xem file ngoài là bắt buộc | Quyết định rõ required/optional; nếu optional chỉ bắt `NoSuchFileException` |
| File sai quyền nhưng plugin vẫn im lặng dùng defaults | Bắt quá rộng mọi exception rồi fallback | Không nuốt `AccessDeniedException`/`IOException` |
| Thay file xong plugin vẫn dùng cấu hình cũ | Config chỉ nạp lúc `start`, không có reload | Restart hoặc thiết kế reload và snapshot có đồng bộ |
| Sau hot reload vẫn thấy resource cũ | Class loader hoặc provider instance cũ còn được giữ | Tạo loader mới, chuyển instance, dừng cũ, dọn reference |

Khi gặp `null` từ `getResourceAsStream`, kiểm tra **nội dung artifact thực tế** trước; chạy từ IDE với `src/main/resources` có thể khiến mọi thứ “tình cờ đúng” nhưng JAR phát hành lại thiếu resource. Khi external config không hoạt động, hãy kiểm tra **absolute path đã được host truyền**, quyền đọc và trạng thái filesystem thay vì chỉ in `System.getProperty("user.dir")`.

## 9. Checklist trước khi phát hành plugin

- [ ] Default resource nằm trong artifact plugin đúng vị trí, có namespace riêng và đọc bằng `Class.getResourceAsStream`/module API phù hợp.
- [ ] Không dùng `new File("config/...")` hoặc `Path.of("config/...")` làm cơ chế chính để tìm cấu hình plugin.
- [ ] Host cấp absolute config root theo môi trường; plugin nhận thư mục riêng theo ID đã được xác thực.
- [ ] Đã xác định precedence giữa defaults, external overrides, environment và secrets.
- [ ] Dùng UTF-8 Reader cho file properties có Unicode; quản lý BOM và escape đúng chuẩn.
- [ ] Thiếu resource bắt buộc thì báo lỗi; external optional chỉ được fallback khi **thật sự không có file**.
- [ ] Validate key/type/range trước khi plugin ACTIVE; tránh in giá trị secret vào log.
- [ ] Kiểm tra đường dẫn con, quyền filesystem, symlink và ranh giới namespace khi nguồn đầu vào không hoàn toàn tin cậy.
- [ ] Đóng mọi reader/stream bằng `try-with-resources`; có chính sách rõ cho reload và thread safety.
- [ ] Test JAR đóng gói thật, chạy từ ít nhất hai CWD khác nhau với cùng absolute config root, kết quả nhất quán.

**Tài liệu Java để tra cứu:** [`Class.getResourceAsStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getResourceAsStream(java.lang.String)), [`ClassLoader.getResourceAsStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html#getResourceAsStream(java.lang.String)), [`Files.newBufferedReader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#newBufferedReader(java.nio.file.Path,java.nio.charset.Charset)), [`Properties.load(Reader)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Properties.html#load(java.io.Reader)), [`ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html).

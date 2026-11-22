# Kiểm chứng tìm tài nguyên và provider dịch vụ trong Java ClassLoader

Một hệ thống plugin có thể **nạp được class** nhưng vẫn **không đọc được resource** hoặc **không tìm thấy service provider**. Ngược lại, một `getResource(...)` có thể trả URL hợp lệ nhưng lấy **bản resource của parent**, không phải bản cùng tên ở plugin child. Do đó, khi kiểm thử classloader, không thể chỉ assert “`loadClass` thành công” rồi kết luận phần resources và SPI cũng đúng.

Bài này xây dựng một quy trình **kiểm chứng hành vi** cho ba thành phần:

1. **Tìm resource:** `ClassLoader.getResource`, `getResources`, `getResourceAsStream`, `URLClassLoader.findResource`, `Class.getResource`.
2. **Phát hiện service provider:** SPI, `META-INF/services/<binary-service-name>`, `ServiceLoader`, lazy discovery và provider constructor.
3. **Đúng classloader boundary:** parent delegation, defining loader của provider, shared SPI type, TCCL và named modules khi áp dụng.

Kết quả phải được kiểm bằng **tên/path thực sự được yêu cầu, loader được dùng, URL nguồn trả về, số provider và runtime type identity**. Không dựa vào việc một thư mục/JAR “có file đó trên đĩa” như bằng chứng đủ.

## 1. Mục tiêu của kiểm thử resource và service provider

Giả sử ứng dụng:

~~~text
ApplicationLoader
  |
  +-- api.Formatter (SPI interface)
  +-- config/marker.txt         (resource: parent-data)
  |
  +-- PluginLoader (child)
        |
        +-- plugin.PluginFormatter.class
        +-- META-INF/services/api.Formatter
        +-- config/marker.txt   (resource: plugin-data)
~~~

Ta muốn xác minh:

- Parent load được **`api.Formatter`** và child dùng **cùng runtime API type**, không tự định nghĩa một bản SPI khác.
- `PluginLoader.getResource("config/marker.txt")` theo delegation mặc định có thể trả **parent resource**.
- `PluginLoader.findResource("config/marker.txt")` (nếu là `URLClassLoader`) tìm nguồn URL **riêng child**.
- `PluginLoader.getResources("config/marker.txt")` có thể cho thấy **cả hai tài nguyên**, không chỉ kết quả đầu.
- `ServiceLoader.load(api.Formatter.class, parent)` không tìm provider của plugin vì descriptor/class ở child.
- `ServiceLoader.load(api.Formatter.class, pluginLoader)` tìm đúng **một provider**, khởi tạo được và provider implement đúng runtime SPI.
- `ServiceLoader.load(api.Formatter.class)` dùng **thread context class loader (TCCL)**; đặt đúng pluginLoader trong phạm vi có kiểm soát giúp tìm provider; cuối cùng phải restore TCCL.

Đây là một **contract test của loader architecture**: nếu bất kỳ assertion nào khác dự kiến, cần xem lại cấu trúc classpath, descriptor, parent chain, runtime types hoặc resource policy.

## 2. Các API resource có quy tắc đường dẫn khác nhau

### 2.1. `ClassLoader.getResource(String)`

~~~java
URL url = pluginLoader.getResource("config/marker.txt");
~~~

Đây là mảnh minh họa, cần biến `pluginLoader` đã có và import `java.net.URL`.

- Nhận tên resource theo **path từ gốc search path**, sử dụng dấu `/`.
- Trả **một URL** hoặc `null`.
- Hành vi mặc định của `ClassLoader` hỏi parent trước, rồi tới `findResource` của loader hiện tại.
- Nếu parent và child đều chứa resource cùng tên, **parent có thể che child**.
- Trong named modules, những resource thuộc package của named module có thể chịu quy tắc `opens` và encapsulation; có URL physical không đồng nghĩa ClassLoader API nhất thiết trả nó.

### 2.2. `ClassLoader.getResources(String)`

~~~java
Enumeration<URL> urls =
        pluginLoader.getResources("config/marker.txt");
~~~

- Trả `Enumeration<URL>` nhiều ứng viên, có thể gồm parent và child.
- Dùng khi kiểm chứng **trùng resource names** hoặc định dạng có nhiều files cùng tên.
- Không tự coi thứ tự enumeration là priority nghiệp vụ lâu dài nếu plugin architecture có custom overrides.
- Bảo đảm đóng streams **sau khi mở** từng URL; `getResources` chỉ trả URL enumeration, không phải mọi streams đã mở.

Kiểm đếm:

~~~java
List<URL> all = Collections.list(
        pluginLoader.getResources("config/marker.txt"));

System.out.println("resource candidates: " + all.size());
~~~

Đây là mảnh minh họa với imports `java.util.List`, `java.util.Collections`.

### 2.3. `URLClassLoader.findResource(String)`

~~~java
URL own = pluginLoader.findResource("config/marker.txt");
~~~

Ở đây giả định biến `pluginLoader` có kiểu `URLClassLoader`. API `findResource` trên `URLClassLoader` được public và tìm **resource trong URL search path của loader ấy**, không đi hỏi parent như `getResource` mặc định. Với classloader subclass khác, `findResource` thường là protected hook và không nhất thiết gọi được từ host.

**Không kết luận:** `findResource` “luôn tốt hơn” `getResource`. Chỉ dùng khi **có yêu cầu rõ ràng chọn resource của plugin**, hoặc để debug nguồn. Trong framework mà resource policy riêng đã được định nghĩa, cần tuân thủ policy đó.

### 2.4. `getResourceAsStream(String)`

~~~java
try (InputStream in =
        pluginLoader.getResourceAsStream("config/marker.txt")) {
    if (in == null) {
        throw new IllegalStateException("Missing marker");
    }
    String text = new String(in.readAllBytes(),
            StandardCharsets.UTF_8);
}
~~~

Đây là đoạn minh họa, cần imports `InputStream` và `StandardCharsets`. Stream có thể là `null` nếu không tìm được. **Đọc xong phải đóng**, kể cả khi URLClassLoader được đóng ở cuối vòng đời plugin.

Không cache/chia sẻ một `InputStream` cho mọi thread; nó có trạng thái con trỏ đọc và vòng đời `close`. Nếu muốn cache resource data dùng chung, cache snapshot bytes hoặc immutable representation rồi tạo stream riêng cho mỗi caller.

### 2.5. `Class.getResource` và tên tương đối package

Giả sử class `plugin.PluginFormatter` ở package `plugin`:

~~~java
Class<?> type =
        pluginLoader.loadClass("plugin.PluginFormatter");

// Relative với package plugin:
URL a = type.getResource("settings.txt");

// Absolute từ root:
URL b = type.getResource("/plugin/settings.txt");

// ClassLoader nhận root-relative name, KHÔNG có slash đầu:
URL c = pluginLoader.getResource("plugin/settings.txt");
~~~

Đây là mảnh minh họa; các URL chỉ khác null khi file thực sự có ở đúng path.

| Lời gọi | Resource name được tra |
|---|---|
| `PluginFormatter.class.getResource("settings.txt")` | `plugin/settings.txt` |
| `PluginFormatter.class.getResource("/plugin/settings.txt")` | `plugin/settings.txt` |
| `pluginLoader.getResource("plugin/settings.txt")` | `plugin/settings.txt` |
| `pluginLoader.getResource("settings.txt")` | `settings.txt` ở root |

**Không trộn quy ước này** khi viết test: `ClassLoader.getResource("/plugin/settings.txt")` không phải cách truyền path chuẩn như `Class.getResource("/plugin/settings.txt")`.

## 3. Resource có trên đĩa không có nghĩa nằm trong artifact runtime

Một lỗi hay gặp là code source có:

~~~text
src/main/resources/config/marker.txt
~~~

nhưng artifact chạy không chứa:

~~~text
config/marker.txt
~~~

`javac` biên dịch `.java`, **không mặc nhiên copy mọi file text** vào output class directory. Gradle/Maven có resource processing riêng; khi dùng lệnh `javac` trực tiếp cần copy resource thủ công.

Nếu phân phối plugin JAR, kiểm tra:

~~~bash
jar --list --file dist/plugin.jar
~~~

Các entry phải có tên dùng dấu `/`, ví dụ:

~~~text
plugin/PluginFormatter.class
META-INF/services/api.Formatter
config/marker.txt
~~~

**`META-INF/services` là dữ liệu resource, không phải class Java.** Nó phải nằm đúng trong JAR/thư mục mà loader dùng để khám phá providers.

Nếu `getResource` trả `null`, kiểm tra theo thứ tự:

1. Name có dùng `/` đúng không?
2. Tệp đã được copy vào runtime artifact chưa?
3. URL root/classpath root có đang trỏ đúng cấp thư mục không?
4. Loader có nhìn thấy nguồn hay chỉ parent/child/sibling loader khác nhìn thấy?
5. Named-module resource có bị package encapsulation hạn chế không?
6. Resource lookup policy có bị subclass override theo hướng khác không?

## 4. SPI và ServiceLoader: kiểm chứng thêm metadata, không chỉ bytecode

**Service Provider Interface (SPI)** là một interface/abstract class mô tả hợp đồng, ví dụ:

~~~java
package api;

public interface Formatter {
    String format();
}
~~~

Provider:

~~~java
package plugin;

public final class PluginFormatter implements api.Formatter {
    public PluginFormatter() {
    }

    @Override
    public String format() {
        return "plugin-provider";
    }
}
~~~

Với **classpath/unnamed-module provider**, tệp đăng ký cần là:

~~~text
META-INF/services/api.Formatter
~~~

và nội dung:

~~~text
plugin.PluginFormatter
~~~

Đúng hai loại “tên”:

- **Tên file descriptor:** binary name của service `api.Formatter`.
- **Nội dung mỗi dòng:** binary name đầy đủ của provider `plugin.PluginFormatter`.

Không dùng `plugin/PluginFormatter.class` làm dòng provider config. File config được mã hóa UTF-8; comment dùng `#`, dòng trống được bỏ qua; provider duplicate names được lọc theo quy tắc API.

**ServiceLoader không quét toàn bộ các class để tìm mọi `implements Formatter`.** Nó khám phá qua resource descriptor và module metadata.

### Tìm đúng descriptor

~~~java
Enumeration<URL> descriptors = pluginLoader.getResources(
        "META-INF/services/api.Formatter");
~~~

Nếu không có descriptor, hãy tìm nguyên nhân ở **resource visibility/packaging**, không lập tức sửa constructor reflection.

### Provider phải cùng runtime service type

Với hai class loaders khác nhau:

~~~text
Host interface:   (api.Formatter, AppLoader)
Plugin interface: (api.Formatter, PluginLoader)
~~~

Dù cùng tên, đó là **hai interfaces khác nhau** nếu đều tự define. Provider implement bản plugin thì `api.Formatter.class.isAssignableFrom(providerClass)` từ host có thể trả `false`.

Thiết kế đúng: **shared SPI được parent loader định nghĩa**, plugin loader delegate việc nạp API về parent, chỉ tự define implementation.

### Provider constructor trong classpath mode

Ở unnamed module/classpath, provider class cần phù hợp yêu cầu `ServiceLoader`, thường là **public class có public constructor không tham số** và assignable về SPI. Nếu descriptor chỉ tới class không phải subtype, thiếu constructor hoặc provider không thể initialize, iterator/stream của ServiceLoader có thể ném `ServiceConfigurationError`.

Kiểm tra:

~~~java
Class<?> providerClass = pluginLoader.loadClass(
        "plugin.PluginFormatter");

System.out.println(api.Formatter.class
        .isAssignableFrom(providerClass));
~~~

Đây là mảnh minh họa cần `api.Formatter` và `pluginLoader` đã tồn tại. `true` chứng minh assignability theo các runtime class identities đang dùng; nó không bảo đảm constructor/provider invocation không thất bại.

## 5. Cách ServiceLoader chọn class loader

### `ServiceLoader.load(SPI.class, loader)`

~~~java
ServiceLoader<api.Formatter> found =
        ServiceLoader.load(api.Formatter.class, pluginLoader);
~~~

Đây là **explicit loader mode**. Dùng khi đã biết plugin loader chính xác và muốn tránh phụ thuộc trạng thái thread bên ngoài.

### `ServiceLoader.load(SPI.class)`

~~~java
ServiceLoader<api.Formatter> found =
        ServiceLoader.load(api.Formatter.class);
~~~

Overload một tham số dùng **thread context class loader (TCCL)** ở thread hiện tại. Trong một plugin runtime:

- TCCL có thể là application loader, không thấy plugin descriptors.
- TCCL có thể được framework đặt thành plugin loader, thấy providers.
- TCCL có thể là loader cũ sau một lần redeploy nếu thread pool không restore context.

Đừng cho rằng TCCL luôn bằng system class loader hay defining loader của SPI.

### Đặt TCCL có scope và restore

~~~java
Thread thread = Thread.currentThread();
ClassLoader before = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    ServiceLoader<api.Formatter> providers =
            ServiceLoader.load(api.Formatter.class);
    // Duyệt providers ở đây.
} finally {
    thread.setContextClassLoader(before);
}
~~~

Đây là mảnh minh họa. Phải **restore trong `finally`** để thread pool/request tiếp theo không bị rò rỉ loader context.

### Lazy discovery và cache

Lời gọi `ServiceLoader.load(...)` thường tạo đối tượng ServiceLoader; việc khám phá và instantiate providers diễn ra khi iterate hoặc dùng stream. Do đó:

~~~java
ServiceLoader<api.Formatter> services =
        ServiceLoader.load(api.Formatter.class, pluginLoader);

// Chưa được bảo đảm mọi provider đã instantiate.
for (api.Formatter formatter : services) {
    System.out.println(formatter.format());
}
~~~

Các lỗi provider configuration có thể xuất hiện **ở lần iterate**, không nhất thiết ngay tại `load`. Khi kiểm thử, phải thật sự **duyệt iterator/stream**, không chỉ assert ServiceLoader instance != null.

`reload()` xóa cache của ServiceLoader instance; nó **không tự redefine Java classes, unload classloader hoặc rebuild JAR**. ServiceLoader bản thân **không thread-safe** nếu nhiều threads dùng chung/iterate/reload cùng instance mà thiếu synchronization.

## 6. Ví dụ Java 17+ chạy thật: parent resource khác child resource, provider chỉ ở child

Thiết kế test harness:

~~~text
                App loader
             /     |       \
        api.Formatter    host code
             |          config/marker.txt = parent-data
             |
        URLClassLoader child
              |
         plugin.PluginFormatter.class
         config/marker.txt = plugin-data
         META-INF/services/api.Formatter
              |
        ServiceLoader with explicit loader/TCCL
~~~

Kết quả sẽ chứng minh **thành công của classloading không đủ để suy ra resource/source/provider semantics**.

### 6.1. Cấu trúc source files

~~~text
project/
  src/
    api/
      api/
        Formatter.java
    plugin/
      plugin/
        PluginFormatter.java
    host/
      ResourceAndProviderCheck.java
  resources/
    host/
      config/
        marker.txt
    plugin/
      config/
        marker.txt
      META-INF/
        services/
          api.Formatter
  out/
    api/
    host/
    plugin/
~~~

### 6.2. File `src/api/api/Formatter.java`

~~~java
package api;

public interface Formatter {
    String format();
}
~~~

### 6.3. File `src/plugin/plugin/PluginFormatter.java`

~~~java
package plugin;

import api.Formatter;

public final class PluginFormatter implements Formatter {
    public PluginFormatter() {
    }

    @Override
    public String format() {
        return "plugin-provider";
    }
}
~~~

### 6.4. File `resources/host/config/marker.txt`

~~~text
parent-data
~~~

### 6.5. File `resources/plugin/config/marker.txt`

~~~text
plugin-data
~~~

Hai resources cố ý dùng **cùng relative path** `config/marker.txt` nhưng khác nội dung để test thứ tự delegation.

### 6.6. File `resources/plugin/META-INF/services/api.Formatter`

~~~text
plugin.PluginFormatter
~~~

Descriptor chỉ đặt ở plugin source, **không** đặt trong host output. Như vậy ServiceLoader dùng parent sẽ không tìm provider này, nhưng child có URL đúng sẽ tìm thấy.

### 6.7. File `src/host/ResourceAndProviderCheck.java`

~~~java
import api.Formatter;

import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Collections;
import java.util.List;
import java.util.ServiceLoader;

public final class ResourceAndProviderCheck {
    private static final String DATA = "config/marker.txt";
    private static final String DESCRIPTOR =
            "META-INF/services/api.Formatter";

    static String read(URL url) throws IOException {
        if (url == null) {
            return "(missing)";
        }

        try (InputStream input = url.openStream()) {
            return new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8).strip();
        }
    }

    static int count(ServiceLoader<Formatter> loader) {
        int result = 0;
        for (Formatter ignored : loader) {
            result++;
        }
        return result;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: ResourceAndProviderCheck <plugin-dir>");
        }

        ClassLoader parent = Formatter.class.getClassLoader();
        URL pluginRoot = Path.of(args[0]).toAbsolutePath()
                .toUri().toURL();

        try (URLClassLoader child = new URLClassLoader(
                "plugin", new URL[]{pluginRoot}, parent)) {

            System.out.println("parent resource: "
                    + read(parent.getResource(DATA)));

            System.out.println("child getResource: "
                    + read(child.getResource(DATA)));

            System.out.println("child findResource: "
                    + read(child.findResource(DATA)));

            List<URL> all = Collections.list(
                    child.getResources(DATA));

            System.out.println("resource candidates: "
                    + all.size());

            List<URL> descriptors = Collections.list(
                    child.getResources(DESCRIPTOR));

            System.out.println("provider descriptors: "
                    + descriptors.size());

            System.out.println("parent providers: "
                    + count(ServiceLoader.load(
                            Formatter.class, parent)));

            ServiceLoader<Formatter> services =
                    ServiceLoader.load(Formatter.class, child);

            int providerCount = 0;

            for (Formatter service : services) {
                providerCount++;

                System.out.println("provider value: "
                        + service.format());

                System.out.println("provider defined by child: "
                        + (service.getClass().getClassLoader()
                           == child));
            }

            System.out.println("explicit child providers: "
                    + providerCount);

            Class<?> apiFromChild =
                    child.loadClass("api.Formatter");

            System.out.println("shared SPI identity: "
                    + (apiFromChild == Formatter.class));

            Thread thread = Thread.currentThread();
            ClassLoader previous =
                    thread.getContextClassLoader();

            try {
                thread.setContextClassLoader(child);

                System.out.println("TCCL providers: "
                        + count(ServiceLoader.load(
                                Formatter.class)));
            } finally {
                thread.setContextClassLoader(previous);
            }

            System.out.println("TCCL restored: "
                    + (thread.getContextClassLoader()
                       == previous));
        }
    }
}
~~~

### 6.8. Compile và copy resources

Các lệnh sau chạy từ thư mục `project` bằng **Bash trên Linux/macOS** hoặc môi trường Bash tương thích:

~~~bash
mkdir -p out/api out/host/config
mkdir -p out/plugin/config out/plugin/META-INF/services

javac -d out/api src/api/api/Formatter.java

javac -cp out/api -d out/plugin \
    src/plugin/plugin/PluginFormatter.java

javac -cp out/api -d out/host \
    src/host/ResourceAndProviderCheck.java

cp resources/host/config/marker.txt \
    out/host/config/marker.txt

cp resources/plugin/config/marker.txt \
    out/plugin/config/marker.txt

cp resources/plugin/META-INF/services/api.Formatter \
    out/plugin/META-INF/services/api.Formatter

java -cp "out/api:out/host" \
    ResourceAndProviderCheck out/plugin
~~~

**Điều kiện quan trọng:**

- `out/api` và `out/host` thuộc **application classpath**.
- `out/plugin` **không** được đưa vào `-cp`; nó chỉ xuất hiện trong URL search path của child.
- Cả parent và child chứa `config/marker.txt`, nhưng chỉ child chứa descriptor và provider implementation.
- Plugin compile dựa vào `out/api` nhưng artifact plugin **không copy `api/Formatter.class`**, vì SPI phải được parent định nghĩa một lần.

Trên Windows PowerShell, dùng `New-Item -ItemType Directory -Force` để tạo thư mục và `Copy-Item` để copy resources. Thay classpath separator `:` thành `;`:

~~~powershell
java -cp "out/api;out/host" ResourceAndProviderCheck out/plugin
~~~

### 6.9. Stdout dự kiến với đúng cấu trúc trên

~~~text
parent resource: parent-data
child getResource: parent-data
child findResource: plugin-data
resource candidates: 2
provider descriptors: 1
parent providers: 0
provider value: plugin-provider
provider defined by child: true
explicit child providers: 1
shared SPI identity: true
TCCL providers: 1
TCCL restored: true
~~~

**Đọc và hiểu kết quả:**

1. **`parent resource: parent-data`:** parent loader nhìn resource tại `out/host/config/marker.txt`.
2. **`child getResource: parent-data`:** URLClassLoader mặc định dùng parent-first resource lookup; bản của parent được chọn.
3. **`child findResource: plugin-data`:** `findResource` bỏ qua parent để tìm trong URL search path của child.
4. **`resource candidates: 2`:** `getResources` cho thấy cả hai candidates; trong cấu hình test, đúng hai file cùng path.
5. **`provider descriptors: 1`:** chỉ plugin có `META-INF/services/api.Formatter`; chứng minh descriptor nằm trong search scope của child.
6. **`parent providers: 0`:** parent không thấy child plugin descriptor, nên không biết provider.
7. **`provider value: plugin-provider`:** ServiceLoader không chỉ thấy descriptor mà còn load và instantiate được provider.
8. **`provider defined by child: true`:** implementation class thuộc child; không bị parent che.
9. **`explicit child providers: 1`:** chỉ một provider đã đăng ký trong test fixture.
10. **`shared SPI identity: true`:** child delegate `api.Formatter` về parent; host và provider dùng cùng runtime interface.
11. **`TCCL providers: 1`:** overload `ServiceLoader.load(Formatter.class)` dùng TCCL tạm thời là child.
12. **`TCCL restored: true`:** cuối cùng thread được trả về context loader cũ, không giữ child plugin loader trong thread pool.

**Không hard-code kết quả này cho mọi ứng dụng:** nếu parent classpath vô tình chứa một provider cùng SPI, nếu có thêm JAR cung cấp descriptor hoặc URLClassLoader có policy tùy biến, số candidates/providers và thứ tự có thể khác. Đây là stdout dự kiến của **fixture độc lập với các file đúng như hướng dẫn**.

### 6.10. Đóng plugin thành JAR để kiểm chứng packaging

Thay child directory bằng JAR:

~~~bash
mkdir -p dist

jar --create --file dist/formatter-plugin.jar -C out/plugin .

jar --list --file dist/formatter-plugin.jar

java -cp "out/api:out/host" \
    ResourceAndProviderCheck dist/formatter-plugin.jar
~~~

JAR phải chứa ít nhất:

~~~text
plugin/PluginFormatter.class
config/marker.txt
META-INF/services/api.Formatter
~~~

Host chuyển đối số thành `URL` bằng `Path.toUri().toURL()` nên có thể dùng **directory hoặc JAR** làm URL source. Với fixture tương đương, các assertions/output giữ nguyên.

## 7. Vì sao phải kiểm riêng provider descriptor và provider class?

`ServiceLoader` hoạt động qua nhiều giai đoạn:

~~~text
ServiceLoader.load(SPI, loader)
                  |
                  v
       ServiceLoader instance
                  |
                  v
     Iterator / Stream được duyệt
                  |
                  v
 Tìm META-INF/services/<SPI binary name>
                  |
                  v
 Đọc tên provider implementation
                  |
                  v
 class loader tìm class implementation
                  |
                  v
 Kiểm tra assignability về runtime SPI
                  |
                  v
 Instantiate provider
                  |
                  v
 Return service object
~~~

Một test chỉ assert `ServiceLoader.load(...) != null` **hầu như vô nghĩa** để chứng minh provider đã tìm được. Một ServiceLoader trống vẫn là object khác `null`.

Cần các assert riêng:

- Descriptor URL tồn tại trong đúng loader scope.
- Descriptor có UTF-8 và provider binary names hợp lệ.
- Provider class load được và defining loader đúng.
- Provider là subtype của **chính SPI `Class<?>` của consumer**.
- Constructor/factory đúng mode và chạy được.
- Iterate thực sự trả provider với expected behavior.

Nếu một bước thất bại, đừng gộp mọi nguyên nhân thành “ClassLoader không hoạt động”.

## 8. Các negative tests đáng có

### 8.1. Thiếu file descriptor

Giữ `plugin/PluginFormatter.class` nhưng bỏ:

~~~text
META-INF/services/api.Formatter
~~~

Kết quả:

- `child.loadClass("plugin.PluginFormatter")` vẫn có thể thành công.
- `ServiceLoader.load(Formatter.class, child)` không khám phá provider này vì thiếu registration.
- Test `provider descriptors == 0` giúp khoanh vùng packaging.

Đây là **tình huống biến thể**, không phải output của fixture chuẩn.

### 8.2. Descriptor đặt sai tên

Sai:

~~~text
META-INF/services/Formatter
~~~

Đúng:

~~~text
META-INF/services/api.Formatter
~~~

Tên file phải là **binary name đầy đủ của SPI**. Việc package folder của provider đúng không giúp nếu descriptor name sai.

### 8.3. Descriptor chứa sai provider name

Sai:

~~~text
plugin/PluginFormatter.class
~~~

Đúng:

~~~text
plugin.PluginFormatter
~~~

Nếu ServiceLoader đọc descriptor nhưng không tìm được tên provider, có thể ném `ServiceConfigurationError` **khi iterate**, thay vì trả empty list. Cần bắt/log lỗi ở boundary của plugin chứ không nuốt.

### 8.4. Provider không assignable về SPI

Nếu plugin được nạp theo child-first policy và tự define thêm bản `api.Formatter`, provider có thể implement **một runtime interface khác**:

~~~text
(api.Formatter, ParentLoader)
(api.Formatter, ChildLoader)
~~~

Cùng tên source/binary không đủ. `Formatter.class.isAssignableFrom(providerClass)` từ host sẽ `false`; ServiceLoader có thể ném `ServiceConfigurationError` khi provider type không phù hợp.

**Fix:** shared SPI do một loader chung định nghĩa; child delegate về đó. Không chỉ copy cùng interface bytes vào mỗi plugin JAR.

### 8.5. Provider constructor lỗi

Trong unnamed-module/classpath mode, provider thường cần **public no-arg constructor** và class public phù hợp. Nếu thiếu hoặc constructor ném exception, có thể sinh `ServiceConfigurationError` khi ServiceLoader instantiate provider.

Test bắt buộc phải duyệt providers thật, không dừng ở descriptor URL. Với named modules, explicit module providers còn có provider factory method theo quy tắc riêng; **không dùng nhầm quy tắc provider factory của JPMS cho unnamed-module descriptor**.

### 8.6. Resource bị parent che

Cả parent và child có:

~~~text
config/marker.txt
~~~

`getResource` trả bản parent theo mặc định. Test phải phân biệt:

- **Resource visibility:** có tìm được resource không?
- **Resource ownership/source:** bản nào được chọn?
- **Resource content:** bytes có đúng version/môi trường không?

Không chỉ assert `getResource(...) != null`. Nếu ứng dụng phải dùng config private của plugin, kiểm tra resource URL hoặc dùng namespace/lookup API có chủ đích.

### 8.7. TCCL sai trong thread pool

Một test chỉ chạy main thread có thể pass, nhưng production sử dụng thread pool có TCCL khác. Nếu thư viện gọi `ServiceLoader.load(SPI.class)`, kết quả có thể thay đổi theo thread.

Test cần tạo task với TCCL được đặt trước, verify provider count rồi **restore trong finally**, không để context của plugin A rò sang request plugin B.

### 8.8. Duplicate descriptors và thứ tự provider

Khi nhiều JAR cung cấp cùng SPI, `getResources("META-INF/services/SPI")` có thể trả nhiều URLs. ServiceLoader có thể tổng hợp provider names và bỏ qua khai báo trùng theo quy tắc.

Đừng giả định “provider đầu tiên” luôn là provider ưu tiên trong business logic. Nếu cần chọn implementation, thu thập danh sách provider và sử dụng **policy tường minh** (ID/priority/compatible version/capabilities) thay vì phụ thuộc classpath order ngoài kiểm soát.

## 9. Tạo bộ assertion tự động cho CI

Trong test suite (JUnit hoặc một `main` tự kiểm tra như demo), nên thiết kế assertion theo tầng:

| Tầng | Assertion | Nguyên nhân nó bảo vệ |
|---|---|---|
| Artifact | JAR có class + resource + descriptor | Tránh thiếu file từ build |
| Binary name | `loadClass("plugin.PluginFormatter")` thành công | Đúng package/classpath root |
| Defining loader | `providerClass.getClassLoader() == pluginLoader` | Provider thuộc plugin |
| Shared SPI | `pluginLoader.loadClass("api.Formatter") == Formatter.class` | Không duplicate API |
| Parent resource | Nội dung `parent-data` | Parent view đúng |
| Child own resource | Nội dung `plugin-data` | Plugin file được đóng gói |
| Delegated resource | `getResource` trả expected parent content | Thứ tự mặc định đúng |
| All resources | Có đúng hai URLs trong fixture | Phát hiện collisions |
| Provider descriptor | Descriptor URL count đúng | Registration nhìn thấy được |
| ServiceLoader parent | Không có provider plugin | Parent không nhìn xuống child |
| ServiceLoader child | Có đúng một provider | Discovery + instantiate |
| TCCL | Overload một tham số thấy provider khi set child | Thread context đúng |
| Lifecycle | TCCL được restore, URL loader đóng sau dùng | Không giữ loader thừa |

### Kiểm tra robust thay vì hard-code ngoài fixture

Với test fixture có dữ liệu cố định, `== 2` hoặc `== 1` là kiểm tra tốt. Nhưng với ứng dụng thật, test nên dùng **nguồn artifact đã biết**, giới hạn root và clear runtime dependencies để không chịu ảnh hưởng của plugins khác.

Nếu có custom resource lookup policy, expected order có thể **khác URLClassLoader mặc định**; khi đó test phải mô tả chính sách mong muốn rồi kiểm tra theo contract, không áp dụng mù quáng “parent luôn thắng” cho mọi loader subclass.

## 10. Phân biệt classpath provider và named-module provider

Ví dụ đầy đủ ở trên chạy theo **classpath / unnamed-module mode**. Với JPMS named modules, provider registration có thể nằm trong `module-info.java`:

~~~java
module formatter.consumer {
    requires formatter.api;
    uses api.Formatter;
}
~~~

Provider module:

~~~java
module formatter.provider {
    requires formatter.api;
    provides api.Formatter with plugin.PluginFormatter;
}
~~~

Đây là **hai file module-info.java minh họa**, không phải tệp thay thế cho classpath demo. Module graph/layer phải được resolve phù hợp.

### Khác biệt cần kiểm chứng với JPMS

- Consumer named module cần `uses api.Formatter;` khi sử dụng ServiceLoader theo module model.
- Provider module khai báo `provides api.Formatter with plugin.PluginFormatter;`.
- Provider module phải được **resolved** trong module layer mà ServiceLoader tìm.
- `ServiceLoader.load(ModuleLayer layer, Formatter.class)` có quy tắc tìm trong layer/parent layers khác với `load(SPI, ClassLoader)`.
- Không coi `META-INF/services` và `provides` là hai cách luôn tương đương trong mọi module configuration.
- Provider trong explicit named module có thể sử dụng **public static provider() factory method** đúng điều kiện theo JDK specification; đó không phải quy tắc constructor chung của mọi classpath providers.

### Module resource encapsulation

Đối với resource trong **named module package**, `ClassLoader.getResource` có thể chỉ thấy resource khi package được mở theo yêu cầu của API (trừ một số đường dẫn đặc biệt như `.class` theo hợp đồng). Do đó:

~~~java
URL url = loader.getResource("p/secret.txt");
~~~

trả `null` **không nhất thiết** có nghĩa file `p/secret.txt` không tồn tại trong module artifact.

Khi kiểm thử modular resources, xem:

1. Module có tên và được resolved không?
2. Resource nằm trong package nào?
3. `opens`/`exports`/readability được cấu hình thế nào?
4. API đang dùng là `Module.getResourceAsStream`, `Class.getResourceAsStream` hay `ClassLoader.getResource`?
5. Lookup được thực hiện từ caller module nào và theo rule nào?

Không sử dụng `--add-opens` như một “fix chung” cho mọi resource path sai, và không trộn module access error với duplicate classloader SPI identity.

## 11. ServiceLoader, TCCL và lifecycle khi hot redeploy

Trong hệ plugin, thường có những generation liên tiếp:

~~~text
Generation 1:
  URLClassLoader-A -> provider-A
          |
          +-- ServiceLoader cache / TCCL / callbacks

Generation 2:
  URLClassLoader-B -> provider-B
          |
          +-- provider mới
~~~

Nếu host còn giữ `ServiceLoader` của generation A, provider instances hoặc TCCL trỏ tới loader A, classloader cũ có thể chưa được GC/unload ngay dù đã gọi `URLClassLoader.close()`.

**Lưu ý kỹ thuật:**

- `ServiceLoader.reload()` reset provider cache của ServiceLoader instance, **không unload/redefine Java classes**.
- `URLClassLoader.close()` đóng JAR/file handles của loader, **không buộc class unloading**.
- `getResourceAsStream` streams cần đóng riêng.
- Plugin tasks/threads, scheduled jobs, callbacks, ThreadLocals và cached Class/Method objects có thể giữ loader sống.
- Thread context class loader cần restore sau khi gọi framework/ServiceLoader trong phạm vi plugin.
- Khi đóng loader, tránh đồng thời còn thread khác đang load class; API không bảo đảm kết quả xác định cho concurrent close/load.

Một lifecycle tốt:

~~~text
ACTIVE
   |
   v
DRAINING (ngừng request mới; đợi jobs hoàn tất)
   |
   +-- close resource streams
   +-- stop tasks/threads
   +-- remove provider/listener callbacks
   +-- restore TCCL
   +-- drop ServiceLoader/provider caches
   +-- URLClassLoader.close()
   |
   v
RETIRED (drop strong references)
   |
   v
GC có thể unload khi đủ điều kiện, không cam kết ngay
~~~

Nếu plugin resources hoặc service provider data được cập nhật sang version mới, **tạo loader generation mới** có thể là cách đúng; không giả định sửa file JAR trên đĩa làm loader cũ tự nhìn thấy mọi version mới.

## 12. Chẩn đoán cụ thể khi kiểm thử thất bại

### `getResource` trả null

Hỏi:

- Resource path đúng root relative không?
- File có trong class output/JAR không?
- URL của child có đúng và accessible không?
- Package resource thuộc named module có cần `opens` không?
- Subclass có override `findResource` hoặc `getResource` sai không?

### `getResource` có URL nhưng đọc sai config

- In URL được trả về, không chỉ data content.
- So `getResource` với `findResource`.
- Dùng `getResources` để thấy parent/child candidates.
- Đặt resource private dưới namespace không xung đột hoặc chọn rõ source.
- Kiểm tra cache và version/generation.

### Descriptor tồn tại nhưng ServiceLoader trống

- Có đang dùng **đúng SPI class** không?
- Loader truyền cho ServiceLoader có nhìn thấy descriptor không?
- Descriptor có tên đầy đủ `META-INF/services/<binary-name>` không?
- Có đang chạy named modules mà phải dùng `uses`/`provides` không?
- Có chạm tới iterator/stream để kích hoạt lazy discovery chưa?

### ServiceLoader ném `ServiceConfigurationError`

- Descriptor có provider binary name hợp lệ không?
- Provider class có được loader tìm thấy không?
- Provider có subtype của **đúng runtime SPI** không?
- Constructor/provider method có đúng mode/visibility không?
- Có `NoClassDefFoundError`/`ExceptionInInitializerError`/lỗi dependency ẩn bên trong không?
- Có duplicate API class được child-first nạp riêng không?

**Không catch toàn bộ `Throwable` rồi coi lỗi như “không có provider”.** Nó che linkage, native, memory và initialization failures nghiêm trọng. Hãy giữ stack trace/cause chain và ghi artifact/loader identity.

### Lỗi chỉ xảy ra trong một thread

- Ghi `Thread.currentThread().getContextClassLoader()`.
- Ghi defining loader của SPI và provider.
- Thử `ServiceLoader.load(SPI.class, explicitPluginLoader)`.
- Kiểm tra restore TCCL trong thread pools.
- Đảm bảo không có generation cũ còn trong callbacks/caches.

## 13. Công cụ quan sát để xác nhận

**Log resource URLs:**

~~~java
Enumeration<URL> urls =
        pluginLoader.getResources("config/marker.txt");
while (urls.hasMoreElements()) {
    System.out.println(urls.nextElement());
}
~~~

Đây là mảnh minh họa; thứ tự/đường dẫn tuyệt đối tùy máy, do đó không phù hợp hard-code nguyên chuỗi URL vào test cross-platform.

**Log defining loaders:**

~~~java
Class<?> impl =
        pluginLoader.loadClass("plugin.PluginFormatter");

System.out.println(impl.getName());
System.out.println(impl.getClassLoader());
System.out.println(impl.getModule());
~~~

**Log SPI identity:**

~~~java
Class<?> viaChild = pluginLoader.loadClass("api.Formatter");

System.out.println(viaChild == api.Formatter.class);
~~~

**Kiểm tra JAR:**

~~~bash
jar --list --file dist/formatter-plugin.jar
~~~

**JVM classloading logs (HotSpot JDK 17):**

~~~bash
java -Xlog:class+load=info \
    -cp "out/api:out/host" ResourceAndProviderCheck out/plugin
~~~

Các lệnh chẩn đoán có thể in class names, sources và runtime details, nhưng **không tự thay thế kiểm chứng provider descriptor/resources**; classloading log không liệt kê đầy đủ nội dung mọi text resource hoặc nguyên nhân mỗi ServiceLoader failure.

## 14. Những ngộ nhận thường gặp

1. **“`loadClass` thành công thì `getResource` chắc chắn thành công.”** Sai: resource lookup là đường khác.
2. **“Resource có trong thư mục `src/resources` tức có trong JAR.”** Sai: phải copy/package.
3. **“`ClassLoader.getResource("x.txt")` tìm từ package của class đang gọi.”** Sai: root-relative.
4. **“`Class.getResource("x.txt")` luôn tìm từ root.”** Sai: không có slash đầu là tương đối package.
5. **“Child-first class lookup sẽ tự child-first resource lookup.”** Sai: overrides riêng.
6. **“`getResource` cho thấy toàn bộ candidate URLs.”** Sai: dùng `getResources`.
7. **“`findResource` của URLClassLoader cũng hỏi parent.”** Sai: nó tìm ở URLs của chính loader.
8. **“Chỉ cần provider class implements SPI là ServiceLoader tự quét thấy.”** Sai: phải đăng ký descriptor/JPMS provides.
9. **“`META-INF/services` đặt tên theo provider class.”** Sai: đặt theo **SPI binary name**.
10. **“Provider config liệt kê file path `plugin/Impl.class`.”** Sai: dòng chứa binary name `plugin.Impl`.
11. **“`ServiceLoader.load` đã chứng minh provider instantiate được.”** Sai: lazy lookup/instantiation khi iterate.
12. **“ServiceLoader.load(SPI.class)` luôn dùng system class loader.”** Sai: dùng TCCL.
13. **“Đặt TCCL một lần trên thread pool rồi khỏi restore.”** Sai: gây cross-plugin visibility và lifecycle leak.
14. **“Hai interface `api.Formatter` cùng source ở hai loaders là một.”** Sai: runtime identity khác.
15. **“Provider descriptor có trong JAR chắc chắn provider chạy được.”** Sai: constructor/type/linkage/dependencies có thể lỗi.
16. **“`ServiceConfigurationError` là tín hiệu có zero providers bình thường.”** Sai: thường là provider configuration/loading problem.
17. **“Đọc URL từ child mà thấy parent config là JVM đọc sai.”** Không: parent-first resource lookup mặc định.
18. **“Named-module resource rules giống hoàn toàn classpath resources.”** Sai: JPMS encapsulation có thể hạn chế.
19. **“`ServiceLoader.reload()` unload class/plugin ngay.”** Sai: chỉ reset cache.
20. **“`URLClassLoader.close()` sẽ GC loader ngay.”** Sai: còn reference/lifecycle/GC.

## 15. Checklist kiểm chứng khi hoàn thiện một plugin

- [ ] SPI được định nghĩa trong shared API thuộc loader cha phù hợp.
- [ ] Plugin artifact không tự định nghĩa lại SPI khi chính sách child-first không kiểm soát.
- [ ] Provider class được đóng gói đúng package path.
- [ ] `META-INF/services/<SPI binary name>` tồn tại đúng tên và UTF-8.
- [ ] Provider config liệt kê đúng binary implementation names.
- [ ] Provider có public no-arg constructor phù hợp classpath mode hoặc JPMS provider method đúng mode.
- [ ] Test thực sự iterate providers và assert behavior, không chỉ assert ServiceLoader != null.
- [ ] Test provider defining loader, SPI assignability và runtime type identity.
- [ ] Test parent provider visibility khác child khi kiến trúc yêu cầu.
- [ ] Test parent resource và child own resource dưới cùng path.
- [ ] Test `getResource`, `findResource` và `getResources` riêng.
- [ ] Assert đúng content/hash của resource, không chỉ URL != null.
- [ ] Đóng streams sau khi đọc.
- [ ] Test TCCL selected provider count và restore.
- [ ] Test missing descriptor, malformed provider names và constructor/linkage failures.
- [ ] Test duplicate provider registrations/candidate resource order khi có nhiều JAR.
- [ ] Test đóng gói JAR cuối, không chỉ source folder.
- [ ] Nếu dùng named modules, kiểm tra `uses`/`provides`, module resolution/layer và `opens` cho resources khi cần.
- [ ] Có log source URLs, loader identities và provider errors.
- [ ] Có lifecycle clean-up/redeploy không giữ loader cũ qua TCCL hoặc caches.
- [ ] Không dùng resource/path test không đáng tin từ file system làm thay thế runtime lookup thật.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Cả parent và child đều chứa `config/marker.txt`. Vì sao `child.getResource("config/marker.txt")` có thể trả bản parent?

**Đáp án:** Vì ClassLoader resource lookup mặc định tìm parent trước. `URLClassLoader.findResource` có thể dùng để tìm resource trong URL riêng của child.

**Câu 2.** `getResource` và `getResources` khác nhau thế nào?

**Đáp án:** `getResource` trả một URL đầu hoặc null; `getResources` trả Enumeration các URLs được nhìn thấy theo cơ chế loader.

**Câu 3.** Vì sao `type.getResource("settings.txt")` khác `loader.getResource("settings.txt")`?

**Đáp án:** Class API ghép package của `type` khi tên không bắt đầu bằng `/`; ClassLoader API tra từ root search path.

**Câu 4.** Provider class có trong JAR và implement SPI nhưng ServiceLoader không tìm. Kiểm gì trước?

**Đáp án:** `META-INF/services/<SPI binary name>` hoặc `provides` trong JPMS, tên provider đầy đủ, loader/TCCL nhìn thấy descriptor, và việc thật sự iterate ServiceLoader.

**Câu 5.** Provider do child định nghĩa và SPI do parent định nghĩa. Host có thể cast provider về SPI không?

**Đáp án:** Có nếu provider implement **chính runtime SPI type** do parent định nghĩa và method/access rules đúng. Không cần provider implementation class thuộc parent.

**Câu 6.** Tại sao một file provider descriptor đúng vẫn có thể gây `ServiceConfigurationError`?

**Đáp án:** Provider class không tìm thấy, không subtype của SPI, thiếu constructor phù hợp, lỗi initialization, dependency/linkage hoặc cú pháp config lỗi.

**Câu 7.** Cần test `ServiceLoader.load(SPI.class)` từ thread pool khác. Yếu tố gì quan trọng?

**Đáp án:** TCCL của thread; đặt/restore có scope và tránh loader cũ giữ lại sau task.

**Câu 8.** Nếu `getResource` trả null cho một named-module resource, có chắc file đã bị xóa không?

**Đáp án:** Không. Resource có thể bị JPMS encapsulation/`opens` hạn chế, hoặc path/loader không đúng.

**Câu 9.** `ServiceLoader.reload()` có thay bytecode provider đã nạp không?

**Đáp án:** Không. Nó reset provider cache của instance ServiceLoader, không redefine class hoặc unload defining loader.

**Câu 10.** Vì sao CI phải chạy với JAR được đóng gói cuối cùng thay vì chỉ test `src/main/resources`?

**Đáp án:** Resource config/descriptors có thể bị quên copy hoặc build packaging sai; runtime lookup dùng artifact cuối, không quét source folders.

## 17. Mô hình quyết định kiểm chứng

~~~text
             Plugin provider không hoạt động
                         |
             Java class có thể load?
                  /              \
                Không             Có
                 |                 |
             check URL          check resource
             root/name         + descriptor
                                   |
                     getResource/findResource/getResources
                                   |
                      đúng config source?
                             /       \
                           Không       Có
                            |          |
                      resource policy  ServiceLoader iterate
                                        |
                              provider được tìm?
                                  /        \
                                Không       Có
                                 |          |
                          descriptor/TCCL  kiểm type identity,
                          module graph     constructor/behavior
                                            |
                                      stop/redeploy:
                                      close streams,
                                      restore TCCL,
                                      clear cached refs
~~~

**Kết luận:** Kiểm chứng resource và service provider là kiểm chứng **toàn bộ đường dữ liệu**, từ artifact, loader visibility, URL source, provider descriptor đến runtime SPI type và lifecycle. Với plugin classloader, phải kiểm tra riêng **`loadClass`, `getResource`/`findResource`/`getResources` và `ServiceLoader`**; những API này không tự động có cùng chính sách tìm kiếm. Một test harness có parent/child chứa resource trùng path và descriptor chỉ ở child sẽ cho thấy ngay các lỗi ẩn mà một test nạp class đơn giản bỏ sót.

### Tài liệu chính thức

- [Java SE 17 — ClassLoader: getResource/getResources/getResourceAsStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 17 — URLClassLoader: findResource và close](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html)
- [Java SE 17 — Class.getResource](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getResource(java.lang.String))
- [Java SE 17 — ServiceLoader: classpath providers/TCCL/JPMS](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
- [Java SE 17 — Module.getResourceAsStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html#getResourceAsStream(java.lang.String))
- [JLS 17 7.7 — uses/provides module declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7)

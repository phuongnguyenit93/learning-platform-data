# Phân chia ứng dụng chủ, API chung và triển khai plugin bằng ClassLoader

## 1. Vấn đề kiến trúc: host gọi plugin mà không phụ thuộc implementation

Giả sử một ứng dụng Java cần tải thêm tính năng sau khi ứng dụng đã được phát hành: bộ xuất dữ liệu, bộ phân tích nội dung, connector, driver hoặc bộ xử lý tùy chọn. Nếu ứng dụng chủ (**host**) import trực tiếp từng class implementation, mọi lần thêm plugin đều kéo theo sửa mã host, thay đổi dependency graph và có thể gây xung đột phiên bản thư viện.

Một kiến trúc plugin bền vững tách ba vai trò:

1. **Ứng dụng chủ (host):** điều phối vòng đời, tìm và chọn plugin, gọi nghiệp vụ qua hợp đồng, quản lý lỗi, tài nguyên và phiên bản.
2. **API chung (shared API/SPI):** kiểu giao tiếp ổn định — interface, DTO, exception hoặc metadata mà **cả host và plugin cùng nhìn thấy dưới một runtime class identity**.
3. **Triển khai plugin (implementation):** code tính năng, dependencies riêng, service provider, class/resources chỉ cần xuất hiện trong ClassLoader của plugin.

Một mô hình phổ biến:

~~~text
             Application/Parent ClassLoader
            +---------------------------------+
            | Host: plugin.host.PluginHost     |
            | API:  plugin.api.Plugin          |
            | API:  các DTO / contract khác    |
            +---------------------------------+
                         |
                         | parent delegation, chia sẻ API
                         v
             Child ClassLoader plugin A
            +---------------------------------+
            | plugin.impl.EchoPlugin          |
            | plugin-specific classes/JARs   |
            | META-INF/services/...          |
            +---------------------------------+

             Child ClassLoader plugin B
            +---------------------------------+
            | plugin.other.ReportPlugin       |
            | dependency version riêng        |
            +---------------------------------+
~~~

**Nguyên tắc quan trọng nhất:** host và plugin phải dùng **cùng `Class<?>` object** cho kiểu `plugin.api.Plugin`. Chỉ trùng tên `plugin.api.Plugin` hoặc giống bytecode không đủ; một interface cùng tên do hai defining ClassLoader khác nhau tạo ra là **hai runtime types khác nhau**.

Mục tiêu bài: thiết kế ba phần và dependency boundary; thực thi ví dụ Java 17+ nạp plugin từ JAR không nằm trong system classpath; hiểu `ServiceLoader`, parent delegation, đóng gói API, lỗi type identity, version compatibility, quản lý vòng đời và cách mở rộng bằng JPMS khi cần.

## 2. Trách nhiệm cụ thể của ba phần

### 2.1. Host: người điều phối, không sở hữu implementation

Host biết **contract** của plugin, chẳng hạn:

~~~java
Plugin plugin = /* instance do discovery tạo */;
String result = plugin.execute("hello");
~~~

Đây là đoạn **minh họa bên trong một method**, chưa phải chương trình độc lập; `Plugin` thuộc API chung.

Host thường chịu trách nhiệm:

- Chọn thư mục/artifact plugin được phép nạp và xác định phiên bản tương thích.
- Tạo hoặc chọn ClassLoader/module layer cho mỗi plugin hoặc nhóm plugin.
- Khám phá implementation dựa trên metadata, `ServiceLoader` hoặc registry.
- Kiểm tra API version, quyền truy cập và điều kiện khởi tạo.
- Khởi tạo/khởi động, quản lý request, dừng và thu hồi tài nguyên plugin.
- Xử lý lỗi và không để một plugin thất bại làm vô hiệu toàn bộ host nếu kiến trúc cho phép.

**Host không nên cần import `plugin.impl.EchoPlugin`** để biên dịch. Nếu import implementation cụ thể, host có thể vẫn chạy được nhưng đã phá vỡ mục tiêu thay plugin độc lập.

### 2.2. Shared API: điểm hẹn kiểu dữ liệu

Contract nhỏ, ổn định:

~~~java
package plugin.api;

public interface Plugin {
    String id();
    String execute(String input);
}
~~~

API cần nằm trong một artifact/version do host quản lý và **được ClassLoader chung, thường là parent, định nghĩa một lần**.

Đặc điểm API tốt:

- Chứa interface, enums, DTO hoặc abstractions đủ dùng; **không chứa chi tiết engine/vendor của plugin**.
- Các kiểu xuất hiện trong method signatures cũng phải chia sẻ identity, ví dụ `PluginRequest`, `PluginResponse`, `PluginException`.
- Không yêu cầu host biết private implementation classes.
- Có policy versioning và compatibility: binary/source/API contract, default methods khi thích hợp, feature negotiation hoặc manifest version.
- Nếu API cần được cả hai phía gọi, nó phải visible theo classpath/module rules thích hợp.

**Cần chú ý signature closure:** không chỉ `Plugin.class`, mà toàn bộ kiểu trong tham số, return type, callbacks và exceptions crossing boundary cũng cần kiến trúc class identity phù hợp. Nếu interface được parent định nghĩa nhưng một DTO lại bị đóng gói riêng vào cả host và plugin, vẫn có thể xảy ra `ClassCastException` hoặc `LinkageError`.

### 2.3. Plugin implementation: code thay thế được

Ví dụ:

~~~java
package plugin.impl;

import java.util.Locale;
import plugin.api.Plugin;

public final class EchoPlugin implements Plugin {
    @Override
    public String id() {
        return "echo";
    }

    @Override
    public String execute(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
~~~

Plugin chỉ cần compile-time access đến `plugin.api.Plugin`. Ứng dụng host không cần compile-time dependency đến `EchoPlugin`.

Các thư viện nội bộ mà plugin cần có thể đặt trong JAR implementation hoặc được bố trí thành các JAR độc lập mà **plugin loader thực sự nhìn thấy**. Đừng nhầm khai báo dependency của build tool với đường classpath/loader của JVM ở runtime.

## 3. Quy tắc ClassLoader khiến kiến trúc này hoạt động

### 3.1. Runtime type identity

Một runtime class thường được nhận diện bằng cặp:

~~~text
(binaryName, definingClassLoader)
~~~

Ví dụ, nếu host loader `L_host` định nghĩa `plugin.api.Plugin`:

~~~text
Plugin_host = ("plugin.api.Plugin", L_host)
~~~

Nếu plugin loader `L_plugin` **tự định nghĩa thêm một bản API trùng tên**:

~~~text
Plugin_plugin = ("plugin.api.Plugin", L_plugin)
~~~

thì:

~~~text
Plugin_host != Plugin_plugin
~~~

Dù source interface giống hệt, đối tượng triển khai bản `Plugin_plugin` **không tự trở thành instance của** `Plugin_host`. Host ép kiểu có thể ném `ClassCastException`; `ServiceLoader` có thể báo provider **not a subtype** bằng `ServiceConfigurationError`.

**Thiết kế đúng:** `L_plugin` **ủy quyền load** những package contract (`plugin.api.*`) cho loader mà host sử dụng. Trong parent-first `URLClassLoader` thông thường, nếu API nằm ở parent và plugin JAR **không chứa bản sao API**, implementation tự nhiên dùng đúng type của host.

### 3.2. Parent delegation và cách chia sẻ API

~~~text
pluginLoader.loadClass("plugin.api.Plugin")
    -> parentLoader.loadClass("plugin.api.Plugin")
    -> trả lại Class<Plugin> mà host cũng dùng

pluginLoader.loadClass("plugin.impl.EchoPlugin")
    -> parent không có class implementation
    -> child tìm trong plugin JAR
    -> class EchoPlugin do child định nghĩa
~~~

Cơ chế của `URLClassLoader` thường theo parent-first delegation. Tuy nhiên framework/containers có thể dùng child-first hoặc delegation tùy namespace. Vì vậy, **không đủ khi chỉ nói “plugin loader là child”**: nếu chính sách child-first chọn bản API trong plugin JAR, identity vẫn có thể bị chia đôi.

Một cách phòng ngừa là quản lý rõ các namespace:

- `java.*` và platform APIs: không được tùy ý shadow.
- `plugin.api.*` và các shared SDK packages: luôn delegating tới loader chung.
- `plugin.impl.*` và private dependencies: lấy từ loader thuộc plugin khi phù hợp.
- Các shared library khác: xác định rõ dùng chung hay cho phép phiên bản riêng; đừng vô tình tạo API có signature phụ thuộc vào type chỉ tồn tại ở một plugin.

### 3.3. ClassLoader không phải ranh giới bảo mật

ClassLoader hỗ trợ tra cứu class, type identity và một mức cô lập namespace. Nó **không** là sandbox đủ để chạy plugin không đáng tin: code Java trong cùng process có thể truy cập tài nguyên hệ thống theo quyền của tiến trình, tiêu thụ CPU/RAM, tạo threads và tương tác với thư viện chung.

Đối với plugin của bên thứ ba không đáng tin, xem xét **process isolation**, OS/container permissions, resource quotas, ký/xác minh artifacts và giao thức IPC. Đừng dựa trên `ClassLoader` hoặc `SecurityManager` cũ như hàng rào duy nhất.

## 4. Tổ chức mã và artifacts: một API, hai phía phụ thuộc

Một layout đơn giản:

~~~text
project/
├── src/
│   ├── api/
│   │   └── plugin/api/Plugin.java
│   ├── host/
│   │   └── PluginHost.java
│   └── plugin/
│       └── plugin/impl/EchoPlugin.java
├── build/
│   ├── api/
│   ├── host/
│   └── plugin/
│       ├── plugin/impl/EchoPlugin.class
│       └── META-INF/services/plugin.api.Plugin
└── dist/
    └── plugin-echo.jar
~~~

**Đồ thị dependency khi biên dịch:**

~~~text
Shared API module/artifact
       ^             ^
       |             |
      Host         Plugin implementation

Không có compile dependency:
Host ----------> plugin.impl.EchoPlugin
~~~

**Đồ thị runtime/class loaders:**

~~~text
JVM launcher classpath:
    build/host + build/api
    => application loader định nghĩa host và Plugin API

URLClassLoader child:
    dist/plugin-echo.jar
    => implementation + provider descriptor
    => parent = application loader
~~~

Host compile với API; plugin compile với API; nhưng **plugin JAR deploy không cần đóng gói thêm class `plugin/api/Plugin.class`**. Plugin API đã được host cung cấp ở runtime.

Với build tool:

| Vai trò | Dependency hợp lý | Cảnh báo |
|---|---|---|
| Host → shared API | `implementation` / Maven compile | API phải nằm trong host runtime classpath/module graph |
| Plugin → shared API | `compileOnly` (Gradle) hoặc `provided` (Maven), nếu host cam kết cung cấp | Đảm bảo API thật sự có ở parent loader; không để API bản khác vô tình bị nhúng |
| Plugin → private library | Runtime dependency/packaging phù hợp loader plugin | Build resolution không tự làm JVM nhìn thấy JAR nếu deploy thiếu |
| Tests → host/API/implementation | Test dependencies theo từng phần | Test pass không chứng minh classloader layout production tương tự |

Đây là **hướng cấu hình phổ biến**, không bắt buộc cho mọi framework. Với Gradle composite/multi-project, Maven modules hoặc JPMS, cách công bố artifact và scope khác nhau; bạn cần kiểm tra **plugin JAR/distribution cuối** bằng `jar --list` và thử chạy với đúng lệnh JVM.

## 5. Java SPI và ServiceLoader: host tìm implementation mà không import class

Java hỗ trợ Service Provider Interface (**SPI**) dựa trên `java.util.ServiceLoader`. Hai thành phần:

1. **Service type:** interface `plugin.api.Plugin` mà host và provider đều nhận biết.
2. **Provider configuration:** file text tại `META-INF/services/plugin.api.Plugin`, chứa **binary name** của provider class.

Nội dung file:

~~~text
plugin.impl.EchoPlugin
~~~

Tên file phải là **binary name đầy đủ** của service type, không có `.class` hay phần mở rộng khác. Mỗi provider khai báo theo một dòng. Provider class trong ví dụ là public, có public no-arg constructor mặc định và implements đúng service interface runtime.

Host dùng overload:

~~~java
ServiceLoader<Plugin> providers =
        ServiceLoader.load(Plugin.class, pluginLoader);
~~~

**Quan trọng:** overload hai tham số dùng **ClassLoader được truyền tường minh**, không cần hy vọng ambient Thread Context ClassLoader trỏ đúng plugin. Overload một tham số `ServiceLoader.load(Plugin.class)` lại dùng context ClassLoader của current thread và có thể cho kết quả khác.

`ServiceLoader` có lazy discovery/instantiation; lỗi đọc provider hoặc provider không hợp lệ có thể ném `ServiceConfigurationError`. Do đó host production nên lập chính sách xử lý provider errors và đóng tài nguyên, thay vì coi discovery không thể thất bại.

## 6. Thực hành Java 17+ chạy độc lập: host/API/plugin tách ba phần

Đây là thực hành hoàn chỉnh **không cần Maven/Gradle và không tải thư viện từ internet**. Nó kiểm chứng:

- Host classpath chỉ có **host** và **API**, không có plugin implementation.
- Host không tự tìm được implementation bằng application loader.
- Child `URLClassLoader` tìm được plugin từ JAR triển khai.
- `ServiceLoader.load(service, pluginLoader)` phát hiện provider.
- Provider implement **chính interface API object** của host, nên host gọi trực tiếp qua `Plugin` mà không cast reflective.
- Thư viện plugin được dùng mà host **không import** `EchoPlugin`.

### 6.1. File `src/api/plugin/api/Plugin.java`

~~~java
package plugin.api;

public interface Plugin {
    String id();
    String execute(String input);
}
~~~

Đây là hợp đồng chung của cả hệ. Nó dùng `String` để ví dụ gọn; trong ứng dụng thật có thể dùng các DTO không ràng buộc implementation.

### 6.2. File `src/plugin/plugin/impl/EchoPlugin.java`

~~~java
package plugin.impl;

import java.util.Locale;
import plugin.api.Plugin;

public final class EchoPlugin implements Plugin {
    public String id() {
        return "echo";
    }

    public String execute(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
~~~

### 6.3. File provider descriptor

Tạo file:

~~~text
build/plugin/META-INF/services/plugin.api.Plugin
~~~

Nội dung nguyên một dòng (cho phép newline cuối):

~~~text
plugin.impl.EchoPlugin
~~~

Nội dung này phải đi vào **JAR plugin**, không phải chỉ tồn tại ở source tree. Trong ví dụ, tạo file thẳng dưới `build/plugin` sau khi biên dịch là đủ.

### 6.4. File `src/host/PluginHost.java`

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ServiceLoader;
import plugin.api.Plugin;

public final class PluginHost {
    public static void main(String[] args) throws Exception {
        ClassLoader hostLoader = PluginHost.class.getClassLoader();
        System.out.println("hostApiLoaderSame="
                + (hostLoader == Plugin.class.getClassLoader()));

        try {
            Class.forName("plugin.impl.EchoPlugin", false, hostLoader);
            System.out.println("hostCannotLoadPlugin=false");
        } catch (ClassNotFoundException expected) {
            System.out.println("hostCannotLoadPlugin=true");
        }

        URL pluginUrl = Path.of("dist/plugin-echo.jar").toUri().toURL();
        try (URLClassLoader pluginLoader =
                     new URLClassLoader(new URL[] { pluginUrl }, hostLoader)) {
            int count = 0;
            for (Plugin plugin : ServiceLoader.load(Plugin.class, pluginLoader)) {
                count++;
                System.out.println("pluginImplLoaderIsChild="
                        + (plugin.getClass().getClassLoader() == pluginLoader));
                System.out.println("sharedApiIdentity="
                        + (plugin.getClass().getInterfaces()[0] == Plugin.class));
                System.out.println("pluginId=" + plugin.id());
                System.out.println("result=" + plugin.execute("hello"));
            }
            System.out.println("pluginsFound=" + count);
        }
    }
}
~~~

**Một số chi tiết quan trọng:**

- `PluginHost` chỉ import `plugin.api.Plugin`. Nó không import hoặc trực tiếp new `EchoPlugin`.
- Gọi `Class.forName(..., false, hostLoader)` có chủ đích minh họa application loader không tìm được plugin. Nó **không** yêu cầu initialization.
- `URLClassLoader` được truyền URL JAR plugin và parent `hostLoader`. Trong classpath setup này, `plugin.api.Plugin` đến từ parent.
- `ServiceLoader.load(Plugin.class, pluginLoader)` tìm provider metadata bằng loader được chỉ định và instantiate provider khi duyệt.
- `getInterfaces()[0]` là phép kiểm tra đủ dùng **cho đúng class `EchoPlugin` trong ví dụ**, nơi class trực tiếp chỉ implements một interface. Trong code production không được giả định interface đầu tiên trong mảng luôn là API; có thể dùng `Plugin.class.isAssignableFrom(providerClass)` khi phù hợp.
- `try-with-resources` đóng `URLClassLoader` sau khi đã dùng. Nó đóng tài nguyên loader, **không bảo đảm các class/plugin objects được unload ngay lập tức**.

### 6.5. Biên dịch và đóng gói trên Linux/macOS

Đứng trong thư mục `project` (với đúng cây source đã mô tả):

~~~sh
mkdir -p build/api build/host build/plugin/META-INF/services dist

javac --release 17 -d build/api \
    src/api/plugin/api/Plugin.java

javac --release 17 -cp build/api -d build/plugin \
    src/plugin/plugin/impl/EchoPlugin.java

printf 'plugin.impl.EchoPlugin\n' \
    > build/plugin/META-INF/services/plugin.api.Plugin

jar --create --file dist/plugin-echo.jar -C build/plugin .

javac --release 17 -cp build/api -d build/host \
    src/host/PluginHost.java

java -cp "build/host:build/api" PluginHost
~~~

Dấu `:` là separator classpath Linux/macOS; dấu `\` cuối dòng là nối lệnh POSIX shell, không dùng tương tự trong PowerShell.

### 6.6. Biên dịch và chạy trên Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force build/api, build/host, build/plugin/META-INF/services, dist | Out-Null

javac --release 17 -d build/api src/api/plugin/api/Plugin.java

javac --release 17 -cp build/api -d build/plugin src/plugin/plugin/impl/EchoPlugin.java

[System.IO.File]::WriteAllText(
    "build/plugin/META-INF/services/plugin.api.Plugin",
    "plugin.impl.EchoPlugin" + [Environment]::NewLine,
    [System.Text.UTF8Encoding]::new($false)
)

jar --create --file dist/plugin-echo.jar -C build/plugin .

javac --release 17 -cp build/api -d build/host src/host/PluginHost.java

java -cp "build/host;build/api" PluginHost
~~~

PowerShell mẫu phía trên yêu cầu môi trường chạy JDK 17+ và PowerShell có hỗ trợ cú pháp constructor `::new` (Windows PowerShell 5+ hoặc PowerShell 7). Nếu dùng CMD, tạo provider file bằng công cụ text tương ứng và dùng `;` trong `-cp`.

### 6.7. Stdout chính xác đã kiểm chứng

~~~text
hostApiLoaderSame=true
hostCannotLoadPlugin=true
pluginImplLoaderIsChild=true
sharedApiIdentity=true
pluginId=echo
result=HELLO
pluginsFound=1
~~~

Mã trong thực hành đã được biên dịch với `javac --release 17` và chạy thành công bằng JDK. Không cần plugin JAR có `Main-Class`, vì host là executable entry point; `plugin-echo.jar` là **provider artifact**, không phải chương trình độc lập.

### 6.8. Vì sao từng dòng quan trọng?

| Output | Bằng chứng |
|---|---|
| `hostApiLoaderSame=true` | Host và shared API được defining loader chung nạp |
| `hostCannotLoadPlugin=true` | Plugin implementation không có trên application classpath |
| `pluginImplLoaderIsChild=true` | Child `URLClassLoader` định nghĩa implementation |
| `sharedApiIdentity=true` | Interface mà implementation trực tiếp implements là **chính `Plugin.class`** host sử dụng |
| `pluginId=echo` | Plugin được tạo và gọi qua interface thành công |
| `result=HELLO` | Host đã chạy nghiệp vụ qua contract, không cần import implementation |
| `pluginsFound=1` | Provider descriptor/JAR/ServiceLoader lookup hoạt động đúng, phát hiện đúng một provider |

Không in `ClassLoader.toString()` hay đường file tuyệt đối vì chúng có thể khác giữa các máy/JDK; ví dụ xác minh bằng **object identity** và logic nghiệp vụ.

### 6.9. Kiểm tra artifact đã đóng gói

~~~sh
jar --list --file dist/plugin-echo.jar
~~~

Những entry quan trọng:

~~~text
plugin/impl/EchoPlugin.class
META-INF/services/plugin.api.Plugin
~~~

**Không nên có** `plugin/api/Plugin.class` trong plugin JAR của kiến trúc này. Nếu có, trong parent-first URLClassLoader của demo API parent vẫn có thể thắng, nhưng một child-first loader hoặc framework khác có thể nạp bản trùng vào child và tạo hai interface types. Vì thế nên đặt điều kiện packaging rõ từ đầu.

Trong production, kiểm tra thêm implementation dependencies, resource collisions, duplicate providers và các đường `META-INF/services` khi dùng shaded/uber JAR. Công cụ shading cần **merge service descriptors** nếu nhiều thư viện cùng công bố provider.

## 7. Mở rộng sang nhiều plugin và các chiến lược loader

Có ba cách bố trí tùy nhu cầu. **Một loader chung** đơn giản khi toàn bộ plugin được phát hành cùng nhau và dùng dependency tương thích, nhưng cùng binary name chỉ có một định nghĩa trong loader ấy. **Một loader riêng cho mỗi plugin** phù hợp khi cần phiên bản thư viện khác nhau, nâng cấp hoặc dừng riêng; vẫn phải bảo đảm shared API do parent định nghĩa. **JPMS `ModuleLayer`** có chiến lược một hoặc nhiều loader cho modules và khai báo `uses`/`provides`, khác với classpath SPI dùng `META-INF/services`. Việc chọn mô hình, kiểm thử trùng tên và đánh đổi giữa isolation, state và memory được thực hành chuyên sâu trong các bài tiếp theo.

## 8. Vòng đời plugin: load, dùng, dừng và unload

Host quản lý các trạng thái `DISCOVERED → VALIDATED → LOADED → STARTED → STOPPING → STOPPED → RELEASED`, có rollback khi khởi động lỗi. Trước khi đóng loader, host phải chặn công việc mới, drain/cancel các tác vụ đang chạy, gọi stop hooks, hủy đăng ký callbacks/listeners, đóng streams/connections/executors, dọn `ThreadLocal`/TCCL/caches, rồi bỏ references. `URLClassLoader.close()` đóng tài nguyên loader quản lý nhưng không buộc JVM unload class hay dừng thread. Các bài về khởi tạo, shutdown và hot reload đi sâu vào cơ chế này; ở đây trách nhiệm then chốt là **host sở hữu vòng đời**, plugin cung cấp hooks/cleanup theo contract.

## 9. Tính tương thích phiên bản API và phụ thuộc riêng của plugin

API chung cần **binary compatibility** giữa host và mọi plugin đang deploy. Xóa method, đổi JVM descriptor hoặc constructor/record components có thể tạo `NoSuchMethodError`, `AbstractMethodError` hay lỗi linkage, dù cùng shared loader. Plugin riêng có thể dùng `codec v1/v2` ở loader khác nhau nếu không để `codec.*` lọt qua method signature của SPI; hãy map chúng sang shared DTO/schema tại boundary. Một plugin lỗi có thể gây exception, deadlock hoặc tiêu thụ tài nguyên, nên host phải có lỗi/timeout/quota policy; loader riêng chỉ hỗ trợ namespace và dependency isolation. Nếu có nhiều API versions không tương thích, cần migration/adapter hoặc hợp đồng version mới, không chỉ đổi JAR.

## 10. Quy trình debug plugin không hoạt động

### 10.1. Xác nhận đúng artifacts và loader

1. Host đã build **chỉ phụ thuộc shared API**, hay còn import implementation class?
2. API JAR/classes có ở **parent/runtime** của host không?
3. Plugin JAR có `plugin/impl/EchoPlugin.class` và provider descriptor `META-INF/services/plugin.api.Plugin` không?
4. API class có bị **đóng gói trùng** vào plugin implementation artifact không?
5. `URLClassLoader` hoặc custom loader nhận đúng URLs/resources của plugin chưa? Nested JAR không tự được nạp bằng standard `URLClassLoader` nếu không có launcher hiểu cấu trúc.
6. `Plugin.class.getClassLoader()` và `provider.getClass().getInterfaces()[0].getClassLoader()` có đúng quan hệ parent-shared không? (Chỉ dùng trực tiếp `getInterfaces()[0]` khi biết cấu trúc provider.)
7. `Plugin.class.isInstance(provider)` có true không?
8. ServiceLoader đang dùng overload tường minh hay TCCL? Plugin còn trên đúng loader lúc enumerate providers không?
9. API version và private dependency runtime có khớp artifact thực sự deploy không?
10. Plugin có stop hooks/resources/threads còn giữ loader cũ không?

### 10.2. Bảng lỗi và hướng kiểm tra

| Triệu chứng | Nguyên nhân đáng kiểm tra | Hướng xử lý |
|---|---|---|
| `ServiceLoader` trả 0 providers | Thiếu/sai descriptor, provider chưa ở runtime loader path | Kiểm tra `META-INF/services`, tên nhị phân, JAR layout, loader |
| `ServiceConfigurationError: not a subtype` | Provider implements **bản API khác loader** hoặc provider config sai | So identity `Plugin.class` từ host và interface từ provider |
| `ClassCastException: plugin.impl.EchoPlugin cannot be cast to plugin.api.Plugin` | Split API identity hoặc provider không implement interface thật | Bắt plugin API do parent định nghĩa; loại duplicate API |
| `ClassNotFoundException` trên implementation | Child loader không thấy JAR/classpath sai, binary name sai | Xem loader URLs, artifact và package names |
| `NoClassDefFoundError` khi gọi plugin | Thiếu private transitive dependency, lỗi initialization trước đó | Đọc `Caused by` và các class/library còn thiếu |
| `NoSuchMethodError`/`AbstractMethodError` | API/plugin binary version không tương thích | So compiled ABI và artifacts runtime |
| `IllegalAccessError`/`InaccessibleObjectException` | Java access/JPMS exports/opens | Kiểm tra package, defining loader, module rules |
| Một plugin đổi làm plugin khác hỏng | Loader shared không tách được dependency versions | Cân nhắc loader riêng cho mỗi plugin và shared API ổn định |
| Plugin cũ vẫn sống sau reload | Registry, TCCL, threads, ServiceLoader/cache giữ references | Stop, cleanup, close loader, loại bỏ references |
| Local IDE chạy tốt, deploy không thấy plugin | IDE classpath khác launcher/JAR distribution | Chạy artifact phát hành và kiểm tra command thực tế |
| Plugin class trùng tên với parent | Parent-first ưu tiên host class hoặc child-first tạo type duplicate | Xác định namespace/delegation policy rõ |

### 10.3. Một phép chẩn đoán nhanh bằng code

~~~java
static void inspectPlugin(Class<?> api, Object plugin) {
    Class<?> impl = plugin.getClass();
    System.out.println("api=" + api.getName());
    System.out.println("apiLoader=" + api.getClassLoader());
    System.out.println("impl=" + impl.getName());
    System.out.println("implLoader=" + impl.getClassLoader());
    System.out.println("apiAssignable=" + api.isInstance(plugin));
}
~~~

Đây là **method minh họa**, đặt trong một class thích hợp. `toString()` của ClassLoader hữu ích để debug nhưng không phải ID chuẩn; khi cần kiểm tra chính xác, so reference identity trực tiếp. Nếu ứng dụng có multiple module layers, in thêm `api.getModule()` và `impl.getModule()`.

## 11. Sai lầm kiến trúc phổ biến

Những lỗi đáng kiểm tra trước khi phát hành: host import trực tiếp implementation; plugin JAR gói bản shared API bị child-first tự định nghĩa; private library type xuất hiện trong public method signature; thiếu `META-INF/services` hoặc runtime plugin URLs; dùng nhầm TCCL khi discovery; không kiểm tra API binary compatibility; close loader trong khi plugin đang chạy; giữ listener/thread/caches sau stop; xem `ClassLoader` là sandbox bảo mật. Mỗi trường hợp cần xác minh **defining loader, artifact thực tế, service descriptor, runtime exception và lifecycle ownership**. Các bài chuyên sâu tiếp theo cung cấp thí nghiệm từng lỗi.

## 12. Câu hỏi tự kiểm tra và bài tập

1. Ba vai trò host, shared API, implementation cần tách theo nguyên tắc nào?
2. Vì sao host chỉ cần compile dependency tới interface `Plugin` chứ không cần `EchoPlugin`?
3. `Class<?>` identity bao gồm những yếu tố nào? Tại sao hai interfaces trùng binary name vẫn có thể khác nhau?
4. Vì sao shared API phải được nạp từ loader mà cả host/plugin cùng truy cập?
5. Với `URLClassLoader` parent-first, điều gì xảy ra khi child tìm `plugin.api.Plugin`?
6. Nếu plugin JAR cũng chứa `plugin/api/Plugin.class`, rủi ro gì xuất hiện với child-first loader?
7. `META-INF/services/plugin.api.Plugin` cần chứa nội dung gì?
8. `ServiceLoader.load(Plugin.class, pluginLoader)` và `ServiceLoader.load(Plugin.class)` khác nhau về loader selection ra sao?
9. Trong ví dụ, tại sao `hostCannotLoadPlugin=true` vẫn có thể có `pluginsFound=1`?
10. `sharedApiIdentity=true` chứng minh điều gì vượt quá phép so binary names?
11. Vì sao plugin JAR không cần manifest `Main-Class`?
12. Gradle `compileOnly` hoặc Maven `provided` phù hợp khi nào với API mà host cung cấp?
13. Nếu plugin A/B dùng versions khác nhau của codec, khi nào việc tạo hai plugin loaders riêng hữu ích?
14. Vì sao không nên để private codec class xuất hiện ở public method signatures của Plugin API?
15. Khi ServiceLoader báo `not a subtype`, cần kiểm tra classloader của interface nào?
16. Vì sao chỉ đóng `URLClassLoader` không đảm bảo plugin cũ được garbage-collected?
17. TCCL có tự đổi ClassLoader của class đã được define không? Khi nào ServiceLoader dùng TCCL?
18. Nếu muốn chuyển sang JPMS, những descriptor directives nào tương ứng API, host và implementation?
19. Nếu plugin là code không đáng tin, ClassLoader riêng có thay thế process isolation không?
20. Trong một ứng dụng plugin production, bạn cần thêm những quy tắc nào cho versioning, resource limits, shutdown và observability?

**Tiêu chí hoàn thành:** bạn tự biên dịch ba source sets Java 17+, đóng gói đúng provider JAR, chạy host và giải thích đủ bảy dòng stdout; vẽ được dependency graph và classloader hierarchy; chỉ ra cách giữ shared API identity, cấu hình `ServiceLoader`, tách private dependencies và quản lý plugin lifecycle.

## 13. Tài liệu tham khảo chính thức

- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, runtime loader semantics, `loadClass`.
- [Java SE 21 — URLClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): nạp class/resources từ JAR/directory URLs, đóng tài nguyên.
- [Java SE 21 — ServiceLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html): service/provider contract, configuration file, overload theo loader/layer, ServiceConfigurationError.
- [Java SE 21 — ModuleLayer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html): module layers và loader mapping cho JPMS.
- [JVMS Java SE 21 — Loading/Linking](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html): defining/initiating loaders, runtime identity và loading constraints.
- [Gradle Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): API/implementation dependency separation khi thiết kế multi-project builds.
- [Maven Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): scopes như `compile`, `provided`, `runtime`, `test`.

**Kết luận:** plugin architecture không chỉ là “tạo một ClassLoader”. Kiến trúc hoạt động bền vững khi **host sở hữu hợp đồng chung**, **ClassLoader hierarchy thống nhất runtime identity của API**, còn **implementation và private dependencies** được đóng gói/nạp/lifecycle theo policy riêng. Ví dụ được kiểm chứng với Java 17-compatible bytecode; các biến thể framework/JPMS cần chọn API discovery và module/loader mapping phù hợp.
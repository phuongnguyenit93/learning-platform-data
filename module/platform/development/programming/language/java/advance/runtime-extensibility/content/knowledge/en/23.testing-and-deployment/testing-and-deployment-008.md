# Chuyển khỏi lib/ext, java.ext.dirs và giả định application loader là URLClassLoader

Khi nâng một hệ thống Java 8 có cơ chế tải thư viện hoặc plugin động lên Java 17+, ba giả định cũ có thể làm ứng dụng thất bại **ngay khi khởi động** hoặc chỉ lỗi ở đường sử dụng plugin:

1. “Chép JAR vào `$JAVA_HOME/lib/ext` là JVM tự thấy.” **Không còn đúng từ JDK 9**: extension mechanism đã bị loại bỏ.
2. “Có thể trỏ `-Djava.ext.dirs=...` tới thư mục extension riêng.” **Không còn là cách cấu hình hợp lệ**: launcher/compiler của JDK hiện đại từ chối cơ chế cũ.
3. “`ClassLoader.getSystemClassLoader()` trả `URLClassLoader`; cast rồi gọi `getURLs()` hoặc tìm cách `addURL`.” **Không phải hợp đồng Java SE**; application class loader mặc định trong JDK 9+ không còn là `URLClassLoader`.

Ba lỗi này liên quan trực tiếp tới **kiểm thử và triển khai kiến trúc mở rộng runtime**: một JAR có thể được đóng gói đúng nhưng không nằm trên bất kỳ đường tìm kiếm hợp lệ nào; hoặc code cố ép kiểu loader bị `ClassCastException` trước cả khi mở plugin.

Hướng chuyển đổi an toàn là **chọn rõ cơ chế triển khai**: classpath cho thư viện legacy; module path và `ModuleLayer` cho named modules; hoặc một `URLClassLoader` do ứng dụng **tự tạo, tự sở hữu và tự đóng** cho plugin classpath. Phần nghiệp vụ nên thao tác qua contract `ClassLoader`/SPI thay vì phụ thuộc implementation nội bộ của loader hệ thống.

Bài Knowledge này giải thích thay đổi của JDK, lập bảng thay thế cấu hình, cung cấp demo Java 17 chạy độc lập, rồi xây checklist kiểm thử cho migration và plugin deployment.

## 1. Trước JDK 9: extension mechanism thực sự làm gì?

Ở Java 8 và trước đó, JVM có **installed extensions mechanism**: JAR được đặt trong các extension directories được class loader extension tìm thấy mà ứng dụng không cần liệt kê từng JAR trên application classpath. Ví dụ thói quen triển khai cũ:

```text
<JAVA_HOME>/
    jre/lib/ext/
        vendor-codec.jar
        shared-plugin.jar

hoặc:
    java -Djava.ext.dirs=/opt/company/extensions -cp app.jar com.example.Main
```

Đây là **sơ đồ lịch sử**, không phải lệnh dành cho Java 17. Vị trí thư mục tùy bản phân phối/layout JDK/JRE cũ. `java.ext.dirs` dùng để chỉ danh sách thư mục extensions thay vì cấu hình dependency cụ thể cho từng ứng dụng.

Cơ chế này tạo cảm giác tiện lợi nhưng có các chi phí:

- Dependencies bị đặt vào **môi trường Java chung**, khó tái hiện khi chạy test, container hoặc server khác.
- Artifact lạ trong extension directory có thể ảnh hưởng **nhiều ứng dụng** dùng cùng runtime.
- Version conflict khó nhìn thấy nếu hệ thống không quản lý từng JAR và nguồn gốc.
- Plugin được “cài” bằng thay thư mục JDK, làm phức tạp cập nhật, kiểm thử và rollback.
- Loader resolution phụ thuộc cấu hình máy, không nằm rõ trong manifest/deployment descriptor của ứng dụng.

Khi chuyển sang JDK modular runtime, đây không còn là một điểm mở rộng hợp lệ. **Đừng di chuyển máy móc JAR từ `lib/ext` sang một thư mục `lib` khác và giả định JVM sẽ tự quét.** Java không mặc định tự duyệt mọi JAR trong thư mục bất kỳ.

## 2. Thay đổi kể từ JDK 9: cơ chế bị loại bỏ, hierarchy có tên mới

Oracle JDK Migration Guide phân biệt hai thay đổi liên quan nhưng **không đồng nghĩa**:

### 2.1. Extension directory scanning bị loại bỏ

Từ JDK 9, extension mechanism không còn được hỗ trợ. Nếu muốn dùng một JAR từng nằm ở `lib/ext`, phải **đưa nó vào classpath/module path hoặc cơ chế loader do ứng dụng định nghĩa**.

Hướng dẫn migration của Oracle mô tả rằng launcher `java` và compiler `javac` sẽ thoát khi phát hiện cấu hình extension cũ như thuộc tính `java.ext.dirs` hoặc `lib/ext` trong các layout chịu kiểm tra; thông báo chính xác phụ thuộc phiên bản và bản phân phối. Với Java 17 đã kiểm thử, lệnh kiểu:

```bash
java -Djava.ext.dirs=legacy -version
```

**Không phải phương án cấu hình mới**: JVM từ chối thiết lập đó. Việc thử lệnh trên runtime kiểm thử là để **phát hiện cấu hình cũ**, không phải bước bắt buộc khi chạy chương trình demo sau này.

Không nên xử lý lỗi khởi động bằng cách tạo thư mục `lib/ext` mới trong JDK. Hành động đúng là gỡ cấu hình extension cũ, rồi **khai báo các JAR cần thiết trong deployment của ứng dụng**.

### 2.2. Extension class loader đổi vai trò thành platform class loader

Phân cấp khái niệm trong JDK 9+ thường được diễn đạt:

```text
Bootstrap class loader  (thường biểu diễn bằng parent null)
        ^
        |
Platform class loader   ClassLoader.getPlatformClassLoader()
        ^
        |
Application/system class loader   ClassLoader.getSystemClassLoader()
        ^
        |
Loader plugin do ứng dụng tạo (nếu có)
```

Đây là mô hình minh họa của runtime mặc định, **không phải lời hứa mọi custom class loader đều có đúng cây này**. JDK 9+ có `ClassLoader.getPlatformClassLoader()`; nó thay vị trí/khái niệm class loader extensions cũ trong hierarchy nhưng **không tiếp tục tự quét `lib/ext`**.

Platform loader cung cấp khả năng truy cập các classes cần thiết trong platform theo hợp đồng JDK. **Không đồng nhất “visible through platform loader” với “defined by platform loader”**: một số Java SE classes thực tế được bootstrap loader định nghĩa. Code không nên dựa vào loader cụ thể đã định nghĩa từng class platform.

Nếu cần parent cho custom loader tải plugin nhưng plugin có sử dụng **API do application sở hữu**, thường truyền chính **loader của host API**, không tự động truyền platform loader hay `null`:

```java
ClassLoader parent = PluginApi.class.getClassLoader();
URLClassLoader pluginLoader =
        new URLClassLoader(pluginUrls, parent);
```

Đây là **snippet**: `PluginApi`/`pluginUrls` phải được xác định và imports `URLClassLoader`, `URL` phù hợp. Nếu plugin và host phải chia sẻ `PluginApi`, parent này giúp tránh việc plugin nạp một bản API khác. Dùng `null` không phải cách cô lập plugin an toàn; nó có thể làm mất khả năng nhìn thấy host API và các module platform nhất định.

## 3. Application/system loader không còn là URLClassLoader mặc định

Một anti-pattern phổ biến của ứng dụng Java 8:

```java
// Mẫu cũ không portable: có thể ClassCastException trên Java 17.
URLClassLoader app =
        (URLClassLoader) ClassLoader.getSystemClassLoader();

for (URL url : app.getURLs()) {
    System.out.println(url);
}
```

Đoạn trên là **minh họa anti-pattern**, không phải code nên chạy trong production. `ClassLoader.getSystemClassLoader()` có kiểu trả về khai báo **`ClassLoader`**, không phải `URLClassLoader`. Ở JDK 9+, loader application mặc định được implement bằng class nội bộ của JDK, không kế thừa `URLClassLoader`.

Không suy từ một cast thành công trên một JVM cũ rằng JVM khác bắt buộc dùng cùng implementation. Trong runtime cho phép chỉ định custom system loader, hình dạng loader có thể khác; cách lập trình portable là **không ép kiểu khi chỉ cần các method của `ClassLoader`**.

### Những API nên dùng trực tiếp trên ClassLoader

```java
ClassLoader loader = ClassLoader.getSystemClassLoader();

Class<?> c = loader.loadClass("com.example.api.Service");
URL resource = loader.getResource("config/defaults.properties");
java.util.Enumeration<URL> all =
        loader.getResources("META-INF/services/com.example.api.Service");
```

Đây là **snippet** cần imports `URL`, `IOException` và các classes/resources thật. `loadClass` có thể ném `ClassNotFoundException`; `getResource` có thể trả `null`; `getResources` cho enumeration, và API này có thể ném `IOException`.

**Các method trên là hợp đồng chung của `ClassLoader`**; không cần biết loader có danh sách URL hay không. Nếu bạn muốn biết **nguồn artifact nào chứa class/resource**, dùng API tra resource, `Class.getProtectionDomain().getCodeSource()` khi khả dụng, thông tin module/layer và log JVM tùy ngữ cảnh. Không mặc định mọi class có code source URL kiểu `jar:file:...`.

### Không dùng reflection để cưỡng ép sửa loader nội bộ

Một số code legacy phản chiếu vào implementation nội bộ của loader hoặc tìm method `addURL` để bổ sung JAR vào system classpath khi JVM đã khởi động. Đây không phải API chuẩn để chỉnh system loader và có thể bị **strong encapsulation** của JPMS chặn. Đừng coi `--add-opens` là giải pháp lâu dài cho lỗi thiết kế loader: nó chỉ mở quyền reflection tới package được chỉ rõ, không biến JDK internal classes thành public API được bảo đảm ổn định.

**Cần bổ sung JAR động?** Tạo/đổi **loader do ứng dụng sở hữu**, hoặc dùng `ModuleLayer` nếu plugin được triển khai dưới dạng named modules. **Cần classpath chỉ cố định lúc khởi động?** Khai báo bằng launcher/build tool thay vì đột biến system loader khi ứng dụng đang chạy.

## 4. Bảng chuyển đổi: triển khai cũ → mô hình hiện đại

| Giả định/triển khai legacy | Thay bằng | Khi nào phù hợp |
| --- | --- | --- |
| Chép `foo.jar` vào `$JAVA_HOME/lib/ext` | Đưa `foo.jar` vào classpath của ứng dụng hoặc module path | Thư viện cần thiết ngay từ startup |
| `-Djava.ext.dirs=/opt/ext` | `-cp "/opt/ext/*:app.jar"` trên Unix hoặc classpath được build/launcher sinh | Nhiều JAR độc lập nằm trong một thư mục |
| Chèn file vào `lib/ext` lúc ứng dụng đang chạy | Registry + custom loader cho từng plugin generation | Plugin được cài/gỡ/thay thế động |
| `(URLClassLoader) getSystemClassLoader()` | Sử dụng `ClassLoader` API; nếu cần URLs, tự tạo `URLClassLoader` và giữ reference tới nó | Lookup portable, hoặc loader tùy ứng dụng |
| Reflective call tới `addURL` ở system loader | Khai báo startup classpath, hoặc tạo loader mới | Không phụ thuộc JDK internals |
| `sun.misc.Launcher$ExtClassLoader` / `AppClassLoader` | `getPlatformClassLoader()` và `getSystemClassLoader()` qua public API | Truy cập loader cấp platform/application |
| `rt.jar` hoặc `tools.jar` trong classpath | API Java SE modules, `--module-path`/`--add-modules` nếu có nhu cầu | JDK 9+ modular runtime |
| Quét JAR theo thứ tự classpath rồi lấy bản đầu | Ràng buộc artifact/version bằng manifest và registry | Tránh trùng class/resource, deploy lặp |

**Lưu ý syntax đường dẫn:** trên macOS/Linux classpath delimiter là `:`; trên Windows là `;`. Không truyền literal string bao gồm dấu nháy sai theo cú pháp shell. Ví dụ:

```bash
# macOS/Linux: classpath ở thời điểm startup.
java -cp "app.jar:lib/*" com.example.Main
```

```powershell
# Windows PowerShell: classpath ở thời điểm startup.
java -cp "app.jar;lib/*" com.example.Main
```

Đây là **lệnh minh họa**; `app.jar`, `lib/*` và `com.example.Main` phải tồn tại. Wildcard `lib/*` trong classpath được Java launcher mở rộng tới các JAR phù hợp **trong đúng thư mục**, không tự quét đệ quy mọi thư mục con. Thứ tự các JAR được mở rộng không phải hợp đồng quản lý version nên đừng dựa vào wildcard để “chọn đúng plugin” khi có nhiều bản cạnh tranh.

Đưa plugin vào application classpath cũng khiến nó có mặt trong môi trường **chung của ứng dụng**. Nếu cần cài/gỡ/rollback một phiên bản plugin độc lập trong cùng process, dùng loader riêng và lifecycle rõ ràng thay vì đổi classpath toàn JVM.

## 5. Chọn classpath, URLClassLoader riêng hay ModuleLayer?

Đây là quyết định về **phạm vi và vòng đời**, không chỉ về một dòng option.

### A. Classpath tường minh

Phù hợp khi ứng dụng vẫn dùng **unnamed module** và danh sách dependency cố định theo deployment:

```text
build produces:
  app.jar
  lib/codec.jar
  lib/common.jar

startup:
  java -cp "app.jar:lib/*" com.example.Main   (Unix)
  java -cp "app.jar;lib/*" com.example.Main   (Windows)
```

Ưu điểm: dễ cấu hình, tương thích với nhiều JAR Java 8, ít cần sửa code. Hạn chế: JAR vào **cùng application loader** nên không có isolation per plugin; hot-replacement không tự xảy ra khi copy JAR mới.

### B. URLClassLoader do ứng dụng tự tạo

Phù hợp với các **classpath-based plugins** do registry quản lý. Bạn giữ reference của chính `URLClassLoader` mình khởi tạo:

```java
try (URLClassLoader pluginLoader = new URLClassLoader(
        new URL[] { pluginJar.toUri().toURL() },
        PluginApi.class.getClassLoader())) {
    Class<?> type = pluginLoader.loadClass("com.acme.extension.Handler");
    // Khám phá, khởi tạo và sử dụng plugin trong scope này.
}
```

Đây là **snippet**, cần `pluginJar`, `PluginApi` và imports. Điểm quan trọng:

- Bạn **biết** loader này là `URLClassLoader` vì **chính bạn khởi tạo nó**, không phải do ép kiểu system loader.
- Parent nên chứa đúng host/API classes mà plugin cần cùng identity; không chọn `null` một cách tùy tiện.
- `URLClassLoader` thông thường **parent-first**: class trùng ở parent có thể được parent chọn; namespace/compatibility cần được kiểm tra.
- Đóng loader khi generation được retire và không còn request hoặc resource stream sử dụng. `close()` không buộc JVM unload class/objects ngay.
- Trong production, tránh giữ loader trong một try-with-resources bao quanh riêng bước discovery nếu plugin instance còn chạy sau scope ấy; owner của **plugin generation** phải quyết định thời điểm close.

Nếu cần đổi plugin đang chạy, xây loader **mới** cho generation mới, validate, atomic publish snapshot rồi drain/close generation cũ; đừng sửa loader hiện có một cách tùy ý.

### C. Module path + ModuleLayer

Phù hợp khi muốn named modules, hợp đồng `module-info.java`, `requires`/`exports`/`uses`/`provides` và service discovery theo module layer.

Ở startup, launcher có thể dùng:

```bash
java --module-path mods --module com.example.app/com.example.app.Main
```

Đây là **mẫu minh họa**, không có module `com.example.app` trong demo phần 6. `--module-path` làm các module *observable*, nhưng **không có nghĩa tất cả modules được tự động resolve**. Cần root modules/`--add-modules` hoặc service binding khi phù hợp.

Với plugin động ở runtime, pipeline khái niệm:

```text
Plugin artifact / modules directory
       |
       v
ModuleFinder.of(path)                     (observable modules)
       |
       v
Configuration.resolve(...) / resolveAndBind(...)
       |
       v
ModuleLayer.defineModulesWithOneLoader(...) hoặc WithManyLoaders
       |
       v
ModuleLayer.findLoader(moduleName)
       |
       v
ServiceLoader.load(layer, Service.class)
       |
       v
Registry generation + lifecycle
```

`ModuleLayer` không biến system loader thành `URLClassLoader`; nó cung cấp **module resolution và class loader mapping** phù hợp. Với `ServiceLoader` trong layer, service class phải có identity phù hợp và service-use/provider declarations đúng. `resolveAndBind` có thể thêm providers thông qua `uses`/`provides` mà `resolve` không tự thêm nếu provider không là root/dependency.

**Đừng phối trộn lộn xộn hai mô hình:** tự đưa JAR legacy lên classpath nhưng kỳ vọng `ModuleLayer` động thấy nó, hoặc đặt một module ở module path nhưng gọi `Class.forName` bằng sai class loader và cho rằng lỗi là do thiếu JAR. Phải xác định chính xác plugin thuộc **unnamed/classpath scope** hay **named/module scope** tại từng bước.

## 6. Ví dụ Java 17 hoàn chỉnh: không cast application loader, vẫn tải được plugin

Để tái hiện thực tế, demo tạo **host và plugin ở hai output directories khác nhau**:

- Host `LoaderMigrationDemo` chạy từ `host-out` và **không** để plugin trên `-cp` của host.
- Plugin class `demo.plugin.Greeter` được biên dịch riêng vào `plugins`.
- File resource `META-INF/plugin/version.txt` cũng nằm trong `plugins`.
- Host tạo một **`URLClassLoader` tường minh** trỏ đến `plugins`, với application loader làm parent, rồi tải class/resource qua loader này.

Demo dùng JDK 17 và standard API, không cần Maven, Gradle hoặc thư viện ngoài.

### 6.1. Cấu trúc project

```text
loader-migration-demo/
├── LoaderMigrationDemo.java
├── plugin-src/
│   └── demo/plugin/Greeter.java
├── host-out/                   (javac output cho host)
└── plugins/
    ├── demo/plugin/Greeter.class   (javac output cho plugin)
    └── META-INF/plugin/version.txt (resource)
```

Thư mục `host-out` và `plugins` được tạo ở bước biên dịch; file resource được tạo trong phần lệnh chạy. Bài không dùng `$JAVA_HOME/lib/ext` hay `java.ext.dirs`.

### 6.2. Plugin class

**`plugin-src/demo/plugin/Greeter.java`**

```java
package demo.plugin;

public final class Greeter {
    public static String message() {
        return "from-plugin";
    }
}
```

Code plugin này không phụ thuộc host API, để ví dụ tập trung vào khả năng loader tìm class không có trên host classpath. Trong hệ thống SPI thật, plugin thường triển khai một interface do host sở hữu; lúc đó parent loader phải bảo đảm thấy cùng interface.

### 6.3. Host loader

**`LoaderMigrationDemo.java`**

```java
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

public final class LoaderMigrationDemo {
    public static void main(String[] args) throws Exception {
        ClassLoader app = ClassLoader.getSystemClassLoader();
        System.out.println("appIsURLClassLoader=" + (app instanceof URLClassLoader));
        System.out.println("appParentIsPlatform="
                + (app.getParent() == ClassLoader.getPlatformClassLoader()));

        Path plugins = Path.of(args[0]);
        URL[] urls = {plugins.toUri().toURL()};
        try (URLClassLoader plugin = new URLClassLoader(urls, app)) {
            Class<?> type = Class.forName("demo.plugin.Greeter", true, plugin);
            Object value = type.getMethod("message").invoke(null);

            System.out.println("explicitUrls=" + plugin.getURLs().length);
            System.out.println("pluginDefinedClass=" + (type.getClassLoader() == plugin));
            System.out.println("message=" + value);

            try (InputStream in =
                         plugin.getResourceAsStream("META-INF/plugin/version.txt")) {
                if (in == null) throw new IllegalStateException("missing resource");
                System.out.println("resource=" +
                        new String(in.readAllBytes(), StandardCharsets.UTF_8).trim());
            }
        }
    }
}
```

**Giải thích điểm chính:**

1. `app` là `ClassLoader` chung; dòng `instanceof URLClassLoader` **chỉ quan sát**, không ép kiểu.
2. `ClassLoader.getPlatformClassLoader()` là public API Java 9+, thay vì code truy cập `sun.misc.Launcher$ExtClassLoader` nội bộ.
3. `new URLClassLoader(urls, app)` là loader được **host sở hữu**; `getURLs()` hợp lệ trên **đối tượng này**.
4. `Class.forName("demo.plugin.Greeter", true, plugin)` nạp và initialize class thông qua loader explicit. Plugin không nằm trong `host-out`, vì vậy loader này thực sự chịu trách nhiệm tải class.
5. `type.getClassLoader() == plugin` chứng minh class `Greeter` do plugin loader định nghĩa trong demo, chứ không phải một class trùng tên ở parent.
6. `getResourceAsStream("META-INF/plugin/version.txt")` đọc resource bằng đường dẫn logic từ root plugin; không dùng `File.separator` hoặc dẫn vào thư mục nguồn build.
7. Stream và `URLClassLoader` đều được đóng trong `try-with-resources`. Ở production, khi plugin còn đang phục vụ request, **không đóng loader ở cuối method tải plugin**; giữ nó trong generation owner cho đến lúc retire/drain.

### 6.4. Biên dịch/chạy trên Windows PowerShell

Trong thư mục `loader-migration-demo` đã chứa hai file `.java` ở đúng vị trí phần 6.1:

```powershell
New-Item -ItemType Directory -Force host-out, plugins, plugins/META-INF/plugin | Out-Null
"v2" | Set-Content -Encoding Ascii plugins/META-INF/plugin/version.txt

javac --release 17 -d host-out LoaderMigrationDemo.java
javac --release 17 -d plugins plugin-src/demo/plugin/Greeter.java

java -cp host-out LoaderMigrationDemo plugins
```

**Vì sao dùng `-Encoding Ascii` cho file resource demo?** Nội dung `v2` chỉ chứa ASCII, nên cách ghi này đơn giản, tránh một byte-order mark do phiên bản PowerShell nhất định tự thêm khi dùng tùy chọn UTF-8 cũ. Nếu resource thật có Unicode, dùng UTF-8 không BOM theo contract/file API phù hợp.

### 6.5. Biên dịch/chạy trên macOS/Linux

```bash
mkdir -p host-out plugins/META-INF/plugin
printf 'v2\n' > plugins/META-INF/plugin/version.txt

javac --release 17 -d host-out LoaderMigrationDemo.java
javac --release 17 -d plugins plugin-src/demo/plugin/Greeter.java

java -cp host-out LoaderMigrationDemo plugins
```

### 6.6. Kết quả được kiểm chứng trên JDK 17

```text
appIsURLClassLoader=false
appParentIsPlatform=true
explicitUrls=1
pluginDefinedClass=true
message=from-plugin
resource=v2
```

Đây là stdout **đã biên dịch với `javac --release 17` và chạy trên JDK 17**. Hai dòng đầu mô tả **runtime mặc định đã kiểm thử**, không phải lời hứa cho mọi JVM có `java.system.class.loader` tùy chỉnh. Bốn dòng còn lại xác minh rằng loader mới có đúng một URL gốc, định nghĩa class plugin, gọi được method và đọc được resource trong thư mục plugin.

**Ý nghĩa migration:** không cần và không nên cast application loader thành `URLClassLoader` để đọc/tải plugin. App có thể tiếp tục dùng class loader chuẩn, còn plugin có một loader explicit với ownership và source directory rõ ràng.

### 6.7. Kiểm tra riêng java.ext.dirs

Nếu muốn chứng minh cấu hình cũ không còn hợp lệ, chạy độc lập trên môi trường kiểm thử:

```bash
java -Djava.ext.dirs=legacy -version
```

Trên JDK 17 đã thử, JVM **kết thúc với mã lỗi** thay vì chạy `java -version` bình thường. Không nên đưa lệnh này vào startup script production. Nội dung stderr có thể khác tùy build/JDK version; tài liệu Oracle mô tả lỗi extension mechanism no longer supported.

## 7. Nếu plugin thực sự sử dụng ServiceLoader

Demo phần 6 dùng reflection để tránh phụ thuộc host SPI. Với hệ thống thực có API/plugin provider:

```java
// Snippet; PluginApi là interface do host/shared parent loader định nghĩa.
try (URLClassLoader loader =
         new URLClassLoader(pluginUrls, PluginApi.class.getClassLoader())) {
    ServiceLoader<PluginApi> services =
            ServiceLoader.load(PluginApi.class, loader);

    for (PluginApi plugin : services) {
        plugin.validate();
        // Chưa publish cho traffic cho đến khi đạt readiness.
    }
}
```

Đây là **snippet kiến trúc, không chạy độc lập**; `pluginUrls`, `PluginApi` và imports `URLClassLoader`, `ServiceLoader` phải được cung cấp bởi project. Trong code production, vòng đời loader phải **kéo dài qua thời gian phục vụ của provider** (ví dụ nằm trong một generation), không kết thúc ngay ở scope local của snippet nếu còn gọi provider.

Đối với classpath SPI, file metadata cần đặt đúng:

```text
META-INF/services/com.example.api.PluginApi

Nội dung UTF-8 (mỗi dòng tên implementation):
com.example.plugins.CodecPlugin
```

**Điểm phân biệt:** tên `com.example.api.PluginApi` và `com.example.plugins.CodecPlugin` chỉ là **placeholder minh họa cấu trúc**, phải thay bằng các fully qualified names có thật. Plugin class phải implement service API **cùng class identity** được host sử dụng; một bản `PluginApi.class` trùng tên trong child loader có thể gây `ServiceConfigurationError` hoặc `ClassCastException`.

Khi loader plugin parent-first, nếu parent đã chứa class hoặc resource trùng tên, nó có thể chọn **bản ở parent**. Không khắc phục bằng cast system loader. Phải thiết kế namespace plugin riêng, tránh trùng dependencies, xác định loader hierarchy và kiểm thử đúng version được chọn.

### TCCL và ServiceLoader

`ServiceLoader.load(PluginApi.class)` (overload một tham số) sử dụng **thread context class loader (TCCL)**, có thể không phải loader plugin đang mong muốn. Trong host hoặc plugin registry, nếu đã biết loader thuộc generation, nên dùng overload:

```java
ServiceLoader<PluginApi> providers =
        ServiceLoader.load(PluginApi.class, pluginLoader);
```

Snippet yêu cầu `pluginLoader` tường minh và service type hợp lệ. Không tự ý đổi TCCL ở thread pool chỉ để giải lỗi trong mọi trường hợp. Khi framework bắt buộc dùng TCCL, phải thiết lập, khôi phục trong `finally` và test concurrency.

**Đối với named modules**, dùng cơ chế `provides ... with ...`/`uses` và `ServiceLoader.load(layer, serviceClass)` theo JPMS. Cùng một plugin có thể được phân phối dưới dạng classpath JAR hoặc module JAR; cách khám phá/layer/visibility cần tuân theo mô hình triển khai đã chọn.

## 8. Một kế hoạch migration từ Java 8 sang Java 17 có thể thực hiện

### Bước 1 — Lập inventory ở build và runtime

Tìm **chỉ trong project/deployment configuration mà bạn sở hữu** những dấu hiệu sau:

```text
java.ext.dirs
lib/ext
jre/lib/ext
getSystemClassLoader()
(URLClassLoader)
getURLs()
addURL
sun.misc.Launcher
rt.jar
tools.jar
java.endorsed.dirs
```

Không chỉ xem source code. Cần xem:

- startup scripts, `JAVA_TOOL_OPTIONS`/`_JAVA_OPTIONS`, wrapper/service unit;
- Dockerfile/container image, JDK image customization, system properties của app server;
- Maven/Gradle dependencies, test runtime classpath, shaded/fat JAR config;
- module path arguments, `--add-modules`, `--add-opens` không còn cần thiết;
- plugin catalog/manifest và cách ứng dụng tải JAR theo version.

**Giữ phạm vi đọc và sửa đúng quyền:** đây là checklist cho đội triển khai; không có chỉ dẫn chỉnh toàn bộ máy hoặc xóa bất kỳ file Java nào ngoài deployment đã được quản lý.

### Bước 2 — Phân loại từng JAR từng ở extension directory

Mỗi JAR cần một owner rõ:

| Loại | Hướng chuyển | Kiểm tra |
| --- | --- | --- |
| Library cần ngay khi khởi động | Đưa vào application runtime dependency/classpath | Classpath/JAR tồn tại, version đúng |
| API SPI do host định nghĩa | Host/shared loader sở hữu API | Không nạp bản sao API từ plugin |
| Plugin cài/thay phiên bản động | Plugin registry tạo loader hoặc layer per generation | Isolation, validation, drain, cleanup |
| Named module có `module-info.class` | Module path và resolve roots/service binding | `requires`/`exports`/`uses`/`provides` |
| Automatic module | Module path nếu thực sự cần; xem automatic module name/dependency | Mọi yêu cầu JPMS và conflict thực tế |
| Đoạn code can thiệp JDK internals | Dùng public API hoặc kiến trúc loader mới | Không dựa vào `sun.misc.*`/internal cast |

Không có quy tắc “mọi JAR cũ đều phải thành named module”. **Classpath vẫn là lối migration hợp lệ** cho nhiều ứng dụng. JPMS hữu ích khi cần boundaries/graph rõ, nhưng chuyển JAR lên module path có thêm ràng buộc về packages, reflection, service discovery và tên module.

### Bước 3 — Loại bỏ property/directory cũ khỏi bản triển khai

- Xóa **tham số cấu hình** `-Djava.ext.dirs` ở script/service wrapper, không cần “chuyển giá trị” sang một property bí mật khác.
- Đừng chép lại thư mục `lib/ext` vào Java 17 image. Đóng gói dependencies cạnh ứng dụng hoặc vào plugin directory **do host quản lý**.
- Tránh sửa/JDK install của hệ thống đang phục vụ ứng dụng khác. Tạo image/container build mới có phiên bản cấu hình rõ, verify bằng clean-room run.
- Nếu có `java.endorsed.dirs` hoặc `lib/endorsed`, đó là **cơ chế legacy khác** cũng bị loại bỏ, không phải phương án thay thế `lib/ext`.

### Bước 4 — Sửa code phụ thuộc implementation của loader

**Trước:**

```java
URLClassLoader system =
        (URLClassLoader) ClassLoader.getSystemClassLoader();
URL[] urls = system.getURLs();
```

**Sau, khi chỉ cần load resource/class:**

```java
ClassLoader system = ClassLoader.getSystemClassLoader();
URL config = system.getResource("config/defaults.properties");
Class<?> api = system.loadClass("com.example.api.Service");
```

**Sau, khi thật sự muốn danh sách URL của plugin:**

```java
URLClassLoader plugin =
        new URLClassLoader(pluginUrls, ClassLoader.getSystemClassLoader());
URL[] urls = plugin.getURLs();
```

Các đoạn trên là **snippets**; cần imports và class/resource/`pluginUrls` thật. Không nhất thiết phải “giữ loại `URLClassLoader`” nếu mục tiêu chỉ là quan sát URL của application runtime. Đối với diagnostics classpath, xem launcher arguments và runtime module metadata thay vì tái dựng classpath từ loader internals.

### Bước 5 — Kiểm tra contract khi plugin chạy

Một bộ smoke test cần xác minh:

1. Host khởi động **không có `java.ext.dirs`** và không cần thư mục extension cũ.
2. Provider/library bắt buộc tải được từ **classpath/module path/explicit loader** đúng phạm vi.
3. Application loader không cần cast thành `URLClassLoader`.
4. Plugin class có defining loader và origin đúng version.
5. SPI `ServiceLoader` tìm được số provider mong muốn (0, 1 hoặc nhiều theo policy).
6. Named module có graph hợp lệ; reflective access/exports/opens được kiểm tra nếu có.
7. Resource như `META-INF/services`, JSON/template/config được đóng gói và tìm được bằng loader thích hợp.
8. Chuyển V1→V2 không phá request cũ; loader V1 được cleanup đúng lúc.
9. Test cũng chạy được khi đổi working directory, container base image và startup classpath.
10. Application không phụ thuộc đường dẫn `rt.jar` hoặc assumptions về JDK internal URL.

## 9. Chẩn đoán khi migration vẫn thất bại

### JVM từ chối ngay khi startup

**Triệu chứng:** thông báo “extensions mechanism no longer supported”, hoặc nhắc `java.ext.dirs` / `lib/ext`.

**Nhận định:** lỗi được phát hiện **trước khi application main chạy**, nên sửa code `ClassLoader` bên trong `main` không giải quyết được.

**Hành động:** kiểm tra startup flags/environment, bỏ property/extension directory legacy, đưa dependency lên classpath/module path tường minh, thử lại trong image sạch. Nếu launcher lấy property từ `JAVA_TOOL_OPTIONS` hoặc `_JAVA_OPTIONS`, sửa nơi cấu hình môi trường đó thay vì chỉ sửa script gọi `java`.

### ClassCastException khi khởi tạo plugin manager

**Triệu chứng mẫu:**

```text
java.lang.ClassCastException:
  ...AppClassLoader cannot be cast to java.net.URLClassLoader
```

Đây là **mẫu lỗi minh họa**, class name thực tế phụ thuộc JDK. Tìm đoạn ép kiểu `(URLClassLoader) ClassLoader.getSystemClassLoader()`, sửa thành `ClassLoader` API hoặc tự khởi tạo `URLClassLoader`. Không cần can thiệp reflection/JDK internals.

### ClassNotFoundException hoặc NoClassDefFoundError

**ClassNotFoundException** thường gắn với lookup tường minh theo tên bằng loader không nhìn thấy class. **NoClassDefFoundError** có thể xảy ra khi runtime thiếu dependency mà bytecode cần, hoặc class khởi tạo thất bại trước đó. Đây là lỗi **được phát hiện sau khi ứng dụng chạy**, khác lỗi launcher extension mechanism.

Quy trình:

1. Đọc **tên class cần tìm**, cả root cause và loader identity.
2. Kiểm tra file `.class` nằm trong đúng JAR/directory ở deploy thực tế không.
3. Kiểm tra JAR ấy có thuộc **classpath/module path/custom loader** của đoạn code yêu cầu không.
4. Nếu có nhiều version, xác định class **thực sự được load từ artifact nào**.
5. Nếu error nói `Could not initialize class`, tìm initializer failure đầu tiên, không mặc định thiếu file.

### ServiceLoader không thấy provider

- Với classpath: kiểm tra `META-INF/services/<service-interface>` có tồn tại, nội dung đúng, provider class được load bởi đúng loader và implement đúng shared API.
- Với named modules: kiểm tra `uses`, `provides`, module resolved/defined trong layer, class identity của service và cách gọi `ServiceLoader.load(layer, serviceClass)`.
- Đừng vội gán lỗi cho `URLClassLoader`. Có thể SPI metadata đúng nhưng loader parent-first chọn tài nguyên/class khác version.

### Resource JDK không còn nằm trong rt.jar

`ClassLoader.getSystemResource("java/lang/Class.class")` từ JDK 9 có thể trả URL dạng:

```text
jrt:/java.base/java/lang/Class.class
```

Đây là **ví dụ từ hướng dẫn migration của Oracle**, không phải stdout demo. URL này mô tả resource trong modular runtime image; đừng ép tất cả resource URL thành `jar:file:...` hoặc `Path` của file JAR vật lý. Nếu chỉ cần bytes/resource, dùng `getResourceAsStream` hoặc API module/runtime image phù hợp.

## 10. Bảo mật, isolation và vòng đời plugin loader mới

Một migration thành công về mặt compile/chạy chưa chắc thành công về vận hành. Khi chuyển từ extension directory sang custom loader, cần định nghĩa chính xác owner và policy:

**Không xem class loader là security boundary.** Một plugin Java chạy trong cùng JVM về cơ bản có khả năng gọi các API với quyền của tiến trình, trừ khi có kiến trúc/OS isolation phù hợp. Plugin không tin cậy nên nằm ở process/container riêng với filesystem/network/resource permissions được hạn chế.

**Quản lý JAR và bản phát hành.** Không chấp nhận tùy ý đường dẫn plugin từ input chưa kiểm tra; chỉ load artifact được phê duyệt, kiểm tra hash/chữ ký/version, áp dụng allowlist. Cẩn thận với duplicate classes/resources hoặc dependency bị plugin mang theo nhưng đã tồn tại trong parent.

**Quản lý lifecycle.** `URLClassLoader.close()` đóng các tài nguyên được loader sở hữu như JAR file handles và ngăn việc load mới qua loader theo hợp đồng, nhưng **không thu hồi lập tức những class đã định nghĩa**. Một thread nền, callback, static cache, `ThreadLocal`, TCCL hoặc reference `Class<?>` còn tồn tại có thể giữ loader cũ không được garbage collect.

**Đảm bảo API chung.** Host và plugin cần chia sẻ đúng service interface/class identity; đặt API ở parent/shared layer. Nếu plugin cố tự mang một bản API riêng với cùng fully qualified name, có thể gây `ClassCastException` hoặc `ServiceConfigurationError`.

**Dùng generation snapshot khi thay plugin.** Dựng loader/layer V2, khởi tạo/provider/health check, publish một active reference atomically, giữ V1 đến khi request đã nhận V1 hoàn tất; sau đó retire, close và dọn references V1. Đừng chép đè JAR mà loader hiện tại đang mở và kỳ vọng class definition thay đổi.

**Giới hạn nguồn lực.** Nhiều class loader sống đồng thời có thể giữ JAR handles, threads, heap/metaspace, connection pools. Cần metrics số generation, in-flight requests và cleanup failures; timeout cho drain hoặc process isolation với plugin không hợp tác.

## 11. Test matrix cho CI và deployment

| Trường hợp test | Điều cần chứng minh |
| --- | --- |
| Java 17 clean startup | Không phụ thuộc `lib/ext` hoặc `java.ext.dirs` |
| Startup có `-Djava.ext.dirs` trong môi trường kiểm thử | Nhận diện cấu hình legacy bị runtime từ chối và không deploy |
| Default system loader | Code không cast `URLClassLoader` |
| Explicit plugin loader | Plugin class và resource lấy từ đúng thư mục/JAR |
| Plugin không có trên host classpath | Host vẫn load được bằng loader riêng, không vô tình dùng class ở parent |
| Dùng chung host API | Provider implement đúng class identity, không duplicate API |
| Duplicate class/resource giữa parent và child | Policy parent-first/namespace/version được kiểm thử |
| Sai plugin directory | Báo lỗi dễ hiểu, không âm thầm chạy provider khác |
| Classpath wildcard | JAR được đóng gói đúng; không phụ thuộc thứ tự wildcard để quyết định version |
| Named module | ModuleFinder, roots, requires, uses/provides và layer đúng |
| Plugin update | New generation được validate trước cutover; old generation drain rồi close |
| Missing dependency / incompatible Java version | Fail fast với root cause, không gán nhầm cho extension mechanism |
| TCCL và thread pool | Discovery nhất quán giữa threads, TCCL phục hồi nếu bị thay đổi |
| Resource loading | Không coi `jrt:` URL là `jar:file:` hoặc file hệ điều hành |
| Repeated unload/reload | Không giữ lại listener/thread/context/cache khiến class loader leak |

**Đừng chỉ test trên IDE.** IDE thường tự dựng classpath làm những JAR từng ở extension directory tình cờ xuất hiện. Test bằng **artifact thực tế** với đúng launcher arguments, Java runtime image và cấu trúc thư mục dùng trong production. Tối thiểu nên có một integration test tạo plugin tách khỏi host classpath như demo phần 6.

### Những anti-pattern cần dừng

- **Ghi JAR vào `$JAVA_HOME/lib/ext`** trong Dockerfile hoặc install script.
- **Dùng `java.ext.dirs`** như một knob cấu hình plugin mới.
- **Ép kiểu system loader** rồi dùng `getURLs` để đọc/chỉnh classpath.
- **Reflection vào class nội bộ JDK** để gọi `addURL`.
- **Chuyển `URLClassLoader` mới thành singleton sống mãi** mà không theo dõi plugin generations.
- **Đặt plugin API trùng bản ở parent và child** hoặc giả định `ServiceLoader` tự sửa class identity.
- **Coi module path là classpath có tên mới**, bỏ qua module resolution/encapsulation.
- **Nạp plugin từ thư mục không được tin cậy** và coi loader riêng là sandbox.
- **Đóng loader ngay sau khi scan SPI** nhưng vẫn tiếp tục dùng provider trong những request sau.

## 12. Checklist migration trước khi chốt phát hành

**Build và cấu hình:**

- [ ] Đã liệt kê mọi `lib/ext`, `jre/lib/ext` và `java.ext.dirs` trong build, startup và image.
- [ ] Mọi JAR cũ có dependency owner: classpath, module path hoặc registry plugin explicit.
- [ ] Không thay JDK runtime installation bằng cách chép JAR tùy ý; artifact ứng dụng tự chứa manifest cần thiết.
- [ ] Startup dùng đúng delimiter classpath theo OS và không dựa vào thứ tự wildcard để chọn version.
- [ ] Không còn code cần `rt.jar`/`tools.jar` URL của runtime.

**Source và class loader:**

- [ ] Không cast `ClassLoader.getSystemClassLoader()` sang `URLClassLoader`.
- [ ] Dùng `ClassLoader` public API khi chỉ load class/resource.
- [ ] Chỉ gọi `getURLs()` trên `URLClassLoader` do mình tạo hoặc một đối tượng đã kiểm tra kiểu thực tế theo contract.
- [ ] Parent loader giữ host/service API class identity; không parent-null theo thói quen.
- [ ] Cơ chế `ServiceLoader` đúng loại plugin: classpath SPI hay named modules.
- [ ] Dynamic plugin có loader/layer mới, versioned generation và lifecycle close sau drain.

**Test và vận hành:**

- [ ] Chạy test trên Java 17 runtime thực tế, không chỉ compile bằng JDK 17.
- [ ] Có integration test tách `host-out` và `plugins` như demo phần 6.
- [ ] Kiểm tra không có extension property bị launcher từ chối ở môi trường deploy.
- [ ] Kiểm tra đúng loaded class origin/resource và module/loader identity.
- [ ] Có cảnh báo khi thiếu provider, duplicate classes hoặc version collision.
- [ ] Có canary/rollback plan, artifact hash và metrics về class-loader lifetime.
- [ ] Không sử dụng Java class loader để chạy code untrusted mà thiếu process-level isolation.

### Tài liệu chính thức

- [Oracle JDK 17 Migration Guide: Migrating From JDK 8 to Later JDK Releases](https://docs.oracle.com/en/java/javase/17/migrate/migrating-jdk-8-later-jdk-releases.html)
- [JEP 220 — Modular Run-Time Images](https://openjdk.org/jeps/220)
- [JEP 261 — Module System](https://openjdk.org/jeps/261)
- [Java 17 `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java 17 `URLClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html)
- [Java 17 `ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
- [Java 17 `ModuleLayer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html)

**Kết luận:** chuyển khỏi `lib/ext` và `java.ext.dirs` không chỉ là thay một thư mục. Đó là việc **đưa toàn bộ dependency/plugin discovery vào cấu hình ứng dụng có thể tái hiện và kiểm thử**, ngừng dựa vào implementation của application loader, và chọn classpath, explicit `URLClassLoader` hoặc JPMS `ModuleLayer` theo vòng đời thực của plugin. Có thể vẫn dùng `URLClassLoader` trên Java 17 — **nhưng phải là loader do bạn chủ động tạo và quản lý**, chứ không phải kết quả cast từ system loader mặc định.
# Ghi nhận định danh plugin, phiên bản, CodeSource, loader và module

## 1. Bài toán chẩn đoán trong hệ thống plugin

Một host Java có thể tìm được hai bản `demo.plugin.GreetingPlugin` từ hai JAR khác nhau và nạp chúng vào hai `ClassLoader`. Khi một callback cũ vẫn chạy sau hot reload, chỉ ghi `GreetingPlugin failed` trong log không đủ xác định lỗi đến từ artifact nào.

Một bản ghi đúng phải kết hợp **danh tính nghiệp vụ của plugin** với **danh tính thực tế của class đã được JVM nạp**:

- **Plugin ID**: tên ổn định do host/registry quản lý, ví dụ `demo-greeting`.
- **Plugin version**: phiên bản triển khai, ví dụ `1.0.0` hay `2.0.0`; cần chỉ rõ metadata nào là nguồn sự thật.
- **CodeSource**: thông tin nguồn bytecode được gắn với `ProtectionDomain`, thường có URL JAR hoặc directory khi class được nạp từ file.
- **Defining classloader**: đối tượng loader gắn với class thực sự, bao gồm tên loader và một ID thế hệ do host quản lý.
- **Module**: một class có thể thuộc named module (JPMS) hoặc unnamed module của loader; có thể ghi thêm module layer.

Các giá trị không thay thế nhau. `pluginId` và version mô tả đơn vị triển khai do ứng dụng quản lý. `CodeSource`, `ClassLoader` và `Module` mô tả môi trường JVM của **một class cụ thể**. Một plugin có thể gồm nhiều class ở nhiều JAR; các class ấy không nhất thiết có cùng CodeSource.

### Ví dụ một sự cố thật về mặt kiến trúc

~~~text
Registry: demo-greeting, active=2.0.0, generation=42
JAR v1: plugins/greeting-v1.jar
JAR v2: plugins/greeting-v2.jar

Một request mới đi qua v2.
Một listener cũ chưa hủy đăng ký vẫn gọi instance của v1.
~~~

Nếu log ghi đủ `pluginId`, `pluginVersion`, `generation`, class name, CodeSource và loader identity, ta phân biệt được sự cố xảy ra tại v1 hay v2. Đặc biệt **tên lớp giống nhau không có nghĩa là một class identity duy nhất**.

Mục tiêu bài học là lấy metadata bằng API Java 17, tổ chức log có cấu trúc, xử lý giá trị thiếu/không đáng tin, đối chiếu với metadata phát hành và kiểm thử hai phiên bản plugin trong cùng JVM.

## 2. Nguồn dữ liệu nào dùng cho từng trường?

| Trường chẩn đoán | Nguồn được khuyến nghị | Điều cần ghi nhớ |
| --- | --- | --- |
| `pluginId` | Plugin registry/descriptor đã kiểm tra | Không suy ra từ tên file hoặc tên class |
| `pluginVersion` | Metadata phát hành đã xác minh | Chuỗi do plugin tự trả có thể không khớp registry |
| `deploymentGeneration` | Plugin manager cấp mỗi lần activate | Dùng để phân biệt nhiều lượt nạp cùng một version |
| `implementationClass` | `plugin.getClass().getName()` | Tên nhị phân chưa đủ để định danh class trong JVM |
| `codeSource` | `type.getProtectionDomain().getCodeSource()` | Có thể thiếu; URL không chứng minh chữ ký/tính toàn vẹn |
| `definingLoader` | `type.getClassLoader()` | Có thể là `null` đối với bootstrap classes |
| `loaderName` | `definingLoader.getName()` | Có thể `null` và không được bảo đảm duy nhất |
| `moduleKind` và `moduleName` | `type.getModule()`, `isNamed()`, `getName()` | Unnamed module có `getName() == null` |
| `moduleLayer` | `type.getModule().getLayer()` | Có thể `null`; unnamed module luôn không thuộc layer |
| `artifactSha256` | Bộ xác minh artifact ở pipeline/host | Là digest của bytes đã kiểm tra, không phải từ URL đơn thuần |

Host nên ghi cả **metadata kỳ vọng** từ deployment registry và **metadata quan sát được** trên implementation `Class<?>`. Nếu các giá trị mâu thuẫn, báo mismatch thay vì lặng lẽ tin vào version tự khai báo.

Ví dụ, tên `greeting.jar` không nói chắc đây là version nào; version trong `MANIFEST.MF` có thể không tồn tại, bị nhầm hoặc chưa qua kiểm tra. Nếu registry nói `2.0.0` nhưng `plugin.version()` trả `1.0.0`, cần coi đó là một tình huống bất thường, không âm thầm dùng giá trị thứ hai để ghi log như metadata phát hành đã xác minh.

## 3. Đọc CodeSource từ class thực sự

Thông thường, code lấy CodeSource qua `Class` → `ProtectionDomain` → `CodeSource` → URL:

~~~java
// Mã minh họa: biến implementation đã là Class<?> của plugin.
ProtectionDomain protectionDomain =
        implementation.getProtectionDomain();

CodeSource source = protectionDomain == null
        ? null
        : protectionDomain.getCodeSource();

URL sourceLocation = source == null
        ? null
        : source.getLocation();

String origin = sourceLocation == null
        ? "<unavailable>"
        : sourceLocation.toExternalForm();
~~~

Cần import `java.security.ProtectionDomain`, `java.security.CodeSource` và `java.net.URL`. Đoạn này **không phải file độc lập**, vì `implementation` được cung cấp từ code nạp plugin.

### CodeSource thực sự nói điều gì?

`CodeSource` mô tả thông tin nguồn đã được gắn với protection domain của lớp khi loader định nghĩa nó. Với plugin JAR local nạp qua `URLClassLoader`, `getLocation()` thường là URL của JAR. Trong các trường hợp khác nó có thể là directory, địa chỉ theo scheme khác hoặc `null`.

Không được suy luận:

- “CodeSource null” đồng nghĩa mã đáng ngờ hoặc class không tồn tại. Nó có thể hợp lệ, đặc biệt với class do bootstrap/custom loader định nghĩa.
- “CodeSource là đường dẫn A” đồng nghĩa bytes **hiện tại** trên đĩa A chắc chắn giống bytecode đã nạp. File có thể đã thay đổi sau đó.
- “URL có tên đúng” đồng nghĩa JAR đáng tin. Tên file không kiểm tra chữ ký, checksum hay chính sách publisher.
- “CodeSource là file URL” luôn đúng. Không nên ép mọi URL qua `Path.of(url.toURI())` nếu scheme có thể là `jrt:` hoặc `https:`.

Khi ghi log trong môi trường production, dùng `sourceLocation.toExternalForm()` nếu cần URL; đồng thời cân nhắc làm sạch URL/ẩn những phần nhạy cảm. Đường dẫn tuyệt đối có thể làm lộ tên user, cấu trúc thư mục hay mount nội bộ; URL từ bên ngoài có thể chứa query/token.

### CodeSource và xác minh artifact khác nhau

Một deployment an toàn có thể dùng chuỗi sau:

~~~text
Download / discover artifact
  -> kiểm tra ID và version được khai báo
  -> tính SHA-256 và xác minh expected digest / signature
  -> lưu đường dẫn artifact đã xác minh vào registry
  -> tạo plugin loader
  -> nạp implementation
  -> quan sát CodeSource/loader/module
  -> đối chiếu identity thực tế với entry đã xác minh
~~~

`CodeSource` là **thông tin để chẩn đoán**, không tự là bước kiểm chứng tính toàn vẹn. Nếu chính sách bảo mật cần nhận biết nhà phát hành, phải thực hiện cơ chế kiểm chứng thích hợp trước khi kích hoạt mã plugin. Ghi hash từ kết quả xác minh thật; nếu hệ thống chưa xác minh, bỏ trường hash hoặc ghi `null`, không phát sinh một chuỗi “hash” tưởng tượng.

Đối với lỗi `ClassNotFoundException`, có thể chưa có đối tượng `Class<?>` của lớp thất bại để lấy CodeSource. Khi đó log class name, loader định sử dụng, URL/JAR dự kiến và exception; không tạo CodeSource giả.

## 4. ClassLoader: tên loader khác danh tính loader

### 4.1. Defining loader là gì?

`Class.getClassLoader()` trả loader của lớp hoặc `null` cho bootstrap loader. Với phần lớn plugin trong JAR riêng:

~~~java
Class<?> type = plugin.getClass();
ClassLoader definingLoader = type.getClassLoader();
~~~

**Đây là loader của class thực sự**, không nhất thiết là loader object mà một phương thức gọi `loadClass` đã được truyền vào. Theo parent delegation, một loader con có thể trả class do loader cha đã định nghĩa.

Hai class cùng tên nhưng do hai defining loaders khác nhau định nghĩa là hai kiểu khác nhau:

~~~java
// Mã minh họa: hai Class<?> đã được nạp từ hai generation.
boolean sameBinaryName =
        typeV1.getName().equals(typeV2.getName());
boolean sameIdentity = (typeV1 == typeV2);
boolean sameDefiningLoader =
        (typeV1.getClassLoader() == typeV2.getClassLoader());
~~~

Không tự kết luận `sameIdentity == false` chỉ vì hai biến loader ban đầu khác nhau. Nếu cả hai delegate về cùng parent đã chứa implementation, chúng có thể trả cùng class.

### 4.2. Loader name có thể không duy nhất

Từ Java 9, `ClassLoader.getName()` trả tên nếu loader được đặt tên, nếu không trả `null`. Có thể tạo một named URLClassLoader trên Java 17:

~~~java
// Mã minh họa: urls và parentLoader đã được khởi tạo.
URLClassLoader loader = new URLClassLoader(
        "demo-greeting-generation-42",
        urls,
        parentLoader
);
~~~

Hai classloader có thể **trùng tên**; việc đặt tên là hỗ trợ vận hành, không tự tạo khóa duy nhất. Host nên cấp thêm `loaderGeneration` hoặc `pluginInstanceId` khi tạo loader.

Có thể dùng một ID tạm trong phạm vi một JVM:

~~~java
String identityTag = definingLoader == null
        ? "<bootstrap>"
        : definingLoader.getClass().getName() + "@"
                + Integer.toHexString(
                        System.identityHashCode(definingLoader));
~~~

Đây là mã minh họa và giá trị `identityHashCode` **không bảo đảm không trùng**, không bền qua JVM restart, không thích hợp làm khóa lưu trữ/audit. Để theo dấu lâu dài, dùng ID do host sinh với quan hệ rõ đến deployment generation.

### 4.3. Đừng nhầm defining loader với TCCL

~~~java
ClassLoader defining = type.getClassLoader();
ClassLoader tccl =
        Thread.currentThread().getContextClassLoader();
~~~

`tccl` là **thread context classloader** của thread đang chạy, có thể được framework/plugin manager thay tạm để tìm service/resource. Nó không nhất thiết đã định nghĩa `type`. Nếu một callback cũ vẫn giữ TCCL của loader v1, hãy ghi cả `definingLoader` và `tccl` trong log điều tra; đừng dùng TCCL thay cho định danh class.

Trong hệ thống nhiều thread, TCCL còn là nguồn có thể giữ loader cũ sống qua lần reload. Khi đặt TCCL tạm, phải khôi phục trong `finally` trên **chính thread** được thay đổi, và hủy các task cũ khi dừng plugin.

## 5. Module: named, unnamed và layer

Java 9+ có JPMS. `Class.getModule()` trả một đối tượng `Module`; class trên classpath/qua `URLClassLoader` thông thường thuộc **unnamed module** của defining loader.

~~~java
// Mã minh họa: type là Class<?>.
Module module = type.getModule();
boolean named = module.isNamed();
String moduleName =
        named ? module.getName() : "<unnamed>";
ModuleLayer layer = module.getLayer();
~~~

Điểm cần nhớ:

- `Module.getName()` là `null` cho unnamed module; **null không có nghĩa class không thuộc module nào**.
- `Module.getDescriptor()` cũng là `null` với unnamed module; đối với named module, descriptor có thể chứa metadata version nhưng không bắt buộc.
- `Module.getLayer()` có thể `null` nếu module không thuộc layer; unnamed module luôn có layer là `null`.
- Tên named module không nhất thiết là plugin ID. Một plugin có thể gồm nhiều module; nhiều module có thể liên quan cùng một plugin deployment.
- Với custom module layers, nên ghi **layer identity/generation do host quản lý** để phân biệt các thế hệ nạp. Chỉ ghi module name có thể không đủ.
- Khi chẩn đoán `IllegalAccessError` hoặc `InaccessibleObjectException`, `requires/reads`, `exports` và `opens` trong module graph quan trọng hơn việc chỉ nhìn thấy class name.

### Module descriptor version có phải plugin version?

Không mặc định. Ví dụ:

~~~java
// Mã minh họa: class implementation đã tồn tại.
Module m = implementation.getModule();
String descriptorVersion = m.getDescriptor() == null
        ? "<not-applicable>"
        : m.getDescriptor().version()
                .map(Object::toString)
                .orElse("<unspecified>");
~~~

`ModuleDescriptor.version()` là optional. Tương tự, `Package.getImplementationVersion()` có thể trả `null` nếu manifest không có `Implementation-Version` hoặc package chưa được cung cấp metadata ấy. Hệ thống phải chỉ rõ **version triển khai từ registry** là nguồn sự thật hay không và đối chiếu với các version tự khai báo.

## 6. Ví dụ Java 17 hoàn chỉnh: cùng plugin ID, hai JAR và hai loader

Ta tạo một API chung do host sở hữu và hai implementation cùng tên `demo.plugin.GreetingPlugin` ở các JAR v1/v2. Host nạp cả hai bằng named `URLClassLoader`, trích metadata từ class thực sự và so sánh class identity.

### 6.1. Cấu trúc file

~~~text
plugin-metadata-demo/
  src/
    api/demo/api/Plugin.java
    v1/demo/plugin/GreetingPlugin.java
    v2/demo/plugin/GreetingPlugin.java
    host/demo/host/PluginMetadataDemo.java
  build/                     (được tạo bởi lệnh biên dịch)
~~~

JAR của plugin **không được đưa lên application classpath**, nếu không parent loader có thể nạp implementation trước, khiến demo mất ý nghĩa phân biệt hai loader.

### 6.2. File API: src/api/demo/api/Plugin.java

~~~java
package demo.api;

public interface Plugin {
    String id();
    String version();
    String message();
}
~~~

### 6.3. Plugin v1: src/v1/demo/plugin/GreetingPlugin.java

~~~java
package demo.plugin;

import demo.api.Plugin;

public final class GreetingPlugin implements Plugin {
    public GreetingPlugin() {
    }

    @Override
    public String id() {
        return "demo-greeting";
    }

    @Override
    public String version() {
        return "1.0.0";
    }

    @Override
    public String message() {
        return "hello-v1";
    }
}
~~~

### 6.4. Plugin v2: src/v2/demo/plugin/GreetingPlugin.java

~~~java
package demo.plugin;

import demo.api.Plugin;

public final class GreetingPlugin implements Plugin {
    public GreetingPlugin() {
    }

    @Override
    public String id() {
        return "demo-greeting";
    }

    @Override
    public String version() {
        return "2.0.0";
    }

    @Override
    public String message() {
        return "hello-v2";
    }
}
~~~

Cả hai implementation cùng tên nhị phân nhưng khác bytes và nằm trong hai JAR khác nhau. Phần `version()` là một contract minh họa, chưa phải metadata đã được registry xác minh độc lập.

### 6.5. Host: src/host/demo/host/PluginMetadataDemo.java

~~~java
package demo.host;

import demo.api.Plugin;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.CodeSource;
import java.security.ProtectionDomain;

public final class PluginMetadataDemo {
    private PluginMetadataDemo() {
    }

    public static void main(String[] args) throws Exception {
        Path v1 = Path.of("build/jars/plugin-v1.jar");
        Path v2 = Path.of("build/jars/plugin-v2.jar");

        if (!Files.isRegularFile(v1) || !Files.isRegularFile(v2)) {
            throw new IllegalStateException("Plugin JAR missing");
        }

        ClassLoader parent =
                PluginMetadataDemo.class.getClassLoader();

        try (URLClassLoader loader1 = new URLClassLoader(
                    "plugin-v1",
                    new URL[]{v1.toUri().toURL()}, parent);
             URLClassLoader loader2 = new URLClassLoader(
                    "plugin-v2",
                    new URL[]{v2.toUri().toURL()}, parent)) {

            Class<?> c1 = Class.forName(
                    "demo.plugin.GreetingPlugin", true, loader1);
            Class<?> c2 = Class.forName(
                    "demo.plugin.GreetingPlugin", true, loader2);

            Plugin p1 = (Plugin) c1
                    .getDeclaredConstructor().newInstance();
            Plugin p2 = (Plugin) c2
                    .getDeclaredConstructor().newInstance();

            show(p1, c1);
            show(p2, c2);

            System.out.println("sameBinaryName="
                    + c1.getName().equals(c2.getName()));
            System.out.println("sameClass=" + (c1 == c2));
            System.out.println("sameDefiningLoader="
                    + (c1.getClassLoader() == c2.getClassLoader()));
            System.out.println("bothImplementHostApi="
                    + (Plugin.class.isAssignableFrom(c1)
                            && Plugin.class.isAssignableFrom(c2)));
        }
    }

    private static void show(Plugin plugin, Class<?> type)
            throws Exception {
        ClassLoader defining = type.getClassLoader();
        Module module = type.getModule();

        ProtectionDomain pd = type.getProtectionDomain();
        CodeSource cs = pd == null ? null : pd.getCodeSource();
        URL url = cs == null ? null : cs.getLocation();

        // Trong demo, CodeSource có file: URL đến JAR.
        String file = url == null ? "<unavailable>"
                : Path.of(url.toURI()).getFileName().toString();

        String loaderName = defining == null
                ? "<bootstrap>"
                : (defining.getName() == null
                        ? "<unnamed-loader>" : defining.getName());

        String moduleName = module.isNamed()
                ? module.getName() : "<unnamed>";

        System.out.println(
                "plugin=" + plugin.id() + "@" + plugin.version());
        System.out.println("codeSourceFile=" + file);
        System.out.println("loaderName=" + loaderName);
        System.out.println("module=" + moduleName);
        System.out.println("message=" + plugin.message());
    }
}
~~~

Vì các loader được tạo từ hai đường dẫn `file:` URL tới JAR local, lệnh `Path.of(url.toURI())` ở ví dụ này hợp lệ. Trong logger tổng quát cần dùng `url.toExternalForm()` hoặc xử lý theo scheme và `null` thay vì luôn giả định URL là đường dẫn ổ đĩa.

### 6.6. Lệnh compile và chạy

Tại thư mục `plugin-metadata-demo` với JDK 17+, dùng Bash:

~~~bash
mkdir -p build/api build/v1 build/v2 build/host build/jars

javac --release 17 -encoding UTF-8 \
  -d build/api src/api/demo/api/Plugin.java
jar --create --file build/plugin-api.jar -C build/api .

javac --release 17 -encoding UTF-8 \
  -cp build/plugin-api.jar -d build/v1 \
  src/v1/demo/plugin/GreetingPlugin.java
jar --create --file build/jars/plugin-v1.jar -C build/v1 .

javac --release 17 -encoding UTF-8 \
  -cp build/plugin-api.jar -d build/v2 \
  src/v2/demo/plugin/GreetingPlugin.java
jar --create --file build/jars/plugin-v2.jar -C build/v2 .

javac --release 17 -encoding UTF-8 \
  -cp build/plugin-api.jar -d build/host \
  src/host/demo/host/PluginMetadataDemo.java

java -cp "build/host:build/plugin-api.jar" \
  demo.host.PluginMetadataDemo
~~~

**Stdout chính xác của ví dụ trong cấu hình trên:**

~~~text
plugin=demo-greeting@1.0.0
codeSourceFile=plugin-v1.jar
loaderName=plugin-v1
module=<unnamed>
message=hello-v1
plugin=demo-greeting@2.0.0
codeSourceFile=plugin-v2.jar
loaderName=plugin-v2
module=<unnamed>
message=hello-v2
sameBinaryName=true
sameClass=false
sameDefiningLoader=false
bothImplementHostApi=true
~~~

Khi chạy trên Windows PowerShell, dùng dấu chấm phẩy trong classpath:

~~~powershell
java -cp "build/host;build/plugin-api.jar" demo.host.PluginMetadataDemo
~~~

Các lệnh `javac`/`jar` nhiều dòng phía trên dùng dấu backslash theo cú pháp Bash. Trong PowerShell có thể viết các lệnh ấy trên một dòng. Để kiểm tra file JAR đầu ra:

~~~bash
jar --list --file build/jars/plugin-v1.jar
jar --list --file build/jars/plugin-v2.jar
~~~

Mỗi JAR phải chứa `demo/plugin/GreetingPlugin.class`. Host chỉ biên dịch với `plugin-api.jar`, không chứa implementation trong application classpath. Nhờ vậy, loader1 và loader2 thực sự định nghĩa hai bản class khác nhau trong ví dụ.

**Diễn giải:**

- Plugin ID giống nhau: cả hai thuộc cùng đơn vị nghiệp vụ `demo-greeting`.
- Version khác nhau: mã v1 trả `1.0.0`, mã v2 trả `2.0.0`.
- CodeSource khác nhau: class v1 từ `plugin-v1.jar`, class v2 từ `plugin-v2.jar`.
- Defining loader khác nhau: `plugin-v1` và `plugin-v2`, nên `c1 != c2` dù tên class bằng nhau.
- Module đều `<unnamed>` vì các class được nạp theo classpath trong `URLClassLoader`, không phải named module của JPMS.
- Hai class đều implement chung `demo.api.Plugin` mà host đã định nghĩa, nên phép cast hoạt động.

Chương trình cố ý giữ cả hai loader sống cùng lúc để so sánh. Nó **không thực hiện hot reload sản phẩm**; trong host thật, sau khi chuyển routing phải stop instance cũ, hủy callback/task, đóng loader và xóa registry reference theo lifecycle.

## 7. Ví dụ named module: trường module thực sự thay đổi

Một JAR/classpath plugin trong `URLClassLoader` thường thuộc unnamed module, nhưng JPMS có named module với `module-info.java`. Tạo một ví dụ thứ hai (độc lập với các file mục 6):

~~~text
modsrc/
  demo.namedplugin/
    module-info.java
    demo/namedplugin/ModuleProbe.java
~~~

**File `modsrc/demo.namedplugin/module-info.java`:**

~~~java
module demo.namedplugin {
}
~~~

**File `modsrc/demo.namedplugin/demo/namedplugin/ModuleProbe.java`:**

~~~java
package demo.namedplugin;

public final class ModuleProbe {
    private ModuleProbe() {
    }

    public static void main(String[] args) {
        Module module = ModuleProbe.class.getModule();
        System.out.println("named=" + module.isNamed());
        System.out.println("module=" + module.getName());
        System.out.println(
                "bootLayer=" + (module.getLayer() == ModuleLayer.boot()));
    }
}
~~~

Biên dịch/chạy JDK 17 bằng Bash:

~~~bash
mkdir -p build/mods
javac --release 17 -encoding UTF-8 \
  --module-source-path modsrc \
  -d build/mods --module demo.namedplugin

java --module-path build/mods \
  --module demo.namedplugin/demo.namedplugin.ModuleProbe
~~~

Stdout:

~~~text
named=true
module=demo.namedplugin
bootLayer=true
~~~

Vì ứng dụng được khởi chạy qua module launcher với module này là root, module nằm trong boot layer ở ví dụ trên. Trong ứng dụng tạo custom `ModuleLayer`, trường layer có thể là layer khác. Với unnamed module, `getLayer()` trả `null`. Tên module còn có thể trùng giữa hai layer khác nhau; muốn chẩn đoán thay thế named-module plugin, nên ghi module name cùng layer/generation và classloader.

Nếu một named module có descriptor version, `module.getDescriptor().version()` trả `Optional`; nếu không gán version thì không có. Đừng coi module descriptor version luôn là version triển khai của plugin.

## 8. Thiết kế log có cấu trúc và ID ổn định

Một entry JSON gợi ý:

~~~json
{
  "event": "plugin.activated",
  "pluginId": "demo-greeting",
  "pluginVersion": "2.0.0",
  "deploymentGeneration": 42,
  "implementationClass": "demo.plugin.GreetingPlugin",
  "codeSource": "file:/app/plugins/plugin-v2.jar",
  "loaderName": "plugin-v2",
  "loaderGeneration": 42,
  "moduleKind": "unnamed",
  "moduleName": null,
  "moduleLayer": null,
  "artifactSha256": null,
  "result": "activated"
}
~~~

Đây là **JSON minh họa**, không phải log được sinh ra từ demo Java. `artifactSha256: null` có nghĩa chưa cung cấp digest trong bản ghi ví dụ; hệ thống production phải lấy giá trị thực từ bước xác minh artifact, không bịa hash. Nếu version đã được registry xác minh, có thể thêm `verifiedPluginVersion` bên cạnh giá trị `Plugin.version()` do code tự trả để phân biệt.

Các sự kiện nên ghi:

| Event | Thời điểm | Trường hữu ích |
| --- | --- | --- |
| `plugin.discovered` | Khi tìm artifact | ID/version khai báo, nguồn scan, artifact path |
| `plugin.verified` | Sau kiểm tra digest, chữ ký, policy | ID/version đã xác minh, hash thực, kết quả |
| `plugin.loaded` | Khi lớp implementation đã được JVM nạp | Class, defining loader, CodeSource, module |
| `plugin.activated` | Khi start thành công và chuyển routing | ID, version, generation, loader/module |
| `plugin.invocation.failed` | Một lần gọi lỗi | Correlation ID, generation, class, exception |
| `plugin.deactivated` | Khi ngừng nhận request và stop | Old/new generation, lý do, in-flight count |
| `plugin.released` | Sau cleanup/đóng loader và bỏ registry refs | Cleanup result, close errors, remaining tasks |

`plugin.released` không có nghĩa JVM đã garbage collect hay unload mọi class. Nếu muốn theo dõi class unloading, cần số liệu JVM và heap/thread diagnostics, không suy diễn chỉ từ kết quả lifecycle hook.

### Correlation ID và thế hệ triển khai

Khi hot reload giữa request, log nên gắn request ID / trace ID với `deploymentGeneration`. Một record hoàn chỉnh có thể được truy ngược qua service instance, plugin ID, version và loader generation mà không dựa vào loader name/identity hash có khả năng trùng.

Không dùng `System.identityHashCode(loader)` làm khóa DB xuyên JVM restart. Một cách là host sinh `serviceInstanceId` ở lúc khởi động và `pluginGeneration` mới mỗi khi activate. Khi dùng nhiều instance hoặc replica, ghi rõ instance/region theo chính sách quan sát và bảo vệ dữ liệu.

### Hiệu năng của logging

Lấy metadata từ reflection và định dạng URL lặp lại ở **mọi** request có thể làm tăng CPU/log volume. Nên thu một snapshot dạng chuỗi khi load/activate, dùng trường ngắn `pluginId`/`version`/`generation` ở đường nóng và bổ sung CodeSource/module/loader details khi có lỗi.

Không giữ một `Map<Class<?>, ...>` hoặc `ClassLoader` trong cache toàn cục chỉ để log, vì nó có thể giữ loader plugin cũ sau khi stop. Snapshot chỉ nên chứa dữ liệu thuần (`String`, number, enum) và được bỏ theo lifecycle của generation.

## 9. Các lỗi chẩn đoán thường gặp

### 9.1. Loader bị chọn nhầm do parent delegation

Host có thể báo đã tải JAR v2, nhưng `implementation.getClassLoader()` trả loader của parent chứa v1. Nếu implementation tồn tại trên parent classpath, loader con có thể nhận class cũ. Kiểm tra defining loader và CodeSource của **lớp thực sự được dùng**; đừng chỉ in URL list mà plugin manager định truyền khi tạo loader.

### 9.2. Có class name nhưng chưa có CodeSource

Một `ClassNotFoundException` thường xảy ra trước khi có class object. Khi đó log tên class, expected JAR/module path, loader cố gắng load và stack trace. Nếu đã có class nhưng CodeSource null, hiển thị một giá trị thiếu rõ ràng; không coi null tự động là lỗi bảo mật.

### 9.3. Module name null không phải class không có module

Class ở unnamed module vẫn thuộc một `Module`. Nếu logger gọi `module.getName().toString()` có thể gặp `NullPointerException`. Dùng `module.isNamed()` và chuẩn hóa thành một nhãn đọc được.

### 9.4. Plugin nói version A nhưng registry nói B

Vì plugin ID/version là dữ liệu có thể do plugin tự trả, phải đối chiếu với deployment registry và hash. Ghi mismatch, xem class có được nạp nhầm từ artifact cũ hay không. Không chọn đại một version làm chuẩn khi tình huống đang cần điều tra.

### 9.5. ClassCastException hoặc NoSuchMethodError sau upgrade

Hai class có cùng tên `demo.api.Plugin` do hai loaders riêng định nghĩa có thể không ép kiểu qua nhau; một method được biên dịch theo API mới có thể không tồn tại trong version runtime cũ. Ghi defining loader/CodeSource của API class và implementation; kiểm tra dependency contract, version/ABI.

### 9.6. Lớp cũ chưa unload sau close

`URLClassLoader.close()` đóng tài nguyên loader quản lý nhưng không ép các lớp đã nạp biến mất. Listener, static cache của host, `ServiceLoader`, `Class<?>`, `Method`, TCCL, `ThreadLocal` và executor còn chạy đều có thể giữ loader cũ. Dùng thread dump, heap dominator và JFR/JVM class unloading events để kiểm tra **GC roots** và số vòng reload thực tế.

### 9.7. Logging chính nó gây rò rỉ hoặc lộ dữ liệu

Không giữ plugin instance trong MDC hoặc singleton logger context quá vòng đời request. Context được đưa vào MDC phải được xóa trong `finally`. Tránh log raw URL có credentials, query token, đường dẫn riêng tư; validate/escape plugin ID/version do bên ngoài nhập để tránh log injection. Đặt sampling/retention và quyền xem log thích hợp.

## 10. Quy trình ghi metadata theo vòng đời

Một plugin manager có thể quản lý theo các bước:

1. **DISCOVER:** nhận artifact, đọc metadata khai báo; gán `pluginId` và version dự kiến theo registry.
2. **VERIFY:** xác minh hash/chữ ký và compatibility; gán artifact ID/digest. Nếu không đạt, không load plugin.
3. **LOAD:** tạo loader hoặc module layer; gán generation; nạp implementation. Lấy `Class` thật và thu CodeSource, defining loader, module/layer.
4. **VALIDATE:** kiểm tra contract API và version đã kỳ vọng; ghi mismatch nếu có; không coi CodeSource là bảo đảm tin cậy.
5. **ACTIVATE:** publish routing, ghi sự kiện activation và giữ snapshot theo lifecycle.
6. **INVOKE:** dùng correlation ID và metadata generation đã ghép; log details khi lỗi, không serialize mọi reflection object cho từng request.
7. **STOP:** chặn request mới, chờ in-flight calls, hủy listener/timer/executor, dọn ThreadLocal/TCCL.
8. **RELEASE:** đóng plugin-owned resources, đóng URLClassLoader nếu host sở hữu, gỡ registry/cache và snapshot. Không gắn nhãn “unloaded” cho đến khi có bằng chứng JVM thực tế.

Thứ tự này là mô hình tổ chức, không phải một API chuẩn của Java. Nếu hệ thống có state migration hoặc tài nguyên độc quyền, thứ tự cutover cần điều chỉnh; điều bất biến là không dùng metadata của loader cũ để xác nhận plugin mới.

## 11. Checklist kiểm tra

- [ ] Có ID và version triển khai được quản lý, không lấy nhầm từ tên class hoặc JAR path.
- [ ] Mỗi generation được gắn với artifact đã xác minh và một loader/module layer cụ thể.
- [ ] Lấy CodeSource từ `Class.getProtectionDomain()` với null handling.
- [ ] Ghi `clazz.getClassLoader()` và phân biệt defining loader với TCCL.
- [ ] Ghi `loader.getName()` an toàn khi null và không coi tên là khóa duy nhất.
- [ ] Ghi `Module.isNamed()`, `getName()`, layer/descriptor version khi cần, với null handling.
- [ ] Có trường class name để phân biệt các implementation cùng plugin ID.
- [ ] Log thời điểm discovered, verified, loaded, activated, failed, deactivated, released.
- [ ] Correlation ID nối một request với version/generation đang thực thi.
- [ ] CodeSource path/URL được sanitize, không lộ thông tin nhạy cảm.
- [ ] Không log hash giả hoặc nhầm URL thành chữ ký tin cậy.
- [ ] Cache metadata không giữ `Class<?>`/`ClassLoader` của plugin vô thời hạn.
- [ ] Kiểm thử nhiều lượt hot reload, hai loader cùng binary name, parent delegation, JPMS named và unnamed modules.

## 12. Câu hỏi tự kiểm tra

1. Nếu hai loader định nghĩa class cùng binary name, có phải cùng kiểu không? **Không.** Kiểm tra defining loader và `Class<?>` identity.
2. `Class.getClassLoader() == null` nghĩa gì? Thông thường là class được bootstrap loader nạp, không phải loader mất dữ liệu.
3. `ClassLoader.getName() == null` nghĩa gì? Có thể loader không được đặt tên, khác với loader object null.
4. CodeSource trỏ đến JAR v2 có chứng minh bytes an toàn không? **Không.** Cần chính sách xác minh hash/chữ ký.
5. Vì sao CodeSource có thể thiếu? ProtectionDomain hoặc CodeSource/location không được cung cấp tùy loader/runtime.
6. `Module.getName() == null` có nghĩa không có module? **Không**, đây có thể là unnamed module.
7. Version trong `Package.getImplementationVersion()` hoặc `ModuleDescriptor.version()` có luôn là version plugin không? **Không**, cần hợp đồng rõ ràng.
8. Vì sao dùng loader identity hash làm khóa audit chưa đủ? Có thể trùng và không bền qua restart.
9. Khi thấy v1 vẫn chạy sau reload, log gì trước tiên? Plugin ID/version/generation, request ID, implementation class, CodeSource, defining loader, module.
10. Gọi `URLClassLoader.close()` có đảm bảo JVM unload lớp cũ không? **Không**, phải dọn tham chiếu và phụ thuộc JVM GC.

## 13. Tài liệu API Java 17

- [Class.getClassLoader, getModule, getProtectionDomain](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [ClassLoader.getName](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [ProtectionDomain.getCodeSource](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/ProtectionDomain.html)
- [CodeSource.getLocation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/CodeSource.html)
- [Module.getName, isNamed và getLayer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html)
- [URLClassLoader constructors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html)

**Kết luận:** Một bản ghi chẩn đoán plugin chỉ có ý nghĩa khi kết nối **ID và version do host quản lý** với **CodeSource, defining classloader và module của class thực sự đã được nạp**. Ghi log theo generation, có null handling, nguồn phiên bản được kiểm chứng và correlation ID, ta có thể tìm plugin cũ còn chạy, class bị nạp nhầm từ parent, lỗi module hoặc tham chiếu giữ loader. Metadata quan sát được giúp giải thích sự cố; nó không thay thế xác minh artifact, quản lý lifecycle hay bảo mật thực thi.

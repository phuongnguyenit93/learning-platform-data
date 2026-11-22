# Bảng thay đổi class loading giữa Java 8 và Java hiện đại

Từ **Java 8** đến **Java 9+** rồi **Java 17, 21, 25 và các JDK mới hơn**, JVM vẫn giữ các khái niệm quan trọng: **binary name**, **defining loader**, **parent delegation**, **loading → linking → initialization**, `ClassLoader.loadClass` và định danh kiểu runtime. Thay đổi lớn nhất không phải Java “bỏ ClassLoader”, mà là **JDK 9 đưa hệ thống module JPMS vào runtime**, thay layout `rt.jar`/`tools.jar` bằng modular runtime image, thay **extension loader** bằng **platform loader**, và thay implementation của **application loader**. Các JDK sau siết thêm một số **ranh giới reflection / JDK internals**, bổ sung công cụ và API cho module/code generation.

Bài Knowledge này là **bảng tra cứu thay đổi class loading giữa Java 8 và Java hiện đại** thuộc **Java core – classloader / Tra cứu**. Nội dung phân biệt **quy tắc API** với **chi tiết implementation HotSpot/OpenJDK**, so sánh theo mốc phiên bản, đưa mã Java 8 và Java 17+ kiểm chứng thực tế, và cung cấp checklist di chuyển code cũ.

> **Phạm vi phiên bản:** “Java hiện đại” ở đây chủ yếu là **JDK 9+**, với ví dụ thực hành trên **JDK 17+**. Mốc JDK 21/25 được ghi khi có thay đổi hay API liên quan; không nên suy một hành vi của riêng HotSpot là cam kết chung cho mọi JVM hoặc tất cả JDK về sau.

## 1. Bảng tóm tắt nhanh: điều gì đổi, điều gì không?

| Chủ đề | Java 8 | Java 9+ / Java hiện đại | Hệ quả thực tế |
| --- | --- | --- | --- |
| Mô hình class loader built-in | Bootstrap → extension → application/system, trong các runtime thông dụng | Bootstrap → **platform** → application/system | Không tìm `ExtClassLoader` hay `lib/ext` như cơ chế nạp extension |
| Application loader implementation | Trên Oracle/OpenJDK 8 thường là subclass `URLClassLoader` | Built-in **không còn là `URLClassLoader`** | Không cast `ClassLoader.getSystemClassLoader()` sang `URLClassLoader` |
| Platform/extension loader | Extension loader được dùng với extension mechanism | Platform loader được truy cập qua `ClassLoader.getPlatformClassLoader()` (từ JDK 9) | Parent của custom loader có thể chọn platform loader |
| Classpath | Chủ yếu classpath + extension mechanism | Classpath **vẫn tồn tại**, cùng module path | App classpath thuộc unnamed module; module path cho named modules |
| Đóng gói JDK classes | `jre/lib/rt.jar`, `lib/tools.jar` và các JAR nội bộ | **Modular runtime image**, không còn `rt.jar`/`tools.jar` | Dùng `jrt:/`, `jmod`, `jlink` hoặc API module thay hardcode path |
| Runtime type identity | Binary name + defining loader | **Không đổi** | Hai loaders khác nhau vẫn có thể tạo hai `Class<?>` cùng tên |
| Parent delegation | Có | Vẫn có, nhưng module loading có cơ chế tìm theo module và loader graph | Không giản lược mọi module resolution thành một classpath tuyến tính |
| Module metadata | Không có `Class.getModule()`/`ModuleLayer` | `Class.getModule()`, `Module`, `ModuleLayer` | Log class loader **và** module, đặc biệt với lỗi access |
| Class visibility | Java access + class loader + một số package/security rules | Thêm **module readability / exports / opens** | `public` không đủ nếu module không export đúng package |
| JDK internal APIs | Nhiều thư viện dùng `sun.*`/reflective internals | JDK 9 đặt module boundaries; JDK 17 **strong encapsulation** mặc định | Phải bỏ phụ thuộc internal APIs hoặc dùng mở package có kiểm soát |
| Service discovery | `ServiceLoader` + `META-INF/services` | Thêm `uses`/`provides` và `ServiceLoader.stream()` | SPI có thể hoạt động qua module layer, không chỉ classpath resource |
| Resource lookup | `getResource(s)` theo loader/classpath/JAR | Thêm module encapsulation; resource URL JDK thường `jrt:` | `getResource` có thể không thấy resource trong named module bị đóng |
| Code generation | `ClassLoader.defineClass`, Java 8 `MethodHandles` có các API khác | `Lookup.defineClass` từ JDK 9, hidden classes từ JDK 15 | Framework nên dùng API hiện đại đúng package/module privileges |
| Bytecode version | Java 8 class file major **52** | Java 9=53, 11=55, 17=61, 21=65, 25=69 | `UnsupportedClassVersionError` nếu bytecode mới hơn JVM |
| Security Manager | Có cơ chế cũ và policies, dù không tự biến loader thành sandbox | Deprecated-for-removal JDK 17; **vô hiệu vĩnh viễn từ JDK 24** | Không thiết kế sandbox plugin mới chỉ bằng ClassLoader/Security Manager |
| Diagnostics | `-verbose:class`, `javap`, runtime class loader inspection | Unified Logging như `-Xlog:class+load`, `Class.getModule`, `jrt:` | Điều tra thêm module graph, declaring class và CodeSource |

**Đọc bảng theo đúng ba nhóm:** (1) thay đổi **thực sự trong Java/JDK API**, (2) thay đổi **implementation/layout mặc định**, và (3) thay đổi **mô hình quyền truy cập**. Không phải mọi dòng là một “breaking change” cho source Java thông thường.

## 2. Sơ đồ ClassLoader trước và sau JPMS

Java 8, kiểu hệ thống JDK thông dụng:

```text
bootstrap loader                (thường trả null từ getClassLoader)
        │
        ▼
extension loader                (một số extension JARs)
        │
        ▼
application / system loader     (classpath)
        │
        ▼
custom loaders                 (plugin/webapp/test)
```

Java 9+, mô hình phổ biến:

```text
bootstrap loader                     (java.base và một số module quan trọng)
        │
        ▼
platform loader                      (một số Java SE/JDK modules)
        │
        ▼
application / system loader          (classpath + các modules thích hợp)
        │
        ▼
custom loaders                       (tùy chính sách delegation/module)
```

**Cẩn trọng với hình vẽ:** đây là **quan hệ delegation** điển hình, **không phải quy tắc** rằng “mọi class `java.*` do platform loader định nghĩa”. JDK 9 chuyển **một số**, không phải tất cả, Java SE/JDK classes giữa bootstrap/platform loader. Javadoc cam kết các platform classes **visible through** platform loader, không cam kết tất cả đều **defined by** platform loader. Parent delegation cũng không bảo đảm class loader tự xây luôn parent-first nếu đã override `loadClass`.

**Nhớ:** `String.class.getClassLoader() == null` là biểu diễn bootstrap trong Java 8 lẫn JDK hiện đại; không có API public cho một “bootstrap ClassLoader instance” tương ứng theo cách các loaders khác có.

## 3. Java 8: extension loader và cơ chế thư mục `lib/ext`

Ở Java 8, extension mechanism cho phép Java runtime tìm một số JARs trong thư mục extension mà không yêu cầu chỉ ra từng JAR trên classpath. Nó gắn với **extension class loader** trong hierarchy thông dụng. Một số code cũ lấy parent của system loader và mặc định đó là extension loader, hoặc copy JAR trực tiếp tới `$JAVA_HOME/jre/lib/ext`.

Từ **JDK 9**, extension mechanism bị loại bỏ. Giải pháp **không phải** tạo lại `lib/ext` trong JDK mới, mà là đưa các libraries cần dùng vào **classpath, module path hoặc module configuration** phù hợp. Tên “extension loader” trong các mô tả cũ được thay bằng **platform loader**; mặc dù tổ tiên trong hierarchy có thể trông tương tự, **platform loader không còn quét `lib/ext` như Java 8**.

| Hành vi/code cũ | Trạng thái trên JDK 9+ | Hướng xử lý |
| --- | --- | --- |
| Copy custom JAR vào `jre/lib/ext` | Extension mechanism đã loại bỏ | Đưa vào app dependencies/classpath hoặc module path |
| Dùng `-Djava.ext.dirs=...` | Không còn giải pháp deployment hợp lệ | Xóa property, cấu hình dependencies tường minh |
| Dựa `lib/endorsed` / `java.endorsed.dirs` | Endorsed standards override mechanism bị loại bỏ | Xem upgradeable modules hoặc module path/classpath phù hợp |
| Giả định parent của app loader có thể đọc extension JARs cũ | Không còn đúng | Thiết kế loader graph/dependencies mới |
| Dùng literal class name `sun.misc.Launcher$ExtClassLoader` | Phụ thuộc implementation đã thay đổi | Dùng API `ClassLoader.getPlatformClassLoader()` nếu cần platform parent |

Một số thông báo lỗi từ JDK 9/10 khi còn `lib/ext` hoặc properties cũ có thể khiến VM không khởi động. **Đừng dùng `-XX:+IgnoreUnrecognizedVMOptions` làm “sửa” chính**: cấu hình cũ cần được loại bỏ và thay đúng mô hình deployment.

## 4. Application loader: vì sao không còn cast được sang `URLClassLoader`?

Trong Oracle/OpenJDK 8, nhiều ứng dụng từng viết:

```java
URLClassLoader app =
        (URLClassLoader) ClassLoader.getSystemClassLoader();
```

Đây là **mã phụ thuộc implementation**, không phải Java SE portable contract. Nó thường chạy trên JDK 8 HotSpot nhưng **không còn chạy** trên JDK 9+ built-in app loader: system loader được triển khai bằng internal implementation **không phải `URLClassLoader`**, nên có thể ném `ClassCastException`.

**Sửa theo nhu cầu:**

- **Muốn đọc application classpath:** xem `System.getProperty("java.class.path")` (lưu ý module path là cơ chế khác) và cấu hình launcher/build, không ép cast loader.
- **Muốn nạp plugin JAR ở runtime:** tạo `new URLClassLoader(urls, parent)` mà bạn **sở hữu** và quản lý lifecycle; chọn delegation/shared API đúng.
- **Muốn thêm dependency vào một named module:** dùng module resolution/layers hoặc cơ chế instrumentation/launcher phù hợp; không mong app loader có thể `addURL` như Java 8.
- **Muốn tìm JDK classes:** dùng public APIs của module/runtime image, không tìm hệ thống JAR để tự bổ sung search path.

**Không có API Java SE chung cho việc “thêm URL vào classpath của system loader” trong mọi implementation/JDK.** Việc cố reflectively gọi method nội bộ của `BuiltinClassLoader` rất dễ vấp JPMS strong encapsulation và không nên dùng làm kiến trúc.

## 5. Thực hành A — một chương trình Java 8 source để so sánh hai runtime

Mã chỉ dùng APIs đã có trên Java 8, nên có thể compile với JDK 8 hoặc **`javac --release 8`** trên JDK 17+. Chạy binary đó trên từng JDK để so khác biệt **runtime**, chứ không suy khác biệt từ compiler flags.

Tệp **`src/demo/PortableLoaderProbe.java`**:

```java
package demo;

import java.net.URL;
import java.net.URLClassLoader;

public final class PortableLoaderProbe {
    public static void main(String[] args) {
        ClassLoader system = ClassLoader.getSystemClassLoader();
        URL coreResource =
                ClassLoader.getSystemResource("java/lang/String.class");

        System.out.println("bootstrap String=" +
                (String.class.getClassLoader() == null));
        System.out.println("system is URLClassLoader=" +
                (system instanceof URLClassLoader));
        System.out.println("system parent exists=" +
                (system.getParent() != null));
        System.out.println("core resource protocol=" +
                (coreResource == null
                        ? "<unavailable>"
                        : coreResource.getProtocol()));
    }
}
```

Biên dịch/chạy trên **JDK 17+** từ thư mục project:

```sh
javac --release 8 -d out src/demo/PortableLoaderProbe.java
java -cp out demo.PortableLoaderProbe
```

**Stdout dự kiến trên OpenJDK/HotSpot 17:**

```text
bootstrap String=true
system is URLClassLoader=false
system parent exists=true
core resource protocol=jrt
```

Trên một máy có **Oracle/OpenJDK 8 thông dụng**, biên dịch bằng JDK 8:

```sh
javac -source 8 -target 8 -d out src/demo/PortableLoaderProbe.java
java -cp out demo.PortableLoaderProbe
```

**Stdout thường thấy trên Oracle/OpenJDK 8:**

```text
bootstrap String=true
system is URLClassLoader=true
system parent exists=true
core resource protocol=jar
```

**Giới hạn khẳng định:** các dòng kiểm tra implementation class của system loader và `getSystemResource` phản ánh **Oracle/OpenJDK/HotSpot trong cấu hình tiêu chuẩn**, **không phải bắt buộc trên mọi JVM**. User-defined `java.system.class.loader` hoặc custom JDK image có thể cho kết quả khác. Dòng `-source 8 -target 8` trên JDK 8 chỉ minh họa compile target; `--release 8` trên JDK 17 **không mô phỏng loader của Java 8**.

### Rút ra gì từ bốn dòng?

1. Bootstrap loader vẫn được đại diện bởi `null` ở `String.class.getClassLoader()`.
2. Built-in application loader đã đổi implementation trong modular JDK.
3. System loader vẫn thường có một parent object, nhưng trên JDK hiện đại parent đó là platform loader.
4. JDK runtime class resource chuyển từ dạng JAR resource (thường `jar:file:...rt.jar!...`) sang **`jrt:` resource** của modular runtime image.

## 6. `rt.jar`, `tools.jar`, `jrt:/` và modular runtime image

**Java 8:** nhiều JDK classes/resources nằm trong JARs như `jre/lib/rt.jar` và `lib/tools.jar`. Các công cụ/phần mềm cũ mở chúng bằng `JarFile` hoặc đọc từ những đường dẫn hardcoded.

**JDK 9+:** JEP 220/JPMS chuyển JDK image sang định dạng modular. Các file JAR nổi tiếng nói trên **không còn tồn tại với cấu trúc cũ**. Resource access có thể dùng **`jrt:/`** (JRT filesystem provider) để truy cập nội dung module runtime.

Ví dụ resource của Java SE class:

```text
Java 8 thường:
jar:file:/.../jre/lib/rt.jar!/java/lang/String.class

JDK 9+ thường:
jrt:/java.base/java/lang/String.class
```

Đây là **ví dụ URL minh họa**, không phải đường dẫn thật của mọi OS/JDK image. Nếu code tìm source JAR bằng cách strip `jar:file:` rồi tìm dấu `!`, nó sẽ hỏng trên JDK modular.

**Thay thế thích hợp:**

| Mục đích | Cách hiện đại |
| --- | --- |
| Đọc resource JDK module | `ClassLoader.getSystemResource` khi hợp lệ, `Module.getResourceAsStream`, `jrt:` filesystem |
| Liệt kê module runtime | `ModuleFinder.ofSystem()`, `java --list-modules` |
| Phân tích module dependencies | `jdeps` và metadata module |
| Đóng runtime nhỏ | `jlink` (module-aware runtime image) |
| Thư viện nội bộ app | Quản lý JAR riêng qua classpath/module path; không thêm vào `rt.jar` |
| Quan sát class đã load | `Class.getModule()`, `getClassLoader()`, optional `CodeSource`, `-Xlog:class+load` |

**Một JMOD không phải JAR classpath thông thường.** `.jmod` dùng cho đóng gói/linking modules trong JDK tooling; không nên kỳ vọng `URLClassLoader` đọc `jmods/java.base.jmod` như plugin JAR.

## 7. Thực hành B — kiểm chứng `jrt:` và module metadata trên Java 17+

Tệp **`src/demo/ModernRuntimeProbe.java`**:

```java
package demo;

import java.net.URL;

public final class ModernRuntimeProbe {
    public static void main(String[] args) {
        ClassLoader platform =
                ClassLoader.getPlatformClassLoader();
        ClassLoader app =
                ClassLoader.getSystemClassLoader();

        URL core = ClassLoader.getSystemResource(
                "java/lang/String.class");

        System.out.println("java.base module=" +
                String.class.getModule().getName());
        System.out.println("app module named=" +
                ModernRuntimeProbe.class.getModule().isNamed());
        System.out.println("String bootstrap=" +
                (String.class.getClassLoader() == null));
        System.out.println("app parent is platform=" +
                (app.getParent() == platform));
        System.out.println("JDK resource jrt=" +
                (core != null && "jrt".equals(core.getProtocol())));
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```sh
javac --release 17 -d out src/demo/ModernRuntimeProbe.java
java -cp out demo.ModernRuntimeProbe
```

**Stdout trên OpenJDK/HotSpot 17 trong cấu hình không thay system loader:**

```text
java.base module=java.base
app module named=false
String bootstrap=true
app parent is platform=true
JDK resource jrt=true
```

Các dòng kiểm tra:

- `String` thuộc named module **`java.base`**, nhưng vẫn do bootstrap định nghĩa trong cấu hình chuẩn.
- `ModernRuntimeProbe` chạy bằng `-cp out` nên thuộc **unnamed module** của app loader, không phải một named module do có package `demo`.
- `ClassLoader.getPlatformClassLoader()` là API mới từ JDK 9.
- Built-in app loader thường parent về platform loader. Nếu launcher thay system loader hoặc môi trường không chuẩn, không lấy chi tiết parent object này làm contract cho mọi triển khai.
- `ClassLoader.getSystemResource("java/lang/String.class")` thường trả `jrt:` URL trên modular HotSpot. Không đồng nhất `jrt:` với CodeSource URL; một class hoàn toàn hợp lệ có thể có `CodeSource == null`.

**Không dùng ví dụ này trên JDK 8**: code nhắc `getPlatformClassLoader` và `Class.getModule`, hai APIs chưa có ở source/runtime Java 8.

## 8. JPMS xuất hiện từ Java 9: classpath không biến mất

JPMS (**Java Platform Module System**, JEP 261) đem theo:

- `module-info.java` / module descriptor (`requires`, `exports`, `opens`, `uses`, `provides`).
- **Named modules**, module path và resolved module graph.
- **Unnamed modules** cho classpath classes; module metadata có thể truy vấn qua `Class.getModule()`.
- **Readability** giữa modules và **exports/opens** của packages.
- `ModuleLayer` để tạo những module configurations/layers mới tại runtime.
- Tích hợp module-aware service discovery và resource access.
- Class loaders có thể define classes thuộc các named modules, không chỉ tìm JARs trên một tuyến classpath.

Một class trên application classpath ở JDK 17 vẫn có `ClassLoader`, vẫn được load và vẫn có runtime type identity như Java 8, nhưng `Class.getModule().isNamed()` là **false** (unnamed module). Nếu cùng class được đóng gói/khởi chạy như **named module**, module metadata và access rules khác.

**Mô hình đúng:** từ Java 9+, cần đồng thời suy nghĩ về **“loader nào định nghĩa class?”** và **“class thuộc module/package nào, module có được đọc/export/open?”**.

## 9. Thực hành C — cùng source, so classpath mode với named-module mode

Dùng một class đơn giản để kiểm tra **module identity**. Tệp **`src/demo/ModuleModeDemo.java`**:

```java
package demo;

public final class ModuleModeDemo {
    public static void main(String[] args) {
        Module module = ModuleModeDemo.class.getModule();
        System.out.println("named=" + module.isNamed());
        System.out.println("module=" +
                (module.isNamed()
                        ? module.getName()
                        : "<unnamed>"));
    }
}
```

### C1. Chạy như Java 8-style classpath (trên JDK 17)

```sh
javac --release 17 -d out src/demo/ModuleModeDemo.java
java -cp out demo.ModuleModeDemo
```

**Stdout:**

```text
named=false
module=<unnamed>
```

### C2. Chạy như named module trên cùng JDK 17

Tạo tệp **`module-info.java`** ở project root:

```java
module com.example.probe {
    exports demo;
}
```

Biên dịch vào output directory **khác** để tránh nhầm classpath artifacts với module artifacts:

```sh
javac --release 17 -d mods/com.example.probe module-info.java src/demo/ModuleModeDemo.java
java --module-path mods -m com.example.probe/demo.ModuleModeDemo
```

**Stdout:**

```text
named=true
module=com.example.probe
```

**Điểm kiểm chứng:** source `ModuleModeDemo.java` không đổi, nhưng **cách launch và module descriptor** làm runtime class thuộc module khác. Không suy từ package name hoặc việc `javac` sinh `.class` rằng một class đã tự thuộc named module.

**Không nên biên dịch/running `module-info.java` bằng JDK 8** vì JPMS là API/tooling từ Java 9. Nếu library cần duy trì Java 8, cân nhắc **multi-release JAR, separate artifacts hoặc classpath-first build** theo nhu cầu, thay vì viết thẳng `module-info.java` rồi cố compile bằng `-source 8`.

## 10. Module layers và custom ClassLoaders

Trong Java 8, plugin frameworks thường tạo một `URLClassLoader` cho JARs rồi làm parent-first/child-first. JDK 9+ vẫn cho phép pattern này **trên classpath-style loading**, nhưng còn một lựa chọn: resolve **named modules** và define một `ModuleLayer` mới.

Mô hình:

```text
boot ModuleLayer
   ├─ java.base (bootstrap)
   ├─ java.logging, java.xml, ...
   └─ app modules
         │
         ▼
child ModuleLayer (plugin version/generation)
   ├─ com.example.plugin
   ├─ com.example.plugin.lib
   └─ loaders chosen by layer-definition API
```

Các APIs quan trọng:

- `ModuleFinder`: tìm descriptors/modules trên module path hoặc paths.
- `Configuration.resolve(...)`: tạo graph module được resolve; xác thực dependencies.
- `ModuleLayer.defineModulesWithOneLoader(...)`, `defineModulesWithManyLoaders(...)` hoặc `defineModules(...)`: tạo layer/module-to-loader mappings.
- `ModuleLayer.findLoader(moduleName)`: xác định loader của module trong layer.
- `Class.getModule()`: xem module của runtime class thực.
- `ServiceLoader.load(layer, Service.class)`: khám phá providers trong layer theo module-aware semantics.

**Lưu ý:** **module layer không phải OS sandbox**. Nó tăng khả năng tổ chức modules, version/configuration và access checks; code plugin vẫn thường chạy **trong cùng JVM/process và quyền OS**. Với code không tin cậy, có thể cần isolation cấp process/container/VM.

**Lưu ý về split packages:** named modules và class-loader mappings có những ràng buộc về package/module graph. Đừng chuyển nguyên bản thiết kế child-first loader “trộn nhiều JAR có cùng package” sang modules và mặc định nó sẽ hoạt động.

## 11. Exports và opens: thay đổi lớn với reflection

Trước Java 9, một library dùng reflection vào private members của JDK internals thường phụ thuộc implementation/security policy và có thể hoạt động trên Java 8. Từ Java 9, named modules có ranh giới:

- **`requires`**: module đọc module khác.
- **`exports p`**: package `p` được dùng qua public API bởi modules phù hợp.
- **`exports p to m`**: export có mục tiêu.
- **`opens p` / `opens p to m`**: hỗ trợ deep reflection theo scope.
- **`open module ...`**: mở nhiều packages để reflection, nhưng không làm mọi member thành public API theo nghĩa biên dịch.

**`public` chưa đủ** nếu target nằm trong package của named module không được export phù hợp. `setAccessible(true)` cũng không tự vượt qua JPMS khi package không được mở.

Từ **JDK 9–16**, migration từng cho phép một số relaxed illegal reflective access đối với JDK internals, kèm warnings/điều kiện. **JDK 17 (JEP 403)** áp dụng **strong encapsulation** mặc định với các JDK internals (ngoại trừ một số critical APIs); cơ chế nới lỏng hàng loạt kiểu cũ không còn. Nên **chuyển sang supported public APIs**, chỉ dùng `--add-opens`/`--add-exports` có chọn lọc cho migration nếu thực sự cần.

**Không tự coi mọi `InaccessibleObjectException` là vấn đề classpath.** Class đã tìm thấy; lỗi nằm ở module/package reflective access.

## 12. Thực hành D — deep reflection vào JDK internals bị chặn từ Java 17

Tệp **`src/demo/ReflectionBoundaryDemo.java`**:

```java
package demo;

import java.lang.reflect.Field;
import java.lang.reflect.InaccessibleObjectException;

public final class ReflectionBoundaryDemo {
    public static void main(String[] args) throws Exception {
        Field internal = String.class.getDeclaredField("value");

        try {
            internal.setAccessible(true);
            System.out.println("opened=true");
        } catch (InaccessibleObjectException denied) {
            System.out.println("opened=false");
        }

        System.out.println("owner module=" +
                String.class.getModule().getName());
    }
}
```

Biên dịch/chạy trên **JDK 17+**, không thêm `--add-opens`:

```sh
javac --release 17 -d out src/demo/ReflectionBoundaryDemo.java
java -cp out demo.ReflectionBoundaryDemo
```

**Stdout dự kiến trên OpenJDK/HotSpot 17 với mặc định JPMS:**

```text
opened=false
owner module=java.base
```

Nếu operator **cố ý** mở package `java.lang` của `java.base` cho unnamed modules:

```sh
java --add-opens java.base/java.lang=ALL-UNNAMED -cp out demo.ReflectionBoundaryDemo
```

**Stdout khi opening được JVM chấp nhận:**

```text
opened=true
owner module=java.base
```

**Ý nghĩa:** target class đã tồn tại, loader không có vấn đề. Chỉ **module openness** thay đổi reflective access outcome. `--add-opens` là lựa chọn có rủi ro và cần chỉ định package/scope; **không thêm wildcard opens toàn bộ JDK** như giải pháp mặc định.

**Cẩn trọng:** đây là demo về access check, **không khuyến khích đọc hoặc sửa private representation của `String`** trong sản phẩm. Chi tiết internal fields có thể thay đổi giữa JDK versions; demo chỉ cần metadata field `value` vốn có trên OpenJDK 17 và kiểm tra `setAccessible`.

## 13. Named module vs classpath resource lookup

`ClassLoader.getResource` và `Class.getResource` tồn tại từ Java 8, nhưng JDK 9+ thêm **module encapsulation** đối với resource lookup.

Ví dụ:

```java
URL resource =
        ClassLoader.getSystemResource("sample/config.properties");
```

Đây là **snippet** cần import `java.net.URL` và resource tồn tại. Trên classpath, kết quả thường chịu class loader delegation và search paths. Với resource trong named module, public resource lookup **có thể bị hạn chế** nếu package chứa resource chưa được **opened unconditionally** theo Javadoc của `ClassLoader.getResource`. Có ngoại lệ đặc biệt cho tên kết thúc bằng `".class"`, nhưng không nên coi đó là cách truy cập arbitrary module internals.

So sánh:

| Trường hợp | Java 8-style classpath | Java 9+ named module |
| --- | --- | --- |
| `config.properties` cùng JAR | Thường có thể tìm qua loader resource lookup nếu path đúng | Có thể `null` nếu package không mở phù hợp |
| Resource `.class` của JDK | Thường `jar:...rt.jar!...` | Thường `jrt:/module/...` |
| `Class.getResource` | Dựa package-relative path và loader | Với named module còn module-scoped lookup/encapsulation |
| `Module.getResourceAsStream` | Chưa có API này | Dùng module-specific resource lookup với access rules |
| Quét `META-INF/services` | SPI classpath descriptor | Có thêm JPMS provider declarations ngoài descriptors |

**Gỡ lỗi:** log requested resource name, loader, module, package openness và actual URL. Một `null` từ resource lookup **không luôn nghĩa file bị thiếu khỏi artifact**.

## 14. ServiceLoader: Java 8 descriptors và Java 9+ module providers

**Java 8/classpath SPI**:

```text
META-INF/services/com.example.spi.Parser
    └─ dòng: com.example.impl.FastParser
```

JDK 9+ vẫn hỗ trợ cơ chế này cho classpath/unnamed-module providers, nhưng named modules có:

```java
module com.example.consumer {
    requires com.example.api;
    uses com.example.api.Parser;
}
```

và:

```java
module com.example.provider {
    requires com.example.api;
    provides com.example.api.Parser
        with com.example.impl.FastParser;
}
```

Đây là **module-info snippets**, cần modules và classes tương ứng nếu muốn compile. Các APIs Java 9+:

- `ServiceLoader.load(layer, service)`: khám phá providers trong module layer.
- `ServiceLoader.stream()`: trả `Stream<ServiceLoader.Provider<S>>` để xem provider metadata lazily.
- `Provider.type()` và `Provider.get()`: phân biệt type inspection và lấy provider instance.

Cảnh báo vẫn quan trọng trên cả JDK cũ/mới: `ServiceLoader` là **lazy**, có provider cache, không thread-safe cho concurrent use trên **cùng instance**. `reload()` xóa provider cache nhưng **không redefine JVM classes**. TCCL ảnh hưởng overload `ServiceLoader.load(service)`; đừng mặc định `Class.forName(String)` dùng TCCL.

## 15. ClassLoader APIs: cũ, mới và phạm vi dùng

| API | Có trên Java 8? | Java 9+ | Ghi chú |
| --- | --- | --- | --- |
| `ClassLoader.loadClass(String)` | Có | Có | Không yêu cầu initialization theo hành vi chuẩn |
| `ClassLoader.defineClass` | Có | Có | Protected final, tạo runtime class, không tạo instance |
| `ClassLoader.findClass(String)` | Có | Có | Hook subclass; thường override thay vì thay cả `loadClass` |
| `ClassLoader.getSystemClassLoader()` | Có | Có | Trả system loader, implementation-dependent |
| `ClassLoader.getPlatformClassLoader()` | **Không** | **Có, từ 9** | Dùng khi cần platform loader as parent |
| `ClassLoader.getName()` | **Không** | **Có, từ 9** | Loader name có thể null, không unique |
| `ClassLoader.getUnnamedModule()` | **Không** | **Có, từ 9** | Unnamed module associated với loader |
| `Class.getModule()` | **Không** | **Có, từ 9** | Module của runtime type |
| `Class.forName(Module,String)` | **Không** | **Có, từ 9** | Không init target; có thể trả null |
| `ClassLoader.findClass(moduleName,name)` | **Không** | **Có, từ 9** | Cho loader hỗ trợ named modules |
| `ClassLoader.findResource(moduleName,name)` | **Không** | **Có, từ 9** | Resource lookup gắn module |
| `ClassLoader.resources(String)` | **Không** | **Có, từ 9** | Stream các resource URLs |
| `ModuleLayer`/`ModuleFinder` | **Không** | **Có, từ 9** | Module graph và layers |
| `MethodHandles.Lookup.defineClass(byte[])` | **Không** | **Có, từ 9** | Define class same loader/runtime package từ lookup |
| `MethodHandles.Lookup.defineHiddenClass` | **Không** | **Có, từ 15** | Hidden classes cho runtime frameworks |
| `ClassLoader.registerAsParallelCapable()` | **Có** | **Có** | Không phải tính năng mới của JPMS |
| `ClassLoader.getClassLoadingLock(String)` | **Có** | **Có** | Synchronization của loader, khác class-init lock |
| `Thread.getContextClassLoader()` | **Có** | **Có** | TCCL vẫn dùng cho SPI/framework |

**Sai lầm thường gặp:** gắn mọi API có chữ “loader” vào JDK 9. Ví dụ `registerAsParallelCapable` đã có từ trước, và **ClassLoader parent delegation không bị JPMS phát minh lại từ đầu**.

## 16. Binary compatibility và class-file major versions

| Java release | Class-file major |
| --- | ---: |
| Java 8 | 52 |
| Java 9 | 53 |
| Java 10 | 54 |
| Java 11 | 55 |
| Java 12 | 56 |
| Java 13 | 57 |
| Java 14 | 58 |
| Java 15 | 59 |
| Java 16 | 60 |
| Java 17 | 61 |
| Java 18 | 62 |
| Java 19 | 63 |
| Java 20 | 64 |
| Java 21 | 65 |
| Java 22 | 66 |
| Java 23 | 67 |
| Java 24 | 68 |
| Java 25 | 69 |

**Quan trọng:** class compiled cho Java 17 (major 61) **không thể chạy trực tiếp trên JVM Java 8** (chỉ hiểu tối đa 52). JVM hiện đại thường hỗ trợ classfile versions cũ, nhưng việc một thư viện “được compile từ Java 8” không bảo đảm không phụ thuộc các **internal APIs bị loại bỏ** hoặc reflective access bị JPMS chặn.

Lệnh kiểm tra:

```sh
java -version
javac -version
javap -verbose -classpath out demo.PortableLoaderProbe
```

Trong `javap -verbose`, tìm **`major version`**. Nếu bạn dùng JDK 17+ và muốn build library tương thích Java 8:

```sh
javac --release 8 -d out src/demo/PortableLoaderProbe.java
```

`--release 8` thiết lập target bytecode và supported API view phù hợp với release 8. Nhưng nó **không chuyển runtime Java 17 thành Java 8**, không khôi phục `rt.jar`, không biến system loader thành `URLClassLoader`.

### Multi-release JAR (JDK 9+)

Một **multi-release JAR** có thể chứa code baseline (ví dụ Java 8) và overrides dưới `META-INF/versions/9`, `META-INF/versions/17` ... với manifest `Multi-Release: true`. Tùy runtime, class/resource resolution chọn entry thích hợp theo cơ chế JEP 238. Đây là chiến lược compatibility, không tự sửa tất cả khác biệt về module encapsulation và loader identity.

**Đừng** đặt hai classes cùng binary name ngoài cơ chế multi-release/loader boundaries rồi mặc định JVM có thể chọn phiên bản theo ý bạn. Cần packaging/build tool đúng, test trên runtimes mục tiêu.

## 17. Class identity và loader constraints: những quy tắc không đổi

Dù có JPMS, runtime class vẫn được phân biệt theo **binary name và defining loader**. Một ví dụ:

```text
loader-A defines p.ServiceImpl → Class A
loader-B defines p.ServiceImpl → Class B

A.getName().equals(B.getName()) = true
A == B = false
```

Nếu hai loaders tự định nghĩa **bản sao API interface** thay vì delegate tới host, plugin implementation có thể gây `ClassCastException` hoặc loader-constraint `LinkageError`. Điều này đúng từ Java 8 và **không tự được giải quyết bởi module path**.

Những quy tắc cần giữ:

- Shared API/DTO/exception classes phải có defining-loader strategy nhất quán.
- `Class<?>` có thể thuộc named hoặc unnamed module; module name không thay binary name.
- `Class.getPackageName()` giống nhau **chưa bảo đảm same runtime package**, vì runtime package identity còn phụ thuộc defining loader.
- Parent-first delegation là mặc định của nhiều built-in/classpath loaders, nhưng custom child-first loader cần kiểm soát trùng definition và synchronization.
- Plugin reload muốn định nghĩa lại cùng binary name thường dùng **new defining loader generation**. `URLClassLoader.close()` không unload classes tức thì.
- Class loading, linking và initialization vẫn là những giai đoạn khác nhau. `Class.forName(name,true,loader)` yêu cầu initialization; `loadClass` chuẩn không.

**JPMS bổ sung module readability/exports/opens**, không thay thế toàn bộ các quy tắc identity/linking của JVM.

## 18. Custom loader parent nên là `null` hay platform loader?

Một pattern Java 8:

```java
ClassLoader isolated =
        new java.net.URLClassLoader(urls, null);
```

Đây là **snippet** cần biến `urls`. Parent `null` thường biểu diễn bootstrap-only parent, nhưng **từ JDK 9 bootstrap định nghĩa ít Java SE classes hơn** so với Java 8. Nếu custom loader muốn thấy platform classes mà không phụ thuộc system application loader, nên cân nhắc:

```java
ClassLoader platform =
        ClassLoader.getPlatformClassLoader();

java.net.URLClassLoader isolated =
        new java.net.URLClassLoader(urls, platform);
```

Đây là **snippet Java 9+**, cần `urls` hợp lệ và close loader khi lifecycle kết thúc. Dùng platform parent không có nghĩa plugin sẽ thấy tất cả application classes; đó có thể chính là mục tiêu isolation.

Cân nhắc ba chọn lựa:

| Parent | Ưu điểm | Nguy cơ/cần lưu ý |
| --- | --- | --- |
| `null` | Bớt visibility tới application/platform loader objects | Có thể thiếu Java SE/JDK modules do platform loader define |
| `ClassLoader.getPlatformClassLoader()` | Thấy platform classes mà hạn chế app classes | Shared app API không tự visible; cần thiết kế API sharing |
| `ClassLoader.getSystemClassLoader()` | Dễ thấy host APIs/dependencies | Parent-first có thể “nuốt” plugin version nếu host chứa trùng dependencies |

**Không có một parent tối ưu tuyệt đối cho mọi plugin.** Nó phụ thuộc shared contracts, API isolation, module graph, security threat model và lifecycle. `ClassLoader` không phải sandbox cho mã không đáng tin ngay cả khi parent là `null`.

## 19. Code generation: `Lookup.defineClass` và hidden classes

Java 8 frameworks thường dùng `ClassLoader#defineClass` (qua subclass), reflection vào internals hoặc những API không portable để sinh lớp. Java 9 thêm:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
Class<?> generated = lookup.defineClass(bytes);
```

Đây là **snippet Java 9+**, cần import `java.lang.invoke.MethodHandles`, bytes của một class **cùng package** với lookup class, lookup có **PACKAGE** privileges. API định nghĩa named class với loader, runtime package và protection domain phù hợp với lookup class. Không thể dùng lookup bất kỳ để inject class vào package/module khác.

Từ **JDK 15**, `Lookup.defineHiddenClass` phục vụ anonymous-like/hidden runtime implementation types (JEP 371). Hidden classes không thiết kế để discover bằng binary name thông thường; rất hữu ích cho proxies/lambda/runtime language infrastructure, nhưng không phải replacement trực tiếp cho plugin APIs dựa trên `Class.forName("p.Name")`.

**Di chuyển thư viện sinh bytecode từ Java 8:**

1. Chọn đúng JVM target major version.
2. Dùng API lookup/hidden-class phù hợp thay vì reflection vào JDK internals.
3. Kiểm tra `NestHost`/`NestMembers`, sealed classes, records và package/module rules trên JDK 17+.
4. Đảm bảo framework phát hành có bản hỗ trợ JDK 17/21/25 nếu production dùng.
5. Không dựa vào `--add-opens` hàng loạt như kiến trúc vĩnh viễn.

## 20. Security Manager không phải tương lai của plugin isolation

Java 8 có Security Manager và permission model từng được các hệ thống dùng để hạn chế code dựa trên code source. Nhưng ngay cả khi đã bật, việc xây sandbox đáng tin từ **ClassLoader + SecurityManager** luôn đòi threat model và cấu hình đúng.

Mốc thay đổi:

| Mốc | Ý nghĩa |
| --- | --- |
| Java 8 | Security Manager và policy-based permission checks còn được dùng |
| Java 17 | JEP 411 **deprecated for removal** Security Manager |
| Java 24 | JEP 486 **permanently disables Security Manager** |
| Java 25+ | Không dùng Security Manager để xây sandbox Java truyền thống |

Khi cần chạy code plugin không tin cậy, giải pháp thực tế là **tách tiến trình/VM/container với OS permissions, resource quotas, filesystem/network policy và IPC validation**, không chỉ tùy biến `ClassLoader`. Một process riêng mà vẫn có toàn quyền host cũng **chưa tự thành sandbox**.

## 21. Diagnostics: lỗi cũ và lỗi mới thường gặp sau migration

| Lỗi/triệu chứng | Java 8 thường liên quan | Khi chuyển sang Java 9+ | Cách điều tra |
| --- | --- | --- | --- |
| `ClassCastException` của system loader → URLClassLoader | Implementation cast từng chạy | App loader không còn URLClassLoader | Bỏ cast, dùng custom URLClassLoader/API chính thức |
| `ClassNotFoundException` cho extension JAR | JAR được tìm qua `lib/ext` | Extension mechanism không còn | Đưa dependency vào classpath/module path |
| Tool báo không có `rt.jar`/`tools.jar` | Hardcode cấu trúc JDK 8 | Modular runtime image, `jrt:` | Cập nhật tool, dùng `ModuleReader`/jrt |
| `NoClassDefFoundError` cho platform API | Bootstrap parent từng thấy class | Class có thể do platform loader define | Chọn platform parent phù hợp |
| `IllegalAccessError` | Package/runtime type/access check | Thêm module readability/exports | Log caller/target loader/module/package |
| `InaccessibleObjectException` | Java 8 không có loại lỗi JPMS này | Deep reflection bị module openness chặn | Dùng public API, `--add-opens` khi bắt buộc |
| `ServiceConfigurationError` | Descriptor/classpath/TCCL issue | Còn có `uses/provides` và module layers | Kiểm tra service type, provider module và loader |
| `UnsupportedClassVersionError` | Target bytecode > major 52 | Vẫn xảy ra nếu target > JVM version | `javap -verbose`, build `--release` |
| Resource lookup trả `null` | Missing path/JAR | Có thể package named module chưa opened | Kiểm tra `Module.getResourceAsStream`/opens |
| `ClassNotFoundException` trong plugin child | Parent/classpath wrong | Vừa parent vừa module graph wrong | Ghi requested/defining loader, layer, code source |
| `NoSuchMethodError` sau nâng JDK/library | Binary signature mismatch | JDK internal APIs/version skew | Đối chiếu `javap -s` và artifacts |
| Custom bytecode framework fail | Constructor/ASM verifier mismatch | Classfile attributes/modules/nests mới | Nâng framework/ASM, test target release |

**Không đoán lỗi chỉ bằng exception class.** `NoClassDefFoundError` có thể do missing dependency hoặc **class initialization đã thất bại**; `ClassCastException` có thể do hai types trùng binary name khác defining loaders. Ghi cả **cause chain, loader identity, module và code source** nếu có.

## 22. Lệnh tra cứu hữu ích trên JDK hiện đại

### Module inventory

```sh
java --list-modules
java --describe-module java.base
```

Các lệnh giúp xem module graph/runtime image, không tự xác định custom loader của từng plugin class.

### Kiểm tra dependencies và JDK internals

```sh
jdeps --jdk-internals path/to/application.jar
jdeps --multi-release 17 path/to/application.jar
```

Lệnh là **mẫu**, cần thay `path/to/application.jar`. `jdeps` hỗ trợ tìm phụ thuộc internal APIs và multi-release JAR; nó không thể chứng minh mọi reflective access từ strings/dynamic loading đều được phát hiện.

### Class loading logs

```sh
java -Xlog:class+load=info -cp out demo.ModernRuntimeProbe
java -Xlog:help
```

`-Xlog:class+load` là giao diện **HotSpot Unified Logging** trên JDK 9+, không phải cú pháp có cùng semantics trên mọi JVM. Java 8 từng dùng `-verbose:class` để quan sát tương tự, nhưng output formatting khác. Không viết parser nghiệp vụ dựa vào text log này.

### Xem class file version và binary methods

```sh
javap -verbose -classpath out demo.ModernRuntimeProbe
javap -s -classpath path/to/library.jar com.example.Library
```

`-verbose` hiển thị `major version`; `-s` giúp so method descriptors khi gặp `NoSuchMethodError`.

### Xem resource từ module image

```sh
jimage list "$JAVA_HOME/lib/modules"
```

Lệnh dành cho JDK có công cụ `jimage`, path theo cú pháp shell POSIX. Thư mục runtime có thể khác tùy custom image; không hardcode cấu trúc khi phát hành ứng dụng portable.

## 23. Quy trình chuyển một plugin framework Java 8 sang Java 17+

**Bước 1 — phân loại code cũ.** Tìm việc cast system loader sang `URLClassLoader`, gọi `sun.*`/`com.sun.*` internals, sử dụng `lib/ext`/`rt.jar`, sửa `java.class.path` giữa runtime, dùng reflection vào JDK private members.

**Bước 2 — xác định mô hình deployment.** Nếu toàn bộ plugins là classpath JARs, có thể giữ `URLClassLoader` riêng của plugin dưới parent phù hợp. Nếu hệ thống muốn **named modules**, thiết kế `ModuleLayer`/module graph/`uses`/`provides`. Không cần module hóa mọi thư viện chỉ để chạy trên JDK 17.

**Bước 3 — định nghĩa shared API identity.** Đảm bảo host và plugins cùng resolve API types (interfaces, DTOs, exceptions) qua một defining loader được đồng ý. Kiểm tra `Class.getClassLoader()` và `Class.getModule()` khi debug.

**Bước 4 — sửa resource discovery.** Dùng đúng `META-INF/services` trên classpath hoặc module `uses/provides` trong named modules. Không giả định một loader nhìn thấy resource trong mọi named module; xét package opens.

**Bước 5 — loại phụ thuộc internals.** Thay reflective hacks bằng public Java APIs khi có, nâng bytecode/framework dependencies. Sử dụng `--add-opens` tạm thời, giới hạn đúng module/package/caller, có kế hoạch loại bỏ.

**Bước 6 — kiểm tra multi-release/version.** Phân biệt `javac --release 8` (target API/bytecode cũ) và JDK 17 runtime behavior. Kiểm tra `major version` của artifacts, thử trên JDK 8 nếu vẫn tuyên bố hỗ trợ.

**Bước 7 — test trong đúng loader graph.** IDE thường đưa JAR plugin lên host classpath, làm parent-first trả class của host. Phải test với host/plugin artifacts tách riêng, xác nhận defining loaders/module layers.

**Bước 8 — quản lý lifecycle.** Khi reload plugin, tạo loader/layer generation mới phù hợp, drain tasks và release references. `URLClassLoader.close()` không tự unload hết classes ngay; `ServiceLoader.reload()` chỉ xóa provider cache.

**Bước 9 — tạo diagnostics.** In requested class, lookup loader/TCCL, runtime defining loader, named/unnamed module, CodeSource location nếu có, cause chain, artifact ID/version và JDK release. Không lộ secrets/log URLs vô kiểm soát.

**Bước 10 — tách security boundary.** Nếu plugin là code không tin cậy, module/class loader chỉ là phần của architecture, không thay cho OS sandbox/process separation.

## 24. Bảng quyết định: dùng công nghệ nào?

| Nhu cầu | Java 8-style giải pháp | Trên JDK hiện đại nên cân nhắc |
| --- | --- | --- |
| Nạp một JAR plugin động | `URLClassLoader` riêng | Vẫn dùng được cho classpath plugin; chọn parent/close hợp lý |
| Cách ly hai phiên bản thư viện | Child loader tùy biến | Child loaders hoặc module layers tùy packaging |
| Mô tả API dependencies/module boundary | Maven/Gradle + classpath | Thêm `module-info.java` khi cần named modules |
| Plugin discovery | `META-INF/services` | Descriptor hoặc module `uses/provides`, ServiceLoader |
| Tạo runtime class cùng package host | Custom `defineClass`/framework hacks | `MethodHandles.Lookup.defineClass` với đúng lookup privileges |
| Sinh implementation class không cần binary name discovery | Framework-specific code gen | Hidden class API trong trường hợp phù hợp |
| Duyệt JDK classes | Đọc `rt.jar` | `jrt:`, `ModuleReader`, `jimage`/`jmod` tools |
| Quan sát loader | `Class.getClassLoader()` | Thêm `getModule()`/module layer, loader name/code source |
| Dùng JDK internals | Reflection hack | Thay bằng supported API, tránh `--add-opens` thường trực |
| Bảo mật plugin không đáng tin | Security Manager/class loader cũ | OS-sandboxed separate process/container/VM với IPC |
| Duy trì thư viện cho Java 8 và 17 | Java 8 bytecode | `--release 8` + test trên cả JDK 8/17; cân nhắc multi-release JAR |

**Không có một “công nghệ thay thế ClassLoader” toàn diện.** Module layer quản lý graph và encapsulation; ClassLoader định nghĩa/tra cứu runtime types; process boundary quản lý fault/security isolation ở cấp OS. Chọn công cụ theo ranh giới cần kiểm soát.

## 25. Những ngộ nhận điển hình sau nâng JDK

1. **“Java 9 bỏ classpath.”** Sai: classpath/unnamed modules vẫn hỗ trợ rộng rãi.
2. **“Extension loader mất hẳn nên mọi parent đều bootstrap.”** Sai: extension mechanism bị loại bỏ, nhưng **platform class loader** tồn tại.
3. **“Platform loader định nghĩa mọi class của Java SE.”** Sai: có classes do bootstrap định nghĩa; platform loader chỉ đảm bảo visibility cần thiết.
4. **“`getSystemClassLoader()` luôn trả `URLClassLoader`.”** Không đúng ở modular JDK và chưa từng là Java SE contract.
5. **“`ClassLoader.getPlatformClassLoader()` có trên Java 8.”** Sai: thêm từ Java 9.
6. **“`rt.jar` vẫn có thể đọc nếu tìm đúng thư mục JDK 17.”** Sai: modular runtime image dùng cấu trúc khác.
7. **“`jrt:` chính là JAR URL.”** Sai: filesystem/scheme riêng của runtime image.
8. **“`Class.getModule().getName()==null` là lỗi.”** Sai: unnamed module hợp lệ.
9. **“Dùng `module-info.java` thì class loader identity không còn ý nghĩa.”** Sai: binary name + defining loader vẫn quan trọng.
10. **“`public` luôn truy cập được từ mọi module.”** Sai: còn `exports`/readability.
11. **“`--add-opens` sửa classpath thiếu class.”** Sai: nó mở deep reflection, không thêm missing dependency.
12. **“`--add-exports` và `--add-opens` giống nhau.”** Không; một cái export public API, cái kia cho deep reflection theo scope.
13. **“`loadClass` chạy static initializer.”** Không theo implementation chuẩn; `Class.forName(name,true,loader)` mới yêu cầu initialize.
14. **“Module layer là sandbox.”** Không; plugin vẫn thường cùng JVM/OS permissions.
15. **“Chỉ cần chuyển dependency lên module path là mọi JAR lập tức modular với access giống named module.”** Không; automatic modules, explicit modules và unnamed modules có semantics khác nhau.
16. **“JDK 17 cho phép illegal reflective access cũ chỉ bằng một flag tổng quát.”** Không đúng với JEP 403 strong encapsulation.
17. **“Mọi công cụ JDK 8 sẽ chạy unchanged chỉ cần build `--release 8`.”** Không nếu nó hardcode runtime internals, directory layout hoặc reflection.
18. **“`ServiceLoader.reload()` redefines provider class.”** Không; nó clear cache, không thay runtime definition.
19. **“Một JAR trên module path chắc chắn được resolution và load.”** Không; cần module roots, dependencies và graph phù hợp.
20. **“Java 8 và Java 17 classfile cùng major version.”** Sai: 52 so với 61; JDK 21 major 65, JDK 25 major 69.

## 26. Câu hỏi tự kiểm tra

**1. Thay đổi class loader built-in nổi bật ở Java 9 là gì?** Extension loader được thay bằng **platform loader** trong mô hình mới; app loader built-in không còn là `URLClassLoader`.

**2. Java 9 có xóa parent delegation hay không?** Không; Java vẫn có delegation, dù module-aware loading phức tạp hơn.

**3. Có nên cast system loader sang `URLClassLoader` trên Java 17?** Không. Dùng custom `URLClassLoader` do ứng dụng sở hữu nếu cần URL-based plugin loading.

**4. Khi một custom loader cần platform classes nhưng không muốn app dependencies, parent nào nên cân nhắc?** `ClassLoader.getPlatformClassLoader()`.

**5. `Class.getModule()` có từ Java mấy?** Java 9.

**6. Class chạy trên `-cp` ở JDK 17 có thuộc module không?** Có; thường thuộc **unnamed module**.

**7. JDK 17 còn `rt.jar` ở vị trí Java 8 không?** Không; modular runtime image và `jrt:`.

**8. `String.class.getClassLoader()==null` vẫn hợp lệ trên Java 17?** Có; thường là bootstrap representation.

**9. Major classfile của Java 8, 17, 21 và 25 là gì?** 52, 61, 65, 69.

**10. `--release 8` làm app loader Java 17 thành Java 8 app loader?** Không; compile target và runtime behavior là hai việc khác.

**11. Deep reflection vào JDK internal `java.base/java.lang` từ unnamed module có thể bị gì trên Java 17?** `InaccessibleObjectException` trừ khi có openness được cấp hợp lệ.

**12. Java 9 thêm cách nào để define class cùng package/loader với lookup class?** `MethodHandles.Lookup.defineClass`.

**13. Named modules dùng API nào để khai báo service providers?** `uses`/`provides ... with ...`.

**14. ModuleLayer có tự tách heap/process cho plugin không?** Không; cần process boundary nếu yêu cầu isolation mạnh hơn.

**15. Làm sao xác định JDK runtime class resource trên modular runtime?** Sử dụng `jrt:`/Module APIs thay vì hardcode `rt.jar`.

**16. Tên class giống nhau nhưng hai defining loaders khác nhau có cùng runtime type identity không?** Không.

**17. `ServiceLoader.reload()` có làm version mới của class tự xuất hiện nếu loader cũ đã define class không?** Không.

**18. Vì sao resource tồn tại trong named module nhưng `ClassLoader.getResource` vẫn trả null?** Package resource có thể chưa được opened thích hợp theo module encapsulation.

**19. Class loader riêng có đảm bảo mã plugin không thể truy cập file/network không?** Không; cần OS permissions/sandbox.

**20. Khi di chuyển Java 8 → 17 nên test trên môi trường nào?** Cả build/runtime target cần hỗ trợ, đúng module/classpath configuration và loader graph thực tế, không chỉ IDE.

## 27. Nguồn chính thức và mốc kỹ thuật

- [Oracle JDK 17 Migration Guide — Migrating from JDK 8](https://docs.oracle.com/en/java/javase/17/migrate/migrating-jdk-8-later-jdk-releases.html): khác biệt class loaders, modular runtime images, extension mechanisms và strong encapsulation.
- [Oracle JDK 9 Migration Guide](https://docs.oracle.com/javase/9/migrate/): mốc Java 8 → 9, tên loader, `rt.jar` và module system.
- [JEP 261 — Module System](https://openjdk.org/jeps/261): JPMS, module path và module-aware class loading.
- [JEP 220 — Modular Run-Time Images](https://openjdk.org/jeps/220): JDK image/JRT và thay đổi layout từ JARs.
- [JEP 238 — Multi-Release JAR Files](https://openjdk.org/jeps/238): JAR version-specific class entries.
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): strong encapsulation ở JDK 17.
- [JEP 411 — Deprecate the Security Manager for Removal](https://openjdk.org/jeps/411): JDK 17 deprecation.
- [JEP 486 — Permanently Disable the Security Manager](https://openjdk.org/jeps/486): JDK 24 security manager change.
- [JEP 371 — Hidden Classes](https://openjdk.org/jeps/371): API phục vụ dynamic runtime code generation từ JDK 15.
- [Java SE 17 ClassLoader Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `getPlatformClassLoader`, `getSystemClassLoader`, module-aware resource/findClass APIs.
- [Java SE 17 Class Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getModule`, `forName`, runtime class metadata.
- [Java SE 25 ClassLoader Javadoc](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): hợp đồng ClassLoader trên JDK hiện đại.
- [Java Virtual Machine Specification 17, Chapter 5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): loading/linking/initialization và runtime type identity.

**Kết luận:** Java 8 → Java hiện đại **không xóa ClassLoader**; nó chuyển runtime thành hệ **modules**, đổi implementation loader mặc định, loại `rt.jar` và extension dirs, bổ sung **platform loader**, module metadata/layers, rồi siết access vào JDK internals. Điều không đổi là **binary name + defining loader quyết định runtime type**, cùng các nguyên tắc loading/linking/initialization và nhu cầu quản lý class loader lifecycle. Khi nâng cấp, hãy **bỏ cast system loader**, ngừng hardcode JDK JARs, xác định classpath/module path rõ ràng và log đồng thời **loader + module + CodeSource** để chẩn đoán chính xác.

# In tên lớp, loader, module và nguồn mã trong thông tin lỗi Java

Khi ứng dụng Java có nhiều `ClassLoader` — plugin, application server, test runner, service provider hoặc module layer — chỉ in `ClassNotFoundException: com.example.Plugin` thường **không đủ để chẩn đoán**. Tên lớp đúng không có nghĩa JVM đã dùng **đúng định nghĩa class**. Hai loaders có thể định nghĩa hai runtime types trùng tên; một JAR cũ của parent có thể thắng JAR mới của plugin; một class thuộc named module có thể chịu ràng buộc exports/opens. Vì thế, thông tin lỗi hữu ích nên ghi được ít nhất:

1. **Tên class được yêu cầu hoặc class thực sự liên quan** (`Class.getName()`).
2. **Defining loader** (`Class.getClassLoader()`): object loader nào đã định nghĩa runtime class, với tên và loại loader để phân biệt.
3. **Module thực tế** (`Class.getModule()`): module có tên hay unnamed module và layer nếu cần.
4. **Nguồn mã (code source)** (`Class.getProtectionDomain().getCodeSource().getLocation()`), khi được cung cấp.
5. **Loại lỗi, cause chain, stacktrace, hành động đang thực hiện và loader được dùng để tra cứu**; phân biệt *lookup loader* với *defining loader*.
6. **Ngữ cảnh phiên bản và triển khai**: plugin ID/generation, expected artifact/version, Java runtime version và request/correlation ID, không làm lộ secrets.

Bài Knowledge này thuộc **Java core – classloader / Chẩn đoán**, tập trung vào chủ đề **“In tên lớp, loader, module và nguồn mã trong thông tin lỗi”** trên Java 17+. Các ví dụ đi từ log metadata tối thiểu đến xung đột hai class loaders, lỗi lookup và lỗi initialization; mỗi chương trình chạy độc lập có lệnh biên dịch/chạy và stdout dự kiến.

## 1. Một ví dụ vấn đề: cùng class name nhưng khác ý nghĩa

Giả sử:

```text
Host application classpath
  com.example.api.Widget   (loader = app)

Plugin A
  com.example.impl.Parser  (loader = plugin-A)
  com.example.lib.Json     (v1, loader = plugin-A)

Plugin B
  com.example.impl.Parser  (loader = plugin-B)
  com.example.lib.Json     (v2, loader = plugin-B)
```

Nếu hai plugin tự nạp `com.example.impl.Parser`, `ParserA.getName()` và `ParserB.getName()` giống nhau, nhưng:

```java
System.out.println(ParserA == ParserB);
```

Đây là **snippet** cần hai biến `Class<?> ParserA` và `Class<?> ParserB`. Kết quả có thể là `false`, bởi JVM xác định runtime class identity bằng **binary name + defining class loader**.

Thông điệp:

```text
java.lang.ClassCastException: class com.example.impl.Parser ...
```

chưa giúp trả lời được “class này **do loader nào định nghĩa** và lấy bytes từ artifact nào?”. Nếu kèm defining loader, module và code source, ta có thể xác định class phiên bản cũ/tầng plugin sai mà không suy đoán từ source tree.

**Nguyên tắc:** chẩn đoán class loader dựa trên **runtime `Class<?>` object** và những metadata có thật, không chỉ trên string tên class, đường dẫn dự đoán hay cấu hình Maven/Gradle.

## 2. Bốn API lấy metadata class quan trọng nhất

| Điều cần in | API Java 17 | Cần diễn giải đúng |
| --- | --- | --- |
| Tên runtime class | `type.getName()` | Binary name cho class thông thường; array/primitive/hidden class có quy tắc tên riêng |
| Defining loader | `type.getClassLoader()` | `null` thường chỉ bootstrap loader, và luôn `null` cho primitive/void types |
| Module | `type.getModule()`; `module.getName()` | `null` từ `getName()` là unnamed module, không phải không có Module object |
| Nguồn mã | `type.getProtectionDomain().getCodeSource().getLocation()` | Có thể không có `CodeSource` hoặc `location`; URL không phải bằng chứng tuyệt đối về nội dung bytes |

Các thông tin bổ sung thường hữu ích:

- `type.getPackageName()`: tên package theo Java runtime type; **cùng package name không nhất thiết cùng runtime package** nếu defining loaders khác nhau.
- `type.getClassLoader() == expectedLoader`: kiểm tra identity bằng object reference khi điều tra.
- `loader.getClass().getName()`: implementation class của loader, chẳng hạn built-in/custom loader.
- `loader.getName()` (Java 9+): tên mô tả loader nếu nó được đặt; có thể `null`.
- `System.identityHashCode(loader)`: định danh tham chiếu hỗ trợ phân biệt hai instances trong **một JVM đang chạy**, không phải ID ổn định giữa những lần khởi động.
- `module.getDescriptor()` hoặc `module.getLayer()`: khi cần truy vết named module/JPMS layers.
- `StackTraceElement.getClassLoaderName()`, `getModuleName()`, `getModuleVersion()`: metadata của frame (có thể `null`), nhưng không tự cung cấp `Class<?>` hay code source.

**Tránh chỉ log `loader.toString()`.** Nhiều loaders có `toString` hữu ích, nhưng đây không phải contract đảm bảo có URL/source/version. Với custom loader, `toString()` thậm chí có thể quá dài hoặc chứa thông tin nội bộ không nên đưa lên log công khai.

## 3. `Class.getName()`: tên lớp nào cần in?

`Class.getName()` khác với tên file và một số tên hiển thị:

| API/định dạng | Ví dụ | Khi nào dùng |
| --- | --- | --- |
| `type.getName()` | `com.example.MyService` | Log chính xác runtime type thông thường |
| `type.getSimpleName()` | `MyService` | Dễ đọc, nhưng thiếu package và có thể mơ hồ |
| `type.getCanonicalName()` | `com.example.Outer.Inner` | Human-facing code name; có thể `null` cho local/anonymous/hidden |
| Binary name nested class | `com.example.Outer$Inner` | `Class.forName` và JVM lookup |
| Relative class-file path | `com/example/MyService.class` | Kiểm tra JAR entries/classpath |
| Descriptor | `Lcom/example/MyService;` | Bytecode/JVMS reference |
| Array class `getName()` | `[Ljava.lang.String;` | Không phải tên source-style `String[]` |

Đối với error context, ưu tiên **`type.getName()`** vì nó không làm mất package/nested-class identifier. Nếu class chưa nạp thành công, chưa có `Class<?>` để gọi method; hãy log **binary name đã yêu cầu** thay vì tạo một giá trị class giả.

**Ví dụ thiếu class**:

```java
String requested = "com.example.Missing";
try {
    Class<?> found = lookupLoader.loadClass(requested);
    // Có Class<?> mới đọc được defining loader/module/code source.
} catch (ClassNotFoundException error) {
    // Log requested và chính lookupLoader;
    // không tự khẳng định một defining loader không tồn tại.
}
```

Đây là **snippet**, cần biến `lookupLoader` là `ClassLoader` và method có xử lý exceptions.

## 4. Defining loader khác lookup loader và context loader

Một cuộc gọi:

```java
Class<?> type = child.loadClass("api.Shared");
```

không bảo đảm `type.getClassLoader() == child`. Với parent-first, `child` có thể ủy quyền parent và nhận runtime class do parent định nghĩa.

Ba vai trò:

1. **Requested/lookup loader:** object mà code gọi `loadClass` hoặc truyền vào `Class.forName(name, ..., loader)`.
2. **Defining loader:** `type.getClassLoader()` của runtime class thực tế, có thể là parent hoặc ancestor.
3. **Thread context class loader (TCCL):** `Thread.currentThread().getContextClassLoader()`; thường ảnh hưởng framework/SPI discovery (`ServiceLoader.load(service)`), không mặc định đồng nhất với defining loader.

```text
thread TCCL = plugin-B
         │
         └── ServiceLoader chọn service provider resources

requestedLoader = child-B
         │
         └── child-B.loadClass("api.Contract")
                 │
                 └── parent app defines api.Contract

type.getClassLoader() == app
```

Khi log `ClassNotFoundException`, ghi lookup loader và TCCL nếu có ý nghĩa; khi log `ClassCastException` hoặc `LinkageError`, ghi **defining loaders của cả hai runtime types** nếu caller đang so sánh chúng.

**Không nhầm `loader.getParent()` với `type.getClassLoader()`**: parent là quan hệ object giữa loaders; defining loader cho biết ai đã định nghĩa class cụ thể.

## 5. `getClassLoader() == null` không tự là lỗi

Trong nhiều JVM implementations, một class do bootstrap loader định nghĩa có:

```java
ClassLoader loader = String.class.getClassLoader();
System.out.println(loader == null);
```

Đây là snippet runnable nếu đặt trong một method; kết quả trên JDK 17 thông dụng là `true`. `null` ở đây là cách API đại diện bootstrap loader **không có object Java public để trả về**, không phải bug hoặc class chưa nạp.

Với `int.class` hoặc `void.class`, `getClassLoader()` cũng trả `null`; phân biệt bằng `type.isPrimitive()`. Array classes không có class-file định nghĩa bằng `defineClass` như class thường; `getClassLoader()` của array class phản ánh loader của element type hoặc `null` cho primitive components.

Gợi ý formatter:

```java
static String loaderLabel(Class<?> type) {
    ClassLoader loader = type.getClassLoader();
    if (type.isPrimitive()) {
        return "<primitive>";
    }
    if (loader == null) {
        return "<bootstrap>";
    }
    String name = loader.getName();
    return name == null
            ? loader.getClass().getName()
            : name + " (" + loader.getClass().getName() + ")";
}
```

Đây là method minh họa; không tự chạy nếu chưa nằm trong một class có caller. Trong logger production, cân nhắc in thêm **identity hash** của loader instance vì hai loaders cùng tên/cùng Java implementation class vẫn có thể định nghĩa hai class khác nhau.

## 6. Module: named hay unnamed, và tại sao `getName()` có thể null?

`Class.getModule()` trả đối tượng `Module` tương ứng với class; với classes trên classpath hoặc classes do `URLClassLoader` tạo như classpath-style, module thường là **unnamed module** của defining loader.

```java
Module module = type.getModule();
String moduleName = module.isNamed()
        ? module.getName()
        : "<unnamed>";
```

Đây là **snippet**, cần biến `type` kiểu `Class<?>`.

Ví dụ trên Java 17:

- `String.class.getModule().getName()`: `"java.base"`.
- `MyClasspathClass.class.getModule().isNamed()`: `false` nếu class chạy trên application classpath.
- Một class thuộc named module `org.example.plugin` trả tên module ấy, có thể có module version trong descriptor.
- Với named module layer tự xây, cùng module name ở hai layers **không tự bảo đảm cùng `Class<?>` identity**; cần xem `Module` object, layer và loader phù hợp.

**Không suy luận `module.getName() == null` là “module lookup thất bại”**. Đó là tên của unnamed module, một khái niệm bình thường trong JPMS.

Với `ClassCastException` hoặc `IllegalAccessError`, module metadata giúp xem nhanh liệu vấn đề là duplicate types hay module access (`requires`/`exports`/`opens`). Nhưng chỉ in module name không thay thế phân tích runtime type identity.

## 7. Nguồn mã: `ProtectionDomain → CodeSource → URL`

API chuẩn:

```java
ProtectionDomain domain = type.getProtectionDomain();
CodeSource codeSource =
        domain == null ? null : domain.getCodeSource();
URL location = codeSource == null
        ? null : codeSource.getLocation();
```

Đây là **snippet**, cần import `java.security.ProtectionDomain`, `java.security.CodeSource`, `java.net.URL` và biến `type`.

Ý nghĩa:

- `ProtectionDomain` gắn metadata về domain của runtime class.
- `CodeSource` có thể mô tả **URL nguồn và signer certificates** liên quan.
- `CodeSource.getLocation()` là URL, thường là **`file:/.../app.jar`** hoặc **`file:/.../classes/`** cho classpath classes.
- `null` là giá trị **hợp lệ** nếu không có CodeSource hoặc location; nhiều platform/JDK classes không có source URL kiểu JAR/đường dẫn filesystem.
- `Class.getProtectionDomain()` có thể ném `SecurityException` trên runtime có security checks phù hợp (đặc biệt với mô hình cũ); logger nên xử lý theo chính sách fail-safe.

**Đừng gọi `type.getProtectionDomain().getCodeSource().getLocation().toString()` không kiểm tra null**. Một `NullPointerException` phát sinh từ logger sẽ che lỗi gốc đang điều tra.

**CodeSource location không phải một bằng chứng mật mã tuyệt đối.** URL có thể là vị trí JAR/directory đã dùng khi định nghĩa class, nhưng không chứng minh bytes hiện tại trên đĩa là bytes đã được load, không chứng minh artifact chưa bị thay đổi, và không nói class đang có đúng build version nếu không kết hợp hashes/manifest/versioning.

## 8. CodeSource khác class resource URL và JAR manifest

Một số lập trình viên thử:

```java
URL location = type.getResource(
        type.getSimpleName() + ".class");
```

Đây là snippet có thể hữu ích để **tìm resource tương ứng tên class** trong một số trường hợp, nhưng **không tương đương `ProtectionDomain.CodeSource`**:

- `Class.getResource` phụ thuộc loader/module resource lookup, accessibility và resource-name rules.
- `getResource(...)` có thể trả URL `jrt:/...` cho class thuộc JDK runtime image; đó là resource URL, không nhất thiết `CodeSource.getLocation()`.
- Resource có thể không tìm được, bị module encapsulation che hoặc không phải bytes dùng cho runtime definition.
- Đối với dynamically generated class/hidden class, có thể **không tồn tại file `.class` truy cập bằng URL**.
- Một custom loader có thể define từ mảng byte trong memory, database hoặc network mà không đặt CodeSource; `location == null` là điều hoàn toàn hợp lệ.
- Resource URL và CodeSource URL có thể có độ chi tiết khác nhau: một trỏ đúng `some/Type.class`, một trỏ **JAR/directory gốc**.

Nếu cần xác định class có thật trong JAR nào, **ưu tiên CodeSource location nếu có** và đối chiếu với class-loading logs/artifact inventory. Nếu cần chứng minh bytecode từ artifact nào, thiết kế loader có thể log **định danh build hoặc SHA-256 digest của artifact đáng tin đã xác minh** — không chỉ tên file.

## 9. Thực hành A — in đủ class name, loader, module và CodeSource

Ví dụ đầu tiên là chương trình **hoàn chỉnh Java 17+** trên application classpath. Chúng ta in metadata của chính class demo và `java.lang.String`.

Cấu trúc:

```text
diagnostics-lab/
└── src/demo/DiagnosticDemo.java
```

Tệp **`src/demo/DiagnosticDemo.java`**:

```java
package demo;

import java.net.URL;
import java.security.CodeSource;
import java.security.ProtectionDomain;

public final class DiagnosticDemo {
    private static String loaderOf(Class<?> type) {
        ClassLoader loader = type.getClassLoader();

        if (loader == null) {
            return type.isPrimitive() ? "<primitive>" : "<bootstrap>";
        }
        if (loader == DiagnosticDemo.class.getClassLoader()) {
            return "application";
        }
        return loader.getName() == null
                ? loader.getClass().getName() : loader.getName();
    }

    private static String moduleOf(Class<?> type) {
        Module module = type.getModule();
        return module.isNamed() ? module.getName() : "<unnamed>";
    }

    private static String sourceSchemeOf(Class<?> type) {
        try {
            ProtectionDomain domain = type.getProtectionDomain();
            CodeSource source =
                    domain == null ? null : domain.getCodeSource();
            URL location =
                    source == null ? null : source.getLocation();
            return location == null
                    ? "<unavailable>" : location.getProtocol();
        } catch (SecurityException denied) {
            return "<denied>";
        }
    }

    private static void describe(Class<?> type) {
        System.out.println("class=" + type.getName());
        System.out.println("loader=" + loaderOf(type));
        System.out.println("module=" + moduleOf(type));
        System.out.println("code-source scheme=" +
                sourceSchemeOf(type));
    }

    public static void main(String[] args) {
        describe(DiagnosticDemo.class);
        describe(String.class);
    }
}
```

Biên dịch và chạy trong `diagnostics-lab`:

```sh
javac --release 17 -d out src/demo/DiagnosticDemo.java
java -cp out demo.DiagnosticDemo
```

**Stdout dự kiến trên OpenJDK/HotSpot Java 17 trong cấu hình classpath này:**

```text
class=demo.DiagnosticDemo
loader=application
module=<unnamed>
code-source scheme=file
class=java.lang.String
loader=<bootstrap>
module=java.base
code-source scheme=<unavailable>
```

Chúng ta cố ý chỉ in **URL scheme** thay vì full filesystem URL để stdout không phụ thuộc thư mục đặt project và không rò đường dẫn người dùng.

### Giải thích

- `DiagnosticDemo.class` được application loader định nghĩa từ thư mục `out` trên classpath; nó thuộc unnamed module. CodeSource thường chứa một `file:` URL của thư mục `out`.
- `String.class` được bootstrap định nghĩa trên JDK 17 thông dụng và thuộc named module `java.base`. CodeSource location thường không được cung cấp ở metadata này; **không viết code bắt buộc nó phải tồn tại**.
- `loader=application` là nhãn do **chính ví dụ quy ước** bằng cách so object với loader của `DiagnosticDemo`, không phải cam kết rằng Java luôn đặt tên loader là chữ `application`.
- Nếu chạy dưới custom launcher/security configuration, labels hoặc khả năng truy cập CodeSource có thể khác; demo vẫn xử lý `null` và `SecurityException`.
- Trong log thật, có thể cần ghi **URL đầy đủ** theo policy nội bộ để xác định artifact; ví dụ chỉ in scheme để giữ expected stdout ổn định.

**Điểm phân biệt:** `Class.getProtectionDomain()` đọc metadata, không chạy constructor hay static initializer của target. Việc có `Class<?>` cũng không có nghĩa object của class đã được tạo.

## 10. Ghi full CodeSource URL nhưng phải kiểm soát bảo mật log

Một helper phù hợp cho logging:

```java
static String codeSourceUrl(Class<?> type) {
    try {
        var domain = type.getProtectionDomain();
        if (domain == null || domain.getCodeSource() == null) {
            return "<unknown>";
        }
        var url = domain.getCodeSource().getLocation();
        return url == null ? "<unknown>" : url.toExternalForm();
    } catch (SecurityException denied) {
        return "<access-denied>";
    }
}
```

Đây là **method minh họa**, cần nằm trong class, không phải chương trình độc lập. Nó giữ đầy đủ URL khi được phép, nhưng **không đảm bảo URL thích hợp để xuất ra log công khai**.

Một số URL có thể chứa:

- username hoặc thông tin đường dẫn home directory;
- cấu trúc thư mục triển khai nội bộ;
- tên khách hàng/tenant hoặc môi trường riêng;
- query/fragment có token trong những custom URL schemes;
- network host và endpoint nội bộ.

**Quy tắc tốt hơn:** logger nội bộ có thể giữ canonical artifact ID/version/digest, còn public-facing error chỉ dùng mã lỗi/correlation ID. Nếu buộc log URL, hãy chuẩn hóa/sanitize và redact thông tin nhạy cảm theo policy của hệ thống. Tránh dùng URL đến endpoint không tin cậy như một nơi tự động đọc/download artifact chỉ để chẩn đoán.

### “Nguồn mã” không phải lúc nào cũng là một file

Class có thể đến từ:

- một **JAR** trên classpath/URLClassLoader;
- một **directory** chứa class files;
- **JDK runtime image** (`jrt:`), với CodeSource có thể unavailable;
- một **custom ClassLoader** sinh bytecode trong bộ nhớ;
- một **module layer** không ánh xạ đơn giản về URL filesystem;
- bytecode instrumentation hoặc runtime enhancement.

Vậy nên `CodeSource == null` nên được log là **`<unknown>`** hoặc **`<unavailable>`**, không phải tự kết luận “đó chắc chắn là class độc hại/không có JAR”.

## 11. In loader theo identity, không chỉ tên

Hai `URLClassLoader` instances có thể cùng class implementation, cùng URLs và thậm chí cùng tên, nhưng vẫn là **hai defining loaders khác nhau**.

Một nhãn hữu ích cho session:

```java
static String loaderDetail(ClassLoader loader) {
    if (loader == null) {
        return "<bootstrap>";
    }
    String name = loader.getName();
    return loader.getClass().getName()
            + "[name=" + (name == null ? "<unnamed>" : name)
            + ", id=0x"
            + Integer.toHexString(System.identityHashCode(loader))
            + "]";
}
```

Đây là helper minh họa; nên cẩn thận với việc tên loader tự cấu hình có thể chứa thông tin đầu vào không tin cậy.

**Vì sao identity hash chứ không chỉ `getName()`?**

- `getName()` có thể null; custom loaders có thể có nhãn trùng.
- `loader.getClass().getName()` thường giống nhau cho mọi instances của cùng subclass.
- `System.identityHashCode(loader)` giúp phân biệt objects trong **một lần chạy** dù `equals` bị override.
- Nhưng identity hash chỉ là số hash 32-bit: **có thể collision**, không phải globally unique ID, không dùng làm authentication token, không nhất quán sau restart.

Đối với hệ plugin sản xuất, tốt hơn là chủ động gán **pluginId + generation/version UUID** tại nơi tạo loader và log cùng identity hash như dữ liệu chẩn đoán phụ trợ.

## 12. Thực hành B — hai URLClassLoader định nghĩa cùng tên nhưng khác runtime type

Ví dụ này cho thấy tại sao không đủ chỉ log class name. Ta compile một class `plugin.Widget`, đặt bytes ở thư mục riêng, sau đó tạo hai **named URLClassLoader instances** dùng chung URL, chung parent nhưng độc lập class identity.

Cấu trúc:

```text
duplicate-loader-lab/
├── src/plugin/plugin/Widget.java
├── src/host/demo/DuplicateLoaderDemo.java
├── plugin-out/
└── host-out/
```

**`src/plugin/plugin/Widget.java`:**

```java
package plugin;

public final class Widget {
    public Widget() {
    }

    public String label() {
        return "plugin widget";
    }
}
```

**`src/host/demo/DuplicateLoaderDemo.java`:**

```java
package demo;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class DuplicateLoaderDemo {
    public static void main(String[] args) throws Exception {
        URL pluginRoot = Path.of("plugin-out")
                .toAbsolutePath().toUri().toURL();
        URL[] urls = { pluginRoot };
        ClassLoader platform = ClassLoader.getPlatformClassLoader();

        try (URLClassLoader a =
                     new URLClassLoader("plugin-A", urls, platform);
             URLClassLoader b =
                     new URLClassLoader("plugin-B", urls, platform)) {

            Class<?> left = a.loadClass("plugin.Widget");
            Class<?> right = b.loadClass("plugin.Widget");
            Object rightObject =
                    right.getDeclaredConstructor().newInstance();

            System.out.println("same name=" +
                    left.getName().equals(right.getName()));
            System.out.println("same runtime Class=" + (left == right));
            System.out.println("left loader name=" +
                    left.getClassLoader().getName());
            System.out.println("right loader name=" +
                    right.getClassLoader().getName());
            System.out.println("left module named=" +
                    left.getModule().isNamed());
            System.out.println("left source scheme=" +
                    left.getProtectionDomain()
                        .getCodeSource()
                        .getLocation()
                        .getProtocol());

            try {
                left.cast(rightObject);
                System.out.println("unexpected cast success");
            } catch (ClassCastException mismatch) {
                System.out.println("cast error=" +
                        mismatch.getClass().getSimpleName());
            }
        }
    }
}
```

**Biên dịch** từ `duplicate-loader-lab` bằng JDK 17+:

```sh
javac --release 17 -d plugin-out src/plugin/plugin/Widget.java
javac --release 17 -d host-out src/host/demo/DuplicateLoaderDemo.java
```

**Chạy** (chú ý: chỉ `host-out` trên app classpath):

```sh
java -cp host-out demo.DuplicateLoaderDemo
```

**Stdout trên OpenJDK/HotSpot Java 17 với URL thư mục như trên:**

```text
same name=true
same runtime Class=false
left loader name=plugin-A
right loader name=plugin-B
left module named=false
left source scheme=file
cast error=ClassCastException
```

**Phân tích:**

1. Cả hai loaders được cấp **cùng `plugin-out` URL**, nhưng mỗi instance tự định nghĩa `plugin.Widget`.
2. `left.getName().equals(right.getName())` trả true: binary names giống nhau.
3. `left == right` trả false: defining loaders là hai object khác nhau.
4. `getName()` của named `URLClassLoader` được đặt từ constructor Java 9+, giúp phân biệt `plugin-A`/`plugin-B`.
5. Hai class thuộc unnamed module **riêng theo defining loader**. `isNamed()` trả false cho mỗi bên.
6. `CodeSource` của class do URLClassLoader lấy từ directory `plugin-out` thường có URL scheme `file`.
7. `Class.cast` kiểm tra runtime assignability, nên object được tạo từ `right` không phải instance của runtime type `left`; `ClassCastException` là đúng dù cả hai có binary name giống nhau.

**Lưu ý API:** demo trực tiếp đọc `getCodeSource().getLocation()` để rút gọn vì nguồn là `URLClassLoader` từ `file:` URL có kiểm soát. Trong mã logging tổng quát, **phải dùng helper null-safe** như phần 7–10, vì nhiều classes hoàn toàn hợp lệ không có CodeSource.

Không thêm `plugin-out` vào `-cp` của host nếu muốn quan sát hai defining loaders riêng. Nếu parent application loader đã định nghĩa `plugin.Widget` và parent-first trả về, hai children có thể cùng dùng bản parent khiến kết quả đổi.

## 13. `ClassCastException`: cần log cả hai phía

Một thông điệp kiểu:

```text
ClassCastException: plugin.Widget cannot be cast to plugin.Widget
```

thoạt nhìn nghịch lý nhưng có thể xuất phát từ **hai `Class<?>` khác identity**. Tại runtime, nên ghi:

- `expectedType.getName()`, defining loader, module và CodeSource của type mà host kỳ vọng;
- `actualObject.getClass().getName()`, defining loader, module và CodeSource của object thực;
- class loader dùng để **nạp provider/plugin**, TCCL nếu framework dùng nó;
- artifact ID/version của cả hai;
- toàn bộ stacktrace/cause, nhưng không đưa đường dẫn nhạy cảm vào client response.

Pseudocode:

```java
Class<?> actual = value.getClass();
Class<?> expected = expectedApiClass;

System.err.println("expected=" + expected.getName());
System.err.println("actual=" + actual.getName());
System.err.println("same Class=" + (actual == expected));
System.err.println("assignable=" +
        expected.isAssignableFrom(actual));
// Log thêm loaderDetail và codeSourceUrl cho cả hai.
```

Đây là **snippet** cần biến `value` và `expectedApiClass`. `isAssignableFrom` tốt hơn chỉ so tên, nhất là với interfaces. Đối với một implementation hợp lệ, `actual == expected` thường false (implementation khác interface), nhưng `expected.isAssignableFrom(actual)` phải true.

**Đừng chỉ in `actual.getClassLoader()` rồi kết luận đủ.** Một cast thất bại có ít nhất hai types liên quan: expected và actual. Cần thông tin của **cả hai**.

## 14. `ClassNotFoundException`: class chưa tồn tại nên không thể in defining loader

Khi `ClassLoader.loadClass("plugins.Missing")` ném `ClassNotFoundException`, không có `Class<?>` kết quả để gọi `getModule()` hoặc `getProtectionDomain()`.

Thay vào đó, ghi:

```text
phase=LOAD_CLASS
requested=plugins.Missing
lookupLoader=plugin-loader-7
threadContextLoader=...
parentChain=...
artifactCandidates=...
error=ClassNotFoundException
cause=...
```

Đây là **schema gợi ý**, không phải stdout đã chạy.

Các câu hỏi:

1. `requested` có phải **binary name** đúng không? Với nested class dùng `Outer$Inner`, không dùng `Outer.Inner` trong `loadClass`.
2. Loader được truyền vào `Class.forName` có đúng không?
3. Nếu framework dùng `ServiceLoader`, TCCL có trỏ loader khám phá provider đúng không?
4. URL roots/JAR entries thực sự có `plugins/Missing.class` không?
5. Có package/module encapsulation hoặc loader policy ngăn lookup không?
6. Lỗi có phải thiếu **dependency gián tiếp** dẫn tới `NoClassDefFoundError` thay vì trực tiếp missing requested class?

**Không tự phát lệnh `Class.forName` để “lấy thêm metadata” cho mọi tên không tìm được**, vì có thể gây loading/initialization side effects, làm thay đổi trạng thái chẩn đoán hoặc lặp lại lỗi.

## 15. Thực hành C — báo requested class khi lookup fail, và metadata khi initialization fail

Cấu trúc:

```text
error-context-lab/
└── src/demo/ErrorContextDemo.java
```

**`src/demo/ErrorContextDemo.java`:**

```java
package demo;

import java.net.URL;
import java.security.CodeSource;
import java.security.ProtectionDomain;

public final class ErrorContextDemo {
    static final class Broken {
        static int value = initialize();

        private static int initialize() {
            throw new IllegalStateException("bad configuration");
        }
    }

    private static String codeSourceScheme(Class<?> type) {
        ProtectionDomain domain = type.getProtectionDomain();
        CodeSource codeSource =
                domain == null ? null : domain.getCodeSource();
        URL location = codeSource == null
                ? null : codeSource.getLocation();
        return location == null
                ? "<unavailable>" : location.getProtocol();
    }

    public static void main(String[] args) {
        String missing = "demo.NotPresent";
        ClassLoader lookup =
                ErrorContextDemo.class.getClassLoader();

        try {
            lookup.loadClass(missing);
        } catch (ClassNotFoundException failure) {
            System.out.println("requested=" + missing);
            System.out.println("lookup was app=" +
                    (lookup == ErrorContextDemo.class.getClassLoader()));
            System.out.println("lookup error=" +
                    failure.getClass().getSimpleName());
        }

        try {
            System.out.println(Broken.value);
        } catch (ExceptionInInitializerError failure) {
            Class<?> target = Broken.class;

            System.out.println("failing type=" + target.getName());
            System.out.println("defined by app=" +
                    (target.getClassLoader() == lookup));
            System.out.println("module=" +
                    (target.getModule().isNamed()
                            ? target.getModule().getName()
                            : "<unnamed>"));
            System.out.println("source scheme=" +
                    codeSourceScheme(target));
            System.out.println("init error=" +
                    failure.getClass().getSimpleName());
            System.out.println("root cause=" +
                    failure.getCause().getClass().getSimpleName());
        }
    }
}
```

Biên dịch/chạy bằng JDK 17+ từ `error-context-lab`:

```sh
javac --release 17 -d out src/demo/ErrorContextDemo.java
java -cp out demo.ErrorContextDemo
```

**Stdout trong Java 17/HotSpot thông thường:**

```text
requested=demo.NotPresent
lookup was app=true
lookup error=ClassNotFoundException
failing type=demo.ErrorContextDemo$Broken
defined by app=true
module=<unnamed>
source scheme=file
init error=ExceptionInInitializerError
root cause=IllegalStateException
```

Giải thích:

- Ở nhánh `ClassNotFoundException`, chỉ có **binary name yêu cầu** và **lookup loader**; không hề có class result để gán nhầm module/CodeSource.
- `Broken.value` là static field **không phải compile-time constant**; việc truy cập kích hoạt initialization, `initialize()` ném `IllegalStateException`, JVM báo `ExceptionInInitializerError`.
- Trong catch, `Broken.class` cho phép lấy metadata của **class đã được định nghĩa**, dù initialization thất bại. Class có thể ở trạng thái **erroneous**, nhưng metadata `Class<?>` vẫn có ý nghĩa.
- Runtime class `demo.ErrorContextDemo$Broken` được app loader định nghĩa từ thư mục `out`, thuộc unnamed module và có CodeSource scheme `file` theo cấu hình ví dụ.
- Log **nguyên nhân gốc** quan trọng hơn chỉ in top-level `ExceptionInInitializerError`; trong hệ thống thật cần giữ cả stacktrace/cause chain.

**Đừng suy rằng mọi `NoClassDefFoundError` là thiếu file.** Một class từng initialization thất bại có thể gây `NoClassDefFoundError` cho active uses sau. Điều tra cause và **sự kiện lỗi sớm nhất**.

## 16. Logger tốt phải giữ lỗi gốc, không được ném thêm lỗi

Đừng viết:

```java
try {
    service.run();
} catch (Throwable error) {
    System.err.println("source=" +
        service.getClass()
               .getProtectionDomain()
               .getCodeSource()
               .getLocation());
    // Vô tình NuIlPointerException ở logger → che root cause.
}
```

Đây là **mẫu không an toàn**, chưa có `service` và không phải chương trình runnable. `CodeSource` có thể null. Ngoài ra bắt `Throwable` tràn lan có thể che `VirtualMachineError` hoặc các lỗi JVM không thể phục hồi.

Thay vào đó:

1. **Chỉ catch những loại lỗi thuộc phạm vi handler**, giữ nguyên failure object.
2. Nếu có class thực, lấy metadata theo helper **null-safe**; nếu không có, log lookup context.
3. **Không gọi class constructor/initializer để lấy metadata**; thao tác chẩn đoán phải hạn chế side effects.
4. **Gắn throwable vào logger**: `logger.log(Level.SEVERE, "message", failure)` để giữ stacktrace/cause.
5. Metadata failures (ví dụ `SecurityException`) chỉ nên biến thành sentinel `<denied>` hoặc ghi chú phụ, không thay thế error chính.
6. Hạn chế kích thước log và sanitize strings chứa nguồn không tin cậy.

Ví dụ logging chính thống:

```java
private static final java.util.logging.Logger LOG =
        java.util.logging.Logger.getLogger("plugin.diagnostics");

static void reportFailure(
        String phase, String requested, ClassLoader lookup,
        Class<?> resolved, Throwable failure) {

    String type = resolved == null
            ? "<not-resolved>" : resolved.getName();

    LOG.log(java.util.logging.Level.SEVERE,
            "phase=" + phase
            + ", requested=" + requested
            + ", resolved=" + type
            + ", lookupLoader=" + String.valueOf(lookup),
            failure);
}
```

Đây là **helper minh họa**, chưa phải lớp chạy độc lập; triển khai thật thêm defining loader/module/code source từ `resolved` một cách null-safe. Nếu `resolved == null`, không giả metadata.

**Cẩn trọng:** `String.valueOf(lookup)` có thể gọi custom `toString()`. Khi xử lý logger security-sensitive, dùng định danh loader được quản lý riêng thay vì thực thi logic tùy ý trong `toString()`.

## 17. Những thông tin nên ghi vào một bản ghi lỗi class loading

Một bản ghi structured log có thể dùng các trường:

| Field | Ý nghĩa | Khi không có |
| --- | --- | --- |
| `event` | `CLASS_LOAD_FAILURE`, `LINKAGE_FAILURE`, `PROVIDER_FAILURE` | Bắt buộc có |
| `phase` | `LOOKUP`, `DEFINE`, `LINK`, `INITIALIZE`, `INVOKE` | Có thể `UNKNOWN` nếu caller không biết |
| `requested_class` | Binary name mà code đang yêu cầu | `<not-applicable>` |
| `resolved_class` | `Class.getName()` khi có `Class<?>` | `null`/omitted |
| `defining_loader_name` | `loader.getName()` hoặc label do framework cấp | `<unnamed>/<bootstrap>` |
| `defining_loader_type` | Java class name của loader | `<bootstrap>` |
| `defining_loader_instance` | Scoped ID/plugin generation/identity hash | `<unknown>` |
| `module_name` | Named module hoặc `<unnamed>` | `<not-resolved>` |
| `module_layer` | Named module layer khi hữu ích | `<none>`/omitted |
| `code_source` | URL/code artifact ID nếu có và được phép log | `<unavailable>/<denied>` |
| `lookup_loader` | Loader object ban đầu được hỏi | `<bootstrap>/<unknown>` |
| `tccl` | Thread context loader | Có thể `null` |
| `expected_artifact` | Version/SHA của plugin mong muốn | Omit nếu chưa biết |
| `actual_artifact` | Artifact từ CodeSource/loader mapping | `<unknown>` |
| `error_type` | `failure.getClass().getName()` | Bắt buộc có |
| `message` | Thông điệp lỗi đã được sanitize | Có thể trống |
| `cause_chain` | Causes, suppressed errors theo giới hạn | Có thể thiếu |
| `stacktrace` | Stacktrace được giữ trong logging backend | Có thể bị chính sách cắt |
| `correlation_id` | Nối request, job, plugin generation | Không tự bịa nếu chưa có |

Đây là **schema gợi ý**, không cần mọi hệ thống in đủ trường trên mỗi request. Mục tiêu là đủ thông tin để trả lời **“đã yêu cầu lớp nào, lớp thực tế do đâu định nghĩa, thuộc module nào và bytes có thể đến từ đâu?”**.

Với `ClassCastException`, cần **hai bộ metadata** cho expected/actual types. Với `ClassNotFoundException`, `resolved_class` không có. Với `ServiceConfigurationError`, xem cả service API identity và provider implementation được discovery từ loader/TCCL nào.

## 18. Stacktrace Java 9+ có module/loader, nhưng chưa đủ CodeSource

Java 9 bổ sung các trường trong `StackTraceElement`:

```java
String classLoaderName = frame.getClassLoaderName();
String moduleName = frame.getModuleName();
String moduleVersion = frame.getModuleVersion();
String className = frame.getClassName();
```

Đây là **snippet** cần `frame` kiểu `StackTraceElement`. Các trường loader/module/version có thể null nếu JVM không có metadata tương ứng; `getClassName()` là tên lớp theo frame chứ không phải object `Class<?>`.

Một stack trace có thể hiển thị prefix module/loader:

```text
at java.base/java.lang.Thread.run(Thread.java:...)
at plugin-A//plugin.Widget.run(Widget.java:...)
```

Đây là **ví dụ format minh họa**, không phải output cụ thể của chương trình ở phần 12. Stacktrace formatting có thể phụ thuộc runtime/module/loader names; đừng parse text này như giao thức ổn định.

Những giới hạn:

- Tên loader trong frame không phải object identity đảm bảo duy nhất.
- `StackTraceElement` **không có `getCodeSource()`**.
- Một frame cho biết nơi exception stack đi qua, không tự cho biết **expected runtime class** trong `ClassCastException`.
- Một class có thể đã unloaded hoặc không thể lookup lại từ current TCCL; không mặc định `Class.forName(frame.getClassName())` sẽ nạp đúng class gốc.
- Named module name/version trong frame có thể không đủ phân biệt hai layers hoặc artifacts.

Vì vậy hãy **giữ stacktrace**, đồng thời log `Class<?>` metadata tại những boundary có sẵn type objects.

## 19. Đừng làm logger thay đổi quá trình nạp lớp

Các hành động chẩn đoán có thể gây side effects:

- Gọi `Class.forName(name)` với overload một tham số có thể **initialize class**, chạy static blocks.
- Dùng `Class.forName(name, true, loader)` cũng yêu cầu initialization.
- Gọi `getDeclaredMethods()` hoặc thực hiện reflection sâu có thể kích hoạt thêm resolution/access checks, phát sinh lỗi khác nếu dependencies thiếu.
- In `loader.toString()` trên custom loader có thể chạy user-defined code.
- Gọi `resourceUrl.openStream()` để “xem bytes” có thể gây I/O/block, network access, permission checks.
- Scan toàn bộ `java.class.path`/`java.module.path` tại thời điểm lỗi có thể tốn thời gian hoặc lộ thông tin triển khai.
- Log full URL, environment, system properties hay command-line arguments có thể làm rò secrets.

**Chẩn đoán ít xâm lấn:** nếu đã có `Class<?> type`, lấy `getName()/getClassLoader()/getModule()/getProtectionDomain()` theo policy. Nếu class chưa tồn tại, ghi requested name + lookup loader + known artifact paths từ cấu hình mà không thử khởi tạo class mới chỉ để “xem thêm metadata”.

Khi điều tra sâu ngoài luồng request, có thể sử dụng `Class.forName(name, false, loader)` để yêu cầu lookup **không chủ động initialize target**, nhưng thao tác đó vẫn có thể **load/link thêm classes hoặc phát sinh error**. Phải thực hiện có chủ đích, không nhét vào mọi error handler.

## 20. Bảng lỗi phổ biến và metadata nên ưu tiên

| Triệu chứng | Metadata quan trọng | Giả thuyết cần kiểm tra |
| --- | --- | --- |
| `ClassNotFoundException` | Requested binary name, lookup loader, TCCL, URLs/JAR entries | Không tìm thấy class từ nguồn được phép |
| `NoClassDefFoundError` | Missing dependency name, loader, earliest cause/stacktrace | Dependency không load/link được hoặc class erroneous |
| `ClassCastException` | Expected + actual `Class<?>`, defining loaders, modules, CodeSources | Hai runtime type identities khác nhau |
| `NoSuchMethodError` | Caller and callee CodeSources, binary descriptors, loader, module | Version skew: compile against API khác runtime |
| `NoSuchFieldError` | Callee artifact/version + field descriptor | Runtime class thiếu field tương ứng |
| `LinkageError: loader constraint violation` | Types ở method descriptors, cả defining loaders | Các loader dùng definitions không tương thích |
| `IllegalAccessError` | Caller/target module, runtime package, defining loader, exports | Package-private/JPMS access không phù hợp |
| `InaccessibleObjectException` | Caller module, target module/package, opens rules | Deep reflection vào package chưa mở |
| `ServiceConfigurationError` | Service API, provider name, loader/TCCL, descriptor/JAR | Provider missing, not assignable, constructor/factory lỗi |
| `ExceptionInInitializerError` | Failing class, module, CodeSource, root cause | `<clinit>` lỗi; class đã được load nhưng không initialized |
| `ClassFormatError` | Class bytes source, classfile major/minor, generator version | Bytecode/file class sai cấu trúc |
| `UnsupportedClassVersionError` | Artifact path, `javap -verbose`, running JVM version | Classfile version quá mới/preview mismatch |

**Đừng suy từ exception message duy nhất.** `NoClassDefFoundError` không chỉ có một nguyên nhân; `IllegalAccessError` có thể liên quan đến package/module, không phải đơn thuần là `private`. Class metadata và cause chain mới giúp kiểm chứng.

## 21. CodeSource location không chứng minh checksum, version hoặc nguồn thực tế sau transform

Một lỗi thường gặp là lấy:

```java
URL origin = type.getProtectionDomain()
                 .getCodeSource().getLocation();
```

rồi kết luận “class này chắc chắn có hash X vì JAR ở path Y”. Đây **không phải phép xác minh checksum**.

Với custom loaders, bytecode có thể được transform trước khi `defineClass`; path/code source vẫn chỉ định nơi bắt đầu hoặc domain được gán. File có thể bị thay sau khi bytes đã được nạp. Multi-release JAR có thể chọn class bytes theo runtime version. Java agents có thể biến đổi bytecode lúc loading. Do đó một CodeSource URL không tự chứng minh toàn bộ bytecode đã được JVM định nghĩa.

Nếu cần **provenance mạnh**:

1. Tại deployment, ghi artifact build ID, version và digest SHA-256 từ nguồn đáng tin.
2. Nếu cần xác minh content đã load, thiết kế pipeline bytecode loader có kiểm tra digest/signature theo policy trước khi define.
3. Ghi mapping **loader generation → artifact ID/version/digest** bên ngoài class metadata, có ownership rõ.
4. Không tự tải URL tùy ý trong error handler để hash remote content; có thể gây SSRF, latency, lộ secrets hoặc đọc bytes khác bản đã chạy.
5. Với class do Java agent transform, nếu thực sự cần audit nội dung sau transform, xây cơ chế riêng ở instrumentation boundary và quản lý bảo mật của log.

**Nguồn mã trong log là chỉ dấu để khoanh vùng, không phải bằng chứng integrity đầy đủ.**

## 22. Kết hợp log metadata với JVM và artifact inspection

Khi metadata của `Class<?>` cho thấy một loader hoặc CodeSource bất ngờ, có thể chạy HotSpot với `-Xlog:class+load=info` để quan sát tên và nguồn class khi JVM load:

```bash
java -Xlog:class+load=info -cp out demo.DiagnosticDemo
```

Đây là lệnh minh họa; những dòng JVM ghi ra phụ thuộc JDK, classpath và thời điểm load. Log load không chứng minh class đã initialize, cũng không luôn cho object identity của loader. Dùng `java -Xlog:help` để kiểm tra tag. Với lỗi `NoSuchMethodError`, đối chiếu binary descriptors từ artifact runtime bằng `javap -s -p`; dùng `jar --list --file plugin.jar` để kiểm tra entry. Hai lệnh công cụ đều đọc artifact trên đĩa, không chứng minh JVM đã chọn chính artifact đó.

Các bài tiếp theo trình bày riêng cách đọc Unified Logging (`-verbose:class`, `class+load`, `class+init`), cũng như quy trình `javap`/`jar`/`jdeps`. Trọng tâm ở đây là **nối kết quả chẩn đoán ngoại tuyến với đúng runtime class/loader đã log**, giữ nguyên throwable/cause ban đầu.
## 23. Class loader + module access: đọc hai phía lỗi

Với `IllegalAccessError` hoặc lỗi JPMS reflection, log cả:

- **caller class**: `Class<?>` đại diện code gọi, loader/module/package;
- **target class**: loader/module/package/code source;
- **member**: method/field name và descriptor nếu có;
- **module rules**: caller module có đọc target module không, target package có exports/opens phù hợp không;
- **runtime package**: hai classes có cùng package name *và* defining loader hay không.

Với named modules, `module.isNamed()` và `module.getName()` giúp biết tên, nhưng **module name không bằng module object identity**. Khi có nhiều `ModuleLayer`, ghi layer/loader giúp phân biệt các cấu hình trùng module name.

Ví dụ logic:

```java
Module callerModule = callerClass.getModule();
Module targetModule = targetClass.getModule();

boolean reads = callerModule.canRead(targetModule);
boolean exported = targetModule.isExported(
        targetClass.getPackageName(), callerModule);

System.err.println("reads=" + reads);
System.err.println("exported=" + exported);
```

Đây là **snippet**, cần hai biến `callerClass`/`targetClass`. `canRead`/`isExported` hỗ trợ chẩn đoán nhưng không chứng minh một reflective operation riêng chắc chắn thành công; member visibility, `opens`, lookup privileges và caller context vẫn quan trọng.

## 24. Khi lỗi xảy ra trong ServiceLoader

Với `ServiceConfigurationError`, hãy log **hai vai trò khác nhau**: service API type được consumer yêu cầu và provider implementation (nếu provider đã được resolve), cùng loader/module/CodeSource của mỗi bên. Ngoài ra, log loader dùng để khám phá providers: overload `ServiceLoader.load(service)` dùng TCCL, còn `ServiceLoader.load(service, chosenLoader)` dùng loader truyền vào.

Nếu discovery thất bại trước khi có provider `Class<?>`, chỉ ghi provider *binary name* đọc từ descriptor (nếu biết), không giả một defining loader. Phân biệt thiếu provider descriptor, provider không load được, constructor lỗi và provider không assignable vì service interface bị định nghĩa hai lần. Giữ `ServiceConfigurationError` và nguyên nhân của nó. Trong named modules, kiểm tra `uses`/`provides` và layer liên quan. Bài ServiceLoader của chương về loader ngữ cảnh giải thích chi tiết cơ chế SPI.
## 25. Mẫu structured log không làm lộ thông tin cho người dùng cuối

Một bản ghi nội bộ:

```json
{
  "event": "PLUGIN_LINKAGE_FAILURE",
  "correlationId": "req-42",
  "phase": "INVOKE",
  "requestedClass": "plugin.Widget",
  "resolvedClass": "plugin.Widget",
  "definingLoader": "plugin-A",
  "module": "<unnamed>",
  "codeSource": "<internal-artifact-id>",
  "errorType": "java.lang.ClassCastException",
  "expectedType": "api.Widget",
  "actualType": "plugin.Widget"
}
```

Đây là **JSON mẫu minh họa**, không phải output chạy từ ví dụ nào và không phải schema bắt buộc. ID/source chỉ minh họa. Error logger nội bộ cũng nên lưu throwable/stacktrace thật và plugin generation theo policy.

Thông điệp trả cho client có thể chỉ là:

```text
PLUGIN_EXECUTION_FAILED (correlationId=req-42)
```

Không tự phơi đường dẫn `file:/home/.../deployment/secrets`, absolute filesystem paths, internal hostnames, signer metadata hoặc toàn bộ stacktrace qua public API. **Thông tin nhiều cho người vận hành, tối thiểu cho caller không đáng tin** là lựa chọn tốt hơn.

Một structured log vẫn có thể gây log injection nếu các fields nhận dữ liệu không tin cậy. Log backend phải escape newline/control characters và hạn chế kích thước mỗi field.

## 26. Checklist chẩn đoán classloading trong thực tế

1. **Xác định thao tác**: `loadClass`, `Class.forName`, SPI discovery, linkage, init hay reflection/invoke?
2. **Ghi requested binary name** khi chưa có `Class<?>`. Không tự tạo “resolved class” giả.
3. **Nếu có runtime class**, ghi `getName()`, `getClassLoader()`, `getModule()` và null-safe `CodeSource.location`.
4. **Định danh loader instance** bằng tên/loại/ID cấp bởi framework, không chỉ Java class name của loader.
5. **Ghi cả expected và actual classes** cho cast/assignability failures.
6. **Ghi lookup loader và TCCL** nếu có thể ảnh hưởng delegation/discovery.
7. **Không suy CodeSource phải tồn tại**: bootstrap, generated classes, custom loaders có thể trả null.
8. **Ghi module named/unnamed rõ ràng**, và module layer nếu hệ thống dùng nhiều layers.
9. **Giữ stacktrace/cause chain** của lỗi đầu tiên; đặc biệt khi `ExceptionInInitializerError` dẫn tới `NoClassDefFoundError` về sau.
10. **Đối chiếu artifact thật**: full CodeSource trong log nội bộ được phép, build/version/digest và URL roots.
11. **Không kích hoạt initialization vô ý** chỉ để log metadata.
12. **Không gọi network/I/O không giới hạn trong error handler**, không tải class/JAR chỉ để chứng minh một giả thuyết.
13. **Tôn trọng bảo mật log**: redact secrets/path/tenant data, giữ correlation ID.
14. **Tái hiện trong đúng class loader graph**; IDE/test classpath có thể làm parent loader che plugin JAR.
15. **Kiểm tra lỗi sau khi sửa**: có thể hết `ClassNotFoundException` nhưng lộ thêm `NoSuchMethodError` do dependency version.
16. **Ghi rõ giới hạn** của logging: CodeSource không chứng minh integrity, loader name không định danh duy nhất, module name không quyết định toàn bộ access.

## 27. Các lỗi giải thích phổ biến cần tránh

- **“`Class.getName()` giống nhau thì là cùng runtime type.”** Sai nếu defining loaders khác nhau.
- **“`child.loadClass` trả class thì class đó do child định nghĩa.”** Sai; parent-first có thể trả class của parent.
- **“`getClassLoader() == null` nghĩa là class bị lỗi.”** Sai; thường là bootstrap hoặc primitive.
- **“`getModule().getName() == null` nghĩa là không có module.”** Sai; unnamed module hợp lệ.
- **“Mọi `Class<?>` đều có CodeSource URL.”** Sai; `CodeSource` hoặc location có thể null.
- **“CodeSource file path hiện tại chứng minh bytes đã được JVM nạp.”** Sai; file có thể thay đổi hoặc bytes bị transform.
- **“`Class.getResource` giống `CodeSource.getLocation`.”** Sai; class resource và artifact provenance có semantics khác.
- **“`ClassNotFoundException` luôn có `Class<?>` để in loader/module.”** Không; phải log requested name và lookup context.
- **“Một dòng exception message đủ tìm đúng JAR.”** Không trong plugin/module loader graphs.
- **“`ClassLoader.getName()` là globally unique.”** Không; có thể null/trùng, nên thêm generation/instance ID.
- **“`StackTraceElement.getModuleName()` cung cấp code source.”** Không; không có `getCodeSource` trên stack frame.
- **“Log toàn bộ absolute paths/URLs vào client response là an toàn.”** Không; có thể lộ nội bộ/secrets.
- **“Gọi `Class.forName(name)` chỉ để quan sát metadata không có side effects.”** Sai; overload mặc định có thể initialize class.
- **“Catch `Throwable` rồi chạy reflective probes sâu sẽ luôn làm log tốt hơn.”** Sai; có thể che root cause, tạo lỗi mới hoặc block.
- **“`javap` chứng minh runtime đã chọn artifact đó.”** Sai; đó là công cụ đọc bytecode offline.
- **“Thêm `-Xlog:class+load` nghĩa là mọi class đã initialize.”** Sai; loading và initialization khác nhau.
- **“Module name cùng nhau nghĩa là loader identity cùng nhau.”** Không; cần module object, layer và defining loader.

## 28. Câu hỏi tự kiểm tra

**1. Bốn thông tin runtime nên có khi log một `Class<?>` là gì?** Tên lớp, defining loader, module và CodeSource location nếu được cung cấp.

**2. `Class.getClassLoader() == null` có thể là gì?** Bootstrap loader representation hoặc primitive/void type.

**3. `module.getName() == null` nghĩa là gì?** Unnamed module, không phải class không thuộc module.

**4. Vì sao `child.loadClass("api.Contract")` chưa chứng minh child define class?** Parent-first có thể trả class của parent, cần kiểm tra `type.getClassLoader()`.

**5. `CodeSource.getLocation()` có thể null không?** Có; cần null-safe checks.

**6. Tại sao không in `ClassNotFoundException` cùng defining loader?** Lookup thất bại nên chưa có resolved `Class<?>`; chỉ log requested name và lookup loader.

**7. Vì sao `ClassCastException` cần metadata của expected lẫn actual types?** Hai types có thể trùng binary name nhưng khác defining loader, khiến `isAssignableFrom` false.

**8. `ClassLoader.getName()` có đảm bảo định danh riêng cho hai loader instances không?** Không. Có thể null hoặc trùng; dùng thêm runtime-scoped identity/generation.

**9. CodeSource URL khác class resource URL ở đâu?** CodeSource thường mô tả nguồn/domain cấp JAR/directory; resource có thể trỏ từng `.class` và được lookup theo module/loader rules.

**10. Nếu JDK class có `CodeSource == null`, kết luận nó thiếu JAR được không?** Không; đây có thể là tình huống bình thường trong runtime image.

**11. Có nên dùng `Class.forName(name)` trong exception logger để lấy metadata không?** Không mặc định; nó có thể kích hoạt class initialization.

**12. Khi `NoSuchMethodError`, ngoài loader và CodeSource cần gì?** So compiler/runtime method descriptors (`javap -s`), versions, dependencies và callsite.

**13. Với named modules, module name có đủ khẳng định access hợp lệ không?** Không; cần xem readability, exports/opens, caller/target modules và members.

**14. `StackTraceElement` Java 9+ có những metadata loader/module nào?** `getClassLoaderName()`, `getModuleName()`, `getModuleVersion()` — chúng có thể null.

**15. Có nên tin CodeSource URL như SHA-256 của bytes JVM đã execute không?** Không; integrity cần xác minh artifact/bytes riêng.

**16. Log class metadata sao cho không lộ secrets?** Dùng artifact ID/build version trong public records, giữ full URL ở hệ thống nội bộ được kiểm soát và redact đường dẫn/token.

**17. Một class do loader custom sinh hoàn toàn trong memory có thể có CodeSource không?** Có thể có nếu domain được gán, cũng có thể không; không được giả định bắt buộc.

**18. Khi logger đọc metadata nhưng bị `SecurityException`, nên làm gì?** Giữ lỗi chính, ghi sentinel như `<denied>` và không thay thế throwable ban đầu.

## 29. Nguồn tham khảo chính thức

- [Java SE 17 — `Class` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getName`, `getClassLoader`, `getModule`, `getProtectionDomain`, `getResource`.
- [Java SE 17 — `ClassLoader` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `getName`, parent delegation, `loadClass`, `getParent`.
- [Java SE 17 — `Module` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): `isNamed`, `getName`, `getLayer`, readability/exports.
- [Java SE 17 — `ProtectionDomain` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/ProtectionDomain.html): `getCodeSource()` và metadata domain.
- [Java SE 17 — `CodeSource` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/CodeSource.html): `getLocation()`, signer information và khả năng null.
- [Java SE 17 — `StackTraceElement` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StackTraceElement.html): frame class, loader/module names và versions.
- [Java SE 17 — `URLClassLoader` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): URL roots, named loaders và class/resource loading.
- [Java Virtual Machine Specification 17, `5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): defining loaders, runtime type identity, linking/access.
- [JDK 17 `javap` tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): inspection binary names, descriptors và classfile major version.

**Kết luận:** Khi một ứng dụng Java gặp lỗi class loading/linking, **chỉ tên class không đủ**. Nếu đã có `Class<?>`, hãy log **`getName()` + `getClassLoader()` + `getModule()` + null-safe `ProtectionDomain/CodeSource`**, kết hợp lookup loader/TCCL, expected/actual types, stacktrace và artifact generation. Nếu class chưa nạp thành công, log **requested name và lookup context**, không bịa defining loader/module. Cuối cùng, luôn cân bằng chất lượng chẩn đoán với **khả năng thiếu metadata và bảo mật thông tin log**.

# Khi nào cần mở rộng ClassLoader trong Java?

**Mở rộng `java.lang.ClassLoader`** nghĩa là viết một lớp con để kiểm soát **cách JVM tìm dữ liệu class và định nghĩa runtime class**. Đây là công cụ chuyên biệt, không phải giải pháp mặc định cho mọi lỗi `ClassNotFoundException` hoặc mọi nhu cầu nạp JAR động.

**Nguyên tắc chọn giải pháp:** Hãy ưu tiên classpath/module path, `URLClassLoader`, `ServiceLoader` hoặc module layers nếu chúng đã giải quyết được vấn đề. Chỉ viết custom `ClassLoader` khi bạn thực sự cần **một nguồn class bytecode mới, namespace/isolation riêng hoặc chính sách lựa chọn/biến đổi bytecode có chủ đích** mà các công cụ sẵn có không đáp ứng.

Trong Java, danh tính runtime class được xác định bởi cặp:

```text
(binary name, defining class loader)
```

Vì vậy custom loader không chỉ là một “đường dẫn khác để tìm file”. Nó có thể làm thay đổi **định danh kiểu, khả năng ép kiểu, package-private access, static state, việc giải quyết dependency và vòng đời unload/reload**.

## 1. Trước tiên: ClassLoader mặc định làm gì?

Các JVM hiện đại có bootstrap/platform/application loaders để tìm lớp nền tảng và lớp ứng dụng. `ClassLoader` chuẩn dùng mô hình **parent delegation**:

```text
child.loadClass("plugin.Example")
         |
         v
findLoadedClass(name)
         |
         +-- đã biết class? -> trả về
         |
         v
parent.loadClass(name) (hoặc bootstrap lookup)
         |
         +-- tìm thấy? -> trả về class do parent/ancestor cung cấp
         |
         v
child.findClass(name)
         |
         +-- tìm bytecode riêng, rồi defineClass(...)
         |
         v
Class<?> kết quả
```

`loadClass(String, boolean)` mặc định thực hiện kiểm tra đã nạp, ủy quyền parent, rồi mới gọi `findClass`. Nếu tham số `resolve` là `true`, nó còn gọi `resolveClass` theo hợp đồng API. **`loadClass` không đồng nghĩa với chạy static initializer**: class có thể được load/link nhưng chỉ initialized khi thao tác của chương trình/JVM yêu cầu.

Đối với custom loader **vẫn muốn parent-first**, cách mở rộng được JavaDoc khuyến nghị là override **`findClass(String)`**, không phải ngay lập tức override `loadClass`. Nhờ đó ta giữ lại thuật toán delegation, kiểm tra class đã nạp, locking và resolution của lớp cơ sở.

Các phương thức có vai trò khác nhau:

| API | Mục đích | Thường cần override? |
|---|---|---|
| `loadClass(String)` | Điểm vào nạp lớp theo binary name | **Không** nếu chấp nhận parent-first |
| `loadClass(String, boolean)` | Điều phối cache, parent, findClass, resolve | Chỉ khi cần chính sách delegation khác và đã hiểu hệ quả |
| `findClass(String)` | Tìm/định nghĩa class **do loader này** cung cấp | **Có** với custom nguồn bytecode theo parent-first |
| `defineClass(String, byte[], int, int)` | Chuyển bytes class file hợp lệ thành runtime class | **Gọi**, không override (phương thức protected final) |
| `findLoadedClass(String)` | Truy vấn class đã gắn với initiating loader | Hữu ích nếu tự override loadClass |
| `resolveClass(Class<?>)` | Hoàn tất linking thích hợp | Gọi theo quy tắc `loadClass`; không phải initialization |
| `findResource(String)` / `findResources(String)` | Tìm resource do loader cung cấp | Khi loader cũng phục vụ resource |
| `getClassLoadingLock(String)` | Lock phối hợp nạp theo tên lớp | Cần biết khi tự thay `loadClass`/dùng parallel loading |

**Đừng gọi `defineClass` mỗi lần được yêu cầu một tên đã nạp.** Một loader không thể định nghĩa lại cùng binary name thành runtime class thứ hai của chính loader đó; cố làm vậy có thể dẫn tới `LinkageError` liên quan duplicate definition. Muốn thế hệ class mới thì phải thiết kế defining loader mới và quản lý lifetime của nó.

## 2. Khi nào thực sự nên tạo custom ClassLoader?

Một số nhu cầu chính đáng:

### A. Dữ liệu class không nằm trên URL/JAR/thư mục mà loader có sẵn hiểu được

Ví dụ một môi trường nhận **bytecode từ bộ nhớ**, một kho dữ liệu nội bộ, nội dung tạo bởi compiler trong chương trình, hoặc một định dạng lưu trữ tùy biến. Khi đã có `byte[]` của class file, custom loader có thể gọi `defineClass` để đưa class vào JVM.

`URLClassLoader` làm tốt với URLs tới directory/JAR. Nếu nguồn của bạn là `Map<String,byte[]>` hoặc bytecode được cấp qua API nội bộ, override `findClass` có thể đơn giản hơn ép dữ liệu vào file JAR trên disk.

**Bảo mật:** Việc bytecode nằm trong bộ nhớ hoặc đã mã hóa lúc lưu trữ **không biến nó thành code an toàn**. Xác minh nguồn tin cậy, tính toàn vẹn, kích thước, phụ thuộc và quyền thực thi trước khi định nghĩa. Không nên viết loader tải và chạy bytecode bất kỳ từ mạng chỉ vì có thể.

### B. Tạo namespace cho plugin hoặc phần ứng dụng có vòng đời riêng

Hai plugin có thể dùng hai phiên bản thư viện trùng binary name. Với các **defining loaders khác nhau**, chúng có thể tồn tại như các runtime classes riêng:

```text
Parent/AppLoader:
    shared.api.Plugin          (một contract dùng chung)
       ^                 ^
       |                 |
PluginLoaderA       PluginLoaderB:
    impl.A              impl.B
    lib.VersionX        lib.VersionY
```

Loader riêng giúp cô lập implementation/dependencies, nhưng **shared API cần được ủy quyền cho loader chung**; nếu interface `shared.api.Plugin` cũng bị định nghĩa riêng ở từng child, cast và service exchange có thể thất bại.

Có thể triển khai plugin loading bằng `URLClassLoader` với parent phù hợp; không cần custom subclass trừ khi bạn phải điều chỉnh delegation, resource lookup hoặc nguồn code.

### C. Cần chính sách delegation khác parent-first cho phạm vi xác định

Một số ứng dụng plugin/server muốn **child-first** với dependency riêng để không bị phiên bản cùng tên từ parent chi phối. Khi đó custom `loadClass` có thể được cân nhắc, nhưng phải có luật **namespace cụ thể**, chẳng hạn ưu tiên parent cho `java.*`, `javax.*` phù hợp runtime, `shared.api.*`, và chỉ tự nạp trước cho `plugin.internal.*`.

Đây là phần **khó và nhiều rủi ro hơn** so với override `findClass`. Thiếu đồng bộ, bỏ `findLoadedClass`, quản lý sai `resolveClass` hoặc tự định nghĩa lại shared API có thể gây `LinkageError`, `ClassCastException` hay `IllegalAccessError`. Nên thử loader framework/container đã tồn tại trước.

### D. Sinh/biến đổi bytecode theo quy trình ứng dụng

Custom loader có thể là một bước trong hệ thống compiler, bytecode generator hoặc transformation pipeline: lấy class bytes, kiểm tra/biến đổi, gọi `defineClass`. Nhưng nếu mục tiêu là **instrument những class JVM đã hoặc đang được nạp**, hãy cân nhắc **`java.lang.instrument.Instrumentation`**, Java agent, bytecode library, `MethodHandles.Lookup#defineClass` hoặc hidden classes tùy trường hợp; không phải mọi thay đổi cần thay lớp loader gốc.

### E. Phân tách vòng đời các thế hệ plugin

JVM thường không hỗ trợ “thay class bytes rồi khởi tạo lại cùng runtime class”. Muốn đưa phiên bản mới với cùng binary name vào sử dụng, một phương án là **tạo defining loader mới**, xây lại instances/services trên namespace mới, sau đó loại bỏ references đến loader và objects cũ.

Đây là một kiến trúc hot-reload, **không phải bảo đảm rằng cứ tạo class loader mới là JVM đã unload loader cũ**. Thread, static references, caches, context class loaders và registry có thể giữ class loader cũ sống lâu.

## 3. Những tình huống KHÔNG nên vội mở rộng ClassLoader

| Vấn đề thực tế | Cách ưu tiên | Khi nào mới nghĩ tới custom loader? |
|---|---|---|
| Ứng dụng không thấy thư viện JAR | Sửa `--class-path`, manifest `Class-Path` hoặc module path | Khi phải tìm lớp từ nguồn phi chuẩn |
| Muốn thêm một URL JAR/thư mục trong phạm vi riêng | `URLClassLoader` với parent đã chọn | Khi cần chính sách delegation hoặc nguồn dữ liệu khác |
| Muốn tìm implementation theo interface | `ServiceLoader` + provider declarations | Khi cần tự tổ chức nhiều namespace/provider loaders |
| Muốn gọi class bằng tên chuỗi | `Class.forName(name, initialize, loader)` hoặc `loader.loadClass(name)` | Khi không loader sẵn nào có thể cung cấp class |
| Muốn giảm thời gian khởi tạo của class | Hoãn sử dụng, dùng `Class.forName(..., false, ...)` khi hợp lý | Thường **không** cần custom loader |
| Muốn nạp thêm module | JPMS module path / `ModuleLayer` | Khi kiến trúc module cũng đòi policy loader riêng |
| Muốn đổi method/bytecode class đang chạy | Java agent/Instrumentation, công cụ bytecode phù hợp | Loader chỉ là một phần nếu pipeline định nghĩa class mới |
| Muốn nạp một class mới trong cùng package/nest context | `MethodHandles.Lookup#defineClass` hoặc hidden-class APIs khi đáp ứng điều kiện | Khi cần namespace/lifetime lớn hơn một lookup |
| Muốn chạy plugin từ bên thứ ba **không đáng tin** | Thiết kế thực thi cách ly ở process/container, xác thực code, kiểm soát quyền | **ClassLoader một mình không phải sandbox bảo mật** |
| Muốn có “một singleton static cho mọi plugin” | Đặt contract/state tại loader chung có chủ đích | Custom loader riêng thường tạo **nhiều bản static state**, trái mục tiêu |

Một số điểm thường bị hiểu sai:

- `ClassLoader` **không** phải công cụ quản lý dependency tự động như Maven/Gradle.
- `ClassLoader` **không** thay thế quyền truy cập `module-info.java`, exports/opens, package access hay JVM verification.
- `ClassLoader` **không** buộc mọi resource URL trở thành `File`; resource có thể đến từ JAR, JRT, mạng hoặc bộ nhớ.
- Cố tạo loader mới để “sửa” `NoClassDefFoundError` mà không chẩn đoán nguyên nhân là phản tác dụng: lỗi có thể do thiếu dependency, failed initialization, bytecode sai, version conflict hoặc loader constraints.

## 4. Ví dụ Java 17+: định nghĩa plugin class từ byte[] bằng custom loader

Demo này diễn tả một nhu cầu thực sự: ứng dụng **chỉ có service API trên application classpath**, còn implementation nằm trong bộ nhớ mà custom loader được cấp. Để thực hành dễ lặp lại, chúng ta đọc bytes từ một file `.class` riêng, nhưng **không thêm thư mục plugin vào classpath lúc chạy**. Trong hệ thống thật, `byte[]` có thể đến từ compiler trong bộ nhớ hoặc một nguồn nội bộ tin cậy.

Thư mục nguồn:

```text
loader-demo/
├── src/
│   ├── api/
│   │   └── Greeter.java
│   ├── plugin/
│   │   └── HelloGreeter.java
│   └── app/
│       └── LoaderDemo.java
└── out/
    ├── app/
    └── plugin/
```

### 4.1. Contract chung

Tệp **`src/api/Greeter.java`**:

```java
package api;

public interface Greeter {
    String greet();
}
```

### 4.2. Plugin implementation

Tệp **`src/plugin/HelloGreeter.java`**:

```java
package plugin;

import api.Greeter;

public final class HelloGreeter implements Greeter {
    static {
        System.out.println("Plugin initialized");
    }

    @Override
    public String greet() {
        return "hello-from-bytes";
    }
}
```

### 4.3. Application và custom loader

Tệp **`src/app/LoaderDemo.java`**:

```java
package app;

import api.Greeter;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public final class LoaderDemo {
    static final class MemoryLoader extends ClassLoader {
        private final Map<String, byte[]> definitions;

        MemoryLoader(ClassLoader parent, Map<String, byte[]> definitions) {
            super(parent);
            this.definitions = Map.copyOf(definitions);
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            byte[] bytes = definitions.get(name);
            if (bytes == null) {
                throw new ClassNotFoundException(name);
            }

            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader appLoader = LoaderDemo.class.getClassLoader();

        try {
            Class.forName("plugin.HelloGreeter", false, appLoader);
            System.out.println("Parent sees plugin: true");
        } catch (ClassNotFoundException expected) {
            System.out.println("Parent sees plugin: false");
        }

        byte[] classBytes = Files.readAllBytes(Path.of(args[0]));
        MemoryLoader custom = new MemoryLoader(appLoader,
                Map.of("plugin.HelloGreeter", classBytes));

        Class<?> type = custom.loadClass("plugin.HelloGreeter");
        System.out.println("Defined by custom: "
                + (type.getClassLoader() == custom));
        System.out.println("Class loaded, initialization pending");

        Greeter greeter =
                (Greeter) type.getDeclaredConstructor().newInstance();

        System.out.println("Message: " + greeter.greet());
        System.out.println("Shared Greeter: "
                + (custom.loadClass("api.Greeter") == Greeter.class));
        System.out.println("Same Class on repeat: "
                + (custom.loadClass("plugin.HelloGreeter") == type));
    }
}
```

**Vì sao chỉ override `findClass`?** Vì `MemoryLoader` kế thừa `loadClass` mặc định, nên JVM kiểm tra class đã nạp và ủy quyền parent trước khi gọi `findClass`. Khi plugin implementation không được parent tìm thấy, `findClass` nhận bytes, dùng `defineClass` để định nghĩa runtime class mới. Khi tìm `api.Greeter`, parent định nghĩa contract, nên app và plugin dùng **cùng interface**.

### 4.4. Biên dịch và chạy

Trên Linux/macOS/Git Bash, từ thư mục `loader-demo`:

```bash
mkdir -p out/app out/plugin

javac --release 17 -d out/app \
  src/api/Greeter.java src/app/LoaderDemo.java

javac --release 17 -cp out/app -d out/plugin \
  src/plugin/HelloGreeter.java

java -cp out/app app.LoaderDemo out/plugin/plugin/HelloGreeter.class
```

Trên Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path out/app, out/plugin | Out-Null
javac --release 17 -d out/app src/api/Greeter.java src/app/LoaderDemo.java
javac --release 17 -cp out/app -d out/plugin src/plugin/HelloGreeter.java
java -cp out/app app.LoaderDemo out/plugin/plugin/HelloGreeter.class
```

Đầu ra đã kiểm thử bằng `javac --release 17` và JDK 21 tương thích Java 17:

```text
Parent sees plugin: false
Defined by custom: true
Class loaded, initialization pending
Plugin initialized
Message: hello-from-bytes
Shared Greeter: true
Same Class on repeat: true
```

**Giải thích chính xác các bước:**

1. Runtime classpath chỉ có `out/app`. Parent/application loader tìm được `api.Greeter` và `app.LoaderDemo`, **không tìm được** `plugin.HelloGreeter`. Do đó dòng đầu là `false`.
2. Bytecode plugin đã được biên dịch vào `out/plugin`, nhưng thư mục đó **không nằm trên runtime classpath**. Chương trình đọc đúng file `HelloGreeter.class` thành `byte[]`.
3. `MemoryLoader.findClass("plugin.HelloGreeter")` được gọi sau khi parent không tìm được; `defineClass` tạo runtime class với defining loader là đối tượng `MemoryLoader`.
4. `custom.loadClass(...)` chỉ tải class, không bắt buộc chạy static initializer. Vì vậy dòng `Class loaded, initialization pending` xuất hiện trước `Plugin initialized`.
5. Lời gọi constructor bằng reflection kích hoạt initialization của plugin, rồi constructor và `greet()` chạy.
6. `custom.loadClass("api.Greeter")` ủy quyền parent, nên trả **đúng đối tượng `Class`** mà mã ứng dụng đang dùng. Cast sang `Greeter` thành công.
7. `custom.loadClass("plugin.HelloGreeter")` lần tiếp theo nhận cùng runtime `Class<?>` từ loader đó, không định nghĩa lại class.

**Giới hạn của ví dụ:** Loader này giữ `Map` chứa mutable `byte[]` chỉ để minh họa. `Map.copyOf` sao chép cấu trúc map, **không sao chép các mảng byte bên trong**; nếu dữ liệu đến từ caller không tin cậy/có thể thay đổi đồng thời, phải clone/kiểm soát ownership và xác thực bytecode. Ví dụ cũng không triển khai resource lookup, package metadata, CodeSource hoặc lifecycle đóng nguồn. Một hệ thống production cần các bước này theo yêu cầu thực tế.

## 5. Các quyết định quan trọng khi tự thiết kế loader

### 5.1. Nguồn bytecode và đặt tên

`ClassLoader.findClass(String name)` nhận **binary name** như `com.example.Widget`, không nhận `com/example/Widget.class`. Nếu nguồn là thư mục/JAR, đường tài nguyên có thể được suy ra khi cần:

```java
String entry = name.replace('.', '/') + ".class";
```

Đây là dòng minh họa không độc lập, phù hợp với binary names của class thông thường. Khi xây loader thực tế, phải kiểm tra package/name hợp lệ, tránh traversal, giới hạn đầu vào và chỉ đọc từ nguồn tin cậy. Không nhận một chuỗi tùy ý rồi ghép vào filesystem path mà không kiểm soát đường dẫn và thư mục gốc.

`defineClass(name, bytes, 0, bytes.length)` cần **class-file bytes** hợp lệ. Nếu binary name truyền vào không khớp tên class bên trong bytes, JVM có thể ném `NoClassDefFoundError`. Nếu bytecode sai định dạng hoặc sai quy tắc type verification, có thể gặp `ClassFormatError` hoặc `VerifyError`. Custom loader **không bỏ qua** JVM verification.

### 5.2. Chọn parent cho đúng

Chọn parent phù hợp giúp chia sẻ các class API và JDK platform classes:

```java
ClassLoader parent = SharedService.class.getClassLoader();
ClassLoader custom = new MemoryLoader(parent, definitions);
```

Đây là snippet minh họa; cần `SharedService` và `definitions` được khai báo. Mục tiêu là loader con và application dùng cùng runtime `SharedService` qua delegation.

**Không chọn `null` làm parent chỉ vì muốn “cô lập tuyệt đối”** nếu plugin vẫn cần type/library do application loader định nghĩa. Parent `null` biểu diễn đường bootstrap trong `ClassLoader`, nên có thể không nhìn thấy shared API từ application loader.

Chọn loader parent khác nhau dẫn tới kết quả khác nhau khi cùng tên class đã có mặt ở parent. Parent-first cũng có thể vô tình “thắng” bản class riêng của plugin nếu parent chứa class cùng tên.

### 5.3. Có cần override loadClass để child-first không?

Hầu hết trường hợp không cần. Nhưng nếu có yêu cầu namespace isolation nghiêm túc, một chiến lược minh họa là:

```text
loadClass(name, resolve):
    lock theo name
    nếu đã load -> trả đã load
    nếu name thuộc shared/JDK APIs -> thử parent trước
    nếu name thuộc private plugin namespace:
         thử findClass của child trước
         nếu không tìm được -> fallback parent theo chính sách
    các tên khác -> parent-first
    nếu resolve -> resolveClass(result)
    trả result
```

Đây là **giả mã**, không phải implementation đầy đủ. Cần kiểm soát các điểm khó:

- `getClassLoadingLock(name)` và `findLoadedClass(name)` để không tạo duplicate class trong tình huống đồng thời.
- `ClassNotFoundException` được dùng cho trường hợp không tìm thấy; **không được tùy tiện bắt rồi bỏ qua `VerifyError`, `LinkageError` hoặc `SecurityException` để dùng bản class khác**.
- Không tự định nghĩa `java.*`; `ClassLoader.defineClass` có hạn chế rõ ràng, và nhiều nền tảng còn có policy package/module riêng.
- `shared.api.*` thường phải parent-first để class/interface vượt qua boundary giữa plugin và host.
- Nếu code trong plugin chứa method signatures tham chiếu type do loader khác định nghĩa không tương thích, **loading constraints** của JVM có thể gây `LinkageError`.
- Nếu đảo delegation cho class nhưng không xử lý resource lookup hoặc service discovery tương ứng, class và resource có thể đến từ hai nguồn khác nhau không mong muốn.

Nếu bạn đang có container/plugin framework sẵn, tốt hơn nên hiểu và cấu hình loader policy của framework trước khi viết loader riêng.

### 5.4. Có cần findResource/findResources?

Nếu cùng một nguồn cung cấp `.class` và tài nguyên như configuration, service descriptors, image, schema, loader có thể cần triển khai:

```java
protected URL findResource(String name)
protected Enumeration<URL> findResources(String name)
```

`ClassLoader.getResource` và `getResources` có delegation/search rules riêng. Resource name có dạng `"plugin/config.json"` (dấu `/`), không phải binary name `plugin.config`. Một custom loader trả `Class<?>` đúng nhưng không tìm được `META-INF/services/...` vẫn có thể làm `ServiceLoader` không nhận diện provider.

Nếu resource nằm trong memory/custom scheme, cung cấp URL stream handler phù hợp hoặc API truy xuất trực tiếp bằng stream; không kỳ vọng mọi resource có thể chuyển thành `File`. Tạo custom protocol URL cần cân nhắc chính sách, lifetime và độ phức tạp của connection.

### 5.5. Package, sealing, protection domain và nguồn code

`defineClass` có ràng buộc về class name, package và tập chứng chỉ ký. Khi làm việc với signed JARs, package sealing, `CodeSource` hay cần metadata/protection domain cụ thể, **không nên chỉ đọc bytes rồi gọi overload `defineClass` mặc định và cho rằng mọi metadata được bảo toàn**.

`SecureClassLoader`, `URLClassLoader`, `definePackage` và overload `defineClass(..., ProtectionDomain)` cung cấp công cụ phục vụ các trường hợp liên quan. Với custom loader production, phải tuân thủ quy tắc package/certificates/signers phù hợp khi đưa classes từ nhiều nguồn vào cùng loader.

Hãy đọc JavaDoc của `defineClass`: định nghĩa tên thuộc `java.*` bị hạn chế; tên tham số phải khớp binary name trong class-file bytes khi được cung cấp.

### 5.6. Đồng thời: parallel capable loaders

`ClassLoader` hỗ trợ mô hình **parallel capable**. Các subclass có thể đăng ký bằng `registerAsParallelCapable()` từ static initializer của **chính subclass**, với điều kiện các superclass thích hợp đã được đăng ký và chưa tạo instance; API trả boolean thông báo kết quả.

Điều này cho phép locking theo class name thay vì một lock chung cho toàn loader trong các trường hợp phù hợp. **Không tự bật nếu implementation chưa bảo đảm thread-safety** của map, caches, I/O, transformations và namespace. Nếu tự override `loadClass` mà bỏ lock, việc hai thread cùng yêu cầu class có thể gây duplicate definition hoặc race. Parent-first implementation kế thừa từ `ClassLoader` thường ít rủi ro hơn cho người mới.

### 5.7. Vòng đời: đóng nguồn không có nghĩa unload class ngay

`URLClassLoader` triển khai `Closeable`; đóng nó giải phóng JAR/file handles trong khả năng của loader và ngăn nạp thêm classes/resources qua đường nó quản lý. Nhưng những classes đã load vẫn có thể được dùng, và `close()` **không ép garbage collector unload ngay**.

Custom `MemoryLoader` trong ví dụ không có tài nguyên native/file mở dài hạn, nhưng vẫn có thể giữ mảng bytes/metadata. Một loader production có nguồn network, file handles hoặc caches dài hạn nên có API lifecycle thích hợp, đồng thời quản lý references đến classes, objects, threads và TCCL.

## 6. Nhận diện rủi ro trước khi mở rộng loader

Một loader tùy chỉnh can thiệp vào nơi JVM lấy class bytes và nơi **định nghĩa kiểu**. Vì vậy một tính năng chỉ định làm mới nguồn nạp lớp vẫn có thể thay đổi các ranh giới quan trọng:

| Dấu hiệu | Điều cần kiểm tra |
| --- | --- |
| `ClassCastException` dù class cùng tên | Hai bên có nhận **cùng `Class<?>` của API chia sẻ** hay mỗi loader tự định nghĩa một bản? |
| `ClassNotFoundException` / `NoClassDefFoundError` | Tên/nguồn có vắng mặt, dependency không nhìn thấy, hay class từng khởi tạo lỗi? |
| `ClassFormatError`, `VerifyError`, `UnsupportedClassVersionError` | Bytecode đã đọc có đúng cấu trúc, verification và target JVM? |
| `LinkageError` | Có duplicate definition, binary incompatibility hoặc loading constraint giữa các loader? |
| Resource/provider không được tìm thấy | Loader có hỗ trợ resource lookup và cùng định danh SPI không? |
| Plugin cũ không được thu hồi | Thread, TCCL, registry, cache, handle JAR hoặc object nào đang giữ loader? |

**Đừng xử lý mọi lỗi bằng cách đổi sang child-first hoặc nuốt `LinkageError` để thử bytes khác.** Nên xác định defining loader, binary name, nguồn bytes và nguyên nhân đầu tiên trước. Phần còn lại của chương đi sâu vào chính các giới hạn này, từ lựa chọn parent đến error handling, type identity và vòng đời. Class loader tự nó không phải sandbox cho mã không tin cậy.

## 7. So sánh lựa chọn: URLClassLoader, ServiceLoader, ModuleLayer

### URLClassLoader

Khi có thư mục/JAR ở URL phù hợp và muốn load classes/resources từ đường dẫn đó:

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

Path jar = Path.of("plugins/sample.jar");
URL[] urls = { jar.toUri().toURL() };

try (URLClassLoader loader =
        new URLClassLoader(urls, MyApp.class.getClassLoader())) {
    Class<?> type = loader.loadClass("plugins.Sample");
    // Dùng type trong phạm vi cần thiết.
}
```

Đây là **snippet minh họa**, chưa là file `main` độc lập vì cần `MyApp` và JAR phù hợp. `URLClassLoader` đã cài đặt việc tìm class/resource từ directories/JARs, kiểm soát tài nguyên mở và nhiều hành vi cần thiết; **không cần viết lại `findClass` cho use case này**.

Lưu ý `URLClassLoader` mặc định kế thừa parent delegation. Nếu parent đã có class cùng tên, parent có thể thắng và loader chỉ trả lại class của parent. Muốn dependency isolation có chủ đích cần giải pháp lớp cao hơn, không đơn thuần thêm URL.

### ServiceLoader

Khi ứng dụng chỉ cần implementation của service interface, không cần quản lý class bytes:

```java
ServiceLoader<MyService> services =
        ServiceLoader.load(MyService.class, pluginLoader);
```

Đây là snippet minh họa cần `MyService` và `pluginLoader` có thật. `ServiceLoader` quản lý discovery dựa trên `META-INF/services` hoặc named-module `provides`, còn class loader quản lý visibility/runtime class identity. Có thể phối hợp **`ServiceLoader` với `URLClassLoader` sẵn có**, không buộc custom subclass.

### JPMS ModuleLayer

Với named modules, module path, dependency graph, readability và module access có thể được giải quyết bằng `java.lang.module.Configuration` / `ModuleLayer`. Framework có thể thiết lập layer mới và gắn loader phù hợp. Đây là cơ chế khác với đọc tùy ý `.class` bằng `findClass`.

Nếu bài toán là “plugin có `module-info.java` và cần isolation theo module”, đánh giá module layer trước, vì tự viết loader không tự cung cấp module readability/exports/opens.

### MethodHandles.Lookup / hidden classes

Nếu một framework sinh một lớp **liên quan chặt với lookup class** (như helper class trong runtime package phù hợp), `MethodHandles.Lookup#defineClass` có thể định nghĩa class trong loader/package của lookup class theo những ràng buộc tương ứng. `defineHiddenClass` phục vụ những trường hợp bytecode-generated classes không cần được tìm lại bằng binary name thông thường.

Không nên mặc định đây là thay thế hoàn toàn cho loader khi cần namespace plugin độc lập; chúng giải quyết loại bài toán khác.

### Instrumentation / Java agent

Nếu muốn quan sát/sửa bytecode tại sự kiện class load hoặc retransform/redefine trong những giới hạn của Instrumentation API, Java agent là lựa chọn chuyên dụng. Tạo custom loader không cho phép tùy ý thay tất cả những classes đã được parent/JVM định nghĩa.

## 8. Một quy trình quyết định thực tế

Hỏi lần lượt:

1. **Nguồn class có phải JAR/thư mục thông thường không?** Có → thử classpath/module path hoặc `URLClassLoader`.
2. **Mục tiêu chỉ tìm service implementations không?** Có → thử `ServiceLoader`/JPMS `provides`.
3. **Cần nạp đúng class name với loader đã biết?** Có → dùng `Class.forName(name, initialize, loader)` hoặc `loader.loadClass(name)`.
4. **Bytecode đến từ nguồn không thể biểu diễn tự nhiên bằng URLClassLoader?** Có → cân nhắc subclass override `findClass`.
5. **Cần hai bản cùng binary name cùng tồn tại?** Có → thiết kế defining loaders riêng và shared contracts; cân nhắc container/module framework.
6. **Cần child-first thật không?** Chỉ khi bạn có namespace isolation rules và kiểm thử lỗi type identity/delegation; không phải mặc định.
7. **Cần thay thế class đã định nghĩa trong cùng loader không?** Đánh giá Instrumentation hoặc loader generation mới; một `defineClass` thứ hai cùng tên trong cùng loader không giải quyết được.
8. **Có yêu cầu chạy mã không đáng tin?** Đưa isolation/security về thiết kế process, OS sandbox/container và kiểm soát code provenance; loader một mình không đủ.
9. **Có kế hoạch đóng, dọn, unload?** Xem strong references, thread/TCCL, caches, opened JARs, registration và lifecycle trước khi triển khai.
10. **Có thể viết test chạy trên runtime triển khai thật?** Phải kiểm tra class identity, classpath, resource loading, module access, concurrency và lỗi root cause.

Câu hỏi “Khi nào cần mở rộng `ClassLoader`?” thường có câu trả lời tốt nhất là **“khi chúng ta sở hữu một cơ chế định nghĩa class đặc thù, và đã chứng minh các API có sẵn không đủ”**. Không bắt đầu từ việc subclass chỉ vì muốn gọi `loadClass`.

## 9. Checklist chất lượng cho một ClassLoader tự viết

- [ ] `findClass` trả `Class<?>` nếu tìm/định nghĩa thành công; ném `ClassNotFoundException` đúng khi **không tìm được**.
- [ ] Input là **binary name**; nếu chuyển sang resource path, dùng tên `pkg/Type.class` phù hợp và kiểm soát nguồn.
- [ ] `defineClass` được truyền đúng bytes và binary name; không định nghĩa trùng tên trong cùng loader.
- [ ] Parent có shared API/JDK types cần thiết; không định nghĩa lại API chung trong child một cách vô ý.
- [ ] Nếu dùng custom `loadClass`, có locking, `findLoadedClass`, fallback/resolve và exception propagation đúng.
- [ ] Resource discovery/`ServiceLoader` tìm đúng descriptors nếu provider source dùng cùng loader.
- [ ] Có kiểm soát kích thước, nguồn tin cậy và integrity của bytes; không coi loader là sandbox.
- [ ] Có chính sách module, package-private, sealing, code source/signer, native libraries nếu hệ thống cần.
- [ ] Không giữ vô hạn các references đến plugin loaders/instances khi có yêu cầu unload.
- [ ] Test không chỉ happy path: thiếu class, thiếu dependency, sai bytecode, version mismatch, duplicate class, concurrency và đổi phiên bản.

## 10. Bài tập tự kiểm tra

**1. Khi có một JAR trên filesystem cần load động, phải subclass `ClassLoader` không?** Không nhất thiết; thường thử `URLClassLoader` với parent phù hợp trước.

**2. Vì sao override `findClass` thay vì `loadClass` trong loader parent-first?** Vì lớp cơ sở đã xử lý kiểm tra class đã nạp, parent delegation, synchronization và resolution; `findClass` chỉ bổ sung cách tìm nguồn class riêng.

**3. Tại sao classloader trong ví dụ phải dùng application loader làm parent?** Vì plugin triển khai `api.Greeter` và app cần cast sang **cùng runtime interface**; parent cung cấp contract dùng chung.

**4. `loadClass` có chạy `static { ... }` ngay không?** Không phải theo hợp đồng mặc định. Initialization diễn ra khi chương trình/JVM yêu cầu, chẳng hạn tạo instance.

**5. Hai loaders cùng `defineClass("p.Widget", sameBytes, ...)` có tạo cùng runtime class không?** Không. Defining loader khác làm class identity khác.

**6. `ClassNotFoundException` có nên được dùng để che `VerifyError` không?** Không. Lỗi không tìm thấy khác lỗi bytecode sai; cần báo đúng nguyên nhân.

**7. Muốn provider implementation được chọn theo loader của plugin, chọn API nào?** Thường `ServiceLoader.load(serviceType, pluginLoader)` hoặc một phương án module-layer thích hợp; không cần tự hiện thực SPI discovery.

**8. Custom ClassLoader có bảo đảm plugin đáng tin và không truy cập tài nguyên hệ thống không?** Không. Đó không phải cơ chế sandbox bảo mật độc lập.

**9. `URLClassLoader.close()` có ép unload tất cả classes do nó định nghĩa không?** Không. Nó đóng tài nguyên loader quản lý nhưng class unloading phụ thuộc JVM/garbage collection và không còn references.

**10. Thời điểm nào nên đầu tư custom delegation policy?** Khi có yêu cầu namespace isolation đã xác định, đã chọn shared API boundary, biết danh sách packages cần ưu tiên parent/child, và có test cho type identity, linkage, concurrency.

## 11. Tài liệu chuẩn

- Java SE 17, `ClassLoader`: thuật toán `loadClass`, `findClass`, `defineClass`, `getClassLoadingLock` và `registerAsParallelCapable`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17, `URLClassLoader`: nạp classes/resources từ URL, `close()` và `findClass` sẵn có: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- Java SE 17, `ServiceLoader`: SPI providers trên classpath hoặc trong named modules: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Java SE 17, `MethodHandles.Lookup#defineClass` và hidden-class APIs: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- Java SE 17, `Instrumentation`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- JVMS `5.3, *Creation of Classes and Interfaces*, về defining/initiating loaders và class identity: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3

**Ghi nhớ:** Chỉ mở rộng `ClassLoader` khi cần thay đổi **cách class bytes được cung cấp hoặc namespace/chính sách load**. Đối với parent-first custom loader, bắt đầu bằng `findClass` và `defineClass`, giữ shared API ở parent, và không quên **class identity, resources, modules, concurrency, security và lifecycle**. Với JAR thông thường và SPI, hãy tận dụng `URLClassLoader`/`ServiceLoader` trước.

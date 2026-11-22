# Vì sao ClassLoader không tạo thành sandbox bảo mật cho plugin Java

> **Java Core → ClassLoader → Kiến trúc plugin.** `ClassLoader` giúp kiểm soát **từ đâu tìm bytecode**, **lớp nào thuộc namespace nào** và **quan hệ delegation giữa host và plugin**. Nó không tạo ranh giới bảo mật tương đương một tiến trình, một người dùng hệ điều hành hay container. Một plugin có bytecode Java bình thường, sau khi được nạp vào cùng JVM, nhìn chung vẫn có thể gọi các API nền tảng theo quyền mà **tiến trình JVM** có. Bài học phân biệt class isolation, module encapsulation, metadata bảo mật lịch sử và sandbox thực tế; có ví dụ Java 17+ được chạy kiểm chứng.

## 1. Hiểu đúng bài toán và mô hình đe dọa

Giả sử hệ thống host cho phép tải một JAR chứa plugin:

```text
Host JVM process
├── Host application classes
├── Plugin API: com.example.api.Plugin
├── Plugin ClassLoader A
│   ├── plugin-a.jar
│   └── một số dependencies riêng
└── Plugin ClassLoader B
    ├── plugin-b.jar
    └── phiên bản dependencies khác
```

Một thiết kế như vậy có thể giải quyết các vấn đề hợp lý:

- Hai plugin dùng hai phiên bản thư viện cùng tên nhưng khác defining loader.
- Không tự đưa implementation của plugin A vào search path của plugin B.
- Cho plugin giao tiếp với host qua API chung có cùng `Class<?>` identity.
- Quản lý thế hệ plugin: tạo loader mới khi cập nhật, giải phóng references tới loader cũ nếu có thể.
- Giữ cấu trúc tìm class và resource có thể giải thích, kiểm thử.

**Nhưng:** nếu plugin A là bytecode không đáng tin, câu hỏi chuyển sang hướng khác: “Liệu plugin có thể đọc file của host, kết nối mạng, sửa global state hoặc dừng process không?” Chỉ chia tách loaders **không cung cấp lời hứa ngăn những hành động ấy**.

### Ba mô hình tin cậy khác nhau

| Mô hình plugin | Mục tiêu | ClassLoader đủ không? |
| --- | --- | --- |
| Plugin **đáng tin**, khác dependencies | Tách thư viện, tránh `ClassCastException`/collision, quản lý lifecycle. | Có ích và thường phù hợp, nhưng còn phải quản lý state. |
| Plugin **bán tin cậy**, hợp tác theo contract | Hạn chế lỗi vô tình bằng API/plugin contract, validation, timeout. | Hữu ích một phần; không đảm bảo chống mã cố ý lách contract. |
| Plugin **không tin cậy hoặc có thể độc hại** | Bảo vệ dữ liệu, file, network, process và tài nguyên khỏi mã chạy tùy ý. | **Không.** Cần ranh giới thực thi mạnh hơn như tiến trình khác với quyền OS hạn chế. |

**Threat model quyết định giải pháp:** tránh class conflict khác hoàn toàn với việc phòng plugin cố tình đánh cắp dữ liệu, phá dịch vụ hoặc vượt kiểm soát quyền.

## 2. ClassLoader thực sự cô lập những gì?

JVM định danh một class/interface thông thường bằng cặp **(binary name, defining loader)**.

```text
Loader A -> com.plugin.Widget (Class A)
Loader B -> com.plugin.Widget (Class B)

Tên nhị phân bằng nhau
Định nghĩa bởi loader khác nhau
=> Class A != Class B
```

Hệ quả:

- Cùng tên `com.plugin.Widget` không nhất thiết cùng runtime type.
- Hai lớp thuộc hai loaders khác nhau có thể gặp `ClassCastException` khi ép kiểu, kể cả code trông giống nhau.
- `Package` runtime, package-private access và metadata package chịu sự phân định theo defining loader.
- Một loader chỉ tìm những resources/classes trong phạm vi nguồn và delegation policy của nó, không tự đọc mọi JAR ngoài đường tìm.
- TCCL (`Thread.currentThread().getContextClassLoader()`) có thể được framework sử dụng để tìm provider/resource khác system loader.

Đây là **namespace và dependency isolation**. Nó là thuộc tính quan trọng cho plugin architecture, nhưng **không phải chính sách cấm sử dụng Java API**.

### Parent delegation không phải tường lửa

Đường `ClassLoader.loadClass` phổ biến dùng parent-first:

```text
pluginLoader.loadClass("java.nio.file.Files")
    |
    v
parent / platform / bootstrap lookup
    |
    '--> java.nio.file.Files được trả từ Java runtime
```

Parent delegation giúp thống nhất các lớp nền tảng và chia sẻ API, không chặn plugin dùng chính các API đó. Việc không cho plugin **định nghĩa lại** `java.lang.String` không có nghĩa đã không cho plugin **gọi** `java.lang.String`, `Files`, `Socket`, `ProcessBuilder` hoặc các phương thức khác của JDK mà nó truy cập được.

Không tự đặt `parent = null` rồi gọi đó là “sandbox”. Parent null là yêu cầu delegation đến bootstrap loader theo semantics của `ClassLoader`; nhiều API nền tảng vẫn tồn tại. Ngoài ra, class loading constraints và namespaces cần tuân thủ dù chọn parent nào.

## 3. Điều gì KHÔNG được class loader ngăn chặn?

Nếu class đã được JVM chấp nhận và bắt đầu thực thi, bytecode của nó có thể tự gọi các public APIs mà module/access rules và môi trường cho phép. Một vài ví dụ đáng chú ý:

| Khả năng của plugin | ClassLoader có tự chặn không? | Rủi ro đối với host |
| --- | --- | --- |
| `Files.readString(Path)` | Không. | Đọc file process có quyền, nếu biết/đoán đường dẫn. |
| `Files.writeString(Path, ...)` | Không. | Sửa/xóa dữ liệu mà OS account có quyền. |
| `System.getProperty`, `System.getenv` | Không. | Đọc system properties/environment có sẵn trong process. |
| `Socket`, `HttpClient` | Không. | Kết nối ra ngoài nếu network policy cho phép. |
| `ProcessBuilder` | Không. | Chạy process con nếu OS/runtime cho phép. |
| `System.exit` | ClassLoader không đảm bảo chặn. | Có thể kết thúc cả JVM chứa host. |
| Tạo thread, giữ lock, CPU loop, cấp phát bộ nhớ | Không. | Tắc nghẽn, memory pressure, denial of service. |
| Gọi API host public hay lấy references được truyền | Không. | Thay đổi trạng thái chia sẻ tùy API/objects được phơi bày. |
| Reflection | Không phải quy tắc từ ClassLoader; JPMS còn kiểm soát reflection. | Có thể truy cập thêm members khi module/package mở phù hợp. |

Điều kiện bên ngoài vẫn có tác dụng: filesystem ACL, quyền OS user, SELinux/AppArmor, container config, network policy, JPMS access và một số quyền của API chuyên biệt. Nhưng **cơ chế này không phải bảo đảm do ClassLoader tạo ra**.

Không diễn giải bảng thành “mọi lời gọi luôn thành công”: thao tác có thể thất bại vì OS permissions, path không tồn tại, network bị chặn, module encapsulation hoặc security policy khác. Điểm cần nhớ là **việc thay loader không tự thiết lập deny policy cho những thao tác ấy**.

### “Không cung cấp API nguy hiểm cho plugin” chưa đủ

Host có thể expose interface chỉ gồm:

```java
public interface PluginContext {
    String readPublicConfig();
    void emitEvent(String event);
}
```

Đây là **snippet Java** minh họa contract, không phải chương trình độc lập. Với plugin đáng tin, contract giúp thiết kế tốt. Nhưng nếu bytecode plugin được phép thực thi **mã Java tùy ý trong cùng JVM**, nó có thể gọi thẳng `Files`, `HttpClient` hoặc API khác mà không đi qua `PluginContext`. Một restricted wrapper API **không tạo sandbox** nếu không có thêm enforcement ở runtime/OS/process.

## 4. SecureClassLoader có chữ “Secure” nhưng không biến plugin thành an toàn

`java.security.SecureClassLoader` mở rộng `ClassLoader` và cung cấp API gắn `CodeSource`, `ProtectionDomain` và `PermissionCollection` cho class được định nghĩa.

```java
protected final Class<?> defineClass(
    String name, byte[] bytes, int offset, int length,
    java.security.CodeSource source);

protected java.security.PermissionCollection getPermissions(
    java.security.CodeSource source);
```

Đây là **chữ ký API rút gọn**, không copy thành file Java độc lập. Subclass có thể override `getPermissions` để cung cấp permission metadata cho domain được dựng.

Lịch sử:

```text
SecureClassLoader.defineClass(..., CodeSource)
       |
       v
CodeSource(location, certificates)
       |
       v
getPermissions(CodeSource)
       |
       v
ProtectionDomain
       |
       v
Class<?> gắn với domain
       |
       v
Legacy SecurityManager/Policy (khi từng được bật)
       |
       '--> nền tảng có thể kiểm tra permissions tại protected operations
```

**Khi Security Manager không được bật**, một tập permissions rỗng không tự bảo vệ filesystem/network. **Từ JDK 24**, Security Manager bị vô hiệu hóa vĩnh viễn theo JEP 486. Javadoc `SecureClassLoader` hiện đại cũng nêu rõ permissions không còn dùng để kiểm soát quyền truy cập tài nguyên khi Security Manager không được hỗ trợ.

`CodeSource` vẫn có thể hữu ích cho metadata/provenance, nhưng:

- `CodeSource.location` có thể là URL **do loader tự gán**; nó không chứng minh bytes đã được xác minh nguồn gốc.
- `CodeSource` không tự chứng minh JAR đã ký hoặc đáng tin; nếu có signing cần quy trình verification phù hợp.
- `ProtectionDomain.getPermissions()` có thể chứa collection rỗng nhưng điều đó không tự chặn `Files.readString` trên JDK 24+.
- Certificate consistency, class-format verification, package sealing, module access và `SecurityManager` là các khái niệm khác nhau; không thay thế cho nhau.

## 5. Vì sao SecurityManager không còn là đường xây sandbox mới?

Trước đây Java có mô hình kiểm tra permissions dựa trên Security Manager:

- `CodeSource` và domain liên kết class với một nguồn code.
- `java.security.Policy` có thể định nghĩa `FilePermission`, `SocketPermission`, `PropertyPermission`, v.v.
- Khi `SecurityManager` được kích hoạt, các API tích hợp permission checks có thể cho phép hoặc từ chối thao tác.
- `AccessController` tham gia mô hình stack-based access control và `doPrivileged`.

Tuy nhiên, cơ chế này có độ phức tạp cao, adoption hạn chế và không bao giờ tạo bảo đảm cô lập mọi vấn đề (native code, tài nguyên chia sẻ, side channels và các rủi ro khác).

Dòng thời gian:

| Java/JDK | Tình trạng |
| --- | --- |
| Java 8/11 và các bản cũ | Security Manager có thể được dùng trong môi trường bật và cấu hình đúng; mặc định ứng dụng thường không có sandbox. |
| Java 17 | **JEP 411** deprecate Security Manager **for removal**. |
| Java 17–23 | Các khả năng legacy còn có nhưng có cảnh báo/ràng buộc tùy phiên bản. |
| **JDK 24+** | **JEP 486** vô hiệu hóa Security Manager vĩnh viễn. Không thể cài/bật lại bằng launcher hoặc `System.setSecurityManager`. |

Trên JDK 24+, `System.getSecurityManager()` trả `null`; `System.setSecurityManager(...)` ném `UnsupportedOperationException`; các thuộc tính policy kiểu cũ không tạo enforcement. `AccessController.checkPermission(...)` còn có thể **ném `AccessControlException` vô điều kiện** theo API compatibility, nhưng điều đó **không** có nghĩa file/network API được bảo vệ như xưa.

Điều quan trọng khi di trú plugin framework cũ: không chỉ thay thế cú pháp, mà phải chuyển **thực thi ranh giới bảo mật** sang hệ thống thích hợp. Xem tài liệu Oracle về việc Security Manager bị vô hiệu hóa và JEP 486 ở cuối bài.

## 6. Thực hành Java 17+: plugin đọc được tệp thử nghiệm dù domain không cấp FilePermission

Thí nghiệm là một minh họa **an toàn, chỉ đọc tệp do host tự tạo trong thư mục tạm**. Host tự tạo file chứa text `training-only`, cho plugin biết đường dẫn bằng property `demo.resource.path` để kết quả tái lập; plugin dùng `Files.readString` đọc file đó **không qua plugin API của host**.

Mục tiêu không phải truy cập dữ liệu bí mật hay vượt kiểm soát OS. Mục tiêu là quan sát: **một SecureClassLoader trả permission collection rỗng không ngăn code Java trong cùng JVM đọc tài nguyên mà process được phép đọc khi không có Security Manager**.

### Cấu trúc project

```text
src/
  plugin/
    demo/
      Worker.java
  app/
    LoaderSandboxDemo.java
plugin-classes/  (javac tạo)
app-classes/     (javac tạo)
```

**File `src/plugin/demo/Worker.java`:**

```java
package plugin.demo;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class Worker {
    public static String readHostFile() throws IOException {
        String path = System.getProperty("demo.resource.path");
        return Files.readString(Path.of(path)).trim();
    }
}
```

**File `src/app/LoaderSandboxDemo.java`:**

```java
import java.io.FilePermission;
import java.io.IOException;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.CodeSource;
import java.security.PermissionCollection;
import java.security.Permissions;
import java.security.SecureClassLoader;
import java.security.cert.Certificate;

public final class LoaderSandboxDemo {
    static final class PluginLoader extends SecureClassLoader {
        private final Path root;
        private final URL origin;

        PluginLoader(Path root) throws IOException {
            super(ClassLoader.getPlatformClassLoader());
            this.root = root.toAbsolutePath();
            this.origin = this.root.toUri().toURL();
        }

        @Override
        protected PermissionCollection getPermissions(CodeSource cs) {
            return new Permissions();
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            try {
                byte[] data = Files.readAllBytes(
                        root.resolve(name.replace('.', '/') + ".class"));
                CodeSource cs = new CodeSource(
                        origin, (Certificate[]) null);
                return defineClass(name, data, 0, data.length, cs);
            } catch (IOException ex) {
                throw new ClassNotFoundException(name, ex);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path example =
                Files.createTempFile("harmless-demo-", ".txt");
        try {
            Files.writeString(
                    example, "training-only",
                    StandardCharsets.UTF_8);
            System.setProperty(
                    "demo.resource.path", example.toString());

            PluginLoader loader =
                    new PluginLoader(Path.of("plugin-classes"));
            Class<?> worker = Class.forName(
                    "plugin.demo.Worker", true, loader);

            System.out.println("owned by plugin loader: "
                    + (worker.getClassLoader() == loader));
            System.out.println("code source present: "
                    + (worker.getProtectionDomain()
                            .getCodeSource() != null));

            boolean granted = worker.getProtectionDomain()
                    .getPermissions()
                    .implies(new FilePermission(
                            example.toString(), "read"));

            System.out.println(
                    "file permission in domain: " + granted);

            String value = (String) worker
                    .getMethod("readHostFile")
                    .invoke(null);
            System.out.println("plugin file read: " + value);

            System.out.println("same class on reload: "
                    + (Class.forName(
                            "plugin.demo.Worker", false, loader)
                            == worker));
        } finally {
            System.clearProperty("demo.resource.path");
            Files.deleteIfExists(example);
        }
    }
}
```

### Biên dịch và chạy

Từ thư mục có `src`:

```bash
javac --release 17 -d plugin-classes src/plugin/demo/Worker.java
javac --release 17 -d app-classes src/app/LoaderSandboxDemo.java
java -cp app-classes LoaderSandboxDemo
```

Không đưa `plugin-classes` vào application classpath. Loader của host chỉ nhận `app-classes`, còn loader tùy chỉnh tìm bytecode `plugin.demo.Worker` từ `plugin-classes`. Chương trình dùng API sẵn có trong Java 17+.

**Stdout chính xác đã kiểm chứng trên OpenJDK 24 với `javac --release 17`:**

```text
owned by plugin loader: true
code source present: true
file permission in domain: false
plugin file read: training-only
same class on reload: true
```

### Giải thích 5 dòng đầu ra

1. `owned by plugin loader: true`: instance `PluginLoader` mới là defining loader của `plugin.demo.Worker`; parent không định nghĩa class đó.
2. `code source present: true`: overload `SecureClassLoader.defineClass` đã gắn `CodeSource`; thông tin nguồn **không phải giấy chứng nhận an toàn**.
3. `file permission in domain: false`: `getPermissions` trả collection rỗng, do đó `PermissionCollection.implies(FilePermission(path,"read"))` là `false`.
4. **`plugin file read: training-only`:** plugin vẫn đọc được file do host tạo, bằng direct `Files.readString` khi JVM không dùng Security Manager để từ chối theo domain. Đây là điều cần chứng minh.
5. `same class on reload: true`: với cùng binary name và defining loader, lần nạp tiếp theo tái sử dụng `Class<?>`; property này thuộc class loading, không thuộc authorization.

**Lưu ý môi trường:** Trên JDK 24+ không có Security Manager được bật, nên kết quả minh họa diễn ra trong cấu hình chuẩn không bị OS chặn. Trên JDK 17–23, khi **không bật Security Manager**, cùng nguyên tắc áp dụng; nếu chủ động bật Security Manager cũ với policy phù hợp, hành vi đọc file có thể khác. Ví dụ **không cần** và **không hướng dẫn** bật Security Manager.

**Lưu ý phạm vi an toàn:** Host tự cung cấp đường dẫn tới file do chính nó tạo và xóa sau test. Việc đó minh họa rằng loader không chặn thao tác OS mà process được phép làm; nó **không** kiểm thử đoán đường dẫn bí mật, ký JAR hay khai thác lỗi hệ điều hành. Đừng đặt secrets thực vào system property để mô phỏng test này.

## 7. Tại sao API host chỉ lộ các method an toàn vẫn không tạo sandbox?

Một host có thể thiết kế:

```java
public interface Plugin {
    void execute(PluginContext ctx);
}

public interface PluginContext {
    String getPublicGreeting();
}
```

Đây là **hai khai báo minh họa** cần tách thành `Plugin.java` và `PluginContext.java` nếu muốn biên dịch. Nếu plugin chỉ tự nguyện dùng `ctx.getPublicGreeting()`, API contract có tác dụng giảm misuse.

Nhưng plugin bytecode tùy ý cũng có thể viết:

```java
// Ví dụ ý tưởng bên trong code plugin:
String runtime = System.getProperty("java.version");
java.nio.file.Path path = java.nio.file.Path.of("config.txt");
// Nếu process OS có quyền thì plugin có thể dùng Files API.
```

Không có mechanism nào trong `ClassLoader` mặc định buộc plugin phải gọi `ctx` thay vì thư viện JDK. Không trao reference trực tiếp tới database client cho plugin cũng không đủ nếu nó vẫn có credentials trong environment/process hay quyền đọc tệp config chứa connection string.

**Object capability và trust boundary:** Contract API được kiểm soát có ích nếu plugin **đáng tin** hoặc thực thi trong sandbox thực sự chặn những quyền ngoài contract. Nếu plugin độc hại chạy cùng process mà vẫn gọi API JDK, chỉ hạn chế `PluginContext` là biện pháp **kỷ luật kiến trúc**, không phải phòng thủ tuyệt đối.

## 8. JPMS mạnh hơn classpath encapsulation nhưng cũng không phải sandbox

Từ Java 9, named modules có `requires`, `exports` và `opens`:

```java
module com.example.host {
    exports com.example.plugin.api;
    // Không exports/open packages implementation riêng của host.
}
```

JPMS giúp kiểm soát:

- Module nào **đọc** module nào.
- Public API của package nào được **export** cho module khác.
- Package nào được **open** cho reflective access sâu.
- Một số truy cập qua reflection/bytecode vào internals bị chặn theo module graph.

Nhưng:

- `module-info.java` không phải policy “plugin không được đọc bất kỳ file nào”.
- Plugin có thể vẫn dùng các public API của `java.base` được phép, như `java.nio.file.Files` và `System.getProperty`.
- `--add-opens` và `--add-exports` mở thêm module boundaries khi framework cần; lạm dụng chúng làm giảm encapsulation, chứ không tạo file/network isolation.
- Một module không exported có thể giảm một đường truy cập trực tiếp tới internal host classes, nhưng **không đủ** trước code plugin chạy cùng OS process với những quyền sẵn có.
- Reflection và native/JNI/FFM có các quy định truy cập riêng; không đồng nhất “có module” với “không thể làm hành động nguy hiểm”.

Hãy dùng JPMS để xây module API boundaries rõ ràng. Khi cần cách ly code không tin cậy, thêm security boundary ở tầng **process, OS và hạ tầng**.

## 9. Class-loader lifecycle không đồng nghĩa cô lập tài nguyên

Loader mới có thể nạp cùng binary name ở generation khác, nhưng không chuyển object/static state cũ hay tạo ranh giới quyền mới. `URLClassLoader.close()` chỉ đóng tài nguyên thuộc loader, không dừng threads hoặc hoàn tác filesystem/network side effects. TCCL, registries, threads và static/global state có thể giữ plugin alive hoặc cho plugin ảnh hưởng shared process. Đây là thêm một lý do phải phân biệt lifecycle cleanup với **security isolation**.

## 10. Quy trình phù hợp cho plugin đáng tin

Nếu plugin do đội ngũ kiểm soát/phê duyệt, cần nạp động và tương thích thư viện, class loaders vẫn là công cụ đúng. Kiến trúc tham khảo:

```text
Host application
    |
    +--> shared plugin API (host/parent loader)
    |
    +--> PluginLoader A -> plugin-a.jar + dependencies A
    |
    '--> PluginLoader B -> plugin-b.jar + dependencies B
```

Các nguyên tắc:

1. **API chung** do parent loader định nghĩa. Implementation trong plugin loader có thể implements interface này mà vẫn cast được về API của host.
2. **Không đóng gói trùng bản API** trong từng plugin child loader nếu child tự định nghĩa bản riêng; làm vậy tạo runtime types không tương thích.
3. **Quyết định delegation** rõ ràng. Parent-first thường dễ suy luận; child-first nếu có lý do phiên bản thư viện phải tránh shadow JDK/host API và xử lý các package/loader constraints phù hợp.
4. **Kiểm tra nguồn artifact**: version, checksum, chữ ký khi cần và provenance đáng tin. Đọc JAR thành công không chứng minh đáng tin.
5. **Quản lý vòng đời**: unregister callbacks, shutdown tasks, close I/O, dọn TCCL, bỏ references và sử dụng `URLClassLoader.close()` khi thích hợp.
6. **Có hợp đồng lỗi** và monitoring cho plugin. Một exception của plugin không nên phá state host ngoài ý muốn; dùng transactional/compensation mechanisms khi cần.
7. **Không gọi “an toàn với untrusted code”** chỉ vì loaders tách biệt. Đây là thiết kế plugin **đáng tin nhưng có dependencies riêng**.

Một loader child-first tùy chỉnh, nếu override `loadClass`, còn cần đúng đồng bộ `getClassLoadingLock`, `findLoadedClass` và tránh định nghĩa trùng cùng binary name. Đó là bài toán correctness/class identity, không phải security sandbox.

## 11. Thiết kế cho plugin không tin cậy: tiến trình riêng

Khi threat model bao gồm plugin cố tình vượt contract, kiến trúc điển hình:

```text
                     Host process (trusted)
                +----------------------------+
                | API gateway / plugin broker|
                | Authenticate + authorize   |
                | Input validation + limits  |
                +--------------+-------------+
                               |
                      IPC / network protocol
                               |
                +--------------v-------------+
                | Worker process (untrusted) |
                | Different OS identity      |
                | Limited filesystem mounts  |
                | Egress network policy      |
                | CPU/memory/time limits     |
                | Auditing and termination   |
                +----------------------------+
```

Host không trực tiếp đưa DB credentials, file descriptors, process handles hoặc host internals cho worker nếu không cần thiết. Hãy cho worker biết **chỉ thông tin và thao tác cần dùng**. Một plugin xử lý ảnh chẳng hạn có thể nhận bytes qua IPC rồi trả ảnh đã xử lý, không cần quyền đọc toàn bộ thư mục cấu hình host.

Các lớp kiểm soát nên cân nhắc:

| Ranh giới/kiểm soát | Mục tiêu |
| --- | --- |
| Process riêng | Worker crash/`System.exit` không trực tiếp dừng JVM của host. |
| OS user/account riêng | File permissions giới hạn worker khỏi dữ liệu host. |
| Read-only/masked mounts | Ngăn sửa/đọc các đường dẫn không cần thiết. |
| Network namespace / egress rules | Ngăn kết nối ngoài mục đích, giảm exfiltration. |
| CPU/memory/process limits | Giảm DoS do vòng lặp hoặc cấp phát vô hạn. |
| Wall-clock timeout + kill process | Có thể kết thúc worker không hợp tác; thread interrupt cùng JVM yếu hơn. |
| IPC validation + authorization | Không cho worker gọi host operation ngoài quyền business. |
| Logs, audit, update policy | Quan sát hành vi, gỡ lỗi, rollback khi artifact lỗi. |

**Chú ý:** chỉ tách process mà vẫn chạy cùng OS account có toàn quyền đọc host secrets thì isolation vẫn có lỗ hổng. Container “mặc định” cũng không bảo đảm an toàn khi được cấp host mounts rộng, privileged mode hoặc network mở. Thiết kế phải dựa trên threat model và cấu hình thật.

Một số hệ cần mức cô lập cao hơn: microVM/hypervisor, dedicated machine, sandbox chuyên dụng hoặc managed execution service. ClassLoader vẫn có thể dùng **bên trong worker process** để hỗ trợ tổ chức dependencies, nhưng boundary chống mã độc nằm ở lớp khác.

## 12. Rủi ro cung cấp dữ liệu và xác thực plugin

**Nguồn đáng tin không có nghĩa code không lỗi.** Một plugin có chữ ký hợp lệ có thể chứa bug logic, lỗi dependency hoặc hành vi không phù hợp. Chữ ký/hash có mục đích xác minh artifact đã được phân phối như mong đợi, không tự giới hạn quyền runtime.

Pipeline tải plugin đáng tin cậy có thể gồm:

- Chỉ chấp nhận artifacts từ repository/nhà cung cấp đã phê duyệt.
- Chốt dependency versions, kiểm tra checksum/signatures theo chain of trust phù hợp.
- Quét lỗi/phụ thuộc dễ bị tấn công và ký artifact trong supply-chain pipeline.
- Validate plugin manifest, declared capabilities, supported API version.
- Dùng allowlist packages/modules/entrypoints để tránh load nhầm implementation.
- Tạo loader mới cho một generation; không thêm JAR tùy ý vào system loader global.
- Quản lý rollback nếu plugin gây lỗi.

Các bước này giảm rủi ro **nguồn cung cấp và correctness**, nhưng **không chuyển ClassLoader thành sandbox** khi một artifact độc hại vẫn lọt qua. Không coi `CodeSource.location` do custom loader tự gán là bằng chứng xác thực.

## 13. Sai lầm phổ biến và cách sửa

| Nhận định sai | Vì sao sai | Phương án đúng |
| --- | --- | --- |
| “Plugin có ClassLoader riêng nên không thể gọi `Files`.” | `Files` thuộc JDK, vẫn được dùng theo quyền process/module. | Giới hạn qua OS/process boundary. |
| “Parent = null nghĩa không thấy Java core.” | Bootstrap classes vẫn có thể được truy cập. | Hiểu delegation; không dùng parent null làm sandbox. |
| “Trả `new Permissions()` nghĩa không có quyền OS.” | PermissionCollection không được enforce khi không có Security Manager. | Không dựa vào legacy policy để chặn I/O. |
| “`SecureClassLoader` chắc chắn an toàn vì chữ Secure.” | Nó hỗ trợ metadata domain, không phải security boundary hiện đại. | Dùng cho source/class-loading metadata; sandbox ở process/OS. |
| “`CodeSource` URL là bằng chứng chữ ký hợp lệ.” | Metadata có thể được gán thủ công. | Verify artifact/signatures từ nguồn thực. |
| “`module-info.java` không export package nên plugin không thể đọc file.” | JPMS kiểm soát package/module access, không phải OS filesystem. | Phân biệt encapsulation với capability enforcement. |
| “Không truyền DB client reference cho plugin là đủ.” | Plugin có thể đọc env/config hoặc tự dùng network API nếu được phép. | Tách credentials và process permissions; IPC kiểm soát. |
| “`URLClassLoader.close()` kill plugin.” | Close chỉ xử lý loader resources theo contract, không terminate threads/process. | Lifecycle shutdown và process termination độc lập. |
| “Catch `Throwable` quanh plugin bảo vệ host hoàn toàn.” | Không ngăn resource exhaustion, state mutation hay `System.exit`. | Process isolation và quota. |
| “Security Manager còn bật được trên JDK 24 bằng flag cũ.” | JEP 486 đã vô hiệu hóa vĩnh viễn. | Migration sang cơ chế khác. |
| “Chỉ dùng `Thread.interrupt()` để bắt plugin dừng.” | Code có thể không hợp tác hoặc không kiểm tra interrupt. | Timeout/kill worker process và limits. |
| “Chỉ scan bytecode là sandbox.” | Static scan/allowlist có thể bỏ sót dynamic behavior; không phải enforcement chung. | Kết hợp provenance, validation và sandbox cấp hệ thống. |

## 14. Checklist trước khi triển khai hệ plugin

**Đối với plugin đáng tin:**

1. Xác định package/API nào phải được host parent loader định nghĩa.
2. Đảm bảo plugin không mang bản duplicate của host interface.
3. Chọn đúng URLClassLoader/custom loader, nguồn class và resource.
4. Xử lý phiên bản, dependency conflicts, ServiceLoader/TCCL nếu có.
5. Xác minh artifact provenance phù hợp nhu cầu.
6. Có lifecycle quản lý threads, callbacks, streams, loaders và references.
7. Test `ClassCastException`, `ClassNotFoundException`, `LinkageError` và upgrade scenario.

**Đối với plugin không tin cậy, bắt buộc xem xét thêm:**

1. Ranh giới process/machine và OS identity riêng.
2. Quyền filesystem/network tối thiểu, không mount host secrets.
3. CPU/memory/thread/process limits, deadline và kill policy.
4. IPC protocol có schema, validation, authn/authz và payload limits.
5. Secrets chỉ nằm ở host trusted side khi có thể.
6. Logging, audit trail, sandbox escape threat review và updates.
7. Mô hình độ tin cậy nêu rõ loại code nào được phép vào mỗi execution tier.

Một yêu cầu “cấm plugin đọc `/etc`” phải được kiểm thử ở **filesystem/OS restriction**, không thể chứng minh bằng việc tạo custom ClassLoader rồi thấy package không có trên classpath.

## 15. Câu hỏi tự kiểm tra

1. **ClassLoader có tạo ra một OS process mới không?**  
   Không. Class được định nghĩa bởi loader khác vẫn chạy trong JVM process hiện tại.

2. **Hai loaders định nghĩa cùng `com.example.Widget` có chung runtime class không?**  
   Không, nếu defining loader khác nhau thì class identity khác nhau dù binary name trùng.

3. **Vì sao parent delegation không ngăn plugin gọi `java.nio.file.Files`?**  
   Delegation tìm và chia sẻ các lớp Java runtime; nó không cài permissions hạn chế hành vi của bytecode.

4. **`ProtectionDomain.getPermissions()` không implies `FilePermission(read)` thì `Files.readString` luôn bị từ chối?**  
   Không. Khi không có Security Manager, collection đó không tự tạo enforcement. Demo kiểm chứng điều này trên JDK 24.

5. **Từ bản Java nào Security Manager bị vô hiệu hóa vĩnh viễn?**  
   JDK 24 (JEP 486), sau giai đoạn deprecated for removal từ Java 17 (JEP 411).

6. **Một JAR được ký hợp lệ có nghĩa plugin bị giới hạn network không?**  
   Không. Signing liên quan provenance/integrity, không phải giới hạn quyền hệ điều hành.

7. **Named modules với `exports`/`opens` có bảo đảm chống plugin đọc file không?**  
   Không. Chúng kiểm soát truy cập package và reflection, không phải policy file/network.

8. **`URLClassLoader.close()` có dừng threads của plugin không?**  
   Không. Thực thi plugin và lifecycle threads cần cơ chế riêng.

9. **Nếu plugin độc hại cần xử lý dữ liệu nhưng không được truy cập host secrets, kiến trúc hợp lý là gì?**  
   Worker process riêng, OS identity/rights giới hạn, IPC được kiểm soát, không truyền secrets vô cớ.

10. **Tại sao plugin API chỉ có `getPublicGreeting` không phải sandbox đủ mạnh?**  
    Plugin bytecode có thể gọi trực tiếp JDK APIs mà không đi qua API wrapper.

11. **Nếu hai plugin tin cậy cần hai version thư viện khác nhau thì dùng gì?**  
    Separate class loader namespaces, chia sẻ đúng API qua parent, quản lý lifecycle.

12. **Tài liệu nào giải thích trạng thái Security Manager mới?**  
    JEP 486 và Oracle Java SE 24 Security Developer's Guide; xem mục 16.

## 16. Tài liệu tham khảo chính thức

- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): defining loader, `loadClass`, `defineClass`, delegation, protection domain.
- [Java SE 25 — SecureClassLoader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/SecureClassLoader.html): `CodeSource`, `getPermissions`, API Note về permissions khi Security Manager không còn.
- [Java SE 21 — CodeSource](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/CodeSource.html): location và certificates/signers.
- [Java SE 21 — ProtectionDomain](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/ProtectionDomain.html): metadata domain và tập permissions.
- [JEP 411 — Deprecate the Security Manager for Removal](https://openjdk.org/jeps/411): lịch sử Java 17.
- [JEP 486 — Permanently Disable the Security Manager](https://openjdk.org/jeps/486): thay đổi trong JDK 24.
- [Oracle Java SE 24 — The Security Manager Is Permanently Disabled](https://docs.oracle.com/en/java/javase/24/security/security-manager-is-permanently-disabled.html): hành vi `System`, `Policy`, `AccessController` và khuyến nghị migration.
- [Oracle Secure Coding Guidelines for Java SE](https://www.oracle.com/java/technologies/javase/seccodeguide.html): hạn chế isolation trong cùng process và khuyến nghị separate processes/OS-level controls cho code không tin cậy.
- [JVMS 5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): runtime type identity theo binary name và defining loader.

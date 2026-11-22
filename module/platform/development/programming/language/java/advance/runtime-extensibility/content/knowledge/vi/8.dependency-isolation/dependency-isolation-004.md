# Ưu tiên loader cha hoặc plugin và các ngoại lệ phải ủy quyền

## 1. Bài toán cô lập phụ thuộc của plugin Java

Giả sử ứng dụng host và một plugin cùng cần lớp có tên `com.acme.lib.Parser`, nhưng host đóng gói thư viện phiên bản 1 trong khi plugin cần phiên bản 2. Hai phiên bản có thể khác chữ ký method, behavior hoặc dependency. Một `ClassLoader` được đặt giữa host và plugin có thể cho phép mỗi phía dùng bản của mình, nhưng quyết định **nạp từ cha trước (parent-first)** hay **nạp từ plugin trước (plugin-first/child-first)** làm thay đổi phiên bản nào được chọn.

Còn có một giới hạn ngược lại: interface SPI và các kiểu dữ liệu dùng để giao tiếp giữa host với plugin **phải có danh tính Java thống nhất**. Nếu host nạp `com.acme.api.Plugin` bằng class loader A còn plugin nạp *bản sao cùng tên* bằng class loader B, hai `Class<?>` không trở thành một kiểu chỉ vì tên giống nhau. Trong Java, danh tính của một class gắn với **tên nhị phân và defining class loader**; hai lớp có tên y hệt do hai loader khác nhau định nghĩa là hai runtime type khác nhau.

Vì vậy, thiết kế class loading cho hệ thống mở rộng thường kết hợp:

- **Parent-first** cho những lớp thuộc host, JDK và hợp đồng giao tiếp được chia sẻ.
- **Plugin-first** cho mã implementation và các dependency riêng mà plugin sở hữu, khi có nhu cầu tránh xung đột phiên bản.
- **Ngoại lệ bắt buộc ủy quyền cho cha** ngay cả trong chính sách plugin-first, nhất là API/SPI mà host và plugin cùng trao đổi.

Đích đến không chỉ là “plugin load được class”; host còn phải cast, gọi API, nhận callback, truyền DTO, đăng ký `ServiceLoader` và xử lý exception qua ranh giới một cách nhất quán.

## 2. Cơ chế ủy quyền class loader

### 2.1. Parent-first là hành vi mặc định của ClassLoader

`ClassLoader.loadClass(String)` theo implementation chuẩn ưu tiên theo trình tự:

1. Kiểm tra `findLoadedClass(name)`: lớp đã được **loader hiện tại** nạp/định nghĩa chưa?
2. Ủy quyền cho **parent loader** (hoặc bootstrap khi không có parent).
3. Nếu cha không tìm được, thử `findClass(name)` tại loader hiện tại.
4. Nếu không tìm được ở đâu, báo `ClassNotFoundException`.

Trong `loadClass(name, resolve)`, tham số `resolve` quyết định có gọi `resolveClass` hay không sau khi xác định class. Không nên bỏ qua bước kiểm tra cache và cơ chế đồng bộ khi tự viết thuật toán ưu tiên khác.

`URLClassLoader` cũng theo delegation mặc định này. Tạo một `URLClassLoader` trỏ tới plugin JAR **chưa đủ** để tách version khi cha đã thấy một class cùng tên: nếu cha tìm thấy trước, class của plugin có thể không được chọn.

```text
Parent-first khi yêu cầu tên com.acme.lib.Parser

pluginLoader.loadClass("com.acme.lib.Parser")
    |
    +-- đã nạp bởi pluginLoader? -- có --> dùng lại
    |
    +-- hỏi host/parent ------------ có --> lấy class do parent tìm thấy
    |
    +-- parent không tìm được ----------> pluginLoader.findClass(...)
```

### 2.2. Plugin-first đổi thứ tự cho một nhóm class

Với nhóm tên mà plugin sở hữu, một loader tùy biến có thể thử `findClass(name)` từ JAR/thư mục của plugin **trước** khi ủy quyền cho parent. Khi plugin có bản riêng của thư viện, class của plugin sẽ thắng; khi plugin không có, vẫn có thể fallback về parent.

```text
Plugin-first cho tên com.acme.plugin.lib.Parser

pluginLoader.loadClass("com.acme.plugin.lib.Parser")
    |
    +-- đã nạp? ----------------------- có --> dùng lại
    |
    +-- có class trong plugin? -------- có --> define class của plugin
    |
    +-- plugin không tìm thấy -------------> thử host/parent
```

**Chính sách nên áp theo nhóm tên có chủ sở hữu**, không theo khẩu hiệu “tất cả child-first”. Trong cùng một loader, cách phân loại thường được quyết định trước khi `loadClass`; không để kết quả phụ thuộc vào thời điểm plugin được khởi tạo.

### 2.3. “Loading” không đồng nghĩa “Defining”

Loader nhận yêu cầu có thể **trả về class do parent định nghĩa**; lớp không nhất thiết được định nghĩa bởi loader nhận lời gọi. Điều này giải thích vì sao ta có thể có một `PluginLoader` riêng nhưng `api.Plugin.class.getClassLoader()` vẫn là host loader.

Thông tin hữu ích khi chẩn đoán:

- `type.getName()`: tên class.
- `type.getClassLoader()`: defining class loader (có thể là `null` cho lớp do bootstrap định nghĩa).
- `type.getModule()`: module chứa class khi dùng Java 9+.
- `loader.getParent()`: cấu trúc cha của loader; không đồng nghĩa mọi lớp đi qua cha đều thuộc cùng một JAR.

Thứ tự class loading ảnh hưởng tới identity, linking, package access và tầm nhìn của thư viện; nó không tự thay đổi chữ ký Java hay chuyển đổi một đối tượng thuộc hai định nghĩa class khác nhau thành compatible.

## 3. Chọn parent-first hay plugin-first theo trường hợp

| Trường hợp | Ưu tiên hợp lý | Lý do |
| --- | --- | --- |
| API/SPI host–plugin (interface, DTO, exception dùng chung) | **Parent-first bắt buộc theo hợp đồng** | Giữ một runtime type để cast/gọi callback |
| Lớp nền tảng Java (`java.*`) | **Ủy quyền cho Java platform/parent** | Không định nghĩa lại lớp nền tảng; JVM ngăn class loader thông thường định nghĩa tên thuộc `java.*` |
| Runtime bridge, giao diện framework do host quản lý và đi qua ranh giới | Thường **parent-first** | Tránh hai bản khác danh tính cho cùng hợp đồng |
| Implementation riêng của plugin | Plugin loader định nghĩa (plugin-first hoặc parent fallback khi cha không có) | Mã plugin thuộc vòng đời riêng |
| Dependency private có version khác host | **Plugin-first** khi policy cho phép | Tránh ép plugin dùng version của host |
| Dependency phải thực sự dùng chung một instance/type với host | **Parent-first** | Giữ hợp đồng, class identity, object model và lifecycle thống nhất |
| Thư viện chỉ có một bản, không vượt ranh giới và không có xung đột | Có thể parent-first | Đơn giản hơn nếu chiến lược deploy cho phép |
| Cấu hình/resource, `META-INF/services` | **Chính sách tìm resource riêng** | `getResource(s)` và `ServiceLoader` không nhất thiết dùng cùng thứ tự như `loadClass` |

Parent-first không tự động sai: nó giảm việc tải trùng class, phù hợp cho các API do host kiểm soát và đơn giản hơn trong ứng dụng một classpath. Plugin-first cũng không phải mặc định an toàn hơn: nó có thể tạo hai định nghĩa API và gây `ClassCastException` hoặc `ServiceConfigurationError`.

Nguyên tắc quyết định là: **lớp nào cần cùng danh tính ở hai phía, lớp nào phải được cô lập về version, và lớp nào host sở hữu vòng đời**.

## 4. Các ngoại lệ phải ủy quyền khi thiết kế plugin-first

### 4.1. Lớp Java platform và các namespace bị bảo vệ

Không thử nạp/định nghĩa bản sao lớp JDK để ghi đè hành vi nền tảng. Với `java.*`, loader tùy biến phải ủy quyền; JVM còn hạn chế việc một class loader thông thường định nghĩa class có tên bắt đầu bằng `java.`. Các package khác thuộc platform có thể nằm trong module như `java.base`, `java.sql`, `java.logging`, `java.xml`, hoặc có tên `javax.*`/`jdk.*`; hãy phân loại theo module/runtime thực tế và chính sách host.

Không áp dụng máy móc “mọi `javax.*` và `jakarta.*` đều là JDK”:

- `jakarta.*` thường là thư viện/framework bên ngoài JDK; khi contract `jakarta.servlet.*` hoặc `jakarta.validation.*` đi qua boundary, host nên chỉ định bản dùng chung.
- Một dependency private có namespace `javax.*` có thể là thư viện ngoài platform; chính sách phải dựa trên **quyền sở hữu và contract**, không chỉ một prefix đoán mò.
- Với API Java tiêu chuẩn, vẫn cần cho lớp được nạp từ platform/parent thay vì shadow bằng copy trong plugin.

### 4.2. Host API/SPI và kiểu giao tiếp

Giả sử host định nghĩa:

```java
package com.acme.api;

public interface Plugin {
    Result execute(Request request);
}
```

Đây là **đoạn interface minh họa**; `Request` và `Result` cũng thuộc API chung, không phải các lớp có sẵn trong JDK. Nếu plugin bundle bản riêng của `Plugin` hoặc `Request`, host có thể nhìn thấy đối tượng “implements Plugin” trong source nhưng vẫn thất bại tại runtime. Phải **ủy quyền toàn bộ những kiểu Java có thể xuất hiện qua biên**, gồm:

- Interface/abstract class SPI và base class.
- DTO, enum, record, generic bound, exception và annotation mà host/plugin dùng chung.
- Callback/listener, service contract, event type và những loại xuất hiện trong chữ ký method.
- Các API phụ trợ mà những kiểu trên trực tiếp tham chiếu và thực sự thuộc hợp đồng chung.

Không chỉ liệt kê một interface chính rồi quên các kiểu phụ. Một `Plugin.execute(Request)` chỉ ổn nếu cả `Plugin` lẫn `Request` có cùng runtime identity ở phía host và plugin.

Cách đóng gói phù hợp là host cung cấp một **API JAR dùng chung**; plugin biên dịch dựa vào API này nhưng khi chạy không tự định nghĩa bản thứ hai. Có thể khai báo dependency theo kiểu `compileOnly`/`provided` (tùy build tool), kiểm soát nội dung JAR lúc package, và dùng delegation exception cho namespace API.

**Quan trọng:** parent-first chỉ ưu tiên cha; nếu cha không có API, implementation mặc định có thể fallback về bản copy trong plugin. Hệ thống nên **xác thực trước rằng contract bắt buộc có ở parent** và từ chối plugin thiếu điều kiện, thay vì im lặng chấp nhận một định nghĩa API riêng.

### 4.3. Các bridge dùng chung do host quản lý

Tùy kiến trúc, những API như logging facade, tracing/metrics API, dependency injection extension contract hoặc transaction callback cũng có thể cần dùng chung. Ví dụ host và plugin cùng truyền `org.slf4j.Logger` hoặc đăng ký một framework callback được host tiêu thụ: những interface xuất hiện ở cả hai phía nên có một định nghĩa nhất quán. Phần implementation/backend bên trong plugin lại có thể cần tách riêng.

Đừng đưa mọi thư viện framework vào danh sách parent-first chỉ vì tên quen thuộc. Hãy hỏi:

1. Có **đối tượng thuộc kiểu này** đi qua ranh giới host–plugin không?
2. Ai quản lý lifecycle/registry của kiểu đó?
3. Bản ABI và version nào host cam kết cấp?
4. Dependency transitive nào bắt buộc cùng identity để không bị lỗi linking?

Nếu câu trả lời chỉ là “plugin tự dùng thư viện ở bên trong”, plugin-first có thể phù hợp hơn.

## 5. Viết chính sách loadClass đúng và tránh fallback sai

Một quyết định thực tế có thể mô tả bằng bảng policy:

| Nhóm class | Quy tắc | Khi thiếu |
| --- | --- | --- |
| `java.*` và platform classes | Parent/platform first | Fail nếu platform không có |
| `com.acme.api.*` (contract dùng chung) | **Chỉ lấy class từ parent đã xác thực** | Báo thiếu shared API; không dùng copy plugin |
| `com.acme.plugin.*` | Tìm tại plugin trước | Có thể fail-fast nếu đây phải là implementation nội bộ |
| `com.acme.vendor.private.*` | Plugin-first; fallback theo chính sách explicit | Tránh vô tình lấy host version không compatible |
| Những package khác | Parent-first theo mặc định, nếu policy chưa cho phép isolate | Tránh shadow class không được khai báo |

Đây là policy **minh họa**. Tên package là quy ước của từng hệ thống, không phải danh sách có sẵn trong `ClassLoader`.

Pseudocode của một loader có ngoại lệ:

```text
loadClass(name, resolve):
    lock theo tên class nếu loader hỗ trợ khóa song song
    if findLoadedClass(name) != null: return class đã nạp

    if isPlatform(name):
        result = delegateToParent(name)
    else if isSharedHostApi(name):
        result = delegateToParentStrictly(name)
        # không fallback sang plugin nếu API bắt buộc thiếu
    else if isPluginOwned(name):
        result = findClassInPlugin(name)
        # fallback sang parent chỉ nếu policy cho phép và class không có tại plugin
    else:
        result = delegateToParentThenFindLocal(name)

    if resolve: resolveClass(result)
    return result
```

Khi tự implement `loadClass(String, boolean)`:

- Luôn kiểm tra `findLoadedClass` trước để tránh định nghĩa lại một class trong cùng loader.
- Dùng `synchronized (getClassLoadingLock(name))` hoặc cơ chế tương đương để xử lý concurrent load; đặc tính parallel-capable của subclass cần được hiểu rõ.
- Chỉ fallback parent khi `findClass` ném **`ClassNotFoundException`** cho class vắng mặt. Không nuốt `LinkageError`, `SecurityException` hoặc lỗi verify/init thực sự để thử một version khác âm thầm.
- Tôn trọng `resolveClass` theo tham số `resolve`.
- Gọi `super.loadClass(name, false)` trong một class loader kế thừa có thể thực hiện **parent-first rồi tìm tại loader hiện tại**. Nếu cần chế độ **chỉ parent** cho API chung, gọi `getParent().loadClass(name)` với xử lý bootstrap và xác thực rõ, tránh dùng fallback local không mong muốn.
- Chọn các prefix chuẩn xác; `name.startsWith("com.acme.api.")` khác với `name.startsWith("com.acme.api")`, vì dạng thiếu dấu chấm có thể khớp nhầm `com.acme.application.*`. Khi có class `com.acme.api` chính nó, cần xử lý tên chính xác nếu policy yêu cầu.
- Class đã nạp không tự chuyển sang loader khác khi sửa policy hoặc thay JAR. Muốn nâng cấp plugin độc lập thường phải tạo **loader mới** và giải phóng mọi tham chiếu đến loader cũ.

Nếu cần cô lập mạnh, một loader riêng cho **mỗi plugin** phù hợp hơn một loader chung cho tất cả plugin: hai plugin khi đó có thể dùng hai phiên bản `com.vendor.Json` mà không giẫm lên nhau. Host phải kiểm tra không để kiểu private của plugin A tràn trực tiếp vào API của plugin B.

## 6. Ví dụ Java 17+ chạy được: parent-first, plugin-first và ngoại lệ API

Ví dụ sau chạy bằng **một file duy nhất**, tự tạo hai tập class độc lập trong thư mục tạm rồi biên dịch bằng `JavaCompiler` của JDK:

- **Host classes** có `demo.api.Greeting` và `demo.lib.Message` trả `host-library`.
- **Plugin classes** cũng có bản sao `demo.api.Greeting` và một `demo.lib.Message` khác trả `plugin-library`, cùng `demo.plugin.Hello` sử dụng chúng.
- Một `PluginLoader` thử parent hoặc plugin trước theo policy. Với `delegateSharedApi=true`, namespace `demo.api.*` luôn được ủy quyền cho host. Trường hợp cuối cố tình bỏ ngoại lệ này để chứng minh rủi ro.

Tệp **`DelegationPolicyDemo.java`**:

```java
import java.io.IOException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public class DelegationPolicyDemo {
    static final class PluginLoader extends URLClassLoader {
        private final boolean pluginFirst;
        private final boolean delegateSharedApi;

        PluginLoader(Path pluginClasses, ClassLoader parent,
                     boolean pluginFirst, boolean delegateSharedApi)
                throws IOException {
            super(new URL[]{pluginClasses.toUri().toURL()}, parent);
            this.pluginFirst = pluginFirst;
            this.delegateSharedApi = delegateSharedApi;
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            synchronized (getClassLoadingLock(name)) {
                Class<?> type = findLoadedClass(name);
                if (type == null) {
                    boolean alwaysParent =
                            name.startsWith("java.")
                            || (delegateSharedApi
                                && name.startsWith("demo.api."));
                    if (alwaysParent || !pluginFirst) {
                        type = super.loadClass(name, false);
                    } else {
                        try {
                            type = findClass(name);
                        } catch (ClassNotFoundException notInPlugin) {
                            type = super.loadClass(name, false);
                        }
                    }
                }
                if (resolve) {
                    resolveClass(type);
                }
                return type;
            }
        }
    }

    static Path source(Path root, String relative, String code)
            throws IOException {
        Path file = root.resolve(relative);
        Files.createDirectories(file.getParent());
        Files.writeString(file, code, StandardCharsets.UTF_8);
        return file;
    }

    static void compile(JavaCompiler compiler, Path output,
                        Path... files) throws IOException {
        Files.createDirectories(output);
        List<String> args = new ArrayList<>(
                List.of("--release", "17", "-encoding", "UTF-8",
                        "-d", output.toString()));
        for (Path file : files) {
            args.add(file.toString());
        }
        if (compiler.run(null, null, null,
                args.toArray(String[]::new)) != 0) {
            throw new IllegalStateException("Compilation failed");
        }
    }

    static Object instance(ClassLoader loader) throws Exception {
        return Class.forName("demo.plugin.Hello", true, loader)
                .getDeclaredConstructor().newInstance();
    }

    static String message(Object provider) throws Exception {
        return (String) provider.getClass()
                .getMethod("message").invoke(provider);
    }

    static void deleteTree(Path root) throws IOException {
        try (Stream<Path> paths = Files.walk(root)) {
            for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                Files.deleteIfExists(path);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Run with a JDK, not a JRE");
        }
        Path root = Files.createTempDirectory("delegation-demo-");
        try {
            Path hostSrc = root.resolve("host-src");
            Path pluginSrc = root.resolve("plugin-src");
            Path hostClasses = root.resolve("host-classes");
            Path pluginClasses = root.resolve("plugin-classes");
            Path hostApi = source(hostSrc, "demo/api/Greeting.java",
                    "package demo.api; public interface Greeting { String message(); }");
            Path hostLib = source(hostSrc, "demo/lib/Message.java",
                    "package demo.lib; public class Message { "
                    + "public static String value() { return \"host-library\"; } }");
            Path pluginApi = source(pluginSrc, "demo/api/Greeting.java",
                    "package demo.api; public interface Greeting { String message(); }");
            Path pluginLib = source(pluginSrc, "demo/lib/Message.java",
                    "package demo.lib; public class Message { "
                    + "public static String value() { return \"plugin-library\"; } }");
            Path pluginImpl = source(pluginSrc, "demo/plugin/Hello.java",
                    "package demo.plugin; public class Hello "
                    + "implements demo.api.Greeting { "
                    + "public String message() { return demo.lib.Message.value(); } }");

            compile(compiler, hostClasses, hostApi, hostLib);
            compile(compiler, pluginClasses, pluginApi, pluginLib, pluginImpl);

            try (URLClassLoader host = new URLClassLoader(
                        new URL[]{hostClasses.toUri().toURL()},
                        ClassLoader.getPlatformClassLoader());
                 PluginLoader parentFirst =
                        new PluginLoader(pluginClasses, host, false, true);
                 PluginLoader pluginFirst =
                        new PluginLoader(pluginClasses, host, true, true);
                 PluginLoader noException =
                        new PluginLoader(pluginClasses, host, true, false)) {

                Class<?> sharedApi = host.loadClass("demo.api.Greeting");
                Object first = instance(parentFirst);
                Object second = instance(pluginFirst);
                Object broken = instance(noException);

                System.out.println("parent-first: " + message(first));
                System.out.println("plugin-first: " + message(second));
                System.out.println("shared API: " + sharedApi.isInstance(second));
                System.out.println("no API exception: " + sharedApi.isInstance(broken));
            }
        } finally {
            deleteTree(root);
        }
    }
}
```

Biên dịch và chạy trên **JDK 17 hoặc mới hơn** (máy cần có `javac` và `java`):

```bash
javac --release 17 DelegationPolicyDemo.java
java DelegationPolicyDemo
```

Đầu ra chính xác (đã kiểm tra bằng biên dịch và chạy thực tế):

```text
parent-first: host-library
plugin-first: plugin-library
shared API: true
no API exception: false
```

Giải thích từng dòng:

1. `parent-first`: host đã có `demo.lib.Message` nên loader của plugin nhận class do host định nghĩa; code `Hello` in kết quả từ thư viện host.
2. `plugin-first`: loader của plugin tự tìm `demo.lib.Message` ở kho bytecode plugin trước; vì vậy dùng bản plugin.
3. `shared API: true`: dù `Hello` và private library có thể được nạp từ plugin, `demo.api.Greeting` được ủy quyền về host, nên host nhận ra instance là một implementation của **chính kiểu host**.
4. `no API exception: false`: plugin có bản sao `demo.api.Greeting` và loader nạp bản đó trước; host kiểm tra `isInstance` với interface của host thì thất bại. Một phép cast tương đương có thể gây `ClassCastException`.

Ví dụ **cố ý** đưa cùng API vào hai bộ class để minh họa lỗi; hệ thống production nên bỏ bản copy API khỏi runtime plugin nếu host cấp API. Trong demo, ngoại lệ `demo.api.*` là policy parent-first đơn giản, **không phải chế độ parent-only nghiêm ngặt** nếu host không có API: `super.loadClass` vẫn có thể fallback sang class của plugin. Với một shared API bắt buộc, hệ thống thực phải kiểm tra API đã tồn tại ở host và từ chối fallback sai.

Cũng lưu ý đây là demo dùng classpath và `URLClassLoader` để tập trung vào **thứ tự tìm class**; nó không mô phỏng toàn bộ quản lý module JPMS, chữ ký artifact, sandbox hay hot-reload production. `JavaCompiler` biên dịch các source tạm tại runtime chỉ để tạo hai bộ class có cùng tên nhưng nội dung khác nhau; khi triển khai thật, các bộ class thường đã được build thành JAR độc lập.

## 7. Đừng nhầm cơ chế nạp class với cơ chế tìm resource

`ClassLoader.loadClass(...)` và `getResource(...)` / `getResources(...)` là **hai nhóm hành vi riêng**. Đổi sang plugin-first trong `loadClass` không tự động khiến:

- `getResource("config.yml")` chọn bản của plugin trước.
- `getResources("META-INF/services/...")` trả đúng các descriptor cần thiết từ host và plugin.
- `ServiceLoader` khám phá đúng provider trong mọi class loader hoặc module layer.
- Một framework đang dùng **thread context class loader (TCCL)** tự chuyển sang plugin loader.

`URLClassLoader` mặc định đi theo cơ chế tìm resource được kế thừa; nếu kiến trúc muốn resource plugin override host, cần thiết kế **chính sách resource lookup riêng**, kiểm soát cả kết quả đơn và nhiều kết quả, cùng thứ tự/duplicate.

Đặc biệt, nhiều plugin sử dụng `META-INF/services`. Việc “plugin-first resources” bỏ qua danh sách provider của parent hoặc gộp trùng bất cẩn có thể làm plugin không được phát hiện, provider API bị lỗi identity, hoặc `ServiceConfigurationError` xuất hiện khi khởi tạo. Không nên áp dụng chung chính sách override resource cho mọi path; tệp cấu hình riêng plugin và service declaration có thể cần hai quy tắc khác nhau.

### 7.1. ServiceLoader và shared SPI

Khi host nạp provider:

```java
ServiceLoader<MySpi> providers =
        ServiceLoader.load(MySpi.class, pluginLoader);
```

Đây là **mã minh họa tích hợp**, trong đó `MySpi` là kiểu do host định nghĩa và `pluginLoader` là loader đang quản lý artifact plugin. `ServiceLoader` yêu cầu provider thực sự phù hợp với `MySpi`. Nếu plugin-first định nghĩa bản sao của `MySpi`, provider có thể không assignable và quá trình tìm/khởi tạo có thể thất bại với `ServiceConfigurationError`.

Chọn loader rõ ràng giúp tránh tình huống tìm provider bằng một loader nhưng SPI lại được nạp bằng loader khác. Với overload `ServiceLoader.load(MySpi.class)`, Java dùng **thread context class loader** hiện tại; vì vậy thay đổi TCCL có thể ảnh hưởng đường khám phá, dù chính `MySpi.class` vẫn thuộc host.

### 7.2. TCCL phải được khôi phục

Một số framework/JDK API tìm class hoặc resource qua `Thread.currentThread().getContextClassLoader()`, không đi thẳng qua loader đã tạo đối tượng plugin. Nếu bắt buộc tạm đặt TCCL để gọi plugin, hãy khôi phục trong `finally`:

```java
Thread thread = Thread.currentThread();
ClassLoader original = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    // Gọi code/plugin framework cần TCCL ở đây.
    invokePlugin();
} finally {
    thread.setContextClassLoader(original);
}
```

Đây là **mã minh họa tích hợp**, cần `pluginLoader` và `invokePlugin()` do ứng dụng cung cấp. Không giữ TCCL của plugin trên thread pool sau khi trả request: điều đó có thể khiến các tác vụ khác nhìn nhầm dependency của plugin, rò rỉ class loader và cản trở unload. Cần truyền/khôi phục context có chủ đích trong tác vụ bất đồng bộ theo đúng contract; chỉ đặt TCCL cho một thread không tự động đổi toàn bộ luồng thực thi khác.

## 8. Lỗi thường gặp do chọn thứ tự hoặc ngoại lệ sai

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra và sửa |
| --- | --- | --- |
| Plugin gọi method mới nhưng gặp `NoSuchMethodError` | Parent-first lấy nhầm bản lib cũ của host | Kiểm tra defining loader và version; cho phép plugin-first ở dependency private |
| `ClassCastException` dù hai tên class giống nhau | Host và plugin định nghĩa cùng API/SPI | Chia sẻ API ở parent và ủy quyền bắt buộc; kiểm tra `getClassLoader()` |
| `ServiceConfigurationError` khi khám phá provider | Provider có thể implement bản SPI riêng; metadata/resource có thể sai | Kiểm tra service class identity, loader, descriptor và root cause |
| `NoClassDefFoundError` khi chạy | Thiếu dependency transitive hoặc lỗi khởi tạo trước đó | Xem cause chain, closure dependency và layer/classpath thực |
| `LinkageError`, `loader constraint violation` | Các class cùng tham gia chữ ký runtime không có identity tương thích | Kiểm tra delegation của mọi kiểu đi qua biên |
| Plugin tải được nhưng callback không được đăng ký | Host registry mong đợi interface/class do host định nghĩa | Cùng SPI và event/annotation contract phải dùng shared class |
| Thư viện plugin vô tình thay class/framework chung | Plugin-first quá rộng | Giới hạn namespace private và ngoại lệ shared |
| Plugin không thấy resource/provider | Chỉ override `loadClass` nhưng resource lookup/TCCL khác | Kiểm tra `getResources`, `ServiceLoader` và TCCL |
| Plugin cũ không unload được | Static cache, thread, listener, TCCL giữ tham chiếu | Gỡ registration, đóng loader, chấm dứt task, dọn cache theo ownership |

**Đừng chữa `NoSuchMethodError` bằng cách đổi tất cả sang plugin-first**. Nếu method thuộc một DTO hoặc SPI đi qua boundary, tạo bản riêng có thể khiến lỗi chuyển thành `ClassCastException` hay `LinkageError`. Hãy xác định chính xác thư viện nào được phép private và thư viện nào bắt buộc shared.

Khi chẩn đoán, in loader của cả interface host và class implementation:

```java
System.out.println(MySpi.class.getClassLoader());
System.out.println(instance.getClass().getClassLoader());
System.out.println(MySpi.class.isInstance(instance));
```

Đây cũng là **đoạn minh họa tích hợp**. `instance` có thể thuộc plugin loader mà vẫn implement API do parent định nghĩa; điều quan trọng là class/interface trong chuỗi thừa kế và method signature có identity nhất quán.

## 9. Vận hành, version và giới hạn cô lập

### 9.1. Quy tắc version và phụ thuộc

- **Host API/SPI:** công bố version tương thích và kiểm tra khi plugin được nhận. Parent-first chỉ thống nhất type, không chứng minh ABI/behavior tương thích.
- **Dependency private:** đóng gói với plugin và cho phép plugin-first trong namespace đã chọn; tránh để class private xuất hiện trực tiếp trong method public của SPI.
- **Dependency shared:** host quyết định version, plugin khai báo khoảng version mình hỗ trợ và được kiểm thử với version host thực sự cấp.
- **Hai plugin khác nhau:** dùng loader riêng khi cần hai version private song song; tránh static singleton chung nếu không chủ đích chia sẻ.
- **Shading/relocation:** có thể giảm trùng tên package của dependency private, nhưng cần cập nhật resource như `META-INF/services`, reflection strings và serialization metadata nếu công cụ build không tự xử lý. Shading không thay thế chính sách shared SPI.

Một API đóng gói trùng trong plugin nên được phát hiện bằng kiểm tra build/deploy, chứ không chỉ trông cậy việc parent-first sẽ “che” bản copy.

### 9.2. JPMS và module layers

Trong Java 9+, có thể dùng `ModuleLayer` để triển khai module riêng cho plugin; service có thể được khai báo qua `provides ... with ...` và `uses` thay vì `META-INF/services`. Lúc đó class visibility còn do module resolution, readability, `exports` và `opens` quyết định. Không thể sửa một lỗi `module does not read` hoặc truy cập reflective bằng cách đảo thứ tự parent-first/child-first đơn thuần.

Một layer có thể gắn với một hay nhiều class loader tùy chiến lược định nghĩa; **class loader isolation** và **module encapsulation** là hai cơ chế liên quan nhưng không đồng nhất. Cần chọn `ServiceLoader.load(layer, service)` hoặc overload khác theo mô hình deployment và kiểm tra lại cả service identity.

### 9.3. Cô lập dependency không phải sandbox bảo mật

ClassLoader riêng chủ yếu hỗ trợ namespace, lifecycle và quản lý dependency. Nó **không tự ngăn** plugin đọc file, mở kết nối mạng, dùng reflection hay gọi API host công khai. Java Security Manager đã bị loại bỏ khỏi mô hình bảo vệ được khuyến nghị và không thể xem plugin-first là cơ chế sandbox cho code không tin cậy. Nếu cần ranh giới tin cậy mạnh, cân nhắc tiến trình riêng, quyền hệ điều hành, IPC, môi trường container hoặc cơ chế kiểm soát thích hợp.

### 9.4. Lifecycle và unload

Một class đã được JVM định nghĩa bởi loader cụ thể không thể “đổi chủ” khi thay policy. Muốn nạp plugin phiên bản mới, thường tạo loader/module layer mới, đăng ký provider mới, hủy listener/task/timer/thread của plugin cũ và bảo đảm không còn tham chiếu mạnh tới class/instance/loader cũ. Đóng `URLClassLoader` giải phóng tài nguyên mà nó quản lý nhưng **không bảo đảm ngay lập tức unload tất cả class** nếu còn tham chiếu khác.

## 10. Checklist kiểm thử trước khi phát hành plugin

1. **Parent-first baseline:** khi host và plugin cùng có một dependency, xác nhận version thực tế và defining loader là bản host.
2. **Plugin-first private dependency:** với hai version khác nhau, xác nhận plugin dùng bản của mình và host vẫn dùng bản host.
3. **API/SPI luôn shared:** kể cả plugin JAR vô tình chứa bản copy, `HostSpi.class.isInstance(provider)` phải đúng; trong production nên loại bản copy khỏi artifact.
4. **Bắt buộc có shared API tại parent:** thử host thiếu API và xác nhận bị từ chối, không fallback âm thầm sang bản plugin.
5. **Kiểu đi qua boundary:** thử các DTO, callback, exception, enum, annotation được dùng chung, không chỉ interface chính.
6. **Thiếu dependency hoặc lỗi linkage:** không bắt rồi fallback tùy tiện; giữ root cause và xác định artifact/class loader.
7. **Resource và ServiceLoader:** kiểm tra resource đơn, nhiều resource, service descriptor, TCCL và `ServiceConfigurationError` ở môi trường deploy thật.
8. **Nhiều plugin song song:** cùng tên thư viện nhưng khác version không xung đột giữa các loader.
9. **JPMS nếu áp dụng:** kiểm tra `uses`, `provides`, layer, `exports` và `opens`.
10. **Reload/unload:** bảo đảm không còn thread, TCCL, registry hoặc static cache của host tham chiếu plugin cũ.

**Nguyên tắc thiết kế:** dùng parent-first cho các class cần **một danh tính Java chung**, plugin-first cho mã và dependency **thực sự thuộc sở hữu riêng của plugin**, và khai báo các ngoại lệ ủy quyền đủ chặt để API/SPI của host không bị shadow. Phần còn lại của hệ thống—resource lookup, `ServiceLoader`, TCCL, version policy và lifecycle—phải được thiết kế phù hợp với quyết định đó, thay vì mặc định mọi loại tìm kiếm đều tuân cùng một quy tắc.
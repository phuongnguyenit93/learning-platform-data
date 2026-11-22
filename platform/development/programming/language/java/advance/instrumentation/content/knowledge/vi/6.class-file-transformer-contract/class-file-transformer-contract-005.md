# Lọc lớp theo tên, bộ nạp, module và nguồn mã trước khi phân tích bytecode

## 1. Bài toán: transformer được gọi cho nhiều lớp hơn ta định sửa

Sau khi Java agent đăng ký `ClassFileTransformer` bằng `Instrumentation.addTransformer(...)`, JVM có thể gọi callback cho các lớp của ứng dụng, thư viện, agent và runtime. Nếu cứ parse toàn bộ `classfileBuffer` trước rồi mới quyết định một class có cần instrument không, agent sẽ tốn CPU/bộ nhớ trên những lớp không liên quan, kéo dài startup và tăng nguy cơ sửa nhầm.

**Nguyên tắc cốt lõi:** dùng các metadata mà JVM **đã cung cấp trong callback** để lọc trước, rồi mới phân tích bytecode khi lớp nằm trong phạm vi đã định. Bốn metadata chính là:

1. **Tên lớp**: tên nội bộ như `com/acme/orders/OrderService`.
2. **Bộ nạp lớp**: đối tượng `ClassLoader` **định nghĩa** class.
3. **Module**: module runtime (named hoặc unnamed) sở hữu class.
4. **Nguồn mã**: `CodeSource` lấy qua `ProtectionDomain`, nếu class có metadata này.

Bài học giúp bạn thiết kế allowlist có thứ tự, hiểu khi nào phải kiểm tra từng điều kiện, xử lý `null`, phân biệt tên class với identity JVM, và tạo một Java 17+ agent chạy được chứng minh **không hề đọc bytecode của lớp bị loại**.

**Giới hạn cần nhớ:** bộ lọc phạm vi instrumentation giúp chọn đúng đối tượng; nó **không** tự xác minh chữ ký mã hay cấp quyền JVM. Nếu một tiêu chí là yêu cầu bắt buộc của chính sách, thiếu dữ liệu để đánh giá phải có nhánh xử lý rõ ràng, thông thường `return null` (không instrument).

## 2. Đọc đúng hợp đồng `ClassFileTransformer.transform`

Trên JDK 17 có overload với thông tin module:

~~~java
byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer)
        throws IllegalClassFormatException;
~~~

Đây là chữ ký API được trích theo cấu trúc, chưa phải chương trình độc lập. Khi viết class transformer, override overload này nếu cần module. Trên Java 17, hai overload `transform` là **default methods**; overload sáu tham số mặc định ủy quyền cho overload năm tham số, còn overload năm tham số mặc định trả `null`. Vì vậy không nên mặc định rằng đây là functional interface để dùng lambda.

| Tham số | Ý nghĩa trong callback | Điều cần phòng tránh |
|---|---|---|
| `className` | Internal class name như `java/util/List`, dùng dấu `/` | So sánh nhầm với binary name có dấu `.`; không xử lý `null` |
| `loader` | Defining class loader; `null` nếu do bootstrap loader định nghĩa | So sánh tên class của loader thay vì instance identity |
| `module` | Named hoặc unnamed module của class | Gọi `module.getName().equals(...)` khi module không có tên |
| `protectionDomain` | Domain dùng khi định nghĩa lớp, có thể chứa `CodeSource` | Truy cập chuỗi `getCodeSource().getLocation()` không kiểm tra `null` |
| `classBeingRedefined` | Thường `null` trong lần định nghĩa mới; class đích khi redefine/retransform | Nhầm với class cần chủ động tìm bằng `Class.forName` |
| `classfileBuffer` | Bytes classfile JVM chuyển tới transformer tại lượt này | Parse sớm, sửa in-place hoặc giữ tham chiếu để thay đổi về sau |

Nếu không cần sửa class, **trả `null`**. Nếu cần sửa, tạo **byte array mới hợp lệ**, không chỉnh trực tiếp `classfileBuffer`. Khi có nhiều transformers, bytes của transformer trước có thể đi vào transformer sau; không mặc định mảng đầu vào giống hệt tệp `.class` trên đĩa.

Thứ tự các callback không phải một danh sách class cố định: JVM có thể gọi nhiều lần từ các luồng khác nhau, đặc biệt khi ứng dụng nạp lớp động, và có các lượt redefine/retransform tùy capability.

## 3. Đặt bộ lọc metadata ở đầu callback

Một thứ tự dễ kiểm tra và thường có hiệu năng tốt:

~~~text
transform(module, loader, name, redefining, domain, bytes)
     |
     v
[1] name chính xác hoặc thuộc package allowlist?
     | no -> return null
     v
[2] loader identity/chính sách loader phù hợp?
     | no -> return null
     v
[3] module đúng kiểu và tên/identity?
     | no -> return null
     v
[4] domain -> CodeSource -> origin hợp lệ?
     | no/unknown -> return null
     v
[5] lúc này mới parse/inspect classfileBuffer
     |
     +-- không có thay đổi -> return null
     +-- cần biến đổi -> return new byte[] hợp lệ
~~~

Cách này không biến mỗi callback thành một lần mở JAR, quét annotations, phân tích method hoặc giải mã constant pool. Bộ lọc tên và identity thường rất rẻ; kiểm tra URL/path cũng chỉ thực hiện cho tập class nhỏ đã qua các điều kiện trước.

Biểu thức phạm vi:

~~~text
selected =
    isAllowedName(className)
 && isAllowedLoader(loader)
 && isAllowedModule(module)
 && isAllowedOrigin(protectionDomain)

if (!selected) return null;
return inspectOrTransform(classfileBuffer);
~~~

Đây là **pseudo-code**, không phải class Java có thể chạy độc lập. Khi dùng thực tế, xác định rõ thế nào là “allowed”: một class chính xác, một package có ranh giới, một loader identity, một module name/instance và một thư mục/JAR nguồn cho phép.

## 4. Lọc theo tên: internal name khác binary name

Tên thường viết trong Java code và trong callback là hai dạng khác nhau:

| Tên trong Java | `className` của transformer |
|---|---|
| `com.acme.OrderService` | `com/acme/OrderService` |
| `com.acme.internal.Metrics` | `com/acme/internal/Metrics` |
| `com.acme.Outer$Inner` | `com/acme/Outer$Inner` |

Nếu chỉ chọn đúng một lớp:

~~~java
if (!"com/acme/OrderService".equals(className)) {
    return null;
}
~~~

Cách đặt literal bên trái `equals` là **null-safe** nếu `className` không có giá trị. Nếu chọn package `com.acme.orders` và các package con:

~~~java
if (className == null
        || !className.startsWith("com/acme/orders/")) {
    return null;
}
~~~

Phải có dấu `/` cuối prefix để tránh vô tình chọn `com/acme/ordersInternal/Hidden`. Nếu chỉ muốn lớp outer mà không muốn nested class, chọn so sánh exact class name; tên nested thường chứa `$` và prefix thô có thể quá rộng.

Chính sách tên cần có bộ exclude cho package agent/helper, bytecode engine hoặc logging backend nếu allowlist có thể bao trùm chúng. Lỗi phổ biến là `startsWith("com/acme")` không có separator, vô tình chạm `com/acme2`, hoặc dùng `contains("Service")` vốn không thể hiện ranh giới package.

**Không gọi `Class.forName(...)` ngay trong callback để xác định tên lớp.** Callback đã cung cấp tên. Việc chủ động nạp class lúc JVM đang định nghĩa class khác có thể làm xuất hiện class loading recursion, linkage lỗi hoặc khiến lớp đích nạp trước khi agent sẵn sàng. Chỉ sau khi lọc xong mới tiến tới phân tích bytes nếu cần.

## 5. Lọc theo class loader: identity mới xác định class

Theo JVM, class identity không chỉ là tên chuỗi. Hai định nghĩa với cùng binary name nhưng **khác defining loader** là hai kiểu khác nhau.

~~~text
System loader -------> demo.OrderService  (Class A)
Plugin loader -------> demo.OrderService  (Class B)

Tên giống nhau, defining loader khác => A và B khác identity.
~~~

Trong một chương trình classpath bình thường, nếu chỉ cho phép system loader:

~~~java
if (loader != ClassLoader.getSystemClassLoader()) {
    return null;
}
~~~

Đây là so sánh **`==` giữa hai đối tượng loader**, không so sánh `loader.getClass().getName()`. Nhiều `URLClassLoader` có cùng class Java, nhưng mỗi instance có thể định nghĩa một tập class riêng.

`loader == null` là trường hợp bootstrap loader. Đoạn trên tự loại bỏ bootstrap classes; nếu viết điều kiện khác, cần xử lý null trước khi gọi method trên loader:

~~~java
if (loader == null) {
    return null;
}
~~~

**Khi nào không nên khóa vào system loader?** Spring Boot executable JAR, OSGi, application servers, plugin platforms, nhiều class loaders tùy chỉnh hoặc môi trường hot reload có thể nạp business code qua một loader khác. Khi đó cần chính sách đã kiểm tra về loader đích, ví dụ một tập instance cụ thể hoặc cách xác định custom application loader kết hợp code source/module. Không bỏ hết kiểm tra loader chỉ vì case system loader lọc sai.

Các hệ thống hot reload cần chú ý không giữ tham chiếu mạnh vô hạn tới class loader cũ. Cache theo loader có thể làm rò rỉ ứng dụng khi redeploy. Nếu tập loader được cập nhật đồng thời, xây cơ chế công bố state/caching phù hợp thay vì để callback đọc collection đang bị sửa không đồng bộ.

## 6. Lọc theo `Module`: named, unnamed và layer

JDK 9+ dùng Java Platform Module System. `Module` phản ánh module runtime của class:

- **Named module:** `module.isNamed() == true`; `module.getName()` trả tên như `com.acme.orders`.
- **Unnamed module:** `module.isNamed() == false`; `module.getName() == null`. Mỗi defining loader có unnamed module riêng.
- Named modules còn thuộc một module layer (có thể là nhiều layer trong một ứng dụng), vì vậy **module name không luôn đủ để định danh module instance** khi topology phức tạp.

Nếu chỉ muốn lớp từ classpath unnamed module:

~~~java
if (module == null || module.isNamed()) {
    return null;
}
~~~

Nếu chỉ muốn một named module:

~~~java
if (module == null
        || !module.isNamed()
        || !"com.acme.orders".equals(module.getName())) {
    return null;
}
~~~

Hai đoạn trên là điều kiện minh họa. Chúng không thể cùng áp dụng vì thể hiện **hai chính sách chọn module khác nhau**.

Điều cần tránh:

~~~java
// Sai: getName() có thể là null nếu unnamed module.
if (module.getName().equals("com.acme.orders")) {
    // ...
}
~~~

Không suy ra “unnamed = ứng dụng đáng tin”. Một JAR plugin hoặc thư viện trên classpath cũng thuộc unnamed module. Kết hợp module với loader và origin.

Nếu muốn instrument một named module rồi chèn lời gọi tới helper của agent, **module selection chưa bảo đảm helper truy cập được**: còn phải xét readability, exports/opens và loader visibility. `Instrumentation.redefineModule(...)` có thể mở rộng một số quan hệ module theo hợp đồng API, nhưng đó là một quyết định riêng, chỉ áp dụng khi cần và đã kiểm thử.

## 7. Lọc theo nguồn mã: `ProtectionDomain` và `CodeSource`

`ProtectionDomain` gom thông tin miền bảo vệ khi class được định nghĩa. `ProtectionDomain.getCodeSource()` trả về `CodeSource` **nếu có**. `CodeSource.getLocation()` trả về `URL` của codebase **nếu được cung cấp**.

Phải xử lý toàn bộ chuỗi null:

~~~text
protectionDomain?
    |
    +-- null --------------> return null
    |
    v
getCodeSource()?
    |
    +-- null --------------> return null
    |
    v
getLocation()?
    |
    +-- null --------------> return null
    |
    v
location (URL) -> áp dụng chính sách origin
~~~

Ví dụ phòng thủ:

~~~java
if (protectionDomain == null) return null;
java.security.CodeSource cs = protectionDomain.getCodeSource();
if (cs == null || cs.getLocation() == null) return null;
java.net.URL url = cs.getLocation();
~~~

**Nguồn không nhất thiết là đường dẫn `.class`:** đối với classpath directory, location thường là thư mục root. Đối với class từ JAR, location có thể là URL đến JAR. Với custom class loader, in-memory/generated classes, nested JAR, runtime image hoặc các cách đóng gói đặc thù, metadata có thể vắng hoặc mang dạng URL khác `file:`.

Để so sánh một code source kiểu `file:` với một thư mục/JAR được phép, dùng `URL → URI → Path` thay vì string prefix:

~~~java
java.net.URL location = cs.getLocation();
if (!"file".equalsIgnoreCase(location.getProtocol())) {
    return null;
}

java.nio.file.Path actual;
try {
    actual = java.nio.file.Path.of(location.toURI())
            .toAbsolutePath()
            .normalize();
} catch (java.net.URISyntaxException
        | IllegalArgumentException ex) {
    return null;
}

if (!actual.equals(allowedOrigin)) {
    return null;
}
~~~

`allowedOrigin` là `Path` đã normalize từ cấu hình **một lần** trước khi đăng ký transformer. Dùng `Path.equals` khi policy là **đúng một classpath root hoặc một JAR**; dùng `Path.startsWith(Path)` khi policy cho phép thư mục con (và đã xem xét symbolic links/permission). Không dùng `location.toString().startsWith("/opt/app")` vì `/opt/app-bak` có cùng tiền tố chuỗi, và URL encoding có thể khác đường dẫn OS.

**Một số giới hạn quan trọng:**

- `normalize()` xử lý `.` và `..` về mặt cú pháp, không xác minh symbolic link hoặc file thực. `toRealPath()` có thể cần disk I/O, nên thực hiện ở lúc khởi tạo/configuration nếu bắt buộc, không chạy trên mọi callback.
- `CodeSource` là metadata do loader gắn cho class; **không phải chứng cứ mật mã** rằng bytes được ký đúng hoặc không bị thay thế.
- Với nguồn không rõ và policy yêu cầu origin allowlist, tốt nhất **fail closed**: trả `null` trước khi parse bytecode. Nếu sản phẩm cần instrument generated classes, phải định nghĩa một nhánh chính sách riêng chứ không ngầm cho phép mọi source null.
- Nếu URL không có scheme `file:` (ví dụ nested-loader representation), đừng đưa thẳng vào `Path.of(URI)`; viết adapter phù hợp loại origin đó.
- Chọn code source theo cách JVM **đang chạy** nhìn thấy. Đường dẫn trong container có thể khác host.

## 8. Một Java agent chạy được trên JDK 17+ dùng đủ bốn điều kiện

Ví dụ dưới đây chỉ sử dụng JDK, không yêu cầu Byte Buddy, ASM hay Maven. Agent chỉ quan sát **`sample.target.ReceiptService` từ system loader, unnamed module và source directory `out/app`**. Sau khi qua bốn điều kiện, nó mới đọc 8 byte đầu classfile: magic `CAFEBABE` và major version `61` của Java 17.

Ví dụ còn tạo hai tình huống bị loại: một class cùng simple name nhưng sai package và một class **cùng full binary name** nhưng do custom `URLClassLoader` khác định nghĩa. Transformer luôn trả `null` để giữ hành vi gốc.

### 8.1. Các tệp

~~~text
filter-demo/
├── MANIFEST.MF
├── src/
│   ├── agent/sample/agent/
│   │   ├── FilterAgent.java
│   │   └── ScopeFilter.java
│   └── app/sample/
│       ├── app/App.java
│       ├── target/ReceiptService.java
│       └── other/ReceiptService.java
└── out/                  # Tạo ở bước build
    ├── agent/
    ├── app/
    └── filter-agent.jar
~~~

Tệp `src/agent/sample/agent/FilterAgent.java`:

~~~java
package sample.agent;

import java.lang.instrument.Instrumentation;
import java.nio.file.Path;

public final class FilterAgent {
    private FilterAgent() {}

    public static void premain(String agentArgs, Instrumentation inst) {
        if (agentArgs == null || agentArgs.isBlank()) {
            throw new IllegalArgumentException(
                    "Expected code-source directory in agent arguments");
        }

        Path allowedOrigin = Path.of(agentArgs)
                .toAbsolutePath()
                .normalize();

        inst.addTransformer(new ScopeFilter(allowedOrigin));
        System.out.println("[agent] filter installed");
    }
}
~~~

`premain` chạy trước `App.main`. Đường dẫn cấu hình được normalize một lần; transformer nhận state bất biến. Ở đây chọn đúng một tham số là thư mục nguồn, nên không cần parser key-value phức tạp.

Tệp `src/agent/sample/agent/ScopeFilter.java`:

~~~java
package sample.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.IllegalClassFormatException;
import java.net.URISyntaxException;
import java.net.URL;
import java.nio.file.Path;
import java.security.CodeSource;
import java.security.ProtectionDomain;

public final class ScopeFilter implements ClassFileTransformer {
    private static final String TARGET =
            "sample/target/ReceiptService";

    private final Path allowedOrigin;

    public ScopeFilter(Path allowedOrigin) {
        this.allowedOrigin = allowedOrigin;
    }

    @Override
    public byte[] transform(
            Module module,
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) throws IllegalClassFormatException {

        // 1. Filter name: không động tới bytecode.
        if (!TARGET.equals(className)) {
            return null;
        }

        // 2. Filter defining loader bằng identity.
        if (loader != ClassLoader.getSystemClassLoader()) {
            return null;
        }

        // 3. Filter module: chỉ classpath unnamed module.
        if (module == null || module.isNamed()) {
            return null;
        }

        // 4. Filter code source, phòng thủ với null.
        if (protectionDomain == null) {
            return null;
        }
        CodeSource source = protectionDomain.getCodeSource();
        if (source == null || source.getLocation() == null) {
            return null;
        }

        URL location = source.getLocation();
        if (!"file".equalsIgnoreCase(location.getProtocol())) {
            return null;
        }

        Path actualOrigin;
        try {
            actualOrigin = Path.of(location.toURI())
                    .toAbsolutePath()
                    .normalize();
        } catch (URISyntaxException | IllegalArgumentException ex) {
            return null;
        }
        if (!allowedOrigin.equals(actualOrigin)) {
            return null;
        }

        // CHỈ SAU BỐN GUARD mới kiểm tra bytecode.
        if (classfileBuffer == null || classfileBuffer.length < 8) {
            throw new IllegalClassFormatException("Short class header");
        }

        int magic = ((classfileBuffer[0] & 0xff) << 24)
                | ((classfileBuffer[1] & 0xff) << 16)
                | ((classfileBuffer[2] & 0xff) << 8)
                | (classfileBuffer[3] & 0xff);
        if (magic != 0xCAFEBABE) {
            throw new IllegalClassFormatException("Bad class magic");
        }

        int major = ((classfileBuffer[6] & 0xff) << 8)
                | (classfileBuffer[7] & 0xff);

        System.out.println("[agent] selected "
                + className.replace('/', '.')
                + " major=" + major);
        return null; // Quan sát thôi, không sửa class bytes.
    }
}
~~~

Một số điều quan trọng khi đọc code:

- So sánh `TARGET.equals(className)` an toàn khi `className == null`; nó là guard đầu tiên.
- `loader != ClassLoader.getSystemClassLoader()` loại bootstrap loader và custom loader khác mà không cần gọi method lên `loader`.
- `module == null || module.isNamed()` chỉ cho unnamed module; đây là chính sách demo, không phải hạn chế do JVM áp đặt.
- `CodeSource` có thể không có; thiếu thông tin được loại an toàn.
- Biến `major` chỉ được tính khi cả bốn guard đã pass. Java 17 classfile major version là **61**.
- Khi không có nhu cầu biến đổi, trả `null`; không sửa mảng byte từ JVM và không chặn transformer khác.

Tệp `src/app/sample/target/ReceiptService.java`:

~~~java
package sample.target;

public final class ReceiptService {
    private ReceiptService() {}

    public static void execute() {
        System.out.println("[app] target execute");
    }
}
~~~

Tệp `src/app/sample/other/ReceiptService.java`:

~~~java
package sample.other;

public final class ReceiptService {
    private ReceiptService() {}

    public static void execute() {
        System.out.println("[app] other execute");
    }
}
~~~

Tệp `src/app/sample/app/App.java`:

~~~java
package sample.app;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class App {
    private App() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java sample.app.App <compiled-app-dir>");
        }

        System.out.println("[app] main");

        // Cùng tên/package mà agent chọn, loader hệ thống.
        Class<?> target = Class.forName(
                "sample.target.ReceiptService");
        target.getMethod("execute").invoke(null);

        // Cùng simple name, khác package: rớt name guard.
        Class<?> other = Class.forName(
                "sample.other.ReceiptService");
        other.getMethod("execute").invoke(null);

        // Cùng full binary name, nhưng defining loader khác.
        URL source = Path.of(args[0])
                .toAbsolutePath()
                .normalize()
                .toUri()
                .toURL();

        try (URLClassLoader isolated = new URLClassLoader(
                new URL[] { source },
                ClassLoader.getPlatformClassLoader())) {
            Class<?> copy = Class.forName(
                    "sample.target.ReceiptService",
                    true,
                    isolated);
            copy.getMethod("execute").invoke(null);
        }

        System.out.println("[app] done");
    }
}
~~~

`URLClassLoader` mới có **platform class loader** làm parent. Vì platform loader không có class nghiệp vụ này, bản sao `sample.target.ReceiptService` được định nghĩa bởi custom loader. Nếu để system loader làm parent, cơ chế parent-first có thể trả lại class đã nạp, làm ví dụ không chứng minh được việc khác loader.

Tệp `MANIFEST.MF` (cần kết thúc file bằng newline):

~~~text
Manifest-Version: 1.0
Premain-Class: sample.agent.FilterAgent

~~~

Khi đóng gói bằng `jar cfm`, manifest được lưu thành `META-INF/MANIFEST.MF` trong agent JAR. Không cần `Can-Retransform-Classes` vì ví dụ chỉ theo dõi lần nạp mới.

### 8.2. Biên dịch

Từ thư mục `filter-demo/`, tạo output folders.

Bash:

~~~bash
mkdir -p out/agent out/app
~~~

PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out/agent, out/app | Out-Null
~~~

Chạy các lệnh sau bằng **JDK 17 trở lên**:

~~~bash
javac --release 17 -d out/agent src/agent/sample/agent/FilterAgent.java src/agent/sample/agent/ScopeFilter.java

javac --release 17 -d out/app src/app/sample/app/App.java src/app/sample/target/ReceiptService.java src/app/sample/other/ReceiptService.java

jar cfm out/filter-agent.jar MANIFEST.MF -C out/agent .
~~~

`javac --release 17` bảo đảm class files do ví dụ biên dịch dùng target Java 17; phần header có major version 61. `out/agent` chứa agent classes; `out/app` chứa application classes.

### 8.3. Chạy không agent

~~~bash
java -cp out/app sample.app.App out/app
~~~

Kết quả:

~~~text
[app] main
[app] target execute
[app] other execute
[app] target execute
[app] done
~~~

Lớp mục tiêu được tải hai lần bằng hai loader khác nhau nhưng method in cùng chuỗi. Không có dòng agent.

### 8.4. Chạy agent với origin đúng

~~~bash
java -javaagent:out/filter-agent.jar=out/app -cp out/app sample.app.App out/app
~~~

Kết quả dự kiến trong môi trường classpath directory theo ví dụ:

~~~text
[agent] filter installed
[app] main
[agent] selected sample.target.ReceiptService major=61
[app] target execute
[app] other execute
[app] target execute
[app] done
~~~

Diễn giải:

1. Agent được khởi tạo trước ứng dụng và đăng ký transformer.
2. `sample.target.ReceiptService` từ system loader, unnamed module và directory `out/app` pass cả bốn guard; transformer đọc header và in major=61.
3. `sample.other.ReceiptService` rớt ngay guard name.
4. Bản sao `sample.target.ReceiptService` do isolated `URLClassLoader` tạo có cùng full name và cùng thư mục nguồn, nhưng rớt guard loader, nên không bị đọc header lần nữa.
5. Cả hai bản `ReceiptService` vẫn chạy nguyên trạng vì transformer luôn trả `null`.

### 8.5. Chứng minh source guard bằng cấu hình origin sai

~~~bash
java -javaagent:out/filter-agent.jar=out/not-the-app -cp out/app sample.app.App out/app
~~~

Với policy exact source, `out/not-the-app` khác `out/app`. Kết quả không có dòng `[agent] selected ...`, dù target vẫn được nạp và chạy; callback bị loại **trước khi parse bytes**.

Chú ý: ví dụ minh họa không kiểm tra sự tồn tại của thư mục truyền vào lúc `premain`. Trong hệ thống thật, nên validate đường dẫn cấu hình sớm và quyết định rõ fail-fast hay disabled mode.

## 9. Từ demo sang transformer phân tích bytecode thực sự

Trong ví dụ ta đọc 8 byte đầu classfile, chỉ để minh họa **điểm bắt đầu** làm việc với bytes. Khi xây agent thực, phần sau bốn guard có thể gọi ASM, Byte Buddy hoặc Class-File API nếu dùng JDK hỗ trợ (Class-File API được chuẩn hóa trong JDK 24). Trên JDK 17, đừng import `java.lang.classfile` vì API này chưa tồn tại ở JDK 17.

~~~text
Metadata gates đã pass
       |
       v
Class-file parser
       ├── đọc class version, constant pool
       ├── tìm phương thức/annotation cần instrument
       └── dựng kết quả mới
              ├── không thay đổi: null
              └── thay đổi: new byte[] hợp lệ
                              └── JVM verifier kiểm tra
~~~

Thay đổi thật phải đáp ứng quy tắc classfile, code attributes, stack map frames, exception paths và ràng buộc retransform/redefine nếu đó không phải lần nạp ban đầu. **Lọc đúng đối tượng không bảo đảm biến đổi bytecode đúng.**

Một số trường hợp phức tạp:

- Instrument lớp đã nạp bằng `retransformClasses` cần capability, class modifiable và transformer đăng ký retransform-capable. `addTransformer` không tự xử lý lại các lớp đã load.
- Một class có thể xuất hiện cùng tên từ nhiều class loaders; kết quả của filter phải dựa vào loader của **lượt callback hiện tại**, không dựa trên một lần tra tên toàn cục.
- Nếu instrument helper được bytecode gọi, phải kiểm tra việc helper có thể link từ defining loader/module của lớp đích; bốn guard chọn class không giải quyết tự động visibility của helper.
- Trong hệ thống có nhiều agents, transformer có thể thấy bytes đã được biến đổi ở bước trước. Đảm bảo idempotency hoặc phân biệt class đã sửa bằng cơ chế chính xác; đừng phụ thuộc một hash duy nhất mà không hiểu chuỗi biến đổi.

## 10. Những ngộ nhận dẫn đến lỗi

### 10.1. “Đúng package nghĩa là đúng class”

Sai trong plugin platforms: hai loader có thể chứa `com.acme.OrderService`. Bộ lọc chỉ theo tên làm cả hai bị instrument. Cần loader identity và/hoặc code source/module policy.

### 10.2. “`getClass().getName()` của loader đủ để phân biệt”

Không. Hai `URLClassLoader` đều có cùng Java class. Chúng là các instance khác nhau và có thể định nghĩa class riêng; so theo tên loader sẽ cho kết quả sai.

### 10.3. “Unnamed module nghĩa là app code”

Không. Mỗi loader có unnamed module của nó; code thư viện classpath hoặc plugin đều có thể thuộc unnamed module. Cần xét loader và nguồn mã.

### 10.4. “Có `ProtectionDomain` thì chắc chắn có CodeSource URL”

Không. `ProtectionDomain.getCodeSource()` và `CodeSource.getLocation()` có thể `null`. Trả `null` cho lớp không đủ thông tin nếu origin bắt buộc là một chính sách an toàn và dễ dự đoán.

### 10.5. “So sánh string URL bằng `startsWith` là đủ”

Không. Dấu phân tách, URL encoding, canonical path và symlink khiến kết quả khác. Sử dụng cấu trúc `URI`/`Path` cho scheme tương thích và phân biệt exact origin với subtree origin.

### 10.6. “Parse trước để biết loader hoặc module”

Sai. Hai thông tin này đã ở callback. Không nên parse constant pool, load class phản chiếu hay mở JAR chỉ để suy ra dữ liệu đã có.

### 10.7. “`return null` sẽ chặn mọi transformer khác”

Sai. Nó chỉ nói callback hiện tại không biến đổi input. JVM vẫn áp dụng chuỗi transformer theo hợp đồng API.

### 10.8. “CodeSource xác minh tính đáng tin của class”

Không. CodeSource có thể chứa thông tin URL và signer metadata nhưng origin đơn lẻ không phải bằng chứng bảo mật toàn diện. Kiểm tra trust/signature/hash là trách nhiệm riêng.

### 10.9. “In log mọi lần skip sẽ giúp debug miễn phí”

Không. Số callback có thể rất lớn, đặc biệt lúc startup. Ghi log đồng bộ trong mọi callback làm chậm ứng dụng và có thể kích hoạt thêm class load từ logging framework. Ưu tiên counter/rate limiting và debug có thời hạn.

### 10.10. “System loader là loader của mọi business class”

Không. Spring Boot executable JAR, application servers và framework có custom loaders. Không thấy event chưa chắc tên sai; cần chẩn đoán đúng loader/module/origin runtime trước khi chỉnh policy.

## 11. Bảng kiểm thử và QA khi triển khai

| Tình huống | Tên | Loader | Module | Source | Hành vi |
|---|---|---|---|---|---|
| Target từ `out/app` với system loader | Pass | Pass | Unnamed pass | Pass | Đọc class header, major=61 |
| Class cùng simple name nhưng package khác | Fail | Không xét | Không xét | Không xét | Trả `null` trước khi đọc bytes |
| Full binary name giống target nhưng custom loader | Pass | Fail | Không xét | Không xét | Trả `null` |
| Target đúng loader/module nhưng source khác | Pass | Pass | Pass | Fail | Trả `null` |
| Loader bootstrap `null` | Tùy | Fail trong demo | Không xét | Không xét | Bỏ qua |
| Named module | Tùy | Tùy | Fail trong demo | Không xét | Bỏ qua |
| Thiếu `CodeSource` theo policy bắt buộc | Pass | Pass | Pass | Không rõ | Trả `null`, ghi metric skip nếu cần |
| Bytes classfile hỏng nhưng metadata pass | Pass | Pass | Pass | Pass | Parser/verifier có thể báo lỗi; không dùng bytes sai |

QA trên môi trường production nên bao gồm classloaders thực tế, module layers, nested JAR origin, generated classes, thay đổi code source khi deploy/containerize, nhiều agents cùng hoạt động, và callback retransform/redefine nếu agent có dùng. Test hiệu năng so sánh startup và throughput trước/sau khi bật instrumentation.

**Ba sự kiện phải tách biệt:**

- Log “transformer registered” chỉ chứng minh đăng ký thành công.
- Log “selected ... major=61” chứng minh lớp pass filter và header classfile được kiểm tra.
- **Instrumentation thật** chỉ được chứng minh khi transformer trả bytes mới hợp lệ và ứng dụng hoạt động theo hành vi mong đợi.

## 12. Câu hỏi ôn tập

**1.** Có hai lớp cùng tên `com.acme.Payment`, được định nghĩa bởi hai loader khác nhau. Name filter exact có đủ không?

> Không. Tên nội bộ giống nhau nhưng JVM type identity khác. Cần loader/module/origin policy để phân biệt đúng lớp.

**2.** `module.getName()` trả `null` có chứng minh đây là class ứng dụng không?

> Không. Class thuộc unnamed module; nhiều loader và thư viện đều có thể sở hữu unnamed module. Cần kiểm tra thêm.

**3.** Nếu `protectionDomain.getCodeSource()` là `null`, agent có bắt buộc phải instrument không?

> Không. Khi chính sách yêu cầu origin xác định, bỏ qua lớp đó là hợp lý. Nếu muốn hỗ trợ generated classes, phải định nghĩa cơ chế thay thế rõ.

**4.** Vì sao dùng `Path.equals` hoặc `Path.startsWith(Path)` theo chính sách, không dùng `String.startsWith` trên URL?

> Vì path có ranh giới phân đoạn, xử lý URI/encoding phù hợp hơn. Chính sách exact file khác chính sách subtree; string prefix có thể khớp nhầm tên thư mục.

**5.** Khi nào được gọi parser bytecode?

> Sau khi className, defining loader, module và code source đã pass mọi guard bắt buộc. Nếu chỉ có metadata mà chưa đủ điều kiện, trả `null`.

**6.** Bản sao `sample.target.ReceiptService` tải bằng `URLClassLoader` trong ví dụ có được chọn không?

> Không. Dù cùng full binary name và origin thư mục, defining loader khác system loader nên bị loại trước khi đọc bytes.

**7.** `return null` có nghĩa không class nào được định nghĩa nữa không?

> Không. JVM tiếp tục với bytes hiện tại và các bước transformer/verification khác. Callback này chỉ không thay đổi bytes.

**8.** Nếu callback pass filter nhưng bytecode hỏng, có thể coi filter là lỗi không?

> Không nhất thiết. Filter xác định **phạm vi**; phân tích/biến đổi classfile là một trách nhiệm tiếp theo, có thể thất bại vì format, phiên bản hoặc phép sửa không được hỗ trợ.

## 13. Tài liệu chính thức

- Java 17 `ClassFileTransformer`: tham số `transform`, sự kiện nạp/redefine/retransform, hợp đồng `return null` và byte array: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
- Java 17 `Instrumentation`: `addTransformer` và việc đăng ký theo capability: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- Java 17 `ProtectionDomain`: `getCodeSource()` và class loader metadata: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/ProtectionDomain.html
- Java 17 `CodeSource`: location URL và metadata signing: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/CodeSource.html
- Java 17 `Module`: named/unnamed modules, module name và layer: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- JVM Specification (Java SE 17): class loading, identity và classfile: https://docs.oracle.com/javase/specs/jvms/se17/html/index.html

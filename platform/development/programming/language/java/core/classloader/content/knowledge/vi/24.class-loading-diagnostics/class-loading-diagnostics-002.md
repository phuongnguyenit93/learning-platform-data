# Lần theo parent chain và ClassLoader thực sự định nghĩa lớp trong Java

## 1. Bài toán chẩn đoán: gọi loader A nhưng class lại do loader B định nghĩa

Trong một hệ Java có plugin, nhiều JAR, container hoặc framework, log thường chỉ ghi:

```java
Class<?> type = pluginLoader.loadClass("com.example.Service");
```

Người đọc dễ suy ra: “Vì gọi `pluginLoader.loadClass`, nên chính plugin loader đã định nghĩa `Service`.” **Đây là kết luận không có cơ sở.** Với cơ chế parent-first thông thường, loader nhận yêu cầu có thể ủy quyền cho parent, parent tiếp tục hỏi parent của nó, và class được trả về có thể là định nghĩa từ một loader **hoàn toàn khác**.

Trong chẩn đoán class loading, cần tách ba câu hỏi:

1. **Ai nhận yêu cầu?** Loader được code gọi vào, ví dụ `pluginLoader`.
2. **Đường ủy quyền qua những loader nào?** Parent chain hoặc các cạnh chuyển tiếp do custom framework tự tạo.
3. **Ai thực sự định nghĩa runtime class?** Defining ClassLoader, tra bằng `returnedClass.getClassLoader()`.

Bài này trình bày cách lần theo parent chain, kiểm chứng defining loader bằng class object, phân biệt với initiating loader và TCCL, truy xuất nguồn bytecode, đọc log JVM và xử lý những trường hợp trùng tên lớp. Một chương trình Java 17 hoàn chỉnh sẽ tạo nhiều loader để **chứng minh bằng kết quả chạy được**, thay vì chỉ dựa vào sơ đồ.

## 2. Ba khái niệm không được đánh đồng

### 2.1. Requesting loader — đối tượng nhận lời gọi

Giả sử:

```java
ClassLoader requested = pluginLoader;
Class<?> type = requested.loadClass("com.example.Report");
```

Đây là snippet, cần có `pluginLoader` và class tương ứng.

**Requesting loader** ở đây chỉ là `requested` — đối tượng mà chương trình gọi. Nó có thể tự định nghĩa class, nhưng cũng có thể nhờ loader khác.

### 2.2. Initiating loader — thuật ngữ ở mức JVM

JVMS phân biệt loader **khởi xướng việc nạp** (*initiating loader*) và loader **định nghĩa lớp** (*defining loader*). Khi loader con ủy quyền và nhận class do parent định nghĩa, JVM có thể ghi nhận loader con như một initiating loader của class đó. Điều này quan trọng cho các ràng buộc nạp/liên kết và việc tái sử dụng lớp.

**Đừng coi “initiating” và “defining” là cùng một khái niệm.** Một class có một defining loader theo mô hình định danh runtime; có thể được nhiều loader khác nhau yêu cầu/nạp qua delegation. Phương thức protected `findLoadedClass(name)` kiểm tra class đã được JVM ghi nhận với loader liên quan, không có nghĩa kết quả nhất định do chính loader đó định nghĩa.

### 2.3. Defining loader — ai sở hữu định nghĩa runtime?

Từ một `Class<?>` đã được trả về:

```java
Class<?> type = requested.loadClass("com.example.Report");
ClassLoader defining = type.getClassLoader();
```

Giá trị `defining` là **defining ClassLoader** của runtime class đó. Có thể:

- Bằng `requested` nếu loader này tự định nghĩa.
- Bằng parent/ancestor nếu parent-first delegation đã tìm được class.
- Bằng một loader khác nếu framework áp dụng routing tùy chỉnh.
- Bằng `null` đối với class do bootstrap loader định nghĩa, ví dụ `java.lang.String` ở Java tiêu chuẩn.

**Quy tắc kiểm chứng:** muốn biết một class thực sự thuộc loader nào, hãy kiểm tra **đối tượng Class thật đã được trả về hoặc đang được sử dụng**, thay vì suy từ loader mà code ban đầu gọi.

## 3. Parent chain được biểu diễn như thế nào?

Trong Java 17 thông thường:

```text
       Bootstrap (Class.getClassLoader() biểu diễn bằng null)
           ^
           |
       Platform ClassLoader
           ^
           |
       Application/System ClassLoader
           ^
           |
       Plugin ClassLoader (nếu parent là application)
```

Dấu mũi tên chỉ **hướng từ child lên parent**, không phải hướng “sở hữu class”. Một plugin loader có thể được tạo với parent khác, ví dụ:

```java
ClassLoader parent = ClassLoader.getPlatformClassLoader();

try (java.net.URLClassLoader plugin =
        new java.net.URLClassLoader(pluginUrls, parent)) {
    // Chỉ code/plugin cần dùng platform classes, theo thiết kế.
}
```

Đây là snippet minh họa; cần có `pluginUrls`. Trong trường hợp này parent trực tiếp là **platform**, không phải application loader. Vì vậy **không thể chỉ nhìn tên “plugin loader” để giả định cây parent của nó**.

Các API liên quan:

```java
ClassLoader system = ClassLoader.getSystemClassLoader();
ClassLoader platform = ClassLoader.getPlatformClassLoader();
ClassLoader parent = system.getParent();
```

Đây là snippet. Ở môi trường chuẩn, system/application loader thường có parent là platform; nhưng class loader hierarchy có thể được tùy biến bằng launcher, runtime hoặc framework.

**Bootstrap không luôn là một Java ClassLoader object hiển thị công khai.** Khi gọi `ClassLoader.getParent()` rồi nhận `null`, parent tiếp theo không còn là object Java quan sát được. Khi gọi `String.class.getClassLoader()` trả `null`, đó là biểu diễn API cho bootstrap loader.

### Parent chain là quan hệ cha–con, không phải toàn bộ đồ thị tìm lớp

Một loader tùy chỉnh có thể override `loadClass` để chuyển một số namespace sang **peer loader**, thread context loader hoặc service registry. Ví dụ:

```text
Plugin A  --parent--> Application
    |
    +-- custom route for api.impl.* --> Plugin B
```

Ở đây, `A.getParent()` chỉ mô tả parent trực tiếp. Nó **không tự tiết lộ** custom route A→B. Do đó tracing đầy đủ đôi khi phải kết hợp `getParent()` với log từ các override của `loadClass` và các bộ định tuyến của framework.

Trong hệ JPMS (Java 9+), module resolution, module layers và class loader mapping cũng ảnh hưởng class được tìm ở đâu; không nên suy toàn bộ hành vi từ cây parent đơn giản.

## 4. Parent-first delegation: đọc chính xác các bước

Thuật toán mặc định `ClassLoader.loadClass(String, boolean)` về tổng thể:

```text
child.loadClass("pkg.Type")
    |
    +-- findLoadedClass("pkg.Type")
    |       \-- Đã có? trả Class đã ghi nhận
    |
    +-- parent.loadClass("pkg.Type")
    |       \-- Parent tìm được? trả Class của parent/ancestor
    |
    +-- child.findClass("pkg.Type")
            \-- Child tìm bytecode rồi defineClass -> trả Class
```

Ngoài sơ đồ còn có class loading locks, resolution/linking và các exception theo API. Sơ đồ chỉ diễn tả ưu tiên **mặc định**.

Hệ quả:

- Nếu parent **có** `pkg.Type`, child thường không tìm bản bytecode cùng tên ở JAR riêng.
- Nếu parent **không có**, child có thể gọi `findClass` để tự định nghĩa.
- Một child có thể **đã ghi nhận nạp** một class do parent định nghĩa; yêu cầu lặp về cùng tên trả lại class object đó.
- Đổi thứ tự URL trong child **không giải quyết** xung đột khi parent-first đã trả class từ parent.
- Nếu override `loadClass` thành child-first, quy tắc ưu tiên khác; phải quan sát implementation thực sự, không mặc định toàn bộ loader đều parent-first.

Một code fragment dễ khiến nhầm lẫn:

```java
ClassLoader child = ...;
Class<?> result = child.loadClass("pkg.Type");
System.out.println(result.getClassLoader() == child);
```

Đây là snippet; kết quả có thể `true` **hoặc** `false`, phụ thuộc class thực tế được định nghĩa ở đâu. Nếu `false`, đó chưa chắc là bug — có thể là delegation được thiết kế đúng.

## 5. Danh tính runtime: cùng binary name có thể là hai kiểu khác nhau

Theo JVMS, một runtime class/interface có danh tính dựa vào **(binary name, defining loader)**.

```text
("pkg.Type", ParentLoader) != ("pkg.Type", SiblingLoader)
```

Ngay cả khi hai loader dùng **cùng nội dung bytecode**, việc cả hai tự định nghĩa `pkg.Type` tạo hai runtime types riêng.

| Quan sát | Class P do parent định nghĩa | Class S do sibling định nghĩa |
| --- | --- | --- |
| `getName()` | `pkg.Type` | `pkg.Type` |
| `getClassLoader()` | parent | sibling |
| `P == S` | `false` nếu hai định nghĩa độc lập | `false` |
| `P.isInstance(instanceOfS)` | Không chỉ vì tên giống nhau | Không tự tương thích |
| Static fields | Gắn với class P | Gắn với class S |
| Package-private | Kiểm tra theo runtime package của P | Theo runtime package của S |

**Runtime package** cũng phụ thuộc tên package và **defining loader**. Hai class cùng khai báo `package pkg;` nhưng do hai loader định nghĩa không được mặc nhiên dùng quyền package-private của nhau.

Khi thấy `ClassCastException` kiểu “X cannot be cast to X”, cần in defining loader của **hai đối tượng Class thực tế**, không chỉ so tên chuỗi.

## 6. Những API chẩn đoán và giới hạn của chúng

| API | Biết được gì? | Không nên suy điều gì? |
| --- | --- | --- |
| `type.getClassLoader()` | Defining loader của class thật | Không trả danh sách mọi loader từng yêu cầu |
| `loader.getParent()` | Parent trực tiếp của loader (hoặc null) | Không liệt kê custom peer routing |
| `ClassLoader.getSystemClassLoader()` | System class loader | Không đảm bảo đây là loader định nghĩa mọi class ứng dụng |
| `ClassLoader.getPlatformClassLoader()` | Platform loader của JDK | Không chứng minh parent của custom loader là platform |
| `Thread.currentThread().getContextClassLoader()` | TCCL đang gắn trên thread | Không mặc định là defining loader của class đang gọi |
| `Class.forName(name, false, loader)` | Yêu cầu tìm/nạp qua loader **được chỉ định**, chưa chủ động initialize | Class trả về có thể do parent/ancestor định nghĩa |
| `type.getProtectionDomain().getCodeSource()` | Code source metadata khi có | Không phải luôn có URL, cũng không xác nhận mọi lớp đến từ file/JAR |
| `type.getModule()` | Runtime module của class | Không thay thế defining loader hay cho biết toàn bộ resolution graph |
| `URLClassLoader.getURLs()` | Các URL đăng ký làm nguồn tìm của URLClassLoader | Không chứng minh URL nào thực sự định nghĩa class; parent có thể thắng |
| `loader.getResource(name)` | URL tài nguyên đầu tiên theo policy lookup | Không phải chứng cứ quyết định class thật đã dùng URL ấy |
| `loader.getResources(name)` | Có thể thấy nhiều bản resource cùng tên | Không chứng minh JVM đã định nghĩa nhiều class cùng tên trong một loader |
| `findLoadedClass(name)` (protected) | Class JVM đã ghi nhận nạp với initiating loader tương ứng | Không có API public gọi từ ứng dụng ngoài subclass |

Với class bootstrap, `getClassLoader() == null` là bình thường; với primitive như `int.class`, API cũng trả `null` nhưng không nên coi primitive là một class file do bootstrap đọc như `java.lang.String`.

Một `Class<?>` có thể đại diện array class. Loader liên quan array types tuân theo quy tắc JVM đối với component type; đừng kết luận mọi array class đều đến từ một class file `[].class` trong JAR.

## 7. Thực hành Java 17: tạo parent, child và sibling loader, kiểm chứng định nghĩa thật

Chương trình này dùng `JavaCompiler` của JDK để **tự tạo hai phiên bản của cùng binary name** `diag.Sample` rồi nạp bằng ba `URLClassLoader`:

```text
Platform loader
    |
    +--> Parent URLClassLoader
    |        root: parent-classes/
    |        diag.Sample.origin() -> "PARENT"
    |          |
    |          +--> Child URLClassLoader
    |                root: child-classes/
    |                diag.Sample.origin() -> "CHILD"
    |                diag.ChildOnly.origin() -> "CHILD_ONLY"
    |
    +--> Sibling URLClassLoader
             root: child-classes/
             diag.Sample.origin() -> "CHILD"
```

Dù `Child URLClassLoader` có một `diag.Sample` riêng, lời gọi `child.loadClass("diag.Sample")` được parent-first delegation thỏa mãn ở **Parent**. Trong khi đó `diag.ChildOnly` không tồn tại ở parent, nên **Child tự định nghĩa**. Sibling có parent là platform, nên nó tự định nghĩa bản Sample ở child-classes.

### 7.1. Chương trình đầy đủ

Lưu toàn bộ mã vào file `LoaderTraceDemo.java`:

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.CodeSource;
import java.util.Comparator;
import java.util.Enumeration;
import java.util.StringJoiner;
import java.util.stream.Stream;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public final class LoaderTraceDemo {
    private static void compile(JavaCompiler compiler, Path output,
                                Path... sources) throws Exception {
        String[] args = new String[4 + sources.length];
        args[0] = "--release";
        args[1] = "17";
        args[2] = "-d";
        args[3] = output.toString();
        for (int i = 0; i < sources.length; i++) {
            args[4 + i] = sources[i].toString();
        }
        if (compiler.run(null, null, null, args) != 0) {
            throw new IllegalStateException("Compilation failed");
        }
    }

    private static boolean definedFrom(Class<?> type, Path expected)
            throws Exception {
        CodeSource source = type.getProtectionDomain().getCodeSource();
        return source != null && source.getLocation() != null
                && Path.of(source.getLocation().toURI()).toRealPath()
                       .equals(expected.toRealPath());
    }

    private static String origin(Class<?> type) throws Exception {
        return (String) type.getMethod("origin").invoke(null);
    }

    private static String chain(ClassLoader start, ClassLoader parent,
                                ClassLoader platform) {
        StringJoiner path = new StringJoiner(" -> ");
        for (ClassLoader at = start; at != null; at = at.getParent()) {
            path.add(at == start ? "child"
                    : at == parent ? "parent"
                    : at == platform ? "platform" : "other");
        }
        path.add("bootstrap");
        return path.toString();
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Use a full JDK 17+");
        }
        Path root = Files.createTempDirectory("loader-trace-");
        try {
            Path parentSrc = root.resolve("psrc/diag/Sample.java");
            Path childSrc = root.resolve("csrc/diag/Sample.java");
            Path onlySrc = root.resolve("csrc/diag/ChildOnly.java");
            Path parentOut = root.resolve("parent-classes");
            Path childOut = root.resolve("child-classes");
            Files.createDirectories(parentSrc.getParent());
            Files.createDirectories(childSrc.getParent());
            Files.createDirectories(parentOut);
            Files.createDirectories(childOut);
            Files.writeString(parentSrc,
                    "package diag; public class Sample {"
                    + " public static String origin() { return \"PARENT\"; } }");
            Files.writeString(childSrc,
                    "package diag; public class Sample {"
                    + " public static String origin() { return \"CHILD\"; } }");
            Files.writeString(onlySrc,
                    "package diag; public class ChildOnly {"
                    + " public static String origin() { return \"CHILD_ONLY\"; } }");
            compile(compiler, parentOut, parentSrc);
            compile(compiler, childOut, childSrc, onlySrc);

            ClassLoader platform = ClassLoader.getPlatformClassLoader();
            try (URLClassLoader parent = new URLClassLoader(
                         new URL[]{parentOut.toUri().toURL()}, platform);
                 URLClassLoader child = new URLClassLoader(
                         new URL[]{childOut.toUri().toURL()}, parent);
                 URLClassLoader sibling = new URLClassLoader(
                         new URL[]{childOut.toUri().toURL()}, platform)) {

                Class<?> fromChildRequest = child.loadClass("diag.Sample");
                Class<?> childOnly = child.loadClass("diag.ChildOnly");
                Class<?> childVersion = sibling.loadClass("diag.Sample");
                Class<?> fromForName = Class.forName("diag.Sample", false, child);

                System.out.println("chain=" + chain(child, parent, platform));
                System.out.println("requestIsDefining="
                        + (fromChildRequest.getClassLoader() == child));
                System.out.println("parentFirstOrigin=" + origin(fromChildRequest));
                System.out.println("parentFirstLoaderIsParent="
                        + (fromChildRequest.getClassLoader() == parent));
                System.out.println("parentCodeSource="
                        + definedFrom(fromChildRequest, parentOut));
                System.out.println("childOnlyOrigin=" + origin(childOnly));
                System.out.println("childOnlyLoaderIsChild="
                        + (childOnly.getClassLoader() == child));
                System.out.println("childCodeSource="
                        + definedFrom(childOnly, childOut));
                System.out.println("repeatedSameClass="
                        + (child.loadClass("diag.Sample") == fromChildRequest));
                System.out.println("forNameSameClass="
                        + (fromForName == fromChildRequest));
                System.out.println("siblingOrigin=" + origin(childVersion));
                System.out.println("sameBinaryName="
                        + childVersion.getName().equals(fromChildRequest.getName()));
                System.out.println("sameRuntimeClass="
                        + (childVersion == fromChildRequest));
                System.out.println("siblingLoaderIsSibling="
                        + (childVersion.getClassLoader() == sibling));
                Enumeration<URL> resources = child.getResources("diag/Sample.class");
                int matches = 0;
                while (resources.hasMoreElements()) {
                    resources.nextElement();
                    matches++;
                }
                System.out.println("classFileResources=" + matches);
                System.out.println("stringBootstrap="
                        + (child.loadClass("java.lang.String")
                                .getClassLoader() == null));
            }
        } finally {
            try (Stream<Path> paths = Files.walk(root)) {
                for (Path p : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(p);
                }
            }
        }
    }
}
```

### 7.2. Biên dịch và chạy

Từ thư mục chứa file nguồn, dùng JDK 17 trở lên:

```bash
javac --release 17 LoaderTraceDemo.java
java LoaderTraceDemo
```

Chương trình tạo hai thư mục source và hai thư mục class tạm, biên dịch các class ở runtime bằng `javax.tools.JavaCompiler` rồi dọn chúng sau khi ba URLClassLoader đã được đóng. **Không thêm** các thư mục tạm vào application classpath; nếu làm thế, loader được cấu hình có thể không còn minh họa đúng giả thiết “platform parent không chứa diag.Sample”.

### 7.3. Stdout đã kiểm chứng

Đã biên dịch chương trình với JDK 21 và `--release 17`, chạy thành công trong môi trường JDK tiêu chuẩn. Kết quả:

```text
chain=child -> parent -> platform -> bootstrap
requestIsDefining=false
parentFirstOrigin=PARENT
parentFirstLoaderIsParent=true
parentCodeSource=true
childOnlyOrigin=CHILD_ONLY
childOnlyLoaderIsChild=true
childCodeSource=true
repeatedSameClass=true
forNameSameClass=true
siblingOrigin=CHILD
sameBinaryName=true
sameRuntimeClass=false
siblingLoaderIsSibling=true
classFileResources=2
stringBootstrap=true
```

### 7.4. Vì sao mỗi kết quả lại quan trọng?

**`chain=child -> parent -> platform -> bootstrap`**: lần theo `getParent()` cho thấy đường quan hệ cha của loader thử nghiệm. Nhãn cuối “bootstrap” đại diện cho parent `null` ở cuối chuỗi; không phải object ClassLoader Java được in tên.

**`requestIsDefining=false`**: yêu cầu do child gửi, nhưng `fromChildRequest.getClassLoader()` **không phải child**. Đây là bằng chứng trực tiếp rằng “loader nhận request” khác “loader định nghĩa”.

**`parentFirstOrigin=PARENT`** và **`parentFirstLoaderIsParent=true`**: parent-first đã dùng class của parent dù child có một `diag.Sample.class` chứa logic khác.

**`parentCodeSource=true`**: `ProtectionDomain.getCodeSource().getLocation()` của class này chỉ đến thư mục `parent-classes` mà chương trình tự tạo. Đây là tín hiệu bổ sung có giá trị, nhưng trên JVM/runtime khác có thể có `CodeSource == null` hoặc URL không phải file thông thường.

**`childOnlyOrigin=CHILD_ONLY`**, **`childOnlyLoaderIsChild=true`**, **`childCodeSource=true`**: parent không có `diag.ChildOnly` nên child tìm bytecode tại URL local và tự định nghĩa class. Trường hợp này khác hoàn toàn `diag.Sample`.

**`repeatedSameClass=true`**: gọi `child.loadClass("diag.Sample")` lần nữa nhận lại class đã ghi nhận thay vì định nghĩa một runtime type mới cho cùng tên.

**`forNameSameClass=true`**: `Class.forName("diag.Sample", false, child)` dùng **loader chỉ định** để tìm class, nhưng class trả về vẫn là cùng định nghĩa của parent. Tham số `false` yêu cầu không chủ động khởi tạo class tại lời gọi này.

**`siblingOrigin=CHILD`**, **`sameBinaryName=true`**, **`sameRuntimeClass=false`**, **`siblingLoaderIsSibling=true`**: sibling có parent là platform, nên không thấy bản Sample ở parent URLClassLoader và tự định nghĩa bản trong `child-classes`. Hai class cùng tên nhưng **khác defining loader**, do đó là hai runtime types.

**`classFileResources=2`**: hỏi child về resource `diag/Sample.class` có thể liệt kê cả bản của parent và bản ở URL local. **Hai URL resource không chứng minh JVM đã định nghĩa hai runtime classes cùng tên trong child**; JVM thật sự chọn một định nghĩa cho `diag.Sample` ở đường child request.

**`stringBootstrap=true`**: class JDK `java.lang.String` do bootstrap định nghĩa; khi gọi qua child cũng nhận về class nền tảng, thể hiện delegation.

## 8. Thêm helper để đọc parent chain trong dự án thật

Tùy framework, ClassLoader có thể có `toString()` rất dài hoặc nhiều loader có cùng tên hiển thị. Nên gán ID ngắn theo **object identity**, ghi rõ loader được yêu cầu, rồi in defining loader sau khi load.

Helper tối giản:

```java
static void printParentChain(ClassLoader starting) {
    int depth = 0;
    for (ClassLoader loader = starting;
         loader != null;
         loader = loader.getParent()) {
        System.out.println("depth=" + depth++
                + ", type=" + loader.getClass().getName()
                + ", identity=" + System.identityHashCode(loader));
    }
    System.out.println("depth=" + depth + ", loader=<bootstrap/null>");
}
```

Đây là **helper minh họa**, không phải chương trình độc lập. Nếu một loader custom vi phạm dự kiến và tạo parent chain kỳ lạ, nên có giới hạn chiều sâu và visited-set khi viết công cụ chẩn đoán của framework. Quan hệ parent được thiết lập theo constructor thông thường vốn không dễ tạo vòng, nhưng custom delegation routes bên ngoài parent chain **có thể** có chu trình riêng.

**Không xem `System.identityHashCode(loader)` là ID toàn cục tuyệt đối**: có thể trùng giữa object khác nhau và không ổn định qua lần chạy JVM. Với logger sản phẩm, gán một ID từ registry bằng object-identity map cho mỗi session/plugin và không giữ mạnh loader sau khi unload.

### In thêm class/module và CodeSource

Một helper chẩn đoán class đã nạp:

```java
static void describe(Class<?> type) {
    ClassLoader loader = type.getClassLoader();
    java.security.ProtectionDomain pd = type.getProtectionDomain();
    java.security.CodeSource codeSource =
            pd == null ? null : pd.getCodeSource();

    System.out.println("name=" + type.getName());
    System.out.println("definingLoader=" + loader);
    System.out.println("module=" + type.getModule());
    System.out.println("package=" + type.getPackageName());
    System.out.println("source=" + (codeSource == null
            || codeSource.getLocation() == null
            ? "<unknown>" : codeSource.getLocation()));
}
```

Đây là helper độc lập ở mức method (đặt trong class và gọi với `Class<?>` thực tế). Nếu môi trường hạn chế truy cập một số metadata, cần xử lý exception phù hợp; đừng tự coi thiếu CodeSource là một class “không có defining loader”.

**Cảnh báo log bảo mật:** đường `CodeSource`, URL repository hoặc string `toString()` của loader có thể chứa đường dẫn nội bộ/thông tin nhạy cảm. Chỉ in ở môi trường chẩn đoán được cấp quyền và tránh lộ secret/token trong production log.

## 9. Thread Context ClassLoader (TCCL) khác defining loader như thế nào?

Một số framework nạp provider từ plugin JAR thông qua:

```java
ClassLoader context =
        Thread.currentThread().getContextClassLoader();
```

TCCL là **ngữ cảnh nạp lớp được gắn vào thread**, được một số API/framework sử dụng để chọn nơi khám phá class/service. Nó **không thay đổi** ClassLoader đã định nghĩa một class đang tồn tại.

Ví dụ ứng dụng chạy code host do application loader định nghĩa nhưng tạm dùng TCCL của plugin:

```java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    // Gọi framework/API vốn lựa chọn context class loader.
} finally {
    thread.setContextClassLoader(previous);
}
```

Đây là snippet, cần biến `pluginLoader`. Sau khi đổi TCCL:

- `Host.class.getClassLoader()` **không đổi**.
- `Class.forName("some.Type")` overload một tham số vẫn theo quy tắc loader gắn với caller, không tự nhiên dùng TCCL.
- `Class.forName("some.Type", false, pluginLoader)` dùng loader chỉ định, nhưng class có thể vẫn do parent định nghĩa.
- `ServiceLoader.load(Service.class)` có những quy tắc sử dụng context loader theo overload/API và quyền module caller; muốn chẩn đoán phải ghi rõ overload nào.
- Thread pool có thể giữ TCCL plugin sau khi plugin dừng; nhớ khôi phục trong `finally` để tránh classloader leak.

**Nguyên tắc:** logging nên tách `requestedLoader`, `TCCL` và `actualClass.getClassLoader()` thành **ba trường khác nhau**, không gán tất cả cùng một nhãn “loader”.

## 10. CodeSource: file/JAR nào cung cấp class?

Khi nghi “hai phiên bản JAR cùng có class này”, sau khi lấy được `Class<?>` thật:

```java
java.security.CodeSource source =
        clazz.getProtectionDomain().getCodeSource();
System.out.println(source == null ? "<unknown>"
        : source.getLocation());
```

Đây là snippet, cần biến `clazz`. Với class do `URLClassLoader` nạp từ JAR/thư mục thông thường, `CodeSource.getLocation()` thường cho URL nguồn đã định nghĩa class. Điều này hữu ích hơn việc chỉ in mọi JAR có mặt trong `loader.getURLs()`.

Tuy nhiên:

- Một loader tùy chỉnh dùng `defineClass` từ memory/database có thể không cung cấp CodeSource URL đặc trưng.
- Class từ runtime image `jrt:`/bootstrap có thể có metadata khác với file/JAR thông thường, thậm chí `null`.
- `CodeSource` có thể cho nơi xuất xứ khai báo, không bảo đảm một file vẫn còn tồn tại tại thời điểm debug.
- JAR có manifest `Class-Path` và công cụ build có thể đưa nguồn phụ thuộc gián tiếp; constructor URL list không luôn là toàn bộ thực tế tìm kiếm.
- URL classpath có thể là `jar:` hoặc giao thức khác; không giả định `new File(url.toURI())` luôn hợp lệ.
- Với named modules, `type.getModule()` giúp bổ sung ngữ cảnh; `CodeSource` không thay thế module information.

**Mạnh nhất là kết hợp:** class name → defining loader → module → CodeSource (nếu có) → launcher/module/classpath configuration → source artifact thực tế.

## 11. Tìm thấy nhiều resource .class không có nghĩa đã định nghĩa nhiều class

Khi chạy:

```java
Enumeration<java.net.URL> urls =
        loader.getResources("diag/Sample.class");
while (urls.hasMoreElements()) {
    System.out.println(urls.nextElement());
}
```

đây là một snippet, cần import `Enumeration` và biến `loader`. Nó có thể in URL từ parent lẫn child, kể cả khi `loader.loadClass("diag.Sample")` chỉ nhận định nghĩa của parent.

Sự khác nhau:

- **Resource search**: lấy URL file có tên phù hợp; `getResources` có thể trả nhiều nơi.
- **Class loading**: JVM định nghĩa/tái sử dụng một runtime class cho binary name trong defining loader phù hợp.
- **Parent-first**: nguồn được tìm đầu có thể đến từ parent, bỏ qua bytecode class trùng tên ở child.
- **Custom resource lookup**: có thể dùng thứ tự khác custom class delegation; không lấy `getResource` thay bằng chứng class `getClassLoader()`.

Nếu cần xác định class do loader nào định nghĩa, **`Class.getClassLoader()` là dữ kiện cốt lõi**. Resource enumeration hữu ích để kiểm tra **xung đột candidate files**, không quyết định lớp đang chạy.

## 12. Những trường hợp khiến parent-chain đơn giản chưa đủ

### 12.1. Child-first hoặc hybrid delegation

Một plugin loader có thể ưu tiên local cho `plugin.internal.*` nhưng giữ parent-first cho `java.*` và `host.api.*`. Khi ấy cần ghi policy theo namespace, vì quan hệ `getParent()` vẫn giống nhau nhưng thứ tự tìm có thể khác.

Hỏi:

1. Loader có override `loadClass(String)` hoặc `loadClass(String, boolean)` không?
2. Với binary name này, policy là parent-first hay child-first?
3. Có nhánh chuyển tiếp sang peer loader không?
4. Class đã ghi nhận qua `findLoadedClass` từ lời gọi trước chưa?
5. Một loader khác có định nghĩa trùng binary name không?

### 12.2. JPMS module layers

Trên module path, module resolution quyết định modules nào tham gia graph, còn loader mapping quyết định class được định nghĩa bởi loader nào. Hai class trong cùng module layer không nhất thiết dùng cùng loader, và tên module không thay cho defining loader.

Nên log cả:

```java
Class<?> type = ...;
System.out.println(type.getModule());
System.out.println(type.getClassLoader());
```

Đây là snippet. Khi có module layer tùy chỉnh, cần đối chiếu layer, module graph, service binding và package ownership thực tế.

### 12.3. Framework có loader tree riêng

Application server, OSGi-like framework, test runner, IDE, plugin host và công cụ build có thể:

- Tạo nhiều classloader đồng cấp;
- Delegate theo package/import rules;
- Dùng một loader chung cho API và loader riêng cho implementation;
- Áp dụng URL/classpath transformation hoặc instrumentation;
- Đưa bytes từ network, database, cache hay memory vào `defineClass`.

Vì vậy, parent chain là **điểm bắt đầu**. Khi lớp do loader bất ngờ định nghĩa, phải tìm logic routing và creation của framework, không tự mặc định JDK URLClassLoader thuần.

### 12.4. Class loader lifetime và hot reload

Một plugin có thể được reload với loader mới nhưng host vẫn giữ `Class<?>`/instance từ loader cũ trong cache. Code cùng tên tiếp tục hoạt động theo định nghĩa cũ. `URLClassLoader.close()` **không** tự xóa lớp cũ hoặc ép unload; classloader cũ chỉ có cơ hội được GC khi những đường strong-reference phù hợp biến mất.

Nếu chẩn đoán “đã deploy JAR mới nhưng JVM vẫn chạy class cũ”, cần xác định class object thực tế, defining loader ID, CodeSource và reference giữ phiên bản cũ; đừng chỉ xem nội dung file JAR hiện tại trên đĩa.

## 13. Bổ sung JVM log và công cụ khi parent chain chưa đủ

Nếu cần chứng minh lớp nào đã được JVM load từ nguồn nào, dùng `-Xlog:class+load=info` trên HotSpot và đối chiếu **cùng runtime `Class<?>`**: `getName()`, `getClassLoader()`, `getModule()`, `CodeSource` khi có. Log load ở mức info không ghi lại mọi nhánh `loadClass`/delegation; muốn biết custom routing phải chèn log đúng vào loader do bạn sở hữu.

Dùng `jcmd PID VM.classloaders` để quan sát parent tree của **target JVM** (kiểm tra lệnh hỗ trợ bằng `jcmd PID help`). Khi nghi JAR chứa binary name hoặc ABI trùng, dùng `jar --list` và `javap -s -p` trên từng artifact; chúng là dữ liệu tĩnh, chưa xác nhận bản được chọn ở runtime. Chương có bài riêng giải thích `-Xlog`, ba lệnh `jcmd` và `jar/javap/jdeps`; giữ parent-chain trace trong phần 7 làm bằng chứng thực nghiệm chính của bài này.
## 14. Quy trình chẩn đoán thực tế theo thứ tự ưu tiên

Khi thấy class được nạp “sai JAR/sai loader”:

1. **Lấy đúng `Class<?>`** mà code ứng dụng đang dùng. Nếu có object, ưu tiên `object.getClass()`; nếu có API method, kiểm tra class đang thực sự chứa nó. Tránh gọi `Class.forName` bừa với loader khác rồi tưởng đó là class gây lỗi.
2. **In binary name và defining loader** bằng `type.getName()`, `type.getClassLoader()`. Đối với bootstrap, ghi rõ `<bootstrap/null>`.
3. **Ghi loader nhận yêu cầu** và **TCCL** tách biệt; dùng object ID/registry ID để phân biệt nhiều instance có cùng class name.
4. **Lần theo parent chain** của loader nhận yêu cầu; đừng quên chain có thể kết thúc tại bootstrap khi parent trả null.
5. **Kiểm tra chính sách override** cho namespace bị ảnh hưởng: parent-first, child-first, peer delegation hay module provider resolution.
6. **In module và CodeSource** của Class thực tế khi metadata có sẵn.
7. **Liệt kê URL/resource candidates** bằng `getURLs`, `getResources("pkg/Type.class")` hoặc xem classpath/module path, nhưng không dùng chúng thay defining loader.
8. **Xem log JVM** `-Xlog:class+load` để bổ sung thời điểm và nguồn class; nếu cần, log trong custom `findClass`/`loadClass`.
9. **Đối chiếu trùng binary names và ABI** trong các JAR bằng `jar tf`/`javap`, đặc biệt khi gặp `NoSuchMethodError` hoặc `ClassCastException`.
10. **Kiểm tra loader lifecycle** nếu vừa redeploy plugin: host cache có thể giữ class hoặc instance do loader cũ định nghĩa.
11. **Kiểm tra module graph** nếu dùng JPMS, thay vì chỉ nhìn mảng URL của `URLClassLoader`.
12. **Đánh giá lại policy dependency:** loại bỏ bản JAR trùng khi có thể; đặt shared SPI ở parent và giữ implementation của plugin ở loader riêng.

Một log sự kiện có cấu trúc tốt:

```text
request=42 class=com.example.Service requestLoader=plugin-A
route=parent-first parent=host
result=success definingLoader=host module=<unnamed>
source=file:/deployment/host-api.jar
```

Đây là **log minh họa**, không phải stdout chương trình ở phần 7. Ghi lại **requesting** và **defining** riêng là bước cải thiện quan trọng nhất.

## 15. Những sai lầm thường gặp

| Suy luận sai | Cách hiểu đúng |
| --- | --- |
| “Tôi gọi `child.loadClass` nên class do child định nghĩa.” | Parent-first có thể trả class của parent. Kiểm tra `result.getClassLoader()`. |
| “`child.getParent() == parent` nghĩa mọi class child trả về đều do parent định nghĩa.” | Child có thể tự định nghĩa nếu parent không có class. |
| “`Class.getClassLoader() == null` là lỗi.” | Với `String` trong Java chuẩn, đó là bootstrap. |
| “TCCL của thread chính là defining loader của mọi class trong thread.” | TCCL chỉ là context có thể được một số API chọn dùng. |
| “Hai class có `getName()` bằng nhau thì là cùng kiểu.” | Cần cùng defining loader; có thể là hai runtime types. |
| “`getResources` tìm hai file .class nghĩa là hai runtime classes cùng được child định nghĩa.” | Resource enumeration và class definition khác nhau. |
| “`URLClassLoader.getURLs()` chứa plugin.jar nên mọi class plugin phải từ đó.” | Parent có thể cung cấp class trước, và nguồn gián tiếp cũng có thể tham gia. |
| “CodeSource null nghĩa class không có nguồn hoặc không có loader.” | CodeSource có thể không có metadata; defining loader vẫn xác định được khi có Class object. |
| “Đổi thứ tự URL trong child sẽ thắng bản ở parent.” | Không khi parent-first vẫn chọn parent. |
| “Đóng URLClassLoader sẽ thay class cũ bằng phiên bản mới.” | Close không phải redefine/unload; phiên bản mới thường cần loader mới. |
| “Hai loader cùng trỏ một thư mục nên tạo cùng runtime class.” | Nếu mỗi loader tự định nghĩa, class identity vẫn khác. |
| “Parent chain mô tả toàn bộ mọi cạnh nạp.” | Custom peer delegation/module resolution có thể tạo các đường khác. |
| “Không có class-load log nghĩa loadClass chưa từng được gọi.” | Lời gọi có thể chỉ tái sử dụng class đã load hoặc thất bại trước khi có sự kiện định nghĩa. |
| “Cứ bật child-first cho toàn bộ package để sửa conflict.” | Có thể nhân đôi API/SPI chung và phá type identity. |

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `child.loadClass("pkg.Type")` trả về đối tượng Class mà `getClassLoader() == parent`. Ai định nghĩa class?

**Đáp án:** Parent. Child là nơi nhận yêu cầu, có thể là initiating loader; defining loader là parent.

**Câu 2.** Nếu parent không có `pkg.Helper` nhưng child có bytecode trong JAR riêng, ai có thể định nghĩa?

**Đáp án:** Child, nếu chính sách parent-first đi đến `findClass` của child và class file hợp lệ.

**Câu 3.** Vì sao `Thread.currentThread().getContextClassLoader()` không đủ để biết class `pkg.Type` do ai định nghĩa?

**Đáp án:** TCCL là ngữ cảnh thread cho các API lựa chọn loader; class runtime đã được định nghĩa bởi một loader xác định riêng và không đổi theo TCCL.

**Câu 4.** Hai `URLClassLoader` độc lập có cùng URL tới file `pkg.Type.class`. Có chắc `Class<?>` trả về bằng nhau?

**Đáp án:** Không nếu mỗi loader tự định nghĩa class. Danh tính runtime class phụ thuộc (binary name, defining loader).

**Câu 5.** `getResources("pkg/Type.class")` liệt kê hai URL, nhưng `child.loadClass("pkg.Type")` trả class parent. Đây có mâu thuẫn không?

**Đáp án:** Không. Resource lookup có thể liệt kê nhiều candidate; class loading chọn/tái sử dụng một định nghĩa theo delegation.

**Câu 6.** Công cụ nào quan trọng nhất để kiểm chứng defining loader của một class thật đã được lấy?

**Đáp án:** `type.getClassLoader()` trên chính đối tượng `Class<?>` đó. Bổ sung CodeSource/module/log khi muốn biết nguồn và bối cảnh.

**Câu 7.** Vì sao `Class.forName(name, false, child)` vẫn có thể trả class của parent?

**Đáp án:** Loader argument chỉ định nơi **bắt đầu yêu cầu**. Thuật toán delegation của child có thể hỏi parent, parent định nghĩa và trả class.

**Câu 8.** Nếu classloader cha không phải application loader mà là platform loader, nên làm gì trước khi chẩn đoán?

**Đáp án:** In actual `getParent()` chain, đừng áp dụng một hierarchy mặc định cứng nhắc từ tên plugin.

**Câu 9.** Khi hot reload plugin, `CodeSource` vẫn trỏ JAR cũ và defining loader ID cũ. Một khả năng là gì?

**Đáp án:** Có thể host đang giữ Class<?>/instance của phiên bản plugin cũ. Kiểm tra caches, listeners, threads và lifecycle.

**Câu 10.** Khi `NoSuchMethodError` xuất hiện với hai bản thư viện trùng class, chỉ cần in danh sách JAR đang có là đủ chưa?

**Đáp án:** Chưa. Cần xác định chính class runtime đã được chọn, defining loader, CodeSource và method descriptor so với compile-time API.

## 17. Checklist vận hành

- [ ] Lấy đúng `Class<?>`/instance gây vấn đề.
- [ ] Ghi binary name, defining loader object identity, module và CodeSource khi có.
- [ ] Lưu requesting loader khác trường với defining loader và TCCL.
- [ ] In parent chain bắt đầu từ loader nhận yêu cầu.
- [ ] Phân biệt bootstrap (null) với loader object thật.
- [ ] Kiểm tra custom `loadClass`/`findClass`, child-first và peer routes.
- [ ] Không dùng `getResource`/`getResources` thay bằng chứng class identity.
- [ ] Liệt kê JAR candidates và kiểm tra trùng binary name/method signatures.
- [ ] Với URLClassLoader, xem URL order nhưng nhớ parent-first có thể thắng.
- [ ] Với JPMS, ghi module/layer và resolution graph.
- [ ] Với hot reload, kiểm tra các Class<?>/instances/caches của loader cũ.
- [ ] Dùng unified class-load log/jcmd theo khả năng JDK, bảo vệ thông tin nhạy cảm.
- [ ] Đảm bảo host SPI/API chỉ có một định nghĩa runtime chung khi plugin chia sẻ kiểu.
- [ ] Kiểm thử cả nhánh parent sở hữu class và nhánh child tự định nghĩa class.

## 18. Kết luận và nguồn chính thức

**Parent chain trả lời “loader có thể hỏi ai?”; `Class.getClassLoader()` trả lời “ai thật sự định nghĩa class này?”.** Đây là hai câu hỏi khác nhau và đều quan trọng. Khi một class được yêu cầu qua child loader, parent-first delegation có thể khiến nó được định nghĩa ở parent; khi parent không tìm được, child mới có cơ hội định nghĩa local. Hai runtime classes cùng tên nhưng khác defining loader là hai kiểu riêng biệt, dù có cùng code source hay bytecode.

Muốn chẩn đoán đáng tin cậy, hãy xuất phát từ **Class object thật**, ghi rõ requesting/defining loader, lần parent chain, bổ sung module/CodeSource và xem code routing thực tế. Log hệ thống và resource enumeration là bằng chứng phụ trợ, không thay thế quy tắc runtime class identity.

Tài liệu tham khảo chuẩn:

- Java SE 17 `ClassLoader` API (`loadClass`, `findLoadedClass`, `getParent`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 `Class` API (`getClassLoader`, `forName`, `getModule`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17 `URLClassLoader` API (URL search paths, `getURLs`, `close`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- Java SE 17 `ProtectionDomain` / `CodeSource`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/ProtectionDomain.html
- JVMS 17 §5.3 — *Creation of Classes and Interfaces* (defining và initiating loaders): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- JLS 17 §12.2 — *Loading of Classes and Interfaces*: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.2
- Java SE 17 launcher `java` (unified logging, classpath): https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Java SE 17 `jcmd` utility: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html

# 16.8 Quản lý nhiều lớp được sinh, tài nguyên file manager và phiên bản mã biên dịch

Một hệ thống biên dịch Java **lúc chạy** không chỉ chuyển một chuỗi mã nguồn thành một tệp `.class`. Trong ứng dụng thực tế, một lần biên dịch có thể nhận **nhiều source units**, sinh ra **nhiều class files** (bao gồm nested, anonymous, synthetic và các type được annotation processor sinh), đọc nhiều dependency, đồng thời tạo những tài nguyên phụ. Sau đó runtime còn phải quyết định **bộ bytecode nào thuộc cùng một phiên bản**, nạp chúng bằng **class loader nào**, và lúc nào đóng `JavaFileManager`, giải phóng file handles/cache hay bỏ đi sản phẩm biên dịch lỗi.

Đề bài này thuộc chủ đề **16. Biên dịch lúc chạy**. Trọng tâm không phải cú pháp gọi `javac` đơn lẻ, mà là ba trách nhiệm có liên hệ chặt chẽ:

1. **Quản lý toàn bộ đầu ra của một compilation task**: không làm rơi `Outer$Inner.class`, không đè tệp giữa hai lượt, không dùng nhầm dependency hoặc chỉ trả lại bytecode của một lớp chính.
2. **Quản lý vòng đời tài nguyên của file manager**: xác định ai sở hữu `StandardJavaFileManager`/`ForwardingJavaFileManager`, vị trí đọc–ghi, stream, diagnostic, caching và policy về concurrency.
3. **Quản lý phiên bản của mã được biên dịch**: tách compilation result theo version/release, không trộn hai thế hệ có cùng binary name, kiểm tra khả năng chạy trên JVM mục tiêu, và chủ động quản lý class loader/lifecycle.

Ví dụ sử dụng **Java 17+**, dựa trên Java Compiler API (JSR 199, module `java.compiler`). Có hai chương trình độc lập: biên dịch nhiều lớp vào bộ nhớ và nạp hai revision cạnh nhau; biên dịch theo lô ra thư mục tạm, sử dụng lại file manager tuần tự và **không công bố** một lượt biên dịch lỗi. Mã và `stdout` đã được đối chiếu bằng `javac --release 17`.

## 1. Các thành phần của một pipeline biên dịch runtime

| Thành phần | API | Trách nhiệm |
| --- | --- | --- |
| Lấy compiler | `ToolProvider.getSystemJavaCompiler()` | Cung cấp compiler khi runtime có `jdk.compiler`; có thể trả `null` nếu không có |
| Tạo compilation task | `JavaCompiler.getTask(...)` | Nhận options, units, diagnostics và file manager; trả task có `call()` |
| Mã nguồn/bytecode trừu tượng | `JavaFileObject`, `SimpleJavaFileObject` | Đại diện `.java`, `.class` trong file system, bộ nhớ hay nguồn khác |
| Định tuyến input/output | `JavaFileManager` | Tìm source/class/resource ở các `Location` và nhận output cho từng generated class |
| Quản lý file chuẩn | `StandardJavaFileManager` | Đọc/ghi file, jar, path; cấu hình output/classpath/module-path |
| Tùy biến file manager | `ForwardingJavaFileManager` | Ủy quyền phần lớn API; override những thao tác cần chuyển vào bộ nhớ hay kiểm toán |
| Báo lỗi | `DiagnosticCollector<JavaFileObject>` | Thu thập `ERROR`, `WARNING`, dòng/cột, nguồn và thông điệp |
| Nạp kết quả | `ClassLoader` hoặc `URLClassLoader` | Định nghĩa từng class từ **toàn bộ** output bundle, giữ ranh giới phiên bản |

Điểm quan trọng: **`JavaCompiler` không phải class loader**. Biên dịch thành công không đồng nghĩa runtime đã load hoặc khởi tạo lớp. `JavaFileManager` phục vụ trình biên dịch; một `ClassLoader` (hoặc cơ chế định nghĩa lớp thích hợp) xử lý bước nạp mã đã sinh. Cả hai có vòng đời và trách nhiệm khác nhau.

### 1.1. `getTask` nhận những dữ kiện gì?

```java
JavaCompiler.CompilationTask task = compiler.getTask(
        null,            // Writer cho output không phải diagnostic chuẩn
        fileManager,     // JavaFileManager: input/output routing
        diagnostics,     // DiagnosticListener
        options,         // e.g. ["--release", "17", "-proc:none"]
        null,            // classes: tên class cho annotation processing
        compilationUnits // Iterable<? extends JavaFileObject>
);
boolean success = Boolean.TRUE.equals(task.call());
```

Đây là **đoạn minh họa**, cần các biến đã được khai báo/import. `call()` thực hiện task; một `CompilationTask` **không được gọi lại** để biên dịch một phiên bản khác. Muốn build mới, lấy **task mới**, và tùy chiến lược tái sử dụng hoặc tạo mới file manager.

Không phụ thuộc vào việc `getTask` trả thành công là mọi bytecode đã được **công bố an toàn** cho các request khác. Compiler có thể tạo một phần output trước khi phát hiện lỗi ở unit khác; lớp điều phối phải kiểm tra kết quả rồi mới quyết định publish **cả bundle**. Kể cả khi `call()` trả true, quy trình kiểm tra/đóng gói và xác nhận dependency vẫn là trách nhiệm ứng dụng.

## 2. Một lượt biên dịch có thể tạo nhiều lớp hơn số tệp .java

Ví dụ có hai units:

```java
// Helper.java
package demo.generated;
public class Helper {
    public static String prefix() { return "Hello, "; }
}

// Greeter.java
package demo.generated;
public class Greeter {
    public String greet(String name) {
        return Helper.prefix() + name + "@" + new Info().tag();
    }
    static class Info {
        String tag() { return "v1"; }
    }
}
```

Đây là hai tệp riêng được viết liền để minh họa; **không** lưu cả hai `public class` trong một tệp. Khi biên dịch cùng lúc, compiler tạo ít nhất:

```text
demo/generated/Helper.class
demo/generated/Greeter.class
demo/generated/Greeter$Info.class
```

Đừng cố tự dự đoán đầy đủ danh sách output từ số lượng units. Với local class, anonymous class, lambda/bridge, annotation processing hoặc các biến thể bytecode của compiler, số lượng và tên output thực tế có thể khác.

- Mỗi `getJavaFileForOutput(location, className, kind, sibling)` với `kind == CLASS` là **một sản phẩm output cần giữ**.
- Với nested class, `className` có thể là `demo.generated.Greeter$Info`; hãy dùng **binary name do compiler cung cấp**, không tự ghép bằng tên source.
- Cùng một unit có thể định nghĩa thêm package-private top-level classes, vì thế `Greeter.java` không nhất thiết chỉ cho `Greeter.class`.
- Nếu để compiler ghi ra thư mục, kiểm kê tất cả `.class` thực tế trong output riêng biệt của task.
- Nếu lưu in-memory, map **binary name → toàn bộ byte[]**, gồm nested/secondary classes. Không chỉ lấy bytecode của class public.

**Một batch cho các units phụ thuộc nhau** thường đơn giản nhất. Ví dụ `Greeter` gọi `Helper`, cho cả hai `JavaFileObject` vào cùng `getTask` để compiler tự resolve phụ thuộc nội bộ. Biên dịch `Greeter` ở task tách biệt khi `Helper` chỉ đang nằm trong một byte[] map riêng có thể thất bại: compiler cần một `CLASS_PATH`/`MODULE_PATH` hoặc file manager input biết tìm `Helper.class`. **Class loader của ứng dụng không tự trở thành classpath của compiler**.

### 2.1. Không nhầm tên file với binary name

`demo.generated.Greeter` là binary name, còn `demo/generated/Greeter.class` là cách ánh xạ path thường gặp. `Greeter$Info` là binary name của nested type, **không phải `Greeter.Info`** khi gọi `ClassLoader.loadClass`. Trong code Java nguồn, ta viết `Greeter.Info`; trong file manager/class loader, lớp đó thường có tên binary `demo.generated.Greeter$Info`.

Một `JavaFileObject` cho source trong bộ nhớ nên có URI tuyệt đối, ví dụ:

```java
URI.create("string:///demo/generated/Greeter.java");
```

`SimpleJavaFileObject` dùng URI này như identity mô tả source. Không tạo URI tương đối như `Greeter.java`; một số compiler/file manager dựa vào URI để chẩn đoán và kiểm tra nguồn. Nếu mã hoặc tên lớp đến từ người dùng, **validate binary name và escape/encode đường dẫn đúng cách**, tránh ghép vô điều kiện thành filesystem path.

## 3. Vòng đời và ownership của JavaFileManager

`StandardJavaFileManager` là một **resource owner**. Nó có thể giữ stream, zip/jar file handles, cache và các cấu trúc file system khác; vì vậy luôn xác định nơi thực hiện `close()`. Javadoc `JavaCompiler` thậm chí đề xuất **tái sử dụng một standard file manager cho nhiều compilation tasks tuần tự** để có thể giảm chi phí quét jar/file system, rồi đóng sau cùng.

Một mô hình dễ quản lý:

```text
create compiler
  |
  +--> open StandardJavaFileManager
         |
         +--> task revision A (sources + options + output A)
         +--> task revision B (sources + options + output B)
         |
         +--> close file manager (end of scope)
  |
  +--> publish validated bundle(s)
  |
  +--> separate runtime ClassLoader generation(s)
```

**Các nguyên tắc:**

1. Dùng `try-with-resources` cho `StandardJavaFileManager` hay wrapper `ForwardingJavaFileManager`. `close()` giải phóng tài nguyên của manager (và với forwarding manager chuẩn, gọi close của delegate).
2. `flush()` chỉ đẩy/hoàn thiện output đã buffer; **không đồng nghĩa `close()`**. Đừng dựa vào `flush()` như cách đóng mọi jar handles hoặc resource.
3. Có thể dùng **một manager cho nhiều tasks tuần tự**; nhưng `JavaFileManager` **không bắt buộc synchronized cho mọi phương thức**. Không đồng thời chạy nhiều `CompilationTask` dùng chung mutable manager rồi mặc định thread-safe.
4. `JavaFileManager` có nghĩa vụ hỗ trợ concurrent access tới **những file objects khác nhau** mà nó tạo, nhưng điều này **không** bảo đảm thread-safe toàn bộ manager hay state của custom map.
5. Nếu ứng dụng xử lý nhiều job song song, ưu tiên **manager/compilation context riêng cho từng job**; nếu cần cache chia sẻ, hãy thiết kế explicit synchronization và không chia sẻ output mutable.
6. Đóng manager không unload những `Class<?>` đã được class loader định nghĩa; lifecycle compilation và lifecycle execution là hai việc riêng.
7. Đừng tái sử dụng cùng một output directory cho các version nếu yêu cầu atomic publish hoặc rollback. Một task lỗi có thể để lại file partial; việc overwrite class file đang dùng bởi loader còn dẫn đến hành vi khó đoán.

### 3.1. Standard manager và forwarding manager

`StandardJavaFileManager` làm việc với `Path` và `File`, hỗ trợ cấu hình `StandardLocation.CLASS_OUTPUT`, `CLASS_PATH`, `SOURCE_PATH`, `ANNOTATION_PROCESSOR_PATH`, `SOURCE_OUTPUT` hoặc các location liên quan JPMS. Ví dụ:

```java
try (StandardJavaFileManager fm =
         compiler.getStandardFileManager(diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
    fm.setLocationFromPaths(StandardLocation.CLASS_OUTPUT, List.of(outputDir));
    Iterable<? extends JavaFileObject> units =
        fm.getJavaFileObjectsFromPaths(List.of(sourceA, sourceB));
    boolean success = Boolean.TRUE.equals(
        compiler.getTask(null, fm, diagnostics,
            List.of("--release", "17", "-proc:none"),
            null, units).call());
}
```

Đoạn trên là **khung minh họa** với biến `compiler`, `diagnostics`, `outputDir`, `sourceA` và `sourceB`. Chương trình đầy đủ ở phần 6.

`ForwardingJavaFileManager<StandardJavaFileManager>` có thể override riêng `getJavaFileForOutput` để bắt bytecode vào `ByteArrayOutputStream`, trong khi các hoạt động khác (đọc standard modules, classpath, jar) chuyển tiếp xuống standard manager. Đây là cách thực dụng cho **in-memory compiler**.

**Cảnh báo:** một forwarding manager chỉ override output `CLASS` chưa chắc hỗ trợ **hoàn toàn** chế độ in-memory khi có annotation processors hoặc resource generators. `Filer.createSourceFile`, `Filer.createResource` có thể sử dụng `SOURCE_OUTPUT`/`CLASS_OUTPUT` qua những phương thức khác như `getFileForOutput`. Cần bổ sung routing cho source/resource, đường input tương ứng và rounds processing nếu cho phép annotation processing.

## 4. Ví dụ đầy đủ 1: biên dịch nhiều class vào memory, nạp v1/v2 riêng

Chương trình này thực hiện trong **một file Java nguồn**:

- Tạo **hai compilation units** `demo.generated.Helper` và `demo.generated.Greeter`.
- Bắt **mọi output `CLASS`** vào map trong `MemoryManager`, bao gồm `Greeter$Info`.
- Biên dịch phiên bản `v1` với `--release 11` và `v2` với `--release 17`.
- Kiểm tra **major version** của class file, dùng hai `ClassLoader` riêng để nạp cùng binary name của hai revision.
- Không publish map nếu task thất bại; manager được đóng bằng try-with-resources.
- Cố ý dùng `-proc:none` để ví dụ chỉ làm việc với source/class, không chạy annotation processors.

Lưu đúng tên **`InMemoryVersionsDemo.java`**:

```java
import javax.tools.*;
import java.io.*;
import java.lang.reflect.Method;
import java.net.URI;
import java.util.*;

public class InMemoryVersionsDemo {
    static final class Source extends SimpleJavaFileObject {
        private final String code;
        Source(String binaryName, String code) {
            super(URI.create("string:///" + binaryName.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.code = code;
        }
        @Override public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    static final class Bytecode extends SimpleJavaFileObject {
        private final ByteArrayOutputStream data = new ByteArrayOutputStream();
        Bytecode(String binaryName) {
            super(URI.create("mem:///" + binaryName.replace('.', '/')
                    + Kind.CLASS.extension), Kind.CLASS);
        }
        @Override public OutputStream openOutputStream() { return data; }
        byte[] bytes() { return data.toByteArray(); }
    }

    static final class MemoryManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        private final Map<String, Bytecode> compiled = new TreeMap<>();
        MemoryManager(StandardJavaFileManager standard) { super(standard); }

        @Override public JavaFileObject getJavaFileForOutput(
                Location location, String className, JavaFileObject.Kind kind,
                FileObject sibling) throws IOException {
            if (location == StandardLocation.CLASS_OUTPUT
                    && kind == JavaFileObject.Kind.CLASS) {
                Bytecode file = new Bytecode(className);
                if (compiled.putIfAbsent(className, file) != null)
                    throw new IOException("Duplicate class output: " + className);
                return file;
            }
            return super.getJavaFileForOutput(location, className, kind, sibling);
        }

        Map<String, byte[]> snapshot() {
            Map<String, byte[]> result = new TreeMap<>();
            compiled.forEach((name, file) -> result.put(name, file.bytes()));
            return Collections.unmodifiableMap(result);
        }
    }

    static Map<String, byte[]> compile(String revision, int release)
            throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null)
            throw new IllegalStateException("Run on a JDK with jdk.compiler");

        String prefix = switch (revision) {
            case "v1" -> "Hello, ";
            case "v2" -> "Hi, ";
            default -> throw new IllegalArgumentException("Unknown revision");
        };

        String helper = "package demo.generated;\n"
                + "public class Helper { public static String prefix() { "
                + "return \"" + prefix + "\"; } }\n";
        String greeter = "package demo.generated;\n"
                + "public class Greeter {\n"
                + "  public String greet(String name) { "
                + "return Helper.prefix() + name + \"@\" "
                + "+ new Info().tag(); }\n"
                + "  static class Info { String tag() { "
                + "return \"" + revision + "\"; } }\n"
                + "}\n";
        List<JavaFileObject> units = List.of(
                new Source("demo.generated.Helper", helper),
                new Source("demo.generated.Greeter", greeter));

        DiagnosticCollector<JavaFileObject> diagnostics = new DiagnosticCollector<>();
        try (MemoryManager manager = new MemoryManager(
                compiler.getStandardFileManager(
                        diagnostics, Locale.ROOT,
                        java.nio.charset.StandardCharsets.UTF_8))) {

            List<String> options = List.of("--release", String.valueOf(release),
                    "-proc:none", "-encoding", "UTF-8");
            boolean ok = Boolean.TRUE.equals(compiler.getTask(
                    null, manager, diagnostics, options, null, units).call());
            if (!ok) {
                for (Diagnostic<? extends JavaFileObject> d
                        : diagnostics.getDiagnostics()) {
                    System.err.println(d.getKind() + " line "
                            + d.getLineNumber() + " "
                            + d.getMessage(Locale.ROOT));
                }
                throw new IllegalStateException(
                        "Compilation failed for " + revision);
            }
            return manager.snapshot();
        }
    }

    static final class VersionLoader extends ClassLoader {
        private final Map<String, byte[]> bytecode;
        VersionLoader(Map<String, byte[]> bytecode) {
            super(InMemoryVersionsDemo.class.getClassLoader());
            this.bytecode = bytecode;
        }

        @Override protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            byte[] bytes = bytecode.get(name);
            if (bytes == null) throw new ClassNotFoundException(name);
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    static int classMajor(byte[] b) {
        return ((b[6] & 0xff) << 8) | (b[7] & 0xff);
    }

    public static void main(String[] args) throws Exception {
        Map<String, byte[]> v1 = compile("v1", 11);
        Map<String, byte[]> v2 = compile("v2", 17);
        System.out.println("classes=" + v1.keySet());
        System.out.println("v1 major="
                + classMajor(v1.get("demo.generated.Greeter")));
        System.out.println("v2 major="
                + classMajor(v2.get("demo.generated.Greeter")));

        VersionLoader loader1 = new VersionLoader(v1);
        VersionLoader loader2 = new VersionLoader(v2);
        Class<?> first = loader1.loadClass("demo.generated.Greeter");
        Class<?> second = loader2.loadClass("demo.generated.Greeter");
        Method greet1 = first.getMethod("greet", String.class);
        Method greet2 = second.getMethod("greet", String.class);
        System.out.println("v1=" + greet1.invoke(
                first.getConstructor().newInstance(), "Ada"));
        System.out.println("v2=" + greet2.invoke(
                second.getConstructor().newInstance(), "Ada"));
        System.out.println("sameClass=" + (first == second));
        System.out.println("sameName="
                + first.getName().equals(second.getName()));
    }
}
```

Biên dịch/running bằng JDK 17 hoặc cao hơn (lệnh `javac` dành cho **lớp host**, không phải hai source sinh trong string):

```bash
javac --release 17 InMemoryVersionsDemo.java
java InMemoryVersionsDemo
```

`stdout` đầy đủ đã kiểm tra:

```text
classes=[demo.generated.Greeter, demo.generated.Greeter$Info, demo.generated.Helper]
v1 major=55
v2 major=61
v1=Hello, Ada@v1
v2=Hi, Ada@v2
sameClass=false
sameName=true
```

### 4.1. Tại sao phải giữ ba class files?

Khi gọi `Greeter.greet`, method cần tới `Helper.prefix()` **và** `Greeter$Info.tag()`. Nếu cache chỉ giữ `demo.generated.Greeter.class`, lời gọi có thể ném `NoClassDefFoundError` khi JVM cần load một class phụ chưa có. Vì vậy `MemoryManager` lưu **mọi `className`** mà compiler đưa tới `getJavaFileForOutput`, không hardcode một tên Greeter.

`TreeMap` chỉ làm output danh sách có thứ tự ổn định để demo; production có thể dùng map khác. `Collections.unmodifiableMap` ngăn sửa cấu trúc map, **không** bảo vệ nội dung của từng `byte[]` khỏi sửa đổi. Nếu bundle đi qua ranh giới không đáng tin, cần clone các mảng khi lưu/đưa ra hoặc dùng cấu trúc immutable đủ mạnh.

### 4.2. Vì sao v1 và v2 cùng tên nhưng khác Class?

`Class<?>` identity trên JVM phụ thuộc **binary name + defining class loader** (cùng các quy tắc nạp lớp khác). `v1` và `v2` đều định nghĩa `demo.generated.Greeter`, nhưng `loader1 != loader2` nên:

- `first.getName().equals(second.getName())` là true;
- `first == second` là false;
- các static fields của hai bản là những trạng thái riêng, nếu không trỏ đến state chia sẻ khác từ parent loader;
- một object v1 **không phải instance của Class v2** và không được cast mù giữa các generation.

`VersionLoader` chỉ override `findClass`. Nó vẫn dùng cơ chế **parent-first** mặc định của `ClassLoader.loadClass`. Ví dụ hoạt động vì parent loader **không có** `demo.generated.Greeter` hoặc `Helper`. Nếu parent đã load lớp cùng binary name, class loader có thể trả **bản của parent** thay vì bytes mới; production phải quản lý tên namespace, parent policy và loader architecture có chủ đích.

### 4.3. Vì sao một source host Java 17 tạo bytecode Java 11?

`InMemoryVersionsDemo` là chương trình host Java 17 (dùng switch expression và những API hiện đại). Nhưng source **được tạo dưới dạng string** chỉ sử dụng cú pháp tương thích release 11. Compiler task `compile("v1",11)` truyền `--release 11`, do đó `Greeter.class` có **major version 55**. Phiên bản v2 dùng `--release 17`, tạo major **61**. **Release của compiler output không bị quyết định bởi release của ứng dụng host**; nó do options của từng task quyết định trong giới hạn compiler hỗ trợ.

Bản v1 có thể chạy trên Java 11 nếu **toàn bộ** code và dependencies tương thích, không chỉ vì class header ghi 55. Đây là điều kiện cần, không phải chứng cứ đủ về mọi dependency, module, native library hoặc môi trường runtime.

### 4.4. Một vài giới hạn được giữ cố ý trong ví dụ

- Không dùng annotation processing (`-proc:none`). Muốn hỗ trợ generated source/resource, phải mở rộng file manager hơn chỗ override `CLASS_OUTPUT`.
- `MemoryManager` mới cho mỗi revision. Điều này tránh output của v1 còn tồn tại khi build v2. Compiler object có thể được tạo mới; đây là ví dụ chọn isolation thay vì tối đa hóa cache.
- `VersionLoader` nhận toàn bộ map bytes. Nó chỉ chịu trách nhiệm `findClass`, không tự scan file system. Với code không đáng tin, một loader thông thường **không phải sandbox**.
- `classMajor` chỉ minh họa đọc hai byte major tại offset 6–7 theo JVMS; production phải kiểm tra header `CAFEBABE`, chiều dài, minor/preview version, checksum/chữ ký và format trước khi tin bytes.
- `String` source trong demo ghép từ **revision do chính chương trình kiểm soát**, không chèn trực tiếp input tùy ý. Với user-supplied source, phải áp dụng validation, phân quyền và isolation.

## 5. Version của mã biên dịch có ít nhất ba nghĩa

Một ứng dụng “biên dịch v2” nên nói rõ **v2 là gì**:

1. **Bytecode target release**: `--release 8/11/17/...` quyết định ngôn ngữ/API Java chuẩn mục tiêu và classfile format; chọn theo JVM cần chạy.
2. **Revision của source/logic**: `v1`, `v2`, commit hash, schema version hoặc generation number. Hai revision có thể cùng `--release 17` nhưng cho hành vi khác nhau.
3. **Thế hệ runtime đã load**: một `ClassLoader`/module layer và những Class objects cụ thể. Hai bundle có bytes giống nhau vẫn có thể được định nghĩa trong hai loaders khác nhau, tạo class identities khác nhau.

Không nên đồng nhất một khái niệm với hai khái niệm còn lại. Một ví dụ về manifest có thể là:

```text
bundleId=orders-eval-v2
sourceDigest=SHA256(source files + normalized config)
compilerJdk=21.x
options=--release 17 -proc:none -encoding UTF-8
targetClassMajor=61
dependencies=exact artifact IDs / checksums
outputClasses=demo.generated.Helper,demo.generated.Greeter,demo.generated.Greeter$Info
loaderGeneration=17
buildStatus=VALIDATED
```

Đây là **mẫu metadata minh họa**, không phải output của chương trình. Đừng gán `sourceDigest` một hash bịa đặt. Khi cần build reproducibility, hash phải bao phủ các inputs có ảnh hưởng đến output; không chỉ nội dung của một file Java.

### 5.1. `--release`, `-source` và `-target`

| Option | Tác dụng | Lưu ý |
| --- | --- | --- |
| `--release N` | Biên dịch theo cú pháp và public platform API của bản N, sinh class version tương ứng | Khuyến nghị khi cần chạy trên bản Java cũ được compiler hỗ trợ |
| `-source N` | Giới hạn tính năng cú pháp nguồn | Không tự cấm gọi platform API mới nếu đang dùng JDK mới |
| `-target N` | Chọn class file format | Không tự xác thực platform API thực sự tồn tại trên JDK N |
| `-encoding UTF-8` | Quy định encoding của source đọc từ file | Giữ tính nhất quán khi compile trên nhiều máy |
| `-proc:none` | Tắt annotation processing | Hữu ích cho demo có nguồn kiểm soát; không dùng nếu project cần code generated từ processors |

Theo tài liệu `javac` Java 17, nên dùng `--release` thay vì tự phối `-source`/`-target` khi cần API compatibility với release cũ. Tuy nhiên, nó **không bảo đảm** tương thích với một thư viện third-party ở runtime, phiên bản module, cấu hình dịch vụ hay native dependencies. Compiler của từng JDK chỉ hỗ trợ một tập release mục tiêu nhất định; kiểm tra options và môi trường thật.

### 5.2. Classfile major và UnsupportedClassVersionError

Những mốc thông dụng:

| Java release | Classfile major |
| --- | --- |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Nếu biên dịch thành major 65 mà triển khai trên Java 17 (thường hỗ trợ đến major 61), JVM sẽ từ chối load bằng `UnsupportedClassVersionError`, không phải tự chạy phiên bản mới hơn. Nhưng chỉ đọc major cũng chưa đảm bảo an toàn: bytes có thể bị lỗi, phụ thuộc API không có hoặc có minor version đặc thù cho preview features.

**Không coi `--release N` là công tắc “chạy đúng N trên mọi server”**. Nó chủ yếu kiểm soát cú pháp, classfile và platform API. Hãy test bundle và dependencies bằng JVM đích, kiểm soát compiler flags, annotation processors và module path.

## 6. Ví dụ đầy đủ 2: StandardJavaFileManager, thư mục output riêng và lỗi build

Ví dụ này cho thấy phương án **ghi class files ra ổ đĩa** thay vì memory:

- Tạo workspace tạm bằng `Files.createTempDirectory`.
- Biên dịch cùng batch hai source files có phụ thuộc, ghi vào thư mục `good`.
- Nạp output bằng một `URLClassLoader` rồi **đóng loader**.
- Tái sử dụng **cùng StandardJavaFileManager theo thứ tự tuần tự** cho một task có source lỗi, nhưng đổi output sang `rejected`.
- Không ghi đè hay publish output `good` vì compilation thứ hai thất bại.
- Dọn chính thư mục tạm do chương trình tạo, không đụng tài nguyên project khác.

Lưu tệp **`BatchFileManagerDemo.java`**:

```java
import javax.tools.*;
import java.io.IOException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.stream.Stream;

public class BatchFileManagerDemo {
    static List<String> names(Path root) throws IOException {
        try (Stream<Path> paths = Files.walk(root)) {
            return paths.filter(p -> p.toString().endsWith(".class"))
                    .map(p -> root.relativize(p).toString().replace('\\', '/'))
                    .sorted().toList();
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null)
            throw new IllegalStateException("Requires a JDK compiler");

        Path root = Files.createTempDirectory("batch-compile-");
        try {
            Path src = root.resolve("src/demo/job");
            Path good = root.resolve("good");
            Path rejected = root.resolve("rejected");
            Files.createDirectories(src);
            Files.createDirectories(good);
            Files.createDirectories(rejected);

            Path helper = src.resolve("Helper.java");
            Path worker = src.resolve("Worker.java");
            Path broken = src.resolve("Broken.java");

            Files.writeString(helper,
                    "package demo.job; public class Helper { "
                    + "public static int value() { return 6; } }",
                    StandardCharsets.UTF_8);
            Files.writeString(worker,
                    "package demo.job; public class Worker { "
                    + "public int total() { return Helper.value() * 7; } }",
                    StandardCharsets.UTF_8);
            Files.writeString(broken,
                    "package demo.job; public class Broken { int value = ; }",
                    StandardCharsets.UTF_8);

            try (StandardJavaFileManager fm =
                     compiler.getStandardFileManager(
                        null, Locale.ROOT, StandardCharsets.UTF_8)) {

                fm.setLocationFromPaths(StandardLocation.CLASS_OUTPUT,
                        List.of(good));
                DiagnosticCollector<JavaFileObject> goodDiagnostics =
                        new DiagnosticCollector<>();
                boolean success = Boolean.TRUE.equals(compiler.getTask(
                        null, fm, goodDiagnostics,
                        List.of("--release", "17", "-proc:none"),
                        null, fm.getJavaFileObjectsFromPaths(
                                List.of(helper, worker))).call());

                System.out.println("valid=" + success);
                System.out.println("classes=" + names(good));
                try (URLClassLoader loader = new URLClassLoader(
                        new URL[] { good.toUri().toURL() },
                        BatchFileManagerDemo.class.getClassLoader())) {
                    Class<?> cls = loader.loadClass("demo.job.Worker");
                    Object instance = cls.getConstructor().newInstance();
                    System.out.println("result="
                            + cls.getMethod("total").invoke(instance));
                }

                fm.setLocationFromPaths(StandardLocation.CLASS_OUTPUT,
                        List.of(rejected));
                DiagnosticCollector<JavaFileObject> badDiagnostics =
                        new DiagnosticCollector<>();
                boolean bad = Boolean.TRUE.equals(compiler.getTask(
                        null, fm, badDiagnostics,
                        List.of("--release", "17", "-proc:none"),
                        null, fm.getJavaFileObjectsFromPaths(
                                List.of(broken))).call());
                boolean error = badDiagnostics.getDiagnostics().stream()
                        .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR);

                System.out.println("invalid=" + bad);
                System.out.println("hasError=" + error);
                System.out.println("publishedClasses=" + names(good).size());
            }
        } finally {
            try (Stream<Path> paths = Files.walk(root)) {
                for (Path p : paths.sorted(
                        Comparator.reverseOrder()).toList())
                    Files.deleteIfExists(p);
            }
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac --release 17 BatchFileManagerDemo.java
java BatchFileManagerDemo
```

`stdout` chính xác:

```text
valid=true
classes=[demo/job/Helper.class, demo/job/Worker.class]
result=42
invalid=false
hasError=true
publishedClasses=2
```

### 6.1. Ý nghĩa vận hành của ví dụ đĩa

1. `setLocationFromPaths(CLASS_OUTPUT,List.of(good))` hướng output của task thành công vào một thư mục riêng. Không dùng thư mục mã nguồn hay output chung khi cần isolation.
2. `getJavaFileObjectsFromPaths(List.of(helper,worker))` đưa **hai files** vào cùng task; `Worker` có thể resolve `Helper` trong compilation đó.
3. `success=true` là trạng thái compiler. Code vẫn chỉ load lớp **sau khi** đã kiểm tra thành công.
4. `URLClassLoader` cần được đóng để giải phóng những resource/URL handles mà nó nắm giữ. `close()` **không có nghĩa** JVM tự unload những Class objects đã được load; chúng có thể sống khi còn references.
5. Đổi `CLASS_OUTPUT` sang `rejected` chứng minh ta có thể **tái sử dụng StandardJavaFileManager tuần tự** cho task khác. `invalid=false`, `hasError=true` được đọc từ `DiagnosticCollector`.
6. `publishedClasses=2` chứng minh build cũ giữ nguyên. Chương trình **không bao giờ lấy output của build lỗi** để trộn vào bản đã chạy, bất kể thư mục `rejected` có thể có artifact nào do compiler tạo trước khi báo lỗi.
7. Cleanup trong `finally` chỉ xóa đường dẫn mới tạo từ `Files.createTempDirectory`. Trong sản phẩm thực, dọn workspace phải tuân thủ ownership/retention, và tránh xóa folder output đang được loader/process khác sử dụng.

**Quan trọng:** `DiagnosticCollector` có thể chứa nhiều diagnostics; đừng viết test phụ thuộc vào số lượng hoặc nguyên văn tiếng Anh của diagnostic message giữa các phiên bản `javac`. Ví dụ chỉ kiểm tra có `ERROR`. Với API thật, ghi log `getKind`, `getCode`, `getSource().toUri()` nếu không null, `getLineNumber`, `getColumnNumber` và message theo locale — có thể redact nếu source nhạy cảm.

## 7. Nếu annotation processing sinh thêm source và resource?

Bật annotation processing (không dùng `-proc:none`) thay đổi đáng kể hình dạng pipeline. Processor chạy theo *rounds* và qua `Filer` có thể tạo:

- `.java` vào `StandardLocation.SOURCE_OUTPUT`;
- `.class` vào `CLASS_OUTPUT`;
- tệp phụ như `META-INF/services/...` hoặc metadata JSON/properties qua `Filer.createResource` và `JavaFileManager.getFileForOutput`.

Bảng phân biệt:

| Nhu cầu | API/file manager | Điều cần quản lý |
| --- | --- | --- |
| Nhận class sinh ra | `getJavaFileForOutput(...,Kind.CLASS,...)` | Mọi binary names, kể cả nested |
| Source do processor tạo | `getJavaFileForOutput(...,Kind.SOURCE,...)` | Location `SOURCE_OUTPUT`, round tiếp theo, identity URI |
| Resource do processor tạo | `getFileForOutput(location,packageName,relativeName,sibling)` | Path theo package, resource kind, duplicate/collision |
| Tra lại class/source đã sinh | `getJavaFileForInput`, `list`, `inferBinaryName` (tùy compiler) | Compiler phải nhìn thấy đúng output/generation |
| Nạp resource lúc chạy | `ClassLoader.getResource(...)` hoặc resource store hợp lệ | Bundling resource cùng classpath và thế hệ loader |

Một custom file manager **chỉ** capture `Kind.CLASS` như `MemoryManager` của phần 4 là phù hợp cho demo tắt processors, nhưng không được quảng cáo là một in-memory Java build system hoàn chỉnh có annotation processors. Muốn chạy annotation processors đáng tin cậy, cần quản lý cả **SOURCE_OUTPUT, CLASS_OUTPUT, resources, các lượt đọc lại source/class và collision policy**, kèm test với processor thật.

### 7.1. Thận trọng với processors

Annotation processors là **code thực thi trong quá trình compilation**, không phải chỉ metadata. Nếu nhận source do người dùng gửi, việc bật processor từ classpath/modulepath có thể khiến plugin không đáng tin được load ngay khi **biên dịch**, trước cả bước load kết quả. Mẫu demo dùng `-proc:none` để tránh biến số đó; còn production phải whitelist processors, pin version, tách environment và áp dụng sandbox/process boundary phù hợp.

Để hỗ trợ processors trong build chính thức, đừng tự tắt một cách âm thầm rồi coi output đã đầy đủ — một framework dùng MapStruct, Dagger, Lombok hoặc processor khác có thể cần những nguồn được sinh để biên dịch thành công. Có thể kiểm soát `-processor`, `-processorpath`, `--processor-module-path` và processor options, đồng thời ghi vào manifest của bundle.

## 8. Nhiều compilation tasks và phụ thuộc giữa các phiên bản

### 8.1. One batch và nhiều batches khác nhau

**Nếu nhiều units có dependency cùng một version**, compile chung một task khi có thể. Nếu chia thành nhiều batches, các outputs từ batch A cần được thấy bởi compiler của B:

- Với file system, đặt thư mục output của A vào **classpath hoặc module path đầu vào của B** thích hợp.
- Với in-memory output, file manager phải triển khai đường **read/list/inferBinaryName** để compiler có thể tìm `.class` của A, hoặc dùng một layer trung gian thực sự cung cấp bytes qua classpath/memory filesystem.
- Không chỉ “để `ClassLoader` nhớ A”. Compiler API dùng file manager và search locations của chính nó, không tự đi hỏi loader ứng dụng mọi type.
- Nếu đang sử dụng JPMS, phải phân biệt **CLASS_PATH**, **MODULE_PATH**, **MODULE_SOURCE_PATH** và output location của module; không dồn tất cả vào package-oriented classpath khi dependency là named module.

Các output nên được gắn với **revision/dependency graph**. Không để revision v2 compile với classfile v1 chỉ vì một output dir cũ vẫn có `Helper.class`, trừ khi đó là một dependency version được **cố ý pin**.

### 8.2. Không “thêm đè” một Class trong cùng loader

Một class loader thường không thể định nghĩa lại cùng binary name với bytes mới bằng `defineClass` như tạo một class thứ hai trong chính loader đó. Gọi `defineClass` lặp cùng tên trong một loader gây `LinkageError`. Nếu lớp đã được load, sửa file `.class` trên đĩa **không** làm JVM tự thay bytecode của `Class<?>` cũ.

Chiến lược cập nhật phổ biến:

1. Biên dịch một **bundle đầy đủ** của revision v2 vào output mới.
2. Kiểm tra/đóng gói.
3. Tạo một **loader generation mới** cho v2 và nạp đúng tập classes.
4. Chuyển một điểm tham chiếu ở tầng application (routing/registry/service handle) sang generation mới theo chính sách đồng bộ.
5. Cho request đã bắt đầu trên v1 hoàn thành với v1; chỉ giải phóng loader cũ khi không còn instance/threads/handles/cache giữ nó.

**Không ép cast giữa các generation** chỉ vì `Class.getName()` giống nhau. Nếu muốn một API chung, định nghĩa interface/DTO ổn định **ở parent loader** và cho các bản generated triển khai nó. Boundary nên dùng interface hoặc dữ liệu có schema, không đưa trực tiếp `demo.generated.Greeter` của v1 cho code kỳ vọng Greeter v2.

### 8.3. Class loader và resource isolation

- Parent-first mặc định ưu tiên lớp đã có trong parent. Đảm bảo namespace generated không xung đột, hoặc có loader policy đã test (tránh child-first rộng bừa bãi cho `java.*`).
- `URLClassLoader.close()` giải phóng tài nguyên mở, nhưng **không** bảo đảm unload class ngay lập tức.
- Memory loader không có file handles như URL loader, nhưng `Class<?>`, `MethodHandle`, static cache, thread context class loader, thread hoặc plugin object vẫn có thể giữ loader sống.
- Một static map `Map<String,Class<?>>` toàn cục có thể làm hỏng hot reload: key chỉ binary name không phân biệt loader generation, và value giữ loader cũ.
- Resource files và class files phải thuộc **cùng bundle version**; không nạp `META-INF/services` của revision cũ vào loader mới khi API kỳ vọng version khác.
- Nếu phải unload an toàn, quản lý in-flight calls, cleanup hooks, references và timeout. GC không phải công cụ quyết định thứ tự rollback nghiệp vụ.

## 9. Xây compilation artifact/bundle bền vững

Một production build artifact nên bao gồm:

```text
CompilationBundle {
  id: logicalName + revision + contentHash
  sourceUnitNames: [binary names...]
  classFiles: Map<binaryName, byte[]>
  resources: Map<relativePath, byte[]>  // if generated
  compiler: JDK build and implementation
  options: --release, classpath, modulepath, processors...
  dependencyDigests: exact resolved dependencies
  diagnostics: captured errors/warnings
  status: BUILDING | VALIDATED | REJECTED | PUBLISHED
}
```

Đây là **thiết kế minh họa**, không phải kiểu Java đã khai báo độc lập. Trong ví dụ memory, output `Map<String,byte[]>` chỉ là **phần classFiles** của cấu trúc lớn hơn.

### 9.1. Build–validate–publish thay vì overwrite trực tiếp

**Một chiến lược đơn giản và an toàn hơn:**

```text
sources + pinned dependencies + compiler options
         |
         v
  isolated task / output staging
         |
      call()
         |
    +----+----+
    |         |
  ERROR       OK
    |         |
 discard     check complete bundle + diagnostics
    |         |
 no publish   verify outputs / source-dependency versions
              |
              v
         publish immutable artifact
              |
              v
         loader generation / atomic route switch
```

Nếu ghi output ra filesystem, có thể dùng thư mục theo UUID/hash cho từng build và **chỉ công bố một manifest/pointer** sau khi mọi bước kiểm tra hoàn thành. Một thao tác rename atomically chỉ có ý nghĩa nếu filesystem/đường đi thực sự hỗ trợ cùng-volume atomic move; với `Files.move(...,ATOMIC_MOVE)` có thể gặp `AtomicMoveNotSupportedException`. Hãy thiết kế fallback, fsync/durability nếu yêu cầu, và không hứa “atomic deploy” chỉ nhờ di chuyển directory.

Nếu lưu trong database/object storage, upload bundle bất biến trước, sau đó update một version pointer có điều kiện/transaction. **Không** phát tán nửa bộ `.class` rồi trông chờ runtime tự chờ phần còn lại xuất hiện.

### 9.2. Khi nào cache compilation result?

Một key cache đúng phải đại diện những đầu vào có thể ảnh hưởng đến class output, ví dụ:

- hash của **toàn bộ source units** sau khi chuẩn hóa encoding và đường dẫn;
- `--release`, các compiler flags ảnh hưởng semantics và processor options;
- compiler implementation/version (nếu yêu cầu deterministic builds);
- resolved classpath/modulepath libraries và checksums;
- annotation processor names/versions/config;
- generated resources hoặc cấu hình feature flags được embed vào source;
- target platform và policy của code generator.

Chỉ hash chuỗi source của class chính rồi bỏ qua helper, dependency hoặc processor có thể cache ra bytecode **sai thế hệ**. Không phụ thuộc hoàn toàn vào timestamp/mtime, vì hai nội dung khác nhau có thể có timestamp giống hoặc cache remote dùng đồng hồ khác.

**Đừng nhầm cache compiled bytes với cache loaded Class:** một bundle bytes có thể tái sử dụng để tạo loader generation khác; còn `Class<?>` gắn với một defining loader cụ thể, nên cache theo binary name thuần túy dễ trộn giữa versions.

## 10. Quản lý concurrent compilation jobs

JavaFileManager không bắt buộc thread-safe toàn bộ API. Nếu nhiều request cùng yêu cầu build:

- Mỗi job có **file manager, diagnostic collector, output store và task riêng**; output directory/map không được shared mutable.
- Nếu cần dedup cùng source hash, một build coordinator có thể dùng `ConcurrentHashMap<Key,CompletableFuture<Bundle>>` hoặc hàng đợi job theo key, nhưng phải thiết kế policy retry/cancel/timeout và cleanup khi lỗi. Đừng đặt nhiều compilation tasks cùng ghi vào một map.
- Pin version của dependencies ở **thời điểm bắt đầu build**: không để một task đọc jar v1 đầu tiên rồi jar v2 ở giai đoạn sau vì thư mục output bị cập nhật.
- Chỉ công bố **bundle đã hoàn tất** qua một reference bất biến/transactional pointer; request chạy v1 giữ reference v1 tới khi kết thúc.
- Nếu có quota bộ nhớ hoặc metaspace, kiểm soát số output bytes, số compiler tasks và số loaders đang sống; cân nhắc TTL/LRU và ràng buộc GC/lifecycle.

**Một lưu ý nhỏ nhưng quan trọng:** `ConcurrentHashMap` làm map an toàn cho từng thao tác nhưng không tự biến một multi-file build thành transaction atomic. Bạn vẫn cần trạng thái build và thời điểm publish riêng.

## 11. Lỗi thường gặp: đọc dấu hiệu và sửa đúng lớp

| Triệu chứng | Nguyên nhân thường gặp | Hướng giải quyết |
| --- | --- | --- |
| `ToolProvider.getSystemJavaCompiler()==null` | Runtime thiếu `jdk.compiler` hoặc dùng image rút gọn | Dùng JDK thích hợp; kiểm tra modules của runtime image |
| `CompilationTask.call()==false` | Source/option/dependency lỗi | Đọc `DiagnosticCollector`; không publish artifact partial |
| `IllegalArgumentException` khi tạo `getTask` | Options/arguments không hợp lệ | Validate options và danh sách units; đừng dựng flag từ raw user string |
| `NoClassDefFoundError` khi chạy | Quên secondary/nested class, sai dependency hoặc class loader | Lưu **mọi generated binary name**; kiểm tra bundle/classpath |
| `ClassNotFoundException` | Loader không tìm binary name | Dùng tên `package.Outer$Inner` cho nested; kiểm tra resource/output map |
| `LinkageError: duplicate class definition` | Cố định nghĩa cùng FQN hai lần trong một loader | Tạo loader generation mới cho revision khác |
| `ClassCastException` giữa hai bản cùng tên | Class identities khác vì loader khác | Dùng API interface ở parent loader hoặc DTO trung lập |
| `UnsupportedClassVersionError` | Output major cao hơn JVM đích | Chọn `--release` đúng; test trên JDK mục tiêu |
| `NoSuchMethodError` lúc runtime | Class compiled chống lại version dependency khác runtime | Pin dependency graph/bundle, kiểm tra binary compatibility |
| `ClassFormatError` hoặc `VerifyError` | Bytecode sai hoặc bị hỏng/mismatch | Kiểm tra bytes và source compiler; không mutate byte[] sau publish |
| Lỗi không ổn định khi build song song | Chia sẻ FileManager/output/cache không đồng bộ | Manager/outputs riêng từng job, coordinator cho duplicate requests |
| File jar bị khóa lâu | `StandardJavaFileManager` hoặc `URLClassLoader` chưa đóng | Dùng try-with-resources, thống kê ownership |
| Code sinh ra chạy bản cũ | Parent loader đã có FQN, hoặc loader/cache không đổi | Giải quyết parent-first collision, tạo loader mới và update route |
| Resource/metadata biến mất | File manager chỉ bắt Kind.CLASS, bỏ `getFileForOutput` | Bổ sung SOURCE_OUTPUT/resources và loader resource lookup |
| Build báo lỗi nhưng còn `.class` cũ | Dùng chung output dir, compiler để lại stale files | Compile trong staging sạch, publish bundle only on success |
| Class loader/metaspace không giải phóng | Còn cache Class/MethodHandle/threads/context loader | Theo dõi references, đóng tài nguyên, lifecycle-aware caching |
| Build khác nhau nhưng cache hit | Cache key thiếu dependencies/options/processor/version | Hash đầy đủ inputs, pin/compiler metadata |
| Compilation qua CPU/memory budget | Không giới hạn resource, processor/cycle input nguy hiểm | Giới hạn job, timeouts, isolate process/container theo chính sách |

### 11.1. Diagnostics: source line, source URI, warning

`DiagnosticCollector<JavaFileObject>` lưu `Diagnostic` với loại, vị trí, mã và thông điệp. Một lỗi có thể có `getSource()==null` hoặc line number là `Diagnostic.NOPOS`; do đó không hardcode rằng lúc nào cũng có path/line. Với compiler options hoặc failures đặc biệt, một số thông tin cũng có thể ghi ra `Writer` truyền ở `getTask` hay output mặc định theo Javadoc. Ứng dụng nên thu thập cả diagnostic listener và lỗi I/O/các exception của task.

**Đừng đưa source bí mật vào exception/log không kiểm soát.** Compiler messages có thể chứa tên class, source path và mảnh code. Gán build ID và phân loại error, warning, note để người dùng sửa mà không lộ mã nguồn của tenant khác.

## 12. An toàn và ranh giới tin cậy

Biên dịch Java từ chuỗi **không** làm mã an toàn. Những nguy cơ cần đánh giá:

- **Code execution:** loader và reflection khi tạo instance hoặc gọi method có thể chạy static initializers, I/O, thread spawning, network/process access dưới quyền process.
- **Compiler plugins/processors:** annotation processors có thể thực thi ngay lúc compile; `-proc:none` trong bài chỉ giảm bớt rủi ro này, không làm source sau biên dịch vô hại.
- **Tài nguyên:** source cố ý tạo rất nhiều classes, vòng annotation processing hoặc nested types có thể làm tràn heap/disk/metaspace.
- **Namespace/dependency confusion:** class cùng binary name giữa tenants hoặc version khác nhau, parent-first loader, sai module path có thể dẫn tới gọi code ngoài dự kiến.
- **Filesystem path injection:** source binary names, package paths, manifest/resource paths và output dir cần được canonicalize/validate; không cho người dùng điều khiển trực tiếp thư mục ghi của process.
- **Deserialization/classpath:** không tải jar/processor/bytecode từ nguồn không tin cậy chỉ vì `CompilationTask.call()==true`.

Nếu phải hỗ trợ chạy **mã Java không đáng tin** từ bên ngoài, cân nhắc **process/container isolation ở OS**, quyền tối thiểu, giới hạn CPU/memory/network/filesystem, giám sát và hủy process. Một custom `ClassLoader` trong cùng JVM không phải security sandbox đầy đủ.

## 13. Checklist triển khai

Trước khi coi một runtime compilation pipeline đủ ổn định, hãy tự trả lời:

1. **Input units:** đã thu đủ source phụ thuộc, package/binary name hợp lệ và không trùng lặp?
2. **Options:** `--release`, encoding, classpath/modulepath và annotation processing có được pin rõ?
3. **Compiler availability:** runtime thật có `jdk.compiler` và JDK hỗ trợ target release?
4. **Manager ownership:** ai tạo, ai đóng; manager có reuse tuần tự hay isolation cho concurrent tasks?
5. **Output completeness:** `getJavaFileForOutput` hoặc thư mục output có ghi mọi generated `.class`, kể cả nested/secondary?
6. **Resources:** processors có tạo source/resources không; `getFileForOutput` và `SOURCE_OUTPUT` đã được xử lý?
7. **Diagnostics:** `call()==true` chưa; lỗi/warning có source location đúng và không lộ tenant data?
8. **Publish:** artifact có được công bố **chỉ sau khi success + validation** dưới một version ID bất biến?
9. **Version compatibility:** target classfile major và toàn bộ dependencies chạy được trên JVM đích?
10. **Classloader:** mỗi generation có loader/resource policy riêng; parent-first collision và interface boundary đã rõ?
11. **Hot reload:** route switch, in-flight tasks và cleanup generation cũ đã có kế hoạch?
12. **Cache:** key có bao gồm source, options, compiler, library digests và processors?
13. **Concurrency:** có build coordinator hoặc output isolation để tránh hai tasks ghi đè nhau?
14. **Security:** nguồn code, processor, bytecode, file paths và runtime execution được kiểm soát theo trust boundary?
15. **Resource limits:** compile timeouts, bytecode size, file handles, threads và metaspace được quan sát?

Nếu chưa trả lời được những câu như **“bản v2 có thể load lại `Helper` của v1 không?”**, **“task lỗi có thể để lại output nào?”**, **“ai close file manager?”**, hoặc **“nếu processor sinh thêm class thì manager tìm ở đâu?”**, pipeline chưa có mô hình vòng đời rõ ràng.

## 14. Bài tập tự kiểm tra

**Bài A — multiple outputs.** Một unit `Outer.java` chứa nested class `Outer.Inner` và anonymous class. In-memory manager chỉ lưu `Outer.class`. Điều gì có thể xảy ra?

**Đáp án:** Khi code cần tới nested/anonymous class, loader không tìm được `Outer$Inner` hoặc `Outer$1` và có thể ném `NoClassDefFoundError`. Phải giữ mọi class outputs do compiler báo, không hardcode số lượng/tên.

**Bài B — class identity.** Hai bundle v1/v2 đều có `pkg.Service`, được nạp bởi hai `ClassLoader` khác nhau. `v1.getName().equals(v2.getName())` và `v1==v2` có thể có giá trị gì?

**Đáp án:** Tên có thể giống nhau (true), nhưng `Class<?>` objects khác identity (false) nếu thực sự được định nghĩa bởi hai loaders khác nhau. Dùng interface ổn định ở parent loader để kết nối nếu cần.

**Bài C — bytecode target.** Host Java 17 gọi compiler với `--release 11` cho một source Java 11 hợp lệ. `.class` có major bao nhiêu?

**Đáp án:** 55, không phải 61. Source host và source được biên dịch là hai chương trình có options khác nhau.

**Bài D — lỗi task.** Task biên dịch ba units báo `false` nhưng output directory có hai `.class`. Có nên publish không?

**Đáp án:** Không. Đó là partial/stale output; bỏ staging của task lỗi, giữ nguyên bundle đã publish.

**Bài E — resource lifetime.** Dùng cùng `StandardJavaFileManager` cho hai tasks **tuần tự**, có cần close cuối cùng không? `flush()` có đủ không?

**Đáp án:** Cần close khi kết thúc lifecycle. Reuse tuần tự được Javadoc khuyến nghị, nhưng flush không thay close; tài nguyên jar/filesystem có thể còn mở.

**Bài F — annotation processor.** File manager custom chỉ override `getJavaFileForOutput(...,Kind.CLASS,...)`. Processor tạo `META-INF/services/example.Service`. Resource đó chắc được lưu vào class map không?

**Đáp án:** Không. Resource sử dụng `getFileForOutput` và resource location, không tự thành `JavaFileObject.Kind.CLASS`. Cần output/resource store tương ứng.

**Bài G — caching.** Code source không đổi, nhưng jar dependency đã thay implementation. Cache key chỉ theo source hash có còn đúng không?

**Đáp án:** Không đủ. Dependency graph/digest, options, compiler/processor version có thể ảnh hưởng output và runtime compatibility.

**Bài H — parent-first.** Bytecode loader chứa `pkg.Widget` v2 nhưng parent đã load `pkg.Widget` v1. Override mỗi `findClass` có đảm bảo load v2 không?

**Đáp án:** Không. `loadClass` thông thường kiểm tra parent trước; cần namespace/parent policy được thiết kế để tránh collision, đồng thời tách loader generation.

**Bài I — release vs source.** Vì sao `-source 11 -target 11` trên JDK 17 không tương đương đầy đủ `--release 11`?

**Đáp án:** Hai option đầu chủ yếu giới hạn syntax và class format, không tự cấm tham chiếu các Java platform APIs chỉ có từ release mới. `--release` giới hạn public platform API sẵn có ở release mục tiêu.

**Bài J — memory map.** `Collections.unmodifiableMap(Map<String,byte[]>)` đã làm mọi bytecode trong map immutable chưa?

**Đáp án:** Chưa. Map không đổi cấu trúc nhưng `byte[]` values vẫn có thể bị sửa nếu ai đó giữ reference. Cần snapshot/defensive copy hay immutable binary container ở trust boundary.

## 15. Nguồn tài liệu chính thức

- [Oracle JDK 17 — `JavaCompiler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html): `getTask`, diagnostics, file manager lifecycle và reuse tuần tự.
- [Oracle JDK 17 — `JavaFileManager`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaFileManager.html): locations, `getJavaFileForOutput`, `getFileForOutput`, `close`/`flush`, concurrency limits.
- [Oracle JDK 17 — `StandardJavaFileManager`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html): path-based units, `setLocationFromPaths` và file manager hoạt động trên file system.
- [Oracle JDK 17 — `ForwardingJavaFileManager`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ForwardingJavaFileManager.html): override một số phương thức, delegation cho manager chuẩn.
- [Oracle JDK 17 — `SimpleJavaFileObject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html): nguồn dạng string và output objects tùy biến.
- [Oracle JDK 17 — `DiagnosticCollector`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/DiagnosticCollector.html): lấy diagnostics từ compilation task.
- [Oracle JDK 17 — `javax.annotation.processing.Filer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html): nguồn class/source/resource do annotation processors tạo.
- [Oracle JDK 17 — `javac` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `--release`, `-d`, classpath/module-path, annotation processing và nhiều source files.
- [Oracle JDK 17 — `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findClass`, `defineClass` và parent delegation.
- [Oracle JDK 17 — `URLClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): nạp classes/resources từ URL và đóng loader.
- [JVMS Java SE 17 `4.1 — `ClassFile`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.1): cấu trúc class file, `major_version`/`minor_version` và format.
- [Oracle JDK 17 — `ToolProvider`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html): tìm system Java compiler, kiểm tra khả năng có sẵn.

**Ghi nhớ:** một compilation task có thể sinh ra nhiều `.class` ngoài các source units. Hãy **thu đủ output**, **đóng hoặc reuse file manager có chủ đích**, **không publish khi build lỗi**, **gắn phiên bản/source/options/dependencies với một bundle bất biến**, và **nạp mỗi generation qua class loader phù hợp**. `--release` xác định mức tương thích bytecode/API Java chuẩn, còn version logic và loader generation là những khái niệm riêng. Tách rõ **build → validate → publish → load → retire** là nền tảng để biên dịch lúc chạy không làm lẫn mã cũ/mới hoặc rò rỉ tài nguyên.

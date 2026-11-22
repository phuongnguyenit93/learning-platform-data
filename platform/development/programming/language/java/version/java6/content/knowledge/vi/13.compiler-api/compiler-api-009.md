# Tách biên dịch khỏi bước nạp và thực thi lớp bằng Java Compiler API

## 1. Ba giai đoạn khác nhau của một chương trình Java

Khi một ứng dụng tạo mã nguồn Java tại thời điểm chạy hoặc nhận mã nguồn từ một công cụ sinh mã, cần phân biệt ba giai đoạn:

1. **Biên dịch (compile):** `JavaCompiler` phân tích mã nguồn `.java` và tạo bytecode `.class` (hoặc báo lỗi cú pháp, kiểu dữ liệu, dependency...). Kết quả thành công là **artifact có thể nạp**, chưa phải kết quả chạy chương trình.
2. **Nạp và liên kết lớp (load/link):** JVM dùng một `ClassLoader` thích hợp để tìm và định nghĩa lớp từ bytecode, kiểm tra và liên kết những thành phần cần thiết. Tải lớp chưa đồng nghĩa chạy phương thức của ứng dụng hay khởi tạo lớp.
3. **Khởi tạo và thực thi (initialize/execute):** JVM khởi tạo lớp khi có tác vụ thuộc nhóm kích hoạt khởi tạo, chẳng hạn gọi một phương thức `static` của lớp chưa được khởi tạo. Sau đó code ứng dụng mới thực sự chạy và tạo kết quả hoặc side effect.

Đây là khác biệt cốt lõi của chủ đề **“Tách biên dịch khỏi bước nạp, thực thi lớp”** trong Compiler API.

~~~text
Mã nguồn .java
      |
      v
JavaCompiler / CompilationTask.call()
      |
      +---- thất bại --> diagnostics; không chuyển sang chạy
      |
      v
Bytecode .class trong output directory
      |
      v
ClassLoader / Class.forName(..., false, loader)
      |
      v
Đối tượng Class<?> (chưa buộc khởi tạo lớp)
      |
      v
Gọi phương thức / Class.forName(..., true, loader)
      |
      v
Khởi tạo lớp nếu cần, sau đó thực thi code
~~~

Java Compiler API `javax.tools` xuất hiện từ Java 6 và **vẫn là API chuẩn trên Java hiện đại**. Các ví dụ bên dưới dùng **JDK 17 trở lên**, chỉ sử dụng API còn được hỗ trợ, phù hợp với một runtime chứa compiler.

### 1.1. Vì sao nên tách?

- **Kiểm tra lỗi sớm:** chỉ nạp khi `CompilationTask.call()` trả về thành công.
- **Quan sát độc lập:** lưu diagnostics của compiler, kiểm tra sự tồn tại của class file, rồi kiểm tra lỗi ở giai đoạn load hoặc invoke bằng loại lỗi phù hợp.
- **Quản lý dependency:** classpath dùng khi **biên dịch** và nơi class loader tìm dependency khi **chạy** là hai cấu hình riêng phải tương thích.
- **Kiểm soát vòng đời:** có thể tạo class loader riêng cho mỗi phiên bản mã sinh ra thay vì trộn tất cả vào classloader của ứng dụng.
- **Tránh side effect ngoài ý muốn:** xác nhận compilation thành công không có nghĩa đã chạy đoạn mã đích; chính ứng dụng chọn thời điểm kích hoạt nó.

Tình huống áp dụng là hệ thống sinh mã, công cụ thử nghiệm, pipeline kiểm tra mã, plugin/script engine có bước tạo `.class`. Với ứng dụng Java thông thường, biên dịch trong quy trình build rồi chạy artifact thường đơn giản và ổn định hơn biên dịch động ở mỗi yêu cầu.

## 2. Các API giữ vai trò gì?

| API | Nhiệm vụ | Không tự làm gì? |
| --- | --- | --- |
| `ToolProvider.getSystemJavaCompiler()` | Lấy trình biên dịch Java được cung cấp bởi môi trường hiện tại | Không tự biên dịch hoặc chạy ứng dụng |
| `JavaCompiler.getStandardFileManager(...)` | Quản lý nguồn, output và tài nguyên của compiler | Không thay cho runtime class loader |
| `JavaFileObject` / `StandardJavaFileManager` | Biểu diễn source file và vị trí biên dịch | Không tự thực thi bytecode |
| `DiagnosticCollector<JavaFileObject>` | Thu lỗi/cảnh báo trong quá trình biên dịch | Không quyết định nạp lớp |
| `JavaCompiler.getTask(...).call()` | Bắt đầu công việc biên dịch, trả `Boolean` thành công/thất bại | Không tự gọi `main()` hay phương thức của lớp vừa sinh |
| `URLClassLoader` | Tạo class loader có thể tìm lớp từ thư mục hoặc JAR được chỉ định | Không biên dịch source |
| `Class.forName(name, false, loader)` | Tìm/nạp lớp mà không yêu cầu khởi tạo lớp | Không tự gọi phương thức nghiệp vụ |
| `Class.getMethod(...).invoke(...)` | Tìm và gọi phương thức bằng reflection | Không sửa lỗi compile đã xảy ra trước đó |

Trên Java hiện đại, các interface/compiler API nằm trong module `java.compiler`; bản triển khai `javac` thường được cung cấp bởi module `jdk.compiler`. `ToolProvider.getSystemJavaCompiler()` **có thể trả về `null`** khi runtime image không chứa compiler, chẳng hạn image tùy chỉnh chỉ gồm module phục vụ chạy ứng dụng. Chương trình cần kiểm tra trường hợp này trước khi gọi API tiếp.

**Lưu ý quan trọng:** compile code trong JVM là thao tác biên dịch, **không tự chạy `main` hay phương thức của lớp vừa biên dịch**. Tuy nhiên trình biên dịch có thể chạy **annotation processors** hoặc plugin được cấu hình cho quá trình biên dịch. Ví dụ học tập bên dưới dùng `-proc:none` để tắt annotation processing và giúp hành vi quan sát ổn định. Không coi biên dịch source từ bên ngoài là một sandbox bảo mật.

## 3. Ví dụ đầy đủ: compile → xác nhận class file → load → invoke

Ví dụ sử dụng một chương trình duy nhất tên `CompileLoadRunDemo.java`. Chương trình tạo Java source trong thư mục tạm, biên dịch bằng `JavaCompiler`, tạo `URLClassLoader` cho output, tải lớp mà **chưa khởi tạo**, sau đó gọi phương thức `static` qua reflection.

Tệp `CompileLoadRunDemo.java`:

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.stream.Stream;
import javax.tools.*;

public final class CompileLoadRunDemo {
    public static void main(String[] args) throws Exception {
        Path work = Files.createTempDirectory("compiler-api-");
        try {
            Path source = work.resolve("src/demo/generated/Hello.java");
            Path output = work.resolve("classes");
            Files.createDirectories(source.getParent());
            Files.createDirectories(output);
            String program = """
                    package demo.generated;

                    public final class Hello {
                        static { System.out.println("initialized"); }

                        public static String greet(String name) {
                            return "Hello, " + name + "!";
                        }
                    }
                    """;
            Files.writeString(source, program, StandardCharsets.UTF_8);

            JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
            if (compiler == null) {
                throw new IllegalStateException("A JDK with jdk.compiler is required");
            }

            DiagnosticCollector<JavaFileObject> diagnostics = new DiagnosticCollector<>();
            boolean compiled;
            try (StandardJavaFileManager files = compiler.getStandardFileManager(
                    diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
                Iterable<? extends JavaFileObject> units =
                        files.getJavaFileObjectsFromPaths(List.of(source));
                compiled = Boolean.TRUE.equals(
                        compiler.getTask(null, files, diagnostics,
                                List.of("-proc:none", "-d", output.toString()),
                                null, units).call());
            }

            System.out.println("compiled=" + compiled);
            if (!compiled) {
                for (Diagnostic<? extends JavaFileObject> d
                        : diagnostics.getDiagnostics()) {
                    System.err.println(d.getKind() + ": "
                            + d.getMessage(Locale.ROOT));
                }
                return;
            }

            System.out.println("class-file=" + Files.exists(
                    output.resolve("demo/generated/Hello.class")));
            try (URLClassLoader loader = new URLClassLoader(
                    new URL[] { output.toUri().toURL() },
                    ClassLoader.getPlatformClassLoader())) {
                Class<?> hello = Class.forName("demo.generated.Hello", false, loader);
                System.out.println("loaded=" + hello.getName());
                System.out.println("before-invoke");
                Object result = hello.getMethod("greet", String.class)
                        .invoke(null, "An");
                System.out.println("result=" + result);
            }
        } finally {
            try (Stream<Path> paths = Files.walk(work)) {
                for (Path p : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(p);
                }
            }
        }
    }
}
~~~

**Lệnh biên dịch và chạy chương trình điều phối** (trong thư mục chứa file):

~~~bash
javac -encoding UTF-8 CompileLoadRunDemo.java
java CompileLoadRunDemo
~~~

**Kết quả quan sát được:**

~~~text
compiled=true
class-file=true
loaded=demo.generated.Hello
before-invoke
initialized
result=Hello, An!
~~~

Ở đây có **hai quá trình biên dịch khác nhau**:

- Lệnh `javac CompileLoadRunDemo.java` ngoài terminal tạo class của **chương trình điều phối**.
- Trong khi `CompileLoadRunDemo` đang chạy, `compiler.getTask(...).call()` biên dịch source `Hello.java` mà nó vừa tạo. Chính `Hello.class` là artifact chúng ta muốn kiểm tra rồi nạp.

## 4. Đọc kết quả theo đúng ranh giới từng giai đoạn

### 4.1. Biên dịch chưa làm chạy code của `Hello`

`getTask(...)` mới tạo `CompilationTask`; gọi `call()` mới thực sự bắt đầu biên dịch. `call()` trả về `true` khi mọi đơn vị biên dịch hoàn thành mà không có lỗi compile; trả về `false` nếu biên dịch không thành công. Một task chỉ được gọi `call()` **một lần**.

Tùy chọn `-d <thư mục>` điều khiển vị trí output: trong bài là `work/classes/demo/generated/Hello.class`. Vì `Hello.java` khai báo package `demo.generated`, JVM mong đợi đường dẫn class file tương ứng dưới classpath root.

Tùy chọn `-proc:none` vô hiệu hóa annotation processing cho bài học. Nó **không** có nghĩa hệ thống JavaCompiler luôn không thực thi bất kỳ code nào trong mọi cấu hình; đó là giới hạn có chủ đích của fixture.

Dòng:

~~~text
compiled=true
class-file=true
~~~

xác nhận hai việc riêng: compiler báo thành công, và artifact được tìm thấy tại output path dự kiến. Nó **chưa** chứng minh lớp đã được load hoặc phương thức `greet` đã chạy.

### 4.2. Nạp lớp không bắt buộc khởi tạo lớp

Phần code:

~~~java
Class<?> hello =
        Class.forName("demo.generated.Hello", false, loader);
System.out.println("loaded=" + hello.getName());
~~~

là **đoạn trích** trong chương trình hoàn chỉnh ở mục 3. Tham số `false` cho biết **không yêu cầu khởi tạo lớp** tại lời gọi `Class.forName`. JVM tìm và nạp lớp từ `URLClassLoader` rồi trả về đối tượng `Class<?>`. Chương trình in:

~~~text
loaded=demo.generated.Hello
before-invoke
~~~

nhưng vẫn chưa in `initialized`.

`ClassLoader.loadClass("demo.generated.Hello")` cũng có thể dùng cho mục đích nạp lớp mà không trực tiếp yêu cầu khởi tạo. Ngược lại, `Class.forName(name, true, loader)` yêu cầu khởi tạo lớp; do đó nếu thay `false` bằng `true` trong ví dụ thì thông báo `initialized` có thể xuất hiện ngay tại bước `Class.forName`.

### 4.3. Khi nào code của lớp mới thực thi?

Đoạn sau trong chương trình chính:

~~~java
Object result = hello.getMethod("greet", String.class)
        .invoke(null, "An");
System.out.println("result=" + result);
~~~

tìm phương thức công khai `public static String greet(String)` bằng reflection. Vì là phương thức `static` nên đối số receiver của `invoke` là `null`. Đối số `"An"` được truyền cho tham số `String`.

Lời gọi phương thức `static` khiến JVM khởi tạo `Hello` nếu chưa khởi tạo, vì vậy mới xuất hiện:

~~~text
initialized
result=Hello, An!
~~~

Đây là bằng chứng quan sát được của **thứ tự**: compile thành công → tìm thấy file → load class → kích hoạt init khi invoke → chạy logic trong `greet`.

Không đánh đồng việc **compile thành công** với **thực thi thành công**: phương thức Java hợp lệ vẫn có thể ném ngoại lệ nghiệp vụ khi chạy.

### 4.4. Vì sao dùng `URLClassLoader` với classpath root là thư mục `classes`?

`Class.forName("demo.generated.Hello", ..., loader)` nhận **binary name** có package, không nhận tên đường dẫn `demo/generated/Hello.class`. `URLClassLoader` được cấu hình với URL trỏ tới **gốc output** (`work/classes`), từ đó class loader mới có thể tìm file `demo/generated/Hello.class`.

Ví dụ dùng `ClassLoader.getPlatformClassLoader()` làm parent vì source sinh ra chỉ phụ thuộc Java platform; nhờ vậy không vô tình ưu tiên một class cùng tên đã có trên application classpath. Trong ứng dụng thật, source sinh ra có thể cần dùng interface chung của host. Khi ấy phải chọn parent loader và dependency URLs để **cả phía compile và runtime đều thấy cùng API**, tránh làm lệch danh tính kiểu.

`URLClassLoader` triển khai `AutoCloseable` và được đóng bằng `try-with-resources`. Việc đóng loader giúp giải phóng tài nguyên truy cập JAR/URL; **nó không bắt JVM ngay lập tức unload những class đã được nạp**.

## 5. Trường hợp lỗi compile: phải dừng trước load

Để xác nhận nhánh thất bại, tạo tệp độc lập `CompilerErrorDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.List;
import javax.tools.*;

public class CompilerErrorDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("compiler-error-");
        try {
            Path src = root.resolve("Broken.java");
            Files.writeString(src, "public class Broken { int n = ; }",
                    StandardCharsets.UTF_8);
            JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
            if (compiler == null) {
                throw new IllegalStateException("JDK compiler unavailable");
            }
            DiagnosticCollector<JavaFileObject> diagnostics =
                    new DiagnosticCollector<>();
            boolean success;
            try (StandardJavaFileManager fm = compiler.getStandardFileManager(
                    diagnostics, null, StandardCharsets.UTF_8)) {
                var units = fm.getJavaFileObjectsFromPaths(List.of(src));
                success = Boolean.TRUE.equals(compiler.getTask(null, fm,
                        diagnostics, List.of("-proc:none", "-d", root.toString()),
                        null, units).call());
            }
            boolean hasErrors = diagnostics.getDiagnostics().stream()
                    .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR);
            System.out.println("compiled=" + success);
            System.out.println("has-errors=" + hasErrors);
            System.out.println("class-file=" + Files.exists(
                    root.resolve("Broken.class")));
        } finally {
            try (var paths = Files.walk(root)) {
                for (Path p : paths.sorted(
                        java.util.Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(p);
                }
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 CompilerErrorDemo.java
java CompilerErrorDemo
~~~

Output từ trường hợp lỗi cú pháp cố ý:

~~~text
compiled=false
has-errors=true
class-file=false
~~~

`DiagnosticCollector` thu các `Diagnostic` và cho phép kiểm tra `Diagnostic.Kind.ERROR`, vị trí dòng/cột, mã lỗi và thông báo. Tránh viết test phụ thuộc chính xác câu chữ thông báo lỗi của compiler: văn bản có thể khác giữa môi trường, locale và phiên bản JDK. Ở ví dụ này chỉ kiểm tra **có lỗi compile**, thay vì ràng buộc vào một chuỗi lỗi cố định.

**Quy tắc thiết kế:** nếu `call()` không trả `true`, **không chuyển sang giai đoạn nạp/thực thi** cho output của lần build ấy. Nếu dùng chung thư mục output qua nhiều lần build, các file `.class` cũ có thể vẫn còn dù lần biên dịch mới thất bại; vì vậy production pipeline nên dùng output directory mới hoặc xác thực artifact gắn đúng với phiên bản source đã biên dịch.

## 6. Mỗi giai đoạn có một nhóm lỗi khác nhau

| Giai đoạn | Lỗi hoặc dấu hiệu | Nguyên nhân điển hình | Cách phản ứng |
| --- | --- | --- | --- |
| Lấy compiler | `getSystemJavaCompiler() == null` | Runtime image không có compiler implementation | Yêu cầu môi trường có `jdk.compiler` |
| Chuẩn bị compilation task | `IllegalArgumentException`, lỗi I/O | Option không được hỗ trợ hoặc file manager/path sai | Kiểm tra options, quyền truy cập, đường dẫn |
| Compile | `call() == false`, `Diagnostic.Kind.ERROR` | Source sai cú pháp, kiểu dữ liệu, thiếu compile dependency | Dừng và báo diagnostics |
| Load | `ClassNotFoundException` | Tên binary class sai hoặc loader không thấy file | Kiểm tra `-d`, package, output root và loader URLs |
| Link/resolve | `NoClassDefFoundError`, `LinkageError` hoặc subclass | Thiếu runtime dependency, bytecode hoặc liên kết không tương thích | Kiểm tra runtime classpath, các phiên bản thư viện |
| Init | `ExceptionInInitializerError` | Static initializer hoặc khởi tạo trường static thất bại | Xem nguyên nhân lỗi khi khởi tạo |
| Reflection setup | `NoSuchMethodException`, `IllegalAccessException` | Sai tên/chữ ký hoặc quyền truy cập | Kiểm tra public API và kiểu tham số |
| Invoke | `InvocationTargetException` | Phương thức được gọi ném exception | Xem `getCause()` và xử lý lỗi nghiệp vụ |

Một compilation có thể thành công nhưng **chưa đủ dependency ở runtime**, hoặc phương thức sẽ lỗi khi chạy. Vì thế test tốt phải có **assertion riêng** cho từng giai đoạn: compiler thành công, artifact tồn tại, loader nạp đúng class, API có thể gọi, giá trị trả về chính xác.

`java.lang.reflect.Method.invoke` bọc exception do chính phương thức được gọi ném vào `InvocationTargetException`. Điều này khác với lỗi compile của `JavaCompiler`; không dùng một catch tổng quát để che khuất nguyên nhân thuộc các giai đoạn khác nhau.

## 7. Khi biên dịch cần dependency riêng

Đoạn source sinh ra trong ví dụ chỉ dùng Java standard library. Ở dự án thật, source có thể tham chiếu `com.example.api.Plugin` nằm trong một JAR của ứng dụng. Khi ấy phải giải quyết **hai mặt**:

- **Compile classpath:** cung cấp API JAR qua option `--class-path` / `-classpath` hoặc cấu hình `StandardJavaFileManager` tại `StandardLocation.CLASS_PATH`; nếu không, compiler có thể báo không tìm thấy symbol/package.
- **Runtime lookup:** class loader dùng để nạp lớp sinh ra cũng phải có đường đến dependency phù hợp qua parent loader hoặc URL tương ứng. Một lớp compile được với một phiên bản API nhưng chạy cùng phiên bản không tương thích có thể lỗi khi link hay invoke.

Ví dụ mô tả cách đặt options khi đã biết rõ `dependencyJar` và `outputDir`:

~~~java
List<String> options = List.of(
        "-proc:none",
        "--class-path", dependencyJar.toString(),
        "-d", outputDir.toString());
~~~

**Đây là đoạn minh họa**, không phải chương trình độc lập. `dependencyJar` và `outputDir` là các biến `Path` đã xác thực. Đừng coi `--class-path` chỉ định cho compiler cũng tự động cấu hình classpath của `URLClassLoader`: chúng phục vụ hai bước khác nhau.

Nếu mã sinh ra là **named module** (JPMS), cần cân nhắc `--module-path`, module descriptor và class loader/module layer tương ứng. Không ép mô hình classpath của ví dụ trên vào named module phức tạp mà không thiết kế lại quá trình resolution.

## 8. Kiến trúc triển khai: giữ ranh giới giữa các thành phần

Trong hệ thống có biên dịch động, có thể chia trách nhiệm theo hợp đồng:

~~~text
SourceGenerator
    -> tạo và xác thực Java source
CompilerService
    -> compile, lưu diagnostics, artifact path, success
ArtifactStore
    -> quản lý phiên bản output .class/JAR
ClassLoadService
    -> tạo loader cho một artifact/version, nạp class theo binary name
ExecutionService
    -> kiểm tra interface/chữ ký, gọi phương thức, thu result/exception
LifecycleManager
    -> đóng loader, giải phóng tài nguyên, xóa artifact không còn dùng
~~~

Đây là sơ đồ kiến trúc gợi ý, không phải các lớp có sẵn trong JDK. Lợi ích nằm ở chỗ có thể kiểm tra riêng câu hỏi: **“Source có compile được?”**, **“Artifact nạp được?”** và **“Khi gọi thì hành vi đúng?”**

Một số quy tắc hữu ích khi hiện thực:

1. **Artifact gắn với phiên bản nguồn:** source hash, compiler options, dependency fingerprint và output path phải cùng một bản build; không vô tình load class cũ.
2. **Output mới cho lần compile mới:** khi có thay đổi source cùng binary name, tạo loader mới cho artifact mới. Một loader đã định nghĩa class không thông thường định nghĩa lại cùng tên trong chính nó.
3. **Quản lý tài nguyên:** đóng `StandardJavaFileManager` và `URLClassLoader`; không giữ tham chiếu class, object, thread context loader hoặc static cache qua phiên bản không cần thiết.
4. **Đánh dấu lỗi theo giai đoạn:** diagnostics của compiler khác với `ClassNotFoundException`, lỗi liên kết, lỗi init và lỗi nghiệp vụ khi invoke.
5. **Không chạy mã ngoài ý muốn:** chỉ bước execution đã được thiết kế mới gọi phương thức của lớp đích. Nếu có người dùng gửi source, phải coi cả compile (do annotation processors) và execution là thao tác có rủi ro, không dùng classloader như một ranh giới sandbox.
6. **Quy trình thực thi mã không tin cậy:** nếu thực sự cần chạy code từ nguồn không tin cậy, dùng môi trường tách biệt với quyền hạn, hạn mức tài nguyên và khả năng giám sát được thiết kế phù hợp. Một `URLClassLoader` chỉ giải quyết nạp lớp, không cung cấp isolation bảo mật.

### 8.1. Kịch bản cần gọi `main(String[] args)`

Nếu lớp sinh ra có phương thức `public static void main(String[] args)`, có thể gọi qua reflection sau khi nạp lớp:

~~~java
// Đoạn minh họa trong một phương thức đã có Class<?> generatedClass:
generatedClass.getMethod("main", String[].class)
        .invoke(null, (Object) new String[] {"one", "two"});
~~~

Cast `(Object)` là có chủ đích để mảng `String[]` trở thành **một tham số** của `Method.invoke(Object, Object...)`, không bị hiểu như danh sách đối số varargs. Ví dụ chính ở mục 3 gọi `greet` nên không cần có `main` trong source sinh ra.

Việc nạp lớp rồi gọi `main` bằng reflection trong **cùng JVM** khác với chạy `java -cp ... GeneratedMain` ở **tiến trình JVM mới**. Nếu cần tách lỗi, bộ nhớ hoặc vòng đời tiến trình, phải thiết kế cơ chế tạo tiến trình và quản lý output/exit code riêng.

### 8.2. Compile thành công có làm class được nạp tự động không?

**Không.** `CompilationTask.call()` hoạt động ở tầng compiler, ghi artifact theo cấu hình file manager. JVM không tự “đăng ký” output directory mới vào mọi class loader đang tồn tại. Ở ví dụ, thư mục `classes` chỉ được đưa vào đường tìm kiếm sau khi tạo `URLClassLoader` với URL của nó.

Ngay cả khi class đã load, cũng không đồng nghĩa một phương thức nghiệp vụ đã chạy. Có thể quan sát riêng giai đoạn khởi tạo nhờ `Class.forName(name, false, loader)` rồi kích hoạt bằng invocation có kiểm soát.

## 9. Sai lầm phổ biến

- **“`compile()` xong là chương trình đã chạy.”** Sai; compiler trả kết quả biên dịch. Muốn thực thi cần nạp và gọi phương thức hoặc chạy JVM với classpath/module path phù hợp.
- **“Có file `Hello.class` thì `Class.forName(...)` sẽ tự tìm thấy.”** Sai; file phải thuộc vùng tìm kiếm của class loader được dùng, đúng binary name và đúng package path.
- **“Đổi `-d` là đủ để runtime class loader biết output.”** Sai; `-d` chỉ xác định nơi compiler ghi file.
- **“`getTask(...)` đã thực hiện compile.”** Chưa; `call()` mới khởi động tác vụ, và chỉ dùng một lần.
- **“Không có compiler luôn là lỗi compile của source.”** Không; `getSystemJavaCompiler() == null` là vấn đề cấu hình runtime.
- **“Bắt lỗi compile cũng bắt được lỗi khi method chạy.”** Không; compiler diagnostics, linkage, init và invocation xảy ra ở những bước khác nhau.
- **“Tái sử dụng một loader sẽ nạp lại lớp cùng tên sau khi biên dịch lần nữa.”** Không nên giả định. Dùng artifact/version khác kèm loader mới khi cần nạp bản cập nhật.
- **“ClassLoader cô lập hoàn toàn mã bất kỳ.”** Sai; nó không phải sandbox. Tắt `-proc:none` cũng không tự động làm cho compilation an toàn với input không tin cậy.
- **“Dùng chuỗi message của javac làm hợp đồng test.”** Không ổn định. Kiểm tra `Boolean`, loại diagnostic, và file/behavior đầu ra.

## 10. Tự kiểm tra và bài luyện

**Câu 1.** `CompilationTask.call()` trả `true`, nhưng sau đó `Class.forName("x.Y", false, loader)` ném `ClassNotFoundException`. Kết luận gì?

**Đáp án:** Compile có thể đã thành công; bước **load** dùng tên lớp, output root hoặc class loader không đúng. Kiểm tra path của `x/Y.class` và URL của loader, chưa thể kết luận compiler sai.

**Câu 2.** Khi nào dòng `initialized` xuất hiện trong ví dụ mục 3?

**Đáp án:** Sau `before-invoke`, khi `Method.invoke` gọi phương thức static trên lớp chưa được khởi tạo. Nó không xuất hiện ở bước compiler trả `true` hoặc khi gọi `Class.forName(..., false, loader)`.

**Câu 3.** Có thể kiểm tra constructor/static initializer bị lỗi chỉ bằng `compiler.getTask(...).call()` không?

**Đáp án:** Không. Đây là lỗi xảy ra khi lớp được **khởi tạo hoặc thực thi**; cần test riêng đường load/init/invoke. Trường hợp lỗi khi chạy có thể liên quan `ExceptionInInitializerError` hoặc `InvocationTargetException` tùy vị trí phát sinh.

**Câu 4.** Source phụ thuộc một API JAR đã có trong compile classpath nhưng loader mới không tìm được JAR ấy. Rủi ro nào xuất hiện?

**Đáp án:** Lỗi load/link/runtime, chẳng hạn `NoClassDefFoundError`, mặc dù compile thành công. Compile dependency và runtime visibility phải cùng giải quyết.

**Câu 5.** Có thể dùng `getSystemJavaCompiler()` trong mọi Java runtime không?

**Đáp án:** Không. Có runtime image không mang module `jdk.compiler` và method trả `null`. Phải kiểm tra trước khi dùng và thiết kế yêu cầu môi trường triển khai phù hợp.

**Bài luyện:** Mở rộng `CompileLoadRunDemo` thành một phương thức `compile(Path source, Path output)` trả về kết quả chứa `success` và danh sách `Diagnostic`; sau đó viết test riêng cho từng điều kiện: cú pháp sai, load sai tên, gọi sai chữ ký và phương thức ném exception. Chỉ bước “execute” mới được invoke và mỗi phiên bản output phải được nạp bằng loader được chọn rõ ràng.

## 11. Tài liệu chính thức còn áp dụng

- [Java SE 26 — JavaCompiler](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/JavaCompiler.html): cách tạo `CompilationTask`, file manager, diagnostics.
- [Java SE 25 — JavaCompiler.CompilationTask](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/JavaCompiler.CompilationTask.html): `call()` thực hiện công việc biên dịch, trả kết quả và không được gọi lại.
- [Java SE 25 — ToolProvider](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/ToolProvider.html): lấy system Java compiler và khả năng trả `null`.
- [Java SE 25 — ClassLoader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): cách tải lớp, tên binary, parent delegation.
- [Java SE 25 — Class.forName](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)): kiểm soát việc khởi tạo ở bước nạp lớp.
- [Java SE 25 — jdk.compiler module](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/module-summary.html): vị trí triển khai compiler trong JDK hiện đại.

**Ghi nhớ:** `JavaCompiler` tạo ra code có thể nạp; `ClassLoader` quyết định code nào nhìn thấy được; JVM khởi tạo và thực thi chỉ khi chương trình đi vào đường gọi thích hợp. Dùng ranh giới này để kiểm thử và xử lý lỗi đúng giai đoạn.

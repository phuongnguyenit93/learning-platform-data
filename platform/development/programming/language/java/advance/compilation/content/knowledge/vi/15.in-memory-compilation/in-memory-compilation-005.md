# Cấu hình phụ thuộc và vị trí đầu ra cho file manager tùy biến

Trong Java Compiler API, việc đưa source code vào RAM chỉ giải quyết **đầu vào** của quá trình biên dịch. Để tạo một compiler tool có ích, ta còn phải cho trình biên dịch biết **nơi tìm dependency** và **nơi ghi source, class file, resource được sinh**. `JavaFileManager` là giao diện thực hiện hai nhiệm vụ ấy. `StandardJavaFileManager` quản lý tệp/JAR thông thường; `ForwardingJavaFileManager` giúp tùy biến một số điểm vào/ra mà vẫn dùng khả năng phân giải đường dẫn có sẵn.

Điểm dễ mắc lỗi nhất: cấu hình `CLASS_PATH` giúp `javac` **biết về một class khi biên dịch**, nhưng không tự làm class ấy xuất hiện trong **ClassLoader lúc chạy**. Tương tự, `JavaFileObject` chứa source trong bộ nhớ chưa đồng nghĩa bytecode output cũng ở trong bộ nhớ. Cần phân biệt rõ input, resolution, output và runtime.

Bài Knowledge này sử dụng Java 17+, cung cấp một dự án chạy được có **dependency trên đĩa, source ứng dụng trong RAM, bytecode ứng dụng trong RAM, và ClassLoader riêng để chạy thử**; sau đó mở rộng sang nhiều lượt biên dịch, annotation processing, module, tài nguyên và xử lý lỗi.

## 1. Bốn câu hỏi cần trả lời trước khi viết file manager

Mỗi lần biên dịch cần trả lời:

1. **Compilation units lấy từ đâu?** File `.java` trên đĩa, chuỗi `String`, database, editor buffer hay một hệ thống file ảo?
2. **Dependency được tìm ở đâu?** Platform APIs, classpath, module path, source path hoặc các class file đã biên dịch trong bộ nhớ từ lượt trước?
3. **Output ghi vào đâu?** Thư mục `.class` trên đĩa, byte arrays trong RAM, JAR, generated-source directory hoặc kho artifact khác?
4. **Ai nạp và sử dụng bytecode sau compile?** JVM chạy chương trình riêng qua `-cp`/`--module-path` hay custom ClassLoader trong một tiến trình có kiểm soát?

Sơ đồ:

~~~text
JavaFileObject (SOURCE)
  ├─ source file trên đĩa
  └─ source text trong RAM
                 │
                 ▼
         JavaCompiler.getTask(...)
                 │
         JavaFileManager
           ├─ CLASS_PATH / MODULE_PATH
           │     └─ đọc thư viện .class, .jar, module
           ├─ SOURCE_PATH
           │     └─ tìm source phụ thuộc nếu được cấu hình
           ├─ ANNOTATION_PROCESSOR_PATH
           │     └─ nạp processor cho compiler
           └─ output hooks
                 ├─ CLASS_OUTPUT → .class trên đĩa hoặc RAM
                 ├─ SOURCE_OUTPUT → generated .java
                 └─ tài nguyên từ annotation processor
                 │
                 ▼
            class files / bytes
                 │
                 ▼
         ClassLoader hoặc runtime JVM
                 ├─ bytecode ứng dụng
                 └─ dependencies cần thiết khi chạy
~~~

**Không nhất thiết mọi trường hợp đều có một output location duy nhất.** Một processor có thể sinh source và resource, compiler sinh nhiều class từ một compilation unit, một named module có thể có output theo module, và một ứng dụng có thể cần cả thư mục/URL dependency lẫn bytecode RAM.

## 2. Các API chính trong javax.tools

| API | Nhiệm vụ |
| --- | --- |
| `JavaCompiler` | Tạo task biên dịch và standard file manager |
| `JavaCompiler.CompilationTask` | Đại diện một lượt compile, gọi `call()` đúng một lần |
| `JavaFileObject` | Trừu tượng file nguồn hoặc class; gồm `Kind.SOURCE`/`Kind.CLASS` |
| `SimpleJavaFileObject` | Lớp cơ sở cho source/string/class output tự triển khai |
| `JavaFileManager` | Tìm input, nhận output, phân giải tên, quản lý locations |
| `StandardJavaFileManager` | File manager chuẩn cho `Path`, `File`, JAR và output directory |
| `ForwardingJavaFileManager<T>` | Bao manager khác và override các thao tác cần thiết |
| `StandardLocation` | Các tên location chuẩn như `CLASS_PATH`, `CLASS_OUTPUT` |
| `DiagnosticCollector` | Nhận lỗi, cảnh báo và thông tin vị trí theo cấu trúc |
| `ToolProvider` | Lấy compiler được runtime cung cấp |

API công khai thuộc module `java.compiler`. Trên JDK phổ biến, implementation `javac` thuộc module `jdk.compiler`. `ToolProvider.getSystemJavaCompiler()` **có thể trả `null`** nếu runtime image không chứa system compiler; kiểm tra điều này trước khi tạo file manager.

Ví dụ mở compiler:

~~~java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException("Requires a JDK with jdk.compiler");
}
~~~

Đây là **snippet** cần import `JavaCompiler` và `ToolProvider` từ `javax.tools`, không phải một tệp standalone. Một compiler task thành công trả về kết quả biên dịch; nó **không tự chạy method `main`**.

## 3. Phân biệt input và output locations

`StandardLocation` định nghĩa các location hay dùng:

| Location | Đọc hay ghi? | Mục đích |
| --- | --- | --- |
| `CLASS_PATH` | Đọc | Tìm .class và JAR classpath, kể cả dependency thư viện |
| `SOURCE_PATH` | Đọc | Tìm source phụ thuộc khi compiler được phép tra cứu |
| `MODULE_PATH` | Đọc | Tìm named/automatic module dependencies |
| `CLASS_OUTPUT` | Ghi | Nơi tạo .class cho source đang compile |
| `SOURCE_OUTPUT` | Ghi | Nơi tạo .java do annotation processors sinh |
| `ANNOTATION_PROCESSOR_PATH` | Đọc | Tìm processor và các dependencies để chạy processor |
| `ANNOTATION_PROCESSOR_MODULE_PATH` | Đọc | Tìm processor providers dưới dạng module |
| `PLATFORM_CLASS_PATH` | Đọc trong cấu hình phù hợp | Platform classes ở các mô hình/JDK tương ứng; không tự thiết lập bừa khi dùng release/module API hiện đại |

`CLASS_OUTPUT` và `SOURCE_OUTPUT` **không thay thế nhau**. Với annotation processing, một lượt compile có thể tạo `generated/demo/Helper.java` ở source output và `classes/demo/Helper.class` ở class output.

Hầu hết người dùng nên bắt đầu bằng `StandardJavaFileManager`. Chỉ viết manager tùy biến khi thật sự muốn thay đổi input/output, ví dụ lưu bytecode vào byte array để truyền cho runtime engine.

## 4. Cấu hình dependency bằng StandardJavaFileManager

`StandardJavaFileManager` cho phép gắn đường tìm với location:

~~~java
Path depClasses = Path.of("deps/classes").toAbsolutePath();
Path outputDir = Path.of("out").toAbsolutePath();

Files.createDirectories(outputDir);

standardManager.setLocationFromPaths(
        StandardLocation.CLASS_PATH,
        List.of(depClasses)
);

standardManager.setLocationFromPaths(
        StandardLocation.CLASS_OUTPUT,
        List.of(outputDir)
);
~~~

Đây là **snippet**, giả định đã import `Path`, `Files`, `List`, `StandardLocation` và tạo `standardManager`. Dòng `CLASS_PATH` hướng compiler đến thư mục chứa các package `.class`. Thư mục classpath có thể thay bằng một JAR thật, hoặc danh sách nhiều entry. Mỗi entry là một `Path` riêng.

**Với output location tiêu chuẩn trên đĩa, chỉ truyền đúng một directory** vào `setLocationFromPaths(CLASS_OUTPUT, ...)`, và tạo directory trước. Các input search locations có thể nhận nhiều path entries; output directory không phải nơi chọn luân phiên nhiều điểm ghi.

Ví dụ dependency nằm ở:

~~~text
deps/classes/
└── library/
    └── Greeter.class
~~~

Khi source viết `import library.Greeter;`, compiler tìm class qua `CLASS_PATH`. Nếu dependency không có trong location và cũng không tìm được ở con đường khác, việc nhập tên kiểu có thể báo `package library does not exist` hoặc `cannot find symbol`.

**Đường dẫn classpath cần trỏ tới root của package**, ở đây là `deps/classes`, không phải trực tiếp `deps/classes/library` hoặc `Greeter.class`.

### Khi có nhiều dependency

~~~java
standardManager.setLocationFromPaths(
        StandardLocation.CLASS_PATH,
        List.of(
                Path.of("deps/classes"),
                Path.of("libs/json.jar"),
                Path.of("libs/util.jar")
        )
);
~~~

Đây là snippet cho các đường dẫn đã tồn tại. API nhận collection `Path` nên bạn **không** tự ghép chuỗi bằng dấu `:` hoặc `;` vào một `Path` duy nhất. Nếu dùng option `--class-path` thì ngược lại phải dùng ký tự phân cách phụ thuộc OS. Chọn một phương án cấu hình rõ ràng, không đặt trùng nhiều nguồn chân lý.

## 5. Cấu hình bằng compiler options hay file manager?

Có hai hướng thường gặp.

**Hướng A — file manager locations:**

~~~java
standardManager.setLocationFromPaths(
        StandardLocation.CLASS_PATH, List.of(Path.of("deps/classes")));
standardManager.setLocationFromPaths(
        StandardLocation.CLASS_OUTPUT, List.of(Path.of("out")));

List<String> options = List.of("--release", "17", "-proc:none");
~~~

**Hướng B — compiler options:**

~~~java
List<String> options = List.of(
        "--release", "17",
        "-proc:none",
        "--class-path", "deps/classes",
        "-d", "out"
);
~~~

Cả hai là **snippet**; ở hướng B, `out` phải là output directory thích hợp và các đường dẫn cần tồn tại. Options được truyền vào tham số thứ tư của `JavaCompiler.getTask(...)`, còn source phải được cung cấp trong tham số `compilationUnits`. Không đặt tên tệp `.java` vào options như khi gọi dòng lệnh `javac` và tưởng compiler sẽ tự tìm source unit.

Không trộn `setLocationFromPaths(CLASS_OUTPUT, X)` với option `-d Y` khác nhau trong cùng task. Một implementation có thể thay đổi file manager location khi xử lý option, nên bạn sẽ khó biết nơi output thực sự ghi vào. Với custom manager chặn `CLASS_OUTPUT` để lưu trong RAM, cũng không nên đồng thời buộc một `-d` trên đĩa trừ khi đã chủ động thiết kế cách kết hợp.

### Không nhầm compile classpath với runtime classpath

Nếu compiler nhìn thấy `deps/classes` thì code sử dụng `library.Greeter` có thể compile thành công. Nhưng khi chạy bằng launcher:

~~~bash
java -cp out app.Main
~~~

runtime classpath ở lệnh này **không chứa `deps/classes`**. Nếu chương trình cần `Greeter` và class chưa ở nơi khác, có thể gặp `NoClassDefFoundError`. Cần cung cấp dependency khi chạy:

~~~bash
java -cp "out:deps/classes" app.Main
~~~

Dấu `:` dành cho shell Linux/macOS; Windows dùng `;`. Đây là ví dụ với class files trên đĩa; nếu `app.Main` chỉ nằm trong RAM, `java -cp` không tự tìm được nó.

## 6. Ví dụ hoàn chỉnh: dependency trên đĩa, source và class ứng dụng trong RAM

Ví dụ này có **hai nhánh rõ ràng**:

1. Biên dịch thư viện `library.Greeter` ra thư mục `deps/classes` bằng `javac` thông thường.
2. Chạy một Java program gọi `JavaCompiler`: nó đọc source app từ `String`, tìm dependency ở `deps/classes`, tạo bytecode `app.Main` trong RAM bằng `ForwardingJavaFileManager`, sau đó chạy phương thức qua một ClassLoader riêng biết cả bytecode RAM lẫn thư mục dependency.

Ví dụ dùng JDK 17+, không cần Maven/Gradle hoặc thư viện ngoài.

### 6.1. Cấu trúc thư mục

~~~text
memory-compiler-demo/
├── src/
│   └── library/
│       └── Greeter.java
├── MemoryCompileWithDependency.java
└── deps/
    └── classes/                # được tạo khi build dependency
~~~

Không cần tạo `app/Main.java` trên ổ đĩa vì nội dung source app sẽ là Java text block trong tool.

### 6.2. Thư viện dependency: src/library/Greeter.java

~~~java
package library;

public final class Greeter {
    private Greeter() {
    }

    public static String hello(String name) {
        return "Hello, " + name;
    }
}
~~~

Thư viện không import API phức tạp; ta có thể dễ nhận biết lỗi thiếu dependency và kết quả runtime chính xác.

Biên dịch bằng Bash từ root project:

~~~bash
mkdir -p deps/classes
javac --release 17 -d deps/classes src/library/Greeter.java
~~~

Sau đó có `deps/classes/library/Greeter.class`. Tệp này sẽ là dependency khi compiler biên dịch app source trong RAM.

### 6.3. Tool JavaCompiler: MemoryCompileWithDependency.java

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.URI;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeSet;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileManager;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public class MemoryCompileWithDependency {
    static final class StringSource extends SimpleJavaFileObject {
        private final String source;

        StringSource(String className, String source) {
            super(URI.create("string:///"
                    + className.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.source = source;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return source;
        }
    }

    static final class MemoryClassFile extends SimpleJavaFileObject {
        private final ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        MemoryClassFile(String className, Kind kind) {
            super(URI.create("memory:///"
                    + className.replace('.', '/')
                    + kind.extension), kind);
        }

        @Override
        public OutputStream openOutputStream() {
            return bytes;
        }

        byte[] getBytes() {
            return bytes.toByteArray();
        }
    }

    static final class MemoryFileManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {

        private final Map<String, MemoryClassFile> outputs = new HashMap<>();

        MemoryFileManager(StandardJavaFileManager delegate) {
            super(delegate);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location,
                String className,
                JavaFileObject.Kind kind,
                FileObject sibling) throws IOException {

            if (location == StandardLocation.CLASS_OUTPUT
                    && kind == JavaFileObject.Kind.CLASS) {
                MemoryClassFile output = new MemoryClassFile(className, kind);
                outputs.put(className, output);
                return output;
            }

            return super.getJavaFileForOutput(
                    location, className, kind, sibling);
        }

        Map<String, byte[]> snapshot() {
            Map<String, byte[]> result = new HashMap<>();
            outputs.forEach((name, file) ->
                    result.put(name, file.getBytes()));
            return result;
        }
    }

    static final class OutputClassLoader extends URLClassLoader {
        private final Map<String, byte[]> compiled;

        OutputClassLoader(URL dependencyUrl, Map<String, byte[]> compiled) {
            super(new URL[] {dependencyUrl},
                    ClassLoader.getPlatformClassLoader());
            this.compiled = compiled;
        }

        @Override
        protected Class<?> findClass(String name) throws ClassNotFoundException {
            byte[] bytes = compiled.get(name);
            if (bytes != null) {
                return defineClass(name, bytes, 0, bytes.length);
            }
            return super.findClass(name);
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler is required");
        }

        Path dependency = Path.of("deps/classes").toAbsolutePath();
        if (!Files.isDirectory(dependency)) {
            throw new IllegalStateException("Compile library dependency first");
        }

        String source = """
                package app;
                public class Main {
                    public static String run() {
                        return library.Greeter.hello("Ada");
                    }
                }
                """;

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        Map<String, byte[]> bytecode;
        try (StandardJavaFileManager standard =
                     compiler.getStandardFileManager(
                             diagnostics, Locale.ROOT, null)) {

            // Dependencies used at compile time:
            standard.setLocationFromPaths(
                    StandardLocation.CLASS_PATH, List.of(dependency));

            MemoryFileManager manager = new MemoryFileManager(standard);
            JavaFileObject input = new StringSource("app.Main", source);

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null,
                    manager,
                    diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null,
                    List.of(input));

            boolean success = task.call();
            System.out.println("compiled=" + success);

            if (!success) {
                for (Diagnostic<? extends JavaFileObject> d
                        : diagnostics.getDiagnostics()) {
                    System.err.println(
                            d.getKind() + ": " + d.getMessage(Locale.ROOT));
                }
                return;
            }

            bytecode = manager.snapshot();
            System.out.println("memoryClasses="
                    + new TreeSet<>(bytecode.keySet()));
        }

        // Dependency resolution at runtime is a separate concern.
        try (OutputClassLoader loader = new OutputClassLoader(
                dependency.toUri().toURL(), bytecode)) {

            Class<?> app = loader.loadClass("app.Main");
            Object value = app.getMethod("run").invoke(null);
            System.out.println("result=" + value);
        }
    }
}
~~~

Đây là **một class Java standalone**. Các inner classes triển khai đúng các điểm mở rộng cần thiết:

- `StringSource` là compilation unit `SOURCE` từ text block.
- `MemoryClassFile` chứa luồng ghi bytecode bằng `ByteArrayOutputStream`.
- `MemoryFileManager` chuyển tiếp mọi thao tác không tùy biến cho standard manager và **chỉ chặn `CLASS_OUTPUT` với kind `CLASS`**.
- `snapshot()` chuyển output thành map tên lớp → bytecode (`byte[]`).
- `OutputClassLoader` nạp class app từ bytes và có URL cho dependency `deps/classes`.
- Annotation processing bị tắt chủ động để ví dụ không phải giải quyết generated sources/resources.

### 6.4. Lệnh chạy và stdout

Đứng ở root `memory-compiler-demo`:

~~~bash
mkdir -p deps/classes
javac --release 17 -d deps/classes src/library/Greeter.java
javac --release 17 MemoryCompileWithDependency.java
java MemoryCompileWithDependency
~~~

Stdout từ lệnh cuối:

~~~text
compiled=true
memoryClasses=[app.Main]
result=Hello, Ada
~~~

Điều kiện để có đúng output: JDK có system compiler, `deps/classes/library/Greeter.class` hợp lệ, không có sự can thiệp ngoài ví dụ. Các lệnh `javac` thành công thường không in stdout. Các messages nếu xuất hiện từ compiler/diagnostics có thể nằm trên stderr tùy JDK và môi trường.

**Giải thích kết quả:**

1. Khi compile app, thư viện được tra bằng `StandardLocation.CLASS_PATH`.
2. `getJavaFileForOutput(CLASS_OUTPUT, "app.Main", CLASS, ...)` được manager tùy biến chặn và ghi bytes vào RAM.
3. `snapshot()` cho biết class app có sẵn, nhưng không có tệp `app/Main.class` nào bắt buộc phải sinh trên đĩa.
4. `OutputClassLoader` kết hợp class `app.Main` từ RAM và `library.Greeter` từ đường URL của dependency.
5. Method public static `run()` được gọi bằng reflection, trả về chuỗi chính xác `Hello, Ada`.

**Ranh giới bảo mật:** demo dùng custom ClassLoader để quan sát hành vi, không phải sandbox. Đừng nạp và chạy Java source không đáng tin trong cùng JVM chứa tài nguyên nhạy cảm. Annotation processor cũng là code thực thi ngay trong quá trình compile, vì vậy ví dụ tắt `-proc` khi không cần.

## 7. Vì sao phải đặt dependency ở cả compile và runtime?

Đây là hai thế giới khác nhau:

| Thời điểm | Ai cần dependency? | Cấu hình trong demo |
| --- | --- | --- |
| Compile | `javac` phải phân giải `library.Greeter` trong source app | `standard.setLocationFromPaths(CLASS_PATH, ...)` |
| Run | JVM/ClassLoader phải load `library.Greeter` khi code app được thực thi | `URLClassLoader` nhận URL `deps/classes` |
| Generated output | `javac` phải ghi `app.Main` sang JavaFileObject output | `MemoryFileManager.getJavaFileForOutput` |
| Load app | ClassLoader phải tìm class `app.Main` | `OutputClassLoader.findClass` từ map bytes |

Nếu bỏ `CLASS_PATH` trong compiler task, app không compile vì tên `library.Greeter` không thể phân giải. Nếu chỉ giữ compile path nhưng bỏ dependency URL ở loader, app có thể compile được nhưng lỗi khi liên kết/thực thi class (thường là `NoClassDefFoundError`).

**Không nên dùng context class loader hoặc app class loader của tool như một sự thay thế mơ hồ cho compile classpath**. Compiler tìm kiểu qua file manager và options; runtime loader tìm class qua class loading delegation. Hai cơ chế liên hệ nhưng độc lập.

Trong project dùng Maven/Gradle, build tool thường tổ chức compile classpath và runtime classpath khác nhau theo dependency scopes. Đó là lý do một dependency khai `compileOnly` có thể dùng để biên dịch nhưng bị thiếu lúc chạy nếu ứng dụng thật sự gọi class của nó.

## 8. Output class có thể sinh nhiều file từ một source

Trong demo chỉ có `app.Main`. Nhưng một compilation unit có nested class, local class, record hay synthetic helper có thể sinh **nhiều** file `.class`. File manager phải coi tên lớp nhị phân `className` ở mỗi lần `getJavaFileForOutput` là **khóa output riêng**, không giả định một source tương ứng đúng một byte array.

Ví dụ minh họa:

~~~java
package app;

public class Outer {
    static class Nested {
    }
}
~~~

Nếu compile source này, thường có ít nhất `app.Outer` và `app.Outer$Nested`. Tên file/bytecode thực tế do compiler quyết định theo cấu trúc code. Manager dùng `Map<String, MemoryClassFile>` có thể lưu nhiều kết quả, còn manager chỉ lưu một `ByteArrayOutputStream` chung sẽ làm mất dữ liệu hoặc trộn class files.

Nếu dùng multi-module project, **chỉ khóa bằng binary class name có thể chưa đủ** khi các module cần không gian tên/output tách biệt. Cân nhắc khóa theo module/location và binary name, sử dụng location dành cho từng module, và không trộn outputs của các compilation tasks không liên quan.

### Khi nào dùng byte[] thay vì ByteArrayOutputStream?

Trong khi compiler ghi, cần một stream nhận bytes. Sau khi compiler đóng stream và `task.call()` hoàn tất, nên snapshot sang `byte[]` bất biến theo ý nghĩa sử dụng và loại bỏ reference thừa khi có thể. Cẩn thận không expose map mutable cho các thread khác khi compilation còn đang chạy.

## 9. Muốn CLASS_OUTPUT trên đĩa thì không cần override

Nếu mục tiêu là **source trong RAM nhưng class file ra đĩa**, bạn chỉ cần `StringSource` và standard file manager:

~~~java
Path classDir = Path.of("build/classes");
Files.createDirectories(classDir);

standardManager.setLocationFromPaths(
        StandardLocation.CLASS_OUTPUT, List.of(classDir));

JavaCompiler.CompilationTask task = compiler.getTask(
        null, standardManager, diagnostics,
        List.of("--release", "17", "-proc:none"),
        null, List.of(new StringSource("app.Main", sourceText)));
boolean success = task.call();
~~~

Đây là **snippet**, dựa trên `StringSource` và các biến `compiler`, `diagnostics`, `sourceText` đã được khai báo như bài ví dụ. Với cấu hình này, `app/Main.class` được standard manager ghi ra directory tương ứng. Nó khác demo ở mục 6, nơi CLASS_OUTPUT được chặn sang RAM.

Nếu bạn đã tạo custom forwarding manager nhưng muốn **chỉ một số class** được ghi RAM và phần khác ra disk, cần có chính sách chọn output chính xác. Một compiler có thể tự phát sinh nhiều class file; ghi phân tán nửa RAM nửa disk tùy tên có thể gây khó khăn cho việc load và đóng gói. Thông thường tốt hơn chọn **một đích nhất quán cho một compilation task**.

## 10. Tạo source bằng annotation processor: SOURCE_OUTPUT và CLASS_OUTPUT

Khi annotation processor được bật, nó có thể gọi:

~~~java
JavaFileObject source =
        processingEnv.getFiler().createSourceFile("generated.Helper");
~~~

Đây là snippet **bên trong một processor** có `processingEnv`. Nó khác class output của compiler.

Với standard file manager, muốn generated source ra đĩa:

~~~java
Files.createDirectories(Path.of("build/generated"));
Files.createDirectories(Path.of("build/classes"));

standardManager.setLocationFromPaths(
        StandardLocation.SOURCE_OUTPUT,
        List.of(Path.of("build/generated")));

standardManager.setLocationFromPaths(
        StandardLocation.CLASS_OUTPUT,
        List.of(Path.of("build/classes")));
~~~

Ví dụ trên giả định annotation processor được cấu hình phù hợp và `standardManager` còn mở. `SOURCE_OUTPUT` cho generated `.java`; `CLASS_OUTPUT` cho `.class` của code ban đầu và code được sinh.

### Nếu muốn cả generated source cũng nằm trong RAM?

Cần quản lý **nhiều loại output**, không phải chỉ override `CLASS_OUTPUT`:

- `getJavaFileForOutput(..., Kind.SOURCE, ...)`: để processor tạo source Java.
- JavaFileObject SOURCE phải hỗ trợ ghi content, rồi hỗ trợ đọc lại để compiler parse/compile ở round tiếp theo (chẳng hạn `openWriter`/`getCharContent` phù hợp).
- `getJavaFileForOutput(..., Kind.CLASS, ...)`: giữ bytecode class trong RAM.
- `getFileForOutput(...)`: với tài nguyên do `Filer.createResource` tạo ở output location.
- Các thao tác tìm lại source/class nếu compiler yêu cầu, chẳng hạn `getJavaFileForInput` và `list`, có thể cần tùy biến tùy thiết kế.

**Không được khẳng định chỉ override `getJavaFileForOutput(..., CLASS, ...)` thì toàn bộ annotation processing đã in-memory.** Trong ví dụ mục 6, `-proc:none` cố ý tránh trường hợp processor sinh source và resource.

Một thiết kế thực tế có thể **cho generated sources/resources ra thư mục tạm** qua standard manager, nhưng giữ final class bytes trong RAM. Cách lai này đơn giản hơn xây filesystem ảo đầy đủ nếu yêu cầu bảo mật và lưu trữ cho phép.

## 11. Tài nguyên từ processor: getFileForOutput là nhánh riêng

Annotation processor không chỉ sinh source hoặc class; nó có thể tạo file metadata, ví dụ một service descriptor:

~~~java
FileObject resource = processingEnv.getFiler().createResource(
        StandardLocation.CLASS_OUTPUT,
        "",
        "META-INF/services/example.Service");
~~~

Đây là snippet minh họa, chỉ hợp lệ khi processor được khai báo, `example.Service` tồn tại theo mục đích thực tế và code xử lý file output tương ứng. Resource được ghi bằng `openWriter()` hoặc `openOutputStream()` theo API; lệnh `createResource` mới tạo file object chứ chưa tự ghi nội dung hoàn chỉnh.

Khi giữ output class trong RAM, **resource không tự xuất hiện trong map class bytes**. `getFileForOutput` là API khác `getJavaFileForOutput`. Nếu ứng dụng sau compile cần nạp resource qua `ClassLoader.getResourceAsStream` hoặc Java `ServiceLoader`, custom loader/bundle cũng phải cung cấp resource tương ứng.

Một cách kiểm tra đầy đủ pipeline:

1. Processor tạo source `generated.Helper` trong SOURCE_OUTPUT.
2. Compiler tạo `generated.Helper.class` trong CLASS_OUTPUT.
3. Processor tạo `META-INF/services/...` resource.
4. Khi chạy, loader có thể tìm cả class và resource theo vị trí đã triển khai.

Nếu chỉ bước 2 thành công, không đủ kết luận rằng service loading sẽ hoạt động.

## 12. Phụ thuộc đã biên dịch trong RAM ở lượt trước

Bài toán nâng cao: task A compile `lib.Api` vào bytes map; task B compile `app.Use` có `import lib.Api;` nhưng `lib.Api.class` **không nằm trên đĩa**. Lúc này, chỉ override output của task A và pass byte array làm ClassLoader cho task B **không đủ**. Compiler của task B cần nhìn thấy class file như **input dependency** trong file manager.

~~~text
Task A:
  lib.Api.java ──compile──► map["lib.Api"] = bytes

Task B:
  app.Use.java
       │
       ├─ cần giải tên lib.Api ở compile time
       │   └─ file manager phải expose lib.Api.class từ map
       ▼
    compiled app.Use.class
~~~

Những điểm mở rộng có thể liên quan:

| Method | Tác dụng |
| --- | --- |
| `getJavaFileForInput(location, className, CLASS)` | Trả object đại diện class file biết tên cụ thể |
| `list(location, packageName, kinds, recurse)` | Cho compiler liệt kê package, nhất là khi tìm kiểu/import |
| `inferBinaryName(location, file)` | Trả tên nhị phân đúng cho custom JavaFileObject |
| `hasLocation(location)` | Thông báo khả năng hỗ trợ location khi implementation yêu cầu |
| `getClassLoader(location)` | Cung cấp loader cho location khi cần (đặc biệt với processor hoặc tooling) |
| `getJavaFileForOutput(...)` | Chặn đầu ra class/source của lượt compile tiếp |

Không phải compiler luôn chỉ gọi `getJavaFileForInput`: khi phân tích wildcard imports hoặc tìm các kiểu trong package, nó có thể dùng `list`/`inferBinaryName`. Vì vậy, một manager vừa lưu output bytes vừa muốn dùng làm **classpath RAM của lần compile sau** phải triển khai đủ mô hình resolution, không chỉ một method “tra tên bằng map”.

### Mẫu JavaFileObject cho class bytes đầu vào

~~~java
static final class BytecodeInput extends SimpleJavaFileObject {
    private final byte[] bytes;

    BytecodeInput(String binaryName, byte[] bytes) {
        super(URI.create("memory:///"
                + binaryName.replace('.', '/')
                + Kind.CLASS.extension), Kind.CLASS);
        this.bytes = bytes.clone();
    }

    @Override
    public InputStream openInputStream() {
        return new ByteArrayInputStream(bytes);
    }
}
~~~

Đây là **snippet** cho một nested class trong file có import `URI`, `InputStream`, `ByteArrayInputStream` và `SimpleJavaFileObject`. Nó chỉ giải quyết cách đọc content của một class input; cần file manager trả nó từ `getJavaFileForInput` hoặc `list`, đồng thời giữ đúng binary name/location.

Nếu chưa cần chain compile hoàn toàn in-memory, cách đơn giản và bền vững hơn là **đưa source A và B vào cùng compilation task** hoặc ghi dependency A ra một temporary directory/JAR rồi dùng standard manager cho task B. Dùng một task khi các nguồn là một tập thống nhất thường giúp compiler xử lý mối quan hệ kiểu mà không đòi file manager ảo phức tạp.

## 13. list và inferBinaryName: hai phương thức rất dễ bỏ sót

Một file manager dùng cho dependencies ảo không thể giả định compiler biết hết tên class từ source. Ví dụ:

~~~java
import lib.*;
public class Use {
    lib.Api value;
}
~~~

Khi tìm package `lib`, compiler có thể cần **liệt kê** các file object khả dụng và **suy ra tên nhị phân** từng file. Nếu manager chỉ override `getJavaFileForInput` cho một tên cụ thể, wildcard import hoặc việc tìm nested/sibling types có thể lỗi khó đoán.

Khi override `list`, cần hợp nhất hợp lý những file object từ underlying standard manager với objects trong memory, tránh duplicate ambiguous types. Khi override `inferBinaryName`, nếu object do manager tạo, trả **binary name thực tế**, còn file object của manager gốc phải được delegate cho manager gốc.

Chú ý binary name như `lib.Outer$Nested` **khác** tên source `lib.Outer.Nested` trong một số ngữ cảnh. Đừng tự tạo tên từ URI bằng cách nối chuỗi sơ sài rồi giả định mọi class đều top-level. Module-oriented locations làm bài toán phức tạp thêm vì còn module identity và readability.

## 14. ClassLoader sau compile không tự dùng JavaFileManager

Một lỗi hiểu nhầm: vì compiler và ClassLoader đều “tìm class”, nhiều người muốn truyền `JavaFileManager` trực tiếp vào JVM để chạy mã. Nhưng chúng thuộc hai API khác nhau:

- `JavaFileManager` phục vụ compiler: tìm source/class dependencies, tạo output file objects.
- `ClassLoader` phục vụ runtime: định nghĩa/nạp classes và có thể tìm resources.
- ModuleLayer và JPMS còn có giải pháp riêng cho named modules ở runtime.
- `java -cp` của launcher không đọc map bytecode trong RAM của tiến trình tool khác.

Ở ví dụ mục 6, `OutputClassLoader` nhận **snapshot** class bytes và URL dependency. Khi compile một class bằng manager RAM, chưa có bước tự động đưa class vào parent class loader. Chỉ khi gọi `loadClass`/reflection thì chương trình mới dùng output.

**Không dùng ClassLoader custom như ranh giới bảo mật.** Nếu biên dịch source không tin cậy hoặc thực thi kết quả, hãy chạy trong môi trường isolated có resource limits. `-proc:none` giảm một nhánh chạy mã ngoài ý muốn, nhưng không thay chính sách sandbox và input validation.

## 15. Named modules khác ứng dụng classpath

Ví dụ chính dùng classpath/unnamed module để rõ ràng. Với JPMS, `--module-path` và module descriptor còn chi phối resolution/readability/exports:

~~~java
standardManager.setLocationFromPaths(
        StandardLocation.MODULE_PATH,
        List.of(Path.of("mods/libraries")));
~~~

Đây là snippet cho module artifacts thật. Khi source là named module, compiler có thể dùng module-specific locations, các API như `getLocationForModule`/`listLocationsForModules` và `setLocationForModule` tùy nhu cầu.

Cấu hình `MODULE_PATH` **không giống** `CLASS_PATH`. Một JAR automatic module và cùng JAR trên classpath có mô hình truy cập khác nhau. Custom manager override `getJavaFileForOutput` cho classpath `CLASS_OUTPUT` không có nghĩa đã hỗ trợ mọi output path của multi-module compilation. Với module output, phải xử lý đúng `Location` mà compiler cung cấp, không tự ép tất cả về một module giả.

Một nguyên tắc thiết kế: **nếu chưa cần tùy biến module resolution, hãy để StandardJavaFileManager quản lý module path** và chỉ override class output (đúng nhu cầu) cho một compilation task. Triển khai lại JPMS resolution trong custom manager là công việc lớn, không nên làm chỉ để nhận vài `byte[]`.

## 16. Annotation processor path phải cấu hình riêng

Một processor **chạy lúc biên dịch**, không phải dependency runtime mặc định của app:

~~~java
standardManager.setLocationFromPaths(
        StandardLocation.ANNOTATION_PROCESSOR_PATH,
        List.of(Path.of("libs/my-processor.jar")));
~~~

Đây là snippet khi processor artifact có thật. Bên cạnh đó, source cần annotation API trên compile classpath hoặc module path thích hợp. Với modular processor, dùng `ANNOTATION_PROCESSOR_MODULE_PATH` hoặc compiler option `--processor-module-path` tùy cấu hình.

Thêm processor JAR vào `CLASS_PATH` không nhất thiết kích hoạt processor. Đặc biệt từ JDK 23, `javac` không còn tự chạy processor chỉ vì phát hiện provider trên classpath theo mặc định; cấu hình processing rõ ràng bằng `-processor`, processor path/module path hoặc chế độ tương ứng.

Với compiler service xử lý source người dùng, **tắt processor** nếu không cần:

~~~java
List<String> options = List.of("--release", "17", "-proc:none");
~~~

Nếu ứng dụng cần annotation code generation, hãy quản lý processor version và output location cho generated sources/resources. Processor có thể chạy mã đọc/ghi file khi compiler task đang chạy, nên phải được xem như thành phần đáng tin của build toolchain.

## 17. Thứ tự thiết kế một custom manager tốt

Trước khi override nhiều method, định nghĩa **bảng chính sách**:

| Loại dữ liệu | Location/Kind | Nguồn hoặc đích | Giải pháp |
| --- | --- | --- | --- |
| Source chính | `SOURCE` compilation units | Text editor RAM | `StringSource` |
| Java platform API | System modules | JDK image | Delegate standard manager |
| Third-party classes | `CLASS_PATH` | Directory/JAR | Standard manager location |
| Named module classes | `MODULE_PATH` | Modular JARs | Standard manager + descriptors |
| App bytecode | `CLASS_OUTPUT` + `CLASS` | RAM map | Override `getJavaFileForOutput` |
| Generated Java source | `SOURCE_OUTPUT` + `SOURCE` | Disk temp hoặc memory | Delegate / override có chủ đích |
| Generated resource | `CLASS_OUTPUT` + resource | Disk temp hoặc RAM | `getFileForOutput`, loader/resource policy |
| Processor implementation | Processor path | JAR đáng tin | Standard manager; explicit processor selection |
| Output loaded at runtime | ClassLoader | Bytecode RAM + library URLs | Custom loader hoặc packaging |

**Giữ các thành phần ít tùy biến nhất có thể.** Nếu hệ thống chỉ cần inspect class bytes của một task, mẫu forwarding manager trong demo là đủ. Nếu cần incremental compilation, source/codegen/resource hoàn toàn in-memory, module graph động và classloader nhiều tầng, cần thiết kế và test từng hợp đồng API thay vì thêm vài override tùy hứng.

## 18. Khi nào output phải được tách theo request?

Trong compiler server, hai người dùng có thể cùng gửi `package demo; public class Main { ... }`. Nếu dùng một map toàn cục khóa `demo.Main`, compile sau có thể ghi đè bytes của request trước; loader có thể nạp nhầm code và dẫn tới rò rỉ dữ liệu.

Để tránh:

1. Mỗi compilation request có **manager, diagnostics và output map riêng**.
2. Tạo `CompilationTask` riêng, gọi `call()` một lần.
3. Chỉ lấy snapshot output sau khi task hoàn tất, tránh đọc object đang ghi.
4. Tạo ClassLoader mới nếu cần chạy kết quả, và đóng nó khi có thể.
5. Không giữ toàn bộ source/bytecode trong cache vô hạn; xác định TTL, quotas và eviction.
6. Dùng key gồm request/build identity, module và binary name nếu làm kho lưu trữ chung.
7. Đặt timeout và memory/disk limits bằng isolation ở cấp tiến trình/container đối với input không tin cậy.

`JavaCompiler` và file manager không cung cấp sẵn một sandbox hay hệ thống incremental build hoàn chỉnh. Không chia sẻ cùng task hoặc cùng mutable manager giữa nhiều thread nếu chưa chứng minh thread-safety.

## 19. Chẩn đoán lỗi theo đúng tầng

| Triệu chứng | Nguyên nhân thường gặp | Cần kiểm tra |
| --- | --- | --- |
| `package library does not exist` | Compile classpath thiếu dependency | `CLASS_PATH`, JAR root, đúng `Path`, đúng package |
| `cannot find symbol` dù .class nằm trong map cũ | Task mới không tìm input class trong memory | `getJavaFileForInput`, `list`, `inferBinaryName` hoặc đưa vào cùng task |
| `compiled=true` nhưng không có file .class trên disk | CLASS_OUTPUT bị chặn sang RAM như thiết kế | `snapshot()`, output policy |
| Source in-memory nhưng file .class xuất hiện trên disk | Chỉ tùy biến source, chưa chặn output | `getJavaFileForOutput`/`CLASS_OUTPUT` |
| `ClassNotFoundException: app.Main` | Loader không có bytecode app | Map keys, loader delegation, class name |
| `NoClassDefFoundError: library/Greeter` | Runtime loader không có dependency | URL/classpath/module graph lúc chạy |
| `UnsupportedClassVersionError` | Class từ dependency/output yêu cầu Java cao hơn runtime | Class-file major, `--release`, JDK thực tế |
| Generated `.java` không có | Source output chưa cấu hình hoặc processor không chạy | `SOURCE_OUTPUT`, processor path, rounds |
| `FilerException` | Processor tạo trùng file theo nhiều rounds | Unique output names, output manager |
| ServiceLoader không tìm provider | Resource `META-INF/services` thiếu ở runtime | `getFileForOutput`, resources/URLClassLoader |
| File manager đóng quá sớm | Standard manager hoặc streams đã close | `try-with-resources`, task lifecycle |
| JavaFileObject bị compiler bỏ qua | URI/kind/binaryName không hợp lệ | URI, extension, `SOURCE`/`CLASS`, infer name |
| Output location báo lỗi | Directory không tồn tại hoặc nhiều output paths | Tạo directory trước, đúng cardinality |
| API dùng compiler trả `null` | Runtime image thiếu `jdk.compiler` | `ToolProvider`, Java runtime image |

**Đừng đọc nhầm `compile=true` thành `runtime=true`.** Phải có bước riêng để load, link, invoke và kiểm tra output thực tế nếu ứng dụng cần thực thi class sinh ra.

## 20. Kiểm thử manager tùy biến như một component

Bộ test hữu ích không chỉ có happy path:

- **Source hợp lệ, dependency hợp lệ:** compile thành công, output map có đúng binary names, bytes khác rỗng.
- **Thiếu dependency compile:** task thất bại và `DiagnosticCollector` chứa lỗi loại `ERROR`.
- **Dependency chỉ thiếu runtime:** task compile thành công, nhưng runtime loader phù hợp phải báo lỗi khi class được nạp/thực thi.
- **Một source sinh nhiều class:** map chứa top-level và nested class; mỗi byte array có class-file header phù hợp.
- **Source syntax/type error:** task thất bại, không công bố output map như artifact hợp lệ.
- **Hai tasks sequential:** manager hoặc output được reset/cô lập có chủ đích; không dùng lại `CompilationTask`.
- **Processor sinh source/resource:** nếu được hỗ trợ, kiểm tra cả `SOURCE_OUTPUT`, `CLASS_OUTPUT` và resources.
- **Unicode/encoding:** source string với Unicode, file source dùng UTF-8 khi đọc từ đĩa.
- **Module dependencies:** đối chiếu với `module-info.java` và module locations nếu JPMS nằm trong phạm vi.
- **Concurrency:** requests khác nhau không trộn output và diagnostics; không mặc định shared manager là thread-safe.

Khi kiểm tra class bytes, có thể đọc bốn byte đầu để nhận diện magic `CAFEBABE`, nhưng **magic đúng chưa chứng minh class loadable hay đúng bytecode target**. Có thể dùng ASM, `javap` (nếu xuất ra file), hoặc class loader/test thực tế theo nhu cầu. Class-file version và dependency graph cần được kiểm tra riêng.

## 21. Checklist triển khai Java 17+

1. Xác định rõ **compile units, dependencies, outputs, runtime loader** trước khi code.
2. Kiểm tra `ToolProvider.getSystemJavaCompiler()` không null.
3. Ưu tiên `StandardJavaFileManager` cho file/JAR/module trên đĩa.
4. Đặt `CLASS_PATH`/`MODULE_PATH` cho dependency; phân biệt với classpath của JVM chạy tool.
5. Đặt `CLASS_OUTPUT`/`SOURCE_OUTPUT` tương ứng output policy và tạo thư mục nếu ghi ra đĩa.
6. Khi cần output bytecode RAM, override `getJavaFileForOutput` cho đúng `Location`/`Kind`; delegate các trường hợp khác.
7. Khi cần class RAM của task trước làm dependency task sau, hỗ trợ **input/list/inferBinaryName**, không chỉ class output.
8. Khi có annotation processing, hỗ trợ generated source và resources hoặc chủ động disable `-proc:none`.
9. Tách **compiler manager** khỏi **runtime ClassLoader**; cung cấp runtime dependencies độc lập.
10. Dùng diagnostics và kết quả `call()`, không suy đoán compile thành công từ số file tạo ra.
11. Đóng standard manager, streams và URLClassLoader khi phù hợp; không share task giữa threads.
12. Cô lập compiler server, giới hạn dependency và runtime execution của source không tin cậy.
13. Kiểm thử trên đúng JDK, đúng `--release`, đúng classpath/module path và các môi trường runtime đích.

## 22. Tự kiểm tra

**Câu 1.** Source được cung cấp qua `SimpleJavaFileObject.getCharContent`. Bytecode có tự nằm trong RAM không?  
**Trả lời:** Không. Đầu ra do `JavaFileManager` và output location quyết định; standard manager có thể ghi ra disk.

**Câu 2.** `StandardLocation.CLASS_PATH` và `StandardLocation.CLASS_OUTPUT` có thay thế nhau không?  
**Trả lời:** Không. Một nơi tìm class dependencies đầu vào, một nơi tạo class output.

**Câu 3.** Dependency `library.Greeter` đã có trên compiler classpath, tại sao khi chạy class app vẫn gặp `NoClassDefFoundError`?  
**Trả lời:** JVM/ClassLoader runtime chưa có đường tìm dependency tương ứng. Compile classpath không tự được ghi vào ClassLoader.

**Câu 4.** Muốn giữ bytecode RAM, method tối thiểu nào thường override trong một forwarding manager?  
**Trả lời:** `getJavaFileForOutput(...)` với `StandardLocation.CLASS_OUTPUT` và `JavaFileObject.Kind.CLASS`, trả JavaFileObject có output stream.

**Câu 5.** Vì sao `getJavaFileForInput` một mình có thể chưa đủ khi dùng class bytes trong RAM làm dependency cho task khác?  
**Trả lời:** Compiler còn có thể cần `list` và `inferBinaryName` khi tìm các kiểu trong package, wildcard imports hoặc resolution.

**Câu 6.** Khi processor sinh `Generated.java`, chỉ lưu class bytes RAM đã hỗ trợ full in-memory processing chưa?  
**Trả lời:** Chưa. Cần nguồn sinh có thể ghi/đọc, xử lý output resource và những thao tác tương ứng cho rounds.

**Câu 7.** `CLASS_OUTPUT` trên đĩa có thể nhận một list gồm ba folder và tự phân phối class files không?  
**Trả lời:** Không trong standard manager; output location chuẩn yêu cầu chính xác một đường dẫn directory theo contract.

**Câu 8.** Nếu tool chạy Java 21 nhưng truyền `--release 17`, ClassLoader runtime có tự sử dụng Java 17 không?  
**Trả lời:** Không. Compiler sinh class files target Java 17, nhưng tool đang chạy trên Java 21. Nếu cần xác nhận Java 17 runtime compatibility phải chạy artifact trên Java 17 thật.

**Câu 9.** Custom ClassLoader có phải sandbox cho code người dùng không?  
**Trả lời:** Không. Nó điều khiển cơ chế nạp class, không thay thế isolation và resource limits.

## 23. Ghi nhớ và tài liệu chuẩn

**`JavaFileManager` chính là ranh giới giữa compiler với nguồn dữ liệu và artifact đầu ra.** Khi custom manager, chỉ override những hành vi cần thay đổi và giữ lại chuẩn resolution của `StandardJavaFileManager`. `CLASS_PATH`/`MODULE_PATH` trả lời **“javac tìm dependency ở đâu?”**; `CLASS_OUTPUT`/`SOURCE_OUTPUT` trả lời **“compiler và processor ghi kết quả ở đâu?”**; `ClassLoader` trả lời **“JVM thực thi và tìm class sau khi biên dịch thế nào?”**. Đây là ba câu hỏi độc lập phải cấu hình nhất quán.

Tài liệu tra cứu chính thức:

- [JavaFileManager — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaFileManager.html).
- [StandardJavaFileManager — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html).
- [ForwardingJavaFileManager — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ForwardingJavaFileManager.html).
- [JavaCompiler — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html).
- [SimpleJavaFileObject — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html).
- [StandardLocation — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/StandardLocation.html).

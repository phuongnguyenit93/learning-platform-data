# 16.4 Cấu hình `CompilationTask`, class path, module path, `--release` và annotation processing

## 1. Biên dịch Java lúc chạy không chỉ là gọi `javac`

Trong Java 17, package `javax.tools` (module `java.compiler`) cho phép một chương trình Java gọi Java compiler theo API. Kịch bản thường gặp là code editor, template engine, build tool, plugin runtime, bài kiểm tra trực tuyến hoặc dịch vụ chuyển Java source thành `.class` ngay khi ứng dụng đang chạy.

Trục chính của API là:

~~~java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
JavaCompiler.CompilationTask task =
    compiler.getTask(out, fileManager, diagnostics,
                     options, classes, compilationUnits);
Boolean success = task.call();
~~~

Đây là **snippet minh họa**, chưa phải chương trình độc lập; các biến đầu vào cần được tạo. `CompilationTask` là **một lần biên dịch được cấu hình**: đầu vào, class path, module path, mục tiêu nền tảng `--release`, cơ chế annotation processing và nơi ghi output đều phải được quyết định **trước khi gọi `call()`**. `call()` thực thi công việc, trả `true` khi thành công, `false` nếu quá trình compile thất bại. Một số cấu hình sai có thể ném exception ngay khi tạo task hoặc trong lúc chạy thay vì trả false.

Bài này phân biệt chính xác các trách nhiệm:

- **`JavaCompiler`**: tạo compilation task.
- **`StandardJavaFileManager`**: quản lý nguồn/bytecode, đọc class/JAR/module, ánh xạ đường dẫn.
- **`DiagnosticCollector`**: nhận thông báo ERROR/WARNING/NOTE với nguồn, vị trí, mã lỗi.
- **`options` của task**: các tùy chọn tương ứng `javac` như `-classpath`, `--module-path`, `--release`, `-d`, `-processorpath`, `-processor`, `-proc:none`.
- **`compilationUnits`**: tập `JavaFileObject` cần dịch.
- **`classes`**: tên những class sẽ được **annotation processing** xử lý, không phải cách đặt class path hoặc chỉ định output.
- **Class loader ở runtime**: bước riêng sau biên dịch; `CompilationTask` tạo `.class` nhưng không tự nạp chúng vào class loader của ứng dụng.

Toàn bộ chương trình minh họa dùng Java 17+, không phụ thuộc IDE. Ví dụ đã được kiểm tra với `javac --release 17` và một JDK mới hơn chạy Java compiler API ở chế độ target 17.

## 2. Các tham số của `getTask` không hoán đổi được

Chữ ký chuẩn:

~~~java
JavaCompiler.CompilationTask getTask(
    Writer out,
    JavaFileManager fileManager,
    DiagnosticListener<? super JavaFileObject> diagnosticListener,
    Iterable<String> options,
    Iterable<String> classes,
    Iterable<? extends JavaFileObject> compilationUnits
)
~~~

Đây là **khai báo API để giải thích**, không phải function bạn cần triển khai.

| Tham số | Dùng vào việc gì? | Ví dụ |
| --- | --- | --- |
| `out` | Nơi ghi **thông tin bổ sung** không đi qua `DiagnosticListener`; `null` dùng output mặc định | `new StringWriter()` |
| `fileManager` | Nguồn và output file, JAR/class path, module locations, processor discovery | `compiler.getStandardFileManager(...)` |
| `diagnosticListener` | Thu thập chẩn đoán khi biên dịch | `DiagnosticCollector<JavaFileObject>` |
| `options` | Các tùy chọn hợp lệ của compiler, đưa **thành từng chuỗi tách rời** | `List.of("--release","17","-d","out")` |
| `classes` | Tên các class để annotation processing xử lý; thường `null` khi biên dịch từ source | `null` |
| `compilationUnits` | Các `JavaFileObject` kiểu SOURCE cần compile; có thể `null` khi dùng `-m` chọn module nguồn | `manager.getJavaFileObjectsFromPaths(List.of(source))` |

### Vòng đời khuyến nghị

~~~text
ToolProvider.getSystemJavaCompiler()
          |
          v
Compiler tồn tại? (yêu cầu jdk.compiler trong runtime)
          |
          v
Tạo DiagnosticCollector + StandardJavaFileManager
          |
          v
Cấu hình đường dẫn nguồn, output, dependencies, processors
          |
          v
Xây List<String> options và JavaFileObject inputs
          |
          v
JavaCompiler.getTask(...)
          |
          v
CompilationTask.call() -> Boolean success
          |
      +---+---+
      |       |
     true    false
      |       |
      v       v
  .class   Đọc DiagnosticCollector
      |
      v
Load/chạy class (nếu ứng dụng cần)
~~~

**Không dùng lại cùng một `CompilationTask` để gọi `call()` nhiều lần.** Mỗi lượt compile mới nên tạo task mới. Có thể dùng lại `JavaCompiler` hoặc một `StandardJavaFileManager` tuần tự để tận dụng caching JAR/file-system theo hợp đồng của API, nhưng phải quản lý lifecycle và trạng thái đường dẫn nhất quán.

**Không mặc định JDK luôn có compiler**: `ToolProvider.getSystemJavaCompiler()` có thể trả `null` nếu runtime image không chứa module `jdk.compiler` (chẳng hạn một custom `jlink` image). Java 17 `java.compiler` cung cấp API nhưng compiler implementation thực tế nằm ở `jdk.compiler`. Đối với một ứng dụng cần compile động, kiểm tra compiler ngay khi khởi động và triển khai bằng JDK/runtime image có compiler.

## 3. Hai đường để cấu hình file locations

Bạn có thể đặt locations theo **compiler options** hoặc qua **`StandardJavaFileManager`**. Không nên cấu hình hai nơi mâu thuẫn rồi kỳ vọng compiler tự đoán ý định.

| Mục đích | Tùy chọn `javac` khi dùng `getTask` | `StandardLocation` khi dùng file manager |
| --- | --- | --- |
| Nơi tìm dependency không modular | `-classpath` / `--class-path` | `CLASS_PATH` |
| Nơi tìm named modules đã biên dịch | `--module-path` | `MODULE_PATH` |
| Output `.class` | `-d` | `CLASS_OUTPUT` |
| Nơi ghi Java source do processor tạo | `-s` | `SOURCE_OUTPUT` |
| Đường dẫn processor trên class path | `-processorpath` / `--processor-path` | `ANNOTATION_PROCESSOR_PATH` |
| Đường dẫn processor là named modules | `--processor-module-path` | `ANNOTATION_PROCESSOR_MODULE_PATH` |
| Nguồn Java bình thường | `--source-path`, hoặc `compilationUnits` | `SOURCE_PATH` |
| Nguồn nhiều named modules | `--module-source-path` | `MODULE_SOURCE_PATH` |

Một cấu hình qua file manager (đây là **snippet**, không độc lập):

~~~java
try (StandardJavaFileManager manager =
        compiler.getStandardFileManager(diagnostics, null,
                                        java.nio.charset.StandardCharsets.UTF_8)) {
    manager.setLocationFromPaths(
        StandardLocation.CLASS_PATH,
        java.util.List.of(java.nio.file.Path.of("libs/dependency.jar")));
    manager.setLocationFromPaths(
        StandardLocation.CLASS_OUTPUT,
        java.util.List.of(java.nio.file.Path.of("build/classes")));

    // Tạo task bằng chính manager đã được cấu hình.
}
~~~

Nếu chọn cách này, tạo sẵn directories cần thiết và xác định rõ path tương ứng với file/JAR hay output directory. `setLocationFromPaths` được hỗ trợ bởi `StandardJavaFileManager` trên `Path` của file system phù hợp; nó không phải cách truyền một tham số `Path` đơn lẻ vào `getTask`.

Đối với chương trình nhỏ, dùng `List<String> options` dễ đối chiếu với command-line `javac` hơn. Với build tool nhiều lượt compile, file manager và `StandardLocation` cho phép quản trị locations một cách cấu trúc hơn.

## 4. Class path: cách compile một dự án không dùng JPMS

**Class path** chứa directories/JARs có các class trong **unnamed module**. Nếu Java source `app.App` import `lib.Helper` đã biên dịch, task cần biết `Helper.class` nằm ở đâu. `-classpath` thuộc bước **compiler resolution**, khác với class loader khi chạy ứng dụng.

Ví dụ sau tự tạo hai source file, compile library, cố tình compile app **không có class path** để thu diagnostic, rồi thêm class path và chạy class kết quả bằng một class loader riêng. Nó cũng kiểm tra `--release 17` tạo bytecode class-file major version **61**.

### Ví dụ 1 — `CompilationTaskDemo.java`

Lưu toàn bộ mã dưới đây:

~~~java
import javax.tools.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.io.*;
import java.net.*;
import java.util.*;

public class CompilationTaskDemo {
    static Path write(Path base, String relative, String source)
            throws IOException {
        Path file = base.resolve(relative);
        Files.createDirectories(file.getParent());
        Files.writeString(file, source, StandardCharsets.UTF_8);
        return file;
    }

    static boolean compile(
            JavaCompiler compiler,
            Path file,
            List<String> options,
            DiagnosticCollector<JavaFileObject> reports)
            throws IOException {
        try (StandardJavaFileManager manager =
                compiler.getStandardFileManager(
                        reports, null, StandardCharsets.UTF_8)) {
            Iterable<? extends JavaFileObject> inputs =
                    manager.getJavaFileObjectsFromPaths(List.of(file));

            JavaCompiler.CompilationTask task = compiler.getTask(
                    new StringWriter(), manager, reports,
                    options, null, inputs);
            return Boolean.TRUE.equals(task.call());
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null)
            throw new IllegalStateException("Requires JDK");

        Path root = Path.of(args[0]);
        Path library = write(root, "src/lib/Helper.java",
                "package lib; public class Helper { " +
                "public static String hi(String n){return \"Hi-\"+n;} }");
        Path app = write(root, "src/app/App.java",
                "package app; import lib.Helper; " +
                "public class App { public static String run(){ " +
                "return Helper.hi(\"Ada\"); } }");
        Path wrong = write(root, "src/app/Broken.java",
                "package app; public class Broken { int n = \"wrong\"; }");

        Path libOut = root.resolve("libOut");
        Path appOut = root.resolve("appOut");

        var d1 = new DiagnosticCollector<JavaFileObject>();
        boolean libOk = compile(compiler, library,
                List.of("--release", "17", "-proc:none",
                        "-encoding", "UTF-8",
                        "-d", libOut.toString()), d1);
        System.out.println("libCompiled=" + libOk);

        var missing = new DiagnosticCollector<JavaFileObject>();
        boolean withoutCp = compile(compiler, app,
                List.of("--release", "17", "-proc:none",
                        "-d", appOut.toString()), missing);
        System.out.println("withoutClassPath=" + withoutCp);
        System.out.println("missingErrors=" +
                missing.getDiagnostics().stream()
                        .filter(x -> x.getKind() ==
                                Diagnostic.Kind.ERROR).count());

        var d2 = new DiagnosticCollector<JavaFileObject>();
        boolean appOk = compile(compiler, app,
                List.of("--release", "17", "-proc:none",
                        "-classpath", libOut.toString(),
                        "-d", appOut.toString()), d2);
        System.out.println("withClassPath=" + appOk);

        byte[] compiled = Files.readAllBytes(
                appOut.resolve("app/App.class"));
        int major = ((compiled[6] & 0xff) << 8) |
                    (compiled[7] & 0xff);
        System.out.println("classMajor=" + major);

        try (URLClassLoader loader = new URLClassLoader(
                new URL[]{appOut.toUri().toURL(),
                          libOut.toUri().toURL()}, null)) {
            Class<?> type = loader.loadClass("app.App");
            System.out.println(
                    "call=" + type.getMethod("run").invoke(null));
        }

        var invalid = new DiagnosticCollector<JavaFileObject>();
        boolean badOk = compile(compiler, wrong,
                List.of("--release", "17", "-proc:none",
                        "-d", root.resolve("badOut").toString()),
                invalid);
        System.out.println("invalidCompiled=" + badOk);
        System.out.println("invalidErrors=" +
                invalid.getDiagnostics().stream()
                        .filter(x -> x.getKind() ==
                                Diagnostic.Kind.ERROR).count());
    }
}
~~~

Chạy từ một working directory tùy ý mà bạn có quyền ghi, với JDK 17 trở lên:

~~~sh
javac --release 17 CompilationTaskDemo.java
java CompilationTaskDemo work/basic
~~~

**Stdout đã kiểm chứng với một JDK chạy compiler API ở `--release 17`:**

~~~text
libCompiled=true
withoutClassPath=false
missingErrors=2
withClassPath=true
classMajor=61
call=Hi-Ada
invalidCompiled=false
invalidErrors=1
~~~

**Cảnh báo về số lượng diagnostics:** 2 và 1 là số thông báo ERROR của môi trường chạy ví dụ được kiểm tra; compiler implementation/JDK và cách lập source có thể làm **số diagnostics thay đổi**. Phần bất biến cần xác nhận là `withoutClassPath=false`, `withClassPath=true`, `invalidCompiled=false`, class version 61 và kết quả `Hi-Ada` khi compile/runtime đúng.

Phân tích:

1. Compiler API được lấy từ `ToolProvider`. `compile(...)` tạo file manager theo `UTF-8` và đóng bằng try-with-resources.
2. `getJavaFileObjectsFromPaths(List.of(file))` biến `Path` thành source compilation unit cho task. `classes=null` bởi vì lượt này không yêu cầu xử lý annotation trên class names.
3. `lib.Helper` được dịch vào `work/basic/libOut`.
4. Lượt dịch `app.App` đầu tiên cố tình **không có `-classpath libOut`**, nên import `lib.Helper` không được resolve; `CompilationTask.call()` trả false và lỗi vào `DiagnosticCollector`.
5. Lượt thứ hai thêm `-classpath libOut` thì compile thành công vào `work/basic/appOut`. Library output không tự động biến thành compiler class path chỉ vì nó đã tồn tại trong một thư mục.
6. Bytecode major 61 phù hợp Java 17. `--release 17` còn giới hạn cú pháp và Java SE/JDK API được công bố cho release 17; không chỉ set major version.
7. `URLClassLoader` với hai URLs cho phép nạp cả app và library trong một lớp runtime riêng. **CompilationTask không tự đưa bytecode vào class loader hiện tại.**
8. `Broken.java` có field `int` nhận String nên compile fail; chương trình đếm diagnostics nhưng không in thông điệp phụ thuộc locale.

**Không dùng một class loader đã nạp `app.App` làm cơ chế “thay mới cùng tên” vô hạn:** JVM ràng buộc identity lớp bởi binary name + defining loader. Muốn reload một phiên bản khác của cùng tên, thường cần class loader mới hoặc cơ chế instrument/redefinition chuyên biệt, không phải compile lại là class tự đổi.

## 5. `--release`: cú pháp, API nền tảng và class-file version

`--release 17` không chỉ đơn giản là hai cờ `-source 17 -target 17`. Nó yêu cầu compiler:

- Kiểm tra **ngôn ngữ Java 17** (không dùng cú pháp Java 18+).
- Sinh bytecode tương thích **class-file major version 61**.
- Dịch đối chiếu với **API Java SE/JDK được công bố cho release 17**, không vô tình gọi API chỉ có trên JDK mới hơn rồi tạo class file major 61.
- Giới hạn một số compiler options dùng để mở rộng truy cập vào JDK internals của release đích.

Bảng mốc class-file phổ biến:

| `--release` | Class-file major |
| --- | ---: |
| `11` | 55 |
| `17` | 61 |
| `21` | 65 |

**Không trộn `--release` với `-source`/`-target` trong cùng task**; `javac` từ chối cấu hình mâu thuẫn. Khi biên dịch module target 17, `--release 17` vẫn hỗ trợ JPMS, nhưng phải có module source path/module dependencies phù hợp.

Trong `getTask`, đặt option và giá trị ở **hai phần tử**:

~~~java
List<String> options = List.of(
    "--release", "17",
    "-encoding", "UTF-8",
    "-proc:none",
    "-d", "build/classes"
);
~~~

Đây là **snippet cấu hình**, không phải program độc lập. Đừng viết `List.of("--release 17", "-d build/classes")` và mong compiler parse như command shell đã tách sẵn; `Iterable<String> options` phải chứa các token như `javac` nhận.

**Kiểm tra tính tương thích thực sự:** chạy thử ứng dụng trên JDK 17 mục tiêu. `--release` không bao quát mọi dependency thứ ba, native code, reflection internals, cấu hình module graph ở deployment hay môi trường hệ điều hành.

## 6. Class path và module path không phải cùng một thứ

| Vấn đề | Class path | Module path |
| --- | --- | --- |
| Đối tượng chính | Class/JAR trong **unnamed module** | Named modules: module descriptors và package exports/readability |
| Tùy chọn | `-classpath`, `--class-path` | `--module-path`, `-p` |
| Module descriptor | Không yêu cầu `module-info.java` | Có `module-info.class` hoặc automatic module metadata nếu dùng JAR tự động |
| Quyền truy cập package | Java public/package rules và loader context | Ngoài Java visibility còn có `requires`/readability và `exports` |
| Cách xác định source modules | `compilationUnits` của các source files bình thường | `--module-source-path` và `-m module.name` để compile nhiều module |
| Output thường gặp | `build/classes/p/Foo.class` | `mods/m.name/p/Foo.class` khi compile nhiều module |

**`-classpath` không thay thế `--module-path`** khi Java source nằm trong named module và dependency cần được resolve qua module graph. Ngược lại, đưa JAR không modular vào module path có thể biến nó thành **automatic module** với tên cần được xác định rõ, không nên mặc định có cùng access semantics như class path.

Nếu chỉ cần dịch một module đơn lẻ, có thể đưa các `JavaFileObject` của module vào `compilationUnits` và cấu hình `--module-path` cho dependency đã biên dịch. Nếu cần dịch **nhiều modules từ một source tree**, `--module-source-path` kết hợp `-m` là cách biểu đạt rõ ràng.

### Ví dụ 2 — `ModuleTaskDemo.java`

Chương trình tạo hai named modules:

~~~text
work/modules/src/
  m.lib/
    module-info.java
    lib/Greeter.java
  m.app/
    module-info.java
    app/Main.java
~~~

`m.lib` khai báo `exports lib`. `m.app` khai báo `requires m.lib`, rồi gọi `lib.Greeter.hello()`. Thay vì tự lấy `JavaFileObject` từng file, task truyền option `-m m.lib,m.app` và `compilationUnits=null`; compiler sẽ duyệt các module sources từ `--module-source-path`.

Lưu **`ModuleTaskDemo.java`**:

~~~java
import javax.tools.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

public class ModuleTaskDemo {
    static void write(Path root, String name, String source)
            throws Exception {
        Path file = root.resolve(name);
        Files.createDirectories(file.getParent());
        Files.writeString(file, source, StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null)
            throw new IllegalStateException("Requires JDK");

        Path root = Path.of(args[0]);
        Path src = root.resolve("src");
        Path mods = root.resolve("mods");

        write(src, "m.lib/module-info.java",
                "module m.lib { exports lib; }");
        write(src, "m.lib/lib/Greeter.java",
                "package lib; public class Greeter {" +
                "public static String hello(){return \"module-hi\";} }");
        write(src, "m.app/module-info.java",
                "module m.app { requires m.lib; }");
        write(src, "m.app/app/Main.java",
                "package app; import lib.Greeter;" +
                "public class Main { public static void main(String[] a) {" +
                "System.out.println(Greeter.hello()); } }");

        var diagnostics = new DiagnosticCollector<JavaFileObject>();

        try (StandardJavaFileManager manager =
                compiler.getStandardFileManager(
                        diagnostics, null, StandardCharsets.UTF_8)) {
            List<String> options = List.of(
                    "--release", "17", "-proc:none",
                    "--module-source-path", src.toString(),
                    "-d", mods.toString(),
                    "-m", "m.lib,m.app");

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, manager, diagnostics, options, null, null);

            System.out.println("modulesCompiled=" +
                    Boolean.TRUE.equals(task.call()));
        }

        System.out.println("libModuleInfo=" +
                Files.exists(mods.resolve("m.lib/module-info.class")));
        System.out.println("appClass=" +
                Files.exists(mods.resolve("m.app/app/Main.class")));
    }
}
~~~

Chạy:

~~~sh
javac --release 17 ModuleTaskDemo.java
java ModuleTaskDemo work/modules
java --module-path work/modules/mods -m m.app/app.Main
~~~

**Stdout của hai lệnh `java`:**

~~~text
modulesCompiled=true
libModuleInfo=true
appClass=true
module-hi
~~~

Tại sao ví dụ thành công?

1. `--module-source-path work/modules/src` ánh xạ `m.lib`, `m.app` tới hai thư mục nguồn.
2. `-m m.lib,m.app` yêu cầu compiler biên dịch những module đó. Ở **`getTask`**, tham số thứ năm `classes` vẫn là `null`, vì `-m` được xử lý dưới `options`. Không nhầm `classes=List.of("m.lib")` với module selection.
3. `m.app` đọc `m.lib` bằng `requires`, và package `lib` được `m.lib` export. Đường dẫn file source modules đủ để javac resolve giữa các module trong cùng compilation task.
4. Output là `work/modules/mods/m.lib/...` và `work/modules/mods/m.app/...`.
5. Khi chạy `java`, vẫn phải cung cấp **`--module-path` cho runtime**, tách khỏi settings của compile task.

**Phân biệt `--module-source-path` và `--module-path`:** cái đầu trỏ tới **module sources đang biên dịch**; cái sau trỏ tới **module dependencies đã tồn tại** (directory/JAR chứa named modules) khi cần. Chúng có thể cùng xuất hiện trong một task có cả source modules mới và compiled module dependencies.

## 7. Annotation processing: code nào chạy lúc biên dịch?

Annotation processor là một đoạn Java code thực thi **trong quá trình compile**, dùng API `javax.annotation.processing` và `javax.lang.model` để đọc các elements được compiler thấy và có thể tạo source/resource files qua `Filer`.

Điều này khác với **reflection lúc chạy app**: processor chạy trước khi class output được sử dụng, có access tới model của source declarations theo rounds. Một processor có thể sinh `GeneratedFoo.java`, rồi compiler compile file mới cùng phần còn lại trong những rounds tiếp theo.

Phân biệt các thành phần:

| Thành phần | Vai trò |
| --- | --- |
| `AbstractProcessor` / `Processor` | Plugin chạy ở compile time |
| `@SupportedAnnotationTypes` | Tập annotation names mà processor chấp nhận; `"*"` là wildcard |
| `@SupportedSourceVersion(SourceVersion.RELEASE_17)` | Processor tuyên bố hỗ trợ source model của Java 17 |
| `RoundEnvironment` | Các elements và trạng thái của một processing round |
| `Filer.createSourceFile(...)` | Tạo source Java mới; thường phát sinh vòng processing tiếp theo |
| `Messager` | Phát compiler diagnostics từ processor |
| `-processor` | Danh sách processor classes được gọi **rõ ràng** |
| `-processorpath` | Nơi compiler **tìm processor code và dependencies của nó** trong classpath |
| `--processor-module-path` | Nơi tìm các **modular processors** trong module path |
| `-proc:none` | Tắt annotation processing |
| `-proc:only` | Chạy processing nhưng **không compile các source thành .class** sau đó |
| `-s` | Thư mục chứa generated `.java` |
| `-d` | Thư mục chứa compiled `.class` |

**Tách ba đường dẫn:** `-classpath` cho **application compile dependencies**; `-processorpath` cho **code processor chạy lúc compile**; `-s` là output Java source từ processor. Chúng có thể khác hoàn toàn. Nếu processor dùng dependency của riêng nó, dependency ấy phải có ở processor path, không chỉ có ở class path của ứng dụng.

Đối với named-module processors, sử dụng `--processor-module-path` theo các yêu cầu packaging/module declarations. Không tự đặt đồng thời processor path và processor module path một cách mâu thuẫn. Nếu muốn chọn processors không dựa vào auto-discovery, `-processor tooling.GenerateProcessor` hoặc `task.setProcessors(...)` là hai cơ chế chọn tường minh, với các vòng đời và class loading cần quản trị.

### Vấn đề bảo mật của annotation processing

**Processor là executable code, không phải annotation data thụ động.** Khi được kích hoạt, processor có thể thực thi code trong quá trình compile với quyền của tiến trình/host. Vì vậy:

- Đừng tự động chạy processors từ một dependency chưa tin cậy.
- Trong dịch vụ nhận source từ bên ngoài, chủ động chọn `-proc:none` theo mặc định khi không cần code generation.
- Nếu cần processing, pin phiên bản processor và dependencies, đặt processor path rõ ràng, chạy trong môi trường sandbox/tiến trình hạn chế quyền khi code không đáng tin.
- Không coi `DiagnosticCollector` là sandbox. Nó chỉ nhận diagnostics, không giới hạn CPU, RAM, I/O, network hoặc hành vi của processor.

**Không dựa vào default discovery như một hợp đồng ổn định giữa mọi JDK.** Các phiên bản `javac` có thể khác về mặc định kích hoạt annotation processing; cấu hình rõ `-proc:none` hoặc `-processor` khi cần reproducible behavior.

## 8. Ví dụ 3 — một processor tạo Java source trong quá trình compile

Ví dụ này cố tình cho user class phụ thuộc vào `GeneratedMsg` chưa tồn tại:

~~~java
package client;
public class UseGenerated {
    public static void main(String[] args) {
        System.out.println("message=" + GeneratedMsg.message());
    }
}
~~~

Đoạn này **chỉ là nội dung source mà chương trình demo sẽ tự ghi ra file**; tự compile riêng sẽ fail nếu `GeneratedMsg` chưa được tạo. Chương trình bên dưới thực hiện đúng ba bước:

1. Dịch processor với `-proc:none` để tránh processor discovery trong lúc **build chính processor**.
2. Dịch `UseGenerated.java` khi **không có processor** để cho thấy compile fail.
3. Dịch với `-processorpath`, `-processor` và `-s` để processor tạo `client.GeneratedMsg`, sau đó compiler tự compile generated source thành class.

Lưu toàn bộ **`ProcessorTaskDemo.java`**:

~~~java
import javax.tools.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.io.*;

public class ProcessorTaskDemo {
    static Path write(Path base, String name, String source)
            throws IOException {
        Path file = base.resolve(name);
        Files.createDirectories(file.getParent());
        Files.writeString(file, source, StandardCharsets.UTF_8);
        return file;
    }

    static boolean compile(
            JavaCompiler compiler, Path source, List<String> options)
            throws IOException {
        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
                compiler.getStandardFileManager(
                        diagnostics, null, StandardCharsets.UTF_8)) {
            var units = manager.getJavaFileObjectsFromPaths(
                    List.of(source));
            var task = compiler.getTask(
                    new StringWriter(), manager, diagnostics,
                    options, null, units);
            return Boolean.TRUE.equals(task.call());
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null)
            throw new IllegalStateException("Requires JDK");

        Path root = Path.of(args[0]);

        Path processor = write(
            root, "src/tooling/GenerateProcessor.java", """
                package tooling;
                import javax.annotation.processing.*;
                import javax.lang.model.*;
                import javax.lang.model.element.*;
                import javax.tools.*;
                import java.io.*;
                import java.util.*;

                @SupportedAnnotationTypes("*")
                @SupportedSourceVersion(SourceVersion.RELEASE_17)
                public final class GenerateProcessor
                        extends AbstractProcessor {
                    private boolean written;

                    @Override public boolean process(
                            Set<? extends TypeElement> annotations,
                            RoundEnvironment round) {
                        if (written || round.processingOver())
                            return false;

                        written = true;
                        try (Writer out = processingEnv.getFiler()
                                .createSourceFile("client.GeneratedMsg")
                                .openWriter()) {
                            out.write(
                                "package client; public class GeneratedMsg {" +
                                "public static String message() {" +
                                "return \\"generated\\"; } }");
                        } catch (IOException ex) {
                            throw new UncheckedIOException(ex);
                        }
                        return false;
                    }
                }
                """);

        Path user = write(
            root, "src/client/UseGenerated.java", """
                package client;
                public class UseGenerated {
                    public static void main(String[] args) {
                        System.out.println(
                            "message=" + GeneratedMsg.message());
                    }
                }
                """);

        Path procClasses = root.resolve("processors");
        Path classes = root.resolve("classes");
        Path generated = root.resolve("generated");

        boolean procReady = compile(compiler, processor,
                List.of("--release", "17", "-proc:none",
                        "-d", procClasses.toString()));
        System.out.println("processorCompiled=" + procReady);

        boolean disabled = compile(compiler, user,
                List.of("--release", "17", "-proc:none",
                        "-d", root.resolve("noProc").toString()));
        System.out.println("withoutProcessor=" + disabled);

        boolean enabled = compile(compiler, user,
                List.of("--release", "17",
                        "-processorpath", procClasses.toString(),
                        "-processor", "tooling.GenerateProcessor",
                        "-s", generated.toString(),
                        "-d", classes.toString()));
        System.out.println("withProcessor=" + enabled);

        System.out.println("generatedSource=" +
                Files.exists(generated.resolve(
                        "client/GeneratedMsg.java")));
        System.out.println("generatedClass=" +
                Files.exists(classes.resolve(
                        "client/GeneratedMsg.class")));
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~sh
javac --release 17 ProcessorTaskDemo.java
java ProcessorTaskDemo work/processing
java -cp work/processing/classes client.UseGenerated
~~~

**Stdout của hai lệnh `java`:**

~~~text
processorCompiled=true
withoutProcessor=false
withProcessor=true
generatedSource=true
generatedClass=true
message=generated
~~~

### Vì sao đây là annotation processing thật?

- Processor được compiler dịch vào `work/processing/processors/tooling/GenerateProcessor.class`.
- Trong compile task thứ hai, `-proc:none` tắt processing. Source `UseGenerated` tham chiếu `GeneratedMsg` chưa tồn tại, nên compiler báo lỗi.
- Trong task thứ ba, `-processorpath work/processing/processors` đưa processor code vào môi trường compiler, và `-processor tooling.GenerateProcessor` yêu cầu chạy nó **tường minh**.
- Processor implement `process(...)`, gọi `Filer.createSourceFile("client.GeneratedMsg")`, tạo file `work/processing/generated/client/GeneratedMsg.java`.
- Compiler chạy các processing rounds cần thiết, sau đó compile `UseGenerated` và generated `GeneratedMsg` vào `work/processing/classes`. Việc class được phát sinh là một phần của compile task; không cần gọi `javac` lần nữa cho generated file.
- Lệnh `java -cp ... client.UseGenerated` là **runtime execution sau compile**, không phải annotation processing. Nó in `message=generated`.

**Tại sao cần biến `written`?** Processor có thể được gọi trong nhiều rounds. Nếu luôn tạo cùng file ở mỗi round, `Filer` sẽ báo lỗi do trùng file. Ví dụ dùng `written` để chỉ phát sinh một lần trong vòng đời processor.

**Tại sao `return false`?** Nó cho phép processor khác tiếp tục xem các annotations tương ứng. `return true` mang nghĩa processor claim annotations nó xử lý, không có nghĩa “task compile thành công”; kết quả compile nằm ở `CompilationTask.call()`.

**Về `@SupportedAnnotationTypes("*")`:** wildcard giúp demo chạy mà không cần định nghĩa annotation riêng, nhưng processor production nên khai báo các annotation cụ thể để tránh chạy ngoài dự kiến và phối hợp đúng với processors khác.

## 9. `-proc:only`, `-proc:none` và cơ chế chọn processor

Ba chế độ cần nhớ:

| Cấu hình | Compile application classes? | Chạy annotation processors? | Tình huống |
| --- | --- | --- | --- |
| `-proc:none` | Có | Không | Compile thường, kiểm soát rủi ro processor |
| `-proc:only` + processor được cấu hình | Không thực hiện pha compile class sau processing | Có | Chỉ sinh source/metadata hoặc kiểm tra annotation |
| `-processor X` (và processor path) | Có, nếu không đặt `-proc:only` | Có, gọi X | Code generation trong build |
| Không chỉ định processing options | Phụ thuộc compiler version và cấu hình | Có thể không tự discovery ở JDK mới | Không nên dựa vào mặc định |

Với JDK 17, cú pháp được tài liệu hóa rõ cho `-proc:none` và `-proc:only`. Đừng gắn cờ `-proc:full` vào các ví dụ bắt buộc chạy trên Java 17 nếu chưa kiểm tra khả năng hỗ trợ của **compiler cụ thể**; với nhiệm vụ ở đây, việc chỉ định `-processor` đủ để processing chạy cùng compilation.

### `task.setProcessors(...)` khác với `-processor` thế nào?

`CompilationTask` cũng có:

~~~java
task.setProcessors(
    java.util.List.of(new MyProcessor())
);
~~~

Đây là **snippet**, giả định một class `MyProcessor` implement `javax.annotation.processing.Processor` đã có sẵn. API này cung cấp **processor instances trực tiếp**, thay vì để compiler discover bằng class/module path. Nó phù hợp cho ứng dụng đã quản lý lifecycle/constructor/dependencies của processors, nhưng không có nghĩa processor được sandbox hoặc mặc định được phép thực thi mọi thứ.

Không trộn `setProcessors(...)` với cấu hình `-processor` mâu thuẫn. Chọn **một cách kiểm soát rõ ràng**: explicit instance hoặc explicit processor names + processor path.

### Processor module path

Nếu processor được đóng gói thành **named module**, dùng `--processor-module-path` cùng module provider metadata (ví dụ `provides javax.annotation.processing.Processor with ...`). Nó khác `--module-path` của ứng dụng mà bạn đang biên dịch. Processor cần được load vào môi trường **host compiler**, trong khi module path của ứng dụng dùng để resolve module graph của **source đang dịch**.

Dùng `--module-path` cho application dependencies **không tự cấp** processor discovery như `--processor-module-path`. Tách các path để tránh compile-time code execution ngoài dự kiến.

## 10. Diagnostics: chẩn đoán đầu ra một cách đáng tin

`DiagnosticCollector<JavaFileObject>` lưu từng `Diagnostic` với các trường:

- `getKind()`: `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE`, `OTHER`.
- `getSource()`: `JavaFileObject` tương ứng, có thể `null` nếu diagnostic không gắn một file.
- `getLineNumber()`, `getColumnNumber()`, `getStartPosition()`, `getEndPosition()`: vị trí khi compiler cung cấp; có thể là `Diagnostic.NOPOS`.
- `getCode()`: mã diagnostic do compiler cung cấp; hữu ích để phân nhóm nhưng không phải toàn bộ public contract giữa các compiler khác nhau.
- `getMessage(Locale)`: nội dung theo locale; tránh dùng **chuỗi tiếng Anh của compiler** làm key logic duy nhất.

**Snippet xử lý diagnostics cho một task** (giả định đã có `diagnostics`):

~~~java
for (Diagnostic<? extends JavaFileObject> diagnostic
        : diagnostics.getDiagnostics()) {
    if (diagnostic.getKind() == Diagnostic.Kind.ERROR) {
        JavaFileObject file = diagnostic.getSource();
        String at = file == null
                ? "<unknown>" : file.getName();

        System.out.println(at + ":" + diagnostic.getLineNumber()
                + " [" + diagnostic.getCode() + "] "
                + diagnostic.getMessage(java.util.Locale.ROOT));
    }
}
~~~

Đây không phải chương trình độc lập; nó cần biến `DiagnosticCollector<JavaFileObject> diagnostics` được tạo cho một compilation task. Khi output ra API response, nên escaping và giới hạn số diagnostic/tổng bytes để tránh spam và tránh rò rỉ đường dẫn nội bộ của hệ thống.

**`Boolean.FALSE` khác với exception**: source lỗi cú pháp/type thường làm task trả false và diagnostic ERROR. Các option không hợp lệ có thể khiến `getTask(...)` ném `IllegalArgumentException`; lỗi trong processor/file manager do người dùng cung cấp có thể được bọc trong `RuntimeException`. Không thiết kế code chỉ bắt `false` rồi bỏ toàn bộ exceptions.

## 11. Lỗi thường gặp khi cấu hình compile task

| Hiện tượng | Nguyên nhân thường gặp | Cách điều tra/sửa |
| --- | --- | --- |
| `getSystemJavaCompiler() == null` | Runtime image không chứa compiler implementation | Dùng JDK có `jdk.compiler`; kiểm tra `java --list-modules`/runtime image |
| `package ... does not exist` | Thiếu classpath hoặc module graph | Kiểm tra `-classpath`/`--module-path` và named module `requires`/`exports` |
| Compile library thành công nhưng compile app thất bại | Library output không nằm trên classpath của task app | Thêm output dir/JAR của library vào `-classpath` |
| `class file has wrong version` lúc chạy | Chạy trên JVM cũ hơn target bytecode | Compile với `--release` phù hợp và kiểm tra runtime JDK |
| Compile trên JDK mới nhưng runtime JDK 17 thiếu method | Chỉ dùng `-source/-target` nên vô tình tham chiếu API mới | Dùng `--release 17` |
| Compiler từ chối `--release` với `-source/-target` | Các cách chọn release chồng lấn | Chỉ chọn một cách, ưu tiên `--release` |
| `module not found` | Thiếu `--module-path` hoặc module source path | Xác minh tên module, `module-info`, layout nguồn |
| `module-info.java` xuất hiện trong classpath build nhưng API không thấy | Trộn modular và classpath compilation modes | Chọn rõ module mode và đặt files đúng module source layout |
| Processor không chạy | `-proc:none`, sai processor path, không chỉ định hoặc discovery thay đổi | Dùng `-processor` hoặc `setProcessors`; chọn path rõ ràng |
| `Annotation processor ... not found` | Processor chưa compile hoặc class path/processor path không đúng | Build processor trước, kiểm tra class name và dependencies |
| `FilerException: Attempt to recreate a file` | Processor sinh lại cùng source trong nhiều rounds | Dùng trạng thái one-shot, kiểm tra `processingOver()` |
| Generated source có nhưng class không thấy | `-proc:only`, output path khác, compile task thất bại | Kiểm tra `-proc`, `-d`, diagnostics, generated classes |
| Processor sinh class hoặc resource vào sai chỗ | Nhầm `-s` và `-d`/file manager locations | `-s` cho source, `-d` cho classes |
| Java source mới compile xong nhưng class cũ vẫn chạy | Class loader cũ đã định nghĩa cùng binary name | Dùng loader mới, versioned class name, hoặc cơ chế reload phù hợp |
| Build service chậm/không ổn định | Quá nhiều task/file managers, code processor có side effects, unbounded input | Cache hợp lý, kiểm soát tài nguyên, timeout/sandbox bên ngoài |

### Đường dẫn trên Windows và Linux/macOS

`-classpath` nhận **một chuỗi path** sau option. Nếu có nhiều entries, nối bằng `File.pathSeparator` (Windows thường `;`, Linux/macOS thường `:`), thay vì hardcode dấu phân cách theo hệ điều hành.

Snippet:

~~~java
String deps = java.util.List.of(
        java.nio.file.Path.of("build/libs/core.jar"),
        java.nio.file.Path.of("build/classes"))
    .stream()
    .map(java.nio.file.Path::toString)
    .collect(java.util.stream.Collectors.joining(
            java.io.File.pathSeparator));

List<String> options = List.of(
    "--release", "17",
    "-classpath", deps,
    "-proc:none",
    "-d", "build/output");
~~~

Đoạn này chưa phải chương trình độc lập, nhưng `List<String> options` có dạng chính xác để đưa vào `getTask`. Tương tự, `--module-path` và `-processorpath` nhận danh sách paths phân tách theo quy tắc nền tảng.

### In-memory sources và output

Không bắt buộc viết source `.java` ra disk. `SimpleJavaFileObject` có thể bọc một `String` và cung cấp `getCharContent(...)`; `ForwardingJavaFileManager` có thể chặn output class bytes vào bộ nhớ. Khi dùng kỹ thuật đó, vẫn phải giải quyết **classpath/modulepath**, cách nạp class bytes, security và versioning. `CompilationTask` không tự giải quyết các ranh giới ấy.

Ví dụ `SimpleJavaFileObject` tối thiểu (**snippet**, không độc lập):

~~~java
class SourceFromString extends SimpleJavaFileObject {
    private final String source;

    SourceFromString(String binaryName, String source) {
        super(java.net.URI.create(
                "string:///" + binaryName.replace('.', '/')
                        + JavaFileObject.Kind.SOURCE.extension),
              JavaFileObject.Kind.SOURCE);
        this.source = source;
    }

    @Override
    public CharSequence getCharContent(boolean ignoreEncodingErrors) {
        return source;
    }
}
~~~

Khi dùng, thêm import `javax.tools.*`, tạo một `SourceFromString("demo.Hello", source)` rồi truyền trong `compilationUnits`; tránh nhận input source không kiểm soát và chạy ngay trong host process.

## 12. Reliability và security khi biên dịch theo yêu cầu

1. **Phân loại nguồn:** generated code nội bộ khác với source từ người dùng không tin cậy. Java compiler API không phải biện pháp sandbox.
2. **Giới hạn tài nguyên:** đặt giới hạn file sizes, số source units, số diagnostics, CPU/time/memory/disk ở tiến trình/sandbox. `CompilationTask.call()` là lời gọi blocking; API không tự có timeout.
3. **Không tự động chạy bytecode đã compile:** Compiler chỉ xác nhận class hợp lệ theo Java/JVM rules, **không xác nhận an toàn nghiệp vụ**. Một `ClassLoader` riêng không tự cung cấp sandbox bảo mật.
4. **Không chạy annotation processors lạ:** `-proc:none` theo mặc định trong pipeline không cần processors; explicit allowlist và processor path khi cần.
5. **Tách output giữa các build:** không ghi đè class output của build trước trong khi đang chạy để tránh stale artifacts/races.
6. **Định danh build:** lưu source hash, compiler version, release target, options, dependency versions và processor versions để kết quả reproducible.
7. **Quản lý file manager:** đóng `StandardJavaFileManager` bằng try-with-resources; nếu cache/reuse cho nhiều task tuần tự, bảo đảm không có simultaneous mutation và đóng khi xong.
8. **Xử lý diagnostics và exceptions:** `call() == false` không đồng nghĩa mọi lỗi đều là cú pháp Java; thêm log diagnostics và nguyên nhân RuntimeException, phân biệt I/O, module access, processor failure.
9. **Phân biệt compile và run:** chạy trong một process/container với policy độc lập; bytecode có thể tham chiếu thư viện/nền tảng hợp lệ lúc compile nhưng thiếu ở runtime.
10. **Không dựa vào default annotation discovery:** giữa các JDK/flags có thể thay đổi; explicit options giúp tránh bất ngờ.

## 13. Bài tập tự kiểm tra

**Câu 1.** Muốn compile `app.App` dùng `lib.Helper` đã biên dịch vào `libOut`, cần điều gì trong task mới?

**Đáp án:** Thêm `-classpath libOut` (hoặc cấu hình `StandardLocation.CLASS_PATH`) để compiler thấy `Helper.class`. Thư mục output của task trước không tự được thêm vào class path.

**Câu 2.** Trong `getTask(out,fm,diag,options,classes,units)`, tham số `classes` có phải là nơi đặt `List.of("app.App")` để chạy class ngay sau build không?

**Đáp án:** Không. `classes` dành cho các class names cần annotation processing; `units` là nguồn cần dịch. Chạy class là bước khác sau compile.

**Câu 3.** `--release 17` làm gì mà `-target 17` một mình không bảo đảm?

**Đáp án:** Nó vừa chọn mức language, class-file version 61, vừa giới hạn API platform theo release 17. `-target` riêng chủ yếu chọn bytecode version.

**Câu 4.** Khi nào dùng `--module-source-path` và `--module-path`?

**Đáp án:** `--module-source-path` tìm **module source roots** cần biên dịch; `--module-path` tìm **named module dependencies** đã có để resolve. Có thể dùng cả hai khi thích hợp.

**Câu 5.** `-processorpath` khác `-classpath` thế nào?

**Đáp án:** Processor path tìm và load compiler plugins thực thi ở compile time; class path cho dependency của source ứng dụng. Tách chúng để quản lý dependencies và quyền thực thi.

**Câu 6.** Nếu dùng `-proc:none` với source `UseGenerated` phụ thuộc `GeneratedMsg` chưa có, task có tự tạo `GeneratedMsg` không?

**Đáp án:** Không. `-proc:none` chặn processors; compiler thất bại nếu không tìm thấy class nguồn/bytecode đó qua các paths khác.

**Câu 7.** `-proc:only` có tạo application `.class` như lượt compile bình thường không?

**Đáp án:** Không. Nó chỉ thực hiện annotation processing và source/resource generation, không biên dịch application classes sau processing.

**Câu 8.** `task.call()==false`; làm sao biết lỗi ở source file, classpath hay processing?

**Đáp án:** Dùng `DiagnosticCollector`, xem `Kind.ERROR`, code/source/line/message. Đồng thời kiểm tra options/locations và processor logs; không suy luận từ boolean một mình.

**Câu 9.** Một ứng dụng JDK 21 compile bằng `--release 17`, class bytecode major bao nhiêu?

**Đáp án:** 61. Nhưng phải kiểm tra third-party APIs và runtime dependencies riêng, vì `--release` không kiểm soát mọi JAR bên ngoài.

**Câu 10.** Khi đã compile class `demo.Plugin` phiên bản B, có thể yêu cầu cùng class loader đã load phiên bản A tự thay definition bằng cách gọi `CompilationTask` lần nữa không?

**Đáp án:** Không. Compiler sinh bytes; class identity/definition do loader/JVM quản lý. Dùng class loader mới hoặc instrumentation/redefinition phù hợp để cập nhật trong runtime.

## 14. Nguồn chính thống Java 17

- `JavaCompiler`, `getTask`, `CompilationTask`, `DiagnosticCollector` và ví dụ file manager: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html
- `ToolProvider.getSystemJavaCompiler()` và điều kiện `jdk.compiler` có mặt: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html
- `StandardJavaFileManager` và `getJavaFileObjectsFromPaths`/`setLocationFromPaths`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html
- `StandardLocation`, các file-manager locations chuẩn: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/StandardLocation.html
- `JavaCompiler.CompilationTask` và `setProcessors`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.CompilationTask.html
- `javax.annotation.processing.Processor`, `AbstractProcessor`, `RoundEnvironment`, `Filer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/package-summary.html
- JDK `javac` options (`--release`, `-classpath`, `--module-source-path`, `--module-path`, `-processorpath`, `-proc:none/only`): https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- `Diagnostic`, mã và vị trí lỗi: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/Diagnostic.html

**Tóm tắt cốt lõi:** `CompilationTask` là một công việc biên dịch được **cấu hình tường minh**. Class path giải quyết dependencies không modular; module path và module source path giải quyết named modules; `--release` ràng buộc cả Java language/API/bytecode target; annotation processor là code **chạy ở compile time**, phải được kiểm soát qua `-proc`, processor path và processor selection. Đọc `DiagnosticCollector`, kiểm soát output locations và tách **compile** khỏi **load/run** giúp một hệ thống dynamic Java compilation đúng và dễ bảo trì.
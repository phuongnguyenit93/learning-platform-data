# Tạo CompilationTask bằng getTask và truyền tùy chọn biên dịch

## 1. Tại sao cần JavaCompiler API?

Bình thường, một lượt biên dịch được gọi từ terminal:

~~~bash
javac --release 17 -encoding UTF-8 -d build/classes src/demo/Hello.java
~~~

Với **Compiler API** của Java (JSR 199, package `javax.tools`, module `java.compiler`), chính một chương trình Java có thể tạo lượt biên dịch, truyền file nguồn, tùy chọn, nơi ghi class và nhận chẩn đoán mà không phải tách log từ một lệnh shell. Cách này hữu ích cho trình soạn thảo, công cụ tạo mã, hệ thống kiểm thử bài nộp, build integration và chương trình kiểm tra Java source.

Luồng thao tác:

~~~text
ToolProvider.getSystemJavaCompiler()
               |
               v
JavaCompiler + StandardJavaFileManager
               |
       JavaFileObject SOURCE
       List<String> options
       DiagnosticListener / Writer
               |
               v
      compiler.getTask(...)
               |
        CompilationTask
               |
             call()
               |
      Boolean success + diagnostics
               |
       .class tại CLASS_OUTPUT
~~~

**`getTask` chỉ tạo task; `CompilationTask.call()` mới thực hiện biên dịch.** Kết quả compile không tự động chạy Java program mới sinh ra. Sau đó muốn chạy class cần một JVM/class loader có runtime classpath tương ứng.

Mục tiêu bài: hiểu đủ sáu tham số của `getTask`, dùng `JavaFileObject` đúng cách, chuyển compiler options thành danh sách argument, thu diagnostics có cấu trúc, đọc kết quả thành công/thất bại và quản lý vòng đời file manager.

## 2. Các API liên quan và trách nhiệm

| API | Vai trò |
| --- | --- |
| `ToolProvider.getSystemJavaCompiler()` | Lấy Java compiler được runtime cung cấp nếu có |
| `JavaCompiler` | Tạo `CompilationTask` và file manager |
| `JavaCompiler.CompilationTask` | Đại diện một lần compile; gọi `call()` |
| `StandardJavaFileManager` | Chuyển `File`/`Path` thành `JavaFileObject` và tìm/ghi file |
| `JavaFileObject` | Trừu tượng hóa nguồn Java hoặc class file |
| `DiagnosticCollector<JavaFileObject>` | Thu các lỗi/cảnh báo có cấu trúc |
| `Diagnostic.Kind` | Phân loại `ERROR`, `WARNING`, `NOTE` và các loại khác |
| `StandardLocation` | Chỉ vị trí chuẩn như `CLASS_OUTPUT`, `CLASS_PATH`, `SOURCE_PATH` |
| `SimpleJavaFileObject` | Lớp cơ sở nếu muốn cung cấp source ngay từ string |

Với named module Java, host sử dụng Compiler API cần khai báo:

~~~java
module my.compiler.host {
    requires java.compiler;
}
~~~

Đây là một **fragment module-info.java**, không phải chương trình độc lập. Nếu host chạy trên classpath của JDK đầy đủ, có thể sử dụng `javax.tools` như các package Java chuẩn thông thường.

Điểm quan trọng: `getSystemJavaCompiler()` có thể trả về `null` trên một runtime image không chứa compiler provider. Có `java` để chạy ứng dụng không đồng nghĩa luôn có `javac` hoặc `jdk.compiler`. Cần kiểm tra kết quả trước khi sử dụng API.

## 3. Chữ ký JavaCompiler.getTask và sáu tham số

~~~java
JavaCompiler.CompilationTask getTask(
        Writer out,
        JavaFileManager fileManager,
        DiagnosticListener<? super JavaFileObject> diagnosticListener,
        Iterable<String> options,
        Iterable<String> classes,
        Iterable<? extends JavaFileObject> compilationUnits);
~~~

Đây là **chữ ký interface** nhằm học API, không phải một class độc lập có thể chạy.

| Tham số | Nghĩa | Cách dùng thường gặp |
| --- | --- | --- |
| `out` | Writer cho output bổ sung; nếu null, công cụ dùng stderr mặc định | `new PrintWriter(System.err, true)` |
| `fileManager` | Dịch vụ tìm/đọc/ghi sources/classes | `compiler.getStandardFileManager(...)` |
| `diagnosticListener` | Nhận compiler diagnostics có cấu trúc | `DiagnosticCollector<JavaFileObject>` |
| `options` | Danh sách tùy chọn compiler theo từng argument | `List.of("--release","17","-d","build/classes")` |
| `classes` | Tên các lớp được chỉ định cho **annotation processing**, không phải file nguồn cần biên dịch thông thường | `null` |
| `compilationUnits` | Iterable các `JavaFileObject` có `Kind.SOURCE` để compile | `manager.getJavaFileObjectsFromPaths(...)` |

**Đặc biệt dễ nhầm:** `classes` không phải nơi viết `"src/demo/Hello.java"`; đưa một source file thành `JavaFileObject` ở tham số `compilationUnits`. Còn `options` chứa compiler flags, không chứa cả lệnh shell hay danh sách file nguồn kiểu CLI. Trong bài tập compile source thông thường, `classes = null`.

Nếu `fileManager = null`, compiler sử dụng standard file manager. Nếu `diagnosticListener = null`, compiler dùng cơ chế báo lỗi mặc định; khi cung cấp listener, một số output không khớp với interface `Diagnostic` vẫn có thể được ghi qua writer/kênh mặc định. Đừng dựa vào việc một `StringWriter` không có output để kết luận task thành công.

## 4. Ví dụ Java 17+ hoàn chỉnh, đã chạy thử

Tạo cây thư mục:

~~~text
project/
├── CompileWithApi.java
├── src/
│   └── demo/Hello.java
└── build/
    ├── tool/       # host class
    └── classes/    # output của compiler được gọi từ API
~~~

### 4.1. File src/demo/Hello.java

~~~java
package demo;

public final class Hello {
    public static void main(String[] args) {
        System.out.println("Hello, Compiler API");
    }
}
~~~

### 4.2. File CompileWithApi.java

~~~java
import java.io.IOException;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class CompileWithApi {
    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Expected: source-file output-directory");
        }

        Path source = Path.of(args[0]);
        Path output = Path.of(args[1]);
        Files.createDirectories(output);

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "A JDK compiler is required");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        boolean success;
        try (StandardJavaFileManager manager =
                     compiler.getStandardFileManager(
                             diagnostics,
                             Locale.ROOT,
                             StandardCharsets.UTF_8)) {

            Iterable<? extends JavaFileObject> units =
                    manager.getJavaFileObjectsFromPaths(
                            List.of(source));

            List<String> options = List.of(
                    "--release", "17",
                    "-encoding", "UTF-8",
                    "-d", output.toString(),
                    "-proc:none");

            JavaCompiler.CompilationTask task = compiler.getTask(
                    new PrintWriter(System.err, true),
                    manager,
                    diagnostics,
                    options,
                    null,
                    units);

            success = Boolean.TRUE.equals(task.call());

            for (Diagnostic<? extends JavaFileObject> d :
                    diagnostics.getDiagnostics()) {
                System.err.printf(Locale.ROOT,
                        "%s at line %d: %s%n",
                        d.getKind(),
                        d.getLineNumber(),
                        d.getMessage(Locale.ROOT));
            }
        }

        System.out.println(success ? "COMPILE_OK" : "COMPILE_FAILED");
        if (!success) {
            System.exit(1);
        }
    }
}
~~~

**Giải thích hành vi:**

1. `Files.createDirectories(output)` tạo thư mục đầu ra để compiler có nơi ghi `.class`.
2. `ToolProvider.getSystemJavaCompiler()` lấy compiler của JVM/JDK đang chạy host. Khi thiếu provider thì dừng với thông báo rõ ràng.
3. `getStandardFileManager` nhận `Locale.ROOT` và `UTF-8` để làm rõ cách đọc nguồn và hiển thị diagnostics.
4. `manager.getJavaFileObjectsFromPaths(List.of(source))` tạo một compilation unit cho tệp nguồn, không tự quét mọi Java file trong directory.
5. `options` truyền `--release`, `-encoding`, `-d` và `-proc:none` thành **các string arguments rời**. `-proc:none` cố ý tắt annotation processing để ví dụ không phụ thuộc processor bên ngoài.
6. `compiler.getTask(...)` tạo nhiệm vụ; `task.call()` thực hiện compile; `Boolean.TRUE` là thành công.
7. `DiagnosticCollector` lưu các lỗi và cảnh báo; chương trình in từng diagnostic qua stderr.
8. `try-with-resources` đóng `StandardJavaFileManager` khi đã xong, giải phóng tài nguyên đọc JAR/file.
9. Host in trạng thái trên stdout; nếu compile thất bại, host thoát với mã khác 0 để script/CI phát hiện.

### 4.3. Lệnh biên dịch/chạy

Từ thư mục project trên Bash (Linux/macOS/Git Bash):

~~~bash
mkdir -p build/tool build/classes
javac --release 17 -encoding UTF-8 -d build/tool CompileWithApi.java
java -cp build/tool CompileWithApi src/demo/Hello.java build/classes
java -cp build/classes demo.Hello
~~~

Stdout của lệnh **chạy host Compiler API**:

~~~text
COMPILE_OK
~~~

Stdout của lệnh **chạy class mới được biên dịch**:

~~~text
Hello, Compiler API
~~~

Đây là hai chương trình được chạy ở hai bước khác nhau. Không có lệnh `javac src/demo/Hello.java` ở ngoài: chính host thực hiện lượt biên dịch này.

Ví dụ đã được chạy thử trên **OpenJDK 21 với `--release 17`**, và hai dòng output trên đã được quan sát trực tiếp.

Trên Windows PowerShell, thay lệnh tạo thư mục bằng:

~~~powershell
New-Item -ItemType Directory -Force build/tool, build/classes | Out-Null
~~~

Hai lệnh `java -cp` còn lại giữ được vì mỗi classpath có một entry. Nếu nhiều entries: Linux/macOS dùng dấu hai chấm (`:`), Windows dùng dấu chấm phẩy (`;`); đặt classpath trong dấu nháy nếu shell cần.

## 5. Khi source bị lỗi: task.call và DiagnosticCollector

Tạo thêm tệp **src/demo/Broken.java**:

~~~java
package demo;

public final class Broken {
    MissingType value;
}
~~~

`MissingType` không được khai báo, vì thế khi chạy:

~~~bash
java -cp build/tool CompileWithApi src/demo/Broken.java build/classes
~~~

host vẫn tạo được `CompilationTask` nhưng compilation thất bại; `task.call()` trả false. Host in trạng thái:

~~~text
COMPILE_FAILED
~~~

Các lỗi kiểu `cannot find symbol` được in ra stderr. **Dòng trên chỉ là stdout do host sinh**, không phải toàn bộ stderr compiler; wording, line number và số diagnostics có thể khác theo JDK. Host thoát với mã 1, giúp người gọi nhận diện task thất bại.

Khi tích hợp với IDE hoặc CI, nên giữ cả `Diagnostic.Kind`, vị trí file và message, nhưng không viết test phụ thuộc một đoạn stderr được định dạng nguyên văn. Trong code trên, `d.getLineNumber()` có thể trả vị trí lỗi thực tế, hoặc sentinel nếu diagnostic không có vị trí.

Một lượt task thất bại không nhất thiết xóa sạch output cũ. Để tránh sử dụng nhầm class trước đó, hãy biên dịch trong output directory mới/sạch khi cần kiểm chứng kết quả.

## 6. Truyền compiler options: những quy tắc quan trọng

**Trong API, options là một danh sách string**, không phải chuỗi lệnh shell có khoảng trắng.

Lệnh terminal:

~~~bash
javac --release 17 -encoding UTF-8 -d build/classes -classpath lib/api.jar src/demo/Hello.java
~~~

Chuyển thành:

~~~java
List<String> options = List.of(
        "--release", "17",
        "-encoding", "UTF-8",
        "-d", "build/classes",
        "-classpath", "lib/api.jar");

// Source file đi qua compilationUnits, không nằm trong options.
~~~

**Sai:**

~~~java
List<String> wrong = List.of("--release 17", "-d build/classes");
~~~

`"--release 17"` là một string duy nhất, không phải hai đối số compiler. Trừ khi một tùy chọn cụ thể hỗ trợ dạng gắn giá trị như `--key=value`, hãy đưa option và value thành phần tử riêng.

| Option | Ý nghĩa và lưu ý |
| --- | --- |
| `--release 17` | Giới hạn cú pháp, bytecode và Java SE API cho release được hỗ trợ |
| `-d outputDir` | Chọn thư mục ghi `.class`; nên tạo thư mục trước |
| `-encoding UTF-8` | Cấu hình charset source; nên khớp file manager |
| `-cp paths` hoặc `-classpath paths` | Compile dependencies: các JAR, class directories; `paths` là **một argument** có separator của OS |
| `--source-path roots` | Nơi tìm source liên quan, **không** tự yêu cầu compile mọi file |
| `--module-path paths` | Module dependencies trong JPMS |
| `-processor name` | Chọn annotation processor cụ thể |
| `-processorpath paths` | Nơi tìm processor code |
| `-proc:none` | Tắt annotation processors cho lượt compile này |
| `-Xlint:all` | Bật warnings bổ sung theo compiler |
| `-Werror` | Warning trở thành nguyên nhân build thất bại |

**Không chuyển nguyên xi toàn bộ shell command** vào một phần tử options, và không đưa `src/demo/Hello.java` vào options như thể tham số cuối của command line. Source input thuộc `compilationUnits`.

**`-J-Xmx512m` không phải cách đặt heap cho JavaCompiler API.** Flag `-J` dành cho launcher `javac` để truyền argument đến JVM chạy javac. Khi host đang gọi Compiler API trong cùng JVM, phải cấu hình heap ở **JVM chạy host**, ví dụ:

~~~bash
java -Xmx512m -cp build/tool CompileWithApi src/demo/Hello.java build/classes
~~~

`compiler.isSupportedOption(optionName)` có thể giúp kiểm tra compiler nhận một option và thông tin số lượng đối số theo contract. Dù option được hỗ trợ, tổ hợp options và giá trị cụ thể vẫn có thể không hợp lệ hoặc không tồn tại trên filesystem.

### --release khác với chỉ -source / -target

`--release 17` kiểm soát source language, class file version và các API của Java platform release mục tiêu. Chỉ dùng `-source 17 -target 17` không có hàng rào API đầy đủ khi cross-compile cho release cũ trên JDK mới. Host dùng Compiler API cũng phải chọn toolchain và target version đúng, không chỉ vì host tự chạy được trên JDK mới mà bỏ qua cấu hình release.

## 7. File manager locations so với -d / -cp

Ví dụ dùng compiler options:

~~~java
List<String> options = List.of("-d", "build/classes");
~~~

Một cách khác là cấu hình **StandardJavaFileManager** bằng `StandardLocation`:

~~~java
// Fragment trong host, với manager đã tạo và output directory tồn tại.
manager.setLocationFromPaths(
        javax.tools.StandardLocation.CLASS_OUTPUT,
        List.of(Path.of("build/classes")));

manager.setLocationFromPaths(
        javax.tools.StandardLocation.CLASS_PATH,
        List.of(Path.of("lib/api.jar")));
~~~

`CLASS_OUTPUT` chọn nơi ghi bytecode, `CLASS_PATH` chọn compiled dependencies, `SOURCE_PATH` là gốc tìm Java source, còn `SOURCE_OUTPUT` là nơi annotation processors tạo generated source. Đừng lẫn những location này.

`setLocationFromPaths` nhận collection `Path` và thay thế search path trước đó cho location; output location phải phù hợp contract, thông thường là **một directory đã tồn tại**. Với `CLASS_PATH` có thể cung cấp nhiều đường dẫn JAR và thư mục.

**Chọn một nguồn cấu hình cho mỗi location.** Nếu đã đặt `CLASS_OUTPUT` trong file manager, đừng đồng thời truyền `-d` chỉ sang thư mục khác rồi kỳ vọng không có xung đột. Cách dùng `-d` ở ví dụ chính đơn giản nhất để người học nhận thấy compile output.

**Classpath của host khác compile classpath của chương trình được biên dịch:** việc chạy `java -cp build/tool CompileWithApi` chỉ giúp JVM nạp host. Source `Hello.java` có thể có phụ thuộc ngoài, và khi ấy compile task cần classpath riêng trong options/file manager. Sau khi compile xong, chương trình chạy lại cần runtime classpath đúng với các class/JAR đó.

## 8. Diagnostic và Writer là hai kênh khác nhau

`DiagnosticCollector<JavaFileObject>` lưu cấu trúc của từng chẩn đoán. Có thể khai thác:

~~~java
// Fragment trong host có biến diagnostics hợp lệ.
for (Diagnostic<? extends JavaFileObject> d
        : diagnostics.getDiagnostics()) {
    System.out.println("kind=" + d.getKind());
    System.out.println("code=" + d.getCode());
    System.out.println("line=" + d.getLineNumber());
    System.out.println("column=" + d.getColumnNumber());
    System.out.println("message=" + d.getMessage(Locale.ROOT));
}
~~~

- `getKind()`: lỗi, cảnh báo, note...
- `getSource()`: source file object nếu diagnostic liên quan file, có thể null.
- `getLineNumber()` / `getColumnNumber()`: vị trí nếu có, có thể là `Diagnostic.NOPOS`.
- `getCode()`: mã diagnostic do compiler cung cấp.
- `getMessage(Locale)`: nội dung dễ đọc, có thể thay đổi theo bản JDK hoặc locale.

Lỗi compiler có thể xuất hiện trong collector; thông tin bổ sung vẫn có thể đi qua `out`, và diagnostic không gắn được với nguồn cụ thể có thể không có số dòng. Vì vậy đừng chỉ dựa trên việc Writer trống hoặc chỉ so khớp chuỗi error message.

Để quyết định thành công, dùng **Boolean từ `call()`**; để giải thích thất bại, dùng **danh sách diagnostics**, cùng những exception phát sinh trong khi thiết lập file manager/options.

## 9. Chọn nhiều source files và source trong bộ nhớ

`getJavaFileObjectsFromPaths` cho phép compile nhiều file:

~~~java
// Fragment: cả hai file phải có thật; cần manager hợp lệ.
Iterable<? extends JavaFileObject> units =
        manager.getJavaFileObjectsFromPaths(List.of(
                Path.of("src/demo/Hello.java"),
                Path.of("src/demo/Helper.java")));

JavaCompiler.CompilationTask task =
        compiler.getTask(null, manager, diagnostics,
                options, null, units);
~~~

Đó là **fragment**, không phải chương trình độc lập; khác với danh sách đường dẫn ở classpath. Compiler xét đúng tập compilation units ban đầu và tìm thêm dependencies theo cấu hình tương ứng.

Đôi khi source được tạo trong bộ nhớ. Dùng `SimpleJavaFileObject` thay vì buộc phải ghi tệp tạm:

~~~java
// Fragment: imports java.net.URI và javax.tools.SimpleJavaFileObject.
final class TextSource extends SimpleJavaFileObject {
    private final String source;

    TextSource(String qualifiedName, String source) {
        super(URI.create("string:///"
                + qualifiedName.replace('.', '/')
                + Kind.SOURCE.extension), Kind.SOURCE);
        this.source = source;
    }

    @Override
    public CharSequence getCharContent(boolean ignoreEncodingErrors) {
        return source;
    }
}
~~~

Sau đó:

~~~java
// Fragment trong host có compiler, manager, diagnostics, options.
JavaFileObject input = new TextSource(
        "demo.Generated",
        "package demo; public class Generated {}");
JavaCompiler.CompilationTask task = compiler.getTask(
        null, manager, diagnostics, options, null, List.of(input));
boolean success = Boolean.TRUE.equals(task.call());
~~~

**Phân biệt:** đây là **in-memory source**, không mặc nhiên là **in-memory class output**. Với standard file manager, compiled classes có thể vẫn ghi ra filesystem. Để giữ bytecode trong bộ nhớ cần custom `JavaFileManager`/`JavaFileObject` và class loader phù hợp.

`compilationUnits` phải gồm file objects đại diện `Kind.SOURCE`. Nếu đưa object thuộc kind khác hoặc option không hợp lệ vào `getTask`, có thể nhận `IllegalArgumentException` trước khi `call()` chạy. Đừng nhầm lỗi thiết lập API với diagnostic của một Java source thiếu type.

## 10. Annotation processing, classes và vòng đời task

`CompilationTask` còn có những setter như `setProcessors(Iterable<? extends Processor>)` và `setLocale(Locale)` để cấu hình trước khi compile. Ví dụ khái niệm:

~~~java
// Fragment: processors, compiler, manager, diagnostics, options, units có sẵn.
JavaCompiler.CompilationTask task = compiler.getTask(
        null, manager, diagnostics, options, null, units);
task.setProcessors(processors);
task.setLocale(Locale.ROOT);
boolean ok = Boolean.TRUE.equals(task.call());
~~~

Phải gọi setters **trước `call()`**. Tham số `classes` của `getTask` dành cho tên class cần được annotation processor xử lý trong trường hợp thích hợp; nó **không phải** tên class cần load/run, không phải danh sách source files, và thường để null.

Nếu project dùng annotation processors, phải cấu hình processor path, discovery, generated source output và các rounds có chủ đích. Ví dụ runnable ở mục 4 đặt `-proc:none` để tránh việc một processor tình cờ có trong môi trường làm thay đổi kết quả. Khi dùng processors, bỏ flag này và cấu hình theo đúng công cụ build.

Một instance `CompilationTask` dùng cho **một lần gọi `call()`**. Muốn compile lần tiếp theo, tạo task mới; file manager chuẩn có thể tái sử dụng **cho các lượt compile tuần tự** nếu còn mở, để giảm chi phí đọc JAR/thư mục. Không mặc định một task hoặc file manager tùy biến an toàn khi dùng đồng thời từ nhiều threads.

## 11. Xử lý ngoại lệ, resources và giới hạn an toàn

Có ba nhóm trạng thái:

1. **Không có compiler:** `getSystemJavaCompiler() == null`; không tạo được task.
2. **Đầu vào/options không hợp lệ:** `getTask` có thể ném `IllegalArgumentException` hoặc exception do component cung cấp; lỗi này không nhất thiết thành một diagnostic bình thường.
3. **Biên dịch đã thực hiện nhưng source sai:** `task.call()` trả `false` và listener nhận diagnostics; host cần báo thất bại với exit code phù hợp.

Cần quản lý thêm:

- Dùng **try-with-resources** cho file manager. Nếu dùng một file manager nhiều lần, đóng sau lượt cuối và tránh việc race giữa tasks.
- Tạo output directory có chủ đích; không tin rằng compile thất bại sẽ tự rollback toàn bộ file đã ghi. Nếu cần giao dịch output, compile vào thư mục tạm rồi chỉ xuất bản khi thành công.
- Không tự cho rằng class mới được compile đã nạp vào class loader của host. Runtime có classpath và module path riêng.
- Với named modules, lựa chọn `--module-path`, `--module-source-path` và module-oriented locations theo đúng JPMS; `getTask` không tự giải quyết mọi dependency.
- **Compiler API không phải sandbox.** Annotation processors có thể thực thi code trong JVM compile, và chương trình mới được tạo có thể nguy hiểm nếu được chạy. Với source không tin cậy, cần cách ly process/OS, giới hạn quyền I/O, thời gian, CPU, memory và policy processor. `-proc:none` không thay thế isolation.

## 12. So sánh getTask, Tool.run và gọi javac ngoài tiến trình

| Phương pháp | Đặc điểm | Tình huống thích hợp |
| --- | --- | --- |
| `JavaCompiler.getTask` | API có compilation units, file manager và diagnostics có cấu trúc | Host compiler, IDE/plugin, kiểm tra/generate Java source |
| `JavaCompiler.run(...)` | Giao diện Tool nhận các command-line style arguments và trả mã trạng thái số | Gọi compiler theo mô hình CLI đơn giản trong JVM |
| Tiến trình `javac` riêng | Có process boundary, output và exit code của OS | Dùng compiler toolchain khác hoặc muốn cách ly compiler process |

`getTask` chạy compiler qua API hiện có của host. Nó không tự chọn một JDK khác chỉ nhờ mục tiêu `--release 17`. Nếu cần JDK compiler phiên bản riêng, phải chọn toolchain hoặc khởi chạy một process thích hợp.

## 13. Lỗi thường gặp và cách tránh

| Hiện tượng | Lý do | Cách xử lý |
| --- | --- | --- |
| `compiler == null` | Runtime thiếu compiler provider | Dùng JDK có compiler hoặc triển khai toolchain |
| `getTask` từ chối option | Dùng string `"--release 17"` hoặc option không hỗ trợ | Truyền từng token, kiểm tra compiler/JDK |
| Không thấy class output | Thiếu `-d` / `CLASS_OUTPUT`, output sai | Tạo và chỉ rõ output dir |
| Không compile source mong muốn | Chưa đưa `JavaFileObject` vào `compilationUnits` | Xây units từ đúng source files |
| Truyền file vào `classes` | Nhầm với class names cho annotation processing | Dùng `classes=null` khi compile source |
| Diagnostics khó đọc | Không có collector hoặc thiếu locale/source positions | Dùng `DiagnosticCollector` và đọc vị trí |
| Task thất bại nhưng script coi như thành công | Bỏ qua `Boolean call()` | Kiểm tra true/false, trả nonzero khi cần |
| `ClassNotFoundException` khi chạy class mới | Runtime classpath không có output dir | Chạy với `-cp build/classes` hoặc loader phù hợp |
| Compile pass nhưng phụ thuộc thiếu khi chạy | Compile/runtime classpath khác nhau | Kiểm soát dependencies cả hai pha |
| Task thứ hai bị lỗi khi gọi lại `call()` | Reuse đối tượng task | Tạo `CompilationTask` mới |
| Annotation processor không chạy | Có `-proc:none` hoặc thiếu processor config | Bật và cấu hình processor có chủ đích |
| Biên dịch code lạ trong cùng JVM | Rủi ro processors, file I/O, class loading | Cách ly môi trường và quyền thực thi |

## 14. Checklist kiểm thử JavaCompiler API

Trước khi `getTask`:

- Đã xác minh có JavaCompiler provider chưa?
- Đã chọn đủ chính xác các tệp `.java` cần compile và đưa chúng thành `JavaFileObject.Kind.SOURCE` chưa?
- `options` có được tách đúng các argument, và các đường dẫn/release có phù hợp không?
- Compile classpath/module path và annotation processor options có đúng source set không?
- Output directory có sẵn và không xung đột `-d` với file manager locations không?

Sau `call()`:

- Kết quả có thực sự là `Boolean.TRUE`, không phải chỉ không ném exception?
- Diagnostics có `ERROR`, warning hay vị trí cần báo cho người dùng không?
- Class output có nằm trong thư mục đúng dự kiến không?
- File manager đã đóng đúng vòng đời không?
- Chương trình được biên dịch đã được chạy/test với runtime classpath và toolchain phù hợp chưa?
- Compile thất bại có bị output cũ đánh lừa hay không?

### Bài thực hành

1. Tạo `CompileWithApi.java` và `src/demo/Hello.java` như mục 4. Biên dịch host rồi chạy host; xác nhận `COMPILE_OK`. Chạy output class; xác nhận `Hello, Compiler API`.
2. Thêm `Broken.java` với `MissingType`; chạy host để nhận `COMPILE_FAILED` và diagnostics; không khẳng định stderr có đúng một số dòng cố định.
3. Thay `--release 17` bằng release khác được JDK hỗ trợ; xem bytecode major version bằng `javap -verbose` và bảo đảm code/API phù hợp.
4. Dùng `StandardLocation.CLASS_OUTPUT` thay cho `-d`; đảm bảo không khai báo hai output locations mâu thuẫn.
5. Tạo task thứ hai mới với một source khác, thử reuse file manager tuần tự rồi đóng tài nguyên.
6. Khi thực sự cần annotation processing, bỏ `-proc:none`, cấu hình processors và quan sát generated sources/diagnostics.

**Kết luận:** tạo `CompilationTask` đúng yêu cầu ba điều kiện: **nguồn dưới dạng `JavaFileObject`**, **options dạng danh sách đối số tách riêng**, và **`task.call()` được kiểm tra cùng diagnostics**. API cung cấp khả năng điều khiển compiler bằng Java code, không thay thế việc quản lý JDK, dependency, runtime hoặc môi trường thực thi an toàn.

## Tài liệu tham khảo

- [Java SE 17 — JavaCompiler](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html): chữ ký `getTask`, file managers và diagnostics.
- [Java SE 17 — StandardJavaFileManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html): lấy file objects từ Path, cấu hình locations.
- [Java SE 17 — JavaCompiler.CompilationTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.CompilationTask.html): `call()`, `setProcessors`, `setLocale`.
- [JDK 17 — javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): compiler options, source/target/release.

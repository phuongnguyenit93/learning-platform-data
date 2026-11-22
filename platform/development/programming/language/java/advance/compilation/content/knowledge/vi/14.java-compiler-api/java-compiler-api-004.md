# Biên dịch tệp Java bằng StandardJavaFileManager

Khi dùng lệnh `javac`, công cụ tự tìm file nguồn, đọc nội dung, tra cứu thư viện và ghi các file `.class`. Với ứng dụng cần gọi compiler ngay bên trong Java — chẳng hạn IDE, công cụ kiểm tra source, hệ thống chấm bài, trình sinh mã hoặc build tool — Java SE cung cấp **Java Compiler API** trong module `java.compiler`. Thành phần quan trọng để làm việc với **các tệp thực trên đĩa** là `javax.tools.StandardJavaFileManager`.

`StandardJavaFileManager` chuyển các `Path`/`File` nguồn thành đối tượng `JavaFileObject`, quản lý các vị trí tìm class/source và nơi ghi kết quả. Nó phối hợp với `JavaCompiler`, `CompilationTask` và `DiagnosticCollector`, giúp chương trình Java biên dịch tệp mà không cần tạo tiến trình `javac` bên ngoài.

Bài học dùng **Java 17+**, ưu tiên API được Java SE hỗ trợ, mã chạy đầy đủ, kết quả kỳ vọng rõ ràng, và các lưu ý về encoding, classpath, quản lý tài nguyên và lỗi thường gặp.

## 1. Sơ đồ các thành phần

```text
Path của source .java
        |
        v
StandardJavaFileManager
  - getJavaFileObjectsFromPaths(...)
  - setLocationFromPaths(CLASS_OUTPUT, ...)
  - setLocationFromPaths(CLASS_PATH, ...)
        |
        v
Iterable<? extends JavaFileObject>
        |
        v
JavaCompiler.getTask(...)
        |
        +----> CompilationTask.call() ------> true/false
        |
        +----> DiagnosticCollector --------> lỗi/cảnh báo/vị trí
        |
        +----> StandardJavaFileManager ----> ghi .class
```

Các vai trò không nên đánh đồng:

| Thành phần | Trách nhiệm |
| --- | --- |
| `ToolProvider.getSystemJavaCompiler()` | Lấy system Java compiler nếu runtime có |
| `JavaCompiler` | Cung cấp các phương thức gọi compiler từ chương trình |
| `StandardJavaFileManager` | Quản lý các file nguồn/class trên filesystem, JAR và những location chuẩn |
| `JavaFileObject` | Biểu diễn một tệp dùng bởi compiler, ví dụ source hoặc class file |
| `StandardLocation` | Các location được chuẩn hóa như `CLASS_OUTPUT`, `CLASS_PATH`, `SOURCE_PATH` |
| `JavaCompiler.CompilationTask` | Một tác vụ compilation được cấu hình bởi nguồn và options; `call()` thực thi |
| `DiagnosticCollector<JavaFileObject>` | Nhận diagnostic dạng đối tượng thay vì phân tích chuỗi stderr |

Từ khóa **standard** ở đây chỉ file manager theo Java Compiler API, không hàm ý mọi implementation compiler phải xử lý mọi đường dẫn kỳ lạ giống nhau. File manager chuẩn cung cấp cách làm việc tiện lợi với file và path thông thường.

## 2. Vì sao phải dùng file manager?

Giả sử bạn muốn biên dịch `src/demo/Hello.java` vào `out/demo/Hello.class`. Một cách là khởi chạy `javac -d out src/demo/Hello.java` bằng `ProcessBuilder`; nhưng nếu phần mềm đã là Java và cần kiểm soát diagnostics hoặc input/output, Java Compiler API phù hợp hơn.

File manager xử lý các nhiệm vụ như:

- Bao bọc một file `.java` thành `JavaFileObject` để compiler có thể đọc nó.
- Quản lý **source encoding** khi chuyển byte sang ký tự.
- Thiết lập **class output**, **classpath**, **source path** và các location chuẩn.
- Truy cập class file hoặc JAR mà compiler cần để phân giải kiểu.
- Quản lý tài nguyên nội bộ như handle tới JAR; hỗ trợ `flush()`/`close()`.
- Cho phép compiler ghi `.class` ở đúng package path thay vì chính ứng dụng tự xây dựng từng tên file.

`JavaFileObject` không phải nội dung source đã được parser đọc xong. Nó là một **đối tượng trừu tượng hóa file**. Compiler tiếp tục chịu trách nhiệm lexing, parsing, type checking và code generation.

## 3. Ví dụ đầy đủ Java 17+: tạo file, biên dịch và kiểm tra output

Lưu tệp bên dưới với tên **`FileManagerCompileDemo.java`** ở một thư mục làm việc bất kỳ. Chương trình tự tạo source `fm-demo/src/demo/Hello.java`, gọi compiler, kiểm tra file class và in kết quả có thể kiểm chứng.

```java
import java.io.IOException;
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
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public class FileManagerCompileDemo {
    public static void main(String[] args) throws IOException {
        Path source = Path.of("fm-demo/src/demo/Hello.java");
        Path classes = Path.of("fm-demo/classes");

        Files.createDirectories(source.getParent());
        Files.createDirectories(classes);

        String code = """
                package demo;

                public class Hello {
                    public static void main(String[] args) {
                        System.out.println("Xin chào, Java!");
                    }
                }
                """;

        Files.writeString(source, code, StandardCharsets.UTF_8);

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "Cần chạy bằng JDK có system Java compiler");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        boolean success;
        try (StandardJavaFileManager manager =
                     compiler.getStandardFileManager(
                             diagnostics, Locale.ROOT,
                             StandardCharsets.UTF_8)) {

            manager.setLocationFromPaths(
                    StandardLocation.CLASS_OUTPUT,
                    List.of(classes));

            Iterable<? extends JavaFileObject> units =
                    manager.getJavaFileObjectsFromPaths(
                            List.of(source));

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, manager, diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null, units);

            success = Boolean.TRUE.equals(task.call());
        }

        long errors = diagnostics.getDiagnostics().stream()
                .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
                .count();

        System.out.println("success=" + success);
        System.out.println("classExists=" + Files.isRegularFile(
                classes.resolve("demo/Hello.class")));
        System.out.println("errors=" + errors);
    }
}
```

### Biên dịch và chạy chương trình điều khiển compiler

Trong thư mục chứa `FileManagerCompileDemo.java`, dùng JDK 17+:

```bash
javac -encoding UTF-8 FileManagerCompileDemo.java
java FileManagerCompileDemo
```

Stdout chính xác khi môi trường có compiler và các thao tác file hợp lệ:

```text
success=true
classExists=true
errors=0
```

Chương trình cũng sinh các tệp:

```text
fm-demo/
├── src/demo/Hello.java
└── classes/demo/Hello.class
```

Kiểm tra file class bằng launcher:

```bash
java -cp fm-demo/classes demo.Hello
```

Stdout chính xác:

```text
Xin chào, Java!
```

Hai lời gọi `java` khác nhau: lần đầu chạy **chương trình điều khiển compiler** `FileManagerCompileDemo`; lần sau chạy **class vừa được sinh** `demo.Hello`.

Nếu chạy demo nhiều lần trong cùng thư mục, `Files.writeString` sẽ viết lại source đã tạo và compiler có thể ghi lại class. Khi thử nghiệm tính đầy đủ của một lượt compilation, nên bắt đầu bằng output sạch để không nhầm file `.class` cũ với file mới được sinh. Đừng xóa folder dữ liệu của người khác khi dọn output.

## 4. Phân tích trình tự trong ví dụ

**Bước 1 — tạo source thực.** `Path.of("fm-demo/src/demo/Hello.java")` xác định file theo đường dẫn tương đối với thư mục làm việc hiện tại. `Files.createDirectories(...)` tạo package directory và output directory. `Files.writeString(..., UTF_8)` ghi đúng byte encoding.

**Bước 2 — lấy compiler.** `ToolProvider.getSystemJavaCompiler()` là điểm vào của API. Nếu môi trường runtime không có system compiler thì có thể trả `null`; chương trình xử lý điều đó tường minh. Không nên tự suy từ tên class `ToolProvider` rằng mọi JRE tối giản đều có `javac`.

**Bước 3 — lấy file manager.** `compiler.getStandardFileManager(diagnostics, Locale.ROOT, UTF_8)` thiết lập listener cho diagnostic không gây lỗi nghiêm trọng, locale hiển thị và charset để giải mã file. Charset ở đây khớp với encoding dùng để tạo source.

**Bước 4 — đặt output.** `setLocationFromPaths(StandardLocation.CLASS_OUTPUT, List.of(classes))` yêu cầu ghi class file vào một **thư mục output đã tồn tại**. Package `demo` khiến class nằm dưới `demo/Hello.class`.

**Bước 5 — đưa source vào task.** `getJavaFileObjectsFromPaths(List.of(source))` chuyển tập `Path` tới `Iterable<? extends JavaFileObject>`. Tham số nhận là **file**, không phải thư mục source root. API có overload nhận `Collection<? extends Path>`, được ưu tiên từ Java 13.

**Bước 6 — cấu hình compilation.** `getTask(...)` nhận file manager, diagnostic listener, compiler options, danh sách tên class cho annotation processing (ở ví dụ truyền `null`), và compilation units. Options `--release 17` giữ target Java 17; `-proc:none` tắt annotation processing cho bài demo.

**Bước 7 — thực thi.** `task.call()` là điểm thực sự biên dịch. Chỉ gọi `getTask(...)` mà không gọi `call()` thì chưa tạo được file class.

**Bước 8 — đọc kết quả.** `Boolean.TRUE.equals(task.call())` giúp có boolean rõ ràng. `DiagnosticCollector` cung cấp danh sách diagnostic có cấu trúc. `Files.isRegularFile(...)` là kiểm tra artifact; bản thân tồn tại file không đủ chứng minh artifact mới được tạo trong lần chạy hiện tại nếu chưa làm sạch output.

**Bước 9 — đóng file manager.** Try-with-resources gọi `close()` kể cả khi xảy ra lỗi. Nó giúp giải phóng file handle, nhất là khi xử lý nhiều JAR hoặc chạy trên Windows, nơi file handle còn mở có thể cản trở thao tác với artifact.

## 5. Chữ ký JavaCompiler.getTask giải thích từng tham số

Một cách viết phổ biến:

```java
JavaCompiler.CompilationTask task = compiler.getTask(
        outWriter,
        fileManager,
        diagnosticListener,
        options,
        classes,
        compilationUnits);
```

Đây là **đoạn minh họa chữ ký**, không phải chương trình độc lập.

| Tham số | Ý nghĩa |
| --- | --- |
| `outWriter` | Writer cho output bổ sung từ compiler; `null` dùng output mặc định |
| `fileManager` | File manager để tìm/ghi file; `null` khiến compiler dùng mặc định |
| `diagnosticListener` | Nhận diagnostic; `null` khiến compiler định dạng thông báo theo cách mặc định |
| `options` | Các tùy chọn compiler như `--release`, `-proc:none`; `null` nghĩa là không thêm option |
| `classes` | Tên class dành cho annotation processing trong chế độ hỗ trợ; thường để `null` cho biên dịch source |
| `compilationUnits` | Các `JavaFileObject` loại SOURCE cần biên dịch |

Chỉ truyền tên file vào `classes` thay vì `compilationUnits` là sai mục đích. `classes` **không** phải danh sách file `.class` cần xuất ra và không thay thế cho tập nguồn đầu vào.

`getTask(...)` có thể ném `IllegalArgumentException` khi option không hợp lệ hoặc compilation unit có kind không phải source. Nếu thành phần do người gọi cung cấp gặp lỗi không thể tiếp tục, cũng có thể có exception. Không nên giả định mọi lỗi đều được báo dưới dạng `CompilationTask.call() == false`.

Một `CompilationTask` đại diện cho **một lượt biên dịch**, không dùng lại cùng task object để gọi `call()` nhiều lần. Có thể tạo các task khác nhau với compiler/file manager theo yêu cầu, nhưng phải quản lý input, output và lifecycle rõ ràng.

## 6. Chọn đúng phương thức getJavaFileObjects

`StandardJavaFileManager` có nhiều cách tạo `JavaFileObject`:

| Phương thức | Khi nên dùng |
| --- | --- |
| `getJavaFileObjects(Path... paths)` | Danh sách `Path` truyền dưới dạng varargs |
| `getJavaFileObjectsFromPaths(Collection<? extends Path>)` | Có sẵn một `Collection<Path>`; phù hợp Java 17+ |
| `getJavaFileObjects(File... files)` | Đã có các `java.io.File` |
| `getJavaFileObjectsFromFiles(Iterable<? extends File>)` | Tập các `File` |
| `getJavaFileObjects(String... names)` | Các tên file/đường dẫn dưới dạng chuỗi |
| `getJavaFileObjectsFromStrings(Iterable<String>)` | Có danh sách chuỗi đường dẫn |

Ví dụ tương đương về ý định với file `Hello.java`:

```java
Path path = Path.of("fm-demo/src/demo/Hello.java");

Iterable<? extends JavaFileObject> a =
        manager.getJavaFileObjects(path);

Iterable<? extends JavaFileObject> b =
        manager.getJavaFileObjectsFromPaths(List.of(path));
```

Đây là **snippet trong scope có biến `manager`**, không phải file Java độc lập. Không truyền nguyên một thư mục vào danh sách file nguồn: API có thể ném `IllegalArgumentException` khi đầu vào là directory.

**Cạm bẫy với overload cũ:** overload `getJavaFileObjectsFromPaths(Iterable<? extends Path>)` đã bị deprecated từ Java 13. Hãy dùng overload nhận **`Collection`**, ví dụ `List.of(path)`, hoặc `getJavaFileObjects(path)`. Bởi `Path` tự triển khai `Iterable<Path>`, code gọi nhầm overload Iterable với một `Path` đơn lẻ có thể bị hiểu thành các thành phần của đường dẫn thay vì một tệp source.

Nếu phải lấy mọi `.java` dưới một source root, người gọi tự tìm các file phù hợp bằng `Files.walk(...)` (đồng thời đóng Stream), rồi truyền danh sách các `Path` **tệp thực**. File manager không tự hiểu rằng một `Path` thư mục nghĩa là “biên dịch đệ quy mọi file Java”.

## 7. StandardLocation: classpath khác output

Các location có tác động riêng tới việc compiler tìm và ghi file:

| Location | Mục đích |
| --- | --- |
| `StandardLocation.CLASS_OUTPUT` | Thư mục ghi `.class` |
| `StandardLocation.SOURCE_OUTPUT` | Thư mục ghi source sinh ra, thường qua annotation processor |
| `StandardLocation.CLASS_PATH` | Các root/JAR dùng để tìm class trên classpath |
| `StandardLocation.SOURCE_PATH` | Các root dùng để tìm source bổ sung |
| `StandardLocation.ANNOTATION_PROCESSOR_PATH` | Đường tìm annotation processor trên classpath processor |
| `StandardLocation.MODULE_PATH` | Module path theo JPMS |
| `StandardLocation.SYSTEM_MODULES` | Platform/system modules do toolchain định nghĩa |

Các hằng này là những location **khác nhau**. Đặt `CLASS_OUTPUT` không đồng nghĩa thiết lập `CLASS_PATH`; compiler cần tra cứu một dependency đã build ở thư mục khác thì cần đường tìm phù hợp.

Với Java 17+:

```java
manager.setLocationFromPaths(
        StandardLocation.CLASS_OUTPUT,
        List.of(Path.of("build/app-classes")));

manager.setLocationFromPaths(
        StandardLocation.CLASS_PATH,
        List.of(Path.of("build/lib-classes"),
                Path.of("lib/helper.jar")));
```

Đây là **snippet cấu hình trong một chương trình**, không phải lệnh độc lập; các thư mục output cần được tạo trước và các JAR phải tồn tại. Các entry CLASS_PATH là root package hoặc JAR, không phải tên class hay package cụ thể.

`setLocationFromPaths(...)` **thay thế** search path trước đó của location được chọn; nó không tự append vào classpath mặc định. Nếu cần thêm nhiều entry, đưa toàn bộ tập entry mong muốn vào cùng một `Collection<Path>`.

Đối với output location, API yêu cầu đúng **một** path và đó phải là một directory hiện có. Truyền hai output directories cho `CLASS_OUTPUT`, hoặc đường dẫn đến một file thay vì directory, sẽ không đáp ứng contract.

Không nên cấu hình trùng một location vừa qua `setLocationFromPaths(...)` vừa qua compiler option `-d` hoặc `-classpath` mà không xác định rõ precedence. Chọn một cách cấu hình nhất quán sẽ giúp debug và kiểm thử dễ hơn.

## 8. Biên dịch nhiều tệp trong một task

Nếu chương trình có:

```text
src/
  demo/
    Main.java
    Helper.java
```

thì có thể truyền hai file cùng lúc:

```java
List<Path> sources = List.of(
        Path.of("src/demo/Main.java"),
        Path.of("src/demo/Helper.java"));

Iterable<? extends JavaFileObject> units =
        manager.getJavaFileObjectsFromPaths(sources);

JavaCompiler.CompilationTask task = compiler.getTask(
        null, manager, diagnostics,
        List.of("--release", "17", "-proc:none"),
        null, units);

boolean success = Boolean.TRUE.equals(task.call());
```

Đây là **snippet** sử dụng các biến `compiler`, `manager`, `diagnostics` đã khai báo, không phải một file runnable riêng.

Nếu `Main` cần `Helper` thì việc liệt kê cả hai source tường minh sẽ giúp kiểm soát rõ tập đầu vào. Nếu chỉ truyền `Main.java` mà compiler tìm thấy `Helper.java` thông qua source path, compiler có thể thực hiện **implicit source compilation** theo các quy tắc `javac`. Do đó “chỉ một `JavaFileObject` trong compilationUnits” không bảo đảm chỉ một class được sinh.

Đối với build cần tái lập, nên cấu hình rõ nguồn, sourcepath/classpath, output và compiler options. Đừng dựa vào các class file tồn tại từ lần trước.

## 9. Biên dịch dependency riêng và dùng CLASS_PATH cho ứng dụng

Giả sử đã biên dịch thư viện `demo.lib.Utility` vào `build/lib-classes`; ứng dụng ở `src/app/demo/app/Main.java` cần `Utility`. Khi tạo compilation task cho app:

```java
manager.setLocationFromPaths(
        StandardLocation.CLASS_OUTPUT,
        List.of(Path.of("build/app-classes")));

manager.setLocationFromPaths(
        StandardLocation.CLASS_PATH,
        List.of(Path.of("build/lib-classes")));

Iterable<? extends JavaFileObject> appUnits =
        manager.getJavaFileObjectsFromPaths(List.of(
                Path.of("src/app/demo/app/Main.java")));

boolean ok = Boolean.TRUE.equals(
        compiler.getTask(
                null, manager, diagnostics,
                List.of("--release", "17", "-proc:none"),
                null, appUnits
        ).call());
```

Đây là snippet cấu hình, cần tạo các directory output trước khi gọi. Sau đó runtime thường cần cả hai nơi:

- macOS/Linux: `java -cp "build/app-classes:build/lib-classes" demo.app.Main`.
- Windows: `java -cp "build/app-classes;build/lib-classes" demo.app.Main`.

**Compile-time classpath và runtime classpath độc lập.** Compiler API thành công không tự làm JVM launcher chạy ứng dụng nhìn thấy các dependency.

Dùng `-cp` với ứng dụng đơn giản cũng là cách khác để cấu hình classpath, nhưng code dùng file manager nên ưu tiên một cách nhất quán: set `StandardLocation.CLASS_PATH` hoặc truyền option `-classpath`; đừng trộn để vô tình ghi đè đường tìm.

## 10. Charset: lý do UTF-8 phải được cấu hình đúng

Có hai nơi liên quan encoding trong ví dụ:

```java
Files.writeString(source, code, StandardCharsets.UTF_8);

compiler.getStandardFileManager(
        diagnostics, Locale.ROOT, StandardCharsets.UTF_8);
```

Dòng đầu ghi tệp nguồn thành byte UTF-8. Dòng sau yêu cầu file manager dùng UTF-8 để giải mã byte thành ký tự khi đọc source. Hai lựa chọn phải thống nhất để tránh lỗi hoặc văn bản tiếng Việt bị hỏng.

Từ JDK 18 (JEP 400), UTF-8 là charset mặc định của phần lớn API Java SE; tuy vậy, nếu mục tiêu là build nhất quán qua JDK và môi trường, chỉ định rõ charset vẫn dễ hiểu và đáng tin hơn, đặc biệt khi đầu vào có ký tự ngoài ASCII.

`Locale.ROOT` ở `getStandardFileManager` ảnh hưởng tới cách trình bày diagnostic do file manager phát ra; nó không phải encoding. `UTF_8` là đối tượng `Charset`, không phải tên ngôn ngữ.

Nếu file nguồn được ghi bằng UTF-16 nhưng file manager đọc bằng UTF-8, nguồn sẽ không được giải mã đúng. Đừng “sửa” bằng cách thay mọi Unicode thành ký tự ASCII nếu nguyên nhân là mismatch charset.

## 11. DiagnosticCollector: đọc lỗi có cấu trúc

`DiagnosticCollector<JavaFileObject>` cung cấp một danh sách diagnostic. Ta có thể phân loại theo `Diagnostic.Kind`, xem source/line/column và message để người lập trình đọc.

Ví dụ xử lý **bên trong phương thức có biến `diagnostics`**:

```java
for (Diagnostic<? extends JavaFileObject> d
        : diagnostics.getDiagnostics()) {
    if (d.getKind() == Diagnostic.Kind.ERROR) {
        String sourceName = d.getSource() == null
                ? "<unknown>"
                : d.getSource().getName();

        System.out.println(
                sourceName + " line=" + d.getLineNumber());
    }
}
```

`getLineNumber()` có thể trả `Diagnostic.NOPOS` nếu lỗi không gắn với một dòng cụ thể. `getSource()` có thể trả `null`. `getMessage(Locale.ROOT)` là văn bản diễn giải **implementation-dependent**; không nên parse nó bằng một regex cố định để quyết định loại lỗi.

Chẳng hạn, nếu source có `int count = "x";`, `task.call()` thường trả `false`, và collector sẽ có diagnostic kind `ERROR`. Khi muốn thống kê kết quả của công cụ, dùng kind/error count và build status; không dựa vào chuỗi `"incompatible types"` của JDK.

Có diagnostic listener không bảo đảm mọi output của compiler đều xuất hiện dưới dạng `Diagnostic`. Một số thông điệp không khớp đối tượng diagnostic có thể đi qua output writer. Vì vậy công cụ thật cũng cần quản lý writer/log phù hợp; nhưng **dữ liệu có cấu trúc** vẫn là đường chính cho editor hoặc automation.

## 12. Ví dụ kiểm tra lỗi compile bằng API

Lưu `CompileFailureDemo.java`:

```java
import java.io.IOException;
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
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public class CompileFailureDemo {
    public static void main(String[] args) throws IOException {
        Path src = Path.of("failure-demo/Bad.java");
        Path out = Path.of("failure-demo/classes");
        Files.createDirectories(src.getParent());
        Files.createDirectories(out);
        Files.writeString(
                src,
                "public class Bad { int count = \"wrong\"; }\n",
                StandardCharsets.UTF_8);

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler required");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        boolean ok;
        try (StandardJavaFileManager fm =
                     compiler.getStandardFileManager(
                             diagnostics, Locale.ROOT,
                             StandardCharsets.UTF_8)) {
            fm.setLocationFromPaths(
                    StandardLocation.CLASS_OUTPUT,
                    List.of(out));
            Iterable<? extends JavaFileObject> sourceFiles =
                    fm.getJavaFileObjectsFromPaths(List.of(src));
            ok = Boolean.TRUE.equals(
                    compiler.getTask(
                            null, fm, diagnostics,
                            List.of("--release", "17", "-proc:none"),
                            null, sourceFiles
                    ).call());
        }

        boolean hasError = diagnostics.getDiagnostics().stream()
                .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR);

        System.out.println("success=" + ok);
        System.out.println("hasError=" + hasError);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 CompileFailureDemo.java
java CompileFailureDemo
```

Stdout dự kiến:

```text
success=false
hasError=true
```

Chương trình điều khiển compiler **biên dịch thành công**; bên trong nó, compiler được yêu cầu biên dịch một source cố tình không hợp lệ. Vì diagnostic được thu thập thay vì in nguyên văn, ví dụ có thể kiểm thử theo hai boolean ổn định mà không phụ thuộc cách `javac` format lỗi ở từng phiên bản.

Đừng nhầm `java CompileFailureDemo` trả mã thoát của chương trình điều khiển với kết quả biên dịch của `Bad.java`. Trong ví dụ này, Java program không tự gọi `System.exit(1)` khi `ok == false`; nếu muốn CI thất bại, chương trình điều khiển phải tự quyết định mã thoát dựa trên `ok`.

## 13. Quản lý tài nguyên: close, flush và tái sử dụng

`StandardJavaFileManager` kế thừa `Closeable`, nên nên sử dụng:

```java
try (StandardJavaFileManager fm =
             compiler.getStandardFileManager(
                     diagnostics, Locale.ROOT,
                     StandardCharsets.UTF_8)) {
    // Cấu hình location, tạo JavaFileObject và compile.
}
```

Đóng file manager giúp nhả các handle tới file/JAR và các tài nguyên nội bộ. Tài liệu `JavaCompiler` cũng cho phép **dùng lại cùng standard file manager cho nhiều sequential compilation tasks**, giúp tận dụng caching của JAR/file metadata. Tuy nhiên:

- Đừng dùng **cùng một CompilationTask** để chạy nhiều lần.
- Nếu dùng cùng manager cho nhiều task, cần kiểm soát lại `CLASS_OUTPUT`, `CLASS_PATH`, `SOURCE_PATH` trước từng task để tránh state còn sót.
- File manager không nên bị chia sẻ đồng thời giữa nhiều thread/compilation tasks nếu không có hợp đồng thread-safety cụ thể của implementation.
- Không dùng lại một `JavaFileObject` sau khi các file underlying đã bị xóa/di chuyển và coi nó luôn còn hợp lệ.
- Với build nhiều người dùng/đa tenant, kiểm soát nơi đọc và ghi; không cho path đầu vào tùy ý ghi đè file quan trọng.

`flush()` dùng để làm sạch buffer theo contract của file manager khi cần; `close()` kết thúc vòng đời quản lý tài nguyên. Dù file manager chuẩn có cơ chế hoạt động đặc biệt khi được truy cập sau close theo đặc tả, một thiết kế rõ ràng vẫn nên đóng một lần và lấy manager mới khi bắt đầu một lifecycle mới.

## 14. Phân biệt file nguồn, output, sourcepath và annotation processor

Trong một compiler task, không nên nhầm các đường dẫn:

```text
src/app/demo/Main.java         --> compilation unit tường minh
src/lib/...                    --> SOURCE_PATH nếu tìm source phụ thuộc
lib/dependency.jar             --> CLASS_PATH nếu tìm class phụ thuộc
generated-sources/...          --> SOURCE_OUTPUT cho generated .java
build/classes/...              --> CLASS_OUTPUT cho .class
processor jars                 --> ANNOTATION_PROCESSOR_PATH
```

Nếu một file Java được compiler đọc **ngầm** qua source path, nó có thể ảnh hưởng tập class được sinh; cờ `-implicit:class`/`-implicit:none` của `javac` có ý nghĩa riêng với việc sinh `.class` từ source ngầm.

Nếu annotation processing được bật, processor có thể tạo source qua `Filer` và các file ấy được compiler xử lý ở các vòng sau. `SOURCE_OUTPUT` thường tương ứng nơi file sinh ra; `CLASS_OUTPUT` dành cho class file. Khi tập trung vào việc học `StandardJavaFileManager` cơ bản, `-proc:none` giúp ví dụ không phụ thuộc processor tình cờ có trên classpath.

Với JDK 23 trở đi, việc kích hoạt annotation processing đã thay đổi so với một số bản JDK cũ. Nếu ứng dụng cần processor, phải cấu hình rõ processor path/module path, processor và options theo đúng JDK; đừng dựa vào auto-discovery mặc định.

## 15. FileManager và JPMS: khi source thuộc named module

Các ví dụ ở trên biên dịch source **không có `module-info.java`** (classpath/unnamed module). Với dự án dùng JPMS, file manager cũng hỗ trợ các location như:

- `StandardLocation.MODULE_PATH`: các named modules/JAR trên module path.
- `StandardLocation.MODULE_SOURCE_PATH`: vị trí source của modules.
- `StandardLocation.MODULE_CLASS_OUTPUT` (nếu được compiler implementation hỗ trợ ở các ngữ cảnh tương ứng) và các module-oriented locations mà `JavaFileManager` công bố.
- `setLocationForModule(...)` trong các tình huống cần gắn một module name với location riêng.

Không nên tự suy rằng các tùy chọn/classpath thuần túy sẽ áp dụng nguyên xi khi có `module-info.java`. Khả năng đọc module, exports và vị trí output module có quy tắc riêng.

Khi làm việc với nhiều module, có thể đơn giản hơn nếu để build tool quản lý module source path/graph hoặc dùng compiler options `--module-source-path`, `--module-path`, `--module` thay vì tự xây một hệ thống ánh xạ location. Nếu cần viết tooling chuyên biệt, hãy đọc kỹ contract của `StandardJavaFileManager` và `JavaFileManager` trên **đúng JDK**.

## 16. Các lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| `ToolProvider.getSystemJavaCompiler() == null` | Runtime không có system compiler | Chạy bằng JDK có module/compiler thích hợp |
| `IllegalArgumentException` khi lấy compilation units | Truyền directory hoặc loại file object không phù hợp | Đưa danh sách file `.java` cụ thể |
| `IOException` khi đặt `CLASS_OUTPUT` | Output directory chưa tồn tại hoặc không sử dụng được | `Files.createDirectories(out)` và kiểm tra quyền |
| Biên dịch thành công nhưng không thấy class | Đang kiểm tra sai folder/package hoặc file class cũ gây nhầm | Đọc `CLASS_OUTPUT` thực tế, kiểm tra output sạch |
| `package ... does not exist` | CLASS_PATH/SOURCE_PATH không có dependency | Cấu hình classpath/sourcepath đúng root package |
| `cannot find symbol` với type phụ thuộc | Source hoặc class không thể tra cứu | Kiểm tra source file, type name, package, classpath |
| `UnsupportedClassVersionError` lúc chạy | Runtime JVM quá cũ so với class file | Đặt `--release`/toolchain đúng target |
| Chuỗi tiếng Việt lỗi hoặc compiler báo ký tự lạ | Charset ghi source khác charset đọc source | Dùng UTF-8 nhất quán ở cả hai đầu |
| Warning/error không in lên console | DiagnosticCollector đang nhận diagnostic | Đọc `getDiagnostics()` thay vì chỉ xem stderr |
| `getTask(...)` chưa sinh file | Chưa gọi `CompilationTask.call()` | Thực thi task và đọc kết quả |
| File JAR không thể xóa trên Windows | File manager còn giữ handle | Đóng manager bằng try-with-resources |
| `class file for X not found` dù X có ở dependency khác | Classpath đang thiếu dependency gián tiếp | Kiểm tra đầy đủ classpath/task |
| Compile pass nhưng launcher báo `NoClassDefFoundError` | Runtime classpath thiếu class | Khai báo đủ output/dependency khi `java -cp` |
| Kết quả khác nhau giữa máy/CI | JDK, classpath, charset hoặc output cũ khác nhau | Ghi rõ options, JDK và build trong output sạch |

Những thông báo lỗi chỉ mang tính minh họa, có thể thay đổi theo compiler và phiên bản. Dựa vào `Diagnostic.Kind`, file/line/column và compilation status khi cần phân tích tự động, chứ không khóa logic vào một câu stderr cố định.

## 17. Những lỗi thiết kế khi xây công cụ biên dịch

**Dùng SystemCompiler mà không xử lý null.** Ứng dụng có thể chạy trên runtime không đóng gói compiler. Thông báo rõ cần JDK hoặc kiểm tra deployment image.

**Lẫn vị trí ghi với nơi tìm.** `CLASS_OUTPUT` không thay `CLASS_PATH`. Khi biên dịch nhiều phase, cần đưa class được tạo ở phase trước vào classpath của phase sau nếu phase sau phụ thuộc chúng.

**Đưa một directory vào getJavaFileObjectsFromPaths.** API nhận source file paths, không có nghĩa compiler sẽ tự quét đệ quy một thư mục.

**Không đóng file manager.** Dễ tích lũy handle với JAR, gây khó khăn trên Windows hay trong service biên dịch liên tục.

**Dựa vào compiler output text.** Thông báo có thể đổi locale và cách trình bày; dùng `DiagnosticCollector` và status nếu cần máy đọc.

**Dùng output shared giữa các lượt biên dịch không kiểm soát.** Artifact cũ làm kết quả kiểm tra tồn tại file thiếu đáng tin. Mỗi lượt build nên có output directory được quản lý, dọn an toàn khi phù hợp.

**Bỏ qua security boundary.** Java Compiler API không phải sandbox cho source không tin cậy. Code được biên dịch có thể chưa chạy ngay trong compiler, nhưng annotation processor/plugin có thể thực thi mã trong quá trình compile; kiểm soát processor path, filesystem access và isolation khi xử lý source đến từ người dùng.

**Cho rằng CLASS_PATH tự tải Maven dependencies.** File manager quản lý vị trí file/JAR đã có; việc download/resolve dependency là trách nhiệm riêng của build tool hoặc ứng dụng.

## 18. Quy trình áp dụng cho công cụ thực tế

1. Xác nhận **JDK** và compiler có sẵn; chọn version nguồn/bytecode bằng `--release` nếu phù hợp.
2. Chọn **source files** chính xác dưới dạng `Path`, và **output directory** riêng; tạo thư mục trước.
3. Chọn encoding nhất quán; dùng `StandardCharsets.UTF_8`.
4. Lấy `JavaCompiler` và `DiagnosticCollector`.
5. Mở `StandardJavaFileManager` qua try-with-resources.
6. Cấu hình `CLASS_OUTPUT`, `CLASS_PATH`, `SOURCE_PATH` hoặc module path nếu nhiệm vụ cần; tránh xung đột với compiler options.
7. Chuyển source paths thành `JavaFileObject` bằng `getJavaFileObjectsFromPaths(Collection)`.
8. Tạo task bằng `getTask(...)`; truyền compiler options thích hợp.
9. Gọi `call()` đúng một lần trên task; lấy boolean build result.
10. Thu thập diagnostic và kiểm tra class files/artefacts trong output sạch.
11. Đóng manager, giữ log/compiler version cho truy nguyên khi thất bại.
12. Nếu cần **chạy** class đã compile, cấu hình launcher/class loader với runtime classpath/module path riêng và không coi “compile pass” là bằng chứng runtime đầy đủ.

## 19. Bài tập tự kiểm tra

**Bài 1.** Một chương trình gọi `getJavaFileObjectsFromPaths(List.of(Path.of("src")))`, trong đó `src` là directory. Liệu compiler tự biên dịch mọi `.java` bên dưới không?

**Đáp án:** Không. API nhận file paths; directory không phải compilation unit hợp lệ. Hãy liệt kê từng file nguồn.

**Bài 2.** `CLASS_OUTPUT` đặt là `build/classes`. Nếu source `package demo; public class A {}`, class file ở đâu?

**Đáp án:** `build/classes/demo/A.class`.

**Bài 3.** File được ghi bằng UTF-8 nhưng file manager được cấu hình đọc ISO-8859-1. Điều gì có thể xảy ra?

**Đáp án:** Ký tự Unicode có thể được giải mã sai và source/chuỗi Java bị hỏng. Cấu hình charset nhất quán.

**Bài 4.** Có `CompilationTask` nhưng không thấy `.class`. Cần kiểm tra đầu tiên điều gì?

**Đáp án:** Đã gọi `task.call()` hay chưa; sau đó xem status, diagnostics và output location.

**Bài 5.** `List.of(sourcePath)` nên được truyền vào overload nào trên Java 17+?

**Đáp án:** `getJavaFileObjectsFromPaths(Collection<? extends Path>)` hoặc dùng `getJavaFileObjects(sourcePath)`; tránh overload nhận `Iterable` đã deprecated.

**Bài 6.** Một lượt compile tạo `build/lib-classes/demo/lib/Utility.class`, lượt sau cần `Utility`. Chỉ đặt `CLASS_OUTPUT` của app có đủ không?

**Đáp án:** Không. Lượt sau phải có `CLASS_PATH` phù hợp hoặc input/sourcepath giải quyết dependency.

**Bài 7.** Vì sao demo `CompileFailureDemo` có thể in `success=false` mà chính lệnh `java CompileFailureDemo` vẫn kết thúc bình thường?

**Đáp án:** Boolean là kết quả **compilation bên trong chương trình**; ứng dụng không gọi `System.exit` với mã lỗi. Hai mức kết quả tách biệt.

**Bài 8.** Cách nào tốt hơn để tự động thống kê lỗi: đếm dòng stderr chứa `error:` hay đếm `Diagnostic.Kind.ERROR`?

**Đáp án:** Dùng Diagnostic API và kết quả task; văn bản stderr không có schema ổn định.

## 20. Tổng kết và tài liệu tham khảo

`StandardJavaFileManager` là cầu nối giữa **tệp nguồn thực** và **Java Compiler API**. Người lập trình cung cấp `Path`/`File`, file manager biểu diễn các compilation units và quản lý vị trí tìm/ghi, `JavaCompiler` tạo task, `call()` thực thi, còn `DiagnosticCollector` cung cấp thông tin lỗi có cấu trúc.

Năm điểm cần nhớ: **(1)** truyền danh sách file nguồn, không truyền thư mục như một compilation unit; **(2)** đặt `CLASS_OUTPUT` tới directory đã tồn tại và phân biệt với `CLASS_PATH`; **(3)** chọn charset rõ ràng; **(4)** đọc status và diagnostic thay vì đoán từ stderr; **(5)** đóng file manager đúng vòng đời. Với những nguyên tắc này, công cụ biên dịch Java sẽ dễ kiểm thử, chẩn đoán và vận hành hơn.

Tài liệu chính thức:

- [Java SE 21 StandardJavaFileManager](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html) — các overload xử lý `Path`/`File`, setLocationFromPaths, class/source locations.
- [Java SE 21 JavaCompiler](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaCompiler.html) — `getTask`, `getStandardFileManager`, diagnostic listener và tái sử dụng manager.
- [Java SE 21 StandardLocation](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/StandardLocation.html) — vai trò các location chuẩn.
- [Java SE 21 DiagnosticCollector](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/DiagnosticCollector.html) — thu thập diagnostic.
- [JDK 21 javac manual](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html) — các option compiler như `--release` và `-proc:none`.

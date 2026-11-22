# Công cụ nhúng Java 9+: phân biệt `java.util.spi.ToolProvider` với `javax.tools.ToolProvider`

## 1. Vấn đề: hai API trùng tên nhưng khác nhiệm vụ

Khi cần sử dụng các công cụ của JDK **ngay trong ứng dụng Java**, thay vì bắt người dùng mở terminal chạy `javac`, `jar` hoặc `javadoc`, ta có thể gọi các API công khai để tìm và thực thi công cụ. Trong Java tồn tại **hai loại `ToolProvider` khác nhau**:

- **`java.util.spi.ToolProvider`** là **interface** thuộc module **`java.base`**, được bổ sung từ **Java 9**. Nó định nghĩa cách tìm **một công cụ theo tên** và gọi công cụ đó theo kiểu **dòng lệnh**: truyền `String... args`, nhận kết quả đầu ra/lỗi và mã thoát `int`. Các tên điển hình là `"javac"`, `"jar"`, `"jlink"`, `"javadoc"` nếu runtime chứa provider tương ứng.
- **`javax.tools.ToolProvider`** là **class** thuộc module **`java.compiler`**, đã có trước Java 9 và **vẫn được hỗ trợ hiện nay**. Nó có các phương thức **static** để lấy **`JavaCompiler`** hoặc **`DocumentationTool`** của hệ thống, từ đó sử dụng API biên dịch/tạo tài liệu chuyên biệt như `getTask(...)`, `JavaFileManager`, `JavaFileObject` và `DiagnosticListener`.

**Đề bài quan trọng:** khi thấy `ToolProvider`, **luôn nhìn đủ package**. Tên trùng nhau không có nghĩa chung kiểu dữ liệu hoặc hoán đổi phương thức.

~~~java
// API Java 9+ cho công cụ được đăng ký theo tên:
java.util.spi.ToolProvider.findFirst("javac");

// API Java Compiler cho trình biên dịch của hệ thống:
javax.tools.ToolProvider.getSystemJavaCompiler();
~~~

Hai lời gọi trên có thể cùng dẫn đến khả năng biên dịch Java do module `jdk.compiler` cung cấp, nhưng **đối tượng nhận được, mức điều khiển và cách xử lý kết quả là khác nhau**.

## 2. Bảng phân biệt cốt lõi

| Tiêu chí | `java.util.spi.ToolProvider` | `javax.tools.ToolProvider` |
|---|---|---|
| Loại khai báo | **Interface**; provider triển khai `name()` và `run(...)`. | **Class** tiện ích có các factory method static. |
| Có từ | **Java 9**; tiếp tục được hỗ trợ. | **Java 6**; tiếp tục được hỗ trợ. |
| Module/package | `java.base` / `java.util.spi`. | `java.compiler` / `javax.tools`. |
| Mục tiêu | Gọi **các công cụ được đăng ký theo tên**, thường tương đương lệnh trong terminal. | Lấy API chuyên dụng của **compiler** và **documentation tool**. |
| Tìm công cụ | `ToolProvider.findFirst("javac")` trả `Optional<ToolProvider>`; provider có thể không tồn tại. | `ToolProvider.getSystemJavaCompiler()` trả `JavaCompiler` hoặc `null` khi không có compiler. |
| Nhận diện | `provider.name()`; có thể hỏi `description()` trên JDK 19+. | Lấy đối tượng có kiểu `JavaCompiler` hoặc `DocumentationTool` và dùng các phương thức của interface tương ứng. |
| Gọi kiểu dòng lệnh | `provider.run(PrintWriter out, PrintWriter err, String... args)` hoặc bản nhận `PrintStream`; trả `int`. | `JavaCompiler` cũng triển khai `javax.tools.Tool.run(InputStream, OutputStream, OutputStream, String... args)`; ngoài ra có API cấp cao hơn. |
| API chuyên dụng cho mã nguồn | Không trực tiếp có `getTask`, `JavaFileObject` hay diagnostics có cấu trúc. | `compiler.getTask(...)`, `getStandardFileManager(...)`, `DiagnosticCollector` và khả năng cung cấp source từ bộ nhớ. |
| Thông báo thất bại | `Optional.empty()` khi không có provider; `run` trả mã lỗi khác `0` theo quy ước của công cụ. | `null` khi không có system compiler; `CompilationTask.call()` trả `Boolean` cho thành công/thất bại; diagnostics và ngoại lệ khi thích hợp. |
| Phù hợp nhất | Công cụ tổng quát, script-like invocation, thao tác `jar`, `jlink`, `javac` theo tham số lệnh. | Hệ thống phân tích/biên dịch Java, IDE, dynamic compilation, unit test về trình biên dịch, xử lý lỗi ở mức file/dòng/cột. |

**Điểm tinh tế:** không nên nói rằng `javax.tools.ToolProvider` “chạy được compiler nhưng `java.util.spi.ToolProvider` không chạy được” — cả hai đều có thể sử dụng `javac` nếu JDK cung cấp các module cần thiết. Sự khác nhau nằm ở **tầng trừu tượng và API điều khiển**.

## 3. `java.util.spi.ToolProvider`: SPI cho công cụ được đặt tên

### 3.1. Tìm provider bằng tên

~~~java
import java.util.Optional;
import java.util.spi.ToolProvider;

// Đoạn minh họa: đặt trong một phương thức Java.
Optional<ToolProvider> found = ToolProvider.findFirst("javac");

if (found.isPresent()) {
    System.out.println(found.get().name());
} else {
    System.out.println("javac provider unavailable");
}
~~~

- `findFirst(name)` dùng cơ chế service provider (`ServiceLoader`, system class loader) để lấy **provider đầu tiên có `name()` phù hợp**. Nếu không tìm được, kết quả là `Optional.empty()`.
- `"javac"`, `"javadoc"`, `"jar"`, `"jlink"` là **tên công cụ**, không phải fully qualified Java class name. Sự có mặt của từng provider phụ thuộc các module thực tế được đưa vào JDK/runtime image.
- Nếu có nhiều provider trùng tên, `findFirst` chỉ chọn **provider đầu tiên** được tìm thấy. Không dựa vào thứ tự tùy ý giữa nhiều provider để thực hiện tác vụ có yêu cầu xác định nhà cung cấp.
- `findFirst(null)` ném `NullPointerException`. Dùng tên không tồn tại trả `Optional.empty()`, **không phải** `null`.
- Từ Java 19 có `description()` trả `Optional<String>` để hỗ trợ hiển thị danh sách công cụ; mã nhắm Java 17 không nên gọi phương thức mới này.

### 3.2. Chạy như một công cụ dòng lệnh

~~~java
import java.io.PrintWriter;
import java.util.spi.ToolProvider;

// Đoạn minh họa: đặt trong một phương thức Java.
ToolProvider javac = ToolProvider.findFirst("javac")
        .orElseThrow(() -> new IllegalStateException(
                "The javac ToolProvider is not available"));

int exitCode = javac.run(
        new PrintWriter(System.out, true),
        new PrintWriter(System.err, true),
        "-version"
);

if (exitCode != 0) {
    throw new IllegalStateException("javac failed: " + exitCode);
}
~~~

`run(...)` nhận **các đối số của công cụ** như `"-version"`, `"-d"`, tên file nguồn; **không đưa tên chương trình `"javac"` thêm vào đầu mảng đối số**. Ý nghĩa tham số cụ thể được định nghĩa bởi **từng công cụ**.

Theo contract, `0` biểu thị thành công; giá trị khác `0` là lỗi do công cụ định nghĩa. Hai `PrintWriter`/`PrintStream` cho phép tách đầu ra bình thường và thông báo lỗi. Có thể dùng `StringWriter` để thu log.

**API không bắt buộc khởi động một JVM mới**: mục đích của `ToolProvider` là có thể gọi công cụ từ Java. Tuy nhiên, không khẳng định mọi provider đều dùng cùng cơ chế nội bộ hoặc cô lập tài nguyên; `ToolProvider` cũng không phải sandbox cho nguồn mã không tin cậy.

### 3.3. Khả năng mở rộng bởi provider khác

`ToolProvider` là một **SPI**: nhà phát triển thư viện có thể tạo provider triển khai `name()` và `run(PrintWriter, PrintWriter, String...)`, đăng ký qua cơ chế service provider, rồi ứng dụng tiêu thụ tìm bằng `findFirst` hoặc `ServiceLoader`.

Công cụ do JDK cung cấp thường đăng ký qua các module như:

| Công cụ | Module triển khai thường gặp | Chức năng |
|---|---|---|
| `javac` | `jdk.compiler` | Biên dịch nguồn Java. |
| `javadoc` | `jdk.javadoc` | Sinh tài liệu API. |
| `jar` | `jdk.jartool` | Tạo/xem/giải nén JAR. |
| `jlink` | `jdk.jlink` | Đóng gói runtime image từ module. |

Một runtime image được tối giản bằng `jlink` có thể **không chứa** một hoặc nhiều module ở trên. Khi ấy, `findFirst("javac")` có thể không có kết quả dù interface `java.util.spi.ToolProvider` luôn tồn tại trong `java.base`.

## 4. `javax.tools.ToolProvider`: điểm vào Compiler API

`javax.tools.ToolProvider` phục vụ việc lấy các công cụ Java chuyên biệt, chủ yếu:

~~~java
// Đoạn minh họa, không phải chương trình độc lập.
javax.tools.JavaCompiler compiler =
        javax.tools.ToolProvider.getSystemJavaCompiler();

javax.tools.DocumentationTool documentation =
        javax.tools.ToolProvider.getSystemDocumentationTool();
~~~

**Ý nghĩa khi chạy:**

- `getSystemJavaCompiler()` trả hệ thống `JavaCompiler` nếu có; trong JDK tiêu chuẩn, implementation nằm trong module `jdk.compiler`. Nếu module/compiler vắng mặt, phương thức trả **`null`**.
- `getSystemDocumentationTool()` trả `DocumentationTool` (thường do module `jdk.javadoc` cung cấp), hoặc **`null`** nếu không có.
- Tên package là `javax.tools` nhưng **không phải công nghệ Java EE hay một API đã bị loại bỏ**: đây là **Java Compiler API đang được duy trì** trong module `java.compiler`.

Điểm mạnh của `JavaCompiler` là khả năng làm việc với các đối tượng thay vì chỉ chuỗi lệnh:

| API | Lợi ích khi tích hợp compiler |
|---|---|
| `getStandardFileManager(...)` | Tạo trình quản lý file/source/class cho tác vụ biên dịch; trả `StandardJavaFileManager` có thể đóng trong try-with-resources. |
| `getTask(out, fileManager, diagnostics, options, classes, units)` | Tạo `CompilationTask`; `call()` thực hiện biên dịch và trả thành công/thất bại. |
| `JavaFileObject` | Biểu diễn một file nguồn hoặc kết quả biên dịch; có thể cung cấp mã từ bộ nhớ (không bắt buộc phải ghi `.java` ra đĩa). |
| `DiagnosticCollector<JavaFileObject>` | Thu thông báo lỗi/cảnh báo có cấu trúc như loại lỗi, nguồn, dòng và cột. |
| `JavaFileManager` | Cho phép điều khiển nơi compiler đọc nguồn/thư viện và nơi ghi class; hỗ trợ in-memory/virtual filesystem qua custom implementation phù hợp. |
| `DocumentationTool.getTask(...)` | Tạo nhiệm vụ sinh tài liệu với các thành phần/đối số có cấu trúc. |

### 4.1. Mã biên dịch theo API có cấu trúc

~~~java
// Đoạn minh họa: sourcePath, outputDir là Path đã tồn tại.
JavaCompiler compiler = javax.tools.ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException("System compiler unavailable");
}

DiagnosticCollector<JavaFileObject> diagnostics =
        new DiagnosticCollector<>();

try (StandardJavaFileManager fileManager =
             compiler.getStandardFileManager(
                     diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {

    Iterable<? extends JavaFileObject> units =
            fileManager.getJavaFileObjectsFromPaths(
                    java.util.List.of(sourcePath));

    Boolean success = compiler.getTask(
            null,
            fileManager,
            diagnostics,
            java.util.List.of("-d", outputDir.toString()),
            null,
            units
    ).call();

    if (!Boolean.TRUE.equals(success)) {
        for (Diagnostic<? extends JavaFileObject> d :
                diagnostics.getDiagnostics()) {
            System.err.println(d.getKind() + ": line "
                    + d.getLineNumber() + ": " + d.getMessage(Locale.ROOT));
        }
    }
}
~~~

Đoạn minh họa này yêu cầu các `import` tương ứng (`javax.tools.*`, `java.nio.file.Path`, `java.nio.charset.StandardCharsets`, `java.util.Locale`) và hai biến `Path` đã được khởi tạo; **nó không phải chương trình chạy độc lập**. `getJavaFileObjectsFromPaths(List.of(path))` chọn overload nhận `Collection<? extends Path>`, là cách dùng còn được hỗ trợ hiện nay.

Đây là kiểu xử lý hợp lý khi ứng dụng cần hiển thị lỗi compile chính xác cho người dùng, lưu diagnostics, tích hợp IDE hoặc vận hành compiler nhiều lần. `java.util.spi.ToolProvider.run` có thể thu log văn bản, nhưng không trực tiếp cung cấp các `Diagnostic` object.

## 5. Cùng biên dịch một file bằng hai API: chương trình Java 17+ đầy đủ

Ví dụ sau **không phụ thuộc thư viện ngoài**, chỉ yêu cầu một JDK có `jdk.compiler`. Chương trình tạo một thư mục tạm, viết file `Tiny.java`, biên dịch hai lần: một lần qua **SPI dòng lệnh**, một lần qua **Compiler API có cấu trúc**. Mỗi lần có thư mục kết quả riêng để dễ so sánh và toàn bộ file tạm được dọn sau khi chạy.

Tạo file **`ToolProviderContrast.java`**:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;

public class ToolProviderContrast {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("jdk-tool-provider-");
        try {
            Path source = root.resolve("Tiny.java");
            Path spiOutput = Files.createDirectory(root.resolve("spi"));
            Path apiOutput = Files.createDirectory(root.resolve("api"));

            Files.writeString(source,
                    "public class Tiny {"
                    + " public static int answer() { return 42; }"
                    + " }",
                    StandardCharsets.UTF_8);

            // A. java.util.spi.ToolProvider: tìm công cụ theo tên và
            // truyền tham số như khi gọi javac trong terminal.
            java.util.spi.ToolProvider tool =
                    java.util.spi.ToolProvider.findFirst("javac")
                            .orElseThrow(() -> new IllegalStateException(
                                    "javac tool provider unavailable"));

            StringWriter toolLog = new StringWriter();
            int exitCode = tool.run(
                    new PrintWriter(toolLog, true),
                    new PrintWriter(toolLog, true),
                    "-encoding", "UTF-8",
                    "-d", spiOutput.toString(),
                    source.toString());

            if (exitCode != 0) {
                throw new IllegalStateException(
                        "SPI javac failed: " + toolLog);
            }

            // B. javax.tools.ToolProvider: lấy JavaCompiler để tạo task
            // với JavaFileObject và StandardJavaFileManager.
            JavaCompiler compiler =
                    javax.tools.ToolProvider.getSystemJavaCompiler();
            if (compiler == null) {
                throw new IllegalStateException(
                        "System JavaCompiler unavailable");
            }

            boolean success;
            try (StandardJavaFileManager fileManager =
                         compiler.getStandardFileManager(
                                 null, Locale.ROOT, StandardCharsets.UTF_8)) {

                Iterable<? extends JavaFileObject> units =
                        fileManager.getJavaFileObjectsFromPaths(
                                List.of(source));

                success = Boolean.TRUE.equals(
                        compiler.getTask(
                                null,
                                fileManager,
                                null,
                                List.of("-encoding", "UTF-8",
                                        "-d", apiOutput.toString()),
                                null,
                                units
                        ).call());
            }

            System.out.println("SPI tool name: " + tool.name());
            System.out.println("SPI exit code: " + exitCode);
            System.out.println("SPI class exists: "
                    + Files.isRegularFile(
                            spiOutput.resolve("Tiny.class")));
            System.out.println("Compiler API success: " + success);
            System.out.println("API class exists: "
                    + Files.isRegularFile(
                            apiOutput.resolve("Tiny.class")));

        } finally {
            // Chỉ xóa file trong thư mục tạm vừa tạo.
            try (var walk = Files.walk(root)) {
                for (Path path : walk
                        .sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }
}
~~~

Biên dịch và chạy trên **Java 17+** từ thư mục chứa file trên:

~~~bash
javac ToolProviderContrast.java
java ToolProviderContrast
~~~

**Stdout đã kiểm chứng với OpenJDK 24 (full JDK):**

~~~text
SPI tool name: javac
SPI exit code: 0
SPI class exists: true
Compiler API success: true
API class exists: true
~~~

**Giải thích chính xác từng bước:**

1. `findFirst("javac")` lấy một **provider** có `name() == "javac"`. `run(...)` được cấp các đối số `-encoding`, `-d` và đường dẫn file, hệt kiểu gọi `javac` từ command line. Giá trị `0` là mã thoát báo thành công.
2. `getSystemJavaCompiler()` trả một **`JavaCompiler`**, rồi `getTask(...)` nhận `JavaFileObject` và `StandardJavaFileManager`, `call()` cho biết tác vụ biên dịch có thành công hay không.
3. Cả hai tạo `Tiny.class` ở **hai thư mục khác nhau**. Chúng cùng giải quyết bài toán compile, nhưng khác interface và mức cấu hình. `ToolProviderContrast` chỉ chứng minh việc compile file nhỏ trong JDK thử nghiệm; không chứng minh mọi provider tên `"javac"` trên mọi runtime có triển khai giống nhau.
4. Ví dụ có `try-with-resources` để đóng file manager và `Files.walk` để xóa thư mục tạm theo thứ tự từ file con lên cha. Nó không tạo file nguồn trong repository hiện tại.
5. Nếu chạy trên runtime image **không có `jdk.compiler`**, `findFirst("javac")` có thể không trả provider hoặc `getSystemJavaCompiler()` có thể trả `null`; ứng dụng phải giải quyết yêu cầu về module/runtime.

**Điều quan trọng về output:** chương trình không in nội dung `Tiny.java` hoặc bytecode; hai dòng `class exists: true` là phép kiểm tra file kết quả thực tế. Trường hợp compiler báo lỗi, SPI dùng exit code và log; Compiler API có thể bổ sung `DiagnosticCollector` để hiển thị lỗi có cấu trúc.

## 6. Vì sao `javax.tools.ToolProvider` vẫn cần thiết khi đã có SPI mới?

Cả hai API vẫn hữu ích và **không thay thế nhau hoàn toàn**:

**Trường hợp cần một lệnh công cụ:** một ứng dụng build/packaging có thể muốn tạo JAR hoặc runtime image. `java.util.spi.ToolProvider.findFirst("jar")` hoặc `findFirst("jlink")` cho phép gọi provider bằng tên và các tùy chọn dòng lệnh. `javax.tools.ToolProvider` không cung cấp factory có tên `getSystemJarTool()` hay `getSystemJlinkTool()`.

~~~java
// Mã minh họa: cần một provider "jar" trong runtime.
java.util.spi.ToolProvider jarTool =
        java.util.spi.ToolProvider.findFirst("jar")
                .orElseThrow(() -> new IllegalStateException(
                        "jar tool unavailable"));

// Các tham số thực tế của jar tùy tác vụ.
// int exit = jarTool.run(outWriter, errWriter, "--create", "--file", ...);
~~~

**Trường hợp cần compiler tích hợp sâu:** một IDE, dịch vụ build, trình soạn thảo online hoặc framework cần compile nguồn trong bộ nhớ, bắt lỗi theo số dòng/cột, cấu hình annotation processing, file manager, class output, classpath, compiler options. `JavaCompiler.getTask(...)` và `javax.tools.DiagnosticCollector` thích hợp hơn một chuỗi log từ lệnh `javac`.

**Trường hợp chỉ muốn biên dịch file như command line:** cả `ToolProvider.findFirst("javac")` và `JavaCompiler.run(...)` có thể đáp ứng. Chọn theo mức điều khiển và loại output/error mà ứng dụng cần, không khẳng định chỉ một trong hai có thể thực thi compiler.

## 7. Module Java, khả năng tìm provider và các phiên bản JDK

Các API liên quan nằm ở các module khác nhau:

~~~text
java.base
  java.util.spi.ToolProvider       // API gọi công cụ qua tên, Java 9+

java.compiler
  javax.tools.ToolProvider         // factory getSystemJavaCompiler()
  javax.tools.JavaCompiler         // CompilationTask, diagnostics
  javax.tools.JavaFileObject
  javax.tools.JavaFileManager

jdk.compiler
  triển khai hệ thống javac        // cần có trong JDK/runtime image

jdk.javadoc
  triển khai hệ thống javadoc

jdk.jartool
  provider jar

jdk.jlink
  provider jlink
~~~

Với một ứng dụng **Java module** dùng `JavaCompiler`, khai báo tối thiểu API dependency:

~~~java
// module-info.java, đoạn minh họa:
module com.example.build {
    requires java.compiler;
}
~~~

`java.base` luôn là dependency ngầm. Nhưng `requires java.compiler` **chỉ bảo đảm đọc được các interface của Compiler API**, **không tự bảo đảm runtime image chứa implementation `jdk.compiler`**. Nếu module ứng dụng bắt buộc cần compiler của JDK, phải đóng gói/chạy trong runtime có module `jdk.compiler`; trong môi trường module được kiểm soát chặt có thể thêm `requires jdk.compiler;` để thể hiện phụ thuộc implementation JDK (đổi lại giảm tính độc lập với các runtime không có module đó).

Khi dùng `jlink` để tạo runtime image tối giản, **kiểm tra module có mặt**; nếu ứng dụng cần `javac` mà image không chứa `jdk.compiler` thì cả cơ chế tìm provider và gọi system compiler đều có thể không khả dụng. Mã mới nên xử lý vắng mặt bằng `Optional.empty()` hoặc `null` rõ ràng, thay vì gọi `get()` hoặc `getTask()` ngay.

Việc API có mặt trên JDK 17, 21, 24, 26... không có nghĩa mọi công cụ CLI đều được đăng ký trong một runtime tùy biến. `ToolProvider` là API chung, còn từng provider phụ thuộc module cài đặt.

## 8. Những khác biệt về thông báo lỗi và tài nguyên

### 8.1. Đầu ra dạng text so với diagnostics có cấu trúc

Khi gọi `java.util.spi.ToolProvider.run(...)`, dữ liệu trả ra thường là hai luồng text (`out`, `err`) và mã trạng thái `int`. Nếu cần hiển thị một lỗi compile, ứng dụng có thể lưu log, nhưng không nên tự giả định thông báo của mọi phiên bản compiler sẽ có cùng định dạng.

Với `JavaCompiler`, sử dụng `DiagnosticCollector<JavaFileObject>`. Một `Diagnostic` có thể cung cấp `getKind()`, `getSource()`, `getLineNumber()`, `getColumnNumber()` và `getMessage(locale)` — thuận tiện cho IDE để đánh dấu vị trí lỗi. Kết quả compile qua `getTask(...).call()` là `Boolean`; kiểm tra `Boolean.TRUE.equals(...)` để xử lý an toàn.

### 8.2. Classpath, file manager và in-memory compilation

`ToolProvider.run(...)` thường nhận tùy chọn như `-classpath` hoặc `--class-path` dưới dạng **chuỗi**, giống syntax dòng lệnh. Ngược lại, `JavaCompiler` cho phép làm việc trực tiếp với `JavaFileObject` và file manager — thuận tiện cho source được sinh động, môi trường ảo hoặc bộ nhớ.

Lưu ý: một số tính năng của shell/launcher **không được giả định** có trong lời gọi embedded. Ví dụ:

- Không đưa tùy chọn VM `-J...` vào công cụ `javac` như thể đang gọi binary launcher; khi nhúng vào cùng JVM, các JVM options phải áp dụng cho **JVM đang chạy ứng dụng**.
- Không mặc định shell sẽ mở rộng glob như `lib/*` bên trong chuỗi tham số; hãy xác định classpath rõ ràng hoặc xử lý bằng `JavaFileManager`.
- Dùng `--release` khi biên dịch nhắm API của một phiên bản Java đã định thay vì chỉ đặt `-source`/`-target` mà không kiểm soát thư viện nền.
- Đóng `StandardJavaFileManager` khi xong và quản lý bộ nhớ, nguồn code, annotation processor, đường dẫn output và quyền file đúng yêu cầu ứng dụng.

### 8.3. Bảo mật và quản lý thực thi

Nhúng công cụ không làm mã nguồn được xử lý trở nên an toàn. Compiler có thể chạy **annotation processor**, đọc file/classpath và tiêu thụ CPU/RAM; plugin, compiler extension hoặc provider bên thứ ba có thể chạy mã trong JVM. Nếu nhận source không tin cậy từ người dùng, phải xem xét cô lập cấp tiến trình/môi trường, hạn chế tài nguyên và kiểm soát dependency/processor. `ToolProvider` và `JavaCompiler` **không phải sandbox**.

Không cần khởi tạo một tiến trình Java mới cho mỗi tác vụ chỉ để sử dụng API, nhưng nếu cần mức cô lập mạnh hoặc timeout ngoài JVM, ứng dụng có thể chọn kiến trúc worker process riêng. Đây là quyết định vận hành, không thay đổi bản chất hai API.

## 9. Những lỗi phổ biến cần tránh

**Lỗi 1 — Import nhầm class:**

~~~java
import javax.tools.ToolProvider;

// Sai vì class này KHÔNG có phương thức findFirst:
// ToolProvider.findFirst("javac");

// Đúng với kiểu đang import:
javax.tools.JavaCompiler compiler =
        ToolProvider.getSystemJavaCompiler();
~~~

Ngược lại, nếu import `java.util.spi.ToolProvider` rồi gọi `getSystemJavaCompiler()` thì code không biên dịch. Khi cần dùng cả hai trong cùng file, cách rõ ràng nhất là **viết đầy đủ package** như ví dụ `ToolProviderContrast.java`.

**Lỗi 2 — Nghĩ `findFirst("javac")` luôn thành công.** Khi image thiếu `jdk.compiler` hoặc không có provider phù hợp, kết quả có thể là `Optional.empty()`. Kiểm tra kết quả trước khi `run`.

**Lỗi 3 — Nghĩ `getSystemJavaCompiler()` không bao giờ là `null`.** Phương thức có thể trả `null` khi không có system compiler; điều này thường gặp trong một runtime image không chứa module compiler.

**Lỗi 4 — Đánh đồng `0` của SPI với `true` của task.** `run` trả `int` mã lỗi; `CompilationTask.call()` trả `Boolean`. Không chuyển `int` thành boolean theo kiểu “nonzero là true” như ở một số ngôn ngữ khác.

**Lỗi 5 — Cho rằng `javax.tools.ToolProvider` không thể chạy compiler như công cụ.** `JavaCompiler` kế thừa `javax.tools.Tool`, có `run(...)` cho thực thi theo kiểu lệnh. Điểm mạnh chính của `javax.tools` là API **chi tiết hơn** như `getTask`, không phải chỉ có một phương thức duy nhất.

**Lỗi 6 — Dùng `ToolProvider.run` rồi cố gọi `getTask()` trên provider.** `java.util.spi.ToolProvider` không định nghĩa `getTask()`. Hãy lấy `JavaCompiler` qua `javax.tools.ToolProvider` nếu cần tasks và diagnostics.

**Lỗi 7 — Ghép chuỗi một câu lệnh dài và truyền làm một tham số.** `run(..., String... args)` nhận **mỗi đối số là một phần tử riêng**, ví dụ `"-d", outDir, sourceFile`; không truyền `"javac -d out Tiny.java"` thành một string và mong API tách lệnh như shell.

**Lỗi 8 — Chỉ nhận thành công dựa vào log trống.** Với `ToolProvider.run`, dùng mã thoát; với `JavaCompiler`, dùng `call()` và xem diagnostics. Log trống không đủ chứng minh biên dịch đã tạo kết quả đúng.

**Lỗi 9 — Cho rằng hai API bảo đảm không có side effects.** Compile/packaging có thể ghi file, đọc classpath và chạy code của plugin/annotation processor. Chọn thư mục output tường minh, kiểm soát nguồn và dọn tài nguyên.

**Lỗi 10 — Viết code mới dựa vào đường dẫn nội bộ của trình biên dịch.** Để tích hợp ổn định với JDK hiện hành, ưu tiên **`java.util.spi.ToolProvider`**, **`javax.tools.JavaCompiler`** và các interface công khai; không dựa vào những lớp implementation không được cam kết như API công khai.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Hai cách sau trả cùng kiểu dữ liệu không?

~~~java
var x = java.util.spi.ToolProvider.findFirst("javac");
var y = javax.tools.ToolProvider.getSystemJavaCompiler();
~~~

**Đáp án:** Không. `x` có kiểu `Optional<java.util.spi.ToolProvider>`, `y` có kiểu `javax.tools.JavaCompiler` (hoặc giá trị `null` khi compiler không có).

**Câu 2.** Cần gọi `jlink` theo các tham số như trong terminal, nên bắt đầu từ API nào?

**Đáp án:** `java.util.spi.ToolProvider.findFirst("jlink")` nếu runtime có provider `jlink`. `javax.tools.ToolProvider` không có `getSystemJlinkTool()`.

**Câu 3.** Cần đánh dấu chính xác dòng/cột có lỗi cú pháp trong IDE, nên dùng API nào?

**Đáp án:** `javax.tools.JavaCompiler.getTask(...)` với `DiagnosticCollector<JavaFileObject>` và `StandardJavaFileManager` hoặc file manager được tùy biến.

**Câu 4.** `ToolProvider.run(...)` trả `1`, nhưng log không có chữ “error”. Tác vụ đã thành công chưa?

**Đáp án:** Không. Quy ước của interface: **mã `0` thành công, mã khác `0` là lỗi** do công cụ báo.

**Câu 5.** Dùng JDK 21 nhưng `ToolProvider.findFirst("javac")` trả rỗng. Có phải Java 21 đã loại bỏ `ToolProvider`?

**Đáp án:** Không. Interface vẫn có từ Java 9 trở đi. Có thể runtime image không chứa module `jdk.compiler` hoặc provider chưa được đưa vào môi trường tìm kiếm.

**Câu 6.** `javax.tools.ToolProvider` có phải một API “legacy” cần loại khỏi code mới vì đã có SPI từ Java 9?

**Đáp án:** Không. `javax.tools.ToolProvider` và `JavaCompiler` vẫn là API công khai, phù hợp cho biên dịch/tạo tài liệu có cấu trúc. API SPI tên trùng giúp gọi công cụ theo kiểu tham số dòng lệnh.

## Tài liệu tham khảo còn áp dụng

- [Java SE 26 — `java.util.spi.ToolProvider`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/spi/ToolProvider.html): interface, `findFirst`, `name`, `run` và kiểu trả về.
- [Java SE 26 — `javax.tools.ToolProvider`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/ToolProvider.html): `getSystemJavaCompiler`, `getSystemDocumentationTool` và các điều kiện có thể trả `null`.
- [Java SE 26 — `javax.tools.JavaCompiler`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/JavaCompiler.html): `getTask`, `getStandardFileManager` và diagnostics.
- [Java SE 26 — `javax.tools.StandardJavaFileManager`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html): làm việc với `Path` và quản lý file nguồn/class.
- [Java SE 26 — module `jdk.compiler`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.compiler/module-summary.html): cung cấp `javac` qua ToolProvider SPI và `JavaCompiler`.
- [Java SE 26 — module `jdk.javadoc`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.javadoc/module-summary.html): cung cấp `javadoc` và `DocumentationTool`.
- [Java SE 26 — `javax.tools.Tool`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/Tool.html): `run(InputStream, OutputStream, OutputStream, String...)`.
- [Java SE 26 — `java.util.ServiceLoader`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html): cơ chế tìm các service providers.
- [Java SE 26 — javac Tool Guide](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html): tùy chọn dòng lệnh, `--release` và giới hạn khi gọi công cụ nhúng.

**Ghi nhớ:** khi cần **tìm một công cụ bằng tên và chạy theo tham số CLI**, dùng `java.util.spi.ToolProvider`; khi cần **điều khiển compiler/documentation task, file manager và diagnostics bằng Java API**, dùng `javax.tools.ToolProvider` để lấy `JavaCompiler` hoặc `DocumentationTool`. Cả hai con đường đều là API hiện hành và phải xử lý đúng tình huống module/provider không có sẵn.

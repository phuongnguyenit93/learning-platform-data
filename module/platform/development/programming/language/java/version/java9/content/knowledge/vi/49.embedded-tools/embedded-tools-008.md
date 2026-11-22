# Thu thập chẩn đoán và đóng tài nguyên của công cụ nhúng trong Java 9+

## 1. Vì sao gọi công cụ ngay trong JVM cần quản lý chẩn đoán và tài nguyên?

Một ứng dụng Java có thể cần **biên dịch source Java, tạo tài liệu Javadoc hoặc chạy một công cụ JDK từ chương trình**. Ví dụ, hệ thống sinh mã tự động kiểm tra source trước khi phát hành; cổng nội bộ tạo tài liệu API từ các module; IDE/CI cần nhận lỗi biên dịch theo vị trí trong source để hiển thị cho người dùng.

Java cung cấp các API chuẩn cho những nhu cầu đó:

- `javax.tools.JavaCompiler` để **biên dịch** nguồn Java ngay trong tiến trình.
- `javax.tools.DocumentationTool` để **chạy công cụ tạo Javadoc** ngay trong tiến trình.
- `javax.tools.DiagnosticListener` / `DiagnosticCollector` để **thu thập lỗi, cảnh báo, ghi chú** thành dữ liệu có cấu trúc.
- `javax.tools.StandardJavaFileManager` / `JavaFileManager` để đọc source, classpath, module path và ghi output; phải quản lý các stream, tệp và tài nguyên liên quan.
- `java.util.spi.ToolProvider` (có từ Java 9) cho cách gọi công cụ kiểu CLI từ chương trình, thu hai luồng text và mã thoát.

Một lời gọi biên dịch có thể mở file source, file JAR, đọc module/classpath, ghi `.class` và tạo diagnostics. Nếu chỉ xem `true/false` mà bỏ qua diagnostics, người dùng khó biết vì sao thất bại. Nếu không đóng file manager hoặc những stream do mình tạo, ứng dụng chạy lâu có thể giữ file handle, cache hoặc tệp tạm lâu hơn cần thiết.

```text
Ứng dụng Java
  │
  ├─ chuẩn bị source + classpath + output
  │
  ├─ JavaCompiler / DocumentationTool
  │     ├─ CompilationTask / DocumentationTask → kết quả true/false
  │     ├─ DiagnosticListener              → ERROR / WARNING / NOTE / vị trí nguồn
  │     └─ JavaFileManager                  → mở file, jar, module, class output
  │
  ├─ đọc diagnostics, tạo báo cáo rõ ràng
  └─ close file manager + streams, xử lý exception và dọn tệp tạm
```

**Phạm vi phiên bản:** Java Compiler API `javax.tools` đã tồn tại trước Java 9; từ Java 9, nó thuộc kiến trúc module qua `java.compiler` và hoạt động cùng hệ JDK module. Giao diện `java.util.spi.ToolProvider` cho gọi công cụ theo tên được bổ sung ở Java 9. Các API này vẫn là cách làm được hỗ trợ trong JDK hiện đại; bài không dựa vào classloader tìm công cụ đã bị đánh dấu deprecated hoặc API nội bộ JDK.

## 2. Phân biệt hai cơ chế gọi công cụ chuẩn

| Đặc điểm | Task API có cấu trúc | ToolProvider kiểu lệnh |
| --- | --- | --- |
| Điểm vào | `JavaCompiler.getTask(...)`, `DocumentationTool.getTask(...)` | `java.util.spi.ToolProvider.findFirst("javac"/"javadoc")` rồi `run(...)` |
| Đầu vào | `JavaFileObject`, `JavaFileManager`, options | Các chuỗi đối số giống CLI |
| Chẩn đoán | `DiagnosticListener` / `DiagnosticCollector`, thông tin vị trí | `PrintWriter`/`PrintStream` cho stdout, stderr dạng văn bản |
| Kết quả | `CompilationTask.call()` hoặc `DocumentationTask.call()` trả `Boolean` | `run(...)` trả `int`, 0 là thành công |
| Quản lý file | Ứng dụng có thể sở hữu `StandardJavaFileManager` và đóng bằng `try-with-resources` | Công cụ quản lý phần nội bộ của lần chạy; ứng dụng quản lý stream và tệp do mình tạo |
| Phù hợp | IDE, CI cần diagnostics có cấu trúc, quản lý source/output, tích hợp tài liệu | Chạy nhanh công cụ JDK bằng tên, giữ tương đồng CLI |

Hai lớp cùng mang tên `ToolProvider` nhưng **khác package và ý nghĩa**:

- `javax.tools.ToolProvider`: static factory `getSystemJavaCompiler()`, `getSystemDocumentationTool()`.
- `java.util.spi.ToolProvider`: interface SPI, có `findFirst(name)` và `run(...)`.

Không import cả hai bằng tên ngắn rồi gọi nhầm. Trong phần CLI sẽ dùng **tên đầy đủ `java.util.spi.ToolProvider`**.

## 3. Các kiểu Diagnostic và điều có thể đọc được

Một `Diagnostic<S extends JavaFileObject>` mô tả một thông điệp từ công cụ. Các thông tin hữu ích:

| Trường/API | Ý nghĩa |
| --- | --- |
| `getKind()` | Mức độ: `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE`, `OTHER`. |
| `getSource()` | Đối tượng nguồn liên quan, **có thể là `null`**. |
| `getLineNumber()`, `getColumnNumber()` | Dòng/cột theo cách công cụ xác định, **có thể không biết vị trí**. |
| `getStartPosition()`, `getEndPosition()`, `getPosition()` | Chỉ số vị trí ký tự được công cụ công bố khi có. |
| `getCode()` | Mã chẩn đoán; **phụ thuộc công cụ/implementation**, không nên hardcode cho mọi JDK. |
| `getMessage(Locale)` | Nội dung đọc được theo locale; cần xử lý như văn bản báo lỗi, không làm khóa kiểm thử lâu dài. |

Khi công cụ không biết vị trí, API trả hằng `Diagnostic.NOPOS` (thường là `-1`). **Không tự khẳng định mọi lỗi luôn có dòng, cột và nguồn**.

Các đối tượng source như `JavaFileObject` có `toUri()` để hiển thị đường dẫn; nhưng `getSource() == null` là tình huống hợp lệ đối với lỗi không gắn nguồn. Khi trình bày đường dẫn trong web/UI, phải cân nhắc che thư mục tuyệt đối, tên tài khoản hoặc cấu trúc nội bộ.

Chẳng hạn, bộ phận giao diện có thể định dạng an toàn:

```java
Diagnostic<? extends JavaFileObject> d = ...;  // Đã có chẩn đoán
String sourceName = d.getSource() == null
        ? "(no source)"
        : d.getSource().getName();
String line = d.getLineNumber() == Diagnostic.NOPOS
        ? "?"
        : Long.toString(d.getLineNumber());
String message = d.getMessage(Locale.ROOT);
```

Đây là **đoạn mã minh họa**, không phải class chạy độc lập; cần `import javax.tools.Diagnostic;`, `JavaFileObject`, `java.util.Locale`. Nếu hiển thị cho người dùng, nên phân biệt cảnh báo với lỗi và escape văn bản khi xuất HTML/JSON.

## 4. `DiagnosticListener` và `DiagnosticCollector` khác nhau thế nào?

`DiagnosticListener<S>` là interface một phương thức:

```java
void report(Diagnostic<? extends S> diagnostic);
```

Công cụ gọi `report` để phát thông báo cho bộ lắng nghe. Bạn có thể dùng lambda để xử lý ngay, ví dụ chuyển event sang logger hay bảng lỗi. Không nên để `report` ném exception bất ngờ hoặc làm công việc chậm/chặn tiến trình khi xử lý hàng nghìn lỗi.

`DiagnosticCollector<S>` là implementation sẵn có của `DiagnosticListener`. Nó giữ diagnostics trong danh sách và cho đọc lại bằng:

```java
DiagnosticCollector<JavaFileObject> diagnostics =
        new DiagnosticCollector<>();
// Truyền diagnostics vào getTask(...) và (khi phù hợp) getStandardFileManager(...).
// Sau khi task chạy:
for (Diagnostic<? extends JavaFileObject> d : diagnostics.getDiagnostics()) {
    System.out.println(d.getKind() + ": " + d.getMessage(Locale.ROOT));
}
```

Đây cũng là **trích đoạn minh họa**, cần import `javax.tools.*` và `java.util.Locale`; không phải chương trình hoàn chỉnh.

**Quy tắc sử dụng:**

1. Tạo **collector mới cho mỗi nhiệm vụ độc lập** nếu muốn báo cáo không lẫn lỗi từ các lần chạy.
2. Truyền collector vào cả `getTask` và `getStandardFileManager` khi muốn nhận cả chẩn đoán của tool và file manager.
3. Thường duyệt `getDiagnostics()` **sau khi `call()` kết thúc**; đừng nhầm collector với một stream log tự động ra console.
4. `Diagnostic.Kind.ERROR` nên đếm riêng; warnings và notes là những nhóm khác.
5. `DiagnosticCollector` giữ các đối tượng trong bộ nhớ; trên hệ thống lớn, cân nhắc giới hạn hoặc xử lý trực tiếp qua `DiagnosticListener` để tránh giữ vô hạn thông điệp.
6. Không giả định mọi lỗi/exception đều trở thành `Diagnostic`. `IOException`, `IllegalArgumentException` hoặc lỗi từ code thành phần có thể được ném trực tiếp; một số chẩn đoán khác vẫn có thể ra kênh `Writer`.

Nếu không chỉ định listener, công cụ sẽ có cơ chế mặc định để định dạng diagnostics. Khi cần dữ liệu có cấu trúc, truyền listener một cách tường minh.

## 5. Quản lý tài nguyên: ai có nghĩa vụ đóng?

`StandardJavaFileManager` kế thừa `JavaFileManager` và `Closeable` / `AutoCloseable`; đây là tài nguyên quan trọng nhất khi nhúng compiler/javadoc.

**Quy tắc chủ sở hữu:** thành phần **tạo/lấy một file manager mà mình quản lý** phải đóng khi hoàn tất; nếu một API nhận manager do bên gọi truyền vào, không mặc định đóng tài nguyên của bên gọi khi vẫn còn nhu cầu sử dụng.

Mẫu đơn giản:

```java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException("JDK compiler not available");
}

DiagnosticCollector<JavaFileObject> diagnostics =
        new DiagnosticCollector<>();

try (StandardJavaFileManager manager =
             compiler.getStandardFileManager(
                     diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
    // Chọn source files, class output, options; gọi getTask(...).call().
}
// StandardJavaFileManager.close() được gọi dù task thành công hay ném exception.
```

Đây là **đoạn mẫu**, cần import `javax.tools.*`, `java.util.Locale`, `java.nio.charset.StandardCharsets`; các biến source và task được tạo trong `try` tùy ứng dụng.

Điểm khác biệt cần ghi nhớ:

- **`JavaCompiler` / `DocumentationTool`** là đối tượng công cụ, **không phải `AutoCloseable`**. Không gọi `compiler.close()`.
- `CompilationTask` / `DocumentationTask` không phải stream để đóng. Gọi `call()` để thực thi; mỗi task được tạo để thực thi theo vòng đời một lần.
- `StandardJavaFileManager.close()` giải phóng các tài nguyên nó mở trực tiếp hoặc gián tiếp, gồm các file/archive handles có liên quan. `flush()` chỉ đẩy các output đang chờ, **không tương đương close**.
- `try-with-resources` đảm bảo gọi `close()` cả khi lỗi; exception từ `close` có thể là suppressed exception khi một exception khác đã xảy ra trong khối.
- `DiagnosticCollector` chỉ chứa dữ liệu đã ghi nhận, không có lệnh `close()`; nếu lưu collector trong cache/static collection sẽ kéo dài thời gian tồn tại của diagnostics và tham chiếu tới source.
- Nếu **ứng dụng tự mở** một `InputStream`, `OutputStream`, `Reader` hoặc `Writer` chứa file/zip, chính ứng dụng cần đóng chúng. Đừng nghĩ đóng file manager tự động đóng mọi stream **tự tạo bên ngoài**.
- `FileManager` chuẩn có hỗ trợ việc mở lại trong một số tình huống theo hợp đồng API, nhưng với công việc chia phạm vi rõ ràng, mô hình dễ kiểm soát nhất vẫn là **manager sống trong một `try`**, kết thúc task rồi đóng.
- Các tệp đầu ra `.class` hoặc thư mục Javadoc **không tự bị xóa** bởi `close()`; cần quy trình thu hồi/dọn tệp riêng nếu chúng chỉ là tệp tạm.

Một hệ thống server thường cần cả **giới hạn bộ nhớ/disk**, tránh biên dịch hàng trăm nguồn khổng lồ đồng thời, giới hạn thời gian xử lý ở tầng thực thi và kiểm soát tệp tạm trên ổ đĩa.

## 6. Ví dụ Java 17+ hoàn chỉnh: biên dịch lỗi, thu diagnostics, tạo Javadoc và đóng tài nguyên

Chương trình bên dưới thể hiện trọn vòng đời **công cụ nhúng**:

1. Lấy compiler và Javadoc tool từ JDK.
2. Tạo source Java **có lỗi cú pháp**; biên dịch và thu một lỗi bằng `DiagnosticCollector`.
3. Sửa source; biên dịch lần nữa với collector mới.
4. Tạo Javadoc HTML từ source hợp lệ bằng `DocumentationTool`, dùng file manager riêng.
5. Dùng `try-with-resources` đóng từng `StandardJavaFileManager`, rồi xóa thư mục làm việc tạm ngay cả khi xảy ra lỗi.

Không cần database, network, dependency bên ngoài, hay nguồn file người dùng. JDK 17+ có các module tool là đủ.

Lưu dưới tên **`EmbeddedToolsDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.stream.Stream;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.DocumentationTool;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public class EmbeddedToolsDemo {
    private static final String INVALID = """
            /** Example type. */
            public class Example {
                /** Returns an answer. @return answer */
                public int answer() { return ; }
            }
            """;
    private static final String VALID = INVALID.replace(
            "return ;", "return 42;");

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        DocumentationTool docs = ToolProvider.getSystemDocumentationTool();
        if (compiler == null || docs == null) {
            throw new IllegalStateException("Full JDK tools are required");
        }

        Path root = Files.createTempDirectory("embedded-tools-");
        try {
            Path source = root.resolve("Example.java");
            Path classes = Files.createDirectory(root.resolve("classes"));
            Path site = root.resolve("docs");

            Files.writeString(source, INVALID, StandardCharsets.UTF_8);
            compile(compiler, source, classes, "invalid");

            Files.writeString(source, VALID, StandardCharsets.UTF_8);
            compile(compiler, source, classes, "valid");

            DiagnosticCollector<JavaFileObject> docDiagnostics =
                    new DiagnosticCollector<>();
            try (StandardJavaFileManager manager =
                         docs.getStandardFileManager(
                                 docDiagnostics, Locale.ROOT,
                                 StandardCharsets.UTF_8)) {
                var sources = manager.getJavaFileObjectsFromPaths(
                        List.of(source));
                boolean ok = docs.getTask(
                        null, manager, docDiagnostics, null,
                        List.of("-quiet", "-d", site.toString()),
                        sources).call();
                System.out.println("javadoc successful: " + ok);
                System.out.println("javadoc index exists: " +
                        Files.exists(site.resolve("index.html")));
            }
        } finally {
            try (Stream<Path> paths = Files.walk(root)) {
                for (Path path : paths.sorted(Comparator.reverseOrder())
                                      .toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }

    private static void compile(
            JavaCompiler compiler, Path source, Path classes, String label)
            throws IOException {
        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();
        try (StandardJavaFileManager manager =
                     compiler.getStandardFileManager(
                             diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
            manager.setLocationFromPaths(
                    StandardLocation.CLASS_OUTPUT, List.of(classes));
            var sources = manager.getJavaFileObjectsFromPaths(
                    List.of(source));
            boolean ok = Boolean.TRUE.equals(
                    compiler.getTask(null, manager, diagnostics,
                            List.of("--release", "17"), null, sources).call());
            long errors = diagnostics.getDiagnostics().stream()
                    .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
                    .count();
            System.out.println(label + " successful: " + ok);
            System.out.println(label + " errors: " + errors);
        }
    }
}
```

Tại thư mục trống chứa file Java:

```bash
javac --release 17 -encoding UTF-8 EmbeddedToolsDemo.java
java EmbeddedToolsDemo
```

**Stdout chính xác đã kiểm thử bằng OpenJDK 24**:

```text
invalid successful: false
invalid errors: 1
valid successful: true
valid errors: 0
javadoc successful: true
javadoc index exists: true
```

Đầu ra trên phiên bản compiler khác có thể khác về số lượng hoặc cách diễn đạt một số diagnostics; ví dụ được thiết kế để có một lỗi rõ ràng trên JDK thử nghiệm. Với ứng dụng thật, kiểm thử thông qua `Kind`, vị trí và kết quả task thay vì cố định câu chữ lỗi compiler.

### Vì sao ví dụ chạy được mà không cần build tool?

- `getSystemJavaCompiler()` và `getSystemDocumentationTool()` lấy công cụ từ các module JDK hiện diện. Nếu chỉ chạy trên runtime đã rút gọn và bỏ `jdk.compiler` hoặc `jdk.javadoc`, chúng có thể trả `null`. Mã kiểm tra trước khi dùng.
- `Files.writeString` tạo một source file mới trong thư mục tạm. Có hai phiên bản: `INVALID` có `return ;` trong method trả `int` nên biên dịch thất bại; `VALID` thay bằng `return 42;`.
- Mỗi lần gọi helper `compile` có **collector mới, file manager mới**, nên số lỗi của lần thứ hai không bị trộn với lần thứ nhất.
- `manager.getJavaFileObjectsFromPaths(...)` chuyển `Path` thành `JavaFileObject` dùng cho `getTask`.
- `manager.setLocationFromPaths(StandardLocation.CLASS_OUTPUT, ...)` điều khiển output `.class`, không phụ thuộc thư mục làm việc.
- `--release 17` yêu cầu code được biên dịch theo API và ngôn ngữ Java 17. **Chỉ đặt `--release` khi JDK tool đang chạy hỗ trợ giá trị đó.**
- `DocumentationTool.getTask(out, fileManager, diagnosticListener, docletClass, options, compilationUnits)` được gọi với `docletClass=null` nên sử dụng Standard Doclet. `-quiet` giảm một số output và `-d` chỉ đường thư mục tài liệu HTML.
- `Files.exists(site.resolve("index.html"))` chỉ là phép kiểm tra output tối thiểu. Trong CI nên kiểm tra số trang, liên kết và nội dung đáng mong đợi nếu cần bảo đảm tài liệu thực sự hoàn chỉnh.
- Khối `finally` dùng `Files.walk` rồi xóa từ **đường dẫn con tới cha**. Do `paths.sorted(...).toList()` tạo danh sách trước khi xóa, không sửa cấu trúc traversal khi đang đọc stream; `try-with-resources` đóng stream duyệt file.

**Vì sao không in toàn bộ chẩn đoán?** Kết quả text chi tiết phụ thuộc JDK/compiler và locale. Bài học minh họa giá trị **có cấu trúc, ổn định hơn** là `true/false` và số `Diagnostic.Kind.ERROR`. Ứng dụng thật có thể dùng collector để hiển thị thông tin dòng/cột/đường dẫn theo nhu cầu.

## 7. Phân tích dòng chẩn đoán để xây báo cáo lỗi hữu ích

Một diagnostic có thể được biểu diễn bằng model:

```text
kind:   ERROR
source: Example.java
line:   4
column: tùy compiler
code:   mã riêng của compiler
text:   thông điệp theo Locale được yêu cầu
```

Đây là **dạng dữ liệu minh họa**, không phải toàn bộ stdout cố định của chương trình ở trên. Để biến thành thông báo báo cáo:

```java
for (Diagnostic<? extends JavaFileObject> d : diagnostics.getDiagnostics()) {
    if (d.getKind() != Diagnostic.Kind.ERROR) {
        continue;
    }
    String file = d.getSource() == null
            ? "(no source)" : d.getSource().getName();
    String position = d.getLineNumber() == Diagnostic.NOPOS
            ? "unknown" : Long.toString(d.getLineNumber());
    System.out.printf("%s:%s: %s%n",
            file, position, d.getMessage(Locale.ROOT));
}
```

Đây là trích đoạn cần đặt trong phạm vi có biến `diagnostics` và imports phù hợp; **không độc lập**. Nếu dữ liệu từ source không tin cậy, đường dẫn và diagnostic text cần được escape/ẩn thông tin nội bộ khi đưa lên UI. Một đường dẫn tuyệt đối có thể để lộ thư mục của máy CI/server.

Khi cần **chẩn đoán ngay trong thời gian thực** thay vì giữ danh sách:

```java
DiagnosticListener<JavaFileObject> listener = diagnostic -> {
    if (diagnostic.getKind() == Diagnostic.Kind.ERROR) {
        // Chuyển sự kiện sang tầng logging/reporting phù hợp.
        System.err.println(diagnostic.getMessage(Locale.ROOT));
    }
};
```

Trích đoạn này không độc lập, cần import `DiagnosticListener` và `Locale`. Trong server/IDE, tránh block thread của compiler bằng I/O kéo dài hoặc ném unchecked exception từ listener; nếu gửi sang queue, thiết kế mức giới hạn và lưu thứ tự/scope của từng tác vụ.

## 8. Phân biệt `call()` trả thất bại với exception của công cụ

Trong API:

- `CompilationTask.call()` và `DocumentationTask.call()` là thao tác chính để thực thi task. Trên trường hợp compile/doc không đạt, kết quả có thể là `false` cùng diagnostics.
- Nhưng tạo task với options không hợp lệ, file manager bị lỗi, component tự định nghĩa (annotation processor/doclet) ném exception hoặc lỗi I/O có thể **ném exception**, không chỉ trả `false`.
- Vì vậy **không được đánh đồng “không có Diagnostic.Kind.ERROR” với “chắc chắn thành công”**. Kiểm tra **cả kết quả task, chẩn đoán và mọi exception**.
- `Boolean.TRUE.equals(task.call())` hữu ích khi logic của bạn muốn xử lý giá trị an toàn; không che mất exception. Trong ví dụ `compile`, method ném `IOException` từ cấu hình/quản lý file khi cần; `main` có `throws Exception` để bài học gọn.

Tổ chức xử lý cho production:

```text
try (StandardJavaFileManager manager = ...) {
    tạo source units + cấu hình output
    tạo task + gọi call()
    kiểm tra Boolean result và DiagnosticCollector
} catch (IOException e) {
    báo lỗi truy cập file / đóng manager
} catch (IllegalArgumentException e) {
    báo lỗi options / argument không hợp lệ
} catch (RuntimeException e) {
    nhận diện lỗi component/provider, log an toàn rồi xử lý
} finally {
    dọn tệp tạm do ứng dụng tạo
}
```

Đây là **pseudocode quy trình**, không phải code Java có thể biên dịch. Đừng gom mọi exception thành một chuỗi `"compilation failed"` mà mất stack trace phục vụ vận hành; đồng thời không trả nguyên đường dẫn/nội dung source bí mật cho người dùng không có quyền.

## 9. `flush`, `close` và tái sử dụng file manager

| Hành động | Ý nghĩa | Khi nào dùng |
| --- | --- | --- |
| `manager.flush()` | Đẩy tài nguyên output đang chờ flush; **không giải phóng toàn bộ file handle**. | Khi có lý do cụ thể cần nhìn output nhưng vẫn giữ manager cho task tiếp. |
| `manager.close()` | Giải phóng tài nguyên được manager mở trực tiếp/gián tiếp; có thể ném `IOException`. | Khi scope sử dụng kết thúc, thông qua `try-with-resources`. |
| `InputStream.close()`, `OutputStream.close()` | Đóng stream do ứng dụng hoặc file object mở. | Khi hoàn tất đọc/ghi; thường gói trong `try-with-resources` riêng. |
| Xóa thư mục tạm / file đầu ra | Thu hồi dữ liệu persist trên disk sau khi không còn cần. | Do ứng dụng quyết định; việc đóng manager không tự xóa artifact. |
| `DiagnosticCollector.getDiagnostics()` | Đọc thông báo đã thu thập; không mở/đóng file. | Sau task, hoặc theo quy trình reporting được thiết kế. |

API cho phép **reuse một `StandardJavaFileManager` qua nhiều task** để cache tệp JAR/classpath khi thích hợp. Tuy nhiên, manager có trạng thái (locations, caches, output), nên cần quản lý thời gian sống và tránh chia sẻ vô điều kiện giữa các task chạy đồng thời.

Cách chọn:

- **Ứng dụng đơn giản hoặc cần cô lập từng lượt:** tạo manager cho mỗi task như ví dụ, đóng khi task kết thúc. Dễ tránh rò tài nguyên và lẫn cấu hình.
- **Build service xử lý nhiều lần với classpath ổn định:** có thể nghiên cứu reuse manager để giảm overhead đọc JAR; vẫn phải có ownership rõ, cấu hình đồng bộ, đo hiệu quả và đóng cuối scope.
- **Công cụ/framework tự cấp manager:** kiểm tra hợp đồng ownership trước khi đóng; không tùy tiện đóng manager mà framework vẫn dùng.

Khi `close()` gây exception trong lúc một exception từ `call()` đang được ném, Java try-with-resources giữ exception chính và ghi exception lúc close ở `getSuppressed()`; không quên kiểm tra suppressed exceptions khi điều tra lỗi khó tái hiện.

## 10. Nhúng Javadoc: lấy diagnostics và đóng StandardJavaFileManager

`DocumentationTool` có cách gọi gần compiler, nhưng phần tạo tài liệu có thêm **doclet** và options riêng:

```java
DocumentationTool javadoc = ToolProvider.getSystemDocumentationTool();
if (javadoc == null) {
    throw new IllegalStateException("jdk.javadoc unavailable");
}
DiagnosticCollector<JavaFileObject> diagnostics =
        new DiagnosticCollector<>();

try (StandardJavaFileManager manager =
             javadoc.getStandardFileManager(
                     diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
    var sources = manager.getJavaFileObjectsFromPaths(
            List.of(Path.of("src/Example.java")));
    boolean ok = javadoc.getTask(
            null, manager, diagnostics, null,
            List.of("-d", "build/api-docs"), sources).call();
    // Dùng ok + diagnostics để đánh giá kết quả.
}
```

Đây là **trích đoạn minh họa**, cần đã tồn tại file `src/Example.java`, thư mục/đường output phù hợp và imports. `null` ở tham số `docletClass` chọn **Standard Doclet**; nếu cung cấp class doclet, nó chạy như mã Java trong tiến trình tạo tài liệu.

Phần chẩn đoán của Javadoc có thể đến từ phân tích Java, doclint, phần sinh HTML và custom doclet. `DiagnosticCollector` là kênh chuẩn để thu chúng, nhưng vẫn cần kiểm tra kết quả `call()` và exception. Nếu viết **custom doclet** trong module `jdk.javadoc.doclet`, công cụ cung cấp thêm `Reporter` cho mã doclet phát note/warning/error; đó là vai trò của người **viết doclet**, còn `DocumentationTool` là API của người **gọi công cụ**.

Tách rõ **đóng file manager của JavaDoc API** với **đọc/ghi output** của doclet: file `index.html` và các tệp khác vẫn nằm trên disk sau khi manager đóng; dọn dẹp tệp tạm hoặc xuất bản tài liệu là trách nhiệm của ứng dụng.

## 11. Khi nào dùng `java.util.spi.ToolProvider.findFirst`?

Nếu chỉ muốn chạy một lệnh công cụ tương tự CLI và nhận mã thoát/text, API SPI tiện hơn:

```java
var tool = java.util.spi.ToolProvider.findFirst("javac")
        .orElseThrow(() ->
                new IllegalStateException("javac not available"));

var stdout = new java.io.StringWriter();
var stderr = new java.io.StringWriter();
var out = new java.io.PrintWriter(stdout);
var err = new java.io.PrintWriter(stderr);

int exit = tool.run(out, err,
        "--release", "17", "-d", "build/classes", "src/Example.java");
out.flush();
err.flush();

System.out.println("exit: " + exit);
System.out.println("stderr chars: " + stderr.getBuffer().length());
```

**Đây là trích đoạn minh họa, không độc lập**: yêu cầu file `src/Example.java`, đường `build/classes` được chuẩn bị và JDK provider `javac` hiện diện. `StringWriter` lưu dữ liệu trong bộ nhớ; với output lớn nên định hướng output qua writer thích hợp hoặc kiểm soát dung lượng, và đóng writer mà ứng dụng sở hữu khi kết thúc.

`run(...)` trả **`int`**, giá trị `0` biểu thị thành công; kết quả khác 0 là lỗi theo quy ước riêng của công cụ. Tuy nhiên, **stdout/stderr ở dạng chuỗi text**, không tự cung cấp `Diagnostic.getLineNumber()` hay `Diagnostic.getSource()`. Nếu ứng dụng cần map lỗi compiler về vị trí source để IDE đánh dấu, `JavaCompiler.getTask` và collector thường phù hợp hơn.

Trong module JDK hiện đại:

- `javax.tools.ToolProvider.getSystemJavaCompiler()` tìm compiler của `jdk.compiler` nếu module đó hiện diện.
- `javax.tools.ToolProvider.getSystemDocumentationTool()` tìm Javadoc của `jdk.javadoc` nếu module đó hiện diện.
- `java.util.spi.ToolProvider.findFirst("javac")` hoặc `findFirst("javadoc")` dùng service provider theo tên tool.
- Một runtime tùy biến từ `jlink` có thể thiếu những module tool; **không giả định cứ có JVM là có compiler/Javadoc**.

Không sử dụng `javax.tools.ToolProvider.getSystemToolClassLoader()`: phương thức đó đã **deprecated từ Java 9** và JDK hiện hành không cung cấp classloader cũ theo cách này.

## 12. Lưu ý module Java 9+ và môi trường triển khai

Ứng dụng có `module-info.java` dùng compiler/documentation API cần khai báo module API:

```java
module my.embedded.tools {
    requires java.compiler;
}
```

`java.compiler` chứa các API `javax.tools`. Triển khai hệ thống còn cần có **provider thực thi** `jdk.compiler` cho compiler và `jdk.javadoc` cho Javadoc. Module runtime có thể tạo bằng `jlink`; chỉ thêm `java.compiler` không mặc định bảo đảm cả hai công cụ có sẵn.

Đối với Java application chạy trên classpath (như ví dụ), không cần `module-info.java`. Ví dụ yêu cầu **JDK đầy đủ**, vì runtime đã rút gọn có thể không cung cấp compiler hoặc documentation tool. Thử `ToolProvider.getSystemJavaCompiler()` và `getSystemDocumentationTool()` ngay khi khởi động tác vụ, và báo lỗi rõ nếu trả `null`.

Khi biên dịch mã ở version khác, `--release 17` giúp giới hạn API/ngôn ngữ nền tảng theo Java 17 trên tool hỗ trợ mức đó. Đừng dùng `-source`/`-target` rồi kết luận chương trình chỉ dùng API của nền tảng đích; `--release` là lựa chọn phù hợp hơn cho kiểm tra tương thích với Java runtime đích.

## 13. Tính an toàn, hiệu năng và giới hạn của công cụ nhúng

**Chẩn đoán tốt và đóng file manager mới giải quyết vòng đời I/O.** Công cụ nhúng vẫn có thể tiêu thụ CPU/RAM, chạy plugin và xử lý mã không đáng tin. Các vấn đề hiện hành:

1. **Kiểm soát mã nguồn nhập vào.** Compiler phân tích code theo Java language, nhưng các annotation processors và plugin build có thể **thực thi mã Java** trong quá trình biên dịch. Javadoc có thể chạy custom doclet. Không coi việc gọi compiler hay Javadoc trong cùng JVM là sandbox an toàn cho source/plugin độc hại.
2. **Giảm quyền/đặt giới hạn.** Với nguồn từ người dùng bên ngoài, cân nhắc dịch vụ hoặc process bị cô lập, giới hạn file system/network, thời gian chạy, CPU, memory và số lượng tác vụ đồng thời. Các API `javax.tools` **không tự tạo sandbox**.
3. **Tắt annotation processing nếu không cần.** Với compiler có hỗ trợ, dùng option `-proc:none` khi cần tránh chạy processors; chú ý các plugin khác và classpath/modulepath vẫn phải kiểm soát.
4. **Không thu thập vô hạn.** Compiler có thể phát rất nhiều diagnostics; `DiagnosticCollector` lưu tất cả trong RAM. Cân nhắc giới hạn số diagnostic báo cáo, cắt gọn log và đặt ngưỡng input.
5. **Quản lý đường dẫn.** Không cho user tùy ý chọn `-d` tới thư mục nhạy cảm; sanitize tên file/đường dẫn, dùng thư mục tạm cách ly, tránh path traversal, symlink race trong môi trường nhiều tenant.
6. **Không làm lộ source.** Chẩn đoán có thể lộ tên file, source fragment và đường dẫn hệ thống. Phân loại quyền xem, che thông tin nhạy cảm và không gửi toàn bộ compiler output sang log công khai.
7. **Đảm bảo cleanup.** Đóng file managers và streams; xóa file tạm khi hợp lệ; nếu cần lưu artifact, chuyển đến nơi có chính sách lưu trữ rõ ràng.
8. **Phiên bản JDK và tái lập.** Compiler/Javadoc mỗi JDK có thể thay đổi diagnostics, doclint và định dạng HTML; khóa toolchain trong CI, test các điều kiện quan trọng qua `kind`, mã thoát và nội dung file, tránh phụ thuộc message text từng ký tự.

Nếu nhiều request trong server đồng thời dùng compiler/Javadoc, mô hình **mỗi request có collector và manager riêng** dễ cô lập dữ liệu. Chỉ reuse/caching khi hiểu rõ thread safety và hợp đồng ownership của provider.

## 14. Lỗi thường gặp và xử lý

| Triệu chứng/nhầm lẫn | Nguyên nhân và cách khắc phục |
| --- | --- |
| `ToolProvider.getSystemJavaCompiler() == null` | Runtime thiếu `jdk.compiler` hoặc provider không hiện diện; chạy trên JDK đầy đủ hoặc cấu hình module khi xây runtime. |
| `getSystemDocumentationTool() == null` | Thiếu `jdk.javadoc`; kiểm tra JDK/jlink image. |
| Có `false` nhưng không có lỗi hiển thị | Chưa truyền collector/listener vào `getTask`, có diagnostic ra kênh writer khác, hoặc lỗi được báo bằng exception. |
| Collector của lần 2 chứa lỗi từ lần 1 | Tái sử dụng collector; tạo mới cho mỗi nhiệm vụ độc lập. |
| `getSource() == null` hay dòng `-1` | Có diagnostic không gắn source/vị trí; hiển thị placeholder an toàn thay vì dereference. |
| Lỗi path/classpath không dễ đọc | Cấu hình file manager/locations sai, module path hoặc file đầu vào không tồn tại; in thông tin cấu hình không nhạy cảm. |
| `IOException` khi đóng file manager | Lỗi tài nguyên I/O; kiểm tra suppressed exceptions và xử lý/ghi log, không bỏ qua. |
| File JAR không thể xóa/di chuyển trong khi app chạy | File manager/stream có thể còn giữ handle; kiểm tra try-with-resources và scope của cache. |
| `flush()` rồi cho rằng mọi handle đã giải phóng | `flush` không đồng nghĩa `close`. |
| Tác vụ trả `true` nhưng báo cáo source sai | Kiểm tra file output, số artifact, vị trí class output và việc source có đúng phiên bản. |
| `DocumentationTool` thành công nhưng không có HTML ở đường dự kiến | Sai `-d`, doclet riêng không sinh HTML, hoặc tìm sai thư mục xuất. |
| `java.util.spi.ToolProvider.run(...)` không có lỗi dạng `Diagnostic` | SPI CLI trả mã thoát và text; muốn chẩn đoán có cấu trúc thì dùng `JavaCompiler`/`DocumentationTool` task API. |
| Compiler chạy rất chậm/tốn RAM | Rất nhiều source/diagnostics, annotation processors, classpath lớn hoặc quá nhiều tác vụ đồng thời; giới hạn input và đo hiệu năng. |
| Mã build chạy trên JDK này nhưng lỗi trên JDK khác | `--release` không được hỗ trợ hoặc thay đổi cấu hình tool/provider; thống nhất JDK và target release. |

### Checklist vận hành

Trước mỗi lượt gọi công cụ nhúng, kiểm tra:

- Đã nhận đúng provider (`getSystemJavaCompiler()` hoặc `getSystemDocumentationTool()` khác `null`)?
- Mã nguồn và đường output được cho phép? Charset và `--release` có được xác định rõ?
- Collector/listener mới được truyền vào **cả task và file manager** khi cần?
- Đã gọi `call()`, kiểm tra kết quả cùng các diagnostics và exceptions?
- Đã đóng `StandardJavaFileManager` và các stream của mình bằng `try-with-resources`?
- Đã xử lý file output/temp, chính sách lưu trữ/xóa và tránh rò dữ liệu?
- Có hạn mức CPU/memory/disk/diagnostics nếu công cụ được gọi từ API server?

## 15. Câu hỏi tự kiểm tra

**Tình huống A.** Một lượt compile trả `false` và listener ghi `ERROR` ở dòng 4. Ứng dụng nên hiển thị gì? **Kết quả thất bại cùng loại lỗi, tên source nếu có, dòng/cột nếu có và thông điệp được escape theo giao diện.** Không coi `-1` là một dòng hợp lệ.

**Tình huống B.** Dùng `compiler.getTask(null, null, ...)` và không đóng gì có đúng không? **Có thể chạy**, nhưng bạn không sở hữu manager tường minh để quản lý vòng đời. Nếu cần quản lý tài nguyên và nhiều tác vụ, tạo `StandardJavaFileManager` có scope rõ rồi đóng bằng `try-with-resources`.

**Tình huống C.** Sau `fileManager.flush()`, liệu có thể kết luận JAR đã được giải phóng? **Không.** `close()` mới là phương thức giải phóng tài nguyên của manager.

**Tình huống D.** Custom Javadoc doclet ném exception, collector rỗng. Có nghĩa tài liệu tạo thành công? **Không.** Phải xem kết quả `call()`, exception và file output; diagnostics không bao phủ mọi lỗi.

**Tình huống E.** Muốn dùng công cụ `javadoc` như CLI và chỉ lấy mã thoát cùng stdout/stderr, phải viết `DocumentationTool` đầy đủ không? **Không bắt buộc.** Có thể dùng `java.util.spi.ToolProvider.findFirst("javadoc")` rồi `run` khi JDK cung cấp provider.

## Tài liệu chính thức còn hiệu lực

- Java SE 26 — [`javax.tools.JavaCompiler`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/JavaCompiler.html): `getTask`, listeners, file managers, ví dụ thu diagnostics.
- Java SE 26 — [`javax.tools.DocumentationTool`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/DocumentationTool.html): nhúng Javadoc, `getTask`, diagnostics và file manager.
- Java SE 25/26 — [`StandardJavaFileManager`](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html) và [`JavaFileManager`](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/JavaFileManager.html): quản lý tài nguyên, `close` và `flush`.
- Java SE 26 — [`Diagnostic`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/Diagnostic.html), [`DiagnosticCollector`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/DiagnosticCollector.html), [`DiagnosticListener`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/DiagnosticListener.html).
- Java SE 25 — [`javax.tools.ToolProvider`](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/ToolProvider.html): compiler/Javadoc providers, deprecation của `getSystemToolClassLoader`.
- Java SE 25 — [`java.util.spi.ToolProvider`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/spi/ToolProvider.html): SPI công cụ theo tên, `findFirst` và `run`.
- Java SE 25 — [Module `jdk.javadoc`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.javadoc/module-summary.html): provider cho công cụ `javadoc` và API doclet.

**Ghi nhớ:** Khi nhúng công cụ JDK vào ứng dụng, tách rõ **kết quả task, chẩn đoán và vòng đời tài nguyên**. Dùng `DiagnosticCollector` khi cần lỗi có cấu trúc; dùng `try-with-resources` để đóng `StandardJavaFileManager`; kiểm tra cả `call()` và exceptions; dọn file tạm; chỉ chạy nguồn/processors/doclets trong phạm vi tin cậy và kiểm soát. Đây là các nguyên tắc vẫn áp dụng trên các JDK hiện đại.
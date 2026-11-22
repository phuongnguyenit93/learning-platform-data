# Xử lý kết quả `call()`, đầu ra chẩn đoán và lỗi cấu hình trong Java Compiler API

Khi ứng dụng Java gọi **Java Compiler API** để biên dịch chương trình, nó không đơn thuần nhận một chuỗi thông báo giống khi chạy `javac` từ terminal. API `javax.tools.JavaCompiler` trả về một đối tượng **`CompilationTask`**; ứng dụng có thể lấy **kết quả `Boolean`** của `call()`, thu thập **diagnostics có cấu trúc** qua `DiagnosticListener` hoặc `DiagnosticCollector`, và nhận **đầu ra bổ sung** qua `Writer`. Ngoài lỗi trong mã nguồn được báo theo cách thông thường, lời gọi còn có thể thất bại vì **cấu hình compiler, option không hợp lệ, đường dẫn, file manager hoặc một thành phần do người dùng cài đặt**.

Phân biệt ba kênh kết quả này là điều kiện cần để viết IDE, dịch vụ compile-online, test framework, code-generation tool hoặc plugin build không kết luận sai rằng “không có exception nghĩa là compile thành công”.

Bài dùng Java 17 trở lên, ưu tiên Java Compiler API công khai trong module `java.compiler` và phân biệt những quy định của API với chi tiết hiển thị của bản `javac` cụ thể.

## 1. Kiến trúc một lần compile bằng API

Một chuỗi thao tác phổ biến:

```text
ToolProvider.getSystemJavaCompiler()
           |
           v
JavaCompiler instance
           |
           +-- DiagnosticCollector<JavaFileObject>
           +-- StandardJavaFileManager
           +-- nguồn: JavaFileObject / compilationUnits
           +-- options: --release, -d, -cp, ...
           +-- Writer: additional compiler output
           |
           v
compiler.getTask(...)
           |
           v
JavaCompiler.CompilationTask
           |
           v
task.call()
   |                    |                    |
   v                    v                    v
Boolean result      Diagnostics list      Possible exceptions
true / false        ERROR, WARNING, ...   configuration/SPI failures
   |
   v
close file manager, inspect class output, report status
```

**`getTask(...)` tạo ra một compilation task chưa chạy**; `call()` mới kích hoạt compilation. Trả về `true` nghĩa là toàn bộ các files được xử lý **không có compilation errors** theo hợp đồng của task. Trả về `false` nghĩa là compilation không hoàn thành thành công do lỗi, thường có diagnostics liên quan.

**Không dùng `task.call() != null` làm tiêu chí thành công.** Với `CompilationTask` theo API, `Boolean.TRUE.equals(task.call())` là cách diễn đạt tường minh, tránh nhầm object `Boolean.FALSE` (khác `null`) thành thành công.

### Các đối tượng cần hiểu

| Thành phần | Vai trò | Lưu ý |
| --- | --- | --- |
| `ToolProvider.getSystemJavaCompiler()` | Lấy compiler đi kèm platform hiện tại | Có thể trả `null` nếu image/runtime không có compiler, ví dụ thiếu module `jdk.compiler` |
| `JavaCompiler.getTask(...)` | Tạo compilation task với file manager, listener, options và input | Có thể ném `IllegalArgumentException` nếu cấu hình input/option bất hợp lệ |
| `JavaCompiler.CompilationTask.call()` | Thực hiện compile và trả `Boolean` | Mỗi task **chỉ được `call` một lần** |
| `DiagnosticCollector<JavaFileObject>` | Thu các chẩn đoán vào danh sách | Bao gồm kind, code, source, line/column/message nếu có |
| `Writer out` của `getTask` | Nhận **additional output** của compiler | Không thay thế hoàn toàn diagnostic listener |
| `StandardJavaFileManager` | Quản lý file source, output location và đọc classpath | Cần đóng đúng cách, phù hợp `try-with-resources` |
| `JavaFileObject` | Mô hình input/output Java source/class | Có thể đại diện file thực hoặc source từ chuỗi trong bộ nhớ |

Khác với cách chạy `javac` bằng `ProcessBuilder`, Compiler API không cần tạo tiến trình OS mới cho mỗi lượt compile. Nó hoạt động trong JVM đang gọi compiler và sử dụng những đối tượng cung cấp cho task, nên **exception của annotation processor, file manager hoặc listener** có thể ảnh hưởng trực tiếp đến chương trình điều phối.

## 2. Kết quả `CompilationTask.call()`: đúng nghĩa true/false

`JavaCompiler.CompilationTask` mở rộng `Callable<Boolean>`. Java SE 17 xác định:

- `call()` thực hiện công việc biên dịch; **trả `true` khi và chỉ khi tất cả file được compile không có errors**.
- `false` là dấu hiệu compilation có lỗi theo API; thường xảy ra với lỗi cú pháp, type checking, thiếu class, invalid source constructs.
- **Gọi lại `call()` lần hai trên chính task** sẽ ném `IllegalStateException`. Muốn biên dịch lại, hãy **tạo task mới**.
- `call()` có thể ném `RuntimeException` nếu gặp lỗi không thể khắc phục trong **thành phần do người dùng cung cấp**, với nguyên nhân thực được gắn trong cause.

Ví dụ nguyên tắc:

```java
JavaCompiler.CompilationTask task = compiler.getTask(
        additionalOutput,
        fileManager,
        diagnostics,
        options,
        null,
        compilationUnits
);
boolean ok = Boolean.TRUE.equals(task.call());
```

Đây là **mảnh code trong một phương thức** có đầy đủ các biến và imports tương ứng, chưa phải chương trình độc lập. Chú ý cách kiểm tra:

```java
if (!ok) {
    // Thông báo compile thất bại; xem diagnostics và output bổ sung.
}
```

Không viết `try { task.call(); success = true; } catch (...) { ... }` vì **nhiều lỗi nguồn chỉ khiến `call()` trả `false`**, không hề ném exception.

### Một task chỉ dùng một lần, file manager có thể dùng nhiều lần

Tài liệu API nhấn mạnh `CompilationTask.call()` **chỉ một lần**, nhưng một `StandardJavaFileManager` được hỗ trợ dùng cho nhiều **sequential compilations** nếu quản lý đúng. Vì vậy có thể:

1. Dùng cùng `JavaCompiler` để tạo task A, gọi A đúng một lần.
2. Tạo task B hoàn toàn mới và gọi B đúng một lần.
3. Tái sử dụng file manager nếu muốn cache đường dẫn/JAR, nhưng tránh concurrency không có đảm bảo và giữ riêng diagnostics/output của từng task.
4. Đóng file manager sau khi hoàn tất.

Ví dụ chính ở dưới tạo file manager mới mỗi lần để làm rõ lifecycle, thay vì tối ưu sớm.

## 3. Diagnostics có cấu trúc: vì sao không chỉ đọc chuỗi stderr?

`DiagnosticCollector<JavaFileObject>` là một triển khai `DiagnosticListener` lưu các `Diagnostic` trong một danh sách. Thay vì parse các dòng text phụ thuộc locale/phiên bản, có thể truy cập từng thuộc tính:

| Thuộc tính của `Diagnostic` | Dùng để làm gì? |
| --- | --- |
| `getKind()` | Phân loại `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE`, `OTHER` |
| `getCode()` | Mã chẩn đoán do compiler định nghĩa; hữu ích cho logs nhưng không phải mã chuẩn ổn định cho mọi compiler |
| `getMessage(Locale.ROOT)` | Nội dung chẩn đoán đã format; ngôn ngữ/cách diễn đạt có thể khác |
| `getSource()` | Source `JavaFileObject` liên quan; **có thể `null`** với lỗi không gắn một file cụ thể |
| `getLineNumber()` | Dòng nguồn nếu có |
| `getColumnNumber()` | Cột nguồn nếu có |
| `getStartPosition()` / `getEndPosition()` | Phạm vi ký tự nếu compiler cung cấp |
| `getPosition()` | Vị trí ký tự ưu tiên nếu có |

Nếu không có thông tin vị trí, API có giá trị đặc biệt như `Diagnostic.NOPOS`, **không** phải lúc nào line/column cũng là số dương. Đừng truyền thẳng `diagnostic.getSource().toUri()` khi chưa kiểm tra `getSource() != null`.

Ví dụ duyệt diagnostics an toàn:

```java
for (Diagnostic<? extends JavaFileObject> d :
        diagnostics.getDiagnostics()) {
    String where = d.getSource() == null
            ? "<no source>"
            : d.getSource().toUri().toString();
    System.out.printf(
            "%s code=%s file=%s line=%d col=%d%n",
            d.getKind(), d.getCode(), where,
            d.getLineNumber(), d.getColumnNumber());
    System.out.println(d.getMessage(Locale.ROOT));
}
```

Đây là **đoạn logic minh họa** nằm trong một chương trình đã khai báo `diagnostics` và imports; thứ tự, message hoặc số diagnostics **không được coi là output cố định**. Khi IDE cần highlight, chỉ sử dụng range nếu không phải `NOPOS` và chuyển đổi line/column theo API GUI của mình.

### `getDiagnostics()` không đồng nghĩa mọi thứ compiler đã in ra

Tài liệu `JavaCompiler` ghi rõ: nếu có diagnostic listener, phần diagnostics thích hợp sẽ được chuyển cho listener. **Nhưng vẫn có một số thông điệp/diagnostics không thể biểu diễn thành `Diagnostic`** và có thể được viết vào **additional output Writer**. Vì vậy, đối với ứng dụng cần log đầy đủ:

1. **Kết quả task:** `Boolean` từ `call()`.
2. **Diagnostics có cấu trúc:** `DiagnosticCollector` hoặc custom listener.
3. **Additional output:** `Writer` truyền vào `getTask(...)`.
4. **Exceptions:** các lỗi cấu hình/runtime/SPI phát sinh ở bước thiết lập hoặc thực thi.

Không giả định một kênh là bản sao hoàn chỉnh của ba kênh kia.

### WARNING không tự động là lỗi

Nếu compiler báo `Diagnostic.Kind.WARNING` hoặc `MANDATORY_WARNING`, `call()` vẫn có thể `true` **nếu không có lỗi**. Nếu kích hoạt chính sách `-Werror`, các warning được phát ra có thể làm compilation thất bại theo quy tắc compiler. Đừng tự quy ước `diagnostics.getDiagnostics().isEmpty()` là tiêu chí duy nhất để xác nhận build thành công: note/warning có thể tồn tại ngay khi `call()` trả true.

Nếu cần kiểm soát chính sách, cấu hình rõ các options liên quan đến lint/warnings và dùng kết quả `call()` làm nguồn xác nhận compile success.

## 4. Phân biệt `Writer out`, listener và stdout/stderr

Chữ ký `JavaCompiler.getTask`:

```java
JavaCompiler.CompilationTask getTask(
        Writer out,
        JavaFileManager fileManager,
        DiagnosticListener<? super JavaFileObject> diagnosticListener,
        Iterable<String> options,
        Iterable<String> classes,
        Iterable<? extends JavaFileObject> compilationUnits)
```

Đây là **khai báo API minh họa** (tên type có thể được trình bày với generic wildcards đầy đủ). Các tham số:

- **`out`**: `Writer` nhận **additional output** của compiler. Nếu `null`, compiler sử dụng output mặc định, thường `System.err`.
- **`fileManager`**: file manager đọc/ghi sources, classes, output và các locations. Nếu `null`, compiler dùng standard file manager.
- **`diagnosticListener`**: nhận diagnostics có cấu trúc. Nếu `null`, compiler tự format diagnostics và gửi tới output mặc định.
- **`options`**: danh sách **compiler options** giống chức năng cờ `javac`; `null` nghĩa là không truyền cờ.
- **`classes`**: **tên các classes để annotation processing**, không phải mọi source files cần compile; thường truyền `null` khi compile source Java thông thường.
- **`compilationUnits`**: danh sách `JavaFileObject` kiểu SOURCE cần compile; trong thao tác compile source, không nên nhét `String` đường dẫn vào đây.

Nếu cung cấp **cả listener và Writer**, không có cam kết rằng lỗi nguồn sẽ được in dạng text trong Writer. Chúng thường đi qua listener/collector. Ngược lại, **Writer rỗng không chứng minh không có lỗi**, và **Collector rỗng không chứng minh mọi output khác đều rỗng**.

### Khi nào nên dùng `StringWriter`?

`StringWriter` thuận tiện cho compiler API vì có thể lưu additional output trong RAM:

```java
StringWriter otherOutput = new StringWriter();
DiagnosticCollector<JavaFileObject> diagnostics =
        new DiagnosticCollector<>();

JavaCompiler.CompilationTask task = compiler.getTask(
        otherOutput, fileManager, diagnostics, options, null, units);
boolean success = Boolean.TRUE.equals(task.call());
String extra = otherOutput.toString();
```

Đây là **snippet**, không phải file hoàn chỉnh. `StringWriter` không thay thế `DiagnosticCollector`. Khi cung cấp các thành phần do người dùng viết, cần tránh để listener hoặc Writer tùy biến ném lỗi bất thường mà không được giám sát.

### Khi nào dùng custom `DiagnosticListener`?

Có thể truyền lambda:

```java
DiagnosticListener<JavaFileObject> listener =
        diagnostic -> {
            if (diagnostic.getKind() == Diagnostic.Kind.ERROR) {
                // Gửi dữ liệu chẩn đoán đã kiểm tra null/NOPOS tới UI.
            }
        };
```

Đây cũng là **mảnh minh họa**. Listener được gọi trong lúc compiler xử lý; tránh ném unchecked exception, blocking lâu hoặc tự chỉnh file/source đang được compiler dùng bên trong callback. Collector thường dễ kiểm thử và xử lý theo batch hơn.

## 5. Ví dụ Java 17 đầy đủ: một lần thành công và một lần lỗi nguồn

Ví dụ thực hành sau cố ý biên dịch **hai chương trình nguồn dạng chuỗi trong bộ nhớ**, không cần tạo file `Hello.java`/`Broken.java` đầu vào. Ứng dụng host vẫn ghi compiled class của bài thành công vào thư mục output riêng.

### 5.1. Tạo chương trình `CompilerApiDemo.java`

Lưu tệp đúng tên **`CompilerApiDemo.java`**:

```java
import java.io.IOException;
import java.io.StringWriter;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class CompilerApiDemo {
    private static final class StringSource
            extends SimpleJavaFileObject {
        private final String source;

        StringSource(String className, String source) {
            super(URI.create("string:///"
                    + className.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.source = source;
        }

        @Override
        public CharSequence getCharContent(
                boolean ignoreEncodingErrors) {
            return source;
        }
    }

    private static void compile(
            JavaCompiler compiler,
            String label,
            String className,
            String source,
            Path output)
            throws IOException {

        Files.createDirectories(output);

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();
        StringWriter otherOutput = new StringWriter();

        try (StandardJavaFileManager manager =
                     compiler.getStandardFileManager(
                             diagnostics, Locale.ROOT,
                             StandardCharsets.UTF_8)) {

            List<String> options = List.of(
                    "--release", "17",
                    "-proc:none",
                    "-encoding", "UTF-8",
                    "-d", output.toString());

            JavaCompiler.CompilationTask task =
                    compiler.getTask(
                            otherOutput,
                            manager,
                            diagnostics,
                            options,
                            null,
                            List.of(new StringSource(className, source)));

            boolean success = Boolean.TRUE.equals(task.call());
            boolean hasErrors = diagnostics.getDiagnostics().stream()
                    .anyMatch(d -> d.getKind()
                            == Diagnostic.Kind.ERROR);

            System.out.println(label + ": success=" + success
                    + ", hasErrors=" + hasErrors);

            // In diagnostics ở sản phẩm thật bằng getKind(),
            // getCode(), getSource(), positions và getMessage().
            // Không parse nội dung message để xác định thành công.
        }
    }

    public static void main(String[] args) throws IOException {
        JavaCompiler compiler =
                ToolProvider.getSystemJavaCompiler();

        if (compiler == null) {
            throw new IllegalStateException(
                    "No system Java compiler available");
        }

        String good =
                "package demo;\n"
                + "public class Hello {\n"
                + "  public static int twice(int n) {\n"
                + "    return n * 2;\n"
                + "  }\n"
                + "}\n";

        String bad =
                "package demo;\n"
                + "public class Broken {\n"
                + "  public static void wrong() {\n"
                + "    int value = \"text\";\n"
                + "  }\n"
                + "}\n";

        compile(compiler, "valid", "demo.Hello", good,
                Path.of("build", "api-valid"));
        compile(compiler, "invalid", "demo.Broken", bad,
                Path.of("build", "api-invalid"));
    }
}
```

### 5.2. Biên dịch và chạy host

Dùng JDK có compiler và hỗ trợ Java 17, đứng tại thư mục chứa `CompilerApiDemo.java`:

```sh
javac --release 17 -encoding UTF-8 CompilerApiDemo.java
java CompilerApiDemo
```

**Stdout dự kiến chính xác từ chính chương trình trên** (không in diagnostics chi tiết):

```text
valid: success=true, hasErrors=false
invalid: success=false, hasErrors=true
```

Giải thích:

1. `ToolProvider.getSystemJavaCompiler()` lấy system compiler, được kiểm tra không phải `null` trước khi dùng.
2. `StringSource` là `SimpleJavaFileObject` có `Kind.SOURCE` và URI `string:///demo/Hello.java` hoặc `string:///demo/Broken.java`; `getCharContent` trả nội dung để compiler đọc.
3. `getStandardFileManager` dùng `Locale.ROOT` và UTF-8 để kiểm soát cách đọc/format phù hợp hơn với bài học; chính options còn quy định `-encoding UTF-8` cho source đầu vào.
4. Mỗi lời gọi `compile(...)` tạo một `CompilationTask` mới và **gọi `call()` đúng một lần**, không dùng lại task đã chạy.
5. `-proc:none` tắt annotation processing để ví dụ chỉ tập trung vào compiler-result/diagnostics, tránh processor tự động làm thay đổi kết quả.
6. Bản nguồn `Hello` hợp lệ nên `call()` trả true, không có `ERROR`.
7. Bản nguồn `Broken` gán `String` vào `int` nên có lỗi kiểu, `call()` trả false và `DiagnosticCollector` chứa ít nhất một `ERROR`.
8. Hai output directories được tách riêng để tránh xem nhầm class file hợp lệ còn lại từ lần compile khác.
9. File manager tự đóng nhờ try-with-resources ngay cả nếu tác vụ ném exception; output directory được tạo trước khi chạy `getTask`.

Từ `build/api-valid` có thể tìm thấy `demo/Hello.class`. Với `build/api-invalid`, **không nên suy ra sẽ có class file cho `Broken`**. Trong dự án thật, compilation có thể tạo **một số output** trước khi phát hiện lỗi; không xem kết quả `call=false` là giao dịch tự động rollback toàn bộ files đã ghi.

### 5.3. Xem diagnostics thực tế thay vì chỉ boolean

Để khám phá thông tin lỗi, bổ sung **trong phương thức `compile` sau `task.call()`**:

```java
for (Diagnostic<? extends JavaFileObject> d :
        diagnostics.getDiagnostics()) {
    String sourceName = d.getSource() == null
            ? "<none>" : d.getSource().toUri().toString();

    System.out.printf(
            "%s at %s:%d:%d [%s]%n",
            d.getKind(),
            sourceName,
            d.getLineNumber(),
            d.getColumnNumber(),
            d.getCode());
    System.out.println(d.getMessage(Locale.ROOT));
}
```

Đây là **mảnh mở rộng**, không phải mã đã được chạy bởi chương trình ban đầu. Lệnh trên có thể in nhiều dòng vì `Broken` sai kiểu; **không cố ghi nguyên văn message và vị trí** như một kết quả bắt buộc cho mọi compiler/JDK. Những thuộc tính như `getSource` và vị trí có thể thiếu hoặc là `NOPOS` ở các chẩn đoán khác.

### 5.4. Nếu muốn chạy class được compile trong bộ nhớ

Compiler của ví dụ **đọc source từ chuỗi**, nhưng **ghi output class vào đĩa** nhờ `-d` và standard file manager. Điều này **không** đồng nghĩa `Hello` đã được load vào JVM host sau khi `call()` thành công. Muốn gọi method `Hello.twice` lúc runtime cần một class loader thấy output (hoặc một custom in-memory file manager và class loader được thiết kế đúng).

Ví dụ lệnh chạy `Hello` trực tiếp sẽ không hoạt động vì lớp này **không có `public static void main(String[])`**. Nếu muốn demo runtime, tạo một class `Main` có `main` và gọi `Hello.twice`, rồi chạy với classpath gồm output tương ứng.

## 6. Cách phân loại ba nhóm lỗi lớn

| Tình huống | `getTask(...)` | `call()` | Cần xử lý gì? |
| --- | --- | --- | --- |
| Java source đúng, options hợp lệ | Tạo task | `true` | Kiểm tra output nếu muốn dùng artifact |
| Java source sai syntax/type | Thường tạo task | `false` | Đọc `ERROR` diagnostics, không gán cho “system crash” |
| Thiếu dependency/source class | Thường tạo task | `false` | Kiểm tra classpath/module path và diagnostics |
| `-Werror` khi có warning được coi là error | Tạo task | Có thể `false` | Phân biệt warning policy và lỗi nguồn |
| Option không hợp lệ | **Có thể ném `IllegalArgumentException`** theo hợp đồng `getTask` | Không chắc đã có task để gọi | Validate options/tránh dùng option không được hỗ trợ |
| Input `JavaFileObject` không phải `Kind.SOURCE` | **`IllegalArgumentException`** theo hợp đồng `getTask` | Không có task hợp lệ | Cấp đúng compilation units |
| Đường dẫn output/fileManager lỗi | Có thể lỗi ở cấu hình file manager hoặc khi compile | Có thể exception/failed task tùy nguyên nhân | Kiểm tra directory, quyền, disk, path provider |
| Compiler runtime không có `jdk.compiler` | `compiler == null` từ `ToolProvider` | Không thể tạo task | Chạy trên JDK/runtime image có compiler |
| Custom listener/Writer/file manager/processor ném exception không phục hồi | Có thể lỗi trong getTask hoặc call | Có thể `RuntimeException` và cause | Log cause, điều tra callback tùy biến |
| Gọi lại cùng task | Task đã chạy | **`IllegalStateException`** | Tạo một task mới |

**Không ép tất cả vào “`call()` trả false”** và cũng không ép tất cả vào “throw `Exception`”. Lỗi nguồn là một kết quả biên dịch thông thường; lỗi configuration/SPI có thể là ngoại lệ ở giai đoạn thiết lập hoặc chạy. Điều quan trọng là biết **ở pha nào lỗi phát sinh**.

### `IllegalArgumentException` khi options sai

Theo Javadoc `JavaCompiler.getTask`, option không hợp lệ hoặc compilation unit khác SOURCE có thể ném `IllegalArgumentException`. Chẳng hạn một option hoàn toàn không được compiler nhận diện có thể bị từ chối ngay từ lúc tạo task:

```java
List<String> options = List.of("-this-option-does-not-exist");
JavaCompiler.CompilationTask task =
        compiler.getTask(null, manager, diagnostics,
                         options, null, units);
```

Đây là **negative snippet** để tìm hiểu lỗi cấu hình, không phải chương trình độc lập. Không nên dựa vào nội dung message exception cố định vì mỗi implementation có thể khác. Một lựa chọn được nhận diện nhưng **xung đột với lựa chọn khác** cũng có thể được compiler báo theo kênh khác tùy chi tiết; hãy xử lý cả exception và kết quả/diagnostics.

Có thể kiểm tra sơ bộ `compiler.isSupportedOption(option)` từ giao diện `OptionChecker` để xác định hỗ trợ và số đối số mà compiler kỳ vọng, nhưng phép kiểm tra này **không thay thế validation toàn bộ tổ hợp options**, không bảo đảm các path tồn tại hay target release hợp lệ.

### File manager và output location

Nếu dùng `StandardJavaFileManager.setLocationFromPaths`, hãy tạo **output directory thật sự tồn tại** trước khi đặt location:

```java
Path output = Path.of("build", "classes");
Files.createDirectories(output);
manager.setLocationFromPaths(
        StandardLocation.CLASS_OUTPUT,
        List.of(output));
```

Đây là **mảnh bên trong code có `manager`, imports phù hợp**, không phải file độc lập. Java SE 17 ghi rõ `setLocationFromPaths` có thể ném `IOException` nếu output location không trỏ tới directory tồn tại; `IllegalArgumentException` nếu output location không đúng số lượng path hoặc path không được file manager hỗ trợ.

Với một output location, chỉ định **đúng một directory**. Nếu đã cấu hình output bằng `setLocationFromPaths(StandardLocation.CLASS_OUTPUT, ...)` thì không cần đồng thời truyền `-d` trong options; dùng một cơ chế nhất quán để giảm nhầm lẫn.

### Khi `ToolProvider` trả `null`

`ToolProvider.getSystemJavaCompiler()` có thể trả `null` khi runtime image không có compiler, chẳng hạn ứng dụng chạy bằng môi trường tối giản đã loại `jdk.compiler`. Đó là **lỗi môi trường ứng dụng host**, không phải lỗi cú pháp mã được biên dịch.

`java -version` chỉ cho biết JVM đang chạy; không bảo đảm `jdk.compiler` có sẵn. Khi cần Compiler API trên production, cấu hình một JDK hoặc custom runtime image có module compiler, kiểm tra trước khi nhận compile requests.

## 7. Mô hình xử lý kết quả an toàn trong dịch vụ biên dịch

Khi thiết kế một service, nên phân biệt trạng thái hệ thống và trạng thái source:

```text
REJECTED_CONFIG
    - compiler unavailable, invalid option, invalid input kind
COMPILATION_FAILED
    - call() == false; diagnostics và logs lưu theo request
COMPILED
    - call() == true; artifacts được kiểm tra rồi mới công bố
INTERNAL_FAILURE
    - runtime exception từ callback/custom component,
      I/O failure hoặc lỗi môi trường nghiêm trọng
```

Đây là **một mô hình trạng thái gợi ý**, không phải các hằng chuẩn của Java Compiler API. Có thể map sang HTTP status/error codes hoặc hệ thống job queue theo yêu cầu sản phẩm, nhưng đừng trộn compiler-source errors với lỗi máy chủ.

Gợi ý cấu trúc Java:

```java
try {
    // Kiểm tra system compiler, source, options và file locations.
    // Tạo task mới, gọi một lần.
    boolean success = Boolean.TRUE.equals(task.call());
    if (!success) {
        // Trả compilation failed, kèm diagnostics đã lọc.
    }
} catch (IllegalArgumentException invalidConfig) {
    // Cấu hình/input không hợp lệ.
} catch (IllegalStateException invalidLifecycle) {
    // Task lifecycle sai hoặc trạng thái truy cập không phù hợp.
} catch (RuntimeException unexpected) {
    // Kiểm tra cause từ custom compiler component.
} // IOException từ file manager/Files xử lý ở scope phù hợp.
```

Đây chỉ là **pseudo-structure**: không copy nguyên vào project mà thiếu biến `task`, kết quả và `catch IOException` nếu method có checked I/O. Nên phân biệt cấu hình do client cung cấp với lỗi do chính host phát sinh; exception type giống nhau có thể cần cách báo cáo khác tùy nguồn.

### Không nuốt lỗi từ `close()`

`StandardJavaFileManager` là `Closeable`. Hãy dùng try-with-resources, và nếu close ném `IOException` thì xử lý theo chính sách I/O. Nếu compile xong nhưng output chưa được flush/close đúng hoặc storage lỗi, **không vội công bố artifact** chỉ dựa trên `call() == true`. Có thể có exception từ việc đóng resources sau `call()`; đó là một phần kết quả của hoạt động end-to-end.

### Tách success khỏi artifact publishing

`call() == true` là sự thành công của **compilation task**, không phải cam kết:

- Artifact đã được upload, ký, publish hoặc triển khai thành công.
- Đầu ra không chứa warnings.
- Có đúng một class file duy nhất.
- Mọi runtime dependency đều tương thích với JVM đích.
- Mã biên dịch là an toàn hoặc không chứa hành vi độc hại.

Trong ứng dụng đáng tin cậy, tạo output vào thư mục riêng của request, xác minh nội dung và chỉ sau đó chuyển artifact sang vùng công bố. Với untrusted source, xem mục an toàn bên dưới.

## 8. Đầu ra chẩn đoán cần ghi/log ra sao?

Một cấu trúc diagnostic record tối thiểu cho UI hoặc JSON có thể chứa:

```text
severity: ERROR | WARNING | MANDATORY_WARNING | NOTE | OTHER
code: compiler-specific string
source: URI if present
line: long or NOPOS
column: long or NOPOS
message: localized text
```

Tính năng nên bổ sung:

1. **Không parse string của `getMessage()` để xác định severity.** Dùng `getKind()`.
2. **Giữ code của diagnostic** để hỗ trợ correlation, nhưng đừng coi mã nội bộ compiler là hợp đồng tương thích giữa mọi JDK.
3. **Lọc path nhạy cảm** khi trả diagnostics ra bên ngoài; đường dẫn source trên máy chủ có thể nằm trong URI.
4. **Giới hạn lượng log** và số diagnostics nếu cần; không để người dùng tạo hàng triệu lỗi làm cạn bộ nhớ.
5. **Phân biệt output kênh riêng**: diagnostics cấu trúc, additional writer output, host exception stack trace.
6. **Không tự chỉnh sửa các diagnostic sources** khi listener đang được gọi; tránh side effects khó đoán.
7. **Báo lỗi khớp invocation cụ thể**; không dùng `DiagnosticCollector` của request trước rồi gộp làm status hiện tại.
8. **Hiểu vị trí không nhất thiết tồn tại**: diagnostics lỗi option hoặc file manager có thể không gắn dòng source cụ thể.

### Tại sao không chỉ chuyển toàn bộ `System.err` thành lỗi?

Nếu `diagnosticListener` là `null`, compiler format diagnostics ra default output, thường `System.err`. Trong ứng dụng nhiều requests cùng chạy, chuyển hướng `System.err` toàn JVM là không an toàn vì gây lẫn logs của tác vụ khác. Thay vào đó, **cung cấp explicit listener/collector và Writer** cho từng task, và kiểm soát các thành phần do host sở hữu.

Compiler API cũng **không bảo đảm mọi custom annotation processor sẽ im lặng trên `System.out`/`System.err`**. Processor do bên thứ ba viết có thể in trực tiếp; nếu cần cô lập tuyệt đối logs và lỗi, thực thi trong một process riêng có kiểm soát thay vì thay `System.setErr` toàn cục.

## 9. Cấu hình classpath, module path và annotation processing

Ví dụ chính dùng `-proc:none` để tắt annotation processing, do đó chỉ kiểm tra pipeline compile. Trong dự án thực tế, options có thể gồm:

- `--class-path`/`-cp`: nơi tìm dependencies ngoài JDK.
- `--module-path`: named modules.
- `--release 17`: chọn target source, classfile version và API nền tảng Java 17.
- `-d`: output class directory.
- `-s`: generated source directory.
- `-processor`, `-processorpath`: chọn/nạp annotation processors.
- `-Xlint:...` và `-Werror`: cảnh báo và chính sách lỗi.

Các compiler options phải truyền bằng **chuỗi phần tử tách đúng**:

```java
List<String> options = List.of(
        "--release", "17",
        "-classpath", "libs/example.jar",
        "-d", "build/classes");
```

Đây là **mảnh danh sách options**, không phải chương trình biên dịch riêng. Không truyền nguyên một chuỗi `"--release 17 -d build/classes"` như một phần tử `List<String>` rồi mong compiler tự chạy shell parser. `getTask(...)` không nhận cú pháp lệnh của PowerShell/bash; nó nhận **các token option**.

### Annotation processor có thể phá task theo cách khác lỗi nguồn

Một processor do người dùng cung cấp có thể báo `Diagnostic.Kind.ERROR`, làm compile trả false theo mô hình bình thường. Nhưng một processor **ném unchecked exception** chưa được xử lý, hoặc một custom `JavaFileManager`/`DiagnosticListener` gặp lỗi runtime, có thể khiến compiler ném `RuntimeException` với cause là lỗi ở component. Cần ghi lại cause và ngăn tình trạng một processor lỗi làm hỏng toàn bộ dịch vụ host.

Để thử compile nhiều tasks theo thứ tự, dùng một file manager được hỗ trợ tái sử dụng; **đừng** gọi `CompilationTask.call()` hai lần trên cùng instance. Khi dùng nhiều requests đồng thời, mỗi request nên có riêng diagnostics, input/output location, và không dùng chung mutable buffers/path nếu chưa có bảo đảm thread safety.

## 10. Lỗi sai cấu hình thường gặp và chẩn đoán nhanh

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| `compiler == null` | Runtime image thiếu module compiler | Chạy trên JDK hoặc image chứa `jdk.compiler` |
| `IllegalArgumentException` tại `getTask` | Option không hợp lệ, compilation units không phải SOURCE | Kiểm tra token options và `JavaFileObject.Kind` |
| `IllegalStateException` gọi `call()` lần hai | Dùng lại task đã thực thi | Mỗi lần compile tạo `CompilationTask` mới |
| `call() == false`, collector có `ERROR` | Source có lỗi, thiếu dependency, vi phạm Java language rules | Đọc `getKind`, `getSource`, line/column/message |
| `call() == false` khi `-Werror` | Warning được coi là lỗi của build | Xem cả warning và compiler diagnostics |
| `call() == true` nhưng collector có `WARNING` | Warning không mặc nhiên làm compilation lỗi | Báo thành công kèm warning theo chính sách |
| `Writer` rỗng nhưng compile lỗi | Diagnostics được đưa cho `DiagnosticListener` | Dựa vào `call()` và collector |
| Compiler thất bại nhưng collector rỗng | Sự cố cấu hình/IO hoặc diagnostics không biểu diễn thành `Diagnostic` | Kiểm tra Writer và exception; không khẳng định “không lỗi” |
| `NoClassDefFoundError` / processor load thất bại | Processor path hoặc runtime thiếu dependency | Kiểm tra classpath, processor path, module graph |
| `IOException` khi set output location | Output directory chưa có/quyền ghi không hợp lệ | Tạo/kiểm tra directory trước và đóng resources |
| Biên dịch xong nhưng app không chạy | Mục tiêu runtime/classpath sai hoặc class không có `main` | Tách compilation success khỏi runtime testing |
| Log nhiều request bị lẫn | Dùng `System.err`/collector hoặc thư mục output toàn cục | Cô lập per-request resources và output |

Nếu exception xảy ra lúc tạo task, **không có một kết quả `call()` hợp lệ để tham chiếu**. Nếu exception xảy ra trong `call()`, hãy giữ nguyên stack/cause để debug host, nhưng không cố diễn giải nó thành Java syntax error khi không có căn cứ.

## 11. Kiểm thử các trường hợp cần có trong hệ thống Compiler API

Một bộ test cơ bản:

1. **Source hợp lệ:** `call()==true`, không có `ERROR`, class output xuất hiện đúng vị trí.
2. **Source syntax/type sai:** `call()==false`, collector chứa ít nhất một `ERROR`, location có thể xác định.
3. **Warning không bật `-Werror`:** compilation có thể thành công, warning vẫn được báo.
4. **Warning với `-Werror`:** build fail theo cấu hình; không dựa vào số cảnh báo cụ thể giữa các versions.
5. **Option bất hợp lệ:** xác nhận xử lý `IllegalArgumentException` hoặc kênh thông báo compiler phù hợp.
6. **Compiler không hiện diện:** host trả trạng thái cấu hình thay vì `NullPointerException`.
7. **Output location không tồn tại hoặc không ghi được:** I/O được báo tách khỏi lỗi source.
8. **Gọi `call()` hai lần:** xác nhận `IllegalStateException`; sửa bằng cách tạo task mới.
9. **Custom listener/file manager throw:** không mất cause; application không nhầm thành `call()==false`.
10. **Nhiều requests:** diagnostics và Writer không lẫn nhau; output directories tách biệt.
11. **Task tạo artifacts nhưng fail:** không công bố output của một compilation chưa thành công.
12. **Target JDK khác:** chạy test với Java 17, 21 khi dự án yêu cầu; option/diagnostic text có thể khác.

Đặc biệt, test **case lỗi nguồn** và **case lỗi cấu hình** riêng biệt. Nếu chỉ kiểm thử các source lỗi cú pháp thì code host có thể không xử lý được exception ở `getTask`; nếu chỉ kiểm thử option sai thì không chứng minh collector hoạt động đúng.

## 12. An toàn khi biên dịch mã không tin cậy

**Biên dịch nguồn Java không tin cậy trong cùng JVM với service host là một quyết định bảo mật lớn.** Compiler task có thể đọc files phù hợp với quyền process, annotation processors/plugins có thể thực thi mã Java ở compile time, và `JavaFileManager` hoặc compiler components tùy biến có thể truy cập tài nguyên host.

Nếu ứng dụng nhận source từ người dùng:

- Không dựa vào `-proc:none` như một **sandbox toàn diện**; nó chỉ tắt annotation processing, không giải quyết mọi rủi ro khác.
- Ưu tiên process/container riêng bị giới hạn CPU, memory, disk, network và quyền filesystem, được tạo mới cho từng job hoặc được cô lập đúng mức.
- Không cho người dùng chọn bừa classpath, processor path hoặc arbitrary compiler options trong môi trường chứa dữ liệu bí mật.
- Kiểm soát file name/path, chống path traversal và tránh ghi vào output directory dùng chung.
- Cân nhắc timeout và giám sát tài nguyên ở tầng điều phối; `CompilationTask.call()` **không** tự cung cấp API timeout chuẩn để ngắt compile đang chạy an toàn theo một lời gọi.
- Nếu cần chạy bytecode vừa compile, **cô lập runtime riêng**; một lần compile thành công không chứng minh bytecode an toàn để chạy trong process host.

Điều này liên quan trực tiếp đến cách xử lý lỗi: khi process/container hết tài nguyên hoặc bị kill, trạng thái phải được ghi là **infrastructure failure**, không bịa một `Diagnostic.Kind.ERROR` tương ứng với mã nguồn.

## 13. Checklist khi gọi Compiler API

- [ ] Đã kiểm tra `ToolProvider.getSystemJavaCompiler() != null`?
- [ ] Mỗi request có riêng `CompilationTask`, chỉ gọi `call()` đúng một lần?
- [ ] Đã xử lý đúng `Boolean.TRUE.equals(task.call())` thay vì suy ra từ exception?
- [ ] Đã cấp `DiagnosticListener` hoặc `DiagnosticCollector` để lấy lỗi/warning có cấu trúc?
- [ ] Đã giữ `Writer` cho additional compiler output và không nhầm nó với collector?
- [ ] Đã kiểm tra null `Diagnostic.getSource()` và `Diagnostic.NOPOS`?
- [ ] Đã truyền options thành từng token, biết rõ option nào được hỗ trợ?
- [ ] Đã xác định `compilationUnits` là các `JavaFileObject.Kind.SOURCE`?
- [ ] Đã chuẩn bị output location trước khi dùng `StandardJavaFileManager`?
- [ ] Đã đóng file manager bằng try-with-resources và xử lý I/O?
- [ ] Đã phân biệt source errors, invalid configuration, callback exceptions và lỗi runtime JVM?
- [ ] Đã kiểm tra output, tránh công bố file còn sót từ một task thất bại?
- [ ] Đã dùng đúng compiler/runtime versions và cấu hình classpath/module path?
- [ ] Với untrusted source, đã cô lập hoạt động compile/runtime khỏi JVM host?

**Kết luận:** `CompilationTask.call()` là **tín hiệu thành công/thất bại của quá trình biên dịch**, `DiagnosticCollector` cung cấp **chẩn đoán có cấu trúc**, `Writer` giữ **đầu ra bổ sung**, còn ngoại lệ biểu hiện những **lỗi ở pha thiết lập hoặc thành phần thực thi** không thể đơn giản quy thành lỗi cú pháp nguồn. Hãy xử lý từng kênh theo hợp đồng API, đóng file manager, kiểm tra artifact và thiết kế trạng thái lỗi riêng cho application host.

## Tài liệu tham khảo chính thức

- Java SE 17, `JavaCompiler` và `getTask(...)`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html
- Java SE 17, `JavaCompiler.CompilationTask` và `call()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.CompilationTask.html
- Java SE 17, `DiagnosticCollector`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/DiagnosticCollector.html
- Java SE 17, `Diagnostic` và `Diagnostic.Kind`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/Diagnostic.html
- Java SE 17, `ToolProvider`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html
- Java SE 17, `StandardJavaFileManager`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html
- Oracle JDK 17, *The javac Command*: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
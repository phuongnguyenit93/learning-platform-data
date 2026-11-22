# `JavaCompiler.CompilationTask` và kết quả biên dịch trong Java

## 1. Học gì từ một tác vụ biên dịch?

Java có API biên dịch chương trình ngay trong một ứng dụng Java, đặt trong package `javax.tools` của module chuẩn `java.compiler`. API này hữu ích khi xây dựng trình kiểm tra mã, IDE, công cụ sinh mã, bộ kiểm thử mã do người dùng nhập hoặc hệ thống build tùy biến. Nó vẫn là API **hiện hành trong Java 17+**.

Cần phân biệt rõ ba bước:

1. **Tạo tác vụ** bằng `JavaCompiler.getTask(...)`: xác định source, options, file manager và nơi nhận chẩn đoán. Tác vụ chưa thực thi biên dịch.
2. **Chạy tác vụ** bằng `JavaCompiler.CompilationTask.call()`: thực sự chạy compiler và thu về `Boolean` cho biết biên dịch có lỗi hay không.
3. **Đọc kết quả chi tiết** qua `DiagnosticCollector` hoặc `DiagnosticListener`, cùng sản phẩm đầu ra (`.class` hoặc artifact tùy file manager). `Boolean` không chứa thông báo lỗi, vị trí lỗi hay nội dung các class sinh ra.

Ví dụ: JavaCompiler có thể nhận source trong bộ nhớ thông qua `JavaFileObject`, kiểm tra nó, trả `false` nếu source sai kiểu, và cung cấp một diagnostic có `Kind.ERROR`. Không phải gọi một tiến trình `javac` bằng `ProcessBuilder` mới làm được điều này.

### Các kiểu cần nhớ

| API | Vai trò |
| --- | --- |
| `ToolProvider.getSystemJavaCompiler()` | Lấy compiler do runtime cung cấp; có thể trả `null` khi runtime không có compiler |
| `JavaCompiler` | Factory tạo tác vụ biên dịch và file manager |
| `JavaCompiler.CompilationTask` | Một tác vụ biên dịch **chỉ chạy một lần** |
| `JavaFileObject` | Đại diện source Java hoặc sản phẩm compiler |
| `StandardJavaFileManager` | Quản lý source/output thường nằm trên filesystem và các vị trí như classpath |
| `DiagnosticListener` | Nhận sự kiện lỗi, cảnh báo, ghi chú từ compiler |
| `DiagnosticCollector` | Implementation của listener lưu lại danh sách `Diagnostic` |
| `Diagnostic` | Mức độ, file nguồn, vị trí và thông báo lỗi/cảnh báo |

**Điểm mấu chốt:** `CompilationTask` là công việc biên dịch đang chờ chạy, **không phải đối tượng chứa kết quả sau biên dịch**. Giá trị trả về của `call()` và các diagnostics là hai đầu ra khác nhau, có nhiệm vụ bổ sung cho nhau.

## 2. Tạo `CompilationTask`: chính xác sáu tham số của `getTask`

Chữ ký API:

~~~java
JavaCompiler.CompilationTask getTask(
    Writer out,
    JavaFileManager fileManager,
    DiagnosticListener<? super JavaFileObject> diagnosticListener,
    Iterable<String> options,
    Iterable<String> classes,
    Iterable<? extends JavaFileObject> compilationUnits
);
~~~

Đây là **chữ ký phương thức minh họa trong interface `JavaCompiler`**, không phải chương trình chạy độc lập.

| Tham số | Ý nghĩa và cách sử dụng |
| --- | --- |
| `out` | `Writer` nhận các đầu ra không được biểu diễn thành diagnostic; nếu `null`, compiler mặc định ghi ra `System.err` |
| `fileManager` | Cách compiler tìm source, dependency và ghi output. Với ứng dụng thông thường, dùng `compiler.getStandardFileManager(...)` và đóng khi xong |
| `diagnosticListener` | Nơi nhận các lỗi/cảnh báo cấu trúc; dùng `DiagnosticCollector<JavaFileObject>` nếu muốn đọc sau khi chạy. Nếu `null`, compiler sử dụng cách báo lỗi mặc định |
| `options` | Các option như `--release`, `-d`, `--class-path`, `--module-path`, `-proc:none`; thường dùng `List.of(...)`; `null` nghĩa là không truyền option |
| `classes` | **Tên class cần đưa vào annotation processing**, không phải source code thông thường hay danh sách file phải biên dịch; với biên dịch source bình thường, truyền `null` |
| `compilationUnits` | Danh sách `JavaFileObject` loại `SOURCE` đại diện cho các đơn vị source cần biên dịch |

Ví dụ tạo tác vụ sau khi đã chuẩn bị `compiler`, `fileManager`, `diagnostics`, `sourceFiles` và `outputDir`:

~~~java
JavaCompiler.CompilationTask task = compiler.getTask(
    null,
    fileManager,
    diagnostics,
    List.of("--release", "17", "-proc:none", "-d", outputDir.toString()),
    null,
    sourceFiles
);
~~~

Đây là **mã ghép vào ngữ cảnh**, các biến nói trên phải được khai báo trước. Ý nghĩa từng option:

- `--release 17`: biên dịch theo bộ API và ngôn ngữ hướng đến Java 17; có thể dùng khi chạy compiler JDK 17 hoặc mới hơn có hỗ trợ release này. Đừng dùng riêng `-source` mà quên tính tương thích API của thư viện.
- `-d <dir>`: đặt thư mục chứa output `.class`. Thư mục cần được chuẩn bị trước; ví dụ đầy đủ sẽ tự tạo thư mục tạm.
- `-proc:none`: không chạy annotation processors được phát hiện trong quá trình biên dịch. Ví dụ sử dụng điều này để tập trung vào kiểm tra Java thông thường. Nếu ứng dụng thực sự cần generate code qua annotation processing, hãy cấu hình xử lý riêng và có chủ đích.
- `--class-path`, `--module-path` hoặc cấu hình `StandardJavaFileManager`: cần khi source phụ thuộc thư viện/module không có sẵn. Không được cho rằng `getTask` tự tải dependency từ Internet.

`getTask(...)` chỉ trả về tác vụ chưa chạy. Các thiết lập tùy chọn như `task.setLocale(...)`, `task.setProcessors(...)` và `task.addModules(...)` (khi áp dụng) cần được thực hiện **trước** `call()`; các thiết lập này không hợp lệ khi tác vụ đã bắt đầu.

## 3. Chạy `call()` và hiểu đúng `Boolean`

~~~java
Boolean result = task.call();
boolean compiledWithoutErrors = Boolean.TRUE.equals(result);
~~~

Đây là đoạn dùng khi đã có `task`. Theo hợp đồng `CompilationTask.call()`:

- Trả về `true` **khi và chỉ khi các source được biên dịch mà không có lỗi**.
- Trả về `false` khi quá trình biên dịch báo lỗi, chẳng hạn cú pháp sai hoặc một biểu thức không tương thích kiểu. Một số warning có thể xuất hiện khi kết quả vẫn `true`.
- **Chỉ được gọi một lần trên mỗi `CompilationTask`.** Gọi `task.call()` lần thứ hai sẽ ném `IllegalStateException`, cho dù lần đầu thành công hay thất bại. Muốn biên dịch tiếp, hãy tạo **tác vụ mới** từ `getTask(...)`.
- `call()` có thể ném `RuntimeException` khi có lỗi không thể phục hồi trong thành phần do ứng dụng cung cấp (ví dụ listener hoặc file manager tự viết); đây không phải lỗi source thông thường được mã hóa thành `false`.
- `getTask(...)` có thể ném `IllegalArgumentException` với option không hợp lệ hoặc `compilationUnits` không phải source. Đó là lỗi cấu hình đầu vào, không phải một diagnostic của Java source.

**`true` không đồng nghĩa chương trình đã chạy thành công.** Nó chỉ nói rằng compiler biên dịch source không có lỗi. Không có phương thức `main`, sai điều kiện nghiệp vụ, lỗi khi chạy, sự cố truy cập tài nguyên hoặc thiếu dependency lúc runtime vẫn có thể xảy ra sau đó.

**`false` không bảo đảm thư mục output hoàn toàn rỗng.** Khi biên dịch nhiều đơn vị, compiler có thể đã ghi một số output trước khi phát hiện lỗi ở đơn vị khác; thư mục output cũ cũng có thể chứa class từ lần biên dịch trước. Hãy coi `false` là trạng thái **không được phép phát hành hoặc nạp** tập output của lần build đó. Dùng thư mục riêng cho mỗi lượt hoặc dọn output theo chiến lược build đáng tin cậy.

### Một `CompilationTask` khác gì chạy lệnh `javac`?

| Hình thức | Kết quả chính | Cách lấy diagnostic |
| --- | --- | --- |
| `CompilationTask.call()` | `Boolean` của tác vụ | `DiagnosticListener`/`DiagnosticCollector` |
| `JavaCompiler.run(...)` (Tool API) | Mã trả về dạng `int` | Các stream của công cụ |
| CLI `javac ...` | Exit code của process | Terminal stdout/stderr hoặc các option của `javac` |

Đừng áp dụng công thức `exitCode == 0` cho `CompilationTask.call()`: API này trả `Boolean`, không trả `int`.

## 4. `DiagnosticCollector`: lấy nguyên nhân và vị trí lỗi

Tạo collector và dùng nó làm `diagnosticListener`:

~~~java
DiagnosticCollector<JavaFileObject> diagnostics =
        new DiagnosticCollector<>();

try (StandardJavaFileManager fileManager =
        compiler.getStandardFileManager(
                diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
    // Tạo task với cùng diagnostics và fileManager, sau đó gọi task.call().
}
~~~

Đây là **đoạn minh họa trong method đã có biến `compiler`**, cần các import trong chương trình hoàn chỉnh ở phần 5. `StandardJavaFileManager` triển khai `Closeable` nên dùng try-with-resources.

Sau `call()`, lặp danh sách:

~~~java
for (Diagnostic<? extends JavaFileObject> diagnostic
        : diagnostics.getDiagnostics()) {
    String file = diagnostic.getSource() == null
            ? "<unknown>"
            : diagnostic.getSource().getName();

    System.out.printf("%s:%d:%d %s: %s%n",
            file,
            diagnostic.getLineNumber(),
            diagnostic.getColumnNumber(),
            diagnostic.getKind(),
            diagnostic.getMessage(Locale.ROOT));
}
~~~

Đây là **đoạn ghép vào ngữ cảnh `diagnostics`**, không phải chương trình độc lập.

Một `Diagnostic` có những thông tin thiết yếu:

- `getKind()`: loại diagnostic. `ERROR` là lỗi, `WARNING`/`MANDATORY_WARNING` là cảnh báo, `NOTE` là ghi chú; còn có `OTHER`.
- `getSource()`: `JavaFileObject` liên quan đến lỗi; **có thể là `null`** cho một số diagnostic không gắn với file.
- `getLineNumber()` và `getColumnNumber()`: đánh số từ **1**, hoặc `Diagnostic.NOPOS` khi không có vị trí. Không giả định mọi diagnostic đều có dòng/cột.
- `getMessage(Locale)`: mô tả chi tiết; wording có thể phụ thuộc **JDK/compiler và locale**, không nên snapshot chuỗi này trong test xuyên phiên bản.
- `getCode()`: mã lỗi, **phụ thuộc implementation** và có thể `null`; hữu ích khi debug compiler cụ thể, không phải định danh lỗi portable giữa mọi compiler.

**Đừng trộn `status` và số diagnostic:** `true` không nhất thiết đồng nghĩa diagnostics trống, vì còn warning/note. Một lỗi source có thể tạo nhiều thông báo `ERROR` liên quan; số lượng và nội dung thông báo không nên hardcode khi kiểm tra trên nhiều phiên bản JDK. Nếu chỉ cần biết có lỗi hay không, dùng `diagnostics.getDiagnostics().stream().anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR)`.

## 5. Chương trình Java 17+ hoàn chỉnh: biên dịch source trong bộ nhớ

Ví dụ dưới đây tự chứa một chương trình Java, tạo **hai tác vụ khác nhau**: source hợp lệ và source lỗi kiểu. Nó quan sát `call()`, diagnostic và việc gọi task lần thứ hai bị chặn. Mã nguồn cần kiểm tra nằm trong bộ nhớ thông qua `SimpleJavaFileObject`; các file `.class` được ghi vào thư mục tạm và được dọn sau thử nghiệm.

Tạo tệp **`CompilationTaskDemo.java`**:

~~~java
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.stream.Stream;

import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class CompilationTaskDemo {
    // Một source .java được tạo từ chuỗi, không cần tệp .java trên đĩa.
    private static final class StringSource extends SimpleJavaFileObject {
        private final String text;

        StringSource(String className, String text) {
            super(URI.create("string:///"
                    + className.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.text = text;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return text;
        }
    }

    private record Result(boolean success, long errors,
                          boolean secondCallRejected) {}

    private static Result compile(JavaCompiler compiler,
                                  Path outputDir,
                                  String className,
                                  String sourceText) throws IOException {
        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
                compiler.getStandardFileManager(
                        diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {

            JavaFileObject unit = new StringSource(className, sourceText);

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null,
                    manager,
                    diagnostics,
                    List.of("--release", "17",
                            "-proc:none", "-d", outputDir.toString()),
                    null,
                    List.of(unit));

            Boolean success = task.call();

            // Task là one-shot: gọi lại phải báo IllegalStateException.
            boolean secondCallRejected;
            try {
                task.call();
                secondCallRejected = false;
            } catch (IllegalStateException expected) {
                secondCallRejected = true;
            }

            long errorCount = diagnostics.getDiagnostics().stream()
                    .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
                    .count();

            return new Result(Boolean.TRUE.equals(success),
                              errorCount, secondCallRejected);
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "This runtime does not include the Java compiler");
        }

        Path outputDir = Files.createTempDirectory("task-demo-");
        try {
            String valid = "public class Good {"
                    + " public static int answer() { return 42; }"
                    + " }";
            Result good = compile(compiler, outputDir, "Good", valid);

            System.out.println("Good compiled: " + good.success());
            System.out.println("Good errors: " + good.errors());
            System.out.println("Good.class exists: "
                    + Files.isRegularFile(outputDir.resolve("Good.class")));
            System.out.println("Good task called twice: "
                    + good.secondCallRejected());

            String invalid = "public class Broken {"
                    + " public static int answer() { return \"wrong\"; }"
                    + " }";
            Result broken = compile(compiler, outputDir, "Broken", invalid);

            System.out.println("Broken compiled: " + broken.success());
            System.out.println("Broken has errors: " + (broken.errors() > 0));
            System.out.println("Broken task called twice: "
                    + broken.secondCallRejected());
        } finally {
            // Đóng stream đi bộ cây trước khi xóa để tương thích Windows.
            List<Path> paths;
            try (Stream<Path> walk = Files.walk(outputDir)) {
                paths = walk.sorted(Comparator.reverseOrder()).toList();
            }
            for (Path path : paths) {
                Files.deleteIfExists(path);
            }
        }
    }
}
~~~

Chạy trong thư mục chứa tệp bằng **JDK 17+ có module `jdk.compiler`**:

~~~bash
javac CompilationTaskDemo.java
java CompilationTaskDemo
~~~

Stdout của chương trình với JDK chuẩn hỗ trợ Java 17:

~~~text
Good compiled: true
Good errors: 0
Good.class exists: true
Good task called twice: true
Broken compiled: false
Broken has errors: true
Broken task called twice: true
~~~

Ở đây hai dòng `task called twice: true` có nghĩa là lần gọi thứ hai **đã bị từ chối đúng hợp đồng**, không phải đã biên dịch lại. Diagnostic chi tiết của `Broken` được collector giữ, nhưng chương trình chỉ in việc **có ít nhất một lỗi** để tránh phụ thuộc thông báo và số lượng lỗi cụ thể theo compiler/JDK.

**Giải thích cơ chế:**

1. `StringSource` là `JavaFileObject` có `Kind.SOURCE`, URI đuôi `.java` và nội dung trả về từ `getCharContent(...)`. Đây là cách chuẩn để đưa source dạng chuỗi vào compiler mà không phải tạo file `Good.java`/`Broken.java`.
2. `compile(...)` tạo **collector và manager riêng** cho mỗi lượt; vì vậy diagnostics của lượt tốt không lẫn với lượt lỗi.
3. `getTask(...)` tạo đối tượng chưa chạy. Chỉ `call()` mới khởi động biên dịch và có thể tạo output.
4. Source `Good` hợp lệ và output được ghi vào `Good.class` trong thư mục tạm. Source `Broken` cố trả `String` từ method khai báo `int`, tạo ít nhất một `Kind.ERROR`; `call()` trả `false`.
5. Trong cả hai trường hợp, gọi lại cùng task sẽ bị từ chối. Muốn chạy lượt tiếp theo, chương trình tạo `CompilationTask` mới.
6. `StandardJavaFileManager` đóng theo try-with-resources; file `.class` tạm được xóa ở `finally`. Ví dụ chỉ **biên dịch**, không nạp hoặc chạy `Good.class`.

### Nếu muốn log diagnostic thực tế

Thay vì chỉ đếm error, tại nơi đã có `diagnostics`, có thể log:

~~~java
for (Diagnostic<? extends JavaFileObject> d : diagnostics.getDiagnostics()) {
    if (d.getKind() == Diagnostic.Kind.ERROR) {
        String name = d.getSource() == null
                ? "<unknown>" : d.getSource().getName();
        System.err.printf("%s:%d:%d: %s%n",
                name, d.getLineNumber(), d.getColumnNumber(),
                d.getMessage(Locale.ROOT));
    }
}
~~~

Đoạn này là **minh họa đặt bên trong phương thức `compile` trước khi thoát try-with-resources**; nếu thêm vào chương trình ở trên, stderr sẽ có thông báo lỗi của compiler, còn stdout mô tả ở trên không đổi. Đừng hardcode chính văn diagnostic cho mọi phiên bản JDK.

## 6. Khi chạy nhiều tác vụ: kết quả, file manager, processor

### Tạo task mới mỗi lượt

Mỗi `CompilationTask` là **one-shot**. Muốn biên dịch một project sau khi source thay đổi, lấy một tác vụ mới. `JavaCompiler` có thể được dùng để tạo nhiều task tuần tự. `StandardJavaFileManager` có thể tái sử dụng giữa các task (đôi khi tiết kiệm đọc lại JAR), nhưng việc tái sử dụng file manager không làm task cũ được gọi lại. Hãy đóng file manager khi owner không còn dùng và kiểm soát đồng thời nếu chia sẻ giữa các thread.

### Quản lý đầu ra như một build có trạng thái

Không dùng `call() == true` làm bằng chứng duy nhất rằng tất cả class files đúng nơi hoặc đang là bản mới nhất. Kiểm tra thư mục output, quản lý output sạch cho từng build, phân biệt lỗi compiler với lỗi ghi file và chỉ xuất bản artifact khi toàn bộ các bước cần thiết đều thành công.

Ví dụ với nhiều source, nếu một unit lỗi và unit khác đã có class output, `call()` vẫn là `false` cho cả task. Đừng lấy class còn nằm trên đĩa làm dấu hiệu “build thành công”.

### Diagnostic và exception khác nhau

- **Lỗi source** thường được trả dưới dạng diagnostic `ERROR` và `call() == false`.
- **Option/configuration sai** có thể làm `getTask(...)` ném `IllegalArgumentException` trước khi compile.
- **Thành phần tùy biến của ứng dụng bị lỗi nặng** (file manager, listener, custom `JavaFileObject`) có thể gây `RuntimeException`.
- **Không có compiler**: `ToolProvider.getSystemJavaCompiler()` có thể trả `null`, thường do chạy trên runtime image không bao gồm `jdk.compiler`. Khi đó phải dùng JDK/runtime có compiler hoặc cung cấp toolchain thích hợp.

### Annotation processing có thể thay đổi kết quả

Annotation processor có thể phát sinh source/class, cảnh báo hoặc lỗi trong cùng task. Nếu muốn chạy processor do ứng dụng quản lý, cần cấu hình processors, paths và options có chủ đích. `task.setProcessors(...)` phải gọi **trước** `call()`; không thể thay processor trên một task đã chạy. Ví dụ dùng `-proc:none` nên không chạy processor, giúp minh họa kết quả lõi.

Không biên dịch source không tin cậy như thể đó là sandbox bảo mật: một pipeline có processor hoặc công cụ tích hợp có thể thực thi code ở giai đoạn build. Muốn cô lập quá trình build/runtime cần thiết kế isolation riêng, không dựa vào việc `CompilationTask` trả `Boolean`.

### Module và classpath

Chương trình ví dụ chạy trên **classpath** để dễ thử bằng `javac` và `java`. Với code ứng dụng chạy trong một **named module**, khai báo `requires java.compiler;` để dùng `javax.tools`. Đảm bảo runtime image có module triển khai compiler (`jdk.compiler`) nếu cần gọi `getSystemJavaCompiler()`. Khi biên dịch source modular, cân nhắc `--module-path`, `--module-source-path`, `--module` và file manager locations tương ứng; đặt option theo cấu trúc project và toolchain thực tế.

## 7. Lỗi thường gặp

| Nhầm lẫn | Thực tế |
| --- | --- |
| “`getTask` đã compile” | `getTask` tạo task; `call` mới thực thi |
| “`call()` trả exit code” | `CompilationTask.call()` trả `Boolean`; exit code thuộc CLI hoặc `Tool.run` |
| “`true` nghĩa là không có warning” | Warning/note vẫn có thể tồn tại khi compiler không có lỗi |
| “`false` nghĩa là không có file output” | Output có thể sinh một phần hoặc còn từ build trước |
| “Gọi `call` lại để compile lần hai” | Task chỉ chạy một lần, gọi lại ném `IllegalStateException` |
| “`classes` là danh sách file `.java`” | `classes` dành cho tên class được xử lý bởi annotation processing; source nằm ở `compilationUnits` |
| “Đọc chi tiết lỗi từ `Boolean`” | Dùng `DiagnosticListener`/`DiagnosticCollector` |
| “Diagnostic luôn có file/dòng/cột” | `getSource()` có thể `null`; position có thể `NOPOS` |
| “Thông báo lỗi giống nhau trên mọi JDK” | `getMessage` và `getCode` phụ thuộc compiler/locale |
| “Đóng `CompilationTask`” | Task không có lifecycle close; đóng **file manager** và các resource do ứng dụng sở hữu |

## 8. Câu hỏi tự kiểm tra

1. **Tạo task với `getTask` rồi chưa gọi `call` có file `.class` chưa?** Không thể giả định có output do task đó; compiler chưa chạy.
2. **`call` trả `false` nhưng chỉ thấy một vài `.class` thì build thành công chưa?** Chưa; kết quả task báo biên dịch có lỗi.
3. **Muốn biết source lỗi ở dòng nào?** Lấy các `Diagnostic` từ collector và đọc `getLineNumber()`, `getColumnNumber()` nếu khác `NOPOS`.
4. **Muốn biên dịch lại một source khác?** Tạo `CompilationTask` mới; không gọi lại task cũ.
5. **Tại sao `getSystemJavaCompiler()` trả null trên một runtime tùy chỉnh?** Compiler implementation, thường là module `jdk.compiler`, có thể không nằm trong runtime image.
6. **`call() == true` đã kiểm thử logic nghiệp vụ chưa?** Chưa; biên dịch thành công không thay thế chạy unit tests và kiểm thử thực thi.
7. **Làm sao tránh log lỗi phụ thuộc ngôn ngữ/JDK khi viết test?** Kiểm tra `Kind.ERROR`, kết quả task và những thuộc tính được contract bảo đảm; tránh so sánh nguyên văn `getMessage(Locale)`.

## 9. Nguồn tham khảo chính thức, còn hiệu lực

- [Java SE 25 — `JavaCompiler`](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/JavaCompiler.html): chữ ký `getTask`, file manager, các tham số.
- [Java SE 25 — `JavaCompiler.CompilationTask`](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/JavaCompiler.CompilationTask.html): `call()` trả `Boolean`, chạy một lần, `setProcessors`, `setLocale`, `addModules`.
- [Java SE 25 — `Diagnostic`](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/Diagnostic.html): loại diagnostic, vị trí và thông điệp.
- [Java SE 25 — `DiagnosticCollector`](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/DiagnosticCollector.html): thu thập diagnostics.
- [Java SE 25 — `ToolProvider`](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/ToolProvider.html): lấy system compiler và trường hợp trả `null`.

Tư duy đúng khi dùng API: **`getTask` chuẩn bị → `call` thực thi đúng một lần → `Boolean` nói trạng thái biên dịch → `DiagnosticCollector` giải thích lỗi/cảnh báo → file manager quản lý các output.**
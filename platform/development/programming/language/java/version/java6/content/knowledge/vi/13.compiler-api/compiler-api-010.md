# Giới hạn tin cậy khi đầu vào biên dịch do bên ngoài cung cấp — Java Compiler API

## 1. Vấn đề: biên dịch mã không đồng nghĩa xử lý dữ liệu thông thường

Ứng dụng Java có thể nhận mã nguồn từ biểu mẫu trực tuyến, plugin, hệ thống chấm bài, tác vụ do khách hàng gửi hoặc repository bên ngoài, rồi gọi `javax.tools.JavaCompiler` để kiểm tra hoặc tạo file `.class`. Khi nguồn được bên ngoài cung cấp, ứng dụng đang xử lý một **đầu vào không tin cậy**. Ranh giới tin cậy bao gồm nhiều thứ hơn chuỗi Java source:

- **Source code:** cú pháp, số lượng file, kích thước, độ phức tạp, đường dẫn/tên lớp; có thể gây quá tải compiler hoặc khai thác lỗi compiler.
- **Compiler options:** `-proc:...`, `-processor`, `-Xplugin:...`, `--class-path`, `--module-path`, `-d`, `-s` và những lựa chọn khác làm thay đổi nơi compiler đọc/ghi hoặc code mở rộng nào được gọi.
- **Dependencies và build extensions:** JAR/processor/plugin bên thứ ba có thể chứa bytecode thực thi trong **quá trình build**, không cần chờ chạy class mới biên dịch.
- **File manager, diagnostic listener và những callback tự viết:** thành phần ứng dụng gọi từ compiler phải được thiết kế và kiểm tra như code có quyền của process.
- **Output và log:** file `.class` là bytecode có thể thực thi về sau; diagnostic/file name/message có thể mang văn bản do bên ngoài kiểm soát.

Đây là bài học về **ranh giới tin cậy**, không phải cách biến `JavaCompiler` thành sandbox. API của Java không cam kết cô lập source do bên ngoài gửi khỏi quyền của tiến trình biên dịch.

Phân biệt ba hành vi:

1. **Phân tích/biên dịch source thông thường:** compiler đọc và phân tích văn bản Java, phát sinh bytecode. Chỉ có code `static { ... }` trong source **không làm initializer đó chạy ngay khi javac biên dịch**.
2. **Thực thi code khi build:** annotation processor hoặc plugin của compiler, nếu được bật và tải từ classpath/module path, có thể **chạy code Java ngay trong tiến trình compiler**. Đây là rủi ro cần chặn tại ranh giới.
3. **Thực thi artifact về sau:** khi ứng dụng nạp/khởi tạo/chạy class đã tạo, **code của người gửi thực thi**. Việc `CompilationTask.call()` trả `true` không làm bytecode trở nên an toàn.

Cách bảo vệ thích hợp tùy mức tin cậy: code từ repository đã kiểm duyệt khác với code do người dùng Internet gửi. Với đối tượng không tin cậy thực sự, việc giới hạn options vẫn chưa thay thế **cách ly ở mức hệ điều hành**.

## 2. Biên dịch trong tiến trình: lợi ích và giới hạn

Luồng gọi thường thấy:

~~~java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
JavaCompiler.CompilationTask task =
        compiler.getTask(null, fileManager, diagnostics, options, null, sources);
Boolean success = task.call();
~~~

Đây là **đoạn ghép vào chương trình đã khai báo các biến**; không chạy độc lập. `ToolProvider` thuộc `javax.tools`.

`getTask(...)` tạo tác vụ; `call()` bắt đầu biên dịch và trả về `Boolean` thể hiện **không có lỗi biên dịch**. Khi dùng system compiler qua `JavaCompiler` trong ứng dụng, công việc compiler chạy trong **cùng JVM/process với ứng dụng gọi API**. API không cấp thêm một vùng bảo mật hay mức quyền thấp hơn cho `task.call()`.

Hệ quả của in-process compilation:

- Compiler tiêu thụ **CPU, heap, metaspace và tài nguyên của process**. Source lớn hoặc có cấu trúc phức tạp có thể gây tiêu tốn tài nguyên, kể cả khi không có processor.
- Một lỗi nghiêm trọng trong compiler hoặc library/compiler extension có thể ảnh hưởng ứng dụng đang phục vụ các request khác.
- Nếu ứng dụng cho phép gắn annotation processor, javac plugin hoặc callback tùy biến đến từ nguồn không tin cậy, code đó có thể thực thi với quyền process.
- `Future.cancel(true)` hoặc `Thread.interrupt()` không phải cơ chế đáng tin để dừng mọi công việc compiler/extension đã chạy. Không thiết kế timeout như thể nó có thể buộc dừng an toàn một compilation bị treo trong cùng JVM.
- `StandardJavaFileManager` phải được đóng sau khi dùng; không đưa đường dẫn của file manager hoặc output từ request của user vào thẳng cấu hình mà không kiểm soát.

**Nguyên tắc:** Nếu nguồn đến từ bên ngoài nhưng đã qua một quy trình xét duyệt tin cậy, in-process compilation có thể là lựa chọn hiệu quả. Nếu hệ thống phải nhận **source tùy ý từ người không tin cậy**, hãy xem compiler như một workload cần cách ly; chạy trong một worker/process riêng có giới hạn hệ điều hành, không nhúng trực tiếp vào JVM chứa dữ liệu/credential quan trọng.

### Không thể dựa vào `SecurityManager`

Trên **JDK 24+**, Java Security Manager đã bị **vô hiệu hóa vĩnh viễn** (JEP 486). Không dùng `SecurityManager` hoặc `java.policy` như giải pháp sandbox cho compiler. Trên Java hiện đại, ranh giới thực thi cần dựa vào **OS/container/VM isolation, quyền process, file/network permissions, resource limits**. Một class loader riêng hoặc JPMS module boundaries cũng **không tự tạo sandbox quyền hệ điều hành**.

## 3. Những đầu vào nào được phép đi qua biên?

| Dữ liệu từ request | Rủi ro nếu chuyển thẳng | Cách kiểm soát có hiệu quả |
| --- | --- | --- |
| Source text | Source rất lớn/phức tạp, compiler bị quá tải; có thể dùng API tùy ý nếu class được thực thi về sau | Giới hạn byte/ký tự, file count, timeout thực thi ở process riêng; không nạp/chạy artifact tùy tiện |
| Tên file, package, class | Path traversal, trùng tệp, ghi nhầm vị trí hoặc diagnostic chứa đường dẫn nhạy cảm | Tên được ứng dụng xác định/kiểm tra; ghép với thư mục job riêng; không tin đường dẫn tuyệt đối của request |
| Danh sách `javac` options | Bật processor/plugin; đổi classpath/output; truy cập file ngoài phạm vi | **Ứng dụng tạo options cố định từ allowlist**, người dùng không truyền một chuỗi command hoặc list options bất kỳ |
| Classpath/module path | Tải dependency, processor hoặc plugin khác dự kiến | Chỉ dùng artifact trusted/pinned; tạo đường dẫn/địa điểm tìm class riêng cho job; không ghép classpath server tùy tiện |
| Annotation processors | Có thể chạy code khi compile, sinh source và file tùy ý với quyền JVM | Tắt với `-proc:none` nếu không cần; nếu bắt buộc dùng processor, chỉ chạy processor trusted trong worker cách ly |
| Javac plugin `-Xplugin:...` | Plugin có thể chạy code ở compiler | Không nhận option từ user; không đăng ký plugin không tin cậy |
| Output `.class` / JAR | Bytecode không an toàn khi load/chạy; có thể chứa logic ngoài mong đợi | Lưu vùng tạm riêng, giới hạn dung lượng; chỉ phát hành sau các bước kiểm tra; chạy test/bytecode trong môi trường cách ly |
| Diagnostic/error text | Lộ đường dẫn, log injection, XSS khi render trực tiếp, output quá lớn | Giới hạn số dòng/độ dài, mã hóa khi hiển thị HTML, tránh trả absolute path/secret, không dùng diagnostic như nội dung tin cậy |

### Cẩn trọng với `-proc:none` và sự thay đổi mặc định của JDK

`-proc:none` **tắt annotation processing** trong javac. Điều này cần thiết cho pipeline không chủ ý chạy processor do dependency cung cấp. Từ **JDK 23**, javac cũng thay đổi hành vi mặc định: annotation processing cần được yêu cầu/cấu hình rõ ràng; nhưng một bộ option khác hoặc công cụ tích hợp có thể bật lại. Vì thế dùng `-proc:none` tường minh giúp ý định dễ kiểm tra khi hỗ trợ nhiều JDK.

`-proc:none` **không phải cờ bật sandbox**: nó không giới hạn CPU, RAM, network, file read/write của compiler, không kiểm soát plugin nếu bạn vẫn cho phép `-Xplugin`, và không bảo đảm class sau biên dịch an toàn khi chạy.

### `--release` cũng không phải sandbox

`--release 17` khiến javac dùng quy tắc ngôn ngữ, bytecode và API công khai tương ứng Java 17. Nó giúp kiểm soát compatibility, **không loại bỏ các API Java tiêu chuẩn có khả năng đọc file, mở network hoặc tạo process khi chương trình được chạy sau này**. Không dùng `--release` như cơ chế ngăn code độc hại.

## 4. Ví dụ Java 17+: giới hạn options, file output và không chạy artifact

Ví dụ dưới đây minh họa **một lớp phòng vệ ở API boundary**, phù hợp để học và thử. Nó thực hiện:

1. Ứng dụng nhận **duy nhất nội dung source**, không nhận đường dẫn, classpath hay compiler options do bên ngoài cung cấp.
2. Hạn chế kích thước source; đặt tên class và `JavaFileObject` do chương trình xác định.
3. Tạo thư mục job riêng, output riêng và classpath rỗng để giảm việc nhìn thấy dependency ứng dụng; đồng thời tắt annotation processing bằng `-proc:none`.
4. Thu thập `Diagnostic` để biết có lỗi; chỉ in **trạng thái và số lượng lỗi**, không echo raw source hay đường dẫn nhạy cảm.
5. **Không load/execute** output `.class`; dọn thư mục tạm.

**Đây vẫn không phải sandbox:** `JavaCompiler` thực thi trong JVM hiện tại. Với source không tin cậy từ Internet, phải đưa công việc thực tế vào worker có cách ly OS và resource limits như phần 6.

Tạo tệp **`CompileBoundaryDemo.java`**:

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

public final class CompileBoundaryDemo {
    private static final int MAX_CHARS = 10_000;

    // JavaFileObject do ứng dụng tạo: không đọc path do user truyền.
    static final class Source extends SimpleJavaFileObject {
        private final String content;

        Source(String content) {
            super(URI.create("string:///Example.java"), Kind.SOURCE);
            this.content = content;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return content;
        }
    }

    record Report(boolean success, long errorCount, boolean classExists) {}

    private static Report compile(JavaCompiler compiler,
                                  String source,
                                  Path jobDir) throws IOException {
        if (source.length() > MAX_CHARS) {
            throw new IllegalArgumentException("Source too large");
        }

        Path output = Files.createDirectories(jobDir.resolve("classes"));
        Path emptyCp = Files.createDirectories(jobDir.resolve("empty-cp"));
        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
                compiler.getStandardFileManager(
                        diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {

            List<String> options = List.of(
                    "--release", "17",
                    "-proc:none",
                    "--class-path", emptyCp.toString(),
                    "-d", output.toString()
            );

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, manager, diagnostics, options,
                    null, List.of(new Source(source)));

            boolean success = Boolean.TRUE.equals(task.call());
            long errors = diagnostics.getDiagnostics().stream()
                    .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
                    .count();

            return new Report(success, errors,
                    Files.isRegularFile(output.resolve("Example.class")));
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "A JDK/compiler-enabled runtime is required");
        }

        Path root = Files.createTempDirectory("compile-boundary-");
        try {
            // Nếu class này chỉ được compile, static initializer không chạy.
            String valid = "public class Example {"
                    + " static { System.out.println(\"INITIALIZED\"); }"
                    + " public static int answer() { return 42; }"
                    + " }";
            String invalid = "public class Example {"
                    + " public static int answer() { return \"bad\"; }"
                    + " }";

            Report good = compile(
                    compiler, valid,
                    Files.createDirectory(root.resolve("good")));
            Report bad = compile(
                    compiler, invalid,
                    Files.createDirectory(root.resolve("bad")));

            System.out.println("good compiled: " + good.success());
            System.out.println("good errors: " + good.errorCount());
            System.out.println("good class exists: " + good.classExists());
            System.out.println("bad compiled: " + bad.success());
            System.out.println("bad has errors: " + (bad.errorCount() > 0));
            System.out.println("artifact executed: no");
        } finally {
            List<Path> paths;
            try (Stream<Path> walk = Files.walk(root)) {
                paths = walk.sorted(Comparator.reverseOrder()).toList();
            }
            for (Path path : paths) {
                Files.deleteIfExists(path);
            }
        }
    }
}
~~~

Chạy với **JDK 17+ có compiler** trong thư mục chứa tệp:

~~~bash
javac CompileBoundaryDemo.java
java CompileBoundaryDemo
~~~

Stdout dự kiến chính xác khi dùng JDK thông thường và ví dụ nguyên bản:

~~~text
good compiled: true
good errors: 0
good class exists: true
bad compiled: false
bad has errors: true
artifact executed: no
~~~

Bạn **không** thấy dòng `INITIALIZED` vì chương trình chỉ biên dịch `Example` chứ không nạp/khởi tạo class đó. Biên dịch thành công không tạo bảo đảm an toàn để chạy code này.

### Giải thích vì sao từng biện pháp có giới hạn

- `new Source(source)` tạo unit từ chuỗi, tránh cho user kiểm soát trực tiếp path của source file. Nhưng source vẫn đi vào bộ phân tích cú pháp/kiểu của compiler.
- `MAX_CHARS` giới hạn kích thước đầu vào trong ví dụ, không giới hạn toàn bộ tài nguyên có thể dùng. Trong dịch vụ thật cần thêm giới hạn tổng số file, bytes, số tác vụ đồng thời, memory, CPU, disk và thời gian.
- `empty-cp` và `--class-path` cố định giúp không tự động lấy classpath ứng dụng làm nơi giải dependency. Đây là giới hạn **dependency visibility**, không phải chính sách quyền truy cập OS.
- `-proc:none` bảo đảm tác vụ mẫu không chạy annotation processor. Code mẫu không nhận `-Xplugin` hoặc option tùy ý từ client.
- `-d` và thư mục riêng giúp tránh trộn output giữa các job. Thư mục tạm không ngăn một compiler/process có quyền khác đọc file bên ngoài, nên không xem đây là filesystem sandbox.
- `DiagnosticCollector` tiện cho demo, nhưng nó **có thể tăng bộ nhớ theo số diagnostic**. Với dịch vụ nhận đầu vào không tin cậy, cần thiết kế cơ chế giới hạn diagnostic/output từ xa thay vì giữ mọi diagnostic vô hạn.
- `Files.walk` xóa output cuối thử nghiệm. Nếu một job bị kill đột ngột, cần cơ chế quét và xóa job directory còn sót; code cleanup trong `finally` chưa đủ cho mọi sự cố.
- Một `.class` tồn tại chỉ là artifact. Ứng dụng không tự nạp class đó, không gọi `Class.forName`, không tạo object hay invoke `main`.

## 5. Khi nào compiler có thể chạy code trong quá trình build?

### Annotation processor

Annotation processor là class thực thi, triển khai `javax.annotation.processing.Processor` và có thể đọc/generate source, sinh file hoặc thực hiện side effect tùy quyền process. Nếu processor từ dependency không tin cậy được bật, việc **compile source** có thể kích hoạt code ấy, ngay cả khi bạn không chạy bytecode vừa sinh.

Các cách kích hoạt processor phụ thuộc javac options và toolchain, ví dụ `-processor`, `--processor-path`, `--processor-module-path`, `-proc:full`. Vì vậy **không** nhận các option này từ request một cách tự do. Nếu ứng dụng có nhu cầu annotation processing hợp lệ (Lombok, MapStruct, code generator nội bộ, v.v.), hãy đưa processor vào nhóm dependency đã xét duyệt và chạy trong worker được cô lập theo độ tin cậy của nó.

### Javac plugin, dependency và callback

`-Xplugin:Name` cho phép cài javac plugin; plugin là code chạy cùng compiler. Classpath/module path có thể ảnh hưởng công cụ tìm thấy class/processor/plugin nào. Custom `JavaFileManager`, `DiagnosticListener` và `JavaFileObject` cũng là code được compiler gọi: nếu thành phần này thực thi thao tác phức tạp với dữ liệu do người ngoài gửi, chính chúng có thể trở thành lỗ hổng.

**Điểm phân biệt:** Java source thông thường không tự chạy các constructor, method hay static initializer của nó trong quá trình biên dịch. Rủi ro thực thi khi build đến từ **công cụ/extension mà compiler sử dụng**, cùng với lỗi triển khai và những tài nguyên mà chúng được phép truy cập.

### Biên dịch xong: không tự động chuyển thành code đáng tin

Không dùng một kết quả `call() == true` để quyết định `ClassLoader#defineClass` hoặc chạy `main` ngay trong JVM chứa dữ liệu nhạy cảm. Nếu sản phẩm cần chạy code do user gửi, đó là **một ranh giới thực thi thứ hai**, yêu cầu worker/VM/container được cô lập, quyền hạn hạn chế, kiểm soát syscall/file/network và giới hạn tài nguyên riêng; công đoạn compile an toàn hơn không tự cung cấp an toàn cho runtime.

## 6. Kiến trúc khuyến nghị cho hệ thống chấp nhận source tùy ý

~~~mermaid
flowchart TD
    A[Request chứa source không tin cậy] --> B[Kiểm tra size, quota, schema, auth]
    B --> C[Hàng đợi tác vụ và thư mục riêng]
    C --> D[Worker cô lập bằng OS/container/VM]
    D --> E[Fixed compiler options + trusted JDK/dependencies]
    E --> F{CompilationTask.call thành công?}
    F -->|Không| G[Trả diagnostics đã giới hạn và mã hóa]
    F -->|Có| H[Kiểm tra artifact, chính sách phân phối]
    H --> I{Có cần chạy code?}
    I -->|Không| J[Lưu output theo quyền/quota cho phép]
    I -->|Có| K[Worker runtime cô lập riêng]
    G --> L[Cleanup, ghi audit và giải phóng quota]
    J --> L
    K --> L
~~~

Trong sơ đồ trên, **worker cô lập** mới là ranh giới chính với nguồn không tin cậy. Một JVM con riêng nhưng chạy cùng user, có toàn quyền đọc filesystem/network và không có giới hạn tài nguyên **chưa phải isolation đủ mạnh**.

Một thiết kế thực tế cần những lớp kiểm soát sau (tùy mức rủi ro):

1. **Admission:** xác thực/ủy quyền, quota theo user, giới hạn số job đồng thời, size/encoding/loại source, tổng file và dependency.
2. **Trusted toolchain:** JDK được quản lý cập nhật, compiler options từ code ứng dụng, dependency/JAR trusted, pin version/checksum khi phù hợp, mặc định tắt processor/plugin không cần thiết; không cho caller ghi đè classpath, processor path hoặc output path.
3. **Execution isolation:** chạy compiler trên process/VM/container ngắn hạn với user ít quyền, filesystem riêng tối thiểu, giới hạn network egress, CPU/memory/process/file descriptor/disk và hard timeout do supervisor **bên ngoài** worker thực thi.
4. **Artifact isolation:** phân biệt thư mục source, classpath, output, cache; không trộn tenant. Khi fail, không phát hành output dù có vài class đã được tạo. Kiểm soát việc copy artifact ra môi trường khác.
5. **Observability và cleanup:** giới hạn log/diagnostics; mã hóa khi hiện HTML; che các đường dẫn nội bộ, không in source chứa bí mật; audit job id, người gửi, kết quả, resource usage; kill/cleanup cả khi timeout.
6. **Runtime isolation riêng:** nếu chạy code, thiết lập ranh giới thực thi độc lập; kiểm soát network, file, tài nguyên và thời gian. Không chạy artifact của user trong process ứng dụng chỉ vì biên dịch thành công.

Không thể chứng minh an toàn bằng một denylist từ khóa kiểu “cấm `Runtime`, `java.io`, `java.net`” hoặc bằng việc bắt riêng `SecurityException`. Java có reflection, nhiều API đồng nghĩa và các bề mặt mở rộng; phân tích source để enforce quyền truy cập không thay thế sandbox OS. Compiler option allowlist và policy nghiệp vụ vẫn hữu ích nhưng chỉ là các lớp phòng vệ bổ sung.

## 7. Xử lý lỗi, diagnostics và dữ liệu rò rỉ

`DiagnosticCollector` nhận danh sách `Diagnostic<? extends JavaFileObject>` để ứng dụng xem `Kind.ERROR`/`WARNING`, dòng, cột và message. Với source không tin cậy cần:

- **Tách lỗi biên dịch và lỗi infrastructure.** `CompilationTask.call()` trả `false` khi có lỗi biên dịch bình thường; nhưng timeout, OOM, worker chết, lỗi file manager, lỗi IO hay cấu hình option sai phải được báo thành trạng thái khác. Không biến mọi exception thành “source invalid”.
- **Giới hạn output.** Một source có thể sinh rất nhiều lỗi. Bọc listener, cắt số lượng diagnostic được lưu/trả, giới hạn bytes stderr/stdout và ngừng job quá quota. `DiagnosticCollector` trong demo giữ toàn bộ để dễ hiểu, nên không áp dụng nguyên xi cho multi-tenant production.
- **Không tin message.** Tên class/file, source snippet và một số thông điệp có thể chứa chuỗi do user kiểm soát. Escape khi hiển thị HTML/Markdown, tránh log injection và path disclosure. `Diagnostic.getSource()` có thể `null`; dòng/cột có thể là `Diagnostic.NOPOS`; message cụ thể phụ thuộc locale và compiler version.
- **Không trả toàn bộ file nội bộ.** Diagnostic có thể nhắc đến đường dẫn classpath/JDK/workspace. Khi mở API công khai, chuẩn hóa thông tin tối thiểu cần thiết, không để lộ đường dẫn của ứng dụng/tenant khác.
- **Tạo đối tượng task mới cho lần biên dịch mới.** `CompilationTask` là tác vụ dùng một lần. `reload` hay `call()` lần hai không phải cách compile lại. Một job mới cần scope/temp directory/diagnostic riêng.

## 8. Các hiểu lầm thường dẫn đến lỗ hổng

| Nhận định sai | Điều đúng |
| --- | --- |
| “Chỉ gọi `getTask`/`call` nên không chạy code lạ.” | Processor/plugin hoặc callback được compiler kích hoạt có thể chạy code; code sau khi compile cũng không đáng tin để nạp |
| “`-proc:none` đã tạo sandbox.” | Nó chỉ tắt annotation processing; còn quyền OS và resource của compiler |
| “`--release 17` cấm API nguy hiểm.” | Nó kiểm soát tương thích ngôn ngữ/API, không kiểm soát quyền lúc chạy |
| “ClassLoader/ModuleLayer riêng tự giới hạn filesystem.” | Class/module boundary không phải OS sandbox |
| “Mã compile thành công là mã an toàn.” | `true` chỉ biểu thị không có lỗi biên dịch |
| “Bọc `task.call()` trong thread timeout là đủ.” | Interrupt không bảo đảm dừng compiler; phải có supervisor có thể dừng worker process |
| “Output ở thư mục tạm là không thể đọc ngoài đó.” | Compiler có quyền process trừ khi OS sandbox thực sự chặn |
| “Diagnostics là text đáng tin để render trực tiếp.” | Nó có thể chứa dữ liệu do user kiểm soát và cần escape/limit |
| “Security Manager có thể khóa quyền của compiler.” | JDK 24+ vô hiệu hóa vĩnh viễn Security Manager; dùng isolation của OS/container/VM |
| “Bắt hết `Exception` và trả lỗi syntax là đủ.” | Phải phân biệt code invalid, policy denied, compiler crash, quota, timeout và infrastructure failure |

## 9. Tình huống tự kiểm tra

1. **API nhận source do khách hàng gửi và chạy `CompilationTask.call()` trực tiếp trong JVM web server. Nêu nguy cơ.** CPU/heap của server bị ảnh hưởng; compiler/parser hoặc callback có thể lỗi; thiếu hard timeout; nếu processor/plugin được bật có thể thực thi code trong JVM có quyền nhạy cảm. Hướng xử lý là job worker cô lập.
2. **Từ request người dùng, backend nhận `List<String> options` và chuyển thẳng tới `getTask`. Vì sao nguy hiểm?** Người gửi có thể cấu hình processor/plugin, classpath/module path hoặc đường dẫn ghi output. Ứng dụng phải xây option allowlist theo chính sách.
3. **Dùng `-proc:none` và source có `static { System.out.println("hello"); }`. Khi gọi compiler có xuất hiện “hello” không?** Với compile source Java thông thường và không có code khác kích hoạt class, static initializer của class đó không chạy. Nhưng điều này **không** chứng minh an toàn của pipeline.
4. **Compile trả `true`, người dùng có được chạy class trong server không?** Không. Chạy bytecode là ranh giới thực thi mới, cần kiểm soát riêng.
5. **Một build `false` nhưng thư mục có vài file `.class`, có phát hành không?** Không; phải xem toàn bộ job thất bại và loại bỏ output chưa được xác nhận.
6. **Vì sao không dùng `SecurityManager` trong một hệ thống Java mới?** Nó đã bị vô hiệu hóa vĩnh viễn từ JDK 24; dùng isolation hệ điều hành thay thế.

## 10. Tài liệu tham khảo đang có hiệu lực

- [Java SE 25 — JavaCompiler](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/JavaCompiler.html): `getTask`, file manager và compiler API.
- [Java SE 25 — JavaCompiler.CompilationTask](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/JavaCompiler.CompilationTask.html): `call()` và vòng đời task.
- [Java SE 25 — Diagnostic](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/Diagnostic.html): loại diagnostic, nguồn, vị trí, message.
- [Java SE 26 — javac command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html): `-proc:none`, `--release`, processor options và `-Xplugin`.
- [JDK 23 release notes — annotation processing defaults](https://www.oracle.com/java/technologies/javase/23-relnote-issues.html): thay đổi mặc định của annotation processing.
- [Java SE 25 Security Guide — Security Manager permanently disabled](https://docs.oracle.com/en/java/javase/25/security/security-manager-is-permanently-disabled.html): hành vi JDK 24+ và hướng thay thế.

**Ý chính:** `JavaCompiler` phục vụ biên dịch và báo lỗi, không được thiết kế làm vùng chạy an toàn cho source không tin cậy. Kiểm soát inputs/options và processor là cần thiết; để chịu được source tùy ý từ bên ngoài, **ranh giới có thể thực thi và dừng cưỡng bức ở mức OS** mới quyết định khả năng cô lập.
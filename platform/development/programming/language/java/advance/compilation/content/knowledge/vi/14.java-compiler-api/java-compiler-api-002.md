# Lấy compiler bằng ToolProvider và xử lý khi compiler không có sẵn

Thông thường lập trình viên biên dịch Java bằng lệnh `javac`, IDE, Maven hoặc Gradle. Nhưng một số công cụ cần **biên dịch mã Java ngay từ một ứng dụng Java đang chạy**, ví dụ trình kiểm tra bài tập, công cụ sinh code hoặc IDE tối giản. API chuẩn `javax.tools` hỗ trợ điều đó. Điểm vào phổ biến là:

~~~java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
~~~

Vấn đề quan trọng: **kết quả có thể là `null`**. Không phải mọi Java runtime đều có một compiler implementation. Một ứng dụng được biên dịch trên JDK đầy đủ có thể được triển khai trên runtime image nhỏ chỉ phục vụ chạy bytecode. Khi ấy, gọi `compiler.getTask(...)` ngay mà không kiểm tra sẽ gây lỗi `NullPointerException`, trong khi nguyên nhân thật là môi trường không có system compiler.

Bài học giải thích cách dùng `ToolProvider`, cách phát hiện thiếu compiler, sự khác biệt giữa module API và implementation, cách gọi `JavaCompiler` để biên dịch nguồn trong tiến trình, thu thập diagnostic và tổ chức các phương án fail-fast, giảm chức năng hoặc dùng compiler bên ngoài. Ví dụ hướng tới **JDK 17+**.

## 1. Java Compiler API cung cấp những gì?

Các kiểu thường gặp:

| Kiểu API | Công dụng |
| --- | --- |
| `javax.tools.ToolProvider` | Lấy một số công cụ Java do môi trường chạy cung cấp |
| `javax.tools.JavaCompiler` | Giao diện compiler Java, có `run(...)` và `getTask(...)` |
| `JavaCompiler.CompilationTask` | Công việc biên dịch, thực thi bằng `call()` |
| `StandardJavaFileManager` | Kết nối nguồn/đầu ra với các tệp và đường dẫn chuẩn |
| `JavaFileObject` | Đơn vị nguồn hoặc class mà compiler làm việc |
| `DiagnosticCollector<JavaFileObject>` | Thu thập lỗi, warning, note một cách có cấu trúc |
| `Diagnostic` | Mô tả mức độ, file nguồn, vị trí và thông điệp chẩn đoán |

Mô hình tổng quát:

~~~text
Ứng dụng Java đang chạy
       |
       v
ToolProvider.getSystemJavaCompiler()
       |
       +-- trả null ----------> xử lý thiếu compiler
       |
       v
JavaCompiler
       |
       +-- StandardJavaFileManager
       +-- JavaFileObject nguồn
       +-- compiler options
       +-- DiagnosticCollector
       |
       v
CompilationTask.call()
       |
       +-- thành công --------> classfile đầu ra
       |
       +-- thất bại ----------> xem diagnostic
~~~

API này làm việc ở **thời điểm biên dịch**. Nó không tự động tải dependency, không khởi động debugger, không chứng minh code đã đúng logic và không tự chạy classfile sau khi biên dịch. Việc **biên dịch**, **nạp lớp** và **thực thi lớp** là các bước riêng.

Đặc biệt, `ToolProvider.getSystemJavaCompiler()` **không tương đương** gọi `ProcessBuilder("javac")`. Nó không đơn giản tìm một executable tên `javac` trong `PATH` rồi khởi động process ngoài; nó lấy công cụ qua API mà runtime/JDK hiện tại cung cấp.

## 2. Lấy compiler đúng cách và kiểm tra `null`

Trong phương thức Java, có thể viết:

~~~java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    // Compiler không sẵn có trong runtime hiện tại.
}
~~~

Đây là **đoạn minh họa**, chưa phải file độc lập. `getSystemJavaCompiler()` là phương thức `static` của `ToolProvider`. Kiểu trả về là `JavaCompiler` khi có implementation hoặc `null` khi không có system compiler thích hợp.

**Không nên**:

~~~java
ToolProvider.getSystemJavaCompiler().run(
        null, System.out, System.err, "Hello.java");
~~~

Nếu system compiler thiếu, biểu thức phía trước `.run(...)` bằng `null` và gây `NullPointerException`. Exception này không giúp người dùng hiểu rằng họ cần một runtime có compiler.

### Chương trình probe chạy được trên JDK 17+

Tạo **`CompilerProbe.java`**:

~~~java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public final class CompilerProbe {
    private CompilerProbe() {
    }

    public static void main(String[] args) {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();

        if (compiler == null) {
            System.err.println("NO_SYSTEM_COMPILER");
            System.exit(2);
        }

        System.out.println("SYSTEM_COMPILER_AVAILABLE");
    }
}
~~~

Trên JDK có compiler:

~~~sh
javac --release 17 -encoding UTF-8 CompilerProbe.java
java CompilerProbe
~~~

Stdout chính xác:

~~~text
SYSTEM_COMPILER_AVAILABLE
~~~

Ở runtime có API `java.compiler` nhưng thiếu compiler implementation, chương trình **đã được biên dịch trước** có thể in:

~~~text
NO_SYSTEM_COMPILER
~~~

Dòng này ở **stderr**, và mã thoát là **2** do `System.exit(2)`. Không thể dùng chính runtime không có compiler để biên dịch `CompilerProbe.java` ngay tại đó; phải lấy `CompilerProbe.class` từ một môi trường build phù hợp.

Nếu runtime thiếu luôn các lớp API `javax.tools`, chương trình có thể không khởi động đến câu kiểm tra `null` vì lỗi nạp/link kiểu. Vì vậy, `null` xử lý một trường hợp thiếu implementation, không thay thế việc đóng gói module API cần thiết.

### Cần xử lý `null` theo yêu cầu sản phẩm

Có hai cách hợp lý tùy ứng dụng:

- **Bắt buộc compile:** trả trạng thái lỗi, dừng tác vụ, hướng dẫn dùng JDK hoặc runtime image chứa implementation phù hợp.
- **Compile là tính năng tùy chọn:** tắt tính năng, báo cho người dùng, vẫn cho các chức năng độc lập khác hoạt động.

Một CLI có thể thoát với mã khác 0 như probe. Một thư viện Java thường **không nên tự gọi `System.exit`** vì nó sẽ dừng cả process của ứng dụng chủ; thư viện nên trả kết quả có trạng thái rõ hoặc ném exception có ý nghĩa để caller quyết định.

## 3. `java.compiler` khác `jdk.compiler`

Từ Java 9, mô hình module của JDK phân biệt API với implementation:

- **`java.compiler`** là module chuẩn chứa `javax.tools.JavaCompiler`, `javax.tools.ToolProvider` và các API compiler liên quan.
- **`jdk.compiler`** là module JDK cung cấp implementation trình biên dịch Java thông thường (`javac`).

Vì vậy **có API `java.compiler` chưa đủ kết luận có system compiler**. Runtime image được tạo với `jlink` có thể chứa API mà không chứa provider compiler. Trên một JDK đầy đủ, thông thường có cả hai.

Bạn có thể kiểm tra modules bằng lệnh chạy trên runtime muốn thử:

~~~sh
java --list-modules
java --describe-module java.compiler
java --describe-module jdk.compiler
~~~

Các dòng của `--list-modules` thường có tên như `java.compiler@17...` hoặc `jdk.compiler@17...`, với phần phiên bản phụ thuộc bản phân phối. Nếu `jdk.compiler` không tồn tại ở runtime image, đó là dấu hiệu cần điều tra. **Kết luận khả năng lấy compiler vẫn nên dựa trên probe chạy bởi chính executable `java` của ứng dụng.**

### Runtime tự tạo không có compiler

Trên máy có JDK 17+ và công cụ `jlink`, có thể tạo runtime thử nghiệm:

~~~sh
jlink --add-modules java.base,java.compiler --output runtime-without-javac
~~~

Bảo đảm thư mục đầu ra chưa tồn tại và chỉ làm thí nghiệm tại vị trí bạn được phép tạo tệp. Image này chủ đích có API `java.compiler` nhưng không yêu cầu `jdk.compiler`.

Sau khi đã biên dịch `CompilerProbe.java` bằng JDK đầy đủ, trên Linux/macOS chạy:

~~~sh
runtime-without-javac/bin/java -cp . CompilerProbe
~~~

Trên Windows PowerShell:

~~~powershell
.\runtime-without-javac\bin\java.exe -cp . CompilerProbe
~~~

Ở image không có provider compiler, probe đi vào nhánh thiếu compiler và phát `NO_SYSTEM_COMPILER` ở stderr. Bài thực hành này phân biệt **“runtime có khả năng chạy classfile”** với **“runtime có khả năng biên dịch Java trong tiến trình”**.

Không nên suy từ việc hệ điều hành cài sẵn `javac` hoặc từ tên thư mục `JAVA_HOME` mà không kiểm tra executable được dùng để chạy chính process hiện tại.

## 4. Ví dụ đầy đủ: biên dịch một tệp `.java` bằng Compiler API

Ví dụ này tạo mã nguồn `GeneratedGreeting.java` bằng `Files.writeString`, sau đó dùng `JavaCompiler.getTask(...)` để tạo classfile. Cuối cùng bạn có thể chạy lớp kết quả bằng `java` riêng.

**Tệp `InProcessCompileDemo.java`:**

~~~java
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

public final class InProcessCompileDemo {
    private InProcessCompileDemo() {
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "System Java compiler not available; use a JDK");
        }

        Path root = Path.of("build", "compiler-api-demo");
        Path sourceDir = root.resolve("src");
        Path classDir = root.resolve("classes");
        Files.createDirectories(sourceDir);
        Files.createDirectories(classDir);

        Path source = sourceDir.resolve("GeneratedGreeting.java");
        String code = """
                public class GeneratedGreeting {
                    public static void main(String[] args) {
                        System.out.println("Hello from generated Java");
                    }
                }
                """;

        Files.writeString(source, code, StandardCharsets.UTF_8);

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        List<String> options = List.of(
                "--release", "17",
                "-encoding", "UTF-8",
                "-d", classDir.toString());

        try (StandardJavaFileManager manager =
                     compiler.getStandardFileManager(
                             diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {

            Iterable<? extends JavaFileObject> units =
                    manager.getJavaFileObjectsFromPaths(List.of(source));

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, manager, diagnostics, options, null, units);

            boolean success = Boolean.TRUE.equals(task.call());
            System.out.println("Compilation success: " + success);

            for (Diagnostic<? extends JavaFileObject> diagnostic
                    : diagnostics.getDiagnostics()) {
                System.err.println(diagnostic.getKind()
                        + ": " + diagnostic.getMessage(Locale.ROOT));
            }

            if (!success) {
                throw new IllegalStateException(
                        "Generated source did not compile");
            }
        }
    }
}
~~~

Mã dùng Java 17+ và có đủ imports. Các thư mục `build/compiler-api-demo/src` và `build/compiler-api-demo/classes` được tạo nếu chưa tồn tại. Chương trình cần quyền ghi tại thư mục làm việc hiện tại, và compiler phải hỗ trợ `--release 17`.

Biên dịch và chạy chương trình điều khiển:

~~~sh
javac --release 17 -encoding UTF-8 InProcessCompileDemo.java
java InProcessCompileDemo
~~~

Trong môi trường có compiler và tệp được tạo thành công, **stdout**:

~~~text
Compilation success: true
~~~

Sau đó, chạy classfile được tạo trong lần compile thứ hai:

~~~sh
java -cp build/compiler-api-demo/classes GeneratedGreeting
~~~

Stdout:

~~~text
Hello from generated Java
~~~

Điểm cốt lõi: lần chạy `InProcessCompileDemo` dùng **compiler object trong Java API** để biên dịch `GeneratedGreeting.java`. Nó không dùng `ProcessBuilder` hay chạy shell command `javac` từ bên trong code. Lệnh `javac` ở đầu bài chỉ dùng để tạo classfile của **chính chương trình demo**.

### Các phần của `getTask(...)`

| Đối tượng/tham số | Ý nghĩa |
| --- | --- |
| `compiler` | Đối tượng `JavaCompiler` đã được kiểm tra khác `null` |
| `manager` | `StandardJavaFileManager` làm việc với nguồn/đầu ra |
| `diagnostics` | Collector nhận lỗi/warning có cấu trúc |
| `options` | Các cờ biên dịch như `--release`, `-encoding` và `-d` |
| `units` | Danh sách `JavaFileObject` ứng với tệp nguồn |
| `task.call()` | Bắt đầu biên dịch, trả kết quả thành công/thất bại |

`getStandardFileManager(...)` nhận locale và charset để giải quyết thông báo/mã hóa phù hợp; `-encoding UTF-8` ở options làm rõ encoding đọc nguồn. `try-with-resources` bảo đảm file manager được đóng khi hoàn tất kể cả khi xảy ra lỗi.

`--release 17` điều khiển mức nguồn, định dạng bytecode và API nền tảng được phép dùng. Nó **không tự biến một runtime thiếu compiler thành runtime có compiler**.

`-d` chỉ nơi ghi classfile. Đừng gộp thư mục nguồn và thư mục output trong build lớn; nếu nhiều tác vụ đồng thời dùng chung đầu ra, cần thiết kế tránh ghi đè hoặc trộn classfile.

### Biên dịch thành công có phải không có cảnh báo?

Không nhất thiết. Khi compiler có warning, `DiagnosticCollector` có thể chứa `WARNING` hoặc `MANDATORY_WARNING` dù `task.call()` trả `true`. Ngược lại, compiler có thể thất bại vì lỗi mà collector ghi dưới `ERROR`. Nếu dùng tùy chọn `-Werror`, policy cảnh báo có thể khiến biên dịch thất bại.

Phân biệt **kết quả tác vụ** với **danh sách diagnostic**; không mặc định collector rỗng nếu thành công hoặc collector có dữ liệu là thất bại.

## 5. Cố ý gây lỗi để xem diagnostics

Trong `InProcessCompileDemo.java`, thử **thay riêng nội dung biến `code`** bằng mã nguồn không hợp lệ sau:

~~~java
public class GeneratedGreeting {
    public static void main(String[] args) {
        int count = "abc";
    }
}
~~~

Đây là **mẫu mã nguồn để đưa vào tệp `GeneratedGreeting.java`**, không phải chương trình có thể biên dịch/chạy thành công. Phép gán `String` cho `int` không hợp lệ. Khi compile task chạy, `task.call()` trả trạng thái thất bại và collector có diagnostic loại `ERROR`.

Có thể mở rộng vòng lặp xử lý diagnostic thành:

~~~java
for (Diagnostic<? extends JavaFileObject> d
        : diagnostics.getDiagnostics()) {
    System.err.println("Kind: " + d.getKind());
    System.err.println("Line: " + d.getLineNumber());
    System.err.println("Column: " + d.getColumnNumber());
    System.err.println("Message: " + d.getMessage(Locale.ROOT));
}
~~~

Đây là **đoạn thay cho vòng lặp trong ví dụ hoàn chỉnh**, dùng imports/biến đã khai báo. Đừng kỳ vọng vị trí cụ thể và toàn bộ wording của diagnostic giống nhau trên mọi JDK. Nếu lỗi không gắn với một điểm trong source, `getLineNumber()` và `getColumnNumber()` có thể trả `Diagnostic.NOPOS`.

Trong ví dụ có diagnostic `ERROR`, chương trình sẽ in `Compilation success: false` rồi ném `IllegalStateException` theo chính sách fail-fast đã chọn. **Đây không phải tình huống `compiler == null`:** compiler đã tồn tại và thực sự kiểm tra mã, nhưng nguồn không hợp lệ.

## 6. Phân loại trạng thái theo đúng nguyên nhân

Hãy coi các trạng thái này là độc lập:

| Trường hợp | Dấu hiệu | Xử lý |
| --- | --- | --- |
| Thiếu compiler implementation | `getSystemJavaCompiler() == null` | Báo môi trường không có compiler; không gọi `getTask` |
| API `java.compiler` cũng vắng mặt | Lỗi nạp/link lớp API hoặc module không resolve | Sửa runtime image/module setup |
| Compiler có nhưng nguồn lỗi | `task.call() == false` và diagnostic phù hợp | Hiển thị lỗi nguồn, dòng, cột, thông báo |
| Compiler có và chạy thành công | `task.call() == true` | Ghi nhận vị trí classfile, xử lý warning nếu có |
| Không tạo/đọc được file | `IOException` hoặc lỗi file manager | Sửa quyền, đường dẫn hoặc tài nguyên |
| Compiler option không hỗ trợ | Exception/diagnostic phù hợp | Kiểm tra `--release`, `-d`, classpath và JDK |
| Runtime chạy output thất bại | `NoClassDefFoundError` hoặc lỗi version | Kiểm tra runtime classpath và bytecode target |

Nếu người dùng đưa mã nguồn sai, **đừng đưa lời khuyên “cài JDK”** khi `compiler` đã khác `null`. Ngược lại, khi `compiler == null`, **đừng báo “syntax error”** vì compiler chưa xử lý nguồn.

Một API nội bộ hữu ích nên trả thông tin có cấu trúc: trạng thái `UNAVAILABLE` / `SUCCESS` / `COMPILATION_FAILED` / `ENVIRONMENT_ERROR`, diagnostics và output path nếu có. Với ứng dụng web/service, chuyển các trạng thái này thành thông báo hoặc mã lỗi phù hợp, không phát một exception mơ hồ cho mọi tình huống.

## 7. `JavaCompiler.run(...)` khác `getTask(...)`

Ngoài `getTask(...)`, `JavaCompiler` có phương thức `run(...)` theo phong cách công cụ dòng lệnh. Ví dụ sau giả định `compiler` đã được kiểm tra, và các tệp từ phần 4 đã được tạo:

~~~java
int exitCode = compiler.run(
        null, System.out, System.err,
        "-encoding", "UTF-8",
        "-d", "build/compiler-api-demo/classes",
        "build/compiler-api-demo/src/GeneratedGreeting.java");
~~~

Đây là **đoạn minh họa bên trong method**, không phải tệp Java độc lập. `run(...)` trả **mã số**; mã `0` thông thường biểu thị thành công, còn mã khác `0` biểu thị thất bại.

So sánh:

- **`run(...)`:** truyền các chuỗi giống tham số `javac` và cung cấp output/error streams, thuận tiện cho tác vụ đơn giản.
- **`getTask(...)`:** làm việc với file manager, `JavaFileObject` và `DiagnosticCollector` để xử lý dữ liệu/diagnostic có cấu trúc, phù hợp công cụ cần kiểm soát nhiều hơn.
- **Cả hai:** cần một đối tượng `JavaCompiler` thật. Không phương thức nào khắc phục được giá trị `null` của `ToolProvider`.

Cũng đừng nhầm `JavaCompiler.run(...)` với `Runtime.exec(...)` hay `ProcessBuilder`. Cái đầu là API của compiler object trong tiến trình, hai cái sau điều phối chương trình con từ hệ điều hành.

## 8. Cấu hình compiler path và phụ thuộc

Lấy được compiler chỉ là **điều kiện cần**. Với mã nguồn có import phụ thuộc ngoài, compiler task còn cần biết classpath/module path phù hợp.

Ví dụ, một nguồn dùng `org.example.lib.Greeter` có thể bị lỗi:

~~~text
package org.example.lib does not exist
~~~

dù `getSystemJavaCompiler()` trả object hợp lệ. Khi đó vấn đề là **compile classpath**, không phải “system compiler missing”. Bạn có thể cấu hình đường dẫn bằng compiler options thích hợp hoặc các vị trí trong file manager.

Các tham số source/target, `--release`, phiên bản JDK, encoding, output directory và annotation processing cũng có thể ảnh hưởng kết quả. Một compiler chạy được không tự phát hiện mọi thư viện trong dự án; công cụ build như Gradle/Maven thường quản lý phần phụ thuộc này giúp bạn.

Sau khi compile thành công, JVM chạy kết quả vẫn cần đúng **runtime classpath/module path**. Bytecode được tạo cho mức Java cao hơn JVM đích có thể gây `UnsupportedClassVersionError`. Phân tích lỗi theo **giai đoạn** giúp bạn tránh điều trị sai nguyên nhân.

## 9. Khi chạy trong container, service hoặc runtime `jlink`

Một máy có thể đồng thời có:

- Một JDK trên máy phát triển, cung cấp cả `java` và `javac`.
- Một JDK khác dùng bởi IDE hoặc Gradle daemon.
- Một container chỉ mang runtime image tối giản để chạy app.
- Một bản Java runtime do `jlink` tạo mà không có module `jdk.compiler`.

Vì thế, chỉ chạy `javac -version` trong terminal **không đủ chứng minh** chính ứng dụng của bạn chạy trong runtime có compiler.

### Thu thập thông tin từ chính process

Trong mã Java, có thể chẩn đoán:

~~~java
System.out.println("java.version = "
        + System.getProperty("java.version"));
System.out.println("java.home = "
        + System.getProperty("java.home"));
System.out.println("compiler available = "
        + (ToolProvider.getSystemJavaCompiler() != null));
~~~

Đây là **đoạn minh họa trong method** với import `ToolProvider` phù hợp. Các đường dẫn/phiên bản phụ thuộc môi trường nên không có stdout cố định. Quan sát chúng từ **process thực tế** có giá trị hơn so với chỉ xem `JAVA_HOME` của một terminal khác.

### Ứng dụng Java modular cần `requires java.compiler`

Nếu code gọi `javax.tools` thuộc một **explicit named module** có descriptor, cần nêu dependency API:

~~~java
module demo.compiler.client {
    requires java.compiler;
}
~~~

Đây là nội dung `module-info.java` minh họa, chưa phải project đầy đủ. `requires java.compiler` cho module ứng dụng truy cập API chuẩn; nó **không tự bảo đảm runtime image có compiler implementation**. Với ứng dụng cần biên dịch động trong runtime `jlink`, bảo đảm module/provider thích hợp cũng được phân phối.

### Điều gì xảy ra nếu chỉ có `java.compiler`?

Runtime có thể nạp API `ToolProvider` nhưng `getSystemJavaCompiler()` vẫn trả `null`. Đây là lý do cần kiểm tra provider chứ không chỉ nhìn module API. Runtime thiếu cả `java.compiler` thì lỗi lại khác, có thể là `NoClassDefFoundError`/lỗi module resolution trước khi đến dòng kiểm tra.

## 10. Chọn fail-fast, graceful degradation hay fallback

**Fail-fast** phù hợp khi ứng dụng bản chất là một compiler service hoặc trình kiểm tra mã: thiếu compiler là lỗi vận hành bắt buộc. Báo rõ runtime thiếu khả năng, trả trạng thái thất bại và kết thúc tác vụ.

**Graceful degradation** phù hợp khi biên dịch là tính năng phụ: đánh dấu tính năng unavailable và cho ứng dụng tiếp tục phần nghiệp vụ không phụ thuộc compiler. Nếu có giao diện, hiển thị thông báo rõ thay vì để người dùng bấm rồi gặp `NullPointerException`.

**Fallback sang công cụ bên ngoài** chỉ phù hợp nếu hệ thống chủ động hỗ trợ đường dẫn `javac` được cấu hình hoặc một dịch vụ build riêng. Khi dùng `ProcessBuilder` cần xử lý executable path, exit code, stdout/stderr, timeout, classpath, quyền hệ điều hành và phiên bản compiler. Không nên mặc định dùng bất kỳ `javac` nào xuất hiện trong PATH khi yêu cầu version ổn định hoặc nguồn không đáng tin cậy.

**An toàn:** Compiler API không phải sandbox. Biên dịch, tải, thực thi code do người dùng đưa vào, hoặc chạy annotation processors của bên thứ ba, có thể tiêu thụ tài nguyên hoặc gây tác động ngoài ý muốn. Không dùng `JavaCompiler` như một cơ chế cô lập mã không tin cậy; cần kiến trúc giới hạn quyền và tài nguyên độc lập.

## 11. Quy trình chẩn đoán theo thứ tự

Khi một ứng dụng không biên dịch động được, làm theo thứ tự:

1. **Kiểm tra `getSystemJavaCompiler()`.** Nếu `null`, dừng nhánh biên dịch và báo thiếu compiler.
2. **Xác định đúng runtime.** In `java.home` và `java.version` trong process đang chạy, không đoán từ một terminal khác.
3. **Kiểm tra API/provider module.** Với Java 9+, xem `java.compiler` và `jdk.compiler` trong runtime image; khác biệt API và implementation là mấu chốt.
4. **Chạy probe ở môi trường đích.** Biên dịch `CompilerProbe.class` bằng JDK có compiler rồi chạy bằng executable của deployment.
5. **Nếu compiler tồn tại, kiểm tra nguồn và options.** Kiểm tra source file, `JavaFileObject`, `--release`, classpath/module path và thư mục output.
6. **Đọc diagnostics.** Với lỗi nguồn, xem `ERROR` và vị trí; với warning, xem policy `-Werror` nếu có.
7. **Kiểm tra runtime output.** Sau khi compile thành công, chạy classfile trong môi trường tương thích và với dependency cần thiết.
8. **Thử trên artifact triển khai thật.** Kiểm tra container hoặc image `jlink`, không chỉ laptop dev.

Những điều không nên làm: tự chặn `NullPointerException` để đoán thiếu compiler; in “compile failed” chung chung; trả success khi chưa tạo classfile; hoặc chạy mã do người dùng cung cấp trên server production mà thiếu cơ chế an toàn.

## 12. Bài tập thực hành

**Bài 1 — Probe.** Tạo `CompilerProbe.java`, biên dịch/chạy trên JDK và giải thích vì sao `SYSTEM_COMPILER_AVAILABLE` xuất hiện. Thay nhánh null bằng exception có thông điệp rõ nếu muốn xây thư viện thay cho CLI.

**Bài 2 — Runtime image.** Nếu có `jlink`, tạo image chỉ gồm `java.base`, `java.compiler`. Dùng classfile probe đã biên dịch bằng JDK để kiểm tra hành vi thiếu compiler; phân biệt với trường hợp runtime thiếu cả API.

**Bài 3 — Compile in-process.** Chạy `InProcessCompileDemo.java` và sau đó chạy `GeneratedGreeting`, xác nhận hai dòng stdout tương ứng ở **hai lần chạy**.

**Bài 4 — Lỗi cố ý.** Sửa `GeneratedGreeting` để gán `String` cho `int`. Dự đoán `task.call()`, mức diagnostic và sự khác biệt với `compiler == null`.

**Bài 5 — Quyền ghi.** Đổi thư mục output sang nơi không được phép ghi trong môi trường thử nghiệm; nêu cách phân loại lỗi thay vì hướng người dùng cài lại JDK.

**Bài 6 — Thư viện có dependency.** Viết một nguồn Java cần lớp trong JAR ngoài. Làm compiler có sẵn nhưng không có compile classpath; sau đó thêm đường dẫn đúng. Vì sao việc có compiler không tự làm mọi import hợp lệ?

**Bài 7 — So sánh API.** Nếu công cụ cần lấy lỗi kiểu có line/column/kind để hiển thị trong IDE, nên dùng `run(...)` hay `getTask(...)` với collector? Giải thích.

### Câu hỏi tự đánh giá

1. **Lấy system compiler bằng API nào?** — `ToolProvider.getSystemJavaCompiler()`.
2. **Giá trị `null` có nghĩa gì?** — Môi trường chạy không cung cấp system Java compiler qua API.
3. **`JavaCompiler` ở module nào?** — API ở `java.compiler`; implementation JDK thông thường ở `jdk.compiler`.
4. **Có `javac` trong PATH có bảo đảm API khác `null`?** — Không, process có thể dùng runtime khác.
5. **Nếu `task.call()` trả `false` có đồng nghĩa compiler không tồn tại?** — Không, compiler đã chạy tác vụ nhưng tác vụ thất bại.
6. **Công cụ nào thu thập lỗi/warning cấu trúc?** — `DiagnosticCollector` và các `Diagnostic`.
7. **`getTask(...)` có tự tải thư viện ngoài không?** — Không; cần cấu hình dependency và đường tìm kiếm phù hợp.
8. **Khi nào nên fail-fast?** — Khi biên dịch là chức năng bắt buộc của ứng dụng.
9. **Khi nào nên giảm chức năng?** — Khi biên dịch chỉ là khả năng tùy chọn và các tính năng khác không phụ thuộc nó.
10. **Compiler API có thể dùng để chạy code không tin cậy an toàn không?** — Không; cần cơ chế cách ly và kiểm soát riêng.

**Kết luận:** Lấy compiler bằng `ToolProvider` là bước nhỏ nhưng có ý nghĩa kiến trúc lớn. **Đừng nhầm API tồn tại với implementation tồn tại**, đừng nhầm compiler không có sẵn với mã nguồn không biên dịch được. Kiểm tra `null`, chọn chính sách xử lý minh bạch, dùng `JavaCompiler` và diagnostics có cấu trúc, rồi xác minh trên chính runtime sẽ triển khai.
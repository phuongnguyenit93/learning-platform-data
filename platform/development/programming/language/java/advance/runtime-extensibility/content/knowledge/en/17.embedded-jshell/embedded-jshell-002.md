# Tạo JShell, cấu hình classpath, tùy chọn biên dịch và luồng vào ra

## 1. JShell nhúng là gì và cần cấu hình ở đâu?

`JShell` có thể được dùng như một công cụ dòng lệnh (`jshell`) hoặc **nhúng trong ứng dụng Java** qua API thuộc module `jdk.jshell`. Ở chế độ nhúng, host không phải mô phỏng terminal REPL: nó tạo một `JShell` state engine, gửi từng đoạn mã Java (*snippet*) qua `eval(String)`, đọc kết quả dưới dạng `SnippetEvent`, giữ trạng thái giữa các lần eval và đóng engine khi kết thúc.

Một ứng dụng thực tế có thể cần:

- Đưa thư viện/API của host vào **classpath của snippet** để code được nhập có thể import và gọi.
- Cấu hình các **compiler options** dùng khi JShell phân tích và biên dịch snippet.
- Cấu hình **JVM options cho tiến trình thực thi snippet** (với execution engine dùng remote VM).
- Tách luồng `System.in`, `System.out` và `System.err` của snippet khỏi luồng console của host, để nhận đầu vào, lưu log hoặc hiển thị trong UI.
- Đọc **trạng thái, lỗi biên dịch và exception** của snippet qua API, thay vì chỉ dò chuỗi console.
- Quản lý vòng đời, tránh chạy snippet đồng thời trên một `JShell` và xử lý rủi ro khi chạy Java code động.

**Đề bài này tập trung đúng giai đoạn khởi tạo và cấu hình JShell nhúng:** `JShell.create()` / `JShell.builder()`, `compilerOptions`, `remoteVMOptions`, `addToClasspath`, `in`, `out`, `err`. Các phần về evaluation và diagnostics được trình bày đủ để chứng minh cấu hình hoạt động.

> **Ý chính:** Host JVM, trình biên dịch/phân tích snippet và môi trường **thực thi** snippet có thể có cấu hình khác nhau. Đừng coi `compilerOptions`, `remoteVMOptions` và `addToClasspath` là ba cách viết của cùng một cấu hình.

## 2. Thành phần trong một ứng dụng JShell nhúng

Sơ đồ luồng dữ liệu thường gặp với execution engine mặc định:

~~~text
Host JVM
  |
  +-- Java code gọi JShell.builder() / JShell.eval()
  |       |
  |       +-- compiler / source analysis
  |       |      +-- compilerOptions(...)
  |       |      +-- classpath cho snippet
  |       |
  |       +-- SnippetEvent, Diag, status, exception
  |       |
  |       +-- execution engine (mặc định: remote process)
  |                +-- remoteVMOptions(...)
  |                +-- System.in  <-- Builder.in(...)
  |                +-- System.out --> Builder.out(...)
  |                +-- System.err --> Builder.err(...)
  |
  +-- code host quyết định log, UI, lưu dữ liệu, timeout, close
~~~

Ở cấu hình mặc định của Java 17, engine tạo **tiến trình thực thi từ xa** cho snippet và tài liệu yêu cầu đóng `JShell` để giải phóng tài nguyên. Nhưng API `JShell.Builder.executionEngine(...)` cho phép thay engine; do đó không nên mặc định mọi cấu hình tùy chỉnh đều tạo tiến trình remote giống mặc định.

Để sử dụng API trong chương trình, các kiểu quan trọng bao gồm:

~~~java
import jdk.jshell.JShell;
import jdk.jshell.Snippet;
import jdk.jshell.SnippetEvent;
import jdk.jshell.Diag;
~~~

Đây là các import minh họa (không phải chương trình độc lập). Module chứa các kiểu này là `jdk.jshell`, không phải `java.base`. Nếu dùng một **explicit named module** của host, cần khai báo dependency tới `jdk.jshell` trong `module-info.java`:

~~~java
module demo.host {
    requires jdk.jshell;
}
~~~

Trong các ví dụ classpath/unnamed module bên dưới, ta biên dịch và chạy với `--add-modules jdk.jshell` để yêu cầu module công cụ này tham gia graph rõ ràng. Runtime image được đóng gói tối giản bằng `jlink` có thể không chứa `jdk.jshell`: cần kiểm tra module có sẵn thay vì mặc định mọi JRE thu gọn đều có API này.

## 3. Khởi tạo nhanh và khởi tạo có tùy chỉnh

### 3.1. Mặc định: `JShell.create()`

Nếu không có yêu cầu cấu hình đặc biệt:

~~~java
try (JShell shell = JShell.create()) {
    shell.eval("int x = 2 + 3;");
}
~~~

Đoạn này cần import `jdk.jshell.JShell` và đặt bên trong một method. `JShell.create()` tương đương `JShell.builder().build()`. `JShell` implement `AutoCloseable` nên nên dùng `try-with-resources` để gọi `close()` kể cả khi có exception.

Mặc định `JShell.Builder.out` và `err` dùng `System.out` / `System.err` của phía điều khiển; **đầu vào của snippet mặc định là stream rỗng** (không phải mặc định gắn với `System.in` của host). Vì vậy, snippet đọc `System.in` mà host không cấu hình input có thể gặp EOF hoặc thất bại khi chờ một dòng.

### 3.2. Tùy chỉnh: `JShell.builder()`

~~~java
JShell shell = JShell.builder()
        .in(snippetInput)
        .out(snippetOutput)
        .err(snippetError)
        .compilerOptions("-Xlint:deprecation")
        .remoteVMOptions("-Ddemo.mode=embedded")
        .build();
~~~

Đây là **đoạn API tích hợp**, không phải chương trình độc lập: `snippetInput` cần là `InputStream`, `snippetOutput` và `snippetError` là `PrintStream`. Tạo stream trước khi build, đóng engine và các stream theo vòng đời phù hợp.

Các phương thức cấu hình của `Builder` có thể chain; việc `build()` tạo JShell state engine là bước tách biệt với việc gửi snippet qua `eval`.

| Phương thức | Mục đích | Không nên nhầm với |
|---|---|---|
| `JShell.create()` | Khởi tạo nhanh với mặc định | JShell CLI có prompt |
| `JShell.builder().build()` | Tương đương `create()` khi không cấu hình gì | Tự động nạp thư viện ngoài |
| `Builder.in(InputStream)` | Nguồn `System.in` cho code được eval | Chuỗi snippet gửi tới `eval(String)` |
| `Builder.out(PrintStream)` | Nơi snippet ghi `System.out` | `SnippetEvent.value()` |
| `Builder.err(PrintStream)` | Nơi snippet ghi `System.err` | Danh sách `Diag` của compiler |
| `Builder.compilerOptions(String...)` | Tùy chọn bổ sung cho compiler khi parse/analyze/generate snippet | Tham số khởi động remote JVM |
| `Builder.remoteVMOptions(String...)` | Tùy chọn VM cho engine khởi chạy remote JVM | Compiler flags hoặc tham số JVM host |
| `JShell.addToClasspath(String)` | Bổ sung path vào cuối classpath mà `eval` sử dụng | Thêm JAR vào classpath của JVM host đang chạy |
| `Builder.fileManager(...)` | Điều chỉnh Java file manager cho compilation/source analysis khi thật sự cần | Thêm JAR đơn giản bằng `addToClasspath` |
| `Builder.executionEngine(...)` | Chọn hoặc cấu hình execution control engine | Một cách thay đổi compiler flags |

Các API trên là **Java API thật**, không phải pseudo-configuration. Đừng sao chép cú pháp lệnh của JShell CLI như `/env` hoặc `/open` rồi coi đó là Java statement hợp lệ trong `eval(String)`.

## 4. Cấu hình classpath để snippet thấy thư viện

### 4.1. Vì sao host thấy thư viện nhưng snippet không thấy?

Một ứng dụng có thể chạy trên host JVM với classpath riêng nhưng snippet được biên dịch và thực thi trong môi trường JShell. Bạn **không nên suy luận** rằng mọi class loader, module, JAR hoặc đường dẫn của host luôn được JShell nhìn thấy tự động.

API đúng khi cần đưa một thư viện vào classpath cho `eval` là:

~~~java
shell.addToClasspath(pathToLibrary);
~~~

Trong đó `pathToLibrary` là chuỗi đường dẫn phù hợp, ví dụ thư mục chứa các file `.class` đã compile hoặc đường dẫn JAR. API `addToClasspath(String)` **thêm path ở cuối classpath dùng cho `eval()`**. Nên gọi trước những snippet phụ thuộc path này để việc kiểm chứng thứ tự dễ hiểu và hạn chế trạng thái bị thay đổi giữa phiên.

Ví dụ mã tích hợp:

~~~java
Path library = Path.of("lib", "example-api.jar").toAbsolutePath();
shell.addToClasspath(library.toString());
shell.eval("import com.example.api.Greeting;");
~~~

Đoạn trên cần có `java.nio.file.Path`, một `JShell shell` đang mở và JAR thực sự chứa package/class đó; mã chỉ minh họa, không phải một chương trình chạy được khi JAR chưa tồn tại.

### 4.2. Đường dẫn thư mục và đường dẫn JAR

Có hai dạng thường gặp:

~~~text
lib-classes/
  demo/lib/TextTools.class
~~~

hoặc:

~~~text
libs/example.jar
  demo/lib/TextTools.class
~~~

Với thư mục chứa class, truyền **root của package tree** (ví dụ `lib-classes`, không phải `lib-classes/demo/lib`); với JAR, truyền path của JAR. Dùng `Path.toAbsolutePath()` để tránh nhầm working directory.

Lưu ý: `JShell.addToClasspath` là **đường tìm class phục vụ evaluation**, không phải thao tác copy file và không tự biên dịch `.java`. Cần biên dịch thư viện thành `.class` hoặc đóng gói JAR từ trước. Nó không thay `--module-path`/module resolution khi ứng dụng dùng named modules; ví dụ chính bên dưới dùng classpath để tránh trộn lẫn bài toán JPMS.

### 4.3. `addToClasspath` và `compilerOptions` không tương đương

`compilerOptions` chuyển tùy chọn bổ sung vào các compiler invocations liên quan parse, analysis và code generation của JShell. Dù một số tùy chọn javac có liên hệ đến đường tìm class, **cách chuyên biệt và dễ kiểm soát** để bổ sung JAR/thư mục cho snippet là `addToClasspath`. Đặc tả cảnh báo các compiler option làm nhiễu hoạt động JShell là không được hỗ trợ và có tác động không xác định.

Đừng dùng `compilerOptions("-classpath", "...")` như một thao tác thay thế vô điều kiện cho `addToClasspath(...)`, hoặc nghĩ rằng `--class-path` của lệnh `java` khởi động host sẽ tự di chuyển toàn bộ classpath đến một remote engine.

### 4.4. Khi nào thêm classpath?

Trong ví dụ chạy được, thứ tự là:

~~~text
1. Biên dịch TextTools.java → lib-classes/
2. Khởi tạo JShell bằng Builder
3. shell.addToClasspath(lib-classes)
4. shell.eval("import demo.lib.TextTools;")
5. shell.eval("System.out.println(TextTools.transform(\"java\"));")
6. Đọc events, captured stdout
7. close()
~~~

Tách hai pha compile giúp minh bạch: **library** được javac biên dịch trước; **snippet** được JShell biên dịch khi `eval`. Nếu tên package hoặc thư mục class sai, lệnh import có thể bị từ chối; khi đó cần kiểm tra `Snippet.Status` và diagnostics chứ không chỉ nhìn console.

## 5. Compiler options: ảnh hưởng đến phân tích/biên dịch snippet

`JShell.Builder.compilerOptions(String... options)` bổ sung các tùy chọn cho compiler mà JShell dùng để parse, phân tích và sinh code. Ví dụ được dùng trong chương trình đầy đủ:

~~~java
.compilerOptions("-Xlint:deprecation")
~~~

Đây là ví dụ một tùy chọn lint bổ sung tương thích JShell trong môi trường chạy đã kiểm tra. Nó **không** có nghĩa snippet hoặc host bắt buộc bật lint, và không tự khiến warning xuất hiện nếu mã không dùng API deprecated.

Nguyên tắc:

- Chỉ truyền những option mà Java compiler/JShell hỗ trợ trong bối cảnh đó.
- Không nhét tùy chọn JVM như `-Xmx256m` hoặc `-Ddemo.mode=embedded` vào `compilerOptions`. Đây là VM options, không phải javac flags.
- Không giả định mọi option của lệnh độc lập `javac` đều hợp lệ với compiler nhúng JShell. API Java 17 nói rõ **các tùy chọn gây nhiễu JShell có tác dụng không xác định**.
- Khi muốn đổi chính sách source/target language, module accessibility hoặc annotation processing, cần kiểm tra thật trên JDK mục tiêu; đừng dùng các tổ hợp `--release`/`--module-path` như giải pháp tổng quát khi chưa xác minh.
- `compilerOptions` thiết lập qua `Builder` trước `build()`. Khi chỉ cần bổ sung dependency classpath **sau** khi đã build, dùng `shell.addToClasspath(...)`.

Điểm này đặc biệt quan trọng vì chương trình ví dụ bên dưới có **hai giai đoạn compile** khác nhau: `javac --release 17` được dùng bên ngoài để biên dịch host/library, còn `compilerOptions("-Xlint:deprecation")` là option của **compiler bên trong JShell**.

## 6. Remote VM options: ảnh hưởng tới nơi snippet thực thi

Với execution engine mặc định dùng remote process, `Builder.remoteVMOptions(String... options)` đặt các tùy chọn JVM bổ sung cho tiến trình thực thi snippet:

~~~java
.remoteVMOptions("-Ddemo.mode=embedded")
~~~

Vì thế trong snippet:

~~~java
System.out.println(System.getProperty("demo.mode"));
~~~

có thể in ra:

~~~text
embedded
~~~

Đây là một snippet Java chạy ở môi trường evaluation; khi gọi `System.getProperty` ở host JVM, kết quả có thể khác, vì **host và remote VM là hai môi trường riêng**. Đoạn in `embedded` chỉ đúng khi dùng Builder option trên cùng session và execution engine triển khai remote VM tương ứng.

So sánh:

| Nơi bạn đặt tùy chọn | Ví dụ | Đối tượng chịu tác động |
|---|---|---|
| Lệnh khởi động host JVM | `java -Xmx512m -cp out EmbeddedShellDemo ...` | Host JVM |
| `Builder.remoteVMOptions(...)` | `"-Ddemo.mode=embedded"` | Remote execution VM do engine tạo |
| `Builder.compilerOptions(...)` | `"-Xlint:deprecation"` | Compiler xử lý snippet |
| `shell.addToClasspath(...)` | Path tới `lib-classes` hoặc JAR | Classpath để evaluate snippet |

Không phải mọi execution engine tùy chỉnh đều khởi chạy remote VM: đặc tả `jdk.jshell.spi.ExecutionEnv` mô tả extra VM options là lời đề xuất cho engine; engine có thể không tạo remote process. Do đó không khẳng định `remoteVMOptions` sẽ tác động lên mọi engine theo cách giống nhau.

Đối với cấu hình tài nguyên/memory, đặt giới hạn theo đúng tiến trình cần giới hạn. Một option `-Xmx` của **host** không đồng nghĩa giới hạn heap của **remote process** khi snippet thực thi.

## 7. Cấu hình `System.in` cho snippet

### 7.1. Đầu vào dành cho code được eval, không phải source

`Builder.in(InputStream in)` ánh xạ một `InputStream` do host cung cấp thành `System.in` ở phía code được eval:

~~~java
.in(new ByteArrayInputStream(
        "Ada\n".getBytes(StandardCharsets.UTF_8)))
~~~

Đây là đoạn Builder tích hợp; cần import `java.io.ByteArrayInputStream` và `java.nio.charset.StandardCharsets`. Một snippet sau đó có thể đọc:

~~~java
System.out.println(
    "input=" + new java.util.Scanner(System.in).nextLine());
~~~

Với stream chứa `Ada\n`, snippet in `input=Ada`. Ngược lại, chuỗi đầu vào của `JShell.eval(String source)` là **mã Java**, không phải dữ liệu được đẩy vào `System.in`.

### 7.2. Nếu không thiết lập `in`

Theo Javadoc Java 17, mặc định Builder cấp **input stream rỗng** cho evaluation. Nếu snippet gọi `Scanner.nextLine()` khi không có dòng nào, nó có thể ném `NoSuchElementException`; code dùng `BufferedReader.readLine()` có thể nhận `null`. Host nên cấu hình input khi ứng dụng thực sự cần tương tác.

Đừng cấp bừa `System.in` của host vào `Builder.in` trong một chương trình mà host đồng thời cũng đọc console: Javadoc cảnh báo việc cùng dùng `System.in` cho nhập snippet và nhập của ứng dụng có thể xung đột. Một UI/HTTP server thường dùng hàng đợi hoặc stream được quản lý riêng, có quy tắc cấp dữ liệu cho từng phiên.

### 7.3. Ngắt việc đọc input

Javadoc cho phép phương thức `InputStream.read` ném `InterruptedIOException` để báo người dùng hủy input; snippet đang chạy có thể được dừng theo cơ chế JShell. Tuy vậy, **không** nên xem đây là đảm bảo timeout cứng hoặc dừng được mọi mã Java. Một snippet có vòng lặp lâu hoặc bị block ở thư viện khác có thể cần xử lý timeout ở cấp execution engine/process.

## 8. Cấu hình `System.out` và `System.err`

`Builder.out(PrintStream)` và `Builder.err(PrintStream)` định tuyến output và error output **do code evaluation ghi**. Mặc định chúng dùng `System.out` và `System.err`, nhưng ứng dụng nhúng có thể ghi vào buffer, log file hoặc bridge tới UI.

Đoạn tối giản:

~~~java
ByteArrayOutputStream stdoutBytes = new ByteArrayOutputStream();
ByteArrayOutputStream stderrBytes = new ByteArrayOutputStream();

try (PrintStream jsOut = new PrintStream(
             stdoutBytes, true, StandardCharsets.UTF_8);
     PrintStream jsErr = new PrintStream(
             stderrBytes, true, StandardCharsets.UTF_8);
     JShell jshell = JShell.builder()
             .out(jsOut)
             .err(jsErr)
             .build()) {

    jshell.eval("System.out.println(\"Hello from snippet\");");
    jshell.eval("System.err.println(\"Error stream from snippet\");");
}
~~~

Đây là **đoạn Java tích hợp**, cần import `ByteArrayOutputStream`, `PrintStream`, `StandardCharsets` và `JShell`. Host đọc `stdoutBytes.toString(StandardCharsets.UTF_8)` và `stderrBytes...` sau khi eval/close.

**Phân biệt ba loại kết quả:**

1. **Standard output** từ `System.out.print*` trong snippet → `Builder.out`.
2. **Error output** từ `System.err.print*` trong snippet → `Builder.err`.
3. **Trạng thái, giá trị biểu thức, diagnostics và exception của JShell** → `SnippetEvent`, `JShell.diagnostics(Snippet)`, `SnippetEvent.value()`, `SnippetEvent.exception()`; **không mặc định** được JShell in như transcript REPL lên output stream.

Ví dụ khi gọi `jshell.eval("1 + 2")`, API có thể tạo sự kiện expression với `event.value()` bằng chuỗi `"3"`; đừng mặc định một dòng `3` tự xuất hiện trên `Builder.out` như console REPL. Nếu UI muốn hiển thị giá trị, host phải xây một phần trình bày dựa vào event.

Nên dùng encoding thống nhất, ví dụ UTF-8 ở cả `PrintStream` và `ByteArrayOutputStream.toString(StandardCharsets.UTF_8)`. Nếu hiển thị trong UI, không để một session dùng chung mutable output stream của nhiều user mà thiếu định tuyến và kiểm soát đồng thời.

## 9. Ví dụ hoàn chỉnh Java 17+: thư viện riêng + JShell nhúng

Ví dụ kiểm tra bốn yêu cầu cùng lúc:

1. Biên dịch một thư viện `demo.lib.TextTools` **ngoài classpath của host** rồi đưa vào classpath của snippet bằng `addToClasspath`.
2. Dùng `compilerOptions("-Xlint:deprecation")`.
3. Đặt system property của remote VM bằng `remoteVMOptions("-Ddemo.mode=embedded")`.
4. Chuyển `System.in`, `System.out`, `System.err` của snippet vào các stream do host quản lý và đọc events.

### 9.1. Cấu trúc thư mục

~~~text
embedded-jshell/
  demo/
    lib/
      TextTools.java
  EmbeddedShellDemo.java
  lib-classes/     (do javac tạo)
  out/             (do javac tạo)
~~~

Hai file nguồn đều là Java 17 hợp lệ. Không dùng Maven/Gradle, reflection tùy chỉnh hoặc JAR ngoài.

### 9.2. Thư viện: `demo/lib/TextTools.java`

~~~java
package demo.lib;
import java.util.Locale;

public final class TextTools {
    private TextTools() {}

    public static String transform(String source) {
        return "lib:" + source.toUpperCase(Locale.ROOT);
    }
}
~~~

`TextTools.transform("java")` sẽ trả về `lib:JAVA`. Host JVM sẽ được chạy với classpath chỉ chứa `out`, do đó thư viện này phải được đưa riêng vào môi trường evaluation của JShell. `Locale.ROOT` giúp phép upper-case ổn định bất kể locale mặc định của hệ điều hành.

### 9.3. Host: `EmbeddedShellDemo.java`

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.List;
import jdk.jshell.JShell;
import jdk.jshell.Snippet;
import jdk.jshell.SnippetEvent;

public final class EmbeddedShellDemo {
    public static void main(String[] args) throws Exception {
        Path libraryClasses = Path.of(args[0]).toAbsolutePath();
        ByteArrayOutputStream capturedOut = new ByteArrayOutputStream();
        ByteArrayOutputStream capturedErr = new ByteArrayOutputStream();

        try (PrintStream snippetOut = new PrintStream(capturedOut, true, StandardCharsets.UTF_8);
             PrintStream snippetErr = new PrintStream(capturedErr, true, StandardCharsets.UTF_8);
             JShell shell = JShell.builder()
                     .in(new ByteArrayInputStream("Ada\n".getBytes(StandardCharsets.UTF_8)))
                     .out(snippetOut)
                     .err(snippetErr)
                     .compilerOptions("-Xlint:deprecation")
                     .remoteVMOptions("-Ddemo.mode=embedded")
                     .build()) {
            shell.addToClasspath(libraryClasses.toString());
            check(shell, "import demo.lib.TextTools;");
            check(shell, "System.out.println(TextTools.transform(\"java\"));");
            check(shell, "System.out.println(\"mode=\" + System.getProperty(\"demo.mode\"));");
            check(shell, "System.out.println(\"input=\" + new java.util.Scanner(System.in).nextLine());");
            check(shell, "System.err.println(\"snippet-warning\");");
        }

        System.out.println("snippet stdout:");
        System.out.print(capturedOut.toString(StandardCharsets.UTF_8).replace("\r\n", "\n"));
        System.out.println("snippet stderr:");
        System.out.print(capturedErr.toString(StandardCharsets.UTF_8).replace("\r\n", "\n"));
    }

    private static void check(JShell shell, String source) {
        List<SnippetEvent> events = shell.eval(source);
        if (events.isEmpty() || events.stream().anyMatch(e ->
                e.status() != Snippet.Status.VALID || e.exception() != null)) {
            throw new IllegalStateException("JShell eval failed: " + source);
        }
    }
}
~~~

### 9.4. Biên dịch, chạy và kết quả kiểm chứng

Đứng trong thư mục `embedded-jshell/`, dùng Bash (Linux, macOS hoặc Git Bash):

~~~bash
mkdir -p lib-classes out

javac --release 17 -d lib-classes demo/lib/TextTools.java
javac --release 17 --add-modules jdk.jshell -d out EmbeddedShellDemo.java

java --add-modules jdk.jshell -cp out EmbeddedShellDemo lib-classes
~~~

Lưu ý:

- `lib-classes` chỉ chứa thư viện; `out` chứa host. Khi chạy `java -cp out`, thư viện không có sẵn trên application classpath của host; đường dẫn `lib-classes` được truyền vào `main` làm tham số rồi đưa cho `shell.addToClasspath(...)`.
- `javac --release 17` bảo đảm các API và cú pháp của source tương thích Java 17. Cờ `--add-modules jdk.jshell` xác định module chứa API nhúng khi compile/chạy ứng dụng trên classpath.
- Tham số cuối `lib-classes` là **một đường dẫn**. Nếu thay bằng đường dẫn thư mục có khoảng trắng, bảo đảm quote argument theo shell.
- Dùng JDK 17+ có module `jdk.jshell`; runtime image tối giản thiếu module này sẽ không chạy được.

Đầu ra đã được kiểm tra thực tế khi biên dịch bằng `javac --release 17` và chạy trên JDK 24:

~~~text
snippet stdout:
lib:JAVA
mode=embedded
input=Ada
snippet stderr:
snippet-warning
~~~

Đầu ra trên cho thấy rõ:

- `lib:JAVA`: snippet import thành công `TextTools` **chỉ sau khi `addToClasspath`**.
- `mode=embedded`: JVM thực thi snippet nhận property từ `remoteVMOptions`.
- `input=Ada`: `Scanner(System.in)` trong snippet đọc từ `ByteArrayInputStream` do Builder cung cấp.
- `snippet-warning`: snippet ghi `System.err` vào buffer riêng, không trộn với stdout.
- Các dòng `snippet stdout:` / `snippet stderr:` là **host tự in** sau khi JShell đóng, không phải prompt hay kết quả mặc định của giao diện JShell CLI.

`check(shell, source)` xác thực mỗi snippet của ví dụ chỉ có trạng thái `VALID` và không có exception. Đây là helper **cố ý nghiêm ngặt** cho năm snippet rất đơn giản; một host REPL đầy đủ nên hỗ trợ nhiều kiểu event, các trạng thái như `RECOVERABLE_DEFINED` và thay đổi phụ thuộc, thay vì coi mọi event không-`VALID` là lỗi nghiêm trọng.

### 9.5. Vì sao dùng `try-with-resources`?

`JShell` implement `AutoCloseable`. Với execution engine mặc định, `build()` tạo remote process; đóng engine giúp giải phóng tài nguyên khi chương trình kết thúc hoặc có lỗi. Output streams cũng được đóng sau phiên; trong ví dụ byte buffer vẫn có thể đọc được sau khi đóng `PrintStream`.

Khi tích hợp vào ứng dụng server, quản lý vòng đời theo session/user. Không mở JShell mới cho mọi ký tự nhập, không giữ remote process vô hạn, và không gọi `close()` khi còn snippet đang sử dụng session mà không có chính sách dừng/timeout rõ ràng.

## 10. Đọc sự kiện, diagnostics và exception thay vì đoán qua stdout

`JShell.eval(String)` trả `List<SnippetEvent>`, không trả trực tiếp một chuỗi giống transcript của CLI. Một event có:

- `status()`: ví dụ `VALID`, `REJECTED`, `RECOVERABLE_DEFINED`, `OVERWRITTEN` (tùy ngữ cảnh).
- `snippet()`: đối tượng snippet liên quan; dùng với `shell.diagnostics(snippet)`.
- `value()`: biểu diễn chuỗi của một giá trị được đánh giá khi thích hợp; có thể `null` với những snippet không tạo giá trị.
- `exception()`: exception từ runtime evaluation theo cơ chế API; có thể `null`.
- `causeSnippet()` và các thông tin liên quan để phân biệt thay đổi trực tiếp và thay đổi do dependency.

Khi một import hoặc biểu thức không hợp lệ, host có thể đọc diagnostics như sau:

~~~java
List<SnippetEvent> events = shell.eval("import missing.pkg.Type;");
for (SnippetEvent event : events) {
    System.out.println("status=" + event.status());
    shell.diagnostics(event.snippet())
         .forEach(d -> System.out.println(
                 d.getMessage(java.util.Locale.ROOT)));
}
~~~

Đây là **đoạn minh họa bên trong method** có biến `JShell shell`, import `jdk.jshell.SnippetEvent` và `java.util.List`. Không nên coi văn bản lỗi compiler là output ổn định giữa các phiên bản JDK; khi xây UI, nên hiển thị status, diagnostic code, vị trí và message lấy từ chính API.

### Nhiều snippet trong một input

Đặc tả `JShell.eval` yêu cầu input là **một snippet Java hoàn chỉnh** (declaration, expression, statement, import, v.v.). Nếu người dùng gửi một buffer chứa nhiều snippet, đừng ném toàn bộ chuỗi vào `eval` mà mặc định engine sẽ phân chia đúng. Dùng `JShell.sourceCodeAnalysis().analyzeCompletion(...)` để tách/căn cứ trạng thái hoàn chỉnh trước khi eval. Trường hợp này tách biệt với `Builder.in`: **input của eval là mã**, còn stream `in` là **dữ liệu runtime** mà đoạn mã ấy đọc.

### Vì sao không chỉ đọc `Builder.err`?

Lỗi compile snippet và output người dùng ghi ra `System.err` là hai kênh khác nhau. Một snippet có thể bị `REJECTED` nhưng không có dòng nào được “in” vào `Builder.err`; ngược lại, một snippet `VALID` có thể cố ý gọi `System.err.println("warning")`. Kết hợp **events + diagnostics + output streams** mới là dữ liệu đủ để hiển thị một phiên JShell nhúng.

## 11. Tùy chọn nâng cao của Builder: chỉ dùng khi cần

Ngoài các cấu hình chính, Java 17 có:

### `fileManager(Function<StandardJavaFileManager, StandardJavaFileManager>)`

Dùng để điều chỉnh Java file manager phục vụ compilation và source analysis; có ích khi ứng dụng có cơ chế file/directory/library đặc biệt và phải can thiệp vào cách compiler thấy nguồn hoặc output. Đối với nhu cầu thêm thư viện Java bình thường, **`addToClasspath` đơn giản hơn**.

Ví dụ chữ ký API:

~~~java
JShell.Builder builder = JShell.builder()
        .fileManager(existing -> existing);
~~~

Đây là đoạn minh họa sử dụng identity mapping, không thay đổi hành vi; không phải cơ chế thêm classpath. Viết custom file manager cần nắm `javax.tools.JavaFileManager` và quy tắc compiler của JShell.

### `executionEngine(...)`

Dùng để chọn provider hoặc đặc tả execution control khi bạn chủ động cần engine khác mặc định. Chỉ nên đặt tối đa **một overload `executionEngine`** trên Builder. Khi thay engine, việc route I/O, remote VM options, cô lập process và dừng snippet phụ thuộc hợp đồng của engine ấy.

### `idGenerator(...)` và `tempVariableNameGenerator(...)`

Các API này phục vụ việc đặt tên/id cho snippets/temporary variables. Chúng không phải cấu hình classpath, compiler flags hoặc I/O. Callback của generator có hạn chế truy cập `JShell` trong lúc trạng thái đang cập nhật; không nên tùy tiện gọi lại `eval` trong callback.

Đối với ứng dụng vừa học cách nhúng JShell, hãy bắt đầu bằng `builder().in().out().err().compilerOptions().remoteVMOptions().build()` và `addToClasspath`; chỉ mở rộng Builder khi có yêu cầu kỹ thuật cụ thể.

## 12. Những lỗi phổ biến và hướng chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `package jdk.jshell does not exist` hoặc không thấy API JShell | Compile trên runtime image/JDK thiếu `jdk.jshell` hoặc module không tham gia graph | Kiểm tra JDK 17+, `java --list-modules` và cấu hình `--add-modules jdk.jshell`/`requires jdk.jshell` |
| `ToolProvider` hoạt động nhưng `JShell.build()` thất bại | Thiếu thành phần của JDK/engine hoặc môi trường không thể tạo execution environment | Đọc nguyên nhân `IllegalStateException`, kiểm tra runtime image và quyền tạo process |
| `import com.example.X` bị `REJECTED` | Thư viện không trên snippet classpath hoặc package/class name sai | Biên dịch dependency, truyền root của package tree/JAR qua `addToClasspath`, xem diagnostics |
| Host import được class nhưng snippet không thấy | Classpath/loader của host khác môi trường evaluation | Cấu hình classpath **của snippet**, không chỉ classpath của host |
| Cấu hình `compilerOptions("-Dkey=value")` không cho hiệu ứng mong muốn | Trộn JVM option với compiler option | Chuyển sang `remoteVMOptions` khi property cần trong remote execution VM |
| `remoteVMOptions("-D...")` nhưng host `System.getProperty` không đổi | Option đặt cho VM thực thi snippet, không phải host | Kiểm tra property bằng snippet; phân biệt hai JVM |
| Snippet gọi `Scanner(System.in).nextLine()` bị EOF | `Builder.in` mặc định stream rỗng hoặc stream cung cấp đã hết dữ liệu | Cấp input riêng có nội dung đúng format và quản lý vị trí đọc |
| Không thấy kết quả biểu thức dù `eval` trả về event | Giá trị nằm trong `SnippetEvent.value()`, không tự in trên stdout | Đọc events và xây transcript của host |
| Không có compiler error trong `Builder.err` | Compiler diagnostics không phải `System.err` của snippet | Dùng `shell.diagnostics(event.snippet())` |
| Output của hai user trộn nhau | Dùng chung buffer/stream/session không có điều phối | Cấp session stream riêng, serialize evaluation và áp dụng giới hạn |
| Host treo khi snippet chạy lâu | `eval` đồng bộ chờ code thực thi hoặc code bị block ở input/I/O | Timeout có chính sách, giới hạn tài nguyên ở execution engine/process; `stop()` là best effort |
| Remote VM không áp dụng `-D...` với custom engine | Engine không khởi tạo remote VM hoặc xử lý option khác | Đọc tài liệu `ExecutionControlProvider`/`ExecutionEnv` và kiểm chứng engine thực tế |
| Đã `close` mà vẫn gọi `eval` | JShell đã đóng | Không tái sử dụng; tạo session mới nếu cần |
| Classpath mới trỏ tới JAR đã thay nhưng còn thấy class cũ | Class đã nạp và state/loader còn lưu | Tạo session/loader mới; không kỳ vọng đổi bytecode class đã định nghĩa |

Cách debug hiệu quả là log **các thông tin tách biệt**: classpath thực tế đã đưa vào shell, các Builder option, `SnippetEvent.status`, diagnostics, exception, captured stdout/stderr và chính xác snippet đang chạy. Không dựa vào việc “không in gì” để suy ra compile failure.

## 13. Vòng đời, đa luồng và giới hạn an toàn

### 13.1. `JShell` không thread-safe

Javadoc chỉ ra `JShell` **không thread-safe**, trừ một số thao tác được ghi riêng. Một web server không nên cho nhiều request gọi `eval`, `drop`, `addToClasspath` trên cùng engine đồng thời. Dùng executor/queue cho mỗi session, đồng bộ hóa trên tầng host và bảo đảm output/diagnostics gắn đúng request. Nếu cần chạy nhiều user độc lập, thường nên dùng session riêng và quota rõ ràng.

### 13.2. Không coi JShell là sandbox

JShell cho phép thực thi Java code động; snippet có thể dùng các API để đọc file, gọi mạng, tạo thread hoặc tiêu thụ CPU/memory trong phạm vi quyền được cấp. Việc tạo process riêng bằng default engine **không tự đảm bảo an toàn**, bởi process đó vẫn có thể chạy với quyền hệ điều hành của host.

Với nội dung không tin cậy, dùng thêm các biện pháp hệ điều hành/container, tài khoản giới hạn, filesystem/network policy, CPU/memory/time quotas và quản lý process. `JShell.stop()` chỉ cố gắng dừng snippet đang chạy; Javadoc nói rõ có tình huống không thể dừng, ví dụ bị block ở I/O. Không dùng `stop()` như đảm bảo vô điều kiện.

### 13.3. Quản lý stream và bộ nhớ

`ByteArrayOutputStream` tiện cho ví dụ nhỏ nhưng nếu snippet in vô hạn, buffer có thể chiếm toàn bộ heap host. Production nên dùng stream có giới hạn, cơ chế backpressure hoặc append log có quota, kèm chiến lược giữ lại một phần đầu/cuối output. Đừng giữ mọi `SnippetEvent` và toàn bộ output không giới hạn.

Khi session kết thúc, `close()` `JShell` để giải phóng tài nguyên. Nếu UI hủy một evaluation, cần điều phối việc `stop`/đóng engine và xử lý trạng thái cuối, không vừa đóng vừa cho request khác tái sử dụng session.

### 13.4. Phân biệt dữ liệu input với code input

- `shell.eval("...")`: **mã nguồn Java** được đánh giá.
- `Builder.in(input)`: **byte stream runtime** để đoạn mã đó đọc qua `System.in`.
- `Builder.out/err(stream)`: **byte/output channel runtime** của snippet.
- `SnippetEvent` và `Diag`: **metadata và kết quả** do host lấy từ API.

Đây là bốn kênh khác nhau. Định nghĩa hợp đồng cho từng kênh giúp tránh nhầm quyền, dấu xuống dòng, encoding và vòng đời stream.

## 14. Checklist khi triển khai JShell nhúng

1. Đã chọn JDK/runtime image có `jdk.jshell` chưa?
2. Có sử dụng `JShell.builder()` khi cần I/O/compiler/remote VM options thay vì chỉ `create()`?
3. Input/Output/Error stream do host cấp riêng và có vòng đời rõ ràng chưa?
4. Đã xác định class/JAR nào **snippet cần nhìn thấy**, và dùng `addToClasspath` với path đúng?
5. Có phân biệt `compilerOptions` với `remoteVMOptions` và JVM option của host?
6. Nếu snippet cần đọc `System.in`, đã cấp stream có nội dung hay cơ chế cấp input động chưa?
7. Có xử lý `SnippetEvent.status/value/exception` và `JShell.diagnostics`, thay vì chỉ in stdout/stderr?
8. Có tách input thành các snippet hoàn chỉnh trước khi gọi `eval`?
9. Có serialize các thao tác trên cùng `JShell` để tránh race condition?
10. Có đóng JShell, stream và xử lý timeout/quota, nhất là với code bên ngoài gửi tới?
11. Đã thử thực tế trên JDK/OS/execution engine sẽ triển khai chưa?

## 15. Tự kiểm tra nhanh

**1. Tạo một JShell nhúng với thiết lập mặc định bằng câu lệnh nào?**  
`JShell.create()` hoặc `JShell.builder().build()`.

**2. Đã có `libs/extra.jar` và muốn snippet `import` class bên trong. Dùng API nào?**  
`shell.addToClasspath(pathToJar)`, rồi kiểm tra `SnippetEvent` và diagnostics của import.

**3. `compilerOptions("-Xlint:deprecation")` có thay thế `remoteVMOptions("-Dapp.name=demo")` không?**  
Không. Một bên cấu hình compiler cho snippet, bên kia cấu hình VM thực thi snippet.

**4. Input stream cho `Builder.in` chứa `Ada\n`, còn `eval` chứa `System.in.read()`. Hai chuỗi này giống nhau không?**  
Không. `eval` nhận mã Java, `in` đưa dữ liệu cho code khi thực thi.

**5. Không gọi `Builder.in`, snippet dùng `Scanner(System.in).nextLine()` có luôn đọc từ console host không?**  
Không. Mặc định input stream cho evaluation là stream rỗng.

**6. `Builder.out` có tự in kết quả giá trị của mọi expression không?**  
Không. `SnippetEvent.value()` cung cấp giá trị của expression khi thích hợp; host quyết định cách trình bày.

**7. Khi snippet bị `REJECTED`, nên đọc log stderr hay diagnostics?**  
`JShell.diagnostics(snippet)` và status của event là nguồn chính xác cho compile diagnostic.

**8. `remoteVMOptions` có tác động lên host `System.getProperty` không?**  
Không phải mặc định. Khi dùng remote engine, option hướng tới VM chạy snippet.

**9. Có nên cho nhiều request web cùng gọi `eval` trên một `JShell` không?**  
Không tùy tiện; `JShell` không thread-safe. Cần serialize hoặc cấp session riêng.

**10. Đóng JShell có quan trọng dù ứng dụng host vẫn chạy?**  
Có. Execution engine mặc định tạo remote process và `close()` giải phóng tài nguyên session.

**Ghi nhớ:** để nhúng JShell đúng cách, dùng `Builder` tạo engine với các stream và options phù hợp, thêm classpath **cho snippet** qua `addToClasspath`, đánh giá từng snippet hoàn chỉnh và lấy kết quả bằng **events + diagnostics + captured I/O**, rồi đóng session. Cấu hình compiler, JVM host và remote execution VM là ba phạm vi cần phân biệt.

## Tài liệu tham khảo

- [Java SE 17 — `JShell`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jshell/jdk/jshell/JShell.html): `create`, `builder`, `eval`, `addToClasspath`, `diagnostics` và `close`.
- [Java SE 17 — `JShell.Builder`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jshell/jdk/jshell/JShell.Builder.html): `in`, `out`, `err`, `compilerOptions`, `remoteVMOptions`, `fileManager` và `executionEngine`.
- [Java SE 17 — `SnippetEvent`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jshell/jdk/jshell/SnippetEvent.html): status, value và exception theo event.
- [Java SE 17 — `SourceCodeAnalysis`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jshell/jdk/jshell/SourceCodeAnalysis.html): tách nguồn thành snippet hoàn chỉnh.
- [Java SE 17 — `ExecutionEnv`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jshell/jdk/jshell/spi/ExecutionEnv.html): luồng I/O và extra remote VM options cho execution engine.

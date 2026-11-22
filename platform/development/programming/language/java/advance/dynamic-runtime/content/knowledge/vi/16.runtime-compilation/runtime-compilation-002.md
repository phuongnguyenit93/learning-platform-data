# 16.2. Tìm compiler bằng ToolProvider và xử lý môi trường thiếu jdk.compiler

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xác định **system Java compiler** ở runtime bằng `javax.tools.ToolProvider.getSystemJavaCompiler()` và hiểu vì sao kết quả có thể là `null`.
2. Phân biệt **module `java.compiler`** (API như `JavaCompiler`, `JavaFileObject`, `ToolProvider`) với **module `jdk.compiler`** (triển khai trình biên dịch `javac` trong JDK).
3. Phân biệt hai loại `ToolProvider` dễ nhầm: `javax.tools.ToolProvider` và `java.util.spi.ToolProvider`; hiểu cái nào trả `JavaCompiler`, cái nào tìm công cụ CLI theo tên `"javac"`.
4. Phát hiện môi trường JDK đầy đủ, runtime image tạo bởi `jlink`, chương trình bị giới hạn modules hoặc container chỉ có runtime; đưa ra thông báo chẩn đoán rõ ràng khi thiếu compiler.
5. Viết chương trình Java 17+ **vẫn chạy được khi `java.compiler` không có trong boot layer**, thông qua một entrypoint chỉ dựa vào `java.base` và một helper chứa mã `javax.tools` được tải theo điều kiện.
6. Thực hiện một tác vụ biên dịch đơn giản bằng `JavaCompiler.getTask(...)` với diagnostics, options, file manager và thư mục đầu ra tạm.
7. Quyết định khi nào **fail fast**, khi nào đóng gói `jdk.compiler`, khi nào chuyển biên dịch sang build-time/external service, và hiểu giới hạn bảo mật của runtime compilation.

**Ngữ cảnh:** Ở chương **16. Biên dịch lúc chạy**, một ứng dụng có thể sinh mã Java khi đang hoạt động (plugin, DSL, rule engine, template compiler, testing tool). Không phải mọi JVM chạy ứng dụng đều có compiler. Một ứng dụng chạy tốt trên máy phát triển JDK có thể thất bại khi deploy vào runtime image gọn, container tối giản hoặc môi trường dùng `--limit-modules`. Bước đầu tiên trước mọi tác vụ compile là **phát hiện compiler và chọn chính sách fallback**.

## 1. “Chạy được Java” không đồng nghĩa “biên dịch được Java”

Từ Java 9, runtime được tổ chức theo **JPMS modules**. Phân biệt ba thành phần:

| Thành phần | Module | Vai trò | Câu hỏi cần hỏi |
| --- | --- | --- | --- |
| Java runtime cơ bản | `java.base` | Chạy bytecode, class loader, collections, filesystem, process, `ModuleLayer`... | Java program có thể chạy không? |
| Compiler APIs | `java.compiler` | Chứa `javax.tools.JavaCompiler`, `javax.tools.ToolProvider`, file managers và diagnostics | Code có truy cập được **API** Java compiler không? |
| System compiler implementation | `jdk.compiler` | Triển khai `javac`/system `JavaCompiler` và một số compiler APIs nội bộ | Runtime hiện tại có **compiler implementation** để compile không? |

Trong một runtime image tiêu chuẩn có đủ JDK modules, `javax.tools.ToolProvider.getSystemJavaCompiler()` thường trả một `JavaCompiler`. Nhưng nếu **`jdk.compiler` không có hoặc không khả dụng**, phương thức này có thể trả `null`, dù module `java.compiler` cùng các interface API vẫn hiện diện.

Ví dụ:
- Máy phát triển có JDK đầy đủ → thường có cả `java.compiler` và `jdk.compiler` → tìm được compiler.
- Runtime image `jlink` chỉ chứa `java.base` và một số application modules → có thể thiếu `java.compiler` lẫn `jdk.compiler`.
- Image có `java.compiler` để tải code tham chiếu API nhưng **không** có `jdk.compiler` → biên dịch hệ thống không sẵn có.
- JVM đang chạy với `--limit-modules` có thể **ẩn một module đối với quá trình khởi chạy hiện tại**, dù file của module còn nằm trong JDK trên đĩa.

**Kết luận thực hành:** Không suy diễn từ `java -version`, `java.home`, tên vendor, việc có Java runtime hay môi trường từng có JDK trong CI rằng `getSystemJavaCompiler()` chắc chắn khác `null`. Hãy **kiểm tra kết quả thực sự**.

## 2. Hai ToolProvider cùng tên nhưng khác hợp đồng

Đây là lỗi phổ biến khi import.

### 2.1. `javax.tools.ToolProvider` — lấy API compiler

Trong module `java.compiler`:

```java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    // Không có system Java compiler khả dụng qua API này.
}
```

Đây là đoạn minh họa đặt trong một method. Phương thức `getSystemJavaCompiler()` trả **`JavaCompiler` hoặc `null`**. Theo implementation note của Java SE 17, nó dùng compiler do `jdk.compiler` cung cấp nếu module đó khả dụng; ngược lại trả `null`.

`JavaCompiler` cung cấp các thao tác như:
- `getTask(...)`: xây một `CompilationTask` có thể thu diagnostics, options, units và annotation processing.
- `run(...)`: lối gọi tiện lợi theo giao diện `javax.tools.Tool`, nhận input/output streams và options, trả mã trạng thái.
- `getStandardFileManager(...)`: tạo standard file manager để đọc/ghi source/class files, quản lý filesystem, classpath và module path tùy cấu hình.

### 2.2. `java.util.spi.ToolProvider` — tìm công cụ theo tên

Trong module `java.base` có **một interface khác**:

```java
boolean javacToolFound =
        java.util.spi.ToolProvider.findFirst("javac").isPresent();
```

Nó tìm một **system tool provider** có tên `"javac"` thông qua cơ chế service provider. Nếu tìm được, có thể chạy công cụ qua phương thức `run(PrintWriter out, PrintWriter err, String... args)` của interface này.

**Nó không trả `javax.tools.JavaCompiler`**. Một đối tượng `java.util.spi.ToolProvider` không thể ép kiểu bừa thành `JavaCompiler`. Dùng tên fully qualified khi cần cả hai trong một file để tránh import nhầm.

| Nhu cầu | API | Loại giá trị |
| --- | --- | --- |
| Biên dịch qua file manager, JavaFileObject, diagnostic listener | `javax.tools.ToolProvider.getSystemJavaCompiler()` | `JavaCompiler` hoặc `null` |
| Kiểm tra công cụ tên `javac` có được đăng ký | `java.util.spi.ToolProvider.findFirst("javac")` | `Optional<ToolProvider>` |
| Tạo hẳn một tiến trình `javac` của OS | `ProcessBuilder` (nếu được phép và binary thực sự tồn tại) | `Process`; không đồng nghĩa JSR 199 |
| Lấy một compiler provider bên thứ ba | `ServiceLoader.load(JavaCompiler.class)` khi `java.compiler` hiện diện | Provider được đăng ký; không nhất thiết là system compiler |

Hai cách tìm trong bảng đầu có thể **cùng tồn tại** khi `jdk.compiler` khả dụng, nhưng phục vụ hai API khác nhau và không thay thế nhau trong mọi trường hợp.

### 2.3. Những cách phát hiện lỗi thời

Tránh dựa vào `tools.jar` hoặc `com.sun.tools.javac.Main` như là một API public ổn định. `tools.jar` gắn với các JDK cũ trước JPMS và không phải mô hình Java 17. `ToolProvider.getSystemToolClassLoader()` đã bị deprecated và theo Java SE 17 trả `null`; nó không phải cách chuẩn để “tìm javac” trên Java 17+.

## 3. Các trạng thái môi trường cần phân biệt

Một chẩn đoán cơ bản có ba phép kiểm tra độc lập:

```java
boolean api = ModuleLayer.boot()
        .findModule("java.compiler").isPresent();
boolean impl = ModuleLayer.boot()
        .findModule("jdk.compiler").isPresent();
boolean tool = java.util.spi.ToolProvider
        .findFirst("javac").isPresent();
```

Đây là đoạn minh họa nằm trong method; cả ba phép kiểm tra trên **chỉ dùng `java.base`**, không cần import `javax.tools`.

`ModuleLayer.boot().findModule(...)` báo module có được **resolve trong boot layer** của JVM đang chạy không, **không** đơn giản là hỏi module file có tồn tại trong JDK cài đặt không. Vì vậy nó phù hợp để quan sát môi trường thực thi hiện tại nhưng không nên xem là công cụ kiểm kê mọi module có thể nạp trên đĩa.

| Trạng thái | `java.compiler` | `jdk.compiler` | Ý nghĩa |
| --- | --- | --- | --- |
| Cả API và implementation khả dụng | Có | Có | Có thể thử `getSystemJavaCompiler()`; vẫn **kiểm tra null** |
| Chỉ compiler API | Có | Không | Có thể tải `javax.tools` nhưng system compiler thường `null` |
| Không có compiler API | Không | Không | Code phụ thuộc trực tiếp `javax.tools` có thể không load/link được; phải tránh gọi helper |
| Có provider `javac` qua SPI | Tùy cấu hình | Thường có | `java.util.spi.ToolProvider.findFirst("javac")` là bằng chứng độc lập về command-tool provider, không phải `JavaCompiler` |

**Thứ tự quyết định an toàn:**

1. Nếu `java.compiler` không có trong boot layer: đừng gọi mã phụ thuộc `javax.tools`.
2. Nếu API có: có thể gọi `javax.tools.ToolProvider.getSystemJavaCompiler()`.
3. Nếu compiler trả `null`: xử lý như **compiler unavailable**, không dereference.
4. Chỉ khi compiler khác `null` mới tạo file manager và compilation task.
5. Nếu hệ thống cho phép alternative compiler, tìm provider/remote service **theo chính sách được cấu hình**, không âm thầm dùng bất kỳ tool có tên gần giống nào.

**Lưu ý:** Với ứng dụng dùng **named module** và khai báo `requires java.compiler;`, JVM sẽ yêu cầu module này tại startup; nếu thiếu, boot layer có thể fail **trước khi vào `main`**. Kiểu guard ở runtime chỉ hữu ích khi cách đóng gói cho phép ứng dụng khởi động mà không cần module ấy, như entrypoint trên classpath dựa vào `java.base` và helper được tải theo điều kiện.

## 4. Kiểm tra nhanh bằng CLI

Các lệnh này là thao tác chẩn đoán môi trường, không phải điều kiện thay cho kiểm tra trong code:

```bash
java -version
java --list-modules
javac -version
```

- `java -version`: cho biết JVM đang chạy, không xác nhận compiler provider tồn tại trong **runtime image ứng dụng thật**.
- `java --list-modules`: liệt kê module của runtime image hiện được chọn bởi binary `java` này. Kiểm tra có `java.compiler@...` và `jdk.compiler@...` hay không.
- `javac -version`: cho biết executable `javac` có thể tìm được theo `PATH` của shell hay không. Nó **có thể thuộc JDK khác** với process Java thực chạy ứng dụng.
- Với Windows PowerShell, có thể dùng `Get-Command java` và `Get-Command javac` để xem đường dẫn được chọn; với Unix shell dùng `command -v java` và `command -v javac`.

Vì `JAVA_HOME`, `PATH`, đường dẫn tuyệt đối và container image có thể không trùng, nên **đừng** coi sự thành công của `javac -version` trên shell admin là bằng chứng cho tiến trình app.

### 4.1. `--limit-modules` để mô phỏng thiếu modules

Có thể dùng cờ launcher để **giới hạn các module khả kiến** trong test:

```bash
java --limit-modules java.base,java.compiler CompilerDiscoveryDemo
java --limit-modules java.base CompilerDiscoveryDemo
```

Các lệnh trên giả định class `CompilerDiscoveryDemo` đã được compile và nằm trên classpath hiện tại. `--limit-modules` không xóa module khỏi JDK; nó giới hạn các module được quan sát/resolve trong **lần chạy đó**, thuận tiện để test fallback. Ở tình huống thứ nhất, API vẫn có nhưng provider implementation `jdk.compiler` bị ẩn. Ở tình huống thứ hai, chỉ `java.base` khả dụng.

Trong một app modular có module descriptor yêu cầu module không thuộc giới hạn, chương trình có thể fail ở bước module resolution; ví dụ demo classpath tránh phụ thuộc đó trong entrypoint.

## 5. Mẫu kiểm tra tối thiểu: đừng bỏ qua null

Với runtime đã có module `java.compiler`, cách viết ngắn gọn là:

```java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public final class CompilerCheck {
    public static void main(String[] args) {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();

        if (compiler == null) {
            System.err.println(
                    "System Java compiler unavailable: "
                    + "run with jdk.compiler or disable runtime compilation.");
            return;
        }

        System.out.println("System Java compiler is available.");
    }
}
```

File độc lập **`CompilerCheck.java`** này biên dịch khi API compiler có ở compile time, nhưng **không phải mẫu an toàn cho runtime thiếu cả `java.compiler`**, vì class trực tiếp tham chiếu các kiểu từ module ấy. Nếu app thực sự phải chạy trong runtime image tối giản chỉ có `java.base`, dùng mẫu phân tách entrypoint/helper ở phần 6.

Đừng viết:

```java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
compiler.getStandardFileManager(null, null, null);
```

Đây là **phản ví dụ** đặt trong method đã import các class; khi compiler `null`, dòng thứ hai sẽ ném `NullPointerException`. Lỗi này dễ khiến người dùng tưởng code của họ có vấn đề ở file manager, trong khi nguyên nhân thực là **runtime thiếu compiler**.

### 5.1. Null là một kết quả hợp lệ theo hợp đồng

`ToolProvider.getSystemJavaCompiler()` **được phép trả null**. Vì thế null-check là thành phần thiết yếu, không phải một workaround cho bug JDK. Hãy trả lỗi có ý nghĩa như:
- `COMPILER_UNAVAILABLE`;
- hướng dẫn kiểm tra module `jdk.compiler`;
- cách dùng runtime đầy đủ hoặc chuyển sang build-time;
- cấu hình nào đang yêu cầu tính năng compilation.

Không tự động chạy `System.exit(1)` trong library. Library nên trả exception/result có ngữ cảnh; ứng dụng entrypoint hoặc service policy quyết định có dừng tiến trình hay không.

## 6. Chương trình Java 17+ chạy độc lập, an toàn qua ba môi trường

File **`CompilerDiscoveryDemo.java`** sau:

- Entrypoint dùng module API `java.base` để kiểm tra boot layer trước.
- Chỉ gọi nested helper `CompilerApi` khi module `java.compiler` được resolve.
- Nested helper có các tham chiếu `javax.tools` và kiểm tra `getSystemJavaCompiler() == null` trước khi compile.
- Nếu compiler có sẵn, biên dịch một lớp `GeneratedGreeting` từ **mã nguồn trong bộ nhớ**, đưa class output vào **thư mục tạm**, thu diagnostics, đóng standard file manager và xóa file tạm.
- Không dùng `javac` từ PATH và không nạp/chạy class mới tạo; nó chỉ xác minh khả năng biên dịch.

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import java.util.Optional;

public class CompilerDiscoveryDemo {
    public static void main(String[] args) throws Exception {
        boolean apiPresent = ModuleLayer.boot().findModule("java.compiler").isPresent();
        boolean implPresent = ModuleLayer.boot().findModule("jdk.compiler").isPresent();
        boolean toolPresent = java.util.spi.ToolProvider.findFirst("javac").isPresent();

        System.out.println("java.compiler=" + apiPresent);
        System.out.println("jdk.compiler=" + implPresent);
        System.out.println("javac.tool=" + toolPresent);

        if (!apiPresent) {
            System.out.println("status=API_ABSENT");
            return;
        }
        CompilerApi.run();
    }

    static final class CompilerApi {
        static void run() throws Exception {
            javax.tools.JavaCompiler compiler =
                    javax.tools.ToolProvider.getSystemJavaCompiler();
            if (compiler == null) {
                System.out.println("status=COMPILER_UNAVAILABLE");
                return;
            }
            System.out.println("status=COMPILER_AVAILABLE");

            String code = "public class GeneratedGreeting {"
                    + " public static String message() { return \"hello\"; } }";
            javax.tools.JavaFileObject source = new javax.tools.SimpleJavaFileObject(
                    java.net.URI.create("string:///GeneratedGreeting.java"),
                    javax.tools.JavaFileObject.Kind.SOURCE) {
                @Override
                public CharSequence getCharContent(boolean ignoreEncodingErrors) {
                    return code;
                }
            };

            javax.tools.DiagnosticCollector<javax.tools.JavaFileObject> errors =
                    new javax.tools.DiagnosticCollector<>();
            Path directory = Files.createTempDirectory("compile-discovery-");
            try {
                try (javax.tools.StandardJavaFileManager manager =
                        compiler.getStandardFileManager(
                                errors, Locale.ROOT, StandardCharsets.UTF_8)) {
                    List<String> options = List.of(
                            "--release", "17", "-proc:none",
                            "-d", directory.toString());
                    Boolean result = compiler.getTask(
                            null, manager, errors, options, null,
                            List.of(source)).call();
                    System.out.println("compile.ok=" + Boolean.TRUE.equals(result));
                    System.out.println("diagnostics=" + errors.getDiagnostics().size());
                    System.out.println("class.exists="
                            + Files.exists(directory.resolve("GeneratedGreeting.class")));
                }
            } finally {
                Files.deleteIfExists(directory.resolve("GeneratedGreeting.class"));
                Files.deleteIfExists(directory);
            }
        }
    }
}
```

**Biên dịch trên môi trường phát triển có JDK 17+**:

```bash
javac --release 17 CompilerDiscoveryDemo.java
```

Nếu đang đứng trong thư mục chứa class vừa biên dịch, chạy:

```bash
java CompilerDiscoveryDemo
java --limit-modules java.base,java.compiler CompilerDiscoveryDemo
java --limit-modules java.base CompilerDiscoveryDemo
```

### 6.1. Output khi compiler sẵn có

```text
java.compiler=true
jdk.compiler=true
javac.tool=true
status=COMPILER_AVAILABLE
compile.ok=true
diagnostics=0
class.exists=true
```

Đây là **stdout đã được kiểm chứng** trên OpenJDK 24 với mã được biên dịch bằng `javac --release 17`. Khi chạy trên JDK 17+ đầy đủ tương thích, output tương tự nếu module provider và filesystem phù hợp.

### 6.2. Output khi có API nhưng thiếu jdk.compiler

Lệnh:

```bash
java --limit-modules java.base,java.compiler CompilerDiscoveryDemo
```

**Stdout đã kiểm chứng:**

```text
java.compiler=true
jdk.compiler=false
javac.tool=false
status=COMPILER_UNAVAILABLE
```

Giải thích:
- Các kiểu `javax.tools` vẫn hiện diện, nên nested helper `CompilerApi` được phép chạy.
- Nhưng `getSystemJavaCompiler()` trả `null` vì provider implementation của JDK không khả dụng trong module graph bị giới hạn.
- Chương trình ghi trạng thái rõ ràng và **không** tạo file manager/compilation task.
- Không có `NullPointerException` và không phát sinh file class.

**Điều cần học:** Có **API** không đồng nghĩa có **implementation**. Module `java.compiler` chứa hợp đồng công khai, còn `jdk.compiler` chứa implementation system `javac`.

### 6.3. Output khi thiếu cả java.compiler

Lệnh:

```bash
java --limit-modules java.base CompilerDiscoveryDemo
```

**Stdout đã kiểm chứng:**

```text
java.compiler=false
jdk.compiler=false
javac.tool=false
status=API_ABSENT
```

Entrypoint chỉ dùng `java.base`; nó kiểm tra module trước khi **tham chiếu helper** chứa `javax.tools`. Vì thế trong ví dụ này, class helper **không bị load** khi `java.compiler` vắng mặt.

Nếu chuyển import `javax.tools.` cùng các loại `JavaCompiler`/`JavaFileObject` vào chữ ký public, superclass hoặc logic khởi tạo của main class, ứng dụng có thể thất bại ở bước class loading/verification/linkage trước khi kịp kiểm tra. Giữ ranh giới giữa core runtime và phần chức năng optional rõ ràng.

### 6.4. Vì sao mẫu không viết output vào source tree?

`JavaCompiler.getTask(...)` trong ví dụ nhận:
- `JavaFileObject` chứa mã nguồn từ `getCharContent(...)`;
- `-d` trỏ tới thư mục tạm;
- `DiagnosticCollector` để thu lỗi;
- `StandardJavaFileManager` được đóng bằng try-with-resources.

Điều này hạn chế file sinh ra trong project khi chỉ muốn probe. `Files.deleteIfExists(...)` dùng vì biết chính xác output mong đợi chỉ là một class đơn giản; **đừng** sao chép đoạn cleanup này cho compiler job có thể sinh nhiều class/package hoặc annotation-processor files mà không thiết kế cơ chế dọn dẹp tài nguyên an toàn.

### 6.5. Vì sao dùng `-proc:none`?

`-proc:none` tắt annotation processing trong ví dụ kiểm tra. Compilation và annotation processing là **hai việc khác nhau**. Nếu để một processor không mong muốn trên classpath/module path, compile có thể chạy logic của processor ngay trong process. Đây là một lý do phải kiểm soát options, dependencies và đầu vào khi nhận mã nguồn không tin cậy.

`-proc:none` **không** làm toàn bộ compile trở thành sandbox an toàn. Parser/type checker vẫn xử lý input không tin cậy và dùng tài nguyên JVM; compile có thể tốn thời gian/bộ nhớ hoặc tạo file ngoài vùng kiểm soát nếu cấu hình file manager lỏng lẻo.

## 7. Phân tích đúng JavaCompiler.getTask(...)

Signature chính của API (viết rút gọn để đọc):

```java
JavaCompiler.CompilationTask getTask(
    Writer out,
    JavaFileManager fileManager,
    DiagnosticListener<? super JavaFileObject> diagnosticListener,
    Iterable<String> options,
    Iterable<String> classes,
    Iterable<? extends JavaFileObject> compilationUnits
);
```

Đây là **chữ ký tham khảo**, không phải code cần khai báo lại. Ý nghĩa:

| Tham số | Vai trò |
| --- | --- |
| `out` | Writer cho thông tin output của compiler nếu cần; `null` chọn output mặc định tùy API |
| `fileManager` | Đường vào source, classpath, output; dùng `StandardJavaFileManager` hoặc custom file manager |
| `diagnosticListener` | Nhận lỗi, cảnh báo, vị trí source và message |
| `options` | Tùy chọn javac như `--release`, `-classpath`, `-d`, `-proc:none` |
| `classes` | Các tên class phục vụ processing khi phù hợp; ví dụ source-only đặt `null` |
| `compilationUnits` | Các đơn vị mã nguồn, ví dụ `SimpleJavaFileObject` chứa source in-memory |

`CompilationTask.call()` trả `Boolean` biểu thị compilation có thành công hay không. Kiểm tra an toàn bằng `Boolean.TRUE.equals(result)`. Nếu `false`, **đọc diagnostics** để giải thích tại sao. Đừng dùng số lượng diagnostic bằng 0 làm điều kiện duy nhất để khẳng định success: compiler có thể có warning nhưng vẫn compile thành công; có trường hợp lỗi xảy ra ở tầng khác trước khi diagnostics được tạo.

### 7.1. Lấy diagnostics đầy đủ

Một mẫu xử lý lỗi compile:

```java
Boolean ok = compiler.getTask(
        null, manager, diagnostics, options, null, units).call();

if (!Boolean.TRUE.equals(ok)) {
    for (javax.tools.Diagnostic<? extends javax.tools.JavaFileObject> d
            : diagnostics.getDiagnostics()) {
        System.err.printf(
                "%s:%d:%d: %s: %s%n",
                d.getSource() == null ? "(unknown)" : d.getSource().getName(),
                d.getLineNumber(),
                d.getColumnNumber(),
                d.getKind(),
                d.getMessage(java.util.Locale.ROOT));
    }
    throw new IllegalStateException("Compilation failed");
}
```

Đây là **đoạn minh họa trong method** có `compiler`, `manager`, `diagnostics`, `options`, `units`. Vì `Diagnostic` có thể chỉ ra source null hoặc vị trí không biết, không nên giả định mọi diagnostic đều có line/column hợp lệ.

**Không nuốt compile failure** rồi cố load một class file cũ từ cùng output directory. Tình huống đó có thể thực thi phiên bản trước dù job hiện tại đã thất bại.

### 7.2. `run(...)` khác `getTask(...)`

`JavaCompiler.run(in, out, err, String... arguments)` là API tool-style tiện lợi, trả **mã trạng thái số** (thường 0 nếu thành công). Nó hữu ích nếu cần hành vi gần CLI. Nhưng:
- khó tích hợp diagnostics và file manager như `getTask`;
- vẫn cần compiler object khác `null`;
- không tạo tiến trình `javac` độc lập theo mặc định.

Đừng gọi nhầm `java.util.spi.ToolProvider.run(...)` với `JavaCompiler.getTask(...)`: đây là hai interface công cụ khác nhau.

### 7.3. Version compatibility và options

Nếu ứng dụng chạy trên JDK 17, `--release 17` hợp lệ. Nếu chạy trên JDK mới hơn có hỗ trợ target release 17, `--release 17` cũng hợp lệ. Nhưng trên JDK **cũ hơn 17**, tùy chọn đó có thể không được hỗ trợ. Nếu hệ thống phải hỗ trợ nhiều đời compiler, nên kiểm tra phiên bản compiler thực sự, các lựa chọn `--release` được chấp nhận và hệ thống module dependencies.

`--release` giúp compile theo public API/platform của release đích, nhưng **không** tự đóng gói mọi thư viện ngoài JDK, không xử lý classloader, và không bảo đảm chương trình sinh ra tương thích với mọi application dependency version.

## 8. Xử lý khi thiếu compiler: chọn chính sách thay vì chữa tạm

### 8.1. Cách 1 — Fail fast có hướng dẫn (ưu tiên khi tính năng bắt buộc)

Khi runtime compilation là thành phần chính của service, hãy phát hiện sự thiếu vắng compiler **ngay khi khởi tạo tính năng** và trả lỗi có hướng dẫn:

```text
COMPILER_UNAVAILABLE
Runtime Java compiler is not available.
Check the selected Java runtime image and resolved module jdk.compiler.
Deploy a Java 17+ image with jdk.compiler, or disable runtime compilation.
```

Đây là **mẫu thông báo**, không phải output của chương trình ở phần 6. Ưu điểm: không có trạng thái lỗi nửa chừng, không chạy compiler rỗng, không che nguyên nhân dưới `NullPointerException`.

Nếu tính năng compile là optional, vô hiệu hóa nó nhưng cho phần còn lại của service tiếp tục chạy. Cần định nghĩa rõ capability flag/health check để caller biết endpoint compile chưa sẵn sàng.

### 8.2. Cách 2 — Đóng gói jdk.compiler vào runtime image

Với `jlink`, phải chọn module implementation khi dựng image. Ví dụ trên JDK 17+ có `jlink`:

```bash
jlink --add-modules java.base,jdk.compiler,jdk.zipfs --output compiler-image
```

Lệnh mang tính hướng dẫn: đường dẫn/output và các application modules cần được điều chỉnh theo deployment. `jdk.compiler` có dependency tới `java.compiler` nên việc chọn `jdk.compiler` sẽ kéo module API vào qua module graph. `jdk.zipfs` hữu ích khi compiler cần truy cập JAR filesystem; trong một image có nhu cầu thật, hãy kiểm tra tất cả provider/dependency cần thiết chứ đừng cho rằng chỉ ba modules trên là đủ cho mọi compilation workload.

Khi chạy app, có thể cần đảm bảo `jdk.compiler` **được resolve**. Nếu app chạy trên classpath hay module path với cấu hình đặc biệt, có thể chạy với `--add-modules jdk.compiler` phù hợp với module graph hiện có. **Không thể làm xuất hiện module chưa được đóng gói** chỉ bằng thêm flag khi file module không có trong image.

Sau khi tạo image, bắt buộc kiểm thử bằng chính binary của image:
- xem modules của image;
- chạy code discovery;
- thực hiện một compilation task thật với classpath và `--release` như production;
- kiểm tra nhu cầu đọc JAR/module path, file permissions, temp dir và bộ nhớ.

### 8.3. Cách 3 — Chuyển biên dịch sang build-time

Nếu mã nguồn sinh ra có thể biết trước khi deploy:
- generate source khi build;
- chạy compiler trong CI/build environment;
- đóng gói bytecode đã biên dịch;
- runtime chỉ việc nạp đúng artifact đã kiểm chứng.

Lợi ích:
- runtime image nhỏ hơn, không cần `jdk.compiler`;
- dễ tách nhiệm vụ build khỏi xử lý request;
- giảm CPU/memory spikes và bề mặt tấn công của runtime compilation.

Không chọn compile-at-runtime chỉ vì thấy JavaCompiler API thú vị; cân nhắc tính cần thiết của việc thay mã thực sự trong khi ứng dụng chạy.

### 8.4. Cách 4 — Compiler worker/service bên ngoài

Nếu phải biên dịch mã theo yêu cầu nhưng không muốn để compiler trong process chính, sử dụng một **build/compile worker** riêng có JDK:
- API contract rõ ràng cho input/version/dependencies;
- giới hạn CPU, RAM, đĩa, thời gian, network;
- sandbox/isolation và policy cho mã người dùng;
- artifact validation/signing/checksum;
- transport, retry, timeout và audit.

Việc compile ở worker **không tự làm mã được sinh ra an toàn để thực thi**. Nếu load và chạy class người dùng, cần thêm isolation và security policy tương ứng.

### 8.5. Cách 5 — Một compiler implementation khác

Khi `java.compiler` có mặt, có thể khám phá `javax.tools.JavaCompiler` providers được đăng ký thông qua `ServiceLoader` (nếu ứng dụng thật sự hỗ trợ một compiler thay thế).

```java
java.util.Optional<javax.tools.JavaCompiler> alternative =
        java.util.ServiceLoader
                .load(javax.tools.JavaCompiler.class)
                .findFirst();
```

Đây là đoạn minh họa trong method có module `java.compiler`. Không nhầm `ServiceLoader.load(JavaCompiler.class)` với `java.util.spi.ToolProvider.findFirst("javac")`. Một provider bên thứ ba có cách cấu hình, giới hạn ngôn ngữ, options, module support và binary dependencies riêng. Không dựa vào sự có mặt của provider nếu chưa kiểm thử compiler thật.

**Nếu `java.compiler` không có:** không thể chỉ dùng JavaCompiler SPI bình thường mà không cung cấp module API. Một external compiler process/service là hướng riêng, cần được thiết kế/cho phép rõ ràng.

## 9. Named modules: requires, requires static và runtime image

Khi viết module riêng:

```java
module com.example.dynamiccompiler {
    requires java.compiler;
}
```

Đây là **file module-info.java minh họa**. `requires java.compiler;` là dependency **bắt buộc lúc runtime**. Nếu runtime image thiếu module đó, module resolution không hoàn tất; code `main` không có cơ hội chạy null-check.

Nếu compilation chỉ là **tính năng tùy chọn**:
- có thể tách implementation compiler sang **module riêng** chỉ được resolve khi tính năng khả dụng;
- hoặc dùng optional dependency thích hợp, có thể cân nhắc `requires static java.compiler;` khi dependency cần tại compile time nhưng optional lúc runtime;
- dù cấu hình module-info linh hoạt thế nào, phải **không load các class có phụ thuộc compiler API** khi module vắng mặt.

`requires static` không có nghĩa JVM tự download hoặc tạo `jdk.compiler`. Nó cũng không bảo đảm module `java.compiler` được resolve sẵn chỉ vì code đã từng compile thành công. Hãy kiểm thử chính xác module graph trong image deploy.

### 9.1. Vì sao jdeps không thể đoán mọi provider được dùng động?

`jdeps` phân tích các module phụ thuộc mà bytecode tham chiếu được. Nếu code chỉ import `javax.tools.JavaCompiler`/`ToolProvider`, công cụ có thể chỉ ra dependency tới `java.compiler`; nó **không nhất thiết suy ra** nhu cầu provider implementation `jdk.compiler` từ hành vi gọi `getSystemJavaCompiler()` tại runtime.

Do đó trong `jlink` pipeline, phải có bước **kiểm tra nhu cầu service providers** hoặc khai báo thêm `jdk.compiler` theo chính sách build, thay vì chỉ dựa trên static dependency scan.

### 9.2. --limit-modules khác xóa module khỏi image

`--limit-modules` giúp mô phỏng module bị ẩn trong lần chạy, nhưng không chứng minh filesystem của runtime image đã loại bỏ module. Với `jlink`, module có thể thực sự **không tồn tại** trong image. Cả hai trường hợp đều có thể khiến `getSystemJavaCompiler() == null`, nhưng cách sửa khác nhau:
- Module có trong image nhưng chưa resolve → xem cấu hình launcher/module graph và `--add-modules`.
- Module không có trong image → phải **xây lại image** hoặc dùng runtime khác.
- Có API nhưng provider hỏng hoặc cấu hình khác thường → chẩn đoán service/module loader, không chỉ copy lệnh thêm flag.

## 10. Bảng chẩn đoán lỗi thường gặp

| Hiện tượng | Giải thích khả dĩ | Hướng kiểm tra/sửa |
| --- | --- | --- |
| `getSystemJavaCompiler() == null` | System compiler implementation không khả dụng | Kiểm tra `jdk.compiler`, runtime image, launcher flags; fail fast hoặc dùng compiler khác đã được cấu hình |
| `NoClassDefFoundError: javax/tools/JavaCompiler` | `java.compiler` không hiện diện/không được resolve, nhưng class đang được load phụ thuộc API | Tách feature optional; kiểm tra module graph; đóng gói API module khi cần |
| Startup module resolution failure | Named module có `requires java.compiler` nhưng image thiếu module | Xây image đúng dependency hoặc đổi thiết kế optional module |
| `ToolProvider.findFirst("javac")` empty | CLI-tool provider không có trong service discovery hiện tại | Kiểm tra `jdk.compiler`/provider và module resolution; không suy JavaCompiler có sẵn |
| `javac` trên PATH nhưng compiler null | Shell `javac` thuộc runtime/JDK khác, hoặc module current process không chứa provider | So sánh JVM/process paths, `java.home`, module graph |
| Compiler non-null nhưng `getTask().call()` trả false | Lỗi mã nguồn, classpath/module path, target release hoặc options | Đọc `DiagnosticCollector`; báo đúng source/line |
| `IllegalArgumentException` khi tạo task | Options/compilation units không hợp lệ hoặc API contract sai | Kiểm tra arguments, compilation units, option support |
| `ServiceConfigurationError` khi tìm provider | Service provider metadata/class lỗi | Kiểm tra provider artifacts, loader, module descriptors |
| `ClassNotFoundException` khi load class vừa compile | Output directory chưa nằm trong classloader phù hợp hoặc compile thất bại | Kiểm tra class.exists, package paths, classloader, artifact policy |
| `UnsupportedClassVersionError` khi load class | Bytecode được compile cho release cao hơn runtime | Chọn `--release` tương thích, test trên runtime đích |
| Không đọc được JAR dependency | Classpath/module path, file permissions hoặc thiếu filesystem provider `jar:` | Kiểm tra `jdk.zipfs` và đường dẫn dependency |
| Build chạy trên máy dev nhưng fail trong container | Image/container thiếu module, JDK path khác, filesystem read-only hoặc thiếu tài nguyên | Chạy probe và compile test **ngay trong container image cuối** |

Không phải mọi lỗi đều được giải quyết bằng “cài JDK mới hơn”. Nếu `-d` trỏ vào thư mục chỉ đọc hoặc classpath sai, JDK đầy đủ vẫn không thể hoàn thành job. Luôn phân biệt **discovery failure** và **compilation failure**.

## 11. Bảo mật và vận hành khi compile lúc chạy

### 11.1. Runtime compilation không phải sandbox

`JavaCompiler.getTask(...)` biên dịch source; nó không bảo đảm source đầu vào được tin cậy hoặc code sau biên dịch an toàn để thực thi. Một ứng dụng nhận source từ người dùng còn cần:
- xác thực quyền gọi compile;
- giới hạn kích thước source, số files, thời gian và CPU/memory;
- kiểm soát classpath/module path;
- tắt hoặc allowlist annotation processors;
- dùng output directory riêng, không ghi chồng artifact của request khác;
- kiểm tra mã được sinh ra trước khi load;
- cô lập quá trình **thực thi** code tùy ý trong environment thích hợp.

Không coi `-proc:none` là một sandbox đầy đủ. Với nguồn không tin cậy, **biên dịch ở worker/process cô lập** thường là lựa chọn an toàn hơn chạy compiler trong chính process phục vụ request.

### 11.2. Đừng tự động ProcessBuilder fallback khi null

Một anti-pattern:

```java
if (javax.tools.ToolProvider.getSystemJavaCompiler() == null) {
    // Tự chạy "javac" lấy từ PATH cho mọi request.
}
```

Đây là **phản ví dụ**, nằm trong method có compiler API. Nguy cơ:
- `javac` từ PATH không khớp runtime hoặc là binary không mong muốn;
- user input có thể bị dùng sai làm CLI arguments;
- resource và output không được cách ly;
- policy security/audit không biết có fallback;
- custom image có thể không có executable đó.

Nếu thực sự dùng external compiler, cấu hình **đường dẫn tuyệt đối đã xác minh**, lập arguments bằng `ProcessBuilder(List<String>)` (không nối thành shell command), dùng timeout/resource bounds và nắm chắc trách nhiệm đọc stdout/stderr. Đây là **một kiến trúc riêng**, không phải tác dụng phụ của `getSystemJavaCompiler() == null`.

### 11.3. File manager, class loader và cache

- Đóng `StandardJavaFileManager` khi xong job; tránh giữ file handles mở.
- Có chính sách dọn tệp đầu ra cả khi biên dịch thất bại.
- Không dùng chung mutable compiler state/file manager giữa nhiều thread nếu chưa xác nhận thread safety của implementation và cách dùng.
- Đảm bảo không load bytecode cũ khi compiler trả false; mỗi job nên dùng output/scope riêng.
- Cache compiler results chỉ khi input source, toolchain version, options, classpath và dependency state cùng khớp.
- Thay compiler/runtime có thể thay diagnostics và generated bytecode; test reproducibility nếu dự án yêu cầu kết quả build xác định.

## 12. Kiểm thử chức năng discovery và fallback

Một bộ test đáng tin nên bao gồm:

| Trường hợp | Cách tạo tình huống | Kết quả mong đợi |
| --- | --- | --- |
| JDK hoàn chỉnh | Dùng JDK17+ có `jdk.compiler` khả dụng | `getSystemJavaCompiler() != null`, compile một source đơn giản thành công |
| Chỉ API | `--limit-modules java.base,java.compiler` với demo classpath | Không crash; in `COMPILER_UNAVAILABLE` |
| Chỉ runtime cơ bản | `--limit-modules java.base` với demo classpath | Không load helper compiler; in `API_ABSENT` |
| Java source không hợp lệ | Dùng một source test cố ý sai cú pháp | `getTask().call()` false và diagnostics có lỗi |
| Classpath thiếu dependency | Source tham chiếu class không có trong compile path | Báo diagnostic, không load bytecode cũ |
| Output directory không ghi được | Kiểm soát quyền ghi | Báo lỗi I/O/compilation rõ ràng, cleanup |
| Runtime image đã đóng gói | Chạy binary `java` của image cuối | Có đủ modules và dependencies thực tế |
| Sai version target | Dùng `--release` ngoài khả năng của compiler | Báo option lỗi, hướng dẫn version hỗ trợ |

**Đặc biệt:** Tests dùng `--limit-modules` để mô phỏng thiếu module cần chạy trên **class path** theo hướng dẫn của demo. Không lấy một named module đang `requires java.compiler` rồi mong nó khởi động bình thường với `--limit-modules java.base`; đó là kiểm tra một tình huống khác: module resolution failure.

### 12.1. Không kiểm tra chỉ bằng hai boolean

`apiPresent && implPresent` là tín hiệu hỗ trợ, **không phải bảo đảm compile sẽ thành công**. Một hệ thống đáng tin còn cần thử:
- `ToolProvider.getSystemJavaCompiler() != null`;
- một compilation task đúng options;
- diagnostics và output;
- filesystem/temp/classpath/module path;
- class loading/execution sau compile nếu tính năng thực sự cần.

Các yếu tố như `jdk.zipfs` và thư viện phụ thuộc có thể khiến compile nguồn thực tế thất bại dù việc tìm provider thành công.

### 12.2. Logging tối thiểu hữu ích

Khi tính năng compile được khởi tạo, có thể log:
- `Runtime.version()` và `System.getProperty("java.home")` (nếu log path phù hợp policy);
- `ModuleLayer.boot().findModule("java.compiler")` / `findModule("jdk.compiler")`;
- `ToolProvider.getSystemJavaCompiler() == null`;
- số lượng source units, target release và kết quả task;
- diagnostics đã xử lý an toàn.

Không log nguyên văn toàn bộ source người dùng nếu có dữ liệu nhạy cảm. Với multi-tenant service, phân tách log context/IDs nhưng tránh expose path nội bộ hoặc secret compilation options.

## 13. FAQ và lỗi hiểu sai

**Q1. Máy có `java`, vậy vì sao JavaCompiler null?**

Vì runtime Java không bắt buộc cung cấp compiler implementation. `java.compiler` là API; `jdk.compiler` là provider của JDK. Custom runtime image có thể loại bỏ implementation.

**Q2. Chỉ có `java.compiler` thì gọi `JavaCompiler.getTask` được không?**

Không có đối tượng `JavaCompiler` từ `getSystemJavaCompiler` nếu provider không khả dụng. Interface tồn tại không tự tạo compiler. Có thể cân nhắc provider khác được đăng ký, nhưng phải cấu hình/test riêng.

**Q3. `java.util.spi.ToolProvider.findFirst("javac")` có bằng `javax.tools.ToolProvider.getSystemJavaCompiler()` không?**

Không. Cái đầu trả Optional của một CLI tool provider interface trong `java.base`; cái sau trả compiler API object trong `java.compiler` hoặc `null`.

**Q4. Có cần thêm `jdk.compiler` vào `module-info.java` bằng `requires` không?**

Không tự động làm vậy chỉ để dùng `javax.tools`; chương trình API thường khai báo `requires java.compiler`, còn implementation JDK được cung cấp/resolve theo runtime image và service mechanism. Khi build image không có compiler, có thể cần **thêm `jdk.compiler`** vào modules root của `jlink` hoặc flags phù hợp; không nhầm module API và implementation.

**Q5. Tại sao `jdeps` không hiển thị `jdk.compiler` nhưng chạy vẫn cần nó?**

Vì code tham chiếu compiler **API**, còn implementation có thể được tìm động qua ToolProvider/service. Static dependency analysis không luôn bao quát nhu cầu provider lúc runtime.

**Q6. Thêm `--add-modules jdk.compiler` có chữa image đã lược bỏ module không?**

Không. Flag chỉ hỗ trợ resolve module **đang có sẵn** trong runtime/module path. Nếu image thật thiếu `jdk.compiler`, phải rebuild image/deploy runtime khác.

**Q7. Có thể dùng `ToolProvider.getSystemToolClassLoader()` để vượt qua null không?**

Không. Phương thức này deprecated và theo Java SE 17 luôn trả `null`. Đó không phải cơ chế tìm compiler hiện đại.

**Q8. Không dùng annotation processors có bảo đảm an toàn tuyệt đối không?**

Không. `-proc:none` chỉ tắt annotation processing. Việc compile nguồn tùy ý vẫn tiêu tốn tài nguyên và classfile sau biên dịch vẫn có thể chứa mã độc hại nếu được nạp/chạy.

**Q9. JavaCompiler không null nhưng source vẫn fail, có phải lỗi ToolProvider không?**

Không nhất thiết. Kiểm tra `getTask().call()`, `DiagnosticCollector`, classpath, module path, release, file manager và output path trước.

**Q10. Mẫu một file trong bài có thực sự không crash khi java.compiler thiếu không?**

Có, với chương trình classpath đã kiểm chứng trên OpenJDK24 và biên dịch `--release 17`: entrypoint chỉ dùng `java.base`, kiểm tra module rồi mới tham chiếu class helper có `javax.tools`. Nếu chuyển sang named module hoặc thay class loading structure, phải test lại trong runtime image đó.

## 14. Bài tập và đáp án

### Bài 1 — Phân biệt module

Một app chạy trên runtime có `java.compiler` nhưng không có `jdk.compiler`. Dự đoán `getSystemJavaCompiler()`.

**Đáp án:** Với implementation JDK 17 tiêu chuẩn, trả `null`. Module API hiện diện không bảo đảm system compiler implementation.

### Bài 2 — Import nào đúng?

Muốn gọi `getSystemJavaCompiler()` và nhận `JavaCompiler`, dùng:

```java
import javax.tools.ToolProvider;
import javax.tools.JavaCompiler;
```

**Đáp án:** Đúng. `java.util.spi.ToolProvider` là interface công cụ CLI khác; `findFirst("javac")` không trả `JavaCompiler`.

### Bài 3 — Giải thích ba output

Vì sao cùng `CompilerDiscoveryDemo.class` có thể in:
- `COMPILER_AVAILABLE` ở JDK đầy đủ;
- `COMPILER_UNAVAILABLE` khi giới hạn đến `java.base,java.compiler`;
- `API_ABSENT` khi giới hạn chỉ `java.base`?

**Đáp án:** Ba trạng thái correspond với module graph và provider discovery khác nhau. Entrypoint không tham chiếu trực tiếp `javax.tools`, nên không phải load helper khi API không có. Khi API còn nhưng provider vắng, phương thức tìm compiler trả null.

### Bài 4 — Packaging

Một service cần compile source theo yêu cầu trong runtime image do `jlink` tạo. `jdeps` chỉ gợi ý `java.compiler`. Hãy nêu ít nhất ba bước đảm bảo service có thể compile.

**Đáp án:** Thêm `jdk.compiler` vào image root modules, bổ sung provider hỗ trợ như `jdk.zipfs` nếu workload cần JAR filesystem; kiểm tra module graph/`getSystemJavaCompiler` trên **image cuối**; chạy compile test thật với options và classpath; chuẩn bị fallback nếu compile không phải tính năng bắt buộc.

### Bài 5 — Diagnose compile failure

`getSystemJavaCompiler() != null`, nhưng `getTask().call()` trả `false`. Có nên thông báo “JDK thiếu compiler” không?

**Đáp án:** Không. Compiler đã được tìm thấy. Đọc `DiagnosticCollector` và kiểm tra source/options/dependencies/file manager. Không thay lỗi compilation bằng lỗi discovery.

### Bài 6 — Thiết kế optional feature

Một ứng dụng muốn chạy bình thường trên image chỉ có `java.base`, nhưng có endpoint optional “compile Java”. Có nên đặt mọi `JavaCompiler` type ở chữ ký public của main class?

**Đáp án:** Không nếu muốn bảo đảm main class load an toàn khi API module vắng. Tách compiler-specific code sang class/module optional và chỉ load khi kiểm tra môi trường thành công; kiểm thử ngay trên runtime tối giản.

### Bài 7 — Khác biệt CLI và API

Một máy có executable `javac` ở PATH; app vẫn nhận `getSystemJavaCompiler() == null`. Nêu hai nguyên nhân.

**Đáp án:** `javac` trên PATH có thể thuộc **JDK khác** với JVM chạy app; hoặc module `jdk.compiler` không khả dụng/không resolved trong module graph của app (kể cả khi binary `javac` tồn tại trên OS). Không dùng PATH như bằng chứng duy nhất.

### Bài 8 — Chính sách fallback

Người dùng đưa một đoạn Java source không tin cậy để biên dịch. Runtime thiếu `jdk.compiler`. Có nên tự ý chạy `ProcessBuilder("javac",...)` bất kỳ executable tìm thấy không?

**Đáp án:** Không. Phải có policy rõ, đường dẫn công cụ đã xác minh, kiểm soát input và CLI arguments, giới hạn tài nguyên, output isolation, timeout và bảo mật. Nên cân nhắc compile worker được sandbox hóa. Nếu feature không được hỗ trợ, trả một capability error rõ ràng.

## Tài liệu chính thức

- [Java SE 17 — javax.tools.ToolProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html): `getSystemJavaCompiler` và điều kiện trả `null` khi thiếu `jdk.compiler`.
- [Java SE 17 — javax.tools.JavaCompiler](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html): `getTask`, `getStandardFileManager` và compilation task contract.
- [Java SE 17 — javax.tools package](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/package-summary.html): Compiler SPI và service providers.
- [Java SE 17 — java.compiler module](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/module-summary.html): Các API compiler và language model.
- [Java SE 17 — jdk.compiler module](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/module-summary.html): Implementation javac, compiler tool provider và `jdk.zipfs`.
- [Java SE 17 — java.util.spi.ToolProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/ToolProvider.html): `findFirst("javac")` và command tool SPI.
- [Java SE 17 — StandardJavaFileManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html): File manager lifecycle và compilation inputs/outputs.
- [Java SE 17 — jlink tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html): Build custom runtime images với đúng modules.

## Kết luận

`javax.tools.ToolProvider.getSystemJavaCompiler()` là cách chuẩn để tìm **system Java compiler** trong code, nhưng **`null` là kết quả hợp lệ** khi implementation không được cung cấp. `java.compiler` chứa **API**, `jdk.compiler` chứa **compiler thực tế** của JDK, còn `java.util.spi.ToolProvider` là một interface khác để tìm **CLI tool** tên `javac`. Hãy kiểm tra module graph, tránh load `javax.tools` khi API module không có, luôn null-check compiler, kiểm tra một compilation task thật và chọn chính sách fail-fast/build-time/đóng gói JDK/worker rõ ràng. Với runtime image do `jlink` tạo, cần kiểm chứng **chính image deployment cuối cùng**, không suy luận từ máy phát triển hoặc chỉ từ `java -version`.

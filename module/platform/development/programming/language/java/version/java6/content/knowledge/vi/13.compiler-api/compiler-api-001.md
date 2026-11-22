# JSR 199 và nhu cầu biên dịch Java từ chương trình

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích **JSR 199 (Java Compiler API)** giải quyết nhu cầu gì và vì sao vẫn được sử dụng trong Java hiện đại.
- Phân biệt **biên dịch** mã nguồn thành `.class` với **nạp và chạy** mã đã biên dịch; hiểu những việc Java Compiler API làm và không làm.
- Gọi `ToolProvider.getSystemJavaCompiler()`, dùng `JavaCompiler.getTask(...)`, `JavaFileObject`, `StandardJavaFileManager` và `DiagnosticCollector` để biên dịch Java ngay trong ứng dụng.
- Viết và chạy chương trình Java 17+ biên dịch nguồn lưu trong chuỗi, thu thập lỗi có cấu trúc, thiết lập `--release` và thư mục đầu ra.
- Biết khi nào cần API thay vì gọi công cụ dòng lệnh, đồng thời xử lý classpath, module, annotation processing, vòng đời tài nguyên và mã nguồn không đáng tin cậy.

**Phạm vi:** JSR 199 xuất hiện từ Java 6, nhưng `javax.tools` và `JavaCompiler` **vẫn là API chuẩn đang dùng**. Các ví dụ sử dụng Java 17+ và cách đóng gói hiện hành; không dựa vào các cơ chế công cụ Java đã lỗi thời.

## 1. Vì sao một chương trình lại cần biên dịch Java?

Thông thường, lập trình viên gõ:

```bash
javac -d out src/example/Hello.java
java -cp out example.Hello
```

`javac` biến mã nguồn `.java` thành bytecode `.class`; lệnh `java` sau đó mới nạp lớp và chạy chương trình. Nhưng có nhiều ứng dụng **phải khởi động hoặc kiểm soát chính bước biên dịch**:

| Bài toán thực tế | Vì sao cần biên dịch ngay trong chương trình? |
| --- | --- |
| IDE, trình soạn thảo và công cụ giáo dục | Kiểm tra mã, hiển thị lỗi kèm dòng/cột và cung cấp phản hồi khi người dùng chỉnh sửa. |
| Nền tảng chấm bài hoặc bài tập Java | Nhận mã nguồn, biên dịch tự động, phân biệt lỗi cú pháp/kiểu với lỗi lúc chạy. |
| Hệ thống sinh mã nguồn từ schema hoặc template | Sinh các lớp Java rồi kiểm chứng/chuyển chúng thành `.class` trong một quy trình được điều phối bằng Java. |
| Công cụ build, kiểm thử hoặc kiểm tra tương thích | Chủ động chọn bộ file, classpath, phiên bản Java và xử lý kết quả thành dữ liệu có cấu trúc. |
| Một số hệ thống extension nội bộ | Biên dịch mã do hệ thống tạo ra, sau đó **ở bước riêng** kiểm tra, đóng gói hoặc nạp artifact nếu được phép. |

Bản chất chung: **mã nguồn hoặc tham số biên dịch chỉ có khi ứng dụng đang chạy**, hoặc ứng dụng cần nhận lỗi thành dữ liệu để xử lý tiếp.

Không phải lúc nào biên dịch động cũng cần thiết. Với ứng dụng thông thường có mã nguồn cố định, hãy để Maven/Gradle hoặc công cụ build biên dịch **trước khi deploy**. Nếu chỉ cần gọi mã đã có trong dependency, không cần tạo compiler task.

Một ví dụ so sánh:

```text
Thông thường:
.java --(javac tại build time)--> .class/JAR --(java)--> chạy

JSR 199:
Java application --(JavaCompiler API)--> compiler task
                  --(JavaFileObject)--> mã nguồn
                  <--(Diagnostic)----- lỗi/cảnh báo có cấu trúc
                  <--(output)--------- .class (hoặc đích do file manager quy định)
                                            |
                                            v
                                bước nạp/chạy riêng, nếu có
```

**Biên dịch không có nghĩa là thực thi chương trình vừa được biên dịch.** Chỉ nhận về `.class` không tự gọi `main()`, không tự tạo class loader và không tự chạy mã của lớp kết quả. Riêng **annotation processor hoặc compiler plugin**, nếu được kích hoạt, có thể thực thi mã ngay trong giai đoạn biên dịch; vì vậy phải quản lý riêng (xem mục an toàn).

## 2. JSR 199 là gì và còn áp dụng đến hiện nay như thế nào?

**JSR 199** là đặc tả chuẩn hóa giao diện để chương trình Java tìm và gọi công cụ biên dịch Java, cung cấp nguồn đầu vào, nhận diagnostics và tùy biến cách compiler đọc/ghi file. API cốt lõi nằm trong package **`javax.tools`**.

Trong kiến trúc module Java hiện nay:

- **`java.compiler`**: module chuẩn định nghĩa API và các giao diện như `JavaCompiler`, `JavaFileManager`, `JavaFileObject`, `Diagnostic`, `ToolProvider`.
- **`jdk.compiler`**: module JDK cung cấp triển khai compiler hệ thống (tương ứng với `javac`). Có thể vắng mặt trong runtime image tùy cách đóng gói.
- Một ứng dụng **named module** trực tiếp dùng API cần khai báo `requires java.compiler;` trong `module-info.java`. Ứng dụng chạy trên classpath thông thường không cần tự tạo file `module-info.java`.

Điểm dễ nhầm: tên package vẫn là **`javax.tools`**, không phải một API Jakarta. API này không bị thay thế chỉ vì ứng dụng hiện đại dùng module Java 9+.

Lấy compiler hệ thống:

```java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException(
            "A JDK with the system Java compiler is required");
}
```

`getSystemJavaCompiler()` **có thể trả `null`** khi runtime không cung cấp compiler. Việc một hệ thống chạy được bytecode Java không có nghĩa runtime của hệ thống đó chứa module `jdk.compiler`. Với container hoặc `jlink` runtime image rút gọn, hãy chủ động kiểm tra compiler có sẵn trước khi bật chức năng biên dịch.

**JSR 199 so với JSR 269:** JSR 199 gọi và điều phối compiler. JSR 269 mô tả **annotation processing**; nếu compiler task bật processor thì processor có thể chạy trong quá trình biên dịch. Hai khả năng liên quan nhau nhưng phục vụ mục đích khác nhau.

## 3. Các thành phần cốt lõi của Compiler API

| Thành phần | Vai trò chính |
| --- | --- |
| `ToolProvider` | Tra cứu compiler hệ thống bằng `getSystemJavaCompiler()`. |
| `JavaCompiler` | Giao diện compiler; tạo `StandardJavaFileManager` và `CompilationTask`. |
| `JavaCompiler.CompilationTask` | Đại diện cho **một lần biên dịch**; gọi `call()` để thực hiện và lấy kết quả thành công/thất bại. |
| `JavaFileObject` | Trừu tượng nguồn `.java` hoặc tệp liên quan đến biên dịch, không bắt buộc phải là file nằm trên đĩa. |
| `SimpleJavaFileObject` | Lớp nền thuận tiện khi tự xây `JavaFileObject`, ví dụ nguồn Java lưu trong `String`. |
| `StandardJavaFileManager` | File manager mặc định của compiler; xử lý file nguồn, dependency, output theo các vị trí chuẩn. |
| `DiagnosticCollector<JavaFileObject>` | Thu thập lỗi, cảnh báo và thông tin compiler dưới dạng `Diagnostic`. |
| `Diagnostic` | Cung cấp loại thông báo (`ERROR`, `WARNING`, ...), vị trí dòng/cột, mã chẩn đoán và nội dung thông báo. |
| `JavaFileManager` / `ForwardingJavaFileManager` | Mở rộng hoặc ủy quyền cơ chế đọc/ghi, hữu ích khi cần bộ nhớ, virtual filesystem hoặc output đặc biệt. |

Đường đi thường dùng:

1. Xác nhận compiler hiện diện.
2. Chuẩn bị một hoặc nhiều `JavaFileObject` đại diện cho mã nguồn.
3. Tạo `DiagnosticCollector` nếu cần lưu kết quả báo lỗi.
4. Tạo `StandardJavaFileManager` trong khối `try-with-resources`.
5. Gọi `compiler.getTask(...)` với nguồn, lựa chọn compiler và nơi ghi kết quả.
6. Gọi `task.call()`; nếu trả `true` thì lần biên dịch đã thành công theo compiler.
7. Đọc diagnostics và xử lý sản phẩm đầu ra. Đóng file manager sau khi không còn dùng.

**`getTask(...)` tạo nhiệm vụ; `call()` mới thực hiện biên dịch.** `CompilationTask` không phải lệnh tự chạy ngầm, không được xem như một job đã khởi động trong background.

## 4. Ví dụ đầy đủ Java 17+: biên dịch một chuỗi Java và thu thập lỗi

Ví dụ sau **không cần Maven/Gradle hay thư viện ngoài JDK**. Chương trình nhận compiler hiện hành, đóng gói mã nguồn trong `StringSource`, biên dịch một lớp hợp lệ và một lớp sai cú pháp rồi cho biết thành công/thất bại. Nó không chạy bytecode vừa tạo, để giữ phạm vi tập trung vào Compiler API.

Tạo tệp **`CompilerApiDemo.java`**:

```java
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

public class CompilerApiDemo {
    private static final class StringSource extends SimpleJavaFileObject {
        private final String text;

        StringSource(String className, String text) {
            super(URI.create("string:///" +
                    className.replace('.', '/') + Kind.SOURCE.extension),
                    Kind.SOURCE);
            this.text = text;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return text;
        }
    }

    private static boolean compile(
            JavaCompiler compiler,
            StandardJavaFileManager fileManager,
            DiagnosticCollector<JavaFileObject> messages,
            Path output,
            JavaFileObject source) {
        List<String> options = List.of(
                "--release", "17", "-proc:none", "-d", output.toString());

        Boolean result = compiler.getTask(
                null, fileManager, messages, options, null, List.of(source))
                .call();
        return Boolean.TRUE.equals(result);
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "A JDK with the system Java compiler is required");
        }

        Path output = Files.createTempDirectory("jsr199-demo-");
        try (StandardJavaFileManager files = compiler.getStandardFileManager(
                null, Locale.ROOT, StandardCharsets.UTF_8)) {
            JavaFileObject good = new StringSource(
                    "demo.Greeter",
                    "package demo; public class Greeter {" +
                    " public static String message() { return \"OK\"; } }");

            var goodMessages = new DiagnosticCollector<JavaFileObject>();
            boolean goodOk = compile(compiler, files, goodMessages, output, good);
            System.out.println("Good source compiles: " + goodOk);
            System.out.println("Class file exists: " +
                    Files.exists(output.resolve("demo/Greeter.class")));

            JavaFileObject bad = new StringSource(
                    "demo.Broken",
                    "package demo; public class Broken { int x = ; }");

            var badMessages = new DiagnosticCollector<JavaFileObject>();
            boolean badOk = compile(compiler, files, badMessages, output, bad);
            System.out.println("Bad source compiles: " + badOk);

            boolean hasError = badMessages.getDiagnostics().stream()
                    .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR);
            System.out.println("Error diagnostic received: " + hasError);
        } finally {
            Files.deleteIfExists(output.resolve("demo/Greeter.class"));
            Files.deleteIfExists(output.resolve("demo"));
            Files.deleteIfExists(output);
        }
    }
}
```

### Biên dịch và chạy

Từ thư mục chứa `CompilerApiDemo.java`, với **JDK 17+ có compiler**:

```bash
javac CompilerApiDemo.java
java CompilerApiDemo
```

**Đầu ra chuẩn** (đã kiểm tra với JDK 21):

```text
Good source compiles: true
Class file exists: true
Bad source compiles: false
Error diagnostic received: true
```

Chương trình dọn thư mục đầu ra tạm sau khi hoàn tất. Output là `.class` của `demo.Greeter`, nằm tạm ở `<temp>/demo/Greeter.class` trong thời gian kiểm tra; `demo.Broken` không biên dịch thành công.

Không in nguyên văn thông báo lỗi của compiler trong `stdout` vì nội dung chẩn đoán chi tiết và ngôn ngữ có thể phụ thuộc compiler/JDK/locale. Điều kiểm chứng ổn định ở đây là mã không hợp lệ tạo ra ít nhất một `Diagnostic.Kind.ERROR`.

### Giải thích từng thành phần quan trọng

**Nguồn Java từ `String`:** `StringSource` kế thừa `SimpleJavaFileObject`. URI `string:///demo/Greeter.java` và `Kind.SOURCE` cho compiler biết đây là đơn vị biên dịch có tên tương ứng với class `demo.Greeter`. `getCharContent(...)` trả về nội dung nguồn; do đó không cần tạo `demo/Greeter.java` trên filesystem.

**File manager:** `getStandardFileManager(...)` trả một file manager hỗ trợ các đường dẫn và output thông thường. Ở đây dùng `try-with-resources` để đóng tài nguyên khi xong. Có thể tái sử dụng file manager trong **nhiều lượt biên dịch tuần tự** nếu cần giảm chi phí chuẩn bị.

**Tùy chọn biên dịch:** `--release 17` yêu cầu ngôn ngữ, API nền và target phù hợp Java 17; `-d <path>` chọn thư mục để ghi `.class`; `-proc:none` chủ động tắt annotation processing trong ví dụ. Các lựa chọn được truyền qua danh sách `List<String>`, không ghép thành một chuỗi dòng lệnh duy nhất.

**Diagnostic:** mỗi lượt biên dịch dùng một `DiagnosticCollector` riêng. `getTask(...)` nhận collector rồi `call()` thực thi task; sau đó đọc `getDiagnostics()`. Dùng collector mới tránh trộn lỗi của nhiều lượt và cho phép ứng dụng gắn lỗi đúng với tài liệu đang chỉnh sửa.

**Kết quả:** `call()` trả kiểu `Boolean`; ví dụ dùng `Boolean.TRUE.equals(result)`. Khi mã sai cú pháp, phương thức trả `false` và thông báo lỗi được thu thập, thay vì yêu cầu ứng dụng tự phân tích text in trên console.

**Nạp lớp và chạy:** ví dụ chỉ xác nhận sự tồn tại của file `.class`. Nếu sau này cần nạp lớp, đó là bước riêng với `ClassLoader` và giới hạn an toàn phù hợp; **JSR 199 không tự thực thi phương thức `message()`**.

## 5. Nếu mã nguồn có sẵn trên đĩa thì sao?

Không phải lúc nào cũng cần `SimpleJavaFileObject`. Với file `src/example/Hello.java` đã tồn tại, `StandardJavaFileManager` có thể chuyển đường dẫn thành danh sách compilation unit:

```java
// Đoạn tích hợp vào chương trình đã có compiler và fileManager,
// không phải một chương trình main độc lập.
Iterable<? extends JavaFileObject> files =
        fileManager.getJavaFileObjectsFromPaths(
                List.of(Path.of("src/example/Hello.java")));

var diagnostics = new DiagnosticCollector<JavaFileObject>();
boolean ok = Boolean.TRUE.equals(
        compiler.getTask(
                null,
                fileManager,
                diagnostics,
                List.of("--release", "17", "-proc:none", "-d", "out"),
                null,
                files)
        .call());
```

Ở đây, `out` phải là đường dẫn đầu ra phù hợp với môi trường (tạo thư mục trước khi biên dịch nếu cần). Đoạn trên minh họa một phương án dùng source file thực, không lặp lại nội dung của chương trình hoàn chỉnh.

Khi dự án có dependency:

- Cấu hình `--class-path` / `-classpath` cho các dependency classpath cần thiết; không suy đoán compiler sẽ tự hiểu mọi dependency của ứng dụng gọi nó.
- Với named modules, dùng `--module-path`, `--module-source-path` và các lựa chọn module thích hợp theo cấu trúc build thực tế.
- Với mã cần chạy ở Java 17, ưu tiên `--release 17` hơn việc chỉ đặt bytecode target; `--release` còn kiểm tra API nền tương ứng.
- Những đường dẫn source/output/dependency phải được kiểm soát; không lấy trực tiếp nội dung không đáng tin để nối vào lệnh shell.

Nếu compiler xử lý nhiều source file phụ thuộc nhau, truyền đủ compilation unit hoặc source path được cấu hình phù hợp. Đừng gọi biên dịch riêng từng file một cách tùy tiện rồi mặc định compiler tìm thấy mọi type khác.

## 6. Chẩn đoán lỗi có cấu trúc thay vì đọc stderr

Trong IDE hoặc hệ thống đánh giá mã, một chuỗi thông báo kiểu “compilation failed” thường chưa đủ. `Diagnostic` có thể cho bạn:

- `getKind()`: `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE`...;
- `getSource()`: đơn vị nguồn tương ứng (có thể `null` với một số thông báo toàn cục);
- `getLineNumber()` / `getColumnNumber()`: vị trí lỗi theo compiler; nếu không khả dụng thường là `Diagnostic.NOPOS`;
- `getCode()`: mã chẩn đoán phụ thuộc compiler, hữu ích trong một số hệ thống;
- `getMessage(Locale)`: thông báo dễ đọc theo locale khi được hỗ trợ.

Đoạn xử lý bổ sung, giả sử đã có `DiagnosticCollector<JavaFileObject> diagnostics`:

```java
for (Diagnostic<? extends JavaFileObject> d
        : diagnostics.getDiagnostics()) {
    if (d.getKind() == Diagnostic.Kind.ERROR) {
        String source = d.getSource() == null
                ? "<unknown>"
                : d.getSource().toUri().toString();

        System.out.printf(
                "Source=%s, line=%d, column=%d, kind=%s%n",
                source,
                d.getLineNumber(),
                d.getColumnNumber(),
                d.getKind());
        System.out.println(d.getMessage(Locale.ROOT));
    }
}
```

Đây là **đoạn minh họa nằm trong phương thức**, sử dụng import `javax.tools.Diagnostic` và `java.util.Locale`. Thông báo và vị trí chính xác phụ thuộc source/compiler; không hard-code dựa trên một chuỗi lỗi cụ thể. Với nhiều lượt biên dịch, phân nhóm collector theo lượt hoặc document để giao diện hiển thị lỗi đúng file.

**Chú ý:** `DiagnosticCollector` thu được các thông báo được phát qua listener; tài liệu API cho phép compiler ghi một số chẩn đoán không thể biểu diễn thành `Diagnostic` ra luồng output riêng. Một hệ thống nghiêm túc nên quản lý cả đầu ra văn bản khi cần, không mặc định collector nắm mọi thông báo.

## 7. `getTask(...)` và `run(...)` khác nhau khi nào?

`JavaCompiler` có hai cách sử dụng thường gặp:

| Cách gọi | Phù hợp khi | Kết quả và giới hạn |
| --- | --- | --- |
| `compiler.getTask(writer, manager, diagnostics, options, classes, units).call()` | Muốn giao diện có cấu trúc, `JavaFileObject` từ file/chuỗi, chẩn đoán và file manager tùy biến. | `call()` trả `Boolean`; phần lớn ứng dụng tích hợp compiler sẽ chọn cách này. |
| `compiler.run(in, out, err, args...)` | Muốn gọi compiler kiểu công cụ dòng lệnh qua API và xử lý các luồng vào/ra. | Trả **mã trạng thái `int`**, không trả `DiagnosticCollector` theo cấu trúc của `getTask`; gần với cách truyền tham số công cụ. |

Một ví dụ gọi kiểu công cụ, **chỉ minh họa khi file và thư mục đã tồn tại**:

```java
int status = compiler.run(
        null,
        System.out,
        System.err,
        "-proc:none",
        "--release", "17",
        "-d", "out",
        "src/example/Hello.java");

if (status != 0) {
    throw new IllegalStateException("javac failed: status=" + status);
}
```

Không nhầm `run(...)` này với lệnh `java` để thực thi chương trình đã biên dịch. `JavaCompiler.run(...)` vẫn là **biên dịch**.

Chọn `getTask(...)` khi hệ thống cần kiểm soát source object, file manager, diagnostics, locale và kết quả theo từng lần biên dịch.

## 8. Biên dịch hoàn toàn trong bộ nhớ: cần hiểu đúng phạm vi

Có hai lớp yêu cầu khác nhau:

1. **Nguồn Java ở bộ nhớ:** như `StringSource` trong ví dụ; không cần tệp `.java` thực. Đây là tính năng phổ biến và đủ cho nhiều trình kiểm tra mã.
2. **Đầu ra `.class` cũng ở bộ nhớ:** không tự có chỉ nhờ dùng `StringSource`. Cần xây `JavaFileManager`/`JavaFileObject` phù hợp để đón các byte của class, thường bằng cách bọc `StandardJavaFileManager` với `ForwardingJavaFileManager` và override nơi compiler tạo output.

Nếu định nạp bytecode ở bộ nhớ, lớp phụ trách `ClassLoader` phải nhận và định nghĩa class theo cách quản lý vòng đời rõ ràng. Compiler API chỉ chịu trách nhiệm biến source thành artifact; phần nạp/thực thi là một vấn đề độc lập.

Một bài toán dùng class từ nhiều lượt biên dịch có thể bị lỗi vì:

- phiên bản lớp đã nạp trong class loader cũ khác với bytecode mới;
- classpath không chứa dependency hoặc không khớp binary name;
- output của lượt trước còn tồn tại và gây nhầm lẫn;
- module/class loader không nhìn thấy đúng API/runtime dependency.

Tùy yêu cầu, ghi `.class` ra thư mục tạm cô lập rồi xử lý artifact bằng một tiến trình khác thường dễ kiểm soát hơn việc đưa toàn bộ loader và bytecode vào bộ nhớ ứng dụng.

## 9. Phiên bản Java, annotation processing và an toàn

### 9.1. Chọn phiên bản và classpath

- **Runtime cần compiler:** đảm bảo có module `jdk.compiler`. Trong môi trường JDK đầy đủ, `ToolProvider.getSystemJavaCompiler()` thường trả compiler hệ thống; trong một số runtime image rút gọn nó trả `null`.
- **`--release`:** cố định phiên bản Java mục tiêu cùng API nền tương ứng. Ví dụ chạy compiler từ JDK 21/24/26 nhưng biên dịch cho Java 17 thì dùng `--release 17`; compiler phải hỗ trợ phiên bản target đã chọn.
- **Classpath/module path:** chỉ định rõ những dependency mà source được phép dùng. Classpath của compiler không tự động tương đương classpath chạy ứng dụng trong mọi môi trường.
- **Character encoding:** nếu file nguồn nằm trên đĩa, chỉ định charset rõ ràng (ví dụ UTF-8 qua `getStandardFileManager(..., StandardCharsets.UTF_8)`) khi thích hợp; URI và nội dung `StringSource` đã là chuỗi ký tự trong JVM.

### 9.2. Annotation processing có thể chạy mã trong lúc biên dịch

`javax.annotation.processing` là khả năng hiện hành và hữu ích cho nhiều công cụ sinh mã. Tuy nhiên, compiler task có thể **chạy processor** nếu được bật/cấu hình. Vì vậy:

- Ví dụ tự biên dịch nguồn ở trên chọn **`-proc:none`** để tắt annotation processing một cách rõ ràng.
- Nếu ứng dụng thực sự cần processor, hãy chủ động cấu hình processor/path đáng tin, kiểm soát phiên bản, lỗi, quyền truy cập và lifecycle của chúng.
- **Từ JDK 23**, `javac` yêu cầu cấu hình rõ để kích hoạt annotation processing thay vì tự động tìm processor chỉ dựa vào classpath như một số JDK cũ. Đừng viết logic phụ thuộc default không ổn định giữa các bản JDK; luôn đặt lựa chọn chủ động (`-proc:none` khi không cần; cấu hình xử lý phù hợp khi cần).

Đây là khác biệt vận hành đang có tác dụng trong Java hiện đại, không phải lời khuyên dùng lại behavior lịch sử.

### 9.3. Biên dịch mã không đáng tin cậy không phải sandbox

Một hệ thống chấm bài hoặc nhận code của bên thứ ba phải phân tách hai rủi ro:

- **Compiler task:** có thể tiêu tốn CPU/bộ nhớ/đĩa; annotation processors, plugins hoặc thành phần được cấu hình có thể chạy mã trong quá trình compile. Tắt processing không có nghĩa bản thân compiler trở thành sandbox.
- **Chạy artifact:** mã `.class` vừa tạo là mã tùy ý; **không nạp và chạy trực tiếp trong JVM dịch vụ** chỉ vì compile thành công.

Với input không đáng tin cậy, nên dùng tiến trình/container cách ly phù hợp, giới hạn thời gian, CPU, bộ nhớ, I/O, quyền filesystem/network, số file và kích thước đầu vào; không biến compiler trong web server thành cơ chế thực thi tự do. Kiểm soát các tùy chọn compiler và đường dẫn, tránh để người dùng tùy ý thêm processor/plugin vào execution environment.

**Không đồng nhất `-proc:none` với một biện pháp an toàn tuyệt đối**: nó chỉ xử lý phạm vi annotation processing.

## 10. Thiết kế API tích hợp compiler trong sản phẩm

Một dịch vụ biên dịch gọn, dễ kiểm thử thường nhận:

```text
CompileRequest {
  sourceName     // ví dụ: demo.Greeter
  sourceText     // Java source hoặc danh sách source
  targetRelease  // ví dụ: 17, kiểm tra với JDK compiler hiện hành
  dependencies   // classpath/module path được cho phép
}

CompileResult {
  success        // kết quả compiler
  diagnostics    // kind, source, line, column, message
  artifacts      // đường dẫn/bytecode do file manager sinh ra
}
```

Các tên ở trên chỉ biểu diễn một **hợp đồng dữ liệu minh họa**, không phải class hay phương thức chuẩn của JSR 199.

Một vòng xử lý hợp lý:

1. **Validate request:** giới hạn size, tên lớp/tệp, encoding, phiên bản release, đường dẫn và dependencies.
2. **Resolve compiler:** kiểm tra compiler khả dụng, khả năng hỗ trợ target.
3. **Prepare units and file manager:** tạo `JavaFileObject`, chọn output cô lập và resources sẽ được đóng.
4. **Invoke task:** truyền options chính xác, tắt processor nếu không cần, gọi `getTask(...).call()`.
5. **Normalize diagnostics:** chuyển `Diagnostic` thành thông tin đủ dùng cho UI, tránh phụ thuộc nguyên văn text riêng từng JDK.
6. **Publish result:** chỉ công bố artifacts của lượt thành công; quản lý output tạm và không để file cũ gây sai kết luận.
7. **Separate execution:** nếu cần thử chạy mã đã biên dịch, làm việc đó ở bước riêng với chính sách cách ly.

Nếu có nhiều compilation task, không dùng chung một file manager đóng rồi hoặc một output directory cho các request đồng thời mà không phối hợp. Tài liệu `JavaCompiler` cho phép tái sử dụng standard file manager để giảm chi phí trên **các lần biên dịch tuần tự**; điều đó không phải bằng chứng mọi triển khai/file manager an toàn khi dùng chung đồng thời.

## 11. Lỗi phổ biến và cách khắc phục

| Dấu hiệu | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `getSystemJavaCompiler() == null` | Runtime không có triển khai compiler hệ thống. | Dùng JDK/runtime image có `jdk.compiler` hoặc cấu hình compiler provider phù hợp. |
| Task `call()` trả `false` | Lỗi biên dịch; diagnostics có thể chứa chi tiết. | Hiển thị `Diagnostic.Kind.ERROR`, dòng/cột, source cho người dùng. |
| Mã nguồn chuỗi bị báo sai tên lớp | URI, package và public class name không tương ứng. | Đặt URI `string:///demo/Greeter.java` cho `package demo; public class Greeter`. |
| Compile không tìm được symbol của dependency | Thiếu classpath/module path hoặc source cần thiết. | Kiểm tra `--class-path`, `--module-path`, units và target release. |
| Compile thành công nhưng không thấy `.class` nơi dự kiến | Output do file manager/options quyết định. | Xác nhận `-d` và đường dẫn thực; kiểm tra diagnostics và artifact. |
| Chương trình cần Java 17 nhưng dùng API mới hơn | Chỉ chọn bytecode target chưa đủ cho API nền. | Dùng `--release 17` và kiểm tra compiler hỗ trợ release. |
| Annotation processor chạy ngoài ý muốn | Cấu hình compiler/path cho phép processing. | Chủ động `-proc:none` nếu không cần; nếu cần thì chỉ chọn processor đáng tin. |
| Diagnostic messages thay đổi giữa máy | Locale hoặc compiler/JDK khác. | Xử lý bằng `kind`, `source`, `line`, `column`; không parse message như giao thức ổn định. |
| Biên dịch nguồn thành công nhưng ứng dụng không chạy | Compile và run là hai giai đoạn khác nhau. | Kiểm tra class loader, phụ thuộc runtime, cách chạy và output riêng. |

## 12. Câu hỏi tự kiểm tra

**1. Vì sao ứng dụng IDE dùng `JavaCompiler.getTask(...)` thay vì chỉ gọi một câu lệnh shell?**

Vì API cho phép truyền nguồn qua `JavaFileObject`, lấy diagnostics có cấu trúc và kiểm soát file manager/lựa chọn compiler ngay trong Java. Một tiến trình `javac` bên ngoài vẫn có chỗ dùng, đặc biệt khi cần cách ly, nhưng việc đọc log không cung cấp cùng mô hình đối tượng như `DiagnosticCollector`.

**2. `JavaCompiler.getTask(...)` đã biên dịch mã ngay chưa?**

Chưa. Đây là bước tạo `CompilationTask`. Lời gọi `call()` thực hiện task.

**3. Có thể dùng nguồn là chuỗi mà không tạo tệp `.java` trên đĩa không?**

Có. Tạo `JavaFileObject` phù hợp, thường bằng `SimpleJavaFileObject` và override `getCharContent(...)`. Muốn `.class` cũng ở bộ nhớ cần bổ sung file manager output tùy biến.

**4. `call()` trả `true` có đồng nghĩa ứng dụng chứa `main` mới sẽ tự chạy không?**

Không. Thành công chỉ cho biết compiler task biên dịch thành công; nạp/chạy bytecode là công việc độc lập.

**5. Vì sao ví dụ dùng `-proc:none`?**

Để nêu rõ bài đang kiểm tra biên dịch mã nguồn, không cần chạy annotation processors. Đây là cấu hình đúng mục đích và nhất quán giữa nhiều JDK; nó không thay thế các biện pháp cách ly đối với input không đáng tin cậy.

**6. Cần mang `javax.tools` sang tên package khác khi chuyển sang JDK hiện đại không?**

Không. `javax.tools` vẫn là package chuẩn của module `java.compiler`; `jdk.compiler` cung cấp triển khai compiler hệ thống trên JDK tương ứng.

## Tài liệu chính thức và đang được duy trì

- [JCP — JSR 199 Java Compiler API](https://jcp.org/aboutJava/communityprocess/final/jsr199/index.html): đặc tả gốc về gọi compiler từ chương trình.
- [Java SE 26 — `javax.tools.JavaCompiler`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/JavaCompiler.html): `getTask`, diagnostics, standard file manager và khả năng mở rộng.
- [Java SE 26 — `javax.tools.ToolProvider`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/ToolProvider.html): lấy compiler hệ thống và trường hợp không khả dụng.
- [Java SE 26 — module `java.compiler`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/module-summary.html): API chuẩn ở Java module system.
- [Java SE 26 — module `jdk.compiler`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.compiler/module-summary.html): triển khai javac và compiler hệ thống.
- [JDK 23 Release Notes — thay đổi mặc định annotation processing](https://www.oracle.com/java/technologies/javase/23-relnote-issues.html): lý do cần cấu hình processor một cách tường minh.

**Ghi nhớ:** JSR 199 cho phép chương trình Java điều phối trình biên dịch bằng **API chuẩn**: cung cấp source, thiết lập options, thực hiện task, thu diagnostics và lấy output. Chỉ áp dụng biên dịch động khi có nhu cầu thực; quản lý compiler/runtime, dependencies và bảo mật riêng. Biên dịch thành công **không tự nạp hoặc chạy** class vừa tạo.

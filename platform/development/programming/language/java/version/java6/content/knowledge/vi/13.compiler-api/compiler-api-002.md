# ToolProvider.getSystemJavaCompiler và môi trường có compiler

## 1. Phương thức này trả về gì?

`javax.tools.ToolProvider.getSystemJavaCompiler()` là điểm vào của **Java Compiler API**. Phương thức tĩnh này trả về một `javax.tools.JavaCompiler` nếu **môi trường Java đang chạy ứng dụng** cung cấp một trình biên dịch Java hệ thống; nếu không có trình biên dịch như vậy, phương thức **trả về `null`**.

~~~java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    // Runtime hiện tại không cung cấp system Java compiler.
} else {
    // Có thể sử dụng JavaCompiler API để biên dịch mã Java.
}
~~~

Đây là **đoạn mã minh họa đặt trong một phương thức**, không phải chương trình Java độc lập. Nó mô tả đúng hợp đồng quan trọng nhất: **luôn kiểm tra `null` trước khi gọi `compiler.getTask(...)` hoặc `compiler.run(...)`**.

Điểm dễ nhầm: ứng dụng **chạy được bytecode Java** không có nghĩa môi trường đó **biên dịch được mã Java**. JVM cần để chạy ứng dụng có thể được đóng gói tối giản; compiler chỉ cần thiết khi chương trình thật sự phải biên dịch nguồn Java tại runtime.

Đối tượng `JavaCompiler` là API gọi compiler **trực tiếp từ chương trình Java hiện tại**, với hỗ trợ diagnostic, file manager và compilation task. Nó không tự động cấp quyền tải hoặc thực thi mã tùy ý, không tự cung cấp công cụ build hoàn chỉnh và cũng không tự làm xuất hiện compiler nếu runtime không đóng gói compiler.

## 2. Vì sao có Java chạy được nhưng `getSystemJavaCompiler() == null`?

Từ Java 9, JDK sử dụng hệ thống module. Cần phân biệt hai thành phần hiện hành:

| Module | Vai trò | Điều gì xảy ra nếu chỉ có module này? |
| --- | --- | --- |
| `java.compiler` | Định nghĩa các API `javax.tools.JavaCompiler`, `javax.tools.ToolProvider`, `DiagnosticCollector`, `JavaFileManager`... | Mã có thể biên dịch và gọi API; **chưa chắc có compiler implementation** |
| `jdk.compiler` | Cung cấp implementation compiler hệ thống (javac) trong các bản JDK thông dụng | Khi module này có mặt và khả dụng, `getSystemJavaCompiler()` có thể trả về compiler thực |

**Đừng đánh đồng `java.compiler` với `jdk.compiler`.** Module thứ nhất chứa *hợp đồng lập trình*; module thứ hai cung cấp *triển khai hệ thống*. Với OpenJDK/Oracle JDK hiện hành, `getSystemJavaCompiler()` sử dụng compiler do `jdk.compiler` cung cấp khi sẵn có và trả `null` trong trường hợp không có system compiler.

Các môi trường điển hình:

- **Chạy bằng JDK đầy đủ** có `jdk.compiler`: thường trả về đối tượng `JavaCompiler` khác `null`.
- **Runtime image tự tạo bằng `jlink`** chỉ mang các module ứng dụng cần để chạy, không có `jdk.compiler`: mã dùng API có thể chạy nếu có `java.compiler`, nhưng `getSystemJavaCompiler()` trả `null`.
- **Container image / runtime tối giản:** kết quả phụ thuộc chính xác image và module thực tế, không phụ thuộc nhãn “Java 17”, “Java 21” hoặc tên image.
- **Hệ thống có nhiều JDK:** lệnh `javac` trên `PATH` có thể trỏ tới một bộ JDK khác với lệnh `java` khởi chạy ứng dụng. Compiler trên `PATH` **không được dùng làm tiêu chí** để kết luận JavaCompiler API sẽ hoạt động.

Trên Java hiện đại, thay vì dựa vào mô hình JRE/JDK cũ để phỏng đoán, hãy **kiểm tra runtime image thực tế**: nó có cung cấp `jdk.compiler` không và API có trả về compiler không?

## 3. Cách kiểm tra compiler tại runtime

### 3.1. Kiểm tra trực tiếp bằng Java

Mẫu kiểm tra tối thiểu:

~~~java
boolean available =
        javax.tools.ToolProvider.getSystemJavaCompiler() != null;
System.out.println("Compiler available: " + available);
~~~

Khi chạy trên JDK có compiler, kết quả là `Compiler available: true`; khi chạy trên runtime không có compiler, kết quả là `Compiler available: false`. Kiểm tra tại chỗ này đáng tin cậy hơn việc chỉ xem tên biến `JAVA_HOME` hoặc sự tồn tại của lệnh `javac` trên máy.

### 3.2. Lệnh kiểm tra môi trường

Trên terminal của **môi trường triển khai thật**, có thể chạy:

~~~sh
java -version
javac -version
java --list-modules
~~~

Xem trong kết quả `java --list-modules` có `java.compiler` và `jdk.compiler` hay không. `javac -version` chỉ chứng minh **shell tìm được lệnh javac**; nó không tự chứng minh tiến trình `java` của ứng dụng dùng cùng runtime image. Để chắc chắn, kiểm tra `java.home` **từ chính tiến trình**:

~~~java
System.out.println(System.getProperty("java.home"));
~~~

Hai đoạn Java trong phần này là **snippet**, có thể đặt trong `main`. Trên máy có nhiều bản Java, công cụ IDE, build runner, container hoặc service manager có thể chọn runtime khác với terminal. Vì vậy, hãy ưu tiên kết quả `getSystemJavaCompiler()` **trong tiến trình cần biên dịch**, không suy đoán từ terminal của máy phát triển.

Nếu ứng dụng chạy bằng named module, module chứa mã gọi `javax.tools` cần khai báo:

~~~java
requires java.compiler;
~~~

Đây là **một directive nằm bên trong `module-info.java`**, không phải tệp `module-info.java` đầy đủ. Nó cho phép truy cập API; muốn biên dịch thành công ở runtime vẫn phải đóng gói một system compiler phù hợp.

## 4. Ví dụ Java 17+ hoàn chỉnh: kiểm tra và thực sự biên dịch mã nguồn

Ví dụ này cho thấy cả hai nhánh **có compiler** và **không có compiler**. Khi có compiler, chương trình tạo nguồn `Generated.java` **trong bộ nhớ**, biên dịch thành `Generated.class` bằng `JavaCompiler.getTask()` và kiểm tra file class đã được ghi. Khi không có compiler, chương trình in trạng thái rồi kết thúc có kiểm soát, không phát sinh `NullPointerException`.

Lưu chương trình sau thành tệp **`CompilerApiDemo.java`**:

~~~java
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
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public class CompilerApiDemo {
    private static final class Source extends SimpleJavaFileObject {
        private final String text;

        Source(String name, String text) {
            super(URI.create("string:///" + name + Kind.SOURCE.extension),
                    Kind.SOURCE);
            this.text = text;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return text;
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            System.out.println("Compiler available: false");
            return;
        }

        System.out.println("Compiler available: true");
        Path output = Path.of("generated-classes");
        Files.createDirectories(output);

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager files =
                     compiler.getStandardFileManager(
                             diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {

            files.setLocationFromPaths(
                    StandardLocation.CLASS_OUTPUT, List.of(output));

            JavaFileObject source = new Source(
                    "Generated",
                    "public class Generated { "
                            + "public static int answer() { return 42; } "
                            + "}");

            Boolean ok = compiler.getTask(
                    null,
                    files,
                    diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null,
                    List.of(source)
            ).call();

            System.out.println(
                    "Compilation success: " + Boolean.TRUE.equals(ok));
            System.out.println(
                    "Class file exists: " +
                    Files.isRegularFile(output.resolve("Generated.class")));

            if (!Boolean.TRUE.equals(ok)) {
                for (Diagnostic<? extends JavaFileObject> d
                        : diagnostics.getDiagnostics()) {
                    System.out.println(
                            d.getKind() + " at line " + d.getLineNumber()
                                    + ": " + d.getMessage(Locale.ROOT));
                }
            }
        }
    }
}
~~~

### 4.1. Biên dịch và chạy trên JDK đầy đủ

Trong thư mục chứa `CompilerApiDemo.java`, dùng JDK 17+:

~~~sh
javac --release 17 CompilerApiDemo.java
java CompilerApiDemo
~~~

Kết quả chính xác khi chạy bằng JDK có system compiler (đã kiểm tra bằng JDK):

~~~text
Compiler available: true
Compilation success: true
Class file exists: true
~~~

Lúc này `generated-classes/Generated.class` đã được tạo. Chương trình **chỉ biên dịch mã nguồn**; nó **chưa tải lớp `Generated` bằng class loader và chưa gọi phương thức `answer()`**. Biên dịch và thực thi là hai bước độc lập.

Nếu một file `Generated.class` cũ đã có trong thư mục đầu ra, kiểm tra `Files.isRegularFile(...)` một mình không đủ xác nhận nó vừa được tạo. Trong chương trình, kiểm tra quan trọng nhất vẫn là `Boolean.TRUE.equals(ok)`; với pipeline thực tế nên biên dịch vào một thư mục output sạch hoặc quản lý artifact theo build ID.

### 4.2. Chạy chương trình trong runtime tối giản không có compiler

Với JDK có `jlink`, có thể tạo một runtime chỉ chứa `java.base` và `java.compiler` (cùng các phụ thuộc module bắt buộc được `jlink` thêm theo đồ thị module):

~~~sh
jlink --add-modules java.base,java.compiler --output runtime-no-compiler
~~~

Trên Linux/macOS, dùng class đã biên dịch từ mục 4.1:

~~~sh
./runtime-no-compiler/bin/java -cp . CompilerApiDemo
~~~

Trên Windows PowerShell, lệnh chạy tương đương:

~~~powershell
.\runtime-no-compiler\bin\java.exe -cp . CompilerApiDemo
~~~

Kết quả đã kiểm tra với runtime tạo bằng `jlink`:

~~~text
Compiler available: false
~~~

**Giải thích:** runtime này có `java.compiler` nên JVM nạp được lớp `CompilerApiDemo` vốn tham chiếu `javax.tools`, nhưng **không có `jdk.compiler` để cung cấp implementation**. Vì vậy API trả `null`, chương trình in trạng thái và thoát bình thường.

Đây là minh họa thực tế rằng **một chương trình cùng bytecode** có thể thấy compiler trên một Java runtime và không thấy compiler trên runtime khác. Nếu muốn runtime tự biên dịch, phải bảo đảm image đóng gói `jdk.compiler` và các thành phần phụ thuộc cần thiết. Không chỉnh sửa các API trong ví dụ chỉ để “đánh lừa” kiểm tra `null`.

## 5. Diễn giải các đối tượng và tùy chọn trong chương trình

| Thành phần | Vai trò |
| --- | --- |
| `ToolProvider.getSystemJavaCompiler()` | Yêu cầu system Java compiler; kiểm tra `null` trước khi dùng |
| `JavaCompiler` | Giao diện compiler cho phép gọi `getTask(...)` hoặc `run(...)` |
| `SimpleJavaFileObject` | Mô tả một tệp Java ảo; ở đây trả về mã nguồn từ `String` |
| `JavaCompiler.CompilationTask` | Một tác vụ biên dịch; gọi `call()` để thực hiện và nhận trạng thái thành công/thất bại |
| `StandardJavaFileManager` | Quản lý nguồn/đầu ra dạng file và location thông dụng |
| `StandardLocation.CLASS_OUTPUT` | Xác định thư mục chứa class file được tạo ra |
| `DiagnosticCollector<JavaFileObject>` | Thu thập các diagnostic để ứng dụng xử lý lỗi và cảnh báo |
| `--release 17` | Yêu cầu compiler nhắm tới nền tảng Java 17, gồm API chuẩn khả dụng và bytecode tương ứng |
| `-proc:none` | Tắt annotation processing trong ví dụ |

Phương thức `getTask(writer, fileManager, listener, options, classes, compilationUnits)` trong ví dụ nhận:

1. `writer = null`: không tùy biến writer mặc định cho phần output không chuyển thành diagnostic.
2. `fileManager = files`: biết vị trí ghi class file vào `generated-classes`.
3. `listener = diagnostics`: thu thập lỗi biên dịch để có thể kiểm tra.
4. `options`: đặt `--release 17`, tắt annotation processing bằng `-proc:none`.
5. `classes = null`: không chỉ định tên lớp riêng để annotation processing.
6. `compilationUnits = List.of(source)`: đúng một nguồn Java trong bộ nhớ.

`getTask(...)` **tạo tác vụ**, còn `call()` **thực thi biên dịch**. Tùy phiên bản compiler, không phải mọi option CLI đều hợp lệ qua API. Với `jdk.compiler` hiện hành, không truyền tùy chọn launcher như `-J...`, argument file `@file` hoặc wildcard classpath kiểu launcher; cần đưa giá trị option thực tế và classpath/module path rõ ràng vào compiler/file manager. Trong ví dụ dùng tập option thông dụng, phù hợp Java 17+.

Chú ý không nhầm **`javax.tools.ToolProvider`** với **`java.util.spi.ToolProvider`** (API cho các công cụ kiểu dòng lệnh). Bài này dùng `javax.tools.ToolProvider.getSystemJavaCompiler()` vì cần một đối tượng `JavaCompiler` và `CompilationTask`. Nếu mục đích chỉ là gọi công cụ tên `javac` với cú pháp gần CLI, `java.util.spi.ToolProvider.findFirst("javac")` là một hướng khác trong JDK có công cụ, nhưng không thay thế phần xử lý diagnostics/file manager của ví dụ.

## 6. Xử lý trường hợp không có compiler trong ứng dụng thật

Một ứng dụng chạy ở nhiều môi trường nên có chính sách rõ ràng nếu compiler là **tính năng bắt buộc** hay **tùy chọn**.

### Compiler bắt buộc

Nếu sản phẩm phải biên dịch plugin/source động tại runtime, thất bại nên được báo **sớm khi khởi động**, cùng gợi ý runtime phải đóng gói compiler:

~~~java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException(
            "This feature requires a Java runtime image with jdk.compiler");
}
~~~

Đây là snippet đặt trong một phương thức Java. Nó chỉ thông báo cấu hình môi trường thiếu thành phần; việc khắc phục là đổi runtime image/module deployment, không phải chỉ thêm một `import`.

Nếu build custom runtime, có thể yêu cầu module compiler khi tạo image:

~~~sh
jlink --add-modules java.base,java.compiler,jdk.compiler --output runtime-with-compiler
~~~

Lệnh này dành cho công đoạn **đóng gói bằng JDK có `jlink`**. Khi chạy trên image được tạo đúng cách, `jdk.compiler` cung cấp compiler. Với dự án có module hoặc phụ thuộc khác, `--add-modules` phải chứa các module ứng dụng cần; compiler cũng có thể cần thêm nhà cung cấp filesystem phù hợp, chẳng hạn `jdk.zipfs` khi phải đọc các JAR. Không mặc định coi chỉ ba module ở ví dụ là đủ cho mọi ứng dụng sản xuất.

### Compiler chỉ là tính năng tùy chọn

Nếu mã Java được biên dịch **trong CI/build**, còn ứng dụng production chỉ tải `.class` hoặc JAR đã tạo, **runtime không nhất thiết phải chứa `jdk.compiler`**. Khi đó tránh gọi Compiler API cho đường chạy thông thường, hoặc tắt riêng chức năng biên dịch động nếu `getSystemJavaCompiler() == null`.

Có thể dùng môi trường build/compiler riêng để xử lý những yêu cầu cần biên dịch rồi chuyển artifact đã kiểm tra cho runtime. Thiết kế này giúp giảm kích thước runtime và tách quyền biên dịch ra khỏi tiến trình xử lý yêu cầu sản xuất.

## 7. Chẩn đoán khi `getSystemJavaCompiler()` bất ngờ trả `null`

Làm lần lượt theo **môi trường thực sự chạy ứng dụng**:

1. **In `System.getProperty("java.home")`** ngay trong tiến trình để biết runtime image mà JVM hiện tại đang dùng. Đừng chỉ dựa vào biến môi trường hoặc IDE.
2. **Xác minh runtime image có `jdk.compiler`** bằng `<đường-dẫn-runtime>/bin/java --list-modules`. Nếu chỉ có `java.compiler` mà không có `jdk.compiler`, API có thể tồn tại nhưng không có system compiler.
3. **So sánh lệnh `java` và `javac`** đang được shell/IDE/CI sử dụng: chúng có thể đến từ hai bản cài khác nhau. Sự hiện diện của lệnh `javac` trên `PATH` không sửa được một tiến trình Java đang chạy bằng image thiếu compiler.
4. **Kiểm tra cách đóng gói container hoặc `jlink`**: module `jdk.compiler` có được thêm vào runtime không? Việc thu nhỏ image có thể đã loại module đó.
5. **Nếu runtime có compiler nhưng compile thất bại**, ngừng chẩn đoán như thể kết quả `null`. Khi đó cần kiểm tra diagnostic, option, classpath, module path, thư mục đầu ra, permission và source code.

Không nên “giải quyết” lỗi bằng việc chuyển sang API nội bộ không ổn định. Hãy bổ sung đúng module implementation cần thiết hoặc điều chỉnh kiến trúc để thực hiện biên dịch tại giai đoạn build.

## 8. Có compiler nhưng biên dịch vẫn thất bại: phân biệt ba loại vấn đề

**A. Compiler vắng mặt (`compiler == null`).** Không thể gọi `getTask` trên đối tượng không tồn tại. Đây là vấn đề **runtime image hoặc deployment**.

**B. Compiler sẵn có nhưng nguồn/option bị lỗi (`task.call() == false`).** Nguyên nhân có thể là sai cú pháp Java, source version không hỗ trợ, thiếu dependency, package/module không tìm thấy, thư mục đầu ra không hợp lệ hoặc processor lỗi. Cần đọc `DiagnosticCollector` để biết loại lỗi, file, dòng và thông điệp thay vì trả về một lỗi chung chung.

**C. Tác vụ ném ngoại lệ:** tùy tình huống có thể gặp `IllegalArgumentException` do option không hợp lệ, `IOException` khi thao tác với file manager hoặc runtime exception do môi trường. Những lỗi cấu hình này cần được ghi nhận/khắc phục; không nên chuyển tất cả thành “compiler not found”.

Ví dụ xử lý một diagnostic bất kỳ (snippet minh họa trong phạm vi có biến `diagnostics`):

~~~java
for (Diagnostic<? extends JavaFileObject> d
        : diagnostics.getDiagnostics()) {
    System.out.printf(
            "%s line %d: %s%n",
            d.getKind(),
            d.getLineNumber(),
            d.getMessage(Locale.ROOT));
}
~~~

Thông điệp diagnostic có thể khác giữa compiler, locale và phiên bản JDK. Để viết kiểm thử vững, so sánh `task.call()`, `Diagnostic.Kind`, mã lỗi hoặc vị trí nguồn khi phù hợp; **không buộc toàn bộ câu chữ thông điệp phải giống nhau trên mọi JDK**.

Compiler API cho phép sử dụng file manager chuẩn hoặc tùy biến. Khi source phụ thuộc thư viện bên ngoài, cần cấu hình classpath/module path tương ứng. Tương tự khi build bằng CLI, **khả năng tìm được compiler** không đồng nghĩa **tìm được mọi dependency của chương trình được biên dịch**.

## 9. Lưu ý cho hệ thống thực tế

- **Tính bảo mật:** biên dịch mã không tin cậy **không phải** thao tác an toàn chỉ vì được gọi qua `JavaCompiler`. Compiler/processor/plugin có thể dùng tài nguyên và chạy mã trong tiến trình. `-proc:none` giúp tắt annotation processing trong ví dụ, **không phải cơ chế sandbox**. Với source không tin cậy, ưu tiên môi trường biên dịch được cô lập với giới hạn CPU, RAM, I/O, thời gian và quyền truy cập; thiết kế thêm kiểm tra artifact trước khi sử dụng.
- **Vòng đời tài nguyên:** đóng `StandardJavaFileManager` bằng `try-with-resources`; dùng thư mục đầu ra rõ ràng, tránh dùng chung file output giữa các tác vụ cạnh tranh, dọn artifact tạm theo chính sách.
- **Hiệu năng:** tạo compiler task cho từng yêu cầu có chi phí. Nếu có nhiều tác vụ độc lập, cân nhắc quản lý hàng đợi, giới hạn số biên dịch đồng thời và tái sử dụng file manager **theo các tác vụ tuần tự** khi phù hợp; không giả định `JavaCompiler` hoặc file manager tùy ý là thread-safe.
- **Tính tái lập:** cố định JDK/toolchain, option `--release`, dependency, module path, locale và cách xử lý annotation processor. Một JDK mới có thể phát hiện lỗi mới hoặc tạo bytecode khác; cần kiểm thử với môi trường triển khai mục tiêu.
- **Triển khai module:** named module cần `requires java.compiler` để dùng API, còn runtime image cần `jdk.compiler` nếu phải thực sự biên dịch bằng compiler hệ thống. Các dependency thêm của compiler/ứng dụng phải được đóng gói đầy đủ.
- **Không chạy mã vừa biên dịch mặc định:** compiler tạo artifact; việc nạp hoặc thực thi bytecode cần chính sách class loader/module layer và cơ chế kiểm soát riêng. Thành công khi biên dịch không đồng nghĩa mã được chấp nhận để thực thi trong production.

## 10. Tự kiểm tra

**Tình huống 1.** Một runtime `jlink` có `java.base` và `java.compiler` nhưng không có `jdk.compiler`. Chương trình chứa `import javax.tools.JavaCompiler` có chạy được không, và `getSystemJavaCompiler()` trả gì?

**Đáp án:** Có thể chạy chương trình vì API đã có; phương thức trả **`null`** do image thiếu system compiler implementation.

**Tình huống 2.** Lệnh `javac -version` chạy bình thường trên terminal nhưng ứng dụng trong container nhận `null`. Có mâu thuẫn không?

**Đáp án:** Không. Hai lệnh có thể dùng các runtime/image khác nhau. Cần kiểm tra `java.home` và module của **tiến trình trong container**.

**Tình huống 3.** `getSystemJavaCompiler()` trả về khác `null`, nhưng `CompilationTask.call()` trả `false`. Có phải nên thêm `jdk.compiler`?

**Đáp án:** Không. Compiler đã tồn tại; đây là lỗi **biên dịch hoặc cấu hình đầu vào**. Đọc diagnostics và rà soát source, dependency, option, output path.

**Tình huống 4.** Việc bật `-proc:none` đã bảo đảm có thể biên dịch bất kỳ mã Java chưa được kiểm duyệt trong production chưa?

**Đáp án:** Chưa. Nó chỉ vô hiệu hóa annotation processing; compilation và artifact vẫn cần cô lập, giới hạn tài nguyên và chính sách tin cậy phù hợp.

**Ghi nhớ:** `ToolProvider.getSystemJavaCompiler()` là **phép kiểm tra system compiler ở chính runtime đang chạy**. Kết quả `null` phản ánh thiếu compiler implementation; compiler khác `null` mới cho phép tiếp tục biên dịch qua `JavaCompiler`, nhưng thành công còn phụ thuộc source, option, file manager và môi trường.

### Tham khảo API hiện hành

- [`javax.tools.ToolProvider` — Java SE API](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/ToolProvider.html): hợp đồng `getSystemJavaCompiler()`.
- [`javax.tools.JavaCompiler` — Java SE API](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/JavaCompiler.html): `getTask`, `getStandardFileManager`, diagnostics.
- [Module `jdk.compiler` — JDK API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.compiler/module-summary.html): implementation compiler hệ thống, module/tool và giới hạn API.

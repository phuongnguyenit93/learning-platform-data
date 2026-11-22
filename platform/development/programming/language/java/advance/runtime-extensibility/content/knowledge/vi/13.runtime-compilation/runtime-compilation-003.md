# Lấy JavaCompiler qua ToolProvider và xử lý kết quả null

Java hỗ trợ **biên dịch mã Java ngay khi ứng dụng đang chạy** bằng API trong gói javax.tools. Điểm vào phổ biến là **ToolProvider.getSystemJavaCompiler()**, trả về đối tượng JavaCompiler của runtime hiện tại **nếu có compiler**. Lời gọi này **có thể trả về null**: một ứng dụng Java chạy được không có nghĩa môi trường đó có khả năng biên dịch Java source.

Đây là vấn đề quan trọng trong hệ thống **runtime extensibility**: host có thể nhận source của plugin, biên dịch thành bytecode rồi nạp lớp mới. Nếu host chạy trên runtime image rút gọn, môi trường triển khai không có module compiler, hoặc dùng nhầm bản Java runtime, tính năng này phải có cách xử lý rõ ràng thay vì ném NullPointerException.

Kết quả cần đạt sau bài học:

1. Biết lấy đúng **javax.tools.JavaCompiler** từ **javax.tools.ToolProvider** và kiểm tra null **trước** khi sử dụng.
2. Hiểu vì sao có Java runtime nhưng không có Java compiler, đặc biệt với JDK 9+ và ảnh runtime tạo bằng **jlink**.
3. Chọn chính sách xử lý khi compiler vắng mặt: **fail-fast**, **vô hiệu hóa tính năng có thông báo**, hoặc sử dụng phương án biên dịch thay thế đã được triển khai có chủ đích.
4. Phân biệt **không có compiler** với **có compiler nhưng biên dịch thất bại**; thu thập diagnostics, đóng file manager và quản lý output/class loader.
5. Chạy được ví dụ Java 17 đầy đủ, với kết quả cố định trong hai trường hợp có và không có compiler.

## 1. JavaCompiler và ToolProvider thực sự làm gì?

Hai kiểu cần import:

~~~java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;
~~~

Trong Java 9 trở đi, các API này thuộc **module java.compiler**. Chúng là giao diện và cơ chế tìm công cụ; **module java.compiler không đồng nghĩa với module thực thi compiler**. Trong bản phân phối JDK 17 thông dụng, compiler hệ thống được cung cấp bởi **module jdk.compiler**.

Lời gọi cơ bản:

~~~java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    // Runtime hiện tại không cung cấp system Java compiler.
} else {
    // Có thể tiếp tục cấu hình và gọi trình biên dịch.
}
~~~

Hợp đồng trả về có hai trường hợp:

| Kết quả | Ý nghĩa | Hành động tiếp theo |
| --- | --- | --- |
| Khác null | Runtime hiện tại cung cấp đối tượng compiler hệ thống | Chọn input, output, options; gọi getTask hoặc run; xử lý kết quả |
| null | Runtime hiện tại **không cung cấp** compiler hệ thống mà ToolProvider có thể lấy | Thực thi chính sách dự phòng hoặc báo không hỗ trợ; **không** gọi phương thức trên null |

Theo tài liệu Java SE 17, cách triển khai JDK trả compiler do **jdk.compiler** cung cấp nếu module này khả dụng, nếu không thì trả **null**. API cho phép môi trường Java có javax.tools mà không bắt buộc có implementation của compiler.

**Điểm cần phân biệt:**

- **JavaCompiler** là API lập trình, không phải đối tượng tự có sẵn trên mọi JVM.
- **ToolProvider.getSystemJavaCompiler()** tìm **compiler của runtime đang chạy tiến trình Java**; nó không tự duyệt biến PATH để chạy file javac.exe hoặc một lệnh javac bất kỳ.
- Một chương trình đã được biên dịch thành .class/.jar chỉ cần JVM có thể thực thi bytecode; điều đó không chứng minh runtime có compiler để tạo bytecode mới.
- Có thể dùng ServiceLoader tìm những implementation JavaCompiler khác do ứng dụng chủ động cung cấp, nhưng **không thể coi đây là fallback tự động** của getSystemJavaCompiler. Nếu có fallback, ứng dụng phải chọn/kiểm tra nó một cách tường minh.

### Đừng nhầm ToolProvider này với API tên gần giống

Trong mã trên, kiểu chính xác là **javax.tools.ToolProvider**. Java còn có các API cung cấp công cụ khác trong JDK, bao gồm java.util.spi.ToolProvider và các tool provider riêng. Chúng không thay thế trực tiếp hợp đồng của **javax.tools.JavaCompiler**, và có thể có cơ chế gọi khác. Khi thiết kế host plugin sử dụng JavaCompiler.CompilationTask, hãy import đúng gói javax.tools.

## 2. Vì sao getSystemJavaCompiler() trả null?

Trường hợp null **không nhất thiết là lỗi mã Java**. Đó là tín hiệu môi trường chạy không có system Java compiler phù hợp.

### 2.1. Chạy bằng runtime không bao gồm trình biên dịch

Trong các hệ Java cũ, người học thường gặp tình huống ứng dụng được khởi động bằng **JRE** thay vì **JDK**. Trên Java 9+, mô hình phân phối đã thay đổi: bản JDK thông dụng có compiler, nhưng có thể tạo **custom runtime image** chỉ chứa các module cần thiết để chạy ứng dụng. Một image như vậy có thể có module java.compiler (API) mà **không có jdk.compiler** (implementation).

Ví dụ ứng dụng chỉ cần tính năng web và đọc file lúc bình thường; nhà vận hành có thể tạo image bằng jlink để giảm kích thước. Khi plugin upload source mới, host đột ngột cần compiler nhưng image không có nó. Nếu code dùng ngay compiler.getTask(...), hệ quả thường là NullPointerException ở runtime.

### 2.2. Tiến trình dùng bản java khác với bản bạn kiểm tra ở terminal

Trên máy có nhiều bản JDK/runtime, câu lệnh java mà IDE, Docker entrypoint, service manager hay container thực sự chạy **có thể khác** bản java/javac bạn gõ tại terminal.

Ví dụ:

~~~text
Shell của người phát triển:
  javac -version  -> javac 17.x

Container ứng dụng:
  /opt/app-runtime/bin/java ...  -> custom runtime không có jdk.compiler

Kết quả:
  ToolProvider.getSystemJavaCompiler() trong container -> null
~~~

Hai dòng trên là **tình huống minh họa**, không phải stdout cố định của một lệnh. ToolProvider chịu sự quyết định của runtime **bên trong tiến trình**, không phải compiler mà người quản trị tình cờ tìm thấy ở một thư mục khác.

### 2.3. Module hoặc ảnh đóng gói không cho compiler tham gia

Trên JDK 17, module **jdk.compiler** là một phần cài đặt compiler. Khi tạo image bằng jlink, hoặc giới hạn các module mà runtime quan sát được, module compiler có thể không khả dụng. Cũng có thể ứng dụng chạy dưới chế độ native image/embedded JVM có tập công cụ khác với JDK phát triển.

Chỉ kiểm tra java.version hoặc Java 17 không đủ để kết luận có compiler. Cách kiểm tra **dứt khoát theo hợp đồng API** vẫn là gọi ToolProvider.getSystemJavaCompiler() rồi xét null.

## 3. Cách kiểm tra đơn giản nhất trước khi dùng compiler

Tạo file **CompilerProbe.java**:

~~~java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public final class CompilerProbe {
    public static void main(String[] args) {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        System.out.println(compiler == null
                ? "SYSTEM_COMPILER_UNAVAILABLE"
                : "SYSTEM_COMPILER_AVAILABLE");
    }
}
~~~

Chạy bằng **JDK 17+**:

~~~bash
javac -encoding UTF-8 CompilerProbe.java
java CompilerProbe
~~~

Nếu runtime đang chạy có system compiler:

~~~text
SYSTEM_COMPILER_AVAILABLE
~~~

Nếu không có:

~~~text
SYSTEM_COMPILER_UNAVAILABLE
~~~

Đây là **hai nhánh có điều kiện**; không phải một lệnh duy nhất luôn in cả hai dòng. Bản ứng dụng dùng để tạo file .class có thể được biên dịch trên máy build, rồi **file .class** được chuyển sang image tối giản để thử nhánh null.

Tại sao ví dụ tách biên dịch và thực thi? Bởi một runtime không có compiler vẫn **chạy được CompilerProbe.class** nếu có java.base và java.compiler phù hợp. Đó chính là ý nghĩa của trường hợp null: **chạy mã Java được** nhưng **không biên dịch mã Java mới được** qua system compiler.

## 4. Xử lý null đúng nghiệp vụ: không có một chính sách cho mọi hệ thống

Lời gọi getSystemJavaCompiler() không tự biết tính năng biên dịch lúc chạy là **bắt buộc** hay **tùy chọn**. Host phải tự quyết định chính sách.

### 4.1. Fail-fast khi plugin source compilation là tính năng bắt buộc

Nếu hệ thống không thể phục vụ yêu cầu khi thiếu compiler, báo lỗi ngay ở giai đoạn kiểm tra cấu hình hoặc khi khởi tạo dịch vụ biên dịch; tránh trì hoãn tới lúc người dùng upload plugin.

~~~java
// Đoạn mã minh họa, đặt trong lớp dịch vụ biên dịch của ứng dụng.
private static JavaCompiler requireSystemCompiler() {
    JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
    if (compiler == null) {
        throw new IllegalStateException(
                "Runtime hiện tại không có system Java compiler; "
                + "hãy chạy với JDK/runtime image có jdk.compiler");
    }
    return compiler;
}
~~~

Ưu điểm: cấu hình triển khai sai được phát hiện sớm và có lỗi rõ ràng. Không nên thay bằng Objects.requireNonNull với thông báo chung chung nếu quản trị viên cần hiểu module nào đang thiếu; thông báo ngoại lệ phải chỉ ra cách sửa.

Nếu ứng dụng vận hành trên cluster, có thể chạy capability check trong health/startup validation; chỉ quảng cáo dịch vụ compile là khả dụng khi kiểm tra thành công. Dù startup có compiler, các lỗi ở lần compile sau vẫn phải được xử lý riêng.

### 4.2. Graceful degradation khi biên dịch chỉ là tính năng tùy chọn

Nếu ứng dụng vẫn có thể đọc/khởi chạy plugin đã biên dịch sẵn mà không cần biên dịch source, thay vì làm ứng dụng chết, hãy vô hiệu hóa **duy nhất** tính năng biên dịch.

~~~java
// Đoạn minh họa trong một phương thức dịch vụ.
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();

if (compiler == null) {
    return "COMPILE_FEATURE_DISABLED";
}

// Tiếp tục sử dụng compiler khi khác null.
~~~

Đoạn code trên chỉ minh họa nhánh điều khiển và giả định phương thức đang trả String; **không phải chương trình chạy độc lập**. Khi đưa vào host thật, nên dùng một kết quả có kiểu như CompileResult với status **UNAVAILABLE**, thay vì mã chuỗi tự do.

Ví dụ response API có thể là HTTP 503 khi tính năng được cấu hình là tạm thời không khả dụng, hoặc lỗi cấu hình/feature flag riêng nếu môi trường này không hỗ trợ compile một cách có chủ đích. Đừng giả vờ compilation đã thành công và đừng biến lỗi “không có compiler” thành “source người dùng sai”.

### 4.3. Cơ chế dự phòng phải có ranh giới rõ

Các lựa chọn khác:

- **Build trước khi triển khai**: CI dùng JDK biên dịch plugin, runtime chỉ nạp artifact đã ký/kiểm tra.
- **Compiler service tách biệt**: host gửi source đến worker/service biên dịch được quản lý riêng, nhận artifact có kiểm tra tính toàn vẹn.
- **Compiler implementation khác**: chỉ dùng nếu có implementation được kiểm chứng, hỗ trợ javax.tools.JavaCompiler và đã tích hợp có chủ ý.

Không viết fallback tùy tiện thành **Runtime.exec("javac ...")** rồi tin rằng hệ thống đã an toàn: cách này dùng một process/toolchain khác với ToolProvider, phải xác định executable path, classpath, timeout, stdin/stdout/stderr, quyền hệ điều hành, nguồn input, resource limits và chính sách bảo mật. Không xử lý null bằng cách “cài đặt compiler trong lúc đang chạy” nếu host production không có quyền/chu trình quản lý phần mềm tương ứng.

### 4.4. Tránh lỗi lập trình phổ biến

~~~java
// SAI: có thể ném NullPointerException ngay khi chạy trên runtime không có compiler.
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
compiler.run(null, System.out, System.err, "-version");
~~~

Bản đúng:

~~~java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    System.err.println("No system compiler in this runtime");
} else {
    int exitCode = compiler.run(null, System.out, System.err, "-version");
    if (exitCode != 0) {
        System.err.println("Compiler tool returned " + exitCode);
    }
}
~~~

Hai đoạn mã là **snippets** có thể đặt trong main hoặc một phương thức phù hợp; không phải hai class độc lập. Lệnh **-version** chỉ minh họa cách gọi API run; với nghiệp vụ biên dịch thực, nên dùng **getTask** và diagnostics để kiểm soát input/output. Đối với run, kết quả được biểu diễn bằng **mã thoát int**; đối với getTask(...).call(), đó là kết quả **Boolean** theo hợp đồng CompilationTask. Đừng trộn hai loại kết quả.

## 5. Ví dụ Java 17 độc lập: lấy compiler, biên dịch source lúc chạy và nạp class

Ví dụ dưới đây kết hợp đầy đủ:

1. Gọi **ToolProvider.getSystemJavaCompiler()**.
2. Nếu null: in thông báo, **không** tạo file manager hoặc gọi getTask.
3. Nếu khác null: tạo một JavaFileObject chứa source code được kiểm soát.
4. Biên dịch source vào một thư mục tạm bằng **JavaCompiler.getTask(...)**.
5. Kiểm tra **Boolean.TRUE.equals(task.call())**, xem diagnostics khi thất bại.
6. Nạp file .class được tạo bằng URLClassLoader, gọi một phương thức public tĩnh.
7. Đóng StandardJavaFileManager và URLClassLoader, rồi xóa thư mục tạm.

Đây là ví dụ dành cho **source tin cậy do chính ứng dụng tạo ra**, không phải mẫu sandbox để biên dịch/chạy source từ người dùng chưa được tin cậy.

### 5.1. File hoàn chỉnh: RuntimeCompilerDemo.java

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.URL;
import java.net.URLClassLoader;
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

public final class RuntimeCompilerDemo {

    private static final String CLASS_NAME = "generated.Hello";

    private static final String SOURCE = """
            package generated;

            public final class Hello {
                public static String message() {
                    return "Hello dynamic";
                }
            }
            """;

    private RuntimeCompilerDemo() {
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();

        if (compiler == null) {
            System.out.println("compiler=unavailable");
            return;
        }

        System.out.println("compiler=available");
        Path outputDir = Files.createTempDirectory("java-compile-demo-");

        try {
            DiagnosticCollector<JavaFileObject> diagnostics =
                    new DiagnosticCollector<>();

            JavaFileObject sourceFile =
                    new SourceFromString(CLASS_NAME, SOURCE);

            boolean compiled;

            try (StandardJavaFileManager manager =
                         compiler.getStandardFileManager(
                                 diagnostics, Locale.ROOT,
                                 StandardCharsets.UTF_8)) {

                List<String> options = List.of(
                        "--release", "17",
                        "-proc:none",
                        "-d", outputDir.toString());

                JavaCompiler.CompilationTask task =
                        compiler.getTask(
                                null, manager, diagnostics,
                                options, null, List.of(sourceFile));

                compiled = Boolean.TRUE.equals(task.call());
            }

            System.out.println("compile=" +
                    (compiled ? "success" : "failure"));

            if (!compiled) {
                for (Diagnostic<? extends JavaFileObject> d
                        : diagnostics.getDiagnostics()) {
                    System.err.println(
                            d.getKind() + ": " +
                            d.getMessage(Locale.ROOT));
                }
                return;
            }

            URL classesUrl = outputDir.toUri().toURL();
            try (URLClassLoader loader = new URLClassLoader(
                    new URL[] { classesUrl },
                    RuntimeCompilerDemo.class.getClassLoader())) {

                Class<?> generated =
                        Class.forName(CLASS_NAME, true, loader);

                Object result = generated
                        .getMethod("message")
                        .invoke(null);

                System.out.println("loaded=" + result);
            }

        } finally {
            deleteDirectory(outputDir);
        }
    }

    private static void deleteDirectory(Path root) throws IOException {
        try (Stream<Path> paths = Files.walk(root)) {
            for (Path path : paths
                    .sorted(Comparator.reverseOrder())
                    .toList()) {
                Files.deleteIfExists(path);
            }
        }
    }

    private static final class SourceFromString
            extends SimpleJavaFileObject {

        private final String source;

        SourceFromString(String className, String source) {
            super(URI.create(
                    "string:///" +
                    className.replace('.', '/') +
                    Kind.SOURCE.extension), Kind.SOURCE);
            this.source = source;
        }

        @Override
        public CharSequence getCharContent(
                boolean ignoreEncodingErrors) {
            return source;
        }
    }
}
~~~

**Lưu file đúng tên RuntimeCompilerDemo.java**, encoding UTF-8. Ví dụ dùng Java text blocks, List.of và Stream.toList(), nên yêu cầu **JDK 17+** để biên dịch chính chương trình ví dụ.

### 5.2. Lệnh biên dịch và chạy

Trong thư mục chứa RuntimeCompilerDemo.java:

~~~bash
javac -encoding UTF-8 RuntimeCompilerDemo.java
java RuntimeCompilerDemo
~~~

Với **JDK 17 đầy đủ**, system compiler sẵn có, thư mục tạm ghi được và mã nguồn tin cậy của ví dụ không bị thay đổi, stdout chính xác:

~~~text
compiler=available
compile=success
loaded=Hello dynamic
~~~

Khi cùng file class RuntimeCompilerDemo.class chạy trên runtime **có API java.compiler nhưng không có compiler implementation**, stdout là:

~~~text
compiler=unavailable
~~~

Chỉ **một trong hai nhánh** chạy tại một thời điểm. Lỗi I/O, quyền ghi, class loading hoặc những vấn đề hệ thống khác là các lỗi riêng có thể khiến chương trình ném exception; ví dụ này cố ý khai báo throws Exception để người học quan sát rõ. Trong sản phẩm cần chuyển chúng thành kết quả có kiểu, telemetry và xử lý vòng đời thích hợp.

### 5.3. Giải thích các điểm then chốt

**Kiểm tra null xảy ra trước mọi tác vụ compile.** Nhờ vậy không có code nào gọi compiler.getStandardFileManager khi compiler là null. Bước này cũng không thực hiện I/O không cần thiết khi tính năng compile không khả dụng.

**SourceFromString** là JavaFileObject có Kind.SOURCE và URI dạng string:///generated/Hello.java. Nó mô tả input cho compiler; đây không phải lớp động đã được JVM nạp. Compiler sẽ tạo bytecode thực sự khi task được gọi.

**StandardJavaFileManager** được lấy từ compiler và đóng bằng try-with-resources. JavaCompiler API có thể tái sử dụng file manager giữa nhiều compilation tasks, nhưng host cần quản lý lifecycle và thread-safety theo thiết kế, không tự chia sẻ tùy ý giữa các tác vụ đồng thời.

**--release 17** yêu cầu compiler tạo code cho nền tảng Java 17; **-d** chọn nơi ghi .class; **-proc:none** tắt annotation processing trong lần biên dịch minh họa. Tắt annotation processing không biến compiler thành sandbox tuyệt đối.

**Boolean.TRUE.equals(task.call())** tránh phụ thuộc vào việc task trả một Boolean boxed cụ thể; đó là bước kiểm tra biên dịch thành công. Đây là kết quả **sau khi đã có compiler**, khác hoàn toàn với việc compiler có thể null lúc đầu.

**URLClassLoader** nạp file class từ thư mục tạm. Đối tượng Class được định nghĩa trong một loader mới, không tự xuất hiện vào classpath hệ thống của ứng dụng. Cần quản lý loader riêng theo phiên plugin và tránh giữ tham chiếu class/instance sau khi plugin đã kết thúc. Khi nạp class bằng Class.forName(name, true, loader), JVM có thể khởi tạo lớp đó và thực thi mã, vì vậy chỉ dùng source **đã tin cậy** trong ví dụ.

**Cleanup** đóng loader trước rồi xóa .class và thư mục tạm theo thứ tự đường dẫn từ sâu đến nông. Trên hệ thật, cần thêm xử lý riêng cho trường hợp xóa thất bại, process crash hoặc artifact được cache ngoài vòng đời yêu cầu.

## 6. Phân biệt ba tầng lỗi: compiler vắng mặt, source sai, và môi trường compile lỗi

Những vấn đề dưới đây thường bị đánh đồng dù cách khắc phục khác nhau:

| Tầng | Dấu hiệu quan sát | Ý nghĩa | Xử lý phù hợp |
| --- | --- | --- | --- |
| **Khả năng (capability)** | ToolProvider.getSystemJavaCompiler() == null | Runtime không cung cấp system compiler | Fail-fast hoặc disable compile, sửa runtime/deployment, chọn fallback được cấu hình |
| **Tác vụ biên dịch** | Compiler khác null nhưng task.call() không thành công | Source, options, dependency, classpath/module path hoặc annotation processing có vấn đề | Thu diagnostics, báo lỗi có ngữ cảnh, giữ runtime ổn định |
| **Hạ tầng/vòng đời** | IOException, lỗi file manager, lỗi tạo thư mục, nạp class, LinkageError, phản chiếu hoặc I/O | Có thể compile được nhưng filesystem, phụ thuộc, class loader hoặc mã đã nạp thất bại | Phân loại lỗi, cleanup, log, retry chỉ khi an toàn |

Một compiler object khác null **không chứng minh** source nào cũng được chấp nhận. Ngược lại, không có compiler **không phải** lỗi cú pháp source. Khi ghi log hoặc trả API, nên có mã kết quả riêng.

Ví dụ status kiểu dữ liệu:

~~~java
// MẪU THIẾT KẾ THÀNH PHẦN, KHÔNG PHẢI CHƯƠNG TRÌNH ĐỘC LẬP.
enum CompileStatus {
    UNAVAILABLE,
    SUCCESS,
    COMPILATION_FAILED,
    INFRASTRUCTURE_ERROR
}
~~~

Sử dụng enum và một CompileResult chứa diagnostics để phân biệt lỗi lành mạnh hơn so với chỉ trả boolean. Nếu thành công nhưng bước nạp class sau đó thất bại, hãy ghi nhận riêng trạng thái **LOAD_FAILED**, vì đó là một giai đoạn khác với compilation.

### 6.1. JavaCompiler.run khác getTask.call

Một cách gọi compiler đơn giản:

~~~java
// Đoạn này giả định compiler khác null.
int status = compiler.run(
        null, System.out, System.err,
        "-d", "build", "src/demo/Example.java");
~~~

- **run(...)** nhận các đường dẫn/options dạng String tương tự tool command line và trả **int**: 0 biểu thị thành công theo quy ước của tool; kết quả khác 0 báo lỗi.
- **getTask(...)** cho phép truyền JavaFileObject, DiagnosticListener, file manager, options và classes; trả CompilationTask với **call()** có kết quả Boolean.
- Nếu cần compiler input in-memory và báo lỗi có vị trí trong source, **getTask + DiagnosticCollector** thường phù hợp hơn.
- **Đừng** xem trạng thái null của ToolProvider giống với null của một kết quả compilation. Chúng xảy ra ở hai tầng khác nhau.

Đoạn run ở trên chỉ minh họa API, cần tồn tại file src/demo/Example.java và thư mục/đường ghi hợp lệ khi chạy thực tế; nó **không phải chương trình độc lập**.

### 6.2. Diagnostics giúp hiển thị lỗi source chính xác hơn

JavaCompiler có thể báo loại, file, dòng, cột và thông điệp của lỗi:

~~~java
DiagnosticCollector<JavaFileObject> errors =
        new DiagnosticCollector<>();

// Cần JavaCompiler và JavaFileManager hợp lệ để tạo task.
// Sau task.call():
for (Diagnostic<? extends JavaFileObject> d
        : errors.getDiagnostics()) {
    System.out.println(d.getKind()
            + " at line " + d.getLineNumber()
            + ": " + d.getMessage(Locale.ROOT));
}
~~~

Đây là **snippet chẩn đoán** đặt sau một task thực sự dùng đối tượng errors, không phải code chạy riêng. Dùng Locale.ROOT giúp hành vi thông điệp rõ hơn nhưng **không** bảo đảm một chuỗi chẩn đoán chữ-đúng 100% trên mọi bản compiler/vendor/JDK. Đừng viết test brittle dựa vào nguyên văn tiếng Anh của diagnostic.

Các diagnostic source có thể lộ dữ liệu người dùng, tên file, classpath hoặc đường dẫn tạm. Trên server, cần giới hạn dung lượng, ẩn thông tin nhạy cảm khi log, và trả diagnostics tới đúng chủ thể có quyền xem source.

## 7. Chẩn đoán runtime khi compiler bị null

Khi ứng dụng production ghi nhận không có compiler, làm theo thứ tự:

### Bước 1 — xác định runtime thực sự đang chạy

Chạy đúng executable hoặc vào process/container đang chạy ứng dụng:

~~~bash
java -version
java --list-modules
~~~

Với bản phân phối JDK và cấu hình quyền phù hợp, có thể kiểm tra:

~~~bash
javac -version
~~~

**Chú ý:** lệnh javac trong shell chỉ xác nhận file javac mà shell tìm thấy. Nó **không phải bằng chứng** ToolProvider trong tiến trình server có thể trả JavaCompiler; hai tiến trình có thể sử dụng đường runtime hoặc image khác nhau.

Trong code đang chạy, ghi thông tin tối thiểu được phép:

~~~java
// Snippet chẩn đoán, đặt vào phương thức đang chạy của host.
System.out.println("java.version=" +
        System.getProperty("java.version"));
System.out.println("java.home=" +
        System.getProperty("java.home"));
System.out.println("compiler.present=" +
        (ToolProvider.getSystemJavaCompiler() != null));
~~~

Đây là snippet để hỗ trợ chẩn đoán. Không xuất tràn đường dẫn, biến môi trường hoặc cấu hình nhạy cảm vào response công khai.

### Bước 2 — kiểm tra module compiler

Trong JDK 17, **javax.tools** nằm ở **java.compiler**, còn implementation compiler hệ thống nằm ở **jdk.compiler**. Tìm module trong kết quả **java --list-modules** của đúng runtime. Có thể kiểm tra module trong boot layer ở thời điểm chạy:

~~~java
// Chỉ là phép kiểm tra phụ trợ, không thay ToolProvider.
boolean compilerModuleResolved =
        ModuleLayer.boot().findModule("jdk.compiler").isPresent();
~~~

Một bản runtime không có jdk.compiler thường không có system Java compiler. Tuy nhiên không viết code ứng dụng chỉ dựa vào tên module để quyết định kết quả: **getSystemJavaCompiler() == null** vẫn là kiểm tra công khai trực tiếp theo API.

Nếu code tự đóng gói thành named module và import javax.tools, descriptor thông thường cần:

~~~java
module demo.runtime.compiler.host {
    requires java.compiler;
}
~~~

**requires java.compiler** giúp module host đọc API javax.tools. Nó không bảo đảm image được đóng gói có compiler implementation. Tránh khai báo requires jdk.compiler chỉ vì muốn sử dụng JavaCompiler: đó là module triển khai công cụ, trong khi code host chỉ cần API công khai của java.compiler; việc đóng gói và cấp quyền khả dụng compiler là một quyết định runtime/deployment khác.

### Bước 3 — kiểm tra custom image/jlink

Từ một JDK 17 đầy đủ, có thể tạo image chỉ mang API javax.tools nhưng **không** mang system compiler để kiểm thử nhánh null:

~~~bash
jlink --module-path "$JAVA_HOME/jmods" \
  --add-modules java.base,java.compiler \
  --output image-no-compiler

./image-no-compiler/bin/java -cp . CompilerProbe
~~~

Nếu CompilerProbe.class đã được biên dịch trước bằng JDK đầy đủ, output kỳ vọng là:

~~~text
SYSTEM_COMPILER_UNAVAILABLE
~~~

Để tạo image có implementation compiler, thêm **jdk.compiler**:

~~~bash
jlink --module-path "$JAVA_HOME/jmods" \
  --add-modules java.base,java.compiler,jdk.compiler \
  --output image-with-compiler

./image-with-compiler/bin/java -cp . CompilerProbe
~~~

Trên một JDK 17 đầy đủ và image được tạo đúng, output kỳ vọng:

~~~text
SYSTEM_COMPILER_AVAILABLE
~~~

Hai lệnh jlink là **hai lần tạo image khác nhau**. Thư mục output phải chưa tồn tại; JAVA_HOME phải trỏ tới một JDK có thư mục jmods và jlink; chạy trong Bash trên Linux/macOS/Git Bash. Trên Windows, dùng cú pháp đường dẫn, biến môi trường và executable phù hợp. Với module graph của ứng dụng thực, phải thêm tất cả module còn cần thiết thay vì chỉ lấy tối thiểu từ minh họa.

**Không dùng jlink như một thao tác “sửa nóng” tại runtime**. Hãy thay đổi image trong pipeline build/deploy, kiểm thử nó trong môi trường giống production và phát hành lại. Một image gọn cho production chỉ cần biên dịch **trước khi đóng gói** nếu không muốn cài compiler trong runtime.

### Bước 4 — xem launcher và container deployment

Tại Dockerfile, entrypoint, service unit và cấu hình IDE:

- Xác minh **java executable** thực sự khởi động host, không chỉ JAVA_HOME trên máy phát triển.
- Xác minh runtime image/container có **jdk.compiler**, hoặc đã chuyển tính năng compile sang build/worker chuyên dụng.
- Nếu dùng nhiều runtime layers, xác minh mỗi workload cần biên dịch đều chạy trong image tương ứng.
- Kiểm tra các tùy chọn giới hạn module hoặc tạo module layer; đừng suy luận từ danh sách JAR trên disk.
- Sau khi sửa image, chạy CompilerProbe bằng **chính executable triển khai** trước khi bật feature compile cho người dùng.

## 8. Kiểm thử nhánh null ngay cả khi máy phát triển có compiler

Nếu máy phát triển luôn chạy JDK đầy đủ, nhánh null dễ không bao giờ được chạy. Cách kiểm thử tốt là **tiêm khả năng truy xuất compiler**, không tìm mẹo làm hỏng biến PATH.

Ví dụ ngắn:

~~~java
import java.util.function.Supplier;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public final class CompilerPolicyDemo {
    private static String status(Supplier<JavaCompiler> supplier) {
        return supplier.get() == null ? "UNAVAILABLE" : "AVAILABLE";
    }

    public static void main(String[] args) {
        System.out.println("simulated=" + status(() -> null));
        System.out.println("actual=" +
                status(ToolProvider::getSystemJavaCompiler));
    }
}
~~~

Biên dịch:

~~~bash
javac -encoding UTF-8 CompilerPolicyDemo.java
java CompilerPolicyDemo
~~~

Dòng thứ nhất **luôn** là:

~~~text
simulated=UNAVAILABLE
~~~

Dòng thứ hai tùy runtime là **actual=AVAILABLE** hoặc **actual=UNAVAILABLE**. Đây là kiểm thử chính sách xử lý null độc lập với việc máy phát triển có compiler hay không. Với unit test thật, nên tiêm Supplier/CompilerProvider vào một CompileService và khẳng định nhánh UNAVAILABLE không gọi thêm file manager, không ghi output và có error status đúng. Không cần tự cài giả JavaCompiler chỉ để kiểm tra nhánh null đơn giản.

Đồng thời cần một integration test bằng **runtime image không có compiler** như mục 7 để xác minh điều kiện triển khai thực sự, vì test dùng Supplier giả không chứng minh image production được đóng gói đúng.

### Ma trận kiểm thử nên có

| Trường hợp | Kỳ vọng |
| --- | --- |
| Full JDK 17, source hợp lệ | Compiler khác null, biên dịch thành công, có artifact hợp lệ |
| Full JDK 17, source lỗi cú pháp | Compiler khác null nhưng compilation thất bại, diagnostics có lỗi |
| Custom image có java.compiler nhưng thiếu jdk.compiler | ToolProvider trả null; host báo UNAVAILABLE/disable theo chính sách |
| Source hợp lệ nhưng thư mục output không ghi được | Báo infrastructure error; cleanup, không kết luận compiler vắng mặt |
| Biên dịch thành công nhưng nạp class lỗi | Báo load/link error riêng, không gộp thành null compiler |
| Có hai yêu cầu compile đồng thời | Input/output riêng, file manager/lifecycle hợp lệ, không ghi đè artifact |
| Plugin không tin cậy | Không chạy source/class đã tạo trong host process nếu không có ranh giới cách ly được đánh giá phù hợp |

## 9. Vòng đời JavaCompiler trong một hệ plugin

Đối với host thường xuyên biên dịch code động, kiểm tra null là **bước đầu**, không thay thế thiết kế lifecycle.

### 9.1. Khi nào kiểm tra?

- **Ở startup**: nếu host bắt buộc có compiler, kiểm tra sớm và từ chối bật chức năng khi thiếu.
- **Ở capability/feature initialization**: nếu optional, ghi nhận khả năng compile để giao diện/REST API hiển thị đúng.
- **Trước mỗi lần dùng trong service**: code vẫn nên có guard rõ ràng, đặc biệt ở ranh giới tích hợp và trong test.

Không cache một biến boolean từ startup rồi bỏ kiểm tra logic sử dụng về sau nếu mã có thể chạy trong nhiều mode hoặc đối tượng compiler được cung cấp khác nhau. Ngược lại, cũng không cần tra cứu lặp đi lặp lại một cách vô ích ở mỗi dòng code; một service được khởi tạo với compiler hoặc trạng thái UNAVAILABLE có thể làm rõ phụ thuộc.

### 9.2. Không trộn file và class loader của nhiều plugin

Mỗi lần compile nên có:

1. Input source được định danh rõ (binary class name, package).
2. Tập tùy chọn cố định và được kiểm soát: --release, classpath/module-path, -d, -proc:none nếu không muốn annotation processors.
3. Output directory hoặc in-memory JavaFileManager riêng cho lần biên dịch.
4. Diagnostics liên kết với đúng yêu cầu/tenant.
5. Class loader hoặc module layer gắn với phiên plugin; API chung được chia sẻ phù hợp để không nhân bản kiểu.
6. Quy trình commit/rollback artifact, đóng manager/loader và dọn file tạm.
7. Giới hạn tải, số request, kích thước source/artifact và quan sát latency.

Một đối tượng JavaCompiler có thể tạo nhiều CompilationTask, nhưng không suy ra file manager được chia sẻ tự do giữa các thread. Với quy mô lớn, cần hiểu hợp đồng cụ thể của implementation và điều phối compile jobs; thường **đơn giản hơn khi mỗi task có một file manager/output scope riêng**.

### 9.3. Phân biệt compiler với class loader

**Biên dịch thành công** tạo .class, không tự cài class vào application class loader. Muốn thực thi plugin vừa biên dịch, host còn phải đưa artifact vào class loader hoặc module layer thích hợp, kiểm tra type compatibility, vòng đời và phạm vi quyền của mã mới. Đây là bước sau JavaCompiler.

Không cố dùng ToolProvider để “hot reload” một Class đã được loader cũ định nghĩa: cùng defining loader không thể định nghĩa lại class bình thường bằng cách ghi đè .class trên disk. Thực hiện cập nhật plugin bằng lớp/loader phiên mới hoặc cơ chế instrument được thiết kế riêng; dọn tham chiếu phiên cũ theo chính sách.

## 10. Bảo mật khi biên dịch lúc chạy

**Có JavaCompiler không đồng nghĩa được phép biên dịch hoặc nạp source tùy ý.** Nếu source đến từ người dùng không tin cậy:

- Bản thân giai đoạn **biên dịch** có thể tiêu thụ CPU, RAM, disk và thông tin classpath đáng kể. Annotation processors có thể chạy mã, do đó cân nhắc **-proc:none** nếu không cần processors; nếu cần processors, chỉ tin cậy danh sách và nguồn processor được cho phép.
- Giai đoạn **nạp hoặc thực thi bytecode** là nguy cơ khác: code có thể đọc file, truy cập mạng, dùng reflection hoặc gọi API host theo quyền tiến trình. Dùng URLClassLoader đơn thuần **không phải sandbox**.
- Không coi Java SecurityManager (đã deprecated ở các JDK hiện đại) là ranh giới an toàn chung cho mọi phiên bản; cần isolation cấp process/container/VM, chính sách hệ điều hành, giới hạn tài nguyên và môi trường chạy được kiểm soát.
- Không cho source tự chọn tùy ý classpath/module path, compiler flags, output directory hay file path; validate input, chặn path traversal và tránh ghi đè artifact quan trọng.
- Có timeout, quota, giới hạn diagnostics, dọn file tạm, theo dõi compilation jobs và chính sách hủy/cô lập khi vượt giới hạn. **CompilerTask.call() không có tham số timeout riêng**; nếu cần hủy compilation độc hại/treo, cách ly trong worker process giúp giới hạn và dừng an toàn hơn.
- Khi dùng compiler service bên ngoài, xác thực request, kiểm tra artifact trả về, ghi nhận version compiler và bảo vệ secrets; lỗi service không phải đồng nghĩa ToolProvider trả null.

Đối với mã tự sinh nội bộ, vẫn nên quy định đường dẫn output và cleanup để ngăn lỗi vận hành; biện pháp bảo mật mạnh tùy mức độ tin cậy của source, dependency và nơi thực thi plugin.

## 11. Những hiểu nhầm hay gặp

**“Chạy Java 17 thì chắc chắn có javac trong API.”** Sai. Java SE bảo đảm các interface cần thiết nhưng không đòi hỏi mọi runtime đều cung cấp compiler. Custom image có thể bỏ jdk.compiler.

**“Thêm import javax.tools.ToolProvider là đủ.”** Sai. Import và việc có module java.compiler không tự tạo compiler implementation. Cần kiểm tra kết quả trả về.

**“Nếu máy có javac trên PATH, getSystemJavaCompiler không thể null.”** Sai. API tìm system tool của runtime hiện tại, không chạy một shell tìm lệnh javac.

**“JavaCompiler null là do source Java sai cú pháp.”** Sai. Khi null, thậm chí chưa có compilation task; lỗi source chỉ xuất hiện sau khi đã lấy được compiler và biên dịch.

**“Compiler khác null nghĩa là task chắc chắn thành công.”** Sai. Lỗi syntax, classpath, dependencies, annotation processor, I/O hoặc option vẫn có thể làm task thất bại.

**“Chỉ cần requires java.compiler thì chắc chắn có compiler.”** Sai. Dòng này cho phép module đọc API javax.tools; implementation có thể vắng mặt khỏi image.

**“Có thể chữa null bằng java.util.spi.ToolProvider hoặc getSystemToolClassLoader.”** Không đúng như fallback chung. Đó là API/đường đi khác; trong JDK 17, phương thức **getSystemToolClassLoader()** của javax.tools.ToolProvider đã deprecated và implementation luôn trả null, không nên dựa vào nó.

**“Tắt annotation processing làm mã người dùng an toàn.”** Không đúng. Nó giảm một kênh thực thi mã lúc compile, nhưng không bảo vệ khi code đã biên dịch được nạp/chạy. Cần ranh giới tin cậy và cách ly.

**“Biên dịch được rồi thì class tự xuất hiện trong ứng dụng.”** Sai. Sau compilation còn việc nạp bytecode qua loader/module layer đúng, kiểm tra API identity và quản lý lifecycle.

## 12. Checklist triển khai

Trước khi bật tính năng biên dịch plugin lúc chạy, kiểm tra:

- **Runtime**: xác định chính xác Java executable đang chạy host và cấu trúc runtime image thực tế.
- **API**: dùng đúng javax.tools.ToolProvider và javax.tools.JavaCompiler.
- **Null guard**: xét null trước mọi getStandardFileManager/getTask/run.
- **Chính sách**: xác định compile là bắt buộc hay tùy chọn; có thông báo và status riêng cho UNAVAILABLE.
- **Module**: ứng dụng named module có requires java.compiler; image nếu cần compiler hệ thống có module jdk.compiler.
- **Input**: source, encoding, binary name, release target và dependency path được kiểm soát.
- **Kết quả**: phân biệt compiler null, compilation false và exception của hạ tầng.
- **Diagnostics**: thu lỗi có vị trí hợp lệ, giới hạn dữ liệu log và tránh phụ thuộc nguyên văn thông điệp của một vendor/JDK.
- **Resource**: đóng file manager, class loader, output streams; dọn thư mục tạm và xử lý lỗi cleanup.
- **Security**: không chạy bytecode người dùng không tin cậy ngay trong tiến trình host; có isolation/quota/timeout thích hợp.
- **Kiểm thử**: test full JDK, image thiếu compiler, source hợp lệ/không hợp lệ, lỗi output và load class; theo dõi tính năng sau triển khai.

**Tóm lại:** ToolProvider.getSystemJavaCompiler() là cách trực tiếp để hỏi runtime có cung cấp **system Java compiler** hay không. **null là một kết quả hợp lệ của API** cần được xử lý như một nhánh năng lực hệ thống; chỉ khi compiler khác null mới tạo compilation task, đánh giá kết quả compile và tiến hành nạp plugin. Thiết kế đúng còn đòi hỏi runtime image phù hợp, diagnostics rõ ràng, đóng tài nguyên và ranh giới bảo mật cho mã động.

## Tài liệu tham khảo chính thức

- [Java SE 17 — javax.tools.ToolProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html): hợp đồng getSystemJavaCompiler() và điều kiện trả null.
- [Java SE 17 — javax.tools.JavaCompiler](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html): getTask, run, getStandardFileManager và CompilationTask.
- [Java SE 17 — javax.tools package](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/package-summary.html): framework tools/diagnostics và phạm vi API.
- [JDK 17 — jlink](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html): xây dựng runtime image theo module.
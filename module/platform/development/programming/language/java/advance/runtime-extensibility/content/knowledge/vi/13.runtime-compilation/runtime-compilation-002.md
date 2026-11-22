# Phân biệt module java.compiler, jdk.compiler và trình biên dịch thực tế

## 1. Ba khái niệm không đồng nghĩa

Khi Java ứng dụng muốn biên dịch mã nguồn ngay lúc chạy—chẳng hạn hệ thống plugin, sandbox thực hành hoặc trình tạo mã—cần phân biệt **API biên dịch**, **implementation của JDK** và **công cụ thực sự có thể sử dụng trong runtime hiện tại**.

| Thành phần | Vai trò | Có gì? |
|---|---|---|
| \`java.compiler\` | Module chuẩn Java SE định nghĩa API biên dịch | \`javax.tools.JavaCompiler\`, \`ToolProvider\`, \`JavaFileObject\`, \`DiagnosticCollector\` |
| \`jdk.compiler\` | Module của JDK chứa compiler implementation | Trình biên dịch \`javac\` và các API \`com.sun.source.*\`, implementation liên quan |
| Trình biên dịch thực tế | Compiler được ứng dụng chọn và có thể gọi ở runtime | System compiler, công cụ \`javac\` bên ngoài, hoặc compiler khác hỗ trợ hợp đồng |

**Điểm mấu chốt:** có module \`java.compiler\` không có nghĩa máy ảo hiện tại chứa compiler implementation. API chỉ định nghĩa cách giao tiếp; một runtime image tùy chỉnh có thể không chứa \`jdk.compiler\`. Do đó \`ToolProvider.getSystemJavaCompiler()\` có thể trả về \`null\`.

## 2. \`java.compiler\`: hợp đồng Java Compiler API

\`java.compiler\` là module tiêu chuẩn cung cấp package \`javax.tools\`. Những kiểu thường gặp:

- \`JavaCompiler\`: interface biểu diễn compiler xử lý Java source;
- \`JavaCompiler.CompilationTask\`: tác vụ biên dịch có thể gọi qua \`call()\`;
- \`ToolProvider\`: cách lấy system compiler theo quy tắc JDK;
- \`JavaFileObject\` và \`SimpleJavaFileObject\`: mô hình tệp nguồn/class, có thể xây dựng in-memory file object;
- \`StandardJavaFileManager\`: xử lý tệp chuẩn và đường dẫn;
- \`DiagnosticListener\`/\`DiagnosticCollector\`: nhận lỗi, cảnh báo và thông tin dòng/cột;
- \`JavaFileManager\`: có thể tùy chỉnh để lưu kết quả ra bộ nhớ.

Một named module dùng API này khai báo:

\`\`\`java
module example.host {
    requires java.compiler;
}
\`\`\`

Nếu dùng classpath (unnamed module) trong runtime JDK thông thường, thường không cần \`module-info.java\`.

**Cần phân biệt \`javax.tools\` với \`javax.annotation.processing\`**: cả hai thuộc phạm vi API biên dịch nhưng chức năng khác nhau. Một bên quản lý compiler/file manager/diagnostics, bên kia cung cấp annotation processing API. Đối với plugin chạy mã mới, việc biên dịch bytecode chỉ là một bước; phải có class loader/module layer riêng để định nghĩa class và quản lý vòng đời.

## 3. \`jdk.compiler\`: implementation của javac

\`jdk.compiler\` là module đặc thù JDK cung cấp implementation của Java compiler. Trong JDK hiện đại, module này bao gồm command compiler provider và các package như \`com.sun.source.tree\`, \`com.sun.source.util\` dành cho phân tích cây cú pháp.

Có thể xem thông tin module trên JDK:

\`\`\`bash
java --describe-module jdk.compiler
\`\`\`

Hoặc:

\`\`\`bash
java --list-modules
\`\`\`

Kết quả phụ thuộc bản phân phối và runtime image. Ví dụ trên một JDK 17 đầy đủ, danh sách thường có \`java.compiler@17...\` và \`jdk.compiler@17...\`. Không nên hardcode phiên bản hoặc toàn bộ output vì vendor, bản vá và cách tạo runtime image có thể khác.

\`jdk.compiler\` **không đồng nghĩa với việc mọi class nội bộ \`com.sun.tools.javac.*\` là public API ổn định**. JPMS có cơ chế export package; code ứng dụng nên dùng \`javax.tools\` khi chỉ cần biên dịch, và dùng public API \`com.sun.source.*\` khi cần thông tin AST được hỗ trợ. Tránh truy cập trực tiếp các package implementation nội bộ vì có thể bị chặn bởi module encapsulation hoặc thay đổi giữa các phiên bản JDK.

Trong thiết kế thông thường, **host chỉ cần \`requires java.compiler\`**, không cần \`requires jdk.compiler\` chỉ để gọi \`ToolProvider.getSystemJavaCompiler()\`. Điều này giữ code của host phụ thuộc vào hợp đồng Java SE và cho phép kiểm tra implementation vào runtime.

## 4. \`ToolProvider.getSystemJavaCompiler()\` và \`null\`

\`javax.tools.ToolProvider.getSystemJavaCompiler()\` trả về compiler do môi trường Java hiện tại cung cấp theo cơ chế system compiler. Khi không có compiler, kết quả là \`null\`.

\`\`\`java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException("No system Java compiler available");
}
\`\`\`

*Đoạn này minh họa cách kiểm tra, chưa là chương trình độc lập.*

Một số tình huống cần đặc biệt chú ý:

- **JDK đầy đủ**: thông thường có compiler khả dụng.
- **Runtime image \`jlink\` chỉ gồm module cần chạy**: có thể có \`java.compiler\` nhưng thiếu \`jdk.compiler\`; system compiler không khả dụng.
- **Container tối giản**: image runtime có thể không có compiler dù máy phát triển có JDK.
- **Ứng dụng chạy bằng native image hoặc runtime đặc thù**: cơ chế compiler/Java module có thể khác JVM JDK thường; cần xác minh trên môi trường triển khai thực tế.
- **JDK compiler module có nhưng đường dẫn output không ghi được**: compiler tồn tại, nhưng compilation vẫn thất bại vì quyền ghi/đường dẫn/classpath/module path.

Trước khi tuyên bố hệ thống hỗ trợ biên dịch lúc chạy, phải kiểm tra **compiler tồn tại**, **source/target/release phù hợp**, **dependency path đúng**, **file manager đủ quyền** và **môi trường có tài nguyên cần thiết**.

## 5. Ví dụ Java 17+ đầy đủ: phát hiện và chạy system compiler

Tạo tệp **\`CompilerProbe.java\`**:

\`\`\`java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class CompilerProbe {
    public static void main(String[] args) throws IOException {
        System.out.println("java.compiler present: " +
                ModuleLayer.boot().findModule("java.compiler").isPresent());
        System.out.println("jdk.compiler present: " +
                ModuleLayer.boot().findModule("jdk.compiler").isPresent());

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        System.out.println("system compiler present: " + (compiler != null));
        if (compiler == null) {
            return;
        }

        Path dir = Files.createTempDirectory("compiler-demo-");
        Path source = dir.resolve("Hello.java");
        Files.writeString(source, """
                public class Hello {
                    public static String message() { return "compiled"; }
                }
                """);

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
                     compiler.getStandardFileManager(diagnostics, null, null)) {
            Iterable<? extends JavaFileObject> units =
                    manager.getJavaFileObjects(source.toFile());
            List<String> options = List.of(
                    "--release", "17",
                    "-d", dir.toString()
            );
            JavaCompiler.CompilationTask task =
                    compiler.getTask(null, manager, diagnostics,
                            options, null, units);

            boolean successful = Boolean.TRUE.equals(task.call());
            System.out.println("compilation successful: " + successful);
            System.out.println("class file present: " +
                    Files.exists(dir.resolve("Hello.class")));

            diagnostics.getDiagnostics().forEach(
                    d -> System.err.println(d.getKind() + ": " +
                            d.getMessage(null)));
        }
    }
}
\`\`\`

Chạy trên **JDK 17+ có \`jdk.compiler\` và hỗ trợ \`--release 17\`**:

\`\`\`bash
javac CompilerProbe.java
java CompilerProbe
\`\`\`

Kết quả khi chạy trên JDK 17 đầy đủ với các module được resolve thông thường:

\`\`\`text
java.compiler present: true
jdk.compiler present: true
system compiler present: true
compilation successful: true
class file present: true
\`\`\`

Chương trình tạo thư mục tạm, ghi \`Hello.java\`, dùng Java Compiler API biên dịch nó vào cùng thư mục, và kiểm tra có \`Hello.class\`. Việc biên dịch **không tự chạy \`Hello\`**: muốn sử dụng class cần loader phù hợp hoặc tích hợp với module layer và lifecycle của plugin. Để tránh tích lũy file tạm trong ứng dụng thật, cần bổ sung chính sách dọn dẹp; ví dụ giữ thư mục để có thể kiểm tra output.

Không nên lấy tên \`java.compiler\` hoặc \`jdk.compiler\` trong \`ModuleLayer.boot()\` làm bằng chứng duy nhất. Kiểm tra \`compiler != null\` mới là bước sát mục tiêu, và kết quả \`task.call()\` mới cho biết một lần biên dịch cụ thể thành công hay không.

## 6. Đánh giá module có mặt bằng ModuleLayer và ModuleFinder

Có hai mức câu hỏi:

**(1) Module hiện thuộc layer hay chưa?**

\`\`\`java
boolean inBootLayer =
        ModuleLayer.boot().findModule("jdk.compiler").isPresent();
\`\`\`

**(2) Runtime image có module để tìm kiếm không?**

\`\`\`java
boolean observable =
        java.lang.module.ModuleFinder.ofSystem()
                .find("jdk.compiler")
                .isPresent();
\`\`\`

\`ModuleFinder.ofSystem()\` tìm module trong system module image; nó không tự tạo compiler instance hoặc tự resolve module trong boot layer. Hai kết quả có thể khác nhau nếu module có trong image nhưng không được resolve vào layer đang xét.

Khi chọn runtime image cho ứng dụng, **khả năng tìm thấy module khác với việc compiler thực sự có thể gọi và biên dịch thành công**. Host nên đánh giá theo feature test thích hợp, nhất là khi chạy trong image được tạo bằng \`jlink\`.

### Ví dụ module-info.java cho host

\`\`\`java
module example.runtimecompiler.host {
    requires java.compiler;
}
\`\`\`

Host chỉ phụ thuộc vào giao diện trong \`java.compiler\`; runtime deployment quyết định có implementation phù hợp không. Nếu dùng package \`com.sun.source.*\` của JDK compiler, cần cân nhắc dependency tường minh \`requires jdk.compiler\`, đồng thời chấp nhận đây là dependency đặc thù JDK.

## 7. Tự thiết kế runtime image với jlink

Một ví dụ tạo image chứa compiler:

\`\`\`bash
jlink --add-modules java.base,java.compiler,jdk.compiler \
      --output runtime-with-compiler
\`\`\`

Sau đó dùng executable \`java\` trong thư mục \`runtime-with-compiler/bin\` để chạy ứng dụng đã biên dịch. Khi triển khai thực tế, thêm các module mà host và plugin thực sự cần. Cần chú ý compiler implementation có các dependency module riêng và \`jlink\` sẽ giải quyết dependencies theo module graph.

Một image không chứa \`jdk.compiler\` có thể vẫn chứa \`java.compiler\` nếu ứng dụng cần compile API như một phần của dependency graph nhưng không có compiler implementation để chạy.

**Giới hạn quan trọng:** runtime image được tạo bởi \`jlink\` không đồng nghĩa một bộ JDK đầy đủ. Nó có thể thiếu executable \`javac\` trong \`bin\` ngay cả khi runtime đủ module để Java Compiler API hoạt động. Hãy phân biệt compile **in-process qua \`javax.tools\`** với gọi command **\`javac\` bên ngoài**. Khả năng có command-line tool cần được xác minh riêng.

## 8. Compiler API so với \`javac\` command và compiler bên thứ ba

Có ba chiến lược thực thi biên dịch:

| Chiến lược | Ưu điểm | Ràng buộc |
|---|---|---|
| \`ToolProvider.getSystemJavaCompiler()\` | API Java chuẩn; diagnostics/file manager linh hoạt; có thể biên dịch in-process | Phụ thuộc compiler implementation trong runtime; mã compiler chạy trong tiến trình host |
| Chạy \`javac\` bằng \`ProcessBuilder\` | Tiến trình riêng, dễ kiểm soát timeout/output; dùng toolchain được chọn | Cần executable và JDK/toolchain phù hợp; phải xử lý process, môi trường, classpath, output |
| Compiler bên thứ ba | Phù hợp runtime hoặc tính năng riêng; có thể cung cấp API khác | Cần kiểm tra mức hỗ trợ Java, API, dependency và bảo trì |

Ví dụ chạy trình biên dịch ngoài qua \`ProcessBuilder\` (mã minh họa, chưa là chương trình đầy đủ):

\`\`\`java
Process process = new ProcessBuilder(
        "/path/to/jdk/bin/javac",
        "--release", "17",
        "-d", "/safe/output",
        "/safe/source/Hello.java"
).redirectErrorStream(true).start();
\`\`\`

Cần đọc stdout/stderr kịp thời để tránh deadlock do buffer đầy, đặt timeout, kiểm tra exit code, hủy process khi cần, và dùng đường dẫn đã kiểm soát. Không xây câu lệnh shell bằng cách nối chuỗi lấy từ người dùng. \`ProcessBuilder\` nhận danh sách argument riêng biệt nên dễ kiểm soát hơn shell interpolation, nhưng vẫn phải kiểm tra source/target path và quyền filesystem.

Bên thứ ba có thể cung cấp \`JavaCompiler\` implementation hoặc API riêng tùy thư viện. Không giả định mọi compiler Java đều xuất hiện từ \`ToolProvider.getSystemJavaCompiler()\`: overload này dùng cơ chế system compiler của môi trường, không phải registry tổng quát cho mọi compiler tùy chọn.

## 9. Mối liên hệ với plugin và biên dịch lúc chạy

Đối với hệ thống runtime extensibility, một quy trình an toàn thường là:

\`\`\`text
Nguồn plugin được cho phép
        |
        v
Kiểm tra định dạng + giới hạn kích thước + quyền
        |
        v
Chọn compiler/toolchain phù hợp
        |
        v
Compile vào vùng staging riêng
        |
        v
Thu thập diagnostics và xác thực output
        |
        v
Kiểm tra hợp đồng API/dependency/module
        |
        v
Chuyển artifact được duyệt sang class loader/layer
        |
        v
Khởi tạo và kích hoạt plugin có kiểm soát
\`\`\`

**Biên dịch không phải ranh giới bảo mật.** JavaCompiler có thể kích hoạt annotation processor hoặc các plugin compiler trong quá trình biên dịch, tùy option và môi trường, và có thể chạy mã trong tiến trình host. Với nguồn không tin cậy, cần kiểm soát processor path; cân nhắc \`-proc:none\` khi không cần annotation processing, và ưu tiên compile trong process/container cô lập với hạn chế tài nguyên/quyền. Các option được hỗ trợ thay đổi theo compiler/toolchain, nên kiểm tra trên phiên bản mục tiêu.

Với bytecode đã compile, việc load và chạy cũng yêu cầu chính sách riêng; class loader/module layer không tự sandbox mã độc. Nếu module API của plugin được chia sẻ, tránh đóng gói lặp để không gây lỗi class identity hoặc liên kết.

## 10. Các lỗi thường gặp

- **“Có \`java.compiler\` nghĩa là có \`javac\`.”** Sai: module chuẩn định nghĩa API, không cam kết có compiler executable.
- **“Chỉ cần \`requires java.compiler\` là compiler luôn hoạt động.”** Sai: implementation cần được cung cấp bởi runtime.
- **“\`jdk.compiler\` là API Java SE bắt buộc trong mọi runtime image.”** Sai: đây là module JDK, có thể bị loại khỏi custom image.
- **“Có module \`jdk.compiler\` là mọi tác vụ compile sẽ thành công.”** Sai: source, options, dependency, quyền ghi hoặc tài nguyên vẫn có thể gây lỗi.
- **“Gọi \`ToolProvider\` sẽ tìm mọi compiler bên thứ ba.”** Sai: nó truy cập system compiler theo cơ chế môi trường hiện tại.
- **“Compile source là an toàn nếu không thực thi class output.”** Sai: annotation processing hoặc compiler plugin có thể chạy code trong lúc compile.
- **“Compile xong thì class mới có thể gọi trực tiếp.”** Sai: còn bước nạp/định nghĩa class và kiểm tra tương thích API.
- **“Có \`javac\` trong máy dev thì container production cũng có.”** Sai: mỗi runtime cần được kiểm tra độc lập.

## 11. Checklist trước khi triển khai runtime compilation

1. Xác minh phiên bản Java/runtime và các module quan sát được.
2. Kiểm tra \`ToolProvider.getSystemJavaCompiler()\` thực tế, hoặc toolchain command đã chọn.
3. Thực hiện một compile smoke test với \`--release\` phù hợp.
4. Đặt source/output trong thư mục staging riêng có giới hạn và cleanup.
5. Thiết lập classpath/module path, annotation processing policy và dependency allowlist.
6. Thu thập diagnostics đầy đủ, mã lỗi và nguyên nhân; không dựa chỉ vào \`Hello.class\` có tồn tại.
7. Với nguồn không tin cậy, tách tiến trình/giới hạn tài nguyên và quyền.
8. Sau compile, xác minh bytecode/API/module và chỉ kích hoạt plugin khi đã qua preflight.
9. Kiểm thử cả môi trường dev, CI, container và runtime image tùy chỉnh.

**Ghi nhớ:** \`java.compiler\` là **hợp đồng Java Compiler API**, \`jdk.compiler\` là **implementation compiler của JDK**, và **compiler thực tế** là công cụ ứng dụng có thể gọi thành công tại runtime. Ba lớp này cần được kiểm tra riêng khi xây dựng tính năng biên dịch plugin lúc chạy.

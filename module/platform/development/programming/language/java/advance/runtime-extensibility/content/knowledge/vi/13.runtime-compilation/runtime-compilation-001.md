# Khi nào nên nhận mã nguồn Java thay vì cài thêm JAR đã biên dịch?

## 1. Câu hỏi thiết kế thực sự là gì?

Trong ứng dụng Java có khả năng mở rộng lúc chạy (runtime extensibility), host muốn bổ sung hành vi mới mà không sửa hoặc biên dịch lại toàn bộ ứng dụng chính. Có hai cách nhận phần mở rộng:

- **Nhận JAR đã biên dịch:** nhà phát triển plugin viết mã Java, biên dịch/kiểm thử/đóng gói từ trước, rồi host nhận artifact chứa bytecode và tài nguyên (ví dụ một provider ServiceLoader).
- **Nhận mã nguồn Java:** host hoặc một dịch vụ build được chỉ định nhận các tệp **.java** hoặc đoạn source có cấu trúc, **biên dịch chúng thành bytecode** phù hợp môi trường, rồi mới nạp và gọi class kết quả.

Dù chọn cách nào, **JVM chạy bytecode, không trực tiếp chạy cú pháp Java source như một ngôn ngữ script thông thường**. “Nhận source” bổ sung một giai đoạn compilation trước class loading; nó không thay thế class loader, API/SPI, kiểm soát phiên bản hay chính sách trust.

Một hiểu lầm phổ biến là “muốn cài plugin lúc chạy thì bắt buộc nhận source”. Điều này **sai**. JAR cũng có thể được phát hiện và nạp khi ứng dụng đang chạy nếu host thiết kế class loader hoặc module layer và vòng đời plugin phù hợp. Ngược lại, một hệ thống có thể **nhận source để review/build trong CI** rồi phát hành JAR, hoàn toàn không cần JavaCompiler trong tiến trình sản xuất.

Vì vậy, cần tách hai quyết định:

1. **Định dạng đầu vào** cần chấp nhận: mã nguồn để biên dịch, hay artifact bytecode đã được build?
2. **Nơi và lúc biên dịch**: trước triển khai (CI/build service), lúc cài plugin, hay mỗi khi quy tắc thay đổi tại runtime?

Nhận mã nguồn là hợp lý khi có **nhu cầu thay đổi/điều chỉnh code thực sự** và có khả năng quản lý cả bước biên dịch. Nếu chỉ cần tải một implementation đã ổn định, JAR thường đơn giản và có ít trách nhiệm vận hành hơn.

## 2. Hai chuỗi xử lý: source và JAR

~~~text
Phương án A: nhận JAR
Nhà phát triển plugin
  └─ viết source → build/test/sign → plugin.jar
                                   |
                                   v
Host: xác minh artifact → nạp JAR → kiểm tra SPI → khởi tạo → gọi
                          (loader hoặc ModuleLayer)

Phương án B: nhận Java source
Người cung cấp mã nguồn
  └─ source .java + dependency/version/compile options
                                   |
                                   v
Host hoặc build service: validate → JavaCompiler/javac → .class
                                    |                 |
                                 diagnostics       kiểm tra output
                                                       |
                                                       v
                      nạp qua loader/layer → kiểm tra SPI → gọi
~~~

Điểm khác biệt nằm ở **đầu vào và trách nhiệm compilation**, không nằm ở việc JVM có thể mở rộng lúc chạy hay không. Cả hai đều phải giải quyết namespace của class, ranh giới API, liên kết dependency, quyền thực thi, vòng đời và thông tin lỗi.

### Ma trận quyết định nhanh

| Tiêu chí | Nhận source rồi biên dịch | Cài JAR có sẵn |
| --- | --- | --- |
| Hành vi được sinh từ cấu hình/quy tắc thay đổi liên tục | Hữu ích nếu Java source là đầu ra cần thiết | Phải có quy trình build lại JAR mỗi lần đổi |
| Plugin là bản phát hành ổn định do đội khác cung cấp | Thường không cần thiết | Phù hợp hơn |
| Chạy nơi không có JDK/compiler | Cần build ở nơi khác | Chạy được với runtime có đủ module/dependency |
| Cần kiểm tra lại source và xây dựng artifact theo API hiện tại | Có lợi nếu có toolchain kiểm soát | Chỉ thích hợp khi có artifact tương thích |
| Yêu cầu khởi động/cài đặt nhanh, ít phụ thuộc build | Bất lợi khi compile lúc cài | Phù hợp hơn |
| Cần quản lý annotation processing, compiler flags, dependencies | Host/build service phải đảm nhiệm | Trách nhiệm chủ yếu nằm ở pipeline build plugin |
| Cần cô lập mã không đáng tin | **Không tự giải quyết an toàn** | **Không tự giải quyết an toàn** |
| Cần thay đổi class đã load | Phải nạp output bằng loader/layer mới | Cũng phải quản lý loader/layer mới |

Không dùng riêng một hàng trong bảng để ra quyết định. Ví dụ, “muốn audit được source” là lý do tốt để **nhận source**, nhưng chưa phải lý do đủ để **compile source trong JVM đang phục vụ người dùng**.

## 3. Trường hợp nên nhận mã nguồn Java

### 3.1. Host phải tạo implementation từ dữ liệu động

Một hệ thống rule engine hoặc generator có thể tạo class Java dựa trên cấu hình nghiệp vụ, schema, DSL đã được biên dịch thành Java, template được kiểm soát hoặc định nghĩa hàm do đội nội bộ cung cấp.

Ví dụ: nền tảng xử lý đơn hàng sinh adapter cho một schema mới; mỗi phiên bản schema dẫn tới một implementation của cùng interface **OrderTransformer**. Nếu yêu cầu phải có **Java class** để gắn vào hệ thống và cập nhật trong runtime, JavaCompiler có thể là một giai đoạn hợp lý.

Điều kiện để chọn hướng này:
- Phải biên dịch thật ra class hoặc module; một bảng cấu hình/interpreter không đáp ứng yêu cầu.
- Thời điểm thay đổi và vòng đời phiên bản đã rõ.
- Toolchain, dependency, mã nguồn tạo ra và kết quả compile có thể kiểm chứng/tái tạo.
- Source chỉ có khả năng truy cập những API của host được công bố trong hợp đồng.

**Nếu quy tắc chỉ là biểu thức đơn giản**, cân nhắc cấu hình, DSL có giới hạn, rule engine hoặc callback đã biên dịch sẵn trước. Việc xây dựng runtime Java compiler chỉ để thay một điều kiện if có thể tạo chi phí và rủi ro không cần thiết.

### 3.2. Cần biên dịch theo đúng phiên bản API và môi trường hiện hành

Đôi khi source của một extension có thể tương thích với một phiên bản API đã thay đổi, nhưng JAR đóng gói sẵn phụ thuộc chữ ký cũ. Nếu sở hữu source và có kiểm thử đầy đủ, build lại theo API hiện hành có thể tạo artifact tương thích.

Ví dụ: host vừa đổi một interface nội bộ, và các provider nội bộ cần được biên dịch lại trước khi kích hoạt. Đây là lý do **nhận source**, nhưng vẫn thường nên thực hiện trong **pipeline build/test** hơn là ở mỗi request sản xuất.

**Không bảo đảm tự tương thích:** recompilation chỉ giải quyết những vấn đề mà source thực sự biên dịch được theo API mới. Nếu ý nghĩa API, yêu cầu null, đồng bộ, data format hay transaction đã đổi, vẫn phải sửa source và kiểm thử hành vi. Compiler thành công không chứng minh hợp đồng runtime còn đúng.

### 3.3. Plugin là bản tùy chỉnh riêng theo tenant hoặc lần triển khai

Một sản phẩm có nhiều khách hàng có thể cần thuật toán tùy chỉnh do nhóm triển khai đáng tin cậy cung cấp. Nhận source cho phép lưu phiên bản rõ ràng, kiểm tra khác biệt, build thành nhiều artifact độc lập và quay lại phiên bản trước.

Khi chọn giải pháp này, mỗi bản cần có **version ID, hash, trạng thái compile/test, API target và quyền kích hoạt**. Không compile lại bất kỳ đoạn source nào ở mỗi request nếu đã có artifact tương ứng. Mô hình đáng cân nhắc là **compile ở bước công bố phiên bản**, sau đó chỉ nạp kết quả đã được phê duyệt.

### 3.4. Mục tiêu là review, kiểm thử hoặc tái lập build

Nhận mã nguồn giúp kiểm tra cách triển khai, chạy static analysis, kiểm toán dependency và build lại bằng toolchain xác định. Tuy nhiên, từ nhu cầu review không suy ra cần compile trong ứng dụng đang chạy. Thường an toàn và dễ vận hành hơn nếu:

1. Nhận source trong một môi trường build.
2. Chạy formatter/linter/test/scan thích hợp.
3. Biên dịch bằng toolchain cố định, tạo artifact versioned.
4. Kiểm tra checksum/chữ ký và triển khai artifact.
5. Host cài JAR/nhận service provider khi cần.

Một phương án thiết kế tốt có thể **nhận source ở cổng phát triển nhưng chỉ nhận JAR ở cổng runtime**.

## 4. Khi nào chỉ nên cài thêm JAR đã biên dịch?

**Ưu tiên JAR đã build** khi plugin được phát hành bởi một đội phát triển hoặc nhà cung cấp, có giao diện SPI ổn định, ít cần sửa trực tiếp theo từng lần chạy và đã có quy trình build, kiểm thử, xác minh artifact.

Các tình huống điển hình:

- Thêm một JDBC driver, implementation SPI, bộ xử lý định dạng, extension adapter đã phát hành.
- Triển khai bản vá hoặc phiên bản plugin đã qua kiểm thử ở staging.
- Runtime được tối giản bằng **jlink**, container nhỏ hoặc môi trường chỉ có module cần chạy, không chứa compiler.
- Cần startup/activation nhanh, kết quả build có thể tái lập và không muốn để compiler flags/dependency resolution trở thành trách nhiệm của host.
- Muốn sử dụng registry, Maven repository hoặc hệ thống phân phối artifact có checksum/chữ ký.

JAR không tự động là “an toàn” hoặc “tương thích”. Bytecode của JAR vẫn có thể đọc file, mở network, sửa dữ liệu hoặc gây lỗi JVM. Host phải kiểm tra provenance, version, loader/module visibility, API contract và policy trước khi kích hoạt.

Một JAR có thể chứa **META-INF/services** để ServiceLoader tìm provider trên classpath, hoặc **module-info.class** với chỉ thị **provides ... with ...** trên module path. Hai cơ chế discovery cần được cấu hình đúng; việc thêm file JAR vào một thư mục không khiến JVM đang chạy tự động tìm đến nó nếu host không có cơ chế reload/scan.

## 5. Những điều kiện bắt buộc trước khi host chấp nhận source

### 5.1. Có compiler thực sự, không chỉ Java runtime

API chuẩn **javax.tools.JavaCompiler** cho phép gọi trình biên dịch từ Java code; implementation thường lấy qua **ToolProvider.getSystemJavaCompiler()** khi đang chạy trên JDK có **jdk.compiler**. Giá trị trả về **có thể là null** nếu runtime image không có system compiler.

**java.compiler** chứa API JavaCompiler; **jdk.compiler** cung cấp compiler implementation trong các JDK tiêu chuẩn. Ứng dụng đóng gói bằng jlink phải kiểm tra các module đi kèm. Trong production, không nên mặc định “có lệnh java” đồng nghĩa “có javac”.

Có thể dùng compiler ở một **dịch vụ build tách biệt** và để runtime chỉ nạp artifact đã xác thực. Đây là phương án thường tốt khi runtime cần nhỏ gọn hoặc có hạn chế an toàn.

### 5.2. Có bộ hợp đồng SPI rõ ràng

Mã nguồn được nhận phải biết implement interface nào, dùng kiểu DTO nào và được phép gọi API nào. Định nghĩa đầu vào/đầu ra, nullability, exception, thread safety, timeout và ownership ở ranh giới.

Trên classpath, nên đặt **API/SPI trong loader cha**, implementation trong loader con. Nếu cùng tên interface nhưng hai loader định nghĩa hai bản khác nhau, class vừa compile vẫn có thể không cast được sang API host. Với JPMS, cần làm rõ **module readability, exports/opens, uses/provides** và ModuleLayer; không thể giả định việc đặt .class vào URLClassLoader sẽ tự bổ sung nó vào một named module đã tồn tại.

### 5.3. Có toàn bộ đầu vào build đúng phiên bản

Compiler cần:
- Source files đúng package và public type, các source liên quan nếu biên dịch nhiều lớp.
- **Classpath hoặc module path** có các dependency cần thiết, đúng phiên bản và thứ tự.
- Target Java version, **--release** hoặc cặp source/target phù hợp.
- Compiler options, encoding, annotation processor policy và output directory.
- Cách thu thập **diagnostics**: mức độ, file, dòng/cột, mã lỗi; không chỉ boolean thành công/thất bại.
- Cơ chế kiểm tra class output và artifact provenance sau compilation.

JavaCompiler **không tự tải dependency Maven**, không tự chạy Gradle/Maven và không tự giải quyết mọi vấn đề của module graph. Với project phức tạp dùng annotation processors/code generation, build tool có thể phù hợp hơn việc gọi compiler một lần với một danh sách .java.

### 5.4. Có quyết định về trust và thời điểm thực thi

Nếu code từ người dùng hoặc đối tác chưa tin cậy, **không compile và chạy trực tiếp trong JVM của host** với quyền của chính tiến trình. Nhận source không đồng nghĩa kiểm tra được ý đồ của nó; sau compilation, code có thể thực thi I/O, gọi network, tạo thread, giữ lock hoặc thay đổi trạng thái.

Cần thiết kế riêng quyền truy cập, xác thực publisher, tài nguyên/timeout và môi trường cách ly. Với nội dung không đáng tin, cân nhắc một DSL có năng lực hạn chế hoặc **quy trình compile và execute trong process/container được cô lập**. Bản thân JavaCompiler, URLClassLoader và việc ký JAR **không tạo sandbox**.

## 6. Ví dụ Java 17 hoàn chỉnh: biên dịch source rồi nạp một Task

Bài thực hành mô phỏng host nhận một implementation dạng Java source. Để có thể chạy độc lập và kiểm tra rõ kết quả, ví dụ nhúng source đáng tin cậy trong **String**. Trong hệ thống thực, đoạn source này có thể được lấy từ bản version đã được review và xác thực.

**Mục tiêu kỹ thuật**:
1. Host giữ một interface **Task** ổn định.
2. JavaCompiler biên dịch mã nguồn **dyn.UpperTask** theo API của host.
3. Host nạp .class trong output directory bằng URLClassLoader con.
4. Object được cast sang **Task** và thực thi.
5. Host đóng file manager/loader và dọn thư mục output tạm.

Đây là ví dụ học tập về compile/load. Nó không phải pipeline có sandbox, tính năng ký code, rate limit hay cache production.

Tạo **src/demo/Host.java**:

~~~java
package demo;

import java.net.URI;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class Host {
    public interface Task {
        String run(String input);
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("A JDK compiler is required");
        }

        String pluginSource = """
                package dyn;
                public final class UpperTask implements demo.Host.Task {
                    public String run(String input) {
                        return input.toUpperCase(java.util.Locale.ROOT);
                    }
                }
                """;

        JavaFileObject unit = new SimpleJavaFileObject(
                URI.create("string:///dyn/UpperTask.java"), JavaFileObject.Kind.SOURCE) {
            @Override
            public CharSequence getCharContent(boolean ignoreEncodingErrors) {
                return pluginSource;
            }
        };

        Path classes = Files.createTempDirectory("runtime-plugin-");
        try {
            DiagnosticCollector<JavaFileObject> diagnostics = new DiagnosticCollector<>();
            try (StandardJavaFileManager manager = compiler.getStandardFileManager(
                    diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
                List<String> options = List.of(
                        "--release", "17",
                        "-proc:none",
                        "-classpath", System.getProperty("java.class.path"),
                        "-d", classes.toString());
                boolean success = Boolean.TRUE.equals(compiler.getTask(
                        null, manager, diagnostics, options, null, List.of(unit)).call());
                if (!success) {
                    diagnostics.getDiagnostics().forEach(System.err::println);
                    throw new IllegalStateException("Plugin compilation failed");
                }
                System.out.println("Compiled: " + success);
            }

            try (URLClassLoader child = new URLClassLoader(
                    new URL[]{classes.toUri().toURL()}, Host.class.getClassLoader())) {
                Class<?> type = child.loadClass("dyn.UpperTask");
                Task task = (Task) type.getDeclaredConstructor().newInstance();
                System.out.println("Result: " + task.run("hello"));
                System.out.println("Child defines provider: " + (type.getClassLoader() == child));
                System.out.println("Host API compatible: " + Task.class.isAssignableFrom(type));
            }
        } finally {
            try (var walk = Files.walk(classes)) {
                for (Path file : walk.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(file);
                }
            }
        }
    }
}
~~~

Giải thích:

- **ToolProvider.getSystemJavaCompiler()** lấy system compiler. Nếu không có, ví dụ từ chối trước khi compile.
- **SimpleJavaFileObject** biểu diễn một Java source file trong bộ nhớ có URI **string:///dyn/UpperTask.java** phù hợp tên class **dyn.UpperTask**; **getCharContent** cấp toàn bộ source.
- **StandardJavaFileManager** quản lý đầu vào/đầu ra chuẩn và được đóng trong try-with-resources. Với **-d**, compiler ghi .class vào một thư mục tạm.
- **--release 17** yêu cầu biên dịch theo ngôn ngữ/API nền tảng Java 17 khi compiler hỗ trợ release đó; không bảo đảm các library ngoài JDK tương thích.
- **-proc:none** tắt annotation processing cho ví dụ để không vô tình chạy processor từ compiler classpath. Nếu hệ thống cần processor thật sự, phải định nghĩa, khóa phiên bản và kiểm soát processor path.
- **-classpath System.getProperty("java.class.path")** đưa class **demo.Host.Task** vào tập class mà compiler nhìn thấy trong ví dụ này. Khi host dùng loader/module khác, cần dựng classpath/module path đúng kiến trúc; không sao chép nguyên cách này mà không kiểm tra.
- **Boolean.TRUE.equals(...call())** giúp phân biệt kết quả compile thành công với giá trị null/false; khi thất bại, mã in diagnostics rồi dừng trước bước class loading.
- URLClassLoader được tạo với **Host.class.getClassLoader()** làm parent: lớp **Task** dùng chung vẫn được parent định nghĩa, còn provider mới chỉ có trong thư mục output con.
- **getDeclaredConstructor().newInstance()** cần constructor không tham số có thể truy cập. Trong ví dụ UpperTask là public class không khai báo constructor nào, nên Java sinh public default constructor.
- try-with-resources đóng loader, và **Files.walk** xóa output tạm theo thứ tự con trước cha. Đóng loader không bảo đảm class được unload ngay nếu vẫn còn reference.

### 6.1. Biên dịch và chạy trên JDK 17 trở lên

Từ thư mục chứa **src/**, tạo thư mục output và biên dịch host:

~~~bash
mkdir -p out
javac --release 17 -d out src/demo/Host.java
java -cp out demo.Host
~~~

Trên Windows PowerShell, thay riêng bước tạo thư mục bằng **New-Item -ItemType Directory -Force out**, còn hai lệnh **javac** và **java** giữ nguyên.

Kết quả chuẩn, với code và classpath của ví dụ:

~~~text
Compiled: true
Result: HELLO
Child defines provider: true
Host API compatible: true
~~~

Kết quả cho thấy **source được biên dịch ở runtime**, provider được định nghĩa bởi **loader con**, và interface Task vẫn có **cùng type identity** với host. Đây là lý do việc phân chia loader quan trọng ngay cả khi bản thân compilation đã thành công.

### 6.2. Source được biên dịch ở đâu và kết quả được giữ ở đâu?

Ví dụ dùng một URI in-memory cho **source** nhưng output vẫn là **file .class** trong thư mục tạm do **-d** chỉ định. Đây là mô hình **in-memory input + disk output**, không phải cả quá trình đều diễn ra trong RAM.

Muốn hoàn toàn in-memory, cần triển khai **JavaFileManager** riêng để giữ bytecode và một ClassLoader có **defineClass** đọc các byte[] đó. Cách này hữu ích khi cần tránh ghi output tạm, nhưng phức tạp hơn, cần quản lý package, dependency, class identity và vòng đời. Không nên chọn chỉ để có chữ “in-memory” nếu thư mục tạm được quản lý tốt đã đáp ứng nhu cầu.

### 6.3. Giới hạn của ví dụ

- Biên dịch **một implementation** và khởi tạo bằng reflection; không tự quản lý toàn bộ multi-file project hay annotation processors.
- Không có validation, authentication hoặc sandbox cho source ngoài hệ thống.
- Không có cache: mỗi lần chạy main đều compile lại.
- Không chạy trong custom ModuleLayer hay triển khai module-info.java cho plugin.
- Không có SLA cho compilation time, giới hạn RAM/CPU, timeout hoặc rollback.
- Không chạy source nhập ngẫu nhiên từ web/khách hàng; source đã được viết sẵn để ví dụ an toàn và xác định.
- Không tự biến source thành JAR: nếu cần phát hành artifact, phải có bước đóng gói và metadata riêng.

## 7. Nhận source rồi compile có giải quyết được lỗi tương thích JAR không?

Có thể giải quyết **một số lỗi biên dịch hoặc bytecode target** khi có đủ source và dependency, nhưng không phải mọi lỗi.

| Triệu chứng khi cài JAR | Source và recompilation giúp gì? | Cần kiểm tra gì nữa? |
| --- | --- | --- |
| **UnsupportedClassVersionError** vì bytecode mới hơn JVM | Có thể compile lại với **--release** được compiler hỗ trợ nếu source không dùng tính năng quá mới | API/library target và source có tương thích phiên bản Java cũ không? |
| **NoSuchMethodError** sau thay thư viện | Có thể compile lại, phát hiện chữ ký cũ ngay lúc build | Tất cả dependency runtime có đúng phiên bản và hành vi không? |
| **ClassNotFoundException** do thiếu dependency | Chỉ compile lại không tạo ra thư viện còn thiếu | Dependency của source, compile path và runtime path |
| **ClassCastException** giữa loader | Source vẫn có thể tạo hai bản API trong hai loader | Type identity của API/SPI và parent delegation |
| **IllegalAccessError** hoặc ràng buộc JPMS | Recompile chỉ có ích nếu thay thiết kế quyền truy cập đúng | module-info.java, requires, exports/opens và layer |
| Kết quả nghiệp vụ sai | Không có gì bảo đảm từ việc compile thành công | Contract tests và integration tests |
| Lỗi khởi tạo hoặc thiếu cấu hình môi trường | Compiler có thể pass nhưng plugin vẫn fail khi chạy | Config, resource, native library, permission và lifecycle |

Nếu một plugin có JAR tương thích sẵn, việc yêu cầu source và compile lại có thể tạo thêm một tổ hợp phiên bản chưa từng được kiểm thử. **Reproducibility** và cách chứng minh artifact đang chạy tương ứng đúng source/flags/dependencies quan trọng hơn cảm giác “build trên máy này chắc tương thích”.

## 8. Classpath, module path và chiến lược nạp sau compile

### 8.1. Classpath plugin

Trong chương trình đơn giản, source compile với **-classpath** để tham chiếu API host. Sau đó URLClassLoader con nạp class output. Parent-first tạo cơ hội chia sẻ một bản SPI, trong khi mỗi plugin có thể có loader và package riêng.

Cần tránh:
- Đưa bản sao SPI vào loader con rồi dùng child-first, khiến cùng interface có hai identity.
- Để host API tham chiếu trực tiếp implementation class chỉ tồn tại trong loader con.
- Giữ static reference đến ClassLoader cũ sau khi nạp phiên bản mới.
- Gộp nhiều JAR/version không tương thích vào một global classpath.

Nếu cài JAR prebuilt, host cũng có thể đưa URL của JAR vào URLClassLoader rồi khám phá implementation qua **ServiceLoader.load(service, loader)**. **JavaCompiler không cần tham gia** chuỗi xử lý này.

### 8.2. Named module và JPMS

Đối với plugin là **explicit named module**, cần biên dịch với các option thích hợp như **--module-path** và **--module-source-path**, khai báo **module-info.java** khi cần, rồi quản lý **ModuleLayer**. Chỉ viết bytecode vào thư mục và đưa URL vào loader không biến module đó thành một module đã resolve theo mong muốn.

SPI qua JPMS thường dùng **uses Service** trong consumer và **provides Service with Provider** trong provider; host nên gọi ServiceLoader theo layer phù hợp. Implementation package có thể được đóng gói, không exports/opens cho host, trong khi provider vẫn được ServiceLoader khởi tạo theo cơ chế của JPMS.

Nếu không có lý do vận hành để tự dựng graph module lúc runtime, hãy biên dịch module trong pipeline build rồi cài artifact theo cấu hình JPMS xác định.

## 9. Chi phí compile ở runtime và cách giảm

**Compiling có chi phí khác loading.** Compiler phải parse/resolve/type-check/generate bytecode; có thể cần nhiều nguồn, annotation processors, module graph và file I/O. Với các rule thay đổi ít nhưng được gọi nhiều, compile ở mỗi request làm tăng latency, CPU, memory và khả năng bị abuse.

Mô hình thực tế:

~~~text
Source version được phê duyệt
       |
       v
Tạo key: source hash + API version + compiler target
       + options + fingerprint dependency + processor version
       |
       v
Cache đã có artifact hợp lệ?
   | có                      | không
   v                         v
Đọc artifact                Compile + kiểm thử + kiểm chứng
   |                         |
   +------------+------------+
                |
                v
        Kích hoạt bản được chọn
                |
                v
       Gọi nhiều lần, không compile lại
~~~

Nên khóa **release target, classpath/module path, compiler version, processor policy, dependency versions và source hash**. Chỉ dùng hash của source sẽ sai khi API hoặc compiler flags thay đổi. Kết quả build cần có định danh bất biến để rollback và chẩn đoán.

Mỗi phiên bản được kích hoạt có thể cần **loader riêng**. Khi thay phiên bản, tách traffic khỏi loader cũ, dừng callback, đóng tài nguyên và giải phóng reference trước khi kỳ vọng class unloading. **URLClassLoader.close() không tự unload class** và không ngắt thread do plugin tạo.

Với nhiều biến thể nhỏ, kiểm tra liệu một interpreter/DSL hoặc các tham số cấu hình truyền cho một implementation đã build sẵn có rẻ hơn việc sinh nhiều class. “Có thể compile” không đồng nghĩa “nên compile”.

## 10. An toàn: kiểm soát cả bước biên dịch lẫn thực thi

Đây là điều kiện quyết định nếu source không đến từ đội phát triển đáng tin cậy:

- **Source Java có quyền năng của Java code**, không phải một file cấu hình thụ động. Khi class được nạp và thực thi, code có thể truy cập những tài nguyên mà tiến trình cho phép.
- **Annotation processor và compiler plugin** là code có thể được chạy trong giai đoạn build. Ví dụ dùng **-proc:none** để tắt processor cho source minh họa; dự án có processor phải khóa, rà soát và cô lập chúng.
- Giới hạn kích thước source, số file, thời gian compile, CPU/memory/disk và số lượng phiên bản lưu trữ. Cần xác thực/quota trước khi compile.
- Không trộn compiler classpath với thư viện nhạy cảm nội bộ một cách vô thức; chỉ cấp các API cần để build. Tuy nhiên, **giấu library khỏi compiler path không phải biện pháp sandbox khi thực thi**.
- Compile và chạy trong **quy trình/process cách ly** nếu phải nhận source từ bên không tin cậy; áp dụng quyền filesystem/network, resource quota và lifecycle phù hợp.
- Kiểm tra provenance, hash, version và logs; không lưu source/diagnostic có secret như văn bản công khai.
- Không coi **SecurityManager** là mô hình sandbox hiện đại mặc định; trên Java 17 cơ chế này đã bị đánh dấu deprecated for removal và có nhiều giới hạn thực tế.

JAR prebuilt cũng cần các biện pháp trust phù hợp. Khác biệt là với source, host còn phải kiểm soát **compiler/build pipeline**. Không nên quảng bá nhận source là “an toàn hơn” chỉ vì có thể đọc được mã.

## 11. Các lỗi phổ biến trong luồng source compilation

| Lỗi | Dấu hiệu | Xử lý đúng |
| --- | --- | --- |
| Chạy trên runtime thiếu compiler | ToolProvider.getSystemJavaCompiler() trả null | Cài JDK phù hợp hoặc chuyển compile sang build service |
| Source dùng cú pháp/API ngoài target | Diagnostics cho biết lỗi release hoặc symbol | Sửa source/target; dùng --release rõ |
| Thiếu classpath/module path | cannot find symbol, package does not exist | Cấu hình dependency chính xác; không tự phỏng đoán từ environment |
| Sai package hoặc binary name | ClassNotFoundException khi nạp output | Tên file, package, URI của JavaFileObject và tên load phải khớp |
| Compile thành công nhưng không cast được | ClassCastException | Chia sẻ đúng SPI qua loader cha hoặc module dùng chung |
| Source compile nhưng runtime lỗi linkage | NoClassDefFoundError/NoSuchMethodError | Kiểm tra dependency runtime và version của artifact |
| Lạm dụng một loader cho nhiều bản cùng tên | Vẫn dùng class đã nạp hoặc LinkageError | Kích hoạt version bằng loader/layer phù hợp |
| Output tạm/loader tích tụ | Disk/memory tăng, tài nguyên không được đóng | Đóng file manager/loader, dọn temp, gỡ tham chiếu/callback |
| Diagnostics lộ secret | Log chứa source hoặc đường dẫn nhạy cảm | Lọc thông tin, gắn request/version ID thay vì log toàn source |
| Chạy compile theo mỗi request | Latency/CPU tăng nhanh | Cache output theo toàn bộ build inputs và compile theo phiên bản |
| Nhận source chưa tin cậy ngay trong host | Code có thể gây side effect ngoài ý muốn | DSL hoặc compile/execute trong process cách ly |

**Phân biệt lỗi:** compile fail không phải là không tìm thấy plugin; class loading fail không phải lỗi ngôn ngữ Java source; extension chạy và ném exception không chứng minh compiler sai. Mỗi giai đoạn nên có trạng thái và diagnostics riêng: RECEIVED → VALIDATED → COMPILED → VERIFIED → ACTIVATED → FAILED/RETIRED.

## 12. Quy trình chọn phương án theo tình huống

~~~text
Có sẵn JAR của đúng plugin và phiên bản hợp đồng?
   |
   +-- Có --> JAR đã kiểm thử/được tin cậy?
   |              |
   |              +-- Có --> Cài JAR qua loader/layer của host
   |              |
   |              +-- Không --> Yêu cầu nguồn/provenance/test phù hợp
   |
   +-- Không --> Có cần tùy biến Java implementation?
                    |
                    +-- Không --> Tìm config/DSL/plugin JAR hiện có
                    |
                    +-- Có --> Source có được tin cậy và định phiên bản?
                                 |
                                 +-- Không --> Không compile và chạy
                                 |            trong JVM host; thiết kế cách ly
                                 |
                                 +-- Có --> Có cần compile ngay trong host?
                                              |
                                              +-- Không --> CI/build service
                                              |            tạo JAR đã xác thực
                                              |
                                              +-- Có --> Kiểm tra JDK compiler,
                                                           API/dependencies,
                                                           quotas/cache,
                                                           test và loader
~~~

### Ba tình huống so sánh

**Tình huống A: cài provider định dạng dữ liệu đã phát hành.** Nhà cung cấp gửi JAR với implementation SPI tương thích, đã test và có checksum. Host chỉ cần khởi tạo plugin loader/ServiceLoader thích hợp. **Chọn JAR**; yêu cầu source compilation ở runtime không đem lại giá trị rõ.

**Tình huống B: khách hàng doanh nghiệp có adapter riêng được đội nội bộ review.** Adapter phải khác theo từng phiên bản API, nhưng cập nhật mỗi tuần. Có thể **nhận source**, chạy build/test trong CI, tạo JAR riêng và phát hành có version. **Không cần compile trong JVM phục vụ request**.

**Tình huống C: hệ thống generator tạo class Java từ một schema vừa được cấu hình tại runtime.** Mỗi schema được duyệt phát sinh một implementation cần nạp ngay, compiler đã được chuẩn bị, và execution nằm trong boundary được thiết kế. Có thể **compile source theo từng phiên bản schema**, cache bytecode và chỉ gọi implementation đã xác thực. Nếu schema do người dùng không tin cậy điều khiển, cần thêm cơ chế giới hạn và cách ly phù hợp trước khi cho phép chạy code.

## 13. Checklist trước khi chấp nhận Java source làm đầu vào extension

1. **Có lý do cần source:** plugin thực sự phải sinh/tùy biến/rebuild từ source, thay vì chỉ cần cài JAR hiện có.
2. **Đã xác định giai đoạn compile:** CI, build service, lúc cài plugin hoặc runtime theo version; không compile lại vô ích trên mỗi request.
3. **Đã xác định compiler:** JDK/module jdk.compiler hay dịch vụ build riêng, release target, options và dependency resolution.
4. **Có API/SPI dùng chung:** phân biệt class loader/module layer và bảo đảm assignability, null/exception contract.
5. **Có diagnostics rõ:** lỗi syntax, compile, load/link, instantiate và runtime được báo thành các giai đoạn khác nhau.
6. **Có kiểm thử và versioning:** source hash, fingerprint dependency/compiler, artifact immutable, kích hoạt/rollback và cache.
7. **Có giới hạn tài nguyên và trust:** input validation, processor policy, quota, filesystem/network isolation nếu source chưa đáng tin.
8. **Có quản lý lifecycle:** close loader/resource, ngừng thread/callback, loại tham chiếu cũ khi thay phiên bản.
9. **Có chiến lược vận hành:** logs, observability, thời gian compilation, số phiên bản đồng thời, bảo mật source và diagnostics.
10. **Đã so sánh với JAR/DSL/config:** giải pháp được chọn phải giải quyết nhu cầu nghiệp vụ bằng chi phí phù hợp.

**Nguyên tắc cốt lõi:** nhận mã nguồn Java khi **cần quyền kiểm soát hoặc tạo implementation trước khi có bytecode**; cài JAR đã biên dịch khi **chỉ cần phân phối và kích hoạt hành vi đã được build**. JavaCompiler mở thêm một bước tạo bytecode tại runtime, nhưng không loại bỏ trách nhiệm tương thích, class loading, kiểm thử, cache và an toàn khi thực thi.

## Tài liệu Java 17 tham khảo

- JavaCompiler: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html
- ToolProvider: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html
- ClassLoader: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- URLClassLoader: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html

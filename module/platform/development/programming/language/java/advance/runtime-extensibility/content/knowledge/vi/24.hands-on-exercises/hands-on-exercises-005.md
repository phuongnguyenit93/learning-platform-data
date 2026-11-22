# Biên dịch quy tắc Java từ bộ nhớ rồi tích hợp qua cùng hợp đồng

Một ứng dụng nghiệp vụ có thể có hai nguồn quy tắc: **quy tắc đóng gói sẵn** trong mã của host/plugin và **quy tắc được tạo hoặc chỉnh sửa lúc hệ thống đang chạy**. Nếu mỗi nguồn sử dụng một kiểu gọi riêng, host sẽ phải duy trì hai đường thực thi, hai định dạng kết quả và hai cơ chế kiểm thử. Thiết kế tốt hơn là quy định **một hợp đồng Java ổn định**, biên dịch các quy tắc động thành class triển khai hợp đồng đó, sau đó đưa cả quy tắc viết sẵn lẫn quy tắc động vào cùng một registry.

Java 17 cung cấp API **javax.tools.JavaCompiler** (JSR 199) để biên dịch mã nguồn được biểu diễn bằng JavaFileObject. Bằng cách kết hợp **SimpleJavaFileObject**, **ForwardingJavaFileManager** và một **ClassLoader riêng**, ta có thể đưa source code vào compiler từ một String, nhận bytecode .class ở dạng byte[] mà không lưu source hoặc class động thành tệp, rồi nạp implementation qua interface dùng chung.

Bài thực hành này đi từ hợp đồng Rule → source trong bộ nhớ → bytecode trong bộ nhớ → class loader → instance Rule → cùng pipeline đánh giá. Phần cuối xử lý lỗi, ranh giới bảo mật, giới hạn tài nguyên, versioning và các điều kiện để biến nguyên mẫu thành một hệ thống có thể vận hành.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Định nghĩa một **SPI/hợp đồng Rule** rõ ràng, không phụ thuộc vào nguồn gốc của implementation.
2. Tạo JavaFileObject cho source dạng String và truyền vào **JavaCompiler.getTask(...)**.
3. Nhận **tất cả class output** qua JavaFileManager và lưu trong Map<String, byte[]>.
4. Dùng loader con để nạp bytecode nhưng **ủy quyền interface Rule và DTO Request cho loader của host**.
5. Kiểm tra một class mới có triển khai đúng Rule và khởi tạo qua constructor công khai.
6. Đưa quy tắc biên dịch động vào cùng danh sách/registry với quy tắc Java viết sẵn.
7. Phân biệt **compile failure**, **class loading/linkage failure**, **instantiation failure** và **business execution failure**.
8. Biết vì sao **khả năng biên dịch Java động không đồng nghĩa an toàn để chạy mã không tin cậy**.

Cả mã host và plugin mẫu sử dụng **Java 17+**, không cần Maven/Gradle hay thư viện bên ngoài. Thí nghiệm chạy trên **classpath**, không dùng module-info.java; khi chuyển sang JPMS phải xét thêm module graph và readability.

## 2. Kiến trúc tổng thể

~~~text
                     HỢP ĐỒNG CHUNG (API)
                 demo.api.Rule + demo.api.Request
                              |
                    +---------+---------+
                    |                   |
             Quy tắc viết sẵn     Source Java từ String
             SmallAmountRule               |
                    |                       v
                    |              SimpleJavaFileObject
                    |                       |
                    |                       v
                    |             javax.tools.JavaCompiler
                    |                       |
                    |                       v
                    |           MemoryJavaFileManager
                    |                       |
                    |               Map<String,byte[]>
                    |                       |
                    |                       v
                    |            MemoryClassLoader
                    |             (parent = API loader)
                    |                       |
                    |                       v
                    |             demo.dynamic.TravelRule
                    |                 implements Rule
                    |                       |
                    +-----------+-----------+
                                |
                                v
                         List<Rule> registry
                                |
                                v
                          Request input
                                |
                                v
                       rule.matches(request)
                                |
                                v
                         boolean decision
~~~

Điều đáng chú ý là **hai implementation khác nhau đi vào cùng một danh sách List<Rule>**. Logic quyết định gọi rule.matches(request) chỉ biết interface Rule. Nó không phải hỏi "rule này đến từ file .class, JAR hay String compile lúc runtime?" và không phải thực thi thêm một kênh eval riêng.

JavaCompiler chỉ sinh bytecode. Nó **không tự động chạy** class, không đăng ký class vào ServiceLoader và không quản lý lifecycle của plugin. Các bước nạp, xác minh contract, khởi tạo, đăng ký và gọi đều do host quyết định.

## 3. Thiết kế hợp đồng trước khi viết compiler

Hợp đồng thử nghiệm gồm hai type ổn định:

- **Request**: record bất biến mang dữ liệu tối thiểu mà mỗi rule được phép quan sát: category và amount.
- **Rule**: interface có id() để quản lý và matches(Request) trả quyết định boolean.

~~~java
package demo.api;

public interface Rule {
    String id();
    boolean matches(Request request);
}
~~~

~~~java
package demo.api;

public record Request(String category, int amount) {}
~~~

Hai đoạn code trên lần lượt là hai file Rule.java và Request.java; không đặt hai public top-level type trong cùng một file. Trong một hệ thống thực, Request thường là DTO được thiết kế kỹ hơn, có validation/nullability, các giá trị enum/domain được phép và phiên bản schema.

**Vì sao phải giữ đúng một bản API?** Ở JVM, danh tính của class không chỉ dựa trên tên package + tên class mà còn dựa trên **defining ClassLoader**. Hai bản demo.api.Rule do hai loader khác nhau định nghĩa **không phải một type**, cho dù bytecode có tên giống nhau. Lúc đó kiểm tra Rule.class.isAssignableFrom(generatedClass) hoặc ép kiểu sang Rule có thể thất bại.

Quy tắc ở đây là: **host tạo và sở hữu Rule/Request; class loader của rule động sử dụng host loader làm parent; không tự compile thêm bản Rule.java bên trong tác vụ động**.

Một hợp đồng tốt còn xác định rõ matches(...) có được phép side effect không, lỗi nào được ném, thời gian thực thi tối đa, thread-safety, lifecycle của Rule instance và cách lựa chọn nhiều rule. Demo dùng boolean để giữ kết quả tất định; production có thể dùng Decision(status, reason, evidence) nhưng nên giữ DTO thuộc API chung.

## 4. Cấu trúc project thực hành

Từ thư mục **rule-lab/**:

~~~text
rule-lab/
├── src/
│   ├── api/demo/api/
│   │   ├── Rule.java
│   │   └── Request.java
│   ├── builtin/demo/builtin/
│   │   └── SmallAmountRule.java
│   └── host/demo/host/
│       └── DynamicRulesDemo.java
└── build/
    └── classes/                  (được tạo khi build)
~~~

Không cần tạo tệp .java cho quy tắc động: mã của nó sẽ là **Java text block** bên trong host. Sau khi chạy, không có file .class nào của demo.dynamic.TravelRule trong build/classes: nó đi qua bộ nhớ.

### 4.1. API chung: Rule.java

Tạo **src/api/demo/api/Rule.java**:

~~~java
package demo.api;

public interface Rule {
    String id();
    boolean matches(Request request);
}
~~~

### 4.2. DTO chung: Request.java

Tạo **src/api/demo/api/Request.java**:

~~~java
package demo.api;

public record Request(String category, int amount) {}
~~~

Record có sẵn từ Java 16. Trong bài này, amount là số nguyên đơn vị quy ước cho lab; sản phẩm tài chính nên dùng đơn vị tiền rõ ràng và kiểu dữ liệu phù hợp (ví dụ BigDecimal hoặc minor units).

### 4.3. Quy tắc viết sẵn: SmallAmountRule.java

Tạo **src/builtin/demo/builtin/SmallAmountRule.java**:

~~~java
package demo.builtin;

import demo.api.Request;
import demo.api.Rule;

public final class SmallAmountRule implements Rule {
    @Override
    public String id() {
        return "small-amount";
    }

    @Override
    public boolean matches(Request request) {
        return request.amount() <= 100;
    }
}
~~~

Đây là implementation Java bình thường, được javac biên dịch trước khi host chạy. Nó không biết JavaCompiler API và không cần ClassLoader tùy chỉnh.

### 4.4. Host biên dịch và nạp rule trong bộ nhớ

Tạo **src/host/demo/host/DynamicRulesDemo.java**:

~~~java
package demo.host;

import demo.api.Request;
import demo.api.Rule;
import demo.builtin.SmallAmountRule;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileManager;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class DynamicRulesDemo {
    // 1. JavaFileObject chứa source nằm trong một String.
    private static final class SourceText extends SimpleJavaFileObject {
        private final String source;

        SourceText(String binaryName, String source) {
            super(URI.create("string:///"
                    + binaryName.replace('.', '/')
                    + JavaFileObject.Kind.SOURCE.extension),
                    JavaFileObject.Kind.SOURCE);
            this.source = source;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return source;
        }
    }

    // 2. JavaFileObject nhận .class bytes qua OutputStream.
    private static final class ClassBytes extends SimpleJavaFileObject {
        private final ByteArrayOutputStream data = new ByteArrayOutputStream();

        ClassBytes(String binaryName) {
            super(URI.create("mem:///classes/"
                    + binaryName.replace('.', '/')
                    + JavaFileObject.Kind.CLASS.extension),
                    JavaFileObject.Kind.CLASS);
        }

        @Override
        public OutputStream openOutputStream() {
            return data;
        }

        byte[] bytes() {
            return data.toByteArray();
        }
    }

    // 3. Redirect mọi class output vào Map thay vì đĩa.
    private static final class MemoryFileManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        private final Map<String, ClassBytes> compiled = new LinkedHashMap<>();

        MemoryFileManager(StandardJavaFileManager standard) {
            super(standard);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location,
                String binaryName,
                JavaFileObject.Kind kind,
                FileObject sibling) throws IOException {

            if (kind != JavaFileObject.Kind.CLASS) {
                throw new IOException("Only CLASS output is supported");
            }
            ClassBytes output = new ClassBytes(binaryName);
            compiled.put(binaryName, output);
            return output;
        }

        Map<String, byte[]> bytecodes() {
            Map<String, byte[]> result = new HashMap<>();
            for (var entry : compiled.entrySet()) {
                result.put(entry.getKey(), entry.getValue().bytes());
            }
            return Map.copyOf(result);
        }
    }

    // 4. Nạp class động; Rule/Request vẫn do loader cha định nghĩa.
    private static final class MemoryClassLoader extends ClassLoader {
        private final Map<String, byte[]> bytecodes;

        MemoryClassLoader(ClassLoader parent, Map<String, byte[]> bytecodes) {
            super(parent);
            this.bytecodes = bytecodes;
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            byte[] bytes = bytecodes.get(name);
            if (bytes == null) {
                throw new ClassNotFoundException(name);
            }
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    // Giữ loader cùng instance để quản lý vòng đời rule động.
    private record LoadedRule(Rule rule, ClassLoader loader) {}

    private static LoadedRule compileAndCreate(
            String binaryName, String source) throws Exception {

        if (source.length() > 10_000) {
            throw new IllegalArgumentException("Source exceeds lab limit");
        }

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Run with JDK 17+, not a runtime without javac");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();
        Map<String, byte[]> compiledBytes;

        // Standard manager dùng để ĐỌC classpath của host.
        // Wrapper của ta thay đường GHI class output thành bộ nhớ.
        try (StandardJavaFileManager standard =
                compiler.getStandardFileManager(
                        diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {

            MemoryFileManager memory = new MemoryFileManager(standard);

            List<String> options = List.of(
                    "--release", "17",
                    "-proc:none",
                    "-classpath", System.getProperty("java.class.path"));

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null,
                    memory,
                    diagnostics,
                    options,
                    null,
                    List.of(new SourceText(binaryName, source)));

            boolean success = Boolean.TRUE.equals(task.call());
            if (!success) {
                for (Diagnostic<? extends JavaFileObject> d
                        : diagnostics.getDiagnostics()) {
                    System.err.println("compile-error line="
                            + d.getLineNumber() + " "
                            + d.getMessage(Locale.ROOT));
                }
                throw new IllegalStateException("Compilation failed");
            }
            compiledBytes = memory.bytecodes();
        }

        MemoryClassLoader loader = new MemoryClassLoader(
                Rule.class.getClassLoader(), compiledBytes);

        Class<?> raw = Class.forName(binaryName, true, loader);
        Class<? extends Rule> implementation = raw.asSubclass(Rule.class);
        Rule rule = implementation.getDeclaredConstructor().newInstance();
        return new LoadedRule(rule, loader);
    }

    public static void main(String[] args) throws Exception {
        String binaryName = "demo.dynamic.TravelRule";

        // 5. Đây là TOÀN BỘ source của implementation động.
        // Không có file TravelRule.java trên đĩa.
        String javaSource = """
                package demo.dynamic;

                import demo.api.Request;
                import demo.api.Rule;

                public final class TravelRule implements Rule {
                    public TravelRule() {}

                    @Override
                    public String id() {
                        return "travel-high";
                    }

                    @Override
                    public boolean matches(Request request) {
                        return "travel".equals(request.category())
                                && request.amount() >= 500;
                    }
                }
                """;

        LoadedRule dynamic = compileAndCreate(binaryName, javaSource);
        Rule builtin = new SmallAmountRule();

        // 6. Cả hai được gọi thông qua CÙNG interface Rule.
        List<Rule> registry = List.of(builtin, dynamic.rule());

        System.out.println("contract="
                + Rule.class.isInstance(dynamic.rule()));
        System.out.println("separate-implementation-loader="
                + (dynamic.loader() != Rule.class.getClassLoader()));

        for (Request request : List.of(
                new Request("travel", 800),
                new Request("office", 60))) {

            System.out.println("request="
                    + request.category() + "/" + request.amount());
            for (Rule rule : registry) {
                System.out.println("  " + rule.id()
                        + "=" + rule.matches(request));
            }
        }
    }
}
~~~

**Rà soát vai trò từng thành phần:**

- SourceText là JavaFileObject có Kind.SOURCE. Hàm getCharContent trả về String đã có trong RAM. URI dạng string:///... chỉ là tên file logic cho compiler, không có nghĩa file được tạo trên đĩa.
- ClassBytes nhận bytecode qua ByteArrayOutputStream. Compiler có thể tạo **nhiều** .class từ một source (nested class, anonymous class...), nên file manager lưu Map theo **binaryName**, không chỉ một byte[] duy nhất.
- MemoryFileManager bọc StandardJavaFileManager: standard vẫn đọc class/module từ môi trường compile; output .class qua getJavaFileForOutput được redirect vào memory. Trong demo, không có annotation processor do -proc:none.
- MemoryClassLoader dùng parent delegation mặc định. Nó tìm class động trong bytecode map khi parent chưa tìm thấy. Parent được chọn là **Rule.class.getClassLoader()**, nhờ đó demo.api.Rule và demo.api.Request có cùng danh tính với host.
- Class.forName(binaryName, true, loader) không chỉ nạp class mà còn **khởi tạo class** nếu cần; static initializer của rule có thể có side effect. Demo chỉ chạy mã **được tin cậy**, không phải môi trường nhận Java tùy ý của người lạ.
- asSubclass(Rule.class) xác minh class động thực sự triển khai hợp đồng chung. Đây không phải một phép đổi kiểu lỏng lẻo bằng tên class.
- getDeclaredConstructor().newInstance() yêu cầu constructor không tham số có thể truy cập theo quyền thông thường; mã nguồn demo khai báo public constructor.
- LoadedRule giữ cả instance và loader để host quản lý lifecycle. Không có ClassLoader.close() chung bảo đảm unload class; cần kết thúc work và giải phóng reference khi thay thế rule version.
- List<Rule> registry không phân biệt rule viết sẵn và rule động; cả hai được gọi qua matches(Request).

**Ranh giới của mẫu:** Đây là mô hình classpath với source và bytecode động trong bộ nhớ. Standard manager vẫn đọc classpath của host từ các class/JAR đã build trên đĩa. Không có ý nghĩa "toàn bộ hoạt động javac không sử dụng filesystem", và mã trên chưa triển khai sandbox, quota tổng output, cache hoặc giới hạn CPU cứng.

## 5. Biên dịch và chạy bài thực hành

Từ thư mục **rule-lab/**, chạy JDK 17+ trong bash:

~~~bash
mkdir -p build/classes

javac --release 17 -encoding UTF-8 -d build/classes \
  src/api/demo/api/Rule.java \
  src/api/demo/api/Request.java \
  src/builtin/demo/builtin/SmallAmountRule.java \
  src/host/demo/host/DynamicRulesDemo.java

java -cp build/classes demo.host.DynamicRulesDemo
~~~

**Stdout kỳ vọng chính xác** khi có JDK compiler và mã giống nguyên bản:

~~~text
contract=true
separate-implementation-loader=true
request=travel/800
  small-amount=false
  travel-high=true
request=office/60
  small-amount=true
  travel-high=false
~~~

Phân tích:

- contract=true chứng tỏ object động là instance của **Rule.class do host giữ**.
- separate-implementation-loader=true xác nhận class implementation được định nghĩa bởi loader khác, trong khi interface chung vẫn được chia sẻ.
- Với travel/800, SmallAmountRule trả false, còn TravelRule do runtime compile trả true.
- Với office/60, SmallAmountRule trả true, TravelRule trả false.
- Không có nhánh nào trong vòng for cần biết provider đến từ compiler hay class đã build. Đây chính là **cùng hợp đồng** trong thực hành.

**Trên Windows:** khi classpath có nhiều entry, dấu phân cách là dấu ; thay vì :. Trong demo chỉ có một entry build/classes, nên lệnh java có thể dùng giống nhau. mkdir -p và dấu backslash xuống dòng là cú pháp bash; sử dụng Git Bash/WSL hoặc chuyển thành lệnh PowerShell phù hợp.

**Điều kiện môi trường:** ToolProvider.getSystemJavaCompiler() yêu cầu runtime có module/compiler của JDK (jdk.compiler). Một runtime image tối giản không có compiler có thể trả null. JDK 17+ chuẩn dùng để build/run ví dụ thường có sẵn API này.

## 6. Vì sao compilation thành công chưa đủ để đưa vào registry?

Có bốn ranh giới khác nhau:

| Ranh giới | Điều đã biết | Điều còn có thể sai |
| --- | --- | --- |
| CompilationTask.call() trả true | Source hợp lệ với compiler options và dependencies hiện tại | Class được nạp sau đó có thể gặp linkage/init error |
| MemoryFileManager có byte[] | Bytecode đã được sinh vào bộ nhớ | Chưa xác minh class name/type, số lượng output và quyền thực thi |
| Class.forName(...) thành công | JVM đã định nghĩa/khởi tạo class được chọn | Constructor có thể thất bại; method có thể gây side effect |
| asSubclass + newInstance thành công | Đã có Rule instance hợp lệ về kiểu | matches(...) vẫn có thể ném RuntimeException, chạy chậm hoặc sai nghiệp vụ |

Host thực tế nên thực hiện **validation trước khi publish**: class name allowlist, interface type, constructor, rule ID không trùng, version/API hash, sanity tests, input/output constraints, khả năng tải dependencies, giới hạn tài nguyên và chính sách logging.

Khi một bước thất bại, đừng thêm bytecode hoặc instance lỗi vào registry đang phục vụ traffic. Nên xây candidate hoàn chỉnh ở khu staging, xác nhận rồi **thay snapshot** registry theo cơ chế đồng bộ. Nếu validation thất bại, giữ nguyên bản đang chạy.

**Một nuance quan trọng:** compiler task thành công với source không có Rule implementation đúng tên vẫn có thể tạo bytecode. Class.forName(binaryName, ...) hoặc asSubclass(...) sau đó mới phát hiện sai phạm. Biên dịch là điều kiện cần, không phải tiêu chí hoàn tất của plugin.

## 7. Các lỗi phải phân loại riêng

### 7.1. Lỗi biên dịch

Ví dụ sửa đoạn source động từ:

~~~java
request.amount() >= 500
~~~

thành:

~~~java
request.unknownAmount() >= 500
~~~

Đây là **đoạn thay thế trong source text block**, không phải chương trình độc lập. Compiler sẽ không tìm thấy method unknownAmount() trên demo.api.Request. CompilationTask.call() trả false; DiagnosticCollector cung cấp Diagnostic.Kind.ERROR cùng line/column/message và source reference.

Host demo in diagnostic lên stderr rồi ném IllegalStateException("Compilation failed"). Không cố nạp class từ Map sau khi compilation thất bại. Đầu ra chi tiết của javac có thể khác giữa những build JDK; bài lab **không gán một stdout cố định** cho trường hợp lỗi này.

Một biến thể khác là sửa dòng public final class TravelRule thành WrongRule nhưng vẫn truyền binaryName="demo.dynamic.TravelRule". Compiler có thể báo lỗi tên public class/URI không khớp, hoặc nếu source hợp lệ cho tên khác thì bước tìm class sẽ thất bại. Để chẩn đoán, log **binaryName được yêu cầu**, tên source logic và danh sách class output; không sửa lỗi bằng cách cho ClassLoader tải bất kỳ class đầu tiên nó thấy.

### 7.2. Lỗi class identity hoặc loader

Nếu source động tự chứa thêm bản demo.api.Rule nhưng host muốn gọi Rule.class đã build trước, JVM có thể gặp xung đột class identity. Với parent-first loader của demo, API do parent cung cấp, nhưng không nên cố đưa những binary name thuộc package host API vào Map để dựa vào thứ tự delegate ngẫu nhiên.

Chẩn đoán:

~~~java
// Đoạn minh họa tích hợp: có sẵn biến dynamic và kiểu Rule.
Class<?> type = dynamic.rule().getClass();
System.out.println(type.getName());
System.out.println(type.getClassLoader());
System.out.println(Rule.class.getClassLoader());
System.out.println(Rule.class.isAssignableFrom(type));
~~~

Trong demo, className là demo.dynamic.TravelRule, class loader khác host API loader, nhưng isAssignableFrom trả true. Nếu false, kiểm tra **hai loader đã định nghĩa SPI nào**, module graph, dependency version và package của implementation. Việc hai class cùng tên không đủ để chúng tương thích.

### 7.3. Lỗi khởi tạo

Class có thể triển khai Rule nhưng thiếu public constructor không tham số, constructor ném IllegalStateException hoặc static initializer làm hỏng trạng thái. Ví dụ nếu source động khai báo constructor chỉ nhận một tham số thì reflection getDeclaredConstructor() có thể ném NoSuchMethodException.

Class.forName(binaryName, true, loader) còn có thể gây ExceptionInInitializerError nếu static initializer ném lỗi. Constructor invocation có thể ném InvocationTargetException (có cause là exception thực sự từ constructor). Phải phân biệt lỗi này với CompilationTask.call() trả false.

**Đừng bắt Throwable rồi coi mọi lỗi là "compile thất bại".** Lỗi linkage (NoClassDefFoundError, VerifyError, IncompatibleClassChangeError...) hoặc runtime initialization cần ghi đúng stage; nếu gặp lỗi JVM nghiêm trọng phải có chính sách fail closed, không tiếp tục tùy tiện.

### 7.4. Lỗi khi chạy quy tắc

Ngay cả khi Rule instance đã được tạo, matches(request) vẫn có thể ném RuntimeException, tạo thread hoặc chặn I/O nếu implementation được phép gọi những API đó. Một host thực tế cần giới hạn tác động của từng rule, xác định có fallback hay không, và báo **RULE_EXECUTION_ERROR** riêng với **COMPILE_ERROR**.

Ví dụ đoạn tích hợp:

~~~java
// Mã minh họa: rule và request đã được xác định.
try {
    boolean matched = rule.matches(request);
    // Đưa matched vào Decision/registry pipeline.
} catch (RuntimeException ex) {
    // Log rule ID/version và cause; chọn fail closed hay degraded mode.
}
~~~

Không âm thầm trả false trong mọi lỗi. false có nghĩa "quy tắc được thực thi và không khớp"; failure có nghĩa "không xác định được kết quả". Việc nhập hai trạng thái này có thể khiến hệ thống thực hiện quyết định nguy hiểm.

## 8. Tích hợp vào cùng registry và ServiceLoader

Ở lab, registry chỉ là List.of(...), nhưng một host plugin thật có thể duy trì một registry chung:

~~~java
// Mã minh họa: host đã có Rule API và đối tượng dynamicRule.
List<Rule> rules = new java.util.ArrayList<>();

// Những provider classpath đã đăng ký trong META-INF/services/demo.api.Rule.
java.util.ServiceLoader.load(Rule.class).forEach(rules::add);

// Bổ sung implementation runtime compile đã được xác minh.
rules.add(dynamicRule);

// Từ đây host chỉ cần duyệt và gọi Rule.
~~~

**Quy tắc động không tự xuất hiện trong ServiceLoader chỉ vì compiler đã sinh class.** ServiceLoader đòi hỏi đăng ký service bằng META-INF/services hoặc module provides theo mô hình deployment. Với rule động được tạo trong bộ nhớ, host có thể **đăng ký trực tiếp instance vào registry** như trên; không cần tạo descriptor giả để bắt ServiceLoader quét một Map bytecode.

Trong kiến trúc thực:

- **Discovery** quyết định tìm candidate từ JAR, module, database, source code hoặc registry bên ngoài.
- **Compilation/loading** biến source thành Rule instance hợp lệ, có metadata về version và loader.
- **Registration** đưa instance đã xác minh vào một danh sách/snapshot dùng chung.
- **Execution** chỉ nhìn thấy Rule/Request và trả kết quả theo contract.
- **Lifecycle** ngừng nhận request mới, đợi task đang chạy, hủy reference/loader khi thay thế version.

Nếu dùng DI container, map of strategies hoặc routing table thay cho ServiceLoader, nguyên tắc không đổi: **một hợp đồng dùng chung và một đường thực thi nhất quán**.

## 9. Không đưa class của host vào output động

Tại compile time, javac cần biết định nghĩa Rule và Request. Tùy chọn:

~~~text
-classpath <giá trị java.class.path của host>
~~~

trong demo giúp compiler tìm các class API đã build ở build/classes. Đây là lựa chọn **cho lab classpath đơn giản**, không phải chính sách nên sao chép nguyên xi vào một dịch vụ nhiều tenant. Nếu classpath host chứa thư viện nội bộ không dành cho rule, compiler có thể tham chiếu các API đó và source động có thể liên kết với chúng.

Trong production, hãy cung cấp một **compile classpath được cho phép rõ ràng**, chỉ gồm API/SPI/DTO và thư viện rule được phê duyệt. Thực thi cần quyền runtime tương ứng và có thể cần cô lập tiến trình. Không cho request điều khiển tùy ý -classpath, --module-path, -processorpath, -d hoặc các compiler options khác.

Cơ chế dùng StandardJavaFileManager đọc dependency từ classpath **không khiến Rule được biên dịch lại**. Trong demo, compile units chỉ có SourceText(TravelRule). Vì vậy output Map chỉ chứa implementation mới và các nested types do chính source đó tạo, không chứa API của host.

Với JPMS named modules, cách thêm -classpath như lab có thể không đủ: cần xem module path, readability, exports và API layer. ModuleLayer/uses/provides là các hợp đồng khác; việc tạo một MemoryClassLoader classpath không tự sinh Module object hay thêm module vào layer. Khi chuyển kiến trúc sang named modules, phải thiết kế module resolution và loader mapping riêng.

## 10. Những giới hạn không nên bỏ qua

Đoạn lab **không phải sandbox**. JavaCompiler có thể cần CPU/heap lớn, và code được biên dịch khi nạp/chạy có toàn bộ khả năng tương ứng với quyền của tiến trình. ClassLoader tách tên class, **không phải ranh giới bảo mật**.

| Rủi ro | Mã lab đã làm | Việc production còn phải làm |
| --- | --- | --- |
| Source khổng lồ | Có kiểm tra String.length() 10.000 UTF-16 code units | Kiểm tra **byte input trước khi đọc hết request**, số file, encoding, tổng bytes |
| Output nhiều class/bytecode | Lưu Map và ByteArrayOutputStream | Chặn **số class và tổng byte ngay trong output stream**, không đợi compile xong |
| Compiler diagnostics quá nhiều | Dùng DiagnosticCollector | Listener/Writer có quota số lượng/ký tự/byte và logging an toàn |
| Annotation processor tự chạy | Đã đặt -proc:none | Khóa processor path/options và dependency allowlist |
| Compiler treo hoặc tốn CPU | Chưa có timeout | Biên dịch trong **process/container có quota CPU/RAM** và hard deadline |
| Code thực thi có side effect | Chỉ chạy source tin cậy trong lab | Chạy mã không tin cậy trong process riêng, giới hạn file/network/OS privileges |
| Nạp nhầm ABI | asSubclass kiểm tra Rule type | API version pinning, binary compatibility tests, classpath/module identity |
| Vòng đời rule cũ | LoadedRule giữ instance và loader | Registry snapshots, dừng task và loại references trước khi unload |
| Trùng tên rule/version | Demo dùng một tên động cố định | Namespace/version scheme, hash artifact, xác thực ownership |
| Tải dependency bất ngờ | Parent trỏ loader của host | Compile/runtime dependency policy, tránh đưa toàn host classpath vào worker |

**Soft timeout không phải hard timeout.** Ví dụ bọc compiler task trong Future.get(timeout) rồi gọi cancel(true) chỉ giới hạn **thời gian caller đợi**; nó không đảm bảo compiler hoặc code rule đã thật sự dừng. Nếu một người dùng không tin cậy gửi source làm compiler tiêu tốn CPU/heap, cần process isolation và cơ chế kill/cleanup thực sự.

**Đừng lấy biên dịch thành công làm tiêu chí an toàn mã nguồn.** Mã Java hợp lệ vẫn có thể gọi System.exit, truy cập file, mở network, tạo threads hoặc gây side effect trong static initializer/constructor/matches. Các bước Class.forName(..., true, loader) và newInstance trong lab **đã bắt đầu thực thi code user**; tách chúng khỏi host là yêu cầu nếu source không tin cậy.

Trong bản production còn cần ký số/hash hoặc nguồn xác thực của rule code, audit trail thay đổi, quyền publish, kiểm tra thành phần phụ thuộc và cơ chế rollback.

## 11. Versioning, caching và hot reload

Một rule động là một **đơn vị phiên bản của implementation**, không phải thay đổi trực tiếp lên interface Rule đang tồn tại. Khi source thay đổi:

1. Tạo candidate version mới với source hash, API version, compiler options và dependency set.
2. Compile thành bytecode mới, lưu output tạm trong bộ nhớ hoặc artifact cache có quota.
3. Tạo class loader mới (không cố dùng lại loader đã định nghĩa cùng binaryName).
4. Khởi tạo Rule mới và kiểm tra contract, ID, health/sanity tests.
5. Chỉ sau khi validation thành công mới publish registry snapshot mới.
6. Dừng nhận request trên version cũ, đợi request đang dùng instance cũ hoàn tất.
7. Gỡ references từ registry, thread, ThreadLocal, callbacks và caches tới Rule/loader cũ để GC có thể thu hồi khi không còn tham chiếu.

**Vì sao phải tạo loader mới?** JVM không định nghĩa lại cùng một class name trong cùng một loader bằng defineClass như một hot-replace bình thường. Nếu gọi defineClass lần nữa cho binaryName đã có, thường sẽ bị LinkageError; tải bytecode khác qua một loader mới là mô hình versioning rõ ràng hơn. Không ép "đổi class ngay trong loader cũ" trong production trừ khi bạn đã chọn cơ chế instrumentation/redefinition chuyên dụng với giới hạn riêng.

**Cache** có thể giảm chi phí compile đối với source lặp lại. Key nên bao gồm **hash source + Java release + compiler options + phiên bản Rule/Request API + dependency fingerprints**. Nếu chỉ cache theo source text, bytecode cũ có thể tương thích sai khi host API thay đổi. Cache cần TTL/size cap và không lưu dữ liệu tenant này cho tenant khác nếu không có chính sách hợp lệ.

Một rule version có thể giữ state trong instance. Không dùng lại instance tùy tiện khi nhiều request chạy đồng thời nếu implementation không thread-safe; lựa chọn singleton, per-request instance hoặc actor/serial executor phải thuộc hợp đồng lifecycle.

## 12. Kiểm thử đúng ba tầng

### 12.1. Contract tests

Với mọi Rule instance (builtin hoặc dynamic), chạy cùng một bộ test:

~~~java
// Mã minh họa: nhận sẵn Rule rule và Request request.
String id = rule.id();
if (id == null || id.isBlank()) {
    throw new IllegalArgumentException("Rule ID must not be blank");
}
boolean decision = rule.matches(request);
// Assert decision theo policy của test case.
~~~

Không kiểm tra bằng nhánh "nếu dynamic thì gọi eval(String)" nữa. Điều này giúp một contract test suite phát hiện behavior mismatch của cả hai nguồn rule.

### 12.2. Compilation tests

- Đầu vào hợp lệ đúng binaryName → CompilationTask.call() thành công, bytecode chứa class được yêu cầu.
- Sai syntax/type → CompilationTask.call() thất bại, diagnostics có vị trí; không publish candidate.
- Package/class name không đúng → kiểm tra source URI, class file names và bước Class.forName.
- Source có nested classes → Map chứa **tất cả** outputs cần cho implementation.
- Source quá hạn mức → từ chối trước khi tạo compilation task.
- Options, compile classpath hoặc JDK version không phù hợp → ghi lỗi đầy đủ và không thay active registry.

### 12.3. Runtime integration tests

- Parent loader thấy đúng Rule/Request; class động có thể cast sang Rule và gọi matches.
- Rule viết sẵn và dynamic nhận **cùng đối tượng Request**, cùng mã xử lý kết quả/lỗi.
- Sai constructor hoặc static initialization → candidate không được publish.
- matches ném exception → ghi **execution failure**, không tự coi đó là matches=false.
- Thay source/recompile với loader mới → version mới được chọn sau publish; work đang dùng version cũ được kết thúc đúng lifecycle.
- Nhiều request đồng thời → registry snapshot nhất quán, không race khi thay loader.
- Một rule không tin cậy hoặc treo → worker/process bị cách ly và hệ thống tiếp tục phục vụ request khác.

**Đầu ra phải là quyết định có thể kiểm chứng**, không chỉ in String từ compiler. Nếu ứng dụng cần quyết định đa trạng thái, nên định nghĩa một Decision type có mã lỗi/trạng thái riêng thay cho boolean; mọi implementation đều trả loại đó.

## 13. Bài tập mở rộng

**Bài A — quy tắc thứ ba:** Viết source String cho class demo.dynamic.OfficeRule triển khai Rule, trả true nếu request.category().equals("office") và amount >= 50. Biên dịch trong cùng quy trình bằng một binaryName khác, đưa nó vào registry rồi in kết quả. Không cần sửa Rule interface.

**Bài B — kiểm tra lỗi syntax:** Đổi amount() thành amountX() ở source TravelRule. Ghi diagnostic line/kind, xác nhận không có dynamic Rule instance nào được publish nếu compilation thất bại. Đừng coi lỗi nạp class sau đó là phương thức xử lý compile failure.

**Bài C — kiểm tra class identity:** Tạo một loader không chia sẻ Rule API từ parent trong một thử nghiệm có kiểm soát và thử ép type. Phân tích vì sao cùng tên demo.api.Rule chưa đủ; khôi phục cấu trúc parent-first cho host.

**Bài D — version mới:** Đổi ngưỡng từ 500 sang 900, tạo loader mới, thay registry sau validation. Kiểm tra Request("travel",800) chuyển từ match sang no-match ở version mới, nhưng instance cũ chỉ bị gỡ sau khi không còn request dùng.

**Bài E — output quota:** Bổ sung vào ClassBytes/MemoryFileManager giới hạn số file và tổng byte write trước khi ghi vào ByteArrayOutputStream. Thử source sinh nested/anonymous classes. Khi vượt hạn mức, không publish bất kỳ output một phần.

**Bài F — tách process:** Chuyển công việc compile/load/execute của source không tin cậy sang một Java worker process riêng nhận source và Request qua giao thức IPC được giới hạn. So sánh timeout chờ Future trong cùng JVM với việc terminate worker process và dọn tài nguyên.

**Bài G — kết hợp plugin JAR:** Tạo một Rule provider đóng gói JAR kèm META-INF/services/demo.api.Rule; dùng ServiceLoader ở host để đưa nó vào registry, rồi thêm TravelRule từ memory compiler. Xác nhận cả ba implementation đều được gọi thông qua một List<Rule> và cùng Request schema.

## 14. Checklist trước khi đưa kỹ thuật vào hệ thống thật

- **API:** Rule/Request là artifact chung, có version và behavior contract rõ ràng; không bị định nghĩa lại trong loader của implementation.
- **Source:** nguồn Java được xác minh owner, class/package name, kích thước và encoding; compile classpath và options do server kiểm soát.
- **Compiler:** kiểm tra ToolProvider.getSystemJavaCompiler(), nhận diagnostics, tắt annotation processing nếu không cho phép; quản lý standard file manager.
- **Output:** lưu đủ mọi class file trong bộ nhớ, giới hạn class count/bytes, không đăng ký output lỗi hoặc một phần.
- **Loading:** parent loader thống nhất SPI, class name đúng, subtype check, constructor validation, phân loại lỗi linkage/instantiation.
- **Registration:** chỉ publish Rule đã pass validation và contract tests; snapshot registry cập nhật atomically theo thiết kế concurrency.
- **Execution:** mọi Rule dùng cùng invocation path và DTO; timeout, exceptions, retry/fallback được định nghĩa trong policy.
- **Security:** không dùng ClassLoader như sandbox; biên dịch và chạy source không tin cậy ngoài host JVM với quota/OS isolation.
- **Lifecycle:** có plugin ID/version, rollback, cleanup callbacks/threads/reference và new loader khi reload.
- **Observability:** ghi compiler duration, output byte count, diagnostics, loader/version IDs, rule invocation latency, compile/load/execution error tách riêng.

Tài liệu tham khảo Java SE 17: [JavaCompiler](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html), [JavaFileManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaFileManager.html), [SimpleJavaFileObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html), [ForwardingJavaFileManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ForwardingJavaFileManager.html), [ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html) và [ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html).

**Kết luận:** thành công của runtime extensibility không nằm ở việc tạo được file .class, mà ở việc **mã động tuân thủ cùng hợp đồng mà host đã ổn định**, được nạp bằng loader tôn trọng class identity và chỉ được đưa vào pipeline sau khi kiểm chứng. Khi đó một quy tắc viết sẵn, một provider từ JAR và một quy tắc biên dịch từ String có thể cùng xử lý Request qua Rule — còn compile/load/lifecycle/security vẫn là các trách nhiệm riêng được quản lý rõ ràng.
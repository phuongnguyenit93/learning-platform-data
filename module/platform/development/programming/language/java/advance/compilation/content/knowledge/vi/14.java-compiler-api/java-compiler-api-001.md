# JavaCompiler và các thành phần của javax.tools

Thay vì luôn gọi tiến trình `javac` từ terminal, Java cung cấp một **Compiler API** công khai cho phép chương trình Java điều khiển việc biên dịch mã nguồn, gom diagnostics, chọn nơi đọc/ghi class file và thậm chí cung cấp source từ chuỗi trong bộ nhớ. API chính nằm trong package `javax.tools` của module chuẩn `java.compiler`; implementation trình biên dịch hệ thống thường nằm trong module JDK `jdk.compiler`.

Đây là bài về **lập trình công cụ với compiler**, không phải việc học cú pháp Java cơ bản. Ta sẽ hiểu các thành phần và vòng đời của một compilation task, chạy ví dụ Java 17+ biên dịch source trên đĩa và trong bộ nhớ, nhận lỗi bằng `DiagnosticCollector`, kiểm soát file manager, xử lý annotation processor, quan sát AST khi cần, và tránh các rủi ro khi biến trình biên dịch thành dịch vụ trực tuyến.

## 1. Khi nào dùng Compiler API thay vì gọi javac?

Dùng `javac` trực tiếp thường đơn giản nhất:

~~~bash
javac --release 17 -d out src/demo/Hello.java
~~~

Nếu ứng dụng của bạn cần **tự gọi compiler** thì `JavaCompiler` hữu ích trong các tình huống:

- IDE/editor phải biên dịch đoạn nguồn mà người dùng vừa nhập, hiển thị lỗi theo vị trí và loại lỗi.
- Công cụ chấm bài hoặc playground tạo source động và cần biết biên dịch thành công hay thất bại.
- Công cụ build riêng muốn chia task, chỉ định classpath, module path, release và thư mục output bằng Java code.
- Bộ sinh mã muốn kiểm tra đầu ra `.java` có hợp lệ hay không.
- Công cụ phân tích tĩnh muốn tiếp cận các cây cú pháp qua API của implementation `javac`.
- Chương trình cần lưu source hoặc kết quả biên dịch vào một backend khác tệp thông thường, thông qua file manager phù hợp.

**Không nên dùng Compiler API chỉ để chạy một build thông thường** nếu Maven hoặc Gradle đã giải quyết đầy đủ dependency, caching, incremental compilation, testing và packaging. Compiler API cung cấp **một lượt biên dịch**, không tự thay thế hệ thống build.

Điểm phân biệt quan trọng: gọi `JavaCompiler` không có nghĩa Java có “mã động được chạy an toàn”. Biên dịch và thực thi là hai hoạt động khác nhau, trong khi annotation processors có thể chạy code ngay **trong quá trình biên dịch**.

## 2. Bản đồ các thành phần cốt lõi

~~~text
                     Java program / IDE / tool
                                │
                 ToolProvider.getSystemJavaCompiler()
                                │
                                ▼
                      JavaCompiler instance
                                │
           ┌────────────────────┼──────────────────────┐
           │                    │                      │
           ▼                    ▼                      ▼
  Compilation Units       JavaFileManager       DiagnosticListener
  (JavaFileObject)             │                      │
           │           đọc source/class/JAR     nhận ERROR/WARNING/NOTE
           │           ghi .class/.java                │
           └────────────────────┼──────────────────────┘
                                │
                    JavaCompiler.getTask(...)
                                │
                                ▼
                     CompilationTask.call()
                                │
                ┌───────────────┴─────────────────┐
                ▼                                 ▼
          Boolean success                Diagnostics + output
                │                                 │
             true/false                  class files / source generated
~~~

| Thành phần | Package/type | Vai trò |
| --- | --- | --- |
| `ToolProvider` | `javax.tools.ToolProvider` | Tìm compiler hoặc documentation tool do platform cung cấp |
| `JavaCompiler` | Interface | Tạo compilation task và standard file manager; cũng có `run(...)` qua `Tool` |
| `JavaCompiler.CompilationTask` | Interface | Đại diện cho **một** công việc biên dịch; cấu hình và gọi `call()` |
| `JavaFileObject` | Interface | Trừu tượng một file source/class/HTML/other; không nhất thiết là file trên đĩa |
| `FileObject` | Interface | Trừu tượng file chung; `JavaFileObject` là trường hợp chuyên biệt |
| `StandardJavaFileManager` | Interface | File manager chuẩn cho file/Path/JAR, tạo compilation units từ đường dẫn |
| `JavaFileManager` | Interface | Cơ chế tìm input và mở output cho compiler |
| `StandardLocation` | Enum | Địa điểm logic như `CLASS_PATH`, `CLASS_OUTPUT`, `SOURCE_PATH`, `SOURCE_OUTPUT`, `MODULE_PATH` |
| `Diagnostic` / `DiagnosticListener` | Interfaces | Biểu diễn/tiếp nhận lỗi, warning, note và vị trí nguồn |
| `DiagnosticCollector` | Class | `DiagnosticListener` có sẵn, gom diagnostics để xử lý về sau |
| `SimpleJavaFileObject` | Class | Lớp cơ sở thuận tiện cho source trong chuỗi hoặc output tùy biến |
| `ForwardingJavaFileManager` | Class | Bao một manager có sẵn và override một số thao tác |
| `Tool` / `OptionChecker` | Interfaces | Giao diện công cụ chung và kiểm tra mức hỗ trợ option |

Trong Java 9+, **API** công khai ở module `java.compiler`; **implementation javac** của JDK thông dụng ở module `jdk.compiler`. Đây là hai module khác nhau. Cả hai đều khác với tiến trình `java` chạy chương trình được biên dịch.

## 3. Tìm compiler: ToolProvider và trường hợp null

Điểm vào thông dụng:

~~~java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException("Runtime khong co system compiler");
}
~~~

Đây là **snippet** đặt trong phương thức, không phải một class độc lập. Trên JDK đầy đủ có `jdk.compiler`, lệnh thường trả về implementation của `javac`. Nhưng `getSystemJavaCompiler()` **có thể trả `null`** nếu môi trường không cung cấp system compiler, ví dụ một custom runtime image bị cắt mất `jdk.compiler`. Đừng kiểm tra sự hiện diện compiler bằng cách nhìn chuỗi `java.version` rồi coi như chắc chắn.

Tự kiểm tra bằng:

~~~bash
java -version
javac -version
java --list-modules
~~~

Lệnh `java --list-modules` trên runtime có module `jdk.compiler` thường cho thấy module đó trong danh sách. Với runtime image tối giản, compiler không nhất thiết đi kèm. `javac -version` chỉ thành công khi lệnh compiler thực sự được cài và tìm thấy theo môi trường PATH.

Phân biệt hai lớp trùng tên:

- `javax.tools.ToolProvider` có `getSystemJavaCompiler()` trả về `JavaCompiler`.
- `java.util.spi.ToolProvider` thuộc service-provider API chung của các công cụ theo tên; đừng vô ý import nhầm rồi gọi method của loại kia.

Nếu tool có file `module-info.java` và chỉ dùng API `javax.tools`, nó cần đọc module `java.compiler`:

~~~java
module my.build.tool {
    requires java.compiler;
}
~~~

Một module chỉ `requires java.compiler` để compile source **không đảm bảo** runtime image luôn chứa provider `jdk.compiler`. Hãy kiểm tra compiler instance lúc chạy và đóng gói runtime image phù hợp. Nếu dùng `com.sun.source.util.JavacTask` để quan sát compiler, module `jdk.compiler` cũng liên quan; xem mục về API AST.

## 4. Tạo task: hiểu đủ sáu tham số getTask

Khai báo API ở mức rút gọn:

~~~java
JavaCompiler.CompilationTask getTask(
    java.io.Writer out,
    JavaFileManager fileManager,
    DiagnosticListener<? super JavaFileObject> diagnosticListener,
    Iterable<String> options,
    Iterable<String> classes,
    Iterable<? extends JavaFileObject> compilationUnits
);
~~~

Đây là **signature minh họa từ JavaCompiler**, không phải phương thức bạn cần tự định nghĩa.

| Tham số | Ý nghĩa |
| --- | --- |
| `out` | Nơi ghi những thông điệp của công cụ không được đi qua listener; `null` dùng đích mặc định |
| `fileManager` | Quản lý việc đọc file, JAR và ghi output; `null` để compiler chọn file manager chuẩn |
| `diagnosticListener` | Nhận diagnostics có cấu trúc; nếu `null` công cụ báo theo cách mặc định |
| `options` | Dãy các token option như `"--release", "17", "-d", "out"`; `null` nghĩa không truyền thêm option |
| `classes` | Các tên class cho xử lý annotation theo quy ước công cụ; **không phải danh sách tên source thông thường** |
| `compilationUnits` | Các `JavaFileObject` biểu diễn source `.java` thực sự cần biên dịch |

`CompilationTask task = compiler.getTask(...);` mới **tạo công việc**, chưa biên dịch. Gọi `task.call()` để chạy việc biên dịch và nhận `Boolean` báo thành công hoặc thất bại.

Ví dụ dùng option đúng:

~~~java
List<String> options = List.of("--release", "17", "-proc:none");
JavaCompiler.CompilationTask task =
        compiler.getTask(null, fileManager, diagnostics, options, null, units);
boolean success = task.call();
~~~

Cần khai báo `compiler`, `fileManager`, `diagnostics` và `units` trong ngữ cảnh cụ thể như ví dụ hoàn chỉnh sau. Với `getTask`, đường dẫn source **được truyền trong `compilationUnits`**, không phải viết một string file name vào options như khi sao chép nguyên xi lệnh shell.

Một `CompilationTask` **chỉ dùng một lần**. Không gọi `call()` hai lần trên cùng task để biên dịch lại. Nếu cần biên dịch nhiều lượt, tạo task mới; có thể tái sử dụng standard file manager **theo tuần tự** để tận dụng cache JAR nếu phù hợp.

## 5. Ví dụ hoàn chỉnh: biên dịch tệp .java trên đĩa

Tạo project nhỏ:

~~~text
compiler-api-demo/
├── DiskCompileDemo.java
├── src/
│   └── demo/
│       └── Hello.java
└── out/                      # tạo khi chạy DiskCompileDemo
~~~

**`src/demo/Hello.java`:**

~~~java
package demo;

public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello from compiled code");
    }
}
~~~

**`DiskCompileDemo.java`:**

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
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public class DiskCompileDemo {
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Need a JDK with jdk.compiler");
        }

        Path output = Path.of("out");
        Files.createDirectories(output);

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
                     compiler.getStandardFileManager(
                             diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {

            manager.setLocationFromPaths(
                    StandardLocation.CLASS_OUTPUT, List.of(output));

            Iterable<? extends JavaFileObject> units =
                    manager.getJavaFileObjectsFromPaths(
                            List.of(Path.of("src/demo/Hello.java")));

            List<String> options = List.of(
                    "--release", "17",
                    "-proc:none"
            );

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, manager, diagnostics, options, null, units);

            boolean success = task.call();
            System.out.println("compiled=" + success);

            for (Diagnostic<? extends JavaFileObject> diagnostic
                    : diagnostics.getDiagnostics()) {
                System.err.println(
                        diagnostic.getKind() + ": "
                                + diagnostic.getMessage(Locale.ROOT));
            }
        }
    }
}
~~~

Đứng tại thư mục `compiler-api-demo`, chạy:

~~~bash
javac --release 17 DiskCompileDemo.java
java DiskCompileDemo
java -cp out demo.Hello
~~~

Với JDK 17+ có system compiler, source hợp lệ, output các lệnh chạy là:

~~~text
compiled=true
Hello from compiled code
~~~

Các dòng trên là **stdout từ hai lệnh `java` ghép theo thứ tự**; lệnh `javac DiskCompileDemo.java` thông thường không có stdout khi thành công. Nếu toolchain có diagnostics warning, vòng lặp có thể in thêm trên **stderr**; ví dụ đơn giản không chủ ý sinh warning.

Điều thực sự xảy ra:

1. `ToolProvider` lấy compiler hiện có.
2. `DiagnosticCollector` giữ các thông báo lỗi/cảnh báo có cấu trúc.
3. `StandardJavaFileManager` nhận đường dẫn nguồn và class output.
4. `getTask` nhận options `--release 17` và `-proc:none`, cùng JavaFileObject cho `Hello.java`.
5. `task.call()` biên dịch source; compiler ghi `out/demo/Hello.class`.
6. Lệnh `java -cp out demo.Hello` **chạy bytecode ở bước khác**, không phải do `task.call()` tự gọi main.

`-proc:none` được dùng trong demo để làm hành vi xác định hơn, không để processor bên ngoài vô tình chạy. Trong build thật cần annotation processors, hãy cấu hình chúng chủ động thay vì vô hiệu hóa.

## 6. StandardJavaFileManager: nhiều hơn một danh sách file

`StandardJavaFileManager` hỗ trợ đọc `Path`/`File`, JAR, classpath, source path và ghi output. Nó là lựa chọn mặc định khi làm việc với cây source/JAR thông thường. Một số thao tác quan trọng:

~~~java
manager.getJavaFileObjectsFromPaths(List.of(Path.of("src/demo/Hello.java")));

manager.setLocationFromPaths(
        StandardLocation.CLASS_OUTPUT, List.of(Path.of("out")));

manager.setLocationFromPaths(
        StandardLocation.CLASS_PATH, List.of(Path.of("libs/util.jar")));
~~~

Ba câu là **snippet**, giả sử `manager` đã được tạo và những đường dẫn có thực. `CLASS_OUTPUT` chỉ nơi ghi `.class`, còn `CLASS_PATH` chỉ nơi tìm các class hoặc JAR dependency. Không nên nhầm `SOURCE_OUTPUT` với `CLASS_OUTPUT`: `SOURCE_OUTPUT` dành cho các file source do annotation processor sinh trong trường hợp có `-s`/cấu hình tương đương.

Một số location thường gặp:

| Location | Sử dụng điển hình |
| --- | --- |
| `CLASS_PATH` | Thư viện ngoài được dùng để phân giải kiểu |
| `SOURCE_PATH` | Tìm Java sources khi cần |
| `CLASS_OUTPUT` | Đích của `.class` |
| `SOURCE_OUTPUT` | Đích của `.java` được codegen sinh thêm |
| `MODULE_PATH` | Tìm các named module dependencies |
| `ANNOTATION_PROCESSOR_PATH` | Tìm và nạp processor/dependencies trong model classpath |

Bạn có thể chọn **một trong hai cách**: cấu hình location bằng file manager, hoặc truyền các option tương ứng như `-classpath`, `--module-path`, `-d`, `-s`. Tránh cấu hình trùng và mâu thuẫn giữa manager và options; phải biết cấu hình nào có hiệu lực trong implementation thực tế.

`StandardJavaFileManager` implement `Closeable`. Dùng `try-with-resources` để giải phóng file handles và tài nguyên liên quan. Standard file manager có thể được dùng cho **nhiều sequential compilation tasks**, nhưng không nên mặc nhiên dùng đồng thời một manager cho nhiều task trên nhiều thread; thiết kế đồng bộ và thread safety phải được đánh giá riêng.

**Mã hóa source:** tham số charset ở `getStandardFileManager(listener, locale, charset)` giúp chỉ rõ cách file manager đọc file. Trong ví dụ dùng `StandardCharsets.UTF_8`. Điều này khác với encoding nội dung output bytecode: class file là định dạng nhị phân, không phải tệp UTF-8.

## 7. DiagnosticCollector: nhận lỗi lập trình được

Khi code không hợp lệ, `JavaCompiler` có thể phát diagnostics với những thuộc tính như:

- `getKind()`: `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE`, `OTHER`.
- `getSource()`: file gắn với lỗi, **có thể `null`** khi lỗi là option hoặc môi trường.
- `getLineNumber()` và `getColumnNumber()`: vị trí dòng/cột, nếu có.
- `getStartPosition()`, `getEndPosition()`, `getPosition()`: offset vị trí; nếu không có dùng giá trị `Diagnostic.NOPOS`.
- `getCode()`: mã diagnostic phụ thuộc compiler implementation, có thể hữu ích cho tooling.
- `getMessage(Locale)`: thông báo đã được định dạng theo locale, không phải một mã lỗi bất biến.

Lưu ý: `DiagnosticCollector.getDiagnostics()` trả danh sách diagnostics do collector nhận, nhưng **không cam kết** mọi thông tin của compiler đều có một đối tượng `Diagnostic`: một số thông báo không phù hợp diagnostic model có thể xuất qua writer/đích mặc định. Không nên parse câu chữ `getMessage()` làm API mã lỗi ổn định.

### Ví dụ chạy được: lỗi compile-time từ source trong chuỗi

Tệp **`DiagnosticsDemo.java`**:

~~~java
import java.net.URI;
import java.util.List;
import java.util.Locale;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class DiagnosticsDemo {
    static final class StringSource extends SimpleJavaFileObject {
        private final String code;

        StringSource(String className, String code) {
            super(URI.create("string:///" + className + ".java"), Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Need jdk.compiler");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        String source = "public class Bad { int n = \"oops\"; }";

        try (StandardJavaFileManager manager =
                     compiler.getStandardFileManager(
                             diagnostics, Locale.ROOT, null)) {

            JavaFileObject input = new StringSource("Bad", source);

            boolean success = compiler.getTask(
                    null, manager, diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null, List.of(input)).call();

            boolean hasError = diagnostics.getDiagnostics().stream()
                    .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR);

            System.out.println("compiled=" + success);
            System.out.println("hasError=" + hasError);
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 DiagnosticsDemo.java
java DiagnosticsDemo
~~~

Stdout:

~~~text
compiled=false
hasError=true
~~~

Vì `int n = "oops";` là **sai kiểu**; cú pháp Java vẫn hợp lệ nhưng attribution/type checking từ chối. Demo **không in nguyên câu diagnostic** để tránh phụ thuộc cách diễn đạt theo JDK/locale. Muốn hiển thị cho người dùng, có thể duyệt `diagnostics.getDiagnostics()`, in `getKind()`, filename, dòng/cột và message với null checks.

Chú ý `StringSource` cho một file source trong **bộ nhớ**; compiler không cần file `Bad.java` trên đĩa. Nhưng nếu biên dịch source hợp lệ trong ví dụ này, standard file manager có thể sinh class file ra đĩa theo cấu hình mặc định; **source in-memory chưa có nghĩa output in-memory**.

## 8. JavaFileObject và SimpleJavaFileObject: source không nhất thiết ở đĩa

`JavaFileObject` biểu diễn một compilation unit hoặc class file trong mô hình của compiler, hỗ trợ các thao tác như `getCharContent(boolean)` hoặc `openInputStream()` phù hợp `Kind`. Những giá trị `JavaFileObject.Kind` quan trọng gồm:

| Kind | Ví dụ |
| --- | --- |
| `SOURCE` | Nội dung Java source từ file hoặc chuỗi |
| `CLASS` | Kết quả class file / bytecode |
| `HTML` | Tệp HTML ở môi trường tool có hỗ trợ |
| `OTHER` | Resource không thuộc các loại trên |

`SimpleJavaFileObject` là lớp cơ sở để implement một số method mà nguồn dữ liệu của bạn thật sự hỗ trợ. Source từ String có thể override:

~~~java
@Override
public CharSequence getCharContent(boolean ignoreEncodingErrors) {
    return sourceCode;
}
~~~

Trong ví dụ này, `sourceCode` là biến field kiểu `String`. Vì compiler đọc ký tự trực tiếp, flag `ignoreEncodingErrors` không có vai trò decoding byte từ file nguồn như ở file manager thông thường.

URI nội bộ thường có dạng:

~~~text
string:///demo/Hello.java
mem:///demo/Hello.class
~~~

URI cần hợp lệ và nên phản ánh package/class name cùng Kind đúng; nó **không** buộc phải trỏ đến tệp thực trên ổ đĩa. Nếu một class public có tên `Hello`, hãy bảo đảm tên compilation unit tương ứng, nếu không compiler có thể báo tên public class không khớp tên file.

Không biến mọi file thành một `SimpleJavaFileObject` duy nhất rồi giả định compiler tự xử lý dependency: file manager vẫn chịu trách nhiệm tìm các class/source khác trên classpath/module path, và compilation units chỉ mô tả phần input đưa vào task.

## 9. Biên dịch hoàn toàn trong bộ nhớ: custom JavaFileManager

Để source **và bytecode** cùng nằm trong bộ nhớ, cần không chỉ `SimpleJavaFileObject` làm source, mà còn **chặn nơi compiler ghi class output**. `ForwardingJavaFileManager` giúp bọc standard manager, chỉ override thao tác đích cần thiết.

Tệp **`MemoryCompileDemo.java`** đầy đủ:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.OutputStream;
import java.net.URI;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileManager;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class MemoryCompileDemo {
    static final class Source extends SimpleJavaFileObject {
        private final String code;

        Source(String className, String code) {
            super(URI.create("string:///" + className.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    static final class MemoryManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        final Map<String, ByteArrayOutputStream> compiled = new HashMap<>();

        MemoryManager(StandardJavaFileManager standard) {
            super(standard);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location,
                String className,
                JavaFileObject.Kind kind,
                FileObject sibling) {

            if (kind != JavaFileObject.Kind.CLASS) {
                throw new IllegalArgumentException("Expected class output");
            }

            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            compiled.put(className, bytes);

            URI uri = URI.create("mem:///" + className.replace('.', '/')
                    + kind.extension);

            return new SimpleJavaFileObject(uri, kind) {
                @Override
                public OutputStream openOutputStream() {
                    return bytes;
                }
            };
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Need jdk.compiler");
        }

        String code = """
                package sample;
                public class Answer {
                    public static int value() {
                        return 42;
                    }
                }
                """;

        try (StandardJavaFileManager standard =
                     compiler.getStandardFileManager(null, null, null)) {

            MemoryManager manager = new MemoryManager(standard);
            JavaFileObject source = new Source("sample.Answer", code);

            boolean success = compiler.getTask(
                    null, manager, null,
                    List.of("--release", "17", "-proc:none"),
                    null, List.of(source)).call();

            System.out.println("compiled=" + success);
            System.out.println("classFound="
                    + manager.compiled.containsKey("sample.Answer"));
            System.out.println("bytecodeNonEmpty="
                    + (manager.compiled.containsKey("sample.Answer")
                       && manager.compiled.get("sample.Answer").size() > 0));
        }
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac --release 17 MemoryCompileDemo.java
java MemoryCompileDemo
~~~

Stdout:

~~~text
compiled=true
classFound=true
bytecodeNonEmpty=true
~~~

Giải thích:

- `Source` trình bày `sample.Answer` như source Java qua URI và `getCharContent()`.
- `MemoryManager` giữ lại output class theo tên; `getJavaFileForOutput(...)` trả `JavaFileObject` mà compiler có thể gọi `openOutputStream()` để ghi byte.
- `MemoryManager` kế thừa đa số thao tác từ `StandardJavaFileManager`, vì vậy platform classes/dependencies vẫn được đọc bằng cơ chế có sẵn.
- Biên dịch source nội bộ không cần tạo `sample/Answer.java` trên ổ đĩa. Trong demo không cần `-d` vì class output được custom manager nắm.
- Map `compiled` chứa các byte arrays sau `call()`; class file **chưa tự được nạp vào JVM**.

**Giới hạn:** đây là bản demo cho class output. Một compiler pipeline có thể sinh thêm source/resource do annotation processing, nên nếu muốn “mọi output đều in-memory”, cần xử lý các location và loại file output cần thiết (source, class, resource), không chỉ `Kind.CLASS`. Demo có `-proc:none` để tránh nhánh annotation processing. Đừng dùng một global map không giới hạn cho server nhận input tùy ý; source và output lớn có thể gây hết bộ nhớ.

Để **thực thi** class từ mảng byte, cần một `ClassLoader` thích hợp (ví dụ custom loader dùng `defineClass`) và chính sách isolation. Việc chỉ có bytes trong `compiled` chưa gọi `Answer.value()`. **Custom ClassLoader không phải sandbox bảo mật**; không chạy mã người dùng không đáng tin chỉ vì đã đổi file manager.

## 10. DiagnosticListener tùy biến và cách xử lý vị trí lỗi

`DiagnosticCollector` hợp khi muốn lấy toàn bộ diagnostics sau `task.call()`. Nếu cần streaming diagnostics theo từng lỗi, implement `DiagnosticListener<JavaFileObject>`:

~~~java
DiagnosticListener<JavaFileObject> listener = diagnostic -> {
    String file = diagnostic.getSource() == null
            ? "<no source>"
            : diagnostic.getSource().getName();

    System.err.println(
            diagnostic.getKind() + " " + file
                    + ":" + diagnostic.getLineNumber()
                    + ":" + diagnostic.getColumnNumber()
                    + " " + diagnostic.getMessage(Locale.ROOT));
};
~~~

Đây là **snippet**, cần import `javax.tools.DiagnosticListener` và `java.util.Locale` và đưa `listener` vào tham số thứ ba của `getTask(...)`.

Các giá trị vị trí có thể không có; số `-1` tương ứng `Diagnostic.NOPOS` trong trường hợp đó. Nếu xây IDE, đừng dùng vị trí `-1` làm offset trong source buffer; cần kiểm tra giới hạn. `getSource()` cũng có thể `null` đối với các chẩn đoán option/configuration.

**Tách severity và policy:** `Kind.ERROR` thường làm compilation không thành công; `WARNING` không nhất thiết. Một công cụ có thể đặt `-Werror` để xem warning là lỗi trong chính sách build. Đừng tự đánh dấu `success=true` chỉ vì collection không có `ERROR` khi chưa kiểm tra kết quả `task.call()`.

**Cẩn trọng với message:** locale, version JDK và compiler implementation có thể đổi nội dung. Giao diện người dùng nên hiển thị message nhưng tránh logic phân loại dựa vào câu tiếng Anh cố định. Khi cần kiểm thử, kiểm tra kind, vị trí, code khi có hỗ trợ và kết quả compile.

## 11. run(...) của Tool so với getTask(...)

`JavaCompiler` kế thừa `Tool`, có method `run(InputStream in, OutputStream out, OutputStream err, String... arguments)`. Nó gần phong cách gọi lệnh `javac`: đưa các đối số như khi dùng công cụ và nhận **exit code kiểu `int`**.

Ví dụ **snippet** khi file nguồn và output directory có sẵn:

~~~java
int exit = compiler.run(
        null,
        System.out,
        System.err,
        "--release", "17",
        "-d", "out",
        "src/demo/Hello.java"
);
System.out.println("exit=" + exit);
~~~

Với source hợp lệ, thông thường `exit=0`. Nhưng `run(...)` không cung cấp cùng mức tùy biến `JavaFileObject`, `JavaFileManager`, `DiagnosticCollector` như `getTask(...)`. Nếu công cụ cần lỗi có cấu trúc, source trong memory hoặc class output custom, nên chọn `getTask`.

| Tiêu chí | `compiler.run(...)` | `compiler.getTask(...).call()` |
| --- | --- | --- |
| Dạng gọi | Gần CLI, nhận các argument string | Thành phần API có file objects, manager và listener |
| Kết quả | `int` exit code | `Boolean` success/failure |
| Diagnostics | Chủ yếu qua output/error streams | Có `DiagnosticListener`/`DiagnosticCollector` |
| Source trong memory | Không phải cơ chế chính | Dùng custom `JavaFileObject` |
| Output trong memory | Không phải cơ chế chính | Dùng custom `JavaFileManager` |
| Control annotation processor | Qua arguments | Qua options và `CompilationTask.setProcessors(...)` |
| Lặp nhiều lần | Gọi lại công cụ | Tạo task mới mỗi lần, có thể tái dùng manager tuần tự |

Với `run(...)`, không nên bỏ qua việc bảo vệ đường dẫn nếu arguments đến từ input người dùng: các option có thể điều khiển classpath, output, processor path hoặc filesystem access.

## 12. Annotation processing qua Compiler API

`CompilationTask` hỗ trợ `setProcessors(Iterable<? extends Processor> processors)` để cấu hình **instances processor**, thay cho cơ chế discovery thông thường của javac khi cần kiểm soát trực tiếp. `Processor` nằm ở `javax.annotation.processing`, thuộc module `java.compiler`.

Ví dụ **snippet minh họa**, giả sử class `MyProcessor` implement `Processor` và task chưa chạy:

~~~java
JavaCompiler.CompilationTask task =
        compiler.getTask(null, manager, diagnostics, options, null, units);
task.setProcessors(List.of(new MyProcessor()));
boolean success = task.call();
~~~

Processor phải phù hợp source language và annotation; không giả định chỉ setProcessor là đủ để source có annotation được khai báo đúng. Với processor được tìm bằng service/provider, có thể chọn bằng compiler options `-processor`, `-processorpath` hoặc `--processor-module-path` theo kiểu artifact.

Khi processor tạo source qua `Filer`:

- Nguồn mới có thể tham gia các round processing tiếp theo.
- `StandardLocation.SOURCE_OUTPUT`/option `-s` quyết định nơi ghi source tùy file manager.
- Class được biên dịch vào `CLASS_OUTPUT`/`-d` nếu chế độ compile bình thường.
- `-proc:only` chỉ thực hiện xử lý annotation, không tiếp tục biên dịch bytecode thông thường.
- `-proc:none` tắt processing — hữu ích cho compiler playground không muốn vô tình chạy processor.

**Bảo mật:** annotation processor là mã Java có thể chạy trong tiến trình compiler, có quyền đọc/ghi file hoặc thực hiện side effects theo môi trường. Không nên đưa JAR processor từ nguồn không đáng tin vào compiler server. Từ JDK 23, cơ chế kích hoạt implicit annotation processing thay đổi theo hướng cần cấu hình tường minh hơn; tool phải chọn processor chủ động thay vì tin rằng JAR nào trên classpath cũng tự chạy.

## 13. Module, classpath và target release trong API

Các options truyền cho `getTask` có mục đích tương tự options của `javac`:

~~~java
List<String> options = List.of(
        "--release", "17",
        "--class-path", "libs/dependency.jar",
        "-d", "out",
        "-proc:none"
);
~~~

Đây là **snippet** yêu cầu paths tương ứng đã tồn tại. Cũng có thể cấu hình `StandardJavaFileManager` qua `StandardLocation.CLASS_PATH` và `CLASS_OUTPUT`. Khi dùng named modules, các option như `--module-path`, `--module-source-path` và output phù hợp phải được đặt theo cấu trúc dự án. Nếu app nằm trong named module, module chứa API `javax.tools` cần `requires java.compiler`; nếu tool đọc AST ở `com.sun.source.*`, implementation/API mở rộng ở `jdk.compiler` có thể cần khai thêm trong descriptor.

**Compiler runtime khác target release**:

- Chạy tool bằng JDK 21 với `--release 17` nghĩa là **compiler implementation chạy trong Java 21**, nhưng source/output tuân mức Java 17 theo khả năng hỗ trợ của javac.
- Annotation processor cũng chạy ở môi trường compiler JDK; một processor yêu cầu JDK 21 sẽ không chạy được khi process ở JDK 17, bất kể target source là Java 8 hay 17.
- `--release 17` kiểm soát Java language, class-file version và Java platform APIs; nó **không tự kéo dependency JAR bên ngoài về Java 17**.
- `ToolProvider.getSystemJavaCompiler()` không phải cross-compiler tùy ý: danh sách release được hỗ trợ phụ thuộc JDK implementation thực tế.

Để xác nhận release target với output disk, dùng `javap -verbose` kiểm tra class-file major. Với Java 17, major version là **61**. Nhưng một class file major 61 chưa chứng minh cả chương trình tương thích runtime Java 17 nếu dependency yêu cầu class version cao hơn hoặc runtime API/module khác.

## 14. Quan sát compiler qua JavacTask khi cần AST

`javax.tools.JavaCompiler` là API portable cho compilation services. Nếu dùng **system javac** trong JDK, đối tượng task được trả về thường có thể được xem như `com.sun.source.util.JavacTask`, thuộc API công khai phục vụ công cụ của module `jdk.compiler`.

Ví dụ **snippet cho implementation javac**, không đảm bảo áp dụng với mọi custom compiler provider:

~~~java
JavaCompiler.CompilationTask task =
        compiler.getTask(null, manager, diagnostics, options, null, units);

if (task instanceof com.sun.source.util.JavacTask javacTask) {
    javacTask.setTaskListener(new com.sun.source.util.TaskListener() {
        @Override
        public void started(com.sun.source.util.TaskEvent event) {
            System.out.println("START " + event.getKind());
        }

        @Override
        public void finished(com.sun.source.util.TaskEvent event) {
            System.out.println("END " + event.getKind());
        }
    });
}

boolean success = task.call();
~~~

`TaskEvent.Kind` bao gồm các event cấp cao như `PARSE`, `ENTER`, `ANALYZE`, `GENERATE`, `ANNOTATION_PROCESSING`, `ANNOTATION_PROCESSING_ROUND`. Không nên đồng nhất event với mọi pass nội bộ của javac hoặc dự đoán mọi file có đúng một event mỗi loại.

`JavacTask` còn có API hỗ trợ phân tích cây cú pháp, chẳng hạn `parse()`, `analyze()` và `Trees` ở những workflow phù hợp. Đây là **lĩnh vực compiler tooling sâu hơn**, và nếu chủ động dùng các phase methods, cần hiểu vòng đời task. **Không** gọi `parse()/analyze()` rồi đồng thời điều khiển `call()` như hai con đường độc lập mà không biết task state.

Dùng các lớp implementation nội bộ `com.sun.tools.javac.*` là một bước khác, thường cần options mở module và dễ bị thay đổi theo JDK. Nếu nhu cầu chỉ là compile và hiển thị errors, hãy ưu tiên `javax.tools`.

## 15. CompilationTask và lỗi chương trình: giới hạn của Boolean success

Khi `task.call()` trả `true`, ta chỉ biết **lượt biên dịch báo thành công** theo compiler. Điều này **không** có nghĩa:

- Method `main` đã được chạy.
- Bytecode được JVM nạp thử với toàn bộ dependency lúc runtime.
- Chương trình không có lỗi logic, deadlock, NPE hoặc lỗi môi trường.
- Mọi annotation processor đều “đúng” theo business rule.
- Đầu ra đã được đóng gói thành JAR hoặc đã được deploy.

Khi `task.call()` trả `false`, thường có compile diagnostics; cần lấy chúng để giải thích. Nhưng **exception** phát sinh từ file manager, invalid options, processor hoặc lỗi hệ thống có thể được ném ra thay vì trả `false` trong một số tình huống. Không nên đồng nhất mọi exception do code của compiler tool với “source code lỗi bình thường”.

Một service thiết kế tốt nên phân biệt trạng thái:

| Trạng thái | Ý nghĩa |
| --- | --- |
| `COMPILED` | `call() == true` và output xử lý thành công |
| `SOURCE_ERROR` | `call() == false` và diagnostics nêu lỗi nguồn |
| `CONFIG_ERROR` | Option, classpath, module path hoặc compiler unavailable |
| `TOOL_FAILURE` | Exception từ processor, manager hoặc compiler infrastructure |
| `RUNTIME_FAILURE` | Chỉ khi app được chạy riêng và gặp lỗi |

Nếu compiler server tiếp nhận nhiều requests, mỗi request nên có diagnostics, output, timeout/quota và concurrency policy rõ ràng. Dùng một `CompilationTask` mới cho mỗi request; không chia sẻ mutable collector và file manager giữa concurrent requests nếu chưa có chứng cứ thread safety.

## 16. Thử biên dịch liên tiếp và caching file manager

Theo contract, standard file manager có thể tái sử dụng cho **nhiều compilation tasks tuần tự**. Lợi ích có thể là giảm công đọc JAR metadata hoặc quét filesystem; không có cam kết sẽ nhanh hơn trong mọi trường hợp.

Ý tưởng (pseudocode Java, không phải class độc lập):

~~~java
try (StandardJavaFileManager manager =
         compiler.getStandardFileManager(null, null, null)) {

    for (BuildRequest request : requests) {
        Iterable<? extends JavaFileObject> units =
                manager.getJavaFileObjectsFromPaths(request.sources());

        JavaCompiler.CompilationTask task = compiler.getTask(
                null, manager, null, request.options(), null, units);

        boolean ok = task.call();
        // Ghi nhận kết quả và diagnostics cho từng request.
    }
}
~~~

`BuildRequest` là **kiểu mô hình tưởng tượng** để minh họa vòng lặp, không có trong JDK; để chạy cần tự định nghĩa. Nếu các requests dùng classpath hoặc output location khác nhau, phải cập nhật cấu hình file manager/task tương ứng, và tránh việc output cũ ảnh hưởng lượt mới.

**Không** sử dụng nguyên một `CompilationTask` cho nhiều lần `call()`. **Không** đương nhiên share một standard file manager cho compiler calls song song trên các thread. Tùy thiết kế, dùng file manager riêng từng request có thể an toàn và đơn giản hơn.

## 17. Hiệu năng, quản lý tài nguyên và bảo mật

Biên dịch code có thể dùng nhiều CPU, RAM, file descriptors và thời gian, dù source không có vòng lặp vô hạn. Một hệ thống cho người dùng upload/nhập Java code nên xét:

1. **Giới hạn kích thước source và số file**; xác nhận encoding, URI, package/class name hợp lệ.
2. **Giới hạn option được phép**: không cho input tùy ý điều khiển `-processorpath`, `-d`, `--patch-module`, `-J` hoặc một đường dẫn hệ thống không được cấp phép.
3. **Chính sách dependency**: tải JAR từ nguồn đáng tin, khóa phiên bản, kiểm soát license và lỗ hổng.
4. **Giới hạn tài nguyên**: worker process/isolated environment với CPU, memory, disk và thời gian hợp lý. Một Java thread không phải ranh giới sandbox.
5. **Tắt annotation processing khi không cần** bằng `-proc:none` để giảm nguy cơ thực thi processor chưa kiểm soát.
6. **Không thực thi mã sau compile** trong cùng tiến trình với tài nguyên nhạy cảm nếu mã đến từ nguồn không đáng tin; dùng môi trường cô lập chuyên dụng.
7. **Tách output theo request**, tránh ghi đè class files của yêu cầu khác; làm sạch output tạm theo chính sách.
8. **Không tin `ClassLoader` là sandbox**. Bảo mật thực tế phải dựa trên isolation ở cấp OS/container và các ràng buộc phù hợp; Java Security Manager không còn là giải pháp đáng dựa vào trong JDK hiện đại.
9. **Thu thập diagnostics an toàn**, tránh xuất quá nhiều logs hoặc lộ absolute paths/bí mật từ môi trường build.
10. **Báo cáo chính xác bước thành công**: compile-only, test, execution, packaging và deployment là những trạng thái khác nhau.

Nếu phải dùng API trong production, nên có policy rõ cho từng loại source: tin cậy (công cụ nội bộ), bán tin cậy (user plugin có kiểm soát), hoặc không tin cậy (public playground). Cấu hình và mức cô lập sẽ khác nhau đáng kể.

## 18. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `getSystemJavaCompiler() == null` | Runtime image thiếu `jdk.compiler` | Kiểm tra JDK thật, module image, toolchain |
| `getTask(...)` báo option không hợp lệ | Sai token option hoặc xung đột `--release`/`--source` | Xem `javac -help`, options của task, compiler version |
| `call() == false` | Source syntax/type/import errors | Đọc `DiagnosticCollector` và source location |
| `getSource() == null` trong diagnostic | Lỗi không gắn với một source cụ thể | Cho phép source nullable, không gọi `toUri()` ngay |
| Biên dịch thành công nhưng không thấy `.class` ở nơi dự đoán | `CLASS_OUTPUT`/`-d` hoặc custom file manager | Kiểm tra output location và provider implementation |
| Có source trong memory nhưng class xuất hiện trên disk | Chỉ custom input, output vẫn do standard manager | Override `getJavaFileForOutput` nếu cần in-memory output |
| Class có bytecode nhưng không chạy được | Chưa load class, sai runtime classpath/dependency | Tách compiler và execution phase |
| `ClassCastException` khi ép task sang `JavacTask` | Compiler provider không phải implementation javac phù hợp | Kiểm tra `instanceof`, tránh cast mù |
| Processor chạy ngoài ý muốn | Processor discovery/configuration trong environment | Dùng `-proc:none` hoặc processor path có kiểm soát |
| Lỗi file handles hoặc JAR bị giữ | Quên close `StandardJavaFileManager` | `try-with-resources`, lifecycle rõ |
| Lỗi encoding của source ngoài ASCII | Charset không thống nhất | Chỉ định UTF-8, không phụ thuộc default charset |
| Lỗi khi biên dịch nhiều request song song | Share mutable manager/collector/task không an toàn | Tách state hoặc đồng bộ theo contract |
| Output class cũ “che” lỗi mới | Không cô lập hoặc làm sạch output | Thư mục riêng từng request, ghi nhận build artifacts |

Không mọi failure đều cần thay compiler options. Nhiều vấn đề xuất phát từ **file manager location**, runtime image, dependency hoặc việc nhầm compile phase với runtime. Bắt đầu debug bằng một source nhỏ hợp lệ, một output dir xác định và diagnostics có cấu trúc.

## 19. Checklist làm việc thực tế với javax.tools

- Có **JDK/compiler implementation** thật, không chỉ giả định từ version string.
- Phân biệt `javax.tools.ToolProvider` và `java.util.spi.ToolProvider`.
- Tạo `JavaFileObject` hợp lệ cho từng compilation unit; source file names/package đúng.
- Dùng `StandardJavaFileManager` khi nguồn/đích là file/JAR thông thường; custom `ForwardingJavaFileManager` chỉ khi cần mở rộng hành vi.
- Cấu hình classpath/module path, `--release` và output location một cách nhất quán.
- Truyền source units vào tham số cuối của `getTask`; không coi `classes` là source file name list.
- Có `DiagnosticCollector` hoặc listener cho thông báo; kiểm tra `getSource()`/`NOPOS` trước khi dùng.
- Gọi `call()` **một lần trên mỗi task**; check `Boolean`, exceptions và output.
- Đóng file manager và tài nguyên; không share state không kiểm soát qua threads.
- Cấu hình annotation processing rõ; tắt `-proc:none` nếu không cần.
- Với in-memory source, quyết định **output sẽ ở đâu**; custom input không đồng nghĩa custom output.
- Không coi compile thành công là đã test/chạy chương trình hoặc đã được sandbox.
- Kiểm thử trên đúng JDK, classpath, module graph và runtime mà công cụ sẽ triển khai.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** `ToolProvider.getSystemJavaCompiler()` trả `null` có nghĩa Java source sai không?  
**Đáp án:** Không. Đó là tình trạng môi trường không cung cấp system compiler; thường cần runtime image/JDK có `jdk.compiler`.

**Câu 2.** Trong `getTask(out, manager, listener, options, classes, units)`, tên tệp `Hello.java` được đưa vào `classes` hay `units`?  
**Đáp án:** Tạo `JavaFileObject` từ source và đưa vào `units`. `classes` không phải tham số thay thế compilation unit thông thường.

**Câu 3.** Vì sao `call() == true` không đồng nghĩa chương trình chạy đúng?  
**Đáp án:** API biên dịch tạo class file; JVM chưa nhất thiết nạp/khởi chạy class và dependency.

**Câu 4.** `DiagnosticCollector` và `DiagnosticListener` liên hệ thế nào?  
**Đáp án:** `DiagnosticCollector` là implementation của `DiagnosticListener` gom các `Diagnostic` vào một danh sách, còn listener tùy biến có thể xử lý ngay mỗi lỗi.

**Câu 5.** Có thể biên dịch nguồn từ chuỗi nhưng class file vẫn xuất ra ổ đĩa không?  
**Đáp án:** Có. Input `SimpleJavaFileObject` in-memory độc lập với output manager; nếu không custom output, standard manager vẫn có thể ghi ra disk.

**Câu 6.** Muốn ghi bytecode vào `Map<String, byte[]>` cần điều chỉnh điểm nào?  
**Đáp án:** JavaFileManager, thường override `getJavaFileForOutput` qua `ForwardingJavaFileManager` và trả JavaFileObject có `openOutputStream()` phù hợp.

**Câu 7.** Có nên dùng `task.call()` nhiều lần trên cùng object?  
**Đáp án:** Không. Task chỉ dành cho một lượt; tạo task mới, có thể tái dùng standard file manager tuần tự nếu phù hợp.

**Câu 8.** Compiler server nhận Java source không đáng tin đã bật `-proc:none`, vậy có an toàn tuyệt đối không?  
**Đáp án:** Không. Tắt processor chỉ giảm một đường thực thi mã; compilation vẫn tiêu thụ tài nguyên và có nhiều bề mặt tấn công. Nếu chạy class được tạo thì càng cần isolation nghiêm ngặt.

**Câu 9.** Làm cách nào quan sát sự kiện `PARSE`/`GENERATE` khi dùng javac?  
**Đáp án:** Với system javac, có thể dùng `JavacTask`/`TaskListener`; đó là API quan sát cấp cao, không phải API chung cho mọi compiler provider.

## 21. Ghi nhớ và tài liệu chuẩn

**`JavaCompiler`** tạo compiler task; **`JavaFileObject`** mô tả source/class files; **`JavaFileManager`** quyết định cách tìm/ghi file; **`DiagnosticListener`**/`DiagnosticCollector` xử lý lỗi; **`CompilationTask.call()`** thực thi biên dịch. Hãy giữ tách biệt **compile inputs**, **compiler options**, **class output**, **diagnostics** và **runtime execution**.

Nếu chỉ cần biên dịch Java source trên đĩa, dùng `StandardJavaFileManager`. Nếu source là String, dùng `SimpleJavaFileObject`. Nếu bytecode cũng phải nằm trong memory, dùng custom `JavaFileManager`. Nếu quan sát AST/phase, xem API `JavacTask` của module `jdk.compiler` khi implementation hỗ trợ. Không coi thành công compile là đảm bảo runtime hay cô lập bảo mật.

Nguồn chính thức để đào sâu:

- [JavaCompiler — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html).
- [ToolProvider — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html).
- [StandardJavaFileManager — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html).
- [JavaFileManager — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaFileManager.html).
- [SimpleJavaFileObject — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html).
- [JavacTask — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/JavacTask.html).

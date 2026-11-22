# Lưu nhiều tệp class cho lớp lồng nhau và nguồn được sinh khi biên dịch Java trong bộ nhớ

Khi sử dụng `javax.tools.JavaCompiler` để biên dịch Java source ngay trong RAM, một sai lầm phổ biến là chuẩn bị một `ByteArrayOutputStream` cho “class chính” rồi coi đó là toàn bộ kết quả. Thực tế, **một compilation unit có thể sinh nhiều tệp `.class`**: class top-level, member class, local class, anonymous class và những kiểu mới được annotation processor tạo ra. Một generated Java source có thể đồng thời tồn tại dưới dạng `.java` trong `SOURCE_OUTPUT` và `.class` trong `CLASS_OUTPUT`.

Vì vậy, bài toán đúng không phải là “biên dịch một chuỗi trả về một mảng byte”, mà là **thu toàn bộ file outputs theo location, kind và binary name**, bảo toàn chúng đến khi compiler hoàn tất, rồi cung cấp đủ class bytes cho classloader.

## 1. Mô hình tổng thể

~~~text
Các JavaFileObject Kind.SOURCE (chuỗi mã nguồn từ RAM)
                             |
                    JavaCompiler.getTask
                             |
                     Annotation processor
                             |
               Filer.createSourceFile(...)
                             |
                SOURCE_OUTPUT + Kind.SOURCE
                    Generated.java (RAM)
                             |
                      Processing rounds
                             |
                         javac codegen
                             |
                CLASS_OUTPUT + Kind.CLASS
                  +----------+-----------+
                  |          |           |
             Main.class Outer.class  Outer$Nested.class
                  |          |           |
                  +----------+---- ... --+
                             |
                      Map<String, byte[]>
                             |
                      Custom ClassLoader
                             |
                        defineClass()
                             |
                     Thực thi trong JVM
~~~

**Phân biệt rõ:**

- **Source đầu vào:** `JavaFileObject` loại `Kind.SOURCE` để compiler đọc những tệp Java ảo do ứng dụng cung cấp.
- **Generated source:** `JavaFileObject` loại `Kind.SOURCE` được tạo bởi `Filer`/processor tại location `StandardLocation.SOURCE_OUTPUT`. Compiler có thể đọc nguồn đó ở processing round tiếp theo.
- **Compiled binary:** `JavaFileObject` loại `Kind.CLASS` tại `StandardLocation.CLASS_OUTPUT`. Một source input có thể dẫn đến **nhiều lần** gọi tạo output.
- **Runtime loading:** `ClassLoader` dùng binary name và class bytes. Việc lưu bytes vào map không tự đưa type vào application classpath.

Java compiler API thuộc module chuẩn `java.compiler`; bản implementation system compiler đòi hỏi JDK có compiler, thường là module `jdk.compiler`. `ToolProvider.getSystemJavaCompiler()` có thể trả `null` trong môi trường thiếu compiler.

## 2. Vì sao số class files lớn hơn số source files?

Xét nguồn sau (đoạn minh họa chưa độc lập):

~~~java
package demo;

public class Outer {
    public static class Nested {}

    public void run() {
        class Local {}
        Runnable anonymous = new Runnable() {
            @Override public void run() {}
        };
        anonymous.run();
    }
}
~~~

Với `javac` thông thường, ngoài `demo.Outer` còn có các binary classes cho `demo.Outer$Nested`, `Local` và anonymous class. Tên của local/anonymous classes thường chứa `$` và số thứ tự, **nhưng chi tiết đánh số không phải API ổn định cho mọi compiler**. Đừng tự đoán tên file hoặc chỉ lọc các class có cùng simple name với source.

| Nguyên nhân | Ví dụ | Đầu ra cần lưu |
| --- | --- | --- |
| Top-level type | `class Outer` | `demo.Outer` |
| Static nested/member type | `static class Nested` | `demo.Outer$Nested` |
| Non-static inner member type | `class Inner` | Thường `demo.Outer$Inner` |
| Local class trong method | `class Local` | Binary name riêng, thường có phần số |
| Anonymous class | `new Runnable() { ... }` | Binary name riêng, thường có `$N` |
| Một compilation unit khai báo nhiều types | Package-private type cùng file | Mỗi top-level type cần class output riêng |
| Generated Java source | `Filer.createSourceFile("demo.Generated")` | Generated `.java` và, nếu compile thành công, `.class` |
| Processor tạo binary trực tiếp | `Filer.createClassFile` | `.class` không nhất thiết có generated `.java` |
| Record, enum và synthetic constructs | `record Point(...)` | `.class` tương ứng; có thể có thêm members/classes tùy trường hợp |
| Lambda | `() -> doWork()` | **Không bắt buộc tạo `Outer$N.class`**; `javac` hiện đại thường dùng `invokedynamic` |

**Nguyên tắc lưu:** compiler là nguồn thông tin đúng về **những output được tạo**. Đừng tính số lượng class files từ việc đếm dấu `class`, số constructor hay số lambda trong source.

## 3. Callback quan trọng nhất: `getJavaFileForOutput`

Giao diện cốt lõi của `JavaFileManager`:

~~~java
JavaFileObject getJavaFileForOutput(
    JavaFileManager.Location location,
    String className,
    JavaFileObject.Kind kind,
    FileObject sibling
) throws IOException;
~~~

Đây là chữ ký API, không phải tệp Java chạy độc lập.

- `location`: thường `StandardLocation.CLASS_OUTPUT` hoặc `SOURCE_OUTPUT`. Đây là **nơi logic** compiler muốn ghi.
- `className`: **binary name** do compiler cung cấp. Ví dụ `demo.Outer$Nested`, khác với source name `demo.Outer.Nested` và khác URI file.
- `kind`: `JavaFileObject.Kind.CLASS` cho compiled binary, `Kind.SOURCE` cho generated Java source.
- `sibling`: file object liên quan để hỗ trợ xác định output; không nên dùng riêng sibling làm khóa duy nhất, vì một source có thể sinh nhiều binary files.
- Giá trị trả về: một `JavaFileObject` có khả năng nhận nội dung mà compiler/processor ghi vào.

Trong bản bộ nhớ:

~~~text
CLASS_OUTPUT  + CLASS  + "demo.Outer$Nested" -> byte[] của .class
SOURCE_OUTPUT + SOURCE + "demo.Generated"    -> bytes/text của .java
CLASS_OUTPUT  + CLASS  + "demo.Generated"    -> byte[] của .class
~~~

Do **`demo.Generated` có thể xuất hiện hai lần với kind khác nhau**, cần tách `Map<String, Output> classFiles` và `Map<String, Output> generatedSources` hoặc dùng khóa tổng hợp `(location, kind, name)`. Không lưu cả hai vào map chỉ khóa bằng `"Generated"`.

Một output object cần buffer riêng, không chia sẻ cùng `ByteArrayOutputStream` giữa các class names. Nếu nhiều files cùng ghi vào một buffer, bytes bị lẫn hoặc bị reset, làm loader thất bại với `ClassFormatError`, `NoClassDefFoundError` hoặc thông báo linkage khác.

## 4. Ví dụ Java 17+ đầy đủ: source trong RAM, processor sinh nguồn, nhiều class outputs

Ví dụ dùng **một tệp duy nhất** ở phía host: `MemoryCompilerDemo.java`. Trong lúc chạy, host tạo ba sources ảo `demo.Marker`, `demo.Outer` và `demo.Main`. Một annotation processor chạy trong cùng process sinh `demo.Generated`. Compiler ghi tất cả class bytes vào map; custom loader nạp `demo.Main`, gồm cả các dependencies nằm trong map.

### 4.1. Toàn bộ mã nguồn

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileManager;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public final class MemoryCompilerDemo {
    // Source Java viết sẵn, được cung cấp từ String.
    static final class Source extends SimpleJavaFileObject {
        private final String source;

        Source(String binaryName, String source) {
            super(URI.create("string:///" + binaryName.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.source = source;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return source;
        }
    }

    // Mỗi output file có buffer riêng, dùng cho CLASS hoặc SOURCE.
    static final class Output extends SimpleJavaFileObject {
        private final ByteArrayOutputStream buffer = new ByteArrayOutputStream();

        Output(String binaryName, Kind kind) {
            super(URI.create("mem:///" + binaryName.replace('.', '/')
                    + kind.extension), kind);
        }

        @Override
        public OutputStream openOutputStream() {
            buffer.reset();
            return buffer;
        }

        @Override
        public Writer openWriter() {
            return new OutputStreamWriter(openOutputStream(), StandardCharsets.UTF_8);
        }

        @Override
        public InputStream openInputStream() {
            return new ByteArrayInputStream(buffer.toByteArray());
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return new String(buffer.toByteArray(), StandardCharsets.UTF_8);
        }

        byte[] bytes() {
            return buffer.toByteArray();
        }
    }

    static final class MemoryFiles
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        final Map<String, Output> classFiles = new TreeMap<>();
        final Map<String, Output> generatedSources = new TreeMap<>();

        MemoryFiles(StandardJavaFileManager delegate) {
            super(delegate);
        }

        @Override
        public boolean hasLocation(Location location) {
            if (location == StandardLocation.CLASS_OUTPUT
                    || location == StandardLocation.SOURCE_OUTPUT) {
                return true;
            }
            return super.hasLocation(location);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(Location location,
                String className, JavaFileObject.Kind kind, FileObject sibling)
                throws IOException {
            if (location == StandardLocation.CLASS_OUTPUT
                    && kind == JavaFileObject.Kind.CLASS) {
                Output file = new Output(className, kind);
                if (classFiles.putIfAbsent(className, file) != null) {
                    throw new IOException("Duplicate class output: " + className);
                }
                return file;
            }
            if (location == StandardLocation.SOURCE_OUTPUT
                    && kind == JavaFileObject.Kind.SOURCE) {
                Output file = new Output(className, kind);
                if (generatedSources.putIfAbsent(className, file) != null) {
                    throw new IOException("Duplicate source output: " + className);
                }
                return file;
            }
            return super.getJavaFileForOutput(location, className, kind, sibling);
        }
    }

    // Processor được đăng ký TƯỜNG MINH trong CompilationTask.
    @SupportedAnnotationTypes("demo.Marker")
    @SupportedSourceVersion(SourceVersion.RELEASE_17)
    public static final class Generator extends AbstractProcessor {
        private boolean emitted;

        @Override
        public boolean process(Set<? extends TypeElement> annotations,
                RoundEnvironment round) {
            if (emitted || round.processingOver() || annotations.isEmpty()) {
                return true;
            }
            emitted = true;
            try (Writer writer = processingEnv.getFiler()
                    .createSourceFile("demo.Generated").openWriter()) {
                writer.write("package demo;\n"
                        + "public class Generated {\n"
                        + "  public static String message() { return \"generated\"; }\n"
                        + "}\n");
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR, ex.toString());
            }
            return true;
        }
    }

    static final class ByteLoader extends ClassLoader {
        private final Map<String, byte[]> classes;

        ByteLoader(ClassLoader parent, Map<String, byte[]> classes) {
            super(parent);
            this.classes = classes;
        }

        @Override
        protected Class<?> findClass(String name) throws ClassNotFoundException {
            byte[] data = classes.get(name);
            if (data == null) {
                throw new ClassNotFoundException(name);
            }
            return defineClass(name, data, 0, data.length);
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("A full JDK is required");
        }

        List<JavaFileObject> inputs = List.of(
                new Source("demo.Marker", """
                        package demo;
                        public @interface Marker {}
                        """),
                new Source("demo.Outer", """
                        package demo;
                        @Marker
                        public class Outer {
                            public static class Nested {
                                public static String text() { return "nested"; }
                            }
                            public String local() {
                                class Local { String text() { return "local"; } }
                                return new Local().text();
                            }
                            public String anonymous() {
                                Runnable task = new Runnable() {
                                    @Override public void run() {}
                                };
                                task.run();
                                return "anonymous";
                            }
                        }
                        """),
                new Source("demo.Main", """
                        package demo;
                        public class Main {
                            public static void main(String[] args) {
                                System.out.println(Generated.message());
                                System.out.println(Outer.Nested.text());
                                System.out.println(new Outer().local());
                                System.out.println(new Outer().anonymous());
                            }
                        }
                        """));

        DiagnosticCollector<JavaFileObject> diagnostics = new DiagnosticCollector<>();
        try (StandardJavaFileManager standard = compiler.getStandardFileManager(
                diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
            MemoryFiles files = new MemoryFiles(standard);
            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, files, diagnostics, List.of("--release", "17"),
                    null, inputs);
            task.setProcessors(List.of(new Generator()));

            if (!Boolean.TRUE.equals(task.call())) {
                for (Diagnostic<? extends JavaFileObject> d :
                        diagnostics.getDiagnostics()) {
                    System.err.println(d);
                }
                throw new IllegalStateException("Compilation failed");
            }

            Map<String, byte[]> classBytes = new TreeMap<>();
            files.classFiles.forEach(
                    (name, file) -> classBytes.put(name, file.bytes()));

            System.out.println("generated-source="
                    + files.generatedSources.containsKey("demo.Generated"));
            System.out.println("generated-class="
                    + classBytes.containsKey("demo.Generated"));
            System.out.println("member-class="
                    + classBytes.containsKey("demo.Outer$Nested"));
            System.out.println("extra-classes="
                    + classBytes.keySet().stream()
                    .filter(n -> n.startsWith("demo.Outer$")
                            && !n.equals("demo.Outer$Nested"))
                    .count());

            ByteLoader loader = new ByteLoader(
                    MemoryCompilerDemo.class.getClassLoader(), classBytes);
            Class<?> main = Class.forName("demo.Main", true, loader);
            main.getMethod("main", String[].class)
                    .invoke(null, (Object) new String[0]);
        }
    }
}
~~~

### 4.2. Lệnh chạy và kết quả

Lưu toàn bộ đoạn code trên vào `MemoryCompilerDemo.java`, dùng JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 MemoryCompilerDemo.java
java MemoryCompilerDemo
~~~

**Stdout đã kiểm chứng bằng OpenJDK 21 với target Java 17:**

~~~text
generated-source=true
generated-class=true
member-class=true
extra-classes=2
generated
nested
local
anonymous
~~~

`generated-source=true` và `generated-class=true` xác nhận **cùng một type `demo.Generated`** có cả generated source lẫn compiled binary. `member-class=true` xác nhận `demo.Outer$Nested` không bị bỏ sót. `extra-classes=2` là hai class bổ sung từ local/anonymous constructs khi dùng `javac` của JDK đã thử, nhưng **không sử dụng tên đánh số của chúng làm khóa cố định trong logic ứng dụng**.

Chỉ mã Java của host `MemoryCompilerDemo.java` được biên dịch trực tiếp bằng lệnh bên ngoài; các types `demo.*` được biên dịch vào RAM thông qua `JavaCompiler`. Phần chạy `demo.Main` dùng map bytes, không cần ghi các class `demo.*` ra ổ đĩa.

## 5. Bóc tách từng phần quan trọng

### 5.1. `Source`: Java source không cần file trên đĩa

`SimpleJavaFileObject` được tạo với URI dạng `string:///demo/Outer.java` và `Kind.SOURCE`, rồi `getCharContent` trả source string. Một `CompilationTask` có thể nhận nhiều `JavaFileObject` tương ứng các source units. URI cần hợp lệ, mang đuôi thích hợp cho kind và giúp chẩn đoán tên file rõ ràng.

Ví dụ ba input sources trong chương trình gồm `demo.Marker`, `demo.Outer` và `demo.Main`. Số source files này **không** đặt giới hạn cho số `Kind.CLASS` outputs. Nếu có thêm top-level types hoặc generated source, compiler vẫn có thể tạo nhiều outputs khác.

### 5.2. `Output`: buffer riêng và khả năng đọc lại generated source

Class bytes được compiler ghi qua `openOutputStream`. Source mới do `Filer.createSourceFile` tạo có thể được processor ghi qua `openWriter`; compiler phải đọc generated source trong round sau, nên `getCharContent` và `openInputStream` phải được hỗ trợ phù hợp.

Trong ví dụ, `openWriter` sử dụng UTF-8 và `getCharContent` giải mã cùng encoding. Điều này tránh mất ký tự Unicode khi processor sinh source chứa chuỗi Unicode. Mỗi `Output` có một `ByteArrayOutputStream` **riêng**, tránh trộn bytes giữa `Outer.class`, `Outer$Nested.class` và `Generated.class`.

### 5.3. `MemoryFiles`: phân loại theo location + kind

`ForwardingJavaFileManager<StandardJavaFileManager>` delegate việc tìm JDK classes, module/classpath inputs và các thao tác không override cho standard manager. Ta chỉ chặn hai nhánh:

~~~java
// Mã minh họa trong getJavaFileForOutput(...)
if (location == StandardLocation.CLASS_OUTPUT
        && kind == JavaFileObject.Kind.CLASS) {
    // Lưu vào classFiles bằng className
}
if (location == StandardLocation.SOURCE_OUTPUT
        && kind == JavaFileObject.Kind.SOURCE) {
    // Lưu vào generatedSources bằng className
}
~~~

Đây là **đoạn minh họa**, không phải method đầy đủ. `hasLocation` cho biết file manager nhận hai output locations do nó xử lý.

Nếu muốn hỗ trợ processor sinh **resources**, cần bổ sung xử lý `getFileForOutput(Location, packageName, relativeName, sibling)`. Method này khác `getJavaFileForOutput` và không tự được chặn bởi ví dụ. Resource như `META-INF/services/...` cần map riêng theo location/package/path. Vì thế demo đã bao phủ **generated Java source và class outputs**, nhưng không tự tuyên bố bao phủ mọi loại file mà một processor bất kỳ có thể tạo.

### 5.4. `Generator`: source mới sinh ra trong compilation

Processor được đăng ký bằng:

~~~java
task.setProcessors(List.of(new Generator()));
~~~

Cách này không phụ thuộc service descriptor hoặc auto-discovery. `Generator` được kích hoạt khi compiler phát hiện `@demo.Marker`, tạo `demo.Generated` qua `Filer` rồi không tạo trùng trong các rounds sau.

Cần hiểu trình tự:

1. `demo.Outer` được annotate bằng `@Marker`.
2. Compiler gọi `Generator.process(...)`.
3. Processor tạo `SOURCE_OUTPUT / demo.Generated.java`.
4. Compiler nhận generated source, resolve `Generated.message()` được `demo.Main` gọi.
5. Bytecode generator yêu cầu class output cho `demo.Generated`.
6. `MemoryFiles.classFiles` chứa bytes tương ứng.

`@SupportedSourceVersion(SourceVersion.RELEASE_17)` mô tả mức source processor hỗ trợ; `--release 17` trong compilation options mới là lựa chọn target Java 17. Một `CompilationTask` chỉ dùng một lần: phải tạo task mới cho lần biên dịch mới.

### 5.5. `ByteLoader`: class name phải là binary name

`ClassLoader.findClass(String name)` nhận binary name như `demo.Main` hoặc `demo.Outer$Nested`. Dùng chính `className` compiler truyền vào manager làm map key sẽ giúp `findClass` tra đúng.

`defineClass(name, bytes, 0, bytes.length)` tạo runtime class definition từ bytes. Khi `demo.Main` dùng `Generated` hay nested/local/anonymous types, classloader phải tìm được tất cả những classes liên quan.

`Class.forName("demo.Main", true, loader)` chỉ định loader của bộ bytecode. Cast `(Object) new String[0]` trong lời gọi reflection:

~~~java
main.getMethod("main", String[].class)
    .invoke(null, (Object) new String[0]);
~~~

bảo đảm mảng `String[]` được truyền **như một đối số** cho `main(String[])`, tránh cơ chế trải varargs của `Method.invoke`.

`ByteLoader` dùng parent-first delegation theo hành vi mặc định: nếu parent classloader đã chứa class **cùng binary name**, parent có thể được ưu tiên. Đây là demo cơ chế loading, **không phải sandbox** hoặc giải pháp classloader isolation đầy đủ.

## 6. Source file, output file và binary name là ba thứ khác nhau

Ví dụ type `demo.Outer$Nested`:

~~~text
Source compilation unit: demo.Outer  (string:///demo/Outer.java)
Java nested source name: demo.Outer.Nested
JVM binary name:          demo.Outer$Nested
Class output:             mem:///demo/Outer$Nested.class
Map key:                  "demo.Outer$Nested"
~~~

Đối với local và anonymous classes, compiler được quyền dùng naming scheme tạo những binary names riêng (thường có số), nên **không suy đoán** output name từ AST hoặc tên source. Để lưu toàn bộ class bytes, không cần biết trước danh sách names: cứ nhận mọi `CLASS_OUTPUT + Kind.CLASS` callback.

`getJavaFileForOutput` có tham số `sibling` nhưng không nên dùng sibling source làm key, vì nhiều outputs có thể thuộc **cùng một sibling**.

## 7. Phân biệt class files và generated sources của annotation processing

| Loại | API tạo | File manager location | Nội dung |
| --- | --- | --- | --- |
| Java source do processor sinh | `Filer.createSourceFile` | `SOURCE_OUTPUT` | Java text / `Kind.SOURCE` |
| Java class do compiler sinh | Code generation của `javac` | `CLASS_OUTPUT` | JVM binary / `Kind.CLASS` |
| Java class do processor sinh trực tiếp | `Filer.createClassFile` | `CLASS_OUTPUT` | JVM binary / `Kind.CLASS` |
| Resource do processor sinh | `Filer.createResource` | `SOURCE_OUTPUT` hoặc `CLASS_OUTPUT` | Tùy resource; có thể không phải Java source |
| Source viết tay đầu vào | `new Source(...)` | Compilation units | Java text compiler đọc |
| Dependency đã biên dịch | Classpath/module path manager | `CLASS_PATH`/`MODULE_PATH` | Bytecode đầu vào, **không phải output mới** |

Với `-proc:only`, annotation processing có thể sinh `Generated.java` mà **không sinh class file ứng dụng**. Nếu muốn làm pipeline hai bước, lần compile kế tiếp phải nhận generated source làm input và tạo task mới (thường dùng `-proc:none` để không sinh trùng). Trong ví dụ chính, pipeline là processing **và** compilation trong cùng task.

Nếu source sinh ra sai cú pháp hoặc không resolve được type, compiler có thể đã tạo `Generated.java` nhưng compilation thất bại và class map không đầy đủ. Không dùng map làm bản build hợp lệ nếu `task.call()` không thành công.

## 8. Quản lý nhiều compilation runs

Dùng compiler để xây công cụ IDE, expression evaluator hoặc plugin server nghĩa là có thể compile nhiều lần trong cùng JVM. Một vài nguyên tắc:

1. **Mỗi lần compile có output maps riêng.** Không cho classBytes của run cũ lẫn run mới.
2. **Không dùng lại một `CompilationTask`.** API task dùng cho một compilation; tạo task mới mỗi lượt.
3. **Không tái định nghĩa cùng binary name trong cùng classloader.** Nếu muốn load phiên bản mới, thường tạo classloader mới cho run mới.
4. **Đóng tài nguyên chuẩn.** `StandardJavaFileManager` implement `Closeable`; dùng try-with-resources như ví dụ. Output buffers có thể được snapshot ra byte arrays sau compile thành công.
5. **Cẩn thận chia sẻ `byte[]`.** `Map.copyOf(...)` không clone phần tử bytes; caller có thể sửa byte arrays nếu bạn trả tham chiếu trực tiếp. Copy từng mảng khi cần bất biến.
6. **Đồng bộ khi cần.** Không tự coi compiler task, maps và buffers chia sẻ an toàn giữa threads. Nếu nhiều requests chạy đồng thời, mỗi request nên có manager/state riêng.
7. **Cache đúng khóa.** Cùng một source string nhưng JDK version, `--release`, classpath, processor version hoặc compiler options khác có thể tạo output khác. Không cache chỉ theo main class name.
8. **Giới hạn tài nguyên.** Bytecode/output có thể lớn; chỉ compile và thực thi code tin cậy trong process ứng dụng, hoặc áp dụng isolation thực sự cho mã không tin cậy.

## 9. Diagnostics và lỗi một phần

`DiagnosticCollector<JavaFileObject>` lưu thông tin compiler warnings/errors. Nếu `task.call()` trả false, có thể vẫn còn **một số outputs đã tạo trước khi phát hiện lỗi**. Không đưa chúng lên runtime classloader và tuyên bố build thành công.

Đoạn xử lý lỗi minh họa:

~~~java
// Chỉ dùng thay vị trí call() hiện có, không gọi task.call() lần hai.
boolean success = Boolean.TRUE.equals(task.call());
if (!success) {
    for (Diagnostic<? extends JavaFileObject> diagnostic
            : diagnostics.getDiagnostics()) {
        System.err.println(diagnostic.getKind() + ": "
                + diagnostic.getMessage(Locale.ROOT));
    }
}
~~~

Mã trên là đoạn đặt trong method có `task` và `diagnostics` phù hợp. Trong ứng dụng thực tế, bổ sung URI source, line, column để chỉ ra lỗi xuất phát từ source đầu vào hay generated source.

Một kết quả compile có thể được mô hình hóa:

~~~java
// Record minh họa bên trong dự án có imports phù hợp
record CompileResult(
    boolean success,
    Map<String, byte[]> classBytes,
    Map<String, String> generatedSources,
    List<String> diagnostics
) {}
~~~

Tuy nhiên không trả class outputs nếu compilation thất bại như thể thành công. Nên tạo snapshot immutable *về mặt logic*, clone bytes khi dữ liệu được giao sang thread/plugin khác, và giữ generated-source text chỉ khi cần debug/audit.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách sửa |
| --- | --- | --- |
| `ClassNotFoundException: demo.Outer$Nested` | Chỉ lưu class chính | Lưu **mọi** `getJavaFileForOutput(CLASS_OUTPUT, ...)` |
| `NoClassDefFoundError` lúc chạy method | Thiếu class phụ trợ/local/anonymous trong loader | Đối chiếu binary name lỗi với map keys |
| `ClassFormatError` | Reuse một buffer hoặc key sai bytes | Một buffer mỗi output, key bằng className từ compiler |
| `Generated.java` có nhưng `Generated.class` không có | `-proc:only` hoặc compilation lỗi | Kiểm tra compile options, diagnostics và class map |
| `Generated.class` có nhưng không có source | Processor tạo class binary trực tiếp, hoặc source location không chặn | Kiểm tra processor API và locations |
| `FilerException` | Cố tạo cùng file nhiều lần/đụng input | Guard rounds, tránh tên trùng |
| `ToolProvider.getSystemJavaCompiler() == null` | Runtime thiếu compiler | Chạy full JDK |
| `UnsupportedOperationException` khi đọc generated source | In-memory output chỉ có write stream | Thêm `getCharContent`/`openInputStream` |
| `IllegalArgumentException` với URI | URI không hợp lệ, không đúng source kind | Dùng URI có scheme/path/extension phù hợp |
| Compiled code dùng bản cũ | Map hoặc parent classloader giữ class khác cùng name | New run state và loader isolation |
| Processor sinh resource trên disk | Không override `getFileForOutput` | Thêm resource handling |
| App chạy được trên máy build nhưng không trên deploy | Không đóng gói đủ nested/generated classes | Xuất tất cả class bytes cần thiết |
| Class-output map có entry nhưng compilation thất bại | Compiler ghi một phần trước khi lỗi | Chỉ công bố kết quả nếu task thành công |

### Quy trình debug

1. Xác nhận `ToolProvider.getSystemJavaCompiler()` và JDK/target release.
2. Xác nhận input `JavaFileObject` có kind/source text/URI hợp lệ.
3. Xác nhận processor được đăng ký và nguồn sinh qua `Filer`.
4. Log từng callback `location + kind + className`; **không chỉ log Main**.
5. Kiểm tra `generatedSources` có đúng source mới và compiler đọc được.
6. Kiểm tra `classFiles` có đủ outputs, byte lengths hợp lệ, không bị ghi đè.
7. Kiểm tra diagnostics/success; không dùng partial build.
8. Tạo classloader mới và thực thi code để phát hiện thiếu binary dependencies.
9. Thử source có nested, local, anonymous và processor-generated types: đây là bộ test quan trọng cho file manager.

## 11. Tự kiểm tra kiến thức

**1.** Vì sao một source `Outer.java` có thể sinh nhiều `.class`?  
Vì outer chứa member/local/anonymous types và compiler có thể tạo nhiều outputs. Số source files không xác định số class files.

**2.** Khóa map tốt nhất cho class output là gì?  
Dùng **binary name nguyên văn** compiler truyền vào `getJavaFileForOutput`, ví dụ `demo.Outer$Nested`, không dùng simple name hoặc source filename.

**3.** `SOURCE_OUTPUT` và `CLASS_OUTPUT` khác nhau thế nào?  
`SOURCE_OUTPUT` lưu generated Java text/source files; `CLASS_OUTPUT` lưu compiled JVM bytecode (và có thể resources).

**4.** Vì sao `demo.Generated` có thể xuất hiện trong hai maps?  
Một entry là generated `Generated.java`; entry kia là compiled `Generated.class`, cùng tên type nhưng khác kind/location.

**5.** Lambda có bắt buộc tạo một class file bổ sung như anonymous class?  
Không. `javac` hiện đại thường biểu diễn lambda qua `invokedynamic`; chỉ lưu những output compiler thực sự tạo.

**6.** Lúc nào `Generated.java` có mà chưa có `Generated.class`?  
Với `-proc:only`, lỗi biên dịch generated source, hoặc khi pipeline cố ý tách processing và compilation thành hai lượt.

**7.** Chỉ override `openOutputStream` có đủ để hỗ trợ processor sinh Java source trong RAM không?  
Chưa chắc. Compiler có thể cần đọc generated source bằng `getCharContent` hoặc `openInputStream`; cần thiết kế file object hỗ trợ các thao tác đó.

**8.** Vì sao trong ví dụ dùng `Class.forName("demo.Main", true, loader)`?  
Các classes `demo.*` chỉ nằm trong map memory, không được ghi ra application classpath. Phải dùng loader đọc map.

**9.** Có thể dùng lại một `ClassLoader` để thay bytes của class đã define không?  
Không theo cơ chế `defineClass` thông thường. Mỗi version/run nên dùng loader phù hợp riêng.

**10.** Có thể coi compiler + custom classloader là sandbox để chạy code không tin cậy không?  
Không. Bytecode thực thi có thể có quyền process; cần isolation tài nguyên và quyền ở tầng thích hợp.

## 12. Checklist triển khai

- [ ] Dùng `JavaFileObject.Kind.SOURCE` cho input source strings.
- [ ] Tạo một output buffer **riêng** cho mỗi class/source output.
- [ ] Thu **tất cả** `CLASS_OUTPUT + Kind.CLASS` callbacks, không lọc riêng main class.
- [ ] Giữ nguyên binary names có dấu `$` của nested/local/anonymous classes.
- [ ] Thu `SOURCE_OUTPUT + Kind.SOURCE` khi processor sinh Java source.
- [ ] Generated source object hỗ trợ ghi **và đọc lại** cho processing rounds.
- [ ] Map source và map class tách biệt; mở rộng khóa với location/kind/module/run nếu cần.
- [ ] Nếu processor sinh resources, xử lý thêm `getFileForOutput`.
- [ ] Chỉ load outputs khi `CompilationTask.call()` thành công.
- [ ] Snapshot bytes/diagnostics và tách mỗi compilation run để tránh stale state.
- [ ] Classloader resolve được **mọi** dependent binary classes đã sinh.
- [ ] Kiểm thử case member, local, anonymous và source do processor tạo.
- [ ] Không dựa vào tên đánh số local/anonymous hoặc số class file của lambda.
- [ ] Bảo vệ hệ thống khi compile/load code không tin cậy bằng isolation thực sự.

## Tài liệu tham khảo

- [Java 17 API — JavaCompiler](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html): compilation task và file manager.
- [Java 17 API — JavaFileManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaFileManager.html): `getJavaFileForOutput` và output locations.
- [Java 17 API — ForwardingJavaFileManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ForwardingJavaFileManager.html): delegation đến standard manager.
- [Java 17 API — SimpleJavaFileObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html): JavaFileObject cho memory input/output.
- [Java 17 API — Filer](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html): generated source/class/resource outputs.
- [Java 17 API — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `findClass` và `defineClass`.

**Kết luận:** Với JavaCompiler trong bộ nhớ, kết quả đúng là **tập hợp tất cả các output files** được compiler/processor yêu cầu, phân biệt **source và class**, giữ **binary names** chính xác, rồi nạp class từ toàn bộ bytecode tương ứng. Một source có thể tạo nhiều `.class`, và một generated source có thể tiếp tục sinh generated class ngay trong compilation. Thu đủ outputs mới giúp runtime tránh mất lớp lồng nhau hoặc lớp do processor sinh.

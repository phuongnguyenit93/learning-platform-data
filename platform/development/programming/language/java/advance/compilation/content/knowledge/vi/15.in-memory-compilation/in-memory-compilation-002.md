# Biểu diễn nguồn String bằng SimpleJavaFileObject

Trong Java, ta có thể biên dịch một đoạn mã nguồn **đang nằm trong `String`** mà không cần tạo tệp `.java` trên ổ đĩa. API `javax.tools.JavaCompiler` nhận tập đối tượng `JavaFileObject` thay vì chỉ tên đường dẫn tệp. Để đưa một `String` vào đầu vào của compiler, cách phổ biến là kế thừa **`SimpleJavaFileObject`**, tạo một URI biểu diễn tên nguồn và override **`getCharContent(boolean)`** để trả nội dung mã Java.

Cách làm này rất hữu ích cho trình soạn thảo code, bài tập trực tuyến, bộ sinh mã, compiler test, hệ thống template và các công cụ phân tích nguồn. Tuy nhiên cần nắm một ranh giới quan trọng: **nguồn ở bộ nhớ không đồng nghĩa class file đầu ra cũng ở bộ nhớ**. Nếu vẫn dùng `StandardJavaFileManager` mặc định và cấu hình `-d out`, class file được ghi ra ổ đĩa. Muốn giữ cả bytecode trong RAM phải bổ sung một `JavaFileManager` xử lý đầu ra.

Bài học tập trung vào **biểu diễn một đơn vị nguồn `.java` từ chuỗi** và cách truyền nó vào `JavaCompiler`, đồng thời cung cấp ví dụ nâng cao cho biên dịch hoàn toàn trong bộ nhớ. Các chương trình độc lập chạy với **Java 17+** và đã được kiểm chứng bằng JDK 24 với tham số `--release 17`.

## 1. Những API tham gia vào quá trình

| Thành phần | Vai trò | Lưu ý |
| --- | --- | --- |
| `ToolProvider.getSystemJavaCompiler()` | Lấy compiler Java cung cấp bởi JDK hiện tại | Trả `null` khi không có compiler thích hợp trong runtime |
| `JavaCompiler` | Tạo compilation task | Là interface của Java Compiler API, không phải lệnh shell `javac` |
| `JavaFileObject` | Trừu tượng hóa nguồn, class hoặc loại file phục vụ compiler | Có `Kind.SOURCE`, `Kind.CLASS` và các dạng khác |
| `SimpleJavaFileObject` | Lớp cơ sở giúp tự định nghĩa JavaFileObject | Cần override phương thức đọc/ghi theo mục đích |
| `URI` | Định danh logic cho đơn vị nguồn | Không yêu cầu URI đó trỏ đến file thật nếu object có thể cung cấp nội dung |
| `getCharContent(boolean)` | Cung cấp các ký tự mã nguồn | Đường đọc quan trọng cho nguồn từ String |
| `StandardJavaFileManager` | File manager tiêu chuẩn của compiler | Phù hợp để sử dụng classpath, module path và output trên đĩa |
| `DiagnosticCollector` | Thu nhận error/warning/note có cấu trúc | Dùng để xem nguồn, dòng, cột, mức độ |
| `JavaCompiler.CompilationTask` | Đại diện một lần biên dịch | `call()` trả kết quả thành công/thất bại |

Chuỗi mã nguồn **không phải** tham số trực tiếp của `compiler.getTask(...)`. Ta phải bọc nội dung trong một hoặc nhiều đối tượng `JavaFileObject` để compiler biết: “đây là đơn vị nguồn Java tên gì, thuộc loại nào, và đọc các ký tự từ đâu”.

### Pipeline tổng quát

```text
String chứa mã Java
       |
       v
StringSource extends SimpleJavaFileObject
   - URI: string:///demo/Hello.java
   - Kind.SOURCE
   - getCharContent() -> String
       |
       v
JavaCompiler.getTask(...)
       |
       +---- DiagnosticCollector: lỗi / cảnh báo / vị trí
       |
       +---- StandardJavaFileManager: classpath, output
       |
       v
CompilationTask.call()
       |
       +---- false: có lỗi biên dịch
       |
       +---- true: biên dịch thành công
                 |
                 +---- (mặc định hoặc -d) .class trên đĩa
                 |
                 +---- (FileManager tùy chỉnh) bytecode trong RAM
```

Compiler có thể đọc nhiều đơn vị nguồn trong cùng một task: `List.of(sourceA, sourceB)`. Trong bài này, mỗi ví dụ bắt đầu với một file nguồn logic để thấy rõ quan hệ tên lớp và URI, rồi mới mở rộng.

## 2. Cấu trúc tối thiểu của StringSource

Mẫu cốt lõi:

```java
import java.net.URI;
import java.util.Objects;
import javax.tools.SimpleJavaFileObject;

public final class StringSource extends SimpleJavaFileObject {
    private final String content;

    public StringSource(String binaryName, String content) {
        super(URI.create("string:///" +
                binaryName.replace('.', '/') +
                Kind.SOURCE.extension), Kind.SOURCE);
        this.content = Objects.requireNonNull(content);
    }

    @Override
    public CharSequence getCharContent(boolean ignoreEncodingErrors) {
        return content;
    }
}
```

Lớp trên **không chứa `main`**; nó là một thành phần để dùng với `JavaCompiler`. Có thể lưu thành `StringSource.java` rồi biên dịch cùng chương trình sử dụng, hoặc định nghĩa như nested class trong ví dụ hoàn chỉnh ở phần sau.

Giải thích từng phần:

1. `extends SimpleJavaFileObject`: ta không tự triển khai mọi phương thức của `JavaFileObject`; lớp cơ sở đã cung cấp phần nền.
2. `URI.create("string:///...")`: tạo một **định danh logic**, không phải yêu cầu đọc từ mạng hay truy cập filesystem.
3. `binaryName.replace('.', '/')`: chuyển `demo.Hello` thành đường dẫn logic `demo/Hello`.
4. `Kind.SOURCE.extension`: tương đương chuỗi `.java`, tránh ghi cứng đuôi tệp.
5. `Kind.SOURCE`: báo đúng loại đối tượng đầu vào; nếu nhầm `Kind.CLASS`, trình biên dịch sẽ không xem đây là mã nguồn Java bình thường.
6. `getCharContent(...)`: cung cấp nội dung `String` cho compiler. Không có lời gọi `Files.readString` hay mở tệp `.java`.
7. `Objects.requireNonNull(content)`: làm rõ nội dung nguồn phải có giá trị; việc nhận chuỗi rỗng là một trường hợp khác mà compiler sẽ chẩn đoán dựa trên ngữ cảnh.

Tham số `ignoreEncodingErrors` tồn tại trong giao diện vì một số file manager đọc từ byte stream cần xử lý lỗi giải mã. Ở ví dụ này, nguồn đã là ký tự Java trong `String` nên **không cần giải mã byte**, và việc không sử dụng tham số là có chủ đích.

### Vì sao URI là string:///demo/Hello.java?

Giả sử tên nhị phân của lớp là `demo.Hello`:

```text
binaryName                       demo.Hello
binaryName.replace('.', '/')     demo/Hello
Kind.SOURCE.extension            .java
URI                              string:///demo/Hello.java
```

Dấu `///` thường được dùng để URI có path tuyệt đối. Scheme `string` là một **quy ước tùy chỉnh của ví dụ**, không phải giao thức HTTP, không làm compiler tự tải dữ liệu từ website, và không tạo file ở `/demo/Hello.java`.

Điều quan trọng là URI cho compiler một định danh **hợp lệ, ổn định, phân biệt được** giữa các nguồn. Với các code snippet từ người dùng, không nên ghép thẳng tên không tin cậy vào URI nếu chưa kiểm tra tên class và những ký tự cần escape. Ví dụ này giả định `binaryName` đã là tên Java binary name hợp lệ.

## 3. Mã nguồn và URI phải mô tả cùng đơn vị biên dịch

Giả sử source chứa:

```java
package demo;

public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello from String");
    }
}
```

Tên nhị phân của lớp public là `demo.Hello`. Khi tạo `StringSource`, ta dùng:

```java
new StringSource("demo.Hello", text)
```

Thông thường tên lớp `public` phải khớp tên đơn vị nguồn `Hello.java`; package `demo` nằm trong đoạn mã Java và tương ứng với đường dẫn logic `demo/Hello.java`.

Các sai lầm dễ gặp:

- Dùng `new StringSource("Hello", text)` trong khi source khai báo `package demo;`; cách đặt tên URI không phản ánh package, có thể gây lỗi ở các công cụ cần suy ra tên nhị phân.
- Dùng URI `string:///demo/Other.java` cho file chứa `public class Hello`; compiler có thể báo tên lớp public không khớp.
- Đưa một chuỗi chứa **nhiều lớp public top-level** vào một đơn vị nguồn duy nhất; quy tắc tên tệp Java vẫn cần được tôn trọng.
- Tạo hai `JavaFileObject` cùng URI/name cho hai nguồn khác nhau trong một task; compiler có thể gặp xung đột đơn vị biên dịch.

Một file nguồn có thể chứa thêm các top-level class **không public** theo quy tắc Java. Khi bài toán yêu cầu nhiều lớp public thuộc nhiều tệp, hãy tạo **nhiều StringSource** với các binary name tương ứng.

## 4. Ví dụ chạy được: String → compiler → class file → chạy class

Tạo file **`StringSourceDemo.java`** với nội dung đầy đủ sau. Ví dụ này chọn *đầu vào ở bộ nhớ* nhưng **đầu ra là class file trong một thư mục tạm** để dễ nhìn thấy pipeline.

```java
import java.net.URI;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class StringSourceDemo {
    static final class Source extends SimpleJavaFileObject {
        private final String source;

        Source(String binaryName, String text) {
            super(URI.create("string:///" +
                    binaryName.replace('.', '/') +
                    Kind.SOURCE.extension), Kind.SOURCE);
            this.source = Objects.requireNonNull(text);
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return source;
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Run this example with a JDK.");
        }

        String text = """
                package demo;
                public class Hello {
                    public static void main(String[] args) {
                        System.out.println("Hello from String");
                    }
                }
                """;

        Path classes = Files.createTempDirectory("string-classes-");
        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
                compiler.getStandardFileManager(
                    diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
            Boolean ok = compiler.getTask(
                    null,
                    manager,
                    diagnostics,
                    List.of("--release", "17", "-d", classes.toString()),
                    null,
                    List.of(new Source("demo.Hello", text))
            ).call();

            System.out.println("compiled=" + Boolean.TRUE.equals(ok));

            if (!Boolean.TRUE.equals(ok)) {
                for (Diagnostic<? extends JavaFileObject> item
                        : diagnostics.getDiagnostics()) {
                    System.err.println(item.getKind() + ": " +
                            item.getMessage(Locale.ROOT));
                }
                return;
            }
        }

        try (URLClassLoader loader = new URLClassLoader(
                new URL[] {classes.toUri().toURL()})) {
            Class<?> type = Class.forName("demo.Hello", true, loader);
            type.getMethod("main", String[].class)
                    .invoke(null, (Object) new String[0]);
        }
    }
}
```

Dùng terminal trong thư mục chứa `StringSourceDemo.java`, với JDK 17+:

```bash
javac --release 17 StringSourceDemo.java
java StringSourceDemo
```

Stdout **đã kiểm chứng bằng JDK 24 với `--release 17`**:

```text
compiled=true
Hello from String
```

Trình tự thực tế:

1. `javac --release 17 StringSourceDemo.java` biên dịch **chương trình host** cung cấp Java Compiler API, không phải biên dịch `demo.Hello`. Đây là bước chuẩn bị để chạy ví dụ.
2. `java StringSourceDemo` chạy host.
3. Host lấy compiler từ `ToolProvider`; tạo đối tượng `Source` mang URI `string:///demo/Hello.java` và String chứa code `demo.Hello`.
4. `compiler.getTask(...).call()` biên dịch nguồn do `getCharContent` trả về. `--release 17` giới hạn phiên bản ngôn ngữ/API/class target của lượt biên dịch này.
5. `-d classes.toString()` đưa `demo/Hello.class` vào thư mục tạm.
6. `URLClassLoader` nạp class được sinh từ thư mục ấy; reflection gọi `main` của `demo.Hello`.
7. Class `demo.Hello` in `Hello from String`.

**Phân biệt hai lượt compiler:** trình biên dịch shell tạo `StringSourceDemo.class`; sau đó JavaCompiler API bên trong chương trình host tạo `demo/Hello.class`. Nếu chỉ copy source snippet `demo.Hello` mà không dùng API thì không minh họa đúng bài toán.

### Vì sao dùng (Object) new String[0]?

Lời gọi:

```java
type.getMethod("main", String[].class)
    .invoke(null, (Object) new String[0]);
```

`Method.invoke` nhận `Object... args`. Ép `(Object)` giúp mảng `String[]` được truyền như **một tham số** cho `main(String[] args)`, thay vì dễ gây nhầm lẫn với cú pháp varargs của reflection. Vì `main` là static, receiver truyền vào `invoke` là `null`.

Trong hệ thống sản xuất, nạp/chạy code được biên dịch động có nhiều rủi ro hơn phần biên dịch: **không chạy mã Java không đáng tin cậy chỉ trong cùng JVM rồi kỳ vọng class loader bảo đảm sandbox an toàn**. `ClassLoader` là cơ chế nạp lớp, không phải ranh giới bảo mật đủ mạnh cho code từ người dùng không tin cậy.

### Tệp tạm có được xóa chưa?

Ví dụ dùng `Files.createTempDirectory(...)` và không xóa thư mục trong demo để tập trung vào quy trình. Khi triển khai thật, cần có chính sách quản lý vòng đời và xóa class file tạm an toàn sau khi các classloader liên quan đã không còn sử dụng, theo khả năng của hệ điều hành và runtime. Không xóa một thư mục khi chưa xác định chắc chắn đó là thư mục do chính ứng dụng tạo.

## 5. Tạo diagnostic có file, dòng và cột dù nguồn là String

Lợi ích quan trọng của `JavaFileObject` là compiler có thể tạo error/warning **gắn với một URI logic** ngay cả khi nguồn không tồn tại trên đĩa. Dùng `DiagnosticCollector<JavaFileObject>` để thu diagnostics có cấu trúc.

Tạo file **`StringSourceErrorDemo.java`**:

```java
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Locale;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class StringSourceErrorDemo {
    static final class Source extends SimpleJavaFileObject {
        private final String content;

        Source(String binaryName, String content) {
            super(URI.create("string:///" +
                    binaryName.replace('.', '/') +
                    Kind.SOURCE.extension), Kind.SOURCE);
            this.content = content;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return content;
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler javac = ToolProvider.getSystemJavaCompiler();
        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        String broken = """
                package demo;
                public class Broken {
                    int number = "not an int";
                }
                """;

        try (StandardJavaFileManager files =
                javac.getStandardFileManager(
                    diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
            boolean passed = javac.getTask(
                    null,
                    files,
                    diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null,
                    List.of(new Source("demo.Broken", broken))
            ).call();

            System.out.println("compiled=" + passed);
        }

        for (Diagnostic<? extends JavaFileObject> issue
                : diagnostics.getDiagnostics()) {
            if (issue.getKind() == Diagnostic.Kind.ERROR) {
                System.out.println("kind=" + issue.getKind());
                System.out.println("source=" + issue.getSource().toUri());
                System.out.println("line=" + issue.getLineNumber());
                System.out.println("column=" + issue.getColumnNumber());
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 StringSourceErrorDemo.java
java StringSourceErrorDemo
```

Stdout của ví dụ **đã kiểm chứng trên JDK 24**:

```text
compiled=false
kind=ERROR
source=string:///demo/Broken.java
line=3
column=18
```

Kết quả cho thấy:

- Không có file `demo/Broken.java` thật; URI `string:///demo/Broken.java` do chính constructor `Source` cung cấp.
- Compiler tìm được lỗi gán literal `String` cho field kiểu `int`.
- `Diagnostic.Kind.ERROR` xác định mức lỗi của chính Java compiler; người viết code không cần parse chuỗi stderr.
- `getSource().toUri()` liên kết diagnostic với **đơn vị nguồn logic**.
- `getLineNumber()` và `getColumnNumber()` trả vị trí trên source cho lỗi cụ thể. Với diagnostic không gắn vị trí, API có thể trả `Diagnostic.NOPOS` (giá trị `-1`).
- Vì ví dụ cố ý chứa lỗi nguồn, `CompilationTask.call()` trả `false`, nhưng **chương trình host** vẫn hoàn thành bình thường, nên lệnh `java StringSourceErrorDemo` có thể có exit code 0. Đừng nhầm exit code của host với kết quả biên dịch động được in trong `compiled=false`.

**Vị trí 3:18 là của đúng đoạn source đã cho và compiler đã kiểm thử**, không phải cam kết mọi lỗi/mọi JDK luôn báo ở cột 18. Các warning khác có thể có source hoặc vị trí không xác định.

### Cần hiện thông điệp compiler cho người dùng?

Có thể dùng:

```java
for (Diagnostic<? extends JavaFileObject> diagnostic
        : diagnostics.getDiagnostics()) {
    System.err.println(
        diagnostic.getKind() + " at " +
        diagnostic.getLineNumber() + ":" +
        diagnostic.getColumnNumber() + " - " +
        diagnostic.getMessage(Locale.ROOT));
}
```

Đây là **mảnh code minh họa**, giả định biến `diagnostics` đã được tạo từ chương trình đầy đủ. Chỉ dùng số dòng/cột khi khác `Diagnostic.NOPOS`. Khi làm editor nhiều tab, ánh xạ URI nguồn vào tab tương ứng để người dùng có thể nhảy đến vị trí lỗi.

## 6. Source từ String và output class không nhất thiết đều ở RAM

Tên chương “biên dịch trong bộ nhớ” đôi khi khiến người học tưởng chỉ cần tạo `SimpleJavaFileObject` là xong toàn bộ. Thực tế có hai chiều I/O:

```text
ĐẦU VÀO                             ĐẦU RA
String chứa mã Java                 class bytes
   |                                   |
   v                                   v
JavaFileObject.Kind.SOURCE       JavaFileObject.Kind.CLASS
   |                                   |
getCharContent()                  openOutputStream()
   |                                   |
   +----------- JavaCompiler ----------+
                       |
                       +-- StandardJavaFileManager -> filesystem
                       |
                       +-- JavaFileManager tùy chỉnh -> ByteArrayOutputStream
```

Trong `StringSourceDemo`, nguồn đến từ `String` nhưng output đi qua `StandardJavaFileManager` với `-d`, tạo `.class` trên đĩa. Muốn **compiler hoàn toàn không ghi bytecode ra đĩa**, ta cần can thiệp đầu ra qua `JavaFileManager.getJavaFileForOutput(...)`.

Đó là phần mở rộng kỹ thuật hợp lý của bài học, **không phải yêu cầu bắt buộc của SimpleJavaFileObject nguồn**. Việc quản lý in-memory class output là một vai trò riêng, nên không cố đưa `openOutputStream` vào cùng object `Kind.SOURCE` rồi hi vọng compiler ghi class vào source object ấy.

## 7. Ví dụ nâng cao: cả nguồn và bytecode đều trong bộ nhớ

Tạo file **`FullyMemoryDemo.java`**. Ví dụ gồm bốn thành phần:

1. `Source`: như trước, chứa String và có `Kind.SOURCE`.
2. `Output`: một `SimpleJavaFileObject` có `Kind.CLASS`, ghi dữ liệu vào `ByteArrayOutputStream`.
3. `MemoryFiles`: bọc `StandardJavaFileManager`, chặn output class từ compiler để lưu trong Map.
4. `ClassLoader`: nạp bytecode `byte[]` vừa tạo và gọi một phương thức mẫu.

```java
import java.io.ByteArrayOutputStream;
import java.io.OutputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileManager;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class FullyMemoryDemo {
    static final class Source extends SimpleJavaFileObject {
        private final String content;

        Source(String name, String content) {
            super(URI.create("string:///" + name.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.content = content;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return content;
        }
    }

    static final class Output extends SimpleJavaFileObject {
        private final ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        Output(String name, Kind kind) {
            super(URI.create("mem:///" + name.replace('.', '/')
                    + kind.extension), kind);
        }

        @Override
        public OutputStream openOutputStream() {
            return bytes;
        }

        byte[] content() {
            return bytes.toByteArray();
        }
    }

    static final class MemoryFiles
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        final Map<String, Output> classes = new HashMap<>();

        MemoryFiles(StandardJavaFileManager delegate) {
            super(delegate);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location,
                String className, JavaFileObject.Kind kind,
                FileObject sibling) throws java.io.IOException {
            if (kind != JavaFileObject.Kind.CLASS) {
                return super.getJavaFileForOutput(
                        location, className, kind, sibling);
            }
            Output output = new Output(className, kind);
            classes.put(className, output);
            return output;
        }
    }

    public static void main(String[] args) throws Exception {
        String source = """
                package demo;
                public class InMemory {
                    public static int sum(int x, int y) {
                        return x + y;
                    }
                }
                """;

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        DiagnosticCollector<JavaFileObject> issues = new DiagnosticCollector<>();

        try (StandardJavaFileManager standard =
                compiler.getStandardFileManager(
                    issues, Locale.ROOT, StandardCharsets.UTF_8);
             MemoryFiles memory = new MemoryFiles(standard)) {
            boolean ok = compiler.getTask(
                    null,
                    memory,
                    issues,
                    List.of("--release", "17", "-proc:none"),
                    null,
                    List.of(new Source("demo.InMemory", source))
            ).call();

            System.out.println("compiled=" + ok);
            if (!ok) {
                return;
            }

            ClassLoader loader =
                    new ClassLoader(FullyMemoryDemo.class.getClassLoader()) {
                        @Override
                        protected Class<?> findClass(String name)
                                throws ClassNotFoundException {
                            Output output = memory.classes.get(name);
                            if (output == null) {
                                throw new ClassNotFoundException(name);
                            }
                            byte[] bytes = output.content();
                            return defineClass(name, bytes, 0, bytes.length);
                        }
                    };

            Class<?> type = loader.loadClass("demo.InMemory");
            Object result = type.getMethod(
                    "sum", int.class, int.class).invoke(null, 7, 8);
            System.out.println("result=" + result);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 FullyMemoryDemo.java
java FullyMemoryDemo
```

Stdout đã được **kiểm chứng trên JDK 24**:

```text
compiled=true
result=15
```

Không có `-d` trong **lệnh biên dịch động bên trong ứng dụng**; compiler gọi `MemoryFiles.getJavaFileForOutput` và nhận đối tượng `Output`. Khi ghi class file, compiler dùng `openOutputStream`, vì vậy bytecode được giữ trong `ByteArrayOutputStream` thay vì tạo `demo/InMemory.class` từ lần biên dịch động.

**Phạm vi của tuyên bố “hoàn toàn trong bộ nhớ”:** đó là **nguồn `demo.InMemory` và các bytecode của lần biên dịch động**. File `FullyMemoryDemo.java` và class file của **chương trình host** vẫn được tạo từ lệnh `javac FullyMemoryDemo.java` ở ngoài. File manager tiêu chuẩn vẫn có thể đọc thư viện/JDK/classpath; đây không phải một cơ chế ngăn mọi I/O của toàn JVM.

### Vì sao cần Map theo binary name?

Khi compiler phát sinh nhiều lớp (chẳng hạn inner class hoặc các lớp từ nhiều nguồn), mỗi output có **binary name riêng**. `Map<String, Output>` giữ bytecode tương ứng để class loader tìm được theo tên. Nếu chỉ giữ một `ByteArrayOutputStream` dùng chung cho mọi output, nhiều class file có thể ghi đè/lẫn dữ liệu.

Trong production, có thể còn phải xử lý tài nguyên generated by annotation processors, concurrency, package resolution và tên module. Ví dụ trên chứng minh nguyên lý **capture class output**, không tự động trở thành một compiler server hỗ trợ mọi kiểu build.

### Class loader của ví dụ có phải sandbox?

**Không.** `ClassLoader.defineClass` là cơ chế định nghĩa class trong JVM, không giới hạn mọi hành động có thể thực hiện bởi code được nạp. Nếu nguồn đến từ người dùng không tin cậy, cần **cách ly process/container/VM**, giới hạn tài nguyên và quyền theo mô hình bảo mật phù hợp. Đừng dùng một custom class loader như ranh giới bảo mật duy nhất.

## 8. Tại sao không dùng Files.readString hoặc getJavaFileObjectsFromStrings?

Hai cách có mục tiêu khác nhau:

```java
String sourceText = "public class A {}";
```

`sourceText` là **nội dung mã Java**. Nhưng API:

```java
fileManager.getJavaFileObjectsFromStrings(
    java.util.List.of("A.java"));
```

nhận **tên file/đường dẫn** theo hợp đồng của file manager tiêu chuẩn, không nhận nội dung mã Java thuần từ chuỗi. Nếu bạn truyền `"public class A {}"` vào danh sách ấy, tool có thể hiểu đó là **tên đường dẫn kỳ lạ**, không phải một source unit.

Dùng `StandardJavaFileManager` để đọc file đã có trên đĩa là hoàn toàn đúng khi mục tiêu là compile file. Dùng `SimpleJavaFileObject + getCharContent` phù hợp khi **nguồn chỉ nằm trong String** hoặc được tổng hợp trong RAM.

Còn `Files.readString(path)` là API để đọc từ một tệp thực; dùng nó trước khi tạo `StringSource` vẫn hoạt động, nhưng **không có lợi nếu nguồn đã sẵn trong bộ nhớ**. Cần chọn phương pháp theo nguồn dữ liệu thật.

## 9. Nhiều StringSource trong một CompilationTask

Giả sử có hai đơn vị nguồn:

```java
String utilCode = """
        package demo;
        public class Util {
            public static int doubleOf(int n) {
                return n * 2;
            }
        }
        """;

String mainCode = """
        package demo;
        public class UseUtil {
            public static void main(String[] args) {
                System.out.println(Util.doubleOf(5));
            }
        }
        """;
```

Đây là **hai đoạn khai báo String minh họa** bên trong một method Java 17+, không phải một chương trình độc lập. Khi đã có class `Source` của phần trên, có thể truyền:

```java
List.of(
    new Source("demo.Util", utilCode),
    new Source("demo.UseUtil", mainCode)
)
```

vào tham số `compilationUnits` của `compiler.getTask(...)`. Compiler biết cả hai đơn vị nguồn trong cùng task và có thể giải quyết tham chiếu `Util` từ `UseUtil` mà không cần tạo hai file `.java` trước đó.

Nếu ghi class ra ổ đĩa bằng `-d out` rồi chạy `java -cp out demo.UseUtil`, stdout sẽ là:

```text
10
```

**Quan trọng:** ví dụ nhiều source phía trên là các mảnh code để **chèn vào một host JavaCompiler API phù hợp**; không phải lệnh shell độc lập. Đừng nhầm việc có một `List.of(...)` hợp lệ với một chương trình đầy đủ có `main`.

### Mỗi source phải có URI riêng

Dù hai class cùng package `demo`, hai URI vẫn là:

```text
string:///demo/Util.java
string:///demo/UseUtil.java
```

Không gán chung `string:///demo/Source.java` cho cả hai rồi mong compiler tự suy ra tất cả từ nội dung. URI mô tả **đơn vị nguồn**, không chỉ package.

## 10. DiagnosticCollector, Charset và vị trí lỗi

Vì `getCharContent` trả `CharSequence` đã giải mã, tham số `Charset` của `getStandardFileManager(...)` **không tự mã hóa lại String nguồn của `Source`**. Nó vẫn hữu ích với các file thật do standard manager đọc và các thao tác file liên quan.

Ví dụ:

```java
compiler.getStandardFileManager(
    diagnostics, Locale.ROOT, StandardCharsets.UTF_8);
```

- `Locale.ROOT` giúp output diagnostic được lựa chọn theo locale trung lập khi API hỗ trợ.
- `StandardCharsets.UTF_8` quy định charset dùng trong file manager tiêu chuẩn; không phải “convert mọi String thành UTF-8” vì String trong JVM đã ở dạng ký tự.
- `DiagnosticCollector` thu danh sách chẩn đoán, hỗ trợ mức `ERROR/WARNING/NOTE`, URI, dòng, cột, mã diagnostic và message.

Có thể kiểm tra thêm:

```java
long line = issue.getLineNumber();
long column = issue.getColumnNumber();
String code = issue.getCode();
String message = issue.getMessage(Locale.ROOT);
```

Đây là đoạn minh họa bên trong vòng lặp có biến `issue` kiểu `Diagnostic<? extends JavaFileObject>`. Mã diagnostic nội bộ và văn bản message có thể khác giữa JDK/vendor; hãy dựa vào `Kind`, source URI, vị trí và chính sách kiểm thử thay vì cố hard-code một câu tiếng Anh.

Một diagnostic không gắn vào source cụ thể có thể có `getSource() == null`, vì vậy **kiểm tra null trước khi gọi `toUri()`** trong chương trình tổng quát. Bài `StringSourceErrorDemo` có nguồn tương ứng nên `getSource()` không null trong trường hợp đã kiểm chứng.

## 11. JavaCompiler.CompilationTask: tham số nào dễ nhầm?

Chữ ký thường gặp:

```java
JavaCompiler.CompilationTask getTask(
    java.io.Writer out,
    JavaFileManager fileManager,
    DiagnosticListener<? super JavaFileObject> diagnosticListener,
    Iterable<String> options,
    Iterable<String> classes,
    Iterable<? extends JavaFileObject> compilationUnits
);
```

Chữ ký trên được viết lại để giải thích API, không cần chép vào source.

Ý nghĩa thực hành:

1. `out` là nơi ghi một số output bổ sung của compiler theo công cụ; truyền `null` trong demo để dùng mặc định.
2. `fileManager` điều phối đường tìm input/output; có thể là standard manager hoặc `ForwardingJavaFileManager` của bạn.
3. `diagnosticListener` nhận diagnostic có cấu trúc; `DiagnosticCollector` là implementation tiện lợi.
4. `options` là danh sách từng argument của compiler, ví dụ `List.of("--release", "17", "-d", classes.toString())`.
5. `classes` dùng cho những tên class cần xử lý theo các chế độ liên quan; các demo biên dịch source units trực tiếp nên truyền `null`.
6. `compilationUnits` là collection `JavaFileObject` chứa các source đơn vị.

**Không nhầm thứ tự `options` và `compilationUnits`.** Những chuỗi như `"--release"`, `"17"` là *compiler options*, còn nội dung `"public class..."` phải nằm trong `Source.getCharContent`.

### Mỗi task nên có mục đích và vòng đời rõ

`CompilationTask.call()` chỉ nên được gọi một lần cho một task. Nếu muốn biên dịch code mới, tạo task mới và cung cấp lại source units/diagnostics phù hợp; không giữ một task rồi gọi `call()` lặp lại như một service endpoint. Việc tái sử dụng compiler instance hoặc file manager phải tuân theo tài liệu API, không suy ra thread safety chung từ một ví dụ chạy đơn luồng.

Quản lý `StandardJavaFileManager` bằng try-with-resources như các ví dụ giúp giải phóng tài nguyên. Với custom forwarding manager, quyết định đóng cả wrapper và delegate cần được thực hiện rõ; ví dụ `FullyMemoryDemo` đóng hai resource có thứ tự, phù hợp cho phép thử đã chạy.

## 12. Classpath, annotation processors và modules vẫn quan trọng

Nguồn từ `String` **không bỏ qua hệ thống phân giải type**. Nếu mã chứa `import com.example.Service;`, compiler vẫn cần tìm thư viện cung cấp class đó.

Ví dụ compiler option cho thư viện bên ngoài:

```java
List.of(
    "--release", "17",
    "-classpath", "libs/example.jar",
    "-d", output.toString()
)
```

Đây là danh sách options minh họa, cần file JAR thật nếu muốn compile mã phụ thuộc. Compiler không tự truy cập Internet hay tải dependency khi thấy `import`.

Một số lưu ý:

- Nếu compile code thuộc một **named module**, cần cân nhắc `module-info.java`, `--module-path` và mô hình module, không chỉ thay classpath.
- Annotation processing có thể được bật, tắt hoặc cấu hình tùy toolchain. Nếu bạn cần chỉ kiểm tra source mà không chạy processor bên ngoài, dùng `-proc:none` khi phù hợp với JDK.
- Nếu chủ đích chạy processor, cấu hình `-processor`, `-processorpath` hoặc processor module path tương ứng, cùng dependency của processor.
- Đừng coi URI scheme `string` là đường dẫn module path hoặc filesystem; đó chỉ là định danh của JavaFileObject input.
- Class output trong bộ nhớ không có nghĩa class phụ thuộc cũng ở bộ nhớ: compiler có thể vẫn đọc classpath/module path từ disk hoặc runtime image.

Trong hệ thống lớn, sự khác biệt giữa **tên class**, **URI source**, **class loader ở runtime** và **tên module** có thể làm phát sinh lỗi khó debug; ghi log đúng lớp thông tin thay vì chỉ lưu chuỗi source.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `getSystemJavaCompiler()` trả `null` | Ứng dụng chạy trong môi trường không có system Java compiler | Chạy bằng JDK có module `jdk.compiler`, kiểm tra runtime image |
| Không tìm được đơn vị nguồn | Truyền String trực tiếp thay vì `JavaFileObject` hoặc URI/Kind không hợp lệ | Đảm bảo `Kind.SOURCE` và `getCharContent` |
| `public class Hello` báo không khớp file | URI/name không tương thích tên public class | Dùng tên logic `demo.Hello` -> `string:///demo/Hello.java` |
| Nguồn có `package demo` nhưng tham chiếu không được resolve | Binary name/URI không khớp hoặc thiếu nguồn/phụ thuộc | Xác minh URI và danh sách compilation units |
| `compiled=false` nhưng host exit code vẫn 0 | Task trả thất bại, host không tự `System.exit` | Đọc Boolean result và diagnostics |
| `getSource()` null gây `NullPointerException` | Diagnostic không có source cụ thể | Kiểm tra null trước `toUri()` |
| Không thấy `.class` trong thư mục mong đợi | Output path sai, manager tùy chỉnh giữ bytecode hoặc `-proc:only` | Xác minh `-d`, file manager, task mode |
| Lệnh compile thành công nhưng classloader không tìm thấy class | Class output chưa nằm ở URL/classloader tương ứng | Kiểm tra đường dẫn package/class và loader |
| Class được compile nhưng không chạy vì lỗi dependency | Runtime thiếu class hoặc module cần thiết | Kiểm tra classpath/module path của runtime độc lập |
| Bytecode từ nhiều class bị ghi đè | Chỉ dùng một buffer thay vì map theo binary name | Sử dụng mỗi output object cho một class |
| Lỗi encoding dù source là String | Đoạn code tạo String sai hoặc file phụ thuộc dùng charset khác | Kiểm tra nguồn tạo String và file manager |
| Biên dịch nhiều lần gây rò rỉ RAM | Giữ lại bytecode, source, diagnostics, class loader quá lâu | Đặt giới hạn/vòng đời và giải phóng tham chiếu |

**Đừng sửa sai loại lỗi:** sai URI không phải vấn đề classloader nếu `javac` chưa compile thành công; ngược lại, compile thành công nhưng `ClassNotFoundException` khi nạp động là vấn đề ở runtime loader/đầu ra, không phải `getCharContent`.

## 14. Hiệu năng, giới hạn và bảo mật

Biên dịch code từ bộ nhớ có thể giảm nhu cầu tạo tệp `.java` tạm, nhưng **không bảo đảm nhanh hơn mọi trường hợp**. `JavaCompiler` vẫn phải parse/type-check/emit bytecode, có thể truy cập JDK và thư viện, tạo diagnostics, và tiêu thụ CPU/RAM. Tái sử dụng các cấu trúc compiler phải tuân thủ hợp đồng tài nguyên và vòng đời.

Những điểm cần chủ động kiểm soát:

- **Giới hạn kích thước source:** tránh nhận chuỗi không giới hạn làm cạn heap.
- **Giới hạn thời gian CPU/bộ nhớ:** một input có thể làm compiler/processor dùng nhiều tài nguyên; API không tự cung cấp sandbox.
- **Tránh chạy code không tin cậy trong cùng process:** custom classloader và `-proc:none` không thay thế cách ly hệ thống.
- **Không tải processor tùy ý của nguồn không tin cậy:** annotation processors có thể là code thực thi trong compiler process; cần quản lý processor path.
- **Quản lý diagnostics:** không trả về log nội bộ hoặc đường dẫn nhạy cảm ngoài ý muốn.
- **ClassLoader lifecycle:** bytecode đã nạp có thể tồn tại khi còn tham chiếu tới classloader, class hoặc object; clear map không đồng nghĩa giải phóng ngay mọi class runtime.
- **Tài nguyên tạm:** nếu dùng thư mục output, theo dõi và xóa đúng thư mục do mình tạo, tránh làm ảnh hưởng dữ liệu ngoài phạm vi.

Một hệ thống “chạy Java online” phải có kiến trúc cách ly phù hợp. Bài này **chỉ dạy cách biểu diễn nguồn và gọi compiler**, không cung cấp bảo đảm bảo mật cho việc thi hành mã của người dùng.

## 15. Bài tập thực hành

### Bài 1 — Nhận diện JavaFileObject

Một class `Source` giữ `String` mã Java và muốn compiler đọc mã đó. Cần constructor và override gì?

**Đáp án:** Tạo `SimpleJavaFileObject` với URI logic của đơn vị nguồn và `Kind.SOURCE`; override `getCharContent(boolean)` trả `CharSequence` chứa mã. Không tự động cần `openOutputStream` trên source object.

### Bài 2 — Tên source và package

Source chứa `package shop; public class Product {}`. URI phù hợp với tên nhị phân nào?

**Đáp án:** `shop.Product` và một URI logic như `string:///shop/Product.java`. Không dùng `shop/Other.java` cho public class Product.

### Bài 3 — Lỗi nằm ở dòng nào?

Tại sao `DiagnosticCollector` có thể in `string:///demo/Broken.java` dù file này không tồn tại trên filesystem?

**Đáp án:** Vì `JavaFileObject.toUri()` được cung cấp bởi đối tượng nguồn; compiler liên kết diagnostic với chính JavaFileObject ấy. `getCharContent` cung cấp ký tự thực, không cần file vật lý.

### Bài 4 — Compile thành công nhưng không có file đích

Lần biên dịch động dùng custom `MemoryFiles` và map bytecode. Không thấy `demo/InMemory.class` trên disk, có phải compiler thất bại?

**Đáp án:** Không. `CompilationTask.call()` có thể trả `true`; bytecode được ghi vào `ByteArrayOutputStream` của `Output`, không phải filesystem.

### Bài 5 — Sai ngữ nghĩa của getJavaFileObjectsFromStrings

Người học viết `fileManager.getJavaFileObjectsFromStrings(List.of("public class A {}"))`. Tại sao sai mục tiêu?

**Đáp án:** Method của standard file manager nhận **tên file**, không nhận source code string. Cần tạo `StringSource("A", "public class A {}")` rồi đưa vào compilation units.

### Bài 6 — Vì sao compiled=false không làm host lỗi?

Host in `compiled=false` nhưng lệnh `java StringSourceErrorDemo` trả exit code 0. Có bất thường không?

**Đáp án:** Không. Compiler task và host application là hai lớp kết quả. Nếu host cần báo build thất bại ra shell/CI, hãy quyết định exit code của host một cách tường minh.

### Bài 7 — Diagnostic không có source

Nếu một diagnostic có `getSource() == null`, điều gì xảy ra khi gọi `issue.getSource().toUri()`?

**Đáp án:** `NullPointerException`. Chỉ đọc URI khi có source; dùng `Diagnostic.NOPOS` để nhận biết trường hợp không có line/column.

### Bài 8 — Giữ code hoàn toàn trong RAM

Chỉ override `Source.getCharContent` có đủ để giữ bytecode trong RAM không?

**Đáp án:** Không. Cần cung cấp file manager có khả năng tạo đối tượng output `Kind.CLASS` với `openOutputStream()` ghi vào buffer, sau đó quản lý class bytes và loader nếu cần chạy.

### Bài 9 — Chạy code bên ngoài có an toàn không?

Compiler source String và load bằng `ClassLoader.defineClass` có bảo đảm ngăn code đọc file hoặc tạo network connections không?

**Đáp án:** Không. ClassLoader không phải sandbox bảo mật đầy đủ. Cần môi trường cách ly và policy quản lý tài nguyên phù hợp cho nguồn không tin cậy.

## 16. Checklist khi viết StringSource thật

- [ ] `getSystemJavaCompiler()` không phải `null`.
- [ ] `StringSource` có URI hợp lệ, duy nhất và `Kind.SOURCE`.
- [ ] URI phản ánh tên nhị phân/package của top-level public type.
- [ ] `getCharContent(boolean)` trả mã Java đã được tạo đúng.
- [ ] Mỗi source unit trong task có định danh riêng.
- [ ] `getTask(...)` nhận đúng thứ tự tham số và tập `compilationUnits`.
- [ ] Options có cấu trúc đúng từng argument, ví dụ `"--release", "17"`.
- [ ] Có `DiagnosticCollector` để xử lý lỗi/warning và vị trí nguồn.
- [ ] Đọc Boolean/Boolean.TRUE.equals của `call()` trước khi nạp class.
- [ ] Phân biệt file manager tiêu chuẩn và custom manager cho bytecode in-memory.
- [ ] Đóng file manager và classloader khi phù hợp.
- [ ] Nếu dùng classloader riêng, phân biệt runtime classpath và classpath của compiler.
- [ ] Không giả định host exit code trùng với kết quả dynamic compilation.
- [ ] Không thực thi mã không tin cậy trong host JVM mà không có biện pháp cách ly.

## 17. Kết luận và tài liệu chính thống

**`SimpleJavaFileObject` là cầu nối giữa một chuỗi ký tự trong JVM và đầu vào trừu tượng mà `JavaCompiler` có thể biên dịch.** Ba yếu tố cốt lõi là **URI định danh đơn vị nguồn**, **`Kind.SOURCE`**, và **`getCharContent(boolean)`** trả nội dung String. Từ đó `JavaCompiler.getTask(...)` thực hiện type checking và phát sinh class file; `DiagnosticCollector` cho phép liên kết lỗi/cảnh báo với URI và vị trí source dù không có file thật.

Nếu muốn toàn bộ **bytecode đầu ra ở trong RAM**, phải mở rộng thêm `JavaFileManager`/`SimpleJavaFileObject` đầu ra, không chỉ thay đổi source object. Việc load/run class cần xử lý riêng và không phải là cơ chế bảo mật cho code không tin cậy.

Tài liệu tham khảo:

1. [Java SE 17 — SimpleJavaFileObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html): constructor `(URI, Kind)` và các method cần override.
2. [Java SE 17 — JavaFileObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaFileObject.html): `Kind.SOURCE`, `Kind.CLASS` và giao diện source/class.
3. [Java SE 17 — JavaCompiler](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html): `getTask`, standard file manager và compilation units.
4. [Java SE 17 — ToolProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html): lấy system Java compiler.
5. [Java SE 17 — DiagnosticCollector](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/DiagnosticCollector.html): thu nhận chẩn đoán có cấu trúc.
6. [Java SE 17 — ForwardingJavaFileManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ForwardingJavaFileManager.html): bọc và tùy chỉnh cơ chế tìm/ghi file của compiler.

Khi debug một bài toán compile source String, hãy kiểm tra theo thứ tự: **tên và URI nguồn → `getCharContent` → compilation units/options → diagnostic → file manager/output → class loader**. Cách chia các tầng rõ ràng giúp tìm được lỗi thật thay vì nhầm lẫn giữa mã nguồn, bytecode và runtime.
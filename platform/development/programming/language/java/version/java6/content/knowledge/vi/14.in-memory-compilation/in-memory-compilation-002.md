# ForwardingJavaFileManager và chặn đầu ra class khi biên dịch trong bộ nhớ

## Mục tiêu

Khi ứng dụng dùng Java Compiler API để biên dịch một chuỗi mã Java, việc đặt **mã nguồn** trong RAM chưa đủ để gọi là **biên dịch hoàn toàn trong bộ nhớ**. Nếu vẫn dùng file manager tiêu chuẩn mà không xử lý đầu ra, trình biên dịch có thể ghi `.class` xuống ổ đĩa. Muốn nhận bytecode dưới dạng `byte[]` để lưu trữ, kiểm thử, nạp class hoặc chuyển sang bước xử lý khác, ứng dụng cần **chặn nơi compiler yêu cầu ghi class file**.

`ForwardingJavaFileManager<M extends JavaFileManager>` trong `javax.tools` giải quyết việc này: nó **ủy quyền (delegate)** hầu hết hoạt động của `JavaFileManager` cho manager nền, đồng thời cho phép override đúng phương thức cần thay đổi. Đối với class bytecode, điểm chặn chính là `getJavaFileForOutput(...)`.

Bài học thuộc nhóm **Biên dịch trong bộ nhớ** và tập trung vào cách kết hợp:

- `ToolProvider.getSystemJavaCompiler()` và `JavaCompiler.CompilationTask` để biên dịch trong cùng tiến trình JVM.
- `StandardJavaFileManager` để giữ cơ chế phân giải thư viện, platform classes, classpath/module path bình thường.
- `ForwardingJavaFileManager` để chuyển yêu cầu ghi `JavaFileObject.Kind.CLASS` tại `StandardLocation.CLASS_OUTPUT` sang vùng nhớ.
- `SimpleJavaFileObject` và `ByteArrayOutputStream` để nhận từng class file.
- `DiagnosticCollector` để thu thập lỗi thay vì âm thầm kết luận biên dịch thành công.
- Một `ClassLoader` riêng khi cần **sử dụng** bytecode đã biên dịch.

Ví dụ độc lập sử dụng **Java 17 trở lên**, là API còn được hỗ trợ trong các JDK hiện hành. Không dựa vào class nội bộ `com.sun.tools.javac.*`, đường dẫn tạm bị hard-code, hoặc API cũ đã lỗi thời.

## 1. Vì sao chặn đầu ra class?

### 1.1. Mã nguồn trong RAM không đồng nghĩa bytecode ở RAM

Ví dụ:

```java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();

JavaFileObject source = /* một SOURCE object được tạo từ String */;
JavaCompiler.CompilationTask task = compiler.getTask(
        null, standardFileManager, diagnostics,
        List.of("--release", "17"), null, List.of(source));

Boolean success = task.call();
```

*Đây là mã minh họa; `standardFileManager`, `diagnostics` và `source` phải được khởi tạo.* Một `JavaFileObject` nguồn tùy biến có thể đọc nội dung từ `String`, nhưng đối tượng `standardFileManager` vẫn quản lý cách tạo sản phẩm đầu ra. Nếu không chuyển hướng việc ghi class, Java compiler có thể tạo `.class` ở vị trí output tương ứng của nó trên filesystem.

Luồng xử lý khi **chặn đầu ra**:

```text
String chứa Java source
   │
   ▼
SimpleJavaFileObject (Kind.SOURCE)
   │    getCharContent(...)
   ▼
JavaCompiler.getTask(...).call()
   │
   ├── hỏi JavaFileManager về classpath, module path, dependency...
   │         │
   │         ▼
   │    ForwardingJavaFileManager
   │         └── delegate đến StandardJavaFileManager
   │
   └── yêu cầu JavaFileObject cho output .class
              │
              ▼
       getJavaFileForOutput(...)
              │
              ├─ CLASS_OUTPUT + Kind.CLASS
              │      └─ BytecodeFile (Kind.CLASS)
              │             └─ openOutputStream()
              │                    └─ ByteArrayOutputStream
              │                           └─ byte[] theo binary class name
              │
              └─ các yêu cầu không chặn
                     └─ delegate đến manager nền
```

Lợi ích cốt lõi: **chỉ thay cách ghi những class output cần kiểm soát**, còn phần còn lại của hệ thống compiler tiếp tục dựa trên manager tiêu chuẩn. Đây là cách tận dụng khả năng sẵn có của JDK mà không phải tự xây toàn bộ file manager.

### 1.2. Phân biệt bốn đối tượng

| Thành phần | Trách nhiệm |
| --- | --- |
| `JavaCompiler` | Tạo và chạy compilation task. |
| `JavaFileManager` | Giao diện trừu tượng tìm nguồn, đọc dependency, yêu cầu file đầu ra. |
| `StandardJavaFileManager` | Implementation tiêu chuẩn cho filesystem, JAR, classpath và module locations. |
| `ForwardingJavaFileManager` | Wrapper ủy quyền; có thể đổi hành vi chọn lọc như tạo file object đầu ra. |
| `JavaFileObject` | Mô tả **một** source/class file, cung cấp phương thức đọc hoặc ghi thực tế. |

`ForwardingJavaFileManager` không tự tạo vùng nhớ để ghi. Muốn chặn đầu ra thật sự, nó phải trả về một `JavaFileObject` có `openOutputStream()` ghi vào bộ đệm byte.

## 2. Tại sao dùng forwarding thay vì thay thế toàn bộ file manager?

`StandardJavaFileManager` thường được tạo qua:

```java
StandardJavaFileManager standard =
        compiler.getStandardFileManager(
                diagnostics, Locale.ROOT, StandardCharsets.UTF_8);
```

JDK cung cấp **đối tượng đã cấu hình** chứ không yêu cầu ứng dụng kế thừa class implementation của nó. Java Compiler API khuyến nghị mô hình wrapper `ForwardingJavaFileManager`, tương tự ý tưởng decorator/delegation:

```java
final class CapturingFileManager
        extends ForwardingJavaFileManager<StandardJavaFileManager> {

    CapturingFileManager(StandardJavaFileManager standard) {
        super(standard);
    }

    // Override đúng điểm chặn cần thiết.
}
```

Phần lớn các lời gọi khác, chẳng hạn tìm class trên classpath, truy vấn location hoặc đóng manager, sẽ được forwarding manager chuyển đến manager nền. Điều đó giúp giữ hành vi chuẩn khi giải quyết dependency và module.

Có thể so sánh:

- **Kế thừa một implementation javac nội bộ:** phụ thuộc chi tiết không thuộc Java Compiler API công khai; không nên dùng.
- **Tự triển khai đầy đủ `JavaFileManager`:** phải xử lý nhiều loại location, module, input, output và lifecycle; phức tạp khi chỉ muốn chặn `.class`.
- **`ForwardingJavaFileManager`:** chỉ override những hoạt động cần chuyển hướng và delegate mọi trường hợp khác.

Wrapper không tự làm manager hoặc bản đồ bytecode an toàn đa luồng. Thiết kế vòng đời và ownership vẫn là trách nhiệm của ứng dụng.

## 3. Điểm chặn quan trọng: `getJavaFileForOutput(...)`

Hợp đồng của `JavaFileManager`:

```java
JavaFileObject getJavaFileForOutput(
        JavaFileManager.Location location,
        String className,
        JavaFileObject.Kind kind,
        FileObject sibling
) throws IOException;
```

Các tham số có ý nghĩa:

| Tham số | Ý nghĩa | Trong bài |
| --- | --- | --- |
| `location` | Location mục tiêu do compiler quản lý. | Chỉ can thiệp `StandardLocation.CLASS_OUTPUT`. |
| `className` | **Binary name** của class cần ghi. | `demo.dynamic.Hello`, `demo.dynamic.Hello$Nested`. |
| `kind` | Loại file được yêu cầu. | Chặn đúng `JavaFileObject.Kind.CLASS`. |
| `sibling` | File liên quan để giúp manager quyết định vị trí output; có thể `null`. | Không cần cho bộ đệm RAM; **giữ nguyên khi delegate**. |

Override đơn giản:

```java
@Override
public JavaFileObject getJavaFileForOutput(
        JavaFileManager.Location location,
        String className,
        JavaFileObject.Kind kind,
        FileObject sibling) throws IOException {

    if (location == StandardLocation.CLASS_OUTPUT
            && kind == JavaFileObject.Kind.CLASS) {
        ClassBytes target = new ClassBytes(className, kind);
        compiled.put(className, target);
        return target;
    }

    return super.getJavaFileForOutput(
            location, className, kind, sibling);
}
```

*Đoạn trên thuộc lớp `CapturingFileManager` ở ví dụ đầy đủ, trong đó `ClassBytes` và `compiled` được định nghĩa bên dưới.*

Điểm cần hiểu:

1. **`getJavaFileForOutput` là điểm yêu cầu file object**; bytes thực sự được ghi khi compiler gọi `openOutputStream()` trên object được trả về.
2. Phải lưu target theo **`className`**. Một nguồn Java có thể sinh **nhiều file `.class`**, ví dụ class bao ngoài và nested class, anonymous class hoặc các class khác cùng compilation unit.
3. Phân biệt `CLASS_OUTPUT` với `SOURCE_OUTPUT`. Annotation processor có thể sinh `.java` hoặc resource ở những nơi khác; chặn `CLASS_OUTPUT` chưa bao phủ chúng.
4. Chỉ chặn `kind == CLASS` tại location yêu cầu. Với output không thuộc phạm vi, trả về kết quả `super.getJavaFileForOutput(...)` để giữ khả năng chuẩn.
5. `className` là tên binary, không phải đường dẫn file. Dùng `replace('.', '/') + ".class"` để tạo URI tượng trưng.

### API output theo originating files ở JDK hiện đại

Từ Java 18, `JavaFileManager` có thêm `getJavaFileForOutputForOriginatingFiles(...)`. Theo hợp đồng của `ForwardingJavaFileManager` hiện hành, khi subclass đã override `getJavaFileForOutput(...)` như trên, phiên bản nhận originating files sẽ delegate về override đó (sử dụng một originating file đầu tiên làm sibling nếu có).

Điều này giúp interception trên ví dụ tiếp tục áp dụng với đường gọi output mới; **không mặc định mọi API output đều đi qua nó**. Với yêu cầu ghi resource hoặc generated source, cần xét thêm các phương thức như `getFileForOutput(...)` và location tương ứng. Các lời gọi của annotation processor là chủ đề riêng, cần kiểm tra theo tình huống thực tế.

## 4. Đối tượng giữ bytecode: `SimpleJavaFileObject`

### 4.1. Tạo đúng URI và Kind

Class file không bắt buộc có `Path`. Ta có thể dùng URI giả lập, ví dụ:

```text
mem:///demo/dynamic/Hello.class
mem:///demo/dynamic/Hello$Nested.class
```

Đây là những URI **định danh object**, không phải đường dẫn tệp phải tồn tại trên ổ đĩa.

`SimpleJavaFileObject` nhận URI và `Kind` ở constructor. Để nhận bytecode, tạo subtype của nó:

```java
private static final class ClassBytes extends SimpleJavaFileObject {
    private final ByteArrayOutputStream buffer =
            new ByteArrayOutputStream();

    ClassBytes(String binaryName, Kind kind) {
        super(URI.create("mem:///"
                + binaryName.replace('.', '/')
                + kind.extension), kind);
    }

    @Override
    public OutputStream openOutputStream() {
        return buffer;
    }

    byte[] copy() {
        return buffer.toByteArray();
    }
}
```

Trong chương trình hoàn chỉnh bên dưới, những class import `ByteArrayOutputStream`, `OutputStream` và `URI` đã được cung cấp.

**Tại sao override `openOutputStream()`?** Implementation mặc định của `SimpleJavaFileObject.openOutputStream()` ném `UnsupportedOperationException`. Nếu chỉ tạo `new SimpleJavaFileObject(uri, Kind.CLASS)` mà không override method ghi, compiler không có cách nhận một output stream để lưu bytecode vào RAM.

**Tại sao `copy()` trả `byte[]` mới?** `ByteArrayOutputStream.toByteArray()` trả một bản sao của nội dung đã viết. Người tiêu thụ không thể trực tiếp sửa bộ đệm đang được file object quản lý. Tuy nhiên `byte[]` vẫn là mutable, nên registry lâu dài nên tiếp tục quản lý ownership và sao chép tại ranh giới tin cậy khi cần.

**Tại sao không đặt tên file theo simple class name?** Source có thể sinh class `demo.dynamic.Hello$Nested`. Nếu chỉ dùng `Hello.class` hoặc lấy phần cuối trước dấu `$`, nhiều sản phẩm sẽ đè nhau. Lưu theo **binary name đầy đủ**.

### 4.2. Input source cũng có thể ở RAM

Input source là một `JavaFileObject.Kind.SOURCE` với `getCharContent(...)`:

```java
private static final class SourceCode extends SimpleJavaFileObject {
    private final String code;

    SourceCode(String binaryName, String code) {
        super(URI.create("string:///"
                + binaryName.replace('.', '/')
                + Kind.SOURCE.extension), Kind.SOURCE);
        this.code = code;
    }

    @Override
    public CharSequence getCharContent(boolean ignoreEncodingErrors) {
        return code;
    }
}
```

Đầu vào và đầu ra là hai vai trò độc lập:

- **`SourceCode`:** compiler đọc source qua `getCharContent(...)`.
- **`ClassBytes`:** compiler ghi bytes qua `openOutputStream()`.
- **`CapturingFileManager`:** kết nối yêu cầu file output của compiler tới `ClassBytes`.

Có thể dùng source nằm trên đĩa qua `standard.getJavaFileObjectsFromPaths(List.of(path))` và **vẫn chặn class output vào RAM**. Việc input ở đâu và output ở đâu là hai quyết định riêng.

## 5. Ví dụ hoàn chỉnh: compile Java trong RAM và thu toàn bộ `.class`

Ví dụ tạo một class `demo.dynamic.Hello` có nested class `Nested`. Một source tạo **hai** class files. Khi compilation task thành công, chương trình xuất danh sách binary names và tải `Hello` bằng class loader riêng để gọi method `message()`.

### 5.1. Lưu thành `InMemoryCompileDemo.java`

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;

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

public class InMemoryCompileDemo {

    // Input: mã nguồn Java có trong String.
    private static final class SourceCode extends SimpleJavaFileObject {
        private final String code;

        SourceCode(String binaryName, String code) {
            super(URI.create("string:///"
                    + binaryName.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    // Output: nơi trình biên dịch ghi bytecode của một class.
    private static final class ClassBytes extends SimpleJavaFileObject {
        private final ByteArrayOutputStream buffer =
                new ByteArrayOutputStream();

        ClassBytes(String binaryName, Kind kind) {
            super(URI.create("mem:///"
                    + binaryName.replace('.', '/')
                    + kind.extension), kind);
        }

        @Override
        public OutputStream openOutputStream() {
            return buffer;
        }

        byte[] copy() {
            return buffer.toByteArray();
        }
    }

    // Wrapper: mọi thao tác bình thường ủy quyền cho standard manager,
    // riêng class output chuyển thành ClassBytes trong bộ nhớ.
    private static final class CapturingFileManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        private final Map<String, ClassBytes> compiled =
                new TreeMap<>();

        CapturingFileManager(StandardJavaFileManager standard) {
            super(standard);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location,
                String className,
                JavaFileObject.Kind kind,
                FileObject sibling) throws IOException {

            if (location == StandardLocation.CLASS_OUTPUT
                    && kind == JavaFileObject.Kind.CLASS) {
                ClassBytes target = new ClassBytes(className, kind);
                compiled.put(className, target);
                return target;
            }

            return super.getJavaFileForOutput(
                    location, className, kind, sibling);
        }

        // Chỉ lấy snapshot sau khi compilation task trả kết quả thành công.
        Map<String, byte[]> snapshot() {
            Map<String, byte[]> result = new TreeMap<>();
            compiled.forEach((name, file) ->
                    result.put(name, file.copy()));
            return result;
        }
    }

    // Loading là một bước riêng: file manager không tự execute class.
    private static final class MemoryClassLoader extends ClassLoader {
        private final Map<String, byte[]> classes;

        MemoryClassLoader(Map<String, byte[]> classes) {
            super(InMemoryCompileDemo.class.getClassLoader());
            this.classes = classes;
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            byte[] code = classes.get(name);
            if (code == null) {
                throw new ClassNotFoundException(name);
            }
            return defineClass(name, code, 0, code.length);
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "JDK compiler not available");
        }

        DiagnosticCollector<JavaFileObject> issues =
                new DiagnosticCollector<>();

        Map<String, byte[]> bytes;
        try (CapturingFileManager manager = new CapturingFileManager(
                compiler.getStandardFileManager(
                        issues, Locale.ROOT, StandardCharsets.UTF_8))) {

            JavaFileObject source = new SourceCode(
                    "demo.dynamic.Hello",
                    """
                    package demo.dynamic;
                    public class Hello {
                        public static String message() {
                            return "from memory";
                        }
                        public static class Nested {}
                    }
                    """);

            boolean ok = Boolean.TRUE.equals(compiler.getTask(
                    null, manager, issues,
                    List.of("--release", "17", "-proc:none"),
                    null, List.of(source)).call());

            long errors = issues.getDiagnostics().stream()
                    .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
                    .count();

            System.out.println("compiled=" + ok);
            System.out.println("errors=" + errors);

            if (!ok) {
                throw new IllegalStateException("Compilation failed");
            }
            bytes = manager.snapshot();
        }

        System.out.println("class files=" + bytes.size());
        System.out.println("classes=" + bytes.keySet());
        System.out.println("bytecode nonempty="
                + bytes.values().stream()
                        .allMatch(value -> value.length > 0));

        ClassLoader loader = new MemoryClassLoader(bytes);
        Class<?> generated =
                loader.loadClass("demo.dynamic.Hello");
        Object message =
                generated.getMethod("message").invoke(null);
        System.out.println("loaded method=" + message);
    }
}
```

### 5.2. Chạy trên JDK 17+

Lưu tệp đúng tên `InMemoryCompileDemo.java`, mở terminal tại thư mục chứa tệp và thực thi:

```bash
javac --release 17 InMemoryCompileDemo.java
java InMemoryCompileDemo
```

Trên Windows dùng lệnh tương tự trong PowerShell nếu `javac` và `java` nằm trong `PATH`.

**Stdout chính xác:**

```text
compiled=true
errors=0
class files=2
classes=[demo.dynamic.Hello, demo.dynamic.Hello$Nested]
bytecode nonempty=true
loaded method=from memory
```

**Giải thích output:**

1. `compiled=true`: `CompilationTask.call()` trả `true`, tức lần biên dịch thành công.
2. `errors=0`: không có `Diagnostic.Kind.ERROR`.
3. `class files=2`: nguồn có class bao ngoài `Hello` và nested class `Hello.Nested`; chúng tạo hai bytecode riêng.
4. `classes=[...]`: `TreeMap` sắp tên binary để output có thứ tự ổn định. `$` trong `Hello$Nested` là một phần của **binary name** của nested class.
5. `bytecode nonempty=true`: mỗi entry có bytes khác rỗng.
6. `loaded method=from memory`: class loader đọc `byte[]`, định nghĩa class và reflection gọi phương thức thành công.

Trong lệnh CLI, `javac` tạo các `.class` của **chương trình demo** bên cạnh tệp `InMemoryCompileDemo.java`. Nhưng các class **`demo.dynamic.Hello` và `demo.dynamic.Hello$Nested` do compilation task bên trong tạo** được chặn tại `CLASS_OUTPUT` và chỉ được lưu trong `Map<String, byte[]>` của ví dụ. Đó là hai cấp biên dịch khác nhau.

Options `List.of("--release", "17", "-proc:none")` áp dụng cho **lần biên dịch động bên trong JVM**: chọn mục tiêu Java 17 và tắt annotation processing trong demo. Đây là lựa chọn có chủ đích để đầu ra chỉ gồm class bytecode cơ bản; không đại diện mọi cấu hình cần có của công cụ build thực tế.

## 6. Những chi tiết quan trọng của interception

### 6.1. Vì sao chặn `CLASS_OUTPUT` thay vì mọi `Kind.CLASS`?

Compiler có nhiều lý do để yêu cầu file object, bao gồm đọc input class từ classpath hoặc module path, tạo class output, ghi generated source hoặc resource. Chỉ khi **`location == StandardLocation.CLASS_OUTPUT` và `kind == CLASS`**, ta mới biết request phù hợp chính xác mục tiêu của wrapper này: nhận bytecode class ở location đầu ra thông thường.

Nếu bất kỳ request nào khác cũng bị trả về một object RAM sai loại, có thể làm hỏng cách compiler tìm dependency, ghi generated source, hoặc ghi resource. `super.getJavaFileForOutput(...)` là nơi delegate request không thuộc phạm vi.

Trong compiler hỗ trợ nhiều module, còn có **module-specific output locations** được manager xác định từ `CLASS_OUTPUT`. Một wrapper dùng cho JPMS nhiều module cần khảo sát các location thực tế mà compiler gửi đến và xác định từng output location nào cần chặn. Điều kiện so sánh `location == CLASS_OUTPUT` trong demo tối giản là phù hợp bài biên dịch source **không có `module-info.java`**.

### 6.2. Một source không tương đương một class

Các cấu trúc sau có thể phát sinh nhiều `.class`:

```java
public class Outer {
    static class Nested {}
    Runnable r = new Runnable() {
        public void run() {}
    };
}
```

Đoạn trên chỉ minh họa nguồn có nested/anonymous classes; số lượng và tên output có thể phụ thuộc cấu trúc mã nguồn. **Không viết implementation chỉ giữ một `ByteArrayOutputStream` duy nhất** hoặc chỉ map theo simple name. Mỗi lần compiler gọi `getJavaFileForOutput(...)` cần target phù hợp với **binary name đầy đủ**, và bản đồ cần thu **tất cả** output sau khi task thành công.

Trong ví dụ, `compiled.put(className, target)` phù hợp với một task độc lập tạo output một lần cho mỗi binary name. Nếu quản lý nhiều lần compile chung một manager, cần chủ động quyết định policy cho trùng class name: ghi đè, versioning, hoặc tạo namespace theo từng task. Không công bố kết quả chưa biên dịch xong.

### 6.3. `SimpleJavaFileObject` không tự sở hữu dữ liệu

Constructor của `SimpleJavaFileObject` chỉ giữ URI và kind, cung cấp mặc định cho các phương thức. Các method chưa hỗ trợ mặc định có thể ném `UnsupportedOperationException`:

- Với source trong RAM, phải cung cấp `getCharContent(...)` hoặc cơ chế đọc phù hợp.
- Với class output trong RAM, phải cung cấp `openOutputStream()`.
- Nếu muốn compiler đọc class đã được tạo trước đó như một dependency cho lần compile sau, file object cần **cơ chế đọc bytes** như `openInputStream()` và file manager phải biết cách liệt kê/tìm những class này.

URI `mem:///...` chỉ là tên logic; nó **không tự có nội dung** và không kích hoạt I/O tới filesystem.

### 6.4. `ByteArrayOutputStream` và đóng output stream

Compiler thường gọi `openOutputStream()`, ghi bytes và đóng stream. `ByteArrayOutputStream.close()` không có tác dụng giải phóng tài nguyên native như stream file nên bytes vẫn có thể được đọc qua `toByteArray()` sau khi task kết thúc.

Ví dụ này giữ một buffer cho mỗi output object. Nếu tự xây hệ thống có khả năng ghi song song, đọc snapshot giữa lúc đang viết, hoặc mở lại cùng một output object cho nhiều lần ghi, cần thiết kế giao thức ownership rõ ràng; `ByteArrayOutputStream` và `TreeMap` không tự an toàn đa luồng.

Đừng kết luận thành công chỉ vì `compiled` có entries. Compiler có thể đã tạo một hoặc nhiều output **trước khi gặp lỗi**. Phải kiểm tra `task.call() == true` rồi mới công bố map.

### 6.5. Diagnostic và lỗi biên dịch

`DiagnosticCollector<JavaFileObject>` nhận cảnh báo và lỗi. Khi biên dịch không thành công, cần trình bày diagnostics có ngữ cảnh:

```java
boolean ok = Boolean.TRUE.equals(task.call());

if (!ok) {
    for (Diagnostic<? extends JavaFileObject> d :
            diagnostics.getDiagnostics()) {
        System.err.printf(
                "%s %s:%d:%d %s%n",
                d.getKind(),
                d.getSource() == null
                        ? "<unknown>" : d.getSource().getName(),
                d.getLineNumber(),
                d.getColumnNumber(),
                d.getMessage(Locale.ROOT));
    }
    throw new IllegalStateException("Compilation failed");
}
```

Đây là **đoạn mã ghép vào một luồng biên dịch đã có** `task` và `diagnostics`, không phải chương trình độc lập. Dòng/cột có thể là `Diagnostic.NOPOS` khi không có vị trí. Đừng assert nguyên văn diagnostic message trong test dùng nhiều phiên bản JDK vì wording/locale có thể đổi.

Ngoài lỗi source Java thông thường, các thao tác file manager có thể ném `IOException`, còn API compiler có thể gặp lỗi từ configuration, processor hoặc runtime. Không biến mọi exception thành `false` rồi bỏ diagnostics.

## 7. Giữ các tính năng của StandardJavaFileManager

Ưu điểm quan trọng nhất của `ForwardingJavaFileManager` là phần **delegate**:

- Tìm API lớp nền tảng trong JDK và các class phụ thuộc.
- Đọc resource/JAR/classpath qua file manager chuẩn.
- Tôn trọng cấu hình options, locations và module path.
- Quản lý các file object không nằm trong nhóm class output bị chặn.
- Chuyển tiếp `flush()` và `close()` khi không override.

Nếu source động cần tham chiếu tới một thư viện ngoài JDK, ứng dụng phải cấu hình classpath hoặc module path thích hợp. Ví dụ, với một `StandardJavaFileManager standard` chưa đưa vào wrapper:

```java
standard.setLocationFromPaths(
        StandardLocation.CLASS_PATH,
        List.of(Path.of("libs/library.jar")));
```

Đây là **minh họa cấu hình**, giả sử JAR ở đường dẫn đó thực sự tồn tại; không phải phần bắt buộc trong demo độc lập. `setLocationFromPaths` thay location đã cấu hình, do đó phải truyền đủ dependency cần dùng. Nếu định dùng module path, cần thiết lập đúng JPMS và output location riêng theo module.

Một hiểu lầm dễ gặp: thấy đầu ra được chặn trong RAM rồi cho rằng **mọi thao tác I/O compiler đều ở RAM**. Standard manager vẫn có thể đọc JDK modules, JAR và các file trên filesystem. Bài toán ở đây là **class output in-memory**; muốn hoàn toàn cô lập mọi I/O phải triển khai phạm vi lớn hơn nhiều.

## 8. Tách capture bytecode và nạp class

Sau khi task hoàn thành, ta có `Map<String, byte[]>`. **Compiler API không tự tạo class loader và không tự chạy mã vừa biên dịch**. Có thể giữ bytes làm artifact, ghi tệp khi thật sự cần hoặc nạp bằng class loader tùy biến.

Trong demo, `MemoryClassLoader.findClass(String name)`:

1. Tìm bytes theo binary name.
2. Nếu không có, ném `ClassNotFoundException` để phù hợp hợp đồng class loader.
3. Nếu có, gọi `defineClass(name, bytes, 0, bytes.length)`.
4. `loadClass(...)` còn dùng cơ chế delegation mặc định; trong ví dụ, tên `demo.dynamic.Hello` được chọn để không đụng các class ứng dụng đã có.

Lưu ý:

- Dữ liệu của nested class cũng phải được lưu, dù chương trình demo chỉ trực tiếp gọi method của class bao ngoài.
- Class loader thường theo mô hình **parent-first**. Nếu parent loader đã nạp class cùng tên, `loadClass` có thể trả class của parent thay vì bytes mới; khi xây hệ thống plugin thực tế cần chính sách tên và isolation rõ ràng.
- Một class đã được định nghĩa trong một class loader không thể tùy ý định nghĩa lại cùng tên trong loader đó. Nếu cần nhiều phiên bản code, có thể cần quản lý **class loader mới** cùng vòng đời của phiên bản.
- Class loader không làm code không tin cậy trở nên an toàn. Với mã có thể do người dùng hoặc nguồn bên ngoài đưa vào, phải thiết kế cô lập quyền/tài nguyên ở mức tiến trình hoặc môi trường chạy phù hợp; đóng góp của file manager chỉ là chuyển hướng dữ liệu biên dịch.
- Đừng lưu bytes trong một static map không có cơ chế dọn dẹp; nó có thể giữ lượng dữ liệu lớn, class loader và các object liên quan lâu hơn mong muốn.

## 9. Chặn output khác: generated source và resource

Ví dụ thực hành tắt annotation processing bằng `-proc:none` để giới hạn đối tượng cần xử lý. Trong ứng dụng có annotation processors, compiler/processor có thể tạo:

- `JavaFileObject.Kind.SOURCE` tại `StandardLocation.SOURCE_OUTPUT`.
- Class output tại `CLASS_OUTPUT`.
- Resource qua `JavaFileManager.getFileForOutput(...)` hoặc biến thể originating files.

Chặn `getJavaFileForOutput(...)` cho `CLASS_OUTPUT/CLASS` **không có nghĩa tất cả `.java` và tài nguyên cũng vào RAM**. Nếu yêu cầu của hệ thống là không ghi bất kỳ generated file nào xuống filesystem, cần mở rộng interception cho chính xác các location/kind và method output mà task sẽ sử dụng.

Khi dùng JDK 18+, API còn cung cấp:

```java
getJavaFileForOutputForOriginatingFiles(...)
getFileForOutputForOriginatingFiles(...)
```

Trong `ForwardingJavaFileManager` hiện hành, overload nhận originating files có quy tắc forward phù hợp đến override cũ nếu subclass đã override method tương ứng. Dù vậy, không nhầm giữa **file Java** (source/class) và **resource tùy ý**: hai nhóm có extension points khác nhau.

Không nên override mọi output bằng cùng một `JavaFileObject.Kind.CLASS`; nếu processor ghi text `.java` qua `openWriter()` thì object class chỉ có `openOutputStream()` có thể không đáp ứng hợp đồng đúng.

## 10. Biên dịch lần hai phụ thuộc bytecode RAM của lần một

Ví dụ đã triển khai đủ để **thu bytecode** sau một task và **nạp class để chạy**. Một mục tiêu khác là biên dịch `B.java` mà nó `import` class `A` vừa biên dịch trước đó chỉ tồn tại trong map bytes.

Khi đó, chỉ override `getJavaFileForOutput(...)` là **chưa đủ**. Trong compilation task tiếp theo, compiler phải có cách **tìm và đọc** class `A` như dependency. Một thiết kế file manager RAM đầy đủ cần xem xét:

- `getJavaFileForInput(location, className, kind)` để tìm `Kind.CLASS` theo binary name.
- `list(location, packageName, kinds, recurse)` để liệt kê các class trong package mà compiler cần resolve.
- `inferBinaryName(location, JavaFileObject)` khi compiler yêu cầu suy ra class name từ một file object tùy biến.
- `hasLocation(...)`/location mapping, `getClassLoader(...)` và các phương thức module-specific nếu kiến trúc dùng JPMS.
- `openInputStream()` của object bytecode để trả đúng dữ liệu đã capture; trong trường hợp có nhiều compilation tasks, cần đồng bộ vòng đời và quản lý snapshot của outputs.

Không nhất thiết override tất cả phương thức cho mọi tình huống; hãy xác định cách compiler truy vấn dependency trong workflow đang làm và kiểm tra bằng test có **hai tác vụ biên dịch liên tiếp**. Việc map chứa `A.class` không tự khiến standard manager tìm thấy nó vì standard manager không biết map đó tồn tại.

Nếu sản phẩm chỉ cần một lượt compile rồi nạp/run hoặc lưu bytecode, thiết kế tối giản trong bài là đủ và dễ bảo trì.

## 11. Kết nối với module system (JPMS)

Java 9+ hỗ trợ compile các named modules với `module-info.java`. Khi đó compiler có thể yêu cầu **module-specific output location** thay vì một `CLASS_OUTPUT` đơn giản.

Ví dụ đã kiểm thử chỉ biên dịch một source **không khai báo module**. Nếu hệ thống của bạn cần compile nhiều modules trong RAM:

1. Xác định module source path, module path và module graph.
2. Đọc các location được compiler sử dụng, bao gồm những location được xác định theo module.
3. Xây quy tắc interception không chỉ dựa vào identity `StandardLocation.CLASS_OUTPUT` nếu output thực tế là module-specific location.
4. Đảm bảo binary name và module identity được lưu đúng để không nhầm các class thuộc module khác nhau.
5. Kiểm thử sản phẩm `module-info.class`, class files của từng module và cách class loader/module layer nhận artifacts.

Không nên áp dụng code demo classpath cho JPMS rồi mặc định mọi output đều bị chặn: phạm vi `location == CLASS_OUTPUT` cố ý giới hạn cho trường hợp không module.

## 12. Kiểm thử đúng hành vi của bộ ghi class trong RAM

Các phép kiểm thử nên tập trung vào hợp đồng công khai và kết quả có thể quan sát:

| Test | Dữ liệu | Kết quả cần kiểm tra |
| --- | --- | --- |
| Source duy nhất | Một class `Hello` đơn giản | `task.call() == true`; map chứa `Hello`; bytes không rỗng. |
| Nhiều class từ một source | Class `Hello` có `static class Nested` | Map có cả `Hello` và `Hello$Nested`; mỗi class có bytes riêng. |
| Package | `package demo.dynamic` | Key dùng binary name đầy đủ, URI output tương ứng đường dẫn logic. |
| Lỗi cú pháp | Source thiếu dấu `}` | Task thất bại, collector chứa `ERROR`; không công bố snapshot như thành công. |
| Không có compiler | Runtime không cung cấp `jdk.compiler` | Báo lỗi rõ ràng từ `getSystemJavaCompiler() == null`. |
| Dependency trên JDK | Source dùng `java.util.List` | Standard manager tiếp tục resolve JDK class bình thường. |
| Thư viện ngoài | Source cần class từ một JAR được cấu hình | Manager delegate đúng classpath; class output vẫn ở map. |
| Không rò ra filesystem | Kiểm tra đường output được quản lý bởi test | Không có `Hello.class` của target sinh ở folder output vật lý. |
| Load class | Dùng class loader map bytes | `loadClass` và gọi method thành công với input đã biên dịch. |
| Trùng tên class giữa nhiều task | Hai phiên bản cùng binary name | Có quy tắc version/snapshot và class loader phù hợp; không công bố dữ liệu cũ nhầm phiên bản mới. |

Ví dụ kiểu JUnit Jupiter để khẳng định nội dung output của fixture có kiểm soát (đây là **đoạn minh họa**, phụ thuộc `bytes` từ demo và JUnit trong test classpath):

```java
assertTrue(bytes.containsKey("demo.dynamic.Hello"));
assertTrue(bytes.containsKey("demo.dynamic.Hello$Nested"));
assertTrue(bytes.values().stream().allMatch(v -> v.length > 0));
assertEquals(2, bytes.size());
```

Không assert đúng **độ dài bytecode** hoặc toàn bộ byte array theo một phiên bản JDK: compiler có thể tạo metadata/classfile khác theo bản JDK, options và debug information dù chương trình có cùng ngữ nghĩa.

Một kiểm thử bổ sung tốt là cố tình làm source sai rồi khẳng định compiler trả `false` và diagnostics chứa ít nhất một `Diagnostic.Kind.ERROR`. Sau lỗi, đừng yêu cầu map rỗng tuyệt đối: tùy tình huống compiler có thể đã tạo một phần output trước khi thất bại.

## 13. Lỗi phổ biến và cách sửa

### 13.1. Dùng mặc định `SimpleJavaFileObject.openOutputStream()`

**Hiện tượng:** compiler phát sinh `UnsupportedOperationException` hoặc không tạo được bytecode.

**Nguyên nhân:** `SimpleJavaFileObject` không tự cung cấp nơi ghi bytes. **Cách sửa:** override `openOutputStream()` bằng stream thực tế như `ByteArrayOutputStream`.

### 13.2. Override đúng tên method nhưng không truyền wrapper vào `getTask(...)`

**Hiện tượng:** output vẫn được ghi vào filesystem.

**Nguyên nhân:** code vô tình truyền `standard` thay vì `capturingManager` khi tạo task:

```java
// Sai với mục tiêu capture: bỏ qua wrapper.
compiler.getTask(null, standard, issues, options, null, units);

// Đúng: truyền wrapper đã override getJavaFileForOutput.
compiler.getTask(null, capturingManager, issues, options, null, units);
```

Đây là đoạn minh họa với các biến có sẵn. Cần đảm bảo compiler luôn thấy đúng instance file manager.

### 13.3. Lưu tất cả class files vào một buffer

**Hiện tượng:** chỉ còn bytecode của class cuối hoặc dữ liệu bị nối/trộn.

**Cách sửa:** tạo một `ClassBytes` cho **mỗi `className`** và map theo binary name. Một file source không bảo đảm một file class.

### 13.4. Chặn cả source và resource bằng `Kind.CLASS`

**Hiện tượng:** annotation processing hoặc ghi file khác thất bại.

**Cách sửa:** chặn đúng cặp location/kind, delegate phần còn lại. Nếu cần chặn `SOURCE_OUTPUT` hay resource, triển khai object và các thao tác ghi phù hợp riêng.

### 13.5. Coi `compiled.size() > 0` là compile thành công

**Hiện tượng:** chấp nhận bytecode thiếu hoặc artifact từ task lỗi.

**Cách sửa:** kiểm tra `Boolean.TRUE.equals(task.call())` và diagnostics, chỉ công bố bytes sau khi thành công. Để tách trạng thái, tạo map riêng cho mỗi task và thay snapshot sau khi hoàn tất.

### 13.6. Quên xử lý class loader và classpath

**Hiện tượng:** biên dịch thành công nhưng `loadClass` thất bại hoặc trả về bản class cũ.

**Cách sửa:** nạp bytes bằng class loader phù hợp, quản lý parent delegation và giải quyết dependency khi compile/load. `ForwardingJavaFileManager` không tự tải class.

### 13.7. Định nghĩa lại cùng binary name trong một ClassLoader

**Hiện tượng:** `LinkageError` hoặc không quan sát được phiên bản code mới.

**Cách sửa:** thiết kế quản lý phiên bản class loader; không dựa vào `getJavaFileForOutput` như cơ chế hot swap class đã nạp.

### 13.8. Mở rộng từ demo đơn luồng sang nhiều task song song mà không cô lập state

**Hiện tượng:** output bị lẫn giữa task hoặc map nhận trạng thái chưa hoàn thành.

**Cách sửa:** tạo mỗi compilation task một manager/map riêng hoặc thực hiện tuần tự có đồng bộ hóa rõ ràng. Java Compiler API không cam kết `TreeMap` và `ByteArrayOutputStream` tự thread-safe.

### 13.9. Quên đóng manager

**Hiện tượng:** file handles/cache của standard manager còn giữ.

**Cách sửa:** dùng `try-with-resources`. `ForwardingJavaFileManager.close()` forward đến manager nền nếu không override; ví dụ đóng wrapper bao quanh standard manager.

### 13.10. Cho rằng `-proc:none` đã sandbox hóa compiler

**Hiện tượng:** đưa source không tin cậy vào cùng tiến trình và cho phép chạy bytecode trực tiếp.

**Cách sửa:** tách rõ compile, load, execute; cân nhắc process isolation và hạn mức tài nguyên cho code không tin cậy. `-proc:none` chỉ tắt annotation processing theo option, không cung cấp sandbox cho code được nạp/chạy.

## 14. Checklist triển khai thực tế

1. Tạo `JavaCompiler` bằng `ToolProvider.getSystemJavaCompiler()` và kiểm tra `null`.
2. Tạo `DiagnosticCollector`, `StandardJavaFileManager` với charset rõ ràng.
3. Định nghĩa `SourceCode` (`Kind.SOURCE` + `getCharContent`) hoặc lấy source từ filesystem.
4. Định nghĩa `ClassBytes` (`Kind.CLASS` + `openOutputStream`) cho từng binary name.
5. Bọc standard manager bằng `ForwardingJavaFileManager` và override `getJavaFileForOutput` cho location/kind mong muốn.
6. Truyền **wrapper** vào `compiler.getTask(...)`; đặt options có chủ đích.
7. Gọi `task.call()` đúng một lần, kiểm tra thành công trước khi công bố bytecode.
8. Lấy map bytes dạng snapshot, đóng manager; quản lý memory/ownership rõ ràng.
9. Nếu cần chạy, tạo class loader phù hợp; nếu cần compile tiếp phụ thuộc class RAM, bổ sung các phương thức input/list/inferBinaryName.
10. Test nested class, lỗi cú pháp, classpath, không ghi ra đĩa và vòng đời của class loader.

## 15. Câu hỏi tự kiểm tra

**1. Đã dùng `SimpleJavaFileObject` làm source RAM; compiler có tự trả bytes trong RAM không?**  
Không. Source object chỉ thay đổi cách đọc input. Cần intercept đầu ra qua `JavaFileManager`.

**2. Vì sao phải override `getJavaFileForOutput(...)`?**  
Đây là điểm compiler yêu cầu `JavaFileObject` đại diện cho class output. Object được trả về quyết định nơi `openOutputStream()` ghi bytecode.

**3. Nếu một `.java` sinh 3 class, map cần bao nhiêu entry?**  
Thông thường ba entry với ba binary names tương ứng, vì mỗi file `.class` được yêu cầu riêng.

**4. `ForwardingJavaFileManager` có tự thay ClassLoader không?**  
Không. Nó chỉ tham gia compile I/O. Loading và execution là trách nhiệm riêng.

**5. Muốn compile `B` phụ thuộc `A` đã được compile trong RAM ở task trước thì chỉ map output có đủ không?**  
Không. Compiler ở lượt sau cần các phương thức tìm/đọc class đầu vào từ bộ nhớ, chẳng hạn `getJavaFileForInput`, `list`, `inferBinaryName` tùy trường hợp.

**6. Khi compiler thất bại nhưng map đã có bytes thì có công bố kết quả không?**  
Không. Chỉ sử dụng snapshot chính thức khi `task.call()` thành công và dữ liệu đáp ứng kiểm tra cần thiết.

**7. `getJavaFileForOutputForOriginatingFiles(...)` ở JDK hiện đại có làm override `getJavaFileForOutput(...)` luôn bị bỏ qua không?**  
Không. Hợp đồng `ForwardingJavaFileManager` hiện hành chuyển tiếp qua override tương ứng khi subclass đã override method này. Nhưng các output khác như resource cần kiểm tra điểm chặn riêng.

## Tài liệu API chính thức, còn hiệu lực

- [Java SE 26 — `ForwardingJavaFileManager`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/ForwardingJavaFileManager.html): wrapper và quy tắc delegate, bao gồm các overload output.
- [Java SE 26 — `JavaFileManager`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/JavaFileManager.html): `getJavaFileForOutput`, `getJavaFileForInput`, `list`, locations, originating files.
- [Java SE 26 — `SimpleJavaFileObject`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html): mặc định `openOutputStream`, `getCharContent` và yêu cầu override.
- [Java SE 26 — `JavaCompiler`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/JavaCompiler.html): API compiler và forwarding file manager.
- [Java SE 26 — `StandardJavaFileManager`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html): khả năng đọc filesystem, classpath và module path.
- [Java SE 26 — `JavaFileObject`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/JavaFileObject.html) và [`DiagnosticCollector`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/DiagnosticCollector.html): hợp đồng file source/class và thu thập chẩn đoán.

**Ghi nhớ:** chặn đầu ra class trong RAM bằng `ForwardingJavaFileManager` nghĩa là thay **đích của `getJavaFileForOutput(CLASS_OUTPUT, ..., CLASS, ...)`** thành object có `openOutputStream()` ghi vào bộ đệm. Toàn bộ cơ chế tìm dependency có thể tiếp tục được `StandardJavaFileManager` xử lý; chỉ khi workflow cần thêm nguồn phụ thuộc trong RAM, generated source/resource hoặc JPMS phức tạp thì mới mở rộng các điểm chặn khác.

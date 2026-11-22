# Thu bytecode qua `JavaFileObject` và `ForwardingJavaFileManager`

**Biên dịch trong bộ nhớ (in-memory compilation)** là kỹ thuật nhận mã nguồn Java dưới dạng chuỗi hoặc đối tượng dữ liệu, gọi trình biên dịch Java từ chính chương trình, rồi thu kết quả `.class` trực tiếp thành các mảng `byte[]`. Ứng dụng có thể lưu bytecode vào cache, kiểm tra kết quả, truyền cho một class loader, hoặc đóng gói thành artifact khác mà không phải để trình biên dịch ghi từng file `.class` ra thư mục.

Trọng tâm của kỹ thuật nằm ở hai điểm mở rộng trong Java Compiler API (JSR 199):

1. **`JavaFileObject`** biểu diễn một đầu vào hoặc đầu ra của trình biên dịch, có thể được hiện thực bằng dữ liệu trong bộ nhớ thay vì file vật lý.
2. **`ForwardingJavaFileManager`** bọc một file manager thông thường và chặn yêu cầu tạo **file đầu ra bytecode**, qua đó chuyển luồng ghi `.class` vào `ByteArrayOutputStream`.

Bài này dùng **Java 17+**, có một chương trình đầy đủ, biên dịch được và chạy được. Ví dụ cố ý khiến trình biên dịch phát sinh **hai class file** từ một source file (lớp chính và lớp lồng nhau) để chứng minh rằng phải thu **mọi đầu ra**, không chỉ file tương ứng với class nguồn ban đầu.

## 1. Luồng dữ liệu: từ source text đến bytecode

Với cách biên dịch quen thuộc:

```text
Hello.java --javac--> Hello.class trên ổ đĩa
```

Với Java Compiler API:

```text
String mã nguồn
       |
       v
SimpleJavaFileObject (Kind.SOURCE)
       |
       v
JavaCompiler.getTask(...).call()
       |
       v
JavaFileManager.getJavaFileForOutput(...)
       |
       v
JavaFileObject (Kind.CLASS)
       |
       v
openOutputStream()
       |
       v
ByteArrayOutputStream
       |
       v
Map<binaryClassName, byte[]>
       |
       +--> cache / đóng gói / kiểm tra
       |
       +--> ClassLoader.defineClass(...)
```

**Không có bước bắt buộc ghi `.class` xuống đĩa** trong đường biên dịch được thiết kế ở đây. Tuy nhiên, điều đó không có nghĩa toàn bộ quá trình luôn không dùng ổ đĩa: trình biên dịch vẫn có thể đọc các dependency, module hoặc tài nguyên từ classpath/module path thông thường. “Trong bộ nhớ” ở bài này chỉ khẳng định **source và bytecode đầu ra được quản lý trong bộ nhớ**.

Ngoài ra, khi bạn chạy `javac` để biên dịch chính chương trình demo, các `.class` của **chương trình điều khiển biên dịch** có thể nằm trên đĩa; đó không phải bytecode của lớp Java được demo tạo động.

## 2. Bốn vai trò trong Java Compiler API

| Thành phần | Vai trò | Method cần hiểu |
|---|---|---|
| `JavaCompiler` | Khởi chạy một tác vụ biên dịch từ bên trong JVM | `getTask(...)`, `CompilationTask.call()` |
| `JavaFileObject` | Mô hình một đơn vị mã nguồn hoặc bytecode đầu ra | `getCharContent(...)`, `openOutputStream()` |
| `JavaFileManager` | Cung cấp đầu vào, xử lý nơi ghi output cho compiler | `getJavaFileForOutput(...)`, `close()` |
| `ForwardingJavaFileManager<M>` | Bọc một manager có sẵn, chỉ tùy biến hành vi cần thiết | Override `getJavaFileForOutput(...)`, delegate phần còn lại |

Một số API liên quan:

- `ToolProvider.getSystemJavaCompiler()` lấy Java compiler được cung cấp bởi môi trường chạy, nếu có; cần một **JDK phù hợp**, không thể mặc định mọi runtime image đều chứa compiler.
- `StandardJavaFileManager` biết cách làm việc với file, JAR, classpath và các đường dẫn chuẩn.
- `SimpleJavaFileObject` là lớp cơ sở tiện lợi khi không cần tự hiện thực toàn bộ interface `JavaFileObject`.
- `DiagnosticCollector<JavaFileObject>` thu lỗi/cảnh báo với vị trí nguồn mà không phải tự parse văn bản stderr.
- `JavaFileObject.Kind.SOURCE` biểu diễn source; `Kind.CLASS` biểu diễn class file. **Mã nguồn là văn bản; bytecode `.class` là dữ liệu nhị phân**.

Cách thực hiện thực dụng là **dùng standard manager cho phần lớn hành vi** và chặn đúng một đầu ra cần thay đổi. Không nên tự viết lại toàn bộ logic tìm dependency/JAR khi nhu cầu chỉ là thu `.class` vào bộ nhớ.

## 3. Đầu vào: source text dưới dạng `JavaFileObject`

Giả sử ta cần biên dịch tên nhị phân `demo.DynamicHello` từ một chuỗi chứa `package demo;` và `public final class DynamicHello`.

Ta tạo một `SimpleJavaFileObject` kiểu SOURCE:

```java
private static final class SourceFile extends SimpleJavaFileObject {
    private final String source;

    SourceFile(String className, String source) {
        super(URI.create("string:///" + className.replace('.', '/')
                + Kind.SOURCE.extension), Kind.SOURCE);
        this.source = source;
    }

    @Override
    public CharSequence getCharContent(boolean ignoreEncodingErrors) {
        return source;
    }
}
```

Đây là **một thành phần bên trong chương trình đầy đủ ở phần 6**, không phải tệp độc lập. Những điểm chính:

1. `URI.create("string:///demo/DynamicHello.java")` là **URI logic**, không phải đường dẫn file cần tồn tại trên đĩa.
2. Tham số thứ hai của `SimpleJavaFileObject` là `Kind.SOURCE`, thông báo đây là input source.
3. `getCharContent(...)` cung cấp văn bản cho compiler. Với source đã ở dạng `String`, không cần `FileInputStream` hoặc đọc lại file.
4. Tên class dùng để tạo URI phải phù hợp với source và quy tắc đặt tên Java; đây không phải lý do để bỏ qua việc kiểm tra class/package người dùng cung cấp.

`SimpleJavaFileObject` có nhiều hành vi mặc định không cung cấp nội dung; vì thế input source cần override phương thức đọc thích hợp. Ngược lại, **đầu ra CLASS** cần override phương thức **ghi nhị phân**, không phải `getCharContent()`.

## 4. Đầu ra: `JavaFileObject` lưu `.class` vào byte array

Khi compiler chuẩn bị ghi một class file, nó sẽ nhận một `JavaFileObject` đầu ra từ file manager rồi gọi phương thức ghi thích hợp. Với output nhị phân của `Kind.CLASS`, ta cung cấp `OutputStream`:

```java
private static final class BytecodeFile extends SimpleJavaFileObject {
    private final ByteArrayOutputStream bytes = new ByteArrayOutputStream();

    BytecodeFile(String className, Kind kind) {
        super(URI.create("mem:///" + className.replace('.', '/')
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
```

Các chi tiết cần phân biệt:

- `mem:///demo/DynamicHello.class` là **URI định danh output**; scheme `mem` không tự tạo bộ nhớ hay lưu trữ. Bytecode thực sự được ghi vào `ByteArrayOutputStream`.
- `Kind.CLASS.extension` tương ứng với `.class`.
- `openOutputStream()` trả luồng ghi để compiler gửi **dãy byte class file** vào đó. Nếu chỉ giữ một `StringBuilder`, output `.class` sẽ không được thu đúng.
- `toByteArray()` trả **một bản sao dữ liệu byte** sau khi compiler đã hoàn thành ghi.
- Mỗi class file cần **một output object riêng**. Nếu nhiều class cùng ghi vào một stream chung, dữ liệu sẽ bị trộn và không còn là các class file hợp lệ.
- Nên lấy bản sao bytecode **sau khi `CompilationTask.call()` hoàn thành thành công**. Đọc giữa lúc compiler còn ghi có thể cho dữ liệu chưa hoàn chỉnh.

Trong môi trường yêu cầu tối ưu bộ nhớ, có thể thiết kế chính sách quản lý buffer và thời điểm giải phóng. Nhưng không nên xem `ByteArrayOutputStream` là storage dùng chung an toàn cho nhiều tác vụ biên dịch đồng thời.

## 5. Chặn điểm tạo output bằng `ForwardingJavaFileManager`

Compiler không biết rằng ta muốn ghi ra bộ nhớ, nên phải **thay đường đi của `getJavaFileForOutput(...)`**. Lớp manager minh họa:

```java
private static final class MemoryManager
        extends ForwardingJavaFileManager<StandardJavaFileManager> {
    private final Map<String, BytecodeFile> classes = new LinkedHashMap<>();

    MemoryManager(StandardJavaFileManager standard) {
        super(standard);
    }

    @Override
    public JavaFileObject getJavaFileForOutput(
            JavaFileManager.Location location, String className,
            JavaFileObject.Kind kind, FileObject sibling) throws IOException {
        BytecodeFile output = new BytecodeFile(className, kind);
        classes.put(className, output);
        return output;
    }

    Map<String, byte[]> bytecodes() {
        Map<String, byte[]> result = new LinkedHashMap<>();
        classes.forEach((name, file) -> result.put(name, file.content()));
        return result;
    }
}
```

Tương tự hai lớp trên, đây là **trích đoạn** sẽ xuất hiện trong chương trình đầy đủ. Giải nghĩa chữ ký:

| Tham số | Ý nghĩa |
|---|---|
| `location` | Vị trí output mà compiler yêu cầu, ví dụ output class; trong ví dụ đơn giản chưa cần phân loại |
| `className` | **Tên nhị phân** của class được tạo, ví dụ `demo.DynamicHello$Punctuation` |
| `kind` | Loại file cần tạo, ở luồng demo chủ yếu là `CLASS` |
| `sibling` | File object liên quan, giúp manager biết ngữ cảnh nếu cần; không được giả định luôn khác `null` |

**Vì sao dùng `ForwardingJavaFileManager`?** Nó giữ lại hành vi đọc input, tra classpath, tra JAR, xử lý vị trí và `close()` do `StandardJavaFileManager` cung cấp. Ta chỉ override đúng phần output cần điều khiển.

Bản demo lưu `Map<String, BytecodeFile>` theo tên class. Đây là thiết kế phù hợp cho một lần biên dịch **classpath đơn giản**, trong đó mỗi tên nhị phân của một class output chỉ xuất hiện một lần. Trong hệ thống biên dịch nhiều module, nhiều round hoặc nhiều output location, khóa chỉ bằng tên có thể không đủ; khi ấy cần tính cả **module/location/round** để tránh đè kết quả.

**Quan trọng:** việc override `getJavaFileForOutput` chỉ kiểm soát các output được truy cập qua method này. Một triển khai phức tạp có thể tạo thêm resource, generated source, output theo module, hoặc cơ chế file manager bổ sung. Khi mục tiêu là **không ghi bất kỳ artifact nào xuống đĩa**, phải kiểm toán thêm các method như `getFileForOutput`, xử lý annotation processor, module-oriented output và đầu ra phụ thuộc công cụ.

## 6. Chương trình Java 17 hoàn chỉnh, biên dịch và chạy được

Tạo tệp duy nhất `InMemoryCompilerDemo.java` với **toàn bộ nội dung** sau. Mã dùng các lớp chuẩn `javax.tools` và Java API, không cần thư viện bên thứ ba.

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeSet;
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

public final class InMemoryCompilerDemo {
    private static final class SourceFile extends SimpleJavaFileObject {
        private final String source;

        SourceFile(String className, String source) {
            super(URI.create("string:///" + className.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.source = source;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return source;
        }
    }

    private static final class BytecodeFile extends SimpleJavaFileObject {
        private final ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        BytecodeFile(String className, Kind kind) {
            super(URI.create("mem:///" + className.replace('.', '/')
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

    private static final class MemoryManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        private final Map<String, BytecodeFile> classes = new LinkedHashMap<>();

        MemoryManager(StandardJavaFileManager standard) {
            super(standard);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location, String className,
                JavaFileObject.Kind kind, FileObject sibling) throws IOException {
            BytecodeFile output = new BytecodeFile(className, kind);
            classes.put(className, output);
            return output;
        }

        Map<String, byte[]> bytecodes() {
            Map<String, byte[]> result = new LinkedHashMap<>();
            classes.forEach((name, file) -> result.put(name, file.content()));
            return result;
        }
    }

    private static final class MemoryLoader extends ClassLoader {
        private final Map<String, byte[]> code;

        MemoryLoader(Map<String, byte[]> code) {
            super(InMemoryCompilerDemo.class.getClassLoader());
            this.code = Map.copyOf(code);
        }

        @Override
        protected Class<?> findClass(String name) throws ClassNotFoundException {
            byte[] bytes = code.get(name);
            if (bytes == null) {
                throw new ClassNotFoundException(name);
            }
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("A JDK is required");
        }

        String binaryName = "demo.DynamicHello";
        String source = """
                package demo;
                public final class DynamicHello {
                    private static final class Punctuation {
                        static String ending() { return "!"; }
                    }
                    public static String message(String name) {
                        return "Hello, " + name + Punctuation.ending();
                    }
                }
                """;

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();
        Map<String, byte[]> bytecodes;

        try (MemoryManager manager = new MemoryManager(
                compiler.getStandardFileManager(
                        diagnostics, Locale.ROOT, StandardCharsets.UTF_8))) {
            JavaCompiler.CompilationTask task = compiler.getTask(
                    null,
                    manager,
                    diagnostics,
                    List.of("--release", "17"),
                    null,
                    List.of(new SourceFile(binaryName, source)));

            boolean ok = Boolean.TRUE.equals(task.call());
            if (!ok) {
                for (Diagnostic<? extends JavaFileObject> d
                        : diagnostics.getDiagnostics()) {
                    System.err.println(d.getKind() + " at line "
                            + d.getLineNumber() + ": "
                            + d.getMessage(Locale.ROOT));
                }
                throw new IllegalStateException("Compilation failed");
            }

            bytecodes = manager.bytecodes();
        }

        System.out.println("Compilation: success");
        System.out.println("Classes: " + new TreeSet<>(bytecodes.keySet()));

        ClassLoader loader = new MemoryLoader(bytecodes);
        Class<?> generated = loader.loadClass(binaryName);
        Object result = generated.getMethod("message", String.class)
                .invoke(null, "Java");

        System.out.println("Result: " + result);
    }
}
```

### 6.1. Cách chạy

Cài JDK 17 trở lên và đứng ở thư mục chứa `InMemoryCompilerDemo.java`.

Linux/macOS:

```bash
javac --release 17 -encoding UTF-8 InMemoryCompilerDemo.java
java InMemoryCompilerDemo
```

Windows PowerShell dùng **cùng hai lệnh**:

```powershell
javac --release 17 -encoding UTF-8 InMemoryCompilerDemo.java
java InMemoryCompilerDemo
```

Không cần chuẩn bị file `demo/DynamicHello.java` trên đĩa; chuỗi source của lớp động đã nằm trong chương trình.

### 6.2. Stdout chính xác

Kết quả chạy thành công:

```text
Compilation: success
Classes: [demo.DynamicHello, demo.DynamicHello$Punctuation]
Result: Hello, Java!
```

**Vì sao có hai tên trong `Classes`?** Dù chỉ cung cấp **một** `SourceFile` kiểu SOURCE, compiler tạo một class file cho `demo.DynamicHello` và một class file cho lớp lồng nhau `demo.DynamicHello$Punctuation`. Dấu `$` là một phần của tên nhị phân lớp lồng nhau trong ví dụ; không có nghĩa hai tên là cùng một class file.

Kết quả được sắp xếp bằng `TreeSet` để đầu ra ổn định; thứ tự compiler gọi `getJavaFileForOutput()` không phải điều kiện mà consumer nên dựa vào.

Chương trình `MemoryLoader` sử dụng chính map bytecode thu được. Khi `demo.DynamicHello.message(...)` gọi lớp lồng nhau, class loader cũng tìm được `demo.DynamicHello$Punctuation` từ map, nhờ vậy tránh lỗi thiếu class phụ.

## 7. Trình tự thực thi bên trong `main`

Có thể theo dõi bằng các mốc sau:

1. **Lấy compiler:** `ToolProvider.getSystemJavaCompiler()` trả một compiler nếu runtime có công cụ này; nếu không, dừng với thông báo yêu cầu JDK.
2. **Tạo input:** `new SourceFile(binaryName, source)` đóng gói source text và URI logic tương ứng với tên class.
3. **Tạo diagnostic collector:** nhận warning/error dạng đối tượng, gồm `Kind`, vị trí và message.
4. **Mở manager:** standard manager xử lý classpath/JAR; `MemoryManager` chặn các request tạo class output.
5. **Tạo task:** `compiler.getTask(writer, fileManager, diagnosticListener, options, classes, compilationUnits)` nhận manager, tùy chọn `--release 17` và nguồn trong bộ nhớ.
6. **Gọi `task.call()`:** compiler phân tích cú pháp, kiểm tra kiểu và tạo output thông qua `getJavaFileForOutput()` → `BytecodeFile.openOutputStream()`.
7. **Kiểm tra kết quả:** chỉ chấp nhận `Boolean.TRUE`; nếu thất bại, dùng diagnostics để thông báo lỗi và **không coi bytecode chưa hoàn chỉnh là kết quả hợp lệ**.
8. **Chụp bytecode:** `manager.bytecodes()` chuyển các buffer thành `Map<String, byte[]>`. Khi rời `try`, manager (và delegate của nó) được đóng.
9. **Nạp từ bytecode:** class loader nhận map và dùng `defineClass(...)` trong `findClass(...)`. Chỉ khi JVM cần lớp tương ứng, dữ liệu byte mới được định nghĩa thành `Class<?>`.
10. **Gọi method:** dùng reflection với chữ ký đã biết (`message(String)`), nhận kết quả rồi in.

Việc `getTask()` trả một task **không phải bảo đảm biên dịch đã xảy ra**. Đường thực thi biên dịch diễn ra khi gọi `task.call()`. `JavaCompiler.CompilationTask` không phải đối tượng để chạy lặp đi lặp lại với cùng trạng thái; mỗi lượt biên dịch nên có một task mới và có thể có manager mới.

## 8. Vì sao phải thu mọi class output thay vì chỉ lớp chính?

Một source file có thể phát sinh nhiều class file:

- **Lớp lồng nhau** (nested/static/inner class).
- **Anonymous class** hoặc một số cấu trúc ngôn ngữ sinh class phụ.
- **Nhiều top-level class** hợp lệ trong cùng compilation unit (chỉ một public top-level class tương ứng với tên source file).
- **Các compilation unit được cung cấp đồng thời** trong một lần biên dịch.

Không nên thiết kế:

```java
// Minh họa cách làm không đủ: chỉ đoán một đầu ra cho lớp chính.
byte[] compiled = outputs.get("demo.DynamicHello");
```

rồi loại bỏ phần còn lại nếu dự kiến sẽ nạp và thực thi lớp động. Nếu `DynamicHello` tham chiếu `Punctuation`, loader cần cả hai bytecode khi class phụ được nạp.

Thiết kế đáng tin hơn là **lưu tất cả đầu ra theo tên nhị phân** và chỉ tạo loader sau khi tác vụ đã thành công:

```java
Map<String, byte[]> allClasses = manager.bytecodes();
```

Câu lệnh trên là trích đoạn dùng trong ngữ cảnh có biến `manager`. Chỉ cần chặn thêm các loại resource/source khác khi bài toán thực sự sử dụng annotation processor hoặc output phụ.

## 9. Diagnostics: lỗi biên dịch khác lỗi chạy class

`JavaCompiler.getTask(...).call()` thường trả:

- `true`: tác vụ biên dịch thành công (có thể vẫn có warning).
- `false`: có lỗi biên dịch, ví dụ lỗi cú pháp hoặc kiểu.
- Một số lỗi nghiêm trọng khác có thể phát sinh dưới dạng ngoại lệ; không được gộp mọi trường hợp thành kết quả `false`.

Ví dụ nếu source động gọi một method chưa tồn tại, compiler sẽ báo lỗi trong `DiagnosticCollector` và chương trình ở phần 6 **không tiến tới bước nạp class**.

Muốn in lỗi có cấu trúc:

```java
for (Diagnostic<? extends JavaFileObject> d : diagnostics.getDiagnostics()) {
    System.err.printf("%s: line %d, column %d: %s%n",
            d.getKind(),
            d.getLineNumber(),
            d.getColumnNumber(),
            d.getMessage(Locale.ROOT));
}
```

Đây là trích đoạn trong phạm vi có biến `diagnostics`. Khi số dòng/cột không xác định, API có thể cung cấp giá trị biểu thị “không có vị trí”; không được giả định mọi diagnostic đều ứng với một source line cụ thể.

Phải phân biệt hai giai đoạn:

| Giai đoạn | Lỗi thường gặp | Cách kiểm tra |
|---|---|---|
| Biên dịch | Cú pháp sai, thiếu kiểu hoặc method, option sai | `task.call()`, `DiagnosticCollector`, compilation classpath |
| Định nghĩa/nạp class | Không đủ bytecode lớp phụ, class name không khớp, thiếu dependency | Map output, `ClassLoader.findClass`, `ClassLoader.loadClass` |
| Liên kết/thực thi | `NoClassDefFoundError`, `NoSuchMethodError`, exception do code động | Phiên bản dependency runtime, stack trace, ranh giới loader |
| Reflection | Sai tên method/chữ ký/quyền truy cập | `getMethod(...)`, parameter types, khả năng truy cập |
 
Một tác vụ có thể **biên dịch thành công** nhưng khi chạy vẫn lỗi, nếu compilation classpath chứa dependency không có trong class loader runtime. Thu đủ bytecode của những lớp *được biên dịch trong lượt hiện tại* không đồng nghĩa thu mọi dependency cần để thực thi.

## 10. Những mở rộng thực tế của file manager

### 10.1. Nhiều source unit

`getTask()` có tham số `Iterable<? extends JavaFileObject> compilationUnits`, nên có thể đưa nhiều `SourceFile` vào cùng một lần biên dịch:

```java
List<JavaFileObject> units = List.of(
        new SourceFile("demo.First", firstSource),
        new SourceFile("demo.Second", secondSource));
```

Đây là ví dụ **cú pháp minh họa**: `firstSource`/`secondSource` là các biến chứa source text mà ứng dụng cần cung cấp. Khi cả hai source được compiler nhìn thấy trong cùng task, chúng có thể tham chiếu nhau theo quy tắc Java bình thường.

Không nên tự khởi động một `getTask()` cho mỗi lớp phụ thuộc nhau nếu chưa thiết kế cách chuyển bytecode đã biên dịch làm classpath/in-memory input cho task tiếp theo.

### 10.2. Biên dịch nhiều lượt và tra cứu class trong bộ nhớ

Trong demo, `MemoryManager` chỉ bắt output; nó **không** đưa các `byte[]` đó thành input cho một task compiler khác. Nếu muốn biên dịch lớp B ở lần sau trong khi B phụ thuộc lớp A đã biên dịch ở lần trước, cần giải quyết việc compiler tìm được `.class` của A.

Có hai cách chính:

1. Đóng gói/cung cấp A trên một classpath được compiler hỗ trợ (có thể qua JAR/file trung gian nếu chấp nhận I/O).
2. Thiết kế thêm các method tra input trong `JavaFileManager`, như `getJavaFileForInput(...)`, `list(...)`, `inferBinaryName(...)` và ngữ nghĩa module/classpath tương ứng, để bytecode in-memory được compiler nhận diện. **Chỉ override `getJavaFileForOutput()` không đủ cho trường hợp này.**

Đừng nhầm đường tìm class của **compiler** với `ClassLoader` dùng để **chạy** class sau biên dịch: đây là hai cơ chế thuộc hai giai đoạn khác nhau.

### 10.3. Annotation processors và generated resources

Annotation processor có thể phát sinh source, class hoặc resource mới. Ví dụ của bài chưa bật processor tùy biến; nếu áp dụng trong dự án lớn, manager có thể cần xử lý:

- `getJavaFileForOutput(...)` cho generated source và class.
- `getFileForOutput(...)` cho resource không phải Java class.
- Các method output liên quan module/location nếu có nhiều module.
- Tên binary class và origin/sibling phù hợp khi nhiều compilation rounds.
- Chính sách cho phép hoặc vô hiệu annotation processing theo mức độ tin cậy của source.

Không được tuyên bố “không đụng đĩa” chỉ dựa trên việc capture `Kind.CLASS` khi còn các đường ghi output khác chưa được kiểm tra. Nếu nguồn không tin cậy, nên chủ động cân nhắc cấu hình processing và cơ chế cô lập.

### 10.4. Quản lý nhiều module hoặc nhiều phiên bản class

Trong một task đơn giản, `Map<String, byte[]>` có khóa `binaryName` là đủ. Khi cùng tên lớp xuất hiện ở nhiều module hoặc compilation context, cần thêm thông tin **module identity / output location**. Khi chạy, mỗi phạm vi class loader cũng phải được thiết kế để biết class name nào thuộc về nó.

Việc cho hai class cùng tên vào một map dưới một khóa sẽ khiến một lớp ghi đè lớp còn lại; đó không phải cô lập phiên bản. Cần module layer hoặc loader riêng theo yêu cầu thiết kế, thay vì chỉ thay đổi kiểu map.

## 11. Tương tác với class loader: thu bytecode không đồng nghĩa nạp class

Bản demo có:

```java
ClassLoader loader = new MemoryLoader(bytecodes);
Class<?> generated = loader.loadClass("demo.DynamicHello");
```

`MemoryLoader.findClass()` sử dụng `defineClass(name, bytes, 0, bytes.length)`. Nó **không** gọi file system để tìm class động. Tuy nhiên class loader trong demo vẫn theo cơ chế **parent-first mặc định** do `loadClass()` của `ClassLoader`; nếu parent đã có class cùng tên, parent có thể thắng trước khi `findClass()` được gọi.

Vì vậy, trong ví dụ ta chọn tên `demo.DynamicHello` chưa nằm trên classpath. Với môi trường plugin thực tế, cần chính sách namespace, package và delegation rõ ràng để tránh va chạm. Không tùy tiện chuyển toàn bộ loader thành child-first vì có thể nhân đôi các kiểu hợp đồng chung và gây `ClassCastException`.

Ngoài ra:

- `defineClass` kiểm tra tính hợp lệ của class file theo các quy tắc của JVM; bytecode sai có thể gây `ClassFormatError` hoặc lỗi xác minh/liên kết.
- Nạp class không có nghĩa mọi đường thực thi của nó đã được kiểm tra nghiệp vụ.
- Tái biên dịch cùng tên class **không thể thay định nghĩa đã tồn tại trong cùng một loader** chỉ bằng cách thay `byte[]` của map. Thường phải tạo loader mới hoặc dùng cơ chế đặc thù phù hợp.
- Loader/class/instance đang còn tham chiếu sẽ giữ dữ liệu và tài nguyên liên quan; nếu tạo compiler và loader theo từng yêu cầu, cần quy định vòng đời và giới hạn cache.

## 12. An toàn, tài nguyên và vận hành

Biên dịch mã nguồn động không phải sandbox. Ngay cả khi chỉ biên dịch, annotation processor hoặc plugin của compiler có thể chạy code; khi nạp/thực thi class được sinh ra, code đó chạy với quyền của JVM hiện tại.

Với mã do người dùng ngoài hệ thống cung cấp, cần đánh giá nghiêm ngặt:

- **Nguồn đáng tin:** ai được phép gửi source, bật compiler option nào và ai được phép bật annotation processor.
- **Giới hạn tài nguyên:** size của source, số compilation unit, số class sinh ra, tổng bytecode, thời gian CPU và memory. Một vòng build không giới hạn có thể cạn heap.
- **Dependency:** compilation classpath không nên tùy ý lấy library thiếu kiểm soát. Các artifact/phần mở rộng compiler cần được kiểm tra và quản lý.
- **Chạy code:** muốn chạy code không tin cậy cần cách ly đủ mạnh, ví dụ process/container có chính sách quyền và tài nguyên phù hợp; **class loader không phải ranh giới bảo mật**.
- **Concurrent requests:** mỗi tác vụ nên sở hữu state/manager/buffer của mình; không chia sẻ một `LinkedHashMap` hoặc standard file manager theo cách không có kiểm soát giữa nhiều luồng.
- **Dọn dẹp:** dùng `try-with-resources` để đóng file manager. Sau khi chụp bytecode, quyết định lúc nào xóa cache và bỏ tham chiếu loader/instances.
- **Giám sát:** ghi metrics về duration, số source, số class bytes, warning/error; tránh ghi toàn bộ source nhạy cảm vào log.

Đặc biệt, `DiagnosticCollector` có thể chứa chuỗi code, tên tệp hoặc lỗi liên quan source; nếu source chứa thông tin nhạy cảm, hãy xử lý log và quyền truy cập phù hợp.

## 13. Sai lầm thường gặp và cách sửa

| Sai lầm | Biểu hiện | Cách khắc phục |
|---|---|---|
| Override `getCharContent()` cho cả output `.class` | Không thu được bytecode đúng | Output CLASS cần `openOutputStream()` |
| Giữ một `ByteArrayOutputStream` cho mọi class | File `.class` bị trộn dữ liệu | Tạo output mới cho từng tên binary/output location |
| Chỉ lấy bytecode của top-level class | Class phụ thiếu khi nạp | Thu mọi `getJavaFileForOutput()` của task |
| Dùng tên file path thay cho binary class name | Map lookup/class loader sai tên | Dùng `className` compiler cung cấp; giữ mapping rõ |
| `task.call()` trả false vẫn dùng output | Có thể chỉ có bytes không hoàn chỉnh | Dừng và đọc diagnostics |
| Tạo bytecode nhưng không cung cấp class loader | Không thể gọi trực tiếp class động bằng type tĩnh không có trên compile classpath | Dùng loader phù hợp và reflection/giao diện chung |
| Trộn compilation classpath với runtime classpath | Biên dịch xong, chạy lại thiếu dependency | Kiểm tra cả hai môi trường |
| `ToolProvider.getSystemJavaCompiler()` trả null | Runtime thiếu compiler | Dùng JDK/runtime có module compiler cần thiết |
| Chỉ override output mà muốn compile lần sau dùng lại bytecode | Compiler không tìm thấy class biên dịch trước | Thiết kế thêm input lookup hoặc cung cấp artifact ở classpath |
| Cho source không tin cậy chạy trong JVM host | Rủi ro tài nguyên và bảo mật | Cô lập quy trình build/thực thi và hạn chế quyền |
| Chia sẻ manager/buffer tùy ý giữa thread | Race condition, kết quả sai | Tách state theo task, đồng bộ khi cần |
| Giữ vô hạn map `byte[]` và loader | Tăng heap và khó giải phóng class | Quản lý cache, quota và lifecycle |

## 14. Checklist kiểm thử một bộ in-memory compiler

Trước khi đưa vào ứng dụng:

1. **Input chính xác:** `JavaFileObject.Kind.SOURCE` có URI và source content hợp lệ, tên package/class khớp nguồn.
2. **Capture đầy đủ:** `getJavaFileForOutput` nhận đúng tên nhị phân và tạo buffer riêng cho mỗi class file.
3. **Không ghi output ngoài ý muốn:** kiểm tra các loại output cần capture, kể cả resource do processor tạo khi có.
4. **Diagnostic tin cậy:** lỗi biên dịch được phản hồi qua diagnostic có ngữ cảnh; không dùng partial bytecode.
5. **Nhiều class:** kiểm thử nested class/anonymous class và đủ `byte[]` cần để nạp.
6. **Ranh giới phụ thuộc:** compiler và class loader nhìn thấy đúng dependency/version.
7. **Kết quả sau biên dịch:** map được chụp sau `task.call()`, dữ liệu nhị phân không bị chuyển sai encoding.
8. **Lifecycle:** file manager được đóng; cache bytecode và loader không tăng vô hạn.
9. **Kiểm thử thất bại:** source sai syntax, thiếu type, thiếu dependency runtime, compiler unavailable.
10. **Bảo mật:** có chính sách đối với source/processor và việc thực thi class động.

## 15. Bài tập củng cố

1. **Đếm bytecode:** sau khi `task.call()` trả `true`, bổ sung vòng lặp `Map.Entry<String, byte[]>` để in kích thước byte của từng class. Vì sao kích thước bytecode có thể khác theo JDK dù hành vi chương trình giống nhau?
2. **Tạo thêm lớp lồng nhau:** thêm một nested static class nữa vào chuỗi `source`. Dự đoán số `Kind.CLASS` output và những khóa mới sẽ xuất hiện trong map.
3. **Cố ý gây lỗi:** đổi `Punctuation.ending()` thành một tên method không tồn tại. Theo dõi `DiagnosticCollector` và giải thích vì sao không được dùng `bytecodes` khi compilation thất bại.
4. **Biên dịch hai source:** tạo hai `SourceFile` có class khác nhau và truyền đồng thời cho `getTask()`. Cho một class gọi method của class còn lại; xác minh compiler phát hiện dependency trong cùng task.
5. **Biên dịch nhiều lượt:** thiết kế bước đọc bytecode đã lưu như `JavaFileObject.Kind.CLASS` để compiler lượt sau dùng, liệt kê các method file manager cần xem xét. Vì sao chỉ có `getJavaFileForOutput()` là chưa đủ?
6. **Đổi chiến lược runtime:** tạo một loader mới từ map bytecode và chứng minh việc đổi bytecode map không tự thay class đã nạp trong loader cũ. Nêu rủi ro leak loader khi chạy lặp lại nhiều lần.

**Kết luận:** trong Java Compiler API, `JavaFileObject` là **nơi compiler đọc source hoặc ghi class**, còn `ForwardingJavaFileManager` là **điểm điều hướng output** từ đường lưu file mặc định sang bộ nhớ. Thiết kế đúng phải lưu *mọi* class file được sinh ra, kiểm tra kết quả compiler và diagnostics, rồi tách bạch việc **biên dịch**, **nạp** và **thực thi** bytecode.
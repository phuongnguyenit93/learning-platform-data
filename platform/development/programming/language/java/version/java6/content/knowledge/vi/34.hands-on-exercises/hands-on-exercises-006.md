# Biên dịch mã sinh trong bộ nhớ và báo lỗi theo vị trí (Java 17+)

## 1. Mục tiêu bài thực hành

Khi một ứng dụng cần tạo mã Java từ template, mô hình dữ liệu, DSL, metadata hoặc cấu hình, không nhất thiết phải ghi từng file `.java` và `.class` ra đĩa. **Java Compiler API** (`javax.tools`) cho phép truyền **Java source đang ở trong `String`**, ghi nhận class outputs thành `byte[]` trong RAM và thu lỗi biên dịch dưới dạng các `Diagnostic` có **source, dòng, cột và character offset**. Bài này ghép cả ba bước thành một ví dụ có thể biên dịch/chạy.

Các mục tiêu cụ thể:

1. Tạo một `JavaFileObject` loại `SOURCE` từ `String` do trình sinh mã tạo.
2. Lấy `JavaCompiler` bằng `ToolProvider.getSystemJavaCompiler()` và tạo một `CompilationTask` với `--release 17`.
3. Viết `ForwardingJavaFileManager` chặn `getJavaFileForOutput` để nhận **mọi file class** vào `ByteArrayOutputStream` thay vì output directory mặc định.
4. Dùng `DiagnosticCollector<JavaFileObject>`, phân loại `Diagnostic.Kind.ERROR`, hiển thị đúng tên nguồn, dòng/cột 1-based và offsets 0-based.
5. Hiểu khi nào `getSource()==null` hoặc `getPosition()==Diagnostic.NOPOS`, tránh tính vị trí âm.
6. Biết vì sao một source có thể tạo nhiều class files, và vì sao compile thất bại có thể vẫn có **partial outputs** không được dùng.
7. Có thể nạp class sinh ra bằng `ClassLoader` **nếu source hoàn toàn do mình tin cậy và kiểm soát**, nhưng phân biệt rõ compile và execute.
8. Quản lý compiler resources, dependency classpath, annotation processing và giới hạn bảo mật.

**Kiến thức hiện hành:** các API dưới đây nằm trong module `java.compiler`, có trên Java 17, 21, **Java 25** khi runtime có compiler provider (thường là `jdk.compiler`). Không dùng compiler internal packages, API đã bị loại bỏ hoặc JavaScript scripting engine lịch sử. `--release 17` và `-proc:none` được sử dụng cho ví dụ.

**Giới hạn quan trọng:** “trong bộ nhớ” ở đây nói tới **source do chương trình sinh và generated class bytes**, không có nghĩa Java compiler không đọc file/module/JAR dependency nào trên máy. Ví dụ chính `InMemoryCompileDemo.java` vẫn được biên dịch từ file bằng `javac` như một ứng dụng Java bình thường; chỉ `demo.Greeting`/`demo.Greeting$Helper` bên trong nó được compile và lưu hoàn toàn trong memory manager.

## 2. Kiến trúc từ Java String tới kết quả biên dịch

```text
Generated Java String
        |
        v
SourceFile extends SimpleJavaFileObject
  Kind.SOURCE
  URI mem:///demo/Greeting.java
  getCharContent() --> source String
        |
        v
JavaCompiler.getTask(...)
        |
        +---------------------------+
        |                           |
        v                           v
DiagnosticCollector       MemoryManager extends
  ERROR/WARNING/NOTE      ForwardingJavaFileManager
  source URI              CLASS_OUTPUT + Kind.CLASS
  line/column                       |
  position/start/end                v
        |                 ClassFile.openOutputStream()
        |                 ByteArrayOutputStream
        v                           |
UI báo lỗi theo vị trí              v
                           Map<String, byte[]>
                           "demo.Greeting"
                           "demo.Greeting$Helper"
                                     |
                        Chỉ với source đã được tin
                                     v
                                ClassLoader
```

Có **hai nhóm kết quả độc lập**: diagnostics cho người dùng (có thể xuất hiện cả lúc compile thành công) và class bytes (chỉ publish nếu tác vụ thành công). Không coi `task.call()==false` là “lỗi không có vị trí”, cũng không coi việc map bytecode không rỗng là compiler đã thành công.

### 2.1. API nào làm gì?

| API | Vai trò | Lưu ý |
| --- | --- | --- |
| `ToolProvider.getSystemJavaCompiler()` | Tìm compiler hiện có của runtime. | Có thể trả `null` khi không có provider trong runtime image. |
| `JavaCompiler.getTask(...)` | Khởi tạo tác vụ biên dịch. | `call()` mới thực thi; task không dùng lại để compile lần thứ hai. |
| `SimpleJavaFileObject` | Base class cho source và class file object custom. | Source override `getCharContent`, class output override `openOutputStream`. |
| `JavaFileObject.Kind.SOURCE` | Kiểu logical Java source. | URI có đuôi `.java` và package/binary name tương ứng. |
| `JavaFileObject.Kind.CLASS` | Kiểu compiled class. | Output thường có đuôi `.class`; binary name có thể chứa `$`. |
| `StandardJavaFileManager` | File manager chuẩn: classpath, modules, file resources. | Đóng sau tác vụ, có thể có cache/file handles. |
| `ForwardingJavaFileManager` | Delegate mặc định, override chọn lọc. | Đỡ phải tự viết toàn bộ classpath/module resolution. |
| `StandardLocation.CLASS_OUTPUT` | Logical location cho class outputs. | Intercept location này trong memory manager. |
| `DiagnosticCollector` | Nhận danh sách diagnostics. | Cài đặt `DiagnosticListener` tiện cho UI/lint. |
| `Diagnostic` | Kind, source, message, code, line, column, offsets. | Không phải mọi diagnostic đều có position. |
| `ClassLoader.defineClass` | Tạo class từ bytes khi thực sự cần execute. | Không phải security sandbox. |

`JavaCompiler` nằm trong `java.compiler`; implementation/compiler service trong JDK thường được cung cấp bởi `jdk.compiler`. Khi sử dụng một runtime tối giản (ví dụ `jlink` image đã bỏ compiler), hãy phát hiện `null` và báo lỗi rõ.

## 3. Tạo source JavaFileObject chỉ từ String

Đây là lớp nguồn được dùng trong chương trình hoàn chỉnh:

```java
static final class SourceFile extends SimpleJavaFileObject {
    private final String text;

    SourceFile(String binaryName, String text) {
        super(URI.create("mem:///" + binaryName.replace('.', '/')
                + Kind.SOURCE.extension), Kind.SOURCE);
        this.text = text;
    }

    @Override
    public CharSequence getCharContent(boolean ignoreEncodingErrors) {
        return text;
    }
}
```

**Snippet**, cần `java.net.URI` và `javax.tools.SimpleJavaFileObject`. Với binary name `demo.Greeting`, URI là `mem:///demo/Greeting.java`. Đây là **logical URI**, không phải một file `/demo/Greeting.java` trên ổ đĩa.

Điểm cần nhớ:
- `getCharContent` trả `CharSequence` của nguồn, ở đây là Java `String`.
- `ignoreEncodingErrors` liên quan cách đọc bytes từ file object; String trong RAM không cần giải mã UTF-8.
- URI cần khác nhau cho các compilation units và khớp với public top-level class/package.
- Không dùng `StandardJavaFileManager.getJavaFileObjectsFromFiles` rồi tuyên bố nguồn không nằm trên disk: API đó mô tả file paths thật.
- Nếu sinh nhiều top-level classes, tạo danh sách nhiều `SourceFile` rồi đưa vào `getTask`.

**Bẫy:** không thể chỉ truyền source String trực tiếp vào `JavaCompiler.getTask` thay vì `JavaFileObject`. Compiler phải được cung cấp nguồn theo đúng abstraction `Iterable<? extends JavaFileObject>`.

## 4. Lưu class files trong RAM

### 4.1. ClassFile giữ ByteArrayOutputStream

```java
static final class ClassFile extends SimpleJavaFileObject {
    private final ByteArrayOutputStream bytes = new ByteArrayOutputStream();

    ClassFile(String binaryName, Kind kind) {
        super(URI.create("mem:///" + binaryName.replace('.', '/')
                + kind.extension), kind);
    }

    @Override
    public OutputStream openOutputStream() {
        return bytes;
    }

    byte[] toBytes() {
        return bytes.toByteArray();
    }
}
```

**Snippet**, cần `java.io.ByteArrayOutputStream`/`OutputStream`, `java.net.URI` và `SimpleJavaFileObject`. Khi compiler cần ghi class bytes, nó gọi `openOutputStream()`. `ByteArrayOutputStream.toByteArray()` trả bản sao an toàn để lưu trong kết quả.

### 4.2. MemoryManager mở rộng ForwardingJavaFileManager

```java
static final class MemoryManager
        extends ForwardingJavaFileManager<StandardJavaFileManager> {
    private final Map<String, ClassFile> compiled = new TreeMap<>();

    MemoryManager(StandardJavaFileManager delegate) {
        super(delegate);
    }

    @Override
    public JavaFileObject getJavaFileForOutput(
            JavaFileManager.Location location,
            String binaryName,
            JavaFileObject.Kind kind,
            FileObject sibling) throws IOException {
        if (location == StandardLocation.CLASS_OUTPUT
                && kind == JavaFileObject.Kind.CLASS) {
            ClassFile file = new ClassFile(binaryName, kind);
            compiled.put(binaryName, file);
            return file;
        }
        return super.getJavaFileForOutput(location, binaryName, kind, sibling);
    }

    Map<String, byte[]> getClassBytes() {
        Map<String, byte[]> result = new TreeMap<>();
        compiled.forEach((name, file) -> result.put(name, file.toBytes()));
        return result;
    }
}
```

**Snippet:** cần các imports `javax.tools.*`, `java.util.Map`/`TreeMap` và `java.io.IOException`. Dùng **một map theo binary name**, vì một source file có thể sinh nhiều class outputs như `Outer`, `Outer$Nested` hoặc các class khác.

`ForwardingJavaFileManager` chuyển những calls không override tới `StandardJavaFileManager`. Đây là phương pháp đúng cho bài cơ bản, tránh tự viết lại toàn bộ classpath/module lookup. Nhưng nó **chưa** chặn mọi loại output: generated source từ annotation processors có thể dùng `SOURCE_OUTPUT`, resource outputs có thể đi qua `getFileForOutput`. Bài dùng `-proc:none` để không chạy annotation processors ngoài ý muốn; nếu bật processors thì phải thiết kế thêm để đáp ứng yêu cầu “mọi thứ trong memory”.

### 4.3. Tại sao output bytes có thể tồn tại dù task thất bại?

Biên dịch nhiều source units là pipeline nhiều pha. Một compiler có thể tạo được một vài class bytes trước khi phát hiện lỗi ở source khác. Vì thế:
- `MemoryManager.getClassBytes()` là **những bytes đã được ghi**, không thay thế `CompilationTask.call()`.
- Khi `call()==false`, **discard toàn bộ generated classes**, không publish hay invoke chúng.
- Không suy `failed compile ⇒ empty map` là contract. Input sai cú pháp cụ thể trong demo cho map rỗng, nhưng đó chỉ là kết quả thực nghiệm.

## 5. Thu diagnostics và hiển thị vị trí

### 5.1. DiagnosticCollector và Diagnostic.Kind

```java
DiagnosticCollector<JavaFileObject> diagnostics =
        new DiagnosticCollector<>();
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException("JDK compiler provider required");
}
```

**Snippet**, trong code đầy đủ có đóng manager. `DiagnosticCollector` thu `Diagnostic<? extends JavaFileObject>` mà compiler phát. `Diagnostic.Kind` có:
- `ERROR` — lỗi biên dịch.
- `WARNING` — cảnh báo.
- `MANDATORY_WARNING` — cảnh báo bắt buộc.
- `NOTE` — ghi chú.
- `OTHER` — loại khác.

Số diagnostics > 0 **không có nghĩa compile thất bại**. Một tác vụ compile thành công có thể phát WARNING/NOTE. Hãy dựa trên `Boolean.TRUE.equals(task.call())` và chính sách xử lý warnings (nếu muốn `-Werror`, phải lựa chọn rõ).

### 5.2. Line, column, character offset: hai hệ đánh số

| API | Ý nghĩa | Quy ước |
| --- | --- | --- |
| `getSource()` | JavaFileObject liên quan tới diagnostic. | Có thể null. |
| `getLineNumber()` | Số dòng trong nguồn. | **1-based**; NOPOS nếu không có. |
| `getColumnNumber()` | Cột trên dòng. | **1-based**; NOPOS nếu không có. |
| `getPosition()` | Character offset từ đầu toàn bộ nguồn. | **0-based**; NOPOS nếu không có. |
| `getStartPosition()` | Start của vùng lỗi. | Offset 0-based; NOPOS khi không có. |
| `getEndPosition()` | End của vùng lỗi theo compiler. | Offset 0-based; NOPOS khi không có. |
| `getKind()` | Severity/category. | Dùng enum `Diagnostic.Kind`. |
| `getCode()` | Compiler diagnostic identifier. | Implementation-dependent, có thể null. |
| `getMessage(Locale)` | Message đã localize. | Text có thể thay đổi theo JDK/provider/locale. |

Vị trí có nghĩa theo Javadoc phải bảo đảm `start <= position <= end`. `Diagnostic.NOPOS` là sentinel cho **không có vị trí phù hợp**; không dùng nó làm index mảng. Với lỗi toàn cục, compiler options sai hoặc diagnostics không gắn một source cụ thể, `getSource()==null` và line/column NOPOS là tình huống hợp lệ.

**Character offset không phải UTF-8 byte offset.** Trong chương trình, `String` dùng các Java `char`/UTF-16 code units. Nếu trong source có emoji, ký tự supplementary hoặc tab, phải map tới visual editor columns cẩn thận. CRLF và newline normalization cũng ảnh hưởng tới offset từ đầu nguồn.

### 5.3. Ví dụ mã sai cú pháp

```java
package demo;
public class Broken {
    public int twice() {
        return 1 + ;
    }
}
```

Trong chương trình, đoạn trên có đúng **8 spaces** trước `return`; dấu `;` ở dòng 4, cột 20. Với OpenJDK 24 đã kiểm chứng, `getPosition()==80`, start/end cũng là 80. Không tự động suy mọi compiler sẽ chọn cùng một token/caret: các compiler providers hoặc JDK releases có thể đưa spans/messages khác.

**Đối với UI**, nên lưu source gốc không đổi để kết hợp diagnostics:
1. Kiểm tra `getSource()` có khớp compilation unit đang render.
2. Kiểm tra `line>=1`/`column>=1` và khác NOPOS.
3. Lấy `lines[line-1]`.
4. Với ASCII spaces như ví dụ, đặt `column-1` spaces trước dấu `^`.
5. Với tabs/Unicode/graphemes, chuyển từ character positions sang visual columns thay vì trực tiếp lặp spaces.
6. Escape source/message trước khi render HTML, tránh XSS.
7. Nếu thiếu position, hiển thị general error ở cấp task.

### 5.4. Không parse lỗi bằng message text

`getMessage(Locale.ENGLISH)` có ích để hiển thị, nhưng wording có thể đổi theo compiler/JDK/locale. Mã `getCode()` cũng phụ thuộc implementation. Không viết logic ứng dụng dựa vào việc message phải chứa cụm tiếng Anh cụ thể. Trong stdout kiểm chứng, bài chỉ in `diagnosticMessagePresent=true` thay vì chép một error message không ổn định.

## 6. Chương trình Java 17+ hoàn chỉnh: InMemoryCompileDemo.java

### 6.1. Ý tưởng của test

Chương trình thực hiện **hai compilation tasks**:
- **Positive:** source Java `demo.Greeting` chứa nested helper; compiler tạo **hai class binaries** trong map; loader chỉ nạp *mã do bài tự kiểm soát* để gọi `Greeting.hello("Java 17")`.
- **Negative:** `demo.Broken` chứa `return 1 + ;`; compiler trả `false`, `Diagnostic.Kind.ERROR` với source URI, dòng/cột và các offsets.

Bài dùng options `List.of("--release","17","-proc:none")` và `Locale.ENGLISH`. `--release` cố định Java language/API/bytecode target, `-proc:none` tắt annotation processing cho test này (không phải sandbox). Code chỉ dùng JDK standard library; không cần Maven/Gradle.

### 6.2. Toàn bộ mã

Lưu file `InMemoryCompileDemo.java` bằng UTF-8:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.lang.reflect.Method;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
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

public final class InMemoryCompileDemo {

    static final class SourceFile extends SimpleJavaFileObject {
        private final String text;

        SourceFile(String binaryName, String text) {
            super(URI.create("mem:///" + binaryName.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.text = text;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return text;
        }
    }

    static final class ClassFile extends SimpleJavaFileObject {
        private final ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        ClassFile(String binaryName, Kind kind) {
            super(URI.create("mem:///" + binaryName.replace('.', '/')
                    + kind.extension), kind);
        }

        @Override
        public OutputStream openOutputStream() {
            return bytes;
        }

        byte[] toBytes() {
            return bytes.toByteArray();
        }
    }

    static final class MemoryManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        private final Map<String, ClassFile> compiled = new TreeMap<>();

        MemoryManager(StandardJavaFileManager delegate) {
            super(delegate);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location,
                String binaryName,
                JavaFileObject.Kind kind,
                FileObject sibling) throws IOException {
            if (location == StandardLocation.CLASS_OUTPUT
                    && kind == JavaFileObject.Kind.CLASS) {
                ClassFile file = new ClassFile(binaryName, kind);
                compiled.put(binaryName, file);
                return file;
            }
            return super.getJavaFileForOutput(
                    location, binaryName, kind, sibling);
        }

        Map<String, byte[]> getClassBytes() {
            Map<String, byte[]> result = new TreeMap<>();
            compiled.forEach((name, file) -> result.put(name, file.toBytes()));
            return result;
        }
    }

    record CompileResult(boolean success,
            Map<String, byte[]> classes,
            List<Diagnostic<? extends JavaFileObject>> diagnostics) {}

    static CompileResult compile(String binaryName, String text)
            throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "This example requires a full JDK with compiler");
        }
        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();
        try (StandardJavaFileManager standard =
                     compiler.getStandardFileManager(
                         diagnostics, Locale.ENGLISH,
                         StandardCharsets.UTF_8)) {
            MemoryManager manager = new MemoryManager(standard);
            JavaCompiler.CompilationTask task = compiler.getTask(
                    null,
                    manager,
                    diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null,
                    List.of(new SourceFile(binaryName, text)));
            boolean successful = Boolean.TRUE.equals(task.call());
            return new CompileResult(
                    successful,
                    manager.getClassBytes(),
                    List.copyOf(diagnostics.getDiagnostics()));
        }
    }

    static final class MemoryClassLoader extends ClassLoader {
        private final Map<String, byte[]> binaries;

        MemoryClassLoader(ClassLoader parent, Map<String, byte[]> binaries) {
            super(parent);
            this.binaries = Map.copyOf(binaries);
        }

        @Override
        protected Class<?> findClass(String binaryName)
                throws ClassNotFoundException {
            byte[] code = binaries.get(binaryName);
            if (code == null) {
                throw new ClassNotFoundException(binaryName);
            }
            return defineClass(binaryName, code, 0, code.length);
        }
    }

    static void check(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }

    public static void main(String[] args) throws Exception {
        String good = "package demo;\n"
                + "public final class Greeting {\n"
                + "  public static String hello(String who) {\n"
                + "    return Helper.message(who);\n"
                + "  }\n"
                + "  private static final class Helper {\n"
                + "    static String message(String name) { return \"Xin chao, \" + name; }\n"
                + "  }\n"
                + "}\n";

        CompileResult ok = compile("demo.Greeting", good);
        check(ok.success(), "good compilation");
        check(ok.classes().keySet().equals(
                java.util.Set.of("demo.Greeting", "demo.Greeting$Helper")),
                "class output capture");
        boolean hasError = ok.diagnostics().stream()
                .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR);
        check(!hasError, "unexpected diagnostic");

        ClassLoader loader = new MemoryClassLoader(
                InMemoryCompileDemo.class.getClassLoader(), ok.classes());
        Class<?> type = Class.forName("demo.Greeting", true, loader);
        Method method = type.getMethod("hello", String.class);
        String greeting = (String) method.invoke(null, "Java 17");
        check(greeting.equals("Xin chao, Java 17"),
                "compiled method response");

        System.out.println("goodSuccess=" + ok.success());
        System.out.println("goodClasses=" + ok.classes().keySet());
        System.out.println("goodClassCount=" + ok.classes().size());
        System.out.println("goodErrorCount=" +
                ok.diagnostics().stream().filter(
                    d -> d.getKind() == Diagnostic.Kind.ERROR).count());
        System.out.println("goodGreeting=" + greeting);

        String bad = "package demo;\n"
                + "public class Broken {\n"
                + "    public int twice() {\n"
                + "        return 1 + ;\n"
                + "    }\n"
                + "}\n";

        CompileResult fail = compile("demo.Broken", bad);
        List<Diagnostic<? extends JavaFileObject>> errors =
                fail.diagnostics().stream().filter(
                    d -> d.getKind() == Diagnostic.Kind.ERROR).toList();
        check(!fail.success(), "invalid source compiled");
        check(errors.size() == 1, "expected 1 syntax diagnostic");
        check(fail.classes().isEmpty(), "bad code created class file");
        Diagnostic<? extends JavaFileObject> error = errors.get(0);

        check(error.getLineNumber() == 4, "error line");
        check(error.getColumnNumber() == 20, "error column");
        check(error.getSource() != null, "source absent");
        check(error.getPosition() >= 0, "offset unavailable");
        check(error.getStartPosition() <= error.getPosition(), "start/position");
        check(error.getEndPosition() >= error.getPosition(), "end/position");
        check(!error.getMessage(Locale.ENGLISH).isBlank(), "message absent");

        String[] badLines = bad.split("\\R", -1);
        String offendingLine = badLines[(int) error.getLineNumber() - 1];
        int caretOffset = (int) error.getColumnNumber() - 1;

        System.out.println("badSuccess=" + fail.success());
        System.out.println("badClassCount=" + fail.classes().size());
        System.out.println("diagnosticCount=" + errors.size());
        System.out.println("diagnosticKind=" + error.getKind());
        System.out.println("diagnosticFile=" + error.getSource().toUri());
        System.out.println("diagnosticLine=" + error.getLineNumber());
        System.out.println("diagnosticColumn=" + error.getColumnNumber());
        System.out.println("diagnosticPosition=" + error.getPosition());
        System.out.println("diagnosticStart=" + error.getStartPosition());
        System.out.println("diagnosticEnd=" + error.getEndPosition());
        System.out.println("sourceLine=" + offendingLine.trim());
        System.out.println("caret=" + " ".repeat(caretOffset) + "^");
        System.out.println("diagnosticMessagePresent=" +
                !error.getMessage(Locale.ENGLISH).isBlank());
    }
}
```

**Đây là một file Java độc lập, không phải pseudocode.** Các classes helper đều là nested types của `InMemoryCompileDemo`; mã nguồn `demo.Greeting` được tạo ở runtime từ String. Import `ArrayList` không được sử dụng và có thể bỏ, nhưng không ảnh hưởng compile.

### 6.3. Biên dịch/chạy

```bash
javac --release 17 -encoding UTF-8 InMemoryCompileDemo.java
java InMemoryCompileDemo
```

Kết quả biên dịch `InMemoryCompileDemo.java` thành .class trên disk là bình thường để chạy bản thân demo. **Hai .class thuộc package `demo` được sinh tại runtime đều được chặn bằng JavaFileManager vào memory.** Một compilation unit duy nhất sinh hai class binaries nhờ nested helper.

### 6.4. Stdout thật đã kiểm chứng

Chạy trên **OpenJDK 24**, code được biên dịch bằng `javac --release 17 -encoding UTF-8`; đúng **18 dòng stdout**:

```text
goodSuccess=true
goodClasses=[demo.Greeting, demo.Greeting$Helper]
goodClassCount=2
goodErrorCount=0
goodGreeting=Xin chao, Java 17
badSuccess=false
badClassCount=0
diagnosticCount=1
diagnosticKind=ERROR
diagnosticFile=mem:///demo/Broken.java
diagnosticLine=4
diagnosticColumn=20
diagnosticPosition=80
diagnosticStart=80
diagnosticEnd=80
sourceLine=return 1 + ;
caret=                   ^
diagnosticMessagePresent=true
```

Giải thích:
- `goodSuccess=true`, `goodClassCount=2`: compiler nhận source String và ghi hai class files vào RAM.
- `goodGreeting=...`: class loader chỉ chạy **source do ví dụ sở hữu**; đây là hành động chủ động, không tự xảy ra khi `task.call()`.
- `badSuccess=false`, `diagnosticCount=1`: source invalid bị compiler từ chối bằng `ERROR`.
- `diagnosticFile` là URI của in-memory `JavaFileObject`.
- `diagnosticLine=4`, `diagnosticColumn=20`: vị trí cho người đọc 1-based.
- `diagnosticPosition=80`, start/end=80: offset characters 0-based của source String.
- `caret=...^` chỉ hoạt động trực tiếp vì ví dụ sử dụng ASCII/spaces.
- `diagnosticMessagePresent=true` tránh phụ thuộc wording lỗi tiếng Anh có thể thay đổi.

**Tính di động:** một số compiler/JDK versions có thể chọn span hoặc số diagnostics hơi khác. Các assertion về cột 20 và số ERROR=1 được cố tình xác minh cho fixture này trên compiler đã dùng; khi làm hệ thống tổng quát, đừng buộc mọi compiler/JDK phải trả cùng message, error code hoặc exact token span.

## 7. Nhiều compilation units, classpath và modules

### 7.1. Biên dịch nhiều source files cùng lúc

`JavaCompiler.getTask` nhận `Iterable<? extends JavaFileObject>`, không giới hạn một source. Có thể tạo:

```java
List<JavaFileObject> units = List.of(
        new SourceFile("demo.Model", modelSource),
        new SourceFile("demo.Mapper", mapperSource),
        new SourceFile("demo.Service", serviceSource));

JavaCompiler.CompilationTask task = compiler.getTask(
        null, manager, diagnostics,
        List.of("--release", "17", "-proc:none"),
        null, units);
boolean success = Boolean.TRUE.equals(task.call());
```

**Snippet, không độc lập:** `modelSource`/`mapperSource`/`serviceSource` là các Strings tạo trước, `compiler`/`manager`/`diagnostics` đã khai báo. Cùng một task giúp compiler resolve references giữa các compilation units. `MemoryManager` phải giữ mọi outputs, không ghi đè map mỗi khi compiler sinh class thứ hai.

### 7.2. Dependencies và bộ phiên dịch mã

- `--release 17` giới hạn syntax/standard APIs và classfile target theo Java 17.
- `-classpath` cung cấp các dependencies nằm trên classpath, nếu generated source cần bên ngoài JDK.
- `--module-path` hỗ trợ named modules/JPMS khi build đúng module graph.
- `-proc:none` tắt annotation processors trong demo.
- `-Xlint`, `-Werror` có thể dùng nếu cần warning policy rõ ràng và compiler có hỗ trợ.

`--release` không làm classpath dependencies tự trở nên tương thích, không xử lý version xung đột của external JARs và không thay security isolation. Nên cố định compiler options theo môi trường build, không lấy raw flags từ request người dùng mà không kiểm soát.

Nếu muốn biên dịch source **sau** tham chiếu class bytes sinh từ một lần compile trước trong RAM, demo chưa đủ: còn phải triển khai input lookup trong `JavaFileManager` (như `getJavaFileForInput`, `list`, `inferBinaryName`, `contains` hoặc location handling phù hợp), hoặc xuất class bytes thành dependency artifact có kiểm soát.

### 7.3. Tái sử dụng file manager

Theo JavaCompiler Javadoc, `StandardJavaFileManager` có thể được reuse để tận dụng caches JAR/file. Tuy nhiên, với multi-tenant hoặc concurrent jobs:
- Bảo đảm lifecycle đóng đúng, không share mutable manager khi không thread-safe.
- Isolate diagnostics/output maps giữa các tasks.
- Có chính sách refresh nếu classpath JAR thay đổi.
- Không giữ unbounded caches/byte arrays/classloaders.
- Task mới cho source mới; đừng gọi `call()` lần hai trên cùng `CompilationTask`.

## 8. Annotation processing và “mã sinh” hai nghĩa

“Mã sinh” đôi khi nói về source Strings được hệ thống tự dựng; đôi khi nói về **annotation processors** chạy trong compiler, ví dụ `javax.annotation.processing.Processor` tạo source qua `Filer`. Cả hai đều hợp lệ nhưng **khác pipeline**:

| Trường hợp | Nguồn được tạo ở đâu? | File manager cần gì? |
| --- | --- | --- |
| Ứng dụng tạo `String` rồi gọi compiler | Runtime application; source đưa qua `getCharContent`. | SOURCE input và CLASS_OUTPUT output. |
| Annotation processor sinh source trong compile rounds | Trong javac, processor gọi `Filer`. | Cần thêm SOURCE_OUTPUT, generated source/resources, class lookup và nhiều rounds. |

Trong bài dùng `-proc:none`, không chạy annotation processors ngoài ý muốn; vì vậy manager chỉ chặn class output có thể đáp ứng mục tiêu. Nếu bật processors, **không thể hứa mọi generated files vẫn ở RAM** với manager hiện tại; phải mở rộng đúng các callbacks/output kinds và kiểm thử.

**Bảo mật:** annotation processor là code chạy ngay trong compilation process, với quyền của process. Nếu source hoặc classpath đến từ bên không tin cậy, đừng nạp processors/plugins không xác minh. Tắt `-proc:none` không phải sandbox hoàn chỉnh, vì compiler và code khi được classload có những attack surfaces khác.

## 9. Quản lý Diagnostic trong UI/editor thật

Một UI/IDE không nên lấy dòng/cột bằng cách parse `Diagnostic#getMessage`. Nên chuẩn hóa DTO:

```text
sourceUri
kind
lineNumber       (1-based hoặc NOPOS)
columnNumber     (1-based hoặc NOPOS)
position         (0-based hoặc NOPOS)
startPosition    (0-based hoặc NOPOS)
endPosition      (0-based hoặc NOPOS)
code             (tùy compiler, có thể null)
message          (localized, dùng để hiển thị)
```

**Đây là mô tả schema**, không phải JSON literal. Chỉ lấy source đã gửi compiler để render context; source URI `mem:///...` không phải địa chỉ HTTP có thể click/download ngoài mạng.

### 9.1. UTF-16, CRLF, tabs và Unicode

- Java `String` lập chỉ mục bằng UTF-16 code units; emoji có thể chiếm hai `char`.
- UTF-8 bytes không dùng cùng offset; đừng lấy `getPosition` để index vào `byte[]` UTF-8.
- `getColumnNumber` do compiler gán cho vị trí trong source, UI lại tính visual columns theo tab width và grapheme clusters.
- Cùng source có `\r\n` hoặc `\n` thì offsets/dòng có thể khác; không normalize lại source sau khi compile rồi dùng offsets cũ.
- Với highlight theo spans, xác nhận quy tắc end offset của compiler/provider và bảo vệ bounds trước khi tạo substring.
- Với `NOPOS`, giữ diagnostic global thay vì highlight index âm.

### 9.2. Messages và localization

Có thể dùng `getMessage(Locale.forLanguageTag("vi-VN"))` để yêu cầu locale, nhưng compiler provider **không bắt buộc** phải cung cấp bản dịch tiếng Việt; nó có thể trả chuỗi tiếng Anh hoặc khác version. Đừng coi diagnostic code/message là protocol public ổn định. Khi cần machine-readable classification, ưu tiên `Diagnostic.Kind`, source positions và domain logic riêng.

## 10. ClassLoader không phải sandbox

`MemoryClassLoader` trong chương trình gọi `defineClass(binaryName,byte[],...)`. Việc đó cho phép test end-to-end **với source tự tạo**, nhưng không nên dùng để chạy arbitrary Java source nhận từ người dùng:
- Class initialization, static initializers và invoked methods có thể chạy code thực sự.
- Code có thể đọc file, gọi network, tạo threads, consume CPU/heap, load native libs… theo quyền process.
- Parent-first class delegation có thể nạp class có cùng tên từ parent, gây version conflict.
- Class unloading phụ thuộc garbage collection của classloader cùng mọi references; xóa byte[] trong Map **không bắt JVM unload class ngay**.
- Java 17+ không cung cấp sandbox tổng quát chỉ bằng ClassLoader hoặc SecurityManager legacy.

Với untrusted source, nên **chỉ compile và trả diagnostics**, không execute. Nếu bắt buộc chạy, cần một environment cô lập ở cấp OS/process/container/VM, quyền filesystem/network tối thiểu, quotas/timeout, cách kill process và audit thích hợp. Không coi một regex allowlist imports hoặc `--release` là security boundary.

### 10.1. Các giới hạn tài nguyên

Ứng dụng production nên giới hạn source length, số compilation units, số class outputs, số jobs đồng thời, heap, CPU/wall-clock, số file handles và TTL cho cached classes. `CompilationTask.call()` không có contract timeout/hủy cưỡng bức an toàn; nếu phải đảm bảo deadline với input không tin cậy, tách compiler sang process có thể dừng.

### 10.2. Đóng file managers và giải phóng buffers

Code mẫu dùng:

```java
try (StandardJavaFileManager standard =
        compiler.getStandardFileManager(
            diagnostics, Locale.ENGLISH, StandardCharsets.UTF_8)) {
    MemoryManager manager = new MemoryManager(standard);
    // Tạo và thực hiện task, lấy bản sao class bytes khi task hoàn tất.
}
```

**Snippet:** sau khi task kết thúc, đóng standard manager tránh giữ JAR handles/caches. Trong hệ thống phức tạp, manager wrapper/standard có owner và close semantics cần được thiết kế nhất quán, không dùng closed manager cho task sau.

Class byte arrays và diagnostics cũng nên có vòng đời rõ; không cache theo tenant mãi mãi. Nếu chỉ trả lỗi, bỏ references tới classloader để có cơ hội GC.

## 11. Lỗi phổ biến và chẩn đoán

| Lỗi/hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `getSystemJavaCompiler()==null` | Runtime thiếu `jdk.compiler`/provider. | Dùng JDK đầy đủ hoặc custom image có compiler. |
| `class ... is public, should be declared in a file named ...` | Logical URI/binary name không đúng. | `mem:///demo/Greeting.java` khớp `demo.Greeting`. |
| `cannot find symbol` | Thiếu source cùng task hoặc dependency. | Bổ sung compilation units/classpath/modulepath. |
| `call()==false` nhưng không có ERROR có source | Diagnostic có thể global hoặc lỗi config/options. | Xử lý Kind và NOPOS, không suy lỗi phải gắn file. |
| `getColumnNumber()==NOPOS` | Không có position phù hợp. | Hiển thị general error, không index vào lines. |
| UI highlight lệch do emoji/tab | Nhầm byte/char/visual column. | Chuyển offset đúng với source đã gửi compiler. |
| Chỉ thấy `Greeting.class` | Manager lưu một output thay vì nhiều class names. | Map theo binaryName, giữ nested/synthetic classes. |
| Class bytes vẫn xuất ra đĩa | Dùng default output manager hoặc missed output kinds. | Chặn đúng CLASS_OUTPUT; kiểm tra processors/resources. |
| Có bytecode dù compile thất bại | Một phần output đã sinh. | Discard khi result=false, không load. |
| `ClassNotFoundException` khi invoke | Classloader không tìm thấy binaryName trong map. | Kiểm tra keys và parent delegation. |
| `NoClassDefFoundError` | Thiếu nested class/runtime dependency. | Giữ tất cả generated binaries và classpath đúng. |
| `LinkageError` khi compile lại cùng name | Class identity hoặc loader conflict. | Tạo classloader riêng, quản lý versions. |
| `OutOfMemoryError` sau nhiều jobs | Lưu byte arrays/classloaders/diagnostics vô hạn. | Bounded caches, TTL, quotas. |
| Warnings bị coi là fail | Chỉ đếm diagnostics thay vì `call()`. | So compiler result và Kind. |
| Lỗi compile ở máy khác có message khác | Provider/JDK/locale khác. | Không parse message string; test portable. |
| Processor sinh files ngoài RAM | Chưa intercept SOURCE_OUTPUT/resources. | Disable processors hoặc xây manager đầy đủ. |
| “Biên dịch trong RAM” mà compiler vẫn đọc disk | Compiler delegate JDK/classpath to StandardJavaFileManager. | Phân biệt in-memory generated input/output với diskless toàn hệ thống. |
| Classloader execute code nguy hiểm | Source chưa tin cậy. | Chỉ compile; nếu execute cần OS isolation. |

**Checklist debug nhanh:** kiểm tra JDK compiler → source URI/package/public name → compiler options → classpath/modulepath → manager intercept CLASS_OUTPUT → call() Boolean → diagnostics kinds/source/positions → partial outputs → optional classload/test khi source trusted.

## 12. Ma trận kiểm thử

| Trường hợp | Đầu vào | Kết quả nên xác nhận |
| --- | --- | --- |
| Source String hợp lệ | `demo.Greeting`. | `call()==true`, bytes tồn tại. |
| Nested helper | `Greeting.Helper`. | Có `demo.Greeting$Helper` trong Map. |
| Trusted execution | Gọi `hello("Java 17")`. | `Xin chao, Java 17`. |
| Syntax error | `return 1 + ;`. | ERROR, source URI, line/column. |
| Semantic error | Reference tên biến không khai báo. | ERROR; message tùy provider. |
| Two source files | Model + Mapper. | Resolve types giữa units. |
| Warning only | `-Xlint` case. | Kind.WARNING; compile có thể thành công. |
| NOPOS | Diagnostic không liên kết source. | UI không crash. |
| UTF-16/emoji | Unicode trước lỗi. | Caret xử lý code units/visual columns. |
| CRLF | Source Windows line endings. | Vị trí khớp exact source. |
| Multiple outputs | Inner/multiple classes. | Không overwrite map, đủ files. |
| Partial output failure | Một source fail sau source khác. | Không publish bytes. |
| Annotation processor | `-proc:none`. | Processor không được thực thi. |
| Multi-tenant loads | Hai versions cùng binary name. | Classloader isolation và cache lifecycle. |
| Missing compiler | Custom runtime image. | Message rõ, không NullPointerException. |
| Security test | Input ngoài/đồ thị code quá lớn. | Resource isolation, không execute. |
| Compatibility | JDK 17/21/25. | API hoạt động, diagnostics format có fallback. |

## 13. Bài tập mở rộng

1. **Nhiều source files:** Sinh ``demo.User`` và ``demo.UserMapper``, đưa cùng `getTask` và khẳng định có cả hai class outputs.
2. **Semantic error:** Dùng `return unknownValue;` để tạo lỗi phân giải tên. Thu `Kind.ERROR`, line/column/offset, nhưng không assert message nguyên văn.
3. **Diagnostics DTO:** Chuyển diagnostic thành record với `sourceUri`, `kind`, `line`, `column`, `start`, `end`, `message`; bỏ qua NOPOS hoặc render global errors.
4. **Unicode tests:** Chèn emoji, tab và CRLF trước vị trí lỗi, so sánh compiler offset với editor visual columns.
5. **Warning policy:** Dùng `-Xlint`, hiển thị warnings riêng; nếu cần fail-on-warning, cấu hình `-Werror` sau khi kiểm chứng compiler.
6. **Cache:** Cache outputs theo hash source/options/dependencies, hạn chế bộ nhớ và tránh chia sẻ giữa tenants.
7. **Compile only:** Bỏ `MemoryClassLoader` hoàn toàn, trả diagnostics và artifacts only; phù hợp service validate code.
8. **In-memory dependency:** Mở rộng manager để compiler tìm class bytes từ lần compile trước qua input lookups đúng contract.
9. **JPMS:** Tạo module với `requires java.compiler;`; bảo đảm runtime có compiler provider.
10. **Annotation processing:** Thử processor được tin cậy sinh một source, xây SOURCE_OUTPUT/resource handling trong RAM và test rounds.
11. **Resource limits:** Chạy compiler worker process tách biệt với giới hạn memory/time và cleanup.
12. **Portability:** Chạy test trên Java 17, 21, 25; so ERROR/location semantics, không so hard-coded localized messages.

## 14. FAQ

**1. Có thể compile một String Java mà không tạo .java trên đĩa?** Có. Dùng `SimpleJavaFileObject.Kind.SOURCE` và `getCharContent` trả String.

**2. Vì sao cần custom JavaFileManager?** Để `getJavaFileForOutput(CLASS_OUTPUT, ..., Kind.CLASS)` trả output stream ghi bytes vào RAM thay vì default output.

**3. Chỉ DiagnosticCollector đã đủ chặn .class xuất ra disk chưa?** Không; nó chỉ nhận lỗi, còn FileManager quyết định class output.

**4. JavaCompiler có trong mọi JRE không?** Không bảo đảm. `ToolProvider.getSystemJavaCompiler` có thể null khi thiếu provider, thường cần đầy đủ JDK.

**5. `--release 17` có bảo đảm source an toàn để chạy?** Không. Nó điều khiển language/API/bytecode compatibility, không cấp sandbox.

**6. Dấu `$` trong `Greeting$Helper` nghĩa là gì?** Đây là binary name của nested class, thường có class output riêng.

**7. Khi compile failed mà memory manager còn bytes thì dùng được không?** Không nên; đó có thể là partial artifacts. Chỉ publish sau successful task.

**8. getLineNumber/getColumnNumber bắt đầu từ 0 hay 1?** Từ **1**; `getPosition` là character offset từ **0**.

**9. getPosition có phải số bytes trong UTF-8 không?** Không, là character offset trong source; Java String dùng UTF-16 code units.

**10. Khi getSource null hoặc NOPOS phải làm gì?** Hiển thị một general diagnostic, không tính caret/mảng từ giá trị âm.

**11. Có thể parse nguyên getMessage(Locale) để xác định loại lỗi?** Không ổn định; dùng `Diagnostic.Kind` và vị trí, message chỉ cho người dùng đọc.

**12. Có thể nạp generated class luôn khi compile thành công?** Có thể về kỹ thuật, nhưng **không nên nạp code không tin cậy**. ClassLoader không là security sandbox.

**13. Vì sao example dùng -proc:none?** Để không chạy annotation processors; nếu bật processors thì cần trust và quản lý file outputs bổ sung.

**14. JavaCompiler tự lưu bytecode vào ClassLoader không?** Không. Class bytes là outputs của file manager; nạp Class là bước riêng, tùy nhu cầu.

**15. Tại sao compiler vẫn truy cập disk dù nguồn/class outputs trong RAM?** Vì StandardJavaFileManager có thể truy cập JDK modules, classpath và JAR resources.

**16. Những API này còn được hỗ trợ ở Java 25 không?** Có, `javax.tools` JavaCompiler/Diagnostic/file managers là API được tài liệu hóa hiện nay.

**17. Có nên chia sẻ một StandardJavaFileManager cho nhiều threads cùng lúc?** Cần đồng bộ và thiết kế lifecycle phù hợp; không mặc định thread-safe cho mọi workload/provider.

**18. Dòng/cột và span có chắc giống trên mọi JDK không?** Không. Contract đánh số giống nhau, nhưng vị trí parser chọn, số diagnostics và wording có thể khác.

## 15. Checklist triển khai an toàn

- [ ] JDK/compiler provider có mặt; xử lý `getSystemJavaCompiler()==null` rõ ràng.
- [ ] Mỗi generated compilation unit có logical URI, package và public class name đúng.
- [ ] `SourceFile` trả source nguyên văn từ `String` bằng `getCharContent`.
- [ ] `MemoryManager` intercept `StandardLocation.CLASS_OUTPUT`/`Kind.CLASS` cho mọi binary names.
- [ ] Byte streams được snapshot/copy và có memory limits.
- [ ] `getTask` nhận đúng sources/options/file manager/diagnostic listener.
- [ ] `CompilationTask.call()` được gọi một lần, Boolean thành công được kiểm tra trước publish.
- [ ] Diagnostics được gom theo Kind; xử lý source null, line/column/positions = NOPOS.
- [ ] UI biết line/column 1-based, offsets 0-based; xử lý Unicode/CRLF/tabs và HTML escaping.
- [ ] Không dựa vào messages hoặc codes implementation-dependent như một protocol.
- [ ] Nếu không cần processors thì `-proc:none`; nếu bật thì trust và mở rộng file manager.
- [ ] Compiler options, classpath, modulepath do hệ thống kiểm soát.
- [ ] Không nạp/chạy generated code không được tin; cần isolation OS-level nếu bắt buộc thực thi.
- [ ] Có quotas, concurrency controls, cancellation strategy, bounded caches và cleanup.
- [ ] File managers đóng đúng sau compile, không rò JAR handles/classloaders.
- [ ] Kiểm thử trên Java 17/21/25 và compiler/runtime provider thực tế.

## 16. Tài liệu chính thức

- [Java SE 17 — JavaCompiler](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html): getTask, StandardJavaFileManager, diagnostics.
- [Java SE 25 — JavaCompiler](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/JavaCompiler.html): API hiện hành.
- [Java SE 17 — ToolProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html): getSystemJavaCompiler.
- [Java SE 17 — SimpleJavaFileObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html): in-memory source/output.
- [Java SE 17 — JavaFileObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaFileObject.html): source/class file kinds.
- [Java SE 17 — ForwardingJavaFileManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ForwardingJavaFileManager.html): output interception.
- [Java SE 17 — StandardJavaFileManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html): delegate, resources, lifecycle.
- [Java SE 17 — Diagnostic](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/Diagnostic.html): 1-based lines/columns, 0-based positions, NOPOS, messages.
- [Java SE 25 — Diagnostic](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/Diagnostic.html): contract tiếp tục áp dụng.
- [Java SE 17 — DiagnosticCollector](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/DiagnosticCollector.html): nhận diagnostics.
- [Java SE 17 — JavaFileManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaFileManager.html): standard locations và file abstractions.
- [Java SE 17 — StandardLocation](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/StandardLocation.html): CLASS_OUTPUT, SOURCE_OUTPUT.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): nạp class bytes.

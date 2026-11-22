# 16.3. Biểu diễn mã nguồn bằng JavaFileObject và SimpleJavaFileObject

> **Bối cảnh:** Bài Knowledge thuộc **16. Biên dịch lúc chạy** của module **Java Advance – dynamic-runtime**. Trọng tâm là cơ chế biểu diễn một đơn vị mã nguồn Java dưới dạng đối tượng `javax.tools.JavaFileObject`, và cách kế thừa `SimpleJavaFileObject` để cung cấp mã nguồn từ **`String`/bộ nhớ** cho compiler API chuẩn (JSR 199) trong Java 21. Bài cũng giải thích việc phân biệt nguồn `SOURCE` với đầu ra `CLASS`, file manager, kết quả biên dịch, diagnostics, class loading và các giới hạn thực tế. Mọi ví dụ chạy bằng JDK, không dùng thư viện bytecode bên ngoài.

## 1. Kết quả cần đạt và kiến thức nền

Sau bài này, bạn cần thực hiện được:

1. Phân biệt `FileObject`, `JavaFileObject`, `SimpleJavaFileObject`, `JavaFileManager`, `StandardJavaFileManager` và `JavaCompiler.CompilationTask`.
2. Biết `Kind.SOURCE` khác `Kind.CLASS`, khi nào dùng `getCharContent`, `openReader`, `openInputStream`, `openOutputStream`, và method mặc định nào của `SimpleJavaFileObject` ném `UnsupportedOperationException`.
3. Xây dựng `StringSource` đúng bằng `URI.create("string:///.../Name.java")`, ánh xạ **binary class name** thành đường dẫn package, và giữ `Kind.SOURCE`.
4. Đưa một hoặc nhiều `JavaFileObject` vào `JavaCompiler.getTask(... compilationUnits)`, dùng `ToolProvider.getSystemJavaCompiler()`, xử lý khi compiler không có, đóng file manager và đọc kết quả `call()`.
5. Biên dịch source nằm trong memory nhưng ghi `.class` vào thư mục tạm; phân biệt **vị trí input source** và **vị trí output bytecode**.
6. Biên dịch **cả source lẫn class output trong bộ nhớ** bằng `ForwardingJavaFileManager` và `SimpleJavaFileObject` kiểu `CLASS`, rồi nạp class đã tạo qua `ClassLoader`.
7. Biên dịch nhiều source units cùng một task và thu thập `DiagnosticCollector` để gắn dòng lỗi về URI của source object.
8. Nhận diện giới hạn: không đồng nhất JavaFileObject với file trên đĩa, không tự mở URL scheme `string:` qua mạng, không giả định compiler API là sandbox cho mã không tin cậy.
9. Tự chạy năm chương trình Java 21 độc lập, hiểu ý nghĩa và giới hạn của từng dòng stdout.

**Kiến thức trước:** class/package và file `.java`; `String`, `URI`, `Reader`, `OutputStream`; `ClassLoader` và Reflection; `try-with-resources`; nền tảng `javac`. Bài dùng API trong module `java.compiler` và implementation compiler thông thường thuộc JDK (`jdk.compiler`).

## 2. Vì sao compiler không chỉ nhận đường dẫn tệp?

Một compiler thường đọc mã nguồn từ `src/com/example/Hello.java` và ghi bytecode vào `out/com/example/Hello.class`. Tuy nhiên các hệ thống plugin, templating, expression engine hoặc code generation có thể tạo mã Java ngay trong RAM, từ cơ sở dữ liệu hay một nguồn khác. Để không buộc mọi compiler gắn chặt với `Path`/`File`, API `javax.tools` cung cấp **trừu tượng file object**.

```text
Nguồn ký tự Java
  |
  +--- file thật ----------- StandardJavaFileManager -----------+
  |                                                            |
  +--- String trong RAM ----- StringSource extends             |
                             SimpleJavaFileObject             |
                                          |                     |
                                          v                     v
                                   JavaFileObject SOURCE (compilationUnits)
                                          |
                                          v
                      JavaCompiler.getTask(...).call()
                                          |
                            Compiler yêu cầu FileManager xuất kết quả
                                          |
                          +---------------+----------------+
                          |                                |
               .class trên đĩa                  BytecodeOutput CLASS trong RAM
            StandardJavaFileManager              ForwardingJavaFileManager
                          |                                |
                     URLClassLoader                  ClassLoader#defineClass
```

Một **`JavaFileObject`** mang thông tin “đây là source Java ở URI này, với nội dung này” hoặc “đây là class output ở URI này, có stream ghi bytes”. Điều đó không đồng nghĩa nó **là** một tệp hệ điều hành. `URI` có thể là `string:///...` hay `mem:///...` chỉ dùng để định danh object; JVM không tự mở mạng hay ổ đĩa từ những scheme ví dụ đó.

### 2.1. Hai chiều data flow

- **Input:** compiler đọc `JavaFileObject.Kind.SOURCE` thông qua nội dung ký tự (`getCharContent`, `openReader` hoặc API đọc tương ứng).
- **Output:** file manager cung cấp `JavaFileObject.Kind.CLASS` để compiler ghi bytecode. Trong ví dụ memory, output object phải triển khai `openOutputStream`.
- **Diagnostic:** compiler report lỗi, warning và vị trí source qua `DiagnosticListener`/`DiagnosticCollector`; `Diagnostic.getSource()` có thể trỏ tới chính JavaFileObject đầu vào.
- **Load/execute:** là bước **riêng** sau compile. `JavaCompiler` không tự chạy `main` hoặc gọi static method mới sinh.

Chính sự tách bạch này làm API hữu ích cho biên dịch động nhưng cũng yêu cầu quản lý class loading và quyền thực thi nghiêm ngặt.

## 3. Phân biệt các interface và class trong javax.tools

| API | Vai trò | Dữ liệu quan trọng |
| --- | --- | --- |
| `FileObject` | Trừu tượng file cho công cụ nói chung, không chỉ Java | `toUri()`, `getName()`, `getCharContent`, streams, timestamp, delete |
| `JavaFileObject` | `FileObject` có ngữ nghĩa source/class Java | `getKind()`, `isNameCompatible()`, `getNestingKind()`, `getAccessLevel()` |
| `SimpleJavaFileObject` | Base class giúp viết JavaFileObject tùy biến ít mã | Constructor `(URI,Kind)`; defaults cho tên, kind, reader, streams |
| `JavaCompiler` | Compiler lập trình được | `getTask(...)`, `getStandardFileManager(...)` |
| `JavaCompiler.CompilationTask` | Một nhiệm vụ biên dịch | `call()` trả thành công/thất bại |
| `DiagnosticCollector<JavaFileObject>` | Gom diagnostics từ compiler | `getDiagnostics()` và `Diagnostic` location |
| `JavaFileManager` | Tra nguồn classpath/modules và chọn nơi lưu outputs | `getJavaFileForOutput`, `getJavaFileForInput`, `list`... |
| `StandardJavaFileManager` | File manager làm việc với filesystem/JAR/Path | Các methods lấy `JavaFileObject` từ `Path`/`File` |
| `ForwardingJavaFileManager` | Lớp wrapper chuyển tiếp đến một manager khác | Override có chọn lọc, ví dụ bắt `CLASS` output |

`JavaFileObject` là **interface**; `SimpleJavaFileObject` chỉ là một trong các implementation. Khi đã có tệp thật, `StandardJavaFileManager.getJavaFileObjectsFromPaths(Collection<Path>)` thường phù hợp hơn tự viết subclass. Khi nguồn là chuỗi đang ở memory, `SimpleJavaFileObject` là lựa chọn gọn, vì nó đã triển khai phần lớn chi tiết cơ sở.

### 3.1. Nguyên tắc phân vai

Không dùng một `JavaFileObject.Kind.SOURCE` để chứa bytecode `.class`; không dùng `CLASS` rồi chỉ override `getCharContent` để giả làm source. Kinds thể hiện **loại dữ liệu**, còn các stream methods cung cấp **cách dữ liệu di chuyển**.

Một compiler không có nghĩa được phép bỏ qua contract của JavaFileManager. Khi bạn muốn thay cách tạo class outputs, cách chuẩn là **điều chỉnh file manager**, không cố đoán compiler sẽ ghi bytes vào nơi nào dựa trên source URI.

## 4. JavaFileObject.Kind: SOURCE, CLASS, HTML, OTHER

`JavaFileObject.Kind` là enum chỉ loại file object:

| Kind | Extension | Ý nghĩa và ví dụ |
| --- | --- | --- |
| `SOURCE` | `.java` | Compilation unit: `com/acme/Widget.java` |
| `CLASS` | `.class` | Bytecode output/input: `com/acme/Widget.class` |
| `HTML` | `.html` | Tài liệu HTML mà Java tools có thể thao tác |
| `OTHER` | chuỗi rỗng | Các file khác, ví dụ metadata hoặc tài nguyên tùy công cụ |

`Kind.SOURCE.extension` là `".java"`; `Kind.CLASS.extension` là `".class"`. Dùng extension của enum để giảm hard-code. `isNameCompatible(simpleName,kind)` kiểm tra sự tương hợp giữa **simple name** và loại/đường dẫn file object, không xác thực cú pháp source text bên trong.

### 4.1. Constructor và fields

`SimpleJavaFileObject` cung cấp constructor **protected**:

```java
// Chỉ là mẫu bên trong một subclass của SimpleJavaFileObject.
super(URI.create("string:///com/acme/Widget.java"), Kind.SOURCE);
```

Superclass lưu `protected final URI uri` và `protected final Kind kind`. `toUri()` trả định danh; `getKind()` trả loại. `getName()` dùng cho tên thân thiện với người và vị trí diagnostics; giá trị cụ thể của tên có thể là URI path, tùy implementation và contract, **không phải** binary class name.

`getNestingKind()` và `getAccessLevel()` trong base implementation trả `null` vì đó chỉ là **hint**. Nếu bạn đã biết thông tin chuẩn, có thể override có trách nhiệm; đừng suy `null` nghĩa class chắc chắn là top-level hoặc package-private.

### 4.2. Những methods mặc định hay gây bất ngờ

Theo Javadoc Java SE 21:

- `SimpleJavaFileObject.getCharContent(boolean)` mặc định ném `UnsupportedOperationException`.
- `openInputStream()` và `openOutputStream()` mặc định cũng ném `UnsupportedOperationException`.
- `openReader(boolean)` bọc kết quả `getCharContent(...)` vào `Reader`; nếu bạn override `getCharContent` để trả String, `openReader` sẽ dùng được.
- `openWriter()` bọc `openOutputStream()`; chỉ hoạt động nếu output stream được hỗ trợ.
- `getLastModified()` mặc định trả `0L`; `delete()` mặc định không xóa và trả `false`.
- `isNameCompatible(simpleName, kind)` mặc định xem URI path có khớp `simpleName + kind.extension` hoặc kết thúc bằng `"/" + simpleName + kind.extension` hay không, **đồng thời kind phải khớp**.

Không bắt các exceptions này và âm thầm đổi thành chuỗi rỗng: bạn sẽ che lỗi implementation và khiến compiler nhận source trống.

## 5. Thiết kế StringSource: từ binary name đến URI

Cách triển khai cơ bản tương thích Java 21:

```java
// Trích đoạn class; bản chương trình độc lập ở Lab 1.
static final class StringSource extends SimpleJavaFileObject {
    private final String code;

    StringSource(String binaryName, String code) {
        super(URI.create("string:///" + binaryName.replace('.', '/')
                + Kind.SOURCE.extension), Kind.SOURCE);
        this.code = code;
    }

    @Override
    public CharSequence getCharContent(boolean ignoreEncodingErrors) {
        return code;
    }
}
```

Giả sử `binaryName="demo.Hello"`, URI thành `string:///demo/Hello.java`. Compiler xem đây như nguồn Java thuộc package `demo` với public top-level class `Hello`. Không cần file thật ở `/demo/Hello.java` trên OS.

**Có ba phần phải nhất quán:**

1. **Tên định danh:** `binaryName` là tên đầy đủ dạng dấu chấm, ví dụ `com.acme.Hello`.
2. **URI path:** thay `.` của package thành `/` và thêm `Kind.SOURCE.extension`, cho `string:///com/acme/Hello.java`.
3. **Source declaration:** bên trong `code` phải có `package com.acme;` và public top-level type tên `Hello` tương ứng. Compiler dùng tên file/compilation unit để kiểm tra tên public top-level type khi cần.

Nếu đặt `"demo.Hello"` mà mã là `public class Other`, compiler có thể báo `Other` phải được khai báo trong file `Other.java`. URI dùng cho diagnostic và các name-compatibility checks; **nó không tự đổi tên class trong mã nguồn**.

### 5.1. Chọn URI an toàn

- Dùng absolute URI với scheme rõ như `string:///...`, path chuẩn, extension đúng; `"Hello.java"` tương đối không phải mẫu ổn định cho một virtual source.
- Không ghép tên class từ input tùy tiện rồi gọi `URI.create`. Hãy validate binary name/package, loại bỏ path traversal, URI reserved characters và input lạ; nếu cần mã hóa ký tự, dùng constructor `URI` theo từng thành phần.
- Class lồng nhau không cần source file riêng cho `Outer$Inner` nếu nó nằm trong `Outer.java`; input compilation unit thường mang **top-level type name**.
- `package-info.java` và `module-info.java` là các compilation units đặc biệt. Không áp dụng mù quáng quy tắc “mọi source có một binary public class name”.
- `getName()` là tên để con người đọc, `toUri()` là identifier; đừng đồng nhất chúng với `Class.getName()` hoặc dùng để tạo classloader identity.

### 5.2. Kind đúng nhưng chưa có nội dung

Subclass chỉ gọi `super(uri, Kind.SOURCE)` **không đủ** để biểu diễn source String: compiler có thể yêu cầu đọc ký tự, và mặc định `getCharContent` ném `UnsupportedOperationException`. Đây là override trọng tâm của toàn bộ bài.

## 6. Lab 1 — JavaFileObject nguồn trong RAM

Lưu file **`SourceObjectBasicsLab.java`**:

```java
import java.io.Reader;
import java.net.URI;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;

public class SourceObjectBasicsLab {
    static final class StringSource extends SimpleJavaFileObject {
        private final String source;

        StringSource(String binaryName, String source) {
            super(URI.create("string:///" + binaryName.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.source = source;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return source;
        }
    }

    public static void main(String[] args) throws Exception {
        String source = "package demo; public class Hello {}";
        JavaFileObject file = new StringSource("demo.Hello", source);

        System.out.println("kind=" + file.getKind());
        System.out.println("uri=" + file.toUri());
        System.out.println("name=" + file.getName());
        System.out.println("compatibleHello=" +
                file.isNameCompatible("Hello", JavaFileObject.Kind.SOURCE));
        System.out.println("compatibleWrongName=" +
                file.isNameCompatible("Other", JavaFileObject.Kind.SOURCE));
        System.out.println("compatibleWrongKind=" +
                file.isNameCompatible("Hello", JavaFileObject.Kind.CLASS));
        System.out.println("sameSource=" +
                source.contentEquals(file.getCharContent(false)));
        try (Reader r = file.openReader(false)) {
            System.out.println("firstCharacter=" + (char) r.read());
        }
        System.out.println("timestamp=" + file.getLastModified());

        try {
            file.openInputStream();
            System.out.println("input=unexpected");
        } catch (UnsupportedOperationException expected) {
            System.out.println("input=UnsupportedOperationException");
        }

        try {
            file.openOutputStream();
            System.out.println("output=unexpected");
        } catch (UnsupportedOperationException expected) {
            System.out.println("output=UnsupportedOperationException");
        }
    }
}
```

**Lệnh (JDK 21 hoặc JDK mới hơn hỗ trợ `--release 21`):**

```sh
javac --release 21 -Xlint:all SourceObjectBasicsLab.java
java SourceObjectBasicsLab
```

**Stdout kiểm chứng trên JDK được dùng để chạy lab:**

```text
kind=SOURCE
uri=string:///demo/Hello.java
name=/demo/Hello.java
compatibleHello=true
compatibleWrongName=false
compatibleWrongKind=false
sameSource=true
firstCharacter=p
timestamp=0
input=UnsupportedOperationException
output=UnsupportedOperationException
```

### 6.1. Đọc output

- `getKind()` cho `SOURCE` vì constructor nhận `Kind.SOURCE`.
- `toUri()` bảo toàn scheme `string` và path từ binary name. Dòng `getName()` là tên dễ đọc ở implementation được thử; Javadoc không yêu cầu mọi JavaFileObject trả **đúng cùng một định dạng tên thân thiện**.
- `isNameCompatible("Hello",SOURCE)` đúng vì path kết thúc `/Hello.java` và kind khớp. `Other` sai tên, `CLASS` sai kind.
- `getCharContent(false)` trả source String đúng bytecode-independent, còn `openReader(false)` đọc ký tự đầu tiên là `p` của `package`.
- `timestamp=0` là giá trị mặc định của base class, không phải thời điểm bạn khởi tạo StringSource.
- `openInputStream`/`openOutputStream` chưa override, vì vậy hai lời gọi bị từ chối. Đây không phải lỗi compiler: class được thiết kế chỉ cho phép đọc source dưới dạng ký tự.

## 7. Chuỗi đã có sẵn và vấn đề encoding

`getCharContent(boolean ignoreEncodingErrors)` làm việc với **CharSequence đã được giải mã thành ký tự Java**. Nếu source đã là một `String` hợp lệ, bản thân `getCharContent` không phải chạy một decoder byte-stream nên tham số `ignoreEncodingErrors` thường không ảnh hưởng nội dung:

```java
// Getter minh họa trong StringSource:
@Override
public CharSequence getCharContent(boolean ignoreEncodingErrors) {
    return code;
}
```

Nhưng nếu bạn viết JavaFileObject đọc từ **byte[]**, file nén hoặc network stream, encoding trở thành trách nhiệm thật. Khi ấy cần tôn trọng contract `ignoreEncodingErrors` cùng charset và diagnostics/replace policy. Không đánh đồng “không có encoding errors trong String đã có” với “mọi đầu vào byte đều có thể bỏ qua encoding”.

### 7.1. Khi nào dùng openReader và openInputStream?

- Với `Kind.SOURCE` của StringSource, `getCharContent` là đường đơn giản nhất. `openReader` kế thừa implementation đã bọc CharSequence, nên không cần override riêng.
- Nếu backend là file/byte array, bạn có thể override `openInputStream` hoặc `openReader` phù hợp contract và thực tế compiler/file manager tương ứng.
- Với `Kind.CLASS`, bytecode là dữ liệu **nhị phân**, nên ví dụ output memory override `openOutputStream` để compiler ghi bytes; không được dùng Java `String` để giữ bytes binary vì có thể phá dữ liệu.
- `StandardJavaFileManager` chịu trách nhiệm encoding khi làm việc với source files trên disk; `getStandardFileManager(..., charset)` cho phép chọn charset tương ứng. Đừng ép Java source String đã đúng thành bytes rồi decode lại vô ích.

### 7.2. Nội dung có thể thay đổi không?

Nên giữ `code` là `private final String`. Một `CharSequence` tùy biến có thể mutable; nếu nguồn thay đổi giữa các lần compiler đọc, diagnostic line/positions và kết quả parse có thể không ổn định. Với compilation unit dạng memory, cách tốt là **tạo snapshot String bất biến** cho từng task.

## 8. Nối JavaFileObject với JavaCompiler.getTask

`ToolProvider.getSystemJavaCompiler()` trả compiler tích hợp khi JDK runtime có implementation `jdk.compiler`; có thể trả **`null`** ở image đã rút gọn không chứa compiler. Luôn kiểm tra trước khi dùng API.

Hình dạng API chính:

```java
// Chữ ký minh họa đã lược bỏ tên kiểu generic chi tiết:
JavaCompiler.CompilationTask getTask(
        Writer out,
        JavaFileManager fileManager,
        DiagnosticListener<? super JavaFileObject> diagnosticListener,
        Iterable<String> options,
        Iterable<String> classes,
        Iterable<? extends JavaFileObject> compilationUnits);
```

Mỗi tham số:

| Tham số | Chức năng |
| --- | --- |
| `out` | Writer cho output không thuộc diagnostics hoặc output tool; `null` dùng mặc định |
| `fileManager` | Tra classpath/module path và tạo outputs; `null` để compiler dùng standard manager |
| `diagnosticListener` | Nhận errors/warnings; dùng `DiagnosticCollector<JavaFileObject>` |
| `options` | Tùy chọn giống `javac`, ví dụ `--release`, `-d`, `-proc:none` |
| `classes` | Tên classes cho annotation processing trong những trường hợp hỗ trợ; **không phải danh sách compilation units** |
| `compilationUnits` | Iterable chứa các `JavaFileObject` nguồn cần biên dịch |

**Lệnh quan trọng:** `Boolean ok = compiler.getTask(...).call()` thực thi công việc. Tạo task object hoặc tạo `JavaFileObject` chưa chạy compiler. Một `CompilationTask` không được thiết kế để gọi `call()` nhiều lần; muốn biên dịch request khác, tạo task mới.

### 8.1. Cú pháp một lần biên dịch từ source memory

```java
// Đoạn minh họa: compiler, fileManager, diagnostics, source, outDir đã có.
boolean ok = compiler.getTask(
        null,
        fileManager,
        diagnostics,
        List.of("--release", "21", "-proc:none", "-d", outDir.toString()),
        null,
        List.of(source)
).call();
```

`"--release", "21"` yêu cầu biên dịch cho Java 21. `"-proc:none"` tắt annotation processing trong các lab để giảm side effects và làm output xác định. `"-d"` chỉ định **đầu ra class files**, không biến input source URI thành file thật.

Một số lỗi trong compiler có thể là `Diagnostic.Kind.ERROR`; `call()` trả `false` khi compilation thất bại. Đừng coi việc `getTask` không ném exception đồng nghĩa compile thành công.

## 9. Lab 2 — mã nguồn trong String, class output ra thư mục tạm

Tạo file độc lập **`CompileToDirectoryLab.java`**:

```java
import java.net.URI;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class CompileToDirectoryLab {
    static final class StringSource extends SimpleJavaFileObject {
        private final String code;

        StringSource(String name, String code) {
            super(URI.create("string:///" + name.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
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
            throw new IllegalStateException("JDK compiler unavailable");
        }

        JavaFileObject unit = new StringSource("demo.Calculator",
                "package demo; public class Calculator { " +
                "public static int add(int a, int b) { return a + b; } }");

        Path out = Files.createTempDirectory("java-compiler-lab-");
        try {
            DiagnosticCollector<JavaFileObject> diagnostics =
                    new DiagnosticCollector<>();
            boolean ok;
            try (StandardJavaFileManager manager =
                    compiler.getStandardFileManager(diagnostics, null, null)) {
                ok = compiler.getTask(null, manager, diagnostics,
                        List.of("--release", "21", "-proc:none", "-d", out.toString()),
                        null, List.of(unit)).call();
            }

            System.out.println("compiled=" + ok);
            System.out.println("errorCount=" +
                    diagnostics.getDiagnostics().stream()
                            .filter(d -> d.getKind() == Diagnostic.Kind.ERROR).count());
            System.out.println("classFile=" +
                    Files.isRegularFile(out.resolve("demo/Calculator.class")));

            try (URLClassLoader loader = new URLClassLoader(
                    new URL[] {out.toUri().toURL()}, ClassLoader.getPlatformClassLoader())) {
                Class<?> calc = Class.forName("demo.Calculator", true, loader);
                Object result = calc.getMethod("add", int.class, int.class)
                        .invoke(null, 4, 9);
                System.out.println("add=" + result);
            }
        } finally {
            try (var walk = Files.walk(out)) {
                for (Path path : walk.sorted(Comparator.reverseOrder()).toList()) {
                    Files.delete(path);
                }
            }
        }
    }
}
```

Lệnh:

```sh
javac --release 21 -Xlint:all CompileToDirectoryLab.java
java CompileToDirectoryLab
```

**Stdout:**

```text
compiled=true
errorCount=0
classFile=true
add=13
```

### 9.1. Tại sao đây chưa phải “compile hoàn toàn trong memory”?

- `unit` là `Kind.SOURCE` với dữ liệu lấy từ String, không có `demo/Calculator.java` trên disk.
- Compiler vẫn có **`StandardJavaFileManager`** và tùy chọn `-d`. Vì vậy output `demo/Calculator.class` được ghi ra **thư mục tạm thật**.
- `URLClassLoader` được tạo riêng từ `out` và load class bằng tên nhị phân `demo.Calculator`; Reflection gọi `add(4,9)` và thu 13.
- `try-with-resources` đóng file manager và URLClassLoader. `finally` dọn thư mục tạm, không để file bài lab rải rác.
- Các options và classpath thực tế có thể ảnh hưởng khả năng compile dependency bên ngoài JDK; bài này chỉ dùng source tự chứa để output ổn định.

### 9.2. Cách phân biệt source path với class output path

Hai cách định danh:

```text
Input  JavaFileObject.toUri() : string:///demo/Calculator.java
Output filesystem class path  : <temporary-directory>/demo/Calculator.class
Runtime binary name           : demo.Calculator
```

Tên `demo.Calculator` là **binary name**, không phải URI. `Class.forName("demo.Calculator", ...)` yêu cầu loader có thể tìm đúng bytes của class output. Không thể gọi `Class.forName("string:///demo/Calculator.java")` vì đó là source URI, không phải class name.

## 10. Biên dịch nhiều JavaFileObject trong một task

`compilationUnits` là một `Iterable<? extends JavaFileObject>`, không bị giới hạn một file. Với nhiều source units có phụ thuộc lẫn nhau, cung cấp chúng trong **một task** giúp compiler xử lý các type references qua cùng compilation context.

Ví dụ:

```text
JavaFileObject SOURCE "plug.Service"
  package plug; public interface Service { int eval(int x); }

JavaFileObject SOURCE "plug.ServiceImpl"
  package plug; public class ServiceImpl implements Service { ... }

JavaCompiler.getTask(... List.of(serviceUnit, implUnit)).call()
   |
   +--> plug/Service.class
   +--> plug/ServiceImpl.class
```

Những compilation units được nhập cùng một lần có thể tìm thấy lẫn nhau; không cần bạn tự tạo `Service.class` trước. Tuy nhiên nếu class A đã được biên dịch ở **một task trước** vào một kho memory tùy biến, task kế tiếp muốn dùng nó làm dependency sẽ cần **file manager tìm được output cũ** — đây là bài toán khác với compilationUnits cùng task.

### 10.1. Gói dữ liệu source đúng

Khi tạo nguồn từ nhiều String, cần phân biệt:

- **Danh sách sources**: `List<JavaFileObject>` do bạn xây, mỗi item có URI và `Kind.SOURCE` phù hợp.
- **Danh sách options**: `List<String>`, với mỗi flag và giá trị có vị trí riêng.
- **Danh sách `classes`** trong `getTask`: thường truyền `null` cho việc compile đơn giản; không đặt tên source classes vào đây thay cho `compilationUnits`.
- **Classpath/module path**: cung cấp trong options hoặc cấu hình file manager nếu source tham chiếu libraries. Không lạm dụng `ClassLoader` của host để thay tất cả compiler classpath configuration.

## 11. Lab 3 — hai nguồn JavaFileObject trong một lần compile

Tạo **`MultipleSourcesLab.java`**:

```java
import java.net.URI;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class MultipleSourcesLab {
    static final class Source extends SimpleJavaFileObject {
        final String code;

        Source(String name, String code) {
            super(URI.create("string:///" + name.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
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
            throw new IllegalStateException("JDK compiler unavailable");
        }

        List<JavaFileObject> units = List.of(
                new Source("plug.Service",
                        "package plug; public interface Service { int eval(int x); }"),
                new Source("plug.ServiceImpl",
                        "package plug; public class ServiceImpl implements Service { " +
                        "public int eval(int x) { return x + 5; } }")
        );

        Path dir = Files.createTempDirectory("multiple-units-");
        try {
            boolean success;
            try (StandardJavaFileManager manager =
                    compiler.getStandardFileManager(null, null, null)) {
                success = compiler.getTask(null, manager, null,
                        List.of("--release", "21", "-proc:none", "-d", dir.toString()),
                        null, units).call();
            }

            System.out.println("sourceUnits=" + units.size());
            System.out.println("compiled=" + success);
            System.out.println("bothClasses=" +
                    (Files.exists(dir.resolve("plug/Service.class"))
                    && Files.exists(dir.resolve("plug/ServiceImpl.class"))));

            try (URLClassLoader loader = new URLClassLoader(
                    new URL[] {dir.toUri().toURL()}, ClassLoader.getPlatformClassLoader())) {
                Class<?> api = Class.forName("plug.Service", true, loader);
                Class<?> impl = Class.forName("plug.ServiceImpl", true, loader);
                Object object = impl.getConstructor().newInstance();
                System.out.println("implementsService=" + api.isInstance(object));
                System.out.println("eval=" +
                        impl.getMethod("eval", int.class).invoke(object, 7));
            }
        } finally {
            try (var paths = Files.walk(dir)) {
                for (Path p : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.delete(p);
                }
            }
        }
    }
}
```

```sh
javac --release 21 -Xlint:all MultipleSourcesLab.java
java MultipleSourcesLab
```

**Stdout:**

```text
sourceUnits=2
compiled=true
bothClasses=true
implementsService=true
eval=12
```

### 11.1. Phân tích

- `units` là danh sách **hai** JavaFileObjects cùng `SOURCE` và có URI tương ứng từng class.
- Compiler tạo hai class files, dù **không có source file nào được lưu ra đĩa**.
- `Class.forName` load cả interface `plug.Service` và implementation `plug.ServiceImpl` qua cùng một loader, nên `api.isInstance(object)` đúng.
- `eval(7)` gọi method thật của class mới compile, trả 12. Không có mã tự viết để phân tích source thành bytecode, vì JavaCompiler đã đảm nhiệm parsing/type checking/code generation.
- Trong hệ thống thật, nếu nhiều plugin/class loaders có tên type giống nhau, runtime type identity vẫn phụ thuộc defining class loader; `JavaFileObject.toUri()` tự nó không điều khiển runtime loader.

## 12. Khi muốn bytecode đầu ra cũng ở trong bộ nhớ

Nếu chỉ override `getCharContent` thì **input** đã là memory, nhưng **output** vẫn do file manager quyết định. Để tránh tạo `.class` files, cần một **`JavaFileManager` tùy biến**.

Thiết kế thường gặp:

```text
                           compiler
                        JavaCompiler.getTask
                           |         |
                           |         +--> getJavaFileForOutput(CLASS_OUTPUT, name, CLASS)
                           |                                      |
 Input StringSource       |                              MemoryManager wrapper
 getCharContent(...)      |                                      |
                           |                              BytecodeOutput CLASS
                           |                              openOutputStream()
                           |                                      |
                           +--------------------------------------+
                                                                  |
                                                        ByteArrayOutputStream
                                                                  |
                                                   Map<binaryName, byte[]>
                                                                  |
                                                  custom ClassLoader#defineClass
```

`ForwardingJavaFileManager<StandardJavaFileManager>` là lớp tiện ích: nó **ủy quyền** hầu hết hoạt động tìm JDK classes/dependencies cho standard manager, đồng thời bạn chỉ override `getJavaFileForOutput(...)` để bắt class outputs.

### 12.1. Ba thành phần chuyên trách

**1. StringSource (đầu vào):** kế thừa `SimpleJavaFileObject` loại `SOURCE` và cung cấp `getCharContent`.

**2. BytecodeOutput (đầu ra):** kế thừa `SimpleJavaFileObject` loại `CLASS` và override `openOutputStream`. Compiler ghi **bytes classfile**, không cần chuyển chúng qua `String`.

**3. MemoryManager (đường dẫn đầu ra):** kế thừa `ForwardingJavaFileManager`, override `getJavaFileForOutput(location,binaryName,kind,sibling)`. Compiler có thể tạo **nhiều class files** từ một source unit, ví dụ nested class, anonymous classes và các synthetic members. Không dùng một `ByteArrayOutputStream` chung cho tất cả outputs nếu muốn giữ distinct class bytes.

### 12.2. URI của output khác source URI

Ví dụ `binaryName="live.Multiply$Part"` và kind `CLASS`:

```text
Source:        string:///live/Multiply.java
Main output:   mem:///live/Multiply.class
Nested output: mem:///live/Multiply$Part.class
Runtime names: live.Multiply, live.Multiply$Part
```

JDK compiler gọi file manager với **binary name của output**. Bạn có trách nhiệm lưu từng output theo tên ấy trong map. URI `mem:` là định danh; việc `ClassLoader#defineClass` sử dụng bytes không cần một URL protocol handler cho `mem:`.

### 12.3. Giới hạn của demo memory manager

Một manager chỉ override `getJavaFileForOutput` là đủ cho một compile task đơn giản **đã có đầy đủ compilation units** và chỉ cần giữ outputs. Nếu lần compile kế tiếp cần đọc những generated classes của task trước, có thể phải override thêm `getJavaFileForInput`, `list`, `inferBinaryName` và các hoạt động location thích hợp để compiler nhìn thấy bytes tồn tại trong memory. Đừng tự kết luận “output nằm trong map” là compiler tự tra lại nó khi resolve dependencies.

Bài cũng không thực hiện hỗ trợ annotation-generated sources, module-specific output locations hoặc resources tự sinh. Những quy tắc đó cần hợp đồng file manager mở rộng theo use case.

## 13. Lab 4 — compile source và CLASS output hoàn toàn trong RAM

Tạo file độc lập **`CompileInMemoryLab.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.OutputStream;
import java.net.URI;
import java.util.HashMap;
import java.util.List;
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

public class CompileInMemoryLab {
    static final class StringSource extends SimpleJavaFileObject {
        private final String code;

        StringSource(String binaryName, String code) {
            super(URI.create("string:///" + binaryName.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    static final class BytecodeOutput extends SimpleJavaFileObject {
        private final ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        BytecodeOutput(String binaryName, Kind kind) {
            super(URI.create("mem:///" + binaryName.replace('.', '/')
                    + kind.extension), kind);
        }

        @Override
        public OutputStream openOutputStream() {
            return bytes;
        }

        byte[] toByteArray() {
            return bytes.toByteArray();
        }
    }

    static final class MemoryManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        final Map<String, BytecodeOutput> classes = new HashMap<>();

        MemoryManager(StandardJavaFileManager standard) {
            super(standard);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location, String binaryName,
                JavaFileObject.Kind kind, FileObject sibling) {
            BytecodeOutput output = new BytecodeOutput(binaryName, kind);
            classes.put(binaryName, output);
            return output;
        }
    }

    static final class ByteLoader extends ClassLoader {
        private final Map<String, byte[]> code;

        ByteLoader(Map<String, byte[]> code) {
            super(ClassLoader.getPlatformClassLoader());
            this.code = Map.copyOf(code);
        }

        @Override
        protected Class<?> findClass(String name) throws ClassNotFoundException {
            byte[] bytes = code.get(name);
            if (bytes == null) throw new ClassNotFoundException(name);
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler unavailable");
        }

        String source = """
                package live;
                public class Multiply {
                    public static int run(int x, int y) { return Part.product(x, y); }
                    private static class Part {
                        static int product(int a, int b) { return a * b; }
                    }
                }
                """;
        Map<String, byte[]> bytes = new HashMap<>();
        boolean ok;

        try (StandardJavaFileManager standard =
                     compiler.getStandardFileManager(null, null, null);
                MemoryManager manager = new MemoryManager(standard)) {
            ok = compiler.getTask(null, manager, null,
                    List.of("--release", "21", "-proc:none"), null,
                    List.of(new StringSource("live.Multiply", source))).call();

            manager.classes.forEach((name, file) ->
                    bytes.put(name, file.toByteArray()));
        }

        System.out.println("compiled=" + ok);
        System.out.println("generatedClasses=" + bytes.size());
        System.out.println("allHaveBytes=" +
                bytes.values().stream().allMatch(b -> b.length > 4));

        ByteLoader loader = new ByteLoader(bytes);
        Class<?> main = Class.forName("live.Multiply", true, loader);
        Object result = main.getMethod("run", int.class, int.class)
                .invoke(null, 3, 7);
        System.out.println("product=" + result);
        System.out.println("customLoader=" + (main.getClassLoader() == loader));
    }
}
```

```sh
javac --release 21 -Xlint:all CompileInMemoryLab.java
java CompileInMemoryLab
```

**Stdout:**

```text
compiled=true
generatedClasses=2
allHaveBytes=true
product=21
customLoader=true
```

### 13.1. Vì sao một source tạo hai class files?

Source `live.Multiply` chứa một nested class `Part`. Compiler sinh **`live.Multiply.class`** và **`live.Multiply$Part.class`**; số đầu ra là 2. Vì file manager giữ map theo binary name, cả hai được lưu riêng. Nếu bạn chỉ giữ `Multiply.class`, chương trình có thể bị `NoClassDefFoundError` khi method `run` cần dùng nested `Part`.

### 13.2. Compiler khác ClassLoader

- `compiler.getTask(...).call()` tạo bytes và đi qua file manager; không tự tải class thành runtime `Class<?>`.
- `ByteLoader.findClass` tìm bytes theo binary name và gọi `defineClass`. Đây mới là bước tạo runtime class identity cho code mới.
- `ByteLoader` đặt parent là platform loader để ví dụ cô lập với các app classes không liên quan; phần type trong source chỉ dùng JDK. Với plugin thực có shared interfaces/SDK, phải chọn parent và delegation policy có chủ đích.
- `customLoader=true` xác nhận main class do loader do ta tạo định nghĩa, không phải do application class loader đã compile `CompileInMemoryLab`.
- Output `allHaveBytes=true` chỉ là sanity check; nếu muốn validate class file, có thể kiểm tra magic bytes `0xCAFEBABE` hoặc load thử với `ClassLoader`, nhưng **chưa** chứng minh source code an toàn để chạy.

### 13.3. Chỗ không nên copy nguyên vào production

Trong ví dụ, `MemoryManager` dùng `HashMap` đơn giản cho một task tuần tự và trả output bytes ngay khi task hoàn tất. Trong ứng dụng nhiều compilation tasks/threads, quản lý ownership cho từng task, lifecycle class loaders, memory pressure và đóng streams. JavaFileManager contract không bắt buộc một instance hoàn toàn thread-safe, dù phải hỗ trợ thao tác đồng thời trên các *distinct file objects* mà nó cung cấp.

Ngoài ra, khi compile **mã do người dùng không tin cậy cung cấp**, bạn phải cách ly ở **process/container/OS boundary** phù hợp, đặt quota/timeouts/giới hạn tài nguyên và chính sách annotation processors. Một custom classloader không phải security sandbox đầy đủ.

## 14. DiagnosticCollector giữ lỗi gắn với source object

`JavaCompiler.getTask` có thể nhận `DiagnosticCollector<JavaFileObject>` làm listener. Khi source có lỗi, compiler phát các `Diagnostic` chứa:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `getKind()` | `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE`... |
| `getSource()` | JavaFileObject được gắn với diagnostic, có thể `null` nếu không gắn source cụ thể |
| `getLineNumber()` | Dòng trong source, hoặc `Diagnostic.NOPOS` |
| `getColumnNumber()` | Cột trong source, hoặc `NOPOS` |
| `getStartPosition()/getEndPosition()` | Vị trí ký tự nếu có |
| `getCode()` | Mã diagnostic do implementation cung cấp |
| `getMessage(locale)` | Mô tả để người đọc hiểu, có thể thay đổi theo locale/JDK |

Source URI rất hữu ích trong editor hoặc website code playground: người dùng có thể biết lỗi thuộc “file ảo” nào, dù không có file ở disk. Nhưng phải nhớ `URI` chỉ là định danh, **không phải đường dẫn tự động có quyền đọc file thật**.

### 14.1. Không dùng message text làm assertion

Câu chữ của compiler error có thể được bản địa hóa hoặc thay đổi giữa JDK versions. Khi viết test ổn định, kiểm tra `kind`, `source`, `line` hoặc `Diagnostic.getCode()` khi phù hợp, nhưng cũng chú ý diagnostic codes không phải hợp đồng ngôn ngữ chung của mọi compiler. Trong ví dụ tiếp theo, chương trình in **kind, URI, line** thay vì in cả message.

## 15. Lab 5 — source sai cú pháp và diagnostics có vị trí

Tạo file **`DiagnosticsLab.java`**:

```java
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class DiagnosticsLab {
    static final class Source extends SimpleJavaFileObject {
        final String code;

        Source(String name, String code) {
            super(URI.create("string:///" + name.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
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
            throw new IllegalStateException("JDK compiler unavailable");
        }
        JavaFileObject bad = new Source("demo.Broken",
                "package demo;\npublic class Broken {\n    int x = ;\n}\n");
        DiagnosticCollector<JavaFileObject> collector = new DiagnosticCollector<>();
        Path out = Files.createTempDirectory("diagnostics-");
        try {
            boolean success;
            try (StandardJavaFileManager manager =
                    compiler.getStandardFileManager(collector, null, null)) {
                success = compiler.getTask(null, manager, collector,
                        List.of("--release", "21", "-proc:none", "-d", out.toString()),
                        null, List.of(bad)).call();
            }

            Diagnostic<? extends JavaFileObject> firstError =
                    collector.getDiagnostics().stream()
                            .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
                            .findFirst().orElseThrow();

            System.out.println("compiled=" + success);
            System.out.println("kind=" + firstError.getKind());
            System.out.println("source=" + firstError.getSource().toUri());
            System.out.println("line=" + firstError.getLineNumber());
            System.out.println("errorsPresent=" +
                    collector.getDiagnostics().stream()
                            .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR));
        } finally {
            try (var paths = Files.walk(out)) {
                for (Path p : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.delete(p);
                }
            }
        }
    }
}
```

```sh
javac --release 21 -Xlint:all DiagnosticsLab.java
java DiagnosticsLab
```

**Stdout kiểm chứng:**

```text
compiled=false
kind=ERROR
source=string:///demo/Broken.java
line=3
errorsPresent=true
```

### 15.1. Giải thích dữ liệu lỗi

- `DiagnosticsLab.java` **biên dịch thành công**; lỗi nằm trong String mô phỏng source `demo.Broken` chỉ được compiler thứ hai biên dịch **khi chương trình đang chạy**.
- `int x = ;` ở **dòng 3** của source ảo, sai cú pháp Java nên inner compilation trả `false`.
- `Diagnostic.getSource().toUri()` trả `string:///demo/Broken.java`, đúng source URI ban đầu. Không cần file thật để xác định source và số dòng.
- Đừng báo `compiled=false` nghĩa bản thân `DiagnosticsLab` không chạy; nó đã chạy và thu lại lỗi của quá trình compile thứ cấp đúng như thiết kế.
- Nếu diagnostic không gắn source, `getSource()` có thể null; production code phải kiểm tra trước khi lấy `toUri()`. Nếu không có position, `Diagnostic.NOPOS` không phải lỗi crash.

## 16. So sánh ba chiến lược lưu source và class output

| Nhu cầu | Input JavaFileObject | FileManager | Class output | Cách chạy |
| --- | --- | --- | --- | --- |
| Compiler CLI kiểu thông thường | `.java` trên filesystem | Standard manager | `.class` trên disk | `java -cp...` |
| Sinh Java source ở runtime, output lưu file | `SimpleJavaFileObject(SOURCE)` từ String | Standard manager + `-d` | `.class` trên disk | `URLClassLoader` |
| Compiler hoàn toàn in-memory | `SimpleJavaFileObject(SOURCE)` từ String | Forwarding manager custom | `ByteArrayOutputStream` theo binaryName | Custom `ClassLoader#defineClass` |
| IDE/editor với source ảo | Một tập JavaFileObjects của nhiều buffers | Custom/forwarding manager | Tùy ứng dụng | Có thể chỉ compile/check, không execute |
| Annotation processing/code generator | SOURCE và generated SOURCE/CLASS objects | FileManager hỗ trợ locations và outputs | Nhiều class/resource outputs | Tùy pipeline |

Hai tiêu chí cần quyết định độc lập: **source nằm ở đâu?** và **compiler sẽ ghi output ở đâu?** Một chương trình gọi `new StringSource(...)` không thể mặc nhiên nói “không dùng disk” khi chưa xem file manager.

### 16.1. StandardJavaFileManager và path

Với mã nguồn thật:

```java
// Minh họa: compiler và java.nio.file.Path sourcePath đã tồn tại.
try (StandardJavaFileManager standard =
        compiler.getStandardFileManager(null, null, null)) {
    Iterable<? extends JavaFileObject> units =
            standard.getJavaFileObjectsFromPaths(java.util.List.of(sourcePath));
    boolean ok = compiler.getTask(
            null, standard, null, java.util.List.of("-proc:none"),
            null, units).call();
}
```

Đây là cách làm nếu source đã ở disk. Không nên đọc cả file vào String rồi tạo source ảo chỉ để lặp lại những gì standard manager đã làm, trừ khi bạn thực sự cần sửa nội dung in-memory trước khi biên dịch.

### 16.2. Một source unit có thể sinh nhiều class files

Java source chứa nested/local/anonymous classes có thể sinh **nhiều `Kind.CLASS` outputs**. File manager phải xử lý từng `binaryName`, không chỉ file output có tên trùng top-level class. Lab 4 chứng minh một source tạo hai .class files.

Nếu dùng processor tạo thêm source units, có thể phát sinh `Kind.SOURCE` outputs trong quá trình compile, và file manager cần hỗ trợ cơ chế tương ứng. Không lấy một map `Map<String,byte[]>` chứa only classes làm kho duy nhất cho mọi loại generated file.

## 17. Chọn đúng contract về name, URI và class identity

### 17.1. Source file name, binary name và runtime name là ba tầng

```text
Java source declaration:
    package app.rules;
    public class RuleEngine { ... }

source JavaFileObject.toUri():
    string:///app/rules/RuleEngine.java

class output:
    mem:///app/rules/RuleEngine.class

runtime binary name:
    app.rules.RuleEngine

actual runtime Class<?>:
    (binary name, defining ClassLoader, runtime module context)
```

URI không chứa defining loader. Một Java class có thể được định nghĩa bởi các loaders khác nhau dù output binary name giống nhau. Một in-memory compiler có thể tạo bytes đúng, nhưng bạn vẫn phải bảo đảm classloader/linkage/shared API identity hợp lệ khi đưa object sang phần còn lại của hệ thống.

### 17.2. Không dùng getName để tìm runtime class

`file.getName()` không phải API nhận `"app.rules.RuleEngine"` và cũng không thay `Class.getName()`. Tương tự, `FileObject.toUri()` không thay `ClassLoader.loadClass("app.rules.RuleEngine")`. Hãy lưu **binaryName** riêng trong metadata nếu cần dùng sau compile.

### 17.3. Khi source là module-info hoặc package-info

`module-info.java` khai báo module, không phải public class `module-info`; `package-info.java` giữ package metadata. Việc chọn URI và compilation unit Kind phải tôn trọng tên đặc biệt này, các module-specific compiler options và file manager location tương ứng. Không lấy tên `module-info` rồi giả vờ đó là binary class name thông thường.

### 17.4. Nếu compile nhiều lần, quản lý dependency đúng nơi

Một `Map<String,byte[]>` chứa class output của lần trước có thể dùng cho **custom runtime ClassLoader**, nhưng compiler của lần sau không tự thấy map đó. Muốn compiler resolve một type trước đó, có thể:

- Cung cấp lại source unit trong cùng task.
- Lưu class files ra thư mục/JAR rồi đưa vào compiler classpath/module path.
- Mở rộng custom JavaFileManager để báo có class file qua `getJavaFileForInput/list/inferBinaryName`, cùng location và URI rules.

Chọn một cách có contract, không dựa vào “đã load class bằng custom ClassLoader nên JavaCompiler chắc cũng tìm được”.

## 18. Độ tin cậy, phiên bản JDK và an toàn

### 18.1. Chỉ dùng API có trong Java 21

Từ Java 23, một số phiên bản JDK có convenience factory mới trên `SimpleJavaFileObject` để tạo source từ String. **Không sử dụng API được thêm sau Java 21** trong bài code hỗ trợ Java 21. Ở đây ta dùng constructor protected `SimpleJavaFileObject(URI,Kind)` và override `getCharContent` đã được hỗ trợ từ lâu. Hãy xác minh phiên bản API thay vì sao chép snippet từ tài liệu JDK 25/26 rồi gắn `--release 21` mà chưa compile.

`javac --release 21` kiểm tra nguồn, API khả dụng và bytecode mục tiêu cho Java 21; chạy chương trình trong một JDK hỗ trợ phiên bản class file là bước khác. Trong lab này, chương trình có thể chạy trên JDK 21+ với compiler tích hợp đầy đủ.

### 18.2. ToolProvider có thể trả null

Một JRE/JDK runtime image `jlink` có thể không chứa module `jdk.compiler`. `ToolProvider.getSystemJavaCompiler()==null` nghĩa không có system compiler provider; giải pháp là chạy bằng JDK đầy đủ hoặc cung cấp compiler hợp pháp qua tool SPI, không nên dereference null và đổ lỗi cho source object.

### 18.3. Không biên dịch và thực thi mã không tin cậy trong cùng process

**Quan trọng:** `javax.tools.JavaCompiler` là công cụ biên dịch, **không phải sandbox**. Dù source được giữ trong String và output là byte array:

- Các annotation processors có thể thực thi mã trong quá trình compile nếu được kích hoạt.
- Mã đã compile khi load/initialize/invoke có quyền của process/class loader/module context, có thể làm I/O, tạo thread, kết nối mạng hoặc chiếm tài nguyên nếu runtime cho phép.
- `ClassLoader#defineClass` **không** tự giới hạn CPU, RAM, file system hay network.
- Đầu vào quá lớn, nhiều compilation units hoặc generated code phức tạp có thể tiêu hao đáng kể bộ nhớ/CPU.

Các lab dùng `-proc:none` để tránh chạy annotation processors. Với mã nguồn không đáng tin, cần **isolation cấp process/container/OS**, giới hạn quyền/tài nguyên/timeout, output directory an toàn và không tự động invoke code sau compile. Nếu không có isolation, chỉ biên dịch nguồn được kiểm soát.

### 18.4. Vòng đời của compiler và class loader

Dùng `try-with-resources` cho `StandardJavaFileManager`, `ForwardingJavaFileManager`, `URLClassLoader` và streams. Compiler/FileManager có thể cache JAR/file handles; không giữ reference vô hạn. Mỗi task có thể tạo nhiều class output objects, nên phải đặt chính sách giới hạn số class/bytes/versions. Classloader không chắc unload được nếu còn objects, static fields, threads hoặc caches giữ reference đến classes/loader.

## 19. Những lỗi thường gặp và cách điều tra

| Hiện tượng | Nguyên nhân thường gặp | Kiểm tra/khắc phục |
| --- | --- | --- |
| `UnsupportedOperationException` khi compiler đọc source | Subclass `SimpleJavaFileObject` không override `getCharContent`, hoặc cung cấp sai read API | Trả một CharSequence thật cho `Kind.SOURCE`. |
| `IllegalArgumentException` lúc tạo `URI` | URI/path chứa ký tự reserved/sai scheme | Validate binary name, tạo URI absolute, percent-encode theo thành phần. |
| `isNameCompatible=false` | URI path không kết thúc bằng `Name.java` hoặc Kind không đúng | In `toUri()`, `getKind()`; dùng `Kind.SOURCE.extension`. |
| “public class X should be in X.java” | Source URI/file name không khớp public top-level type name | Đồng bộ `binaryName`, source package và top-level class. |
| `ToolProvider.getSystemJavaCompiler() == null` | Runtime thiếu compiler module/provider | Chạy JDK có `jdk.compiler`, kiểm tra module image. |
| `task.call() == false` | Source syntax, types, classpath/options lỗi | Thu thập `DiagnosticCollector` và hiển thị source URI/line. |
| Không có `.class` trong RAM | Chỉ tạo StringSource, vẫn dùng standard file manager | Override `getJavaFileForOutput`, cung cấp `Kind.CLASS` output. |
| `openOutputStream` bị unsupported | `BytecodeOutput` không override stream | Dùng `ByteArrayOutputStream` và trả stream cho compiler. |
| Chỉ có một class khi source chứa nested types | File manager ghi đè cùng stream/output key | Giữ outputs riêng theo binary name + kind/location khi cần. |
| `ClassNotFoundException` sau compile | Loader không nhìn thấy output binary name | Kiểm tra map/`-d` path, loader parent, output location. |
| `NoClassDefFoundError` khi gọi | Thiếu dependency/nested class output hoặc classloader identity xung đột | Lưu mọi generated classes và cung cấp shared deps thích hợp. |
| `ClassCastException` giữa plugin types | Cùng tên class nhưng hai defining loaders khác nhau | Chia sẻ interface contracts qua loader chung. |
| Lỗi biên dịch source ảo nhưng không biết vị trí | Bỏ diagnostic listener hoặc source URI sai | Dùng `DiagnosticCollector`, `getSource/toUri`, line/column. |
| Compiler task thứ hai không tìm thấy output task trước | Memory output map chưa được tích hợp vào classpath/file manager | Override input/list methods hoặc materialize classes có kiểm soát. |
| Mã chạy tiêu tốn quá nhiều CPU/RAM | Dynamic source được coi là an toàn vì “in memory” | Isolate process, quota, timeout, input validation. |
| Resource/JAR bị khóa | File manager, output streams hoặc URLClassLoader chưa đóng | Dùng try-with-resources và dọn tài nguyên sau khi task hoàn tất. |

### 19.1. Trình tự debug đúng tầng

```text
[1] source code String có đủ và đúng package/public class name?
       |
[2] JavaFileObject.getKind() == SOURCE?
       |
[3] toUri() absolute và path kết thúc .java? isNameCompatible đúng?
       |
[4] getCharContent() có trả nội dung không?
       |
[5] compiler != null? options/classpath/module path đúng?
       |
[6] getTask(..., compilationUnits).call() có thành công?
       |
[7] DiagnosticCollector có ERROR, source URI, line nào?
       |
[8] FileManager xuất CLASS vào disk hay memory? chứa đủ nested classes?
       |
[9] ClassLoader có nạp đúng binaryName và dependencies?
       |
[10] Runtime invocation có đúng type/quyền và an toàn không?
```

Không bỏ qua bước 6 rồi đổ lỗi cho ClassLoader, và cũng không lấy một class loading exception để suy ngay source compiler đã thất bại. Mỗi pha có contract riêng.

## 20. Bài tập thực hành và đáp án định hướng

**Bài 1 — Phân biệt Kind.** Tạo hai `SimpleJavaFileObject` với cùng binary name `demo.Hello` nhưng `Kind.SOURCE` và `Kind.CLASS`. Dự đoán URI extensions nếu constructor ghép `kind.extension` và kết quả `isNameCompatible("Hello", SOURCE/CLASS)`. Giải thích vì sao phần bytes CLASS không nên trả qua `getCharContent`.

**Bài 2 — Source name mismatch.** Đổi StringSource name từ `demo.Hello` sang `demo.Other` nhưng vẫn khai báo `public class Hello`. Compile và xem `DiagnosticCollector`. Sửa bằng cách thống nhất binary name với public top-level type; không sửa `getKind` để che lỗi.

**Bài 3 — Đọc từ Reader.** Dùng `SourceObjectBasicsLab` để đếm ký tự source thông qua `openReader(false)`. So `length` với `getCharContent(false).length()`, dùng try-with-resources.

**Bài 4 — Không có system compiler.** Mô tả cách xử lý khi `ToolProvider.getSystemJavaCompiler()==null`; không đề xuất fallback `Runtime.exec("javac")` vô điều kiện trên mọi host vì đường dẫn, version, quyền và an toàn phải được kiểm soát.

**Bài 5 — Compiler options.** Trong Lab 2, bỏ `-d` và thay bằng cấu hình `StandardLocation.CLASS_OUTPUT` trên standard manager. Kiểm tra output location có đúng hay không. Giữ `--release 21` và `-proc:none` để output dễ dự đoán.

**Bài 6 — Nhiều source units.** Trong `MultipleSourcesLab`, thêm `plug.AnotherImpl` implements `Service`; truyền ba `JavaFileObject`, kỳ vọng có ba `.class`. Xác minh trước khi load rằng mọi output class paths tồn tại.

**Bài 7 — Một source nhiều class outputs.** Trong Lab 4, thêm một nested `static class Helper`. Dự đoán `generatedClasses` tăng lên, map phải chứa `live.Multiply$Helper` và `live.Multiply$Part`. Sửa tiêu chí QA thay vì hard-code “cứ một SOURCE thì một CLASS”.

**Bài 8 — Bytecode storage.** Trong `CompileInMemoryLab`, kiểm tra mỗi byte array có ít nhất 4 bytes đầu `CA FE BA BE`. Không diễn giải việc có magic bytes là đủ chứng minh class hợp lệ/an toàn.

**Bài 9 — Diagnostics và line mapping.** Đổi source lỗi thành nhiều dòng, rồi in `getLineNumber()`/`getColumnNumber()`. Nếu diagnostic không có source hoặc `NOPOS`, helper hiển thị thế nào?

**Bài 10 — Recompile dependencies.** Chạy một task compile `plug.Service` trong memory rồi task khác compile `plug.ServiceImpl` chỉ tham chiếu interface đã có bytes. Giải thích vì sao chỉ giữ bytecode trong map chưa đủ, và chọn giữa cung cấp source cùng task, materialize class output hay triển khai `JavaFileManager.getJavaFileForInput`/`list`.

**Bài 11 — Unicode source.** Tạo StringSource chứa chuỗi literal tiếng Việt hoặc ký tự non-ASCII và gọi `getCharContent(false)`. Giải thích vì sao khi nguồn đã là Java String, việc giải mã bytes đã xảy ra trước đó; khi đọc bytes ngoài vào, charset policy lại quan trọng.

**Bài 12 — Security review.** Một website nhận source Java từ người lạ, compile rồi load qua custom classloader trong web server. Chỉ ra ít nhất ba rủi ro và một kiến trúc isolation đúng mức. Giải thích `-proc:none` giúp hạn chế processor execution nhưng không biến output bytecode thành safe code.

### 20.1. Checklist hoàn thành

- [ ] Phân biệt `SOURCE`, `CLASS` và dòng dữ liệu đầu vào/đầu ra.
- [ ] Viết đúng subclass `SimpleJavaFileObject` với `Kind.SOURCE` và `getCharContent`.
- [ ] Hiểu URI `string:///.../Name.java` là identifier, không phải file thật.
- [ ] Ghép đúng `binaryName`, source package/public class và output class name.
- [ ] Truyền nhiều `JavaFileObject` qua `compilationUnits`.
- [ ] Sử dụng `JavaCompiler.getTask`, `StandardJavaFileManager`, `DiagnosticCollector` và đóng resources.
- [ ] Viết `Kind.CLASS` output object có `openOutputStream` và `ForwardingJavaFileManager` để giữ bytecode memory.
- [ ] Load class bằng binary name, bảo đảm nested outputs/dependencies hiện diện.
- [ ] Tách lỗi source syntax, name, compiler availability, file manager và class loader.
- [ ] Chạy và hiểu stdout của cả năm lab; không gọi compiler API là security sandbox.

## 21. Tài liệu chính thức Java 21

- [Java SE 21 — JavaFileObject](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaFileObject.html): `Kind`, `isNameCompatible`, nesting/access hints và hợp đồng file source/class.
- [Java SE 21 — SimpleJavaFileObject](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html): protected constructor, `getCharContent`, `openReader`, stream defaults, `toUri`.
- [Java SE 21 — FileObject](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/FileObject.html): URI, name, character/byte access, timestamps, delete.
- [Java SE 21 — JavaCompiler](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaCompiler.html): `getTask`, standard manager, compiler services và SPI.
- [Java SE 21 — ToolProvider](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/ToolProvider.html): `getSystemJavaCompiler()`.
- [Java SE 21 — StandardJavaFileManager](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html): mapping giữa `Path/File` và `JavaFileObject`.
- [Java SE 21 — JavaFileManager](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaFileManager.html): file locations, binary names và output factories.
- [Java SE 21 — ForwardingJavaFileManager](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/ForwardingJavaFileManager.html): wrapper với override có chọn lọc.
- [Java SE 21 — DiagnosticCollector](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/DiagnosticCollector.html) và [Diagnostic](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/Diagnostic.html): diagnostics kèm source, line, kind.
- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `defineClass`, parent delegation và runtime class identity.
- [JDK 21 — javac command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): `--release`, `-d`, `-proc:none` và compiler options.

**Kết luận:** `JavaFileObject` là giao diện của **source/class file trong compiler toolchain**, không nhất thiết là file trên disk. `SimpleJavaFileObject` cho phép bạn triển khai một source ảo bằng **URI + Kind.SOURCE + getCharContent()**; `JavaCompiler` biên dịch nó cùng các source khác; `JavaFileManager` chọn nơi ghi `Kind.CLASS`; và **ClassLoader** mới quyết định cách load code đã biên dịch. Giữ bốn trách nhiệm tách biệt, bạn có thể xây runtime compiler rõ ràng, có diagnostics hữu ích và không nhầm dữ liệu source với quyền thực thi.

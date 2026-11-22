# 16.5 Thu thập Diagnostic, vị trí lỗi và trạng thái biên dịch

**Ngữ cảnh:** Java Advance → dynamic-runtime → 16. Biên dịch lúc chạy.

Khi một ứng dụng tự biên dịch mã Java tại runtime bằng API `javax.tools.JavaCompiler`, câu trả lời "biên dịch thành công hay chưa?" chỉ là **một phần** kết quả. Để phục vụ IDE, playground, rule engine, hệ thống sinh code, bài chấm tự động hoặc server nhận Java source, ta còn cần biết **vì sao biên dịch thất bại, ở file nào, dòng nào, cột nào, có cảnh báo hay không**, và liệu lỗi đó thuộc mã nguồn hay hạ tầng thực thi compiler.

Ba thành phần then chốt:

- **`JavaCompiler.CompilationTask.call()`** trả trạng thái tác vụ biên dịch, thông thường `true` khi không có lỗi biên dịch và `false` khi có lỗi.
- **`DiagnosticCollector<JavaFileObject>`** nhận các `Diagnostic` do compiler phát ra, gồm `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE` và `OTHER`.
- **`Diagnostic`** mô tả mức độ, nguồn, thông điệp và thông tin vị trí: `getLineNumber()`, `getColumnNumber()`, `getPosition()`, `getStartPosition()`, `getEndPosition()`, `getCode()`, `getMessage(Locale)`.

Bài này trình bày trọn vẹn luồng thu thập lỗi/cảnh báo với **Java 17+**, kiểm chứng ba ca biên dịch thực sự (hợp lệ, sai kiểu và cảnh báo deprecated), cách sử dụng tọa độ để hiện vị trí lỗi, ý nghĩa của kết quả `task.call()`, và cách tránh các giả định sai về thông báo do compiler cung cấp.

## 1. Một lượt biên dịch tạo ra ba nhóm kết quả

Một hệ thống biên dịch động nên xem kết quả như ba lớp dữ liệu có quan hệ nhưng không đồng nhất:

| Nhóm | API tiêu biểu | Câu hỏi trả lời |
| --- | --- | --- |
| **Trạng thái tác vụ** | `CompilationTask.call()` | Task hoàn tất thành công theo compiler không? |
| **Diagnostics** | `DiagnosticCollector.getDiagnostics()` | Có bao nhiêu lỗi, cảnh báo, ghi chú? Ở đâu? Nội dung gì? |
| **Đầu ra artifacts / hạ tầng** | `JavaFileManager`, output directory, `Writer`, exception của API | Class file được viết đi đâu? File manager/option/compiler có hỏng không? |

Sơ đồ:

```text
String Java source / JavaFileObject
             |
             v
ToolProvider.getSystemJavaCompiler()
             |
             v
JavaCompiler.getTask(writer, fileManager,
                     diagnosticListener, options,
                     classes, compilationUnits)
             |
             +------ compiler reports ------> DiagnosticCollector
             |                                   |
             v                                   +--> ERROR / WARNING / NOTE
      CompilationTask.call()                     +--> source, line, column, offsets
             |
             +--> true / false
             |
             +--> class output qua JavaFileManager
             |
             +--> có thể có exception hạ tầng/configuration
```

Ví dụ một đoạn mã có **một lời gọi tới API deprecated** vẫn có thể được biên dịch thành công. Ngược lại, một đoạn mã gán `String` vào `int` gây lỗi và trả `false`. Vì vậy **có diagnostic không đồng nghĩa compile fail**, và **danh sách diagnostics trống không đủ để kết luận task đã thành công** nếu compilation chưa chạy, bị dừng hoặc ném exception.

## 2. Các API chịu trách nhiệm

### 2.1 `ToolProvider.getSystemJavaCompiler()`

API lấy `JavaCompiler` được tích hợp với runtime Java nếu môi trường cung cấp compiler module `jdk.compiler`. Trên bản phân phối chỉ có runtime tối giản hoặc custom runtime image thiếu module này, phương thức có thể trả **`null`**.

```java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException("A JDK compiler is required");
}
```

Đây là **snippet**; để biên dịch phải import `javax.tools.JavaCompiler` và `javax.tools.ToolProvider`, hoặc dùng chương trình hoàn chỉnh tại mục 5. Đừng gọi `compiler.getTask(...)` trên `null` rồi báo cho người dùng "lỗi cú pháp" — đó là **lỗi môi trường, không phải lỗi Java source**.

### 2.2 `JavaFileObject` đại diện mã nguồn

`JavaCompiler` xử lý các đối tượng `JavaFileObject`. Có thể dùng `StandardJavaFileManager.getJavaFileObjectsFromPaths(...)` cho file thật hoặc kế thừa `SimpleJavaFileObject` để cung cấp nội dung **ngay trong RAM**.

Ví dụ một source object có:

- URI `string:///lesson/Broken.java`.
- `Kind.SOURCE`.
- Nội dung chuỗi `package lesson; ...` qua `getCharContent(boolean)`.

Compiler dùng metadata URI/tên để định danh file, đồng thời `Diagnostic.getSource()` có thể trả về chính `JavaFileObject` gắn với lỗi. Trong ví dụ, tên source hiển thị `/lesson/Broken.java` từ `getName()`; **không nên mặc định mọi JavaFileManager đều trả tên cùng định dạng**.

### 2.3 `DiagnosticCollector<JavaFileObject>`

Đây là một `DiagnosticListener` lưu các diagnostics compiler gửi tới. Tạo collector **mới cho mỗi lượt compilation độc lập** để tránh trộn errors/warnings của lượt trước:

```java
DiagnosticCollector<JavaFileObject> diagnostics =
        new DiagnosticCollector<>();
```

Đây là snippet trong code đã import `javax.tools`. Khi tạo task, truyền chính collector vào **tham số thứ ba** của `compiler.getTask`. Sau `task.call()`, đọc `diagnostics.getDiagnostics()` để biết những diagnostic đã được phát.

**Collector không tự gọi compiler, không tạo class file và không tính trạng thái thành công.** Nó chỉ nhận diagnostic events. Cũng đừng tái sử dụng cùng collector cho một loạt compile rồi tưởng `getDiagnostics()` chỉ chứa lỗi của lần cuối.

### 2.4 `StandardJavaFileManager` và output

`JavaCompiler.getTask` cần file manager để đọc các compilation units, giải quyết dependencies/module path/classpath và ghi outputs. `compiler.getStandardFileManager(...)` là lựa chọn cơ bản; nên đóng bằng `try-with-resources`.

Khi compile từ nguồn in-memory nhưng **không** cung cấp output manager tùy biến, compiler vẫn có thể ghi `.class` ra filesystem. Trong ví dụ, `-d` chỉ về một thư mục tạm riêng và thư mục ấy được dọn khi hoàn tất, tránh phát sinh class files vào repo/cwd.

Nếu hệ thống thực sự cần bytecode ở RAM, có thể triển khai `ForwardingJavaFileManager`/`JavaFileManager.getJavaFileForOutput` và một `JavaFileObject` trả `OutputStream` vào buffer. **In-memory source không tự có nghĩa là in-memory output.**

## 3. `Diagnostic.Kind`: lỗi, warning và note

`Diagnostic.Kind` bao gồm:

| Kind | Diễn giải | Cách dùng |
| --- | --- | --- |
| `ERROR` | Lỗi compiler, ví dụ mismatch kiểu, symbol không tồn tại, cú pháp không hợp lệ | Hiển thị là lỗi; thông thường task không thành công |
| `WARNING` | Cảnh báo không bắt buộc, ví dụ lint warning theo cấu hình | Hiển thị là cảnh báo, không mặc định kết luận thất bại |
| `MANDATORY_WARNING` | Cảnh báo thuộc nhóm bắt buộc do compiler/JLS yêu cầu thông báo trong những hoàn cảnh thích hợp | **Cũng là warning**, nên tính vào tổng warning |
| `NOTE` | Thông tin bổ sung do compiler phát | Hiển thị dạng thông tin, không xem là lỗi |
| `OTHER` | Loại chẩn đoán không thuộc những nhóm trên | Xử lý như thông tin khác hoặc bảo lưu kind |

**Sai lầm thường gặp:** Chỉ đếm `Diagnostic.Kind.WARNING` rồi bỏ sót `MANDATORY_WARNING`. Trong chương trình ở mục 5, với compiler OpenJDK đã thử nghiệm, diagnostic về deprecated API được báo bằng `MANDATORY_WARNING`, trong khi compilation vẫn thành công.

Cách đếm:

```java
long errors = diagnostics.getDiagnostics().stream()
        .filter(d -> d.getKind() == Diagnostic.Kind.ERROR).count();

long warnings = diagnostics.getDiagnostics().stream()
        .filter(d -> d.getKind() == Diagnostic.Kind.WARNING
                || d.getKind() == Diagnostic.Kind.MANDATORY_WARNING).count();
```

Đây là snippet đã có `diagnostics`. Tổng warning không tự gồm `NOTE`/`OTHER`. Nếu sản phẩm cần tổng tất cả events, hãy lưu riêng `List<Diagnostic<...>>` rồi phân loại theo đầy đủ kind.

## 4. Vị trí lỗi: file, dòng, cột và offsets

Một `Diagnostic<? extends JavaFileObject> d` có những trường dữ liệu chính:

| API | Ý nghĩa | Khi không khả dụng |
| --- | --- | --- |
| `d.getSource()` | Source object gắn với lỗi | Có thể **`null`** |
| `d.getLineNumber()` | Dòng chứa vị trí chính, thường trình bày từ **1** | `Diagnostic.NOPOS` |
| `d.getColumnNumber()` | Cột tại dòng, thường trình bày từ **1** | `Diagnostic.NOPOS` |
| `d.getPosition()` | Offset ký tự từ đầu source, **bắt đầu từ 0** | `Diagnostic.NOPOS` |
| `d.getStartPosition()` | Offset vùng bắt đầu vấn đề | `Diagnostic.NOPOS` |
| `d.getEndPosition()` | Offset vùng kết thúc vấn đề | `Diagnostic.NOPOS` |
| `d.getKind()` | Mức độ `ERROR/WARNING/...` | Kind do diagnostic cung cấp |
| `d.getCode()` | Mã diagnostic phụ thuộc implementation, **có thể null** | Không xem là định danh ổn định xuyên compiler |
| `d.getMessage(Locale.ROOT)` | Thông báo lỗi theo locale được chọn | Câu chữ phụ thuộc implementation/JDK |

Các offset không phải byte offset của file UTF-8: chúng là **character offsets** theo cách nguồn được JavaFileObject cung cấp. Java String lưu văn bản dạng UTF-16 code units; với code có supplementary Unicode characters, tab, CRLF hoặc những chuỗi có normalization khác nhau, editor cần **map offset sang tọa độ giao diện** một cách có chủ đích, không nhầm với index byte UTF-8.

Theo `Diagnostic` contract:

```text
startPosition <= position <= endPosition
```

Khi có location, `getPosition` là offset của vị trí chính; `getStartPosition` và `getEndPosition` mô tả khoảng mà compiler nhận định liên quan. Đừng tự kết luận mọi compiler luôn trả cùng span: độ rộng vùng tô sáng có thể phụ thuộc JDK/compiler và loại lỗi.

### 4.1 Ví dụ một lỗi cụ thể

Trong source:

```java
package lesson;
public class Broken {
    static int get() {
        int n = "oops";
        return n;
    }
}
```

Đây là đoạn source độc lập được truyền cho JavaCompiler nhưng chưa có `public static void main`. Khi compile, lỗi là **không thể gán `String` cho `int`**. Trên phiên bản compiler thực nghiệm, diagnostic xuất hiện ở **dòng 4, cột 17**, chính tại literal `"oops"`.

Vì cột bắt đầu từ 1, vị trí được đánh dấu sau 16 ký tự trong dòng:

```text
        int n = "oops";
                ^
```

Tính từ đầu toàn source (mỗi dòng kết thúc bằng `\n`) vị trí được báo là `position=77`, `start=77`, `end=83` ở compiler đã thử. Khi tích hợp IDE, **không hard-code 77 hoặc column 17**; đọc location động từ từng `Diagnostic` thực tế.

### 4.2 Vì sao `getSource() == null` là tình huống bình thường?

Không phải diagnostic nào cũng gắn một file. Có lỗi do compiler options, environment, classpath/module path, annotation-processing setup hoặc trạng thái toàn compilation không trỏ đến một token source cụ thể. Khi không có vị trí thích hợp, `getPosition() == Diagnostic.NOPOS` (giá trị `-1`) và line/column/start/end không dùng được.

Do đó code trình bày phải có fallback:

```java
String source = d.getSource() == null
        ? "<no source>"
        : d.getSource().getName();

String location = d.getLineNumber() == Diagnostic.NOPOS
        ? "(global diagnostic)"
        : d.getLineNumber() + ":" + d.getColumnNumber();
```

Đây là snippet trong ngữ cảnh biến `d` đã tồn tại, không phải chương trình độc lập. Khi location không có, hiển thị thông báo ở mức project/compilation thay vì highlight ngẫu nhiên dòng 0 hoặc -1.

### 4.3 Vị trí lỗi trong editor và code generator

Với Java code do framework sinh ra, đôi khi file compiler báo là `GeneratedSource.java` chứ không phải file mà người dùng nhập. Để cung cấp UX tốt, application cần map:

1. JavaFileObject được compiler thấy → generated URI/path.
2. Offset hoặc line/column compiler trả → đúng bản **source đã compile**.
3. Vị trí trong generated source → nguồn template/user input ban đầu (nếu hệ thống có source map).
4. Message và severity → UI notification, lỗi theo field hay theo file.

Không thể tự lấy `getLineNumber` của source generated rồi áp lên raw textarea người dùng khi generator đã thêm package/imports/wrappers. Tương tự, nếu editor normalize CRLF thành LF sau khi compile, offsets có thể không còn trùng. Hãy giữ immutable snapshot nguồn của chính lượt compile đó và liên kết diagnostics với version/snapshot ID.

## 5. Ví dụ Java 17+ hoàn chỉnh: ba ca biên dịch và diagnostics

Chương trình **`CompilerDiagnosticsDemo.java`** dùng `ToolProvider`, `SimpleJavaFileObject`, `DiagnosticCollector` và `StandardJavaFileManager`. Ba ca:

- **`valid`:** Java source hợp lệ, compile thành công, không có diagnostic.
- **`invalid`:** gán `String` cho `int`, compile thất bại, có `ERROR` chỉ rõ file/dòng/cột/offsets.
- **`warning`:** gọi API được đánh dấu `@Deprecated` với `-Xlint:deprecation`, compile thành công nhưng có cảnh báo.

Chương trình không load/run mã người dùng đã compile; nó chỉ tạo class files trong thư mục temp và xóa chúng sau mỗi ca. Điều này giúp tách bạch compile-time diagnostics khỏi lỗi khi gọi runtime bytecode.

### 5.1 File `CompilerDiagnosticsDemo.java`

```java
import java.io.IOException;
import java.io.StringWriter;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.stream.Stream;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class CompilerDiagnosticsDemo {
    static final class Source extends SimpleJavaFileObject {
        final String text;

        Source(String binaryName, String text) {
            super(URI.create("string:///" +
                    binaryName.replace('.', '/') + Kind.SOURCE.extension), Kind.SOURCE);
            this.text = text;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return text;
        }
    }

    static void compileCase(JavaCompiler compiler, String label, List<Source> sources)
            throws IOException {
        Path output = Files.createTempDirectory("compile-diagnostics-");
        DiagnosticCollector<JavaFileObject> diagnostics = new DiagnosticCollector<>();
        try (StandardJavaFileManager files =
                     compiler.getStandardFileManager(diagnostics, Locale.ROOT,
                             StandardCharsets.UTF_8)) {
            var options = List.of("--release", "17", "-proc:none",
                    "-Xlint:deprecation", "-d", output.toString());
            boolean success = Boolean.TRUE.equals(compiler.getTask(
                    new StringWriter(), files, diagnostics, options, null, sources).call());

            long errors = diagnostics.getDiagnostics().stream()
                    .filter(d -> d.getKind() == Diagnostic.Kind.ERROR).count();
            long warnings = diagnostics.getDiagnostics().stream()
                    .filter(d -> d.getKind() == Diagnostic.Kind.WARNING
                            || d.getKind() == Diagnostic.Kind.MANDATORY_WARNING).count();
            System.out.println(label + ": success=" + success +
                    " errors=" + errors + " warnings=" + warnings);

            for (Diagnostic<? extends JavaFileObject> d : diagnostics.getDiagnostics()) {
                String file = d.getSource() == null ? "<none>" :
                        d.getSource().getName();
                System.out.println("  " + d.getKind() + " " + file +
                        " line=" + d.getLineNumber() +
                        " column=" + d.getColumnNumber() +
                        " position=" + d.getPosition() +
                        " start=" + d.getStartPosition() +
                        " end=" + d.getEndPosition());
                System.out.println("  messagePresent=" +
                        !d.getMessage(Locale.ROOT).isBlank());

                if (d.getSource() != null &&
                        d.getLineNumber() != Diagnostic.NOPOS) {
                    String[] lines = d.getSource().getCharContent(true)
                            .toString().split("\\R", -1);
                    int index = Math.toIntExact(d.getLineNumber() - 1);
                    if (index >= 0 && index < lines.length) {
                        System.out.println("  source=" + lines[index].strip());
                    }
                }
            }
        } finally {
            try (Stream<Path> all = Files.walk(output)) {
                for (Path file : all.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(file);
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("A JDK compiler is required");
        }

        String good = "package lesson;\n" +
                "public class Good {\n" +
                "    public static int value() { return 7; }\n" +
                "}\n";
        String bad = "package lesson;\n" +
                "public class Broken {\n" +
                "    static int get() {\n" +
                "        int n = \"oops\";\n" +
                "        return n;\n" +
                "    }\n" +
                "}\n";
        String legacy = "package lesson;\n" +
                "public class OldApi {\n" +
                "    @Deprecated public static void old() {}\n" +
                "}\n";
        String client = "package lesson;\n" +
                "public class Client {\n" +
                "    public static void call() { OldApi.old(); }\n" +
                "}\n";

        compileCase(compiler, "valid", List.of(new Source("lesson.Good", good)));
        compileCase(compiler, "invalid", List.of(new Source("lesson.Broken", bad)));
        compileCase(compiler, "warning", List.of(
                new Source("lesson.OldApi", legacy),
                new Source("lesson.Client", client)));
    }
}
```

### 5.2 Biên dịch và chạy

Tạo một thư mục trống, lưu file nguồn theo đúng tên và chạy với **JDK 17 trở lên**:

```bash
javac --release 17 -encoding UTF-8 CompilerDiagnosticsDemo.java
java CompilerDiagnosticsDemo
```

Code dùng `List.of`, `String.strip` và `Stream.toList` (có từ Java 16), nên `--release 17` tương thích. Đòi hỏi môi trường có compiler (module `jdk.compiler`): nếu chạy trên runtime image chỉ có `java.base` và thiếu compiler, `ToolProvider.getSystemJavaCompiler()` có thể trả `null`.

**Stdout đã kiểm chứng với OpenJDK 24, biên dịch bằng `--release 17`:**

```text
valid: success=true errors=0 warnings=0
invalid: success=false errors=1 warnings=0
  ERROR /lesson/Broken.java line=4 column=17 position=77 start=77 end=83
  messagePresent=true
  source=int n = "oops";
warning: success=true errors=0 warnings=1
  MANDATORY_WARNING /lesson/Client.java line=3 column=39 position=76 start=70 end=80
  messagePresent=true
  source=public static void call() { OldApi.old(); }
```

**Lưu ý về tính tái lập:** Các tổng `success` và `errors` phản ánh đúng ba ca kiểm tra; lời cảnh báo từ compiler (bao gồm `WARNING` hay `MANDATORY_WARNING`), vị trí chính xác của warning, code/message diagnostic có thể thay đổi theo JDK/vendor/options. Vì thế chương trình **không in nguyên văn thông điệp** vào stdout mẫu, mà chỉ xác nhận `messagePresent`. Muốn hiển thị nội dung thực tế, hãy gọi `d.getMessage(locale)` trong ứng dụng (mục 7). Các cột/vị trí đã nêu là kết quả được kiểm chứng trong môi trường thử, không phải những giá trị API đảm bảo cứng cho mọi compiler.

### 5.3 Tại sao kết quả đúng như vậy?

1. `valid` nhận một `JavaFileObject` cho `lesson.Good` có source hợp lệ. `task.call()` trả `true`, collector không có error/warning: `success=true errors=0 warnings=0`.
2. `invalid` compile `lesson.Broken`. Dòng `int n = "oops";` không phù hợp kiểu; task trả `false`, collector có `ERROR`.
3. `/lesson/Broken.java` chính là `Source.getName()` từ URI `string:///lesson/Broken.java`. Đây là identity do source object tạo, không phải đường dẫn filesystem phải tồn tại.
4. `line=4 column=17` là vị trí compiler ghi nhận lỗi trong source được cấp. `position=77 start=77 end=83` là character offsets từ đầu source.
5. `messagePresent=true` cho thấy `getMessage(Locale.ROOT)` trả một thông điệp hữu ích; ta cố ý không phụ thuộc câu chữ chi tiết vì message text có thể được thay đổi.
6. `warning` compile **hai source files trong một task**: `lesson.OldApi` định nghĩa method deprecated và `lesson.Client` gọi nó.
7. `-Xlint:deprecation` yêu cầu compiler đưa ra chẩn đoán deprecation. Bộ compiler trong ca kiểm chứng phát một `MANDATORY_WARNING` tại `Client.java` dòng 3; tổng warnings vẫn bằng 1.
8. `success=true` ở ca warning chứng minh **cảnh báo không mặc định làm task thất bại**. Nếu policy của dự án là "warnings are errors", phải áp dụng quy tắc riêng hoặc option phù hợp.
9. `-proc:none` tắt annotation processing cho ba ca; nó giúp demo ổn định và giảm một nguồn thực thi code khi compile input không tin cậy.
10. `-d output` giữ class files ở temp directory. Cuối ca, `try-with-resources` đóng file manager và `finally` xóa thư mục output. Các source strings không cần nằm trên filesystem.

### 5.4 Lưu ý về `StringWriter`

Đối số đầu tiên của `compiler.getTask(...)` là `Writer` để nhận output **không đi qua diagnostic listener**. Ví dụ cung cấp `new StringWriter()` nhưng không in nó ra vì mục tiêu là kiểm tra `DiagnosticCollector`. Trong ứng dụng thật, giữ reference:

```java
StringWriter compilerOutput = new StringWriter();
JavaCompiler.CompilationTask task = compiler.getTask(
        compilerOutput, fileManager, diagnostics, options,
        null, compilationUnits);
Boolean successful = task.call();

String extraOutput = compilerOutput.toString();
```

Đây là **snippet**, cần có `compiler`, `fileManager`, `diagnostics`, `options` và `compilationUnits`. `extraOutput` khác danh sách diagnostics; không nên đánh đồng mọi text trong Writer với `Diagnostic.Kind.ERROR`. Sử dụng collector để có thông tin vị trí/loại lỗi dạng cấu trúc, Writer để lưu thêm thông báo ngoài diagnostic channel nếu có.

## 6. `CompilationTask.call()` có ý nghĩa gì?

`JavaCompiler.CompilationTask` mở rộng `JavaCompiler.CompilationTask` từ compiler API và triển khai `Callable<Boolean>`. Phương thức `call()` **thực hiện tác vụ biên dịch** và trả giá trị Boolean cho biết tác vụ hoàn thành không có lỗi theo compiler.

Trong code:

```java
Boolean result = compiler.getTask(
        writer, fileManager, diagnostics, options, null, units).call();

boolean success = Boolean.TRUE.equals(result);
```

Đây là snippet trong ngữ cảnh đã có các biến tương ứng. `Boolean.TRUE.equals(...)` hữu ích để xác định rõ chỉ `Boolean.TRUE` mới được tính là thành công. Các task compilation riêng nên được tạo lại nếu muốn recompile: đừng gọi `call()` lần hai trên cùng object task và mong compiler tự reset.

### Trạng thái thực tế nên tách nhiều loại

| Trường hợp | `task.call()` / exception | Diagnostics | Trạng thái ứng dụng gợi ý |
| --- | --- | --- | --- |
| Source đúng, không warnings | `true` | Có thể trống | `SUCCESS` |
| Source đúng nhưng warnings | `true` | `WARNING`/`MANDATORY_WARNING` | `SUCCESS_WITH_WARNINGS` |
| Source sai cú pháp hoặc type | `false` | Thường có `ERROR` | `COMPILE_ERROR` |
| Compiler được cấu hình coi warnings là errors | Có thể `false` | Có thể có warning kèm diagnostic lỗi liên quan | `COMPILE_ERROR` hoặc `POLICY_REJECTED` theo policy |
| Không có `JavaCompiler` | Không tạo được task | Không có diagnostics compilation | `COMPILER_UNAVAILABLE` |
| Tham số/option/task setup không hợp lệ | Có thể ném exception trước/khi compile | Có thể không có location | `SETUP_ERROR` |
| File manager / output I/O lỗi | Có thể ném exception hoặc task thất bại | Không nhất thiết đủ error location | `INFRA_ERROR` |
| Code compile thành công nhưng bị lỗi khi chạy | Compilation `true` | Compile diagnostics có thể trống | `RUNTIME_ERROR` của giai đoạn thực thi, không phải compile failure |

Các nhãn `SUCCESS_WITH_WARNINGS`, `COMPILE_ERROR`... là **enum/policy do ứng dụng tự đặt**, không phải các trạng thái mà `CompilationTask` tự trả. `call()` chỉ trả Boolean (hoặc không trả vì exception); mapping trạng thái phụ thuộc requirement của hệ thống.

**Đừng chỉ dùng `errors == 0` làm status.** Một task chưa chạy, bị exception, hoặc thất bại do policy/IO vẫn có thể không có `Diagnostic.Kind.ERROR` có location cụ thể. Nguồn chân lý cho kết quả compile là task result cùng thông tin lỗi của API; danh sách diagnostics cung cấp ngữ cảnh, không thay thế status.

### `-Werror` và cảnh báo

Với compiler `javac`, option `-Werror` có thể biến warnings thành điều kiện khiến compilation bị coi là thất bại. Nếu bật, `success` có thể là `false` dù issue gốc mang loại warning. Một dịch vụ review nên lưu **cả policy**, diagnostics và `task.call()` để giải thích điều đó cho người dùng.

`-Xlint:deprecation` bật deprecation diagnostics trên javac; cấu hình compiler khác nhau có thể thay số lượng/nội dung warning. Không trộn một test kỳ vọng "1 warning" với logic nghiệp vụ yêu cầu đúng một warning trên mọi JDK/vendor.

### Task thất bại có thể để lại output không hoàn chỉnh

Compiler có thể đã viết một số class files trước khi phát hiện lỗi khác. Vì vậy `task.call()==false` không nhất thiết chứng minh output folder trống. Trong ứng dụng production, hãy biên dịch vào **staging/output temp riêng**, chỉ publish artifacts nếu task thành công và policy cho phép. Không để class loader lấy output chưa hoàn thành chỉ vì file `.class` xuất hiện trên filesystem.

## 7. Hiển thị diagnostic message mà không phụ thuộc câu chữ cố định

`Diagnostic.getMessage(Locale)` cung cấp message cho người đọc; `getCode()` cung cấp mã compiler-specific và **có thể `null`**. Cần bảo lưu cả hai nếu UI/debugger yêu cầu, nhưng **không dùng chuỗi message đã dịch làm khóa logic**.

Snippet trong vòng lặp `for (Diagnostic<? extends JavaFileObject> d : ...)`:

```java
String message = d.getMessage(Locale.ROOT);
String code = d.getCode(); // có thể null, phụ thuộc compiler
System.out.println("kind=" + d.getKind());
System.out.println("message=" + message);
System.out.println("code=" + code);
```

Chương trình đầy đủ ở mục 5 chỉ in `messagePresent` để có stdout ổn định trong môi trường thử. Với UI thật, hãy dùng `message` làm văn bản lỗi, còn `kind` và `position` làm dữ liệu phân loại và định vị. Nếu cần đa ngôn ngữ, chọn `Locale` có chủ đích (ví dụ `Locale.ROOT` cho log ổn định hơn theo cấu hình; tuy nhiên **không đảm bảo** wording hoàn toàn không đổi giữa compiler versions).

### Không tự parse compiler stderr để tìm line/column

Một cách làm dễ vỡ là lấy dòng text kiểu `Broken.java:4: error: incompatible types` từ stderr rồi dùng regex tìm số dòng. Nó phụ thuộc locale, compiler vendor và format thông báo. Nếu đã dùng `javax.tools`, hãy lấy trực tiếp:

```java
Diagnostic.Kind kind = d.getKind();
long line = d.getLineNumber();
long column = d.getColumnNumber();
long start = d.getStartPosition();
long end = d.getEndPosition();
```

Đây là snippet dùng `d` hiện có. Dữ liệu location tách khỏi thông điệp tự nhiên, dễ map sang IDE, JSON response hoặc event stream. Chỉ dùng parser text khi làm việc với compiler khác không cung cấp diagnostic API dạng cấu trúc.

## 8. Chuyển diagnostics thành vị trí trên editor

### 8.1 Hợp đồng vị trí rõ ràng

Một trình biên tập thường dùng:

- **File URI/path**: chuỗi hoặc resource ID. `Diagnostic.getSource()` có thể `null`.
- **Line**: 1-based từ `getLineNumber()`; nhiều editor APIs dùng 0-based, cần chuyển đổi tại boundary.
- **Column**: 1-based từ `getColumnNumber()`; tabs có thể thay đổi cách hiển thị, không đơn giản bằng index ký tự.
- **Character offsets**: 0-based từ `getPosition()/getStartPosition()/getEndPosition()`; không phải byte offsets UTF-8.
- **Message**: `getMessage(locale)` để người đọc hiểu.
- **Severity**: ánh xạ từ `Diagnostic.Kind`.

Ví dụ chẩn đoán ở `Broken.java`:

```text
file:   /lesson/Broken.java
kind:   ERROR
line:   4
column: 17
start:  77
end:    83

        int n = "oops";
                ^^^^^^
```

Các dấu caret dùng để giải thích khoảng source do compiler đánh dấu ở **bản source của demo**; trong UI thật cần tính indent, tab width, Unicode và chính sách end offset của editor. Nếu bạn gọi `strip()` để in một dòng source cho dễ đọc như trong demo, tọa độ column gốc **không còn** trùng vị trí hiển thị của dòng đã strip. Để highlight đúng, nên giữ nguyên nội dung dòng gốc.

### 8.2 Khi compiler báo lỗi không có vị trí

Không phải diagnostic nào cũng chỉ được một token:

```java
boolean located = d.getPosition() != Diagnostic.NOPOS
        && d.getSource() != null;

if (!located) {
    // Gắn diagnostic vào cấp project / compilation.
}
```

Đây là snippet. Đừng ép lỗi command option hay classpath vào dòng đầu một source tùy ý, vì người dùng sẽ sửa nhầm. Với lỗi setup, giao diện có thể đưa ra một banner tổng quát cùng chi tiết exception/option thay vì vẽ underline trong editor.

### 8.3 Sorting, grouping và nhiều file

`DiagnosticCollector` nhận events theo thứ tự compiler report, nhưng một editor nên nhóm theo source identity và sort theo location:

1. Nhóm theo canonical URI/resource ID (không chỉ basename `Broken.java`).
2. Với diagnostics có vị trí, sort theo `line` rồi `column` tăng dần.
3. Xử lý diagnostics không có source/position ở nhóm "project-level".
4. Giữ kind để hiển thị ERROR khác WARNING/NOTE.
5. Giữ nguyên message và code (nếu có), không gộp hai lỗi khác nhau chỉ vì cùng dòng.
6. Gắn compilation ID/source version để không trộn diagnostics của lượt compile cũ với buffer mới.

Trong hệ thống sinh code, duy trì source map giữa generated file và input của người dùng. Nếu chưa có mapping tin cậy, hiển thị rõ lỗi của generated source thay vì khẳng định lỗi nằm ở dòng tương ứng trong source gốc.

### 8.4 API response mẫu dạng ý tưởng

Một service có thể trả cấu trúc sau (đây là **mô hình dữ liệu**, không phải object do JavaCompiler tự sinh):

```text
CompilationResult
  status: COMPILE_ERROR
  compilerAvailable: true
  taskSucceeded: false
  errorCount: 1
  warningCount: 0
  diagnostics:
    - kind: ERROR
      sourceUri: string:///lesson/Broken.java
      line: 4
      column: 17
      position: 77
      startPosition: 77
      endPosition: 83
      message: text từ getMessage(Locale.ROOT)
```

Một service dùng JSON cần escape nội dung message khi serialize, không nối chuỗi tùy tiện. Đối với dữ liệu nhạy cảm, tránh trả full source và compiler internals ngoài mức cần thiết; người dùng hợp lệ chỉ cần những diagnostic gắn với source của chính request.

## 9. Vì sao warnings có thể "biến mất"?

Các compiler options ảnh hưởng trực tiếp loại và lượng diagnostics:

| Option/điều kiện | Hệ quả |
| --- | --- |
| `-Xlint:deprecation` | Yêu cầu javac chi tiết hơn về deprecated API |
| `-Xlint:all` | Mở nhiều nhóm lint warnings, có thể làm log nhiều hơn |
| `-Werror` | Cho phép coi warnings là nguyên nhân thất bại theo policy compiler |
| `-proc:none` | Không chạy annotation processors trong lượt compiler này |
| `--release 17` | Dùng Java 17 source/API/target compatibility trên JDK hỗ trợ option |
| Không có classpath/module-path phù hợp | Có thể sinh symbol/package/module errors |
| Chọn khác `Locale` | Có thể làm thông điệp trình bày khác |
| Dùng compiler vendor khác hoặc JDK version khác | Diagnostic code, message, vị trí và mức warning có thể khác |

Nếu output mong đợi `WARNING` nhưng thực tế là `MANDATORY_WARNING`, đây **không nhất thiết là bug trong collector**. Vẫn phải thống kê warning dưới cả hai Kind. Với deprecation, compiler có thể báo ngắn gọn rằng method deprecated hoặc báo tại từng call site tùy options và implementation.

**Đừng cấu hình `-Xlint:all` chỉ để có một bài kiểm thử đơn giản** nếu sản phẩm cần log ít nhiễu: hãy bật đúng lint key yêu cầu, rồi test bằng source cố định. Đừng biến mọi `NOTE` thành `WARNING` chỉ vì câu chữ của message chứa "warning" — Kind là dữ liệu cấu trúc.

## 10. Xử lý lỗi khi setup, compile, và run

Một runtime compilation service thường có tối thiểu ba bước:

```text
VALIDATE REQUEST
    |
    v
CREATE COMPILATION TASK
    |
    v
CALL COMPILER & COLLECT DIAGNOSTICS
    |
    +-- task true ----> stage compiled outputs
    |                   +-- warnings? report separately
    |
    +-- task false ---> return compiler diagnostics
    |
    +-- exception ----> return infrastructure/setup failure
    |
    v
(if authorized) LOAD/RUN BYTECODE --> runtime errors belong to another phase
```

Các lỗi khác nhau cần phân loại:

**Lỗi mã nguồn:** Java syntax/type/access errors là compiler diagnostics. `CompilationTask.call()==false` là tín hiệu quan trọng; show diagnostic file/line/column cho tác giả source.

**Lỗi cấu hình compiler:** Không có compiler, option không hợp lệ, file manager không khởi tạo được, output dir không ghi được, thiếu dependencies. Có thể nhận exception hoặc diagnostic không gắn source. Hãy cung cấp trạng thái setup/infra, không giả dạng "có lỗi ở dòng 1".

**Lỗi runtime:** Compile thành công không chứng minh class đã biên dịch sẽ load/link/run thành công. `ClassNotFoundException`, `NoClassDefFoundError`, `ExceptionInInitializerError`, lỗi nghiệp vụ, timeout hoặc security events khi chạy code là giai đoạn khác. Không đưa chúng vào mảng `DiagnosticCollector` như một lỗi compile giả.

**Lỗi do chính diagnostic processing:** Nếu code format cố gọi `d.getSource().getName()` mà không check `null`, hoặc lấy `getLineNumber()-1` rồi index mảng mà không check `Diagnostic.NOPOS`, formatter có thể ném exception dù compiler đã làm đúng. Hãy tách exception formatter khỏi compilation status nếu hệ thống cần bền vững.

## 11. Kỹ thuật triển khai an toàn cho hệ thống biên dịch động

### 11.1 Giữ output theo từng lần compile

Mỗi task nên có source snapshot, collector, file manager, output directory/target storage riêng. Biên dịch vào staging và chỉ publish class artifacts nếu task success **và policy ứng dụng chấp nhận** (ví dụ không có warning nghiêm trọng). Demo dùng temp directory, code production có thể có caching/versioning nhưng không được nhầm output từ hai build requests.

Không cho client tự truyền tùy ý `-d`, `-classpath`, `--module-path`, `-Xplugin` hoặc processor path nếu service có shared machine; hãy whitelist compiler options. Annotation processors có thể thực thi code lúc compile; `-proc:none` chỉ giảm riêng rủi ro đó và không thay thế sandbox/giới hạn tài nguyên.

### 11.2 Biên dịch mã không đáng tin là vấn đề bảo mật riêng

`JavaCompiler` chỉ là compiler API, **không phải sandbox**. Việc một source biên dịch thành công không làm nó an toàn để thực thi. Khi nhận Java code từ internet/người dùng:

- Giới hạn CPU, memory, time, filesystem/network permission theo cơ chế isolation phù hợp.
- Vô hiệu hóa annotation processing nếu không cần.
- Chỉ cho phép classpath/modules và compilation options đã được xác định.
- Không load/run artifact trong JVM chứa secrets hoặc service credentials.
- Không cho code mới truy cập trực tiếp class loader hoặc output path của người dùng khác.
- Giữ logs có kiểm soát, tránh lưu full source hay message chứa thông tin nhạy cảm không cần thiết.

Tách **diagnostic collection** khỏi **bytecode execution**; bài này chỉ tạo và đọc diagnostics.

### 11.3 Không giữ collector xuyên requests

Nếu cùng một service compile file A rồi file B, collector cũ có thể giữ thông báo của A. Với concurrent requests, reuse collector/file manager không có protocol rõ ràng còn gây nhầm resource identity và race. Khởi tạo một collector mới, một result object mới và một output scope riêng trên mỗi lượt độc lập.

Nếu muốn sort/group diagnostics, có thể copy list sau khi `call()` và file manager close phù hợp. Tránh giữ mã nguồn khổng lồ trong collector/source objects lâu hơn cần thiết.

### 11.4 Quy tắc sử dụng diagnostics trong CI/IDE

Trong IDE, show compiler diagnostics gắn với đúng buffer version; trong CI, báo status theo `task.call()`, warning policy và artifact publish result; trong trình chấm tự động, phân biệt lỗi compile với lỗi test runtime. Khi auto-fix, dùng kind + source ranges + phân tích AST/semantics, không quyết định sửa code chỉ từ một message localized.

## 12. Những ngộ nhận và anti-patterns

| Ngộ nhận / sai lầm | Thực tế / cách sửa |
| --- | --- |
| "`DiagnosticCollector` tự biết biên dịch thành công." | Collector chỉ lưu diagnostics; status đến từ `task.call()` và tình trạng exception. |
| "Có warning tức là task failed." | Warnings thường đi cùng `success=true`; policy `-Werror` là trường hợp riêng. |
| "Không có `ERROR` tức là chắc chắn success." | Task có thể chưa chạy/exception/config failure; kiểm tra Boolean và lỗi API. |
| "Chỉ Kind `WARNING` là cảnh báo." | Cần tính cả `MANDATORY_WARNING`. |
| "Mọi diagnostic có `getSource()`." | `getSource()` có thể `null`; phải có fallback toàn compilation. |
| "Line và column bắt đầu từ 0." | API thường trả **1-based** khi có vị trí; `getPosition` là **0-based offset**. |
| "Offset là số byte của UTF-8 file." | Không; là character offset trên source object. |
| "`getEndPosition` luôn có cùng span ở mọi javac version." | Diagnostic range phụ thuộc compiler/loại lỗi; không hard-code. |
| "`getCode()` là enum ổn định toàn Java." | Compiler-specific, có thể null; không dùng như public stable protocol mà không versioning. |
| "`getMessage(Locale)` trả một chuỗi cố định." | Câu chữ có thể khác locale/implementation/JDK version. |
| "Dùng `StringJavaFileObject` thì .class tự nằm trong RAM." | In-memory **source** không tự thành in-memory **output**; configure file manager. |
| "Compiler task chỉ có thể báo lỗi bằng `Diagnostic`." | Thiếu compiler, option/file manager lỗi có thể ném exception hoặc ghi kênh khác. |
| "Compiler success nghĩa là bytecode chắc chắn chạy được mọi nơi." | Runtime linkage/dependencies/security và bugs là giai đoạn khác. |
| "Dùng `d.getLineNumber()-1` truy cập array là luôn an toàn." | Có `NOPOS` và out-of-range nếu source/line mapping khác; cần bounds check. |
| "Lấy diagnostics từ task trước để show trong editor hiện tại." | Phải gắn compiler result với source snapshot/version cụ thể. |
| "Compiler có thể an toàn chạy bất kỳ code người dùng." | Không. Biên dịch và thực thi untrusted code cần isolation/security. |

## 13. Một checklist debug thực hành

Nếu hệ thống biên dịch động trả `false` hoặc màn hình IDE không đánh dấu đúng lỗi, hãy kiểm tra theo thứ tự:

1. **Compiler có tồn tại?** `ToolProvider.getSystemJavaCompiler()!=null`, module `jdk.compiler` sẵn sàng.
2. **Source đúng chưa?** `JavaFileObject.getKind()==SOURCE`, URI/path, `getCharContent()` trùng snapshot vừa gửi.
3. **Có truyền collector cho đúng task?** Tham số thứ ba của `JavaCompiler.getTask`.
4. **Task có thực sự chạy?** Có gọi `call()`, bắt exception setup/I/O.
5. **Options có đúng?** `--release`, `-classpath`, `--module-path`, lint, annotation processing.
6. **Status nhận được?** `Boolean.TRUE.equals(task.call())`, không chỉ đếm errors.
7. **Warning có được cộng đủ hai Kind?** `WARNING` + `MANDATORY_WARNING`.
8. **Diagnostic thuộc source nào?** `getSource()`, URI, class loader/file manager, source snapshot ID.
9. **Có position không?** `getPosition()!=Diagnostic.NOPOS` và source khác null.
10. **Line/column map ra editor đúng không?** 1-based vs 0-based; CRLF, tab, Unicode, generated wrapper.
11. **Message có bị parse làm protocol không?** Dùng `getKind()`, `getCode()` có kiểm soát, source ranges; message phục vụ người đọc.
12. **Output artifacts ở đâu?** `-d`, file manager, cleanup; đừng publish khi compile false.
13. **Có lỗi runtime riêng?** Bắt/expose ở giai đoạn execute, không trộn vào diagnostics compilation.
14. **Có concurrent requests?** Kiểm tra collector/fileManager/output scopes riêng biệt.
15. **Không tin test vị trí cứng của một JDK:** Nếu mọi thứ đúng trừ column/warning kind trên JDK khác, xem JavaCompiler implementation trước khi kết luận bug.

## 14. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** `DiagnosticCollector` được truyền vào tham số nào của `JavaCompiler.getTask`?

**Đáp án:** Tham số thứ **ba**: `diagnosticListener`; theo thứ tự `(out, fileManager, diagnosticListener, options, classes, compilationUnits)`.

**Câu 2.** `task.call()` trả `true` và collector có một `MANDATORY_WARNING`. Compilation có phải lỗi?

**Đáp án:** Không mặc nhiên. Task đã thành công, kèm warning. Ứng dụng có thể trình bày `SUCCESS_WITH_WARNINGS`; nếu policy là `-Werror` hoặc custom rejection, status có thể khác.

**Câu 3.** Source có `int n = "oops";`, compiler báo `ERROR` dòng 4, cột 17. Line và column tính từ 0 hay 1?

**Đáp án:** Từ **1**. `getPosition()` là character offset từ **0** của source. Nếu editor cần zero-based line index thì trừ 1 sau khi đã check `NOPOS`.

**Câu 4.** `getSource()` trả `null` và `getPosition()` trả `-1`. Ứng dụng nên đánh dấu tại `line 0` không?

**Đáp án:** Không. Đây là diagnostic không có source/location cụ thể; show ở cấp compilation/project.

**Câu 5.** `getCode()` có thể dùng làm mã giao thức ổn định giữa các compiler vendors không?

**Đáp án:** Không nên. `getCode()` compiler-specific và có thể `null`. Cần versioning/mapping của ứng dụng nếu phải dựa vào nó.

**Câu 6.** `getMessage(Locale.ROOT)` có chắc giống hoàn toàn giữa JDK 17, 21, 24 không?

**Đáp án:** Không. Nội dung thông báo phụ thuộc compiler implementation và phiên bản. Hãy test semantics (kind/status/location hợp lý), không hard-code nguyên văn message.

**Câu 7.** `getStartPosition`, `getPosition` và `getEndPosition` khi cùng tồn tại có quan hệ gì?

**Đáp án:** Theo API, `start <= position <= end`. Đây là các character offsets, không phải byte offsets.

**Câu 8.** `-Xlint:deprecation` có làm compile thất bại chỉ vì gọi method deprecated không?

**Đáp án:** Không mặc định. Nó bật diagnostic về deprecated usage; để chặn warning theo policy có thể dùng `-Werror` hoặc post-check.

**Câu 9.** `Source` là in-memory JavaFileObject. Chạy compiler có chắc không tạo class file trên disk?

**Đáp án:** Không. Source in RAM và output là hai chuyện riêng. Với `StandardJavaFileManager`, `-d` sẽ ghi class files tới output directory.

**Câu 10.** `task.call()` báo `false` nhưng app vẫn thấy `.class` trong output directory. Có nên load chúng không?

**Đáp án:** Không. Compiler có thể ghi output một phần trước khi fail; chỉ publish artifacts từ staging khi task/policy thành công.

**Câu 11.** Khi hiển thị lỗi ở một source được generator thêm 30 dòng imports trước nội dung người dùng, có thể lấy `getLineNumber()` rồi đánh vào raw textarea không?

**Đáp án:** Không trực tiếp. Line thuộc **generated compilation unit**; cần source map để chuyển về input của người dùng.

**Câu 12.** Dùng chung `DiagnosticCollector` giữa hai compiler tasks độc lập có sao không?

**Đáp án:** Có thể trộn diagnostics cả hai lượt, đặc biệt khi chạy song song. Tạo collector riêng cho mỗi task và giữ compilation ID riêng.

**Câu 13.** `ToolProvider.getSystemJavaCompiler() == null` chứng minh source sai cú pháp?

**Đáp án:** Không. Đó là compiler unavailable trong môi trường chạy; source chưa được compiler xử lý.

**Câu 14.** Một Java source compile thành công nhưng khi load class thiếu dependency thì lỗi thuộc giai đoạn nào?

**Đáp án:** Runtime/linkage phase, không phải `DiagnosticCollector` của compilation ban đầu. Status compile và execution nên tách biệt.

**Câu 15.** Compiler có thể phát `NOTE` mà không có `ERROR`/`WARNING`. Có nên tăng errorCount?

**Đáp án:** Không. Tính errorCount chỉ với `Diagnostic.Kind.ERROR`; giữ `NOTE` như event thông tin.

**Câu 16.** Một service compile mã do người dùng gửi dùng `-proc:none` thì đã an toàn tuyệt đối chưa?

**Đáp án:** Chưa. Đó chỉ là một giảm thiểu rủi ro về annotation processors. Vẫn cần isolation, resource quotas, whitelisted options, quản lý classpath và tuyệt đối không chạy untrusted bytecode trong process chứa secrets.

## 15. Ghi nhớ

- **`DiagnosticCollector` thu thập diagnostics, `CompilationTask.call()` báo kết quả**; hai nguồn này bổ sung nhau.
- **`ERROR` khác `WARNING` và `MANDATORY_WARNING`**. Có warning vẫn có thể compile thành công.
- **Vị trí không phải lúc nào cũng tồn tại**: `getSource()` có thể null; `getPosition()/getLineNumber()/getColumnNumber()` có thể là `Diagnostic.NOPOS`.
- **Line/column thường 1-based; offsets là character offsets 0-based**, không phải vị trí byte UTF-8.
- **Message và code không phải stable protocol:** `getMessage(Locale)` phụ thuộc implementation/locale/JDK, `getCode()` có thể null.
- **Tách ba pha:** setup compiler, compile diagnostics/artifacts, và runtime execution.
- **Một lượt biên dịch = một collector + file manager/output scope + source snapshot** để tránh kết quả cũ và race.
- **JDK compiler cần hiện diện**, annotation processors/options/classpath cần được kiểm soát, đặc biệt khi biên dịch mã không đáng tin.
- **Kiểm thử cả thành công, lỗi và warning**; test stdout của môi trường cụ thể và không bắt UI phải dùng một chuỗi compiler message cố định.

### Tài liệu chuẩn (Java SE 17)

- [`javax.tools.JavaCompiler` — `getTask` và cách dùng `DiagnosticCollector`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html)
- [`javax.tools.Diagnostic` — kind, source, line/column, position, code, message](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/Diagnostic.html)
- [`javax.tools.DiagnosticCollector` — thu thập danh sách diagnostics](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/DiagnosticCollector.html)
- [`javax.tools.ToolProvider` — lấy system Java compiler](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html)
- [`javax.tools.JavaFileObject` và `SimpleJavaFileObject` — nguồn biên dịch](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html)
- [`javax.tools.StandardJavaFileManager` — input/output và resources](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html)
- [`javac` options của Java 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
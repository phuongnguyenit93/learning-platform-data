# Thu DiagnosticCollector, vị trí lỗi và mức độ chẩn đoán

## Mục tiêu

Sau bài học, bạn có thể:

1. Dùng Java Compiler API để gọi trình biên dịch từ một chương trình Java thay vì chỉ chạy `javac` ở terminal.
2. Gắn `DiagnosticCollector<JavaFileObject>` vào `JavaCompiler.CompilationTask`, lấy lỗi, cảnh báo và ghi chú dưới dạng đối tượng có cấu trúc.
3. Giải thích `Diagnostic.Kind` và sự khác biệt giữa `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE` và `OTHER`.
4. Thu file nguồn, số dòng, cột, offset và vùng lỗi bằng `getSource()`, `getLineNumber()`, `getColumnNumber()`, `getPosition()`, `getStartPosition()` và `getEndPosition()`.
5. Xử lý đúng `Diagnostic.NOPOS`, nguồn `null`, thông báo được bản địa hóa và mã diagnostic phụ thuộc compiler.
6. Thực hành hai kịch bản Java 17+: lỗi kiểu biên dịch từ chuỗi source trong bộ nhớ và cảnh báo generic khi biên dịch file Java trên đĩa.
7. Xây dựng báo cáo chẩn đoán có khả năng tái lập, phân biệt kết quả compile với exception của chương trình đã chạy.

Bài tập trung vào **thu chẩn đoán của compiler, vị trí lỗi và mức độ chẩn đoán**. Không yêu cầu thư viện bên thứ ba hay IDE.

## 1. Diagnostic khác gì với thông báo in ra stderr?

Khi biên dịch source Java, compiler có thể phát:

- Lỗi cú pháp: thiếu dấu `;`, ngoặc không đóng.
- Lỗi kiểm tra kiểu: gán `String` cho biến `int`, gọi method chưa tồn tại.
- Cảnh báo: raw generic, unchecked conversion, API deprecated, hành vi được bật kiểm tra qua `-Xlint`.
- Ghi chú: thông tin phụ từ compiler hoặc annotation processor.

Ở command line, `javac` thường trình bày những thông báo này bằng văn bản có filename, line number, source snippet và caret. Ví dụ về **ý nghĩa** của một lỗi (không phải stdout cố định):

~~~text
error: incompatible types: String cannot be converted to int
~~~

Nếu bạn viết IDE, dịch vụ chấm code hoặc công cụ build, việc tách thông báo bằng regex theo các từ `error:` hoặc `warning:` rất dễ gãy: văn bản có thể thay đổi theo JDK, compiler provider, locale và tùy chọn.

Java Compiler API cung cấp giao diện **`Diagnostic<S>`**, chứa những trường có cấu trúc như loại chẩn đoán, nguồn, vị trí, code và nội dung thông báo. `DiagnosticCollector<S>` là listener tiện lợi gom các đối tượng `Diagnostic` để bạn đọc sau.

~~~text
Source: JavaFileObject(s)
         |
         v
JavaCompiler.getTask(..., diagnosticListener, ...)
         |
         v
CompilationTask.call()
         |
         +--- boolean compile success / failure
         |
         +--- DiagnosticListener.report(diagnostic)
                      |
                      v
                DiagnosticCollector
                      |
                      v
               getDiagnostics()
                      |
                      +--- kind / code / message
                      +--- source file
                      +--- line / column / offsets
~~~

**Đừng nhầm:** collector không tự sửa mã, không tự biên dịch lại và không chạy chương trình đã được biên dịch. Nó chỉ giữ những diagnostic được công cụ báo trong tác vụ biên dịch.

## 2. Các thành phần trong Java Compiler API

| API | Vai trò |
| --- | --- |
| `javax.tools.ToolProvider` | Tìm system Java compiler nếu runtime cung cấp |
| `javax.tools.JavaCompiler` | Tạo task biên dịch bằng API |
| `JavaCompiler.CompilationTask` | Một tác vụ compiler; `call()` thực hiện tác vụ |
| `javax.tools.DiagnosticListener<S>` | Nhận từng thông báo qua `report(...)` |
| `javax.tools.DiagnosticCollector<S>` | Implementation của listener có lưu danh sách |
| `javax.tools.Diagnostic<S>` | Một lỗi/cảnh báo/ghi chú có cấu trúc |
| `javax.tools.JavaFileObject` | Đại diện cho Java source/class file |
| `javax.tools.SimpleJavaFileObject` | Lớp tiện ích để tự tạo đối tượng source |
| `javax.tools.StandardJavaFileManager` | Cung cấp file objects và kiểm soát nguồn/đầu ra |
| `javax.tools.Diagnostic.Kind` | Enum phân loại mức chẩn đoán |

Những API chính ở package `javax.tools` thuộc module Java `java.compiler`. Compile-time model và diagnostic không phải Java runtime Reflection: không cần load class `Broken` để compiler phát hiện gán sai kiểu trong source của nó.

### 2.1 Quy trình gắn collector vào task

~~~java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
DiagnosticCollector<JavaFileObject> collector =
        new DiagnosticCollector<>();

try (StandardJavaFileManager fileManager =
        compiler.getStandardFileManager(
                collector, Locale.ROOT, StandardCharsets.UTF_8)) {

    JavaCompiler.CompilationTask task = compiler.getTask(
            null, fileManager, collector, options, null, sources);

    boolean compiled = Boolean.TRUE.equals(task.call());

    for (Diagnostic<? extends JavaFileObject> diagnostic
            : collector.getDiagnostics()) {
        // Xử lý từng diagnostic.
    }
}
~~~

Đây là **đoạn mã minh họa trong một method**, chưa phải chương trình chạy độc lập: cần imports, kiểm tra compiler `null`, biến `options` và `sources`. Ví dụ đầy đủ ở mục 4.

Chú ý:

- `getTask(...)` tạo task; `task.call()` mới yêu cầu biên dịch.
- Đối số listener trong `getTask(...)` là nơi nhận các diagnostic có cấu trúc.
- `getStandardFileManager(...)` nhận listener cho những chẩn đoán thuộc cơ chế file manager.
- Đối số writer đầu tiên của `getTask` dành cho output phụ của công cụ. DiagnosticListener không đồng nghĩa với việc bắt toàn bộ `System.out` hoặc `System.err`.
- `getDiagnostics()` trả các diagnostic đã thu; để so sánh hai lần compile, nên có **collector mới cho mỗi task**.
- Hãy đóng file manager bằng `try-with-resources`; một task không được tái dùng để `call()` lần hai.

### 2.2 Compiler có thể không tồn tại

`ToolProvider.getSystemJavaCompiler()` có thể trả `null` khi runtime image không cung cấp compiler, chẳng hạn một bản Java runtime tùy biến. Một JDK đầy đủ thường có compiler, nhưng không nên mặc định mọi môi trường chạy Java đều có.

~~~java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException(
            "Java compiler is unavailable in this runtime");
}
~~~

Snippet này cần imports `JavaCompiler` và `ToolProvider` và đặt trong một method. Nếu làm dịch vụ compile mã nguồn, kiểm tra này giúp thông báo lỗi môi trường rõ hơn thay vì `NullPointerException`.

### 2.3 Task result khác với diagnostics

Thông thường `Boolean.TRUE.equals(task.call())` là true khi compile thành công và false khi có lỗi. Nhưng không suy ra một cách máy móc:

- Có warning thì task luôn false: **sai**, warning thường không ngăn compile.
- Không có ERROR trong collector thì toàn bộ pipeline chắc chắn thành công: **sai**, có thể xảy ra lỗi ngoài stream diagnostic.
- `getDiagnostics().isEmpty()` nghĩa là ứng dụng sẽ chạy đúng: **sai**, đó chỉ là thông tin compiler đã báo.
- Mọi exception trong file manager hoặc annotation processor đều được chuyển thành `Diagnostic.Kind.ERROR`: **không được bảo đảm**.

Khi xây công cụ, ghi **cả** boolean task, danh sách diagnostics, compiler options và exception phát sinh ngoài luồng chẩn đoán.

## 3. Phân loại Diagnostic.Kind

Các loại cơ bản ở Java 17:

| `Diagnostic.Kind` | Ý nghĩa | Phân loại trong giao diện |
| --- | --- | --- |
| `ERROR` | Lỗi biên dịch | Error |
| `WARNING` | Cảnh báo thông thường | Warning |
| `MANDATORY_WARNING` | Cảnh báo bắt buộc theo quy tắc của công cụ | Warning |
| `NOTE` | Ghi chú, thông tin hỗ trợ | Info |
| `OTHER` | Loại diagnostic còn lại | Other/Info tùy chính sách |

Nếu muốn đếm nhóm cảnh báo, kiểm tra **cả** `WARNING` và `MANDATORY_WARNING`:

~~~java
long warnings = collector.getDiagnostics().stream()
        .filter(d ->
            d.getKind() == Diagnostic.Kind.WARNING
            || d.getKind() == Diagnostic.Kind.MANDATORY_WARNING)
        .count();
~~~

Đây là snippet, giả định `collector` đã khai báo. Không dùng `ordinal()` của enum làm mức severity: thứ tự enum không phải hợp đồng ưu tiên hiển thị.

### 3.1 Compiler options ảnh hưởng số diagnostics

Một source có raw generic có thể compile bình thường, nhưng khi thêm `-Xlint:unchecked` thì compiler phát cảnh báo chi tiết. Một source gọi API deprecated có thể phát thêm cảnh báo với `-Xlint:deprecation`.

Khi thêm `-Werror`, build có thể **thất bại vì có warning**. Không mặc định mọi `WARNING` sẽ bị đổi `Kind` thành `ERROR`: compiler có thể báo warning gốc và thêm diagnostic liên quan chính sách xử lý warning.

Muốn so sánh thống kê giữa hai build, phải biết cùng source, compiler version, classpath, `--release`, các `-Xlint` options và `-Werror` hay không.

### 3.2 Ghi chú từ annotation processor

Annotation processor có thể phát:

~~~java
processingEnv.getMessager().printMessage(
        javax.tools.Diagnostic.Kind.NOTE,
        "Processed one element",
        element);
~~~

Đây là snippet **bên trong processor**, với biến `element` thuộc `javax.lang.model.element.Element`. `Messager` báo thông điệp tới cơ chế chẩn đoán compile. Khi javac chuyển nó tới listener, bạn có thể nhận `NOTE` trong collector.

Nếu processor cung cấp vị trí của element/annotation, compiler có thể liên hệ diagnostic với source. Tuy nhiên, không phải `NOTE` nào cũng có file, dòng và cột; code hiển thị phải xử lý được trường hợp thiếu vị trí.

## 4. Ví dụ hoàn chỉnh A: bắt lỗi của source trong bộ nhớ

Ta xây **driver Java hợp lệ** có tên `DiagnosticCollectorDemo`. Driver dùng Compiler API biên dịch một source khác tên `sample.Broken`. Source `Broken` **cố tình sai kiểu** để tạo `Diagnostic.Kind.ERROR`.

Cần JDK 17 trở lên. Kiểm tra:

~~~bash
java -version
javac -version
~~~

### 4.1 Tạo file DiagnosticCollectorDemo.java

~~~java
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class DiagnosticCollectorDemo {

    private static final class StringSource extends SimpleJavaFileObject {
        private final String sourceCode;

        StringSource(String className, String sourceCode) {
            super(
                    URI.create("string:///"
                            + className.replace('.', '/')
                            + Kind.SOURCE.extension),
                    Kind.SOURCE);
            this.sourceCode = sourceCode;
        }

        @Override
        public CharSequence getCharContent(
                boolean ignoreEncodingErrors) {
            return sourceCode;
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "JDK with Java compiler required");
        }

        String brokenCode = String.join("\n",
                "package sample;",
                "public class Broken {",
                "    public static void main(String[] args) {",
                "        int number = \"wrong\";",
                "    }",
                "}"
        ) + "\n";

        JavaFileObject source =
                new StringSource("sample.Broken", brokenCode);
        DiagnosticCollector<JavaFileObject> collector =
                new DiagnosticCollector<>();

        Path output = Files.createTempDirectory("compile-diagnostics-");

        try (StandardJavaFileManager fileManager =
                compiler.getStandardFileManager(
                        collector, Locale.ROOT, StandardCharsets.UTF_8)) {

            List<String> options = List.of(
                    "--release", "17",
                    "-proc:none",
                    "-d", output.toString()
            );

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null,
                    fileManager,
                    collector,
                    options,
                    null,
                    List.of(source)
            );

            boolean compiled = Boolean.TRUE.equals(task.call());
            long errors = collector.getDiagnostics().stream()
                    .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
                    .count();

            System.out.println("compiled=" + compiled);
            System.out.println("errors=" + errors);

            for (Diagnostic<? extends JavaFileObject> d
                    : collector.getDiagnostics()) {
                if (d.getKind() == Diagnostic.Kind.ERROR) {
                    System.out.println(
                            "ERROR at line " + d.getLineNumber());
                    System.out.println(
                            "positionKnown="
                            + (d.getPosition() != Diagnostic.NOPOS));
                }
            }
        }
    }
}
~~~

Giải thích:

- `StringSource` kế thừa `SimpleJavaFileObject` để cung cấp source qua `getCharContent`.
- URI của nguồn là `string:///sample/Broken.java`; đây là tên logic của Java source, không buộc file tồn tại trên ổ đĩa.
- `Files.createTempDirectory` tạo output thật cho compiler. Đường dẫn đó không được in ra stdout nên expected output không phụ thuộc tên ngẫu nhiên.
- `-proc:none` tắt annotation processing trong phép thử, tránh một processor bên ngoài tạo thêm thông báo.
- `--release 17` giới hạn ngôn ngữ, platform API và class-file target theo Java 17.
- `DiagnosticCollector` được truyền vào compiler task. Driver đếm error và đọc số dòng ở mỗi `Diagnostic`.
- Source `Broken` được tạo bằng `String.join("\n", ...)` để các dòng có thứ tự rõ ràng. Dòng sai kiểu chính xác là **dòng 4**.
- File manager được đóng bằng `try-with-resources`. Output directory tạm vẫn có thể tồn tại sau lần chạy; một công cụ thực nên có cơ chế cleanup phù hợp cho output do mình tạo.

**Phân biệt hai tầng:** chương trình `DiagnosticCollectorDemo` phải compile và chạy thành công; tác vụ compiler **bên trong** chương trình được thiết kế để thất bại khi compile `sample.Broken`.

### 4.2 Biên dịch và chạy driver trên Linux/macOS

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out DiagnosticCollectorDemo.java
java -cp out DiagnosticCollectorDemo
~~~

### 4.3 Biên dịch và chạy trên Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out DiagnosticCollectorDemo.java
java -cp out DiagnosticCollectorDemo
~~~

Stdout với javac JDK 17+ phù hợp:

~~~text
compiled=false
errors=1
ERROR at line 4
positionKnown=true
~~~

Không đưa cột và toàn bộ message vào expected output vì **cách chọn vị trí chi tiết và văn bản thông báo có thể khác giữa compiler/provider**.

### 4.4 Thử sửa lỗi để so sánh

Trong code `String.join`, thay chính xác dòng:

~~~java
"        int number = \"wrong\";",
~~~

bằng:

~~~java
"        int number = 7;",
~~~

Đây là **hai dòng code trong Java driver**, không phải hai chương trình riêng. Biên dịch lại driver rồi chạy; kết quả mong đợi:

~~~text
compiled=true
errors=0
~~~

Vòng `for` chỉ in các diagnostic `ERROR` nên sau khi sửa không có dòng chi tiết lỗi. Thí nghiệm trước–sau cố định compiler/options và chỉ thay source được compile.

## 5. Lấy tên nguồn, dòng, cột và vị trí lỗi

Một đối tượng `Diagnostic<S>` cho phép lấy các trường:

| Phương thức | Ý nghĩa |
| --- | --- |
| `getKind()` | Loại diagnostic: error/warning/note... |
| `getSource()` | Source object gắn với diagnostic; có thể `null` |
| `getLineNumber()` | Số dòng bắt đầu từ **1**, hoặc `NOPOS` |
| `getColumnNumber()` | Số cột bắt đầu từ **1**, hoặc `NOPOS` |
| `getPosition()` | Offset ký tự bắt đầu từ **0**, hoặc `NOPOS` |
| `getStartPosition()` | Offset đầu vùng lỗi, có thể `NOPOS` |
| `getEndPosition()` | Offset cuối vùng lỗi, có thể `NOPOS` |
| `getCode()` | Mã chẩn đoán phụ thuộc compiler/provider, có thể `null` |
| `getMessage(Locale)` | Nội dung thông báo được localize theo khả năng compiler |

Theo Java SE 17 `Diagnostic`, khi có vị trí hợp lệ:

~~~text
getStartPosition() <= getPosition() <= getEndPosition()
~~~

Line và column đếm từ 1, nhưng offset ký tự đếm từ 0. `Diagnostic.NOPOS` là giá trị sentinel (trong API hiện hành là `-1`). **Không dùng số 0 để biểu diễn “không xác định”**, vì offset 0 là ký tự đầu tiên hợp lệ.

### 5.1 Formatter an toàn khi không có vị trí

Ví dụ một method tiện ích có thể đặt trong class của bạn:

~~~java
static void printDiagnostic(
        Diagnostic<? extends JavaFileObject> d) {

    String file = d.getSource() == null
            ? "(no source)"
            : d.getSource().getName();

    String where = d.getPosition() == Diagnostic.NOPOS
            ? "(no position)"
            : "line " + d.getLineNumber()
                    + ", column " + d.getColumnNumber();

    System.out.println(d.getKind()
            + " | " + file + " | " + where);
    System.out.println("code=" + d.getCode());
    System.out.println("message=" + d.getMessage(Locale.ROOT));
}
~~~

Đây là snippet, cần import `javax.tools.Diagnostic`, `JavaFileObject` và `java.util.Locale`. Nó **không phải class có `main` độc lập**.

Nếu source không có, đừng gọi `d.getSource().getName()` trực tiếp: sẽ gặp `NullPointerException`. Nếu position bằng `NOPOS`, đừng tạo link tới dòng `-1` hoặc tự đoán rằng diagnostic thuộc dòng đầu tiên.

### 5.2 Khi diagnostic không gắn vào một source file

Có những warning/error ở mức công cụ hoặc cấu hình, không nằm trong một source cụ thể. Khi đó thông tin có thể tương đương:

~~~text
source: null
position: NOPOS
line: NOPOS
column: NOPOS
~~~

Đây là **trường hợp minh họa**, không phải output cố định của một lệnh cụ thể. Khi vẽ giao diện, đưa thông điệp vào vùng thông báo cấp task/project, thay vì tô một dòng bất kỳ.

Một diagnostic cũng có thể có `getSource() != null` nhưng không có vị trí phù hợp. Hãy kiểm tra từng trường, không giả định chỉ cần source khác null thì line/column chắc chắn hợp lệ.

### 5.3 Position khác byte offset của file

Offset mà API nói tới là vị trí ký tự trong source. Không thể tùy tiện dùng nó làm **byte offset** trong file UTF-8: các ký tự tiếng Việt có thể chiếm nhiều byte. Một editor có thể dùng vị trí dựa trên UTF-16 code units, Unicode code points hoặc định dạng khác; cần ánh xạ đúng.

Những điểm phải thống nhất khi đánh dấu vị trí:

- Cùng **phiên bản source** đã đưa cho compiler, không phải file đã được người dùng sửa sau đó.
- Quy tắc newline: LF hoặc CRLF.
- Tab có thể hiển thị như nhiều cột trực quan nhưng không đơn giản là nhiều ký tự.
- Ký tự ngoài BMP, surrogate pair và giao thức position encoding của editor.
- Offset đầu/cuối của diagnostic có quy tắc riêng; cần kiểm tra contract và độ dài nguồn trước khi cắt chuỗi.

Đừng mặc định `getStartPosition()` và `getEndPosition()` dùng trực tiếp trong `source.substring(start, end)` mà không kiểm tra đầu mút và quy ước editor. Nếu chỉ cần gắn vị trí ban đầu, dùng line/column đã được xác minh có thể đơn giản hơn.

### 5.4 Source có thể là generated source

Annotation processor có thể sinh Java source rồi compiler báo lỗi trong file mới sinh. Lúc này `getSource()` trỏ đến source được compiler phân tích, không nhất thiết là file người dùng vừa mở. Muốn liên hệ lỗi ngược với file nguồn kích hoạt processor cần thêm thông tin như originating element hoặc source mapping do pipeline của bạn duy trì. `DiagnosticCollector` không tự dựng bản đồ nguồn tùy ý.

## 6. Ví dụ hoàn chỉnh B: thu cảnh báo từ file trên đĩa

Ví dụ A có `ERROR`. Bây giờ cần một chương trình compile thành công nhưng có warning. Ta dùng raw generic và bật `-Xlint:unchecked`.

### 6.1 Tạo src/sample/UncheckedDemo.java

~~~java
package sample;

import java.util.ArrayList;
import java.util.List;

public class UncheckedDemo {
    public static void main(String[] args) {
        List<String> values = new ArrayList();
        System.out.println(values.size());
    }
}
~~~

`new ArrayList()` dùng raw type được gán vào `List<String>`, khiến javac báo unchecked conversion khi bật `-Xlint:unchecked`. Việc đổi sang `new ArrayList<>()` sẽ loại bỏ dạng warning này.

### 6.2 Tạo FileDiagnosticDemo.java

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
import javax.tools.ToolProvider;

public class FileDiagnosticDemo {
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Compiler unavailable");
        }

        Path output = Path.of("out", "classes");
        Files.createDirectories(output);

        DiagnosticCollector<JavaFileObject> collector =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
                compiler.getStandardFileManager(
                        collector, Locale.ROOT, StandardCharsets.UTF_8)) {

            Iterable<? extends JavaFileObject> sourceFiles =
                    manager.getJavaFileObjectsFromPaths(
                            List.of(Path.of("src/sample/UncheckedDemo.java")));

            List<String> options = List.of(
                    "--release", "17",
                    "-Xlint:unchecked",
                    "-proc:none",
                    "-d", output.toString()
            );

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, manager, collector, options, null, sourceFiles);

            boolean compiled = Boolean.TRUE.equals(task.call());

            long errors = collector.getDiagnostics().stream()
                    .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
                    .count();

            long warnings = collector.getDiagnostics().stream()
                    .filter(d -> d.getKind() == Diagnostic.Kind.WARNING
                            || d.getKind() == Diagnostic.Kind.MANDATORY_WARNING)
                    .count();

            System.out.println("compiled=" + compiled);
            System.out.println("errors=" + errors);
            System.out.println("hasWarnings=" + (warnings > 0));
        }
    }
}
~~~

Giải thích:

- `getJavaFileObjectsFromPaths` tạo source units từ file thật; không cần `SimpleJavaFileObject` như ví dụ trong bộ nhớ.
- `Files.createDirectories` bảo đảm output directory tồn tại.
- `-Xlint:unchecked` yêu cầu compiler phát cảnh báo chi tiết.
- `-proc:none` tắt annotation processing ngoài ý muốn trong demo.
- Driver phân loại warning dựa vào enum, không parse chữ `warning` trong message.
- Đường dẫn source là **relative path**; chạy từ project root nơi có `src/sample/UncheckedDemo.java`.

### 6.3 Build và chạy

Từ project root:

**Linux/macOS:**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out FileDiagnosticDemo.java
java -cp out FileDiagnosticDemo
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out FileDiagnosticDemo.java
java -cp out FileDiagnosticDemo
~~~

Với javac JDK 17+ phù hợp, stdout:

~~~text
compiled=true
errors=0
hasWarnings=true
~~~

Đây là điều quan trọng: **một warning không đồng nghĩa compilation thất bại**.

Chạy source ứng dụng đã được driver biên dịch:

~~~bash
java -cp out/classes sample.UncheckedDemo
~~~

Stdout:

~~~text
0
~~~

Vì `values` là danh sách rỗng, kích thước là 0. Trong ứng dụng thật, warning generic nên được sửa bằng cách khai báo kiểu nhất quán, không chỉ bỏ qua.

### 6.4 Khi bật -Werror

Nếu thêm `"-Werror"` vào `options` cùng `-Xlint:unchecked`, compiler có thể coi warning là lý do làm task thất bại. Tùy trình biên dịch, collector có thể nhận warning gốc **và** diagnostic tổng kết lỗi do chính sách warning-as-error.

Không nên viết logic “nếu `warnings > 0` thì tự đổi tất cả warning thành ERROR”. Hãy giữ:

- `compiled` do task trả về;
- `errorCount`;
- `warningCount`;
- compiler options đã dùng.

Nhờ vậy dashboard có thể trình bày chính xác: “Có cảnh báo; build thất bại vì policy `-Werror`” thay vì mô tả sai một unchecked warning thành lỗi kiểu của source.

## 7. Message và diagnostic code có ổn định không?

### 7.1 getMessage(Locale)

~~~java
String message = diagnostic.getMessage(Locale.ROOT);
~~~

Đây là snippet trong method có biến `diagnostic`. API nhận `Locale` để compiler có thể chọn ngôn ngữ hiển thị nếu có. Nhưng không bảo đảm mọi Java compiler/JDK có bản dịch tiếng Việt hay cùng wording giữa các release.

Ví dụ `Locale.forLanguageTag("vi-VN")` có thể được truyền, nhưng nếu compiler không có bản dịch tương ứng thì thông điệp có thể vẫn xuất hiện bằng ngôn ngữ khác. `Locale.ROOT` thích hợp cho một số báo cáo trung tính, không phải hợp đồng rằng mọi thông điệp là cùng một chuỗi tiếng Anh.

**Không so sánh chính xác thông báo tự nhiên để quyết định loại lỗi.** Hãy dựa vào `Kind` và trường cấu trúc; text chỉ dùng để hỗ trợ con người đọc.

### 7.2 getCode()

~~~java
String code = diagnostic.getCode();
~~~

Mã diagnostic là **implementation-dependent**, có thể `null`. Trong javac có những mã nội bộ bắt đầu bằng các tiền tố như `compiler.err` hoặc `compiler.warn`, nhưng ứng dụng không được giả định đây là standard enum ổn định giữa mọi compiler, vendor và release.

Có thể dùng mã để thống kê khi dự án pin compiler cụ thể, nhưng cần có fallback cho `null` hoặc mã chưa biết.

### 7.3 Code khác với severity

`getKind() == ERROR` nói về **mức độ**. `getCode()` (nếu có) nói về **chủng loại lỗi theo compiler**. Hai dữ liệu đều hữu ích nhưng không thay thế nhau.

Một record ứng dụng có thể được thiết kế:

~~~text
severity       ERROR / WARNING / INFO
sourceUri      URI | null
line           1-based | null
column         1-based | null
position       0-based | null
compilerCode   string | null
message        localized string
buildId        identifier of compilation task
~~~

Đây là **schema khái niệm**, không phải định nghĩa chuẩn được Java Compiler API bắt buộc. Nếu xuất JSON hoặc LSP, phải quy định rõ kiểu offset/encoding, giá trị null và các quy tắc bảo mật dữ liệu.

## 8. Tự viết DiagnosticListener để xử lý tức thời

`DiagnosticCollector` thích hợp để đọc danh sách sau khi compile. Nếu cần phản hồi ngay cho người dùng, có thể tạo listener callback:

~~~java
DiagnosticListener<JavaFileObject> listener = d -> {
    String source = d.getSource() == null
            ? "(no source)"
            : d.getSource().getName();
    System.out.println(d.getKind() + " | " + source
            + " | " + d.getLineNumber());
};
~~~

Đây là snippet cần import `DiagnosticListener` và `JavaFileObject`. Truyền listener này vào tham số tương ứng của `compiler.getTask(...)`.

Muốn vừa thu danh sách vừa stream:

~~~java
DiagnosticCollector<JavaFileObject> collector =
        new DiagnosticCollector<>();

DiagnosticListener<JavaFileObject> listener = d -> {
    collector.report(d);
    System.out.println(d.getKind());
};
~~~

Trong đoạn trên, **wrapper listener** được truyền vào task; không có hai tham số listener độc lập trong `getTask`. Hãy tránh dùng collector chung cho nhiều compilation task không có chính sách phân tách, nhất là nếu chạy song song.

Callback không nên ném lỗi bất ngờ trong một dịch vụ; một exception trong listener có thể ảnh hưởng invocation compiler. Trong ứng dụng thật, cân nhắc buffering, thread safety, backpressure và phương án báo cáo lỗi của chính listener.

| Cơ chế | Thích hợp khi | Lưu ý |
| --- | --- | --- |
| `DiagnosticCollector` | Lọc, đếm và xuất báo cáo cuối | Mỗi task nên có collector riêng |
| Custom listener | Cập nhật UI/log khi từng thông báo xuất hiện | Tự quản lý callback, lưu trữ và lỗi |
| Wrapper listener + collector | Cần stream và bản tổng kết | Chỉ truyền wrapper vào task |

## 9. Diagnostic không thay thế cơ chế xử lý exception

Compiler diagnostics báo vấn đề **mà compiler phát hiện trong source/task**. Một số lỗi thực thi công cụ hoặc môi trường cần bắt theo đường khác.

| Tình huống | Cách xử lý |
| --- | --- |
| Source sai kiểu | Thu `Diagnostic.Kind.ERROR` |
| Unchecked warning | Thu warning khi bật flag liên quan |
| ToolProvider không có compiler | Kiểm tra `compiler == null` |
| Tùy chọn task không hợp lệ | Xử lý exception theo contract API; không chắc có diagnostic |
| Không đọc được file nguồn | Kiểm tra file manager/IOException và diagnostic liên quan |
| Annotation processor gặp lỗi hệ thống | Xử lý failure/exception ngoài diagnostic thông thường |
| Code đã compile nhưng ném `NullPointerException` khi chạy | Dùng runtime debugger/log/exception handling, **không** dùng compiler collector |

Ví dụ xử lý task:

~~~java
boolean compiled;
try {
    compiled = Boolean.TRUE.equals(task.call());
} catch (RuntimeException ex) {
    // Đây có thể là lỗi invocation/tooling ngoài stream diagnostic.
    throw ex;
}
~~~

Đây là snippet, giả định biến `task` đã được tạo. Trong hệ thống thật, xử lý thêm tài nguyên file manager, trạng thái build và cách log lỗi với dữ liệu nhạy cảm được lược bỏ.

`getDiagnostics().isEmpty()` cũng không chứng minh chương trình runtime hoạt động đúng. Lỗi mạng, file, SQL, NPE hoặc linkage runtime là các nhóm độc lập.

## 10. Lựa chọn vị trí chính xác khi đưa vào editor

Một công cụ IDE/chấm bài nên thực hiện:

1. Nhận source và giữ **phiên bản nội dung** được đưa vào compile.
2. Tạo `JavaFileObject` với URI ổn định hoặc file source thực tế.
3. Khi có diagnostic, liên hệ `getSource()` với tài liệu tương ứng.
4. Nếu `getPosition() == NOPOS`, hiển thị cấp build/file và không giả tọa độ.
5. Nếu có position, xác minh source content chưa thay đổi.
6. Chuyển offset, line, column sang tọa độ editor theo encoding đã thỏa thuận.
7. Tô rõ `ERROR`, `WARNING`, `NOTE`; không bỏ các kind ít gặp.
8. Ghi diagnostic code/message dưới dạng chi tiết bổ sung.
9. Giữ compiler version và flags để tái hiện.
10. Không buộc đầu ra diagnostic của mọi compiler phải giống hệt `javac` của một phiên bản.

Ví dụ nếu compiler nêu dòng 4 ở URI `string:///sample/Broken.java`, editor cần mở **chính văn bản nguồn tương ứng với URI/phiên biên dịch đó**, không tự động tìm một file `Broken.java` khác trên ổ đĩa.

### Vì sao không nên tô dòng lỗi theo substring message?

Một thông điệp như “cannot find symbol” có thể chứa tên identifier, type, context của generic và chi tiết API. Chúng thay đổi theo phiên bản compiler. `Diagnostic` đã cung cấp vị trí dạng số; hãy ưu tiên dữ liệu có cấu trúc. Nếu không có vị trí, hiển thị thông báo mà không bịa line.

### Lỗi từ generated source

Annotation processor có thể sinh source ở bước compile. Diagnostic liên quan generated source có thể trỏ tới file `.java` do processor tạo, dù người dùng không trực tiếp viết file đó. Để điều hướng từ generated source về source gốc, cần metadata/mapping của pipeline; collector **không tự nhận biết** quy tắc tạo source của mọi processor.

## 11. So sánh Compiler API với javac CLI

Tạo file cố tình sai kiểu `Broken.java`:

~~~java
public class Broken {
    public static void main(String[] args) {
        int number = "wrong";
    }
}
~~~

Biên dịch bằng lệnh:

~~~bash
javac --release 17 -encoding UTF-8 Broken.java
~~~

CLI có thể hiển thị file, số dòng, source line và caret trên stderr. Compiler API thu cùng loại sai kiểu thông qua `Diagnostic.Kind.ERROR`, cho phép ứng dụng tự định dạng.

Có thể yêu cầu chẩn đoán CLI chi tiết hơn:

~~~bash
javac -Xdiags:verbose --release 17 -encoding UTF-8 Broken.java
~~~

Đây là lệnh kiểm tra riêng; không cần giả định wording của log luôn giống nhau. `-Xdiags:verbose` có thể bổ sung ngữ cảnh, còn `DiagnosticCollector` chủ yếu thay đổi **cách bạn nhận thông báo**.

Nếu dùng `-Xmaxerrs` hoặc `-Xmaxwarns` để giới hạn số diagnostic, số phần tử thu được có thể không đại diện cho toàn bộ lỗi tiềm ẩn. Compiler cũng có thể dừng phân tích một phần source sau lỗi cú pháp/kiểu nghiêm trọng.

**Không lấy số lượng diagnostic làm định nghĩa tuyệt đối của số lỗi trong một project** khi các flags/giới hạn compiler khác nhau.

### 11.1 Cẩn thận với stderr và tool output

Diagnostic listener không đồng nghĩa bắt mọi thứ một annotation processor in ra bằng `System.out.println` hoặc `System.err.println`. File manager/compiler có thể có output bổ sung hoặc exception riêng. Nếu xây công cụ cần audit, ghi tách ba luồng:

- Structured compiler diagnostics;
- Compiler/process logs hoặc writer output;
- Exceptions và kết quả task.

## 12. Bảng xử lý lỗi phổ biến

| Biểu hiện | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `getSystemJavaCompiler() == null` | Runtime không cung cấp compiler | Dùng JDK phù hợp, kiểm tra module/runtime image |
| Task fail nhưng collector ít thông báo | Lỗi ngoài diagnostic stream hoặc compiler bị giới hạn | Xem exception, writer, file manager, processor |
| Compile true nhưng vẫn có warning | Warning không chặn compile mặc định | Đếm warning riêng; xem `-Werror` |
| Thêm `-Werror` làm compile false | Chính sách warning-as-error | Ghi cả result và các Kind compiler phát |
| Không có warning unchecked | Không bật `-Xlint:unchecked` hoặc source đã sửa | Xem compiler options |
| `getSource()` trả null | Diagnostic cấp task không gắn file | Hiển thị thông báo không có file |
| `getPosition() == NOPOS` | Không có vị trí phù hợp | Không tạo link đến dòng `-1` |
| Editor highlight sai | Nội dung source/encoding khác, offset mapping không khớp | Đồng bộ version, LF/CRLF, Unicode, tabs |
| `getCode()` null hoặc thay đổi | Provider không cam kết code portable | Có fallback |
| Test message fail sau nâng JDK | Wording/locale đổi | Assert kind/source/line/task status |
| Hai build trộn diagnostics | Dùng lại collector không quản lý vòng đời | Tạo collector cho từng task |
| Error ở generated source | Annotation processor tạo source mới | Kiểm tra `getSource()`, nguồn sinh |
| Driver không tìm thấy source file | Working directory không đúng | Chạy tại project root, kiểm tra `Path` |
| Lỗi runtime bị gọi nhầm compiler error | Không phân biệt giai đoạn | Tách exception lúc chạy khỏi compile diagnostics |

## 13. Bài tập có đáp án

### Bài 1 — Lỗi kiểu ở dòng nào?

Với `DiagnosticCollectorDemo`, vì sao stdout có `ERROR at line 4` và `compiled=false`?

**Đáp án:** Source trong `String.join` đặt `int number = "wrong";` ở dòng thứ tư. Compiler phát lỗi kiểu, task thất bại, collector lưu diagnostic có line number 4.

### Bài 2 — Sửa source

Thay thành `int number = 7;`, compile lại. Điều gì thay đổi?

**Đáp án:** Task có thể thành công, `errors=0` và không còn dòng in chi tiết ERROR của loop.

### Bài 3 — Có warning nhưng build vẫn đạt

Với `FileDiagnosticDemo`, tại sao có `hasWarnings=true` trong khi `compiled=true`?

**Đáp án:** `-Xlint:unchecked` phát cảnh báo vì raw generic, còn không có chính sách `-Werror` nên compile có thể thành công.

### Bài 4 — Bắt đủ mức warning

Tại sao không chỉ đếm `Diagnostic.Kind.WARNING`?

**Đáp án:** API còn có `MANDATORY_WARNING`. Khi thống kê nhóm warning, thường cần cộng cả hai.

### Bài 5 — Diagnostic không có vị trí

Nếu `getSource()==null` và `getPosition()==NOPOS`, giao diện nên đánh dấu file/dòng nào?

**Đáp án:** Không tự đánh dấu dòng nào. Hiển thị thông điệp ở cấp project/task.

### Bài 6 — Ổn định của message

Một unit test so chuỗi thông báo tiếng Anh của javac với literal cố định. Vì sao dễ gãy?

**Đáp án:** Wording, locale và diagnostic code phụ thuộc implementation/version. Nên kiểm tra Kind, vị trí thích hợp và task result.

### Bài 7 — Runtime error

Sau khi compile thành công, ứng dụng ném `NullPointerException`. Collector có tự thu ngoại lệ ấy không?

**Đáp án:** Không. Nó thu chẩn đoán trong compiler task, không bắt lỗi của JVM thực thi ứng dụng.

### Bài 8 — Offset và UTF-8

Editor đang đọc file UTF-8, còn compiler trả `getPosition()=120`. Có nên tô ngay byte thứ 120 không?

**Đáp án:** Không. Offset API theo vị trí ký tự, không tương đương byte offset UTF-8. Cần ánh xạ đúng source và encoding.

### Bài 9 — Bảo vệ null

Tại sao `d.getSource().getName()` có thể gây NPE?

**Đáp án:** API cho phép `getSource()==null` với diagnostic không gắn file. Kiểm tra nguồn trước khi gọi `getName()`.

### Bài 10 — Task với -Werror

Nếu task có warning và `-Werror`, ứng dụng nên báo cáo những gì?

**Đáp án:** Giữ kết quả `task.call()` thực, lỗi/cảnh báo theo Kind mà compiler phát, đồng thời ghi cờ `-Werror` trong compiler options; không tự thay severity bằng suy đoán.

## 14. Checklist

- [ ] Tôi hiểu `DiagnosticCollector` là một `DiagnosticListener` có lưu danh sách.
- [ ] Tôi truyền collector vào `getTask` và gọi `call()` đúng một lần.
- [ ] Tôi kiểm tra compiler `null`.
- [ ] Tôi tạo được ví dụ source sai kiểu trong bộ nhớ.
- [ ] Tôi thu được `ERROR` và biết line number tương ứng.
- [ ] Tôi biên dịch được source có unchecked warning với `-Xlint:unchecked`.
- [ ] Tôi phân biệt `WARNING` và `MANDATORY_WARNING`.
- [ ] Tôi xử lý `getSource()==null` và `Diagnostic.NOPOS`.
- [ ] Tôi hiểu line/column bắt đầu từ 1, offset từ 0.
- [ ] Tôi không dùng text message hay diagnostic code làm hợp đồng portable.
- [ ] Tôi tách compiler task result, diagnostics và exceptions.
- [ ] Tôi giữ đúng source version khi hiển thị vị trí lỗi.
- [ ] Tôi dùng file manager, path/encoding và compiler options hợp lệ.
- [ ] Tôi không nhầm compile diagnostic với runtime exception.

## Tài liệu API tham khảo

- [Diagnostic — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/Diagnostic.html)
- [DiagnosticCollector — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/DiagnosticCollector.html)
- [DiagnosticListener — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/DiagnosticListener.html)
- [JavaCompiler — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html)
- [ToolProvider — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html)
- [javac options — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)

## Ghi nhớ

**`DiagnosticCollector` thu diagnostic có cấu trúc từ compiler task**. `Diagnostic.Kind` cho biết mức độ, `getSource()` xác định source, line/column và character positions chỉ ra nơi xảy ra vấn đề khi có. Hãy xử lý `null` và `NOPOS`, không dựa vào message hay diagnostic code để xác định mức lỗi một cách portable. Kết quả chẩn đoán đáng tin cậy luôn đi kèm **task success/failure, compiler options, source version và exception riêng của công cụ**.

# Chẩn đoán vị trí và lỗi bằng Compiler Tree API được hỗ trợ (Java 14+)

> **Mục tiêu:** dùng các giao diện Java công khai, vẫn được hỗ trợ trong JDK hiện đại để xác định **lỗi biên dịch xuất hiện tại dòng/cột nào**, lấy **khoảng offset của node trong cây cú pháp Java (AST)** và gắn thông báo của công cụ phân tích mã vào nguồn. Trọng tâm là `javax.tools.JavaCompiler`, `DiagnosticCollector`, `Diagnostic`, `com.sun.source.util.JavacTask`, `Trees`, `SourcePositions` và `LineMap`. Ví dụ là Java 17+ hoàn chỉnh, biên dịch/chạy trên OpenJDK 24. Tuy bài nằm trong chủ đề Java 14, các giao diện nền tảng đã xuất hiện trước đó và tiếp tục áp dụng; **không** sử dụng các lớp implementation nội bộ `com.sun.tools.javac.*`, công cụ không còn được hỗ trợ hay cơ chế reflection để vượt JPMS.

## 1. Vì sao cần truy cập lỗi và vị trí từ compiler?

Một IDE, bộ kiểm tra quy tắc, hệ thống chấm bài hay build tool thường cần hai loại kết quả riêng:

1. **Chẩn đoán của compiler:** mã nguồn không hợp lệ tại đâu, severity là lỗi hay cảnh báo, và cần hiển thị lời nhắn nào? Ví dụ biểu thức `MISSING` tham chiếu tới tên chưa khai báo.
2. **Vị trí node cú pháp:** biến, phương thức, class, biểu thức hoặc lệnh nằm ở khoảng source nào để highlight, chọn vùng, rà soát code style hay gắn cảnh báo riêng?

Java cung cấp API cho cả hai công việc:

| Tầng | Public API | Mục đích |
|---|---|---|
| Java Compiler API / JSR 199 | `javax.tools.JavaCompiler`, `ToolProvider` | Lấy compiler và tạo lượt biên dịch/phân tích |
| Thu thập lỗi và cảnh báo | `DiagnosticListener`, `DiagnosticCollector`, `Diagnostic` | Nhận và xử lý structured diagnostics |
| Nguồn và file manager | `JavaFileObject`, `SimpleJavaFileObject`, `StandardJavaFileManager` | Đọc source từ file hoặc từ bộ nhớ |
| Compiler Tree API | `JavacTask`, `CompilationUnitTree`, `TreePathScanner` | Parse source thành AST và duyệt cấu trúc |
| Liên hệ node với source | `Trees`, `SourcePositions`, `LineMap` | Xác định offset, dòng/cột, vị trí bắt đầu/kết thúc |

`javax.tools.*` nằm trong **module `java.compiler`**. Các giao diện `com.sun.source.*` nằm trong **module `jdk.compiler`** và được tài liệu module chính thức mô tả là Compiler Tree API. **Không nhầm `com.sun.source.*` với `com.sun.tools.javac.*`** — package thứ hai gồm nhiều chi tiết triển khai không phải API ứng dụng ổn định.

**Phân biệt với lỗi runtime:** `Diagnostic.Kind.ERROR` không phải `Throwable` hoặc Java exception được ném khi chương trình đang chạy; nó là báo cáo **compile-time**. Khi một ứng dụng đã build ném `NullPointerException`, stack trace có cơ chế line number khác, không trực tiếp trả `CompilationUnitTree` hay `Diagnostic.getEndPosition()`.

## 2. Lấy compiler chính thức: `ToolProvider.getSystemJavaCompiler()`

```java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException("No system Java compiler");
}
```

Đây là **snippet** nằm trong một phương thức. `ToolProvider.getSystemJavaCompiler()` trả về compiler hệ thống nếu runtime có cung cấp; có thể trả `null` khi chạy trong Java runtime image tối giản không chứa compiler. Đừng coi việc Java ứng dụng đang chạy được là bằng chứng ở runtime đó có javac.

Cần sử dụng **JDK 17+ có compiler** để chạy ví dụ. Nếu ứng dụng đóng gói runtime bằng `jlink`, đảm bảo module `jdk.compiler` và dependencies cần thiết có mặt khi phân tích nguồn động.

Với một Java module có `module-info.java`, cấu hình mẫu:

```java
module example.analyzer {
    requires java.compiler;
    requires jdk.compiler;
}
```

Đây là mẫu descriptor minh họa để dùng hai API module trong một ứng dụng modular, **không phải** file cần thêm khi chạy demo classpath mục 7. Với chương trình chạy trên classpath/JDK hoàn chỉnh, thông thường không cần `--add-exports` hay `--add-opens` vì các gói Compiler Tree API đã được công bố.

## 3. `DiagnosticCollector`: lấy thông báo thành dữ liệu có cấu trúc

Thay vì parse văn bản lỗi được in ra stderr bởi `javac`, ứng dụng có thể gửi `DiagnosticListener` khi tạo task. Implementation tiêu chuẩn tiện dụng là `DiagnosticCollector<JavaFileObject>`:

```java
DiagnosticCollector<JavaFileObject> collector =
    new DiagnosticCollector<>();

try (StandardJavaFileManager files =
        compiler.getStandardFileManager(
            collector, Locale.ROOT, StandardCharsets.UTF_8)) {
    JavaCompiler.CompilationTask task =
        compiler.getTask(null, files, collector,
            List.of("-proc:none"), null, sources);
    boolean success = task.call();
    // collector.getDiagnostics(): các lỗi/cảnh báo/note compiler đã báo.
}
```

Đây là **snippet**: `compiler` và `Iterable<? extends JavaFileObject> sources` phải được khai báo trong ngữ cảnh gọi; với code độc lập xem mục 7. `StandardJavaFileManager` cần được đóng; ví dụ dùng `try-with-resources`.

`DiagnosticCollector` implements `DiagnosticListener`, nhận thông báo bằng `report(...)` và trả danh sách qua `getDiagnostics()`. Mỗi thông báo có `Diagnostic.Kind` và tùy trường hợp có source/offset/line/column.

**Chọn task đúng mục tiêu:**

- `CompilationTask.call()` thích hợp khi muốn compiler thực hiện một lượt biên dịch và trả Boolean thành công/thất bại.
- `JavacTask.parse()` thích hợp khi cần AST để phân tích cấu trúc.
- `JavacTask.analyze()` hoàn tất semantic analysis, giúp bắt các lỗi tên không tồn tại, type mismatch và resolution.
- `JavacTask.generate()` tạo output class files khi thực sự cần.
- **Không chạy `call()` rồi tiếp tục `parse()` trên cùng task** như một workflow được bảo đảm. Chọn nhánh từ đầu; tạo task mới nếu cần một lượt độc lập.

Compiler có thể viết một số thông báo không thể biểu diễn đầy đủ bằng `Diagnostic` ra writer/output, dù đã cung cấp listener. Vì vậy một collector không nhất thiết bao trùm mọi text mà compiler có thể xuất ra trong mọi điều kiện.

### `Diagnostic.Kind` là severity có kiểu

| Kind | Ý nghĩa thường dùng |
|---|---|
| `ERROR` | Lỗi ngăn compilation hợp lệ |
| `WARNING` | Cảnh báo compiler |
| `MANDATORY_WARNING` | Cảnh báo bắt buộc theo API/compiler |
| `NOTE` | Thông tin giải thích hoặc chú thích |
| `OTHER` | Các thông báo khác |

Một collector có thể chứa cả warning, note và error. Không được tính **số lượng diagnostics = số lỗi**. Khi chỉ cần lỗi:

```java
long errorCount = collector.getDiagnostics().stream()
    .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
    .count();
```

Đây là một đoạn Java nằm trong phương thức với `collector` có sẵn. Ngay cả khi `errorCount == 0` sau `parse()`, **chưa chứng minh** toàn bộ mã hợp lệ về mặt kiểu/ký hiệu; cần `analyze()` hoặc full compilation.

## 4. API vị trí của `Diagnostic`: 0-based và 1-based

`javax.tools.Diagnostic<S>` cung cấp:

| Phương thức | Thông tin |
|---|---|
| `getKind()` | `ERROR`, `WARNING`, `NOTE`... |
| `getSource()` | `S` (thường `JavaFileObject`) hoặc `null` nếu thông báo không gắn với file |
| `getPosition()` | Offset **ký tự** được đánh số từ **0** |
| `getStartPosition()` | Offset đầu phần source gắn với vấn đề |
| `getEndPosition()` | Offset cuối phần source gắn với vấn đề |
| `getLineNumber()` | **Dòng bắt đầu từ 1** |
| `getColumnNumber()` | **Cột bắt đầu từ 1** |
| `getCode()` | Mã chẩn đoán **implementation-dependent**, có thể `null` |
| `getMessage(Locale locale)` | Văn bản thông báo, có thể được dịch/khác phiên bản |

**Rất quan trọng:**

- Offset `getPosition()` là **0-based**, không phải số byte UTF-8 của source.
- `getLineNumber()` và `getColumnNumber()` là **1-based**.
- Nếu vị trí không khả dụng, Java dùng **`Diagnostic.NOPOS`**, không phải `0`.
- `getSource()` có thể là `null`. Không giả định lỗi nào cũng có file/line/column.
- Khi các tọa độ tồn tại, Javadoc quy định `startPosition <= position <= endPosition`.

Ví dụ nguồn:

```java
package demo;
class Broken {
    void run() {
        int n = MISSING;
    }
}
```

Trên JDK 24 đã thử, lỗi không tìm thấy `MISSING` có `Kind.ERROR`, `line=4`, `column=17`. Cột 17 tính từ đầu dòng chứa tám dấu cách trước `int`. Đây là **tình huống cụ thể**, không phải cam kết mọi compiler luôn chọn cùng một token làm caret đối với mọi loại lỗi.

**Đừng biến `NOPOS` thành âm 1 trong giao diện hiển thị “dòng -1” hoặc cắt chuỗi bằng chỉ số âm.** Một thông báo về option compiler, nguồn không đọc được, hoặc vấn đề cấp task có thể không có tọa độ. Hãy hiển thị dưới phần thông báo chung hoặc gắn với file nếu chỉ có source mà chưa có vị trí.

### Mã lỗi và message không phải hợp đồng portable

`getCode()` có thể giúp phân loại chi tiết với **một compiler/version** nhất định, nhưng mã này **không được tiêu chuẩn hóa xuyên compiler** và có thể null. `getMessage(Locale)` được xây cho người đọc, có thể thay đổi khi ngôn ngữ, phiên bản, cách xử lý lỗi hay compiler thay đổi.

Không viết kiểu:

```java
if (message.contains("cannot find symbol")) {
    // Bắt lỗi tên biến bằng cách parse câu tiếng Anh.
}
```

Đoạn trên minh họa **thói quen cần tránh**: lời văn không phải enum lỗi ổn định, và ở Locale khác có thể không chứa câu ấy. Nếu công cụ cần logic chính xác theo symbol/type, nên dùng Tree API, `Trees.getElement(TreePath)` hoặc compiler analysis thay vì parse tiếng Anh.

## 5. Compiler Tree API: AST và vị trí node

`com.sun.source.tree.*` đại diện các node trong Java source: `CompilationUnitTree`, `ClassTree`, `MethodTree`, `VariableTree`, `MethodInvocationTree`, `BlockTree`... Cấu trúc này hiểu nested declarations, comments, generic signatures, switch expressions, text blocks và các cú pháp Java hợp lệ tốt hơn một biểu thức chính quy đơn giản.

Sau khi tạo `JavacTask`:

```java
CompilationUnitTree unit = javac.parse().iterator().next();
Trees trees = Trees.instance(javac);
SourcePositions positions = trees.getSourcePositions();

new TreePathScanner<Void, Void>() {
    @Override
    public Void visitVariable(VariableTree node, Void ignored) {
        long start = positions.getStartPosition(unit, node);
        if (start != Diagnostic.NOPOS) {
            LineMap lm = unit.getLineMap();
            if (lm != null) {
                System.out.println(lm.getLineNumber(start) + ":" +
                                   lm.getColumnNumber(start));
            }
        }
        return super.visitVariable(node, ignored);
    }
}.scan(unit, null);
```

Đây là snippet có các import tương ứng và biến `JavacTask javac` đã được khởi tạo. Với nhiều source, phải xử lý **từng** `CompilationUnitTree` và ghép vị trí của node với **đúng compilation unit**; `SourcePositions` không hứa cho offset hữu ích nếu hỏi vị trí của node không thuộc unit được truyền.

### `SourcePositions` trả khoảng nguồn, không phải chuỗi text

`SourcePositions` có:

```java
long getStartPosition(CompilationUnitTree unit, Tree node)
long getEndPosition(CompilationUnitTree unit, Tree node)
```

Hai giá trị là offset ký tự kể từ đầu compilation unit. Theo Javadoc, giá trị có thể là `Diagnostic.NOPOS` khi không biết vị trí hoặc không tìm được node.

Ví dụ `VariableTree` mang khai báo `int total = 7;`, trên JDK được thử, khoảng `[start,end)` đã cho phép lấy đúng source:

```java
String statement = good.substring((int) start, (int) end);
// "int total = 7;" trong ví dụ đã thử.
```

**Điều kiện an toàn trước khi cắt:**

```java
if (start != Diagnostic.NOPOS &&
    end != Diagnostic.NOPOS &&
    start >= 0 && start <= end && end <= text.length()) {
    String fragment = text.substring((int) start, (int) end);
}
```

Đây là snippet trong phương thức có `String text` và `long start/end`. Không gọi `substring` cho node được tạo tổng hợp, AST có lỗi cú pháp hoặc mapping không hợp lệ mà chưa kiểm tra. Với mã bị lỗi cú pháp, compiler vẫn có thể tạo `ERRONEOUS` nodes để tiếp tục phân tích, nhưng **không phải mọi node đều có vị trí chính xác**.

### `LineMap` đổi offset thành dòng/cột

`CompilationUnitTree.getLineMap()` có thể cung cấp `LineMap` (hoặc `null` nếu không có). Các phương thức:

- `getLineNumber(long pos)`: dòng của offset, từ 1.
- `getColumnNumber(long pos)`: cột của offset, từ 1; tính đến việc **tab được mở rộng**.
- `getPosition(long line,long column)`: biến line/column thành offset.
- `getStartPosition(long line)`: offset đầu dòng.

Không dùng công thức “lấy index trừ offset dòng rồi cộng 1” cho mọi trường hợp, vì tab, CRLF, Unicode escapes và cách IDE hiển thị có thể khiến cột khác với số byte hoặc số Unicode graphemes trên màn hình.

**Vị trí Diagnostic và vị trí AST không hoàn toàn giống mục đích:** diagnostic đánh dấu chỗ compiler muốn báo vấn đề; `SourcePositions` mô tả phạm vi của node cú pháp. Một thông báo lỗi có thể trỏ tới identifier, trong khi node `VariableTree` bao phủ cả khai báo. Không dùng offset của node toàn bộ để thay thế caret location của diagnostic nếu muốn người học thấy đúng token gây lỗi.

## 6. Phân biệt lỗi cú pháp và lỗi ngữ nghĩa

Hai giai đoạn thường gặp khi dùng `JavacTask`:

| Giai đoạn | Chức năng | Ví dụ |
|---|---|---|
| `parse()` | Phân tích cấu trúc ngữ pháp và tạo tree | Thiếu dấu `;`, ngoặc, keyword không hợp lệ |
| `analyze()` | Resolve symbol, kiểm tra kiểu, thực hiện phân tích ngữ nghĩa | `cannot find symbol`, ép kiểu không hợp lệ, method không tồn tại |
| `generate()` | Tạo output khi compilation phù hợp | Sinh class files; không cần thiết cho trình chỉ muốn inspect AST |

Nguồn sai cú pháp:

```java
class BrokenSyntax {
    void test() {
        int number = 10
    }
}
```

có thể được phát hiện ngay khi `parse()`. Compiler vẫn có thể tạo AST một phần để phục vụ tooling, nhưng không nên coi mọi vị trí từ AST sai là hợp lệ hoặc duy nhất.

Nguồn đúng cú pháp nhưng sai ngữ nghĩa:

```java
class BrokenSemantic {
    void test() {
        int n = MISSING;
    }
}
```

đòi hỏi `analyze()` để phát hiện tên `MISSING` chưa được khai báo trong ngữ cảnh đó. Vì vậy nếu bạn viết bài kiểm tra code “parse chạy xong không báo lỗi = compile thành công”, **kết luận ấy sai**.

Một lỗi syntax có thể khiến compiler báo nhiều lỗi thứ cấp. Số và thứ tự diagnostics có thể đổi khi compiler chọn chiến lược recovery khác; UI/CI nên hiển thị theo severity, source, vị trí, không assert đúng số lượng lỗi trên **mọi** Java version.

## 7. Chương trình độc lập Java 17+: lấy vị trí AST và error của javac

Chương trình bên dưới tạo **hai tệp source ảo hoàn toàn trong bộ nhớ** thông qua `SimpleJavaFileObject`. Nó không tạo file `demo/Example.java` hoặc `demo/Broken.java` trong repository:

- `Example` đúng cú pháp và kiểu; parse tree, duyệt `VariableTree` tên `total`, lấy vị trí start/end và trích đoạn. Sau `analyze()`, collector không có `ERROR`.
- `Broken` chứa identifier chưa khai báo `MISSING`; sau `parse()` rồi `analyze()`, collector báo lỗi ngữ nghĩa với tọa độ dòng/cột.
- `JavacTask` lấy từ system compiler JDK; `-proc:none` tắt annotation processing vì không cần chạy processors để kiểm tra.
- Hai task riêng tránh tái sử dụng compiler task đã hoàn tất và đóng file manager đúng vòng đời.

Tạo file **`CompilerLocationDemo.java`**:

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
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.LineMap;
import com.sun.source.tree.VariableTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.SourcePositions;
import com.sun.source.util.TreePathScanner;
import com.sun.source.util.Trees;

public class CompilerLocationDemo {
    private static final class Source extends SimpleJavaFileObject {
        private final String text;

        Source(String name, String text) {
            super(URI.create("string:///" +
                name.replace('.', '/') + Kind.SOURCE.extension),
                Kind.SOURCE);
            this.text = text;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return text;
        }
    }

    private static JavacTask task(
            JavaCompiler compiler,
            StandardJavaFileManager files,
            DiagnosticCollector<JavaFileObject> collector,
            String className, String text) {
        return (JavacTask) compiler.getTask(
            null, files, collector, List.of("-proc:none"), null,
            List.of(new Source(className, text)));
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            System.out.println("compiler=unavailable");
            return;
        }

        String good = "package demo;\n"
                    + "class Example {\n"
                    + "    void run() {\n"
                    + "        int total = 7;\n"
                    + "    }\n"
                    + "}\n";

        DiagnosticCollector<JavaFileObject> validDiagnostics =
            new DiagnosticCollector<>();
        try (StandardJavaFileManager files = compiler.getStandardFileManager(
                validDiagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
            JavacTask javac = task(
                compiler, files, validDiagnostics, "demo.Example", good);
            CompilationUnitTree unit = javac.parse().iterator().next();
            Trees trees = Trees.instance(javac);
            SourcePositions positions = trees.getSourcePositions();

            new TreePathScanner<Void, Void>() {
                @Override
                public Void visitVariable(VariableTree node, Void ignored) {
                    if (node.getName().contentEquals("total")) {
                        long start = positions.getStartPosition(unit, node);
                        long end = positions.getEndPosition(unit, node);
                        LineMap lines = unit.getLineMap();
                        System.out.println("tree.kind=" + node.getKind());
                        System.out.println("tree.line=" +
                            lines.getLineNumber(start));
                        System.out.println("tree.column=" +
                            lines.getColumnNumber(start));
                        System.out.println("tree.text=" +
                            good.substring((int) start, (int) end));
                    }
                    return super.visitVariable(node, ignored);
                }
            }.scan(unit, null);

            javac.analyze();
            long errors = validDiagnostics.getDiagnostics().stream()
                .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
                .count();
            System.out.println("valid.errorCount=" + errors);
        }

        String broken = "package demo;\n"
                      + "class Broken {\n"
                      + "    void run() {\n"
                      + "        int n = MISSING;\n"
                      + "    }\n"
                      + "}\n";

        DiagnosticCollector<JavaFileObject> errors =
            new DiagnosticCollector<>();
        try (StandardJavaFileManager files = compiler.getStandardFileManager(
                errors, Locale.ROOT, StandardCharsets.UTF_8)) {
            JavacTask javac = task(
                compiler, files, errors, "demo.Broken", broken);
            javac.parse();
            javac.analyze();
        }

        long count = errors.getDiagnostics().stream()
            .filter(d -> d.getKind() == Diagnostic.Kind.ERROR).count();
        System.out.println("broken.errorCount=" + count);
        for (Diagnostic<? extends JavaFileObject> d :
                errors.getDiagnostics()) {
            if (d.getKind() == Diagnostic.Kind.ERROR) {
                System.out.println("error.kind=" + d.getKind());
                System.out.println("error.line=" + d.getLineNumber());
                System.out.println("error.column=" + d.getColumnNumber());
                System.out.println("error.positionPresent=" +
                    (d.getPosition() != Diagnostic.NOPOS));
                System.out.println("error.sourcePresent=" +
                    (d.getSource() != null));
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 CompilerLocationDemo.java
java CompilerLocationDemo
```

**Stdout chính xác đã kiểm chứng với OpenJDK 24:**

```text
tree.kind=VARIABLE
tree.line=4
tree.column=9
tree.text=int total = 7;
valid.errorCount=0
broken.errorCount=1
error.kind=ERROR
error.line=4
error.column=17
error.positionPresent=true
error.sourcePresent=true
```

Giải thích:

1. `tree.kind=VARIABLE`: visitor tìm được đúng node khai báo biến thay vì chỉ tìm chuỗi `total` bằng `indexOf()`.
2. `tree.line=4`, `tree.column=9`: AST declaration bắt đầu tại dòng 4, cột 9.
3. `tree.text=int total = 7;`: đoạn nguồn trích bằng `SourcePositions` khớp với khai báo.
4. `valid.errorCount=0`: source `Example` qua cả parse và semantic analyze không sinh ERROR trong lần kiểm chứng.
5. `broken.errorCount=1`: source `Broken` có một lỗi compiler trong lần thử.
6. `error.kind=ERROR`, `error.line=4`, `error.column=17`: diagnostic định vị identifier `MISSING`.
7. `error.positionPresent=true` và `error.sourcePresent=true`: compiler cung cấp offset và source JavaFileObject; công cụ có thể dùng để highlight.

**Lưu ý tính xác định:** các dòng in của demo dùng source được khai báo nguyên văn với dấu `\n`, dấu cách cố định và một lỗi rất đơn giản. Chương trình đã chạy trên OpenJDK 24 như stdout trên. Khi đổi indentation, compiler/JDK hoặc thêm lỗi khác, số diagnostic và vị trí có thể thay đổi. Bài **không** cố so sánh nguyên văn `getMessage(Locale.ROOT)` hay `getCode()` do chúng không phải chuỗi ổn định xuyên triển khai.

**Vì sao demo được javac biên dịch dù có chuỗi `MISSING`?** Nó không chứa Java source hỏng ở cấp top-level program. `"MISSING"` thuộc nội dung `String broken` là source đầu vào của compiler **khi chương trình chạy**. Hai lớp `Example` và `Broken` được phân tích trong bộ nhớ, không chạy như ứng dụng.

## 8. `Trees.printMessage`: tạo thông báo từ luật phân tích riêng

Compiler error là một nhánh; công cụ lint cũng có thể tự phát hiện quy tắc của tổ chức và muốn thông báo chính xác tại node AST. API công khai `Trees.printMessage` có chữ ký:

```java
trees.printMessage(
    Diagnostic.Kind.WARNING,
    "Tên biến nên mô tả ý nghĩa rõ hơn",
    node,
    unit);
```

Đây là **snippet** nằm trong visitor có `Trees trees`, `Tree node` và `CompilationUnitTree unit` cùng task. Phương thức in một thông điệp thuộc kind được cung cấp **ở vị trí của node** trong compilation unit; tránh tự ghép filename/line/column bằng cách dò source text thủ công.

**Không nhầm tác dụng:** phát warning custom trong một lượt analysis **không** tự thêm luật compile vào mọi javac của máy. Để tích hợp vào annotation processor hoặc công cụ riêng, phải thiết kế lifecycle/compiler invocation và nơi nhận diagnostic.

Với phân tích sâu sau `analyze()`, có thể dùng:

- `Trees.getElement(TreePath)` để tìm symbol/element gắn với node.
- `Trees.getTypeMirror(TreePath)` để biết type của expression.
- `TreePathScanner.getCurrentPath()` để lấy context path trong visitor.

Những API này hữu ích nếu bạn muốn phân biệt hai method cùng tên ở hai class khác nhau hoặc xác minh kiểu của một expression. Nếu source đang lỗi, element/type có thể chưa resolve hoàn chỉnh, nên cần null/error-type checks. Nếu công việc chỉ cần vị trí syntax, không buộc phải chạy semantic analyze.

## 9. Chuẩn hóa tọa độ để hiển thị IDE, CI và code review

Một cấu trúc dữ liệu riêng cho công cụ có thể gồm:

```text
CompilerFinding
  severity       : ERROR | WARNING | ...
  sourceUri      : String?       (null nếu lỗi không có file)
  line           : Long?         (1-based hoặc unavailable)
  column         : Long?         (1-based hoặc unavailable)
  startOffset    : Long?         (0-based hoặc unavailable)
  pointOffset    : Long?         (0-based hoặc unavailable)
  endOffset      : Long?         (0-based hoặc unavailable)
  compilerCode   : String?       (không portable)
  displayMessage : String        (localizable)
  sourceRevision : String/hash   (nếu nội dung có thể thay đổi)
```

Đây là **schema minh họa**, không phải class được cung cấp sẵn trong JDK. Khi xây pipeline:

1. Lấy `d.getKind()` làm severity chính.
2. Chỉ dùng `d.getSource().toUri()` sau khi kiểm tra `getSource()!=null`.
3. Kiểm tra `d.getPosition()!=Diagnostic.NOPOS` trước khi chuyển offset thành selection.
4. Nếu có interval, kiểm tra `0<=start<=end<=source.length` trước khi gọi `substring`.
5. Dùng `getMessage(locale)` làm lời nhắn cho người đọc, **không** parse thành mã lỗi business-critical.
6. Gắn diagnostic với **phiên bản source** (hash/version) để biết nó còn tương ứng với nội dung editor hiện tại.
7. Nếu source thay đổi từ phiên bản A sang B, **xóa/recompute** findings cũ; đừng lấy offset cũ tô lên nguồn mới.

### Unicode, tab và sự khác biệt hiển thị

Một cột trong editor không nhất thiết là “số pixel/visual glyph”. Các yếu tố cần kiểm thử: tab stop, Java Unicode escape xử lý bởi compiler, CRLF so với LF, tiếng Việt có dấu, emoji và Unicode supplementary characters.

- `Diagnostic.getPosition()` được định nghĩa là **character offset**, không phải byte index của tệp UTF-8.
- `String.substring()` của Java dùng index UTF-16 code unit; với source từ `CharSequence` cần hiểu encoding và bảo đảm offset phù hợp trước khi cắt.
- `LineMap.getColumnNumber()` tính đến việc **mở rộng tab**.
- Một số editor API dùng UTF-16, số khác dùng code points hoặc display columns; cần adapter chuyển tọa độ và test trên chính source.

Đừng giả định `getPosition()+1 == getColumnNumber()` cho file nhiều dòng, chứa tab, newline hoặc ký tự đa byte. Đặc biệt **mã nguồn có Unicode** có thể cần mapping giữa byte offsets, Java chars và cột hiển thị.

## 10. Ngữ nghĩa khi có `NOPOS` và nhiều source files

**Không phải mọi thông báo có vị trí.** Ví dụ một compiler option không hợp lệ, lỗi I/O hay chẩn đoán toàn cục có thể không gắn với một token. Code an toàn:

```java
for (Diagnostic<? extends JavaFileObject> d :
        collector.getDiagnostics()) {
    String source = d.getSource() == null
        ? "<no source>"
        : d.getSource().toUri().toString();

    String where = d.getPosition() == Diagnostic.NOPOS
        ? "<unknown position>"
        : d.getLineNumber() + ":" + d.getColumnNumber();

    System.out.println(d.getKind() + " " + source + " " + where);
}
```

Đây là snippet có `DiagnosticCollector<JavaFileObject> collector` và import tương ứng. Phải escape/ẩn URL đường dẫn nếu dữ liệu dùng trong HTML hoặc log công khai.

Với nhiều `JavaFileObject`, nhận diện bằng `getSource()`/URI. Các `CompilationUnitTree` từ `parse()` cũng phải được gắn với `CompilationUnitTree.getSourceFile()`. Không dùng line map của file A để hiển thị offset thuộc source B.

**Không ép danh sách lỗi chỉ một phần tử** trong production: compiler có thể phát nhiều warning/error trên một source. Đừng dựa vào thứ tự chẩn đoán là thứ tự xuất hiện trong file trên mọi compiler/JDK; khi cần UI sort, sắp theo source, line, column và severity, giữ thông tin thực tế.

## 11. An toàn khi phân tích source bên ngoài

Compiler là công cụ phát triển nhưng chạy bên trong tiến trình ứng dụng có quyền và tài nguyên thực. Một dịch vụ nhận source code có thể gặp file lớn, dependency sâu, classpath không kiểm soát và annotation processors thực thi mã. Các biện pháp hiện hành:

- Dùng `-proc:none` khi không cần annotation processing; demo đã làm vậy. Điều đó **không tự biến compiler thành sandbox**.
- Đặt giới hạn thời gian, CPU, memory và kích thước source/số file. Với input không tin cậy, xem xét **process/container isolation**.
- Kiểm soát classpath/module path, file manager và output directory; tránh để code nhận từ ngoài đọc secrets hoặc thao tác lên workspace mà service có quyền.
- Không đưa source code nhạy cảm hoặc local absolute paths vào telemetry/log công khai; lọc thông điệp và URI.
- Không nhúng các option `--add-opens`/`--add-exports` để truy cập implementation internals chỉ vì một API công khai đã có sẵn.
- Đóng `StandardJavaFileManager` bằng `try-with-resources`, và tạo compilation task riêng cho mỗi lượt phân tích độc lập.
- Nếu nhiều worker/compiler tasks chạy đồng thời, không chia sẻ mutable collector hoặc source buffer theo cách gây race condition. Thiết kế ownership/task lifecycle cụ thể.
- Ghi rõ JDK version, compiler options, `--release` và module/classpath trong báo cáo; các yếu tố này có thể thay đổi loại lỗi compiler phát hiện.

Khi cần chạy full compilation, dùng `CompilationTask.call()`; khi chỉ cần AST thì không cần tạo bytecode hoặc nạp/chạy class người dùng. **Không bao giờ tự thực thi mã nguồn không tin cậy để lấy diagnostic compile-time.**

## 12. Những lỗi thường gặp và cách sửa

| Nhầm lẫn | Vì sao sai | Cách sửa |
|---|---|---|
| `getLineNumber()`/`getColumnNumber()` bắt đầu từ 0 | Tài liệu quy định **1-based** | Chuyển tọa độ trước khi gửi tới editor nếu UI dùng 0-based |
| `getPosition()` là byte offset của UTF-8 | Nó là **character offset 0-based** | Tách biệt byte/char/display column |
| `Diagnostic.NOPOS` là vị trí đầu file | `NOPOS` nghĩa là không có vị trí | Guard và hiển thị fallback |
| `getSource()` luôn có JavaFileObject | Có chẩn đoán không gắn với source | Kiểm tra null |
| `getCode()` là mã lỗi chuẩn toàn bộ compiler | Compiler-dependent, có thể null | Dùng metadata này có điều kiện |
| Có thể parse nguyên câu `getMessage(Locale)` thành rule | Message thay đổi theo compiler/locale | Dùng Kind, AST và semantic APIs |
| `parse()` thành công chứng minh source compile được | Lỗi type/symbol cần `analyze()` | Thực hiện giai đoạn thích hợp |
| AST luôn có source positions | Có `NOPOS` với node không định vị được | Kiểm tra start/end trước khi dùng |
| `CompilationUnitTree.getLineMap()` luôn khác null | Contract cho phép null | Guard và fallback |
| `getEndPosition` luôn đại diện một selection đẹp ở UI | Ranh giới AST khác caret diagnostic | Kiểm chứng source slice và mục tiêu highlight |
| Dùng regex để tìm declaration Java | Java syntax phức tạp, nhiều loại node | Dùng `TreePathScanner` |
| `com.sun.source.*` là API nội bộ tuyệt đối không dùng | Đây là API được module JDK công bố | Dùng public API, tránh `com.sun.tools.javac.*` |
| Mọi Java runtime đều có compiler | Runtime image có thể bỏ `jdk.compiler` | Kiểm tra `getSystemJavaCompiler()` |
| Một CompilationTask có thể `call` nhiều lần rồi `parse` | Task có lifecycle riêng | Tạo task mới cho lượt mới |
| Một lỗi source chỉ sinh đúng một Diagnostic mọi phiên bản | Recovery và compiler options có thể thay đổi | Test tính chất/Kind, không hard-code count xuyên mọi JVM |
| Source editor đổi sau khi diagnostic tạo | Offset cũ không còn tương ứng | Gắn revision và invalidation |
| Tắt annotation processing là sandbox an toàn | `-proc:none` chỉ tắt processor path | Process isolation và resource limits nếu cần |

## 13. Checklist hoàn thành trình chẩn đoán mã Java

1. Chạy với JDK hiện hành có `java.compiler`/`jdk.compiler`.
2. Chọn `JavaCompiler`/`DiagnosticCollector` thay vì parse text stderr của javac.
3. Dùng `getTask()` đúng nguồn, file manager, listener và options (ví dụ `-proc:none`).
4. Khi cần AST, cast `JavacTask` chỉ nếu compiler hỗ trợ; dùng `parse()` và `analyze()` theo mục tiêu.
5. Với mỗi lỗi, xét `Kind`, `getSource()`, `getPosition()` và `Diagnostic.NOPOS` trước khi render.
6. Nhớ dòng/cột **bắt đầu từ 1**, offset **từ 0**.
7. Duyệt AST bằng `TreePathScanner`/`TreeScanner`; lấy `SourcePositions` cho đúng unit/node.
8. Kiểm tra `start/end`, độ dài source và `LineMap` trước khi cắt hoặc highlight.
9. Không phụ thuộc các compiler code/message implementation-specific trong test portable.
10. Thử cả **mã hợp lệ** và mã sai syntax/semantic, source có tab/Unicode/CRLF và lỗi không vị trí.
11. Khi có luật riêng, dùng `Trees.printMessage` để đặt warning vào đúng node.
12. Trong IDE/CI, gắn lỗi với version của source và xóa diagnostics cũ khi source đổi.
13. Với source không tin cậy, hạn chế resource, quyền, classpath và annotation processing.
14. Không dùng các lớp `com.sun.tools.javac.*` nội bộ khi API `com.sun.source.*` đã đủ.

## Tài liệu tham khảo chính thức

- Oracle Java SE 25: **`javax.tools.Diagnostic<S>`**, ý nghĩa offset, dòng/cột, `NOPOS` và message: https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/Diagnostic.html
- Oracle Java SE 25: **`DiagnosticCollector<S>`**, `getDiagnostics()` và `report()`: https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/DiagnosticCollector.html
- Oracle Java SE 25: **`JavaCompiler`**, `getTask()` và chuẩn file manager/source-in-memory: https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/JavaCompiler.html
- Oracle Java SE 25: **`JavacTask`**, `parse()`, `analyze()`, `generate()`: https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/util/JavacTask.html
- Oracle Java SE 25: **`Trees`**, `getSourcePositions()`, `printMessage()` và semantic mapping: https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/util/Trees.html
- Oracle Java SE 25: **`SourcePositions`**, `getStartPosition()`/`getEndPosition()`: https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/util/SourcePositions.html
- Oracle Java SE 25: **`CompilationUnitTree`**, `getLineMap()`, `getSourceFile()`: https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/tree/CompilationUnitTree.html
- Oracle Java SE 25: **`LineMap`**, chuyển offset và tab-expanded columns: https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/tree/LineMap.html
- Oracle Java SE 26: **module `jdk.compiler`**, Compiler Tree API được xuất bản: https://docs.oracle.com/en/java/javase/26/docs/api/jdk.compiler/module-summary.html

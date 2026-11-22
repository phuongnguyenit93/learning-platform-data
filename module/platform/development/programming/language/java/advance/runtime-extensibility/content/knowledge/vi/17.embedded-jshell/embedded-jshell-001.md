# Khi nào dùng JShell cho đoạn mã Java tương tác thay vì JavaCompiler?

## 1. Câu hỏi kiến trúc cần giải quyết

Giả sử ứng dụng Java cho phép người dùng thử một biểu thức, định nghĩa biến, gọi thử method, thay đổi một vài dòng rồi xem kết quả ngay. Một lựa chọn là gọi `JavaCompiler` để sinh `.class`, tạo class loader mới và thực thi mỗi lần. Lựa chọn khác là nhúng API `jdk.jshell.JShell` để duy trì một phiên tương tác.

Hai API đều liên quan đến **biên dịch Java**, nhưng có hợp đồng sử dụng khác nhau:

- **`JShell`:** đánh giá từng *snippet* — biểu thức, câu lệnh, khai báo biến, method, class hoặc import — trong **một phiên có trạng thái**. Lần nhập sau có thể dùng khai báo của lần nhập trước. API trả về `SnippetEvent`, kết quả biểu thức và diagnostics để công cụ REPL/IDE hiển thị ngay.
- **`JavaCompiler`:** biên dịch các *compilation unit* theo quy trình build rõ ràng, thường tạo bytecode thành tệp `.class`/JAR hoặc artifact trong bộ nhớ thông qua `JavaFileManager`. Việc nạp, tạo instance và thực thi artifact là **giai đoạn riêng** mà ứng dụng phải xây dựng.
- **Cả hai không phải sandbox an toàn cho mã không tin cậy.** Chọn JShell vì trải nghiệm tương tác, không vì cho rằng nó vô hại khi nhận source từ người lạ.

Đề bài không phải “API nào biên dịch nhanh hơn trong mọi trường hợp?”, mà là: **Ứng dụng cần một phiên thử mã từng bước hay cần một sản phẩm biên dịch ổn định, có thể lưu và triển khai?**

## 2. Bản chất của JShell: REPL stateful, không chỉ là eval(String)

JShell được giới thiệu từ Java 9 và có mặt trong module `jdk.jshell`. API trung tâm là `jdk.jshell.JShell`:

```java
try (jdk.jshell.JShell shell = jdk.jshell.JShell.create()) {
    shell.eval("int n = 7;");
    shell.eval("n * 3");
    shell.eval("int twice(int x) { return x * 2; }");
    shell.eval("twice(n)");
}
```

Đoạn trên là **minh họa API**; chương trình độc lập, xử lý `SnippetEvent` và stdout chính xác nằm ở mục 6.

Một phiên JShell lưu **trạng thái nguồn** (biến, method, kiểu, import và các khai báo đang active) cùng **trạng thái thực thi** của chúng. Vì thế `n` vẫn tồn tại khi đánh giá `n * 3`, và method `twice` còn dùng được trong lần nhập tiếp theo. Lập trình viên không phải tự tạo một class Java hoàn chỉnh cho mỗi biểu thức.

Cần phân biệt:

1. **JShell cũng biên dịch source.** Nó dùng cơ sở hạ tầng Java compiler để xử lý snippet, nhưng che đi nhiều thao tác tạo class/wrapper và quản lý execution state. Không đúng khi nói “JShell chạy Java mà không biên dịch”.
2. **JShell không phải `javax.script.ScriptEngine` chung cho mọi ngôn ngữ.** Nó chuyên cho Java snippets và API phân tích của `jdk.jshell`.
3. **JShell CLI và Java API khác nhau.** Lệnh như `/vars`, `/methods`, `/reset` trong chương trình `jshell` tương tác không phải Java snippets để gửi trực tiếp cho `JShell.eval`. API có `variables()`, `methods()`, `drop(...)`, `close()` và các phương thức khác để triển khai thao tác tương đương.
4. **Một lần `eval` nên nhận đúng một snippet hoàn chỉnh.** Muốn nhận nhiều dòng hoặc khối văn bản tùy ý từ một trình soạn thảo, ứng dụng nên dùng `SourceCodeAnalysis.analyzeCompletion(...)` để tách đầu vào và xác định khi nào đã đủ cú pháp, thay vì cắt theo dấu xuống dòng.
5. **State chỉ thuộc phiên JShell cụ thể.** Tạo phiên mới không tự mang theo các biến đã khai báo ở phiên cũ. Dữ liệu mà ứng dụng muốn lưu cần có cơ chế snapshot/replay được kiểm soát.

## 3. JavaCompiler: compile artifact rồi mới load/execute

API `javax.tools.JavaCompiler` thích hợp với pipeline sinh mã hoàn chỉnh, nơi source có thể là một hoặc nhiều file Java có package, dependency và cấu hình compiler:

```text
Source .java / JavaFileObject
       |
       v
JavaCompiler.getTask(...) + JavaFileManager
       |
       v
CompilationTask.call()  -> diagnostics / success / failure
       |
       v
 .class files / in-memory bytecode / JAR
       |
       v
validate + publish artifact
       |
       v
ClassLoader hoặc ModuleLayer
       |
       v
instantiate/invoke/deploy/test
```

JavaCompiler **không có khái niệm phiên REPL duy trì `n` sau một lời gọi** theo hợp đồng chung. Mỗi compilation task xử lý các nguồn và classpath/module path mà caller cung cấp. Muốn thực hiện nhiều lượt nhập liên tiếp, ứng dụng phải quản lý code sinh, tên class, output, version, class loader và vòng đời artifact.

Ngược lại, JavaCompiler có những lợi thế quan trọng khi cần sản phẩm build:

- Biên dịch source có cấu trúc chuẩn: package, named classes, nhiều compilation units, module descriptor, annotation processing và output paths.
- Tạo artifact để **lưu lại, kiểm thử, đóng gói, ký, scan, cache hoặc triển khai**; không phụ thuộc vào một phiên JShell còn sống.
- Tích hợp công cụ build/CI, classpath/module path và chính sách compilation phù hợp.
- Phân biệt rành mạch kết quả compiler với việc thực thi; compile thành công không đồng nghĩa logic runtime thành công.

JavaCompiler có thể được dùng với **source hoặc output trong bộ nhớ** thông qua `JavaFileObject`/`JavaFileManager` tùy biến. Khác biệt giữa hai API **không đơn giản là JShell dùng RAM, JavaCompiler bắt buộc ghi file**.

## 4. Bảng quyết định: khi nào ưu tiên JShell?

| Nhu cầu thực tế | Chọn ưu tiên | Lý do |
|---|---|---|
| Người dùng nhập `1 + 2` và muốn thấy `3` ngay | JShell | Expression snippet có value, không cần tạo class hoàn chỉnh |
| Tạo một biến rồi dùng lại ở nhiều lần nhập | JShell | State sống xuyên các lời gọi `eval` trong cùng phiên |
| Học Java, playground, console nội bộ, REPL trong IDE | JShell | Có snippet status, error diagnostics, source completion |
| Thử phương thức ngắn, import API rồi gọi ngay | JShell | Khai báo/method/import lưu trong phiên, dễ sửa và đánh giá lại |
| Biên dịch hàng chục file Java thành JAR plugin phát hành | JavaCompiler | Cần compilation units, artifact, dependency/output management |
| Sinh một implementation của SPI để host sử dụng lâu dài | Thường JavaCompiler | Kiểm soát binary name, bytecode, class loader và lifecycle |
| Chạy build lặp lại có cache, reproducibility, test/CI | JavaCompiler | Có đường ra artifact tách biệt với phiên tương tác |
| Cần module descriptor, annotation processing hay output chuẩn | JavaCompiler | Phù hợp mục tiêu build hơn so với mô hình snippet |
| Người dùng vừa thử mã, vừa muốn lưu thành tính năng sản phẩm | JShell để prototype; JavaCompiler cho build cuối | Phải chuyển code thử thành source chuẩn, kiểm thử lại |
| Nhận Java không tin cậy và muốn giới hạn file/network/CPU | Không chọn chỉ bằng hai API này | Cần ranh giới bảo mật tiến trình/OS/container riêng |

**Kết luận nhanh:** Nếu thao tác chính là **“nhập một đoạn → nhận phản hồi → sửa ngay trong cùng ngữ cảnh”**, JShell thường phù hợp. Nếu thao tác chính là **“nhận mã nguồn hoàn chỉnh → tạo artifact ổn định → kiểm thử/triển khai”**, JavaCompiler thường phù hợp.

## 5. Sự khác biệt quan trọng về input và output

### Input của JShell

Một input có thể là:

```java
int score = 10;
```

hoặc:

```java
score * 2
```

hoặc:

```java
int bonus(int x) { return x + 5; }
```

Đây là **các snippet riêng biệt**, không phải một source file đầy đủ. JShell lưu định nghĩa giữa các lần `eval`. Biểu thức `score * 2` có thể được gán một biến tạm do JShell tạo, không cần người dùng viết `class Main { ... }`.

### Input của JavaCompiler

Một compilation unit có cấu trúc Java thông thường:

```java
package demo;

public final class Discount {
    public static int apply(int price) {
        return price - 5;
    }
}
```

Đây là source của file `demo/Discount.java`, **không phải chương trình có `main` độc lập**. JavaCompiler có thể chuyển source này thành `demo/Discount.class`. Việc gọi `Discount.apply(10)` là bước runtime khác.

### Output khác nhau

- `JShell.eval(input)` trả `List<SnippetEvent>` — thay đổi trạng thái snippet, giá trị biểu thức (nếu có), exception và thông tin về sự kiện trực tiếp/gián tiếp.
- `JShell.diagnostics(snippet)` trả thông báo lỗi/cảnh báo từ **lần đánh giá gần nhất** của snippet đó; `JShell.status(snippet)` trả trạng thái hiện tại.
- `JavaCompiler.CompilationTask.call()` trả `Boolean` cho sự thành công của task; diagnostics đến từ listener/collector; output bytecode được quản lý qua file manager.
- `SnippetEvent.value()` không phải lúc nào cũng có: khai báo method/import thường có `null` vì không sinh giá trị biểu thức để in.
- `JavaCompiler` không tự invoke method của lớp vừa biên dịch. Caller phải load/execute tách biệt nếu đó là mục tiêu.

Hai API vì vậy có **unit of work** khác nhau: JShell xử lý tương tác có trạng thái; JavaCompiler xử lý một nhiệm vụ biên dịch có đầu vào/đầu ra được chủ sở hữu xác định.

## 6. Ví dụ Java 17 chạy độc lập với JShell API

Chương trình tạo một JShell session, khai báo biến, đánh giá biểu thức, khai báo method, sửa giá trị của biến và phát hiện snippet không hợp lệ. Nó chỉ in các dữ liệu ổn định, không in ID biến tạm hay thông báo lỗi compiler vốn có thể thay đổi.

**Tệp `JshellChoiceDemo.java`:**

```java
import java.util.List;
import jdk.jshell.JShell;
import jdk.jshell.Snippet;
import jdk.jshell.SnippetEvent;

public final class JshellChoiceDemo {
    private static String evaluate(JShell shell, String input) {
        List<SnippetEvent> events = shell.eval(input);
        return events.stream()
                .filter(e -> e.status() == Snippet.Status.VALID)
                .map(SnippetEvent::value)
                .filter(v -> v != null)
                .findFirst()
                .orElse("(no value)");
    }

    public static void main(String[] args) {
        try (JShell shell = JShell.create()) {
            System.out.println("declare=" + evaluate(shell, "int n = 7;"));
            System.out.println("expression=" + evaluate(shell, "n * 3"));
            System.out.println("method=" + evaluate(shell,
                    "int twice(int x) { return x * 2; }"));
            System.out.println("call=" + evaluate(shell, "twice(n)"));
            System.out.println("update=" + evaluate(shell, "n = 9;"));
            System.out.println("call-again=" + evaluate(shell, "twice(n)"));

            List<SnippetEvent> errors = shell.eval("int broken = ;");
            boolean rejected = errors.stream().anyMatch(
                    e -> e.status() == Snippet.Status.REJECTED);
            long errorDiagnostics = errors.stream()
                    .flatMap(e -> shell.diagnostics(e.snippet()))
                    .filter(d -> d.isError())
                    .count();
            System.out.println("invalid-rejected=" + rejected);
            System.out.println("has-errors=" + (errorDiagnostics > 0));
        }
    }
}
```

### 6.1. Lệnh biên dịch/chạy

Trong terminal có JDK 17 hoặc mới hơn, đứng ở thư mục chứa file:

```powershell
# Windows PowerShell
javac --release 17 --add-modules jdk.jshell JshellChoiceDemo.java
java --add-modules jdk.jshell -cp . JshellChoiceDemo
```

```bash
# Linux/macOS
javac --release 17 --add-modules jdk.jshell JshellChoiceDemo.java
java --add-modules jdk.jshell -cp . JshellChoiceDemo
```

`--add-modules jdk.jshell` bảo đảm module cung cấp API JShell được giải vào graph khi host class đang chạy ở classpath. Không sử dụng `java.compiler` như một thay thế cho `jdk.jshell`: hai module khác nhau. Một custom runtime image có thể không đóng gói module JShell, nên cần xác minh môi trường deployment.

### 6.2. Stdout đã kiểm chứng

```text
declare=7
expression=21
method=(no value)
call=14
update=9
call-again=18
invalid-rejected=true
has-errors=true
```

Kết quả đã được xác minh bằng `javac --release 17` và chạy Java. Phân tích:

1. `int n = 7;` tạo biến trong JShell state; event hợp lệ có value `7`.
2. `n * 3` dùng biến đã có và trả `21`, không cần biên dịch một source file mới từ đầu theo cách caller nhìn thấy.
3. Khai báo method `twice` hợp lệ nhưng không phải một phép gọi cho ra giá trị; helper in `(no value)`.
4. `twice(n)` trả `14`, chứng minh method dùng được qua nhiều lần `eval`.
5. `n = 9;` cập nhật state, nên lần gọi tiếp theo trả `18`.
6. `int broken = ;` bị đánh dấu `REJECTED` và sinh error diagnostic; chương trình vẫn có thể dùng các khai báo hợp lệ trong cùng phiên.
7. `try-with-resources` đóng JShell sau khi sử dụng, thay vì giữ execution engine tồn tại vô hạn.

**Giới hạn của helper `evaluate`:** Nó chọn value đầu tiên của event có status `VALID`, đủ cho chương trình demo gửi **một snippet hoàn chỉnh cho mỗi lần gọi**. Công cụ REPL thực tế phải xử lý **toàn bộ** event, vì một lần đánh giá/định nghĩa lại có thể tạo thêm event cập nhật các snippet phụ thuộc. Đừng chỉ lấy `events.get(0)` rồi mặc định phần còn lại không quan trọng.

## 7. Chương trình so sánh: JavaCompiler tạo artifact rõ ràng

Nếu yêu cầu là tạo một class Java chuẩn có thể lưu hoặc triển khai, dùng `JavaCompiler`. Ví dụ Java 17 này viết source file vào thư mục tạm, biên dịch bằng file manager, đóng file manager và xác nhận tệp `.class` được sinh. Nó **không thực thi class vừa biên dịch**, vì đó là trách nhiệm của bước runtime riêng.

**Tệp `CompilerChoiceDemo.java`:**

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public final class CompilerChoiceDemo {
    public static void main(String[] args) throws Exception {
        Path workspace = Files.createTempDirectory("compiler-choice-");
        Path source = workspace.resolve("src/demo/Generated.java");
        Path classes = Files.createDirectories(workspace.resolve("classes"));
        Files.createDirectories(source.getParent());
        Files.writeString(source, """
                package demo;
                public final class Generated {
                    public static int twice(int number) {
                        return number * 2;
                    }
                }
                """, StandardCharsets.UTF_8);

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler is not available");
        }

        var diagnostics = new DiagnosticCollector<JavaFileObject>();
        boolean success;
        try (StandardJavaFileManager manager =
                compiler.getStandardFileManager(
                        diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
            manager.setLocationFromPaths(
                    StandardLocation.CLASS_OUTPUT, List.of(classes));
            var units = manager.getJavaFileObjectsFromPaths(List.of(source));
            success = Boolean.TRUE.equals(compiler.getTask(
                    null, manager, diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null, units).call());
        }

        System.out.println("compiled=" + success);
        System.out.println("artifact=" +
                Files.isRegularFile(classes.resolve("demo/Generated.class")));
    }
}
```

**Biên dịch và chạy trên Windows/Linux/macOS** (đứng ở thư mục chứa file):

```bash
javac --release 17 CompilerChoiceDemo.java
java -cp . CompilerChoiceDemo
```

**Stdout chính xác:**

```text
compiled=true
artifact=true
```

Đây là kết quả đã được kiểm chứng bằng việc biên dịch/chạy. Tên thư mục tạm có thành phần ngẫu nhiên nhưng không xuất hiện trong stdout. Với ứng dụng thực, sau compile hãy kiểm tra diagnostics, source/artifact version, đóng file manager, đóng gói hoặc publish artifact. Sau đó mới quyết định có tạo `URLClassLoader`/`ModuleLayer` để chạy hay không.

**So sánh trực tiếp:** JShell demo ghi `n` rồi dùng lại trong cùng phiên; JavaCompiler demo tạo `demo.Generated.class` có tên nhị phân và đường dẫn xác định. Chọn mô hình nào phụ thuộc việc ứng dụng cần **state tương tác** hay **artifact phân phối**.

## 8. Dùng SnippetEvent, status và diagnostics đúng cách

Một công cụ nhúng JShell không nên hiểu `eval` trả về “chuỗi kết quả hoặc exception”. Thực tế nó trả danh sách `SnippetEvent`, và một event có:

- `snippet()`: snippet liên quan, có thể kiểm tra `kind()` và `source()`.
- `status()`: trạng thái của snippet sau thay đổi được event mô tả.
- `previousStatus()`: trạng thái trước đó khi có thay đổi.
- `value()`: chuỗi biểu diễn giá trị nếu lần đánh giá tạo giá trị; không nên giả định luôn khác `null`.
- `exception()`: exception do snippet thực thi ném theo mô hình exception của JShell; có thể khác lỗi biên dịch.
- `causeSnippet()`: có thể xác định event xảy ra gián tiếp vì snippet khác bị thêm/sửa/xóa.

Một số status quan trọng:

| Status | Ý nghĩa sử dụng |
|---|---|
| `VALID` | Snippet được định nghĩa/đánh giá hợp lệ tại trạng thái đang xét |
| `REJECTED` | Snippet bị từ chối, thường do lỗi không thể trì hoãn |
| `RECOVERABLE_DEFINED` | Khai báo có thể được định nghĩa, dù còn dependency chưa phân giải; chưa phải đảm bảo gọi sẽ thành công |
| `RECOVERABLE_NOT_DEFINED` | Khai báo có thể được khôi phục nhưng chưa tạo được định nghĩa dùng được |
| `OVERWRITTEN` | Khai báo cũ được thay bằng khai báo mới cùng định danh phù hợp |
| `DROPPED` | Khai báo đã bị xóa khỏi trạng thái active |
| `NONEXISTENT` | Trạng thái không tồn tại của snippet trong một số bước chuyển |

**Không gộp mọi status khác `REJECTED` thành “chạy thành công”.** Một method có unresolved dependency có thể ở trạng thái recoverable; khi gọi có thể thất bại và cần dùng `unresolvedDependencies(...)` để giải thích.

Để báo lỗi có ý nghĩa, dùng:

```java
for (SnippetEvent event : shell.eval(input)) {
    System.out.println(event.status());
    if (event.exception() != null) {
        System.err.println(event.exception().getMessage());
    }
    shell.diagnostics(event.snippet()).forEach(diag -> {
        if (diag.isError()) {
            System.err.println(diag.getMessage(java.util.Locale.ROOT));
        }
    });
}
```

Đây là **đoạn minh họa cần đặt trong scope có `shell` và `input`**. Các thông báo diagnostics có thể khác nhau giữa phiên bản JDK/locale; đừng viết bài test dựa trên nguyên văn mọi thông điệp compiler. Ưu tiên assert status, kind, event value và sự tồn tại của error diagnostic.

### Lỗi lúc execute khác lỗi compile

`shell.eval("1 / 0")` có thể được biên dịch thành snippet hợp lệ rồi thất bại khi thực thi, tạo `SnippetEvent.exception()` khác `null`. Lỗi cú pháp như `int broken = ;` lại có thể tạo `REJECTED` và diagnostics. REPL phải trình bày hai tình huống này khác nhau: người dùng sửa cú pháp so với người dùng debug exception khi chạy.

Nếu default execution engine của JShell chạy ngoài tiến trình như JDK thường cấu hình, exception của mã người dùng được mô tả qua API JShell chứ không nhất thiết là đối tượng Throwable của cùng class loader trong host. Đừng tự cast `exception()` thành exception class của mã nguồn đánh giá.

## 9. Giao diện nhập nhiều dòng: SourceCodeAnalysis mới là bước phân tách

Một người dùng có thể nhập:

```java
int total(int x) {
    return x + 10;
}
```

Đây là **một method snippet** trải nhiều dòng, không phải ba snippet. Nếu UI gửi mỗi dòng vào `shell.eval(...)` riêng, nội dung có thể bị từ chối dù method cuối cùng hợp lệ.

API `shell.sourceCodeAnalysis()` cung cấp `SourceCodeAnalysis.analyzeCompletion(buffer)` để nhận biết mức độ hoàn chỉnh và phần source đã đủ điều kiện xử lý. Một cách tiếp cận:

1. Thêm từng dòng người dùng nhập vào input buffer của **một phiên**.
2. Dùng `analyzeCompletion(buffer)` để xác định đã có complete snippet hay cần thêm dấu đóng/braces/semicolon.
3. Khi đủ một snippet, chuyển **exact source của snippet hoàn chỉnh** vào `eval`; giữ phần text dư (nếu có) để tiếp tục phân tích, không bỏ ký tự.
4. Duyệt toàn bộ `SnippetEvent` và cập nhật UI: source, status, value, diagnostics, unresolved dependency và stdout/stderr.
5. Giữ mã nguồn/history theo session ID nếu ứng dụng cần khôi phục hoặc audit.

Phác thảo API (không phải chương trình độc lập):

```java
var analysis = shell.sourceCodeAnalysis();
var completion = analysis.analyzeCompletion(buffer);
if (completion.completeness().isComplete()) {
    String completeSource = completion.source();
    shell.eval(completeSource);
    buffer = completion.remaining();
}
```

Một lệnh trong CLI như `/list` hay `/drop` không gửi qua `eval`; UI phải ánh xạ thành các lời gọi API tương ứng. JShell CLI còn có cơ chế history, prompt, command parser riêng. **Nhúng API không tự có một giao diện REPL hoàn chỉnh.**

## 10. State: sức mạnh lớn nhất đồng thời là rủi ro lớn nhất của JShell

Trong cùng một phiên, nhập:

```java
int discount = 5;
```

rồi:

```java
int price(int base) { return base - discount; }
```

rồi:

```java
discount = 7;
```

có nghĩa method ở lần đánh giá sau có thể quan sát state mới. Điều này rất hữu ích khi dạy học, thử thuật toán hoặc xây console tương tác. Nhưng sản phẩm cần chú ý:

- **Định nghĩa lại khai báo:** JShell cho phép thay một số khai báo cùng tên/chữ ký. Khi đó event có thể nói snippet cũ bị `OVERWRITTEN`; biến/method khác phụ thuộc vào nó có thể thay status hoặc hành vi.
- **Xóa khai báo:** `shell.drop(snippet)` thay đổi source state, có thể ảnh hưởng nhiều snippet phụ thuộc. Không coi `drop` là “đảo ngược mọi side effect” của đoạn mã đã thực thi.
- **Phần phụ thuộc chưa giải quyết:** khai báo có thể được chấp nhận có điều kiện. Gọi `shell.unresolvedDependencies(declarationSnippet)` khi cần hiển thị các tên chưa có, thay vì khẳng định người dùng đã chạy thành công.
- **Side effects vẫn tồn tại:** ghi file, gửi HTTP request, mutate object, tạo thread hoặc cập nhật database không tự rollback chỉ vì người dùng drop/redefine snippet.
- **Reset phiên:** muốn trở về ngữ cảnh hoàn toàn mới, cách đơn giản là `close()` phiên cũ và tạo `JShell.create()` mới. `close()` không khôi phục các hệ thống bên ngoài đã bị thay đổi.
- **Phiên lâu sống:** nhiều snippet và class definitions có thể tăng memory, thời gian phân tích và chi phí điều phối engine. Cần giới hạn session lifetime, số snippet, dung lượng history và số phiên đang mở.

Đối với nhiều người dùng, không nên dùng **một singleton JShell dùng chung cho mọi request**: state sẽ rò qua người dùng, output và hành vi khó dự đoán. Dùng session ID gắn với chủ sở hữu và có lifecycle/timeout rõ ràng.

## 11. Lifecycle: JShell.close khác JavaFileManager.close

JShell implement `AutoCloseable`. Với code host:

```java
try (JShell shell = JShell.create()) {
    // Những lần eval, drop, đọc diagnostics của session này.
}
// shell.close() đã được gọi.
```

Đây là mẫu minh họa. `close()` giải phóng tài nguyên engine; một phiên đã đóng không được dùng tiếp như phiên active. Nếu cần một session mới, tạo instance khác.

JavaCompiler thường có lifecycle:

```java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
try (StandardJavaFileManager manager =
        compiler.getStandardFileManager(null, null, null)) {
    // Tạo task, cấu hình classpath/output và gọi task.call().
}
// Manager được close, nhưng artifact .class có thể vẫn tồn tại.
```

Đây cũng là đoạn minh họa, không phải chương trình độc lập. Ý nghĩa khác biệt:

| JShell | JavaCompiler |
|---|---|
| Quản lý một phiên tương tác và execution state | Quản lý compilation task và artifact |
| Đóng `JShell` khi session kết thúc | Đóng `JavaFileManager` sau tác vụ/phiên compile |
| Có thể dùng `drop`, định nghĩa lại snippet trong cùng session | Không cung cấp state tương tác/overwrite semantics qua task |
| Không nên lấy internal compiled class của JShell làm artifact triển khai mặc định | Artifact đầu ra là mục tiêu thiết kế trực tiếp |
| Có thể còn side effects bên ngoài dù session đã close | Artifact/lớp đã load còn sống theo lifecycle ứng dụng, không theo manager |

Trong cả hai trường hợp, **close tài nguyên API không đồng nghĩa hoàn tác mã Java đã chạy**. Với JavaCompiler, việc nạp/chạy class có thể chưa diễn ra. Với JShell, mỗi lần `eval` có thể đã thực thi side effects ngay.

## 12. Classpath, module và ranh giới host–snippet

Một JShell session chạy trong một execution environment. Nó không bảo đảm nhìn thấy mọi class hoặc object mà ứng dụng host nhìn thấy chỉ vì hai bên cùng là Java.

Các yếu tố quan trọng:

1. **Module `jdk.jshell`:** host cần có module này trong runtime image và trong module graph. `javac --add-modules jdk.jshell`/`java --add-modules jdk.jshell` trong ví dụ giúp rõ ràng.
2. **Classpath cho snippet:** `shell.addToClasspath(pathString)` bổ sung một path vào classpath dùng bởi `eval`. Path phải có JAR/classes mà execution engine có thể đọc; việc cấu hình sai có thể dẫn tới diagnostics hoặc lỗi runtime.
3. **Classpath cho host khác classpath snippet:** lớp host có thể đã được nạp từ application loader, nhưng class trong snippet chạy trong loader/engine khác. Đừng giả định một `Class<?>` hoặc object host tự truyền được qua Java source expression.
4. **Default package:** các class được định nghĩa trong unnamed package của host không phải đường tích hợp ổn định cho snippet. API JShell nói rõ các class trong unnamed package không được truy cập từ package nơi code `eval` được đặt; API công khai nên có package và dependency cấu hình rõ.
5. **Named modules và reflection:** JShell không tự giải quyết mọi cấu hình `requires/exports/opens` của ứng dụng. Nếu sản phẩm cần build named module chuẩn, JavaCompiler + module path/ModuleLayer thường hợp mô hình hơn.
6. **Nhiều phiên:** mỗi phiên có state riêng; classloader và engine lifetime cần được quản lý tránh giữ class/plugin JAR cũ. Không cache bừa `Class<?>`, output hay object kỳ vọng dùng xuyên session.

Không thiết kế một API “chạy thử biểu thức trong JShell rồi lấy object thật trực tiếp từ heap của host” nếu chưa có cầu nối dữ liệu được hỗ trợ. Với workflow cần trao đổi giá trị, cân nhắc serialize qua JSON/string hoặc gọi API/IPC có hợp đồng; lưu ý JShell `SnippetEvent.value()` chỉ là **chuỗi hiển thị**, không phải một object Java sống có thể cast tùy ý.

## 13. Tính song song, timeout và khả năng hủy

Javadoc nêu `JShell` **không thread-safe** (ngoại trừ trường hợp được ghi rõ). Tránh hai request cùng gọi `eval` hoặc `drop` trên một instance trong lúc chưa có cơ chế xếp hàng/đồng bộ rõ ràng.

Đối với một ứng dụng web có nhiều người dùng:

- Một session JShell nên có một **owner** và cơ chế tuần tự hóa các thao tác thay đổi state. Có thể dùng actor/queue một luồng cho từng session.
- Giới hạn số phiên, độ dài snippet, độ sâu history và tổng tài nguyên. Session sống lâu cần cơ chế idle timeout và `close()`.
- `shell.stop()` chỉ **cố gắng** dừng một snippet đang thực thi; Javadoc không bảo đảm lúc nào cũng dừng được, ví dụ code bắt ngoại lệ hoặc bị chặn trong một thao tác không hợp tác.
- `Future.cancel(true)` trên thread host không đồng nghĩa chắc chắn chặn code đang chạy bên execution engine.
- Nếu snippet có thể chạy vô hạn, sinh thread, ghi disk hoặc truy cập mạng, cần giới hạn thực sự ở **cấp process/OS/container**. Execution engine mặc định của JShell thường chạy ngoài tiến trình, nhưng không nên coi điều đó là một sandbox được bảo đảm.
- Không thực hiện các thao tác gọi ngược `eval/drop` từ callback theo cách tạo reentrancy. Khi dùng `onSnippetEvent`, theo tài liệu API, callback được gọi trong lúc state đang biến đổi; phải tuân thủ hạn chế về gọi phương thức JShell trong callback.

Với JavaCompiler, một compilation task cũng có thể lâu hoặc tốn tài nguyên, nhưng task không tự tạo một phiên REPL. Cần quản lý compile worker, timeouts, source limits và cleanup artifact, sau đó quản lý runtime worker **riêng biệt** nếu code sẽ được thực thi.

## 14. Hiệu năng: tối ưu theo vòng đời chứ không mặc định API nào nhanh hơn

JShell được thiết kế để giảm **chi phí tương tác trong trải nghiệm người dùng**: mỗi lần nhập không yêu cầu caller tạo, biên dịch, nạp class source hoàn chỉnh. Nó phù hợp prototyping và feedback nhanh. Tuy vậy:

- Tạo một JShell session có thể có chi phí khởi tạo compiler/engine và tiến trình từ xa.
- Giữ phiên sống cho nhiều lượt có thể tiết kiệm chi phí khởi tạo so với tạo phiên mới trên mỗi phím Enter, nhưng tăng memory, state history và tài nguyên.
- Redefine nhiều lần có thể khiến nhiều snippets phụ thuộc cần được phân tích/cập nhật.
- Thời gian `eval` bao gồm parsing, compilation và có thể cả việc chạy mã — không chỉ một phép tính.
- JavaCompiler với nhiều nguồn/caching/file manager và build pipeline phù hợp có thể hiệu quả hơn khi sản phẩm cần biên dịch một tập source lớn hoặc artifact lâu dài.
- Thử nghiệm hiệu năng phải tính cả **phân tích source, compile, class loading, execution, IO, warmup, process startup và cleanup**, không so một `eval("1+1")` với một build nhiều trăm class.

Một số liệu như “JShell luôn nhanh hơn JavaCompiler” không có giá trị chung nếu chưa định nghĩa workload. Với runtime extensibility, quan trọng hơn là chọn đúng **độ hạt phiên (session)** và **độ hạt build/artifact**.

## 15. Security: không cho source không tin cậy chạy chỉ vì có JShell

JShell rất thuận lợi để viết playground, nhưng việc eval source có thể dẫn tới **thực thi mã Java thật**. Mã đó có thể dùng filesystem, network, CPU, memory, threads hoặc thư viện trong môi trường được phép. Một snippet sai có thể gây lỗi, chiếm tài nguyên hoặc tạo side effects trước khi người dùng nhấn “reset”.

Các kiểm soát có ý nghĩa nếu nguồn không tin cậy:

1. Chạy mã trong **worker process/container tách biệt**, có OS identity/quyền file/network/resource limits và lifecycle độc lập.
2. Giới hạn thời gian, CPU, RAM, thread/process, số snippet và số phiên; có cơ chế kill worker đáng tin cậy chứ không chỉ dựa `JShell.stop()`.
3. Giới hạn classpath/module path, tránh mount tài liệu, secrets hoặc credentials của host vào môi trường chạy mã.
4. Ghi log các phiên để audit, không in giá trị biến/diagnostics chứa thông tin nhạy cảm ra output công khai.
5. Không tin vào `JavaCompiler` như “cơ chế an toàn hơn” nếu sau đó vẫn load/chạy artifact không tin cậy trong JVM host. Với compiler, annotation processing cũng cần chính sách riêng trong build pipeline.
6. Không nhầm **lỗi compile** với **mã an toàn**: một snippet `VALID` chứng minh Java chấp nhận nó ở thời điểm xét, không chứng minh logic không độc hại.

JShell default engine có thể dùng một JVM khác theo thiết kế JDK, nhưng nếu không kiểm soát OS permission và isolation thì một tiến trình khác không tự đủ để tạo boundary bảo mật phù hợp với yêu cầu mạnh.

## 16. Một số kiến trúc áp dụng thực tế

### 16.1. IDE / môi trường học Java có ô nhập tương tác

```text
User nhập câu lệnh
  -> kiểm tra nguồn và số lượng ký tự
  -> SourceCodeAnalysis: đủ một snippet?
  -> session JShell riêng
  -> eval
  -> SnippetEvent/status/diagnostics/value
  -> cập nhật UI/history
  -> tiếp tục dùng state cho câu lệnh kế tiếp
```

Đây là tình huống JShell phát huy ưu thế rõ nhất. UX có thể hiển thị biến hiện tại, method đã định nghĩa, code chưa hoàn chỉnh và chỗ lỗi. Cần chuẩn hóa session ownership và timeout.

### 16.2. Sinh plugin class từ template

```text
Template/source generator
  -> JavaCompiler + JavaFileManager
  -> .class hoặc JAR + metadata
  -> validate, test, sign/publish
  -> ClassLoader / ModuleLayer
  -> lifecycle plugin
```

JavaCompiler phù hợp hơn vì output cần tên lớp, artifact, dependency và rollout ổn định; không nên lấy state của JShell làm nguồn triển khai không được kiểm soát.

### 16.3. Prototype trước, sản phẩm sau

```text
Nhập biểu thức / thử API bằng JShell
  -> chọn lời giải phù hợp
  -> chuyển thành Java source/class/method chuẩn
  -> JavaCompiler hoặc build tool
  -> unit tests + integration tests
  -> publish artifact
```

Đây là workflow lai hợp lý: JShell giảm chi phí khám phá ý tưởng, JavaCompiler tạo sản phẩm dùng lâu dài. Tuy nhiên, không giả định có thể copy nguyên chuỗi snippet rồi compile thành source file; các khai báo top-level, biến tạm `$1` và semantics của REPL phải được chuyển về cấu trúc Java chuẩn.

### 16.4. Rule expression ngắn trong hệ thống nghiệp vụ

Nếu rule do chuyên gia nội bộ tin cậy viết bằng Java và muốn thử ngay trong console, JShell có thể là công cụ **soạn và kiểm thử tương tác**. Nhưng nếu rule phải chạy hàng triệu lần trong production, versioning, audit, transaction, classloader isolation và kiểm thử phù hợp, nên cân nhắc biên dịch artifact Java chuẩn, rule DSL riêng hoặc cơ chế runtime có hợp đồng chặt hơn. Không lấy JShell session của admin để phục vụ mọi request sản xuất.

## 17. Bộ kiểm thử quyết định API và tính đúng của implementation

| Kiểm thử | Khi chọn JShell | Khi chọn JavaCompiler |
|---|---|---|
| Dùng biến ở hai lượt gọi | Lượt hai nhìn thấy state của session | Phải đưa source/dependency phù hợp vào task mới |
| Biểu thức `n * 3` | Event trả value trực tiếp | Cần đặt biểu thức trong method/class hợp lệ |
| Khai báo method rồi gọi | Method active trong session | Method tồn tại trong class output sau compile |
| Source sai cú pháp | `REJECTED`/diagnostics, session còn hoạt động | Task thất bại/diagnostics, không publish artifact |
| Code ném exception khi chạy | `SnippetEvent.exception()` | Exception ở runtime loader/invocation, không phải compiler result |
| Trùng tên khai báo | Có `OVERWRITTEN` và cập nhật phụ thuộc theo REPL | Phụ thuộc input/version/artifact; không phải overwrite session |
| Dừng/reset | Drop/close/recreate session; side effects không tự rollback | Kết thúc task, đóng file manager; artifact vẫn có thể tồn tại |
| Nhiều người dùng | State phải tách per session; không chia sẻ JShell concurrent | Tách per build/output/class loader theo request/version |
| Cần binary artifact để deploy | Không phải sản phẩm chính của API | Là use case trực tiếp |
| Môi trường runtime rút gọn | Phải có `jdk.jshell` và engine thích hợp | Phải có compiler/toolchain thích hợp |
| Source không tin cậy | Bắt buộc cô lập thực thi và giới hạn tài nguyên | Cũng phải cô lập compile/annotation processing và execution |

Một bộ test tích hợp hữu ích cho JShell là: tạo phiên A, khai báo `int n=7`, chạy biểu thức từ cùng phiên, xác minh output; tạo phiên B và xác minh B **không** nhìn thấy `n`; đóng cả hai. Với JavaCompiler, test compile hai phiên bản source thành hai artifact tách biệt và xác minh loader không nạp nhầm bytecode cũ.

## 18. Lỗi thường gặp và cách tránh

- **Hiểu JShell như JavaCompiler mini không có state:** làm mất ưu thế tương tác và thiết kế sai ranh giới session.
- **Đưa nhiều dòng Java rời rạc vào một `eval` mà không phân tích completeness:** dễ tạo `REJECTED` không cần thiết. Dùng `SourceCodeAnalysis` để tách snippet.
- **Gửi lệnh CLI `/vars` vào `shell.eval("/vars")`:** sai tầng API; dùng `variables()` và render UI riêng.
- **Chỉ đọc event đầu tiên:** bỏ lỡ status thay đổi của các khai báo phụ thuộc; duyệt mọi `SnippetEvent`.
- **Xem `value()==null` là lỗi:** method, class, import hợp lệ thường không trả value.
- **Xem `status()==VALID` là mã an toàn:** chưa nói gì về quyền file/network, side effects, hay infinite loop.
- **Gộp error diagnostics với runtime exceptions:** dẫn tới thông điệp sai về nguyên nhân thất bại.
- **Dùng một JShell singleton cho nhiều tenant hoặc nhiều thread:** rò state và tạo race; giới hạn ownership/concurrency.
- **Tưởng snippet có thể trả trực tiếp object host:** value thường chỉ là chuỗi biểu diễn; engine/class loader có thể khác.
- **Giữ phiên sống vô hạn hoặc quên `close()`:** có thể giữ compiler/engine process, class definitions và tài nguyên.
- **Tưởng JavaCompiler chạy class sau khi compile:** caller cần load/execute phase riêng.
- **Tưởng JavaCompiler chỉ làm việc trên disk:** custom JavaFileManager hỗ trợ compilation/output in-memory.
- **Dùng JShell để phát hành JAR production:** thiếu workflow artifact/version/testing; dùng build/compiler pipeline.
- **Dùng remote JShell engine như sandbox:** không có OS security boundary đầy đủ chỉ nhờ lựa chọn API.

## 19. Checklist chọn giải pháp và kết luận

Trước khi chọn, hãy trả lời theo thứ tự:

1. **Input là một Java snippet tương tác hay một tập source file/class/module chuẩn?** Snippet có trạng thái gợi ý JShell; source build chuẩn gợi ý JavaCompiler.
2. **Có cần giữ biến, method, import giữa các lần nhập không?** Nếu có, JShell cung cấp phiên stateful sẵn.
3. **Kết quả cần là giá trị/diagnostics ngay hay artifact có thể lưu/deploy?** Giá trị ngay dùng JShell, artifact ổn định dùng JavaCompiler.
4. **Code cần chạy trong cùng thời điểm nhập hay sau review/test/publish?** JShell phù hợp thử tương tác; JavaCompiler thuận lợi tách compile khỏi execute.
5. **Ai sở hữu runtime state và tài nguyên?** JShell cần session lifecycle; JavaCompiler cần file manager + artifact + class loader lifecycle.
6. **Nguồn mã có đáng tin cậy và có giới hạn OS/process không?** Nếu không, không dựa riêng vào bất kỳ API nào để đảm bảo an toàn.
7. **Có cần chuyển prototype thành sản phẩm không?** Cân nhắc JShell cho giai đoạn thử và JavaCompiler/build tool cho bước đóng gói chính thức.

**Ghi nhớ:** *JShell là API để xây một phiên thử Java tương tác có trạng thái; JavaCompiler là API để xây pipeline biên dịch Java có artifact và trách nhiệm thực thi tách biệt.* JShell có thể dùng compiler ở bên trong, nên không nên hiểu chúng là hai cơ chế “interpreted Java” và “compiled Java”. Sự khác biệt nằm ở **hợp đồng sử dụng, mức độ tương tác, vòng đời trạng thái và loại kết quả mà hệ thống cần**.

**Tài liệu chuẩn Java 17:** [jdk.jshell package](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jshell/jdk/jshell/package-summary.html), [JShell](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jshell/jdk/jshell/JShell.html), [SnippetEvent](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jshell/jdk/jshell/SnippetEvent.html), [SourceCodeAnalysis](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jshell/jdk/jshell/SourceCodeAnalysis.html), [JavaCompiler](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html) và [StandardJavaFileManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html).

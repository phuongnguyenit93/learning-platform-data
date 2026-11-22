# Kiểm tra công cụ phân tích, định dạng và kiểm thử có hiểu cú pháp Java mới

## 1. Vì sao mã Java chạy được nhưng công cụ đi kèm vẫn có thể thất bại?

Khi nâng cấp ngôn ngữ Java hoặc đưa một cấu trúc mới vào dự án, có thể xảy ra tình huống:

- `javac` của JDK mới **biên dịch được**, nhưng một công cụ phân tích tĩnh báo `unexpected token`.
- IDE tô đỏ cú pháp `record`, `switch` expression hoặc pattern matching, dù command-line build chạy tốt.
- Trình định dạng (formatter) từ chối parse file hoặc **thay đổi nội dung text block** sau khi căn lề.
- Tool phân tích cú pháp quét được file nhưng **bỏ sót** một loại node AST mới, khiến kiểm tra quy tắc không còn đáng tin.
- Unit test vẫn pass vì code cũ được chạy, nhưng những file sử dụng cú pháp mới không được compile bởi cấu hình build thực sự.
- CI dùng JDK khác máy phát triển: code được formatter trên một máy rồi không compile trên runner khác.
- Parser hiểu cú pháp, nhưng bước **phân giải tên, type checking, module access** hoặc runtime mới phát hiện lỗi.

Vấn đề không chỉ nằm ở “Java version bao nhiêu?”. Mỗi thành phần có **một mức hỗ trợ ngôn ngữ riêng**: compiler, parser/AST, static analyzer, formatter, IDE, build plugin và runtime.

**Mục tiêu bài học:** xây dựng quy trình xác minh một tool có thực sự **nhận biết cú pháp mới, giữ đúng ý nghĩa chương trình và kiểm tra nó đúng cách**, thay vì chỉ thấy một file được lưu mà kết luận mọi công cụ đã hỗ trợ.

**Phạm vi phiên bản:** nội dung dùng các API được tài liệu Java SE 17/25/26 duy trì hiện nay. Ví dụ chạy được với **Java 17+**, không dựa vào API preview đã lỗi thời. Với cú pháp mới hơn Java 17, phải chọn JDK và phiên bản tool hỗ trợ tương ứng; không gán nhầm phiên bản ngôn ngữ với phiên bản chạy tool.

## 2. Ba cấp độ phải kiểm chứng riêng

Một công cụ làm việc với mã Java có thể “hỗ trợ cú pháp” ở nhiều cấp, không thể đánh đồng.

| Cấp độ | Câu hỏi phải trả lời | Phép thử điển hình |
| --- | --- | --- |
| **Từ vựng và cú pháp** | Tool tokenize/parse được file, có tạo AST đúng node không? | Parse fixture, đếm `Tree.Kind`, không có diagnostics lỗi/`ERRONEOUS` |
| **Ngữ nghĩa / type checking** | Tên, kiểu, scope, control flow và access rules có hợp lệ không? | `javac --release ...`, `JavacTask.analyze()`, test lỗi có chủ đích |
| **Hành vi khi chạy** | Chương trình sau phân tích/định dạng có giữ kết quả không? | Chạy tests, so sánh output, trường hợp biên và dữ liệu nhạy whitespace |

Một static analyzer còn có cấp thứ tư: **quy tắc phân tích** phải thật sự nhận biết node mới. Một parser có thể tạo `SWITCH_EXPRESSION` đúng nhưng rule vốn chỉ tìm `SWITCH` statement lại **bỏ sót** switch expression. Như vậy “parse được” chưa đủ để nói tool kiểm tra đúng logic hay đảm bảo quality.

Ví dụ khác: formatter có thể bảo toàn cây AST ở các node thông thường nhưng nếu **dịch indentation bên trong một Java text block** sai cách, giá trị String ở runtime có thể thay đổi. Vì thế kiểm tra “không báo lỗi” cần đi kèm **kiểm thử hành vi**.

### Cây cú pháp (AST) có gì và không có gì?

Trong module `jdk.compiler`, package `com.sun.source.tree` chứa các interface mô tả **abstract syntax tree (AST)** của Java source. Một số node:

- `CompilationUnitTree`: một compilation unit/file.
- `ClassTree`: class, interface, enum, record tùy `Tree.Kind`.
- `MethodTree`, `VariableTree`: khai báo.
- `SwitchTree`: switch statement.
- `SwitchExpressionTree`: switch **expression** trả về giá trị.
- `YieldTree`: `yield` đưa giá trị từ một nhánh switch expression.
- `BindingPatternTree`: binding pattern như `obj instanceof String s`.
- `LiteralTree`: literals, gồm cả string literals.

**AST không phải bản sao từng ký tự của mã nguồn.** Comment, cách xuống dòng, vị trí dấu cách và cấu trúc token đầy đủ không nhất thiết được biểu diễn thành các node riêng biệt. Vì vậy một công cụ cần chỉnh sửa/format đúng comment và whitespace có thể cần thêm **token stream, source positions, raw source hoặc concrete syntax tree**, chứ không thể chỉ ghép lại mã bằng `Tree.toString()` và mong mọi thứ nguyên vẹn.

## 3. Các cú pháp Java ổn định nên có trong bộ fixture

Đối với module đang học Java 14, một số cấu trúc có liên hệ lịch sử rất quan trọng:

| Tính năng | Phiên bản ổn định chính thức | Dấu hiệu trong source | Một điểm nhận biết của Compiler Tree API |
| --- | --- | --- | --- |
| Switch expressions | **JDK 14**, JEP 361 | `var x = switch (n) { ... };` | `Tree.Kind.SWITCH_EXPRESSION` |
| `yield` trong switch expression | Cùng switch expression JDK 14 | `yield value;` | `Tree.Kind.YIELD` |
| Text blocks | **JDK 15**, JEP 378 | Dùng dấu mở/đóng `"""` với nội dung nhiều dòng | `LiteralTree` có `Tree.Kind.STRING_LITERAL`; **không có kind riêng bảo đảm nhận biết nguồn text block** |
| Records | **JDK 16**, JEP 395 | `record Point(int x, int y) {}` | `ClassTree` với `Tree.Kind.RECORD` |
| Pattern matching for `instanceof` | **JDK 16**, JEP 394 | `obj instanceof String s` | `Tree.Kind.BINDING_PATTERN` |
| Sealed classes | **JDK 17**, JEP 409 | `sealed interface ... permits ...` | `ClassTree`/`ModifiersTree`; cần kiểm tra modifiers/permits, không đếm bằng một kind `SEALED` riêng |
| Record patterns và pattern matching for switch | **JDK 21**, JEP 440/441 | Record deconstruction hoặc `case String s ->` | Các node pattern/case thuộc API version tương ứng |

**Không dùng cú pháp preview của Java 14 như thể nó là cú pháp chính thức của Java 14.** Text blocks, records và một số pattern features đã trải qua preview rồi mới được chuẩn hóa ở các bản Java sau. Với dự án hiện đại, nên chọn **bản stable tối thiểu thực sự chứa từng tính năng** và dùng `--release` tương ứng.

Ví dụ code dùng đồng thời switch expression + text block + record + pattern `instanceof` nên compile với **`--release 17`** (hoặc mức cao hơn phù hợp), **không** với `--release 14` nếu không thay đổi source.

**Cảnh báo về `Tree.Kind`:** các hằng số AST cũng có lịch sử “since” riêng. Ví dụ `SWITCH_EXPRESSION` và `YIELD` có từ JDK 14; `RECORD` và `BINDING_PATTERN` từ JDK 16. Nếu plugin được compile với phiên bản API cũ, nó không thể tự viện dẫn enum constants chưa tồn tại ở bản đó. Muốn hỗ trợ Java mới phải cập nhật **bản JDK/compiler API mà plugin chạy trên**, không chỉ đổi một tùy chọn hiển thị.

## 4. Thiết lập nguồn chuẩn cho phép thử

Bộ fixture nên nhỏ nhưng đủ kích hoạt **chính xác** các cú pháp cần kiểm tra:

- Dùng một file Java có tên trùng với public class.
- Sử dụng một phiên bản Java cụ thể, ví dụ **`--release 17`**.
- Có ít nhất một biểu thức switch và một nhánh `yield`.
- Có record và một binding pattern cho `instanceof`.
- Có text block với nội dung được kiểm chứng ở runtime.
- Có một trường hợp **biên dịch hợp lệ** và một trường hợp **biên dịch thất bại có chủ đích** ở language level thấp hơn.
- Không đưa dependency không liên quan vào fixture để tránh nhiễu classpath.

Tạo file **`SyntaxFixture.java`**:

~~~java
public class SyntaxFixture {
    record Point(int x, int y) {}

    static String classify(Object obj) {
        if (obj instanceof Point p && p.x() > 0) {
            return switch (p.y()) {
                case 0 -> "zero";
                default -> {
                    yield """
                            positive
                            """;
                }
            };
        }
        return "other";
    }

    public static void main(String[] args) {
        System.out.println("zero=" + classify(new Point(2, 0)));
        System.out.println("otherCase=" +
                classify(new Point(2, 3)).replace("\n", "\\n"));
        System.out.println("fallback=" + classify("not a point"));
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 SyntaxFixture.java
java SyntaxFixture
~~~

**Stdout đã kiểm chứng với Java 17 target:**

~~~text
zero=zero
otherCase=positive\n
fallback=other
~~~

Giải thích:

1. `record Point` buộc parser phải hiểu record declaration.
2. `obj instanceof Point p` kiểm tra binding pattern, trong đó biến `p` được phép sử dụng khi biểu thức điều kiện đúng.
3. `switch (p.y())` đang ở bên phải `return`, nên là **switch expression** khác với switch statement.
4. Nhánh `default -> { yield ...; }` chứa một **`YieldTree`**, không phải `ReturnTree`.
5. Text block tạo String `"positive\n"` có dấu newline cuối. `replace("\n","\\n")` chỉ để stdout hiện hai ký tự backslash + n thay cho xuống dòng thực.
6. Một lần chạy với value 0, một lần với value 3 và một lần với object không khớp pattern cho phép kiểm tra cả các đường đi chính.

**Phạm vi khẳng định:** chương trình này đã biên dịch và chạy trong môi trường có JDK 24 dùng `javac --release 17`. Nó không tuyên bố toàn bộ formatter/linter trên Internet đã hiểu file này; từng công cụ cần bài kiểm tra riêng.

## 5. Kiểm tra AST bằng `ToolProvider`, `JavacTask` và `TreePathScanner`

Java SE/JDK cung cấp những API hữu ích, không cần parser thư viện ngoài cho ví dụ cơ bản:

- `javax.tools.ToolProvider.getSystemJavaCompiler()` tìm system Java compiler. Trả **`null`** nếu runtime không cung cấp compiler (ví dụ custom runtime image bỏ module `jdk.compiler`).
- `javax.tools.JavaCompiler` và `StandardJavaFileManager` cung cấp compiler task và danh sách source files.
- `javax.tools.DiagnosticCollector` thu error/warning diagnostics, giúp phân biệt “parse có AST” với “source hợp lệ”.
- `com.sun.source.util.JavacTask` cho phép chạy `parse()` và `analyze()`.
- `com.sun.source.util.TreePathScanner` đi qua các node và duy trì đường dẫn cây.
- `Tree.Kind` xác định node switch expression, yield, record, binding pattern...
- `Trees.instance(task).getSourcePositions()` kết hợp `CompilationUnitTree.getLineMap()` để xác định vị trí node trong file nguồn.

Đây là **Compiler Tree API được JDK tài liệu hóa**, khác với việc import `com.sun.tools.javac.*` internal không được bảo đảm là Java SE API công khai.

Tạo file **`AstSyntaxCheck.java`** bên cạnh `SyntaxFixture.java`:

~~~java
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.Tree;
import com.sun.source.tree.LiteralTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.TreePathScanner;
import com.sun.source.util.Trees;
import java.nio.file.Path;
import java.util.EnumMap;
import java.util.Map;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class AstSyntaxCheck {
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Need JDK with jdk.compiler");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager files =
                     compiler.getStandardFileManager(diagnostics, null, null)) {
            var javaFileObjects =
                    files.getJavaFileObjects(Path.of(args[0]));

            JavacTask task = (JavacTask) compiler.getTask(
                    null, files, diagnostics,
                    java.util.List.of("--release", "17", "-proc:none"),
                    null, javaFileObjects);

            var units = task.parse();
            Map<Tree.Kind, Integer> counts =
                    new EnumMap<>(Tree.Kind.class);
            int[] textBlockValueHits = {0};
            long[] recordLine = {-1};
            Trees trees = Trees.instance(task);

            for (CompilationUnitTree unit : units) {
                new TreePathScanner<Void, Void>() {
                    @Override
                    public Void scan(Tree tree, Void unused) {
                        if (tree != null) {
                            counts.merge(tree.getKind(), 1, Integer::sum);
                            if (tree.getKind() == Tree.Kind.RECORD) {
                                long start = trees.getSourcePositions()
                                        .getStartPosition(unit, tree);
                                recordLine[0] =
                                        unit.getLineMap().getLineNumber(start);
                            }
                        }
                        return super.scan(tree, unused);
                    }

                    @Override
                    public Void visitLiteral(
                            LiteralTree literal, Void unused) {
                        if ("positive\n".equals(literal.getValue())) {
                            textBlockValueHits[0]++;
                        }
                        return super.visitLiteral(literal, unused);
                    }
                }.scan(unit, null);
            }

            task.analyze();

            long errors = diagnostics.getDiagnostics().stream()
                    .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
                    .count();

            System.out.println("compilerErrors=" + errors);
            System.out.println("switchExpressions=" +
                    counts.getOrDefault(Tree.Kind.SWITCH_EXPRESSION, 0));
            System.out.println("yieldNodes=" +
                    counts.getOrDefault(Tree.Kind.YIELD, 0));
            System.out.println("recordNodes=" +
                    counts.getOrDefault(Tree.Kind.RECORD, 0));
            System.out.println("bindingPatterns=" +
                    counts.getOrDefault(Tree.Kind.BINDING_PATTERN, 0));
            System.out.println("textBlockLiteralValueFound=" +
                    (textBlockValueHits[0] == 1));
            System.out.println("recordLinePositive=" +
                    (recordLine[0] > 0));
            System.out.println("erroneousNodes=" +
                    counts.getOrDefault(Tree.Kind.ERRONEOUS, 0));

            if (errors != 0 || recordLine[0] < 1 ||
                counts.getOrDefault(Tree.Kind.SWITCH_EXPRESSION, 0) != 1 ||
                counts.getOrDefault(Tree.Kind.YIELD, 0) != 1 ||
                counts.getOrDefault(Tree.Kind.RECORD, 0) != 1 ||
                counts.getOrDefault(Tree.Kind.BINDING_PATTERN, 0) != 1 ||
                counts.getOrDefault(Tree.Kind.ERRONEOUS, 0) != 0 ||
                textBlockValueHits[0] != 1) {
                throw new AssertionError("AST feature recognition mismatch");
            }
        }
    }
}
~~~

Biên dịch chương trình phân tích và fixture ở cùng thư mục:

~~~bash
javac --release 17 -encoding UTF-8 SyntaxFixture.java AstSyntaxCheck.java
java AstSyntaxCheck SyntaxFixture.java
~~~

**Stdout được kiểm chứng:**

~~~text
compilerErrors=0
switchExpressions=1
yieldNodes=1
recordNodes=1
bindingPatterns=1
textBlockLiteralValueFound=true
recordLinePositive=true
erroneousNodes=0
~~~

### Giải thích các kiểm tra

- **`compilerErrors=0`:** `task.analyze()` đã được gọi sau `parse()`, không chỉ quét một cây cú pháp được tạo ra nửa chừng. Những lỗi ở bước phân giải tên/type checking cũng được thu trong diagnostics.
- **`switchExpressions=1`:** parser phải tạo đúng **`Tree.Kind.SWITCH_EXPRESSION`** cho vị trí trả về giá trị, không lẫn với `SWITCH` statement.
- **`yieldNodes=1`:** scanner nhận biết `yield` riêng, không đánh đồng với `return` hoặc `break`.
- **`recordNodes=1`:** declaration `record Point` được biểu diễn bằng `ClassTree` có kind `RECORD`, không phải class thường.
- **`bindingPatterns=1`:** cú pháp `instanceof Point p` tạo binding pattern node, không chỉ một điều kiện `instanceof` kiểu cũ.
- **`textBlockLiteralValueFound=true`:** `LiteralTree.getValue()` mang giá trị String đã được compiler xử lý (bao gồm newline). Một text block **vẫn được AST coi là string literal**, do đó không thể chỉ dùng `Tree.Kind.STRING_LITERAL` để khẳng định source có ba dấu nháy.
- **`recordLinePositive=true`:** API source positions tìm được vị trí bắt đầu declaration record và line number dương. Nó cho phép linter hoặc tool đưa ra diagnostic gắn với vị trí thực.
- **`erroneousNodes=0`:** không có node `Tree.Kind.ERRONEOUS` được scanner nhận thấy. Kết hợp với `compilerErrors=0`, đây là kiểm tra hữu ích, nhưng **không đủ để chứng minh không có bug runtime hoặc logic**.

**Lưu ý về `-proc:none`:** trong ví dụ này, task tắt annotation processing để kiểm tra AST của fixture không phụ thuộc processor ngoài. Khi chạy build thực, annotation processors có thể là một phần cần kiểm thử riêng; đừng tự tắt chúng trong production build chỉ vì ví dụ đang dùng `-proc:none`.

### Giới hạn của bài kiểm tra AST

- Đếm được node không tự xác minh rule bảo mật/quality **có kiểm tra nhánh đó**.
- `Tree.Kind` mô tả **cấu trúc**, không phải tất cả comment/whitespace/ý nghĩa text của source.
- `getSourcePositions()` có thể trả **-1** nếu vị trí một node không khả dụng. Tool tốt cần xử lý thay vì giả định mọi node có offset dương.
- Một AST visitor chỉ override `visitSwitch(...)` **không chắc** tự xử lý `visitSwitchExpression(...)` đúng ý; xem API của scanner và test cả hai.
- Các Tree APIs có thể bổ sung node mới qua JDK versions; plugin nên có coverage cho các kind mới và fallback an toàn, không tự ý bỏ qua mà vẫn báo “đã kiểm tra toàn bộ”.

## 6. Kiểm tra công cụ chọn đúng language level bằng phép thử âm

Một source có thể được JDK mới parse mặc định, nhưng **sản phẩm lại chỉ hỗ trợ target Java cũ hơn**. Cần kiểm tra compiler thực sự bị ràng buộc đúng version.

Với `TextBlockIndentDemo.java` ở phần 8 (chứa text blocks, stable từ Java 15), hãy chạy:

~~~bash
javac --release 17 -encoding UTF-8 TextBlockIndentDemo.java
~~~

Lệnh hợp lệ, vì text blocks có từ Java 15 và target Java 17 hỗ trợ.

Nếu chạy cùng source với:

~~~bash
javac --release 14 -encoding UTF-8 TextBlockIndentDemo.java
~~~

thì **phải thất bại**. Trên JDK 24 được kiểm thử, compiler trả lỗi về text blocks chưa được hỗ trợ ở `-source 14`. Điều này không có nghĩa chương trình lỗi ở Java 17; nó chứng minh **test âm** đã phát hiện giới hạn version theo thiết kế.

Kiểm tra âm có thể thực hiện bằng script CI:

~~~text
Compile with supported release 17   => expected PASS
Compile same new-syntax source with release 14 => expected FAIL
~~~

Đừng dựa vào việc tìm đúng một câu chữ diagnostic trên mọi JDK: thông điệp compiler có thể khác nhau giữa version, locale và vendor. Trong CI hãy ưu tiên **exit code không bằng 0**, rồi xác nhận nhóm lỗi tương ứng với version mismatch, thay vì so toàn bộ stderr byte-for-byte.

### Vì sao dùng `--release`, không chỉ `--source`/`--target`?

`--release 17` kiểm soát:

- Cú pháp nguồn thuộc phiên bản ngôn ngữ Java 17.
- Version class file khi compile.
- Các API Java SE công khai khả dụng cho target release.

Chỉ đặt `--source 17 -target 17` mà để classpath JDK cao hơn lọt vào có thể khiến code gọi API mới **không có ở Java 17** nhưng vẫn compile; tới runtime Java 17 thì thất bại. Vì vậy lựa chọn mặc định cho dự án xây trên JDK mới mà cần chạy trên runtime cũ là dùng **`--release` phù hợp**.

Với Maven, có thể cấu hình:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Đoạn XML là **trích đoạn `pom.xml`**, không phải file Maven hoàn chỉnh. Với Gradle, cần cấu hình Java toolchains / compile release tương ứng theo version Gradle thực tế, rồi kiểm tra CI. Không đặt JDK/IDE language level riêng lẻ và cho rằng toàn bộ toolchain đã theo đúng version.

**Preview features:** nếu dự án cố ý thử feature đang preview ở **chính bản JDK đang sử dụng**, xem tài liệu `javac --enable-preview` cùng source/release hợp lệ và chạy/test preview tương ứng. Không lấy cú pháp preview từ Java 14 rồi áp dụng các option preview cũ vào Java 17 hoặc JDK 25 như một cách làm chung. Bài này tập trung vào những tính năng đã ổn định để tránh yêu cầu preview không cần thiết.

## 7. Kiểm tra formatter: không chỉ việc nó sửa được khoảng trắng

**Formatter** là công cụ đọc source và xuất source được căn chỉnh theo quy tắc. Ví dụ: **google-java-format**, một formatter do dự án Google phát hành. Theo tài liệu dự án, công cụ dùng **`jdk.compiler` để parse Java**, vì vậy JVM thực thi formatter cần phù hợp với cú pháp Java mới của file nguồn. Hướng dẫn hiện hành của dự án yêu cầu **JDK 21+ để chạy bản formatter hiện đại**, và trong thực tế phải dùng JDK **ít nhất bằng language version source cần format**, cùng với version formatter có hỗ trợ cú pháp đó.

Một lệnh tham khảo khi đã có JAR `google-java-format-all-deps.jar`:

~~~bash
java -jar google-java-format-all-deps.jar --dry-run --set-exit-if-changed SyntaxFixture.java
~~~

Đây là **lệnh tích hợp tham khảo theo README của formatter**, **không phải lệnh đã thực thi trong bài**: máy kiểm thử chỉ sử dụng JDK và không có một bản formatter JAR được cấp trong phạm vi thử. Phải cài/định danh đúng phiên bản, kiểm tra Java runtime dành cho formatter và xem `--help` của bản thực tế.

Ý nghĩa:

- `--dry-run`: kiểm tra format mà không sửa file.
- `--set-exit-if-changed`: đưa việc khác biệt format vào exit code, hữu ích cho CI.
- Dùng `--replace` khi **đã muốn thực sự sửa source**, không dùng nó như lệnh kiểm tra read-only.
- Pin version của formatter ở build để IDE và CI không tranh cãi vì các thay đổi thuật toán formatting.

### Một formatter đạt chất lượng cần qua ít nhất năm phép thử

1. **Parse được cú pháp:** đưa `SyntaxFixture.java` qua formatter; không `unsupported syntax` hoặc crash.
2. **Kết quả compile được:** source sau format vẫn compile với `javac --release 17`.
3. **Kết quả runtime không đổi:** `zero=zero`, `otherCase=positive\n` và `fallback=other` giữ nguyên.
4. **Idempotence:** format thêm lần thứ hai không tiếp tục sửa code, tức `F(F(source)) == F(source)` về nội dung file. Nếu mỗi lần formatter sửa lại các dòng mới, build không ổn định.
5. **Không làm mất dữ liệu nguồn quan trọng:** comment, Javadoc, literal values, escapes, line continuation, text blocks, annotations, license headers và vị trí code cần giữ lại.

Một diff đẹp hơn **không đủ chứng minh** chương trình tương đương. Formatter cũng có thể thay thứ tự imports (trong một số mode) hoặc tác động tới code dùng comment/annotation. Vì thế hãy đọc diff sau khi format những file chứa syntax mới, không auto-accept một thay đổi lớn vì tool “format passed”.

### Bài toán text block đặc biệt

Trong text blocks, **indentation** có thể ảnh hưởng **giá trị chuỗi** vì Java loại bỏ *incidental whitespace* theo quy tắc đóng/mở `"""` và các dòng nội dung. Nếu formatter di chuyển một dòng nội dung nhưng không giữ quan hệ indentation phù hợp, String runtime có thể khác.

Một phép thử ngắn được chạy thật ở phần tiếp theo sẽ chứng minh sự khác biệt. Nó không có nghĩa formatter nào cũng mắc lỗi, mà là **lý do phải kiểm tra semantic preservation** thay vì chỉ tin vào formatting diff.

## 8. Java 17+ số 3: một dấu cách có thể thay đổi giá trị text block

Tạo file **`TextBlockIndentDemo.java`**:

~~~java
public class TextBlockIndentDemo {
    public static void main(String[] args) {
        String original = """
                x
                """;
        String shiftedContent = """
                 x
                """;

        System.out.println("original=" +
                original.replace(" ", "_").replace("\n", "\\n"));
        System.out.println("shifted=" +
                shiftedContent.replace(" ", "_").replace("\n", "\\n"));
        System.out.println("sameValue=" +
                original.equals(shiftedContent));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 TextBlockIndentDemo.java
java TextBlockIndentDemo
~~~

**Stdout đã kiểm thử:**

~~~text
original=x\n
shifted=_x\n
sameValue=false
~~~

Chỉ có **một dấu cách bổ sung trước ký tự `x`** trong dòng nội dung thứ hai. Dòng đóng text block vẫn giữ vị trí cũ, nên khi Java loại bỏ phần thụt đầu dòng chung:

- `original` nhận giá trị `"x\n"`.
- `shiftedContent` nhận giá trị `" x\n"` (có một dấu cách).
- Hai String khác nhau; bài đổi dấu cách thành `_` khi in để người đọc nhìn rõ.

Đây là **hai file/literal hợp lệ về cú pháp**. Một formatter làm thay đổi layout kiểu này mà không bảo toàn ý nghĩa sẽ không thể được chứng minh đúng chỉ bằng việc chạy parser.

Đối với source chứa JSON/SQL/template trong text block, thay đổi whitespace có thể gây sai kết quả, checksum, snapshot, query semantics hoặc giao thức. Khi nâng cấp formatter, nên có **tests nội dung exact string** và test những nơi text block được sử dụng.

**Điểm AST cần nhớ:** cả hai String trong ví dụ đều có node kind `STRING_LITERAL`. Nếu tool kiểm tra chỉ **đếm số lượng `STRING_LITERAL`**, hai phiên bản sẽ trông tương tự, nhưng `LiteralTree.getValue()` và runtime cho thấy nội dung khác nhau. Vì vậy so sánh AST thô hoặc node counts không thay thế kiểm thử semantic values.

## 9. Static analyzers và linters: hỗ trợ grammar khác với hỗ trợ rule

**Parser:** đọc được cấu trúc Java.  
**Linter:** áp các quy tắc như style, cấu trúc, naming, độ phức tạp hoặc code smells.  
**Semantic analyzer:** cần type resolution/symbols để phát hiện vấn đề sâu hơn.

Một tool như **Checkstyle** dùng parser riêng, có bộ quy tắc kiểm tra style. Tài liệu dự án hiện tại nêu các bản **Checkstyle 14.x chạy trên Java 21+** và hỗ trợ parse các tính năng ngôn ngữ **đến Java 25**; hỗ trợ preview features có thể thay đổi. Điều này là một ví dụ rõ ràng rằng:

- **Java để chạy linter** và **Java syntax linter hiểu được** không nhất thiết cùng phiên bản.
- Cùng một phiên bản linter có thể hiểu cú pháp đến một mức nhất định dù JVM chạy nó có version cao hơn.
- Không thể suy luận Checkstyle 14.x chắc chắn hiểu **mọi** cú pháp được bổ sung sau Java 25; phải xem release notes của tool.
- Ngoài support grammar, còn phải kiểm tra **rule** có đúng với AST mới hay không.

**Cách kiểm chứng linter trong dự án:**

1. Xác định version linter và Java runtime tool đó đang dùng.
2. Kiểm tra bảng hoặc release notes “Supported Java Language Version” của **chính version** đã pin.
3. Chạy linter trên fixture chứa cú pháp đang sử dụng; fail khi parse error.
4. Tạo **test rule dương** có lỗi cố ý để rule chắc chắn báo đúng trên cấu trúc mới.
5. Tạo **test rule âm** với mã hợp lệ, để tránh false positive khi dùng record, switch expression hoặc pattern variables.
6. Ghi kết quả ra CI và giữ version linter ổn định; nâng cấp theo nhánh riêng khi muốn dùng syntax mới.

### Ví dụ rule bị bỏ sót mà không có parse error

Một rule viết từ trước chỉ kiểm tra:

~~~java
if (tree.getKind() == Tree.Kind.SWITCH) {
    // Kiểm tra số lượng nhánh trong switch statement.
}
~~~

Đây là **mã minh họa**, không phải chương trình hoàn chỉnh. Khi gặp:

~~~java
int label = switch (code) {
    case 1 -> 10;
    default -> 20;
};
~~~

node có kind **`SWITCH_EXPRESSION`**, không phải `SWITCH`. Nếu rule phải kiểm tra cả statement và expression mà không cập nhật visitor, nó sẽ **bỏ sót** mà không nhất thiết báo parse error.

Một điều kiện khái quát hơn:

~~~java
Tree.Kind kind = tree.getKind();
if (kind == Tree.Kind.SWITCH ||
        kind == Tree.Kind.SWITCH_EXPRESSION) {
    // Rule xử lý cả hai dạng switch;
    // còn phải phân biệt nhánh expression, yield và rules control flow.
}
~~~

Đoạn này chỉ mô tả **định hướng viết rule**, chưa chứng minh visitor đã phân tích đúng mọi `case` và `yield`. Cần tests với từng cách viết switch: statement cũ, expression arrow, nhánh block có yield, default/exhaustiveness và pattern cases khi language version hỗ trợ.

### IDE cũng cần được xem là một công cụ riêng

Khi terminal chạy `javac --release 17` thành công nhưng IDE vẫn gạch lỗi:

- Kiểm tra **Project SDK**, **module SDK**, **language level** và **build tool JVM**.
- Xác định IDE parser/indexer version có hỗ trợ Java syntax đang dùng.
- Kiểm tra compiler target trong Maven/Gradle có khớp IDE settings.
- Làm mới project model hoặc invalidates caches **chỉ sau khi** đã kiểm chứng cấu hình, không dùng “xóa cache” như cách thay cho upgrade IDE.
- Dùng CLI compiler làm **baseline đáng tin**, rồi kiểm tra IDE lint/format/plugin riêng.

## 10. Ma trận kiểm thử bắt buộc cho syntax mới

Một checklist hữu ích khi thay đổi Java language level:

| Loại test | Input | Kết quả mong đợi |
| --- | --- | --- |
| **Positive compile** | Source với syntax mới, `--release` hỗ trợ | Biên dịch thành công |
| **Negative compile** | Cùng source với `--release` chưa hỗ trợ syntax | Biên dịch thất bại có chẩn đoán đúng nhóm |
| **AST recognition** | Fixture có switch/record/pattern | Node kind phù hợp, không lỗi diagnostics |
| **Semantic analyze** | Source hợp lệ đầy đủ symbols/types | Không error sau `analyze()` |
| **Rule detects violation** | Source mới có một lỗi linter cố ý | Linter báo lỗi, không bỏ sót |
| **Rule accepts valid** | Source mới nhưng không có lỗi rule | Linter không báo false positive |
| **Formatter parse** | Fixture đầy đủ syntax | Không crash/unsupported grammar |
| **Formatter compile** | Source sau format | `javac --release` tương ứng pass |
| **Formatter idempotent** | Format output lần thứ hai | Không thay đổi thêm |
| **Semantic preservation** | Code trước/sau format | Cùng kết quả tests, strings và data |
| **Runtime tests** | Các nhánh trong switch, pattern, text block | Stdout và behavior đúng |
| **Build reproducibility** | CI runner với version pin | Cùng source/artifacts/test results theo hợp đồng |
| **Multi-JDK matrix** | JDK versions nằm trong danh sách hỗ trợ của dự án | Pass trên runtime thật cho target versions |

Điều quan trọng là kiểm tra **hai chiều**:

- Một cú pháp mới phải được chấp nhận **khi nó hợp lệ**.
- Cú pháp bất hợp lệ, code vi phạm rule hoặc code dùng sai language level phải bị từ chối **khi đáng lẽ phải từ chối**.

Nếu linter luôn in “0 warnings” vì không chạy trên file chứa cú pháp mới, thì không có bằng chứng nào cho thấy nó hiểu code. Phải xác minh số file được scan hoặc đưa fixture cố ý vi phạm vào test suite.

## 11. Lựa chọn compiler, formatter và analyzer: đừng đo version bằng một con số chung

Một dự án Java 17 có thể đồng thời có:

- JDK 24 hoặc JDK 25 **để chạy build**;
- compiler target **`--release 17`**;
- một formatter phiên bản mới yêu cầu **JDK 21+ để chạy**;
- một linter phiên bản khác có grammar support đến **Java 25**;
- runtime production chạy **Java 17**;
- IDE cài **JDK 26** nhưng project language level giữ **Java 17**.

Từng lựa chọn hợp lệ nếu **đều được cấu hình đúng và kiểm thử**, nhưng không thể nói “dự án dùng Java 17 nên mọi tool chạy Java 17” hoặc “JDK 26 trên máy sẽ tự biến source thành cú pháp Java 26”.

Để duy trì đồng bộ, ghi vào tài liệu build ít nhất:

~~~text
Project language release: 17
Compiler JDK on CI: a supported JDK providing --release 17
Application runtime: Java 17+ per project support policy
Formatter: pinned tool version + required runtime JDK
Linter/analyzer: pinned version + grammar support + required runtime JDK
IDE language level: 17
Preview language features: disabled unless explicitly approved
~~~

Danh sách trên là **mẫu mô tả**, không phải file cấu hình của một hệ thống build cụ thể.

**Tách nghĩa của version:**

- **Language feature support**: parser có hiểu grammar cần dùng?
- **Runtime compatibility**: class file và API có chạy ở Java production?
- **Tool runtime requirement**: formatter/linter cần JRE/JDK nào để tự khởi động?
- **Compiler API compatibility**: tool dựa `jdk.compiler` đang dùng các node và phương thức phù hợp với bản JDK nào?
- **Rule coverage**: parser hiểu rồi, rule có phân tích node đúng không?

Nếu chỉ kiểm tra một dòng `java -version`, bốn câu hỏi còn lại vẫn chưa được trả lời.

## 12. Một quy trình CI mẫu cho cú pháp Java ổn định

Đây là workflow mang tính khái niệm; tên task tương ứng sẽ khác tùy Maven/Gradle/CI system:

~~~text
Resolve toolchain:
  pin JDK/compiler and formatter/linter versions
        |
        v
Compile source at configured --release
        |
        v
Parse + analyze syntax fixtures
        |
        v
Format check (dry-run only)
        |
        v
Static analysis + positive/negative rule tests
        |
        v
Run unit/integration tests, exact text-block values
        |
        v
Optionally test runtime on supported JDK matrix
        |
        v
Package / publish if all gates pass
~~~

Có thể thực thi một tập lệnh cơ bản tại chỗ:

~~~bash
javac --release 17 -encoding UTF-8 SyntaxFixture.java AstSyntaxCheck.java TextBlockIndentDemo.java
java SyntaxFixture
java AstSyntaxCheck SyntaxFixture.java
java TextBlockIndentDemo
~~~

Các lệnh trên đã được kiểm tra về mặt compile/run trong môi trường JDK 24 với target Java 17. Bản thân format-check/linter của bên thứ ba chưa được chạy ở môi trường này, vì cần binary và version cụ thể của dự án.

Nếu dùng Maven/Gradle:

- Cấu hình `--release 17` qua compiler plugin/toolchain.
- Đưa các syntax fixtures và AST checks vào test sources hoặc custom verification task.
- Bắt đầu từ command **kiểm tra định dạng không sửa source** trong CI.
- Chạy static analysis sau khi tool đã được kiểm chứng hỗ trợ syntax.
- Chạy test trên artifact đã build, không chỉ file được IDE compile theo cache.
- Đặt fail-fast đúng tầng: parse error của formatter không biến thành “format check skipped”, linter crash không biến thành “0 violations”.
- Theo dõi báo cáo chẩn đoán: có bao nhiêu files được scan, rules nào được bật và có loại source nào bị loại trừ.

### Vấn đề cần cân nhắc khi dùng annotation processors

Một số công cụ phát sinh source code trong build. Nếu fixture chỉ có file gốc, có thể bỏ qua lỗi parser/linter trên generated code. Cần làm rõ source sets:

- `src/main/java` và `src/test/java`.
- `module-info.java` nếu dự án modular.
- Generated Java sources do annotation processors tạo, nếu chúng là một phần release.
- Multi-release JAR source theo language level khác nhau, nếu dự án thực sự dùng.
- Các script, snippet hoặc source fragments được IDE/tool biên dịch theo quy tắc riêng.

Không nên ép một formatter chạy trên generated code mà không có chính sách, nhưng phải **chủ động xác định** tool cần kiểm tra phần nào và vì sao.

## 13. Chẩn đoán lỗi: parser, analyzer, formatter và test khác nhau ra sao?

| Triệu chứng | Nơi kiểm tra trước | Khả năng nguyên nhân |
| --- | --- | --- |
| `javac` báo `records are not supported in -source 14` | Compiler target `--release` | Java 14 chưa có record stable |
| Formatter báo unexpected token ở `record` | Version formatter, JDK chạy tool | Tool parser chưa hỗ trợ record |
| Checkstyle parse fail tại `yield` | Language support và config Checkstyle version | Grammar/rule version chưa phù hợp |
| AST scanner đếm `switchExpressions=0` dù fixture có switch expression | Visitor/AST API và fixture được scan | Rule chỉ xử lý `SWITCH` hoặc scan nhầm file |
| Parser được, `analyze()` lỗi symbol | Classpath/module path và type rules | Dependency/visibility hoặc type error |
| Formatter chạy xong nhưng text block khác | Diff/giá trị `LiteralTree.getValue()` | Whitespace/escape bị thay đổi |
| Compile pass nhưng CI trên Java 17 không chạy | `--release` và runtime JDK thực tế | Dùng API/class file vượt target hoặc không test đúng runtime |
| IDE tô đỏ nhưng CLI pass | IDE language level/plugin cache | Tooling lệch configuration hoặc parser lỗi thời |
| Linter báo 0 nhưng rule cố ý sai vẫn pass | Source inclusion/rule configuration | File hoặc rule không được chạy |
| AST có `ERRONEOUS` nhưng tool vẫn báo success | Diagnostic checking logic | Tool chỉ scan node counts, không xem errors |

Quy trình giải quyết nên bắt đầu bằng **bằng chứng tối thiểu**:

1. Xác định version của **JDK chạy compiler** và **JDK chạy formatter/linter**.
2. Tách một fixture ngắn chứa đúng syntax gây lỗi.
3. Chạy `javac --release R` làm baseline.
4. Chạy parser/analyzer/linter trên **cùng file** và ghi error message.
5. Nếu tool không parse được, xác nhận ngữ pháp được hỗ trợ ở phiên bản đó, rồi **nâng tool** hoặc chọn source language level phù hợp.
6. Nếu parse được nhưng rule không chạy, bổ sung positive/negative rule tests hoặc sửa visitor.
7. Nếu formatter làm thay đổi semantics, khóa version formatter, báo bug và **không chấp nhận output làm nguồn đáng tin** cho tới khi được kiểm chứng.
8. Chạy lại compile và tests trước khi đưa vào CI mặc định.

**Không giải quyết bằng cách bật tùy tiện `--enable-preview`**, vì preview là cơ chế riêng cho language features đang preview tại một JDK cụ thể. Nó không sửa lỗi parser/linter cũ hoặc formatter viết sai.

## 14. Những lỗi hiểu nhầm thường gặp

**Lỗi 1 — “`javac` compile được nên mọi tool đều hiểu Java mới.”**  
Sai. Formatter, linter, IDE parser và analyzer có thể dùng grammar khác hoặc JDK khác.

**Lỗi 2 — “Formatter xuất ra file tức là đã bảo toàn ý nghĩa.”**  
Chưa đủ. Cần compile, tests và kiểm tra nội dung text blocks/escapes.

**Lỗi 3 — “Một AST có `SWITCH` nghĩa là mọi dạng switch đã được kiểm tra.”**  
Sai. Switch statement và expression có node kind riêng.

**Lỗi 4 — “Text block có `Tree.Kind.TEXT_BLOCK`.”**  
Không nên giả định. Java Compiler Tree API xử lý nó như `STRING_LITERAL`; cần xem giá trị literal và source span khi muốn phân biệt cú pháp gốc.

**Lỗi 5 — “AST node counts giống nhau chứng minh source cùng nghĩa.”**  
Sai. Hai literals khác nội dung có thể có cùng số node `STRING_LITERAL`.

**Lỗi 6 — “Record là class thường nên chỉ tìm `Tree.Kind.CLASS` là đủ.”**  
Sai. `ClassTree` có kind `RECORD` cho record declaration.

**Lỗi 7 — “Một parser pass nghĩa là type checking pass.”**  
Sai. Cần `analyze()` hoặc compile thật để kiểm tra symbols/types.

**Lỗi 8 — “Một linter không báo gì tức là nó đã kiểm tra tất cả files.”**  
Sai. Cần xác nhận file inclusion và rule coverage, tốt nhất dùng test cố ý vi phạm.

**Lỗi 9 — “`--release 17` và JDK chạy formatter là một version.”**  
Không nhất thiết. Compiler target, tool runtime và parser grammar là ba lớp cấu hình.

**Lỗi 10 — “Trình định dạng chỉ có thể sửa khoảng trắng vô hại.”**  
Sai trong bối cảnh text blocks, escape, lexical grammar và comment positioning; phải kiểm chứng semantic preservation.

**Lỗi 11 — “Mọi syntax preview thời Java 14 đều được dùng y nguyên trong Java 17.”**  
Sai. Chỉ dùng cú pháp đã ổn định tại release mục tiêu, tham khảo tài liệu JDK tương ứng.

**Lỗi 12 — “Nếu test Java 17 pass, code dùng Java 21 features cũng sẽ pass khi chạy Java 17.”**  
Sai. Source grammar và class file/API version phải tương thích runtime mục tiêu.

**Lỗi 13 — “Muốn xử lý `record` phải import compiler internal `com.sun.tools.javac.*`.”**  
Không cần cho các ví dụ AST cơ bản; các public Tree APIs nằm trong `com.sun.source.tree` và `com.sun.source.util` của module `jdk.compiler`.

**Lỗi 14 — “Một `--dry-run` đã format code vào file.”**  
Không. Dry-run chủ yếu kiểm tra, không thay đổi source. Muốn áp dụng phải dùng tùy chọn riêng và vẫn chạy tests.

**Lỗi 15 — “IDE chạy ổn là CI chắc chắn ổn.”**  
Sai. CI có toolchain và plugin versions độc lập.

**Lỗi 16 — “Chỉ cần nâng JDK, không cần nâng linter.”**  
Sai. Tool có parser/AST và hỗ trợ grammar riêng; một linter quá cũ vẫn có thể không hiểu syntax mới.

**Lỗi 17 — “Mọi warning là lỗi ngôn ngữ.”**  
Không. Có warnings về style, deprecation, annotation processing hoặc runtime policy; cần phân loại, không gọi tất cả là syntax errors.

**Lỗi 18 — “Chỉ cần test đường hợp lệ.”**  
Không. Test âm rất cần để chứng minh linter/validator thực sự **phát hiện** syntax hoặc rule violations thay vì bỏ qua.

## 15. Checklist trước khi merge code dùng cú pháp Java mới

1. **Xác định syntax cụ thể**: switch expression, yield, text block, record, pattern, sealed class hay tính năng mới hơn?
2. **Ghi stable JDK release** chứa syntax đó; không suy từ năm tạo module hoặc trạng thái preview cũ.
3. **Pin `--release`** của compiler, và kiểm tra compiler version hỗ trợ release đó.
4. **Xác minh ToolProvider/JDK compiler** có sẵn nếu analyzer dựa trên `jdk.compiler`.
5. **Compile positive fixture** chứa feature và chạy các trường hợp nhánh thực tế.
6. **Compile negative fixture** ở release chưa hỗ trợ để xác minh gate.
7. **Kiểm tra AST kinds**: có `SWITCH_EXPRESSION`, `YIELD`, `RECORD`, `BINDING_PATTERN` nếu fixture dùng chúng?
8. **Kiểm tra diagnostics**: sau parse/analyze không còn error hay `ERRONEOUS`.
9. **Kiểm tra linter rule**: source mới có lỗi cố ý phải bị báo; source tốt phải pass.
10. **Kiểm tra formatter**: version/runtime tương thích, dry-run pass sau khi định dạng.
11. **Kiểm tra idempotence**: chạy format hai lần không thay đổi thêm.
12. **Chạy lại compile và runtime tests sau format**, đặc biệt text blocks, escaped strings và comments quan trọng.
13. **So sánh source value** với `LiteralTree.getValue()` nếu tool có nguy cơ thay đổi literal.
14. **Xác nhận files được scan** trong CI: main, test, module-info và generated code theo chính sách.
15. **Kiểm tra IDE language level** không lệch build tool; không xem IDE một mình là nguồn chân lý.
16. **Chốt version matrix**, lưu bằng chứng vào CI logs trước khi đưa syntax mới vào dự án lớn.

## 16. Bài tập tự luyện

**Bài 1 — AST switch.**  
Từ `SyntaxFixture.java`, đổi `return switch` thành một `switch` statement gán vào biến, giữ hành vi tương đương. Chạy lại AST checker. Bạn cần cập nhật expectation của `SWITCH_EXPRESSION` như thế nào? Tại sao `YIELD` có thể biến mất?

*Gợi ý:* switch statement có `Tree.Kind.SWITCH`, khác switch expression, và thường dùng assignment/`break` theo cấu trúc tương ứng.

**Bài 2 — Record và class.**  
Đổi `record Point(int x,int y)` thành một class thông thường với constructor/accessors tương ứng. Chạy lại scanner. Bạn phải sửa expectation của `RECORD` ra sao? Có cần thêm test behavior của `equals()/hashCode()/toString()` nếu muốn thay thế hoàn toàn semantics record không?

*Gợi ý:* thay record bằng class không tự động sinh toàn bộ semantics của record nếu không viết code tương ứng.

**Bài 3 — Text block.**  
Thêm một dấu cách ở đầu dòng nội dung trước `positive` nhưng giữ closing delimiter tại vị trí cũ. Chạy lại program và kiểm tra exact String. Vì sao AST kind counts vẫn có thể không đổi?

*Gợi ý:* kiểm tra `LiteralTree.getValue()` chứ không chỉ `Tree.Kind.STRING_LITERAL`.

**Bài 4 — Negative release.**  
Chạy fixture với `--release 14` và giải thích vì sao một số syntax chưa là ngôn ngữ stable ở thời điểm đó. Sau đó thử phiên bản source chỉ dùng switch expression mà không có record/pattern/text block. Nó có thể biên dịch với `--release 14` không?

*Gợi ý:* switch expressions đã stable từ Java 14.

**Bài 5 — Linter coverage.**  
Một rule chỉ tìm `Tree.Kind.SWITCH`. Đưa switch statement và switch expression vào hai fixtures khác nhau, yêu cầu rule báo trên cả hai. Kết quả nào chứng minh rule đang bỏ sót?

*Gợi ý:* parser pass nhưng một nhánh AST chưa được visitor xử lý.

**Bài 6 — Formatter safety.**  
Chạy formatter đã chọn trên file text block, lưu diff, compile/test lại và format lần hai. Chứng minh `F(F(source)) == F(source)` và String value giữ nguyên; nếu không, pipeline phải làm gì?

*Gợi ý:* dừng merge hoặc cập nhật/đổi version formatter, không tự động áp dụng output phá semantics.

**Bài 7 — Toolchain matrix.**  
Với ứng dụng target Java 17 nhưng linter yêu cầu JRE 21 để chạy, xác định cấu hình compiler target, JDK chạy linter và production runtime. Những version nào bắt buộc phải trùng, và những version nào chỉ cần tương thích?

*Gợi ý:* tool runtime >= yêu cầu của tool; source/bytecode/API phải tương thích production runtime; không nhất thiết mọi Java process dùng một JDK.

## 17. Câu hỏi kiểm tra kiến thức

**Câu 1.** Compiler Tree API trong JDK nằm ở module nào?  
**Đáp án:** `jdk.compiler`, gồm `com.sun.source.tree` và `com.sun.source.util`.

**Câu 2.** Cần API nào để nhận system Java compiler trong chương trình Java?  
**Đáp án:** `ToolProvider.getSystemJavaCompiler()`; trả `null` nếu compiler không có trong runtime.

**Câu 3.** `Tree.Kind.SWITCH_EXPRESSION` và `Tree.Kind.SWITCH` có cùng nghĩa không?  
**Đáp án:** Không. Một bên biểu thức có giá trị, một bên statement.

**Câu 4.** Record declaration có `Tree.Kind.CLASS` hay `Tree.Kind.RECORD` trong Tree API hiện đại?  
**Đáp án:** `RECORD`.

**Câu 5.** Một text block có nhất thiết là AST kind riêng khác string literal không?  
**Đáp án:** Không. `LiteralTree` cho text block vẫn là `STRING_LITERAL`; muốn xác minh nội dung thì đọc `getValue()`.

**Câu 6.** Vì sao phải gọi `JavacTask.analyze()` sau `parse()` trong một bài test compiler?  
**Đáp án:** Để kiểm tra thêm name/type resolution và thu diagnostics ngữ nghĩa, không chỉ kiểm tra syntax parsing.

**Câu 7.** `--release 17` có tự chuyển formatter sang phiên bản Java 17 không?  
**Đáp án:** Không. `--release` là option của compiler; formatter có runtime/tool version riêng.

**Câu 8.** Một formatter chạy không lỗi có chứng minh text block giữ nguyên giá trị chưa?  
**Đáp án:** Chưa. Cần test exact string behavior và kiểm tra diff.

**Câu 9.** Static analyzer quét `SWITCH` nhưng không quét `SWITCH_EXPRESSION` có thể gây gì?  
**Đáp án:** False negative: một cấu trúc hợp lệ bị bỏ sót khỏi phạm vi rule.

**Câu 10.** `javac --release 14 TextBlockIndentDemo.java` nên thành công không?  
**Đáp án:** Không. Text blocks stable từ Java 15; source dùng text blocks không hợp lệ ở language level 14.

**Câu 11.** Vì sao cần hai bộ test: source tốt và source cố ý vi phạm rule?  
**Đáp án:** Source tốt kiểm tra false positives, source sai kiểm tra rule có thật sự phát hiện vấn đề và đã scan file hay chưa.

**Câu 12.** Trong CI nên dùng formatter với `--dry-run` để làm gì?  
**Đáp án:** Kiểm tra trạng thái format mà không ghi sửa source; kết hợp exit status để fail build khi lệch style.

**Câu 13.** Có thể suy từ tên `com.sun.source.tree` rằng đây là private compiler internals không?  
**Đáp án:** Không. Đây là Tree API được tài liệu hóa thuộc module `jdk.compiler`, khác các implementation internals `com.sun.tools.javac.*`.

**Câu 14.** “Nâng JDK máy build lên bản mới” đã đủ để plugin AST cũ hiểu syntax mới?  
**Đáp án:** Không. Plugin cần được build/test với node kinds và rules tương ứng, đồng thời công cụ parser phải hỗ trợ grammar.

## Nguồn tham khảo chính thức và công cụ

- **Oracle Java SE 17 — `com.sun.source.tree`:** các interface biểu diễn AST của Java source, từ `CompilationUnitTree` đến `SwitchExpressionTree` và `YieldTree`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/tree/package-summary.html
- **Oracle Java SE 25 — `Tree.Kind`:** các kinds được hỗ trợ, gồm `SWITCH_EXPRESSION`, `YIELD`, `RECORD`, `BINDING_PATTERN` và `STRING_LITERAL`: https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/tree/Tree.Kind.html
- **Oracle Java SE 17 — `JavacTask`:** các bước `parse()`, `analyze()` của compiler task: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/JavacTask.html
- **Oracle Java SE 17 — `TreePathScanner`:** duyệt cây và quản lý đường dẫn node: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/TreePathScanner.html
- **Oracle Java SE 17 — `ToolProvider`:** hệ thống cung cấp Java compiler; `getSystemJavaCompiler()` có thể trả null: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html
- **Oracle Java SE 17 — `JavaCompiler` và `DiagnosticCollector`:** compiler API và chẩn đoán lỗi: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html
- **OpenJDK JEP 361 — Switch Expressions** (final JDK 14): https://openjdk.org/jeps/361
- **OpenJDK JEP 378 — Text Blocks** (final JDK 15): https://openjdk.org/jeps/378
- **OpenJDK JEP 394 — Pattern Matching for instanceof** (final JDK 16): https://openjdk.org/jeps/394
- **OpenJDK JEP 395 — Records** (final JDK 16): https://openjdk.org/jeps/395
- **OpenJDK JEP 409 — Sealed Classes** (final JDK 17): https://openjdk.org/jeps/409
- **google-java-format — README:** công cụ định dạng, yêu cầu runtime/compiler parser, `--dry-run` và `--set-exit-if-changed`: https://github.com/google/google-java-format/blob/master/README.md
- **Checkstyle — tài liệu chính thức:** bảng yêu cầu JRE/JDK và mức hỗ trợ Java language syntax, giới hạn parser/rules: https://checkstyle.org/
- **Apache Maven — Guide to Targeting a Java Version:** dùng `maven.compiler.release` / `--release` để kiểm tra syntax, class file và API target: https://maven.apache.org/guides/mini/guide-java-target.html
# Giới hạn của cây cú pháp mới parse và rủi ro khi phụ thuộc API nội bộ của javac

Một chương trình Java trải qua nhiều công việc khác nhau khi được biên dịch: đọc token, xây dựng cây cú pháp (*parse*), ghi nhận khai báo, phân giải tên, kiểm tra kiểu, phân tích luồng điều khiển và cuối cùng sinh bytecode. **Cây cú pháp ngay sau `parse()` mới cho biết chương trình được viết như thế nào về mặt cấu trúc; nó chưa phải bản chứng nhận rằng chương trình đúng ngữ nghĩa.**

Điều này đặc biệt quan trọng đối với công cụ phân tích mã nguồn: IDE, linter, refactoring, code generator hay plugin compiler. Nếu nhìn thấy một `IdentifierTree` tên `value` rồi kết luận ngay đó là trường nào, kiểu gì hoặc lời gọi overload nào, công cụ đã đi vượt những gì giai đoạn parse bảo đảm.

Một rủi ro khác là dựa trực tiếp vào các lớp triển khai như `com.sun.tools.javac.tree.JCTree`, `com.sun.tools.javac.code.Symbol`, `com.sun.tools.javac.comp.Attr` hoặc `com.sun.tools.javac.util.Context`. Chúng tiện cho việc nghiên cứu internals của một bản OpenJDK, nhưng **không phải hợp đồng API ứng dụng ổn định**. Thay đổi JDK, module encapsulation hay cách compiler xử lý cây có thể làm plugin hỏng.

Bài học này phân biệt rành mạch *syntax* với *semantics*, minh họa hai pha `JavacTask.parse()`/`analyze()` bằng Java 17+, giới thiệu API công bố trong `com.sun.source.tree`/`com.sun.source.util` và cách tránh khóa công cụ vào internals.

## 1. Từ mã nguồn tới AST: parse thực sự làm gì?

Xét source hợp lệ về cú pháp:

```java
package sample;

public class Demo {
    public int twice(int number) {
        return number * 2;
    }
}
```

Parser có thể nhận diện những cấu trúc như:

- Một `CompilationUnitTree` với khai báo package `sample`.
- Một `ClassTree` tên `Demo`.
- Một `MethodTree` tên `twice` với kiểu trả về ghi trong source là `int`.
- Một tham số `VariableTree` tên `number`.
- Một `ReturnTree` chứa `BinaryTree` biểu diễn phép nhân.
- Hai toán hạng, trong đó tên `number` được biểu diễn bằng cấu trúc cú pháp phù hợp.

Ví dụ sơ đồ khái niệm:

```text
CompilationUnitTree
└── ClassTree: Demo
    └── MethodTree: twice
        ├── return type syntax: int
        ├── parameter syntax: int number
        └── ReturnTree
            └── BinaryTree: MULTIPLY
                ├── IdentifierTree: number
                └── LiteralTree: 2
```

Ở thời điểm này, cây mô tả **cú pháp đã nhận diện**, không tự cung cấp đầy đủ thông tin để xác nhận:

- Tham chiếu `number` đã gắn với `VariableElement` nào.
- Kiểu của mọi biểu thức khi xét generic inference, boxing, numeric promotion và overload.
- Một tên kiểu được import có tồn tại trên classpath/module path không.
- Quyền truy cập `private`, `protected`, module readability hoặc exports có hợp lệ không.
- Mọi đường đi có return, biến đã được gán trước khi đọc, exception có được xử lý không.
- Một method reference/lambda có functional interface đích phù hợp không.

Cần những bước sau parse để trả lời các câu hỏi đó. Parser không phải trình kiểm tra kiểu đầy đủ.

## 2. “Có AST” không đồng nghĩa “biên dịch thành công”

Đoạn sau **đúng cú pháp nhưng sai ngữ nghĩa**:

```java
class InvalidExample {
    MissingType field;
}
```

Parser vẫn có thể dựng `ClassTree` và `VariableTree` cho `field` với một nút kiểu viết là `MissingType`. Nhưng bước phân giải tên không tìm thấy `MissingType` và compiler báo lỗi.

Tương tự:

```java
class WrongAssignment {
    int value = "abc";
}
```

Parser nhận diện một biến `int value` và một string literal. Chỉ ở quá trình kiểm tra kiểu mới phát hiện `String` không gán được cho `int`.

Vì thế, nếu công cụ chỉ chạy `parse()` rồi in “source hợp lệ”, diễn đạt chính xác phải là “parser đã đọc được cấu trúc cú pháp ở mức có thể phân tích”. Không nên nói “code type-safe”, “compile pass” hay “chạy được”.

Ngược lại, với source sai cú pháp, parser của IDE/compiler có thể tạo một **cây phục hồi lỗi** (*error recovery tree*). API có `ErroneousTree` và `Tree.Kind.ERRONEOUS` để mô tả phần lỗi. Đừng giả định cứ có `CompilationUnitTree` là hoàn toàn không có syntax error; phải đọc diagnostics.

## 3. Những thông tin nào thuộc pha ngữ nghĩa?

| Câu hỏi | Chỉ có parse tree đã đủ? | Pha/cơ chế thường cần |
| --- | --- | --- |
| Trong source có khai báo lớp tên `Demo` không? | Có, với source được parse phù hợp | AST/`ClassTree` |
| Tên method viết trong source là gì? | Có | `MethodTree` |
| Biểu thức dùng operator nào? | Có | `BinaryTree` và `Tree.Kind` |
| `List` ở đây là `java.util.List` hay một class cùng tên khác? | Chưa | Imports, symbol resolution |
| `value` là biến cục bộ, field, parameter hay tên không tồn tại? | Chưa | Scope, enter/resolve/attribution |
| `add(3)` chọn overload nào? | Chưa | Overload resolution và conversions |
| `x + y` có type gì? | Chưa đủ trong trường hợp tổng quát | Type attribution |
| `return "x"` trong method trả `int` hợp lệ không? | Chưa | Type checking |
| `var item = factory()` được suy ra kiểu gì? | Chưa | Type inference và target typing |
| Lambda `x -> x.length()` hợp lệ với target nào? | Chưa | Target functional interface |
| Method có thể thiếu return/biến chưa definite assignment? | Chưa | Control/data-flow checking |
| Một class có được sinh bytecode thành công? | Chưa | Các bước semantic/flow/generation |
| Một identifier đã gắn với `Element` nào? | Không bảo đảm chỉ sau parse | `Trees.getElement` sau pha phân tích phù hợp |

Một AST có thể chứa `MethodInvocationTree` và tên method, nhưng **không có nghĩa** nó đã biết chính xác `ExecutableElement` mà compiler sẽ chọn. Nếu lớp có overload, kế thừa hoặc generic method, không được tự giải quyết lời gọi bằng cách so tên chuỗi.

### Ví dụ về cùng cú pháp nhưng khác ngữ nghĩa

```java
void use(String x) {}
void use(Object x) {}

void caller() {
    use("hi");
}
```

Đây là snippet trong một class, không phải file Java độc lập. AST biểu diễn một lần gọi `use("hi")`; sau khi phân giải overload, compiler chọn `use(String)`. Nếu chỉ nhìn tên `use` và có hai khai báo, không thể chọn theo quy tắc “phương thức nào được viết trước”.

## 4. API công khai của JDK cho phân tích cây

Các package nên ưu tiên cho công cụ dựa trên `javac`:

- `com.sun.source.tree`: tập **giao diện AST** như `Tree`, `CompilationUnitTree`, `ClassTree`, `MethodTree`, `IdentifierTree`, `BinaryTree`, `ErroneousTree`.
- `com.sun.source.util`: `JavacTask`, `TreeScanner`, `TreePathScanner`, `TreePath`, `Trees` và các tiện ích liên hệ AST với ngữ nghĩa.
- `javax.tools`: `JavaCompiler`, `ToolProvider`, `JavaFileObject`, `DiagnosticCollector`, `StandardJavaFileManager`.
- `javax.lang.model.element` và `javax.lang.model.type`: kiểu trừu tượng `Element`/`TypeMirror` để làm việc với khai báo và type sau khi ngữ nghĩa đã có.

**Phân biệt tiền tố `com.sun`:** `com.sun.source.tree` và `com.sun.source.util` là **Tree API được tài liệu hóa của JDK** trong module `jdk.compiler`. Chúng không giống các lớp `com.sun.tools.javac.*` thuộc phần implementation nội bộ. Tuy vậy, `com.sun.source.*` gắn với tính năng compiler của JDK, không phải lời hứa mọi compiler Java bên thứ ba đều hỗ trợ chính xác cách tích hợp như `javac`.

Đối với nhu cầu chỉ biên dịch tệp và đọc lỗi, `javax.tools` thuộc Java Compiler API chuẩn thường đủ; chỉ dùng Tree API khi thật sự cần duyệt cú pháp. Nếu cần chính xác element/type, phối hợp Tree API với `javax.lang.model` thay vì cast xuống internal `Symbol`.

## 5. Ví dụ hoàn chỉnh Java 17+: parse trước, analyze sau

Ví dụ này được biên dịch/chạy độc lập bằng JDK 21 với target Java 17. Nó tạo Java source **trong bộ nhớ**, parse AST, rồi gọi analyze để lấy symbol của method.

Lưu tệp **`AstPhaseDemo.java`**:

```java
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import javax.lang.model.element.Element;
import javax.lang.model.element.ExecutableElement;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;
import com.sun.source.tree.ClassTree;
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.MethodTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.TreePath;
import com.sun.source.util.Trees;

public class AstPhaseDemo {
    static final class Source extends SimpleJavaFileObject {
        private final String code;

        Source(String name, String code) {
            super(URI.create("string:///"
                    + name.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    public static void main(String[] args) throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler required");
        }

        DiagnosticCollector<JavaFileObject> ds =
                new DiagnosticCollector<>();

        String source = """
                package sample;
                public class Demo {
                    public int twice(int number) { return number * 2; }
                }
                """;

        try (StandardJavaFileManager fm =
                     compiler.getStandardFileManager(
                             ds, Locale.ROOT, StandardCharsets.UTF_8)) {

            JavacTask task = (JavacTask) compiler.getTask(
                    null, fm, ds,
                    List.of("--release", "17", "-proc:none"),
                    null, List.of(new Source("sample.Demo", source)));

            List<CompilationUnitTree> units = new ArrayList<>();
            for (CompilationUnitTree u : task.parse()) {
                units.add(u);
            }

            ClassTree clazz =
                    (ClassTree) units.get(0).getTypeDecls().get(0);
            MethodTree method = clazz.getMembers().stream()
                    .filter(m -> m instanceof MethodTree)
                    .map(m -> (MethodTree) m)
                    .filter(m -> m.getName().contentEquals("twice"))
                    .findFirst()
                    .orElseThrow();

            // Thông tin cú pháp, lấy ngay sau parse().
            System.out.println("parsedClass=" + clazz.getSimpleName());
            System.out.println("parsedMethod=" + method.getName());

            // Kích hoạt phân tích ngữ nghĩa.
            task.analyze();

            // Liên hệ nút AST với ký hiệu được compiler phân giải.
            Trees trees = Trees.instance(task);
            TreePath path = TreePath.getPath(units.get(0), method);
            Element element = trees.getElement(path);

            System.out.println("resolvedKind=" + element.getKind());
            System.out.println("returnType="
                    + ((ExecutableElement) element).getReturnType());

            long errors = ds.getDiagnostics().stream()
                    .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
                    .count();
            System.out.println("errors=" + errors);
        }
    }
}
```

Biên dịch/chạy từ thư mục chứa file:

```bash
javac --release 17 -encoding UTF-8 AstPhaseDemo.java
java AstPhaseDemo
```

Stdout chính xác trên JDK 21:

```text
parsedClass=Demo
parsedMethod=twice
resolvedKind=METHOD
returnType=int
errors=0
```

Trong lab này, `parse()` cung cấp một `ClassTree` và `MethodTree` để ta đọc tên khai báo; **không cần tự đào vào `JCTree`**. Sau `task.analyze()`, ví dụ dùng `Trees.getElement(TreePath)` để lấy `Element` liên kết với method và `ExecutableElement.getReturnType()` để lấy return type.

`task.analyze()` thực hiện phân tích ngữ nghĩa của task; ví dụ không gọi `generate()` và không cố sinh file `.class`. `-proc:none` tắt annotation processing để kết quả không phụ thuộc processor tình cờ có trên đường tìm kiếm.

Ví dụ trên biết trước input chứa đúng một top-level class hợp lệ với method `twice`. Một công cụ tổng quát cần kiểm tra type của từng node, khả năng collection rỗng, diagnostics và tình huống có nhiều compilation units thay vì cast `getTypeDecls().get(0)` một cách mặc định.

## 6. Ví dụ thứ hai: parse được nhưng analyze phát hiện lỗi

Để trực tiếp kiểm chứng khác biệt, lưu tệp **`AstErrorPhaseDemo.java`**:

```java
import java.io.IOException;
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
import com.sun.source.util.JavacTask;

public class AstErrorPhaseDemo {
    static final class Source extends SimpleJavaFileObject {
        private final String code;

        Source() {
            super(URI.create("string:///sample/Bad.java"), Kind.SOURCE);
            code = "package sample; public class Bad { MissingType field; }";
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    public static void main(String[] args) throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler required");
        }

        DiagnosticCollector<JavaFileObject> ds =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager fm =
                     compiler.getStandardFileManager(
                             ds, Locale.ROOT, StandardCharsets.UTF_8)) {
            JavacTask task = (JavacTask) compiler.getTask(
                    null, fm, ds,
                    List.of("--release", "17", "-proc:none"),
                    null, List.of(new Source()));

            int units = 0;
            for (CompilationUnitTree unit : task.parse()) {
                units++;
            }
            System.out.println("parsedUnits=" + units);

            task.analyze();

            boolean semanticError = ds.getDiagnostics().stream()
                    .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR);
            System.out.println("semanticError=" + semanticError);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 -encoding UTF-8 AstErrorPhaseDemo.java
java AstErrorPhaseDemo
```

Stdout đã kiểm tra trên JDK 21:

```text
parsedUnits=1
semanticError=true
```

Chương trình `AstErrorPhaseDemo` tự biên dịch thành công; **nguồn `Bad` bên trong bộ nhớ** có cây cú pháp nhưng không được compiler giải quyết kiểu `MissingType`. Dữ liệu diagnostic được thu vào `DiagnosticCollector` nên không phải phụ thuộc nguyên văn thông báo như `cannot find symbol`.

Đoạn code cố tình in **boolean có error** thay vì một số lượng lỗi cố định vì mỗi compiler và phiên bản có thể báo nhiều thông tin ngữ nghĩa khác nhau. Kết luận ổn định ở đây là: **AST có thể tồn tại cùng với lỗi biên dịch**.

## 7. Vì sao không truy cập Element quá sớm?

`Trees.getElement(TreePath)` là cầu nối từ cú pháp tới **declaration element**. Nhưng ngay sau `parse()`, compiler có thể chưa ghi nhận đầy đủ symbol hoặc chưa thực hiện attribution cho node.

Các điểm phải nhớ:

- `getElement(path)` có thể trả **`null`** nếu element không sẵn có.
- Với path tới loại node không thể có element tương ứng, API có thể ném **`IllegalArgumentException`**.
- `getTypeMirror(path)` cũng có thể trả `null` hoặc ném `IllegalArgumentException` nếu path không phù hợp.
- Với chương trình sai kiểu, có thể gặp `ErrorType` hoặc thông tin chưa đầy đủ; đừng coi mọi `TypeMirror` đều là `DeclaredType` có thể cast an toàn.
- `analyze()` giúp công cụ có thông tin ngữ nghĩa trong những tình huống compiler có thể phân tích. Nó không biến source sai thành đúng và không bảo đảm mọi node đều có `Element`/`TypeMirror`.

Do đó, công cụ phân tích phải thiết kế hai chế độ hoạt động khác nhau: **syntax-only mode** cho parse cây và **semantic-aware mode** khi cần symbols/types. Trong semantic-aware mode, gọi bước phân tích phù hợp, đọc diagnostic và kiểm tra `null`/kind trước khi truy cập sâu.

Tránh gọi phương thức `getTypeMirror` trên mọi node rồi suy ra rằng mọi node đều có một type. Ví dụ một node biểu diễn câu lệnh `return`, phần tử package hoặc construct cú pháp khác không phải lúc nào cũng có type mirror theo nghĩa mong đợi của người lập trình.

## 8. Duyệt cây bằng TreePathScanner thay vì lục field nội bộ

`TreeScanner<R,P>` cho phép duyệt AST; `TreePathScanner<R,P>` còn duy trì **đường đi hiện tại** đến node. Điều này quan trọng vì `Trees.getElement` và `Trees.getTypeMirror` nhận `TreePath`, không chỉ một nút `Tree` rời rạc.

Ví dụ snippet dùng sau khi `task.analyze()`:

```java
Trees trees = Trees.instance(task);

new TreePathScanner<Void, Void>() {
    @Override
    public Void visitIdentifier(
            com.sun.source.tree.IdentifierTree node, Void ignored) {

        TreePath path = getCurrentPath();
        Element symbol = trees.getElement(path);

        if (symbol != null) {
            System.out.println(node.getName()
                    + " -> " + symbol.getKind());
        }
        return super.visitIdentifier(node, ignored);
    }
}.scan(units.get(0), null);
```

Đây là **snippet**, không phải file độc lập; nó giả định có `task`, `units`, và import `Trees`, `TreePathScanner`, `TreePath`, `Element`. Không dùng output của snippet làm stdout cố định vì số identifier, những node sinh bổ sung và thứ tự duyệt có thể khác tùy source/JDK.

Lưu ý:

- Một `IdentifierTree` thể hiện tên cú pháp; `Element` thể hiện khai báo sau khi phân giải.
- Một `MemberSelectTree` như `System.out` không nhất thiết là `IdentifierTree` đơn; visitor cần xử lý đúng các loại node.
- `MethodInvocationTree` cần phân giải overload ở bước semantic; không so tên chuỗi để tự đoán declaration.
- Khi cần tên method đã được phân giải, có thể lấy `Element` tại `TreePath` thích hợp và kiểm tra `ElementKind.METHOD`.
- `TreePathScanner` hữu ích cho các công cụ muốn báo vị trí chính xác, nhưng vẫn phải kiểm tra nguồn có lỗi hay chưa.

Nếu chỉ cần thống kê cú pháp (số khai báo method, số `if`, số vòng lặp), `TreeScanner` hoặc `TreePathScanner` sau parse thường đủ. Nếu cần “biến này là field hay local”, phải bước qua ranh giới sang semantic-aware processing.

## 9. SourcePositions không biến AST thành nguyên bản source

`Trees.getSourcePositions()` hỗ trợ lấy offset bắt đầu/kết thúc của một node trong compilation unit. `CompilationUnitTree.getLineMap()` có thể giúp chuyển offset sang dòng/cột.

Ví dụ khái niệm:

```java
var positions = trees.getSourcePositions();
long start = positions.getStartPosition(unit, node);
long end = positions.getEndPosition(unit, node);
```

Đây là snippet với biến `unit` và `node` tương ứng kiểu `CompilationUnitTree`/`Tree`. Một vị trí không sẵn có có thể được biểu diễn bằng giá trị âm/`Diagnostic.NOPOS`, vì vậy công cụ phải kiểm tra trước khi cắt chuỗi nguồn.

Cần tách ba lớp:

1. **AST:** cấu trúc cú pháp như method, expression, statement.
2. **Source text:** khoảng trắng, xuống dòng, dấu ngoặc, comment và mọi ký tự người lập trình đã viết.
3. **Semantic model:** symbol, type, scope, resolved overload và các thông tin kiểm tra.

Một AST không nhất thiết lưu đầy đủ mọi **comment** hay định dạng của source. `DocTrees` có API chuyên biệt cho Javadoc; nó không đồng nghĩa có thể bảo toàn mọi comment tùy ý. Nếu muốn formatter hoặc refactoring giữ nguyên trivia (comment/whitespace), cần giữ source text gốc và thiết kế phép sửa dựa trên vị trí, hoặc sử dụng parser/công cụ source-preserving phù hợp.

Không suy ra rằng `tree.toString()` sẽ khôi phục 100% byte nguồn ban đầu. `toString()` có thể cho biểu diễn đọc được nhưng không phải hợp đồng round-trip formatter.

## 10. AST có thể thay đổi khi compiler chuyển pha

Khi compiler đi qua enter, attribution, flow và lowering, implementation có thể bổ sung hoặc biến đổi cấu trúc nội bộ phục vụ sinh mã.

Vì vậy công cụ không nên giả định:

- Một reference tới `JCTree` hoặc list node sẽ bất biến từ parse tới generate.
- Tất cả node nội bộ đã có `type` và `sym` ngay sau parse.
- Một node được tạo trong pass trước vẫn chắc chắn hiện diện cùng identity ở pass sau.
- Mọi class/constructor/method tổng hợp đều xuất hiện ở AST như một dòng source người dùng đã viết.
- Số lượng/loại node nội bộ của `javac` bằng nhau giữa mọi JDK.

Giao diện `com.sun.source.tree` giúp tránh thao tác trực tiếp vào nhiều field nội bộ. Tuy vậy, một chương trình phân tích có trạng thái vẫn nên quản lý phạm vi của `JavacTask` và `TreePath`, không cất giữ reference tới AST như cache vĩnh viễn độc lập với source/compilation.

Nếu cần chạy nhiều lượt phân tích cho các phiên bản source khác nhau, hãy tạo compilation task mới cho mỗi lượt và bỏ cache semantic gắn với task cũ hoặc có cơ chế invalidation rõ ràng.

## 11. Vì sao com.sun.tools.javac.* rủi ro?

Các lớp như:

- `com.sun.tools.javac.tree.JCTree`, `JCTree.JCMethodDecl`, `TreeMaker`;
- `com.sun.tools.javac.code.Symbol`, `Type`;
- `com.sun.tools.javac.comp.Enter`, `Attr`, `Resolve`;
- `com.sun.tools.javac.util.Context`, `Names`;
- các cấu trúc và visitor khác trong implementation `javac`

có thể rất hấp dẫn vì cho phép đọc hoặc thay đổi field trực tiếp. Nhưng đây là **implementation details**, không phải API ổn định dành cho ứng dụng. Tài liệu `javac` của OpenJDK nêu rõ các package bắt đầu bằng `com.sun.tools.javac` ngoài các API được chỉ định riêng là nội bộ và có thể thay đổi bất cứ lúc nào.

Hậu quả điển hình:

| Cách phụ thuộc | Rủi ro |
| --- | --- |
| Cast `Tree` sang `JCTree` | Không portable sang compiler khác; gặp thay đổi internal class/AST layout |
| Đọc `JCExpression.type` hoặc symbol field trước attribution | Giá trị có thể `null` hoặc chưa có nghĩa ngữ nghĩa mong đợi |
| Tạo node bằng `TreeMaker` rồi chèn vào cây compiler | Cần tái thiết lập owner/symbol/type/position; dễ phá invariants của compiler |
| Gọi trực tiếp `Enter`/`Attr`/`Resolve` | Phụ thuộc thứ tự pha, signature, internal state `Context` |
| Dùng reflection vào private fields | Bị JPMS strong encapsulation; cần quyền mở package và vẫn rủi ro phiên bản |
| Dùng `--add-exports` như thể nó ổn định hóa API | Chỉ nới quyền truy cập; không giữ nguyên method/field/behavior sau nâng JDK |
| Giữ cache symbol/type qua các compilation task | Symbol thuộc context/task và có thể stale, dẫn tới phân giải sai |
| Dùng exception/diagnostic text nội bộ để nhận diện lỗi | Message/code có thể thay đổi, và đường lỗi không được thiết kế làm protocol |

Nếu một plugin thực sự cần biến đổi AST ở tầng compiler nội bộ, đó là lựa chọn kỹ thuật **compiler-specific**, đòi hỏi kiểm thử theo ma trận phiên bản JDK, quản lý tương thích và kế hoạch nâng cấp. Không nên ngầm trình bày nó như một phần của Java Language Specification.

## 12. JPMS: có quyền truy cập không có nghĩa API được bảo đảm

Từ Java 9, module `jdk.compiler` đóng gói các package của compiler. Những package Tree API được export theo descriptor thích hợp; nhiều package nội bộ `com.sun.tools.javac.*` không được export thông thường sang ứng dụng.

Một công cụ cũ phụ thuộc `JCTree` có thể gặp lỗi truy cập module ở compile time hoặc runtime. Với mục đích migration, có thể gặp cờ:

```text
--add-exports jdk.compiler/com.sun.tools.javac.tree=ALL-UNNAMED
```

Dòng này **chỉ minh họa option** khi một ứng dụng chạy trên classpath cần truy cập public types trong package nội bộ đó; đây không phải câu lệnh `javac`/`java` độc lập. Nếu dùng reflection sâu vào thành viên không công khai, cấu hình có thể liên quan `--add-opens` ở runtime.

Hai cờ có ý nghĩa khác nhau:

- `--add-exports`: mở rộng export của một package tới những module được chỉ định, giúp truy cập theo ngữ nghĩa Java tới public types/members phù hợp.
- `--add-opens`: mở package cho deep reflection tới module đích theo những điều kiện được quy định.

**Cả hai không bảo đảm tương thích mã nguồn/nhị phân** khi internal class hoặc cấu trúc thay đổi. Chúng cũng không biến API nội bộ thành public supported API.

Nên ưu tiên code hoạt động không cần `--add-exports`/`--add-opens`, nhất là ở công cụ dùng chung nhiều JDK. Khi cờ ngoại lệ là bắt buộc, cần ghi rõ version hỗ trợ và chỉ áp dụng phạm vi package/module tối thiểu.

## 13. Lựa chọn API theo nhu cầu thật

| Mục tiêu | Lựa chọn phù hợp trước tiên |
| --- | --- |
| Chỉ compile file và nhận lỗi | `javax.tools.JavaCompiler` + `DiagnosticCollector` |
| Đếm cấu trúc cú pháp | `JavacTask.parse()` + `TreeScanner`/`TreePathScanner` |
| Lấy tên class/method như trong source | `ClassTree`/`MethodTree` |
| Biết identifier/method trỏ tới khai báo nào | `JavacTask.analyze()` + `Trees.getElement(TreePath)` |
| Biết type của biểu thức sau phân tích | `Trees.getTypeMirror(TreePath)` + `javax.lang.model.type` |
| Duyệt declarations, generics và member types | `javax.lang.model.element` + `TypeMirror`/`Elements`/`Types` |
| Viết annotation processor | `javax.annotation.processing`, `RoundEnvironment`, `Filer`, `Messager` |
| Đọc Javadoc dưới dạng cây | `DocTrees` và các API doc-comment liên quan |
| Cần giữ comment/whitespace khi refactor | Giữ source gốc + source positions hoặc thư viện source-preserving |
| Thao tác trực tiếp compiler internals | Chỉ khi có nhu cầu bắt buộc, giới hạn phiên bản và kiểm thử nghiêm ngặt |

Không cần chuyển sang internal `Symbol` chỉ để lấy tên method, kiểu trả về hay loại phần tử. `ExecutableElement`, `TypeElement`, `VariableElement` và `TypeMirror` thường giải quyết những nhu cầu này ở mức API công bố.

## 14. Cẩn thận với lỗi nguồn và dữ liệu semantic không đầy đủ

Một linter chạy trên source người dùng khi đang gõ trong IDE cần chấp nhận code **chưa hoàn chỉnh**. Có thể xảy ra:

- Compilation unit chỉ parse được một phần hoặc có `ErroneousTree`.
- Một import chưa viết xong khiến symbol không phân giải được.
- Một expression chưa đủ context để inference có type phù hợp.
- Một element/type mirror không sẵn có hoặc là error type.
- Một diagnostic gắn với source nhưng không có line/column cụ thể.
- Một processor biến đổi/sinh source khiến tập compilation units thay đổi theo pha.
- Một classpath/module path bị thiếu khiến nhiều symbol có lỗi dây chuyền.

Tạo báo cáo theo nguyên tắc **best effort**:

1. Đọc toàn bộ diagnostics; phân biệt `ERROR`, `WARNING`, `NOTE`.
2. Không assert rằng `getElement(path)` luôn khác null.
3. Kiểm tra `ElementKind`/`TypeKind` trước khi cast.
4. Đối với lỗi chưa phân giải được, đánh dấu “unknown/unresolved” thay vì suy đoán kiểu.
5. Tránh lưu semantic result của một lần compile vào lần compile khác khi source hoặc dependency đã đổi.
6. Nếu công cụ sửa code, chỉ sửa node chắc chắn có source position đúng; tránh edit dựa trên AST phục hồi không ổn định.
7. Khi yêu cầu tính đúng tuyệt đối, không đưa ra kết luận semantic nếu compiler chưa hoàn tất bước thích hợp hoặc đã báo lỗi liên quan.

Lỗi lập trình phổ biến là sử dụng “không tìm thấy element” như bằng chứng “biến không được khai báo”. Kết quả `null` có thể đơn giản phản ánh *phase chưa sẵn sàng*, loại node không phù hợp hoặc môi trường compilation thiếu dependency.

## 15. Overload, generics và lambda là phép thử tốt cho ranh giới parse/analyze

### Overload

```java
static void send(Object value) {}
static void send(String value) {}

static void work() {
    send("ok");
}
```

AST chứa một `MethodInvocationTree` tên `send`. Pha semantic mới áp dụng overload resolution để chọn `send(String)`. Không dùng “method đầu tiên tìm thấy trong class” làm thuật toán phân giải.

### Generics và target typing

```java
List<String> names = java.util.Collections.emptyList();
```

Parser thấy một generic method invocation và một biến có kiểu `List<String>`. Compiler cần target typing và ràng buộc generic để chọn type argument tương thích. AST thuần không nên được xem là biểu diễn của “`T` đã suy thành `String`” nếu không có semantic model tương ứng.

### Lambda

```java
java.util.function.Function<String, Integer> f =
        s -> s.length();
```

AST chứa lambda với tham số `s`. Kiểu của `s` ở đây phụ thuộc functional interface đích. Parse riêng lambda không thể cho một kết luận typed đầy đủ về `s` nếu bỏ qua ngữ cảnh phép gán.

### Điều kiện truy cập

```java
package a;
public class Service {
    private void secret() {}
}
```

Một source khác có thể parse `service.secret()` như lời gọi method, nhưng chỉ trong ngữ cảnh class/module và quyền truy cập cụ thể compiler mới kết luận nó hợp lệ hay không.

Bốn ví dụ trong mục 15 là **snippets minh họa**, không phải bốn chương trình độc lập để chạy chung; chúng chỉ cho thấy cú pháp và ngữ nghĩa là hai tầng khác nhau.

## 16. Kiểm thử công cụ AST mà không bám vào implementation

Một bộ kiểm thử nên có:

- **Syntax-only cases:** class, method, field, nested class, record, switch, pattern (phù hợp `--release` đang dùng).
- **Semantic cases:** import trùng tên, shadowing, overload, generics, inheritance và quyền truy cập.
- **Invalid source cases:** sai cú pháp, sai kiểu, thiếu class, source chưa gõ xong.
- **Classpath/module path cases:** dependency có và không có, named module và package export.
- **Version cases:** compiler/JDK thực sự được công cụ tuyên bố hỗ trợ.

Điều gì nên được assert?

| Có thể kiểm thử bền hơn | Nên tránh kiểm thử exact nếu cần portable |
| --- | --- |
| `CompilationUnitTree` có class/method khai báo mong đợi | `JCTree` concrete class name/field layout |
| `ElementKind.METHOD` cho method đã phân giải | Nội bộ symbol id, compiler context identity |
| `ExecutableElement.getReturnType()` theo semantic | Text của một implementation-specific diagnostic |
| Có diagnostic kind `ERROR` khi nguồn sai kiểu | Số dấu `^` hoặc khoảng trắng trong stderr |
| Vị trí node hợp lệ theo contract và source | Vị trí byte/AST giữa mọi version mà không xét source |
| Kết quả build/task đúng | Thứ tự mọi callback nội bộ của compiler |

Một API công bố vẫn có những precondition và khác biệt phiên bản; kiểm thử nên dùng JDK/toolchain được hỗ trợ thay vì suy luận rằng bất kỳ compiler nào cũng chạy y nguyên.

## 17. Quy trình quyết định khi cần viết công cụ phân tích Java

1. **Xác định câu hỏi.** Cần xem cú pháp, symbol/type, hay bytecode?
2. Nếu chỉ cần cấu trúc, dùng `parse()` và Tree API, đừng trả giá cho kiến trúc bám internal symbol.
3. Nếu cần phân giải/kiểm tra type, cấu hình classpath/module path rồi dùng `analyze()` và `Trees`/`javax.lang.model`.
4. Xử lý diagnostics, `null`, `ErrorType` và source sai thay vì assume semantic hoàn chỉnh.
5. Truy cập source positions bằng public Tree utilities, và giữ source text để bảo toàn comment/whitespace.
6. Hạn chế tách/gắn node bằng cách cast `JCTree`; nếu phải biến đổi, đánh giá công cụ/library hỗ trợ rewrite và xác định contract.
7. Nếu một nhu cầu buộc dùng `com.sun.tools.javac.*`, công khai đó là compiler-specific; khóa phiên bản và có migration/test matrix.
8. Không dùng `--add-exports`/`--add-opens` làm lời hứa API nội bộ ổn định.
9. Kiểm tra output trên compiler/JDK thật (ví dụ JDK 17 và 21 khi có hỗ trợ), không chụp snapshot định dạng log.
10. Khi source thay đổi, khởi tạo task phù hợp và vô hiệu hóa cache symbols/AST cũ.

## 18. Bài tập tự kiểm tra

**Bài A — AST có bằng chứng type-safe không?** Parse `class X { MissingType x; }`. Nếu nhận `ClassTree`, có thể kết luận Java hợp lệ không?

**Đáp án:** Không. Parse xác định cấu trúc cú pháp; kiểm tra ngữ nghĩa không phân giải được `MissingType`.

**Bài B — tên method và overload.** Trong đoạn có hai overload `send(Object)`, `send(String)`, liệu `MethodInvocationTree` tự cho biết nên gọi overload nào không?

**Đáp án:** Không. Cần phân giải ngữ nghĩa theo kiểu đối số, conversion và độ đặc hiệu.

**Bài C — interface hay internal implementation?** Đọc tên method khai báo nên dùng `MethodTree.getName()` hay cast sang `JCTree.JCMethodDecl`?

**Đáp án:** Ưu tiên `MethodTree.getName()`. Nó là Tree API được tài liệu hóa, ít phụ thuộc implementation hơn.

**Bài D — lúc nào dùng getElement?** Vì sao không assume `Trees.getElement(TreePath)` luôn có `Element` sau `parse()`?

**Đáp án:** Symbol/attribution có thể chưa sẵn sàng, và API có thể trả `null` cho element không có. Chỉ truy vấn sau pha semantic phù hợp và kiểm tra kết quả.

**Bài E — có thể dùng --add-exports để “đóng băng” JCTree?**

**Đáp án:** Không. Nó mở quyền truy cập module trong ngữ cảnh chỉ định, không cấm OpenJDK thay đổi internal classes.

**Bài F — AST round-trip được không?** Có nên viết lại toàn bộ source từ `tree.toString()` rồi cam kết giữ nguyên comment/indentation không?

**Đáp án:** Không. AST không phải bản lưu đầy đủ byte-for-byte của source; cần source text và cơ chế bảo toàn trivia.

**Bài G — ví dụ runnable.** Chạy `AstPhaseDemo.java`; sau parse in hai tên gì, sau analyze in method kind/type gì?

**Đáp án:** `Demo`, `twice`; sau analyze là `METHOD` và `int`, không có diagnostic `ERROR`.

**Bài H — nguồn thiếu kiểu.** `AstErrorPhaseDemo` in `parsedUnits=1` và `semanticError=true`. Nó minh họa điều gì?

**Đáp án:** Một cây cú pháp có thể tồn tại trong khi source vẫn có lỗi ngữ nghĩa. Trạng thái parse không thay thế thành công của compiler.

## 19. Tổng kết và tài liệu chuẩn

Cây `parse()` mới chỉ trả lời **“source có cấu trúc cú pháp nào?”**. Nó không tự trả lời đầy đủ **“tên đó là symbol nào, biểu thức có type gì, lời gọi hợp lệ không và bytecode có tạo được không?”**. Khi cần ngữ nghĩa, dùng `JavacTask.analyze()` và những API được tài liệu hóa như `Trees`, `TreePath`, `Element`, `TypeMirror`, đồng thời xử lý diagnostics và source chưa hợp lệ.

Cũng cần phân biệt **Tree API do JDK công bố** (`com.sun.source.*`) với **implementation internals** (`com.sun.tools.javac.*`). Phụ thuộc trực tiếp vào `JCTree`, `Symbol`, `Attr` hoặc `Context` có thể tạo coupling với phiên bản compiler và bị JPMS strong encapsulation. Các cờ nới quyền không biến internals thành stable API.

Tài liệu đối chiếu:

- [JDK 21 JavacTask](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/util/JavacTask.html) — các phương thức `parse`, `analyze`, `generate`.
- [JDK 21 Tree API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/tree/package-summary.html) — các interface mô hình cú pháp.
- [JDK 21 Trees](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/util/Trees.html) — `getElement`, `getTypeMirror`, `getSourcePositions` và semantics của kết quả có thể thiếu.
- [JDK 21 TreePathScanner](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/util/TreePathScanner.html) — duyệt cây và giữ path của node hiện tại.
- [JDK 21 JavaCompiler](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaCompiler.html) — compiler task và diagnostic listener.
- [JDK 21 javac manual](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html) — những API được hỗ trợ và cảnh báo nội bộ `com.sun.tools.javac.*`.
- [Oracle JDK Migration Guide](https://docs.oracle.com/en/java/javase/21/migrate/migrating-jdk-8-later-jdk-releases.html) — module encapsulation, `--add-exports`/`--add-opens` và rủi ro phụ thuộc internal APIs.

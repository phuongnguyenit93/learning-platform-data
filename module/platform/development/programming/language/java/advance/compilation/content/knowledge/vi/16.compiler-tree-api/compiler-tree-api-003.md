# Duyệt CompilationUnitTree bằng TreeScanner và TreePathScanner trong Java

## 1. Mục tiêu: đọc cấu trúc cú pháp Java mà không tự viết parser

Khi phát triển công cụ phân tích source Java — ví dụ kiểm kê method, tìm lời gọi API, rà soát quy tắc code hoặc thu thập vị trí khai báo — việc tìm chuỗi ký tự bằng regex không đủ tin cậy. Cùng một từ có thể xuất hiện trong comment, string literal, generic type, method call hoặc khai báo. **Abstract Syntax Tree (AST)** biểu diễn cấu trúc chương trình thành các node được phân loại.

Java Compiler Tree API trong module **`jdk.compiler`** cung cấp:
- `com.sun.source.tree.CompilationUnitTree`: node gốc của một compilation unit, thường tương ứng một Java source file; chứa package, imports, các khai báo cấp cao nhất và thông tin source.
- `com.sun.source.tree.Tree`: giao diện chung cho các node AST; `Tree.Kind` biểu thị loại node.
- `com.sun.source.util.TreeScanner<R,P>`: visitor duyệt đệ quy các node con và có thể truyền trạng thái `P`, trả kết quả `R`.
- `com.sun.source.util.TreePathScanner<R,P>`: kế thừa `TreeScanner`, đồng thời duy trì **đường đi từ compilation unit đến node hiện tại** trong quá trình duyệt.
- `com.sun.source.util.TreePath`: một node cộng với chuỗi tổ tiên trong AST.
- `com.sun.source.util.Trees` và `SourcePositions`: cung cấp vị trí source và cầu nối tới mô hình symbol/type của compiler khi giai đoạn phân tích đã đủ.

**Phân biệt trọng tâm:** `TreeScanner` đủ khi bạn muốn đếm, duyệt và kiểm tra node theo cấu trúc. `TreePathScanner` phù hợp khi quy tắc cần biết **node đang nằm trong lớp/method/biểu thức nào**, cần gọi `Trees.getElement(TreePath)`, `Trees.getTypeMirror(TreePath)` hoặc điều hướng tới tổ tiên.

Đây là API của trình biên dịch, không phải Java reflection: nó làm việc với **source/AST tại thời điểm phân tích**, kể cả khi chương trình chưa chạy. Các giao diện `com.sun.source.*` là API compiler được tài liệu hóa; khác với việc phụ thuộc trực tiếp những lớp nội bộ `com.sun.tools.javac.*` vốn có ràng buộc ổn định và đóng gói khác.

## 2. CompilationUnitTree là gì?

Một tệp source ví dụ:

~~~java
package demo;
class Sample {
    void greet() {
        System.out.println("hi");
    }
    int add(int a, int b) {
        return a + b;
    }
}
~~~

Mỗi compilation unit có thể chứa package declaration, imports, một hoặc nhiều type declarations và metadata nguồn. Dạng cây khái niệm:

~~~text
COMPILATION_UNIT
├── PACKAGE demo
└── CLASS Sample
    ├── METHOD greet
    │   └── BLOCK
    │       └── EXPRESSION_STATEMENT
    │           └── METHOD_INVOCATION System.out.println("hi")
    └── METHOD add
        └── BLOCK
            └── RETURN
                └── PLUS a + b
~~~

Sơ đồ cố ý rút gọn: AST thật có thể có thêm `MODIFIERS`, `IDENTIFIER`, `MEMBER_SELECT`, `PRIMITIVE_TYPE`, `VARIABLE`, `LITERAL` và các node khác. **Không** dùng sơ đồ để khẳng định một node chỉ có đúng một kiểu con hay cây luôn giữ nguyên giữa mọi bản `javac`.

Một số phương thức của `CompilationUnitTree`:

| Phương thức | Ý nghĩa |
| --- | --- |
| `getSourceFile()` | `JavaFileObject` biểu diễn source file đầu vào |
| `getPackageName()` | Cây tên package, có thể `null` với unnamed package |
| `getImports()` | Các `ImportTree` |
| `getTypeDecls()` | Các khai báo cấp cao nhất, kể cả các dạng module/source khác tùy ngữ cảnh |
| `getLineMap()` | Bản đồ vị trí ký tự trong source đến dòng/cột |
| `getModule()` | Thông tin module declaration khi compilation unit là `module-info.java` |
| `getPackage()` | `PackageTree` mô tả package declaration |

Một compilation unit không nhất thiết chỉ có một public class; file `package-info.java` hoặc `module-info.java` cũng cần được xử lý đúng theo loại nguồn. Tool không nên tự giả định “tệp có đúng một `ClassTree`”.

## 3. So sánh TreeScanner và TreePathScanner

| Tiêu chí | `TreeScanner<R,P>` | `TreePathScanner<R,P>` |
| --- | --- | --- |
| Duyệt con đệ quy bằng `visitXxx` | Có | Có, kế thừa TreeScanner |
| Duy trì `TreePath` hiện tại tự động | Không | Có, qua `getCurrentPath()` |
| Dùng để đếm class/method/invocation | Rất phù hợp | Cũng làm được |
| Cần xem node cha/ancestor | Tự truyền stack hoặc trạng thái | Dùng `getCurrentPath().getParentPath()` |
| Dùng `Trees.getElement(path)` | Phải tạo/tra path riêng | Thuận tiện hơn |
| Bắt đầu từ `CompilationUnitTree` | `scan(unit, state)` | `scan(unit, state)` |
| Bắt đầu từ một subtree với path đã có | Có thể scan Tree, nhưng không mang context | `scan(TreePath, state)` |
| Chi phí | Nhẹ hơn vì không luôn tạo/duy trì context path | Thường thêm chi phí path bookkeeping |
| Có thể dùng `R`, `P` generic | Có | Có |

Hai tham số generic:
- `R`: kiểu kết quả của visitor, ví dụ `Void`, `Integer`, tập dữ liệu.
- `P`: trạng thái truyền qua mỗi bước `scan` / `visit`, ví dụ cấu hình hoặc đối tượng collector.

Ví dụ `TreeScanner<Void, Void>` nghĩa là **không dùng return value hay tham số traversal**; kết quả được lưu trong field của scanner. Với công cụ cần tích lũy giá trị bằng `R`, phải hiểu cách `TreeScanner.reduce(R,R)` hợp nhất kết quả của các node; đừng mặc định mọi visitor tự cộng các giá trị con.

**Quy tắc quan trọng:** khi override `visitMethod`, `visitClass` hoặc `visitMethodInvocation`, thường gọi `super.visitXxx(node, p)` để tiếp tục duyệt node con. Nếu không gọi `super`, bạn đang **chặn việc đi xuống subtree đó**, có thể cố ý để tối ưu/prune nhưng cũng có thể làm mất kết quả phân tích.

## 4. Ví dụ Java 17+ đầy đủ: hai scanner trên cùng source

Ví dụ được kiểm chứng bằng `javac 24.0.2 --release 17` và chạy thành công. Chương trình Java này gọi Java Compiler API để **parse source**, không cần khởi chạy ứng dụng `Sample`.

Cấu trúc:

~~~text
project/
  Sample.java
  AstWalk.java
~~~

### 4.1. Tệp Sample.java — source cần phân tích

~~~java
package demo;
class Sample {
    void greet() {
        System.out.println("hi");
    }
    int add(int a, int b) {
        return a + b;
    }
}
~~~

Đây là source mà scanner sẽ đọc. Dòng đầu là `package demo;`; tên class là `Sample`, hai methods `greet` và `add`.

### 4.2. Tệp AstWalk.java — công cụ duyệt AST

~~~java
import com.sun.source.tree.ClassTree;
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.MethodInvocationTree;
import com.sun.source.tree.MethodTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.SourcePositions;
import com.sun.source.util.TreePath;
import com.sun.source.util.TreePathScanner;
import com.sun.source.util.TreeScanner;
import com.sun.source.util.Trees;

import java.io.IOException;
import java.nio.file.Path;
import java.util.List;
import javax.tools.JavaCompiler;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class AstWalk {
    private static final class CountScanner extends TreeScanner<Void, Void> {
        int classes;
        int methods;
        int calls;

        @Override
        public Void visitClass(ClassTree node, Void unused) {
            classes++;
            return super.visitClass(node, unused);
        }

        @Override
        public Void visitMethod(MethodTree node, Void unused) {
            methods++;
            return super.visitMethod(node, unused);
        }

        @Override
        public Void visitMethodInvocation(
                MethodInvocationTree node, Void unused) {
            calls++;
            return super.visitMethodInvocation(node, unused);
        }
    }

    private static final class ContextScanner
            extends TreePathScanner<Void, Void> {
        private final SourcePositions positions;

        ContextScanner(SourcePositions positions) {
            this.positions = positions;
        }

        @Override
        public Void visitMethod(MethodTree node, Void unused) {
            TreePath path = getCurrentPath();
            CompilationUnitTree unit = path.getCompilationUnit();

            long offset = positions.getStartPosition(unit, node);
            long line = offset < 0
                    ? -1
                    : unit.getLineMap().getLineNumber(offset);

            var parentKind =
                    path.getParentPath().getLeaf().getKind();

            System.out.println("METHOD " + node.getName()
                    + " parent=" + parentKind + " line=" + line);
            return super.visitMethod(node, unused);
        }

        @Override
        public Void visitMethodInvocation(
                MethodInvocationTree node, Void unused) {
            var parentKind = getCurrentPath()
                    .getParentPath().getLeaf().getKind();

            System.out.println("CALL " + node.getMethodSelect()
                    + " parent=" + parentKind);
            return super.visitMethodInvocation(node, unused);
        }
    }

    public static void main(String[] args) throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Run this tool on a JDK");
        }

        try (StandardJavaFileManager files =
                     compiler.getStandardFileManager(null, null, null)) {
            var inputs = files.getJavaFileObjects(
                    Path.of("Sample.java").toFile());

            JavacTask task = (JavacTask) compiler.getTask(
                    null, files, null,
                    List.of("--release", "17", "-proc:none"),
                    null, inputs);

            for (CompilationUnitTree unit : task.parse()) {
                System.out.println(
                        "UNIT " + unit.getSourceFile().getName());

                CountScanner counts = new CountScanner();
                counts.scan(unit, null);
                System.out.println("COUNT classes=" + counts.classes
                        + " methods=" + counts.methods
                        + " calls=" + counts.calls);

                SourcePositions positions =
                        Trees.instance(task).getSourcePositions();

                new ContextScanner(positions).scan(unit, null);
            }
        }
    }
}
~~~

Toàn bộ ví dụ sử dụng `com.sun.source.tree` và `com.sun.source.util` trong module `jdk.compiler`. Một ứng dụng chạy bằng JRE custom image cần bảo đảm module `jdk.compiler` có mặt; `ToolProvider.getSystemJavaCompiler()` có thể là `null` khi chạy trong runtime không có Java compiler.

Điểm khác biệt ngay trong code:
- `CountScanner` không dùng path. Nó cập nhật ba biến đếm khi gặp `ClassTree`, `MethodTree`, `MethodInvocationTree`.
- `ContextScanner` dùng `getCurrentPath()` để lấy **`CompilationUnitTree` và node cha của method/call**, không tự lưu một stack tổ tiên.
- `SourcePositions.getStartPosition(unit, node)` trả **offset** trong source; `LineMap.getLineNumber(offset)` đổi offset thành **dòng**, bắt đầu từ 1.
- Lệnh `task.parse()` nhận source do file manager cung cấp. Chương trình không gọi `task.analyze()` vì mục tiêu chỉ là **duyệt cấu trúc cú pháp**.
- `-proc:none` tắt annotation processing trong task mẫu, giúp kết quả độc lập với processor có thể có trên classpath.

### 4.3. Biên dịch và chạy

Từ thư mục `project` chứa hai tệp:

~~~bash
javac --release 17 -encoding UTF-8 AstWalk.java
java AstWalk
~~~

**Stdout chính xác** của ví dụ:

~~~text
UNIT Sample.java
COUNT classes=1 methods=2 calls=1
METHOD greet parent=CLASS line=3
CALL System.out.println parent=EXPRESSION_STATEMENT
METHOD add parent=CLASS line=6
~~~

Không có stdout từ `Sample.greet()`: công cụ chỉ **parse và scan**, không thực thi class được phân tích. Thứ tự visitor tuân theo traversal AST của source mẫu: method `greet` xuất hiện trước `add`.

Nếu thay `CountScanner` bằng `ContextScanner` ở chỗ đếm, chương trình vẫn đếm được, nhưng không cần trả giá cho path bookkeeping nếu công cụ chỉ cần tổng số node.

## 5. Từ source đến CompilationUnitTree: Compiler API

Cách tạo AST trong code mẫu gồm bốn bước:

1. `ToolProvider.getSystemJavaCompiler()` lấy `JavaCompiler` của môi trường có compiler.
2. `StandardJavaFileManager` biến `Sample.java` thành `JavaFileObject`.
3. `JavaCompiler.getTask(...)` tạo compile task; ép kiểu sang `JavacTask` để gọi `parse()`.
4. `task.parse()` trả các `CompilationUnitTree`; mỗi unit được đưa vào `scanner.scan(unit, null)`.

`JavacTask` có các pha quan trọng:

| Lời gọi | Tác dụng |
| --- | --- |
| `parse()` | Phân tích cú pháp, xây `CompilationUnitTree` |
| `analyze()` | Phân tích ngữ nghĩa, resolve symbols/type, thực hiện các pha compiler liên quan |
| `generate()` | Thực hiện bước sinh output class files sau các pha trước |
| `Trees.instance(task)` | Cung cấp cầu nối tới AST, vị trí và biểu diễn language model của compiler |

Không đồng nhất `task.parse()` với `javac` đã hoàn tất type-checking. AST có thể được tạo cả khi mã có tên kiểu chưa resolve; tùy loại lỗi, parser còn tạo `ErroneousTree`. Nếu rule cần kết luận “method này thật sự gọi phương thức nào” thì **chuỗi ký tự AST không đủ**, cần symbol resolution và type attribution phù hợp.

**Không gọi nhiều lần `parse()`, `analyze()` hoặc `generate()` trên cùng task một cách tùy tiện.** API task có state và thứ tự pha; tool nên quyết định rõ mình chỉ cần parse hay cần semantic analysis. Bất kỳ chẩn đoán nào được compiler phát ra đều cần được thu thập/quản lý trong ứng dụng thực.

Với source có nhiều file, có thể truyền nhiều `JavaFileObject` vào task và duyệt mỗi `CompilationUnitTree` riêng. Đừng giữ `TreePath` từ task này để kết luận symbol của task khác, vì classpath, compiler state và symbol table có thể khác.

## 6. TreeScanner: duyệt và tổng hợp node theo cú pháp

`TreeScanner<R,P>` implement `TreeVisitor<R,P>` và thực hiện traversal đệ quy. Các phương thức tiêu biểu:
- `visitCompilationUnit(CompilationUnitTree, P)`
- `visitClass(ClassTree, P)`
- `visitMethod(MethodTree, P)`
- `visitVariable(VariableTree, P)`
- `visitMethodInvocation(MethodInvocationTree, P)`
- `visitIdentifier(IdentifierTree, P)`
- `visitMemberSelect(MemberSelectTree, P)`
- `visitBlock(BlockTree, P)`

Một `TreeScanner` **không giữ TreePath hiện tại**. Nếu bạn viết rule cần biết “method invocation này nằm trong method nào”, cách đơn giản có thể là tự truyền context `P` từ visitor cha. Nhưng nếu rule liên quan nhiều ancestors, nested classes hoặc cần compiler symbols, `TreePathScanner` sẽ rõ hơn.

### 6.1. Dùng field để đếm

Ví dụ `CountScanner` ở phần 4 dùng `TreeScanner<Void, Void>` và ba fields. Một instance mới cho mỗi unit giúp tránh đếm tích lũy nhầm khi phân tích nhiều file. Nếu muốn cộng dồn toàn project, dùng collector chung có chủ ý, và định nghĩa rõ có đếm nested classes, anonymous classes hay generated constructs không.

Với một `ClassTree` có phương thức khai báo constructor, `visitMethod` cũng có thể đếm constructor (nó được biểu diễn qua `MethodTree`). Vì vậy không nên đặt nhãn “methods” mà không xác định có tính constructors hay không. Trong fixture phần 4, parse-only thấy hai phương thức viết tay, không cần suy luận về constructor ngầm định được chèn ở pha compiler sau.

### 6.2. `R`, `P` và `reduce`

Giả sử bạn muốn trả về số node thay vì field:

~~~java
// Phác thảo ý tưởng: không phải class Java độc lập.
TreeScanner<Integer, Void> scanner = new TreeScanner<>() {
    @Override
    public Integer reduce(Integer left, Integer right) {
        return (left == null ? 0 : left)
                + (right == null ? 0 : right);
    }

    @Override
    public Integer visitMethod(MethodTree node, Void p) {
        Integer children = super.visitMethod(node, p);
        return 1 + (children == null ? 0 : children);
    }
};
~~~

Cần hiểu rằng `TreeScanner` mặc định dùng `reduce` để kết hợp kết quả từ child visitors; với `R=Integer`, muốn cộng thật sự phải override `reduce`. Đây là lý do không thể giả định “`scan` trả tổng node” nếu chưa định nghĩa chiến lược tổng hợp.

### 6.3. Pruning có chủ đích

Đôi khi chỉ cần class signatures, không cần đọc method bodies:

~~~java
@Override
public Void visitMethod(MethodTree node, Void state) {
    recordSignature(node);
    return null; // không gọi super -> không duyệt node con
}
~~~

Đây là **đoạn minh họa trong một subclass scanner**, giả định `recordSignature` tồn tại. Nếu dùng mẫu này, các invocation nằm trong thân method **không bao giờ được visit**. Điều đó có thể là tối ưu hợp lệ hoặc một bug nếu mục tiêu là kiểm kê lời gọi API.

## 7. TreePathScanner: có thể biết node cha và ngữ cảnh

`TreePathScanner` kế thừa traversal của `TreeScanner` nhưng duy trì đường đi bằng `TreePath`. Trong một visitor:

~~~java
@Override
public Void visitMethodInvocation(
        MethodInvocationTree node, Void unused) {
    TreePath current = getCurrentPath();
    TreePath parent = current.getParentPath();

    // current.getLeaf() là invocation hiện tại.
    // parent.getLeaf() là node cha, nếu path có cha.
    // current.getCompilationUnit() trả root của source file.
    return super.visitMethodInvocation(node, unused);
}
~~~

Đoạn trên nằm **bên trong subclass TreePathScanner**, không phải chương trình độc lập.

`TreePath` có các thông tin quan trọng:

| Phương thức | Ý nghĩa |
| --- | --- |
| `getLeaf()` | Node AST được path hiện tại xác định |
| `getParentPath()` | Path lên node cha; có thể `null` tại root |
| `getCompilationUnit()` | Compilation unit ở gốc path |
| `TreePath.getPath(unit, node)` | Tìm path của một node trong unit, nếu node thực sự nằm trong tree đó |
| `TreePath.getPath(path, node)` | Tìm path của node thuộc subtree được chỉ bởi path |

**Trong visitor, `getCurrentPath()` chỉ hợp lệ khi scanner đang ở bên trong một lời gọi `scan` được khởi tạo đúng.** Đừng lưu tham chiếu scanner rồi gọi `getCurrentPath()` ngoài traversal để giả định nó vẫn trỏ tới node vừa duyệt.

### 7.1. Khởi tạo traversal đúng cách

Hai cách khởi đầu thường dùng:

~~~java
// Duyệt cả source file:
new ContextScanner(positions).scan(compilationUnit, null);
~~~

~~~java
// Duyệt subtree khi đã có TreePath hợp lệ:
new ContextScanner(positions).scan(existingPath, null);
~~~

Đây là **những dòng minh họa trong method**, các biến cần tồn tại. API của `TreePathScanner.scan(Tree, P)` cho phép bắt đầu trực tiếp bằng một `CompilationUnitTree` làm root. Khi muốn bắt đầu ở **một method hoặc expression cụ thể**, hãy dựng path hợp lệ từ root hoặc dùng `TreePath` đã có; không gọi `scan(arbitraryMethodTree, null)` trên scanner mới rồi mong tự biết ancestors.

Ví dụ tìm path từ root:

~~~java
TreePath path = TreePath.getPath(compilationUnit, methodTree);
if (path != null) {
    new ContextScanner(positions).scan(path, null);
}
~~~

Đoạn trên giả định `methodTree` là node thuộc chính `compilationUnit`. Việc tìm lại path bằng `getPath` có thể phải đi qua cây để xác định node; trong một lượt scan lớn, dùng `getCurrentPath()` thường hiệu quả hơn gọi `TreePath.getPath` lặp lại cho mọi node.

### 7.2. Đọc ancestor an toàn

Ví dụ xác định method enclosing gần nhất:

~~~java
// Phác thảo bên trong visitMethodInvocation:
TreePath p = getCurrentPath().getParentPath();
while (p != null && !(p.getLeaf() instanceof MethodTree)) {
    p = p.getParentPath();
}
String ownerMethod = p == null
        ? "<outside-method>"
        : ((MethodTree) p.getLeaf()).getName().toString();
~~~

Đoạn trên không phải source độc lập; `<outside-method>` là **một string literal trong Java code**. Vòng lặp phải kiểm tra `p != null` vì invocation có thể nằm trong field initializer hoặc initializer block chứ không phải method. Với nested classes, một method invocation có thể thuộc constructor, lambda hoặc anonymous class; định nghĩa “enclosing method” phải phù hợp yêu cầu của analyzer.

Điều quan trọng là **`TreePath` mô tả cấu trúc AST**, không tự mang nghĩa “symbol đó khai báo trong package nào” hoặc “method đã resolve overload nào”. Muốn câu trả lời semantic, cần `Trees` và compiler attribution.

## 8. Gắn kết AST với vị trí file, dòng và cột

Một rule có ích cần trả về **vị trí** để người dùng sửa code. Công thức:

1. `Trees.instance(task).getSourcePositions()` lấy `SourcePositions`.
2. `getStartPosition(unit, tree)` trả offset source của node.
3. `unit.getLineMap().getLineNumber(offset)` trả dòng.
4. `unit.getLineMap().getColumnNumber(offset)` trả cột.

Ví dụ:

~~~java
SourcePositions positions = Trees.instance(task).getSourcePositions();
long start = positions.getStartPosition(unit, node);
if (start >= 0 && unit.getLineMap() != null) {
    long line = unit.getLineMap().getLineNumber(start);
    long column = unit.getLineMap().getColumnNumber(start);
    System.out.println(line + ":" + column);
}
~~~

Đoạn trên **không phải chương trình độc lập**, vì `task`, `unit`, `node` cần có trước. Offset có thể là **`Diagnostic.NOPOS` (thường -1)** với cây không có vị trí nguồn xác định. Do đó phải kiểm tra trước khi chuyển sang dòng/cột. LineMap phản ánh vị trí source compiler đọc; không dùng `String.length()` trên một source đã thay đổi encoding hoặc newline rồi suy luận lại.

`getEndPosition(unit, node)` cũng hữu ích cho rule highlighting, nhưng không phải mọi node luôn có điểm cuối hợp lệ. Khi xây IDE plugin/code action, cần bảo toàn encoding, line endings và file identity.

Nếu chỉ cần tên file: `unit.getSourceFile().getName()`; trong môi trường file manager tùy biến, tên có thể là URI hoặc đường dẫn do JavaFileObject cung cấp, không nên luôn giả định filesystem path chuẩn.

## 9. TreePathScanner và phân giải symbol/type

`TreePathScanner` không tự thực hiện type-check. Nó **giữ context path** để các API như `Trees` có thể truy vấn thông tin ngữ nghĩa khi compiler đã làm những pha cần thiết.

Ví dụ khung tìm symbol:

~~~java
// Bên trong một TreePathScanner đang scan:
TreePath path = getCurrentPath();
Element symbol = trees.getElement(path);
TypeMirror type = trees.getTypeMirror(path);
~~~

Đây là **trích đoạn**, giả định đã import `javax.lang.model.element.Element`, `javax.lang.model.type.TypeMirror` và giữ đối tượng `Trees trees` hợp lệ từ `Trees.instance(task)`. Không có bảo đảm `symbol`/`type` hữu ích khi chỉ gọi `parse()`: nhiều kết quả cần attribution qua `task.analyze()`. Thậm chí sau analyze, chúng có thể là `null` hoặc biểu diễn lỗi với source không hợp lệ hoặc loại tree không tương ứng một symbol.

Đối chiếu các use case:

| Câu hỏi | Có thể chỉ parse + scan không? | Có thể cần semantic analysis? |
| --- | --- | --- |
| Một file có bao nhiêu khai báo `class`? | Có | Không bắt buộc |
| Method khai báo tên gì? | Có | Không bắt buộc |
| Có biểu thức gọi method `foo()` không? | Có, theo cú pháp | Nếu cần biết nó là `foo` nào thì có |
| Gọi `print` overload nào? | Không đủ | Có, cần symbol resolution |
| Biểu thức có kiểu `String` hay `Object`? | Không đủ | Có |
| Node này nằm trong method/class nào theo cú pháp? | Có, bằng TreePath | Không bắt buộc |
| Method reference trỏ đến khai báo nào? | Không đủ | Có |

**Không thay `TreePath` bằng tên chuỗi tự đoán** khi muốn kết luận gọi method thật. `a.toString()` và `b.toString()` giống nhau về tên, nhưng có thể resolve tới các declarations khác nhau.

### 9.1. Khi cần analyze

Với compiler task trong phần 4, có thể thiết kế pipeline tách hai pha:

~~~java
JavacTask task = /* task được tạo từ JavaCompiler */;
Iterable<? extends CompilationUnitTree> units = task.parse();
task.analyze();

// Sau đó duyệt các units và dùng Trees.instance(task)
// để truy vấn symbol/type khi phù hợp.
~~~

Đây là **pseudocode minh họa workflow**, không phải một tệp chạy độc lập. Lúc này cần xử lý diagnostics nếu source có lỗi. `analyze()` có thể trigger annotation processing và các bước compilation có liên quan theo task/options; nếu công cụ chỉ scan cú pháp thì không cần phân tích ngữ nghĩa.

Phân biệt **CompilationUnitTree** chứa AST với **Trees** là service truy cập thông tin compiler. `TreePathScanner` duyệt cây, `Trees` cung cấp bridge tới elements/types/source positions.

## 10. Trường hợp Java 17+: record, lambda, nested class và method references

Khi scan source thực tế, nhiều cấu trúc không nằm ở vị trí đơn giản như ví dụ:

~~~java
record Person(String name) {
    String upper() {
        return name.toUpperCase();
    }
}
~~~

Đây là source Java 17 hợp lệ nếu đặt trong file phù hợp. Nó nhắc rằng `ClassTree` không chỉ dành cho class truyền thống; các kind/type constructs như record và interface cần được xử lý theo `Tree.Kind` và visitor phù hợp với source level. Dự án dùng Java mới hơn có thể thêm cú pháp và tree kinds mới; khi dùng `javac --release 17`, chỉ cấu trúc hợp lệ của source 17 mới nên được giả định.

Ví dụ lambda:

~~~java
Runnable r = () -> System.out.println("hello");
~~~

Đây là một statement trong method, **không phải tệp độc lập**. Invocation `System.out.println` vẫn có thể được `visitMethodInvocation` nhìn thấy nếu scanner duyệt đệ quy qua `LambdaExpressionTree`. Nhưng để xác định method enclosing, bạn có thể phải xem path và lambda boundary thay vì giả định node cha trực tiếp là `MethodTree`.

Ví dụ method reference:

~~~java
java.util.function.Supplier<String> s = "x"::toUpperCase;
~~~

Nó dùng `MemberReferenceTree`, **không phải `MethodInvocationTree`**. Nếu viết analyzer “tất cả lời gọi” mà chỉ override `visitMethodInvocation`, bạn sẽ bỏ sót method references. Cần xác định chính xác những cú pháp cần thống kê.

Nested/local/anonymous classes có thể làm xuất hiện nhiều `ClassTree` trong một `CompilationUnitTree`, bao gồm class declarations bên trong phương thức hoặc trong biểu thức `new`. Nếu đếm số top-level classes thì nên kiểm tra path hoặc dùng `unit.getTypeDecls()` thay vì đếm tất cả `visitClass`.

## 11. Truy cập node cha: lỗi phổ biến nhất

Một số lỗi rất dễ gặp:

**Lỗi A — gọi `getCurrentPath()` trong TreeScanner.** Phương thức này thuộc `TreePathScanner`, không có trong `TreeScanner`. Nếu cần path, đổi subclass hoặc tự duy trì context có kiểm soát.

**Lỗi B — bắt đầu TreePathScanner từ một node con không có path.** Bắt đầu trực tiếp ở `CompilationUnitTree` hoặc `scan(TreePath, p)` từ path hợp lệ. Không giả định method tree tự biết compilation unit.

**Lỗi C — `getParentPath()` có thể `null`.** Với root compilation unit, không có ancestor. Khi viết quy tắc tổng quát, luôn guard `null`.

**Lỗi D — quên `super.visitXxx`.** Scanner bỏ qua descendants dưới node vừa override; số method calls hoặc expressions bị thiếu.

**Lỗi E — duyệt cùng subtree hai lần.** Nếu bạn gọi `scan(child,p)` thủ công rồi lại gọi `super.visitXxx`, child có thể được thăm lặp. Điều này gây double-counting ngay cả khi cây không có node trùng.

**Lỗi F — nhầm method invocation với method declaration.** `MethodTree` là khai báo, `MethodInvocationTree` là lời gọi, `NewClassTree` là khởi tạo object, `MemberReferenceTree` là method reference. Phân biệt đúng node kind.

**Lỗi G — nhầm text với symbol.** `node.getMethodSelect().toString()` là biểu diễn cú pháp, không chứng minh đã resolve đúng overload. Khi cần symbol, phải dùng compiler attribution và `Trees.getElement`.

**Lỗi H — đếm ngầm compiler-generated nodes.** Parser có thể không hiện constructor mặc định; các pha sau có thể biến đổi cây. Đừng so sánh máy móc số `MethodTree` giữa parse-only và các trạng thái compiler khác.

**Lỗi I — giữ TreePath khi task/AST đã thay đổi.** Path gắn với cây và compiler task cụ thể. Không cache path từ invocation cũ rồi ghép với task mới.

**Lỗi J — dựa vào source position tuyệt đối.** Offset có thể không xác định; kiểm tra `NOPOS`, file identity và `LineMap`.

## 12. Thiết kế công cụ phân tích nhiều file

Một analyzer dùng trong CI thường có pipeline:

~~~text
Input .java files + compiler options + source/module/classpath
                |
                v
JavaCompiler / JavacTask.parse()
                |
        CompilationUnitTree (mỗi file)
                |
                +--> TreeScanner: số liệu cấu trúc
                |
                +--> TreePathScanner: vị trí + ancestor context
                |
                +--> (nếu cần) task.analyze() + Trees:
                     symbols, types, source positions
                |
                v
          Diagnostic / JSON / report
~~~

Không được trộn số liệu syntactic và semantic mà không ghi rõ: “5 lời gọi method theo cú pháp” khác “5 lời gọi tới method signature X”. Một analyzer nên:
- Lấy `JavaFileObject` và compiler options từ đúng build configuration, tránh phân tích bằng JDK/source level khác CI.
- Tạo collector riêng hoặc quản lý trạng thái thống nhất cho nhiều units.
- Dùng `TreePathScanner` khi rule cần ancestor, tự ghi file + dòng + kind.
- Bảo vệ `null` và `NOPOS`, phân biệt parse errors với semantic errors.
- Xác định có phân tích generated sources, tests, module-info.java hoặc chỉ source sở hữu.
- Dùng parse-only cho quy tắc thuần cú pháp, analyze khi cần resolve symbols.
- Test với nested/local classes, lambda, method reference, record, annotation và source syntax error.
- Kiểm tra hiệu năng: không gọi `TreePath.getPath(unit,node)` lặp lại trên mọi node khi đã có path trong scanner.
- Không giả định AST/Tree.Kind của compiler JDK mới hoàn toàn trùng JDK cũ, đặc biệt với preview features.

### 12.1. Không làm biến đổi AST chỉ bằng scanner

`TreeScanner` và `TreePathScanner` là **visitor đọc/duyệt**; chúng không tự thực hiện code transformation. Nếu muốn phát sinh diagnostics, sử dụng `Trees.printMessage` hoặc `Messager` đúng ngữ cảnh (annotation processor có `Messager`), và xử lý output riêng. Nếu muốn sửa source, cần một hệ rewrite/text edit có phép ánh xạ offset và bảo toàn token/trivia; đừng mutate implementation nodes của `javac` bằng giả định không được API đảm bảo.

`com.sun.source.util.Plugin`, `TaskListener` và JSR 269 là những cơ chế tích hợp compiler khác với một tool ngoài gọi `JavacTask.parse()`. Chúng đều có thể truy cập AST theo ngữ cảnh, nhưng quyền và vòng đời khác nhau; bài này tập trung vào duyệt `CompilationUnitTree`.

## 13. Mở rộng từ ví dụ: tìm method trong một class cụ thể

Một scanner thực tế có thể chỉ muốn method `add` trong `Sample`. Có hai chiến lược:

1. Với `TreeScanner`: override `visitClass`, nhận tên class qua `ClassTree.getSimpleName()`, truyền context xuống `visitMethod` bằng `P` hoặc một stack.
2. Với `TreePathScanner`: trong `visitMethod`, đi ngược path cho đến `ClassTree` gần nhất; kiểm tra tên class. Cách này hữu ích khi có nested classes, anonymous classes hoặc methods trong nhiều cấp.

Đoạn kiểm tra nearest class từ một `visitMethod`:

~~~java
TreePath p = getCurrentPath().getParentPath();
while (p != null && !(p.getLeaf() instanceof ClassTree)) {
    p = p.getParentPath();
}
if (p != null) {
    ClassTree owner = (ClassTree) p.getLeaf();
    String className = owner.getSimpleName().toString();
    // Dùng className cùng node.getName() trong rule.
}
~~~

Đây là **trích đoạn trong TreePathScanner**, không phải class Java độc lập. Với anonymous class, `getSimpleName()` có thể là tên rỗng; nếu cần danh tính đầy đủ, phải dùng path/symbol phù hợp và compiler analysis thay vì chỉ dựa vào simple name.

Nếu chỉ muốn top-level class names, dùng `unit.getTypeDecls()` và lọc những khai báo là `ClassTree`; không cần scan toàn thân method để tìm nó. **Chọn API tối thiểu đủ đáp ứng câu hỏi** là cách giữ analyzer dễ hiểu.

## 14. Ví dụ câu hỏi và bài tập

**Câu 1.** Tại sao trong code mẫu `TreeScanner` đếm `calls=1` dù có hai methods?  
**Đáp án:** `greet()` chứa lời gọi `System.out.println`; `add()` chỉ có phép cộng và lệnh return, không có `MethodInvocationTree`.

**Câu 2.** Vì sao `TreePathScanner` in `parent=EXPRESSION_STATEMENT` cho `System.out.println`?  
**Đáp án:** Invocation là biểu thức được đặt làm một statement; node cha trực tiếp của invocation là `ExpressionStatementTree`. Method `greet` là một **tổ tiên xa hơn**, không phải cha trực tiếp.

**Câu 3.** Khi nào nên chọn `TreeScanner<Void, Void>`?  
**Đáp án:** Khi chỉ đếm, kiểm kê hoặc kiểm tra node theo cú pháp và không cần truy ngược ancestors hay truy vấn symbol bằng TreePath.

**Câu 4.** Một method invocation xuất hiện trong lambda. `getCurrentPath().getParentPath()` có luôn là `MethodTree` không?  
**Đáp án:** Không. Parent path có thể là expression statement, return, lambda body hoặc một biểu thức khác. Phải đi ngược nhiều mức nếu cần enclosing method.

**Câu 5.** Để xác định thực sự gọi overload nào, chỉ dùng `MethodInvocationTree.getMethodSelect().toString()` có đủ không?  
**Đáp án:** Không. Cần semantic analysis và `Trees.getElement(path)` trên path hợp lệ.

**Câu 6.** `getStartPosition` trả `-1`; có nên chuyển thành dòng `-1` một cách máy móc?  
**Đáp án:** Không. Đó là trường hợp không có vị trí nguồn xác định; cần guard và bỏ qua hoặc báo vị trí unknown.

**Câu 7.** Có thể bắt đầu TreePathScanner với `scan(methodTree, null)` từ scanner mới mà vẫn có ancestors của compilation unit không?  
**Đáp án:** Không được dựa vào điều đó. Hãy bắt đầu từ `CompilationUnitTree` hoặc `scan(TreePath, p)` khi path đã đầy đủ.

**Câu 8.** Quên gọi `super.visitMethod` trong scanner thì có thể sai điều gì?  
**Đáp án:** Scanner sẽ không duyệt method body, bỏ qua các invocation, variables, expressions nằm trong method.

**Câu 9.** Source chứa một nested class và một anonymous class. `visitClass` có thể đếm cả chúng không?  
**Đáp án:** Có; `ClassTree` thể hiện các khai báo class/anonymous class tương ứng. Nếu chỉ cần top-level types thì lọc theo `unit.getTypeDecls()` hoặc context path.

**Câu 10.** `CompilationUnitTree` có trực tiếp chứa `Class<?>` reflection của JVM không?  
**Đáp án:** Không. Đây là AST source. `Class<?>` thuộc runtime reflection; khi cần symbol/type compile-time dùng Java Compiler Model và `Trees`.

## 15. Tài liệu chính thức

- [Java 17 — CompilationUnitTree](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/tree/CompilationUnitTree.html)
- [Java 17 — TreeScanner](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/TreeScanner.html)
- [Java 17 — TreePathScanner](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/TreePathScanner.html)
- [Java 17 — TreePath](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/TreePath.html)
- [Java 17 — JavacTask](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/JavacTask.html)
- [Java 17 — Trees và SourcePositions](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/Trees.html)

**Ghi nhớ:** `CompilationUnitTree` là root của AST source; `TreeScanner` duyệt và tổng hợp node; `TreePathScanner` làm điều đó **kèm path từ gốc tới node hiện tại**. Bắt đầu scan đúng cách, gọi `super.visitXxx` khi cần đi xuống con, kiểm tra parent/null/source positions, và chỉ truy vấn symbol/type sau khi compiler đã có đủ thông tin semantic.

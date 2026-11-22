# Vai trò của Compiler Tree API trong phân tích mã nguồn Java

**Compiler Tree API** là bộ giao diện công khai của JDK cho phép chương trình quan sát **cây cú pháp trừu tượng (Abstract Syntax Tree — AST)** của mã nguồn Java mà compiler sử dụng. Nó đặc biệt hữu ích khi xây dựng **công cụ phân tích tĩnh**, trình kiểm tra quy tắc code, plugin hỗ trợ IDE, bộ dò các mẫu cú pháp, công cụ thu thập vị trí source, trình sinh báo cáo hoặc processor muốn liên hệ giữa khai báo và source code.

Thay vì tìm kiếm Java source bằng chuỗi hoặc biểu thức chính quy, công cụ dùng Tree API có thể đặt câu hỏi ở cấp độ ngôn ngữ: “Đây có phải một `MethodTree`?”, “`return` nằm trong phương thức nào?”, “Câu lệnh này gọi phương thức nào?”, “Tên được viết trong file nằm ở dòng nào?”. Khi kết hợp cây cú pháp với kết quả **phân tích ngữ nghĩa** của compiler, ta còn hỏi được “Tên này được phân giải thành `Element` nào?” và “Kiểu thực sự của biểu thức này là gì?”.

Bài thuộc chủ đề **cây cú pháp** trong quá trình biên dịch Java, tập trung vào những API được tài liệu JDK công bố trong hai package `com.sun.source.tree` và `com.sun.source.util`. Ví dụ ưu tiên Java 17 trở lên.

## 1. Compiler Tree API đứng ở đâu trong pipeline `javac`?

Một mô hình đơn giản của việc biên dịch là:

```text
Java source (.java)
       |
       v
Lexical analysis / Parsing
       |
       v
AST: CompilationUnitTree, ClassTree, MethodTree, ...
       |             ^
       |             |
       |        Compiler Tree API
       v
Enter + symbol / type attribution + semantic checks
       |
       v
Đối chiếu AST với Element, TypeMirror, Scope
       |
       v
Các biến đổi nội bộ / hạ cấp cú pháp
       |
       v
Bytecode generation (.class)
```

Sơ đồ là **mô hình khái quát để học**, không phải cam kết tên và thứ tự chính xác của mọi pha nội bộ `javac` trong mọi bản JDK. JavaCompiler API cho phép lấy một `JavacTask` và chủ động gọi `parse()`, `analyze()`, `generate()` khi phù hợp; Tree API cung cấp các abstraction để quan sát cây được tạo và liên hệ nó với model ngữ nghĩa.

### Phân biệt ba tầng dữ liệu

| Tầng | API điển hình | Câu hỏi trả lời |
| --- | --- | --- |
| **Cú pháp** | `CompilationUnitTree`, `ClassTree`, `MethodTree`, `ExpressionTree`, `Tree.Kind` | Source có những cấu trúc ngôn ngữ nào? |
| **Ngữ nghĩa** | `Element`, `TypeMirror`, `Scope`, `Trees.getElement`, `Trees.getTypeMirror` | Tham chiếu trỏ tới symbol nào và kiểu thực tế là gì? |
| **Class file/bytecode** | `javap`, JVM class-file structures | Compiler đã xuất bytecode, descriptors, attributes gì? |

Compiler Tree API **không phải bytecode API** và **không phải một Java parser dạng string**. AST mang cấu trúc của chương trình nguồn, còn bytecode là kết quả sau khi compile, có thể chứa các chi tiết như synthetic members, bridge methods hoặc desugaring mà AST nguồn không bộc lộ theo cùng dạng.

## 2. Package và module cần dùng

Java 17 phân phối API liên quan trong module **`jdk.compiler`**:

- `com.sun.source.tree`: những giao diện biểu diễn các node AST — `Tree`, `CompilationUnitTree`, `ClassTree`, `MethodTree`, `VariableTree`, `IfTree`, `MethodInvocationTree`, v.v.
- `com.sun.source.util`: các tiện ích để duyệt, xác định đường đi, ánh xạ source và nhận thông tin compiler — `JavacTask`, `TreeScanner`, `TreePathScanner`, `TreePath`, `Trees`, `SourcePositions`, `TaskListener`.
- `com.sun.source.doctree`: AST cho nội dung tài liệu Javadoc; có các tiện ích `DocTrees`.
- `javax.tools` trong module `java.compiler`: interface compiler, file manager, diagnostic collector, `JavaFileObject`.
- `javax.lang.model` và các subpackages trong `java.compiler`: model khai báo và kiểu của chương trình ở mức ngữ nghĩa.

**Không vì tiền tố `com.sun` mà mặc định đây là mọi API nội bộ không được hỗ trợ**. Các package `com.sun.source.tree`/`com.sun.source.util` là các package được **`jdk.compiler` export công khai**, có tài liệu API. Ngược lại, phần lớn các class cụ thể trong `com.sun.tools.javac.*` là chi tiết triển khai compiler và không nên được dùng như API ổn định của công cụ phân tích.

Nếu viết ứng dụng **modular** có `module-info.java`, khai báo:

```java
module com.example.analyzer {
    requires jdk.compiler;
}
```

Với chương trình classpath thông thường sử dụng JDK đầy đủ, có thể import các API đã được export của `jdk.compiler`; ví dụ chạy trong bài không cần tạo module descriptor.

**Điều kiện môi trường:** phải dùng JDK/runtime image có `jdk.compiler`. Custom runtime tối giản có thể không có compiler. `ToolProvider.getSystemJavaCompiler()` có thể trả `null`; mã sản xuất cần kiểm tra trường hợp đó trước khi tạo task.

## 3. AST là gì và node mang thông tin gì?

**AST** biểu diễn các cấu trúc cú pháp có ý nghĩa, không cố giữ nguyên mọi chi tiết văn bản như spacing, số lượng dấu cách, comment bình thường hoặc dấu chấm phẩy dưới dạng node riêng.

Với source:

```java
public class Calculator {
    public int doubleIt(int x) {
        return x + x;
    }
}
```

Một cách nhìn AST rút gọn:

```text
CompilationUnitTree
└── ClassTree: Calculator
    └── MethodTree: doubleIt
        ├── return type: PrimitiveTypeTree(INT)
        ├── parameter: VariableTree(x : int)
        └── BlockTree
            └── ReturnTree
                └── BinaryTree(PLUS)
                    ├── IdentifierTree(x)
                    └── IdentifierTree(x)
```

Đây là **sơ đồ minh họa**, không phải kết quả `toString()` của một node AST. Cây thực còn có modifier nodes, danh sách members và nhiều thông tin cú pháp khác.

| Giao diện | Đại diện |
| --- | --- |
| `CompilationUnitTree` | Một compilation unit (file nguồn), package, imports, type declarations, line map |
| `ClassTree` | Khai báo class, interface, enum, record và những thành viên/cấu trúc tương ứng |
| `MethodTree` | Khai báo method/constructor, parameters, return type, body, thrown types |
| `VariableTree` | Khai báo field, parameter hoặc local variable |
| `BlockTree` | Khối các statement |
| `IfTree` / `ForLoopTree` | Cấu trúc điều khiển |
| `ReturnTree` | Return statement |
| `MethodInvocationTree` | Biểu thức gọi method |
| `IdentifierTree` | Tham chiếu tên đơn |
| `MemberSelectTree` | Truy cập member qua biểu thức như `obj.method` |
| `BinaryTree` | Phép toán hai toán hạng như `a + b` |
| `LiteralTree` | Literal số, chuỗi, boolean, null |
| `ErroneousTree` | Phần lỗi cú pháp mà compiler vẫn biểu diễn trong một cây khi phục hồi lỗi |

`Tree.Kind` cho phép phân loại node, ví dụ `CLASS`, `METHOD`, `VARIABLE`, `METHOD_INVOCATION`, `PLUS`, `RETURN`. Tên `Tree.Kind` không nên được coi là cùng một thứ với `ElementKind` hoặc JVM opcode: chúng mô tả các tầng khác nhau.

### AST không phải token stream hoàn chỉnh

Ví dụ hai đoạn:

```java
int total = 1 + 2;
```

và:

```java
int total=1+2; // tính tổng
```

thường cho cấu trúc AST tương ứng giống nhau ở những node ngữ nghĩa chính, dù khác whitespace/comment. Nếu công cụ cần **giữ nguyên mọi byte formatting, comments và khoảng trắng** để viết formatter hoặc sửa source với zero-diff, phải bổ sung một mô hình text/token/trivia phù hợp. Compiler Tree API không tự cung cấp một concrete syntax tree bảo tồn mọi ký tự.

## 4. Hai phong cách duyệt: `TreeScanner` và `TreePathScanner`

### `TreeScanner<R,P>`

`TreeScanner` đi qua những cây con và gọi các visitor methods như `visitClass`, `visitMethod`, `visitVariable`, `visitMethodInvocation`. Với nhu cầu thống kê cấu trúc đơn giản, nó có thể đủ:

```java
new TreeScanner<Void, Void>() {
    @Override
    public Void visitMethod(MethodTree method, Void unused) {
        System.out.println(method.getName());
        return super.visitMethod(method, unused);
    }
}.scan(unit, null);
```

Đây là **mảnh code**, giả định có biến `CompilationUnitTree unit` và imports. Gọi `super.visitMethod(...)` giúp tiếp tục duyệt các descendants bên trong phương thức. Nếu cố ý bỏ lời gọi `super`, bạn có thể dừng việc xuống phần body của method.

### `TreePathScanner<R,P>`

`TreePathScanner` mở rộng `TreeScanner` và duy trì **`TreePath` tới node hiện tại**. Nó hữu ích khi cần:

- Biết một statement thuộc method/class nào theo đường ancestor.
- Tra `Trees.getElement(getCurrentPath())`.
- Tra kiểu của biểu thức bằng `Trees.getTypeMirror(getCurrentPath())`.
- Xây một diagnostic cần vị trí của node trong compilation unit.

Ví dụ:

```java
new TreePathScanner<Void, Void>() {
    @Override
    public Void visitMethod(MethodTree method, Void unused) {
        TreePath path = getCurrentPath();
        // path liên kết compilation unit → ancestors → method node.
        return super.visitMethod(method, unused);
    }
}.scan(unit, null);
```

Đây cũng là **snippet**, không phải chương trình chạy riêng. `getCurrentPath()` chỉ có ngữ cảnh phù hợp **bên trong visitor callback khi scanner đang hoạt động**; đừng gọi nó trước khi bắt đầu scan rồi mong có path tới node bất kỳ.

**Quan trọng:** Khi khởi đầu từ một `CompilationUnitTree`, `scanner.scan(unit, null)` là một cách hợp lệ để tạo context path ban đầu. Với node con đơn lẻ không kèm compilation unit, nên bắt đầu bằng `scanner.scan(TreePath, ...)` hoặc xây path hợp lệ; tự `scan` một node lẻ có thể không cung cấp đủ thông tin ancestor/source.

## 5. Ví dụ hoàn chỉnh Java 17: liệt kê phương thức và dòng source

Ví dụ này **không viết source analyzer bằng regex**. Nó yêu cầu `javac` parse file thành AST, dùng `TreePathScanner` tìm `MethodTree` và `SourcePositions` để đổi vị trí bắt đầu thành số dòng.

### 5.1. Tạo cấu trúc source

```text
project/
├── TreeInspector.java
└── src/
    └── demo/
        └── Sample.java
```

**`src/demo/Sample.java`**, giữ dòng trống để số dòng trong output chính xác:

```java
package demo;

public class Sample {
    public int add(int a, int b) {
        return a + b;
    }

    public int twice(int number) {
        return add(number, number);
    }
}
```

Theo thứ tự trên, `add` được khai báo bắt đầu ở **dòng 4**, `twice` ở **dòng 8** (đếm dòng đầu tiên của source là 1).

### 5.2. Viết `TreeInspector.java`

```java
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.LineMap;
import com.sun.source.tree.MethodTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.SourcePositions;
import com.sun.source.util.TreePathScanner;
import com.sun.source.util.Trees;
import java.io.IOException;
import java.nio.file.Path;
import java.util.List;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class TreeInspector {
    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java TreeInspector path/to/Source.java");
        }

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "JDK compiler (jdk.compiler) is unavailable");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
                     compiler.getStandardFileManager(
                             diagnostics, null, null)) {

            Iterable<? extends JavaFileObject> sources =
                    manager.getJavaFileObjectsFromPaths(
                            List.of(Path.of(args[0])));

            JavacTask task = (JavacTask) compiler.getTask(
                    null,
                    manager,
                    diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null,
                    sources);

            Trees trees = Trees.instance(task);
            SourcePositions positions = trees.getSourcePositions();

            for (CompilationUnitTree unit : task.parse()) {
                LineMap lines = unit.getLineMap();

                new TreePathScanner<Void, Void>() {
                    @Override
                    public Void visitMethod(
                            MethodTree method, Void unused) {
                        long offset =
                                positions.getStartPosition(unit, method);

                        if (offset >= 0
                                && method.getReturnType() != null) {
                            long line = lines.getLineNumber(offset);
                            System.out.println(
                                    "method=" + method.getName()
                                    + " line=" + line);
                        }

                        return super.visitMethod(method, unused);
                    }
                }.scan(unit, null);
            }

            boolean hasErrors = diagnostics.getDiagnostics()
                    .stream()
                    .anyMatch(d -> d.getKind()
                            == Diagnostic.Kind.ERROR);

            if (hasErrors) {
                System.err.println("Source contains parse errors");
            }
        }
    }
}
```

**Giải thích đường đi:**

1. Lấy `JavaCompiler` bằng `ToolProvider`. Nếu runtime image không có compiler, dừng với thông báo riêng.
2. `getStandardFileManager(...)` dùng `JavaFileObject` cho file input; `try-with-resources` đảm bảo file manager được đóng.
3. `getTask(...)` tạo một compiler task từ source file. Tham số `List.of("--release", "17", "-proc:none")` giúp parse theo mức Java 17 và tắt annotation processing cho ví dụ.
4. Với implementation `javac` trong `jdk.compiler`, task nhận về có thể **ép sang `JavacTask`** để gọi `parse()`. Đây là tích hợp đặc thù JDK compiler, không phải cam kết mọi `JavaCompiler` bên thứ ba đều trả `JavacTask`.
5. `Trees.instance(task)` cung cấp các phép tra cứu gắn với task; `getSourcePositions()` cho vị trí AST node trong compilation unit.
6. `task.parse()` trả các `CompilationUnitTree`. Ví dụ **chỉ parse**, không gọi `analyze()` hoặc `generate()`, nên nó không nhằm kiểm tra toàn bộ type semantics hoặc sinh class file của `Sample`.
7. `TreePathScanner` tự duyệt các node con; override `visitMethod` để tìm method declarations.
8. `method.getReturnType() != null` lọc constructor declarations (constructor không có return type) nếu có. Ví dụ source không tự viết constructor.
9. Vị trí `offset` không âm mới được đổi sang line number; source positions có thể vắng mặt ở một số node.
10. Compiler diagnostics được thu vào collector; chương trình chỉ in cảnh báo tổng quát nếu gặp `ERROR`, thay vì phụ thuộc vào câu chữ diagnostics.

### 5.3. Biên dịch và chạy

Tại thư mục `project`, với **JDK 17+**:

```sh
javac --release 17 -encoding UTF-8 TreeInspector.java
java TreeInspector src/demo/Sample.java
```

**Stdout chính xác với hai tệp ở trên:**

```text
method=add line=4
method=twice line=8
```

Chạy `TreeInspector` bằng một JDK mới hơn nhưng target source `--release 17` không thay đổi các dòng của source. Class `TreeInspector.class` được sinh bởi lệnh biên dịch công cụ; còn `Sample.class` **không** được tạo chỉ từ lời gọi `task.parse()` của chương trình.

**Nếu source nhập có lỗi cú pháp:** Compiler có thể tạo `ErroneousTree` và báo `Diagnostic.Kind.ERROR`. Output scan có thể thiếu node hoặc có vị trí không đầy đủ; chương trình ví dụ chỉ minh họa kiểm tra `hasErrors`. Công cụ phân tích thật nên dừng hoặc đánh dấu kết quả là **partial** khi diagnostics có lỗi, không báo kết quả AST như hoàn chỉnh một cách vô điều kiện.

### 5.4. Hạn chế của phép đo line

`SourcePositions.getStartPosition(unit, tree)` trả **vị trí ký tự bắt đầu** của node trong compilation unit hoặc `-1`/`Diagnostic.NOPOS` khi không xác định. `LineMap.getLineNumber(offset)` chuyển position hợp lệ sang dòng.

Một số trường hợp cần lưu ý:

- Node do compiler tổng hợp có thể không có source position.
- Constructor ngầm hoặc members được tạo sau một pha compiler không nhất thiết có nguồn khai báo tương ứng.
- Vị trí áp dụng cho **source file cụ thể**; không được ghép offset của unit A với `LineMap` của unit B.
- Vị trí ký tự dùng semantics của API/source; không tự coi là byte offset UTF-8 trong file.
- Khi cần highlight cả range, lấy thêm `getEndPosition` nhưng kiểm tra khả năng không có end position.
- Line/column dùng quy ước của `LineMap`/diagnostic, thường là **1-based**; không mặc định thẳng vào API editor 0-based mà không chuyển đổi.

## 6. `parse()`, `analyze()` và `generate()`: chọn đúng mức

`JavacTask` cung cấp các phương thức cho những pha công việc cấp cao:

| Method | Vai trò | Khi phù hợp |
| --- | --- | --- |
| `parse()` | Phân tích cú pháp, trả `CompilationUnitTree` | Dò phương thức, biểu thức, cấu trúc lệnh, dòng nguồn |
| `analyze()` | Hoàn thành phân tích ngữ nghĩa | Cần `Element`, `TypeMirror`, quy tắc kiểu/phân giải symbol |
| `generate()` | Sinh output code/class files | Cần compiler thật sự tạo class files sau quá trình phù hợp |
| `CompilationTask.call()` | Thực hiện compile như một task và trả `Boolean` thành công | Tool chỉ cần compile kết quả; không tự phối hợp các pha Tree API |

Các lời gọi phải tuân theo trạng thái task; không nên gọi `task.call()` tùy ý **sau** khi đã chủ động thao tác các pha theo cách không được API bảo đảm. Dùng **task mới** cho một quá trình compile khác hoặc muốn lặp lại việc parse/analysis.

### Vì sao `parse()` chưa đủ cho kiểu?

Từ mã:

```java
import java.util.List;

class Example {
    void consume(List<String> values) {
        System.out.println(values.size());
    }
}
```

AST có thể cho biết một `MethodInvocationTree` biểu diễn `values.size()` và `IdentifierTree` tên `values`. Nhưng để khẳng định **`values` là tham số nào**, kiểu biểu thức là gì, `size` được phân giải thành method nào, compiler cần phân tích symbol/type.

Nếu chỉ so sánh `node.toString().equals("size()")` hoặc tên text của method invocation, dễ nhầm khi một tên phương thức được overload, được kế thừa, xuất hiện trong các lớp khác nhau hoặc bị shadowing.

**Quy tắc học tập:** dùng parse-only cho truy vấn **cú pháp**; dùng analysis + `Trees`/language model cho truy vấn **ngữ nghĩa**.

## 7. Liên hệ AST với `Element` và `TypeMirror`

Sau khi có dữ liệu phân tích ngữ nghĩa phù hợp từ `JavacTask.analyze()`, `Trees` là cầu nối giữa cây và mô hình language elements:

- `Trees.getElement(TreePath)`: lấy khai báo **`Element`** tương ứng node/path, nếu có.
- `Trees.getTypeMirror(TreePath)`: lấy **`TypeMirror`** biểu diễn kiểu của node/path, khi có thể xác định.
- `Trees.getPath(Element)`: lấy `TreePath` đến khai báo source tương ứng nếu compiler có cây nguồn.
- `Trees.getTree(Element)`: lấy AST declaration liên quan `Element` nếu source tree hiện diện.
- `Trees.getScope(TreePath)`: truy vấn scope tại vị trí phù hợp.
- `JavacTask.getElements()` và `getTypes()`: utilities cho model ngữ nghĩa.

Ví dụ **mảnh tích hợp**, giả định bạn đã tạo `JavacTask task`, duyệt `CompilationUnitTree unit` từ `task.parse()`, rồi gọi `task.analyze()` và có `Trees trees`:

```java
task.analyze();

new TreePathScanner<Void, Void>() {
    @Override
    public Void visitMethod(MethodTree method, Void unused) {
        TreePath path = getCurrentPath();
        Element symbol = trees.getElement(path);

        if (symbol instanceof ExecutableElement executable
                && method.getReturnType() != null) {
            System.out.println(
                    executable.getSimpleName()
                    + " returns "
                    + executable.getReturnType());
        }
        return super.visitMethod(method, unused);
    }
}.scan(unit, null);
```

Đây là **snippet, không phải file Java độc lập**: thêm `javax.lang.model.element.Element` và `ExecutableElement` imports, đảm bảo `task`, `unit`, `trees` cùng một compiler task. Mã này minh họa cách sử dụng language model sau `analyze()`; tránh ép kiểu `Element` thành `ExecutableElement` trước khi kiểm tra với `instanceof`.

### `TreePath` quan trọng vì một tên không đủ để nhận dạng symbol

Hai chỗ cùng có `IdentifierTree("value")` có thể tham chiếu hai biến khác nhau trong các scope khác nhau. `TreePath` mang **ngữ cảnh ancestor** từ compilation unit đến node, nên `Trees.getElement` có thể phân giải đúng element ở vị trí đó khi compiler đã hoàn tất attribution.

Không cố gọi `getElement` ở bất kỳ node nào cũng phải nhận một kết quả không-null. Với node không biểu diễn symbol, compiler chưa analyze, source có lỗi, hoặc dữ liệu tới từ binary dependency không có source tree, API có thể trả `null` hoặc chưa có thông tin đầy đủ. Code phân tích thật cần chính sách xử lý **unresolved** thay vì ném `NullPointerException`.

### `TypeMirror` khác text của `Tree`

`Tree` mô tả source syntax, ví dụ `List<String>` hoặc một biểu thức số học. `TypeMirror` mô tả kiểu ngữ nghĩa mà compiler suy ra/tra cứu, có thể bao gồm type arguments, wildcard, intersection type, error type và kết quả inference.

Ví dụ `int result = 1 + 2;`: AST phép cộng chứa `BinaryTree(PLUS)` với hai `LiteralTree`, còn `TypeMirror` của biểu thức có thể là `int`. Khi biểu thức involve generics/overload, kiểu suy ra không nhất thiết đọc được chỉ bằng `node.toString()`.

## 8. `TreeVisitor` và cách viết luật phân tích tĩnh

Mỗi `Tree` có thể được thăm qua `TreeVisitor`. Cách thuận tiện nhất thường là kế thừa `TreeScanner` hoặc `TreePathScanner` và override visitor method đúng loại node.

### Ví dụ: đếm lời gọi phương thức

```java
final class InvocationCounter
        extends TreeScanner<Void, Void> {
    private int count;

    @Override
    public Void visitMethodInvocation(
            MethodInvocationTree invocation, Void unused) {
        count++;
        return super.visitMethodInvocation(invocation, unused);
    }

    int getCount() {
        return count;
    }
}
```

Đây là **class snippet** cần imports `com.sun.source.tree.MethodInvocationTree` và `com.sun.source.util.TreeScanner`. Để dùng, tạo `InvocationCounter counter`, gọi `counter.scan(unit, null)` rồi đọc `counter.getCount()`.

**Giới hạn:** Đếm cú pháp invocation khác với đếm lời gọi runtime. Một lời gọi nguồn có thể chạy nhiều lần trong vòng lặp, không chạy do điều kiện, hoặc kết quả bị dispatch đến implementation khác. AST chỉ phản ánh những invocation expressions được viết/sinh vào cây của mã nguồn được phân tích, không mô phỏng runtime.

### Ví dụ: tìm câu lệnh `return` trong một phương thức

`TreePathScanner` có thể override `visitReturn(ReturnTree node, ...)` và dùng đường ancestor để xác định method chứa nó. Khi có lambda hoặc nested/local class, phải quyết định scope của luật một cách rõ ràng; không nhất thiết mọi `return` dưới subtree method đều là return trực tiếp của chính method đó.

Ví dụ hệ thống lint có thể:

- Cảnh báo method quá dài dựa vào source range và cấu trúc AST.
- Cảnh báo sử dụng một API cũ khi **symbol resolved** trỏ tới API đó, thay vì so tên text.
- Đếm vòng lặp lồng nhau và độ sâu nhánh.
- Tìm lệnh `catch` bỏ trống có khả năng nuốt ngoại lệ.
- Kiểm tra annotation trên khai báo.
- Phát hiện `if` với điều kiện luôn boolean literal trong AST.

Nhưng đừng hứa Tree API tự động chứng minh chương trình không lỗi concurrency, không rò rỉ tài nguyên hay không có security flaw. Các phân tích nâng cao cần **control-flow/data-flow**, mô hình chương trình và/hoặc thư viện phân tích bổ sung.

## 9. Phát hành diagnostic gắn với vị trí AST

Một công cụ phân tích hữu ích không chỉ in tên method lên console mà còn muốn báo **đúng vị trí nguồn**. Hai cách phổ biến:

1. Dùng `SourcePositions` + `CompilationUnitTree.getLineMap()` để lấy file, dòng, cột; sau đó lưu kết quả cho IDE/CI.
2. Dùng tiện ích `Trees.printMessage(Diagnostic.Kind kind, CharSequence msg, Tree t, CompilationUnitTree root)` khi đang có môi trường compiler tương ứng; nhờ đó diagnostic gắn với vị trí node.

Các diagnostics trong quá trình parse/analyze cũng có thể được gửi tới `DiagnosticCollector<JavaFileObject>` khi tạo `JavaCompiler.CompilationTask`.

Ví dụ cách duyệt compiler diagnostics an toàn:

```java
for (Diagnostic<? extends JavaFileObject> d :
        diagnostics.getDiagnostics()) {
    String sourceName = d.getSource() == null
            ? "<unknown>" : d.getSource().getName();

    System.out.println(
            d.getKind() + " " + sourceName
            + ":" + d.getLineNumber());
}
```

Đây là **snippet**, giả định có `DiagnosticCollector`/imports. `Diagnostic` có thể không gắn với source cụ thể hoặc không có vị trí; `getLineNumber()` có thể là `Diagnostic.NOPOS`. Không dùng vị trí âm để highlight một dòng không tồn tại.

### Parse lỗi và recoverable trees

Khi mã nguồn có lỗi như thiếu dấu ngoặc hoặc khai báo chưa hoàn chỉnh, `javac` có thể **phục hồi một phần** để tạo AST và chẩn đoán. `ErroneousTree` là một kiểu node biểu diễn phần source mà compiler không phân tích cú pháp theo cấu trúc mong muốn.

Đối với IDE, AST chưa hoàn chỉnh vẫn có giá trị cho gợi ý code. Nhưng với một công cụ CI yêu cầu độ tin cậy tuyệt đối, bạn có thể chọn không thực thi một số luật semantic nếu đã có `Diagnostic.Kind.ERROR`. Trong mọi trường hợp, **`parse()` trả một cây không đồng nghĩa source hợp lệ**.

## 10. Vai trò của `TaskListener` và thời điểm quét cây

`com.sun.source.util.TaskListener` có thể theo dõi những sự kiện cấp compiler do `JavacTask` phát ra, với `started(TaskEvent)` và `finished(TaskEvent)`. `TaskEvent.Kind` bao gồm các loại liên quan parse, enter, analyze và generate. Điều này hữu ích nếu muốn phân tích ở một pha phù hợp hoặc tích hợp vào quá trình compile dài.

**Ví dụ skeleton:**

```java
task.addTaskListener(new TaskListener() {
    @Override
    public void started(TaskEvent event) {
    }

    @Override
    public void finished(TaskEvent event) {
        if (event.getKind() == TaskEvent.Kind.PARSE) {
            // Có thể xem compilation unit của event
            // theo API phù hợp và thời điểm hợp lệ.
        }
    }
});
```

Đây là **snippet**; yêu cầu imports `TaskListener` và `TaskEvent`, cùng biến `task` đúng loại `JavacTask`. Không đưa logic ghi bytecode hoặc sửa compiler internal state vào callback khi chưa có hợp đồng an toàn rõ ràng.

### Chọn thời điểm dựa trên thông tin mình cần

- **Sau parse:** đủ cho các quy tắc cú pháp; AST có thể tồn tại ngay cả khi source có lỗi.
- **Sau analyze:** phù hợp cho truy vấn `Element`, `TypeMirror`, scope và validation theo symbol; phải xử lý errors.
- **Trước/sau generate:** phù hợp nếu mục tiêu là quan sát tiến trình và class outputs, nhưng bytecode nên được kiểm tra bằng class-file tools thích hợp.

Không cần cài `TaskListener` cho mọi công cụ. Nếu muốn một lần quét source đơn giản, ví dụ `TreeInspector` với `task.parse()` trực tiếp dễ đọc và dễ kiểm thử hơn.

## 11. Dùng Tree API trong annotation processor

JSR 269 `javax.annotation.processing` thường đưa processor một tập `Element` có annotation; Processor API **thiên về language model**, không tự mô tả mọi chi tiết cú pháp nằm trong method bodies. Khi annotation processor cần biết vị trí source/AST:

```java
Trees trees = Trees.instance(processingEnv);
TreePath path = trees.getPath(element);
if (path != null) {
    Tree declaration = path.getLeaf();
    // Phân tích declaration AST qua TreePathScanner phù hợp.
}
```

Đây là **snippet** trong `AbstractProcessor` với `processingEnv` và `Element element`; không phải file độc lập. Sử dụng `Trees.instance(ProcessingEnvironment)` khi compiler cung cấp Tree API tương ứng.

**Lưu ý:**

- `getPath(element)` có thể trả `null` nếu element tới từ **binary dependency** không có source tree, hoặc cây nguồn không khả dụng.
- Annotation processor có thể được gọi nhiều vòng; generated source ở vòng sau có AST mới. Không giả định `getRootElements()` của một vòng chứa mọi declaration trong lịch sử.
- Không giữ tham chiếu compiler tree/`Element` qua những compiler invocations khác nhau; thu thập dữ liệu ổn định khi cần.
- Dùng `Filer` để tạo source/class files đúng giao thức processor; Tree API **không có trách nhiệm tự ghi source code đã sửa** vào đĩa.
- Nếu cần Javadoc AST, dùng `DocTrees`/`DocTreePathScanner` cho doc comments, đừng parse text Javadoc bằng regex như một thay thế cho toàn bộ mô hình.

### AST và source-level lint khác nhau với annotation validation

Một annotation processor chỉ cần kiểm tra `@NotBlank` trên field có thể dùng `Element`/`TypeMirror` mà không cần Tree API. Tree API có giá trị **khi yêu cầu phụ thuộc vị trí/cú pháp/source body**, ví dụ kiểm tra một phương thức annotated có lệnh `return` đặc biệt hoặc có thực hiện kiểu gọi không được phép.

Đừng dùng Tree API chỉ để thay thế một truy vấn `Element.getSimpleName()` vốn đã được Processor API hỗ trợ: chọn abstraction nhỏ nhất đáp ứng yêu cầu.

## 12. Các giới hạn và vấn đề tương thích

### API công khai và compiler internals

- `com.sun.source.tree`, `com.sun.source.util` và `com.sun.source.doctree` là phần được module `jdk.compiler` export; có tài liệu chính thức.
- `com.sun.tools.javac.tree.JCTree`, `com.sun.tools.javac.code.Symbol` và nhiều loại compiler internal khác **không** phải hợp đồng công khai tương tự. Việc dùng chúng có thể cần `--add-exports`, vỡ khi nâng JDK, và phụ thuộc sâu vào implementation.
- `Tree` là interface cho truy vấn; không mặc định có public mutation API cho việc sửa AST bất kỳ và khiến compiler biên dịch lại theo cách ổn định.
- Nếu mục tiêu là **tái cấu trúc mã nguồn**, hãy thiết kế hệ rewrite dựa trên source ranges/text edits với validation, hoặc dùng framework có hợp đồng rewrite riêng.

### JDK compiler không phải mọi compiler Java

`JavaCompiler` là một SPI; một compiler Java bên thứ ba có thể triển khai `javax.tools.JavaCompiler` nhưng không trả ra `com.sun.source.util.JavacTask`. Với code:

```java
JavacTask task = (JavacTask) compiler.getTask(...);
```

cách cast này dựa vào implementation `javac` có trong `jdk.compiler`. Trong tool muốn hỗ trợ nhiều compiler, hãy kiểm tra kiểu bằng `instanceof` hoặc công bố rõ phụ thuộc vào JDK `javac`, thay vì nghĩ tất cả `JavaCompiler` implementations đều tương thích Tree API.

### Mã Java mới và version compiler

AST node kinds được mở rộng khi Java có cú pháp mới (records, switch expressions, pattern matching...). Nếu trình phân tích chạy trên JDK khác nhau, loại node nhận được hoặc hành vi traversal có thể thay đổi. Dùng đúng version JDK và `--release` phù hợp với project; kiểm thử khi nâng toolchain.

Một tree scanner viết theo Java 17 có thể gặp cú pháp mới hơn khi được chạy bằng JDK mới và không giới hạn release. Không cố ép những node lạ thành kiểu cũ dựa trên `toString()`; hãy thiết kế visitor để bỏ qua hoặc xử lý node kinds chưa hỗ trợ theo chính sách tool.

### Không bảo đảm output AST giống source formatting

`Tree.toString()` chỉ là biểu diễn để quan sát/debug. Không nên:

- So sánh nó làm serialization format bền vững.
- Parse nó lại để xây dependency graph chính thức.
- Trông chờ giữ nguyên comment, whitespace, token offsets.
- Dùng text output làm evidence duy nhất cho việc phân giải overloaded methods.

Nếu cần lưu dữ liệu, định nghĩa schema của chính công cụ: file URI, kind, tên symbol đã phân giải, source range, loại finding và message.

## 13. Những sai lầm thường gặp

**“Compiler Tree API chỉ để in hình cây.”** Không. AST có thể được duyệt theo loại cấu trúc, liên hệ với vị trí source và sau semantic analysis với `Element`/`TypeMirror`; đó là nền tảng cho nhiều công cụ phân tích tĩnh.

**“`parse()` đã kiểm tra hết mọi kiểu.”** Sai. Parse chủ yếu tạo AST; muốn hỏi symbol/type đã được compiler phân giải cần các pha semantic thích hợp, thường gọi `analyze()`.

**“Chỉ cần tên identifier là biết variable nào.”** Sai. Scope, shadowing, overloaded methods, generics và imports đòi hỏi symbol resolution. Sử dụng `TreePath` + `Trees.getElement` ở pha phù hợp.

**“`TreeScanner` và `TreePathScanner` giống hệt nhau.”** Không. `TreePathScanner` quản lý path tới current node, hữu ích cho semantic/source-aware rules; `TreeScanner` đơn giản hơn khi chỉ đếm/duyệt cấu trúc.

**“Tất cả AST nodes có vị trí dòng.”** Không. Synthetic/error/recovered nodes có thể không có source position; kiểm tra `Diagnostic.NOPOS` hoặc giá trị âm trước khi dùng.

**“Cây AST đã parse nghĩa là mã nguồn biên dịch thành công.”** Sai. Compiler có thể cung cấp AST và diagnostics lỗi; output class file còn phụ thuộc analyze/generate.

**“`Trees.getPath(element)` luôn trả tree.”** Sai. Với element từ thư viện `.class` không có source trong compilation task, cây có thể không tồn tại.

**“Có `com.sun` thì tất cả là API nội bộ, hoặc tất cả đều an toàn.”** Cả hai thái cực đều sai. Dùng package được `jdk.compiler` export và tài liệu chính thức, tránh compiler implementation classes không được export.

**“Tree API tự động sửa source file.”** Sai. Nó là API xem/traversal và semantic bridge; không có cam kết mutating source AST rồi compiler sẽ tự tạo ra source mới phù hợp.

**“Có method invocation node nghĩa là method chắc chắn được chạy.”** Sai. AST mô tả chương trình, không mô phỏng mọi nhánh điều khiển và runtime dispatch.

**“Dùng compiler API sẽ compile source trong một sandbox bảo mật.”** Sai. Compiler/annotation processors có thể truy cập filesystem hoặc chạy mã trong JVM host. Với source không tin cậy, cần thực thi và kiểm soát tài nguyên ở môi trường cô lập; Tree API không phải cơ chế sandbox.

## 14. Checklist chọn và dùng Tree API đúng

- [ ] Yêu cầu phân tích **cú pháp**, **semantic type/symbol** hay **bytecode**? Đã chọn đúng tầng API?
- [ ] Chạy bằng JDK có module `jdk.compiler` và kiểm tra `ToolProvider` không `null`?
- [ ] Nếu ứng dụng modular, `module-info.java` có `requires jdk.compiler;`?
- [ ] Đã dùng các package công khai `com.sun.source.tree/util` thay vì internals `com.sun.tools.javac.*`?
- [ ] Dùng `JavacTask.parse()` để lấy `CompilationUnitTree` rồi scan đúng cấp cây?
- [ ] Dùng `TreePathScanner` khi cần ancestor path và tra symbol?
- [ ] Có gọi `analyze()` trước truy vấn semantic `Element`/`TypeMirror` trong task phù hợp?
- [ ] Có kiểm tra null/unresolved của `Trees.getElement/getPath`?
- [ ] Có kiểm tra source position hợp lệ và ánh xạ đúng `CompilationUnitTree.getLineMap()`?
- [ ] Có thu compiler diagnostics và xử lý source lỗi/partial trees?
- [ ] Có tránh giả định mọi AST node hoặc binary dependency đều có source tree?
- [ ] Có phân biệt lỗi parser, lỗi semantic và lỗi của tool phân tích?
- [ ] Có đóng `StandardJavaFileManager` và không sử dụng task sai lifecycle?
- [ ] Có kiểm thử trên JDK/compiler phiên bản mục tiêu cùng cú pháp Java cần hỗ trợ?
- [ ] Có giữ nguyên source formatting khi đưa ra sửa đổi, thay vì tái xuất `Tree.toString()` làm file nguồn?

**Kết luận:** Compiler Tree API giúp chuyển việc “đọc mã nguồn như văn bản” thành “phân tích **cấu trúc Java mà compiler hiểu**”. `com.sun.source.tree` cung cấp hình dạng AST, `TreeScanner`/`TreePathScanner` giúp duyệt cây, `Trees` kết nối node với **vị trí source** và **symbol/type model**, còn `JavacTask` cho phép chọn mức parse hoặc analyze. Đây là công cụ quan trọng cho static analysis/lint/IDE, nhưng cần hiểu rõ giới hạn của syntax-only checks, thông tin semantic, khả năng phục hồi lỗi và sự khác biệt giữa public API với compiler internals.

## Tài liệu tham khảo chính thức

- Java SE 17, module **`jdk.compiler`** và danh sách exported packages: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/module-summary.html
- Java SE 17, package **`com.sun.source.tree`**: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/tree/package-summary.html
- Java SE 17, package **`com.sun.source.util`**: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/package-summary.html
- Java SE 17, **`JavacTask`** (`parse`/`analyze`/`generate`): https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/JavacTask.html
- Java SE 17, **`TreePathScanner`**: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/TreePathScanner.html
- Java SE 17, **`Trees`** và **`SourcePositions`**: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/Trees.html
- Java SE 17, **`JavaCompiler`** (`javax.tools`): https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html
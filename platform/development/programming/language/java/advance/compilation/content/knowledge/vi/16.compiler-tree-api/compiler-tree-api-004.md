# Liên hệ nút Tree với Element và TypeMirror bằng Trees

Trong công cụ phân tích mã Java, **cây cú pháp (AST)** cho biết *đoạn mã được viết ra sao*, còn **mô hình phần tử (`Element`)** cho biết *tên ấy tham chiếu đến khai báo nào*, và **mô hình kiểu (`TypeMirror`)** cho biết *kiểu mà trình biên dịch suy ra hoặc kiểm tra là gì*. Ba lớp thông tin này có quan hệ chặt chẽ nhưng không thể thay thế cho nhau.

Ví dụ, ở câu lệnh `int count = names.size();`:

- Nút `MethodInvocationTree` thể hiện cú pháp lời gọi `names.size()`.
- `Trees.getElement(TreePath)` có thể cho biết phương thức `size` nào đã được phân giải; kết quả thường là `ExecutableElement` có `ElementKind.METHOD`.
- `Trees.getTypeMirror(TreePath)` trên **đường dẫn tới toàn bộ biểu thức lời gọi** cho kiểu kết quả `int`.
- Nút `IdentifierTree` của `names` lại liên hệ tới `VariableElement` của biến local và có kiểu sử dụng `java.util.List<java.lang.String>`.

Khả năng nối ba biểu diễn này là nền tảng của linter, kiểm tra API, code navigation, refactoring và annotation processor có phân tích sâu mã nguồn. API công khai được dùng ở đây là **`com.sun.source.util.Trees`** và **`TreePath`** trong module JDK `jdk.compiler`, kết hợp `com.sun.source.tree`, `javax.lang.model.element` và `javax.lang.model.type`. Đây là các API tài liệu hóa dành cho cây cú pháp của compiler; không cần dựa vào các lớp nội bộ `com.sun.tools.javac.*`.

Bài này dùng Java 17+ và các ví dụ đã được biên dịch, chạy với JDK 24 nhắm `--release 17`.

## 1. Tree, Element và TypeMirror trả lời những câu hỏi khác nhau

| Đối tượng | Mô tả | Ví dụ | Câu hỏi phù hợp |
| --- | --- | --- | --- |
| `Tree` | Nút cú pháp trong source | `IdentifierTree`, `MethodInvocationTree`, `VariableTree` | “Người viết code đã dùng cấu trúc gì?” |
| `CompilationUnitTree` | Đơn vị biên dịch, thường tương ứng một tệp Java | import, package, top-level declarations | “Nút nằm trong nguồn nào?” |
| `TreePath` | Đường dẫn từ đơn vị nguồn qua cha tới một nút hiện tại | đường tới `names` bên trong `names.size()` | “Nút này thuộc ngữ cảnh nào?” |
| `Element` | Khai báo/symbol sau phân giải tên | class, method, field, local variable | “Tên này liên kết với khai báo nào?” |
| `TypeMirror` | Kiểu theo mô hình ngôn ngữ | `int`, `List<String>`, type variable | “Biểu thức hoặc khai báo có kiểu gì?” |
| `Trees` | Cầu nối giữa các biểu diễn | `getElement`, `getTypeMirror`, `getPath` | “Từ cú pháp, đến symbol hoặc kiểu bằng cách nào?” |

Các mô hình này không đồng nhất:

- **`Tree` không phải đối tượng runtime**. Nó mô tả source, không phải instance của class lúc chạy.
- **`Element` không phải `Class<?>` hay `java.lang.reflect.Method`**. Đây là biểu diễn trong giai đoạn biên dịch.
- **`TypeMirror` không phải `java.lang.reflect.Type`**. Nó bao gồm những kiểu mà compiler suy luận từ nguồn, kể cả generic/wildcard/type variable và các dạng lỗi hoặc chưa đầy đủ.
- Một `Tree` không nhất thiết có `Element` tương ứng, nhưng vẫn có thể có một kiểu biểu thức.
- Một `Element` có thể đến từ classpath/module path và **không có cây source tương ứng** trong compilation task hiện tại.

Điểm mấu chốt: **phải xác định đang hỏi về cú pháp, khai báo hay kiểu của biểu thức** trước khi chọn API.

## 2. TreePath quan trọng vì một nút cần ngữ cảnh

`Tree` biểu diễn một nút; chỉ nhìn nút chưa đủ để xác định hết ngữ nghĩa. Cùng chữ `size` có thể xuất hiện trong phương thức của nhiều class, trong biến local hoặc trong một lời gọi sau generic inference. Ngữ cảnh ở các nút cha, scope, receiver và import tham gia vào việc phân giải.

`TreePath` mang một chuỗi quan hệ:

```text
CompilationUnitTree
    |
    +-- ClassTree Example
           |
           +-- MethodTree run
                  |
                  +-- VariableTree count
                         |
                         +-- MethodInvocationTree names.size()
                                |
                                +-- MemberSelectTree names.size
                                       |
                                       +-- IdentifierTree names
```

Mô hình trên chỉ biểu thị phần đáng chú ý, không liệt kê tất cả node trung gian của AST. Khi scanner ở `MethodInvocationTree`, `getCurrentPath()` trả đường đi tới lời gọi. Khi scanner ở `IdentifierTree names`, đường đi tới **chính identifier** đó.

API cốt lõi:

```java
Element element = trees.getElement(path);
TypeMirror type = trees.getTypeMirror(path);
```

Hai dòng này là **mảnh minh họa trong nơi đã có `Trees trees` và `TreePath path`**, không phải chương trình độc lập. Kết quả có thể khác nhau giữa hai path, dù các nút đều nằm trong cùng một câu lệnh.

**Không nên tạo một `TreePath` tùy tiện bằng cách chỉ giữ tham chiếu `Tree`**. Hãy sử dụng `TreePathScanner` để bảo trì đường dẫn trong lúc duyệt, hoặc API như `Trees.getPath(element)` / `TreePath.getPath(compilationUnit, tree)` khi đã có đủ thông tin.

## 3. Các API trọng tâm của Trees

Nhóm phương thức thường dùng của `com.sun.source.util.Trees`:

| API | Kết quả | Chú ý |
| --- | --- | --- |
| `Trees.instance(JavacTask)` | Cầu nối tới compiler task dùng javac | Dùng trong công cụ compiler API chủ động parse/analyze |
| `Trees.instance(ProcessingEnvironment)` | Cầu nối của môi trường annotation processing | Dùng trong processor khi implementation hỗ trợ Trees |
| `trees.getElement(TreePath)` | `Element` gắn với tree node | Có thể `null` nếu không có symbol hoặc không xác định |
| `trees.getTypeMirror(TreePath)` | `TypeMirror` của tree node | Có thể `null` hoặc là kiểu lỗi khi thông tin chưa đủ |
| `trees.getPath(Element)` | Đường dẫn tới khai báo của phần tử | Có thể `null` khi không có nguồn tương ứng |
| `trees.getPath(CompilationUnitTree, Tree)` | Đường dẫn tới nút thuộc unit đã cho | Chỉ dùng khi biết rõ nguồn và nút |
| `trees.getTree(Element)` | Cây khai báo tương ứng phần tử | Có thể `null` với phần tử không có source |
| `trees.getSourcePositions()` | Bộ truy vấn offset nguồn của tree | Dùng cùng unit và `LineMap` để lấy line/column |
| `trees.printMessage(...)` | Diagnostic gắn vào một `Tree` | Hữu ích khi muốn highlight một biểu thức/cú pháp cụ thể |

**Lưu ý về loại tham số:** `Trees.getTypeMirror` ở đây nhận **`TreePath`**, không phải `Element` hay `Tree` đơn lẻ. `Element.asType()` cũng trả `TypeMirror`, nhưng trả **kiểu gắn với khai báo**; nó không tự thay thế kiểu cụ thể của một biểu thức tại vị trí sử dụng.

Một số phương thức có thể ném `IllegalArgumentException` nếu đưa vào `TreePath` không phù hợp với đối tượng yêu cầu; các API cũng có thể trả `null` khi thông tin không có. Công cụ phân tích nên xử lý hai tình huống này một cách có chủ đích thay vì luôn ép kiểu hoặc gọi `toString()` không kiểm tra.

## 4. Quy trình với JavaCompiler: parse → analyze → scan

Khi dùng `javax.tools.JavaCompiler`, có hai kiểu hoạt động phổ biến:

1. **Biên dịch file Java thông thường:** compiler tự thực hiện phân tích và tạo class file.
2. **Viết công cụ phân tích source:** lấy `JavacTask`, gọi `parse()` và `analyze()`, rồi dùng `Trees` để truy vấn semantics của các nút.

Dạng công cụ thứ hai phù hợp để trình diễn *Tree → Element/TypeMirror*. Chỉ parse syntax chưa bảo đảm có đầy đủ symbol/kiểu: compiler có thể chưa giải quyết tên, generic, overload hoặc import. `analyze()` buộc compiler tiến hành phân tích ngữ nghĩa cho task.

```text
JavaCompiler + JavaFileObject
            |
            v
JavacTask.parse()  ---> CompilationUnitTree
            |
            v
JavacTask.analyze() ---> symbol/type attribution
            |
            v
Trees.instance(task)
            |
            v
TreePathScanner.scan(compilationUnit, null)
            |
            +--> getCurrentPath()
                   |
                   +--> trees.getElement(path)
                   +--> trees.getTypeMirror(path)
```

`parse()` trả về các đơn vị nguồn cú pháp; `analyze()` trả các phần tử khai báo được phân tích, nhưng ta không cần dùng giá trị trả về khi chỉ muốn phân tích những `CompilationUnitTree` đã được parse. Không gọi `generate()` nếu mục tiêu chỉ là phân tích. Trong công cụ thật, cần cấu hình diagnostics và classpath/module path để resolution chính xác.

## 5. Ví dụ hoàn chỉnh: lấy Element và TypeMirror từ nút Tree

Tạo file **`TreesBridgeDemo.java`**:

```java
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.IdentifierTree;
import com.sun.source.tree.MethodInvocationTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.TreePathScanner;
import com.sun.source.util.Trees;
import java.net.URI;
import java.util.List;
import javax.lang.model.element.Element;
import javax.lang.model.type.TypeMirror;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class TreesBridgeDemo {
    static final class Source extends SimpleJavaFileObject {
        private final String text;

        Source(String name, String text) {
            super(URI.create("string:///" + name.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.text = text;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return text;
        }
    }

    public static void main(String[] args) throws Exception {
        String code = """
                import java.util.List;
                class Example {
                    void run() {
                        List<String> names = List.of("Ada");
                        int count = names.size();
                    }
                }
                """;

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();

        try (StandardJavaFileManager files =
                compiler.getStandardFileManager(null, null, null)) {
            JavacTask task = (JavacTask) compiler.getTask(
                    null,
                    files,
                    null,
                    List.of("--release", "17", "-proc:none"),
                    null,
                    List.of(new Source("Example", code)));

            Iterable<? extends CompilationUnitTree> units = task.parse();
            task.analyze();

            Trees trees = Trees.instance(task);

            for (CompilationUnitTree unit : units) {
                new TreePathScanner<Void, Void>() {
                    @Override
                    public Void visitIdentifier(
                            IdentifierTree node, Void unused) {
                        if (node.getName().contentEquals("names")) {
                            Element symbol =
                                    trees.getElement(getCurrentPath());
                            TypeMirror type =
                                    trees.getTypeMirror(getCurrentPath());

                            System.out.println(
                                    "identifier=" + node.getName());
                            System.out.println(
                                    "element-kind=" + symbol.getKind());
                            System.out.println(
                                    "element-name=" + symbol.getSimpleName());
                            System.out.println(
                                    "expression-type=" + type);
                        }
                        return super.visitIdentifier(node, unused);
                    }

                    @Override
                    public Void visitMethodInvocation(
                            MethodInvocationTree node, Void unused) {
                        if (node.getMethodSelect().toString()
                                .equals("names.size")) {
                            Element method =
                                    trees.getElement(getCurrentPath());
                            TypeMirror resultType =
                                    trees.getTypeMirror(getCurrentPath());

                            System.out.println(
                                    "call=" + node.getMethodSelect());
                            System.out.println(
                                    "target-kind=" + method.getKind());
                            System.out.println(
                                    "target-name=" + method.getSimpleName());
                            System.out.println(
                                    "call-type=" + resultType);
                        }
                        return super.visitMethodInvocation(node, unused);
                    }
                }.scan(unit, null);
            }
        }
    }
}
```

Đây là **một chương trình chạy độc lập** trên JDK 17+. Chạy ở thư mục chứa file:

```bash
javac --release 17 TreesBridgeDemo.java
java TreesBridgeDemo
```

Stdout **đã kiểm chứng trên JDK 24 với `--release 17`**:

```text
call=names.size
target-kind=METHOD
target-name=size
call-type=int
identifier=names
element-kind=LOCAL_VARIABLE
element-name=names
expression-type=java.util.List<java.lang.String>
```

Các dòng xuất hiện theo thứ tự scanner duyệt: `visitMethodInvocation` in trước, sau đó gọi `super.visitMethodInvocation` để xuống những nút con, nơi `visitIdentifier` gặp `names`.

Đầu ra là dữ liệu **của compiler xử lý source `Example`**, không phải kết quả chạy `Example.run()`. Trong bài lab, lớp `Example` không có `main`; chương trình chạy thực tế là `TreesBridgeDemo` và **không thực thi** đoạn `names.size()` như một ứng dụng Java bình thường. Compiler phân tích ngữ nghĩa của lời gọi và cho ta symbol/type.

### Phân tích chính xác từng dòng

| Dòng stdout | API | Ý nghĩa |
| --- | --- | --- |
| `call=names.size` | `MethodInvocationTree.getMethodSelect()` | Dạng biểu thức chọn method trong nguồn |
| `target-kind=METHOD` | `trees.getElement(path).getKind()` | Compiler liên kết lời gọi với một khai báo phương thức |
| `target-name=size` | `Element.getSimpleName()` | Tên khai báo được resolve |
| `call-type=int` | `trees.getTypeMirror(path)` | Kiểu của **toàn bộ biểu thức gọi** `names.size()` |
| `identifier=names` | `IdentifierTree.getName()` | Chữ định danh xuất hiện trong source |
| `element-kind=LOCAL_VARIABLE` | `trees.getElement(path).getKind()` | Tên `names` trỏ đến khai báo biến local |
| `element-name=names` | `Element.getSimpleName()` | Tên của symbol biến |
| `expression-type=List<String>` | `trees.getTypeMirror(path)` | Kiểu biểu thức tham chiếu biến `names` theo thông tin compile-time |

**Điều kiện của output:** chương trình dùng đúng source Java và JDK đã được kiểm chứng. `TypeMirror.toString()` cho kiểu generic có thể khác về hình thức trình bày giữa compiler implementation; vì vậy công cụ sản xuất nên truy vấn `TypeKind` và dùng `Types`/`Elements` để so sánh kiểu, thay vì so một chuỗi toString cứng.

## 6. Vì sao getElement và getTypeMirror không trả cùng một thứ?

Hãy xét:

```java
List<String> names = List.of("Ada");
int count = names.size();
```

Trên path của **`IdentifierTree names`**:

- `getElement` liên kết đến biến local `names`. Nó là **`VariableElement`**.
- `getTypeMirror` cho kiểu biểu thức `names`, ở đây là `List<String>`.

Trên path của **`MethodInvocationTree names.size()`**:

- `getElement` liên kết đến method được chọn `size()`, ở đây có `ElementKind.METHOD`.
- `getTypeMirror` cho **kiểu kết quả của lời gọi** là `int`.

Với lời gọi method generic như `List.of("Ada")`, sự khác nhau có thể rõ hơn: một `ExecutableElement` mô tả khai báo generic và các type parameters của nó; kiểu của **biểu thức gọi sau type inference** có thể là `List<String>`. Không lấy trực tiếp `methodElement.asType()` rồi giả định đó là kiểu kết quả **sau tất cả suy luận kiểu tại điểm gọi**.

Tương tự, `Tree.toString()` biểu diễn dạng source có thể tiện để debug, nhưng không đủ để nhận diện method được overload: hai method cùng tên có thể có danh sách tham số khác nhau. Nên đọc `ExecutableElement` thực tế, loại tham số, owner và signature khi cần.

### Element có nhiều loại cụ thể

`Element` là interface tổng quát. Các dạng thường gặp:

- `TypeElement`: class, interface, enum, record, annotation type.
- `ExecutableElement`: method, constructor và một số executable-related declarations.
- `VariableElement`: field, local variable, formal parameter, enum constant.
- `PackageElement`: khai báo package.
- `ModuleElement`: named module.

Đừng ép mọi kết quả của `getElement` sang `ExecutableElement`. Nên kiểm tra `getKind()` hoặc `instanceof` rồi mới cast. Với source đang có lỗi, symbol có thể không như kỳ vọng; xử lý `null` và các trạng thái lỗi.

### TypeMirror cũng có nhiều loại

- `PrimitiveType` (ví dụ `int`) có `TypeKind.INT`.
- `DeclaredType` (ví dụ `java.util.List<java.lang.String>`) giữ thông tin kiểu đối số.
- `ArrayType`, `TypeVariable`, `WildcardType`, `ExecutableType`, `NoType` và `ErrorType` phục vụ những cấu trúc khác nhau.

`TypeMirror.toString()` hữu ích để in log, nhưng để kiểm tra ngữ nghĩa đúng nên dùng `TypeMirror.getKind()`, interface con phù hợp, và `Types.isSameType(...)` hoặc `Types.isAssignable(...)`. Quan hệ subtype và assignability không phải lúc nào có thể suy ra từ tên chuỗi.

## 7. TreePathScanner so với TreeScanner

Cả hai đều giúp duyệt cây, nhưng mục tiêu khác nhau.

| Scanner | Quản lý đường dẫn hiện tại? | Khi nào đủ? |
| --- | --- | --- |
| `TreeScanner<R,P>` | Không tự cung cấp `getCurrentPath()` | Chỉ cần đếm/quan sát hình dạng AST |
| `TreePathScanner<R,P>` | Có, qua `getCurrentPath()` khi được khởi tạo đúng | Cần gọi `Trees.getElement` / `getTypeMirror` trên từng nút |

Một ví dụ chỉ đếm số `MethodInvocationTree` có thể dùng `TreeScanner`. Khi phải hỏi lời gọi liên kết với khai báo method nào, **`TreePathScanner` thường thuận tiện hơn** vì giữ đường dẫn.

Lưu ý quan trọng từ Java API: để khởi tạo current path, bắt đầu bằng **`scan(TreePath, p)`** hoặc **`scan(CompilationUnitTree, p)`**. `scan(Tree, p)` dành cho việc duyệt các node con sau khi đã có path hoặc trường hợp khởi tạo đặc biệt từ compilation unit. Đừng tùy tiện gọi `scan(methodInvocationTree, null)` từ một scanner hoàn toàn mới rồi kỳ vọng `getCurrentPath()` luôn hợp lệ.

Trong ví dụ đã chạy:

```java
new TreePathScanner<Void, Void>() {
    // overrides ...
}.scan(unit, null);
```

`unit` là `CompilationUnitTree` nên scanner có thể khởi tạo root path và lần theo các node con. Trong annotation processor ở phần sau, ta bắt đầu từ **`TreePath` của phần tử root** nên dùng `scan(path, null)`.

### Gọi super để đi tiếp vào con

Trong override:

```java
@Override
public Void visitMethodInvocation(
        MethodInvocationTree node, Void unused) {
    // Kiểm tra node hiện tại ...
    return super.visitMethodInvocation(node, unused);
}
```

`super.visitMethodInvocation` cho phép scanner tiếp tục duyệt những node con. Nếu chỉ `return null` sau khi xử lý một lời gọi, bạn có thể vô tình **bỏ qua các identifier/biểu thức con**, khiến phân tích thiếu dữ liệu.

Trường hợp cố ý prune một subtree có thể phù hợp với một số công cụ, nhưng phải xác định ý định rõ. Đó không phải cách mặc định khi muốn kiểm tra toàn bộ lời gọi.

## 8. Từ Element trở lại Tree: getPath(Element) và getTree(Element)

`Trees` còn hỗ trợ chiều ngược lại: từ một `Element` đã resolve sang đường dẫn hoặc cây khai báo nguồn:

```java
TreePath declarationPath = trees.getPath(element);
```

Nếu `declarationPath != null`, bạn có thể đọc `declarationPath.getLeaf()` để biết tree node biểu diễn khai báo và `getCompilationUnit()` để biết đơn vị nguồn. Có thể dùng `trees.getTree(element)` để lấy tree của khai báo khi phù hợp.

Nhưng **không bảo đảm luôn có source tree**:

- `java.util.List` từ JDK được compiler biết qua module/class file, nhưng task phân tích nguồn `Example` không nhất thiết chứa AST khai báo của lớp này.
- Một method được dùng từ JAR thư viện không có source có thể có `ExecutableElement` hoàn toàn hợp lệ, trong khi `trees.getPath(methodElement)` trả `null`.
- Với phần tử do processor hoặc compiler tạo ra, source/path có thể không có, hoặc không tương ứng với một đoạn source người dùng viết trực tiếp.

Vì vậy, phân biệt:

```java
Element symbol = trees.getElement(useSitePath);
TreePath declaration = symbol == null ? null : trees.getPath(symbol);
```

Đoạn này là **mảnh code minh họa trong ngữ cảnh đã có `trees` và `useSitePath`**, không phải file Java hoàn chỉnh. `useSitePath` mô tả **vị trí sử dụng**, còn `declaration` mô tả **vị trí khai báo** nếu có. Hai path khác nhau, dù trỏ đến cùng một symbol.

Đây chính là nguyên lý dùng trong tính năng **Go to Definition** của IDE: từ identifier hiện tại → symbol → vị trí khai báo. Khi không có source đi kèm dependency, IDE có thể mở bytecode/decompiled source hoặc metadata theo thiết kế của chính IDE, không phải bởi `Trees` tự sinh source.

## 9. Dùng Trees trong annotation processor

`Trees` có overload:

```java
Trees trees = Trees.instance(processingEnv);
```

Bên trong `AbstractProcessor`, `processingEnv` được khởi tạo khi processor nhận môi trường. Với `javac` tương thích, có thể dùng `Trees` để đi sâu vào cú pháp của phần tử được annotation processing nhìn thấy.

Một nguyên tắc cấu trúc:

1. Nhận `Element` từ `RoundEnvironment.getRootElements()` hoặc tập element được annotate.
2. Lấy `TreePath path = trees.getPath(element)`.
3. Kiểm tra path khác `null`: element từ classpath có thể không có AST source.
4. Dùng `new TreePathScanner<...>() {...}.scan(path, null)` để duyệt từ vị trí khai báo.
5. Trong mỗi `visit...`, gọi `trees.getElement(getCurrentPath())` hoặc `trees.getTypeMirror(getCurrentPath())` khi cần semantic information.

Không nên giả định **mọi** processor implementation trên mọi compiler đều hỗ trợ `com.sun.source.util.Trees`; đây là API có ý nghĩa với compiler tree model mà implementation đang dùng. Cần kiểm tra và cung cấp thông báo phù hợp nếu công cụ không hỗ trợ.

### 9.1. Processor hoàn chỉnh: TreeInspectorProcessor.java

Tạo file **`TreeInspectorProcessor.java`**:

```java
import com.sun.source.tree.IdentifierTree;
import com.sun.source.tree.MethodInvocationTree;
import com.sun.source.util.TreePath;
import com.sun.source.util.TreePathScanner;
import com.sun.source.util.Trees;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.ProcessingEnvironment;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.lang.model.type.TypeMirror;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("*")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class TreeInspectorProcessor extends AbstractProcessor {
    private Trees trees;

    @Override
    public synchronized void init(ProcessingEnvironment environment) {
        super.init(environment);
        trees = Trees.instance(environment);
    }

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment round) {
        if (round.processingOver()) {
            return false;
        }

        for (Element root : round.getRootElements()) {
            TreePath path = trees.getPath(root);
            if (path == null) {
                continue;
            }

            new TreePathScanner<Void, Void>() {
                @Override
                public Void visitIdentifier(
                        IdentifierTree node, Void unused) {
                    if (node.getName().contentEquals("data")) {
                        Element symbol =
                                trees.getElement(getCurrentPath());
                        TypeMirror type =
                                trees.getTypeMirror(getCurrentPath());

                        processingEnv.getMessager().printMessage(
                                Diagnostic.Kind.NOTE,
                                "identifier " + symbol.getSimpleName()
                                    + " = " + type);
                    }
                    return super.visitIdentifier(node, unused);
                }

                @Override
                public Void visitMethodInvocation(
                        MethodInvocationTree node, Void unused) {
                    if (node.getMethodSelect().toString()
                            .equals("data.size")) {
                        Element method =
                                trees.getElement(getCurrentPath());
                        TypeMirror type =
                                trees.getTypeMirror(getCurrentPath());

                        processingEnv.getMessager().printMessage(
                                Diagnostic.Kind.NOTE,
                                "call " + method.getSimpleName()
                                    + " returns " + type);
                    }
                    return super.visitMethodInvocation(node, unused);
                }
            }.scan(path, null);
        }
        return false;
    }
}
```

Bài lab dùng `@SupportedAnnotationTypes("*")` để processor nhận các annotation types mà compiler giao và xử lý root elements; đây là cách trình diễn kỹ thuật, **không phải khuyến nghị mọi processor sản xuất nên claim tất cả annotation**. `return false` thể hiện processor không claim những annotation types nó chỉ quan sát.

`@SupportedSourceVersion(RELEASE_17)` khớp với tham số `--release 17` bên dưới. Đừng đổi sang Java source version mới hơn mà quên kiểm tra supported source version thực của processor.

### 9.2. Source được processor kiểm tra

Tạo file **`Sample.java`**:

```java
import java.util.List;

class Sample {
    void check() {
        List<String> data = List.of("A");
        int length = data.size();
    }
}
```

Không có `main` vì ví dụ này chủ yếu chứng minh việc compiler/processor đọc biểu thức. Nó vẫn là source Java hợp lệ.

### 9.3. Biên dịch và chạy processor

Tại thư mục chứa cả hai file:

```bash
javac --release 17 -d proc TreeInspectorProcessor.java
javac --release 17 -processorpath proc -processor TreeInspectorProcessor -proc:only Sample.java
```

Lệnh thứ nhất biên dịch processor vào thư mục `proc`. Lệnh thứ hai **khởi chạy processor trong javac**, không tạo `Sample.class` vì có `-proc:only`.

Trích yếu diagnostic **đã kiểm chứng trên JDK 24, `--release 17`**:

```text
Note: call size returns int
Note: identifier data = java.util.List<java.lang.String>
```

Cả hai lệnh biên dịch trả exit code **0** trong trường hợp này. Diagnostics `NOTE` được trình biên dịch hiển thị (thường ở stderr); không phải stdout của một chương trình `Sample.main`.

Vì sao nó hoạt động?

- `trees.getPath(root)` cung cấp vị trí cú pháp của class `Sample`.
- `TreePathScanner.scan(path, null)` duyệt vào method `check` và các biểu thức.
- Tại `data.size()`, `trees.getElement` cho element của method và `getTypeMirror` cho kiểu kết quả `int`.
- Tại identifier `data`, `getElement` cho biến local và `getTypeMirror` cho kiểu `List<String>`.
- `Messager.printMessage(NOTE, ...)` ở bài lab in thông tin để quan sát; một processor thực tế có thể dùng kết quả này để kiểm tra policy và phát `WARNING`/`ERROR` phù hợp.

**Cẩn thận:** vì processor ví dụ không gắn `NOTE` vào `Element`, diagnostic in ra không có vị trí nguồn cụ thể. Nếu muốn đánh dấu chính một `Tree`, có thể dùng `Trees.printMessage(...)` với `CompilationUnitTree`, như phần sau. Với lỗi gắn vào khai báo, `Messager.printMessage(kind,msg,element)` vẫn hữu ích.

## 10. Gắn diagnostic vào Tree cụ thể

Ở annotation processor, `Messager` hỗ trợ gắn message với `Element`, `AnnotationMirror` và `AnnotationValue`. Khi vấn đề lại nằm ở **một biểu thức cú pháp** (ví dụ một phép gọi không được phép), `Trees` có phương thức:

```java
trees.printMessage(
    Diagnostic.Kind.WARNING,
    "Avoid this call in this context",
    getCurrentPath().getLeaf(),
    getCurrentPath().getCompilationUnit()
);
```

Đoạn trên là mảnh minh họa **bên trong một visitor thuộc TreePathScanner**, nơi `trees` và `getCurrentPath()` hợp lệ. `CompilationUnitTree` xác định đơn vị nguồn của leaf; compiler có thể gắn diagnostic vào vị trí tương ứng. Không cần tự tính số dòng/cột để tạo thông báo vị trí cơ bản.

Phân biệt:

| Cơ chế | Đối tượng để gắn vị trí | Khi thích hợp |
| --- | --- | --- |
| `Messager.printMessage(kind,msg,element)` | Khai báo/Element | Lỗi của toàn class, method hoặc field |
| `Messager.printMessage(...,element,annotationMirror,value)` | Giá trị annotation | Validation annotation cụ thể |
| `Trees.printMessage(kind,msg,tree,unit)` | Tree trong một source unit | Lỗi của biểu thức/lời gọi/source syntax |

**Đừng kết luận Trees chỉ dùng để đọc.** Nó còn hỗ trợ những tiện ích có ngữ cảnh source như `getSourcePositions()` và `printMessage(...)`, làm nền cho công cụ kiểm tra mã nguồn có chất lượng developer experience tốt.

## 11. Lấy dòng/cột từ AST bằng SourcePositions và LineMap

Nếu cần lưu vị trí cho IDE, JSON report hoặc hệ thống navigation:

```java
CompilationUnitTree unit = path.getCompilationUnit();
long start = trees.getSourcePositions()
                  .getStartPosition(unit, path.getLeaf());

long end = trees.getSourcePositions()
                .getEndPosition(unit, path.getLeaf());

if (start >= 0) {
    long line = unit.getLineMap().getLineNumber(start);
    long column = unit.getLineMap().getColumnNumber(start);
}
```

Đoạn trên **chỉ minh họa trong một method có biến `path` và `trees`**, chưa là chương trình độc lập; `end` có thể được dùng để lưu range. Offset chưa biết có thể được biểu diễn bằng giá trị âm theo hợp đồng API. Đừng cố dùng offset làm chỉ số vào một `String` khác đã thay đổi nội dung hoặc normalization vì vị trí sẽ sai.

`TreePath` có `getCompilationUnit()` và `getLeaf()`; hai đối tượng này phải thuộc cùng ngữ cảnh compiler tree model. Không đem một `Tree` từ compilation unit A kết hợp với unit B để hỏi vị trí.

### Những trường hợp thiếu vị trí

- Tree hoặc Element xuất phát từ symbol có sẵn trong JAR, không có source tương ứng.
- Source generated, synthetic nodes hoặc những node mà compiler không lưu vị trí đủ chi tiết.
- Mã có lỗi cú pháp/ngữ nghĩa khiến cấu trúc tree không như dự kiến.

Các công cụ nên có fallback: ghi tên symbol, URI nguồn nếu biết, hoặc diagnostic ở vị trí cha phù hợp. Không ép `-1` thành số dòng hợp lệ.

## 12. Lỗi nguồn và trạng thái compiler ảnh hưởng semantics thế nào?

Nếu chỉ gọi `parse()` mà không `analyze()`, cây cú pháp vẫn có thể duyệt được để tìm method invocation, identifier, literal; nhưng `getElement`/`getTypeMirror` có thể không có thông tin semantic đầy đủ.

Nếu source có lỗi như:

```java
class Broken {
    void f() {
        MissingType name = null;
        name.go();
    }
}
```

Đây là đoạn **cố ý lỗi biên dịch** vì `MissingType` không được định nghĩa. Compiler có thể tạo `ErrorType` cho một số nút, thiếu symbol hoặc báo diagnostic; việc gọi `getTypeMirror(path)` không bảo đảm một DeclaredType hợp lệ. Hãy xử lý:

```java
Element symbol = trees.getElement(path);
TypeMirror type = trees.getTypeMirror(path);

if (symbol == null || type == null) {
    // Không có đủ thông tin semantic tại vị trí này.
}
```

Mã trên là mảnh minh họa trong ngữ cảnh đã có `trees` và `path`. Cần phân biệt `type == null` với `type.getKind() == TypeKind.ERROR`; một `ErrorType` vẫn là một đối tượng TypeMirror nhưng biểu diễn kiểu đang lỗi.

Đừng chạy một linter và tuyên bố “không có vấn đề” chỉ vì các truy vấn type trả `null` khi chương trình nguồn đã có lỗi. Cần collect diagnostics của compiler và quyết định có tiếp tục quy tắc phụ thuộc type hay không.

## 13. Generics: Element.asType và Trees.getTypeMirror khác nhau

Xem:

```java
import java.util.List;

class GenericUse {
    void consume() {
        List<String> words = List.of("A");
        String first = words.get(0);
    }
}
```

Nút gọi `words.get(0)` liên kết với khai báo method `get(int)` của `List<E>`. Nhưng tại lời gọi cụ thể, receiver là `List<String>`, nên **kiểu biểu thức gọi** là `String`.

Khi code analysis cần kiểm tra kiểu của **kết quả ở use site**, thường dùng:

```java
TypeMirror resultType = trees.getTypeMirror(callPath);
```

Còn `ExecutableElement` từ:

```java
Element method = trees.getElement(callPath);
```

mô tả **khai báo method**. Việc chỉ gọi `method.asType()` thường cho thông tin chữ ký khai báo/generic form, không tự tương đương kiểu kết quả tại từng invocation.

Đối với các phép toán phức tạp, `javax.lang.model.util.Types` hỗ trợ `asMemberOf`, `isSameType`, `isAssignable` và các phép chuyển đổi type khác; cần xác định đúng receiver type và ngữ cảnh. Không so hai `TypeMirror` bằng `toString()` nếu quyết định ảnh hưởng tính đúng của tool.

### Generic type có thể xuất hiện ở nhiều mức

| Vị trí AST | Element có thể tương ứng | TypeMirror đáng chú ý |
| --- | --- | --- |
| `List<String> words` (khai báo) | `VariableElement` của `words` | Kiểu biến `List<String>` |
| `words` (identifier) | Chính `VariableElement` | Kiểu biểu thức `List<String>` |
| `words.get(0)` (invocation) | `ExecutableElement` của `get` | Kiểu kết quả `String` |
| `"A"` (literal) | Thường không có Element khai báo | Kiểu `String` của literal |
| `words.get` (member selection) | Element method | Kiểu liên quan method/member ở vị trí chọn |

Với literal, `getElement(path)` thường trả `null` vì một literal không tham chiếu khai báo biến hay method; điều đó **không có nghĩa literal không có kiểu**. `getTypeMirror(path)` có thể vẫn trả kiểu primitive hoặc `java.lang.String`.

## 14. Các lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `getCurrentPath()` là `null` | Khởi động `TreePathScanner` từ subtree không có root path | Dùng `scan(unit, null)` hoặc `scan(path, null)` |
| `trees.getElement(path)` trả `null` | Node không liên kết symbol hoặc compiler chưa phân tích đủ | Xem loại node, gọi `analyze()` đúng lúc, xử lý null |
| `getTypeMirror(path)` trả ErrorType | Source hoặc dependency có lỗi semantic | Thu diagnostics, không giả định kiểu hợp lệ |
| Nhận symbol khác mong đợi | Truy vấn path tới member select thay vì invocation hoặc ngược lại | Xác định chính leaf và kiểm tra kiểu node |
| Chỉ biết `MethodInvocationTree.toString()` | So text mà chưa phân giải overload | Dùng `getElement` và `ExecutableElement` |
| Muốn type kết quả mà lại đọc `method.asType()` | Nhầm khai báo generic và type biểu thức | Dùng `getTypeMirror` của invocation path |
| Không mở được source declaration | Symbol đến từ class file/module, `getPath(Element)` null | Xử lý trường hợp không có nguồn |
| Scanner không đi xuống identifier | Override `visitMethodInvocation` không gọi `super` | Duyệt con khi phù hợp |
| Báo sai line/column | Ghép tree với compilation unit khác | Dùng `path.getCompilationUnit()` và source positions cùng task |
| NPE khi duyệt mã lỗi | Không kiểm tra null cho Element/TypeMirror | Phân nhánh thiếu thông tin |
| Biên dịch processor không thấy `Trees` | JDK/compiler implementation hoặc module config không phù hợp | Dùng JDK có `jdk.compiler` và cấu hình đúng; kiểm tra API hỗ trợ |
| Dùng classloader để lấy TypeMirror | Nhầm compile-time type với runtime reflection | Dùng model `javax.lang.model.type` |
| Phân tích nguồn sai thư viện | Classpath/module path khác môi trường dự án | Dùng cùng dependencies, release và options |

**Đừng sửa bằng cách cast bừa** một Element sang TypeElement hay một TypeMirror sang DeclaredType. Hãy kiểm tra `ElementKind`/`TypeKind`, rồi dùng API tương ứng.

## 15. Kiểm chứng với JavacTask và processor: điểm khác nhau

| Đặc điểm | JavacTask phân tích String source | Annotation processor |
| --- | --- | --- |
| Điểm vào | `JavaCompiler.getTask` → cast `JavacTask` | `AbstractProcessor.init/process` |
| Lấy Trees | `Trees.instance(task)` | `Trees.instance(processingEnv)` |
| Gốc để duyệt | `CompilationUnitTree` từ `parse()` | `TreePath` từ `getPath(rootElement)` |
| Phân tích ngữ nghĩa | Gọi `task.analyze()` trước khi query | Compiler điều phối phase/round |
| Tương tác với compiler | Chủ động gọi parse/analyze | Nhận `RoundEnvironment` |
| Diagnostic | DiagnosticListener/Collector hoặc `Trees.printMessage` | `Messager` và `Trees.printMessage` |
| Mục tiêu ví dụ | Công cụ kiểm tra code độc lập | Validation hoặc source analysis trong build |

**Không tự gọi `JavacTask.analyze()` từ annotation processor** như thể processor được quyền điều khiển toàn bộ compiler phase. Trong processor, compiler đã chủ động điều phối processing rounds và mô hình element/type; bạn sử dụng các object nó cung cấp.

### Kiểm thử phù hợp

- Bài `TreesBridgeDemo`: chạy `java TreesBridgeDemo` và so cả symbol/type.
- Bài `TreeInspectorProcessor`: chạy `javac -processor ... -proc:only Sample.java` và kiểm tra các note từ compiler.
- Bài dùng mã lỗi: thu diagnostic compiler, xác minh tool không crash và không báo các phán đoán phụ thuộc type khi type chưa phân giải.
- Bài generic overload: thay argument type và quan sát `Element` trỏ tới method overload nào, `TypeMirror` của invocation thay đổi thế nào.

## 16. Bài tập có đáp án

**Bài 1: Tree và Element**

Trong source `service.run()`, `MethodInvocationTree` và `ExecutableElement` khác nhau thế nào?

**Đáp án:** MethodInvocationTree cho biết cấu trúc lời gọi ở vị trí nguồn; ExecutableElement biểu diễn khai báo phương thức mà compiler chọn khi giải quyết lời gọi. Một method có thể có nhiều call-site Tree nhưng cùng một Element khai báo.

**Bài 2: Vì sao TreePath bắt buộc?**

Có thể dùng `trees.getTypeMirror(identifierTree)` khi chỉ giữ IdentifierTree không?

**Đáp án:** Không; chữ ký của Trees yêu cầu `TreePath`. Dùng TreePathScanner để lấy current path hoặc tạo path đúng từ source unit/element.

**Bài 3: Kiểu của names.size()**

`names` có kiểu `List<String>`. `getTypeMirror` ở `names.size()` trả kiểu gì, và `getElement` trả loại khai báo gì?

**Đáp án:** Kiểu kết quả là `int`, element là method `size` (`ElementKind.METHOD`).

**Bài 4: Generic declaration và use site**

`List<String> words` và `words.get(0)`. Lấy `getElement(callPath).asType()` có chắc bằng kiểu `String` không?

**Đáp án:** Không. Element mô tả method declaration (có thể generic), còn `getTypeMirror(callPath)` mô tả kiểu của biểu thức tại call site sau phân giải ngữ nghĩa.

**Bài 5: Node không có Element**

Một `LiteralTree` biểu diễn `42` có thể có `TypeMirror` `int` dù `getElement` trả `null` không?

**Đáp án:** Có. Literal có kiểu nhưng không tham chiếu tới một khai báo mang tên.

**Bài 6: Reverse lookup**

`getElement` trả method trong thư viện JDK. `trees.getPath(element)` trả null. Có phải method không tồn tại?

**Đáp án:** Không. Symbol có thể đến từ class file/module mà task hiện tại không có source tree. Null ở chiều reverse lookup không phủ định việc đã resolve method.

**Bài 7: Scope của scanner**

Một scanner mới nhận `scan(methodTree, null)` và `getCurrentPath()` không hợp lệ. Khắc phục?

**Đáp án:** Bắt đầu từ CompilationUnitTree hoặc một TreePath hợp lệ, rồi duyệt xuống node bằng scanner.

**Bài 8: Processor phát Note**

Ví dụ processor chỉ in `Note: call size returns int` và `Note: identifier data = ...`. Chương trình Sample có được chạy để tạo output ấy không?

**Đáp án:** Không. Các note phát trong giai đoạn javac xử lý annotation; `Sample` không có `main` và lệnh có `-proc:only`.

**Bài 9: Kiểm tra null và lỗi kiểu**

Nếu source thiếu import type, tool có nên ép mọi `TypeMirror` sang `DeclaredType` để xử lý tiếp?

**Đáp án:** Không. Kiểm tra `null` và `TypeKind.ERROR`, thu diagnostic, chỉ áp dụng rule khi đủ thông tin semantic.

## 17. Checklist viết công cụ phân tích bằng Trees

- [ ] Chạy trên JDK có compiler/tree API tương ứng.
- [ ] Xác định mode: JavacTask độc lập hay annotation processor.
- [ ] Có cấu hình đúng `--release`, classpath hoặc module path.
- [ ] Dùng `CompilationUnitTree` hoặc `TreePath` hợp lệ để khởi tạo scanner.
- [ ] Với scanner, dùng `getCurrentPath()` tại node cần truy vấn.
- [ ] Chỉ hỏi `getElement` trên tree node có thể liên hệ khai báo.
- [ ] Chỉ hỏi `getTypeMirror` sau khi compiler đã có đủ semantic information.
- [ ] Kiểm tra null và `ErrorType` khi mã nguồn sai.
- [ ] Phân biệt kiểu khai báo `Element.asType()` với kiểu biểu thức `Trees.getTypeMirror()`.
- [ ] Không so generic type bằng text khi cần so ngữ nghĩa.
- [ ] Dùng `Trees.getPath(Element)` cho Go to Definition, chấp nhận source không có.
- [ ] Dùng `getSourcePositions` và `LineMap` trong cùng compilation unit.
- [ ] Gọi `super.visit...` nếu cần duyệt toàn bộ subtree.
- [ ] Nếu phát diagnostic, gắn vào đúng Tree/Element và mức độ.
- [ ] Test các trường hợp generic, overloaded method, thiếu import, external library và code generated.
- [ ] Không dùng internal `com.sun.tools.javac.*` khi API `com.sun.source.util` đáp ứng yêu cầu.

## 18. Tóm tắt và tài liệu tra cứu

**`Tree` là cú pháp; `Element` là symbol/khai báo; `TypeMirror` là kiểu trong mô hình compiler.** Để kết nối chúng một cách đáng tin, lấy **`TreePath`** từ `TreePathScanner` hoặc từ các method `Trees.getPath(...)`, rồi gọi `Trees.getElement(path)` và `Trees.getTypeMirror(path)` sau khi thông tin semantic đã sẵn có.

Cùng một dòng mã, **path tới identifier** có thể trả `VariableElement` và `List<String>`, trong khi **path tới method invocation** trả `ExecutableElement` và `int`. Khi viết code analysis, nên chọn path đúng cấp độ rồi xử lý null/kiểu lỗi thay vì dùng string matching như một giải pháp semantic hoàn chỉnh.

Tài liệu chính thống:

1. [Java SE 17 — Trees](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/Trees.html): `getElement`, `getTypeMirror`, `getPath`, `getTree`, `printMessage`.
2. [Java SE 17 — TreePath](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/TreePath.html): đường dẫn AST và compilation unit.
3. [Java SE 17 — TreePathScanner](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/TreePathScanner.html): duyệt AST cùng ngữ cảnh cha.
4. [Java SE 17 — JavacTask](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/JavacTask.html): `parse`, `analyze` và compiler task.
5. [Java SE 17 — Element](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/Element.html): mô hình khai báo.
6. [Java SE 17 — TypeMirror](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/type/TypeMirror.html): mô hình kiểu.
7. [Java SE 17 — Types](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/Types.html): so sánh và suy luận quan hệ kiểu trong công cụ.

**Quy trình ghi nhớ:** *Node nguồn → TreePath → Trees → Element/TypeMirror → kiểm tra ngữ nghĩa*. Làm đúng chuỗi này giúp nhận diện khai báo và kiểu chính xác thay vì chỉ phân tích ký tự của mã Java.
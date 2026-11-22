# Dùng JavacTask để parse, analyze và generate

## 1. Vì sao cần điều khiển từng pha của javac?

Lệnh `javac` bình thường đọc nguồn Java, kiểm tra tính hợp lệ và tạo các file `.class`. Nhưng công cụ như IDE, code indexer, linter, công cụ phân tích kiến trúc hoặc build/test harness có thể cần **quan sát cú pháp trước khi kiểm tra kiểu**, xác định method mà một lời gọi tham chiếu, hoặc chỉ tạo bytecode sau khi mọi phép kiểm tra đã hoàn tất.

JDK cung cấp `com.sun.source.util.JavacTask` trong module **`jdk.compiler`**. Đây là API dành cho compiler `javac`, cho phép:

- `parse()` — phân tích nguồn thành abstract syntax trees (AST), trả về các `CompilationUnitTree`.
- `analyze()` — hoàn tất phân tích ngữ nghĩa, trả về các `Element` được phân tích; sau bước này compiler có thể trả các symbol và type đã được resolve.
- `generate()` — sinh output của compiler, điển hình là `.class`, dưới dạng các `JavaFileObject`.
- `Trees.instance(task)` — kết nối AST với mô hình ngôn ngữ, `Element`, `TypeMirror` và vị trí source.
- `addTaskListener(...)` — nhận các sự kiện `PARSE`, `ENTER`, `ANALYZE`, `GENERATE` và khi phù hợp là annotation processing.

**Phân biệt:** `JavacTask` là một implementation chuyên biệt của `JavaCompiler.CompilationTask`. Không phải mọi compiler tuân theo `javax.tools.JavaCompiler` đều phải cung cấp `JavacTask`. `ToolProvider.getSystemJavaCompiler()` trên một JDK có `javac` thường cung cấp task có thể ép kiểu sang `JavacTask`, nhưng nên kiểm tra `instanceof`.

Bài học này giới thiệu ba pha và ví dụ Java 17+ đã được thử bằng OpenJDK 21: đọc class/method từ AST, đọc type sau analyze, generate class rồi thực thi.

## 2. Đọc đúng ba tầng của một lần compile

| Bước | API | Dữ liệu nhận được | Những điều chưa bảo đảm |
| --- | --- | --- | --- |
| **Parse** | `JavacTask.parse()` | `CompilationUnitTree`, `ClassTree`, `MethodTree`, `VariableTree` và các node khác | Tất cả tên/kiểu đã resolve; chương trình hợp lệ về ngữ nghĩa |
| **Analyze** | `JavacTask.analyze()` | `Element` được phân tích; thông tin tên, kiểu, ràng buộc | Đã phát xong tất cả file `.class` |
| **Generate** | `JavacTask.generate()` | `JavaFileObject` cho các file được sinh ra | Chương trình chạy được trên mọi runtime/classpath |

Sơ đồ tư duy:

```text
Java source (.java)
       |
       v
PARSE
       | CompilationUnitTree, ClassTree, MethodTree
       v
ENTER + ANALYZE
       | Element, TypeMirror, symbol resolution, diagnostics
       v
GENERATE
       | .class output / JavaFileObject
       v
Runtime (bước riêng, nếu cần chạy kiểm thử)
```

Sơ đồ không phải mô tả đầy đủ mọi phase nội bộ của `javac`. Compiler có thể xử lý nhiều source files, nguồn được phát hiện ngầm, annotation processing rounds, ENTER và các công việc phụ khác. Một lời gọi `parse()` hoặc `analyze()` cũng có thể khiến compiler làm thêm những công việc cần thiết để hoàn tất pha đó.

Cần đặc biệt nhớ rằng **`JavacTask.generate()` khác `Filer.createSourceFile(...)` của annotation processor**. Phương thức đầu tạo output compiler; phương thức sau để processor sinh Java source mới phục vụ các rounds.

## 3. API ở đâu, và vì sao không nên dùng internals?

| Thành phần | Module | Vai trò |
| --- | --- | --- |
| `javax.tools.JavaCompiler`, `StandardJavaFileManager`, `DiagnosticCollector` | `java.compiler` | Tạo task, quản lý file và diagnostics |
| `javax.lang.model.element.Element`, `TypeElement`, `ExecutableElement` | `java.compiler` | Khai báo và phương thức đã được compiler hiểu |
| `javax.lang.model.type.TypeMirror`, `Types` | `java.compiler` | Kiểu Java và kiểm tra quan hệ kiểu |
| `com.sun.source.tree.*` | `jdk.compiler` | Giao diện AST (cây cú pháp) |
| `com.sun.source.util.JavacTask`, `Trees`, `TreePathScanner` | `jdk.compiler` | Pha compiler và kết nối tree–symbol–type |
| `com.sun.tools.javac.*` | Chi tiết triển khai của compiler | Các internal classes không nên coi là API ổn định |

Tên package `com.sun.source` dễ khiến người đọc nhầm với internal compiler classes, nhưng đây là **Tree API được JDK công bố**. Nó khác với việc truy cập sâu vào `com.sun.tools.javac.*` vốn có thể bị module encapsulation và thay đổi theo phiên bản.

Khi chương trình host là **named module**, nó thường cần:

```java
module source.inspector {
    requires java.compiler;
    requires jdk.compiler;
}
```

Đây là một `module-info.java` minh họa, không phải toàn bộ một project. `java.compiler` cung cấp API chuẩn, `jdk.compiler` cung cấp `JavacTask` và Tree API. Không cần thêm `--add-exports` vô điều kiện để dùng exported public API.

**Module của công cụ host không đồng nhất với module mà công cụ đang phân tích.** Một host có thể dùng `jdk.compiler` để kiểm tra source Java 17 vốn không sử dụng các API compiler.

## 4. Khởi tạo JavacTask an toàn

Cách thông dụng là dùng JSR 199 `JavaCompiler` API:

```java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException("No system compiler");
}

try (StandardJavaFileManager files =
         compiler.getStandardFileManager(diagnostics, null, null)) {
    files.setLocationFromPaths(
            StandardLocation.CLASS_OUTPUT, List.of(outputDirectory));

    var inputs = files.getJavaFileObjectsFromPaths(
            List.of(sourceFile));

    JavaCompiler.CompilationTask compilationTask =
            compiler.getTask(
                    null, files, diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null, inputs);

    if (!(compilationTask instanceof JavacTask task)) {
        throw new IllegalStateException("Not a javac task");
    }

    var parsed = task.parse();
    task.analyze();
    var generated = task.generate();
}
```

**Đây là đoạn minh họa**, chưa runnable riêng lẻ: `diagnostics`, `outputDirectory`, `sourceFile` và imports chưa được khai báo. Ví dụ hoàn chỉnh ở mục 6.

Các quyết định quan trọng:

1. `getSystemJavaCompiler()` có thể trả `null` nếu runtime image của host không chứa system compiler; chạy bằng JDK phù hợp.
2. `getStandardFileManager(...)` cung cấp file manager có thể tạo các compilation units từ `Path`; đóng file manager khi task kết thúc.
3. `CLASS_OUTPUT` là nơi ghi class files, không tự động là runtime classpath của host.
4. `--release 17` ràng buộc mức ngôn ngữ, định dạng class file và Java SE API phù hợp Java 17.
5. `-proc:none` vô hiệu annotation processing trong ví dụ, để không có generated source làm thay đổi số lượng class và phases. Nếu cần processor thực sự, không dùng cờ này.
6. `getTask(..., options, classes, compilationUnits)` có các tham số khác nhau; `options` **không** phải danh sách tên file nguồn; `compilationUnits` mới chứa `JavaFileObject` của nguồn.
7. Cast sang `JavacTask` phải phản ánh provider được sử dụng. Với compiler khác, nên dùng những API chuẩn mà nó cung cấp thay vì cast ép.

## 5. Một compilation task: chọn call() hoặc ba pha

Đối với build không cần phân tích trung gian:

```java
boolean success = Boolean.TRUE.equals(
        compilationTask.call());
```

`call()` thực thi toàn bộ task, trả kết quả thành công/thất bại, và theo hợp đồng compilation task chỉ được gọi **một lần**.

Đối với công cụ muốn kiểm soát các pha:

```java
Iterable<? extends CompilationUnitTree> units =
        task.parse();
// Quan sát AST...

task.analyze();
// Đọc Elements và Types...

Iterable<? extends JavaFileObject> outputs =
        task.generate();
// Đối chiếu outputs...
```

**Không** làm theo quy trình “`parse` → `analyze` → `generate` → `call`” trên cùng task: `call` và ba phase methods là hai cách điều khiển việc biên dịch, không phải hai lượt compile cộng dồn. Chọn một chiến lược, tạo **task mới** nếu muốn chạy compilation khác.

Các phương thức phase-specific có thể ném `IOException` và `IllegalStateException` nếu compiler ở trạng thái không cho phép. Đừng coi một task như cấu trúc không trạng thái có thể gọi parse/analyze/generate lặp lại tùy ý.

## 6. Ví dụ đầy đủ đã kiểm thử: PhaseDemo.java

Chương trình sau tạo `example.Greeter` dưới một thư mục tạm, dùng JavacTask đi qua ba pha, đọc class/method, xác nhận type từ semantic model, lấy `Element` từ `MethodTree`, tạo `Greeter.class` và dùng classloader riêng để kiểm tra method trả về `Hello, Ada`.

Tạo file **`PhaseDemo.java`**:

```java
import com.sun.source.tree.ClassTree;
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.MethodTree;
import com.sun.source.tree.Tree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.TreePath;
import com.sun.source.util.Trees;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.ExecutableElement;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public class PhaseDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("javac-phase-");
        Path src = Files.createDirectories(
                root.resolve("src/example"));
        Path out = Files.createDirectories(root.resolve("out"));
        Path source = src.resolve("Greeter.java");

        Files.writeString(source, """
                package example;
                public class Greeter {
                    private final String name;
                    public Greeter(String name) {
                        this.name = name;
                    }
                    public String hello() {
                        return "Hello, " + name;
                    }
                }
                """);

        JavaCompiler compiler =
                ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "No system compiler in runtime image");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager fm =
                 compiler.getStandardFileManager(
                         diagnostics, null, null)) {
            fm.setLocationFromPaths(
                    StandardLocation.CLASS_OUTPUT, List.of(out));

            var inputs = fm.getJavaFileObjectsFromPaths(
                    List.of(source));

            JavaCompiler.CompilationTask raw = compiler.getTask(
                    null, fm, diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null, inputs);

            if (!(raw instanceof JavacTask task)) {
                throw new IllegalStateException(
                        "Compiler provider is not javac");
            }

            // PHA 1: Parse thành AST.
            Iterable<? extends CompilationUnitTree> parsed =
                    task.parse();
            CompilationUnitTree unit = parsed.iterator().next();

            ClassTree clazz = null;
            for (Tree declaration : unit.getTypeDecls()) {
                if (declaration instanceof ClassTree c) {
                    clazz = c;
                    break;
                }
            }
            if (clazz == null) {
                throw new IllegalStateException(
                        "No class declaration");
            }

            MethodTree helloTree = null;
            for (Tree member : clazz.getMembers()) {
                if (member instanceof MethodTree method
                        && method.getName().contentEquals("hello")) {
                    helloTree = method;
                }
            }
            if (helloTree == null) {
                throw new IllegalStateException(
                        "Missing hello method");
            }

            System.out.println(
                    "parsed=" + clazz.getSimpleName());

            // PHA 2: Resolve declarations và types.
            task.analyze();
            TypeElement type = task.getElements()
                    .getTypeElement("example.Greeter");
            if (type == null) {
                throw new IllegalStateException(
                        "Type was not resolved");
            }

            ExecutableElement hello = null;
            for (Element element : type.getEnclosedElements()) {
                if (element.getKind() == ElementKind.METHOD
                        && element.getSimpleName()
                                .contentEquals("hello")) {
                    hello = (ExecutableElement) element;
                }
            }
            if (hello == null) {
                throw new IllegalStateException(
                        "Method was not resolved");
            }

            System.out.println(
                    "analyzed=" + type.getQualifiedName());
            System.out.println(
                    "returnType=" + hello.getReturnType());

            Trees trees = Trees.instance(task);
            TreePath methodPath =
                    TreePath.getPath(unit, helloTree);
            Element fromTree = trees.getElement(methodPath);
            System.out.println(
                    "treeElement=" + fromTree.getSimpleName());

            // PHA 3: Tạo .class.
            List<JavaFileObject> generated = new ArrayList<>();
            task.generate().forEach(generated::add);

            System.out.println(
                    "generated=" + generated.size());
            System.out.println(
                    "classExists=" + Files.isRegularFile(
                            out.resolve("example/Greeter.class")));

            long errors = diagnostics.getDiagnostics().stream()
                    .filter(d ->
                            d.getKind() == Diagnostic.Kind.ERROR)
                    .count();
            System.out.println("errors=" + errors);
        }

        // Bước chạy runtime tách biệt khỏi compiler.
        try (URLClassLoader loader = new URLClassLoader(
                 new URL[] { out.toUri().toURL() },
                 ClassLoader.getPlatformClassLoader())) {
            Class<?> compiled = Class.forName(
                    "example.Greeter", true, loader);
            Object instance = compiled
                    .getConstructor(String.class)
                    .newInstance("Ada");
            Object result = compiled
                    .getMethod("hello")
                    .invoke(instance);
            System.out.println("result=" + result);
        }
    }
}
```

Biên dịch và chạy với **JDK 17+**:

```bash
javac --release 17 PhaseDemo.java
java PhaseDemo
```

**Stdout chính xác, đã kiểm chứng trên OpenJDK 21:**

```text
parsed=Greeter
analyzed=example.Greeter
returnType=java.lang.String
treeElement=hello
generated=1
classExists=true
errors=0
result=Hello, Ada
```

Ví dụ tạo thư mục tạm mới mỗi lần chạy, có các thư mục `src/example` và `out`. Chương trình không in đường dẫn tạm và không xóa output ngay, giúp có thể inspect thủ công class file nếu muốn. `URLClassLoader` được dùng chỉ để thử chạy artifact mới sinh; không phải sandbox bảo mật.

### Giải thích chính xác đầu ra

- `parsed=Greeter`: lớp `Greeter` đã được tìm ở AST từ `CompilationUnitTree.getTypeDecls()`.
- `analyzed=example.Greeter`: mô hình compiler đã có `TypeElement` với qualified name tương ứng.
- `returnType=java.lang.String`: phương thức `hello` được resolve và có kiểu trả về là `String`.
- `treeElement=hello`: `Trees.getElement(TreePath)` nối method tree ở source với semantic element.
- `generated=1`: ví dụ này có một top-level class output; không được suy ra mọi compilation tạo đúng một file.
- `classExists=true`: `out/example/Greeter.class` đã được ghi.
- `errors=0`: không có diagnostics loại ERROR trong compilation đó.
- `result=Hello, Ada`: class mới được load và method trả về đúng khi chạy.

Nếu source chứa nested hoặc anonymous classes, class outputs có thể nhiều hơn số top-level source classes. Nếu có lỗi, compiler có thể trả AST một phần hoặc tạo partial outputs; không coi có output file là điều kiện đủ chứng minh build thành công.

## 7. Parse: đọc AST mà chưa cần giải quyết toàn bộ tên kiểu

`parse()` trả các `CompilationUnitTree` đại diện các đơn vị biên dịch. Mỗi unit có:

- `getPackageName()` và package-related metadata;
- `getImports()`;
- `getTypeDecls()` để duyệt các declarations;
- `getSourceFile()` trỏ `JavaFileObject` tương ứng;
- `getLineMap()` phục vụ chuyển offset sang dòng/cột.

Các Tree subtype thường gặp:

| Tree | Biểu diễn ở mã nguồn |
| --- | --- |
| `ClassTree` | Class/interface/record/enum declaration |
| `MethodTree` | Method hoặc constructor declaration |
| `VariableTree` | Field, parameter, local variable declaration |
| `MethodInvocationTree` | Lời gọi method |
| `NewClassTree` | Biểu thức tạo object |
| `ParameterizedTypeTree` | Kiểu dùng type arguments, ví dụ `List<String>` |
| `IfTree`, `ForLoopTree`, `ReturnTree` | Statements |
| `ErroneousTree` | Phần cú pháp lỗi khi parser phục hồi |

Giả sử source có:

```java
List<String> values = List.of("A", "B");
```

Parser có thể tạo cây cho khai báo và kiểu có tham số, nhưng việc loại `List` được import đúng và method `List.of` có sẵn cho `--release` mục tiêu hay không phải được xác minh ở pha analyze.

Nếu source bị sai cú pháp, compiler có thể **vẫn trả AST có `ErroneousTree`**, đồng thời phát diagnostic. Không suy diễn “`parse()` trả về iterable” thành “mã nguồn chắc chắn đúng”.

### Parse nhiều file

Trong ví dụ chỉ truyền một `JavaFileObject`, nên có thể dùng `iterator().next()`. Với nhiều file:

```java
for (CompilationUnitTree unit : task.parse()) {
    System.out.println(unit.getSourceFile().getName());
}
```

Đây là đoạn minh họa trong host đã tạo `task`. Không được chỉ lấy unit đầu tiên khi đang làm code indexer cho cả project. Compiler còn có thể đọc thêm source dependencies hoặc generated source theo cấu hình.

## 8. Analyze: chuyển từ cú pháp sang mô hình có ngữ nghĩa

Trong pha analyze, compiler thực hiện name resolution, type checking, generic constraints, access control, overload resolution và các kiểm tra cần thiết. API liên quan:

- `task.getElements()` để truy cứu declarations như `TypeElement`.
- `task.getTypes()` để so sánh kiểu, assignability, subtyping và erasure.
- `Trees.instance(task)` để gắn một AST node với `Element` hoặc `TypeMirror`.
- `DiagnosticCollector` để nhận thông báo lỗi kiểu hoặc tên không resolve được.

Ví dụ một `MethodTree` có tên `hello`. Ở parse, chỉ biết tồn tại node phương thức có tên đó; sau analyze, `ExecutableElement` cho phép đọc return type, tham số, modifiers và quan hệ với các phương thức khác.

### Element khác Tree thế nào?

| `Tree` | `Element` |
| --- | --- |
| Một vị trí/cấu trúc cú pháp trong source | Một khai báo trong semantic language model |
| Phù hợp cho source transformations, cấu trúc statement và expression | Phù hợp cho tên qualified, modifiers, parameter/return types |
| Có thể tồn tại khi source chưa resolve đúng | Có thể thiếu/không đầy đủ khi source có lỗi |
| Duyệt bằng `TreeScanner`/`TreePathScanner` | Duyệt qua `getEnclosedElements()`, `Elements` utility |
| Có source offset khi đi với `CompilationUnitTree` | Không đại diện cho source text gốc từng ký tự |

`Element` không phải `java.lang.Class<?>`. Khi phân tích code chưa compile xong, không nên dùng `Class.forName(...)` để thay thế `Elements.getTypeElement(...)`.

### TypeMirror và Types

`Trees.getTypeMirror(TreePath)` trả kiểu của node tương ứng khi compiler đã có thông tin ngữ nghĩa. Ví dụ expression `"Hello, " + name` trong `Greeter.hello()` có kiểu `java.lang.String`, nhưng biểu thức `42` có kiểu primitive `int`, mảng có `ArrayType`, và type variable generic có `TypeVariable`.

Đừng cast mọi `TypeMirror` sang `DeclaredType`; hãy kiểm tra `getKind()` hoặc dùng type visitors. Khi cần kiểm tra gán được hay không:

```java
boolean allowed = task.getTypes().isAssignable(fromType, toType);
```

Đây là đoạn code minh họa với hai `TypeMirror` đã được resolve. So sánh chuỗi `fromType.toString()` và `toType.toString()` không thay thế được semantic rules về generics, inheritance và conversion.

## 9. TreePath, Trees và TreePathScanner

Một `Tree` biểu diễn node cú pháp, nhưng node cần ngữ cảnh của package, enclosing class, imports và các declarations. `TreePath` giữ đường đi từ `CompilationUnitTree` tới node; nhờ nó `Trees` có thể trả symbol và type của node.

Đoạn đã sử dụng trong ví dụ:

```java
Trees trees = Trees.instance(task);
TreePath path = TreePath.getPath(unit, helloTree);
Element method = trees.getElement(path);
```

`Trees.getElement(path)` có thể trả `null` nếu node không có element thích hợp hoặc không resolve được. Không ép kiểu/đọc `getSimpleName()` khi chưa kiểm tra null trong công cụ thực tế xử lý source lỗi.

### Duyệt nhiều nodes

Một helper đếm lời gọi method:

```java
import com.sun.source.tree.MethodInvocationTree;
import com.sun.source.util.TreePathScanner;

public final class CallCounter extends TreePathScanner<Void, Void> {
    private int calls;

    @Override
    public Void visitMethodInvocation(
            MethodInvocationTree tree, Void unused) {
        calls++;
        return super.visitMethodInvocation(tree, unused);
    }

    public int count() {
        return calls;
    }
}
```

Đây là class helper hợp lệ, cần được sử dụng trong một host đã có `CompilationUnitTree unit`:

```java
CallCounter scanner = new CallCounter();
scanner.scan(unit, null);
System.out.println(scanner.count());
```

Không có giá trị count cố định cho mọi Java file; số call nodes phụ thuộc AST. Trong visitor, `getCurrentPath()` cho phép `Trees.getElement(...)` hoặc `Trees.getTypeMirror(...)` sau analyze:

```java
@Override
public Void visitMethodInvocation(
        MethodInvocationTree tree, Void unused) {
    Element callee = trees.getElement(getCurrentPath());
    if (callee != null) {
        System.out.println("callee=" + callee);
    }
    return super.visitMethodInvocation(tree, unused);
}
```

**Đây là mẩu code bên trong một `TreePathScanner` có field `Trees trees`**, không phải một class hoàn chỉnh. `TreePathScanner` duy trì path khi duyệt. Dùng `TreeScanner` đơn giản khi không cần current path.

## 10. Vị trí nguồn và diagnostics

### DiagnosticCollector

`DiagnosticCollector<JavaFileObject>` nhận lỗi và cảnh báo có cấu trúc:

```java
for (Diagnostic<? extends JavaFileObject> d
        : diagnostics.getDiagnostics()) {
    System.err.println(
            d.getKind() + " " + d.getLineNumber()
            + ":" + d.getColumnNumber()
            + " " + d.getMessage(null));
}
```

Đây là đoạn trong host có `diagnostics`. Dòng/cột có thể mang giá trị sentinel nếu diagnostic không gắn với một vị trí nguồn; message có thể phụ thuộc phiên bản/locale. Khi viết kiểm thử, nên so sánh error kind hoặc diagnostic code và phần có nghĩa thay vì chốt nguyên văn mọi câu.

### SourcePositions

`Trees.getSourcePositions()` cho offset của Tree node trong một `CompilationUnitTree`:

```java
long start = trees.getSourcePositions()
        .getStartPosition(unit, helloTree);
long end = trees.getSourcePositions()
        .getEndPosition(unit, helloTree);
```

Đoạn này sử dụng `trees`, `unit` và `helloTree` của ví dụ đầy đủ. Offset dựa trên vị trí ký tự trong source, **không** mặc nhiên là byte offset trong UTF-8. Vị trí có thể không khả dụng và được báo bằng giá trị âm. Dùng line map khi dữ liệu hợp lệ:

```java
long line = unit.getLineMap().getLineNumber(start);
long column = unit.getLineMap().getColumnNumber(start);
```

Không dùng offsets từ AST cũ để sửa file đã thay đổi kể từ lúc parse. `Tree.toString()` chỉ là biểu diễn debug, không bảo đảm bảo tồn whitespace, comments hoặc formatting ban đầu; muốn viết code action, cần giữ source snapshot và cách ghép source có kiểm soát.

## 11. TaskListener và các phase events

`JavacTask` có `addTaskListener(...)` và `setTaskListener(...)`. Listener nhận callback `started(TaskEvent)` và `finished(TaskEvent)` khi compiler thực hiện các hoạt động.

Ví dụ đăng ký trong host **trước `task.parse()`**:

```java
task.addTaskListener(new com.sun.source.util.TaskListener() {
    @Override
    public void started(com.sun.source.util.TaskEvent event) {
        System.out.println("START " + event.getKind());
    }

    @Override
    public void finished(com.sun.source.util.TaskEvent event) {
        System.out.println("END " + event.getKind());
    }
});
```

Các kind hữu ích:

| Kind | Ý nghĩa |
| --- | --- |
| `PARSE` | Parse một source file |
| `ENTER` | Enter declarations/symbols |
| `ANALYZE` | Phân tích ngữ nghĩa |
| `GENERATE` | Sinh compiler output |
| `ANNOTATION_PROCESSING` | Annotation processing nói chung |
| `ANNOTATION_PROCESSING_ROUND` | Một annotation processing round |
| `COMPILATION` | Sự kiện tổng thể với một đường compile thông thường |

Đừng giả định mỗi kind chỉ xuất hiện đúng một lần; nhiều classes và nhiều source files có thể tạo nhiều events. Theo tài liệu `TaskEvent.Kind`, **`COMPILATION` không được phát khi chủ động sử dụng `JavacTask.parse()`, `analyze()` hoặc `generate()`**. Vì vậy thiếu event này không chứng minh task chưa thực thi.

Không gọi các phase methods của cùng task bên trong listener để cố điều khiển compiler ở giữa một callback. API listeners dành cho quan sát, tránh reentrant compilation hoặc thay state bất ngờ.

## 12. Phân tích nguồn có lỗi: AST vẫn có thể tồn tại

Nguồn có cú pháp hợp lệ nhưng sai kiểu:

```java
package demo;
public class Broken {
    int value() {
        return "a string";
    }
}
```

Đây là ví dụ **cố ý không biên dịch được**. `parse()` có thể trả cây `ClassTree` và `MethodTree`; đến `analyze()` compiler nhận ra `String` không thể trả về như `int`, phát lỗi.

Nguồn sai cú pháp:

```java
public class Unclosed {
    void run() {
        System.out.println("x");
```

Đây cũng là ví dụ **cố ý không hợp lệ**; parser có thể phục hồi một phần và tạo `ErroneousTree`, nhưng không có hợp đồng bắt buộc nó phải phục hồi cùng hình dạng trên mọi JDK.

Với IDE linter cần hoạt động trên code đang được gõ, điều quan trọng là:

- Không bỏ qua diagnostics chỉ vì parse trả trees.
- Không assume `Trees.getElement(...)` luôn khác null.
- Nếu `TypeMirror.getKind() == ERROR`, kiểu chưa resolve; có thể do dependency/classpath thiếu hoặc generated source chưa xuất hiện.
- Không xuất bản class artifacts khi task có lỗi và output chỉ được tạo một phần.
- Đánh giá lại toàn bộ compilation environment khi source thay đổi; không cache `TreePath` và symbols mãi mãi.

## 13. Annotation processing và generate có phải cùng một việc?

**Không.** `JavacTask.generate()` là pha phát compiler output như `.class`. Annotation processor chạy theo **JSR 269**, dùng `Filer.createSourceFile(...)` để tạo source mới; compiler có thể nhận source ấy trong round tiếp.

| Công việc | API | Output tiêu biểu |
| --- | --- | --- |
| Parse source thành AST | `JavacTask.parse()` | `CompilationUnitTree` |
| Resolve/check kiểu | `JavacTask.analyze()` | `Element`, `TypeMirror` và diagnostics |
| Sinh class file | `JavacTask.generate()` | `JavaFileObject` cho `.class` |
| Sinh Java source từ annotation | `ProcessingEnvironment.getFiler().createSourceFile(...)` | `.java` mới đưa vào compilation |
| Sửa text trong file nguồn | Cơ chế source-edit riêng | Không có phương thức `Tree.setBody(...)` chuẩn |

Trong ví dụ PhaseDemo ta bật `-proc:none`. Nếu muốn bật processor đã có instance, có thể làm:

```java
JavaCompiler.CompilationTask raw = compiler.getTask(
        null, fm, diagnostics,
        List.of("--release", "17"), null, inputs);

raw.setProcessors(List.of(new MyProcessor()));
JavacTask task = (JavacTask) raw;
task.parse();
task.analyze();
task.generate();
```

Đây là đoạn cấu hình **minh họa**, giả định `MyProcessor` tồn tại, đã được load trong JVM của host và có thể thực thi; phải gọi `setProcessors` trước khi khởi động các phases, không đồng thời đặt `-proc:none`. Processor có thể phát source, class hoặc resource tùy thiết kế.

`com.sun.source.tree.Tree` là interface quan sát cú pháp, không phải API chung để tùy tiện sửa AST rồi ép `generate()` viết bytecode của cây tự tạo. Nếu cần sinh mã mới, dùng Filer hoặc tạo source riêng; nếu cần sửa code người dùng, dùng công cụ source-rewrite phù hợp thay vì dựa vào internals của javac.

## 14. Nhiều nguồn và module có thể làm số output khác số input

Trong dự án thường có nhiều file:

```java
var units = files.getJavaFileObjectsFromPaths(
        List.of(mainSource, helperSource));
```

Đây là đoạn minh họa; các `Path`/`StandardJavaFileManager` phải tồn tại. `parse()` có thể trả nhiều `CompilationUnitTree`. `generate()` có thể trả nhiều file hơn số compilation units do nested/anonymous classes hoặc generated code; không dùng công thức “một Java file = một class file”.

Với source dependencies được tìm ngầm, classpath, source path, `-Xprefer` và `-implicit` có thể ảnh hưởng file nào được đọc và output nào được tạo. Để tái hiện, cần ghi source inputs, JDK version, options, dependencies và thư mục output sạch.

Đối với named modules:

- `module-info.java` có `ModuleTree`, không thể coi mọi compilation unit đều có một `ClassTree`.
- `MODULE_SOURCE_PATH` là nơi chứa source modules; `MODULE_PATH` là nơi chứa compiled module dependencies.
- `requires`, `exports` và module readability có thể ảnh hưởng kết quả analyze.
- Output có thể theo từng named module. Runtime cần module-path/layer đúng, không chỉ `URLClassLoader` như classpath demo.

**Không dùng máy móc cách nạp classpath ở PhaseDemo để chạy named module**; đó là một bài toán runtime/module layer riêng.

## 15. Làm công cụ lớn: lifecycle, caching, concurrency và hiệu năng

Một `JavacTask` đại diện **một compilation snapshot**, không phải một compiler server đa lần gọi không giới hạn. Những quy tắc thiết kế đáng giữ:

1. Tạo task mới cho lần compile/analysis độc lập; chọn `call()` hoặc pha tường minh.
2. Không chia sẻ một task giữa các threads cùng gọi `parse/analyze/generate`; quản lý file manager và output directory khi chạy song song.
3. Đóng file manager theo lifecycle; khi runtime test class mới, đóng classloader sau khi sử dụng.
4. Không giữ `Element`, `TypeMirror` hoặc `TreePath` của task cũ qua những lần source thay đổi và giả định chúng đã cập nhật.
5. Nếu chỉ làm syntax indexing, dừng ở `parse` để tiết kiệm công việc; nếu cần semantic accuracy, hãy `analyze` với classpath/module path đầy đủ.
6. Chỉ `generate` khi thật sự cần class files; build artifact không phải điều kiện để một linter cú pháp làm việc.
7. Thu diagnostics theo cấu trúc; không dùng `System.out` từ compiler là nguồn dữ liệu lỗi duy nhất.
8. Tránh tự chạy annotation processors không tin cậy; processor là code thực thi trong build environment, có thể đọc resources/environment.
9. Chốt compiler version, options, input hashes và outputs khi mục tiêu là reproducibility.
10. Tách công cụ phân tích source với môi trường chạy output; compiler success không đồng nghĩa runtime test success.

## 16. Bảng chẩn đoán nhanh

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `getSystemJavaCompiler() == null` | JVM host không có system compiler | Chạy host trên JDK/runtime image có compiler |
| Ép task sang `JavacTask` bị lỗi | Compiler provider khác `javac` | Kiểm tra `instanceof` hoặc dùng API chung |
| IDE không tìm `com.sun.source.util` | Thiếu `jdk.compiler` hoặc sai module configuration | Dùng JDK có `jdk.compiler`, named module `requires jdk.compiler` |
| `parse` có cây nhưng code vẫn sai | Parse không tự kiểm tra hết kiểu | `analyze` và đọc diagnostics |
| `Trees.getElement` trả null | Node không resolve hoặc không có element | Kiểm tra phase, TreePath và lỗi compiler |
| `TypeMirror` là `ERROR` | Dependency thiếu hoặc source chưa hoàn chỉnh | Kiểm tra classpath/module path, generated sources |
| `generate` trả ít file | Source có lỗi hoặc chỉ có ít declarations | Đọc diagnostics, output dir và các pha |
| `IllegalStateException` | Task/phase bị gọi sai thời điểm hoặc lặp lại | Tạo task mới, tuân thủ lifecycle |
| Class file tồn tại nhưng runtime không load | Runtime classpath/module path thiếu | Cấu hình runtime riêng |
| Listener không thấy `COMPILATION` | Đang dùng trực tiếp phase API | Quan sát các `PARSE/ENTER/ANALYZE/GENERATE` events |
| Có `.class` cũ sau lỗi build | Output directory không được làm sạch | Dùng output riêng/sạch, kiểm tra diagnostics |
| Dùng `Tree.toString()` để sửa source | Không bảo toàn source text gốc | Dùng positions và source snapshot/công cụ rewrite |
| “Generate” bị hiểu là sinh annotation code | Nhầm compiler output với Filer | Phân biệt `JavacTask.generate` và `Filer` |

## 17. Câu hỏi tự kiểm tra

**1.** Có `ClassTree` từ `parse()`, có thể kết luận tên mọi kiểu trong class đều hợp lệ?

**Đáp án:** Không. AST biểu diễn cấu trúc; cần `analyze()` và diagnostics cho name resolution/type checking.

**2.** Muốn biết lời gọi `service.execute()` thực sự tham chiếu method nào, nên dùng gì?

**Đáp án:** Sau `analyze()`, tạo `TreePath` cho `MethodInvocationTree` và dùng `Trees.getElement(path)`; cần xử lý null và lỗi resolve.

**3.** `JavacTask.generate()` có phải là API để tạo Java source theo một annotation không?

**Đáp án:** Không. `generate()` phát output compiler; annotation processor dùng `Filer` để tạo source/class/resource.

**4.** Một tool đã gọi `task.parse(), task.analyze(), task.generate()` có nên gọi tiếp `task.call()` để “chắc chắn” không?

**Đáp án:** Không. Chọn điều khiển các pha hoặc `call()` cho cùng một task; muốn compile lại hãy tạo task mới.

**5.** Vì sao `TreePathScanner` hữu ích hơn `TreeScanner` trong công cụ phân tích ngữ nghĩa?

**Đáp án:** Vì scanner duy trì đường dẫn đến node hiện tại; các API `Trees.getElement/getTypeMirror` thường cần `TreePath`.

**6.** `TaskEvent.Kind.COMPILATION` không xuất hiện nhưng các `PARSE` và `GENERATE` có. Đây có phải lỗi?

**Đáp án:** Không. Tài liệu quy định COMPILATION event không phát khi dùng trực tiếp các phase methods của JavacTask.

**7.** Sau `generate()` có `Greeter.class`, nhưng `java example.Greeter` báo không có main. Vì sao?

**Đáp án:** Class `Greeter` chỉ có constructor và method `hello`, không có entry point `public static void main`. Ví dụ host dùng reflection để tạo instance và gọi method.

**8.** Source vừa bị sửa nhưng công cụ vẫn giữ `TypeMirror` từ lần analyze trước. Vấn đề là gì?

**Đáp án:** Model thuộc compilation snapshot trước, có thể đã lỗi thời. Cần tạo task/analysis mới hoặc cơ chế incremental có quản lý.

**9.** Chỉ muốn đếm các `if` trong source, có cần gọi generate không?

**Đáp án:** Không. `parse` và visitor cho `IfTree` là đủ, trừ khi rule còn cần ngữ nghĩa kiểu.

**10.** Vì sao ví dụ PhaseDemo ghi `generated=1` nhưng không nên viết test tổng quát mong mọi task đều một file?

**Đáp án:** Số classes phụ thuộc nhiều source units, nested/anonymous classes, annotation generated code và các compiler output khác. Giá trị 1 chỉ áp dụng cho ví dụ đơn giản được kiểm thử.

## 18. Nguồn chính thức

- **JDK 21 JavacTask:** https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/util/JavacTask.html — `parse()`, `analyze()`, `generate()`, compiler utilities và listeners.
- **JDK 21 Trees:** https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/util/Trees.html — `getElement`, `getTypeMirror`, `getSourcePositions`.
- **JDK 21 TreePathScanner:** https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/util/TreePathScanner.html — AST visitor có current path.
- **JDK 21 CompilationUnitTree:** https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/tree/CompilationUnitTree.html — cấu trúc compilation unit.
- **JDK 21 TaskEvent.Kind:** https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/util/TaskEvent.Kind.html — các event kinds và ghi chú về COMPILATION.
- **JDK 21 JavaCompiler API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaCompiler.html — `getTask` và file manager.
- **JDK 21 javac reference:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html — options như `--release`, `-proc`, classpath và output.

**Kết luận:** `JavacTask` giúp công cụ điều khiển và quan sát việc biên dịch theo trình tự **source → AST (`parse`) → semantic model (`analyze`) → class output (`generate`)**. Khi triển khai, giữ đúng lifecycle một task, dùng `Trees`/`TreePath` cho symbol và type, kiểm tra diagnostics, phân biệt annotation source generation với bytecode generation và chỉ chạy tới pha thật sự cần.
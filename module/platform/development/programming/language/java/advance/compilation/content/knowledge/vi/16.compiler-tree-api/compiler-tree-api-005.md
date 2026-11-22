# Xác định vị trí nguồn để báo lỗi hoặc hiển thị kết quả phân tích cây cú pháp Java

## 1. Vấn đề: từ nút AST quay lại đúng dòng và cột của source

Một công cụ phân tích Java thường duyệt **abstract syntax tree (AST)** để tìm các method invocation, khai báo, biểu thức không hợp lệ hoặc quy tắc mã nguồn cần cảnh báo. Nhưng người dùng không muốn chỉ thấy thông báo “phát hiện lời gọi Math.max”; họ cần biết **file nào, dòng mấy, cột mấy, đoạn ký tự nào** để nhảy tới vị trí, gạch chân hoặc hiện lời gợi ý trong editor.

Trong Compiler Tree API của JDK, một `Tree` biểu diễn cấu trúc cú pháp, không phải mặc nhiên chứa số dòng/cột. Ta cần kết hợp:

- `CompilationUnitTree`: root của một source file, biết `getSourceFile()` và `getLineMap()`.
- `Trees.getSourcePositions()`: trả về `SourcePositions`, ánh xạ một nút `Tree` trong đúng compilation unit về **offset ký tự** từ đầu file.
- `SourcePositions.getStartPosition(unit, tree)` và `getEndPosition(unit, tree)`: vị trí bắt đầu/kết thúc khi compiler biết được.
- `LineMap.getLineNumber(offset)` và `getColumnNumber(offset)`: đổi offset thành dòng/cột theo cú pháp nguồn thực tế.
- `TreePathScanner`: quét AST và giữ context `TreePath` từ compilation unit tới nút đang xét.
- `Trees.printMessage(kind, message, tree, compilationUnit)`: để công cụ dựa trên javac phát một chẩn đoán gắn vào nút nguồn.
- `DiagnosticCollector`: thu lỗi/cảnh báo từ compiler thành dữ liệu có cấu trúc.

Luồng chính:

~~~text
         Tệp .java
            |
       JavacTask.parse()
            |
    CompilationUnitTree
            |
      TreePathScanner
            |
        Tree node
            |
 SourcePositions.getStartPosition(unit, node)
            |
     offset ký tự từ 0
            |
 CompilationUnitTree.getLineMap()
            |
       line / column
            |
   Console / IDE / code review / warning
~~~

**Điểm bắt buộc:** luôn ghép `Tree` với đúng `CompilationUnitTree` chứa nó. Một offset 120 trong file A không có nghĩa gì nếu đem đổi dòng bằng `LineMap` của file B.

## 2. Những kiểu vị trí khác nhau và ý nghĩa

| Đại lượng | API | Hệ tọa độ |
| --- | --- | --- |
| Tệp nguồn | `unit.getSourceFile()` | `JavaFileObject` và URI của compilation unit |
| Start offset | `positions.getStartPosition(unit, node)` | Vị trí ký tự từ đầu source, **bắt đầu 0** |
| End offset | `positions.getEndPosition(unit, node)` | Vị trí cuối vùng cú pháp, có thể không biết |
| Dòng | `unit.getLineMap().getLineNumber(start)` | Dòng trong file, **bắt đầu 1** |
| Cột | `unit.getLineMap().getColumnNumber(start)` | Cột trên dòng, **bắt đầu 1**, có xét tab expansion |
| Tọa độ diagnostic | `Diagnostic.getLineNumber()` / `getColumnNumber()` | Compiler cung cấp, có thể không tồn tại |
| Vị trí diagnostic dạng offset | `Diagnostic.getStartPosition()` / `getPosition()` / `getEndPosition()` | Tính trên source của diagnostic, có thể là `NOPOS` |

Tài liệu `SourcePositions` mô tả offset tính từ đầu compilation unit, ký tự đầu tiên ở vị trí 0. `LineMap` chịu trách nhiệm chuyển đổi. Với ký tự tab, cột tính theo tab expansion của trình biên dịch, không phải đơn giản bằng số ký tự của substring kể từ dấu xuống dòng.

Không nhầm:

- **Byte offset** trong file UTF-8 không đồng nghĩa **character offset** của compiler. Chữ tiếng Việt có thể chiếm nhiều byte.
- **Dòng/cột của IDE** có thể khác convention (một số giao thức editor dùng 0-based line/character).
- **End position** không phải một “dòng cuối” hay “số lượng ký tự” được đưa thẳng ra UI; trước khi highlight cần đổi cả start và end về hệ tọa độ editor.
- `Tree.toString()` mô tả lại biểu thức theo compiler, không trả về vị trí văn bản gốc.

Với những node được tổng hợp, không có trong source, hoặc khi compiler không có thông tin định vị, `getStartPosition` / `getEndPosition` có thể trả `Diagnostic.NOPOS` (giá trị -1). Luôn kiểm tra trước khi gọi `LineMap` hoặc cắt source text.

## 3. Khác biệt giữa Tree, TreePath và CompilationUnitTree

Một `Tree` đại diện một node như `MethodInvocationTree`, `ClassTree`, `VariableTree` hoặc `LiteralTree`. Một `CompilationUnitTree` đại diện *toàn bộ tệp nguồn*. `TreePath` giữ chuỗi ancestor từ compilation unit tới node, rất hữu ích để biết method/class bao quanh hoặc lấy symbol/type sau khi phân tích ngữ nghĩa.

| Nhu cầu | Nên dùng |
| --- | --- |
| Xác định tọa độ trong file | `SourcePositions` + `CompilationUnitTree` |
| Duyệt method calls trong file | `TreePathScanner.visitMethodInvocation` |
| Biết ancestors/owner đang chứa lời gọi | `TreePathScanner.getCurrentPath()` |
| Tìm declaration tương ứng sau khi analyze | `Trees.getElement(TreePath)` |
| Tìm kiểu đã phân giải | `Trees.getTypeMirror(TreePath)` |
| Gắn warning vào source | `Trees.printMessage` |
| Gắn warning vào declaration trong annotation processor | `Messager.printMessage` với `Element` tương ứng |

`TreePathScanner` thường phù hợp hơn `TreeScanner` nếu bài toán cần context và symbol resolution. Với một phép phân tích cú pháp đơn giản chỉ cần dòng/cột, `TreeScanner` cũng có thể đủ, miễn là bạn giữ đúng `CompilationUnitTree`.

**Không gọi `Trees.getElement(path)` trên cây mới parse rồi mặc định có symbol đầy đủ.** Để lấy `Element`/`TypeMirror` chính xác, phải thực hiện các pha phân giải/analyze cần thiết và xử lý lỗi của source; còn để lấy vị trí cú pháp thường chỉ cần parse.

## 4. Ví dụ Java 17+ hoàn chỉnh: in vị trí hai lời gọi method

Ví dụ dùng `com.sun.source.*` trong JDK module `jdk.compiler`. Ta tạo một chương trình **để phân tích source**, không phải annotation processor. Nó đọc một `.java`, gọi `JavacTask.parse()`, quét các `MethodInvocationTree` và in file/line/column.

Cấu trúc:

~~~text
project/
├── LocateCalls.java
├── src/
│   └── demo/Sample.java
└── out/               # class của công cụ LocateCalls
~~~

### 4.1. File src/demo/Sample.java

Giữ nguyên khoảng trắng, dòng trống và dấu xuống dòng theo mẫu để khớp kết quả dòng/cột:

~~~java
package demo;

public final class Sample {
    public static void main(String[] args) {
        System.out.println(Math.max(2, 5));
    }
}
~~~

Dòng có hai method invocations lồng nhau: `System.out.println(...)` ở ngoài, `Math.max(2, 5)` ở trong.

### 4.2. File LocateCalls.java

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;

import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.LineMap;
import com.sun.source.tree.MethodInvocationTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.SourcePositions;
import com.sun.source.util.TreePathScanner;
import com.sun.source.util.Trees;

public final class LocateCalls {
    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: LocateCalls source-file");
        }

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler required");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
                     compiler.getStandardFileManager(
                             diagnostics,
                             Locale.ROOT,
                             StandardCharsets.UTF_8)) {

            Iterable<? extends JavaFileObject> input =
                    manager.getJavaFileObjectsFromPaths(
                            List.of(Path.of(args[0])));

            JavacTask task = (JavacTask) compiler.getTask(
                    null, manager, diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null, input);

            Iterable<? extends CompilationUnitTree> parsed =
                    task.parse();

            Trees trees = Trees.instance(task);
            SourcePositions positions = trees.getSourcePositions();

            for (CompilationUnitTree unit : parsed) {
                new TreePathScanner<Void, Void>() {
                    @Override
                    public Void visitMethodInvocation(
                            MethodInvocationTree node,
                            Void ignored) {

                        long start =
                                positions.getStartPosition(unit, node);
                        long end =
                                positions.getEndPosition(unit, node);

                        if (start != Diagnostic.NOPOS) {
                            LineMap map = unit.getLineMap();
                            System.out.printf(Locale.ROOT,
                                    "CALL %s @ %d:%d%n",
                                    node.getMethodSelect(),
                                    map.getLineNumber(start),
                                    map.getColumnNumber(start));
                        }

                        if (end != Diagnostic.NOPOS
                                && end < start) {
                            throw new IllegalStateException(
                                    "Invalid source span");
                        }

                        return super.visitMethodInvocation(
                                node, ignored);
                    }
                }.scan(unit, null);
            }
        }

        for (Diagnostic<? extends JavaFileObject> diagnostic :
                diagnostics.getDiagnostics()) {
            if (diagnostic.getKind() == Diagnostic.Kind.ERROR) {
                System.err.println(
                        diagnostic.getMessage(Locale.ROOT));
            }
        }
    }
}
~~~

### 4.3. Biên dịch và chạy

Dùng JDK 17+ có `javac` và `jdk.compiler`; đứng ở thư mục project:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out LocateCalls.java
java -cp out LocateCalls src/demo/Sample.java
~~~

**Stdout chính xác** khi tệp nguồn giữ đúng cách xuống dòng và thụt lề:

~~~text
CALL System.out.println @ 5:9
CALL Math.max @ 5:28
~~~

Thứ tự như trên vì `TreePathScanner` duyệt lời gọi ngoài trước, rồi mới duyệt lời gọi lồng trong, và ta in trước khi gọi `super.visitMethodInvocation`. Không khẳng định mọi traversal tùy biến đều có cùng thứ tự khi người viết đổi scanner.

Trên Windows PowerShell có thể tạo thư mục bằng:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out LocateCalls.java
java -cp out LocateCalls src/demo/Sample.java
~~~

Chương trình `Sample` **không cần được biên dịch** để LocateCalls đọc được AST. Nếu muốn chạy Sample như một Java application độc lập, phải compile nó thành class trước:

~~~bash
javac --release 17 -d out src/demo/Sample.java
java -cp out demo.Sample
~~~

Khi chạy Sample, stdout là:

~~~text
5
~~~

**Kiểm chứng thực hành:** ví dụ LocateCalls đã được compile và chạy bằng JDK 21 với `--release 17`. Hai vị trí `5:9` và `5:28` là kết quả quan sát được từ đúng sample ở trên, không phải một chỉ số được suy đoán từ tên node.

## 5. Giải mã dòng/cột của ví dụ

Với dòng:

~~~java
        System.out.println(Math.max(2, 5));
~~~

- Có **8 dấu cách** trước `System`, nên lời gọi `System.out.println` bắt đầu ở cột **9**.
- `Math.max` nằm bên trong `println( ... )`, bắt đầu ở cột **28**.
- Cả hai bắt đầu ở **dòng 5**.
- Trong AST, `MethodInvocationTree` bên ngoài có một node con biểu diễn `Math.max(2, 5)`.
- Khi gọi `getStartPosition(unit, outer)`, vị trí chỉ tới đầu `System`; gọi cho inner node chỉ tới đầu `Math`.

Điểm quan trọng là tọa độ được **compiler trả về từ AST**; việc tự đếm dấu cách ở đây chỉ giúp học viên kiểm tra đầu ra. Với tệp có tab, Unicode, CRLF và token/comment phức tạp, hãy dùng `LineMap` chứ không tự tính `lastIndexOf("\\n")` và đếm ký tự.

`getLineNumber` và `getColumnNumber` dùng **1-based**; offset của `SourcePositions` dùng **0-based**. Nếu IDE/editor cần hệ 0-based, hãy chuyển đổi tại ranh giới gửi dữ liệu ra UI, không thay đổi dữ liệu gốc của compiler trong quá trình phân tích.

## 6. Lấy cả vùng source để highlight

Để gạch chân cả biểu thức thay vì chỉ trỏ một vị trí, cần cả start và end:

~~~java
// Fragment trong scanner, giả định đã có unit, node và positions:
long start = positions.getStartPosition(unit, node);
long end = positions.getEndPosition(unit, node);

if (start != Diagnostic.NOPOS
        && end != Diagnostic.NOPOS
        && end >= start) {
    LineMap map = unit.getLineMap();
    long startLine = map.getLineNumber(start);
    long startColumn = map.getColumnNumber(start);
    long endLine = map.getLineNumber(end);
    long endColumn = map.getColumnNumber(end);
    // Gửi vùng này cho editor hoặc tạo code lens/report.
}
~~~

Đây là **fragment**, không phải file Java tự chạy. Trong mô hình javac thường dùng, end offset là vị trí ngay sau vùng cú pháp, thuận tiện cho khoảng `[start, end)` để highlight. Nhưng API `SourcePositions` bảo đảm vị trí bắt đầu/kết thúc và có thể báo `NOPOS`; khi cắt source text hoặc đổi sang giao thức editor, cần kiểm chứng convention của compiler/consumer, tránh lỗi lệch một ký tự.

**Một span có thể qua nhiều dòng.** Ví dụ lambda body hoặc invocation trải qua ba dòng sẽ có startLine khác endLine. Đừng chỉ lưu `line` và một “độ dài trên dòng” rồi đánh dấu sai phần còn lại.

Khi cần lấy ký tự thực:

~~~java
// Fragment: sourceText là String của đúng compilation unit.
// Chỉ cắt khi các offset và độ dài đã được kiểm tra.
if (0 <= start && start <= end
        && end <= sourceText.length()) {
    String snippet =
            sourceText.substring((int) start, (int) end);
}
~~~

Chỉ áp dụng khi đã chắc chắn offset và nội dung `sourceText` lấy từ **đúng phiên bản nguồn mà compiler parse**, không phải nội dung file đã bị editor thay đổi sau đó. Nếu source phát sinh từ `SimpleJavaFileObject` in-memory, đọc chính object đó thay vì đoán trên filesystem. Với source thực, có thể dùng `unit.getSourceFile().getCharContent(true)` rồi kiểm tra encoding/độ dài.

Về Unicode: không biến offset của compiler thành **UTF-8 byte offset** bằng cách cast sang int và dùng trực tiếp trên mảng byte; đối với editor dùng UTF-16 code units, phải đối chiếu quy tắc indexing và surrogate pairs.

## 7. In diagnostic tại đúng nút bằng Trees.printMessage

Nếu công cụ muốn báo **warning/error có thông tin file và vị trí**, thay vì tự in:

~~~java
System.err.println("Avoid Math.max");
~~~

hãy dùng API của `Trees`:

~~~java
// Fragment đặt trong visitMethodInvocation của TreePathScanner.
// trees và unit phải tương ứng với task đang được scan.
trees.printMessage(
        Diagnostic.Kind.WARNING,
        "Review this invocation",
        node,
        unit);
~~~

`Trees.printMessage` nhận `Diagnostic.Kind`, thông báo, node và compilation unit chứa node. Nó gắn vị trí nguồn vào diagnostic theo contract, hữu ích cho compiler output và công cụ tích hợp. Không cần tự ghép đường dẫn file, ký tự `:`, dòng và cột trong message.

Nếu muốn chỉ báo lỗi cho một loại lời gọi, **đừng kiểm tra `node.toString().contains("...")` một cách tùy tiện**: đây là text của cây, có thể bị ảnh hưởng bởi cú pháp và không xác định được overloaded method. Nên dùng `TreePathScanner.getCurrentPath()` và sau pha phân giải ngữ nghĩa gọi `Trees.getElement(path)` để biết method declaration thực sự, rồi kiểm tra `ExecutableElement`, owner và types theo Java language model. Đó là bước vượt quá ví dụ in tọa độ thuần cú pháp, nhưng rất quan trọng khi xây static analysis rule thật.

Nếu cần cảnh báo một **annotation processor**, API `Messager.printMessage(Diagnostic.Kind, ..., Element)` có thể gắn lỗi tại declaration; nó không luôn cho phép chọn chính xác một expression AST bên trong method. Khi quy tắc cần vị trí expression, `Trees` + `Tree` thường là công cụ phù hợp hơn. Hai API phục vụ các cấp độ khác nhau.

## 8. DiagnosticCollector và tọa độ lỗi của chính compiler

Khi compiler phân tích nguồn có lỗi, `DiagnosticCollector<JavaFileObject>` cho ta thông tin có cấu trúc. Để yêu cầu type checking thực sự, không chỉ parse, có thể gọi `task.analyze()` sau `task.parse()`, trong điều kiện compiler/task được thiết lập phù hợp.

~~~java
// Fragment, cần nằm trong vòng đời JavacTask hợp lệ:
Iterable<? extends CompilationUnitTree> units = task.parse();
task.analyze();

for (Diagnostic<? extends JavaFileObject> d
        : diagnostics.getDiagnostics()) {
    if (d.getKind() == Diagnostic.Kind.ERROR) {
        JavaFileObject file = d.getSource();
        System.err.printf(Locale.ROOT,
                "ERROR %s:%d:%d %s%n",
                file == null ? "<unknown>" : file.toUri(),
                d.getLineNumber(),
                d.getColumnNumber(),
                d.getMessage(Locale.ROOT));
    }
}
~~~

Đây là **fragment**, không phải chương trình tự chạy. Trên source có lỗi, `analyze()` thường làm phát sinh lỗi resolution/type checking mà chỉ `parse()` chưa phát hiện. Không gọi `task.call()` sau khi đã sử dụng các pha phân tích riêng theo cách không được tool contract cho phép; hãy quản lý vòng đời `JavacTask` rõ ràng.

Các phương thức quan trọng của `Diagnostic`:

| Method | Thông tin |
| --- | --- |
| `getKind()` | Error, warning, mandatory warning, note... |
| `getSource()` | Source file object hoặc null |
| `getLineNumber()` | Dòng nguồn nếu có, hoặc `NOPOS` |
| `getColumnNumber()` | Cột nguồn nếu có, hoặc `NOPOS` |
| `getPosition()` | Vị trí diagnostic trọng tâm |
| `getStartPosition()` | Đầu vùng diagnostic nếu có |
| `getEndPosition()` | Cuối vùng diagnostic nếu có |
| `getCode()` | Diagnostic code của công cụ |
| `getMessage(Locale)` | Thông điệp hiển thị; wording phụ thuộc JDK/locale |

Để xử lý trong IDE, nên giữ **kind, file, offsets/line/column và code** thay vì parse định dạng stderr của javac bằng regex. Không phải diagnostic nào cũng có source line/column, chẳng hạn lỗi option hoặc một thông điệp liên quan build setup. Kiểm tra `NOPOS` để hiển thị cảnh báo cấp project nếu không định vị được node.

Khi đã có AST node, `SourcePositions` thường cho span của **node cú pháp**; `Diagnostic` cho span mà **compiler chọn để báo lỗi**. Hai span có thể không trùng nhau, và đó không nhất thiết là lỗi của compiler: một diagnostic có thể chỉ gạch chân tên method, trong khi `MethodInvocationTree` bao toàn bộ lời gọi với arguments.

## 9. Dùng TreePathScanner để giữ context khi phân tích

`TreePathScanner` cung cấp `getCurrentPath()` trong visitor. Đường dẫn giúp nhận biết node cha, method chứa node và element đã được resolve. Ví dụ:

~~~java
// Fragment trong scanner:
@Override
public Void visitMethodInvocation(MethodInvocationTree node,
                                  Void unused) {
    TreePath path = getCurrentPath();
    // path.getLeaf() chính là node của invocation này.
    // path.getParentPath() dẫn tới AST node cha.
    // trees.getElement(path) có ích sau khi analyze().
    return super.visitMethodInvocation(node, unused);
}
~~~

Không nhất thiết mọi invocation đều tương ứng một method đã resolve thành công: source có thể sai, processor có thể sinh code ở vòng sau hoặc overload resolution thất bại. Trong các trường hợp đó `trees.getElement(path)` có thể trả null hoặc các phần của model là error types; công cụ phân tích không nên crash.

Khi muốn duyệt nhiều source units, tạo scanner mới cho từng unit hoặc truyền đúng unit vào context visitor, thay vì dùng một biến global gắn cố định file đầu tiên. `CompilationUnitTree.getSourceFile()` là nguồn để báo file tương ứng.

Có thể lấy cây từ một `Element` bằng `Trees.getTree(element)` hoặc đường dẫn `Trees.getPath(element)` trong những trường hợp compiler giữ source tree cho khai báo đó, nhưng **không bảo đảm** mọi external library class có source AST đang có sẵn. Một class chỉ được tìm thấy qua dependency JAR có thể có `Element`, `TypeMirror` mà không có source tree/offset trong bài đang compile.

## 10. Phân biệt vị trí nút cú pháp và vị trí ký tự người dùng nhìn thấy

AST không giữ đầy đủ mọi chi tiết lexical theo cách một parser bảo toàn nguyên văn source sẽ giữ. Một số dấu câu, khoảng trắng, comments hoặc annotation/qualifier có thể được ánh xạ vào các node khác nhau, và token bạn muốn highlight không nhất thiết trùng toàn bộ span của node AST.

Ví dụ khi xem lời gọi:

~~~java
service
    .getClient()
    .send("ok");
~~~

`MethodInvocationTree` bao cả lời gọi; `MethodSelect` là một subtree; các arguments là subtrees khác. Nếu chỉ muốn gạch chân identifier `send`, lấy start/end của **toàn bộ invocation** có thể tô cả chuỗi lời gọi. Cần chọn đúng subtree, hoặc sử dụng thêm công cụ đọc token/source khi cần vị trí chính xác của một dấu câu/tên trong cú pháp.

Đừng tự suy rằng `node.toString().indexOf("send")` cộng với start offset của node tạo ra tọa độ chuẩn: `toString()` có thể format khác text nguồn và không bảo toàn comments/whitespace. Dùng `SourcePositions` cho các node phù hợp; nếu muốn token-level precision ngoài AST coverage, kết hợp lexer/token API có contract rõ và giữ cùng snapshot nguồn.

Ngoài ra:

- **Tab:** `LineMap.getColumnNumber` có tính tab expansion; tự đếm char trong substring thường sai.
- **CRLF/LF:** đổi line map sau khi chuẩn hóa newline có thể làm lệch offset, nếu không đồng thời thay snapshot source.
- **Unicode:** Java source có thể gồm ký tự bổ sung ngoài BMP hoặc Unicode escapes. Tránh giả định offset == UTF-8 byte index.
- **Source file bị thay đổi:** vị trí lấy từ build cũ không được dùng mù quáng trên editor buffer mới.
- **Synthetic/recovered trees:** compiler tạo node không có span hoặc có vị trí không đủ; phải có fallback.
- **Nhiều file cùng tên:** `Sample.java` ở hai source roots khác nhau phải được phân biệt bằng `JavaFileObject.toUri()` hoặc định danh file chuẩn, không chỉ basename.

Một analyzer tốt lưu cả **URI, phiên bản snapshot, start/end offsets và line/column đã chuẩn hóa** (nếu consumer cần) để UI đối chiếu đúng. Nếu không có vị trí, hiển thị lỗi cấp file/project thay vì bịa dòng 1, cột 1.

## 11. Lỗi thường gặp khi xây công cụ báo vị trí nguồn

| Triệu chứng | Lỗi gốc | Cách sửa |
| --- | --- | --- |
| Báo dòng 0/cột 0 | Lẫn offset 0-based với line/column 1-based | Đổi bằng `LineMap` |
| Lỗi chỉ sau khi gặp dấu tab | Tự tính cột bằng `substring.length` | Dùng `LineMap.getColumnNumber` |
| Bị lỗi với chữ Unicode/emoji | Dùng byte offset làm char offset | Phân biệt UTF-8 bytes và Java char offsets |
| Highlight sai file | Dùng unit/LineMap của source khác | Mang đúng `CompilationUnitTree` cùng node |
| `IndexOutOfBoundsException` khi substring | Chưa kiểm tra `NOPOS` hoặc source snapshot khác | Validate offset, bounds, snapshot |
| Chỉ tìm vị trí của class ngoài JAR | Không có source AST cho dependency | Dùng symbol metadata, nếu không có source thì fallback |
| `getElement(path)` là null | Chưa analyze hoặc source có lỗi | Chạy đúng pha và xử lý resolution errors |
| Tô cả invocation thay vì tên method | Chọn `MethodInvocationTree` quá rộng | Chọn subtree đúng hoặc token source |
| Báo warning bằng `System.out.println` | Mất tích hợp diagnostic/source location | Dùng `Trees.printMessage` |
| Dùng `node.toString()` rồi search trong file | Pretty-print không giống source gốc | Lấy offsets từ `SourcePositions` |
| Sai vị trí sau edit | Cache offsets theo source cũ | Gắn version/snapshot, parse lại sau chỉnh sửa |
| Có `-1` trong output | Compiler không có vị trí cho node | Kiểm tra `Diagnostic.NOPOS` |
| Diagnostic có dòng nhưng không có end span | Không phải compiler nào cũng cung cấp vùng highlight đầy đủ | Hiển thị caret ở position hoặc fallback |
| Thông báo lặp lại trên AST con/cháu | Scanner báo tại cả outer và inner invocation | Thiết kế rule theo loại node, owner/context |

## 12. Quy trình đưa tọa độ AST sang IDE hoặc báo cáo static analysis

Một pipeline đáng tin cậy thường gồm:

1. **Chốt nguồn:** lưu source URI, encoding, version/hash hoặc snapshot ID trước phân tích.
2. **Tạo JavacTask:** chọn compilation units, `--release`, classpath/module path, annotation processing policy. Không dùng input khác với file mà editor đang hiển thị.
3. **Parse AST:** lấy `CompilationUnitTree` và `Trees.getSourcePositions()`.
4. **Scan có context:** dùng `TreePathScanner`; tại mỗi node cần báo, giữ đúng unit và path.
5. **Lấy offset hợp lệ:** kiểm tra `getStartPosition`, `getEndPosition` khác `Diagnostic.NOPOS` và trật tự/bounds hợp lệ.
6. **Đổi tọa độ:** dùng `LineMap`. Chọn chuẩn 1-based/0-based ở lớp giao tiếp UI, không rải phép `+1/-1` trên toàn bộ analyzer.
7. **Xác minh ngữ nghĩa nếu rule cần:** thực hiện `analyze` rồi dùng `Trees.getElement/getTypeMirror`, xử lý symbols không resolve.
8. **Xuất diagnostic:** ưu tiên compiler diagnostic API hoặc cấu trúc gồm file/span/severity/code/message, tránh chỉ có một chuỗi text.
9. **Kiểm thử nội dung cụ thể:** gồm nested calls, multi-line invocations, tab, CRLF, Unicode, source lỗi và generated nodes.
10. **Đảm bảo không stale:** so khớp source snapshot trước khi editor highlight hoặc áp dụng quick fix.

### Bài thực hành

- Chạy nguyên ví dụ `LocateCalls` để nhận `CALL System.out.println @ 5:9` và `CALL Math.max @ 5:28`.
- Thêm một dòng trống ở đầu `Sample.java`; dự đoán hai lời gọi chuyển sang dòng 6 và chạy lại để xác nhận.
- Đổi 8 dấu cách trước `System` thành 1 tab; dùng output thực nghiệm để kiểm tra tab expansion trong `LineMap`.
- Đưa `Math.max` xuống dòng tiếp theo; so sánh start/end của outer invocation và inner invocation.
- Thêm `trees.printMessage(Diagnostic.Kind.WARNING, "Review this invocation", node, unit)` trong visitor; quan sát compiler gắn warning vào vị trí node.
- Thử source thiếu dấu `;`, phân biệt parser diagnostics với custom analyzer warnings; đừng gán vị trí giả cho node mà compiler trả `NOPOS`.
- Nếu xây IDE, đổi tọa độ sang convention editor một lần tại boundary và kiểm tra việc highlight sau khi file thay đổi.

**Kết luận:** `SourcePositions` trả **offset gắn với nút AST và compilation unit**, `LineMap` chuyển offset thành **dòng/cột theo source**, còn `Trees.printMessage` hoặc `DiagnosticCollector` nối kết phát hiện phân tích với **chẩn đoán có vị trí**. Dùng các API này thay cho việc parse `Tree.toString()` hoặc tự đếm dấu xuống dòng sẽ cho kết quả chính xác và dễ mở rộng hơn khi source có nested expressions, Unicode, tab, nhiều file và lỗi compiler.

## Tài liệu tham khảo

- [Java SE 17 — SourcePositions](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/SourcePositions.html).
- [Java SE 17 — LineMap](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/tree/LineMap.html).
- [Java SE 17 — Trees](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/Trees.html).
- [Java SE 17 — TreePathScanner](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/TreePathScanner.html).
- [Java SE 17 — JavacTask](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/JavacTask.html).

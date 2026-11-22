# Phân tích cây cú pháp Java lồng nhau mà vẫn giữ đúng ngữ cảnh điều khiển

## 1. Vấn đề cần giải quyết

Trong Java, một câu lệnh có thể nằm sâu bên trong nhiều cấu trúc: phương thức → vòng lặp có nhãn → nhánh `if` → `switch` → nhánh `case` → `break`. Nếu công cụ phân tích chỉ đếm số lượng `if`, `for`, `return`, `yield` hoặc `break` mà **không nhớ cấu trúc đang bao quanh**, nó rất dễ báo sai ý nghĩa của câu lệnh.

Ví dụ:

```java
outer:
for (int i = 0; i < 2; i++) {
    if (i == 0) {
        switch (i) {
            case 0 -> { break outer; }
            default -> {}
        }
    } else {
        continue outer;
    }
}
```

Hai câu lệnh có cùng nhãn `outer`, nhưng ý nghĩa khác nhau:

- `break outer` kết thúc **toàn bộ labeled statement `outer: for (...) ...`**.
- `continue outer` chuyển sang **lượt lặp tiếp theo** của vòng lặp được gắn nhãn `outer`.
- `switch` ở giữa **không phải đích** của `break outer`, dù nó gần hơn về độ sâu trong AST.
- Một `continue` không nhãn trong ngữ cảnh có nhiều vòng lặp lại nhắm tới vòng lặp thích hợp **gần nhất**.

Tương tự, một `return` nằm trong thân lambda **không kết thúc phương thức chứa lambda**; một `yield` hoàn tất **`switch` expression**, không phải cả phương thức.

Bài học hướng dẫn cách sử dụng **Java Compiler Tree API** để duyệt AST (*Abstract Syntax Tree*), duy trì **ngữ cảnh điều khiển** khi đi vào/đi ra cấu trúc lồng nhau, và nhận diện đích điều khiển ở mức **cú pháp**. Đồng thời bài phân biệt rạch ròi **AST traversal** với **Control-Flow Graph (CFG)**: duyệt cây không tự tạo một mô hình thực thi runtime đầy đủ.

**Ngữ cảnh phiên bản:** `switch` expression và `yield` trở thành tính năng chuẩn ở **Java 14** (JEP 361), nên chúng là ví dụ điển hình cho việc phân tích điều khiển lồng nhau. `TreePathScanner` thuộc module `jdk.compiler` vẫn là API được hỗ trợ trên các JDK hiện đại. Chương trình hoàn chỉnh dùng **Java 17+**, không dựa vào tính năng preview hay các lớp triển khai nội bộ `com.sun.tools.javac.*`.

## 2. Phân biệt AST, đường dẫn cha và ngữ cảnh điều khiển

Ba thứ sau liên quan nhau nhưng **không đồng nghĩa**:

| Thành phần | Nó mô tả gì? | Nó không tự giải quyết gì? |
| --- | --- | --- |
| **AST** | Cấu trúc cú pháp: node `IfTree`, `ForLoopTree`, `SwitchTree`, `ReturnTree`, v.v. | Thứ tự chạy thực tế, số lần lặp, đường đi nào khả thi |
| **`TreePath`** | Chuỗi các node từ compilation unit tới node hiện tại | Không tự suy ra đích `break`, `continue`, `return` hay đường exception |
| **Ngữ cảnh điều khiển** | Thông tin logic do analyzer giữ: đang ở phương thức/lambda nào, nhánh `then/else` nào, loop/case/switch nào, label nào còn hiệu lực | Không tự chứng minh data-flow, reachability hoặc side effect của runtime |

Một công cụ nên dùng **`TreePathScanner` để đi đúng cây** và dùng **một stack/frame ngữ cảnh có quản lý vòng đời** để biểu diễn những thông tin quan trọng cho câu hỏi đang phân tích.

Ví dụ phân tích một câu lệnh `break` có thể có ngữ cảnh:

```text
METHOD:evaluate
  > LABEL:outer
  > LOOP
  > IF_THEN
  > SWITCH_STMT
  > CASE
  > IF_THEN
  > BREAK
```

Nơi đứng của câu lệnh là sâu trong `switch`, nhưng đích điều khiển của `break outer` vẫn là **labeled statement `outer`**. Nếu chỉ nhớ “node điều khiển gần nhất là `switch`”, phân tích sẽ sai.

### Vì sao không nên đi tìm ngoặc bằng String?

Biểu thức chính quy hoặc phép đếm `{`/`}` trên source text rất dễ bị nhầm bởi comment, string, text block, lambda, annotation và cú pháp `if` không có dấu ngoặc. Java còn có quy tắc *dangling else*: `else` gắn với `if` gần nhất còn thiếu `else` theo ngữ pháp, không đơn giản theo số khoảng trắng.

Dùng một **parser Java đúng phiên bản ngôn ngữ** để nhận cấu trúc cây trước khi phân tích ngữ cảnh.

## 3. API còn áp dụng: `com.sun.source.tree` và `TreePathScanner`

Các loại cần biết:

| API | Vai trò |
| --- | --- |
| `javax.tools.ToolProvider.getSystemJavaCompiler()` | Lấy Java compiler được cung cấp bởi JDK |
| `com.sun.source.util.JavacTask` | Tác vụ compiler cung cấp `parse()`, `analyze()` |
| `com.sun.source.tree.CompilationUnitTree` | Gốc AST của một source file |
| `TreePathScanner<R,P>` | Visitor duyệt cây, tự cập nhật `TreePath` cho node hiện tại |
| `TreePathScanner.getCurrentPath()` | Lấy đường dẫn AST của node đang được visitor xử lý |
| `IfTree` | Điều kiện, nhánh `then` và `else` |
| `ForLoopTree`, `WhileLoopTree`, `EnhancedForLoopTree` | Các node vòng lặp |
| `LabeledStatementTree` | Câu lệnh có nhãn, ví dụ `outer: for (...)` |
| `SwitchTree` | `switch` **statement** |
| `SwitchExpressionTree` | `switch` **expression** tạo ra giá trị |
| `CaseTree` | Một nhánh/case trong `switch` |
| `BreakTree`, `ContinueTree`, `ReturnTree`, `YieldTree` | Các câu lệnh chuyển quyền điều khiển |

Đối với chương trình chạy trên **classpath**, không cần import các package nội bộ của compiler. Với chương trình có `module-info.java`, module sử dụng Tree API cần khai báo dependency tới `jdk.compiler` (và các yêu cầu module tương ứng).

```java
module ast.example {
    requires jdk.compiler;
}
```

Đây là **đoạn minh họa module descriptor**, không dùng đồng thời với cách chạy `Main.java` đơn giản bằng classpath dưới đây.

**Lưu ý:** `TreePathScanner` khác `TreeScanner` ở việc tự duy trì **đường dẫn hiện tại**. Từ một `visitXxx`, gọi `super.visitXxx` để duyệt con, hoặc chủ động gọi `scan(child, p)` khi cần điều khiển thứ tự và ngữ cảnh. Nếu tự duyệt child nhưng đồng thời gọi `super` như bình thường, node đó có thể được phân tích **hai lần**.

## 4. Quy tắc control-flow cần nhớ trước khi cài đặt

| Câu lệnh | Đích theo ngữ nghĩa Java | Điều dễ nhầm khi lồng nhau |
| --- | --- | --- |
| `break;` | Vòng lặp hoặc **switch statement** gần nhất bao quanh phù hợp | Không tự nhắm tới `if` hay `switch expression` |
| `break label;` | **Labeled statement** có nhãn phù hợp | Có thể thoát khỏi nhiều cấu trúc lồng nhau |
| `continue;` | Vòng lặp gần nhất phù hợp | Không nhắm tới `switch` hoặc `if` |
| `continue label;` | Vòng lặp được gắn nhãn phù hợp | Nhãn phải gắn với một **iteration statement** hợp lệ |
| `return;` / `return value;` | Thực thể thực thi hiện tại: phương thức/constructor hoặc lambda tùy ngữ cảnh và dạng return hợp lệ | `return` trong lambda không thoát phương thức ngoài |
| `yield expr;` | `switch` expression gần nhất hợp lệ | Không phải `return`; không dùng để kết thúc `switch` statement |
| `throw expr;` | Chuyển theo cơ chế exception handling | Cần xét `catch`/`finally` và các cạnh lỗi ngầm |
| `if` / `else` | Lựa chọn nhánh theo giá trị điều kiện runtime | AST có cả hai nhánh, không nói nhánh nào chạy |
| `for` / `while` / `do` | Lặp khi điều kiện cho phép | AST traversal chỉ thăm **một lần** mỗi node, không mô phỏng số lần lặp |
| `try` / `catch` / `finally` | Luồng bình thường và luồng hoàn thành đột ngột | `finally` có thể chạy ngay cả khi có `return`/`break` và có thể làm đổi kết quả hoàn thành |

Các quy tắc trên căn cứ Java Language Specification, đặc biệt phần **normal/abrupt completion** (`14.1) và `break`/`continue`/`return`/`yield` (`14.15–14.17, `14.21).

**Ranh giới quan trọng:** `switch` **statement** và `switch` **expression** là hai loại AST khác nhau. Khi một công cụ chỉ nhìn token `switch` và gộp chúng thành một loại, việc phân tích `break`/`yield` có thể sai.

## 5. Thiết kế ngăn xếp ngữ cảnh

Một cách triển khai dễ hiểu là giữ `Deque<Frame>`:

```java
record Frame(String type, String label) {}

Deque<Frame> frames = new ArrayDeque<>();
```

Đây là phần khai báo minh họa bên trong một lớp/phương thức có import phù hợp; nó chưa phải chương trình độc lập.

Mỗi frame đại diện cho một lớp ngữ cảnh, ví dụ:

- `METHOD:evaluate`: tên phương thức đang phân tích.
- `LAMBDA`: đánh dấu ranh giới thân lambda.
- `LABEL:outer`: có một labeled statement trong scope.
- `LOOP`: đang đi qua một vòng lặp.
- `IF_THEN` hoặc `IF_ELSE`: AST node thuộc nhánh nào.
- `SWITCH_STMT` hoặc `SWITCH_EXPR`: phân biệt statement/expression.
- `CASE` hoặc `DEFAULT`: vị trí một case.

Quy tắc quản lý stack:

1. **Khi vào** node mang ý nghĩa ngữ cảnh, `push(frame)`.
2. **Duyệt** node con khi frame còn nằm trên stack.
3. **Khi rời** node, `pop()`.
4. Dùng `try/finally` để đảm bảo pop ngay cả nếu visitor ném exception.
5. Khi bắt đầu một **thực thể thực thi khác** (method, lambda, initializer hoặc class lồng), phải tránh suy luận jump target xuyên qua ranh giới không hợp lệ.
6. Không dùng một biến Boolean toàn cục kiểu `insideLoop`: nó không biểu diễn được độ sâu, nhiều vòng lặp hoặc sự khác nhau giữa các scope.

Khung helper:

```java
private Void inside(String type, String label, Supplier<Void> visit) {
    frames.push(new Frame(type, label));
    try {
        return visit.get();
    } finally {
        frames.pop();
    }
}
```

Với cách này, một `break` bên trong `switch` lồng trong `for` vẫn có thể tra ngược từ frame trong cùng ra frame ngoài một cách kiểm soát. Khi rời khỏi `switch`, frame `SWITCH_STMT` được bỏ đúng thời điểm và không “rò” sang câu lệnh tiếp theo.

## 6. Chương trình Java 17+ hoàn chỉnh: phân tích lồng nhau

Chương trình sau dùng `JavaCompiler` và `JavacTask` để parse **một source file Java giả lập đang nằm trong bộ nhớ**, rồi dùng `TreePathScanner` ghi nhận các câu lệnh chuyển quyền điều khiển.

Bộ scanner minh họa giữ riêng các lớp `METHOD`, `LAMBDA`, `LABEL`, `LOOP`, `IF_THEN`, `IF_ELSE`, `SWITCH_STMT`, `SWITCH_EXPR` và `CASE/DEFAULT`. Với dữ liệu thử hợp lệ, nó truy ra đích gần nhất phù hợp cho `break`, `continue`, `return` và `yield`.

### Toàn bộ tệp `Main.java`

```java
import com.sun.source.tree.*;
import com.sun.source.util.JavacTask;
import com.sun.source.util.TreePathScanner;
import java.net.URI;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.Iterator;
import java.util.List;
import java.util.function.Supplier;
import javax.tools.*;

public class Main {
    record Frame(String type, String label) {
        String display() {
            return label.isEmpty() ? type : type + ":" + label;
        }
    }

    static class ContextScanner extends TreePathScanner<Void, Void> {
        private final Deque<Frame> frames = new ArrayDeque<>();

        private Void inside(String type, String label, Supplier<Void> visit) {
            frames.push(new Frame(type, label));
            try {
                return visit.get();
            } finally {
                frames.pop();
            }
        }

        private String context() {
            List<String> parts = new ArrayList<>();
            Iterator<Frame> iterator = frames.descendingIterator();
            while (iterator.hasNext()) {
                parts.add(iterator.next().display());
            }
            return String.join(" > ", parts);
        }

        private String nearest(String... types) {
            for (Frame frame : frames) {
                for (String type : types) {
                    if (frame.type().equals(type)) {
                        return frame.display();
                    }
                }
                if (frame.type().equals("METHOD")
                        || frame.type().equals("LAMBDA")) {
                    break;
                }
            }
            return "UNRESOLVED";
        }

        private String labeled(String label) {
            for (Frame frame : frames) {
                if (frame.type().equals("LABEL")
                        && frame.label().equals(label)) {
                    return frame.display();
                }
                if (frame.type().equals("METHOD")
                        || frame.type().equals("LAMBDA")) {
                    break;
                }
            }
            return "UNRESOLVED";
        }

        private void report(String operation, String target) {
            System.out.println(operation + " -> " + target
                    + " | " + context()
                    + " | ast=" + getCurrentPath().getLeaf().getKind());
        }

        @Override
        public Void visitMethod(MethodTree tree, Void p) {
            return inside("METHOD", tree.getName().toString(),
                    () -> super.visitMethod(tree, p));
        }

        @Override
        public Void visitLambdaExpression(LambdaExpressionTree tree, Void p) {
            return inside("LAMBDA", "",
                    () -> super.visitLambdaExpression(tree, p));
        }

        @Override
        public Void visitLabeledStatement(LabeledStatementTree tree, Void p) {
            return inside("LABEL", tree.getLabel().toString(),
                    () -> super.visitLabeledStatement(tree, p));
        }

        @Override
        public Void visitForLoop(ForLoopTree tree, Void p) {
            return inside("LOOP", "",
                    () -> super.visitForLoop(tree, p));
        }

        @Override
        public Void visitWhileLoop(WhileLoopTree tree, Void p) {
            return inside("LOOP", "",
                    () -> super.visitWhileLoop(tree, p));
        }

        @Override
        public Void visitDoWhileLoop(DoWhileLoopTree tree, Void p) {
            return inside("LOOP", "",
                    () -> super.visitDoWhileLoop(tree, p));
        }

        @Override
        public Void visitEnhancedForLoop(EnhancedForLoopTree tree, Void p) {
            return inside("LOOP", "",
                    () -> super.visitEnhancedForLoop(tree, p));
        }

        @Override
        public Void visitIf(IfTree tree, Void p) {
            scan(tree.getCondition(), p);
            inside("IF_THEN", "",
                    () -> scan(tree.getThenStatement(), p));
            if (tree.getElseStatement() != null) {
                inside("IF_ELSE", "",
                        () -> scan(tree.getElseStatement(), p));
            }
            return null; // Already scanned each child once.
        }

        @Override
        public Void visitSwitch(SwitchTree tree, Void p) {
            return inside("SWITCH_STMT", "",
                    () -> super.visitSwitch(tree, p));
        }

        @Override
        public Void visitSwitchExpression(SwitchExpressionTree tree, Void p) {
            return inside("SWITCH_EXPR", "",
                    () -> super.visitSwitchExpression(tree, p));
        }

        @Override
        public Void visitCase(CaseTree tree, Void p) {
            String branch = tree.getExpressions().isEmpty()
                    ? "DEFAULT" : "CASE";
            return inside(branch, "", () -> super.visitCase(tree, p));
        }

        @Override
        public Void visitBreak(BreakTree tree, Void p) {
            String target = tree.getLabel() == null
                    ? nearest("LOOP", "SWITCH_STMT")
                    : labeled(tree.getLabel().toString());
            report("BREAK", target);
            return super.visitBreak(tree, p);
        }

        @Override
        public Void visitContinue(ContinueTree tree, Void p) {
            String target = tree.getLabel() == null
                    ? nearest("LOOP")
                    : labeled(tree.getLabel().toString());
            report("CONTINUE", target);
            return super.visitContinue(tree, p);
        }

        @Override
        public Void visitReturn(ReturnTree tree, Void p) {
            report("RETURN", nearest("LAMBDA", "METHOD"));
            return super.visitReturn(tree, p);
        }

        @Override
        public Void visitYield(YieldTree tree, Void p) {
            report("YIELD", nearest("SWITCH_EXPR"));
            return super.visitYield(tree, p);
        }
    }

    public static void main(String[] args) throws Exception {
        String source = """
                class Sample {
                    static int evaluate(int x) {
                        outer:
                        for (int i = 0; i < 2; i++) {
                            if (x > 0) {
                                switch (i) {
                                    case 0 -> {
                                        if (x > 10) break outer;
                                    }
                                    default -> {}
                                }
                            } else {
                                continue outer;
                            }
                        }
                        return switch (x) {
                            case 0 -> 0;
                            default -> {
                                if (x < 0) yield -1;
                                yield x;
                            }
                        };
                    }

                    static java.util.function.IntUnaryOperator op() {
                        return n -> {
                            if (n < 0) return -1;
                            return n + 1;
                        };
                    }
                }
                """;

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "A JDK with jdk.compiler is required");
        }

        JavaFileObject file = new SimpleJavaFileObject(
                URI.create("string:///Sample.java"),
                JavaFileObject.Kind.SOURCE) {
            @Override
            public CharSequence getCharContent(boolean ignoreEncodingErrors) {
                return source;
            }
        };

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();
        JavacTask task = (JavacTask) compiler.getTask(
                null, null, diagnostics,
                List.of("--release", "17", "-proc:none"),
                null, List.of(file));

        Iterable<? extends CompilationUnitTree> units = task.parse();
        task.analyze(); // Validate source, without generating class files.
        if (diagnostics.getDiagnostics().stream().anyMatch(
                d -> d.getKind() == Diagnostic.Kind.ERROR)) {
            throw new IllegalStateException(
                    "Sample source has Java errors");
        }

        ContextScanner scanner = new ContextScanner();
        for (CompilationUnitTree unit : units) {
            scanner.scan(unit, null);
        }
    }
}
```

**Biên dịch và chạy bằng JDK 17 hoặc mới hơn:**

```bash
javac --release 17 -encoding UTF-8 Main.java
java Main
```

Chương trình cần **JDK có compiler**; một runtime bị tối giản không chứa `jdk.compiler` có thể không cung cấp `ToolProvider.getSystemJavaCompiler()`. `-proc:none` tắt xử lý annotation processor trong tác vụ ví dụ, tránh để một source thử đơn giản kéo theo annotation processing không cần thiết.

### Stdout chính xác đã kiểm chứng

```text
BREAK -> LABEL:outer | METHOD:evaluate > LABEL:outer > LOOP > IF_THEN > SWITCH_STMT > CASE > IF_THEN | ast=BREAK
CONTINUE -> LABEL:outer | METHOD:evaluate > LABEL:outer > LOOP > IF_ELSE | ast=CONTINUE
RETURN -> METHOD:evaluate | METHOD:evaluate | ast=RETURN
YIELD -> SWITCH_EXPR | METHOD:evaluate > SWITCH_EXPR > DEFAULT > IF_THEN | ast=YIELD
YIELD -> SWITCH_EXPR | METHOD:evaluate > SWITCH_EXPR > DEFAULT | ast=YIELD
RETURN -> METHOD:op | METHOD:op | ast=RETURN
RETURN -> LAMBDA | METHOD:op > LAMBDA > IF_THEN | ast=RETURN
RETURN -> LAMBDA | METHOD:op > LAMBDA | ast=RETURN
```

**Phép kiểm thử:** chương trình được biên dịch bằng `javac --release 17` và chạy thành công trên JDK hiện đại; cả **8 dòng** khớp kết quả trên. Chương trình phân tích **một class `Sample` được nhúng như chuỗi văn bản**, không chạy mã `Sample.evaluate(...)` hoặc `Sample.op()`.

## 7. Cách đọc kết quả mà không nhầm với thời gian chạy

### 7.1. Hai loại chuyển vòng lặp có nhãn

`BREAK -> LABEL:outer` đến từ câu lệnh trong `case 0` của `switch statement`, trong `IF_THEN`, trong `for` mang nhãn `outer`. Nó rời khỏi cả labeled statement.

`CONTINUE -> LABEL:outer` xuất hiện trong `else` của `if (x > 0)`. Nó chuyển tới lượt lặp tiếp theo của `for` được gắn nhãn.

Một công cụ chỉ ghi “break nằm trong switch” sẽ báo sai đích của `break outer`; một công cụ không ghi nhận `IF_ELSE` sẽ làm mất thông tin rằng `continue outer` nằm ở nhánh trái ngược với `break outer`.

### 7.2. `return switch (...)` tạo hai tầng điều khiển

Dòng:

```java
return switch (x) {
    case 0 -> 0;
    default -> {
        if (x < 0) yield -1;
        yield x;
    }
};
```

có **`ReturnTree` bên ngoài** và **`SwitchExpressionTree` bên trong**. Các lệnh `yield` trả giá trị cho switch expression; **`return` của phương thức** mới trả giá trị cuối cùng cho bên gọi phương thức.

Duyệt AST theo `TreePathScanner` có thể **in sự kiện RETURN trước các YIELD** vì visitor của node `ReturnTree` được gọi trước khi scanner đi vào expression con. Đó là **thứ tự duyệt cây**, **không phải thứ tự thực thi**. Lúc chạy, biểu thức `switch` phải được đánh giá để có giá trị trước khi `return` hoàn tất.

**Không được dùng thứ tự log của AST để kết luận “return xảy ra trước yield” ở runtime.**

### 7.3. `return` trong lambda khác `return` của phương thức

Trong `op()`:

```java
return n -> {
    if (n < 0) return -1;
    return n + 1;
};
```

- `return n -> ...` ở bên ngoài trả về **đối tượng functional interface** từ phương thức `op()`.
- Hai câu lệnh `return` ở **thân lambda** trả kết quả khi **lambda được gọi**, không thoát khỏi phương thức `op()` tại thời điểm khởi tạo lambda.
- Stack của scanner cho thấy `METHOD:op > LAMBDA`. Khi tìm target của `return` trong lambda, phải dừng ở `LAMBDA` gần nhất.

Không nên duyệt từ `ReturnTree` ngược tới `MethodTree` gần nhất trong `TreePath` mà bỏ qua `LambdaExpressionTree`, vì sẽ gắn nhầm đích điều khiển.

## 8. Vì sao phải quét `if` theo ba phần?

`IfTree` cung cấp ba thành phần:

```java
tree.getCondition()
tree.getThenStatement()
tree.getElseStatement()
```

`getElseStatement()` có thể trả về `null` nếu không có nhánh else.

Trong chương trình ví dụ:

```java
@Override
public Void visitIf(IfTree tree, Void p) {
    scan(tree.getCondition(), p);
    inside("IF_THEN", "",
            () -> scan(tree.getThenStatement(), p));
    if (tree.getElseStatement() != null) {
        inside("IF_ELSE", "",
                () -> scan(tree.getElseStatement(), p));
    }
    return null;
}
```

Cách thực hiện có ý nghĩa:

1. Quét điều kiện **ngoài** frame `IF_THEN`/`IF_ELSE`. Điều kiện được đánh giá để quyết định nhánh, không thuộc kết quả của một trong hai nhánh.
2. Khi quét `then`, push `IF_THEN`.
3. Khi quét `else`, push `IF_ELSE`.
4. Frame được pop sau khi child scan xong; sibling không thừa hưởng nhầm frame.
5. Trả `null` vì các child đã được quét; **không tiếp tục gọi `super.visitIf(...)`**, nếu không điều kiện/nhánh sẽ bị quét lần thứ hai.

Nếu mục tiêu phân tích cần biết **đang ở biểu thức điều kiện**, có thể tạo frame riêng `IF_CONDITION` quanh `scan(tree.getCondition(), p)`, nhưng không nên gắn toàn bộ điều kiện vào `IF_THEN`.

### `else if` thực ra là một `if` lồng trong else

```java
if (a) {
    actionA();
} else if (b) {
    actionB();
} else {
    actionC();
}
```

Đây là **snippet minh họa**, các biến/phương thức phải được định nghĩa khi dùng trong chương trình thật. Về mặt AST, phần `else if (b)` là một **`IfTree` nằm trong `getElseStatement()` của `if (a)`**. Scanner có thể ghi bối cảnh `IF_ELSE > IF_THEN` cho `actionB()`.

Đừng san phẳng `if` và `else if` thành các nhánh độc lập mà quên các điều kiện trước đó. Nếu cần tạo logic path condition, nhánh của `actionB` còn mang điều kiện **`!a && b`** trong cách diễn giải đơn giản không có side effect.

### “Dangling else”

```java
if (a)
    if (b)
        actionA();
    else
        actionB();
```

Theo ngữ pháp Java, `else` trên gắn với **`if (b)`**, không gắn với `if (a)`. Đây là đoạn minh họa cú pháp. `IfTree.getElseStatement()` phản ánh cấu trúc parser đã xác định; không suy đoán bằng thụt đầu dòng của text.

## 9. Xử lý loop và label theo scope đúng

Trong ví dụ, `visitForLoop` push `LOOP` trước khi gọi `super.visitForLoop`. Điều đó cho biết các node con đang nằm trong cấu trúc vòng lặp. Tuy nhiên, để thiết kế một analyzer phức tạp hơn, có thể phân biệt bốn pha của `for`:

```text
for (
    initializer;   // chạy lúc vào vòng lặp
    condition;     // kiểm tra trước mỗi lượt
    update         // chạy sau thân/continue phù hợp
) {
    body;           // phần thân lặp
}
```

Một visitor chuyên sâu có thể giữ frame `FOR_INIT`, `FOR_CONDITION`, `FOR_UPDATE` và `FOR_BODY` khi quét từng phần. Không nên kết luận rằng một biểu thức ở `update` và một statement ở `body` xảy ra cùng số lần hoặc cùng thứ tự chỉ vì cả hai có parent `ForLoopTree`.

**`continue` không chỉ đơn giản “nhảy về đầu file”**. Trong basic `for`, sau `continue` hợp lệ, các update expressions được xử lý theo quy tắc vòng lặp rồi điều kiện được kiểm tra cho lượt kế. Với `while`/`do`/enhanced `for`, quy tắc tiếp tục khác về cấu trúc thực thi. AST scanner cơ bản chỉ xác định **đích loop**, không tự tạo đầy đủ cạnh CFG.

### Bảng đích cho nhãn

| Mẫu mã hợp lệ | Ý nghĩa |
| --- | --- |
| `outer: for (...) { break outer; }` | Rời khỏi labeled statement `outer` |
| `outer: for (...) { continue outer; }` | Tiếp tục vòng lặp mang nhãn `outer` |
| `label: { break label; }` | `break` có thể thoát khỏi một labeled block |
| `label: { continue label; }` | **Không hợp lệ** vì `continue` label cần iteration statement |
| `for (...) { switch (...) { case ...: break; } }` | `break` không nhãn thoát `switch statement` gần nhất |
| `for (...) { if (...) continue; }` | `continue` không nhãn nhắm tới vòng lặp gần nhất |

Trong demo, `labeled(String)` chỉ tra một **nhãn có tên** trong stack rồi in mục tiêu. Nó được áp dụng cho **source đã qua `JavacTask.analyze()` và không có lỗi**, nên ví dụ hợp lệ. **Đối với analyzer production**, cần ghi thêm **loại labeled statement** và xác nhận đặc biệt rằng đích `continue label` là một loop, không chấp nhận tùy tiện nhãn của một block/switch.

Ngoài ra, source có thể có label cùng tên lồng nhau hoặc class/lambda/method bên trong. Phải xác định nhãn **có hiệu lực gần nhất trong cùng thực thể thực thi**, tránh tra xuyên qua ranh giới bất hợp lệ.

## 10. `switch statement` và `switch expression` có ngữ nghĩa khác nhau

Java có cả:

```java
switch (day) {
    case 1 -> System.out.println("Monday");
    default -> System.out.println("Other");
}
```

và:

```java
String name = switch (day) {
    case 1 -> "Monday";
    default -> "Other";
};
```

Đây là hai snippet minh họa trong phương thức có `day` kiểu phù hợp. Đoạn đầu là **`SwitchTree`**, đoạn sau là **`SwitchExpressionTree`**.

Sự khác nhau:

- `SwitchTree` biểu diễn **statement**; các quy tắc `break` không nhãn áp dụng cho switch statement. Với `case L -> ...`, dạng rule không có fall-through giữa các rule như các statement group kiểu dấu `:`.
- `SwitchExpressionTree` phải tạo một giá trị hoặc hoàn thành đột ngột theo quy tắc ngôn ngữ; dùng biểu thức trực tiếp ở nhánh `->` hoặc `yield` trong block.
- `yield` có đích là **`switch expression` gần nhất hợp lệ**, không phải bất kỳ `switch` nào.
- `break label` và `continue label` có đích theo cấu trúc bao quanh nhưng **không thể nhảy xuyên qua switch expression một cách tùy ý**; compiler thực thi các giới hạn control transfer của ngôn ngữ.
- Trong Java 21+, pattern matching for switch được chuẩn hóa và có thể tạo thêm loại case label/guard phức tạp; analyzer nên cập nhật xử lý AST theo JDK mục tiêu, không giả định mọi case chỉ là một số nguyên.

### Giới hạn cố ý của `visitCase` trong ví dụ

```java
String branch = tree.getExpressions().isEmpty()
        ? "DEFAULT" : "CASE";
```

Đây là cách phân biệt **constant case/default** trong input demo Java 17. Nó **không phải bộ phân tích label tổng quát** cho mọi loại pattern case ở các JDK mới. Khi mở rộng, đọc API `CaseTree.getLabels()` và các loại `CaseLabelTree` có trong JDK mục tiêu, đồng thời kiểm thử trường hợp `case null, default`, guarded pattern và nhiều nhãn.

Không nên dùng `tree.toString()` như một parser phụ để tìm chữ `default` hoặc bóc điều kiện: việc in lại AST không có nghĩa phản ánh chính xác mọi nguồn hay đặc điểm semantic.

## 11. Vì sao `TreePathScanner` hỗ trợ giữ ngữ cảnh chính xác?

Khi override `visitBreak(BreakTree tree, ...)`, `getCurrentPath().getLeaf()` chính là node `BreakTree` đang được quét. Từ `TreePath` bạn có thể tìm parent:

```java
TreePath current = getCurrentPath();
TreePath parentPath = current.getParentPath();
Tree parent = parentPath == null ? null : parentPath.getLeaf();
```

Đây là snippet **trong một lớp kế thừa `TreePathScanner`**, yêu cầu import `com.sun.source.tree.Tree` và `com.sun.source.util.TreePath`. Khi dùng `TreePathScanner.scan(Tree, p)` từ các visitor, đường dẫn được thiết lập đúng trong thời gian duyệt child rồi phục hồi khi trở ra.

**Nhưng chỉ có `TreePath` vẫn chưa đủ để báo đích mọi câu lệnh:**

- Một `break outer` có thể đi qua nhiều parent là `IfTree`, `BlockTree` và `SwitchTree` trước khi tới `LabeledStatementTree` đúng tên.
- `return` trong lambda cần dừng tại lambda trước khi tới method.
- Phân tích hoạt động ở cả `catch`, `finally` và nhánh điều kiện cần lưu thông tin logic, không chỉ `Tree.Kind`.
- Khi quét lại một subtree ở scope khác hoặc một analysis pass khác, ngữ cảnh của công cụ phải được **khởi tạo cho đúng entry point**; không tái sử dụng stack sót từ lần trước.

Ưu điểm của kết hợp `TreePathScanner` + frame stack là một phần giữ **cấu trúc cú pháp chính thức**, phần còn lại giữ **câu hỏi nghiệp vụ mà analyzer muốn trả lời**.

### Khi bắt đầu quét

Trong chương trình hoàn chỉnh:

```java
for (CompilationUnitTree unit : units) {
    scanner.scan(unit, null);
}
```

`scan` khởi tạo đường dẫn từ root. Theo hợp đồng `TreePathScanner`, gọi `getCurrentPath()` bên trong visitor khi đang scan mới có ngữ cảnh có ý nghĩa. Đừng gọi `getCurrentPath()` sau khi toàn bộ scan hoàn tất rồi kỳ vọng nó còn trỏ tới node `break` cuối cùng.

## 12. Ranh giới phương thức, lambda, lớp và initializer

Một analyzer chỉ có stack loop/if có thể mắc lỗi khi gặp:

```java
void outer() {
    Runnable action = () -> {
        while (true) {
            return; // Chỉ kết thúc lần chạy lambda này.
        }
    };
    action.run();
    // Phương thức outer vẫn có thể tiếp tục.
}
```

Đây là snippet Java minh họa. `return` trong lambda có thân block chỉ rời khỏi việc thực thi lambda; không phải “non-local return” khỏi `outer()`.

Tương tự, phương thức nằm trong **local class hoặc anonymous class** có một thực thể thực thi riêng. Không cho một `break`, `continue` hoặc `yield` tìm target trong các frame vòng lặp ở phương thức chứa khai báo class ấy.

**Chiến lược production:**

1. Khi đi vào `MethodTree`, tạo scope điều khiển mới với identifier riêng, và lưu/restoring scope của bên ngoài nếu cần báo bối cảnh từ vựng.
2. Khi đi vào `LambdaExpressionTree`, tạo ranh giới return và các loop/switch thuộc lambda; không giải jump xuyên lambda.
3. Khi đi vào `ClassTree`, phân biệt **cấu trúc từ vựng chứa khai báo** với **đường thực thi phương thức/initializer của class đó**. Có thể reset stack điều khiển thực thi, giữ riêng metadata về class cha.
4. Với static/instance initializer, cần frame riêng cho execution context thích hợp, không mặc nhiên gán mọi statement vào method gần nhất.
5. Sau mỗi scope, dùng `finally` để phục hồi trạng thái của scanner.

**Giới hạn của chương trình demo:** nó in kết quả chính xác cho source mẫu đã phân tích; nó **không triển khai đầy đủ** ngăn cách state cho các local/anonymous classes, initializer, pattern switch và mọi dạng statement mới. Vì vậy không trình bày nó như một static analyzer hoàn chỉnh cho toàn bộ ngữ pháp Java 21+.

## 13. `try`, `catch`, `finally` và luồng bất thường

Trong source Java:

```java
static int find(boolean fail) {
    try {
        if (fail) return 1;
        throw new IllegalStateException("problem");
    } catch (IllegalStateException ex) {
        return 2;
    } finally {
        System.out.println("cleanup");
    }
}
```

Đây là một phương thức Java hợp lệ nhưng **không thuộc source `Sample` trong ví dụ chính**. Phân tích đúng cần phân biệt:

- `try` là vùng được bảo vệ.
- `catch` chỉ tiếp nhận exception phù hợp.
- `finally` thông thường được thực thi khi rời `try`/`catch` theo cả đường bình thường và nhiều đường hoàn thành đột ngột, trừ các tình huống dừng/không hoàn thành mà runtime không có cơ hội thực hiện.
- `return 1` hoặc `return 2` thuộc phương thức `find`, nhưng trước khi hoàn tất return, `finally` có thể thực thi.
- Nếu chính `finally` ném exception hoặc kết thúc đột ngột, nó có thể thay đổi lý do hoàn thành ban đầu.

**Ví dụ:** in `RETURN -> METHOD:find` khi thấy một `ReturnTree` trong AST là đúng **đích cú pháp** của câu lệnh. Nhưng sẽ sai nếu kết luận “mỗi khi gặp return thì method ngay lập tức trả về, bỏ qua finally”.

### `try-with-resources`

`try (resource) { ... }` còn có logic đóng tài nguyên, kể cả suppressed exceptions. Nếu mục tiêu là CFG, analyzer phải biểu diễn các đường close/exception phù hợp; AST đơn thuần không tự bung đầy đủ những đường thực thi implicit đó.

Cách mở rộng visitor:

```java
@Override
public Void visitCatch(CatchTree tree, Void p) {
    return inside("CATCH", "",
            () -> super.visitCatch(tree, p));
}
```

Snippet này nằm **trong lớp `ContextScanner`** đã có helper `inside`; chưa tự phân biệt kiểu exception. Khi muốn gắn `FINALLY` riêng, cần override `visitTry` và quét `getResources()`, `getBlock()`, `getCatches()`, `getFinallyBlock()` dưới các frame thích hợp **một lần mỗi child**, không gọi `super.visitTry` rồi scan thêm finally lần nữa.

Ngoài ra, **lệnh gọi phương thức** trong try có thể ném exception mà AST không có `ThrowTree` trực tiếp, nên CFG cần thông tin method/exception semantics tương ứng.

## 14. Biểu thức điều kiện cũng là control-flow

Đừng chỉ tìm câu lệnh `if` và `switch`. Java có các biểu thức làm thay đổi việc phần con có được đánh giá hay không:

- `a && b`: khi `a` false, `b` không được đánh giá.
- `a || b`: khi `a` true, `b` không được đánh giá.
- `condition ? thenExpr : elseExpr`: chọn một trong hai expression.
- `switch` expression: một trong các nhánh trả giá trị.
- Lambda: body có thể **chưa chạy** ở thời điểm biểu thức lambda được tạo.
- Method call có exception: đường thực thi có thể kết thúc đột ngột.

Ví dụ:

```java
if (value != null && value.length() > 3) {
    use(value);
}
```

Đây là snippet, `value`/`use` cần được khai báo ở chương trình cụ thể. AST sẽ chứa `BinaryTree` (AND) với cả hai operand, nhưng **không có nghĩa `value.length()` luôn chạy**. Nếu dựng CFG cần cạnh short-circuit và sự thật `value != null` trong nhánh vế phải để suy luận an toàn dereference.

Đối với toán tử ba ngôi:

```java
int result = ok ? left() : right();
```

Cả `left()` và `right()` nằm trong AST, nhưng chỉ nhánh được chọn mới được đánh giá lúc runtime. Một visitor muốn giữ ngữ cảnh nên override `visitConditionalExpression` và quét riêng `getCondition()`, `getTrueExpression()`, `getFalseExpression()` dưới frame tương ứng.

**Một lần nữa:** duyệt AST **không phải** mô phỏng mọi đường đi runtime. Để phân tích nullness, definite assignment, resource lifecycle hay reachability, cần **path conditions và data-flow** hoặc một CFG chính xác hơn.

## 15. Không nhầm AST walker với CFG/data-flow engine

Một công cụ có thể đi qua tất cả node rất chính xác nhưng vẫn không biết các câu lệnh nào sẽ chạy trong một input cụ thể.

```java
int f(int x) {
    if (x > 0) {
        return x;
    }
    return -x;
}
```

Đây là phương thức minh họa, không phải program độc lập. `TreePathScanner` sẽ thấy **hai `ReturnTree`**. Điều đó không có nghĩa một lần gọi `f(1)` sẽ thực thi cả hai return. Một CFG sẽ biểu diễn nhánh điều kiện và hai đường hoàn tất khác nhau.

| Nhu cầu | AST + stack ngữ cảnh đủ dùng? | Khi nào cần thêm? |
| --- | --- | --- |
| Liệt kê `break`, `continue`, `yield` nằm trong method/loop/case nào | Thường có, nếu xử lý đầy đủ syntax và scope | Với target phức tạp, cần thêm semantic checks |
| Phân loại `if` then/else của một statement | Có | Nếu cần điều kiện khả thi, phải phân tích path condition |
| Xác định `return` thuộc lambda hay method | Có với scope frame đúng | Với class/initializer/phân tích tổng quát cần đầy đủ boundary |
| Đếm cú pháp `for`/`while`/`switch` | Có | Không có nghĩa đếm số lần chạy runtime |
| Chứng minh câu lệnh unreachable | **Không chỉ từ scan AST** | Kiểm tra các đường đi/abrupt completion hoặc CFG |
| Tính biến `x` có luôn được gán trước khi dùng | Không | Definite-assignment/data-flow analysis |
| Tìm đường exception tới `catch/finally` | Không đầy đủ | Exception-flow graph, method effects |
| Tìm resource leak trên mọi path | Không | CFG + resource state analysis |
| Phát hiện untrusted data tới SQL sink | Không | Interprocedural taint/data-flow analysis |

Một thiết kế phân tích nghiêm túc thường gồm:

1. Parse source và nhận AST.
2. Validate syntax/semantic với compiler theo `--release`/toolchain phù hợp.
3. Gắn parent scope, symbols và source positions.
4. Dựng representation của **basic blocks** và các **cạnh** if/else/loop/break/continue/return/throw/yield.
5. Xử lý exceptional edges, `finally` và short-circuit.
6. Chạy thuật toán data-flow tới fixpoint trên các vòng lặp, lưu điều kiện/nội dung cần thiết.
7. Báo kết quả bằng location và lý do, không nhầm “xuất hiện trong AST” với “sẽ thực thi”.

**Phần 4–6 vượt quá ví dụ AST scanner ở bài này.** Việc mô tả đúng giới hạn của công cụ quan trọng ngang với việc in đúng context cho những case mà công cụ đã hỗ trợ.

## 16. Gắn kết quả với vị trí mã nguồn

Khi làm linter hay IDE plugin, chỉ in `METHOD > IF_THEN > CASE` chưa đủ; người đọc cần biết **file và dòng/cột**.

Java Compiler API cung cấp `Trees` và `SourcePositions` để tra offset trong source. Mẫu sử dụng trong một visitor có `CompilationUnitTree unit` và `Tree tree`:

```java
Trees trees = Trees.instance(task);
SourcePositions positions = trees.getSourcePositions();

long offset = positions.getStartPosition(unit, tree);
if (offset >= 0 && unit.getLineMap() != null) {
    long line = unit.getLineMap().getLineNumber(offset);
    long column = unit.getLineMap().getColumnNumber(offset);
    System.out.println(line + ":" + column);
}
```

Đây là **đoạn minh họa tích hợp**, cần import `com.sun.source.util.Trees`, `com.sun.source.util.SourcePositions` và có `task`/`unit`/`tree` đúng scope. `getStartPosition(...)` có thể trả giá trị âm khi vị trí không xác định, nên phải kiểm tra trước khi chuyển thành dòng/cột. Với nhiều source files, luôn dùng **compilation unit chứa node đó**, không dùng LineMap của một file khác.

Nếu cần biết declaration/symbol thay vì chỉ syntax, `Trees.getElement(TreePath)` có thể cung cấp thông tin semantic khi compiler đã analyze phù hợp; một số node không có element tương ứng. Không suy đoán mục tiêu label từ chuỗi `tree.toString()` khi có API và ngữ cảnh rõ ràng hơn.

## 17. Kiểm thử scanner theo cấu trúc chứ không chỉ theo số dòng

Bộ kiểm thử tốt cần bao gồm cả ngữ cảnh lồng nhau và ngữ cảnh **không được thừa hưởng**:

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| `for` chứa `if`, `switch statement` và `break outer` | Target là `LABEL:outer`, không phải `SWITCH_STMT` |
| `continue outer` ở `else` | Target là `LABEL:outer` và context có `IF_ELSE` |
| `return switch(...)` | `ReturnTree` gắn METHOD; `YieldTree` gắn SWITCH_EXPR |
| Lambda trong phương thức | `return` của lambda gắn LAMBDA, không gắn METHOD bên ngoài |
| Nhiều vòng lặp lồng nhau | `continue;` và `break;` không nhãn nhắm đúng vòng/statement gần nhất |
| Labeled block | `break label` hợp lệ; `continue label` không hợp lệ nếu không phải loop |
| `else if` | AST thể hiện `IfTree` nằm trong nhánh else của `IfTree` ngoài |
| `if` không có else | Không dereference `getElseStatement()==null` |
| `switch expression` có `yield` lồng | `yield` target là switch expression gần nhất hợp lệ |
| Method trong local/anonymous class | Không nhầm loop/label của method outer |
| `try`/`catch`/`finally` | Xem xét cleanup và abrupt completion, không coi return là kết thúc ngay |
| `&&` và `||` | Không coi cả hai operand luôn được đánh giá |
| Input có lỗi cú pháp/semantic | Báo diagnostic thay vì cho rằng AST trả về luôn hợp lệ |
| Class dùng feature của JDK mới | Chọn `--release` phù hợp, không áp luật cú pháp của JDK cũ lên feature mới |

### Bảo toàn stack qua mọi đường thoát

Một sai lầm dễ phát sinh khi analyzer đang thử nghiệm:

```java
frames.push(new Frame("LOOP", ""));
scan(tree.getStatement(), p);
frames.pop();
```

Nếu `scan(...)` ném ngoại lệ, `pop()` không được chạy, khiến frame `LOOP` có thể “rò” sang node tiếp theo nếu công cụ bắt exception ở cấp ngoài rồi tiếp tục. Dùng `try/finally` như helper trong chương trình hoàn chỉnh để giữ bất biến của stack.

Cần nhớ rằng **stack mutable trong demo không được chia sẻ đồng thời** giữa nhiều lượt quét trên nhiều thread. Nếu muốn phân tích song song nhiều compilation unit, dùng scanner/context **riêng cho từng task** hoặc thiết kế đồng bộ/truyền state phù hợp.

## 18. Lỗi thường gặp khi phân tích lồng nhau

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Duyệt text thay vì parser | Nhầm brace, else, case, lambda, comment | Dùng Java Compiler Tree API |
| Chỉ có biến `insideLoop = true` | Mất độ sâu và loại loop | Stack frame theo từng scope |
| Push frame nhưng quên pop | Context chảy sang sibling/node khác | `try/finally` |
| Tự `scan` child rồi lại gọi `super.visitIf` | Phân tích trùng node | Chỉ chọn **một** cách duyệt mỗi child |
| Coi mọi `break` nằm trong switch đều thoát switch | `break label` có thể thoát cấu trúc ngoài | Resolve label theo scope |
| Cho `continue label` nhắm labeled block | Không đúng quy tắc Java | Kiểm tra nhãn gắn iteration statement |
| Xem `return` trong lambda là return của method | Nhầm thực thể thực thi | Dùng ranh giới `LAMBDA` |
| Xem `yield` là `return` | Nhầm kết thúc switch expression với method | Phân biệt `YieldTree` và `ReturnTree` |
| Gộp `SwitchTree` và `SwitchExpressionTree` | Sai luật `break`/`yield` | Dùng đúng loại node |
| Coi thứ tự visitor là thứ tự runtime | `RETURN` có thể được in trước `YIELD` | Chỉ coi là DFS AST traversal |
| Không xét `finally` | Báo sai đường trả về/exception | Thêm exception-flow nếu cần |
| Bỏ qua `&&`, `||`, `?:` | Báo sai tính khả thi/side effect | Mô hình short-circuit |
| Dùng `tree.toString()` làm vị trí nguồn | Sai file/dòng, dễ lệ thuộc format | `SourcePositions` + LineMap |
| Bỏ qua diagnostics | Phân tích source sai hoặc thiếu type | `JavacTask.analyze()`/`DiagnosticCollector` |
| Coi scanner demo là CFG đầy đủ | Kết luận sai reachability và data-flow | Dựng CFG và phân tích luồng riêng |
| Dùng compiler internals không ổn định | Khó nâng cấp JDK | Ưu tiên public `com.sun.source.*` API |

## 19. Bài tập và đáp án

**Bài 1.** Trong ví dụ chính, `break outer` nằm ở `switch statement`. Vì sao không báo target `SWITCH_STMT`?

**Đáp án:** `break` **có nhãn**. Đích là `LabeledStatementTree` mang tên `outer`, không phải statement breakable gần nhất. `SWITCH_STMT` vẫn nằm trong **context path** nhưng không phải jump target.

**Bài 2.** Đổi `break outer` thành `break;` ở cùng chỗ trong source. Target cần thay đổi thế nào?

**Đáp án:** `break;` không nhãn sẽ kết thúc `switch statement` gần nhất, vì nó nằm bên trong `switch (i)`. Scanner cần trả `SWITCH_STMT` (giả sử source còn hợp lệ và không thay đổi những điều kiện khác).

**Bài 3.** Tại sao hai `yield` trong `return switch (...)` không phải là hai `return` của phương thức?

**Đáp án:** `yield` tạo giá trị cho `switch expression`. `return` nằm ngoài switch expression mới chuyển giá trị cho phương thức. Chỉ một nhánh phù hợp thực thi lúc runtime; AST scanner duyệt cả hai `yield` trên source.

**Bài 4.** Vì sao `IF_ELSE > IF_THEN` có thể là context hợp lệ?

**Đáp án:** Trong cấu trúc `else if`, một `IfTree` nằm trong nhánh `else` của `IfTree` ngoài; nhánh `then` của `if` trong có context lồng `IF_ELSE > IF_THEN`.

**Bài 5.** Nếu `scan(tree.getThenStatement(), p)` hoàn tất rồi scanner tiếp tục xử lý `else`, nhưng frame `IF_THEN` vẫn nằm trong stack, điều gì sai?

**Đáp án:** Nhánh `else` sẽ bị báo là nằm trong `then`, làm sai điều kiện đường đi. Phải pop frame sau khi quét mỗi nhánh, tốt nhất qua `try/finally`.

**Bài 6.** Đối với `return n -> { return n + 1; };` trong một method, có mấy đích return?

**Đáp án:** Hai thực thể thực thi khác nhau: return bên ngoài kết thúc phương thức, còn return trong lambda chỉ kết thúc lần gọi lambda.

**Bài 7.** Nếu chương trình in `RETURN` trước `YIELD`, có thể kết luận runtime chạy return trước yield không?

**Đáp án:** Không. Visitor thấy node ngoài `ReturnTree` trước expression con `SwitchExpressionTree` trong quá trình quét AST. Thứ tự đánh giá runtime là chuyện khác.

**Bài 8.** Muốn chứng minh một biến có giá trị khác null trên mọi đường dẫn tới một method call thì chỉ `TreePathScanner` có đủ không?

**Đáp án:** Không. Cần xử lý điều kiện rẽ nhánh, short-circuit, loops, exceptions và data-flow/path conditions; thông tin AST nesting chỉ là đầu vào.

**Bài 9.** Có nên áp dụng `continue label;` với nhãn một block thường không?

**Đáp án:** Không. Java chỉ cho `continue label` hướng tới iteration statement hợp lệ; `break label` mới có thể thoát một labeled statement như block.

**Bài 10.** Khi cần tạo linter báo đúng dòng chứa `break`, nên dùng gì?

**Đáp án:** Dùng `getCurrentPath()` để biết node, `Trees.getSourcePositions()` để lấy offset và `CompilationUnitTree.getLineMap()` để chuyển thành dòng/cột; kiểm tra giá trị vị trí không xác định.

## 20. Checklist khi viết công cụ phân tích

Trước khi kết luận một phân tích ngữ cảnh điều khiển là đúng, tự kiểm tra:

1. Đã parse source bằng parser đúng phiên bản Java cần hỗ trợ chưa?
2. Đã tách **AST nesting** khỏi **runtime control-flow** chưa?
3. Đã giữ `TreePath` và stack context riêng, có push/pop trong `finally` chưa?
4. Với `if`, có phân biệt condition/then/else và tránh scan trùng child không?
5. Với `for/while/do/enhanced for`, có giữ đúng loop scope và pha thực thi khi cần không?
6. Với labeled break/continue, có resolve nhãn theo **scope hợp lệ** và phân biệt đích loop/block không?
7. Với `switch statement`/`switch expression`, có phân biệt `break` và `yield` không?
8. Với lambda/method/class/initializer, có tránh non-local jump target sai không?
9. Với `return`/`throw`, có xét `finally` nếu đang khẳng định thứ tự/khả năng hoàn tất runtime không?
10. Với `&&`/`||`/`?:`, có mô hình short-circuit nếu cần data-flow không?
11. Đã xử lý diagnostics từ compiler và kiểm tra source positions hợp lệ chưa?
12. Test đã gồm các nhánh lồng nhau và trường hợp **không được** kế thừa context chưa?
13. Có giới hạn rõ rằng thuật toán hiện tại chỉ làm **AST analysis**, không phải CFG/data-flow hoàn chỉnh không?

**Ghi nhớ:** phân tích cú pháp Java lồng nhau cần **cả đường dẫn AST và ngăn xếp ngữ cảnh điều khiển**. `TreePathScanner` cho phép duyệt đúng cấu trúc source; frame stack giúp xác định câu lệnh thuộc nhánh, vòng lặp, nhãn, lambda và `switch` nào. `break`, `continue`, `return` và `yield` có **đích ngữ nghĩa khác nhau**. Để nói về đường chạy thật, tính khả thi hoặc tính đúng của dữ liệu, phải xây thêm **CFG/exception-flow/data-flow** thay vì suy luận từ thứ tự visitor.

### Tài liệu tham khảo chính thức còn áp dụng

- [Java SE 21 — TreePathScanner](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/util/TreePathScanner.html)
- [Java SE 21 — TreePath](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/util/TreePath.html)
- [Java SE 21 — Java Compiler Tree interfaces](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/tree/package-summary.html)
- [Java SE 21 — JavacTask](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/util/JavacTask.html)
- [Java SE 21 — Trees, SourcePositions](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/util/Trees.html)
- [Java Language Specification, Chapter 14 — Control statements and abrupt completion](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html)
- [JEP 361 — Switch Expressions, final in JDK 14](https://openjdk.org/jeps/361)

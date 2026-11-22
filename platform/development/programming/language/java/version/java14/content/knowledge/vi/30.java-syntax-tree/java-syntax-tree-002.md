# YieldTree cho câu lệnh tạo kết quả nhánh trong cây cú pháp Java

## Mục tiêu

Khi viết công cụ phân tích mã nguồn Java (linter, code analyzer, plugin IDE, refactoring tool hoặc công cụ kiểm tra quy tắc dự án), bạn không nên chỉ tìm chuỗi `yield` trong source. Trình biên dịch Java biểu diễn mã nguồn thành **cây cú pháp trừu tượng** (Abstract Syntax Tree, AST), trong đó một câu lệnh **`yield expression;`** có nút riêng mang tên **`com.sun.source.tree.YieldTree`**.

`YieldTree` biểu diễn **một câu lệnh chuyển giá trị về cho biểu thức `switch` bao quanh**, khác với:

- Nhánh `case X -> expression`, nơi expression trực tiếp là kết quả, **không có câu lệnh `yield` tường minh**.
- `return expression;`, trả kết quả từ method/lambda phù hợp, **không phải** kết quả của switch expression.
- `break;` trong switch statement, kết thúc luồng điều khiển của một statement.
- Lời gọi `Thread.yield()`, nhường CPU cho scheduler, **không liên quan** tới switch expression và `YieldTree`.

**Mốc Java 14:** Switch expressions trở thành tính năng chính thức trong **Java 14** theo **JEP 361**, và `yield` là câu lệnh trả giá trị từ switch expression. `YieldTree` và `Tree.Kind.YIELD` thuộc **Compiler Tree API** của JDK, dùng trong các công cụ phân tích cú pháp hiện hành. Không cần `--enable-preview` khi biên dịch code dùng switch expressions trên Java 17+.

Sau bài học, bạn có thể:

1. Nhận biết chính xác chỗ một câu lệnh `yield` xuất hiện trong code Java và trong AST.
2. Hiểu `YieldTree extends StatementTree`, `getKind() == Tree.Kind.YIELD`, `getValue()` trả `ExpressionTree`.
3. Phân biệt `YieldTree`, `SwitchExpressionTree`, `SwitchTree`, `CaseTree` và `BlockTree`.
4. Dùng `TreePathScanner.visitYield(...)` để lấy từng node cùng đường dẫn các nút cha.
5. Tìm **switch expression gần nhất** là đối tượng nhận giá trị của một `yield`, kể cả khi có switch expression lồng nhau.
6. Xác định **dòng mã nguồn** của `yield` bằng `Trees.getSourcePositions()` và `CompilationUnitTree.getLineMap()`.
7. Hiểu vì sao **đếm YieldTree không đồng nghĩa đếm số nhánh tạo giá trị** và vì sao `parse()` chưa đủ để xác nhận mọi lỗi ngữ nghĩa.
8. Biên dịch và chạy một ví dụ **Java 17+** gồm chương trình `switch` thật và trình quét AST có stdout đã kiểm chứng.

Bài tập trung vào các API **vẫn được hỗ trợ trên JDK hiện đại**. Không dùng cú pháp preview cũ `break value`, không gọi các lớp cài đặt nội bộ như `com.sun.tools.javac.tree.JCTree` để làm công cụ portable, và không giả định mọi biểu thức trong switch đều là `YieldTree`.

## 1. Nhắc lại: switch expression tạo kết quả như thế nào?

Một `switch` có thể là **statement** hoặc **expression**.

### 1.1. Switch statement

~~~java
// Đoạn minh họa nằm trong một method.
switch (status) {
    case 0 -> System.out.println("new");
    default -> System.out.println("other");
}
~~~

`switch` trên thực thi hành động. Bản thân nó **không được dùng như biểu thức có giá trị**. Trong Compiler Tree API, loại cú pháp này được biểu diễn bằng **`SwitchTree`**; node kind là `Tree.Kind.SWITCH`.

### 1.2. Switch expression

~~~java
// Đoạn minh họa nằm trong một method.
int fee = switch (level) {
    case 0 -> 10;
    case 1 -> 20;
    default -> 30;
};
~~~

Đây là **một biểu thức** tạo giá trị kiểu `int`. AST chứa **`SwitchExpressionTree`** với kind `Tree.Kind.SWITCH_EXPRESSION`.

**Điểm cốt lõi:** Với `case 0 -> 10;`, biểu thức `10` ở ngay bên phải mũi tên đã là kết quả của nhánh. Trong source không có `yield`, vì vậy parser **không tạo `YieldTree` cho nhánh này**. Nếu công cụ chỉ quét `YieldTree` để tìm mọi kết quả switch, công cụ sẽ bỏ sót kiểu nhánh này.

### 1.3. Khi dùng block cần yield tường minh

~~~java
// Đoạn minh họa nằm trong một method.
int fee = switch (level) {
    case 0 -> 10;
    case 1 -> {
        int base = 20;
        yield base + 1;
    }
    default -> throw new IllegalArgumentException("unknown level");
};
~~~

Nhánh `case 1` có nhiều statements. Trong block đó, `yield base + 1;` **trả giá trị của switch expression**. Đây chính là node **`YieldTree`** trong AST.

Nhánh `default -> throw ...` hoàn tất bằng ngoại lệ, **không yêu cầu thêm một câu lệnh `yield`**.

### 1.4. Cú pháp dấu hai chấm vẫn hợp lệ

~~~java
// Đoạn minh họa nằm trong một method.
int fee = switch (level) {
    case 0:
        yield 10;
    case 1:
        yield 20;
    default:
        yield 30;
};
~~~

Đây là **switch expression** dùng *switch-labeled statement groups*, không phải switch statement. Cú pháp dấu hai chấm **vẫn được Java hỗ trợ**, dù nhiều codebase hiện nay ưu tiên dạng `->` vì hạn chế nguy cơ fall-through và dễ đọc hơn.

**Không trộn** nhánh `case X -> ...` và `case Y: ...` **trong cùng một switch block**. Hai ví dụ trên là các biểu thức switch khác nhau và có quy tắc cấu trúc khác nhau.

## 2. YieldTree là gì?

Theo `jdk.compiler/com.sun.source.tree.YieldTree`:

~~~java
public interface YieldTree extends StatementTree {
    ExpressionTree getValue();
}
~~~

Đây là dạng **chữ ký API rút gọn** để học cấu trúc; source của JDK còn có inherited methods từ `Tree` như `getKind()` và `accept(...)`.

| Thành phần | Kiểu/giá trị | Ý nghĩa |
|---|---|---|
| `YieldTree` | Interface AST | Một node biểu diễn câu lệnh `yield expression;` |
| `StatementTree` | Superinterface | `yield` là **statement**, dù nó cung cấp một giá trị |
| `Tree.Kind.YIELD` | Kind của node | Nhận diện tường minh yield statement |
| `getValue()` | `ExpressionTree` | Biểu thức được viết sau `yield` |
| `TreeVisitor.visitYield(...)` | Phương thức visitor | Tiếp nhận node yield trong bộ duyệt AST |
| `TreeScanner.visitYield(...)` | Hook đệ quy | Truy cập mọi yield node trong cây nguồn |
| `TreePathScanner.visitYield(...)` | Hook có đường dẫn cha | Truy cập yield và tìm switch expression sở hữu |
| `SourcePositions` | API vị trí nguồn | Xác định offset node trong file, không phải giá trị tính toán |

### 2.1. Kiểu trả về của getValue rất quan trọng

Với đoạn:

~~~java
yield base + 1;
~~~

Cấu trúc khái niệm của AST:

~~~text
YieldTree                       (kind: YIELD)
  getValue() -> ExpressionTree  (kind: PLUS)
      IdentifierTree            (base)
      LiteralTree               (1)
~~~

`getValue()` **không trả về giá trị số đã được tính**. Nó trả về **cây cú pháp biểu thức**. Vì vậy bạn có thể đọc `getValue().getKind()` là `PLUS` và truy tiếp các node con, nhưng không thể suy ra `base + 1` bằng bao nhiêu nếu chưa có thông tin semantic và giá trị của `base`.

Tương tự, với `yield calculate(n);`, `getValue()` là một `MethodInvocationTree`, **không phải kết quả trả về khi phương thức chạy**.

### 2.2. YieldTree không phải ExpressionTree

Dù `yield` có “trả giá trị” cho switch expression, cấu trúc ngữ pháp của nó vẫn là:

~~~text
yield Expression ;
~~~

Vì vậy:

- `YieldTree` **extends `StatementTree`**, không extends `ExpressionTree`.
- Phần **`Expression` nằm bên trong** được lấy bằng `getValue()`.
- Một switch expression hoàn chỉnh là **`SwitchExpressionTree extends ExpressionTree`**.
- Một switch statement là **`SwitchTree extends StatementTree`**.

Nhầm `YieldTree` thành expression tree có thể khiến code visitor/transformer bỏ qua hoặc xử lý sai node con.

### 2.3. yield không phải return hoặc break

| Câu lệnh | Node AST | Mục tiêu điều khiển |
|---|---|---|
| `yield expression;` | `YieldTree` | Switch expression gần nhất phù hợp |
| `return expression;` | `ReturnTree` | Method/lambda return target |
| `break;` | `BreakTree` | Loop hoặc switch statement phù hợp |
| `throw expression;` | `ThrowTree` | Chuyển điều khiển bằng ngoại lệ |
| `Thread.yield();` | `MethodInvocationTree` trong một expression statement | Gọi API scheduler, không liên quan switch |

Câu lệnh `yield` **không thể** dùng để trở thành kết quả của một **switch statement đứng riêng**. Ngược lại, trong một switch expression, `break` không thay thế được `yield` để cung cấp kết quả.

Có những giới hạn điều khiển khác theo Java Language Specification: `yield` không thể vượt qua ranh giới method/constructor/initializer/lambda để “trở về” switch expression nằm ở ngoài. Nó chuyển điều khiển đến **switch expression gần nhất theo quy tắc ngữ pháp**, không phải bất kỳ switch nào nhìn thấy trong file.

## 3. Những nút cây liên quan

| Node/API | Dùng để làm gì? | Điểm phân biệt |
|---|---|---|
| `CompilationUnitTree` | Đại diện một file đơn vị biên dịch Java | Gốc quét AST của file |
| `MethodTree` | Method/constructor declaration | Có thể chứa nhiều switch |
| `SwitchExpressionTree` | Một switch **tạo giá trị** | `getExpression()` là selector; `getCases()` trả các case |
| `SwitchTree` | Một switch **statement** | Có cases nhưng không là expression có giá trị |
| `CaseTree` | Một nhánh/cụm nhánh `case` hoặc `default` | `getCaseKind()` phân biệt RULE và STATEMENT |
| `BlockTree` | Khối lệnh `{ ... }` | Có thể chứa local variable, if và YieldTree |
| `YieldTree` | Câu lệnh `yield value;` | `getValue()` là AST biểu thức |
| `ExpressionTree` | Biểu thức của nhánh hoặc của yield | Có thể là literal, binary, invocation, switch expression khác |
| `TreePath` | Một chuỗi node từ root đến node hiện tại | Dùng để tìm các nút cha thực tế |
| `LineMap` | Đổi offset sang dòng/cột source | Hữu ích báo vị trí lint |

### 3.1. Dùng CaseTree để không bỏ sót kết quả

Trong API Java 17+, `CaseTree.CaseKind` có hai giá trị cơ bản:

- `RULE`: dạng `case X -> body`; `caseTree.getBody()` trả node sau mũi tên, có thể là **ExpressionTree**, **BlockTree** hoặc **ThrowTree**.
- `STATEMENT`: dạng `case X: statements`; `caseTree.getStatements()` trả các statements của cụm case.

Nếu bạn viết một linter “mọi nhánh phải tạo giá trị”:

- Với **RULE + expression body**: đó là một biểu thức kết quả **không đi qua YieldTree**.
- Với **RULE + block body**: có thể có một hoặc nhiều câu lệnh `yield` trên các luồng điều khiển, hoặc có đường chỉ `throw`.
- Với **STATEMENT group** trong switch expression: thường dùng `yield` hoặc `throw` để hoàn tất đúng.
- Với **switch statement**: nó không có requirement “trả về giá trị” như switch expression.

Đừng chỉ đếm `YieldTree` để quyết định tính exhaustive hoặc control flow chính xác của cả switch expression. Một phân tích thực sự cần kiểm tra cấu trúc và **các đường đi điều khiển**; `javac` đã có những luật ngữ nghĩa tương ứng.

### 3.2. Chú ý API theo phiên bản

Từ Java 14, `CaseTree.getCaseKind()`, `getBody()` và `getExpressions()` là những API phù hợp để xử lý hai dạng case. `CaseTree.getExpression()` là một getter cũ đã được đánh dấu deprecated trong các JDK mới; không xây mới code dựa vào nó nếu có lựa chọn tốt hơn.

Từ Java 21, `CaseTree.getLabels()` giúp mô hình hóa case labels hiện đại hơn, gồm patterns và default label. Nếu công cụ phải chạy trên Java 17, đừng dùng những API mới hơn baseline; nếu phân tích cú pháp Java 21+, hãy đọc Javadoc của **JDK đang chạy** để xử lý patterns và guards đúng.

## 4. Hình dung AST của một switch expression

Với:

~~~java
int total = switch (kind) {
    case 0 -> 10;
    case 1 -> {
        int base = 20;
        yield base + 1;
    }
    default -> throw new IllegalArgumentException();
};
~~~

Hình dung cấu trúc:

~~~text
VariableTree: total
  initializer -> SwitchExpressionTree (SWITCH_EXPRESSION)
    selector -> IdentifierTree: kind
    cases:
      CaseTree (RULE, case 0)
        body -> LiteralTree: 10
               [KHÔNG có YieldTree]
      CaseTree (RULE, case 1)
        body -> BlockTree
          VariableTree: base = 20
          YieldTree (YIELD)
            getValue() -> BinaryTree (PLUS)
      CaseTree (RULE, default)
        body -> ThrowTree
               [KHÔNG có YieldTree]
~~~

Sơ đồ mang tính khái niệm, không phải output đã in của trình biên dịch. Nó minh họa vì sao một analyzer chỉ xử lý `YieldTree` sẽ **không thấy expression-only case** và **không coi throw là một giá trị**.

Với switch expression **lồng nhau**, mỗi `yield` thuộc về **switch expression gần nhất hợp lệ**. Vì vậy khi báo lỗi hoặc liên kết một biểu thức tạo kết quả với switch, phải xét **đường dẫn node cha** chứ không lấy switch đầu tiên trong file.

## 5. Cách sử dụng TreePathScanner.visitYield

`TreePathScanner<R,P>` nằm trong `com.sun.source.util`, thuộc module `jdk.compiler`. Đây là một visitor quét các node đồng thời duy trì **TreePath** của node hiện tại.

Để phát hiện một yield:

~~~java
// Đoạn nằm trong lớp visitor, không phải chương trình độc lập.
@Override
public Void visitYield(YieldTree node, Void ignored) {
    ExpressionTree value = node.getValue();
    System.out.println("kind=" + node.getKind());       // YIELD
    System.out.println("valueKind=" + value.getKind()); // Tùy expression
    return super.visitYield(node, ignored);
}
~~~

**Vì sao gọi `super.visitYield`?** Để visitor tiếp tục duyệt biểu thức con `getValue()`. Nếu biểu thức kết quả chứa một switch expression **lồng nhau**, bỏ lời gọi `super` có thể khiến công cụ không thấy các `yield` sâu hơn.

Nếu bạn chủ động chỉ muốn phát hiện các `yield` cấp hiện tại và không quét children, có thể chọn chiến lược khác. Nhưng phải viết rõ phạm vi, không đếm thiếu mà tưởng kết quả đã bao phủ toàn cây.

### 5.1. Lấy switch expression sở hữu yield

Trong `visitYield`, `getCurrentPath()` là đường dẫn tới yield node hiện tại. Có thể đi ngược:

~~~java
// Đoạn minh họa trong visitYield.
TreePath owner = getCurrentPath().getParentPath();

while (owner != null
        && owner.getLeaf().getKind() != Tree.Kind.SWITCH_EXPRESSION) {
    owner = owner.getParentPath();
}

// owner chứa switch expression gần nhất, nếu tồn tại.
~~~

Đây là thao tác tìm kiếm **đường dẫn AST gần nhất**, không phải tự xây lại control-flow graph. Với source hợp lệ có yield statement, JLS xác định mục tiêu switch expression của nó. Với source sai ngữ nghĩa, cây có thể vẫn được tạo ở pha parse; đừng khẳng định tìm thấy switch expression là code chắc chắn biên dịch.

### 5.2. Lấy vị trí nguồn

`Trees.getSourcePositions()` cung cấp vị trí bắt đầu/kết thúc của các node; `CompilationUnitTree.getLineMap()` đổi offset thành số dòng/cột:

~~~java
// Đoạn minh họa trong visitor, với trees/unit đã lấy từ JavacTask.
SourcePositions positions = trees.getSourcePositions();

long offset = positions.getStartPosition(unit, node);
long line = unit.getLineMap().getLineNumber(offset);
~~~

- `offset` là vị trí trong đơn vị biên dịch, không phải “số dòng” tự thân.
- `line` là số dòng source, tính từ 1 khi có LineMap.
- Với node tổng hợp hoặc không có vị trí, API có thể trả `Diagnostic.NOPOS`; công cụ production nên xử lý thiếu vị trí.
- Nếu cần cắt **đúng nguyên văn source** để hiển thị, dùng start/end positions trên source text. `Tree.toString()` là biểu diễn do compiler tạo, **không bảo đảm giữ nguyên mọi whitespace/comment**.

## 6. Chương trình ví dụ 1: switch expressions và switch statement

Để kiểm thử cả runtime và AST, tạo file **`SwitchFixture.java`** như sau. Chương trình có:

- Một arrow expression branch **không có yield**.
- Một arrow **block** có `yield`.
- Một switch expression **lồng bên trong** switch expression khác.
- Các nhánh có `if` và nhiều đường `yield`.
- Một switch expression dạng **colon statements**.
- Một switch **statement** tách biệt, không tạo kết quả.

### 6.1. Toàn bộ SwitchFixture.java

~~~java
public final class SwitchFixture {
    public static int arrow(int n) {
        return switch (n) {
            case 0 -> 10;
            case 1 -> {
                int base = 20;
                yield base + 1;
            }
            case 3 -> {
                int inner = switch (n % 2) {
                    case 0 -> 200;
                    default -> {
                        yield 201;
                    }
                };
                yield inner + 3;
            }
            default -> {
                if (n < 0) {
                    yield -1;
                }
                yield n * 2;
            }
        };
    }

    public static int colon(int n) {
        return switch (n) {
            case 0:
                yield 100;
            case 1:
                yield 101;
            default:
                throw new IllegalArgumentException("unexpected: " + n);
        };
    }

    public static void statement(int n) {
        switch (n) {
            case 0 -> System.out.println("statement=zero");
            default -> System.out.println("statement=other");
        }
    }

    public static void main(String[] args) {
        System.out.println("arrow(0)=" + arrow(0));
        System.out.println("arrow(1)=" + arrow(1));
        System.out.println("arrow(3)=" + arrow(3));
        System.out.println("arrow(-2)=" + arrow(-2));
        System.out.println("colon(1)=" + colon(1));
        statement(0);
    }
}
~~~

Biên dịch/chạy bằng JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 SwitchFixture.java
java SwitchFixture
~~~

**Stdout đã kiểm chứng:**

~~~text
arrow(0)=10
arrow(1)=21
arrow(3)=204
arrow(-2)=-1
colon(1)=101
statement=zero
~~~

Giải thích:

1. `arrow(0)` lấy ngay giá trị `10` sau mũi tên, **không có yield statement**.
2. `arrow(1)` đi vào block, tạo `base=20` rồi `yield base + 1`, được `21`.
3. `arrow(3)` có inner switch expression: `3 % 2 = 1`, inner default `yield 201`; sau đó outer `yield inner + 3` tạo `204`. **Hai yield này có hai switch owners khác nhau**.
4. `arrow(-2)` qua `if (n < 0)`, thực hiện `yield -1`; câu `yield n * 2` phía sau không được chạy trong đường đó.
5. `colon(1)` thực hiện `yield 101` từ statement group; không cần `break` để tạo kết quả.
6. `statement(0)` chỉ in thông báo bằng một **SwitchTree**, không phải SwitchExpressionTree.

**Mỗi lần chạy chỉ chọn một nhánh**, nhưng AST vẫn chứa tất cả yield statements tường minh trong source. Do đó **số YieldTree trên source không phải số lệnh yield thực thi trong một lần chạy**.

## 7. Chương trình ví dụ 2: duyệt AST bằng Java Compiler API

Tạo tệp thứ hai **`YieldTreeInspector.java`** cùng thư mục với `SwitchFixture.java`. Đây là một chương trình Java độc lập để đọc **mã nguồn**, không chạy class đang được phân tích. Nó dùng:

- `ToolProvider.getSystemJavaCompiler()` và `StandardJavaFileManager` để chuẩn bị source file.
- `JavacTask.parse()` để nhận `CompilationUnitTree`.
- `TreePathScanner` để đếm switch expressions, switch statements và yield statements.
- `YieldTree.getValue()` để lấy loại AST của biểu thức kết quả.
- `TreePath` để tìm switch expression gần nhất.
- `SourcePositions` và `LineMap` để in dòng của yield và switch đích.

### 7.1. Toàn bộ YieldTreeInspector.java

~~~java
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.SwitchExpressionTree;
import com.sun.source.tree.SwitchTree;
import com.sun.source.tree.Tree;
import com.sun.source.tree.YieldTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.SourcePositions;
import com.sun.source.util.TreePath;
import com.sun.source.util.TreePathScanner;
import com.sun.source.util.Trees;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.util.List;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class YieldTreeInspector {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Pass one Java source path");
        }
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("A JDK is required");
        }
        try (StandardJavaFileManager manager = compiler.getStandardFileManager(
                null, null, StandardCharsets.UTF_8)) {
            Iterable<? extends JavaFileObject> files =
                    manager.getJavaFileObjects(new File(args[0]));
            JavacTask task = (JavacTask) compiler.getTask(
                    null, manager, null, List.of("-proc:none", "--release", "17"),
                    null, files);
            Trees trees = Trees.instance(task);
            SourcePositions positions = trees.getSourcePositions();

            for (CompilationUnitTree unit : task.parse()) {
                class Visitor extends TreePathScanner<Void, Void> {
                    int expressions;
                    int statements;
                    int yields;
                    @Override
                    public Void visitSwitchExpression(
                            SwitchExpressionTree node, Void ignored) {
                        expressions++;
                        return super.visitSwitchExpression(node, ignored);
                    }
                    @Override
                    public Void visitSwitch(SwitchTree node, Void ignored) {
                        statements++;
                        return super.visitSwitch(node, ignored);
                    }
                    @Override
                    public Void visitYield(YieldTree node, Void ignored) {
                        yields++;
                        TreePath owner = getCurrentPath().getParentPath();
                        while (owner != null
                                && owner.getLeaf().getKind() != Tree.Kind.SWITCH_EXPRESSION) {
                            owner = owner.getParentPath();
                        }
                        long yieldLine = unit.getLineMap().getLineNumber(
                                positions.getStartPosition(unit, node));
                        long switchLine = owner == null ? -1 :
                                unit.getLineMap().getLineNumber(
                                        positions.getStartPosition(unit, owner.getLeaf()));
                        System.out.println("yield#" + yields
                                + " line=" + yieldLine
                                + " valueKind=" + node.getValue().getKind()
                                + " value=" + node.getValue()
                                + " switchLine=" + switchLine);
                        return super.visitYield(node, ignored);
                    }
                }
                Visitor v = new Visitor();
                v.scan(unit, null);
                System.out.println("switchExpressions=" + v.expressions);
                System.out.println("switchStatements=" + v.statements);
                System.out.println("explicitYields=" + v.yields);
            }
        }
    }
}
~~~

### 7.2. Biên dịch và chạy inspector

Có thể biên dịch cả hai source trong một lần:

~~~bash
javac --release 17 -encoding UTF-8 \
  SwitchFixture.java YieldTreeInspector.java
~~~

Chạy inspector trên file nguồn:

~~~bash
java YieldTreeInspector SwitchFixture.java
~~~

**Kết quả đã được kiểm chứng khi biên dịch bằng `--release 17` và chạy JDK 24:**

~~~text
yield#1 line=7 valueKind=PLUS value=base + 1 switchLine=3
yield#2 line=13 valueKind=INT_LITERAL value=201 switchLine=10
yield#3 line=16 valueKind=PLUS value=inner + 3 switchLine=3
yield#4 line=20 valueKind=INT_LITERAL value=-1 switchLine=3
yield#5 line=22 valueKind=MULTIPLY value=n * 2 switchLine=3
yield#6 line=30 valueKind=INT_LITERAL value=100 switchLine=28
yield#7 line=32 valueKind=INT_LITERAL value=101 switchLine=28
switchExpressions=3
switchStatements=1
explicitYields=7
~~~

**Dấu hiệu quan trọng trong output:**

- Có **ba** `SwitchExpressionTree`: biểu thức ngoài của `arrow`, biểu thức lồng `switch (n % 2)`, và biểu thức của `colon`.
- Có **một** `SwitchTree`: method `statement` dùng switch để gọi `println`.
- Có **bảy** `YieldTree` tường minh. Nhánh `case 0 -> 10` **không tạo YieldTree**.
- `yield#2` ở dòng 13 thuộc **switch lồng nhau bắt đầu dòng 10**.
- `yield#3` ở dòng 16 thuộc **switch ngoài bắt đầu dòng 3**.
- Hai `yield` khác nhau có thể tạo những giá trị khác nhau tùy đường điều khiển, như nhánh `if` của default.

Trong output JDK dùng để test, `yield -1` được báo `valueKind=INT_LITERAL`. **Không suy từ cách in này rằng mọi literal số âm đều phải được biểu diễn bằng cùng một hình dạng nội bộ ở mọi compiler**, đặc biệt khi xét source được tạo tự động hoặc nhiều ngữ cảnh cú pháp; luôn kiểm tra AST thực tế.

Vị trí dòng và chuỗi `node.getValue().toString()` mang tính **biểu diễn từ source/compiler**. Nếu thay đổi số dòng, formatter hoặc bản JDK, cách in có thể thay đổi. Các thuộc tính quan trọng về mặt API là `Tree.Kind` và quan hệ node, không phải format của log.

### 7.3. Tại sao code này thực sự phát hiện yield đúng?

Từ `task.parse()`, mỗi `CompilationUnitTree` chứa AST của file đã parse. `v.scan(unit,null)` duyệt đệ quy các node, và khi gặp `YieldTree` gọi `visitYield`. Trong callback:

1. Tăng `yields`.
2. Lấy `getCurrentPath().getParentPath()`.
3. Đi lên cây đến `Tree.Kind.SWITCH_EXPRESSION` gần nhất.
4. Đọc vị trí bắt đầu của `YieldTree` và switch owner bằng `SourcePositions`.
5. Lấy loại cú pháp expression từ `node.getValue().getKind()`.
6. Gọi `super.visitYield(...)` để duyệt các node con.

**Không chỉ dùng switch đầu tiên của file** làm owner: source có thể có nhiều switch expressions, lồng sâu hoặc nằm ở các methods khác nhau.

### 7.4. Tại sao không “đánh giá” node.getValue?

Với `yield base + 1`, `getValue()` là cây toán tử `PLUS`. Inspector chỉ in syntax; nó **không chạy chương trình đang phân tích** và không biết biến `base` tại runtime.

Muốn suy luận kiểu biểu thức hoặc symbol, công cụ có thể yêu cầu pha **`analyze()`**, `Trees.getTypeMirror(TreePath)` và một ngữ cảnh compiler đầy đủ. Muốn suy luận control flow phức tạp hoặc constant propagation, cần phân tích thêm, không chỉ có `YieldTree.getValue()`.

Sử dụng `parse()` để tìm node cú pháp là mục đích của demo; nó **không bảo đảm source code chắc chắn hợp lệ về type/control-flow**. Một chương trình phân tích chất lượng production cần tiếp nhận diagnostics, xử lý parse errors và sử dụng các pha thích hợp của compiler.

## 8. Những tình huống YieldTree dễ gây hiểu nhầm

### 8.1. Arrow expression trực tiếp không có YieldTree

~~~java
// Đoạn minh họa.
int result = switch (x) {
    case 1 -> 100;
    default -> 200;
};
~~~

Có một `SwitchExpressionTree` và các `CaseTree` nhưng **không có `YieldTree`**. Đây vẫn là switch expression hợp lệ, tạo ra giá trị cho biến `result`.

Nếu mục tiêu của linter là thu thập **mọi result expression** của switch, phải lấy:

- Expression body của `case ... -> expression`.
- `YieldTree.getValue()` của những statements `yield` thực sự thuộc switch expression đó.

Không suy tổng số kết quả chỉ bằng `YieldTree`.

### 8.2. Arrow block cần yield hoặc throw trên đường đi phù hợp

~~~java
// CỐ Ý SAI: block có đường đi kết thúc bình thường mà không yield.
int result = switch (x) {
    case 1 -> {
        System.out.println("one");
        // Thiếu yield hoặc throw.
    }
    default -> 0;
};
~~~

`javac` từ chối vì switch expression phải có kết quả khi hoàn tất bình thường. Chỉ đặt `yield` trong một nhánh `if` mà vẫn còn đường chạy không trả giá trị cũng có thể không đạt yêu cầu.

Phiên bản sửa:

~~~java
// Đoạn minh họa.
int result = switch (x) {
    case 1 -> {
        System.out.println("one");
        yield 1;
    }
    default -> 0;
};
~~~

### 8.3. Không viết "case -> yield expression" trần

~~~java
// CỐ Ý SAI:
int result = switch (x) {
    case 1 -> yield 1;
    default -> 0;
};
~~~

Với arrow rule, `yield` là một **statement** chứ không phải expression được phép đặt trực tiếp sau mũi tên trong switch expression. Hãy dùng `case 1 -> 1;` hoặc block:

~~~java
int result = switch (x) {
    case 1 -> {
        yield 1;
    }
    default -> 0;
};
~~~

Mẫu này giúp linter phân biệt **expression body** và **block chứa YieldTree**.

### 8.4. Yield trong if nằm trong switch expression

~~~java
// Đoạn minh họa trong method.
int result = switch (x) {
    default -> {
        if (x < 0) {
            yield -1;
        }
        yield 1;
    }
};
~~~

Có **hai YieldTree** trong source nhưng một lần thực thi **chỉ đi qua một**. Nếu công cụ báo “số lần yield khi chạy”, chỉ đếm AST là sai; AST cho biết **vị trí khai báo của câu lệnh**, không phải tần suất thực thi.

### 8.5. Yield trong switch expression lồng nhau

~~~java
// Đoạn minh họa trong method.
int result = switch (x) {
    default -> {
        int inner = switch (x % 2) {
            default -> {
                yield 7;    // Thuộc inner switch expression.
            }
        };
        yield inner + 1;     // Thuộc outer switch expression.
    }
};
~~~

AST chứa hai `YieldTree` nhưng mỗi node gắn với **switch target khác nhau**. Đây là lý do dùng `TreePathScanner` đi lên đường dẫn parent thay vì gán mọi yield cho switch gần nhất về mặt **dòng văn bản**, vốn không đáng tin khi lồng nhau.

### 8.6. Thread.yield() không tạo YieldTree

~~~java
// Đoạn minh họa.
Thread.yield();
~~~

Đây là lời gọi method `java.lang.Thread.yield()`. Compiler Tree API biểu diễn lời gọi dưới một `MethodInvocationTree` và một statement chứa invocation. **Không có `YieldTree`**.

Tên giống nhau không đủ để quyết định loại AST; phân biệt qua cú pháp và node kind.

### 8.7. Tên yield là restricted identifier

`yield` là một **restricted identifier** trong cú pháp Java hiện đại, không nên dùng làm tên method không định danh theo cách làm code khó đọc. Việc gọi phương thức `Thread.yield()` có tên sau dấu chấm **khác** câu lệnh `yield expression;`.

Đừng viết analyzer bằng regex `/yield/` rồi giả định mọi chỗ khớp chuỗi là yield statement. Comment, tên method, string literal và biểu thức có thể chứa chuỗi đó mà không liên quan AST `YieldTree`.

## 9. Các quy tắc ngữ nghĩa cần nhớ khi phân tích YieldTree

### 9.1. Yield cần một switch-expression target hợp lệ

Java Language Specification xác định `yield` chuyển điều khiển tới **switch expression gần nhất** theo cấu trúc ngữ pháp. Nếu không có target hợp lệ, đó là compile-time error.

Ví dụ cố ý sai:

~~~java
// CỐ Ý SAI: switch statement đứng riêng, không tạo kết quả.
switch (x) {
    case 1 -> {
        yield 1;
    }
    default -> {}
}
~~~

`switch` ở đây là statement, không phải expression; bản thân statement không thể nhận giá trị `yield`.

**Chú ý:** Không nên phát biểu cực đoan rằng “bất kỳ YieldTree nào xuất hiện bên trong một SwitchTree đều sai”: trong một cấu trúc phức tạp, có thể có **switch statement lồng bên trong switch expression** và một yield có thể nhắm tới enclosing switch expression hợp lệ theo luật của JLS. Muốn hiểu target, xem ancestor path và kiểm tra ngữ nghĩa, không kiểm tra một ancestor bất kỳ rồi kết luận.

### 9.2. Không nhảy qua ranh giới lambda hoặc method

~~~java
// CỐ Ý SAI nếu yield muốn trả về outer switch expression.
int result = switch (x) {
    default -> {
        java.util.function.IntSupplier s = () -> {
            yield 1;
        };
        yield s.getAsInt();
    }
};
~~~

`yield` trong lambda không thể nhảy ra để trả giá trị cho switch expression ở bên ngoài lambda. Đây là **compile-time error**. Thay vào đó, lambda tự `return 1;`, rồi outer block `yield s.getAsInt();`.

**Bài học cho analyzer:** đi lên ancestor để tìm switch gần nhất là bước định vị cú pháp, nhưng nếu phát hiện ranh giới lambda/method/constructor/initializer, phải hiểu các giới hạn luồng điều khiển theo JLS. Đừng coi một cây có `SWITCH_EXPRESSION` phía trên là đủ để source hợp lệ.

### 9.3. Yield expression không được là void

~~~java
// CỐ Ý SAI: println trả void.
int result = switch (x) {
    default -> {
        yield System.out.println("hello");
    }
};
~~~

Một `yield` phải cung cấp giá trị tương thích với switch expression đích; không thể yield một biểu thức kiểu `void`. AST vẫn có thể có `YieldTree` ở pha parse, nhưng **analyze/type checking** phải xử lý lỗi này.

### 9.4. Exhaustiveness và kiểu kết quả không do YieldTree quyết định

Một switch expression cần **exhaustive** (bao phủ các giá trị đầu vào theo quy tắc của Java). Những `yield` ở các nhánh phải cung cấp giá trị tương thích với kiểu của switch expression ở context.

`YieldTree.getValue()` không cho bạn câu trả lời “mọi giá trị selector đều có nhánh” hoặc “type của switch expression chắc chắn là int” nếu thiếu phân tích `CaseTree`, selector và type attribution.

Ví dụ, `default -> throw new ...` có thể làm nhánh kết thúc bằng exception, **không cần yield**. Một linter đếm ít yield hơn số case không đồng nghĩa switch thiếu kết quả.

## 10. Thực hành xây linter dựa trên YieldTree

### 10.1. Chọn câu hỏi phân tích trước

Các mục tiêu khác nhau đòi cách duyệt khác nhau:

| Câu hỏi | AST/API phù hợp |
|---|---|
| Có bao nhiêu `yield` tường minh? | `visitYield`, đếm `YieldTree` |
| Giá trị cú pháp của mỗi yield là gì? | `YieldTree.getValue()` và cây biểu thức con |
| Yield ở dòng nào? | `SourcePositions` + `LineMap` |
| Yield thuộc switch expression nào? | `TreePathScanner`, tìm `SWITCH_EXPRESSION` gần nhất |
| Có bao nhiêu switch expressions? | `visitSwitchExpression` |
| Có bao nhiêu switch statements? | `visitSwitch` |
| Case arrow trả expression trực tiếp? | `CaseTree.getCaseKind()` + `getBody()` |
| Case dạng colon chứa statement nào? | `CaseTree.getStatements()` |
| Kiểu giá trị yield là gì? | Pha phân tích semantic + `Trees.getTypeMirror(TreePath)` |
| Mọi đường đi có tạo kết quả không? | Control-flow/semantic analysis, không chỉ đếm yields |
| Chính xác snippet gốc của yield? | Start/end positions trên source text |
| Bao nhiêu lần yield thực thi ở runtime? | Runtime instrumentation/profiling, không phải AST count |

### 10.2. Không ghi đè AST bằng cách tự cast nội bộ

Compiler Tree API có các interface `com.sun.source.tree.*` được JDK cung cấp cho việc đọc cây cú pháp. Javadoc cảnh báo **các interface này có thể thay đổi khi ngôn ngữ phát triển**, nên công cụ cần version compatibility tests.

Đừng phụ thuộc không cần thiết vào `com.sun.tools.javac.tree.JCTree` hoặc internal compiler implementation classes để đọc một node `yield` đơn giản. Các API nội bộ có thể thay đổi hoặc không được export công khai; việc dùng `YieldTree`, `TreePathScanner` và `JavacTask` giúp code rõ ràng và phù hợp công cụ phân tích nguồn.

Cũng **không nên tự implement `Tree`** hoặc cố sửa các node hiện có để “rewrite” một switch expression. Compiler Tree API chủ yếu cung cấp **AST view**, không phải builder API bất biến/ổn định cho arbitrary AST mutation. Với code transformation, chọn hạ tầng hỗ trợ source rewrite và kiểm thử ngữ nghĩa.

### 10.3. Đừng trộn các pha parse, analyze và execute

Có ba việc khác nhau:

1. **Parse**: xây cấu trúc AST từ source. `JavacTask.parse()` là trọng tâm của ví dụ.
2. **Analyze**: kiểm tra types, symbol resolution, control flow và những lỗi compile-time. Có thể dùng `JavacTask.analyze()` cùng compiler diagnostics nếu tool cần.
3. **Execute**: chạy bytecode trên JVM; **không diễn ra** chỉ vì bạn gọi `parse()` hoặc `analyze()`.

**Không chạy source người dùng trong linter** chỉ để biết biểu thức yield sẽ trả bao nhiêu: code có thể có side effects, IO hoặc input không tin cậy.

Khi phân tích source sinh từ tool khác hoặc source đang sửa dở trong IDE, nên xử lý lỗi cú pháp/thiếu symbol để tránh crash; AST có thể chứa `ErroneousTree` hoặc thiếu positions hợp lệ.

## 11. Dự án modular và yêu cầu môi trường JDK

Ví dụ inspector dùng hai nhóm API:

- `javax.tools.JavaCompiler`, `JavaFileObject`, `ToolProvider`: module **`java.compiler`**.
- `com.sun.source.tree.*`, `com.sun.source.util.JavacTask`/`Trees`: module **`jdk.compiler`**.

Khi viết **module-info.java** cho một công cụ Java có module tường minh, có thể cần:

~~~java
// Đoạn minh họa cho module-info.java của công cụ, không dùng
// cùng source classpath ví dụ ở trên nếu chưa modularize project.
module example.yield.inspector {
    requires java.compiler;
    requires jdk.compiler;
}
~~~

`ToolProvider.getSystemJavaCompiler()` cần một **JDK/runtime có compiler**; trong một runtime image được tạo bằng `jlink` mà không có module/compiler tương ứng, nó có thể trả `null`. Ví dụ đã kiểm tra trường hợp này bằng một exception rõ ràng.

Khi đóng gói linter thành app, phải bảo đảm runtime chứa `jdk.compiler` và `java.compiler`, không chỉ `java.base`. Khi chạy trên bản JDK mới, có thể parse các cú pháp mới hơn; các AST nodes/CaseTree APIs cũng phát triển theo ngôn ngữ.

**Khuyến nghị:** chọn **JDK toolchain** mà bạn muốn hỗ trợ, kiểm thử trên các phiên bản mục tiêu, và không giả định mọi cú pháp được JDK mới parse thành các node giống hệt JDK cũ. Ví dụ minh họa giới hạn cú pháp input với `--release 17` để có kết quả ổn định trên code Java 17.

## 12. Lỗi thường gặp

| Hiện tượng/nhầm lẫn | Nguyên nhân | Cách xử lý |
|---|---|---|
| Đếm `yield` bằng regex | Gặp comment, string, method `Thread.yield` | Dùng `YieldTree` trong AST |
| Không tìm thấy YieldTree của `case 0 -> 10` | Branch trả expression trực tiếp, không có `yield` | Đọc `CaseTree.getBody()` với RULE |
| Coi YieldTree là ExpressionTree | `yield` là statement chứa một expression | Dùng `node.getValue()` |
| `getValue()` được nghĩ là kết quả runtime | API trả ExpressionTree cú pháp | Chỉ dùng syntax, kết hợp type analysis nếu cần |
| Đếm `YieldTree` bằng số nhánh tạo giá trị | Case arrow-expression/throw không có YieldTree | Phân tích cả CaseTree và flow |
| Liên kết yield với switch gần nhất về số dòng | Nested switch expressions gây sai | Đi lên `TreePath` tới owner phù hợp |
| Xem `SwitchTree` như `SwitchExpressionTree` | Statement không phải value-producing expression | Phân biệt `visitSwitch` và `visitSwitchExpression` |
| Dùng `break 10` thay `yield 10` | Cú pháp preview cũ, không áp dụng Java hiện đại | Dùng `yield` hoặc arrow-expression |
| Dùng `return` trong block để trả giá trị switch | Return rời method, không tương đương yield | Dùng `yield` trong switch expression |
| Dùng `case -> yield x;` trần | Yield là statement, không phải expression body | Dùng `case -> x;` hoặc `case -> {yield x;}` |
| Thiếu yield ở một đường của block | Switch expression không hoàn tất với giá trị | Bảo đảm yield hoặc throw trên mọi đường thích hợp |
| Yield vượt lambda/method boundary | Không được nhảy xuyên ranh giới | Dùng return trong lambda, yield ngoài lambda |
| Yield một biểu thức kiểu `void` | Switch expression cần value | Dùng expression trả giá trị |
| `Task.parse()` thành công nên tưởng source hợp lệ hoàn toàn | Parse chưa phải full semantic analysis | Đọc diagnostics và dùng analyze khi cần |
| `Tree.toString()` được coi là exact source | AST pretty-print có thể đổi spacing/comments | Dùng source positions trên text |
| `LineMap` được nghĩ là luôn có vị trí hợp lệ | Generated/erroneous tree có thể thiếu position | Kiểm tra `Diagnostic.NOPOS` |
| Inspector chạy trên JRE không có compiler | `ToolProvider.getSystemJavaCompiler() == null` | Chạy bằng JDK/runtime có `jdk.compiler` |
| Sử dụng `CaseTree.getExpression()` trong code mới | API đã deprecated ở JDK hiện hành | Dùng getExpressions/getLabels theo baseline |
| Tự implement hoặc mutate `Tree` | AST view không phải builder API được bảo đảm ổn định | Dùng tool source rewrite chuyên dụng |
| Tính cả mã được parse như đã thực thi | AST chứa cả nhánh không đi qua trong runtime | Phân biệt syntax count và execution path |

## 13. Bài tập và lời giải

**Câu 1.** `YieldTree` đại diện cho node nào?

**Đáp án:** Một **câu lệnh `yield expression;`**. Nó là `StatementTree`, có kind `Tree.Kind.YIELD`; `getValue()` trả cây `ExpressionTree` của biểu thức được yield.

**Câu 2.** Source `case 1 -> 100;` của switch expression có cần YieldTree không?

**Đáp án:** Không. `100` trực tiếp là expression body của rule case; để thu thập nó phải dùng `CaseTree.getBody()`, không chỉ quét `YieldTree`.

**Câu 3.** `case 1 -> { int n = 2; yield n * 3; }` có node gì?

**Đáp án:** CaseTree RULE có body BlockTree; trong block chứa VariableTree và **YieldTree**, với `getValue()` là một binary expression (nhân `n * 3`).

**Câu 4.** Một file có ba switch expressions và bảy yield statements. Một lần chạy có thực hiện bảy yields không?

**Đáp án:** Không suy ra được. AST đếm các **declarations của statement**, còn runtime chỉ đi qua những nhánh được chọn. Có thể cùng một case có nhiều yields trên các nhánh `if` khác nhau.

**Câu 5.** `Thread.yield()` có tạo `YieldTree` không?

**Đáp án:** Không. Đó là method invocation và một expression statement; tên method giống chữ `yield` không quyết định AST kind.

**Câu 6.** Để tìm switch expression đích của yield trong nested switch, dùng gì?

**Đáp án:** Dùng `TreePathScanner.getCurrentPath()`, đi ngược `TreePath` đến `Tree.Kind.SWITCH_EXPRESSION` gần nhất rồi xét quy tắc ngữ nghĩa nếu cần.

**Câu 7.** `YieldTree.getValue()` có trả số `204` tại runtime khi expression là `inner + 3` không?

**Đáp án:** Không. Nó trả ExpressionTree mô tả `inner + 3`; giá trị runtime chỉ xuất hiện khi chương trình chạy với dữ liệu cụ thể.

**Câu 8.** `switch statement` có là một yield target hợp lệ như switch expression không?

**Đáp án:** Không. Yield tạo kết quả của **switch expression**. Một switch statement đứng riêng không có kết quả để nhận yield.

**Câu 9.** Tại sao `JavacTask.parse()` chưa đủ để khẳng định có yield hợp lệ?

**Đáp án:** Parse xây AST; tính hợp lệ về kiểu, control flow, exhaustiveness và các ranh giới điều khiển còn cần semantic analysis/compiler diagnostics.

**Câu 10.** Muốn vị trí dòng của một YieldTree, gọi API nào?

**Đáp án:** `Trees.getSourcePositions().getStartPosition(unit,node)` để có source offset, sau đó `unit.getLineMap().getLineNumber(offset)`. Cần xử lý vị trí không xác định trong tool production.

**Câu 11.** Dùng `return 1` thay cho `yield 1` trong một arrow-block của switch expression có tương đương không?

**Đáp án:** Không. Return nhắm tới method/lambda return target, còn yield nhắm tới switch expression. Không dùng return như một cách trả nhánh.

**Câu 12.** Có nên dùng trực tiếp `com.sun.tools.javac.tree.JCTree` để truy cập một yield node?

**Đáp án:** Không cần thiết. Dùng `com.sun.source.tree.YieldTree` và visitor API đã được công khai trong `jdk.compiler`; vẫn cần kiểm thử tương thích vì Compiler Tree API có thể tiến hóa.

**Câu 13.** Một linter “mọi nhánh của switch có kết quả” có thể được xây bằng việc kiểm tra có ít nhất một YieldTree trong mỗi CaseTree không?

**Đáp án:** Không. Rule với expression body trả kết quả mà không cần yield, throw branch không trả giá trị, và một block có yield ở một đường nhưng thiếu ở đường khác vẫn có thể sai. Phải phân tích **từng dạng case và control flow**.

## Tài liệu chính thức

- [OpenJDK JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): switch expressions trở thành tính năng chính thức ở Java 14, với câu lệnh yield.
- [Oracle Java 25 — YieldTree](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/tree/YieldTree.html): `YieldTree extends StatementTree` và `getValue()`.
- [Oracle Java 25 — Tree.Kind](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/tree/Tree.Kind.html): kind `YIELD` và `SWITCH_EXPRESSION`.
- [Oracle Java 25 — SwitchExpressionTree](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/tree/SwitchExpressionTree.html): selector `getExpression()` và `getCases()`.
- [Oracle Java 25 — CaseTree](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/tree/CaseTree.html): `CaseKind.RULE`/`STATEMENT`, `getBody()`/`getStatements()`, các API hiện hành.
- [Oracle Java 25 — TreeScanner](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/util/TreeScanner.html): `visitYield`, `visitSwitchExpression` và quy tắc scan children.
- [Oracle Java 17 — TreePathScanner](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/TreePathScanner.html): đường dẫn cha và `getCurrentPath()`.
- [Oracle Java 17 — JavacTask](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/JavacTask.html): `parse()`, `analyze()` và compiler task.
- [Oracle Java 17 — Trees](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/Trees.html): `getSourcePositions()`, `getTypeMirror()` và tree utilities.
- [Oracle Java 17 — SourcePositions](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/SourcePositions.html): start/end position của syntax trees.
- [Oracle Java 17 — JLS 14.21: The yield Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.21): yield target, điều kiện compile-time error và giới hạn control flow.
- [Oracle Java 17 — JLS 15.28: Switch Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.28): quy tắc ngữ nghĩa của switch expressions.
- [Oracle Java 26 — Switch Expressions and Statements](https://docs.oracle.com/en/java/javase/26/language/switch-expressions-statements.html): hướng dẫn cú pháp còn được dùng trên JDK hiện đại.

**Ghi nhớ:** `YieldTree` đại diện **chính câu lệnh `yield expression;`**, không phải tất cả kết quả của mọi nhánh switch. Dùng `getValue()` để lấy **AST biểu thức được yield**, `visitYield` để tìm các vị trí yield, và `TreePathScanner` để ghép đúng yield với **switch expression gần nhất**. Nhánh `case -> expression` không có YieldTree, nhánh `throw` cũng không yield, và một switch statement riêng không phải value-producing target. Hãy kết hợp phân tích CaseTree, source positions và semantic diagnostics khi cần một linter chính xác.
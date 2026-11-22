# Đọc phần thân và các biểu thức nhãn case trong cây cú pháp Java

## 1. Bài toán và mục tiêu

Một công cụ phân tích mã Java thường cần **đọc cấu trúc của các nhánh `case`**, chứ không chỉ tìm chuỗi chữ `case` bằng regex. Ví dụ, với:

~~~java
String label = switch (score) {
    case 1, 2 -> "low";
    case 3 -> {
        yield "medium";
    }
    default -> "other";
};
~~~

Chúng ta cần trả lời:

- Đây là **`switch expression`** hay **`switch statement`**?
- Nhánh `case 1, 2` có **hai biểu thức nhãn** hay hai case nodes?
- Nhánh `case 1, 2 -> "low"` có **phần thân kiểu biểu thức** hay danh sách câu lệnh?
- Nhánh `case 3 -> { yield ...; }` biểu diễn một **`BlockTree`** hay một `YieldTree` trực tiếp?
- `default` được biểu diễn khác `case 1` như thế nào?
- Với cú pháp hiện đại như `case String s when s.length() > 3 ->` hoặc `case null, default ->`, API nào đọc được **pattern, default và guard** đầy đủ?

Mục tiêu của bài là sử dụng **Compiler Tree API** của JDK (`com.sun.source.tree`, `com.sun.source.util`) để đọc **biểu thức nhãn** và **phần thân** của `CaseTree`, từ đó tạo nền tảng cho linter, static analyzer, code navigation, refactoring và công cụ thống kê switch.

**Phạm vi:** Chủ đề cha là **“Cây cú pháp Java”**, đề bài trực tiếp là **“Đọc phần thân và các biểu thức nhãn case”**. Trọng tâm nằm ở **AST của `switch`**, không phải viết một switch statement mới để chạy nghiệp vụ.

**Tính hiện hành:** `switch expression` được chuẩn hóa ở **Java 14** (JEP 361); `SwitchExpressionTree`, `CaseTree.getExpressions()`, `getBody()`, `getCaseKind()` vẫn còn sử dụng được. Trên **Java 21+**, API hiện hành `CaseTree.getLabels()` và `getGuard()` hỗ trợ biểu diễn nhãn pattern/`null`/`default` tốt hơn. Bài có **hai ví dụ độc lập**: chương trình thứ nhất được biên dịch với **`--release 17`**, chương trình thứ hai với **`--release 21`**. Không dùng API preview của JDK 17 cho chương trình Java 17.

## 2. AST khác gì so với chuỗi mã nguồn?

**Abstract Syntax Tree (AST)** biểu diễn cấu trúc cú pháp bằng các node có kiểu. Ví dụ:

~~~java
switch (n) {
    case 8, 9 -> System.out.println("near");
    default -> {
        System.out.println("far");
    }
}
~~~

Có thể hình dung:

~~~text
SwitchTree
├── expression: n
└── cases
    ├── CaseTree: RULE
    │   ├── labels: 8, 9
    │   └── body: ExpressionStatementTree
    │       └── MethodInvocationTree
    └── CaseTree: RULE
        ├── label: default
        └── body: BlockTree
            └── ExpressionStatementTree
~~~

Điểm có giá trị: **hai nhánh đều dùng `->`, nhưng phần thân có hình dạng AST khác nhau**. Nếu chỉ lấy chuỗi sau dấu `->`, công cụ dễ nhầm một method call với một block, hoặc làm mất cấu trúc `yield`.

Compiler Tree API thuộc module **`jdk.compiler`**; phần public API có tên package `com.sun.source.*`. Đây là API được tài liệu JDK cung cấp để đọc AST, **khác** việc sử dụng những lớp triển khai nội bộ `com.sun.tools.javac.*` không phải API ổn định cho ứng dụng.

### 2.1. Những thành phần chính

| API / node | Vai trò |
| --- | --- |
| `JavaCompiler` và `ToolProvider` | Lấy compiler của JDK để tạo compilation task |
| `JavacTask` | `parse()` nguồn Java thành `CompilationUnitTree`; có thể `analyze()` khi cần kiểm tra ngữ nghĩa |
| `CompilationUnitTree` | Gốc AST của một source file |
| `TreePathScanner` | Duyệt AST và giữ đường dẫn đến node hiện tại |
| `SwitchTree` | Node **switch statement** |
| `SwitchExpressionTree` | Node **switch expression** |
| `CaseTree` | Một nhóm cú pháp `case`/`default` trong switch |
| `ExpressionTree` | Loại node biểu thức, ví dụ literal, identifier, binary expression |
| `StatementTree` | Loại node câu lệnh, ví dụ block, break, yield, invocation statement |
| `CaseLabelTree` | Kiểu nhãn tổng quát trong Java 21+ |
| `SourcePositions` / `LineMap` | Vị trí offset, dòng và cột trong source file |

**Chú ý:** AST phản ánh **cú pháp**, không tự tính giá trị của mọi biểu thức nhãn. Node cho `case 1 + 2` có thể là một `BinaryTree`; giá trị hằng số 3 là vấn đề đánh giá/semantic analysis chứ không phải chỉ gọi `toString()`.

## 3. SwitchTree và SwitchExpressionTree: cùng có cases, khác vai trò

### 3.1. Switch statement

~~~java
switch (n) {
    case 0 -> System.out.println("zero");
    default -> System.out.println("other");
}
~~~

AST node: **`SwitchTree`**, kế thừa `StatementTree`.

Hai phương thức quan trọng:

~~~java
ExpressionTree selector = switchTree.getExpression();
List<? extends CaseTree> cases = switchTree.getCases();
~~~

Đây là **snippet**, trong đó `switchTree` là đối tượng `SwitchTree` được lấy từ AST. `selector` là biểu thức trong cặp ngoặc `switch (...)`; `cases` chứa các CaseTree theo thứ tự xuất hiện.

### 3.2. Switch expression

~~~java
String category = switch (n) {
    case 1, 2 -> "low";
    default -> "other";
};
~~~

AST node: **`SwitchExpressionTree`**, kế thừa `ExpressionTree`.

~~~java
ExpressionTree selector = switchExpression.getExpression();
List<? extends CaseTree> cases = switchExpression.getCases();
~~~

Đây là **snippet**, trong đó `switchExpression` là đối tượng `SwitchExpressionTree`.

**Đừng nhầm `SwitchTree` với `SwitchExpressionTree`.** Cả hai có `getExpression()` và `getCases()`, nhưng chính node cha khác loại. `Tree.Kind.SWITCH` và `Tree.Kind.SWITCH_EXPRESSION` cũng khác nhau. Khi viết scanner, nên override **cả `visitSwitch` và `visitSwitchExpression`** nếu cần phân tích mọi switch trong project.

### 3.3. Vì sao không chỉ tìm tên “switch”?

Một chương trình có thể chứa:

~~~java
int result = switch (a) {
    case 1 -> 10;
    default -> 0;
};

switch (a) {
    case 1 -> System.out.println("one");
    default -> System.out.println("other");
}
~~~

Hình thức nhìn khá giống, nhưng:
- Biểu thức đầu tiên **tạo một giá trị** để gán cho `result`.
- Câu lệnh thứ hai **thực thi hành động**.
- Cả hai vẫn dùng `CaseTree`, nhưng **phần thân case** có thể thuộc những node kinds khác nhau.

Trong trình phân tích cú pháp, luôn xuất phát từ loại node AST thay vì suy luận từ `toString()` của toàn bộ switch.

## 4. CaseTree: node cần đọc chính xác

`CaseTree` biểu diễn một nhánh hoặc nhóm nhãn trong switch. Các API dùng trong bài:

| Method | Dữ liệu trả về | Khi nào dùng? |
| --- | --- | --- |
| `getCaseKind()` | `CaseTree.CaseKind.RULE` hoặc `STATEMENT` | Xác định cú pháp **mũi tên `->`** hay **dấu hai chấm `:`** |
| `getExpressions()` | `List<? extends ExpressionTree>` | Đọc **nhãn biểu thức truyền thống** trong mã nhắm Java 17/Java 14 |
| `getBody()` | `Tree` hoặc `null` | Đọc **phần thân** của case dạng **`RULE`** |
| `getStatements()` | `List<? extends StatementTree>` hoặc `null` | Đọc **các statement** của case dạng **`STATEMENT`** |
| `getLabels()` | `List<? extends CaseLabelTree>` | **Java 21+**: đọc nhãn tổng quát gồm constant, pattern, default |
| `getGuard()` | `ExpressionTree` hoặc `null` | **Java 21+**: điều kiện `when` của case pattern |
| `getExpression()` | `ExpressionTree` hoặc `null` | **Deprecated**; không nên dùng để xây tool mới |

**Quy tắc quan trọng:** `getBody()` và `getStatements()` **không phải hai cách đồng nghĩa để đọc cùng một dữ liệu**. Hãy xét `getCaseKind()` trước rồi gọi phương thức tương ứng.

### 4.1. Hai hình thức của CaseKind

~~~text
CaseTree.CaseKind
├── RULE       : case 1, 2 -> expression / statement / block / throw
└── STATEMENT  : case 1, 2: statements
~~~

**`RULE`** tương ứng cú pháp mũi tên:

~~~java
case 1, 2 -> "low"
case 3 -> { yield "medium"; }
case 4 -> throw new IllegalStateException()
~~~

**`STATEMENT`** tương ứng cú pháp dấu hai chấm:

~~~java
case 1:
    perform();
    break;
~~~

Những đoạn trên là **mảnh cú pháp case trong switch**, không phải tệp Java độc lập.

### 4.2. Không suy diễn từ `null` một cách mù quáng

Với case kiểu RULE:
- `getBody()` trả một `Tree` mô tả phần sau `->`.
- `getStatements()` trả **`null`**.

Với case kiểu STATEMENT:
- `getStatements()` trả **danh sách các statement**, có thể **rỗng**.
- `getBody()` trả **`null`**.

**Dễ sai:** Viết `caseTree.getStatements().size()` mà không kiểm tra `CaseKind` sẽ dẫn tới `NullPointerException` khi gặp cú pháp `->`.

## 5. Đọc biểu thức nhãn case bằng getExpressions()

### 5.1. Một nhãn

~~~java
case 3 -> "three";
~~~

`caseTree.getExpressions()` chứa một biểu thức, ví dụ `LiteralTree` cho literal nguyên `3`.

### 5.2. Nhiều nhãn trong cùng case

~~~java
case 1, 2 -> "low";
~~~

Đây là **một CaseTree** có **hai `ExpressionTree` trong `getExpressions()`**. Nó khác với hai nhánh liên tiếp viết bằng dấu hai chấm.

Ví dụ xử lý an toàn:

~~~java
List<? extends ExpressionTree> labels = caseTree.getExpressions();

for (ExpressionTree label : labels) {
    System.out.println("Label kind: " + label.getKind());
}
~~~

Đây là **snippet trong một hàm đã có `caseTree`**, cần import `java.util.List` và `com.sun.source.tree.ExpressionTree`. Nếu nhãn là literal, `getKind()` có thể là `INT_LITERAL`, `STRING_LITERAL`, v.v.

### 5.3. Nhánh default ở API biểu thức cổ điển

~~~java
default -> "other";
~~~

Với `getExpressions()`, **danh sách trả về rỗng** cho `default`:

~~~java
String display = caseTree.getExpressions().isEmpty()
        ? "default"
        : caseTree.getExpressions().toString();
~~~

Đây là code minh họa. Nó phù hợp **ví dụ switch kiểu truyền thống trên Java 17**. Với **Java 21+**, đặc biệt `case null, default` hay pattern labels, nên dùng `getLabels()` để biểu diễn đầy đủ hơn, thay vì coi mọi danh sách expression rỗng là “chỉ có default”.

### 5.4. Không dùng getExpression() deprecated

`CaseTree.getExpression()` đã **deprecated**. Nó chỉ trả **biểu thức đầu tiên** khi một case có nhiều nhãn, hoặc `null` khi default. Nếu công cụ cần biết cả `case 1, 2, 3`, API này **làm mất dữ liệu**.

**Nên dùng:**
- `getExpressions()` cho các case labels kiểu biểu thức trong chương trình nhắm Java 17.
- `getLabels()` cho công cụ Java 21+ cần phân tích pattern, `null`, `default` và các loại nhãn mới.

Không xây parser mới chỉ quanh `getExpression()`; nó không còn phù hợp cho phân tích switch đầy đủ.

## 6. Đọc phần thân của case dạng RULE bằng getBody()

### 6.1. Mũi tên trả một expression

~~~java
case 1, 2 -> "low";
~~~

`getBody()` là một node **`STRING_LITERAL`**. Đây không phải `List<StatementTree>`, và cũng không phải một `ReturnTree`.

### 6.2. Mũi tên theo sau một block

~~~java
case 3 -> {
    int x = n + 1;
    yield "value" + x;
}
~~~

`getBody()` là một **`BlockTree`**. Các câu lệnh bên trong block lấy qua:

~~~java
Tree body = caseTree.getBody();

if (body instanceof BlockTree block) {
    for (StatementTree statement : block.getStatements()) {
        System.out.println(statement.getKind());
    }
}
~~~

Đây là snippet với `caseTree` đã có và các import `Tree`, `BlockTree`, `StatementTree` tương ứng. Pattern matching cho `instanceof` ở dạng này đã ổn định trên Java 17.

Trong block ví dụ:
- Có một khai báo biến `int x = n + 1`.
- Có một `YieldTree` với biểu thức `"value" + x` (kind **`PLUS`**).
- `yield` **trao giá trị của switch expression**, không phải `return` khỏi method.

**Đừng gọi `getBody().getKind() == YIELD` chỉ vì trong block có từ khóa `yield`**. Node trực tiếp sau `->` là **`BLOCK`**, còn `YieldTree` nằm sâu bên trong block.

### 6.3. Mũi tên theo sau một câu lệnh gọi method

~~~java
case 8, 9 -> System.out.println("near");
~~~

Với switch **statement** dùng arrow, `getBody()` thường là **`EXPRESSION_STATEMENT`**, chứa một `MethodInvocationTree`. Nó khác với switch **expression** trả giá trị bằng expression trực tiếp.

### 6.4. Mũi tên theo sau throw

~~~java
case 100 -> throw new IllegalArgumentException();
~~~

`getBody()` là một **`ThrowTree`** (kind `THROW`). Vì vậy code phân tích cần chấp nhận **nhiều loại Tree**, không chỉ `ExpressionTree` và `BlockTree`.

### 6.5. Không dùng toString() như parser thay thế

`Tree.toString()` hữu ích để **in debug**, nhưng không bảo đảm giữ nguyên mọi khoảng trắng, comment hoặc định dạng nguồn. Một linter nghiêm túc nên:
- Kiểm tra `getKind()` và interface node thật.
- Duyệt node con bằng `TreeScanner`/`TreePathScanner`.
- Dùng `SourcePositions` khi cần đoạn nguồn chính xác.
- Không regex trên chuỗi `getBody().toString()` để quyết định block có `yield` hay không.

## 7. Đọc phần thân của case dạng STATEMENT bằng getStatements()

### 7.1. Một case chứa nhiều statement

~~~java
switch (n) {
    case 1:
        System.out.println("one");
        break;
    default:
        System.out.println("other");
}
~~~

Với `case 1:`, `getCaseKind() == STATEMENT` và `getStatements()` là danh sách có thể gồm:
- `EXPRESSION_STATEMENT` cho lệnh in.
- `BREAK` cho `break;`.

Với `default:`, phương thức cũng trả danh sách statement thuộc nhánh.

### 7.2. Case rỗng không phải lỗi của API

~~~java
switch (n) {
    case 0:
    case 1:
        System.out.println("small");
        break;
    default:
        System.out.println("other");
}
~~~

AST thường có **hai CaseTree liên tiếp**:
- `case 0:` có **danh sách statement rỗng**.
- `case 1:` có **hai statement**: invocation và `break`.

Đó là cú pháp switch statement truyền thống cho phép **fall-through**. Chúng **không tương đương về cấu trúc AST** với:

~~~java
case 0, 1 -> System.out.println("small");
~~~

Ở đây là **một CaseTree dạng RULE** có **hai nhãn**, không có fall-through kiểu dấu hai chấm.

### 7.3. Một case dấu hai chấm cũng có thể có nhiều biểu thức nhãn

~~~java
case 1, 2:
    System.out.println("small");
    break;
~~~

Đây là **một CaseTree dạng STATEMENT**, `getExpressions()` có **hai expression nodes**, `getStatements()` chứa các statement. Hãy phân biệt **“nhiều nhãn trong một case”** với **“nhiều case nodes đứng liên tiếp”**.

### 7.4. Switch expression vẫn có thể dùng case dấu hai chấm

Trong switch expression, các nhánh **dấu hai chấm** cũng có thể sử dụng `yield`:

~~~java
int result = switch (n) {
    case 0: yield 10;
    case 1, 2: yield 20;
    default: yield 30;
};
~~~

Ở đây:
- Node cha là **`SwitchExpressionTree`**.
- Các `CaseTree` đều có kind **`STATEMENT`**.
- `getStatements()` chứa **`YieldTree`**.
- `getBody()` trả `null`.

**Quan trọng:** Đừng đồng nhất “switch expression” với “mọi case phải là RULE”. **Loại switch ở node cha** và **loại cú pháp case** là **hai chiều phân loại độc lập**.

## 8. Ví dụ Java 17+ hoàn chỉnh: duyệt SwitchTree và CaseTree

Ví dụ sau tự tạo **một file nguồn Java trong bộ nhớ**, gọi `javac` qua `JavaCompiler`/`JavacTask`, rồi duyệt AST để đọc:
- Switch statement hay switch expression.
- Mỗi danh sách **biểu thức nhãn case**.
- Cú pháp **RULE** hay **STATEMENT**.
- Loại node **phần thân** hoặc số statement tương ứng.
- Node `yield` trong phần thân block.

Dùng JDK 17+ có **module `jdk.compiler`**. Không cần file mã nguồn `Sample.java` trên ổ đĩa vì ví dụ dùng `SimpleJavaFileObject`.

**Lưu vào tệp `SwitchAstReader17.java`:**

~~~java
import java.io.IOException;
import java.net.URI;
import java.util.List;
import java.util.stream.Collectors;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;
import com.sun.source.tree.CaseTree;
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.ExpressionTree;
import com.sun.source.tree.SwitchExpressionTree;
import com.sun.source.tree.SwitchTree;
import com.sun.source.tree.Tree;
import com.sun.source.tree.YieldTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.TreePathScanner;

public final class SwitchAstReader17 {
    private static final String SOURCE = """
        class Sample {
            static String level(int n) {
                return switch (n) {
                    case 1, 2 -> "low";
                    case 3 -> {
                        int x = n + 1;
                        yield "value" + x;
                    }
                    default -> "other";
                };
            }

            static void log(int n) {
                switch (n) {
                    case 0:
                    case 1:
                        System.out.println("small");
                        break;
                    default:
                        System.out.println("big");
                }
            }

            static void arrows(int n) {
                switch (n) {
                    case 8, 9 -> System.out.println("near");
                    default -> {
                        System.out.println("far");
                    }
                }
            }
        }
        """;

    private static final class SourceFile extends SimpleJavaFileObject {
        SourceFile() {
            super(URI.create("string:///Sample.java"), JavaFileObject.Kind.SOURCE);
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return SOURCE;
        }
    }

    private static String labels(CaseTree c) {
        List<? extends ExpressionTree> labels = c.getExpressions();
        return labels.isEmpty()
                ? "default"
                : labels.stream()
                        .map(Object::toString)
                        .collect(Collectors.joining(", "));
    }

    private static void printCase(CaseTree c) {
        String payload;
        if (c.getCaseKind() == CaseTree.CaseKind.RULE) {
            Tree body = c.getBody();
            payload = "body=" + (body == null ? "null" : body.getKind().name());
            if (c.getStatements() != null) {
                throw new IllegalStateException(
                        "Arrow rule has statement list");
            }
        } else {
            payload = "statements=" + c.getStatements().size();
            if (c.getBody() != null) {
                throw new IllegalStateException(
                        "Colon case has a rule body");
            }
        }

        System.out.println("  labels=[" + labels(c) + "] form="
                + c.getCaseKind() + " " + payload);
    }

    public static void main(String[] args) throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "Use a JDK, not a stripped runtime");
        }

        JavacTask task = (JavacTask) compiler.getTask(
                null, null, null,
                List.of("-proc:none", "--release", "17"),
                null, List.of(new SourceFile()));

        for (CompilationUnitTree unit : task.parse()) {
            new TreePathScanner<Void, Void>() {
                @Override
                public Void visitSwitchExpression(
                        SwitchExpressionTree tree, Void p) {
                    System.out.println("SWITCH_EXPRESSION");
                    for (CaseTree c : tree.getCases()) {
                        printCase(c);
                    }
                    return super.visitSwitchExpression(tree, p);
                }

                @Override
                public Void visitSwitch(SwitchTree tree, Void p) {
                    System.out.println("SWITCH_STATEMENT");
                    for (CaseTree c : tree.getCases()) {
                        printCase(c);
                    }
                    return super.visitSwitch(tree, p);
                }

                @Override
                public Void visitYield(YieldTree tree, Void p) {
                    System.out.println("    yield expression="
                            + tree.getValue().getKind());
                    return super.visitYield(tree, p);
                }
            }.scan(unit, null);
        }
    }
}
~~~

### 8.1. Biên dịch và chạy

~~~bash
javac -encoding UTF-8 --release 17 SwitchAstReader17.java
java SwitchAstReader17
~~~

**Stdout chính xác đã kiểm chứng trên JDK 24, mã biên dịch theo `--release 17`:**

~~~text
SWITCH_EXPRESSION
  labels=[1, 2] form=RULE body=STRING_LITERAL
  labels=[3] form=RULE body=BLOCK
  labels=[default] form=RULE body=STRING_LITERAL
    yield expression=PLUS
SWITCH_STATEMENT
  labels=[0] form=STATEMENT statements=0
  labels=[1] form=STATEMENT statements=2
  labels=[default] form=STATEMENT statements=1
SWITCH_STATEMENT
  labels=[8, 9] form=RULE body=EXPRESSION_STATEMENT
  labels=[default] form=RULE body=BLOCK
~~~

### 8.2. Giải thích các dòng đầu

**`SWITCH_EXPRESSION`**: scanner đến node `SwitchExpressionTree` của method `level`.

**`labels=[1, 2] form=RULE body=STRING_LITERAL`**: một CaseTree có hai nhãn `1` và `2`; phần thân trực tiếp là expression literal `"low"`.

**`labels=[3] form=RULE body=BLOCK`**: phần sau arrow là block, không phải `YieldTree` trực tiếp.

**`yield expression=PLUS`**: scanner tiếp tục duyệt block và thấy `YieldTree` chứa biểu thức nối chuỗi `"value" + x`, loại node `PLUS`. Vì `visitSwitchExpression` gọi `super.visitSwitchExpression(...)`, trình duyệt vẫn đi vào các node con.

**`labels=[default]`**: do code hiển thị riêng khi `getExpressions()` rỗng; không có một literal `default` nằm trong `getExpressions()` của Java 17.

### 8.3. Giải thích switch statement kiểu dấu hai chấm

**`labels=[0] form=STATEMENT statements=0`**: case đầu là một nhóm nhãn riêng, không có statement sau dấu hai chấm trước case tiếp theo.

**`labels=[1] form=STATEMENT statements=2`**: case thứ hai chứa method invocation và `break`.

**`labels=[default] form=STATEMENT statements=1`**: nhánh default chứa một statement in ra màn hình.

Việc **case 0 không có statement** không có nghĩa nó không được nhận diện khi runtime chạy: trong switch statement kiểu colon, execution có thể **fall-through** đến statements của case sau. AST hiển thị cấu trúc cú pháp, không tự mô phỏng toàn bộ control flow.

### 8.4. Giải thích switch statement kiểu mũi tên

**`labels=[8, 9] form=RULE body=EXPRESSION_STATEMENT`**: phần sau arrow là invocation statement.

**`labels=[default] form=RULE body=BLOCK`**: phần sau arrow là block chứa một statement.

**Không nên mong `getBody()` luôn trả `ExpressionTree`**. Kiểu trả về là `Tree` vì một rule body có thể là expression, statement, block hoặc throw theo cú pháp hợp lệ.

### 8.5. Vì sao trình duyệt không đọc những file khác?

Source nằm trong text block `SOURCE` và được bọc bởi `SimpleJavaFileObject`. `JavacTask.parse()` biến source thành AST. Trong ví dụ này, chương trình không gọi `task.analyze()` hay `task.generate()`, vì chỉ cần cú pháp `switch`; không cần sinh class `Sample.class`.

**Lưu ý:** `JavacTask.parse()` có thể trả cây cả khi source chứa lỗi; trong tool production, dùng diagnostic listener/collector và kiểm tra lỗi trước khi tin cấu trúc hoặc đưa ra gợi ý refactor.

## 9. Tách đúng nhãn và phần thân trong code analyzer

Một phương thức xử lý nên kiểm tra **`CaseKind` trước**:

~~~java
static void inspectCase(CaseTree c) {
    if (c.getCaseKind() == CaseTree.CaseKind.RULE) {
        Tree body = c.getBody();
        if (body != null) {
            System.out.println("Arrow body kind=" + body.getKind());
        }
    } else {
        List<? extends StatementTree> statements = c.getStatements();
        if (statements != null) {
            System.out.println("Colon statement count="
                    + statements.size());
        }
    }
}
~~~

Đây là **snippet trong class**, cần các imports `CaseTree`, `Tree`, `StatementTree`, `List`. Nó tránh dereference `null` và không giả định số statement tối thiểu là 1.

### 9.1. Đừng đưa nhãn vào cùng tập node với statements

Case label **không** phải là “câu lệnh đầu tiên” trong `getStatements()`. Nhãn là phần xác định nhánh, được đọc từ `getExpressions()` hoặc `getLabels()`. Ngược lại, `yield`, `break` và các method calls nằm trong **body/statements**, không nằm trong tập label expressions.

### 9.2. Đừng coi số nhãn là số CaseTree

~~~java
case 1, 2, 3 -> "group";
~~~

Một CaseTree; `getExpressions().size() == 3` trong tình huống biểu thức hằng thông thường.

~~~java
case 1:
case 2:
case 3:
    System.out.println("group");
    break;
~~~

Ba CaseTree liên tiếp (theo cách phân tích trong ví dụ đã kiểm chứng), trong đó các nhánh trước có thể có **danh sách statements rỗng**.

Một công cụ thống kê “số nhánh” cần định nghĩa muốn đếm:
- **Số `CaseTree`** (số nhóm cú pháp).
- **Số label alternatives**.
- **Số đoạn body có statement**.
- Hay **số đường đi có thể thực thi** (phân tích control flow sâu hơn).

Các con số đó không luôn bằng nhau.

## 10. Đọc nhãn hiện đại với getLabels() trên Java 21+

Từ Java 21, các loại nhãn switch đã phong phú hơn:
- Constant labels, trong đó có literal `null`.
- Pattern labels như `case String s` hoặc `case Integer n`.
- Default labels, kể cả cấu trúc `case null, default`.
- Guard `when` gắn với một pattern case.

Vì vậy API **`CaseTree.getLabels()`** trả một danh sách **`CaseLabelTree`** và `getGuard()` trả điều kiện guard khi có.

### 10.1. Những interface cần biết

| API Java 21+ | Vai trò |
| --- | --- |
| `CaseLabelTree` | Superinterface của các nhãn case hiện hành |
| `ConstantCaseLabelTree` | Nhãn là constant expression, bao gồm `null` |
| `PatternCaseLabelTree` | Nhãn là pattern; dùng `getPattern()` |
| `DefaultCaseLabelTree` | Phần `default` của nhãn |
| `CaseTree.getLabels()` | Đọc **mọi label alternatives** dưới kiểu tổng quát |
| `CaseTree.getGuard()` | Đọc **biểu thức sau `when`**, hoặc `null` nếu không có |

### 10.2. Vì sao không ép getExpressions() xử lý pattern?

`getExpressions()` trả `ExpressionTree`; trong khi `PatternCaseLabelTree` chứa **`PatternTree`**, không phải biểu thức nhãn hằng thông thường. Dùng `getLabels()` giúp tool không mất thông tin pattern hoặc default khi xử lý syntax mới.

**Cẩn thận với phiên bản:** Trong một số JDK trước Java 21, các API phục vụ pattern switch từng mang trạng thái **preview**. Đề bài yêu cầu kiến thức còn áp dụng, vì vậy **ví dụ production nhắm Java 21+** dùng các API **đã ổn định** và không khuyến nghị bật preview của JDK 17.

## 11. Ví dụ Java 21+ hoàn chỉnh: pattern, guard, null và default

Ví dụ sau cũng phân tích source **trong bộ nhớ**, nhưng dùng Java 21 syntax và API `getLabels()`/`getGuard()`.

**Lưu thành `SwitchLabelsReader21.java`:**

~~~java
import java.io.IOException;
import java.net.URI;
import java.util.List;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;
import com.sun.source.tree.CaseLabelTree;
import com.sun.source.tree.CaseTree;
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.ConstantCaseLabelTree;
import com.sun.source.tree.PatternCaseLabelTree;
import com.sun.source.tree.SwitchExpressionTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.TreePathScanner;

public final class SwitchLabelsReader21 {
    private static final String SOURCE = """
        class ModernSample {
            static String describe(Object value) {
                return switch (value) {
                    case String s when s.length() > 3 -> "long text";
                    case Integer n -> "number";
                    case null, default -> "other";
                };
            }
        }
        """;

    private static final class SourceFile extends SimpleJavaFileObject {
        SourceFile() {
            super(URI.create("string:///ModernSample.java"),
                    JavaFileObject.Kind.SOURCE);
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return SOURCE;
        }
    }

    public static void main(String[] args) throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK required");
        }

        JavacTask task = (JavacTask) compiler.getTask(
                null, null, null,
                List.of("-proc:none", "--release", "21"),
                null, List.of(new SourceFile()));

        for (CompilationUnitTree unit : task.parse()) {
            new TreePathScanner<Void, Void>() {
                @Override
                public Void visitSwitchExpression(
                        SwitchExpressionTree tree, Void p) {
                    System.out.println("SWITCH_EXPRESSION");
                    for (CaseTree c : tree.getCases()) {
                        System.out.println("  labels count="
                                + c.getLabels().size() + " guard="
                                + (c.getGuard() == null
                                ? "none" : c.getGuard()));

                        for (CaseLabelTree label : c.getLabels()) {
                            String detail = switch (label) {
                                case ConstantCaseLabelTree constant ->
                                    "constant="
                                            + constant.getConstantExpression();
                                case PatternCaseLabelTree pattern ->
                                    "pattern=" + pattern.getPattern();
                                default -> "kind=" + label.getKind();
                            };
                            System.out.println("    " + detail);
                        }
                    }
                    return super.visitSwitchExpression(tree, p);
                }
            }.scan(unit, null);
        }
    }
}
~~~

### 11.1. Biên dịch và chạy

~~~bash
javac -encoding UTF-8 --release 21 SwitchLabelsReader21.java
java SwitchLabelsReader21
~~~

**Stdout chính xác đã kiểm chứng trên JDK 24 với `--release 21`:**

~~~text
SWITCH_EXPRESSION
  labels count=1 guard=s.length() > 3
    pattern=String s
  labels count=1 guard=none
    pattern=Integer n
  labels count=2 guard=none
    constant=null
    kind=DEFAULT_CASE_LABEL
~~~

### 11.2. Giải thích từng nhánh

**`case String s when s.length() > 3`**:
- `getLabels()` có một `PatternCaseLabelTree`.
- `getPattern()` là `String s`.
- `getGuard()` là biểu thức `s.length() > 3`.
- Guard là một **ExpressionTree riêng**, không phải một label thứ hai.

**`case Integer n`**:
- Một `PatternCaseLabelTree`.
- `getGuard() == null`.
- Variable `n` được khai báo trong pattern.

**`case null, default`**:
- `getLabels().size() == 2`.
- Một `ConstantCaseLabelTree` với constant expression là literal `null`.
- Một `DefaultCaseLabelTree`, kind `DEFAULT_CASE_LABEL`.
- Không nên coi đây là một list `getExpressions()` rỗng giống standalone `default`.

### 11.3. Vì sao ví dụ sử dụng switch trên label objects?

Đoạn:

~~~java
String detail = switch (label) {
    case ConstantCaseLabelTree constant -> "...";
    case PatternCaseLabelTree pattern -> "...";
    default -> "...";
};
~~~

là **pattern matching for switch** đã ổn định từ Java 21. Nó được biên dịch với `--release 21`, **không** nằm trong chương trình Java 17 ở phần 8. Đây là ví dụ cho cả việc **phân tích syntax hiện đại** và **dùng syntax Java 21 hợp lệ trong tool**.

### 11.4. Khi nào cần kiểm tra guard?

Nếu bạn viết linter phát hiện case thiếu kiểm tra điều kiện, hoặc refactor một nhánh pattern:
- Đọc **pattern label** để biết kiểu/biến.
- Đọc **guard** để biết điều kiện `when` nếu có.
- Đọc **body** theo `CaseKind`.
- Không gom `when` vào nội dung `PatternTree` bằng xử lý chuỗi.

Việc guard có type đúng, biến pattern trong scope nào, có compile thành công hay không là vấn đề **semantic analysis**; `parse()` chỉ cung cấp cây cú pháp.

## 12. Đọc vị trí dòng/cột và đoạn source chính xác

Khi làm code navigation hoặc hiển thị lỗi, `toString()` không đủ để biết vị trí. Dùng **`Trees.getSourcePositions()`** cùng **`CompilationUnitTree.getLineMap()`**.

### 12.1. Vị trí offset

~~~java
SourcePositions positions =
        Trees.instance(task).getSourcePositions();

long start = positions.getStartPosition(unit, caseTree);
long end = positions.getEndPosition(unit, caseTree);
~~~

Đây là **snippet trong compilation task đã parse**, cần import `com.sun.source.util.Trees`, `SourcePositions` và biến `task`, `unit`, `caseTree`. Các offset tính theo đơn vị ký tự của source file. Một vị trí không khả dụng có thể là **`Diagnostic.NOPOS`**; hãy kiểm tra trước khi sử dụng.

### 12.2. Chuyển thành số dòng

~~~java
if (start != Diagnostic.NOPOS && unit.getLineMap() != null) {
    long line = unit.getLineMap().getLineNumber(start);
    System.out.println("case starts at line " + line);
}
~~~

Đây là **snippet**, cần import `javax.tools.Diagnostic`. `LineMap` trả dòng/cột theo source, không phải số byte trong file UTF-8. Nếu bạn cần chính xác một đoạn nguồn cho refactor, hãy giữ **source contents** gốc và dùng phạm vi offset hợp lệ, không cắt từ output `toString()`.

### 12.3. Kiểm chứng thực tế với case colon có yield

Một kiểm tra riêng trên JDK 24 đã phân tích source:

~~~java
int result = switch (n) {
    case 0: yield 10;
    case 1, 2: yield 20;
    default: yield 30;
};
~~~

Kết quả AST (trích thông tin **CaseKind/labels/statements/line** từ công cụ thử nghiệm):

~~~text
kind=STATEMENT labels=0 stmts=1 first=YIELD line=4
kind=STATEMENT labels=1,2 stmts=1 first=YIELD line=5
kind=STATEMENT labels= stmts=1 first=YIELD line=6
~~~

Số dòng thuộc về **file thử nghiệm** cụ thể đã đặt switch trong một class/method, không phải số dòng của snippet rút gọn ngay phía trên. Điểm cần nhớ: **một switch expression hoàn toàn có thể có CaseTree kiểu STATEMENT, với `YieldTree` trong `getStatements()`**.

## 13. Scanner: tránh bỏ sót hoặc đếm trùng

### 13.1. Gọi super để duyệt xuống node con

Trong ví dụ phần 8, mỗi override có:

~~~java
return super.visitSwitchExpression(tree, p);
~~~

Điều này cho phép scanner tiếp tục vào **các node con**, bao gồm case bodies và `yield`. Nếu thay bằng `return null`, bạn có thể **bỏ sót các switch lồng nhau, yield và biểu thức trong body**, tùy thiết kế visitor.

### 13.2. Đừng xử lý case hai lần vô tình

Nếu bạn:
1. Trong `visitSwitchExpression` lặp `tree.getCases()` và tăng `count`.
2. Đồng thời override `visitCase` cũng tăng `count`.
3. Sau đó gọi `super.visitSwitchExpression`.

Một `CaseTree` sẽ bị tính **hai lần**. Hãy chọn:
- **Chiến lược A:** tổng hợp trực tiếp trong `visitSwitch`/`visitSwitchExpression` và để `visitCase` chỉ dùng cho phân tích con cần thiết; hoặc
- **Chiến lược B:** override `visitCase` một lần và lấy thông tin parent bằng `TreePathScanner.getCurrentPath()`, không lặp tăng lại.

### 13.3. Switch lồng nhau

~~~java
switch (a) {
    case 1 -> {
        switch (b) {
            case 2 -> System.out.println("nested");
            default -> System.out.println("other");
        }
    }
    default -> { }
}
~~~

Hai `SwitchTree` nằm lồng nhau. `TreePathScanner` giúp giữ **đường dẫn cha–con**, nên có thể phân biệt case thuộc switch nào. Không dùng một biến global `currentSwitch` rồi quên phục hồi khi thoát khỏi nested switch.

### 13.4. TreeScanner hay TreePathScanner?

| Công cụ | Hữu ích khi nào? |
| --- | --- |
| `TreeScanner<R,P>` | Duyệt nodes và thu thập dữ liệu đơn giản, không cần đường dẫn cha |
| `TreePathScanner<R,P>` | Cần biết **path đến node hiện tại**, sử dụng `Trees.getElement(...)` hoặc thông tin semantic |
| `TreeVisitor` trực tiếp | Muốn kiểm soát sâu mọi node mà không nhờ scanner mặc định |

Ví dụ bài chọn `TreePathScanner` vì phù hợp mở rộng sang tool phân tích mã nhiều file và lồng nhau.

## 14. AST parser không giống semantic checker

### 14.1. parse() chỉ đọc cấu trúc

`JavacTask.parse()` xây AST từ source; nó không tự xác nhận đầy đủ:
- Kiểu selector của switch hợp lệ hay không.
- Các case constant có trùng giá trị hay không.
- Pattern bị che khuất/dominated hoặc có exhaustive coverage.
- Biểu thức `yield` có type phù hợp với switch expression.
- Biến pattern đang ở đúng scope hay không.
- Constant folding của một case expression dẫn tới giá trị nào.

Muốn quyết định những vấn đề ngữ nghĩa, gọi `analyze()` trong một compilation task phù hợp và sử dụng `Trees`/`TypeMirror`/`Element` cùng diagnostics khi cần. Không viết linter khẳng định “switch đã compile thành công” chỉ vì `parse()` trả về một `CompilationUnitTree`.

### 14.2. Thu thập và kiểm tra diagnostics

Một hướng cấu hình compiler:

~~~java
DiagnosticCollector<JavaFileObject> diagnostics =
        new DiagnosticCollector<>();

JavaCompiler.CompilationTask compilation =
        compiler.getTask(
                null, fileManager, diagnostics, options, null, sources);

JavacTask task = (JavacTask) compilation;
Iterable<? extends CompilationUnitTree> units = task.parse();
~~~

Đây là **snippet**, các biến `compiler`, `fileManager`, `options`, `sources` cần chuẩn bị và import `javax.tools.DiagnosticCollector`/`JavaFileObject`. Dùng diagnostics để kiểm tra lỗi và xác định source locations.

**Lưu ý:** Nếu phân tích code có nhiều lỗi, `javac` có thể tạo `ErroneousTree` hoặc thông tin không đầy đủ. Một tool production phải **đối xử thận trọng** với tree thiếu/hỏng, không ném NPE hoặc tạo refactor sai.

### 14.3. Không dùng regex để thay parser

Một regex tìm `case .* ->` rất dễ nhầm:
- Chuỗi `"case 1 ->"` trong string literal.
- Comment.
- Switch lồng nhau.
- Pattern guard nhiều biểu thức.
- Block nhiều dòng.
- Cú pháp `case null, default`.
- Những ký tự xuống dòng/Unicode escapes.

Compiler AST đã giải quyết một phần lớn khó khăn cú pháp. Khi cần sửa source mà bảo toàn comment và whitespace, có thể kết hợp **AST + source ranges**, nhưng vẫn cần cơ chế rewrite/refactor cẩn thận.

## 15. Các lỗi thường gặp khi đọc CaseTree

| Sai lầm | Điều có thể xảy ra | Cách đúng |
| --- | --- | --- |
| Chỉ override `visitSwitch` | Không thấy switch expression | Override cả `visitSwitchExpression` |
| Coi mọi case là `RULE` | `getBody()` trả null cho colon case | Kiểm tra `getCaseKind()` |
| Gọi `getStatements().size()` cho arrow case | `NullPointerException` | Dùng `getBody()` khi RULE |
| Coi mọi RULE body là `ExpressionTree` | Sai với `BlockTree`, `ThrowTree`, `ExpressionStatementTree` | Xem `Tree.Kind` hoặc `instanceof` |
| Coi `yield` luôn là body trực tiếp | Bỏ qua block chứa `YieldTree` | Duyệt con của `BlockTree` |
| Dùng `getExpression()` deprecated | Mất các label sau nhãn thứ nhất | Dùng `getExpressions()` / `getLabels()` |
| Coi `getExpressions().isEmpty()` luôn là default đơn | Không đại diện đủ syntax hiện đại | Java 21+ dùng `getLabels()` |
| Đếm mỗi `case 0: case 1:` như một CaseTree | Sai số node trong colon grouping | Duyệt `getCases()` và kiểm thử |
| Nhầm `case 1, 2 ->` thành hai CaseTree | Đếm sai nhóm cú pháp | Một CaseTree có hai label expressions |
| Dùng `getStatements()` đọc `case -> { ... }` | Không thấy statements trong block | `getBody()` rồi cast `BlockTree` nếu phù hợp |
| Coi AST là kết quả đánh giá biểu thức hằng | Chẩn đoán sai giá trị case | Kết hợp semantic analysis |
| Gọi `Tree.toString()` rồi dùng regex | Dễ sai về comment/format/nested constructs | Duyệt typed nodes và source positions |
| Sử dụng `getLabels()` trong mã `--release 17` | API preview/khác phiên bản; không ổn định cho target cũ | Dùng Java 21+ ổn định hoặc `getExpressions()` cho mã Java17 cổ điển |
| Coi `getGuard()` là một label | Nhầm số nhãn và điều kiện `when` | Đọc guard riêng |
| Không xét `Diagnostic.NOPOS` | Sai offset, có thể crash khi slice source | Kiểm tra tính hợp lệ vị trí |
| Parse xong là coi source hợp lệ | Bỏ qua lỗi type, domination, exhaustiveness | Kiểm tra diagnostics và semantic analysis |
| Tự dùng `com.sun.tools.javac.*` implementation internals | Rủi ro không tương thích JDK | Dùng `com.sun.source.*` được tài liệu hóa |
| Chạy tool trên runtime đã loại `jdk.compiler` | `ToolProvider.getSystemJavaCompiler()` có thể null | Chạy bằng JDK hoặc runtime chứa module compiler |

## 16. Trường hợp Java 14 và thay đổi của ngôn ngữ qua thời gian

### 16.1. Vì sao Java 14 là mốc quan trọng?

**JEP 361** chuẩn hóa switch expressions trong Java 14:
- Switch có thể **trả giá trị**.
- Nhánh `->` giúp tránh fall-through ngoài ý muốn trong mô hình phổ biến.
- Block của switch expression có thể dùng **`yield`** để trả giá trị cho switch.
- Compiler AST có `SwitchExpressionTree` và node `YieldTree`.

Đây **vẫn là kiến thức hiện hành**, không phải feature đã lỗi thời. Cách gọi `yield` cũng cần phân biệt với `return`: `yield` đưa giá trị ra khỏi **switch expression**, trong khi `return` trả khỏi method/lambda tương ứng.

### 16.2. Java 21 mở rộng tập nhãn

**Pattern matching for switch** được chuẩn hóa trong Java 21. AST cần phân biệt:
- Constant case label.
- Pattern case label.
- `default` label.
- Guard `when`.

Trên Java 21+, `CaseTree.getLabels()` và `getGuard()` là cách đọc phù hợp. Đừng dạy cách dùng **preview flags của Java 17** như lựa chọn chuẩn cho dự án hiện đại.

### 16.3. Phần API nào cần tránh?

- **`CaseTree.getExpression()` deprecated:** không xây tool mới phụ thuộc nó.
- Các lớp triển khai nội bộ compiler không được công bố: không dùng để truy xuất member fields chỉ có ở một build.
- Cú pháp pattern switch preview của các JDK cũ: không lấy làm mẫu chính thức.
- Phân tích chuỗi bằng regex thay vì typed AST khi bài toán cần cấu trúc.

Thay vào đó, chọn **mức JDK mục tiêu có chủ đích** và dựa vào Javadoc của chính version đó.

## 17. Bài tập thực hành có đáp án

### Bài 1 — Phân biệt node cha

~~~java
String v = switch (n) {
    case 1 -> "one";
    default -> "other";
};
~~~

**Hỏi:** AST node switch là `SwitchTree` hay `SwitchExpressionTree`?

**Đáp án:** `SwitchExpressionTree` vì switch tạo giá trị được gán cho `v`. Các nhánh con vẫn là `CaseTree`.

### Bài 2 — Hai nhãn trong một case

~~~java
case 1, 2 -> "small";
~~~

**Hỏi:** Có bao nhiêu CaseTree? `getExpressions().size()` bằng bao nhiêu trong Java 17?

**Đáp án:** Một CaseTree; hai expression labels, nên size là **2**.

### Bài 3 — Phần thân rule là gì?

~~~java
case 1 -> {
    yield "one";
}
~~~

**Đáp án:** `getCaseKind() == RULE`; `getBody().getKind() == BLOCK`. `YieldTree` nằm **bên trong block**, không phải body trực tiếp.

### Bài 4 — Colon case và null

~~~java
case 0:
case 1:
    System.out.println("small");
    break;
~~~

**Đáp án:** `CaseTree` cho `case 0:` là `STATEMENT` và có **0 statements** trong ví dụ; `case 1:` có **2 statements**. `getBody() == null` cho cả hai.

### Bài 5 — Lỗi getStatements

~~~java
if (caseTree.getStatements().size() > 0) {
    // ...
}
~~~

**Hỏi:** Vì sao mã dễ crash?

**Đáp án:** Nếu case dùng `->`, `getStatements()` trả `null`. Kiểm tra `getCaseKind()`, sau đó dùng `getBody()` hoặc `getStatements()` tương ứng.

### Bài 6 — Default trên Java 21+

~~~java
case null, default -> "other";
~~~

**Hỏi:** `getLabels()` trả bao nhiêu phần tử và thuộc loại nào?

**Đáp án:** **2**: `ConstantCaseLabelTree` cho `null` và `DefaultCaseLabelTree` cho `default`. Không nên suy luận từ `getExpressions()` rằng đây chỉ là standalone default.

### Bài 7 — Guard có là label thứ hai không?

~~~java
case String s when s.length() > 3 -> "long";
~~~

**Đáp án:** Không. `getLabels()` có **một pattern label**, còn `getGuard()` trả **ExpressionTree** mô tả `s.length() > 3`.

### Bài 8 — Colon case trong switch expression

~~~java
int out = switch (n) {
    case 1: yield 10;
    default: yield 0;
};
~~~

**Đáp án:** Node cha là `SwitchExpressionTree`, mỗi CaseTree có `CaseKind.STATEMENT`, `getStatements()` chứa `YieldTree`. Không thể suy ra `CaseKind.RULE` chỉ từ loại node cha.

### Bài 9 — Kiểm tra lỗi phân tích cú pháp

Bạn gọi `task.parse()` và nhận `CompilationUnitTree`. Có thể tuyên bố code biên dịch thành công, không thiếu case và không trùng case labels không?

**Đáp án:** **Không.** `parse()` cung cấp AST; validation kiểu, exhaustiveness và duplicate constants cần diagnostics/semantic analysis.

### Bài 10 — Đếm label alternatives

Một công cụ đếm số phần tử `case` trong:

~~~java
switch (n) {
    case 1, 2 -> System.out.println("a");
    case 3 -> System.out.println("b");
    default -> System.out.println("c");
}
~~~

**Đáp án:** **3 CaseTree**, nhưng **4 label alternatives** nếu tính `default` là một alternative và `1`, `2`, `3` riêng rẽ. Tool phải xác định nó cần đếm cái nào.

### Bài 11 — Chọn API trên target Java 17

Ứng dụng linter được biên dịch với `--release 17` và chỉ cần đọc các `case` có constant labels truyền thống.

**Đáp án:** `CaseTree.getExpressions()` cùng `getCaseKind()`, `getBody()` và `getStatements()`. Không dùng API Java 21 trong code target Java17.

### Bài 12 — Định vị source

Bạn cần đánh dấu chính xác dòng của `case 3 ->` khi hiển thị diagnostic.

**Đáp án:** `Trees.instance(task).getSourcePositions().getStartPosition(unit, caseTree)` rồi dùng `unit.getLineMap().getLineNumber(start)` khi vị trí hợp lệ và không phải `Diagnostic.NOPOS`.

## 18. Checklist khi viết công cụ phân tích switch

- [ ] Dùng **`jdk.compiler` Compiler Tree API**, không dựa vào compiler implementation internals.
- [ ] Override cả **`visitSwitch`** và **`visitSwitchExpression`** khi cần quét mọi switch.
- [ ] Phân biệt **node cha** với **`CaseKind`** của từng case.
- [ ] Với **RULE**, đọc `getBody()` và kiểm tra kind trước khi cast.
- [ ] Với **STATEMENT**, đọc `getStatements()` và chấp nhận danh sách rỗng.
- [ ] Đọc đầy đủ nhãn biểu thức bằng **`getExpressions()`** cho target Java17.
- [ ] Không dùng **`getExpression()` deprecated**.
- [ ] Với target **Java21+**, dùng **`getLabels()`** để hỗ trợ constant, pattern, null, default.
- [ ] Đọc **`getGuard()`** riêng, không gộp guard thành label.
- [ ] Phân biệt `case 1, 2 ->` với `case 1: case 2:`.
- [ ] Với switch expression, xử lý `YieldTree` cả khi nằm trong `BlockTree` và trong colon case statement list.
- [ ] Có chiến lược scanner **không đếm trùng** và không bỏ sót nested switch.
- [ ] Khi cần sửa source, dùng **SourcePositions/LineMap** và kiểm tra `NOPOS`.
- [ ] Có diagnostics và semantic analysis khi kết luận code hợp lệ hay không.
- [ ] Biên dịch/test tool với **`--release` tương ứng**; không dùng preview syntax làm mặc định.
- [ ] Kiểm thử trên source có `default`, nhiều nhãn, statement rỗng, block, throw, yield, pattern và guard.
- [ ] Không coi `Tree.toString()` là biểu diễn nguyên bản của source hoặc một bộ parser thay thế.
- [ ] Không kết luận một case chắc chắn được thực thi chỉ từ AST; đó là bài toán control-flow/runtime riêng.

## 19. Tóm tắt

**Đọc phần thân và nhãn case** nghĩa là kết hợp đúng các API:

1. **`SwitchTree` / `SwitchExpressionTree`** cho node switch; gọi `getCases()` để lấy các `CaseTree`.
2. **`CaseTree.getCaseKind()`** để phân biệt **RULE (`->`)** và **STATEMENT (`:`)**.
3. **`getBody()`** cho RULE; phần thân có thể là expression, block, statement hoặc throw.
4. **`getStatements()`** cho STATEMENT; danh sách có thể rỗng và có thể chứa `YieldTree` khi node cha là switch expression.
5. **`getExpressions()`** cho biểu thức nhãn theo API Java17; **không dùng `getExpression()` deprecated**.
6. **`getLabels()` và `getGuard()` từ Java21** để xử lý đầy đủ constant/pattern/null/default và `when`.
7. **`TreePathScanner`, `SourcePositions` và diagnostics** để mở rộng từ bài tập thành một tool phân tích source nghiêm túc.

**Tính đúng của linter** đòi hỏi không nhầm số label với số CaseTree, không bỏ sót nhánh `default`, không gọi body API sai CaseKind, và không giả định parse tree tự chứng minh chương trình hợp lệ. Những nguyên tắc này vẫn có giá trị trên các JDK hiện nay.

**Tài liệu chính thức, còn áp dụng:**
- [Oracle Java SE 25 — CaseTree](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/tree/CaseTree.html): `getLabels`, `getGuard`, `getExpressions`, `getBody`, `getStatements`, `getCaseKind`.
- [Oracle Java SE 17 — CaseTree](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/tree/CaseTree.html): API biểu thức nhãn và body phù hợp Java17.
- [Oracle Java SE 25 — SwitchTree](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/tree/SwitchTree.html): switch statement AST.
- [Oracle Java SE 25 — SwitchExpressionTree](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/tree/SwitchExpressionTree.html): switch expression AST.
- [Oracle Java SE 25 — Package com.sun.source.tree](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/tree/package-summary.html): các nhãn và AST node hiện đại.
- [Oracle Java SE 21 — Module jdk.compiler](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/module-summary.html): Compiler Tree API public surface.
- [Oracle Java SE 25 — JavacTask](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/util/JavacTask.html): `parse()` và `analyze()`.
- [Oracle Java SE 25 — SourcePositions](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/util/SourcePositions.html): đọc vị trí AST.
- [OpenJDK JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): tính năng chuẩn hóa từ Java14.
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): pattern switch ổn định Java21.

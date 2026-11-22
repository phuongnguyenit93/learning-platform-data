# TreeVisitor và TreeScanner cho switch expression, yield trong cây cú pháp Java (Java 14+)

## 1. Vì sao cần hiểu cây cú pháp của switch expression?

Trong Java hiện đại, `switch` có thể là **câu lệnh** (`switch statement`) hoặc **biểu thức tạo ra giá trị** (`switch expression`). Bên trong switch expression, `yield` chuyển một giá trị từ nhánh về toàn bộ biểu thức `switch`. Những cấu trúc đó có ý nghĩa đặc biệt khi viết công cụ phân tích mã nguồn, linter, refactoring, trình kiểm tra quy tắc code hoặc plugin compiler.

Xét ví dụ:

```java
int score = switch (level) {
    case 1 -> 10;
    case 2 -> {
        int temporary = 20;
        yield temporary;
    }
    default -> 0;
};
```

Ta có thể muốn hỏi:

- Đoạn mã có bao nhiêu **switch expression**, khác với **switch statement**?
- Nhánh `case 1 -> 10` có tạo một node `YieldTree` không?
- `yield temporary;` xuất hiện ở đâu trong AST?
- Duyệt mọi node con bằng cách nào mà không quên selector, case body, nested expressions?
- Nếu cần phân tích một node đơn lẻ, dùng **`TreeVisitor`** hay **`TreeScanner`**?
- Vì sao có những phương thức visitor mới như `visitSwitchExpression` và `visitYield`?

Các câu hỏi đó thuộc **Java Compiler Tree API** trong module **`jdk.compiler`**, với những interface ở package `com.sun.source.tree` và các visitor tiện ích ở `com.sun.source.util`. Đây là các API còn được duy trì trong JDK hiện đại; không cần truy cập các lớp implementation nội bộ `com.sun.tools.javac.tree.JCTree` cho những tác vụ thông thường.

**Trọng tâm bài:** dùng `TreeVisitor` để phân phối theo kiểu node, dùng `TreeScanner` để đi qua toàn bộ cây, và xử lý đúng **`SwitchExpressionTree`, `YieldTree`, `SwitchTree`, `CaseTree`**.

### Mốc phiên bản, kiến thức còn áp dụng

- **Switch expression và `yield` được chuẩn hóa trong Java 14** theo JEP 361. Chúng đã trải qua preview ở các bản trước, nhưng **hướng dẫn hiện hành không cần `--enable-preview`**.
- API Tree của `jdk.compiler` có `TreeVisitor.visitSwitchExpression(...)`, `visitYield(...)` và các node tương ứng. Chúng tồn tại và được hỗ trợ trong JDK 17, 21, 25.
- Code thực hành ở dưới sử dụng cú pháp/API ổn định, được biên dịch bằng **`javac --release 17`**, đồng thời đã kiểm thử **`--release 14`** trên JDK hiện đại.
- Không dùng cách làm lỗi thời như lấy kết quả switch expression qua `break value;` của giai đoạn preview cũ, hoặc `CaseTree.getExpression()` đã **deprecated**.

## 2. Từ mã Java sang Abstract Syntax Tree (AST)

**Abstract Syntax Tree** là cấu trúc biểu diễn cú pháp của source code bằng các node, mỗi node có loại và quan hệ cha–con.

Ví dụ với:

```java
int answer = switch (x) {
    case 1 -> 10;
    case 2 -> {
        yield x * 2;
    }
    default -> -1;
};
```

Sơ đồ giản lược:

```text
VariableTree: answer
└── SwitchExpressionTree  [Kind.SWITCH_EXPRESSION]
    ├── selector: IdentifierTree(x)
    ├── CaseTree [CaseKind.RULE]
    │   ├── label: 1
    │   └── body: LiteralTree(10)
    ├── CaseTree [CaseKind.RULE]
    │   ├── label: 2
    │   └── body: BlockTree
    │       └── YieldTree [Kind.YIELD]
    │           └── value: BinaryTree(x * 2)
    └── CaseTree [CaseKind.RULE]
        ├── label: default
        └── body: UnaryTree(-1)
```

Sơ đồ chỉ hiển thị những node liên quan để học, không phải bản dump đầy đủ cho mọi compiler/JDK. Điều quan trọng là:

1. **`SwitchExpressionTree`** biểu diễn **toàn bộ** biểu thức `switch (...) { ... }`.
2. **`getExpression()`** của nó là **selector** (ở đây `x`), không phải giá trị cuối cùng của switch.
3. **`getCases()`** là danh sách `CaseTree`.
4. Case có dạng `-> expression`: body chính là **expression tree**, không có câu lệnh `yield` tường minh.
5. Case có dạng `-> { ... yield expression; }`: body là `BlockTree`, bên trong có **`YieldTree`**.
6. `YieldTree.getValue()` cho ra **biểu thức** đứng sau từ khóa `yield`.

### Mô hình tổng quan của các loại node

| Kiểu AST | Là gì? | `getKind()` | Phương thức visitor |
| --- | --- | --- | --- |
| `SwitchExpressionTree` | `switch` **trả về giá trị** | `Tree.Kind.SWITCH_EXPRESSION` | `visitSwitchExpression` |
| `SwitchTree` | `switch` **câu lệnh** | `Tree.Kind.SWITCH` | `visitSwitch` |
| `CaseTree` | Một nhánh `case`/`default` | `Tree.Kind.CASE` | `visitCase` |
| `YieldTree` | Câu lệnh `yield expression;` | `Tree.Kind.YIELD` | `visitYield` |
| `BlockTree` | Khối lệnh `{ ... }` | `Tree.Kind.BLOCK` | `visitBlock` |
| `BreakTree` | Câu lệnh `break;` | `Tree.Kind.BREAK` | `visitBreak` |
| `ReturnTree` | Câu lệnh `return ...;` | `Tree.Kind.RETURN` | `visitReturn` |

**Không gộp `SwitchExpressionTree` và `SwitchTree` thành cùng một loại chỉ vì đều viết từ khóa `switch`**. Nếu linter chỉ override `visitSwitch(SwitchTree, ...)`, nó **bỏ sót switch expression**.

## 3. `TreeVisitor<R, P>`: visitor dispatch theo loại node

Interface:

```java
com.sun.source.tree.TreeVisitor<R, P>
```

cung cấp một tập phương thức `visitXxx(node, p)`. Khi gọi:

```java
R result = node.accept(visitor, parameter);
```

node tự chuyển điều khiển tới phương thức visitor tương ứng với **loại thực tế của node**. Đây là mô hình *visitor pattern*.

Hai tham số generic:

- **`R`**: kiểu kết quả trả về từ một lần thăm. Nếu không cần kết quả, dùng `Void`.
- **`P`**: kiểu tham số bổ sung truyền qua các lần thăm; nếu không có, dùng `Void`.

Ví dụ kiểu trả về chuỗi:

```java
TreeVisitor<String, Void> classifier = ...;
String description = node.accept(classifier, null);
```

Đây là **snippet**: `node` và `classifier` phải được tạo trước. Cách viết này tiện khi muốn biết một node là switch expression hay switch statement mà **chưa cần đi qua tất cả descendants**.

### Hai phương thức riêng của Java 14+

```java
R visitSwitchExpression(SwitchExpressionTree node, P p)
R visitYield(YieldTree node, P p)
```

Bên cạnh đó đã có `visitSwitch(SwitchTree node, P p)` cho switch statement.

**Cẩn thận với khả năng phát triển của Java:** Javadoc `TreeVisitor` cảnh báo **các loại node mới có thể được bổ sung trong các phiên bản Java tương lai**, làm một class **implements TreeVisitor trực tiếp** trở nên không còn tương thích source khi nâng JDK, vì phải triển khai thêm phương thức mới.

Với code phân tích thường ngày, nên:

- Kế thừa **`SimpleTreeVisitor<R,P>`** khi chỉ cần dispatch và xử lý một số loại node.
- Kế thừa **`TreeScanner<R,P>`** khi cần **duyệt toàn bộ subtree**.
- Kế thừa **`TreePathScanner<R,P>`** khi phải biết node cha/đường đi của node hiện tại.
- Chỉ implement `TreeVisitor` trực tiếp nếu có lý do cụ thể và sẵn sàng bảo trì đủ phương thức khi JDK bổ sung kiểu node.

### `SimpleTreeVisitor` không tự là một scanner toàn cây

Ví dụ:

```java
TreeVisitor<String, Void> classifier =
        new SimpleTreeVisitor<String, Void>("other") {
    @Override
    public String visitSwitchExpression(
            SwitchExpressionTree node, Void p) {
        return "expression";
    }

    @Override
    public String visitSwitch(SwitchTree node, Void p) {
        return "statement";
    }
};
```

Đây là **snippet** cần các `import` ở `com.sun.source.tree` và `com.sun.source.util`. Với một node `SwitchExpressionTree`, `node.accept(classifier, null)` trả `"expression"`. Với `SwitchTree`, nó trả `"statement"`. Với những node không được override, constructor `SimpleTreeVisitor("other")` cung cấp giá trị mặc định.

**`SimpleTreeVisitor` không tự tìm mọi switch trong file nguồn.** Để đi từ `CompilationUnitTree` xuống class, method, block, expression và yield, dùng `TreeScanner`.

## 4. `TreeScanner<R,P>`: tự động duyệt xuống các node con

`com.sun.source.util.TreeScanner<R,P>` là implementation của `TreeVisitor`, được thiết kế **duyệt các node con**.

Cách dùng:

```java
class CountingScanner extends TreeScanner<Void, Void> {
    int switchExpressions;

    @Override
    public Void visitSwitchExpression(
            SwitchExpressionTree node, Void unused) {
        switchExpressions++;
        return super.visitSwitchExpression(node, unused);
    }
}
```

Ví dụ này là snippet trong file đã có các import. Dòng `super.visitSwitchExpression(node, unused)` **rất quan trọng**: nó cho phép scanner tiếp tục duyệt **selector và các case con**, bao gồm những switch expression lồng nhau, yield bên trong block, các biểu thức con.

Sau khi tạo scanner:

```java
CountingScanner scanner = new CountingScanner();
scanner.scan(compilationUnit, null);
System.out.println(scanner.switchExpressions);
```

`compilationUnit` phải là `CompilationUnitTree` lấy từ Java compiler. Cách dùng trên đếm toàn bộ node `SWITCH_EXPRESSION` trong cây được đưa vào, không chỉ switch xuất hiện ở một vị trí đã biết trước.

### Nếu quên `super.visitXxx(...)` sẽ xảy ra gì?

Giả sử:

```java
@Override
public Void visitSwitchExpression(
        SwitchExpressionTree node, Void p) {
    switchExpressions++;
    return null; // Không duyệt descendants!
}
```

Đây là snippet minh họa **khi cố ý chặn traversal**. Scanner sẽ nhận biết switch expression tại node hiện tại nhưng **không tự đi xuống các case và yield bên trong nó**. Nó cũng sẽ bỏ lỡ một switch expression lồng trong một nhánh case.

Đôi khi không duyệt con là chủ đích (ví dụ bỏ qua subtree không phù hợp); nhưng nếu nhiệm vụ là **đếm tất cả** thì phải gọi `super` hoặc tự scan các con đầy đủ.

### `TreeScanner` trả về giá trị thế nào?

Theo Javadoc, các phương thức thăm mặc định thường:

- Duyệt node con theo **thứ tự từ trái sang phải**.
- Nếu có nhiều con, kết hợp kết quả qua `reduce(R r1, R r2)`.
- `reduce` mặc định thường giữ kết quả của **node con được scan sau cùng**, không tự cộng dồn mọi số đếm.

Vì vậy, **đừng chỉ override `visitYield` để `return 1` rồi nghĩ `scanner.scan(unit,null)` tự trả tổng yield**. Với yêu cầu đếm, có hai cách:

1. **Dùng biến đếm trong scanner** (như chương trình phần 7) và `TreeScanner<Void,Void>`.
2. Hoặc thiết kế `TreeScanner<Integer,Void>` với `visitYield`, `reduce` và giá trị mặc định được xử lý nhất quán để cộng toàn cây.

Cách thứ nhất minh bạch và ít lỗi hơn cho người mới dùng Compiler Tree API.

## 5. `SwitchExpressionTree` và `SwitchTree`: khác nhau trong AST

Có hai dạng source hợp lệ:

```java
// Switch expression: tạo một giá trị.
int code = switch (x) {
    case 1 -> 10;
    default -> 0;
};

// Switch statement: thực hiện hành động.
switch (x) {
    case 1 -> System.out.println("one");
    default -> System.out.println("other");
}
```

Đây là **snippet bên trong một method có biến `x`**. Trước mắt hãy chú ý: **dùng `->` không tự biến một switch statement thành switch expression**. Phải nhìn **vai trò cú pháp của toàn bộ switch**.

| Tiêu chí | `SwitchExpressionTree` | `SwitchTree` |
| --- | --- | --- |
| Gốc cú pháp | `return switch (...) { ... };`, `var v = switch (...) ...` | `switch (...) { ... }` như một statement |
| Interface cha | `ExpressionTree` | `StatementTree` |
| `Tree.Kind` | `SWITCH_EXPRESSION` | `SWITCH` |
| Visitor | `visitSwitchExpression(...)` | `visitSwitch(...)` |
| Selector | `getExpression()` | `getExpression()` |
| Cases | `getCases()` | `getCases()` |
| Dùng `yield` | Có, để trả giá trị từ nhánh có block/statement group | Không, bản thân switch statement không phải yield target |
| Dùng `break;` | Không dùng `break` để tạo giá trị | Có thể dùng `break;` theo cú pháp switch statement |

**`yield` chuyển giá trị tới switch expression bao quanh gần nhất** (theo các quy tắc điều khiển dòng của JLS), không có nghĩa nó là `return` của method. Một switch expression có thể nằm trong `return`, trong assignment hoặc trong phép tính lớn hơn; `yield` chỉ hoàn tất **biểu thức switch đó**.

### Hai API lấy dữ liệu của switch expression

```java
ExpressionTree selector = node.getExpression();
List<? extends CaseTree> cases = node.getCases();
```

Snippet giả định `node` có kiểu `SwitchExpressionTree`, đã import `List` và các tree types.

- `getExpression()` là biểu thức trong ngoặc `switch(selector)`.
- `getCases()` là danh sách `CaseTree`, chưa phải “danh sách các giá trị kết quả”.
- Để biết một case trả giá trị gì, phải xét **`CaseTree.getBody()`**, `getStatements()`, `YieldTree.getValue()` và cấu trúc biểu thức con; không thể chỉ gọi `getCases().size()` rồi suy ra kết quả runtime.

**AST phản ánh cú pháp**. Nó không tự thực thi selector, không tự biết giá trị runtime của biến, không tự chạy branch và không tính kết quả cuối khi code sử dụng biến/hàm.

## 6. `CaseTree`: phân biệt nhánh `->` và nhánh `:`

`CaseTree` có phương thức:

```java
CaseTree.CaseKind getCaseKind()
Tree getBody()
List<? extends StatementTree> getStatements()
```

**Đừng nhầm `CaseKind.STATEMENT` với `SwitchTree`**: `CaseKind.STATEMENT` nghĩa là **case có nhãn dấu hai chấm `:`**, và nó có thể xuất hiện **ngay trong một switch expression**.

### 6.1. `CaseKind.RULE`: nhánh arrow `->`

Ví dụ:

```java
return switch (x) {
    case 1 -> 10;
    case 2 -> {
        yield x * 2;
    }
    default -> -1;
};
```

Ba case đều có:

```java
caseTree.getCaseKind() == CaseTree.CaseKind.RULE
```

Nhưng kết quả của `getBody()` là những loại node khác nhau:

- `case 1 -> 10`: **`LiteralTree`**, thuộc `ExpressionTree`.
- `case 2 -> { yield x * 2; }`: **`BlockTree`**, chứa `YieldTree`.
- `default -> -1`: một **`UnaryTree`**, thuộc `ExpressionTree`.

Với rule case, `getStatements()` trả **`null`**, nên code sau là lỗi:

```java
// Anti-pattern: ném NullPointerException với RULE case.
for (StatementTree statement : caseTree.getStatements()) {
    ...
}
```

Cách đúng là kiểm tra `getCaseKind()` và duyệt `getBody()` khi là `RULE`.

### 6.2. `CaseKind.STATEMENT`: nhánh colon `:`

Ví dụ:

```java
return switch (x) {
    case 1:
        yield "one";
    default:
        yield "other";
};
```

Đây vẫn là **switch expression**, dù nhánh case dùng dấu `:`. Với `CaseKind.STATEMENT`:

- `getStatements()` trả danh sách statement cho case đó, ví dụ một `YieldTree`.
- `getBody()` trả **`null`**.
- Code phải hiểu cấu trúc **statement group** và quy tắc hoàn thành của switch expression. Không được quy mỗi case `:` thành switch statement.

Ví dụ xử lý hai dạng:

```java
@Override
public Void visitCase(CaseTree node, Void p) {
    if (node.getCaseKind() == CaseTree.CaseKind.RULE) {
        Tree body = node.getBody();          // Có thể là biểu thức, block...
        // Xử lý tùy loại body.
    } else {
        List<? extends StatementTree> list = node.getStatements();
        // Xử lý các statement trong nhóm này.
    }
    return super.visitCase(node, p);        // Vẫn scan mọi node con.
}
```

Đây là **snippet**, cần import `Tree`, `StatementTree`, `CaseTree`, `List`. Chỉ để giải thích dạng API; với mục tiêu đếm, `TreeScanner` tự duyệt con mà không cần bạn gọi `scan` thủ công từng member.

### Nhãn case trong Java hiện đại

- `CaseTree.getExpressions()` trả các **constant case label expressions** theo API; với default case, danh sách có thể rỗng. Nó phù hợp với nhiều case cổ điển (như `case 1, 2`), nhưng không bao quát mọi loại nhãn pattern hiện đại.
- `CaseTree.getExpression()` **đã deprecated**: không nên dùng làm lối truy cập mới, vì có thể có nhiều labels và chỉ trả nhãn đầu tiên.
- Từ **Java 21**, API `CaseTree.getLabels()` và các interface `CaseLabelTree` cho phép xử lý nhiều dạng nhãn modern switch, bao gồm pattern/default, **không phải API ổn định cho chương trình phải tương thích Java 14/17**.
- Với công cụ phân tích Java 21+ pattern switch, nên dựa vào `getLabels()` khi target JDK hỗ trợ. Với bài Java 14/17 này, các ví dụ tập trung switch với hằng số và không dùng API preview.

## 7. `YieldTree`: khi nào có node `yield`?

Một `YieldTree` biểu diễn chính câu lệnh:

```java
yield expression;
```

API chính:

```java
ExpressionTree getValue()
```

**Ví dụ:**

```java
case 2 -> {
    int twice = x * 2;
    yield twice;
}
```

Trong AST, `yield twice;` tạo **`YieldTree`**; `getValue()` trả một `IdentifierTree` cho `twice`, **không** trả block và không trả kết quả runtime của `twice`.

Ngược lại:

```java
case 1 -> 10;
```

là **một expression body trực tiếp**, **không cần `yield`**, nên **không có `YieldTree` ở case này**. Đây là lý do sai lầm khi đếm “mỗi rule case là một yield”.

### Không phải các statement gần giống đều tạo `YieldTree`

| Cú pháp | AST node | Ý nghĩa |
| --- | --- | --- |
| `yield x;` | `YieldTree` | Đưa `x` làm giá trị của enclosing switch expression |
| `return x;` | `ReturnTree` | Trả khỏi method/lambda tương ứng, khác semantics |
| `break;` | `BreakTree` | Kết thúc statement target, không tạo giá trị switch expression |
| `throw new RuntimeException();` | `ThrowTree` | Thoát bằng exception |
| `case 1 -> 10` | Expression tree trong `CaseTree.getBody()` | Rule expression không có yield statement |
| `case 2 -> { yield x; }` | `BlockTree` chứa `YieldTree` | Block cần yield để tạo giá trị |

**Không dùng cú pháp preview cũ `break 123;`** để trả giá trị switch expression. Đây là ý tưởng từng xuất hiện trước khi Java 14 chuẩn hóa `yield`, không phải cú pháp hiện hành.

### Thăm `yield` trong scanner

```java
@Override
public Void visitYield(YieldTree node, Void p) {
    System.out.println("yield expression: " + node.getValue());
    return super.visitYield(node, p);
}
```

Snippet này in **cấu trúc cú pháp** qua `toString()`, không phải kết quả tính toán thực tế. Gọi `super.visitYield` để tiếp tục duyệt **biểu thức bên trong yield**, vì bản thân biểu thức có thể chứa node đáng quan tâm.

### Tránh nhầm biểu thức con với giá trị của toàn bộ switch

Một switch expression có thể chứa:

```java
int answer = switch (x) {
    case 1 -> 10;
    default -> {
        int value = compute();
        yield value;
    }
};
```

`YieldTree.getValue()` cho ra AST của identifier `value`. Nó **không tự resolve symbol hoặc tính giá trị của method `compute()`**. Nếu công cụ cần biết type, symbol hoặc flow analysis, phải dùng compiler semantic phase/`Trees`/`TreePath` và những API tương ứng; chỉ dùng `TreeScanner` trên cú pháp là chưa đủ.

## 8. Chương trình Java 17+ đầy đủ: phân loại bằng TreeVisitor, đếm bằng TreeScanner

Chương trình dưới đây **không sửa source file của dự án**. Nó tạo một chuỗi Java code trong bộ nhớ rồi nhờ Java Compiler API parse thành `CompilationUnitTree`.

Trong source mẫu có:

1. Một **switch expression** có rule body trực tiếp (`case 1 -> 10`) và hai block chứa `yield`.
2. Một **switch expression** dùng colon statement groups với hai câu `yield`.
3. Một **switch statement** dùng arrow rules để in ra console nếu được chạy (nhưng chương trình **chỉ parse**, không thực thi nó).

Sau khi quét, scanner phải đếm **2 switch expressions, 1 switch statement, 4 yield nodes, 5 rule cases, 2 colon cases và 1 arrow expression body**.

Tạo tệp **`SwitchTreeScannerDemo.java`**:

```java
import com.sun.source.tree.*;
import com.sun.source.util.JavacTask;
import com.sun.source.util.SimpleTreeVisitor;
import com.sun.source.util.TreeScanner;
import java.net.URI;
import java.util.ArrayList;
import java.util.List;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.ToolProvider;

public class SwitchTreeScannerDemo {
    static class Counter extends TreeScanner<Void, Void> {
        int expressions;
        int statements;
        int yields;
        int rules;
        int statementGroups;
        int arrowExpressionBodies;
        List<String> descriptions = new ArrayList<>();

        // TreeVisitor trực tiếp chỉ phân loại node được truyền vào.
        TreeVisitor<String, Void> dispatcher =
                new SimpleTreeVisitor<String, Void>("other") {
                    @Override
                    public String visitSwitchExpression(
                            SwitchExpressionTree node, Void p) {
                        return "expr:" + node.getCases().size();
                    }
                    @Override
                    public String visitSwitch(SwitchTree node, Void p) {
                        return "stmt:" + node.getCases().size();
                    }
                };

        @Override
        public Void visitSwitchExpression(
                SwitchExpressionTree node, Void p) {
            expressions++;
            descriptions.add(node.accept(dispatcher, null));
            return super.visitSwitchExpression(node, p);
        }

        @Override
        public Void visitSwitch(SwitchTree node, Void p) {
            statements++;
            descriptions.add(node.accept(dispatcher, null));
            return super.visitSwitch(node, p);
        }

        @Override
        public Void visitCase(CaseTree node, Void p) {
            if (node.getCaseKind() == CaseTree.CaseKind.RULE) {
                rules++;
                if (node.getBody() instanceof ExpressionTree) {
                    arrowExpressionBodies++;
                }
            } else {
                statementGroups++;
            }
            return super.visitCase(node, p);
        }

        @Override
        public Void visitYield(YieldTree node, Void p) {
            yields++;
            return super.visitYield(node, p);
        }
    }

    public static void main(String[] args) throws Exception {
        String source = String.join("\n",
            "class Sample {",
            "  int classify(int x) {",
            "    return switch (x) {",
            "      case 1 -> 10;",
            "      case 2 -> { int twice = x * 2; yield twice; }",
            "      default -> { yield -1; }",
            "    };",
            "  }",
            "  String word(int x) {",
            "    return switch (x) {",
            "      case 1: yield \"one\";",
            "      default: yield \"other\";",
            "    };",
            "  }",
            "  void announce(int x) {",
            "    switch (x) {",
            "      case 1 -> System.out.println(\"one\");",
            "      default -> System.out.println(\"other\");",
            "    }",
            "  }",
            "}"
        );

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Run with a JDK");
        }

        // File Java nằm trong bộ nhớ, không cần Sample.java trên đĩa.
        JavaFileObject file = new SimpleJavaFileObject(
                URI.create("string:///Sample.java"),
                JavaFileObject.Kind.SOURCE) {
            @Override
            public CharSequence getCharContent(boolean ignoreErrors) {
                return source;
            }
        };

        JavacTask task = (JavacTask) compiler.getTask(
                null, null, null,
                List.of("--release", "17", "-proc:none"),
                null, List.of(file));

        Counter counter = new Counter();
        for (CompilationUnitTree unit : task.parse()) {
            counter.scan(unit, null);
        }

        if (counter.expressions != 2 || counter.statements != 1 ||
                counter.yields != 4 || counter.rules != 5 ||
                counter.statementGroups != 2 ||
                counter.arrowExpressionBodies != 1) {
            throw new AssertionError(
                    "Unexpected AST shape: " + counter.descriptions);
        }

        System.out.println("switchExpressions=" + counter.expressions);
        System.out.println("switchStatements=" + counter.statements);
        System.out.println("yieldNodes=" + counter.yields);
        System.out.println("ruleCases=" + counter.rules);
        System.out.println("statementCases=" + counter.statementGroups);
        System.out.println(
                "arrowExpressionBodies=" + counter.arrowExpressionBodies);
        System.out.println("dispatch=" + counter.descriptions);
    }
}
```

### 8.1. Biên dịch và chạy

Sử dụng JDK 17+ (JDK đầy đủ, bao gồm `jdk.compiler`):

```bash
javac --release 17 -encoding UTF-8 SwitchTreeScannerDemo.java
java --add-modules jdk.compiler SwitchTreeScannerDemo
```

**Output chính xác đã kiểm thử trên Windows JDK 24:**

```text
switchExpressions=2
switchStatements=1
yieldNodes=4
ruleCases=5
statementCases=2
arrowExpressionBodies=1
dispatch=[expr:3, expr:2, stmt:2]
```

Có thể biên dịch cùng source bằng:

```bash
javac --release 14 -encoding UTF-8 SwitchTreeScannerDemo.java
```

**Kết quả kiểm thử:** build với `--release 14` cũng thành công trên JDK 24. Điều này phù hợp với tính năng và API AST đã được chuẩn hóa từ Java 14; không cần bật preview flag. Chương trình chạy ở JDK thực tế có `jdk.compiler`, không phụ thuộc một JRE tối giản không chứa compiler.

### 8.2. Vì sao dùng `JavaCompiler` và `JavacTask.parse()`?

`ToolProvider.getSystemJavaCompiler()` lấy compiler có sẵn trong JDK. `SimpleJavaFileObject` giữ source trong bộ nhớ qua method `getCharContent(...)`. `getTask(...)` tạo task, sau đó ép về `JavacTask` để gọi `parse()`.

`parse()` trả về một hoặc nhiều **`CompilationUnitTree`**; mỗi unit là gốc cây cú pháp cho một file Java. Scanner bắt đầu bằng `counter.scan(unit, null)` rồi tự đi sâu xuống tất cả descendants.

**Chương trình này chỉ parse source**, không compile class `Sample`, không thực thi `announce` và không tải class `Sample` vào JVM. Các dòng `System.out.println("one")` bên trong chuỗi source mẫu là **cú pháp được parse**, không xuất hiện ở stdout của demo AST.

**Giới hạn:** `parse()` không đồng nghĩa đã hoàn tất **type checking, symbol resolution và semantic analysis**. Nếu triển khai linter thực tế, dùng `DiagnosticCollector` để kiểm tra parse/compile diagnostics và cân nhắc `task.analyze()`, `Trees` hoặc các API có dữ liệu semantic khi cần. Với ví dụ này, source được thiết kế hợp lệ và số node được kiểm tra bằng assertion.

### 8.3. Vì sao `TreeVisitor` trả `[expr:3, expr:2, stmt:2]`?

Trong `visitSwitchExpression` của scanner:

```java
descriptions.add(node.accept(dispatcher, null));
```

`accept` sẽ gọi `dispatcher.visitSwitchExpression(node, null)`. Trong `visitSwitch`, nó gọi `dispatcher.visitSwitch(node, null)`. Mỗi hàm đọc `node.getCases().size()`:

- Switch expression `classify`: **3** cases.
- Switch expression `word`: **2** cases.
- Switch statement `announce`: **2** cases.

`SimpleTreeVisitor` ở đây **phân loại node hiện tại**, không duyệt các child case. Chính `TreeScanner` bên ngoài chịu trách nhiệm tìm các node trong source file.

### 8.4. Vì sao có `4` yield nodes?

- `classify`: `case 2 -> { ... yield twice; }` có **1 YieldTree**.
- `classify`: `default -> { yield -1; }` có **1 YieldTree**.
- `word`: `case 1: yield "one";` có **1 YieldTree**.
- `word`: `default: yield "other";` có **1 YieldTree**.
- `classify`: `case 1 -> 10;` **không** tạo `YieldTree`.
- `announce` là switch statement; không có `yield`.

Tổng cộng **4**, không phải 7 (số case) và không phải 2 (số switch expressions). Đó là lý do cần đi tới **`YieldTree` tường minh** thay vì suy luận từ số nhánh `case`.

### 8.5. Vì sao `ruleCases=5` và `statementCases=2`?

- `classify` có 3 case arrow `->` → 3 `RULE`.
- `word` có 2 case colon `:` → 2 `STATEMENT`.
- `announce` có 2 case arrow `->` → 2 `RULE`.

Vì vậy `RULE = 3 + 2 = 5`, còn `STATEMENT = 2`.

**Lưu ý:** `statementCases` trong code là **số `CaseKind.STATEMENT`**, không phải số `SwitchTree`. Sự khác biệt này thường gây nhầm lẫn khi viết AST analyzer.

### 8.6. Vì sao chỉ có `arrowExpressionBodies=1`?

Trong code:

```java
if (node.getBody() instanceof ExpressionTree) {
    arrowExpressionBodies++;
}
```

Các loại body:

- `classify: case 1 -> 10`: `LiteralTree` là **`ExpressionTree`** → tăng 1.
- `classify: case 2 -> { ... }`: `BlockTree` → không tăng.
- `classify: default -> { ... }`: `BlockTree` → không tăng.
- `announce: case 1 -> System.out.println("one")`: body là **statement expression** dạng `ExpressionStatementTree`, không phải `ExpressionTree` trực tiếp → không tăng.
- `announce: default -> System.out.println("other")`: cùng dạng `ExpressionStatementTree` → không tăng.

Điều này cho thấy **arrow rule không mặc định có body loại ExpressionTree**. Nó có thể là biểu thức, statement, block hoặc throw statement tùy ngữ cảnh. Khi phân tích cần dùng **`instanceof` với type AST** hoặc `getKind()`, không cast bừa.

## 9. `TreeScanner` với nested switch expressions: tránh bỏ sót và đếm trùng

Ví dụ một switch expression nằm trong case của switch expression khác:

```java
int result = switch (x) {
    case 1 -> switch (x + 1) {
        case 2 -> 22;
        default -> 0;
    };
    default -> 99;
};
```

Đây là snippet trong một method có biến `x`. Nếu scanner override `visitSwitchExpression` và luôn gọi `super.visitSwitchExpression`, nó sẽ nhìn thấy:

- Một **switch expression ngoài**.
- Một **switch expression trong** nằm trong body của `case 1`.

**Hai node switch expression**, không phải một. Nếu quên gọi `super` cho node ngoài, scanner sẽ không duyệt vào switch con.

### Đếm yield cho đúng switch expression

Một scanner đếm tổng `YieldTree` toàn unit là đơn giản. Nhưng nếu muốn báo **mỗi switch expression có bao nhiêu yield tương ứng**, không được lấy mọi `yield` tìm thấy trong subtree của switch ngoài rồi tự khẳng định chúng đều trả giá trị cho switch ngoài.

Nguyên nhân: một switch expression có thể **lồng trong** switch expression khác; `yield` thuộc **switch expression đích gần nhất theo JLS**. Với linter thực, bạn cần **quan hệ parent–child/AST path** để xác định yield target.

Khi đó cân nhắc **`TreePathScanner<R,P>`**, kế thừa `TreeScanner` và duy trì `TreePath` tới node hiện tại. Trong `visitYield` có thể đi dọc `getCurrentPath().getParentPath()` để tìm `SwitchExpressionTree` bao quanh phù hợp.

Ý tưởng tối giản:

```java
// Snippet bên trong subclass của TreePathScanner<Void, Void>.
@Override
public Void visitYield(YieldTree node, Void p) {
    TreePath parent = getCurrentPath().getParentPath();
    while (parent != null) {
        if (parent.getLeaf() instanceof SwitchExpressionTree target) {
            // target là switch expression tổ tiên gần nhất.
            recordYieldFor(target, node.getValue());
            break;
        }
        parent = parent.getParentPath();
    }
    return super.visitYield(node, p);
}
```

Đây là **snippet minh họa**, cần `recordYieldFor` được định nghĩa và import `TreePath`, `TreePathScanner`. Nó cho thấy lý do sử dụng parent path; không phải một class có thể biên dịch độc lập. **`TreePathScanner.getCurrentPath()` chỉ hoạt động đúng khi scan được khởi đầu từ một lời gọi `scan(...)` hợp lệ**, không được khởi tạo path bằng việc gọi trực tiếp `visitYield` tùy tiện.

Nếu muốn phân tích tính hợp lệ của `yield` qua method/lambda boundary, phải tuân theo JLS và dùng diagnostic/semantic analysis phù hợp; parent walk chỉ là bước định vị cấu trúc.

## 10. Cách lấy vị trí dòng/cột của switch và yield

Một công cụ phân tích mã nguồn thường muốn báo:

```text
Sample.java:12:5 — switch expression contains a yield statement
```

`TreeScanner` chỉ đi qua AST, không tự giữ vị trí dòng/cột. API hỗ trợ:

- `com.sun.source.util.Trees`: cầu nối tới AST, source positions, type/symbol thông qua compiler task phù hợp.
- `com.sun.source.util.SourcePositions`: tìm offset `getStartPosition(unit, tree)` và `getEndPosition(unit, tree)`.
- `CompilationUnitTree.getLineMap()`: chuyển offset source thành số dòng/cột.
- `TreePathScanner`: lấy path nếu cần biết context node tại thời điểm quét.

Snippet minh họa khi đã có `CompilationUnitTree unit` và `Trees trees`:

```java
long offset = trees.getSourcePositions()
        .getStartPosition(unit, yieldNode);

if (offset >= 0) {
    long line = unit.getLineMap().getLineNumber(offset);
    long column = unit.getLineMap().getColumnNumber(offset);
    System.out.println(line + ":" + column);
}
```

Đoạn này **không độc lập** vì `trees` và `yieldNode` phải được lấy trong chương trình phân tích. Nó không biến `yieldNode` thành một statement được thực thi; mục tiêu là ghi lại thông tin **địa chỉ mã nguồn**.

**Lưu ý:** Một số node được tổng hợp hoặc lỗi parser có thể thiếu vị trí xác định (`-1`), nên đừng mặc định mọi offset hợp lệ. Nếu cần rewrite chính xác, chú ý thêm comment, whitespace và các giới hạn của mô hình Tree API; AST không phải bản sao byte-for-byte của source.

## 11. Bẫy về API hiện đại và version

### 11.1. `CaseTree.getExpression()` đã deprecated

Dùng `getExpression()` trên `CaseTree` là lựa chọn không tốt cho code mới vì một case có thể có **nhiều nhãn**. Trong Javadoc Java 25, phương thức được đánh dấu **`@Deprecated`** và yêu cầu dùng `getExpressions()` cho các nhãn expression.

**Đừng nhầm:** `SwitchExpressionTree.getExpression()` không deprecated theo cùng nghĩa; đó là **selector** của switch. Cùng tên method nhưng nằm trên hai interface và có ý nghĩa khác.

### 11.2. Pattern labels và preview API

Java 21 chuẩn hóa pattern matching for switch; Tree API có các node case label phù hợp hơn. Đặc biệt, `CaseTree.getLabels()` là API ổn định kể từ Java 21, trong khi ở các JDK trước nó có các giai đoạn preview/reflective preview.

Nếu compiler tool của bạn phải build bằng `--release 14` hoặc `--release 17`, **đừng dùng `getLabels()` chỉ vì thấy Javadoc Java 25 có nó**. Bài demo này cố ý dùng `getCaseKind()` và `getBody()` đã có trong API ổn định trước đó.

Nếu mục tiêu là phân tích **Java 21+ pattern switch**, hãy phát triển và kiểm thử trên target JDK tương ứng, bổ sung logic duyệt `CaseLabelTree`, guards và các pattern AST nodes hiện đại. Không áp logic “mọi case label đều là hằng số ExpressionTree” vào toàn bộ cú pháp mới.

### 11.3. `TreeVisitor` có thể thêm phương thức trong bản JDK tương lai

Khi Java thêm loại node như một pattern syntax mới, interface `TreeVisitor` có thể được mở rộng. Một class viết `implements TreeVisitor<R,P>` trực tiếp phải triển khai đủ các method mới; nếu không, code có thể gặp lỗi source compatibility khi nâng JDK.

**Kế thừa `TreeScanner` hoặc `SimpleTreeVisitor`** là lựa chọn thực dụng cho hầu hết linter và tool phân tích mã nguồn. Những lớp tiện ích này giúp kế thừa hành vi mặc định cho nhiều node và giảm lượng boilerplate.

### 11.4. `com.sun.source.*` khác API nội bộ `com.sun.tools.javac.*`

Các package `com.sun.source.tree` và `com.sun.source.util` thuộc Java Compiler Tree API của module `jdk.compiler`, được tài liệu hóa công khai. Ngược lại, các lớp implementation `com.sun.tools.javac.tree.JCTree` là chi tiết nội bộ của compiler, có thể bị giới hạn bởi module encapsulation và thay đổi theo JDK.

Khi chỉ cần **đọc và phân tích AST**, hãy ưu tiên `com.sun.source.*`. Không thêm `--add-exports` để truy cập internals nếu có API công khai đáp ứng bài toán.

### 11.5. Parser không phải type checker

`JavacTask.parse()` trả AST **ngay cả khi một số cú pháp có lỗi**, có thể xuất hiện `ErroneousTree` hoặc diagnostics. Không chỉ nhìn số node rồi coi source hợp lệ.

Với công cụ production:

1. Cung cấp `DiagnosticCollector<JavaFileObject>` để xem lỗi parser/compilation.
2. Kiểm tra `Diagnostic.Kind.ERROR` nếu phải từ chối source không hợp lệ.
3. Nếu logic cần kiểu/symbol, sử dụng compiler semantic analysis và `Trees`/`TreePath` phù hợp.
4. Không tự thực thi code phân tích — cây cú pháp là dữ liệu về source.
5. Giới hạn dữ liệu đầu vào của linter, xử lý nhiều compilation units và exception phù hợp.
6. Cân nhắc tài nguyên khi scan project rất lớn.

## 12. Quy trình xây một rule phân tích switch expression bằng TreeScanner

Ví dụ muốn xây quy tắc **“thống kê số switch expression và yield trong từng file”**:

1. Tạo JavaCompiler task cho từng source hoặc nhóm source.
2. Parse ra `CompilationUnitTree`.
3. Tạo `TreeScanner<Void,Void>` với counters.
4. Override `visitSwitchExpression` để đếm biểu thức switch.
5. Override `visitYield` để đếm statement yield.
6. Override `visitSwitch` riêng nếu cần phân biệt statement.
7. Override `visitCase` khi cần phân loại RULE/STATEMENT.
8. **Gọi `super.visitXxx`** trong mỗi override để không bỏ sót descendants.
9. Sau khi scan mỗi file, xuất báo cáo. Nếu dùng scanner chung cho nhiều file, reset counters hoặc tạo scanner mới cho từng file.
10. Nếu cần report theo từng node với vị trí, dùng `TreePathScanner` và `SourcePositions`.
11. Kiểm thử trên cả **arrow expression body**, **arrow block with yield**, **colon case with yield**, và **switch statement**.
12. Giữ build trên phiên bản JDK/target source được hỗ trợ và tránh deprecated/preview APIs.

### Những tình huống phải thử thêm

| Tình huống | Kỳ vọng scanner |
| --- | --- |
| `case 1 -> 10;` trong switch expression | Đếm **switch expression**; không có `YieldTree` ở case này |
| `case 2 -> { yield 20; }` | Đếm **1 YieldTree** |
| `case 1: yield "one";` | `CaseKind.STATEMENT` nhưng **vẫn** trong switch expression |
| `switch(x) { case 1 -> print(); ... }` | `SwitchTree`, **không** `SwitchExpressionTree` |
| Switch expression lồng trong switch expression | Đếm cả hai khi gọi `super` |
| `throw new IllegalStateException()` trong rule | Là `ThrowTree`, không phải `YieldTree` |
| `return switch(...) { ... };` | `ReturnTree` chứa `SwitchExpressionTree` |
| Nhiều nhãn `case 1,2 -> ...` | Một `CaseTree` với nhiều nhãn, không phải hai case tree |
| Case có pattern/guard trong Java 21+ | Không mặc định tất cả label là hằng số; cần API modern |
| Source cú pháp sai | Có thể có diagnostics/`ErroneousTree`; không coi kết quả đếm là đã hợp lệ |

## 13. Lỗi phổ biến và cách sửa

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ override `visitSwitch` | Bỏ sót `switch expression` | Bổ sung `visitSwitchExpression` |
| Chỉ tìm keyword `yield` trong chuỗi source | Dễ nhầm comment/string hoặc context | Dùng `YieldTree` qua AST |
| Cho rằng mỗi `case ->` sinh `YieldTree` | Đếm dư yield | Yield chỉ tồn tại khi có câu lệnh `yield` tường minh |
| Nghĩ colon `case :` chỉ xuất hiện ở switch statement | Phân loại sai switch expression | Kiểm tra `SwitchExpressionTree` và `CaseKind` độc lập |
| Gọi `getStatements()` cho RULE case rồi duyệt | Có thể NPE vì trả null | RULE dùng `getBody()` |
| Gọi `getBody()` cho STATEMENT case rồi cast | Có thể null | STATEMENT dùng `getStatements()` |
| Không gọi `super.visitSwitchExpression` | Bỏ sót yield và switch lồng trong subtree | Gọi super khi cần quét toàn bộ |
| Không gọi `super.visitYield` | Bỏ sót node bên trong yield expression | Gọi super hoặc scan thủ công đúng phạm vi |
| Dùng `TreeScanner<Integer,Void>` mà không hiểu `reduce` | Kết quả không phải tổng số node | Dùng counters hoặc override reduce chính xác |
| Dùng `TreeVisitor` trực tiếp rồi bỏ phương thức mới | Dễ lỗi tương thích khi nâng JDK | Kế thừa `SimpleTreeVisitor`/`TreeScanner` |
| Dùng `CaseTree.getExpression()` mới | API deprecated, không xử lý hết labels | Chọn `getExpressions()`/`getLabels()` theo JDK |
| Dùng `getLabels()` trong tool phải target JDK 17 | API preview/không ổn định ở version cũ | Chỉ dùng với JDK/target ổn định phù hợp |
| Suy ra giá trị runtime từ `YieldTree.getValue().toString()` | AST là cú pháp, không chạy code | Dùng semantic analysis hoặc thực thi test riêng |
| Cho rằng `parse()` tương đương type-check | Source có thể còn lỗi | Kiểm tra diagnostics, semantic phase nếu cần |
| Tưởng `break value` là syntax hiện hành | Giai đoạn preview cũ đã kết thúc | Dùng `yield` trong Java 14+ |
| Truy cập `JCTree` nội bộ để đọc switch | Phụ thuộc implementation và module exports | Ưu tiên `com.sun.source.*` |
| Scan nested switches rồi gán mọi yield cho switch ngoài | Sai yield target | Dùng `TreePathScanner`/context stack |
| Chỉ xem `switch` dạng text để biết statement/expression | Cùng keyword, cú pháp gần giống | Dùng AST node kind |

## 14. Checklist chất lượng cho công cụ AST

- [ ] Chỉ dùng API đã ổn định của `jdk.compiler` trên target JDK cần hỗ trợ?
- [ ] Có phân biệt `SwitchExpressionTree` với `SwitchTree`?
- [ ] Có override `visitSwitchExpression` và `visitYield` theo đúng mục tiêu?
- [ ] Có gọi `super.visitXxx` để duyệt descendants khi cần?
- [ ] Có hiểu `yield` chỉ là statement tường minh, không xuất hiện cho mọi arrow-expression case?
- [ ] Có tách `CaseKind.RULE` và `CaseKind.STATEMENT`?
- [ ] Có tránh `getBody()`/`getStatements()` trên sai CaseKind?
- [ ] Không dùng `CaseTree.getExpression()` deprecated cho code mới?
- [ ] Có chọn `getLabels()` chỉ khi JDK target ổn định hỗ trợ pattern labels?
- [ ] Nếu cần parent chain/yield target, có dùng `TreePathScanner`/context stack?
- [ ] Nếu cần vị trí lỗi, có dùng `SourcePositions` và `LineMap`?
- [ ] Có thu thập parser/compiler diagnostics?
- [ ] Không coi AST là kết quả thực thi hoặc type checking hoàn tất?
- [ ] Có test cả switch statement arrow, switch expression arrow/colon và nested switch?
- [ ] Có kiểm chứng stdout/số node từ chương trình runnable?
- [ ] Có tránh lớp implementation javac nội bộ khi API công khai đủ dùng?

## 15. Câu hỏi tự kiểm tra

**1. `switch` với `case ->` luôn là `SwitchExpressionTree`?**

Không. `case ->` cũng dùng được trong `switch statement`. Kiểu AST của toàn bộ switch mới quyết định `SwitchTree` hay `SwitchExpressionTree`.

**2. `case 1 -> 10` có một `YieldTree` không?**

Không. Đó là expression body trực tiếp. `YieldTree` chỉ ứng với câu `yield expression;` hiện diện trong source.

**3. `case 2 -> { yield 20; }` tạo body loại gì?**

`CaseTree.getBody()` là một `BlockTree`, chứa `YieldTree` với `getValue()` là expression tree của literal `20`.

**4. `case 1: yield "one";` trong switch expression có CaseKind nào?**

`CaseKind.STATEMENT` vì dùng cú pháp dấu hai chấm, **dù switch bao quanh là expression**.

**5. Vì sao `getStatements()` có thể gây NullPointerException khi gọi trên RULE case?**

Vì `getStatements()` được quy định trả **`null`** cho rule cases. Dùng `getBody()` cho `RULE`.

**6. Khác biệt chính giữa `SimpleTreeVisitor` và `TreeScanner`?**

`SimpleTreeVisitor` xử lý/dispatch node được đưa vào mà không tự scan toàn bộ con. `TreeScanner` chủ động duyệt descendants, nên thích hợp linter thống kê trên cả source file.

**7. Khi override `TreeScanner.visitSwitchExpression`, nếu không gọi `super` thì sao?**

Các case và descendants có thể không được scan; bạn sẽ bỏ sót những yield hoặc switch expression lồng trong node đó.

**8. Số `YieldTree` có bằng số case của switch expression không?**

Không. Một case rule có thể trả giá trị trực tiếp không có yield, một block có nhiều nhánh điều kiện với yield, và case colon có thể chứa yield.

**9. Muốn biết yield thuộc switch expression nào khi có switch lồng nhau, dùng gì?**

Dùng `TreePathScanner` và đường đi tổ tiên, hoặc quản lý stack context chính xác khi scan.

**10. `JavacTask.parse()` có đủ để biết kiểu của mọi biểu thức không?**

Không. Parse chủ yếu tạo AST cú pháp. Muốn type/symbol phải dùng semantic analysis và các API `Trees`/`TreePath` tương ứng, đồng thời xử lý diagnostics.

**11. `CaseTree.getExpression()` có còn là lựa chọn tốt khi phân tích Java hiện đại không?**

Không. Nó deprecated; dùng `getExpressions()` với constant labels, hoặc `getLabels()` khi target API mới ổn định hỗ trợ pattern labels.

**12. Có cần `--enable-preview` khi dùng `switch expression` và `yield` trong Java 17+ không?**

Không. Chúng đã được chuẩn hóa từ Java 14.

## 16. Nguồn chính thức đang áp dụng

- [Oracle Java 25 API — TreeVisitor](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/tree/TreeVisitor.html): generic visitor, `visitSwitchExpression`, `visitYield`, cảnh báo tương thích khi interface được bổ sung method.
- [Oracle Java 25 API — TreeScanner](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/util/TreeScanner.html): `scan`, cách duyệt descendants, `reduce`, các visit methods.
- [Oracle Java 25 API — SimpleTreeVisitor](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/util/SimpleTreeVisitor.html): visitor xử lý một node và default value.
- [Oracle Java 25 API — TreePathScanner](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/util/TreePathScanner.html): duy trì parent path khi duyệt AST.
- [Oracle Java 25 API — SwitchExpressionTree](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/tree/SwitchExpressionTree.html): `getExpression()` và `getCases()`.
- [Oracle Java 25 API — YieldTree](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/tree/YieldTree.html): `getValue()` của yield statement.
- [Oracle Java 25 API — CaseTree](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/tree/CaseTree.html): `CaseKind`, `getBody()`, `getStatements()`, deprecated `getExpression()` và labels API.
- [Oracle Java 25 API — JavacTask](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/util/JavacTask.html): `parse()` và các pha compiler.
- [Oracle Java 14 — Switch Expressions](https://docs.oracle.com/en/java/javase/14/language/switch-expressions.html) và [OpenJDK JEP 361](https://openjdk.org/jeps/361): ngữ nghĩa switch expression và `yield`, chính thức từ Java 14.
- [Oracle Java 17 API — CaseTree](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/tree/CaseTree.html): kiểm tra phần API ổn định khi phải hỗ trợ source/target cũ.

**Ghi nhớ:** `TreeVisitor` quyết định **đang thăm loại node nào**, `TreeScanner` đi **qua toàn bộ AST**. Với switch expression dùng `visitSwitchExpression`, với câu lệnh `yield` dùng `visitYield`, với switch statement dùng `visitSwitch`; đừng nhầm `case -> expression` là `YieldTree`. Kết hợp `CaseTree.getCaseKind()` và `getBody()/getStatements()` để xử lý chính xác cả hai cú pháp case, đồng thời gọi `super.visitXxx` nếu muốn tiếp tục duyệt descendants.

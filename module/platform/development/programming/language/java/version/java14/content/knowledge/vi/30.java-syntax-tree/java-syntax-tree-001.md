# `SwitchExpressionTree`: đọc và phân tích biểu thức `switch` trong cây cú pháp Java

## 1. Mục tiêu và bối cảnh

**`SwitchExpressionTree`** là một interface trong **Compiler Tree API** của JDK, thuộc package `com.sun.source.tree` và module `jdk.compiler`. Interface này biểu diễn **một biểu thức `switch`** (*switch expression*) trong cây cú pháp trừu tượng (AST) của mã nguồn Java. Nó **không phải** một hàm thực thi `switch`, không phải runtime reflection và không có nhiệm vụ tự tính giá trị của mọi nhánh.

Từ Java 14, **biểu thức `switch` được chuẩn hóa** (JEP 361): một `switch` có thể tạo ra **một giá trị** để gán biến, `return` hoặc truyền làm đối số. Compiler Tree API cung cấp node `SwitchExpressionTree` để chương trình như static analyzer, IDE, linter, công cụ kiểm thử mã nguồn và tiện ích phân tích AST nhận diện biểu thức này.

Ví dụ Java thông thường:

```java
String label = switch (number) {
    case 0 -> "ZERO";
    case 1, 2 -> "SMALL";
    default -> "OTHER";
};
```

Đây là **đoạn mã minh họa** với biến `number` đã được khai báo. Trong AST, toàn bộ phần `switch (...) {...}` ở bên phải phép gán là một `SwitchExpressionTree`; các nhánh bên trong là các node `CaseTree`.

**Phân biệt hai lớp kiến thức:**

- **Ngôn ngữ Java:** biểu thức `switch` có giá trị, phải bao phủ các trường hợp có thể xảy ra theo quy tắc của ngôn ngữ và dùng `yield` khi một nhánh dạng khối cần cung cấp kết quả.
- **Compiler Tree API:** `SwitchExpressionTree` cho phép **xem cấu trúc mã nguồn** (biểu thức chọn, các nhánh, kiểu cú pháp của nhánh), chứ không thay việc biên dịch, phân tích kiểu hoặc thực thi mã.

**Special Note — chỉ dùng kiến thức còn hiệu lực:** bài sử dụng **Java 17+**, `SwitchExpressionTree` và các API vẫn được hỗ trợ hiện nay. Không dùng cú pháp `break value` của những giai đoạn preview cũ. Với phân tích nhãn pattern `switch` của Java 21+, bài phân biệt API hiện hành theo từng phiên bản JDK; không sử dụng API preview của Java 17 trong ví dụ chạy bằng `--release 17`.

## 2. Switch expression khác switch statement thế nào?

| Tiêu chí | `switch` expression | `switch` statement |
| --- | --- | --- |
| Vai trò | **Expression**, có thể tạo một giá trị | **Statement**, điều khiển luồng |
| Cây AST | `SwitchExpressionTree` | `SwitchTree` |
| Kiểu AST cha | `ExpressionTree` | `StatementTree` |
| `Tree.Kind` | `SWITCH_EXPRESSION` | `SWITCH` |
| Kết quả của nhánh | Nhánh phải tạo giá trị hoặc hoàn tất bất thường (ví dụ `throw`), theo quy tắc exhaustiveness | Không nhất thiết tạo giá trị |
| Cú pháp nhánh | Hỗ trợ `case ... ->` và nhóm `case ... :` | Cũng hỗ trợ cả hai dạng |
| Dùng `yield`? | Có, để cung cấp giá trị từ khối/nhóm statement trong switch expression | Không dùng `yield` để trả giá trị cho một switch statement thường |

**Quan trọng:** Không thể nhận diện `switch` expression chỉ bằng cách thấy ký hiệu `->`. Cả **switch statement** lẫn **switch expression** đều có thể chứa nhánh dạng `case ... ->`. Khi phân tích AST, hãy xét **loại node**: `SwitchExpressionTree` hay `SwitchTree`, hoặc `Tree.Kind.SWITCH_EXPRESSION` / `Tree.Kind.SWITCH`.

### 2.1. Chương trình chạy thật: kết quả của `switch`

Lưu file **`SwitchRuntimeDemo.java`**:

```java
public class SwitchRuntimeDemo {
    static String label(int n) {
        return switch (n) {
            case 0 -> "ZERO";
            case 1, 2 -> "SMALL";
            default -> {
                yield "OTHER";
            }
        };
    }

    static int points(String category) {
        return switch (category) {
            case "A": yield 10;
            default: yield 1;
        };
    }

    public static void main(String[] args) {
        System.out.println("label0=" + label(0));
        System.out.println("label2=" + label(2));
        System.out.println("label5=" + label(5));
        System.out.println("pointsA=" + points("A"));
        System.out.println("pointsX=" + points("X"));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 SwitchRuntimeDemo.java
java SwitchRuntimeDemo
```

**Đầu ra đã được kiểm chứng:**

```text
label0=ZERO
label2=SMALL
label5=OTHER
pointsA=10
pointsX=1
```

Trong hai phương thức, `switch` là **biểu thức** vì kết quả của nó được dùng trực tiếp sau `return`. Với nhánh `case 0 -> "ZERO"`, chính expression sau mũi tên cung cấp giá trị. Với `default -> { yield "OTHER"; }`, lệnh `yield` cung cấp giá trị của nhánh có khối. Với dạng `case "A": yield 10;`, cần `yield` vì đây là **nhóm statement dạng dấu hai chấm**.

### 2.2. Exhaustiveness và cách hoàn tất

Biểu thức `switch` phải có cách xử lý **mọi đầu vào có thể xảy ra** theo hệ thống kiểu/nhãn của phiên bản Java đang dùng. Với `int` như `label`, nhánh `default` giúp bao phủ các giá trị không được liệt kê. Với enum, có thể liệt kê đầy đủ tất cả enum constants và compiler xác định biểu thức exhaustive mà không cần `default` tường minh.

Nếu một nhánh kết thúc bình thường mà không tạo giá trị cho `switch` expression, mã không hợp lệ. Nhánh có thể tạo giá trị bằng biểu thức trực tiếp sau `->`, bằng `yield`, hoặc hoàn tất bất thường qua `throw` khi phù hợp.

**Đừng nhầm `yield` và `return`:** `yield` chuyển một giá trị cho **`switch` expression bao quanh**, còn `return` thoát khỏi phương thức (hoặc ngữ cảnh có `return` hợp lệ) chứ không phải cách trả kết quả từ một nhánh khối của switch expression.

### 2.3. Fall-through: hai dạng nhánh không đồng nhất

- **Nhánh rule `case ... ->`** không fall-through sang rule kế tiếp.
- **Nhánh statement group `case ... :`** có thể có đặc tính chuyển tiếp giữa các nhãn/nhóm như switch truyền thống, nhưng một switch expression phải kết thúc theo quy tắc tạo kết quả; `yield` là cách rõ ràng để thoát với một giá trị.

Vì vậy không nên nói “mọi dạng switch expression đều không bao giờ có fall-through”. Phải **xem `CaseTree.CaseKind`** để biết mã đang dùng nhánh rule hay statement group.

## 3. Compiler Tree API nằm ở đâu?

Các interface trong bài:

| Interface/API | Module | Vai trò |
| --- | --- | --- |
| `SwitchExpressionTree` | `jdk.compiler` | Node cho một switch expression |
| `SwitchTree` | `jdk.compiler` | Node cho switch statement |
| `CaseTree` | `jdk.compiler` | Node cho từng case/default |
| `YieldTree` | `jdk.compiler` | Node cho lệnh `yield expr;` |
| `Tree.Kind` | `jdk.compiler` | Phân loại kind của node AST |
| `CompilationUnitTree` | `jdk.compiler` | Node đại diện đơn vị biên dịch/file mã nguồn |
| `TreePathScanner` | `jdk.compiler` | Visitor duyệt cây, duy trì đường dẫn đến node hiện tại |
| `JavacTask` | `jdk.compiler` | Cung cấp `parse()`, `analyze()`, `generate()` của javac |
| `JavaCompiler`/`ToolProvider` | `java.compiler` | Lấy compiler qua Tool API |
| `Trees` và `SourcePositions` | `jdk.compiler` | Lấy node, đường dẫn, vị trí mã nguồn, hỗ trợ phân tích nâng cao |

Các lệnh import thường dùng:

```java
import com.sun.source.tree.SwitchExpressionTree;
import com.sun.source.tree.SwitchTree;
import com.sun.source.tree.CaseTree;
import com.sun.source.tree.YieldTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.TreePathScanner;
```

Đây là **mã import**, không phải chương trình chạy độc lập. Khi dùng các interface thuộc `com.sun.source.tree`, bạn đang sử dụng **Compiler Tree API công khai được module `jdk.compiler` export**, không phải `com.sun.tools.javac.*` nội bộ.

### 3.1. JPMS module

Một tiện ích phân tích mã nguồn Java được viết như **named module** nên khai báo:

```java
module com.example.asttool {
    requires jdk.compiler;
}
```

Trong khi đó, ứng dụng Java thường chạy theo **classpath** trên một bản JDK đầy đủ có thể compile/run ví dụ bài này bằng các lệnh `javac` và `java` trực tiếp, như phần 6.

**Không nhầm module `jdk.compiler` với `java.compiler`:**

- `java.compiler` có `javax.tools.JavaCompiler`, `ToolProvider`, `JavaFileObject`.
- `jdk.compiler` có AST interface `com.sun.source.tree.*` và `JavacTask`/`TreePathScanner`.

Dự án có `requires jdk.compiler;` sẽ có quyền đọc các API cần thiết do JDK compiler cung cấp thông qua dependency module của nó; nếu trực tiếp dùng thêm `javax.tools` và muốn rõ phụ thuộc, có thể khai báo `requires java.compiler;`. **Không cần thêm `--add-exports` cho `com.sun.source.tree` vì package này đã được export công khai.**

**Runtime image tối giản:** Nếu bạn chạy công cụ AST trên một runtime tự tạo bằng `jlink` mà **không có `jdk.compiler`**, `ToolProvider.getSystemJavaCompiler()` có thể trả `null`, và chương trình dùng AST không thể hoạt động bình thường. Để phân tích source, dùng **JDK đầy đủ hoặc runtime image chứa các module compiler cần thiết**, không mặc định môi trường chỉ có `java.base`.

## 4. Cấu trúc của `SwitchExpressionTree`

Interface có hai phương thức chính:

```java
ExpressionTree getExpression();
List<? extends CaseTree> getCases();
```

Chúng được định nghĩa trong interface `SwitchExpressionTree`; đây là **chữ ký API rút gọn** (không phải mã để khai báo lại interface).

### 4.1. `getExpression()`: selector của switch

Với mã:

```java
return switch (status) {
    case 200 -> "OK";
    default -> "OTHER";
};
```

`tree.getExpression()` trả về **node biểu thức chọn `(status)`**, không phải giá trị runtime của `status`. Trong AST, selector có thể là `ParenthesizedTree` bao quanh expression thực; một số bản javac khi chuyển nó thành text sẽ in `(status)` với dấu ngoặc.

**Không nhầm hai phương thức cùng tên:**

- **`SwitchExpressionTree.getExpression()`**: **API hiện hành, không deprecated**, dùng lấy selector của toàn bộ biểu thức switch.
- **`CaseTree.getExpression()`**: **deprecated**, chỉ lấy biểu thức đầu tiên của một nhánh case; thay bằng `CaseTree.getExpressions()` cho các constant case labels ở Java 17+.

Sự khác nhau này rất quan trọng khi đọc ví dụ trên Internet và thiết kế linter cho nhiều nhãn.

### 4.2. `getCases()`: các nhánh của switch

Ví dụ:

```java
String result = switch (n) {
    case 0 -> "ZERO";
    case 1, 2 -> "SMALL";
    default -> "OTHER";
};
```

`getCases()` trả một danh sách **3 `CaseTree`** trong thứ tự mã nguồn: case 0, case 1/2, default. **Một case có hai nhãn `1, 2` vẫn là một `CaseTree`**, không phải hai node case riêng.

Mỗi `CaseTree` có thể cung cấp:

| API | Dùng để làm gì? | Lưu ý |
| --- | --- | --- |
| `getCaseKind()` | Phân biệt `RULE` và `STATEMENT` | Không suy từ chuỗi `toString()` |
| `getExpressions()` | Lấy các nhãn biểu thức hằng như `1, 2` | Có từ Java 14; dùng được với `--release 17` |
| `getBody()` | Lấy node sau mũi tên trong nhánh `RULE` | Có thể là expression, block hoặc throw; `null` cho `STATEMENT` |
| `getStatements()` | Lấy danh sách câu lệnh của nhánh `STATEMENT` | Trả `null` với nhánh `RULE` |
| `getLabels()` | Lấy các case-label nodes tổng quát, bao gồm default và pattern | **API ổn định từ Java 21**, không dùng trong ví dụ nhắm `--release 17` |
| `getGuard()` | Lấy điều kiện guard của pattern case khi có | **API từ Java 21** |

Ở các phiên bản Java mới hơn, `CaseTree.getLabels()` là API phù hợp hơn khi một `switch` chứa **pattern labels, null labels, guarded patterns**; không chỉ các biểu thức hằng. **`getExpressions()` vẫn còn được hỗ trợ nhưng không mô tả toàn bộ khả năng pattern của Java 21+**. Mẫu Java 17 trong bài chỉ phân tích nhãn hằng và `default`, vì vậy dùng `getExpressions()` là hợp lý.

### 4.3. `CaseTree.CaseKind`

Có hai giá trị cốt lõi:

- `RULE`: nhánh kiểu `case X -> expression`, `case X -> { block }` hoặc `case X -> throw ...`.
- `STATEMENT`: nhóm kiểu `case X: statements`.

Ví dụ:

```java
case 0 -> "ZERO";                  // RULE, getBody() là expression
case 1 -> { yield "SMALL"; }       // RULE, getBody() là BLOCK
case 2: yield "TWO";               // STATEMENT, getStatements() chứa YieldTree
```

Các dòng này là **minh họa các loại case ở những switch expression khác nhau**; đừng ghép nguyên các dòng thành một switch duy nhất vì Java không cho phép tùy tiện trộn hai dạng nhánh trong cùng switch block.

### 4.4. `YieldTree`

Khi compiler thấy `yield value;` trong switch expression, nó tạo node **`YieldTree`**:

```java
yield "OTHER";
```

`YieldTree.getValue()` trả **`ExpressionTree`** cho expression sau `yield` (ví dụ string literal `"OTHER"`).

Với rule `case 0 -> "ZERO";`, **không cần `yield`**, nên **không sinh `YieldTree` chỉ vì nhánh tạo ra giá trị**. Đây là điều quan trọng khi đếm số `yield` trong AST: số `YieldTree` **không phải** số nhánh switch expression, cũng không phải tổng số cách trả về giá trị.

## 5. Cấu trúc AST minh họa

Cho biểu thức:

```java
switch (n) {
    case 0 -> "ZERO";
    case 1, 2 -> "SMALL";
    default -> { yield "OTHER"; }
}
```

Có thể hình dung cây con:

```text
SwitchExpressionTree            kind=SWITCH_EXPRESSION
├── selector: (n)
└── cases: [3 CaseTree]
    ├── CaseTree RULE (label: 0)
    │   └── getBody(): STRING_LITERAL "ZERO"
    ├── CaseTree RULE (labels: 1, 2)
    │   └── getBody(): STRING_LITERAL "SMALL"
    └── CaseTree RULE (default)
        └── getBody(): BLOCK
            └── YieldTree (getValue() = "OTHER")
```

**Đây là sơ đồ tư duy**, không phải chuỗi AST chuẩn mà mọi JVM buộc phải in ra. Cây thật của javac có thêm node cho dấu ngoặc, biểu thức, block và vị trí nguồn; phần 6 sẽ in ra những thuộc tính API cụ thể có thể kiểm tra.

Với biến thể dấu hai chấm:

```java
switch (n) {
    case 0: yield "ZERO";
    default: yield "OTHER";
}
```

các `CaseTree` có `CaseKind.STATEMENT`, `getBody() == null` và `getStatements()` chứa `YieldTree` tương ứng.

## 6. Ví dụ Java 17+ hoàn chỉnh: phân tích source bằng `JavacTask`

Chương trình bên dưới **đọc mã nguồn Java từ một chuỗi trong bộ nhớ**, yêu cầu javac phân tích cú pháp thành AST, sau đó dùng `TreePathScanner` tìm các node `SwitchExpressionTree`, `SwitchTree` và `YieldTree`.

Mã nguồn được phân tích chứa:

1. Một switch expression dùng **arrow rules** (3 case, một nhánh có `yield`).
2. Một switch expression dùng **colon statement groups** (2 case, hai lệnh `yield`).
3. Một switch **statement** dùng arrow rules, để chứng minh `->` không đồng nghĩa với `SwitchExpressionTree`.

Bài này không cần tạo các file nguồn phụ cho đoạn mã được phân tích.

### 6.1. Tệp `SwitchExpressionTreeDemo.java`

```java
import com.sun.source.tree.CaseTree;
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.SwitchExpressionTree;
import com.sun.source.tree.SwitchTree;
import com.sun.source.tree.Tree;
import com.sun.source.tree.YieldTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.TreePathScanner;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.stream.Collectors;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class SwitchExpressionTreeDemo {
    static final class Inspector extends TreePathScanner<Void, Void> {
        int expressions;
        int statements;
        int yields;

        @Override
        public Void visitSwitchExpression(SwitchExpressionTree tree, Void unused) {
            expressions++;
            System.out.println("expression#" + expressions
                    + " kind=" + tree.getKind()
                    + " selector=" + tree.getExpression()
                    + " cases=" + tree.getCases().size());
            for (CaseTree c : tree.getCases()) {
                String labels = c.getExpressions().isEmpty()
                        ? "default"
                        : c.getExpressions().stream()
                                .map(Object::toString)
                                .collect(Collectors.joining("|"));
                Tree body = c.getBody();
                int statementCount = c.getStatements() == null
                        ? -1 : c.getStatements().size();
                System.out.println("  case=" + labels
                        + " style=" + c.getCaseKind()
                        + " body=" + (body == null ? "none" : body.getKind())
                        + " statements=" + statementCount);
            }
            return super.visitSwitchExpression(tree, unused);
        }

        @Override
        public Void visitSwitch(SwitchTree tree, Void unused) {
            statements++;
            System.out.println("statement#" + statements
                    + " kind=" + tree.getKind()
                    + " cases=" + tree.getCases().size());
            return super.visitSwitch(tree, unused);
        }

        @Override
        public Void visitYield(YieldTree tree, Void unused) {
            yields++;
            System.out.println("  yield=" + tree.getValue());
            return super.visitYield(tree, unused);
        }
    }

    public static void main(String[] args) throws Exception {
        String source = """
                class Sample {
                    static String byArrow(int n) {
                        return switch (n) {
                            case 0 -> "ZERO";
                            case 1, 2 -> "SMALL";
                            default -> { yield "OTHER"; }
                        };
                    }

                    static String byColon(int n) {
                        return switch (n) {
                            case 0: yield "ZERO";
                            default: yield "OTHER";
                        };
                    }

                    static void asStatement(int n) {
                        switch (n) {
                            case 0 -> System.out.println(n);
                            default -> { }
                        }
                    }
                }
                """;

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Use a full JDK, not a JRE-only runtime");
        }
        JavaFileObject file = new SimpleJavaFileObject(
                URI.create("string:///Sample.java"), JavaFileObject.Kind.SOURCE) {
            @Override
            public CharSequence getCharContent(boolean ignoreEncodingErrors) {
                return source;
            }
        };

        try (StandardJavaFileManager files =
                compiler.getStandardFileManager(null, null, StandardCharsets.UTF_8)) {
            JavacTask task = (JavacTask) compiler.getTask(
                    null, files, null, List.of("--release", "17", "-proc:none"),
                    null, List.of(file));
            Inspector inspector = new Inspector();
            for (CompilationUnitTree unit : task.parse()) {
                inspector.scan(unit, null);
            }
            System.out.println("totals=expressions:" + inspector.expressions
                    + ",statements:" + inspector.statements
                    + ",yields:" + inspector.yields);
        }
    }
}
```

### 6.2. Biên dịch và chạy

Sử dụng **JDK đầy đủ** từ Java 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 SwitchExpressionTreeDemo.java
java SwitchExpressionTreeDemo
```

**Đầu ra đã kiểm chứng:**

```text
expression#1 kind=SWITCH_EXPRESSION selector=(n) cases=3
  case=0 style=RULE body=STRING_LITERAL statements=-1
  case=1|2 style=RULE body=STRING_LITERAL statements=-1
  case=default style=RULE body=BLOCK statements=-1
  yield="OTHER"
expression#2 kind=SWITCH_EXPRESSION selector=(n) cases=2
  case=0 style=STATEMENT body=none statements=1
  case=default style=STATEMENT body=none statements=1
  yield="ZERO"
  yield="OTHER"
statement#1 kind=SWITCH cases=2
totals=expressions:2,statements:1,yields:3
```

**Lưu ý về output:** `selector=(n)` là cách javac render node biểu thức được bao bởi dấu ngoặc trong ví dụ này. Các chuỗi literal và ký tự ngăn nhãn `|` được tạo bởi code hiển thị. Các công cụ khác không nhất thiết định dạng `Tree.toString()` giống javac; nếu muốn tái tạo đúng mã nguồn, phải dùng vị trí nguồn thay vì so một chuỗi render làm hợp đồng API.

### 6.3. Giải thích kết quả

| Dòng / thuộc tính | Ý nghĩa |
| --- | --- |
| `expression#1` | Visitor gặp switch expression dạng `case ... ->` đầu tiên |
| `kind=SWITCH_EXPRESSION` | Node đó có kind của **biểu thức**, khác `SWITCH` |
| `selector=(n)` | `getExpression()` trả **node selector**, không phải giá trị runtime `n` |
| `cases=3` | `getCases()` có 3 case nodes; `case 1, 2` chỉ chiếm một node |
| `style=RULE` | `CaseTree.getCaseKind()` nhận dạng nhánh mũi tên |
| `body=STRING_LITERAL` | `CaseTree.getBody()` là expression literal sau `->` |
| `body=BLOCK` | Nhánh `default -> { ... }` có block chứa `YieldTree` |
| `statement=-1` | **Sentinel do demo quy ước** để hiển thị `getStatements() == null` đối với rule; **không** phải số câu lệnh âm của Java |
| `expression#2` | Switch expression dùng nhóm `case ... :` |
| `style=STATEMENT` | Nhánh dấu hai chấm, `getBody() == null` và `getStatements()` có danh sách câu lệnh |
| `yield="ZERO"` và `yield="OTHER"` | `YieldTree.getValue()` cho expression sau mỗi `yield` |
| `statement#1 kind=SWITCH` | Đây là `SwitchTree` dù cũng có `case ... ->` |
| `totals=expressions:2,statements:1,yields:3` | Có 2 switch expression, 1 switch statement, 3 `yield` tường minh |

**Vì sao chỉ có 3 `YieldTree`?** Ở switch expression thứ nhất, hai rule `case 0 -> "ZERO"` và `case 1, 2 -> "SMALL"` trả giá trị qua **expression body**, nên **không tạo node `YieldTree`**. Nhánh default có một `yield`. Switch expression thứ hai có hai `yield`, tổng là ba.

### 6.4. Các kỹ thuật API trong ví dụ

- `ToolProvider.getSystemJavaCompiler()` trả compiler của JDK. Nếu môi trường không có compiler (ví dụ runtime bị cắt giảm), trả `null`.
- `SimpleJavaFileObject` được override `getCharContent(...)` để cấp source code **ngay trong bộ nhớ**.
- `JavaCompiler.getTask(...)` cấu hình parser/compilation task; ép sang `JavacTask` để gọi `parse()`.
- `--release 17` làm rõ mức ngôn ngữ/API của mã cần phân tích, tránh vô tình chấp nhận cú pháp Java mới hơn.
- `-proc:none` tắt annotation processing trong tác vụ demo; bài không cần chạy processor.
- `TreePathScanner.scan(unit, null)` đi từ `CompilationUnitTree` xuống các node con, gọi những override `visitSwitchExpression`, `visitSwitch` và `visitYield`.
- `super.visitSwitchExpression(...)`/`super.visitSwitch(...)`/`super.visitYield(...)` tiếp tục duyệt node con sau khi ghi nhận thông tin. **Bỏ các lời gọi `super` mà không chủ động quét con có thể làm mất các node `yield` hoặc switch lồng nhau.**
- `getExpressions()` được dùng cho constant labels; code không động tới `CaseTree.getLabels()` vốn chưa ổn định trong chế độ Java 17.
- `Tree.getKind()` được dùng thay vì parse tên lớp triển khai nội bộ của javac.

**Không có `System.out.println(n)` từ mã `Sample` được thực thi khi chạy trình phân tích:** nó chỉ là **mã nguồn nằm trong chuỗi để parser đọc**, còn chương trình thật là `SwitchExpressionTreeDemo`.

## 7. Chỉ parse AST hay còn kiểm tra kiểu và tính đúng đắn?

`JavacTask.parse()` trả về những `CompilationUnitTree` sau **phân tích cú pháp**, nhưng chỉ có cây cú pháp **không chứng minh chương trình được phân tích là Java hợp lệ về kiểu và ngữ nghĩa**.

Ví dụ parser có thể nhận diện một `switch` trong một source đang còn lỗi như:

- Nhánh của switch expression không bao phủ giá trị theo quy tắc exhaustiveness.
- Một `yield` biểu thức không có kiểu phù hợp.
- Một biến tên `status` chưa hề được khai báo.
- Hai case labels trùng nhau.
- Một nhánh cố hoàn tất bình thường mà không yield/throw nơi cần.

**Đừng dùng số `CaseTree` để tự kết luận exhaustive hay không.** Exhaustiveness phụ thuộc kiểu selector, các nhãn và phiên bản ngôn ngữ, đặc biệt enum, sealed types và patterns ở Java mới.

Khi cần xác nhận semantic/type:

```java
// Đoạn minh họa, giả định task là JavacTask hợp lệ.
Iterable<? extends CompilationUnitTree> units = task.parse();
task.analyze();
```

`analyze()` yêu cầu compiler thực hiện phân tích ngữ nghĩa. Khi làm công cụ thực tế, nên dùng `DiagnosticCollector<JavaFileObject>` để thu warning/error và xét `Diagnostic.Kind.ERROR`; không chỉ dựa vào số AST nodes. Nếu cần kiểu của một expression hay symbol của member, kết hợp `Trees.instance(task)`, `TreePath` và `TypeMirror` ở pha phù hợp.

### Source file không có dấu lỗi có đủ chưa?

Không. Trong IDE, một file được parse khi người dùng **đang gõ dở** vẫn có thể sinh `ErroneousTree`. AST có thể chưa hoàn chỉnh. Khi phân tích các node, phải **chịu được mã chưa hoàn chỉnh** và tránh cast node theo giả định cố định.

**Dùng `parse()` cho bài học này là có chủ ý:** mục tiêu chính là khám phá **hình dạng cây cú pháp `switch`**, không xây một full compiler hoặc proof của sự hợp lệ của chương trình.

## 8. Xác định vị trí source và áp dụng vào linter

Một linter thường không chỉ muốn đếm switch expression; nó còn muốn báo **file và dòng** có vấn đề. Compiler Tree API có:

- `TreePathScanner.getCurrentPath()`: đường đi từ root tới node hiện tại.
- `Trees.instance(task)`: truy cập các tiện ích AST của task.
- `Trees.getSourcePositions()`: truy vấn offset bắt đầu/kết thúc của node trong source.
- `CompilationUnitTree.getLineMap()`: chuyển offset thành số dòng/cột.

Đoạn minh họa đặt **bên trong `visitSwitchExpression`** khi scanner có context:

```java
TreePath path = getCurrentPath();
CompilationUnitTree unit = path.getCompilationUnit();

Trees trees = Trees.instance(task);
long offset = trees.getSourcePositions()
        .getStartPosition(unit, path.getLeaf());

long line = unit.getLineMap().getLineNumber(offset);
System.out.println("switch expression at line " + line);
```

Đoạn trên **không độc lập**; phải có `task` trong scope và import `com.sun.source.util.TreePath`/`Trees`. Với node lỗi hoặc nguồn không có vị trí, start offset có thể là `-1`; khi đó **không được** chuyển thẳng sang line number mà không kiểm tra.

Điều này hữu ích cho các quy tắc:

- Đếm hoặc giới hạn độ phức tạp của switch expression.
- Kiểm tra case expression có quá nhiều nhãn hằng hay không.
- Phát hiện switch expression dùng nhóm `case ... :` và đề xuất chuyển sang arrow rules nếu phù hợp.
- Báo vị trí những `yield` tường minh trong các nhánh block.
- Xây bản đồ AST phục vụ refactoring, tài liệu hóa hoặc code review.

**Giới hạn quan trọng:** Compiler Tree API cung cấp **view đọc AST do javac tạo**, không cung cấp cơ chế chuẩn để sửa trực tiếp mọi node rồi tự sinh lại source giữ nguyên formatting/comment. Với refactoring, nên dùng công cụ được thiết kế cho rewrite, giữ trivia/comment và kiểm tra semantic sau sửa. `Tree.toString()` không được coi là serializer hoàn hảo của file nguồn.

## 9. Java 21+ và sự phát triển của các case labels

Java 21 chuẩn hóa **pattern matching for switch** (JEP 441). Khi phân tích mã nguồn hiện đại có pattern, null case và guards, cách mô hình hóa **case labels** phong phú hơn nhãn hằng Java 17.

Ví dụ cú pháp Java 21+ (minh họa, **không thuộc chương trình `--release 17` của phần 6**):

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String s when s.length() > 3 -> "LONG_STRING";
        case String s -> "STRING";
        default -> "OTHER";
    };
}
```

Trường hợp này vẫn tạo **`SwitchExpressionTree`** vì nó vẫn là biểu thức switch. Nhưng một `CaseTree` có thể chứa **pattern label** hoặc **null label**, không chỉ constant expressions.

Trong **JDK 21+**, các API còn áp dụng gồm:

| API | Công dụng |
| --- | --- |
| `CaseTree.getLabels()` | Liệt kê các node `CaseLabelTree`; xử lý constant/pattern/default labels |
| `CaseTree.getGuard()` | Lấy expression guard kiểu `when ...` khi nhánh có guard |
| `ConstantCaseLabelTree` | Nhãn case hằng |
| `PatternCaseLabelTree` | Nhãn chứa pattern |
| `DefaultCaseLabelTree` | Nhãn `default` |

`getLabels()` và `getGuard()` là **API ổn định từ Java 21**. **Không dùng trực tiếp các API ấy trong mã Java 17 của bài:** `getLabels()` từng mang trạng thái preview ở Java 17, vì vậy dùng khi nhắm JDK 21+ cùng mức ngôn ngữ tương ứng. Trong ví dụ Java 17, chúng ta dùng `CaseTree.getExpressions()` với các nhãn hằng vì vẫn là API được hỗ trợ và không cần preview.

**Cẩn thận với quy tắc `getExpressions().isEmpty()`:** trong ví dụ Java 17 chỉ chứa nhãn hằng và `default`, danh sách rỗng cho biết nhánh default. Với switch pattern của Java 21+, một case **không có constant expressions** không nhất thiết là default; muốn xác định label chính xác hãy kiểm tra `getLabels()` theo loại node. Đó là lý do linter tổng quát cho Java 21+ không nên dùng nguyên xi logic phân loại nhãn trong demo Java 17.

## 10. Các tình huống dễ sai và cách xử lý

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Thấy `case ->` rồi gán mọi switch là expression | Switch statement cũng có arrow rules | Xem `SwitchExpressionTree`/`SwitchTree` hoặc `Tree.Kind` |
| Nhầm `SwitchExpressionTree.getExpression()` với `CaseTree.getExpression()` | Dùng API case đã deprecated hoặc lấy sai selector | Selector dùng method của `SwitchExpressionTree`; case constants dùng `getExpressions()` |
| Tưởng `getExpression()` trả giá trị thực tại runtime | AST chỉ lưu mã nguồn | Dùng compiler/runtime khác để tính giá trị, không tự eval AST |
| Đếm từng literal `case 1,2` thành một `CaseTree` | Sai số nhánh | `getCases()` có một node cho nhánh đa nhãn |
| Coi `getBody()` luôn có giá trị | Với `STATEMENT` nó là `null` | Xem `getCaseKind()` trước |
| Coi `getStatements()` luôn là danh sách | Với `RULE` nó là `null` | Chỉ đọc danh sách với `STATEMENT` |
| Tưởng mỗi nhánh cho giá trị đều sinh `YieldTree` | Arrow expression sinh giá trị trực tiếp | `YieldTree` chỉ xuất hiện ở lệnh `yield` tường minh |
| Tưởng switch expression luôn không có fall-through | Nhóm case dấu `:` có cơ chế khác arrow | Phân biệt `RULE` và `STATEMENT` |
| Dùng `break value` từ ví dụ preview cũ | Không phải cú pháp Java hiện hành | Dùng `yield` trong nhánh thích hợp |
| Bỏ `super.visitSwitchExpression(...)` không scan con | Bỏ sót yield và switch lồng nhau | Tiếp tục traversal sau khi xử lý node |
| Dùng `CaseTree.getLabels()` mà biên dịch `--release 17` | API chưa ổn định với target đó | Dùng `getExpressions()` cho constant case ở 17; `getLabels()` ở 21+ |
| Dùng `getExpressions().isEmpty()` để xác nhận default trong pattern switch Java 21+ | Có thể nhầm pattern/null labels | Dùng `getLabels()` và kiểu label |
| Coi AST parse là proof code hợp lệ | Có thể chưa type-check, có ErroneousTree | `analyze()`/compiler diagnostics và kiểm thử thật |
| So `Tree.toString()` để kết luận source không đổi | Formatter/biểu diễn tree có thể khác source gốc | Dùng source positions và file gốc |
| Dùng `com.sun.tools.javac.*` nội bộ thay vì Compiler Tree API | Dễ phụ thuộc implementation không được export | Dùng `com.sun.source.tree.*` và `com.sun.source.util.*` |
| Chạy tiện ích parser trên JRE/runtime thiếu `jdk.compiler` | Không có JavaCompiler/JavacTask | Dùng JDK hoặc runtime image chứa compiler module |
| Tưởng `yield` là `return` | Phân tích control-flow sai | `yield` cung cấp giá trị của enclosing switch expression |
| Dựa vào số case để xác định exhaustive | Thiếu thông tin kiểu enum/sealed/pattern | Kết hợp compiler semantic analysis |

## 11. Bài tập tự luyện có đáp án

**Câu 1.** `SwitchExpressionTree` thuộc module và package nào?  
**Đáp án:** Module `jdk.compiler`, package `com.sun.source.tree`.

**Câu 2.** `SwitchExpressionTree` kế thừa `ExpressionTree` hay `StatementTree`?  
**Đáp án:** `ExpressionTree`. `SwitchTree` là node cho switch statement và kế thừa `StatementTree`.

**Câu 3.** `Tree.Kind` nào ứng với hai loại switch?  
**Đáp án:** `SWITCH_EXPRESSION` cho switch expression và `SWITCH` cho switch statement.

**Câu 4.** `SwitchExpressionTree.getExpression()` trả gì?  
**Đáp án:** Node `ExpressionTree` của selector trong `switch (...)`, **không phải** giá trị thực được tính khi chạy.

**Câu 5.** `CaseTree.getExpression()` có nên dùng cho mã Java mới không?  
**Đáp án:** Không. Phương thức ấy deprecated; dùng `CaseTree.getExpressions()` cho nhãn biểu thức hằng hoặc `getLabels()` cho mô hình nhãn rộng hơn trên JDK 21+.

**Câu 6.** `case 1, 2 -> "SMALL";` là bao nhiêu `CaseTree`?  
**Đáp án:** Một `CaseTree`, với hai constant expressions trong `getExpressions()`.

**Câu 7.** Với `case 0 -> "ZERO";`, `getBody()` là gì và có `YieldTree` không?  
**Đáp án:** Body là `ExpressionTree` kiểu string literal; không có `YieldTree` tường minh.

**Câu 8.** Với `default -> { yield "OTHER"; }`, `getBody()` là node gì?  
**Đáp án:** `BlockTree` (`Tree.Kind.BLOCK`), bên trong có một `YieldTree`.

**Câu 9.** Với `case 0: yield "ZERO";`, `getCaseKind()` là gì?  
**Đáp án:** `STATEMENT`; `getBody()==null`, `getStatements()` chứa lệnh `YieldTree`.

**Câu 10.** Vì sao `TreePathScanner.visitYield` đếm ít hơn số case của hai biểu thức switch trong demo?  
**Đáp án:** Các arrow-rule expression body trả về trực tiếp, không sinh `yield`; chỉ explicit yield statements được đếm.

**Câu 11.** `JavacTask.parse()` có đảm bảo switch expression exhaustive và có kiểu hợp lệ?  
**Đáp án:** Không. Parse chỉ tạo AST; phải xem `analyze()` và compiler diagnostics cho kiểm tra semantic.

**Câu 12.** Muốn tìm dòng của `SwitchExpressionTree` trong file, API nào hữu ích?  
**Đáp án:** `Trees.getSourcePositions()` và `CompilationUnitTree.getLineMap()`, kèm `TreePathScanner.getCurrentPath()`.

**Câu 13.** Vì sao mã Java 17 dùng `getExpressions()` thay vì `getLabels()`?  
**Đáp án:** `getExpressions()` hỗ trợ constant case labels trong Java 17; `getLabels()` trở thành API chính thức cho label tổng quát từ JDK 21 và từng là preview trong Java 17.

**Câu 14.** Khi phân tích pattern switch của Java 21+, có thể mặc định `getExpressions().isEmpty()` nghĩa là `default` không?  
**Đáp án:** Không. Các pattern/null labels có thể không được đại diện bằng danh sách constant expressions; cần `getLabels()`.

## 12. Tóm tắt và tài liệu chính thức

**Công thức nhận biết:**

```text
Java source:  switch (...) { case ... }
          |
          v
        JavacTask.parse()
          |
          v
    CompilationUnitTree
          |
          +-- SwitchExpressionTree  [Tree.Kind.SWITCH_EXPRESSION]
          |      +-- getExpression() -> selector
          |      +-- getCases()      -> CaseTree[]
          |               +-- RULE: getBody()
          |               +-- STATEMENT: getStatements()
          |               +-- YieldTree khi có "yield expr;"
          |
          +-- SwitchTree            [Tree.Kind.SWITCH]
                 (switch statement, không tạo giá trị biểu thức)
```

Những điểm cần nhớ:

1. **`SwitchExpressionTree` là node cú pháp**, không phải đối tượng switch runtime.
2. **`getExpression()` lấy selector, `getCases()` lấy các case nodes**.
3. **`CaseKind.RULE` và `CaseKind.STATEMENT`** quyết định nên đọc `getBody()` hay `getStatements()`.
4. **`YieldTree` chỉ đại diện `yield` tường minh**, còn arrow expression có thể cho giá trị mà không có yield statement.
5. Phân tích mã Java 17 constant labels dùng **`getExpressions()`**; mã Java 21+ với pattern switch dùng **`getLabels()`/`getGuard()`** theo API mới.
6. **Parse AST ≠ semantic validation**; cần compiler analysis và diagnostics nếu công cụ đưa ra kết luận về tính đúng đắn của mã nguồn.

**Nguồn chính thức và còn áp dụng:**

- [Oracle Java SE 17 — `SwitchExpressionTree`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/tree/SwitchExpressionTree.html): `getExpression()`, `getCases()`, kế thừa `ExpressionTree`.
- [Oracle Java SE 25 — `SwitchExpressionTree`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/tree/SwitchExpressionTree.html): API hiện hành.
- [Oracle Java SE 17 — `SwitchTree`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/tree/SwitchTree.html): phân biệt switch statement.
- [Oracle Java SE 17 — `CaseTree`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/tree/CaseTree.html): `CaseKind`, `getBody()`, `getStatements()`, `getExpressions()`.
- [Oracle Java SE 25 — `CaseTree`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/tree/CaseTree.html): `getLabels()` và `getGuard()` hiện hành trên JDK 21+.
- [Oracle Java SE 17 — `YieldTree`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/tree/YieldTree.html): `getValue()`.
- [Oracle Java SE 17 — `JavacTask`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/JavacTask.html): `parse()` và `analyze()`.
- [Oracle Java SE 17 — `TreePathScanner`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/TreePathScanner.html): visitor duyệt AST theo đường dẫn.
- [OpenJDK JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): biểu thức switch thành tính năng chính thức trong Java 14.
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): mẫu nhãn mở rộng trong Java 21.

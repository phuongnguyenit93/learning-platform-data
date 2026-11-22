# Phân biệt `CaseTree` dạng `RULE` và `STATEMENT` trong cây cú pháp Java

> **Java 14 — Cây cú pháp Java.** `CaseTree` thuộc Compiler Tree API (`com.sun.source.tree`, module `jdk.compiler`). Khi phân tích một nhánh `case`/`default`, `getCaseKind()` trả **`CaseTree.CaseKind.RULE`** nếu mã nguồn dùng dấu mũi tên `->`, hoặc **`CaseTree.CaseKind.STATEMENT`** nếu dùng dấu hai chấm `:`. Sự khác biệt quyết định cách truy cập dữ liệu AST: RULE đọc `getBody()`; STATEMENT đọc `getStatements()`. Switch expressions/arrow rules được chuẩn hóa ở **Java 14, JEP 361**. Bài chỉ trình bày **kiến thức còn áp dụng trên JDK hiện hành**, không dùng preview hoặc API legacy để thay thế các API mới đã ổn định. Các chương trình chính dùng Java 17; ví dụ pattern switch chính thức dùng Java 21+.

## 1. Kết quả học tập

Bạn sẽ biết cách:

1. Nhận diện case RULE (`case X -> ...`) và STATEMENT (`case X: ...`) theo cú pháp và AST.
2. Phân biệt `CaseTree.getCaseKind()` với `Tree.getKind()`.
3. Dùng đúng `getBody()` và `getStatements()`; không gây `NullPointerException`.
4. Hiểu `getBody()` có thể chứa expression, block, throw statement, expression statement; không luôn là `BlockTree`.
5. Phân biệt **hai chiều độc lập**: loại switch bao ngoài (statement/expression) và CaseKind của nhánh (RULE/STATEMENT).
6. Hiểu fall-through của colon-style switch, no-fall-through của arrow rules, `break` và `yield`.
7. Duyệt AST thực tế qua `JavacTask.parse()`/`TreePathScanner.visitCase()`.
8. Đọc case có list statements rỗng, nhiều labels, `default` và case guards.
9. Tránh `getExpression()` deprecated; chọn `getExpressions()` hoặc `getLabels()` theo target JDK.
10. Áp dụng vào static analysis/refactoring cùng kiểm thử biên và source-version correctness.

## 2. Ngữ cảnh Java 14: ngôn ngữ và Compiler Tree API

Java có switch statement dạng `case X:` từ lâu. Java 12/13 từng preview switch expressions và arrow rules, đến **Java 14** JEP 361 hoàn tất cú pháp switch expression, arrow switch rules và `yield`. `CaseTree` xuất hiện từ trước Java 14 và được cập nhật để mô tả hai hình thức case; không nên nói toàn bộ interface này “lần đầu ra mắt Java 14”.

API vẫn dùng được trên JDK hiện đại:

| Kiểu | Vai trò |
| --- | --- |
| `CaseTree` | Node AST cho một case/default trong switch statement/expression. |
| `CaseTree.CaseKind` | Enum có hai giá trị `RULE` và `STATEMENT`. |
| `Tree.Kind` | Enum rộng hơn, mô tả loại AST node như `CASE`, `SWITCH`, `SWITCH_EXPRESSION`, `BLOCK`. |
| `SwitchTree` | AST node của switch statement. |
| `SwitchExpressionTree` | AST node của switch expression. |
| `BlockTree` | Node của block `{ ... }`, có method `getStatements()` riêng. |
| `StatementTree` | Kiểu cha của statement nodes. |
| `JavacTask` | Công cụ parse/analyze Java source từ compiler. |
| `TreePathScanner` | Visitor/AST traversal, có thể override `visitCase`. |
| `ToolProvider` | Lấy system Java compiler từ JDK. |

**RULE** và **STATEMENT** là tên hai hình thức cú pháp của case, **không phải** tên của hai loại switch. Bản thân switch statement cũng cho phép cả RULE và STATEMENT; switch expression cũng vậy.

## 3. Nhìn mã nguồn để phân biệt

RULE (mũi tên):

~~~java
int value = switch (number) {
    case 0 -> 10;
    case 1 -> {
        yield 20;
    }
    default -> 30;
};
~~~

STATEMENT (dấu hai chấm):

~~~java
int value = switch (number) {
    case 0:
        yield 10;
    case 1:
        yield 20;
    default:
        yield 30;
};
~~~

Đây là **hai mảnh code** nằm trong phương thức có biến `int number`. **Cả hai đều là switch expressions**: dấu `->`/`:` quyết định CaseKind, chứ không phải việc switch trả giá trị.

Trong switch statements, cả hai cũng hợp lệ:

~~~java
switch (number) {
    case 0 -> System.out.println("zero");
    default -> System.out.println("other");
}
~~~

~~~java
switch (number) {
    case 0:
        System.out.println("zero");
        break;
    default:
        System.out.println("other");
}
~~~

**Không được trộn `case 0 ->` và `case 1:` trong cùng một switch block.** Theo Java Language Specification, switch block dùng một trong hai hình thức: *switch rules* hoặc *switch labeled statement groups*.

### Bảng so sánh

| Thuộc tính | RULE | STATEMENT |
| --- | --- | --- |
| Hình thức | `case X -> body` | `case X: statements` |
| Giá trị enum | `CaseTree.CaseKind.RULE` | `CaseTree.CaseKind.STATEMENT` |
| Đọc nội dung | `caseTree.getBody()` | `caseTree.getStatements()` |
| Method không áp dụng | `getStatements() == null` | `getBody() == null` |
| Dạng dữ liệu | Một `Tree`: expression/statement/block | `List<? extends StatementTree>` |
| Rỗng | Block trong RULE có thể có list rỗng nếu hợp ngữ cảnh | List của case có thể rỗng, ví dụ grouped labels |
| Fall-through sang case kế | Không | Có thể |
| Hợp lệ trong switch statement | Có | Có |
| Hợp lệ trong switch expression | Có | Có |
| Kiểm tra khi làm linter | Body kind/descendants | Danh sách statements, flow giữa labels |

## 4. Hợp đồng API: `getCaseKind()`, `getBody()`, `getStatements()`

Các method:

~~~java
CaseTree.CaseKind kind = caseTree.getCaseKind();
Tree body = caseTree.getBody();
List<? extends StatementTree> statements =
        caseTree.getStatements();
~~~

Đây là **mảnh Java**, giả định `caseTree` được khai báo trước và có các import tương ứng.

Theo Javadoc:

- `getCaseKind()` trả `RULE` hoặc `STATEMENT`.
- Với **RULE**, `getBody()` trả `Tree` ở sau mũi tên, còn `getStatements() == null`.
- Với **STATEMENT**, `getStatements()` trả list (có thể `size()==0`), còn `getBody() == null`.
- `CaseTree.getStatements()` khác `BlockTree.getStatements()`: một RULE có body là block nhưng `CaseTree.getStatements()` **vẫn null**.
- `getExpressions()` trả constant expression labels; với `default` nó trả list rỗng.
- `getLabels()` và `getGuard()` là API chính thức từ Java 21, dùng cho case labels/guards hiện đại.
- `getExpression()` là **deprecated**, không nên dùng khi viết công cụ mới.

Mảnh xử lý an toàn:

~~~java
if (caseTree.getCaseKind() == CaseTree.CaseKind.RULE) {
    Tree body = caseTree.getBody();
    // Phân tích body theo Tree.Kind.
} else {
    List<? extends StatementTree> statements =
            caseTree.getStatements();
    // statements có thể rỗng.
}
~~~

**Sai phổ biến:**

~~~java
caseTree.getStatements().size(); // RULE -> NullPointerException
caseTree.getBody().getKind();     // STATEMENT -> NullPointerException
~~~

Hai dòng trên là **mảnh code cố ý sai**, cho thấy cần check CaseKind trước khi đọc.

### `getKind()` không phải `getCaseKind()`

~~~java
caseTree.getKind();      // Tree.Kind.CASE
caseTree.getCaseKind();  // CaseTree.CaseKind.RULE hoặc STATEMENT
~~~

`Tree.getKind()` nói node thuộc loại **CASE**, không nói hình thức `:` hay `->`. Không đem `Tree.Kind.CASE` so với `CaseTree.CaseKind.RULE` vì đó là hai enum khác nhau.

## 5. RULE body không nhất thiết là một block

Các hình thức arrow rules:

~~~java
int result = switch (code) {
    case 0 -> 10;
    case 1 -> {
        int temporary = 19;
        yield temporary + 1;
    }
    default -> throw new IllegalArgumentException();
};
~~~

Đây là **mảnh code** với biến `code` đã có.

| Case | `getBody().getKind()` |
| --- | --- |
| `case 0 -> 10;` | `Tree.Kind.INT_LITERAL` |
| `case 1 -> { ... }` | `Tree.Kind.BLOCK` |
| `default -> throw ...;` | `Tree.Kind.THROW` |
| `case 2 -> System.out.println(2);` trong switch statement | `Tree.Kind.EXPRESSION_STATEMENT` |

Hợp đồng `CaseTree.getBody()` trả về `Tree`, không luôn là `BlockTree`. Chỉ khi body là `BlockTree` mới gọi `BlockTree.getStatements()`:

~~~java
Tree body = caseTree.getBody();
if (body instanceof BlockTree block) {
    for (StatementTree statement : block.getStatements()) {
        // Phân tích statement trong body block.
    }
}
~~~

Đây là mảnh code đặt trong nhánh RULE, giả định có import. Pattern matching `instanceof` đã chính thức từ Java 16 và chạy trên Java 17. **Không** dùng `caseTree.getStatements()` để đọc body block của RULE.

RULE **không có fall-through** sang rule kế tiếp. Arrow block vẫn có thể `throw`, `yield` hoặc `return` tùy ngữ cảnh. Trong switch statement, biểu thức sau arrow phải là *statement expression* như method invocation/assignment; `case 1 -> 10;` ở switch statement là cú pháp không hợp lệ, nhưng hợp lệ với switch expression.

## 6. STATEMENT và danh sách statements rỗng

Colon-style switch statement:

~~~java
switch (number) {
    case 0:
    case 1:
        System.out.println("zero or one");
        break;
    default:
        System.out.println("other");
}
~~~

Đây là mảnh code có biến `int number`.

| Case | CaseKind | `getStatements().size()` |
| --- | --- | ---: |
| `case 0:` | STATEMENT | 0 |
| `case 1:` | STATEMENT | 2 |
| `default:` | STATEMENT | 1 |

`case 0:` có list rỗng, không phải `null`. Nó cố tình rơi vào nhánh xử lý chung với `case 1:`. Nếu `number==0`, các lệnh sau `case 1:` sẽ chạy cho tới `break`.

Phân biệt:

- RULE: `getStatements()==null` do API không dùng trường này.
- STATEMENT: `getStatements()` là một list, **có thể trống**.
- Nhãn `default:` vẫn hợp lệ dù `getExpressions()` rỗng.

Khi phân tích fall-through, đừng kết luận mọi statement group không có `break` là bug: có thể kết thúc bằng `return`, `throw`, `yield` hoặc logic phân nhánh. AST cho biết cấu trúc; kết luận control-flow cần phân tích thêm.

### `yield` khác `break`

Trong switch expression, `yield expression;` đưa giá trị từ block hoặc colon statement group ra biểu thức switch. Trong switch statement colon, `break;` thường kết thúc switch và tránh rơi sang nhánh kế.

Cú pháp `break 10;` để trả giá trị từng được thử nghiệm trong quá trình phát triển switch expressions, nhưng **không phải cú pháp Java 14+ chính thức**. Hãy dùng `yield 10;`.

## 7. Hai chiều độc lập: outer switch và inner case

Đây là điểm trung tâm của bài:

| Switch bên ngoài | CaseKind | Ví dụ |
| --- | --- | --- |
| `SwitchTree` (switch statement) | RULE | `case 1 -> System.out.println("x");` |
| `SwitchTree` (switch statement) | STATEMENT | `case 1: System.out.println("x"); break;` |
| `SwitchExpressionTree` (switch expression) | RULE | `case 1 -> 10;` |
| `SwitchExpressionTree` (switch expression) | STATEMENT | `case 1: yield 10;` |

**Cả bốn tổ hợp đều hợp lệ.** Trên AST:

- `SwitchTree.getKind() == Tree.Kind.SWITCH`.
- `SwitchExpressionTree.getKind() == Tree.Kind.SWITCH_EXPRESSION`.
- `CaseTree.getKind() == Tree.Kind.CASE`.
- `CaseTree.getCaseKind()` quyết định RULE hoặc STATEMENT.

Một analyzer muốn biết **loại switch** phải xem ancestor node qua `TreePathScanner.getCurrentPath()` hoặc visitor context. Không suy luận outer switch từ CaseKind.

### Ví dụ độc lập 1 — Switch statement chứa RULE, switch expression chứa STATEMENT

Tạo tệp **`SwitchFormVsCaseKindDemo.java`**:

~~~java
public class SwitchFormVsCaseKindDemo {
    static String ruleInStatement(int value) {
        StringBuilder answer = new StringBuilder();
        switch (value) {
            case 1 -> answer.append("one");
            default -> answer.append("other");
        }
        return answer.toString();
    }

    static int statementInExpression(int value) {
        return switch (value) {
            case 1:
                yield 100;
            default:
                yield -1;
        };
    }

    public static void main(String[] args) {
        System.out.println("statementWithRule="
                + ruleInStatement(1));
        System.out.println("expressionWithColon="
                + statementInExpression(1));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 SwitchFormVsCaseKindDemo.java
java SwitchFormVsCaseKindDemo
~~~

**Stdout chính xác:**

~~~text
statementWithRule=one
expressionWithColon=100
~~~

Đây là minh chứng chạy được rằng **loại switch không quyết định CaseKind**. Một linter chỉ dựa vào tên `SwitchExpressionTree` rồi tự gán RULE sẽ phân tích sai chương trình thứ hai.

## 8. Ví dụ độc lập 2 — Tạo và duyệt AST bằng JDK Compiler API

Ví dụ này không yêu cầu người học tạo file source được phân tích: toàn bộ source `Example` ở trong một Java text block. `JavacTask.parse()` dựng AST; `TreePathScanner.visitCase()` duyệt các nhánh.

Tạo tệp **`CaseKindAstDemo.java`**:

~~~java
import com.sun.source.tree.CaseTree;
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.Tree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.TreePathScanner;
import java.net.URI;
import java.util.List;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.ToolProvider;

public class CaseKindAstDemo {
    static JavaFileObject source(String name, String code) {
        return new SimpleJavaFileObject(
                URI.create("string:///" + name + ".java"),
                JavaFileObject.Kind.SOURCE) {
            @Override
            public CharSequence getCharContent(boolean ignored) {
                return code;
            }
        };
    }

    public static void main(String[] args) throws Exception {
        String code = """
            class Example {
                int value(int x) {
                    return switch (x) {
                        case 0 -> 10;
                        case 1 -> { yield 20; }
                        default -> 30;
                    };
                }
                void action(int x) {
                    switch (x) {
                        case 0:
                            System.out.println("zero");
                            break;
                        default:
                            System.out.println("other");
                    }
                }
            }
            """;

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "A JDK with jdk.compiler is required");
        }

        JavacTask task = (JavacTask) compiler.getTask(
                null, null, null,
                List.of("-proc:none", "--release", "17"),
                null, List.of(source("Example", code)));

        for (CompilationUnitTree unit : task.parse()) {
            new TreePathScanner<Void, Void>() {
                @Override
                public Void visitCase(CaseTree node, Void ignored) {
                    if (node.getCaseKind()
                            == CaseTree.CaseKind.RULE) {
                        Tree body = node.getBody();
                        System.out.println("RULE body="
                                + body.getKind()
                                + " statements="
                                + node.getStatements());
                    } else {
                        System.out.println("STATEMENT body="
                                + node.getBody()
                                + " statements="
                                + node.getStatements().size());
                    }
                    return super.visitCase(node, ignored);
                }
            }.scan(unit, null);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK đầy đủ hỗ trợ Java 17:

~~~bash
javac --release 17 CaseKindAstDemo.java
java CaseKindAstDemo
~~~

**Stdout chính xác, đã chạy trên OpenJDK 21:**

~~~text
RULE body=INT_LITERAL statements=null
RULE body=BLOCK statements=null
RULE body=INT_LITERAL statements=null
STATEMENT body=null statements=2
STATEMENT body=null statements=1
~~~

Giải thích:

1. Switch expression đầu có ba rules: literal `10`, block `{ yield 20; }` và literal `30`.
2. Các rules có `getBody()` theo từng `Tree.Kind`; `getStatements()` đều null.
3. Switch statement sau có hai colon cases, danh sách statements lần lượt dài 2 và 1, `getBody()` null.
4. Những `println("zero")` và `println("other")` nằm trong source của `Example` **không được thực thi**, vì `parse()` chỉ xây AST.
5. `ToolProvider.getSystemJavaCompiler()` có thể trả null trên runtime đã loại bỏ `jdk.compiler`, nên phải kiểm tra.
6. `-proc:none` tắt annotation processing; `--release 17` chọn source level ổn định và không cần `--enable-preview`.

**Parsing chưa đảm bảo semantic correctness.** Mã có thể parse nhưng sai type, duplicate labels, pattern dominance hoặc không exhaustive. Công cụ cần diagnostics và `analyze()` khi mục tiêu gồm semantic validation.

## 9. Ví dụ độc lập 3 — Một STATEMENT có zero statements

Tạo **`ColonEmptyGroupDemo.java`**:

~~~java
import com.sun.source.tree.CaseTree;
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.TreePathScanner;
import java.net.URI;
import java.util.List;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.ToolProvider;

public class ColonEmptyGroupDemo {
    public static void main(String[] args) throws Exception {
        String code = """
            class Example {
                void handle(int n) {
                    switch (n) {
                        case 0:
                        case 1:
                            System.out.println("shared");
                            break;
                        default:
                            System.out.println("other");
                    }
                }
            }
            """;

        JavaFileObject src = new SimpleJavaFileObject(
                URI.create("string:///Example.java"),
                JavaFileObject.Kind.SOURCE) {
            @Override
            public CharSequence getCharContent(boolean ignore) {
                return code;
            }
        };

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler required");
        }
        JavacTask task = (JavacTask) compiler.getTask(
                null, null, null,
                List.of("-proc:none", "--release", "17"),
                null, List.of(src));

        for (CompilationUnitTree unit : task.parse()) {
            new TreePathScanner<Void, Void>() {
                @Override
                public Void visitCase(CaseTree node, Void unused) {
                    System.out.println(node.getCaseKind()
                            + " labels=" + node.getExpressions().size()
                            + " statements="
                            + node.getStatements().size());
                    return super.visitCase(node, unused);
                }
            }.scan(unit, null);
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 ColonEmptyGroupDemo.java
java ColonEmptyGroupDemo
~~~

**Stdout chính xác, đã chạy trên OpenJDK 21:**

~~~text
STATEMENT labels=1 statements=0
STATEMENT labels=1 statements=2
STATEMENT labels=0 statements=1
~~~

Ý nghĩa:

- `case 0:` là STATEMENT và có list statements **rỗng**.
- `case 1:` cũng STATEMENT, có hai statements dùng chung.
- `default:` là STATEMENT, có một statement; `getExpressions()` rỗng vì default không phải constant expression label.
- `getStatements().size()==0` không đồng nghĩa RULE; RULE trả **null**.
- `getExpressions().size()==0` không đồng nghĩa “nhánh không có label”; default là label hợp lệ.

## 10. Đọc labels đúng API khi JDK thay đổi

`CaseTree.getExpression()` là API **deprecated**; nó chỉ trả biểu thức đầu tiên và không đáp ứng nhiều labels hoặc pattern cases. Với mã Java 17 có constant labels, dùng:

~~~java
List<? extends ExpressionTree> expressions =
        caseTree.getExpressions();
~~~

Đây là mảnh code cần import `ExpressionTree` và `List`. `case 1, 2 -> ...` có nhiều expression labels, `default -> ...` thì rỗng.

### JDK 21+ pattern matching for switch

**JEP 441** chuẩn hóa pattern matching for switch ở Java 21. Case có thể dùng type patterns, `case null` và `when` guard; Compiler Tree API hiện hành có:

- `caseTree.getLabels()`: danh sách các `CaseLabelTree`, kể cả default/pattern.
- `caseTree.getGuard()`: biểu thức guard của case hoặc null.
- `getExpressions()`: phù hợp constant-case expressions, **không là API tổng quát cho mọi pattern label**.
- `getCaseKind()`: vẫn là cách phân biệt RULE/STATEMENT, không phụ thuộc labels/guards.

Không viết code `--release 17` gọi các API label/guard Java 21 rồi coi đó là API ổn định ở 17. Dùng JDK 21+ cho pattern switch chính thức, không dựa vào preview cũ.

### Ví dụ độc lập 4 — JDK21 pattern labels và guards

Tạo **`ModernCaseLabelsDemo.java`**:

~~~java
import com.sun.source.tree.CaseTree;
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.TreePathScanner;
import java.net.URI;
import java.util.List;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.ToolProvider;

public class ModernCaseLabelsDemo {
    public static void main(String[] args) throws Exception {
        String code = """
            class Example21 {
                static int classify(Object value) {
                    return switch (value) {
                        case null -> 0;
                        case String s when !s.isEmpty() -> 1;
                        default -> -1;
                    };
                }
            }
            """;

        JavaFileObject file = new SimpleJavaFileObject(
                URI.create("string:///Example21.java"),
                JavaFileObject.Kind.SOURCE) {
            @Override
            public CharSequence getCharContent(boolean ignored) {
                return code;
            }
        };

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK required");
        }
        JavacTask task = (JavacTask) compiler.getTask(
                null, null, null,
                List.of("-proc:none", "--release", "21"),
                null, List.of(file));

        for (CompilationUnitTree unit : task.parse()) {
            new TreePathScanner<Void, Void>() {
                @Override
                public Void visitCase(CaseTree node, Void ignored) {
                    System.out.println("kind=" + node.getCaseKind()
                            + " labels=" + node.getLabels().size()
                            + " guard=" + (node.getGuard() != null));
                    return super.visitCase(node, ignored);
                }
            }.scan(unit, null);
        }
    }
}
~~~

Chạy bằng JDK 21+:

~~~bash
javac --release 21 ModernCaseLabelsDemo.java
java ModernCaseLabelsDemo
~~~

**Stdout chính xác, đã chạy trên OpenJDK 21:**

~~~text
kind=RULE labels=1 guard=false
kind=RULE labels=1 guard=true
kind=RULE labels=1 guard=false
~~~

Cả ba case đều RULE vì dùng `->`; chỉ case `String s when ...` có guard. Guard không làm thay đổi CaseKind. Không chạy `javac --release 21` bằng compiler JDK 17, vì 17 chưa hỗ trợ release 21.

## 11. Cách viết visitor/linter

Thay vì tìm `"case ..."` bằng regex, dùng `visitCase` để phân tích đúng cấu trúc kể cả source nhiều dòng, comments, nested switches và pattern labels.

Mẫu xử lý:

~~~java
@Override
public Void visitCase(CaseTree node, Void unused) {
    switch (node.getCaseKind()) {
        case RULE -> {
            Tree body = node.getBody();
            // Kiểm tra body.getKind() và các descendant nodes.
        }
        case STATEMENT -> {
            for (StatementTree statement : node.getStatements()) {
                // Kiểm tra các statements.
            }
        }
    }
    return super.visitCase(node, unused);
}
~~~

Đây là **mảnh code cần đặt trong một TreePathScanner class**, không phải chương trình độc lập. `super.visitCase` tiếp tục duyệt descendant nodes; nếu bạn tự `scan(body,...)` rồi lại `super.visitCase`, có thể **đếm/kiểm tra node hai lần**.

### Khi cần xác định outer switch

`TreePathScanner.getCurrentPath()` trả path hiện tại; đi qua các ancestor nodes để tìm `SwitchTree` hoặc `SwitchExpressionTree` gần nhất. Đó là cách xác định outer switch **độc lập với** `CaseKind`. Dùng `Tree.Kind.SWITCH` và `Tree.Kind.SWITCH_EXPRESSION` đúng mục đích, không đoán bằng dấu colon/arrow.

### Cảnh báo fall-through phải có ngữ nghĩa

Để xây rule “thiếu break”:

1. Đọc CaseKind, bỏ qua nguy cơ fall-through giữa các RULE.
2. Với STATEMENT, đọc `getStatements()` và xem các grouped labels.
3. Kiểm tra đường điều khiển: `break`/`return`/`throw`/`yield`, vòng lặp, if/else và exception paths.
4. Không đánh dấu `case 0: case 1: ...` có list rỗng là bug tự động.
5. Nếu tự động chuyển colon switch thành arrow switch, kiểm tra **semantics không đổi**; fall-through có chủ ý có thể bị mất.
6. Khi source có pattern variables (Java 21+), tôn trọng scoping/dominance/fall-through rules của JLS.

Ví dụ:

~~~java
switch (x) {
    case 0:
    case 1:
        run();
        break;
    default:
        other();
}
~~~

Đây là mảnh code có biến và phương thức giả định. `case 0:` không có statement, nhưng **đó là cách gom nhãn chủ ý**. Regex “case thiếu break ngay dưới nhãn” sẽ gây false positive.

## 12. Những lỗi phổ biến

| Lỗi | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| So `getKind()` với RULE | `getKind()` trả `Tree.Kind.CASE` | Dùng `getCaseKind()`. |
| So `getCaseKind()` với `Tree.Kind.CASE` | Nhầm hai enum | Phân biệt loại node và case form. |
| `getStatements().size()` ở RULE | Trả null | Chỉ đọc với STATEMENT. |
| `getBody().getKind()` ở STATEMENT | Trả null | Chỉ đọc với RULE. |
| Cast RULE body luôn thành `BlockTree` | Body có thể là literal/throw/expression statement | Test `Tree.Kind` hoặc `instanceof`. |
| Coi STATEMENT luôn có statements | Grouped label có list rỗng | Cho phép size=0. |
| Coi RULE = switch expression | Switch statement cũng dùng RULE | Xem ancestor switch riêng. |
| Coi STATEMENT = switch statement | Switch expression cũng dùng colon + yield | Xem ancestor switch riêng. |
| Trộn `:` với `->` trong một switch block | Không đúng JLS | Chọn một hình thức mỗi switch block. |
| Thêm `break` vào arrow case | RULE không fall-through | Không thêm vô lý. |
| Dùng `break value;` | Preview cũ, không còn cú pháp chính thức | Dùng `yield value;`. |
| Dùng `getExpression()` | Deprecated | `getExpressions()` hoặc `getLabels()`. |
| Dùng `getExpressions()` cho mọi pattern labels | API không mô tả đầy đủ pattern | Java21+ dùng `getLabels()`. |
| Dùng `getLabels()` ở `--release 17` | API ổn định từ Java21 | Target Java21+ khi cần. |
| Không kiểm tra compiler null | Runtime tùy biến thiếu `jdk.compiler` | Dùng JDK đầy đủ/module hợp lệ. |
| `parse()` là đủ để chứng minh source compile | Parsing khác semantic analysis | Thu diagnostics và `analyze()`. |
| Scan cùng descendants nhiều lần | Vừa tự traverse vừa gọi `super.visitCase` | Chọn một traversal pattern. |
| Dò case bằng regex | Không hiểu comments, strings, nesting | Dùng AST API. |

## 13. Kiểm thử ranh giới

| Source case | CaseKind | Hành vi AST |
| --- | --- | --- |
| `case 0 -> 10;` | RULE | Body `INT_LITERAL`, statements null. |
| `case 0 -> { yield 10; }` | RULE | Body `BLOCK`; block chứa `YieldTree`. |
| `case 0 -> throw new IllegalStateException();` | RULE | Body `THROW`. |
| `case 0 -> println();` trong switch statement | RULE | Body expression statement. |
| `case 0: println(); break;` | STATEMENT | Body null, 2 statements. |
| `case 0: case 1: println(); break;` | STATEMENT | List 0 rồi list 2. |
| `default: println();` | STATEMENT | Expression labels rỗng, 1 statement. |
| `case 1: yield 10;` trong switch expression | STATEMENT | List chứa `YieldTree`. |
| `case String s when ... -> 1;` Java21+ | RULE | Pattern label + guard, body expression. |

Một test AST đúng phải xác minh **cả bốn tổ hợp** outer switch statement/expression × CaseKind RULE/STATEMENT, thay vì suy luận từ một ví dụ thường gặp.

## 14. Cách chạy các demo

Mỗi `public class` phải được đặt trong file trùng tên và chạy từ thư mục chứa file đó. Các ví dụ dùng APIs công khai của JDK, không cần dependency ngoài hoặc preview flags.

Java 17:

~~~bash
javac --release 17 SwitchFormVsCaseKindDemo.java
java SwitchFormVsCaseKindDemo

javac --release 17 CaseKindAstDemo.java
java CaseKindAstDemo

javac --release 17 ColonEmptyGroupDemo.java
java ColonEmptyGroupDemo
~~~

Java 21+:

~~~bash
javac --release 21 ModernCaseLabelsDemo.java
java ModernCaseLabelsDemo
~~~

Bốn demo đã được biên dịch và chạy thực tế trên **OpenJDK 21**. Với các demo parser, những đoạn code `Example` nằm trong `String` chỉ được phân tích cú pháp, **không được thực thi**.

Nếu xây chương trình analyzer dưới dạng named module, khai báo dependencies:

~~~java
module org.example.asttool {
    requires java.compiler;
    requires jdk.compiler;
}
~~~

Đây là **module descriptor minh họa**, không cần khi chạy demo classpath. `java.compiler` chứa `javax.tools`; `jdk.compiler` chứa `com.sun.source.tree` và `com.sun.source.util`.

## 15. Bài tập có đáp án

**1. `case 1 -> 10;` là gì?** — RULE. Body là expression; không dùng `getStatements()`.

**2. `case 1: yield 10;` trong switch expression là gì?** — STATEMENT. Switch expression có thể dùng colon style.

**3. `getStatements() == null` nói gì?** — Theo contract là RULE; nếu list rỗng không null có thể là STATEMENT grouped label.

**4. RULE có `{ int x=1; yield x; }` thì đọc statements thế nào?** — Đọc `getBody()`, nếu body là `BlockTree` thì gọi `block.getStatements()`; `CaseTree.getStatements()` vẫn null.

**5. `Tree.Kind.CASE` có nói nhánh dùng `:` hay `->` không?** — Không, phải dùng `getCaseKind()`.

**6. Một `case 0:` có list rỗng trước `case 1:`, chắc chắn bug?** — Không; có thể là grouped labels với intentional fall-through.

**7. `getExpression()` có nên dùng trong analyzer mới không?** — Không; deprecated. Dùng `getExpressions()` cho constant labels hoặc `getLabels()` Java21+.

**8. `case String s when !s.isEmpty() -> 1` ở Java21 trả CaseKind gì?** — RULE; `getGuard()!=null`.

**9. Vì sao output của `CaseKindAstDemo` không có `zero`?** — Chương trình chỉ parse source `Example`, không thực thi method của nó.

**10. Có thể đổi mọi `case X:` thành `case X ->` bằng find-and-replace không?** — Không; fall-through và control flow có thể thay đổi, cần semantic analysis.

## 16. Checklist sử dụng đúng

- [ ] Source/API phù hợp Java 14+ chính thức; không dựa preview cũ?
- [ ] `CaseTree.getCaseKind()` dùng để quyết định RULE/STATEMENT?
- [ ] `Tree.getKind()` chỉ dùng cho node kind (`CASE`, `SWITCH`, `BLOCK`...)?
- [ ] RULE lấy `getBody()`, không truy cập `getStatements()` như list?
- [ ] STATEMENT lấy `getStatements()`, không gọi `getBody().getKind()`?
- [ ] STATEMENT list rỗng được chấp nhận?
- [ ] RULE body được kiểm tra theo `Tree.Kind` trước khi cast?
- [ ] Outer `SwitchTree`/`SwitchExpressionTree` được phân biệt độc lập?
- [ ] Không trộn hai case forms trong một switch block?
- [ ] Có hiểu `break`, `yield` và fall-through?
- [ ] API deprecated `getExpression()` đã được thay thế?
- [ ] Với pattern switch Java21+, dùng `getLabels()`/`getGuard()`?
- [ ] Compiler và `--release` tương thích source level?
- [ ] Có kiểm tra `ToolProvider.getSystemJavaCompiler()` không null?
- [ ] Nếu cần semantic correctness, có diagnostics và `analyze()`?
- [ ] Visitor không traverse descendants hai lần?
- [ ] Có tests cho arrow literal/block/throw, colon rỗng, default và pattern guard?

## 17. Tài liệu chính thức còn áp dụng

1. [Oracle JDK 25 — `CaseTree`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/tree/CaseTree.html): `getCaseKind`, `getBody`, `getStatements`, `getExpressions`, `getLabels`, `getGuard`.
2. [Oracle JDK 25 — `CaseTree.CaseKind`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/tree/CaseTree.CaseKind.html): hai dạng RULE và STATEMENT.
3. [Oracle JDK 14 — `CaseTree`](https://docs.oracle.com/en/java/javase/14/docs/api/jdk.compiler/com/sun/source/tree/CaseTree.html): đối chiếu API trong ngữ cảnh module Java 14.
4. [OpenJDK JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): hoàn thiện switch expression/arrow rules/`yield` ở Java 14.
5. [JLS SE 25 — `14.11 Switch Statements`](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.11): switch rules, statement groups và fall-through.
6. [JLS SE 25 — `15.28 Switch Expressions`](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.28): expression switch và `yield`.
7. [Oracle JDK 25 — `TreePathScanner`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/util/TreePathScanner.html): visitor và AST traversal.
8. [Oracle JDK 25 — `JavacTask`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/util/JavacTask.html): `parse`/`analyze`.
9. [Oracle JDK 25 — `ToolProvider`](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/ToolProvider.html): compiler provider có thể null khi runtime thiếu `jdk.compiler`.
10. [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): pattern switch và `when` guards chính thức từ Java 21.

**Kết luận:** Với `CaseTree`, **RULE = `->` → đọc `getBody()`**; **STATEMENT = `:` → đọc `getStatements()`**. Một switch statement hoặc switch expression đều có thể chứa cả hai dạng tùy cách viết block. Đừng nhầm `Tree.Kind` với `CaseKind`, đừng dereference những method trả null cho dạng case không phù hợp, và dùng các API nhãn hiện đại theo đúng JDK khi phân tích pattern switch.
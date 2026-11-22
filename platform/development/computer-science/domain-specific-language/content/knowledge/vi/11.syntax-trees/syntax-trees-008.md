# Visitor và listener

## 1. Vì sao cần Visitor và Listener khi xử lý cây cú pháp?

Khi một ngôn ngữ chuyên biệt miền (Domain-Specific Language — DSL) được phân tích, parser thường tạo ra một cấu trúc cây để biểu diễn nội dung nguồn. Cấu trúc đó có thể là **parse tree** phản ánh các production của grammar hoặc **Abstract Syntax Tree (AST)** tập trung vào ý nghĩa của chương trình.

Sau khi cây được tạo, hệ thống cần thực hiện nhiều công việc:

- Tính giá trị của biểu thức.
- Kiểm tra kiểu và quy tắc nghiệp vụ.
- Thu thập tên biến, hàm, kiểu hoặc khai báo.
- Xây dựng bảng ký hiệu và kiểm tra phạm vi.
- Chuyển đổi cây thành một biểu diễn trung gian.
- Sinh mã nguồn, SQL hoặc cấu hình.
- In lại DSL theo một định dạng thống nhất.
- Tìm vị trí và giải thích lỗi.

Nếu mỗi công việc tự duyệt cây theo cách riêng, mã nguồn dễ lặp lại, khó bảo trì và có thể xử lý các loại node không nhất quán. **Visitor** và **Listener** là hai mẫu tổ chức việc duyệt cây, giúp tách cấu trúc cây khỏi các thao tác cần thực hiện trên cây.

Hai mẫu có mục tiêu gần nhau nhưng cách điều khiển khác nhau:

- Visitor thường để thao tác chủ động gọi hàm tương ứng cho từng node và nhận kết quả trả về.
- Listener thường nhận các callback khi bộ duyệt đi vào hoặc đi ra khỏi node; một walker điều khiển thứ tự duyệt.

Trong hệ sinh thái ANTLR, hai cách này được cung cấp phổ biến cho parse tree. Trong AST tự xây dựng bằng Java, Visitor cũng là một mẫu thiết kế hướng đối tượng thường gặp.

## 2. Parse tree và AST trước khi chọn cách duyệt

Visitor hoặc Listener không thay thế parser. Chúng hoạt động sau khi parser đã tạo ra cấu trúc cây.

### 2.1 Parse tree

Parse tree thể hiện cách chuỗi token khớp với grammar. Các node thường tương ứng với rule hoặc thành phần cú pháp.

Ví dụ grammar:

~~~text
expression
    : expression '+' term
    | term
    ;

term
    : NUMBER
    ;
~~~

Với đầu vào:

~~~text
1 + 2
~~~

Parse tree có thể giữ các node cho rule expression, term, token cộng và token số. Cấu trúc này hữu ích khi cần biết chính xác người dùng đã viết gì và cú pháp nào đã được áp dụng.

### 2.2 Abstract Syntax Tree

AST loại bỏ nhiều chi tiết cú pháp không cần cho các bước xử lý ngữ nghĩa. Cùng biểu thức trên có thể được biểu diễn:

~~~text
Add
├── Number(1)
└── Number(2)
~~~

AST tập trung vào phép cộng và hai toán hạng. Nó không nhất thiết giữ dấu ngoặc, dấu phân cách hoặc mọi node trung gian của grammar.

### 2.3 Nên duyệt cây nào?

| Nhu cầu | Cấu trúc thường phù hợp |
|---|---|
| Báo lỗi cú pháp theo đúng rule và token | Parse tree |
| Thu thập thông tin từ các callback parser | Parse tree |
| Tính toán hoặc kiểm tra biểu thức đã chuẩn hóa | AST |
| Sinh mã theo khái niệm miền | AST hoặc IR |
| In lại đúng hình thức nguồn | Parse tree có token và vị trí nguồn |
| Phân tích ngữ nghĩa độc lập grammar | AST hoặc IR |

Một pipeline thường dùng parse tree để xây AST, rồi dùng Visitor trên AST cho các bước semantic analysis, tối ưu hóa hoặc code generation. Tuy nhiên, DSL nhỏ có thể thao tác trực tiếp trên parse tree nếu cấu trúc grammar phù hợp.

## 3. Mẫu Visitor là gì?

Visitor là mẫu thiết kế cho phép định nghĩa các thao tác trên một cấu trúc node mà không đặt toàn bộ logic của từng thao tác vào các lớp node đó.

Một Visitor thường có:

1. Một interface hoặc abstract class khai báo phương thức xử lý cho từng loại node.
2. Các node cung cấp phương thức accept để gọi đúng phương thức Visitor.
3. Một lớp Visitor cụ thể cài đặt thao tác cần thực hiện.
4. Kết quả trả về có thể là giá trị tính toán, mô hình mới, chuỗi mã hoặc một đối tượng phân tích.

Ý tưởng dispatch:

~~~text
node.accept(visitor)
       |
       v
visitor.visitAdd(node)
       |
       +--> duyệt toán hạng trái
       |
       +--> duyệt toán hạng phải
       |
       v
    trả kết quả
~~~

Visitor thường phù hợp khi có một tập node tương đối ổn định nhưng cần nhiều thao tác khác nhau trên chúng.

## 4. Cài đặt Visitor đơn giản bằng Java

Giả sử AST của DSL có biểu thức số:

~~~java
interface Expression {
    <R> R accept(ExpressionVisitor<R> visitor);
}

interface ExpressionVisitor<R> {
    R visitNumber(NumberExpression expression);
    R visitAdd(AddExpression expression);
    R visitMultiply(MultiplyExpression expression);
}
~~~

Các node:

~~~java
final class NumberExpression implements Expression {
    private final int value;

    NumberExpression(int value) {
        this.value = value;
    }

    int value() {
        return value;
    }

    @Override
    public <R> R accept(ExpressionVisitor<R> visitor) {
        return visitor.visitNumber(this);
    }
}

final class AddExpression implements Expression {
    private final Expression left;
    private final Expression right;

    AddExpression(Expression left, Expression right) {
        this.left = left;
        this.right = right;
    }

    Expression left() {
        return left;
    }

    Expression right() {
        return right;
    }

    @Override
    public <R> R accept(ExpressionVisitor<R> visitor) {
        return visitor.visitAdd(this);
    }
}

final class MultiplyExpression implements Expression {
    private final Expression left;
    private final Expression right;

    MultiplyExpression(Expression left, Expression right) {
        this.left = left;
        this.right = right;
    }

    Expression left() {
        return left;
    }

    Expression right() {
        return right;
    }

    @Override
    public <R> R accept(ExpressionVisitor<R> visitor) {
        return visitor.visitMultiply(this);
    }
}
~~~

Điểm quan trọng là mỗi node tự chuyển quyền điều khiển đến phương thức Visitor phù hợp với loại node. Visitor không cần kiểm tra thủ công kiểu của từng node bằng chuỗi if hoặc instanceof.

### 4.1 Visitor tính giá trị

Ta có thể cài đặt một Visitor trả về Integer:

~~~java
final class EvaluationVisitor implements ExpressionVisitor<Integer> {
    @Override
    public Integer visitNumber(NumberExpression expression) {
        return expression.value();
    }

    @Override
    public Integer visitAdd(AddExpression expression) {
        int left = expression.left().accept(this);
        int right = expression.right().accept(this);
        return left + right;
    }

    @Override
    public Integer visitMultiply(MultiplyExpression expression) {
        int left = expression.left().accept(this);
        int right = expression.right().accept(this);
        return left * right;
    }
}
~~~

Sử dụng:

~~~java
Expression expression = new MultiplyExpression(
    new AddExpression(
        new NumberExpression(1),
        new NumberExpression(2)
    ),
    new NumberExpression(3)
);

int result = expression.accept(new EvaluationVisitor());
// result = 9
~~~

Visitor điều khiển cách kết hợp kết quả của các node con. Với node cộng, nó duyệt trái và phải rồi cộng hai kết quả. Với node nhân, nó nhân hai kết quả.

### 4.2 Visitor sinh chuỗi

Một thao tác khác trên cùng AST có thể sinh biểu thức dạng văn bản:

~~~java
final class PrintVisitor implements ExpressionVisitor<String> {
    @Override
    public String visitNumber(NumberExpression expression) {
        return Integer.toString(expression.value());
    }

    @Override
    public String visitAdd(AddExpression expression) {
        String left = expression.left().accept(this);
        String right = expression.right().accept(this);
        return "(" + left + " + " + right + ")";
    }

    @Override
    public String visitMultiply(MultiplyExpression expression) {
        String left = expression.left().accept(this);
        String right = expression.right().accept(this);
        return "(" + left + " * " + right + ")";
    }
}
~~~

Với cùng một cây, EvaluationVisitor trả về kết quả số, còn PrintVisitor trả về chuỗi. Cấu trúc AST không cần biết phép tính hoặc cách in.

### 4.3 Visitor thu thập thông tin

Không phải Visitor nào cũng trả về một giá trị đơn giản. Một Visitor có thể cập nhật một tập hợp hoặc một đối tượng kết quả:

~~~java
final class NodeCountVisitor implements ExpressionVisitor<Integer> {
    @Override
    public Integer visitNumber(NumberExpression expression) {
        return 1;
    }

    @Override
    public Integer visitAdd(AddExpression expression) {
        return 1
            + expression.left().accept(this)
            + expression.right().accept(this);
    }

    @Override
    public Integer visitMultiply(MultiplyExpression expression) {
        return 1
            + expression.left().accept(this)
            + expression.right().accept(this);
    }
}
~~~

Visitor này đếm số node trong cây. Các thao tác khác có thể thu thập identifier, số lượng literal, loại phép toán hoặc metadata.

## 5. Visitor có kiểu kết quả và Visitor không trả về giá trị

Trong Java, generic Visitor cho phép quy định kiểu kết quả:

~~~java
interface AstVisitor<R> {
    R visitNumber(NumberExpression node);
    R visitAdd(AddExpression node);
}
~~~

Ví dụ:

- Evaluator dùng AstVisitor<Integer> hoặc một kiểu kết quả miền.
- Printer dùng AstVisitor<String>.
- Validator có thể dùng AstVisitor<List<Diagnostic>>.
- Code generator có thể dùng AstVisitor<GeneratedCode>.

Nếu thao tác cần nhiều kết quả, có thể dùng một lớp kết quả riêng thay vì tuple hoặc biến mutable rải rác:

~~~java
record AnalysisResult(
    Type inferredType,
    List<Diagnostic> diagnostics
) {}
~~~

Visitor không trả về giá trị cũng có thể được biểu diễn bằng Void hoặc interface có phương thức void. Khi dùng Void, mỗi phương thức thường trả về null; trong Java, interface chuyên biệt có thể dễ đọc hơn nếu thao tác không có kết quả.

Nên chọn kiểu kết quả phản ánh rõ trách nhiệm của Visitor. Không nên dùng Object cho mọi thao tác nếu có thể dùng generic để compiler kiểm tra kiểu.

## 6. Thứ tự duyệt và quyền điều khiển trong Visitor

Visitor thường quyết định rõ cách duyệt các node con. Đây là điểm khác với Listener dựa trên walker.

### 6.1 Pre-order

Pre-order xử lý node cha trước, sau đó mới đến node con:

~~~java
Result visitAdd(AddExpression node) {
    before(node);
    Result left = node.left().accept(this);
    Result right = node.right().accept(this);
    return combine(node, left, right);
}
~~~

Thứ tự này hữu ích khi cần kiểm tra hoặc thiết lập trạng thái trước khi đi xuống cây.

### 6.2 Post-order

Post-order xử lý node con trước rồi mới tổng hợp tại node cha. Ví dụ evaluator thường cần giá trị của hai toán hạng trước khi thực hiện phép cộng.

~~~java
Result visitAdd(AddExpression node) {
    Result left = node.left().accept(this);
    Result right = node.right().accept(this);
    return add(left, right);
}
~~~

### 6.3 Dừng hoặc bỏ qua một nhánh

Visitor chủ động gọi node con nên có thể:

- Không duyệt một nhánh khi không cần.
- Chỉ duyệt một nhánh theo điều kiện.
- Dừng bằng cách trả kết quả sớm hoặc ném một exception điều khiển đã được thiết kế.
- Duyệt theo thứ tự khác với thứ tự lưu trong node nếu ngữ nghĩa cho phép.

Ví dụ, evaluator có thể short-circuit biểu thức AND: nếu vế trái false thì không cần đánh giá vế phải. Đây là một lý do quan trọng để Visitor tự điều khiển việc duyệt thay vì luôn đi qua mọi node.

## 7. Visitor trong AST có nhiều loại node

AST của DSL thực tế thường có nhiều nhóm node:

- Expression: literal, identifier, call, binary operation.
- Statement: assignment, conditional, loop hoặc action.
- Declaration: variable, function, policy, rule.
- Type: primitive, collection, domain-specific type.
- Metadata: annotation, comment hoặc source location.

Khi số node tăng, interface Visitor cần có phương thức tương ứng hoặc một chiến lược fallback.

Ví dụ:

~~~java
interface DslVisitor<R> {
    R visitLiteral(LiteralExpression node);
    R visitName(NameExpression node);
    R visitCall(CallExpression node);
    R visitBinary(BinaryExpression node);
    R visitRule(RuleDeclaration node);
    R visitPolicy(PolicyDeclaration node);
}
~~~

Một node mới thường yêu cầu cập nhật interface và các Visitor cụ thể. Điều này có thể tạo nhiều công việc khi AST thay đổi, nhưng cũng giúp compiler phát hiện thao tác nào chưa xử lý node mới nếu không có implementation mặc định.

### 7.1 Default method và fallback

Có thể cung cấp phương thức mặc định:

~~~java
interface DslVisitor<R> {
    R visitLiteral(LiteralExpression node);
    R visitBinary(BinaryExpression node);

    default R visitUnknown(AstNode node) {
        throw new UnsupportedOperationException(
            "Unsupported node: " + node.getClass().getSimpleName()
        );
    }
}
~~~

Fallback giảm công việc ban đầu nhưng có thể che giấu việc quên xử lý node mới. Với các bước quan trọng như semantic analysis hoặc code generation, nên để hành vi chưa hỗ trợ được phát hiện rõ ràng.

### 7.2 Visitor tổng quát và visitor theo nhóm

Với AST lớn, có thể chia visitor theo trách nhiệm:

- ExpressionVisitor xử lý biểu thức.
- StatementVisitor xử lý câu lệnh.
- DeclarationVisitor xử lý khai báo.
- TypeVisitor xử lý kiểu.

Việc chia nhỏ giúp interface dễ đọc và hạn chế một lớp phải biết mọi thành phần. Tuy nhiên, tránh tạo quá nhiều interface nhỏ khiến việc phối hợp và truyền kết quả trở nên phức tạp.

## 8. Mẫu Listener là gì?

Listener là cách xử lý cây bằng các callback được gọi khi walker đi qua node. Listener thường cung cấp hai sự kiện:

- **Enter:** walker vừa đi vào một node hoặc context.
- **Exit:** walker đã xử lý xong các node con và chuẩn bị rời node.

Với một cây:

~~~text
Add
├── Number(1)
└── Multiply
    ├── Number(2)
    └── Number(3)
~~~

Thứ tự callback dạng depth-first có thể là:

~~~text
enter Add
  enter Number(1)
  exit Number(1)
  enter Multiply
    enter Number(2)
    exit Number(2)
    enter Number(3)
    exit Number(3)
  exit Multiply
exit Add
~~~

Listener thường không tự gọi đệ quy sang node con. Walker chịu trách nhiệm đi qua cây và gọi callback đúng thứ tự. Listener phản ứng với sự kiện bằng cách cập nhật trạng thái, thu thập dữ liệu hoặc tạo cấu trúc khác.

## 9. Listener trong ANTLR

ANTLR có thể sinh Listener interface và BaseListener từ grammar. Mỗi parser rule thường có các callback enterRule và exitRule tương ứng.

Ví dụ grammar:

~~~text
grammar Calc;

program
    : expression EOF
    ;

expression
    : expression op=('*' | '/') expression
    | expression op=('+' | '-') expression
    | NUMBER
    ;

NUMBER
    : [0-9]+
    ;

WS
    : [ \\t\\r\\n]+ -> skip
    ;
~~~

Đây là grammar minh họa cho parser có hỗ trợ đệ quy trái trực tiếp và precedence. Với grammar thực tế, cần kiểm tra cách công cụ xử lý thứ tự toán tử và phiên bản ANTLR đang dùng.

Sau khi sinh mã, có thể mở rộng BaseListener:

~~~java
final class TraceListener extends CalcBaseListener {
    @Override
    public void enterExpression(CalcParser.ExpressionContext ctx) {
        System.out.println("enter expression");
    }

    @Override
    public void exitExpression(CalcParser.ExpressionContext ctx) {
        System.out.println("exit expression");
    }
}
~~~

Walker điều khiển quá trình:

~~~java
CalcLexer lexer = new CalcLexer(CharStreams.fromString("1 + 2 * 3"));
CommonTokenStream tokens = new CommonTokenStream(lexer);
CalcParser parser = new CalcParser(tokens);

CalcParser.ProgramContext tree = parser.program();

TraceListener listener = new TraceListener();
ParseTreeWalker.DEFAULT.walk(listener, tree);
~~~

Các lớp CalcLexer, CalcParser và CalcBaseListener là mã được ANTLR sinh từ grammar. Ví dụ giả định project đã cấu hình plugin và runtime ANTLR tương ứng.

## 10. Dùng Listener để xây dựng AST

Một ứng dụng phổ biến của Listener là chuyển parse tree thành AST. Vì walker đi theo thứ tự depth-first, listener có thể lưu kết quả của node con rồi ghép chúng khi nhận callback exit của node cha.

### 10.1 Ý tưởng dùng stack

Giả sử grammar có biểu thức gồm số và phép cộng. Khi đi vào hoặc đi ra các node:

1. Khi gặp literal số, tạo NumberExpression.
2. Đẩy node biểu thức tương ứng lên stack.
3. Khi hoàn tất một phép toán, lấy các node con theo đúng thứ tự và tạo node cha.
4. Đẩy node cha trở lại stack.

Với biểu thức phức tạp, phải dựa vào cấu trúc context và số toán hạng của production để lấy đúng node. Không nên giả định mọi rule đều có đúng hai node con.

### 10.2 Ví dụ Listener xây AST theo callback exit

Một ví dụ đơn giản với grammar chỉ có phép cộng:

~~~text
grammar SimpleCalc;

program
    : expression EOF
    ;

expression
    : expression '+' NUMBER
    | NUMBER
    ;

NUMBER
    : [0-9]+
    ;

WS
    : [ \\t\\r\\n]+ -> skip
    ;
~~~

Listener có thể lưu kết quả theo từng context:

~~~java
final class AstBuilder extends SimpleCalcBaseListener {
    private final Map<ParserRuleContext, Expression> values =
        new IdentityHashMap<>();

    @Override
    public void exitExpression(
        SimpleCalcParser.ExpressionContext ctx
    ) {
        if (ctx.NUMBER() != null) {
            int value = Integer.parseInt(ctx.NUMBER().getText());
            values.put(ctx, new NumberExpression(value));
            return;
        }

        Expression left = values.get(ctx.expression());
        int rightValue = Integer.parseInt(ctx.NUMBER().getText());
        Expression right = new NumberExpression(rightValue);

        values.put(ctx, new AddExpression(left, right));
    }

    Expression result(SimpleCalcParser.ProgramContext program) {
        return values.get(program.expression());
    }
}
~~~

Với grammar có đệ quy trái, ANTLR có thể tạo cấu trúc context lồng nhau theo từng phép mở rộng. Callback exit của context con xảy ra trước callback exit của context cha, vì vậy giá trị con đã có thể được tra cứu.

Đây là ví dụ minh họa cho một grammar rất nhỏ. Trong ứng dụng thực tế, có thể dùng context stack, map theo context hoặc visitor để lấy kết quả con. Cần xử lý rõ trường hợp lỗi parse, context thiếu node và token không hợp lệ.

### 10.3 Dùng Listener để thu thập khai báo

Listener cũng thuận tiện khi cần quét một lượt để thu thập thông tin:

~~~java
final class DeclarationCollector extends MyDslBaseListener {
    private final Set<String> names = new LinkedHashSet<>();

    @Override
    public void exitVariableDeclaration(
        MyDslParser.VariableDeclarationContext ctx
    ) {
        names.add(ctx.ID().getText());
    }

    Set<String> names() {
        return Set.copyOf(names);
    }
}
~~~

Sau khi walker hoàn tất, tập hợp names chứa các tên biến đã khai báo. Với phạm vi lồng nhau, một Set duy nhất có thể không đủ; cần dùng stack các scope hoặc một symbol table có cấu trúc.

## 11. Listener và quản lý trạng thái

Vì Listener phản ứng với sự kiện, trạng thái thường được lưu trong object Listener.

Các ví dụ:

- Stack biểu diễn phạm vi hiện tại.
- Map lưu kết quả của context.
- List lưu diagnostics.
- Bộ đếm theo dõi số node hoặc độ sâu.
- Bộ tích lũy tạo AST hoặc IR.

### 11.1 Stack cho phạm vi lồng nhau

Giả sử DSL có block:

~~~text
scope "outer" {
  let customer = ...
  scope "inner" {
    let order = ...
  }
}
~~~

Listener có thể đẩy scope khi enter và lấy scope ra khi exit:

~~~java
final class ScopeListener extends MyDslBaseListener {
    private final Deque<Scope> scopes = new ArrayDeque<>();

    @Override
    public void enterBlock(MyDslParser.BlockContext ctx) {
        scopes.push(new Scope(currentScope()));
    }

    @Override
    public void exitBlock(MyDslParser.BlockContext ctx) {
        scopes.pop();
    }

    private Scope currentScope() {
        return scopes.peek();
    }
}
~~~

Đây là khung ý tưởng. Cần tạo root scope trước khi walk, xử lý khai báo trùng và báo lỗi khi tham chiếu tên không tồn tại. Nếu scope được đẩy ở enter thì mọi khai báo bên trong block phải được thêm vào scope hiện tại.

### 11.2 Cẩn thận với trạng thái dùng lại

Một Listener thường giữ mutable state. Nếu dùng lại cùng instance cho nhiều lần walk mà không reset, dữ liệu của lần trước có thể ảnh hưởng lần sau.

Có thể chọn:

- Tạo Listener mới cho mỗi lần phân tích.
- Có phương thức reset được kiểm soát.
- Truyền một context kết quả riêng cho mỗi lần walk.

Không nên dùng cùng một Listener đồng thời từ nhiều thread trừ khi mọi trạng thái và thao tác được thiết kế thread-safe. Thông thường, tạo instance riêng cho mỗi lần parse dễ hiểu và an toàn hơn.

## 12. So sánh Visitor và Listener

| Tiêu chí | Visitor | Listener |
|---|---|---|
| Điều khiển duyệt | Visitor hoặc node chủ động gọi node con | Walker điều khiển thứ tự callback |
| Cách xử lý | Phương thức visit cho từng loại node | Callback enter/exit cho từng rule hoặc node |
| Kết quả trả về | Thường có kiểu kết quả rõ | Thường tích lũy qua trạng thái hoặc context |
| Bỏ qua nhánh | Chủ động không gọi node con | Phụ thuộc khả năng điều khiển walker hoặc cơ chế riêng |
| Short-circuit | Tự nhiên khi Visitor kiểm soát traversal | Cần cơ chế trạng thái hoặc walker tùy biến |
| Trạng thái | Có thể truyền qua tham số hoặc lưu trong Visitor | Thường lưu trong Listener và stack |
| Phù hợp | Tính toán, transform, in, sinh mã | Theo dõi sự kiện, thu thập, xử lý theo enter/exit |
| Cấu trúc được duyệt | AST hoặc parse tree | Thường parse tree trong parser generator |
| Độ phụ thuộc grammar | Tùy thiết kế AST; ANTLR visitor phụ thuộc rule context | Listener sinh từ grammar thường gắn trực tiếp với rule |

Không có quy tắc rằng Visitor luôn tốt hơn Listener hoặc ngược lại. Hãy chọn dựa trên kiểu kết quả, mức kiểm soát traversal, cách quản lý trạng thái và loại cây cần xử lý.

## 13. Visitor và Listener trong ANTLR

ANTLR có thể sinh cả hai dạng API từ cùng grammar nếu cấu hình sinh visitor được bật.

### 13.1 Listener

Listener có các callback enter và exit. Một ParseTreeWalker duyệt cây và gọi callback:

~~~java
ParseTreeWalker.DEFAULT.walk(listener, tree);
~~~

Listener không cần tự gọi hàm duyệt con. Nếu cần tính kết quả từ con lên cha, có thể lưu kết quả của context con trong map hoặc stack rồi tổng hợp tại callback exit.

### 13.2 Visitor

Visitor của ANTLR thường có các phương thức visit tương ứng với parser rule. Một visitor cụ thể có thể trả về kiểu kết quả R:

~~~java
final class EvalVisitor extends CalcBaseVisitor<Integer> {
    @Override
    public Integer visitProgram(CalcParser.ProgramContext ctx) {
        return visit(ctx.expression());
    }

    @Override
    public Integer visitNumber(CalcParser.NumberContext ctx) {
        return Integer.parseInt(ctx.NUMBER().getText());
    }

    @Override
    public Integer visitAdd(CalcParser.AddContext ctx) {
        int left = visit(ctx.left);
        int right = visit(ctx.right);
        return left + right;
    }
}
~~~

Tên context và trường như NumberContext, AddContext, left hoặc right phụ thuộc grammar và mã ANTLR sinh ra. Ví dụ này chỉ minh họa cách dùng visitor có kiểu kết quả.

Trong ANTLR, một số lớp BaseVisitor mặc định có thể gọi visitChildren. Nếu override một rule mà cần kết quả cụ thể, hãy kiểm tra cách aggregate kết quả con; không nên giả định giá trị trả về mặc định luôn là điều mong muốn.

### 13.3 Khác biệt khi đi qua cây

Với Visitor, người viết thường gọi visit trên node con:

~~~java
Integer left = visit(ctx.left);
Integer right = visit(ctx.right);
return left + right;
~~~

Với Listener, walker tự đi xuống các node con và gọi callback:

~~~java
@Override
public void enterAdd(CalcParser.AddContext ctx) {
    // Xử lý khi bắt đầu vào rule.
}

@Override
public void exitAdd(CalcParser.AddContext ctx) {
    // Xử lý sau khi các rule con đã được duyệt.
}
~~~

Visitor thuận tiện khi cần trả kết quả từ một nhánh. Listener thuận tiện khi cần quan sát toàn bộ sự kiện vào/ra mà không muốn tự điều khiển đệ quy.

## 14. Khi nào nên dùng Visitor?

Visitor thường là lựa chọn phù hợp khi:

### 14.1 Cần tính kết quả từ cây

Evaluator cần lấy kết quả của node con rồi tổng hợp tại node cha. Visitor có kiểu trả về giúp thể hiện trực tiếp quan hệ đó.

### 14.2 Cần nhiều phép xử lý trên cùng AST

Một AST có thể được dùng cho type checking, pretty printing, code generation và optimization. Mỗi thao tác có thể là một Visitor riêng, giúp giữ logic theo trách nhiệm.

### 14.3 Cần kiểm soát thứ tự duyệt

Visitor có thể duyệt có điều kiện, short-circuit hoặc bỏ qua nhánh. Điều này quan trọng khi một nhánh không cần đánh giá hoặc có thể gây tác dụng phụ.

### 14.4 Cần chuyển đổi cây

Visitor có thể tạo AST mới hoặc IR mới từ AST cũ. Ví dụ, constant folding thay biểu thức cộng hai literal bằng một literal kết quả.

### 14.5 Muốn dùng kiểu kết quả rõ ràng

Generic Visitor cho phép compiler kiểm tra loại kết quả của từng thao tác. Điều này hữu ích trong Java khi các bước xử lý tạo ra nhiều loại dữ liệu khác nhau.

## 15. Khi nào nên dùng Listener?

Listener thường phù hợp khi:

### 15.1 Cần phản ứng theo sự kiện enter/exit

Một số phân tích tự nhiên được mô tả bằng việc đi vào và rời khỏi block, rule hoặc declaration. Listener cung cấp callback theo thứ tự đó.

### 15.2 Cần quét cây để thu thập dữ liệu

Thu thập tên khai báo, import, annotation hoặc thống kê có thể thực hiện trong một lượt duyệt. Listener giúp tập trung việc thu thập vào các callback tương ứng.

### 15.3 Cần theo dõi phạm vi lồng nhau

Enter block có thể push scope; exit block có thể pop scope. Cấu trúc callback này tự nhiên với stack.

### 15.4 Muốn walker quản lý traversal

Khi không cần bỏ qua hoặc thay đổi thứ tự duyệt, để ParseTreeWalker điều khiển có thể làm code ngắn hơn và dễ hiểu.

### 15.5 Làm việc trực tiếp với parse tree do ANTLR sinh

Listener gắn với parser rule và context. Nếu nhiệm vụ là quan sát cấu trúc cú pháp hoặc thu thập dữ liệu theo grammar, đây là một lựa chọn thuận tiện.

## 16. Có thể kết hợp Visitor và Listener không?

Có. Một pipeline DSL có thể dùng Listener ở giai đoạn parse tree và Visitor ở giai đoạn AST:

~~~text
DSL source
    |
    v
Lexer / Parser
    |
    v
Parse tree
    |
    v
Listener
    |
    v
AST
    |
    +--> Type-check Visitor
    |
    +--> Evaluation Visitor
    |
    +--> Pretty-print Visitor
    |
    +--> Code-generation Visitor
~~~

Ví dụ:

- Listener thu thập declaration và xây cấu trúc AST từ parse tree.
- Visitor kiểm tra kiểu và trả về Type hoặc danh sách diagnostic.
- Visitor khác đánh giá biểu thức.
- Visitor khác sinh mã Java hoặc SQL.

Cách kết hợp này phân tách trách nhiệm: Listener làm việc gần grammar; Visitor làm việc với mô hình ngữ nghĩa ổn định hơn. Nhưng không cần thêm cả hai chỉ vì có thể. Với DSL nhỏ, một Visitor trên parse tree có thể đủ; với AST tự xây, một Listener có thể không cần thiết.

## 17. Xử lý lỗi trong Visitor và Listener

Lỗi có thể phát sinh ở nhiều giai đoạn:

- Parser không thể tạo parse tree hợp lệ.
- Listener gặp context thiếu token hoặc node do parser recovery.
- Visitor nhận AST có kiểu hoặc cấu trúc không hợp lệ.
- Evaluator gặp dữ liệu thiếu hoặc phép toán không xác định.
- Code generator gặp node chưa hỗ trợ.

### 17.1 Giữ vị trí nguồn

Node hoặc context nên giữ source span: file, dòng, cột, vị trí bắt đầu và kết thúc. Visitor hoặc Listener có thể dùng thông tin này để tạo diagnostic.

Ví dụ:

~~~java
record Diagnostic(
    String code,
    String message,
    SourceSpan span
) {}
~~~

Không nên chỉ ném một exception chung mà không cho biết node hoặc vị trí nguồn liên quan.

### 17.2 Tích lũy nhiều lỗi hay dừng ngay?

Validator thường có thể thu thập nhiều diagnostic trong một lượt để người dùng sửa nhiều lỗi cùng lúc. Evaluator hoặc code generator có thể cần dừng ngay khi gặp cấu trúc không thể xử lý an toàn.

Hãy chọn chính sách theo từng bước:

- Validation: thường tích lũy lỗi và cảnh báo.
- Evaluation: có thể trả kết quả lỗi có cấu trúc.
- Code generation: dừng nếu IR không hợp lệ hoặc target không hỗ trợ.

### 17.3 Parse tree sau error recovery

Parser có thể cố gắng phục hồi và tạo context chứa token tổng hợp hoặc node thiếu. Listener và Visitor phải biết liệu parser có lỗi hay không trước khi giả định mọi context đều đầy đủ.

Một cách an toàn là không chạy bước semantic processing nếu parse diagnostics chứa lỗi nghiêm trọng, hoặc chỉ xử lý những phần đã được xác định là hợp lệ.

## 18. Hiệu năng và giới hạn đệ quy

Visitor và Listener thường duyệt cây theo depth-first. Với cây thông thường, chi phí duyệt tỷ lệ với số node. Tuy nhiên, cần chú ý:

- Độ sâu cây rất lớn có thể làm tràn call stack khi dùng đệ quy.
- Listener lưu mọi context hoặc node trong map có thể tiêu tốn bộ nhớ.
- Visitor tạo nhiều object trung gian có thể tăng allocation.
- Một node có thể bị duyệt nhiều lần bởi nhiều Visitor khác nhau.
- Việc giữ parse tree sau khi tạo AST có thể làm tăng bộ nhớ nếu không còn cần thiết.

Nếu DSL cho phép biểu thức hoặc cấu trúc lồng rất sâu, hãy giới hạn độ sâu đầu vào hoặc dùng traversal iterative với stack tường minh.

Không nên tối ưu trước khi đo. Với cây vừa phải, code đệ quy rõ ràng thường dễ bảo trì hơn. Khi cần xử lý file lớn, hãy benchmark trên dữ liệu đại diện và đo cả thời gian lẫn bộ nhớ.

## 19. Kiểm thử Visitor và Listener

Kiểm thử cần xác nhận cả việc callback hoặc phương thức được gọi đúng lẫn kết quả ngữ nghĩa.

### 19.1 Kiểm thử Visitor

Với evaluator:

~~~java
@Test
void evaluatesNestedExpression() {
    Expression expression = new MultiplyExpression(
        new AddExpression(
            new NumberExpression(1),
            new NumberExpression(2)
        ),
        new NumberExpression(3)
    );

    int result = expression.accept(new EvaluationVisitor());

    assertEquals(9, result);
}
~~~

Nên bổ sung:

- Mỗi loại node có test tương ứng.
- Cây lồng nhiều tầng.
- Trường hợp biên và lỗi.
- Thứ tự đánh giá nếu có short-circuit.
- Node mới được xử lý hoặc bị từ chối rõ ràng.

### 19.2 Kiểm thử Listener

Có thể dùng một Listener ghi lại chuỗi sự kiện:

~~~java
final class EventLogListener extends MyDslBaseListener {
    private final List<String> events = new ArrayList<>();

    @Override
    public void enterBlock(MyDslParser.BlockContext ctx) {
        events.add("enter:block");
    }

    @Override
    public void exitBlock(MyDslParser.BlockContext ctx) {
        events.add("exit:block");
    }

    List<String> events() {
        return List.copyOf(events);
    }
}
~~~

Test có thể xác nhận thứ tự enter/exit với input lồng nhau. Với Listener xây AST, hãy so sánh AST hoặc kết quả đánh giá cuối cùng thay vì chỉ kiểm tra số callback.

### 19.3 Kiểm thử parse tree và AST

Nên có test cho:

- Input hợp lệ tạo cấu trúc mong đợi.
- Input lỗi không làm Listener hoặc Visitor crash ngoài dự kiến.
- Vị trí nguồn được giữ đúng.
- AST tạo từ Listener có cùng ý nghĩa với AST tham chiếu.
- Visitor xử lý đầy đủ các loại node.
- Thứ tự duyệt và thứ tự tổng hợp kết quả đúng.

Nếu grammar thay đổi, các test này giúp phát hiện Listener phụ thuộc vào tên rule hoặc cấu trúc context đã bị thay đổi.

## 20. Những sai lầm thường gặp

### Dùng Visitor nhưng quên duyệt node con

Một phương thức visit có thể chỉ xử lý node hiện tại và bỏ sót các node con, khiến một phần cây không được phân tích.

**Cách khắc phục:** quy định rõ phương thức nào tự duyệt con, phương thức nào dùng helper visitChildren; viết test cho cây lồng nhau.

### Dùng Listener để trả kết quả nhưng không quản lý trạng thái

Listener không có kiểu trả kết quả tự nhiên như Visitor. Nếu dùng biến dùng chung mà không phân biệt context, kết quả con có thể bị ghi đè hoặc gắn nhầm node cha.

**Cách khắc phục:** dùng stack, map theo context hoặc object kết quả có cấu trúc; xác định rõ thời điểm push, pop và tổng hợp.

### Giả định callback enter và exit tương đương

Enter xảy ra trước khi đi qua node con; exit xảy ra sau khi node con đã được duyệt. Đặt logic tổng hợp ở sai callback có thể khiến dữ liệu con chưa sẵn sàng.

**Cách khắc phục:** dùng enter cho thiết lập trạng thái, exit cho tổng hợp từ con khi phù hợp.

### Để Listener giữ state giữa nhiều lần parse

Dữ liệu cũ có thể làm sai kết quả lần sau.

**Cách khắc phục:** tạo instance mới cho mỗi lần walk hoặc reset state có kiểm soát.

### Gắn logic nghiệp vụ vào parse tree quá chặt

Đổi grammar có thể làm thay đổi context và callback, khiến logic nghiệp vụ phải sửa theo.

**Cách khắc phục:** cân nhắc chuyển parse tree thành AST hoặc mô hình miền ổn định trước khi thực hiện nhiều bước phân tích.

### Tạo quá nhiều Visitor nhỏ

Mỗi thao tác một lớp có thể hợp lý, nhưng chia quá nhỏ khiến truyền context và phối hợp phức tạp.

**Cách khắc phục:** nhóm theo trách nhiệm có ý nghĩa và dùng kết quả có cấu trúc.

### Coi Listener luôn chậm hơn Visitor

Hiệu năng phụ thuộc số node, số lần duyệt, object được tạo và cách quản lý trạng thái. Tên mẫu thiết kế không đủ để kết luận hiệu năng.

**Cách khắc phục:** đo bằng benchmark phù hợp trên workload thực tế.

## 21. Quy trình lựa chọn và triển khai

Khi xây dựng bước xử lý cây cú pháp cho DSL, có thể thực hiện:

1. **Xác định cấu trúc đầu vào:** parse tree do parser generator tạo hay AST tự xây.
2. **Xác định kết quả cần có:** giá trị, diagnostic, symbol table, AST mới, IR hay mã nguồn.
3. **Xác định quyền điều khiển:** cần short-circuit hoặc bỏ qua nhánh hay chỉ cần duyệt toàn bộ cây.
4. **Chọn mẫu:** Visitor cho thao tác chủ động và kết quả có kiểu; Listener cho callback theo sự kiện và walker điều khiển.
5. **Thiết kế trạng thái:** quyết định dữ liệu truyền qua tham số, return value, stack hay context.
6. **Tách trách nhiệm:** tránh trộn parse, validation, evaluation và code generation trong một lớp.
7. **Giữ source location:** bảo đảm diagnostic có thể trỏ về file DSL.
8. **Kiểm thử:** kiểm tra node đơn, cây lồng, lỗi, thứ tự duyệt và kết quả.
9. **Đo hiệu năng khi cần:** kiểm tra độ sâu và kích thước đầu vào đại diện.
10. **Tài liệu hóa:** mô tả ai sở hữu traversal và cách thêm node mới.

## 22. Ví dụ kiến trúc tổng hợp cho DSL

Một hệ thống DSL có thể tổ chức các thành phần:

~~~text
Source file
    |
    v
Lexer / Parser
    |
    v
Parse tree
    |
    +--> Error listener
    |
    v
AST builder listener
    |
    v
AST
    |
    +--> Name-resolution visitor
    |
    +--> Type-check visitor
    |
    +--> Evaluation visitor
    |
    +--> Pretty-print visitor
    |
    +--> Code-generation visitor
~~~

Mỗi bước có một trách nhiệm:

- Error listener thu thập lỗi từ lexer/parser.
- AST builder listener chuyển cấu trúc cú pháp sang mô hình gọn hơn.
- Name-resolution visitor giải quyết identifier và phạm vi.
- Type-check visitor xác định kiểu và tạo diagnostic.
- Evaluation visitor tính kết quả trong context.
- Pretty-print visitor tạo văn bản chuẩn hóa.
- Code-generation visitor chuyển AST hoặc IR sang target.

Đây là một cách tổ chức tham khảo. Một DSL nhỏ có thể bỏ bớt bước; một hệ thống lớn có thể thêm IR, optimizer hoặc nhiều backend. Không cần ép mọi dự án dùng đủ tất cả thành phần.

## 23. Câu hỏi tự kiểm tra

1. Phân biệt parse tree và AST.
2. Visitor tách thao tác khỏi cấu trúc node bằng cơ chế nào?
3. Vì sao generic Visitor hữu ích trong Java?
4. Phân biệt pre-order và post-order traversal.
5. Listener nhận callback enter và exit theo thứ tự nào?
6. Vì sao Listener thường dùng stack hoặc map để tổng hợp kết quả?
7. Nêu ưu điểm của Visitor khi cần short-circuit.
8. Khi nào Listener phù hợp để thu thập khai báo và quản lý scope?
9. Có thể kết hợp Listener và Visitor trong cùng pipeline DSL như thế nào?
10. Vì sao cần giữ source location trong AST hoặc parse context?
11. Cần kiểm thử những gì khi grammar thay đổi?
12. Làm thế nào để tránh lỗi state khi tái sử dụng Listener?

Khi lựa chọn Visitor hoặc Listener, hãy bắt đầu từ công việc cần thực hiện trên cây. Nếu cần kết quả có kiểu và quyền điều khiển traversal, Visitor thường thuận tiện. Nếu cần phản ứng theo sự kiện enter/exit trong một lượt duyệt do walker điều khiển, Listener thường tự nhiên hơn. Điều quan trọng là giữ rõ trách nhiệm, trạng thái và ngữ nghĩa của từng bước xử lý.

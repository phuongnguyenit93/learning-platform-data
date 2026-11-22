# Xây interpreter hoặc codegen

Một dự án thực hành DSL giúp người học đi qua toàn bộ vòng đời của một ngôn ngữ nhỏ: thiết kế cú pháp, phân tích source, xây mô hình trung gian, kiểm tra ngữ nghĩa và biến mô hình thành hành vi có thể quan sát. Hai hướng triển khai phổ biến là **interpreter** và **code generator (codegen)**.

Interpreter đọc mô hình DSL rồi trực tiếp đánh giá hoặc thực thi nó trong runtime do dự án kiểm soát. Code generator chuyển mô hình DSL thành một ngôn ngữ hoặc artifact khác, chẳng hạn Java source, SQL, JSON Schema, cấu hình hoặc workflow definition. Hai hướng có thể dùng chung lexer, parser, AST, type checker và semantic model; khác nhau chủ yếu ở phần backend.

Dự án này nên bắt đầu với một DSL có phạm vi nhỏ và mục tiêu rõ. Ví dụ, một ngôn ngữ biểu thức tính giá đơn hàng, một DSL mô tả rule phê duyệt hoặc một DSL khai báo entity và operation. Không cần xây một ngôn ngữ tổng quát ngay từ đầu. Điều quan trọng là có một vertical slice chạy được từ source text đến kết quả cuối, sau đó mở rộng theo từng tính năng.

## 1. Chọn bài toán và mục tiêu dự án

Trước khi viết parser, hãy xác định DSL dùng để mô tả điều gì và ai sẽ sử dụng nó.

Một số bài toán phù hợp:
- Expression DSL: tính toán biểu thức và biến.
- Rule DSL: điều kiện và hành động.
- Query DSL: lọc, sắp xếp và chiếu dữ liệu.
- Configuration DSL: khai báo cấu hình ứng dụng.
- Workflow DSL: mô tả các bước và điều kiện chuyển trạng thái.
- Schema DSL: khai báo entity, field và relationship.
- API DSL: khai báo endpoint, input và response.

Ví dụ chọn một Rule DSL nhỏ:

~~~text
rule "bulk-discount" {
    when order.quantity >= 10
    then order.discountRate = 0.10
}
~~~

Mục tiêu có thể là:
- Đọc source DSL từ file.
- Parse thành AST.
- Resolve tên field và type.
- Phát hiện lỗi trước khi chạy.
- Thực thi rule trên object Java.
- Hoặc sinh Java source tương đương và compile được.

Nên xác định deliverable ngay từ đầu:
- Một CLI có lệnh compile/run.
- Một thư viện Java có API rõ.
- Một tập fixture DSL.
- Diagnostics có source location.
- Test tự động.
- Một ví dụ tích hợp trong ứng dụng nhỏ.

## 2. Interpreter và code generator khác nhau thế nào?

| Tiêu chí | Interpreter | Code generator |
|---|---|---|
| Đầu ra | Giá trị hoặc hành vi runtime | Source code hoặc artifact |
| Thực thi | Trực tiếp trên AST/IR | Compiler/backend khác thực thi output |
| Thời gian xử lý | Có thể mỗi lần chạy | Thường generate trước rồi chạy |
| Debug | Có thể gắn trace vào AST node | Cần source map giữa DSL và generated code |
| Portability | Phụ thuộc interpreter runtime | Phụ thuộc target và runtime được sinh ra |
| Tối ưu | Runtime optimization hoặc compiled expression | Tối ưu code/artifact đầu ra |
| Use case | Rule evaluation, expression, workflow | Java, SQL, schema, config, client SDK |

Interpreter phù hợp khi:
- DSL cần thay đổi nhanh và thực thi linh hoạt.
- Muốn giữ runtime semantics trong một nơi.
- Không muốn sinh và compile source cho mỗi thay đổi.
- Cần trace theo từng expression hoặc rule.

Codegen phù hợp khi:
- Muốn tận dụng compiler hoặc runtime có sẵn.
- Cần artifact triển khai độc lập.
- Muốn sinh code type-safe.
- Cần tích hợp với build system hoặc toolchain hiện hữu.
- Muốn target nhiều ngôn ngữ hoặc nền tảng.

Có thể xây cả hai backend trên cùng frontend. Đây là cách tốt để kiểm tra xem semantic model có độc lập với cách thực thi hay không.

## 3. Kiến trúc tổng thể

Một pipeline cơ bản:

~~~mermaid
flowchart TD
    A[DSL source] --> B[Lexer]
    B --> C[Parser]
    C --> D[AST]
    D --> E[Name resolution]
    E --> F[Type checking]
    F --> G[Semantic model or IR]
    G --> H[Interpreter]
    G --> I[Code generator]
    H --> J[Runtime result]
    I --> K[Generated artifact]
    K --> L[Target compiler or runtime]
~~~

Trách nhiệm từng tầng:

- Lexer: chuyển ký tự thành token.
- Parser: kiểm tra grammar và tạo AST.
- AST: biểu diễn cấu trúc cú pháp.
- Name resolver: tìm symbol được tham chiếu.
- Type checker: kiểm tra kiểu và chuyển đổi.
- Semantic model/IR: biểu diễn ý nghĩa đã resolve.
- Interpreter: đánh giá IR.
- Codegen: sinh target artifact.
- Target runtime/compiler: thực thi artifact được sinh.

Không nên đặt toàn bộ logic vào parser hoặc generator. Tách tầng giúp test từng contract và hỗ trợ nhiều backend.

## 4. Giới hạn ngôn ngữ phiên bản đầu

Một phiên bản đầu nên có ít construct nhưng hoàn chỉnh.

Ví dụ Expression DSL:
- Literal: số, chuỗi, boolean.
- Variable reference.
- Arithmetic: cộng, trừ, nhân, chia.
- Comparison: bằng, khác, lớn hơn, nhỏ hơn.
- Logical: and, or, not.
- Parentheses.
- Variable declaration.
- If expression hoặc rule condition.

Ví dụ:

~~~text
let subtotal = quantity * unitPrice
let eligible = quantity >= 10 and customer.isMember
if eligible {
    subtotal * 0.90
} else {
    subtotal
}
~~~

Nên hoãn:
- User-defined function.
- Generic type.
- Macro.
- Dynamic reflection.
- Arbitrary plugin execution.
- Concurrency.
- Complex module system.

Khi core semantics ổn định, có thể thêm tính năng theo nhu cầu thật.

## 5. Định nghĩa grammar

Grammar là hợp đồng cú pháp. Một grammar nhỏ có thể viết bằng EBNF:

~~~text
program       = { statement } ;
statement     = variableDecl | ruleDecl | expressionStmt ;
variableDecl  = "let" identifier "=" expression ;
ruleDecl      = "rule" stringLiteral "{" "when" expression
                "then" statement "}" ;
expressionStmt = expression ;

expression    = logicalOr ;
logicalOr     = logicalAnd { "or" logicalAnd } ;
logicalAnd    = equality { "and" equality } ;
equality      = comparison { ("==" | "!=") comparison } ;
comparison    = term { (">" | ">=" | "<" | "<=") term } ;
term          = factor { ("+" | "-") factor } ;
factor        = unary { ("*" | "/") unary } ;
unary         = ("!" | "-") unary | primary ;
primary       = number | string | boolean | identifier
              | "(" expression ")" ;
~~~

Grammar thể hiện precedence: nhân/chia có precedence cao hơn cộng/trừ; comparison cao hơn logical and/or.

Cần định nghĩa thêm:
- Comment syntax.
- String escape.
- Decimal literal.
- Identifier character set.
- Whitespace.
- End-of-file behavior.
- Error recovery.
- Reserved keywords.

Không nên chỉ dựa vào ví dụ source để suy ra grammar. Một grammar tường minh giúp parser, formatter, editor và tài liệu đồng nhất.

## 6. Thiết kế token và lexer

Lexer đọc source và tạo token stream. Token nên giữ kind, lexeme hoặc literal value và source span.

Ví dụ token:

~~~java
enum TokenKind {
    IDENTIFIER,
    NUMBER,
    STRING,
    LET,
    RULE,
    WHEN,
    THEN,
    TRUE,
    FALSE,
    PLUS,
    MINUS,
    STAR,
    SLASH,
    EQUAL_EQUAL,
    BANG_EQUAL,
    LEFT_PAREN,
    RIGHT_PAREN,
    LEFT_BRACE,
    RIGHT_BRACE,
    EOF
}

record SourceSpan(
    String sourceName,
    int startOffset,
    int endOffset,
    int line,
    int column
) {}

record Token(
    TokenKind kind,
    String lexeme,
    Object literal,
    SourceSpan span
) {}
~~~

Lexer cần xử lý:
- Whitespace.
- Newline và line/column.
- Identifier và keyword.
- Integer/decimal literal.
- String escape.
- Operator dài hơn một ký tự.
- Comment.
- Invalid character.
- Unterminated string.

Ví dụ, khi gặp dấu =, lexer cần xem ký tự tiếp theo để phân biệt assignment với equality. Token giữ source span giúp diagnostics chỉ đúng vị trí.

## 7. Parser và AST

Parser nhận token stream và tạo Abstract Syntax Tree (AST). AST giữ cấu trúc có ý nghĩa, không nhất thiết giữ mọi dấu câu hoặc whitespace.

Một AST expression có thể dùng sealed interface:

~~~java
sealed interface Expr
    permits NumberLiteral, BooleanLiteral,
            VariableRef, BinaryExpr, UnaryExpr {}

record NumberLiteral(
    BigDecimal value,
    SourceSpan span
) implements Expr {}

record BooleanLiteral(
    boolean value,
    SourceSpan span
) implements Expr {}

record VariableRef(
    String name,
    SourceSpan span
) implements Expr {}

record BinaryExpr(
    Expr left,
    TokenKind operator,
    Expr right,
    SourceSpan span
) implements Expr {}

record UnaryExpr(
    TokenKind operator,
    Expr operand,
    SourceSpan span
) implements Expr {}
~~~

AST nên giữ source span ở node quan trọng để type error và runtime trace có thể trỏ về source.

Parser có thể dùng recursive descent cho grammar nhỏ. Với biểu thức, precedence climbing hoặc Pratt parser giúp xử lý operator precedence gọn hơn.

## 8. Recursive descent parser

Mỗi grammar production thường tương ứng một method parser.

~~~java
Expr expression() {
    return logicalOr();
}

Expr logicalOr() {
    Expr expr = logicalAnd();

    while (match(TokenKind.OR)) {
        Token operator = previous();
        Expr right = logicalAnd();
        expr = new BinaryExpr(
            expr,
            operator.kind(),
            right,
            span(expr, right)
        );
    }

    return expr;
}
~~~

Parser cần:
- Kiểm tra token mong đợi.
- Báo lỗi có source location.
- Phục hồi để tiếp tục parse phần sau khi có thể.
- Không tạo AST node giả không hợp lệ mà semantic phase không hiểu.
- Giới hạn nesting depth nếu input không tin cậy.

Error recovery giúp editor hiển thị nhiều diagnostics cùng lúc. Với compiler batch, có thể dừng sớm hơn nếu lỗi làm mất cấu trúc.

## 9. Name resolution và symbol table

Sau parsing, identifier cần được resolve vào symbol cụ thể. Một symbol có thể là variable, field, function, type hoặc rule.

Ví dụ:

~~~text
let taxRate = 0.08
let total = subtotal * (1 + taxRate)
~~~

Resolver cần tìm taxRate trong scope hiện tại. Nếu không tồn tại, tạo diagnostic UNRESOLVED_NAME.

Một symbol table khái niệm:

~~~java
record Symbol(
    int id,
    String name,
    SymbolKind kind,
    Type type,
    SourceSpan declaration
) {}

final class Scope {
    private final Scope parent;
    private final Map<String, Symbol> symbols =
        new HashMap<>();

    Optional<Symbol> resolve(String name) {
        Symbol local = symbols.get(name);
        if (local != null) {
            return Optional.of(local);
        }
        return parent == null
            ? Optional.empty()
            : parent.resolve(name);
    }
}
~~~

Cần xác định:
- Scope lồng nhau.
- Shadowing.
- Declaration order.
- Import/module resolution.
- Duplicate declaration.
- Built-in symbols.
- Qualified name.

Không nên để interpreter hoặc codegen tự tìm tên bằng string. Hãy resolve trước và gắn stable symbol ID vào semantic model.

## 10. Type system và semantic validation

Type checker xác định kiểu của expression và kiểm tra operation hợp lệ.

Một type system nhỏ có thể gồm:
- Integer.
- Decimal.
- Boolean.
- String.
- Null/Optional.
- Domain types như Money hoặc CustomerId.

Ví dụ:
- Number + Number hợp lệ.
- String + String chỉ hợp lệ nếu DSL định nghĩa concatenation.
- Boolean and Boolean hợp lệ.
- Date * Integer không hợp lệ nếu không có semantics.
- Condition của if phải là Boolean.

Một interface type checker có thể:

~~~java
Type check(
    Expr expression,
    TypeEnvironment environment
);
~~~

Type checker nên trả diagnostics thay vì chỉ ném exception cho lỗi người dùng. Cần định nghĩa implicit conversion, numeric promotion, nullability và error propagation.

## 11. Canonical IR

AST phản ánh cấu trúc cú pháp. Intermediate Representation (IR) phản ánh ý nghĩa đã resolve và thuận tiện cho backend.

Ví dụ source:

~~~text
subtotal * (1 + taxRate)
~~~

IR có thể lưu:
- Symbol ID của subtotal.
- Decimal type.
- Add node với constant 1.
- Symbol ID của taxRate.
- Multiply node.
- Source mapping.

Một IR node:

~~~java
record IrBinary(
    IrExpression left,
    IrOperator operator,
    IrExpression right,
    Type resultType,
    SourceSpan source
) implements IrExpression {}
~~~

IR nên:
- Không còn identifier chưa resolve.
- Có type rõ.
- Biểu diễn conversion tường minh.
- Giữ source mapping.
- Có version nếu được serialize.
- Không phụ thuộc riêng interpreter hoặc target backend.

Nếu cả interpreter và codegen dùng cùng IR, hai backend có thể được kiểm thử trên cùng semantic input.

## 12. Hướng A: xây interpreter

Interpreter đánh giá AST hoặc IR trực tiếp.

Một interpreter đơn giản có thể dùng visitor:

~~~java
interface IrVisitor<R> {
    R visitNumber(IrNumber expression);
    R visitBoolean(IrBoolean expression);
    R visitVariable(IrVariable expression);
    R visitBinary(IrBinary expression);
    R visitUnary(IrUnary expression);
}
~~~

Evaluator giữ Environment chứa variable values:

~~~java
final class Environment {
    private final Environment parent;
    private final Map<Integer, Object> values =
        new HashMap<>();

    Object get(int symbolId) {
        if (values.containsKey(symbolId)) {
            return values.get(symbolId);
        }
        if (parent != null) {
            return parent.get(symbolId);
        }
        throw new IllegalStateException(
            "Missing runtime binding: " + symbolId
        );
    }
}
~~~

Evaluator có thể xử lý binary operation:

~~~java
Object evaluateBinary(
        IrBinary expression,
        Environment environment) {

    Object left = evaluate(expression.left(), environment);

    if (expression.operator() == IrOperator.AND
            && Boolean.FALSE.equals(left)) {
        return false;
    }

    if (expression.operator() == IrOperator.OR
            && Boolean.TRUE.equals(left)) {
        return true;
    }

    Object right = evaluate(expression.right(), environment);

    return switch (expression.operator()) {
        case ADD -> add(left, right);
        case SUBTRACT -> subtract(left, right);
        case MULTIPLY -> multiply(left, right);
        case DIVIDE -> divide(left, right);
        case EQUAL -> Objects.equals(left, right);
        case AND -> (Boolean) left && (Boolean) right;
        case OR -> (Boolean) left || (Boolean) right;
    };
}
~~~

Đây là ví dụ khái niệm; implementation cần kiểm tra runtime type và xử lý lỗi có source location thay vì cast mù.

## 13. Environment và scope trong interpreter

Interpreter cần quản lý variable binding và lifetime.

Các trường hợp:
- Global variable.
- Local variable.
- Function parameter.
- Nested block.
- Shadowing.
- Mutable/immutable binding.
- Closure nếu DSL hỗ trợ function.

Mỗi scope có thể tham chiếu parent scope. Khi thoát block, local binding không còn nhìn thấy.

Nếu DSL có function, cần định nghĩa call frame:
- Argument evaluation.
- Parameter binding.
- Return value.
- Recursion.
- Maximum call depth.
- Exception propagation.

Không nên để Environment là một global mutable map nếu có nhiều request hoặc evaluation song song. Mỗi evaluation cần context riêng hoặc immutable shared environment.

## 14. Runtime value model

Không nên dùng Object tùy ý mà không có quy tắc. Một value model có thể gồm:
- NumberValue.
- BooleanValue.
- StringValue.
- NullValue.
- ListValue.
- RecordValue.
- DomainValue.

Value model cần quy định:
- Equality.
- Hashing.
- Serialization.
- Numeric precision.
- Null behavior.
- Mutability.
- Display/formatting.
- Type identity.

Ví dụ, Decimal nên dùng BigDecimal nếu yêu cầu tính chính xác. Division by zero cần tạo runtime diagnostic có code và source span. Không nên để exception Java thô lộ ra user.

## 15. Rule execution và side effects

Nếu DSL có rule hoặc command, cần phân biệt expression thuần với hành động có side effect.

Một rule engine có thể:
1. Resolve input.
2. Evaluate condition.
3. Nếu condition true, tạo action plan.
4. Kiểm tra capability.
5. Thực thi action.
6. Ghi trace/audit.

Không nên để một expression thuần tự gửi email hoặc ghi database. Tách evaluation khỏi effect giúp:
- Test deterministic.
- Replay decision.
- Shadow evaluation.
- Kiểm soát permission.
- Retry có idempotency.
- Audit rõ.

Nếu action thất bại, cần xác định có rollback, compensation hoặc partial state.

## 16. Hướng B: xây code generator

Codegen chuyển IR thành target artifact. Có thể target:
- Java source.
- Kotlin source.
- SQL.
- JSON Schema.
- OpenAPI.
- Configuration file.
- Bytecode hoặc custom VM instruction.
- Workflow definition.

Một backend cần:
- Target selection.
- Type mapping.
- Name mangling.
- Literal formatting.
- Import/dependency management.
- Source map.
- Diagnostics.
- Output manifest.
- Deterministic ordering.

Ví dụ Java backend sinh expression:

~~~java
String emit(IrExpression expression) {
    return switch (expression) {
        case IrNumber number ->
            number.value().toPlainString();

        case IrBoolean bool ->
            Boolean.toString(bool.value());

        case IrVariable variable ->
            names.javaName(variable.symbolId());

        case IrBinary binary ->
            "(" + emit(binary.left())
                + operator(binary.operator())
                + emit(binary.right()) + ")";
    };
}
~~~

Generator nên sinh code từ IR đã type-check. Không nên vừa parse source vừa nối chuỗi Java trong một bước.

## 17. Type mapping sang target language

Type mapping chuyển DSL type sang type của target.

Ví dụ:

| DSL type | Java target |
|---|---|
| Integer | long hoặc BigInteger |
| Decimal | BigDecimal |
| Boolean | boolean/Boolean |
| String | String |
| UUID | UUID |
| LocalDate | LocalDate |
| Instant | Instant |
| List<T> | List<TargetType> |
| Optional<T> | Optional<TargetType> hoặc nullable contract |

Mapping cần xét:
- Nullability.
- Precision.
- Overflow.
- Equality semantics.
- Collection mutability.
- Date/time timezone.
- Domain type wrapper.
- Serialization.

Không nên chỉ map theo tên type. Ví dụ DSL Integer có thể có arbitrary precision; map sang int sẽ làm mất giá trị lớn.

## 18. Name mangling và identifier safety

Tên trong DSL có thể không phải identifier hợp lệ trong target language hoặc có thể trùng keyword.

Ví dụ:
- DSL field tên class.
- Hai field khác nhau chỉ khác ký tự không hỗ trợ.
- Tên Unicode.
- Tên bắt đầu bằng số.
- Hai symbol cùng tên ngắn ở namespace khác nhau.

Generator cần một NameAllocator:
- Tạo tên hợp lệ.
- Tránh keyword.
- Tránh collision.
- Giữ mapping ổn định.
- Có thể dùng symbol ID thay vì name string.
- Tạo source map từ tên target về DSL source.

Không nên đơn giản lowercase mọi tên vì có thể tạo collision và đổi semantics.

## 19. Expression precedence trong codegen

Generator phải giữ đúng grouping và precedence. Ví dụ:

~~~text
a + b * c
~~~

Có thể sinh trực tiếp vì multiplication có precedence cao hơn addition. Nhưng:

~~~text
(a + b) * c
~~~

cần giữ parentheses.

Một cách an toàn là mỗi IR expression cung cấp precedence level. Parent emitter so sánh precedence của child với operator cha để quyết định có cần parentheses.

Không nên sinh code bằng cách nối string thiếu kiểm soát. Sai một cặp ngoặc có thể đổi kết quả dù generated source compile thành công.

## 20. Runtime support library cho codegen

Generated code thường cần helper runtime:
- Decimal operations.
- Null-safe comparison.
- Collection utilities.
- Rule context.
- Error/diagnostic mapping.
- Domain conversion.
- Date/time helper.
- Runtime function registry.

Codegen cần khai báo runtime dependency và version constraint. Nếu generated code gọi helper API không tồn tại trong runtime được cài, integration sẽ fail.

Có thể sinh manifest:

~~~yaml
generator:
  id: java
  version: 2.3.0
dsl:
  languageVersion: "1"
runtime:
  required: ">=4.1 <5"
artifacts:
  - path: src/generated/java/OrderRules.java
    kind: java-source
~~~

Manifest giúp build system biết artifact nào được tạo và runtime nào cần có.

## 21. Source mapping và diagnostics

Khi interpreter hoặc generated code phát sinh lỗi, người dùng cần thấy vị trí DSL gốc.

Source map có thể ánh xạ:
- IR node → DSL source span.
- Generated file/line → DSL source span.
- Runtime instruction → DSL expression.
- Generated symbol → DSL symbol ID.

Nếu generated Java ném exception, runtime adapter có thể dùng source map để báo:
- File DSL.
- Line/column.
- Rule hoặc expression.
- Error code.
- Safe message.

Không nên chỉ báo stack trace của generated Java. Nó hữu ích cho developer backend nhưng không đủ cho người viết DSL.

## 22. Deterministic generation

Cùng semantic model và cùng toolchain nên tạo output ổn định.

Cần kiểm soát:
- Thứ tự symbol.
- Import ordering.
- Whitespace/formatter.
- Encoding và newline.
- Timestamp.
- Absolute path.
- Random identifiers.
- Hash seed.
- Locale.
- Target platform.

Deterministic output giúp:
- Golden tests ổn định.
- Build cache hiệu quả.
- Review diff dễ.
- Reproducible build.
- Artifact provenance đáng tin cậy.

Nếu timestamp cần thiết, truyền build time tường minh hoặc tách nó khỏi generated source để không invalidates mọi output.

## 23. CLI và project layout

Một project Java nhỏ có thể có cấu trúc:

~~~text
mini-dsl/
  language/
    Token.java
    Lexer.java
    Parser.java
    Ast.java
    TypeChecker.java
    Ir.java
  interpreter/
    Evaluator.java
    Environment.java
    RuntimeValue.java
  codegen/
    JavaGenerator.java
    NameAllocator.java
    SourceMap.java
  cli/
    Main.java
  runtime/
    DslRuntime.java
  src/
    main/
    test/
    test-resources/
  examples/
    discount.dsl
    order.dsl
~~~

CLI có thể cung cấp:
- dsl parse file.dsl
- dsl check file.dsl
- dsl run file.dsl
- dsl generate java file.dsl
- dsl explain file.dsl
- dsl version

Mỗi command cần exit code rõ. Parse/type error nên trả non-zero và diagnostics; help/version không cần load runtime hoặc plugin nặng.

## 24. Error model và diagnostics

Compiler/interpreter nên dùng structured diagnostics thay vì chỉ exception message.

Một diagnostic có thể chứa:
- Code.
- Severity.
- Message.
- Source span.
- Related location.
- Suggested fix.
- Phase.
- Cause nếu là internal error.

Ví dụ:

~~~text
E-TYPE-004: Cannot multiply Money by String
  at order.dsl:12:18
  expression: quantity * unitPrice
  expected: Numeric × Numeric
  actual: Integer × String
~~~

Phân biệt:
- User error: syntax/type/validation.
- Runtime domain error: division by zero, missing binding.
- Infrastructure error: file I/O, dependency unavailable.
- Internal compiler error: invariant của implementation bị vi phạm.

Không nên biến mọi exception thành “Invalid DSL”. Internal error cần correlation ID và log kỹ thuật; user error cần hướng dẫn sửa source.

## 25. Kiểm thử lexer và parser

Lexer tests:
- Mỗi token kind.
- Operator dài/ngắn.
- String escape.
- Unicode identifier.
- Comment.
- Decimal literal.
- Invalid character.
- Unterminated string.
- Line/column.

Parser tests:
- AST shape.
- Operator precedence.
- Parentheses.
- Nested block.
- Missing token.
- Unexpected token.
- Error recovery.
- Deep nesting.

Có thể dùng parser snapshot hoặc structural assertion. Không nên chỉ assert parser không ném exception; cần xác minh AST đúng cấu trúc.

## 26. Kiểm thử semantic model

Type checker/resolver tests:
- Name resolution.
- Scope và shadowing.
- Duplicate symbol.
- Unknown symbol.
- Type mismatch.
- Implicit conversion.
- Nullability.
- Function signature.
- Cross-module import.
- Dependency cycle.

IR tests:
- Mọi reference đã resolve.
- Type annotation đầy đủ.
- Conversion được biểu diễn tường minh.
- Source span được giữ.
- IR serialization/versioning nếu có.

Một compiler pipeline cần có test đảm bảo lỗi semantic ngăn backend chạy trên model không hợp lệ.

## 27. Kiểm thử interpreter

Interpreter tests nên kiểm tra:
- Arithmetic và comparison.
- Boolean short-circuit.
- Scope.
- Variable binding.
- Null behavior.
- Decimal precision.
- Runtime error.
- Rule match/no-match.
- Action authorization.
- Timeout/step limit.
- Cancellation.
- Determinism.

Ví dụ property:
- Evaluate cùng IR và environment không đổi cho cùng kết quả nếu expression pure.
- Thêm comment không đổi result.
- Short-circuit không evaluate nhánh không cần thiết.
- Runtime error có source span đúng.

Với side effect, dùng test double cho effect boundary và xác minh action chỉ chạy khi condition đúng và permission hợp lệ.

## 28. Kiểm thử code generator

Generator tests gồm:
- Snapshot/golden output.
- Target syntax validation.
- Compile generated source.
- Run generated artifact.
- Compare result với interpreter.
- Name collision.
- Type mapping.
- Source map.
- Deterministic output.
- Dependency manifest.

Một chiến lược mạnh là differential test:
1. Chạy DSL bằng interpreter.
2. Generate code từ cùng IR.
3. Compile và chạy generated code.
4. So sánh output, error và side effect theo contract.

Nếu hai backend khác kết quả, có thể có bug trong interpreter, IR semantics hoặc generator.

## 29. End-to-end test

Một end-to-end test có thể:
1. Đọc fixture DSL.
2. Chạy CLI compile.
3. Kiểm tra diagnostics.
4. Sinh artifact.
5. Compile artifact.
6. Nạp vào runtime.
7. Chạy input fixture.
8. Assert output.
9. Kiểm tra log và source map.

Nên có success path và failure path. Ví dụ một file DSL hợp lệ tạo artifact chạy được; một file tham chiếu symbol không tồn tại phải dừng trước code generation và trả diagnostic đúng.

## 30. Ví dụ: mini expression interpreter

Một chương trình nhỏ có thể hỗ trợ:

~~~text
let quantity = 3
let unitPrice = 12.50
quantity * unitPrice
~~~

Flow:
1. Lexer tạo token.
2. Parser tạo declaration và binary expression.
3. Resolver gắn symbol ID cho quantity và unitPrice.
4. Type checker xác định Decimal result.
5. Interpreter đánh giá trong environment.
6. CLI in kết quả 37.50.

Khi mở rộng, có thể thêm:
- Function call.
- If expression.
- List.
- Record.
- Rule.
- Import.
- User-defined function.

Mỗi feature nên có grammar, AST, semantics, interpreter/codegen support và test trước khi được xem là hoàn chỉnh.

## 31. Ví dụ: mini code generator cho Java

Với cùng expression, generator có thể sinh:

~~~java
import java.math.BigDecimal;

public final class GeneratedCalculation {
    public static BigDecimal evaluate() {
        BigDecimal quantity =
            new BigDecimal("3");

        BigDecimal unitPrice =
            new BigDecimal("12.50");

        return quantity.multiply(unitPrice);
    }
}
~~~

Generated code cần:
- Type mapping đúng.
- Literal chính xác.
- Parentheses/precedence đúng.
- Import không trùng.
- Name không collision.
- Source map.
- Runtime dependency nếu dùng helper.

Sau khi generate, compile bằng JavaCompiler hoặc build task và chạy method evaluate để xác nhận kết quả.

## 32. Chọn interpreter hay codegen cho dự án

Chọn interpreter khi:
- DSL có logic động và cần evaluate nhiều lần.
- Muốn trace từng node.
- Muốn giới hạn function/capability ở runtime.
- Không muốn phụ thuộc target compiler.

Chọn codegen khi:
- Target runtime đã trưởng thành.
- Cần artifact triển khai.
- Muốn tận dụng tối ưu compiler target.
- Cần tạo source/schema/config cho hệ thống khác.

Chọn cả hai khi:
- Muốn dùng interpreter làm reference implementation.
- Muốn codegen cho production.
- Cần differential test.
- Muốn hỗ trợ nhiều target backend.

Nếu làm cả hai, nên xây shared IR và semantic test suite trước. Nếu không, hai backend có thể tự phát triển semantics khác nhau.

## 33. Lộ trình thực hiện theo milestone

Một lộ trình thực tế:

**Milestone 1 — Language slice**
- Chọn domain nhỏ.
- Viết grammar.
- Lexer và parser.
- AST và syntax diagnostics.

**Milestone 2 — Semantic frontend**
- Symbol table.
- Name resolution.
- Type checking.
- Canonical IR.

**Milestone 3 — First backend**
- Interpreter hoặc codegen.
- Runtime values hoặc target type mapping.
- Error/source mapping.
- CLI command.

**Milestone 4 — End-to-end**
- Fixture DSL.
- Runtime/target compile.
- Functional tests.
- Error tests.

**Milestone 5 — Hardening**
- Resource limits.
- Deterministic behavior.
- Cancellation.
- Security/capability nếu DSL có side effect.
- Build/package integration.

**Milestone 6 — Extension**
- Functions hoặc rules.
- Module/import.
- Plugin/backend thứ hai.
- Documentation và sample project.

Không nên bắt đầu với plugin system, optimizer hoặc distributed execution trước khi vertical slice cơ bản hoạt động.

## 34. Tiêu chí hoàn thành dự án

Một dự án thực hành có thể xem là đạt mục tiêu khi:
- Có grammar và language reference ngắn.
- Lexer/parser tạo AST ổn định.
- Diagnostics chỉ đúng source location.
- Name resolution và type checking có test.
- Có semantic IR.
- Interpreter hoặc codegen hoạt động trên fixture.
- Generated code compile được nếu chọn codegen.
- Kết quả có test end-to-end.
- Lỗi được biểu diễn bằng structured diagnostic.
- CLI có help, version và exit code.
- Project có README và example.
- Có giới hạn resource nếu source không tin cậy.
- Có build command tái lập.

Nếu chọn cả hai backend, cần thêm test chứng minh interpreter và generated artifact cho kết quả tương đương trên cùng tập input.

## 35. Nguyên tắc thiết kế

- **Chọn domain nhỏ:** một vertical slice hoàn chỉnh có giá trị hơn grammar rộng nhưng không chạy được.
- **Viết semantics trước backend:** xác định type, null, conversion và evaluation order.
- **Tách frontend khỏi backend:** lexer/parser/analyzer không phụ thuộc interpreter hoặc target language.
- **Giữ source span:** mọi diagnostic và runtime trace cần truy về DSL source.
- **Resolve symbol trước execution:** không tìm tên bằng string ở mọi lần evaluate.
- **Dùng canonical IR:** tạo contract chung cho interpreter và codegen.
- **Phân biệt pure expression và side effect:** dễ test và kiểm soát quyền.
- **Sinh code từ IR đã kiểm tra:** tránh nối chuỗi source trực tiếp từ input.
- **Giữ output deterministic:** giúp review, cache và reproduce.
- **Kiểm thử nhiều tầng:** lexer, parser, semantic, backend, compile và runtime.
- **So sánh hai backend nếu có:** interpreter có thể làm reference cho codegen.
- **Đặt resource limits:** recursion, evaluation steps, memory và output size cần giới hạn.
- **Thiết kế diagnostics cho người dùng:** code, source span và hướng khắc phục rõ.
- **Tích hợp build sớm:** generated artifact cần được compile và đóng gói trong pipeline thật.
- **Mở rộng theo milestone:** chỉ thêm module, function, plugin hoặc optimization khi core ổn định.

Xây interpreter hoặc code generator là dự án thực hành giúp kết nối các kiến thức về grammar, parser, AST, type system, IR, runtime và compiler backend. Khi bắt đầu bằng một ngôn ngữ nhỏ, giữ frontend độc lập, định nghĩa semantics rõ và kiểm tra output qua một luồng end-to-end, người học có thể xây một DSL chạy được, giải thích được và có nền tảng để mở rộng thành công cụ thực tế.

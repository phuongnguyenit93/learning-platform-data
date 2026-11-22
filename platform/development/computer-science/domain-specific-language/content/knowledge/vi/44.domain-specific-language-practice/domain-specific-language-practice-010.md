# Viết bộ kiểm thử

## Mục tiêu của dự án

Một DSL (domain-specific language) chỉ đáng tin cậy khi người dùng có thể viết source, nhận diagnostics, thực thi và tích hợp nó vào ứng dụng mà không tạo ra hành vi bất ngờ. Parser chạy được với vài ví dụ chưa đủ để chứng minh ngôn ngữ đúng. Cần một bộ kiểm thử bao phủ grammar, semantics, runtime, host integration, compatibility và các điều kiện vận hành.

Trong dự án thực hành này, chúng ta xây dựng **bộ kiểm thử cho một DSL rule nhỏ** dùng để tính mức giảm giá đơn hàng. Cách tổ chức có thể áp dụng cho query DSL, workflow DSL, configuration DSL hoặc policy DSL.

DSL mẫu:

~~~text
RULE vipDiscount {
  WHEN customer.level == "GOLD"
   AND order.total >= 1000000
  THEN order.total * 0.10
}

RULE standardDiscount {
  WHEN customer.level == "SILVER"
  THEN order.total * 0.05
}
~~~

Ứng dụng host cung cấp context gồm customer và order. Runtime parse rule, đánh giá điều kiện và trả về giá trị giảm giá. Bộ test cần xác nhận:

- Tokenizer nhận diện đúng keyword, identifier, literal và operator.
- Parser tạo AST đúng cấu trúc.
- Semantic analyzer phát hiện tên và kiểu không hợp lệ.
- Evaluator tính đúng biểu thức.
- Diagnostics có code và source location ổn định.
- Host truyền context và type mapping đúng.
- Runtime không làm rò rỉ state giữa các lần chạy.
- Input không hợp lệ hoặc không tin cậy không gây crash hay vượt resource limit.
- Thay đổi grammar hoặc runtime không làm hỏng source đã được hỗ trợ.

Dự án sẽ đi từ test đơn vị đến test tích hợp, sau đó thêm property-based testing, golden tests, security tests và CI. Các ví dụ Java dùng phong cách JUnit 5 để minh họa; có thể điều chỉnh cho test framework của project.

## Kiến trúc tối thiểu cần kiểm thử

Một DSL rule engine có thể có pipeline:

~~~text
Source text
    |
    v
Lexer
    |
    v
Parser
    |
    v
AST
    |
    v
Semantic analyzer
    |
    v
Typed / resolved model
    |
    v
Evaluator
    |
    v
Host context and functions
    |
    v
Rule result
~~~

Mỗi tầng có contract riêng. Nếu chỉ viết end-to-end test, khi test fail sẽ khó xác định lỗi nằm ở lexer, parser, type checker hay evaluator. Nếu chỉ viết unit test, các thành phần có thể hoạt động riêng lẻ nhưng tích hợp sai.

### Lexer

Chuyển source thành token. Ví dụ token stream:

~~~text
RULE vipDiscount {
  WHEN customer.level == "GOLD"
  THEN order.total * 0.10
}
~~~

~~~text
RULE
IDENTIFIER(vipDiscount)
LEFT_BRACE
WHEN
IDENTIFIER(customer)
DOT
IDENTIFIER(level)
EQUAL_EQUAL
STRING("GOLD")
THEN
IDENTIFIER(order)
DOT
IDENTIFIER(total)
STAR
NUMBER(0.10)
RIGHT_BRACE
EOF
~~~

### Parser

Chuyển token thành AST. Parser cần xác định precedence, associativity, block structure và source span.

### Semantic analyzer

Resolve identifier, function, type, nullability và các ràng buộc theo schema. Parser có thể chấp nhận cú pháp nhưng semantic analyzer vẫn có thể từ chối source.

### Evaluator

Đánh giá AST hoặc resolved expression với context cụ thể. Cần giữ đúng semantics của Boolean, Decimal, null và error.

### Host integration

Host tạo context, cung cấp domain object, function, permission và mapping result. Đây là boundary cần integration test riêng.

### Diagnostics

Mọi tầng có thể tạo diagnostic. Một diagnostic nên có code, severity, message, source span và related information nếu cần.

## Cấu trúc project kiểm thử

Có thể tổ chức test theo component và mục đích:

~~~text
dsl-project/
  src/
    main/
      java/
        lexer/
        parser/
        ast/
        semantic/
        runtime/
        host/
        diagnostics/
  src/
    test/
      java/
        lexer/
        parser/
        semantic/
        runtime/
        host/
        integration/
        compatibility/
        security/
      resources/
        fixtures/
          valid/
          invalid/
          semantic/
          compatibility/
        golden/
          ast/
          diagnostics/
          evaluation/
        schemas/
          customer.json
          order.json
~~~

Nếu build system dùng convention khác, có thể đặt các folder tương ứng. Điều quan trọng là test fixture được quản lý cùng source và có thể chạy tự động.

### Unit tests

Kiểm tra một component với input nhỏ, độc lập và deterministic.

### Component tests

Kiểm tra nhiều lớp nội bộ phối hợp, ví dụ lexer + parser hoặc parser + semantic analyzer.

### Host integration tests

Khởi tạo integration layer thật, truyền context và gọi host binding. Dependency ngoài có thể được thay bằng test server có contract rõ.

### Compatibility tests

Dùng corpus source từ các language version được hỗ trợ.

### Security tests

Kiểm tra unauthorized call, resource limit, input quá lớn và sandbox boundary.

### Performance tests

Đo parse/evaluation với workload đại diện. Không nên trộn benchmark dài vào test suite nhanh nếu làm CI chậm và thiếu ổn định.

## Xây dựng test harness

Test harness tạo các thành phần cần thiết để test không phải lặp lại setup.

Ví dụ API minh họa:

~~~java
final class DslTestHarness {
    private final Lexer lexer = new Lexer();
    private final Parser parser = new Parser();
    private final SemanticAnalyzer analyzer = new SemanticAnalyzer();
    private final Evaluator evaluator = new Evaluator();

    ParseResult parse(String source) {
        var tokens = lexer.scan(source);
        return parser.parse(tokens);
    }

    CompileResult compile(String source, DslSchema schema) {
        var parseResult = parse(source);
        if (!parseResult.diagnostics().isEmpty()) {
            return CompileResult.failure(parseResult.diagnostics());
        }
        return analyzer.analyze(parseResult.ast(), schema);
    }

    EvaluationResult evaluate(
            String source,
            DslSchema schema,
            EvaluationContext context) {
        var compiled = compile(source, schema);
        if (!compiled.success()) {
            return EvaluationResult.failure(compiled.diagnostics());
        }
        return evaluator.evaluate(compiled.program(), context);
    }
}
~~~

Đây là skeleton để minh họa boundary. Implementation thực tế có thể dùng dependency injection hoặc compiler service.

### Harness cần deterministic

Harness nên inject:
- Clock.
- Random source.
- Host function registry.
- Schema.
- Locale và timezone.
- Execution limits.
- Cancellation token.
- Diagnostic collector.

Không dùng system clock hoặc random global trong test nếu kết quả phụ thuộc chúng.

### Test fixture builder

Tạo helper cho domain data:

~~~java
Customer customer(String level) {
    return new Customer("customer-1", level, true);
}

Order order(BigDecimal total) {
    return new Order("order-1", total, "VND");
}
~~~

Fixture nên tạo dữ liệu hợp lệ theo domain invariant. Test có thể tạo fixture invalid riêng khi mục tiêu là kiểm tra validation.

### Không dùng một harness quá giả lập

Nếu mục tiêu là test host integration, phải dùng host binding và configuration thực. Harness chỉ nên thay dependency ngoài khi cần kiểm soát response; không được thay chính boundary đang kiểm tra.

## Kiểm thử lexer

Lexer cần test từng loại token và các boundary.

### Token hợp lệ

Ví dụ JUnit:

~~~java
@Test
void scansKeywordsIdentifiersAndOperators() {
    var tokens = lexer.scan("RULE x { WHEN a >= 10 THEN a * 0.1 }");

    assertThat(tokens)
        .extracting(Token::type)
        .contains(
            TokenType.RULE,
            TokenType.IDENTIFIER,
            TokenType.LEFT_BRACE,
            TokenType.WHEN,
            TokenType.GREATER_EQUAL,
            TokenType.NUMBER,
            TokenType.THEN,
            TokenType.STAR,
            TokenType.RIGHT_BRACE,
            TokenType.EOF
        );
}
~~~

Các test nên bao phủ:
- Keyword và identifier.
- Integer và decimal literal.
- String literal.
- Escape sequence.
- Comment.
- Punctuation.
- Operator một và hai ký tự.
- Whitespace.
- Unicode identifier nếu được hỗ trợ.
- EOF.

### Keyword boundary

Tên như ruleName hoặc whenValue không được bị cắt thành keyword RULE hoặc WHEN nếu grammar yêu cầu identifier đầy đủ.

### Number literal

Kiểm tra:
- 0.
- Số âm nếu dấu trừ là unary operator.
- Decimal.
- Exponent nếu hỗ trợ.
- Leading zero.
- Overflow hoặc literal quá lớn.
- Dấu chấm không có chữ số theo grammar.

### String và escape

Test quote, backslash, newline escape, Unicode escape, string rỗng và unterminated string. Lexer cần tạo diagnostic với source span phù hợp.

### Source location

Với input nhiều dòng, xác nhận line/column và offset đúng. Cần xác định offset tính theo byte, Unicode code point hay UTF-16 code unit để IDE và compiler thống nhất.

### Invalid character

Ký tự không được hỗ trợ cần tạo diagnostic rõ và lexer phải có chiến lược recovery. Một ký tự lỗi không nên khiến parser rơi vào vòng lặp vô hạn.

## Kiểm thử parser

Parser test xác nhận grammar và AST shape.

### Parse thành công

~~~java
@Test
void parsesSimpleRule() {
    var result = harness.parse("""
        RULE vipDiscount {
          WHEN customer.level == "GOLD"
          THEN order.total * 0.10
        }
        """);

    assertThat(result.diagnostics()).isEmpty();
    assertThat(result.ast().rules()).hasSize(1);
    assertThat(result.ast().rules().getFirst().name())
        .isEqualTo("vipDiscount");
}
~~~

Nếu project target Java chưa có getFirst(), dùng get(0).

### AST shape

Không chỉ kiểm tra parse success. Cần xác nhận node tree:
- RuleDeclaration có tên và body.
- Condition có LogicalAnd.
- Equality có PropertyAccess và StringLiteral.
- Result expression có Multiply.
- Source span bao phủ đúng construct.

Có thể dùng AST visitor hoặc canonical tree printer để assertion dễ đọc.

### Operator precedence

Ví dụ:

~~~text
a + b * c
~~~

Parser cần tạo Add ở root, Multiply là right child. Kiểm tra cả associativity:

~~~text
a - b - c
~~~

Nếu left-associative, AST tương đương (a - b) - c.

### Parentheses

~~~text
(a + b) * c
~~~

AST phải giữ grouping theo ngoặc. Nếu AST loại bỏ node ParenthesizedExpression, cấu trúc vẫn phải phản ánh grouping đúng.

### Grammar negative tests

Kiểm tra:
- Thiếu closing brace.
- Thiếu expression sau THEN.
- Operator thiếu operand.
- Keyword sai vị trí.
- Duplicate declaration nếu grammar cấm.
- Token dư sau EOF.
- Nested block không hợp lệ.

### Error recovery

Nếu DSL phục vụ IDE, parser cần tạo diagnostics và tiếp tục phân tích phần sau. Test nên xác nhận lỗi trong rule thứ nhất không làm mất rule thứ hai nếu recovery contract hỗ trợ.

### Snapshot AST

Có thể chuẩn hóa AST thành text:

~~~text
Rule(name=vipDiscount)
  Condition
    And
      Equal
        Property(customer, level)
        String("GOLD")
      GreaterEqual
        Property(order, total)
        Decimal(1000000)
  Result
    Multiply
      Property(order, total)
      Decimal(0.10)
~~~

Lưu snapshot giúp phát hiện grammar drift. Snapshot chỉ nên chứa thông tin ổn định, không gồm object address hoặc ID ngẫu nhiên.

## Kiểm thử semantic analysis và type system

Một source có thể đúng grammar nhưng sai nghĩa. Semantic test cần dùng schema rõ ràng.

Ví dụ schema:

~~~java
DslSchema schema = DslSchema.builder()
    .type("customer", ObjectType.builder()
        .field("level", Types.STRING)
        .field("active", Types.BOOLEAN)
        .build())
    .type("order", ObjectType.builder()
        .field("total", Types.DECIMAL)
        .build())
    .build();
~~~

### Name resolution

Kiểm tra:
- Property tồn tại.
- Identifier không tồn tại.
- Scope và shadowing.
- Module import.
- Function resolution.
- Ambiguous symbol.
- Case sensitivity.

Ví dụ source customer.levle phải phát diagnostic UNKNOWN_PROPERTY, không được âm thầm trả null.

### Type checking

Các test:
- String so sánh với String.
- Decimal so sánh với Decimal.
- Boolean dùng trong AND.
- Arithmetic trên kiểu hỗ trợ.
- Function arguments đúng kiểu.
- Return type phù hợp.
- Invalid implicit conversion.
- Nullable value.

### Numeric semantics

Với tiền tệ, dùng Decimal/BigDecimal. Test precision, scale, rounding và boundary. Không so sánh floating-point bằng equality tuyệt đối nếu DSL semantics cho phép sai số.

### Null và missing

Phân biệt:
- Field tồn tại và có null.
- Field không tồn tại.
- Optional value chưa có.
- Empty string.
- Empty collection.

Test truth table cho comparison, AND, OR, NOT và equality theo semantics DSL.

### Static validation

Nếu rule cần trả Decimal, source trả String phải tạo diagnostic trước runtime. Nếu function yêu cầu permission, analyzer hoặc policy checker cần phát hiện thiếu quyền theo contract.

### Diagnostics

Assert code và source span thay vì chỉ so sánh message text:

~~~java
assertThat(result.diagnostics())
    .extracting(Diagnostic::code)
    .contains("UNKNOWN_PROPERTY");
~~~

Message có thể được chỉnh câu chữ, còn diagnostic code nên ổn định cho tooling.

## Kiểm thử evaluator

Evaluator chạy resolved program với context. Test cần bao phủ kết quả và lỗi.

### Happy path

~~~java
@Test
void evaluatesVipDiscount() {
    var context = context(
        customer("GOLD"),
        order(new BigDecimal("1500000.00"))
    );

    var result = harness.evaluate(VIP_RULE, schema, context);

    assertThat(result.success()).isTrue();
    assertThat(result.value())
        .isEqualTo(new BigDecimal("150000.0000"));
}
~~~

Expected scale phụ thuộc arithmetic policy của DSL; test phải phản ánh contract đã định nghĩa.

### Boundary values

Với điều kiện total >= 1,000,000, test:
- 999,999.99.
- 1,000,000.00.
- 1,000,000.01.
- Zero.
- Negative value nếu domain cho phép.
- Null hoặc missing total.

### Boolean evaluation

Kiểm tra short-circuit nếu DSL cam kết:
- false AND expression không được đánh giá.
- true OR expression không được đánh giá.

Nếu expression có side effect, cần test rằng evaluation order đúng semantics. Nếu DSL yêu cầu guard pure, analyzer nên từ chối side-effecting function trong condition.

### Evaluation error

Test chia cho zero, missing function, invalid cast, recursion limit và host exception. Runtime cần trả structured error, không làm crash host process.

### Isolation giữa execution

Chạy cùng compiled rule với hai context khác nhau. Kết quả không được chia sẻ biến hoặc state giữa invocation. Nếu evaluator cache mutable frame trong compiled program, test concurrency sẽ phát hiện lỗi.

### Cancellation và timeout

Inject cancellation token và deterministic clock. Xác nhận evaluator dừng theo policy, giải phóng resource và trả đúng status.

## Kiểm thử diagnostics

Diagnostics là một phần API của DSL. Chúng được dùng bởi CLI, IDE, CI và host application.

Một diagnostic model có thể gồm:

~~~text
Diagnostic
  code
  severity
  message
  sourceId
  startOffset
  endOffset
  relatedInformation[]
  suggestedFix
~~~

### Stable code

Test code như SYNTAX001, UNKNOWN_SYMBOL, TYPE_MISMATCH hoặc RUNTIME_TIMEOUT. Không nên để test phụ thuộc hoàn toàn vào câu message.

### Source span

Kiểm tra start/end offset cho:
- Token lỗi.
- Identifier không resolve.
- Function call sai argument.
- Expression có type mismatch.
- Runtime error gắn với call site.

### Related information

Với duplicate declaration, diagnostic có thể chỉ ra cả vị trí khai báo đầu và khai báo sau. Test xác nhận related location.

### Severity

Warning, error và fatal cần được phân biệt. CI có thể dùng severity threshold nên thay đổi severity cũng là behavior cần test.

### Serialization

Nếu diagnostics được trả qua JSON hoặc LSP, test schema và field compatibility. Không serialize internal exception hoặc secret.

## Kiểm thử host integration

Host integration xác nhận DSL kết nối đúng với application services.

### Context mapping

Tạo authenticated principal, tenant và domain object qua host fixture. Chạy DSL rồi xác nhận context được map đúng. Không cho source DSL tự giả mạo principal hoặc tenant.

### Function binding

Đăng ký host function:

~~~java
registry.register(
    "customer.isActive",
    (Customer customer) -> customer.isActive()
);
~~~

Test signature, overload, null handling, exception mapping và permission. Nếu function có side effect, cần metadata và test idempotency/transaction.

### Repository integration

Nếu DSL đọc database, test trên database engine phù hợp để xác nhận query, transaction, type mapping và tenant filter. In-memory database chỉ phù hợp khi behavior cần test không phụ thuộc khác biệt engine.

### Transaction

Nếu DSL gọi nhiều host action trong transaction, kiểm tra commit và rollback. Nếu action gọi external service, kiểm tra compensation hoặc outbox thay vì giả định rollback database sẽ hoàn tác side effect bên ngoài.

### Event integration

Kiểm tra outgoing event chỉ được publish theo commit policy, payload đúng schema và duplicate event được xử lý theo idempotency contract.

### Authorization

Test principal có quyền và không có quyền. Unauthorized action không được gọi host service. Nếu policy service unavailable, action nhạy cảm cần fail closed theo contract.

### Error mapping

Host cần ánh xạ DSL diagnostic sang API response hoặc domain error. Không trả raw stack trace hoặc secret.

## Kiểm thử property-based

Unit test truyền thống dùng một số input cụ thể. Property-based testing sinh nhiều input để kiểm tra tính chất tổng quát.

Một số property hữu ích:

### Parse-print-parse

Nếu DSL có formatter:

~~~text
parse(source) -> AST
format(AST) -> normalizedSource
parse(normalizedSource) -> AST2
~~~

AST và AST2 cần tương đương theo canonical representation.

### Deterministic evaluation

Với pure expression và cùng context, evaluation lặp lại phải cho cùng kết quả.

### Constant folding equivalence

Nếu optimizer fold expression hằng, kết quả trước và sau optimization phải tương đương.

### Numeric invariants

Với domain money, có thể kiểm tra rounding và precision theo rule. Tránh property quá rộng nếu semantics không bảo đảm phép toán có tính kết hợp.

### No crash

Với source ngẫu nhiên trong giới hạn, lexer/parser phải trả token/AST/diagnostic hoặc resource-limit result, không crash hoặc treo vô hạn.

### Generator có giới hạn

Generator nên giới hạn:
- Expression depth.
- Token count.
- String length.
- Collection size.
- Numeric range.
- Recursion.
- Execution budget.

Property-based test cần seed được lưu khi fail để tái hiện.

## Golden tests và regression corpus

Golden tests lưu kết quả kỳ vọng cho source hoặc behavior đại diện.

### Fixture organization

~~~text
fixtures/
  valid/
    simple-rule.dsl
    nested-expression.dsl
  invalid/
    missing-brace.dsl
    unknown-property.dsl
  semantic/
    decimal-boundary.dsl
    null-condition.dsl
golden/
  ast/
  diagnostics/
  evaluation/
~~~

### Golden AST

Lưu canonical AST để phát hiện parser thay đổi. Không snapshot internal object serialization nếu format không ổn định.

### Golden diagnostics

Lưu code, severity, span và message template. Nếu message được localization, snapshot nên dùng locale cố định hoặc chỉ assert các field contract.

### Golden execution

Lưu input context và expected result. Với action, lưu expected side effect record trong fake host service hoặc database fixture.

### Regression from bug reports

Mỗi bug được sửa nên có test tái hiện. Fixture nên mô tả bug và expected behavior để tránh lỗi quay lại.

### Review snapshot

Không tự động cập nhật golden output khi test fail. Review cần xác định khác biệt là intended behavior change hay regression.

## Kiểm thử compatibility

Khi DSL có nhiều language/runtime version, test suite cần chạy corpus cũ trên candidate runtime.

### Source compatibility

Lưu source fixtures theo version và kiểm tra parse/compile.

### Semantic compatibility

Chạy cùng source và input trên runtime cũ và mới, so sánh result, error category và side effect theo contract.

### Host API compatibility

Kiểm tra function signature, return type, permission và transaction behavior.

### Artifact compatibility

Nạp AST/bytecode/plan cũ nếu format được hỗ trợ; nếu không, xác nhận runtime từ chối với diagnostic rõ hoặc rebuild từ source.

### Migration test

Chạy migration tool, parse source sau migration, so sánh semantics và chạy tool lần hai để xác nhận idempotency.

## Kiểm thử security và resource limits

DSL có thể nhận source từ user hoặc tenant. Test cần xem source như input không tin cậy.

### Input abuse

Thử:
- Source quá lớn.
- Expression lồng quá sâu.
- String literal rất dài.
- Nhiều identifier.
- Import cycle.
- Regex tốn CPU nếu hỗ trợ regex.
- Recursive function.
- Collection quá lớn.

Runtime cần giới hạn parse depth, execution time, memory và recursion.

### Permission boundary

Kiểm tra user không có quyền không thể gọi host action, đọc secret hoặc truy cập tenant khác.

### Sandbox

Nếu DSL có command/plugin/script, kiểm tra filesystem, network và process isolation trong môi trường test an toàn.

### Injection

Không nối string từ input user vào shell, SQL hoặc query text tùy tiện. Dùng parameter binding hoặc API cấu trúc. Test payload có quote, delimiter và metacharacter.

### Secret redaction

Dùng fake secret marker để xác nhận secret không xuất hiện trong diagnostic, log, trace, result hoặc cache không bảo vệ.

### Denial of service

Kiểm tra resource budget, cancellation và concurrency limit. Một source độc hại không được chiếm hết worker pool.

## Kiểm thử concurrency và lifecycle

Runtime thường được chia sẻ giữa nhiều request.

### Concurrent evaluation

Chạy cùng compiled program với nhiều context đồng thời. Kết quả phải độc lập và deterministic nếu expression pure.

### Concurrent compilation

Nhiều request cùng compile một module. Cache/single-flight không được trả AST hoặc artifact chưa hoàn chỉnh.

### Reload

Khi source mới được publish, request mới dùng revision mới; request đang chạy dùng snapshot đã pin theo contract. Không có trạng thái registry nửa cũ nửa mới.

### Shutdown

Host shutdown cần ngừng nhận execution mới, chờ hoặc cancel execution đang chạy, đóng thread pool và giải phóng resource.

### Stress test

Chạy mixed workload gồm parse, compile, evaluate, reload và host calls. Theo dõi memory, thread, connection và latency. Stress test dài có thể chạy riêng khỏi suite nhanh.

## Kiểm thử performance

Performance test xác nhận các giới hạn thực tế, không chỉ kết quả đúng.

### Parse benchmark

Đo:
- Source nhỏ/lớn.
- AST node count.
- Cold parse và warm cache.
- Error recovery.
- Import graph.
- Incremental parse nếu có.

### Evaluation benchmark

Đo expression đơn giản, nested expression, function call và nhiều rule. Tách thời gian DSL runtime khỏi thời gian host service.

### Allocation và memory

Theo dõi allocation rate, retained AST, cache size và GC. Cache có thể tăng memory dù giảm parse CPU.

### Throughput và tail latency

Đo concurrency và p50/p95/p99 latency. Không chỉ báo average vì request chậm có thể bị che khuất.

### Performance regression threshold

Ngưỡng CI cần đủ rộng để tránh flaky do máy build. Benchmark nghiêm túc nên chạy trên môi trường kiểm soát và lưu baseline theo runtime version.

## Test data và tính xác định

Một bộ test đáng tin cậy cần tái lập kết quả.

### Fake clock

Inject clock thay vì gọi system time trực tiếp. Test có thể đặt thời điểm cố định và tiến clock để kiểm tra deadline.

### Stable IDs

Dùng ID fixture cố định hoặc deterministic generator. Không phụ thuộc database auto-increment nếu không cần.

### Locale và timezone

Đặt locale/timezone rõ ràng. Không để test phụ thuộc cấu hình máy developer hoặc CI runner.

### Database isolation

Mỗi test cần transaction rollback, schema riêng hoặc unique namespace. Nếu test kiểm tra commit/outbox, cần quan sát dữ liệu sau commit thay vì rollback fixture quá sớm.

### External service

Dùng fake server hoặc test double có contract rõ cho success, timeout, retryable error và malformed response. Không gọi production service trong test suite.

### Test order independence

Chạy test theo thứ tự khác nhau hoặc song song để phát hiện shared mutable state. Một test không được phụ thuộc cache hoặc registry do test trước tạo ra.

## CI pipeline cho bộ kiểm thử DSL

Một pipeline cơ bản:

~~~text
Checkout
   |
   v
Compile production code
   |
   v
Run lexer/parser tests
   |
   v
Run semantic/runtime tests
   |
   v
Run host integration tests
   |
   v
Run compatibility/security tests
   |
   v
Run performance smoke
   |
   v
Publish test reports
~~~

### Phân tầng suite

- Fast: unit và component tests chạy ở mỗi commit.
- Integration: host/database/broker tests chạy trên pull request hoặc merge.
- Compatibility: version matrix chạy theo release candidate hoặc thay đổi language core.
- Security: negative tests và fuzz corpus theo lịch hoặc khi thay đổi boundary.
- Performance: benchmark trên runner ổn định.

### Test report

Report nên phân biệt:
- Assertion failure.
- Test setup failure.
- Dependency unavailable.
- Timeout.
- Infrastructure failure.
- Skipped test.
- Flaky retry.

Không nên tự động retry mọi failure rồi coi build thành công. Retry có thể che race condition.

### Coverage

Line coverage giúp phát hiện code chưa chạy, nhưng không chứng minh semantics đúng. Cần kết hợp branch coverage, decision table, mutation testing hoặc property tests cho logic quan trọng.

### Mutation testing

Mutation testing cố ý thay đổi một biểu thức hoặc điều kiện để kiểm tra test có phát hiện không. Nếu đổi >= thành > mà test vẫn pass, có thể thiếu boundary test. Mutation testing có chi phí runtime nên thường chạy chọn lọc.

## Ví dụ test end-to-end cho DSL rule

Một test integration có thể đi qua toàn pipeline:

~~~java
@Test
void vipOrderReceivesDiscountThroughHostApplication() {
    var customer = new Customer("c-1", "GOLD", true);
    var order = new Order("o-1", new BigDecimal("1500000.00"));

    var result = hostDslService.evaluate(
        "pricing.vipDiscount",
        Map.of(
            "customer", customer,
            "order", order
        )
    );

    assertThat(result.status()).isEqualTo(SUCCESS);
    assertThat(result.value())
        .isEqualTo(new BigDecimal("150000.0000"));
}
~~~

Test này cần khởi tạo host integration thực tế để xác nhận module được resolve, function registry được đăng ký, context mapping đúng và result được trả về. Nếu host service ghi dữ liệu hoặc tạo event, test cần kiểm tra cả side effect đó.

### Negative end-to-end test

~~~java
@Test
void unknownCustomerFieldReturnsDiagnostic() {
    var source = """
        RULE invalid {
          WHEN customer.levle == "GOLD"
          THEN order.total * 0.10
        }
        """;

    var result = hostDslService.validate(source);

    assertThat(result.success()).isFalse();
    assertThat(result.diagnostics())
        .extracting(Diagnostic::code)
        .contains("UNKNOWN_PROPERTY");
}
~~~

Test cần xác nhận host trả diagnostic có cấu trúc, không ném exception nội bộ ra API.

### Test unauthorized action

Nếu DSL có host action, tạo principal không có permission và xác nhận action không được gọi. Chỉ assert response là DENIED là chưa đủ; cần kiểm tra không có side effect.

## Checklist deliverables của dự án thực hành

Kết quả dự án nên có:

| Deliverable | Nội dung |
|---|---|
| Test harness | Cách khởi tạo lexer/parser/runtime/host |
| Lexer tests | Token, literal, operator, source location |
| Parser tests | Grammar, precedence, AST, recovery |
| Semantic tests | Name resolution, type, null, diagnostics |
| Evaluator tests | Result, error, boundary, determinism |
| Host integration tests | Context, function, persistence, transaction |
| Golden corpus | AST, diagnostics, expected evaluation |
| Property tests | Invariants và generated input |
| Compatibility suite | Source/runtime version matrix |
| Security suite | Permission, resource limit, injection |
| Performance suite | Parse/evaluate latency và memory |
| CI workflow | Chạy suite và lưu report |
| Documentation | Cách chạy test và thêm fixture |

### Tiêu chí hoàn thành

Một bộ test có thể được coi là sẵn sàng cho pilot khi:
- Các grammar construct được hỗ trợ có positive và negative test.
- Operator precedence và type behavior được kiểm tra.
- Diagnostics có code và source span.
- Evaluator có boundary và null tests.
- Host context và permission được kiểm tra.
- Test chạy lặp lại với kết quả deterministic.
- Có ít nhất một compatibility corpus.
- Có resource limit và security test cho input không tin cậy.
- CI chạy được suite phù hợp và tạo report.
- Mỗi bug được sửa có regression test.

## Những lỗi thường gặp khi viết bộ kiểm thử DSL

### Chỉ test happy path

Source hợp lệ đơn giản không bao phủ malformed input, null, boundary và concurrency. Cần cả positive lẫn negative test.

### Chỉ assert parse success

AST có thể sai cấu trúc nhưng parser vẫn trả success. Assert node shape hoặc canonical representation.

### Test phụ thuộc message text

Message có thể được sửa hoặc dịch. Dùng diagnostic code, severity và source span làm contract chính.

### Dùng mock cho boundary cần kiểm tra

Mock toàn bộ host adapter không kiểm tra transaction, type mapping hoặc dependency injection. Giữ implementation thật tại boundary đang được test.

### Dùng sleep trong async test

Sleep làm test chậm và flaky. Dùng future, latch, deterministic scheduler hoặc fake clock.

### Không test null và precision

Đây là các nguồn regression phổ biến của DSL nghiệp vụ. Định nghĩa semantics và tạo fixture boundary.

### Dùng test fixture không hợp lệ ngoài ý muốn

Domain object sai invariant có thể làm test fail trước khi DSL chạy. Dùng fixture builder và tạo invalid case có chủ đích.

### Golden snapshot quá chi tiết

Snapshot internal ID hoặc timestamp tạo diff nhiễu. Chỉ snapshot phần representation ổn định.

### Không cô lập cache và registry

State còn lại từ test trước làm kết quả phụ thuộc thứ tự. Dùng namespace riêng hoặc reset có kiểm soát.

### Không kiểm tra side effect

Result đúng không chứng minh database/event đúng. Assert host state và external boundary.

### Không lưu seed của property test

Lỗi ngẫu nhiên không thể tái hiện làm giảm giá trị property testing. Ghi seed và input khi fail.

### Không có owner cho fixture

Khi grammar thay đổi, fixture cần được cập nhật có review. Không tự động xóa test cũ để build pass.

## Quy trình thực hiện dự án

Có thể triển khai theo các bước:

1. **Định nghĩa contract:** ghi rõ grammar, type, null, error, evaluation và host behavior cần hỗ trợ.
2. **Chọn DSL mẫu:** tạo một số rule đại diện cho success, boundary và invalid case.
3. **Thiết lập test harness:** inject schema, clock, registry, context và resource limits.
4. **Viết lexer tests:** token, literal, escape, comment, Unicode và source location.
5. **Viết parser tests:** AST shape, precedence, syntax error và recovery.
6. **Viết semantic tests:** name resolution, type, overload, nullability và diagnostics.
7. **Viết evaluator tests:** arithmetic, Boolean, boundary, exception và isolation.
8. **Viết host integration tests:** context, function binding, database, transaction và authorization.
9. **Tạo golden corpus:** AST, diagnostics, result và regression fixtures.
10. **Bổ sung property/fuzz tests:** invariants, malformed source và resource limit.
11. **Bổ sung compatibility tests:** source version, host API và artifact.
12. **Bổ sung security/performance tests:** permission, injection, memory, latency và concurrency.
13. **Tích hợp CI:** phân tầng suite, report, timeout và environment pinning.
14. **Thiết lập quy trình regression:** mỗi bug có test tái hiện; mọi golden update cần review.
15. **Đánh giá pilot:** theo dõi flaky rate, test duration, defect escape và chi phí bảo trì suite.

## Kết luận

Viết bộ kiểm thử cho DSL cần kiểm tra toàn bộ hành trình từ source text đến kết quả trong host application. Lexer và parser cần positive/negative fixtures; semantic analyzer cần kiểm tra type, name resolution và diagnostics; evaluator cần boundary, null, precision, determinism và error tests. Host integration cần xác nhận context, permission, transaction, persistence và side effect.

Một suite bền vững kết hợp unit/component tests, golden corpus, property-based testing, compatibility tests, security tests và performance tests. Test harness phải deterministic, fixture cần được cô lập và diagnostics nên có code ổn định. CI nên phân tầng test theo thời gian và rủi ro, đồng thời giữ regression test cho mỗi lỗi đã sửa.

Khi bộ test được xem như một phần của language contract, nhóm có thể thay đổi parser, runtime và host integration với bằng chứng rõ ràng rằng behavior được hỗ trợ vẫn đúng. Đây là nền tảng để DSL phát triển qua nhiều phiên bản mà không phụ thuộc vào kiểm tra thủ công hoặc một vài ví dụ happy path.

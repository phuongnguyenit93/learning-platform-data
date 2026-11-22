# Property-based test

Khi xây dựng một ngôn ngữ miền đặc thù (Domain-Specific Language — DSL), kiểm thử bằng một vài ví dụ cố định thường chưa đủ để phát hiện các lỗi phát sinh từ tổ hợp cú pháp, dữ liệu, kiểu và trạng thái thực thi. Một biểu thức có thể hoạt động với số nguyên dương nhưng sai với số âm; parser có thể đọc đúng chương trình ngắn nhưng lỗi ở nesting sâu; serializer có thể giữ nguyên object đơn giản nhưng làm mất thông tin khi có optional field hoặc Unicode; optimizer có thể tạo kết quả khác interpreter ở một nhóm input hiếm.

**Property-based testing** (kiểm thử dựa trên thuộc tính) là phương pháp kiểm thử trong đó người viết mô tả những tính chất phải đúng với nhiều input được sinh tự động. Thay vì chỉ viết một input và một expected output, ta định nghĩa generator tạo dữ liệu thuộc miền cần kiểm tra, rồi định nghĩa property/invariant để xác nhận hành vi. Framework thực hiện property nhiều lần với các input khác nhau và thường cố gắng thu nhỏ input gây lỗi thành một trường hợp phản ví dụ đơn giản.

Ví dụ với một DSL biểu thức số học, property có thể phát biểu: parse một biểu thức hợp lệ rồi format và parse lại phải giữ nguyên cấu trúc/ngữ nghĩa; hoặc đánh giá biểu thức bằng interpreter và compiled evaluator phải cho cùng kết quả. Generator có thể tạo AST gồm literal, phép cộng, nhân và ngoặc; serializer chuyển AST thành source text; parser đọc lại; evaluator so sánh kết quả.

~~~mermaid
flowchart TD
    A[Define property] --> B[Generate input]
    B --> C[Run DSL operation]
    C --> D[Check invariant]
    D --> E{Pass?}
    E -->|Yes| F[Generate next case]
    F --> B
    E -->|No| G[Shrink counterexample]
    G --> H[Reproduce and diagnose]
~~~

Property-based testing đặc biệt hữu ích với DSL vì không gian input thường rất lớn: nhiều grammar production, expression tree, kiểu dữ liệu, biến thể optional, import graph, rule combination và execution state. Phương pháp này không thay thế hoàn toàn example-based test; hai cách bổ sung cho nhau. Example test diễn tả trường hợp nghiệp vụ cụ thể, còn property test tìm lỗi trong nhiều trường hợp mà người viết test khó liệt kê hết.

## 1. Property-based testing là gì?

Một property là phát biểu tổng quát về hành vi của hệ thống. Nó mô tả điều phải đúng với mọi input thuộc một miền xác định, hoặc với mọi input thỏa điều kiện tiền đề.

Một property thường có dạng:

~~~text
for every input x in Domain:
    if Precondition(x):
        assert Invariant(Operation(x))
~~~

Ví dụ:
- Với mọi AST hợp lệ, serialize rồi parse lại phải bảo toàn cấu trúc theo canonical form.
- Với mọi expression được hỗ trợ, interpreter và compiler phải cho kết quả tương đương.
- Với mọi schema hợp lệ, payload do generator tạo theo schema phải pass validator.
- Với mọi invalid input, parser phải trả diagnostic có source span hợp lệ và không crash.
- Với mọi sequence command hợp lệ, state machine không được chuyển sang trạng thái terminal trái phép.

### Generator

Generator là thành phần tạo input theo một phân phối hoặc cấu trúc nhất định. Với DSL, generator có thể tạo source text, token stream, AST, schema, module graph, input data hoặc sequence thao tác.

### Shrinking

Khi một input làm property thất bại, shrinking tìm input nhỏ hơn vẫn tái hiện lỗi. Ví dụ một workflow 80 step được thu nhỏ còn hai step và một nhánh gây lỗi, giúp tìm nguyên nhân dễ hơn.

### Seed và reproducibility

Framework thường dùng random seed để sinh input. Khi test fail, seed và counterexample cần được lưu để chạy lại chính xác. Không nên chỉ ghi “property failed after 342 tries” mà thiếu dữ liệu tái hiện.

### Statistical exploration

Property test không chứng minh đúng với mọi input vô hạn. Nó tăng độ bao phủ bằng cách khám phá nhiều input được sinh theo generator. Chất lượng phụ thuộc vào property, generator, distribution, shrinker và số lần chạy.

## 2. Vì sao DSL phù hợp với property-based testing?

DSL thường có một grammar định nghĩa tập chương trình hợp lệ và semantics xác định cách chương trình hoạt động. Đây là nền tảng tốt để sinh input có cấu trúc và kiểm tra các quan hệ tổng quát.

### Không gian cú pháp lớn

Một grammar có thể kết hợp declaration, statement, expression, type, annotation, import và nested block. Test thủ công khó bao phủ mọi tổ hợp.

### Tổ hợp kiểu và giá trị

Một expression có thể chứa Integer, Decimal, String, Boolean, date/time, collection, nullability và function call. Các lỗi thường chỉ xuất hiện ở ranh giới kiểu hoặc tổ hợp lồng nhau.

### Nhiều implementation cần tương đương

DSL có thể có interpreter, compiler, optimizer, evaluator, serializer và code generator. Có thể kiểm tra các implementation độc lập bằng cùng input và so sánh semantics.

### Round-trip tự nhiên

Parser và formatter/serializer có quan hệ thuận nghịch. Một AST được format rồi parse lại nên tương đương với AST ban đầu theo định nghĩa canonicalization.

### State transition phong phú

Workflow/rule engine có trạng thái, retry, timeout, branch, event và cancellation. Model-based property có thể tạo sequence hành động và xác nhận invariant xuyên suốt.

### Regression từ lỗi cũ

Khi phát hiện một counterexample, có thể lưu nó thành regression example. Property test tiếp tục tìm lỗi mới, còn corpus giữ lỗi cũ không tái xuất hiện.

## 3. Example-based testing và property-based testing

Hai phương pháp giải quyết những câu hỏi khác nhau.

| Tiêu chí | Example-based | Property-based |
|---|---|---|
| Input | Do người viết chọn. | Generator tạo tự động. |
| Expected result | Thường là giá trị cụ thể. | Là invariant hoặc quan hệ tổng quát. |
| Mục tiêu | Kiểm tra tình huống nghiệp vụ đã biết. | Khám phá nhiều trường hợp và tổ hợp. |
| Debug | Thường dễ hiểu ngay. | Cần shrink để đơn giản hóa. |
| Coverage | Phụ thuộc danh sách ví dụ. | Phụ thuộc generator và distribution. |
| Reproducibility | Input cố định. | Seed/counterexample phải được lưu. |
| Vai trò | Regression, acceptance và edge case cụ thể. | Invariant, algebraic law và differential testing. |

Ví dụ test cố định:

~~~java
@Test
void addsTwoNumbers() {
    assertEquals(7, evaluator.evaluate("3 + 4"));
}
~~~

Property tổng quát:

~~~java
@Property
void additionIsCommutative(@ForAll int a, @ForAll int b) {
    assertEquals(
        evaluator.evaluate(a + " + " + b),
        evaluator.evaluate(b + " + " + a)
    );
}
~~~

Ví dụ trên chỉ hợp lệ nếu DSL định nghĩa phép cộng trên miền số nguyên và không có overflow semantics khác biệt. Với string concatenation hoặc Decimal rounding, commutativity có thể có semantics riêng. Property phải phản ánh language specification, không được áp một quy luật toán học ngoài miền hỗ trợ.

## 4. Xác định property tốt

Property phải đủ chính xác để phân biệt đúng/sai, có miền input rõ và tránh giả định sai.

### Invariant

Invariant là điều kiện luôn phải đúng trong một phạm vi. Ví dụ:
- Mọi node AST có source span nằm trong giới hạn source.
- Mọi reference đã resolve đều trỏ đến symbol tồn tại.
- Mọi process instance terminal không tự quay về RUNNING.
- Tổng số item trong collection sau serialize/parse không thay đổi.

### Algebraic law

Một số operation có các luật đại số:
- Cộng số nguyên có tính kết hợp trong miền không overflow.
- Sort hai lần cho kết quả như sort một lần.
- Normalize một giá trị nhiều lần cho kết quả như normalize một lần (idempotence).
- Parse/format có canonicalization ổn định.

### Metamorphic relation

Khi không dễ biết expected output tuyệt đối, tạo một biến đổi input mà output phải thay đổi hoặc giữ nguyên theo quy luật. Ví dụ thêm comment không ảnh hưởng evaluation result; đổi whitespace không ảnh hưởng AST; đổi tên biến đồng bộ ở declaration và reference phải giữ semantics.

### Differential property

Chạy cùng input qua hai implementation độc lập rồi so sánh: interpreter và compiler, parser A và parser B, old runtime và new runtime. Cần tránh dùng chung code path khiến cả hai cùng mắc một lỗi.

### Round-trip property

Kiểm tra một chuỗi chuyển đổi như AST → source → AST, object → JSON → object hoặc schema → generated model → schema. So sánh theo semantics/canonical representation phù hợp.

### Domain property

Một DSL nghiệp vụ có thể cần property riêng: tổng tiền không âm, allocation không vượt capacity, approval threshold tuân theo policy, workflow không phát event sau cancellation. Các property này cần chủ domain xác nhận.

### Tránh property tautology

Property không nên gọi cùng hàm để tạo expected và actual. Nếu formatter và parser cùng dùng chung một implementation lỗi, round-trip có thể pass dù semantics sai. Nên dùng oracle độc lập hoặc luật có thể kiểm chứng từ mô hình khác.

## 5. Generator cho DSL

Generator quyết định input nào được khám phá. Generator tốt cần tạo nhiều input hợp lệ, phân phối có chủ đích và có thể shrink.

Có nhiều cấp generator:

| Cấp | Input sinh ra | Dùng để kiểm tra |
|---|---|---|
| Character | Ký tự, Unicode, whitespace. | Lexer và encoding. |
| Token | Token sequence. | Parser token handling. |
| AST | Expression/declaration tree. | Serializer, compiler và evaluator. |
| Source | Văn bản DSL. | End-to-end parser và diagnostics. |
| Semantic model | Type, symbol, module graph. | Resolver và type checker. |
| Runtime data | Input/variables/context. | Evaluation và execution. |
| Command sequence | Start, signal, retry, cancel. | State machine và workflow runtime. |
| Environment | Config, plugin, dependency versions. | Integration và lifecycle. |

### Sinh AST trước rồi serialize thành source

Với property cần source hợp lệ, sinh AST thường đáng tin cậy hơn sinh text ngẫu nhiên. Generator hiểu grammar và có thể tạo node đúng cấu trúc. Sau đó serializer tạo source để kiểm tra parser.

### Sinh source text trực tiếp

Text generator hữu ích cho lexer, malformed syntax, error recovery và fuzzing. Nhưng nếu chỉ tạo ký tự ngẫu nhiên, phần lớn input có thể sai cú pháp ngay đầu file và không khám phá sâu parser.

### Recursive generator

Expression grammar có thể đệ quy:

~~~text
Expr
  = Literal
  | Variable
  | Unary(Operator, Expr)
  | Binary(Expr, Operator, Expr)
  | Call(FunctionName, List<Expr>)
  | Group(Expr)
~~~

Generator phải giới hạn depth/size để tránh sinh cây quá sâu hoặc quá lớn.

### Weighted choice

Phân phối generator nên ưu tiên cấu trúc thường gặp nhưng vẫn dành tỷ lệ cho edge case. Ví dụ 50% expression đơn giản, 30% binary/nested, 10% function call và 10% boundary form. Tỷ lệ thực tế nên dựa trên grammar/workload của DSL.

### Recursive size control

Một generator recursive cần giảm size budget khi đi xuống nhánh con. Nếu không, nó có thể tạo cây quá lớn hoặc đệ quy vô hạn.

### Generate valid và invalid riêng

Generator hợp lệ dùng để kiểm tra semantics. Generator invalid tạo lỗi có chủ đích như missing delimiter, wrong type hoặc unresolved reference. Không nên trộn hai mục tiêu mà không phân loại expected behavior.

## 6. Generator có nhận thức grammar

Grammar-aware generator hiểu production và sinh node theo cấu trúc hợp lệ.

Ví dụ grammar expression:

~~~text
Expression
    = Literal
    | Identifier
    | "(" Expression ")"
    | Expression Operator Expression
    | Identifier "(" Arguments ")"
~~~

Generator có thể chọn production, tạo child expression rồi build AST. Để tránh ambiguity, AST serializer phải thêm ngoặc cần thiết theo precedence.

### Depth budget

Đặt giới hạn depth để tránh tree quá sâu. Có thể giảm xác suất recursive branch khi gần chạm giới hạn.

### Node budget

Depth thấp vẫn có thể tạo tree rất rộng. Node budget giới hạn tổng số AST node.

### Production coverage

Theo dõi số lần mỗi production được chọn. Nếu generator hiếm khi tạo lambda hoặc generic type, property test có thể bỏ qua phần grammar quan trọng.

### Semantic-aware generation

Một AST cú pháp có thể không type-check. Generator semantic-aware có thể duy trì environment/symbol table để tạo variable đúng scope, function đúng arity và type-compatible expression.

### Scope-aware variable generation

Khi sinh block, generator cần biết variable đã khai báo trong scope nào, variable nào được capture và shadowing hợp lệ ra sao. Cách này giúp tạo nhiều chương trình semantic-valid thay vì chỉ syntactic-valid.

### Module-aware generation

Với import, generator tạo module graph không cycle hoặc cycle theo policy. Reference được sinh dựa trên symbol export thật để resolver có thể chạy đến sâu.

## 7. Generator cho expression và type system

Expression generator nên gắn type mong muốn để kiểm soát tính hợp lệ.

Ví dụ một generator có thể nhận expected type:

~~~text
generateExpression(expectedType, depth):
    if depth == 0:
        return generateLiteral(expectedType)

    choose compatible production:
        literal
        variable of expectedType
        function call returning expectedType
        operator whose result is expectedType
        conditional with both branches expectedType
~~~

### Typed generation

Nếu expected type là Boolean, generator có thể tạo comparison, logical operator hoặc Boolean literal. Nếu expected type là Decimal, nó tạo literal và operator phù hợp.

### Type boundary

Sinh giá trị tại min/max, zero, negative, empty string, maximum precision, scale boundary, null và optional absence. Boundary values thường phát hiện lỗi nhiều hơn phân phối random đều.

### Numeric overflow

Nếu DSL dùng fixed-width integer, generator cần sinh quanh MIN_VALUE/MAX_VALUE và kiểm tra overflow semantics. Không giả định Java overflow và DSL overflow luôn giống nhau.

### Decimal precision

Sinh Decimal ở scale tối đa, precision tối đa, số âm, zero và giá trị gần rounding boundary. So sánh theo contract về scale và rounding mode.

### Temporal values

Sinh Instant quanh epoch, leap day, timezone offset, DST transition và boundary của supported date range. Nếu DSL dùng local time, kiểm tra ambiguous/nonexistent local times.

### Nullability và optionality

Sinh ba trạng thái khi schema cho phép: field missing, explicit null và present value. Chúng cần được giữ riêng nếu API/DSL phân biệt.

## 8. Shrinking: thu nhỏ phản ví dụ

Shrinking là điểm mạnh quan trọng của property-based testing. Khi input lớn gây lỗi, framework thử giảm input mà vẫn giữ property fail.

Ví dụ input lỗi:

~~~text
process Fulfill {
    step Validate { ... }
    parallel Ship {
        branch A { ... }
        branch B { ... }
    }
    if condition {
        call nested(...)
    }
}
~~~

Shrinker có thể loại declaration không liên quan, bỏ branch, rút expression và giảm literal để tạo trường hợp nhỏ hơn.

### Shrink AST

Các phép shrink phổ biến:
- Thay subtree bằng child.
- Thay expression bằng literal cùng type.
- Bỏ statement không cần thiết.
- Rút danh sách về ít phần tử hơn.
- Giảm nesting depth.
- Giảm số declaration.
- Rút string/number về giá trị đơn giản.
- Xóa annotation không ảnh hưởng lỗi.

### Preserve validity

Nếu property chỉ áp dụng cho chương trình type-correct, shrinker cần giữ chương trình hợp lệ. Xóa một declaration có thể làm reference unresolved; thay expression có thể đổi type. Shrinker grammar-aware và type-aware giúp counterexample vẫn có ý nghĩa.

### Shrink invalid input

Với property kiểm tra parser error recovery, shrinker có thể cần giữ lỗi cú pháp cụ thể. Ví dụ luôn giữ token thiếu hoặc delimiter sai, đồng thời bỏ phần source không liên quan.

### Local minimum

Shrinking thường tìm input nhỏ theo các phép biến đổi đã định nghĩa, không bảo đảm tìm input nhỏ nhất toàn cục. Chất lượng shrinker phụ thuộc cách mô hình hóa cấu trúc.

### Shrinking không được che lỗi

Nếu shrinker biến input thành một trường hợp mà property không còn áp dụng, framework có thể báo kết quả khó hiểu. Cần dùng precondition/assumption hợp lý và xác nhận candidate shrink vẫn thuộc miền test.

## 9. Property cho lexer và tokenizer

Lexer có thể được kiểm tra bằng nhiều luật tổng quát.

### Token span hợp lệ

Mọi token phải có start/end offset hợp lệ, start không âm, end không vượt source length và end không nhỏ hơn start.

### Token ordering

Token stream phải được sắp theo source position, không overlap trừ khi lexer có channel/overlap semantics được định nghĩa.

### Concatenation/coverage

Nếu lexer giữ trivia, ghép lexeme của token và trivia theo thứ tự phải tái tạo source theo quy tắc encoding/normalization. Nếu whitespace bị bỏ, source reconstruction cần dùng source buffer và offset.

### Keyword và identifier

Keyword phải được nhận đúng token type; identifier dài hơn keyword như ifReady không được token hóa thành IF rồi IDENTIFIER nếu grammar yêu cầu longest match.

### Unicode stability

Lexer phải xử lý đúng surrogate pair, combining marks và ký tự ngoài BMP theo language specification.

### Invalid character

Ký tự không được phép phải tạo diagnostic với source span đúng, không treo hoặc bỏ qua âm thầm.

### Metamorphic whitespace property

Thêm whitespace ở vị trí grammar cho phép không làm thay đổi token sequence có ý nghĩa hoặc AST. Comment cũng có thể được chèn ở vị trí hợp lệ mà không đổi semantics.

## 10. Property cho parser và AST

Parser là nơi property-based testing có thể khám phá nhiều cấu trúc grammar.

### Parse-format-parse

Với AST hợp lệ A:

1. Format A thành source S.
2. Parse S thành AST B.
3. So sánh A và B theo canonical AST equivalence.

Không nên so sánh object identity hoặc source formatting nếu format được phép chuẩn hóa.

### AST source span

Mỗi node có source span nằm trong source và child span nằm trong phạm vi parent theo grammar rule. Node synthetic cần có semantics riêng.

### Deterministic parsing

Cùng source và cùng language version phải tạo AST/diagnostic tương đương. Không để hash iteration order hoặc global mutable state làm kết quả thay đổi.

### Whitespace/comment invariance

Biến đổi whitespace/comment hợp lệ không được đổi semantic AST. Nếu CST lưu trivia, so sánh semantic projection thay vì toàn bộ tree.

### Parentheses relation

Thêm ngoặc quanh expression theo grammar cho phép có thể giữ evaluation result, nhưng AST shape có thể khác. Property nên so sánh semantic equivalence hoặc normalized AST.

### Error recovery property

Parser không được crash với source arbitrary trong giới hạn tài nguyên. Diagnostic span phải hợp lệ và recovery phải tiến triển để tránh infinite loop.

### Prefix property

Với grammar hỗ trợ incomplete parse, prefix của valid source có thể tạo partial tree hoặc incomplete diagnostic. Không giả định mọi prefix đều parse thành công.

## 11. Property cho formatter và pretty printer

Formatter thường có tính chất ổn định và bảo toàn semantics.

### Idempotence

Format một source đã format lần nữa phải cho kết quả không đổi:

~~~text
format(format(source)) == format(source)
~~~

Property này cần xác định formatter có giữ comment, line ending và trivia hay không.

### Semantic preservation

Parse source ban đầu và source sau format phải tương đương về AST semantics.

### Stable output

Cùng AST và formatting configuration phải tạo cùng output. Không phụ thuộc locale hoặc platform newline nếu contract yêu cầu canonical output.

### Width constraints

Nếu formatter có line width, các line nên tuân thủ quy tắc đã công bố, ngoại trừ literal/token không thể ngắt.

### Comment preservation

Nếu comment là thành phần có ý nghĩa cho documentation hoặc directive, formatter không được làm mất hoặc đổi vị trí sai.

### Unicode and escaping

Format/parse round-trip phải giữ đúng string value, escape sequence và Unicode normalization theo contract.

## 12. Property cho interpreter, compiler và optimizer

Một DSL có thể có nhiều cách thực thi. Đây là cơ hội cho differential testing.

### Interpreter/compiler equivalence

Với mọi program P và input X thuộc miền được hỗ trợ:

~~~text
evaluateInterpreter(P, X)
    == evaluateCompiled(P, X)
~~~

Cần chuẩn hóa exception, decimal scale, ordering và side effect observation trước khi so sánh.

### Optimizer preservation

Với optimizer O:

~~~text
evaluate(P, X) == evaluate(O(P), X)
~~~

Property cần tránh chương trình có undefined behavior hoặc nondeterministic function nếu chưa định nghĩa semantics.

### Constant folding

Thay biểu thức hằng bằng giá trị tính trước phải giữ kết quả. Ví dụ 2 * 3 có thể fold thành 6, nhưng cần tôn trọng overflow, decimal rounding và evaluation error.

### Short-circuit semantics

Với AND/OR, expression bên phải có thể không được đánh giá nếu vế trái quyết định kết quả. Property cần kiểm tra cả giá trị và side effect/call count nếu DSL cho phép function có side effect.

### Evaluation order

Nếu DSL định nghĩa thứ tự evaluate argument hoặc operand, property có thể sinh trace để xác nhận thứ tự đó. Không giả định toán tử giao hoán nếu có side effect.

### Exception equivalence

Interpreter và compiler cần phân loại lỗi tương đương theo contract: divide-by-zero, unresolved variable, type error, timeout. Message có thể khác nhưng error code/semantic category cần khớp.

### State equivalence

Với workflow engine, so sánh final state và event trace giữa hai runtime version trên cùng generated workflow/input, nếu semantics được kỳ vọng giống nhau.

## 13. Metamorphic testing cho DSL

Metamorphic testing kiểm tra quan hệ giữa input và output sau một biến đổi được biết trước.

Các metamorphic relation hữu ích:

| Biến đổi input | Quan hệ kỳ vọng |
|---|---|
| Thêm whitespace hợp lệ | AST semantics không đổi. |
| Thêm comment không ảnh hưởng | Evaluation result không đổi. |
| Format rồi parse | AST tương đương. |
| Rename biến nhất quán | Result không đổi nếu binding được giữ. |
| Reorder declaration độc lập | Semantics không đổi nếu language cho phép. |
| Thêm ngoặc dư hợp lệ | Evaluation result không đổi. |
| Serialize rồi deserialize | Model tương đương. |
| Chạy optimizer | Result không đổi. |
| Evaluate cùng input hai lần trong pure DSL | Result giống nhau. |
| Thêm unused declaration | Semantics phần đang xét không đổi nếu không có side effect khi load. |

### Cẩn trọng với giả định

Reorder declaration chỉ an toàn nếu declaration order không mang semantics. Thêm comment có thể không an toàn nếu DSL dùng comment directive. Rename variable cần cập nhật mọi reference và không được capture/shadow một symbol khác.

### Relation có điều kiện

Mỗi metamorphic property cần precondition. Ví dụ thêm ngoặc chỉ hợp lệ quanh expression không tạo thay đổi parsing do generic/type syntax.

### Chuỗi biến đổi

Có thể áp nhiều biến đổi liên tiếp: format, add comments, rename symbols, reorder independent declarations. Sau mỗi bước so sánh canonical semantics để tìm nơi behavior lệch.

## 14. Property cho schema và serialization

DSL schema thường có nhiều combination field, type và constraint.

### Generated payload validity

Với schema S, generator tạo payload P theo S. Validator phải chấp nhận P.

### Mutation invalidation

Tạo P hợp lệ rồi mutate một field theo cách vi phạm constraint. Validator phải từ chối với error path tương ứng.

### Serialize-deserialize round-trip

Object O → bytes/text → O2. So sánh O và O2 theo semantics của type, đặc biệt Decimal, timestamp, null, collection và enum.

### Schema compatibility

Với schema version cũ và mới, kiểm tra compatibility checker trả kết quả đúng với các biến đổi đã mô tả. Có thể sinh schema mutation: add optional field, remove field, change type, tighten range, add enum value.

### Default behavior

Payload thiếu field có default phải tạo model theo default policy. Explicit null phải được xử lý riêng nếu schema cho phép null.

### Unknown fields

Property kiểm tra strict/permissive/preserve mode: strict từ chối; permissive bỏ qua; preserve giữ field qua parse-serialize theo contract.

### Reference resolution

Generator tạo schema graph có reference hợp lệ và invalid. Resolver phải resolve đúng version, phát hiện missing dependency và cycle theo policy.

### Constraint consistency

Generator có thể tạo constraint kết hợp, sau đó tìm payload thỏa hoặc vi phạm. Cần kiểm tra validator không chấp nhận dữ liệu ngoài domain.

## 15. Property cho rule engine

Rule DSL thường có condition, priority, agenda, action và conflict resolution.

### Evaluation determinism

Nếu rule set và input không đổi, decision result phải ổn định khi semantics yêu cầu deterministic execution.

### Rule order invariance

Nếu policy nói thứ tự declaration không ảnh hưởng, hoán vị rule declaration không được đổi kết quả. Nếu rule order là tie-breaker, property phải giữ thứ tự hoặc kiểm tra policy cụ thể.

### Non-matching rule

Thêm một rule có condition luôn false không được đổi decision result, trừ khi engine có observable audit/reporting semantics được định nghĩa.

### Duplicate rule

Thêm duplicate rule có thể:
- Không đổi outcome nhưng tăng activation count.
- Bị validator từ chối.
- Tạo nhiều action nếu semantics cho phép.

Property phải dựa trên rule engine contract, không mặc định duplicate là harmless.

### Priority

Nếu một rule có priority cao hơn và policy chỉ fire highest-priority rule, thêm rule thấp hơn không được đổi winner. Nếu engine fire all, cần kiểm tra agenda order.

### Conflict resolution

Sinh tập rule xung đột và kiểm tra winner theo priority, salience, specificity hoặc configured policy. Có thể so với một reference resolver đơn giản.

### Action trace

Record action calls và thứ tự. Property kiểm tra action không chạy khi rule condition false, action không chạy hai lần nếu idempotency policy yêu cầu, và failed action được phản ánh đúng.

## 16. Property cho workflow và state machine DSL

Workflow DSL thường cần kiểm thử cả một chuỗi hành động, không chỉ một input đơn lẻ.

### State invariants

Ví dụ:
- Completed process không có active task.
- Cancelled process không dispatch task mới.
- Một task chỉ có một owner active tại một thời điểm nếu contract yêu cầu.
- Join-all chỉ complete khi mọi branch bắt buộc đã kết thúc.
- Retry count không vượt max attempts.
- Timer đã cancel không được kích hoạt lại.

### Model-based testing

Xây một model state machine nhỏ độc lập với implementation. Generator tạo command sequence như start, signal, advance time, retry, cancel và resume. Sau mỗi command, so sánh model state với engine state.

### Sequence generation

Một sequence có thể là:
1. Start instance.
2. Complete first task.
3. Advance virtual clock.
4. Deliver callback.
5. Trigger retry.
6. Cancel instance.

Generator cần biết command nào hợp lệ ở state hiện tại hoặc chủ động sinh invalid command để kiểm tra rejection.

### Virtual time

Dùng clock giả lập thay vì sleep thật để test timeout, schedule và retry. Điều này làm test nhanh và reproducible.

### Parallel branch

Sinh nhiều branch hoàn tất theo các thứ tự khác nhau. Final state phải tuân theo join policy bất kể scheduling interleaving hợp lệ.

### Event duplication and ordering

Sinh duplicate, delayed hoặc reordered event nếu runtime hỗ trợ. Kiểm tra idempotency, sequence handling và final state.

### Compensation

Nếu một step fail sau side effect, property có thể xác nhận compensation chạy đúng thứ tự và state cuối phù hợp với saga contract.

## 17. Generator và shrinker cho workflow

Workflow AST có cấu trúc phức tạp hơn expression.

### Generate valid workflow graph

Bắt đầu từ graph acyclic hoặc flow model được hỗ trợ. Sinh node start, task, gateway, join và terminal; sau đó tạo edge thỏa reachability/dependency constraints.

### Ensure terminal path

Nếu DSL yêu cầu mọi path kết thúc, generator cần bảo đảm từ mỗi branch có đường tới terminal. Nếu mục tiêu là negative testing, tạo graph không có terminal path có chủ đích.

### Generate parallelism

Sinh parallel split và join tương thích. Join-all phải có đủ branch; race gateway có thể có policy cancellation.

### Generate loops

Nếu DSL hỗ trợ loop, giới hạn số iteration trong test và dùng virtual execution budget để tránh infinite execution.

### Shrink graph

Có thể bỏ branch không liên quan, rút subprocess, loại node trung gian, giảm loop count và đơn giản hóa condition. Shrinker phải giữ đường đi tái hiện lỗi.

### Preserve causal sequence

Với command sequence, khi shrink cần giữ những command tiền đề cần thiết. Nếu bỏ start hoặc task completion thì command cancel sau đó có thể không còn test cùng lỗi.

## 18. Property-based testing trong Java với jqwik

jqwik là một framework property-based testing phổ biến cho Java và tích hợp với JUnit Platform.

Ví dụ property:

~~~java
import net.jqwik.api.ForAll;
import net.jqwik.api.Property;

class ArithmeticProperties {

    @Property(tries = 500)
    void additionIsCommutative(
            @ForAll int left,
            @ForAll int right) {

        long first = (long) left + right;
        long second = (long) right + left;

        assertEquals(first, second);
    }
}
~~~

Ví dụ dùng long để tránh int overflow trong chính property. Nếu kiểm tra semantics integer của DSL, cần thay oracle theo overflow rule của language.

### Generator cơ bản

~~~java
import net.jqwik.api.Arbitraries;
import net.jqwik.api.Arbitrary;

Arbitrary<Integer> smallIntegers() {
    return Arbitraries.integers().between(-1000, 1000);
}
~~~

### Generator AST

~~~java
Arbitrary<Expr> literals() {
    return Arbitraries.integers()
        .between(-100, 100)
        .map(IntLiteral::new);
}

Arbitrary<Expr> expressions() {
    return Arbitraries.recursive(
        literals(),
        children -> Combinators.combine(
            children,
            Arbitraries.of(BinaryOperator.values()),
            children
        ).as(BinaryExpr::new),
        5
    );
}
~~~

Đây là ví dụ minh họa; cần kiểm soát depth/size, type compatibility và operator domain. Một phép chia có thể sinh divisor zero; điều đó phù hợp nếu đang kiểm tra error semantics nhưng cần loại khỏi property yêu cầu kết quả số hữu hạn.

### Property parse-format-parse

~~~java
@Property
void formattingPreservesAst(@ForAll("validExpressions") Expr expression) {
    String source = formatter.format(expression);
    Expr reparsed = parser.parseExpression(source);

    assertEquals(
        canonicalize(expression),
        canonicalize(reparsed)
    );
}
~~~

### Property interpreter/compiler equivalence

~~~java
@Property
void compiledAndInterpretedResultsMatch(
        @ForAll("wellTypedPrograms") Program program,
        @ForAll("validInputs") RuntimeInput input) {

    Object interpreted = interpreter.evaluate(program, input);
    Object compiled = compiler.compile(program).execute(input);

    assertEquals(normalize(interpreted), normalize(compiled));
}
~~~

### Reproducibility

Khi jqwik tìm counterexample, giữ seed/report và thêm trường hợp thu nhỏ vào regression corpus nếu đó là bug thật. Không nên xóa counterexample chỉ vì test pass trên máy developer sau một lần chạy.

## 19. Property-based testing với QuickTheories

QuickTheories là một lựa chọn khác trong Java, cung cấp generator và property assertion.

Ví dụ ý tưởng:

~~~java
qt()
    .forAll(integers().all())
    .check(value -> {
        String source = literalFormatter.format(value);
        int parsed = parser.parseInteger(source);
        return parsed == value;
    });
~~~

Cú pháp cụ thể phụ thuộc version/library. Khi chọn framework, cân nhắc:
- Khả năng tạo recursive Arbitrary.
- Shrinking tùy chỉnh.
- Seed và replay.
- Tích hợp JUnit/Gradle.
- Diagnostic khi fail.
- Hiệu năng generator.
- API để phân loại/distribute sample.

Không nên chọn framework chỉ vì cú pháp ngắn. Với DSL, generator và shrinker tùy chỉnh thường quan trọng hơn.

## 20. Tách generator khỏi production parser

Generator không nên gọi parser production để quyết định mọi thứ về input hợp lệ rồi dùng chính parser làm oracle. Nếu generator chỉ chấp nhận AST mà parser đã chấp nhận, có thể bỏ sót bug parser ở một production.

### AST constructor độc lập

Có thể tạo AST bằng constructor/model builder và kiểm tra invariants độc lập. Sau đó serializer tạo source.

### Grammar model

Nếu grammar được định nghĩa bằng metadata, generator có thể dùng grammar model nhưng vẫn cần test parser implementation độc lập.

### Reference implementation

Với một subset DSL, có thể xây parser/evaluator đơn giản, chậm nhưng rõ ràng để làm oracle. So sánh với production implementation.

### Golden corpus

Lưu AST hoặc semantic result chuẩn cho các chương trình đại diện. Property test có thể bổ sung random input, còn golden corpus giữ các contract quan trọng.

### Tránh shared bug

Nếu generator và parser dùng chung precedence table bị sai, cả hai có thể đồng ý với semantics sai. Một oracle độc lập hoặc metamorphic law giúp giảm nguy cơ này.

## 21. Distribution, coverage và classification

Số lần chạy lớn không đảm bảo generator khám phá tốt. Cần hiểu input được phân phối ra sao.

### Uniform distribution

Chọn đều giữa các giá trị có thể khiến boundary hiếm khi xuất hiện. Với số nguyên 32-bit, random uniform gần như không tạo đúng MIN/MAX.

### Boundary-biased generation

Chủ động tăng xác suất:
- Zero, one, minus one.
- Min/max integer.
- Empty và singleton collection.
- String rỗng, string dài, Unicode.
- Nesting gần giới hạn.
- Optional missing/null/present.
- Duplicate key và duplicate declaration.
- Date/time ở ranh giới.

### Classify và collect

Framework có thể phân loại sample theo production, depth, type, operator hoặc branch. Nếu 90% sample là literal, test chưa khám phá binary expression dù số tries cao.

### Coverage target

Có thể đặt kỳ vọng tối thiểu cho từng production hoặc category. Nếu generator không đạt, cần điều chỉnh distribution.

### Pairwise và combinatorial coverage

Một số bug xuất hiện khi hai yếu tố kết hợp, ví dụ nullable Decimal trong nested collection hoặc Unicode identifier trong imported module. Pairwise/combinatorial strategy có thể bổ sung random generation.

### Rare path

Một nhánh grammar rất hiếm có thể cần dedicated generator hoặc explicit example test. Không nên kỳ vọng random test tự tìm mọi path.

## 22. Precondition và assumptions

Property có thể chỉ đúng trên một miền con của input.

Ví dụ cộng có tính giao hoán nếu không có side effect và overflow semantics không phá quy luật. Nếu dùng int với wraparound, cộng vẫn giao hoán modulo 2^32; nhưng nếu DSL trap overflow, operation có thể fail tùy operand. Property phải mô tả đúng.

### Precondition

Precondition xác định input hợp lệ. Generator có thể tạo input hợp lệ ngay từ đầu, giảm việc discard sample.

### Assumption

Một số framework hỗ trợ assume/filter để bỏ sample không phù hợp. Nếu filter quá nhiều, test có thể mất thời gian và thực tế chạy ít case.

### Generate by construction

Tốt hơn việc tạo input tùy ý rồi discard phần lớn. Ví dụ sinh divisor khác zero bằng generator range loại zero thay vì filter sau.

### Negative property

Đối với input invalid, property phải phát biểu expected rejection/diagnostic. Không dùng assumption để loại toàn bộ input sai nếu mục tiêu đang kiểm tra validator.

### Undefined behavior

Nếu language specification không định nghĩa một trường hợp, property không nên khẳng định một output cụ thể. Có thể kiểm tra engine trả một category rõ hoặc từ chối input theo policy.

## 23. Determinism, randomness và flaky test

Property-based test dùng random nhưng cần tái hiện được.

### Seed logging

Khi fail, ghi seed, số lần thử, shrunk counterexample, generator version và DSL language version.

### Fixed seed trong regression

Có thể chạy seed cố định để tái hiện bug cũ, nhưng không nên chỉ dùng một seed cố định cho toàn bộ property suite. Điều đó làm giảm khả năng khám phá.

### Random seed trong CI

Có thể dùng seed mới mỗi build hoặc một lịch seed đã định. Khi fail, CI phải xuất đủ thông tin để replay.

### Nondeterministic runtime

Nếu DSL có concurrency, timer hoặc random function, test cần inject deterministic clock/random source và control scheduler. Nếu không, failure có thể không tái hiện.

### Stable ordering

Không so sánh collection theo thứ tự nếu contract không bảo đảm order. Chuẩn hóa result hoặc so sánh theo key.

### Environment dependencies

Locale, timezone, default charset, file system order và system clock có thể làm property flaky. Inject config/environment rõ ràng.

## 24. Stateful property và model-based testing

Một property đơn lẻ thường kiểm tra một operation. Với engine có state, cần kiểm tra sequence operation.

### Model state

Tạo model đơn giản biểu diễn trạng thái kỳ vọng, ví dụ process status, active tasks, retry count và completed branches.

### Commands

Command là thao tác như start, complete task, signal, advance time, retry, pause, resume hoặc cancel.

### Preconditions

Mỗi command có điều kiện hợp lệ. Ví dụ complete task chỉ hợp lệ khi task đang active; resume chỉ hợp lệ khi instance suspended.

### Postconditions

Sau command, so sánh model với implementation. Nếu command invalid, engine phải từ chối theo contract và không làm thay đổi state trái phép.

### Sequence shrinking

Khi sequence fail, shrinker bỏ command không liên quan và rút input của command để tạo chuỗi ngắn hơn.

### Persistence/restart

Model-based test có thể chèn restart giữa sequence. Sau recovery, state của engine phải tương đương model và không lặp side effect.

### Parallel schedules

Có thể sinh interleaving của event/worker completion. Cần dùng deterministic scheduler để kiểm soát thứ tự và replay failure.

## 25. Fuzzing và property-based testing

Hai kỹ thuật có quan hệ gần nhưng không giống nhau.

| Kỹ thuật | Cách tạo input | Mục tiêu chính |
|---|---|---|
| Property-based testing | Generator có cấu trúc và property rõ. | Kiểm tra invariant/semantics. |
| Grammar-based fuzzing | Generator theo grammar. | Khám phá parser/runtime bằng nhiều source. |
| Mutation fuzzing | Biến đổi corpus seed. | Tìm crash và edge case. |
| Coverage-guided fuzzing | Chọn input dựa trên code coverage. | Mở rộng đường thực thi. |
| Differential fuzzing | So sánh nhiều implementation. | Tìm bất đồng semantics. |

### Grammar-based fuzzing

Tạo source hợp lệ theo grammar, sau đó mutate delimiter, keyword, literal hoặc nesting để kiểm tra parser và recovery.

### Mutation fuzzing

Lấy source đã biết rồi xóa, lặp, thay token, chèn Unicode hoặc đổi độ dài literal.

### Coverage guidance

Coverage-guided fuzzer có thể tìm input đi sâu vào parser branch chưa được khám phá. Cần giới hạn resource và lọc crash/hang.

### Property oracle

Fuzzing cần oracle để biết output có sai hay không. Property như parser không crash, interpreter/compiler tương đương hoặc round-trip semantics có thể làm oracle.

### Regression corpus

Mọi crash hoặc semantic mismatch được phát hiện nên được lưu lại, giảm thành test case nhỏ và chạy trong regression suite.

## 26. Kiểm thử parser với source arbitrary

Không phải mọi source đều hợp lệ. Parser phải xử lý input tùy ý trong giới hạn tài nguyên.

Các property hữu ích:
- Parser không crash với bất kỳ byte/text input nào trong giới hạn.
- Parse luôn kết thúc trong budget xác định.
- Mọi diagnostic span nằm trong source.
- Error recovery luôn tiến triển hoặc dừng.
- Parser không tạo node có child reference null trái contract.
- Reparse cùng source/version cho kết quả ổn định.
- Input quá lớn/nesting quá sâu bị từ chối có kiểm soát.

### Invalid UTF-8

Nếu API nhận bytes, generator có thể tạo byte sequence không hợp lệ. Decoder phải trả lỗi phù hợp, không silently replace nếu contract yêu cầu strict decoding.

### Unterminated literal/comment

Sinh string chưa đóng, block comment chưa đóng và escape dang dở. Kiểm tra diagnostic location và recovery.

### Token boundary

Sinh operator bị cắt, identifier dài, number exponent không hoàn chỉnh và Unicode surrogate lỗi.

### Resource exhaustion

Sinh nesting sâu, token cực dài và grammar pattern gây backtracking. Xác nhận parser áp dụng budget.

### Crash-only property chưa đủ

Parser không crash nhưng có thể tạo AST sai. Cần kết hợp structural invariant, differential parsing và round-trip property.

## 27. Property cho name resolution và type checking

Resolver/type checker thường có state scope và dependency.

### Scope visibility

Variable khai báo trong inner scope không được truy cập ngoài scope nếu language không hỗ trợ escape.

### Shadowing

Khai báo variable cùng tên trong inner scope phải tuân theo shadowing rule. Sau khi rời scope, binding outer phải được khôi phục.

### Alpha-renaming

Đổi tên một variable và tất cả reference tương ứng sang tên mới không xung đột phải giữ semantics. Đây là metamorphic property hữu ích cho symbol binding.

### Reference resolution

Mọi resolved reference phải trỏ đến declaration hợp lệ. Missing reference phải tạo diagnostic, không trả symbol null rồi crash ở phase sau.

### Type soundness relation

Nếu type checker chấp nhận expression có type T, evaluator phải trả value thuộc domain T theo semantics. Property có thể sinh well-typed expression rồi evaluate.

### Generic substitution

Sinh generic type và substitution hợp lệ, kiểm tra type inference/substitution không đổi kết quả khi áp dụng tương đương.

### Import graph

Sinh module dependency graph có version và cycle. Resolver phải resolve đúng dependency và phát hiện cycle theo policy.

## 28. Property cho optimizer và code generator

Code generation là một nơi khác để dùng differential/property testing.

### Generated code compiles

Với mọi schema/program thuộc supported subset, generated Java code phải compile thành công.

### Generated behavior equivalence

Generated adapter/validator phải có behavior tương đương reference runtime validator.

### Naming stability

Cùng schema identity/version phải sinh tên type/field ổn định theo naming policy.

### Round-trip schema generation

Schema DSL → JSON Schema/OpenAPI → import lại DSL có thể giữ semantics của supported subset. Không đòi round-trip tuyệt đối nếu target format không biểu diễn được metadata nguồn; cần định nghĩa loss boundary.

### Optimization equivalence

Code generator có thể áp dụng constant folding, dead-code elimination hoặc inline. Property so sánh output với reference interpreter.

### Deterministic artifact

Cùng input và tool version phải tạo artifact byte-for-byte ổn định nếu build reproducibility là requirement. Nếu metadata như timestamp được chèn, cần loại bỏ hoặc chuẩn hóa.

## 29. Kiểm soát side effect trong property tests

Một property chạy hàng trăm lần có thể tạo file, gửi message hoặc cập nhật database. Nếu không cô lập, test sẽ chậm và không tái hiện.

### Pure function first

Tách parsing/evaluation thuần khỏi adapter I/O khi có thể. Property trên pure core nhanh và dễ shrink.

### Fake service

Inject fake clock, repository, message publisher và external client. Ghi trace side effect để so sánh.

### Transaction rollback

Nếu dùng database test, mỗi sample có thể chạy trong transaction được rollback, nhưng cần lưu ý asynchronous worker có thể chạy ngoài transaction.

### Unique test namespace

Mỗi sample cần correlation/idempotency key riêng để tránh trùng dữ liệu.

### Cleanup

Generator/test harness cần cleanup resource dù property fail hoặc shrink. Không để test case trước ảnh hưởng case sau.

### Side-effect equivalence

So sánh trace các operation, không chỉ final result. Hai implementation có thể trả cùng output nhưng phát message khác số lần.

## 30. Tổ chức property suite trong CI

Property test có thể tốn thời gian hơn unit test cố định. Nên chia profile.

### Fast suite

Chạy số tries vừa phải, generator nhỏ, seed ổn định và subset property quan trọng trong mỗi pull request.

### Extended suite

Chạy nhiều tries, large input, deep nesting, fuzz corpus và concurrency trong nightly hoặc scheduled pipeline.

### Regression suite

Chứa mọi counterexample đã từng tìm được, test cố định và minimized source. Nên chạy thường xuyên vì chi phí thường thấp.

### Performance suite

Đo thời gian generator/property riêng với parser runtime. Không dùng benchmark timing như assertion cứng trong unit test vì môi trường CI biến động.

### Failure artifact

CI nên lưu:
- Seed.
- Shrunk counterexample.
- Source DSL hoặc AST serialization.
- Generator parameters/version.
- DSL language version.
- Engine/compiler version.
- Relevant runtime configuration.
- Trace/log đã redacted.

### Flaky triage

Nếu property chỉ fail khi chạy song song, xem shared state, random seed, static cache, test resource và scheduler. Không giải quyết bằng cách retry test vô hạn vì có thể che race condition.

## 31. Đánh giá chất lượng generator

Một generator tốt không chỉ tạo nhiều input; nó phải tạo input có giá trị kiểm thử.

### Validity rate

Với generator valid, phần lớn sample phải hợp lệ theo mục tiêu. Nếu 99% sample bị type checker từ chối, generator chưa khám phá semantics.

### Structural diversity

Theo dõi depth, node count, production distribution, operator frequency, type combination và scope size.

### Boundary frequency

Đảm bảo min/max, empty, singleton, null, duplicate, deep nesting và long literal xuất hiện đủ thường xuyên.

### Shrink quality

Counterexample sau shrink có dễ hiểu không? Có giữ nguyên bug không? Có bị shrink quá chậm không?

### Mutation sensitivity

Một property tốt cần fail khi cố ý chèn một lỗi đại diện vào implementation. Mutation testing có thể đánh giá property có khả năng phát hiện bug hay không.

### Independent oracle

Đánh giá generator/oracle có phụ thuộc cùng implementation với code đang test hay không.

### Seed diversity

Chạy nhiều seed nhưng lưu seed fail. Có thể luân phiên seed theo commit/build ID, đồng thời giữ một tập seed cố định cho regression.

## 32. Ví dụ tổng hợp: test parser và evaluator của DSL

Giả sử DSL hỗ trợ integer literal, unary minus, cộng, trừ, nhân và ngoặc. Ta muốn xác nhận parser và evaluator nhất quán.

Mô hình AST:

~~~java
sealed interface Expr permits IntLiteral, UnaryExpr, BinaryExpr {}

record IntLiteral(long value) implements Expr {}

record UnaryExpr(char operator, Expr operand) implements Expr {}

record BinaryExpr(char operator, Expr left, Expr right) implements Expr {}
~~~

Generator có thể tạo AST với depth giới hạn, serializer thêm ngoặc theo precedence, rồi parser đọc source.

~~~java
@Property(tries = 500)
void parseFormatPreservesExpression(
        @ForAll("expressions") Expr expression) {

    String source = formatter.format(expression);
    Expr parsed = parser.parse(source);

    assertEquals(
        canonicalize(expression),
        canonicalize(parsed)
    );
}
~~~

Một property khác so sánh evaluator với reference evaluator:

~~~java
@Property(tries = 500)
void optimizedEvaluatorMatchesReference(
        @ForAll("safeExpressions") Expr expression) {

    long expected = referenceEvaluator.evaluate(expression);
    long actual = optimizedEvaluator.evaluate(expression);

    assertEquals(expected, actual);
}
~~~

Generator safeExpressions cần tránh phép chia cho zero nếu grammar có division, và xử lý overflow theo semantics đã định nghĩa. Nếu muốn kiểm tra lỗi divide-by-zero, tạo property riêng cho exception/error code.

### Vì sao cần hai property?

Property round-trip kiểm tra parser/formatter bảo toàn AST. Property differential evaluator kiểm tra runtime semantics. Một property có thể pass trong khi property kia fail; tách chúng giúp định vị lỗi.

### Thêm metamorphic relation

Có thể chèn whitespace/comment hợp lệ vào source rồi parse lại và so canonical AST. Có thể thêm ngoặc quanh expression rồi xác nhận evaluation result không đổi.

## 33. Những lỗi thường gặp khi viết property-based test

**Property quá yếu.** Chỉ kiểm tra parser không crash sẽ bỏ sót AST sai. Bổ sung invariant, differential test hoặc round-trip.

**Generator chỉ sinh input đơn giản.** Test không chạm nested expression, import, enum hoặc boundary. Theo dõi distribution và thêm weighted production.

**Generator tạo quá nhiều input invalid.** Property semantics không chạy được vì sample bị reject sớm. Sinh valid input by construction.

**Không có shrinker phù hợp.** Failure source hàng nghìn dòng khó debug. Shrink AST, graph hoặc command sequence theo cấu trúc.

**Assumption lọc quá nhiều sample.** Test báo ít lần thử hữu ích và chạy lâu. Thiết kế generator đúng miền thay vì filter liên tục.

**Dùng cùng implementation làm oracle.** Hai đường code cùng chia sẻ bug. Xây reference model độc lập hoặc dùng metamorphic law.

**Bỏ qua overflow và undefined behavior.** Property toán học không khớp semantics của DSL. Xác định miền và arithmetic policy rõ.

**So sánh kết quả không chuẩn hóa.** Collection order, Decimal scale hoặc diagnostic message khác nhau gây false failure. Chuẩn hóa theo contract, không xóa khác biệt có ý nghĩa.

**Random test không replay được.** Thiếu seed hoặc counterexample. Lưu đầy đủ reproduction metadata.

**Chạy quá nhiều tries mà không có coverage.** Số lượng sample lớn không bảo đảm khám phá production hiếm. Classify và đo distribution.

**Property có side effect không cô lập.** Sample này ảnh hưởng sample khác. Dùng fake service, isolated namespace và cleanup.

**Không giữ regression counterexample.** Bug cũ có thể tái xuất hiện sau khi generator đổi. Lưu minimized input thành regression fixture.

**Chỉ chạy property test nightly.** Bug quan trọng có thể lọt qua PR. Giữ fast property suite trong CI thường xuyên.

## 34. Quy trình áp dụng property-based testing cho DSL

Một quy trình triển khai có thể gồm:

1. **Chọn contract:** xác định parser, formatter, evaluator, schema validator, rule engine hay workflow runtime cần kiểm tra.
2. **Viết property:** mô tả invariant, algebraic law, metamorphic relation hoặc equivalence.
3. **Xác định miền:** phân biệt valid, invalid, undefined và unsupported input.
4. **Thiết kế model:** AST, schema, workflow graph, runtime state hoặc command model.
5. **Xây generator:** grammar-aware, type-aware, scope-aware và boundary-biased.
6. **Xây shrinker:** thu nhỏ tree, source, graph và command sequence mà vẫn giữ điều kiện test.
7. **Chọn oracle:** expected model, reference interpreter, canonical form hoặc differential implementation.
8. **Đặt distribution:** production coverage, depth, size, edge values và rare branch.
9. **Thiết lập reproducibility:** seed, generator version, DSL version và counterexample artifact.
10. **Tích hợp CI:** fast suite, regression suite và extended suite.
11. **Phân tích failure:** replay, shrink, xác định root cause và thêm regression test.
12. **Theo dõi quality:** mutation sensitivity, coverage distribution, shrink time và flaky rate.

## 35. Checklist cho một property test đáng tin cậy

Trước khi đưa property vào CI, cần xác nhận:

- Property phát biểu một invariant có ý nghĩa theo language specification không?
- Precondition và miền input có được xác định không?
- Generator tạo đúng loại input mà test cần không?
- Generator có kiểm soát depth, size và resource không?
- Có boundary values và rare grammar production không?
- Sample có được phân loại để biết distribution không?
- Shrinker có giữ nguyên điều kiện cần thiết để tái hiện lỗi không?
- Oracle có độc lập với implementation đang kiểm thử không?
- Kết quả được chuẩn hóa đúng semantics không?
- Random seed và counterexample có thể replay không?
- Test có cô lập side effect và shared state không?
- Có test invalid input và error recovery khi phù hợp không?
- Có regression corpus cho lỗi đã phát hiện không?
- CI có fast suite và extended suite phù hợp không?
- Có lưu generator version, DSL version và engine version khi fail không?
- Có theo dõi flaky rate và mutation sensitivity không?

## 36. Kết quả cần có sau khi thiết kế property-based testing

Một chiến lược property-based testing hoàn chỉnh cho DSL thường cung cấp:

- **Property catalog:** invariant, algebraic law, metamorphic relation và differential equivalence.
- **Input model:** character, token, AST, source, schema, workflow graph, runtime data và command sequence.
- **Generator library:** grammar-aware, type-aware, scope-aware, boundary-biased và invalid-input generator.
- **Shrinker library:** AST, source, schema, graph và stateful sequence shrinker.
- **Oracle strategy:** reference implementation, canonical form, model state và semantic comparison.
- **Parser properties:** token span, deterministic parse, round-trip, whitespace invariance và error recovery.
- **Runtime properties:** interpreter/compiler equivalence, optimizer preservation, evaluation order và state invariants.
- **Schema properties:** generated payload validation, serialization round-trip, default/null behavior và compatibility.
- **Rule/workflow properties:** conflict resolution, branch/join, retry, cancellation, timeout và compensation.
- **Reproducibility:** seed, counterexample, source version, generator version và runtime configuration.
- **CI profiles:** fast, regression, extended, fuzzing và performance runs.
- **Quality metrics:** production coverage, distribution, shrink quality, mutation sensitivity và flaky rate.

Property-based testing giúp mở rộng phạm vi kiểm thử DSL bằng cách kiểm tra các quy luật trên nhiều input được sinh có chủ đích. Giá trị của phương pháp không nằm ở số lần chạy ngẫu nhiên đơn thuần, mà ở sự kết hợp giữa property chính xác, generator hiểu grammar và semantics, shrinker tạo phản ví dụ nhỏ, cùng oracle độc lập và khả năng replay. Với DSL, có thể áp dụng nó cho lexer/parser, formatter, type checker, interpreter/compiler, optimizer, schema serializer, rule engine và workflow state machine. Khi counterexample được lưu thành regression test và generator được theo dõi distribution, property-based testing trở thành một nguồn phát hiện lỗi liên tục, bổ sung cho các ví dụ nghiệp vụ và kiểm thử tích hợp.


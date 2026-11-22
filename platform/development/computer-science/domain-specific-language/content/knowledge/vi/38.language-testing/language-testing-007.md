# Mutation test

## 1. Mutation testing trong kiểm thử DSL

Một DSL thường có nhiều tầng xử lý: lexer, parser, name resolution, type checking, semantic analysis, lowering, code generation và runtime. Test suite có thể chạy rất nhiều test case nhưng vẫn bỏ sót lỗi ở một nhánh điều kiện, một toán tử so sánh hoặc một quy tắc xử lý biên. Mutation testing (kiểm thử đột biến) là kỹ thuật đánh giá khả năng phát hiện lỗi của test suite bằng cách cố ý tạo các phiên bản chương trình có thay đổi nhỏ, sau đó kiểm tra xem test có phát hiện những thay đổi đó hay không.

Một thay đổi được tạo ra gọi là mutation; phiên bản chương trình đã bị thay đổi gọi là mutant. Nếu test suite thất bại khi chạy mutant, mutant được xem là đã bị kill. Nếu toàn bộ test vẫn pass, mutant sống sót (survived) và có thể cho thấy test chưa kiểm tra hành vi bị thay đổi. Tuy nhiên, mutant sống sót không luôn có nghĩa test yếu: thay đổi có thể không làm thay đổi hành vi quan sát được hoặc có thể tạo ra một chương trình tương đương.

Ví dụ, một DSL có điều kiện:

~~~text
rule "free-shipping" when order.total >= 500
then shipping.cost = 0
~~~

Mutation operator có thể thay toán tử lớn hơn hoặc bằng thành lớn hơn:

~~~text
rule "free-shipping" when order.total > 500
then shipping.cost = 0
~~~

Nếu test chỉ kiểm tra total = 700, cả hai phiên bản đều cho cùng kết quả. Test đó không phát hiện thay đổi. Nếu test có trường hợp total = 500 và kỳ vọng miễn phí vận chuyển, mutant sẽ bị kill.

Mutation testing không chứng minh chương trình hoàn toàn đúng. Nó cung cấp bằng chứng về khả năng phân biệt hành vi đúng và hành vi sai của test suite trong phạm vi mutation operators được áp dụng.

## 2. Vì sao DSL cần mutation testing

Test thông thường thường xác nhận một số input cụ thể cho kết quả dự kiến. Mutation testing đặt câu hỏi ngược lại: nếu một lỗi phổ biến xuất hiện trong implementation, test có phát hiện được không?

Với DSL, câu hỏi này đặc biệt hữu ích vì nhiều lỗi nằm trong semantics:

- Lexer nhận diện sai keyword hoặc literal.
- Parser bỏ qua một nhánh grammar.
- Precedence hoặc associativity của toán tử bị thay đổi.
- Name resolver chấp nhận identifier chưa khai báo.
- Type checker bỏ qua một điều kiện tương thích kiểu.
- Semantic analyzer bỏ qua invariant.
- Code generator phát sinh instruction sai.
- Runtime chọn nhánh hoặc cập nhật state không đúng.
- Error handling biến lỗi thành kết quả mặc định.
- Optimizer thay đổi hành vi có thể quan sát được.

Một test suite chỉ kiểm tra happy path có thể pass ngay cả khi nhiều lỗi như vậy tồn tại. Mutation testing giúp tìm những vùng test chưa đủ nhạy.

### 2.1. Đánh giá test, không chỉ đánh giá source

Code coverage cho biết dòng hoặc nhánh nào đã được thực thi. Nó không cho biết assertion có phát hiện kết quả sai hay không. Một test có thể chạy qua dòng code nhưng không kiểm tra output quan trọng.

Mutation testing thêm một câu hỏi: nếu dòng đó thay đổi theo một kiểu lỗi cụ thể, test có thất bại không?

### 2.2. Ưu tiên vùng có rủi ro cao

Có thể áp dụng mutation testing cho các phần có tác động lớn như type checking, authorization rule, transaction condition, expression evaluation và code generation.

### 2.3. Hỗ trợ thay đổi ngôn ngữ

Khi DSL thêm operator, type hoặc syntax mới, mutation operators mới có thể giúp đánh giá test suite có bao phủ semantics mới hay chưa.

### 2.4. Không thay thế các kỹ thuật khác

Mutation testing bổ sung cho unit test, integration test, property-based test, fuzzing, golden test và contract test. Mỗi kỹ thuật tìm một lớp lỗi khác nhau.

## 3. Quy trình mutation testing

Một vòng mutation testing thường gồm các bước:

1. Chọn source code hoặc module cần phân tích.
2. Chạy test suite gốc để xác nhận baseline pass.
3. Sinh các mutant theo mutation operators.
4. Biên dịch hoặc chuẩn bị từng mutant.
5. Chạy test suite trên mutant.
6. Phân loại mutant bị kill, survived, equivalent hoặc không chạy được.
7. Phân tích nguyên nhân và cải thiện test khi cần.
8. Tính mutation score theo quy ước đã chọn.

~~~text
Original Program
      |
      v
Baseline Tests
      |
      v
Generate Mutants
      |
      v
Run Tests per Mutant
      |
      +------> Killed
      |
      +------> Survived
      |
      +------> Equivalent / Invalid
      |
      v
Analyze Results
      |
      v
Improve Tests or Mutation Model
~~~

Baseline quan trọng: nếu test gốc đã fail, không thể diễn giải kết quả mutation một cách đáng tin cậy. Cần xử lý lỗi baseline trước khi chạy chiến dịch mutation.

## 4. Các trạng thái của mutant

Kết quả mutation cần được phân loại cẩn thận.

### 4.1. Killed

Mutant bị kill khi ít nhất một test thất bại do hành vi bị thay đổi. Test có thể fail ở assertion, exception expectation, snapshot hoặc một điều kiện kiểm tra khác.

### 4.2. Survived

Mutant sống sót khi test suite chạy xong mà không phát hiện khác biệt. Đây là tín hiệu để xem lại test, nhưng chưa phải kết luận tự động rằng mutant là lỗi thật.

### 4.3. Equivalent mutant

Equivalent mutant là phiên bản thay đổi source nhưng hành vi quan sát được tương đương với chương trình gốc trong miền input và semantics đang xét. Test không thể kill mutant tương đương bằng một input hợp lệ.

### 4.4. Invalid mutant

Mutant có thể không biên dịch hoặc vi phạm cấu trúc chương trình. Một số công cụ loại mutant này khỏi score; một số báo riêng. Không nên coi compile error là test đã phát hiện lỗi runtime.

### 4.5. Timed out

Mutant có thể khiến test chạy quá lâu hoặc rơi vào vòng lặp. Timeout có thể được tính là kill nếu harness xác định đây là khác biệt hành vi, nhưng cần tránh timeout quá thấp gây false positive.

### 4.6. No coverage

Một số công cụ đánh dấu mutant không nằm trên đường thực thi của bất kỳ test nào. Đây thường là một dạng survived hoặc trạng thái riêng, tùy công cụ.

### 4.7. Runtime error

Mutant có thể gây exception không mong đợi. Nếu test thất bại vì exception đó, mutant thường được kill. Cần giữ error report để biết test nào phát hiện.

## 5. Mutation score

Mutation score là tỷ lệ mutant có thể kill trong tập mutant được dùng để tính.

Một công thức phổ biến:

\[
Mutation\ Score =
\frac{Killed}{Valid\ Mutants - Equivalent\ Mutants}
\times 100\%
\]

Ví dụ có 100 mutant hợp lệ, 8 mutant được xác định là equivalent và 72 mutant bị kill:

\[
\frac{72}{100-8}\times 100\% \approx 78.26\%
\]

### 5.1. Quy ước mẫu số

Các công cụ có thể xử lý invalid, timeout hoặc no-coverage khác nhau. Khi báo score, cần ghi rõ trạng thái nào được đưa vào mẫu số.

### 5.2. Score không phải xác suất correctness

Mutation score 90% không có nghĩa chương trình đúng 90%. Score chỉ mô tả kết quả trên tập mutation operators và mutant cụ thể.

### 5.3. Score cao nhưng test vẫn thiếu

Nếu mutation operators không mô phỏng loại lỗi quan trọng của DSL, score cao vẫn có thể bỏ sót lỗi semantics.

### 5.4. Score thấp không luôn có nghĩa chất lượng kém

Một tập mutation có nhiều equivalent mutant hoặc operator không phù hợp có thể làm score thấp và khó diễn giải.

### 5.5. So sánh score

Chỉ nên so sánh hai module hoặc hai lần chạy khi mutation operators, tool version, exclusions, baseline và test scope tương đương.

## 6. Mutation operators phổ biến

Mutation operator là quy tắc tạo thay đổi có chủ đích. Operator nên đại diện cho lỗi lập trình có khả năng xảy ra.

### 6.1. Arithmetic operator replacement

Thay phép cộng bằng trừ, nhân bằng chia hoặc một phép toán tương tự.

~~~java
int total = price + tax;
~~~

Mutant:

~~~java
int total = price - tax;
~~~

### 6.2. Relational operator replacement

Thay toán tử nhỏ hơn thành nhỏ hơn hoặc bằng, lớn hơn thành lớn hơn hoặc bằng, hoặc bằng thành khác. Đây là operator rất hữu ích cho boundary condition.

### 6.3. Conditional operator replacement

Thay AND bằng OR hoặc ngược lại. Ví dụ điều kiện yêu cầu cả authenticated và authorized có thể bị mutation thành chỉ cần một trong hai.

### 6.4. Boolean literal replacement

Thay true thành false hoặc false thành true.

### 6.5. Return value replacement

Thay kết quả trả về bằng null, zero, empty value hoặc một boolean cố định. Operator này kiểm tra assertion về output.

### 6.6. Statement deletion

Xóa một statement hoặc bỏ lời gọi quan trọng. Có thể phát hiện test thiếu kiểm tra side effect.

### 6.7. Negation

Đảo điều kiện hoặc biểu thức boolean. Ví dụ một rule chỉ được chạy khi account active có thể bị đảo thành chạy khi account không active.

### 6.8. Constant replacement

Thay một hằng số bằng giá trị khác hoặc zero. Ví dụ limit 100 thành 99.

### 6.9. Method call replacement

Thay một method call bằng method khác có kiểu tương thích hoặc bỏ lời gọi. Có thể phát hiện test không kiểm tra interaction quan trọng.

### 6.10. Exception mutation

Thay loại exception, bỏ throw hoặc chuyển exception thành giá trị mặc định.

## 7. Mutation testing cho lexer

Lexer chuyển source text thành token. Một mutation trong lexer có thể làm sai loại token, vị trí hoặc nội dung literal.

### 7.1. Keyword mutation

Thay keyword thành identifier hoặc ngược lại. Test cần xác nhận reserved word được nhận diện đúng và identifier gần giống keyword vẫn hợp lệ theo grammar.

### 7.2. Operator boundary mutation

Đổi cách nhận diện >= thành > rồi = hoặc đổi != thành ! và =. Test cần kiểm tra tokenization của operator nhiều ký tự.

### 7.3. String escape mutation

Bỏ xử lý escape sequence hoặc đổi cách xử lý dấu quote. Test cần bao phủ newline, quote, backslash và escape không hợp lệ.

### 7.4. Number literal mutation

Thay quy tắc nhận diện decimal, exponent, dấu âm hoặc separator. Test nên có giá trị biên và literal malformed.

### 7.5. Comment mutation

Thay quy tắc kết thúc comment hoặc bỏ qua comment. Test cần xác nhận comment không làm token sau bị mất hoặc nhập nhầm.

### 7.6. Source position mutation

Thay offset hoặc line/column calculation. Test nên kiểm tra diagnostic location, nhất là với Unicode, tab và newline nhiều kiểu.

### 7.7. Whitespace mutation

Thay tập ký tự whitespace được chấp nhận. Test cần xác nhận newline, tab và whitespace Unicode theo grammar.

## 8. Mutation testing cho parser

Parser xác định cấu trúc syntax từ token stream. Một mutation có thể thay đổi grammar hoặc cách xây AST.

### 8.1. Grammar alternative deletion

Bỏ một alternative trong grammar, ví dụ không còn parse được else branch. Test cần có case cho từng alternative.

### 8.2. Optional clause mutation

Bỏ qua clause tùy chọn như timeout hoặc retry policy. Test cần xác nhận clause được parse và xuất hiện đúng trong AST.

### 8.3. Precedence mutation

Thay precedence của and, or, equality hoặc arithmetic. Test nên kiểm tra expression có nhiều operator:

~~~text
a or b and c
~~~

### 8.4. Associativity mutation

Đổi left-associative thành right-associative hoặc ngược lại. Điều này quan trọng với phép trừ, phép chia và một số operator DSL.

### 8.5. Parenthesis mutation

Bỏ qua grouping hoặc chấp nhận dấu ngoặc không cân bằng. Test cần kiểm tra nested expression và syntax error.

### 8.6. AST child mutation

Đổi thứ tự child, bỏ node hoặc gắn node vào parent sai. AST structural assertion hoặc test downstream có thể phát hiện.

### 8.7. Error recovery mutation

Bỏ qua synchronization point hoặc tiếp tục parse sai vị trí. Test cần kiểm tra nhiều diagnostic sau một syntax error và xác nhận parser không làm hỏng các declaration tiếp theo.

## 9. Mutation testing cho name resolution và scope

Name resolution liên kết identifier trong expression với declaration tương ứng.

### 9.1. Scope lookup mutation

Thay lookup hiện tại bằng lookup ở parent hoặc bỏ qua parent scope. Test cần có biến shadowing và nested block.

### 9.2. Declaration visibility

Thay thời điểm declaration có hiệu lực. Test cần xác định forward reference có được phép hay không.

### 9.3. Shadowing mutation

Bỏ kiểm tra duplicate hoặc shadowing. Test cần xác nhận chính sách cho phép hoặc cấm shadowing.

### 9.4. Unknown identifier

Bỏ lỗi khi identifier không tồn tại. Test phải xác nhận diagnostic và vị trí source.

### 9.5. Symbol identity

Thay symbol reference bằng symbol cùng tên ở scope khác. Test cần kiểm tra binding identity, không chỉ text của identifier.

### 9.6. Import resolution

Bỏ kiểm tra module import hoặc thay precedence giữa local declaration và imported symbol. Test nên bao phủ alias, circular import và missing module.

## 10. Mutation testing cho type checker

Type checker kiểm tra phép toán và giá trị có tương thích kiểu hay không. Một lỗi nhỏ có thể khiến chương trình sai được chấp nhận.

### 10.1. Type compatibility mutation

Bỏ điều kiện kiểm tra type equality hoặc assignability. Test cần có cặp kiểu tương thích và không tương thích.

### 10.2. Numeric promotion

Thay quy tắc promotion giữa integer, decimal và floating point. Test cần xác nhận kết quả và kiểu suy luận.

### 10.3. Nullability

Bỏ kiểm tra nullable hoặc non-null. Test cần bao phủ dereference null và flow analysis nếu DSL hỗ trợ.

### 10.4. Generic substitution

Thay type argument hoặc bỏ substitution. Test nên dùng generic function, nested generic và type bound.

### 10.5. Function arity

Bỏ kiểm tra số lượng argument hoặc parameter type. Test cần kiểm tra thiếu, thừa và sai kiểu.

### 10.6. Return type

Bỏ kiểm tra return expression với declared return type. Test cần có function trả sai kiểu và function có nhiều return branch.

### 10.7. Exhaustiveness

Bỏ kiểm tra pattern match hoặc enum case còn thiếu. Test cần xác nhận compiler báo lỗi khi chưa xử lý mọi variant nếu semantics yêu cầu exhaustive.

## 11. Mutation testing cho semantic analysis

Semantic analysis kiểm tra những quy tắc vượt ra ngoài cú pháp và kiểu.

### 11.1. Required field

Bỏ kiểm tra field bắt buộc hoặc default. Test cần có object thiếu field.

### 11.2. Duplicate declaration

Bỏ kiểm tra tên declaration trùng trong cùng scope.

### 11.3. Constraint mutation

Thay range, length hoặc pattern constraint. Test cần bao phủ giá trị ngay dưới, đúng tại và ngay trên boundary.

### 11.4. State transition mutation

Bỏ điều kiện chuyển trạng thái hoặc thay trạng thái đích. Test cần kiểm tra transition hợp lệ và bất hợp lệ.

### 11.5. Authorization rule

Bỏ một điều kiện quyền hoặc thay AND thành OR. Test phải xác nhận request thiếu một quyền bị từ chối.

### 11.6. Dependency validation

Bỏ kiểm tra dependency hoặc cycle. Test cần có graph hợp lệ và graph có cycle.

### 11.7. Invariant mutation

Bỏ một invariant của domain object. Test cần xác nhận trạng thái vi phạm bị từ chối ở đúng phase.

## 12. Mutation testing cho runtime evaluator

Runtime evaluator thực thi expression và statement của DSL.

### 12.1. Arithmetic evaluation

Thay phép cộng thành trừ hoặc đổi thứ tự operand. Test nên dùng giá trị làm kết quả khác nhau rõ ràng.

### 12.2. Short-circuit behavior

Bỏ short-circuit của AND/OR hoặc đảo thứ tự đánh giá. Test cần kiểm tra expression có operand gây side effect hoặc lỗi.

### 12.3. Branch selection

Đảo điều kiện if hoặc chọn sai branch. Test cần kiểm tra cả nhánh true và false.

### 12.4. Loop boundary

Thay điều kiện dừng hoặc số lần lặp. Test cần kiểm tra zero iteration, một iteration và nhiều iteration.

### 12.5. Variable assignment

Bỏ assignment hoặc ghi vào scope sai. Test cần xác nhận giá trị sau block và shadowing.

### 12.6. Exception propagation

Bỏ propagate exception hoặc biến lỗi thành null/default. Test cần xác nhận lỗi đến đúng handler.

### 12.7. State mutation

Đổi thứ tự cập nhật state hoặc bỏ một field. Test cần kiểm tra toàn bộ state có thể quan sát được.

## 13. Mutation testing cho code generation

Code generator chuyển IR thành bytecode, Java source, SQL, JSON hoặc một output khác.

### 13.1. Instruction mutation

Thay instruction hoặc opcode được sinh. Test có thể compile và thực thi generated artifact để phát hiện.

### 13.2. Operand mutation

Đổi operand, constant hoặc variable slot. Test cần xác nhận output value.

### 13.3. Branch target mutation

Chuyển jump target sang label khác. Test cần có cả đường đi và nhánh không được chọn.

### 13.4. Type descriptor mutation

Thay descriptor hoặc cast. Test cần xác nhận generated code tương thích kiểu.

### 13.5. Source map mutation

Đổi line mapping hoặc source range. Test cần xác nhận stack trace và diagnostic trỏ đúng dòng DSL.

### 13.6. Optimization mutation

Bỏ hoặc áp dụng sai optimization. Test cần kiểm tra semantic equivalence giữa optimized và unoptimized output.

### 13.7. Golden output

Snapshot generated output có thể phát hiện thay đổi format hoặc cấu trúc, nhưng chỉ snapshot không đủ để chứng minh output chạy đúng. Kết hợp compile/run test khi phù hợp.

## 14. Mutation testing cho optimizer

Optimizer có thể làm thay đổi biểu diễn chương trình nhưng phải giữ nguyên semantics quan sát được.

### 14.1. Constant folding

Thay phép tính constant hoặc bỏ folding. Test cần so sánh kết quả trước và sau optimization.

### 14.2. Dead code elimination

Bỏ một statement có side effect hoặc giữ lại code chết. Test cần phân biệt expression thuần và expression có side effect.

### 14.3. Common subexpression elimination

Thay cách chia sẻ kết quả biểu thức. Test cần xem xét mutability, exceptions và side effects.

### 14.4. Control flow simplification

Đổi nhánh hoặc điều kiện sau khi phân tích constant. Test cần bao phủ branch semantics.

### 14.5. Inlining

Thay function call bằng body nhưng có thể làm sai evaluation order hoặc exception stack. Test nên kiểm tra cả kết quả lẫn hành vi quan sát được.

### 14.6. Differential execution

Chạy cùng chương trình trên optimized và unoptimized runtime, so sánh output, state và error theo semantics đã định nghĩa.

## 15. DSL-specific mutation operators

Mutation testing cho code Java của compiler có thể dùng operator chung. Tuy nhiên, DSL còn cần mutation ở cấp syntax và semantics.

### 15.1. Grammar mutation

- Bỏ một production.
- Thay token terminal.
- Thay optional thành required hoặc ngược lại.
- Thay repetition zero-or-more thành one-or-more.
- Đổi precedence hoặc associativity.

### 15.2. AST mutation

- Bỏ node.
- Đổi node kind.
- Đổi child order.
- Thay literal value.
- Thay source range.
- Đổi reference tới declaration.

### 15.3. Type rule mutation

- Bỏ một compatibility check.
- Thay type promotion.
- Đổi nullability.
- Bỏ generic bound.
- Thay inferred return type.

### 15.4. Runtime semantics mutation

- Đảo comparison.
- Bỏ state update.
- Đổi evaluation order.
- Bỏ exception propagation.
- Thay default value.

### 15.5. Integration contract mutation

- Bỏ required request field.
- Đổi endpoint hoặc method.
- Bỏ authentication requirement.
- Thay response mapping.
- Bỏ idempotency key.

### 15.6. Policy mutation

- Bỏ authorization condition.
- Thay timeout.
- Nới retry limit.
- Đổi fallback branch.
- Bỏ audit event.

Các mutation policy cần được thiết kế cẩn thận để không tạo hành vi gây side effect trong môi trường thật. Nên chạy trong sandbox hoặc fake adapter.

## 16. Thiết kế test để kill mutant

Khi mutant sống sót, không phải lúc nào cũng cần thêm test mới. Có thể assertion hiện tại chưa kiểm tra đúng thuộc tính.

### 16.1. Test boundary

Với điều kiện amount >= 500, kiểm tra 499, 500 và 501. Boundary test thường kill relational operator mutant.

### 16.2. Test cả hai nhánh

Một if/else cần test điều kiện true và false. Với nhiều nhánh, test mỗi branch và các transition quan trọng.

### 16.3. Assert kết quả có ý nghĩa

Không chỉ xác nhận execution không ném exception. Kiểm tra output, state change, error code hoặc side effect cần thiết.

### 16.4. Negative test

Kiểm tra input không hợp lệ, quyền thiếu, type mismatch và state transition bị cấm.

### 16.5. Interaction assertion

Với adapter hoặc external port, kiểm tra operation được gọi đúng số lần và với argument phù hợp. Tránh over-mocking khiến test chỉ lặp lại implementation.

### 16.6. Property assertion

Kiểm tra invariant tổng quát như tổng phân bổ không vượt budget, parse rồi pretty-print giữ semantics hoặc evaluation không thay đổi state khi expression thuần.

### 16.7. Error assertion

Kiểm tra loại lỗi, diagnostic code và source range, không chỉ kiểm tra có exception bất kỳ.

### 16.8. Test input đa dạng

Dùng giá trị biên, empty, null, duplicate, Unicode, nested structure và các variant hiếm để tăng khả năng phân biệt hành vi.

## 17. Equivalent mutants và cách xử lý

Equivalent mutant làm source khác đi nhưng không tạo khác biệt quan sát được trong miền chương trình hợp lệ.

### 17.1. Ví dụ tương đương

Nếu compiler đã chứng minh x luôn lớn hơn 0 trong scope, thay điều kiện x > 0 bằng true có thể không thay đổi hành vi trên miền state hợp lệ.

### 17.2. Tương đương phụ thuộc miền input

Một mutant có thể tương đương chỉ khi input thỏa precondition. Nếu test generator không biết precondition, việc phân loại sẽ khó.

### 17.3. Không thể tự động chứng minh dễ dàng

Xác định hai chương trình có cùng hành vi nói chung là vấn đề khó. Nhiều công cụ chỉ đánh dấu suspected equivalent dựa trên phân tích hoặc cần con người xác nhận.

### 17.4. Ghi nhận lý do

Khi loại mutant khỏi score, nên lưu lý do, phạm vi input và người xác nhận. Tránh loại mutant chỉ vì nó khó kill.

### 17.5. Equivalent không phải invalid

Invalid mutant không tạo chương trình hợp lệ để chạy; equivalent mutant có thể chạy bình thường nhưng không đổi hành vi. Hai trạng thái này cần được phân biệt.

## 18. Surviving mutants và triage

Mutant sống sót là nguồn thông tin cần phân tích, không phải danh sách lỗi test để sửa máy móc.

### 18.1. Kiểm tra coverage

Xác định test nào chạy qua code bị mutation. Nếu không test nào chạy tới, cần bổ sung scenario.

### 18.2. Kiểm tra assertion

Nếu test có chạy nhưng vẫn pass, xem output có được assert đủ cụ thể không.

### 18.3. Xác định semantics

Mutant có thể không ảnh hưởng behavior theo contract. Nếu vậy, xem xét equivalent hoặc operator không phù hợp.

### 18.4. Ưu tiên theo rủi ro

Mutant ở authorization, monetary calculation, state transition hoặc parser boundary thường đáng chú ý hơn mutation ở formatting không quan trọng.

### 18.5. Không viết test chỉ để giết mutant

Test mới cần thể hiện một yêu cầu hoặc invariant có ý nghĩa. Tránh assertion giả tạo chỉ phụ thuộc implementation detail.

### 18.6. Nhóm mutant tương tự

Nhiều mutant có thể được kill bởi cùng một test hoặc cùng một thiếu sót. Nhóm theo method, operator hoặc semantics giúp triage hiệu quả.

## 19. Mutation testing với Java và PIT

PIT (Pitest) là một mutation testing system phổ biến cho Java và JVM. Nó sửa bytecode theo các mutation operators, chạy test liên quan và báo cáo mutant.

### 19.1. Cách hoạt động khái quát

1. Chạy test suite gốc.
2. Phân tích coverage để xác định test liên quan đến code.
3. Tạo mutant bytecode.
4. Chạy test được chọn.
5. Dừng sớm khi mutant bị kill.
6. Tổng hợp report.

### 19.2. Maven configuration minh họa

~~~xml
<plugin>
    <groupId>org.pitest</groupId>
    <artifactId>pitest-maven</artifactId>
    <version>PINNED_VERSION</version>
    <configuration>
        <targetClasses>
            <param>com.example.dsl.*</param>
        </targetClasses>
        <targetTests>
            <param>com.example.dsl.*Test</param>
        </targetTests>
        <threads>2</threads>
        <outputFormats>
            <param>HTML</param>
            <param>XML</param>
        </outputFormats>
    </configuration>
</plugin>
~~~

Version trong ví dụ là placeholder. Project cần pin phiên bản PIT tương thích với Java, build tool, test framework và plugin hiện dùng.

### 19.3. Chọn target

Không nhất thiết mutation toàn bộ repository ngay từ đầu. Có thể chọn compiler core, evaluator hoặc module có rủi ro cao để giới hạn chi phí.

### 19.4. Test selection

Coverage-based test selection giúp tránh chạy toàn bộ suite cho mọi mutant. Tuy nhiên, test dependency hoặc shared state có thể khiến lựa chọn test liên quan không đơn giản.

### 19.5. Custom mutators

PIT có thể được mở rộng bằng mutator phù hợp. Với DSL, custom mutator có thể nhắm vào type rule, semantic check hoặc adapter policy trong code Java.

### 19.6. Giới hạn

Mutation bytecode không tự hiểu toàn bộ grammar hoặc semantics của DSL. Muốn mutation ở cấp DSL source, cần thêm generator hoặc transformation riêng.

## 20. Mutation testing ở cấp source DSL

Ngoài mutation implementation, có thể tạo mutant trực tiếp từ chương trình DSL để kiểm tra end-to-end compiler và runtime.

### 20.1. Source mutation

Từ một chương trình DSL hợp lệ, tạo bản sao có thay đổi nhỏ:

~~~text
if account.balance >= requested
    allow()
else
    reject()
~~~

Mutant:

~~~text
if account.balance > requested
    allow()
else
    reject()
~~~

Test chạy source mutant qua compiler và runtime, sau đó so sánh kết quả với expected behavior.

### 20.2. Grammar-aware mutation

Generator cần tạo source vẫn parse được khi muốn kiểm tra semantics. Nếu mục tiêu là kiểm tra parser error handling, có thể cố ý tạo source malformed và kỳ vọng diagnostic.

### 20.3. Type-aware mutation

Chỉ tạo thay đổi giữ chương trình type-correct khi mục tiêu là kiểm tra runtime semantics. Với test type checker, mutation có thể cố ý tạo type error.

### 20.4. Preserve source metadata

Mutant cần giữ mapping từ vị trí source gốc sang source thay đổi để report chỉ ra dòng và biểu thức liên quan.

### 20.5. End-to-end oracle

Oracle có thể là expected result, invariant, snapshot hoặc reference interpreter. Cần tránh dùng cùng implementation logic để sinh expected result vì có thể lặp lại cùng lỗi.

## 21. Mutation testing cho parser và compiler pipeline

Compiler có nhiều phase phụ thuộc nhau. Một mutant ở phase sớm có thể gây lỗi ở phase sau.

### 21.1. Phase-level tests

Unit test riêng lexer, parser, resolver và type checker giúp xác định mutant bị kill ở đâu.

### 21.2. Integration tests

Compile toàn bộ chương trình DSL và kiểm tra diagnostic hoặc artifact. Điều này phát hiện lỗi khi các phase phối hợp.

### 21.3. Differential tests

So sánh compiler version mới với reference implementation hoặc compiler trước đó trên tập input đã xác định. Cần phân loại thay đổi được mong đợi và regression.

### 21.4. Golden tests

Lưu AST dump, diagnostic hoặc generated code làm expected artifact. Golden test hữu ích cho regression nhưng cần cập nhật có review khi contract thay đổi.

### 21.5. Semantic equivalence

Hai AST khác cấu trúc vẫn có thể có semantics tương đương. Test nên so sánh kết quả theo contract thay vì chỉ so sánh object tree khi mục tiêu là behavior.

## 22. Mutation testing và property-based testing

Hai kỹ thuật có thể bổ trợ nhau.

### 22.1. Property-based testing

Property-based test sinh nhiều input và kiểm tra một thuộc tính tổng quát. Ví dụ parse rồi pretty-print rồi parse lại phải giữ AST semantics.

### 22.2. Mutation testing

Mutation testing thay đổi implementation và kiểm tra property test có phát hiện sai lệch hay không.

### 22.3. Kết hợp

Property-based test có thể kill nhiều mutant nhờ input đa dạng. Ngược lại, surviving mutant giúp nhận ra property chưa đủ mạnh.

### 22.4. Shrinking

Khi property test tìm thấy input làm mutant khác behavior, shrinking có thể rút gọn input để tạo ví dụ dễ hiểu và dễ lưu thành regression test.

### 22.5. Oracle independence

Property nên mô tả invariant độc lập với code implementation. Nếu property gọi lại cùng helper bị mutation, test có thể không phát hiện lỗi.

## 23. Mutation testing và fuzzing

Fuzzing tập trung sinh input đa dạng hoặc bất thường để tìm crash, hang và lỗi parser/runtime. Mutation testing tập trung thay đổi chương trình để đánh giá test.

### 23.1. Fuzz input

Fuzzer có thể tạo source DSL ngẫu nhiên, token stream hoặc JSON payload. Mục tiêu thường là tìm crash, panic, resource exhaustion hoặc parser inconsistency.

### 23.2. Mutation input

Grammar-based mutator có thể sửa chương trình DSL hợp lệ để tạo biến thể gần với source gốc. Đây là mutation trên input, cần phân biệt với mutation trên implementation.

### 23.3. Kết hợp

Có thể chạy corpus fuzzing trên từng mutant hoặc dùng input được fuzzer tìm thấy làm test regression để kill mutant.

### 23.4. Resource bounds

Fuzzing và mutation có thể tạo input hoặc chương trình chạy rất lâu. Cần giới hạn thời gian, memory và số lần thực thi.

## 24. Mutation testing cho security và policy

DSL có thể mô tả quyền, workflow, dữ liệu và tích hợp nên một số mutation có tác động bảo mật.

### 24.1. Authorization mutation

Thay điều kiện yêu cầu cả hai permission thành chỉ một permission. Test cần xác nhận caller thiếu bất kỳ quyền bắt buộc nào đều bị từ chối.

### 24.2. Tenant isolation mutation

Bỏ điều kiện tenant ID khi truy vấn hoặc mapping. Test cần tạo hai tenant và xác nhận dữ liệu không bị đọc chéo.

### 24.3. Input validation mutation

Bỏ kiểm tra range hoặc schema. Test cần xác nhận payload sai bị reject trước khi tạo side effect.

### 24.4. Secret redaction mutation

Bỏ redaction trong log. Test cần xác nhận secret không xuất hiện trong log output hoặc diagnostic.

### 24.5. TLS policy mutation

Cho phép endpoint không an toàn hoặc bỏ certificate validation. Kiểm tra policy phải chạy trong test environment với fake transport, không gọi endpoint thật.

### 24.6. Audit mutation

Bỏ audit event cho operation nhạy cảm. Test cần xác nhận sự kiện audit được tạo với metadata cần thiết.

### 24.7. Safe execution

Security mutation phải được chạy trong môi trường cô lập, với fake service và dữ liệu tổng hợp. Không để mutant vô hiệu hóa policy tác động tới production.

## 25. Hiệu năng của mutation campaign

Mutation testing có thể tốn nhiều thời gian vì phải chạy test nhiều lần.

### 25.1. Mutant count

Số mutant phụ thuộc kích thước code và operators. Không cần tạo mọi mutation có thể; chọn operator đại diện cho lỗi có khả năng xảy ra.

### 25.2. Test prioritization

Chạy test có khả năng kill mutant trước để dừng sớm. Test selection dựa trên coverage có thể giảm chi phí.

### 25.3. Parallel execution

Mutant độc lập có thể chạy song song, nhưng cần giới hạn concurrency để không làm quá tải CPU, memory hoặc database test.

### 25.4. Baseline reuse

Build artifact và dependency có thể được tái sử dụng nếu tool hỗ trợ an toàn. Tránh chia sẻ mutable output giữa các mutant.

### 25.5. Incremental mutation

Chạy mutation cho code vừa thay đổi hoặc module rủi ro cao trong vòng lặp phát triển; chạy chiến dịch rộng hơn theo lịch.

### 25.6. Timeout calibration

Timeout phải dựa trên thời gian test bình thường và đặc tính workload. Timeout quá thấp tạo false kill; quá cao làm campaign kéo dài.

### 25.7. Flaky tests

Test không ổn định làm kết quả mutant khó diễn giải. Cần xác định baseline repeatability trước khi tin mutation report.

## 26. Đọc mutation report

Mutation report nên giúp người phát triển đi từ mutant đến test và source liên quan.

### 26.1. Source location

Report cần chỉ ra class, method, dòng hoặc source location của mutation.

### 26.2. Mutator description

Hiển thị loại thay đổi, ví dụ conditional boundary hoặc return value mutation.

### 26.3. Killing test

Với mutant bị kill, report nên nêu test đầu tiên làm thất bại và lý do.

### 26.4. Survived mutant

Với mutant sống sót, hiển thị test đã chạy và coverage liên quan để người đọc phân tích.

### 26.5. Trend

Theo dõi score theo thời gian và module. Một đợt giảm score có thể báo test suite không theo kịp thay đổi code.

### 26.6. Exclusion

Ghi rõ module hoặc mutation nào bị loại, lý do và thời hạn xem xét lại. Exclusion không nên trở thành cách làm đẹp score.

## 27. Tích hợp mutation testing vào quy trình phát triển

Không nhất thiết chạy toàn bộ mutation campaign trong mọi lần commit.

### 27.1. Developer feedback

Developer có thể chạy mutation trên class hoặc package đang sửa để nhận phản hồi nhanh.

### 27.2. Pull request

CI có thể chạy một phạm vi mutation giới hạn cho module quan trọng hoặc diff code, tùy tool hỗ trợ.

### 27.3. Scheduled campaign

Chiến dịch rộng chạy theo lịch để kiểm tra test suite trên toàn bộ compiler/runtime.

### 27.4. Quality gate

Có thể đặt ngưỡng mutation score cho module có rủi ro cao. Gate nên xét trend, equivalent mutant, timeout và test flakiness, không chỉ một con số tổng.

### 27.5. Ownership

Mỗi module cần owner xử lý surviving mutant. Report cần được gắn với issue hoặc review nếu mutant cho thấy lỗ hổng test đáng kể.

### 27.6. Baseline management

Khi nâng tool hoặc thay mutation operators, score có thể thay đổi dù source và test không đổi. Lưu tool version và cấu hình cùng report.

## 28. Những sai lầm thường gặp

### 28.1. Coi mutation score là mục tiêu duy nhất

Đội ngũ có thể viết assertion vô nghĩa chỉ để kill mutant. Đánh giá chất lượng test dựa trên behavior và risk, không chạy theo score.

### 28.2. Bỏ qua equivalent mutant mà không ghi lý do

Loại mutant không có bằng chứng làm score thiếu minh bạch. Ghi nhận lý do và phạm vi tương đương.

### 28.3. Chỉ dùng mutation operators chung

Mutation arithmetic hoặc boolean trong Java có thể bỏ sót grammar và semantics của DSL. Bổ sung DSL-specific operators.

### 28.4. Chỉ kiểm tra line coverage

Code đã chạy chưa chắc assertion đủ mạnh. Xem surviving mutant và output mà test kiểm tra.

### 28.5. Chạy test không ổn định

Flaky test có thể làm mutant bị kill ngẫu nhiên. Ổn định baseline trước khi phân tích score.

### 28.6. Mutation quá nhiều và không có ưu tiên

Campaign lớn làm chậm feedback và khó triage. Chọn module, operator và risk theo từng đợt.

### 28.7. Không cô lập side effect

Mutant có thể gọi dịch vụ thật hoặc ghi dữ liệu. Dùng fake, sandbox và test database riêng.

### 28.8. Không xem xét compile failure

Mutant không biên dịch không chứng minh test phát hiện lỗi behavior. Phân loại invalid riêng.

### 28.9. Thêm test chỉ để giết mutant

Test phải phản ánh contract hoặc invariant. Tránh phụ thuộc implementation detail.

### 28.10. Không phân biệt source mutation và implementation mutation

Thay đổi source DSL và thay đổi code compiler là hai loại mutation khác nhau. Chọn đúng loại để trả lời câu hỏi kiểm thử.

## 29. Quy trình áp dụng mutation testing cho DSL

1. **Chọn phạm vi.** Xác định lexer, parser, type checker, runtime, code generator hoặc integration layer cần đánh giá.
2. **Ổn định baseline.** Chạy test gốc và xác nhận kết quả lặp lại.
3. **Chọn mutation operators.** Kết hợp operator JVM chung và operator đặc thù cho grammar, type rule, state và policy.
4. **Xác định oracle.** Chọn expected output, invariant, diagnostic, contract hoặc differential execution.
5. **Cô lập môi trường.** Dùng sandbox, fake adapter, test data và resource limit.
6. **Sinh mutant có kiểm soát.** Gắn mutant với source location, operator và seed nếu có random generation.
7. **Chạy test.** Dùng test selection, timeout và concurrency có giới hạn.
8. **Phân loại kết quả.** Killed, survived, equivalent, invalid, timed out và no coverage.
9. **Triage surviving mutant.** Kiểm tra test coverage, assertion, semantics và risk.
10. **Cải thiện test.** Bổ sung boundary, negative, property, interaction hoặc error assertion có ý nghĩa.
11. **Tính score minh bạch.** Ghi rõ mẫu số, exclusions, tool version và operator set.
12. **Theo dõi xu hướng.** Lưu report và so sánh theo module, release hoặc pull request.
13. **Điều chỉnh operator.** Bổ sung mutation khi DSL có syntax hoặc semantics mới.
14. **Review security mutation.** Chạy các mutation policy trong môi trường cô lập.
15. **Đưa vào quy trình.** Chọn feedback nhanh cho developer và campaign rộng theo lịch.

## 30. Câu hỏi tự kiểm tra

1. Mutation testing là gì và mutant được tạo ra nhằm mục đích gì?
2. Phân biệt killed, survived, equivalent, invalid và timed-out mutant.
3. Mutation score được tính như thế nào và vì sao không phải xác suất correctness?
4. Mutation testing khác code coverage ở điểm nào?
5. Những mutation operators chung nào thường được dùng?
6. Lexer có thể được kiểm tra bằng keyword, operator, literal và source-position mutation ra sao?
7. Parser mutation có thể làm lộ lỗi precedence, associativity và error recovery như thế nào?
8. Name resolution mutation nên bao phủ scope, shadowing và import ra sao?
9. Type checker mutation có thể kiểm tra compatibility, nullability và generic substitution như thế nào?
10. Semantic analysis mutation có thể tác động required field, invariant và authorization ra sao?
11. Runtime evaluator và code generator cần những mutation operators nào?
12. Equivalent mutant là gì và vì sao khó tự động xác định?
13. Làm thế nào triage một surviving mutant mà không viết assertion phụ thuộc implementation?
14. PIT hoạt động khái quát ra sao và giới hạn nào khi áp dụng cho DSL?
15. Phân biệt mutation trên implementation với mutation trực tiếp trên source DSL.
16. Mutation testing kết hợp property-based testing và fuzzing như thế nào?
17. Vì sao security mutation phải chạy trong sandbox hoặc fake environment?
18. Làm thế nào giảm chi phí mutation campaign mà vẫn giữ giá trị phát hiện lỗi?
19. Một mutation report tốt cần cung cấp thông tin gì?
20. Hãy đề xuất bộ mutation operators và test oracle cho một DSL có expression, type system, authorization rule và workflow state transition.

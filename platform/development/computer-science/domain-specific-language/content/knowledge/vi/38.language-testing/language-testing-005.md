# Golden test

## 1. Golden test trong kiểm thử DSL là gì?

Trong một nền tảng ngôn ngữ chuyên biệt miền (Domain-Specific Language — DSL), **golden test** là kỹ thuật kiểm thử so sánh kết quả thực tế của compiler, parser, formatter, validator hoặc runtime với một kết quả chuẩn đã được lưu và xem xét trước.

Kết quả chuẩn thường được gọi là golden file, expected output, baseline hoặc approved snapshot. Nó ghi lại hành vi được mong đợi cho một input cụ thể.

Ví dụ, một DSL mô tả chính sách:

~~~text
policy "Discount"
  when order.total >= 1000000
  then order.discount = 0.05
~~~

Một golden test có thể lưu token stream mà lexer tạo ra, AST hoặc biểu diễn trung gian, diagnostics và source range, kết quả semantic analysis, code hoặc artifact được generate, kết quả formatter hoặc output của runtime.

Khi test chạy, hệ thống tạo kết quả mới rồi so sánh với file chuẩn. Nếu khác nhau, test báo diff để người phát triển xác định thay đổi là lỗi hay một thay đổi có chủ ý cần cập nhật baseline.

Golden test đặc biệt hữu ích khi output có cấu trúc lớn hoặc nhiều chi tiết cần được kiểm tra cùng lúc, chẳng hạn AST dump, generated source, diagnostics, serialized workflow hoặc report.

## 2. Golden test giải quyết vấn đề gì?

Một DSL thường có nhiều tầng biến đổi:

~~~text
DSL source
    |
    v
Lexer
    |
    v
Tokens
    |
    v
Parser
    |
    v
AST
    |
    v
Semantic analysis
    |
    v
IR / execution plan
    |
    v
Generator or runtime
    |
    v
Output
~~~

Một thay đổi nhỏ trong grammar hoặc generator có thể làm thay đổi nhiều output downstream. Nếu chỉ kiểm tra một vài Boolean assertion, test có thể bỏ sót node AST bị thiếu hoặc sai thứ tự, source range bị lệch, diagnostic mất code hoặc severity, generated code thay đổi ngoài ý muốn, formatter làm mất comment hoặc runtime tạo kết quả khác.

Golden test lưu lại toàn bộ hoặc một phần kết quả có ý nghĩa để phát hiện regression trên bề mặt rộng hơn.

### 2.1 Ví dụ so sánh

Input:

~~~text
let total = price * quantity
~~~

Expected AST:

~~~text
LetDeclaration
  name: total
  initializer:
    BinaryExpression
      operator: MULTIPLY
      left: Identifier(price)
      right: Identifier(quantity)
~~~

AST mới được tạo trong lần chạy hiện tại. Nếu parser vô tình đổi precedence hoặc tạo node khác, diff sẽ hiển thị vị trí thay đổi.

## 3. Golden test, snapshot test và unit test

Các kỹ thuật này có phần giao nhau nhưng mục đích không hoàn toàn giống nhau.

| Kỹ thuật | Cách kiểm tra | Phù hợp với |
|---|---|---|
| Unit test | Assertion trên hành vi hoặc giá trị cụ thể | Logic nhỏ, invariant và edge case |
| Integration test | Kiểm tra nhiều thành phần phối hợp | Compiler pipeline, runtime và host API |
| Golden test | So sánh output với file chuẩn được duyệt | Output lớn, cấu trúc và diagnostics |
| Snapshot test | Lưu snapshot rồi so sánh lần chạy sau | UI tree, serialized object, output |
| Property-based test | Kiểm tra thuộc tính trên nhiều input sinh tự động | Invariant, parser và serializer |
| Fuzz test | Sinh input bất thường để tìm crash hoặc lỗi | Lexer, parser và runtime boundary |

Golden test thường là một dạng snapshot hoặc approval testing có quy trình quản lý baseline rõ ràng. Tên gọi có thể khác nhau giữa các framework.

### 3.1 Khi nên dùng golden test?

- Output có nhiều dòng hoặc cấu trúc lồng nhau.
- Kết quả cần được review trực quan.
- Một thay đổi có thể ảnh hưởng nhiều phần output.
- Muốn giữ ví dụ regression lâu dài.
- Có thể tạo output deterministic hoặc normalize phần không ổn định.

### 3.2 Khi không nên chỉ dùng golden test?

Golden test không thay thế assertion cho invariant quan trọng. Một snapshot lớn có thể thay đổi đồng thời nhiều dòng nhưng không nói rõ quy tắc nghiệp vụ nào phải đúng.

Ví dụ, kiểm tra một kết quả tính phí nên có assertion rõ về giá trị, rounding và giới hạn. Golden file có thể bổ sung để kiểm tra report đầy đủ.

## 4. Cấu trúc của một golden test

Một test thường gồm bốn thành phần:

1. **Input fixture:** source DSL, configuration hoặc dữ liệu đầu vào.
2. **Test operation:** compiler, formatter, analyzer hoặc runtime được gọi.
3. **Expected baseline:** kết quả chuẩn đã được lưu.
4. **Comparison:** phép so sánh và diff khi có khác biệt.

~~~text
fixtures/
  valid-discount/
    input.dsl
    expected.ast.txt
    expected.diagnostics.txt
    expected.generated.java
~~~

Test có thể chỉ dùng một expected file hoặc nhiều file cho từng phase.

### 4.1 Input phải rõ ràng

Input fixture nên tự chứa hoặc khai báo dependency rõ. Tránh để kết quả phụ thuộc vào file người dùng trong máy, working directory hoặc dữ liệu mạng thay đổi.

### 4.2 Baseline là dữ liệu được duyệt

Expected file là một phần của test contract. Nó cần được review như code, có lịch sử version và có lý do khi thay đổi.

### 4.3 Diff phải hữu ích

Khi fail, test nên hiển thị file input liên quan, expected và actual, dòng hoặc path khác nhau, cách chạy lại test và cách tạo candidate baseline nếu framework hỗ trợ.

## 5. Chọn output nào làm golden

Không phải mọi giá trị nội bộ đều phù hợp để lưu baseline.

### 5.1 Lexer output

Có thể snapshot token kind, lexeme, channel và source range:

~~~text
LET           "let"       1:1-1:4
IDENTIFIER    "total"     1:5-1:10
EQUALS        "="         1:11-1:12
NUMBER        "10"        1:13-1:15
~~~

Hữu ích khi thay đổi lexer, comment handling, escape sequence hoặc Unicode behavior.

### 5.2 Parser output

AST dump cho thấy node type, child order, operator precedence và source range.

### 5.3 Semantic diagnostics

Golden file có thể chứa code, severity, message, source range và related locations.

### 5.4 Intermediate representation

IR hoặc execution plan phù hợp khi cần kiểm tra compiler lowering, dependency graph hoặc optimization.

### 5.5 Generated code

So sánh source code được sinh ra giúp phát hiện thay đổi template, import, naming, escaping và ordering.

### 5.6 Formatter output

Formatter thường có output văn bản deterministic, rất phù hợp với golden test.

### 5.7 Runtime result

Có thể lưu decision, event sequence hoặc serialized output. Cần loại bỏ timestamp và identifier ngẫu nhiên nếu chúng không thuộc contract.

### 5.8 Không snapshot mọi internal detail

Snapshot quá nhiều chi tiết private khiến refactor vô hại tạo hàng loạt diff. Chỉ golden những output có ý nghĩa ổn định đối với consumer hoặc contract cần bảo vệ.

## 6. Tổ chức thư mục fixture

Một cấu trúc dễ quản lý:

~~~text
src/test/resources/golden/
  lexer/
    unicode-identifiers/
      input.dsl
      expected.txt
  parser/
    operator-precedence/
      input.dsl
      expected.ast
  diagnostics/
    unknown-symbol/
      input.dsl
      expected.txt
  formatter/
    nested-blocks/
      input.dsl
      expected.dsl
  generator/
    discount-policy/
      input.dsl
      expected.java
~~~

### 6.1 Đặt tên theo behavior

Tên fixture nên mô tả tình huống hoặc quy tắc, chẳng hạn operator-precedence, missing-required-field hoặc unicode-source-range. Tránh tên chung chung như test1, sample2 hoặc output-final.

### 6.2 Một fixture, một mục tiêu rõ

Fixture nhỏ giúp diff dễ đọc và khoanh vùng regression. Một end-to-end fixture lớn vẫn hữu ích, nhưng không nên là cách duy nhất để kiểm tra mọi phase.

### 6.3 Dùng extension có ý nghĩa

Giữ input là .dsl, AST là .ast.txt, generated source là .java và diagnostics là .txt để editor hiển thị đúng cú pháp.

### 6.4 Metadata khi cần

Có thể lưu metadata như test ID, phase, options hoặc schema version trong test code hay file metadata riêng. Không nhúng dữ liệu không cần thiết vào expected output.

## 7. Viết golden test trong Java

Ví dụ đơn giản dùng JUnit:

~~~java
class ParserGoldenTest {
    @Test
    void parsesOperatorPrecedence() throws Exception {
        String source = readFixture("parser/operator-precedence/input.dsl");

        AstNode ast = parser.parse(source);
        String actual = AstPrinter.print(ast);
        String expected = readFixture(
            "parser/operator-precedence/expected.ast"
        );

        assertEquals(expected, actual);
    }
}
~~~

Test này dễ hiểu nhưng cần xử lý encoding, newline và diff rõ ràng.

### 7.1 Tách helper

Một helper có thể đọc UTF-8 và chuẩn hóa line ending theo policy:

~~~java
String readFixture(String path) throws IOException {
    try (InputStream input = getClass()
            .getResourceAsStream("/golden/" + path)) {
        if (input == null) {
            throw new FileNotFoundException(path);
        }
        return new String(input.readAllBytes(), StandardCharsets.UTF_8);
    }
}
~~~

### 7.2 So sánh cấu trúc

Nếu output là JSON hoặc tree, có thể parse cả expected và actual rồi so sánh cấu trúc thay vì text thuần. Tuy nhiên, cần quyết định có quan tâm key order, whitespace hoặc serialization details hay không.

### 7.3 Failure message

Dùng assertion library có diff tốt hoặc tạo unified diff để reviewer biết phần nào khác.

### 7.4 Tránh test phụ thuộc thứ tự chạy

Mỗi test nên tạo parser/runtime state riêng hoặc reset state rõ ràng. Không dùng một registry mutable được chia sẻ giữa các fixture nếu thứ tự chạy có thể làm thay đổi output.

## 8. Determinism: điều kiện quan trọng

Golden test chỉ ổn định khi cùng input và cùng contract tạo ra cùng output.

Các nguồn nondeterminism thường gặp:

- Timestamp hiện tại.
- UUID hoặc random number.
- Thứ tự iteration của map/set.
- File system traversal order.
- Locale và timezone mặc định.
- Absolute path của máy.
- Version hoặc metadata môi trường.
- Thread scheduling.
- Network response.
- Compiler/JDK version.

### 8.1 Stable ordering

Nếu thứ tự output có ý nghĩa, định nghĩa sort key và tie-breaker. Không dựa vào thứ tự iteration không được bảo đảm.

### 8.2 Inject clock

Thay vì đọc system clock trực tiếp, truyền Clock cố định trong test:

~~~java
Clock fixedClock = Clock.fixed(
    Instant.parse("2026-01-15T10:00:00Z"),
    ZoneOffset.UTC
);
~~~

### 8.3 Inject random source

Nếu thuật toán cần randomness, dùng seed cố định trong test hoặc inject generator giả lập để tạo kết quả có thể tái lập.

### 8.4 Isolate network

Không gọi service thật trong golden test. Dùng fake, stub hoặc fixture response được version hóa.

### 8.5 Pin toolchain khi cần

Nếu output phụ thuộc compiler/JDK version, test environment nên pin version hoặc lưu version trong metadata để giải thích khác biệt.

## 9. Normalize output trước khi so sánh

Một số khác biệt không mang ý nghĩa đối với contract. Có thể normalize trước khi tạo hoặc so sánh golden:

- Chuẩn hóa CRLF và LF.
- Dùng UTF-8 nhất quán.
- Thay absolute path bằng placeholder.
- Chuẩn hóa timestamp nếu timestamp không phải output cần kiểm tra.
- Sắp xếp collection nếu contract không quy định thứ tự.
- Loại bỏ memory address hoặc process ID.

### 9.1 Normalization phải có chủ đích

Không normalize một khác biệt có ý nghĩa. Nếu thứ tự diagnostics là contract, không được sort diagnostics chỉ để test ổn định.

### 9.2 Path normalization

Trên Windows và Linux, separator khác nhau. Có thể biểu diễn path theo slash chuẩn trong golden nếu path format không phải hành vi đang kiểm thử.

### 9.3 Whitespace

Formatter golden test thường cần giữ nguyên whitespace vì đó là output cần kiểm tra. Parser AST golden test có thể bỏ whitespace nguồn nếu nó không liên quan đến source mapping đang được kiểm thử.

### 9.4 Unicode

Không tự động normalize Unicode NFC/NFD nếu DSL có semantics hoặc source offset phụ thuộc chuỗi code point gốc. Quy tắc normalization cần phù hợp với contract.

### 9.5 Redaction

Không ghi secret hoặc dữ liệu thật vào golden file. Dùng fixture giả và placeholder ổn định.

## 10. Golden test cho lexer và parser

Lexer và parser là nền tảng của DSL nên golden test giúp phát hiện regression rộng.

### 10.1 Lexer cases

Có thể tạo fixture cho keyword và identifier, số nguyên/decimal/exponent, string escape, comment một dòng và nhiều dòng, Unicode identifier, newline và continuation, token lỗi và source range.

### 10.2 Parser cases

Fixture nên bao gồm operator precedence, associativity, nested expression, block và scope, optional syntax, error recovery, missing delimiter và ambiguous grammar.

### 10.3 AST printer ổn định

AST printer nên tạo format deterministic. Không đưa object identity, hash code hoặc memory address vào output.

### 10.4 Source range

Nếu kiểm thử range, golden cần ghi rõ convention: offset zero-based hay one-based, end-exclusive hay end-inclusive, UTF-16 hay code point.

### 10.5 Error recovery

Parser có thể tiếp tục sau lỗi và tạo partial AST. Golden test giúp ghi lại cả diagnostic lẫn node được giữ lại.

## 11. Golden test cho diagnostics

Diagnostics là output quan trọng đối với editor, CLI và build tool.

Một diagnostic có thể chứa:

~~~text
ERROR DSL1021: Unknown symbol 'custmer'
  at examples/order.dsl:4:12-4:19
  suggestion: customer
~~~

Golden test có thể bảo vệ diagnostic code, severity, message, source URI/range, related information, suggested fix và thứ tự diagnostics nếu contract quy định.

### 11.1 Message có ổn định không?

Nếu message là văn bản hiển thị cho người dùng, thay đổi câu chữ có thể hợp lệ. Có thể snapshot code/range/arguments riêng và kiểm tra message ở một lớp test khác.

### 11.2 Localization

Nếu diagnostics được dịch, không nên để golden phụ thuộc locale máy. Chọn locale cố định hoặc tách test nội dung và test localization.

### 11.3 Không che mất diagnostic

Normalizer không nên loại bỏ diagnostic mới chỉ vì thứ tự hoặc message thay đổi. Một diagnostic bổ sung có thể báo regression hoặc thay đổi contract cần review.

## 12. Golden test cho semantic analysis và IR

Semantic analysis có thể tạo symbol table, type information, dependency graph hoặc execution plan.

### 12.1 Symbol table

Golden output có thể hiển thị:

~~~text
Scope: module
  symbol: calculateDiscount
  kind: FUNCTION
  type: (Money, CustomerTier) -> Percentage

Scope: rule Discount
  symbol: order
  kind: VARIABLE
  type: Order
~~~

### 12.2 Type resolution

Test các trường hợp overload, generic type, nullable type, implicit conversion và type error.

### 12.3 Dependency graph

Có thể snapshot graph theo thứ tự node/edge deterministic để phát hiện dependency bị thiếu hoặc cycle mới.

### 12.4 IR

IR golden hữu ích khi compiler có optimization hoặc lowering nhiều bước. Nên snapshot những trường ổn định có ý nghĩa với backend.

### 12.5 Tránh khóa vào implementation

Nếu IR chỉ là chi tiết nội bộ có thể thay đổi thường xuyên, ưu tiên test semantic result hoặc public execution plan thay vì toàn bộ object dump.

## 13. Golden test cho code generation

Code generator thường tạo nhiều file và output dài, rất phù hợp với golden test.

### 13.1 Generated source

Lưu file expected với đúng extension để diff và syntax highlighting dễ đọc.

~~~text
generator/
  simple-policy/
    input.dsl
    expected/
      DiscountPolicy.java
      PolicyMetadata.json
~~~

### 13.2 Multi-file output

So sánh tập file theo relative path và nội dung. Cần phát hiện cả file thừa và file bị thiếu.

### 13.3 Import và declaration order

Nếu generator có thể sắp xếp import hoặc declaration, hãy định nghĩa thứ tự ổn định.

### 13.4 Escaping

Fixture nên kiểm tra quote, backslash, newline, Unicode và ký tự đặc biệt khi chuyển DSL string thành source code.

### 13.5 Generated comments

Nếu output có timestamp hoặc build ID trong header, inject giá trị cố định hoặc loại bỏ trường không thuộc contract.

### 13.6 Compile generated code

Golden comparison xác nhận text giống baseline. Nó không chứng minh code sinh ra compile hoặc chạy đúng. Kết hợp compile/integration test cho các artifact quan trọng.

## 14. Golden test cho formatter

Formatter là trường hợp kinh điển cho golden test vì output chính là văn bản.

Input:

~~~text
policy "Discount"{
when order.total>1000 then order.discount=0.05
}
~~~

Expected:

~~~text
policy "Discount" {
  when order.total > 1000
  then order.discount = 0.05
}
~~~

### 14.1 Idempotence

Formatter nên thường thỏa mãn:

~~~text
format(format(source)) == format(source)
~~~

Golden test kiểm tra output cụ thể; unit/property test kiểm tra idempotence trên nhiều input.

### 14.2 Comment preservation

Kiểm tra comment đầu file, trailing comment, comment giữa expression và comment trong block.

### 14.3 Blank lines và indentation

Golden file giúp review chính xác thay đổi về indent, line break và khoảng trắng.

### 14.4 Format không làm đổi semantics

Có thể parse source trước và sau formatting rồi so sánh semantic model hoặc AST đã bỏ source trivia.

## 15. Golden test cho runtime và workflow

Runtime có thể trả kết quả, event sequence hoặc trace.

Ví dụ:

~~~text
Execution result:
  status: COMPLETED
  decision: APPROVE
  actions:
    - ReserveInventory
    - ChargePayment
    - GenerateInvoice
~~~

### 15.1 Event sequence

Snapshot event sequence giúp phát hiện thay đổi thứ tự workflow. Chỉ làm vậy khi ordering là một phần contract.

### 15.2 Decision output

Golden test có thể lưu outcome và reason code cho các rule set đại diện.

### 15.3 Side effects

Không gọi hệ thống thật chỉ để tạo golden. Dùng fake host services và ghi lại các command/event mà runtime yêu cầu.

### 15.4 Time và retry

Inject clock và scheduler giả lập để output không phụ thuộc thời gian chạy thực tế.

### 15.5 Concurrency

Nếu runtime xử lý song song, không snapshot thứ tự hoàn thành ngẫu nhiên trừ khi order đó được bảo đảm. Có thể snapshot dependency graph hoặc tập kết quả đã canonicalize.

## 16. So sánh văn bản và cấu trúc

Chọn comparator phù hợp với output.

### 16.1 Exact text comparison

So sánh từng ký tự. Phù hợp với formatter, generated source và output mà whitespace có ý nghĩa.

### 16.2 Line-based comparison

So sánh theo dòng, tạo unified diff dễ đọc. Vẫn giữ khác biệt whitespace trong mỗi dòng.

### 16.3 Structured comparison

Parse JSON/XML/YAML hoặc AST dump thành cấu trúc rồi so sánh field. Có thể bỏ qua thứ tự object key nếu format không quy định.

### 16.4 Semantic comparison

So sánh ý nghĩa thay vì serialization. Ví dụ, so sánh hai AST sau khi bỏ source trivia hoặc so sánh tập dependency không quan tâm thứ tự.

### 16.5 Canonical serialization

Nếu output cấu trúc cần lưu dưới dạng text, canonical serializer có thể chuẩn hóa key order, number format và whitespace trước khi lưu.

### 16.6 Không dùng comparator quá rộng

Comparator bỏ qua quá nhiều field có thể khiến regression lọt qua. Mọi trường bị bỏ qua cần có lý do rõ.

## 17. Quy trình cập nhật golden file

Khi test thất bại vì actual khác expected, không nên tự động chấp nhận output mới.

Quy trình cập nhật:

1. Chạy lại đúng test để xác nhận diff ổn định.
2. Xem input fixture và expected hiện tại.
3. Đọc diff của actual output.
4. Xác định thay đổi là regression hay hành vi mới có chủ ý.
5. Nếu là regression, sửa implementation và giữ baseline.
6. Nếu là thay đổi có chủ ý, cập nhật expected file.
7. Review toàn bộ diff như một phần của code change.
8. Chạy các test liên quan để xác nhận thay đổi không làm hỏng behavior khác.
9. Ghi lý do cập nhật nếu diff lớn hoặc thay đổi contract.

### 17.1 Approval mode

Một số framework tạo candidate snapshot khi test fail và yêu cầu người phát triển approve. Candidate không nên tự động trở thành baseline trong CI.

### 17.2 Không update hàng loạt mù quáng

Lệnh update toàn bộ golden có thể làm mất dấu regression nếu developer chỉ chạy update mà không đọc diff.

### 17.3 Review baseline

Reviewer cần thấy cả code thay đổi và golden diff. Một thay đổi generated code lớn cần được giải thích, không chỉ nói rằng snapshot đã được cập nhật.

### 17.4 Xóa fixture cũ

Khi feature bị loại bỏ, có thể xóa input và expected tương ứng cùng thay đổi code. Không giữ fixture chết làm nhiễu suite.

## 18. Đọc diff hiệu quả

Diff tốt giúp xác định nguyên nhân nhanh.

### 18.1 Unified diff

Ví dụ:

~~~diff
-  discount = 0.05
+  discount = 0.10
~~~

### 18.2 Context lines

Hiển thị vài dòng trước và sau khác biệt để hiểu cấu trúc.

### 18.3 Path-level diff

Với generator nhiều file, báo rõ file nào được thêm, xóa hoặc thay đổi.

### 18.4 Large diff

Nếu toàn bộ file thay đổi vì newline hoặc serializer, xác định nguyên nhân trước khi review từng dòng.

### 18.5 Diff có thể gây nhiễu

Một thay đổi formatter có thể tạo nhiều dòng khác biệt. Có thể dùng semantic diff bổ sung, nhưng vẫn giữ exact golden nếu formatting là contract.

## 19. Quản lý baseline và version control

Golden files thường được commit cùng test code.

### 19.1 Lịch sử Git

Git cho biết baseline thay đổi khi nào, bởi ai và cùng commit nào. Điều này hữu ích khi tìm regression.

### 19.2 Review ownership

Golden file đại diện contract của compiler/runtime. Thay đổi lớn có thể cần reviewer hiểu grammar, generator hoặc semantics.

### 19.3 Baseline không phải output tùy ý

Không cập nhật baseline chỉ để CI xanh. Cần hiểu nguyên nhân và xác nhận output mới đúng.

### 19.4 Branch consistency

Khi merge branch thay đổi grammar và branch thay đổi formatter, có thể phát sinh conflict trong expected file. Resolve dựa trên behavior cuối cùng và chạy lại test.

### 19.5 Binary golden

Với image, archive hoặc binary artifact, diff text không hữu ích. Có thể dùng checksum, metadata comparison hoặc specialized visual diff. Không snapshot file binary lớn nếu chỉ cần kiểm tra một số thuộc tính.

## 20. Golden test và kiểm thử regression

Golden test là một công cụ regression testing. Nó giúp giữ hành vi đã được chấp nhận qua các lần thay đổi compiler hoặc runtime.

### 20.1 Regression fixture

Khi phát hiện bug, tạo fixture tái hiện bug và expected output đúng sau khi fix. Fixture giúp bug không quay lại.

### 20.2 Bug phải có assertion phù hợp

Nếu bug liên quan tính toán, hãy có assertion cho kết quả số học hoặc invariant, không chỉ một snapshot chung.

### 20.3 Tập hợp fixture đại diện

Chọn input theo ranh giới grammar, type system, diagnostics, backend và các tình huống đã từng lỗi.

### 20.4 Golden suite không chứng minh tính đúng tuyệt đối

Baseline có thể đã chứa bug. Golden test chứng minh output không thay đổi ngoài ý muốn so với baseline; nó không chứng minh baseline là behavior đúng theo đặc tả.

## 21. Tốc độ và khả năng mở rộng của golden suite

Khi số lượng fixture tăng, suite cần được tổ chức để chạy hiệu quả.

### 21.1 Chia theo phase

Tách lexer, parser, semantic, formatter, generator và runtime để chạy hoặc debug riêng.

### 21.2 Parallel execution

Test có thể chạy song song nếu fixture read-only, output tạm riêng và compiler/runtime không dùng shared mutable state.

### 21.3 Incremental selection

CI có thể chọn suite liên quan khi thay đổi lexer, grammar hoặc generator, nhưng vẫn cần full suite ở checkpoint thích hợp.

### 21.4 Giới hạn kích thước

Golden file quá lớn khó review và làm repository nặng. Chia fixture theo behavior hoặc dùng structured assertion cho phần không cần snapshot toàn bộ.

### 21.5 Cache

Nếu test cache output, cache key phải bao gồm input, compiler version, options và dependency ảnh hưởng kết quả.

## 22. Golden test trong CI/CD

Golden test thường chạy tự động trong pull request và pipeline phát hành.

~~~text
Pull request
    |
    v
Compile test sources
    |
    v
Run golden suite
    |
    v
Compare expected / actual
    |
    +---- match ----> Pass
    |
    +---- mismatch --> Publish diff and fail
~~~

### 22.1 CI không tự approve

Pipeline nên báo mismatch và lưu diff/artifact. Việc cập nhật baseline cần thay đổi code được review.

### 22.2 Môi trường cố định

Pin JDK, locale, timezone và các dependency có ảnh hưởng output. Nếu test được thiết kế portable, vẫn cần chạy trên các hệ điều hành được hỗ trợ.

### 22.3 Failure artifact

Lưu actual output và diff để developer tải về. Tránh in toàn bộ dữ liệu nhạy cảm vào log CI.

### 22.4 Pull request review

Reviewer cần xem expected changes cùng source changes. Diff golden là một phần của thay đổi behavior.

### 22.5 Release gate

Golden suite có thể là một release gate cho compiler, plugin API hoặc runtime behavior. Cần kết hợp các loại test khác để kiểm tra correctness và security.

## 23. Bảo mật và dữ liệu trong golden fixture

Golden file được lưu trong repository và có thể tồn tại lâu.

### 23.1 Không dùng dữ liệu production

Tạo dữ liệu giả có cùng cấu trúc và edge case. Không copy database dump hoặc payload khách hàng vào fixture.

### 23.2 Secret scanning

Golden file vẫn cần được kiểm tra token, password, private key và credential.

### 23.3 Path và environment

Không lưu username, home directory hoặc hostname thật nếu không cần. Dùng workspace tương đối và placeholder.

### 23.4 Executable output

Generated code trong fixture không nên được thực thi tự động chỉ vì nó nằm trong test resource. Test harness cần kiểm soát artifact nào được compile hoặc chạy.

### 23.5 Untrusted fixture

Nếu fixture do contributor bên ngoài cung cấp, xử lý như input không tin cậy. Giới hạn tài nguyên và không cho test truy cập hệ thống thật.

## 24. Những sai lầm thường gặp

### Auto-approve mọi snapshot mismatch

Regression bị biến thành baseline mới mà không ai nhận ra.

**Cách khắc phục:** review diff và yêu cầu lý do cho thay đổi lớn.

### Snapshot toàn bộ object nội bộ

Refactor implementation vô hại làm hàng trăm golden file thay đổi.

**Cách khắc phục:** chọn boundary và output ổn định có ý nghĩa với consumer.

### Không kiểm soát nondeterminism

Test fail ngẫu nhiên do timestamp, path, map order hoặc thread scheduling.

**Cách khắc phục:** inject clock/random, canonicalize và cô lập môi trường theo contract.

### Normalize quá mức

Comparator bỏ qua khác biệt quan trọng như thứ tự diagnostics hoặc source range.

**Cách khắc phục:** chỉ normalize những phần được xác định là không có ý nghĩa.

### Một fixture kiểm tra quá nhiều thứ

Diff lớn và khó xác định nguyên nhân.

**Cách khắc phục:** tách fixture theo phase hoặc behavior.

### Golden pass nhưng logic sai

Baseline cũ có thể chứa bug và test chỉ xác nhận output vẫn giống.

**Cách khắc phục:** bổ sung unit, property và integration assertions cho invariant.

### Không kiểm tra file thừa hoặc thiếu

Generator tạo đúng nội dung một file nhưng vô tình bỏ một artifact khác.

**Cách khắc phục:** so sánh cả tập relative path và nội dung.

### Đưa dữ liệu thật vào fixture

Repository có thể làm lộ dữ liệu cá nhân hoặc secret.

**Cách khắc phục:** dùng synthetic data và secret scanning.

## 25. Quy trình thiết kế golden test cho DSL

Khi thêm một golden test, có thể thực hiện:

1. **Chọn behavior:** xác định lexer, parser, semantic, diagnostics, formatter, generator hay runtime cần bảo vệ.
2. **Tạo input nhỏ:** chỉ chứa cú pháp hoặc tình huống cần kiểm tra.
3. **Xác định output contract:** text, AST, diagnostic, artifact set hoặc decision.
4. **Kiểm soát môi trường:** clock, locale, timezone, path, random và dependency.
5. **Tạo baseline:** chạy implementation đúng và lưu expected output.
6. **Review baseline:** xác nhận output phản ánh đặc tả và behavior mong muốn.
7. **Viết comparator:** exact, line-based, structured hoặc semantic phù hợp.
8. **Kiểm tra failure message:** diff phải chỉ rõ fixture và phần khác.
9. **Thêm regression cases:** bao gồm boundary và bug đã biết.
10. **Chạy trong CI:** không tự động approve baseline.
11. **Review thay đổi:** xem golden diff cùng code diff.
12. **Bảo trì:** xóa fixture chết, chia fixture quá lớn và ghi lý do khi baseline thay đổi.

## 26. Ví dụ tổng hợp: golden test cho compiler DSL

Giả sử compiler có thể parse, validate và generate Java source.

### 26.1 Fixture

~~~text
golden/
  discount-policy/
    input.dsl
    expected.ast.txt
    expected.diagnostics.txt
    expected.java
~~~

Input:

~~~text
policy "Discount"
  input order: Order
  when order.total >= 1000000
  then order.discount = 0.05
~~~

### 26.2 Test pipeline

~~~java
@Test
void compilesDiscountPolicy() throws Exception {
    String source = fixture("discount-policy/input.dsl");

    CompilationResult result = compiler.compile(source);

    assertEquals(
        fixture("discount-policy/expected.ast.txt"),
        AstPrinter.print(result.ast())
    );

    assertEquals(
        fixture("discount-policy/expected.diagnostics.txt"),
        DiagnosticPrinter.print(result.diagnostics())
    );

    assertEquals(
        fixture("discount-policy/expected.java"),
        result.generatedFiles().get("Discount.java")
    );
}
~~~

### 26.3 Determinism

Compiler nhận configuration và clock cố định. Generator sắp xếp import và declaration theo quy tắc đã công bố. File path trong diagnostics được biểu diễn tương đối.

### 26.4 Khi grammar thay đổi

Nếu AST thay đổi có chủ ý, reviewer xem expected.ast.txt. Nếu generated Java thay đổi ngoài dự kiến, test chỉ ra artifact và dòng khác. Không cập nhật tất cả expected files trước khi hiểu nguyên nhân.

### 26.5 Kiểm tra bổ sung

Compile generated Java bằng compiler thật và chạy unit test cho behavior của policy. Golden comparison kiểm tra output text; integration test xác nhận artifact có thể dùng được.

## 27. Câu hỏi tự kiểm tra

1. Golden test là gì và baseline có vai trò gì?
2. Golden test khác unit test và integration test như thế nào?
3. Những phase nào trong DSL compiler phù hợp với golden test?
4. Vì sao baseline phải được review và version hóa?
5. Khi nào nên so sánh exact text và khi nào nên so sánh cấu trúc?
6. Nondeterminism thường đến từ những nguồn nào?
7. Clock injection và random seed giúp test ổn định ra sao?
8. Vì sao normalization phải có chủ đích?
9. Golden test cho source range cần quy định những convention nào?
10. Làm sao snapshot generated code nhiều file?
11. Vì sao formatter golden test cần giữ whitespace?
12. Golden test runtime cần xử lý event ordering và side effect như thế nào?
13. Quy trình cập nhật golden file nên gồm những bước nào?
14. Vì sao CI không nên tự động approve snapshot mới?
15. Golden test có chứng minh baseline là behavior đúng tuyệt đối không?
16. Làm sao giữ suite nhanh khi số lượng fixture tăng?
17. Vì sao không nên dùng dữ liệu production trong golden file?
18. Những trường hợp nào cần unit/property/integration test bổ sung?
19. Làm sao phân biệt regression với thay đổi behavior có chủ ý?
20. Reviewer cần xem những gì khi một pull request cập nhật golden baseline?

Golden test giúp lưu lại và bảo vệ những kết quả quan trọng của DSL qua nhiều lần thay đổi. Khi fixture nhỏ, baseline được duyệt, output deterministic và diff dễ đọc, kỹ thuật này phát hiện regression hiệu quả ở lexer, parser, semantic analysis, diagnostics, formatter, generator và runtime. Baseline cần được xem là một phần của contract kiểm thử, không phải file được cập nhật tự động để làm test xanh.

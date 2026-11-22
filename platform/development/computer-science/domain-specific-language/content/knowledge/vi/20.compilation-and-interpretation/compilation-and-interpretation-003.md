# Pipeline xử lý

## Pipeline xử lý trong DSL là gì?

Một ngôn ngữ chuyên miền (domain-specific language, DSL) thường bắt đầu bằng văn bản do người dùng viết, nhưng hệ thống không thể thực thi trực tiếp chuỗi ký tự đó như một chương trình đã được hiểu đầy đủ. Hệ thống cần đi qua nhiều bước để nhận diện token, phân tích cấu trúc, kiểm tra ý nghĩa, chuyển đổi biểu diễn và cuối cùng thực thi hoặc sinh ra đầu ra phù hợp.

Chuỗi các bước có tổ chức này được gọi là **pipeline xử lý** (processing pipeline). Trong bối cảnh biên dịch và thông dịch, pipeline mô tả cách một chương trình DSL đi từ mã nguồn đến kết quả thực thi, mã đích, cấu hình, truy vấn hoặc một dạng sản phẩm khác.

Một pipeline điển hình có thể gồm:

1. Tiếp nhận nguồn và cấu hình biên dịch.
2. Tiền xử lý hoặc nạp các tài nguyên phụ thuộc.
3. Phân tích từ vựng (lexing).
4. Phân tích cú pháp (parsing).
5. Xây dựng AST hoặc CST.
6. Phân tích ngữ nghĩa và phân giải tên.
7. Kiểm tra kiểu và các ràng buộc miền.
8. Chuyển sang biểu diễn trung gian (IR).
9. Phân tích và tối ưu hóa.
10. Sinh mã đích hoặc chuẩn bị biểu diễn cho interpreter.
11. Liên kết thư viện và tài nguyên cần thiết.
12. Thực thi, đánh giá hoặc triển khai kết quả.
13. Thu thập diagnostics, metadata và thông tin truy vết.

Không phải DSL nào cũng cần tất cả các giai đoạn. Một DSL cấu hình nhỏ có thể chỉ cần parse, validate và tạo object cấu hình. Một DSL truy vấn có thể parse thành query plan rồi gửi đến database engine. Một DSL nghiệp vụ có thể biên dịch thành bytecode hoặc gọi các dịch vụ runtime. Pipeline cần phản ánh mục tiêu thực tế của ngôn ngữ.

Điều quan trọng là mỗi giai đoạn có đầu vào, đầu ra và trách nhiệm rõ ràng. Nhờ đó, lỗi có thể được xác định ở đúng tầng, các thành phần có thể được kiểm thử độc lập và hệ thống có thể thay đổi một bước mà không phải viết lại toàn bộ frontend hoặc backend.

## Bức tranh tổng thể của pipeline

Sơ đồ khái quát:

~~~text
       DSL source files
              |
              v
     Source manager / loader
              |
              v
       Preprocessing
              |
              v
            Lexer
              |
              v
            Parser
              |
              v
         AST / CST
              |
              v
      Semantic analysis
       /      |       \
      v       v        v
   Resolve  Type    Domain rules
    names  checking  validation
       \      |       /
              v
        Typed AST / HIR
              |
              v
     Intermediate Representation
              |
              v
       Optimization passes
              |
              v
       Lowered IR / Plan
              |
              v
      Backend / Code generation
              |
              v
     Artifact / Executable / Plan
              |
              v
       Runtime / Deployment
              |
              v
        Result and diagnostics
~~~

Sơ đồ trên thể hiện một pipeline biên dịch có nhiều tầng. Với interpreter, một số bước sau semantic analysis có thể được thay bằng evaluator đọc AST hoặc IR. Với DSL cấu hình, backend có thể là serializer tạo JSON, YAML hoặc object graph. Với DSL truy vấn, đầu ra có thể là query plan thay vì executable độc lập.

Một cách nhìn hữu ích là phân chia pipeline thành ba vùng:

- **Frontend:** hiểu văn bản DSL và xác định chương trình có cấu trúc, tên và kiểu hợp lệ hay không.
- **Middle-end:** chuyển chương trình sang dạng trung gian, phân tích phụ thuộc và tối ưu hóa theo các quy tắc không phụ thuộc một nền tảng cụ thể.
- **Backend và runtime:** biến biểu diễn đã xử lý thành đầu ra cụ thể hoặc thực thi nó trong môi trường mục tiêu.

Ranh giới này giúp tách cú pháp của ngôn ngữ khỏi cách chương trình được chạy. Một DSL có thể giữ nguyên frontend và middle-end nhưng có nhiều backend cho JavaScript, JVM bytecode, SQL hoặc một engine riêng.

## Đầu vào của pipeline: source, project và context

Pipeline không phải lúc nào cũng nhận một chuỗi đơn. Một chương trình DSL có thể gồm nhiều tệp, module, thư viện, tham số biên dịch, cấu hình môi trường và phiên bản ngôn ngữ.

Source manager hoặc project loader chịu trách nhiệm thu thập những đầu vào đó và tạo một ngữ cảnh nhất quán cho các giai đoạn sau.

Các loại đầu vào thường gặp:

- Một hoặc nhiều tệp DSL.
- Tên module và namespace.
- Các tệp được import hoặc include.
- Phiên bản grammar hoặc language level.
- Thư viện kiểu và khai báo có sẵn.
- Cấu hình compiler hoặc interpreter.
- Feature flags và tùy chọn tương thích.
- Biến môi trường được cho phép.
- Tài nguyên schema, catalog hoặc metadata miền.
- Thông tin source location và encoding.

### Source manager

Source manager quản lý nội dung nguồn và định danh của từng tài liệu. Nó có thể cung cấp API đọc đoạn văn bản, ánh xạ offset sang dòng/cột và truy xuất tên tệp trong diagnostics.

Ví dụ mô hình:

~~~text
SourceFile
  id
  uri
  text
  encoding
  version
  lineIndex
~~~

Khi parser tạo node AST, node có thể giữ source span tham chiếu đến SourceFile. Nhờ đó, semantic analyzer có thể báo lỗi tại vị trí gốc và IDE có thể highlight chính xác đoạn mã.

### Nạp module và import

Nếu DSL hỗ trợ module, pipeline cần tìm và nạp các module phụ thuộc. Việc này có thể diễn ra trước parsing toàn bộ, hoặc được điều phối sau khi parser nhận diện các khai báo import.

Ví dụ:

~~~text
MODULE checkout
IMPORT common.pricing
IMPORT common.customer

RULE "VIP discount"
WHEN customer.isVip
THEN pricing.applyDiscount(order)
~~~

Pipeline cần xác định module common.pricing và common.customer, kiểm tra chúng có tồn tại, đọc đúng phiên bản và đưa khai báo vào môi trường phân giải tên.

Phụ thuộc module có thể tạo đồ thị. Nếu có chu trình import, hệ thống cần quy định cho phép hay từ chối, và nếu cho phép thì cách xử lý khai báo chưa hoàn tất. Không nên để thứ tự tải tệp vô tình quyết định kết quả phân giải.

### Cấu hình và khả năng tái lập

Cùng một source có thể tạo kết quả khác nhau nếu compiler dùng phiên bản grammar, thư viện, schema hoặc cấu hình khác nhau. Một pipeline có thể tái lập cần ghi lại những đầu vào có ảnh hưởng đến kết quả.

Một compilation context có thể chứa:

~~~text
CompilationContext
  languageVersion
  compilerVersion
  targetPlatform
  modulePath
  dependencyVersions
  featureFlags
  unitCatalogVersion
  schemaVersion
  buildOptions
~~~

Thông tin này hỗ trợ cache, debug, audit và tái tạo lỗi. Nếu kết quả biên dịch được triển khai ở nhiều môi trường, cần phân biệt cấu hình lúc build với cấu hình runtime.

## Tiền xử lý (preprocessing)

Một số DSL có giai đoạn tiền xử lý trước lexer hoặc trước parser. Preprocessor có thể xử lý include, macro, directive, điều kiện biên dịch, biến thay thế hoặc tạo nguồn tổng hợp.

Ví dụ:

~~~text
INCLUDE "common/types.dsl"

IF_FEATURE "shipping"
  INCLUDE "shipping/rules.dsl"
END_FEATURE
~~~

Preprocessing có thể giúp tái sử dụng định nghĩa, nhưng cũng làm source mapping và diagnostics phức tạp hơn. Khi một lỗi xuất hiện trong văn bản sau mở rộng macro, người dùng cần biết lỗi bắt nguồn từ vị trí nào trong tệp gốc.

Một preprocessor tốt cần:

- Xác định rõ cú pháp directive.
- Giới hạn đường dẫn được include.
- Phát hiện include cycle.
- Kiểm soát macro expansion và giới hạn đệ quy.
- Giữ mapping từ văn bản mở rộng về nguồn gốc.
- Ghi nhận cấu hình feature đã dùng.
- Trả diagnostics có source location.
- Tránh thực thi nội dung tùy ý trong lúc tiền xử lý.

Không phải DSL nào cũng cần preprocessor. Nếu import và macro có thể được xử lý ở tầng module hoặc AST, có thể giữ pipeline đơn giản hơn. Cần chọn cơ chế dựa trên nhu cầu tái sử dụng và khả năng truy vết.

## Phân tích từ vựng (lexing)

Lexer đọc ký tự nguồn và tạo token stream. Token đại diện cho từ khóa, identifier, literal, toán tử, dấu phân cách hoặc ký hiệu đặc biệt.

Ví dụ nguồn:

~~~text
RULE "VIP"
WHEN order.total >= 1000
THEN discount.rate = 10
~~~

Token stream minh họa:

~~~text
RULE_KEYWORD
STRING_LITERAL("VIP")
NEWLINE
WHEN_KEYWORD
IDENTIFIER("order")
DOT
IDENTIFIER("total")
GREATER_EQUAL
INTEGER_LITERAL(1000)
NEWLINE
THEN_KEYWORD
IDENTIFIER("discount")
DOT
IDENTIFIER("rate")
ASSIGN
INTEGER_LITERAL(10)
EOF
~~~

Lexer chịu trách nhiệm nhận diện token theo lexical grammar, khớp dài nhất, xử lý whitespace/comment và giữ source span. Nó không nên tự quyết định các ràng buộc nghiệp vụ như tên biến có tồn tại hay biểu thức có đúng kiểu không.

### Đầu ra của lexer

Một token thường có:

- Token kind.
- Lexeme gốc hoặc giá trị đã giải mã.
- Start/end offset.
- Source ID.
- Channel hoặc cờ trivia nếu cần.
- Thông tin lỗi nếu token không hợp lệ.

Lexer có thể bỏ qua whitespace và comment nếu chúng không có ý nghĩa cú pháp. Nếu formatter hoặc IDE cần giữ nguyên nguồn, lexer có thể lưu trivia hoặc tạo token trên channel riêng.

### Lỗi từ vựng

Ví dụ:

~~~text
RULE "VIP
WHEN order.total >= @
~~~

Lexer có thể báo string chưa đóng và ký tự @ không hợp lệ. Pipeline nên lưu diagnostics và quyết định có tiếp tục parse phần còn lại hay không. Với IDE, tiếp tục sau lỗi thường hữu ích; với một số compiler batch, có thể dừng sớm nếu token stream không đủ tin cậy.

## Phân tích cú pháp (parsing)

Parser nhận token stream và áp dụng grammar để xác định cấu trúc chương trình. Nó thường dùng một start rule như program, module hoặc expression.

Ví dụ grammar:

~~~ebnf
program = { declaration } ;
declaration = ruleDeclaration | constantDeclaration ;

ruleDeclaration = "RULE", string,
                  "WHEN", expression,
                  "THEN", action,
                  [ "ELSE", action ] ;

constantDeclaration = "DEFINE", identifier, "=", literal ;
~~~

Parser xác định token nào thuộc từng production, kiểm tra thứ tự và tạo cây cú pháp. Với grammar có precedence, parser phải nhóm toán tử đúng quy tắc. Với danh sách, parser cần giữ thứ tự và xử lý separator. Với cấu trúc lồng, parser phải ghép cặp delimiter chính xác.

### AST và CST

Concrete Syntax Tree (CST) giữ cấu trúc gần với token và nguồn gốc cú pháp. Abstract Syntax Tree (AST) giữ các cấu trúc có ý nghĩa cho phân tích ngữ nghĩa và thực thi.

Ví dụ, biểu thức:

~~~text
(a + b) * c
~~~

CST có thể giữ cả dấu ngoặc. AST có thể thể hiện:

~~~text
Multiply
  Add
    Identifier(a)
    Identifier(b)
  Identifier(c)
~~~

AST thường thuận tiện cho semantic analysis và code generation. CST hữu ích cho formatter, refactoring và công cụ cần bảo toàn chi tiết văn bản.

### Parser diagnostics

Parser cần báo lỗi khi token stream không khớp grammar. Diagnostics có thể chứa token mong đợi, token thực tế, source span và gợi ý sửa.

Ví dụ:

~~~text
Expected an expression after '>='.
Found NEWLINE at rules.dsl:4:21.
~~~

Một parser cho IDE có thể tạo cây một phần và phục hồi để tiếp tục phân tích. Một compiler triển khai có thể yêu cầu parse hoàn chỉnh và tiêu thụ hết token đến EOF.

## Phân tích ngữ nghĩa (semantic analysis)

Cú pháp đúng chưa đảm bảo chương trình hợp lệ. Semantic analysis xác định ý nghĩa của các node AST và kiểm tra các ràng buộc không thể biểu đạt đầy đủ bằng grammar.

Các công việc thường gồm:

- Xây dựng scope và symbol table.
- Phân giải tên biến, hàm, module, kiểu và thuộc tính.
- Kiểm tra visibility và quyền truy cập.
- Kiểm tra kiểu dữ liệu và tương thích.
- Kiểm tra số lượng và kiểu tham số.
- Kiểm tra đơn vị đo hoặc dimension.
- Xác nhận các ràng buộc miền.
- Phân tích control flow và tính khả đạt nếu cần.
- Phát hiện khai báo trùng hoặc thiếu.
- Kiểm tra phụ thuộc và chu trình theo chính sách ngôn ngữ.

### Symbol table và name resolution

Ví dụ:

~~~text
DEFINE MIN_TOTAL = 1000000

RULE "VIP discount"
WHEN order.total >= MIN_TOTAL
THEN applyDiscount(order)
~~~

Parser có thể tạo IdentifierNode cho MIN_TOTAL và FunctionCallNode cho applyDiscount. Semantic analyzer tìm các tên đó trong scope hiện tại và module được import, sau đó gắn reference đến khai báo tương ứng.

Nếu không tìm thấy MIN_TOTAL, đó là lỗi phân giải tên. Nếu applyDiscount tồn tại nhưng không nhận tham số order, đó có thể là lỗi kiểm tra chữ ký hàm.

### Type checking

Ví dụ:

~~~text
let distance: Length = 12 km
let duration: Time = 30 min
let speed = distance / duration
let invalid = distance + duration
~~~

Type checker có thể suy ra speed có kiểu Velocity và từ chối invalid vì Length không thể cộng với Time.

Với DSL miền, semantic analysis còn có thể kiểm tra đơn vị, quyền, trạng thái nghiệp vụ hoặc schema. Ví dụ, một rule có thể đúng cú pháp và kiểu nhưng không được phép thay đổi thuộc tính đã bị khóa.

### Typed AST

Sau semantic analysis, AST có thể được bổ sung kiểu, symbol reference và metadata:

~~~text
TypedAssignment
  target: PropertySymbol(shipment.fee)
  targetType: Money<VND>
  value:
    TypedLiteral(0)
    inferredType: Money<VND>
~~~

Không nhất thiết phải sửa trực tiếp AST gốc. Một số hệ thống tạo typed AST hoặc HIR riêng để giữ phân biệt giữa cú pháp nguồn và ý nghĩa đã resolve.

## Biểu diễn trung gian (IR)

IR (Intermediate Representation) là dạng biểu diễn chương trình nằm giữa frontend và backend. Nó được thiết kế để dễ phân tích, biến đổi, tối ưu hóa hoặc sinh mã hơn AST nguồn.

AST thường phản ánh cú pháp và các khái niệm người dùng viết. IR thường làm rõ luồng điều khiển, dữ liệu, kiểu, phép toán và các thao tác runtime.

Một DSL có thể có nhiều cấp IR:

- AST: gần với cấu trúc cú pháp nguồn.
- HIR (High-level IR): giữ các khái niệm miền ở mức cao nhưng đã resolve tên và kiểu.
- MIR (Mid-level IR): biểu diễn thao tác và luồng điều khiển ít phụ thuộc cú pháp.
- LIR (Low-level IR): gần với lệnh máy ảo, bytecode hoặc API backend.

Không phải dự án nào cũng cần nhiều tầng. Mỗi IR bổ sung làm tăng chi phí chuyển đổi và bảo trì, nên chỉ tạo khi có lợi ích cụ thể.

### Ví dụ chuyển AST sang IR

Nguồn:

~~~text
RULE "VIP discount"
WHEN order.total >= 1000 AND customer.segment IS "VIP"
THEN discount.rate = 10
~~~

AST có thể gồm RuleNode, AndExpression, ComparisonExpression và AssignmentNode. HIR có thể biểu diễn rõ các symbol đã resolve:

~~~text
Rule
  condition:
    And
      CompareGreaterEqual
        LoadProperty(Order.total)
        Constant(Money(1000, VND))
      CompareEqual
        LoadProperty(Customer.segment)
        Constant(Segment.VIP)
  action:
    StoreProperty(Discount.rate, Constant(10))
~~~

Một IR thấp hơn có thể tách giá trị trung gian:

~~~text
v1 = load_property order.total
v2 = constant 1000 VND
v3 = compare_ge v1, v2
v4 = load_property customer.segment
v5 = constant VIP
v6 = compare_eq v4, v5
v7 = and v3, v6
branch_if_false v7, next_rule
store_property discount.rate, 10
next_rule:
~~~

Ví dụ minh họa cách hạ tầng biểu diễn; cú pháp IR thực tế phụ thuộc engine.

### Thuộc tính của một IR tốt

Một IR phù hợp cần:

- Có mô hình dữ liệu rõ ràng.
- Biểu diễn đầy đủ ngữ nghĩa cần cho backend.
- Có quy tắc kiểm tra tính hợp lệ riêng.
- Giữ source mapping để diagnostics và debug.
- Hỗ trợ các phép biến đổi có thể kiểm chứng.
- Hạn chế phụ thuộc vào một backend cụ thể nếu cần nhiều target.
- Có phiên bản hoặc hợp đồng tương thích khi được lưu cache.

IR không nên chỉ là bản sao AST với tên node khác. Nó cần giải quyết một nhu cầu cụ thể như tối ưu hóa, phân tích phụ thuộc, thực thi trên VM hoặc sinh nhiều dạng đầu ra.

## Các pass trong pipeline

Một pass là một bước xử lý nhận một biểu diễn chương trình, thực hiện một nhiệm vụ xác định và trả về kết quả hoặc diagnostics. Pipeline thường được xây dựng bằng cách ghép nhiều pass theo thứ tự.

Ví dụ:

~~~text
AST
 |
 +--> ResolveImports
 |
 +--> BuildScopes
 |
 +--> ResolveNames
 |
 +--> TypeCheck
 |
 +--> ValidateDomainRules
 |
 +--> LowerToHIR
 |
 +--> SimplifyExpressions
 |
 +--> LowerControlFlow
 |
 +--> GenerateTarget
~~~

Mỗi pass nên có hợp đồng:

- Input representation và các invariant đầu vào.
- Output representation và invariant đầu ra.
- Diagnostics có thể phát sinh.
- Metadata được thêm, thay đổi hoặc loại bỏ.
- Có thể chạy lặp lại an toàn hay không.
- Có phụ thuộc vào target hoặc môi trường không.
- Có thể cache kết quả hay cần dữ liệu runtime.

### Pass phân tích và pass biến đổi

**Analysis pass** đọc chương trình và tạo thông tin phụ trợ mà không nhất thiết thay đổi cấu trúc. Ví dụ, xây call graph, tính kiểu, phát hiện biến không dùng hoặc phân tích control flow.

**Transformation pass** thay đổi biểu diễn chương trình. Ví dụ, hạ một vòng lặp miền thành jump, thay biểu thức hằng bằng giá trị đã tính hoặc chuyển một lời gọi DSL thành lệnh IR.

Có thể tách hai loại để dễ hiểu và dễ kiểm chứng. Nếu một pass vừa phân tích vừa thay đổi cấu trúc, cần mô tả rõ thông tin nào được tính trước và cách nó còn hợp lệ sau biến đổi.

### Thứ tự pass

Thứ tự pass có thể ảnh hưởng kết quả. Chẳng hạn, name resolution phải có đủ module và symbol trước khi type checking có thể xác định kiểu của lời gọi hàm. Constant folding chỉ an toàn khi biết biểu thức không có tác dụng phụ và các phép toán có ngữ nghĩa xác định.

Một pipeline nên biểu diễn phụ thuộc giữa các pass thay vì chỉ sắp xếp theo tên. Nếu pass A yêu cầu invariant do pass B tạo ra, điều đó cần được thể hiện trong cấu hình hoặc API.

## Tối ưu hóa (optimization)

Tối ưu hóa biến đổi chương trình để cải thiện thời gian chạy, bộ nhớ, kích thước đầu ra hoặc chi phí truy vấn mà vẫn giữ ngữ nghĩa theo hợp đồng DSL.

Các kỹ thuật phổ biến:

- Constant folding: tính trước biểu thức hằng.
- Constant propagation: truyền giá trị hằng qua các biến.
- Dead code elimination: loại bỏ phần không thể ảnh hưởng kết quả.
- Common subexpression elimination: dùng lại biểu thức lặp có thể chia sẻ an toàn.
- Inline: thay lời gọi hàm bằng thân hàm khi phù hợp.
- Loop optimization: tối ưu vòng lặp.
- Query optimization: chọn thứ tự join, index hoặc chiến lược truy vấn.
- Rule simplification: đơn giản hóa điều kiện và nhánh.
- Data layout optimization: thay đổi cách tổ chức dữ liệu cho backend.

### Constant folding

Ví dụ:

~~~text
let threshold = 100 * 10
~~~

Nếu phép nhân chỉ dùng literal và không có tác dụng phụ, compiler có thể biến thành:

~~~text
let threshold = 1000
~~~

Với DSL có đơn vị, phép tính trước cần giữ đúng đơn vị và quy tắc làm tròn. Với DSL tài chính, không được dùng phép tính floating-point nếu ngữ nghĩa yêu cầu Decimal chính xác.

### Dead code elimination

Ví dụ:

~~~text
IF FALSE THEN
  performAction()
END
~~~

Nếu điều kiện thực sự là hằng FALSE và việc loại bỏ nhánh không làm thay đổi tác dụng phụ có thể quan sát, compiler có thể loại bỏ action. Nhưng nếu DSL có tracing, audit hoặc yêu cầu giữ nhánh để giải thích quyết định, pass phải tôn trọng những semantics đó.

### Tối ưu hóa phụ thuộc ngữ nghĩa

Không phải biến đổi nào có vẻ tương đương về toán học cũng an toàn trong runtime. Ví dụ, phép cộng số thực có thể không kết hợp do sai số làm tròn. Lời gọi hàm có thể có side effect. Truy vấn có thể phụ thuộc thứ tự kết quả. Một pass chỉ được thực hiện biến đổi khi các điều kiện ngữ nghĩa được chứng minh hoặc được đặc tả cho phép.

### Kiểm chứng pass

Mỗi transformation pass nên có test đầu vào IR và kết quả IR mong đợi. Có thể kiểm tra:

- IR sau biến đổi thỏa invariant.
- Ngữ nghĩa quan sát được được giữ nguyên.
- Source mapping vẫn hữu ích.
- Pass không tạo vòng lặp biến đổi vô hạn.
- Chạy pass nhiều lần có hành vi được xác định.
- Diagnostics không bị mất hoặc gắn sai nguồn.

Các kiểm thử này thuộc quá trình phát triển compiler; chúng không thay thế việc kiểm tra pipeline tổng thể với chương trình DSL thực tế.

## Backend và sinh mã (code generation)

Backend chuyển IR sang dạng đích. Target có thể là:

- Native machine code.
- JVM bytecode.
- JavaScript hoặc WebAssembly.
- Bytecode cho virtual machine riêng.
- SQL hoặc query plan.
- JSON, YAML hoặc cấu hình hệ thống.
- Workflow definition.
- Lệnh gọi API hoặc một execution plan.

Một frontend độc lập backend giúp cùng một DSL có thể hỗ trợ nhiều môi trường. Backend chịu trách nhiệm ánh xạ kiểu, toán tử, control flow, function call và runtime services sang target.

### Mapping kiểu

Ví dụ, kiểu Integer của DSL có thể ánh xạ sang int32, int64 hoặc BigInt tùy target và phạm vi giá trị. Kiểu Money có thể ánh xạ sang Decimal hoặc cấu trúc value object. Kiểu DateTime cần ánh xạ đến API thời gian có quy tắc timezone phù hợp.

Mapping kiểu phải bảo toàn semantics. Nếu target không có kiểu tương đương, backend có thể dùng runtime library hoặc biểu diễn tổng hợp.

### Mapping control flow

Một cấu trúc DSL:

~~~text
IF condition THEN
  actionA()
ELSE
  actionB()
END
~~~

có thể được sinh thành branch trong bytecode, câu lệnh điều kiện trong ngôn ngữ đích hoặc một node trong workflow graph.

Backend cần giữ đúng:

- Điều kiện được đánh giá khi nào.
- Nhánh nào chạy.
- Thứ tự tác dụng phụ.
- Hành vi khi có exception hoặc lỗi.
- Quy tắc return, break và continue nếu có.

### Runtime helper

Một số thao tác DSL không ánh xạ trực tiếp sang lệnh target. Backend có thể sinh lời gọi đến runtime helper:

~~~text
call runtime.compareMoney(valueA, valueB)
call runtime.resolveEntity(entityId)
call runtime.evaluateRule(ruleId, context)
~~~

Runtime helper cần có hợp đồng phiên bản rõ. Artifact được sinh ra phải tương thích với runtime mà nó sẽ chạy.

## Interpreter và pipeline thông dịch

Không phải DSL nào cũng cần sinh executable. Interpreter có thể đánh giá AST hoặc IR trực tiếp.

Một pipeline thông dịch điển hình:

~~~text
Source
  |
Lexer
  |
Parser
  |
AST
  |
Semantic analysis
  |
Typed AST / IR
  |
Evaluator
  |
Runtime context
  |
Result
~~~

Evaluator duyệt các node và thực hiện hành vi tương ứng. Ví dụ, node Add đánh giá hai toán hạng rồi áp dụng phép cộng theo kiểu đã xác định; node If đánh giá condition và chọn nhánh; node FunctionCall tìm implementation rồi gọi với argument values.

### Tree-walk interpreter

Tree-walk interpreter đi trực tiếp qua AST. Nó đơn giản và phù hợp với DSL nhỏ hoặc công cụ thử nghiệm.

Ưu điểm:

- Ít bước hạ tầng.
- Dễ gắn diagnostics vào node.
- Dễ triển khai ban đầu.
- Có thể giữ nguyên cấu trúc miền để debug.

Hạn chế:

- Việc đánh giá có thể chậm do nhiều dispatch và truy cập node.
- Tối ưu hóa khó hơn nếu AST gần cú pháp.
- Cần quản lý scope, call stack và runtime state rõ ràng.
- Node AST có thể chứa chi tiết không cần cho execution.

### Interpreter trên IR hoặc bytecode VM

Một interpreter khác có thể hạ AST sang IR hoặc bytecode rồi chạy trên virtual machine. VM dùng instruction set và runtime stack hoặc register model.

Ví dụ bytecode giả định:

~~~text
LOAD_PROPERTY order.total
PUSH_CONST 1000
COMPARE_GE
JUMP_IF_FALSE L1
PUSH_CONST 10
STORE_PROPERTY discount.rate
JUMP L2
L1:
PUSH_CONST 0
STORE_PROPERTY discount.rate
L2:
~~~

Cách này giúp tách frontend khỏi evaluator và hỗ trợ tối ưu hóa ở IR. Nó cũng tạo một ranh giới rõ cho sandbox, resource limit và tracing.

## Runtime và môi trường thực thi

Runtime cung cấp các dịch vụ mà chương trình DSL cần khi chạy. Tùy ngôn ngữ, runtime có thể bao gồm:

- Quản lý biến và scope.
- Function registry và module loader.
- Object model và property access.
- Built-in functions.
- Kiểu dữ liệu và phép toán miền.
- I/O và kết nối dịch vụ.
- Transaction hoặc workflow state.
- Exception và error handling.
- Logging, tracing và metrics.
- Resource limits và cancellation.
- Permission checks và sandbox.

Runtime context có thể chứa:

~~~text
RuntimeContext
  inputData
  variables
  functionRegistry
  moduleRegistry
  services
  permissions
  clock
  locale
  cancellationToken
  resourceBudget
~~~

Không nên để DSL truy cập trực tiếp toàn bộ process hoặc hệ điều hành nếu miền không cần. Các khả năng runtime nên được cấp qua API rõ ràng để kiểm soát quyền và làm cho chương trình dễ kiểm thử.

### Runtime error và compile-time error

Compile-time error được phát hiện trước khi thực thi, chẳng hạn cú pháp sai, tên không tồn tại hoặc kiểu không tương thích. Runtime error xuất hiện khi chương trình chạy, chẳng hạn dữ liệu thiếu, timeout, service unavailable hoặc chia cho zero nếu điều kiện đó phụ thuộc dữ liệu.

Một pipeline tốt phân loại lỗi đúng thời điểm. Không nên trì hoãn lỗi có thể phát hiện tĩnh đến runtime nếu điều đó làm tăng rủi ro. Ngược lại, không nên giả vờ biết giá trị dữ liệu runtime khi compile-time không có đủ thông tin.

## Pipeline cho các loại DSL khác nhau

Pipeline tổng quát cần được điều chỉnh theo mục đích của ngôn ngữ.

### DSL cấu hình

DSL cấu hình thường biến văn bản thành object model hoặc cấu hình chuẩn hóa:

~~~text
Source
  -> Lexer/Parser
  -> Configuration AST
  -> Schema validation
  -> Default resolution
  -> Environment binding
  -> JSON/Object/Deployment config
~~~

Các bước quan trọng:

- Kiểm tra trường bắt buộc và kiểu dữ liệu.
- Áp dụng giá trị mặc định.
- Resolve tham chiếu đến secret, resource hoặc module.
- Kiểm tra xung đột giữa các cấu hình.
- Phân biệt cấu hình build-time và runtime.
- Sinh output ổn định để dễ review và cache.

Một DSL cấu hình có thể không cần IR tối ưu hóa hay bytecode. Backend có thể chỉ serialize mô hình đã validate.

### DSL truy vấn

DSL truy vấn có thể chuyển query thành logical plan rồi physical plan:

~~~text
Query source
  -> Parse
  -> Resolve tables and fields
  -> Type check
  -> Logical query plan
  -> Query optimization
  -> Physical plan
  -> Database execution
~~~

Logical plan mô tả ý định truy vấn, chẳng hạn scan, filter, project và join. Optimizer chọn thứ tự join, push filter xuống gần nguồn dữ liệu hoặc chọn index. Physical plan chỉ rõ cách thực thi trên engine cụ thể.

Cần giữ semantics của null, collation, timezone, transaction và ordering. Một tối ưu hóa thay đổi kết quả hoặc thứ tự được cam kết là lỗi compiler.

### DSL quy tắc nghiệp vụ

DSL rule engine thường biên dịch rule thành decision tree, condition graph hoặc rule table:

~~~text
Rule source
  -> Parse
  -> Resolve domain fields
  -> Type and policy validation
  -> Rule IR
  -> Rule normalization
  -> Decision structure
  -> Rule runtime
~~~

Các bước có thể bao gồm phát hiện rule trùng, xếp thứ tự ưu tiên, kiểm tra xung đột, xây index điều kiện và chuẩn bị context dữ liệu. Runtime cần xác định rule được đánh giá tuần tự, theo nhóm ưu tiên hay theo một chiến lược khác.

### DSL workflow

Workflow DSL có thể chuyển thành graph gồm node và edge:

~~~text
Workflow source
  -> Parse
  -> Validate node types
  -> Resolve services
  -> Build workflow graph
  -> Check reachability and cycles
  -> Lower to orchestration plan
  -> Deploy
  -> Orchestrator runtime
~~~

Pipeline cần kiểm tra điểm bắt đầu, điểm kết thúc, nhánh, vòng lặp, retry, timeout và các trạng thái lỗi. Một workflow có thể được biên dịch thành cấu hình cho orchestration engine thay vì mã máy.

### DSL template hoặc sinh mã

DSL template có thể phân tích template, resolve biến và sinh văn bản hoặc mã nguồn:

~~~text
Template
  -> Parse template blocks
  -> Resolve variables and helpers
  -> Validate context
  -> Render
  -> Validate generated output
~~~

Với loại này, output có thể là HTML, SQL, source code hoặc tài liệu. Cần escape đúng theo ngữ cảnh đích và kiểm soát việc đưa dữ liệu không tin cậy vào mã được sinh.

## Quản lý lỗi xuyên suốt pipeline

Lỗi có thể xuất hiện ở mọi giai đoạn. Nếu pipeline chỉ trả một chuỗi lỗi chung, người dùng khó biết cần sửa nguồn, cấu hình, dependency hay môi trường runtime.

Một mô hình diagnostic có thể chứa:

~~~text
Diagnostic
  code
  severity
  message
  primaryLocation
  relatedLocations
  stage
  notes
  suggestedFixes
~~~

Ví dụ phân loại:

| Giai đoạn | Ví dụ lỗi |
|---|---|
| Source loading | Tệp không tồn tại, encoding không hỗ trợ |
| Preprocessing | Include cycle, macro expansion vượt giới hạn |
| Lexing | Ký tự không hợp lệ, string chưa đóng |
| Parsing | Thiếu dấu đóng ngoặc, token sai vị trí |
| Name resolution | Identifier hoặc function không tồn tại |
| Type checking | Không tương thích kiểu hoặc đơn vị |
| Domain validation | Rule vi phạm ràng buộc miền |
| Lowering | Cấu trúc không hỗ trợ trong IR |
| Optimization | Invariant pass bị vi phạm |
| Code generation | Target không hỗ trợ một tính năng |
| Linking | Thiếu runtime symbol hoặc dependency |
| Runtime | Timeout, dữ liệu sai, service failure |

### Error propagation

Mỗi pass cần quyết định lỗi nào làm pipeline dừng. Một số lỗi khiến các bước sau không thể chạy an toàn; một số cảnh báo vẫn cho phép tạo output.

Ví dụ:

- Lỗi lexer nghiêm trọng có thể ngăn parser nhận token stream đáng tin cậy.
- Lỗi parse có thể cho phép IDE tiếp tục bằng AST một phần.
- Lỗi unresolved symbol thường ngăn code generation.
- Warning về biến không dùng có thể không ngăn biên dịch.
- Runtime service failure có thể được xử lý bởi chương trình theo chính sách exception.

Không nên bỏ diagnostics ở giữa pipeline. Nếu một pass biến đổi node, source mapping và related locations cần được cập nhật hoặc giữ lại.

### Fail-fast và error accumulation

Fail-fast dừng ở lỗi đầu tiên có thể giúp compiler đơn giản và tránh phân tích trên dữ liệu hỏng. Error accumulation cố gắng thu thập nhiều lỗi trong một lần chạy, hữu ích cho IDE và trải nghiệm soạn thảo.

Có thể dùng chính sách theo chế độ:

- Editor mode: ưu tiên partial result và nhiều diagnostics.
- Build mode: thu thập đủ lỗi độc lập nhưng không tạo artifact khi có lỗi nghiêm trọng.
- Deploy mode: yêu cầu mọi validation bắt buộc thành công.
- Runtime: xử lý lỗi theo control flow và chính sách dịch vụ.

Các chế độ này nên dùng chung định dạng diagnostic để giao diện và công cụ có thể xử lý nhất quán.

## Source mapping và khả năng truy vết

Khi chương trình đi qua nhiều phép biến đổi, node trong IR hoặc mã đích có thể không còn tương ứng trực tiếp với một đoạn source. Tuy nhiên, người dùng vẫn cần biết kết quả được tạo từ đâu.

Source mapping gắn output hoặc node trung gian với source span gốc. Nó hỗ trợ:

- Báo lỗi biên dịch tại dòng DSL.
- Debug từ instruction về rule hoặc expression nguồn.
- Trace quyết định của rule engine.
- Hiển thị nguồn tạo ra cấu hình hoặc query.
- Audit và giải thích kết quả.
- Refactoring và navigation trong IDE.

Một node IR có thể lưu source origin:

~~~text
IRInstruction
  opcode
  operands
  sourceOrigin
  generatedFrom
~~~

Một phép biến đổi có thể gộp nhiều node nguồn thành một instruction, hoặc tạo nhiều instruction từ một node. Mapping có thể là một-nhiều hoặc nhiều-một, không nhất thiết là một span đơn.

Nếu preprocessor hoặc macro expansion được dùng, source mapping nên giữ cả vị trí mở rộng và vị trí định nghĩa để người dùng có thể điều hướng đến nơi cần sửa.

## Cache và incremental compilation

Với project lớn, chạy lại toàn bộ pipeline sau mỗi thay đổi có thể tốn thời gian. Cache và incremental compilation chỉ xử lý những phần bị ảnh hưởng khi có thể chứng minh kết quả cũ vẫn hợp lệ.

### Cache theo đầu vào

Một cache key có thể phụ thuộc vào:

- Nội dung source.
- Phiên bản ngôn ngữ và compiler.
- Cấu hình build.
- Phiên bản dependency.
- Schema và catalog đơn vị.
- Target backend.
- Feature flags.
- Kết quả của các module được tham chiếu.

Nếu bất kỳ đầu vào ngữ nghĩa nào thay đổi, cache có thể không còn hợp lệ. Chỉ hash source file là chưa đủ nếu chương trình phụ thuộc vào schema hoặc thư viện bên ngoài.

### Incremental pipeline

Một pipeline gia tăng có thể hoạt động như sau:

~~~text
File changed
    |
    v
Find affected source units
    |
    v
Re-lex changed regions
    |
    v
Re-parse affected modules
    |
    v
Invalidate dependent semantic results
    |
    v
Re-run required analysis passes
    |
    v
Rebuild affected IR and artifacts
~~~

Nếu một khai báo public thay đổi, các module tham chiếu đến nó có thể cần phân tích lại. Nếu chỉ thay đổi literal trong một rule độc lập, có thể chỉ cần cập nhật phần IR tương ứng.

### Dependency graph và invalidation

Incremental compilation cần đồ thị phụ thuộc giữa module, symbol, type, resource và pass result. Khi một node thay đổi, hệ thống tìm các kết quả phụ thuộc trực tiếp hoặc gián tiếp để invalidation.

Một cache sai có thể nghiêm trọng hơn không có cache vì tạo output cũ mà không báo lỗi. Cần test rằng thay đổi ở dependency, compiler option hoặc schema làm invalidation đúng.

## Tính xác định và khả năng tái lập

Một pipeline xác định (deterministic) tạo cùng kết quả từ cùng đầu vào và cùng cấu hình. Tính chất này quan trọng cho build reproducible, cache, audit và debug.

Các nguồn gây không xác định có thể gồm:

- Duyệt map hoặc set không bảo toàn thứ tự.
- Thời gian hệ thống được đọc ngầm.
- Random number không có seed cố định.
- Môi trường hoặc locale khác nhau.
- Dependency không khóa phiên bản.
- Query hoặc service bên ngoài thay đổi dữ liệu.
- Thứ tự thực thi song song không được quy định.
- ID được sinh ngẫu nhiên trong artifact.

Nếu DSL cho phép dùng thời gian, random hoặc dữ liệu ngoài, cần đưa chúng vào runtime context rõ ràng. Một chế độ build tái lập có thể yêu cầu seed, clock giả lập và dependency lock.

Không phải mọi kết quả runtime đều phải giống nhau; một rule có thể phụ thuộc dữ liệu đơn hàng thực tế. Nhưng phần biên dịch từ cùng source và cùng context build nên có tính xác định theo hợp đồng.

## Thực thi song song và pipeline concurrency

Một số giai đoạn có thể chạy song song khi không phụ thuộc lẫn nhau. Ví dụ, nhiều module độc lập có thể được lex và parse cùng lúc; nhiều pass analysis trên các module khác nhau có thể chạy đồng thời.

Tuy nhiên, song song hóa cần kiểm soát:

- Dependency giữa module và pass.
- Thứ tự diagnostics khi hiển thị.
- Thread safety của symbol table và cache.
- Cập nhật artifact nguyên tử.
- Hủy tác vụ khi build thất bại.
- Giới hạn bộ nhớ và số worker.
- Tính xác định của output.

Không nên chạy song song một pass nếu nó sửa chung AST hoặc global registry mà không có cơ chế đồng bộ. Có thể ưu tiên pass thuần (pure transformation) nhận input bất biến và trả output mới, vì dễ chạy song song và cache hơn.

## Bảo mật pipeline và sandbox

DSL có thể cho phép người dùng không tin cậy viết chương trình. Khi đó, pipeline và runtime cần kiểm soát cả việc phân tích lẫn thực thi.

Một số điểm cần xem xét:

- Giới hạn kích thước source và số token.
- Giới hạn macro expansion và include depth.
- Chống parser recursion hoặc backtracking tốn kém.
- Giới hạn số node IR và độ sâu biểu thức.
- Không tải module tùy ý từ đường dẫn không được phép.
- Không thực thi code trong preprocessing nếu không cần.
- Kiểm soát function registry và API runtime.
- Giới hạn CPU, memory, wall-clock và số lần gọi dịch vụ.
- Hủy thực thi khi vượt ngân sách.
- Kiểm tra quyền trên dữ liệu và hành động.
- Cô lập tenant và context nếu hệ thống đa người dùng.
- Ghi audit cho hành động nhạy cảm.

Sandbox có thể được thực hiện bằng VM giới hạn instruction, process isolation, container hoặc một runtime có capability API. Cách chọn phụ thuộc mức độ tin cậy, yêu cầu hiệu năng và môi trường triển khai.

Pipeline nên từ chối các tính năng không được hỗ trợ trong target thay vì sinh mã thiếu kiểm soát. Nếu một DSL cho phép gọi hàm plugin, việc resolve symbol cần gắn với allowlist hoặc capability được cấp.

## Quan sát pipeline: logging, tracing và metrics

Pipeline nhiều giai đoạn cần khả năng quan sát để xác định bottleneck và lỗi.

Các thông tin hữu ích:

- Thời gian của từng stage và từng pass.
- Số tệp, token, node AST và instruction IR.
- Số diagnostics theo severity và stage.
- Cache hit/miss và lý do invalidation.
- Số module phụ thuộc và độ sâu graph.
- Kích thước artifact.
- Thời gian runtime và số lần gọi service.
- Resource budget còn lại.
- Phiên bản compiler, language và target.

Một compilation trace có thể dùng chung compilation ID xuyên suốt các stage. Khi có lỗi, ID này giúp liên kết log, diagnostic, artifact và runtime execution.

Không nên ghi nội dung nhạy cảm của source hoặc dữ liệu runtime vào log nếu không cần. Có thể ghi hash, source location và mã lỗi thay vì toàn bộ giá trị. Với hệ thống đa tenant, log và trace cần giữ ranh giới dữ liệu.

## Kiểm thử pipeline xử lý

Kiểm thử từng thành phần là cần thiết nhưng không đủ. Pipeline có thể có từng stage hoạt động đúng riêng lẻ mà dữ liệu truyền giữa các stage lại không tương thích.

Các lớp kiểm thử thường gặp:

### Unit test theo stage

Kiểm tra từng thành phần với input/output nhỏ:

- Lexer tạo token mong đợi.
- Parser tạo AST mong đợi.
- Name resolver gắn đúng symbol.
- Type checker suy ra kiểu và báo lỗi đúng.
- Lowering tạo IR hợp lệ.
- Optimization pass giữ invariant.
- Backend sinh artifact đúng.
- Runtime đánh giá instruction theo semantics.

### Contract test giữa các stage

Kiểm tra output của một stage thỏa invariant mà stage kế tiếp yêu cầu. Ví dụ:

- Parser chỉ tạo node thuộc schema AST đã định nghĩa.
- Semantic analysis không để unresolved reference đi vào code generation nếu target không hỗ trợ.
- IR verifier xác nhận mọi operand có kiểu hợp lệ.
- Backend nhận đúng target-specific IR.
- Runtime chỉ chạy artifact tương thích phiên bản.

### End-to-end test

Chạy chương trình DSL hoàn chỉnh từ source đến kết quả:

~~~text
Source fixture
  -> Full pipeline
  -> Execute or render
  -> Compare expected result
~~~

End-to-end test xác nhận các tầng phối hợp đúng. Nên có ví dụ đại diện cho tính năng quan trọng, lỗi ở các giai đoạn khác nhau và cấu hình target khác nhau.

### Golden test cho artifact

Nếu backend sinh code, bytecode hoặc JSON ổn định, golden test có thể so sánh artifact với kết quả mong đợi. Nếu artifact chứa timestamp hoặc ID ngẫu nhiên, cần chuẩn hóa những trường đó hoặc tách chúng khỏi assertion.

Golden test hữu ích cho review thay đổi code generation, nhưng không thay thế test hành vi runtime. Hai artifact khác nhau có thể tương đương về ngữ nghĩa; ngược lại, artifact giống hình thức chưa chắc chạy đúng nếu dependency runtime thay đổi.

### Differential test

Nếu có hai backend hoặc hai cách thực thi cùng DSL, có thể chạy cùng chương trình và so sánh kết quả. Ví dụ, tree-walk interpreter và bytecode VM cần cho kết quả tương đương với cùng runtime context.

Differential testing có thể phát hiện khác biệt semantics giữa các implementation. Cần kiểm soát nguồn dữ liệu, clock, random seed và side effect để phép so sánh có ý nghĩa.

### Regression test

Mỗi lỗi pipeline đã được sửa nên có fixture tái hiện. Fixture nên ghi lại source, compilation options, dependency versions cần thiết và kết quả hoặc diagnostic mong đợi.

## Ví dụ pipeline hoàn chỉnh cho DSL rule engine

Giả sử DSL dùng để mô tả quy tắc giảm giá:

~~~text
DEFINE MIN_TOTAL = 1000000

RULE "VIP discount"
WHEN order.total >= MIN_TOTAL
  AND customer.segment IS "VIP"
THEN discount.rate = 10
ELSE discount.rate = 0
~~~

Pipeline có thể hoạt động như sau.

### 1. Load source

Source manager đọc tệp, xác định encoding, language version và module context. Nó tạo SourceFile để mọi token và node sau đó có thể trỏ về vị trí nguồn.

### 2. Lexing

Lexer tạo token cho DEFINE, RULE, WHEN, THEN, ELSE, identifier, literal, toán tử và newline. Nó giữ source span cho từng token.

### 3. Parsing

Parser áp dụng grammar để tạo AST gồm ConstantDeclaration, RuleDeclaration, AndExpression, ComparisonExpression và AssignmentNode. Parser xác nhận các thành phần bắt buộc có mặt và không còn token thừa.

### 4. Name resolution

Semantic analyzer đăng ký MIN_TOTAL vào symbol table. Các tên order.total, customer.segment, discount.rate được resolve thành property symbol; các kiểu miền được lấy từ schema.

### 5. Type checking và domain validation

Type checker xác nhận order.total và MIN_TOTAL có kiểu Money tương thích, customer.segment có kiểu Segment và discount.rate chấp nhận giá trị số theo schema. Domain validation có thể kiểm tra quyền cập nhật discount.rate và giới hạn tỷ lệ giảm giá.

### 6. Lowering

Typed AST được chuyển thành Rule IR:

~~~text
RuleIR
  id: vip-discount
  condition:
    AND
      GE(Property(Order.total), Constant(MIN_TOTAL))
      EQ(Property(Customer.segment), Constant(VIP))
  then:
    SET(Discount.rate, 10)
  else:
    SET(Discount.rate, 0)
~~~

### 7. Optimization

Compiler có thể thay MIN_TOTAL bằng giá trị hằng đã resolve, chuẩn hóa biểu thức và tạo decision structure. Chỉ được tối ưu khi giữ nguyên semantics và audit requirements của rule engine.

### 8. Backend

Backend sinh rule artifact cho engine mục tiêu, có thể là JSON, bytecode hoặc decision table. Artifact chứa version, rule ID, dependency metadata và source mapping cần thiết.

### 9. Runtime

Khi có order và customer, rule engine nạp artifact, tạo runtime context, đánh giá condition và thực hiện action phù hợp. Runtime kiểm tra quyền, resource budget và xử lý lỗi dịch vụ nếu action cần gọi hệ thống bên ngoài.

### 10. Trace kết quả

Execution trace ghi rule nào được đánh giá, điều kiện con cho kết quả gì và action nào đã chạy. Người vận hành có thể truy ngược từ trace về source span của rule để giải thích quyết định.

Ví dụ này cho thấy pipeline không chỉ là chuỗi hàm chuyển đổi. Nó là hợp đồng xuyên suốt giữa văn bản, mô hình, kiểu, artifact và môi trường thực thi.

## Thiết kế pipeline có thể mở rộng và bảo trì

Một pipeline dễ bảo trì thường có các đặc điểm:

### Stage có trách nhiệm đơn

Mỗi stage thực hiện một nhiệm vụ có thể mô tả rõ. Lexer không resolve tên; parser không kiểm tra quyền; backend không tự đoán kiểu miền. Phân chia này giúp lỗi có địa chỉ và thành phần có thể tái sử dụng.

### Biểu diễn giữa các stage có hợp đồng

Mỗi representation cần schema và invariant. Ví dụ, Typed AST phải có reference đã resolve ở những vị trí bắt buộc; IR phải có kiểu operand rõ; target IR phải chỉ dùng instruction được backend hỗ trợ.

### Diagnostics xuyên suốt

Mỗi node và instruction nên giữ source origin đủ để thông báo lỗi có thể quay về nguồn. Các pass cần giữ hoặc biến đổi metadata có chủ đích.

### Dependency được khai báo

Pass và module nên khai báo phụ thuộc. Điều này hỗ trợ sắp xếp thứ tự, chạy song song, cache và incremental invalidation.

### Tách ngôn ngữ khỏi target

Frontend nên mô tả semantics DSL; backend quyết định cách thực hiện trên nền tảng. Nếu target-specific logic xuất hiện khắp parser và semantic analyzer, việc thêm target mới sẽ khó hơn.

### Versioning có chủ đích

Grammar, IR, runtime API và artifact cần có quy tắc phiên bản. Khi thay đổi một phần, pipeline cần xác định artifact cũ có thể chạy tiếp hay phải biên dịch lại.

### Quan sát và giới hạn tài nguyên

Mỗi stage nên cung cấp timing, counters và lỗi. Compiler cần giới hạn đầu vào và runtime cần giới hạn thực thi, nhất là khi DSL được viết bởi người dùng cuối.

## Các quyết định kiến trúc quan trọng

Khi thiết kế pipeline, nhóm phát triển cần đưa ra một số quyết định và ghi lại lý do:

| Quyết định | Các lựa chọn thường gặp | Ảnh hưởng |
|---|---|---|
| Frontend output | AST, CST, AST + trivia | Debug, formatter, semantic analysis |
| Semantic model | Sửa AST, Typed AST riêng, symbol side table | Ranh giới và khả năng cache |
| IR | Không dùng, một IR, nhiều cấp IR | Chi phí triển khai và tối ưu |
| Execution | Code generation, tree-walk, bytecode VM | Hiệu năng và portability |
| Backend | Một target, nhiều target | Tính độc lập nền tảng |
| Error policy | Fail-fast, accumulate, partial parse | UX và độ tin cậy build |
| Module loading | Eager, lazy, incremental | Hiệu năng và dependency |
| Optimization | Không tối ưu, pass tĩnh, profile-guided | Tốc độ và độ phức tạp |
| Runtime access | Direct API, capability registry, sandbox | Bảo mật và khả năng kiểm soát |
| Caching | Không cache, cache theo file, cache theo dependency graph | Tốc độ và tính đúng đắn |

Không có một kiến trúc duy nhất phù hợp với mọi DSL. Một ngôn ngữ nhỏ phục vụ cấu hình nội bộ có thể dùng AST trực tiếp và serialize sau validation. Một DSL quy tắc được thực thi hàng triệu lần có thể cần IR, tối ưu hóa và bytecode VM. Một DSL truy vấn cần logical plan và optimizer chuyên biệt.

## Những lỗi thiết kế thường gặp

### Dồn mọi logic vào một bước

Một hàm duy nhất vừa parse, resolve tên, kiểm tra kiểu, tối ưu và sinh mã khiến trách nhiệm khó phân biệt. Khi lỗi xảy ra, khó biết stage nào tạo ra kết quả sai. Hãy tách các nhiệm vụ có invariant riêng.

### Không giữ source location

Khi AST được hạ thành IR, nếu source span bị loại bỏ quá sớm, runtime và compiler khó giải thích lỗi theo ngôn ngữ người dùng. Cần giữ source origin qua các phép biến đổi có ý nghĩa.

### Sinh mã trước khi xác nhận ngữ nghĩa

Nếu backend nhận AST chưa type-check hoặc còn unresolved reference, nó phải tự đoán và có thể sinh artifact sai. Hãy xác định điều kiện đầu vào bắt buộc của backend.

### Tối ưu hóa không bảo toàn semantics

Constant folding, inline hoặc reorder có thể thay đổi side effect, exception, precision hoặc thứ tự kết quả. Mỗi pass cần hiểu semantics DSL và có test tương ứng.

### Không quản lý phiên bản dependency

Cùng source nhưng dependency hoặc schema thay đổi có thể tạo output khác. Nếu cache chỉ dựa trên source, hệ thống có thể dùng artifact cũ không hợp lệ.

### Không phân biệt build-time và runtime

Giá trị chỉ biết khi chạy không thể được giả định tại compile-time. Ngược lại, lỗi kiểu hoặc tên có thể phát hiện sớm không nên trì hoãn nếu điều đó làm runtime dễ thất bại hơn.

### Runtime có quyền quá rộng

Nếu DSL có thể gọi tùy ý hệ thống hoặc truy cập tài nguyên không giới hạn, một rule đơn giản có thể gây tác động ngoài dự kiến. Runtime nên cấp capability theo nhu cầu và kiểm soát resource budget.

### Chỉ test từng stage

Các stage có thể đúng riêng nhưng không tương thích về token, AST schema, IR version hoặc runtime API. Cần contract test và end-to-end test để xác nhận toàn pipeline.

### Không có chiến lược incremental invalidation

Cache không được invalidation đúng có thể trả kết quả cũ. Cần theo dõi dependency giữa source, symbol, schema, catalog, compiler option và artifact.

## Quy trình xây dựng pipeline xử lý DSL

Một quy trình thực tế có thể đi theo các bước:

1. **Xác định sản phẩm đầu ra:** chương trình được diễn giải, sinh mã, tạo cấu hình, query plan hay workflow.
2. **Xác định đầu vào:** source files, module, schema, dependency, language version và build options.
3. **Thiết kế frontend:** source manager, preprocessing nếu cần, lexer, parser và AST/CST.
4. **Thiết kế semantic analysis:** scope, symbol resolution, type checking và domain validation.
5. **Quyết định representation:** xác định AST có đủ hay cần HIR/IR và các invariant tương ứng.
6. **Xác định pass:** phân tích, lowering và optimization; ghi rõ thứ tự và dependency.
7. **Thiết kế backend hoặc evaluator:** mapping kiểu, control flow, runtime helper và artifact format.
8. **Thiết kế runtime context:** dữ liệu, service, permission, cancellation và resource budget.
9. **Thiết kế diagnostics và source mapping:** giữ liên kết từ lỗi và kết quả về mã nguồn.
10. **Thiết kế cache và incremental behavior:** xác định cache key, dependency graph và invalidation.
11. **Thiết kế bảo mật và quan sát:** sandbox, giới hạn tài nguyên, logging, tracing và metrics.
12. **Kiểm thử theo tầng và end-to-end:** xác nhận stage contract, semantics và kết quả thực thi.
13. **Quản lý version:** khóa phiên bản language, compiler, IR, artifact và runtime compatibility.

Nên bắt đầu với pipeline tối thiểu đáp ứng use case. Chỉ thêm IR, optimization pass, bytecode hoặc incremental compilation khi có nhu cầu rõ và có thể đo được. Tuy nhiên, ngay cả pipeline nhỏ cũng cần ranh giới trách nhiệm, diagnostics và source mapping đủ tốt để có thể mở rộng.

## Kết luận

Pipeline xử lý là chuỗi giai đoạn đưa chương trình DSL từ nguồn văn bản đến một kết quả có thể thực thi hoặc sử dụng. Pipeline thường bao gồm nạp nguồn, tiền xử lý, lexing, parsing, xây AST, semantic analysis, tạo IR, tối ưu hóa, sinh mã hoặc đánh giá bằng interpreter, sau đó chạy trong runtime.

Một pipeline được thiết kế tốt có stage với trách nhiệm và hợp đồng rõ ràng, giữ source mapping xuyên suốt, phân biệt lỗi cú pháp với lỗi ngữ nghĩa và lỗi runtime, đồng thời quản lý dependency, cache, version và tài nguyên. Cách tổ chức cụ thể phụ thuộc loại DSL: cấu hình, truy vấn, rule, workflow hay template có thể cần các backend và runtime khác nhau.

Khi xác định đầu ra, đầu vào, invariant giữa các stage và semantics của ngôn ngữ ngay từ đầu, nhóm phát triển có thể xây một pipeline dễ kiểm thử, dễ quan sát và có khả năng mở rộng mà không làm frontend bị phụ thuộc chặt vào một nền tảng thực thi duy nhất.

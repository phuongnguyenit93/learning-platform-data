# Kiểm thử luật parser

## Vai trò của kiểm thử luật parser

Parser nhận token stream do lexer tạo ra và xác định cách các token kết hợp thành khai báo, câu lệnh, biểu thức hoặc cấu trúc khác của DSL. Parser thường xây dựng Abstract Syntax Tree (AST), Concrete Syntax Tree (CST) hoặc một biểu diễn cấu trúc trung gian để các bước sau phân tích ngữ nghĩa và thực thi.

**Kiểm thử luật parser** xác nhận từng production trong grammar được nhận diện đúng, các nhánh cú pháp được lựa chọn đúng, cấu trúc cây được xây chính xác và đầu vào không hợp lệ được báo lỗi phù hợp. Trọng tâm là hợp đồng giữa token stream và cấu trúc cú pháp.

Ví dụ, với grammar giản lược:

~~~ebnf
assignment = identifier, "=", expression ;
~~~

Đầu vào token IDENTIFIER("discount"), ASSIGN, INTEGER_LITERAL(10), EOF cần tạo một node Assignment có đích là identifier discount và giá trị là literal 10. Nếu parser bỏ qua dấu bằng, gắn literal vào sai trường hoặc nhận một chuỗi thiếu biểu thức, luật parser chưa được kiểm thử đúng.

Kiểm thử parser khác với kiểm thử lexer. Lexer xác nhận ký tự được phân loại thành token; parser xác nhận token được kết hợp thành cấu trúc theo grammar. Kiểm thử parser cũng khác với kiểm tra ngữ nghĩa: một phép gán có thể đúng cú pháp nhưng sai kiểu, tham chiếu đến tên không tồn tại hoặc vi phạm quy tắc miền. Những điều kiện đó thuộc các bước sau, trừ khi DSL chủ động tích hợp chúng vào parser.

Một chiến lược kiểm thử parser tốt cần bao phủ:

- Từng production và từng nhánh lựa chọn.
- Phần bắt buộc, tùy chọn và lặp.
- Ranh giới giữa các cấu trúc cú pháp.
- Độ ưu tiên và tính kết hợp của toán tử.
- Cây AST/CST được tạo ra.
- Đầu vào không hợp lệ và vị trí lỗi.
- Khả năng phục hồi sau lỗi nếu parser hỗ trợ.
- Hành vi với đầu vào lớn, lồng sâu và chỉnh sửa gia tăng.

## Xác định hợp đồng parser trước khi viết test

Trước khi kiểm thử, cần xác định parser nhận đầu vào và trả về kết quả theo dạng nào. Parser có thể nhận danh sách token đã tạo sẵn, token stream lazy hoặc gọi trực tiếp lexer thông qua một facade. Để test luật parser độc lập, nên có cách cung cấp token stream có kiểm soát.

Một hợp đồng parser thường xác định:

| Thành phần | Câu hỏi cần trả lời |
|---|---|
| Input | Parser nhận token stream hay source text? |
| Start rule | Production nào là điểm bắt đầu của parse? |
| Output | Trả AST, CST, parse tree hay kết hợp? |
| End of input | Có yêu cầu tiêu thụ hết token đến EOF không? |
| Diagnostics | Lỗi có mã, span, expected token và actual token không? |
| Recovery | Dừng ở lỗi đầu tiên hay tiếp tục thu thập lỗi? |
| Partial parse | Có trả về cây chưa hoàn chỉnh khi lỗi không? |
| Source mapping | Node và lỗi giữ vị trí nguồn ra sao? |
| Ambiguity | Grammar có được phép nhiều cách phân tích không? |
| Limits | Có giới hạn độ sâu, kích thước hoặc thời gian không? |

Nếu parser chỉ trả về boolean thành công/thất bại, test có thể xác nhận ngôn ngữ được chấp nhận nhưng khó phát hiện parser xây sai cấu trúc. Với DSL có AST, nên kiểm tra cả loại node, trường, quan hệ con và source span.

### Tách test parser khỏi test lexer

Một test parser đơn vị nên dùng token giả lập hoặc token fixture để kiểm tra grammar mà không phụ thuộc vào cách lexer nhận diện ký tự. Ví dụ, muốn kiểm tra production so sánh, có thể cung cấp trực tiếp token IDENTIFIER, GREATER_EQUAL và NUMBER.

Sau đó, integration test mới kiểm tra source text đi qua lexer rồi parser. Cách chia này giúp khoanh vùng lỗi:

- Nếu token stream sai, kiểm tra lexer.
- Nếu token stream đúng nhưng parse tree sai, kiểm tra parser.
- Nếu AST đúng nhưng kiểu hoặc tên không hợp lệ, kiểm tra semantic analysis.

Không phải dự án nào cũng cần một framework token fixture riêng, nhưng ranh giới trách nhiệm cần rõ. Nếu tất cả test chỉ chạy source-to-AST, lỗi lexer có thể bị nhầm thành lỗi parser và ngược lại.

## Thiết kế parser test harness

Một test harness có thể nhận token sequence, tên start rule và kết quả mong đợi. Với parser sinh tự động, harness có thể gọi parser generator runtime. Với recursive descent, harness gọi hàm parse tương ứng.

Một test khái quát:

~~~text
result = parse(tokens, startRule = expression)

assert result.success
assert result.ast == expectedAst
assert result.consumedAllInput
assert result.diagnostics.isEmpty()
~~~

Với đầu vào không hợp lệ:

~~~text
result = parse(tokens, startRule = expression)

assert not result.success
assert result.diagnostics contains expectedDiagnostic
assert result.errorSpan == expectedSpan
~~~

Kết quả parse nên được kiểm tra ở mức cấu trúc ổn định. Tránh chỉ so sánh chuỗi debug của AST nếu định dạng debug thay đổi thường xuyên.

### Các dạng assertion hữu ích

- Parse thành công hoặc thất bại.
- Start rule nhận đúng loại đầu vào.
- Toàn bộ token được tiêu thụ.
- Loại node gốc chính xác.
- Node con nằm đúng trường và đúng thứ tự.
- Giá trị literal được giải mã chính xác.
- Operator và operand được gắn đúng.
- Optional field có mặt hoặc vắng mặt đúng.
- Danh sách có đúng số phần tử và thứ tự.
- Source span trỏ đúng token nguồn.
- Diagnostics có đúng mã, vị trí và token mong đợi.

Không phải test nào cũng cần tất cả assertion. Test một production đơn giản có thể kiểm tra node và trường chính; test precedence cần kiểm tra hình dạng cây; test recovery cần kiểm tra cả cây từng phần và danh sách diagnostics.

## Kiểm thử từng production trong grammar

Mỗi production nên có ít nhất một test đại diện cho từng nhánh quan trọng. Với production có lựa chọn, cần test từng alternative. Với phần optional, cần test cả trường hợp có và không có. Với repetition, cần test số phần tử tối thiểu, nhiều phần tử và separator.

Giả sử grammar:

~~~ebnf
statement = assignment | functionCall | ruleDeclaration ;

assignment = identifier, "=", expression ;

functionCall = qualifiedName, "(", [ argumentList ], ")" ;

argumentList = expression, { ",", expression } ;
~~~

Bộ test nên có các trường hợp:

| Production | Đầu vào đại diện | Điều cần xác nhận |
|---|---|---|
| assignment | total = 10 | AssignmentNode, đúng target và value |
| functionCall | send() | Danh sách đối số rỗng |
| functionCall | send(order) | Một đối số |
| argumentList | a, b, c | Ba phần tử theo đúng thứ tự |
| statement | total = 10 | Chọn nhánh assignment |
| statement | send(order) | Chọn nhánh functionCall |

### Production có alternative

Với production:

~~~ebnf
literal = number | string | booleanLiteral ;
~~~

cần test từng nhánh: số, chuỗi, TRUE và FALSE. Không nên chỉ kiểm tra rằng mọi đầu vào đều parse thành LiteralNode. Cần xác nhận subtype hoặc giá trị node tương ứng: NumberLiteral, StringLiteral, BooleanLiteral. Nếu AST dùng một node Literal chung, cần kiểm tra trường kind và value.

Nếu các alternative có tiền tố chung, cần thêm test phân biệt nhánh. Ví dụ hai dạng khai báo cùng bắt đầu bằng IDENTIFIER, nhưng token tiếp theo là ASSIGN hoặc LPAREN. Test cần xác nhận parser không chọn nhánh quá sớm.

### Phần optional

Với:

~~~ebnf
elseClause = [ "ELSE", action ] ;
~~~

cần test:

- Rule không có ELSE.
- Rule có ELSE và một action hợp lệ.
- ELSE xuất hiện nhưng thiếu action.
- ELSE lặp hai lần nếu grammar chỉ cho phép một.
- ELSE xuất hiện ở vị trí không được phép.

Khi không có ELSE, AST có thể lưu optional field là absent/null hoặc một node mặc định theo thiết kế. Test nên xác nhận đúng hợp đồng của mô hình, không tự giả định một cách biểu diễn.

### Phần repetition

Với:

~~~ebnf
argumentList = expression, { ",", expression } ;
~~~

test tối thiểu một phần tử, hai phần tử và danh sách dài hơn. Nếu production cho phép danh sách rỗng bằng cách đặt toàn bộ list trong optional, test cần xác nhận lời gọi không đối số.

Các trường hợp sai cần gồm dấu phẩy đầu, dấu phẩy cuối, hai dấu phẩy liên tiếp và thiếu expression sau separator:

~~~text
f(a)
f(a, b)
f()
f(, a)
f(a,)
f(a,,b)
~~~

Parser cần phân biệt trường hợp hợp lệ và không hợp lệ theo grammar, đồng thời báo lỗi tại vị trí phù hợp.

## Kiểm thử cấu trúc AST và CST

Parse thành công chưa đủ. Parser phải xây cấu trúc đúng để các bước semantic analysis và backend hiểu đúng ý định.

### Kiểm tra loại node và trường

Với phép gán:

~~~text
discount.rate = 10
~~~

AST mong đợi có thể là:

~~~text
Assignment
  target:
    PropertyAccess
      receiver: Identifier("discount")
      property: Identifier("rate")
  value:
    NumberLiteral(10)
~~~

Test cần xác nhận node gốc là Assignment, target là PropertyAccess, receiver là discount, property là rate, value là NumberLiteral với giá trị 10 và không có node thừa hoặc thiếu.

Nếu AST lưu qualified name dưới dạng một chuỗi thay vì chuỗi node, assertion cần phù hợp với thiết kế đó. Mục tiêu là kiểm tra cấu trúc công khai mà các bước sau phụ thuộc vào.

### Kiểm tra thứ tự node trong danh sách

Với một block gồm nhiều action, thứ tự thường có ý nghĩa:

~~~text
THEN
  validateOrder()
  reserveStock()
  capturePayment()
~~~

AST cần giữ đúng thứ tự validateOrder, reserveStock, capturePayment. Nếu parser dùng collection không bảo toàn thứ tự hoặc append node sai, chương trình có thể thực thi hành động theo thứ tự khác.

### AST và CST có mục đích khác nhau

AST thường bỏ các chi tiết cú pháp không cần cho ngữ nghĩa, chẳng hạn dấu ngoặc hoặc dấu phân cách không có ý nghĩa. CST giữ cấu trúc gần với nguồn hơn và có thể giữ comment, whitespace, dấu ngoặc và token cụ thể.

Test AST tập trung vào ý nghĩa cấu trúc. Test CST cần kiểm tra cả chi tiết cú pháp, nhất là khi DSL hỗ trợ formatter, refactoring hoặc round-trip source.

Ví dụ, hai nguồn:

~~~text
(a + b)
~~~

~~~text
a + b
~~~

có thể tạo AST tương đương nhưng CST khác nhau vì một dạng có dấu ngoặc tường minh. Nếu DSL có quy tắc giữ dấu ngoặc cho công cụ chỉnh sửa, không nên chỉ kiểm tra AST.

### Kiểm tra node rỗng và node tổng hợp

Một số grammar cho phép block rỗng, danh sách rỗng hoặc biểu thức mặc định. Test cần xác định parser biểu diễn chúng ra sao: node rỗng riêng, danh sách không có phần tử, optional field không có giá trị hoặc node tổng hợp được tạo trong quá trình parse.

Không nên để cùng một cấu trúc cú pháp tạo nhiều dạng AST khác nhau tùy đường đi parser nếu không có lý do được định nghĩa.

## Kiểm thử độ ưu tiên toán tử

Độ ưu tiên (precedence) quyết định toán tử nào được nhóm trước khi xét thứ tự xuất hiện. Đây là khu vực cần test cấu trúc AST, không chỉ test parse success.

Giả sử DSL có grammar:

~~~ebnf
expression = orExpression ;
orExpression = andExpression, { "OR", andExpression } ;
andExpression = comparison, { "AND", comparison } ;
comparison = additiveExpression,
             [ comparisonOperator, additiveExpression ] ;
additiveExpression = multiplicativeExpression,
                     { ( "+" | "-" ), multiplicativeExpression } ;
multiplicativeExpression = primary,
                           { ( "*" | "/" ), primary } ;
primary = identifier | number | "(", expression, ")" ;
~~~

Grammar thể hiện precedence từ cao xuống thấp: primary, nhân/chia, cộng/trừ, so sánh, AND, OR.

### Ví dụ precedence số học

Nguồn:

~~~text
a + b * c
~~~

AST mong đợi:

~~~text
Add
  left: Identifier(a)
  right:
    Multiply
      left: Identifier(b)
      right: Identifier(c)
~~~

Nguồn:

~~~text
a * b + c
~~~

AST mong đợi:

~~~text
Add
  left:
    Multiply
      left: Identifier(a)
      right: Identifier(b)
  right: Identifier(c)
~~~

Nếu parser tạo Add ở gốc cho biểu thức đầu nhưng gắn b và c sai, assertion trên AST sẽ phát hiện lỗi mà parse success không thể phát hiện.

### Ví dụ precedence logic

Nguồn:

~~~text
a OR b AND c
~~~

Nếu AND ưu tiên cao hơn OR, AST phải tương đương:

~~~text
Or
  left: a
  right:
    And
      left: b
      right: c
~~~

Nguồn a AND b OR c phải có And ở nhánh trái của Or. Cần kiểm tra cả hai thứ tự để tránh parser chỉ xử lý đúng một trường hợp.

### Dấu ngoặc thay đổi cách nhóm

Nguồn:

~~~text
(a + b) * c
~~~

phải tạo Multiply ở gốc, với Add là toán hạng trái. Nguồn:

~~~text
a + (b * c)
~~~

có thể tạo AST giống với a + b * c nếu dấu ngoặc không được giữ trong AST. Nếu test CST, cần xác nhận dấu ngoặc được giữ ở vị trí tương ứng.

### Kiểm thử mọi cặp toán tử

Với n mức precedence, nên có test cho các cặp toán tử ở mức liền kề và cách nhau nhiều mức. Một ma trận kiểm thử giúp nhận ra thứ tự ưu tiên:

| Biểu thức | Điều cần xác nhận |
|---|---|
| a + b * c | Nhân trước cộng |
| a * b + c | Nhân ở nhánh trái |
| a OR b AND c | AND trước OR |
| a AND b OR c | AND được nhóm trước |
| a < b AND c | So sánh trước AND |
| a + b < c * d | Số học trước so sánh |
| (a + b) * c | Ngoặc thay đổi nhóm |
| a * (b + c) | Ngoặc thay đổi nhóm |

Không nhất thiết viết một test cho mọi hoán vị nếu đã có test theo cặp đủ đại diện, nhưng mỗi mức precedence và các điểm giao nhau quan trọng phải được kiểm tra.

## Kiểm thử tính kết hợp của toán tử

Tính kết hợp (associativity) xác định cách nhóm các toán tử cùng precedence khi không có dấu ngoặc.

Với phép trừ kết hợp trái:

~~~text
a - b - c
~~~

AST phải là Subtract(Subtract(a, b), c), không phải Subtract(a, Subtract(b, c)).

Với phép lũy thừa kết hợp phải trong một số ngôn ngữ:

~~~text
a ^ b ^ c
~~~

AST mong đợi là a ^ (b ^ c). Cần test riêng cho từng toán tử hoặc nhóm toán tử có quy tắc kết hợp khác nhau.

### Unary operator và binary operator

Dấu trừ có thể xuất hiện ở cả vị trí unary và binary:

~~~text
-a
a - b
a * -b
-(a + b)
~~~

Parser cần phân biệt dựa trên ngữ cảnh cú pháp. Test nên xác nhận -a tạo UnaryMinus; a - b tạo Subtract; a * -b tạo Multiply với toán hạng phải là UnaryMinus; -(a + b) đặt UnaryMinus bên ngoài biểu thức có ngoặc; --a được chấp nhận hoặc từ chối theo grammar.

Nếu unary minus có precedence khác exponent hoặc phép nhân, cần có test xác nhận tương tác đó.

## Kiểm thử cấu trúc lồng nhau và đệ quy

Grammar DSL thường có các cấu trúc đệ quy: biểu thức trong ngoặc, block lồng nhau, câu lệnh điều kiện bên trong điều kiện, hoặc lời gọi hàm làm đối số của lời gọi khác.

Ví dụ:

~~~text
calculate(round(applyTax(order.total), 2))
~~~

Parser cần tạo cây lồng đúng theo cặp dấu ngoặc và danh sách đối số.

### Ngoặc lồng nhau

Test các mức:

~~~text
a
(a)
((a))
(((a + b)))
~~~

Kiểm tra parser xử lý đúng trường hợp cơ bản, một cặp ngoặc, nhiều cặp ngoặc và biểu thức bên trong. Nếu có giới hạn nesting depth, test đúng ngưỡng và vượt ngưỡng.

### Block lồng nhau

Ví dụ:

~~~text
RULE "outer"
WHEN customer.active
THEN
  IF order.total > 1000 THEN
    applyDiscount()
  ELSE
    applyStandardPrice()
~~~

Parser phải gắn IF và nhánh ELSE vào đúng block hoặc action list. Nếu indentation là cú pháp, test cần kiểm tra token INDENT/DEDENT; nếu dấu ngoặc xác định block, test cần kiểm tra dấu mở/đóng.

### Đệ quy trái và parser strategy

Một grammar có thể dùng đệ quy trái hoặc repetition để biểu diễn chuỗi toán tử. Parser recursive descent thường cần grammar đã loại bỏ đệ quy trái trực tiếp, trong khi parser LR có thể xử lý một số dạng đệ quy trái.

Test cần phù hợp với parser strategy. Không nên kết luận grammar sai chỉ vì một parser không hỗ trợ dạng đệ quy cụ thể; cần kiểm tra đặc tả grammar và họ parser được chọn.

## Kiểm thử danh sách và separator

Danh sách xuất hiện trong tham số, import, khai báo, thuộc tính hoặc action. Parser cần xử lý đúng separator và các trường hợp biên.

Với:

~~~ebnf
argumentList = expression, { ",", expression } ;
~~~

các trường hợp cần kiểm tra:

| Đầu vào | Kết quả theo grammar |
|---|---|
| f(a) | Hợp lệ |
| f(a, b) | Hợp lệ |
| f(a, b, c) | Hợp lệ |
| f() | Chỉ hợp lệ nếu argumentList là optional |
| f(, a) | Không hợp lệ |
| f(a,) | Không hợp lệ nếu trailing comma không được hỗ trợ |
| f(a,,b) | Không hợp lệ |
| f(a b) | Không hợp lệ nếu thiếu separator |

Nếu DSL cho phép trailing comma, grammar cần thể hiện điều đó và test phải xác nhận:

~~~text
f(a, b,)
~~~

Parser không nên vô tình chấp nhận trailing comma chỉ vì implementation bỏ qua token comma cuối. Hành vi phải đến từ đặc tả.

### Danh sách nhiều dòng

Nếu list có thể xuống dòng:

~~~text
f(
  a,
  b,
  c
)
~~~

cần test newline, comment giữa phần tử, dấu phẩy trước newline và dấu phẩy sau newline. Nếu newline là token cú pháp, grammar cần quy định vị trí continuation.

## Kiểm thử các cấu trúc khai báo

DSL thường có declaration cho module, type, function, rule, constant hoặc resource. Mỗi loại khai báo cần test trường bắt buộc, thứ tự thành phần và phần mở rộng tùy chọn.

Ví dụ:

~~~ebnf
functionDeclaration = "FUNCTION", identifier,
                      "(", [ parameterList ], ")",
                      block ;

parameterList = parameter, { ",", parameter } ;

parameter = identifier, [ ":", typeName ] ;
~~~

Các trường hợp:

- Function có danh sách tham số rỗng.
- Function có một tham số.
- Function có nhiều tham số.
- Tham số có type annotation và không có annotation.
- Thiếu tên function.
- Thiếu dấu ngoặc.
- Thiếu dấu đóng ngoặc.
- Thiếu block.
- Dấu phẩy cuối nếu không được phép.

Parser chỉ xác nhận cấu trúc. Việc tên function trùng, typeName có tồn tại hay tham số có kiểu hợp lệ thường thuộc semantic analysis.

### Khai báo lồng và phạm vi cú pháp

Nếu khai báo có thể nằm trong module hoặc block, cần test đúng vị trí cho phép. Một FunctionDeclaration có thể hợp lệ ở cấp module nhưng không được phép bên trong action. Test parser nên xác nhận grammar chấp nhận và từ chối đúng vị trí, không dựa vào semantic analyzer nếu đó là ràng buộc cú pháp.

## Kiểm thử ambiguity và lựa chọn nhánh

Grammar mơ hồ khi cùng một chuỗi token có thể tạo nhiều cây phân tích khác nhau. Parser có thể giải quyết bằng precedence, associativity, lookahead hoặc quy tắc ưu tiên của parser generator. Nhưng test cần khóa hành vi mong đợi.

### Dangling ELSE

Với cấu trúc IF lồng nhau:

~~~text
IF a THEN
  IF b THEN x
ELSE y
~~~

cần xác định ELSE gắn với IF nào. Một quy ước phổ biến là gắn với IF gần nhất chưa có ELSE. Test phải kiểm tra AST thể hiện đúng quy tắc này.

Nếu DSL dùng block delimiter rõ ràng, có thể loại bỏ ambiguity bằng dấu ngoặc hoặc từ khóa kết thúc block. Test vẫn nên bao gồm cấu trúc lồng để bảo đảm parser không gắn nhầm nhánh.

### Alternative có tiền tố chung

Ví dụ:

~~~ebnf
statement = identifier, "=", expression
          | identifier, "(", [ argumentList ], ")" ;
~~~

Cả hai nhánh bắt đầu bằng identifier. Parser cần nhìn token tiếp theo để phân biệt phép gán và lời gọi hàm. Test nên bao gồm cả hai nhánh và các tiền tố chưa hoàn chỉnh:

~~~text
value = 10
send(order)
value
send(
~~~

Các trường hợp chưa hoàn chỉnh có thể là lỗi cú pháp hoặc parse result một phần tùy chế độ parser.

### Ưu tiên trong parser generator

Một số parser generator cho phép khai báo precedence và associativity bằng directive. Khi đó, test cần xác nhận runtime thực sự tạo cây như đặc tả, không chỉ xác nhận grammar generator không báo conflict.

Nếu công cụ cảnh báo shift/reduce hoặc reduce/reduce conflict, không nên bỏ qua mà không hiểu nguyên nhân. Test cho những chuỗi có liên quan cần được thêm để khóa hành vi được chọn.

## Kiểm thử đầu vào không hợp lệ

Một bộ test parser cần nhiều ví dụ sai có chủ đích. Mục tiêu không chỉ là parser từ chối đầu vào, mà còn báo lỗi tại vị trí hữu ích và không tạo cấu trúc sai được xem như hợp lệ.

Các nhóm lỗi:

- Thiếu token bắt buộc.
- Token sai loại tại một vị trí.
- Token thừa sau một cấu trúc hoàn chỉnh.
- Dấu ngoặc hoặc delimiter không cân bằng.
- Separator sai hoặc thiếu.
- Keyword sai vị trí.
- Cấu trúc lồng không được phép.
- Biểu thức thiếu toán hạng.
- Khối thiếu phần kết thúc.
- EOF xuất hiện khi parser còn chờ token.

### Expected và actual token

Ví dụ nguồn:

~~~text
discount.rate 10
~~~

Parser có thể mong đợi ASSIGN sau qualified name nhưng gặp INTEGER_LITERAL. Diagnostic nên chỉ ra vị trí và loại token mong đợi:

~~~text
Expected '=' after assignment target, found INTEGER_LITERAL.
~~~

Test nên xác nhận mã lỗi, span của token gây lỗi và danh sách expected token nếu parser cung cấp. Tránh assertion phụ thuộc toàn bộ câu thông báo nếu wording không phải API ổn định.

### Token thừa sau parse thành công

Một lỗi phổ biến là parser parse được prefix hợp lệ rồi bỏ qua token còn lại. Ví dụ, start rule expression có thể parse a + b trong đầu vào a + b c và không phát hiện c còn dư.

Test cần xác nhận chế độ parse toàn bộ yêu cầu EOF sau cấu trúc gốc. Với parser dùng trong IDE, partial parse có thể được phép, nhưng API phải phân biệt rõ parse prefix với parse complete input.

### EOF giữa cấu trúc

Test nguồn bị cắt tại nhiều vị trí:

~~~text
f(
f(a,
IF condition THEN
RULE "x"
WHEN a >
~~~

Parser cần báo token còn thiếu hoặc trạng thái incomplete tương ứng. Nếu có chế độ editor, nó có thể trả cây một phần và diagnostic có thể được điều chỉnh để không quá ồn khi người dùng đang gõ.

## Kiểm thử diagnostics và source span

Diagnostics là một phần quan trọng của trải nghiệm DSL. Parser có thể từ chối đúng đầu vào nhưng vẫn khó sử dụng nếu báo lỗi sai dòng, sai cột hoặc quá chung chung.

Một parser diagnostic nên có:

- Mã lỗi ổn định.
- Source ID hoặc đường dẫn tệp.
- Span của token hoặc vùng cú pháp liên quan.
- Token thực tế và token mong đợi nếu phù hợp.
- Mô tả ngắn, có thể kèm gợi ý sửa.
- Thông tin vị trí mở cấu trúc nếu lỗi là thiếu dấu đóng.

Ví dụ:

~~~text
rules.dsl:8:17: error PARSE-EXPECTED-EXPRESSION
Expected an expression after '>='.
Found NEWLINE.
~~~

Với dấu ngoặc không đóng, vị trí mở ngoặc thường hữu ích hơn vị trí EOF đơn thuần:

~~~text
rules.dsl:3:9: error PARSE-UNCLOSED-PAREN
Expected ')' to close '(' opened at line 3, column 9.
~~~

### Kiểm tra span của node

AST node có thể giữ source span để IDE điều hướng, highlight và refactor. Test cần xác nhận:

- Node gốc bao phủ đúng vùng cấu trúc.
- Node con có span nằm trong span cha.
- Token đầu và cuối được tính đúng.
- Span của literal không nuốt khoảng trắng ngoài literal nếu quy ước không yêu cầu.
- Node tổng hợp có span được định nghĩa nhất quán.
- Include hoặc macro expansion giữ được nguồn gốc.

Với CST, span thường bám sát token. Với AST, một số node có thể không có token riêng; khi đó cần quy định cách tổng hợp span từ node con.

## Kiểm thử phục hồi lỗi (error recovery)

Parser phục hồi lỗi nhằm tiếp tục phân tích phần còn lại để báo nhiều lỗi trong một lần chạy hoặc hỗ trợ IDE. Recovery không chỉ là bắt exception; nó cần chiến lược đồng bộ để parser tiếp tục ở vị trí hợp lý.

### Panic-mode recovery

Một chiến lược phổ biến là bỏ token cho đến khi gặp token đồng bộ, chẳng hạn dấu chấm phẩy, NEWLINE, dấu đóng block hoặc keyword mở khai báo mới.

Ví dụ:

~~~text
RULE "A"
WHEN order.total >
THEN applyA()

RULE "B"
WHEN customer.active
THEN applyB()
~~~

Nếu biểu thức của Rule A sai, parser có thể đồng bộ tại ranh giới khai báo tiếp theo để tiếp tục parse Rule B. Test cần xác nhận lỗi đầu tiên được báo và Rule B vẫn được tạo trong cây kết quả.

### Phrase-level recovery

Một số parser chèn hoặc xóa token giả định để tiếp tục. Ví dụ thiếu dấu ) trước EOF, parser có thể chèn token đóng để hoàn thành node và ghi diagnostic.

Test cần xác nhận token được chèn/xóa là hợp lý, cây kết quả không bị hỏng, diagnostic chỉ ra phép sửa giả định, parser không tạo quá nhiều lỗi dây chuyền và recovery không làm mất các khai báo hợp lệ tiếp theo.

### Đồng bộ và tránh vòng lặp

Sau lỗi, parser phải tiến token index hoặc kết thúc. Nếu recovery quay lại cùng vị trí mà không thay đổi trạng thái, parser có thể lặp vô hạn.

Test có thể sử dụng timeout hoặc instrumentation để xác nhận parser luôn tiến triển. Cần thử nhiều lỗi liên tiếp, delimiter lồng và EOF bất ngờ.

### Phân biệt lỗi gốc và lỗi dây chuyền

Một token thiếu có thể khiến parser báo nhiều lỗi phía sau. Ví dụ thiếu dấu đóng ngoặc có thể khiến mọi token tiếp theo bị diễn giải sai. Recovery tốt nên hạn chế diagnostics lặp lại do cùng một nguyên nhân.

Test không nhất thiết yêu cầu đúng một diagnostic cho mọi đầu vào, nhưng cần xác nhận lỗi quan trọng được báo và các lỗi tiếp theo có ích, không gây nhiễu quá mức.

## Kiểm thử parser theo loại thuật toán

Cách kiểm thử chi tiết có thể phụ thuộc parser strategy.

### Recursive descent

Recursive descent thường có một hàm cho mỗi nonterminal. Test có thể gọi trực tiếp từng hàm parse hoặc gọi start rule chung.

Các điểm cần kiểm tra:

- Hàm parse tiêu thụ đúng token.
- Lookahead chọn đúng alternative.
- Optional và repetition dừng đúng lúc.
- Đệ quy lồng không làm stack overflow trong giới hạn hỗ trợ.
- Lỗi không để parser đứng yên.
- Precedence được triển khai đúng qua các tầng hàm.

Với parser có backtracking, cần test nhánh thất bại có khôi phục vị trí token đúng trước khi thử nhánh khác.

### LL và predictive parser

Parser LL thường dựa vào lookahead để chọn production. Nếu grammar không LL(k) với k được chọn, parser có thể gặp conflict hoặc cần refactor grammar.

Test cần bao gồm các alternative có tiền tố chung và token lookahead tối đa. Nếu parser dùng một token lookahead, cần xác nhận các nhánh thực tế phân biệt được bằng một token tại những vị trí liên quan.

### LR và shift/reduce parser

Parser LR có thể xử lý một số grammar đệ quy trái và biểu thức theo bảng parse. Test cần xác nhận các conflict được giải quyết theo precedence/associativity mong muốn. Cần kiểm tra cả grammar build warnings và AST runtime, vì một parser sinh thành công không đồng nghĩa mọi chuỗi được hiểu đúng.

### PEG parser

PEG dùng ordered choice: nhánh lựa chọn được thử theo thứ tự và nhánh đầu tiên thành công có thể quyết định cách parse. Điều này khác với alternative trong CFG/EBNF thông thường.

Nếu DSL dùng PEG, thứ tự alternative có thể ảnh hưởng ngữ nghĩa. Test cần đảo hoặc thay đổi tiền tố để xác nhận nhánh mong muốn được chọn, và bảo đảm một nhánh rộng không nuốt đầu vào vốn thuộc nhánh cụ thể hơn.

## Kiểm thử parser gia tăng cho IDE

IDE thường cần parse khi người dùng đang gõ, lúc nguồn chưa hoàn chỉnh. Incremental parser cập nhật cây sau một thay đổi nhỏ thay vì parse lại toàn bộ tệp.

Các thao tác cần test:

- Chèn token giữa hai biểu thức.
- Xóa dấu ngoặc hoặc dấu kết thúc block.
- Đổi tên một identifier.
- Thêm hoặc xóa một nhánh ELSE.
- Chèn khai báo mới ở đầu hoặc giữa tệp.
- Chỉnh sửa trong block lồng sâu.
- Thay đổi token làm đổi alternative của production.
- Sửa nguồn trước một vùng có lỗi chưa được phục hồi.

Một cách kiểm tra đáng tin cậy là so sánh kết quả incremental parse với full parse trên cùng văn bản cuối cùng. Cả hai cần tạo cấu trúc và diagnostics tương đương theo hợp đồng. Nếu node identity được giữ để hỗ trợ editor, test có thể kiểm tra thêm những node không bị ảnh hưởng được tái sử dụng, nhưng không nên để tối ưu identity làm thay đổi ngữ nghĩa.

Parser gia tăng phải xử lý trạng thái lỗi đang tồn tại. Khi người dùng xóa dấu nháy mở hoặc thêm dấu ngoặc đóng, vùng lỗi có thể thay đổi xa hơn vị trí chỉnh sửa. Test cần xác nhận parser tính lại đúng vùng phụ thuộc.

## Property-based testing cho parser

Property-based testing tạo nhiều token stream hoặc chương trình theo các thuộc tính đã xác định. Nó có thể phát hiện trường hợp grammar hiếm mà test thủ công bỏ sót.

Một số property hữu ích:

- Mọi chương trình sinh theo grammar đều được parser chấp nhận.
- Mọi token stream không thuộc grammar bị từ chối hoặc trả trạng thái partial theo chính sách.
- Parse tree của biểu thức giữ đúng precedence.
- Danh sách giữ nguyên thứ tự phần tử.
- Thêm ngoặc quanh một expression không làm thay đổi ngữ nghĩa AST nếu AST bỏ ngoặc.
- Parse rồi pretty-print rồi parse lại tạo AST tương đương.
- Mọi node span nằm trong phạm vi nguồn.
- Parser luôn tiến token index hoặc kết thúc.
- Đầu vào lớn trong giới hạn không làm parser treo hoặc crash.

### Sinh đầu vào từ grammar

Có thể tạo generator đệ quy dựa trên production. Ví dụ, generator cho expression chọn một nhánh trong literal, identifier, binary expression hoặc parenthesized expression, với giới hạn độ sâu để tránh cây vô hạn.

Để tránh chỉ tạo chương trình đơn giản, generator nên phân bố lựa chọn giữa cấu trúc cơ bản, cấu trúc lồng, danh sách dài, optional branch có và không, các toán tử có precedence khác nhau, identifier và literal ở ranh giới, cùng các tổ hợp gần giới hạn độ sâu.

### Mutation-based testing

Bắt đầu từ chương trình hợp lệ rồi biến đổi một token:

- Xóa dấu đóng ngoặc.
- Thay ASSIGN bằng COMMA.
- Đổi keyword thành identifier.
- Thêm separator.
- Hoán đổi hai token.
- Cắt nguồn tại một vị trí.
- Chèn token không hợp lệ giữa hai thành phần.

Parser cần phản ứng có kiểm soát. Một mutation có thể tình cờ vẫn tạo chương trình hợp lệ; khi đó test nên đánh giá theo grammar thực tế, không mặc định mọi mutation đều phải thất bại.

## Fuzz testing parser

Fuzzing cung cấp token stream hoặc source text bất thường để tìm crash, treo, stack overflow, tiêu thụ tài nguyên quá mức và lỗi bộ nhớ.

Có thể fuzz ở hai tầng:

- Token-level fuzzing: sinh dãy token trực tiếp để tập trung vào parser.
- Source-level fuzzing: sinh văn bản để kiểm tra cả lexer và parser.

Token-level fuzzing hữu ích khi cần tách lỗi parser khỏi lexer. Source-level fuzzing gần với cách người dùng sử dụng nhưng khó xác định tầng gây lỗi hơn.

Các trường hợp nên đưa vào corpus:

- Chuỗi token ngẫu nhiên.
- Dấu ngoặc mở/đóng lặp lại.
- Danh sách có separator liên tiếp.
- Keyword lặp.
- Expression lồng sâu.
- Token không mong đợi tại EOF.
- Cấu trúc khai báo lặp hàng nghìn lần.
- Token stream gần hợp lệ chỉ sai một vị trí.

Parser phải có giới hạn độ sâu hoặc cơ chế bảo vệ phù hợp. Nếu grammar cho phép lồng sâu, recursive descent có thể dùng stack lớn; parser cần giới hạn rõ hoặc dùng cấu trúc xử lý phù hợp.

## Kiểm thử round-trip và pretty printer

Nếu DSL có formatter hoặc pretty printer, có thể kiểm tra quan hệ parse-print-parse.

Quy trình:

1. Parse nguồn thành AST.
2. Pretty-print AST thành nguồn chuẩn hóa.
3. Parse lại nguồn vừa in.
4. So sánh hai AST theo cấu trúc và ngữ nghĩa được công bố.

Ví dụ:

~~~text
Source A:
a+b*c

Pretty output:
a + b * c
~~~

Hai nguồn nên tạo AST tương đương. Tuy nhiên, nếu DSL có comment hoặc dấu ngoặc cần bảo toàn, AST thuần có thể không đủ; cần CST hoặc trivia để kiểm tra round-trip lossless.

Một số property:

- Pretty-print không tạo cú pháp sai.
- Parse output thành công.
- AST trước và sau tương đương.
- Formatter chạy lần hai không tiếp tục thay đổi output.
- Comment và source metadata được giữ theo chính sách.
- Dấu ngoặc cần thiết để bảo toàn precedence được in ra.

Round-trip test hữu ích để phát hiện lỗi precedence, associativity và quy tắc separator mà test parse success đơn thuần có thể bỏ sót.

## Hiệu năng và giới hạn tài nguyên

Parser thường cần xử lý nguồn có kích thước khác nhau, từ một rule ngắn đến tệp DSL lớn. Kiểm thử hiệu năng nên dựa trên workload thực tế và những trường hợp dễ gây tốn tài nguyên.

Các kịch bản:

- Tệp có nhiều khai báo cấp cao.
- Expression có chuỗi toán tử dài.
- Block lồng sâu.
- Danh sách có rất nhiều phần tử.
- Nhiều lỗi cú pháp liên tiếp.
- Grammar có nhiều alternative và lookahead.
- Parser có backtracking hoặc ordered choice.
- Token stream kết thúc bất ngờ sau nhiều cấu trúc mở.

Cần đo thời gian parse, bộ nhớ, số node tạo ra, số lần backtrack và số diagnostics nếu có. Không nên đặt ngưỡng chỉ dựa trên một máy phát triển; cần xác định mục tiêu phản hồi cho compiler, build và IDE.

Giới hạn có thể gồm kích thước nguồn, số token, độ sâu lồng nhau, số node AST, số lỗi tối đa và thời gian parse. Khi vượt giới hạn, parser nên trả lỗi có kiểm soát, không crash hoặc treo.

## Tổ chức bộ test parser

Một bộ test dễ bảo trì nên được chia theo production hoặc nhóm ngữ pháp:

~~~text
parser-tests/
  program/
  declarations/
  statements/
  expressions/
  precedence/
  associativity/
  lists-and-separators/
  nested-structures/
  ambiguity/
  invalid-input/
  diagnostics/
  recovery/
  source-spans/
  incremental/
  round-trip/
  fuzz-regressions/
~~~

Tên test nên mô tả hành vi:

- parses-empty-argument-list
- rejects-trailing-comma-when-disabled
- multiplication-binds-tighter-than-addition
- subtraction-is-left-associative
- parses-nested-parentheses
- binds-else-to-nearest-if
- reports-missing-expression-after-operator
- recovers-at-next-rule-declaration
- consumes-entire-input
- incremental-result-matches-full-parse

Với grammar lớn, có thể liên kết test đến tên production trong tài liệu. Khi production thay đổi, người duy trì dễ xác định test nào cần cập nhật.

### Fixture nguồn và fixture token

Fixture nguồn thuận tiện cho integration test. Fixture token phù hợp với test parser đơn vị. Nên lưu hai loại riêng biệt để người đọc biết test đang kiểm tra tầng nào.

Một fixture có thể chứa input source hoặc token sequence, start rule, AST/CST mong đợi, diagnostics mong đợi và ghi chú trường hợp biên nếu cần.

Không nên lưu expected output chỉ dưới dạng một chuỗi không có cấu trúc nếu có thể so sánh AST trực tiếp. Nếu dùng snapshot, cần format ổn định và review diff cẩn thận.

## Ví dụ bộ test cho DSL quy tắc

Giả sử DSL có cú pháp:

~~~text
RULE "VIP discount"
WHEN order.total >= 1000 AND customer.segment IS "VIP"
THEN discount.rate = 10
ELSE discount.rate = 0
~~~

Grammar rút gọn:

~~~ebnf
ruleDeclaration = "RULE", string,
                  "WHEN", expression,
                  "THEN", action,
                  [ "ELSE", action ] ;

expression = orExpression ;
orExpression = andExpression, { "OR", andExpression } ;
andExpression = comparison, { "AND", comparison } ;
comparison = primary, [ comparisonOperator, primary ] ;
comparisonOperator = "==" | "!=" | ">" | ">=" | "<" | "<=" | "IS" ;
primary = identifier | number | string | "(", expression, ")" ;
action = assignment ;
assignment = qualifiedName, "=", expression ;
~~~

Các test chính:

| Test case | Kết quả mong đợi |
|---|---|
| Rule có WHEN và THEN | Parse thành công |
| Rule có ELSE | Parse thành công, elseAction có node |
| Rule không có ELSE | Parse thành công, elseAction absent |
| Thiếu tên rule | Parse thất bại |
| Thiếu biểu thức sau WHEN | Parse thất bại |
| Thiếu action sau THEN | Parse thất bại |
| ELSE không có action | Parse thất bại |
| ELSE lặp hai lần | Parse thất bại nếu grammar chỉ cho phép một |
| AND kết hợp trong biểu thức | Tạo AndExpression |
| So sánh >= | Tạo GreaterEqualExpression |
| Thiếu token sau toán tử | Diagnostic tại vị trí thiếu toán hạng |
| Token thừa sau rule | Bị phát hiện nếu start rule yêu cầu EOF |

Ngoài test bảng, cần assertion AST cho biểu thức:

~~~text
order.total >= 1000 AND customer.segment IS "VIP"
~~~

AST mong đợi có AndExpression ở gốc, hai nhánh là các ComparisonExpression. Nếu parser tạo một ComparisonExpression duy nhất hoặc nhóm sai thứ tự, test AST sẽ phát hiện.

## Những lỗi thường gặp khi kiểm thử parser

### Chỉ kiểm tra parse success

Parser có thể chấp nhận đầu vào nhưng xây AST sai. Cần kiểm tra node kind, trường, thứ tự và precedence.

### Chỉ kiểm tra AST mà không kiểm tra tiêu thụ hết input

Parser có thể parse prefix rồi bỏ token thừa. Test start rule hoàn chỉnh nên xác nhận EOF được tiêu thụ.

### Không kiểm thử nhánh optional

Một nhánh ELSE hoặc type annotation có thể hoạt động khi xuất hiện nhưng làm parser lỗi khi vắng mặt, hoặc ngược lại. Cần test cả hai dạng.

### Bỏ qua separator cuối danh sách

Parser có thể vô tình chấp nhận trailing comma dù grammar không cho phép, hoặc từ chối nó khi đặc tả cho phép. Cần test rõ.

### Không khóa precedence và associativity

Một parser có thể parse mọi biểu thức nhưng tạo cây khác dự kiến. Test AST cho từng cặp precedence và toán tử kết hợp trái/phải.

### Không kiểm tra source span

Cây đúng nhưng span sai làm IDE highlight và diagnostics sai vị trí. Cần test offset, line/column và nguồn trong cấu trúc lồng.

### Chỉ kiểm tra lỗi đầu tiên

Nếu parser hỗ trợ recovery, cần test việc tiếp tục phân tích và tránh lỗi dây chuyền. Nếu parser không hỗ trợ recovery, test phải xác nhận nó dừng có kiểm soát.

### Bỏ qua grammar conflict

Parser generator có thể sinh parser với cảnh báo conflict. Cần hiểu conflict và viết test khóa cách xử lý thay vì bỏ qua cảnh báo.

### Không kiểm thử đầu vào chưa hoàn chỉnh

IDE thường parse khi người dùng đang gõ. Parser cần xử lý EOF giữa cấu trúc và cung cấp partial result hoặc diagnostic phù hợp với chế độ sử dụng.

## Quy trình xây dựng kiểm thử luật parser

Một quy trình thực tế có thể thực hiện theo thứ tự:

1. **Liệt kê production:** xác định start rule và tất cả nonterminal quan trọng.
2. **Tạo test cho từng alternative:** mỗi nhánh cần ít nhất một đầu vào đại diện.
3. **Kiểm tra optional và repetition:** thử vắng mặt, tối thiểu, nhiều phần tử và separator biên.
4. **Kiểm tra AST/CST:** xác nhận node kind, trường, thứ tự và span.
5. **Kiểm tra precedence và associativity:** dùng biểu thức có nhiều toán tử và ngoặc.
6. **Kiểm tra lồng nhau và đệ quy:** thử nesting, block và lời gọi lồng.
7. **Kiểm tra ambiguity:** thử tiền tố chung, dangling ELSE và conflict của parser generator.
8. **Kiểm tra lỗi:** thiếu/thừa token, delimiter sai, EOF và cấu trúc sai vị trí.
9. **Kiểm tra recovery:** xác nhận parser tiến triển và tiếp tục ở điểm đồng bộ nếu được hỗ trợ.
10. **Bổ sung property-based và fuzzing:** khám phá tổ hợp token ngoài ví dụ thủ công.
11. **Kiểm tra tích hợp:** chạy source qua lexer và parser để xác nhận hợp đồng giữa hai tầng.
12. **Giữ regression corpus:** mỗi lỗi parser được sửa cần có test tái hiện.

Quy trình này không yêu cầu mọi DSL phải có tất cả loại parser hoặc công cụ. Hãy chọn lớp kiểm thử phù hợp với grammar, parser strategy và cách DSL được sử dụng.

## Kết luận

Kiểm thử luật parser xác nhận rằng token stream được kết hợp thành cấu trúc cú pháp đúng theo grammar DSL. Một bộ test tốt cần kiểm tra từng production và alternative, phần optional và repetition, cấu trúc AST/CST, precedence, associativity, lồng nhau, ambiguity, lỗi cú pháp, source span và recovery.

Nên kết hợp unit test bằng token fixture, integration test từ source, boundary test, golden test, property-based testing, fuzzing, round-trip test và regression test. Việc kiểm tra cả cấu trúc cây và diagnostics giúp phát hiện lỗi mà chỉ xác nhận parse thành công hoặc thất bại không thể nhận ra. Khi grammar thay đổi, test cần được cập nhật cùng đặc tả để parser tiếp tục tạo ra cách hiểu ổn định, có thể dự đoán cho chương trình DSL.

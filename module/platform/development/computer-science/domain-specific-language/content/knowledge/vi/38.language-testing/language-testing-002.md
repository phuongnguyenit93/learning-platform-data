# Kiểm thử parser

Parser là thành phần biến chuỗi đầu vào của một ngôn ngữ thành cấu trúc có ý nghĩa để các bước tiếp theo có thể phân tích, kiểm tra hoặc thực thi. Trong một DSL (Domain-Specific Language), parser quyết định source nào được chấp nhận, cấu trúc nào được tạo ra và vị trí nào được báo lỗi khi cú pháp không hợp lệ. Một parser có thể biên dịch thành công phần lớn ví dụ thông thường nhưng vẫn có lỗi ở biểu thức lồng nhau, dấu phân cách, Unicode, thứ tự ưu tiên hoặc trường hợp input bị cắt giữa chừng.

**Kiểm thử parser (parser testing)** là hoạt động xác minh lexer và parser diễn giải source theo đúng grammar, tạo ra cấu trúc cú pháp đúng và xử lý input sai theo cách có kiểm soát. Kiểm thử parser cần bao phủ cả source hợp lệ, source không hợp lệ, trường hợp biên, error recovery, source location, tính ổn định và hiệu năng.

Ví dụ một DSL cấu hình có khai báo:

~~~text
service "orders-api" {
    replicas = 3
    enabled = true
}
~~~

Parser cần nhận diện service là keyword, orders-api là string literal, dấu ngoặc nhọn tạo block, replicas và enabled là tên thuộc tính, còn 3 và true là literal có kiểu. Kết quả không chỉ là việc parser không báo lỗi; nó phải là một cây cú pháp thể hiện đúng quan hệ giữa khai báo, block và thuộc tính.

Parser cũng phải xử lý source sai:

~~~text
service "orders-api" {
    replicas = 3
    enabled = true
~~~

Dấu ngoặc đóng bị thiếu. Parser nên đưa ra diagnostic gắn với vị trí hợp lý, không crash, không treo và không tạo AST giả vờ hoàn chỉnh mà các bước sau hiểu nhầm là source hợp lệ.

Trong chương **Kiểm thử DSL**, parser testing là nền tảng cho độ tin cậy của toàn bộ toolchain. Nếu parser tạo sai cấu trúc, semantic analysis, type checking, code generation và diagnostics phía sau đều có thể sai theo.

## 1. Parser trong kiến trúc DSL

Một pipeline DSL thường gồm nhiều bước:

~~~mermaid
flowchart LR
    A[Source text] --> B[Lexer]
    B --> C[Token stream]
    C --> D[Parser]
    D --> E[AST]
    E --> F[Semantic analysis]
    F --> G[Code generation or evaluation]
~~~

Lexer chuyển ký tự thành token. Parser nhận token và áp dụng grammar để tạo parse tree hoặc AST. Semantic analysis tiếp tục kiểm tra tên, kiểu, phạm vi và quy tắc domain.

### 1.1. Lexer và parser có trách nhiệm khác nhau

Lexer thường xử lý:

- Identifier và keyword.
- Number, string và boolean literal.
- Operator và punctuation.
- Whitespace và comment.
- Escape sequence.
- Vị trí dòng, cột và byte offset.

Parser thường xử lý:

- Khai báo và statement.
- Expression và precedence.
- Block và collection.
- Quan hệ lồng nhau.
- Thứ tự thành phần.
- Cấu trúc grammar hợp lệ.
- Error recovery và parse diagnostics.

Một số parser tích hợp lexer. Dù tổ chức thế nào, test nên phân biệt lỗi lexical với lỗi syntax để dễ xác định nguyên nhân.

### 1.2. Parse tree và AST

Parse tree thường giữ nhiều chi tiết grammar, gồm cả punctuation và node trung gian. AST lược bỏ chi tiết cú pháp không cần cho các bước sau.

Ví dụ expression:

~~~text
1 + 2 * 3
~~~

AST mong đợi nếu phép nhân có precedence cao hơn phép cộng:

~~~text
Add
  Literal(1)
  Multiply
    Literal(2)
    Literal(3)
~~~

Parser test cần xác nhận cấu trúc, không chỉ xác nhận expression được chấp nhận.

### 1.3. Parser đúng nhưng semantic analysis có thể thất bại

Ví dụ:

~~~text
service "api" {
    replicas = "three"
}
~~~

Nếu grammar cho phép attribute nhận expression bất kỳ, parser có thể thành công. Type checker mới xác định replicas cần Integer nhưng nhận String. Parser test nên tập trung vào syntax và AST; test semantic là lớp riêng.

### 1.4. Parser là boundary nhận dữ liệu

Source DSL có thể đến từ repository, API, plugin, file upload hoặc module bên ngoài. Vì vậy parser phải được kiểm thử với input không đáng tin cậy, không chỉ ví dụ do tác giả ngôn ngữ viết.

## 2. Mục tiêu của parser testing

Một bộ parser test tốt cần xác minh:

1. Source hợp lệ được chấp nhận.
2. Source được chuyển thành đúng cấu trúc.
3. Source không hợp lệ bị từ chối hoặc phục hồi theo contract.
4. Operator precedence và associativity chính xác.
5. Lexer xử lý literal, escape và Unicode đúng.
6. Source location và diagnostic range chính xác.
7. Parser không crash, treo hoặc tiêu thụ tài nguyên không giới hạn.
8. Cùng source tạo cùng parse result theo cùng phiên bản grammar.
9. Grammar không vô tình chấp nhận cú pháp bị cấm.
10. Thay đổi grammar không phá source cũ ngoài chính sách compatibility.

### 2.1. Acceptance correctness

Parser cần chấp nhận mọi source được grammar cho phép. Nếu parser từ chối một chương trình hợp lệ, người dùng không thể biểu đạt domain mà DSL hứa hỗ trợ.

### 2.2. Rejection correctness

Parser cần từ chối source nằm ngoài grammar. Việc chấp nhận cú pháp sai có thể tạo ambiguity hoặc khiến các tool khác diễn giải khác nhau.

### 2.3. Structural correctness

Parser có thể chấp nhận source nhưng tạo AST sai. Đây là lỗi nghiêm trọng vì downstream có thể thực thi semantics khác với điều người viết mong muốn.

### 2.4. Diagnostic correctness

Khi source sai, parser cần chỉ ra lỗi có thể hiểu và định vị được. Diagnostic không nên chỉ ghi syntax error ở cuối file nếu parser có thể xác định token hoặc construct gây lỗi.

### 2.5. Robustness

Parser cần chịu được input ngẫu nhiên, bị cắt, rất sâu hoặc rất dài trong các giới hạn được công bố.

## 3. Xác định grammar làm oracle cho test

Parser test cần có một nguồn chuẩn để xác định source nào hợp lệ và AST nào được mong đợi. Nguồn đó thường là grammar chính thức hoặc specification của DSL.

Ví dụ grammar EBNF đơn giản:

~~~text
program       = { declaration } ;
declaration   = serviceDecl | variableDecl ;
serviceDecl   = "service" , string , block ;
variableDecl  = "let" , identifier , "=" , expression ;
block         = "{" , { attribute } , "}" ;
attribute     = identifier , "=" , expression ;
expression    = additive ;
additive      = multiplicative , { ("+" | "-") , multiplicative } ;
multiplicative = primary , { ("*" | "/") , primary } ;
primary       = number | string | identifier | "(" , expression , ")" ;
~~~

Grammar này chỉ minh họa. Một DSL thực tế cần quy định comment, separator, newline, list, map, function call, reference và error behavior.

### 3.1. Grammar và implementation phải được kiểm tra độc lập

Không nên dùng parser implementation làm oracle duy nhất cho chính parser đó. Nếu test sinh expected output bằng cùng code path, một bug có thể xuất hiện ở cả actual lẫn expected và không bị phát hiện.

Có thể dùng:

- Grammar specification đã review.
- Hand-authored expected AST.
- Parser độc lập thứ hai nếu có.
- Golden parse tree được review.
- Các property ngôn ngữ đã định nghĩa.

### 3.2. Grammar ambiguity

Nếu một chuỗi có nhiều cách parse, grammar cần giải quyết bằng precedence, associativity hoặc quy tắc disambiguation. Test phải bao phủ các trường hợp mơ hồ đã được xác định.

### 3.3. Grammar version

Nếu DSL có language version, test cần gắn source với version cụ thể. Cùng một cú pháp có thể hợp lệ ở version mới nhưng bị cấm ở version cũ.

## 4. Unit test cho lexer

Lexer test xác nhận chuỗi ký tự được chuyển thành token đúng loại, giá trị và source range.

Ví dụ input:

~~~text
replicas = 12
enabled = true
name = "orders"
~~~

Token stream mong đợi:

| Token | Lexeme hoặc value |
|---|---|
| IDENTIFIER | replicas |
| EQUAL | = |
| INTEGER | 12 |
| IDENTIFIER | enabled |
| EQUAL | = |
| BOOLEAN | true |
| IDENTIFIER | name |
| EQUAL | = |
| STRING | orders |

### 4.1. Keyword và identifier

Kiểm tra keyword được nhận diện đúng mà không biến identifier có cùng tiền tố thành keyword:

~~~text
service "api" {}
serviceName = "catalog"
service2 = "worker"
~~~

Nếu grammar cho phép identifier bắt đầu bằng keyword, lexer cần áp dụng quy tắc longest match hoặc keyword lookup chính xác.

### 4.2. Number literal

Kiểm tra:

- Số nguyên.
- Số thập phân.
- Số âm nếu dấu âm là unary operator.
- Exponent notation nếu hỗ trợ.
- Dấu phân cách digit nếu có.
- Số vượt range.
- Literal thiếu chữ số.

Ví dụ:

~~~text
0
42
3.14
1e6
~~~

Lexer cần phân biệt tokenization với semantic range checking. Một numeric literal có thể tokenize thành công nhưng vượt kiểu số mà compiler hỗ trợ.

### 4.3. String literal

Kiểm tra:

- Chuỗi rỗng.
- Chuỗi có dấu nháy được escape.
- Backslash.
- Newline escape.
- Unicode escape.
- Kết thúc file khi chuỗi chưa đóng.
- Escape sequence không hợp lệ.

### 4.4. Operator dài và ngắn

Nếu DSL có cả = và ==, < và <=, ! và !=, lexer phải chọn token dài nhất theo grammar.

### 4.5. Comment và whitespace

Kiểm tra comment dòng, comment block, tab, space, newline kiểu LF/CRLF và comment ở cuối file. Whitespace thường không ảnh hưởng semantics nhưng có thể ảnh hưởng source location.

### 4.6. Unicode

Kiểm tra identifier Unicode nếu grammar cho phép, string có emoji, combining character và ký tự ngoài BMP. Xác định source offset dùng byte, UTF-16 code unit hay Unicode code point.

## 5. Unit test cho parser

Parser test thường tạo token stream hoặc source rồi so sánh AST với cấu trúc mong đợi.

Ví dụ source:

~~~text
let replicas = 3
~~~

AST mong đợi:

~~~text
VariableDeclaration
  name: "replicas"
  initializer:
    IntegerLiteral(3)
~~~

### 5.1. Test từng production rule

Mỗi production quan trọng nên có ít nhất:

- Một ví dụ hợp lệ cơ bản.
- Một ví dụ hợp lệ có thành phần tùy chọn.
- Một ví dụ ở biên.
- Một ví dụ không hợp lệ gần nhất.

### 5.2. Test block

~~~text
service "api" {
    replicas = 2
}
~~~

Xác nhận:

- Tên service đúng.
- Block được gắn vào declaration.
- Attribute nằm trong block.
- Giá trị là IntegerLiteral.
- Source range của declaration và attribute đúng.

### 5.3. Test list

~~~text
regions = ["asia", "europe", "us"]
~~~

Kiểm tra số phần tử, thứ tự và literal value.

### 5.4. Test map

~~~text
labels = {
    team = "commerce"
    tier = "backend"
}
~~~

Kiểm tra key-value pairing, key duplicate và separator theo grammar.

### 5.5. Test function call

~~~text
region = chooseRegion("staging", fallback = "local")
~~~

Kiểm tra tên function, positional argument, named argument và thứ tự nếu có ý nghĩa.

### 5.6. Test reference

~~~text
network = network.backend
~~~

Parser cần tạo reference node đúng cấu trúc. Việc network.backend có tồn tại hay không thuộc name resolution.

## 6. Kiểm thử expression precedence

Precedence quyết định operator nào được nhóm trước khi tạo AST. Sai precedence có thể làm thay đổi kết quả thực thi mà source vẫn parse thành công.

Ví dụ:

~~~text
1 + 2 * 3
~~~

Nếu multiplication có precedence cao hơn addition, AST phải là:

~~~text
Add
  1
  Multiply
    2
    3
~~~

Kết quả theo semantics số học thông thường là 7, không phải 9.

### 6.1. Test từng cặp operator

Nếu DSL có nhiều nhóm operator, test các cặp có thể cạnh tranh:

| Nhóm | Ví dụ |
|---|---|
| Unary và multiplicative | -a * b |
| Multiplicative và additive | a + b * c |
| Comparison và equality | a < b == c |
| Equality và logical AND | a == b && c |
| Logical AND và OR | a && b || c |
| Conditional | condition ? left : right |

Grammar thực tế có thể dùng keyword thay vì ký hiệu. Điều quan trọng là xác minh cấu trúc AST theo bảng precedence.

### 6.2. Parentheses

Ngoặc phải thay đổi grouping theo ý định:

~~~text
(1 + 2) * 3
~~~

AST cần có Multiply ở root và Add ở child.

### 6.3. Associativity

Với phép trừ, left associativity thường có nghĩa:

~~~text
a - b - c
~~~

được parse thành:

~~~text
Subtract
  Subtract(a, b)
  c
~~~

Với assignment hoặc exponentiation, grammar có thể chọn right associativity. Cần test rõ thay vì suy ra từ một ví dụ đơn lẻ.

### 6.4. Non-associative operator

Một số DSL không cho phép chain comparison như a < b < c. Parser nên từ chối nếu grammar không hỗ trợ, thay vì tự chọn grouping không được công bố.

### 6.5. Unary operator

Test chuỗi như -a, !enabled, --value nếu DSL có cú pháp tương ứng. Cần xác định dấu âm là unary node hay một phần numeric token.

## 7. Kiểm thử grammar lồng nhau

DSL thường cho phép block, expression, list hoặc function call lồng nhau. Đây là vùng dễ phát sinh lỗi parse.

Ví dụ:

~~~text
service "api" {
    environment = {
        region = "asia"
        labels = {
            team = "commerce"
        }
    }
}
~~~

Test cần xác nhận mỗi dấu ngoặc mở được ghép với đúng dấu đóng và node con nằm trong đúng parent.

### 7.1. Nested block

Tạo nhiều cấp block và xác nhận cây AST phản ánh chính xác quan hệ cha-con.

### 7.2. Nested collection

Test list chứa map, map chứa list và collection lồng nhau theo mức grammar cho phép.

### 7.3. Delimiter matching

Kiểm tra ngoặc nhọn, ngoặc tròn, ngoặc vuông và separator. Thiếu hoặc thừa delimiter cần tạo diagnostic rõ.

### 7.4. Separator rules

Nếu DSL dùng comma, newline hoặc semicolon để phân cách phần tử, test các trường hợp:

- Separator bắt buộc.
- Trailing separator được phép hay không.
- Hai separator liên tiếp.
- Separator trước dấu đóng.
- Newline giữa expression.

### 7.5. Empty construct

Kiểm tra block rỗng, list rỗng, argument list rỗng và map rỗng theo grammar.

## 8. Kiểm thử source hợp lệ

Positive tests xác nhận parser chấp nhận những chương trình nằm trong grammar.

Một bộ test nên bao gồm:

- Minimal valid program.
- Mỗi loại declaration.
- Mỗi loại expression.
- Block lồng nhau.
- Comment và whitespace.
- Literal và escape.
- Import/include.
- Annotation hoặc metadata.
- Tính năng theo language version.

### 8.1. Minimal examples

Ví dụ nhỏ nhất giúp cô lập production rule và dễ xác định regression.

### 8.2. Representative examples

Ví dụ gần với source thực tế giúp xác nhận các thành phần phối hợp đúng. Tuy nhiên, test nhỏ vẫn cần thiết để khi thất bại có thể khoanh vùng nhanh.

### 8.3. Corpus của chương trình hợp lệ

Có thể duy trì một corpus gồm các file DSL thực tế đã được review và dùng làm regression suite. Mỗi file cần có version grammar và kỳ vọng parse status.

### 8.4. Versioned examples

Nếu parser hỗ trợ nhiều language version, mỗi fixture nên chỉ rõ version. Không để test phụ thuộc vào default version ngầm.

## 9. Kiểm thử source không hợp lệ

Negative tests xác nhận parser từ chối cú pháp sai và không tạo ra kết quả nguy hiểm.

Các loại input:

- Thiếu keyword.
- Thừa token.
- Thiếu dấu đóng.
- String chưa đóng.
- Expression thiếu operand.
- Separator sai.
- Token không được hỗ trợ.
- Declaration sai vị trí.
- Construct không hợp lệ trong language version.

Ví dụ:

~~~text
service "api" {
    replicas =
}
~~~

Parser nên báo thiếu expression sau dấu bằng.

### 9.1. Một lỗi tại một thời điểm

Test đơn lỗi giúp xác định diagnostic mong đợi. Sau đó bổ sung test nhiều lỗi để kiểm tra recovery.

### 9.2. Invalid token

Ký tự không thuộc grammar cần được nhận diện rõ. Lexer không nên âm thầm bỏ qua ký tự không hợp lệ.

### 9.3. Unexpected end of input

File bị cắt giữa string, block hoặc expression cần báo lỗi EOF phù hợp. Không được truy cập token ngoài giới hạn hoặc treo chờ thêm input trong API parse file hoàn chỉnh.

### 9.4. Trailing garbage

Nếu chương trình hợp lệ kết thúc rồi còn token thừa, parser cần báo lỗi. Không nên parse prefix thành công và bỏ qua phần còn lại trừ khi API được thiết kế rõ là parse fragment.

### 9.5. Error message ổn định ở mức cần thiết

Machine-readable error code và source range nên ổn định. Message text có thể được cải thiện, vì vậy test nên tránh phụ thuộc quá chặt vào toàn bộ câu chữ trừ khi wording là public contract.

## 10. Kiểm thử error recovery

Parser IDE hoặc compiler thường cần tiếp tục phân tích sau lỗi để hiển thị nhiều diagnostic. Đây là error recovery.

Ví dụ:

~~~text
service "api" {
    replicas =
    enabled = true
    port = 8080
}
~~~

Parser có thể báo lỗi ở replicas nhưng vẫn nhận diện enabled và port.

### 10.1. Synchronization point

Parser có thể phục hồi tại token như newline, semicolon, dấu đóng block hoặc keyword declaration. Test cần xác nhận recovery không nuốt mất declaration kế tiếp.

### 10.2. Không tạo cascade diagnostics quá mức

Một lỗi gốc có thể khiến parser báo hàng trăm lỗi phụ. Test nên xác nhận số lượng và vị trí diagnostics hợp lý, có giới hạn.

### 10.3. Partial AST

Nếu parser tạo AST không hoàn chỉnh, node lỗi cần được đánh dấu rõ như ErrorNode hoặc MissingExpression. Downstream không được coi node này là expression hợp lệ.

### 10.4. Recovery không thay đổi source

Parser không nên âm thầm sửa source hoặc ghi lại file. Nếu có automatic fix, nó cần là một action riêng với edit range được mô tả.

### 10.5. IDE incremental parse

Trong editor, source có thể tạm thời không hợp lệ khi người dùng đang gõ. Parser cần giữ cấu trúc đủ để diagnostics và completion tiếp tục hoạt động, đồng thời cập nhật khi source thay đổi.

## 11. Kiểm thử source location và diagnostics

Source location rất quan trọng cho IDE, compiler error và toolchain. Parser cần gắn source span chính xác vào node và diagnostic.

Thông tin thường gồm:

- File hoặc source ID.
- Start offset.
- End offset.
- Start line và column.
- End line và column.
- Related location.
- Severity và diagnostic code.

### 11.1. Token location

Kiểm tra token bắt đầu và kết thúc đúng vị trí, đặc biệt với tab, CRLF, Unicode và escape sequence.

### 11.2. Node span

Một declaration span có thể bao gồm keyword, identifier và block. Test cần xác định range có bao gồm dấu đóng hay không theo contract của AST.

### 11.3. Error span

Diagnostic nên highlight token gây lỗi hoặc vị trí cần có token. Với missing token, range có thể là zero-width insertion point.

### 11.4. Unicode offset

Một số runtime đếm UTF-16 code unit, một số API dùng Unicode code point hoặc UTF-8 byte offset. Cần thống nhất cách biểu diễn và test ký tự ngoài BMP để tránh highlight sai.

### 11.5. Multiple source files

Nếu DSL hỗ trợ import, source range cần giữ source ID của file gốc. Diagnostic trong module được import không nên bị gán nhầm vào file gọi import.

### 11.6. Related diagnostics

Với duplicate declaration hoặc unmatched delimiter, parser có thể chỉ ra cả vị trí hiện tại và vị trí liên quan. Test xác nhận related location trỏ đúng source.

## 12. Golden tests cho parse tree và AST

Golden test lưu output chuẩn để so sánh với kết quả parser mới.

Ví dụ fixture:

~~~text
Input:
let count = 1 + 2 * 3

Expected AST:
VariableDeclaration(name="count")
  Add
    IntegerLiteral(1)
    Multiply
      IntegerLiteral(2)
      IntegerLiteral(3)
~~~

### 12.1. Ưu điểm

- Dễ xem thay đổi cấu trúc.
- Phù hợp với grammar lớn.
- Phát hiện regression trong node type hoặc source span.
- Hữu ích khi parser được sinh từ grammar.

### 12.2. Rủi ro

Golden file có thể quá nhạy với thay đổi không thuộc contract, như formatting hoặc internal node name. Cần serialize AST theo một representation ổn định dành riêng cho test.

### 12.3. Review golden diff

Khi golden output thay đổi, reviewer cần xác định thay đổi là:

- Cải tiến parser có chủ đích.
- Thay đổi grammar.
- Thay đổi AST schema.
- Regression.
- Chỉ là khác biệt formatting.

Không nên tự động cập nhật mọi golden file chỉ để làm CI xanh.

### 12.4. Golden diagnostic

Có thể snapshot diagnostic code, severity, source range và related locations. Nên tránh snapshot stack trace hoặc message nội bộ không ổn định.

## 13. Property-based testing cho parser

Property-based testing tạo nhiều input theo generator và xác nhận các tính chất tổng quát thay vì chỉ kiểm tra một vài ví dụ cố định.

Các property hữu ích:

- Parse rồi pretty-print rồi parse lại giữ cùng AST semantics.
- Mọi source hợp lệ được sinh bởi AST generator đều parse thành công.
- Parser không crash với bất kỳ byte sequence nào trong giới hạn test.
- Thêm comment hoặc whitespace ở vị trí được phép không đổi AST semantics.
- Thay đổi tên identifier không làm đổi cấu trúc node.
- Parse cùng source nhiều lần cho cùng kết quả.

### 13.1. Generate AST rồi serialize

Một cách test mạnh:

1. Sinh AST hợp lệ theo model.
2. Pretty-printer tạo source.
3. Parser đọc source.
4. Chuẩn hóa AST trước và sau.
5. So sánh semantics.

~~~text
AST generator
     |
     v
Pretty printer
     |
     v
Source text
     |
     v
Parser
     |
     v
Parsed AST
     |
     v
Semantic comparison
~~~

Nếu thất bại, property framework có thể shrink input để tìm ví dụ nhỏ nhất tái hiện bug.

### 13.2. Generate source từ grammar

Grammar-based generator tạo token và production hợp lệ. Nó giúp khám phá tổ hợp syntax mà developer ít nghĩ tới.

### 13.3. Invalid mutation

Từ một source hợp lệ, thay đổi một token, xóa delimiter hoặc đổi separator để tạo source gần hợp lệ nhưng sai. Điều này rất hữu ích cho negative tests.

### 13.4. Shrinking

Khi input lớn gây lỗi, shrinking loại bỏ declaration, expression hoặc token không cần thiết cho đến khi còn một trường hợp tối giản.

### 13.5. Seed và reproducibility

Ghi seed và minimized input để tái hiện lỗi. Không dựa vào random test không có seed vì bug có thể khó tái hiện trong CI.

## 14. Fuzz testing

Fuzzing đưa lượng lớn input được tạo tự động vào parser để tìm crash, hang, memory exhaustion hoặc trạng thái nội bộ bất thường.

Các chiến lược:

- Byte-level fuzzing.
- Token-level fuzzing.
- Grammar-based fuzzing.
- Mutation-based fuzzing.
- Differential fuzzing.

### 14.1. Byte-level fuzzing

Sinh byte sequence ngẫu nhiên để kiểm tra lexer và parser không crash với encoding hoặc ký tự bất thường.

### 14.2. Grammar-based fuzzing

Sinh source dựa trên grammar để tạo input có cấu trúc sâu và nhiều tổ hợp hợp lệ.

### 14.3. Mutation fuzzing

Bắt đầu từ corpus source thật rồi thay đổi byte, token, delimiter, literal hoặc vị trí comment.

### 14.4. Fuzz harness

Harness nên gọi parser trong giới hạn thời gian và memory. Một input không được phép làm cả fuzzing worker treo vô hạn.

### 14.5. Crash và hang

Ghi nhận:

- Input gây lỗi.
- Seed.
- Stack trace hoặc crash signature nội bộ.
- Thời gian chạy.
- Peak memory.
- Parser version.

### 14.6. Corpus management

Giữ các input đã tìm ra bug như regression corpus. Loại bỏ duplicate nhưng không xóa mẫu nhỏ có khả năng phát hiện một class lỗi riêng.

### 14.7. Security boundary

Fuzzing parser không nên chạy với secret production hoặc filesystem/network capability rộng. Dùng process/container cô lập.

## 15. Differential testing

Differential testing so sánh kết quả của hai implementation độc lập trên cùng input.

Ví dụ:

- Parser hand-written và parser generated từ grammar.
- Parser phiên bản mới và phiên bản cũ.
- Parser của compiler và parser trong editor.
- Hai backend parser hỗ trợ cùng language version.

Nếu kết quả khác nhau, cần xác định implementation nào phù hợp specification.

### 15.1. Normalize trước khi so sánh

Hai parser có thể tạo AST khác về node trung gian hoặc source metadata nhưng cùng semantics. Cần normalize hoặc so sánh một representation chung.

### 15.2. Không dùng majority vote thay specification

Nếu hai parser đồng ý và một parser khác biệt, hai parser kia vẫn có thể cùng sai. Grammar và language contract mới là chuẩn cuối cùng.

### 15.3. Version comparison

Differential test giữa parser version cũ và mới hữu ích khi thay grammar. Các khác biệt cần được phân loại là thay đổi có chủ đích, bug fix hay breaking change.

## 16. Metamorphic testing

Metamorphic testing xác định cách kết quả phải thay đổi khi input được biến đổi theo một quy tắc đã biết.

Ví dụ:

- Thêm whitespace hợp lệ không đổi AST semantics.
- Thêm comment không đổi AST semantics.
- Thêm parentheses quanh expression không đổi grouping nếu parentheses không thay đổi precedence.
- Đổi tên một identifier không đổi loại node.
- Đổi newline LF sang CRLF không đổi semantics.

### 16.1. Whitespace transformation

Tạo nhiều biến thể spacing và newline cho cùng source. Parse result sau khi bỏ source span cần tương đương.

### 16.2. Comment insertion

Chèn comment tại vị trí được grammar cho phép. Kiểm tra comment không bị đưa nhầm vào expression hoặc làm mất token lân cận.

### 16.3. Parentheses transformation

Thêm ngoặc không cần thiết quanh một expression. Cần so sánh AST sau khi loại ParenthesizedExpression node nếu AST giữ node này.

### 16.4. Formatting transformation

Pretty-printer có thể thay đổi indentation và line break nhưng không được đổi semantics.

### 16.5. Metamorphic relation cần được chứng minh

Không phải mọi biến đổi hình thức đều bảo toàn semantics. Ví dụ newline có thể kết thúc statement trong một số DSL. Chỉ dùng transformation được grammar xác nhận là tương đương.

## 17. Kiểm thử parser generator và grammar changes

Một số DSL dùng parser generator như ANTLR, JavaCC, yacc/bison hoặc parser combinator. Khi grammar thay đổi, cần test cả generated parser và integration với AST builder.

### 17.1. Grammar compile

CI cần xác nhận grammar file được parser generator xử lý thành công và không có conflict ngoài dự kiến.

### 17.2. Ambiguity và conflict

Parser generator có thể báo shift/reduce hoặc reduce/reduce conflict. Nếu conflict được chấp nhận, cần hiểu precedence resolution và có test cho các trường hợp liên quan.

### 17.3. Generated parser consistency

Generated source cần được cập nhật đúng với grammar version. Nếu generated code được commit, test cần phát hiện file sinh ra đã stale.

### 17.4. Semantic action

Nếu grammar có embedded action, test cần xác nhận action không gây side effect bất ngờ và tạo AST đúng. Có thể tách grammar recognition khỏi AST construction để dễ test hơn.

### 17.5. Parser combinator

Với parser combinator, test cần bao phủ backtracking, cut/commit behavior, error labeling và complexity của alternative. Một số combinator có thể thử lại nhiều nhánh và gây thời gian tăng mạnh.

## 18. Kiểm thử ambiguity và disambiguation

Grammar mơ hồ có thể khiến cùng source được hiểu theo nhiều cách hoặc phụ thuộc thứ tự rule.

Ví dụ:

~~~text
value = a + b * c
~~~

Nếu grammar không định nghĩa precedence, parser generator hoặc implementation có thể chọn grouping không mong muốn.

### 18.1. Dangling else

Ngôn ngữ có if lồng nhau cần quy định else gắn với if nào. Test phải xác nhận quy tắc đã chọn.

### 18.2. Identifier và keyword

Test tên giống hoặc chứa keyword để xác nhận tokenization. Ví dụ serviceName có được xem là identifier hay bị tách thành service và Name.

### 18.3. Generic và comparison

Nếu DSL có generic syntax dùng dấu ngoặc nhọn và comparison dùng dấu nhỏ/lớn, cần test các trường hợp parser có thể nhầm.

### 18.4. Newline sensitivity

Nếu newline có ý nghĩa phân cách statement, grammar cần xác định khi nào newline được phép bên trong expression hoặc argument list.

### 18.5. Explicit disambiguation

Có thể dùng parentheses, keyword hoặc separator để loại ambiguity. Test nên bảo vệ cả cú pháp hợp lệ và diagnostic khi thiếu disambiguation.

## 19. Kiểm thử incremental parser

Editor thường không parse lại toàn bộ file sau mỗi ký tự. Incremental parser cập nhật parse tree khi source thay đổi.

### 19.1. Edit sequence

Test có thể mô phỏng:

1. Parse source ban đầu.
2. Chèn một ký tự.
3. Xóa delimiter.
4. Hoàn thiện expression.
5. So sánh incremental result với full parse result.

### 19.2. Tree reuse

Incremental parser có thể tái sử dụng subtree không bị ảnh hưởng. Test cần xác nhận node reuse không làm giữ source range hoặc parent reference cũ.

### 19.3. Invalid intermediate state

Trong lúc gõ, source có thể tạm thời thiếu dấu ngoặc hoặc expression. Parser cần trả partial tree và diagnostic, không crash.

### 19.4. Equivalence với full parse

Sau một chuỗi edit, incremental parse tree cần tương đương full parse của source cuối cùng theo semantics và source locations.

### 19.5. Cancellation

Editor có thể gửi request parse mới trước khi request cũ kết thúc. Parser cũ nên hỗ trợ cancellation để không tích lũy công việc lỗi thời.

## 20. Kiểm thử performance và resource behavior

Parser cần được kiểm thử về hiệu năng vì input hợp lệ hoặc độc hại có thể tạo chi phí lớn.

Các chỉ số:

- Throughput.
- Parse latency.
- Peak memory.
- Token count.
- AST node count.
- Allocation count.
- Garbage collection time.
- Error recovery cost.
- Scaling theo source size.

### 20.1. Linear scaling

Với grammar và input class phù hợp, parse time thường nên tăng gần tuyến tính theo kích thước source. Không nên giả định mọi grammar có complexity tuyến tính; benchmark cần theo dõi các pattern có thể gây backtracking.

### 20.2. Worst-case input

Test nesting sâu, nhiều alternative, identifier dài, string dài và nhiều lỗi liên tiếp.

### 20.3. Backtracking

Parser có backtracking cần test input khiến nhiều alternative thất bại gần cuối. Tránh grammar hoặc parser design có exponential behavior.

### 20.4. Resource limits

Kiểm tra max input bytes, token count, nesting depth, AST nodes và parse deadline. Khi vượt ngưỡng, parser phải dừng có kiểm soát.

### 20.5. Benchmark không phải correctness test

Benchmark đo xu hướng và regression hiệu năng; unit test xác nhận kết quả đúng. Không nên để test thời gian quá chặt trên shared CI vì scheduler và máy chạy có thể khác nhau.

## 21. Kiểm thử Unicode, encoding và newline

Source DSL thường được lưu UTF-8 nhưng toolchain có thể nhận nhiều encoding hoặc newline style.

Các trường hợp:

- UTF-8 có hoặc không có BOM.
- LF và CRLF.
- Tab và space.
- Unicode combining characters.
- Ký tự ngoài BMP.
- Invalid UTF-8 sequence.
- Zero-width character.
- Non-breaking space.
- Bidirectional control character.

### 21.1. Encoding contract

Xác định parser chỉ nhận UTF-8 hay hỗ trợ encoding khác. Nếu input sai encoding, báo lỗi rõ thay vì thay ký tự im lặng.

### 21.2. Normalization

Unicode có thể có nhiều chuỗi code point biểu diễn cùng ký tự nhìn thấy. Nếu identifier cần normalization, specification phải nêu rõ form và tác động đến name equality.

### 21.3. Confusable characters

Ký tự trông giống nhau từ nhiều script có thể gây nhầm tên. Một số DSL có thể cảnh báo hoặc giới hạn identifier script. Đây là chính sách language/security riêng và cần test.

### 21.4. Bidirectional controls

Control character có thể làm source hiển thị khác thứ tự đọc. Tooling có thể cảnh báo hoặc hiển thị escaped representation trong diagnostics.

### 21.5. Source column

Test location với tab, emoji và combining character để bảo đảm editor highlight đúng. Cần phân biệt visual column với code unit offset.

## 22. Kiểm thử comment, documentation và annotation

Comment thường bị bỏ qua trong AST semantics nhưng có thể ảnh hưởng formatter hoặc documentation generator.

Test:

- Comment dòng.
- Comment block.
- Comment lồng nhau nếu hỗ trợ.
- Comment chứa delimiter.
- Documentation comment gắn declaration.
- Annotation trước declaration.
- Annotation sai vị trí.
- Comment ở cuối file.

Ví dụ:

~~~text
/// Service that processes orders.
@owner("commerce")
service "orders-api" {
    replicas = 3 # default production capacity
}
~~~

Nếu comment hoặc annotation được giữ trong AST, test cần xác nhận attachment đúng declaration.

## 23. Kiểm thử import, include và module syntax

Parser có thể đọc cú pháp import:

~~~text
import "modules/network.dsl"
~~~

Parser chỉ xác nhận cấu trúc import. File có tồn tại và có được phép truy cập hay không thuộc module resolver hoặc loader.

### 23.1. Import syntax

Kiểm tra string path, alias, version constraint và import modifier nếu grammar hỗ trợ.

### 23.2. Import placement

Nếu import chỉ được phép ở đầu module, parser hoặc semantic checker cần xác định và test quy tắc đó.

### 23.3. Duplicate import

Parser có thể tạo nhiều import declaration; resolver mới quyết định deduplicate hoặc báo lỗi theo semantics. Test phải phân biệt hai lớp.

### 23.4. Source mapping

Declaration đến từ imported file phải giữ source identity của file đó.

### 23.5. Không truy cập filesystem trong parser unit test

Parser nên nhận token/source đã có. File loading là trách nhiệm riêng, giúp unit test parser deterministic và không phụ thuộc filesystem.

## 24. Test architecture và tổ chức test suite

Một parser test suite có thể chia theo tầng:

~~~text
parser-tests/
    lexer/
        identifiers
        literals
        comments
        unicode
    syntax/
        declarations
        blocks
        expressions
        collections
    precedence/
        arithmetic
        comparison
        logical
    diagnostics/
        invalid-token
        missing-delimiter
        source-ranges
        recovery
    properties/
        round-trip
        whitespace
        grammar-generated
    fuzz/
        corpus
        regression
    performance/
        large-source
        deep-nesting
~~~

Đây là cách tổ chức minh họa. Có thể nhóm theo module hoặc grammar rule của dự án.

### 24.1. Test fixture nhỏ

Mỗi fixture nên tập trung vào một rule hoặc một behavior để dễ hiểu và debug.

### 24.2. Shared assertion

Tạo helper so sánh AST đã chuẩn hóa, diagnostic code và source range. Helper không nên che giấu khác biệt quan trọng.

### 24.3. Corpus regression

Lưu input từng gây bug. Mỗi bug parser được sửa nên có regression fixture nhỏ nhất có thể.

### 24.4. Test naming

Tên test nên nêu grammar construct và expected behavior, ví dụ parses_nested_map_value hoặc reports_missing_closing_brace.

### 24.5. Deterministic test

Tránh test phụ thuộc thứ tự file, timezone, locale hoặc random seed không cố định. Parser output phải deterministic theo contract.

## 25. Ví dụ unit test parser

Ví dụ pseudocode theo phong cách Java:

~~~java
@Test
void parsesArithmeticWithMultiplicationPrecedence() {
    var result = parser.parseExpression("1 + 2 * 3");

    assertTrue(result.isSuccess());

    var expected = add(
        integer(1),
        multiply(integer(2), integer(3))
    );

    assertEquals(expected, normalize(result.ast()));
}
~~~

Test này kiểm tra AST structure. Nếu chỉ assert parse success, lỗi precedence sẽ không bị phát hiện.

### 25.1. Test invalid input

~~~java
@Test
void reportsMissingExpressionAfterAssignment() {
    var result = parser.parse("let count =");

    assertFalse(result.isSuccess());
    assertTrue(result.diagnostics().stream()
        .anyMatch(d -> d.code().equals("PARSE_EXPECTED_EXPRESSION")));
}
~~~

### 25.2. Test source range

~~~java
@Test
void pointsToUnexpectedToken() {
    var result = parser.parse("let count = )");

    var diagnostic = findDiagnostic(
        result,
        "PARSE_EXPECTED_EXPRESSION"
    );

    assertEquals(12, diagnostic.range().startOffset());
}
~~~

Offset trong ví dụ phụ thuộc quy ước của test harness và cách đếm ký tự. Test thực tế nên dùng source map helper để tránh nhầm byte với UTF-16 offset.

### 25.3. Test recovery

~~~java
@Test
void continuesAfterMalformedAttribute() {
    var result = parser.parse("""
        service "api" {
            replicas =
            enabled = true
        }
        """);

    assertTrue(hasDiagnostic(result, "PARSE_EXPECTED_EXPRESSION"));
    assertTrue(containsAttribute(result.partialAst(), "enabled"));
}
~~~

Đây là test cho parser hỗ trợ partial AST. Nếu contract của parser là fail-fast, expected behavior sẽ khác.

## 26. Ví dụ property test cho round-trip

Một property test có thể kiểm tra pretty-printer và parser:

~~~text
property "pretty printed AST parses back to equivalent AST":
    for each generated valid AST:
        source = prettyPrint(ast)
        parsed = parse(source)
        assert parsed.success
        assert normalize(parsed.ast) == normalize(ast)
~~~

### 26.1. Normalize

Normalization có thể loại bỏ:

- Parentheses node không có semantics riêng.
- Source location.
- Trivia không được giữ trong AST.
- Internal node ID.

Không loại bỏ thông tin có ảnh hưởng semantics như thứ tự list hoặc associativity.

### 26.2. Generator constraints

Generator phải tuân thủ grammar và giới hạn resource. Nếu sinh expression quá sâu, property test có thể chỉ kiểm tra limit behavior thay vì round-trip thông thường.

### 26.3. Shrinking

Khi property fail, framework nên rút gọn AST và source. Lưu minimized case vào regression corpus.

## 27. Parser test trong CI

Parser test thường chạy ở mỗi pull request vì thời gian tương đối thấp và lỗi ảnh hưởng rộng.

Một pipeline có thể:

1. Compile parser và grammar.
2. Chạy lexer unit tests.
3. Chạy parser positive/negative tests.
4. Chạy AST golden tests.
5. Chạy diagnostic tests.
6. Chạy property tests với seed cố định.
7. Chạy fuzz smoke tests có thời lượng giới hạn.
8. Chạy performance benchmark định kỳ hoặc trên thay đổi quan trọng.

### 27.1. Pull request gate

Các test deterministic và regression nên là required checks. Fuzzing dài và benchmark có thể chạy theo lịch hoặc trên dedicated runner.

### 27.2. Grammar change review

Khi sửa grammar, pull request nên kèm:

- Lý do thay đổi.
- Source trước/sau.
- AST difference.
- Compatibility impact.
- Updated fixtures.
- Parser generator conflict report nếu có.

### 27.3. Versioned test matrix

Nếu hỗ trợ nhiều language version, CI có thể chạy corpus tương ứng cho từng version và xác nhận deprecation behavior.

### 27.4. Reproducible failure

Fuzz failure cần publish seed và minimized input để CI hoặc developer có thể chạy lại.

## 28. Các lỗi thường gặp khi kiểm thử parser

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Chỉ kiểm tra parse success | Không phát hiện AST sai | So sánh cấu trúc AST |
| Chỉ test source hợp lệ | Parser có thể crash với input sai | Bổ sung negative và fuzz tests |
| Expected AST sinh bằng parser đang test | Bug có thể tự xác nhận | Dùng expected độc lập |
| Không test precedence | Expression được nhóm sai | Test từng nhóm operator |
| Không test associativity | AST sai khi chain operator | Dùng ví dụ nhiều toán hạng |
| Snapshot toàn bộ output không chuẩn hóa | Test dễ vỡ vì thay đổi nội bộ | Stable AST representation |
| Không test source range | IDE highlight sai | Kiểm tra offset và Unicode |
| Recovery nuốt declaration sau lỗi | Mất diagnostics và code completion | Test synchronization point |
| Fuzz không có timeout | Fuzzer có thể treo | Worker isolation và deadline |
| Không lưu fuzz regression | Bug cũ tái xuất hiện | Giữ minimized corpus |
| Parser unit test đọc file thật | Test chậm và không deterministic | Tách loader khỏi parser |
| Bỏ qua language version | Source cũ thay đổi semantics | Versioned grammar fixtures |
| Test performance trên runner nhiễu | Kết quả không ổn định | Benchmark riêng và theo dõi xu hướng |
| Cập nhật golden tự động không review | Che giấu breaking change | Review semantic diff |
| Chỉ test parser generator output | Không kiểm tra AST builder và integration | Test toàn pipeline parser-to-AST |

## 29. Quy trình xây dựng parser testing strategy

Có thể thực hiện theo các bước:

1. **Thu thập grammar:** xác định production rule, precedence và version.
2. **Xác định parser contract:** parse tree/AST, error behavior, source span và recovery.
3. **Tách lexer và parser tests:** kiểm tra tokenization độc lập với syntax.
4. **Tạo positive corpus:** mỗi construct có ví dụ tối thiểu và ví dụ đại diện.
5. **Tạo negative corpus:** missing token, unexpected token, delimiter và malformed literal.
6. **Kiểm tra AST:** xác nhận parent-child, precedence, associativity và node type.
7. **Kiểm tra diagnostics:** code, severity, source range và recovery.
8. **Thêm property tests:** round-trip, whitespace và grammar-generated source.
9. **Thêm fuzzing:** byte, token và grammar-based với sandbox.
10. **Thêm regression corpus:** giữ mọi input đã từng gây lỗi.
11. **Kiểm tra hiệu năng:** input lớn, nesting sâu và backtracking.
12. **Tích hợp CI:** deterministic gate, fuzz smoke và benchmark định kỳ.
13. **Quản lý language version:** test compatibility cho từng grammar version.

## 30. Ví dụ tổng hợp: parser cho DSL cấu hình

Giả sử DSL hỗ trợ service declaration, attributes, nested blocks và arithmetic expression.

Source:

~~~text
service "catalog" {
    replicas = 1 + 2 * 3

    resources {
        cpu = "500m"
        memory = "512Mi"
    }

    enabled = true
}
~~~

### 30.1. Lexer expectations

Lexer tạo token cho keyword service, string literal, brace, identifier, assignment, number, arithmetic operator, string và boolean literal.

### 30.2. Parser expectations

Parser tạo:

~~~text
ServiceDeclaration
  name: StringLiteral("catalog")
  body:
    Attribute("replicas")
      Add
        IntegerLiteral(1)
        Multiply
          IntegerLiteral(2)
          IntegerLiteral(3)
    Block("resources")
      Attribute("cpu")
        StringLiteral("500m")
      Attribute("memory")
        StringLiteral("512Mi")
    Attribute("enabled")
      BooleanLiteral(true)
~~~

### 30.3. Negative variation

Thay:

~~~text
replicas = 1 + * 3
~~~

Parser cần báo expression sai tại operator không có toán hạng phù hợp, giữ được source range và không làm mất các declaration sau đó nếu recovery được hỗ trợ.

### 30.4. Property variation

Thêm whitespace hoặc comment tại vị trí hợp lệ không đổi AST semantics. Đổi newline style không đổi cấu trúc.

### 30.5. Boundary variation

Tăng số nested block đến depth limit. Parser cần xử lý source ngay dưới giới hạn và từ chối source vượt giới hạn theo resource policy.

### 30.6. Regression

Lưu source ban đầu, malformed variation và minimized fuzz case vào corpus. Khi grammar hoặc parser implementation thay đổi, CI chạy lại tất cả các trường hợp này.

## 31. Tiêu chí của một parser test suite tốt

Một parser test suite tốt xác minh cả việc chấp nhận, từ chối và diễn giải source. Nó có expected AST độc lập, test precedence và associativity, kiểm tra diagnostics cùng source range, và bao phủ input bất thường. Property testing, fuzzing và performance tests bổ sung các trường hợp mà người viết test thủ công khó dự đoán.

Các câu hỏi quan trọng:

- Grammar và language version nào là oracle?
- Lexer có test riêng cho keyword, literal, operator, comment và Unicode không?
- Parser có test từng production rule không?
- AST test có xác nhận cấu trúc chứ không chỉ parse success không?
- Precedence, associativity và parentheses đã được kiểm tra chưa?
- Source hợp lệ, source sai và EOF bất thường đều có fixture chưa?
- Error recovery có giữ declaration phía sau lỗi không?
- Diagnostic code và source range có chính xác không?
- Golden output có representation ổn định và được review không?
- Property test có round-trip và metamorphic relation hợp lệ không?
- Fuzzer có seed, timeout, sandbox và regression corpus không?
- Incremental parser có tương đương full parse sau edit không?
- Unicode, newline và source offset có được kiểm tra không?
- Resource limit có được kiểm tra ở parser boundary không?
- CI có chạy parser regression mỗi lần thay grammar không?

Parser là cổng đầu tiên biến source DSL thành cấu trúc mà toàn bộ toolchain tin cậy. Khi parser testing bao phủ grammar, AST, precedence, diagnostics, recovery, Unicode, robustness và resource behavior, thay đổi ngôn ngữ có thể được thực hiện có kiểm soát. Bộ test tốt giúp người viết DSL nhận thông báo chính xác, giúp IDE hoạt động ổn định và giúp compiler tránh diễn giải source theo cách khác với ý định của người dùng.

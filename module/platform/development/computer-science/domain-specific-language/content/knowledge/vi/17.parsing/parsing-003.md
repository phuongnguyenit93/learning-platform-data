# Parser PEG

## 1. PEG là gì?

PEG (Parsing Expression Grammar) là một hình thức đặc tả ngữ pháp dùng để mô tả cách phân tích một chuỗi đầu vào. PEG thường được dùng để xây dựng parser cho ngôn ngữ lập trình, ngôn ngữ cấu hình, định dạng dữ liệu và ngôn ngữ miền chuyên biệt (Domain-Specific Language — DSL).

Điểm đặc trưng của PEG là **lựa chọn có thứ tự (ordered choice)**. Khi một biểu thức có nhiều phương án, parser thử phương án theo thứ tự được viết và chọn phương án đầu tiên thành công. Vì vậy, thứ tự các lựa chọn là một phần của ý nghĩa ngữ pháp.

Ví dụ một grammar PEG đơn giản:

~~~text
Start <- Greeting EOF
Greeting <- "hello" / "hi"
EOF <- !.
~~~

Greeting chấp nhận chuỗi hello hoặc hi. Dấu / biểu diễn lựa chọn có thứ tự: parser thử hello trước; nếu phương án đó thất bại, parser mới thử hi. EOF xác nhận đầu vào đã kết thúc để parser không chấp nhận một tiền tố hợp lệ rồi bỏ qua phần dư.

PEG phù hợp với DSL vì grammar có thể mô tả trực tiếp cấu trúc văn bản và các quy tắc từ vựng, đồng thời hỗ trợ lookahead để kiểm tra ngữ cảnh mà không tiêu thụ ký tự. Nhiều công cụ PEG có thể sinh parser hoặc cung cấp API để viết grammar trong mã nguồn.

## 2. PEG và CFG khác nhau như thế nào?

PEG và CFG (Context-Free Grammar) đều mô tả cấu trúc ngôn ngữ, nhưng cách hiểu phép lựa chọn khác nhau.

- Trong CFG, các phương án thay thế mô tả những khả năng của ngôn ngữ. Thứ tự viết các phương án không làm thay đổi ngôn ngữ được sinh ra.
- Trong PEG, phép / là lựa chọn có thứ tự. Parser ưu tiên phương án đứng trước và chỉ thử phương án tiếp theo nếu phương án trước thất bại ngay trong biểu thức lựa chọn.

Ví dụ:

~~~text
Choice <- "a" / "ab"
~~~

Trong PEG, với đầu vào ab, phương án a thành công trước nên Choice chỉ nhận phần a. Nếu grammar tiếp tục yêu cầu một ký tự c ở phía sau, parser không quay lại để chọn ab chỉ vì phần còn lại của chuỗi thất bại.

Đây là điểm quan trọng khi thiết kế grammar. Người viết PEG phải đặt phương án cụ thể trước phương án tổng quát khi muốn phương án cụ thể được ưu tiên.

| Tiêu chí | CFG | PEG |
|---|---|---|
| Phép lựa chọn | Các phương án thay thế không có thứ tự ưu tiên | Ordered choice, phương án đầu tiên thành công được chọn |
| Mơ hồ | Một chuỗi có thể có nhiều cách phân tích | Cách phân tích được xác định bởi thứ tự và quy tắc PEG |
| Lookahead | Có thể cần kỹ thuật hoặc parser strategy riêng | Có predicate dương và âm trong biểu thức PEG |
| Left recursion | Được hỗ trợ tự nhiên bởi nhiều parser LR | Nhiều PEG parser cơ bản không hỗ trợ trực tiếp; có thể biến đổi grammar hoặc dùng extension |
| Cách triển khai phổ biến | LL, LR, LALR, GLR và các parser generator tương ứng | Recursive descent có backtracking, packrat parsing hoặc PEG parser generator |
| Thiết kế grammar | Thường xử lý xung đột bằng phân tích grammar và parser strategy | Cần quan tâm đặc biệt đến thứ tự lựa chọn và hành vi tiêu thụ đầu vào |

Không nên xem PEG là phiên bản tốt hơn của mọi CFG. PEG thuận tiện cho nhiều ngôn ngữ có cú pháp được kiểm soát, nhưng grammar có thứ tự lựa chọn và quy tắc đệ quy cần được thiết kế cẩn thận.

## 3. Các thành phần cơ bản của biểu thức PEG

PEG xây dựng grammar từ các biểu thức nhỏ. Ký hiệu cụ thể có thể khác đôi chút giữa các công cụ, nhưng những toán tử sau là phổ biến.

### 3.1. Literal

Literal yêu cầu khớp một chuỗi ký tự cố định:

~~~text
Keyword <- "pipeline"
OpenBrace <- "{"
~~~

Nếu đầu vào tại vị trí hiện tại bắt đầu bằng chuỗi đã chỉ định, biểu thức thành công và tiêu thụ các ký tự đó. Nếu không, biểu thức thất bại.

Một số grammar dùng dấu nháy đơn cho literal:

~~~text
Keyword <- 'pipeline'
~~~

Quy ước dấu nháy, escape và xử lý chữ hoa thường phụ thuộc công cụ PEG. Đặc tả DSL cần nêu rõ nếu từ khóa không phân biệt hoa thường.

### 3.2. Sequence — chuỗi biểu thức

Sequence yêu cầu các biểu thức con thành công lần lượt theo thứ tự:

~~~text
Declaration <- "let" Spacing Identifier Spacing "=" Spacing Expression
~~~

Parser phải khớp từ khóa let, khoảng trắng, tên định danh, dấu bằng và biểu thức theo đúng thứ tự. Nếu một thành phần thất bại, toàn bộ sequence thất bại.

### 3.3. Ordered choice — lựa chọn có thứ tự

Dấu / thử các phương án từ trái sang phải:

~~~text
Boolean <- "true" / "false"
AddOp <- "+" / "-"
CompareOp <- ">=" / "<=" / "==" / "!=" / ">" / "<"
~~~

Với toán tử có tiền tố chung, nên đặt dạng dài trước dạng ngắn. Trong CompareOp, >= cần được thử trước >; nếu > đứng trước, parser có thể khớp một phần và làm phương án dài không còn cơ hội được chọn.

### 3.4. Zero-or-more — lặp không hoặc nhiều lần

Hậu tố * yêu cầu biểu thức trước nó khớp không hoặc nhiều lần:

~~~text
Digits <- [0-9]*
Arguments <- Expression ("," Expression)*
~~~

Biểu thức lặp có thể không khớp lần nào. Vì thế Digits cũng có thể nhận chuỗi rỗng; nếu cần ít nhất một chữ số, dùng +.

Trong PEG, phép lặp có tính tham lam: nó lấy nhiều lần khớp nhất có thể theo quy tắc của biểu thức. Không nên kỳ vọng parser tự giảm số lần lặp để cứu một phần sequence phía sau.

### 3.5. One-or-more — lặp ít nhất một lần

Hậu tố + yêu cầu ít nhất một lần khớp:

~~~text
IdentifierStart <- [A-Za-z_]
IdentifierContinue <- [A-Za-z0-9_]*
Identifier <- IdentifierStart IdentifierContinue
~~~

+ tương đương một lần biểu thức rồi đến *. Nó hữu ích cho chữ số, ký tự định danh hoặc danh sách phần tử bắt buộc có ít nhất một phần tử.

### 3.6. Optional — thành phần tùy chọn

Hậu tố ? cho phép biểu thức xuất hiện không hoặc một lần:

~~~text
ReturnStatement <- "return" Spacing Expression?
~~~

Ví dụ này cho phép câu lệnh return có hoặc không có biểu thức theo grammar. Nếu DSL không cho phép return rỗng, không nên dùng ? ở vị trí đó.

### 3.7. Positive lookahead

&e là predicate dương: kiểm tra biểu thức e có khớp tại vị trí hiện tại hay không, nhưng không tiêu thụ ký tự.

~~~text
Number <- [0-9]+ &(!IdentifierContinue)
~~~

Ví dụ trên yêu cầu sau dãy chữ số không có ký tự tiếp tục định danh. Predicate chỉ kiểm tra điều kiện ở vị trí kết thúc; phần đầu vào vẫn ở nguyên vị trí đó để các quy tắc tiếp theo xử lý.

### 3.8. Negative lookahead

!e là predicate âm: thành công khi e thất bại tại vị trí hiện tại, và cũng không tiêu thụ ký tự.

~~~text
Identifier <- !ReservedWord [A-Za-z_] [A-Za-z0-9_]*
~~~

Quy tắc này chỉ chấp nhận tên không phải từ khóa dành riêng. Predicate âm thường dùng để xác định ranh giới token, loại trừ từ khóa hoặc phát hiện cuối đầu vào.

### 3.9. Any character và character class

Dấu . thường đại diện cho một ký tự bất kỳ. Character class biểu diễn tập ký tự:

~~~text
Digit <- [0-9]
Letter <- [A-Za-z]
IdentifierStart <- [A-Za-z_]
~~~

Cách biểu diễn Unicode, ký tự xuống dòng và dải ký tự phụ thuộc công cụ. Nếu DSL cho phép tên tiếng Việt hoặc ký tự Unicode, grammar và implementation cần thống nhất cách nhận diện ký tự.

### 3.10. Grouping

Ngoặc tròn nhóm biểu thức để xác định phạm vi của toán tử:

~~~text
Unary <- ("not" / "-") Primary
~~~

Nhóm giúp thể hiện rõ các lựa chọn được áp dụng ở vị trí nào. Khi grammar dài, nên dùng tên rule để tăng khả năng đọc thay vì lồng nhiều nhóm phức tạp.

## 4. Cách PEG đánh giá một biểu thức

Parser PEG thường làm việc tại một vị trí trong chuỗi đầu vào. Mỗi biểu thức có thể thành công và trả về vị trí mới, hoặc thất bại.

Có thể hình dung kết quả của một lần phân tích như:

~~~text
ParseResult
    success: true | false
    nextPosition: vị trí sau phần đã khớp
    value: giá trị hoặc nút cú pháp (nếu có)
    failureInfo: thông tin lỗi (nếu thất bại)
~~~

Đây là mô hình khái niệm, không phải kiểu dữ liệu bắt buộc của PEG. Một parser thực tế có thể trả về AST, token, vị trí hoặc trạng thái nội bộ khác.

### 4.1. Sequence

Với grammar:

~~~text
Pair <- "a" "b"
~~~

Đầu vào ab làm cả hai literal thành công liên tiếp. Đầu vào ac làm literal thứ nhất thành công nhưng literal thứ hai thất bại; do đó toàn sequence thất bại.

### 4.2. Ordered choice

Với grammar:

~~~text
Value <- "true" / "false"
~~~

Parser thử true trước. Nếu đầu vào không khớp true, nó thử false. Nếu true khớp, lựa chọn hoàn tất với phương án đó.

### 4.3. Không quay lại lựa chọn đã thành công

Xét:

~~~text
Start <- ("a" / "ab") "c"
~~~

Đầu vào abc được xử lý như sau:

1. Trong nhóm lựa chọn, parser thử a và thành công.
2. Vì phương án đầu đã thành công, nhóm lựa chọn trả về kết quả a.
3. Sequence tiếp tục yêu cầu c tại vị trí kế tiếp, nhưng ký tự còn lại là b.
4. Sequence thất bại. Parser không quay lại nhóm để thay a bằng ab.

Nếu muốn nhận cả ac và abc, có thể đặt phương án dài trước:

~~~text
Start <- ("ab" / "a") "c"
~~~

Tuy nhiên, cách sắp xếp phương án chỉ đúng khi phản ánh ý định của ngôn ngữ. Đừng đảo thứ tự một cách máy móc nếu các nhánh có ngữ nghĩa khác nhau.

### 4.4. Lặp tham lam

Xét:

~~~text
Start <- "a"* "a"
~~~

Với đầu vào aaa, phần a* tiêu thụ cả ba ký tự; phần a cuối không còn ký tự để khớp nên sequence thất bại. Parser không tự nhả lại một ký tự từ phép lặp để làm phần cuối thành công.

Nếu mục tiêu là ít nhất một ký tự a, grammar nên viết:

~~~text
Start <- "a"+
~~~

Ví dụ cho thấy cần hiểu ngữ nghĩa của phép lặp thay vì dựa vào trực giác backtracking của một số regex engine.

## 5. Thiết kế ordered choice đúng cách

Thứ tự phương án là một phần của grammar PEG. Một lỗi thường gặp là đặt nhánh tổng quát trước nhánh cụ thể.

### 5.1. Đặt từ khóa dài trước tiền tố ngắn

~~~text
CompareOp <- ">=" / ">" / "<=" / "<"
~~~

Nếu đặt > trước >=, đầu vào >= có thể bị nhận là > trước, để lại dấu = không được xử lý.

### 5.2. Đặt từ khóa trước định danh tổng quát

Giả sử DSL có từ khóa if và định danh:

~~~text
KeywordIf <- "if"
Identifier <- [A-Za-z_] [A-Za-z0-9_]*
~~~

Nếu grammar thử Identifier trước trong một lựa chọn, đầu vào if có thể bị nhận như tên định danh. Cách giải quyết là thử từ khóa trước và kiểm tra ranh giới:

~~~text
IfKeyword <- "if" !IdentifierContinue
Identifier <- !ReservedWord IdentifierStart IdentifierContinue*
~~~

Ranh giới ngăn ifx bị nhận nhầm là từ khóa if.

### 5.3. Tránh nhánh tổng quát nuốt nhánh đặc biệt

Ví dụ một chuỗi có thể là tên thông thường hoặc từ khóa đặc biệt:

~~~text
Primary <- SpecialLiteral / Identifier
~~~

Đặt SpecialLiteral trước Identifier để các literal dành riêng được nhận diện đúng. Nếu dùng cách khác, cần negative lookahead để loại trừ tên dành riêng khỏi nhánh Identifier.

### 5.4. Phân tích tiền tố chung

Hai phương án có thể bắt đầu bằng cùng một chuỗi:

~~~text
Declaration <- "let" Spacing Identifier
             / "let" Spacing "const" Spacing Identifier
~~~

Grammar này có thể không hoạt động như dự kiến nếu nhánh đầu tiên nhận được tiền tố let rồi lựa chọn hoàn tất trước khi nhánh thứ hai có cơ hội. Có thể đặt nhánh cụ thể trước:

~~~text
Declaration <- "let" Spacing "const" Spacing Identifier
             / "let" Spacing Identifier
~~~

Hoặc phân tích tiền tố chung một lần:

~~~text
Declaration <- "let" Spacing ("const" Spacing)? Identifier
~~~

Việc factor tiền tố chung thường giúp grammar ngắn hơn và giảm lặp lại.

## 6. Lookahead và ranh giới token

Lookahead cho phép grammar kiểm tra ký tự tiếp theo mà không tiêu thụ nó. Đây là công cụ quan trọng để phân biệt từ khóa, định danh và các dạng cú pháp có tiền tố giống nhau.

### 6.1. Nhận diện từ khóa

~~~text
IdentifierStart <- [A-Za-z_]
IdentifierContinue <- [A-Za-z0-9_]
Identifier <- IdentifierStart IdentifierContinue*

IfKeyword <- "if" !IdentifierContinue
~~~

!IdentifierContinue yêu cầu ký tự sau if không phải phần tiếp tục của định danh. Vì vậy if là từ khóa, còn ifReady là định danh.

### 6.2. Loại trừ từ khóa khỏi tên

~~~text
ReservedWord <- "if" !IdentifierContinue
              / "else" !IdentifierContinue
              / "while" !IdentifierContinue

Identifier <- !ReservedWord IdentifierStart IdentifierContinue*
~~~

Ở vị trí bắt đầu định danh, parser trước hết xác nhận đầu vào không phải từ khóa dành riêng, rồi mới nhận dãy ký tự định danh.

### 6.3. Kiểm tra cuối đầu vào

PEG thường biểu diễn EOF bằng negative lookahead với ký hiệu khớp một ký tự bất kỳ:

~~~text
EOF <- !.
Start <- Expression EOF
~~~

Nếu Expression chỉ khớp một tiền tố và còn ký tự dư, EOF thất bại. Nhờ đó parser không chấp nhận âm thầm một chương trình chỉ được phân tích một phần.

### 6.4. Predicate không tiêu thụ đầu vào

Ví dụ:

~~~text
Number <- [0-9]+ &("," / ")" / EOF)
~~~

Predicate dương kiểm tra sau số là dấu phẩy, dấu đóng ngoặc hoặc cuối đầu vào. Ký tự phân cách vẫn còn ở vị trí hiện tại để quy tắc chứa số xử lý tiếp.

Lookahead nên được dùng cho điều kiện ngắn và dễ hiểu. Predicate phức tạp lặp lại ở nhiều rule có thể khiến grammar khó đọc và khó chẩn đoán lỗi.

## 7. Whitespace và comment trong PEG

PEG không tự động bỏ qua khoảng trắng trừ khi grammar hoặc công cụ có quy ước riêng. Người thiết kế cần xác định rõ khoảng trắng, dòng mới và chú thích thuộc về cú pháp như thế nào.

### 7.1. Khoảng trắng ngang

Một DSL có thể định nghĩa:

~~~text
HSpace <- [ \t]*
HSpace1 <- [ \t]+
~~~

HSpace cho phép không hoặc nhiều dấu cách/tab; HSpace1 yêu cầu ít nhất một. Dùng HSpace1 giữa từ khóa và tên có thể tránh chấp nhận những cách viết dính liền như source"orders.csv" nếu DSL không muốn hỗ trợ.

### 7.2. Khoảng trắng tổng quát

Nếu newline không có ý nghĩa cấu trúc, có thể dùng:

~~~text
Spacing <- [ \t\r\n]*
~~~

Nếu newline kết thúc câu lệnh hoặc mở/đóng block, không nên gộp newline vào Spacing ở mọi vị trí. Cần tách HSpace và Newline để grammar kiểm soát rõ cấu trúc dòng.

### 7.3. Comment một dòng

Ví dụ DSL dùng #:

~~~text
Comment <- "#" (!Newline .)*
Newline <- "\r\n" / "\n" / "\r"
~~~

Comment tiêu thụ nội dung từ dấu # đến trước newline. Nếu newline là ranh giới câu lệnh, comment không nên tự tiêu thụ newline trừ khi grammar chủ động quy định như vậy.

### 7.4. Comment nhiều dòng

Một dạng comment nhiều dòng có thể được mô tả:

~~~text
BlockComment <- "/*" (!"*/" .)* "*/"
~~~

Grammar này minh họa comment không lồng nhau. Nếu DSL cho phép comment lồng nhau, rule đơn giản trên chưa đủ; cần parser state hoặc grammar chuyên biệt.

### 7.5. Quy tắc bỏ qua khoảng trắng có thể tái sử dụng

Một số grammar dùng quy ước mọi token tự tiêu thụ khoảng trắng phía sau:

~~~text
Token <- RawToken Spacing
~~~

Cách này giảm việc lặp Spacing trong grammar nhưng cần nhất quán. Nếu một số token cần giữ newline hoặc khoảng trắng để xác định cấu trúc, phải có rule riêng cho chúng.

## 8. Xây dựng grammar PEG cho một DSL nhỏ

Xét DSL pipeline:

~~~text
pipeline "daily" {
    source "orders.csv"
    filter amount >= 100 and status == "PAID"
    output "result.csv"
}
~~~

Mục tiêu là nhận diện khai báo pipeline, các câu lệnh source/filter/output và biểu thức điều kiện.

### 8.1. Grammar cấp cao

Một grammar minh họa:

~~~text
Start <- HSpace Pipeline HSpace EOF

Pipeline <- "pipeline" !IdentifierContinue HSpace1 String
            HSpace "{" Newline BodyLine* HSpace "}"

BodyLine <- HSpace (Statement / Comment)? HSpace Newline
Statement <- Source / Filter / Output

Source <- "source" !IdentifierContinue HSpace1 String
Filter <- "filter" !IdentifierContinue HSpace1 Expression
Output <- "output" !IdentifierContinue HSpace1 String

Comment <- "#" (!Newline .)*

HSpace <- [ \t]*
HSpace1 <- [ \t]+
Newline <- "\r\n" / "\n" / "\r"
EOF <- !.
~~~

Đây là grammar giản lược. Nó giả định mỗi câu lệnh nằm trên một dòng, phần thân pipeline có dấu ngoặc nhọn và chuỗi dùng dấu ngoặc kép. Nếu DSL hỗ trợ biểu thức nhiều dòng, dấu chấm phẩy hoặc block lồng nhau, cần mở rộng grammar.

### 8.2. Grammar biểu thức

Để xử lý độ ưu tiên toán tử, có thể chia biểu thức thành các tầng:

~~~text
Expression <- OrExpr
OrExpr <- AndExpr (HSpace "or" !IdentifierContinue HSpace AndExpr)*
AndExpr <- CompareExpr (HSpace "and" !IdentifierContinue HSpace CompareExpr)*
CompareExpr <- AddExpr (HSpace CompareOp HSpace AddExpr)?
AddExpr <- MulExpr (HSpace AddOp HSpace MulExpr)*
MulExpr <- UnaryExpr (HSpace MulOp HSpace UnaryExpr)*
UnaryExpr <- ("not" !IdentifierContinue HSpace UnaryExpr)
           / ("-" UnaryExpr)
           / Primary
Primary <- Number / String / Identifier
         / "(" HSpace Expression HSpace ")"

CompareOp <- ">=" / "<=" / "==" / "!=" / ">" / "<"
AddOp <- "+" / "-"
MulOp <- "*" / "/"
Number <- [0-9]+ ("." [0-9]+)?
Identifier <- !ReservedWord [A-Za-z_] [A-Za-z0-9_]*
~~~

Các tầng từ OrExpr xuống Primary thể hiện thứ tự ưu tiên: phép nhân trước phép cộng, phép cộng trước so sánh, so sánh trước and, và and trước or. Trong từng tầng lặp, parser có thể tạo cây kết hợp trái khi xây AST.

Grammar trên cần bổ sung định nghĩa String, HSpace, ReservedWord, dấu phân cách và các rule còn lại trước khi dùng trong parser thực tế. Phần này tập trung minh họa cách PEG tổ chức độ ưu tiên.

### 8.3. Xử lý từ khóa và định danh

Từ khóa and, or và not cần ranh giới để không bị tách khỏi định danh dài hơn. Negative lookahead sau từ khóa ngăn android bị hiểu là and cộng với phần dư.

Tương tự, nếu DSL có từ khóa source, grammar cần bảo đảm sourceFile vẫn có thể là một định danh hợp lệ ở vị trí cho phép định danh.

## 9. Độ ưu tiên và tính kết hợp của biểu thức

PEG không tự quyết định độ ưu tiên toán tử cho DSL. Grammar cần biểu diễn điều đó thông qua các rule có tầng hoặc cấu trúc tương đương.

### 9.1. Tầng grammar theo độ ưu tiên

Với biểu thức:

~~~text
a + b * c
~~~

Nếu phép nhân có độ ưu tiên cao hơn phép cộng, cây cần tương đương:

~~~text
Add
├── Name(a)
└── Multiply
    ├── Name(b)
    └── Name(c)
~~~

Grammar dạng AddExpr <- MulExpr (AddOp MulExpr)* và MulExpr <- Primary (MulOp Primary)* giúp parser nhận cấu trúc đó.

### 9.2. Tính kết hợp trái

Phép trừ thường kết hợp trái:

~~~text
10 - 3 - 2
~~~

Được hiểu là:

~~~text
(10 - 3) - 2
~~~

Với grammar:

~~~text
AddExpr <- MulExpr (HSpace AddOp HSpace MulExpr)*
~~~

parser có thể thu thập chuỗi toán hạng và toán tử, sau đó gấp trái (left fold) để tạo cây. Nếu chỉ lồng đệ quy theo cách khác, có thể vô tình tạo kết hợp phải và thay đổi kết quả.

### 9.3. Tính kết hợp phải

Một số phép toán hoặc toán tử gán có thể kết hợp phải:

~~~text
a = b = c
~~~

Nếu DSL quy định gán kết hợp phải, cây có dạng Assign(a, Assign(b, c)). Grammar có thể dùng đệ quy phải ở vị trí thích hợp:

~~~text
Assignment <- LogicalExpr ("=" Assignment)?
~~~

Không phải mọi toán tử đều kết hợp giống nhau. Đặc tả DSL cần nói rõ độ ưu tiên và tính kết hợp, đặc biệt khi người dùng có thể viết nhiều toán tử trong một biểu thức.

### 9.4. Không dùng thứ tự PEG để thay thế toàn bộ precedence

Ordered choice giải quyết việc chọn giữa các phương án. Nó không tự thay thế mô hình tầng độ ưu tiên. Dùng một rule khổng lồ với nhiều lựa chọn có thể làm biểu thức khó hiểu và khó mở rộng. Tách theo tầng giúp grammar dễ đọc và dễ xây AST hơn.

## 10. Đệ quy trái và cách xử lý

Đệ quy trái xuất hiện khi một rule gọi lại chính nó ở vị trí đầu tiên:

~~~text
Expression <- Expression "+" Term / Term
~~~

Nhiều PEG parser cơ bản không xử lý trực tiếp dạng này. Parser recursive descent có thể gọi lặp vô hạn vì mỗi lần phân tích Expression lại quay về Expression tại cùng vị trí đầu vào.

### 10.1. Biến đổi thành lặp

Có thể viết lại:

~~~text
Expression <- Term (HSpace "+" HSpace Term)*
~~~

Grammar mới nhận một Term rồi lặp các cặp toán tử và Term tiếp theo. Khi tạo AST, dùng left fold để giữ tính kết hợp trái:

~~~text
terms = [a, b, c]
operators = [+, +]

tree = Add(Add(a, b), c)
~~~

### 10.2. Đệ quy phải

Với cấu trúc có tính kết hợp phải, đệ quy ở phía phải có thể phù hợp:

~~~text
Assignment <- LogicalExpr ("=" Assignment)?
~~~

Điều này khác với đệ quy trái vì parser tiêu thụ phần đầu vào trước khi đi vào lần gọi đệ quy tiếp theo.

### 10.3. Extension hỗ trợ left recursion

Một số PEG parser hiện đại hỗ trợ đệ quy trái trực tiếp hoặc gián tiếp bằng thuật toán mở rộng. Cách hỗ trợ và giới hạn phụ thuộc implementation. Không nên giả định mọi công cụ PEG đều chấp nhận left recursion; hãy kiểm tra tài liệu của parser được chọn và thử grammar trên đúng phiên bản triển khai.

## 11. Packrat parsing

PEG có thể được triển khai bằng backtracking. Nếu parser thử lại cùng một rule tại cùng một vị trí nhiều lần, một số grammar có thể gây công việc lặp đáng kể.

**Packrat parsing** dùng memoization để lưu kết quả phân tích của một rule tại một vị trí đầu vào. Khi cùng rule được yêu cầu ở cùng vị trí lần nữa, parser có thể dùng kết quả đã lưu thay vì phân tích lại.

### 11.1. Bảng memoization

Có thể hình dung bảng cache:

~~~text
Memo[(Rule, InputPosition)] = ParseResult
~~~

Ví dụ, nếu rule Expression được phân tích tại vị trí 120, kết quả thành công hoặc thất bại sẽ được lưu cho cặp (Expression, 120). Một lần gọi tiếp theo tại đúng vị trí đó có thể tái sử dụng kết quả.

### 11.2. Độ phức tạp

Với grammar cố định và cách memoization phù hợp, packrat parsing thường đạt thời gian tuyến tính theo độ dài đầu vào. Đổi lại, parser lưu kết quả cho nhiều cặp rule/vị trí nên có thể tiêu thụ bộ nhớ tỷ lệ với số rule nhân độ dài đầu vào.

Đây là bảo đảm gắn với mô hình packrat và các giả định của implementation; không nên suy ra rằng mọi parser PEG đều tự động chạy tuyến tính hoặc có mức dùng bộ nhớ như nhau.

### 11.3. Ưu điểm

- Tránh phân tích lặp lại cùng rule tại cùng vị trí.
- Làm hiệu năng dễ dự đoán hơn với nhiều grammar có backtracking.
- Hỗ trợ cách viết grammar PEG tự nhiên mà không cần tự tối ưu mọi nhánh.

### 11.4. Chi phí và giới hạn

- Bảng memo có thể lớn với tệp đầu vào dài.
- Lưu AST hoặc giá trị lớn trong từng kết quả có thể tăng mức dùng bộ nhớ.
- Semantic action có tác dụng phụ không phù hợp với việc tái sử dụng kết quả memo.
- Left recursion cần extension hoặc thuật toán bổ sung; memoization cơ bản không tự giải quyết mọi trường hợp.
- Parser gia tăng cho IDE cần chính sách cache và invalidation riêng khi văn bản thay đổi.

### 11.5. Packrat không phải yêu cầu bắt buộc của PEG

PEG là hình thức đặc tả grammar. Packrat là một chiến lược triển khai parser PEG. Có parser dùng backtracking mà không memoize, parser dùng memoization chọn lọc và parser generator tạo mã theo cách khác. Khi chọn công cụ, cần xem xét cả ngữ nghĩa PEG lẫn đặc điểm hiệu năng của implementation.

## 12. Tạo AST từ PEG

Parser không chỉ xác nhận đầu vào hợp lệ; DSL thường cần tạo AST để các bước sau xử lý. Có thể gắn hành động tạo nút với rule hoặc dùng một AST builder riêng.

### 12.1. AST cho biểu thức

Với grammar:

~~~text
AddExpr <- MulExpr (HSpace AddOp HSpace MulExpr)*
~~~

AST builder có thể:

1. Nhận nút MulExpr đầu tiên.
2. Đọc từng cặp AddOp và MulExpr tiếp theo.
3. Tạo một BinaryExpression mới từ cây hiện tại và toán hạng tiếp theo.
4. Lặp đến hết chuỗi.

Ví dụ:

~~~text
amount + fee + tax
~~~

Tạo cây:

~~~text
Add
└── Add
    ├── Name(amount)
    └── Name(fee)
└── Name(tax)
~~~

Biểu diễn cây trên được hiểu là Add(Add(amount, fee), tax), tức kết hợp trái.

### 12.2. AST cho khai báo DSL

Với khai báo:

~~~text
pipeline "daily" {
    source "orders.csv"
    output "daily.csv"
}
~~~

AST có thể là:

~~~text
PipelineDeclaration
├── Name("daily")
├── SourceStatement
│   └── Path("orders.csv")
└── OutputStatement
    └── Path("daily.csv")
~~~

Nút AST nên lưu dữ liệu cần thiết cho semantic analysis và runtime, chẳng hạn tên, biểu thức, tham số, vị trí nguồn và danh sách câu lệnh. Không nhất thiết giữ mọi dấu phân cách nếu chúng không cần cho các bước sau.

### 12.3. Semantic action và tác dụng phụ

Một số PEG tool cho phép gắn semantic action trực tiếp vào rule. Cần thận trọng khi action có tác dụng phụ, bởi parser có thể thử một nhánh rồi thất bại, hoặc memoize kết quả.

Nên ưu tiên action thuần: tạo một giá trị hoặc nút từ phần đã khớp, không ghi file, thay đổi trạng thái toàn cục hoặc gọi dịch vụ. Các tác dụng phụ nên được thực hiện sau khi parse thành công và qua giai đoạn thực thi riêng.

### 12.4. Giữ source location

Khi tạo AST, nên lưu source span của nút hoặc token liên quan. Vị trí nguồn hỗ trợ:

- Báo lỗi ngữ nghĩa tại đúng tên hoặc biểu thức.
- Hiển thị kết quả phân tích trong IDE.
- Ánh xạ lỗi từ runtime về dòng DSL.
- Refactoring và định dạng lại mã.

Nếu chỉ lưu giá trị đã parse mà bỏ vị trí nguồn, các giai đoạn sau khó chỉ ra đoạn văn bản gây ra lỗi.

## 13. Báo lỗi trong PEG parser

Một parser cần cho biết vì sao đầu vào không hợp lệ, không chỉ trả về false. Backtracking khiến việc chọn thông báo lỗi cần được thiết kế cẩn thận.

### 13.1. Vị trí thất bại xa nhất

Một chiến lược phổ biến là lưu vị trí đầu vào xa nhất mà parser gặp lỗi và tập token/rule được mong đợi tại vị trí đó. Nếu nhiều nhánh thất bại, parser có thể dùng vị trí xa nhất để tạo chẩn đoán.

Ví dụ:

~~~text
pipeline "daily" {
    source
}
~~~

Sau từ khóa source, grammar mong đợi một chuỗi đường dẫn. Parser có thể báo:

~~~text
daily.dsl:2:11: expected a quoted source path
~~~

Thông báo như vậy hữu ích hơn parse failed vì chỉ ra loại thành phần còn thiếu.

### 13.2. Nhãn lỗi theo rule

Có thể đặt tên cho điều parser mong đợi:

~~~text
Source <- "source" HSpace1 String
~~~

Nếu String thất bại, implementation có thể hiển thị nhãn như source path. Một số parser generator hỗ trợ error label hoặc expectation name; cách khai báo cụ thể tùy công cụ.

### 13.3. Backtracking và thông báo lỗi gây nhiễu

Một nhánh có thể thất bại ở vị trí xa hơn nhưng chỉ là phương án không được chọn. Nếu parser báo tất cả kỳ vọng từ mọi nhánh, người dùng có thể nhận danh sách lỗi khó hiểu.

Công cụ nên phân biệt lỗi thử nhánh với lỗi cuối cùng của grammar. Có thể dùng rule label, điểm commit/cut nếu implementation hỗ trợ, hoặc thiết kế grammar để các nhánh phân biệt sớm hơn.

### 13.4. Phục hồi cú pháp

Đối với editor hoặc công cụ tương tác, parser có thể cố gắng tiếp tục sau một lỗi để vẫn tạo cây một phần. Ví dụ, nếu thiếu biểu thức sau filter, parser có thể tạo ErrorExpression rồi tiếp tục ở dòng output kế tiếp.

Phục hồi cần tránh tạo quá nhiều lỗi dây chuyền. Nên chọn điểm đồng bộ như newline, dấu chấm phẩy hoặc dấu đóng block tùy cấu trúc DSL. Nút lỗi cần được đánh dấu rõ để semantic analysis và runtime không coi nó là biểu thức hợp lệ.

## 14. PEG scannerless và lexer riêng

PEG có thể mô tả cả cú pháp từ vựng lẫn cú pháp cấu trúc. Một parser scannerless xử lý trực tiếp ký tự nguồn mà không cần lexer độc lập tạo token trước.

### 14.1. Scannerless parsing

Grammar có thể định nghĩa:

~~~text
Identifier <- [A-Za-z_] [A-Za-z0-9_]*
Number <- [0-9]+
String <- '"' (!'"' .)* '"'
Expression <- ...
~~~

Các rule từ vựng và cú pháp cùng nằm trong một grammar. Điều này thuận tiện khi cần lookahead giữa token và cấu trúc, nhưng grammar có thể chứa nhiều quy tắc khoảng trắng, ranh giới và escape.

### 14.2. Kết hợp lexer và PEG parser

Một kiến trúc khác dùng lexer tạo token trước, sau đó PEG parser xử lý chuỗi token:

~~~text
Source text -> Lexer -> Token stream -> PEG parser -> AST
~~~

Cách này hữu ích nếu DSL có hệ thống token phức tạp, cần tái sử dụng lexer hoặc cần tách rõ lỗi từ vựng và lỗi cú pháp. Parser PEG lúc đó hoạt động trên loại token thay vì ký tự thô.

### 14.3. Chọn cách nào?

| Điều kiện | Scannerless PEG | Lexer + PEG |
|---|---|---|
| Grammar nhỏ, token đơn giản | Thường gọn | Có thể thêm tầng không cần thiết |
| Cần lookahead trên ký tự | Trực tiếp | Cần lexer giữ thông tin phù hợp |
| Nhiều định dạng literal phức tạp | Có thể làm grammar dài | Lexer có thể tách riêng trách nhiệm |
| Muốn tái sử dụng token trong nhiều parser | Ít thuận tiện hơn | Thuận tiện hơn |
| Cần thông báo lỗi từ vựng riêng | Có thể gộp vào parser | Có ranh giới lexer rõ |

Không có lựa chọn đúng cho mọi dự án. Hãy dựa vào kích thước grammar, loại dữ liệu đầu vào, công cụ có sẵn và yêu cầu chẩn đoán.

## 15. Triển khai parser PEG

Có ba hướng phổ biến: viết parser thủ công theo quy tắc PEG, dùng parser combinator hoặc dùng parser generator.

### 15.1. Parser viết thủ công

Nhóm có thể viết các hàm tương ứng với rule:

~~~text
parsePipeline()
parseStatement()
parseExpression()
parsePrimary()
~~~

Mỗi hàm nhận vị trí đầu vào, thử các biểu thức theo thứ tự và trả kết quả. Cách này cho phép kiểm soát chặt thông báo lỗi và AST, nhưng nhóm phải tự duy trì backtracking, memoization nếu cần và quy tắc grammar.

### 15.2. Parser combinator

Parser combinator là các hàm hoặc đối tượng nhỏ đại diện cho parser và có thể kết hợp thành parser lớn:

~~~text
literal("if")
sequence(keyword, spacing, expression)
choice(ifStatement, whileStatement, assignment)
many(statement)
optional(elseClause)
lookAhead(identifierBoundary)
~~~

Tên hàm trên là minh họa, không phải API của một thư viện cụ thể. Combinator giúp grammar gần với cách đặc tả, dễ tái sử dụng các rule và có thể viết trực tiếp trong ngôn ngữ chủ.

### 15.3. Parser generator

Parser generator nhận grammar PEG và tạo mã parser hoặc cấu trúc chạy tương ứng. Quy trình thường gồm:

1. Viết grammar trong định dạng công cụ hỗ trợ.
2. Chạy bước sinh parser nếu công cụ yêu cầu.
3. Tích hợp mã sinh ra vào dự án.
4. Viết AST builder hoặc semantic action.
5. Gọi parser từ ứng dụng và xử lý diagnostics.

Ưu điểm là grammar có thể được quản lý tách khỏi logic runtime. Hạn chế là nhóm cần học cú pháp riêng của công cụ, quản lý phiên bản generator và hiểu giới hạn của implementation.

### 15.4. Tích hợp vào ứng dụng DSL

Ứng dụng thường không gọi parser trực tiếp từ mọi nơi. Có thể tạo một facade:

~~~java
public final class DslCompiler {
    public CompilationResult compile(String source) {
        ParseResult parseResult = parser.parse(source);
        if (!parseResult.success()) {
            return CompilationResult.failure(parseResult.diagnostics());
        }

        Ast ast = astBuilder.build(parseResult);
        return semanticAnalyzer.analyze(ast);
    }
}
~~~

Các kiểu trong ví dụ là giả định. Ý tưởng là tách parsing, AST construction và semantic analysis, đồng thời trả diagnostics có cấu trúc cho caller.

## 16. Thiết kế grammar PEG có thể bảo trì

Grammar là một phần quan trọng của API DSL. Khi ngôn ngữ được dùng trong nhiều tệp hoặc quy trình, thay đổi thứ tự rule có thể làm thay đổi cách phân tích một số đầu vào.

### 16.1. Đặt tên rule theo khái niệm

Tên như PipelineDeclaration, FilterStatement, Identifier và StringLiteral giúp grammar dễ đọc hơn các tên viết tắt không có ý nghĩa.

### 16.2. Tách tầng cú pháp

Nên tách:

- Rule cấp chương trình và khai báo.
- Rule câu lệnh và block.
- Rule biểu thức theo độ ưu tiên.
- Rule literal, định danh và comment.
- Rule khoảng trắng và dấu phân cách.

Việc tách tầng giúp thay đổi một phần grammar mà ít ảnh hưởng phần khác.

### 16.3. Giữ thứ tự choice có chủ đích

Đối với mỗi ordered choice, cần hiểu:

- Phương án nào có tiền tố chung?
- Phương án nào cụ thể hơn?
- Nhánh nào có thể khớp tiền tố của nhánh khác?
- Có cần lookahead hoặc boundary không?
- Nếu nhánh đầu thành công nhưng phần còn lại thất bại, kết quả mong muốn là gì?

Thứ tự lựa chọn nên được xem là một quyết định thiết kế có thể ảnh hưởng tương thích, không phải chi tiết trình bày.

### 16.4. Tránh rule lặp rỗng

Một biểu thức được dùng với * hoặc + phải tiêu thụ đầu vào mỗi khi thành công. Nếu rule có thể thành công mà không tiêu thụ ký tự, phép lặp có thể không tiến triển và parser có thể lặp vô hạn hoặc báo lỗi grammar.

Ví dụ không an toàn:

~~~text
Empty <- [ \t]*
Bad <- Empty*
~~~

Empty có thể thành công với chuỗi rỗng. Dùng nó trong một phép lặp khác không tạo tiến triển. Hãy bảo đảm mỗi lần lặp tiêu thụ ít nhất một ký tự hoặc token.

### 16.5. Tránh grammar phụ thuộc tác dụng phụ

Nếu semantic action thay đổi trạng thái bên ngoài trong khi parser thử nhánh, backtracking có thể khiến tác dụng phụ xảy ra cho nhánh cuối cùng bị loại. Hãy giữ action thuần hoặc trì hoãn side effect đến sau khi parse thành công.

### 16.6. Tách cú pháp khỏi quy tắc miền

Grammar nên trả lời đầu vào có hình dạng hợp lệ không. Semantic analyzer nên kiểm tra tên có tồn tại, kiểu có tương thích và quy tắc miền có được thỏa mãn hay không.

Ví dụ sum(status) có thể đúng grammar vì nó là lời gọi hàm với một biểu thức. Việc status là chuỗi và không thể tổng hợp là lỗi ngữ nghĩa, không nhất thiết là lỗi cú pháp.

## 17. Kiểm thử PEG parser

Kiểm thử grammar cần bao gồm đầu vào hợp lệ, không hợp lệ, ranh giới và các trường hợp dễ bị ảnh hưởng bởi ordered choice.

### 17.1. Kiểm thử rule riêng lẻ

Mỗi rule quan trọng nên có ví dụ:

| Rule | Đầu vào hợp lệ | Đầu vào không hợp lệ |
|---|---|---|
| Identifier | customer_id, _total | 9value, chuỗi rỗng |
| Number | 0, 125, 3.14 | .5 nếu grammar không hỗ trợ |
| String | "orders.csv" | Chuỗi thiếu dấu đóng |
| CompareOp | >=, ==, < | => |
| Pipeline | Khai báo đầy đủ | Thiếu block đóng |

### 17.2. Kiểm thử ordered choice

Với các nhánh có tiền tố chung, kiểm thử cả trường hợp ngắn và dài. Ví dụ nếu toán tử hỗ trợ > và >=, cần xác nhận cả hai được nhận đúng, không để >= bị tách thành > và =.

### 17.3. Kiểm thử EOF

Đảm bảo parser từ chối ký tự dư:

~~~text
pipeline "daily" { }
unexpected
~~~

Nếu grammar chỉ parse một tiền tố mà không yêu cầu EOF, đoạn đầu có thể thành công và phần unexpected bị bỏ qua. Rule Start nên xác nhận toàn bộ đầu vào đã được tiêu thụ.

### 17.4. Kiểm thử whitespace và comment

Thử:

- Khoảng trắng ở đầu và cuối.
- Dòng trống.
- Comment sau câu lệnh.
- Comment có ký tự giống dấu ngoặc hoặc dấu phân cách.
- CRLF và LF nếu hỗ trợ nhiều hệ điều hành.
- Tab và dấu cách trong block.

### 17.5. Kiểm thử hiệu năng

Với đầu vào lớn hoặc lồng sâu, đo:

- Thời gian parse.
- Mức dùng bộ nhớ.
- Số lần rule được gọi nếu implementation cung cấp thống kê.
- Hành vi với đầu vào gần đúng nhưng cuối cùng không hợp lệ.
- Độ sâu đệ quy và khả năng xử lý chuỗi dài.

Các đầu vào không hợp lệ dài có thể kích hoạt nhiều nhánh thất bại. Cần đo trường hợp này, không chỉ benchmark các chương trình hợp lệ.

### 17.6. Grammar regression tests

Khi sửa grammar, duy trì bộ tệp DSL mẫu và kết quả AST mong đợi. Một thay đổi thứ tự choice có thể khiến cùng đầu vào được phân tích theo cách khác mà không làm parser báo lỗi. So sánh AST giúp phát hiện thay đổi ngữ nghĩa ngoài ý muốn.

## 18. Hiệu năng và giới hạn tài nguyên

PEG có thể dễ đọc và xác định, nhưng hiệu năng vẫn phụ thuộc grammar và implementation.

### 18.1. Backtracking

Nhiều nhánh cùng thử một tiền tố dài có thể làm parser thực hiện công việc lặp. Memoization hoặc grammar factoring có thể giảm chi phí.

### 18.2. Packrat memory

Packrat thường lưu kết quả cho nhiều cặp rule/vị trí. Với đầu vào rất lớn, bộ nhớ có thể trở thành giới hạn chính. Có thể xem xét memoization chọn lọc nếu công cụ hỗ trợ và nếu phép đo cho thấy một số rule gây lặp đáng kể.

### 18.3. Độ sâu đệ quy

Grammar biểu thức lồng nhau hoặc block lồng sâu có thể tạo call stack sâu. Engine nên đặt giới hạn hợp lý hoặc dùng kỹ thuật triển khai tránh tràn stack khi đầu vào không tin cậy.

### 18.4. Giới hạn kích thước đầu vào

Nếu DSL được nhận từ người dùng hoặc dịch vụ bên ngoài, cần giới hạn:

- Kích thước văn bản.
- Số lượng token hoặc nút AST.
- Độ sâu lồng nhau.
- Độ dài chuỗi và literal.
- Thời gian parse.
- Bộ nhớ dành cho memoization và AST.

PEG không tự cung cấp chính sách giới hạn tài nguyên. Đó là trách nhiệm của parser implementation và ứng dụng tích hợp.

## 19. PEG trong DSL: ưu điểm và hạn chế

### 19.1. Ưu điểm

- **Ordered choice rõ ràng:** grammar có thể xác định trực tiếp thứ tự ưu tiên giữa các phương án.
- **Lookahead tích hợp:** predicate dương và âm giúp xử lý ranh giới token và ngữ cảnh.
- **Có thể mô tả scannerless:** lexer và parser có thể được mô tả trong cùng một grammar.
- **Grammar gần với cấu trúc DSL:** rule có thể đặt tên theo khai báo, câu lệnh và biểu thức của miền.
- **Không có ambiguity theo kiểu nhiều parse tree:** lựa chọn có thứ tự xác định một cách phân tích theo ngữ nghĩa PEG.
- **Có thể dùng packrat:** memoization giúp kiểm soát việc phân tích lặp lại trong nhiều implementation.

### 19.2. Hạn chế

- Thứ tự choice có thể gây lỗi khó nhận ra nếu nhánh tổng quát đứng trước nhánh cụ thể.
- Grammar cần được thiết kế cẩn thận để tránh prefix capture.
- Left recursion không được hỗ trợ bởi mọi PEG parser.
- Packrat có thể dùng nhiều bộ nhớ.
- Error reporting có thể cần thiết kế thêm do backtracking.
- Một grammar lớn với nhiều predicate có thể khó hiểu nếu không được chia rule hợp lý.
- Semantic action có tác dụng phụ có thể không an toàn khi parser thử nhánh hoặc memoize.

### 19.3. Khi nào PEG phù hợp?

PEG là lựa chọn đáng cân nhắc khi:

1. DSL có grammar riêng, kích thước vừa phải hoặc có thể chia thành các nhóm rule rõ ràng.
2. Cần lookahead để phân biệt từ khóa, định danh hoặc cấu trúc có tiền tố chung.
3. Muốn kiểm soát thứ tự ưu tiên giữa các lựa chọn.
4. Nhóm có thể kiểm thử ordered choice và hiểu giới hạn của parser implementation.
5. Cần một parser có thể tích hợp vào ứng dụng và tạo AST cho các bước sau.

Có thể cân nhắc parser LL/LR hoặc một parser generator khác nếu grammar phụ thuộc nhiều vào left recursion, cần hệ sinh thái công cụ cụ thể hoặc có yêu cầu hiệu năng và chẩn đoán phù hợp hơn với lựa chọn đó.

## 20. Quy trình phát triển một PEG parser cho DSL

Một quy trình thực hiện có thể gồm:

1. **Thu thập ví dụ DSL.** Lấy ví dụ hợp lệ, không hợp lệ, trường hợp biên và cấu trúc lồng nhau.
2. **Xác định token và ký hiệu.** Quy định từ khóa, định danh, literal, comment, khoảng trắng và dấu phân cách.
3. **Đặc tả grammar cấp cao.** Mô tả chương trình, module, khai báo, câu lệnh và block.
4. **Thiết kế grammar biểu thức.** Tách theo độ ưu tiên và tính kết hợp của toán tử.
5. **Sắp xếp ordered choice.** Đặt nhánh cụ thể trước nhánh tổng quát và xử lý tiền tố chung.
6. **Thêm lookahead có mục đích.** Dùng predicate để kiểm tra ranh giới, từ khóa và EOF.
7. **Xử lý left recursion.** Biến đổi thành lặp hoặc dùng extension đã được công cụ hỗ trợ.
8. **Chọn implementation.** Parser thủ công, parser combinator hoặc parser generator; cân nhắc packrat.
9. **Xây AST và giữ source span.** Tách cú pháp khỏi kiểm tra ngữ nghĩa và runtime.
10. **Thiết kế diagnostics.** Gắn nhãn lỗi, vị trí nguồn và thông tin kỳ vọng.
11. **Kiểm thử grammar.** Bao phủ ordered choice, whitespace, comment, EOF, lỗi và hiệu năng.
12. **Quản lý phiên bản grammar.** Xác định thay đổi nào tương thích với các tệp DSL đã lưu.

Grammar nên được phát triển cùng ví dụ thực tế. Khi thêm một rule mới, hãy xem xét liệu nó có tiền tố trùng với rule cũ hay làm thay đổi thứ tự lựa chọn. Một thay đổi nhỏ trong grammar PEG có thể làm thay đổi cách parse mà không cần thay đổi cú pháp bề mặt.

## 21. Những sai lầm thường gặp

### 21.1. Coi / giống phép OR không thứ tự

Trong PEG, phương án đầu tiên thành công được ưu tiên. Đổi thứ tự nhánh có thể thay đổi cách phân tích. Hãy xem ordered choice là một phần của đặc tả.

### 21.2. Đặt nhánh ngắn trước nhánh dài

Nếu hai nhánh có tiền tố chung, nhánh ngắn có thể nhận một phần của đầu vào và ngăn nhánh dài được thử. Đặt nhánh cụ thể trước hoặc factor tiền tố chung.

### 21.3. Quên ranh giới từ khóa

Rule if không có boundary có thể khớp tiền tố của ifReady. Dùng lookahead để xác nhận ký tự tiếp theo không phải ký tự tiếp tục định danh.

### 21.4. Không kiểm tra EOF

Nếu Start không yêu cầu EOF, parser có thể chấp nhận tiền tố hợp lệ rồi bỏ qua nội dung dư. Luôn xác định rõ toàn bộ nguồn phải được tiêu thụ hay không.

### 21.5. Viết left recursion trong parser không hỗ trợ

Rule như Expression <- Expression "+" Term / Term có thể gây đệ quy vô hạn ở parser PEG cơ bản. Hãy chuyển thành lặp và xây AST theo tính kết hợp mong muốn, hoặc dùng extension đã được xác nhận.

### 21.6. Lặp một rule có thể khớp rỗng

Rule trong * hoặc + phải tiêu thụ đầu vào khi thành công. Nếu không, parser có thể không tiến triển.

### 21.7. Trộn semantic action có tác dụng phụ vào parser

Backtracking có thể làm action của nhánh không được chọn vẫn đã chạy. Hãy dùng action thuần để tạo dữ liệu hoặc thực hiện tác dụng phụ sau khi parse thành công.

### 21.8. Nghĩ packrat tự giải quyết mọi vấn đề

Memoization giúp giảm parse lặp nhưng không tự sửa grammar sai, thông báo lỗi kém, left recursion không được hỗ trợ hoặc mức dùng bộ nhớ quá cao.

### 21.9. Chỉ kiểm thử đầu vào hợp lệ

Grammar có thể hoạt động với ví dụ đơn giản nhưng thất bại ở prefix, comment, newline, chuỗi escape hoặc đầu vào gần đúng. Cần kiểm thử cả lỗi và trường hợp biên.

## 22. Câu hỏi tự kiểm tra

1. PEG là gì và ordered choice có vai trò gì?
2. Phân biệt cách lựa chọn trong PEG với các phương án thay thế trong CFG.
3. Giải thích sequence, ordered choice, *, +, ?, positive lookahead và negative lookahead.
4. Vì sao trong PEG cần đặt >= trước > khi định nghĩa toán tử so sánh?
5. Với grammar Start <- ("a" / "ab") "c", vì sao đầu vào abc thất bại?
6. Lookahead giúp phân biệt từ khóa if với định danh ifReady như thế nào?
7. Vì sao parser nên yêu cầu EOF ở rule Start?
8. Hãy viết grammar biểu thức có phép nhân ưu tiên cao hơn phép cộng.
9. Đệ quy trái gây vấn đề gì với PEG parser cơ bản? Có thể biến đổi grammar như thế nào?
10. Packrat parsing dùng memoization ra sao? Đổi lại có chi phí gì?
11. Phân biệt scannerless PEG với kiến trúc lexer kết hợp PEG parser.
12. Vì sao semantic action có tác dụng phụ không phù hợp khi parser có backtracking?
13. Hãy đề xuất grammar PEG cho một khai báo DSL gồm tên, danh sách thuộc tính và block câu lệnh.
14. Những trường hợp nào cần có trong bộ kiểm thử regression cho grammar PEG?

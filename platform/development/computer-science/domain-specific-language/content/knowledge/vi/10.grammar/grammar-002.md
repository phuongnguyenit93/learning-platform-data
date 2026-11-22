# Ký pháp EBNF

## EBNF là gì?

Khi thiết kế ngữ pháp cho một ngôn ngữ chuyên miền (domain-specific language, DSL), nhóm phát triển cần một cách mô tả chính xác những cấu trúc nào được xem là hợp lệ. Một danh sách ví dụ đơn lẻ không đủ để xác định mọi cách viết có thể chấp nhận. Cần có các quy tắc tổng quát để người viết, người xây dựng parser và người duy trì ngôn ngữ cùng hiểu một cú pháp.

**EBNF (Extended Backus–Naur Form)** là một ký pháp dùng để mô tả ngữ pháp hình thức. Nó mở rộng ý tưởng của BNF bằng các ký hiệu tiện dụng cho lựa chọn, nhóm, phần tùy chọn và phần lặp. Nhờ đó, đặc tả ngữ pháp thường ngắn gọn và dễ đọc hơn so với việc viết tất cả cấu trúc bằng các quy tắc đệ quy riêng.

EBNF là *ngôn ngữ để mô tả ngôn ngữ*. Nó không phải cú pháp của DSL mà người dùng cuối viết, cũng không phải một parser hay trình biên dịch. Ví dụ, một DSL có thể dùng từ khóa RULE, WHEN và THEN; EBNF mô tả cách các từ khóa đó kết hợp thành một khai báo rule hợp lệ.

Ví dụ một quy tắc EBNF:

    ruleDeclaration = "RULE", string, "WHEN", expression,
                      "THEN", action ;

Quy tắc trên nói rằng một khai báo rule gồm lần lượt từ khóa RULE, một giá trị chuỗi, từ khóa WHEN, một biểu thức, từ khóa THEN và một hành động. Dấu phẩy biểu thị sự nối tiếp trong quy ước EBNF được dùng ở tài liệu này; dấu chấm phẩy kết thúc một production.

EBNF thường được dùng để:

- Đặc tả cú pháp của ngôn ngữ lập trình, DSL, ngôn ngữ cấu hình và định dạng dữ liệu.
- Làm tài liệu tham chiếu cho người viết chương trình DSL.
- Làm đầu vào cho parser generator hoặc làm cơ sở để viết parser thủ công.
- Phân tích cấu trúc hợp lệ, phát hiện chỗ mơ hồ và xem xét độ ưu tiên của toán tử.
- Duy trì sự nhất quán giữa đặc tả, frontend, formatter và công cụ IDE.

## Nguồn gốc và ý tưởng của BNF

Ký pháp Backus–Naur Form (BNF) được dùng để mô tả cấu trúc cú pháp của ngôn ngữ bằng các quy tắc sản xuất (production rules). Mỗi quy tắc định nghĩa một ký hiệu phi kết thúc có thể được thay bằng một chuỗi ký hiệu khác.

Ví dụ BNF đơn giản:

    <digit> ::= "0" | "1" | "2" | "3" | "4"
              | "5" | "6" | "7" | "8" | "9"

    <number> ::= <digit> | <digit> <number>

<digit> và <number> là các ký hiệu phi kết thúc (nonterminal). Chuỗi "0" đến "9" là ký hiệu kết thúc (terminal). Dấu ::= có nghĩa là “được định nghĩa là”, còn | biểu thị lựa chọn giữa các phương án.

Quy tắc <number> sử dụng đệ quy: một số có thể là một chữ số hoặc một chữ số theo sau bởi một số khác. Đây là cách biểu diễn lặp trong BNF. EBNF bổ sung ký hiệu lặp để có thể viết cấu trúc tương tự gọn hơn:

    digit  = "0" | "1" | "2" | "3" | "4"
           | "5" | "6" | "7" | "8" | "9" ;

    number = digit, { digit } ;

{ digit } có nghĩa là lặp digit không hoặc nhiều lần. Do đó number gồm một chữ số bắt buộc, theo sau là không hoặc nhiều chữ số.

Tên gọi “Extended” phản ánh việc bổ sung những cách viết thuận tiện cho các cấu trúc thường gặp. Có nhiều biến thể EBNF được sử dụng trong tài liệu và công cụ khác nhau; vì vậy, đặc tả của một DSL cần công bố rõ dialect hoặc quy ước ký hiệu mà nó sử dụng.

## Các thành phần cơ bản của một production

Một production EBNF thường có dạng:

    nonterminal = expression ;

Trong đó:

- **Nonterminal:** tên của cấu trúc đang được định nghĩa, ví dụ expression, ruleDeclaration hoặc identifier.
- **Dấu định nghĩa:** thường là = trong nhiều biến thể EBNF; một số tài liệu dùng ::= theo phong cách BNF.
- **Expression:** chuỗi ký hiệu mô tả các cách tạo ra nonterminal đó.
- **Dấu kết thúc:** thường là ; trong dialect được chọn.

Một expression có thể chứa terminal, nonterminal, chuỗi nối tiếp, lựa chọn, nhóm, phần tùy chọn và phần lặp.

### Terminal — ký hiệu kết thúc

Terminal là ký hiệu xuất hiện trực tiếp trong văn bản đầu vào và không được thay thế tiếp bằng production khác. Terminal thường là:

- Từ khóa: RULE, WHEN, THEN, AND.
- Toán tử: +, -, >=, ==.
- Dấu phân cách: (, ), ,, ..
- Literal được viết theo dạng cố định, chẳng hạn từ khóa Boolean TRUE.
- Một lớp token do lexer nhận diện, chẳng hạn identifier, number hoặc string.

Trong tài liệu, terminal dạng từ hoặc ký hiệu cố định thường được đặt trong dấu nháy kép:

    assignmentOperator = "=" | "+=" | "-=" ;

Một số đặc tả dùng dấu nháy đơn thay cho dấu nháy kép. Điều quan trọng là dùng nhất quán và nói rõ dấu nháy nào biểu diễn terminal.

### Nonterminal — ký hiệu phi kết thúc

Nonterminal là tên của một cấu trúc có thể được khai triển bằng một production khác. Nó giúp chia ngữ pháp thành những thành phần có ý nghĩa.

Ví dụ:

    assignment = identifier, "=", expression ;

assignment, identifier và expression là nonterminal nếu chúng được định nghĩa bằng các production riêng. Parser dùng các quy tắc đó để xác định một chuỗi token có phải là phép gán hay không.

Tên nonterminal nên mô tả vai trò cú pháp và dùng quy ước nhất quán, chẳng hạn ruleDeclaration, functionCall, argumentList và comparisonExpression. Tránh dùng tên quá chung như thing, part hoặc item nếu chúng không giúp người đọc hiểu cấu trúc.

### Nối tiếp (sequence)

Các thành phần được viết nối tiếp biểu thị chúng phải xuất hiện theo thứ tự đã mô tả. Trong dialect được dùng ở đây, dấu phẩy biểu diễn phép nối tiếp:

    assignment = identifier, "=", expression ;

Một phép gán cần có định danh, tiếp theo là dấu =, rồi đến biểu thức. Nếu đầu vào thiếu một trong các thành phần hoặc sai thứ tự, nó không khớp production này.

Một số dialect EBNF không yêu cầu dấu phẩy và viết nối tiếp trực tiếp. Ví dụ assignment = identifier "=" expression ; có thể xuất hiện trong tài liệu khác. Không nên trộn hai phong cách trong cùng một đặc tả.

### Lựa chọn (alternative)

Dấu | biểu thị lựa chọn giữa một hoặc nhiều phương án. Một nonterminal có thể được tạo từ bất kỳ nhánh nào:

    booleanLiteral = "TRUE" | "FALSE" ;

    statement = assignment | functionCall | ruleDeclaration ;

booleanLiteral có thể là TRUE hoặc FALSE. statement có thể là một phép gán, một lời gọi hàm hoặc một khai báo rule.

Các lựa chọn cần được xem xét để tránh chồng lấn gây mơ hồ. Nếu hai nhánh có thể nhận cùng một chuỗi token nhưng tạo ra cách hiểu khác nhau, parser có thể không biết chọn nhánh nào. Khi đó cần thiết kế lại grammar, thêm ngữ cảnh phân biệt hoặc quy định cơ chế ưu tiên phù hợp.

### Nhóm (grouping)

Dấu ngoặc tròn dùng để nhóm một biểu thức con, nhất là khi kết hợp lựa chọn với phép nối tiếp hoặc phép lặp:

    sign = [ "+" | "-" ] ;

    arithmeticOperator = ( "+" | "-" | "*" | "/" ) ;

Trong ví dụ đầu, dấu ngoặc nhóm hai phương án dấu + và - thành phần tùy chọn. Trong ví dụ thứ hai, nhóm xác định một toán tử số học được chọn từ bốn ký hiệu.

### Phần tùy chọn (optional)

Dấu ngoặc vuông [ ... ] biểu thị một phần có thể xuất hiện một lần hoặc không xuất hiện:

    elseClause = [ "ELSE", action ] ;

Một rule có thể có nhánh ELSE hoặc không. Khi phần tùy chọn có nhiều thành phần nối tiếp, cả nhóm được xem là tùy chọn:

    functionCall = identifier, "(", [ argumentList ], ")" ;

Lời gọi hàm có thể không có đối số, nhưng vẫn phải có cặp ngoặc. Vì vậy send() hợp lệ theo production này, còn send không có ngoặc thì không phải functionCall.

### Lặp không hoặc nhiều lần (repetition)

Dấu ngoặc nhọn { ... } biểu thị phần bên trong có thể lặp không hoặc nhiều lần:

    argumentList = expression, { ",", expression } ;

Danh sách đối số cần có ít nhất một expression, sau đó có thể có nhiều cặp dấu phẩy và biểu thức. Cấu trúc này chấp nhận một đối số, hai đối số hoặc nhiều hơn.

Nếu toàn bộ phần lặp có thể xuất hiện không lần nào, nó biểu diễn chuỗi rỗng. Ví dụ:

    parameterTail = { ",", identifier } ;

parameterTail có thể rỗng hoặc gồm một hay nhiều cặp dấu phẩy và định danh.

### Lặp một hoặc nhiều lần

Nhiều tài liệu gọi cấu trúc một hoặc nhiều lần là + hoặc viết nó bằng một phần tử bắt buộc theo sau bởi phần lặp. Vì ký pháp không thống nhất giữa các dialect, cách viết tường minh dễ hiểu là:

    identifier = letter, { letter | digit | "_" } ;

Quy tắc này yêu cầu ít nhất một chữ cái đầu tiên, sau đó cho phép không hoặc nhiều chữ cái, chữ số hoặc dấu gạch dưới. Do đó, định danh không thể rỗng.

### Chuỗi rỗng (epsilon)

Chuỗi rỗng là chuỗi không chứa terminal nào. Trong tài liệu hình thức, nó thường được ký hiệu ε (epsilon), nhưng nhiều dialect EBNF thể hiện chuỗi rỗng bằng production rỗng hoặc phần tùy chọn/lặp.

Ví dụ:

    optionalSemicolon = [ ";" ] ;

Production có thể sinh chuỗi rỗng nếu dấu ; không xuất hiện. Nếu dùng ε trực tiếp, cần ghi rõ quy ước vì không phải mọi parser generator đều chấp nhận cùng một cách viết.

## Bảng ký hiệu EBNF thường dùng

Bảng dưới đây tóm tắt quy ước được dùng trong tài liệu này. Các dialect khác có thể thay đổi một số dấu hoặc quy tắc kết thúc.

| Ký hiệu | Ý nghĩa | Ví dụ |
|---|---|---|
| = | Định nghĩa một nonterminal | digit = ... ; |
| ; | Kết thúc production | digit = "0" ; |
| , | Nối tiếp theo thứ tự | pair = identifier, ":", value ; |
| \| | Lựa chọn một trong các phương án | sign = "+" \| "-" ; |
| ( ... ) | Nhóm biểu thức | op = ("+" \| "-") ; |
| [ ... ] | Phần tùy chọn, không hoặc một lần | fraction = [ ".", digit ] ; |
| { ... } | Phần lặp, không hoặc nhiều lần | digits = digit, { digit } ; |
| "..." | Terminal dạng văn bản cố định | "WHEN" |
| tên không đặt trong nháy | Nonterminal hoặc tên lớp token theo quy ước | expression, identifier |
| (* ... *) | Comment trong tài liệu EBNF theo một số dialect | (* khai báo rule *) |

Trong bảng, dấu | được hiển thị bằng escape trong ô Markdown để tránh nhầm với cú pháp bảng; trong file grammar thực tế, ký hiệu lựa chọn là dấu gạch đứng thông thường.

Một số tài liệu EBNF còn dùng ? ... ? cho special sequence, - cho phép trừ tập ký hiệu hoặc dấu .. cho khoảng ký tự. Những phần mở rộng này không phổ biến đồng đều. Nếu đặc tả DSL cần dùng chúng, hãy định nghĩa rõ ý nghĩa thay vì giả định mọi công cụ đều hiểu giống nhau.

## Đọc và xây dựng production từ ví dụ

Giả sử DSL cần hỗ trợ khai báo hằng số:

    DEFINE MIN_TOTAL = 1000000

Ta có thể bắt đầu bằng production:

    constantDeclaration = "DEFINE", identifier, "=", number ;

Production này mô tả đúng cấu trúc cấp cao. Nhưng để grammar hoàn chỉnh, cần định nghĩa identifier và number:

    constantDeclaration = "DEFINE", identifier, "=", number ;

    identifier = letter, { letter | digit | "_" } ;

    number = digit, { digit } ;

    letter = "A" | "B" | "C" | "D" | "E" | "F" | "G"
           | "H" | "I" | "J" | "K" | "L" | "M" | "N"
           | "O" | "P" | "Q" | "R" | "S" | "T" | "U"
           | "V" | "W" | "X" | "Y" | "Z"
           | "a" | "b" | "c" | "d" | "e" | "f" | "g"
           | "h" | "i" | "j" | "k" | "l" | "m" | "n"
           | "o" | "p" | "q" | "r" | "s" | "t" | "u"
           | "v" | "w" | "x" | "y" | "z" ;

    digit = "0" | "1" | "2" | "3" | "4"
          | "5" | "6" | "7" | "8" | "9" ;

Grammar này chấp nhận định danh bắt đầu bằng chữ cái, theo sau là chữ cái, chữ số hoặc dấu gạch dưới; số chỉ gồm chữ số. Nó chưa hỗ trợ số âm, số thập phân, dấu phân nhóm, exponent hay literal có đơn vị. Nếu DSL cần các dạng đó, production phải được mở rộng có chủ đích.

Khi đọc một production, hãy lần theo từng nonterminal cho đến khi gặp terminal hoặc một cấu trúc lặp/tùy chọn đã hiểu. Quá trình thay nonterminal bằng một phương án của production được gọi là khai triển (derivation). Nếu có thể khai triển ký hiệu bắt đầu thành chuỗi token đầu vào, chuỗi đó thuộc ngôn ngữ được grammar mô tả.

## Ví dụ đầy đủ: EBNF cho một DSL quy tắc đơn giản

Phần này xây dựng một grammar nhỏ cho DSL quy tắc đơn hàng. Mục đích là minh họa cách dùng EBNF để mô tả chương trình gồm khai báo hằng số và rule, biểu thức logic, so sánh, lời gọi hàm và hành động.

### Cú pháp đầu vào mong muốn

Một tệp có thể chứa các khai báo như:

    DEFINE MIN_TOTAL = 1000000

    RULE "VIP discount"
    WHEN order.total >= MIN_TOTAL
      AND customer.segment IS "VIP"
    THEN discount.rate = 10
    ELSE discount.rate = 0

    RULE "Free shipping"
    WHEN customer.segment IS "VIP"
      AND order.total >= MIN_TOTAL
    THEN shipment.setFee(0)

Đây là ngôn ngữ giả định. Ví dụ sử dụng xuống dòng để phân tách khai báo và rule; grammar bên dưới mô tả các token sau khi lexer đã xử lý whitespace và comment. Nếu newline có ý nghĩa cú pháp, token NEWLINE cần xuất hiện trong grammar; để tập trung vào cấu trúc khai báo, ví dụ này giả định lexer/parser có cơ chế phân tách các khai báo ở cấp chương trình.

### Grammar cấp chương trình

    program = { declaration } ;

    declaration = constantDeclaration | ruleDeclaration ;

    constantDeclaration = "DEFINE", identifier, "=", literal ;

    ruleDeclaration = "RULE", string,
                      "WHEN", expression,
                      "THEN", action,
                      [ "ELSE", action ] ;

program là ký hiệu bắt đầu trong ví dụ. Nó gồm không hoặc nhiều khai báo. Mỗi khai báo là một hằng số hoặc một rule. Một rule có tên, điều kiện, hành động chính và một hành động ELSE tùy chọn.

Nếu DSL yêu cầu tệp phải có ít nhất một khai báo, có thể viết program = declaration, { declaration } ;. Nếu tệp rỗng được phép, dạng { declaration } phù hợp hơn.

### Grammar cho biểu thức

Biểu thức được chia thành các tầng để thể hiện độ ưu tiên của toán tử:

    expression = orExpression ;

    orExpression = andExpression, { "OR", andExpression } ;

    andExpression = comparison, { "AND", comparison } ;

    comparison = additiveExpression,
                 [ comparisonOperator, additiveExpression ] ;

    comparisonOperator = "==" | "!=" | ">" | ">="
                       | "<" | "<=" | "IS" ;

    additiveExpression = multiplicativeExpression,
                         { ( "+" | "-" ), multiplicativeExpression } ;

    multiplicativeExpression = primary,
                               { ( "*" | "/" ), primary } ;

    primary = literal
            | qualifiedName
            | functionCall
            | "(", expression, ")" ;

Các tầng này quy định * và / được nhóm trong multiplicativeExpression, + và - trong additiveExpression, phép so sánh ở tầng tiếp theo, rồi AND và OR. Với cấu trúc này, AND có độ ưu tiên cao hơn OR vì một orExpression chứa các andExpression.

Production comparison chỉ cho phép tối đa một toán tử so sánh. Vì vậy, chuỗi a < b < c không được grammar này chấp nhận như một phép so sánh liên tiếp. Nếu DSL muốn hỗ trợ phép so sánh dây chuyền, cần định nghĩa ngữ nghĩa và production riêng.

### Grammar cho tên, literal và lời gọi hàm

    qualifiedName = identifier, { ".", identifier } ;

    functionCall = qualifiedName, "(", [ argumentList ], ")" ;

    argumentList = expression, { ",", expression } ;

    literal = number | string | booleanLiteral ;

    booleanLiteral = "TRUE" | "FALSE" ;

    number = digit, { digit }, [ ".", digit, { digit } ] ;

    identifier = letter, { letter | digit | "_" } ;

qualifiedName cho phép tham chiếu thuộc tính nhiều cấp như order.customer.address. functionCall cho phép không có đối số hoặc có danh sách đối số. number ở đây hỗ trợ số nguyên và số thập phân không âm; nếu cần dấu âm, có thể đưa dấu vào production unary expression thay vì gắn vào literal.

Định nghĩa string, letter và digit phụ thuộc quy ước lexer. Có thể mô tả chi tiết chúng trong EBNF hoặc ghi rằng chúng là token được lexer nhận diện theo đặc tả từ vựng riêng. Với Unicode identifier, cần xác định rõ tập ký tự được chấp nhận và quy tắc chuẩn hóa.

### Grammar cho hành động

    action = assignment | functionCall ;

    assignment = qualifiedName, "=", expression ;

Hành động có thể là phép gán vào một thuộc tính hoặc lời gọi hàm. Grammar chỉ xác định hình dạng. Nó chưa xác nhận thuộc tính có được phép ghi hay hàm có tồn tại và được phép gọi hay không; các điều kiện đó thuộc phân tích ngữ nghĩa.

## Cách EBNF thể hiện độ ưu tiên toán tử

Một lỗi thường gặp khi viết grammar là đặt tất cả toán tử vào cùng một production:

    expression = primary, { ( "+" | "*" | "AND" | "OR" ), primary } ;

Production này cho phép một chuỗi toán tử nhưng không mô tả rõ độ ưu tiên. Parser có thể tạo cây theo thứ tự trái sang phải hoặc cần quy tắc bổ sung; người đọc grammar không thể suy ra chắc chắn a + b * c phải được nhóm như thế nào.

Một cách phổ biến là chia biểu thức thành các tầng:

    expression = additiveExpression ;

    additiveExpression = multiplicativeExpression,
                         { ( "+" | "-" ), multiplicativeExpression } ;

    multiplicativeExpression = primary,
                               { ( "*" | "/" ), primary } ;

    primary = number | identifier | "(", expression, ")" ;

Với grammar này, a + b * c được phân tích thành a + (b * c) vì multiplicativeExpression được nhận diện như một đơn vị ở bên phải phép cộng. Dấu ngoặc cho phép thay đổi cách nhóm:

    (a + b) * c

### Tính kết hợp trái và phải

Tính kết hợp (associativity) quy định cách nhóm các toán tử cùng mức ưu tiên khi không có dấu ngoặc. Ví dụ, phép trừ thường kết hợp trái:

    a - b - c

được hiểu là (a - b) - c, không phải a - (b - c). Production dạng lặp:

    additiveExpression = multiplicativeExpression,
                         { ( "+" | "-" ), multiplicativeExpression } ;

thường được triển khai bằng cách parser tích lũy từ trái sang phải. Nếu một toán tử cần kết hợp phải, chẳng hạn phép lũy thừa trong nhiều ngôn ngữ, grammar hoặc bước xây AST cần thể hiện rõ quy tắc đó.

Ví dụ một production đệ quy phải cho phép lũy thừa:

    powerExpression = primary, [ "^", powerExpression ] ;

Theo production này, a ^ b ^ c có cấu trúc a ^ (b ^ c). Cần đảm bảo parser được chọn có thể xử lý production theo cách đã viết hoặc chuyển đổi grammar phù hợp.

## Đệ quy trong EBNF

Đệ quy xuất hiện khi một nonterminal được định nghĩa thông qua chính nó, trực tiếp hoặc gián tiếp. Nó hữu ích để mô tả cấu trúc lồng nhau, danh sách và biểu thức.

Ví dụ biểu thức có ngoặc:

    expression = number | "(", expression, ")" ;

Một expression có thể là số hoặc một biểu thức khác được đặt trong ngoặc. Quy tắc này cho phép lồng ngoặc nhiều cấp.

Ví dụ danh sách đệ quy:

    argumentList = expression
                 | expression, ",", argumentList ;

EBNF có thể thay cách viết đệ quy này bằng repetition:

    argumentList = expression, { ",", expression } ;

### Đệ quy trái

Đệ quy trái (left recursion) xảy ra khi một nonterminal có thể khai triển thành một chuỗi bắt đầu bằng chính nó. Ví dụ:

    expression = expression, "+", term | term ;

Đệ quy trái thể hiện tự nhiên tính kết hợp trái và thường phù hợp với parser bottom-up như LR. Tuy nhiên, parser recursive descent đơn giản có thể gọi lặp vô hạn nếu xử lý trực tiếp production này.

Có thể biến đổi sang dạng không đệ quy trái:

    expression = term, { "+", term } ;

Parser recursive descent có thể đọc một term, sau đó lặp khi gặp +. Khi xây AST, parser tích lũy node theo trái để giữ tính kết hợp mong muốn.

Không nên loại bỏ đệ quy trái một cách máy móc mà không giữ ngữ nghĩa. Việc biến đổi grammar có thể thay đổi cách parser xây cây nếu không thiết kế bước kết hợp AST tương ứng.

## EBNF và parser

EBNF mô tả ngôn ngữ được chấp nhận, còn parser là chương trình nhận đầu vào và kiểm tra hoặc xây dựng cấu trúc theo grammar. Grammar có thể được dùng làm tài liệu, đầu vào cho công cụ sinh parser hoặc cơ sở để viết parser thủ công.

### Recursive descent parser

Với recursive descent, mỗi nonterminal thường được triển khai bằng một hàm. Hàm đọc token phù hợp với production và gọi các hàm khác để xử lý nonterminal con.

Ví dụ, production:

    assignment = qualifiedName, "=", expression ;

có thể tương ứng về ý tưởng với hàm:

    parseAssignment():
        target = parseQualifiedName()
        expect("=")
        value = parseExpression()
        return AssignmentNode(target, value)

Đây là pseudocode, không phải cú pháp EBNF. Cách triển khai cần xác định khi token không khớp: báo lỗi, thử nhánh khác hoặc phục hồi tại điểm đồng bộ.

### Parser generator

Parser generator nhận grammar và sinh một phần hoặc toàn bộ mã parser. Một số công cụ dùng grammar gần BNF/EBNF, một số có thêm chỉ thị precedence, action hoặc quy tắc lexer riêng. Không phải công cụ nào cũng hỗ trợ đúng cùng một dialect EBNF.

Khi chọn công cụ, cần kiểm tra:

- Cú pháp grammar mà công cụ chấp nhận.
- Họ parser được sinh ra, chẳng hạn LL, LR hoặc parser PEG.
- Cách xử lý đệ quy trái và xung đột lựa chọn.
- Cơ chế tạo AST và gắn source location.
- Khả năng phục hồi lỗi và diagnostics.
- Khả năng tích hợp với lexer, IDE và ngôn ngữ triển khai.
- Quy tắc tương thích khi grammar thay đổi.

### Grammar không phải là parser

Một file EBNF không tự đọc chương trình. Nó chỉ mô tả các chuỗi hợp lệ theo một tập quy tắc. Để xử lý DSL, vẫn cần lexer hoặc tokenizer, parser, bước xây AST và thường cần phân tích ngữ nghĩa.

Ngoài ra, một grammar có thể chấp nhận nhiều chuỗi hơn hoặc ít chuỗi hơn so với ý định nếu quy tắc được viết sai. Cần kiểm thử grammar bằng ví dụ hợp lệ, không hợp lệ và trường hợp biên.

## Phân biệt cú pháp với ngữ nghĩa

EBNF chủ yếu mô tả cấu trúc cú pháp. Nó có thể nói một câu lệnh gồm từ khóa, định danh và biểu thức theo thứ tự nào, nhưng không thường diễn đạt đầy đủ các ràng buộc phụ thuộc vào bảng symbol, kiểu dữ liệu hoặc trạng thái miền.

Ví dụ:

    SET order.total = "high"

Chuỗi này có thể đúng cú pháp nếu grammar cho phép một phép gán từ qualifiedName sang expression. Tuy nhiên, nó có thể sai kiểu nếu order.total là Money còn "high" là String.

Tương tự:

    CALL refund(order)

có thể đúng cú pháp nhưng sai ngữ nghĩa nếu refund không được khai báo, người gọi không có quyền hoặc đơn hàng chưa ở trạng thái cho phép hoàn tiền.

Các kiểm tra thường thuộc semantic analysis:

- Tên biến, thuộc tính, hàm và module có tồn tại không?
- Tên có nằm trong phạm vi (scope) hiện tại không?
- Các kiểu dữ liệu có tương thích không?
- Hàm có đúng số lượng và kiểu đối số không?
- Thuộc tính có được phép đọc hoặc ghi không?
- Hành động có hợp lệ với trạng thái đối tượng không?
- Các quy tắc có mâu thuẫn hoặc vi phạm chính sách miền không?

Không nên cố nhồi mọi ràng buộc ngữ nghĩa vào grammar. Việc đó thường làm grammar khó đọc, khó phân tích và vẫn không giải quyết được những điều kiện chỉ biết khi chạy.

## Giới hạn và tính mơ hồ của grammar

Một grammar cần xác định rõ cách phân tích mỗi chuỗi. Nếu một chuỗi có thể được phân tích theo nhiều cây cú pháp khác nhau và tạo ra ý nghĩa khác nhau, grammar được gọi là mơ hồ (ambiguous).

Ví dụ:

    expression = expression, "+", expression
               | expression, "*", expression
               | number ;

Grammar này không quy định rõ * có ưu tiên cao hơn + hay không, cũng không quy định cách kết hợp của hai toán tử. Chuỗi 1 + 2 * 3 có thể có nhiều cây phân tích.

Cách phổ biến là phân tầng theo precedence như phần trước. Một cách khác là dùng chỉ thị precedence của parser generator, nếu công cụ hỗ trợ. Dù chọn cách nào, đặc tả cần mô tả hành vi mà người dùng quan sát được.

### Dangling else

Một vấn đề kinh điển là ELSE thuộc về IF nào khi có câu lệnh IF lồng nhau:

    IF a THEN
        IF b THEN x
    ELSE y

Nếu grammar không quy định rõ, ELSE y có thể được hiểu là thuộc IF a hoặc IF b. Nhiều ngôn ngữ giải quyết bằng quy ước gắn ELSE với IF gần nhất chưa có ELSE, hoặc bằng dấu ngoặc/khối tường minh.

### Lựa chọn có tiền tố chung

Nếu hai nhánh bắt đầu bằng cùng một token, parser top-down có thể cần nhìn trước thêm token hoặc biến đổi grammar. Ví dụ:

    statement = identifier, "=", expression
              | identifier, "(", [ argumentList ], ")" ;

Hai nhánh đều bắt đầu bằng identifier. Parser có thể đọc định danh trước rồi xem token tiếp theo là = hay ( để quyết định nhánh. Với grammar phức tạp hơn, cần factoring hoặc parser hỗ trợ lookahead phù hợp.

## Viết EBNF dễ đọc và dễ bảo trì

Một đặc tả grammar tốt cần phục vụ cả người đọc và người triển khai. Nên chia grammar thành các phần có ý nghĩa, đặt tên rõ và tránh production quá dài.

### Tổ chức theo tầng

Có thể chia grammar thành các nhóm:

- Cấu trúc chương trình: program, declaration, module.
- Khai báo: ruleDeclaration, constantDeclaration, functionDeclaration.
- Câu lệnh: statement, assignment, conditionalStatement.
- Biểu thức: expression, comparison, primary.
- Từ vựng: identifier, number, string, comment.

Cách tổ chức này giúp người đọc lần theo từ cấu trúc tổng thể đến chi tiết. Nên đặt production tổng quát trước, sau đó định nghĩa các nonterminal được tham chiếu.

### Dùng tên nonterminal nhất quán

Tên nên thể hiện rõ vai trò, chẳng hạn parameterList, functionCall, comparisonOperator và ruleBody. Có thể dùng hậu tố List, Declaration, Expression hoặc Statement theo quy ước chung.

Không nên dùng cùng một tên cho các cấu trúc có ý nghĩa khác nhau. Nếu một grammar có cả identifier và qualifiedName, cần giải thích rõ identifier là một tên đơn còn qualified name là chuỗi tên phân tách bằng dấu chấm.

### Tránh lặp lại production

Nếu nhiều cấu trúc dùng cùng một danh sách tham số, hãy định nghĩa parameterList một lần rồi tham chiếu lại. Điều này giúp sửa quy tắc ở một nơi và giảm nguy cơ các production trở nên không nhất quán.

Tuy nhiên, không nên tạo quá nhiều nonterminal chỉ để thay thế một ký hiệu đơn giản. Mục tiêu là làm grammar rõ nghĩa, không phải chia nhỏ đến mức người đọc phải lần qua hàng chục production cho một biểu thức ngắn.

### Ghi rõ quy ước từ vựng

EBNF có thể mô tả identifier và number bằng từng ký tự, nhưng nhiều đặc tả tách lexical grammar khỏi syntactic grammar. Ví dụ, phần cú pháp dùng identifier như một token, còn phần từ vựng quy định tập ký tự và cách lexer nhận diện nó.

Nên ghi rõ:

- Tên nào là terminal cố định và tên nào là token class.
- Từ khóa có phân biệt chữ hoa/chữ thường không.
- Identifier có hỗ trợ Unicode không.
- String literal có escape sequence nào.
- Number có exponent, dấu âm hoặc hậu tố đơn vị không.
- Comment và whitespace được xử lý ở lexer hay grammar.

### Ghi chú các quy tắc không thể biểu đạt bằng grammar

Nếu một production chỉ là hình thức và còn cần kiểm tra ngữ nghĩa, hãy ghi chú. Ví dụ, grammar cho phép identifier xuất hiện ở vị trí gọi hàm, nhưng việc hàm có tồn tại và có thể gọi hay không được semantic analyzer xác nhận.

Ghi chú này giúp người triển khai không nhầm rằng parser chấp nhận một cấu trúc đồng nghĩa với chương trình hợp lệ về mọi mặt.

## Các biến thể EBNF và khả năng tương thích

Không có một cách viết EBNF duy nhất được mọi công cụ sử dụng. Các tài liệu có thể khác nhau ở:

- Dùng = hay ::= để định nghĩa production.
- Dùng dấu phẩy cho sequence hay chỉ nối các ký hiệu bằng khoảng trắng.
- Dùng dấu chấm phẩy hay dấu chấm để kết thúc production.
- Dùng { ... } cho repetition hay ký hiệu hậu tố *.
- Dùng [ ... ] cho optional hay ký hiệu hậu tố ?.
- Dùng dấu nháy đơn hay nháy kép cho terminal.
- Cách viết chuỗi rỗng, comment và khoảng ký tự.
- Cách đặt tên token do lexer cung cấp.

Ví dụ cùng một ý nghĩa có thể được viết trong hai phong cách:

    (* Phong cách có dấu phẩy *)
    argumentList = expression, { ",", expression } ;

    // Một phong cách kiểu PEG/EBNF rút gọn
    argumentList <- expression ("," expression)*

Ví dụ thứ hai gần với ký pháp PEG hơn, không nên tự động gọi là EBNF chuẩn. PEG (Parsing Expression Grammar) có quy tắc lựa chọn có thứ tự, khác với cách hiểu lựa chọn trong CFG/EBNF. Vì vậy, khi chuyển grammar giữa các công cụ, cần kiểm tra cả cú pháp lẫn ngữ nghĩa lựa chọn.

Nếu dùng parser generator, hãy viết grammar theo dialect mà công cụ thực sự hỗ trợ và ghi rõ trong dự án. Không nên viết một grammar dùng lẫn dấu ?, *, {} và quy tắc comment từ nhiều nguồn rồi giả định công cụ hiểu thống nhất.

## Quy trình xây dựng grammar bằng EBNF

Một quy trình thực tế có thể đi từ ví dụ đến quy tắc tổng quát:

1. **Thu thập chương trình mẫu:** ghi lại các câu lệnh và cấu hình mà người dùng cần viết, gồm cả trường hợp thông thường và trường hợp biên.
2. **Xác định token:** phân loại từ khóa, định danh, literal, toán tử, dấu phân cách và comment.
3. **Tìm cấu trúc lặp:** nhận diện khai báo, rule, biểu thức, danh sách và khối có thể tái sử dụng.
4. **Đặt nonterminal:** chia cấu trúc thành các thành phần có tên thể hiện ý nghĩa.
5. **Viết production:** dùng sequence, alternative, optional, repetition và grouping để mô tả các cách viết hợp lệ.
6. **Xác định độ ưu tiên và tính kết hợp:** phân tầng expression hoặc ghi rõ chỉ thị parser tương ứng.
7. **Kiểm tra mơ hồ và khả năng phân tích:** xem các nhánh có tiền tố chung, đệ quy trái và lựa chọn chồng lấn.
8. **Đối chiếu ví dụ:** xác nhận mọi chương trình mẫu hợp lệ đều được grammar chấp nhận và ví dụ sai bị từ chối đúng chỗ.
9. **Tách cú pháp khỏi ngữ nghĩa:** ghi nhận các điều kiện cần semantic analyzer kiểm tra.
10. **Duy trì phiên bản:** khi thay đổi production, đánh giá ảnh hưởng đến chương trình cũ và cập nhật tài liệu, parser cùng bộ kiểm thử.

Một grammar nên được xem là tài sản có phiên bản. Thay đổi từ khóa, cấu trúc biểu thức hoặc quy tắc optional có thể khiến chương trình cũ được phân tích khác đi, ngay cả khi backend không thay đổi.

## Kiểm thử grammar

Grammar cần được kiểm chứng bằng các tập đầu vào có chủ đích. Một số nhóm kiểm thử hữu ích:

### Ví dụ hợp lệ

Tạo ví dụ cho từng production và tổ hợp quan trọng. Với functionCall, cần thử lời gọi không đối số, một đối số và nhiều đối số. Với ruleDeclaration, cần thử có ELSE và không có ELSE.

### Ví dụ không hợp lệ

Thử thiếu từ khóa, sai thứ tự, thiếu dấu đóng ngoặc, dấu phẩy thừa, literal sai định dạng và phần lặp không có phần tử bắt buộc. Xác nhận parser báo lỗi gần vị trí gây lỗi.

### Kiểm thử precedence và associativity

Dùng biểu thức như a + b * c, a - b - c, a OR b AND c và các biểu thức có ngoặc để xác nhận AST có cấu trúc đúng.

### Kiểm thử biên

Kiểm tra chương trình rỗng, một khai báo, nhiều khai báo, danh sách dài, biểu thức lồng sâu và comment ở các vị trí khác nhau. Nếu grammar giới hạn độ sâu hoặc số phần tử, kiểm tra thông báo tương ứng.

### Kiểm thử hồi quy

Lưu các chương trình mẫu cùng AST hoặc kết quả phân tích mong đợi. Khi grammar thay đổi, chạy lại chúng để phát hiện cú pháp cũ bị phá vỡ hoặc được diễn giải khác ngoài dự kiến.

### Kiểm thử grammar tự động

Một số công cụ có thể sinh chuỗi theo grammar để kiểm tra parser, hoặc sinh chuỗi gần hợp lệ bằng cách thêm, xóa và thay token. Kết hợp property-based testing và fuzzing giúp phát hiện parser crash, treo hoặc xử lý sai đầu vào bất thường.

## Những lỗi thường gặp khi viết EBNF

### Nhầm terminal với nonterminal

Terminal là ký hiệu cố định hoặc token được lexer cung cấp; nonterminal là cấu trúc được định nghĩa bởi production. Nếu không phân biệt rõ, người đọc có thể không biết identifier là một token hay một production được khai triển bằng từng ký tự.

### Quên quy tắc bắt buộc trong phần lặp

{ item } cho phép không có item. Nếu danh sách cần ít nhất một phần tử, phải viết item, { separator, item } thay vì chỉ { item }.

### Dùng optional khiến cấu trúc quá rộng

Nhiều phần tùy chọn độc lập có thể cho phép những tổ hợp không hợp lệ. Ví dụ, nếu một khai báo có hai thành phần phải xuất hiện cùng nhau, không nên đặt chúng trong hai cặp [...] riêng biệt; hãy nhóm cả hai thành một phần tùy chọn.

### Không xác định precedence

Gộp mọi toán tử vào một production thường khiến cách nhóm biểu thức không rõ. Hãy phân tầng theo độ ưu tiên hoặc dùng cơ chế precedence được công cụ hỗ trợ.

### Không kiểm tra đệ quy trái

Đệ quy trái có thể hợp lệ với một số parser nhưng gây vấn đề cho recursive descent. Cần chọn parser trước hoặc biến đổi grammar phù hợp mà vẫn bảo toàn ngữ nghĩa.

### Coi grammar là đặc tả đầy đủ của chương trình

Parser chấp nhận cú pháp không có nghĩa tên, kiểu, quyền và quy tắc miền đều hợp lệ. Cần tách semantic analysis và runtime validation.

### Trộn nhiều dialect

Một tài liệu dùng = và dấu phẩy, phần khác dùng ::= và ký hiệu *, ? mà không giải thích sẽ gây khó khăn khi đọc hoặc đưa vào parser generator. Hãy chọn một quy ước và công bố nó.

## Kết luận

EBNF là ký pháp hữu ích để mô tả ngữ pháp DSL một cách có cấu trúc. Các production định nghĩa nonterminal thông qua terminal và những cấu trúc như nối tiếp, lựa chọn, nhóm, phần tùy chọn và phần lặp. Khi kết hợp các quy tắc này, người thiết kế có thể mô tả từ cấu trúc chương trình đến biểu thức và literal.

Một grammar EBNF tốt cần rõ về dialect, token, precedence, associativity, đệ quy và các trường hợp mơ hồ. Nó mô tả cú pháp; những điều kiện như phân giải tên, kiểm tra kiểu, quyền và quy tắc nghiệp vụ thường cần semantic analyzer. Khi được kiểm thử bằng ví dụ hợp lệ, không hợp lệ và trường hợp biên, EBNF trở thành nền tảng đáng tin cậy cho parser, tài liệu và công cụ phát triển DSL.

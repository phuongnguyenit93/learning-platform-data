# Kiểm thử quy tắc lexer

## Vai trò của kiểm thử lexer trong DSL

Lexer (lexical analyzer, còn gọi là tokenizer) là thành phần đầu tiên trong frontend DSL chịu trách nhiệm biến chuỗi ký tự nguồn thành một dãy token. Parser dùng dãy token đó để xác định cấu trúc cú pháp. Nếu lexer nhận diện sai token, mọi giai đoạn phía sau có thể hiểu sai chương trình dù grammar và semantic analyzer được triển khai đúng.

**Kiểm thử quy tắc lexer** xác nhận rằng lexer phân loại ký tự và chuỗi ký tự theo đúng đặc tả từ vựng của DSL. Việc kiểm thử cần bao gồm cả đầu vào hợp lệ, đầu vào không hợp lệ, ranh giới token, trường hợp mơ hồ, vị trí nguồn và cách lexer tiếp tục sau lỗi.

Ví dụ, với nguồn:

~~~text
WHEN order.total >= 1000 AND customer.active
~~~

lexer có thể tạo ra dãy token:

~~~text
WHEN_KEYWORD
IDENTIFIER("order")
DOT
IDENTIFIER("total")
GREATER_EQUAL
INTEGER_LITERAL(1000)
AND_KEYWORD
IDENTIFIER("customer")
DOT
IDENTIFIER("active")
EOF
~~~

Nếu lexer tách toán tử >= thành hai token GREATER và EQUAL, parser có thể từ chối một biểu thức vốn hợp lệ. Nếu lexer nhận diện WHEN như một identifier thay vì từ khóa, cấu trúc rule cũng có thể không được phân tích đúng.

Kiểm thử lexer tập trung vào hợp đồng giữa văn bản nguồn và token stream. Nó không thay thế kiểm thử parser hoặc kiểm tra ngữ nghĩa. Một token stream đúng chỉ chứng minh rằng phần từ vựng được nhận diện đúng; nó chưa chứng minh chuỗi token tạo thành chương trình hợp lệ hoặc có ý nghĩa nghiệp vụ.

## Xác định hợp đồng từ vựng trước khi kiểm thử

Muốn kiểm thử có căn cứ, cần có đặc tả từ vựng đủ rõ. Mỗi quy tắc nên xác định:

- Tên loại token.
- Mẫu ký tự hoặc điều kiện nhận diện.
- Giá trị được lưu trong token.
- Phạm vi ký tự được chấp nhận.
- Quy tắc phân biệt chữ hoa và chữ thường.
- Ưu tiên khi nhiều quy tắc cùng khớp.
- Cách xử lý khoảng trắng và comment.
- Cách ghi nhận vị trí nguồn.
- Hành vi khi token chưa hoàn chỉnh hoặc không hợp lệ.

Ví dụ bảng token cho một DSL quy tắc:

| Nhóm | Token ví dụ | Dạng đầu vào |
|---|---|---|
| Từ khóa | RULE, WHEN, THEN, ELSE | Từ khóa được định nghĩa |
| Định danh | IDENTIFIER | order, customer, calculateTax |
| Số | INTEGER_LITERAL, DECIMAL_LITERAL | 12, 12.5 |
| Chuỗi | STRING_LITERAL | "VIP customer" |
| Boolean | TRUE, FALSE | TRUE, FALSE |
| Toán tử | PLUS, MINUS, GREATER_EQUAL, AND | +, -, >=, AND |
| Dấu phân cách | DOT, COMMA, LPAREN, RPAREN | ., ,, (, ) |
| Kết thúc | NEWLINE, SEMICOLON, EOF | Xuống dòng, ;, cuối tệp |
| Trivia | WHITESPACE, COMMENT | Dấu cách, comment nếu lexer giữ lại |
| Lỗi | INVALID_TOKEN hoặc lexical diagnostic | Ký tự không được phép |

Tên token và cú pháp ở bảng chỉ mang tính minh họa. Đặc tả thật cần xác định rõ token nào được parser nhận, token nào bị bỏ qua và token nào được giữ lại cho formatter hoặc IDE.

### Tách lexical grammar khỏi syntactic grammar

Lexical grammar mô tả cách tạo token từ ký tự. Syntactic grammar mô tả cách kết hợp token thành biểu thức và câu lệnh.

Ví dụ, lexer có thể xác định:

- Một identifier bắt đầu bằng chữ cái hoặc dấu gạch dưới.
- Một integer gồm một hoặc nhiều chữ số.
- Chuỗi được bao bởi dấu nháy kép và hỗ trợ escape.
- Toán tử >= là một token.

Parser sau đó quyết định một biểu thức so sánh có dạng operand, GREATER_EQUAL, operand hay không.

Khi viết test, cần xác định lỗi thuộc giai đoạn nào. Chuỗi số sai định dạng có thể là lỗi lexical nếu quy tắc số không chấp nhận nó; một dãy token hợp lệ nhưng sai thứ tự thường là lỗi cú pháp của parser. Ranh giới này cần nhất quán để test không phụ thuộc vào chi tiết triển khai ngẫu nhiên.

## Thiết kế một lexer test harness

Một test harness cho lexer nên cho phép cung cấp văn bản nguồn và so sánh kết quả với token mong đợi. Mỗi token thường có ít nhất:

- Loại token (token kind).
- Giá trị nguyên gốc hoặc giá trị đã giải mã.
- Offset bắt đầu và kết thúc.
- Dòng và cột nếu lexer tính sẵn.
- Thông tin nguồn nếu DSL hỗ trợ nhiều tệp hoặc include.
- Trạng thái lỗi hoặc trivia nếu có.

Một test đơn giản có thể được mô tả như sau:

~~~text
Input:
  order.total >= 1000

Expected:
  IDENTIFIER("order")
  DOT
  IDENTIFIER("total")
  GREATER_EQUAL
  INTEGER_LITERAL(1000)
  EOF
~~~

Một API kiểm thử khái quát:

~~~text
tokens = lex(source)

assert tokenKinds(tokens) == expectedKinds
assert tokenValues(tokens) == expectedValues
assert tokenSpans(tokens) == expectedSpans
assert diagnostics(tokens) == expectedDiagnostics
~~~

Không phải test nào cũng cần so sánh mọi trường. Test tokenization cơ bản có thể chỉ xác nhận loại và giá trị token; test vị trí cần kiểm tra span; test lỗi cần kiểm tra mã lỗi, vị trí và thông tin mong đợi.

### So sánh token có cấu trúc

Không nên chỉ so sánh chuỗi debug do lexer in ra nếu định dạng chuỗi đó có thể thay đổi. Tốt hơn là so sánh cấu trúc token: loại, giá trị, offset và trạng thái. Nếu dùng snapshot hoặc golden file, định dạng snapshot cần ổn định và dễ đọc.

Ví dụ bảng kỳ vọng:

| Index | Kind | Value | Start | End |
|---:|---|---|---:|---:|
| 0 | IDENTIFIER | order | 0 | 5 |
| 1 | DOT | . | 5 | 6 |
| 2 | IDENTIFIER | total | 6 | 11 |
| 3 | GREATER_EQUAL | >= | 12 | 14 |
| 4 | INTEGER_LITERAL | 1000 | 15 | 19 |
| 5 | EOF | — | 19 | 19 |

Offset trong ví dụ là offset ký tự của chuỗi giả định. Đặc tả và test phải thống nhất offset tính theo byte, Unicode code point, UTF-16 code unit hay một quy ước khác.

### Kiểm tra token cuối EOF

Lexer thường phát ra token EOF để parser biết luồng token đã kết thúc. Cần kiểm tra:

- EOF xuất hiện đúng một lần theo hợp đồng.
- Vị trí EOF nằm ở cuối nguồn.
- Nguồn rỗng vẫn có EOF nếu lexer quy định như vậy.
- Lexer không phát thêm token sau EOF.
- Comment hoặc whitespace ở cuối nguồn không làm sai vị trí EOF.

Nếu lexer trả token theo iterator hoặc stream, cần xác nhận hành vi khi gọi tiếp sau EOF được định nghĩa rõ, chẳng hạn trả EOF ổn định hoặc báo đã hết luồng.

## Kiểm thử ranh giới token và quy tắc ưu tiên

Ranh giới token là một trong những nguồn lỗi phổ biến nhất. Hai chuỗi ký tự liền nhau có thể tạo thành một token hoặc nhiều token tùy đặc tả.

### Quy tắc khớp dài nhất

Nhiều lexer dùng nguyên tắc maximal munch (khớp dài nhất): trong các token hợp lệ bắt đầu tại vị trí hiện tại, lexer chọn token khớp được nhiều ký tự nhất, sau đó áp dụng quy tắc ưu tiên nếu vẫn còn nhiều lựa chọn.

Ví dụ có các toán tử:

~~~text
>
>=
==
!=
&&
||
~~~

Với nguồn >=, lexer nên tạo một token GREATER_EQUAL thay vì GREATER rồi EQUAL nếu toán tử hai ký tự được đặc tả. Test cần bao gồm cả toán tử đơn và toán tử dài:

| Input | Expected token |
|---|---|
| > | GREATER |
| >= | GREATER_EQUAL |
| = | ASSIGN |
| == | EQUAL_EQUAL |
| ! | NOT nếu được hỗ trợ |
| != | NOT_EQUAL |
| && | LOGICAL_AND |
| & | Lỗi hoặc token riêng theo đặc tả |

Cũng cần thử chuỗi dài hơn một toán tử hợp lệ, ví dụ === hoặc >>>. Lexer phải phân loại theo quy tắc đã công bố; không được tự suy đoán rằng mọi tổ hợp ký hiệu đều hợp lệ.

### Tiền tố chung giữa các token

Một số token có chung tiền tố. Ví dụ dấu chấm có thể là token DOT, đồng thời dấu chấm cũng có thể xuất hiện trong số thập phân. Test nên kiểm tra:

~~~text
object.field
12.5
12.
.5
1..4
~~~

DSL có thể chấp nhận một số dạng và từ chối dạng khác. Ví dụ, nếu số thập phân bắt buộc có chữ số ở hai phía dấu chấm, 12.5 hợp lệ còn 12. và .5 không hợp lệ. Nếu DSL cho phép .5, lexer cần có quy tắc phân biệt với DOT.

Một nhóm test tốt ghi rõ token stream và diagnostics cho từng trường hợp thay vì chỉ đánh dấu pass/fail.

### Ưu tiên giữa từ khóa và identifier

Từ khóa thường có hình dạng giống identifier. Ví dụ RULE cũng có thể khớp quy tắc identifier. Một chiến lược phổ biến là lexer trước tiên nhận diện chuỗi định danh đầy đủ, sau đó tra cứu bảng từ khóa:

~~~text
source word -> identifier candidate -> keyword lookup -> final token kind
~~~

Cách này tránh việc một từ khóa ngắn bị nhận diện bên trong identifier dài hơn. Nếu DSL có từ khóa RULE, test nên bao gồm:

| Input | Kết quả mong đợi |
|---|---|
| RULE | RULE_KEYWORD |
| rule | Phụ thuộc quy tắc case sensitivity |
| RULES | IDENTIFIER |
| MY_RULE | IDENTIFIER |
| RULE1 | IDENTIFIER |
| ruleName | IDENTIFIER |

Không được nhận diện RULE là từ khóa ở đầu chuỗi RULES nếu quy tắc yêu cầu khớp toàn bộ identifier.

### Từ khóa ngữ cảnh

Một số DSL chỉ coi một từ là từ khóa trong một vị trí nhất định. Ví dụ, FROM có thể là từ khóa trong câu truy vấn nhưng được phép làm tên thuộc tính ở nơi khác. Đây là contextual keyword.

Kiểm thử cần bao gồm từ đó ở mọi ngữ cảnh liên quan. Nếu lexer chỉ phát token IDENTIFIER và parser quyết định theo ngữ cảnh, test lexer cần xác nhận hành vi đó. Nếu lexer phát token riêng, test cần xác nhận vị trí và quy tắc phân biệt.

Không nên kiểm tra contextual keyword bằng một test đơn lẻ ở vị trí quen thuộc. Lỗi thường xuất hiện khi từ đó được dùng làm tên biến, tên thuộc tính hoặc thành phần của qualified name.

## Kiểm thử identifier

Identifier là tên của biến, thuộc tính, module, hàm hoặc kiểu. Quy tắc identifier quyết định ký tự đầu, ký tự tiếp theo, độ dài và chính sách Unicode.

### Ký tự bắt đầu và ký tự tiếp theo

Ví dụ một quy tắc đơn giản:

~~~text
identifier = letter, { letter | digit | "_" }
~~~

Theo quy tắc này, các tên sau hợp lệ:

~~~text
order
customer2
_order
discountRate
~~~

Các tên sau không hợp lệ theo grammar minh họa:

~~~text
2customer
customer-name
"order"
~~~

Nếu DSL cho phép dấu gạch ngang trong identifier, lexer phải xử lý xung đột với toán tử trừ. Ví dụ order-total có thể là một identifier hoặc ba token order, MINUS, total. Quyết định này cần được thể hiện trong đặc tả và test.

### Độ dài và giới hạn

Nếu DSL đặt giới hạn độ dài identifier, cần kiểm tra:

- Độ dài tối thiểu.
- Identifier đúng giới hạn tối đa.
- Identifier vượt giới hạn một ký tự.
- Identifier dài bất thường.
- Cách tính độ dài với ký tự Unicode nhiều code unit.
- Diagnostics có trỏ đúng đầu hoặc cuối identifier hay không.

Không nên chỉ kiểm tra giới hạn bằng số byte nếu đặc tả quy định số ký tự. Với Unicode, một ký tự nhìn thấy có thể gồm nhiều code point hoặc nhiều UTF-16 code unit.

### Unicode và chuẩn hóa

Nếu DSL hỗ trợ Unicode identifier, cần xác định các nhóm ký tự được chấp nhận. Có thể dùng quy tắc dựa trên Unicode identifier properties thay vì chỉ kiểm tra ASCII.

Các trường hợp cần cân nhắc:

- Chữ có dấu trong nhiều hệ chữ.
- Ký tự kết hợp (combining mark).
- Chữ số Unicode.
- Ký tự tương tự nhau về hình thức nhưng khác code point.
- Unicode normalization như NFC.
- Ký tự điều khiển hoặc zero-width.

Hai chuỗi có thể nhìn giống nhau nhưng có biểu diễn Unicode khác nhau. DSL cần quyết định có chuẩn hóa identifier trước khi so sánh hay không. Nếu có, diagnostics và source span vẫn phải trỏ về văn bản gốc.

Nếu DSL chỉ chấp nhận ASCII, cần test các ký tự ngoài ASCII để bảo đảm lexer báo lỗi rõ thay vì âm thầm bỏ qua hoặc biến đổi chúng.

## Kiểm thử literal số

Literal số thường có nhiều dạng và nhiều trường hợp biên. Lexer cần xác định chính xác số nguyên, số thập phân, exponent, dấu, dấu phân nhóm và hậu tố đơn vị nếu DSL hỗ trợ.

### Số nguyên

Với quy tắc số nguyên chỉ gồm chữ số:

~~~text
integer = digit, { digit }
~~~

Test cơ bản:

| Input | Mong đợi |
|---|---|
| 0 | INTEGER_LITERAL |
| 7 | INTEGER_LITERAL |
| 12345 | INTEGER_LITERAL |
| 0007 | Theo chính sách số 0 ở đầu |
| +7 | PLUS và INTEGER hoặc signed literal theo đặc tả |
| -7 | MINUS và INTEGER hoặc signed literal theo đặc tả |
| 12a | Tokenization hoặc lexical error theo quy tắc identifier/số |

Không nên mặc định dấu âm là một phần của literal. Nhiều lexer tách MINUS thành toán tử và số thành token riêng; parser quyết định dấu âm là unary operator. Cách này giúp cùng một token MINUS dùng cho phép trừ và phép đổi dấu.

### Số thập phân

Nếu DSL dùng dấu chấm làm dấu thập phân, các trường hợp cần thử gồm:

~~~text
0.0
12.5
.5
5.
5.0.1
1..2
~~~

Đặc tả có thể chỉ chấp nhận số có chữ số ở cả hai phía dấu chấm. Khi đó .5 và 5. bị từ chối hoặc được tách thành token khác theo quy tắc rõ ràng.

Test phải xác nhận lexer không vô tình nhận 5.0.1 thành hai literal liền nhau mà không có toán tử hoặc dấu phân cách nếu grammar không cho phép.

### Số mũ

Nếu hỗ trợ exponent, các dạng thường gặp:

~~~text
1e3
1E3
1.25e-2
1e+6
~~~

Các trường hợp sai:

~~~text
1e
1e+
1e-
1.2e3.4
~~~

Lexer cần phân biệt exponent hợp lệ với identifier bắt đầu bằng e. Cần xác định có chấp nhận chữ E hoa không, dấu trong exponent có bắt buộc hay không và số mũ có giới hạn không.

### Dấu phân nhóm và locale

Nếu DSL cho phép dấu phân nhóm hàng nghìn, cần tránh nhập nhằng giữa dấu phẩy phân tách đối số và dấu phẩy trong số. Một DSL kỹ thuật thường chọn cú pháp số ổn định, chẳng hạn dấu chấm thập phân và không dùng dấu phân nhóm trong literal nguồn.

Nếu có nhiều locale, không nên để cùng một tệp DSL được hiểu khác nhau tùy cài đặt máy. Cú pháp nguồn nên có quy tắc cố định; locale chủ yếu ảnh hưởng định dạng hiển thị.

### Hậu tố và đơn vị

Nếu số có thể có hậu tố như 10ms, 5kg hoặc 12km/h, cần kiểm tra ranh giới giữa số và đơn vị:

~~~text
10ms
10 ms
10m
10meter
10meters
10m/s
10msExtra
~~~

Lexer có thể tạo token QUANTITY_LITERAL hoặc NUMBER theo sau UNIT token. Dù chọn cách nào, test phải xác nhận đơn vị được nhận diện theo catalog hợp lệ và không nuốt nhầm phần identifier phía sau.

## Kiểm thử string literal

String literal cần được kiểm tra ở cả lớp từ vựng và lớp giải mã giá trị. Lexer phải nhận diện điểm bắt đầu, điểm kết thúc, escape sequence, newline và chuỗi chưa đóng.

### Chuỗi cơ bản

~~~text
""
"hello"
"VIP customer"
"Line one"
~~~

Cần xác nhận giá trị token sau khi giải mã có đúng nội dung, đồng thời source span bao gồm đúng dấu nháy theo quy ước.

### Escape sequence

Nếu DSL hỗ trợ escape, các trường hợp thường gặp:

| Dạng nguồn | Giá trị dự kiến |
|---|---|
| \\" | Dấu nháy kép |
| \\\\ | Dấu gạch chéo ngược |
| \\n | Ký tự xuống dòng |
| \\t | Tab |
| \\r | Carriage return |
| \\uXXXX | Code point hoặc code unit theo quy tắc DSL |

Cần quy định escape không hợp lệ. Ví dụ, nếu \\q không được hỗ trợ, lexer nên báo lỗi tại escape thay vì âm thầm giữ hoặc xóa ký tự.

### Chuỗi chưa đóng

Test các nguồn thiếu dấu nháy đóng:

~~~text
"hello
"hello
world
~~~

Nếu DSL không cho newline trong string thường, lexer cần báo lỗi trước hoặc tại newline. Nếu DSL hỗ trợ multiline string, cần xác định delimiter riêng và quy tắc kết thúc.

### Chuỗi raw và multiline

Nếu DSL có raw string hoặc multiline string, test cần xác nhận:

- Delimiter mở và đóng.
- Escape có được xử lý hay giữ nguyên.
- Cách biểu diễn delimiter bên trong nội dung.
- Newline có được giữ nguyên không.
- Indentation có bị loại bỏ không.
- EOF trước delimiter đóng được báo thế nào.

Đặc biệt, không nên nhận diện comment marker bên trong string như comment. Chuỗi "https://example.test" vẫn là một literal duy nhất nếu dấu // chỉ là nội dung.

## Kiểm thử comment và whitespace

Comment và whitespace thường bị lexer bỏ qua, nhưng cách xử lý cần nhất quán.

### Khoảng trắng giữa token

Nếu dấu cách và tab không có ý nghĩa cú pháp, các biến thể trình bày sau thường tạo cùng token stream:

~~~text
order.total>=1000
order.total >= 1000
order   .   total   >=   1000
~~~

Test nên so sánh token kind và value, đồng thời xác nhận source span thay đổi đúng theo vị trí thực tế.

### Newline

Newline có thể là whitespace thông thường hoặc token kết thúc câu lệnh. Cần test theo chính sách của DSL:

- LF.
- CRLF.
- CR nếu được hỗ trợ.
- Nhiều dòng trống.
- Newline ở đầu và cuối tệp.
- Newline trong biểu thức đang mở.
- Newline sau comment cuối dòng.

Nếu DSL dùng indentation, cần thêm test INDENT/DEDENT và trường hợp trộn tab với dấu cách.

### Comment một dòng và comment khối

Ví dụ:

~~~text
# comment đầu dòng
RULE "VIP"  # comment cuối dòng

/* comment
   nhiều dòng */
WHEN customer.active
~~~

Kiểm tra comment có bị bỏ đúng vị trí không và có làm dính token hai bên hay không. Ví dụ:

~~~text
customer/* note */segment
~~~

Nếu comment được phép đứng như whitespace, kết quả phải giữ hai identifier riêng. Nếu grammar cấm comment ở vị trí đó, lexer/parser cần báo lỗi theo hợp đồng.

### Ký hiệu comment trong string

~~~text
message = "Use // in this URL"
path = "folder/*literal*/name"
~~~

Các ký hiệu trong chuỗi không được mở comment. Test này phát hiện lỗi phổ biến khi comment được xử lý bằng cách xóa văn bản thuần túy trước khi nhận diện string.

## Kiểm thử vị trí nguồn và span

Token span rất quan trọng cho parser diagnostics, IDE, syntax highlighting và refactoring. Một lexer có thể nhận đúng loại token nhưng gắn sai vị trí; lỗi này thường chỉ lộ ra khi người dùng nhận thông báo lỗi ở vị trí không chính xác.

### Offset bắt đầu và kết thúc

Với mỗi token, xác nhận:

- Start offset trỏ đúng ký tự đầu tiên của token.
- End offset là exclusive hay inclusive theo quy ước.
- Độ dài span phù hợp với nội dung token.
- Token liền nhau có span đúng, kể cả khi không có whitespace.
- EOF có span rỗng ở cuối nguồn.

Ví dụ, với nguồn:

~~~text
a >= 10
~~~

Nếu offset tính theo ký tự và bắt đầu từ 0:

| Token | Start | End (exclusive) |
|---|---:|---:|
| IDENTIFIER(a) | 0 | 1 |
| GREATER_EQUAL | 2 | 4 |
| INTEGER_LITERAL(10) | 5 | 7 |
| EOF | 7 | 7 |

### Dòng và cột

Nếu lexer lưu line/column, cần test:

- Token ở dòng đầu tiên.
- Token sau một newline.
- Token sau nhiều dòng.
- Tab trước token.
- Ký tự Unicode nhiều byte hoặc nhiều code unit.
- CRLF được tính là một lần xuống dòng.
- Ký tự kết hợp Unicode.

Đặc tả nên xác định cột đếm theo byte, code point, UTF-16 code unit hay cột hiển thị. Editor và compiler cần dùng quy ước tương thích hoặc có ánh xạ giữa chúng.

### Nguồn nhiều tệp

Nếu DSL hỗ trợ include hoặc import nguồn, token cần giữ source ID. Test cần xác nhận token từ tệp được include trỏ về tệp gốc, không phải chỉ về văn bản đã ghép. Nếu có macro expansion, cần giữ mapping đến vị trí định nghĩa và vị trí gọi macro.

## Kiểm thử lỗi lexical và phục hồi

Lexer cần xử lý đầu vào sai một cách có kiểm soát. Tùy mục tiêu, nó có thể dừng ngay, phát token lỗi rồi tiếp tục, hoặc thu thập nhiều diagnostics.

Các lỗi thường gặp:

- Ký tự không được phép.
- String literal chưa đóng.
- Escape sequence không hợp lệ.
- Comment khối chưa đóng.
- Số sai định dạng.
- Identifier vượt giới hạn.
- Ký hiệu toán tử không hợp lệ.
- Unicode không hợp lệ hoặc không được hỗ trợ.
- Hậu tố đơn vị không được nhận diện.
- Kết thúc tệp ở giữa một token cần delimiter.

### Kiểm tra nội dung diagnostics

Một lexical diagnostic nên có mã ổn định, vị trí, mô tả và thông tin hữu ích để sửa lỗi. Test nên xác nhận mã và span, không nên phụ thuộc vào toàn bộ câu chữ nếu câu chữ có thể được biên tập.

Ví dụ:

~~~text
rules.dsl:4:12: error LEX-STRING-001
Unterminated string literal.
~~~

Hoặc:

~~~text
rules.dsl:7:9: error LEX-CHAR-002
Unexpected character: @
~~~

Thông báo minh họa cần khớp chính sách thật của DSL. Không nên chỉ kiểm tra rằng có một lỗi; cần xác nhận lexer báo đúng loại lỗi và không gán nhầm vị trí.

### Phục hồi sau lỗi

Nếu lexer tiếp tục sau lỗi, cần kiểm tra nó có tìm được ranh giới token tiếp theo và không tạo ra chuỗi diagnostics vô nghĩa.

Ví dụ:

~~~text
SET value = @
SET next = 10
~~~

Nếu @ không hợp lệ, lexer có thể phát INVALID_TOKEN hoặc ghi diagnostic, sau đó tiếp tục ở dòng kế tiếp để nhận diện SET, next và 10. Chính sách phục hồi phải tránh lặp vô hạn tại cùng offset.

Một số lỗi không thể phục hồi cục bộ, chẳng hạn string chưa đóng kéo dài đến EOF. Khi đó, lexer có thể kết thúc với một diagnostic duy nhất. Test cần xác nhận hành vi theo đặc tả.

## Phân loại bộ kiểm thử lexer

Không có một loại test nào đủ bao phủ mọi rủi ro. Nên kết hợp nhiều lớp kiểm thử có mục tiêu rõ ràng.

### Unit test theo từng quy tắc

Mỗi nhóm token có các test nhỏ, độc lập:

- Identifier.
- Keyword.
- Number literal.
- String literal.
- Operator.
- Delimiter.
- Comment.
- Whitespace.
- Invalid character.

Unit test giúp khoanh vùng lỗi và dễ xác định quy tắc nào bị phá vỡ.

### Boundary test

Boundary test tập trung vào điểm chuyển giữa hợp lệ và không hợp lệ: số có dấu chấm cuối, identifier bắt đầu bằng số, toán tử có tiền tố chung, chuỗi thiếu delimiter, độ dài đúng ngưỡng và vượt ngưỡng.

Ví dụ, nếu identifier tối đa 64 code point, cần test 63, 64 và 65 code point. Nếu literal số cho phép tối đa 100 chữ số, cần test đúng 100 và 101 chữ số.

### Golden test hoặc snapshot test

Golden test lưu đầu vào và token stream mong đợi. Chúng hữu ích khi lexer có nhiều loại token hoặc cần bảo đảm kết quả ổn định qua refactor.

Một fixture có thể chứa:

~~~text
# source.dsl
RULE "VIP"
WHEN order.total >= 1000
THEN discount.rate = 10
~~~

Kết quả kỳ vọng được lưu thành danh sách token với kind, value và span. Khi thay đổi grammar từ vựng, diff giúp reviewer thấy token nào thay đổi.

Snapshot không thay thế test có assertion cụ thể. Nếu snapshot quá lớn hoặc khó đọc, lỗi nhỏ có thể bị che khuất. Nên chia fixture theo chủ đề và đặt tên rõ.

### Property-based test

Property-based testing tạo nhiều đầu vào theo các thuộc tính mong đợi thay vì chỉ liệt kê ví dụ. Ví dụ:

- Mọi chuỗi identifier được sinh theo grammar đều tạo đúng một token identifier hoặc keyword tương ứng.
- Mọi số nguyên được sinh trong miền cho phép đều được nhận diện và giải mã đúng.
- Token span luôn nằm trong phạm vi nguồn.
- Lexer luôn tiến về phía trước hoặc kết thúc; không lặp vô hạn tại cùng offset.
- Chèn whitespace ở vị trí được phép không làm thay đổi loại và giá trị token.
- Tokenize rồi tái tạo nguồn theo quy tắc trivia có thể bảo toàn nội dung khi chế độ lossless được hỗ trợ.

Property-based test đặc biệt hữu ích cho tập đầu vào rộng, Unicode và tổ hợp ký hiệu. Khi phát hiện lỗi, framework thường có thể thu nhỏ đầu vào để tìm ví dụ phản chứng đơn giản hơn.

### Fuzz testing

Fuzzing cung cấp đầu vào ngẫu nhiên hoặc biến đổi mạnh để tìm crash, treo, lỗi bộ nhớ hoặc trường hợp lexer xử lý quá chậm. Lexer nên chịu được chuỗi byte/ký tự bất thường mà không làm tiến trình bị sập.

Có thể dùng:

- Random bytes nếu API nhận byte.
- Random Unicode strings nếu API nhận text.
- Token mutation từ chương trình hợp lệ.
- Chuỗi lặp rất dài.
- Ký tự điều khiển và escape bất thường.
- Các dãy dấu nháy, dấu gạch chéo và toán tử lặp.

Fuzzing không chứng minh lexer đúng về ngữ nghĩa. Nó bổ sung cho test xác định bằng cách khám phá những đầu vào mà người viết test chưa nghĩ đến.

### Integration test với parser

Lexer có thể được kiểm thử độc lập, nhưng cần một số integration test để xác nhận token stream thực sự tương thích với parser. Ví dụ, một rule hoàn chỉnh cần đi qua lexer và parser để tạo AST mong đợi.

Nếu integration test thất bại, cần xác định lỗi nằm ở tokenization hay grammar. Một cách hữu ích là lưu token stream trung gian trong thông tin chẩn đoán của test.

### Regression test

Mỗi lỗi lexer đã được sửa nên có một test tái hiện. Ví dụ, nếu RULES từng bị nhận diện nhầm thành RULE rồi IDENTIFIER, cần giữ test đó để lỗi không quay lại.

Regression test nên nhỏ, đặt tên theo hành vi và kiểm tra kết quả mong đợi cụ thể. Không cần thêm nhiều test trùng nhau nếu một fixture đã bao phủ đúng trường hợp.

## Kiểm thử lexer theo bảng dữ liệu

Với quy tắc từ vựng có nhiều trường hợp, table-driven test giúp tránh lặp mã kiểm thử. Một bảng có thể gồm đầu vào, token mong đợi và diagnostic mong đợi.

Ví dụ cho toán tử:

| Input | Token mong đợi | Ghi chú |
|---|---|---|
| + | PLUS | Toán tử một ký tự |
| - | MINUS | Có thể là unary hoặc binary ở parser |
| >= | GREATER_EQUAL | Khớp dài hơn > |
| > | GREATER | Token riêng |
| == | EQUAL_EQUAL | Không nhầm với ASSIGN |
| = | ASSIGN | Token riêng |
| && | LOGICAL_AND | Nếu DSL hỗ trợ |
| & | Lỗi hoặc BIT_AND | Theo đặc tả |

Ví dụ cho số:

| Input | Kết quả | Ghi chú |
|---|---|---|
| 0 | Hợp lệ | Giá trị nhỏ nhất |
| 42 | Hợp lệ | Số nguyên |
| 3.14 | Hợp lệ nếu hỗ trợ decimal | Số thập phân |
| 3. | Theo đặc tả | Dấu chấm cuối |
| .14 | Theo đặc tả | Thiếu phần nguyên |
| 1e5 | Theo đặc tả | Exponent |
| 1e | Lỗi hoặc token tách | Exponent thiếu chữ số |
| 12abc | Theo đặc tả | Ranh giới số và identifier |

Table-driven test giúp thêm trường hợp biên mà không cần tạo một hàm riêng cho từng chuỗi.

## Kiểm thử tính bất biến và quan hệ biến đổi

Ngoài các ví dụ đầu vào cố định, có thể kiểm tra một số quan hệ mà lexer cần duy trì.

### Thêm whitespace ở vị trí được phép

Nếu whitespace không có ý nghĩa cấu trúc tại vị trí giữa hai token, thêm một hoặc nhiều dấu cách không nên làm thay đổi loại và giá trị token:

~~~text
order.total>=100
order . total >= 100
~~~

Token span sẽ thay đổi, nên chỉ so sánh phần không phụ thuộc vị trí. Nếu newline là token có ý nghĩa, không áp dụng phép biến đổi này qua newline.

### Thay đổi cách viết keyword theo chính sách case

Nếu DSL không phân biệt chữ hoa và chữ thường, các dạng RULE, Rule và rule cần tạo cùng token kind. Nếu DSL phân biệt case, test cần xác nhận chỉ cách viết chuẩn là keyword và các dạng còn lại là identifier hoặc lỗi theo đặc tả.

### Token reconstruction

Nếu lexer giữ trivia và token gốc, một công cụ có thể tái tạo nguồn bằng cách nối lexeme và trivia theo thứ tự. Test có thể xác nhận reconstruction giữ nguyên nội dung byte hoặc ký tự theo chính sách encoding.

Nếu lexer loại bỏ comment và whitespace, không thể yêu cầu tái tạo nguyên văn. Khi đó chỉ có thể kiểm tra cấu trúc token hoặc định dạng chuẩn hóa.

### Tiến triển của lexer

Với mọi đầu vào, mỗi bước lexer phải tiêu thụ ít nhất một đơn vị đầu vào hoặc kết thúc. Đây là thuộc tính quan trọng để tránh vòng lặp vô hạn khi gặp ký tự không hợp lệ hoặc token rỗng.

Test có thể đặt giới hạn thời gian hoặc đếm số lần lexer tiến offset. Khi vượt giới hạn, test cần cung cấp đầu vào nhỏ nhất có thể để tái hiện.

## Hiệu năng và giới hạn tài nguyên

Lexer thường tuyến tính theo độ dài đầu vào trong thiết kế thông thường, nhưng regex phức tạp hoặc backtracking không kiểm soát có thể gây thời gian xử lý tăng mạnh. Kiểm thử hiệu năng nên tập trung vào đầu vào đại diện và trường hợp xấu.

Các kịch bản cần cân nhắc:

- Tệp lớn với nhiều token ngắn.
- Một identifier hoặc string rất dài.
- Hàng triệu dấu phân cách lặp lại.
- Nhiều comment khối hoặc chuỗi escape.
- Unicode phức tạp.
- Nguồn có rất nhiều lỗi lexical.
- Token có mẫu regex dễ gây backtracking.

Cần đo thời gian, bộ nhớ và số token tạo ra. Không nên đặt ngưỡng hiệu năng tùy ý; hãy dựa trên kích thước tệp thực tế và yêu cầu phản hồi của compiler hoặc IDE.

Giới hạn tài nguyên có thể gồm độ dài token tối đa, kích thước nguồn tối đa, số diagnostics tối đa và thời gian xử lý. Khi vượt giới hạn, lexer nên trả lỗi có kiểm soát thay vì treo hoặc tiêu thụ bộ nhớ không giới hạn.

## Kiểm thử lexer gia tăng trong IDE

Trong IDE, lexer có thể chạy lại khi người dùng sửa một phần nhỏ của tệp. Incremental lexing cần giữ kết quả đúng khi văn bản được chèn, xóa hoặc thay thế.

Các tình huống quan trọng:

- Chèn ký tự vào giữa identifier.
- Xóa dấu nháy đóng của string.
- Thêm dấu comment mở ở đầu dòng.
- Đổi một toán tử đơn thành toán tử hai ký tự.
- Chèn newline làm thay đổi token NEWLINE hoặc indentation.
- Sửa một ký tự Unicode có độ dài mã hóa khác.
- Chỉnh sửa trước vùng có token dài hoặc comment nhiều dòng.

Test incremental cần so sánh kết quả với việc lex lại toàn bộ nguồn. Với cùng một văn bản cuối cùng, hai cách phải tạo token stream và diagnostics tương đương. Đây là một oracle hữu ích để phát hiện lỗi cache hoặc tính toán vùng bị ảnh hưởng sai.

Nếu lexer có trạng thái qua nhiều dòng, chẳng hạn multiline string hoặc block comment, một chỉnh sửa ở đầu tệp có thể làm thay đổi cách hiểu các dòng sau. Incremental lexer cần tìm lại điểm đồng bộ phù hợp thay vì chỉ cập nhật vùng ký tự vừa sửa.

## Ví dụ bộ test cho một lexer DSL

Giả sử DSL có các quy tắc:

- Keyword RULE, WHEN, THEN, ELSE không phân biệt chữ hoa/thường.
- Identifier bắt đầu bằng chữ cái hoặc dấu gạch dưới, theo sau là chữ cái, chữ số hoặc dấu gạch dưới.
- Số gồm integer hoặc decimal với ít nhất một chữ số ở hai phía dấu chấm.
- String dùng dấu nháy kép, hỗ trợ escape nháy và gạch chéo ngược.
- Toán tử >=, <=, ==, != được ưu tiên hơn toán tử một ký tự.
- Comment một dòng bắt đầu bằng #.
- Dấu cách và tab bị bỏ qua; newline tạo token NEWLINE.

Một tập ví dụ có thể gồm:

~~~text
Input:
RULE "VIP"
WHEN order.total >= 1000
THEN discount.rate = 10
~~~

Token stream mong đợi:

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
NEWLINE
EOF
~~~

Các trường hợp biên:

~~~text
RULES
Rule
_rule2
2rule
12.5
12.
.5
>=
>
"hello"
"hello
# comment
"// not a comment"
~~~

Với mỗi trường hợp, test cần ghi rõ token hoặc lỗi mong đợi theo đặc tả. Ví dụ RULES phải là identifier; 2rule có thể là INTEGER_LITERAL theo sau bởi IDENTIFIER hoặc lexical error nếu DSL cấm dính số với tên; 12. và .5 bị từ chối theo quy tắc decimal nêu trên; chuỗi chưa đóng tạo diagnostic; ký hiệu comment trong string được giữ nguyên.

## Tổ chức test suite và bảo trì

Một bộ test lexer dễ bảo trì thường được chia theo nhóm quy tắc, thay vì một tệp lớn chứa mọi trường hợp.

Cấu trúc minh họa:

~~~text
lexer-tests/
  keywords/
  identifiers/
  numeric-literals/
  string-literals/
  operators/
  delimiters/
  whitespace-comments/
  source-spans/
  invalid-input/
  unicode/
  incremental/
  regression/
~~~

Mỗi fixture nên có tên thể hiện hành vi, chẳng hạn:

- keyword-boundary-rules
- identifier-start-digit
- operator-maximal-munch
- decimal-missing-fraction
- string-escaped-quote
- comment-marker-inside-string
- crlf-line-column
- invalid-character-recovery

Nếu dùng fixture file, có thể lưu nguồn và kết quả mong đợi cạnh nhau. Nếu dùng code, table-driven tests thường phù hợp cho các biến thể ngắn. Với trường hợp Unicode hoặc newline đặc biệt, cần kiểm soát encoding của fixture để tránh editor tự thay đổi nội dung.

Khi quy tắc từ vựng thay đổi, cần cập nhật đặc tả, test và thông tin cho parser cùng lúc. Ví dụ, thêm toán tử ** không chỉ cần test lexer nhận một token mới; parser cũng cần biết precedence và ngữ nghĩa của toán tử. Phần kiểm thử lexer xác nhận token, còn các tầng khác có trách nhiệm xác nhận ý nghĩa.

## Nguyên tắc thiết kế một bộ kiểm thử lexer hiệu quả

Một số nguyên tắc giúp bộ test có giá trị lâu dài:

1. **Bám sát đặc tả:** mỗi test phải có lý do rõ ràng và kết quả mong đợi xác định.
2. **Kiểm tra cả hợp lệ lẫn không hợp lệ:** lexer cần nhận đúng token và từ chối đúng dạng sai.
3. **Tập trung vào ranh giới:** tiền tố chung, token dài/ngắn, keyword/identifier và literal/đơn vị thường chứa nhiều lỗi.
4. **Kiểm tra vị trí nguồn:** token đúng nhưng span sai vẫn gây lỗi nghiêm trọng cho IDE và diagnostics.
5. **Phân biệt lexical với syntax error:** tránh để test lexer phụ thuộc parser khi không cần thiết.
6. **Giữ test hồi quy:** mọi lỗi đã sửa cần có ví dụ tái hiện.
7. **Bổ sung property-based và fuzzing:** dùng chúng để khám phá đầu vào ngoài tập ví dụ thủ công.
8. **Kiểm soát thời gian và bộ nhớ:** xác nhận lexer tiến triển và xử lý đầu vào lớn có giới hạn.
9. **Kiểm thử Unicode và encoding:** không giả định mọi nguồn đều là ASCII.
10. **So sánh incremental với full lexing:** bảo đảm kết quả IDE nhất quán với kết quả phân tích toàn bộ.
11. **Tránh assertion quá mong manh:** kiểm tra cấu trúc token và mã lỗi ổn định, không phụ thuộc chuỗi debug dễ thay đổi.
12. **Cập nhật test cùng đặc tả:** thay đổi token phải được phản ánh trong tài liệu và các tầng frontend liên quan.

## Kết luận

Kiểm thử quy tắc lexer xác nhận rằng văn bản nguồn DSL được chuyển thành token stream theo đúng đặc tả từ vựng. Bộ test cần bao phủ nhận diện token, khớp dài nhất, ưu tiên keyword, identifier, literal số và chuỗi, toán tử, whitespace, comment, Unicode, source span và lỗi lexical.

Một chiến lược đầy đủ kết hợp unit test theo quy tắc, boundary test, golden test, property-based test, fuzzing, regression test và một số integration test với parser. Khi kiểm tra cả token kind, giá trị, vị trí và khả năng phục hồi, nhóm phát triển có thể phát hiện sớm lỗi ở lớp từ vựng và giữ frontend DSL ổn định khi ngôn ngữ được mở rộng.

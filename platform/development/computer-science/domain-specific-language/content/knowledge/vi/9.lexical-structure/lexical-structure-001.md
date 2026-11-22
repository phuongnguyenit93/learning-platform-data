# Token và lexeme trong phân tích từ vựng của DSL

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Giải thích vai trò của phân tích từ vựng (lexical analysis) trong pipeline xử lý một ngôn ngữ chuyên biệt miền (DSL).
- Phân biệt token, loại token (token kind), lexeme, pattern và giá trị thuộc tính của token.
- Đọc một đoạn DSL và xác định chuỗi ký tự nào tạo thành token nào.
- Giải thích cách lexer xử lý từ khóa, định danh, số, chuỗi, toán tử, dấu phân cách, khoảng trắng và chú thích.
- Hiểu các quy tắc chọn token như khớp dài nhất, thứ tự ưu tiên và xử lý từ khóa.
- Nhận biết ranh giới giữa lỗi từ vựng, lỗi cú pháp và lỗi ngữ nghĩa.
- Thiết kế và kiểm thử một lexer cơ bản cho DSL.

## 1. Vị trí của token và lexeme trong pipeline DSL

Một DSL thường được viết dưới dạng văn bản hoặc được nhập từ một tệp cấu hình. Trước khi công cụ có thể hiểu ý nghĩa của biểu thức, nó phải chia chuỗi ký tự thành những đơn vị nhỏ có ý nghĩa đối với ngôn ngữ. Công việc đó thuộc về **phân tích từ vựng** (lexical analysis).

Ví dụ, một quy tắc DSL giả định có thể được viết như sau:

~~~text
rule "free_shipping" {
    when order.total >= 500000
    then order.shipping_fee = 0
}
~~~

Người đọc nhìn thấy từ khóa, tên trường, toán tử, số, chuỗi và dấu ngoặc. Lexer cũng cần nhận diện các đơn vị đó để bước tiếp theo có thể phân tích cấu trúc câu lệnh.

Pipeline điển hình:

~~~text
Văn bản nguồn
     |
     v
Phân tích từ vựng (Lexer)
     |
     v
Dãy token
     |
     v
Phân tích cú pháp (Parser)
     |
     v
Cây cú pháp (AST)
     |
     v
Phân giải tên và kiểm tra ngữ nghĩa
     |
     v
Diễn giải / sinh mã / thực thi
~~~

Lexer xử lý chuỗi ký tự và tạo ra token. Parser nhận dãy token để xác định cách chúng kết hợp thành biểu thức, câu lệnh hoặc cấu trúc lớn hơn. Các bước sau mới xác định tên tham chiếu đến đối tượng nào, kiểu dữ liệu có phù hợp không và quy tắc miền có hợp lệ không.

Ví dụ, lexer có thể nhận diện từ order là một định danh. Parser có thể nhận diện order.total là một biểu thức truy cập thuộc tính. Bộ phân giải tên mới kiểm tra order có được khai báo trong ngữ cảnh hiện tại hay không và có trường total hay không.

## 2. Token, lexeme, token kind và pattern

Các thuật ngữ này liên quan chặt chẽ nhưng không đồng nghĩa. Phân biệt chúng giúp đọc đặc tả lexer và hiểu dữ liệu mà lexer trả về.

### 2.1. Lexeme là chuỗi ký tự thực tế trong mã nguồn

**Lexeme** là đoạn ký tự liên tiếp trong văn bản nguồn được lexer nhận diện như một đơn vị từ vựng. Nó là phần văn bản cụ thể xuất hiện trong chương trình.

Trong biểu thức:

~~~text
order.total >= 500000
~~~

Các lexeme có thể là order, ., total, >= và 500000. Lexeme giữ cách viết thực tế của nguồn. Nếu người viết đổi 500000 thành 500_000 trong một DSL cho phép dấu gạch dưới phân nhóm chữ số, lexeme thay đổi dù giá trị số mà chương trình muốn biểu diễn có thể vẫn là 500000.

### 2.2. Token là đơn vị từ vựng mà lexer tạo ra

**Token** là đơn vị đầu ra của lexer, đại diện cho một thành phần có ý nghĩa từ vựng. Một token thường có ít nhất một loại token và có thể mang thêm lexeme, giá trị đã chuyển đổi và vị trí trong nguồn.

Ví dụ, lexeme order được phân loại thành token loại IDENTIFIER; lexeme >= được phân loại thành token loại GREATER_EQUAL; lexeme 500000 được phân loại thành token loại INTEGER.

Trong nhiều tài liệu, từ token được dùng theo hai cách:

1. Chỉ **loại token** (token kind), chẳng hạn IDENTIFIER, INTEGER hoặc PLUS.
2. Chỉ **một đối tượng token cụ thể** trong dãy đầu ra, có loại, lexeme, giá trị và vị trí.

Khi đọc đặc tả hoặc API, cần xem ngữ cảnh để biết tác giả đang dùng nghĩa nào. Trong bài này, token object là một phần tử cụ thể; token kind là phân loại của phần tử đó.

### 2.3. Pattern mô tả lexeme hợp lệ

**Pattern** là quy tắc mô tả những chuỗi ký tự có thể được nhận diện thành một loại token. Pattern thường được biểu diễn bằng biểu thức chính quy (regular expression), grammar từ vựng hoặc mã nhận diện chuyên biệt.

Ví dụ:

| Token kind | Pattern minh họa | Lexeme ví dụ |
|---|---|---|
| IDENTIFIER | Chữ cái hoặc dấu gạch dưới, sau đó là chữ, số hoặc dấu gạch dưới | order, customer_id |
| INTEGER | Một hoặc nhiều chữ số | 0, 42, 500000 |
| DECIMAL | Chữ số, dấu chấm, chữ số | 3.14, 0.5 |
| STRING | Chuỗi nằm trong dấu nháy theo quy tắc escape | "hello", "free shipping" |
| PLUS | Dấu cộng | + |
| GREATER_EQUAL | Dấu lớn hơn theo sau bởi dấu bằng | >= |
| LEFT_BRACE | Dấu ngoặc nhọn mở | { |

Pattern mô tả hình dạng của lexeme, không nhất thiết mô tả toàn bộ ý nghĩa của nó. Pattern số có thể nhận diện một chuỗi rất lớn, nhưng kiểu số đích hoặc giới hạn nghiệp vụ có thể không cho phép giá trị đó.

### 2.4. Giá trị thuộc tính của token

Lexeme và giá trị (value) có thể khác nhau. Với số và chuỗi, lexer thường chuyển phần văn bản thành giá trị có kiểu để các bước sau sử dụng.

| Lexeme | Token kind | Giá trị có thể lưu |
|---|---|---|
| 0042 | INTEGER | Số nguyên 42, nếu DSL cho phép số 0 ở đầu |
| "hello" | STRING | Chuỗi hello, không bao gồm dấu nháy |
| "\\n" | STRING | Một ký tự xuống dòng sau khi xử lý escape |
| >= | GREATER_EQUAL | Thường không cần giá trị riêng |
| customerId | IDENTIFIER | Tên định danh customerId |

Không phải lexer nào cũng chuyển đổi giá trị ngay. Một số lexer chỉ lưu lexeme và vị trí; parser hoặc bước xử lý sau mới chuyển đổi. Điều quan trọng là đặc tả phải nhất quán về nơi xử lý escape, dấu phân nhóm số và chuyển đổi literal.

### 2.5. Bảng phân biệt nhanh

| Khái niệm | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Lexeme | Đoạn ký tự nào xuất hiện trong nguồn? | >= |
| Token kind | Đoạn đó thuộc loại từ vựng nào? | GREATER_EQUAL |
| Token object | Lexer tạo ra phần tử nào với thông tin gì? | GREATER_EQUAL, lexeme >=, vị trí dòng 2 cột 17 |
| Pattern | Chuỗi nào được phép thuộc loại này? | > theo sau bởi = |
| Giá trị | Literal biểu diễn dữ liệu gì? | 42 hoặc chuỗi đã giải mã |

## 3. Ví dụ chuyển văn bản thành dãy token

Xét biểu thức:

~~~text
order.total >= 500000
~~~

Một lexer có thể tạo ra dãy token:

| Thứ tự | Lexeme | Token kind | Giá trị hoặc thông tin |
|---:|---|---|---|
| 1 | order | IDENTIFIER | Tên order |
| 2 | . | DOT | Không có |
| 3 | total | IDENTIFIER | Tên total |
| 4 | >= | GREATER_EQUAL | Không có |
| 5 | 500000 | INTEGER | Số nguyên 500000 |
| 6 | EOF | END_OF_FILE | Vị trí kết thúc nguồn |

Khoảng trắng giữa các lexeme thường bị bỏ qua trong DSL này. Lexer vẫn phải đọc chúng để xác định ranh giới, nhưng không nhất thiết tạo token WHITESPACE.

Với cả quy tắc đầy đủ:

~~~text
rule "free_shipping" {
    when order.total >= 500000
    then order.shipping_fee = 0
}
~~~

Dãy token có thể được biểu diễn rút gọn:

~~~text
RULE
STRING("free_shipping")
LEFT_BRACE
WHEN
IDENTIFIER("order")
DOT
IDENTIFIER("total")
GREATER_EQUAL
INTEGER(500000)
THEN
IDENTIFIER("order")
DOT
IDENTIFIER("shipping_fee")
EQUAL
INTEGER(0)
RIGHT_BRACE
EOF
~~~

Các tên token cụ thể phụ thuộc vào thiết kế DSL. Có DSL dùng từ khóa THEN; DSL khác có thể dùng dấu mũi tên. Lexer không tự quyết định ngữ pháp câu lệnh; nó chỉ tạo ra những loại token được đặc tả.

## 4. Lexer hoạt động như thế nào?

Lexer thường đọc nguồn từ trái sang phải, giữ vị trí hiện tại và thử nhận diện lexeme tiếp theo. Ở mỗi bước, nó:

1. Bỏ qua hoặc lưu lại khoảng trắng và chú thích theo quy tắc.
2. Xác định ký tự đầu tiên có thể bắt đầu loại token nào.
3. Đọc thêm ký tự cho đến khi đạt ranh giới của lexeme.
4. Chọn token theo quy tắc ưu tiên và khớp dài nhất.
5. Tạo token object với loại, lexeme, giá trị và vị trí.
6. Tiếp tục cho đến cuối nguồn hoặc gặp lỗi không thể khôi phục.

Một lexer có thể được triển khai bằng các nhánh điều kiện, bảng chuyển trạng thái, biểu thức chính quy, máy trạng thái hữu hạn (finite-state machine) hoặc thư viện sinh lexer từ grammar.

### 4.1. Nhận diện theo ký tự đầu

Với một DSL nhỏ, lexer có thể kiểm tra ký tự hiện tại:

- Chữ cái hoặc dấu gạch dưới: có thể bắt đầu định danh hoặc từ khóa.
- Chữ số: có thể bắt đầu literal số.
- Dấu nháy: bắt đầu literal chuỗi.
- Dấu cộng, trừ, bằng hoặc so sánh: bắt đầu toán tử.
- Dấu ngoặc, dấu phẩy, dấu chấm phẩy: dấu phân cách hoặc nhóm.
- Ký tự không thuộc tập hợp hợp lệ: lỗi từ vựng.

Cách phân nhánh này đơn giản, nhưng mỗi nhánh vẫn phải xử lý đầy đủ quy tắc kết thúc lexeme, escape và các trường hợp nhập nhằng.

### 4.2. Khớp dài nhất (maximal munch)

Khi nhiều token có thể bắt đầu bằng cùng một chuỗi, lexer thường chọn lexeme dài nhất có thể khớp. Quy tắc này thường được gọi là maximal munch hoặc longest match.

Ví dụ, DSL có các toán tử >, >=, = và ==. Khi nguồn chứa >=, lexer nên tạo một token GREATER_EQUAL thay vì hai token GREATER và EQUAL. Tương tự, == nên được nhận diện như một token riêng nếu ngôn ngữ định nghĩa toán tử bằng nhau kép.

Nếu lexer luôn chọn token ngắn nhất đầu tiên, nó có thể tách một toán tử hợp lệ thành các mảnh sai. Vì vậy, cách triển khai thường thử các toán tử dài trước hoặc dùng cơ chế tự động bảo đảm khớp dài nhất.

### 4.3. Thứ tự ưu tiên khi nhiều pattern cùng khớp

Khớp dài nhất không giải quyết mọi trường hợp. Hai loại token có thể khớp cùng một lexeme với cùng độ dài. Khi đó, lexer cần quy tắc ưu tiên.

Ví dụ, chuỗi if có thể khớp pattern IDENTIFIER và cũng là từ khóa IF. DSL thường ưu tiên nhận diện từ khóa trước hoặc nhận diện định danh rồi tra bảng từ khóa.

Một từ như iffy cần là IDENTIFIER, không phải IF theo sau bởi IDENTIFIER fy. Do đó, việc nhận diện từ khóa phải kiểm tra toàn bộ lexeme và ranh giới, không chỉ so khớp tiền tố.

### 4.4. Ví dụ về từ khóa và định danh

Giả sử DSL có các từ khóa rule, when, then và true. Các tên order, orderTotal và thenValue là định danh.

Một cách triển khai phổ biến:

1. Lexer nhận diện chuỗi theo pattern định danh.
2. Sau khi thu được lexeme, lexer tra bảng từ khóa.
3. Nếu lexeme trùng một từ khóa được định nghĩa, tạo token loại tương ứng.
4. Nếu không trùng, tạo IDENTIFIER.

| Lexeme | Token kind |
|---|---|
| rule | RULE |
| when | WHEN |
| then | THEN |
| true | TRUE |
| order | IDENTIFIER |
| thenValue | IDENTIFIER |
| ruleName | IDENTIFIER |

Cách này giúp pattern định danh đơn giản và giảm lỗi do từ khóa chỉ là tiền tố của tên dài hơn.

## 5. Các nhóm token thường gặp trong DSL

Một DSL không cần tất cả các nhóm dưới đây, nhưng chúng là những loại thường xuất hiện.

### 5.1. Từ khóa (keywords)

Từ khóa có ý nghĩa cố định trong cú pháp DSL, chẳng hạn rule, when, then, and, or, not, true, false hoặc null.

Từ khóa thường không được dùng như định danh thông thường, trừ khi DSL hỗ trợ cơ chế escape hoặc tên có trích dẫn. Danh sách từ khóa là một phần của đặc tả ngôn ngữ và cần được quản lý cẩn thận vì thêm từ khóa có thể làm mã cũ đổi cách phân tích.

### 5.2. Định danh (identifiers)

Định danh là tên do người viết đặt cho biến, trường, kiểu, hàm, quy tắc hoặc tài nguyên. Ví dụ: order, customerId, shipping_fee.

Đặc tả định danh cần quy định:

- Ký tự nào được phép ở đầu và ở các vị trí tiếp theo.
- Có phân biệt chữ hoa và chữ thường không.
- Có cho phép Unicode hoặc dấu tiếng Việt không.
- Có cho phép dấu gạch dưới hoặc chữ số không.
- Có giới hạn độ dài không.
- Từ khóa có thể được dùng làm tên bằng cách escape hay không.

Không nên giả định mọi DSL đều chỉ cho phép ASCII. Nếu cho phép Unicode, cần quy định chuẩn hóa ký tự và cách so sánh để tránh hai chuỗi nhìn giống nhau nhưng có biểu diễn mã khác nhau.

### 5.3. Literal số

Literal số biểu diễn giá trị số được viết trực tiếp trong nguồn. DSL có thể hỗ trợ:

- Số nguyên: 0, 42, 500000.
- Số thực: 3.14, 0.5.
- Số có dấu phân nhóm: 500_000 nếu được cho phép.
- Số mũ: 1.2e3 nếu miền cần.
- Hậu tố đơn vị: 15%, 10ms, 5kg nếu DSL định nghĩa rõ.

Lexer cần quy định dấu chấm thập phân, dấu phân nhóm, dấu mũ, dấu cộng/trừ và hậu tố. Không nên để cùng một ký tự vừa là dấu phân nhóm vừa là dấu thập phân mà không có quy ước rõ ràng.

Thông thường, dấu trừ được nhận diện thành token MINUS riêng; parser quyết định nó là toán tử trừ nhị phân hay dấu âm một ngôi. Một DSL có thể chọn gộp dấu vào literal số, nhưng phải đặc tả nhất quán vì lựa chọn này ảnh hưởng cách phân tích biểu thức.

### 5.4. Literal chuỗi

Literal chuỗi thường nằm giữa dấu nháy đơn hoặc kép. Lexer cần xác định:

- Loại dấu nháy được hỗ trợ.
- Ký tự escape như dấu nháy, dấu gạch chéo ngược, xuống dòng và tab.
- Chuỗi nhiều dòng có hợp lệ không.
- Cách xử lý Unicode.
- Nội suy biến hoặc biểu thức có được hỗ trợ không.
- Cách báo lỗi khi chuỗi chưa đóng hoặc escape không hợp lệ.

Lexeme của chuỗi có thể bao gồm cả dấu nháy, trong khi giá trị chuỗi đã giải mã thì không. Ví dụ, lexeme chứa ký hiệu escape n có thể tạo giá trị gồm hai dòng nếu DSL định nghĩa escape đó là ký tự xuống dòng.

### 5.5. Toán tử

Toán tử là các ký hiệu hoặc từ khóa biểu diễn thao tác. Ví dụ:

| Lexeme | Token kind có thể dùng | Ý nghĩa thường gặp |
|---|---|---|
| + | PLUS | Cộng |
| - | MINUS | Trừ hoặc âm một ngôi |
| * | STAR | Nhân |
| / | SLASH | Chia |
| = | EQUAL | Gán hoặc so sánh tùy ngữ cảnh |
| == | EQUAL_EQUAL | So sánh bằng |
| != | NOT_EQUAL | Khác |
| > | GREATER | Lớn hơn |
| >= | GREATER_EQUAL | Lớn hơn hoặc bằng |
| && | AND_AND | Logic AND |
| || | OR_OR | Logic OR |

Một số DSL dùng từ khóa and, or, not thay cho ký hiệu. Lexer cần tạo token riêng cho từng toán tử; parser và bước kiểm tra kiểu xác định toán tử đó áp dụng được cho kiểu nào.

### 5.6. Dấu phân cách và dấu nhóm

Các token này giúp phân chia cấu trúc:

- Ngoặc đơn: ( và ).
- Ngoặc vuông: [ và ].
- Ngoặc nhọn: { và }.
- Dấu phẩy: ,
- Dấu chấm: .
- Dấu hai chấm: :
- Dấu chấm phẩy: ;

Lexer nhận diện từng dấu. Parser quyết định chúng mở nhóm, kết thúc danh sách, phân cách tham số hay biểu diễn truy cập thuộc tính.

### 5.7. Khoảng trắng và xuống dòng

Khoảng trắng có thể chỉ dùng để phân tách token, hoặc có thể mang ý nghĩa cú pháp. Trong nhiều DSL, dấu cách và tab bị bỏ qua giữa các token; xuống dòng cũng bị bỏ qua trừ khi nó kết thúc câu lệnh.

Một DSL dựa trên thụt lề có thể cần lexer tạo token INDENT và DEDENT khi mức thụt lề thay đổi. Một DSL cấu hình theo dòng có thể tạo token NEWLINE để parser nhận biết ranh giới câu lệnh.

Không nên xóa mọi khoảng trắng ngay từ đầu nếu chúng còn cần cho chuỗi, thông báo lỗi, định dạng lại mã hoặc cú pháp thụt lề.

### 5.8. Chú thích (comments)

Chú thích thường dành cho con người và không ảnh hưởng đến ý nghĩa thực thi. Ví dụ:

~~~text
# Miễn phí vận chuyển cho đơn lớn
when order.total >= 500000 then order.shipping_fee = 0
~~~

Lexer có thể bỏ qua chú thích, nhưng vẫn cần cập nhật vị trí dòng và cột. Một số công cụ giữ chú thích như trivia để hỗ trợ formatter, tài liệu tự động hoặc chỉnh sửa mã mà không làm mất nội dung của người viết.

### 5.9. Token kết thúc tệp

Nhiều lexer tạo token EOF (end of file) khi đã đọc hết nguồn. EOF giúp parser biết không còn token nào và có thể báo lỗi nếu cấu trúc còn dang dở, chẳng hạn ngoặc mở chưa được đóng.

EOF không phải lexeme được người viết gõ vào. Nó là tín hiệu do lexer tạo ra tại vị trí kết thúc nguồn.

## 6. Khoảng trắng, chú thích và trivia

Trong nhiều triển khai, lexer bỏ qua khoảng trắng và chú thích vì parser không cần chúng để hiểu cấu trúc. Tuy nhiên, một công cụ DSL có thể cần giữ lại thông tin này.

Các thành phần không ảnh hưởng đến ngữ nghĩa nhưng hữu ích cho công cụ thường được gọi là **trivia**. Ví dụ:

- Khoảng trắng giữa hai token.
- Dòng trống.
- Chú thích một dòng hoặc nhiều dòng.
- Ký tự xuống dòng và thụt lề.

Có hai chiến lược phổ biến:

1. **Bỏ qua trivia:** lexer không đưa chúng vào dãy token, nhưng vẫn cập nhật vị trí nguồn.
2. **Giữ trivia:** lexer gắn trivia vào token trước hoặc sau, hoặc lưu thành luồng phụ để formatter và IDE dùng.

Nếu DSL chỉ dùng để thực thi cấu hình, bỏ qua khoảng trắng và chú thích có thể đủ. Nếu DSL có trình soạn thảo, formatter, refactoring hoặc yêu cầu giữ nguyên định dạng, giữ trivia sẽ hữu ích hơn.

## 7. Vị trí nguồn của token

Một token nên mang thông tin vị trí để công cụ chỉ ra lỗi tại nơi người viết có thể sửa. Thông tin thường gồm:

- Tệp nguồn hoặc tên tài liệu.
- Offset bắt đầu và kết thúc trong chuỗi.
- Dòng bắt đầu và cột bắt đầu.
- Dòng kết thúc và cột kết thúc, nếu cần.

Ví dụ token GREATER_EQUAL có thể lưu:

~~~text
kind: GREATER_EQUAL
lexeme: >=
start: line 4, column 22
end: line 4, column 24
~~~

Quy ước cột cần được xác định. Một số công cụ đếm byte UTF-8, một số đếm code point Unicode, một số đếm UTF-16 code unit. Nếu editor và compiler dùng quy ước khác nhau, vị trí gạch chân lỗi có thể lệch khi nguồn chứa ký tự Unicode.

Nên lưu offset nguồn ổn định và chuyển đổi sang định dạng dòng/cột mà giao diện cần. Với ngôn ngữ hỗ trợ tab hoặc ký tự rộng, cần quy định cách tính cột hiển thị.

## 8. Lỗi từ vựng và cách xử lý

Lỗi từ vựng xảy ra khi lexer gặp một chuỗi ký tự không thể tạo thành token hợp lệ theo đặc tả.

Ví dụ:

- Ký tự @ không được DSL hỗ trợ.
- Chuỗi mở bằng dấu nháy nhưng không có dấu đóng.
- Escape sequence không hợp lệ.
- Literal số sai định dạng.
- Định danh bắt đầu bằng ký tự không được phép.
- Comment nhiều dòng không có dấu kết thúc.

Lỗi từ vựng khác lỗi cú pháp. Với lỗi từ vựng, lexer không thể phân loại một phần nguồn thành token hợp lệ. Với lỗi cú pháp, lexer đã tạo token nhưng parser không thể kết hợp chúng theo grammar.

### 8.1. Ví dụ phân biệt lỗi

Giả sử DSL cho phép câu lệnh:

~~~text
set order.total = 100
~~~

Các trường hợp:

| Nguồn | Lớp lỗi | Giải thích |
|---|---|---|
| set order.total = 100 | Không lỗi từ vựng | Tất cả lexeme đều có token tương ứng |
| set order.total = @ | Lỗi từ vựng nếu @ không được hỗ trợ | Không nhận diện được ký tự @ |
| set order.total = | Lỗi cú pháp | Token hợp lệ nhưng thiếu biểu thức sau dấu bằng |
| set unknown.total = 100 | Có thể là lỗi phân giải tên | Cú pháp hợp lệ nhưng unknown không tồn tại trong ngữ cảnh |
| set order.total = "many" | Có thể là lỗi kiểu | Chuỗi không tương thích kiểu trường total |

### 8.2. Thông báo lỗi hữu ích

Thông báo lỗi từ vựng nên chỉ ra:

- Tên tệp hoặc nguồn.
- Dòng và cột.
- Lexeme hoặc ký tự gây lỗi.
- Quy tắc mong đợi ở vị trí đó.
- Cách sửa khả thi nếu có thể xác định.

Ví dụ:

~~~text
Lexical error at rules.dsl:8:19
Unexpected character '@'.
Expected an identifier, number, string, or operator.
~~~

Với chuỗi chưa đóng:

~~~text
Unterminated string literal at rules.dsl:12:7.
The string starts here and reaches the end of the line without a closing quote.
~~~

### 8.3. Khôi phục sau lỗi

Một lexer có thể dừng ngay khi gặp lỗi đầu tiên, hoặc ghi nhận lỗi và tiếp tục từ một vị trí có thể xác định. Với trình soạn thảo tương tác, tiếp tục phân tích thường hữu ích vì người dùng muốn thấy nhiều lỗi cùng lúc.

Khôi phục cần được thiết kế thận trọng. Lexer có thể bỏ qua ký tự không hợp lệ rồi tìm token tiếp theo, nhưng việc bỏ qua quá nhiều có thể tạo ra dãy token gây hiểu nhầm và dẫn đến lỗi dây chuyền ở parser.

Đối với công cụ chạy cấu hình quan trọng, có thể yêu cầu không thực thi khi còn lỗi từ vựng hoặc cú pháp. Với IDE, công cụ có thể tạo token lỗi để giữ cấu trúc phần còn lại và tiếp tục cung cấp gợi ý.

## 9. Ranh giới giữa lexer và parser

Lexer và parser phối hợp với nhau nhưng giải quyết hai vấn đề khác nhau.

| Nội dung | Lexer | Parser |
|---|---|---|
| Đầu vào | Chuỗi ký tự | Dãy token |
| Đầu ra | Token | Cây cú pháp hoặc cấu trúc cú pháp |
| Quan tâm | Lexeme có hình dạng hợp lệ không? | Token có kết hợp theo grammar không? |
| Ví dụ | Nhận >= thành GREATER_EQUAL | Xác định phép so sánh nằm trong biểu thức điều kiện |
| Lỗi | Ký tự lạ, chuỗi chưa đóng, số sai định dạng | Thiếu toán hạng, ngoặc không cân bằng, sai thứ tự token |

Ví dụ, lexer nhận biểu thức thành:

~~~text
IDENTIFIER DOT IDENTIFIER GREATER_EQUAL INTEGER
~~~

Parser có thể dùng grammar:

~~~text
comparison  ::= expression comparator expression
comparator  ::= GREATER | GREATER_EQUAL | LESS | LESS_EQUAL
expression  ::= propertyAccess | literal
propertyAccess ::= IDENTIFIER DOT IDENTIFIER
literal     ::= INTEGER | STRING | TRUE | FALSE
~~~

Grammar này minh họa cách parser nhận diện một phép so sánh. Nó chưa kiểm tra order có tồn tại hay total có kiểu số hay không; những việc đó thuộc phân giải tên và kiểm tra ngữ nghĩa.

### 9.1. Không đưa mọi quy tắc vào lexer

Lexer nên tập trung nhận diện đơn vị từ vựng. Không nên để lexer tự quyết định những vấn đề cần cấu trúc hoặc ngữ cảnh sâu hơn.

Ví dụ:

- Lexer nhận diện dấu trừ thành MINUS; parser xác định nó là trừ nhị phân hay âm một ngôi.
- Lexer nhận diện IDENTIFIER; bộ phân giải tên xác định định danh đó có được khai báo hay không.
- Lexer nhận diện INTEGER; bộ kiểm tra kiểu hoặc runtime xác định giá trị có phù hợp kiểu đích hoặc giới hạn miền không.
- Lexer nhận diện từ khóa; parser xác định vị trí cú pháp mà từ khóa đó được phép xuất hiện.

Một số DSL có thể dùng lexer theo ngữ cảnh hoặc nhiều chế độ từ vựng, nhưng đó là quyết định thiết kế có chủ đích và cần được mô tả rõ.

## 10. Lexer theo ngữ cảnh và chế độ từ vựng

Không phải mọi ngôn ngữ đều có thể nhận diện token bằng một bộ quy tắc duy nhất. Một số DSL cho phép nhúng biểu thức, chuỗi mẫu hoặc đoạn mã của ngôn ngữ khác.

Ví dụ, một DSL mẫu có thể cho phép nội suy biểu thức trong một chuỗi. Phần ngoài vùng nội suy là văn bản; phần bên trong dấu phân cách lại cần phân tích như biểu thức DSL. Lexer có thể chuyển qua lại giữa các chế độ:

- Chế độ văn bản.
- Chế độ chuỗi.
- Chế độ biểu thức nội suy.
- Chế độ mã hoặc truy vấn nhúng.

Mỗi chế độ có thể có quy tắc token khác nhau. Lexer cần biết khi nào vào chế độ mới và khi nào quay lại chế độ trước.

Một số DSL dùng từ khóa theo ngữ cảnh (contextual keywords). Chẳng hạn, từ match chỉ là từ khóa trong một cấu trúc pattern matching, nhưng có thể được dùng làm định danh ở ngữ cảnh khác. Khi đó, lexer có thể phát token IDENTIFIER và parser diễn giải theo vị trí, hoặc lexer được cung cấp trạng thái từ parser.

Lexer theo ngữ cảnh làm tăng độ phức tạp. Chỉ nên dùng khi cú pháp thực sự cần và cần có kiểm thử cho mọi điểm chuyển chế độ.

## 11. Từ vựng và Unicode

Nếu DSL cho phép người dùng dùng tiếng Việt hoặc các ngôn ngữ khác trong định danh và chuỗi, lexer cần quy định rõ cách xử lý Unicode.

Những câu hỏi quan trọng:

- Định danh có được bắt đầu bằng chữ cái Unicode không?
- Có cho phép dấu tiếng Việt trong tên biến hoặc trường không?
- Có phân biệt chữ hoa và chữ thường không?
- Có chuẩn hóa Unicode trước khi so sánh không?
- Ký tự kết hợp dấu được xử lý như thế nào?
- Thông báo lỗi hiển thị vị trí theo byte, code point hay đơn vị UTF-16?

Hai chuỗi nhìn giống nhau có thể có cách biểu diễn Unicode khác nhau: một ký tự có dấu có thể là một code point dựng sẵn hoặc chữ cái đi kèm dấu kết hợp. Nếu DSL dùng tên Unicode, nên quy định chuẩn hóa, chẳng hạn NFC, tại thời điểm xử lý định danh.

Đối với chuỗi nội dung, việc chuẩn hóa cần được cân nhắc theo mục đích. Không nên tự động thay đổi nội dung chuỗi nếu ngữ nghĩa yêu cầu giữ nguyên chính xác dữ liệu người dùng nhập.

## 12. Thiết kế pattern cho token

Một đặc tả từ vựng tốt cần cân bằng giữa tính rõ ràng, khả năng mở rộng và sự dễ đoán.

### 12.1. Ví dụ grammar từ vựng đơn giản

~~~text
IDENTIFIER  := [A-Za-z_][A-Za-z0-9_]*
INTEGER     := [0-9]+
DECIMAL     := [0-9]+ "." [0-9]+
WHITESPACE  := [ \t\r\n]+
STRING      := '"' (escaped-char | non-quote-char)* '"'
~~~

Đây là cách viết minh họa gần với regex, không phải cú pháp chuẩn của mọi công cụ lexer. Đặc tả thực tế phải quyết định dấu escape, newline, Unicode và xung đột giữa INTEGER với DECIMAL.

### 12.2. Tránh pattern chồng lấn không có quy tắc

Giả sử INTEGER là một hoặc nhiều chữ số và DECIMAL là chữ số, dấu chấm, chữ số. Chuỗi 12.5 có thể bắt đầu bằng INTEGER 12 rồi gặp dấu chấm nếu lexer chọn INTEGER quá sớm. Cơ chế khớp dài nhất hoặc quy tắc ưu tiên cần đảm bảo cả 12.5 được nhận diện thành DECIMAL.

Tương tự, nếu DSL có toán tử > và >=, cần ưu tiên token dài hơn. Nếu có từ khóa và định danh, cần xác định cách tra bảng từ khóa sau khi nhận diện toàn bộ định danh.

### 12.3. Literal có hậu tố đơn vị

Một DSL miền vật lý hoặc tài chính có thể hỗ trợ literal mang đơn vị:

~~~text
timeout = 250ms
distance = 12km
discount = 15%
~~~

Có hai cách phổ biến:

1. Lexer tạo NUMBER rồi tạo token đơn vị riêng, ví dụ INTEGER(250), IDENTIFIER(ms).
2. Lexer nhận cả chuỗi thành một token literal có hậu tố, ví dụ DURATION(250, ms).

Cách thứ hai thuận tiện nếu hậu tố là một phần cố định của literal. Cách thứ nhất linh hoạt hơn nếu đơn vị có thể là tên do người dùng định nghĩa. Dù chọn cách nào, việc chuyển đổi đơn vị và kiểm tra tương thích thường cần xử lý ở bước ngữ nghĩa hoặc kiểu.

### 12.4. Dấu âm và số âm

Có thể định nghĩa -12 thành một token số âm, hoặc hai token MINUS và INTEGER(12). Cách tách riêng thường giúp parser xử lý nhất quán toán tử một ngôi và nhị phân:

~~~text
a - 12
-12
~~~

Trong cả hai trường hợp, lexer có thể tạo MINUS và INTEGER(12). Parser dựa vào vị trí để quyết định dấu trừ là phép trừ hay dấu âm.

## 13. Cấu trúc dữ liệu token

Một token object có thể được mô hình hóa như sau:

~~~text
Token {
    kind: TokenKind
    lexeme: String
    literalValue: Optional<Value>
    startOffset: Integer
    endOffset: Integer
    startLine: Integer
    startColumn: Integer
}
~~~

Trong một số triển khai, token không giữ lexeme mà chỉ giữ offset vào nguồn. Cách đó giảm sao chép chuỗi, nhưng yêu cầu nguồn gốc phải còn tồn tại trong thời gian token được dùng.

Ví dụ:

~~~json
{
  "kind": "INTEGER",
  "lexeme": "500000",
  "literalValue": 500000,
  "startLine": 2,
  "startColumn": 24,
  "endLine": 2,
  "endColumn": 30
}
~~~

JSON trên chỉ minh họa một cách biểu diễn. API thực tế có thể dùng enum, class, record hoặc tagged union.

### 13.1. Token kind thường được biểu diễn bằng enum

Ví dụ danh sách loại token:

~~~text
RULE
WHEN
THEN
IDENTIFIER
INTEGER
DECIMAL
STRING
TRUE
FALSE
PLUS
MINUS
STAR
SLASH
EQUAL
EQUAL_EQUAL
GREATER
GREATER_EQUAL
LEFT_PAREN
RIGHT_PAREN
LEFT_BRACE
RIGHT_BRACE
COMMA
DOT
EOF
~~~

Enum giúp parser xử lý loại token rõ ràng. Khi thêm token mới, cần cập nhật grammar, parser, formatter, thông báo lỗi và kiểm thử có liên quan.

## 14. Thuật toán lexer đơn giản

Một lexer cơ bản có thể duy trì:

- source: văn bản nguồn.
- start: vị trí bắt đầu lexeme hiện tại.
- current: vị trí đang đọc.
- line và column: vị trí hiện tại.
- tokens: danh sách token đã tạo.

Mã giả:

~~~text
function scanTokens(source):
    while not atEnd():
        start = current
        scanToken()

    addToken(EOF)
    return tokens

function scanToken():
    c = advance()

    if isWhitespace(c):
        return

    if isLetter(c) or c == "_":
        scanIdentifierOrKeyword()
        return

    if isDigit(c):
        scanNumber()
        return

    if c == '"':
        scanString()
        return

    if c == ">":
        if match("="):
            addToken(GREATER_EQUAL)
        else:
            addToken(GREATER)
        return

    if c == "{":
        addToken(LEFT_BRACE)
        return

    reportUnexpectedCharacter(c)
~~~

Đây là mã giả minh họa. Lexer thực tế cần thêm các toán tử, chú thích, chuỗi escape, số thập phân, vị trí nguồn, khôi phục lỗi và quy tắc Unicode.

### 14.1. Nhận diện định danh và từ khóa

~~~text
function scanIdentifierOrKeyword():
    while isLetterOrDigit(peek()) or peek() == "_":
        advance()

    text = source[start:current]

    if keywordTable contains text:
        addToken(keywordTable[text])
    else:
        addToken(IDENTIFIER, text)
~~~

Lexer đọc toàn bộ định danh trước, sau đó mới tra bảng từ khóa. Cách này bảo đảm tên thenValue không bị tách thành THEN và IDENTIFIER.

### 14.2. Nhận diện số

~~~text
function scanNumber():
    while isDigit(peek()):
        advance()

    if peek() == "." and isDigit(peekNext()):
        advance()
        while isDigit(peek()):
            advance()
        addToken(DECIMAL, parseDecimal(source[start:current]))
    else:
        addToken(INTEGER, parseInteger(source[start:current]))
~~~

Mã giả này chỉ nhận số thập phân có chữ số ở cả hai phía dấu chấm. Nếu DSL cho phép .5 hoặc 5., cần mở rộng quy tắc và xác định cách tránh nhầm dấu chấm truy cập thuộc tính.

### 14.3. Nhận diện chuỗi

~~~text
function scanString():
    while not atEnd() and peek() != '"':
        if peek() == "\":
            advance()
            scanEscape()
        else:
            advance()

    if atEnd():
        reportUnterminatedString()
        return

    advance()
    raw = source[start:current]
    value = decodeEscapes(raw)
    addToken(STRING, value)
~~~

Việc xử lý escape cần theo đúng đặc tả. Nếu lexer bỏ qua ký tự sau dấu gạch chéo ngược mà không kiểm tra, nó có thể chấp nhận những escape không hợp lệ.

## 15. Kiểm thử lexer

Lexer cần được kiểm thử độc lập với parser. Mục tiêu là xác nhận mỗi đầu vào tạo đúng dãy token, lexeme, giá trị và vị trí; đồng thời phát hiện lỗi ở đúng vị trí.

### 15.1. Kiểm thử token đơn

| Đầu vào | Kết quả mong đợi |
|---|---|
| order | IDENTIFIER |
| when | WHEN nếu là từ khóa |
| 42 | INTEGER(42) |
| 3.14 | DECIMAL(3.14) |
| "hello" | STRING("hello") |
| >= | GREATER_EQUAL |
| { | LEFT_BRACE |
| } | RIGHT_BRACE |

### 15.2. Kiểm thử ranh giới và ưu tiên

Các cặp cần thử:

- > và >=
- = và ==
- ! và != nếu cả hai được hỗ trợ
- if và iffy
- rule và ruleName
- 12 và 12.5
- 1e3 và 1e nếu số mũ được hỗ trợ

Các bài kiểm thử này phát hiện lỗi maximal munch, thứ tự ưu tiên và ranh giới từ khóa.

### 15.3. Kiểm thử khoảng trắng và chú thích

Thử cùng một biểu thức với một dấu cách, nhiều dấu cách, tab, xuống dòng, chú thích cuối dòng và dòng trống. Nếu DSL không nhạy với khoảng trắng, dãy token có ý nghĩa phải giống nhau. Nếu DSL dựa trên thụt lề hoặc xuống dòng, kết quả cần phản ánh đúng quy tắc đã định nghĩa.

### 15.4. Kiểm thử literal và escape

Thử chuỗi rỗng, chuỗi có dấu nháy được escape, chuỗi có dấu gạch chéo ngược, chuỗi nhiều dòng nếu được hỗ trợ, chuỗi chưa đóng, escape không hợp lệ, số nguyên ở giới hạn biểu diễn và số có hậu tố đơn vị không hợp lệ.

### 15.5. Kiểm thử vị trí nguồn

Đặt lỗi ở đầu tệp, giữa dòng, sau nhiều dòng và cạnh ký tự Unicode. Kiểm tra thông báo lỗi trỏ đúng lexeme, dòng và cột theo quy ước của công cụ.

### 15.6. Kiểm thử thuộc tính (property-based testing)

Với lexer ổn định, có thể tạo ngẫu nhiên các chuỗi token hợp lệ rồi ghép chúng bằng khoảng trắng hoặc chú thích. Nếu các thành phần đó không mang ý nghĩa cú pháp, lexer cần cho kết quả token tương đương.

Có thể kiểm tra thêm rằng:

- Mỗi token có span nằm trong nguồn.
- Các token không chồng lấn sai vị trí.
- Lexeme của token khớp đoạn nguồn tương ứng.
- Lexer luôn kết thúc hoặc báo lỗi có kiểm soát.
- Mọi đầu vào đều có kết quả xác định, không treo hoặc lặp vô hạn.

## 16. Những quyết định thiết kế từ vựng ảnh hưởng đến DSL

### 16.1. Thêm từ khóa có thể phá mã cũ

Nếu DSL trước đây cho phép người dùng đặt tên biến là match, việc thêm match thành từ khóa có thể làm mã cũ không còn được phân tích như trước. Đây là thay đổi tương thích cần được xem xét.

Có thể tránh một phần vấn đề bằng từ khóa theo ngữ cảnh, cơ chế escape cho định danh hoặc quy tắc phiên bản. Nhưng mỗi lựa chọn đều làm đặc tả và lexer phức tạp hơn.

### 16.2. Phân biệt chữ hoa và chữ thường

Nếu DSL phân biệt hoa thường, Order và order là hai lexeme khác nhau. Nếu không phân biệt, lexer hoặc bước xử lý sau cần chuẩn hóa cách so sánh. Cần quyết định rõ đối với từ khóa và định danh.

Đừng âm thầm chuyển đổi toàn bộ lexeme nếu trường hợp chữ hoa có thể mang ý nghĩa trong chuỗi hoặc tên định danh.

### 16.3. Dấu phân cách số và định dạng địa phương

Một DSL được dùng ở nhiều quốc gia có thể gặp khác biệt về dấu thập phân và dấu phân nhóm. Ví dụ, 1,234 có thể mang nghĩa khác nhau tùy quy ước. Đặc tả DSL nên chọn một định dạng ổn định hoặc quy định locale rõ ràng; không nên để cùng một nguồn có nhiều cách hiểu theo máy đang chạy.

### 16.4. Token hóa literal có đơn vị

Đơn vị như ms, s, kg hoặc % có thể được xem là hậu tố literal hoặc định danh riêng. Quyết định này ảnh hưởng đến khả năng thêm đơn vị tùy chỉnh, suy luận kiểu và kiểm tra chuyển đổi.

### 16.5. Giữ thông tin phục vụ công cụ

Một lexer chỉ phục vụ thực thi có thể bỏ chú thích và khoảng trắng. Nhưng nếu DSL cần formatter, IDE, diff có ý nghĩa hoặc chỉnh sửa cấu trúc, nên giữ trivia, lexeme và span nguồn đủ chi tiết.

## 17. Bài tập tự kiểm tra

### Bài 1: Phân loại token

Cho đoạn DSL:

~~~text
when customer.age >= 18 and customer.active == true
~~~

Hãy liệt kê theo thứ tự từng lexeme, token kind và giá trị nếu có. Xác định khoảng trắng nào có thể bị bỏ qua.

### Bài 2: Phân biệt token và lexeme

Một tệp có hai lần xuất hiện của lexeme order và một lần xuất hiện của lexeme customer. Hãy giải thích vì sao hai token IDENTIFIER có thể có cùng token kind nhưng là hai token object ở hai vị trí khác nhau.

### Bài 3: Khớp dài nhất

Một DSL hỗ trợ các toán tử >, >=, = và ==. Hãy mô tả lexer cần xử lý chuỗi >= và == như thế nào để không tạo ra các token ngắn sai.

### Bài 4: Từ khóa và định danh

DSL có từ khóa if. Hãy xác định token kind của if, iffy và customer_if nếu định danh cho phép dấu gạch dưới. Giải thích vì sao lexer cần đọc hết định danh trước khi tra bảng từ khóa.

### Bài 5: Phân biệt các loại lỗi

Phân loại lỗi trong các đầu vào sau thành lỗi từ vựng, lỗi cú pháp, lỗi phân giải tên hoặc lỗi kiểu:

- set order.total = @
- set order.total =
- set unknown.total = 10
- set order.total = "ten"

Nêu giả định về schema và kiểu dữ liệu để câu trả lời có ý nghĩa.

### Bài 6: Thiết kế literal chuỗi

Đề xuất quy tắc cho chuỗi có dấu nháy kép, dấu gạch chéo ngược, newline và Unicode. Viết ba ví dụ hợp lệ và hai ví dụ không hợp lệ, kèm token hoặc thông báo lỗi mong đợi.

### Bài 7: Thiết kế một lexer nhỏ

Hãy liệt kê token kind và pattern cần có cho DSL tính phí giao hàng gồm biến, số, phần trăm, toán tử so sánh, AND/OR, ngoặc và từ khóa WHEN/THEN. Xác định quy tắc ưu tiên khi pattern chồng lấn.

## Kết luận

Lexeme là đoạn ký tự thực tế trong nguồn; token là đơn vị từ vựng mà lexer tạo ra; token kind phân loại đơn vị đó; pattern mô tả những lexeme hợp lệ. Lexer đọc văn bản, nhận diện từ khóa, định danh, literal, toán tử và dấu phân cách, sau đó tạo dãy token cho parser. Các quy tắc như khớp dài nhất, ưu tiên từ khóa, xử lý khoảng trắng, chú thích, Unicode và vị trí nguồn ảnh hưởng trực tiếp đến cách DSL được hiểu. Phân biệt rõ lỗi từ vựng với lỗi cú pháp, lỗi kiểu và lỗi nghiệp vụ giúp thiết kế pipeline dễ kiểm thử và thông báo lỗi chính xác hơn.

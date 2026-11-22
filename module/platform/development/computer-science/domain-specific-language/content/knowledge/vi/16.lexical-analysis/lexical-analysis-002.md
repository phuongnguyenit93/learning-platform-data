# Nhận diện token

## 1. Token là gì?

Trong phân tích từ vựng (lexical analysis), **token** là đơn vị cú pháp nhỏ nhất mà parser cần nhận biết để phân tích cấu trúc chương trình. Token thường đại diện cho một nhóm ký tự có cùng vai trò, chẳng hạn từ khóa, tên biến, số, chuỗi, toán tử hoặc dấu phân cách.

Ví dụ, xét một biểu thức trong DSL:

~~~text
when order.total >= 1000000 and order.status == "PAID"
~~~

Lexer (bộ phân tích từ vựng) có thể nhận diện chuỗi này thành các token:

| Văn bản đầu vào (lexeme) | Loại token |
|---|---|
| when | WHEN |
| order | IDENTIFIER |
| . | DOT |
| total | IDENTIFIER |
| >= | GREATER_EQUAL |
| 1000000 | INTEGER_LITERAL |
| and | AND |
| order | IDENTIFIER |
| . | DOT |
| status | IDENTIFIER |
| == | EQUAL_EQUAL |
| "PAID" | STRING_LITERAL |

Parser không cần xử lý từng ký tự riêng lẻ. Nó nhận chuỗi token và dùng grammar để xác định biểu thức điều kiện, phép so sánh và các thành phần bên trong.

Token thường có ít nhất hai thông tin:

- **Loại token (token kind/type):** phân loại vai trò của đơn vị, ví dụ IDENTIFIER hoặc INTEGER_LITERAL.
- **Lexeme:** đoạn ký tự thực tế trong mã nguồn tạo nên token, ví dụ order hoặc 1000000.

Trong một số compiler, token còn mang giá trị đã chuyển đổi (literal value), vị trí nguồn, kênh (channel), hoặc tham chiếu tới bảng ký tự. Ví dụ token INTEGER_LITERAL có lexeme là 1000000 và giá trị số nguyên tương ứng.

## 2. Token, lexeme và pattern

Ba khái niệm thường đi cùng nhau nhưng có ý nghĩa khác nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Token | Đơn vị phân loại mà lexer phát ra | IDENTIFIER |
| Lexeme | Đoạn ký tự cụ thể trong nguồn | orderTotal |
| Pattern | Quy tắc mô tả những lexeme thuộc một token | Chữ cái hoặc dấu gạch dưới, tiếp theo là chữ, số hoặc dấu gạch dưới |

Một pattern có thể mô tả rất nhiều lexeme. Ví dụ, pattern của identifier có thể là:

~~~regex
[A-Za-z_][A-Za-z0-9_]*
~~~

Theo pattern này, các tên order, total_2 và _internal là identifier hợp lệ. Chuỗi 2total không hợp lệ vì ký tự đầu tiên là chữ số.

Pattern của số nguyên thập phân không dấu có thể là:

~~~regex
[0-9]+
~~~

Nó nhận diện một hoặc nhiều chữ số. Nhưng nếu DSL hỗ trợ dấu âm, dấu phân cách hàng nghìn, số thập lục phân hoặc hậu tố kiểu, pattern cần mở rộng theo đặc tả.

Một loại token có thể có nhiều pattern khác nhau. Ví dụ STRING_LITERAL có thể cho phép chuỗi dùng dấu nháy kép, dấu nháy đơn hoặc chuỗi nhiều dòng. Ngược lại, một lexeme cụ thể thường được gán một loại token duy nhất trong ngữ cảnh lexer đã xác định.

## 3. Vai trò của lexer trong pipeline xử lý DSL

Phân tích từ vựng thường là bước đầu tiên sau khi đọc mã nguồn. Pipeline tổng quát:

~~~mermaid
flowchart TD
    A["Mã nguồn DSL"] --> B["Lexer / Scanner"]
    B --> C["Danh sách token"]
    C --> D["Parser"]
    D --> E["AST"]
    E --> F["Phân tích ngữ nghĩa"]
    F --> G["Thực thi hoặc sinh mã"]
~~~

Lexer chịu trách nhiệm:

1. Đọc luồng ký tự từ đầu đến cuối.
2. Nhận diện ranh giới giữa các lexeme.
3. Xác định loại token phù hợp với mỗi lexeme.
4. Bỏ qua hoặc lưu lại khoảng trắng, xuống dòng và comment theo chính sách của DSL.
5. Chuyển đổi literal thành giá trị có kiểu khi phù hợp.
6. Ghi nhận vị trí nguồn để parser và công cụ phát triển báo lỗi chính xác.
7. Phát hiện ký tự hoặc chuỗi ký tự không khớp với token nào.

Lexer không thường quyết định một tên như customer có được khai báo hay không, hoặc hai kiểu có tương thích hay không. Đó là công việc của parser và các giai đoạn phân tích ngữ nghĩa. Lexer chỉ xác định customer là một identifier theo quy tắc từ vựng.

Việc tách lexer khỏi parser làm cho compiler dễ tổ chức hơn. Grammar của parser có thể mô tả cấu trúc ở mức token, trong khi lexer tập trung vào chi tiết ký tự, escape sequence và định dạng literal.

## 4. Thiết kế bộ token cho DSL

Trước khi viết lexer, cần liệt kê các nhóm token mà ngôn ngữ cần hỗ trợ. Một DSL khai báo hoặc biểu thức thường có những nhóm sau:

| Nhóm | Ví dụ token | Lexeme ví dụ |
|---|---|---|
| Từ khóa | RULE, WHEN, THEN, IMPORT | rule, when, then, import |
| Identifier | IDENTIFIER | customer, calculateFee |
| Literal số | INTEGER_LITERAL, DECIMAL_LITERAL | 42, 19.95 |
| Literal chuỗi | STRING_LITERAL | "hello" |
| Literal logic | TRUE, FALSE | true, false |
| Literal rỗng | NULL hoặc NONE | null, none |
| Toán tử | PLUS, MINUS, EQUAL_EQUAL | +, -, == |
| Toán tử nhiều ký tự | GREATER_EQUAL, ARROW | >=, -> |
| Dấu phân cách | LPAREN, RPAREN, LBRACE, RBRACE | (, ), {, } |
| Dấu câu | COMMA, COLON, DOT, SEMICOLON | , : . ; |
| Comment | LINE_COMMENT, BLOCK_COMMENT | # ghi chú, /* ghi chú */ |
| Khoảng trắng | WHITESPACE, NEWLINE | dấu cách, tab, xuống dòng |

Không phải token nào cũng được chuyển cho parser. Khoảng trắng và comment có thể được lexer bỏ qua, hoặc giữ trên một channel riêng để formatter, IDE và công cụ tài liệu hóa sử dụng.

### 4.1. Token có giá trị và token chỉ mang cấu trúc

Một số token chứa giá trị cần thiết cho AST:

- INTEGER_LITERAL chứa giá trị số nguyên.
- DECIMAL_LITERAL chứa giá trị thập phân.
- STRING_LITERAL chứa chuỗi sau khi xử lý escape.
- IDENTIFIER chứa tên hoặc tham chiếu tới đoạn tên trong source.

Các token như PLUS, COMMA hoặc LBRACE chủ yếu biểu diễn cấu trúc. Chúng không cần giá trị riêng ngoài loại token và vị trí nguồn.

Nên giữ cả lexeme và giá trị đã giải mã khi cần thông báo lỗi, tái tạo mã nguồn hoặc hiển thị nội dung gốc. Ví dụ, chuỗi nguồn "A\nB" có lexeme chứa hai ký tự gạch chéo và n, nhưng giá trị chuỗi sau khi giải mã chứa một ký tự xuống dòng.

## 5. Nhận diện identifier và từ khóa

Identifier dùng để đặt tên cho biến, hàm, kiểu, rule, namespace hoặc thành phần khác. Một quy tắc phổ biến là:

~~~regex
[A-Za-z_][A-Za-z0-9_]*
~~~

Ví dụ hợp lệ: order, order_2, _cache, calculateTotal.

Ví dụ không hợp lệ theo pattern trên: 2order, total-price, customer.name. Dấu chấm trong customer.name thường là một token DOT nằm giữa hai identifier, không phải một phần của identifier.

### 5.1. Từ khóa là identifier có ý nghĩa dành riêng

Các từ như rule, when, then, import và namespace có thể là từ khóa. Chúng thường có cùng hình thức chữ cái với identifier nhưng mang ý nghĩa cú pháp riêng.

Có hai cách xử lý phổ biến:

1. Lexer có quy tắc riêng cho từng keyword và ưu tiên keyword khi lexeme khớp chính xác.
2. Lexer luôn phát IDENTIFIER, sau đó tra lexeme trong bảng từ khóa để đổi loại token nếu trùng từ khóa dành riêng.

Ví dụ:

~~~text
rule discount {
    when customer.level == "GOLD"
    then applyDiscount()
}
~~~

Trong đó rule, when và then là keyword; discount, customer, level và applyDiscount là identifier.

Không nên phân loại từ khóa chỉ bằng tiền tố. Ví dụ, rulebook không phải keyword rule nếu toàn bộ lexeme là rulebook. Lexer phải đọc hết identifier trước rồi mới so sánh chính xác với bảng keyword.

### 5.2. Từ khóa mềm (soft keyword)

Một DSL có thể có soft keyword: từ chỉ mang ý nghĩa đặc biệt trong một ngữ cảnh cú pháp nhất định, nhưng vẫn được dùng làm identifier ở ngữ cảnh khác.

Ví dụ, match có thể là từ khóa khi mở đầu biểu thức pattern matching, nhưng là tên biến hợp lệ trong một DSL khác. Soft keyword giúp ngôn ngữ mở rộng cú pháp mà ít làm hỏng mã cũ, nhưng tăng trách nhiệm cho parser vì ý nghĩa phụ thuộc ngữ cảnh.

Nếu dùng soft keyword, đặc tả cần nêu rõ vị trí nào lexer hoặc parser xem từ đó là keyword và khi nào nó vẫn là identifier.

## 6. Nhận diện số và literal

Literal số thường có nhiều dạng:

~~~text
42
3.1415
1e6
0xFF
0b1010
~~~

Một DSL không nhất thiết phải hỗ trợ tất cả. Cần quy định chính xác:

- Dấu chấm thập phân và dấu phân cách hàng nghìn.
- Ký pháp số mũ.
- Cơ số nhị phân, bát phân hoặc thập lục phân.
- Dấu phân cách chữ số như dấu gạch dưới.
- Hậu tố kiểu như L, f hoặc đơn vị miền.
- Dấu âm là một phần literal hay là toán tử unary riêng.

### 6.1. Dấu âm và toán tử trừ

Trong nhiều ngôn ngữ, dấu trừ không nằm trong token số:

~~~text
total - 5
total * -5
~~~

Lexer có thể phát token MINUS rồi INTEGER_LITERAL. Parser xác định MINUS là phép trừ nhị phân trong biểu thức đầu tiên và là toán tử unary trong biểu thức thứ hai.

Cách này giúp lexer đơn giản và phân biệt rõ cú pháp toán tử. Nếu lexer gộp dấu âm vào literal, việc nhận diện có thể phụ thuộc vào token đứng trước và dễ gây nhập nhằng.

### 6.2. Số thập phân và dấu chấm

Một lexer cần phân biệt số 12.5 với số 12 theo sau bởi dấu chấm truy cập thuộc tính:

~~~text
12.5
order.total
12.toString()
~~~

Quy tắc cần được thiết kế để dấu chấm chỉ thuộc literal số khi theo sau bởi phần thập phân hợp lệ. Nếu DSL cho phép dấu chấm kết thúc số hoặc ký pháp đặc biệt, cần mô tả rõ để tránh cách nhận diện không nhất quán.

### 6.3. Literal có hậu tố đơn vị

DSL miền nghiệp vụ có thể hỗ trợ đơn vị:

~~~text
timeout = 30s
distance = 12km
rate = 5%
~~~

Có thể xem 30s là một token duration literal, hoặc nhận diện số 30 và identifier s rồi để parser kết hợp. Cách đầu đơn giản cho parser nhưng khiến lexer phải hiểu thêm đơn vị. Cách thứ hai linh hoạt hơn và cho phép đơn vị được phân giải qua bảng symbol, nhưng grammar phải quy định cách kết hợp.

Với tiền tệ và đơn vị đo, cần tránh chuyển đổi ngầm định không rõ nghĩa. Lexer chỉ nhận diện lexeme; việc kiểm tra đơn vị có hợp lệ và có tương thích với biểu thức hay không thuộc các giai đoạn tiếp theo.

## 7. Nhận diện chuỗi và escape sequence

Chuỗi thường được bao quanh bởi dấu nháy:

~~~text
"Hello"
'Hello'
"Line 1\nLine 2"
"She said \"OK\""
~~~

Lexer cần nhận diện:

- Dấu mở chuỗi và dấu đóng chuỗi.
- Ký tự escape.
- Kết thúc chuỗi không hợp lệ.
- Ký tự xuống dòng nếu chuỗi không cho phép nhiều dòng.
- Unicode escape nếu DSL hỗ trợ.

Ví dụ một quy tắc giản lược cho chuỗi dùng dấu nháy kép:

~~~regex
"([^"\\]|\\.)*"
~~~

Quy tắc này minh họa chuỗi bắt đầu và kết thúc bằng dấu nháy kép, cho phép ký tự thông thường hoặc một cặp escape. Lexer thực tế cần kiểm tra escape hợp lệ theo đặc tả, thay vì chấp nhận mọi ký tự sau dấu gạch chéo ngược.

### 7.1. Giải mã escape

Một số escape thường gặp:

| Escape | Giá trị |
|---|---|
| \n | Xuống dòng |
| \r | Carriage return |
| \t | Tab |
| \\ | Dấu gạch chéo ngược |
| \" | Dấu nháy kép |
| \u0041 | Ký tự Unicode theo mã được chỉ định, nếu DSL hỗ trợ |

Lexer có thể giữ lexeme nguyên bản và đồng thời tạo giá trị đã giải mã. Nếu escape không hợp lệ, nó nên phát lỗi tại vị trí escape, thay vì âm thầm bỏ dấu gạch chéo hoặc thay bằng ký tự tùy ý.

### 7.2. Chuỗi nhiều dòng và raw string

DSL có thể hỗ trợ chuỗi nhiều dòng:

~~~text
"""
This is a report.
It contains multiple lines.
"""
~~~

Hoặc raw string, trong đó escape không được diễn giải:

~~~text
r"C:\reports\2026\monthly"
~~~

Những dạng này thường cần lexical mode hoặc quy tắc pattern riêng. Cần xác định cách xử lý dấu phân cách xuất hiện bên trong nội dung, cách thụt lề và việc chuẩn hóa xuống dòng.

## 8. Nhận diện toán tử và dấu phân cách

Một DSL có thể định nghĩa các toán tử một ký tự và nhiều ký tự:

~~~text
+  -  *  /  %
=  ==  !=  <  <=  >  >=
&&  ||  !
->  =>  ??
~~~

Các dấu phân cách thường gặp:

~~~text
( )  { }  [ ]
,  :  ;  .
~~~

Lexer cần nhận diện đúng toán tử dài nhất khi nhiều token có chung tiền tố. Ví dụ, với > và >=, đầu vào >= phải được nhận thành GREATER_EQUAL thay vì GREATER rồi EQUAL.

### 8.1. Quy tắc longest match

Quy tắc longest match (còn gọi là maximal munch) thường yêu cầu lexer chọn lexeme dài nhất có thể khớp tại vị trí hiện tại.

Ví dụ:

~~~text
total >= threshold
~~~

Tại dấu >, lexer có thể nhận diện GREATER hoặc GREATER_EQUAL. Vì >= dài hơn và khớp đầu vào, nó chọn GREATER_EQUAL.

Tương tự:

~~~text
count++
value->result
left != right
~~~

Nếu DSL có ++, -> và !=, lexer phải xét token nhiều ký tự trước hoặc dùng thuật toán tự động tương đương để chọn kết quả dài nhất.

### 8.2. Ưu tiên khi độ dài bằng nhau

Có thể có hai quy tắc token cùng khớp một đoạn ký tự. Khi đó DSL cần chính sách ưu tiên. Ví dụ, keyword rule và identifier đều có thể khớp chuỗi rule. Lexer thường chọn keyword nếu lexeme khớp chính xác với từ khóa dành riêng.

Quy tắc tổng quát thường là:

1. Chọn lexeme dài nhất.
2. Nếu nhiều quy tắc khớp cùng độ dài, áp dụng thứ tự ưu tiên được công bố.
3. Với identifier, kiểm tra bảng keyword sau khi đã nhận diện toàn bộ lexeme.

Không nên dựa vào thứ tự ngẫu nhiên của cấu trúc dữ liệu hoặc thứ tự load module để quyết định token.

## 9. Khoảng trắng, xuống dòng và comment

Khoảng trắng có thể gồm space, tab, carriage return và newline. Với nhiều DSL, lexer bỏ qua space và tab vì chúng chỉ phân tách token:

~~~text
let total = price + tax;
~~~

và:

~~~text
let    total=price+tax;
~~~

có thể tạo cùng chuỗi token nếu DSL không dùng indentation hoặc whitespace để biểu diễn cấu trúc.

### 9.1. Khi xuống dòng có ý nghĩa

Một số DSL dùng newline để kết thúc câu lệnh hoặc phân tách record. Khi đó NEWLINE phải được giữ lại như token:

~~~text
name = "monthly-report"
retries = 3
enabled = true
~~~

Parser có thể dùng NEWLINE để xác định ranh giới giữa các khai báo. Nếu lexer bỏ mọi whitespace, parser sẽ không còn thông tin này.

### 9.2. Indentation-sensitive DSL

Một số ngôn ngữ dùng mức thụt lề để biểu diễn block. Lexer có thể phát INDENT và DEDENT khi độ thụt lề tăng hoặc giảm:

~~~text
rule discount:
    when customer.level == "GOLD"
    then applyDiscount()
    otherwise reject()
~~~

Trong trường hợp này, lexer cần theo dõi stack mức indentation và so sánh ở đầu mỗi dòng. Tab và space phải có chính sách rõ ràng; nếu trộn tùy ý, hai dòng nhìn giống nhau có thể tạo cấu trúc khác nhau.

### 9.3. Comment

Comment thường bị bỏ qua hoặc lưu trên hidden channel:

~~~text
# Chỉ áp dụng cho khách hàng thân thiết
rule loyal-customer {
    ...
}
~~~

Nếu comment cần được giữ để formatter hoặc IDE bảo toàn, lexer có thể phát token comment trên channel riêng. Nếu chỉ phục vụ parser, lexer có thể bỏ chúng sau khi cập nhật đúng vị trí dòng và cột.

## 10. Thứ tự nhận diện và các trường hợp nhập nhằng

Một lexer cần có quy tắc nhất quán khi nhiều token có thể khớp cùng một đoạn đầu vào.

### 10.1. Keyword so với identifier

Với đầu vào:

~~~text
when
whenever
~~~

Nếu when là keyword và whenever là identifier, lexer phải nhận diện toàn bộ identifier trước khi so sánh với bảng keyword. Không được cắt whenever thành keyword when và phần còn lại ever.

### 10.2. Toán tử dài so với toán tử ngắn

Với đầu vào:

~~~text
<=
<<=
==
===
~~~

Nếu DSL hỗ trợ các toán tử này, lexer phải chọn token dài nhất hợp lệ. Nếu một chuỗi không được hỗ trợ, chẳng hạn === khi chỉ có == và =, cần quy định liệu lexer phát == rồi = hay báo lỗi trực tiếp. Lựa chọn này ảnh hưởng chất lượng diagnostic và nên nhất quán.

### 10.3. Số so với identifier

Với:

~~~text
123abc
~~~

DSL có thể coi đây là số 123 theo sau identifier abc, hoặc coi toàn bộ là một lexeme sai. Nhiều ngôn ngữ chọn báo lỗi để tránh người dùng vô tình viết sai literal có hậu tố. Nếu DSL hỗ trợ suffix như 10ms, lexer cần định nghĩa pattern và ranh giới rõ ràng.

### 10.4. Dấu chấm và literal

Với:

~~~text
3.14
object.value
.5
5.
~~~

Lexer cần biết DSL cho phép những dạng số nào. Nếu .5 là decimal hợp lệ, dấu chấm ở đầu có thể mở literal số. Nếu không, nó có thể là DOT token rồi một số nguyên. Những quy tắc này cần được đặc tả để lexer và parser không diễn giải khác nhau.

## 11. Lexical state và context-sensitive lexing

Không phải mọi token đều được nhận diện bằng một bộ pattern cố định áp dụng cho toàn bộ tệp. Một số DSL cần lexer thay đổi trạng thái theo ngữ cảnh.

Ví dụ, khi ở trong chuỗi, dấu // không mở comment:

~~~text
url = "https://example.com/rules";
// Đây mới là comment
~~~

Lexer có thể có các trạng thái:

- DEFAULT: nhận diện keyword, identifier, toán tử và literal.
- STRING: đọc nội dung chuỗi.
- STRING_ESCAPE: xử lý ký tự escape.
- BLOCK_COMMENT: đọc tới dấu đóng comment.
- TEMPLATE: đọc phần văn bản của template.
- INTERPOLATION: quay lại nhận diện biểu thức bên trong template.

Ví dụ template:

~~~text
message = "Hello, ${customer.name}!";
~~~

Lexer phải chuyển từ trạng thái STRING sang INTERPOLATION khi gặp dấu mở interpolation, nhận diện biểu thức customer.name, rồi quay lại STRING khi gặp dấu đóng interpolation.

Context-sensitive lexing có thể làm lexer phức tạp hơn. Nếu có thể, nên giữ phần lớn quy tắc từ vựng độc lập với ngữ nghĩa. Không nên yêu cầu lexer tra cứu kiểu hoặc symbol table để quyết định một tên là token nào, trừ khi ngôn ngữ thực sự cần cơ chế đặc biệt.

## 12. Unicode và quy tắc ký tự

DSL hiện đại thường cần hỗ trợ Unicode trong chuỗi, comment và đôi khi cả identifier. Cần phân biệt:

- **Character encoding:** cách byte được giải mã thành ký tự, thường là UTF-8.
- **Code point:** giá trị Unicode của một ký tự trừu tượng.
- **Code unit:** đơn vị lưu trữ của encoding hoặc runtime, ví dụ UTF-16 code unit.
- **Grapheme cluster:** đơn vị ký tự mà người dùng nhìn thấy, có thể gồm nhiều code point.

Một identifier có thể cho phép chữ cái Unicode:

~~~text
khachHang = loadCustomer();
客户 = loadCustomer();
~~~

Nếu hỗ trợ, cần xác định nhóm Unicode nào được phép ở vị trí bắt đầu và vị trí tiếp theo. Không nên dùng một quy tắc quá rộng cho mọi ký tự vì có thể chấp nhận dấu câu hoặc ký tự điều khiển không mong muốn.

### 12.1. Chuẩn hóa Unicode

Hai chuỗi có thể hiển thị giống nhau nhưng có biểu diễn code point khác nhau. Ví dụ một chữ có dấu có thể được mã hóa bằng một code point dựng sẵn hoặc bằng chữ cái cộng dấu kết hợp.

DSL cần quyết định có chuẩn hóa identifier hay không, chẳng hạn NFC. Nếu có, phải áp dụng nhất quán khi khai báo và khi tham chiếu, đồng thời lưu hoặc báo vị trí theo văn bản nguồn gốc để diagnostic chính xác.

### 12.2. Phân biệt hoa thường

Một DSL có thể phân biệt chữ hoa và chữ thường:

~~~text
customer
Customer
CUSTOMER
~~~

hoặc coi chúng là cùng một identifier. Từ khóa cũng cần chính sách rõ ràng. Nếu keyword không phân biệt hoa thường, lexer phải chuẩn hóa khi so sánh nhưng vẫn giữ lexeme gốc để hiển thị và bảo toàn nguồn.

## 13. Token và vị trí nguồn

Mỗi token nên mang thông tin vị trí đủ để báo lỗi và hỗ trợ công cụ:

| Thuộc tính | Mục đích |
|---|---|
| kind | Loại token |
| lexeme hoặc source span | Đoạn nguồn tạo ra token |
| start offset | Vị trí bắt đầu trong nguồn |
| end offset | Vị trí kết thúc |
| line | Dòng nguồn |
| column | Cột nguồn |
| literal value | Giá trị đã giải mã nếu token là literal |
| channel | Kênh token, nếu lexer hỗ trợ |

Ví dụ cấu trúc token đơn giản:

~~~java
public record Token(
        TokenKind kind,
        String lexeme,
        Object literalValue,
        int startOffset,
        int endOffset,
        int line,
        int column) {
}
~~~

Với mã nguồn lớn, thay vì sao chép chuỗi lexeme cho mọi token, có thể lưu source span trỏ vào vùng văn bản gốc. Cách này giảm cấp phát bộ nhớ và giúp công cụ lấy lại chính xác nội dung.

Column có thể được tính theo byte, code point, UTF-16 code unit hoặc cột hiển thị. Đặc tả và công cụ cần thống nhất đơn vị. Nếu editor dùng UTF-16 offset còn lexer dùng code point, cần chuyển đổi đúng khi hiển thị diagnostic.

## 14. Lỗi từ vựng và phục hồi

Lỗi từ vựng xảy ra khi một ký tự hoặc chuỗi ký tự không khớp với bất kỳ token hợp lệ nào, hoặc khi một token không hoàn chỉnh.

Ví dụ:

~~~text
let amount = 12@;
let title = "unfinished;
let value = 0xG1;
~~~

Các lỗi có thể là:

- Ký tự @ không được hỗ trợ tại vị trí này.
- Chuỗi chưa có dấu nháy đóng.
- Literal thập lục phân có chữ số không hợp lệ.

Một lexer nên báo lỗi kèm vị trí và lexeme liên quan:

~~~text
LEX-001: Unexpected character '@'.
  at pricing.dsl:1:17
  let amount = 12@;
                  ^
~~~

### 14.1. Dừng ngay hay tiếp tục?

Có hai chiến lược phổ biến:

- **Fail-fast:** dừng ở lỗi từ vựng đầu tiên. Cách này đơn giản và phù hợp với một số compiler hoặc công cụ kiểm tra nhỏ.
- **Error recovery:** báo lỗi rồi bỏ qua một phần đầu vào để tiếp tục tìm lỗi khác. Cách này hữu ích cho IDE và editor vì người dùng nhận được nhiều diagnostic trong một lần phân tích.

Một chiến lược phục hồi có thể bỏ qua tới newline, dấu phân cách hoặc ký tự bắt đầu token hợp lệ tiếp theo. Tuy nhiên, bỏ qua quá nhiều có thể làm parser tạo thêm lỗi dây chuyền. Lexer và parser cần phối hợp để giữ quá trình phục hồi có kiểm soát.

### 14.2. Token lỗi

Một số lexer phát token ERROR thay vì chỉ ghi diagnostic. Parser có thể nhận token này và phục hồi tại ranh giới câu lệnh. Nếu dùng cách này, cần quy định token lỗi có được phép đi vào AST hay chỉ tồn tại tạm trong pipeline phân tích.

## 15. Cách triển khai lexer

Có nhiều cách xây dựng lexer:

### 15.1. Lexer thủ công

Lexer thủ công dùng vòng lặp đọc từng ký tự, kiểm tra ký tự hiện tại và gọi hàm xử lý tương ứng. Cách này phù hợp với DSL nhỏ, grammar từ vựng đơn giản và cần kiểm soát chi tiết.

Pseudocode:

~~~text
while not endOfInput:
    skip spaces and tabs

    if current is newline:
        emit NEWLINE or skip it
    else if starts a comment:
        scan comment
    else if starts a string:
        scan string literal
    else if starts a number:
        scan number literal
    else if starts an identifier:
        scan identifier and classify keyword
    else:
        scan the longest matching operator or delimiter

    if no rule matches:
        report lexical error
~~~

Ưu điểm là dễ gắn source location, xử lý lexical state và đưa ra diagnostic tùy biến. Nhược điểm là khi grammar lớn lên, các nhánh và thứ tự ưu tiên có thể khó quản lý nếu không có thiết kế rõ ràng.

### 15.2. Lexer sinh tự động từ grammar

Công cụ như ANTLR cho phép khai báo token bằng grammar rồi sinh lexer:

~~~antlr
lexer grammar RuleLexer;

WHEN        : 'when';
THEN        : 'then';
AND         : 'and';
TRUE        : 'true';
FALSE       : 'false';

GREATER_EQ  : '>=';
EQUAL_EQ    : '==';
GREATER     : '>';
EQUAL       : '=';

INTEGER     : [0-9]+;
IDENTIFIER  : [a-zA-Z_] [a-zA-Z0-9_]*;
STRING      : '"' ( '\\' . | ~["\\\r\n] )* '"';

LINE_COMMENT: '#' ~[\r\n]* -> channel(HIDDEN);
WS          : [ \t\r\n]+ -> skip;
~~~

Đây là grammar minh họa. Thứ tự rule và cơ chế ưu tiên của công cụ lexer ảnh hưởng việc chọn token khi nhiều rule cùng khớp. Với ANTLR, lexer thường áp dụng quy tắc khớp dài nhất và dùng thứ tự rule khi độ dài bằng nhau; cần tham khảo đúng phiên bản công cụ và cách dùng mode/channel trong grammar thực tế.

### 15.3. DFA và automata

Nhiều lexer được xây dựng dựa trên biểu thức chính quy và automata. Regular expression có thể được chuyển thành NFA rồi DFA để nhận diện pattern hiệu quả.

Ví dụ, identifier theo pattern:

~~~regex
[A-Za-z_][A-Za-z0-9_]*
~~~

có thể được biểu diễn bằng một máy trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> Start
    Start --> Identifier: letter or underscore
    Identifier --> Identifier: letter, digit or underscore
    Identifier --> [*]: other character / accept
~~~

Trạng thái Identifier là trạng thái chấp nhận. Lexer tiếp tục đọc khi ký tự tiếp theo còn thuộc nhóm cho phép. Khi gặp ký tự khác, nó kết thúc lexeme và trả ký tự đó về luồng đầu vào để nhận diện token tiếp theo.

Với token nhiều pattern, lexer cần kết hợp các automata hoặc dùng bảng chuyển trạng thái để tìm lexeme dài nhất. Cách này hiệu quả với ngôn ngữ lớn và có thể được sinh tự động từ đặc tả token.

## 16. Ví dụ phân tích một đoạn DSL từ đầu đến token

Xét chương trình:

~~~text
rule discount {
    when order.total >= 1000000 and order.status == "PAID"
    then applyDiscount(10);
}
~~~

Lexer có thể phát ra chuỗi token sau:

| Thứ tự | Token | Lexeme |
|---:|---|---|
| 1 | RULE | rule |
| 2 | IDENTIFIER | discount |
| 3 | LBRACE | { |
| 4 | WHEN | when |
| 5 | IDENTIFIER | order |
| 6 | DOT | . |
| 7 | IDENTIFIER | total |
| 8 | GREATER_EQUAL | >= |
| 9 | INTEGER_LITERAL | 1000000 |
| 10 | AND | and |
| 11 | IDENTIFIER | order |
| 12 | DOT | . |
| 13 | IDENTIFIER | status |
| 14 | EQUAL_EQUAL | == |
| 15 | STRING_LITERAL | "PAID" |
| 16 | THEN | then |
| 17 | IDENTIFIER | applyDiscount |
| 18 | LPAREN | ( |
| 19 | INTEGER_LITERAL | 10 |
| 20 | RPAREN | ) |
| 21 | SEMICOLON | ; |
| 22 | RBRACE | } |

Khoảng trắng và xuống dòng được bỏ qua trong ví dụ này. Parser nhận chuỗi token để xây dựng cấu trúc rule, condition và action. Sau đó, các bước phân tích ngữ nghĩa mới kiểm tra order có tồn tại, total có phải kiểu số và applyDiscount có nhận đối số phù hợp hay không.

Ví dụ minh họa ranh giới trách nhiệm:

- Lexer xác định >= là một token GREATER_EQUAL.
- Parser xác định GREATER_EQUAL xuất hiện trong biểu thức so sánh.
- Type checker xác nhận hai vế có kiểu tương thích.
- Runtime đánh giá biểu thức bằng dữ liệu đơn hàng thực tế.

## 17. Hiệu năng và khả năng mở rộng

Lexer thường đọc mã nguồn tuần tự, do đó có thể hoạt động rất nhanh. Tuy nhiên, một số thiết kế có thể làm tăng chi phí:

- Regex quá phức tạp hoặc có backtracking lớn.
- Sao chép chuỗi lexeme cho mọi token.
- Tính lại line/column từ đầu cho từng token.
- Nạp toàn bộ tệp lớn vào bộ nhớ khi có thể dùng streaming.
- Chuyển đổi Unicode nhiều lần.
- Tra cứu keyword bằng cấu trúc dữ liệu kém phù hợp.

Một số thực hành:

1. Duy trì offset hiện tại và cập nhật dòng/cột khi tiến.
2. Dùng bảng keyword hoặc trie/hash map phù hợp với số lượng từ khóa.
3. Lưu source span thay vì sao chép lexeme khi cần tiết kiệm bộ nhớ.
4. Dùng scanner tuyến tính hoặc DFA cho pattern phổ biến.
5. Đặt giới hạn hợp lý cho độ dài chuỗi, comment và literal nếu DSL xử lý đầu vào không tin cậy.
6. Đo hiệu năng với tệp thực tế trước khi tối ưu.

Với IDE, lexer có thể cần hoạt động gia tăng (incremental lexing): khi người dùng sửa một vùng nhỏ, công cụ chỉ phân tích lại phần bị ảnh hưởng và phần tiếp theo cần thiết. Điều này đòi hỏi token có vị trí ổn định và lexer có thể khôi phục trạng thái tại một điểm trong tệp.

## 18. Kiểm thử bộ nhận diện token

Lexer cần được kiểm thử theo từng loại token và các trường hợp giao nhau.

### 18.1. Kiểm thử token riêng lẻ

Ví dụ:

~~~text
42          -> INTEGER_LITERAL
3.14        -> DECIMAL_LITERAL
customer_1  -> IDENTIFIER
when        -> WHEN
>=          -> GREATER_EQUAL
"hello"     -> STRING_LITERAL
~~~

### 18.2. Kiểm thử ranh giới và ưu tiên

Các cặp như > và >=, = và ==, / và //, identifier và keyword cần có test để xác nhận quy tắc longest match và tie-break.

### 18.3. Kiểm thử chuỗi và comment

Kiểm tra dấu comment trong string, escape hợp lệ và không hợp lệ, chuỗi chưa đóng, comment khối chưa đóng, comment nhiều dòng và newline trong chuỗi.

### 18.4. Kiểm thử Unicode

Kiểm tra ký tự ngoài ASCII trong string, comment và identifier nếu DSL cho phép. Kiểm tra offset và column trong diagnostic khi có ký tự Unicode nhiều code unit.

### 18.5. Kiểm thử lỗi

Kiểm tra ký tự lạ, literal sai định dạng, escape không hợp lệ và cách lexer phục hồi để tiếp tục nhận diện token sau lỗi.

Một test lexer thường xác nhận cả loại token, lexeme, literal value và vị trí nguồn. Chỉ kiểm tra chuỗi loại token có thể bỏ sót lỗi khi lexer nhận đúng loại nhưng cắt sai ranh giới hoặc giải mã sai giá trị.

## 19. Những lỗi thiết kế thường gặp

### Nhận diện keyword theo tiền tố

Nếu lexer tách whenever thành WHEN và EVER, chương trình bị phân tích sai. Hãy nhận diện toàn bộ identifier rồi phân loại keyword theo khớp chính xác.

### Không áp dụng longest match

Nhận >= thành GREATER và EQUAL làm parser phải xử lý một cấu trúc không đúng. Hãy ưu tiên lexeme dài nhất.

### Gộp dấu âm vào mọi literal số

Điều này làm lexer phải đoán ngữ cảnh toán tử và có thể gây nhập nhằng. Thông thường nên để dấu trừ là token riêng rồi xử lý unary/binary trong parser.

### Bỏ mất vị trí nguồn

Nếu lexer không lưu offset, dòng và cột, lỗi parser hoặc type checker khó chỉ đúng đoạn mã. Hãy giữ source span ngay từ đầu.

### Nhầm comment với nội dung chuỗi

Tìm ký hiệu comment mà không xét lexical state có thể cắt chuỗi URL hoặc văn bản. Lexer cần biết đang ở trong string, comment hay trạng thái mặc định.

### Dùng regex cho mọi vấn đề

Regex phù hợp với pattern cục bộ nhưng không đủ để xử lý mọi cấu trúc lồng nhau hoặc trạng thái phức tạp. Chuỗi nhiều dòng, template interpolation và comment lồng nhau thường cần state machine.

### Không đặc tả Unicode

Nếu lexer cho phép identifier Unicode mà không có quy tắc chuẩn hóa và so sánh, hai tên nhìn giống nhau có thể được xem là khác nhau. Cần xác định encoding, tập ký tự và chính sách normalization.

### Bỏ qua lỗi từ vựng

Âm thầm bỏ ký tự lạ có thể làm chương trình được diễn giải khác với nội dung người dùng viết. Hãy phát diagnostic và phục hồi theo quy tắc rõ ràng.

## 20. Quy trình thiết kế nhận diện token cho DSL mới

Khi xây dựng lexer, có thể thực hiện theo trình tự:

1. **Liệt kê token cần có.** Phân nhóm keyword, identifier, literal, operator, delimiter, comment và whitespace.
2. **Định nghĩa pattern.** Quy định ký tự hợp lệ, độ dài, escape, hậu tố và giới hạn của từng token.
3. **Quy định ưu tiên.** Xác định longest match, tie-break và cách xử lý keyword.
4. **Thiết kế lexical state.** Xác định khi nào cần trạng thái string, comment, template hoặc interpolation.
5. **Quy định whitespace.** Xác định newline và indentation có mang ý nghĩa hay không.
6. **Định nghĩa Unicode.** Chọn encoding, tập ký tự identifier, normalization và đơn vị vị trí nguồn.
7. **Thiết kế token representation.** Lưu kind, lexeme/source span, literal value và source location cần thiết.
8. **Xác định lỗi và phục hồi.** Chọn fail-fast hoặc error recovery, quy định token lỗi và diagnostic.
9. **Chọn cách triển khai.** Lexer thủ công, công cụ sinh lexer hoặc DFA tùy độ phức tạp.
10. **Viết bộ kiểm thử.** Bao gồm token riêng lẻ, ranh giới, trường hợp nhập nhằng, Unicode và lỗi.

## 21. Kết luận

Nhận diện token là bước chuyển luồng ký tự của DSL thành những đơn vị có ý nghĩa từ vựng để parser xử lý. Một token thường có loại, lexeme, giá trị literal và vị trí nguồn. Lexer cần nhận diện chính xác keyword, identifier, literal, toán tử, dấu phân cách, comment và khoảng trắng theo các pattern cùng quy tắc ưu tiên đã công bố.

Các nguyên tắc như longest match, xử lý keyword sau khi nhận diện identifier, lexical state cho chuỗi và comment, lưu vị trí nguồn và quy định Unicode giúp việc phân tích nhất quán. Với DSL nhỏ có thể viết lexer thủ công; với ngôn ngữ lớn hơn có thể dùng grammar sinh tự động, regex và automata.

Khi thiết kế DSL, hãy xác định rõ mỗi nhóm ký tự được nhận diện thành token nào, những trường hợp nào có thể nhập nhằng và lexer cần báo lỗi ra sao. Một bộ nhận diện token có quy tắc rõ ràng tạo nền tảng cho parser, checker, IDE và các công cụ phát triển phía sau.

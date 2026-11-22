# Quy trình lexer

## 1. Lexer trong kiến trúc của DSL

Lexer (*lexical analyzer* hoặc bộ phân tích từ vựng) là thành phần đọc văn bản nguồn và chia nó thành một chuỗi token có ý nghĩa từ vựng. Trong một ngôn ngữ chuyên biệt miền (*Domain-Specific Language — DSL*), lexer là bước đầu tiên biến ký tự mà người dùng nhập thành đơn vị mà parser có thể xử lý.

Ví dụ, với DSL mô tả quy tắc:

~~~text
rule "gold-customer" {
    when customer.tier == "GOLD" and order.total >= 1000000
    then discount.percent = 10
}
~~~

Lexer có thể tạo chuỗi token khái quát:

~~~text
RULE
STRING("gold-customer")
LBRACE
WHEN
IDENTIFIER("customer")
DOT
IDENTIFIER("tier")
EQUAL_EQUAL
STRING("GOLD")
AND
IDENTIFIER("order")
DOT
IDENTIFIER("total")
GREATER_EQUAL
NUMBER("1000000")
THEN
IDENTIFIER("discount")
DOT
IDENTIFIER("percent")
EQUAL
NUMBER("10")
RBRACE
EOF
~~~

Parser nhận các token này rồi áp dụng grammar để xác định chúng tạo thành rule, điều kiện và phép gán như thế nào. Lexer không cần hiểu rằng customer là khách hàng hoặc discount là phần giảm giá; nhiệm vụ của nó là nhận diện token theo quy tắc từ vựng.

Một pipeline phổ biến:

~~~text
Văn bản nguồn
     |
     v
Đọc ký tự / giải mã encoding
     |
     v
Lexer: nhận diện token
     |
     v
Token stream + source positions
     |
     v
Parser: áp dụng grammar
     |
     v
CST / Parse tree
     |
     v
AST và phân tích ngữ nghĩa
~~~

Ranh giới giữa lexer và parser cần rõ ràng. Lexer nhận diện những đơn vị như identifier, number, string, operator, delimiter và keyword. Parser xác định các token đó có xuất hiện đúng cấu trúc hay không. Một chuỗi có thể là token hợp lệ nhưng vẫn nằm sai vị trí cú pháp.

## 2. Đầu vào và đầu ra của lexer

### 2.1. Đầu vào: source text

Đầu vào thường là văn bản DSL được đọc từ file, editor, request hoặc bộ nhớ. Trước khi quét token, hệ thống cần xác định:

- Encoding của file, thường là UTF-8 đối với DSL dạng văn bản.
- Cách xử lý byte order mark nếu có.
- Quy tắc xuống dòng: LF, CRLF hoặc CR.
- Cách biểu diễn ký tự Unicode.
- Có cho phép tab, ký tự điều khiển hoặc ký tự không in được không.
- Source file có thể gồm nhiều tài liệu hoặc nhiều phần được ghép lại không.

Lexer thường làm việc trên chuỗi ký tự đã được giải mã. Nếu encoding sai, lỗi có thể xảy ra trước giai đoạn tokenization; không nên báo những byte không giải mã được như thể đó là một token DSL thông thường.

### 2.2. Đầu ra: token

Một token thường chứa các thông tin:

| Trường | Ý nghĩa |
|---|---|
| Type / kind | Loại token, ví dụ IDENTIFIER, NUMBER, PLUS |
| Lexeme / text | Chuỗi ký tự gốc tạo nên token |
| Start offset | Vị trí ký tự bắt đầu |
| End offset | Vị trí kết thúc |
| Line / column | Dòng và cột để hiển thị diagnostics |
| Channel | Kênh token, ví dụ mặc định hoặc hidden |
| Value | Giá trị đã giải mã, nếu token có literal value |
| Flags | Thông tin bổ sung như token tổng hợp hoặc token lỗi |

Ví dụ token số có thể giữ cả văn bản gốc và giá trị đã phân tích:

~~~text
Token {
    type: NUMBER,
    lexeme: "1_000",
    value: 1000,
    startOffset: 12,
    endOffset: 17
}
~~~

Giữ lexeme hữu ích khi formatter, editor hoặc công cụ refactoring cần giữ nguyên cách người dùng viết. Giá trị đã phân tích hữu ích cho parser và các bước sau. Không phải token nào cũng cần trường value; identifier thường cần giữ tên gốc để name resolution thực hiện ở semantic analysis.

### 2.3. EOF và token tổng hợp

Token EOF (*end of file*) đánh dấu kết thúc đầu vào. Parser thường cần token này để xác nhận toàn bộ văn bản đã được tiêu thụ, thay vì chỉ phân tích được một phần đầu.

Một số lexer/parser cũng có token tổng hợp phục vụ phục hồi lỗi, ví dụ token dấu ngoặc đóng được chèn giả định. Token tổng hợp cần được đánh dấu để công cụ phân biệt nó với ký tự thật trong source.

## 3. Quy trình quét từ trái sang phải

Một lexer cơ bản quét văn bản từ đầu đến cuối. Tại mỗi vị trí, nó xác định token tiếp theo dựa trên ký tự hiện tại, các ký tự theo sau và trạng thái lexer.

Quy trình tổng quát:

1. Khởi tạo vị trí đọc tại đầu file và trạng thái ban đầu.
2. Bỏ qua hoặc ghi nhận whitespace và comment theo chính sách.
3. Nhìn ký tự tiếp theo để xác định nhóm token có thể bắt đầu tại vị trí đó.
4. Tiêu thụ chuỗi ký tự dài nhất phù hợp với quy tắc token.
5. Kiểm tra keyword hoặc phân loại token đặc biệt nếu cần.
6. Tạo token kèm lexeme, giá trị và source location.
7. Lặp lại cho đến hết đầu vào.
8. Phát token EOF.

Pseudocode giản lược:

~~~text
function lex(source):
    cursor = 0
    tokens = []

    while not atEnd(source, cursor):
        if isWhitespace(currentChar()):
            consumeWhitespace()
            continue

        if startsComment():
            consumeComment()
            continue

        token = scanNextToken()
        tokens.append(token)

    tokens.append(makeEOF())
    return tokens
~~~

Trong triển khai thực tế, `scanNextToken` phải xử lý các trường hợp nhập nhằng, chuỗi escape, comment nhiều dòng, chế độ lexer và lỗi ký tự. Vị trí dòng/cột cần được cập nhật ở mọi thao tác tiêu thụ ký tự.

## 4. Nhận diện token và quy tắc khớp

### 4.1. Token patterns

Mỗi loại token có một pattern. Với lexer dựa trên regex hoặc lexer generator, pattern thường được mô tả bằng biểu thức chính quy.

Ví dụ:

~~~text
IDENTIFIER = [A-Za-z_][A-Za-z0-9_]*
INTEGER    = [0-9]+
WHITESPACE = [ \t\r\n]+
~~~

Các pattern trên chỉ minh họa identifier ASCII và số nguyên thập phân đơn giản. Một DSL có thể hỗ trợ Unicode, dấu phân cách số, số thập phân, ký pháp khoa học hoặc tên trích dẫn với quy tắc khác.

### 4.2. Longest match

Khi nhiều pattern có thể khớp tại cùng vị trí, lexer thường dùng quy tắc *longest match* (khớp dài nhất): chọn chuỗi hợp lệ dài nhất.

Ví dụ, với token operator:

~~~text
=    EQUAL
==   EQUAL_EQUAL
>    GREATER
>=   GREATER_EQUAL
!    BANG
!=   NOT_EQUAL
~~~

Nếu lexer đọc ký tự đầu tiên là `=`, nó cần xem ký tự tiếp theo để quyết định token là `=` hay `==`. Tương tự, `>=` phải được nhận diện thành một token thay vì `>` rồi `=`.

Longest match cũng quan trọng với identifier và keyword. Nếu `if` là keyword, chuỗi `ifReady` thường phải là một identifier duy nhất, không được tách thành keyword `if` và identifier `Ready`.

### 4.3. Tie-breaking và thứ tự rule

Hai pattern có thể khớp cùng số ký tự. Khi đó lexer cần quy tắc ưu tiên, thường dựa trên thứ tự rule hoặc chính sách của lexer generator.

Ví dụ, cả keyword `when` và pattern identifier đều khớp chuỗi `when`. Có thể giải quyết bằng cách:

- Nhận diện identifier trước, sau đó tra bảng keyword.
- Đặt rule keyword với độ ưu tiên cao hơn identifier.
- Dùng contextual keyword ở parser nếu ngôn ngữ có yêu cầu.

Cần hiểu chính xác thứ tự ưu tiên của công cụ được dùng. Không nên giả định mọi lexer generator xử lý tie-breaking giống nhau.

### 4.4. Một số token có tiền tố chung

Với các toán tử như `<`, `<=`, `<<` và `<<=`, lexer có thể cần nhìn trước nhiều ký tự. Một DFA (*Deterministic Finite Automaton*) có thể biểu diễn quá trình chuyển trạng thái cho các tiền tố chung này.

Việc nhìn trước không nhất thiết làm lexer phức tạp nếu các pattern được thiết kế rõ. Tuy nhiên, nếu DSL có nhiều chuỗi đặc biệt chồng lấn, cần mô tả ưu tiên và viết test cho từng cặp tiền tố.

## 5. Phân loại token thường gặp trong DSL

Một DSL thường có các nhóm token sau:

| Nhóm | Ví dụ | Ghi chú |
|---|---|---|
| Keyword | rule, when, then, import | Từ dành riêng hoặc theo ngữ cảnh |
| Identifier | customer, orderTotal | Tên biến, thuộc tính, hàm, kiểu |
| Number literal | 42, 10.5 | Có thể gồm integer, decimal, exponent |
| String literal | "GOLD" | Có quy tắc escape và đóng chuỗi |
| Boolean / null | true, false, null | Có thể là keyword hoặc literal token |
| Operator | +, ==, >=, and | Dùng trong biểu thức |
| Delimiter | (, ), {, }, [, ], comma | Phân tách cấu trúc |
| Punctuation | ., :, ; | Dấu chấm, dấu hai chấm, dấu kết thúc |
| Comment | // note, /* note */ | Có thể bỏ qua hoặc giữ trivia |
| Whitespace | space, tab, newline | Có thể có ý nghĩa trong DSL |
| EOF | end of input | Kết thúc token stream |

Phân loại này là điểm khởi đầu. DSL cấu hình có thể dùng nhiều token dấu phân cách; DSL workflow có thể có token cho mũi tên và sự kiện; DSL truy vấn có thể có token riêng cho tên bảng, wildcard hoặc tham số.

## 6. Xử lý whitespace và newline

### 6.1. Whitespace không có ý nghĩa cú pháp

Trong nhiều ngôn ngữ, dấu cách và tab chỉ dùng để phân tách token. Lexer bỏ qua chúng:

~~~text
let total = 10
~~~

và:

~~~text
let    total=10
~~~

có thể tạo cùng token stream nếu DSL không quy định whitespace đặc biệt.

Dù bị bỏ qua, vị trí của whitespace vẫn có thể cần thiết cho formatter và diagnostics. Nếu cần bảo toàn comment hoặc khoảng trắng, hãy giữ token trivia hoặc lưu source text riêng.

### 6.2. Newline có ý nghĩa

Một số DSL dùng newline để kết thúc câu lệnh hoặc phân tách phần tử. Khi đó newline phải được phát thành token, ví dụ `NEWLINE`, thay vì bị bỏ qua.

~~~text
set customer = "An"
set active = true
~~~

Nếu mỗi dòng là một câu lệnh, parser có thể dựa vào NEWLINE để nhận biết ranh giới. Cần quy định cách xử lý dòng trống, dòng nối tiếp bằng ký tự continuation và newline bên trong dấu ngoặc.

### 6.3. Semicolon insertion

Một số ngôn ngữ tự động chèn dấu kết thúc câu lệnh khi gặp newline trong những điều kiện nhất định. Nếu DSL chọn cách này, quy tắc phải được định nghĩa rõ:

- Newline nào kết thúc statement?
- Newline sau operator có tiếp tục biểu thức không?
- Newline bên trong ngoặc có bị bỏ qua không?
- Comment cuối dòng có ảnh hưởng không?
- Có thể viết nhiều statement trên một dòng không?

Semicolon insertion có thể giúp tài liệu gọn, nhưng làm lexer/parser phụ thuộc ngữ cảnh nhiều hơn.

## 7. Nhận diện comment và trivia

Comment thường không tham gia ngữ nghĩa thực thi, nhưng có ích cho người viết và công cụ.

Một DSL có thể hỗ trợ:

~~~text
// Comment một dòng

/*
   Comment nhiều dòng
*/
~~~

Lexer cần biết comment bắt đầu và kết thúc ở đâu. Với comment nhiều dòng, cần xác định comment lồng nhau có được hỗ trợ không. Nếu không, ký hiệu mở comment xuất hiện bên trong comment thường không mở một comment mới.

Có ba chiến lược phổ biến:

1. Bỏ comment hoàn toàn khỏi token stream.
2. Phát comment trên hidden channel để parser bỏ qua nhưng tool vẫn truy cập được.
3. Giữ comment và whitespace dưới dạng trivia gắn với token hoặc node.

Nếu DSL có tài liệu hóa ngay trong source, formatter hoặc refactoring, không nên bỏ comment trước khi xác định nhu cầu của các công cụ đó.

## 8. Xử lý identifier và keyword

### 8.1. Nhận diện identifier

Một identifier thường bắt đầu bằng chữ cái hoặc dấu gạch dưới, sau đó có thể gồm chữ cái, chữ số và dấu gạch dưới:

~~~text
IDENTIFIER = [A-Za-z_][A-Za-z0-9_]*
~~~

Ví dụ hợp lệ theo quy tắc này:

~~~text
customer
_order
order2
discount_rate
~~~

Ví dụ không hợp lệ:

~~~text
2order
customer name
order-total
~~~

Các tên có dấu gạch nối hoặc khoảng trắng có thể được hỗ trợ bằng quoted identifier. Nếu cho phép Unicode, cần dùng quy tắc dựa trên thuộc tính Unicode phù hợp thay vì chỉ mở rộng một vài dải mã tùy tiện.

### 8.2. Keyword table

Sau khi quét một identifier, lexer có thể tra cứu lexeme trong bảng keyword:

~~~text
KEYWORDS = {
    "rule": RULE,
    "when": WHEN,
    "then": THEN,
    "and": AND,
    "or": OR
}
~~~

Nếu tên nằm trong bảng, phát token keyword; nếu không, phát token IDENTIFIER.

Cách này giúp keyword và identifier dùng chung quy tắc ký tự, đồng thời tránh việc lexer cắt một tên dài thành keyword cộng phần còn lại. Tuy nhiên, với contextual keyword, parser có thể cần quyết định dựa trên vị trí cú pháp thay vì lexer luôn phát token keyword.

### 8.3. Case sensitivity

Nếu DSL phân biệt hoa thường, `Rule` và `rule` có thể là hai token khác nhau. Nếu không phân biệt, lexer cần chuẩn hóa để tra keyword, nhưng vẫn có thể giữ lexeme gốc cho hiển thị.

Chính sách case phải nhất quán giữa lexer, symbol table, import và công cụ rename.

## 9. Xử lý literal

### 9.1. Number literal

Lexer cần xác định cú pháp số, ví dụ:

~~~text
INTEGER  = [0-9]+
DECIMAL  = [0-9]+ "." [0-9]+
EXPONENT = [0-9]+ ("." [0-9]+)? [eE] [+-]? [0-9]+
~~~

Một DSL có thể hỗ trợ dấu phân cách chữ số như `1_000` hoặc hậu tố đơn vị như `5s`, `10MB`. Khi thiết kế, cần tránh nhập nhằng giữa dấu chấm thập phân và dấu chấm truy cập thuộc tính.

Cũng cần quyết định dấu âm có thuộc token số hay là token unary minus. Nhiều lexer phát `-` riêng, để parser xử lý dấu âm như một toán tử một ngôi. Cách này giúp precedence được mô tả nhất quán.

### 9.2. String literal

String literal thường bắt đầu và kết thúc bằng dấu nháy:

~~~text
"hello"
'hello'
~~~

Nếu cho phép escape:

~~~text
"line 1\nline 2"
"She said: \"Hello\""
~~~

Lexer phải xác định:

- Ký tự mở và đóng chuỗi.
- Escape sequence được hỗ trợ.
- Có cho phép newline bên trong string không.
- Cách xử lý dấu nháy chưa đóng.
- Cách xử lý escape không hợp lệ.
- Giá trị token là lexeme gốc hay chuỗi đã giải mã.

Nên lưu source span và có thể lưu cả lexeme lẫn decoded value để thông báo lỗi và formatter hoạt động đúng.

### 9.3. Boolean, null và literal miền

Các giá trị như `true`, `false` và `null` có thể được phát thành token riêng. DSL cũng có thể có literal miền:

~~~text
100 VND
5 minutes
2026-11-15
~~~

Có hai hướng thiết kế:

- Lexer nhận toàn bộ giá trị kèm đơn vị thành một token chuyên biệt.
- Lexer phát các token cơ bản rồi parser ghép chúng thành literal miền.

Hướng thứ hai thường linh hoạt hơn nếu đơn vị có grammar phong phú. Ngữ nghĩa kiểu và chuyển đổi đơn vị thường thuộc các bước sau lexer.

## 10. Lexer state và lexical modes

Không phải vị trí nào trong source cũng dùng cùng một tập quy tắc token. Lexer có thể có trạng thái hoặc mode để thay đổi cách nhận diện.

### 10.1. String mode

Khi gặp dấu mở string, lexer chuyển sang chế độ đọc string cho đến khi gặp dấu đóng hợp lệ. Trong mode này, ký hiệu như dấu ngoặc hoặc từ khóa thường chỉ là nội dung chuỗi.

Ví dụ:

~~~text
message = "if order.total > 0 then"
~~~

Từ `if` bên trong chuỗi không được phát thành keyword.

### 10.2. Comment mode

Sau khi nhận diện ký hiệu mở comment nhiều dòng, lexer chuyển sang mode comment và tiếp tục cho đến ký hiệu đóng. Nếu hết file trước khi comment đóng, phát diagnostic phù hợp.

### 10.3. Template và interpolation

Một DSL template có thể cho phép nhúng biểu thức trong chuỗi:

~~~text
"Hello, <%= customer.name %>"
~~~

Lexer cần chuyển qua lại giữa text mode và expression mode. Trong phần text, ký tự DSL thông thường được xem là nội dung; bên trong interpolation, lexer nhận diện token theo grammar biểu thức.

### 10.4. Mode stack

Với cấu trúc lồng nhau, lexer có thể dùng stack các mode:

~~~text
DEFAULT
  -> STRING
      -> INTERPOLATION
          -> NESTED_STRING
      <- INTERPOLATION
  <- STRING
<- DEFAULT
~~~

Stack giúp khôi phục đúng mode trước đó khi kết thúc một cấu trúc lồng. Cần giới hạn độ sâu nếu input không đáng tin cậy có thể tạo nesting rất lớn.

## 11. Lookahead và thuật toán lexer

### 11.1. Lookahead

Lookahead là việc xem một hoặc nhiều ký tự tiếp theo mà chưa tiêu thụ chúng, nhằm chọn token phù hợp.

Ví dụ với dấu `=`:

- Nếu ký tự tiếp theo không phải `=`, phát EQUAL.
- Nếu ký tự tiếp theo là `=`, phát EQUAL_EQUAL.

Với toán tử dài hơn như `>>=`, lexer có thể cần nhìn trước nhiều ký tự hoặc dùng automaton được sinh từ token patterns.

### 11.2. Finite automata

Lexer có thể được triển khai bằng finite automata:

- NFA (*Nondeterministic Finite Automaton*) mô tả nhiều khả năng chuyển trạng thái.
- DFA (*Deterministic Finite Automaton*) có một trạng thái tiếp theo duy nhất cho mỗi trạng thái và ký tự đầu vào.
- Regex có thể được chuyển thành automaton để quét token hiệu quả.

Lexer generator thường thực hiện phần lớn công việc này từ các pattern do người thiết kế khai báo. Với lexer viết tay, một switch theo ký tự đầu và các hàm scan chuyên biệt có thể dễ đọc hơn cho DSL nhỏ.

### 11.3. Lexer viết tay

Một lexer viết tay có thể có cấu trúc:

~~~java
Token nextToken() {
    skipIgnoredInput();

    if (isAtEnd()) {
        return eofToken();
    }

    char c = peek();

    if (isIdentifierStart(c)) return scanIdentifier();
    if (isDigit(c)) return scanNumber();

    return switch (c) {
        case '+' -> single(PLUS);
        case '-' -> single(MINUS);
        case '{' -> single(LBRACE);
        case '}' -> single(RBRACE);
        case '=' -> match('=') ? token(EQUAL_EQUAL) : token(EQUAL);
        case '"' -> scanString();
        default -> errorToken(c);
    };
}
~~~

Đây là pseudocode Java rút gọn. Một triển khai thật cần quản lý offset, dòng/cột, CRLF, Unicode, comment, mode và diagnostics. Việc tách `scanIdentifier`, `scanNumber` và `scanString` giúp mỗi loại token có quy tắc riêng dễ hiểu.

### 11.4. Lexer generator

Với grammar lớn hoặc nhiều mode, lexer generator có thể giảm mã thủ công. ANTLR, Flex và các công cụ tương tự cho phép mô tả token patterns rồi sinh mã quét.

Ví dụ grammar lexer giản lược kiểu ANTLR:

~~~antlr
RULE   : 'rule';
WHEN   : 'when';
THEN   : 'then';
AND    : 'and';

EQUAL_EQUAL : '==';
EQUAL       : '=';
GREATER_EQUAL : '>=';
GREATER       : '>';

NUMBER
    : [0-9]+ ('.' [0-9]+)?
    ;

IDENTIFIER
    : [a-zA-Z_] [a-zA-Z_0-9]*
    ;

STRING
    : '"' ('\\' . | ~["\\\r\n])* '"'
    ;

LINE_COMMENT
    : '//' ~[\r\n]* -> skip
    ;

WS
    : [ \t\r\n]+ -> skip
    ;
~~~

Đây là ví dụ minh họa, không phải grammar sản phẩm hoàn chỉnh. Trong ANTLR, thứ tự rule, longest match và các lệnh channel/skip ảnh hưởng token stream; cần tuân theo quy tắc của phiên bản công cụ đang dùng.

## 12. Source locations và Unicode

### 12.1. Offset, line và column

Mỗi token nên có vị trí bắt đầu và kết thúc. Có thể lưu offset theo byte, UTF-16 code unit hoặc Unicode code point, tùy hệ sinh thái và giao thức editor.

Nếu editor dùng UTF-16 nhưng lexer đếm Unicode code point, vị trí cần được chuyển đổi đúng khi gửi diagnostics. Một ký tự ngoài BMP có thể chiếm hai UTF-16 code units nhưng một Unicode code point.

### 12.2. Dòng và cột

Khi tiêu thụ newline, lexer cập nhật line counter và đặt lại column. Với CRLF, cần tránh đếm thành hai dòng. Tab có thể được tính là một code unit hoặc một tab stop tùy quy ước hiển thị; đặc tả và editor integration cần thống nhất.

### 12.3. Unicode identifiers

Nếu DSL hỗ trợ identifier Unicode, nên dựa trên thuộc tính như `XID_Start` và `XID_Continue`, đồng thời xác định chính sách normalization. Cần chú ý ký tự đồng hình và ký tự điều khiển hướng văn bản để tránh tên trông giống nhau nhưng khác code point.

Lexer thường nên giữ lexeme nguyên bản. Việc chuẩn hóa tên để so sánh có thể thực hiện tại bước symbol resolution, theo chính sách ngôn ngữ đã công bố.

## 13. Xử lý lỗi từ vựng và phục hồi

### 13.1. Các lỗi phổ biến

- Ký tự không thuộc bất kỳ token pattern nào.
- String literal chưa đóng.
- Escape sequence không hợp lệ.
- Comment nhiều dòng chưa đóng.
- Number literal sai định dạng.
- Identifier vượt giới hạn độ dài.
- Ký tự điều khiển không được phép.
- Token không hợp lệ trong lexical mode hiện tại.

### 13.2. Diagnostic

Một lexical diagnostic nên chỉ ra:

- File và vị trí lỗi.
- Lexeme hoặc ký tự gây lỗi nếu có thể hiển thị an toàn.
- Mã lỗi ổn định.
- Nguyên nhân.
- Gợi ý sửa nếu có thể xác định chắc chắn.

Ví dụ:

~~~text
rules.dsl:7:19: error LEX-STRING-001
Unterminated string literal.
Add a closing double quote before the end of the line.
~~~

Không nên đưa toàn bộ dữ liệu nhạy cảm của chuỗi vào log hoặc diagnostic nếu source có thể chứa bí mật.

### 13.3. Recovery strategy

Lexer có thể chọn:

- Dừng ngay khi gặp lỗi nghiêm trọng.
- Bỏ qua ký tự lỗi và tiếp tục quét.
- Phát một token lỗi để parser tiếp tục.
- Chuyển sang trạng thái đồng bộ phù hợp, ví dụ cuối dòng hoặc dấu phân cách.

Với CLI compiler, dừng sớm có thể phù hợp. Với editor, tiếp tục quét thường hữu ích hơn để hiển thị nhiều lỗi và giữ các tính năng như completion hoạt động khi người dùng đang gõ dở.

Phục hồi phải tránh tạo một chuỗi token gây hiểu sai nghiêm trọng. Nếu lexer bỏ qua ký tự, cần phát diagnostic để người dùng biết văn bản đã bị bỏ qua khi phân tích.

## 14. Token stream và tích hợp với parser

Lexer thường cung cấp token stream cho parser thay vì tạo toàn bộ parse tree. Token stream có thể hỗ trợ:

- Lấy token tiếp theo.
- Lookahead một hoặc nhiều token.
- Lưu token đã đọc để parser backtrack nếu thuật toán cần.
- Truy cập hidden-channel tokens.
- Đánh dấu vị trí để quay lại.
- Đọc source span và lexeme.

Parser có thể cần token lookahead để chọn production. Tuy nhiên, lexer không nên tự giải quyết các quyết định thuộc grammar nếu không có yêu cầu lexical đặc biệt. Ví dụ, lexer có thể nhận diện IDENTIFIER, còn parser quyết định identifier đó là tên biến, tên hàm hay tên kiểu dựa trên vị trí.

Một số DSL có quy tắc từ vựng phụ thuộc cú pháp, chẳng hạn phân biệt tên kiểu với tên biến hoặc tự động chèn dấu kết thúc câu lệnh. Khi đó cần mô tả rõ phần nào thuộc lexer, phần nào thuộc parser hoặc bước token filter giữa hai thành phần.

## 15. Incremental lexing cho editor

Trong editor, người dùng thay đổi văn bản liên tục. Quét lại toàn bộ file sau mỗi phím gõ có thể tốn kém với tài liệu lớn.

Incremental lexer chỉ quét lại vùng bị ảnh hưởng và phần tiếp theo cho đến khi trạng thái lexical đồng bộ trở lại. Để làm được điều này, hệ thống cần:

- Lưu trạng thái lexer tại các điểm kiểm tra.
- Biết token nào bị ảnh hưởng bởi vùng sửa.
- Xử lý thay đổi có thể làm mất hiệu lực token ở phía sau, ví dụ thêm dấu mở string.
- Cập nhật source positions sau khi độ dài văn bản thay đổi.
- Đồng bộ token stream với parser incremental nếu có.

Tree-sitter cung cấp parser incremental dựa trên cây cú pháp cụ thể; trong kiến trúc đó, quá trình phân tích và cập nhật lexical/syntax được tích hợp theo mô hình của công cụ. Không nên mặc định mọi lexer truyền thống đều hỗ trợ incremental scanning.

## 16. Hiệu năng và giới hạn tài nguyên

Lexer thường tuyến tính theo kích thước đầu vào với các pattern được thiết kế phù hợp, nhưng một số pattern hoặc chiến lược backtracking có thể tạo hành vi chậm bất thường.

Các điểm cần lưu ý:

- Tránh regex có backtracking bùng nổ khi đầu vào không đáng tin cậy.
- Đặt giới hạn hợp lý cho độ dài string và identifier nếu miền cho phép.
- Tránh sao chép substring quá nhiều lần; có thể lưu offset vào source buffer.
- Cân nhắc streaming với file lớn.
- Giới hạn nesting của lexical mode hoặc interpolation.
- Xử lý input rỗng và input rất lớn.
- Không ghi toàn bộ source nhạy cảm vào log khi có lỗi.
- Đo thời gian quét trên dữ liệu đại diện và trường hợp xấu.

Nếu lexer được dùng trong server nhận DSL từ người dùng, thời gian và bộ nhớ tiêu thụ cũng là một phần của bề mặt tấn công. Giới hạn cần được áp dụng trước khi parser và runtime bắt đầu xử lý.

## 17. Kiểm thử lexer

Lexer cần được kiểm thử độc lập với parser. Mỗi test nên xác định source text và chuỗi token mong đợi, gồm loại, lexeme và vị trí nếu vị trí là một phần của hợp đồng.

### 17.1. Kiểm thử token cơ bản

~~~text
Input:
total = 42

Expected:
IDENTIFIER("total")
EQUAL("=")
NUMBER("42")
EOF
~~~

### 17.2. Kiểm thử longest match

~~~text
Input:
a == b >= c != d

Expected:
IDENTIFIER("a")
EQUAL_EQUAL("==")
IDENTIFIER("b")
GREATER_EQUAL(">=")
IDENTIFIER("c")
NOT_EQUAL("!=")
IDENTIFIER("d")
EOF
~~~

### 17.3. Kiểm thử keyword và identifier

~~~text
Input:
if ifReady IF

Expected when keywords are case-sensitive:
IF("if")
IDENTIFIER("ifReady")
IDENTIFIER("IF")
EOF
~~~

Kết quả phải khớp chính sách case sensitivity và keyword của DSL.

### 17.4. Kiểm thử literal và escape

Nên có test cho:

- String rỗng.
- String có escape quote và backslash.
- Escape không hợp lệ.
- String chưa đóng.
- Số nguyên, số thập phân và exponent.
- Số có dấu phân cách.
- Giá trị vượt giới hạn biểu diễn.
- Literal miền như ngày, thời lượng và tiền tệ.

### 17.5. Kiểm thử whitespace, comment và newline

Kiểm tra space, tab, LF, CRLF, dòng trống, comment cuối dòng, comment nhiều dòng và comment chưa đóng. Nếu newline có ý nghĩa, cần xác nhận token NEWLINE được phát đúng.

### 17.6. Property-based và fuzz testing

Có thể sinh chuỗi ngẫu nhiên hoặc chuỗi theo grammar để kiểm tra lexer không crash, không lặp vô hạn và luôn tiến vị trí đọc hoặc kết thúc. Fuzzing hữu ích cho chuỗi escape, Unicode, comment lồng nhau và token dài bất thường.

Một test hữu ích khác là bảo đảm token span không chồng lấn sai và lexeme của token thường khớp đúng đoạn source tương ứng.

## 18. Quy trình xây dựng lexer cho DSL

Một quy trình triển khai có thể gồm:

1. **Liệt kê token:** keyword, identifier, literal, operator, delimiter, comment và whitespace.
2. **Viết lexical specification:** định nghĩa pattern, ưu tiên, longest match và case sensitivity.
3. **Xác định encoding và Unicode:** quy định decoding, normalization và source coordinate.
4. **Chọn cách triển khai:** lexer viết tay hay lexer generator dựa trên quy mô grammar và yêu cầu tooling.
5. **Thiết kế lexical modes:** string, comment, template, interpolation và cấu trúc lồng nhau.
6. **Định nghĩa token model:** type, lexeme, value, source span, channel và flags.
7. **Thiết kế lỗi và recovery:** mã lỗi, vị trí, cách tiếp tục quét và giới hạn.
8. **Tích hợp parser:** token stream, lookahead, hidden tokens và EOF.
9. **Tích hợp editor:** trivia, diagnostics, incremental lexing và mapping vị trí.
10. **Viết test:** token cơ bản, tiền tố chung, literal, Unicode, lỗi, input lớn và fuzz cases.
11. **Đo hiệu năng:** xác nhận thời gian và bộ nhớ phù hợp với kích thước tài liệu mục tiêu.

Một lexical specification rõ ràng giúp lexer viết tay, lexer generator và các công cụ editor nhận diện cùng một ngôn ngữ.

## 19. Những lỗi thiết kế thường gặp

- **Để lexer làm việc của parser:** cố xác định toàn bộ cấu trúc câu lệnh ngay khi quét ký tự khiến lexer phụ thuộc grammar quá mức.
- **Không áp dụng longest match đúng:** token `>=` bị tách thành `>` và `=`.
- **Keyword cắt identifier dài:** `ifReady` bị phân loại sai thành `IF` cộng `Ready`.
- **Bỏ comment quá sớm:** formatter và refactoring mất thông tin người dùng cần giữ.
- **Không quy định newline:** cùng một tài liệu được phân tích khác nhau tùy whitespace hoặc hệ điều hành.
- **Không giữ source positions:** diagnostics không trỏ đúng vị trí.
- **Xử lý Unicode không nhất quán:** lexer và symbol resolution xem cùng tên theo các quy tắc khác nhau.
- **Không kiểm tra string chưa đóng:** parser nhận token stream không thể giải thích rõ lỗi nguồn.
- **Dùng regex thiếu kiểm soát:** input bất thường có thể khiến lexer chậm đáng kể.
- **Không kiểm thử recovery:** một ký tự sai làm mất toàn bộ diagnostics ở phần còn lại của tài liệu.

## 20. Kết luận

Quy trình lexer biến văn bản DSL thành token stream mà parser có thể sử dụng. Nó gồm đọc và giải mã source, quét ký tự, áp dụng token patterns, giải quyết longest match và ưu tiên, xử lý keyword/literal/comment/whitespace, lưu source location, phát hiện lỗi và cung cấp token cho parser.

Một lexer tốt cần có lexical specification rõ ràng, token model nhất quán, quy tắc Unicode và newline xác định, cơ chế phục hồi phù hợp với CLI hoặc editor, cùng bộ kiểm thử bao phủ cả đầu vào hợp lệ và bất thường. Khi ranh giới lexer-parser được thiết kế đúng, các bước parser, semantic analysis và công cụ phát triển DSL có thể dựa trên token stream ổn định và dễ bảo trì.


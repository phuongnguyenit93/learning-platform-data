# Kiểm thử lexer trong DSL

Lexer (bộ phân tích từ vựng) là thành phần đầu tiên trong pipeline xử lý ngôn ngữ. Nó đọc source text và chia chuỗi ký tự thành token như identifier, keyword, literal, operator, dấu phân cách và comment. Parser dùng token stream để xây dựng cấu trúc cú pháp. Nếu lexer phân loại sai ký tự hoặc cắt token ở vị trí không đúng, các bước phía sau có thể nhận một chương trình khác với nội dung người viết dự định.

**Kiểm thử lexer** là xác minh rằng lexer biến source text thành token stream đúng theo đặc tả từ vựng của DSL, đồng thời xử lý đúng lexeme, literal value, source span, trivia, Unicode, lỗi và phục hồi. Một test tốt không chỉ kiểm tra token type mà còn xác nhận vị trí, thứ tự, channel và hành vi tại ranh giới của input.

Trong DSL, lexer có thể có quy tắc riêng cho keyword, identifier, số có đơn vị, chuỗi, comment, toán tử nhiều ký tự hoặc chế độ nội suy. Vì vậy, lexer cần có lexical grammar rõ ràng và bộ kiểm thử độc lập trước khi kiểm thử parser hay toàn bộ ngôn ngữ.

## 1. Lexer trong pipeline của DSL

### 1.1. Vai trò

Ví dụ source:

~~~text
rule FreeShipping {
    when order.total >= 1000000 VND
    then shippingFee = 0 VND
}
~~~

Token stream khái niệm:

~~~text
KEYWORD_RULE
IDENTIFIER("FreeShipping")
LBRACE
KEYWORD_WHEN
IDENTIFIER("order")
DOT
IDENTIFIER("total")
GREATER_EQUAL
INTEGER_LITERAL(1000000)
IDENTIFIER("VND")
KEYWORD_THEN
IDENTIFIER("shippingFee")
EQUAL
INTEGER_LITERAL(0)
IDENTIFIER("VND")
RBRACE
EOF
~~~

Lexer không cần hiểu ý nghĩa nghiệp vụ của FreeShipping. Nó chỉ nhận diện các đơn vị từ vựng.

### 1.2. Lexer và parser

Lexer nhận diện token; parser xác định cấu trúc. Lexer biết >= là một token so sánh, còn parser biết token đó xuất hiện trong biểu thức hợp lệ hay không. Semantic analyzer tiếp tục kiểm tra biến, kiểu và ý nghĩa.

Nếu lexer tách >= thành > và =, parser có thể báo lỗi dù source đúng theo đặc tả. Kiểm thử lexer trực tiếp giúp khoanh vùng lỗi sớm.

### 1.3. Token contract

Một token thường lưu:
- Token type.
- Lexeme: đoạn source gốc.
- Literal value đã giải mã nếu có.
- Start và end position.
- Source file hoặc document ID.
- Channel hoặc trivia flag.
- Diagnostic nếu token lỗi.

Ví dụ:

~~~text
Token {
    type: INTEGER_LITERAL
    lexeme: "1000"
    value: 1000
    span: [24, 28)
}
~~~

### 1.4. EOF

Nhiều lexer phát token EOF để parser biết source đã kết thúc. Cần xác định EOF được phát đúng một lần, vị trí của nó và cách xử lý source rỗng hoặc source kết thúc ngay sau token.

### 1.5. Lexeme và literal value

Lexeme là nội dung nguyên bản. Literal value là giá trị sau khi xử lý escape hoặc chuyển đổi. Với chuỗi có escape newline, lexeme chứa ký tự backslash và chữ n, còn literal value chứa newline thật. Test nên kiểm tra cả hai nếu token model lưu cả hai.

## 2. Đặc tả từ vựng và lexical grammar

### 2.1. Lexical grammar

Lexical grammar mô tả cách nhận diện token bằng character class, regular expression hoặc quy tắc scanner.

~~~text
IDENTIFIER = LETTER (LETTER | DIGIT | "_")*
INTEGER    = DIGIT+
DECIMAL    = DIGIT+ "." DIGIT+
~~~

Đây là ví dụ đơn giản. DSL thực tế cần quy định Unicode, dấu gạch nối, suffix, dấu chấm và cách phân tách.

### 2.2. Token type

Các token thường gặp:
- IDENTIFIER.
- KEYWORD_RULE.
- INTEGER_LITERAL.
- DECIMAL_LITERAL.
- STRING_LITERAL.
- PLUS.
- GREATER_EQUAL.
- LEFT_PAREN.
- RIGHT_PAREN.
- NEWLINE.
- EOF.
- ERROR.

Token type cần có tên ổn định để parser, formatter và test harness cùng sử dụng.

### 2.3. Token span

Source span thường dùng khoảng nửa mở [start, end), trong đó end không thuộc token. Quy ước này giúp tính độ dài bằng end - start và ghép các span liền nhau.

Phải xác định offset tính theo byte UTF-8, UTF-16 code unit hay Unicode code point. Editor có thể dùng UTF-16, trong khi lexer đọc UTF-8. Không thống nhất sẽ làm diagnostic lệch vị trí.

### 2.4. Trivia và channel

Whitespace và comment có thể bị bỏ qua, được phát trên hidden channel hoặc được lưu làm trivia gắn với token. Formatter và refactoring thường cần giữ comment và khoảng trắng, vì vậy test phải theo đúng chính sách lưu trữ.

### 2.5. Token equality

Hai token có thể cùng type và value nhưng khác lexeme hoặc span. Assertion phải kiểm tra những thuộc tính thuộc contract, tránh so sánh quá lỏng khiến lỗi vị trí không bị phát hiện.

## 3. Thiết kế bộ kiểm thử lexer

### 3.1. Test theo token table

| Input | Token mong đợi |
|---|---|
| alpha | IDENTIFIER("alpha") |
| 42 | INTEGER_LITERAL(42) |
| >= | GREATER_EQUAL |
| "hi" | STRING_LITERAL("hi") |
| { | LBRACE |

Mỗi trường hợp nên chạy độc lập để xác định chính xác quy tắc bị lỗi.

### 3.2. Test token stream

Kiểm tra cả chuỗi token từ source nhiều token, gồm whitespace và comment. Test này xác nhận thứ tự, boundary và việc lexer không bỏ hoặc lặp token.

### 3.3. Test literal decoding

Với string và number, kiểm tra lexeme, decoded value, kiểu, precision, source span và diagnostic nếu sai format.

### 3.4. Test lỗi

Input sai cần tạo diagnostic xác định, không crash, không treo và không âm thầm bỏ ký tự nếu đặc tả yêu cầu báo lỗi.

### 3.5. Test độc lập với parser

Phần lớn test lexer nên gọi lexer trực tiếp. Nếu chỉ kiểm tra qua parser, lỗi tokenization có thể bị nhầm thành lỗi cú pháp.

### 3.6. Test deterministic

Chạy cùng input nhiều lần và xác nhận token stream giống nhau. Điều này giúp phát hiện state leak trong lexer tái sử dụng buffer hoặc object.

## 4. Character class

### 4.1. Chữ cái và Unicode

Xác định identifier có hỗ trợ ASCII, chữ Unicode, combining mark và chữ có dấu hay không. Không nên mặc định mọi ký tự ngoài ASCII đều không hợp lệ nếu DSL cần hỗ trợ identifier quốc tế.

### 4.2. Chữ số

Quy định số trong literal chỉ dùng ASCII 0-9 hay chấp nhận Unicode decimal digit. Nếu chỉ hỗ trợ ASCII, chữ số Unicode tương tự cần bị từ chối rõ ràng.

### 4.3. Underscore và dấu nối

Identifier có thể cho phép underscore hoặc hyphen. Nhưng hyphen cũng có thể là toán tử trừ, vì vậy quy tắc bắt đầu và kết thúc identifier phải rõ.

### 4.4. Dấu chấm

Dấu chấm có thể biểu diễn member access, decimal separator hoặc range operator. Test các trường hợp như a.b, 12.5 và 1..10 để xác nhận quy tắc phân tách.

### 4.5. Whitespace

Xác định space, tab, CR, LF và Unicode separator nào được chấp nhận. Nếu newline có ý nghĩa cú pháp, lexer cần phát NEWLINE hoặc giữ line break trong token stream.

### 4.6. Control characters

Ký tự điều khiển không được phép cần tạo diagnostic. Không để chúng làm sai log, terminal hoặc editor output.

## 5. Identifier và keyword

### 5.1. Identifier

Identifier thường bắt đầu bằng chữ cái hoặc underscore và tiếp tục bằng chữ, số hoặc underscore. Grammar cụ thể cần xác định các ký tự được phép.

### 5.2. Keyword boundary

Nếu rule là keyword thì ruleName thường phải là một identifier duy nhất, không bị tách thành KEYWORD_RULE và IDENTIFIER(Name). Test keyword, identifier có prefix và identifier có suffix.

### 5.3. Case sensitivity

Nếu DSL phân biệt hoa thường, Rule và RULE khác rule. Nếu không phân biệt, test các biến thể và xác nhận token type giống nhau. Chính sách của keyword và identifier có thể khác nhau.

### 5.4. Contextual keyword

Contextual keyword chỉ có nghĩa đặc biệt ở một số vị trí. Lexer có thể luôn phát IDENTIFIER để parser nhận diện theo ngữ cảnh, hoặc phát token riêng nhưng cho phép dùng như identifier ở vị trí khác. Test cần bám sát thiết kế.

### 5.5. Reserved keyword và tương thích

Khi thêm keyword, identifier cũ cùng tên có thể trở nên không hợp lệ. Cần test compatibility và cách escape identifier nếu DSL hỗ trợ.

### 5.6. Escaped identifier

Nếu identifier có thể đặt trong dấu quote hoặc backtick, test delimiter, escape, Unicode, newline và tên semantic sau khi giải mã.

## 6. Unicode và vị trí nguồn

### 6.1. Code point và code unit

Unicode code point là đơn vị mã trừu tượng. Một ký tự có thể chiếm nhiều byte UTF-8 hoặc hai UTF-16 code unit. Source span phải dùng đơn vị được công bố.

### 6.2. UTF-8 và UTF-16

Nếu lexer đọc byte UTF-8 nhưng editor cần UTF-16 offset, cần mapping. Test token nằm sau ký tự ngoài Basic Multilingual Plane để phát hiện lệch offset.

### 6.3. Unicode normalization

Hai chuỗi có thể hiển thị giống nhau nhưng có biểu diễn code point khác nhau, ví dụ ký tự dựng sẵn và chữ cái cộng combining mark. DSL cần quyết định có normalize identifier hay so sánh chính xác.

### 6.4. Combining mark và homoglyph

Nếu cho phép combining mark trong identifier, test vị trí và quy tắc ghép. Ký tự nhìn giống chữ Latin nhưng thuộc script khác có thể gây nhầm lẫn; hệ thống có thể giới hạn script hoặc cảnh báo.

### 6.5. Line ending

Kiểm tra LF, CRLF, CR nếu được hỗ trợ, file không có newline cuối và file chỉ có newline. CRLF thường là một line break dù gồm hai code unit.

### 6.6. Tab và column

Offset ký tự và cột hiển thị khác nhau khi có tab. Lexer lưu offset chính xác; diagnostic renderer có thể tính cột hiển thị theo tab width.

### 6.7. Source span rỗng

EOF hoặc marker chèn có thể có span zero-width. Test xác nhận start bằng end và editor đặt diagnostic đúng vị trí.

## 7. Numeric literal

### 7.1. Integer

Test zero, số dương, leading zero, số rất lớn, underscore phân nhóm nếu có và giá trị ở cuối file.

### 7.2. Decimal

Test 0.5, 12.0, decimal thiếu phần nguyên hoặc phần thập phân nếu grammar cho phép, nhiều dấu chấm và precision vượt giới hạn.

### 7.3. Exponent

Nếu hỗ trợ scientific notation, kiểm tra 1e3, 2.5E-4, exponent thiếu chữ số, dấu exponent và overflow.

### 7.4. Hexadecimal và binary

Nếu DSL hỗ trợ 0xFF hoặc 0b1010, test prefix hoa/thường, chữ số sai, prefix không có chữ số và underscore không đúng vị trí.

### 7.5. Dấu âm

Một số lexer phát MINUS riêng rồi parser áp dụng unary operator. Test -1, a-1 và a--1 để xác nhận tokenization.

### 7.6. Unit suffix

DSL có thể hỗ trợ 1000 VND, 12.5 km hoặc 30 ms. Xác định suffix là token riêng, keyword hay một phần literal. Test whitespace, case, suffix gần giống và đơn vị không biết.

### 7.7. Overflow và locale

Phân biệt lỗi lexical với lỗi chuyển đổi số vượt miền. Numeric source nên dùng format ổn định, không phụ thuộc locale máy; test chạy dưới locale khác nhau để đảm bảo kết quả không đổi.

## 8. String literal và escape

### 8.1. Quote

Nếu DSL hỗ trợ cả quote đơn và kép, xác định semantics. Nếu chỉ hỗ trợ một loại, quote còn lại phải được xử lý theo grammar.

### 8.2. Escape sequence

Các escape phổ biến gồm newline, carriage return, tab, backslash, quote và Unicode escape. Test lexeme gốc và literal value đã giải mã.

### 8.3. Escape không hợp lệ

Escape không được hỗ trợ hoặc Unicode escape thiếu chữ số cần tạo diagnostic. Không âm thầm xóa backslash hoặc thay ký tự nếu đặc tả không quy định.

### 8.4. String chưa đóng

~~~text
"unfinished
~~~

Lexer cần báo lỗi tại vị trí hợp lý và có chiến lược recovery. Không được đọc vô hạn hoặc treo chờ input trong file hữu hạn.

### 8.5. Newline và multiline string

Nếu string thường không cho newline, test lexer từ chối. Nếu hỗ trợ multiline, định nghĩa delimiter, CRLF và indentation stripping.

### 8.6. Raw string

Raw string không xử lý escape theo cách thông thường. Test prefix, delimiter và dấu quote bên trong.

### 8.7. Triple-quoted string

Test delimiter kết thúc, chuỗi chứa một hoặc hai quote liên tiếp, indentation và EOF khi chưa đóng.

### 8.8. String interpolation

Ví dụ:

~~~text
"Hello, {{ customer.name }}"
~~~

Lexer có thể chuyển qua các mode: string start, string content, interpolation start, expression, interpolation end và string continuation. Test interpolation lồng, brace lồng, string bên trong expression và escape delimiter.

## 9. Operator và dấu phân cách

### 9.1. Operator một ký tự

Ví dụ +, -, *, /, %, =, <, >, !, & và |. Mỗi operator cần token type và source span chính xác.

### 9.2. Operator nhiều ký tự

Ví dụ ==, !=, <=, >=, &&, ||, -> và =>. Lexer thường dùng maximal munch: chọn token hợp lệ dài nhất tại vị trí hiện tại.

### 9.3. Prefix overlap

Test các cặp có prefix chung:
- = và ==.
- ! và !=.
- <, <= và << nếu có.
- >, >= và >> nếu có.
- /, // và /*.
- : và :: nếu có.

### 9.4. Comment và slash

Nếu / là division, // là line comment và /* là block comment, lexer cần xác định ưu tiên. Test slash cuối file và slash liền với dấu khác.

### 9.5. Punctuation

Kiểm tra comma, dot, colon, semicolon, ngoặc tròn, vuông và nhọn, kể cả khi chúng liền nhau.

### 9.6. Ký tự gần giống operator

Ký tự không được hỗ trợ cần tạo ERROR hoặc diagnostic, không tự chuyển thành operator khác.

## 10. Whitespace, newline và comment

### 10.1. Whitespace

Nếu space và tab không có ý nghĩa cú pháp, lexer có thể bỏ qua chúng nhưng source span của token tiếp theo vẫn phải chính xác.

### 10.2. Newline có ý nghĩa

Nếu newline kết thúc statement, lexer cần phát NEWLINE hoặc giữ line break theo contract. Test nhiều newline liên tiếp và newline trong block.

### 10.3. Line comment

~~~text
// comment
# comment nếu DSL hỗ trợ
~~~

Test comment cuối file không có newline, comment có Unicode và marker xuất hiện bên trong string.

### 10.4. Block comment

~~~text
/* comment
   across lines
*/
~~~

Test comment rỗng, nhiều dòng, delimiter đóng và comment chưa đóng trước EOF.

### 10.5. Nested comment

Nếu cho phép comment lồng, lexer cần quản lý độ sâu. Test nhiều cấp và delimiter xuất hiện trong nội dung.

### 10.6. Documentation comment

Nếu DSL phân biệt documentation comment với comment thường, test token type hoặc channel riêng để documentation generator có thể sử dụng.

### 10.7. Comment trong interpolation

Xác định comment có được phép trong expression nội suy không. Test mode switch để comment không vô tình kết thúc string.

## 11. Lexical modes

### 11.1. Các mode

Lexer có thể có DEFAULT, STRING, TEMPLATE, INTERPOLATION, BLOCK_COMMENT hoặc REGEX_LITERAL. Mỗi mode có tập token và delimiter riêng.

### 11.2. Mode transition

Khi gặp quote, lexer chuyển từ DEFAULT sang STRING. Khi gặp delimiter kết thúc, nó quay lại DEFAULT. Test cả transition hợp lệ và trường hợp kết thúc bất thường.

### 11.3. Nested mode

Interpolation có thể chứa string khác hoặc block. Nếu grammar cho phép lồng, lexer cần stack mode thay vì chỉ một biến mode.

### 11.4. State isolation

State phải được khởi tạo lại cho mỗi source hoặc document. Không để mode, line counter hoặc buffer của file trước ảnh hưởng file sau.

### 11.5. EOF trong mode

Nếu EOF đến khi đang ở STRING hoặc BLOCK_COMMENT, diagnostic cần chỉ ra construct chưa đóng và vị trí bắt đầu tương ứng.

## 12. Lexical error và recovery

### 12.1. Lỗi từ vựng

Lỗi từ vựng xảy ra khi lexer gặp ký tự hoặc chuỗi ký tự không thể tạo token hợp lệ theo grammar hiện tại.

~~~text
name = @@@
~~~

Nếu @ không được hỗ trợ, lexer cần báo lỗi theo quy tắc đã định.

### 12.2. ERROR token

Một số lexer phát ERROR token chứa lexeme và span; số khác ghi diagnostic rồi bỏ qua ký tự. Cần hợp đồng thống nhất để parser và editor xử lý.

### 12.3. Recovery strategy

Các chiến lược gồm skip một ký tự, skip đến delimiter/newline, phát ERROR token rồi tiếp tục hoặc dừng khi không thể đồng bộ.

### 12.4. Tránh lỗi dây chuyền

Một ký tự sai có thể làm parser phát nhiều lỗi tiếp theo. Lexer cần tạo span và recovery point hợp lý để parser đồng bộ ở token sau.

### 12.5. Diagnostic structure

Diagnostic nên có code ổn định, message, severity, source span và related location nếu cần. Test nên kiểm tra code và span, không phụ thuộc quá mức vào nguyên văn message.

### 12.6. Recovery determinism

Cùng source và cùng lexer version cần tạo cùng token/error sequence. Recovery ngẫu nhiên làm test và editor behavior khó tái hiện.

## 13. Incremental lexing

### 13.1. Khái niệm

Editor thường không tokenize lại toàn bộ file sau mỗi lần gõ. Incremental lexer chỉ xử lý vùng thay đổi và phần tiếp theo cần thiết.

### 13.2. Token cache và state

Lexer có thể lưu token cùng state đầu/cuối của từng dòng. Khi một dòng thay đổi, nó re-lex đến khi state và token stream đồng bộ trở lại.

### 13.3. State convergence

Điểm đồng bộ là nơi lexer state mới giống state cũ và token phía sau không thay đổi. Test cần xác nhận lexer dừng re-lex đúng lúc.

### 13.4. Edit tại boundary

Test thêm, xóa hoặc thay ký tự ở đầu token, cuối token, giữa operator nhiều ký tự, trong escape, trong comment delimiter và tại EOF.

### 13.5. Edit làm đổi mode

Thêm hoặc xóa quote có thể làm phần còn lại của file chuyển mode. Incremental lexer phải re-lex đủ xa.

### 13.6. So sánh incremental với full lex

Một test mạnh:
1. Tokenize source ban đầu.
2. Áp dụng edit.
3. Chạy incremental lex.
4. Chạy full lex trên source sau edit.
5. So sánh type, lexeme, value, span và diagnostics.

### 13.7. Cancellation và document version

Nếu document version mới đến trong lúc lexer đang xử lý version cũ, kết quả cũ không được ghi đè state mới. Test cancellation và stale result handling.

## 14. Unit test và table-driven test

### 14.1. Test từng token type

Tạo test cho identifier, keyword, literal, operator, delimiter, whitespace, comment, EOF và error.

### 14.2. Table-driven test

~~~text
cases = [
  { input: "abc", expected: IDENTIFIER("abc") },
  { input: "42", expected: INTEGER_LITERAL(42) },
  { input: ">=", expected: GREATER_EQUAL },
  { input: "{", expected: LBRACE }
]
~~~

### 14.3. Test nhiều token

~~~text
input: "a>=10 and b!=0"
expected:
  IDENTIFIER("a")
  GREATER_EQUAL
  INTEGER_LITERAL(10)
  KEYWORD_AND
  IDENTIFIER("b")
  NOT_EQUAL
  INTEGER_LITERAL(0)
  EOF
~~~

### 14.4. Assertion chi tiết

So sánh type, lexeme, value, span, channel, diagnostic và EOF count. Không chỉ so sánh danh sách token type.

### 14.5. Test source nhỏ thực tế

Dùng một rule, query hoặc workflow ngắn có comment, whitespace, literal và operator để kiểm tra tương tác giữa token.

## 15. Property-based testing

### 15.1. Round-trip

Nếu lexer giữ trivia và lexeme đầy đủ, nối lexeme có thể tái tạo source:

~~~text
reconstruct(lex(source)) == source
~~~

Nếu whitespace bị bỏ, property cần dùng trivia hoặc source span để khôi phục.

### 15.2. Span invariant

Với mỗi token:
- start <= end.
- Span nằm trong source length.
- Token stream có thứ tự không giảm.
- Lexeme khớp source substring theo đơn vị offset đã chọn.

### 15.3. Progress invariant

Mỗi bước lexer phải tiêu thụ ít nhất một đơn vị input hoặc kết thúc. Điều này ngăn infinite loop khi gặp ký tự không hợp lệ.

### 15.4. EOF invariant

Lexer phát EOF đúng theo contract và không tiếp tục tạo token sau EOF.

### 15.5. Unicode và literal generator

Sinh chuỗi có ASCII, Unicode, combining mark, newline, control character; sinh number và string hợp lệ cũng như gần hợp lệ. Xác nhận không crash và span luôn hợp lệ.

### 15.6. Shrinking

Khi property thất bại, framework có thể rút ngắn input đến trường hợp tối giản. Lưu trường hợp đó thành regression test.

## 16. Fuzz testing

### 16.1. Mục tiêu

Fuzzing tạo input bất thường để tìm crash, infinite loop, memory issue, panic hoặc sai tokenization.

### 16.2. Byte-level fuzzing

Sinh byte stream bất kỳ, kể cả UTF-8 không hợp lệ. Lexer cần xử lý encoding error theo contract thay vì crash.

### 16.3. Grammar-aware fuzzing

Sinh source gần hợp lệ rồi biến đổi bằng cách bỏ delimiter, lặp operator, chèn ký tự lạ, cắt giữa escape hoặc lồng comment.

### 16.4. Mutation fuzzing

Lấy source hợp lệ rồi thêm, xóa hoặc thay ký tự ở vị trí ngẫu nhiên. Cách này thường tìm lỗi boundary hiệu quả.

### 16.5. Resource limit và corpus

Fuzz job cần timeout và memory cap. Corpus nên giữ ví dụ hợp lệ, lỗi, Unicode, literal cực trị, operator overlap, nested mode và bug đã phát hiện.

### 16.6. Regression từ fuzz finding

Mỗi finding cần được rút gọn, phân loại và thêm vào regression corpus. Không chỉ sửa bug mà bỏ quên input gây lỗi.

## 17. Golden test và snapshot token stream

### 17.1. Golden output

Golden test lưu token stream mong đợi cho source mẫu. Khi lexer thay đổi, test so sánh output mới với file golden.

### 17.2. Snapshot dễ đọc

~~~text
1:1-1:5 IDENTIFIER "rule"
1:6-1:17 IDENTIFIER "FreeShipping"
1:18-1:19 LBRACE "{"
2:5-2:9 KEYWORD "when"
~~~

### 17.3. Snapshot diagnostics

Lưu error code, message key và span cho source không hợp lệ.

### 17.4. Cập nhật golden

Không tự động chấp nhận snapshot mới chỉ để làm test xanh. Tokenization thay đổi có thể là breaking change cho parser, formatter hoặc editor.

### 17.5. Kết hợp assertion

Snapshot hữu ích để xem diff, nhưng assertion cấu trúc vẫn cần thiết để kiểm tra invariant và giải thích lỗi chính xác.

## 18. Coverage của lexer

### 18.1. Token type coverage

Đo token type nào đã xuất hiện trong test để phát hiện token chưa được kiểm thử.

### 18.2. Rule và branch coverage

Nếu lexer dùng regex hoặc grammar rule, đo mỗi lexical rule. Branch coverage cần bao gồm escape, delimiter, EOF, mode transition, error recovery và maximal munch.

### 18.3. Boundary coverage

Kiểm tra token một ký tự, token dài, ký tự đầu/cuối buffer, delimiter liền kề, newline và EOF.

### 18.4. Coverage không chứng minh đúng

Lexer có thể đạt coverage cao nhưng vẫn phân loại sai. Kết hợp coverage với expected token stream, property và fuzzing.

### 18.5. Mapping đặc tả sang test

Có thể lập mapping từ lexical grammar rule sang test ID. Cách này hữu ích khi review phạm vi hoặc cần bằng chứng kiểm chứng.

## 19. Tích hợp với parser và editor

### 19.1. Parser integration

Chạy một số source qua parser để xác nhận token stream tương thích với grammar cú pháp. Nhưng test lexer độc lập vẫn là chính để khoanh vùng lỗi.

### 19.2. Diagnostic mapping

Nếu parser báo lỗi tại token, vị trí phải trỏ về source span của lexer. Test sau Unicode, tab và CRLF.

### 19.3. Hidden token và formatter

Parser có thể bỏ qua comment nhưng formatter cần giữ. Test integration để đảm bảo token channel và trivia được tiêu thụ đúng.

### 19.4. Partial document

Editor thường gửi source chưa hoàn chỉnh. Lexer cần xử lý string chưa đóng hoặc operator đang gõ dở mà vẫn trả token stream hữu ích cho phần trước.

### 19.5. Semantic highlighting

Lexer cung cấp token cơ bản; semantic token có thể phân biệt symbol, type hoặc variable. Test để keyword không bị nhầm identifier và document version mới không bị kết quả cũ ghi đè.

### 19.6. Latency

Đo latency trên file lớn và khi gõ từng ký tự. Incremental lexer nên tránh full re-lex không cần thiết nhưng phải ưu tiên kết quả đúng.

## 20. Hiệu năng và độ bền

### 20.1. Linear scanning

Lexer thường nên chạy gần O(n) theo độ dài source. Regex backtracking không kiểm soát có thể tạo thời gian chạy tăng nhanh với input crafted.

### 20.2. Long token và many tokens

Test identifier, comment, string rất dài và source chứa nhiều token ngắn. Theo dõi giới hạn token, allocation và memory.

### 20.3. Buffer boundary

Nếu lexer đọc theo chunk, test token hoặc escape cắt ngang ranh giới buffer. Kết quả phải giống khi tokenize toàn bộ source trong một buffer.

### 20.4. Streaming input

Phân biệt tạm thời chưa có thêm byte với EOF thực sự. String hoặc comment chưa hoàn tất có thể cần chờ chunk tiếp theo.

### 20.5. Object reuse

Nếu tái sử dụng token hoặc buffer để giảm allocation, bảo đảm token của request trước không tham chiếu buffer đã bị ghi đè.

### 20.6. Benchmark

Benchmark cần input cố định, warmup và môi trường đủ ổn định. Theo dõi throughput, latency phân vị và memory.

## 21. Kiểm thử bảo mật lexer

### 21.1. Control character

Thử NUL, ESC, CR, LF và control character khác. Lexer cần từ chối hoặc xử lý theo grammar, không làm terminal log bị thao túng.

### 21.2. Unicode bidi control và homoglyph

Ký tự điều khiển hướng văn bản có thể khiến source hiển thị khác thứ tự logic. Ký tự nhìn giống nhau từ script khác có thể gây nhầm. Có thể từ chối hoặc cảnh báo trong identifier nhạy cảm.

### 21.3. Deep nesting

Nếu hỗ trợ nested comment hoặc interpolation, giới hạn độ sâu để tránh stack exhaustion.

### 21.4. Oversized token

Giới hạn độ dài string, identifier và comment khi môi trường yêu cầu. Báo lỗi rõ thay vì cấp phát không giới hạn.

### 21.5. Malformed encoding

Input byte sequence không phải UTF-8 hợp lệ cần được phát hiện ở decoding layer hoặc lexer. Không để các thành phần diễn giải cùng byte theo cách khác nhau.

### 21.6. Log safety

Lexeme chứa control character hoặc secret không nên được in thô vào log. Escape output và giới hạn độ dài diagnostic.

## 22. Ví dụ bộ test cho một DSL

Giả sử DSL có keyword rule, when, then, Boolean operator, identifier, integer, decimal, string, comparison và block comment.

### 22.1. Token test

~~~text
case "keyword":
    input: "rule"
    expected: KEYWORD_RULE, EOF

case "identifier":
    input: "ruleName"
    expected: IDENTIFIER("ruleName"), EOF

case "operator":
    input: ">="
    expected: GREATER_EQUAL, EOF

case "decimal":
    input: "12.50"
    expected: DECIMAL_LITERAL(12.50), EOF
~~~

### 22.2. Longest-match test

~~~text
input: "a>=10 && b!=0"
expected:
    IDENTIFIER("a")
    GREATER_EQUAL
    INTEGER_LITERAL(10)
    AND_AND
    IDENTIFIER("b")
    NOT_EQUAL
    INTEGER_LITERAL(0)
    EOF
~~~

### 22.3. String test

~~~text
input: "a quoted string with an escaped newline"
expected:
    STRING_LITERAL
    EOF
~~~

### 22.4. Error test

~~~text
input: "unfinished string
expected:
    LEX_UNTERMINATED_STRING
    EOF
~~~

### 22.5. Position test

Với source nhiều dòng có tab và ký tự Unicode, xác nhận start/end offset theo đơn vị đã công bố và line/column theo quy ước của compiler/editor.

## 23. Quy trình xây dựng bộ kiểm thử lexer

Một quy trình có thể gồm:
1. Đọc lexical grammar: liệt kê token type, pattern, priority và mode.
2. Xác định token contract: type, lexeme, value, span, channel và EOF.
3. Lập test matrix: token đơn, chuỗi token, boundary, error và mode.
4. Kiểm thử character class: chữ, số, underscore, whitespace, Unicode và control.
5. Kiểm thử keyword: boundary, case sensitivity, contextual keyword và escaped identifier.
6. Kiểm thử literal: integer, decimal, exponent, unit suffix, string và escape.
7. Kiểm thử operator: prefix overlap, maximal munch và punctuation.
8. Kiểm thử comment: line, block, nested và EOF.
9. Kiểm thử vị trí: CRLF, tab, Unicode, offset và source span.
10. Kiểm thử recovery: lỗi từ vựng, diagnostic và token sau lỗi.
11. Kiểm thử incremental: edit, mode transition, state convergence và cancellation.
12. Bổ sung property/fuzz: progress, span invariant, round-trip và malformed input.
13. Tạo golden corpus: source đại diện và token snapshot đã được xác nhận.
14. Kiểm thử parser integration: token stream, trivia và diagnostic mapping.
15. Đo coverage/performance: token/rule/branch coverage, throughput và memory.
16. Tự động hóa CI: chạy regression khi lexer, grammar hoặc encoding layer thay đổi.

## 24. Câu hỏi tự đánh giá

1. Lexer khác parser như thế nào?
2. Một token cần lưu những thông tin nào ngoài token type?
3. Maximal munch giải quyết vấn đề operator prefix overlap ra sao?
4. Keyword boundary giúp tránh lỗi nào?
5. Vì sao cần phân biệt lexeme và decoded literal value?
6. UTF-8 byte offset khác UTF-16 code unit như thế nào?
7. CRLF cần được tính line ra sao?
8. String interpolation yêu cầu lexer mode như thế nào?
9. Lexer recovery giúp editor tiếp tục phân tích ra sao?
10. Incremental lexer cần state convergence để làm gì?
11. Property-based testing có thể kiểm tra invariant nào?
12. Fuzz testing khác table-driven test ra sao?
13. Token coverage có chứng minh lexer đúng không?
14. Vì sao cần so sánh incremental lex với full lex?
15. Những trường hợp nào cần kiểm thử bảo mật lexer?

## Kết luận

Lexer chuyển source text thành token stream và tạo nền tảng cho parser, semantic analysis, formatter cùng editor tooling. Kiểm thử lexer cần xác nhận token type, lexeme, literal value, source span, channel, EOF và diagnostics. Những nhóm quan trọng gồm character class, identifier và keyword, numeric/string literal, operator maximal munch, whitespace/comment, Unicode, lexical mode và error recovery.

Bộ test vững chắc kết hợp table-driven cases, boundary tests, property-based tests, fuzzing, golden snapshots, coverage và integration với parser. Với editor, cần kiểm tra incremental lexing, source position, cancellation và input chưa hoàn chỉnh. Khi mọi invariant của token stream được đặc tả và kiểm chứng, lỗi từ vựng được phát hiện sớm, diagnostics chính xác hơn và các thành phần phía sau có thể dựa vào một hợp đồng đầu vào ổn định.

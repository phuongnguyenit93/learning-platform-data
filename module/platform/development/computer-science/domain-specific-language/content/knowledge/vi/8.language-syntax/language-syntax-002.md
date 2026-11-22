# Từ vựng và ngữ pháp

Một DSL (*Domain-Specific Language* – ngôn ngữ chuyên biệt theo miền) cần có cách biểu diễn thống nhất để người dùng mô tả khái niệm và thao tác trong miền của nó. Hai thành phần nền tảng tạo nên hình thức của ngôn ngữ là **từ vựng** (*lexicon*) và **ngữ pháp** (*grammar*).

- **Từ vựng** xác định những đơn vị ký hiệu mà ngôn ngữ nhận biết: từ khóa, tên, số, chuỗi, toán tử, dấu phân cách và các token khác.
- **Ngữ pháp** xác định cách kết hợp các đơn vị đó thành biểu thức, khai báo, câu lệnh và chương trình hợp lệ.

Từ vựng và ngữ pháp tạo nên phần cú pháp của DSL. Chúng cần được thiết kế dựa trên khái niệm miền, người sử dụng và cách công cụ xử lý chương trình. Một cú pháp tốt giúp người viết diễn đạt ý định rõ ràng, người đọc hiểu cấu trúc và công cụ phát hiện lỗi ở đúng vị trí.

## 1. Từ vựng của DSL

Từ vựng là tập hợp các đơn vị có ý nghĩa cú pháp mà lexer (*lexical analyzer* – bộ phân tích từ vựng) nhận diện trong văn bản nguồn. Khi đọc tệp DSL, lexer thường gom các ký tự thành token và gắn thông tin vị trí để những bước sau xử lý.

Ví dụ, với câu lệnh giả định:

```text
select name, salary from employees where salary > 50000
```

Lexer có thể tạo ra chuỗi token:

```text
KEYWORD("select")
IDENTIFIER("name")
COMMA(",")
IDENTIFIER("salary")
KEYWORD("from")
IDENTIFIER("employees")
KEYWORD("where")
IDENTIFIER("salary")
OPERATOR(">")
NUMBER("50000")
```

Tên token ở đây mang tính minh họa. Một lexer thực tế có thể dùng kiểu token riêng, lưu giá trị đã chuyển đổi và vị trí nguồn.

### 1.1. Ký tự và quy tắc ký tự

Trước khi xác định token, ngôn ngữ cần quy định tập ký tự được phép và cách xử lý chúng. Các quyết định thường gặp gồm:

- Có cho phép chữ Unicode trong tên định danh hay chỉ dùng chữ Latin không dấu?
- Tên có phân biệt chữ hoa và chữ thường không?
- Dấu gạch dưới hoặc chữ số có được xuất hiện trong tên không?
- Khoảng trắng, tab và xuống dòng có ý nghĩa hay chỉ dùng để phân tách?
- Comment bắt đầu và kết thúc bằng ký hiệu nào?
- Chuỗi có hỗ trợ escape như `\n`, `\t`, `\\` hoặc dấu nháy được escape không?

Những quy tắc này ảnh hưởng trực tiếp đến khả năng đọc và tính nhất quán của DSL. Nếu không xác định rõ, hai công cụ có thể hiểu cùng một tệp theo cách khác nhau.

### 1.2. Từ khóa (keywords)

Từ khóa là những từ được dành riêng để biểu diễn cấu trúc hoặc thao tác của ngôn ngữ. Ví dụ:

```text
from
where
select
sort
pipeline
source
transform
```

Từ khóa giúp người đọc nhận ra vai trò của từng phần trong chương trình. Khi chọn từ khóa, nên ưu tiên từ ngắn, quen thuộc với miền và có ý nghĩa nhất quán.

Một quyết định quan trọng là từ khóa có được dùng làm tên định danh hay không. Nếu `select` là từ khóa dành riêng, người dùng không thể đặt tên biến hoặc trường là `select` nếu không có cơ chế escape. Một số ngôn ngữ chỉ dành riêng từ khóa trong một ngữ cảnh nhất định, nhờ đó giảm xung đột tên nhưng làm parser phức tạp hơn.

### 1.3. Tên định danh (identifiers)

Định danh là tên do người viết đặt để tham chiếu đến một đối tượng trong chương trình, chẳng hạn biến, trường, bảng, hàm, tài nguyên hoặc quy tắc.

Ví dụ:

```text
employeeName
monthly_salary
customer
normalizeDate
```

Một quy tắc định danh cần xác định:

- Ký tự đầu tiên được phép.
- Ký tự tiếp theo được phép.
- Có phân biệt hoa thường không.
- Có cho phép Unicode, dấu gạch ngang hoặc dấu chấm không.
- Tên có thể trùng từ khóa không.
- Phạm vi và quy tắc trùng tên được xử lý ở cú pháp hay ngữ nghĩa.

Không nên nhồi quá nhiều ý nghĩa vào hình thức tên. Ví dụ, việc một tên bắt đầu bằng `tmp_` có phải là biến tạm hay không có thể là quy ước đặt tên, không nhất thiết là quy tắc ngữ pháp.

### 1.4. Literal và giá trị hằng

Literal là cách viết trực tiếp một giá trị trong chương trình. Các loại phổ biến gồm:

| Loại literal | Ví dụ | Ý nghĩa |
|---|---|---|
| Số nguyên | `42`, `-7` | Giá trị nguyên |
| Số thập phân | `3.14`, `0.25` | Giá trị có phần thập phân |
| Chuỗi | `"hello"` | Dữ liệu văn bản |
| Boolean | `true`, `false` | Giá trị đúng hoặc sai |
| Null/rỗng | `null` | Không có giá trị, nếu DSL hỗ trợ |
| Ngày tháng | `2026-11-15` | Ngày theo định dạng miền quy định |

DSL có thể định nghĩa literal chuyên biệt theo miền, chẳng hạn tiền tệ, đơn vị đo, khoảng thời gian hoặc địa chỉ tài nguyên. Khi làm vậy, cần quy định cách phân tích, chuẩn hóa và kiểm tra giá trị.

Ví dụ, `10 USD` và `10 VND` không nên được hiểu là cùng một khoản tiền. Đơn vị là một phần của giá trị miền, nên grammar và semantic analysis cần phối hợp để biểu diễn nó đúng.

### 1.5. Toán tử và dấu phân cách

Toán tử biểu diễn phép tính hoặc quan hệ, chẳng hạn:

```text
+  -  *  /       // số học
==  !=  <  >     // so sánh
and  or  not     // logic
->               // chuyển tiếp hoặc ánh xạ
```

Dấu phân cách xác định ranh giới giữa các thành phần:

```text
( )   { }   [ ]   ,   :   ;   .
```

Một DSL khai báo có thể dùng dấu ngoặc nhọn để nhóm thuộc tính của tài nguyên. Một DSL truy vấn có thể dùng dấu phẩy để phân tách trường. Một DSL workflow có thể dùng mũi tên để biểu diễn thứ tự hoặc quan hệ phụ thuộc.

Toán tử và dấu phân cách cần được lựa chọn nhất quán. Nếu cùng một ký hiệu được dùng cho nhiều mục đích, grammar cần cung cấp ngữ cảnh đủ rõ để phân biệt.

### 1.6. Comment và khoảng trắng

Comment giúp người viết giải thích mục đích hoặc ghi chú trong tệp DSL. Một ngôn ngữ có thể dùng comment một dòng như `# ghi chú` hoặc `// ghi chú`, comment nhiều dòng như `/* ... */`, hoặc không hỗ trợ comment.

Khoảng trắng có thể được xử lý theo hai cách:

- **Không mang ý nghĩa cấu trúc:** khoảng trắng chỉ tách token; xuống dòng tương tự dấu cách.
- **Có ý nghĩa cấu trúc:** thụt lề hoặc xuống dòng xác định phạm vi khối lệnh, như trong một số ngôn ngữ dạng indentation-sensitive.

Nếu dùng thụt lề để xác định khối, lexer phải theo dõi mức thụt lề và tạo token tương ứng, chẳng hạn `INDENT` và `DEDENT`. Cần quy định rõ tab và dấu cách được xử lý như thế nào để tránh khác biệt giữa trình soạn thảo.

## 2. Token và quá trình phân tích từ vựng

Token là đơn vị đầu ra của lexer. Một token thường có ít nhất loại token và giá trị văn bản hoặc giá trị đã phân tích. Để hỗ trợ chẩn đoán, token cũng thường lưu vị trí bắt đầu và kết thúc trong nguồn.

Một cấu trúc dữ liệu minh họa:

```java
record SourcePosition(int line, int column, int offset) {}

record Token(
    TokenType type,
    String lexeme,
    Object literalValue,
    SourcePosition start,
    SourcePosition end
) {}
```

`lexeme` là đoạn văn bản gốc tạo ra token; `literalValue` có thể lưu giá trị đã chuyển đổi, ví dụ chuỗi đã giải mã escape hoặc số đã được phân tích. Cách biểu diễn cụ thể phụ thuộc vào ngôn ngữ và implementation.

### 2.1. Lexer làm việc như thế nào?

Một lexer thường đọc nguồn từ trái sang phải, nhận diện token theo các quy tắc đã định. Luồng cơ bản:

1. Bỏ qua khoảng trắng và comment nếu chúng không có ý nghĩa cú pháp.
2. Nhận diện ký tự đầu để chọn nhóm token có thể bắt đầu tại vị trí đó.
3. Đọc thêm ký tự cho đến khi token hoàn chỉnh.
4. Phân loại token và chuyển đổi literal nếu cần.
5. Gắn vị trí nguồn rồi chuyển token cho parser.
6. Báo lỗi từ vựng nếu gặp chuỗi ký tự không thể phân loại.

Ví dụ, lexer gặp `>=` cần nhận diện đó là một toán tử duy nhất thay vì hai token `>` và `=`. Vì vậy, nhiều lexer dùng quy tắc **khớp dài nhất** (*maximal munch*): chọn token hợp lệ dài nhất tại vị trí hiện tại.

### 2.2. Biểu thức chính quy trong lexer

Một số nhóm token có thể được mô tả bằng regular expressions. Ví dụ, một định danh đơn giản có thể dùng:

```regex
[A-Za-z_][A-Za-z0-9_]*
```

Một số nguyên không dấu:

```regex
[0-9]+
```

Một chuỗi đặt trong dấu nháy kép, ở mức minh họa đơn giản:

```regex
"([^"\\]|\\.)*"
```

Các biểu thức này chỉ là quy tắc nhận diện token. Chúng không thay thế toàn bộ grammar của DSL. Regex phù hợp với các mẫu cục bộ như tên, số và chuỗi; cấu trúc lồng nhau như biểu thức có ngoặc hoặc khối khai báo thường cần parser.

### 2.3. Xung đột token

Một chuỗi có thể khớp với nhiều quy tắc token. Ví dụ, `where` có thể khớp quy tắc định danh và cũng là từ khóa. Lexer thường giải quyết bằng thứ tự ưu tiên hoặc bằng cách nhận diện định danh trước rồi tra bảng từ khóa.

Toán tử cũng có thể có tiền tố chung: `=`, `==`, `=>`. Quy tắc khớp dài nhất thường giúp nhận diện `==` hoặc `=>` đúng cách.

Nếu ngôn ngữ có từ khóa ngữ cảnh (*contextual keywords*), lexer có thể phát ra token định danh và để parser xác định vai trò dựa trên vị trí. Cách này linh hoạt nhưng làm tăng độ phức tạp của parser và thông báo lỗi.

## 3. Ngữ pháp của DSL

Ngữ pháp xác định cách các token được kết hợp thành cấu trúc hợp lệ. Một grammar thường gồm:

- **Terminal:** token cụ thể do lexer tạo ra, như `SELECT`, `IDENTIFIER`, `NUMBER`, `LBRACE`.
- **Nonterminal:** tên đại diện cho một cấu trúc lớn hơn, như `Expression`, `Statement`, `Declaration`.
- **Production rule:** quy tắc cho biết một nonterminal có thể được tạo từ những terminal hoặc nonterminal nào.
- **Start symbol:** ký hiệu bắt đầu đại diện cho một chương trình hoàn chỉnh.

Ví dụ, một grammar có thể nói rằng chương trình gồm nhiều câu lệnh, câu lệnh có thể là khai báo hoặc biểu thức, và biểu thức có thể chứa toán tử.

### 3.1. EBNF và cách viết quy tắc

EBNF (*Extended Backus–Naur Form*) là ký pháp thường dùng để mô tả grammar. Một số ký hiệu phổ biến:

| Ký hiệu | Ý nghĩa thường dùng |
|---|---|
| `=` hoặc `::=` | Được định nghĩa là |
| `|` | Lựa chọn một trong các nhánh |
| `[ ... ]` | Thành phần tùy chọn |
| `{ ... }` | Lặp lại không hoặc nhiều lần |
| `( ... )` | Nhóm các thành phần |
| `"..."` | Terminal dạng văn bản cụ thể |
| `;` | Kết thúc một quy tắc trong một số biến thể EBNF |

Ký pháp EBNF có nhiều biến thể giữa các tài liệu và công cụ. Khi dùng cho một dự án, cần xác định quy ước cụ thể để người đọc hiểu chính xác dấu ngoặc, phép lặp và cách viết terminal.

### 3.2. Grammar ví dụ cho một DSL truy vấn nhỏ

Giả sử DSL cho phép viết câu truy vấn theo cấu trúc:

```text
from employees
where salary > 50000
select name, salary
```

Một grammar EBNF đơn giản có thể là:

```ebnf
Program        = Query, { Query } ;
Query          = "from", Identifier,
                 [ "where", Expression ],
                 "select", FieldList ;
FieldList      = Identifier, { ",", Identifier } ;
Expression     = Comparison ;
Comparison     = Operand, [ CompareOperator, Operand ] ;
Operand        = Identifier | Number | String ;
CompareOperator = "==" | "!=" | ">" | ">=" | "<" | "<=" ;
Identifier     = Letter, { Letter | Digit | "_" } ;
Number         = Digit, { Digit } ;
String         = '"', { StringCharacter }, '"' ;
```

Grammar này chỉ minh họa cấu trúc tổng quát. Một triển khai thực tế cần quy định đầy đủ escape trong chuỗi, số âm, số thập phân, comment, tên trùng từ khóa, dấu kết thúc câu lệnh và cách xử lý nhiều điều kiện.

### 3.3. Grammar mô tả cấu trúc, không tự xác định mọi ý nghĩa

Grammar có thể xác định rằng `from` phải theo sau bởi một định danh. Nhưng nó không tự biết tên bảng đó có tồn tại trong schema hay không. Grammar có thể chấp nhận `salary > "high"` nếu hai toán hạng được định nghĩa rộng, trong khi semantic analysis sẽ phát hiện kiểu số và kiểu chuỗi không tương thích.

Vì vậy, cần phân biệt:

- **Cú pháp:** chuỗi token có tạo thành cấu trúc hợp lệ không?
- **Ngữ nghĩa:** cấu trúc đó có ý nghĩa hợp lệ theo quy tắc miền không?

Không nên cố đưa mọi quy tắc nghiệp vụ vào grammar. Những điều kiện phụ thuộc schema, trạng thái hệ thống, quyền truy cập hoặc dữ liệu runtime thường cần được kiểm tra ở bước ngữ nghĩa hoặc thực thi.

## 4. Cấu trúc biểu thức và độ ưu tiên toán tử

Một DSL có biểu thức thường cần quy định rõ cách nhóm toán tử. Ví dụ:

```text
price + quantity * tax
```

Nếu phép nhân có độ ưu tiên cao hơn phép cộng, biểu thức được hiểu là:

```text
price + (quantity * tax)
```

Nếu không có quy tắc ưu tiên hoặc dấu ngoặc, biểu thức có thể mơ hồ hoặc bị hiểu khác nhau giữa các công cụ.

### 4.1. Phân tầng grammar theo độ ưu tiên

Một cách phổ biến là tạo nonterminal riêng cho từng tầng độ ưu tiên:

```ebnf
Expression = Additive ;
Additive   = Multiplicative, { ("+" | "-"), Multiplicative } ;
Multiplicative = Unary, { ("*" | "/"), Unary } ;
Unary      = [ "-" | "not" ], Primary ;
Primary    = Number
           | Identifier
           | "(", Expression, ")" ;
```

Trong ví dụ này, `Multiplicative` nằm bên trong `Additive`, nên phép nhân và chia được phân tích trước phép cộng và trừ. `Primary` cho phép biểu thức con trong ngoặc.

### 4.2. Tính kết hợp (associativity)

Độ ưu tiên xác định toán tử nào được nhóm trước; tính kết hợp xác định cách nhóm các toán tử cùng mức.

Ví dụ, phép trừ thường kết hợp trái:

```text
a - b - c
```

được hiểu là:

```text
(a - b) - c
```

Phép gán trong nhiều ngôn ngữ kết hợp phải:

```text
a = b = c
```

được hiểu là:

```text
a = (b = c)
```

Không nên dựa vào trực giác để suy đoán. Grammar hoặc đặc tả ngôn ngữ cần ghi rõ độ ưu tiên và tính kết hợp của từng toán tử.

### 4.3. Toán tử một ngôi, hai ngôi và gọi hàm

Toán tử một ngôi (*unary*) nhận một toán hạng, như `-x` hoặc `not enabled`. Toán tử hai ngôi (*binary*) nhận hai toán hạng, như `a + b` hoặc `x > 10`. DSL cũng có thể hỗ trợ gọi hàm, truy cập thuộc tính, chỉ mục mảng và toán tử ba ngôi.

Mỗi dạng cần có quy tắc cú pháp và độ ưu tiên. Nếu DSL có nhiều loại biểu thức, nên mô tả bằng grammar rõ ràng thay vì viết một quy tắc chung quá rộng rồi xử lý mọi trường hợp bằng các điều kiện khó hiểu trong parser.

## 5. Đệ quy và cấu trúc lồng nhau

Ngữ pháp của biểu thức và cấu trúc lồng nhau thường có tính đệ quy. Ví dụ, biểu thức trong ngoặc lại có thể chứa một biểu thức khác; khối lệnh có thể chứa các khai báo hoặc khối con.

Một grammar đơn giản cho khối:

```ebnf
Block       = "{", { Statement }, "}" ;
Statement   = Declaration | Assignment | IfStatement ;
IfStatement = "if", Expression, Block,
              [ "else", Block ] ;
```

Quy tắc `Block` chứa `Statement`, còn `IfStatement` chứa `Block`. Đây là cấu trúc đệ quy giúp biểu diễn khối lồng nhau.

Đệ quy cho phép grammar mô tả cấu trúc linh hoạt, nhưng parser phải xử lý đúng dấu ngoặc, điểm kết thúc và trường hợp thiếu thành phần. Với ngôn ngữ lớn, cần cân nhắc giới hạn độ sâu hoặc cơ chế chống đầu vào quá lớn gây tiêu thụ tài nguyên không hợp lý.

## 6. Các loại grammar và cách chọn parser

Không phải mọi grammar đều phù hợp với mọi thuật toán parsing. Một số nhóm thường gặp:

### 6.1. Grammar LL và recursive descent

Parser recursive descent thường có các hàm tương ứng với nonterminal. Cách này dễ hiểu và dễ kiểm soát khi grammar không quá phức tạp. Nhiều parser thủ công dùng một số token nhìn trước (*lookahead*) để quyết định nhánh.

LL là một họ kỹ thuật parsing đọc đầu vào từ trái sang phải và xây dựng dẫn xuất trái. Grammar LL(k) cần số token nhìn trước hữu hạn theo `k` để chọn nhánh. Nếu grammar có đệ quy trái hoặc lựa chọn khó phân biệt, cần biến đổi grammar hoặc dùng kỹ thuật khác.

### 6.2. Grammar LR và parser sinh tự động

Parser LR đọc đầu vào từ trái sang phải và xây dựng dẫn xuất phải theo thứ tự ngược. Các parser LR có thể xử lý nhiều grammar biểu thức tự nhiên hơn recursive descent đơn giản, nhưng thường cần công cụ sinh parser và cách đọc thông báo lỗi riêng.

Các công cụ parser generator có thể nhận grammar và tạo parser. Chúng giúp giảm mã parsing thủ công, nhưng nhóm vẫn phải hiểu xung đột grammar, ưu tiên toán tử, chiến lược phục hồi lỗi và cách ánh xạ kết quả thành AST.

### 6.3. PEG và parsing expression grammar

PEG (*Parsing Expression Grammar*) mô tả cú pháp bằng các biểu thức parsing có thứ tự ưu tiên. Trong PEG, thứ tự các lựa chọn có ý nghĩa: parser thử nhánh đầu tiên, và nếu thành công thì không nhất thiết thử nhánh sau.

PEG có thể thuận tiện khi xây parser cho DSL nhỏ hoặc vừa, nhưng người thiết kế cần hiểu cách ordered choice ảnh hưởng đến việc nhận diện cấu trúc. Một grammar PEG có thể cho kết quả khác grammar CFG tương tự nếu đổi thứ tự nhánh.

### 6.4. Grammar không ngữ cảnh (CFG)

Ngữ pháp không ngữ cảnh (*Context-Free Grammar – CFG*) mô tả cấu trúc bằng các production rule mà vế trái thường là một nonterminal duy nhất. CFG là nền tảng lý thuyết cho nhiều parser và ký pháp grammar.

Không phải mọi ràng buộc của một DSL đều có thể biểu diễn gọn trong CFG. Chẳng hạn, kiểm tra tên biến đã khai báo, kiểu của trường hoặc một tài nguyên chỉ xuất hiện một lần thường cần ngữ nghĩa và trạng thái bên ngoài grammar.

## 7. Tính mơ hồ và xung đột trong grammar

Một grammar mơ hồ (*ambiguous grammar*) nếu cùng một chuỗi token có thể có nhiều cây phân tích khác nhau theo grammar đó.

Ví dụ:

```text
a + b * c
```

Nếu grammar không quy định độ ưu tiên, có thể tạo hai cách nhóm:

```text
(a + b) * c
a + (b * c)
```

Hai cây có thể cho kết quả khác nhau. DSL cần quy định rõ ưu tiên hoặc yêu cầu dấu ngoặc để tránh mơ hồ.

### 7.1. Xung đột shift/reduce và reduce/reduce

Trong một số parser LR, grammar có thể tạo xung đột:

- **Shift/reduce:** parser không biết nên đọc thêm token hay hoàn tất một production hiện tại.
- **Reduce/reduce:** parser không biết nên rút gọn theo production nào trong nhiều lựa chọn.

Một số xung đột có thể giải quyết bằng quy tắc ưu tiên hoặc tính kết hợp của toán tử. Những xung đột khác cho thấy grammar cần được thiết kế lại để rõ ràng hơn.

### 7.2. Dangling else

Một ví dụ kinh điển là câu lệnh `if` lồng nhau:

```text
if conditionA
    if conditionB
        action1
    else
        action2
```

`else` thuộc về `if` nào? Nhiều ngôn ngữ quy định `else` gắn với `if` gần nhất chưa có `else`. Một DSL cũng cần quy tắc tương tự hoặc yêu cầu dấu ngoặc để nhóm khối rõ ràng.

### 7.3. Giảm mơ hồ bằng thiết kế cú pháp

Một số cách thường dùng:

- Định nghĩa độ ưu tiên và tính kết hợp rõ ràng.
- Dùng từ khóa hoặc dấu phân cách giúp phân biệt cấu trúc.
- Yêu cầu dấu ngoặc ở những trường hợp khó đọc.
- Tránh các production có tiền tố chung kéo dài nếu parser không xử lý tốt.
- Dùng cú pháp tường minh cho các khai báo quan trọng.
- Viết ví dụ và test cho các trường hợp ranh giới.

## 8. Từ grammar đến AST

Grammar mô tả những chuỗi token hợp lệ; parser biến chuỗi token thành cấu trúc dữ liệu. AST là một biểu diễn thường dùng vì nó phản ánh quan hệ giữa các thành phần mà không cần giữ mọi dấu câu.

Ví dụ grammar:

```ebnf
Expression = Number, ("+" | "*"), Number ;
```

Một parser có thể tạo AST tương ứng:

```text
BinaryExpression
├── operator: "+"
├── left: NumberLiteral(2)
└── right: NumberLiteral(3)
```

AST thường gồm các loại node như:

- `Program`: toàn bộ chương trình.
- `Declaration`: khai báo tài nguyên, biến hoặc hàm.
- `Statement`: câu lệnh hoặc thao tác.
- `Expression`: biểu thức tính toán hoặc điều kiện.
- `Identifier`: tham chiếu đến tên.
- `Literal`: giá trị hằng.

Mỗi node nên có cấu trúc rõ ràng, kiểu dữ liệu phù hợp và thông tin vị trí nguồn. Khi grammar thay đổi, AST có thể thay đổi theo; do đó, cần cân nhắc liệu AST có phải giao diện nội bộ ổn định cho các bước sau hay không.

## 9. Ví dụ xây dựng DSL cấu hình dịch vụ

Giả sử cần một DSL nhỏ để khai báo dịch vụ:

```text
service "catalog" {
    replicas = 3
    image = "catalog:1.2"
    port = 8080
    enabled = true
}
```

### 9.1. Từ vựng

Các token chính có thể gồm:

| Token | Ví dụ | Vai trò |
|---|---|---|
| `SERVICE` | `service` | Từ khóa mở khai báo dịch vụ |
| `STRING` | `"catalog"` | Tên dịch vụ hoặc chuỗi |
| `LBRACE`, `RBRACE` | `{`, `}` | Mở và đóng khối |
| `IDENTIFIER` | `replicas`, `image` | Tên thuộc tính |
| `EQUALS` | `=` | Gán giá trị |
| `NUMBER` | `3`, `8080` | Giá trị số |
| `BOOLEAN` | `true` | Giá trị logic |

### 9.2. Grammar

Một grammar EBNF có thể là:

```ebnf
Program       = { ServiceDeclaration } ;
ServiceDeclaration = "service", String, Block ;
Block         = "{", { Property }, "}" ;
Property      = Identifier, "=", Value ;
Value         = String | Number | Boolean ;
String        = QuotedString ;
Number        = Integer ;
Boolean       = "true" | "false" ;
Identifier    = Letter, { Letter | Digit | "_" } ;
```

### 9.3. Kiểm tra ngữ nghĩa

Sau khi parser tạo AST, validator có thể kiểm tra:

- `replicas` phải là số nguyên dương.
- `image` phải là chuỗi không rỗng.
- `port` phải nằm trong phạm vi được miền cho phép.
- `enabled` phải là boolean.
- Tên thuộc tính không được lặp nếu DSL không cho phép khai báo trùng.
- Một dịch vụ phải có đủ các trường bắt buộc.

Những điều kiện như kiểu literal có thể được thể hiện một phần trong grammar, nhưng giới hạn số, tính bắt buộc và tính duy nhất thường cần bước ngữ nghĩa. Nhờ tách hai bước, grammar vẫn dễ hiểu và quy tắc miền có thể được mở rộng độc lập.

## 10. Thiết kế từ vựng và grammar phù hợp với miền

Một DSL tốt không chỉ đúng về mặt kỹ thuật mà còn giúp người dùng diễn đạt ý định tự nhiên. Khi thiết kế cú pháp, cần bắt đầu từ các khái niệm và thao tác phổ biến trong miền.

### 10.1. Chọn từ khóa theo ngôn ngữ nghiệp vụ

Tên như `service`, `replicas`, `source`, `transform`, `approve` hoặc `ship` có thể dễ hiểu nếu chúng phản ánh từ vựng mà người dùng miền thường dùng. Tránh tạo nhiều từ khóa đồng nghĩa cho cùng một hành động vì chúng làm tăng độ phức tạp của tài liệu và parser.

### 10.2. Giữ cú pháp nhất quán

Nếu một khai báo dùng `name = value`, các khai báo tương tự nên dùng cùng quy tắc. Nếu một khối mở bằng `{` thì các khối cùng loại nên có quy tắc đóng rõ ràng. Tính nhất quán giúp người dùng dự đoán cú pháp mới từ những gì đã học.

### 10.3. Cân bằng ngắn gọn và tường minh

Cú pháp ngắn có thể giảm công sức gõ, nhưng nếu lược bỏ quá nhiều dấu hiệu cấu trúc, chương trình có thể khó đọc hoặc mơ hồ. Cú pháp tường minh thường phù hợp với cấu hình quan trọng, nơi khả năng đọc và phát hiện lỗi có giá trị cao.

### 10.4. Xem xét khả năng mở rộng

Nếu DSL sẽ có thêm loại tài nguyên, toán tử hoặc câu lệnh, grammar nên có cấu trúc mở rộng hợp lý. Tuy nhiên, không nên tạo cú pháp tổng quát quá mức khi miền chưa cần. Mỗi cấu trúc bổ sung đều tăng chi phí parser, tài liệu, kiểm tra và tương thích.

### 10.5. Xác định quy tắc định dạng

Formatter và style guide nên thống nhất cách thụt lề, xuống dòng, khoảng trắng, dấu phẩy và dấu kết thúc. Nếu có formatter chuẩn, các nhóm có thể tránh tranh luận về cách trình bày và giảm khác biệt không cần thiết trong version control.

## 11. Thông báo lỗi và phục hồi cú pháp

Không có grammar nào tránh được hoàn toàn lỗi do người dùng nhập. Một công cụ DSL cần báo lỗi đủ rõ để người viết biết điều gì sai và sửa ở đâu.

Ví dụ lỗi:

```text
service "catalog" {
    replicas = "three"
    port = 8080
```

Parser có thể phát hiện thiếu dấu `}` ở cuối tệp. Semantic analyzer có thể phát hiện `replicas` cần số nguyên nhưng nhận chuỗi.

Một thông báo lỗi tốt nên nêu:

- Tệp, dòng và cột xảy ra lỗi.
- Token hoặc giá trị gây lỗi.
- Cấu trúc hoặc kiểu giá trị được mong đợi.
- Gợi ý sửa nếu có thể xác định chắc chắn.

Ví dụ:

```text
config.dsl:2:16: expected an integer for property "replicas", found string "three"
```

### 11.1. Phục hồi lỗi (error recovery)

Parser có thể dừng ngay tại lỗi đầu tiên hoặc cố gắng phục hồi để tiếp tục phân tích và báo nhiều lỗi trong một lần chạy.

Một chiến lược phổ biến là bỏ qua token cho đến khi gặp điểm đồng bộ (*synchronization point*) như dấu chấm phẩy, dấu đóng khối hoặc từ khóa bắt đầu khai báo mới. Điều này giúp parser tiếp tục và báo thêm lỗi ở phần sau.

Phục hồi cần thận trọng: nếu parser đoán sai cấu trúc, nó có thể tạo nhiều lỗi giả. Với DSL cấu hình, dừng ở lỗi cú pháp đầu tiên đôi khi dễ hiểu hơn; với IDE, phục hồi từng phần có thể hữu ích để tiếp tục gợi ý và hiển thị diagnostics.

## 12. Kiểm thử từ vựng và ngữ pháp

Grammar và lexer là một phần của đặc tả ngôn ngữ, nên cần được kiểm thử bằng các đầu vào đại diện.

### 12.1. Kiểm thử token

Kiểm tra tên hợp lệ, số, chuỗi, escape, comment, toán tử có tiền tố chung, Unicode và khoảng trắng. Nên có trường hợp biên như chuỗi chưa đóng, ký tự lạ hoặc số có định dạng sai.

### 12.2. Kiểm thử grammar

Với mỗi production quan trọng, chuẩn bị ít nhất một ví dụ hợp lệ và các ví dụ không hợp lệ. Kiểm tra cả cấu trúc lồng nhau, thứ tự khai báo, thành phần tùy chọn và biểu thức có nhiều toán tử.

### 12.3. Kiểm thử ưu tiên và tính kết hợp

Ví dụ cần kiểm tra:

```text
a + b * c
(a + b) * c
a - b - c
not active and enabled
```

Không chỉ kiểm tra parser chấp nhận chuỗi; cần kiểm tra AST có nhóm biểu thức đúng như đặc tả.

### 12.4. Kiểm thử lỗi và vị trí nguồn

Đầu vào sai cần tạo thông báo phù hợp, không làm công cụ treo hoặc đưa ra stack trace khó hiểu. Cần kiểm tra vị trí dòng/cột chính xác, nhất là khi có Unicode, tab, comment nhiều dòng và chuỗi escape.

### 12.5. Kiểm thử tương thích grammar

Khi thay đổi grammar, nên chạy các chương trình DSL đã có để phát hiện thay đổi ngoài dự kiến. Nếu cú pháp cũ bị loại bỏ, cần xác định phiên bản, thông báo deprecation và hướng chuyển đổi.

## 13. Quản lý phiên bản từ vựng và ngữ pháp

DSL có thể phát triển theo thời gian: thêm từ khóa, toán tử, literal hoặc cấu trúc mới; thay đổi cách hiểu của một câu lệnh; loại bỏ cú pháp cũ. Mỗi thay đổi có thể ảnh hưởng đến chương trình đã lưu.

Một số nguyên tắc:

- **Thêm cú pháp theo hướng tương thích:** tránh làm cho một chuỗi vốn hợp lệ ở phiên bản trước trở thành cấu trúc khác mà không có cảnh báo.
- **Dành không gian cho từ khóa mới:** nếu mọi tên đều có thể trùng từ khóa, việc bổ sung từ khóa có thể phá mã cũ.
- **Đánh phiên bản ngôn ngữ:** tệp DSL hoặc môi trường chạy có thể chỉ rõ phiên bản grammar được áp dụng.
- **Có deprecation và migration:** báo trước khi bỏ cú pháp cũ và cung cấp cách chuyển đổi.
- **Kiểm thử chương trình cũ:** duy trì bộ mẫu DSL thực tế để phát hiện thay đổi parser và AST.

Thay đổi grammar không chỉ là thay đổi parser. Nó còn ảnh hưởng đến formatter, syntax highlighting, tài liệu, validator, IDE và các công cụ sinh mã.

## 14. Những sai lầm thường gặp

**Nhầm lẫn từ vựng với ngữ pháp.** Từ khóa và token thuộc từ vựng; cách kết hợp token thành câu lệnh thuộc grammar. Hai phần liên quan nhưng có trách nhiệm khác nhau.

**Dùng regex để xử lý toàn bộ ngôn ngữ.** Regex có thể nhận diện token, nhưng cấu trúc lồng nhau và biểu thức phức tạp thường cần parser có trạng thái và grammar rõ ràng.

**Để grammar chứa mọi quy tắc nghiệp vụ.** Grammar nên mô tả cấu trúc. Quy tắc phụ thuộc schema, kiểu, quyền hoặc trạng thái thường thuộc semantic analysis hay runtime.

**Không quy định ưu tiên toán tử.** Biểu thức có thể được hiểu theo nhiều cách. Cần định nghĩa độ ưu tiên, tính kết hợp hoặc yêu cầu ngoặc.

**Không giữ vị trí nguồn.** Khi AST không lưu vị trí, thông báo lỗi sau parsing khó chỉ đúng đoạn người dùng cần sửa.

**Thêm từ khóa mà không xem xét tên cũ.** Một tên hợp lệ ở phiên bản trước có thể vô tình trở thành từ khóa và làm chương trình cũ không còn phân tích được.

**Cú pháp quá ngắn hoặc quá nhiều ngoại lệ.** Ngôn ngữ khó học nếu cùng một cấu trúc có nhiều cách viết hoặc một ký hiệu mang nhiều nghĩa không rõ ràng.

## 15. Ghi nhớ

- Từ vựng xác định các token như từ khóa, định danh, literal, toán tử và dấu phân cách.
- Lexer đọc ký tự, nhận diện token và gắn vị trí nguồn.
- Grammar quy định cách token kết hợp thành biểu thức, câu lệnh và chương trình.
- EBNF là một ký pháp phổ biến để mô tả production rule, lựa chọn, thành phần tùy chọn và phép lặp.
- Độ ưu tiên và tính kết hợp quyết định cách nhóm biểu thức.
- Parser tạo AST; semantic analysis kiểm tra tên, kiểu và quy tắc miền mà grammar không thể xác định chỉ từ cú pháp.
- DSL cần thông báo lỗi có vị trí, kiểm thử grammar và quản lý tương thích khi từ vựng hoặc ngữ pháp thay đổi.

## 16. Câu hỏi tự kiểm tra

1. Từ vựng và ngữ pháp khác nhau ở nhiệm vụ nào trong một DSL?
2. Lexer tạo ra token gì khi phân tích câu `select name from employees`?
3. Vì sao quy tắc khớp dài nhất hữu ích khi nhận diện các toán tử `=`, `==` và `=>`?
4. Trong EBNF, dấu ngoặc vuông và ngoặc nhọn thường biểu thị điều gì?
5. Vì sao grammar có thể chấp nhận một câu lệnh nhưng semantic analysis vẫn từ chối nó?
6. Độ ưu tiên và tính kết hợp khác nhau như thế nào? Hãy minh họa bằng phép cộng và trừ.
7. Grammar đệ quy giúp biểu diễn cấu trúc nào? Nêu ví dụ về khối lệnh lồng nhau.
8. Một grammar mơ hồ có thể gây ra vấn đề gì cho AST và cách thực thi?
9. Vì sao cần giữ vị trí nguồn trong token hoặc AST?
10. Thêm một từ khóa mới có thể ảnh hưởng đến chương trình DSL cũ như thế nào?

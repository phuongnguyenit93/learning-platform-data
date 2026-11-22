# Recursive descent

**Recursive descent** (phân tích cú pháp đệ quy xuống) là một kỹ thuật xây dựng parser theo hướng từ trên xuống (top-down). Parser bắt đầu từ ký hiệu bắt đầu của grammar, rồi lần lượt phân tích các cấu trúc con bằng cách gọi những hàm tương ứng với các quy tắc ngữ pháp. Một hàm có thể gọi lại chính nó, trực tiếp hoặc gián tiếp, để xử lý cấu trúc lồng nhau; vì vậy kỹ thuật này được gọi là đệ quy xuống.

Recursive descent phù hợp với nhiều DSL vì cách triển khai tương đối trực quan: mỗi quy tắc grammar thường tương ứng với một hàm, còn các hàm kết hợp để nhận diện khai báo, biểu thức, câu lệnh và khối. Parser có thể tạo Abstract Syntax Tree (AST) ngay trong lúc phân tích, báo lỗi gần vị trí sai và được mở rộng theo từng tính năng của ngôn ngữ.

Để dùng kỹ thuật này hiệu quả, cần hiểu cách grammar điều khiển lời gọi hàm, cách chọn nhánh bằng lookahead, cách xử lý đệ quy trái và thứ tự ưu tiên toán tử. Một grammar không phù hợp có thể khiến parser lặp vô hạn, chọn nhầm nhánh hoặc phải quay lui quá nhiều.

## 1. Recursive descent là gì?

Recursive descent là parser mà mỗi nonterminal trong grammar được triển khai bằng một thủ tục hoặc hàm. Hàm đó đọc các token thuộc cấu trúc tương ứng, gọi những hàm khác để phân tích thành phần con, rồi trả về kết quả như AST node hoặc một giá trị cú pháp.

Ví dụ, grammar đơn giản:

```text
Expression -> Number
Expression -> "(" Expression ")"
```

có thể được triển khai bằng hàm `parseExpression`. Nếu token hiện tại là số, hàm đọc số và trả về node literal. Nếu token hiện tại là dấu ngoặc mở, hàm đọc `(`, gọi lại `parseExpression` để phân tích biểu thức bên trong, rồi yêu cầu dấu `)`.

```text
parseExpression()
    ├── nếu NUMBER: đọc số, trả NumberLiteral
    └── nếu "(": đọc "(", gọi parseExpression(), đọc ")", trả node nhóm
```

Điểm đặc trưng là parser đi từ cấu trúc lớn đến các cấu trúc con. Một `Program` có thể chứa nhiều `Statement`; mỗi `Statement` có thể chứa `Expression`; một `Expression` lại có thể chứa các biểu thức con.

### 1.1. Vì sao gọi là top-down?

Parser bắt đầu từ ký hiệu bắt đầu như `Program` và tìm cách giải thích chuỗi token thành cấu trúc đó. Nó đi xuống các quy tắc con cho đến khi khớp token đầu vào.

Ví dụ:

```text
Program
  -> Statement
      -> VariableDeclaration
          -> "let" Identifier "=" Expression ";"
              -> NumberLiteral
```

Khi phân tích hoàn tất, parser đã đi từ khái niệm chương trình tổng thể đến từng thành phần nhỏ như từ khóa, tên biến và literal.

### 1.2. Recursive descent và predictive parser

Recursive descent là một cách tổ chức parser. Nó có thể được triển khai theo kiểu dự đoán (predictive) nếu parser chọn được nhánh dựa trên một lượng lookahead giới hạn mà không cần quay lui. Một parser recursive descent khác có thể thử một nhánh, thất bại rồi quay lui để thử nhánh khác.

Do đó, hai thuật ngữ không hoàn toàn đồng nghĩa:

- **Recursive descent:** nhấn mạnh cấu trúc triển khai bằng các hàm đệ quy tương ứng với grammar.
- **Predictive parsing:** nhấn mạnh việc chọn quy tắc bằng lookahead, không cần backtracking.
- **LL(1):** một lớp grammar có thể được phân tích từ trái sang phải, tạo dẫn xuất trái nhất, với một token lookahead để chọn quy tắc.

Một recursive descent parser viết tốt thường hướng đến cách dự đoán vì dễ hiểu và có hiệu năng ổn định.

## 2. Lexer cung cấp token cho parser

Recursive descent parser thường làm việc trên token stream, không trực tiếp xử lý từng ký tự. Lexer (bộ phân tích từ vựng) đã nhóm ký tự thành các token như keyword, identifier, number, string, operator và dấu phân cách.

Ví dụ DSL:

```text
let total = price * quantity;
```

Lexer có thể tạo dãy token:

| Loại token | Lexeme |
|---|---|
| `LET` | `let` |
| `IDENTIFIER` | `total` |
| `EQUAL` | `=` |
| `IDENTIFIER` | `price` |
| `STAR` | `*` |
| `IDENTIFIER` | `quantity` |
| `SEMICOLON` | `;` |
| `EOF` | kết thúc đầu vào |

Parser không cần tự nhận diện chữ số hoặc xác định nơi kết thúc identifier. Nó chỉ kiểm tra loại token và lấy giá trị đã được lexer giải mã.

Việc tách lexer và parser giúp mỗi phần có trách nhiệm rõ ràng. Lexer xử lý encoding, comment, khoảng trắng và literal; parser xử lý cấu trúc grammar, thứ tự ưu tiên và quan hệ giữa các thành phần.

## 3. Grammar và cách ánh xạ thành hàm

Để triển khai recursive descent, trước tiên cần mô tả grammar. Mỗi quy tắc thường có một nonterminal ở vế trái và một chuỗi terminal/nonterminal ở vế phải.

Ví dụ grammar cho một phần DSL:

```text
Program       -> Statement* EOF
Statement     -> VariableDecl | IfStatement | ExprStatement
VariableDecl  -> "let" IDENTIFIER "=" Expression ";"
IfStatement   -> "if" "(" Expression ")" Block
ExprStatement -> Expression ";"
Block         -> "{" Statement* "}"
```

Có thể ánh xạ các quy tắc thành hàm:

| Nonterminal | Hàm parser | Kết quả thường trả về |
|---|---|---|
| `Program` | `parseProgram()` | `ProgramNode` |
| `Statement` | `parseStatement()` | Một loại `Statement` |
| `VariableDecl` | `parseVariableDecl()` | `VariableDeclaration` |
| `IfStatement` | `parseIfStatement()` | `IfStatement` |
| `ExprStatement` | `parseExprStatement()` | `ExpressionStatement` |
| `Block` | `parseBlock()` | `BlockStatement` |
| `Expression` | `parseExpression()` | Một node biểu thức |

Các hàm gọi nhau theo cấu trúc grammar. Ví dụ, `parseProgram` gọi `parseStatement`; `parseIfStatement` gọi `parseExpression` và `parseBlock`; `parseBlock` lại gọi `parseStatement` nhiều lần.

## 4. Xây dựng bộ khung parser

Một parser thường giữ danh sách token và vị trí token hiện tại. Các hàm tiện ích cơ bản giúp việc đọc token thống nhất.

### 4.1. Con trỏ token

Giả sử parser có:

```text
tokens: danh sách token kết thúc bằng EOF
current: chỉ số token đang xét
```

Các thao tác thường gặp:

- `peek()`: xem token hiện tại mà không tiêu thụ.
- `previous()`: lấy token vừa tiêu thụ.
- `advance()`: tiêu thụ token hiện tại và chuyển sang token tiếp theo.
- `check(kind)`: kiểm tra token hiện tại có loại mong muốn không.
- `match(kinds...)`: nếu token hiện tại khớp một trong các loại, tiêu thụ và trả true.
- `consume(kind, message)`: yêu cầu token có loại xác định; nếu không, báo lỗi.
- `isAtEnd()`: kiểm tra đã gặp EOF chưa.

Ví dụ mã giả:

```text
peek():
    return tokens[current]

advance():
    if not isAtEnd():
        current = current + 1
    return previous()

check(kind):
    if isAtEnd():
        return kind == EOF
    return peek().kind == kind

match(kinds...):
    for kind in kinds:
        if check(kind):
            advance()
            return true
    return false

consume(kind, message):
    if check(kind):
        return advance()
    raise ParseError(message, peek().span)
```

Đây là mô hình minh họa. Trong triển khai thực tế, cần xử lý token EOF, vị trí nguồn và việc không được tăng con trỏ vượt quá cuối danh sách.

### 4.2. Hàm parseProgram

`Program` thường là ký hiệu bắt đầu. Hàm tương ứng lặp qua các câu lệnh đến khi gặp EOF:

```text
parseProgram():
    statements = []
    while not isAtEnd():
        statements.append(parseStatement())
    return ProgramNode(statements)
```

Vòng lặp này giả định mỗi lần `parseStatement` thành công sẽ tiêu thụ ít nhất một token hoặc kết thúc đầu vào. Nếu một nhánh parser không tiến con trỏ khi gặp token không hợp lệ và không phát sinh lỗi, vòng lặp có thể bị mắc kẹt.

### 4.3. Hàm parseStatement

Parser chọn loại câu lệnh dựa trên token đầu tiên:

```text
parseStatement():
    if match(LET):
        return finishVariableDecl()
    if match(IF):
        return finishIfStatement()
    return parseExprStatement()
```

Ở đây, `LET` và `IF` là token mở đầu rõ ràng. Nếu grammar có nhiều quy tắc cùng bắt đầu bằng `IDENTIFIER`, parser có thể cần lookahead nhiều token hoặc thay đổi grammar để chọn nhánh không mơ hồ.

## 5. Ví dụ parser cho khai báo và khối lệnh

Xét grammar:

```text
VariableDecl -> "let" IDENTIFIER "=" Expression ";"
IfStatement  -> "if" "(" Expression ")" Block
Block        -> "{" Statement* "}"
```

Có thể triển khai như sau:

```text
parseVariableDecl():
    name = consume(IDENTIFIER, "Expected variable name")
    consume(EQUAL, "Expected = after variable name")
    initializer = parseExpression()
    consume(SEMICOLON, "Expected ; after declaration")
    return VariableDeclaration(name, initializer)

parseIfStatement():
    consume(LEFT_PAREN, "Expected ( after if")
    condition = parseExpression()
    consume(RIGHT_PAREN, "Expected ) after condition")
    thenBranch = parseBlock()
    return IfStatement(condition, thenBranch)

parseBlock():
    consume(LEFT_BRACE, "Expected {")
    statements = []
    while not check(RIGHT_BRACE) and not isAtEnd():
        statements.append(parseStatement())
    consume(RIGHT_BRACE, "Expected } after block")
    return BlockStatement(statements)
```

Các hàm không cần biết cách đọc từng ký tự. Chúng phối hợp qua token stream và trả về node AST tương ứng.

### 5.1. Xử lý cấu trúc lồng nhau

Khi `parseBlock` gọi `parseStatement`, và `parseIfStatement` bên trong lại gọi `parseBlock`, parser xử lý được các khối lồng nhau tự nhiên:

```text
if (order.isPaid) {
    if (order.total > 100) {
        approve(order);
    }
}
```

Mỗi lời gọi `parseBlock` quản lý một khối riêng. Khi gặp dấu `}`, hàm hiện tại kết thúc và trả quyền điều khiển cho hàm gọi nó.

## 6. Phân tích biểu thức và thứ tự ưu tiên

Biểu thức là phần thường phức tạp nhất của parser vì có nhiều toán tử, mức ưu tiên và tính kết hợp. Một cách triển khai recursive descent phổ biến là chia grammar thành nhiều tầng precedence.

Ví dụ grammar:

```text
Expression  -> Equality
Equality    -> Comparison (("==" | "!=") Comparison)*
Comparison  -> Term ((">" | ">=" | "<" | "<=") Term)*
Term        -> Factor (("+" | "-") Factor)*
Factor      -> Unary (("*" | "/") Unary)*
Unary       -> ("!" | "-") Unary | Primary
Primary     -> NUMBER | STRING | IDENTIFIER | "(" Expression ")"
```

Mỗi tầng gọi tầng có precedence cao hơn. `Equality` là tầng thấp hơn `Comparison`; `Factor` có precedence cao hơn `Term`; `Primary` là thành phần cơ bản.

### 6.1. Vì sao phải chia tầng precedence?

Xét biểu thức:

```text
2 + 3 * 4
```

Nếu phép nhân có precedence cao hơn phép cộng, AST phải là:

```text
Add
├── Number(2)
└── Multiply
    ├── Number(3)
    └── Number(4)
```

Kết quả là 14. Nếu parser nhóm từ trái sang phải mà không xét precedence, nó có thể tạo `Multiply(Add(2, 3), 4)` và cho kết quả 20. Cấu trúc grammar vì vậy quyết định trực tiếp cách nhóm biểu thức.

### 6.2. Dùng vòng lặp cho toán tử kết hợp trái

Quy tắc như:

```text
Term -> Factor (("+" | "-") Factor)*
```

có thể triển khai bằng vòng lặp:

```text
parseTerm():
    expr = parseFactor()
    while match(PLUS, MINUS):
        operator = previous()
        right = parseFactor()
        expr = Binary(expr, operator, right)
    return expr
```

Với `a - b - c`, vòng lặp tạo AST:

```text
Subtract
├── Subtract
│   ├── a
│   └── b
└── c
```

Đây là kết hợp trái: `(a - b) - c`. Cách xây dựng `Binary` mới với biểu thức hiện tại ở bên trái bảo đảm cây có hình dạng đó.

### 6.3. Toán tử kết hợp phải

Một số toán tử có thể kết hợp phải, chẳng hạn phép lũy thừa trong một số ngôn ngữ hoặc phép gán. Khi đó, parser thường gọi đệ quy ở phía phải.

Ví dụ:

```text
Assignment -> IDENTIFIER "=" Assignment | Equality
```

Với `a = b = c`, cách phân tích trên có thể tạo `a = (b = c)`. Parser cần bảo đảm vế trái của phép gán là một đích gán hợp lệ, ví dụ identifier hoặc member access có thể ghi.

### 6.4. Toán tử một ngôi

Quy tắc:

```text
Unary -> ("!" | "-") Unary | Primary
```

cho phép các biểu thức như `!!enabled`, `-amount` và `-(a + b)`. Việc gọi `parseUnary` đệ quy giúp xử lý nhiều toán tử một ngôi liên tiếp.

## 7. Đệ quy trái và cách xử lý

Recursive descent trực tiếp không xử lý tốt grammar đệ quy trái. Đệ quy trái xảy ra khi một nonterminal có thể xuất hiện ở đầu vế phải của chính quy tắc đó.

Ví dụ:

```text
Expression -> Expression "+" Term
Expression -> Term
```

Khi `parseExpression` gọi `parseExpression` trước khi tiêu thụ token nào, hàm sẽ gọi chính nó mãi mãi và có thể tràn stack.

### 7.1. Loại bỏ đệ quy trái trực tiếp

Với grammar tổng quát:

```text
A -> A alpha | beta
```

có thể chuyển thành:

```text
A      -> beta A_tail
A_tail -> alpha A_tail | epsilon
```

Trong đó `epsilon` biểu thị chuỗi rỗng. Áp dụng vào biểu thức cộng:

```text
Expression -> Term ExpressionTail
ExpressionTail -> "+" Term ExpressionTail | epsilon
```

Khi triển khai recursive descent, vòng lặp thường là cách viết đơn giản hơn cho phần tail:

```text
parseExpression():
    expr = parseTerm()
    while match(PLUS):
        right = parseTerm()
        expr = Add(expr, right)
    return expr
```

Kết quả vẫn tạo AST kết hợp trái cho chuỗi phép cộng.

### 7.2. Đệ quy trái gián tiếp

Đệ quy trái gián tiếp xuất hiện khi một nonterminal gọi qua một hoặc nhiều nonterminal khác rồi quay lại chính nó.

```text
A -> B alpha
B -> A beta | gamma
```

Ở đây, `A` có thể bắt đầu bằng `B`, còn `B` có thể bắt đầu bằng `A`. Việc loại bỏ đệ quy trái gián tiếp phức tạp hơn; cần biến đổi grammar theo thứ tự và phân tích các quan hệ phụ thuộc giữa nonterminal.

Không nên chỉ thay một quy tắc mà không kiểm tra các đường dẫn gọi gián tiếp. Một grammar có chu trình nullable cũng có thể gây vấn đề tương tự nếu parser không tiêu thụ token trước khi quay lại.

### 7.3. Giữ nguyên tính kết hợp của toán tử

Khi loại bỏ đệ quy trái, cần bảo đảm AST vẫn thể hiện đúng tính kết hợp ban đầu. Grammar được biến đổi có thể dùng tail đệ quy phải, nhưng parser phải xây dựng AST theo kiểu lặp trái nếu toán tử gốc kết hợp trái.

## 8. Left factoring và lựa chọn nhánh

Left factoring (tách tiền tố chung) là kỹ thuật biến đổi grammar để các nhánh có chung phần đầu được tách ra. Nó giúp parser quyết định nhánh sau khi đọc đủ token cần thiết.

Ví dụ grammar:

```text
Statement -> IDENTIFIER "=" Expression ";"
Statement -> IDENTIFIER "(" Arguments ")" ";"
```

Cả hai nhánh bắt đầu bằng `IDENTIFIER`. Sau khi đọc identifier, parser cần xem token tiếp theo để biết đó là phép gán hay lời gọi hàm.

Có thể left factor:

```text
Statement -> IDENTIFIER StatementTail
StatementTail -> "=" Expression ";"
              | "(" Arguments ")" ";"
```

Trong code, parser đọc identifier trước rồi chọn nhánh dựa vào token tiếp theo. Cách này giảm sự mơ hồ và tránh phải quay lui.

### 8.1. Khi nào cần lookahead nhiều hơn một token?

Một số grammar có chung tiền tố dài hơn một token. Ví dụ, hai cấu trúc đều bắt đầu bằng `IDENTIFIER DOT IDENTIFIER`, sau đó mới khác nhau. Parser có thể cần lookahead nhiều token hoặc điều chỉnh grammar để làm nhánh lựa chọn rõ hơn.

Lookahead là số token parser xem trước để chọn quy tắc mà chưa tiêu thụ chúng. Parser LL(1) chỉ cần một token; parser khác có thể dùng LL(k) với k lớn hơn hoặc dùng chiến lược khác.

### 8.2. Tránh backtracking không cần thiết

Backtracking xảy ra khi parser thử một nhánh, ghi nhận vị trí, và nếu thất bại thì quay về vị trí cũ để thử nhánh khác. Nó có thể hữu ích với grammar linh hoạt, nhưng có thể làm parser khó dự đoán và gây chi phí lớn nếu nhiều nhánh cùng thất bại.

Left factoring và lookahead rõ ràng giúp parser chọn nhánh sớm. Với DSL cấu hình hoặc rule, grammar rõ thường giúp diagnostic tốt hơn và giảm trường hợp parser đọc một phần rồi mới phát hiện nhánh sai.

## 9. FIRST và FOLLOW trong parser dự đoán

FIRST và FOLLOW là các tập dùng trong phân tích cú pháp dự đoán, đặc biệt với grammar LL(1). Chúng giúp xác định token nào có thể bắt đầu một cấu trúc và token nào có thể xuất hiện ngay sau cấu trúc đó.

### 9.1. FIRST

`FIRST(X)` là tập terminal có thể xuất hiện đầu tiên trong chuỗi được sinh từ ký hiệu X. Nếu X có thể sinh chuỗi rỗng, FIRST còn chứa epsilon.

Ví dụ:

```text
Statement -> VariableDecl | IfStatement | ExprStatement
VariableDecl -> "let" IDENTIFIER "=" Expression ";"
IfStatement -> "if" "(" Expression ")" Block
ExprStatement -> Expression ";"
```

`FIRST(VariableDecl)` chứa `LET`; `FIRST(IfStatement)` chứa `IF`. Nếu `FIRST(ExprStatement)` có thể bắt đầu bằng `IDENTIFIER`, `NUMBER`, `STRING`, `(` hoặc các toán tử một ngôi, parser có thể dùng token hiện tại để chọn nhánh.

### 9.2. FOLLOW

`FOLLOW(A)` là tập terminal có thể xuất hiện ngay sau một lần xuất hiện của nonterminal A trong một dẫn xuất hợp lệ. FOLLOW giúp quyết định khi nào một cấu trúc nullable hoặc danh sách lặp đã kết thúc.

Ví dụ, trong:

```text
Block -> "{" Statement* "}"
```

parser tiếp tục đọc `Statement` cho đến khi gặp `RIGHT_BRACE` hoặc EOF bất thường. `RIGHT_BRACE` là token đánh dấu kết thúc danh sách statement trong block.

### 9.3. Điều kiện chọn nhánh LL(1)

Với các lựa chọn `A -> alpha | beta`, parser LL(1) cần phân biệt được các nhánh bằng một token lookahead. Về trực giác, các tập FIRST của những nhánh phải không xung đột; nếu một nhánh có thể sinh epsilon, FOLLOW của A cũng tham gia quyết định.

Nếu các tập lựa chọn xung đột, grammar có thể cần left factoring, loại bỏ đệ quy trái hoặc dùng lookahead nhiều hơn. Không phải mọi grammar đều có thể trở thành LL(1) mà không thay đổi hình thức hoặc giới hạn cú pháp.

## 10. Tạo AST ngay trong quá trình phân tích

Recursive descent parser thường tạo AST node khi một hàm hoàn thành việc phân tích cấu trúc. Điều này giúp parser vừa xác nhận cú pháp vừa xây dựng biểu diễn cho các bước semantic analysis.

Ví dụ node biểu thức:

```text
Expr
├── NumberLiteral(value)
├── StringLiteral(value)
├── Identifier(name)
├── Unary(operator, operand)
├── Binary(left, operator, right)
└── Call(callee, arguments)
```

Parser của phép cộng có thể tạo `Binary` như sau:

```text
parseTerm():
    expr = parseFactor()
    while match(PLUS, MINUS):
        op = previous()
        right = parseFactor()
        expr = Binary(expr, op, right)
    return expr
```

AST lưu cấu trúc ngữ nghĩa cần thiết; các chi tiết như khoảng trắng có thể không được giữ. Nếu formatter hoặc IDE cần bảo toàn văn bản gốc, parser có thể lưu source span hoặc dùng CST/token stream song song.

### 10.1. Gắn vị trí nguồn

Mỗi token thường có source span gồm tệp, offset, dòng và cột. Khi tạo node, parser có thể kết hợp span của token đầu và token cuối để node biết nó đến từ đoạn nào trong mã nguồn.

Thông tin này giúp diagnostic chỉ đúng biểu thức lỗi, giúp IDE chọn vùng văn bản và giúp các công cụ refactoring liên kết node với mã nguồn.

Với Unicode, offset byte, code unit và cột hiển thị có thể khác nhau. Lexer, parser và editor cần thống nhất cách biểu diễn vị trí.

## 11. Ví dụ parser biểu thức hoàn chỉnh hơn

Giả sử DSL hỗ trợ số, tên, ngoặc, toán tử một ngôi, nhân/chia và cộng/trừ. Grammar:

```text
Expression -> Term
Term       -> Factor (("+" | "-") Factor)*
Factor     -> Unary (("*" | "/") Unary)*
Unary      -> ("-" | "!") Unary | Primary
Primary    -> NUMBER | IDENTIFIER | "(" Expression ")"
```

Mã giả:

```text
parseExpression():
    return parseTerm()

parseTerm():
    expr = parseFactor()
    while match(PLUS, MINUS):
        operator = previous()
        right = parseFactor()
        expr = Binary(expr, operator, right)
    return expr

parseFactor():
    expr = parseUnary()
    while match(STAR, SLASH):
        operator = previous()
        right = parseUnary()
        expr = Binary(expr, operator, right)
    return expr

parseUnary():
    if match(MINUS, BANG):
        operator = previous()
        operand = parseUnary()
        return Unary(operator, operand)
    return parsePrimary()

parsePrimary():
    if match(NUMBER):
        return NumberLiteral(previous().value)
    if match(IDENTIFIER):
        return Identifier(previous().text)
    if match(LEFT_PAREN):
        expr = parseExpression()
        consume(RIGHT_PAREN, "Expected )")
        return expr
    raise ParseError("Expected expression", peek().span)
```

Với biểu thức `-2 + 3 * (4 - 1)`, parser tạo cây tương ứng với unary minus ở nhánh trái, phép nhân ở nhánh phải của phép cộng, và biểu thức trong ngoặc được phân tích độc lập. Cây phản ánh đúng precedence mà grammar quy định.

## 12. Đệ quy và giới hạn độ sâu

Recursive descent sử dụng call stack của ngôn ngữ triển khai. Cấu trúc lồng nhau sâu có thể tạo nhiều lời gọi đệ quy:

```text
((((((((value))))))))
```

Hoặc biểu thức một ngôi dài:

```text
!!!!!!!!!!!!!!!!enabled
```

Với đầu vào quá sâu, parser có thể tràn stack. DSL nhận mã nguồn không đáng tin cậy cần cân nhắc giới hạn độ sâu, chuyển một số vòng lặp đệ quy thành vòng lặp thông thường hoặc dùng stack tường minh.

Không phải mọi cấu trúc lồng đều cần đệ quy. Danh sách câu lệnh, tham số hoặc toán tử kết hợp trái thường có thể được xử lý bằng vòng lặp. Đệ quy phù hợp tự nhiên với cấu trúc lồng như ngoặc, khối hoặc cây biểu thức.

## 13. Xử lý và phục hồi lỗi cú pháp

Parser cần phát hiện lỗi và cung cấp thông báo đủ rõ để người dùng sửa. Một parser chỉ dừng ở lỗi đầu tiên có thể phù hợp với compiler đơn giản, nhưng IDE thường cần tiếp tục phân tích để hiển thị nhiều lỗi trong cùng lần mở tệp.

### 13.1. Báo lỗi tại điểm mong đợi

Ví dụ DSL:

```text
let total price * quantity;
```

Parser đang chờ `=` sau tên biến nhưng gặp `price`. Diagnostic có thể là:

```text
Expected "=" after variable name "total".
Found identifier "price" at line 1, column 11.
```

Thông báo nên nêu token mong đợi, token thực tế và vị trí. Tránh chỉ báo lỗi chung chung như “invalid syntax” nếu có thể cung cấp ngữ cảnh.

### 13.2. Panic-mode synchronization

Một kỹ thuật phục hồi phổ biến là bỏ qua token cho đến khi gặp điểm đồng bộ (synchronization token) như dấu chấm phẩy, dấu đóng khối hoặc từ khóa mở đầu khai báo tiếp theo.

Ví dụ:

```text
synchronize():
    advance()
    while not isAtEnd():
        if previous().kind == SEMICOLON:
            return
        if peek().kind in {LET, IF, RULE, ENTITY} :
            return
        advance()
```

Ý tưởng là bỏ qua phần có khả năng đã hỏng cho đến một ranh giới mà parser có thể tiếp tục. Bộ token đồng bộ cần phù hợp với grammar DSL; dùng quá rộng có thể bỏ mất cấu trúc hợp lệ, dùng quá hẹp có thể khiến parser tiếp tục ở sai vị trí.

### 13.3. Error node

Parser dành cho IDE có thể tạo `ErrorExpression` hoặc `ErrorStatement` để giữ cấu trúc phần còn lại. Các bước sau phải biết cách xử lý node lỗi và tránh phát sinh hàng loạt lỗi thứ cấp gây nhiễu.

### 13.4. Không che giấu lỗi cú pháp bằng giá trị mặc định

Không nên tự tạo giá trị mặc định cho token bắt buộc bị thiếu nếu việc đó làm chương trình có nghĩa khác. Ví dụ, thiếu biểu thức sau `=` không nên tự biến thành số 0. Có thể tạo error node để tiếp tục phân tích, nhưng phải giữ trạng thái lỗi rõ ràng.

## 14. Recursive descent có backtracking

Trong một số grammar, parser không thể quyết định nhánh ngay bằng token hiện tại. Một cách là lưu vị trí, thử phân tích một nhánh, rồi quay lại nếu thất bại.

```text
tryAlternativeA():
    saved = current
    if parseAlternativeA succeeds:
        return result
    current = saved
    return parseAlternativeB()
```

Backtracking có thể giúp xử lý grammar phức tạp, nhưng cần chú ý:

- Parser phải khôi phục đầy đủ trạng thái khi thử thất bại, không chỉ vị trí token nếu còn thay đổi symbol table hoặc diagnostic.
- Nhiều nhánh có tiền tố chung có thể khiến cùng một đoạn token bị phân tích lặp lại.
- Trong trường hợp xấu, thời gian có thể tăng rất nhanh.
- Diagnostic từ nhánh thử thất bại cần được quản lý để không báo lỗi giả khi một nhánh khác thành công.

Với DSL có grammar do nhóm thiết kế kiểm soát, thường nên giảm nhu cầu backtracking bằng left factoring và quy tắc lookahead rõ ràng.

### 14.1. Recursive descent dự đoán so với parser backtracking

| Đặc điểm | Predictive recursive descent | Recursive descent có backtracking |
|---|---|---|
| Chọn nhánh | Dựa trên lookahead và grammar đã chuẩn bị | Thử nhánh rồi quay lại nếu thất bại |
| Grammar | Thường LL(1) hoặc LL(k) phù hợp | Có thể xử lý một số grammar khó dự đoán hơn |
| Hiệu năng | Thường dễ dự đoán, tuyến tính với grammar phù hợp | Có thể lặp phân tích và tăng chi phí |
| Độ phức tạp triển khai | Cần chuẩn hóa grammar và bảng lựa chọn rõ | Cần quản lý trạng thái và lỗi khi quay lui |
| Ứng dụng | DSL có cú pháp được thiết kế chủ động | Grammar linh hoạt hoặc thử nghiệm, khi backtracking có kiểm soát |

## 15. Pratt parsing và precedence climbing

Khi biểu thức có nhiều toán tử, một cách khác để triển khai parser top-down là Pratt parsing hoặc precedence climbing. Chúng thường được dùng cùng phong cách recursive descent nhưng tổ chức phân tích biểu thức dựa trên độ ưu tiên của toán tử thay vì tạo một hàm riêng cho từng tầng precedence.

### 15.1. Ý tưởng precedence climbing

Parser nhận một mức precedence tối thiểu. Nó phân tích toán hạng đầu, sau đó tiếp tục đọc toán tử nếu precedence của toán tử đủ cao. Toán hạng phải được phân tích với mức precedence tương ứng để bảo đảm cách nhóm.

Ví dụ, với `2 + 3 * 4`, parser xử lý `*` ở mức ưu tiên cao hơn `+`, nên cây vẫn là `2 + (3 * 4)`.

### 15.2. Pratt parser

Pratt parser dùng các hàm xử lý token ở vị trí prefix và infix. Ví dụ, dấu `-` ở đầu biểu thức có thể là toán tử một ngôi; dấu `-` sau một biểu thức có thể là toán tử trừ hai ngôi.

| Vị trí | Ví dụ | Vai trò |
|---|---|---|
| Prefix | `-amount` | Phân tích toán tử một ngôi |
| Infix | `a - b` | Phân tích phép trừ hai ngôi |
| Call/postfix | `calculate(x)` | Gọi hàm sau biểu thức callee |
| Member access | `order.total` | Truy cập thuộc tính sau biểu thức |

Pratt parsing thường gọn khi DSL có nhiều toán tử và cú pháp hậu tố. Tuy nhiên, recursive descent phân tầng precedence vẫn là lựa chọn dễ hiểu và đủ tốt cho nhiều DSL nhỏ hoặc vừa.

## 16. Phân tích cú pháp danh sách và dấu phân cách

DSL thường có danh sách tham số, thuộc tính, phần tử hoặc câu lệnh. Recursive descent xử lý chúng bằng vòng lặp cho đến khi gặp dấu kết thúc.

Ví dụ grammar:

```text
Arguments -> Expression ("," Expression)* | epsilon
```

Parser:

```text
parseArguments():
    args = []
    if check(RIGHT_PAREN):
        return args
    args.append(parseExpression())
    while match(COMMA):
        args.append(parseExpression())
    return args
```

Khi gọi hàm, parser có thể dùng:

```text
parseCall():
    consume(LEFT_PAREN, "Expected (")
    args = parseArguments()
    consume(RIGHT_PAREN, "Expected )")
    return Call(callee, args)
```

Grammar cần quyết định có cho phép dấu phẩy cuối hay không. Nếu cho phép, parser cần xử lý trường hợp dấu phẩy ngay trước `RIGHT_PAREN`; nếu không, trường hợp đó phải tạo diagnostic.

## 17. Những vấn đề đặc thù khi xây dựng parser cho DSL

### 17.1. Keyword và identifier

Lexer thường phân loại từ khóa như `entity`, `rule`, `when`, `then` thành token riêng. Nếu DSL cho phép dùng từ khóa làm tên trong một số ngữ cảnh, grammar cần quy định rõ hoặc cung cấp cơ chế escape identifier.

### 17.2. Cú pháp khai báo và cú pháp biểu thức

Một DSL có thể dùng tên ở đầu câu lệnh để bắt đầu khai báo hoặc biểu thức. Nếu hai cấu trúc có tiền tố giống nhau, parser cần lookahead hoặc grammar factoring để tránh chọn nhầm.

### 17.3. Kiểu dữ liệu và generic

Các kiểu như `List<Order>` có dấu `<` và `>` cũng được dùng làm toán tử so sánh. Parser có thể cần ngữ cảnh hoặc quy tắc grammar để phân biệt dấu này trong khai báo kiểu và biểu thức.

### 17.4. Ngữ cảnh đặc biệt

Một số DSL có cú pháp chỉ hợp lệ bên trong `rule`, `workflow` hoặc `entity`. Parser có thể nhận diện cấu trúc cú pháp trước, còn semantic analyzer kiểm tra việc dùng đúng ngữ cảnh. Không nên nhồi quá nhiều quy tắc miền vào parser nếu chúng thuộc semantic validation.

### 17.5. Unicode và source location

Lexer phải giải mã văn bản trước khi parser nhận token. Source span của token cần được giữ để parser báo lỗi đúng vị trí, đặc biệt với ký tự nhiều byte hoặc ký tự ngoài BMP. Parser nên dựa vào token kind, không so sánh trực tiếp chuỗi byte của tệp nguồn.

## 18. Độ phức tạp và hiệu năng

Với predictive recursive descent và grammar phù hợp, mỗi token thường được tiêu thụ một số lần hằng định. Thời gian phân tích thường là O(n) theo số token. Bộ nhớ phụ thuộc AST được tạo và độ sâu lời gọi đệ quy.

Các yếu tố ảnh hưởng:

- Số token đầu vào.
- Độ sâu cấu trúc lồng nhau.
- Số lượng lookahead cần thiết.
- Backtracking và số lần thử lại nhánh.
- Chi phí tạo AST node và giữ source span.
- Cách xử lý lỗi và phục hồi.

Với đầu vào có cấu trúc lồng sâu, độ sâu stack có thể tăng theo chiều sâu cú pháp. Với backtracking, thời gian có thể tăng đáng kể trong trường hợp xấu. Nếu DSL xử lý tệp lớn hoặc đầu vào không đáng tin cậy, nên giới hạn kích thước và độ sâu, đồng thời tránh grammar có nhiều nhánh mơ hồ.

## 19. Quy trình phát triển recursive descent parser

Một quy trình thực tế có thể gồm:

1. Xác định các cấu trúc DSL cần hỗ trợ và viết grammar cho chúng.
2. Phân biệt terminal, nonterminal, token và ký hiệu bắt đầu.
3. Kiểm tra grammar có đệ quy trái hoặc tiền tố chung gây khó chọn nhánh không.
4. Loại bỏ đệ quy trái và áp dụng left factoring khi cần.
5. Xác định precedence, associativity và lookahead của biểu thức.
6. Viết hàm parser cho từng nhóm nonterminal.
7. Tạo AST node tại những điểm hoàn thành cấu trúc.
8. Giữ source span để phục vụ diagnostics và IDE.
9. Quy định cách phát hiện lỗi và đồng bộ để tiếp tục phân tích.
10. Kết nối parser với semantic analysis và kiểm tra kiểu.

Không cần chuyển mọi grammar thành LL(1) bằng mọi giá. Mục tiêu là chọn một grammar dễ hiểu, có hành vi xác định và phù hợp với cách triển khai. Nếu grammar cần parser generator hoặc kỹ thuật khác, cũng nên cân nhắc thay vì ép recursive descent.

## 20. Kết luận

Recursive descent là kỹ thuật top-down trong đó các hàm parser tương ứng với các quy tắc grammar và gọi nhau để phân tích cấu trúc lồng nhau. Nó phù hợp với nhiều DSL vì dễ đọc, dễ kiểm soát và có thể tạo AST trực tiếp trong quá trình phân tích.

Để parser hoạt động đúng, grammar cần được thiết kế phù hợp: xử lý đệ quy trái, tách tiền tố chung, xác định lookahead, precedence và associativity. Các hàm tiện ích như `peek`, `match`, `consume` giúp quản lý token nhất quán; source span và chiến lược phục hồi lỗi giúp parser thân thiện hơn với người dùng.

Với DSL có cú pháp vừa phải, recursive descent thường là lựa chọn cân bằng giữa tính đơn giản và khả năng mở rộng. Khi biểu thức có nhiều toán tử, có thể kết hợp với precedence climbing hoặc Pratt parsing. Điều quan trọng là grammar và semantics phải rõ ràng để cùng một chuỗi token luôn tạo ra cấu trúc cú pháp mà người viết mong đợi.

# CST và parse tree

## 1. Vị trí của CST và parse tree trong quá trình phân tích DSL

Ngôn ngữ chuyên biệt miền (*Domain-Specific Language — DSL*) thường được mô tả bằng một grammar. Grammar quy định chuỗi nguồn nào hợp lệ và các thành phần cú pháp có thể kết hợp với nhau ra sao. Khi người dùng viết một tài liệu DSL, parser đọc chuỗi token và xây dựng một cấu trúc cây để biểu diễn cách các thành phần đó khớp với grammar.

Hai khái niệm thường gặp là:

- **Concrete Syntax Tree (CST):** cây cú pháp cụ thể, giữ lại cấu trúc cú pháp chi tiết của chương trình theo grammar, thường bao gồm các nút tương ứng với quy tắc grammar và các token đầu cuối như từ khóa, dấu ngoặc, toán tử và dấu phân cách.
- **Parse tree:** cây được parser tạo ra khi phân tích đầu vào. Trong nhiều công cụ và tài liệu, parse tree được dùng gần như đồng nghĩa với CST, đặc biệt khi cây thể hiện các production của grammar và terminal tokens.

Cách dùng thuật ngữ có thể khác nhau giữa các tài liệu và framework. Một số framework gọi trực tiếp cây do parser sinh ra là parse tree; một số tài liệu dùng parse tree để chỉ cây phản ánh grammar, còn CST nhấn mạnh việc giữ lại chi tiết cú pháp cụ thể. Khi đọc tài liệu một công cụ, cần xem cấu trúc cây thực tế thay vì chỉ dựa vào tên gọi.

CST và parse tree giúp trả lời câu hỏi: **văn bản đầu vào được phân tích thành những thành phần cú pháp nào và chúng liên kết với nhau ra sao?** Đây là nền tảng cho việc xây AST, kiểm tra ngữ nghĩa, định dạng mã, tô màu cú pháp, thông báo lỗi và các công cụ hỗ trợ người viết DSL.

Một pipeline điển hình:

```text
Văn bản DSL
    |
    v
Lexer / bộ phân tích từ vựng
    |
    v
Danh sách token
    |
    v
Parser + Grammar
    |
    v
CST / Parse tree
    |
    +----------------------+
    |                      |
    v                      v
AST / mô hình miền     Syntax diagnostics
    |
    v
Semantic analysis
    |
    v
Interpreter / Compiler / Code generator
```

Không phải hệ thống nào cũng cần tạo cả CST lẫn AST. Với DSL nhỏ, parse tree có thể được duyệt trực tiếp. Với DSL lớn hoặc cần nhiều công cụ phân tích, một bước chuyển từ CST sang AST thường giúp tách chi tiết cú pháp khỏi mô hình ngữ nghĩa.

## 2. Grammar, production và các thành phần của cây

### 2.1. Grammar mô tả cấu trúc

Grammar thường gồm các quy tắc (*production rules*). Mỗi quy tắc mô tả cách một thành phần cú pháp được tạo thành từ các thành phần nhỏ hơn.

Ví dụ grammar đơn giản cho phép gán giá trị:

```text
Statement  ::= Identifier "=" Expression ";"
Expression ::= Number
             | Identifier
Identifier ::= Letter (Letter | Digit | "_")*
Number     ::= Digit+
```

Với câu lệnh:

```text
total = 42;
```

parser có thể nhận diện:

- Một `Statement`.
- Phần bên trái là `Identifier` có tên `total`.
- Token `=` là toán tử gán.
- Phần bên phải là `Expression` chứa `Number` với giá trị `42`.
- Token `;` kết thúc câu lệnh.

Grammar không chỉ liệt kê token; nó mô tả quan hệ phân cấp giữa các nhóm token.

### 2.2. Nonterminal và terminal

Trong grammar:

- **Terminal** là ký hiệu đầu cuối do lexer cung cấp hoặc token cố định của ngôn ngữ, ví dụ `IDENTIFIER`, `NUMBER`, `PLUS`, `"if"` hoặc dấu ngoặc.
- **Nonterminal** là tên quy tắc cú pháp được mở rộng thành các thành phần khác, ví dụ `Expression`, `Statement` hoặc `FunctionDeclaration`.

Trong parse tree, nonterminal thường trở thành các nút bên trong; terminal thường trở thành các nút lá. Một số parser API biểu diễn token đầu cuối bằng đối tượng riêng thay vì node thông thường.

### 2.3. Gốc, nút trong và nút lá

Một cây cú pháp thường có:

- **Root:** nút đại diện cho quy tắc bắt đầu (*start rule*) của grammar.
- **Internal nodes:** nút tương ứng với các nonterminal hoặc nhóm cấu trúc.
- **Leaf nodes:** token đầu cuối được tiêu thụ trong quá trình phân tích.
- **Edges:** quan hệ cha-con thể hiện thứ tự và cấu trúc lồng nhau.

Thứ tự các nút con thường phản ánh thứ tự xuất hiện trong nguồn. Một số grammar có quy tắc đệ quy hoặc lặp, vì vậy một node có thể có nhiều node con cùng loại.

## 3. Ví dụ xây dựng parse tree

### 3.1. Biểu thức cộng và nhân

Xét grammar biểu thức:

```text
Expression ::= Term (("+" | "-") Term)*
Term       ::= Factor (("*" | "/") Factor)*
Factor     ::= Number | "(" Expression ")"
Number     ::= DIGIT+
```

Grammar chia biểu thức thành các mức:

- `Expression` xử lý phép cộng và trừ.
- `Term` xử lý phép nhân và chia.
- `Factor` xử lý số hoặc biểu thức trong ngoặc.

Cách phân tầng này thể hiện độ ưu tiên: phép nhân và chia nằm trong `Term`, nên được nhóm trước phép cộng và trừ.

Với đầu vào:

```text
2 + 3 * 4
```

một parse tree giản lược có thể là:

```text
Expression
├── Term
│   └── Factor
│       └── Number("2")
├── PLUS("+")
└── Term
    ├── Factor
    │   └── Number("3")
    ├── STAR("*")
    └── Factor
        └── Number("4")
```

Cây cho thấy vế phải của phép cộng là một `Term` chứa phép nhân. Vì vậy, cấu trúc biểu diễn phép tính tương đương `2 + (3 * 4)`, không phải `(2 + 3) * 4`.

### 3.2. Biểu thức có dấu ngoặc

Với đầu vào:

```text
(2 + 3) * 4
```

cây có dạng khái quát:

```text
Expression
└── Term
    ├── Factor
    │   ├── LPAREN("(")
    │   ├── Expression
    │   │   ├── Term
    │   │   │   └── Factor
    │   │   │       └── Number("2")
    │   │   ├── PLUS("+")
    │   │   └── Term
    │   │       └── Factor
    │   │           └── Number("3")
    │   └── RPAREN(")")
    ├── STAR("*")
    └── Factor
        └── Number("4")
```

Dấu ngoặc xuất hiện trong cây cụ thể, vì chúng là token được grammar sử dụng để nhóm biểu thức. Cây thể hiện rõ phần biểu thức nào nằm trong ngoặc và phép nhân được áp dụng sau đó.

### 3.3. Ví dụ DSL nghiệp vụ

Giả sử một DSL mô tả quy tắc giảm giá:

```text
rule "gold-customer" {
    when customer.tier == "GOLD" and order.total >= 1000000
    then discount.percent = 10
}
```

Một grammar rút gọn có thể là:

```text
RuleFile       ::= RuleDeclaration*
RuleDeclaration ::= "rule" STRING "{" "when" Condition "then" Assignment "}"
Condition      ::= Comparison ("and" Comparison)*
Comparison     ::= QualifiedName Operator Literal
Assignment     ::= QualifiedName "=" Literal
QualifiedName  ::= IDENTIFIER ("." IDENTIFIER)*
Operator       ::= "==" | ">=" | "<=" | ">" | "<"
Literal        ::= STRING | NUMBER
```

Cây cú pháp giản lược:

```text
RuleFile
└── RuleDeclaration
    ├── RULE("rule")
    ├── STRING("gold-customer")
    ├── LBRACE("{")
    ├── WHEN("when")
    ├── Condition
    │   ├── Comparison
    │   │   ├── QualifiedName
    │   │   │   ├── IDENTIFIER("customer")
    │   │   │   ├── DOT(".")
    │   │   │   └── IDENTIFIER("tier")
    │   │   ├── EQ("==")
    │   │   └── STRING("GOLD")
    │   ├── AND("and")
    │   └── Comparison
    │       ├── QualifiedName
    │       │   ├── IDENTIFIER("order")
    │       │   ├── DOT(".")
    │       │   └── IDENTIFIER("total")
    │       ├── GE(">=")
    │       └── NUMBER("1000000")
    ├── THEN("then")
    ├── Assignment
    │   ├── QualifiedName
    │   │   ├── IDENTIFIER("discount")
    │   │   ├── DOT(".")
    │   │   └── IDENTIFIER("percent")
    │   ├── EQUAL("=")
    │   └── NUMBER("10")
    └── RBRACE("}")
```

Cây trên giúp thấy rõ quy tắc nào tạo ra mỗi thành phần. Nó vẫn giữ các dấu chấm, từ khóa và dấu ngoặc được dùng trong cú pháp, nên có thể truy ngược cấu trúc về văn bản nguồn.

## 4. CST, parse tree và AST khác nhau thế nào?

### 4.1. Abstract Syntax Tree

**Abstract Syntax Tree (AST)** là cây cú pháp trừu tượng, tập trung vào cấu trúc có ý nghĩa đối với chương trình. AST thường bỏ các chi tiết chỉ phục vụ cú pháp như dấu ngoặc không cần thiết, dấu chấm phẩy hoặc các nút trung gian phản ánh cách grammar được viết.

Với biểu thức:

```text
2 + 3 * 4
```

AST có thể là:

```text
Add
├── Number(2)
└── Multiply
    ├── Number(3)
    └── Number(4)
```

AST thể hiện phép cộng có hai toán hạng; toán hạng bên phải là phép nhân. Nó không cần giữ node `Term`, `Factor` hay token dấu cộng như các nút riêng nếu các chi tiết đó không cần cho ngữ nghĩa.

### 4.2. Bảng so sánh

| Tiêu chí | CST / parse tree | AST |
|---|---|---|
| Mục tiêu | Biểu diễn cách đầu vào khớp grammar | Biểu diễn cấu trúc có ý nghĩa |
| Nút | Thường có node cho production và terminal | Thường có node theo khái niệm ngôn ngữ |
| Dấu câu và keyword | Thường được giữ như terminal nodes | Thường được lược bỏ hoặc chuyển thành thuộc tính |
| Phụ thuộc grammar | Gắn khá chặt với cấu trúc grammar | Ít phụ thuộc hơn vào cách viết grammar |
| Kích thước | Thường lớn và chi tiết hơn | Thường gọn hơn |
| Truy vết về nguồn | Thuận tiện nếu giữ token và source span | Cần metadata nguồn nếu muốn truy ngược |
| Ứng dụng | Formatter, syntax tooling, refactoring cú pháp, diagnostics | Semantic analysis, tối ưu, diễn giải, sinh mã |
| Thay đổi grammar | Cấu trúc cây có thể thay đổi rõ rệt | Có thể giữ AST ổn định qua lớp chuyển đổi |

Không phải mọi CST đều lưu đầy đủ khoảng trắng và comment. Lexer thường bỏ qua whitespace hoặc đưa chúng vào hidden channel; comment có thể được bỏ qua, giữ riêng hoặc gắn vào token lân cận. Nếu cần tái tạo chính xác văn bản gốc, công cụ phải lưu trivia, token gốc và source range một cách có chủ đích.

### 4.3. Vì sao không dùng AST cho mọi việc?

AST rất phù hợp cho xử lý ngữ nghĩa, nhưng có thể không đủ thông tin để tái tạo cách người dùng viết chương trình. Ví dụ, hai biểu thức:

```text
total=(price*quantity);
total = price * quantity
```

có thể tạo ra AST tương đương. Nếu công cụ cần định dạng lại mà vẫn giữ comment, dấu ngoặc có chủ ý hoặc phong cách viết, chỉ AST có thể không đủ.

CST hoặc một cấu trúc cú pháp giữ token giúp công cụ biết vị trí dấu ngoặc, dấu phân cách và các chi tiết trình bày. Một kiến trúc phổ biến là giữ CST/token stream cho công cụ nguồn và chuyển sang AST cho các bước xử lý ngữ nghĩa.

## 5. Parse tree được tạo ra như thế nào?

### 5.1. Từ token đến cây

Parser thường nhận danh sách token do lexer tạo ra. Parser áp dụng grammar để xác định cách token kết hợp thành các quy tắc cú pháp.

Với một parser đệ quy xuống (*recursive descent parser*), mỗi nonterminal có thể tương ứng với một hàm. Hàm gọi các hàm khác theo production và tạo node khi quy tắc khớp.

Ví dụ giả mã:

```text
parseExpression():
    node = parseTerm()

    while nextToken is PLUS or MINUS:
        operator = consume()
        right = parseTerm()
        node = makeBinaryNode(node, operator, right)

    return node
```

`parseExpression` gọi `parseTerm` để đọc toán hạng đầu tiên. Khi gặp dấu cộng hoặc trừ, nó đọc toán hạng tiếp theo và thêm cấu trúc tương ứng. Cây được xây dựng theo thứ tự grammar.

### 5.2. Top-down và bottom-up parsing

Hai họ parser phổ biến:

- **Top-down parsing:** bắt đầu từ start rule và mở rộng xuống các quy tắc con để khớp token. Recursive descent và LL parsing thuộc nhóm này.
- **Bottom-up parsing:** bắt đầu từ token và kết hợp các phần nhỏ thành cấu trúc lớn hơn cho đến khi đạt start rule. LR và các biến thể shift-reduce thuộc nhóm này.

Cả hai cách đều có thể tạo parse tree. Việc chọn parser phụ thuộc grammar, công cụ, yêu cầu xử lý lỗi và năng lực triển khai. Parse tree là kết quả cấu trúc; nó không quy định duy nhất thuật toán parsing nào phải được dùng.

### 5.3. Parser generator

Parser generator nhận grammar rồi sinh parser và API truy cập cây. Một số công cụ phổ biến:

- **ANTLR:** sinh lexer/parser từ grammar và cung cấp parse tree, listener và visitor.
- **JavaCC:** sinh parser Java từ grammar; cách biểu diễn cây phụ thuộc cấu hình và mã hỗ trợ mà nhóm xây dựng.
- **Bison:** sinh parser, thường kết hợp với Flex hoặc lexer khác; nhóm có thể định nghĩa semantic value hoặc tự xây cây.
- **Tree-sitter:** sinh parser incremental và concrete syntax tree phù hợp cho công cụ editor và phân tích cú pháp khi đang gõ.

Các công cụ có mô hình grammar và API cây khác nhau. Không nên giả định mọi parser generator đều tự động tạo CST có đầy đủ node hoặc giữ trivia theo cùng một cách.

## 6. Duyệt parse tree: listener và visitor

Sau khi parser tạo cây, ứng dụng thường cần duyệt cây để xây AST, thu thập thông tin hoặc kiểm tra cấu trúc.

### 6.1. Listener

Listener thường dùng mô hình sự kiện: khi bộ duyệt đi vào hoặc đi ra một node, nó gọi callback tương ứng.

Ví dụ khái niệm:

```text
enterRuleDeclaration(node)
enterCondition(node)
exitCondition(node)
exitRuleDeclaration(node)
```

Listener phù hợp khi muốn xử lý cây theo cấu trúc có sẵn và thực hiện hành động khi gặp từng loại node. Trong ANTLR, listener thường được dùng với cơ chế walker có sẵn.

### 6.2. Visitor

Visitor cho phép định nghĩa hàm xử lý cho từng loại node và chủ động gọi visitor cho các node con. Nó thường phù hợp khi cần tính toán và trả về một kết quả từ mỗi node, ví dụ tạo AST hoặc đánh giá biểu thức.

Giả mã:

```text
visitAdd(node):
    left = visit(node.left)
    right = visit(node.right)
    return AddExpression(left, right)

visitNumber(node):
    return NumberExpression(node.value)
```

Visitor giúp kiểm soát thứ tự duyệt và kết quả trả về. Đổi lại, người triển khai cần tự gọi visitor cho các node con; nếu quên duyệt một nhánh, dữ liệu trong nhánh đó có thể bị bỏ sót.

### 6.3. So sánh listener và visitor

| Tiêu chí | Listener | Visitor |
|---|---|---|
| Cách hoạt động | Nhận callback khi walker đi qua node | Gọi hàm xử lý node một cách chủ động |
| Điều khiển thứ tự | Thường do walker quản lý | Người viết visitor điều khiển |
| Kết quả trả về | Thường tích lũy qua trạng thái bên ngoài | Có thể trả kết quả từ mỗi node |
| Phù hợp | Thu thập sự kiện, kiểm tra, ghi nhận cấu trúc | Chuyển đổi cây, tính giá trị, xây AST |
| Rủi ro | Khó kiểm soát trạng thái dùng chung nếu xử lý phức tạp | Có thể quên duyệt node con |

Lựa chọn phụ thuộc mục tiêu xử lý. Một ứng dụng có thể dùng listener để thu thập vị trí khai báo và visitor để chuyển parse tree thành AST.

## 7. CST và AST trong kiến trúc một DSL

Một kiến trúc có cả hai cây có thể được tổ chức như sau:

```text
Source text
    |
    v
Lexer
    |
    v
Tokens + source positions
    |
    v
Parser
    |
    v
CST / Parse tree
    |
    +----------------------------+
    |                            |
    v                            v
Syntax tooling               CST-to-AST
(format, outline,                |
syntax diagnostics)             v
                              AST
                               |
                               v
                       Semantic analysis
                               |
                               v
                       Typed / resolved AST
                               |
                   +-----------+-----------+
                   |                       |
                   v                       v
               Interpreter             Compiler
                   |                       |
                   +-----------+-----------+
                               |
                               v
                         DSL runtime
```

CST phục vụ những tác vụ cần cấu trúc cú pháp chi tiết. AST phục vụ những tác vụ cần hiểu ý nghĩa chương trình. Typed/resolved AST có thể bổ sung thông tin kiểu, symbol binding và kết quả kiểm tra ngữ nghĩa.

Không nhất thiết phải giữ tất cả các dạng cây trong bộ nhớ cùng lúc. Hệ thống có thể tạo CST, chuyển sang AST rồi giải phóng một phần cấu trúc nếu không còn cần. Editor hoặc formatter có thể chọn giữ token stream và CST lâu hơn để hỗ trợ thao tác nguồn.

## 8. Vị trí nguồn, token và trivia

### 8.1. Source span

Một node CST thường có thể liên kết đến đoạn văn bản nguồn đã tạo ra nó. Source span có thể gồm:

- Tên tệp hoặc document URI.
- Offset bắt đầu và kết thúc.
- Dòng và cột bắt đầu, kết thúc.
- Token đầu tiên và token cuối cùng.

Thông tin này giúp diagnostics chỉ đúng phần gây lỗi, editor chọn node khi người dùng đặt con trỏ và refactoring xác định đoạn văn bản cần thay thế.

### 8.2. Token đầu cuối

Terminal node thường đại diện token mà parser tiêu thụ, như `IDENTIFIER`, `NUMBER`, `LBRACE` hoặc `PLUS`. Token có thể chứa:

- Loại token.
- Văn bản gốc.
- Vị trí nguồn.
- Kênh token.
- Trạng thái lỗi hoặc token tổng hợp do parser chèn khi phục hồi.

Token gốc quan trọng khi cần giữ cách viết chính xác, ví dụ chữ hoa thường của keyword hoặc dạng số `1_000` so với `1000` nếu DSL cho phép dấu phân cách số.

### 8.3. Trivia: whitespace và comment

Whitespace và comment thường được gọi là *trivia* vì chúng không trực tiếp quyết định ngữ nghĩa của chương trình. Tuy nhiên, chúng rất quan trọng với editor, formatter và công cụ review.

Một parser có thể:

- Bỏ qua trivia hoàn toàn.
- Giữ trivia trên hidden channel.
- Gắn comment vào node hoặc token gần nhất.
- Lưu toàn bộ token stream cùng source text để tái tạo văn bản.

Nếu DSL cần formatter bảo toàn comment hoặc công cụ sửa cú pháp mà không thay đổi phần không liên quan, nên xác định chính sách trivia ngay từ đầu.

## 9. Parse tree và xử lý lỗi cú pháp

### 9.1. Lỗi khi đầu vào không khớp grammar

Ví dụ grammar yêu cầu:

```text
Assignment ::= Identifier "=" Expression ";"
```

nhưng người dùng viết:

```text
total = ;
```

Parser có thể phát hiện thiếu biểu thức sau dấu bằng. Tùy chiến lược error recovery, parser có thể dừng ngay, bỏ token không hợp lệ hoặc chèn token giả định để tiếp tục phân tích.

### 9.2. Error nodes và missing tokens

Một số parser biểu diễn lỗi ngay trong cây bằng error node hoặc token tổng hợp. Điều này cho phép công cụ vẫn duyệt được phần cấu trúc hợp lệ xung quanh lỗi.

Ví dụ, với:

```text
rule "discount" {
    when customer.tier ==
    then discount.percent = 10
}
```

parser có thể tạo node điều kiện có một toán hạng bị thiếu và ghi diagnostic tại vị trí sau `==`. Cây khi đó là biểu diễn của một lần phân tích có lỗi, không nhất thiết là cây hoàn chỉnh của chương trình hợp lệ.

### 9.3. Panic-mode và chiến lược đồng bộ

Một chiến lược phục hồi đơn giản là bỏ token cho đến khi gặp token đồng bộ như dấu chấm phẩy, dấu đóng ngoặc hoặc từ khóa bắt đầu một câu lệnh mới. Cách này thường được gọi là panic-mode recovery.

Parser cần chọn điểm đồng bộ phù hợp với grammar. Nếu đồng bộ quá sớm, có thể báo nhiều lỗi giả; nếu bỏ quá nhiều token, người dùng mất thông tin lỗi ở phần sau.

### 9.4. Phân biệt cây lỗi và cây hợp lệ

Ứng dụng không nên mặc định mọi parse tree đều biểu diễn chương trình hợp lệ. Cần kiểm tra diagnostics và trạng thái parser trước khi chạy interpreter hoặc compiler. Editor có thể vẫn dùng cây một phần để hỗ trợ completion và tô màu khi người dùng đang gõ dở.

## 10. Ứng dụng của CST và parse tree trong công cụ DSL

### 10.1. Chuyển CST thành AST

Một visitor có thể loại bỏ các node trung gian, dấu câu không cần thiết và chuyển terminal thành thuộc tính của node AST. Ví dụ, parse tree của phép cộng có node cho `Expression`, `Term`, `Factor` và token `PLUS`; AST có thể chỉ cần node `Add(left, right)`.

### 10.2. Syntax highlighting và editor

CST cùng token stream cung cấp thông tin cấu trúc tốt hơn so với chỉ dùng regex. Editor có thể phân biệt identifier trong biểu thức với chuỗi literal, keyword trong đúng ngữ cảnh và vùng cú pháp đang thiếu.

Với parser incremental như Tree-sitter, editor có thể cập nhật một phần cây khi văn bản thay đổi, thay vì phân tích lại toàn bộ tài liệu mỗi lần gõ.

### 10.3. Formatter

Formatter có thể duyệt CST để xác định cấu trúc khối, dấu phân cách và vị trí token. Nếu giữ trivia, formatter có thể bảo toàn hoặc di chuyển comment theo quy tắc. Formatter dựa trên AST vẫn có thể hoạt động, nhưng thường cần thêm quy tắc tái tạo cú pháp và nguồn gốc comment.

### 10.4. Refactoring và code actions

CST và source span giúp công cụ thay đổi một phần tài liệu. Ví dụ:

- Thêm dấu ngoặc quanh biểu thức.
- Chuẩn hóa dấu phẩy hoặc dấu chấm phẩy.
- Chuyển cú pháp cũ sang cú pháp mới.
- Thay đổi thứ tự thuộc tính.
- Tạo skeleton cho một rule mới.

Đổi tên symbol cần semantic resolution để phân biệt tham chiếu thật với chuỗi có cùng nội dung. CST cung cấp vị trí sửa; symbol table xác định những vị trí cần sửa.

### 10.5. Diagnostics và tài liệu trực quan

Cây có thể được dùng để tạo outline, hiển thị cấu trúc rule, liệt kê khai báo và liên kết lỗi với node tương ứng. Đây là nền tảng cho các tính năng như go to definition, document symbols và hover trong language server.

## 11. Ví dụ dùng ANTLR để tạo và duyệt parse tree

ANTLR là một parser generator phổ biến, hỗ trợ sinh lexer/parser và API parse tree cho nhiều ngôn ngữ đích.

Grammar minh họa:

```antlr
grammar MiniExpr;

prog : expr EOF ;
expr : expr op=('*' | '/') expr
     | expr op=('+' | '-') expr
     | INT
     | '(' expr ')'
     ;

INT : [0-9]+ ;
WS  : [ \t\r\n]+ -> skip ;
```

Grammar này chỉ minh họa parser expression; để sử dụng trong dự án thật cần kiểm soát precedence và associativity một cách rõ ràng theo phiên bản ANTLR và cách viết grammar. Một cách thường dùng là tách các mức quy tắc:

```antlr
grammar MiniExpr;

prog : expr EOF ;

expr : additive ;

additive
    : multiplicative (('+' | '-') multiplicative)*
    ;

multiplicative
    : primary (('*' | '/') primary)*
    ;

primary
    : INT
    | '(' expr ')'
    ;

INT : [0-9]+ ;
WS  : [ \t\r\n]+ -> skip ;
```

Với input `2 + 3 * 4`, parser tạo parse tree theo các quy tắc `prog`, `expr`, `additive`, `multiplicative` và `primary`. API sinh ra cho các context giúp ứng dụng truy cập node tương ứng.

Một quy trình Java khái quát:

```java
CharStream input = CharStreams.fromString("2 + 3 * 4");

MiniExprLexer lexer = new MiniExprLexer(input);
CommonTokenStream tokens = new CommonTokenStream(lexer);

MiniExprParser parser = new MiniExprParser(tokens);
MiniExprParser.ProgContext tree = parser.prog();

System.out.println(tree.toStringTree(parser));
```

Đoạn mã là ví dụ sử dụng API ANTLR trong Java. Tên class được sinh từ tên grammar; dự án cần chạy bước generate source và thêm runtime dependency tương ứng.

### 11.1. Dùng visitor

Với visitor, có thể tính giá trị biểu thức hoặc chuyển parse tree thành AST. Ví dụ ý tưởng:

```java
public final class EvalVisitor extends MiniExprBaseVisitor<Integer> {
    @Override
    public Integer visitProg(MiniExprParser.ProgContext ctx) {
        return visit(ctx.expr());
    }

    @Override
    public Integer visitAdditive(MiniExprParser.AdditiveContext ctx) {
        int result = visit(ctx.multiplicative(0));

        for (int i = 1; i < ctx.multiplicative().size(); i++) {
            int right = visit(ctx.multiplicative(i));
            String operator = ctx.getChild(2 * i - 1).getText();

            result = switch (operator) {
                case "+" -> result + right;
                case "-" -> result - right;
                default -> throw new IllegalStateException("Unexpected operator");
            };
        }

        return result;
    }
}
```

Đây là phần minh họa cách visitor xử lý các node. Một visitor đầy đủ cần cài đặt các trường hợp `multiplicative`, `primary` và `INT`, đồng thời xác định chính sách lỗi, chia cho 0 và tràn số.

### 11.2. Dùng listener

Listener có thể ghi nhận khi parser đi vào và đi ra các quy tắc. Ví dụ một listener có thể thu thập tất cả literal số, tên định danh hoặc khai báo rule. Cách này hữu ích khi mục tiêu là quan sát cấu trúc mà không cần trả về một giá trị từ mỗi node.

## 12. Khi nào nên giữ CST và khi nào chỉ cần AST?

Nên giữ hoặc sử dụng CST khi:

- Cần formatter bảo toàn cú pháp, comment hoặc phong cách nguồn.
- Cần refactoring chính xác theo đoạn văn bản.
- Cần hiển thị cây cú pháp để hỗ trợ học tập hoặc debug grammar.
- Cần diagnostics gắn trực tiếp với token và production.
- Editor cần phân tích tài liệu chưa hoàn chỉnh khi người dùng đang gõ.

Có thể chỉ giữ AST cho các bước tiếp theo khi:

- Chỉ cần xử lý ngữ nghĩa, đánh giá biểu thức hoặc sinh mã.
- Không cần tái tạo chính xác cú pháp nguồn.
- Grammar có thể thay đổi nhưng mô hình ngữ nghĩa cần ổn định.
- Tối ưu bộ nhớ và tốc độ xử lý quan trọng.

Trong nhiều hệ thống, parse tree được giữ trong thời gian ngắn để chuyển thành AST rồi giải phóng. Trong IDE, CST hoặc cây incremental có thể được giữ và cập nhật liên tục.

## 13. Các lỗi thường gặp khi làm việc với parse tree

- **Nhầm parse tree với AST:** parse tree phản ánh grammar; AST phản ánh cấu trúc trừu tượng có ý nghĩa.
- **Cho rằng mọi CST đều giữ comment và whitespace:** điều này phụ thuộc lexer, parser và cách lưu trivia.
- **Dựa vào hình thức cây thay vì grammar:** một grammar khác có thể tạo cây khác cho cùng ý nghĩa chương trình.
- **Bỏ qua source location:** làm diagnostics và refactoring khó xác định đúng đoạn nguồn.
- **Giả định cây luôn hợp lệ:** parser có thể tạo cây một phần hoặc cây có error node sau khi phục hồi.
- **Duyệt cây không đầy đủ:** visitor có thể bỏ sót nhánh nếu không gọi xử lý cho node con.
- **Gắn ngữ nghĩa nghiệp vụ vào parser:** parser nên tập trung vào cú pháp; kiểm tra kiểu, khai báo và quyền thường thuộc semantic analysis.
- **Giữ cây quá lâu hoặc sao chép không cần thiết:** CST có thể lớn; cần quản lý vòng đời và bộ nhớ theo nhu cầu công cụ.
- **Không kiểm thử grammar:** thay đổi production có thể làm cây đổi cấu trúc và ảnh hưởng visitor, listener, formatter hoặc editor.

## 14. Quy trình làm việc với CST và parse tree trong một DSL

Một quy trình triển khai có thể gồm:

1. **Định nghĩa grammar:** xác định start rule, terminal, nonterminal, precedence và associativity.
2. **Chọn lexer/parser:** parser viết tay hay parser generator, dựa trên độ phức tạp và nền tảng.
3. **Xác định thông tin nguồn:** lưu token text, source span, comment và whitespace nếu công cụ cần.
4. **Tạo parse tree:** phân tích đầu vào và thu diagnostics.
5. **Xử lý lỗi cú pháp:** quyết định dừng, phục hồi hoặc tạo cây một phần cho editor.
6. **Duyệt cây:** chọn listener cho callback theo cấu trúc hoặc visitor cho chuyển đổi/tính toán.
7. **Chuyển sang AST:** bỏ chi tiết cú pháp không cần thiết và tạo mô hình miền ổn định.
8. **Phân tích ngữ nghĩa:** resolve identifier, kiểm tra kiểu, quyền và invariant.
9. **Tích hợp công cụ:** formatter, syntax highlighting, outline, refactoring và debugger.
10. **Kiểm thử và theo dõi thay đổi:** kiểm tra parse tree/AST mong đợi, diagnostics, grammar ambiguity và tương thích tài liệu cũ.

Khi grammar thay đổi, cần xem xét các consumer của parse tree. Một thay đổi nhỏ trong production có thể đổi tên context, số lượng node hoặc vị trí token; visitor và listener được sinh từ grammar có thể cần cập nhật theo.

## 15. Kết luận

CST và parse tree biểu diễn cấu trúc cú pháp cụ thể mà parser nhận được từ grammar. Chúng giữ mối liên hệ giữa production, token và vị trí nguồn, nhờ đó hỗ trợ phân tích cú pháp, diagnostics, formatter, editor và refactoring. AST thường được tạo tiếp theo để biểu diễn cấu trúc trừu tượng phục vụ semantic analysis, interpreter hoặc compiler.

Khi xây dựng DSL, cần hiểu chính xác parser tạo ra loại cây nào, chi tiết nào được giữ lại và cách xử lý đầu vào sai. Giữ CST khi cần làm việc với cú pháp và nguồn; dùng AST khi cần xử lý ý nghĩa. Việc tách hai vai trò này giúp grammar, công cụ soạn thảo và phần thực thi của DSL dễ phát triển và bảo trì hơn.


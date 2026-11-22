# Viết grammar

## 1. Grammar là gì trong một DSL?

Trong một ngôn ngữ chuyên biệt miền (Domain-Specific Language — DSL), **grammar** là tập quy tắc mô tả cách token được kết hợp thành những cấu trúc cú pháp hợp lệ.

Grammar xác định một chương trình có hình thức như thế nào. Nó trả lời các câu hỏi:

- Một file DSL có thể chứa những thành phần nào?
- Một declaration được viết theo thứ tự nào?
- Expression gồm những toán tử và toán hạng nào?
- Block bắt đầu và kết thúc bằng ký hiệu gì?
- Function call, literal và identifier có hình thức ra sao?
- Cấu trúc nào hợp lệ và cấu trúc nào phải bị parser từ chối?

Ví dụ một DSL mô tả policy:

~~~text
policy "Discount" {
  input order: Order;

  let eligible = order.total >= 1000000;

  if eligible {
    orders.applyDiscount(order.id, 0.05);
  }
}
~~~

Grammar mô tả rằng một policy có keyword policy, tên dạng string, block chứa khai báo input và các statement; một statement có thể là let declaration, if statement, assignment hoặc function call.

Grammar là một phần của language specification. Nó thường được triển khai bằng parser generator như ANTLR, parser viết tay, PEG parser hoặc một thư viện parsing khác.

## 2. Grammar nằm ở đâu trong compiler pipeline?

Một pipeline phổ biến:

~~~text
Source text
    |
    v
Lexer
    |
    v
Token stream
    |
    v
Parser + Grammar
    |
    v
Parse tree
    |
    v
AST
    |
    v
Semantic analysis
    |
    v
IR / Runtime / Generator
~~~

Lexer nhận ký tự và tạo token. Grammar quy định cách parser kết hợp token thành cấu trúc. AST thể hiện cấu trúc có ý nghĩa đối với các phase tiếp theo.

Grammar không tự xác định đầy đủ ý nghĩa nghiệp vụ. Ví dụ parser có thể chấp nhận phép gán vào order.total, nhưng semantic analyzer mới xác định field đó có tồn tại, có thể ghi và có kiểu phù hợp hay không.

### 2.1 Lexer và parser có trách nhiệm khác nhau

| Thành phần | Đầu vào | Đầu ra | Ví dụ |
|---|---|---|---|
| Lexer | Ký tự | Token | let, identifier, number |
| Parser | Token | Parse tree hoặc AST | LetDeclaration |
| Semantic analyzer | AST | Model có kiểu/diagnostic | Type mismatch |

### 2.2 Grammar không thay thế type system

Grammar có thể nhận diện một lời gọi function theo hình thức:

~~~text
orders.approve(orderId);
~~~

Nhưng nó không nhất thiết biết orders.approve có được đăng ký, có nhận OrderId hay có quyền thực thi trong tenant hiện tại không. Những kiểm tra đó thuộc name resolution, type checking và runtime authorization.

## 3. Bắt đầu bằng yêu cầu ngôn ngữ

Không nên bắt đầu viết grammar chỉ từ một ví dụ cú pháp. Trước tiên, xác định người dùng cần diễn đạt điều gì.

### 3.1 Xác định domain concept

Liệt kê những khái niệm cốt lõi:

- Policy hoặc workflow.
- Input và output.
- Declaration.
- Rule và condition.
- Action hoặc command.
- Expression.
- Function call.
- Type và value.
- Block và scope.

Không phải DSL nào cũng cần tất cả các khái niệm này. Chỉ đưa construct vào grammar khi có use case thực tế.

### 3.2 Thu thập ví dụ hợp lệ

Viết một tập source thể hiện các use case thường gặp, từ đơn giản đến phức tạp. Ví dụ nên dùng thuật ngữ domain nhất quán và có output mong đợi.

### 3.3 Thu thập ví dụ không hợp lệ

Ví dụ sai giúp xác định ranh giới grammar:

~~~text
policy "Discount" {
  let = 10;
}
~~~

~~~text
policy "Discount" {
  if order.total > {
    orders.approve(order.id);
  }
}
~~~

Ghi rõ parser nên báo lỗi ở đâu và có thể phục hồi để báo thêm lỗi nào.

### 3.4 Chọn mức độ tự do

Quyết định DSL là declarative (mô tả kết quả mong muốn), imperative (mô tả từng bước), expression-oriented (construct chủ yếu tạo value), statement-oriented (chương trình chủ yếu là chuỗi statement) hay hybrid.

Lựa chọn này ảnh hưởng cấu trúc grammar, scope và semantics.

## 4. Viết đặc tả cú pháp trước khi chọn parser

Đặc tả cú pháp giúp tách quyết định ngôn ngữ khỏi implementation.

### 4.1 Bắt đầu từ chương trình hoàn chỉnh

~~~text
policy "OrderApproval" {
  input order: Order;

  if order.total >= 5000000 {
    decision.requireReview("HIGH_VALUE");
  } else {
    decision.approve();
  }
}
~~~

Từ ví dụ này, xác định:

- Program chứa policy declaration.
- Policy có name và body.
- Body có input declaration và statement.
- If statement có condition và block.
- Có thể có else block.
- Function call có qualified name và argument list.

### 4.2 Tạo danh sách production

Mỗi production mô tả một cấu trúc. Ví dụ:

~~~text
program           = policyDeclaration ;
policyDeclaration = "policy" STRING "{" policyBody "}" ;
policyBody        = inputDeclaration* statement* ;
statement         = letDeclaration | ifStatement | callStatement ;
~~~

### 4.3 Định nghĩa token riêng

Tách keyword, identifier, number, string, punctuation, operator, whitespace và comment.

### 4.4 Định nghĩa quy tắc precedence

Ghi rõ toán tử nào có độ ưu tiên cao hơn và cách kết hợp khi cùng precedence.

### 4.5 Ghi rõ optional và repetition

Quyết định phần nào có thể vắng mặt, xuất hiện một lần hoặc lặp nhiều lần. Ví dụ policy có thể có zero hoặc nhiều input declaration.

## 5. Ký pháp EBNF cơ bản

EBNF (Extended Backus–Naur Form) là một ký pháp phổ biến để mô tả grammar.

Các ký hiệu thường gặp:

| Ký hiệu | Ý nghĩa | Ví dụ |
|---|---|---|
| **=** | Định nghĩa production | expression = term |
| **;** | Kết thúc production | program = statement ; |
| **\|** | Lựa chọn | "+" hoặc "-" |
| **[ ... ]** | Tùy chọn, zero hoặc one | [elseBlock] |
| **{ ... }** | Lặp zero hoặc nhiều lần | {statement} |
| **( ... )** | Nhóm | ("+" hoặc "-") |
| terminal | Token/ký hiệu cụ thể | "if" |
| nonterminal | Tên production | expression |

Ví dụ:

~~~text
program           = policyDeclaration ;
policyDeclaration = "policy" STRING "{" { statement } "}" ;
statement         = letDeclaration | ifStatement | callStatement ;
letDeclaration    = "let" IDENTIFIER "=" expression ";" ;
callStatement     = functionCall ";" ;
~~~

### 5.1 Optional

~~~text
elseClause = [ "else" block ] ;
~~~

### 5.2 Repetition

~~~text
argumentList = expression { "," expression } ;
~~~

Production trên yêu cầu ít nhất một expression, sau đó có thể có thêm expression phân cách bằng dấu phẩy.

### 5.3 Zero-or-more và one-or-more

Một số grammar notation dùng * cho zero-or-more và + cho one-or-more. Cần nêu rõ quy ước đang dùng vì EBNF dialect có thể khác nhau.

### 5.4 Terminal và nonterminal

Terminal là token xuất hiện trong input. Nonterminal là cấu trúc được định nghĩa bằng production khác.

### 5.5 Đệ quy

Grammar có thể dùng recursion để mô tả cấu trúc lồng nhau:

~~~text
block = "{" { statement } "}" ;
~~~

Statement có thể chứa block, tạo nesting nhiều cấp.

## 6. Xây dựng grammar từ trên xuống

Top-down design bắt đầu từ cấu trúc lớn nhất rồi phân rã thành thành phần nhỏ.

### 6.1 Program

~~~text
program = policyDeclaration EOF ;
~~~

EOF yêu cầu parser tiêu thụ toàn bộ input. Nếu không có EOF ở entry rule, parser có thể chấp nhận một prefix rồi bỏ qua phần source còn lại.

### 6.2 Declaration

~~~text
policyDeclaration =
  "policy" STRING "{" policyBody "}" ;
~~~

### 6.3 Body

~~~text
policyBody =
  { inputDeclaration }
  { statement } ;
~~~

### 6.4 Statement

~~~text
statement =
    letDeclaration
  | ifStatement
  | assignment
  | expressionStatement ;
~~~

### 6.5 Expression

Expression được phân rã theo precedence. Không nên viết một production expression quá tổng quát nếu cần kiểm soát thứ tự toán tử.

### 6.6 Kiểm tra ví dụ

Với mỗi production, tạo ít nhất một ví dụ hợp lệ và một ví dụ gần đúng nhưng không hợp lệ. Điều này giúp xác định grammar đang cho phép quá rộng hay quá hẹp.

## 7. Thiết kế lexical grammar

Lexer biến chuỗi ký tự thành token stream.

### 7.1 Keyword

Ví dụ keyword:

~~~text
policy
input
let
if
else
true
false
null
~~~

Keyword thường được nhận diện trước identifier, hoặc lexer dùng quy tắc ưu tiên tương đương.

### 7.2 Identifier

Một quy tắc đơn giản:

~~~text
IDENTIFIER = LETTER { LETTER | DIGIT | "_" } ;
~~~

Quy định rõ có cho phép Unicode, ký tự bắt đầu đặc biệt hoặc tên phân biệt hoa thường không.

### 7.3 Number literal

Ví dụ:

~~~text
NUMBER = DIGIT { DIGIT } [ "." DIGIT { DIGIT } ] ;
~~~

Nếu hỗ trợ exponent, hex hoặc suffix đơn vị, cần định nghĩa riêng và tránh overlap không chủ ý.

### 7.4 String literal

String cần quy định dấu nháy, escape sequence, Unicode escape, multiline string, cách xử lý newline và diagnostic khi string chưa đóng.

### 7.5 Operator và punctuation

Ví dụ:

~~~text
==  !=  <=  >=  &&  ||
+   -   *   /   %
=   <   >
(   )   {   }   ,   .   :   ;
~~~

### 7.6 Longest match

Khi có token overlap, lexer thường chọn token khớp dài nhất. Ví dụ >= phải được nhận là một token thay vì > rồi =.

### 7.7 Comment và whitespace

Xác định line comment, block comment, nested comment nếu có và cách xử lý newline. Whitespace thường được bỏ qua nhưng source position vẫn cần được giữ.

### 7.8 Negative number

Thường nên tokenize dấu trừ như unary/binary operator và số như number literal. Parser quyết định dấu trừ là unary hay binary dựa trên vị trí trong expression.

## 8. Keyword và identifier

Việc phân biệt keyword với identifier cần nhất quán.

### 8.1 Reserved keyword

Reserved keyword không thể được dùng làm tên biến hoặc function. Cách này đơn giản cho parser nhưng có thể hạn chế tên domain.

### 8.2 Contextual keyword

Contextual keyword được xem là keyword chỉ trong một vị trí cú pháp nhất định. Nó linh hoạt hơn nhưng làm grammar và diagnostic phức tạp hơn.

### 8.3 Case sensitivity

Quyết định policy và Policy có giống nhau không. Không nên để lexer, symbol resolver và documentation áp dụng các quy tắc khác nhau.

### 8.4 Identifier Unicode

Nếu hỗ trợ Unicode, định nghĩa phạm vi ký tự, normalization và cách tính source offset. Đừng giả định một ký tự hiển thị luôn tương ứng một code unit.

### 8.5 Escaped identifier

Một số DSL cho phép dùng keyword làm identifier qua quoting. Nếu có, quy tắc escaping và pretty printing cần được mô tả.

## 9. Xây dựng grammar cho expression

Expression thường là phần phức tạp nhất vì có nhiều toán tử và precedence.

### 9.1 Ví dụ precedence

Một thứ tự thường gặp từ cao xuống thấp:

1. Primary: literal, identifier, call, parenthesized expression.
2. Unary: !, unary -.
3. Multiplicative: *, /, %.
4. Additive: +, -.
5. Comparison: <, <=, >, >=.
6. Equality: ==, !=.
7. Logical AND.
8. Logical OR.

Thứ tự này chỉ là ví dụ. DSL phải chọn precedence phù hợp với semantics của mình.

### 9.2 Grammar phân tầng

~~~text
expression      = logicalOr ;
logicalOr       = logicalAnd { "or" logicalAnd } ;
logicalAnd      = equality { "and" equality } ;
equality        = comparison { ("==" | "!=") comparison } ;
comparison      = additive { ("<" | "<=" | ">" | ">=") additive } ;
additive        = multiplicative { ("+" | "-") multiplicative } ;
multiplicative  = unary { ("*" | "/" | "%") unary } ;
unary           = ("not" | "-") unary | primary ;
primary         = literal | functionCall | qualifiedName | "(" expression ")" ;
~~~

### 9.3 Associativity

Với phép trừ, thường dùng left associativity:

~~~text
a - b - c
~~~

được hiểu là:

~~~text
(a - b) - c
~~~

Với phép gán, một số ngôn ngữ dùng right associativity. Grammar cần mô tả rõ.

### 9.4 Parentheses

Parentheses cho phép người dùng thể hiện grouping rõ:

~~~text
(a + b) * c
~~~

Parser cần tạo node expression tương ứng và giữ source range.

### 9.5 Non-associative operator

Một số toán tử so sánh có thể không cho phép chain:

~~~text
a < b < c
~~~

Nếu không hỗ trợ, grammar hoặc semantic analyzer phải báo lỗi rõ thay vì diễn giải ngầm.

## 10. Left recursion và cách xử lý

Một grammar có left recursion trực tiếp:

~~~text
expression = expression "+" term | term ;
~~~

Recursive-descent parser thông thường có thể gọi lặp vô hạn khi production bắt đầu bằng chính nó.

### 10.1 Loại bỏ left recursion trực tiếp

Có thể viết lại:

~~~text
expression = term { "+" term } ;
~~~

Parser tạo một term đầu tiên, sau đó lặp qua các cặp operator và term.

### 10.2 Left recursion gián tiếp

Left recursion gián tiếp xảy ra khi A gọi B, rồi B quay lại A ở vị trí đầu. Cần phân tích dependency giữa các production.

### 10.3 Parser generator hỗ trợ left recursion

Một số parser generator hỗ trợ trực tiếp một dạng left recursion và tự biến đổi grammar. Phải theo đúng quy tắc của công cụ, không giả định mọi generator có behavior giống nhau.

### 10.4 Giữ associativity khi viết lại

Khi loại bỏ left recursion, AST builder cần tạo đúng grouping. Không chỉ làm parser chạy được mà quên semantics của operator.

## 11. Ambiguity và cách giảm mơ hồ

Grammar ambiguous khi cùng một input có nhiều parse tree hợp lệ theo grammar.

### 11.1 Dangling else

Ví dụ:

~~~text
if a
  if b
    action1()
  else
    action2()
~~~

else thuộc if nào? Nhiều ngôn ngữ gắn else với if gần nhất chưa có else, nhưng DSL phải định nghĩa rõ.

### 11.2 Common prefix

Hai production cùng bắt đầu bằng token giống nhau có thể làm parser khó chọn nhánh:

~~~text
statement = identifier "=" expression
          | identifier "(" argumentList ")" ;
~~~

Parser cần nhìn thêm token hoặc dùng lookahead phù hợp.

### 11.3 Left factoring

Có thể tách phần chung:

~~~text
statement = identifier statementTail ;
statementTail = "=" expression
              | "(" argumentList ")" ;
~~~

### 11.4 Precedence và associativity

Grammar expression không rõ precedence thường tạo ambiguity hoặc parse tree ngoài ý muốn. Tách production theo tầng là một cách phổ biến.

### 11.5 Semantic disambiguation

Một số ngôn ngữ dùng thông tin symbol/type để phân biệt cách parse. Cách này có thể cần thiết, nhưng tăng coupling giữa parser và semantic environment. Chỉ dùng khi lợi ích rõ.

### 11.6 Ambiguity test

Với construct dễ mơ hồ, lưu ví dụ input và expected parse tree. Kiểm tra cả trường hợp hợp lệ và trường hợp phải từ chối.

## 12. Viết grammar bằng ANTLR

ANTLR là một parser generator phổ biến. Grammar có thể mô tả parser rules và lexer rules trong một file.

Ví dụ grammar rút gọn cho policy DSL:

~~~antlr
grammar Policy;

program
    : policyDeclaration EOF
    ;

policyDeclaration
    : POLICY STRING LBRACE policyBody RBRACE
    ;

policyBody
    : inputDeclaration* statement*
    ;

inputDeclaration
    : INPUT identifier COLON typeName SEMI
    ;

statement
    : letDeclaration
    | ifStatement
    | assignment
    | expressionStatement
    ;

letDeclaration
    : LET identifier ASSIGN expression SEMI
    ;

ifStatement
    : IF expression block (ELSE block)?
    ;

block
    : LBRACE statement* RBRACE
    ;

assignment
    : qualifiedName ASSIGN expression SEMI
    ;

expressionStatement
    : expression SEMI
    ;

expression
    : logicalOr
    ;

logicalOr
    : logicalAnd (OR logicalAnd)*
    ;

logicalAnd
    : equality (AND equality)*
    ;

equality
    : comparison ((EQ | NEQ) comparison)*
    ;

comparison
    : additive ((LT | LTE | GT | GTE) additive)*
    ;

additive
    : multiplicative ((PLUS | MINUS) multiplicative)*
    ;

multiplicative
    : unary ((STAR | SLASH | PERCENT) unary)*
    ;

unary
    : (NOT | MINUS) unary
    | primary
    ;

primary
    : literal
    | functionCall
    | qualifiedName
    | LPAREN expression RPAREN
    ;

functionCall
    : qualifiedName LPAREN argumentList? RPAREN
    ;

argumentList
    : expression (COMMA expression)*
    ;

qualifiedName
    : identifier (DOT identifier)*
    ;

typeName
    : identifier
    ;

identifier
    : IDENTIFIER
    ;

literal
    : NUMBER
    | STRING
    | TRUE
    | FALSE
    | NULL
    ;

POLICY : 'policy';
INPUT  : 'input';
LET    : 'let';
IF     : 'if';
ELSE   : 'else';
TRUE   : 'true';
FALSE  : 'false';
NULL   : 'null';
AND    : 'and';
OR     : 'or';
NOT    : 'not';

ASSIGN : '=';
EQ     : '==';
NEQ    : '!=';
LTE    : '<=';
GTE    : '>=';
LT     : '<';
GT     : '>';
PLUS   : '+';
MINUS  : '-';
STAR   : '*';
SLASH  : '/';
PERCENT: '%';

LPAREN : '(';
RPAREN : ')';
LBRACE : '{';
RBRACE : '}';
COMMA  : ',';
DOT    : '.';
COLON  : ':';
SEMI   : ';';

NUMBER
    : DIGIT+ ('.' DIGIT+)?
    ;

STRING
    : '"' (ESCAPE | ~["\\\r\n])* '"'
    ;

IDENTIFIER
    : LETTER (LETTER | DIGIT | '_')*
    ;

LINE_COMMENT
    : '//' ~[\r\n]* -> skip
    ;

WS
    : [ \t\r\n]+ -> skip
    ;

fragment ESCAPE
    : '\\' ["\\nrt]
    ;

fragment LETTER
    : [a-zA-Z_]
    ;

fragment DIGIT
    : [0-9]
    ;
~~~

Đây là ví dụ học tập. Một grammar production-ready cần quyết định thêm về Unicode, escape sequence, comment, numeric format, source mapping, error recovery và các construct thực tế.

### 12.1 Parser rule và lexer rule

Trong ANTLR, parser rule thường bắt đầu bằng chữ thường; lexer token rule bắt đầu bằng chữ hoa. Fragment rule chỉ được dùng bên trong lexer rule.

### 12.2 Thứ tự lexer rule

Keyword được định nghĩa trước IDENTIFIER để công cụ có thể áp dụng quy tắc ưu tiên khi cùng độ dài khớp. Longest match và rule order cần được hiểu theo behavior của ANTLR.

### 12.3 Entry rule và EOF

Entry rule có EOF giúp xác nhận toàn bộ file được parse. Nếu không, token thừa ở cuối có thể bị bỏ qua tùy cách gọi parser.

### 12.4 Generated parser

ANTLR sinh lexer/parser và các visitor/listener theo grammar. Generated code là artifact; thông thường chỉnh sửa grammar source rồi regenerate, không sửa trực tiếp generated parser.

## 13. Chọn parser generator hay parser viết tay

Không có một lựa chọn phù hợp với mọi DSL.

| Cách tiếp cận | Ưu điểm | Hạn chế |
|---|---|---|
| ANTLR/LL parser generator | Grammar rõ, tooling và diagnostics tốt | Cần học tool và giới hạn grammar |
| LALR parser generator | Phù hợp grammar có cấu trúc rõ | Conflict cần xử lý và debug |
| PEG parser | Ordered choice, grammar biểu đạt linh hoạt | Ordered choice có thể che nhánh |
| Recursive descent | Kiểm soát logic và diagnostic trực tiếp | Nhiều code thủ công |
| Pratt parser | Gọn cho expression và precedence | Cần tự xây phần declaration/statement |

### 13.1 Parser generator

Phù hợp khi grammar là phần quan trọng cần đọc, review và duy trì như đặc tả. Tool có thể cung cấp parse tree, listener, visitor và error strategy.

### 13.2 Recursive descent

Phù hợp với grammar nhỏ, cú pháp dễ kiểm soát hoặc cần diagnostic tùy biến. Mỗi production thường tương ứng với một method parse.

### 13.3 Pratt parser

Pratt parsing hữu ích cho expression có nhiều prefix/infix operator và precedence. Parser dùng binding power để quyết định tiếp tục parse operator nào.

### 13.4 Kết hợp nhiều kỹ thuật

Có thể dùng recursive descent cho declaration/statement và Pratt parser cho expression. Điều quan trọng là ranh giới rõ và test được.

## 14. Xây dựng AST từ parse tree

Parse tree phản ánh cấu trúc grammar. AST nên phản ánh khái niệm mà compiler và tooling cần.

### 14.1 Parse tree và AST khác nhau

Parse tree thường chứa terminal và node trung gian theo từng production. AST có thể bỏ dấu ngoặc, dấu chấm phẩy và node grammar không có ý nghĩa lâu dài.

### 14.2 Ví dụ

Source:

~~~text
let total = price * quantity;
~~~

AST:

~~~text
LetDeclaration
  name: total
  initializer:
    BinaryExpression
      operator: MULTIPLY
      left: NameExpression(price)
      right: NameExpression(quantity)
~~~

### 14.3 Giữ source location

AST node thường cần source span để diagnostics, editor navigation và code generation mapping.

### 14.4 Immutable AST

AST immutable giúp các phase dễ reasoning và tránh state bị sửa ngoài ý muốn. Nếu cần annotation từ semantic analysis, có thể tạo typed model hoặc side table.

### 14.5 Visitor

Visitor giúp tách thao tác khỏi cấu trúc node, ví dụ AST printer, type checker, evaluator và generator.

### 14.6 Không để AST phản chiếu mọi token

Không nhất thiết tạo một AST node cho mỗi punctuation token. Giữ trivia/comment riêng nếu formatter hoặc refactoring cần chúng.

## 15. Error handling và parser recovery

Parser cần xử lý cả input hợp lệ lẫn input không hợp lệ.

### 15.1 Diagnostic hữu ích

Một diagnostic nên có error code ổn định, severity, message dễ hiểu, source URI/range, expected token hoặc construct khi hữu ích và related location nếu có.

### 15.2 Panic-mode recovery

Parser có thể bỏ qua token đến một synchronization point như dấu chấm phẩy hoặc dấu đóng block để tiếp tục tìm lỗi.

### 15.3 Error node

AST có thể chứa ErrorExpression hoặc InvalidStatement để downstream phase biết vùng đó không hợp lệ.

### 15.4 Tránh cascade

Nếu một expression đã invalid, không nên phát sinh hàng chục diagnostic thứ cấp do semantic analyzer tiếp tục giả định node hoàn chỉnh.

### 15.5 Unterminated string/comment

Lexer cần diagnostic riêng và source range phù hợp. Không nên âm thầm coi phần còn lại của file là token hợp lệ.

### 15.6 Recovery là behavior cần test

Test malformed source và expected diagnostics để bảo đảm editor vẫn có thể cung cấp feedback hữu ích khi người dùng đang gõ dở.

## 16. Grammar và source position

Source location rất quan trọng cho compiler, editor và formatter.

### 16.1 Offset convention

Xác định offset zero-based hay one-based, end-exclusive hay end-inclusive, đếm byte/UTF-16 code unit/Unicode code point và line/column bắt đầu từ 0 hay 1.

### 16.2 Newline

Hỗ trợ LF, CRLF hoặc cả hai theo policy. Source mapping phải nhất quán giữa lexer, parser và editor protocol.

### 16.3 Unicode

Một ký tự hiển thị có thể gồm nhiều code point hoặc code unit. Không tự cộng column bằng số byte UTF-8 nếu contract dùng UTF-16.

### 16.4 Trivia

Comment và whitespace có thể không xuất hiện trong AST semantic, nhưng formatter hoặc refactoring tool có thể cần lưu chúng trong token stream hoặc concrete syntax tree.

## 17. Grammar cho declaration, statement và block

### 17.1 Declaration

Declaration tạo tên hoặc cấu trúc có thể được tham chiếu:

~~~text
let discountRate = 0.05;
~~~

Grammar cần xác định keyword, identifier, dấu gán, expression và terminator.

### 17.2 Statement

Statement biểu diễn hành động hoặc điều khiển luồng:

~~~text
if order.total > 1000 {
  orders.approve(order.id);
}
~~~

### 17.3 Block

~~~text
block = "{" { statement } "}" ;
~~~

Block nhóm statement và có thể tạo scope. Grammar xác định cấu trúc; semantic analyzer xác định declaration trong block có scope thế nào.

### 17.4 Terminator

Chọn dấu chấm phẩy bắt buộc, newline-sensitive hoặc quy tắc tự chèn terminator. Automatic semicolon insertion có thể làm grammar khó hiểu nếu không định nghĩa chặt.

### 17.5 Optional separator

Nếu cho phép dấu phẩy cuối trong argument list, thể hiện rõ trong grammar và test cả trường hợp có/không có dấu phẩy.

## 18. Grammar cho type và function call

### 18.1 Type reference

~~~text
typeReference = qualifiedName [ typeArguments ] ;
~~~

Nếu có generic type, định nghĩa delimiter và cách phân biệt với operator.

### 18.2 Function call

~~~text
functionCall =
  qualifiedName "(" [ argumentList ] ")" ;
~~~

### 18.3 Named argument

~~~text
argument = [ identifier ":" ] expression ;
~~~

Nếu hỗ trợ cả positional và named argument, cần quy định có cho trộn hai loại hay không và thứ tự hợp lệ.

### 18.4 Qualified name

~~~text
qualifiedName = identifier { "." identifier } ;
~~~

Grammar nhận diện đường dẫn tên. Semantic resolver xác định symbol thực tế và quyền truy cập.

### 18.5 Type grammar không đồng nghĩa type checking

Grammar có thể parse List<Order>, nhưng type checker cần xác định Order có tồn tại và List có nhận kiểu đó không.

## 19. Grammar cho comment và formatting

Comment và whitespace có ảnh hưởng đến trải nghiệm người dùng dù thường không ảnh hưởng semantics.

### 19.1 Line comment

~~~text
// Validate the order before payment
~~~

### 19.2 Block comment

~~~text
/*
  Multi-line explanation
*/
~~~

Nếu cho phép nested block comment, cần xác định lexer có thể xử lý nesting ra sao.

### 19.3 Documentation comment

Một dạng comment đặc biệt có thể gắn với declaration để tạo API documentation. Cần định nghĩa comment gắn vào node nào.

### 19.4 Whitespace-insensitive và newline-sensitive

DSL có thể bỏ qua newline như Java hoặc dùng newline làm separator như một số ngôn ngữ scripting. Newline-sensitive grammar cần xử lý continuation và multiline expression rõ ràng.

### 19.5 Formatter

Formatter nên dựa trên AST hoặc concrete syntax tree có đủ thông tin. Grammar và formatter cần thống nhất cách trình bày canonical.

## 20. Kiểm tra grammar bằng test

Không nên chờ đến khi compiler hoàn chỉnh mới kiểm tra grammar.

### 20.1 Positive tests

Mỗi production quan trọng cần có input hợp lệ. Bao gồm nested structure, optional clause và boundary.

### 20.2 Negative tests

Kiểm tra thiếu token, token sai vị trí, delimiter không đóng, expression thiếu toán hạng và keyword không hợp lệ.

### 20.3 Precedence tests

Dùng expression có nhiều operator và xác nhận AST grouping.

### 20.4 Ambiguity tests

Tạo input có prefix chung hoặc dangling else để xác nhận parser chọn cách hiểu đã định nghĩa.

### 20.5 Golden tests

Snapshot token stream, parse tree, AST dump và diagnostics để phát hiện thay đổi ngoài ý muốn.

### 20.6 Property tests

Một số thuộc tính hữu ích:

- Parse rồi pretty-print rồi parse lại vẫn giữ semantics.
- Formatter idempotent.
- Token ranges nằm trong source bounds.
- Parser không crash với input ngẫu nhiên trong giới hạn tài nguyên.

### 20.7 Fuzz tests

Fuzz lexer/parser với input malformed, Unicode, nesting sâu và chuỗi escape. Giới hạn CPU/memory để test không gây cạn tài nguyên.

## 21. Kiểm tra grammar và parser conflict

Một số parser generator cung cấp cảnh báo về ambiguity hoặc conflict.

### 21.1 FIRST và FOLLOW

FIRST(A) là tập terminal có thể bắt đầu chuỗi được sinh từ A. FOLLOW(A) là tập terminal có thể xuất hiện ngay sau A trong một derivation.

Với parser LL, FIRST/FOLLOW giúp kiểm tra parser có thể chọn production dựa trên lookahead hay không.

### 21.2 LL(1)

LL(1) parser đọc từ trái sang phải, tạo leftmost derivation và dùng một token lookahead. Grammar LL(1) thường dễ triển khai bằng recursive descent nhưng không phải mọi ngôn ngữ cần giới hạn ở LL(1).

### 21.3 Shift/reduce conflict

Trong parser LR, conflict có thể cho thấy parser không biết nên shift token tiếp theo hay reduce production hiện tại.

### 21.4 Reduce/reduce conflict

Parser có nhiều production có thể reduce tại cùng một vị trí. Đây thường là dấu hiệu grammar cần được phân tích lại.

### 21.5 Conflict resolution

Một số công cụ cho phép precedence declaration hoặc rule priority. Dùng chúng có chủ đích và ghi lại semantics; không chỉ suppress warning để build thành công.

## 22. Tối ưu grammar mà vẫn giữ khả năng đọc

Grammar là tài liệu sống của ngôn ngữ. Tối ưu parser không nên làm grammar khó hiểu hơn mức cần thiết.

### 22.1 Left factoring

Tách prefix chung để parser chọn nhánh rõ hơn.

### 22.2 Loại bỏ production không dùng

Production chết làm grammar khó đọc và tạo hiểu nhầm về syntax được hỗ trợ.

### 22.3 Tránh lặp rule

Tạo nonterminal dùng chung khi semantics giống nhau. Không gộp những rule chỉ trông giống nhưng có behavior khác.

### 22.4 Đặt tên có ý nghĩa

Tên như policyDeclaration, functionCall và comparisonExpression dễ hiểu hơn rule1 hoặc item2.

### 22.5 Chia grammar theo module

Với DSL lớn, có thể chia lexer, expression, declaration và statement grammar hoặc dùng grammar import theo khả năng tool.

### 22.6 Comment grammar

Ghi chú lý do của precedence, ambiguity resolution và legacy syntax. Không lặp lại nội dung hiển nhiên của rule.

## 23. Versioning và tiến hóa grammar

Grammar là public language contract nếu người dùng viết source dựa trên nó.

### 23.1 Thêm syntax

Thêm construct thường có thể tương thích, nhưng có thể làm một chuỗi trước đây được xem là identifier trở thành keyword. Cần kiểm tra source cũ.

### 23.2 Đổi keyword

Đổi tên keyword có thể làm source cũ không parse. Có thể giữ alias trong một migration window.

### 23.3 Thay precedence

Thay precedence có thể làm cùng source tạo AST khác mà không có syntax error. Đây là thay đổi semantics rất nhạy cảm.

### 23.4 Remove syntax

Đánh dấu deprecated, cung cấp diagnostic và migration guide trước khi loại bỏ theo language version hoặc major release.

### 23.5 Language version

Compiler có thể hỗ trợ nhiều grammar version hoặc chọn grammar theo version khai báo trong source/project configuration.

### 23.6 Persisted AST/IR

Nếu AST hoặc IR được serialize, cần schema version và compatibility policy riêng. Không mặc định parse tree nội bộ là format lưu trữ ổn định.

## 24. Bảo mật khi viết grammar

Grammar và parser xử lý input có thể không tin cậy.

### 24.1 Giới hạn kích thước input

Giới hạn source size, token count và độ dài literal khi phù hợp.

### 24.2 Giới hạn nesting

Nesting sâu có thể gây stack overflow hoặc tiêu thụ memory. Parser/runtime cần giới hạn độ sâu và có cách báo lỗi.

### 24.3 Tránh catastrophic backtracking

Với regex lexer hoặc parser dựa trên backtracking, kiểm tra pattern có thể tạo thời gian xử lý tăng theo cấp số nhân.

### 24.4 Không thực thi khi parse

Parser chỉ nên xây dựng cấu trúc và diagnostic. Không thực hiện host API call hoặc side effect trong quá trình parse.

### 24.5 Error output an toàn

Không đưa source chứa secret hoặc dữ liệu nhạy cảm vào log rộng rãi. Diagnostic nên trích phần cần thiết.

### 24.6 Resource budget

Đặt timeout, memory budget hoặc cancellation cho parsing input lớn nếu môi trường yêu cầu.

## 25. Quy trình viết grammar từ đầu

Một quy trình thực hành:

1. **Xác định use case:** DSL cần diễn đạt những thao tác và khái niệm nào?
2. **Viết ví dụ:** tạo source hợp lệ và không hợp lệ.
3. **Chọn lexical policy:** identifier, keyword, literal, comment và operator.
4. **Định nghĩa top-level:** program, module hoặc document structure.
5. **Định nghĩa declaration:** policy, function, variable, type hoặc import.
6. **Định nghĩa statement:** block, conditional, loop, assignment và command.
7. **Định nghĩa expression:** primary, unary, binary và precedence.
8. **Viết EBNF:** tách production và đặt tên rõ.
9. **Chọn parser approach:** parser generator, recursive descent hoặc Pratt.
10. **Triển khai lexer/parser:** giữ source location và EOF handling.
11. **Map parse tree sang AST:** chỉ giữ cấu trúc có ý nghĩa.
12. **Định nghĩa diagnostics:** code, severity, range và recovery.
13. **Viết tests:** positive, negative, precedence, ambiguity và golden.
14. **Kiểm tra resource/security:** nesting, input size và parser behavior.
15. **Tài liệu hóa:** syntax reference, examples và grammar version.
16. **Chuẩn bị evolution:** deprecation, compatibility và migration.

## 26. Ví dụ tổng hợp: viết grammar cho policy DSL

Giả sử cần một DSL mô tả chính sách phê duyệt đơn hàng.

### 26.1 Yêu cầu

Ngôn ngữ cần hỗ trợ policy có tên, input có kiểu, biến local, Boolean condition, if/else, function call có argument, arithmetic và comparison expression.

### 26.2 Ví dụ source

~~~text
policy "OrderApproval" {
  input order: Order;

  let highValue = order.total >= 5000000;

  if highValue {
    decision.requireReview("HIGH_VALUE");
  } else {
    decision.approve();
  }
}
~~~

### 26.3 EBNF phác thảo

~~~text
program = policyDeclaration EOF ;

policyDeclaration =
  "policy" STRING "{" policyBody "}" ;

policyBody =
  { inputDeclaration } { statement } ;

inputDeclaration =
  "input" IDENTIFIER ":" typeName ";" ;

statement =
    letDeclaration
  | ifStatement
  | assignment
  | expressionStatement ;

letDeclaration =
  "let" IDENTIFIER "=" expression ";" ;

ifStatement =
  "if" expression block [ "else" block ] ;

block =
  "{" { statement } "}" ;

assignment =
  qualifiedName "=" expression ";" ;

expressionStatement =
  expression ";" ;

expression =
  logicalOr ;

logicalOr =
  logicalAnd { "or" logicalAnd } ;

logicalAnd =
  equality { "and" equality } ;

equality =
  comparison { ("==" | "!=") comparison } ;

comparison =
  additive { ("<" | "<=" | ">" | ">=") additive } ;

additive =
  multiplicative { ("+" | "-") multiplicative } ;

multiplicative =
  unary { ("*" | "/" | "%") unary } ;

unary =
  ("not" | "-") unary | primary ;

primary =
    literal
  | functionCall
  | qualifiedName
  | "(" expression ")" ;

functionCall =
  qualifiedName "(" [ argumentList ] ")" ;

argumentList =
  expression { "," expression } ;

qualifiedName =
  IDENTIFIER { "." IDENTIFIER } ;
~~~

### 26.4 AST mong đợi

Với condition:

~~~text
order.total >= 5000000
~~~

AST có thể là:

~~~text
BinaryExpression(GREATER_OR_EQUAL)
  left:
    MemberAccess
      target: NameExpression(order)
      member: total
  right:
    NumberLiteral(5000000)
~~~

### 26.5 Semantic checks

Sau parsing, semantic analyzer kiểm tra order đã được khai báo trong input, Order có field total, total có kiểu số phù hợp, highValue được suy luận là Boolean, decision.requireReview tồn tại, argument truyền vào function có kiểu đúng và principal có capability gọi decision command.

### 26.6 Diagnostics

Nếu viết:

~~~text
if order.total >= {
  decision.approve();
}
~~~

Parser nên báo thiếu expression sau toán tử >= và trỏ về vị trí phù hợp. Nó có thể phục hồi tại dấu đóng block để tiếp tục phân tích phần còn lại.

### 26.7 Test plan

Tạo fixture cho policy hợp lệ, input thiếu type, if thiếu block, precedence, nested call, string escape, unknown token và source range có Unicode.

### 26.8 Kết quả

Grammar tạo ra một syntax contract rõ. Parser kiểm tra hình thức, AST giữ cấu trúc cần thiết và semantic analyzer xác nhận ý nghĩa domain trước runtime.

## 27. Những sai lầm thường gặp khi viết grammar

### Viết grammar từ implementation thay vì domain

Grammar phản ánh class hoặc method nội bộ của host.

**Cách khắc phục:** bắt đầu từ use case và thuật ngữ domain.

### Một production expression quá tổng quát

Parser khó kiểm soát precedence và associativity.

**Cách khắc phục:** tách expression theo tầng hoặc dùng Pratt parser.

### Không yêu cầu EOF

Parser có thể chấp nhận một phần source và bỏ qua token thừa.

**Cách khắc phục:** dùng entry rule tiêu thụ toàn bộ input.

### Không định nghĩa keyword policy

Identifier có thể đột nhiên trở thành keyword khi thêm syntax mới.

**Cách khắc phục:** reserved/contextual keyword policy và compatibility tests.

### Bỏ qua source range

Parser chạy được nhưng editor và diagnostic không thể chỉ đúng vị trí.

**Cách khắc phục:** lưu token span và quy ước offset ngay từ đầu.

### Coi parser là type checker

Grammar chấp nhận cú pháp nhưng compiler không kiểm tra symbol/type.

**Cách khắc phục:** tách parsing khỏi semantic analysis.

### Suppress parser conflict

Build thành công nhưng grammar vẫn ambiguous hoặc chọn nhánh sai.

**Cách khắc phục:** hiểu conflict, thêm ví dụ và giải quyết bằng cấu trúc hoặc precedence có chủ đích.

### Sửa generated parser trực tiếp

Thay đổi bị mất khi regenerate và grammar source không còn phản ánh implementation.

**Cách khắc phục:** chỉnh grammar source và tái tạo artifact.

### Không test malformed input

Parser có thể crash hoặc tạo diagnostic cascade khi người dùng đang gõ dở.

**Cách khắc phục:** negative, recovery và fuzz tests.

### Không quản lý language version

Thay precedence hoặc keyword có thể âm thầm đổi nghĩa source cũ.

**Cách khắc phục:** language version, deprecation và migration policy.

## 28. Câu hỏi tự kiểm tra

1. Grammar mô tả điều gì trong một DSL?
2. Lexer, parser và semantic analyzer có trách nhiệm khác nhau như thế nào?
3. Vì sao cần thu thập ví dụ hợp lệ và không hợp lệ trước khi viết grammar?
4. EBNF biểu diễn lựa chọn, tùy chọn và lặp bằng những ký hiệu nào?
5. Terminal và nonterminal khác nhau ra sao?
6. Top-down grammar design bắt đầu từ đâu?
7. Lexer cần xử lý keyword, identifier, literal và operator như thế nào?
8. Longest match giúp phân biệt operator ra sao?
9. Vì sao dấu trừ thường được tokenize riêng với number literal?
10. Precedence và associativity quyết định parse tree như thế nào?
11. Left recursion trực tiếp có thể gây vấn đề gì với recursive descent parser?
12. Left factoring giải quyết common prefix như thế nào?
13. Ambiguous grammar là gì? Cho ví dụ dangling else.
14. ANTLR parser rule và lexer rule được phân biệt như thế nào?
15. Khi nào nên chọn parser generator, recursive descent hoặc Pratt parser?
16. Parse tree và AST khác nhau ở điểm nào?
17. Vì sao AST cần source location?
18. Parser recovery cần synchronization point và error node ra sao?
19. Những convention source offset nào cần được định nghĩa?
20. FIRST, FOLLOW và parser conflict giúp phân tích grammar như thế nào?
21. Những test nào cần có cho grammar?
22. Vì sao grammar cần được version hóa?
23. Những rủi ro bảo mật nào cần xét khi parse input không tin cậy?
24. Một quy trình viết grammar từ yêu cầu domain đến test gồm những bước nào?

Viết grammar là bước chuyển yêu cầu domain thành một hợp đồng cú pháp rõ ràng cho DSL. Khi lexical rules, production, precedence, associativity, ambiguity, AST mapping, diagnostics và test được thiết kế có chủ đích, parser có thể xử lý source nhất quán và tạo nền tảng ổn định cho semantic analysis, tooling và runtime.

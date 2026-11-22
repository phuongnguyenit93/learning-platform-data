# ANTLR

## 1. ANTLR là gì?

ANTLR (*ANother Tool for Language Recognition*) là một công cụ sinh bộ phân tích cú pháp (*parser generator*) từ grammar. Thay vì tự viết toàn bộ lexer và parser bằng tay, người phát triển mô tả cấu trúc ngôn ngữ trong các file grammar. ANTLR đọc grammar và sinh mã nguồn cho lexer, parser cùng các thành phần hỗ trợ theo target language được chọn.

Trong phát triển DSL (*Domain-Specific Language*), ANTLR có thể được dùng để xây dựng front-end cho:
- Ngôn ngữ cấu hình.
- Ngôn ngữ quy tắc nghiệp vụ.
- DSL truy vấn.
- Ngôn ngữ mô tả workflow.
- Ngôn ngữ khai báo schema.
- Ngôn ngữ biểu thức nhúng trong ứng dụng.
- Ngôn ngữ script có phạm vi và kiểu dữ liệu giới hạn.

Ví dụ, một DSL quy tắc:

~~~text
rule "large-order" {
    when order.total >= 1000000
    then applyDiscount(order, 0.05)
}
~~~

Grammar mô tả cách viết hợp lệ của rule. ANTLR sinh lexer để nhận diện token như keyword, identifier, string, dấu ngoặc và toán tử; parser kết hợp token thành cấu trúc như rule declaration, condition và action call.

Sau khi parser tạo parse tree, ứng dụng có thể duyệt cây để tạo AST hoặc model miền, resolve tên, kiểm tra kiểu và chuẩn bị thực thi.

ANTLR cung cấp phần nhận diện cú pháp. Nó không tự định nghĩa toàn bộ semantics của DSL, không tự tạo runtime nghiệp vụ và cũng không tự quyết định các quy tắc như quyền truy cập, kiểu dữ liệu hay thứ tự thực thi. Những phần đó cần được thiết kế trong các lớp tiếp theo của toolchain.

## 2. Vị trí của ANTLR trong DSL toolchain

Một kiến trúc DSL phổ biến:

~~~text
DSL source
    |
    v
ANTLR Lexer
    |
    v
Token stream
    |
    v
ANTLR Parser
    |
    v
Parse tree
    |
    v
AST / Domain model builder
    |
    v
Name resolution and type checking
    |
    v
Validation and diagnostics
    |
    v
Interpreter / Compiler / Model transformation
~~~

Các bước có trách nhiệm riêng:

| Thành phần | Trách nhiệm |
|---|---|
| Grammar | Định nghĩa token và cấu trúc cú pháp |
| Lexer | Chuyển ký tự thành token |
| Token stream | Lưu chuỗi token cho parser |
| Parser | Kiểm tra thứ tự token và tạo parse tree |
| Parse tree | Biểu diễn các rule grammar đã khớp |
| AST builder | Tạo mô hình trừu tượng phục vụ ứng dụng |
| Semantic analyzer | Resolve symbol, kiểm tra kiểu và ràng buộc |
| Runtime/compiler | Thực thi hoặc chuyển đổi chương trình |

ANTLR thường sinh lexer và parser từ cùng một grammar hoặc từ hai grammar riêng. Ứng dụng host chịu trách nhiệm quản lý source files, cấu hình, diagnostics, semantic model và runtime.

## 3. Grammar trong ANTLR

Grammar là mô tả hình thức về các chuỗi mà ngôn ngữ chấp nhận. Trong ANTLR, grammar thường chứa:
- Lexer rules: mô tả token.
- Parser rules: mô tả cấu trúc token.
- Các lựa chọn, lặp và nhóm.
- Precedence và associativity thông qua cách tổ chức parser rules.
- Một số tùy chọn hoặc hành vi mở rộng.

### 3.1. Parser rule và lexer rule

Quy ước phổ biến:
- Parser rule bắt đầu bằng chữ thường.
- Lexer rule bắt đầu bằng chữ hoa.

Ví dụ:

~~~antlr
grammar MiniCalc;

program
    : statement* EOF
    ;

statement
    : ID '=' expression ';'
    ;

expression
    : INT
    | ID
    ;

ID
    : [a-zA-Z_] [a-zA-Z_0-9]*
    ;

INT
    : [0-9]+
    ;

WS
    : [ \t\r\n]+ -> skip
    ;
~~~

`program`, `statement` và `expression` là parser rules. `ID`, `INT` và `WS` là lexer rules.

Lexer rule mô tả cách nhận diện một token từ ký tự. Parser rule mô tả cách kết hợp token thành cấu trúc lớn hơn.

### 3.2. Cú pháp lựa chọn và lặp

Các ký hiệu thường gặp:

| Cú pháp | Ý nghĩa |
|---|---|
| `A B` | A theo sau bởi B |
| `A \| B` | Chọn A hoặc B |
| `A?` | A xuất hiện 0 hoặc 1 lần |
| `A*` | A xuất hiện 0 hoặc nhiều lần |
| `A+` | A xuất hiện ít nhất 1 lần |
| `(A B)` | Nhóm các phần tử |
| `~A` | Token hoặc ký tự không thuộc A trong ngữ cảnh lexer phù hợp |
| `EOF` | Kết thúc input |

Ví dụ:

~~~antlr
parameterList
    : parameter (',' parameter)*
    ;

parameter
    : ID ':' typeName
    ;
~~~

Grammar cho phép danh sách parameter có một hoặc nhiều phần tử, phân cách bằng dấu phẩy.

### 3.3. Labels

Label giúp đặt tên cho token hoặc rule reference trong một alternative:

~~~antlr
assignment
    : target=ID '=' value=expression
    ;
~~~

Generated context có thể cung cấp các field tương ứng để visitor hoặc listener truy cập. Label giúp code xử lý dễ đọc hơn so với việc dựa vào chỉ số child hoặc vị trí token.

### 3.4. Alternative labels

Có thể đặt tên cho từng alternative để tạo context class riêng:

~~~antlr
expression
    : left=expression op=('*' | '/') right=expression # Multiplicative
    | left=expression op=('+' | '-') right=expression # Additive
    | INT                                            # IntegerLiteral
    | ID                                             # Identifier
    | '(' expression ')'                            # Parenthesized
    ;
~~~

Các alternative labels hữu ích khi xây AST vì mỗi loại biểu thức có thể được xử lý trong method riêng.

## 4. Combined grammar và tách lexer/parser grammar

### 4.1. Combined grammar

Một combined grammar chứa cả parser rules và lexer rules:

~~~antlr
grammar ConfigDsl;

document
    : declaration* EOF
    ;

declaration
    : 'setting' ID '=' value ';'
    ;

value
    : STRING
    | INT
    | 'true'
    | 'false'
    ;

ID
    : [a-zA-Z_] [a-zA-Z_0-9]*
    ;

INT
    : [0-9]+
    ;

STRING
    : '"' (~["\\\r\n] | '\\' .)* '"'
    ;

WS
    : [ \t\r\n]+ -> skip
    ;
~~~

Cách này thuận tiện cho grammar nhỏ và vừa, khi lexer và parser gắn chặt với nhau.

### 4.2. Lexer grammar riêng

Một lexer grammar chỉ định nghĩa token:

~~~antlr
lexer grammar ConfigLexer;

SETTING: 'setting';
TRUE: 'true';
FALSE: 'false';
ASSIGN: '=';
SEMI: ';';
ID: [a-zA-Z_] [a-zA-Z_0-9]*;
INT: [0-9]+;
WS: [ \t\r\n]+ -> skip;
~~~

### 4.3. Parser grammar riêng

Parser grammar dùng token vocabulary từ lexer grammar:

~~~antlr
parser grammar ConfigParser;

options {
    tokenVocab = ConfigLexer;
}

document
    : declaration* EOF
    ;

declaration
    : SETTING ID ASSIGN value SEMI
    ;

value
    : TRUE
    | FALSE
    | INT
    | ID
    ;
~~~

Tách grammar có ích khi lexer phức tạp, nhiều mode hoặc cần tái sử dụng token vocabulary. Đổi lại, build pipeline phải sinh lexer trước để parser có thể dùng token vocabulary.

### 4.4. Khi nào chọn cách nào?

| Tình huống | Lựa chọn thường phù hợp |
|---|---|
| DSL nhỏ, cú pháp đơn giản | Combined grammar |
| Lexer có nhiều mode | Tách lexer và parser |
| Nhiều parser dùng chung token | Lexer grammar riêng |
| Nhiều người cùng quản lý grammar lớn | Tách theo trách nhiệm hoặc module có quy ước rõ |
| Embedded language phức tạp | Có thể dùng lexer/parser riêng cho từng vùng |

Không có quy tắc bắt buộc rằng grammar lớn phải luôn tách. Điều quan trọng là build, token ownership và cách quản lý dependency rõ ràng.

## 5. Lexer rules và tokenization

Lexer đọc ký tự nguồn và tạo token stream. Mỗi token thường có:
- Token type.
- Text hoặc lexeme.
- Start và stop index.
- Line và column.
- Channel.
- Token index.

Ví dụ:

~~~text
total = price + tax
~~~

Token stream khái niệm:

~~~text
ID("total")
ASSIGN("=")
ID("price")
PLUS("+")
ID("tax")
EOF
~~~

### 5.1. Longest match và rule priority

Khi nhiều lexer rules có thể khớp tại cùng vị trí, ANTLR thường ưu tiên rule khớp chuỗi dài nhất; nếu độ dài bằng nhau, thứ tự rule có thể quyết định token được chọn.

Ví dụ:

~~~antlr
IF: 'if';
ID: [a-zA-Z_] [a-zA-Z_0-9]*;
~~~

Chuỗi `if` khớp cả IF và ID với cùng độ dài, nên thứ tự rule làm IF được chọn. Chuỗi `ifReady` dài hơn theo ID nên được nhận diện là identifier.

Cần định nghĩa keyword và identifier cẩn thận để tránh tên hợp lệ bị chia sai.

### 5.2. Whitespace và skip

Nếu whitespace không có ý nghĩa trong DSL, có thể bỏ qua:

~~~antlr
WS
    : [ \t\r\n]+ -> skip
    ;
~~~

Nếu formatter, comment attachment hoặc tooling cần giữ whitespace/newline, có thể gửi token sang channel ẩn thay vì loại bỏ hoàn toàn.

### 5.3. Channels

Token channel cho phép giữ token mà parser mặc định không xử lý như token cú pháp. Channel thường dùng:
- Default channel cho token parser cần.
- Hidden channel cho whitespace/comment hoặc trivia.

Ví dụ:

~~~antlr
LINE_COMMENT
    : '//' ~[\r\n]* -> channel(HIDDEN)
    ;

WS
    : [ \t\r\n]+ -> channel(HIDDEN)
    ;
~~~

Giữ comment trong token stream giúp formatter, documentation tool và editor gắn comment với node phù hợp.

### 5.4. String literal và escape

Một lexer rule string đơn giản:

~~~antlr
STRING
    : '"' (ESCAPE | ~["\\\r\n])* '"'
    ;

fragment ESCAPE
    : '\\' [btnfr"\\]
    ;
~~~

Đây chỉ là ví dụ về tập escape. DSL thực tế phải định nghĩa rõ escape Unicode, multiline string, raw string và lỗi khi gặp escape không hợp lệ.

### 5.5. Number literal

Ví dụ:

~~~antlr
NUMBER
    : DIGIT+ ('.' DIGIT+)? ([eE] [+-]? DIGIT+)?
    ;

fragment DIGIT
    : [0-9]
    ;
~~~

Nếu DSL hỗ trợ hex, exponent, đơn vị hoặc dấu phân cách chữ số, cần mở rộng grammar và test các trường hợp ranh giới. Lexer xác định lexeme; bước semantic hoặc literal conversion có thể kiểm tra miền giá trị.

### 5.6. Lexer modes

Lexer mode hữu ích khi cách nhận diện token phụ thuộc context, ví dụ:
- Nội dung bên trong string template.
- Embedded SQL.
- Block comment.
- Interpolation.
- Markup và expression xen kẽ.

Một mode có thể có lexer rules riêng. Lệnh `pushMode`, `popMode` hoặc `mode` điều khiển chuyển trạng thái.

Ví dụ khái niệm cho template:

~~~antlr
OPEN_TEMPLATE
    : '{{' -> pushMode(EXPRESSION)
    ;

mode EXPRESSION;

CLOSE_TEMPLATE
    : '}}' -> popMode
    ;

EXPR_ID
    : [a-zA-Z_] [a-zA-Z_0-9]*
    ;

EXPR_WS
    : [ \t\r\n]+ -> skip
    ;
~~~

Mode giúp lexer thay đổi vocabulary theo context. Cần xử lý rõ EOF khi đang ở mode khác và tránh mode stack không được đóng.

## 6. Parser rules và cấu trúc DSL

Parser kết hợp token thành cấu trúc theo grammar. Parser rule có thể mô tả:
- Program hoặc document root.
- Declaration.
- Statement.
- Expression.
- Type.
- Rule hoặc workflow.
- Block và collection.

Ví dụ DSL cấu hình:

~~~antlr
document
    : declaration* EOF
    ;

declaration
    : 'setting' ID ':' typeName '=' value ';'
    ;

typeName
    : 'String'
    | 'Integer'
    | 'Boolean'
    ;

value
    : STRING
    | INT
    | BOOLEAN
    ;

BOOLEAN
    : 'true'
    | 'false'
    ;
~~~

Trong grammar thực tế, keyword có thể được định nghĩa thành token riêng để dễ quản lý, thay vì dùng string literal ở parser rule.

### 6.1. EOF ở root rule

Root parser rule thường nên kết thúc bằng EOF:

~~~antlr
program
    : statement* EOF
    ;
~~~

Nếu không có EOF, parser có thể chấp nhận một prefix hợp lệ rồi để lại token thừa mà caller không nhận ra.

### 6.2. Optional và repeated constructs

Ví dụ block có thể rỗng hoặc chứa nhiều statement:

~~~antlr
block
    : '{' statement* '}'
    ;
~~~

Nếu cần ít nhất một statement, dùng `statement+`. Chọn đúng multiplicity để grammar phản ánh semantics và diagnostics rõ ràng.

### 6.3. Dangling else

Grammar của conditional cần tránh ambiguity về else thuộc if nào. Một cách thông dụng là để parser rule lồng cấu trúc if và định nghĩa rõ alternative cho nhánh else. Cần test nested if để xác nhận binding theo mong muốn.

### 6.4. Left recursion và expression grammar

Biểu thức thường có left recursion tự nhiên:

~~~antlr
expr
    : expr '*' expr
    | expr '+' expr
    | INT
    ;
~~~

ANTLR 4 hỗ trợ một số dạng direct left recursion và có thể chuyển đổi nội bộ để xử lý precedence. Tuy vậy, grammar phải tuân theo giới hạn và quy tắc của ANTLR; indirect left recursion không được hỗ trợ giống direct left recursion.

Một cách viết rõ precedence:

~~~antlr
expression
    : expression op=('*' | '/') expression # Multiplicative
    | expression op=('+' | '-') expression # Additive
    | INT                                   # IntegerLiteral
    | ID                                    # Identifier
    | '(' expression ')'                   # Parenthesized
    ;
~~~

Thứ tự alternative ảnh hưởng precedence trong direct left-recursive rule. Nên có test cho precedence và associativity thay vì dựa vào trực giác.

### 6.5. Associativity

Phép trừ thường left-associative:

~~~text
a - b - c
~~~

được hiểu là:

~~~text
(a - b) - c
~~~

Một số toán tử có thể right-associative, chẳng hạn phép lũy thừa theo đặc tả DSL. ANTLR hỗ trợ chỉ định associativity trong các trường hợp grammar phù hợp; cần xác nhận hành vi bằng parse tree tests.

## 7. Tạo AST hoặc model từ parse tree

ANTLR tạo parse tree phản ánh grammar. Ứng dụng thường không muốn dùng trực tiếp parse tree làm domain model vì parse tree chứa nhiều chi tiết cú pháp như dấu ngoặc, dấu phẩy và node grammar trung gian.

Một bước AST builder có thể:
- Bỏ node chỉ phục vụ grammar.
- Tạo node biểu thức và statement.
- Chuẩn hóa literal.
- Gắn source span.
- Gắn metadata cần cho semantic analysis.
- Giữ comment hoặc trivia ở một cấu trúc phụ nếu cần.

Ví dụ:

~~~antlr
assignment
    : target=ID '=' value=expression ';'
    ;
~~~

AST có thể là:

~~~text
AssignmentNode
- target: Identifier("total")
- value: BinaryExpression(
    operator = "+",
    left = Identifier("price"),
    right = Identifier("tax")
  )
- sourceRange: ...
~~~

AST nên mô tả ý nghĩa cấu trúc DSL thay vì sao chép nguyên xi từng parser context.

### 7.1. Giữ source location

Mỗi AST node nên có source span để diagnostics có thể trỏ về source. Có thể lấy start/stop token từ parser context và chuyển sang range của ứng dụng.

Cần xác định đơn vị offset: byte, UTF-16 code unit hoặc Unicode code point. Editor protocol có thể dùng đơn vị khác với lexer/runtime nội bộ.

### 7.2. Parse tree hay AST?

| Tiêu chí | Parse tree | AST/domain model |
|---|---|---|
| Phản ánh grammar | Rất trực tiếp | Đã trừu tượng hóa |
| Giữ dấu cú pháp | Có thể truy cập token và context | Thường loại bỏ |
| Phù hợp semantic model | Không phải lúc nào | Thường phù hợp hơn |
| Dùng cho formatter | Có ích nếu giữ trivia | Cần source/token mapping bổ sung |
| Ổn định khi grammar thay đổi | Có thể thay đổi mạnh | Có thể giữ API ổn định hơn |

Có thể giữ cả parse tree và AST: parse tree cho editor tooling, AST cho semantics và runtime.

## 8. Listener và Visitor

ANTLR cung cấp hai phong cách duyệt parse tree thường dùng: listener và visitor.

### 8.1. Listener

Listener nhận callback khi traversal đi vào hoặc rời khỏi rule. Các method thường có dạng enter/exit cho parser rule.

Ví dụ:

~~~java
public class DeclarationListener
        extends MiniCalcBaseListener {

    @Override
    public void exitStatement(MiniCalcParser.StatementContext ctx) {
        String name = ctx.ID().getText();
        System.out.println("Found assignment: " + name);
    }
}
~~~

Listener phù hợp khi muốn phản ứng theo các sự kiện traversal và có thể dùng ParseTreeWalker để duyệt cây.

### 8.2. Visitor

Visitor gọi method tương ứng với node và trả về giá trị do ứng dụng định nghĩa.

Ví dụ:

~~~java
public class AstBuilder extends MiniCalcBaseVisitor<AstNode> {

    @Override
    public AstNode visitIntegerLiteral(
            MiniCalcParser.IntegerLiteralContext ctx) {
        return new IntegerNode(
            Integer.parseInt(ctx.INT().getText())
        );
    }

    @Override
    public AstNode visitIdentifier(
            MiniCalcParser.IdentifierContext ctx) {
        return new IdentifierNode(ctx.ID().getText());
    }
}
~~~

Visitor thường phù hợp khi xây AST hoặc tính giá trị từ cây. Có thể dùng kiểu trả về cụ thể như AstNode, ExpressionNode hoặc một result type riêng.

### 8.3. So sánh Listener và Visitor

| Tiêu chí | Listener | Visitor |
|---|---|---|
| Điều khiển traversal | Thường do walker quản lý | Visitor quyết định gọi child nào |
| Giá trị trả về | Không có cơ chế return tree value mặc định | Có thể trả kết quả |
| Phù hợp | Thu thập thông tin, sự kiện enter/exit | AST building, evaluation, transformation |
| Bỏ qua child | Cần điều khiển walker hoặc trạng thái | Có thể không gọi visit child |
| Quản lý context | Thường dùng stack hoặc state | Có thể truyền qua tham số |

Không có lựa chọn duy nhất cho mọi dự án. Listener phù hợp với traversal đồng đều; visitor phù hợp khi mỗi node cần logic và kết quả riêng.

### 8.4. Alternative labels và generated methods

Khi dùng alternative labels, ANTLR sinh context class riêng cho từng alternative và method visitor/listener tương ứng. Điều này làm code xử lý rõ hơn, đặc biệt với expression tree.

Nên đặt label có ý nghĩa và tránh phụ thuộc vào tên generated class nếu grammar chưa ổn định.

## 9. Semantic analysis sau ANTLR parsing

ANTLR xác nhận cấu trúc theo grammar, nhưng một chương trình có thể parse thành công mà vẫn sai về ngữ nghĩa.

Ví dụ:

~~~text
let total: Money = customer.name
~~~

Grammar có thể chấp nhận declaration, type và property access. Semantic analyzer mới xác định customer.name là String hay Money và assignment có hợp lệ không.

Các bước semantic thường gồm:

1. Thu thập declaration.
2. Xây scope và symbol table.
3. Resolve identifier và qualified name.
4. Kiểm tra type compatibility.
5. Kiểm tra constraint liên node.
6. Kiểm tra quyền và visibility.
7. Gắn semantic metadata vào AST.
8. Tạo diagnostics.

### 9.1. Symbol table

Symbol table ánh xạ tên trong scope đến declaration hoặc symbol:

~~~text
Scope: Billing
  customerLimit -> VariableSymbol
  calculateTax  -> FunctionSymbol

Scope: Billing.check
  order         -> ParameterSymbol
~~~

Nếu có shadowing, lookup phải theo quy tắc scope. Không nên chỉ dùng một map toàn cục theo tên.

### 9.2. Type checking

Semantic analyzer có thể duyệt AST để suy luận kiểu:

~~~text
inferType(BinaryExpression("+", left, right))
~~~

Sau đó kiểm tra operator có hỗ trợ cặp kiểu đó không và kiểu kết quả có tương thích với context hay không.

### 9.3. Cross-reference và graph invariants

Một workflow có thể parse được nhưng tham chiếu đến step không tồn tại. Đây là lỗi semantic, không phải syntax error. Semantic analyzer cần resolve references và kiểm tra các invariant trên toàn model.

### 9.4. Tách grammar khỏi semantics

Không nên nhồi mọi quy tắc nghiệp vụ vào parser grammar hoặc semantic actions. Tách riêng giúp:
- Grammar tập trung vào cú pháp.
- Semantic rules có thể test độc lập.
- Diagnostics có thể phân loại.
- Runtime và editor dùng chung model.
- Thay đổi grammar ít gây ảnh hưởng đến domain logic.

## 10. Error handling và recovery

Một parser hữu ích cho DSL editor cần cung cấp diagnostics tốt và có thể tiếp tục phân tích sau một số lỗi.

### 10.1. Lexer errors

Ví dụ:
- Ký tự không hợp lệ.
- String chưa đóng.
- Escape không hợp lệ.
- Number literal sai.
- Comment chưa đóng.

Lexer cần tạo thông báo có source range và tránh lặp vô hạn khi gặp ký tự không nhận diện.

### 10.2. Parser errors

Ví dụ:

~~~text
rule "discount" {
    when order.total >
    then applyDiscount(order)
}
~~~

Parser có thể báo thiếu expression sau toán tử lớn hơn. Diagnostic nên trỏ vào vị trí lỗi hoặc token mà parser mong đợi.

### 10.3. Error listeners

ANTLR cho phép gắn error listener để nhận syntax errors. Ứng dụng có thể triển khai listener riêng để thu thập:
- Line và column.
- Offending token.
- Error message.
- Exception hoặc expected token information nếu có.

Không nên chỉ in lỗi ra console trong ứng dụng editor. Cần chuyển lỗi sang diagnostic model của DSL.

### 10.4. Default error strategy

ANTLR cung cấp error strategy để xử lý lỗi cú pháp. Parser có thể thực hiện recovery bằng cách chèn hoặc bỏ token trong một số tình huống để tiếp tục parse.

Recovery tree hữu ích cho editor vì người dùng vẫn nhận được nhiều diagnostics. Nhưng parse tree sau recovery không nên được coi là chương trình hợp lệ để thực thi.

### 10.5. Bail strategy

Trong một số pipeline, có thể muốn dừng ngay khi parse error đầu tiên xuất hiện, ví dụ compile batch nghiêm ngặt hoặc kiểm tra format artifact. Khi đó có thể dùng chiến lược bail phù hợp.

Lựa chọn recovery hay bail phụ thuộc mục tiêu:
- Editor cần tiếp tục phân tích.
- Compiler có thể thu thập nhiều lỗi rồi dừng trước code generation.
- Runtime không nên thực thi model không hợp lệ.

### 10.6. Diagnostic ổn định

Nên chuyển lỗi ANTLR sang mã lỗi và message do DSL định nghĩa. Không nên để ứng dụng phụ thuộc trực tiếp vào câu chữ nội bộ của runtime ANTLR vì message có thể thay đổi giữa version.

## 11. Grammar ambiguity và debugging

Grammar có thể có nhiều cách parse cho cùng một chuỗi hoặc có xung đột trong dự đoán alternative.

### 11.1. Ambiguity

Ví dụ một grammar expression quá rộng có thể khiến parser không biết một chuỗi thuộc alternative nào. Ambiguity thường xuất hiện ở:
- Optional constructs chồng lấn.
- Dangling else.
- Prefix expression.
- Các alternative có prefix chung.
- Embedded language boundary.
- Rule có nhiều cách diễn giải hợp lệ.

### 11.2. Left recursion

ANTLR 4 hỗ trợ direct left recursion cho parser rules trong phạm vi được hỗ trợ. Grammar expression thường dùng cách này để thể hiện precedence. Cần tránh nhầm direct left recursion với indirect/mutual recursion.

### 11.3. Common prefixes

Nếu nhiều alternative bắt đầu bằng cùng token sequence, parser có thể cần nhìn trước thêm token. Có thể left-factor grammar để làm rõ cấu trúc:

~~~antlr
statement
    : ID ('=' expression ';' | '(' argumentList? ')' ';')
    ;
~~~

Đây là ví dụ factoring; grammar thực tế cần cân nhắc ambiguity và semantics.

### 11.4. Diagnostic tool của ANTLR

Khi phát triển grammar, có thể bật parser diagnostics hoặc profiling để xem:
- Decision nào tốn nhiều lookahead.
- Alternative nào gây ambiguity.
- Rule nào có prediction conflict.
- Parse tree được xây như thế nào.

Cần dùng đúng công cụ theo version ANTLR và target runtime. Không nên tối ưu grammar chỉ để loại bỏ warning mà chưa xác nhận semantics.

### 11.5. Grammar tests

Với mỗi construct:
- Một ví dụ hợp lệ tối thiểu.
- Một ví dụ hợp lệ phức tạp.
- Ví dụ ở ranh giới.
- Ví dụ không hợp lệ.
- Ví dụ có thể gây ambiguity.
- Ví dụ có nested structure.

Test nên xác nhận parse tree hoặc AST shape, không chỉ kiểm tra parser không ném exception.

## 12. Semantic predicates và actions

ANTLR hỗ trợ một số cơ chế mở rộng như semantic predicates và embedded actions. Chúng có thể hữu ích nhưng cần dùng thận trọng.

### 12.1. Semantic predicate

Predicate là điều kiện Boolean được dùng trong quá trình parsing để hỗ trợ quyết định alternative trong những trường hợp grammar cần context.

Ví dụ minh họa:

~~~antlr
declaration
    : {isTypeName(_input.LT(1).getText())}? ID ID ';'
    ;
~~~

Đây chỉ là ví dụ khái niệm; cú pháp và vị trí predicate cần tuân theo ANTLR version và target language.

Predicate có thể làm parser phụ thuộc symbol table hoặc context bên ngoài. Nếu state thay đổi không nhất quán, kết quả parse có thể khó tái lập.

### 12.2. Embedded actions

Grammar có thể chứa code target language chạy khi parser/lexer xử lý rule. Ví dụ action có thể cập nhật state hoặc tạo giá trị.

Hạn chế:
- Grammar bị gắn với một target language.
- Khó tái sử dụng.
- Khó test độc lập.
- Có thể làm parsing có side effect.
- Dễ trộn syntax với domain semantics.

Với DSL cần hỗ trợ nhiều target language hoặc editor tooling, thường nên giữ grammar tương đối khai báo và thực hiện AST/semantic work ở lớp riêng.

### 12.3. Khi nào dùng?

Predicate/action có thể hợp lý khi:
- Cần context-sensitive disambiguation mà grammar thuần không đủ.
- Có một parser target cố định.
- Logic nhỏ, ổn định và được test.
- Chi phí tách ra không đáng kể.

Nếu logic là quy tắc nghiệp vụ, quyền truy cập hoặc type checking, nên đặt trong semantic analyzer.

## 13. Generated code và target language

ANTLR sinh mã cho target language được hỗ trợ. Runtime tương ứng cần được đưa vào ứng dụng.

Các artifact thường gồm:
- Lexer class.
- Parser class.
- Base listener và listener interface.
- Base visitor và visitor interface nếu bật visitor generation.
- Token vocabulary hoặc metadata.
- Serialized ATN hoặc dữ liệu automaton nội bộ.

Tên class và file phụ thuộc grammar name, package và cấu hình tool.

### 13.1. Generated source không phải source để sửa tay

Không nên sửa trực tiếp generated lexer/parser vì lần generate tiếp theo sẽ ghi đè. Thay đổi cần được thực hiện ở:
- Grammar.
- Code wrapper hoặc base class do ứng dụng sở hữu.
- AST builder.
- Error listener/strategy.
- Build configuration.

### 13.2. Target language

ANTLR hỗ trợ nhiều target language qua tool/runtime tương ứng. Cần xác nhận:
- Target được hỗ trợ bởi version đang dùng.
- Runtime library tương thích.
- Cấu hình package/namespace.
- Quy trình build.
- Khả năng debug và tooling.

Không nên trộn generated code từ một version tool với runtime version khác nếu không có compatibility được xác nhận.

### 13.3. Version compatibility

Tool và runtime nên được quản lý cùng version hoặc theo compatibility matrix chính thức. Khi nâng version:
- Regenerate parser.
- Compile lại.
- Chạy grammar tests.
- Chạy semantic integration tests.
- Kiểm tra diagnostics và performance.
- Kiểm tra generated artifacts có thay đổi ngoài dự kiến.

## 14. Tích hợp ANTLR trong Java project

Một quy trình build khái niệm:

1. Lưu grammar trong source directory được build system quản lý.
2. Chạy ANTLR tool để sinh Java source.
3. Compile generated source cùng application code.
4. Đưa ANTLR runtime dependency vào classpath.
5. Khởi tạo CharStream, lexer, token stream và parser.
6. Gọi root parser rule.
7. Xử lý diagnostics.
8. Duyệt parse tree để tạo AST/model.

Ví dụ Java:

~~~java
String source = """
    let total = price + tax;
    """;

CharStream input = CharStreams.fromString(source);

MiniCalcLexer lexer = new MiniCalcLexer(input);
CommonTokenStream tokens = new CommonTokenStream(lexer);
MiniCalcParser parser = new MiniCalcParser(tokens);

MiniCalcParser.ProgramContext tree = parser.program();

AstBuilder builder = new AstBuilder();
AstNode model = builder.visit(tree);
~~~

Tên class ở ví dụ giả định grammar có tên MiniCalc. Một ứng dụng thực tế nên cấu hình error listener trước khi parse, kiểm tra syntax error và không chuyển recovery tree thành executable model nếu parse thất bại.

### 14.1. Build integration

Build tool cần biết:
- Input grammar files.
- Output directory.
- Target language.
- Package hoặc namespace.
- Có sinh visitor/listener không.
- ANTLR tool version.
- Runtime dependency version.

Generated output nên nằm trong thư mục build hoặc generated source được quản lý rõ. Không nên để nhiều nguồn grammar khác nhau sinh class trùng tên.

### 14.2. Runtime lifecycle

Với mỗi source document, ứng dụng thường tạo:
- CharStream.
- Lexer.
- TokenStream.
- Parser.
- Error collector.
- Parse tree.

Các object này có thể giữ state theo lần parse. Không nên chia sẻ một parser instance giữa các thread hoặc document đồng thời nếu runtime không bảo đảm thread safety.

### 14.3. Reuse và caching

Có thể cache:
- Grammar-generated classes (đã được load).
- Parse tree hoặc AST theo document version.
- Semantic model.
- Compiled representation.

Cache phải gắn với source version và grammar/runtime version. Khi source hoặc grammar đổi, kết quả cũ phải bị invalidation.

## 15. Tích hợp ANTLR với DSL editor và LSP

ANTLR có thể làm parser backend cho language server.

Một luồng xử lý:
- Editor gửi document open/change.
- Language server cập nhật document snapshot.
- Lexer/parser phân tích source.
- Error listener tạo diagnostics.
- AST builder tạo semantic model.
- Resolver tạo symbol/reference information.
- Server cung cấp completion, hover, definition, references và formatting.

### 15.1. Incremental parsing

ANTLR parser thông thường có thể parse lại toàn bộ input. Với file nhỏ, cách này thường đủ đơn giản. Với file lớn hoặc thao tác realtime, có thể:
- Debounce document changes.
- Cancel parse cũ.
- Parse nền.
- Cache AST theo version.
- Dùng parser strategy hoặc thư viện hỗ trợ incremental nếu phù hợp.
- Chỉ chạy semantic passes bị ảnh hưởng khi có dependency tracking.

Không nên tuyên bố ANTLR tự động cung cấp incremental parsing cho mọi grammar; cần thiết kế rõ phần quản lý document và cập nhật cây.

### 15.2. Code completion

Completion có thể dùng token stream, parse context và semantic model để xác định loại token hợp lệ tại vị trí con trỏ.

Khi source chưa hoàn chỉnh, parser recovery có thể giúp suy ra context, nhưng completion cần xử lý trường hợp parser đang ở trạng thái lỗi.

### 15.3. Source ranges

Token start/stop index và line/column cần được chuyển sang LSP position encoding. Với Unicode, phải thống nhất đơn vị offset giữa ANTLR, AST và client editor.

### 15.4. Diagnostics

Không nên gửi trực tiếp lỗi raw của ANTLR nếu cần message ổn định và thân thiện. Language server có thể ánh xạ lỗi sang:
- Error code riêng.
- Severity.
- Range.
- Message đã chuẩn hóa.
- Related information.
- Quick fix nếu có thể xác định an toàn.

## 16. Testing grammar và parser

Grammar là một phần của ngôn ngữ công khai; thay đổi grammar có thể làm source cũ không parse được hoặc đổi cấu trúc parse.

### 16.1. Positive tests

Mỗi parser rule cần ví dụ hợp lệ:
- Program rỗng nếu được phép.
- Một declaration.
- Nhiều declaration.
- Expression lồng nhau.
- Block lồng nhau.
- String/number literal.
- Comment và whitespace.
- Tất cả alternative.

### 16.2. Negative tests

Kiểm tra:
- Thiếu token bắt buộc.
- Dấu ngoặc không cân bằng.
- String chưa đóng.
- Token không hợp lệ.
- Sai thứ tự keyword.
- EOF giữa construct.
- Token thừa sau root rule.

Xác nhận parser phát diagnostic đúng vị trí và recovery không làm ứng dụng crash.

### 16.3. Parse tree shape tests

Hai input hợp lệ có thể parse thành cây khác mong muốn nếu precedence hoặc alternative ordering sai. Test nên xác nhận:
- Loại context.
- Số lượng child.
- Quan hệ parent-child.
- Operator binding.
- Alternative labels.

### 16.4. AST tests

Kiểm tra AST builder:
- Node type đúng.
- Literal value đúng.
- Source span đúng.
- Child order đúng.
- Identifier binding chưa bị gán nhầm.
- Comment/trivia được giữ ở nơi cần.

### 16.5. Regression tests

Mỗi bug grammar cần trở thành test cố định. Khi thay đổi rule, chạy lại toàn bộ corpus source mẫu để phát hiện breaking changes.

### 16.6. Fuzz testing

Sinh input ngẫu nhiên hoặc mutation từ source hợp lệ để kiểm tra:
- Lexer/parser không crash.
- Không lặp vô hạn.
- Không tiêu thụ bộ nhớ bất thường.
- Error recovery kết thúc.
- Source range luôn hợp lệ.
- Kết quả ổn định với cùng input và version.

## 17. Performance và grammar design

ANTLR dùng cơ chế dự đoán parsing dựa trên grammar và lookahead. Grammar có thể parse đúng nhưng chậm nếu nhiều decision khó hoặc pattern gây nhiều lookahead.

Các điểm cần chú ý:
- Tránh lexer rules chồng lấn không cần thiết.
- Giảm ambiguity.
- Factoring common prefix khi giúp grammar rõ và hiệu quả.
- Tránh parser rules quá rộng có nhiều alternative khó phân biệt.
- Dùng token channels phù hợp thay vì xử lý trivia thủ công không cần thiết.
- Không tạo parse tree nếu chỉ cần tokenize, nếu API cho phép phù hợp.
- Tránh semantic predicates quá đắt.
- Đo thời gian lexer và parser riêng.
- Đo memory trên source lớn.
- Kiểm tra worst-case input.

### 17.1. SLL và LL prediction

ANTLR 4 sử dụng chiến lược prediction có thể dùng SLL và LL tùy cấu hình và tình huống. SLL thường nhanh hơn nhưng có thể cần fallback sang LL khi không đủ thông tin. Cần hiểu đúng version và API trước khi thay đổi prediction mode.

Không nên bật chế độ nhanh rồi bỏ qua lỗi hoặc ambiguity mà chưa có test chứng minh kết quả đúng.

### 17.2. Parse tree memory

Parse tree có thể lớn với input dài. Nếu ứng dụng cần AST nhỏ để thực thi, có thể cân nhắc bỏ bớt dữ liệu trung gian sau khi AST được tạo, hoặc dùng listener/visitor để thu thập model trong một lượt phù hợp.

Tuy nhiên, editor có thể cần parse tree và token stream cho navigation, completion, formatting và diagnostics. Quyết định giữ hay giải phóng phụ thuộc use cases.

### 17.3. Lexer modes và performance

Nhiều mode không nhất thiết chậm, nhưng rule chồng lấn hoặc regex-like pattern phức tạp có thể làm lexing tốn kém. Đo bằng corpus thực tế và input xấu thay vì suy đoán từ số lượng rule.

## 18. Security khi parse DSL không tin cậy

Nếu người dùng có thể gửi source tùy ý, parser là một ranh giới xử lý input không tin cậy.

Các biện pháp:
- Giới hạn kích thước source.
- Giới hạn thời gian parse.
- Giới hạn số diagnostics.
- Tránh semantic action thực hiện side effect.
- Không thực thi code trong lúc parse.
- Giới hạn độ sâu hoặc số node theo khả năng của runtime.
- Kiểm soát stack và memory cho input lồng sâu.
- Không ghi raw source chứa secret vào log.
- Xử lý encoding và Unicode rõ ràng.
- Tách parse khỏi runtime execution và capability access.

### 18.1. Parser denial of service

Grammar hoặc input đặc biệt có thể tạo nhiều nhánh dự đoán, cây rất sâu hoặc lượng node lớn. Nên test worst-case và áp dụng timeout/resource budget phù hợp.

### 18.2. Semantic actions và trust boundary

Nếu grammar chứa action gọi host API hoặc thực hiện I/O, parsing một file không tin cậy có thể gây side effect trước khi chương trình được validate. Tốt hơn là parser chỉ nhận diện cấu trúc; side effect nên xảy ra trong execution phase có kiểm soát capability.

### 18.3. Error message safety

Token text do người dùng cung cấp có thể chứa control characters hoặc nội dung nhạy cảm. Khi đưa vào diagnostic hoặc log, cần escape và giới hạn độ dài.

## 19. Quản lý grammar như một artifact của ngôn ngữ

Grammar không chỉ là file triển khai; nó là một phần của specification DSL.

Nên quản lý:
- Version grammar.
- Version ANTLR tool và runtime.
- Target language.
- Lexer/parser package.
- Token vocabulary.
- Generated source policy.
- Corpus test.
- Compatibility notes.
- Migration khi syntax thay đổi.

### 19.1. Backward compatibility

Thêm syntax mới thường có thể tương thích, nhưng thay đổi keyword hoặc precedence có thể làm source cũ được parse theo cách khác.

Ví dụ một identifier trước đây hợp lệ có thể trở thành keyword. Khi thêm keyword, cần cân nhắc escaping hoặc reserved-word policy.

### 19.2. Grammar versioning

Nếu cần hỗ trợ source nhiều version, có thể:
- Có grammar riêng theo version.
- Có version directive trong source.
- Parse syntax chung rồi migration AST.
- Chọn parser theo project configuration.

Không nên âm thầm dùng grammar mới nếu semantics source cũ thay đổi.

### 19.3. Generated code policy

Có thể không commit generated source và sinh trong build, hoặc commit generated source nếu quy trình yêu cầu. Dù chọn cách nào, tool version phải được cố định và output phải tái tạo được.

### 19.4. Documentation

Mỗi parser rule quan trọng nên có ví dụ syntax và giải thích. Grammar comments, language reference và test corpus cần được cập nhật cùng nhau khi syntax thay đổi.

## 20. Những sai lầm thường gặp

1. **Coi ANTLR là toàn bộ DSL framework:** ANTLR tạo lexer/parser; semantic model và runtime vẫn cần thiết kế.
2. **Đưa mọi logic vào grammar:** làm grammar khó tái sử dụng và test.
3. **Không đặt EOF ở root rule:** có thể bỏ sót token thừa.
4. **Không phân biệt lexer và parser rules:** dẫn đến tokenization sai.
5. **Không quản lý keyword priority:** identifier bị nhận diện thành token không mong muốn.
6. **Bỏ comment bằng skip:** formatter và documentation tooling không còn dữ liệu.
7. **Nhầm parse tree với AST:** domain logic phụ thuộc quá sâu vào generated contexts.
8. **Không giữ source locations:** diagnostics không trỏ được về file.
9. **Không test precedence:** biểu thức được parse sai mà vẫn không báo lỗi.
10. **Sửa generated code:** thay đổi bị mất khi regenerate.
11. **Dùng tool/runtime khác version:** build hoặc runtime có thể không tương thích.
12. **Chỉ kiểm tra parser không crash:** không xác nhận tree shape và semantics.
13. **Thực thi side effect trong grammar action:** parse source không tin cậy trở thành nguy cơ.
14. **Không kiểm soát error recovery:** recovery tree bị dùng nhầm để thực thi.
15. **Không giới hạn resource:** source lớn hoặc lồng sâu gây quá tải.

## 21. Quy trình xây dựng DSL bằng ANTLR

Một quy trình triển khai thực tế:

1. **Định nghĩa syntax của DSL:** viết ví dụ source hợp lệ và không hợp lệ trước.
2. **Thiết kế token vocabulary:** keyword, identifier, literal, operator, delimiter và comment.
3. **Viết lexer rules:** xử lý longest match, escape, whitespace, channels và modes.
4. **Viết parser rules:** document root, declarations, statements, expressions và precedence.
5. **Sinh lexer/parser:** cố định ANTLR tool version và target language.
6. **Tích hợp build:** runtime dependency, generated source directory và package.
7. **Tạo parser diagnostics:** custom error listener và error strategy.
8. **Xây AST/domain model:** dùng visitor hoặc listener phù hợp.
9. **Thực hiện semantic analysis:** symbol resolution, type checking và cross-node validation.
10. **Tích hợp editor:** source ranges, LSP diagnostics, completion và navigation.
11. **Viết test:** grammar, parse tree, AST, errors, regression và fuzz.
12. **Đo performance:** lexer, parser, tree memory và worst-case input.
13. **Quản lý version:** grammar, tool, runtime và syntax compatibility.
14. **Kết nối execution:** interpreter, compiler hoặc model transformation sau khi validation thành công.

Bắt đầu từ một grammar nhỏ, test các construct cốt lõi rồi mở rộng theo nhu cầu của miền. Giữ syntax, semantics và runtime thành các lớp có trách nhiệm rõ ràng sẽ giúp DSL dễ bảo trì hơn.

## 22. Kết luận

ANTLR là parser generator hữu ích để xây dựng front-end cho DSL. Từ grammar, ANTLR sinh lexer và parser, tạo token stream và parse tree để ứng dụng tiếp tục xây AST, resolve symbol, kiểm tra kiểu và thực thi hoặc biên dịch chương trình.

Khai thác ANTLR hiệu quả đòi hỏi grammar được thiết kế rõ, tokenization chính xác, precedence có kiểm thử, diagnostics và recovery phù hợp, cùng cách quản lý generated code và tool/runtime version nhất quán. Khi tích hợp vào editor, cần giữ source positions, comment/trivia và document state; khi xử lý source không tin cậy, cần giới hạn tài nguyên và tránh side effect trong parsing. ANTLR cung cấp nền tảng cú pháp, còn chất lượng của DSL phụ thuộc cách toàn bộ toolchain sử dụng nền tảng đó.


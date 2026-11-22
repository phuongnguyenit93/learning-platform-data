# Tài liệu ngữ pháp

## 1. Tài liệu ngữ pháp trong DSL là gì?

Ngữ pháp (*grammar*) mô tả cấu trúc cú pháp mà một ngôn ngữ chấp nhận. Với DSL (*Domain-Specific Language*), grammar xác định cách viết declaration, expression, statement, type, block, literal, operator và các construct khác.

**Tài liệu ngữ pháp (*grammar documentation*)** là phần đặc tả và giải thích cú pháp của DSL để người viết, người triển khai parser, người xây tooling và người bảo trì ngôn ngữ hiểu cùng một quy tắc.

Một tài liệu ngữ pháp tốt trả lời được:
- Một chương trình DSL có cấu trúc tổng thể như thế nào?
- Token, keyword, identifier và literal được viết ra sao?
- Một construct có grammar production nào?
- Các phần tử là bắt buộc, tùy chọn hay lặp lại?
- Operator có precedence và associativity như thế nào?
- Whitespace, comment, escape và Unicode được xử lý ra sao?
- Cú pháp nào hợp lệ nhưng vẫn có thể sai về semantics?
- Parser báo lỗi ở đâu và người dùng nên sửa thế nào?
- Cú pháp đã thay đổi ra sao giữa các version?

Grammar documentation không chỉ là bản sao của file parser grammar. File grammar thường được tối ưu cho parser generator; tài liệu cần được tổ chức theo cách người dùng tìm được cú pháp họ cần, hiểu ví dụ và biết các giới hạn quan trọng.

## 2. Mục tiêu và đối tượng đọc

Tài liệu ngữ pháp thường phục vụ nhiều nhóm độc giả.

| Đối tượng | Điều họ cần |
|---|---|
| DSL author | Cách viết source hợp lệ |
| Người mới học | Khái niệm, ví dụ và cách đọc syntax notation |
| DSL implementer | Grammar rules, lexical conventions và semantics |
| Tooling developer | Source ranges, error behavior, parser recovery |
| Reviewer | Cách xác định thay đổi syntax có tương thích không |
| Maintainer | Rule ownership, versioning và test corpus |

Không nên cố gắng dùng một trang duy nhất để phục vụ mọi nhu cầu. Có thể chia tài liệu thành:
- Tutorial: hướng dẫn viết chương trình đầu tiên.
- Syntax guide: giải thích construct theo nhóm.
- Grammar reference: đặc tả cú pháp có cấu trúc.
- Semantic reference: ý nghĩa và ràng buộc của construct.
- Error guide: chẩn đoán lỗi và cách sửa.
- Migration guide: thay đổi giữa các version.

### 2.1. Grammar reference và tutorial

Tutorial dạy người dùng hoàn thành một mục tiêu, thường đi từ ví dụ đơn giản đến ứng dụng thực tế. Grammar reference trả lời câu hỏi tra cứu chính xác: một rule nhận dạng những dạng nào?

Tutorial có thể bỏ qua chi tiết ít gặp để giữ mạch học. Reference cần mô tả đầy đủ các alternative và edge cases thuộc phạm vi ngôn ngữ.

### 2.2. Grammar reference và language specification

Language specification thường rộng hơn grammar. Nó có thể gồm:
- Lexical syntax.
- Syntactic grammar.
- Name resolution.
- Type system.
- Evaluation semantics.
- Error behavior.
- Runtime model.
- Compatibility requirements.

Grammar documentation có thể là một phần của language specification hoặc là một sản phẩm tài liệu riêng được sinh từ specification.

## 3. Cấu trúc của một tài liệu ngữ pháp

Một reference dễ tra cứu thường được tổ chức theo các phần:

1. Giới thiệu ngôn ngữ và phạm vi grammar.
2. Quy ước đọc syntax notation.
3. Character set, encoding và lexical conventions.
4. Identifier, keyword, literal và comment.
5. Cấu trúc document/program.
6. Declarations và definitions.
7. Statements và blocks.
8. Types và type expressions.
9. Expressions và operators.
10. Collections, patterns và control constructs.
11. Imports, modules và namespaces.
12. Contextual/semantic constraints.
13. Examples hợp lệ và không hợp lệ.
14. Diagnostics và recovery.
15. Versioning và compatibility.

Không phải DSL nào cũng có tất cả phần trên. Mục lục nên phản ánh các construct thực sự có trong ngôn ngữ, không tạo mục trống chỉ để giống một template.

### 3.1. Overview trước reference chi tiết

Người đọc cần biết một file DSL bắt đầu từ đâu và những thành phần chính là gì trước khi đọc từng production.

Ví dụ cấu trúc tổng quát:

~~~text
program
    = importDeclaration*
      topLevelDeclaration*
      EOF
~~~

Sau đó reference có thể liên kết từng thành phần:
- importDeclaration.
- topLevelDeclaration.
- declaration.
- typeDeclaration.
- functionDeclaration.
- ruleDeclaration.

### 3.2. Tổ chức theo khái niệm người dùng

Nếu grammar có nhiều rule nội bộ, không nên bắt người dùng đọc theo thứ tự file parser. Hãy nhóm theo tác vụ: khai báo, biểu thức, luồng điều khiển, kiểu, module hoặc cấu hình.

Tên rule nội bộ có thể xuất hiện trong appendix hoặc generated reference, còn trang chính dùng tên khái niệm dễ hiểu.

## 4. Syntax notation và cách đọc grammar

Tài liệu cần công bố một notation nhất quán. Những notation phổ biến gồm EBNF, ABNF, PEG và grammar theo parser generator.

### 4.1. EBNF

EBNF (*Extended Backus–Naur Form*) là một họ notation dùng để mô tả production. Một quy ước thường gặp:

| Ký hiệu | Ý nghĩa |
|---|---|
| `A = B ;` | A được định nghĩa bởi B |
| `A B` | A theo sau B |
| `A \| B` | Chọn một trong các alternative |
| `[ A ]` | A tùy chọn |
| `{ A }` | A lặp 0 hoặc nhiều lần |
| `( A )` | Nhóm biểu thức |
| `"text"` | Literal terminal |
| `A` | Nonterminal hoặc rule reference |

Có nhiều biến thể EBNF. Tài liệu phải định nghĩa đúng biến thể đang dùng thay vì giả định mọi người đọc đều hiểu ký hiệu giống nhau.

### 4.2. ABNF

ABNF thường dùng trong đặc tả protocol. Nó có quy tắc về repetition, concatenation, alternative, numeric values và case-insensitive literal theo notation.

Nếu DSL dùng ABNF, cần chỉ rõ:
- Cách viết terminal.
- Quy tắc repetition.
- Case sensitivity.
- Character range.
- Rule definition và continuation.

Không nên trộn cú pháp ABNF với EBNF trong cùng một grammar mà không giải thích.

### 4.3. PEG

PEG (*Parsing Expression Grammar*) mô tả ordered choice. Trong PEG, alternative được thử theo thứ tự và lựa chọn đầu tiên match có ý nghĩa khác với cách hiểu OR không thứ tự trong một số notation CFG.

Các ký hiệu thường gặp trong PEG:
- Sequence.
- Ordered choice.
- Zero-or-more.
- One-or-more.
- Optional.
- Positive/negative lookahead.
- End of input.

Nếu grammar dùng PEG, tài liệu phải giải thích ordered choice vì đổi thứ tự alternative có thể đổi ngôn ngữ được nhận diện.

### 4.4. ANTLR-style grammar

Một tài liệu có thể trình bày parser rules và lexer rules theo cú pháp ANTLR:

~~~antlr
program
    : declaration* EOF
    ;

declaration
    : 'let' IDENTIFIER '=' expression ';'
    ;

IDENTIFIER
    : [a-zA-Z_] [a-zA-Z_0-9]*
    ;

WS
    : [ \t\r\n]+ -> skip
    ;
~~~

Cần phân biệt:
- Parser rule: kết hợp token thành cấu trúc.
- Lexer rule: nhận diện token từ ký tự.
- Fragment: rule hỗ trợ lexer, không tạo token độc lập.
- Channel: phân loại token như hidden/comment.
- Mode: thay đổi lexer vocabulary theo context.

### 4.5. Quy ước trình bày terminal và nonterminal

Có thể dùng:
- Chữ monospace cho terminal.
- Tên italic hoặc link cho nonterminal.
- Keyword viết nguyên văn.
- Placeholder trong dấu ngoặc nhọn.
- Ghi chú riêng cho whitespace và case sensitivity.

Ví dụ:

~~~text
assignment = identifier, "=", expression, ";" ;
~~~

Trong tài liệu, phải nói rõ `identifier` là nonterminal, còn `=` và `;` là terminal.

## 5. Lexical grammar và character model

Parser chỉ làm việc với token hoặc terminal theo mô hình của grammar. Tài liệu cần giải thích lexer nhận diện ký tự thành token như thế nào.

### 5.1. Character encoding

Cần nêu:
- Source encoding được hỗ trợ.
- Unicode version nếu có yêu cầu cụ thể.
- BOM được xử lý ra sao.
- Line ending LF/CRLF.
- Invalid byte sequence được báo lỗi thế nào.
- Column/offset được tính theo byte, code point hay UTF-16 code unit nếu tooling cần.

Đặc biệt với editor integration, đơn vị offset phải được mô tả hoặc được chuẩn hóa qua protocol adapter.

### 5.2. Whitespace

Cần xác định ký tự nào được coi là whitespace:
- Space.
- Tab.
- Carriage return.
- Line feed.
- Form feed nếu hỗ trợ.
- Unicode whitespace nếu hỗ trợ.

Có thể phân biệt whitespace được phép giữa token với newline có ý nghĩa cú pháp.

### 5.3. Newline significance

Một DSL có thể:
- Bỏ qua newline như whitespace.
- Dùng newline kết thúc statement.
- Dùng indentation để tạo block.
- Dùng semicolon làm terminator và cho phép newline tự do.

Tài liệu cần có ví dụ multiline và trường hợp newline không được phép.

### 5.4. Comments

Mô tả:
- Single-line comment.
- Block comment.
- Nested block comment có hỗ trợ không.
- Documentation comment.
- Comment có thể xuất hiện ở vị trí nào.
- Comment ảnh hưởng đến newline/statement boundary hay không.

Ví dụ:

~~~text
// line comment

/*
   block comment
*/

/// documentation comment
~~~

Nếu comment được giữ trong hidden channel để formatter hoặc documentation tooling dùng, có thể nói rõ đây là chi tiết tooling; không cần biến nó thành cú pháp người dùng phải quan tâm nếu không ảnh hưởng semantics.

### 5.5. Identifier

Một identifier reference nên mô tả:
- Ký tự bắt đầu.
- Ký tự tiếp theo.
- Case sensitivity.
- Unicode identifier policy.
- Reserved words.
- Escaped identifiers nếu có.
- Quy tắc normalization.

Ví dụ grammar:

~~~text
identifier = identifierStart, { identifierContinue } ;
identifierStart = letter | "_" ;
identifierContinue = letter | digit | "_" ;
~~~

Đây chỉ là ví dụ ASCII đơn giản. Nếu DSL hỗ trợ Unicode identifier, cần mô tả chính xác profile ký tự được chấp nhận.

### 5.6. Keywords và reserved words

Tài liệu nên liệt kê keyword:
- Reserved trong mọi context.
- Contextual keyword chỉ có ý nghĩa ở vị trí nhất định.
- Keyword có thể được dùng làm identifier khi escape.
- Keyword mới được thêm giữa các version.

Khi thêm keyword, một identifier cũ có thể trở thành cú pháp đặc biệt. Đây là thay đổi có thể gây breaking change.

### 5.7. String literals

Mô tả:
- Quote style.
- Escape sequences.
- Unicode escapes.
- Multiline strings.
- Raw strings.
- Interpolation.
- Termination rules.
- Invalid escape behavior.

Ví dụ:

~~~text
"hello\nworld"
"Unicode: \u{1F600}"
~~~

Nếu interpolation được hỗ trợ, cần phân biệt phần literal text với expression được evaluate.

### 5.8. Numeric literals

Cần mô tả:
- Integer bases: decimal, hexadecimal, binary, octal nếu có.
- Decimal fractions.
- Exponent notation.
- Digit separators.
- Suffix cho type hoặc unit.
- Sign được coi là unary operator hay một phần literal.
- Overflow behavior.

Ví dụ:

~~~text
42
0x2A
3.1415
6.02e23
1_000_000
~~~

Không nên để ví dụ ngầm định một kiểu dữ liệu nếu type inference hoặc suffix semantics chưa được giải thích.

### 5.9. Boolean, null và special literals

Liệt kê literal như true, false, null, none hoặc undefined nếu DSL có. Phân biệt literal syntax với identifier có tên tương tự.

### 5.10. Operators và punctuation

Nên có bảng đầy đủ:
- Arithmetic operators.
- Comparison operators.
- Logical operators.
- Assignment operators.
- Member access.
- Range operators.
- Delimiters.
- Separators.
- Arrow hoặc pipeline operators.

Nếu cùng ký hiệu được dùng trong nhiều context, cần giải thích cách parser xác định nghĩa.

## 6. Syntactic grammar và cấu trúc chương trình

Sau lexical conventions, reference mô tả cách token kết hợp thành declaration và expression.

### 6.1. Root production

Root production xác định cấu trúc toàn file:

~~~text
program
    = importDeclaration*,
      declaration*,
      EOF ;
~~~

EOF là điểm kết thúc input. Nếu grammar chấp nhận prefix mà không yêu cầu EOF, token thừa có thể bị bỏ qua ngoài ý muốn.

### 6.2. Declaration

Declaration thường đặt tên hoặc định nghĩa một thành phần:

~~~text
declaration
    = variableDeclaration
    | functionDeclaration
    | typeDeclaration
    | ruleDeclaration ;
~~~

Mỗi declaration cần mô tả:
- Tên.
- Visibility.
- Modifiers.
- Generic parameters nếu có.
- Body.
- Scope.
- Duplicate-name behavior.

### 6.3. Statement và block

Statement biểu diễn một đơn vị thực thi. Block nhóm nhiều statement:

~~~text
block
    = "{", statement*, "}" ;
~~~

Nếu DSL dùng indentation, grammar và ví dụ phải chỉ rõ mức indent, tab handling và empty block.

### 6.4. Expression

Expression tạo ra giá trị hoặc tham chiếu. Có thể gồm:
- Literal.
- Identifier.
- Function call.
- Member access.
- Unary expression.
- Binary expression.
- Conditional expression.
- Collection literal.
- Lambda hoặc query expression.

### 6.5. Type grammar

Nếu DSL có static typing, cần mô tả:
- Primitive type.
- Named type.
- Generic type.
- Optional/nullable type.
- Union/intersection.
- Function type.
- Tuple/record type.
- Array/map type.
- Type reference.

Ví dụ:

~~~text
type
    = primitiveType
    | qualifiedName
    | type "[" typeArguments "]"
    | type "?" ;
~~~

Đây là grammar minh họa; semantics của generic và nullable cần được mô tả riêng.

### 6.6. Import và qualified names

Mô tả:
- Import path.
- Alias.
- Selective import.
- Wildcard import.
- Namespace qualification.
- Visibility.
- Circular import behavior.

Ví dụ:

~~~text
import billing.rules as billing
import common.{Money, Currency}
~~~

Nếu import path được resolve theo filesystem, package registry hoặc URI, cần giải thích resolution order.

## 7. Precedence và associativity của expression

Grammar expression là phần dễ bị hiểu sai nếu chỉ liệt kê alternative mà không mô tả binding rules.

### 7.1. Precedence

Precedence xác định operator nào được nhóm trước.

Ví dụ:

~~~text
a + b * c
~~~

Nếu multiplication có precedence cao hơn addition, expression tương đương:

~~~text
a + (b * c)
~~~

### 7.2. Associativity

Associativity xác định cách nhóm các operator cùng precedence.

Ví dụ left-associative subtraction:

~~~text
a - b - c
~~~

được nhóm thành:

~~~text
(a - b) - c
~~~

Nếu power operator right-associative, có thể được nhóm:

~~~text
a ^ (b ^ c)
~~~

### 7.3. Precedence table

Reference nên có bảng rõ ràng. Ví dụ minh họa:

| Mức | Operator | Associativity |
|---:|---|---|
| 1 | Member access, call | Left |
| 2 | Unary `!`, `-`, `+` | Right |
| 3 | `*`, `/`, `%` | Left |
| 4 | `+`, `-` | Left |
| 5 | `<`, `<=`, `>`, `>=` | Non-associative |
| 6 | `==`, `!=` | Non-associative |
| 7 | `and` | Left |
| 8 | `or` | Left |
| 9 | `?:` | Right |
| 10 | Assignment | Right |

Bảng thực tế phải khớp parser implementation và language specification. Không nên dùng bảng generic rồi để parser có precedence khác.

### 7.4. Non-associative operators

Một số DSL không cho phép chain comparison như `a < b < c` vì có thể gây hiểu nhầm. Nếu vậy, grammar hoặc semantic validation cần từ chối và tài liệu nên đưa ví dụ thay thế.

### 7.5. Parentheses

Parentheses cho phép nhóm expression tường minh. Cần nói rõ chúng có thể thay đổi precedence hay chỉ nhóm biểu thức; thường cả hai trong expression grammar.

### 7.6. Short-circuit evaluation

Short-circuit là semantics của evaluation, không chỉ grammar. Ví dụ `false and expensive()` có thể không gọi expensive(). Tài liệu cần mô tả nếu ngôn ngữ bảo đảm behavior này.

## 8. Grammar cho construct đặc thù của DSL

Một DSL có thể thêm construct phục vụ miền riêng.

### 8.1. Configuration declarations

~~~text
setting "http.timeout" : Duration = 5s
~~~

Tài liệu cần mô tả key syntax, value type, scope, override và defaulting rules nếu thuộc ngôn ngữ.

### 8.2. Rules

~~~text
rule "high-value-order" {
    when order.total > 1000
    then order.reviewRequired = true
}
~~~

Cần mô tả cấu trúc when/then, nhiều action, priority và rule metadata nếu grammar hỗ trợ.

### 8.3. Workflow

~~~text
process "OrderFlow" {
    start
    task "Validate"
    decision "Approved?"
    end
}
~~~

Cần giải thích node kinds, edge declarations, guard expressions, nested process và loop syntax.

### 8.4. Query language

~~~text
from orders
where status == "OPEN"
select id, total
order by createdAt desc
limit 100
~~~

Tài liệu cần phân biệt query clause order, identifier resolution, aggregation và pagination.

### 8.5. Template/interpolation

~~~text
message = "Hello, ${customer.name}"
~~~

Nếu DSL có template, cần giải thích escaping interpolation marker, nested expression và output encoding.

### 8.6. Embedded language

Một DSL có thể nhúng SQL, regex, expression hoặc script. Cần nêu:
- Boundary giữa host DSL và embedded language.
- Lexer mode hoặc delimiter.
- Escape rules.
- Parser/runtime được dùng.
- Error source mapping.
- Security restrictions.

## 9. Grammar và semantic constraints

Grammar xác định cấu trúc cú pháp. Một số quy tắc chỉ có thể kiểm tra sau parsing.

Ví dụ:

~~~text
let total: Money = "hello"
~~~

Cú pháp có thể hợp lệ nhưng kiểu String không gán được cho Money.

Cần phân biệt:

| Loại quy tắc | Giai đoạn thường kiểm tra | Ví dụ |
|---|---|---|
| Lexical | Lexer | Ký tự không hợp lệ |
| Syntactic | Parser | Thiếu dấu `;` |
| Name resolution | Semantic analysis | Identifier chưa khai báo |
| Type checking | Semantic analysis | Sai kiểu gán |
| Domain validation | Semantic/runtime | Amount âm không được phép |
| Authorization | Runtime | Principal không có quyền |
| Execution constraint | Runtime | Vượt loop budget |

### 9.1. Context-sensitive constraints

Một số cú pháp phụ thuộc context:
- Keyword chỉ có ý nghĩa trong một block.
- Type name phải được khai báo trước hoặc được resolve theo scope.
- Một modifier chỉ hợp lệ với một declaration kind.
- Một branch phải có target tồn tại.

Nếu grammar không thể biểu đạt trực tiếp, tài liệu phải chỉ rõ constraint được kiểm tra ở semantic phase.

### 9.2. Static semantics

Static semantics bao gồm các quy tắc kiểm tra được trước execution như name binding, type compatibility, duplicate declaration và control-flow constraints.

Tài liệu ngữ pháp nên liên kết từ production đến các semantic rules liên quan thay vì nhồi mọi quy tắc vào syntax notation.

### 9.3. Dynamic semantics

Dynamic semantics mô tả cách construct hoạt động khi chạy:
- Evaluation order.
- Side effects.
- Error propagation.
- State transitions.
- Transaction behavior.
- Concurrency.
- Resource limits.

Grammar reference có thể dẫn sang semantics reference cho các chi tiết này.

## 10. Viết một grammar production dễ tra cứu

Mỗi production quan trọng nên có một mục riêng.

Một mẫu trình bày:

### `functionDeclaration`

**Mục đích:** Khai báo một function có tên, tham số và body.

**Syntax:**

~~~text
functionDeclaration
    = "function", identifier,
      "(", parameterList?, ")",
      returnType?,
      block ;
~~~

**Thành phần:**

| Thành phần | Bắt buộc | Mô tả |
|---|---|---|
| `function` | Có | Keyword mở đầu |
| identifier | Có | Tên function |
| parameterList | Không | Danh sách tham số |
| returnType | Không | Kiểu trả về |
| block | Có | Body function |

**Ví dụ hợp lệ:**

~~~text
function add(a: Integer, b: Integer): Integer {
    return a + b
}
~~~

**Ví dụ không hợp lệ:**

~~~text
function add(a: Integer,): Integer {
    return a + b
}
~~~

Nếu trailing comma không được hỗ trợ, cần giải thích parser sẽ báo lỗi tại vị trí nào hoặc rule nào không match.

**Semantic notes:**
- Function name phải duy nhất trong scope theo quy tắc overload.
- Return expression phải tương thích với return type.
- Function body tuân theo scope rules.

Một mục như vậy giúp người dùng thấy syntax, ý nghĩa từng thành phần, ví dụ và các ràng buộc liên quan ở cùng một nơi.

## 11. Syntax diagrams

Syntax diagram (railroad diagram) biểu diễn grammar bằng hình ảnh.

Một diagram đơn giản cho assignment:

~~~text
identifier ---- "=" ---- expression ---- ";"
~~~

Diagram phức tạp hơn có thể dùng nhánh để thể hiện optional và repeated constructs.

### 11.1. Khi nào dùng diagram?

Syntax diagram hữu ích khi:
- Grammar có nhiều lựa chọn.
- Optional/repetition khó đọc trong EBNF.
- Người học chưa quen notation hình thức.
- Có nhiều tầng expression.
- Cần overview một construct.

### 11.2. Diagram không thay thế production

Hình vẽ có thể khó diff, khó search và khó trích dẫn. Nên giữ grammar text làm source of truth, diagram là representation được sinh hoặc kiểm chứng từ cùng model.

### 11.3. Accessibility

Cần có text alternative hoặc production tương ứng cho syntax diagram. Không nên để grammar chỉ tồn tại dưới dạng hình ảnh.

### 11.4. Diagram generation

Nếu tự động sinh diagram, cần xác định:
- Input notation.
- Cách render terminal/nonterminal.
- Cách thể hiện repetition và optional.
- Link tới rule reference.
- Version của generator.
- Cách test diagram đồng bộ với grammar.

## 12. Examples trong grammar documentation

Ví dụ giúp chuyển notation hình thức thành cách viết thực tế.

### 12.1. Minimal valid example

Mỗi construct nên có ví dụ nhỏ nhất hợp lệ để người đọc biết phần nào bắt buộc.

### 12.2. Complete example

Một ví dụ đầy đủ cho thấy construct kết hợp với declaration, type, expression và scope như thế nào.

### 12.3. Boundary examples

Cần có ví dụ cho:
- Empty collection.
- Một phần tử và nhiều phần tử.
- Missing optional field.
- Nested block.
- Unicode identifier nếu hỗ trợ.
- Escape sequence.
- Maximum/minimum literal.
- Comment và newline boundary.

### 12.4. Negative examples

Ví dụ không hợp lệ giúp giải thích ranh giới grammar. Cần nêu lý do lỗi, không chỉ gắn dấu X.

~~~text
// Invalid: missing expression after "="
let total =
~~~

### 12.5. Examples phải chạy được

Nếu ví dụ được tuyên bố là executable, nên parse/validate bằng đúng compiler version. Nếu là pseudocode hoặc syntax minh họa, cần ghi rõ để người đọc không copy nhầm vào project.

### 12.6. Một ví dụ, một ý chính

Không nên nhồi quá nhiều construct vào một ví dụ nhỏ. Mỗi example nên giúp hiểu một rule hoặc một tương tác cụ thể.

## 13. Error diagnostics trong tài liệu ngữ pháp

Grammar documentation nên giải thích những lỗi cú pháp thường gặp và cách đọc parser diagnostics.

### 13.1. Expected token

Parser có thể báo rằng tại một vị trí nó mong đợi một trong các token. Ví dụ sau keyword `let` có thể cần identifier.

Tài liệu nên giải thích token name theo ngôn ngữ người dùng, không buộc họ hiểu tên class hoặc token enum nội bộ.

### 13.2. Missing và extraneous input

Phân biệt:
- Missing token: parser mong một token nhưng không thấy.
- Extraneous token: có token không hợp lệ ở vị trí đó.
- Mismatched token: token hiện tại không khớp cấu trúc mong đợi.
- No viable alternative: không có alternative grammar phù hợp.

### 13.3. Lexer errors

Lexer error có thể do:
- Ký tự không hợp lệ.
- String chưa đóng.
- Escape sequence không hỗ trợ.
- Comment chưa kết thúc.
- Number literal sai format.

### 13.4. Source ranges

Diagnostic nên chỉ rõ:
- File/URI.
- Line và column.
- Range bắt đầu/kết thúc.
- Offending token.
- Expected construct.
- Error code.
- Related location nếu cần.

Cần thống nhất offset encoding giữa parser, AST, editor và language server.

### 13.5. Error recovery

Một parser có thể tiếp tục sau lỗi để hiển thị nhiều diagnostics trong editor. Tài liệu cần nói rõ cây sau recovery không phải lúc nào cũng là chương trình hợp lệ để execute.

### 13.6. Quick fixes

Nếu có thể suy ra an toàn, tooling có thể gợi ý:
- Thêm dấu ngoặc.
- Thêm separator.
- Đổi keyword.
- Đóng string.
- Thêm branch.
- Chỉnh tên identifier.

Quick fix cần giữ semantics và không tự sửa mơ hồ.

## 14. Quy ước naming và cross-reference

Grammar reference thường có nhiều production liên kết với nhau. Naming và linking tốt giúp điều hướng.

### 14.1. Rule names

Nên dùng tên mô tả vai trò cú pháp:
- `expression`.
- `parameterList`.
- `typeReference`.
- `workflowDeclaration`.

Tránh tên mơ hồ như `part1`, `thing`, `otherRule`.

### 14.2. Stable anchors

Mỗi rule cần anchor ổn định để link từ tutorial, error guide và migration guide. Đổi tên anchor không cần thiết có thể làm link cũ hỏng.

### 14.3. Cross-reference

Một mục có thể liên kết:
- Tới rule được tham chiếu.
- Tới operator precedence.
- Tới semantic constraint.
- Tới example.
- Tới error code.
- Tới migration note.

### 14.4. Glossary

Nên định nghĩa thuật ngữ như terminal, nonterminal, token, production, alternative, nullable, precedence, associativity và lookahead.

### 14.5. Searchability

Tài liệu nên có index theo:
- Keyword.
- Operator.
- Rule name.
- Terminal strings.
- Error code.
- Construct name.
- Type name.

Người dùng thường tìm cú pháp bằng keyword hoặc ví dụ họ đang viết.

## 15. Grammar modules và modular documentation

Grammar lớn có thể được chia thành module hoặc file:
- Core syntax.
- Expression syntax.
- Type syntax.
- Workflow syntax.
- Query syntax.
- Extension syntax.

### 15.1. Shared lexical rules

Các module có thể dùng chung identifier, string, number và comment rules. Tài liệu cần chỉ ra nơi định nghĩa chung và nơi module-specific syntax được bổ sung.

### 15.2. Importing grammar fragments

Nếu grammar hỗ trợ grammar import hoặc token vocabulary reuse, cần mô tả dependency và cách build. Không nên để người đọc tưởng một file grammar riêng có thể parse độc lập nếu nó phụ thuộc token vocabulary khác.

### 15.3. Extension points

Nếu người dùng có thể mở rộng keyword, operator hoặc declaration kind, cần nói rõ:
- Extension được đăng ký ở đâu.
- Có conflict với keyword hiện tại không.
- Ordering/precedence.
- Version compatibility.
- Security boundary.
- Tooling support.

### 15.4. Grammar ownership

Một module cần owner hoặc maintainer rõ để biết ai chịu trách nhiệm khi syntax thay đổi. Ownership đặc biệt quan trọng khi nhiều team cùng phát triển DSL.

## 16. Versioning và backward compatibility

Grammar là một phần của public language contract. Thay đổi grammar có thể làm source cũ không parse được hoặc đổi cách diễn giải.

### 16.1. Language version

Có thể chỉ định version trong project metadata hoặc source:

~~~text
languageVersion: "2"
~~~

Compiler dùng version đó để chọn grammar/semantics tương ứng hoặc áp dụng migration.

### 16.2. Thêm keyword

Một identifier trước đây hợp lệ có thể trở thành reserved keyword. Đây có thể là breaking change ngay cả khi không xóa production nào.

### 16.3. Thay precedence

Đổi precedence có thể khiến cùng source tạo AST khác. Đây là semantic breaking change dù parser vẫn chấp nhận input.

### 16.4. Tightening grammar

Một version mới có thể từ chối syntax cũ từng được parser chấp nhận. Cần ghi rõ deprecation period và migration path.

### 16.5. Deprecation

Construct deprecated nên có:
- Version được đánh dấu deprecated.
- Replacement syntax.
- Warning code.
- Version dự kiến loại bỏ.
- Migration example.

### 16.6. Compatibility matrix

Tài liệu có thể cung cấp bảng:

| Language version | Compiler versions | Status |
|---|---|---|
| 1.x | 1.0–1.9 | Maintenance |
| 2.x | 2.0 trở lên | Current |

Bảng thực tế cần phản ánh support policy của dự án.

### 16.7. Changelog theo grammar

Mỗi thay đổi nên ghi:
- Rule hoặc construct bị ảnh hưởng.
- Syntax trước/sau.
- Breaking hay compatible.
- AST/semantic impact.
- Diagnostic thay đổi.
- Migration steps.

## 17. Sinh tài liệu từ grammar source

Để giảm drift, có thể sinh một phần reference từ grammar source hoặc một language metamodel.

Pipeline khái niệm:

~~~text
Grammar source
     |
     v
Grammar parser / metadata extractor
     |
     v
Normalized grammar model
     |
     +----> Rule reference
     +----> Syntax diagrams
     +----> Keyword index
     +----> Rule cross-reference
     |
     v
Documentation site
~~~

### 17.1. Generated và authored content

Generated content phù hợp với:
- Production text.
- Rule names.
- Terminal lists.
- Alternative labels.
- Cross-reference skeleton.
- Syntax diagrams.

Authored content vẫn cần cho:
- Mục đích và rationale.
- Semantics.
- Ví dụ thực tế.
- Common mistakes.
- Migration notes.
- Security implications.

Không nên kỳ vọng parser grammar tự sinh ra giải thích nghiệp vụ đầy đủ.

### 17.2. Grammar annotations

Có thể gắn metadata vào grammar hoặc một file sidecar:
- Display name.
- Description.
- Example.
- Category.
- Visibility.
- Link.
- Since/deprecated version.

Metadata cần được validate để không tham chiếu rule không tồn tại.

### 17.3. Avoid editing generated output

Generated reference không nên được sửa trực tiếp nếu lần build tiếp theo sẽ ghi đè. Nội dung biên tập nên nằm trong source docs hoặc metadata được quản lý.

### 17.4. Reproducible generation

Cần cố định:
- Grammar version.
- Documentation generator version.
- Parser tool version.
- Locale.
- Output format.
- Build options.

Cùng source và toolchain nên tạo tài liệu tương đương để diff dễ review.

## 18. Documentation tests và grammar conformance

Tài liệu grammar cần được kiểm tra như code vì ví dụ hoặc production sai có thể khiến người dùng viết source không chạy.

### 18.1. Example parsing

Có thể trích code block được đánh dấu executable và parse bằng compiler tương ứng. Build thất bại nếu example không còn hợp lệ.

### 18.2. Production coverage

Có thể theo dõi rule nào có:
- Mô tả.
- Ví dụ.
- Semantic notes.
- Link tới related rules.

Không phải mọi internal rule cần trang riêng, nhưng mọi construct public cần được giải thích.

### 18.3. Grammar corpus

Duy trì corpus:
- Valid programs.
- Invalid programs.
- Edge cases.
- Regression cases.
- Version-specific examples.

Corpus vừa kiểm tra parser vừa giúp tài liệu luôn có ví dụ thực tế.

### 18.4. Snapshot tests

Có thể snapshot generated grammar reference hoặc syntax diagrams. Khi output đổi, reviewer cần xác định thay đổi do grammar hay generator.

### 18.5. Link checks

Kiểm tra cross-reference, anchor và external links để tránh trang reference có liên kết hỏng.

### 18.6. Version consistency

Ví dụ cần ghi language version nếu syntax chỉ hợp lệ từ một version nhất định. Không dùng parser mới nhất để validate mọi ví dụ lịch sử mà không xét version.

## 19. Tổ chức website và trải nghiệm tra cứu

Một grammar reference nên dễ tìm và dễ đọc trên desktop, mobile và trong IDE.

### 19.1. Navigation

Có thể tổ chức:
- Getting started.
- Language concepts.
- Syntax reference.
- Types and expressions.
- Statements and declarations.
- Diagnostics.
- Version history.

### 19.2. Syntax highlighting

Code block nên có highlighting đúng DSL. Nếu chưa có grammar cho syntax highlighter, có thể dùng plain text thay vì highlight sai khiến người đọc hiểu nhầm token.

### 19.3. Copyable examples

Ví dụ cần copy được, không chèn line number hoặc annotation vào phần code thực thi. Nếu có placeholder, ghi rõ cần thay bằng giá trị thật.

### 19.4. Responsive tables

Precedence table và grammar table cần đọc được trên màn hình nhỏ. Tránh bảng quá rộng nếu có thể tách thành các nhóm.

### 19.5. Search

Search nên index cả:
- Keyword.
- Rule names.
- Terminal strings.
- Operator symbols.
- Error codes.
- Example source.

Symbol search cần hỗ trợ các ký tự như `=>` hoặc `??`, không chỉ text words.

### 19.6. Accessibility

Dùng heading hierarchy đúng, link có tên rõ, bảng có header và syntax diagrams có text equivalent. Không chỉ dùng màu để phân biệt terminal/nonterminal.

## 20. Localization và thuật ngữ

DSL có thể có syntax cố định bằng tiếng Anh trong khi tài liệu được dịch sang nhiều ngôn ngữ.

Cần phân biệt:
- Keyword trong source: không dịch.
- Rule name nội bộ: thường giữ nguyên.
- Mô tả: có thể dịch.
- Diagnostic code: ổn định, không dịch.
- Diagnostic message: có thể localization.
- Example literal: tùy nội dung và locale.

Một glossary thống nhất giúp các bản dịch dùng cùng thuật ngữ cho parser, token, production, expression và declaration.

### 20.1. Locale-dependent examples

Date, number và decimal separator trong source cần theo grammar, không theo locale của người đọc nếu DSL định nghĩa format cố định.

### 20.2. Unicode và display

Một số Unicode characters nhìn giống nhau nhưng code point khác. Tài liệu cần giải thích identifier normalization hoặc cảnh báo confusable characters nếu ngôn ngữ hỗ trợ Unicode identifiers.

## 21. Security và an toàn khi mô tả cú pháp

Tài liệu ngữ pháp có thể vô tình khuyến khích cách dùng không an toàn nếu không nói rõ giới hạn.

Nên ghi chú:
- Embedded expressions có được phép truy cập filesystem/network không.
- String interpolation có escape output không.
- Regex có giới hạn không.
- Query syntax có parameterization không.
- Include/import có thể truy cập path nào.
- Macro hoặc plugin có thể chạy code không.
- Resource limits và execution permissions.
- Cách xử lý secret trong examples.

Không nên đưa credential thật hoặc dữ liệu production vào sample source.

## 22. Những sai lầm thường gặp

1. **Chỉ publish file grammar thô:** người dùng không hiểu notation hoặc cấu trúc tổng thể.
2. **Không định nghĩa EBNF variant:** ký hiệu optional/repetition bị hiểu khác nhau.
3. **Trộn lexical và parser rules:** người đọc không biết token được tạo như thế nào.
4. **Không liệt kê keyword:** identifier cũ bất ngờ trở thành reserved word.
5. **Bỏ qua whitespace/comment rules:** ví dụ multiline hoạt động khác kỳ vọng.
6. **Không công bố precedence:** expression được nhóm sai.
7. **Nhầm syntax với semantics:** source parse được bị coi là hợp lệ hoàn toàn.
8. **Thiếu negative examples:** người học không hiểu ranh giới cú pháp.
9. **Ví dụ không được parse:** tài liệu lỗi thời.
10. **Sửa generated docs trực tiếp:** nội dung mất khi regenerate.
11. **Không version grammar:** không thể giải thích source cũ.
12. **Anchor không ổn định:** link tới rule bị hỏng sau đổi tên.
13. **Chỉ có syntax diagrams:** không thể search hoặc diff production dễ dàng.
14. **Không có source mapping cho errors:** người dùng khó tìm vị trí sai.
15. **Không mô tả contextual keywords:** parser behavior gây bất ngờ.
16. **Không ghi construct deprecated:** người dùng không có lộ trình migration.
17. **Dùng locale trong syntax examples:** source không portable.
18. **Không phân biệt parser recovery với valid program:** cây phục hồi bị dùng nhầm để execute.

## 23. Quy trình xây dựng và duy trì tài liệu ngữ pháp

Một quy trình thực tế:

1. **Xác định language version và audience:** biết tài liệu phục vụ author, implementer hay cả hai.
2. **Chọn notation chính thức:** EBNF, ABNF, PEG hoặc grammar theo parser tool; ghi rõ quy ước.
3. **Lập inventory public constructs:** declaration, statement, expression, type, literal, operator và module.
4. **Tách lexical và syntactic rules:** mô tả character set, token, keyword, comment và production.
5. **Ghi precedence/associativity:** tạo bảng có thứ tự chính xác.
6. **Liên kết semantics:** chỉ ra ranh giới giữa syntax, name resolution, type checking và runtime.
7. **Viết mục reference theo mẫu:** purpose, syntax, components, examples, constraints và related rules.
8. **Bổ sung positive/negative examples:** có boundary và version annotation.
9. **Tạo syntax diagrams nếu hữu ích:** sinh từ cùng grammar model và có text alternative.
10. **Tổ chức navigation/search:** anchors ổn định, keyword index và glossary.
11. **Sinh phần có thể tự động hóa:** production, rule list, diagrams và cross-references.
12. **Validate examples:** parse bằng đúng language/compiler version.
13. **Kiểm tra links và version consistency:** bảo đảm docs không trỏ sai rule.
14. **Review grammar changes:** ghi breaking changes, deprecation và migration.
15. **Publish cùng release:** gắn tài liệu với grammar/compiler version.
16. **Theo dõi feedback:** bổ sung ví dụ và giải thích nơi người dùng thường mắc lỗi.

## 24. Kết luận

Tài liệu ngữ pháp là reference chính thức giúp người dùng hiểu cách viết DSL và giúp implementer duy trì parser nhất quán. Nó cần mô tả lexical conventions, syntax productions, precedence, associativity, construct đặc thù và ranh giới giữa cú pháp với semantics. Một notation như EBNF, ABNF, PEG hoặc ANTLR grammar phải được giải thích rõ trước khi người đọc sử dụng.

Tài liệu có giá trị khi mỗi construct có mô tả, ví dụ hợp lệ/không hợp lệ, semantic notes và liên kết đến các rule liên quan. Có thể tự động sinh production, syntax diagrams và index từ grammar source, nhưng phần giải thích và hướng dẫn vẫn cần biên tập. Kiểm tra examples bằng parser, quản lý language version, giữ anchor ổn định và ghi migration khi syntax thay đổi giúp tài liệu luôn đồng bộ với ngôn ngữ thực tế.


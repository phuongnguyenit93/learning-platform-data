# Token được mong đợi

Khi parser đọc một chương trình DSL, nó liên tục kiểm tra token hiện tại có phù hợp với cấu trúc ngữ pháp đang được phân tích hay không. Nếu grammar yêu cầu một token nhưng đầu vào cung cấp token khác, parser cần giải thích rõ điều nó đang chờ. Thông tin đó được gọi là **token được mong đợi (expected token)**.

Chẩn đoán “token được mong đợi” là một phần quan trọng của trải nghiệm sử dụng DSL. Thay vì chỉ nói “lỗi cú pháp”, parser có thể cho biết nó đang cần dấu `)`, dấu `}`, từ khóa `then`, dấu `:` hoặc một biểu thức, trong khi thực tế lại gặp token nào. Thông báo tốt còn chỉ ra vị trí, ngữ cảnh và cách sửa có khả năng đúng.

## 1. Token được mong đợi là gì?

Parser thường hoạt động trên luồng token do lexer tạo ra. Ở mỗi bước, parser có một trạng thái hoặc một hàm grammar đang xử lý. Trạng thái đó xác định những token nào có thể xuất hiện hợp lệ tiếp theo.

Ví dụ DSL:

```text
let total price * quantity;
```

Giả sử grammar khai báo biến là:

```text
VariableDeclaration -> "let" IDENTIFIER "=" Expression ";"
```

Sau khi đọc `let` và `total`, parser cần token `=`. Nhưng token hiện tại là identifier `price`. Chẩn đoán có thể nói:

```text
Expected "=" after variable name "total".
Found identifier "price".
```

Trong thông báo này:

- **Expected token:** `=` — token mà grammar yêu cầu ở vị trí hiện tại.
- **Actual token:** `price` — token parser thực sự nhìn thấy.
- **Context:** sau tên biến trong khai báo `let`.
- **Source location:** vị trí của `price` hoặc khoảng vị trí nơi parser phát hiện lỗi.

Expected token không phải lúc nào cũng là một token duy nhất. Có những vị trí grammar cho phép nhiều lựa chọn, chẳng hạn một biểu thức có thể bắt đầu bằng identifier, number, string, dấu ngoặc mở hoặc toán tử một ngôi. Khi đó parser nên báo một tập token hoặc diễn đạt theo khái niệm dễ hiểu như “Expected an expression”.

## 2. Expected token và actual token

Để mô tả lỗi cú pháp chính xác, cần phân biệt điều parser cần với điều đầu vào cung cấp.

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Expected token | Token hoặc nhóm token hợp lệ ở vị trí hiện tại | `RIGHT_PAREN`, `SEMICOLON`, `IDENTIFIER` |
| Actual token | Token hiện tại trong luồng đầu vào | `COMMA`, `NUMBER`, `EOF` |
| Lexeme | Văn bản cụ thể tạo ra token | `)`, `42`, `customer` |
| Context | Cấu trúc grammar đang được phân tích | Danh sách tham số, khai báo entity, điều kiện rule |
| Source span | Vị trí trong tệp nguồn liên quan đến lỗi | Tệp, dòng, cột hoặc offset |

Ví dụ:

```text
rule freeShipping {
    when order.total >= 1000000
    then shipping.fee = 0
```

Parser gặp EOF khi vẫn cần `}` để đóng khối rule. Expected token là `RIGHT_BRACE`; actual token là EOF. Thông báo nên nêu rằng khối `rule` chưa được đóng, thay vì nói chung chung “unexpected end of file”.

### 2.1. Token kind và lexeme

Parser thường so sánh token kind, không chỉ so sánh văn bản. Ví dụ, các từ `let`, `if` và `rule` có thể được lexer phân loại thành các token riêng `LET`, `IF` và `RULE`. Với identifier, token kind là `IDENTIFIER`, còn lexeme là tên cụ thể như `customer`.

Trong diagnostic, dùng cả hai khi hữu ích: tên loại token giúp mô tả cấu trúc, còn lexeme giúp người viết nhận ra chính xác đoạn văn bản gây lỗi.

### 2.2. EOF cũng là một token

EOF (end of file) biểu thị đã hết đầu vào. Nó không phải ký tự do người dùng viết, nhưng parser cần xem nó như một token đặc biệt để xử lý trường hợp cấu trúc chưa hoàn chỉnh.

Ví dụ:

```text
entity Customer {
    name: String

```

Khi gặp EOF, parser đang mong `}`. Diagnostic nên nói “Expected `}` to close entity `Customer`, but reached end of file.”

## 3. Expected-token set được xác định như thế nào?

Expected-token set là tập token có thể xuất hiện hợp lệ tiếp theo theo grammar và trạng thái parser hiện tại. Nó không nên là danh sách token phổ biến của toàn bộ ngôn ngữ.

### 3.1. Tập token đầu vào của một quy tắc

Ví dụ grammar:

```text
Primary -> NUMBER
         | STRING
         | IDENTIFIER
         | "(" Expression ")"
         | "true"
         | "false"
```

Khi parser đang ở `parsePrimary`, tập token được mong đợi có thể là:

```text
{ NUMBER, STRING, IDENTIFIER, LEFT_PAREN, TRUE, FALSE }
```

Nếu parser gặp `RIGHT_BRACE`, thông báo có thể là “Expected an expression” và phần chi tiết liệt kê một số lựa chọn phù hợp. Cách diễn đạt theo khái niệm thường dễ hiểu hơn việc đưa ra toàn bộ token nội bộ.

### 3.2. FIRST set

Trong lý thuyết phân tích cú pháp, `FIRST(X)` là tập terminal có thể xuất hiện đầu tiên trong chuỗi được sinh từ ký hiệu X. Với grammar:

```text
Primary -> NUMBER | IDENTIFIER | "(" Expression ")"
```

`FIRST(Primary)` gồm `NUMBER`, `IDENTIFIER` và `LEFT_PAREN`.

Parser dự đoán có thể dùng FIRST set để quyết định nhánh và để tạo expected-token set khi một cấu trúc cần bắt đầu.

### 3.3. FOLLOW set và điểm kết thúc cấu trúc

`FOLLOW(A)` là tập terminal có thể xuất hiện ngay sau nonterminal A trong một dẫn xuất hợp lệ. Tập này hữu ích khi parser xử lý cấu trúc tùy chọn hoặc danh sách lặp.

Ví dụ:

```text
Block -> "{" Statement* "}"
```

Trong block, parser tiếp tục đọc statement cho đến khi gặp `RIGHT_BRACE`. Nếu gặp token không thể bắt đầu statement và cũng không phải `RIGHT_BRACE`, parser có thể báo expected statement hoặc `}` tùy ngữ cảnh.

FOLLOW giúp xác định token nào có thể kết thúc một cấu trúc. Vì vậy, expected-token set đôi khi là hợp của FIRST của cấu trúc tiếp theo và FOLLOW của cấu trúc hiện tại.

### 3.4. Expected token phụ thuộc trạng thái parser

Cùng một token có thể hợp lệ ở nơi này nhưng không hợp lệ ở nơi khác. `COMMA` có thể hợp lệ giữa hai tham số, nhưng không hợp lệ ngay sau từ khóa `if` nếu grammar yêu cầu dấu `(`.

Vì vậy, diagnostic phải được tạo từ vị trí parser thực sự đang đứng, không chỉ từ danh sách token toàn cục mà ngôn ngữ hỗ trợ.

## 4. Hàm consume/expect trong recursive descent parser

Trong recursive descent, một hàm tiện ích thường được dùng để yêu cầu một token cụ thể. Tên hàm có thể là `consume`, `expect`, `matchRequired` hoặc tên tương tự.

Ví dụ mã giả:

```text
consume(expectedKind, message):
    if check(expectedKind):
        return advance()

    raise ParseError(
        expected = { expectedKind },
        actual = peek(),
        message = message,
        span = peek().span
    )
```

Khi phân tích khai báo:

```text
parseVariableDeclaration():
    name = consume(IDENTIFIER, "Expected variable name")
    consume(EQUAL, "Expected = after variable name")
    initializer = parseExpression()
    consume(SEMICOLON, "Expected ; after initializer")
    return VariableDeclaration(name, initializer)
```

Mỗi lần `consume` thất bại, parser biết token cần có và có thể lấy token hiện tại để đưa vào diagnostic. Việc truyền thông điệp theo ngữ cảnh giúp lỗi cụ thể hơn.

### 4.1. Không phải mọi lỗi đều nên dùng consume

`consume` phù hợp khi grammar yêu cầu một token cụ thể tại vị trí xác định. Khi parser đang chọn giữa nhiều cấu trúc, nên dùng `match`, lookahead hoặc một hàm phân tích con để xác định lựa chọn. Nếu gọi `consume` quá sớm, parser có thể báo lỗi sai ngữ cảnh.

### 4.2. Expected set có nhiều lựa chọn

Một helper tổng quát có thể nhận nhiều loại token:

```text
expectOneOf({IDENTIFIER, NUMBER, STRING}, "Expected a value")
```

Nếu token hiện tại không thuộc tập, diagnostic có thể hiển thị “Expected a value (identifier, number or string), found `}`.” Trong thực tế, parser có thể ưu tiên một nhãn khái niệm thay cho tên token nội bộ.

## 5. Viết thông báo lỗi dễ hiểu

Một thông báo lỗi tốt cần ngắn gọn, chính xác và có thể hành động. Nó nên trả lời ba câu hỏi: parser mong gì, parser gặp gì và người dùng có thể sửa thế nào.

### 5.1. Mẫu thông báo cơ bản

Có thể dùng mẫu:

```text
Expected <expected>, but found <actual>.
<context or hint>
```

Ví dụ:

```text
Expected ":" after property name "email", but found "String".
Use: email: String
```

Thông báo này cho biết dấu `:` bị thiếu sau tên thuộc tính. Nó còn cung cấp một ví dụ cú pháp đúng.

### 5.2. Nêu ngữ cảnh cụ thể

Thông báo “Expected `}`” hữu ích hơn “Syntax error”, nhưng “Expected `}` to close the `entity Customer` block” còn hữu ích hơn vì người dùng biết dấu đóng thuộc về cấu trúc nào.

Ngữ cảnh có thể gồm:

- Tên khai báo hiện tại, ví dụ `Customer` hoặc `freeShipping`.
- Vị trí trong cấu trúc, ví dụ sau tên thuộc tính hoặc trước nhánh `else`.
- Tên hàm hoặc rule đang được phân tích.
- Danh sách tham số hoặc phần tử đang đọc.
- Tệp import hoặc module liên quan nếu lỗi nằm ở cấu trúc nhiều tệp.

### 5.3. Hiển thị actual token phù hợp

Với identifier hoặc literal, có thể hiển thị lexeme trong dấu nháy. Với token dấu câu, hiển thị ký hiệu. Với EOF, dùng “end of file” hoặc “end of input”.

Không nên in trực tiếp các tên enum nội bộ như `TOKEN_RIGHT_PAREN` cho người dùng nếu có thể chuyển thành `)` hoặc “closing parenthesis”.

### 5.4. Tránh liệt kê quá nhiều lựa chọn

Một biểu thức có thể bắt đầu bằng hàng chục token do nhiều tính năng mở rộng. In toàn bộ danh sách có thể khiến thông báo khó đọc.

Có thể:

- Gom token thành nhóm khái niệm như “expression”, “type name” hoặc “statement”.
- Chỉ hiển thị một số lựa chọn tiêu biểu.
- Đưa danh sách chi tiết vào phần mở rộng của diagnostic hoặc IDE.
- Dùng ngữ cảnh để thu hẹp expected set.

### 5.5. Phân biệt expected token với gợi ý sửa

Expected token là kết luận dựa trên grammar. Gợi ý sửa là phỏng đoán về ý định người viết. Ví dụ, khi parser cần `)` nhưng gặp `{`, có thể gợi ý rằng người viết quên đóng điều kiện. Gợi ý phải được trình bày như khả năng, không được khẳng định chắc chắn khi có nhiều cách sửa.

## 6. Vị trí lỗi và source span

Diagnostic cần trỏ đến vị trí có ý nghĩa. Parser thường có thể gắn lỗi vào token hiện tại, nhưng đôi khi vị trí tốt nhất là ngay trước token đó hoặc tại token mở đầu cấu trúc chưa hoàn tất.

### 6.1. Vị trí token hiện tại

Khi parser gặp một token không được mong đợi, vị trí token đó là vị trí tự nhiên để đánh dấu lỗi.

```text
let total price * quantity;
          ^
Expected "=" after variable name.
```

### 6.2. Vị trí token bị thiếu

Với token bị thiếu, không có lexeme thực tế để đánh dấu. Có thể đặt diagnostic ở vị trí hiện tại, tức trước token tiếp theo, hoặc gắn vào token trước đó.

Ví dụ:

```text
let total = 10
              ^
Expected ";" after variable declaration.
```

### 6.3. Source span của cấu trúc mở

Với dấu `}` bị thiếu, parser có thể lưu span của `{` để thông báo:

```text
Unclosed block. Expected "}" to match "{" opened at line 4, column 18.
```

Cách này giúp người dùng tìm được điểm mở tương ứng thay vì chỉ nhìn EOF ở cuối tệp.

### 6.4. Unicode và cách tính cột

Văn bản Unicode khiến byte offset, UTF-16 code unit, code point và cột hiển thị có thể khác nhau. Lexer và parser cần giữ source span theo một quy ước ổn định, sau đó chuyển đổi sang đơn vị mà editor hoặc giao thức tích hợp yêu cầu.

Không nên tự cộng một cột cho mỗi byte UTF-8. Với ký tự nhiều byte hoặc grapheme gồm nhiều code point, vị trí đánh dấu có thể lệch nếu hệ thống không thống nhất cách tính.

## 7. Expected token trong các tình huống grammar phổ biến

### 7.1. Thiếu dấu phân cách

Ví dụ:

```text
entity Customer {
    name String
}
```

Nếu grammar yêu cầu `name: String`, parser gặp `String` khi đang chờ `:`. Thông báo:

```text
Expected ":" after property name "name", found type name "String".
```

### 7.2. Thiếu dấu đóng

Ví dụ:

```text
notifyCustomer(order;
```

Parser cần `RIGHT_PAREN` nhưng gặp `SEMICOLON`. Diagnostic:

```text
Expected ")" to close the argument list, found ";".
```

### 7.3. Thiếu biểu thức

Ví dụ:

```text
when order.total >= then
```

Sau toán tử `>=`, parser cần một biểu thức. Token `then` là từ khóa bắt đầu phần tiếp theo, nên lỗi có thể là:

```text
Expected an expression after ">=", found "then".
```

### 7.4. Thiếu tên sau từ khóa

Ví dụ:

```text
entity {
```

Sau `entity`, parser cần identifier làm tên entity. Diagnostic:

```text
Expected an entity name after "entity", found "{".
```

### 7.5. Thiếu token ở cuối tệp

Ví dụ:

```text
workflow fulfillOrder {
    step validateOrder
    step chargePayment
```

Parser cần `}` để đóng workflow nhưng gặp EOF:

```text
Unexpected end of file. Expected "}" to close workflow "fulfillOrder".
```

## 8. Expected token và phục hồi lỗi

Báo lỗi và phục hồi lỗi là hai việc liên quan nhưng khác nhau. Parser có thể phát hiện expected token sai, rồi quyết định có thể tự sửa tạm thời để tiếp tục phân tích hay phải dừng.

Các chiến lược phổ biến gồm insertion, deletion, panic-mode synchronization và tạo error node.

### 8.1. Chèn token giả định (single-token insertion)

Parser có thể giả định người viết quên một token đơn giản, chẳng hạn `)` hoặc `;`, chèn token tổng hợp vào luồng phân tích rồi tiếp tục.

Ví dụ:

```text
notifyCustomer(order;
```

Parser có thể chèn `)` trước `;` để tiếp tục:

```text
notifyCustomer(order);
```

Nhưng parser phải đánh dấu token được chèn là synthetic và giữ diagnostic. Không nên âm thầm sửa chương trình rồi coi như không có lỗi.

### 8.2. Xóa token thừa (single-token deletion)

Nếu token hiện tại có vẻ thừa và token tiếp theo khớp expected token, parser có thể bỏ qua token hiện tại.

Ví dụ:

```text
let total = = 10;
```

Parser có thể phát hiện `=` thứ hai là token thừa vì sau khi bỏ nó, `NUMBER` có thể bắt đầu biểu thức. Tuy nhiên, quyết định này cần thận trọng: token hiện tại có thể không thừa mà là dấu hiệu của lỗi lớn hơn.

### 8.3. Panic-mode synchronization

Khi parser không thể sửa cục bộ một cách an toàn, nó có thể bỏ qua token đến điểm đồng bộ như `;`, `}` hoặc từ khóa bắt đầu khai báo tiếp theo.

Ví dụ mã giả:

```text
synchronize():
    advance()
    while not isAtEnd():
        if previous().kind == SEMICOLON:
            return
        if peek().kind in {ENTITY, RULE, WORKFLOW, LET, IF}:
            return
        advance()
```

Điểm đồng bộ cần phù hợp với grammar. Nếu parser đồng bộ quá sớm, nó có thể báo nhiều lỗi thứ cấp; nếu bỏ qua quá xa, nó có thể làm mất cả cấu trúc hợp lệ tiếp theo.

### 8.4. Error node

Parser phục vụ IDE có thể tạo `ErrorExpression`, `ErrorType` hoặc `ErrorStatement` để giữ hình dạng cây và cho phép các bước sau tiếp tục làm việc trên phần hợp lệ.

Node lỗi cần chứa source span và trạng thái lỗi. Semantic analyzer phải tránh tạo thêm nhiều diagnostic vô ích từ cùng một node lỗi.

## 9. Phân biệt lỗi gốc và lỗi dây chuyền

Một lỗi cú pháp có thể khiến parser hiểu sai phần tiếp theo và phát sinh nhiều thông báo không liên quan. Đây là lỗi dây chuyền (cascading errors).

Ví dụ:

```text
entity Customer {
    name: String
    email String
    age: Integer
}
```

Thiếu dấu `:` sau `email` là lỗi gốc. Nếu parser không phục hồi đúng, nó có thể báo thêm lỗi ở `age`, dấu `}` hoặc các cấu trúc sau dù chúng vốn hợp lệ.

Để giảm lỗi dây chuyền:

- Phục hồi tại ranh giới cấu trúc phù hợp.
- Giữ node lỗi cho phần không thể phân tích.
- Tránh chạy kiểm tra ngữ nghĩa sâu trên vùng AST đã lỗi nếu điều đó chỉ tạo lỗi thứ cấp.
- Gộp diagnostic trùng lặp hoặc phụ thuộc trực tiếp vào cùng một lỗi gốc.
- Tiếp tục phân tích các khai báo độc lập khi có thể.

## 10. Expected token trong grammar mơ hồ

Khi nhiều nhánh grammar có tiền tố chung, expected-token set có thể lớn hoặc phụ thuộc vào lookahead. Parser cần tránh báo một token cụ thể quá sớm.

Ví dụ grammar:

```text
Statement -> IDENTIFIER "=" Expression ";"
           | IDENTIFIER "(" Arguments ")" ";"
```

Sau khi đọc `IDENTIFIER`, parser chưa thể biết đây là phép gán hay lời gọi hàm. Token tiếp theo cần là `=` hoặc `(`. Nếu token tiếp theo là `;`, expected set tại điểm đó có thể là `{EQUAL, LEFT_PAREN}`.

Thông báo thân thiện:

```text
Expected "=" for an assignment or "(" for a function call after "process".
Found ";".
```

Nếu grammar được left-factor, parser có thể đọc identifier trước rồi chọn nhánh dựa trên token tiếp theo. Diagnostic khi đó phản ánh chính xác lựa chọn còn lại.

### 10.1. Không báo expected token của nhánh đã bị loại

Trong parser có backtracking, một nhánh thử có thể thất bại trước khi nhánh khác được chọn. Diagnostic cuối cùng không nên đơn giản lấy lỗi đầu tiên hoặc ghép mọi token mà tất cả nhánh từng mong đợi.

Parser có thể giữ lỗi sâu nhất (farthest failure), hợp nhất expected set tại cùng vị trí hoặc chọn thông điệp theo nhánh có ngữ cảnh rõ nhất. Cách hợp nhất cần tránh tạo danh sách token gây nhiễu.

### 10.2. Expected set theo điểm thất bại sâu nhất

Với backtracking, parser thường lưu vị trí token mà tại đó một nhánh đi xa nhất trước khi thất bại. Nếu nhiều nhánh thất bại tại cùng vị trí, expected set có thể được hợp nhất. Cách này thường cho chẩn đoán tốt hơn việc báo token mà nhánh đầu tiên cần ngay từ đầu.

## 11. Gợi ý sửa lỗi (quick fixes)

Expected token có thể là cơ sở cho gợi ý sửa, nhưng không phải mọi lỗi đều có một cách sửa duy nhất.

Ví dụ:

| Tình huống | Gợi ý có thể đưa ra |
|---|---|
| Thiếu `;` trước khai báo tiếp theo | Chèn `;` ở cuối câu lệnh trước |
| Thiếu `)` trước `{` | Chèn `)` để đóng điều kiện |
| Thiếu `:` giữa tên thuộc tính và kiểu | Chèn `:` sau tên thuộc tính |
| Dùng nhầm keyword trong vị trí identifier | Đổi tên hoặc escape identifier nếu DSL hỗ trợ |
| Thiếu `}` ở EOF | Chèn `}` để đóng block đang mở |

### 11.1. Khi nào có thể tự động sửa?

Quick fix có thể được áp dụng tự động khi vị trí và token bị thiếu gần như chắc chắn, chẳng hạn thiếu dấu `;` ngay trước một khai báo mới. Với lỗi có nhiều cách sửa, nên hiển thị gợi ý để người dùng chọn.

### 11.2. Không thay đổi nội dung âm thầm

Parser hoặc IDE không nên tự ghi lại mã nguồn mà không thông báo. Nếu dùng token tổng hợp để tiếp tục phân tích, trạng thái đó phải được đánh dấu và diagnostic phải còn hiển thị.

## 12. Expected token trong parser sinh tự động và parser thủ công

Parser có thể được viết thủ công bằng recursive descent hoặc sinh từ grammar bằng công cụ parser generator. Cả hai đều cần thông tin expected token, nhưng cách thu thập khác nhau.

### 12.1. Parser thủ công

Với recursive descent, hàm `consume` hoặc `expect` biết token cụ thể đang yêu cầu. Với lựa chọn nhiều nhánh, parser có thể cung cấp tập token rõ ràng hoặc mô tả theo khái niệm.

Ưu điểm là dễ viết thông điệp gắn với ngữ cảnh nghiệp vụ, ví dụ “Expected a currency code after `amount`”. Hạn chế là nếu mỗi hàm tự xây dựng diagnostic theo cách khác nhau, thông điệp có thể thiếu nhất quán.

### 12.2. Parser generator

Parser generator thường có thể suy ra expected-token set từ trạng thái parser và bảng phân tích. Một số công cụ cung cấp danh sách token hợp lệ tại điểm lỗi.

Tuy nhiên, danh sách suy ra từ trạng thái máy có thể chứa token nội bộ hoặc lựa chọn quá chi tiết. Lớp diagnostic của DSL nên chuyển chúng thành tên hiển thị, nhóm khái niệm và thông điệp có ngữ cảnh.

### 12.3. Dùng chung lớp diagnostic

Dù parser được viết thủ công hay sinh tự động, nên có một cấu trúc diagnostic thống nhất:

```text
Diagnostic
├── code: PARSE_EXPECTED_TOKEN
├── severity: ERROR
├── message: Expected ")" to close argument list
├── primarySpan: vị trí token hiện tại
├── expected: { RIGHT_PAREN }
├── actual: SEMICOLON
├── context: CallExpression
└── relatedSpans: vị trí dấu "(" mở danh sách
```

Nhờ đó, terminal, IDE, formatter và Language Server có thể hiển thị cùng một lỗi theo các cách phù hợp.

## 13. Expected token và ngữ cảnh DSL

DSL thường có thuật ngữ miền riêng. Diagnostic nên diễn đạt expected token theo khái niệm mà người dùng hiểu, không chỉ theo thuật ngữ parser.

Ví dụ:

```text
Expected an entity name after "entity".
```

thân thiện hơn:

```text
Expected IDENTIFIER token.
```

Với một DSL mô tả quy tắc:

```text
rule freeShipping {
    when order.total >=
    then shipping.fee = 0
}
```

Thông báo phù hợp có thể là:

```text
Expected a value or expression after ">=" in the rule condition.
Found keyword "then".
```

Parser biết mình đang ở điều kiện của rule, vì vậy có thể dùng thuật ngữ “rule condition”. Đây là lợi thế của việc truyền context vào các hàm parse hoặc giữ thông tin cấu trúc đang mở.

## 14. Expected token trong danh sách và dấu phẩy

Các danh sách tham số, thuộc tính hoặc phần tử thường có quy tắc dấu phân cách.

Ví dụ:

```text
call notifyCustomer(order, customer);
```

Grammar có thể là:

```text
Arguments -> Expression ("," Expression)*
```

Sau khi parser đọc một biểu thức trong danh sách, token tiếp theo được mong đợi có thể là `COMMA` để bắt đầu phần tử tiếp theo hoặc `RIGHT_PAREN` để kết thúc danh sách.

Ví dụ lỗi:

```text
call notifyCustomer(order customer);
```

Diagnostic:

```text
Expected "," or ")" after the first argument, found identifier "customer".
```

Nếu parser biết số lượng tham số và chữ ký hàm, nó có thể cung cấp thông báo chuyên biệt hơn, nhưng việc kiểm tra chữ ký thường thuộc semantic analysis sau khi cú pháp đã được phân tích.

## 15. Expected token và dấu đóng tương ứng

Các dấu ngoặc và dấu khối thường có cặp mở/đóng: `(` với `)`, `[` với `]`, `{` với `}`. Parser nên lưu vị trí dấu mở để khi thiếu dấu đóng có thể đưa ra related location.

Ví dụ:

```text
workflow processOrder {
    if (order.isPaid {
        dispatch(order)
    }
}
```

Parser gặp `{` khi đang mong `)` để đóng điều kiện. Diagnostic có thể chỉ cả vị trí dấu `(`:

```text
Expected ")" after the condition, found "{".
The matching "(" is at line 2, column 8.
```

Thông tin dấu mở giúp người dùng xác định vị trí cần sửa, nhất là khi cấu trúc lồng nhau sâu.

## 16. Thiết kế cấu trúc diagnostic

Một hệ thống parser nên lưu dữ liệu lỗi có cấu trúc thay vì chỉ tạo một chuỗi message.

Ví dụ mô hình:

```text
ParseDiagnostic
├── code
├── message
├── expectedTokenKinds
├── actualToken
├── primarySpan
├── parserContext
├── relatedSpans
├── notes
└── suggestedFixes
```

### 16.1. Error code ổn định

Mã như `PARSE_EXPECTED_TOKEN` có thể được IDE hoặc công cụ CI sử dụng để lọc và xử lý. Message có thể thay đổi theo phiên bản hoặc ngôn ngữ hiển thị, nhưng error code nên ổn định hơn.

### 16.2. Expected set có cấu trúc

Giữ expected token dưới dạng enum hoặc tập token kind giúp terminal renderer, IDE và test sử dụng cùng dữ liệu. Không nên chỉ phân tích ngược chuỗi message để lấy token được mong đợi.

### 16.3. Related locations

Với dấu đóng bị thiếu, related span có thể trỏ đến dấu mở. Với tên sai, related span có thể trỏ đến khai báo gần giống. Những vị trí phụ này giúp diagnostic có ngữ cảnh mà không làm message chính quá dài.

### 16.4. Diagnostic không phải là AST

Thông tin lỗi có thể được lưu riêng với AST hoặc gắn vào error node. Tách riêng giúp các công cụ thu thập lỗi thống nhất; error node giúp giữ cấu trúc cây để tiếp tục phân tích. Hai cách có thể được kết hợp.

## 17. Các lỗi thường gặp khi tạo expected-token message

| Vấn đề | Vì sao gây khó hiểu | Cách cải thiện |
|---|---|---|
| Chỉ ghi “Syntax error” | Không cho biết cần gì hoặc gặp gì | Nêu expected và actual token |
| Hiển thị tên enum nội bộ | Người dùng không biết `TOKEN_RPAREN` là gì | Dùng ký hiệu hoặc tên thân thiện như `)` |
| Liệt kê toàn bộ token của DSL | Expected set quá rộng và không liên quan | Tính theo parser state và gom nhóm khái niệm |
| Báo lỗi ở đầu câu lệnh | Người dùng khó tìm điểm sai | Gắn primary span vào token gây lỗi hoặc điểm thiếu |
| Không xử lý EOF riêng | Thông báo “found EOF” khó hiểu | Dùng “unexpected end of file/input” |
| Chỉ báo token thiếu, không có context | Không biết cấu trúc nào chưa hoàn tất | Nêu tên block, khai báo hoặc danh sách |
| Gợi ý sửa như một sự thật | Có thể dẫn người dùng sửa sai | Phân biệt expected token với suggested fix |
| Ghép lỗi từ mọi nhánh backtracking | Expected set rất dài và nhiễu | Dùng điểm thất bại sâu nhất và context phù hợp |
| Phục hồi nhưng không đánh dấu token tổng hợp | AST có thể bị hiểu nhầm là hoàn toàn hợp lệ | Giữ diagnostic và đánh dấu synthetic token/node |

## 18. Kiểm thử expected-token diagnostics

Kiểm thử chẩn đoán nên xác nhận dữ liệu lỗi được tạo đúng cho các trường hợp cụ thể. Mỗi test có thể kiểm tra error code, expected set, actual token, source span và message chính.

Các trường hợp thường cần có:

- Thiếu dấu `=` trong khai báo biến.
- Thiếu `:` trong khai báo thuộc tính.
- Thiếu `)` trong lời gọi hàm hoặc điều kiện.
- Thiếu `}` ở cuối block hoặc cuối tệp.
- Thiếu biểu thức sau toán tử.
- Token không hợp lệ ở đầu câu lệnh.
- Một vị trí có nhiều expected token hợp lệ.
- EOF trong danh sách, biểu thức hoặc cấu trúc lồng nhau.
- Backtracking với nhiều nhánh có tiền tố chung.
- Lỗi sau ký tự Unicode nhiều byte để kiểm tra source location.
- Phục hồi lỗi không tạo quá nhiều diagnostic dây chuyền.

Test nên dựa trên source DSL thực tế và so sánh span theo quy ước của parser. Nếu message có thể được bản địa hóa, test có thể ưu tiên error code và structured fields thay vì phụ thuộc toàn bộ câu chữ.

## 19. Nguyên tắc thiết kế expected-token diagnostics

Khi xây dựng parser cho DSL, có thể áp dụng các nguyên tắc sau:

1. **Tính expected set từ trạng thái grammar hiện tại.** Không dùng một danh sách token chung cho toàn ngôn ngữ.
2. **Phân biệt expected và actual.** Nêu rõ parser cần gì và đang gặp gì.
3. **Đưa ngữ cảnh vào thông báo.** Nói rõ đang ở khai báo, điều kiện, danh sách tham số hay block nào.
4. **Xử lý EOF như trường hợp riêng.** Nêu cấu trúc chưa được đóng hoặc thành phần còn thiếu.
5. **Dùng tên token thân thiện.** Hiển thị `)` thay cho enum nội bộ.
6. **Giữ source span và related span.** Cho phép IDE đánh dấu lỗi và vị trí mở tương ứng.
7. **Tách diagnostic khỏi quick fix.** Expected token là thông tin grammar; sửa lỗi là đề xuất có thể cần xác nhận.
8. **Quản lý backtracking.** Chọn lỗi có giá trị nhất, thường dựa trên điểm thất bại sâu nhất và expected set phù hợp.
9. **Phục hồi có kiểm soát.** Chèn/xóa token giả định hoặc đồng bộ chỉ khi có cơ sở; luôn giữ trạng thái lỗi.
10. **Giảm lỗi dây chuyền.** Không tiếp tục báo những lỗi thứ cấp không hữu ích từ cùng một vùng cú pháp đã hỏng.
11. **Dùng structured diagnostic.** Cung cấp error code, expected kinds, actual token, span và context cho mọi công cụ.
12. **Kiểm thử cả nội dung lẫn vị trí.** Một message đúng nhưng trỏ sai dòng/cột vẫn gây khó khăn cho người dùng.

## 20. Kết luận

Token được mong đợi là thông tin cho biết parser cần nhận token hoặc nhóm token nào tại vị trí hiện tại theo grammar. Khi kết hợp với actual token, ngữ cảnh và source span, nó tạo thành một chẩn đoán cú pháp có thể giúp người viết hiểu và sửa lỗi.

Expected-token set cần được xác định từ trạng thái parser, FIRST/FOLLOW hoặc các lựa chọn grammar đang hợp lệ. Parser nên phân biệt token thiếu, token thừa, token sai và EOF; đồng thời có chiến lược phục hồi phù hợp để tránh lỗi dây chuyền. Với parser có backtracking, cần tổng hợp expected set cẩn thận để không đưa ra danh sách gây nhiễu.

Một DSL dễ sử dụng không chỉ phát hiện đầu vào sai mà còn giải thích rõ cấu trúc đang chờ, vị trí cần sửa và những lựa chọn hợp lệ. Diagnostic có cấu trúc, source mapping chính xác và gợi ý sửa có kiểm soát giúp parser trở thành một phần hữu ích của trải nghiệm phát triển DSL.

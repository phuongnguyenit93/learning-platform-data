# Trình định dạng

## 1. Formatter trong DSL editor là gì?

Trong một ngôn ngữ chuyên biệt miền (*Domain-Specific Language — DSL*), người viết có thể trình bày cùng một cấu trúc theo nhiều cách: xuống dòng khác nhau, dùng số lượng dấu cách khác nhau, đặt dấu ngoặc ở cùng hoặc dòng riêng, hoặc viết biểu thức dài trên một dòng. Nếu những khác biệt đó không làm thay đổi ý nghĩa chương trình, editor có thể tự động chuẩn hóa cách trình bày bằng **trình định dạng (*formatter*)**.

Formatter là công cụ đọc văn bản DSL, hiểu cấu trúc của nó và tạo ra văn bản mới theo một bộ quy tắc trình bày nhất quán. Nó thường được tích hợp vào editor qua lệnh Format Document, Format Selection, phím tắt hoặc thao tác lưu file.

Ví dụ, hai đoạn sau có thể có cùng ý nghĩa:

~~~text
rule "vip-customer"{when customer.totalSpent>10000000 and customer.active then grantBenefit(customer)}
~~~

~~~text
rule "vip-customer" {
    when customer.totalSpent > 10000000 and customer.active
    then grantBenefit(customer)
}
~~~

Formatter có thể chuyển dạng đầu thành dạng thứ hai theo quy tắc về khoảng trắng, xuống dòng và indentation.

Mục tiêu quan trọng nhất là **giữ nguyên ngữ nghĩa**. Formatter thay đổi cách viết, không thay đổi điều kiện, thứ tự thực thi, giá trị literal hoặc quan hệ giữa các thành phần của DSL.

Một formatter tốt giúp:
- Tăng khả năng đọc và review.
- Giảm tranh luận về style trong nhóm.
- Làm diff dễ hiểu hơn.
- Giúp người mới tuân theo quy ước của dự án.
- Chuẩn hóa file được sinh bởi nhiều công cụ.
- Tạo nền tảng cho thao tác format tự động trong editor và CI.

## 2. Formatter khác parser và linter như thế nào?

Ba công cụ có thể cùng sử dụng parser hoặc AST nhưng có trách nhiệm khác nhau.

| Công cụ | Trách nhiệm | Ví dụ |
|---|---|---|
| Parser | Xác định cấu trúc source có đúng grammar không | Nhận diện rule, expression và block |
| Formatter | Viết lại whitespace và layout theo style | Thụt lề block, đặt dấu cách quanh operator |
| Linter | Phát hiện vấn đề về style, chất lượng hoặc quy tắc | Cảnh báo tên biến không phù hợp hoặc rule không dùng |

Formatter không nên tự sửa lỗi ngữ nghĩa hoặc đổi tên symbol. Linter có thể đề xuất thay đổi nhưng không nhất thiết viết lại toàn bộ văn bản.

Một pipeline thường gặp:

~~~text
DSL source
    |
    v
Lexer / Parser
    |
    v
Syntax tree + comments/trivia
    |
    v
Formatter
    |
    v
Formatted source
    |
    v
Editor buffer / file
~~~

Nếu source không parse được, formatter cần có chính sách rõ: từ chối format, format phần hợp lệ hoặc dùng recovery tree. Không nên âm thầm xóa đoạn không parse được.

## 3. Formatter cần hiểu cấu trúc DSL

### 3.1. Vì sao không chỉ dùng regex?

Một số thay đổi đơn giản như thêm dấu cách quanh dấu bằng có vẻ có thể làm bằng tìm kiếm và thay thế. Tuy nhiên, cùng một ký tự có thể có ý nghĩa khác nhau tùy context.

Ví dụ:

~~~text
message = "a+b=c"
total=price+tax
query = SELECT a+b FROM orders
~~~

Dấu cộng trong string không phải toán tử. Dấu bằng có thể là assignment, comparison hoặc nội dung của embedded language. Regex không đủ thông tin để biết nơi nào có thể thay đổi an toàn.

Formatter nên dựa trên token stream và syntax tree để biết:
- Node nào là expression, declaration hoặc statement.
- Dấu ngoặc nào thuộc cấu trúc nào.
- Comment gắn với node nào.
- String literal và raw text cần được bảo toàn ra sao.
- Newline có ý nghĩa cú pháp hay chỉ là layout.

### 3.2. Concrete syntax tree và abstract syntax tree

AST tập trung vào cấu trúc ngữ nghĩa và có thể bỏ qua dấu ngoặc, dấu phẩy hoặc trivia không cần cho semantic analysis. Formatter thường cần nhiều thông tin hơn AST.

- **Concrete Syntax Tree (CST):** giữ các token và cấu trúc cú pháp cụ thể.
- **Abstract Syntax Tree (AST):** giữ các cấu trúc có ý nghĩa cho phân tích và thực thi.
- **Trivia:** whitespace, comment và một số token không tham gia trực tiếp vào semantics.

Một formatter có thể dùng CST, AST kết hợp token stream, hoặc một document model riêng. Nếu chỉ dùng AST đã bỏ comment và token gốc, formatter có thể làm mất thông tin người viết muốn giữ.

### 3.3. Source positions

Mỗi token hoặc node nên có source range. Formatter cần biết đoạn nào được tạo từ source nào để:
- Giữ comment gần node phù hợp.
- Format một vùng được chọn.
- Tạo text edit chính xác.
- Bảo toàn đoạn chưa được parse.
- Giữ cursor và selection ổn định trong editor.

## 4. Quy trình hoạt động của formatter

Một pipeline formatter có thể gồm:

1. Nhận source text, document version và formatting options.
2. Tokenize và parse source.
3. Thu thập comment và trivia.
4. Xây dựng document representation từ syntax tree.
5. Áp dụng quy tắc layout và line breaking.
6. Render document thành văn bản.
7. So sánh với source hiện tại.
8. Trả về text edits hoặc toàn bộ văn bản đã format.

Sơ đồ khái niệm:

~~~text
Source text
    |
    v
Lexer / Parser
    |
    v
Syntax + Trivia
    |
    v
Document Builder
    |
    v
Layout Rules
    |
    v
Line Breaking / Indentation
    |
    v
Renderer
    |
    v
Formatted text or Text Edits
~~~

### 4.1. Parse trước khi format

Formatter cần biết cấu trúc để phân biệt token. Nếu parse thất bại, kết quả phụ thuộc recovery policy. Với file đang gõ dở, parser incremental có thể cung cấp syntax tree chưa hoàn chỉnh để formatter giới hạn thay đổi vào các node đã hiểu được.

### 4.2. Xây document model

Thay vì nối chuỗi ngay khi duyệt AST, nhiều formatter xây một biểu diễn trung gian gồm các lệnh layout như:
- Text: in token hoặc chuỗi literal.
- Line: tạo newline nếu cần.
- Soft line: có thể là space hoặc newline tùy độ rộng.
- Indent: tăng mức thụt lề cho vùng tiếp theo.
- Group: thử đặt một cụm trên một dòng.
- Break: cho phép xuống dòng tại điểm đã xác định.

Document model giúp formatter quyết định layout toàn cục thay vì chỉ sửa từng token độc lập.

### 4.3. Render

Renderer chọn cách trình bày dựa trên:
- Maximum line width.
- Indentation width.
- Cấu trúc group.
- Break opportunities.
- Quy tắc blank lines.
- Newline convention.

Sau khi render, formatter tạo kết quả ổn định để editor áp dụng.

## 5. Xây dựng bộ quy tắc định dạng

Một DSL nên có style specification rõ ràng. Những quy tắc thường gặp gồm:

| Khu vực | Quy tắc có thể cấu hình |
|---|---|
| Indentation | 2 hoặc 4 spaces, tab hoặc spaces |
| Line ending | LF hoặc CRLF |
| Braces | Cùng dòng hoặc dòng riêng |
| Operators | Khoảng trắng hai bên |
| Commas | Không có space trước, một space sau |
| Parentheses | Quy tắc space bên trong |
| Blank lines | Khoảng cách giữa declarations và blocks |
| Line width | Độ rộng tối đa khuyến nghị |
| Comments | Vị trí và căn lề |
| Trailing comma | Có hoặc không ở collection nhiều dòng |
| Quotes | Giữ nguyên hoặc chuẩn hóa theo DSL |
| Semicolons | Quy tắc kết thúc statement nếu có |

Các quy tắc phải phù hợp grammar. Ví dụ, nếu newline kết thúc statement trong DSL, formatter không thể tùy tiện đưa hai statement lên cùng một dòng.

### 5.1. Indentation

Ví dụ dùng 4 spaces cho mỗi block:

~~~text
workflow "checkout" {
    step validate {
        action = ValidateOrder
    }

    step charge {
        action = CapturePayment
    }
}
~~~

Indentation thường tăng khi đi vào block, object, collection hoặc continuation line và giảm khi đóng block.

Cần xác định tab được giữ nguyên hay chuyển thành spaces. Nếu editor và formatter dùng quy tắc khác nhau, file có thể liên tục thay đổi sau mỗi lần format.

### 5.2. Khoảng trắng quanh operator

Ví dụ:

~~~text
let total = subtotal + tax
when order.total >= threshold
when customer.active and customer.verified
~~~

Formatter cần biết operator nào là binary, unary, postfix hoặc thuộc cú pháp đặc biệt. Dấu trừ trong `-value` không nhất thiết được format giống phép trừ giữa hai operand.

### 5.3. Dấu phẩy và dấu phân cách

Ví dụ:

~~~text
callFunction(first, second, third)
~~~

Có thể quy định một dấu cách sau comma, không có dấu cách trước comma. Với collection nhiều dòng, trailing comma có thể được cho phép để giảm diff khi thêm phần tử.

### 5.4. Dấu ngoặc và block

Ví dụ một style đặt opening brace cùng dòng:

~~~text
rule "eligible" {
    when customer.active {
        grantBenefit(customer)
    }
}
~~~

Một style khác có thể đặt brace ở dòng riêng. Formatter cần tuân theo một cấu hình nhất quán, không trộn style theo từng node nếu không có lý do được định nghĩa.

### 5.5. Blank lines

Blank line có thể phân tách:
- Các declaration cấp cao.
- Các nhóm rule.
- Phần import và phần định nghĩa.
- Các block logic độc lập.

Không nên thêm blank line sau mọi statement vì làm source quá dài. Quy tắc cần dựa trên node type và cấu trúc.

## 6. Pretty-printing và line breaking

Pretty-printer là thành phần quyết định cách biểu diễn cấu trúc thành văn bản dễ đọc. Một pretty-printer tốt không chỉ thêm newline cố định; nó chọn layout dựa trên độ rộng và cấu trúc.

### 6.1. Maximum line width

Giả sử giới hạn là 80 ký tự. Biểu thức ngắn có thể giữ trên một dòng:

~~~text
let total = subtotal + tax
~~~

Biểu thức dài có thể được tách:

~~~text
let eligible =
    customer.active
    and customer.totalSpent >= minimumSpend
    and customer.country in supportedCountries
~~~

Maximum line width thường là mục tiêu layout, không phải giới hạn cú pháp. Một string literal dài hoặc URL có thể vượt độ rộng nếu không thể ngắt an toàn.

### 6.2. Break opportunities

Formatter nên xác định vị trí có thể xuống dòng:
- Sau comma trong argument list.
- Trước hoặc sau operator theo style.
- Giữa các điều kiện logic.
- Giữa các thuộc tính trong object.
- Giữa các phần tử collection.
- Trước statement trong block.

Không được ngắt string hoặc token theo cách làm thay đổi lexeme trừ khi DSL định nghĩa cách nối chuỗi rõ ràng.

### 6.3. Grouping

Các phần tử liên quan có thể được nhóm để formatter thử đặt trên một dòng. Nếu không vừa, group sẽ được render nhiều dòng.

Ví dụ:

~~~text
callFunction(first, second)
~~~

Nếu quá dài:

~~~text
callFunction(
    firstArgument,
    secondArgument,
    thirdArgument
)
~~~

### 6.4. Continuation indentation

Dòng tiếp theo của expression nên có quy tắc căn lề rõ. Có thể căn theo:
- Mức indent của statement.
- Vị trí mở ngoặc.
- Một continuation indent cố định.

Không nên để continuation line phụ thuộc vào số ký tự của tên biến theo cách khó dự đoán.

## 7. Xử lý comment và trivia

Comment là phần quan trọng của source và thường phải được bảo toàn.

Ví dụ:

~~~text
// Kiểm tra khách hàng trước khi áp dụng ưu đãi
rule "vip" {
    when customer.active /* account is enabled */
        and customer.totalSpent > threshold
    then grantBenefit(customer)
}
~~~

Formatter cần quyết định comment thuộc:
- Node phía trước.
- Node phía sau.
- Một block hoặc declaration.
- Vị trí độc lập giữa hai node.
- Inline position bên trong expression.

### 7.1. Leading comment

Comment trước declaration thường gắn với declaration đó:

~~~text
// Mức chi tiêu tối thiểu
let minimumSpend = 1000000
~~~

Nếu formatter tách comment khỏi declaration, ý nghĩa giải thích có thể bị mất.

### 7.2. Trailing comment

Comment cuối dòng thường gắn với statement hoặc token phía trước:

~~~text
let retryCount = 3 // số lần thử tối đa
~~~

Formatter có thể căn các trailing comment thành cột nếu style yêu cầu, nhưng cần tránh tạo nhiều khoảng trắng không cần thiết.

### 7.3. Inline comment

Comment bên trong expression có thể ảnh hưởng cách ngắt dòng. Formatter cần bảo toàn vị trí tương đối và không di chuyển comment qua ranh giới có thể làm thay đổi cách hiểu.

### 7.4. Comment nhiều dòng

Comment block có thể giữ nguyên nội dung, hoặc được căn lề theo block chứa nó. Nếu formatter reflow nội dung comment, cần có tùy chọn riêng vì việc ngắt lại văn bản có thể làm thay đổi ví dụ hoặc định dạng Markdown bên trong comment.

### 7.5. Comment như tài liệu

Một số DSL dùng comment đặc biệt làm annotation hoặc documentation. Ví dụ:
- Doc comment gắn với function.
- Directive của generator.
- Region marker.
- Suppression comment cho linter.

Những comment này có thể có cú pháp hoặc vị trí quan trọng. Formatter phải giữ chúng chính xác và không chuyển thành comment thường.

## 8. Bảo toàn string literal và token đặc biệt

Formatter thường nên giữ nguyên lexeme của string literal:
- Quote style.
- Escape sequence.
- Khoảng trắng bên trong.
- Newline escape.
- Unicode representation.

Ví dụ:

~~~text
message = "Line 1\nLine 2"
pattern = r"^[A-Z]+\d+$"
~~~

Không nên tự đổi `\n` thành newline thực, đổi dấu nháy hoặc chuẩn hóa escape nếu DSL không bảo đảm hai dạng tương đương.

Với raw string, regex, template hoặc embedded SQL, formatter có thể cần delegate sang formatter chuyên biệt hoặc giữ nguyên vùng đó.

### 8.1. Numeric literal

Formatter thường giữ cách viết số:
- `1_000`.
- `1.00`.
- `1e6`.
- `0xFF`.

Chuẩn hóa số có thể làm mất ý định về độ chính xác, đơn vị hoặc cách biểu diễn. Chỉ đổi khi lexical specification và style guide cho phép.

### 8.2. Case sensitivity

Không tự đổi hoa/thường của identifier hoặc keyword nếu semantics của DSL có phân biệt case hoặc nếu tên miền phải giữ nguyên. Formatter chủ yếu điều chỉnh layout.

### 8.3. Unknown token

Nếu parser gặp token không nhận diện, formatter cần giữ nguyên vùng đó hoặc từ chối format theo policy. Xóa token lạ để tạo output đẹp hơn có thể phá hỏng dữ liệu.

## 9. Newline và cấu trúc có ý nghĩa cú pháp

Một số DSL dùng newline làm dấu kết thúc statement hoặc phân tách phần tử. Với các DSL này, formatter phải hiểu newline là một phần của grammar.

Ví dụ:

~~~text
set customer = "An"
set active = true
~~~

Nếu hai dòng là hai statement riêng, formatter không được ghép chúng thành một dòng nếu không có dấu phân cách hợp lệ.

Cần xác định:
- LF, CRLF hoặc CR được chấp nhận.
- Blank line có ý nghĩa hay chỉ là whitespace.
- Continuation line được nhận diện thế nào.
- Newline trong parentheses có được bỏ qua không.
- Comment cuối dòng ảnh hưởng statement termination ra sao.
- Có semicolon insertion hoặc explicit terminator không.

Formatter nên dùng newline convention được chọn trong editor hoặc project config, nhưng phải giữ đúng ranh giới cú pháp.

## 10. Định dạng theo cấu trúc từng loại node

Một formatter DSL thường cần rule riêng cho từng node type.

### 10.1. Declaration

~~~text
let customerName: String = "An"
let retryCount: Integer = 3
~~~

Có thể quy định thứ tự annotation, type và initializer; khoảng trắng quanh dấu colon và assignment.

### 10.2. Function hoặc operation

~~~text
function calculateTax(
    amount: Money,
    rate: Decimal
): Money {
    return amount * rate
}
~~~

Formatter cần xử lý parameter list, return type và body.

### 10.3. Rule

~~~text
rule "large-order" {
    when order.total >= threshold
    then applyDiscount(order, rate)
}
~~~

Có thể quy định vị trí when/then và cách ngắt condition dài.

### 10.4. Object và record

~~~text
Customer {
    id = "C-100"
    name = "An"
    active = true
}
~~~

Thứ tự property có thể được giữ nguyên vì thứ tự có thể mang ý nghĩa hoặc giúp người dùng theo dõi diff.

### 10.5. Collection

~~~text
supportedCountries = [
    "VN",
    "SG",
    "TH"
]
~~~

Formatter có thể giữ collection ngắn trên một dòng và chuyển collection dài thành nhiều dòng.

### 10.6. Query và embedded language

Nếu DSL có query block, formatter cần biết phần nào thuộc host DSL và phần nào thuộc SQL hoặc ngôn ngữ nhúng. Có thể dùng formatter riêng cho embedded language, nhưng phải giữ mapping vị trí về source gốc.

## 11. Cấu hình formatter

Formatter nên hỗ trợ project-level configuration để cả nhóm dùng chung style.

Một cấu hình minh họa:

~~~yaml
formatter:
  indentSize: 4
  useTabs: false
  lineWidth: 100
  lineEnding: lf
  braceStyle: sameLine
  blankLinesBetweenRules: 1
  trailingComma: multiline
  formatComments: false
~~~

Tên field và cú pháp phụ thuộc implementation. Cần định nghĩa:
- Default values.
- Giá trị hợp lệ và giới hạn.
- Cách kế thừa config từ thư mục cha.
- Config riêng theo file hoặc module.
- Thứ tự ưu tiên giữa project, workspace và user settings.
- Cách xử lý option không còn được hỗ trợ.

### 11.1. Project config và user config

Project config nên chứa quy tắc chia sẻ, như indentation, line width và brace style. User config có thể điều chỉnh trải nghiệm cá nhân, nhưng nếu muốn format nhất quán trong CI thì project config cần có quyền ưu tiên rõ ràng.

### 11.2. EditorConfig

Nếu hệ sinh thái hỗ trợ EditorConfig, formatter có thể đọc các quy tắc chung như indent size, indent style và end-of-line. Các quy tắc riêng của DSL vẫn cần config chuyên biệt.

### 11.3. Format on save

Format on save tự động chạy formatter trước khi lưu file. Cần cân nhắc:
- Chỉ format file hợp lệ hay hỗ trợ partial syntax.
- Có áp dụng cho file generated không.
- Có giữ cursor và selection không.
- Có làm thay đổi quá nhiều dòng không.
- Cách xử lý khi formatter lỗi hoặc timeout.

Format on save nên có thể bật/tắt và không được âm thầm lưu nội dung bị mất do parser recovery.

## 12. Format Document và Format Selection

### 12.1. Format Document

Format Document định dạng toàn bộ file. Đây là trường hợp dễ xác định context nhất vì formatter có thể dùng toàn bộ syntax tree và cấu trúc scope.

### 12.2. Format Selection

Format Selection chỉ định dạng vùng được chọn. Khó khăn là selection có thể bắt đầu hoặc kết thúc giữa một node, expression hoặc block.

Một chiến lược:
1. Xác định node hoặc statement nhỏ nhất bao phủ selection.
2. Mở rộng vùng đến ranh giới cú pháp an toàn.
3. Format node đó với context của parent.
4. Chỉ trả text edit trong vùng được phép nếu có thể.
5. Giữ nguyên nội dung ngoài selection.

Nếu formatter phải mở rộng selection, UI nên cho người dùng biết hoặc implementation nên chọn quy tắc không gây bất ngờ.

### 12.3. Range formatting

Language Server Protocol có request formatting theo range. Server cần:
- Nhận URI và range.
- Xác định node bao phủ range.
- Tính indentation dựa trên context trước range.
- Không làm hỏng token hoặc comment nằm ngoài.
- Trả về edits có range hợp lệ.

Range formatting không đơn giản là cắt substring rồi chạy formatter độc lập vì indentation và grammar phụ thuộc context xung quanh.

### 12.4. On-type formatting

On-type formatting chạy khi người dùng gõ ký tự như newline hoặc closing brace. Nó có thể:
- Tự indent dòng mới.
- Giảm indent khi đóng block.
- Thêm dấu cách theo cấu trúc.
- Căn continuation line.

Cần giới hạn phạm vi chỉnh sửa để không làm editor giật hoặc thay đổi nội dung người dùng vừa nhập.

## 13. Tích hợp với Language Server Protocol

Language Server Protocol (*LSP*) định nghĩa các request phổ biến:
- `textDocument/formatting`: format toàn document.
- `textDocument/rangeFormatting`: format một vùng.
- `textDocument/onTypeFormatting`: format khi gõ một ký tự nhất định.

Server nhận document URI, range và formatting options rồi trả về danh sách TextEdit.

### 13.1. TextEdit

Một TextEdit gồm:
- Range trong document hiện tại.
- New text thay thế range đó.

Server cần bảo đảm range dựa trên đúng document version và position encoding được client/server thống nhất.

### 13.2. Incremental document state

Editor có thể gửi nhiều thay đổi trong khi formatter đang chạy. Kết quả của version cũ không nên áp dụng lên version mới.

Có thể:
- Hủy request cũ.
- Gắn version vào formatting job.
- Chỉ trả edit khi version còn phù hợp.
- Yêu cầu format lại nếu document đã thay đổi.

### 13.3. Capability negotiation

Client có thể hỗ trợ document formatting, range formatting hoặc on-type formatting khác nhau. Language server cần khai báo đúng capability và không giả định editor nào cũng hỗ trợ mọi chức năng.

### 13.4. Position encoding

LSP position có thể dùng UTF-16 hoặc encoding khác đã thương lượng. Formatter cần chuyển đổi offset nội bộ sang line/character đúng, đặc biệt với Unicode ngoài BMP và ký tự kết hợp dấu.

## 14. Idempotence và tính ổn định

Một formatter nên có tính **idempotent**:

~~~text
format(format(source)) = format(source)
~~~

Sau lần format đầu, chạy lại không nên tạo thêm thay đổi.

Idempotence quan trọng vì:
- Format on save có thể chạy nhiều lần.
- CI có thể kiểm tra file đã format.
- Nhiều developer dùng editor khác nhau.
- File được sinh hoặc cập nhật qua automation.
- Tránh diff lặp lại giữa các commit.

### 14.1. Deterministic output

Cùng source và cùng config nên tạo cùng output. Không nên phụ thuộc:
- Thứ tự iteration không ổn định.
- Locale của máy.
- Hệ điều hành nếu newline đã được cấu hình.
- Thời gian hoặc random.
- Phiên bản formatter không được cố định.

### 14.2. Canonical formatting

Một style guide có thể định nghĩa một canonical form cho mỗi cấu trúc. Khi đó formatter chuẩn hóa mọi cách viết hợp lệ về một cách trình bày.

Canonical form giúp giảm diff nhưng cần cân nhắc source có nhiều comment, embedded language hoặc syntax chưa hoàn chỉnh.

### 14.3. Formatter version

Thay đổi formatter version có thể làm toàn bộ project xuất hiện diff lớn. Nên version formatter hoặc config, thông báo thay đổi style và có thể chạy format migration trong một commit riêng.

## 15. Bảo toàn ngữ nghĩa

Formatter phải bảo đảm văn bản sau format có cùng semantics với văn bản trước format.

Các điều kiện cần giữ:
- Cùng AST hoặc cùng semantic model theo định nghĩa DSL.
- Cùng literal values.
- Cùng thứ tự statement nếu thứ tự có ý nghĩa.
- Cùng binding của identifier.
- Cùng precedence và associativity.
- Cùng comment directive và annotation.
- Cùng ranh giới statement.
- Cùng embedded language content nếu không có formatter chuyên biệt.

### 15.1. Parentheses

Formatter không nên xóa parentheses chỉ vì expression có vẻ đơn giản. Parentheses có thể cần thiết để thể hiện ý định hoặc có thể ảnh hưởng parsing trong DSL đặc biệt.

Nếu có tùy chọn loại bỏ ngoặc dư, cần dựa trên AST và operator precedence, đồng thời bảo đảm round-trip semantics.

### 15.2. Operator precedence

Ví dụ:

~~~text
result = a + b * c
~~~

Không được đổi thành:

~~~text
result = (a + b) * c
~~~

vì kết quả có thể khác. Formatter có thể thêm parentheses để rõ ràng nếu chúng không làm đổi binding, nhưng không nên tái cấu trúc biểu thức tùy tiện.

### 15.3. Comments có semantics

Một số comment là directive, chẳng hạn suppression, region, code generation marker hoặc annotation. Chúng phải được xem là syntax có ý nghĩa đối với toolchain và giữ đúng vị trí.

### 15.4. Kiểm tra round-trip

Có thể kiểm tra:
1. Parse source thành semantic model A.
2. Format source.
3. Parse output thành semantic model B.
4. So sánh A và B theo semantics được DSL định nghĩa.

Không nhất thiết so sánh byte-for-byte AST vì source locations và trivia sẽ khác. Cần so sánh cấu trúc và binding có ý nghĩa.

## 16. Xử lý source không hợp lệ hoặc chưa hoàn chỉnh

Người dùng thường gọi formatter khi đang viết dở. Ví dụ:

~~~text
rule "discount" {
    when order.total >
~~~

Parser có thể chưa tạo được cây hoàn chỉnh.

Các chiến lược:
- **Strict mode:** không format nếu có syntax error.
- **Partial formatting:** format các node hoàn chỉnh, giữ nguyên vùng lỗi.
- **Recovery formatting:** dùng recovery tree để format phần có thể hiểu.
- **Selection formatting:** chỉ format một vùng hợp lệ được chọn.

Cần tránh xóa hoặc di chuyển phần source chưa parse được. Nếu formatter không thể bảo đảm giữ nội dung, nên trả lỗi rõ thay vì tạo output có thể mất dữ liệu.

### 16.1. Error nodes

CST/AST có thể chứa error node và token không hợp lệ. Formatter có thể in lại lexeme gốc của vùng đó và không áp dụng quy tắc sâu vào bên trong.

### 16.2. Editor buffer chưa save

Formatter cần làm việc trên nội dung buffer mới nhất, không đọc lại file trên disk rồi ghi đè các thay đổi chưa save.

### 16.3. Cancellation và timeout

Format request cần hỗ trợ cancellation khi document thay đổi hoặc người dùng tiếp tục thao tác. Formatter phải giới hạn thời gian và bộ nhớ cho file lớn hoặc syntax bất thường.

## 17. Giữ ổn định diff và trải nghiệm người dùng

Formatter thường thay đổi nhiều whitespace. Nếu thuật toán không ổn định, một thay đổi nhỏ có thể làm cả file bị reflow.

Các nguyên tắc:
- Chỉ thay đổi vùng cần thiết.
- Giữ thứ tự declaration và collection trừ khi DSL quy định khác.
- Không tự sắp xếp import nếu sorting là một chức năng riêng.
- Giữ line ending theo project config.
- Không thay đổi quote hoặc numeric representation ngoài policy.
- Tạo minimal text edits khi editor cần bảo toàn cursor.
- Hạn chế reflow toàn bộ comment hoặc string.

### 17.1. Minimal edits

Thay vì trả toàn bộ file mới, formatter có thể tính diff và trả các vùng thay đổi nhỏ. Điều này giúp editor giữ selection, undo history và cursor tốt hơn.

Tuy nhiên, quá nhiều edit nhỏ có thể tốn chi phí. Cần cân bằng giữa số edit và kích thước vùng thay thế.

### 17.2. Cursor mapping

Sau khi format, vị trí cursor có thể cần được ánh xạ từ source sang output. Editor có thể dùng edit ranges để cập nhật selection, nhưng formatter có thể cung cấp mapping bổ sung nếu layout thay đổi đáng kể.

### 17.3. Undo

Format là một thao tác chỉnh sửa. Nên được ghi thành một undo step hợp lý để người dùng có thể hoàn tác toàn bộ lần format.

## 18. Hiệu năng và khả năng mở rộng

Formatter thường chạy trong editor nên độ trễ ảnh hưởng trực tiếp trải nghiệm.

Các điểm cần cân nhắc:
- Reuse parse tree nếu document version chưa đổi.
- Dùng incremental parsing cho file lớn.
- Chỉ format vùng cần thiết khi có thể.
- Cache config đã resolve.
- Tránh tạo quá nhiều object trung gian.
- Giới hạn độ sâu đệ quy trên AST.
- Dùng thuật toán layout có giới hạn thời gian.
- Hỗ trợ cancellation.
- Tránh format đồng thời nhiều lần trên cùng document version.
- Đo p50/p95 formatting latency và memory.

Với file nhỏ, parse lại toàn bộ có thể đơn giản và đủ nhanh. Với workspace lớn hoặc editor realtime, incremental parsing và range formatting có thể cải thiện đáng kể.

### 18.1. Worst-case behavior

Formatter cần xử lý:
- Expression lồng sâu.
- Collection rất lớn.
- Comment nhiều dòng dài.
- String dài.
- File có nhiều error nodes.
- Syntax gây nhiều lựa chọn line break.

Một thuật toán layout không kiểm soát có thể thử quá nhiều tổ hợp. Có thể giới hạn search, dùng greedy layout hoặc dynamic programming có giới hạn để giữ latency dự đoán được.

### 18.2. Background execution

Format Document thường là thao tác explicit, nhưng Format on Save có thể chạy trong save pipeline. Cần tránh block UI thread và xử lý kết quả khi document version đã thay đổi.

## 19. Kiểm thử formatter

### 19.1. Golden tests

Mỗi test gồm:
- Input source.
- Formatting options.
- Expected output.

Ví dụ:

Input:

~~~text
rule "x"{when a==1 then run()}
~~~

Expected:

~~~text
rule "x" {
    when a == 1
    then run()
}
~~~

Golden tests hữu ích để xác nhận quy tắc layout và phát hiện thay đổi ngoài ý muốn.

### 19.2. Idempotence tests

Với mỗi input:

~~~text
once = format(source)
twice = format(once)

assert twice == once
~~~

Đây là một thuộc tính quan trọng của formatter.

### 19.3. Semantic preservation tests

Parse source và formatted output, sau đó so sánh semantic model:
- Identifier bindings.
- Expression structure.
- Literal values.
- Statement order.
- Rule conditions.
- Comment directives.
- Embedded language content.

### 19.4. Comment preservation tests

Kiểm tra:
- Leading comment.
- Trailing comment.
- Inline comment.
- Block comment.
- Documentation comment.
- Directive comment.
- Comment cạnh error node.

### 19.5. Range formatting tests

Kiểm tra selection:
- Bên trong expression.
- Bao trọn một statement.
- Bắt đầu giữa token.
- Cắt qua nhiều block.
- Có comment ở ranh giới.
- Có indentation từ parent context.

Xác nhận nội dung ngoài vùng edit không bị thay đổi.

### 19.6. Unicode và newline tests

Dùng source chứa:
- Tiếng Việt có dấu.
- Ký tự ngoài BMP.
- CRLF và LF.
- Tab.
- Combining characters.
- String có escape và raw content.

Xác nhận position, range và line ending đúng.

### 19.7. Fuzz và property-based tests

Sinh syntax tree hoặc source ngẫu nhiên để kiểm tra:
- Formatter không crash.
- Không lặp vô hạn.
- Output parse được nếu input hợp lệ.
- Idempotence được giữ.
- Literal và comment được bảo toàn theo policy.
- Không làm thay đổi semantic model.
- Cancellation kết thúc công việc đúng cách.

## 20. Format on Save và kiểm tra trong CI

### 20.1. Format on Save

Editor có thể gọi formatter trước khi ghi file. Cần xác định:
- Formatter lỗi thì save có tiếp tục không?
- Có format selection hay toàn file?
- Có chỉ format file được hỗ trợ?
- Có giữ encoding và newline không?
- Có áp dụng project config không?

Nếu formatter thất bại, hành vi thường nên có thể dự đoán: hiển thị lỗi và giữ buffer, hoặc cho phép save theo policy của editor.

### 20.2. CI format check

CI có thể chạy formatter ở chế độ check:
- Không ghi file.
- Tính output chuẩn.
- So sánh với source trong repository.
- Báo file chưa được format.

Lệnh check giúp nhóm giữ style nhất quán mà không cần CI tự sửa commit của người dùng.

### 20.3. Formatter migration

Khi đổi style hoặc version formatter, nên:
1. Cố định version mới.
2. Chạy format trên branch riêng.
3. Review diff toàn bộ.
4. Tách commit format khỏi thay đổi logic.
5. Cập nhật editor config và CI.
6. Thông báo quy ước mới cho nhóm.

## 21. Kiến trúc formatter cho DSL editor

Một kiến trúc khái niệm:

~~~text
Editor
  |
  v
Formatting Request
  |
  v
Document Snapshot + Config
  |
  v
Parser / CST / AST
  |
  v
Trivia & Comment Attachment
  |
  v
Document Model Builder
  |
  v
Layout Engine
  |
  v
Text Renderer
  |
  v
Text Edits
  |
  v
Editor Buffer
~~~

Các thành phần:
- **Formatting request handler:** nhận document, range và options.
- **Document snapshot:** cố định nội dung và version dùng cho lần format.
- **Parser:** cung cấp cấu trúc cú pháp.
- **Trivia manager:** giữ comment và whitespace có ý nghĩa.
- **Document builder:** chuyển syntax node thành layout document.
- **Layout engine:** quyết định line breaks và indentation.
- **Renderer:** tạo output text.
- **Edit generator:** tạo TextEdit hoặc diff.
- **Config resolver:** xác định style áp dụng cho file.

Tách các thành phần giúp có thể dùng cùng layout engine cho Format Document, Format Selection, CLI và CI.

## 22. Những sai lầm thường gặp

1. **Dùng regex trên toàn file:** thay đổi nhầm string, comment hoặc embedded language.
2. **Chỉ dùng AST đã bỏ trivia:** làm mất comment và token cần giữ.
3. **Không có style specification:** output khác nhau giữa các môi trường.
4. **Không giữ newline semantics:** ghép hoặc tách statement làm đổi parsing.
5. **Tự chuẩn hóa literal:** thay đổi escape, số hoặc quote không an toàn.
6. **Không bảo toàn comment directive:** làm thay đổi hành vi toolchain.
7. **Format vùng chọn như file độc lập:** indentation và context sai.
8. **Không có idempotence:** mỗi lần format lại tạo diff mới.
9. **Không xử lý syntax lỗi:** có thể xóa nội dung người dùng đang viết.
10. **Không quản lý document version:** áp dụng kết quả cũ lên buffer mới.
11. **Không hỗ trợ cancellation:** editor bị chậm khi file lớn hoặc request cũ.
12. **Không kiểm tra semantics:** output đẹp nhưng có thể đổi ý nghĩa.
13. **Format on Save không kiểm soát:** save có thể gây thay đổi lớn bất ngờ.
14. **Không version formatter:** nâng cấp tool làm toàn bộ project đổi layout không có kế hoạch.

## 23. Quy trình xây dựng formatter cho DSL

Có thể triển khai theo các bước:

1. **Định nghĩa style guide:** indentation, line width, braces, operators, comments và newline.
2. **Xác định grammar và token model:** biết node nào có thể format và token nào phải bảo toàn.
3. **Chọn CST/AST strategy:** giữ đủ source positions, comments và trivia.
4. **Thiết kế document representation:** Text, Line, Group, Indent và Break.
5. **Viết formatter theo node type:** declaration, expression, block, rule, collection và embedded language.
6. **Xây layout engine:** quyết định line break dựa trên width và cấu trúc.
7. **Thiết kế comment attachment:** giữ leading, trailing, inline và directive comments.
8. **Bảo toàn semantics:** literal, operator precedence, statement order và reference binding.
9. **Hỗ trợ editor features:** document, range và on-type formatting.
10. **Tích hợp config:** project settings, editor options và version.
11. **Xử lý lỗi:** partial formatting, error nodes, cancellation và timeout.
12. **Tạo text edits:** giữ cursor, selection và undo history.
13. **Viết tests:** golden, idempotence, semantic preservation, comments, Unicode và range.
14. **Tích hợp CI:** check mode và formatter version cố định.
15. **Đo hiệu năng:** file lớn, syntax lồng sâu và thao tác realtime.

## 24. Kết luận

Formatter trong DSL editor tự động chuẩn hóa cách trình bày source dựa trên cấu trúc cú pháp và một bộ quy tắc style. Nó giúp source dễ đọc, diff ổn định và quy ước của nhóm được áp dụng nhất quán.

Một formatter đáng tin cậy cần hiểu grammar, giữ comment và trivia, bảo toàn literal và semantics, xử lý newline đúng, hỗ trợ document/range/on-type formatting và tạo output idempotent. Khi kết hợp document versioning, cancellation, configuration, text edits và bộ kiểm thử phù hợp, formatter có thể tích hợp vào editor, Format on Save và CI mà không làm thay đổi ý nghĩa của DSL.


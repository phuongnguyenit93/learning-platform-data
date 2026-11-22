# Thiết kế cú pháp cho DSL

Cú pháp là phần người dùng nhìn thấy và viết trực tiếp khi sử dụng một DSL (*Domain-Specific Language*). Nó quyết định cách biểu diễn biểu thức, câu lệnh, khai báo, dữ liệu và cấu trúc nghiệp vụ. Một cú pháp tốt giúp người dùng diễn đạt đúng ý định, đọc lại chương trình dễ dàng và nhận biết lỗi nhanh chóng.

**Thiết kế cú pháp** (*syntax design*) là quá trình lựa chọn ký hiệu, từ khóa, cấu trúc câu lệnh, quy tắc kết hợp và cách tổ chức chương trình để biểu diễn các khái niệm của domain. Công việc này bao gồm cả lexical syntax như identifier, literal và comment, lẫn grammar syntax như expression, statement, block và declaration.

Ví dụ, cùng một quy tắc giảm giá có thể được biểu diễn theo nhiều cách:

```text
if order.total >= 1000000 then order.discount = 0.1
```

Hoặc:

```text
rule "large-order-discount" {
    when order.total >= 1000000
    then order.discount = 0.1
}
```

Hoặc dạng khai báo:

```text
discount "large-order" {
    threshold: 1000000
    rate: 10%
}
```

Mỗi cách có ưu điểm khác nhau. Cú pháp thứ nhất ngắn gọn, cách thứ hai thể hiện rõ điều kiện và hành động, cách thứ ba gần với cấu hình nghiệp vụ. Việc lựa chọn cần dựa trên mục tiêu, người dùng, độ phức tạp và cách DSL sẽ được mở rộng.

## 1. Mục tiêu của thiết kế cú pháp

Một DSL thường có nhóm người dùng và domain cụ thể. Cú pháp nên hỗ trợ họ biểu đạt công việc tự nhiên, nhưng vẫn đủ chính xác để parser và runtime hiểu một nghĩa duy nhất.

Các mục tiêu chính:

- **Readability:** chương trình dễ đọc và dễ review.
- **Writability:** người dùng có thể viết mà không phải nhớ quá nhiều ký hiệu.
- **Consistency:** cùng một khái niệm được viết theo cùng một quy tắc.
- **Unambiguity:** một chương trình hợp lệ có cách parse rõ ràng.
- **Error locality:** lỗi được phát hiện gần vị trí gây ra.
- **Extensibility:** có thể thêm tính năng mà không phá cấu trúc cũ.
- **Toolability:** hỗ trợ formatter, editor, completion và source mapping.
- **Domain fit:** từ vựng và cấu trúc phản ánh khái niệm nghiệp vụ.
- **Compatibility:** thay đổi cú pháp có thể được version hóa và migration.

Không thể tối đa hóa tất cả mục tiêu cùng lúc. Ví dụ, cú pháp rất ngắn có thể khó đọc; cú pháp rất tường minh có thể dài. Thiết kế cần cân bằng theo người dùng và loại chương trình.

## 2. Bắt đầu từ domain và người dùng

Trước khi chọn ký hiệu, hãy xác định ai sẽ viết DSL và họ đang giải quyết công việc nào.

Người dùng có thể là:

- Developer tích hợp DSL vào ứng dụng.
- Chuyên gia nghiệp vụ viết rule.
- Data analyst tạo query.
- Operator cấu hình workflow.
- Administrator quản lý policy.
- Người dùng cuối chỉnh sửa template đơn giản.

Mỗi nhóm có mức độ quen thuộc với lập trình khác nhau. Một DSL dành cho developer có thể dùng expression, generic type và function call. Một DSL cho chuyên gia nghiệp vụ có thể ưu tiên block khai báo, vocabulary domain và form-based editing.

### Task analysis

Thu thập các tác vụ phổ biến:

- Viết một điều kiện.
- Kết hợp nhiều điều kiện.
- Khai báo biến.
- Gọi hàm.
- Định nghĩa rule.
- Xử lý ngoại lệ.
- Import module.
- Cấu hình output.
- Đọc lỗi và sửa source.

Từ mỗi tác vụ, tạo ví dụ ngắn. Những cấu trúc xuất hiện thường xuyên nên có cú pháp thuận tiện và nhất quán.

## 3. Chọn phong cách cú pháp

Một số phong cách thường gặp.

### Cú pháp dạng expression

Phù hợp khi DSL chủ yếu mô tả công thức hoặc phép tính:

```text
price * quantity * (1 - discountRate)
```

Ưu điểm là ngắn và dễ kết hợp với host language. Hạn chế là khó biểu diễn workflow hoặc nhiều bước có trạng thái.

### Cú pháp dạng statement

Phù hợp khi có sequence, assignment và control flow:

```text
let total = price * quantity
if total > limit {
    approve()
}
```

### Cú pháp dạng block khai báo

Phù hợp cho rule, policy và cấu hình:

```text
policy "refund" {
    condition: order.status == "delivered"
    within: 30 days
    result: "eligible"
}
```

### Cú pháp dạng bảng

Phù hợp khi người dùng cần nhìn nhiều tổ hợp điều kiện và kết quả:

```text
decision-table "discount" {
    columns: [customerTier, orderTotal]
    rows:
      ["gold", 1000000] => 0.10
      ["silver", 2000000] => 0.05
}
```

### Cú pháp dạng pipeline

Phù hợp với transformation hoặc xử lý dữ liệu theo chuỗi:

```text
orders
    |> filter(order.total > 100000)
    |> groupBy(order.region)
    |> sum(order.total)
```

Một DSL có thể kết hợp nhiều phong cách, nhưng cần quy tắc nhất quán để người dùng không phải học nhiều cách biểu diễn cùng một khái niệm.

## 4. Từ vựng và naming conventions

Cú pháp bắt đầu từ token: keyword, identifier, operator, literal, delimiter và comment.

### Keyword

Keyword là từ dành riêng cho cấu trúc ngôn ngữ như if, rule, function, match hoặc import.

Cần quyết định keyword là:

- **Reserved:** không được dùng làm identifier.
- **Contextual:** chỉ có ý nghĩa đặc biệt trong một vị trí grammar nhất định.

Reserved keyword giúp parser đơn giản nhưng làm giảm không gian tên của người dùng. Contextual keyword linh hoạt hơn nhưng có thể làm grammar phức tạp.

### Identifier

Identifier cần có quy tắc về:

- Ký tự bắt đầu.
- Ký tự tiếp theo.
- Unicode.
- Phân biệt hoa/thường.
- Quy tắc normalization.
- Reserved words.
- Naming convention.

Ví dụ, DSL có thể dùng camelCase cho variable và PascalCase cho type, hoặc để người dùng tự chọn nhưng formatter chuẩn hóa.

### Naming consistency

Nếu một cấu trúc dùng when/then, không nên dùng condition/action cho cùng ý nghĩa ở một nơi khác mà không có lý do. Từ khóa cần có semantics ổn định và dễ dự đoán.

## 5. Literal và cách biểu diễn giá trị

Literal là giá trị được viết trực tiếp trong source.

Các loại phổ biến:

```text
42
3.1415
true
false
"hello"
'text'
null
[1, 2, 3]
{ name: "Ada", active: true }
```

Cần xác định:

- Integer literal hỗ trợ decimal, hexadecimal hay binary?
- Numeric separator có được phép không?
- Decimal có suffix hoặc scale không?
- String dùng dấu nháy đơn, đôi hay cả hai?
- Escape sequence gồm những gì?
- Multiline string được viết thế nào?
- Date/time literal có format nào?
- Collection literal phân biệt list và set ra sao?
- Object literal có cho phép key không quoted không?

### Numeric literals

Ví dụ:

```text
1000
1_000
0xFF
12.50
1.25e3
```

Nếu hỗ trợ nhiều dạng, parser và formatter cần thống nhất cách hiển thị. Với DSL tài chính, Decimal literal cần có semantics rõ về precision và rounding.

### String literals

String syntax cần xác định escape cho quote, newline, tab, Unicode và backslash. Nếu hỗ trợ raw string hoặc template string, cần tránh ambiguity với các delimiter khác.

## 6. Operator và ký hiệu

Operator biểu diễn phép toán hoặc quan hệ.

Các nhóm thường gặp:

- Arithmetic: +, -, *, /, %.
- Comparison: ==, !=, <, <=, >, >=.
- Logical: and, or, not.
- Assignment: =, +=.
- Membership: in.
- Null handling: ??, ?.
- Pipeline: |>.
- Range: .. hoặc ..=.

Không nên chọn ký hiệu chỉ vì ngắn. Operator cần dễ đọc, không xung đột với token khác và phù hợp với domain.

### Word operators và symbolic operators

So sánh:

```text
isActive and hasPermission
```

với:

```text
isActive && hasPermission
```

Từ khóa and dễ đọc với người dùng nghiệp vụ. Ký hiệu && quen thuộc với developer. Một DSL có thể hỗ trợ một hoặc cả hai, nhưng nếu hỗ trợ cả hai thì cần định nghĩa chính xác và formatter nên chọn một dạng canonical.

## 7. Precedence và associativity

Khi một expression có nhiều operator, parser cần biết operator nào được nhóm trước.

Ví dụ:

```text
2 + 3 * 4
```

Nếu multiplication có precedence cao hơn addition, kết quả là 14.

Associativity xác định cách nhóm các operator cùng precedence:

```text
20 - 5 - 2
```

Nếu phép trừ kết hợp trái, biểu thức là (20 - 5) - 2 và kết quả bằng 13. Nếu kết hợp phải, kết quả sẽ khác.

Một bảng precedence có thể là:

| Mức | Operator | Associativity |
|---:|---|---|
| Cao | Function call, member access | Trái |
|  | Unary +, -, not | Phải |
|  | *, /, % | Trái |
|  | +, - | Trái |
|  | <, <=, >, >= | Không kết hợp hoặc theo policy |
|  | ==, != | Không kết hợp hoặc theo policy |
|  | and | Trái |
| Thấp | or | Trái |

Bảng thực tế cần phù hợp với grammar của DSL. Không nên để cùng một operator có precedence khác nhau ở những context không rõ ràng.

### Parentheses

Parentheses cho phép người dùng biểu diễn grouping tường minh:

```text
(2 + 3) * 4
```

Cần hỗ trợ parentheses nhất quán trong expression và tránh để chúng có nghĩa khác nhau ở các construct không liên quan.

## 8. Grammar và cấu trúc câu lệnh

Grammar định nghĩa cách token kết hợp thành chương trình.

Một grammar nhỏ có thể bắt đầu từ:

```text
Program     ::= Statement*
Statement   ::= LetStatement | IfStatement | ExpressionStatement
LetStatement ::= "let" Identifier "=" Expression
IfStatement ::= "if" Expression Block ("else" Block)?
Block       ::= "{" Statement* "}"
```

Grammar nên phản ánh syntax đã được quyết định, không nên cố nhồi mọi semantics vào parser. Các quy tắc về tên tồn tại, type compatibility hoặc quyền truy cập thường thuộc semantic analysis.

### Expression grammar

Expression grammar cần xử lý precedence và associativity. Có thể dùng precedence climbing, Pratt parser hoặc grammar phân tầng theo operator levels.

### Statement grammar

Statement thường có side effect hoặc điều khiển luồng. Cần phân biệt expression trả value với statement chỉ thực hiện hành động nếu điều đó quan trọng với type system.

## 9. Delimiters và block structure

DSL có thể dùng braces, indentation hoặc keyword kết thúc block.

### Braces

```text
if condition {
    approve()
} else {
    reject()
}
```

Ưu điểm là cấu trúc rõ và ít phụ thuộc whitespace. Hạn chế là nhiều dấu ngoặc có thể làm code dài.

### Indentation-sensitive syntax

```text
if condition:
    approve()
else:
    reject()
```

Ưu điểm là gần với cách trình bày tự nhiên và giảm dấu ngoặc. Hạn chế là lexer cần xử lý INDENT/DEDENT, tab và spaces.

### Keyword delimiters

```text
if condition then
    approve()
else
    reject()
end
```

Cách này tường minh nhưng có thể dài khi nesting nhiều.

Chọn một mô hình block chính và quy định rõ newline, semicolon, indentation và empty block. Trộn nhiều mô hình mà không có quy tắc nhất quán sẽ làm người dùng khó đoán parser.

## 10. Whitespace, newline và semicolon

Cần quyết định whitespace có ý nghĩa hay chỉ dùng để tách token.

Các câu hỏi:

- Newline có kết thúc statement không?
- Có cần semicolon không?
- Có cho phép nhiều statement trên một dòng không?
- Continuation line được nhận diện thế nào?
- Tab và spaces có tương đương không?
- Blank line có ý nghĩa không?
- Comment có ảnh hưởng newline handling không?

Ví dụ:

```text
let total = price * quantity
let tax = total * 0.1
```

Nếu newline kết thúc statement, parser cần quy tắc continuation khi expression kéo dài qua nhiều dòng.

Không nên để một newline tùy ý làm thay đổi semantics nếu người dùng có thể format lại code mà không nhận ra.

## 11. Comments và documentation syntax

Comment giúp giải thích ý định mà không ảnh hưởng execution.

Các kiểu thường gặp:

```text
// Comment một dòng

# Comment theo phong cách shell

/*
   Comment nhiều dòng
*/
```

Không nhất thiết hỗ trợ mọi kiểu. Chọn một quy ước nhất quán và xác định comment có thể lồng nhau hay không.

Documentation comment có thể gắn với declaration:

```text
/// Tính phí giao hàng theo khu vực.
function shippingFee(order: Order): Money {
    ...
}
```

Nếu hỗ trợ documentation comments, cần định nghĩa cách liên kết comment với declaration và cách sinh API reference.

## 12. Syntax cho declaration, function và module

DSL có thể cần khai báo biến, function, type, module hoặc rule.

Ví dụ:

```text
let taxRate: Decimal = 0.1

function finalPrice(base: Decimal): Decimal {
    return base * (1 + taxRate)
}

module pricing {
    export function quote(order: Order): Money {
        ...
    }
}
```

Cần nhất quán về:

- Thứ tự tên, type và parameter.
- Dấu phân cách giữa parameter.
- Required/default argument.
- Return type.
- Visibility.
- Export/import.
- Generic parameter.
- Annotation hoặc metadata.
- Body expression hay block.

Nếu DSL chỉ dành cho cấu hình, có thể không cần function hoặc module đầy đủ. Tránh thêm construct chỉ vì ngôn ngữ lập trình tổng quát thường có chúng.

## 13. Syntax cho domain constructs

Một DSL có thể có construct chuyên biệt như rule, workflow, query hoặc policy.

Ví dụ rule:

```text
rule "high-risk-order" {
    when order.riskScore >= 80
    then requireManualReview()
}
```

Ví dụ workflow:

```text
workflow "refund" {
    start
    validate request
    approve by role("supervisor")
    execute refund
}
```

Ví dụ query:

```text
from orders
where total >= 1000000
select customerId, total
order by total desc
```

Domain construct nên làm nổi bật khái niệm quan trọng và giảm boilerplate. Nhưng cần giữ semantics rõ: thứ tự thực thi, default behavior, error path, permission và output type.

## 14. Syntax cho type và schema

Nếu DSL có type system, syntax cần mô tả type rõ ràng mà không gây quá nhiều nhiễu.

Ví dụ:

```text
type Customer {
    id: UUID
    name: String
    creditLimit: Decimal?
}
```

Cần xác định cách viết:

- Primitive type.
- Optional và nullable type.
- Generic type.
- Union và intersection.
- Record và tuple.
- Enum.
- Function type.
- Type alias.
- Constraint như min/max hoặc pattern.

Không nên để cùng một dấu ? có nhiều nghĩa khó phân biệt, chẳng hạn vừa optional field vừa nullable type mà không có quy tắc rõ.

## 15. Syntax cho pattern matching và destructuring

Pattern matching giúp xử lý nhiều dạng dữ liệu theo cấu trúc.

Ví dụ:

```text
match result {
    case Success(value) => process(value)
    case Failure(error) => report(error)
}
```

Cần xác định:

- Pattern có exhaustive không?
- Case được đánh giá theo thứ tự nào?
- Có guard condition không?
- Wildcard pattern viết thế nào?
- Destructuring có tạo binding mới không?
- Pattern có thể gọi function không?
- Có cho phép pattern trùng hoặc unreachable không?

Syntax nên làm rõ khác biệt giữa pattern binding và expression comparison.

## 16. Annotation và metadata

Annotation có thể bổ sung metadata mà không làm thay đổi cấu trúc chính.

Ví dụ:

```text
@Deprecated(replacement = "dateFromParts")
function legacyDate(year, month, day)

@RequiresRole("finance-manager")
rule "approve-expense" {
    ...
}
```

Cần xác định annotation áp dụng lên declaration nào, thứ tự annotation, cách truyền argument và annotation nào được compiler kiểm tra.

Không nên dùng annotation để giấu một phần lớn semantics. Nếu behavior quan trọng, nên thể hiện bằng construct hoặc metadata rõ ràng có documentation.

## 17. Error recovery và diagnostics

Syntax design cần tính đến trường hợp người dùng đang viết dở hoặc viết sai.

Ví dụ:

```text
rule "discount" {
    when order.total >=
    then outcome "discount"
}
```

Parser nên có khả năng phát diagnostic tại vị trí gần lỗi và tiếp tục phân tích phần sau nếu có thể.

Một diagnostic tốt thường có:

- Error code ổn định.
- Severity.
- Source range.
- Expected token hoặc construct.
- Actual token nếu phù hợp.
- Gợi ý sửa khi có cơ sở.
- Context đủ để editor hiển thị.

Error recovery cần tránh tạo quá nhiều lỗi dây chuyền từ một lỗi gốc. Nếu thiếu dấu đóng block, parser có thể đồng bộ tại keyword hoặc delimiter tiếp theo theo quy tắc đã thiết kế.

## 18. Syntax và tooling

Cú pháp không chỉ được dùng trong parser. Nó còn được sử dụng bởi:

- Syntax highlighting.
- Auto-completion.
- Formatter.
- Language server.
- Go to definition.
- Rename symbol.
- Refactoring.
- Debugger.
- Source maps.
- Documentation generator.

Một cú pháp quá phụ thuộc ngữ cảnh có thể khó highlight hoặc completion. Một cấu trúc có nhiều cách viết tương đương có thể làm formatter khó tạo output canonical.

### Formatter

Formatter nên tạo một dạng trình bày chuẩn:

- Indentation.
- Spaces quanh operator.
- Line breaks.
- Quote style.
- Trailing comma.
- Ordering nếu semantics cho phép.
- Parentheses cần thiết.

Formatter không được thay đổi semantics. Nếu có nhiều cách viết hợp lệ, formatter giúp giảm khác biệt không cần thiết trong code review.

## 19. Unicode và identifier

DSL có thể cho phép identifier Unicode để hỗ trợ domain hoặc ngôn ngữ tự nhiên. Cần quy định:

- Ký tự nào hợp lệ ở đầu và giữa identifier.
- Có normalize Unicode không.
- Identifier có phân biệt hoa/thường không.
- Có cho phép chữ có dấu không.
- Confusable characters được xử lý ra sao.
- Source offset tính theo byte, code point hay UTF-16 unit.
- Formatter và language server dùng cùng quy ước không.

Ví dụ:

```text
let kháchHàng = customer
let giáTrị = 100
```

Unicode identifier có thể cải thiện trải nghiệm cho một số nhóm, nhưng cũng tạo rủi ro nhầm ký tự giống hình dạng. Với DSL có yêu cầu bảo mật cao, có thể cần cảnh báo confusable identifier hoặc giới hạn script mixing.

## 20. Syntax evolution và compatibility

Sau khi phát hành, syntax trở thành contract mà chương trình cũ phụ thuộc.

Khi thay đổi, cần xem:

- Keyword mới có trùng identifier cũ không?
- Operator mới có làm đổi precedence không?
- Grammar mới có parse source cũ theo cách khác không?
- Formatter có đổi output hàng loạt không?
- Có cần language version mới không?
- Có migration tool không?
- Có deprecation window không?

### Contextual keywords

Một cách giảm breaking change là dùng contextual keyword thay vì reserved keyword khi phù hợp. Tuy nhiên, cách này tăng độ phức tạp parser và có thể làm error message khó hiểu.

### Language version

Có thể gắn source với language version:

```text
language "2.5"

rule "discount" {
    ...
}
```

Compiler có thể chọn grammar và semantics tương ứng. Cần xác định default version cho source mới và cách xử lý source thiếu version metadata.

## 21. Syntax và security

Cú pháp có thể mở hoặc hạn chế khả năng của chương trình.

Các câu hỏi:

- Có cho phép dynamic evaluation không?
- Có thể gọi function tùy ý không?
- Có construct truy cập filesystem hoặc network không?
- Identifier có thể trỏ tới class hoặc module tùy ý không?
- String interpolation có thể thực thi expression không?
- Macro expansion có giới hạn không?
- Parser có giới hạn độ sâu và kích thước input không?

Một DSL an toàn thường chỉ cung cấp các construct cần thiết và để host kiểm soát capability. Cú pháp không nên vô tình mở ra reflection hoặc arbitrary code execution.

Parser cũng cần chống input quá lớn hoặc lồng nhau sâu gây stack overflow và denial of service.

## 22. So sánh syntax design alternatives

Khi có nhiều phương án, hãy ghi trade-off rõ ràng.

Ví dụ lựa chọn block syntax:

| Tiêu chí | Braces | Indentation | End keyword |
|---|---|---|---|
| Dễ parse | Thường dễ | Cần lexer xử lý indent | Tương đối dễ |
| Nhìn nesting | Rõ qua dấu ngoặc | Rõ qua thụt lề | Rõ qua end |
| Nhạy whitespace | Thấp | Cao | Thấp |
| Viết nhiều dòng | Tốt | Tốt | Có thể dài |
| Editor support | Phổ biến | Cần indent logic | Phổ biến |
| Lỗi thiếu delimiter | Thiếu brace | Sai indent | Thiếu end |

Không có lựa chọn đúng cho mọi DSL. Cần thử bằng ví dụ thật, parser prototype và editor workflow.

## 23. Prototype syntax trước khi xây compiler đầy đủ

Một prototype nhỏ có thể giúp đánh giá syntax nhanh.

Quy trình:

1. Chọn 5–10 scenario đại diện.
2. Viết 2–3 phương án syntax cho từng scenario.
3. Cho người dùng đọc và giải thích lại ý nghĩa.
4. Xác định các cách hiểu mơ hồ.
5. Viết grammar prototype.
6. Parse thành AST đơn giản.
7. Chạy formatter hoặc pretty printer.
8. Thu thập feedback và cập nhật syntax.

Prototype không cần có optimizer hoặc runtime hoàn chỉnh. Mục tiêu là kiểm tra khả năng diễn đạt, readability và parser feasibility trước khi đầu tư lớn.

## 24. Ví dụ thiết kế syntax cho rule engine

Giả sử domain cần mô tả điều kiện miễn phí giao hàng.

### Phương án A: if statement

```text
if customer.segment == "gold" and order.total >= 500000 {
    shipping.fee = 0
}
```

Phù hợp với người quen lập trình. Nhưng nếu cần priority, metadata và nhiều outcome, block có thể nhanh chóng phức tạp.

### Phương án B: rule block

```text
rule "gold-free-shipping" priority 100 {
    when customer.segment == "gold"
         and order.total >= 500000

    then {
        shipping.fee = 0
        outcome "eligible"
    }
}
```

Cấu trúc thể hiện rõ rule identity, priority, condition và action.

### Phương án C: declarative policy

```text
shippingPolicy "gold-customer" {
    appliesTo: customer.segment == "gold"
    minimumOrder: 500000
    fee: 0
}
```

Cú pháp này gần ngôn ngữ cấu hình và có thể dễ dùng hơn với người không phải developer. Nhưng biểu thức condition và khả năng mở rộng cần được thiết kế rõ.

Đánh giá các phương án bằng scenario, parser prototype, readability test, diagnostics và khả năng mở rộng trước khi chốt.

## 25. Những lỗi thường gặp khi thiết kế cú pháp

**Chọn syntax trước khi hiểu domain.** Ngôn ngữ có thể không phù hợp công việc. Thu thập scenario và vocabulary trước.

**Quá nhiều keyword.** Người dùng khó nhớ và identifier bị hạn chế. Ưu tiên identifier, schema và function cho khái niệm domain.

**Operator không nhất quán.** Cùng một ký hiệu có nhiều nghĩa không rõ. Định nghĩa precedence và context tường minh.

**Không quy định associativity.** Expression có thể được parse khác nhau. Công bố bảng precedence và test AST.

**Whitespace có semantics ngầm.** Formatter có thể vô tình đổi chương trình. Định nghĩa newline, indentation và continuation rõ.

**Trộn expression và statement tùy tiện.** Người dùng không biết construct trả value hay tạo side effect. Quy định rõ type và execution semantics.

**Không thiết kế diagnostics.** Parser chỉ báo syntax error chung chung. Dùng source range, error code và recovery strategy.

**Không thử editor.** Syntax parse được nhưng khó completion và formatting. Prototype language tooling sớm.

**Thêm reserved keyword gây breaking change.** Identifier cũ có thể không còn hợp lệ. Cân nhắc contextual keyword và language version.

**Syntax quá linh hoạt.** Nhiều cách viết tương đương làm formatter và documentation phức tạp. Định nghĩa canonical style.

**Bỏ qua Unicode.** Identifier và source range có thể sai. Định nghĩa normalization và offset convention.

**Không version hóa syntax.** Compiler mới có thể hiểu source cũ khác đi. Gắn language version và migration policy.

## 26. Quy trình thiết kế cú pháp

Có thể thực hiện theo trình tự:

1. Xác định người dùng, domain và các tác vụ chính.
2. Thu thập examples và scenario thật.
3. Xác định vocabulary và construct thường dùng.
4. Chọn phong cách expression, statement, block, table hoặc pipeline phù hợp.
5. Quy định identifier, keyword, literal và operator.
6. Thiết kế precedence, associativity và grouping.
7. Định nghĩa grammar cho declaration, statement và expression.
8. Quy định delimiter, whitespace, comment và newline.
9. Thiết kế type syntax và domain-specific constructs.
10. Tạo parser prototype và kiểm tra ambiguity.
11. Thiết kế diagnostics và error recovery.
12. Thử formatter, completion và editor experience.
13. Kiểm tra Unicode, security và resource limits.
14. Định nghĩa language version và compatibility strategy.
15. Ghi ví dụ, tài liệu và migration rules.

## 27. Câu hỏi tự kiểm tra

1. Thiết kế cú pháp cho DSL là gì và gồm những quyết định nào?
2. Readability, writability, unambiguity và extensibility có thể xung đột ra sao?
3. Reserved keyword và contextual keyword khác nhau như thế nào?
4. Identifier cần quy định những đặc tính Unicode nào?
5. Numeric và string literals cần những quy tắc gì?
6. Khi nào nên dùng word operators thay cho symbolic operators?
7. Precedence và associativity quyết định cách parse expression như thế nào?
8. Braces, indentation và end keyword có trade-off gì?
9. Grammar nên phân chia expression, statement và declaration ra sao?
10. Vì sao whitespace và newline semantics cần được xác định rõ?
11. Comment và documentation syntax nên gắn với declaration thế nào?
12. Domain-specific construct cần thể hiện metadata và execution order ra sao?
13. Optional, nullable và generic types nên được biểu diễn thế nào?
14. Error recovery giúp editor và người dùng như thế nào?
15. Formatter có thể thay đổi semantics trong trường hợp nào?
16. Unicode identifier tạo ra những vấn đề bảo mật và source mapping nào?
17. Khi nào cần tăng language version cho syntax mới?
18. Làm thế nào prototype syntax trước khi xây compiler đầy đủ?
19. Vì sao cần thử cú pháp trong editor chứ không chỉ parser?
20. Hãy thiết kế cú pháp cho một rule miễn phí giao hàng, nêu hai phương án và phân tích trade-off.

Thiết kế cú pháp là quá trình chuyển khái niệm domain thành cách viết có thể đọc, parse và phát triển lâu dài. Khi từ vựng, literal, operator, grammar, block structure, diagnostics và versioning được xác định nhất quán, DSL sẽ giúp người dùng diễn đạt ý định rõ ràng và giúp toolchain xử lý chương trình một cách dự đoán được.


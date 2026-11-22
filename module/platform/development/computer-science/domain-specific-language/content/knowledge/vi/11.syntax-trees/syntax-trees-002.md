# AST và mục đích sử dụng

Khi xây dựng một ngôn ngữ chuyên biệt theo miền (Domain-Specific Language — DSL), trình phân tích cần chuyển văn bản mà người dùng viết thành một cấu trúc mà chương trình có thể hiểu và xử lý. Một trong những cấu trúc quan trọng nhất cho công việc này là **Abstract Syntax Tree (AST)**, thường dịch là **cây cú pháp trừu tượng**.

AST biểu diễn cấu trúc và ý nghĩa cú pháp cốt lõi của chương trình bằng các nút (node) có quan hệ cha-con. Nó giữ lại những thành phần quan trọng như khai báo, biểu thức, phép toán, lời gọi hàm và điều kiện, đồng thời thường lược bỏ các chi tiết chỉ phục vụ việc viết văn bản như dấu ngoặc hoặc dấu phân cách không cần thiết cho các bước xử lý tiếp theo.

Trong DSL, AST là cầu nối giữa cú pháp mà người dùng nhìn thấy và các hoạt động như kiểm tra tên, kiểm tra kiểu, xác thực quy tắc miền, diễn giải, sinh mã, tối ưu hóa hoặc tạo công cụ hỗ trợ. AST được thiết kế tốt giúp các bước này làm việc trên một mô hình có cấu trúc thay vì phải phân tích văn bản thô lặp đi lặp lại.

## 1. AST là gì?

AST là một cấu trúc dữ liệu dạng cây mô tả các thành phần có ý nghĩa của một chương trình. Mỗi nút đại diện cho một cấu trúc cú pháp, chẳng hạn:

- Một chương trình hoặc module.
- Một khai báo entity, rule, workflow hoặc hàm.
- Một câu lệnh gán hoặc lời gọi hành động.
- Một biểu thức số học hoặc logic.
- Một phép so sánh, truy cập thuộc tính hoặc literal.

Ví dụ, biểu thức:

```text
order.total >= 1_000_000
```

có thể được biểu diễn bằng cây gồm một nút so sánh lớn hơn hoặc bằng, với hai nhánh con là truy cập thuộc tính `order.total` và literal số `1_000_000`.

```text
       GreaterThanOrEqual
          /        \\
 MemberAccess      NumberLiteral
    /    \\          1_000_000
 Identifier  Property
   order      total
```

Cây cho thấy phép so sánh có hai toán hạng. Toán hạng trái là thuộc tính `total` của đối tượng `order`; toán hạng phải là một giá trị số. Chương trình có thể đi qua cây để kiểm tra kiểu, đánh giá biểu thức hoặc chuyển nó thành một dạng khác.

AST là “trừu tượng” vì nó không cần giữ mọi ký tự trong văn bản gốc. Dấu cách, xuống dòng, dấu ngoặc dùng để nhóm biểu thức và dấu chấm phẩy có thể không xuất hiện như node riêng nếu chúng không ảnh hưởng đến cấu trúc cần xử lý. Tuy nhiên, trình biên dịch thường giữ thông tin vị trí nguồn bên cạnh node để phục vụ lỗi và công cụ biên tập.

## 2. AST nằm ở đâu trong quá trình xử lý DSL?

Một pipeline điển hình từ văn bản DSL đến kết quả thực thi có thể gồm các bước:

```text
Tệp nguồn DSL
     |
     v
Giải mã ký tự và chuẩn hóa đầu vào theo chính sách
     |
     v
Lexer: tạo token
     |
     v
Parser: phân tích cú pháp
     |
     v
Parse tree / AST
     |
     v
Phân giải tên và kiểm tra ngữ nghĩa, kiểu
     |
     v
AST đã được xác thực hoặc IR
     |
     v
Interpreter / Code generator / Optimizer
     |
     v
Kết quả thực thi hoặc chương trình đích
```

Không phải hệ thống nào cũng có đủ mọi bước hoặc dùng đúng tên như sơ đồ. Một parser có thể tạo AST trực tiếp; một hệ thống khác tạo parse tree rồi chuyển đổi thành AST. Một DSL nhỏ có thể bỏ qua IR riêng và đánh giá AST trực tiếp.

### 2.1. Lexer tạo token

Lexer (bộ phân tích từ vựng) đọc chuỗi ký tự và nhóm chúng thành token như từ khóa, identifier, literal, toán tử và dấu phân cách.

Với biểu thức:

```text
order.total >= 1_000_000
```

Lexer có thể tạo dãy token khái quát:

| Token | Nội dung |
|---|---|
| `IDENTIFIER` | `order` |
| `DOT` | `.` |
| `IDENTIFIER` | `total` |
| `GREATER_EQUAL` | `>=` |
| `NUMBER` | `1_000_000` |

Lexer không cần quyết định `order` có phải một entity đã khai báo hay `total` có tồn tại hay không. Những việc đó thuộc phân tích ngữ nghĩa sau này.

### 2.2. Parser xác định cấu trúc

Parser (bộ phân tích cú pháp) nhận token và kiểm tra chúng có tuân theo ngữ pháp DSL hay không. Nó xác định `order.total` là một biểu thức truy cập thuộc tính và toàn bộ biểu thức là một phép so sánh.

Parser cũng xử lý thứ tự ưu tiên toán tử và cách nhóm biểu thức. Ví dụ, `A or B and C` cần được phân tích theo bảng precedence mà DSL quy định. AST sẽ phản ánh cách nhóm đã được xác định.

### 2.3. AST được phân tích ngữ nghĩa

Sau khi có cấu trúc cú pháp, hệ thống có thể kiểm tra tên có tồn tại, thuộc tính có thuộc đúng kiểu, toán tử có áp dụng được và quy tắc có thỏa các ràng buộc miền hay không.

Ví dụ, biểu thức `order.total >= 1_000_000` có cú pháp hợp lệ, nhưng vẫn có thể sai ngữ nghĩa nếu `total` là kiểu `Date` hoặc `order` không có thuộc tính `total`.

## 3. AST khác gì parse tree?

Parse tree (cây phân tích cú pháp), thường còn gọi là concrete syntax tree (CST), phản ánh sát cấu trúc ngữ pháp mà parser sử dụng. AST giữ lại cấu trúc trừu tượng quan trọng cho xử lý chương trình và thường lược bỏ các nút chỉ phục vụ ngữ pháp.

Ví dụ, ngữ pháp biểu thức có thể định nghĩa:

```text
Expression  -> Expression ">=" Term
Expression  -> Term
Term        -> IDENTIFIER "." IDENTIFIER
Term        -> NUMBER
```

Parse tree có thể chứa node trung gian `Expression`, `Term`, token dấu chấm và token toán tử. AST có thể rút gọn thành `GreaterThanOrEqual(MemberAccess(...), NumberLiteral(...))`.

| Tiêu chí | Parse tree / CST | AST |
|---|---|---|
| Mục đích | Thể hiện cấu trúc theo ngữ pháp | Thể hiện cấu trúc trừu tượng của chương trình |
| Mức độ chi tiết | Thường giữ nhiều thành phần cú pháp | Chỉ giữ các thành phần cần cho xử lý |
| Node trung gian | Có thể có nhiều node tương ứng quy tắc grammar | Thường được rút gọn theo khái niệm ngôn ngữ |
| Dấu câu và dấu ngoặc | Có thể được biểu diễn rõ | Thường không cần node riêng nếu chỉ phục vụ nhóm cú pháp |
| Sử dụng | Phân tích cú pháp, formatter, công cụ cần giữ cấu trúc văn bản | Kiểm tra ngữ nghĩa, thực thi, sinh mã, tối ưu |

Ranh giới giữa CST và AST không tuyệt đối. Một số parser tạo cấu trúc vừa giữ được chi tiết nguồn vừa có node trừu tượng. Một số công cụ gọi cấu trúc của mình là AST dù vẫn lưu token và dấu câu. Điều quan trọng là hiểu thông tin nào được giữ lại và mục đích sử dụng của cấu trúc đó.

## 4. Ví dụ xây dựng AST từ một biểu thức

Giả sử DSL có biểu thức:

```text
(order.total >= 1_000_000) and (order.status == PAID)
```

Theo quy tắc precedence và dấu ngoặc, biểu thức có một nút logic AND ở gốc. Nhánh trái là phép so sánh tổng tiền; nhánh phải là phép so sánh trạng thái.

```text
                 And
                /   \\
              Gte   Equal
             /  \\   /  \\
       Member  Number Member EnumValue
        / \\    1M   / \\    PAID
     order total    order status
```

Có thể biểu diễn các node bằng kiểu dữ liệu như sau (mã giả theo phong cách Kotlin):

```kotlin
sealed interface Expr

data class Identifier(val name: String) : Expr
data class NumberLiteral(val value: Long) : Expr
data class EnumLiteral(val name: String) : Expr
data class MemberAccess(val target: Expr, val member: String) : Expr
data class Equal(val left: Expr, val right: Expr) : Expr
data class GreaterEqual(val left: Expr, val right: Expr) : Expr
data class And(val left: Expr, val right: Expr) : Expr
```

AST tương ứng có thể được tạo bằng cách lồng các đối tượng:

```kotlin
val condition = And(
    left = GreaterEqual(
        left = MemberAccess(Identifier("order"), "total"),
        right = NumberLiteral(1_000_000)
    ),
    right = Equal(
        left = MemberAccess(Identifier("order"), "status"),
        right = EnumLiteral("PAID")
    )
)
```

Ví dụ trên minh họa cấu trúc node; parser thực tế sẽ tự tạo chúng từ token thay vì lập trình viên viết cây thủ công. Sau đó, các bước khác có thể duyệt `condition` để kiểm tra kiểu hoặc đánh giá kết quả.

## 5. Thiết kế node của AST

AST cần phản ánh những khái niệm mà DSL hỗ trợ. Nếu DSL dùng để mô tả quy tắc nghiệp vụ, node có thể gồm `RuleDeclaration`, `Condition`, `Action`, `EntityReference` và các loại biểu thức. Nếu DSL dùng để truy vấn, node có thể gồm `Select`, `From`, `Join`, `Filter`, `GroupBy` và `Sort`.

### 5.1. Node chương trình và node câu lệnh

Một mô hình thường có node gốc đại diện cho chương trình hoặc module, bên dưới là danh sách khai báo:

```kotlin
data class Program(val declarations: List<Declaration>)

sealed interface Declaration
data class EntityDeclaration(
    val name: String,
    val attributes: List<AttributeDeclaration>
) : Declaration

data class RuleDeclaration(
    val name: String,
    val condition: Expr,
    val action: Action
) : Declaration
```

Đây là mô hình rút gọn. Một DSL thực tế có thể có thêm import, namespace, comment, annotation, modifier và source location.

### 5.2. Tách biểu thức và câu lệnh

Biểu thức (expression) tạo ra một giá trị hoặc kết quả có thể được dùng trong biểu thức lớn hơn. Câu lệnh (statement) biểu thị một hành động hoặc cấu trúc điều khiển. Không phải DSL nào cũng cần phân biệt hai loại này giống ngôn ngữ lập trình tổng quát, nhưng tách chúng rõ ràng thường giúp thiết kế AST dễ hiểu.

Ví dụ:

- `order.total >= 1_000_000` là biểu thức Boolean.
- `shipping.fee = 0` có thể là một câu lệnh gán hoặc một action node tùy ngữ nghĩa DSL.
- `if condition then action` có thể là một câu lệnh điều khiển.
- `Money(100, VND)` có thể là biểu thức tạo giá trị tiền.

### 5.3. Node có kiểu rõ ràng

Nên dùng loại node riêng cho các khái niệm có ngữ nghĩa khác nhau. `NumberLiteral`, `StringLiteral`, `BooleanLiteral` và `NullLiteral` có thể cùng là literal nhưng cần lưu giá trị theo kiểu phù hợp. `MemberAccess` khác `FunctionCall`; `Assignment` khác `EqualityComparison`.

Việc dùng một node chung chứa tên chuỗi tùy ý như `Operation("and", ...)` có thể đơn giản lúc đầu, nhưng dễ dẫn đến kiểm tra rải rác và lỗi khi thêm toán tử. Một hệ thống node có kiểu giúp compiler và IDE xử lý từng trường hợp có cấu trúc rõ ràng.

### 5.4. Danh sách và quan hệ cha-con

Node chương trình thường có danh sách khai báo; node block có danh sách câu lệnh; node hàm có danh sách tham số và thân hàm; node gọi hàm có biểu thức callee và danh sách đối số.

Không nên biến mọi quan hệ trong mô hình miền thành node con của AST nếu chúng là liên kết tham chiếu đến khai báo khác. Ví dụ, một `Identifier` trong biểu thức có thể được phân giải thành symbol hoặc declaration qua bảng ký hiệu. Liên kết này thường được lưu trong annotation hoặc cấu trúc semantic riêng.

## 6. Thông tin vị trí nguồn trong AST

Mặc dù AST lược bỏ nhiều chi tiết cú pháp, node thường cần giữ vị trí nguồn (source location hoặc source span). Thông tin này cho biết node đến từ đoạn nào trong tệp DSL.

Một span có thể chứa:

- Tệp hoặc module nguồn.
- Offset bắt đầu và kết thúc.
- Dòng và cột bắt đầu/kết thúc, nếu hệ thống cần.
- Tham chiếu đến token hoặc vùng văn bản gốc.

Ví dụ kiểu dữ liệu:

```kotlin
data class SourceSpan(
    val file: String,
    val startOffset: Int,
    val endOffset: Int
)

data class NumberLiteral(
    val value: Long,
    val span: SourceSpan
) : Expr
```

Khi `order.total` không tồn tại, bộ kiểm tra có thể báo lỗi ngay tại span của `MemberAccess`. Khi người dùng chọn một node trong IDE, công cụ có thể tìm đúng vùng văn bản tương ứng.

Với Unicode, offset có thể được tính theo byte, code unit hoặc code point. Parser và editor phải thống nhất cách chuyển đổi. Nếu không, thông báo lỗi có thể trỏ lệch vị trí khi tệp có ký tự nhiều byte hoặc ký tự ngoài BMP.

## 7. AST được dùng để làm gì?

AST không chỉ là kết quả trung gian của parser. Nó là cấu trúc dùng chung cho nhiều hoạt động của compiler, interpreter và công cụ phát triển DSL.

### 7.1. Kiểm tra ngữ nghĩa

Parser có thể xác định biểu thức có đúng cú pháp nhưng không thể luôn xác định nó có ý nghĩa trong miền hay không. AST cho phép semantic analyzer duyệt từng node và kiểm tra:

- Identifier có được khai báo không?
- Thuộc tính có tồn tại trên kiểu đối tượng không?
- Hàm được gọi có nhận đúng số lượng và kiểu tham số không?
- Toán tử có áp dụng được cho các kiểu toán hạng không?
- Giá trị có nằm trong miền hợp lệ không?
- Một quy tắc có tham chiếu đến trạng thái hoặc hành động được phép không?

Ví dụ, `order.total >= 1_000_000` có thể hợp lệ nếu `order` là `Order` và `total` là `Money` hoặc một kiểu số có đơn vị phù hợp. Nếu `total` là `Date`, semantic analyzer phải từ chối phép so sánh với literal số.

### 7.2. Phân giải tên và bảng ký hiệu

AST chứa các node tham chiếu tên, nhưng để biết tên đó trỏ đến khai báo nào, hệ thống cần name resolution (phân giải tên). Một bảng ký hiệu (symbol table) lưu các khai báo trong scope và cho phép tra cứu identifier.

Ví dụ, trong:

```text
entity Order {
    total: Money
}

rule highValue {
    when order.total >= 1_000_000
    then markForReview(order)
}
```

Parser tạo node cho identifier `order` và member `total`. Name resolver tìm `order` trong ngữ cảnh của rule, xác định kiểu của nó là `Order`, rồi tra thuộc tính `total` trong định nghĩa entity `Order`. Kết quả phân giải có thể được gắn vào AST hoặc lưu trong semantic model.

### 7.3. Kiểm tra kiểu

Type checker xác định kiểu của từng biểu thức và xác thực các phép toán. Ví dụ:

- `Money + Money` có thể hợp lệ khi cùng currency hoặc có quy tắc quy đổi được định nghĩa.
- `Date + Integer` có thể có nghĩa cộng số ngày nếu DSL hỗ trợ rõ.
- `String and Boolean` thường không hợp lệ.
- Điều kiện của `when` có thể bắt buộc phải là Boolean.

AST giúp type checker xử lý cấu trúc biểu thức theo từng loại node. Kết quả kiểm tra có thể được ghi vào semantic model để interpreter hoặc code generator không phải suy luận lại.

### 7.4. Thực thi bằng interpreter

Interpreter (trình thông dịch) có thể duyệt AST và tính kết quả trực tiếp. Ví dụ, với node `And`, interpreter đánh giá nhánh trái và nhánh phải theo quy tắc short-circuit nếu DSL quy định như vậy. Với node `MemberAccess`, nó đọc thuộc tính từ môi trường thực thi.

Mã giả:

```text
evaluate(NumberLiteral(value)) = value
evaluate(BooleanLiteral(value)) = value
evaluate(Equal(left, right)) = evaluate(left) == evaluate(right)
evaluate(And(left, right)) =
    evaluate(left) AND evaluate(right)
evaluate(MemberAccess(target, name)) =
    readProperty(evaluate(target), name)
```

Interpreter cần xác định rõ cách xử lý lỗi runtime, giá trị thiếu, phép chia cho 0, truy cập thuộc tính không tồn tại và giới hạn tài nguyên.

### 7.5. Sinh mã hoặc chuyển sang ngôn ngữ khác

Code generator có thể chuyển AST sang mã nguồn của ngôn ngữ mục tiêu, SQL, JSON, cấu hình hạ tầng hoặc một dạng biểu diễn khác. Ví dụ, một AST truy vấn DSL có thể được chuyển thành SQL có tham số thay vì nối chuỗi tùy ý.

```text
AST truy vấn DSL
      |
      v
Kiểm tra tên và kiểu
      |
      v
SQL generator
      |
      v
SELECT ... WHERE ...
```

Việc sinh mã từ AST có cấu trúc giúp tránh phải phân tích và ghép văn bản thủ công ở nhiều nơi. Generator cần bảo đảm escaping, tham số hóa và ánh xạ kiểu phù hợp với backend.

### 7.6. Tối ưu hóa

AST có thể được biến đổi để biểu thức đơn giản hơn hoặc loại bỏ công việc không cần thiết, miễn là giữ nguyên ngữ nghĩa.

Ví dụ:

```text
not (A == B)
```

có thể được chuyển thành:

```text
A != B
```

Chỉ được áp dụng phép biến đổi này nếu DSL định nghĩa `not`, equality và inequality tương thích theo quy tắc logic tương ứng. Với giá trị null/unknown hoặc kiểu có phép so sánh đặc biệt, phép biến đổi có thể không còn tương đương.

Các tối ưu hóa khác gồm constant folding, loại bỏ nhánh không thể chạy, chuẩn hóa điều kiện và gộp các phép lọc. Mọi phép biến đổi cần có quy tắc ngữ nghĩa rõ và kiểm thử tương đương.

### 7.7. Tạo tài liệu và công cụ IDE

AST là nền tảng cho nhiều công cụ:

- Tô màu cú pháp và điều hướng đến khai báo.
- Tự động hoàn thành thuộc tính, hàm và từ khóa.
- Tìm nơi một entity hoặc rule được tham chiếu.
- Đổi tên symbol trên toàn bộ chương trình.
- Hiển thị cây cấu trúc hoặc sơ đồ quy tắc.
- Tạo tài liệu tham khảo từ các khai báo.
- Cung cấp quick fix cho lỗi phổ biến.

Để hỗ trợ các chức năng này, AST cần liên kết với source span, symbol và kiểu dữ liệu đã phân giải. Một AST chỉ giữ tên chuỗi mà không có thông tin nguồn hoặc semantic model có thể chưa đủ cho trải nghiệm IDE tốt.

## 8. AST trong ví dụ DSL quy tắc nghiệp vụ

Giả sử DSL có quy tắc:

```text
rule freeShipping {
    when order.total >= 1_000_000 and order.status == PAID
    then shipping.fee = 0
}
```

Parser có thể tạo cấu trúc AST khái quát:

```text
RuleDeclaration
├── name: "freeShipping"
├── condition: And
│   ├── GreaterEqual
│   │   ├── MemberAccess(order, total)
│   │   └── NumberLiteral(1000000)
│   └── Equal
│       ├── MemberAccess(order, status)
│       └── EnumLiteral(PAID)
└── action: Assignment
    ├── target: MemberAccess(shipping, fee)
    └── value: NumberLiteral(0)
```

Các bước xử lý tiếp theo có thể diễn ra như sau:

1. **Phân giải tên:** xác định `order`, `shipping`, `total`, `status` và `fee` thuộc những entity hoặc context nào.
2. **Kiểm tra kiểu:** xác nhận `total` có thể so sánh với số tiền; `status` có thể so sánh với enum `OrderStatus`; điều kiện tổng hợp trả về Boolean; `shipping.fee` nhận được giá trị tiền hợp lệ.
3. **Kiểm tra miền:** xác nhận rule có quyền thay đổi phí giao hàng, điều kiện không vi phạm ràng buộc và hành động hợp lệ trong giai đoạn hiện tại.
4. **Tạo semantic model:** gắn kiểu và liên kết symbol đã phân giải vào cấu trúc.
5. **Thực thi hoặc sinh mã:** interpreter áp dụng rule cho đơn hàng; hoặc compiler chuyển rule sang mã của hệ thống quy tắc khác.

AST làm cho các bước này độc lập với cách người dùng viết dấu cách hoặc xuống dòng. Hai biểu thức có cùng cấu trúc và ngữ nghĩa có thể tạo ra AST tương đương dù cách trình bày khác nhau.

## 9. Duyệt và biến đổi AST

Khi AST có nhiều loại node, chương trình cần cách duyệt có tổ chức. Hai kỹ thuật thường gặp là visitor và recursive traversal.

### 9.1. Recursive traversal

Với cây đơn giản, mỗi hàm xử lý node có thể gọi đệ quy đến các node con:

```kotlin
fun countNodes(expr: Expr): Int = when (expr) {
    is Identifier -> 1
    is NumberLiteral -> 1
    is MemberAccess -> 1 + countNodes(expr.target)
    is Equal -> 1 + countNodes(expr.left) + countNodes(expr.right)
    is GreaterEqual -> 1 + countNodes(expr.left) + countNodes(expr.right)
    is And -> 1 + countNodes(expr.left) + countNodes(expr.right)
}
```

Đây là ví dụ rút gọn; một AST thực tế cần xử lý mọi loại node. Recursive traversal dễ hiểu khi cấu trúc nhỏ, nhưng nhiều thao tác khác nhau có thể làm lặp lại logic duyệt.

### 9.2. Visitor pattern

Visitor tách cấu trúc node khỏi các thao tác cần thực hiện trên node. Có thể có visitor để in AST, kiểm tra kiểu, đánh giá biểu thức, sinh mã hoặc thu thập symbol.

```kotlin
interface ExprVisitor<R> {
    fun visitIdentifier(node: Identifier): R
    fun visitNumber(node: NumberLiteral): R
    fun visitMemberAccess(node: MemberAccess): R
    fun visitEqual(node: Equal): R
    fun visitGreaterEqual(node: GreaterEqual): R
    fun visitAnd(node: And): R
}
```

Visitor phù hợp khi AST có cấu trúc tương đối ổn định nhưng cần nhiều thao tác khác nhau. Nếu thường xuyên thêm loại node mới, mọi visitor có thể cần được cập nhật. Một số ngôn ngữ dùng sealed class, pattern matching hoặc algebraic data types để làm rõ các trường hợp cần xử lý.

### 9.3. Biến đổi AST

Một pass (lượt xử lý) có thể nhận AST và tạo AST mới sau khi thay đổi một số node. Ví dụ, constant folding biến biểu thức số có thể tính trước thành một literal:

```text
Add(NumberLiteral(2), Multiply(NumberLiteral(3), NumberLiteral(4)))

-- sau constant folding -->

NumberLiteral(14)
```

Trong hệ thống cần giữ vị trí nguồn hoặc comment, phép biến đổi phải xác định cách bảo toàn hoặc kết hợp source span. Nếu AST được dùng để hiển thị lại mã, có thể cần CST hoặc token gốc song song để không mất chi tiết định dạng.

## 10. AST, semantic model và IR khác nhau thế nào?

Các thuật ngữ này thường xuất hiện cùng nhau nhưng có vai trò khác nhau:

| Cấu trúc | Vai trò | Ví dụ thông tin chứa |
|---|---|---|
| Parse tree / CST | Giữ cấu trúc gần với ngữ pháp và văn bản nguồn | Node grammar, token, dấu ngoặc, dấu phân cách |
| AST | Biểu diễn cấu trúc cú pháp trừu tượng | Rule, biểu thức AND, phép so sánh, literal |
| Semantic model | Bổ sung ý nghĩa đã phân giải | Symbol được tham chiếu, kiểu biểu thức, quan hệ entity |
| IR (Intermediate Representation) | Biểu diễn phù hợp cho phân tích, tối ưu hoặc sinh mã | Control flow, phép toán đã chuẩn hóa, tham chiếu đã phân giải |

Không phải mọi dự án cần tách bốn cấu trúc thành bốn kiểu dữ liệu riêng. Một AST có thể được bổ sung annotation ngữ nghĩa; một IR có thể gần giống AST. Việc tách riêng có ích khi mỗi giai đoạn có yêu cầu khác nhau hoặc cần nhiều backend.

Ví dụ, AST giữ `MemberAccess(Identifier("order"), "total")`. Sau name resolution, semantic model biết `order` là biến có kiểu `Order` và `total` là thuộc tính kiểu `Money`. IR có thể chuyển phép truy cập đó thành một thao tác đọc trường đã gắn symbol ID cụ thể.

## 11. AST trong DSL nội bộ và DSL bên ngoài

AST thường gắn với DSL bên ngoài vì parser đọc văn bản và tạo cây. Tuy nhiên, DSL nội bộ cũng có thể tạo AST hoặc một mô hình tương tự.

Với DSL bên ngoài:

1. Người dùng viết văn bản theo grammar riêng.
2. Parser chuyển token thành AST.
3. Các bước phân tích và thực thi làm việc trên AST.

Với DSL nội bộ:

1. Người dùng viết lời gọi hàm, builder hoặc lambda trong ngôn ngữ chủ.
2. Các hàm của DSL có thể thực thi ngay hoặc tạo đối tượng biểu diễn cấu trúc.
3. Các đối tượng builder có thể tạo thành AST, query model hoặc workflow graph.

Ví dụ, một API truy vấn dạng fluent:

```kotlin
query {
    from(Orders)
    select(Order::total)
    where { status == PAID }
}
```

có thể tạo một cây query gồm `From`, `Select` và `Where`. Dù parser của Kotlin xử lý cú pháp bên ngoài, thư viện DSL vẫn có thể xây dựng một AST miền để kiểm tra, tối ưu và chuyển thành SQL.

Điều này cho thấy AST là mô hình cấu trúc hữu ích cho xử lý DSL, không phụ thuộc việc cú pháp là bên ngoài hay được nhúng trong ngôn ngữ chủ.

## 12. Thiết kế AST tốt cho DSL

### 12.1. Phản ánh khái niệm của miền

Node nên mang tên và cấu trúc thể hiện đúng các khái niệm mà DSL hỗ trợ. Nếu DSL có `Rule`, `Condition` và `Action`, AST nên thể hiện chúng rõ ràng thay vì chỉ lưu một danh sách chuỗi token.

### 12.2. Không gắn chặt AST với văn bản quá mức

AST không nên chỉ là một bản sao của tệp nguồn dưới dạng cây. Hãy giữ những thông tin cần cho xử lý ngữ nghĩa và các công cụ. Nếu cần bảo toàn comment, khoảng trắng hoặc cách viết gốc, có thể lưu token/CST hoặc source span riêng.

### 12.3. Dùng kiểu node rõ ràng

Các loại node nên phân biệt rõ biểu thức, khai báo, câu lệnh và literal. Kiểu node rõ ràng giúp visitor và compiler xử lý từng trường hợp có kiểm soát, đồng thời hạn chế trạng thái không hợp lệ.

### 12.4. Giữ source span và thông tin chẩn đoán

Node nên có khả năng liên kết với vị trí nguồn để báo lỗi, hiển thị cảnh báo và hỗ trợ IDE. Nếu một phép biến đổi tạo node mới từ nhiều node cũ, hãy quy định source span của node kết quả.

### 12.5. Ưu tiên cấu trúc bất biến khi phù hợp

AST bất biến giúp các bước phân tích không vô tình thay đổi dữ liệu mà bước khác đang sử dụng. Một pass có thể tạo cây mới thay vì sửa trực tiếp cây cũ. Điều này hỗ trợ cache, chạy song song và so sánh kết quả, dù có thể cần cân nhắc chi phí cấp phát.

### 12.6. Tách liên kết ngữ nghĩa khỏi cấu trúc cú pháp

Không nên nhồi mọi thông tin phân giải tên, kiểu, quyền và trạng thái runtime vào các node cú pháp nếu chúng có vòng đời khác nhau. Có thể dùng semantic model hoặc annotation riêng để AST gọn và dễ tái sử dụng.

### 12.7. Xác định chính sách lỗi và node lỗi

Parser có thể gặp lỗi giữa tệp. Với công cụ tương tác như IDE, việc dừng hoàn toàn có thể làm mất khả năng hỗ trợ phần văn bản còn lại. Một số parser tạo `ErrorNode` hoặc node chưa hoàn chỉnh để tiếp tục phân tích và cung cấp nhiều diagnostic. Với compiler chạy batch, chính sách có thể đơn giản hơn nhưng vẫn cần thông báo lỗi chính xác.

## 13. Giới hạn và chi phí khi dùng AST

AST hữu ích nhưng cũng tạo thêm cấu trúc và các bước xử lý cần bảo trì.

- **Chi phí thiết kế:** phải định nghĩa node, trường dữ liệu, kiểu và quan hệ cho từng thành phần DSL.
- **Chi phí chuyển đổi:** parser, semantic analyzer, interpreter và generator cần thống nhất về AST.
- **Thay đổi ngôn ngữ:** thêm cú pháp mới có thể yêu cầu thêm node và cập nhật mọi visitor hoặc pass.
- **Bảo toàn nguồn:** AST rút gọn có thể làm mất comment và định dạng nếu không lưu token/CST riêng.
- **Hiệu năng và bộ nhớ:** chương trình lớn có thể tạo nhiều node; cần cân nhắc cấu trúc, cấp phát và cache.
- **Độ phức tạp không cần thiết:** một DSL rất nhỏ chỉ có vài phép toán có thể dùng trực tiếp biểu diễn đơn giản mà chưa cần một framework AST lớn.

Vì vậy, AST nên được xây dựng theo nhu cầu xử lý thực tế. Không cần thiết kế một hệ thống compiler tổng quát nếu DSL chỉ cần một bộ lọc nhỏ và có thể dùng cấu trúc dữ liệu đơn giản.

## 14. Kết luận

AST là cây cú pháp trừu tượng biểu diễn cấu trúc có ý nghĩa của chương trình DSL. Nó thường được tạo sau bước phân tích cú pháp và trở thành đầu vào chung cho phân giải tên, kiểm tra kiểu, kiểm tra quy tắc miền, thực thi, sinh mã, tối ưu hóa và công cụ IDE.

AST khác parse tree ở mức độ trừu tượng và mục đích sử dụng: parse tree bám sát grammar, còn AST tập trung vào các cấu trúc cần cho xử lý chương trình. Một AST hữu ích nên có node có kiểu rõ ràng, giữ thông tin vị trí nguồn khi cần, tách dữ liệu ngữ nghĩa phù hợp và có cách duyệt hoặc biến đổi nhất quán.

Khi thiết kế DSL, hãy bắt đầu từ các khái niệm mà ngôn ngữ cần biểu đạt, xác định những thao tác sẽ thực hiện trên cấu trúc đó, rồi chọn mô hình AST vừa đủ. Cây được thiết kế tốt sẽ giúp các bước xử lý DSL dễ mở rộng, dễ kiểm tra và ít phụ thuộc vào cách người dùng trình bày văn bản.
